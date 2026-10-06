"""Frost & freeze risk: a map of each night's risk (NWS NDFD lows, adjusted for wind and cloud cover) and a
table of every local spot's low + risk for the next few nights.

Risk levels (low temperature, with "good frost nights" = wind under 8 mph and sky under 50% cloud):
  0 NO FROST     39°+ (or 37-38° on a breezy / cloudy night)
  1 PATCHY FROST 37-38° on a calm, clear night, or 33-36° when breezy / cloudy
  2 FROST LIKELY 33-36° on a calm, clear night
  3 FREEZE       29-32°
  4 HARD FREEZE  28° or colder
Data: NDFD GRIB2 MinT + wind speed + sky cover (tgftp.nws.noaa.gov, no key; needs eccodes + numpy).
Without ecCodes, the table falls back to the KORF point forecast (one row, no map).
Graphics are only made when some spot reaches PATCHY FROST or worse (config "frost_always": true to force).
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import fullscreen, outlookmap
from .alertmap import _paste_rounded
from .theme import C, Canvas

LEVELS = [  # (key, name, short, color, meaning)
    ("none", "NO FROST", "NONE", (70, 86, 112), "Lows stay too mild for frost."),
    ("patchy", "PATCHY FROST", "PATCHY", (150, 205, 245),
     "Patchy frost possible in colder, sheltered spots, mainly away from the water."),
    ("frost", "FROST LIKELY", "FROST", (70, 140, 240),
     "Frost is likely on a clear, calm night. Cover or bring in tender plants."),
    ("freeze", "FREEZE", "FREEZE", (150, 90, 225),
     "Temperatures at or below freezing. Protect plants, pets and outdoor pipes."),
    ("hard", "HARD FREEZE", "HARD FRZ", (215, 70, 200),
     "A hard freeze (28° or colder) will end the growing season. Protect pipes and bring pets in."),
]
BINS = [(k + 0.5, LEVELS[k + 1][3]) for k in range(4)]  # smooth risk field -> class colors


def level(low, wind=None, sky=None):
    if low is None or low != low:
        return None
    low = round(low)  # judge the same whole-degree low that's printed
    fav = (wind is None or wind != wind or wind < 8) and (sky is None or sky != sky or sky < 50)
    if low <= 28:
        return 4
    if low <= 32:
        return 3
    if low <= 36:
        return 2 if fav else 1
    if low <= 38:
        return 1 if fav else 0
    return 0


def _levels_np(low, wind, sky):
    import numpy as np
    fav = np.ones(low.shape, bool)
    if wind is not None:
        fav &= ~(wind >= 8)
    if sky is not None:
        fav &= ~(sky >= 50)
    low = np.round(low)
    cls = np.zeros(low.shape, np.float32)
    cls[(low <= 38) & fav] = 1
    cls[(low <= 36) & ~fav] = 1
    cls[(low <= 36) & fav] = 2
    cls[low <= 32] = 3
    cls[low <= 28] = 4
    cls[np.isnan(low)] = np.nan
    return cls


# ------------------------------------------------------------------ data
def _night_label(evening, today):
    if evening == today:
        return "TONIGHT"
    if evening == today + timedelta(days=1):
        return "TOMORROW NIGHT"
    return evening.strftime("%a").upper() + " NIGHT"


def fetch(cfg, cache_dir, now_utc, debug=False):
    """-> {"nights": [{"label","evening","low","wind","sky","risk","lat","lon"}], "errors": [...]}"""
    from . import ndfdmap
    out = {"nights": [], "errors": []}
    try:
        import eccodes  # noqa: F401
        import numpy as np
    except Exception:
        out["errors"].append("frost map needs ecCodes + numpy (pip install eccodes numpy); table uses the point forecast")
        return out
    tz = ZoneInfo(cfg["timezone"])
    box = tuple(cfg.get("outlook_view") or outlookmap.VIEW_BOX)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    ua = cfg["user_agent"]
    n_nights = cfg.get("frost_nights", 3)
    vps = ("001-003",) if n_nights <= 2 else ("001-003", "004-007")
    today = now_utc.astimezone(tz).date()
    last = None
    for sector in cfg.get("ndfd_sectors", ["midatlan", "conus"]):
        try:
            series = {"mint": [], "wspd": [], "sky": []}
            lat = lon = None
            for elem in series:
                for vp in vps:
                    url = ndfdmap.TGFTP.format(sector=sector, vp=vp, elem=elem)
                    path = ndfdmap._download(url, cache / f"ndfd_{sector}_{vp}_{elem}.bin", ua)
                    for valid, la, lo, v in ndfdmap._messages(path, box):
                        lat, lon = la, lo
                        series[elem].append((valid, v))
            if lat is None or not ndfdmap._covers(lat, lon, box):
                raise RuntimeError(f"{sector} sector doesn't cover the map")
            nights = {}
            for valid, v in series["mint"]:
                lt = valid.astimezone(tz)
                morning = lt.date() + (timedelta(days=1) if lt.hour >= 12 else timedelta())  # start or end stamp
                evening = morning - timedelta(days=1)
                lnow = now_utc.astimezone(tz)
                if morning < lnow.date() or (morning == lnow.date() and lnow.hour >= 9):
                    continue  # that night is already over
                nights.setdefault(evening, (v - 273.15) * 9 / 5 + 32)
            for evening in sorted(nights)[:n_nights]:
                t0 = datetime(evening.year, evening.month, evening.day, 21, tzinfo=tz)
                t1 = t0 + timedelta(hours=11)
                pick = lambda key, scale: (lambda g: np.nanmean(np.stack(g), axis=0) * scale if g else None)(
                    [v for t, v in series[key] if t0 <= t.astimezone(tz) <= t1])
                low = nights[evening]
                wind, sky = pick("wspd", 2.23694), pick("sky", 1.0)
                out["nights"].append({"label": _night_label(evening, today), "evening": evening.isoformat(),
                                      "lat": lat, "lon": lon, "low": low, "wind": wind, "sky": sky,
                                      "risk": _levels_np(low, wind, sky)})
            if debug:
                print(f"   [frost] {sector}: {len(out['nights'])} nights")
            if out["nights"]:
                return out
            raise RuntimeError("no overnight lows in range")
        except Exception as ex:
            last = ex
            if debug:
                print(f"   [frost] {sector} failed: {ex}")
    out["errors"].append(f"NDFD frost grids: {last}")
    print(f"  ! frost map unavailable: {last}")
    return out


def sample(now_utc, tz):
    """Synthetic grids: a cold, calm second night (frost/freeze inland), milder first and third nights."""
    import numpy as np
    lat = np.linspace(34.9, 39.3, 190)[:, None] * np.ones((1, 230))
    lon = np.ones((190, 1)) * np.linspace(-79.8, -73.8, 230)[None, :]
    inland = np.clip((-75.6 - lon) / 2.5, 0, 1.6) + np.clip((lat - 36.6) / 2.2, 0, 1)  # colder inland / north
    today = now_utc.astimezone(tz).date()
    out = {"nights": [], "errors": []}
    for i, (base, cool, wnd) in enumerate(((43, 8, 6), (38, 13, 3), (47, 6, 10))):
        low = base - cool * inland + 1.2 * np.sin(lon * 3.1) * np.cos(lat * 2.7)
        wind = wnd + 4 * np.clip((lon + 76.0), 0, 2)  # breezier at the coast
        sky = np.full(low.shape, 20.0 if i == 1 else 40.0)
        ev = today + timedelta(days=i)
        out["nights"].append({"label": _night_label(ev, today), "evening": ev.isoformat(), "lat": lat, "lon": lon,
                              "low": low, "wind": wind, "sky": sky, "risk": _levels_np(low, wind, sky)})
    return out


def _points(cfg):
    return [tuple(p) for p in (cfg.get("frost_points") or cfg.get("outlook_points") or outlookmap.POINTS)]


def _at(field, arr, lon, lat):
    import numpy as np
    if arr is None:
        return None
    d = (field["lat"] - lat) ** 2 + ((field["lon"] - lon) * np.cos(np.radians(lat))) ** 2
    j, i = np.unravel_index(np.nanargmin(d), d.shape)
    v = arr[j, i]
    return None if v != v else float(v)


def table_data(pkg, cfg):
    """-> (night labels, rows [(name, [(low, level) per night])], source)"""
    fr = pkg.get("_frost") or {}
    nights = fr.get("nights") or []
    if nights:
        rows = []
        for name, la, lo in _points(cfg):
            cells = []
            for n in nights:
                low, w_, s_ = (_at(n, n[k], lo, la) for k in ("low", "wind", "sky"))
                cells.append((None if low is None else round(low), level(low, w_, s_)))
            rows.append((name, cells))
        return [n["label"] for n in nights], rows, "National Weather Service (NDFD)"
    # fallback: KORF point forecast lows (night_cond tells us clear vs cloudy, wind_avg is the day's wind)
    start = 0
    days = [d for d in pkg.get("days", [])[start:start + cfg.get("frost_nights", 3)] if d.get("low") is not None]
    if not days:
        return [], [], None
    tz = ZoneInfo(cfg["timezone"])
    today = datetime.fromisoformat(pkg["issued"]).astimezone(tz).date()
    labels, cells = [], []
    for d in days:
        from datetime import date
        labels.append(_night_label(date.fromisoformat(d["date"]), today))
        cloudy = any(w in (d.get("night_cond") or "").lower() for w in ("cloudy", "rain", "showers", "storms"))
        cells.append((d["low"], level(d["low"], d.get("wind_avg"), 80 if cloudy else 20)))
    return labels, [(pkg["location"].get("name", "Norfolk"), cells)], "National Weather Service"


# ------------------------------------------------------------------ drawing
def _ink(c):
    return (20, 28, 46) if 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2] > 150 else C["text"]


def _legend(cv, x, y, maxw):
    outlookmap._legend_chips(cv, x, y, [(lv[3], lv[1].title()) for lv in LEVELS[1:]], maxw)


def _map_graphic(night, idx, pkg, cfg):
    from .ndfdmap import _cell_painter
    field = {"lat": night["lat"], "lon": night["lon"], "val": night["risk"]}
    cv = Canvas(cfg)
    title = "FROST & FREEZE RISK"
    subtitle = f"{night['label']}  ·  NWS FORECAST LOWS, WIND & CLOUD COVER"
    cv.header(title, subtitle)
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    paint = _cell_painter(field, BINS)
    _paste_rounded(cv, outlookmap.draw_map([], mw, mh, cfg, outline=False, painter=paint), mx, my)
    cv.d.rounded_rectangle([z_(mx), z_(my), z_(mx + mw), z_(my + mh)], radius=z_(18), outline=(255, 255, 255, 90),
                           width=z_(2))
    _legend(cv, mx + 16, my + mh - 60, mw - 32)
    loc = cfg["location"]
    hl = _at(night, night["low"], loc["lon"], loc["lat"])
    hk = level(hl, _at(night, night["wind"], loc["lon"], loc["lat"]), _at(night, night["sky"], loc["lon"], loc["lat"]))
    hk = hk or 0
    lv = LEVELS[hk]
    head = lv[1] + (f"  ·  {round(hl)}°" if hl is not None else "")
    meaning = (f"Forecast low near {round(hl)}° in Norfolk {night['label'].lower()}. " if hl is not None else "") + lv[4]
    rows = []
    for name, la, lo in _points(cfg):
        low = _at(night, night["low"], lo, la)
        k = level(low, _at(night, night["wind"], lo, la), _at(night, night["sky"], lo, la))
        rows.append((name, LEVELS[k][3] if k else None, f"{round(low)}°  {LEVELS[k][2]}" if low is not None else "--"))
    area = loc.get("area", "Hampton Roads Area").upper()
    outlookmap._side(cv, px, py, pw_, ph_, lv[3], area, head, meaning, rows, "FORECAST LOW & RISK")
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "National Weather Service (NDFD)"
    cv.footer(pkg, source=src)
    fullscreen.attach(cv, title=title, subtitle=subtitle,
                      map_fn=lambda pw, ph, view: outlookmap.draw_map([], pw, ph, cfg, outline=False, painter=paint, view=view),
                      box=tuple(cfg.get("outlook_view") or outlookmap.VIEW_BOX), head_label=area, head_value=head,
                      head_col=lv[3], meaning=meaning, rows=rows, overlay=lambda c, x, y, w: _legend(c, x, y, w), source=src)
    return cv


def z_(v):
    from .theme import z
    return z(v)


def _table_graphic(labels, rows, src, pkg, cfg):
    cv = Canvas(cfg)
    cv.header("FROST & FREEZE RISK", f"NEXT {len(labels)} NIGHTS  ·  FORECAST LOWS BY LOCATION")
    x, y, w, h = cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top
    # legend strip
    leg_h = 50
    _legend(cv, x, y, w)
    y += leg_h + 14
    h -= leg_h + 14
    note_h = 54 if h > 520 else 0
    n, m = len(rows), len(labels)
    name_w = min(w * (0.30 if cv.tall else 0.26), 340)
    head_h = 52
    gap = 8
    rh = min(150 if cv.tall else 120, (h - head_h - note_h - gap * n) / max(1, n))
    cw = (w - name_w - gap * m) / max(1, m)
    cv.rect(x, y, w, head_h, C["panel"], r=12)
    cv.text(x + 22, y + head_h / 2, "LOCATION", 20, "bold", C["muted"], anchor="lm")
    for j, lab in enumerate(labels):
        cx = x + name_w + gap + j * (cw + gap) + cw / 2
        cv.text(cx, y + head_h / 2, lab, 22 if cw > 200 else 17, "bold", anchor="mm", maxw=cw - 12)
    ry = y + head_h + gap
    home = cfg["location"].get("name", "Norfolk").split(",")[0].lower()
    for name, cells in rows:
        mine = name.lower().startswith(home[:6])
        cv.rect(x, ry, name_w, rh, C["panel"], r=10)
        if mine:
            cv.rect(x, ry, 8, rh, (88, 150, 255, 255), r=4)
        cv.text(x + 22, ry + rh / 2, name, min(30, rh * 0.42), "bold" if mine else "medium", anchor="lm", maxw=name_w - 30)
        for j, (low, k) in enumerate(cells):
            cx0 = x + name_w + gap + j * (cw + gap)
            col = LEVELS[k][3] if k else None
            cv.rect(cx0, ry, cw, rh, (*col, 255) if col else C["panel"], r=10)
            ink = _ink(col) if col else C["muted"]
            t = f"{low}°" if low is not None else "--"
            lab = LEVELS[k or 0][2] if low is not None else ""
            if rh >= 70:
                cv.text(cx0 + cw / 2, ry + rh * 0.44, t, min(46, rh * 0.42), "bold", ink if col else C["text"], anchor="mm")
                cv.text(cx0 + cw / 2, ry + rh * 0.78, lab, min(18, rh * 0.2), "bold", ink, anchor="mm", maxw=cw - 12)
            else:
                cv.text(cx0 + cw * 0.36, ry + rh / 2, t, min(30, rh * 0.5), "bold", ink if col else C["text"], anchor="mm")
                cv.text(cx0 + cw * 0.70, ry + rh / 2, lab, min(21, rh * 0.36), "bold", ink, anchor="mm", maxw=cw * 0.52)
        ry += rh + gap
    if note_h:
        cv.paragraph(x, ry + 8, "Frost can form with lows in the mid 30s on clear, calm nights, especially inland and in "
                     "low spots. Cover tender plants or bring them inside.", 21, "regular", w, max_lines=2, lh=1.25,
                     fill=C["muted"])
    cv.footer(pkg, source="SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else src)
    return cv


def frost_graphics(pkg, cfg):
    labels, rows, src = table_data(pkg, cfg)
    if not rows:
        return None
    worst = max((k or 0) for _, cells in rows for _, k in cells)
    if worst < cfg.get("frost_min_level", 1) and not cfg.get("frost_always"):
        print("  - frost_risk: no frost in the forecast, skipped")
        return None
    out = [("frost_risk_table", _table_graphic(labels, rows, src, pkg, cfg))]
    for i, night in enumerate((pkg.get("_frost") or {}).get("nights") or []):
        nworst = max((cells[i][1] or 0) for _, cells in rows)
        if nworst >= cfg.get("frost_min_level", 1) or cfg.get("frost_always"):
            out.append((f"frost_map_{i + 1}", _map_graphic(night, i, pkg, cfg)))
    return out
