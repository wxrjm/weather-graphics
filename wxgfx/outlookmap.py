"""Outlook graphics on the county stencil: SPC convective outlook, WPC Excessive Rainfall
Outlook and WPC QPF. Map on the left (same stencil as the alert maps), side panel on the right
with the Hampton Roads-area risk, what it means, and a quick list of local cities."""
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageChops, ImageDraw

from . import alertinfo, fullscreen, outlooks, spchazards
from .alertmap import STENCIL, STENCIL_EDGE, _paste_rounded, draw_cities
from .theme import Canvas, C, font, z

VIEW_BOX = (-79.2, -74.4, 35.3, 38.9)  # w, e, s, n -- southeast VA, NE NC, Eastern Shore, S MD
POINTS = [  # local risk list in the side panel
    ("Norfolk", 36.85, -76.29), ("VA Beach", 36.84, -75.98), ("Chesapeake", 36.72, -76.24),
    ("Suffolk", 36.73, -76.58), ("Peninsula", 37.07, -76.45), ("Williamsburg", 37.27, -76.71),
    ("Eastern Shore", 37.55, -75.82), ("Eliz. City", 36.30, -76.22), ("Outer Banks", 36.00, -75.66),
    ("Richmond", 37.54, -77.44),
]


STATE_VIEW = (-84.3, -75.3, 33.8, 39.5)  # Virginia + North Carolina
STATE_CITIES = [  # (name, lat, lon, tier)
    ("Norfolk", 36.85, -76.29, 1), ("Richmond", 37.54, -77.44, 1), ("Raleigh", 35.78, -78.64, 1),
    ("Charlotte", 35.23, -80.84, 1), ("Roanoke", 37.27, -79.94, 1), ("Greensboro", 36.07, -79.79, 1),
    ("Wilmington", 34.23, -77.94, 1), ("Asheville", 35.60, -82.55, 1), ("Elizabeth City", 36.30, -76.22, 2),
    ("Nags Head", 35.96, -75.62, 2), ("Charlottesville", 38.03, -78.48, 2), ("Lynchburg", 37.41, -79.14, 2),
    ("Fredericksburg", 38.30, -77.46, 2), ("Washington", 38.90, -77.04, 2), ("Winchester", 39.18, -78.16, 2),
    ("Blacksburg", 37.23, -80.41, 2), ("Bristol", 36.60, -82.19, 2), ("Danville", 36.59, -79.40, 2),
    ("Greenville", 35.61, -77.37, 2), ("Fayetteville", 35.05, -78.88, 2), ("Morehead City", 34.72, -76.73, 2),
    ("Salisbury", 38.36, -75.60, 2), ("Emporia", 36.69, -77.54, 2), ("Williamsburg", 37.27, -76.71, 2),
]
DMA_POINTS = [  # Hampton Roads DMA locations for the statewide map's side panel
    ("Norfolk", 36.85, -76.29), ("VA Beach", 36.80, -76.05), ("Chesapeake", 36.68, -76.30),
    ("Portsmouth", 36.84, -76.33), ("Suffolk", 36.73, -76.58), ("Hampton", 37.03, -76.35),
    ("Newport News", 37.07, -76.49), ("Williamsburg", 37.27, -76.71), ("Gloucester", 37.41, -76.53),
    ("Smithfield", 36.98, -76.63), ("Franklin", 36.68, -76.92), ("Eastern Shore", 37.55, -75.82),
    ("Eliz. City", 36.30, -76.22), ("Currituck", 36.45, -76.02), ("Outer Banks", 36.00, -75.66),
    ("Edenton", 36.06, -76.61),
]


def _view(pw, ph, box):
    w, e, s, n = box
    cx, cy = (w + e) / 2, (s + n) / 2
    k = math.cos(math.radians(cy))
    span_y = max(n - s, (e - w) * k * ph / pw)
    span_x = span_y * pw / ph / k
    return cx - span_x / 2, cx + span_x / 2, cy - span_y / 2, cy + span_y / 2


def _rgb(c):
    return alertinfo.hex_rgb(c) if isinstance(c, str) else tuple(c)


