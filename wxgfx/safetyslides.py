"""Safety Graphics, slide-style set: severe thunderstorm (gold), tornado (red) and flood (green) explainers in the
Meteorologist Ricky Matthews look.  Same Poppins fonts and cv.header()/cv.footer() as every other graphic in the script.
Original vector art only.  Wide (16:9) and tall/social layouts are both handled by the shared templates below.

Registered by safety.py (appended to MAKERS) -> names safety_* (folder "Safety Graphics").
"""
import math

from .safety import (WHITE, INK, _boxes, _card, _footer, _header, arrow, cloud, ell, house, on, poly, rain, rot, rrect,
                     tree)
from .theme import C, Canvas

GOLD, RED, GREEN = (233, 176, 46), (238, 52, 48), (40, 230, 80)
WATER = (50, 130, 220)
SRC = "National Weather Service"


# ------------------------------------------------------------------ layout helpers
def _split(cv, art, frac_w=0.36, frac_h=0.30, bottom=None):
    """-> (art_box|None, content_box).  Art on the left (wide) or on top (tall)."""
    x, y, w = cv.M, cv.top, cv.W - 2 * cv.M
    h = (cv.bottom if bottom is None else bottom) - y
    if not art:
        return None, (x, y, w, h)
    if not cv.tall:
        aw = w * frac_w
        return (x, y, aw, h), (x + aw + 22, y, w - aw - 22, h)
    ah = h * frac_h
    return (x, y, w, ah), (x, y + ah + 16, w, h - ah - 16)


def _art(cv, art, box):
    if art and box:
        x, y, w, h = box
        cv.rect(x, y, w, h, C["panel"], r=14)
        art(cv, (x + 12, y + 12, w - 24, h - 24))


def _stack(box, n, gap=16):
    x, y, w, h = box
    bh = (h - gap * (n - 1)) / n
    return [(x, y + i * (bh + gap), w, bh) for i in range(n)]


def _panel(cv, box, accent, head, text, hs=38, bs=31):
    """Dark panel, white bar on the left, accent heading, thin rule, white bold uppercase text."""
    x, y, w, h = box
    cv.rect(x, y, w, h, C["panel"], r=10)
    cv.rect(x, y, 10, h, WHITE, r=4)
    pad = 34
    ty = y
    if head:
        cv.text(x + pad, y + 16 + hs, head.upper(), hs, "bold", accent, anchor="ls", maxw=w - pad - 20)
        ry = y + 16 + hs + 14
        cv.line([(x + pad, ry), (x + w - 24, ry)], (255, 255, 255, 110), 2)
        ty = ry + 4
    cv.paragraph(x + pad, ty + 6, text.upper(), bs, "bold", w - pad - 26, max_lines=4, lh=1.2, fill=WHITE, anchor="la",
                 valign="middle", box_h=y + h - ty - 12)


def _panels(cv, accent, items, art=None, art_frac_w=0.36, art_frac_h=0.30, hs=38, bs=31):
    abox, cbox = _split(cv, art, art_frac_w, art_frac_h)
    _art(cv, art, abox)
    for b, (head, text) in zip(_stack(cbox, len(items)), items):
        _panel(cv, b, accent, head, text, hs, bs)


def _bullets(cv, accent, items, art=None, size=40, art_frac_w=0.34):
    abox, cbox = _split(cv, art, art_frac_w, 0.28)
    _art(cv, art, abox)
    x, y, w, h = cbox
    cv.rect(x, y, w, h, C["panel"], r=18)
    band = h / len(items)
    for i, t in enumerate(items):
        cy = y + band * (i + 0.5)
        ell(cv, x + 52, cy, 17, 17, accent)
        cv.paragraph(x + 92, cy - band / 2, t.upper(), size, "bold", w - 130, max_lines=3, lh=1.15, fill=WHITE,
                     anchor="la", valign="middle", box_h=band)


def _statement(cv, accent, big, items, big_size=104):
    x, y, w, h = cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top
    bh = h * (0.40 if not cv.tall else 0.30)
    cv.rect(x, y, w, bh, accent, r=18)
    cv.paragraph(x + 30, y, big.upper(), big_size if not cv.tall else 84, "bold", w - 60, max_lines=2, lh=1.05,
                 fill=on(accent), anchor="la", valign="middle", box_h=bh)
    rest = (x, y + bh + 18, w, h - bh - 18)
    if not cv.tall and len(items) > 1:  # items side by side on wide
        gap = 18
        cw = (w - gap * (len(items) - 1)) / len(items)
        for i, (hd, tx) in enumerate(items):
            _panel(cv, (x + i * (cw + gap), rest[1], cw, rest[3]), accent, hd, tx, 40, 32)
    else:
        for b, (hd, tx) in zip(_stack(rest, len(items)), items):
            _panel(cv, b, accent, hd, tx, 38, 31)


