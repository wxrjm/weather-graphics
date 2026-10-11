"""Nadocast machine-learning tornado probabilities (Brian Hempel, github.com/brianhempel/nadocast).

Data: the published day-1 GRIB2 files on data.nadocast.com (free, no key):
  http://data.nadocast.com/YYYYMM/YYYYMMDD/tHHz/nadocast_<model>_models_conus_tornado[_abs_calib]_YYYYMMDD_tHHz_fAA-BB.grib2
  (+ the matching sig_tornado file).  <model> is "2022" and, on newer runs, "2024_preliminary".
Blend: Nadocast doesn't publish a blended product, so "blended" here = the average of every model version published
for the latest run (same calibration). If only one version exists, that one is used and the graphic says so.
Calibration: "spc" (the regular, SPC-style probabilities) by default; config "nadocast_calibration": "abs" for the
absolutely calibrated files. Probabilities are the chance of a tornado within 25 miles of a point, 12Z-12Z.
Decoding needs ecCodes + numpy (same as the NDFD snow/wind maps).
"""
import math
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import fullscreen, outlookmap
from .alertmap import _paste_rounded
from .theme import C, Canvas, z

BASE = "http://data.nadocast.com"
DATA_BOX = (-125.0, -66.0, 24.0, 50.0)  # w, e, s, n: CONUS
TOR_BINS = [(2, (0, 139, 0)), (5, (139, 71, 38)), (10, (255, 200, 0)), (15, (255, 0, 0)),
            (30, (255, 0, 255)), (45, (145, 44, 238)), (60, (16, 78, 139))]  # SPC tornado colors
CREDIT = "NADOCAST MODEL  ·  nadocast.com"  # the small "data from" strip at the bottom of every Nadocast graphic
SIG_LEVEL = 10  # % sig-tornado chance that gets hatched (SPC convention)
FILE_RE = re.compile(r"nadocast_(?:(?P<model>[0-9a-z_]+?)_models_)?conus_(?P<ev>sig_tornado|tornado)(?P<abs>_abs_calib)?"
                     r"_(?P<ymd>\d{8})_t(?P<hh>\d{2})z_f(?P<a>\d{2})-(?P<b>\d{2})\.grib2")
