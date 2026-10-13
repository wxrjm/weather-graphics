"""Temperature crash: the biggest drop from a warm daytime HIGH to the coldest LOW that follows it.

For every NDFD grid cell we find the day whose high is followed (within `tempdrop_span` days, default 4) by the
deepest low and keep that pair, so the map shows the size of the crash (high - low) and each city callout reads
"85° -> 34°" with the days it happens.  Two graphics, all sizes:
  temp_drop_midatlantic  Mid-Atlantic map (VA, NC, WV, MD, DE, PA, NJ)
  temp_drop_hamptonroads Hampton Roads close-up
Data: NDFD MaxT + MinT GRIB2 (tgftp.nws.noaa.gov, no key; needs eccodes + numpy).
Only made when the biggest city drop reaches `tempdrop_min` (default 20; Hampton Roads uses `tempdrop_min_local`,
default 15).  `"tempdrop_always": true` forces it.
"""
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from . import fullscreen, outlookmap
from .theme import C, Canvas, z

MIDATL_VIEW = (-83.6, -73.6, 34.9, 40.9)
LOCAL_VIEW = (-77.9, -75.0, 35.85, 37.95)
ORANGE, ICE = C["sun"], C["rain"]  # warm high = brand gold, cold low = brand sky blue
STOPS = [(0.0, (206, 230, 248)), (0.3, (98, 176, 255)), (0.62, (52, 112, 220)), (0.85, (60, 70, 205)),
         (1.0, (104, 76, 214))]  # small drop = pale ice -> brand blues -> indigo for the biggest crashes

MIDATL_CITIES = [  # (label, lat, lon)
    ("Norfolk", 36.90, -76.20), ("Richmond", 37.54, -77.44), ("Washington", 38.90, -77.04),
    ("Baltimore", 39.29, -76.61), ("Philadelphia", 39.95, -75.17), ("Raleigh", 35.78, -78.64),
    ("Greensboro", 36.07, -79.79), ("Roanoke", 37.27, -79.94), ("Charleston", 38.35, -81.63),
    ("Salisbury", 38.36, -75.60), ("Harrisburg", 40.27, -76.88), ("Charlottesville", 38.03, -78.48),
    ("Winchester", 39.18, -78.16), ("Elizabeth City", 36.30, -76.22), ("Wilmington NC", 34.23, -77.94),
    ("Dover", 39.16, -75.52),
]
LOCAL_CITIES = [
    ("Norfolk", 36.90, -76.20), ("VA Beach", 36.84, -75.98), ("Chesapeake", 36.72, -76.24),
    ("Hampton", 37.03, -76.35), ("Williamsburg", 37.27, -76.71), ("Suffolk", 36.73, -76.58),
    ("Eliz. City", 36.30, -76.22), ("Eastern Shore", 37.55, -75.82), ("Nags Head", 35.96, -75.62),
    ("Richmond", 37.54, -77.44), ("Franklin", 36.68, -76.92), ("Gloucester", 37.41, -76.53),
    ("Smithfield", 36.98, -76.63), ("Edenton", 36.06, -76.61),
]


# ------------------------------------------------------------------ analysis
def compute_highs(highs):
    """Day-to-day: the biggest one-day fall in the daily HIGH (a front's passage). Same grid keys as compute()."""
    import numpy as np
    days = sorted(highs)
    shape = next(iter(highs.values())).shape
    best = np.full(shape, -np.inf, np.float32)
    hi, lo, hd, ld = (np.full(shape, np.nan, np.float32) for _ in range(4))
    for d in days:
        n = d + timedelta(days=1)
        if n not in highs:
            continue
        drop = highs[d] - highs[n]
        better = np.nan_to_num(drop, nan=-np.inf) > best
        best = np.where(better, drop, best)
        hi = np.where(better, highs[d], hi)
        lo = np.where(better, highs[n], lo)
        hd = np.where(better, float(d.toordinal()), hd)
        ld = np.where(better, float(n.toordinal()), ld)
    best = np.where(np.isinf(best), np.nan, best)
    return {"drop": best, "hi": hi, "lo": lo, "hi_day": hd, "lo_day": ld}


