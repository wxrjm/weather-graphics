"""Power outage risk: 7-day cards from forecast peak wind gusts (one level higher on wet soil + strong gusts).

Levels (peak gust, mph): LOW < 30, ISOLATED 30-40, SCATTERED 41-50, NUMEROUS 51-60, EXTENSIVE 61+.
Advisory guidance only, not a utility forecast.  Config: outage_wet_gust (45), outage_wet_qpf (1.5).
"""
import math

from PIL import ImageDraw

from .theme import C, Canvas, z

LEVELS = [  # name, colour, short description, min gust
    ("LOW", (72, 178, 98), "Outages unlikely", 0),
    ("ISOLATED", (240, 205, 60), "A few outages from limbs on lines", 30),
    ("SCATTERED", (245, 150, 45), "Scattered outages due to fallen trees or branches.", 41),
    ("NUMEROUS", (228, 62, 62), "Several trees and large limbs down. Numerous outages", 51),
    ("EXTENSIVE", (160, 82, 210), "Many trees and limbs down, prolonged outages possible", 61),
]
RANGES = ["UNDER 30 MPH", "30-40 MPH", "41-50 MPH", "51-60 MPH", "61+ MPH"]
GREEN_A, GREEN_B, GREEN_C = (60, 150, 80), (46, 125, 66), (80, 170, 96)
TRUNK, GROUND, WIND, LEAF = (120, 80, 52), (150, 160, 180), (120, 160, 225), (80, 175, 95)


def _level(gust):
    return max(i for i, l in enumerate(LEVELS) if gust >= l[3])