NEAR = [  # (name, state, lat, lon) for "near ..." wording
    ("Norfolk", "VA", 36.85, -76.29), ("Virginia Beach", "VA", 36.85, -75.98), ("Richmond", "VA", 37.54, -77.44),
    ("Roanoke", "VA", 37.27, -79.94), ("Lynchburg", "VA", 37.41, -79.14), ("Charlottesville", "VA", 38.03, -78.48),
    ("Fredericksburg", "VA", 38.30, -77.46), ("Danville", "VA", 36.59, -79.40), ("Emporia", "VA", 36.69, -77.54),
    ("Williamsburg", "VA", 37.27, -76.71), ("Suffolk", "VA", 36.73, -76.58), ("Franklin", "VA", 36.68, -76.92),
    ("Eastern Shore", "VA", 37.55, -75.82), ("Blacksburg", "VA", 37.23, -80.41), ("Winchester", "VA", 39.18, -78.16),
    ("Elizabeth City", "NC", 36.30, -76.22), ("Ahoskie", "NC", 36.29, -76.98), ("Greenville", "NC", 35.61, -77.37),
    ("Rocky Mount", "NC", 35.94, -77.79), ("Raleigh", "NC", 35.78, -78.64), ("Durham", "NC", 35.99, -78.90),
    ("Greensboro", "NC", 36.07, -79.79), ("Charlotte", "NC", 35.23, -80.84), ("Fayetteville", "NC", 35.05, -78.88),
    ("Wilmington", "NC", 34.23, -77.94), ("New Bern", "NC", 35.11, -77.04), ("Nags Head", "NC", 35.96, -75.62),
    ("Asheville", "NC", 35.60, -82.55), ("Salisbury", "MD", 38.36, -75.60), ("Washington", "DC", 38.90, -77.04),
    ("Baltimore", "MD", 39.29, -76.61), ("Dover", "DE", 39.16, -75.52), ("Philadelphia", "PA", 39.95, -75.17),
    ("Pittsburgh", "PA", 40.44, -80.00), ("New York", "NY", 40.71, -74.01), ("Buffalo", "NY", 42.89, -78.88),
    ("Boston", "MA", 42.36, -71.06), ("Charleston", "WV", 38.35, -81.63), ("Columbia", "SC", 34.00, -81.03),
    ("Charleston", "SC", 32.78, -79.93), ("Myrtle Beach", "SC", 33.69, -78.89), ("Atlanta", "GA", 33.75, -84.39),
    ("Savannah", "GA", 32.08, -81.09), ("Macon", "GA", 32.84, -83.63), ("Jacksonville", "FL", 30.33, -81.66),
    ("Tallahassee", "FL", 30.44, -84.28), ("Tampa", "FL", 27.95, -82.46), ("Orlando", "FL", 28.54, -81.38),
    ("Miami", "FL", 25.76, -80.19), ("Birmingham", "AL", 33.52, -86.80), ("Huntsville", "AL", 34.73, -86.59),
    ("Montgomery", "AL", 32.38, -86.30), ("Mobile", "AL", 30.69, -88.04), ("Jackson", "MS", 32.30, -90.18),
    ("Tupelo", "MS", 34.26, -88.70), ("Memphis", "TN", 35.15, -90.05), ("Nashville", "TN", 36.16, -86.78),
    ("Knoxville", "TN", 35.96, -83.92), ("Chattanooga", "TN", 35.05, -85.31), ("Louisville", "KY", 38.25, -85.76),
    ("Lexington", "KY", 38.04, -84.50), ("Paducah", "KY", 37.08, -88.60), ("Cincinnati", "OH", 39.10, -84.51),
    ("Columbus", "OH", 39.96, -83.00), ("Cleveland", "OH", 41.50, -81.69), ("Indianapolis", "IN", 39.77, -86.16),
    ("Evansville", "IN", 37.97, -87.57), ("Chicago", "IL", 41.88, -87.63), ("Springfield", "IL", 39.80, -89.64),
    ("St. Louis", "MO", 38.63, -90.20), ("Kansas City", "MO", 39.10, -94.58), ("Springfield", "MO", 37.21, -93.29),
    ("Detroit", "MI", 42.33, -83.05), ("Milwaukee", "WI", 43.04, -87.91), ("Minneapolis", "MN", 44.98, -93.27),
    ("Des Moines", "IA", 41.59, -93.62), ("Omaha", "NE", 41.26, -95.93), ("Little Rock", "AR", 34.75, -92.29),
    ("Shreveport", "LA", 32.53, -93.75), ("New Orleans", "LA", 29.95, -90.07), ("Lafayette", "LA", 30.22, -92.02),
    ("Houston", "TX", 29.76, -95.37), ("Dallas", "TX", 32.78, -96.80), ("Oklahoma City", "OK", 35.47, -97.52),
    ("Tulsa", "OK", 36.15, -95.99), ("Wichita", "KS", 37.69, -97.34), ("Amarillo", "TX", 35.22, -101.83),
    ("Lubbock", "TX", 33.58, -101.86), ("San Antonio", "TX", 29.42, -98.49), ("Denver", "CO", 39.74, -104.99),
]


