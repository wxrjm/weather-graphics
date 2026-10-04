"""Synthetic NDFD gridpoint in the exact api.weather.gov raw format, for offline testing.
Scenario: warm & humid, cold front with storms on day 3, then cooler, breezy and dry.
"""
import math
from datetime import datetime, timedelta, timezone

HOUR = timedelta(hours=1)


def _f2c(f):
    return (f - 32) * 5 / 9


def _heat_index(t, rh):
    if t < 80:
        return t
    return (-42.379 + 2.04901523 * t + 10.14333127 * rh - .22475541 * t * rh - .00683783 * t * t
            - .05481717 * rh * rh + .00122874 * t * t * rh + .00085282 * t * rh * rh - .00000199 * t * t * rh * rh)


def _rh(t, td):
    tc, dc = _f2c(t), _f2c(td)
    return 100 * math.exp(17.625 * dc / (243.04 + dc)) / math.exp(17.625 * tc / (243.04 + tc))


def build(now, tz):
    # day index -> (high, low, dew, sky, pop_by_local_hour(fn), wx, qpf_total, wind, gust, dir)
    plan = [
        (86, 70, 71, 35, 10, None, 0, 8, 14, 200),
        (89, 72, 73, 45, 30, ("chance", "thunderstorms"), 0.1, 10, 20, 210),
        (84, 66, 72, 75, 70, ("scattered", "thunderstorms"), 0.8, 14, 30, 230),
        (74, 57, 56, 20, 5, None, 0, 16, 34, 320),
        (72, 55, 52, 10, 0, None, 0, 10, 20, 340),
        (75, 58, 55, 25, 5, None, 0, 7, 14, 30),
        (78, 62, 60, 50, 20, ("slight_chance", "rain_showers"), 0.02, 9, 16, 90),
        (80, 64, 63, 55, 25, ("chance", "rain_showers"), 0.05, 10, 18, 150),
        (80, 64, 63, 55, 25, None, 0, 10, 18, 150),
    ]
    start_local = datetime.combine(now.date(), datetime.min.time(), tz)
    hours = [start_local + i * HOUR for i in range(8 * 24)]

    def shape(h):
        if 6 <= h < 15:
            return 0.5 - 0.5 * math.cos(math.pi * (h - 6) / 9)
        if h >= 15:
            return 0.5 + 0.5 * math.cos(math.pi * (h - 15) / 15)
        return 0.5 + 0.5 * math.cos(math.pi * (h + 9) / 15)

    layers = {k: [] for k in ["temperature", "dewpoint", "relativeHumidity", "apparentTemperature",
                              "heatIndex", "windChill", "skyCover", "windDirection", "windSpeed",
                              "windGust", "probabilityOfPrecipitation", "quantitativePrecipitation",
                              "snowfallAmount", "iceAccumulation", "weather"]}
    for t in hours:
        di = (t.date() - now.date()).days
        hi, lo, dew, sky, pop, wx, qpf, wnd, gst, wd = plan[di]
        h = t.hour
        if h >= 15:
            temp = plan[di + 1][1] + (hi - plan[di + 1][1]) * shape(h)
        elif h < 6:
            temp = lo + (plan[max(di - 1, 0)][0] - lo) * shape(h)
        else:
            temp = lo + (hi - lo) * shape(h)
        dp = min(dew, temp)
        rh = _rh(temp, dp)
        aft = 13 <= h <= 21
        p = pop if (aft or pop <= 10) else int(pop * 0.4)
        diurnal = 0.55 + 0.45 * math.sin(math.pi * max(0, min(h - 7, 12)) / 12)
        vt = t.astimezone(timezone.utc).isoformat() + "/PT1H"
        
        add = lambda k, v: layers[k].append({"validTime": vt, "value": v})
        add("temperature", _f2c(temp)); add("dewpoint", _f2c(dp)); add("relativeHumidity", round(rh))
        hix = _heat_index(temp, rh)
        add("heatIndex", _f2c(hix) if temp >= 80 else None)
        add("apparentTemperature", _f2c(hix))
        add("windChill", None)
        add("skyCover", min(100, sky + (20 if aft and pop >= 30 else 0)))
        add("windDirection", wd); add("windSpeed", wnd * diurnal / 0.621371)
        add("windGust", gst * diurnal / 0.621371)
        add("probabilityOfPrecipitation", p)
        add("quantitativePrecipitation", (qpf * 25.4 / 9) if (aft and qpf) else 0)
        add("snowfallAmount", 0); add("iceAccumulation", 0)
        w = [{"coverage": wx[0], "weather": wx[1], "intensity": None, "visibility": {"unitCode": "wmoUnit:km", "value": None},
              "attributes": []}] if wx and (aft or p >= 15) else [{"coverage": None, "weather": None, "intensity": None,
                                                                   "attributes": []}]
        if di == 4 and h < 9:
            w = [{"coverage": "patchy", "weather": "fog", "intensity": None, "attributes": []}]
        layers["weather"].append({"validTime": vt, "value": w})

    def uom(k):
        return {"relativeHumidity": "wmoUnit:percent", "skyCover": "wmoUnit:percent",
                "probabilityOfPrecipitation": "wmoUnit:percent", "windDirection": "wmoUnit:degree_(angle)",
                "windSpeed": "wmoUnit:km_h-1", "windGust": "wmoUnit:km_h-1",
                "quantitativePrecipitation": "wmoUnit:mm", "snowfallAmount": "wmoUnit:mm",
                "iceAccumulation": "wmoUnit:mm"}.get(k, "wmoUnit:degC")

    # real NDFD QPF/snow/ice stop ~72 h out -- mimic that so the sample exercises the gap
    cutoff = now.astimezone(timezone.utc) + timedelta(hours=72)
    for k in ("quantitativePrecipitation", "snowfallAmount", "iceAccumulation"):
        layers[k] = [x for x in layers[k] if datetime.fromisoformat(x["validTime"].split("/")[0]) < cutoff]
    props = {k: ({"values": v} if k == "weather" else {"uom": uom(k), "values": v}) for k, v in layers.items()}
    maxt, mint = [], []
    for di in range(8):
        d = now.date() + timedelta(days=di)
        day7 = datetime.combine(d, datetime.min.time(), tz) + 7 * HOUR
        maxt.append({"validTime": day7.astimezone(timezone.utc).isoformat() + "/PT13H", "value": _f2c(plan[di][0])})
        mint.append({"validTime": (day7 + 12 * HOUR).astimezone(timezone.utc).isoformat() + "/PT14H", "value": _f2c(plan[di + 1][1])})
    props["maxTemperature"] = {"uom": "wmoUnit:degC", "values": maxt}
    props["minTemperature"] = {"uom": "wmoUnit:degC", "values": mint}
    props["updateTime"] = now.astimezone(timezone.utc).isoformat()
    gridpoint = {"properties": props}

    obs = {"properties": {
        "timestamp": (now - timedelta(minutes=9)).isoformat(), "textDescription": "Partly Cloudy",
        "temperature": {"value": _f2c(84)}, "dewpoint": {"value": _f2c(71)},
        "relativeHumidity": {"value": 65}, "heatIndex": {"value": _f2c(90)}, "windChill": {"value": None},
        "windDirection": {"value": 200}, "windSpeed": {"value": 14.8}, "windGust": {"value": None},
        "barometricPressure": {"value": 101490}, "visibility": {"value": 16090}}}
    return gridpoint, sample_alerts(now), obs


