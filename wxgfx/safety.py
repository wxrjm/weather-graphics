"""Safety Graphics: static explainer graphics in the Meteorologist Ricky Matthews look (navy card, Poppins, accent
color matching the hazard).  No forecast data is needed, so they only have to be made once; they are drawn with simple
vector shapes (no photos).  All four sizes work (wide cards sit side by side, tall cards stack).

Registered as graphics key "safety_graphics" -> names safety_* (folder "Safety Graphics").
Run just these:  python run.py --only safety_graphics
"""
import math

from PIL import ImageDraw

from .theme import C, Canvas, z

# ------------------------------------------------------------------ drawing helpers
SKY, GRASS, SOIL, WATER = (120, 170, 220), (92, 150, 84), (110, 84, 62), (62, 130, 205)
WHITE, INK = (255, 255, 255), (20, 28, 46)


def P(pts):
    return [(z(x), z(y)) for x, y in pts]


def poly(cv, pts, fill, outline=None, w=1):
    cv.d.polygon(P(pts), fill=fill, outline=outline, width=z(w) if outline else 0)


def ell(cv, cx, cy, rx, ry, fill, outline=None, w=1):
    cv.d.ellipse([z(cx - rx), z(cy - ry), z(cx + rx), z(cy + ry)], fill=fill, outline=outline, width=z(w) if outline else 0)


def rrect(cv, x, y, w, h, fill, r=0, outline=None, ow=2):
    cv.d.rounded_rectangle([z(x), z(y), z(x + w), z(y + h)], radius=z(r), fill=fill, outline=outline, width=z(ow))


def rot(pts, cx, cy, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


def arrow(cv, x0, y0, x1, y1, fill, w=8, head=26):
    ang = math.atan2(y1 - y0, x1 - x0)
    bx, by = x1 - math.cos(ang) * head * 0.8, y1 - math.sin(ang) * head * 0.8
    cv.line([(x0, y0), (bx, by)], fill, w)
    px, py = -math.sin(ang), math.cos(ang)
    poly(cv, [(x1, y1), (bx + px * head * 0.55, by + py * head * 0.55), (bx - px * head * 0.55, by - py * head * 0.55)], fill)


def lum(col):
    return 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2]


def on(col):
    return INK if lum(col) > 150 else WHITE


def cloud(cv, cx, cy, s, fill=(236, 241, 248), shade=(196, 206, 222)):
    for dx, dy, r in ((-0.30, 0.05, 0.26), (0.0, -0.12, 0.34), (0.30, 0.02, 0.28), (0.0, 0.10, 0.30)):
        ell(cv, cx + dx * s, cy + dy * s, r * s, r * s * 0.9, fill)
    if shade:
        ell(cv, cx, cy + 0.26 * s, 0.52 * s, 0.09 * s, shade)


def rain(cv, x0, y0, x1, y1, n, col=(130, 185, 245, 200), seed=3, ln=22, w=3):
    import random
    rnd = random.Random(seed)
    for _ in range(n):
        x, y = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
        cv.line([(x, y), (x - ln * 0.25, y + ln)], col, w)


def tree(cv, x, base, h, col=(70, 140, 80)):
    rrect(cv, x - h * 0.05, base - h * 0.35, h * 0.1, h * 0.35, (96, 70, 50))
    for dx, dy, r in ((-0.16, 0.45, 0.2), (0.16, 0.48, 0.2), (0, 0.62, 0.24), (0, 0.82, 0.18)):
        ell(cv, x + dx * h, base - dy * h - h * 0.12, r * h, r * h, col)


def house(cv, x, base, w, h, body=(168, 96, 86), roof=(110, 118, 132)):
    rrect(cv, x, base - h, w, h, body)
    poly(cv, [(x - w * 0.06, base - h), (x + w / 2, base - h - h * 0.5), (x + w * 1.06, base - h)], roof)
    for fx in (0.18, 0.62):
        rrect(cv, x + w * fx, base - h * 0.78, w * 0.2, h * 0.34, (232, 238, 246), r=2)
    rrect(cv, x + w * 0.42, base - h * 0.5, w * 0.16, h * 0.5, (60, 66, 80))


# ------------------------------------------------------------------ layout helpers
def _boxes(cv, n, gap=18, top=None, bottom=None):
    top = cv.top if top is None else top
    bottom = cv.bottom if bottom is None else bottom
    M, W = cv.M, cv.W
    if not cv.tall:
        cw = (W - 2 * M - gap * (n - 1)) / n
        return [(M + i * (cw + gap), top, cw, bottom - top) for i in range(n)]
    ch = (bottom - top - gap * (n - 1)) / n
    return [(M, top + i * (ch + gap), W - 2 * M, ch) for i in range(n)]


def _card(cv, box, accent, title, art, rows, title_size=34, art_frac=0.46, band=76):
    """One card: art on top (wide) or on the left (tall), a colored title band, then rows of
    (text, size, weight, color) lines, centered.  art(cv, (x, y, w, h)) draws into its box."""
    x, y, w, h = box
    cv.rect(x, y, w, h, C["panel"], r=14)
    horiz = cv.tall
    tc = on(accent)
    if horiz:
        aw = w * 0.36 if art else 0
        if art:
            art(cv, (x + 8, y + 8, aw - 8, h - 16))
        rx, rw = x + aw, w - aw
        by = y + 14 if art else y
        if not art:  # no art: title band on the left third, rows on the right
            tw = w * 0.34
            cv.rect(x, y, tw, h, (*accent, 255), r=14)
            cv.paragraph(x + tw / 2, y, title, title_size * 0.9, "bold", tw - 24, max_lines=3, lh=1.1, fill=tc, anchor="ma",
                         valign="middle", box_h=h)
            rx, rw = x + tw + 10, w - tw - 20
            by = y + 10
            band = 0
        else:
            cv.rect(rx, by, rw - 10, band, (*accent, 255), r=10)
            cv.text(rx + (rw - 10) / 2, by + band / 2, title, title_size, "bold", tc, anchor="mm", maxw=rw - 40)
            by += band + 8
        cx, cw = rx + (rw - (10 if art else 10)) / 2, rw - 36
        avail = y + h - by - 10
    else:
        ah = h * art_frac if art else 0
        if art:
            art(cv, (x + 6, y + 6, w - 12, ah - 6))
        by = y + ah
        cv.rect(x, by, w, band, (*accent, 255), r=0)
        cv.text(x + w / 2, by + band / 2, title, title_size, "bold", tc, anchor="mm", maxw=w - 30)
        by += band + 14
        cx, cw = x + w / 2, w - 36
        avail = y + h - by - 8
    # rows
    total = 0
    sizes = []
    for t, s, wt, col in rows:
        n = len(cv.wrap(t, s, wt, cw))
        sizes.append(n * s * 1.22 + 8)
        total += sizes[-1]
    k = min(1.0, avail / max(total, 1))
    cur = by + max(0, (avail - total * k) / 2)
    for (t, s, wt, col), hh in zip(rows, sizes):
        cv.paragraph(cx, cur, t, s * k, wt, cw, max_lines=4, lh=1.18, fill=col, anchor="ma")
        cur += hh * k
    return cur