# ------------------------------------------------------------------ fetch
def _get(url, ua, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _listing(url, ua):
    try:
        return _get(url, ua, 30).decode("utf-8", "replace")
    except Exception:
        return ""


def _runs(cfg, now_utc, debug=False):
    """-> [(run_dt_utc, [file names])] newest first, from the data.nadocast.com folder listings."""
    base, ua = cfg.get("nadocast_url", BASE).rstrip("/"), cfg["user_agent"]
    out = []
    for back in (0, 1):
        d = (now_utc - timedelta(days=back)).date()
        day_url = f"{base}/{d:%Y%m}/{d:%Y%m%d}/"
        html = _listing(day_url, ua)
        hours = sorted({int(h) for h in re.findall(r'href="t(\d{1,2})z/?"', html)}, reverse=True)
        if debug:
            print(f"   [nadocast] {day_url}: runs {hours or 'none listed'}")
        for hh in hours:
            names = sorted(set(m.group(0) for m in FILE_RE.finditer(_listing(f"{day_url}t{hh}z/", ua))))
            if names:
                out.append((datetime(d.year, d.month, d.day, hh, tzinfo=timezone.utc), f"{day_url}t{hh}z/", names))
    return out


def _decode(path):
    """GRIB2 -> {lat, lon, val (percent)} cropped to CONUS."""
    import numpy as np
    from .ndfdmap import _messages
    for _, lat, lon, val in _messages(path, DATA_BOX):
        v = np.array(val, dtype=float)
        if np.nanmax(v) <= 1.0001:  # stored as 0-1
            v = v * 100.0
        return {"lat": lat, "lon": lon, "val": v}
    raise RuntimeError("no GRIB messages")


def fetch(cfg, cache_dir, now_utc, debug=False):
    out = {"errors": []}
    try:
        import eccodes  # noqa: F401
        import numpy as np
    except Exception:
        out["errors"].append("Nadocast map needs ecCodes + numpy:  pip install eccodes numpy")
        print("  ! " + out["errors"][-1])
        return out
    want_abs = (cfg.get("nadocast_calibration") or "spc").lower().startswith("abs")
    cache = Path(cache_dir) / "nadocast"
    cache.mkdir(parents=True, exist_ok=True)
    try:
        runs = _runs(cfg, now_utc, debug)
    except Exception as e:
        runs = []
        out["errors"].append(f"Nadocast listing: {e!r}")
    for run_dt, url, names in runs:
        files = [FILE_RE.match(n).groupdict() | {"name": n} for n in names]
        day1 = [f for f in files if int(f["a"]) <= 12]  # day-1 period (Day 2 files start later)
        if not day1:
            continue
        a, b = min(int(f["a"]) for f in day1), None
        day1 = [f for f in day1 if int(f["a"]) == a]
        b = max(int(f["b"]) for f in day1)
        day1 = [f for f in day1 if int(f["b"]) == b]
        picked = {}
        for ev in ("tornado", "sig_tornado"):
            by_model = {}
            for f in (f for f in day1 if f["ev"] == ev):
                by_model.setdefault(f["model"] or "2021", []).append(f)
            chosen = []
            for model, fs in sorted(by_model.items()):
                pref = [f for f in fs if bool(f["abs"]) == want_abs] or fs  # preferred calibration, else the other
                chosen.append(pref[0])
            picked[ev] = chosen
        if not picked.get("tornado"):
            continue
        fields = {}
        try:
            for ev, fs in picked.items():
                grids = []
                for f in fs:
                    p = cache / f["name"]
                    if not p.exists():
                        p.write_bytes(_get(url + f["name"], cfg["user_agent"], 120))
                    grids.append(_decode(p))
                if grids:
                    stack = np.stack([g["val"] for g in grids if g["val"].shape == grids[0]["val"].shape])
                    fields[ev] = {"lat": grids[0]["lat"], "lon": grids[0]["lon"], "val": np.nanmean(stack, axis=0)}
        except Exception as e:
            out["errors"].append(f"Nadocast {url}: {e!r}")
            if debug:
                print(f"   [nadocast] {url} failed: {e!r}")
            continue
        models = [f["model"] or "2021" for f in picked["tornado"]]
        out.update({"tor": fields.get("tornado"), "sig": fields.get("sig_tornado"), "run": run_dt,
                    "start": run_dt + timedelta(hours=a), "end": run_dt + timedelta(hours=b + 1), "models": models,
                    "blended": len(models) > 1, "calibration": "absolutely calibrated" if want_abs else "SPC-calibrated"})
        if debug:
            print(f"   [nadocast] using {run_dt:%Y-%m-%d %HZ} f{a:02d}-{b:02d}, models {models}, "
                  f"peak {np.nanmax(out['tor']['val']):.0f}%")
        return out
    out["errors"].append("no Nadocast day-1 tornado forecast found on data.nadocast.com")
    print("  ! Nadocast: " + out["errors"][-1])
    return out


def sample(now_utc):
    """Synthetic Nadocast-like grid: a Carolinas/southeast VA tornado setup with a sig-tor core."""
    import numpy as np
    lat = np.linspace(24, 50, 175)[:, None] * np.ones((1, 400))
    lon = np.ones((175, 1)) * np.linspace(-125, -66, 400)[None, :]
    blob = lambda cx, cy, sx, sy: np.exp(-(((lon - cx) / sx) ** 2 + ((lat - cy) / sy) ** 2))
    tor = 17 * blob(-78.0, 35.9, 1.6, 0.9) + 6 * blob(-76.6, 36.8, 0.8, 0.5) + 4 * blob(-88.5, 33.5, 2.5, 1.5) \
        + 1.2 * np.sin(lon / 1.7) * np.cos(lat / 1.3) - 1
    sig = np.clip(18 * blob(-78.0, 35.85, 1.0, 0.55) - 2, 0, None)
    run = now_utc.replace(hour=12, minute=0, second=0, microsecond=0)
    mk = lambda v: {"lat": lat, "lon": lon, "val": np.clip(v, 0, None)}
    return {"tor": mk(tor), "sig": mk(sig), "run": run, "start": run + timedelta(hours=2), "end": run + timedelta(hours=24),
            "models": ["2022", "2024_preliminary"], "blended": True, "calibration": "SPC-calibrated", "errors": [],
            "sample": True}


# ------------------------------------------------------------------ helpers
def _miles(la1, lo1, la2, lo2):
    p = math.pi / 180
    a = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(a))