def _callout(cv, accent, big, sub, items, art=None):
    """Left (top on tall) accent callout with big text, art and a sub line; panels on the right."""
    x, y, w, h = cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top
    if not cv.tall:
        lw = w * 0.40
        lbox, rbox = (x, y, lw, h), (x + lw + 22, y, w - lw - 22, h)
    else:
        lh_ = h * 0.46
        lbox, rbox = (x, y, w, lh_), (x, y + lh_ + 16, w, h - lh_ - 16)
    lx, ly, lw, lh2 = lbox
    cv.rect(lx, ly, lw, lh2, C["panel"], r=16, outline=accent, ow=6)
    bigh = lh2 * ((0.36 if not cv.tall else 0.26) if art else 0.55)
    cv.paragraph(lx + 20, ly + 14, big.upper(), 56 if not cv.tall else 50, "bold", lw - 40, max_lines=3, lh=1.05, fill=accent,
                 anchor="la", valign="middle", box_h=bigh)
    if art:
        art(cv, (lx + 16, ly + bigh + 14, lw - 32, lh2 - bigh - 40 - (70 if sub else 0)))
    if sub:
        cv.paragraph(lx + 20, ly + lh2 - 96, sub.upper(), 30, "bold", lw - 40, max_lines=2, lh=1.1, fill=WHITE, anchor="la",
                     valign="middle", box_h=84)
    for b, (hd, tx) in zip(_stack(rbox, len(items)), items):
        _panel(cv, b, accent, hd, tx, 36, 30)


def _columns(cv, accent, cols, foots):
    """2-3 compare columns: heading, white rule, accent bullets, footer banner ("BE READY!" / "TAKE ACTION!")."""
    boxes = _boxes(cv, len(cols), gap=22)
    for box, (head, lines), (ft, solid) in zip(boxes, cols, foots):
        x, y, w, h = box
        cv.rect(x, y, w, h, C["panel"], r=16)
        hh = 96 if not cv.tall else 84
        cv.text(x + w / 2, y + hh * 0.66, head.upper(), 52 if not cv.tall else 46, "bold", accent, anchor="mm", maxw=w - 40)
        cv.line([(x + 30, y + hh), (x + w - 30, y + hh)], WHITE, 4)
        fh = 92 if not cv.tall else 78
        by, bh = y + hh + 10, h - hh - fh - 28
        band = bh / len(lines)
        for i, t in enumerate(lines):
            cy = by + band * (i + 0.5)
            ell(cv, x + 46, cy, 11, 11, accent)
            cv.paragraph(x + 74, cy - band / 2, t.upper(), 32 if not cv.tall else 30, "bold", w - 100, max_lines=3, lh=1.15,
                         fill=WHITE, anchor="la", valign="middle", box_h=band)
        fy = y + h - fh - 14
        if solid:
            cv.rect(x + 20, fy, w - 40, fh, accent, r=12)
        else:
            cv.rect(x + 20, fy, w - 40, fh, (0, 0, 0, 0), r=12, outline=accent, ow=5)
        cv.text(x + w / 2, fy + fh / 2, ft, 46 if not cv.tall else 40, "bold", on(accent) if solid else accent, anchor="mm",
                maxw=w - 70)


# ------------------------------------------------------------------ art
def _bolt(cv, cx, top, s, fill=(255, 224, 80)):
    pts = [(0.10, 0.0), (-0.22, 0.52), (-0.02, 0.50), (-0.16, 1.0), (0.26, 0.38), (0.04, 0.40), (0.24, 0.0)]
    poly(cv, [(cx + a * s, top + b * s) for a, b in pts], fill)