def _header(cv, title, sub, accent):
    cv.header(title, sub, rule_color=accent)


def _footer(cv, pkg, src):
    cv.footer(pkg, source=src)


# ------------------------------------------------------------------ 1. hurricane hunters
def _plane(kind, k):
    """Plan view, nose to the right. -> art(cv, box). k = pixels per foot (shared so the sizes compare)."""
    spec = {  # length, span, fuselage width, wing LE from nose, root chord, tip chord, sweep(ft back at tip), props, jets
        "p3": (116.8, 99.6, 11.5, 40, 16.5, 8.0, 3, (0.30, 0.62), False),
        "g4": (88.3, 77.8, 7.7, 32, 15.0, 5.0, 16, (), True),
        "c130": (97.8, 132.6, 12.0, 30, 16.5, 12.5, 1, (0.26, 0.62), False),
    }[kind]
    L, span, fw, le, cr, ct, sw, props, jets = spec
    body = {"p3": (240, 244, 250), "g4": (246, 248, 252), "c130": (150, 158, 170)}[kind]
    wing = {"p3": (214, 222, 236), "g4": (226, 232, 242), "c130": (128, 136, 148)}[kind]
    edge = (96, 112, 140)

    def art(cv, box):
        bx, by, bw, bh = box
        cx, cy = bx + bw / 2 + 8, by + bh / 2
        n0 = cx + L * k / 2  # nose x
        f = lambda ft: n0 - ft * k
        hs = span / 2 * k
        # wings
        for sgn in (-1, 1):
            poly(cv, [(f(le), cy + sgn * fw * k / 2), (f(le + cr), cy + sgn * fw * k / 2),
                      (f(le + sw + ct), cy + sgn * hs), (f(le + sw), cy + sgn * hs)], wing, edge, 1.5)
        # tail plane
        ts, tc_ = span * (0.36 if kind != "g4" else 0.34), 8.0
        tx = L - tc_ - (2 if kind != "g4" else 3)
        for sgn in (-1, 1):
            poly(cv, [(f(tx), cy + sgn * fw * k * 0.3), (f(tx + tc_), cy + sgn * fw * k * 0.3),
                      (f(tx + tc_ + (4 if kind == "g4" else 1)), cy + sgn * ts / 2 * k), (f(tx + (4 if kind == "g4" else 1)), cy + sgn * ts / 2 * k)],
                 wing, edge, 1.5)
        # fuselage
        rrect(cv, f(L), cy - fw * k / 2, L * k, fw * k, body, r=fw * k / 2, outline=edge, ow=1.5)
        if kind == "p3":
            cv.line([(f(L * 0.92), cy), (f(L * 0.12), cy)], (255, 140, 0, 255), max(2, fw * k * 0.12))  # NOAA orange stripe
        # engines / props
        for fr in props:
            for sgn in (-1, 1):
                ex, ey = f(le + sw * fr * 2 - 5), cy + sgn * hs * (fr + 0.1) * (1 if kind == "p3" else 1.0)
                ell(cv, ex, ey, 6.5 * k, 2.4 * k, (110, 120, 140), edge, 1)
                cv.line([(ex + 6 * k, ey - 8 * k), (ex + 6 * k, ey + 8 * k)], (60, 70, 90, 150), 2.5)
        if jets:
            for sgn in (-1, 1):
                ell(cv, f(L - 24), cy + sgn * (fw * k / 2 + 3.6 * k), 8 * k, 2.6 * k, (150, 160, 180), edge, 1)
        # span bracket
        bxl = cx - L * k / 2 - 18
        cv.line([(bxl, cy - hs), (bxl, cy + hs)], (255, 255, 255, 120), 2)
        for yy in (cy - hs, cy + hs):
            cv.line([(bxl - 6, yy), (bxl + 6, yy)], (255, 255, 255, 120), 2)
    return art


def hurricane_hunters(pkg, cfg):
    cv = Canvas(cfg)
    red = (222, 70, 60)
    _header(cv, "HURRICANE HUNTERS", "PLANE COMPARISONS", red)
    boxes = _boxes(cv, 3)
    bw0, bh0 = boxes[0][2], boxes[0][3]
    k = min(((bh0 * 0.50) if not cv.tall else (bh0 - 30)) * 0.9 / 135, (bw0 * (0.34 if cv.tall else 0.84)) / 125)
    data = [("WP-3D ORION", "p3", "99.6 ft", "27,000 ft", "Flies into the eye of the storm, measuring its intensity"),
            ("NOAA G-IV", "g4", "77.8 ft", "45,000 ft", "Flies at high altitude around the storm's edges, sampling the environment"),
            ("AIR FORCE C-130", "c130", "132.6 ft", "33,000 ft", "Flies into the eye of the storm, measuring its intensity")]
    for box, (nm, kind, ws, ceil, job) in zip(boxes, data):
        rows = [("WINGSPAN", 22, "medium", C["muted"]), (ws, 54, "bold", WHITE), ("CEILING", 22, "medium", C["muted"]),
                (ceil, 54, "bold", WHITE), (job, 26, "regular", C["muted"])]
        _card(cv, box, red, nm, _plane(kind, k), rows, title_size=36 if not cv.tall else 32, art_frac=0.5)
    _footer(cv, pkg, "NOAA Aircraft Operations Center / 53rd WRS")
    return cv