def compute(highs, lows, span=4):
    """highs / lows: {date: 2-D array (deg F)}; lows are keyed by the MORNING they occur.
    -> dict of grids: drop, hi, lo, hi_day, lo_day (day ordinals)."""
    import numpy as np
    days = sorted(highs)
    shape = next(iter(highs.values())).shape
    best = np.full(shape, -np.inf, np.float32)
    hi = np.full(shape, np.nan, np.float32)
    lo = np.full(shape, np.nan, np.float32)
    hd = np.full(shape, np.nan, np.float32)
    ld = np.full(shape, np.nan, np.float32)
    for d in days:
        cand = [(d + timedelta(days=k), lows[d + timedelta(days=k)]) for k in range(1, span + 1)
                if d + timedelta(days=k) in lows]
        if not cand:
            continue
        stack = np.stack([g for _, g in cand])
        filled = np.where(np.isnan(stack), np.inf, stack)
        k = np.argmin(filled, axis=0)
        low = np.take_along_axis(filled, k[None], axis=0)[0]
        low = np.where(np.isinf(low), np.nan, low)
        drop = highs[d] - low
        better = np.nan_to_num(drop, nan=-np.inf) > best
        best = np.where(better, drop, best)
        hi = np.where(better, highs[d], hi)
        lo = np.where(better, low, lo)
        hd = np.where(better, float(d.toordinal()), hd)
        ld = np.where(better, np.array([c[0].toordinal() for c in cand], np.float32)[k], ld)
    best = np.where(np.isinf(best), np.nan, best)
    return {"drop": best, "hi": hi, "lo": lo, "hi_day": hd, "lo_day": ld}


def fetch(cfg, cache_dir, now_utc, debug=False):
    """-> {"lat","lon","drop","hi","lo","hi_day","lo_day","errors"}"""
    from . import ndfdmap
    out = {"errors": []}
    try:
        import eccodes  # noqa: F401
        import numpy as np
    except Exception:
        out["errors"].append("temperature crash map needs ecCodes + numpy (pip install eccodes numpy)")
        print("  ! " + out["errors"][-1])
        return out
    tz = ZoneInfo(cfg["timezone"])
    box = (-93.0, -66.0, 31.5, 44.5)  # much wider than the map view (it grows to fit 16:9 / 9:16)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    lnow = now_utc.astimezone(tz)
    first = lnow.date() if lnow.hour < 17 else lnow.date() + timedelta(days=1)
    last = None
    for sector in cfg.get("ndfd_sectors", ["midatlan", "conus"]):
        try:
            highs, lows, lat, lon = {}, {}, None, None
            for elem in ("maxt", "mint"):
                for vp in ("001-003", "004-007"):
                    path = ndfdmap._download(ndfdmap.TGFTP.format(sector=sector, vp=vp, elem=elem),
                                             cache / f"ndfd_{sector}_{vp}_{elem}.bin", cfg["user_agent"])
                    for valid, la, lo, v in ndfdmap._messages(path, box):
                        lat, lon = la, lo
                        lt = valid.astimezone(tz)
                        f = (v - 273.15) * 9 / 5 + 32
                        if elem == "maxt":
                            day = lt.date() if lt.hour >= 5 else lt.date() - timedelta(days=1)
                            highs.setdefault(day, f)
                        else:
                            day = lt.date() + (timedelta(days=1) if lt.hour >= 12 else timedelta())
                            lows.setdefault(day, f)
            if lat is None or not ndfdmap._covers(lat, lon, (MIDATL_VIEW[0], MIDATL_VIEW[1], MIDATL_VIEW[2], MIDATL_VIEW[3])):
                raise RuntimeError(f"{sector} sector doesn't cover the Mid-Atlantic")
            highs = {d: g for d, g in highs.items() if d >= first}
            lows = {d: g for d, g in lows.items() if d > first}
            if not highs or not lows:
                raise RuntimeError("not enough highs/lows in the forecast")
            res = compute(highs, lows, cfg.get("tempdrop_span", 4))
            res.update({"lat": lat, "lon": lon, "errors": [], "highs": compute_highs(highs)})
            if debug:
                print(f"   [tempdrop] {sector}: {len(highs)} highs, {len(lows)} lows, max drop {np.nanmax(res['drop']):.0f}")
            return res
        except Exception as ex:
            last = ex
            if debug:
                print(f"   [tempdrop] {sector} failed: {ex}")
    out["errors"].append(f"NDFD highs/lows: {last}")
    print(f"  ! temperature crash unavailable: {last}")
    return out


