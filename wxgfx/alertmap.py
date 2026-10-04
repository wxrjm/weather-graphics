"""Per-alert graphic: county stencil map with affected counties shaded in the NWS hazard
color (plus the warning polygon when there is one), and a side panel with the
counties and a plain-language summary of the alert text."""
import math
from PIL import Image, ImageDraw

from . import alertinfo
from .theme import Canvas, C, font, z

STENCIL = (38, 55, 84, 255)
STENCIL_EDGE = (98, 120, 152, 255)
# (name, lat, lon, tier) — tier 1 = larger label, placed first; overlapping labels are dropped
DEFAULT_CITIES = [
    ("Virginia Beach", 36.84, -75.98, 1), ("Norfolk", 36.85, -76.29, 1), ("Chesapeake", 36.72, -76.24, 1),
    ("Hampton", 37.03, -76.35, 1), ("Newport News", 37.07, -76.49, 2, "above"), ("Portsmouth", 36.84, -76.31, 1),
    ("Suffolk", 36.73, -76.58, 1), ("Williamsburg", 37.27, -76.71, 1), ("Richmond", 37.54, -77.44, 1),
    ("Elizabeth City", 36.30, -76.22, 1), ("Salisbury", 38.36, -75.60, 1), ("Ocean City", 38.34, -75.08, 1),
    ("Nags Head", 35.96, -75.62, 1),
    ("Smithfield", 36.98, -76.63, 2), ("Yorktown", 37.24, -76.51, 2), ("Gloucester", 37.41, -76.53, 2),
    ("Mathews", 37.44, -76.32, 2), ("West Point", 37.53, -76.80, 2), ("Franklin", 36.68, -76.92, 2),
    ("Wakefield", 36.97, -76.99, 2), ("Emporia", 36.69, -77.54, 2), ("Petersburg", 37.23, -77.40, 2),
    ("Tappahannock", 37.93, -76.86, 2), ("Kilmarnock", 37.71, -76.38, 2), ("Cape Charles", 37.27, -76.02, 2),
    ("Exmore", 37.53, -75.83, 2), ("Onancock", 37.71, -75.75, 2), ("Chincoteague", 37.93, -75.38, 2),
    ("Pocomoke City", 38.08, -75.57, 2), ("Moyock", 36.52, -76.18, 2), ("Currituck", 36.45, -76.02, 2),
    ("Corolla", 36.38, -75.83, 2), ("Kill Devil Hills", 36.03, -75.68, 2), ("Hertford", 36.19, -76.47, 2),
    ("Edenton", 36.06, -76.61, 2), ("Gatesville", 36.40, -76.75, 2), ("Ahoskie", 36.29, -76.98, 2),
    ("Windsor", 35.99, -76.95, 2), ("Courtland", 36.72, -77.06, 2), ("Waverly", 37.04, -77.10, 2),
    ("Dover", 39.16, -75.52, 2), ("Easton", 38.77, -76.08, 2), ("Cambridge", 38.56, -76.08, 2),
]
HOME_BOX = (-76.95, -75.85, 36.45, 37.35)  # Hampton Roads core kept in view for context


def _bbox_of(fips_list, poly):
    cs = alertinfo.counties()
    xs, ys = [], []
    for f in fips_list:
        c = cs.get(f)
        if not c:
            continue
        for p in c["polys"]:
            for x, y in p[0]:
                xs.append(x); ys.append(y)
    for x, y in poly or []:
        xs.append(x); ys.append(y)
    return (min(xs), max(xs), min(ys), max(ys)) if xs else None


def _view(alert, pw, ph, cfg):
    """Zoom to the alert (+ the home area), padded, at the panel's aspect ratio."""
    home = tuple(cfg.get("map_home_box") or HOME_BOX)
    b = _bbox_of(alert["fips"], alert.get("polygon"))
    w, e, s, n = home if not b else (min(b[0], home[0]), max(b[1], home[1]), min(b[2], home[2]), max(b[3], home[3]))
    cx, cy = (w + e) / 2, (s + n) / 2
    k = math.cos(math.radians(cy))
    span_y = max((n - s) * 1.25, (e - w) * k * 1.25 * ph / pw, 1.5)
    span_x = span_y * pw / ph / k
    return cx - span_x / 2, cx + span_x / 2, cy - span_y / 2, cy + span_y / 2