# ------------------------------------------------------------------ 2. urban flooding
def urban_flooding(pkg, cfg):
    cv = Canvas(cfg)
    green = (46, 160, 100)
    _header(cv, "URBAN AREA FLOODING", "WHY CITIES FLOOD FASTER", green)
    M, W = cv.M, cv.W
    x, y, w, h = M, cv.top, W - 2 * M, cv.bottom - cv.top
    cv.rect(x, y, w, h, (*SKY[:3], 0), r=14)
    # sky panel
    rrect(cv, x, y, w, h, (74, 90, 116, 255), r=14)
    cs_ = min(w * 0.16, h * 0.34)
    for fx in (0.14, 0.38, 0.62, 0.86):
        cloud(cv, x + w * fx, y + cs_ * 0.5 + 8, cs_, (146, 156, 172), None)
    gy = y + h * (0.66 if not cv.tall else 0.70)  # ground line
    split = x + w * 0.46
    rain(cv, x + 10, y + h * 0.2, x + w - 10, gy - 8, 70 if not cv.tall else 50, ln=28 if not cv.tall else 22)
    # rural (left)
    rrect(cv, x, gy, split - x, y + h - gy, SOIL, r=0)
    rrect(cv, x, gy - 14, split - x, 22, GRASS)
    for tx, th in ((0.08, 0.30), (0.17, 0.38), (0.30, 0.26), (0.38, 0.22)):
        tree(cv, x + w * tx * 0.9 / 0.46 * 0.46, gy - 8, h * th * (0.8 if not cv.tall else 0.55))
    ell(cv, x + w * 0.12, gy - 4, w * 0.045, 9, (86, 150, 210))
    ell(cv, x + w * 0.30, gy - 3, w * 0.05, 8, (86, 150, 210))
    for ax in (0.07, 0.15, 0.24, 0.33):  # rain soaking down
        arrow(cv, x + w * ax, gy + 20, x + w * ax, gy + h * 0.16, (150, 205, 255, 230), 5, 20)
    # town (right)
    rrect(cv, split, gy, x + w - split, y + h - gy, (84, 90, 104))
    rrect(cv, split, gy - 14, x + w - split, 18, (50, 54, 64))
    hw = (x + w - split) / 3.4
    for i in range(3):
        house(cv, split + 18 + i * (hw + 14), gy - 14, hw, h * (0.2 if not cv.tall else 0.14),
              body=((168, 96, 86), (214, 190, 120), (150, 110, 96))[i])
    rrect(cv, split + 6, gy - 12, x + w - split - 12, h * 0.1, (*WATER, 235), r=18)  # flooded street
    for i in range(5):
        cv.line([(split + 40 + i * (x + w - split - 100) / 4, gy + 8 + (i % 2) * 14), (split + 90 + i * (x + w - split - 100) / 4, gy + 8 + (i % 2) * 14)],
                (200, 228, 255, 150), 3)
    for ax in (0.58, 0.72, 0.86):  # runoff can't soak in
        arrow(cv, split + (x + w - split) * (ax - 0.46) / 0.54 - 28, gy + h * 0.2, split + (x + w - split) * (ax - 0.46) / 0.54 + 28, gy + h * 0.2, (150, 205, 255, 230), 5, 18)
    cv.text(split + 16, gy + h * 0.2 + 40, "WATER RUNS OFF PAVEMENT", 19, "bold", (200, 214, 232), anchor="lm")
    cv.text(x + 16, gy + h * 0.16 + 40, "SOIL AND CREEKS ABSORB RAIN", 19, "bold", (222, 206, 180), anchor="lm")
    # callouts
    bw_ = w * 0.44 if not cv.tall else w - 40
    bh_ = h * 0.25 if not cv.tall else h * 0.17
    spots = [(x + 20, y + h * 0.05, "RURAL AREAS", ["Ground soaks up rain a little easier", "More creeks and streams to absorb runoff"], green),
             ((x + w - bw_ - 20) if not cv.tall else x + 20, (y + h * 0.05) if not cv.tall else (y + h * 0.05 + bh_ + 14),
              "IN TOWN", ["Rain can't soak into the soil as easily", "Low-lying, poor drainage areas flood easily"], (232, 84, 74))]
    for cx0, cy0, ttl, lines, col in spots:
        cv.rect(cx0, cy0, bw_, bh_, (13, 21, 38, 238), r=12)
        cv.rect(cx0, cy0, 9, bh_, col)
        cv.text(cx0 + 30, cy0 + bh_ * 0.24, ttl, 36 if not cv.tall else 30, "bold", anchor="lm")
        for i, ln_ in enumerate(lines):
            cv.paragraph(cx0 + 30, cy0 + bh_ * (0.42 + 0.26 * i), ln_, 25 if not cv.tall else 22, "medium", bw_ - 56, max_lines=1, fill=C["muted"])
    _footer(cv, pkg, "NOAA / National Weather Service")
    return cv