def _bearing(la1, lo1, la2, lo2):
    p = math.pi / 180
    y = math.sin((lo2 - lo1) * p) * math.cos(la2 * p)
    x = math.cos(la1 * p) * math.sin(la2 * p) - math.sin(la1 * p) * math.cos(la2 * p) * math.cos((lo2 - lo1) * p)
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int(deg / 45 + 0.5) % 8]


def near_text(la, lo):
    name, st, cla, clo = min(NEAR, key=lambda c: _miles(la, lo, c[2], c[3]))
    d = _miles(cla, clo, la, lo)
    if d < 20:
        return f"near {name}, {st}"
    return f"{round(d / 5) * 5:.0f} mi {_bearing(cla, clo, la, lo)} of {name}, {st}"


def _value_at(field, lon, lat):
    import numpy as np
    d = (field["lat"] - lat) ** 2 + ((field["lon"] - lon) * np.cos(np.radians(lat))) ** 2
    j, i = np.unravel_index(np.nanargmin(d), d.shape)
    v = field["val"][j, i]
    return None if v != v else float(v)


def _peak(field, view):
    """-> (value, lat, lon) of the highest probability inside view (w, e, s, n)."""
    import numpy as np
    w, e, s, n = view
    m = (field["lon"] >= w) & (field["lon"] <= e) & (field["lat"] >= s) & (field["lat"] <= n)
    v = np.where(m, field["val"], np.nan)
    if not np.isfinite(v).any():
        return 0.0, None, None
    j, i = np.unravel_index(np.nanargmax(v), v.shape)
    return float(v[j, i]), float(field["lat"][j, i]), float(field["lon"][j, i])


def _bin(v):
    col = None
    for t, c in TOR_BINS:
        if (v or 0) + 1e-9 >= t:
            col = c
    return col


def _pct(v):
    """Display a probability the way SPC does: the bracket it reaches (2, 5, 10...), '<2' below."""
    if v is None or v < 2:
        return "<2%"
    return f"{max(t for t, _ in TOR_BINS if v + 1e-9 >= t)}%"


def _spread_cities(tor, view, taken, n=3, gap_mi=50):
    """Value boxes for the big-text map: the highest-chance cities that aren't crowding the peak / Norfolk boxes."""
    w, e, s, nn = view
    out, spots = [], [t for t in taken if t[0] is not None]
    cand = sorted((c for c in NEAR if w <= c[3] <= e and s <= c[2] <= nn), key=lambda c: -(_value_at(tor, c[3], c[2]) or 0))
    for name, st, la, lo in cand:
        v = _value_at(tor, lo, la)
        if (v or 0) < 2 or len(out) >= n:
            break
        if all(_miles(la, lo, a, b) > gap_mi for a, b in spots):
            out.append((f"{name}", _bin(v), _pct(v), (la, lo)))
            spots.append((la, lo))
    return out


