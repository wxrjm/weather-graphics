"""Recorded lows and highs so far today from hourly ASOS observations (api.weather.gov, no key).

Four graphics in the Temperature folder (a map and a separate table for each):
  asos_low_map / asos_low_table     the coldest reading each station has reported since midnight, and when
  asos_high_map / asos_high_table   the warmest reading so far, and when

When they are made ("auto"): the reference station (KORF) decides.
  low   once its coldest reading is behind it (it is rising, 2+ hours after the low), or from 10 AM on
  high  once its warmest reading is behind it (cooling, 1+ hour after the peak) after 1 PM, or from 5 PM on
Config: asos_temps_mode "auto" | "both" | "low" | "high", asos_stations [[id, name, lat, lon], ...], asos_label_scale (default 0.8).
"""
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import ndfdmap, statemaps
from .nws import NWSClient
from .theme import C, Canvas, z

STATIONS = [  # id, name, lat, lon (the live feed's own coordinates replace these)
    ("KORF", "Norfolk Int'l", 36.894, -76.201), ("KNGU", "Norfolk NAS", 36.938, -76.289), ("KPHF", "Newport News", 37.132, -76.493),
    ("KLFI", "Langley AFB", 37.083, -76.360), ("KFAF", "Fort Eustis", 37.133, -76.608), ("KCPK", "Chesapeake", 36.666, -76.320),
    ("KPVG", "Hampton Roads Exec", 36.780, -76.449), ("KFKN", "Franklin", 36.698, -76.903), ("KJGG", "Williamsburg", 37.239, -76.716),
    ("KFYJ", "West Point", 37.52, -76.78), ("KRIC", "Richmond", 37.505, -77.320), ("KPTB", "Petersburg", 37.184, -77.508),
    ("KOFP", "Ashland", 37.709, -77.436), ("KEMV", "Emporia", 36.687, -77.483), ("KLVL", "Lawrenceville", 36.773, -77.795),
    ("KAVC", "South Hill", 36.689, -78.045), ("KWAL", "Wallops", 37.940, -75.466), ("KMFV", "Melfa", 37.647, -75.761),
    ("KECG", "Elizabeth City", 36.261, -76.175), ("KEDE", "Edenton", 36.028, -76.567), ("KASJ", "Ahoskie", 36.299, -77.171),
    ("KIXA", "Halifax", 36.329, -77.636), ("KMQI", "Manteo", 35.919, -75.696), ("KFFA", "Kill Devil Hills", 36.001, -75.671),
    ("KHSE", "Hatteras", 35.233, -75.617), ("KOCW", "Washington NC", 35.570, -77.050),
]
REF = "KORF"
VIEW = (-78.3, -74.7, 35.0, 38.2)


def _tz(cfg):
    return ZoneInfo(cfg["timezone"])


def _stations(cfg):
    return [tuple(s) for s in (cfg.get("asos_stations") or STATIONS)]


def _f(c):
    return c * 9 / 5 + 32


def _summarise(sid, name, lat, lon, series):
    """series: [(datetime, deg F)] -> one station record, or None."""
    if not series:
        return None
    series = sorted(series)
    lo = min(series, key=lambda r: (r[1], r[0]))
    hi = max(series, key=lambda r: (r[1], r[0]))
    return {"id": sid, "name": name, "lat": lat, "lon": lon, "lo": round(lo[1]), "lo_t": lo[0], "hi": round(hi[1]), "hi_t": hi[0],
            "now": round(series[-1][1]), "now_t": series[-1][0]}


def _fetch_one(client, tz, start_utc, st):
    sid, name, lat, lon = st
    try:
        d = client.get(f"/stations/{sid}/observations?start={start_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}&limit=200", retries=2)
    except Exception:
        return None
    series = []
    for f in d.get("features", []):
        p = f.get("properties", {})
        v = (p.get("temperature") or {}).get("value")
        if v is None or not p.get("timestamp"):
            continue
        series.append((datetime.fromisoformat(p["timestamp"].replace("Z", "+00:00")).astimezone(tz), _f(v)))
    if d.get("features"):
        co = (d["features"][0].get("geometry") or {}).get("coordinates")
        if co:
            lon, lat = co[0], co[1]
    return _summarise(sid, name, lat, lon, series)