# ------------------------------------------------------------------ 3. high-risk day damage pie
def high_risk_damage(pkg, cfg):
    cv = Canvas(cfg)
    mag = (214, 64, 232)
    _header(cv, "HIGH RISK DAYS - DAMAGE", "SOURCE: WPC  ·  EXCESSIVE RAINFALL OUTLOOK RISK CATEGORIES", mag)
    x, y, w, h = cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top
    cv.rect(x, y, w, h, C["panel"], r=14)
    R = min(h * 0.42, w * (0.2 if not cv.tall else 0.36))
    cx = x + w * (0.5 if not cv.tall else 0.5)
    cy = y + h * (0.52 if not cv.tall else 0.40)
    slices = [("HIGH", 92, mag), ("OTHER", 6, (118, 124, 138)), ("MODERATE", 2, (216, 52, 52))]
    start = -90.0
    mids = []
    for nm, pct, col in slices:
        end = start + pct * 3.6
        cv.d.pieslice([z(cx - R), z(cy - R), z(cx + R), z(cy + R)], start, end, fill=(*col, 255), outline=(13, 21, 38, 255), width=z(3))
        mids.append((nm, pct, col, math.radians((start + end) / 2)))
        start = end
    for nm, pct, col, a in mids:
        px, py = cx + math.cos(a) * R, cy + math.sin(a) * R
        if nm == "HIGH":
            lx, ly, anc = cx + R + 70, cy, "lm"
            if cv.tall:
                lx, ly, anc = cx + R * 0.2, cy + R + 56, "mm"
            ex, ey = (cx + R, cy) if not cv.tall else (cx, cy + R)
        elif nm == "OTHER":
            lx, ly, anc = cx + 40, cy - R - 44, "lm"
            ex, ey = px, py
        else:
            lx, ly, anc = cx - 150, cy - R - 12, "rm"
            ex, ey = px, py
        cv.line([(ex, ey), (lx - (12 if anc == "lm" else -12 if anc == "rm" else 0), ly)], (255, 255, 255, 200), 2.5)
        t = f"{nm} ({pct}%)"
        tw = cv.width(t, 30, "bold") + 36
        bx = lx if anc == "lm" else lx - tw if anc == "rm" else lx - tw / 2
        cv.rect(bx, ly - 26, tw, 52, (*col, 255), r=8)
        cv.text(bx + tw / 2, ly, t, 30, "bold", on(col), anchor="mm")
    # big stat
    sx, sy = (x + 40, y + h - 270) if not cv.tall else (x + 40, y + h - 250)
    cv.text(sx, sy + 70, "9/10", 120 if not cv.tall else 100, "bold", mag, anchor="ls")
    cv.text(sx + cv.width("9/10", 120 if not cv.tall else 100, "bold") + 20, sy + 70, "OF ALL", 46, "bold", anchor="ls")
    cv.text(sx, sy + 140, "FLOOD-RELATED DAMAGES", 40 if not cv.tall else 34, "bold", anchor="ls")
    cv.text(sx, sy + 190, "OCCUR ON HIGH RISK DAYS", 28 if not cv.tall else 24, "medium", C["muted"], anchor="ls")
    _footer(cv, pkg, "NOAA Weather Prediction Center")
    return cv


# ------------------------------------------------------------------ 4. flood risk levels table
def flood_risk_levels(pkg, cfg):
    cv = Canvas(cfg)
    green = (46, 160, 100)
    _header(cv, "FLOOD RISK LEVELS", "WPC EXCESSIVE RAINFALL OUTLOOK  ·  WHAT EACH LEVEL MEANS", green)
    rows = [("1 - MARGINAL", "ISOLATED", "Localized flooding, mainly in areas hit by rapid runoff", (62, 168, 96)),
            ("2 - SLIGHT", "SCATTERED", "Small streams likely affected. Poor drainage areas likely flood", (240, 208, 64)),
            ("3 - MODERATE", "NUMEROUS", "Many streams and rivers flood. Some significant flooding possible", (228, 60, 60)),
            ("4 - HIGH", "WIDESPREAD", "Severe flooding likely. Areas that don't normally flood can flood. Life threatening", (214, 64, 232))]
    x, y, w, h = cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top
    hh = 62 if not cv.tall else 0
    if not cv.tall:
        c1, c2 = w * 0.26, w * 0.2
        for cx0, t in ((x, "RISK LEVEL"), (x + c1, "COVERAGE"), (x + c1 + c2, "IMPACTS")):
            cv.text(cx0 + 24, y + hh / 2, t, 26, "bold", C["muted"], anchor="lm")
    gap = 12
    rh = (h - hh - gap * 3) / 4
    for i, (lv, cov, imp, col) in enumerate(rows):
        ry = y + hh + i * (rh + gap)
        cv.rect(x, ry, w, rh, (*col, 255), r=12)
        tc = on(col)
        if not cv.tall:
            cv.text(x + 24, ry + rh / 2, lv, 44, "bold", tc, anchor="lm", maxw=c1 - 40)
            cv.text(x + c1 + 24, ry + rh / 2, cov.title(), 42, "bold", tc, anchor="lm", maxw=c2 - 30)
            cv.paragraph(x + c1 + c2 + 24, ry, imp, 27, "medium", w - c1 - c2 - 50, max_lines=3, lh=1.22, fill=tc,
                         valign="middle", box_h=rh)
        else:
            cv.text(x + 26, ry + 52, lv, 46, "bold", tc, anchor="lm", maxw=w * 0.55)
            cv.text(x + w - 26, ry + 52, cov.title(), 38, "bold", tc, anchor="rm", maxw=w * 0.4)
            cv.paragraph(x + 26, ry + 98, imp, 28, "medium", w - 52, max_lines=3, lh=1.22, fill=tc)
    _footer(cv, pkg, "NOAA Weather Prediction Center")
    return cv


# ------------------------------------------------------------------ 5. tire pressure
def tire_pressure(pkg, cfg):
    cv = Canvas(cfg)
    blue = (88, 150, 255)
    _header(cv, "TIRE PRESSURE DROPPING", "ABOUT 1 PSI FOR EVERY 10°F DROP IN TEMPERATURE", blue)
    x, y, w, h = cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top
    pw = w * (0.64 if not cv.tall else 1.0)
    ph = h if not cv.tall else h * 0.62
    cv.rect(x, y, pw, ph, C["panel"], r=14)
    temps = [75, 65, 55, 45, 35, 25, 15]
    cols = [(255, 150, 50), (255, 205, 130), (255, 240, 120), (90, 200, 110), (120, 225, 255), (110, 120, 255), (240, 130, 235)]
    top, bot = y + 40, y + ph - 120
    lx = x + 40
    x0, x1 = x + pw * 0.28, x + pw - 70  # psi 35 -> 25 left to right
    pts = []
    for i, (t, c) in enumerate(zip(temps, cols)):
        yy = top + (bot - top) * i / (len(temps) - 1)
        psi = 35 - (75 - t) / 10.0
        xx = x0 + (x1 - x0) * (35 - psi) / 10.0
        cv.text(lx, yy, f"{t}°", 56 if not cv.tall else 48, "bold", c, anchor="lm", stroke=3)
        pts.append((xx, yy))
    cv.line(pts, (255, 255, 255, 230), 5)
    for xx, yy in pts:
        r = 26 if not cv.tall else 22
        ell(cv, xx, yy, r, r, (44, 50, 62), (210, 218, 232), 3)
        ell(cv, xx, yy, r * 0.55, r * 0.55, (176, 186, 204))
        ell(cv, xx, yy, r * 0.2, r * 0.2, (60, 66, 80))
    ex, ey = pts[-1]
    arrow(cv, ex + 190, ey, ex + 40, ey, (230, 60, 60), 9, 30)
    cv.text(ex + 200, ey, "~29 psi", 44 if not cv.tall else 36, "bold", (255, 90, 90), anchor="lm", stroke=3)
    for psi in (35, 30, 25):
        xx = x0 + (x1 - x0) * (35 - psi) / 10.0
        cv.text(xx, y + ph - 56, f"{psi} psi", 40 if not cv.tall else 32, "bold", anchor="mm")
        cv.line([(xx, bot + 36), (xx, bot + 52)], (255, 255, 255, 140), 3)
    # tips
    tx, ty, tw, th = (x + pw + 20, y, w - pw - 20, h) if not cv.tall else (x, y + ph + 18, w, h - ph - 18)
    cv.rect(tx, ty, tw, th, C["panel"], r=14)
    cv.text(tx + 28, ty + 46, "WHAT TO DO", 30, "bold", blue, anchor="lm")
    tips = [("CHECK COLD", "Check pressure in the morning, before driving."), ("USE THE DOOR STICKER", "Fill to the PSI printed on the driver's door jamb, not the tire sidewall."),
            ("EXPECT A DROP", "A 40°F swing overnight can cost 4 psi."), ("WATCH THE LIGHT", "A TPMS warning often turns on with the first cold snap.")]
    yy = ty + 100
    step = (th - 120) / len(tips)
    for hd, tx_ in tips:
        cv.text(tx + 28, yy, hd, 27, "bold", anchor="lm", maxw=tw - 56)
        cv.paragraph(tx + 28, yy + 26, tx_, 24, "regular", tw - 56, max_lines=3, lh=1.22, fill=C["muted"])
        yy += step
    _footer(cv, pkg, "General rule of thumb (about 1 psi per 10°F)")
    return cv