def draw_map(layers, pw, ph, cfg, outline=True, painter=None, view=None, dma=None, cities=None, water_alpha=0.78):
    """layers: list of (rgb, polys) drawn bottom -> top.
    painter(draw, proj): optional extra fill layer (e.g. gridded NDFD snow/wind cells)."""
    W_, H_ = z(pw), z(ph)
    w, e, s, n = _view(pw, ph, tuple(view or cfg.get("outlook_view") or VIEW_BOX))
    proj = lambda x, y: ((x - w) / (e - w) * W_, (n - y) / (n - s) * H_)
    lay = Image.new("RGBA", (W_, H_), (17, 27, 47, 255))
    d = ImageDraw.Draw(lay, "RGBA")
    land = Image.new("L", (W_, H_), 0)
    ld = ImageDraw.Draw(land)
    base_outlines = []
    if w < -85.3 or e > -73.2 or s < 32.7 or n > 40.6:  # view runs past the county map: fill in with whole states
        from .cpcmap import base
        b = base()
        for p in b["land"]:
            d.polygon([proj(x, y) for x, y in p[0]], fill=(29, 41, 63, 255))
            ld.polygon([proj(x, y) for x, y in p[0]], fill=255)
        for st in b["states"]:
            for p in st["polys"]:
                pts = [proj(x, y) for x, y in p[0]]
                d.polygon(pts, fill=STENCIL)
                ld.polygon(pts, fill=255)
                base_outlines.append(pts)
        for p in b["lakes"]:
            d.polygon([proj(x, y) for x, y in p[0]], fill=(17, 27, 47, 255))
            ld.polygon([proj(x, y) for x, y in p[0]], fill=0)
    cs = sorted((c for c in alertinfo.counties().values() if alertinfo.in_view(c, w, e, s, n)),
                key=lambda c: c["lsad"].lower() == "city")
    for c in cs:
        for p in c["polys"]:
            pts = [proj(x, y) for x, y in p[0]]
            d.polygon(pts, fill=STENCIL)
            ld.polygon(pts, fill=255)
    # outlook fills: each level on its own layer so holes don't erase lower levels
    ov = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    edges = []
    for col, polys in layers:
        one = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        od = ImageDraw.Draw(one)
        for p in polys:
            od.polygon([proj(x, y) for x, y, *_ in p[0]], fill=(*col, 255))
            for h in p[1:]:
                od.polygon([proj(x, y) for x, y, *_ in h], fill=(0, 0, 0, 0))
        ov.alpha_composite(one)
        edges.append((col, polys))
    if painter:
        painter(ImageDraw.Draw(ov), proj)
    a = ov.getchannel("A")
    alpha = Image.composite(a.point(lambda v: int(v * 0.85)), a.point(lambda v: int(v * water_alpha)), land)
    ov.putalpha(alpha)
    lay.alpha_composite(ov)
    d = ImageDraw.Draw(lay, "RGBA")
    lw = max(1, z(1))
    for pts in base_outlines:  # outer states (beyond the county map)
        d.line(pts + [pts[0]], fill=(214, 226, 244, 120), width=max(1, z(1.3)), joint="curve")
    for c in cs:  # county lines
        for p in c["polys"]:
            pts = [proj(x, y) for x, y in p[0]]
            d.line(pts + [pts[0]], fill=(*STENCIL_EDGE[:3], 150), width=lw)
    if outline:
        for col, polys in edges:
            dark = tuple(int(v * 0.55) for v in col)
            for p in polys:
                pts = [proj(x, y) for x, y, *_ in p[0]]
                d.line(pts + [pts[0]], fill=(*dark, 255), width=z(2.2), joint="curve")
    for ln in alertinfo.state_lines():  # state borders
        d.line([proj(x, y) for x, y in ln], fill=(214, 226, 244, 230), width=max(2, z(1.8)), joint="curve")
    if dma:  # outline the DMA's counties
        for c in cs:
            if c["fips"] in dma:
                for p in c["polys"]:
                    pts = [proj(x, y) for x, y in p[0]]
                    d.line(pts + [pts[0]], fill=(255, 255, 255, 255), width=z(1.6), joint="curve")
    draw_cities(d, proj, W_, H_, cfg, bottom_pad=80, cities=cities)
    return lay