KEEP_OUT = []  # (x0, y0, x1, y1) in canvas px where labels mustn't go (set by full-screen layouts)


def draw_cities(d, proj, W_, H_, cfg, bottom_pad=70, cities=None):
    """Text-only city labels centered on the city's location (no dots). If a label would collide
    with one already placed it nudges slightly up/down, otherwise it's dropped (bigger cities first)."""
    placed = []
    fonts = {1: font("bold", 16), 2: font("medium", 13)}
    abbr = cfg.get("abbreviations") or {}
    for city in cities or cfg.get("map_cities") or DEFAULT_CITIES:
        name, la, lo = city[:3]
        name = abbr.get(name, name).upper()
        tier = city[3] if len(city) > 3 else 1
        f = fonts.get(tier, fonts[2])
        x, y = proj(lo, la)
        tw = d.textlength(name, font=f)
        th = z(17 if tier == 1 else 14)
        spot = None
        for dy in (0, -th * 0.9, th * 0.9):  # centered on the city first
            box = (x - tw / 2 - z(3), y + dy - th / 2 - z(2), x + tw / 2 + z(3), y + dy + th / 2 + z(2))
            blocked = placed + [tuple(z(v) for v in k) for k in KEEP_OUT]
            if box[0] > z(6) and box[2] < W_ - z(6) and box[1] > z(6) and box[3] < H_ - z(bottom_pad) and \
                    not any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1] for b in blocked):
                spot = (x, y + dy, box)
                break
        if not spot:
            continue
        placed.append(spot[2])
        d.text(spot[:2], name, font=f, fill=(255, 255, 255, 255), anchor="mm",
               stroke_width=z(2.5), stroke_fill=(13, 21, 38, 255))


def draw_map(alert, pw, ph, cfg):
    W_, H_ = z(pw), z(ph)
    lay = Image.new("RGBA", (W_, H_), (17, 27, 47, 255))  # water
    d = ImageDraw.Draw(lay, "RGBA")
    w, e, s, n = _view(alert, pw, ph, cfg)
    proj = lambda x, y: ((x - w) / (e - w) * W_, (n - y) / (n - s) * H_)
    col = alertinfo.hex_rgb(alert["color"])
    hit = set(alert["fips"])
    focus = set(cfg.get("alert_counties") or [])
    # independent cities are holes inside counties, so draw counties first, then cities on top
    cs = sorted((c for c in alertinfo.counties().values() if alertinfo.in_view(c, w, e, s, n)),
                key=lambda c: c["lsad"].lower() == "city")
    lw = max(1, z(1.1))
    mix = lambda a, b, t: tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3)) + (255,)
    for c in cs:
        base = (48, 68, 102, 255) if c["fips"] in focus else STENCIL
        fill = mix(base, col, 0.86) if c["fips"] in hit else base
        for p in c["polys"]:
            d.polygon([proj(x, y) for x, y in p[0]], fill=fill)
    for c in cs:  # county lines on top
        for p in c["polys"]:
            pts = [proj(x, y) for x, y in p[0]]
            d.line(pts + [pts[0]], fill=STENCIL_EDGE if c["fips"] not in hit else (255, 255, 255, 170), width=lw)
    if alert.get("polygon"):  # storm-based warning polygon
        pts = [proj(x, y) for x, y in alert["polygon"]]
        ov = Image.new("RGBA", lay.size, (0, 0, 0, 0))
        ImageDraw.Draw(ov).polygon(pts, fill=(*col, 120))
        lay.alpha_composite(ov)
        d = ImageDraw.Draw(lay, "RGBA")
        d.line(pts + [pts[0]], fill=(255, 255, 255, 255), width=z(7))
        d.line(pts + [pts[0]], fill=(*col, 255), width=z(4))
    draw_cities(d, proj, W_, H_, cfg)
    return lay


def _paste_rounded(cv, lay, x, y, r=18):
    mask = Image.new("L", lay.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, lay.width - 1, lay.height - 1], radius=z(r), fill=255)
    base = cv.img.convert("RGBA")
    region = Image.new("RGBA", lay.size, (0, 0, 0, 0))
    region.paste(lay, (0, 0), mask)
    base.alpha_composite(region, (z(x), z(y)))
    cv.img = base.convert("RGB")
    cv.d = ImageDraw.Draw(cv.img, "RGBA")