# ------------------------------------------------------------------ 6. freezing rain setup
def freezing_rain(pkg, cfg):
    cv = Canvas(cfg)
    ice = (120, 200, 240)
    _header(cv, "FREEZING RAIN SETUP", "RAIN THAT FREEZES ON CONTACT WITH THE GROUND", ice)
    x, y, w, h = cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top
    dw = w if cv.tall else w * 0.66
    dh = h if not cv.tall else h * 0.66
    rrect(cv, x, y, dw, dh, (74, 88, 112, 255), r=14)
    ytop, ywarm, ycold, ygr = y, y + dh * 0.14, y + dh * 0.60, y + dh * 0.76
    rrect(cv, x, ytop, dw, ywarm - ytop, (112, 122, 142, 255), r=14)  # cloud deck
    cs_ = min(dw * 0.2, (ywarm - ytop) * 1.7)
    for fx in (0.2, 0.5, 0.8):
        cloud(cv, x + dw * fx, ytop + cs_ * 0.5 + 6, cs_, (178, 186, 202), None)
    cv.rect(x, ywarm, dw, ycold - ywarm, (196, 148, 40, 255))  # warm layer
    cv.rect(x, ycold, dw, ygr - ycold, (66, 84, 196, 255))     # sub-freezing layer
    cv.text(x + dw / 2, (ywarm + ycold) / 2 - 18, "ABOVE 32°F", 54 if not cv.tall else 44, "bold", anchor="mm")
    cv.text(x + dw / 2, (ywarm + ycold) / 2 + 36, "SNOW MELTS INTO RAIN", 26 if not cv.tall else 22, "bold", (255, 244, 214), anchor="mm")
    cv.text(x + dw / 2, (ycold + ygr) / 2 - 12, "BELOW 32°F", 44 if not cv.tall else 36, "bold", anchor="mm")
    cv.text(x + dw / 2, (ycold + ygr) / 2 + 28, "RAINDROPS SUPERCOOL BUT STAY LIQUID", 22 if not cv.tall else 18, "bold", (214, 224, 255), anchor="mm")
    rain(cv, x + 14, ytop + dh * 0.12, x + dw - 14, ygr - 6, 90 if not cv.tall else 60, (190, 220, 250, 210), ln=34 if not cv.tall else 26, w=3)
    rrect(cv, x, ygr, dw, y + dh - ygr, (58, 96, 72, 255))  # ground
    rrect(cv, x, ygr, dw, 20, (214, 238, 252, 255))        # ice glaze
    for i in range(16):
        ix = x + 20 + i * (dw - 40) / 15
        poly(cv, [(ix - 6, ygr + 18), (ix + 6, ygr + 18), (ix, ygr + 18 + 22 + (i % 3) * 8)], (214, 238, 252, 255))
    cv.text(x + dw / 2, ygr + (y + dh - ygr) / 2 + 6, "FREEZING RAIN", 58 if not cv.tall else 46, "bold", (232, 246, 255), anchor="mm", stroke=4,
            stroke_fill=(30, 60, 90))
    # explainer
    ex, ey, ew, eh = (x + dw + 20, y, w - dw - 20, h) if not cv.tall else (x, y + dh + 18, w, h - dh - 18)
    cv.rect(ex, ey, ew, eh, C["panel"], r=14)
    cv.text(ex + 28, ey + 46, "HOW IT HAPPENS", 30, "bold", ice, anchor="lm")
    steps = [("1", "Warm air aloft", "Snow falls into a layer above 32°F and melts into rain."),
             ("2", "Cold air at the surface", "A shallow layer below 32°F cools the drops without freezing them."),
             ("3", "Glaze on contact", "The supercooled drops freeze on roads, trees and power lines.")]
    yy = ey + 100
    step = (eh - 120) / 3
    for n, hd, tx_ in steps:
        ell(cv, ex + 52, yy + 14, 22, 22, (*ice, 255))
        cv.text(ex + 52, yy + 14, n, 26, "bold", INK, anchor="mm")
        cv.text(ex + 90, yy + 6, hd, 30, "bold", anchor="lm", maxw=ew - 120)
        cv.paragraph(ex + 90, yy + 36, tx_, 25, "regular", ew - 118, max_lines=4, lh=1.22, fill=C["muted"])
        yy += step
    _footer(cv, pkg, "NOAA / National Weather Service")
    return cv