def art_bow(cv, box):
    """Radar-style bow echo with straight-line wind arrows."""
    x, y, w, h = box
    cx, cy, R = x + w * 0.16, y + h * 0.5, min(w * 0.36, h * 0.34)
    bands = [((60, 170, 70), 1.00, 0.20), ((240, 220, 60), 0.84, 0.16), ((245, 140, 40), 0.68, 0.14), ((225, 55, 50), 0.54, 0.12)]
    for col, k, th in bands:
        outer, inner = [], []
        for i in range(31):
            a = math.radians(-62 + 124 * i / 30)
            bulge = 1.0 + 0.30 * math.cos(a * 1.45)  # bows out in the middle
            r = R * k * bulge
            outer.append((cx + r * math.cos(a), cy + r * math.sin(a)))
            inner.append((cx + (r - R * th) * math.cos(a), cy + (r - R * th) * math.sin(a)))
        poly(cv, outer + inner[::-1], col)
    for dy in (-0.30, 0.0, 0.30):
        ax = cx + R * 1.38
        arrow(cv, ax, cy + dy * R * 1.5, x + w - 8, cy + dy * R * 1.5, WHITE, 8, 26)


def art_shelf(cv, box):
    x, y, w, h = box
    base = y + h * 0.84
    ell(cv, x + w * 0.62, y + h * 0.20, w * 0.34, h * 0.14, (72, 80, 100))
    ell(cv, x + w * 0.46, y + h * 0.28, w * 0.40, h * 0.12, (86, 95, 118))
    poly(cv, [(x + w * 0.04, y + h * 0.40), (x + w * 0.30, y + h * 0.30), (x + w * 0.98, y + h * 0.26),
              (x + w * 0.98, y + h * 0.44), (x + w * 0.34, y + h * 0.48)], (132, 142, 164))
    for i in range(5):  # shelf layers
        yy = y + h * (0.32 + 0.03 * i)
        cv.line([(x + w * (0.10 + 0.04 * i), yy + h * 0.03), (x + w * 0.95, yy - h * 0.01)], (176, 186, 206, 150), 3)
    rain(cv, x + w * 0.45, y + h * 0.50, x + w * 0.95, base - 6, 26, ln=26, seed=8)
    cv.line([(x, base), (x + w, base)], (96, 150, 84), 5)
    arrow(cv, x + w * 0.44, y + h * 0.62, x + w * 0.06, y + h * 0.62, WHITE, 8, 26)
    arrow(cv, x + w * 0.44, y + h * 0.74, x + w * 0.10, y + h * 0.74, WHITE, 8, 26)


def art_waterspout(cv, box):
    x, y, w, h = box
    cx, wl = x + w * 0.5, y + h * 0.78
    ell(cv, cx, y + h * 0.16, w * 0.40, h * 0.12, (78, 86, 108))
    ell(cv, cx - w * 0.18, y + h * 0.22, w * 0.26, h * 0.09, (96, 106, 130))
    poly(cv, [(cx - w * 0.16, y + h * 0.24), (cx + w * 0.16, y + h * 0.24), (cx + w * 0.03, wl), (cx - w * 0.03, wl)],
         (200, 210, 224))
    poly(cv, [(cx - w * 0.10, y + h * 0.26), (cx + w * 0.02, y + h * 0.26), (cx + w * 0.01, wl), (cx - w * 0.02, wl)],
         (160, 172, 190))
    cv.rect(x, wl, w, y + h - wl, (*WATER, 255), r=0)
    ell(cv, cx, wl, w * 0.16, h * 0.03, (225, 235, 245))
    for i in range(4):
        yy = wl + h * 0.05 * (i + 1)
        cv.line([(x + w * 0.1, yy), (x + w * 0.35, yy)], (130, 185, 245), 4)
        cv.line([(x + w * 0.62, yy + 8), (x + w * 0.9, yy + 8)], (130, 185, 245), 4)


def art_tidal(cv, box):
    x, y, w, h = box
    gy = y + h * 0.72
    ell(cv, x + w * 0.84, y + h * 0.14, h * 0.09, h * 0.09, (236, 238, 220))  # moon
    ell(cv, x + w * 0.88, y + h * 0.12, h * 0.08, h * 0.08, (28, 40, 68))
    hw = w * 0.34
    house(cv, x + w * 0.08, gy, hw, h * 0.26)
    tree(cv, x + w * 0.62, gy, h * 0.40)
    cv.rect(x, gy, w, y + h - gy, (84, 88, 100), r=0)  # road
    cv.rect(x, gy + h * 0.06, w, y + h - gy - h * 0.06, (*WATER, 190), r=0)
    for i in range(3):
        yy = gy + h * (0.10 + 0.06 * i)
        cv.line([(x + w * 0.08, yy), (x + w * 0.30, yy)], (190, 225, 255), 4)
        cv.line([(x + w * 0.52, yy + 6), (x + w * 0.80, yy + 6)], (190, 225, 255), 4)
    arrow(cv, x + w * 0.9, y + h * 0.92, x + w * 0.9, y + h * 0.5, (190, 225, 255), 10, 30)