def extended_qpf(grid):
    """Synthetic NBM-style hourly rain for the sample: showers days 6-7 afternoons."""
    out = {}
    if not grid.qpf_end:
        return out
    t = grid.qpf_end
    for i in range(5 * 24):
        h = t + i * HOUR
        loc = h.astimezone(grid.tz)
        di = (loc.date() - grid.qpf_end.astimezone(grid.tz).date()).days
        out[h] = 0.03 if (di >= 3 and 13 <= loc.hour <= 20) else 0.0
    return out


def _alert(event, severity, ends, same, desc, instr, headline="", geometry=None):
    return {"id": event + ends.isoformat(), "geometry": geometry, "properties": {
        "event": event, "severity": severity, "status": "Actual", "messageType": "Alert",
        "headline": headline or f"{event} issued by NWS Wakefield VA",
        "ends": ends.isoformat(), "expires": ends.isoformat(),
        "geocode": {"SAME": ["0" + f for f in same]},
        "areaDesc": "; ".join(same), "description": desc, "instruction": instr}}


def sample_alerts(now):
    """Realistic Wakefield-style alerts: a storm-based warning, a watch, and a coastal advisory."""
    svr_poly = {"type": "Polygon", "coordinates": [[[-76.62, 36.95], [-76.02, 36.98], [-75.95, 36.72],
                                                     [-76.30, 36.60], [-76.66, 36.70], [-76.62, 36.95]]]}
    return [
        _alert("Severe Thunderstorm Warning", "Severe", now + timedelta(minutes=45),
               ["51710", "51810", "51550", "51740", "51800"],
               "The National Weather Service in Wakefield has issued a\n\n* Severe Thunderstorm Warning for...\n"
               "The City of Norfolk in southeastern Virginia...\n\n* Until 715 PM EDT.\n\n"
               "* At 630 PM EDT, a severe thunderstorm was located over Portsmouth, moving east at 30 mph.\n\n"
               "HAZARD...60 mph wind gusts and quarter size hail.\n\nSOURCE...Radar indicated.\n\n"
               "IMPACT...Hail damage to vehicles is expected. Expect wind damage to roofs, siding, and trees.",
               "For your protection move to an interior room on the lowest floor of a building.",
               geometry=svr_poly),
        _alert("Severe Thunderstorm Watch", "Severe", now + timedelta(hours=4),
               ["51710", "51810", "51550", "51740", "51800", "51650", "51700", "51735", "51199", "51095",
                "51830", "51093", "51181", "51175", "51620", "51073", "51115", "37053", "37029", "37139",
                "37143", "37041", "37073", "37091"],
               "SEVERE THUNDERSTORM WATCH 612 REMAINS VALID UNTIL 11 PM EDT THIS EVENING FOR THE FOLLOWING AREAS",
               "", headline="Severe Thunderstorm Watch issued until 11 PM EDT by NWS Storm Prediction Center"),
        _alert("Coastal Flood Advisory", "Minor", now + timedelta(hours=28),
               ["51710", "51810", "51740", "51650", "51700", "51735", "51001", "51131"],
               "* WHAT...Up to one half foot of inundation above ground level in low-lying areas near "
               "shorelines and tidal waterways.\n\n* WHERE...Norfolk, Virginia Beach, Portsmouth, Hampton, "
               "Newport News, Poquoson and the Virginia Eastern Shore.\n\n* WHEN...From 6 AM to 11 AM EDT "
               "Wednesday, around the time of high tide.\n\n* IMPACTS...Minor flooding of the most vulnerable "
               "roads and properties. Sewells Point is expected to reach 4.8 feet MLLW.",
               "If travel is required, allow extra time as some roads may be closed. Do not drive around "
               "barricades or through water of unknown depth."),
    ]