def sample(now_utc, tz):
    """Synthetic front: hot, humid-feeling highs Tue-Thu, then a plunge with the coldest air NW."""
    import numpy as np
    lat = np.linspace(31.5, 44.5, 400)[:, None] * np.ones((1, 540))
    lon = np.ones((400, 1)) * np.linspace(-93.0, -66.0, 540)[None, :]
    nw = np.clip((lat - 34.4) / 7.0, 0, 1) * 0.5 + np.clip((-76.0 - lon) / 8.5, 0, 1) * 0.6
    coast = np.clip((lon + 77.0) / 3.0, 0, 1)
    today = now_utc.astimezone(tz).date()
    highs = {today + timedelta(days=i): h - 7 * nw - 2 * coast for i, h in enumerate((84, 90, 91, 87, 66, 55, 58))}
    lows = {today + timedelta(days=i): l - 9 * nw + 2 * coast + 0.5 * np.sin(lon * 0.9) * np.cos(lat * 1.1)
            for i, l in enumerate((66, 67, 66, 64, 50, 38, 36), start=1)}
    res = compute(highs, lows, 4)
    res.update({"lat": lat, "lon": lon, "errors": [], "highs": compute_highs(highs)})
    return res


def _at(td, key, lon, lat):
    import numpy as np
    d = (td["lat"] - lat) ** 2 + ((td["lon"] - lon) * math.cos(math.radians(lat))) ** 2
    j, i = np.unravel_index(np.nanargmin(d), d.shape)
    v = td[key][j, i]
    if (td["lat"][j, i] - lat) ** 2 + (td["lon"][j, i] - lon) ** 2 > 0.6 or v != v:
        return None
    return float(v)


def city_rows(td, pool):
    rows = []
    for name, la, lo in pool:
        hi, lo_, dr, hd, ld = (_at(td, k, lo, la) for k in ("hi", "lo", "drop", "hi_day", "lo_day"))
        if None in (hi, lo_, dr, hd, ld):
            continue
        rows.append({"name": name, "lat": la, "lon": lo, "hi": round(hi), "lo": round(lo_), "drop": round(hi) - round(lo_),
                     "hi_day": datetime.fromordinal(int(hd)).date(), "lo_day": datetime.fromordinal(int(ld)).date()})
    return rows