def art_lightning(cv, box):
    x, y, w, h = box
    cloud(cv, x + w * 0.5, y + h * 0.24, min(w, h) * 0.9, fill=(150, 160, 182), shade=(110, 120, 144))
    _bolt(cv, x + w * 0.52, y + h * 0.36, h * 0.46)
    house(cv, x + w * 0.18, y + h * 0.95, w * 0.22, h * 0.17)
    tree(cv, x + w * 0.74, y + h * 0.95, h * 0.40)


def art_hail(cv, box):
    x, y, w, h = box
    cloud(cv, x + w * 0.5, y + h * 0.30, min(w, h) * 0.75, fill=(150, 160, 182), shade=(110, 120, 144))
    import random
    rnd = random.Random(5)
    for _ in range(14):
        sx, sy, r = rnd.uniform(x + w * 0.12, x + w * 0.88), rnd.uniform(y + h * 0.42, y + h * 0.9), rnd.choice((10, 14, 18, 22))
        ell(cv, sx, sy, r, r, (236, 244, 252))
        ell(cv, sx - r * 0.25, sy - r * 0.25, r * 0.35, r * 0.35, WHITE)


def art_overpass(cv, box):
    x, y, w, h = box
    gy = y + h * 0.86
    poly(cv, [(x + w * 0.02, y + h * 0.30), (x + w * 0.98, y + h * 0.30), (x + w * 0.98, y + h * 0.46), (x + w * 0.02, y + h * 0.46)],
         (150, 156, 170))
    for px in (0.18, 0.5, 0.82):
        cv.rect(x + w * px - 14, y + h * 0.46, 28, gy - y - h * 0.46, (118, 124, 140))
    cv.rect(x, gy, w, 8, (90, 96, 108))
    cx, cy, r = x + w * 0.5, y + h * 0.50, min(w, h) * 0.32
    ell(cv, cx, cy, r, r, None, outline=RED, w=14)
    cv.line([(cx - r * 0.7, cy - r * 0.7), (cx + r * 0.7, cy + r * 0.7)], RED, 14)


def _car(cv, x, base, w, col=(205, 210, 222)):
    k = w / 180.0
    rrect(cv, x, base - 38 * k, w, 24 * k, col, r=8 * k)
    poly(cv, [(x + 0.20 * w, base - 38 * k), (x + 0.31 * w, base - 60 * k), (x + 0.69 * w, base - 60 * k), (x + 0.82 * w, base - 38 * k)], col)
    poly(cv, [(x + 0.26 * w, base - 40 * k), (x + 0.34 * w, base - 56 * k), (x + 0.49 * w, base - 56 * k), (x + 0.49 * w, base - 40 * k)], (96, 120, 160))
    poly(cv, [(x + 0.52 * w, base - 40 * k), (x + 0.52 * w, base - 56 * k), (x + 0.66 * w, base - 56 * k), (x + 0.77 * w, base - 40 * k)], (96, 120, 160))
    for fx in (0.22, 0.78):
        ell(cv, x + fx * w, base - 13 * k, 13 * k, 13 * k, (34, 38, 48))
        ell(cv, x + fx * w, base - 13 * k, 6 * k, 6 * k, (160, 168, 184))
    return k


def _depth_art(inches):
    def art(cv, box):
        x, y, w, h = box
        cw = min(w * 0.86, h * 1.7)
        base = y + h * 0.80
        k = _car(cv, x + (w - cw) / 2, base, cw)
        lvl = inches * k
        cv.rect(x, base - lvl, w, lvl + h * 0.20, (*WATER, 170), r=0)
        cv.line([(x, base - lvl), (x + w, base - lvl)], (190, 225, 255), 4)
        cv.line([(x, base), (x + w, base)], (90, 96, 108), 3)
    return art


def _tornado_funnel(cv, cx, top, bot, w):
    poly(cv, [(cx - w, top), (cx + w, top), (cx + w * 0.15, bot), (cx - w * 0.15, bot)], (190, 198, 214))