# ------------------------------------------------------------------ 7. wind impacts
def _art_leaves(cv, box):
    x, y, w, h = box
    cx, cy, s = x + w / 2, y + h / 2, min(w, h)
    rrect(cv, cx - s * 0.04, cy + s * 0.05, s * 0.08, s * 0.38, (104, 76, 54))
    for dx, dy, r in ((-0.18, -0.02, 0.22), (0.14, -0.04, 0.24), (0.0, -0.2, 0.26), (-0.02, 0.0, 0.2)):
        ell(cv, cx + dx * s, cy + dy * s, r * s, r * s, (82, 160, 88))
    for dx, dy in ((0.34, -0.02), (0.42, 0.12), (0.30, 0.2)):
        poly(cv, rot([(cx + dx * s, cy + dy * s), (cx + dx * s + s * 0.09, cy + dy * s - s * 0.03), (cx + dx * s + s * 0.05, cy + dy * s + s * 0.06)], cx + dx * s, cy + dy * s, dx * 200), (110, 190, 100))
    for k in range(3):
        cv.line([(cx - s * 0.46, cy - s * 0.1 + k * s * 0.1), (cx - s * 0.28 + k * s * 0.03, cy - s * 0.1 + k * s * 0.1)], (160, 205, 255, 200), 4)


def _art_chair(cv, box):
    x, y, w, h = box
    cx, cy, s = x + w / 2, y + h / 2, min(w, h)
    gy = cy + s * 0.34
    cv.line([(cx - s * 0.46, gy), (cx + s * 0.46, gy)], (150, 200, 150, 255), 5)
    # table
    rrect(cv, cx - s * 0.42, gy - s * 0.28, s * 0.4, s * 0.04, (150, 170, 190))
    cv.line([(cx - s * 0.22, gy - s * 0.24), (cx - s * 0.22, gy)], (150, 170, 190), 6)
    # toppling chair
    ch = [(cx + 0.02 * s, gy - 0.02 * s), (cx + 0.32 * s, gy - 0.02 * s), (cx + 0.32 * s, gy - 0.1 * s), (cx + 0.02 * s, gy - 0.1 * s)]
    back = [(cx + 0.02 * s, gy - 0.1 * s), (cx + 0.07 * s, gy - 0.1 * s), (cx + 0.07 * s, gy - 0.36 * s), (cx + 0.02 * s, gy - 0.36 * s)]
    pivot = (cx + 0.32 * s, gy)
    for pts in (ch, back):
        poly(cv, rot(pts, *pivot, 28), (186, 160, 128), (120, 100, 80), 2)
    for k in range(3):
        cv.line([(cx - s * 0.46, cy - s * 0.3 + k * s * 0.09), (cx - s * 0.26, cy - s * 0.3 + k * s * 0.09)], (160, 205, 255, 200), 4)


def _art_branch(cv, box):
    x, y, w, h = box
    cx, cy, s = x + w / 2, y + h / 2, min(w, h)
    poly(cv, [(cx - s * 0.1, cy + s * 0.42), (cx + s * 0.1, cy + s * 0.42), (cx + s * 0.07, cy - s * 0.4), (cx - s * 0.07, cy - s * 0.4)], (104, 76, 54))
    poly(cv, [(cx - s * 0.07, cy - s * 0.12), (cx - s * 0.06, cy + s * 0.0), (cx - s * 0.32, cy + s * 0.22), (cx - s * 0.37, cy + s * 0.14)], (130, 96, 68))
    for dx, dy in ((-0.34, 0.2), (-0.26, 0.28), (-0.4, 0.28)):
        ell(cv, cx + dx * s, cy + dy * s, s * 0.08, s * 0.06, (82, 160, 88))
    for dx, dy, r in ((0.0, -0.4, 0.18), (0.16, -0.32, 0.14), (-0.14, -0.32, 0.14)):
        ell(cv, cx + dx * s, cy + dy * s, r * s, r * s, (82, 160, 88))
    for k in range(3):
        cv.line([(cx + s * 0.28, cy - s * 0.2 + k * s * 0.1), (cx + s * 0.48, cy - s * 0.2 + k * s * 0.1)], (160, 205, 255, 200), 4)


def _art_roof(cv, box):
    x, y, w, h = box
    cx, cy, s = x + w / 2, y + h / 2, min(w, h)
    top, bot = cy - s * 0.3, cy + s * 0.3
    poly(cv, [(cx - s * 0.5, bot), (cx - s * 0.18, top), (cx + s * 0.18, top), (cx + s * 0.5, bot)], (186, 112, 84), (120, 70, 54), 2)
    for r in range(4):
        yy = top + (bot - top) * (r + 1) / 4
        fx = (yy - top) / (bot - top)
        xl, xr = cx - s * (0.18 + 0.32 * fx), cx + s * (0.18 + 0.32 * fx)
        cv.line([(xl, yy), (xr, yy)], (120, 70, 54, 200), 2.5)
    poly(cv, [(cx - s * 0.08, cy - s * 0.02), (cx + s * 0.12, cy - s * 0.02), (cx + s * 0.14, cy + s * 0.1), (cx - s * 0.1, cy + s * 0.1)], (54, 44, 44))
    for dx, dy, a in ((0.22, -0.34, 20), (0.34, -0.2, -15), (0.12, -0.44, 35)):
        sx, sy = cx + dx * s, cy + dy * s
        poly(cv, rot([(sx - s * 0.06, sy - s * 0.035), (sx + s * 0.06, sy - s * 0.035), (sx + s * 0.06, sy + s * 0.035), (sx - s * 0.06, sy + s * 0.035)], sx, sy, a), (186, 112, 84), (120, 70, 54), 2)
    for k in range(2):
        cv.line([(cx - s * 0.5, cy - s * 0.4 + k * s * 0.1), (cx - s * 0.3, cy - s * 0.4 + k * s * 0.1)], (160, 205, 255, 200), 4)


def wind_impacts(pkg, cfg):
    cv = Canvas(cfg)
    gold = (240, 170, 50)
    _header(cv, "WIND IMPACTS", "WHAT DIFFERENT WIND SPEEDS CAN DO", gold)
    data = [("20 MPH", "Leaves and small twigs blown around", _art_leaves, (240, 205, 60)),
            ("30 MPH", "Lawn furniture topples over", _art_chair, (245, 150, 45)),
            ("40 MPH", "Branches fall off trees", _art_branch, (228, 62, 62)),
            ("50 MPH", "Shingles and siding ripped off", _art_roof, (160, 82, 210))]
    for box, (mph, txt, art, col) in zip(_boxes(cv, 4), data):
        _card(cv, box, col, mph, art, [(txt.upper(), 30 if not cv.tall else 34, "bold", WHITE)], title_size=52 if not cv.tall else 46, art_frac=0.6, band=92)
    _footer(cv, pkg, "National Weather Service wind impact guidance")
    return cv


