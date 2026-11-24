"""PEAK WIND DAY - HOURLY GUSTS: one bar per hour for the single windiest day of the forecast period, coloured
green / yellow / orange / red / purple by gust speed (no legend), with a wind-direction arrow in each bar and the
compass direction the wind is blowing FROM under the hour.  Data: NDFD hourly wind gust / direction."""
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from .gusts import COMPASS, _arrow
from .theme import C, Canvas

BANDS = [(75, (160, 82, 210), False), (58, (228, 62, 62), False), (40, (245, 150, 45), True),
         (25, (240, 205, 60), True), (0, (72, 178, 98), False)]  # (min mph, colour, dark text on it)


def band(g):
    return next((c, d) for lo, c, d in BANDS if g >= lo)


def windiest_day(pkg, cfg):
    """-> (date, [hour rows]) for the local day with the highest gust in the period, or None."""
    tz = ZoneInfo(cfg["timezone"])
    byday = {}
    for h in pkg.get("wind_hourly") or []:
        g = h.get("gust") if h.get("gust") is not None else h.get("wind")
        if g is None:
            continue
        t = datetime.fromisoformat(h["time"]).astimezone(tz)
        byday.setdefault(t.date(), []).append({"t": t, "g": int(5 * round(g / 5)), "dir": h.get("dir") or ""})
    if not byday:
        return None
    day = max(byday, key=lambda d: (max(r["g"] for r in byday[d]), -d.toordinal()))
    return day, byday[day]


def peak_wind_hourly(pkg, cfg):
    res = windiest_day(pkg, cfg)
    if not res or len(res[1]) < 6:
        return None
    day, rows = res
    cv = Canvas(cfg)
    tall = cv.tall
    cv.header("PEAK WIND DAY · HOURLY GUSTS",
              f"{pkg['location']['area'].upper()}  ·  {day.strftime('%A %b %-d').upper()}  ·  STRONGEST WINDS IN THE 7-DAY FORECAST  ·  MPH")
    M, W = cv.M, cv.W
    px, py, pw, ph = M, cv.top + 4, W - 2 * M, cv.bottom - cv.top - 8
    cv.rect(px, py, pw, ph, C["panel"], r=18)
    x0, x1 = px + 70, px + pw - 24
    y_top, y_bot = py + 62, py + ph - (112 if not tall else 130)
    gmax = max(r["g"] for r in rows)
    ymax = int(math.ceil((gmax + 6) / 10.0) * 10)
    cv.text(px + 24, py + 30, "MPH", 20, "bold", C["muted"], anchor="lm")
    for v in range(0, ymax + 1, 10):
        yy = y_bot - v / ymax * (y_bot - y_top)
        cv.line([(x0, yy), (x1, yy)], (255, 255, 255, 38), 2)
        cv.text(x0 - 12, yy, str(v), 22, "bold", C["muted"], anchor="rm")
    # full 24-hour axis so a partial day (today) still lines up with the clock
    slot = (x1 - x0) / 24
    bw = slot * 0.72
    peak = max(r["g"] for r in rows)
    for r in rows:
        i = r["t"].hour
        cx = x0 + slot * (i + 0.5)
        g = r["g"]
        col, dark = band(g)
        h = max(g / ymax * (y_bot - y_top), 4)
        cv.rect(cx - bw / 2, y_bot - h, bw, h, (*col, 255), r=6)
        cv.text(cx, y_bot - h - 8, str(g), 24 if not tall else 17, "bold", (255, 214, 90) if g == peak else None, anchor="ms")
        d = r["dir"]
        if d in COMPASS:
            asz = min(bw * 0.95, 40)
            ink = (20, 28, 46, 255) if dark else (255, 255, 255, 255)
            edge = (255, 255, 255, 140) if dark else (15, 25, 45, 160)
            if h >= asz + 14:
                _arrow(cv, cx, y_bot - asz * 0.5 - 8, asz, COMPASS[d], ink, outline=edge)
            else:
                _arrow(cv, cx, y_bot - h - 44, asz, COMPASS[d], (255, 255, 255, 255))
        hl = r["t"].strftime("%I%p").lstrip("0")
        hl = hl.replace("AM", "A").replace("PM", "P") if tall else hl.replace("AM", " AM").replace("PM", " PM")
        cv.text(cx, y_bot + 34, hl, 20 if not tall else 14, "bold", anchor="ms", maxw=slot - 2)
        cv.text(cx, y_bot + 72, d, 17 if not tall else 12, "medium", C["muted"], anchor="ms", maxw=slot - 2)
    cv.text(x0 - 12, y_bot + 72, "FROM", 16, "bold", C["muted"], anchor="rs")
    cv.footer(pkg, source="National Weather Service gridded forecast (NDFD) hourly wind gusts"
              if "SAMPLE" not in pkg.get("source", "") else "SAMPLE DATA")
    return cv