# ------------------------------------------------------------------ drawing
def _ramp(n, stops=STOPS):
    cols = []
    for k in range(n):
        t = k / max(1, n - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                u = (t - t0) / (t1 - t0)
                cols.append(tuple(int(c0[i] + (c1[i] - c0[i]) * u) for i in range(3)))
                break
    return cols


def _scale(td, view):
    """Legend range (floor/ceil to 5) from the drops actually inside the view."""
    import numpy as np
    w, e, s, n = view
    m = (td["lon"] >= w) & (td["lon"] <= e) & (td["lat"] >= s) & (td["lat"] <= n) & ~np.isnan(td["drop"])
    v = td["drop"][m] if m.any() else td["drop"][~np.isnan(td["drop"])]
    lo = 5 * math.floor(np.percentile(v, 4) / 5)
    hi = 5 * math.ceil(np.percentile(v, 98) / 5)
    if hi - lo < 15:
        hi = lo + 15
    return lo, hi


def _core_days(dates):
    """The middle half of the dates across every city (so one odd spot doesn't stretch 'TUE-SUN')."""
    d = sorted(dates)
    if len(d) < 4:
        return d
    return d[len(d) // 4: len(d) - len(d) // 4] or d


def _day_range(dates):
    a, b = min(dates), max(dates)
    if a == b:
        return a.strftime("%a").upper(), a.strftime("%b %-d").upper()
    return f"{a.strftime('%a').upper()}-{b.strftime('%a').upper()}", f"{a.strftime('%b %-d').upper()}-{b.strftime('%-d').upper()}" \
        if a.month == b.month else f"{a.strftime('%b %-d').upper()}-{b.strftime('%b %-d').upper()}"


def _pick(rows, proj, area, n, boxsize, force_first="Norfolk", by_drop=True):
    """Largest drops first, never overlapping boxes; Norfolk is always included (home market)."""
    x0, y0, x1, y1 = area
    ok = []
    for r in rows:
        px, py = proj(r["lon"], r["lat"])
        if x0 <= px <= x1 and y0 <= py <= y1:
            ok.append((r, px, py))
    if by_drop:  # regional map: biggest crashes first; local map keeps the list order (home-market cities first)
        ok.sort(key=lambda t: (t[0]["name"] != force_first, -t[0]["drop"]))
    bw, bh = boxsize
    picked = []
    for r, px, py in ok:
        if len(picked) >= n:
            break
        if all(abs(px - p[1]) > bw * 0.55 or abs(py - p[2]) > bh * 1.05 for p in picked):
            picked.append((r, px, py))
    return picked


def _arrow(cv, x, y, w, size, c0=ORANGE, c1=ICE):
    """Gradient arrow (orange -> ice blue), drawn by hand: Poppins has no arrow glyph."""
    n = 14
    for k in range(n):
        t = k / (n - 1)
        col = tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
        cv.line([(x + w * k / n, y), (x + w * (k + 1.4) / n, y)], (*col, 255), size * 0.09)
    hd = size * 0.2
    cv.line([(x + w - hd, y - hd), (x + w, y), (x + w - hd, y + hd)], (*c1, 255), size * 0.09)


def _callout(cv, r, px, py, boxes, bounds, big):
    """Dark card with the city, 'HI° -> LO°' and the days. The white dot sits on the city; the card is placed on
    whichever side of it doesn't collide with the cards already placed."""
    fs = 46 if big else 38
    nm = 21 if big else 18
    arrow_w = fs * 1.25
    t1, t2 = f"{r['hi']}°", f"{r['lo']}°"
    inner = cv.width(t1, fs) + 16 + arrow_w + 16 + cv.width(t2, fs)
    bw = max(inner, cv.width(r["name"].upper(), nm) + 20 + cv.width(_days(r), nm - 6, "medium")) + 44
    bh = fs * 1.35 + nm * 1.9
    bx0, by0, bx1, by1 = bounds
    spots = [(px + 20, py - bh / 2), (px - 20 - bw, py - bh / 2), (px - bw / 2, py - bh - 22), (px - bw / 2, py + 22),
             (px + 20, py - bh - 6), (px - 20 - bw, py - bh - 6), (px + 20, py + 6), (px - 20 - bw, py + 6)]
    best = None
    for k, (x, y) in enumerate(spots):
        x = min(max(x, bx0), bx1 - bw)
        y = min(max(y, by0), by1 - bh)
        hit = (x - 8 < px < x + bw + 8 and y - 8 < py < y + bh + 8) or any(x < b[0] + b[2] + 10 and b[0] < x + bw + 10 and y < b[1] + b[3] + 10 and b[1] < y + bh + 10 for b in boxes)
        if not hit:
            best = (x, y)
            break
    if best is None:
        return False
    x, y = best
    boxes.append((x, y, bw, bh))
    cv.d.ellipse([z(px - 11), z(py - 11), z(px + 11), z(py + 11)], fill=(255, 255, 255, 255), outline=(13, 21, 38, 255),
                 width=z(3))
    cv.rect(x, y, bw, bh, (20, 31, 54, 235), r=12)
    cv.text(x + 22, y + 12, r["name"].upper(), nm, "bold", C["text"], anchor="lt")
    cv.text(x + bw - 16, y + 14, _days(r), nm - 6, "medium", C["muted"], anchor="rt")
    ty = y + nm * 1.55 + fs * 0.62
    cv.text(x + 22, ty, t1, fs, "bold", ORANGE, anchor="lm")
    ax = x + 22 + cv.width(t1, fs) + 14
    _arrow(cv, ax, ty, arrow_w, fs)
    cv.text(ax + arrow_w + 14, ty, t2, fs, "bold", ICE, anchor="lm")
    return True


def _days(r):
    return f"{r['hi_day'].strftime('%a').upper()} - {r['lo_day'].strftime('%a').upper()}"


def _legend(cv, x, y, w, lo, hi, cols, title="TEMPERATURE DROP (°F)"):
    cv.rect(x - 14, y - 40, w + 28, 100, (13, 21, 38, 205), r=12)
    cv.text(x, y - 16, title, 17, "bold", C["muted"], anchor="lm")
    seg = w / len(cols)
    for k, c in enumerate(cols):
        cv.d.rectangle([z(x + k * seg), z(y + 4), z(x + (k + 1) * seg + 1), z(y + 22)], fill=(*c, 255))
    ticks = list(range(int(lo), int(hi) + 1, 5))
    step = 1 if w / max(1, len(ticks) - 1) > 70 else 2
    for i, t in enumerate(ticks):
        if i % step == 0 or t == hi:
            lab = f"{t}°" + ("+" if t == hi else "")
            tx = x + w * (t - lo) / (hi - lo)
            cv.text(tx, y + 44, lab, 17, "bold", C["muted"], anchor="rm" if t == hi else "lm" if t == lo else "mm")


def _crop(td, view, stride):
    """Keep only the grid cells in (and just around) the view; regional views also drop to ~7 km cells."""
    import numpy as np
    w, e, s, n = view
    m = (td["lon"] >= w - 0.6) & (td["lon"] <= e + 0.6) & (td["lat"] >= s - 0.6) & (td["lat"] <= n + 0.6)
    if not m.any():
        return td
    r, c = np.where(m)
    sl = (slice(r.min(), r.max() + 1, stride), slice(c.min(), c.max() + 1, stride))
    return {k: (v[sl] if hasattr(v, "shape") and v.ndim == 2 else v) for k, v in td.items()}


def _graphic(td, pool, key, title_fn, view_box, n_call, tmin, pkg, cfg, tz, by_drop=True,
             labels=("HOTTEST HIGH", "COLDEST LOW"), legend_title="TEMPERATURE DROP (°F)"):
    rows = city_rows(td, pool)
    if not rows:
        return None
    top = max(r["drop"] for r in rows)
    if top < tmin and not cfg.get("tempdrop_always"):
        print(f"  - {key}: biggest drop only {top}°, skipped")
        return None
    cv = Canvas(cfg)
    W, H = cv.W, cv.H
    view = fullscreen.expand_view(view_box, 215 / H, 150 / H)
    td = _crop(td, outlookmap._view(W, H, view), 3 if view_box[1] - view_box[0] > 5 else 1)
    lo, hi = _scale(td, view_box)
    cols = _ramp(int((hi - lo) * 1.0) + 1 if (hi - lo) <= 40 else 40)
    bins = [(lo + (hi - lo) * k / len(cols) - 0.01, c) for k, c in enumerate(cols)]
    bins[0] = (-999, bins[0][1])
    from .ndfdmap import _cell_painter
    paint = _cell_painter({"lat": td["lat"], "lon": td["lon"], "val": td["drop"]}, bins, alpha=225)
    lay = outlookmap.draw_map([], W, H, cfg, outline=False, painter=paint, view=view, cities=[("-", 0, 0, 2)],
                              water_alpha=0.3, county_lines=False)  # dim the open ocean: NDFD values out there are coarse
    base = cv.img.convert("RGBA")
    base.alpha_composite(lay.resize(base.size) if lay.size != base.size else lay)
    cv.img = base.convert("RGB")
    cv.d = ImageDraw.Draw(cv.img, "RGBA")
    fullscreen._fade(cv, 0, 270, 238, 0)
    fullscreen._fade(cv, H - 190, H, 0, 225)
    w_, e_, s_, n_ = outlookmap._view(W, H, view)
    proj = lambda lo_, la: ((lo_ - w_) / (e_ - w_) * W, (n_ - la) / (n_ - s_) * H)
    # header + hottest-high -> coldest-low chips
    big_n = 5 * int(top // 5)
    title = title_fn(big_n, top)
    sub = None
    cv.header(title, sub, rule_color=None)
    picked_rows = None
    boxsize = (330, 120) if not cv.tall else (300, 108)
    bounds = (16, 250 if not cv.tall else 250, W - 16, H - 215)
    n_call = n_call if not cv.tall else max(5, n_call - 2)
    picks = _pick(rows, proj, (30, 262, W - 30, H - 235), n_call, boxsize, by_drop=by_drop)
    boxes = []
    shown = []
    for r, px, py in picks:
        if _callout(cv, r, px, py, boxes, bounds, big=not cv.tall):
            shown.append(r)
    hr, lr = _day_range(_core_days([r["hi_day"] for r in rows])), _day_range(_core_days([r["lo_day"] for r in rows]))
    cy = 206
    cw = 300 if not cv.tall else 232
    for k, (lab, col, rng) in enumerate(((labels[0], ORANGE, hr), (labels[1], ICE, lr))):
        x0 = cv.M + k * (cw + (84 if not cv.tall else 60))
        cv.rect(x0, cy, cw, 82 if not cv.tall else 74, (20, 31, 54, 235), r=10)
        cv.rect(x0, cy, 7, 82 if not cv.tall else 74, (*col, 255), r=3)
        cv.text(x0 + 24, cy + 8, lab, 27 if not cv.tall else 22, "bold", col, anchor="lt")
        cv.text(x0 + 24, cy + (46 if not cv.tall else 40), f"{rng[0]}  ·  {rng[1]}", 19 if not cv.tall else 16, "bold",
                C["muted"], anchor="lt", maxw=cw - 36)
        if k == 0:
            _arrow(cv, x0 + cw + 12, cy + (41 if not cv.tall else 37), 60 if not cv.tall else 36, 40)
    lw = 520 if not cv.tall else min(W - 2 * cv.M - 20, 560)
    _legend(cv, W - cv.M - lw, H - 120, lw, lo, hi, cols, legend_title)
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NWS NDFD"
    cv.footer(pkg, source=src)
    return cv


def tempdrop_graphics(pkg, cfg):
    td = pkg.get("_tempdrop") or {}
    if "drop" not in td:
        return None
    tz = ZoneInfo(cfg["timezone"])
    out = []
    mid = _graphic(td, MIDATL_CITIES, "temp_drop_midatlantic",
                   lambda n, top: f"A {n}° TEMPERATURE CRASH", tuple(cfg.get("tempdrop_view") or MIDATL_VIEW),
                   cfg.get("tempdrop_callouts", 9), cfg.get("tempdrop_min", 20), pkg, cfg, tz)
    if mid is not None:
        out.append(("temp_drop_midatlantic", mid))
    loc = _graphic(td, LOCAL_CITIES, "temp_drop_hamptonroads",
                   lambda n, top: f"HAMPTON ROADS: A {n}° DROP", tuple(cfg.get("tempdrop_local_view") or LOCAL_VIEW),
                   cfg.get("tempdrop_local_callouts", 8), cfg.get("tempdrop_min_local", 15), pkg, cfg, tz, by_drop=False)
    if loc is not None:
        out.append(("temp_drop_hamptonroads", loc))
    return out or None


def tempdrop_highs_graphics(pkg, cfg):
    """Day-to-day fall in the daily high (the day a front arrives): 'HIGH TUE 84 -> HIGH WED 61'."""
    td = pkg.get("_tempdrop") or {}
    if "highs" not in td:
        return None
    t2 = {"lat": td["lat"], "lon": td["lon"], **td["highs"]}
    tz = ZoneInfo(cfg["timezone"])
    out = []
    kw = {"labels": ("HIGH BEFORE", "HIGH AFTER"), "legend_title": "ONE-DAY DROP IN HIGHS (°F)"}
    mid = _graphic(t2, MIDATL_CITIES, "temp_drop_highs_midatlantic", lambda n, top: f"HIGHS DROP {n}° IN A DAY",
                   tuple(cfg.get("tempdrop_view") or MIDATL_VIEW), cfg.get("tempdrop_callouts", 9),
                   cfg.get("tempdrop_highs_min", 12), pkg, cfg, tz, **kw)
    if mid is not None:
        out.append(("temp_drop_highs_midatlantic", mid))
    loc = _graphic(t2, LOCAL_CITIES, "temp_drop_highs_hamptonroads", lambda n, top: f"HAMPTON ROADS: HIGHS DROP {n}°",
                   tuple(cfg.get("tempdrop_local_view") or LOCAL_VIEW), cfg.get("tempdrop_local_callouts", 8),
                   cfg.get("tempdrop_highs_min_local", 10), pkg, cfg, tz, by_drop=False, **kw)
    if loc is not None:
        out.append(("temp_drop_highs_hamptonroads", loc))
    return out or None