# ------------------------------------------------------------------ 8. how hail forms
def how_hail_forms(pkg, cfg):
    cv = Canvas(cfg)
    blue = (90, 150, 255)
    _header(cv, "HOW HAIL FORMS", "UPDRAFTS AND DOWNDRAFTS IN A THUNDERSTORM", blue)
    x, y, w, h = cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top
    dw = w * (0.66 if not cv.tall else 1.0)
    dh = h if not cv.tall else h * 0.64
    rrect(cv, x, y, dw, dh, (86, 128, 190, 255), r=14)
    gy = y + dh * 0.86
    rrect(cv, x, gy, dw, y + dh - gy, (70, 118, 80, 255), r=0)
    ccx, ccy, s = x + dw * 0.5, y + dh * 0.34, dw * 0.52
    cloud(cv, ccx - s * 0.1, ccy + s * 0.12, s * 0.9, (222, 230, 242), None)
    cloud(cv, ccx + s * 0.18, ccy - s * 0.02, s * 0.8, (234, 240, 248), None)
    cloud(cv, ccx, ccy - s * 0.2, s * 0.62, (246, 249, 252), None)
    fl = y + dh * 0.5  # freezing level
    for i in range(0, int(dw), 36):
        cv.line([(x + i + 6, fl), (x + i + 26, fl)], (255, 90, 110, 255), 4)
    cv.text(x + dw - 16, fl - 16, "FREEZING LEVEL", 22 if not cv.tall else 18, "bold", (255, 120, 135), anchor="rs", stroke=3, stroke_fill=(40, 50, 90))
    arrow(cv, ccx + s * 0.02, fl + dh * 0.22, ccx + s * 0.02, ccy - s * 0.2, (255, 190, 80), 14, 40)  # updraft
    cv.text(ccx + s * 0.1, fl + dh * 0.2, "UPDRAFT", 22 if not cv.tall else 18, "bold", (255, 214, 140), anchor="lm", stroke=3, stroke_fill=(70, 50, 20))
    arrow(cv, ccx - s * 0.46, ccy + s * 0.04, ccx - s * 0.62, ccy + s * 0.5 + dh * 0.08, (60, 90, 240), 14, 40)  # downdraft
    cv.text(ccx - s * 0.62, fl - 14, "DOWNDRAFT", 22 if not cv.tall else 18, "bold", (170, 200, 255), anchor="rm", stroke=3, stroke_fill=(20, 30, 90))
    for dx in (-0.06, 0.12):  # raindrops below freezing level
        poly(cv, [(ccx + dx * s, fl + dh * 0.1), (ccx + dx * s - 8, fl + dh * 0.1 + 18), (ccx + dx * s + 8, fl + dh * 0.1 + 18)], (130, 195, 250))
        ell(cv, ccx + dx * s, fl + dh * 0.1 + 20, 9, 9, (130, 195, 250))
    for (hx, hy, r) in ((-0.1, -0.18, 15), (0.2, -0.12, 17), (0.06, -0.03, 14), (0.3, -0.04, 12)):  # hailstones in the loop
        ell(cv, ccx + hx * s, ccy + hy * s, r, r, (206, 212, 222), (140, 150, 168), 2)
    for (lx0, ly0) in ((-0.16, -0.24), (0.16, -0.18)):  # circulation loops (arc + arrowhead)
        lr = s * 0.1
        lcx, lcy = ccx + lx0 * s, ccy + ly0 * s
        cv.d.arc([z(lcx - lr), z(lcy - lr), z(lcx + lr), z(lcy + lr)], 40, 330, fill=(240, 200, 40, 255), width=z(5))
        ax_, ay_ = lcx + lr * math.cos(math.radians(40)), lcy + lr * math.sin(math.radians(40))
        poly(cv, [(ax_ + 12, ay_ - 4), (ax_ - 10, ay_ - 12), (ax_ - 2, ay_ + 12)], (240, 200, 40))
    for (hx, hy, r) in ((-0.62, 0.52, 14), (-0.55, 0.64, 18), (-0.7, 0.6, 11)):  # falling hail
        ell(cv, ccx + hx * s, ccy + hy * s + dh * 0.04, r, r, (232, 236, 244), (150, 160, 178), 2)
    # explainer
    ex, ey, ew, eh = (x + dw + 20, y, w - dw - 20, h) if not cv.tall else (x, y + dh + 18, w, h - dh - 18)
    cv.rect(ex, ey, ew, eh, C["panel"], r=14)
    cv.text(ex + 28, ey + 46, "HOW IT HAPPENS", 30, "bold", blue, anchor="lm")
    steps = [("1", "Updraft lifts raindrops", "Strong rising air carries water above the freezing level, where it freezes."),
             ("2", "Stones grow", "The frozen drops circulate in the storm, adding a layer of ice each trip."),
             ("3", "Hail falls", "Once too heavy for the updraft, the hailstone drops in the cold downdraft.")]
    yy = ey + 100
    step = (eh - 120) / 3
    for n, hd, tx_ in steps:
        ell(cv, ex + 52, yy + 14, 22, 22, (*blue, 255))
        cv.text(ex + 52, yy + 14, n, 26, "bold", INK, anchor="mm")
        cv.text(ex + 90, yy + 6, hd, 30, "bold", anchor="lm", maxw=ew - 120)
        cv.paragraph(ex + 90, yy + 36, tx_, 25, "regular", ew - 118, max_lines=4, lh=1.22, fill=C["muted"])
        yy += step
    _footer(cv, pkg, "NOAA / National Weather Service")
    return cv