def _rot(pts, ox, oy, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return [(ox + (x - ox) * c - (y - oy) * s, oy + (x - ox) * s + (y - oy) * c) for x, y in pts]


def _tree(cv, cx, by, level):
    """Little tree illustration, `by` = ground line; the tree gets progressively more battered."""
    d = cv.d
    P = lambda pts: [(z(x), z(y)) for x, y in pts]
    d.line(P([(cx - 76, by), (cx + 76, by)]), fill=(*GROUND, 255), width=z(4))
    lean = [0, 4, 14, 24, 0][level]
    if level == 4:  # fallen tree: stump + trunk lying down + canopy at the end
        d.polygon(P([(cx - 70, by), (cx - 70, by - 26), (cx - 62, by - 18), (cx - 56, by - 30), (cx - 48, by)]), fill=(*TRUNK, 255))
        d.polygon(P([(cx - 60, by - 22), (cx + 20, by - 4), (cx + 24, by), (cx - 52, by)]), fill=(*TRUNK, 255))
        for ox, oy, r in ((26, -22, 26), (50, -14, 22), (8, -12, 18)):
            d.ellipse(P([(cx + ox - r, by + oy - r), (cx + ox + r, by + oy + r)]), fill=(*GREEN_A, 255))
        _wind(d, cx - 70, by - 120, 2)
        for lx, ly in ((cx - 30, by - 110), (cx - 10, by - 90)):
            _leaf(d, lx, ly, 20)
        return
    trunk = [(cx - 7, by), (cx + 7, by), (cx + 4, by - 70), (cx - 4, by - 70)]
    can = [(cx - 10, by - 100, 28), (cx + 22, by - 78, 30), (cx - 28, by - 76, 28), (cx + 2, by - 62, 26)]
    trunk = _rot(trunk, cx, by, lean)
    d.polygon(P(trunk), fill=(*TRUNK, 255))
    for i, (x, y, r) in enumerate(can):
        (x, y), = _rot([(x, y)], cx, by, lean)
        d.ellipse(P([(x - r, y - r), (x + r, y + r)]), fill=(*[GREEN_C, GREEN_A, GREEN_B, GREEN_A][i], 255))
    if level >= 1:
        _wind(d, cx - 70, by - 108, level)
        _leaf(d, cx + 52, by - 124, 16)
    if level >= 2:
        _leaf(d, cx + 62, by - 98, 14)
        d.line(P([(cx + 40, by - 18), (cx + 58, by - 8)]), fill=(*TRUNK, 255), width=z(3))
    if level >= 3:
        for lx, ly in ((cx - 62, by - 62), (cx - 50, by - 40), (cx + 66, by - 60)):
            _leaf(d, lx, ly, 15)
        d.line(P([(cx - 76, by - 18), (cx - 52, by - 24)]), fill=(*TRUNK, 255), width=z(4))


def _wind(d, x, y, level):
    for k in range(min(3, 1 + level // 2)):
        yy = y + k * 22
        d.line([(z(x + k * 6), z(yy)), (z(x + 34 + k * 6), z(yy))], fill=(*WIND, 255), width=z(4))
        d.line([(z(x + 4 + k * 6), z(yy + 7)), (z(x + 24 + k * 6), z(yy + 7))], fill=(*WIND, 255), width=z(3))


def _leaf(d, x, y, s):
    d.polygon([(z(x), z(y)), (z(x + s), z(y - s * 0.35)), (z(x + s * 0.55), z(y + s * 0.55))], fill=(*LEAF, 255))


def outage_risk_graphic(pkg, cfg):
    days = [d for d in (pkg.get("days") or [])[:7] if d.get("max_gust") is not None]
    if len(days) < 3:
        return None
    wet_g, wet_q = cfg.get("outage_wet_gust", 45), cfg.get("outage_wet_qpf", 1.5)
    cv = Canvas(cfg)
    cv.header("POWER OUTAGE RISK", f"{pkg['location']['area'].upper()}  ·  BASED ON FORECAST PEAK WIND GUSTS")
    n = len(days)
    gap = 14
    cw = (cv.W - 2 * cv.M - gap * (n - 1)) / n
    top, bot = 205, 852
    for i, dd in enumerate(days):
        g = int(dd["max_gust"])
        lv = _level(g)
        wet = g >= wet_g and (dd.get("qpf") or 0) >= wet_q
        if wet:
            lv = min(4, lv + 1)
        name, col, desc, _ = LEVELS[lv]
        x = cv.M + i * (cw + gap)
        cv.rect(x, top, cw, bot - top, C["panel"], r=16)
        cv.text(x + cw / 2, top + 24, dd["dow"], 36, "bold", anchor="mt")
        cv.text(x + cw / 2, top + 72, dd["date_label"].upper(), 20, "medium", C["muted"], anchor="mt")
        _tree(cv, x + cw / 2, top + 252, lv)
        cv.text(x + cw / 2, top + 276, str(g), 76, "bold", anchor="mt")
        cv.text(x + cw / 2, top + 372, "MPH GUSTS", 19, "medium", C["muted"], anchor="mt")
        by = top + 413
        cv.rect(x + 10, by, cw - 20, bot - by - 10, (*col, 255), r=12)
        lum = 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2]
        tc = (20, 28, 46) if lum > 140 else (255, 255, 255)
        cv.text(x + cw / 2, by + 16, "OUTAGE RISK", 14, "bold", tc, anchor="mt")
        cv.text(x + cw / 2, by + 36, name, 26, "bold", tc, anchor="mt", maxw=cw - 30)
        cv.paragraph(x + cw / 2, by + 78, desc + (" (wet soil)" if wet else ""), 18, "regular", cw - 40, max_lines=4, lh=1.22,
                     fill=tc, anchor="ma")
    # legend
    lw = (cv.W - 2 * cv.M - 10 * 4) / 5
    ly, lh = 870, 122
    for i, (name, col, desc, _) in enumerate(LEVELS):
        x = cv.M + i * (lw + 10)
        cv.rect(x, ly, lw, lh, (*col, 255), r=12)
        lum = 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2]
        tc = (20, 28, 46) if lum > 140 else (255, 255, 255)
        cv.text(x + lw / 2, ly + 14, name, 26, "bold", tc, anchor="mt")
        cv.text(x + lw / 2, ly + 46, RANGES[i], 21, "bold", tc, anchor="mt")
        cv.paragraph(x + lw / 2, ly + 78, desc, 15, "bold", lw - 24, max_lines=2, lh=1.15, fill=tc, anchor="ma")
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NWS POINT FORECAST GUSTS"
    cv.footer(pkg, source=f"{src} · ONE LEVEL HIGHER WITH {wet_g}+ MPH GUSTS AND {wet_q}\" OR MORE OF RAIN (WET SOIL). ADVISORY GUIDANCE, NOT A UTILITY FORECAST")
    return cv
