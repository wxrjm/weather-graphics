"""POWER OUTAGE RISK MAP: NDFD peak-gust field for the windiest day of the period (outage_days, default 5) shaded by outage-risk level, with a Hampton Roads
side panel.  Uses the same levels as the 7-day Power Outage Risk cards (outagerisk.LEVELS); no shading = low risk.
Advisory guidance from forecast gusts only, not a utility forecast.  Config: outage_map_always (draw even when calm)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from . import ndfdmap, outlookmap
from .alertmap import _paste_rounded
from .outagerisk import LEVELS, RANGES, _level
from .theme import C, Canvas, z

BINS = [(l[3], l[1]) for l in LEVELS[1:]]  # ISOLATED and up; LOW stays unshaded so the basemap shows through


def outage_map(pkg, cfg):
    data = pkg.get("_ndfdmaps") or {}
    f = data.get("gust")
    if f is None:
        return None
    view = ndfdmap._wind_box(cfg)
    ext = tuple(view)
    day = None
    for d in data.get("gust_days") or []:  # the windiest day of the period (peak gust inside the map area)
        r = ndfdmap._plotted_range(d, ext)
        if r and (day is None or r[1] > day[1][1]):
            day = (d, r)
    if day:
        f, rng = day[0], day[1]
        dd = day[0]["date"]
        when = ("TODAY" if dd == datetime.now(ZoneInfo(cfg["timezone"])).date() else dd.strftime("%A").upper()) + dd.strftime(" %b %-d").upper()
    else:
        rng = ndfdmap._plotted_range(f, ext)
        when = "NEXT 24 HOURS"
        if not rng:
            return None
    if rng[1] < LEVELS[1][3] and not cfg.get("outage_map_always"):
        print("  - outage_map: gusts below outage-risk threshold, skipped")
        return None
    cv = Canvas(cfg)
    title, sub = "POWER OUTAGE RISK", (f"WINDIEST DAY  ·  {when}" if day else when) + "  ·  FROM FORECAST PEAK WIND GUSTS"
    cv.header(title, sub)
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    lay = outlookmap.draw_map([], mw, mh, cfg, outline=False,
                              painter=ndfdmap._cell_painter(f, BINS, alpha=215, smooth=cfg.get("wind_smooth", 2)), view=view)
    _paste_rounded(cv, lay, mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    # legend: only the levels that appear on the map (plus LOW)
    top = _level(rng[1])
    items = [(LEVELS[i][0], LEVELS[i][1]) for i in range(0, top + 1)]
    sz = 20 if not cv.tall else 22
    bw = min(mw - 32, 170 * len(items) + 24)
    cv.rect(mx + 16, my + mh - 64, bw, 48, (13, 21, 38, 225), r=10)
    cw = (bw - 24) / len(items)
    for i, (nm, col) in enumerate(items):
        x = mx + 28 + i * cw
        cv.rect(x, my + mh - 50, 18, 18, (*col, 255), r=4)
        cv.text(x + 26, my + mh - 41, nm, sz, "bold", anchor="lm")
    hv = ndfdmap._value_at(f, cfg["location"]["lon"], cfg["location"]["lat"]) or 0
    hl = _level(hv)
    rows = []
    for name, la, lo in cfg.get("outlook_points") or outlookmap.POINTS:
        v = ndfdmap._value_at(f, lo, la) or 0
        rows.append((name, LEVELS[_level(v)][1], LEVELS[_level(v)][0].title()))
    outlookmap._side(cv, px, py, pw_, ph_, LEVELS[hl][1], cfg["location"].get("area", "Hampton Roads Area").upper(),
                     LEVELS[hl][0], f"{LEVELS[hl][2].rstrip('.')}. Peak gusts near {int(5 * round(hv / 5))} mph. "
                     "Based on forecast wind only; not a utility outage forecast.", rows, "RISK BY CITY")
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "National Weather Service (NDFD)"
    cv.footer(pkg, source=src)
    return cv