def smooth_classes(idx, size, colors, blur, alpha=255):
    """Class grid -> smooth RGBA layer.
    idx: 'L' image, 0 = no data, k+1 = class k (any resolution). colors: [rgb per class].
    The class field is filled under no-data, scaled up, blurred and re-quantized, so boundaries come out as
    smooth curves instead of stair-stepped cells/pixels (adjacent classes blend along true contours)."""
    from PIL import ImageFilter
    step = max(1, 250 // (len(colors) + 1))
    mask = idx.point(lambda v: 255 if v else 0)
    v = idx.point(lambda x: x * step)
    m = mask
    for _ in range(4):  # spread values a little into no-data so edges don't sag toward class 0
        v = Image.composite(v, v.filter(ImageFilter.MaxFilter(3)), m)
        m = m.filter(ImageFilter.MaxFilter(3))
    if v.size != size:
        v = v.resize(size, Image.BILINEAR)
        mask = mask.resize(size, Image.BILINEAR)
    if blur > 0:
        v = v.filter(ImageFilter.GaussianBlur(blur))
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
    q = v.point(lambda x: min(len(colors), int(x / step + 0.5)))
    lut = [(0, 0, 0)] + [tuple(c) for c in colors] + [(0, 0, 0)] * (256 - len(colors) - 1)
    rgb = [q.point([lut[i][ch] for i in range(256)]) for ch in range(3)]
    a = mask.point(lambda x: int(alpha * min(1.0, max(0.0, (x - 96) / 64))))  # soft, anti-aliased outer edge
    a = Image.composite(a, Image.new("L", size, 0), q.point(lambda x: 255 if x else 0))
    return Image.merge("RGBA", (*rgb, a))


def composite_at(base, layer, x, y):
    """alpha_composite that tolerates negative/off-canvas offsets."""
    x, y = int(round(x)), int(round(y))
    cx, cy = max(0, -x), max(0, -y)
    if cx or cy:
        layer = layer.crop((cx, cy, layer.width, layer.height))
        x, y = x + cx, y + cy
    if x >= base.width or y >= base.height or layer.width <= 0 or layer.height <= 0:
        return
    layer = layer.crop((0, 0, min(layer.width, base.width - x), min(layer.height, base.height - y)))
    base.alpha_composite(layer, (x, y))


def _legend_chips(cv, x, y, items, maxw):
    """items: [(rgb, text)] drawn as a row of chips on the map's bottom edge."""
    f = 19
    widths = [cv.width(t, f, "bold") + 46 for _, t in items]
    total = sum(widths) + 8 * (len(items) - 1) + 20
    cv.rect(x, y, min(total, maxw), 44, (13, 21, 38, 225), r=10)
    cx = x + 10
    for (col, t), w_ in zip(items, widths):
        cv.rect(cx, y + 11, 22, 22, (*col, 255), r=4)
        cv.text(cx + 30, y + 22, t, f, "bold", anchor="lm")
        cx += w_ + 8


def _side(cv, x, y, w, h, head_col, head_label, head_value, meaning, rows, row_title):
    compact = h < 440  # short panel under a stacked map (square / 4:5)
    cv.rect(x, y, w, h, C["panel"], r=18)
    cv.text(x + 26, y + (20 if compact else 26), head_label, 20 if compact else 22, "bold", C["muted"], anchor="lt")
    bt, bh = (y + 52, 60) if compact else (y + 62, 84)
    cv.rect(x + 26, bt, w - 52, bh, (*head_col, 255), r=12)
    lum = 0.3 * head_col[0] + 0.59 * head_col[1] + 0.11 * head_col[2]
    cv.text(x + w / 2, bt + bh / 2, head_value, 32 if compact else 40, "bold", (20, 28, 46) if lum > 150 else C["text"],
            anchor="mm", maxw=w - 80)
    my = bt + bh + (12 if compact else 18)
    used = cv.paragraph(x + 26, my, meaning, 21 if compact else 26 if h > 600 else 23, "regular", w - 52,
                        max_lines=1 if compact else 4 if h > 600 else 2, lh=1.28)
    ry = my + used + (10 if compact else 26 if h > 600 else 14)
    cv.line([(x + 26, ry), (x + w - 26, ry)], (255, 255, 255, 60), 1.5)
    ry += 10 if compact else 20 if h > 600 else 12
    cv.text(x + 26, ry, row_title, 19 if compact else 22, "bold", C["muted"], anchor="lt")
    ry += 30 if compact else 40 if h > 600 else 34
    ncol = 2 if w > 900 else 1  # wide, short panel under a stacked map: two columns
    min_rh = 30  # never shrink rows below a readable size; drop the extra rows instead
    per_max = max(1, int((y + h - 10 - ry) // min_rh))
    rows = rows[:per_max * ncol]
    per = -(-len(rows) // ncol) if rows else 1
    rh = min(46, (y + h - 10 - ry) / per)
    fs = min(26, rh * 0.66)
    cw = (w - 52 - (40 if ncol == 2 else 0)) / ncol
    for k, (name, col, val) in enumerate(rows):
        c, r = divmod(k, per)
        cx, yy = x + 26 + c * (cw + 40), ry + r * rh
        if yy + rh > y + h - 6:
            continue
        cv.rect(cx, yy + rh * 0.16, 20, rh * 0.68, (*col, 255) if col else (70, 86, 112, 255), r=4)
        cv.text(cx + 32, yy + rh / 2, name, fs, "medium", anchor="lm", maxw=cw * 0.55)
        cv.text(cx + cw, yy + rh / 2, val, fs, "bold", anchor="rm", maxw=cw * 0.42)


def _hazard_side(cv, x, y, w, h, head_col, head_label, head_value, meaning, hazards, title):
    compact = w > 900 and h < 700  # short, wide panel under a stacked map (4:5 post)
    bh = 84 if not compact else 64
    cv.rect(x, y, w, h, C["panel"], r=18)
    cv.text(x + 26, y + 22, head_label, 22 if not compact else 20, "bold", C["muted"], anchor="lt")
    cv.rect(x + 26, y + 56, w - 52, bh, (*head_col, 255), r=12)
    lum = 0.3 * head_col[0] + 0.59 * head_col[1] + 0.11 * head_col[2]
    cv.text(x + w / 2, y + 56 + bh / 2, head_value, 40 if not compact else 34, "bold",
            (20, 28, 46) if lum > 150 else C["text"], anchor="mm", maxw=w - 80)
    my = y + 56 + bh + 16
    used = cv.paragraph(x + 26, my, meaning, 24 if not compact else 21, "regular", w - 52,
                        max_lines=3 if not compact else 2, lh=1.26)
    ry = my + used + (20 if not compact else 10)
    cv.line([(x + 26, ry), (x + w - 26, ry)], (255, 255, 255, 60), 1.5)
    ry += 18 if not compact else 10
    cv.text(x + 26, ry, title, 22 if not compact else 19, "bold", C["muted"], anchor="lt")
    ry += 38 if not compact else 30
    rows = hazards[:5] if not compact else hazards[:4]
    ncol = 2 if w > 900 else 1
    cw = (w - 52 - (36 if ncol == 2 else 0)) / ncol
    avail = y + h - 12 - ry
    head_h = 40 if not compact else 34

    def block_h(r, size):
        return head_h + len(cv.wrap(r.get("text", ""), size, "regular", cw - 34)) * size * 1.22

    for size in range(24 if not compact else 21, 14, -1):  # shrink text until every row fits
        pairs = [rows[i:i + ncol] for i in range(0, len(rows), ncol)]
        need = sum(max(block_h(r, size) for r in pr) + 14 for pr in pairs)
        if need <= avail:
            break
    for pr in [rows[i:i + ncol] for i in range(0, len(rows), ncol)]:
        rowh = max(block_h(r, size) for r in pr)
        if ry + rowh > y + h - 8:
            break
        for c, r in enumerate(pr):
            bx = x + 26 + c * (cw + 36)
            lvl = str(r.get("level", "")).upper()
            col = spchazards.LEVEL_COLORS.get(lvl, (120, 140, 170))
            lines = cv.wrap(r.get("text", ""), size, "regular", cw - 34)
            cv.rect(bx, ry, 8, block_h(r, size), (*col, 255), r=3)
            pill = lvl + (f"  {r['prob']}%" if r.get("prob") else "")
            pf = 18 if not compact else 16
            pw_ = cv.width(pill, pf, "bold") + 24
            cv.text(bx + 24, ry + 2, r["label"].upper(), 25 if not compact else 22, "bold", anchor="lt",
                    maxw=cw - pw_ - 40)
            cv.rect(bx + cw - pw_, ry + 1, pw_, head_h - 8, (*col, 255), r=15)
            pl = 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2]
            cv.text(bx + cw - pw_ / 2, ry + 1 + (head_h - 8) / 2, pill, pf, "bold",
                    (20, 28, 46) if pl > 150 else C["text"], anchor="mm")
            for i, ln in enumerate(lines):
                cv.text(bx + 24, ry + head_h + i * size * 1.22, ln, size, "regular", anchor="lt")
        ry += rowh + 14


def spc_info(data, cfg):
    """Editable summary for each SPC day: headline, meaning, hazard rows (JSON-friendly)."""
    loc = cfg["location"]
    out = {}
    for day, feats in (data.get("spc") or {}).items():
        home = _level_at(feats, loc["lon"], loc["lat"])
        if home:
            c = next(c for c in outlooks.SPC_CATS if c[1] == home["code"])
            head = f"{c[2].upper()} RISK  ({c[0]} OF 5)" if c[0] else "NO SEVERE RISK"
            code, meaning, level = c[1], c[4], c[0]
        else:
            head, code, level = "NO SEVERE RISK", None, None
            meaning = "Severe thunderstorms are not expected."
        point = spchazards.at_point((data.get("probs") or {}).get(day) or (data.get("probs") or {}).get(str(day)),
                                    loc["lon"], loc["lat"])
        hazards = spchazards.rows_for(point, level) if (point or level is not None) else []
        out[str(day)] = {"category": code, "headline": head, "meaning": meaning,
                         "hazards_title": "POSSIBLE HAZARDS", "hazards": hazards}
    return out


def _level_at(feats, lon, lat):
    best = None
    for f in feats:
        if outlooks.contains(f["polys"], lon, lat) and (best is None or f["level"] > best["level"]):
            best = f
    return best


def _day_label(day, feats, pkg, cfg):
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.fromisoformat(pkg["issued"]).astimezone(timezone.utc)
    t = feats[0].get("times") if feats else None
    dt = outlooks.outlook_day_date(day, now, t)
    today = now.astimezone(tz).date()
    name = "TODAY" if dt == today else "TOMORROW" if dt == today + timedelta(days=1) else dt.strftime("%A").upper()
    return f"DAY {day}  ·  {name}, {dt.strftime('%b').upper()} {dt.day}"


def _cat_graphic(kind, day, feats, pkg, cfg):
    cats = outlooks.SPC_CATS if kind == "spc" else outlooks.ERO_CATS
    title = "SEVERE WEATHER OUTLOOK" if kind == "spc" else "EXCESSIVE RAINFALL OUTLOOK"
    center = "STORM PREDICTION CENTER" if kind == "spc" else "WEATHER PREDICTION CENTER"
    cv = Canvas(cfg)
    cv.header(title, f"{_day_label(day, feats, pkg, cfg)}  ·  {center}")
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    shown = [f for f in feats if not (kind == "spc" and f["level"] == 0)]  # no TSTM area on SPC maps
    layers = [(_rgb(f["color"]), f["polys"]) for f in shown]
    _paste_rounded(cv, draw_map(layers, mw, mh, cfg), mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    top_n = len(cats) if kind == "ero" else 5
    chips = [(_rgb(c[3]), f"{c[0]} {c[1]}") for c in cats if c[0]]
    _legend_chips(cv, mx + 16, my + mh - 60, chips, mw - 32)
    loc = cfg["location"]
    home = _level_at(feats, loc["lon"], loc["lat"])
    if home and home["level"] > 0:
        c = next(c for c in cats if c[1] == home["code"])
        val = f"{c[2].upper()} RISK  ({c[0]} OF {top_n})"
        head_col, meaning = _rgb(c[3]), c[4]
    elif home and kind == "spc":  # general thunder only
        val, head_col, meaning = "NO SEVERE RISK", (70, 86, 112), outlooks.SPC_CATS[0][4]
    else:
        val = "NO RISK"
        head_col = (70, 86, 112)
        meaning = ("Severe thunderstorms are not expected." if kind == "spc"
                   else "Flash flooding is not expected (less than a 5% chance).")
    area_label = cfg['location'].get('area', 'HAMPTON ROADS AREA').upper()
    if kind == "spc":
        info = (pkg.get("spc_outlook") or {}).get(str(day)) or spc_info({"spc": {day: feats}}, cfg)[str(day)]
        cat = next((c for c in outlooks.SPC_CATS if c[1] == str(info.get("category") or "").upper() and c[0] > 0), None)
        if cat:
            head_col = _rgb(cat[3])
        _hazard_side(cv, px, py, pw_, ph_, head_col, area_label, info.get("headline") or val,
                     info.get("meaning") or meaning, info.get("hazards") or [], info.get("hazards_title", "POSSIBLE HAZARDS"))
        edited = info.get("edited")
        src = ("SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NOAA Storm Prediction Center") + \
            (" + METEOROLOGIST EDITS" if edited else "")
        cv.footer(pkg, source=src)
        hz = [(h["label"], spchazards.LEVEL_COLORS.get(str(h.get("level", "")).upper(), (120, 140, 170)),
               str(h.get("level", "")).upper() + (f" {h['prob']}%" if h.get("prob") else "")) for h in info.get("hazards") or []]
        fullscreen.attach(cv, title=title, subtitle=f"{_day_label(day, feats, pkg, cfg)}  ·  {center}",
                          map_fn=lambda pw, ph, view: draw_map(layers, pw, ph, cfg, view=view),
                          box=tuple(cfg.get("outlook_view") or VIEW_BOX), head_label=area_label,
                          head_value=info.get("headline") or val, head_col=head_col,
                          meaning=info.get("meaning") or meaning, rows=hz,
                          overlay=lambda c, x, y, mw_: _legend_chips(c, x, y, chips, mw_), source=src)
        return cv
    rows = []
    for name, la, lo in cfg.get("outlook_points") or POINTS:
        f = _level_at(feats, lo, la)
        if f:
            c = next(c for c in cats if c[1] == f["code"])
            rows.append((name, _rgb(c[3]), c[1] if not c[0] else f"{c[1]} ({c[0]}/{top_n})"))
        else:
            rows.append((name, None, "NONE"))
    _side(cv, px, py, pw_, ph_, head_col, area_label, val, meaning, rows, "LOCAL RISK")
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else \
        ("NOAA Storm Prediction Center" if kind == "spc" else "NOAA Weather Prediction Center")
    cv.footer(pkg, source=src)
    fullscreen.attach(cv, title=title, subtitle=f"{_day_label(day, feats, pkg, cfg)}  ·  {center}",
                      map_fn=lambda pw, ph, view: draw_map(layers, pw, ph, cfg, view=view),
                      box=tuple(cfg.get("outlook_view") or VIEW_BOX), head_label=area_label, head_value=val,
                      head_col=head_col, meaning=meaning, rows=rows,
                      overlay=lambda c, x, y, mw_: _legend_chips(c, x, y, chips, mw_), source=src)
    return cv


def _qpf_bar(cv, bx, by, bw):
    """Color bar: linear 0-12 in scale, like the NWS/WPC reference bar."""
    bw = min(bw, 1100)
    cv.rect(bx, by, bw, 62, (13, 21, 38, 225), r=10)
    x0, x1, top_in = bx + 22, bx + bw - 48, 12.0
    xin = lambda v: x0 + (x1 - x0) * v / top_in
    edges = [t for t, _ in outlooks.QPF_COLORS] + [top_in]
    for (t, c), nxt in zip(outlooks.QPF_COLORS, edges[1:]):
        cv.rect(xin(t), by + 10, xin(nxt) - xin(t) + 0.5, 20, (*c, 255))
    for i in range(13):
        cv.line([(xin(i), by + 30), (xin(i), by + 37)], (255, 255, 255, 220), 2)
        cv.text(xin(i), by + 54, str(i), 17, "bold", anchor="ms")
    cv.text(bx + bw - 12, by + 54, "IN", 15, "bold", C["muted"], anchor="rs")


def _qpf_graphic(qpf, pkg, cfg, statewide=False):
    feats = qpf["features"]
    period = qpf["period"]
    a, _, b = period.partition("-")
    span = f"DAYS {a}-{b} TOTAL" if b else f"DAY {a} TOTAL"
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.fromisoformat(pkg["issued"]).astimezone(tz)
    end = (datetime.fromisoformat(pkg["issued"]).astimezone(timezone.utc) - timedelta(hours=12)).date() + \
        timedelta(days=int(b or a))
    cv = Canvas(cfg)
    where = "VIRGINIA & NORTH CAROLINA  ·  " if statewide else ""
    subtitle = f"{where}{span}  ·  THROUGH {end.strftime('%a %b').upper()} {end.day}"
    cv.header("RAINFALL FORECAST MAP", subtitle)
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    layers = [(outlooks.qpf_color(f["value"]), f["polys"]) for f in feats]
    if statewide:
        dma = set(cfg.get("dma_counties") or (cfg.get("alert_counties") or []) + ["37055"])
        lay = draw_map(layers, mw, mh, cfg, outline=False, view=cfg.get("state_view") or STATE_VIEW, dma=dma,
                       cities=cfg.get("state_map_cities") or STATE_CITIES)
    else:
        lay = draw_map(layers, mw, mh, cfg, outline=False)
    _paste_rounded(cv, lay, mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    vals = sorted({f["value"] for f in feats})
    _qpf_bar(cv, mx + 16, my + mh - 74, mw - 32)

    def at(lon, lat):
        inside = [f["value"] for f in feats if outlooks.contains(f["polys"], lon, lat)]
        if not inside:
            return None, "< " + (f"{vals[0]:g}\"" if vals else '0.01"')
        lo = max(inside)
        hi = next((v for v in vals if v > lo + 1e-6), None)
        return lo, (f'{lo:g}–{hi:g}"' if hi else f'{lo:g}"+')

    loc = cfg["location"]
    v, txt = at(loc["lon"], loc["lat"])
    head_col = outlooks.qpf_color(v) if v else (70, 86, 112)
    spoken = txt.replace('–', ' to ').replace('"+', '" or more')
    meaning = (f"{span.title().replace(' Total', '')} rainfall total for the Hampton Roads area: {spoken}.") if v else \
        "Little or no rain is expected in the Hampton Roads area over this period."
    rows = []
    pts = (cfg.get("dma_points") or DMA_POINTS) if statewide else (cfg.get("outlook_points") or POINTS)
    for name, la, lo in pts:
        pv, pt = at(lo, la)
        rows.append((name, outlooks.qpf_color(pv) if pv else None, pt))
    _side(cv, px, py, pw_, ph_, head_col, cfg['location'].get('area', 'HAMPTON ROADS AREA').upper(),
          txt if v else "LITTLE OR NO RAIN", meaning, rows, "HAMPTON ROADS DMA TOTALS" if statewide else "LOCAL TOTALS")
    cv.footer(pkg, show_source=False)
    if statewide:
        dma_ = set(cfg.get("dma_counties") or (cfg.get("alert_counties") or []) + ["37055"])
        mfn = lambda pw, ph, view: draw_map(layers, pw, ph, cfg, outline=False, view=view, dma=dma_,
                                            cities=cfg.get("state_map_cities") or STATE_CITIES)
        box = tuple(cfg.get("state_view") or STATE_VIEW)
    else:
        mfn = lambda pw, ph, view: draw_map(layers, pw, ph, cfg, outline=False, view=view)
        box = tuple(cfg.get("outlook_view") or VIEW_BOX)
    fullscreen.attach(cv, title="RAINFALL FORECAST MAP", subtitle=subtitle, map_fn=mfn, box=box,
                      head_label=cfg['location'].get('area', 'HAMPTON ROADS AREA').upper(),
                      head_value=txt if v else "LITTLE OR NO RAIN", head_col=head_col, meaning=meaning, rows=rows,
                      overlay=lambda c, x, y, mw_: _qpf_bar(c, x, y - 4, mw_), source=None)
    return cv


def outlook_graphics(pkg, cfg):
    data = pkg.get("_outlooks")
    if not data:
        return None
    out = []
    for kind in ("spc", "ero"):
        for day, feats in sorted((data.get(kind) or {}).items(), key=lambda kv: int(kv[0])):
            day = int(day)
            real = [f for f in feats if f["level"] > 0]  # TSTM alone doesn't count as a risk area
            if not real and not cfg.get("outlook_show_empty", kind == "spc" and day == 1):
                print(f"  - {kind}_day{day}: nothing in the map area, skipped")
                continue
            out.append((f"{kind}_day{day}", _cat_graphic(kind, day, feats, pkg, cfg)))
    maps = dict(data.get("qpf_maps") or {})
    if not maps and data.get("qpf"):  # older single-map data
        maps = {data["qpf"]["period"]: data["qpf"]}
    for period, q in sorted(maps.items(), key=lambda kv: int(kv[0].split("-")[-1])):
        if not q.get("features"):
            continue
        a, _, b = period.partition("-")
        tag = f"{int(b) - int(a) + 1}day" if b else f"day{a}"
        out.append((f"wpc_qpf_{tag}", _qpf_graphic(q, pkg, cfg)))
        if cfg.get("qpf_state_map", True):
            out.append((f"wpc_qpf_{tag}_state", _qpf_graphic(q, pkg, cfg, statewide=True)))
    return out or None