def art_tropical(cv, box):
    x, y, w, h = box
    cx, cy = x + w * 0.5, y + h * 0.42
    for i, (r, a) in enumerate(((0.44, 90), (0.34, 120), (0.24, 160), (0.13, 200))):
        ell(cv, cx, cy, w * r, w * r * 0.55, (225, 232, 245, a))
    ell(cv, cx, cy, w * 0.04, w * 0.025, (20, 28, 46))
    _tornado_funnel(cv, x + w * 0.78, y + h * 0.58, y + h * 0.90, w * 0.06)
    ell(cv, x + w * 0.78, y + h * 0.55, w * 0.11, h * 0.05, (96, 106, 130))


# ------------------------------------------------------------------ graphics
def _make(title, sub, accent, build, src=SRC):
    def fn(pkg, cfg):
        cv = Canvas(cfg)
        _header(cv, title, sub, accent)
        build(cv, accent)
        _footer(cv, pkg, src)
        return cv
    return fn


def _svr_watch_warning(cv, a):
    _columns(cv, a,
             [("Severe Thunderstorm Watch", ["Conditions are favorable for severe storms", "Storms are not happening yet",
                                             "Covers a large area for several hours", "Review your plan and charge your phone"]),
              ("Severe Thunderstorm Warning", ["Severe storm is happening or about to", "Winds 58+ mph and/or 1\" hail",
                                               "Covers your town or county", "Move indoors away from windows now"])],
             [("BE READY!", False), ("TAKE ACTION!", True)])


def _derecho(cv, a):
    _panels(cv, a, [("What it is", "A long-lived windstorm from a fast-moving line of storms"),
                    ("How wide", "Damage swath at least 240 miles long with gusts of 58+ mph"),
                    ("What to do", "Go indoors early, stay away from windows, secure loose items")], art_bow)


def _shelf(cv, a):
    _panels(cv, a, [("What it is", "A low wedge cloud on the leading edge of a storm's cold outflow"),
                    ("What it means", "Strong gusty winds and heavy rain are about to arrive"),
                    ("Is it a tornado?", "No. It is a gust front and does not make a funnel")], art_shelf)


def _lightning(cv, a):
    _callout(cv, a, "When thunder roars, go indoors!", "No place outside is safe",
             [("Hear thunder?", "You are close enough to be struck by lightning"),
              ("Safe places", "A sturdy building or a hard-topped vehicle with windows up"),
              ("Wait it out", "Stay inside for 30 minutes after the last rumble")], art_lightning)


def _hail(cv, a):
    _bullets(cv, a, ["Move indoors, away from windows and skylights", "Driving? Pull over under sturdy cover",
                     "Stay in the vehicle and turn away from the glass", "Bring pets inside and park cars in a garage",
                     "Hail 1 inch or larger is severe"], art_hail)


def _ef_scale(cv, a):
    rows = [("EF0", (125, 200, 235), "65-85 mph", "Light damage"), ("EF1", (80, 200, 120), "86-110 mph", "Moderate damage"),
            ("EF2", (240, 220, 60), "111-135 mph", "Considerable damage"), ("EF3", (245, 150, 50), "136-165 mph", "Severe damage"),
            ("EF4", (232, 64, 64), "166-200 mph", "Devastating damage"), ("EF5", (206, 70, 224), "Over 200 mph", "Incredible damage")]
    x, y, w, h = cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top
    cols = 2 if not cv.tall else 1
    per = len(rows) // cols
    gap = 18
    cw = (w - gap * (cols - 1)) / cols
    for i, (nm, col, mph, dmg) in enumerate(rows):
        c, r = divmod(i, per)
        rh = (h - gap * (per - 1)) / per
        bx, by = x + c * (cw + gap), y + r * (rh + gap)
        cv.rect(bx, by, cw, rh, C["panel"], r=12)
        bw = min(rh * 1.1, 170)
        cv.rect(bx, by, bw, rh, col, r=12)
        cv.text(bx + bw / 2, by + rh / 2, nm, 50, "bold", on(col), anchor="mm", maxw=bw - 16)
        cv.text(bx + bw + 28, by + rh * 0.40, mph.upper(), 44, "bold", col, anchor="lm", maxw=cw - bw - 50)
        cv.text(bx + bw + 28, by + rh * 0.74, dmg.upper(), 30, "bold", WHITE, anchor="lm", maxw=cw - bw - 50)


def _emergency(cv, a):
    _statement(cv, a, "Tornado Emergency",
               [("What it means", "A large, confirmed tornado is headed for a populated area"),
                ("The risk", "Catastrophic damage and an imminent threat to life"),
                ("Do this now", "Take cover immediately in your safe place")])