def _due(rows, now, cfg):
    mode = cfg.get("asos_temps_mode", "auto")
    if mode in ("both", "low", "high"):
        return {"low": mode in ("both", "low"), "high": mode in ("both", "high")}
    ref = next((r for r in rows if r["id"] == REF), rows[0] if rows else None)
    if not ref:
        return {"low": False, "high": False}
    h = now.hour + now.minute / 60
    since_lo = (now - ref["lo_t"]).total_seconds() / 3600
    since_hi = (now - ref["hi_t"]).total_seconds() / 3600
    low = h >= 5 and ((ref["now"] > ref["lo"] and since_lo >= 2) or h >= 10)
    high = (h >= 13 and ref["now"] < ref["hi"] and since_hi >= 1) or h >= 17
    return {"low": low, "high": high}


def fetch(cfg, cache_dir, now_utc, debug=False):
    tz = _tz(cfg)
    now = now_utc.astimezone(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    client = NWSClient(cfg["user_agent"], cache_dir)
    with ThreadPoolExecutor(8) as ex:
        rows = [r for r in ex.map(lambda s: _fetch_one(client, tz, start, s), _stations(cfg)) if r]
    if not rows:
        print("  ! ASOS observations unavailable")
        return None
    print(f"  ASOS: {len(rows)} stations reporting")
    return {"rows": rows, "now": now, "due": _due(rows, now, cfg)}


def sample(now_utc, tz, cfg):
    import random
    rnd = random.Random(11)
    now = now_utc.astimezone(tz).replace(hour=17, minute=10)  # late enough that both the low and the high are "in"
    mid = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = []
    for sid, name, lat, lon in _stations(cfg):
        base = 47 - (lat - 36.9) * 2.2 - max(0, -75.9 - lon) * 0 + (lon + 76.3) * -0.9 + rnd.uniform(-1.5, 1.5)
        if lon > -75.9 or lat < 35.6:
            base += 5
        series = []
        for k in range(0, 18):
            t = mid + timedelta(hours=k, minutes=53)
            v = base + 14 * max(0.0, math.sin((k - 6) / 12 * math.pi)) + rnd.uniform(-0.8, 0.8)
            series.append((t, v))
        rows.append(_summarise(sid, name, lat, lon, series))
    return {"rows": rows, "now": now, "due": {"low": True, "high": True}}


# ------------------------------------------------------------------ graphics
def _tlabel(t):
    return t.strftime("%I:%M %p").lstrip("0")


def _ctx(ad, kind):
    key, tkey = ("lo", "lo_t") if kind == "low" else ("hi", "hi_t")
    rows = sorted(ad["rows"], key=lambda r: (r[key], r[tkey]) if kind == "low" else (-r[key], r[tkey]))
    word = "LOW" if kind == "low" else "HIGH"
    now = ad["now"]
    sub = f"HOURLY ASOS READINGS  ·  {now.strftime('%a %b').upper()} {now.day}  ·  AS OF {_tlabel(now)}"
    return key, tkey, rows, word, sub


def map_graphic(ad, kind, pkg, cfg):
    import numpy as np
    from .newgfx import HR_VIEW, _clean_map, _header_clean, _src, _temp_bar
    key, tkey, rows, word, sub = _ctx(ad, kind)
    vals = [r[key] for r in rows]
    lo_, hi_ = 5 * math.floor(min(vals) / 5), 5 * math.ceil(max(vals) / 5)
    hi_ = max(hi_, lo_ + 10)
    bins = [(t, statemaps.temp_color(t + 1)) for t in range(lo_ - 10, hi_ + 11, 1)]
    bins[0] = (-999, bins[0][1])
    view = tuple(cfg.get("asos_view") or VIEW)
    la = np.arange(34.5, 38.9, 0.05)
    lo = np.arange(-80.0, -74.0, 0.05)
    LO, LA = np.meshgrid(lo, la)
    num = np.zeros(LA.shape)
    den = np.zeros(LA.shape)
    for r in rows:  # inverse-distance weighting between the stations, so the colour field reads as a smooth analysis
        d2 = ((LO - r["lon"]) * 0.8) ** 2 + (LA - r["lat"]) ** 2 + 0.002
        w = 1 / d2 ** 1.5
        num += w * r[key]
        den += w
    field = {"lat": LA, "lon": LO, "val": num / den}
    paint = ndfdmap._cell_painter(field, bins, alpha=255, smooth=1)
    cv = _header_clean(cfg, f"RECORDED {word}S SO FAR TODAY", sub)
    first = ["KORF", "KRIC", "KPHF", "KECG", "KWAL", "KMQI", "KHSE", "KJGG", "KFKN", "KEDE", "KOCW"]  # labels win in this order when towns crowd
    pri = sorted(rows, key=lambda r: first.index(r["id"]) if r["id"] in first else 99)
    cities = [(r["name"], r["lat"], r["lon"], 1 if i < 12 else 2, f"{r[key]}°") for i, r in enumerate(pri)]
    rh = cv.H - 196 - (170 if cv.W < 1500 else 140)
    rw = cv.W - 2 * cv.M if cv.W < 1500 else min(cv.W - 2 * cv.M, int(rh * 1.5))  # wide: a map-shaped box in the middle, not a stretched one
    region = ((cv.W - rw) / 2, 196, rw, rh)
    _clean_map(cv, cfg, paint, cities, view=view, tags=False, region=region, label_scale=cfg.get("asos_label_scale", 0.8))
    _temp_bar(cv, lo_, hi_, f"{word} TEMPERATURE (°F)")
    cv.footer(pkg, source=_src(pkg, "NWS ASOS OBSERVATIONS"))
    return cv


def table_graphic(ad, kind, pkg, cfg):
    from .newgfx import _header_clean, _src
    key, tkey, rows, word, sub = _ctx(ad, kind)
    cv = _header_clean(cfg, f"{word}S SO FAR TODAY", sub)
    n = len(rows)
    ncol = 2
    per = -(-n // ncol)
    top = 200
    bottom = cv.H - 100
    gap = 14
    cw = (cv.W - 2 * cv.M - gap) / ncol
    hd = 30
    rh = min(70, (bottom - top - hd) / per)
    for c in range(ncol):
        x = cv.M + c * (cw + gap)
        cv.text(x + 14, top + hd / 2, "STATION", 15, "bold", C["muted"], anchor="lm")
        cv.text(x + cw - 150, top + hd / 2, f"{word}", 15, "bold", C["muted"], anchor="mm")
        cv.text(x + cw - 16, top + hd / 2, "TIME", 15, "bold", C["muted"], anchor="rm")
    for i, r in enumerate(rows):
        c, k = divmod(i, per)
        x = cv.M + c * (cw + gap)
        y = top + hd + k * rh
        cv.rect(x, y, cw, rh - 6, (20, 31, 54, 235), r=10)
        mid = y + (rh - 6) / 2
        cv.text(x + 14, mid - 8, r["name"].upper(), 17, "bold", anchor="lm", maxw=cw - 290)
        cv.text(x + 14, mid + 12, r["id"], 13, "medium", C["muted"], anchor="lm")
        col = statemaps.temp_color(r[key])
        cv.rect(x + cw - 190, y + 6, 80, rh - 18, (*col, 255), r=8)
        lum = 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2]
        cv.text(x + cw - 150, mid, f"{r[key]}°", 26, "bold", (20, 28, 46) if lum > 140 else (255, 255, 255), anchor="mm")
        cv.text(x + cw - 16, mid, _tlabel(r[tkey]), 18, "medium", anchor="rm")
    cv.footer(pkg, source=_src(pkg, "NWS ASOS OBSERVATIONS"))
    return cv


def asos_graphics(pkg, cfg):
    ad = pkg.get("_asos")
    if not ad or not ad.get("rows"):
        return None
    out = []
    for kind in ("low", "high"):
        if ad["due"].get(kind):
            out.append((f"asos_{kind}_map", map_graphic(ad, kind, pkg, cfg)))
            out.append((f"asos_{kind}_table", table_graphic(ad, kind, pkg, cfg)))
    return out or None