# ------------------------------------------------------------------ 9. severe weather risk levels
def severe_risk_levels(pkg, cfg):
    cv = Canvas(cfg)
    orange = (240, 140, 40)
    _header(cv, "SEVERE WEATHER RISK LEVELS", "WHAT SHOULD YOU DO?", orange)
    data = [("MARGINAL", (76, 175, 96), "NO", "ONCE OR TWICE"), ("SLIGHT", (246, 208, 60), "POSSIBLY", "EVERY FEW HOURS"),
            ("ENHANCED", (240, 130, 40), "PROBABLY", "EVERY HOUR"), ("MODERATE", (228, 62, 62), "YES", "CONSTANTLY"),
            ("HIGH", (214, 64, 232), "YES", "CONSTANTLY")]
    for box, (nm, col, plans, check) in zip(_boxes(cv, 5, gap=14), data):
        big = col if lum(col) > 100 else col
        rows = [("SHOULD I CANCEL MY PLANS?", 26 if not cv.tall else 28, "bold", C["muted"]), (plans, 62 if not cv.tall else 60, "bold", (*big, 255)),
                ("", 60, "regular", C["muted"]),
                ("HOW OFTEN SHOULD I CHECK THE WEATHER?", 26 if not cv.tall else 28, "bold", C["muted"]), (check, 50 if not cv.tall else 52, "bold", (*big, 255))]
        _card(cv, box, col, nm, None, rows, title_size=36 if not cv.tall else 34, band=80)
    _footer(cv, pkg, "NOAA Storm Prediction Center categories")
    return cv


# ------------------------------------------------------------------ 10. tornado safety
def _art_house(cv, box):
    x, y, w, h = box
    cx, cy, s = x + w / 2, y + h / 2, min(w, h * 1.25)
    gl = cy + s * 0.02
    poly(cv, [(cx - s * 0.42, cy - s * 0.2), (cx, cy - s * 0.4), (cx + s * 0.42, cy - s * 0.2)], (110, 118, 132))
    rrect(cv, cx - s * 0.38, cy - s * 0.2, s * 0.76, s * 0.22, (196, 170, 140))
    for fx in (-0.3, -0.08, 0.14, 0.28):
        rrect(cv, cx + fx * s, cy - s * 0.15, s * 0.08, s * 0.1, (232, 238, 246), r=2)
    rrect(cv, cx - s * 0.38, gl, s * 0.76, s * 0.3, (78, 64, 52))  # basement
    rrect(cv, cx - s * 0.12, gl + s * 0.05, s * 0.3, s * 0.2, (30, 36, 48), r=4, outline=(80, 220, 120), ow=4)
    cv.text(cx + s * 0.03, gl + s * 0.15, "SAFE", max(14, s * 0.07), "bold", (110, 235, 140), anchor="mm")
    cv.line([(cx - s * 0.5, gl), (cx + s * 0.5, gl)], (150, 200, 150, 255), 4)


def _art_mobile(cv, box):
    x, y, w, h = box
    cx, cy, s = x + w / 2, y + h / 2, min(w, h * 1.7)
    rrect(cv, cx - s * 0.42, cy - s * 0.1, s * 0.84, s * 0.2, (170, 176, 188), r=4)
    for fx in (-0.34, -0.18, 0.06, 0.2):
        rrect(cv, cx + fx * s, cy - s * 0.06, s * 0.08, s * 0.08, (206, 226, 252), r=2)
    cv.line([(cx - s * 0.46, cy + s * 0.1), (cx + s * 0.46, cy + s * 0.1)], (110, 70, 54, 255), 6)
    ell(cv, cx + s * 0.34, cy - s * 0.3, s * 0.1, s * 0.1, (230, 60, 60))
    cv.line([(cx + s * 0.3, cy - s * 0.34), (cx + s * 0.38, cy - s * 0.26)], WHITE, 5)
    cv.line([(cx + s * 0.38, cy - s * 0.34), (cx + s * 0.3, cy - s * 0.26)], WHITE, 5)
    arrow(cv, cx - s * 0.1, cy + s * 0.24, cx + s * 0.34, cy + s * 0.24, (255, 120, 90), 7, 22)


def _art_multi(cv, box):
    x, y, w, h = box
    cx, cy, s = x + w / 2, y + h / 2, min(w * 0.8, h)
    bw, bh = s * 0.5, s * 0.8
    bx, by = cx - bw / 2, cy - bh / 2
    rrect(cv, bx, by, bw, bh, (176, 186, 202), r=3)
    for r in range(5):
        for c in range(3):
            rrect(cv, bx + bw * (0.1 + 0.3 * c), by + bh * (0.06 + 0.16 * r), bw * 0.2, bh * 0.1, (120, 214, 214), r=2)
    rrect(cv, bx + bw * 0.04, by + bh * 0.86, bw * 0.92, bh * 0.1, (30, 36, 48), r=3, outline=(80, 220, 120), ow=4)
    cv.text(cx, by + bh * 0.91, "HALLWAY", max(12, s * 0.06), "bold", (110, 235, 140), anchor="mm")


def tornado_safety(pkg, cfg):
    cv = Canvas(cfg)
    red = (222, 60, 56)
    _header(cv, "TORNADO SAFETY", "WHERE TO GO DURING A TORNADO WARNING", red)
    data = [("HOUSE", _art_house, "Go to the basement or an interior room on the lowest floor with no windows"),
            ("MOBILE HOME", _art_mobile, "Get out! Go to a sturdy shelter or building nearby"),
            ("MULTI-STORY", _art_multi, "Interior hallway on the lowest floor, away from windows")]
    for box, (ttl, art, txt) in zip(_boxes(cv, 3), data):
        _card(cv, box, red, ttl, art, [(txt, 34 if not cv.tall else 34, "bold", WHITE)], title_size=44 if not cv.tall else 38, art_frac=0.52, band=92)
    _footer(cv, pkg, "National Weather Service")
    return cv


# ------------------------------------------------------------------ registry
MAKERS = [("safety_hurricane_hunters", hurricane_hunters), ("safety_urban_flooding", urban_flooding),
          ("safety_high_risk_damage", high_risk_damage), ("safety_flood_risk_levels", flood_risk_levels),
          ("safety_tire_pressure", tire_pressure), ("safety_freezing_rain", freezing_rain), ("safety_wind_impacts", wind_impacts),
          ("safety_how_hail_forms", how_hail_forms), ("safety_severe_risk_levels", severe_risk_levels),
          ("safety_tornado_safety", tornado_safety)]


def safety_graphics(pkg, cfg):
    want = cfg.get("safety_only")  # optional list of names to make
    out = []
    for name, fn in MAKERS:
        if want and name not in want:
            continue
        out.append((name, fn(pkg, cfg)))
    return out or None