def _painter(tor, sig):
    from .ndfdmap import _cell_painter
    base_paint = _cell_painter(tor, TOR_BINS)

    def paint(d, proj):
        base_paint(d, proj)
        if sig is None:
            return
        from PIL import Image, ImageChops, ImageDraw
        img = d._image
        mask_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
        _cell_painter(sig, [(SIG_LEVEL, (0, 0, 0))])(ImageDraw.Draw(mask_img), proj)
        mask = mask_img.getchannel("A")
        if not mask.getbbox():
            return
        hatch = Image.new("L", img.size, 0)
        hd = ImageDraw.Draw(hatch)
        step, W_, H_ = z(13), img.size[0], img.size[1]
        for k in range(-H_, W_, step):  # SPC-style black diagonal hatching for significant (EF2+) tornadoes
            hd.line([(k, H_), (k + H_, 0)], fill=255, width=max(3, z(3.2)))
        a = ImageChops.multiply(hatch, mask)
        layer = Image.new("RGBA", img.size, (8, 10, 18, 0))
        layer.putalpha(a.point(lambda v: int(v * 0.95)))
        img.alpha_composite(layer)
    return paint


def _legend(cv, x, y, maxw, has_sig):
    items = [(c, f"{t}%") for t, c in TOR_BINS]
    outlookmap._legend_chips(cv, x, y, items, maxw - (210 if has_sig else 0))
    if has_sig:
        widths = sum(cv.width(f"{t}%", 19, "bold") + 46 for t, _ in TOR_BINS) + 8 * (len(TOR_BINS) - 1) + 20
        sx = x + min(widths, maxw - 210) + 10
        cv.rect(sx, y, 200, 44, (13, 21, 38, 225), r=10)
        bx, by = sx + 10, y + 11
        cv.rect(bx, by, 22, 22, (90, 100, 120, 255), r=4)
        for k in range(0, 44, 7):
            x0, x1 = max(0, k - 22), min(22, k)
            if x1 > x0:
                cv.line([(bx + x0, by + 22 - (k - x0)), (bx + x1, by + 22 - (k - x1))], (12, 16, 26, 255), 2)
        cv.text(bx + 30, y + 22, "SIG (EF2+)", 19, "bold", anchor="lm")


