"""Big-text OBSERVED 24 HOUR MAX WIND GUSTS: giant headline, one huge max-gust number (coloured by band), where and when it was recorded, a mini bar per hour for the next 24 h, and a navy tagline banner.
Data: observed station gusts (pkg["_gusts"], api.weather.gov ASOS).  Config: gust_big_hours (24)."""
from datetime import timedelta

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
    """Observed: highest gust at any station (Norfolk Intl + nearby ASOS) in the past 24 hours."""
    data = pkg.get("_gusts")
    if not data or not data.get("stations"):
        return None
    now = data["now"]
    cut = now - timedelta(hours=cfg.get("gust_big_hours", 24))
    best, hourly, sustained = None, {}, False
    for s in data["stations"]:
        for t, g, w in s["obs"]:
            if t < cut or t > now:
                continue
            v = g if g is not None else w
            if v is None:
                continue
            k = t.replace(minute=0, second=0, microsecond=0)
            hourly[k] = max(hourly.get(k, 0), v)
            if g is not None and (best is None or g > best[0]):
                best = (g, t, s["name"])
    if best is None:  # no gusts reported anywhere: show the strongest sustained wind instead
        sustained = True
        for s in data["stations"]:
            for t, g, w in s["obs"]:
                if t >= cut and w is not None and (best is None or w > best[0]):
                    best = (w, t, s["name"])
    if best is None or len(hourly) < 6:
        return None
    tp, t0, stn = best
    rows = sorted((t, g) for t, g in hourly.items())
    gmax = int(round(tp))
    col, _ = band(gmax)
    cv = Canvas(cfg)
    W, H, M, tall = cv.W, cv.H, cv.M, cv.tall
    cv.logo(134 if not tall else 150)
    title = "HOW STRONG WERE THE WIND GUSTS?"
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
    cv.text(M + 48, top + 28, ("MAX WIND SPEED" if sustained else "MAX GUST") + " · PAST 24 HOURS", 36, "bold", C["muted"], anchor="lt")
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
        cv.text(M + 48, ry + 52, f"{stn.upper()}  ·  {t0.strftime('%a').upper()} {_hour(t0)}", 32, "medium", C["muted"], anchor="lm", maxw=W - 2 * M - 96)
    else:
        cv.text(rx, top + ch * 0.38, _word(gmax), 64, "bold", anchor="rm", maxw=(W - 2 * M) * 0.50)
        cv.text(rx, top + ch * 0.38 + 66, f"{t0.strftime('%a').upper()} {_hour(t0)}", 40, "bold", col, anchor="rm")
        cv.text(rx, top + ch * 0.38 + 116, f"OBSERVED AT {stn.upper()}", 30, "medium", C["muted"], anchor="rm", maxw=(W - 2 * M) * 0.5)
    # hourly bars
    by = top + ch + gap
    cv.rect(M, by, W - 2 * M, bars_h, (255, 255, 255, 14), r=18)
    n = len(rows)
    slot = (W - 2 * M - 40) / n
    base = by + bars_h - 46
    tp_ = by + 30
    vmax = max(gmax, 20) * 1.1
    for i, (t, g) in enumerate(rows):
        x = M + 20 + slot * (i + 0.5)
        bh = max(4, (base - tp_) * g / vmax)
        cv.rect(x - slot * 0.36, base - bh, slot * 0.72, bh, (*band(g)[0], 255), r=4)
        if i % (2 if not tall else 3) == 0:
            cv.text(x, base + 8, _hour(t).replace(" ", "").lower(), 20 if not tall else 22, "bold", C["muted"], anchor="mt")
    ty = H - tag_h
    cv.rect(0, ty, W, tag_h, (*NAVY, 255))
    cv.line([(0, ty), (W, ty)], (255, 255, 255, 200), 3)
    tag = f"PAST 24 HR PEAK {gmax} MPH · {stn.upper()}"
    ts = cv.fit(tag, 50, "bold", W - 2 * M, floor=24)
    cv.text(W / 2, ty + tag_h / 2 + 2, tag, ts, "bold", (255, 255, 255), anchor="mm", maxw=W - 2 * M)
    return cv


def big_gust_graphics(pkg, cfg):
    g = big_gust_24(pkg, cfg)
    return [("big_gust_24", g)] if g else None


# ---------------------------------------------------------------- 24-hour peak gusts by station
def _stations24(pkg, cfg):
    """-> (rows [(name, gust, time)] strongest first, now) from observed gusts in the past 24 h, or None."""
    data = pkg.get("_gusts")
    if not data or not data.get("stations"):
        return None
    now = data["now"]
    cut = now - timedelta(hours=24)
    rows = []
    for s in data["stations"]:
        pk = max(((g, t) for t, g, w in s["obs"] if t >= cut and g is not None), default=None)
        if pk:
            rows.append((s["name"], pk[0], pk[1]))
    rows.sort(key=lambda r: -r[1])
    return (rows, now) if rows else None


def _when(t):
    return f"{t.strftime('%a').upper()} {t.strftime('%-I:%M %p')}"