def _waterspouts(cv, a):
    _panels(cv, a, [("What it is", "A tornado over water, or one that moves onto it"),
                    ("Where", "Chesapeake Bay and the coast, most often late summer and fall"),
                    ("Boaters", "Head to shore at a right angle to its path and watch for Marine Warnings")], art_waterspout)


def _tropical_tornadoes(cv, a):
    _bullets(cv, a, ["Tropical systems can spin up quick tornadoes", "Most common in the right-front quadrant",
                     "Often brief, weak and hidden in heavy rain", "They can happen far from the storm's center",
                     "Treat every Tornado Warning seriously"], art_tropical)


def _vehicle(cv, a):
    _callout(cv, a, "Never shelter under an overpass", None,
             [("Best option", "Drive to a sturdy building and go inside"),
              ("No shelter?", "Seat belt on, head below the windows, cover with a coat or blanket"),
              ("Or a ditch", "Lie flat in a low area away from the car and cover your head")], art_overpass)


def _ffw_watch_warning(cv, a):
    _columns(cv, a,
             [("Flash Flood Watch", ["Flooding is possible in the next hours", "Heavy rain may be on the way",
                                     "Know your flood-prone spots", "Have a plan to move to higher ground"]),
              ("Flash Flood Warning", ["Flash flooding is happening or imminent", "Rapid rises in water",
                                       "Roads and creeks can flood quickly", "Move to higher ground now"])],
             [("BE READY!", False), ("TAKE ACTION!", True)])


def _flood_depth(cv, a):
    foot = 90
    boxes = _boxes(cv, 3, bottom=cv.bottom - foot - 14)
    data = [("6 inches", 6, "Loss of control and stalling"), ("12 inches", 12, "Many cars start to float"),
            ("2 feet", 24, "Most cars, SUVs and trucks swept away")]
    for box, (ttl, inch, txt) in zip(boxes, data):
        _card(cv, box, a, ttl.upper(), _depth_art(inch), [(txt.upper(), 32, "bold", WHITE)], title_size=44 if not cv.tall else 38,
              art_frac=0.52, band=88)
    fy = cv.bottom - foot
    cv.rect(cv.M, fy, cv.W - 2 * cv.M, foot, a, r=14)
    cv.text(cv.W / 2, fy + foot / 2, "TURN AROUND, DON'T DROWN!", 54 if not cv.tall else 44, "bold", on(a), anchor="mm",
            maxw=cv.W - 2 * cv.M - 40)


def _tidal(cv, a):
    _panels(cv, a, [("What causes it", "High tide, onshore wind and a new or full moon"),
                    ("Sunny-day flooding", "Streets can flood with no rain at all"),
                    ("Stay safe", "Never drive through salt water and move cars to higher ground")], art_tidal)


SLIDES = [
    ("safety_svr_watch_vs_warning", _make("Severe Thunderstorm Watch vs Warning", "Know the difference", GOLD, _svr_watch_warning)),
    ("safety_derecho", _make("What Is a Derecho?", "Widespread damaging straight-line winds", GOLD, _derecho)),
    ("safety_shelf_cloud", _make("Shelf Cloud", "The leading edge of a storm", GOLD, _shelf)),
    ("safety_lightning_safety", _make("Lightning Safety", "When thunder roars, go indoors", GOLD, _lightning)),
    ("safety_hail_safety", _make("Hail Safety", "Protect yourself from large hail", GOLD, _hail)),
    ("safety_ef_scale", _make("Enhanced Fujita Scale", "Tornado damage ratings", RED, _ef_scale)),
    ("safety_tornado_emergency", _make("Tornado Emergency", "The highest level of tornado alert", RED, _emergency)),
    ("safety_waterspouts", _make("Waterspouts", "Tornadoes over water", RED, _waterspouts)),
    ("safety_tropical_tornadoes", _make("Tropical Tornadoes", "Tornadoes in hurricanes and tropical storms", RED, _tropical_tornadoes)),
    ("safety_vehicle_tornado", _make("Tornado While Driving", "Overpasses are not safe", RED, _vehicle)),
    ("safety_ffw_watch_vs_warning", _make("Flash Flood Watch vs Warning", "Know the difference", GREEN, _ffw_watch_warning)),
    ("safety_flood_depth", _make("How Deep Is Too Deep?", "Flood water and your vehicle", GREEN, _flood_depth)),
    ("safety_tidal_flooding", _make("Tidal Flooding", "Sunny-day flooding in Hampton Roads", GREEN, _tidal)),
]