# ------------------------------------------------------------------ graphics
def _graphic(nd, key, view, area_txt, cities, pkg, cfg, tz):
    tor, sig = nd["tor"], nd.get("sig")
    pk, pla, plo = _peak(tor, view)
    loc = cfg["location"]
    home = _value_at(tor, loc["lon"], loc["lat"])
    start, end = nd["start"].astimezone(tz), nd["end"].astimezone(tz)
    when = f"{start.strftime('%a').upper()} {start.strftime('%I %p').lstrip('0')} – {end.strftime('%a').upper()} {end.strftime('%I %p').lstrip('0')}"
    blend = "BLENDED " if nd.get("blended") else ""
    title = "TORNADO PROBABILITIES"
    subtitle = f"{area_txt}  ·  {when}  ·  {blend}NADOCAST AI"
    where = near_text(pla, plo) if pla is not None else ""
    head_col = _bin(pk) or (70, 86, 112)
    head = f"PEAK {_pct(pk)}" + (f"  ·  {where.upper()}" if pk >= 2 and where else "")
    sig_pk = _peak(sig, view)[0] if sig is not None else 0
    meaning = (f"Peak chance of a tornado within 25 miles: {_pct(pk)}, {where}." if pk >= 2 else
               "Tornado chances stay below 2% across this area.")
    if sig_pk >= SIG_LEVEL:
        meaning += " Hatched areas could see a strong (EF2+) tornado."
    meaning += f" Norfolk: {_pct(home)}."
    # rows: local points for the state map, the highest-chance cities for the wide map
    if key == "local":
        pts = [(n, la, lo) for n, la, lo, *_ in (cfg.get("nadocast_points") or outlookmap.DMA_POINTS[:8]
                                                  + [("Richmond", 37.54, -77.44), ("Raleigh", 35.78, -78.64)])]
    else:
        w, e, s, n = view
        cand = [(f"{c[0]}, {c[1]}", c[2], c[3]) for c in NEAR if w <= c[3] <= e and s <= c[2] <= n]
        cand.sort(key=lambda c: -(_value_at(tor, c[2], c[1]) or 0))
        pts = cand[:10]
    rows = []
    for name, la, lo in pts:
        v = _value_at(tor, lo, la)
        rows.append((name, _bin(v), _pct(v)))
    cv = Canvas(cfg)
    cv.header(title, subtitle)
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    paint = _painter(tor, sig)
    lines = key == "local"  # county lines only on the state map
    lay = outlookmap.draw_map([], mw, mh, cfg, outline=False, painter=paint, view=view, cities=cities, water_alpha=0.0,
                              county_lines=lines)
    _paste_rounded(cv, lay, mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    has_sig = sig_pk >= SIG_LEVEL
    _legend(cv, mx + 16, my + mh - 60, mw - 32, has_sig)
    outlookmap._side(cv, px, py, pw_, ph_, head_col, "PEAK TORNADO CHANCE", head, meaning, rows,
                     "LOCAL CHANCES" if key == "local" else "HIGHEST CHANCES")
    models = " + ".join(m.replace("_preliminary", " prelim") for m in nd.get("models", []))
    src = ("SAMPLE DATA" if nd.get("sample") else "Nadocast") + \
        f" · {models} models{' blended' if nd.get('blended') else ''}"
    cv.footer(pkg, source=src, show_source=not cv.tall)  # tall sizes: the strip below names the source
    fullscreen.credit(cv, CREDIT)
    fullscreen.attach(cv, title=title, subtitle=subtitle,
                      map_fn=lambda pw, ph, v: outlookmap.draw_map([], pw, ph, cfg, outline=False, painter=paint, view=v,
                                                                   cities=cities, water_alpha=0.0, county_lines=lines),
                      box=tuple(view), head_label="PEAK TORNADO CHANCE", head_value=head, head_col=head_col,
                      meaning=meaning, rows=rows, overlay=lambda c, x, y, w_: _legend(c, x, y, w_, has_sig), source=src,
                      callout_rows=([("PEAK", head_col, _pct(pk), (pla, plo))] if pk >= 2 and pla is not None else [])
                      + [("Norfolk", _bin(home), _pct(home), (loc["lat"], loc["lon"]))]
                      + _spread_cities(tor, view, [(pla, plo), (loc["lat"], loc["lon"])]),
                      big_caption=when, credit_text=CREDIT, big_tagline=(f"PEAK {_pct(pk)} {where}".upper() if pk >= 2 else "TORNADO CHANCES BELOW 2%"))
    return cv, pk


def nadocast_graphics(pkg, cfg):
    nd = pkg.get("_nadocast") or {}
    if not nd.get("tor"):
        return None
    tz = ZoneInfo(cfg["timezone"])
    from .cpcmap import EAST_CITIES, EAST_VIEW
    views = [("local", tuple(cfg.get("nadocast_local_view") or outlookmap.STATE_VIEW), "VIRGINIA & NORTH CAROLINA",
              outlookmap.STATE_CITIES),
             ("east", tuple(cfg.get("nadocast_east_view") or EAST_VIEW), "EASTERN U.S.", EAST_CITIES)]
    need = cfg.get("nadocast_min", 2)
    out = []
    for key, view, txt, cities in views:
        pk = _peak(nd["tor"], view)[0]
        if pk < need and not cfg.get("nadocast_always"):
            print(f"  - nadocast_{key}: peak {pk:.0f}% in view (< {need}%), skipped")
            continue
        cv, _ = _graphic(nd, key, view, txt, cities, pkg, cfg, tz)
        out.append((f"nadocast_{key}", cv))
    return out or None
