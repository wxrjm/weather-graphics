"""Big-text 24 HOUR MAX WIND GUSTS: giant headline, one huge max-gust number (coloured by band), when it peaks and
from which direction, a mini bar per hour for the next 24 h, and a navy tagline banner.
Data: pkg["wind_hourly"] (NDFD gust, falling back to sustained wind).  Config: gust_big_hours (24)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from .bigtext import NAVY, _wrap2
from .peakwind import band
from .theme import C, Canvas

COMP = {"N": "NORTH", "NNE": "NORTH-NORTHEAST", "NE": "NORTHEAST", "ENE": "EAST-NORTHEAST", "E": "EAST", "ESE": "EAST-SOUTHEAST",
        "SE": "SOUTHEAST", "SSE": "SOUTH-SOUTHEAST", "S": "SOUTH", "SSW": "SOUTH-SOUTHWEST", "SW": "SOUTHWEST",
        "WSW": "WEST-SOUTHWEST", "W": "WEST", "WNW": "WEST-NORTHWEST", "NW": "NORTHWEST", "NNW": "NORTH-NORTHWEST"}


def _word(g):
    return ("CALM TO LIGHT" if g < 15 else "BREEZY" if g < 25 else "GUSTY" if g < 35 else "WINDY" if g < 46
            else "STRONG WINDS" if g < 58 else "DAMAGING WINDS" if g < 74 else "DESTRUCTIVE WINDS")


def _hour(t):
    return t.strftime("%-I %p").replace("AM", "AM").replace("PM", "PM")


def big_gust_24(pkg, cfg):
    tz = ZoneInfo(cfg["timezone"])
    rows = []
    for h in (pkg.get("wind_hourly") or [])[:cfg.get("gust_big_hours", 24)]:
        g = h.get("gust") if h.get("gust") is not None else h.get("wind")
        if g is None:
            continue
        rows.append((datetime.fromisoformat(h["time"]).astimezone(tz), float(g), h.get("dir") or ""))
    if len(rows) < 6:
        return None
    t0, tp, dp = max(rows, key=lambda r: (r[1], -r[0].timestamp()))
    gmax = int(round(tp))
    col, _ = band(gmax)
    cv = Canvas(cfg)
    W, H, M, tall = cv.W, cv.H, cv.M, cv.tall
    cv.logo(134 if not tall else 150)
    title = "HOW STRONG WILL THE WIND GUSTS GET?"
    if tall:
        lines, size = _wrap2(cv, title, W - 2 * M - 260, 104)
    else:
        size = cv.fit(title, 92, "bold", W - 2 * M - 330)
        lines = (title,)
    for i, l in enumerate(lines):
        cv.text(M, 40 + size * (i + 1) + i * 6, l, size, "bold", anchor="ls")
    top = 40 + size * len(lines) + 40
    cv.line([(M, top), (W - M, top)], C["rule"], 3)
    tag_h = 110
    bottom = H - tag_h - 24
    top += 24
    gap = 22
    bars_h = (bottom - top) * (0.30 if not tall else 0.26)
    ch = bottom - top - bars_h - gap
    cv.rect(M, top, W - 2 * M, ch, (255, 255, 255, 18), r=22)
    cv.rect(M, top + 22, 12, ch - 44, (*col, 255), r=6)
    cv.text(M + 48, top + 28, "MAX GUST · NEXT 24 HOURS", 36, "bold", C["muted"], anchor="lt")
    num = str(gmax)
    nsize = cv.fit(num, 520 if not tall else 480, "bold", (W - 2 * M) * 0.42)
    cx = M + 48
    cv.text(cx, top + ch * 0.55, num, nsize, "bold", col, anchor="lm", stroke=2)
    nw = cv.width(num, nsize, "bold")
    cv.text(cx + nw + 20, top + ch * 0.55 + nsize * 0.28, "MPH", 70 if not tall else 64, "bold", C["muted"], anchor="lm")
    rx = W - M - 40
    if tall:
        ry = top + ch * 0.80
        cv.text(M + 48, ry - 6, _word(gmax), 54, "bold", anchor="lm", maxw=W - 2 * M - 96)
        cv.text(M + 48, ry + 52, f"PEAKS ~{_hour(t0)}  ·  FROM THE {COMP.get(dp, dp)}".strip(" ·"), 32, "medium", C["muted"], anchor="lm", maxw=W - 2 * M - 96)
    else:
        cv.text(rx, top + ch * 0.38, _word(gmax), 64, "bold", anchor="rm", maxw=(W - 2 * M) * 0.50)
        cv.text(rx, top + ch * 0.38 + 66, f"PEAKS ~{_hour(t0)}", 40, "bold", col, anchor="rm")
        if dp:
            cv.text(rx, top + ch * 0.38 + 116, f"FROM THE {COMP.get(dp, dp)}", 30, "medium", C["muted"], anchor="rm", maxw=(W - 2 * M) * 0.5)
    # hourly bars
    by = top + ch + gap
    cv.rect(M, by, W - 2 * M, bars_h, (255, 255, 255, 14), r=18)
    n = len(rows)
    slot = (W - 2 * M - 40) / n
    base = by + bars_h - 46
    tp_ = by + 30
    vmax = max(gmax, 20) * 1.1
    for i, (t, g, d) in enumerate(rows):
        x = M + 20 + slot * (i + 0.5)
        bh = max(4, (base - tp_) * g / vmax)
        cv.rect(x - slot * 0.36, base - bh, slot * 0.72, bh, (*band(g)[0], 255), r=4)
        if i % (2 if not tall else 3) == 0:
            cv.text(x, base + 8, _hour(t).replace(" ", "").lower(), 20 if not tall else 22, "bold", C["muted"], anchor="mt")
    ty = H - tag_h
    cv.rect(0, ty, W, tag_h, (*NAVY, 255))
    cv.line([(0, ty), (W, ty)], (255, 255, 255, 200), 3)
    tag = f"PEAK GUST {gmax} MPH · {_word(gmax)}"
    ts = cv.fit(tag, 50, "bold", W - 2 * M, floor=24)
    cv.text(W / 2, ty + tag_h / 2 + 2, tag, ts, "bold", (255, 255, 255), anchor="mm", maxw=W - 2 * M)
    return cv


def big_gust_graphics(pkg, cfg):
    g = big_gust_24(pkg, cfg)
    return [("big_gust_24", g)] if g else None