def _ellipse(cx, cy, rx, ry, rot=0.0, n=72, wobble=0.0):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        r = 1 + wobble * math.sin(3 * a) + wobble * 0.5 * math.cos(5 * a)
        x, y = rx * r * math.cos(a), ry * r * math.sin(a)
        xr = x * math.cos(rot) - y * math.sin(rot)
        yr = x * math.sin(rot) + y * math.cos(rot)
        pts.append([round(cx + xr, 4), round(cy + yr, 4)])
    pts.append(pts[0])
    return [[pts]]


def _qpf_sample():
    return [{"value": v, "polys": _ellipse(-77.2 + 0.2 * i, 36.4 + 0.02 * i, 5.4 - 0.7 * i, 2.8 - 0.35 * i, 0.45,
                                           wobble=0.05 + 0.01 * i)}
            for i, v in enumerate([0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0])]


def sample_outlooks():
    """Made-up SPC / ERO / QPF polygons around Hampton Roads for offline testing."""
    from .outlooks import SPC_CATS, ERO_CATS
    spc = lambda code, polys: {**dict(zip(("level", "code", "name", "color"), next(c for c in SPC_CATS if c[1] == code)[:4])),
                               "polys": polys, "times": {}}
    ero = lambda code, polys: {**dict(zip(("level", "code", "name", "color"), next(c for c in ERO_CATS if c[1] == code)[:4])),
                               "polys": polys, "times": {}}
    return {
        "spc": {
            1: [spc("TSTM", _ellipse(-77.2, 37.0, 3.2, 2.2, 0.5, wobble=0.05)),
                spc("MRGL", _ellipse(-76.9, 36.9, 2.0, 1.3, 0.6, wobble=0.07)),
                spc("SLGT", _ellipse(-76.5, 36.8, 1.1, 0.65, 0.7, wobble=0.08))],
            2: [spc("TSTM", _ellipse(-76.0, 35.8, 2.6, 1.4, 0.3, wobble=0.05)),
                spc("MRGL", _ellipse(-76.3, 35.6, 1.3, 0.6, 0.3, wobble=0.06))],
            3: [],
        },
        "probs": {
            1: {"torn": {"areas": [{"prob": 2, "polys": _ellipse(-76.6, 36.8, 1.0, 0.6, 0.7)}], "sig": []},
                "wind": {"areas": [{"prob": 5, "polys": _ellipse(-76.9, 36.9, 2.0, 1.3, 0.6)},
                                   {"prob": 15, "polys": _ellipse(-76.5, 36.8, 1.1, 0.65, 0.7)}], "sig": []},
                "hail": {"areas": [{"prob": 5, "polys": _ellipse(-76.7, 36.8, 1.4, 0.9, 0.6)}], "sig": []}},
            2: {"torn": {"areas": [], "sig": []},
                "wind": {"areas": [{"prob": 5, "polys": _ellipse(-76.3, 35.6, 1.3, 0.6, 0.3)}], "sig": []},
                "hail": {"areas": [], "sig": []}},
            3: {"any": {"areas": [], "sig": []}},
        },
        "ero": {
            1: [ero("MRGL", _ellipse(-76.9, 36.9, 1.8, 1.1, 0.5, wobble=0.06)),
                ero("SLGT", _ellipse(-76.4, 36.85, 0.7, 0.45, 0.5, wobble=0.08))],
            2: [ero("MRGL", _ellipse(-75.9, 35.9, 1.0, 0.7, 0.2, wobble=0.06))],
            3: [],
        },
        "qpf_maps": {per: {"period": per, "features": [
            {"value": v, "polys": f["polys"], "times": {}} for f in _qpf_sample() for v in [round(f["value"] * k * 4) / 4]
            if v >= 0.25]} for per, k in (("1-2", 0.3), ("1-3", 0.45), ("1-5", 0.75), ("1-7", 1.0))},
        "qpf": {"period": "1-7", "features": [
            {"value": v, "polys": _ellipse(-77.2 + 0.2 * i, 36.4 + 0.02 * i, 5.4 - 0.7 * i, 2.8 - 0.35 * i, 0.45,
                                           wobble=0.05 + 0.01 * i), "times": {}}
            for i, v in enumerate([0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0])]},
        "errors": [],
    }