def gust_peaks_24(pkg, cfg):
    res = _stations24(pkg, cfg)
    if not res:
        print("  - gust_peaks_24: no gusts reported in the past 24 hours, skipped")
        return None
    rows, now = res
    cv = Canvas(cfg)
    cv.header("PEAK WIND GUSTS", "Highest reported · past 24 hours")
    M, W = cv.M, cv.W
    top, tall = cv.top, cv.tall
    name, g, t = rows[0]
    col = band(g)[0]
    ch = 300 if tall else 250
    cv.rect(M, top, W - 2 * M, ch, C["panel"], r=18)
    cv.rect(M, top, 14, ch, col, r=7)
    cv.text(M + 44, top + 52, "PAST 24 HOURS", 30, "bold", C["muted"], anchor="ls")
    big = 150
    cv.text(M + 44, top + 52 + big * 0.95, f"{g:.0f}", big, "bold", anchor="ls")
    bw = cv.width(f"{g:.0f}", big, "bold")
    cv.text(M + 44 + bw + 16, top + 52 + big * 0.95, "MPH", big * 0.28, "bold", C["muted"], anchor="ls")
    cv.text(M + 44, top + ch - 26, f"{name.upper()} · {_when(t)}", 28, "bold", anchor="ls", maxw=W - 2 * M - 80)
    ty = top + ch + 40
    cv.text(M, ty, "BY STATION", 24, "bold", C["muted"], anchor="ls")
    y = ty + 16
    n = min(len(rows), 10 if tall else 8)
    rh = min(84 if tall else 62, (cv.bottom - y) / (n + 1))
    fs = int(rh * 0.5)
    cx_t, cx_g = W - M - 250, W - M - 24
    cv.text(cx_t, y + rh * 0.7, "TIME", fs * 0.8, "bold", C["muted"], anchor="rs")
    cv.text(cx_g, y + rh * 0.7, "PEAK", fs * 0.8, "bold", C["muted"], anchor="rs")
    y += rh
    for nm, gg, tt in rows[:n]:
        cv.rect(M, y, W - 2 * M, rh - 6, C["panel"], r=8)
        cv.rect(M + 10, y + 8, 12, rh - 22, band(gg)[0], r=5)
        cv.text(M + 34, y + (rh - 6) * 0.68, nm.upper(), fs, "bold", anchor="ls", maxw=W - 2 * M - 520)
        cv.text(cx_t, y + (rh - 6) * 0.68, _when(tt), fs * 0.8, "medium", C["muted"], anchor="rs")
        cv.text(cx_g, y + (rh - 6) * 0.68, f"{gg:.0f} MPH", fs, "bold", anchor="rs")
        y += rh
    cv.footer(pkg, source="SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NWS station observations")
    return cv


def gust_peaks_24_big(pkg, cfg):
    res = _stations24(pkg, cfg)
    if not res:
        return None
    rows, now = res
    cv = Canvas(cfg)
    W, H, M, tall = cv.W, cv.H, cv.M, cv.tall
    cv.logo(134 if not tall else 150)
    title = "PEAK WIND GUSTS · PAST 24 HOURS"
    if tall:
        lines, size = ("PEAK WIND GUSTS", "PAST 24 HOURS"), cv.fit("PEAK WIND GUSTS", 100, "bold", W - 2 * M - 270)
    else:
        size = cv.fit(title, 92, "bold", W - 2 * M - 330)
        lines = (title,)
    for i, l in enumerate(lines):
        cv.text(M, 40 + size * (i + 1) + i * 6, l, size, "bold", anchor="ls")
    top = 40 + size * len(lines) + 40
    cv.line([(M, top), (W - M, top)], C["rule"], 3)
    tag_h = 110
    top += 24
    bottom = H - tag_h - 24
    n = min(len(rows), 5 if tall else 4)
    gap = 16
    rh = (bottom - top - gap * (n - 1)) / n
    for i, (nm, g, t) in enumerate(rows[:n]):
        y = top + i * (rh + gap)
        col = band(g)[0]
        cv.rect(M, y, W - 2 * M, rh, (255, 255, 255, 18), r=18)
        cv.rect(M, y + 16, 12, rh - 32, (*col, 255), r=6)
        ns = int(min(rh * 0.78, 190))
        cv.text(M + 50, y + rh / 2, f"{g:.0f}", ns, "bold", col, anchor="lm", stroke=1.5)
        nw = cv.width(f"{g:.0f}", ns, "bold")
        cv.text(M + 50 + nw + 14, y + rh / 2 + ns * 0.22, "MPH", max(30, int(ns * 0.26)), "bold", C["muted"], anchor="lm")
        tx = M + 50 + max(nw + 150, 360 if not tall else 330)
        if tall:
            cv.text(tx, y + rh * 0.40, nm.upper(), int(min(rh * 0.30, 46)), "bold", anchor="lm", maxw=W - M - 30 - tx)
            cv.text(tx, y + rh * 0.72, _when(t), int(min(rh * 0.22, 32)), "medium", C["muted"], anchor="lm")
        else:
            cv.text(W - M - 40, y + rh * 0.40, nm.upper(), int(min(rh * 0.30, 54)), "bold", anchor="rm", maxw=W - 2 * M - tx - 40)
            cv.text(W - M - 40, y + rh * 0.74, _when(t), int(min(rh * 0.22, 38)), "medium", C["muted"], anchor="rm")
    ty = H - tag_h
    cv.rect(0, ty, W, tag_h, (*NAVY, 255))
    cv.line([(0, ty), (W, ty)], (255, 255, 255, 200), 3)
    tag = f"HIGHEST: {rows[0][1]:.0f} MPH · {rows[0][0].upper()}"
    ts = cv.fit(tag, 50, "bold", W - 2 * M, floor=24)
    cv.text(W / 2, ty + tag_h / 2 + 2, tag, ts, "bold", (255, 255, 255), anchor="mm", maxw=W - 2 * M)
    return cv


def gust_peaks_24_graphics(pkg, cfg):
    out = [("gust_peaks_24", gust_peaks_24(pkg, cfg)), ("gust_peaks_24_big", gust_peaks_24_big(pkg, cfg))]
    out = [(k, g) for k, g in out if g]
    return out or None