def _side_panel(cv, alert, x, y, w, h, col, abbr=None):
    areas = alertinfo.areas_text(alert)
    if isinstance(areas, dict) and abbr:
        areas = {st: [abbr.get(n, n) for n in names] for st, names in areas.items()}
    if isinstance(areas, dict):
        area_lines = [f"{st}: " + ", ".join(names) for st, names in areas.items()]
    else:
        area_lines = [areas]
    rows = alert.get("summary") or []
    ncol = 2 if w > 900 else 1  # wide, short panel under a stacked map: WHAT/WHEN/... in two columns
    cw = (w - 52 - (36 if ncol == 2 else 0)) / ncol
    pairs = [rows[i:i + ncol] for i in range(0, len(rows), ncol)]

    def rh(r, size):
        return 32 + len(cv.wrap(r["text"], size, "regular", cw - 20)) * size * 1.28

    for size in range(28, 15, -1):  # largest body size that fits everything
        need = 40 + sum(len(cv.wrap(ln, size, "medium", w - 52)) * size * 1.26 for ln in area_lines) + 40
        need += sum(max(rh(r, size) for r in pr) + 18 for pr in pairs)
        if need <= h:
            break
    cv.rect(x, y, w, h, C["panel"], r=18)
    cy = y + 24
    cv.text(x + 26, cy, "AREAS INCLUDED", 22, "bold", col, anchor="lt")
    cy += 34
    for ln in area_lines:
        for t in cv.wrap(ln, size, "medium", w - 52):
            cv.text(x + 26, cy, t, size, "medium", anchor="lt")
            cy += size * 1.26
    cy += 14
    cv.line([(x + 26, cy), (x + w - 26, cy)], (255, 255, 255, 60), 1.5)
    cy += 18
    for pr in pairs:
        block = max(rh(r, size) for r in pr)
        if cy + block > y + h - 8:
            break
        for c, r in enumerate(pr):
            bx = x + 26 + c * (cw + 36)
            cv.rect(bx, cy, 6, rh(r, size) - 4, col)
            cv.text(bx + 20, cy, r["label"], 21, "bold", col, anchor="lt")
            for i, t in enumerate(cv.wrap(r["text"], size, "regular", cw - 20)):
                cv.text(bx + 20, cy + 32 + i * size * 1.28, t, size, "regular", anchor="lt")
        cy += block + 18


def alert_graphic(alert, pkg, cfg):
    # tolerate hand-written alerts in manual mode: only "event" and "fips" are really needed
    alert.setdefault("fips", [])
    alert.setdefault("color", "#%02X%02X%02X" % alertinfo.color_for(alert["event"]))
    alert.setdefault("ends_label", "")
    alert.setdefault("summary", [{"label": "WHAT", "text": alert.get("headline", "")}] if alert.get("headline") else [])
    cv = Canvas(cfg)
    col = alertinfo.hex_rgb(alert["color"])
    cv.header(alert["event"], alert["ends_label"], rule_color=col)
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    _paste_rounded(cv, draw_map(alert, mw, mh, cfg), mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(*col, 255), width=z(3))
    # legend chip
    lw = cv.width(alert["event"].upper(), 22, "bold") + 64
    cv.rect(mx + 18, my + mh - 58, lw, 42, (13, 21, 38, 225), r=10)
    cv.rect(mx + 30, my + mh - 48, 22, 22, (*col, 255), r=4)
    cv.text(mx + 62, my + mh - 37, alert["event"].upper(), 22, "bold", anchor="lm")
    _side_panel(cv, alert, px, py, pw_, ph_, col, cfg.get("abbreviations"))
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "National Weather Service"
    cv.footer(pkg, show_location=False, source=src)
    return cv


def alert_maps(pkg, cfg):
    """One graphic per active alert (capped by config 'alert_graphics_max')."""
    out = []
    for i, a in enumerate((pkg.get("alerts") or [])[: cfg.get("alert_graphics_max", 6)]):
        slug = "".join(ch if ch.isalnum() else "_" for ch in a["event"].lower()).strip("_")
        out.append((f"alert_{i + 1}_{slug}", alert_graphic(a, pkg, cfg)))
    return out or None
