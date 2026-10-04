"""Parse NWS raw gridpoint (NDFD) JSON into hourly local-time series.

api.weather.gov/gridpoints/{wfo}/{x},{y} returns every NDFD element as a list of
{"validTime": "2026-09-29T18:00:00+00:00/PT3H", "value": ...}. This module
expands those into one value per UTC hour and converts units to F / mph / inches.
"""
import re
from datetime import datetime, timedelta, timezone

_DUR = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?")
HOUR = timedelta(hours=1)

CONVERT = {
    "wmoUnit:degC": lambda c: c * 9 / 5 + 32,
    "wmoUnit:km_h-1": lambda k: k * 0.621371,
    "wmoUnit:mm": lambda m: m / 25.4,
    "wmoUnit:percent": lambda p: p,
    "wmoUnit:degree_(angle)": lambda d: d,
}

# (field name, is an accumulation that must be split across its hours)
FIELDS = [
    ("temperature", False), ("dewpoint", False), ("relativeHumidity", False),
    ("apparentTemperature", False), ("heatIndex", False), ("windChill", False),
    ("skyCover", False), ("windDirection", False), ("windSpeed", False),
    ("windGust", False), ("probabilityOfPrecipitation", False),
    ("quantitativePrecipitation", True), ("snowfallAmount", True),
    ("iceAccumulation", True),
]


def parse_valid_time(vt):
    start, dur = vt.split("/")
    st = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(timezone.utc)
    m = _DUR.fullmatch(dur)
    d, h, mi = (int(x or 0) for x in m.groups()) if m else (0, 1, 0)
    return st, timedelta(days=d, hours=h, minutes=mi)


def _hours_in(dur):
    return max(1, int(dur.total_seconds() // 3600))


def expand(layer, accum=False):
    """Layer -> {utc_hour_datetime: converted value}."""
    conv = CONVERT.get(layer.get("uom"), lambda v: v)
    out = {}
    for item in layer.get("values", []):
        val = item.get("value")
        if val is None:
            continue
        st, dur = parse_valid_time(item["validTime"])
        n = _hours_in(dur)
        v = conv(val)
        if accum:
            v = v / n
        for i in range(n):
            out[st + i * HOUR] = v
    return out


def periods(layer):
    """Layer -> list of (start_utc, end_utc, converted value), e.g. max/min temp."""
    if not layer:
        return []
    conv = CONVERT.get(layer.get("uom"), lambda v: v)
    res = []
    for item in layer.get("values", []):
        if item.get("value") is None:
            continue
        st, dur = parse_valid_time(item["validTime"])
        res.append((st, st + dur, conv(item["value"])))
    return res


def hour_range(start, end):
    t = start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = end.astimezone(timezone.utc)
    while t < end:
        yield t
        t += HOUR


class Grid:
    def __init__(self, gridpoint_json, tz):
        p = gridpoint_json["properties"]
        self.tz = tz
        self.update_time = p.get("updateTime")
        self.h = {f: expand(p[f], acc) for f, acc in FIELDS if p.get(f)}
        self.max_t = periods(p.get("maxTemperature"))
        self.min_t = periods(p.get("minTemperature"))
        self.weather = {}
        for item in (p.get("weather") or {}).get("values", []):
            st, dur = parse_valid_time(item["validTime"])
            vals = [v for v in (item.get("value") or []) if v and v.get("weather")]
            for i in range(_hours_in(dur)):
                self.weather[st + i * HOUR] = vals
        last = [max(d) for d in self.h.values() if d]
        self.end = max(last) if last else None
        q = self.h.get("quantitativePrecipitation")
        self.qpf_end = (max(q) + HOUR) if q else None  # NDFD QPF stops ~72 h out
        self.ext_qpf, self.ext_model = {}, None

    def add_extended_qpf(self, hourly, model):
        """Hourly precip guidance (inches, keyed by UTC hour start) used only past qpf_end."""
        self.ext_qpf = {t: v for t, v in hourly.items() if self.qpf_end is None or t >= self.qpf_end}
        self.ext_model = model if self.ext_qpf else None

    def rain_total(self, start, end):
        """-> (inches, 'ndfd' | 'guidance' | 'mixed' | None if no data covers the window)."""
        nd = self.h.get("quantitativePrecipitation", {})
        first = min(nd) if nd else None
        tot, src = 0.0, set()
        missing = 0
        for t in hour_range(start, end):
            if first and t < first:
                continue  # already in the past when the forecast was issued
            if t in nd:
                tot += nd[t]; src.add("ndfd")
            elif t in self.ext_qpf:
                tot += self.ext_qpf[t]; src.add("guidance")
            else:
                missing += 1
        if not src or missing > 12:
            return None, None
        return tot, ("mixed" if len(src) == 2 else src.pop())

    def series(self, field, start, end):
        d = self.h.get(field, {})
        return [d[t] for t in hour_range(start, end) if t in d]

    def value_at(self, field, t):
        return self.h.get(field, {}).get(t.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0))

    def weather_in(self, start, end):
        return [(t, self.weather.get(t, [])) for t in hour_range(start, end)]

    def pop_at(self, t):
        return self.value_at("probabilityOfPrecipitation", t) or 0
