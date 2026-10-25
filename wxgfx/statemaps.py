"""Virginia + North Carolina "stencil" graphics (the Halloween-outlook look).

Only the two states are drawn (county shapes = the stencil); the data fills the stencil and a side panel gives one
card per state.  The old big "VIRGINIA" / "NORTH CAROLINA" words are replaced by small, low-opacity gray "VA" / "NC"
tags (on the map and as the legend on each card).

Graphics (all keyless):
  state_spc_day1..3     SPC categorical severe-weather outlook          (from pkg["_outlooks"])
  state_ero_day1..3     WPC excessive rainfall outlook                  (from pkg["_outlooks"])
  state_qpf_<period>    WPC rainfall totals (1-2, 1-3, 1-5, 1-7 days)   (from pkg["_outlooks"])
  state_highs_day1..N   NDFD daily high temperature, state high/low range
  state_lows_day1..N    NDFD overnight low temperature
Config: state_spc_days / state_ero_days / state_qpf_periods / state_temp_days (default 3) / state_stencil_view.
"""
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import alertinfo, outlooks, outlookmap
from .alertmap import STENCIL, STENCIL_EDGE, _paste_rounded
from .theme import C, Canvas, font, z

VIEW = (-84.2, -75.0, 33.6, 39.7)  # VA + NC with a hair of margin (grows to the panel's aspect)
STATES = {"51": "VA", "37": "NC"}
TAG_COL = (190, 200, 216)  # the small gray VA / NC tags
TAG_ALPHA = 175            # lowered opacity (0-255)
TAG_POS = {"VA": (-79.55, 37.55), "NC": (-79.7, 35.5)}

CITIES = [  # (name, lat, lon, tier) -- statewide spread, both states
    ("Norfolk", 36.85, -76.29, 1), ("Richmond", 37.54, -77.44, 1), ("Raleigh", 35.78, -78.64, 1),
    ("Charlotte", 35.23, -80.84, 1), ("Roanoke", 37.27, -79.94, 1), ("Greensboro", 36.07, -79.79, 1),
    ("Wilmington", 34.23, -77.94, 1), ("Asheville", 35.60, -82.55, 1), ("Fayetteville", 35.05, -78.88, 2),
    ("Charlottesville", 38.03, -78.48, 2), ("Lynchburg", 37.41, -79.14, 2), ("Winchester", 39.18, -78.16, 2),
    ("Fredericksburg", 38.30, -77.46, 2), ("Blacksburg", 37.23, -80.41, 2), ("Bristol", 36.60, -82.19, 2),
    ("Danville", 36.59, -79.40, 2), ("Greenville", 35.61, -77.37, 2), ("Hatteras", 35.22, -75.69, 2),
    ("Elizabeth City", 36.30, -76.22, 2), ("Emporia", 36.69, -77.54, 2), ("Wytheville", 36.95, -81.08, 2),
    ("Harrisonburg", 38.45, -78.87, 2), ("Hickory", 35.73, -81.34, 2), ("New Bern", 35.11, -77.04, 2),
    ("Winston-Salem", 36.10, -80.24, 2), ("Rocky Mount", 35.94, -77.79, 2), ("Lumberton", 34.62, -79.01, 2),
    ("Boone", 36.22, -81.67, 2), ("Statesville", 35.78, -80.89, 2), ("Goldsboro", 35.38, -77.99, 2),
    ("Staunton", 38.15, -79.07, 2), ("Culpeper", 38.47, -77.99, 2), ("South Boston", 36.70, -78.90, 2),
    ("Martinsville", 36.69, -79.87, 2), ("Farmville", 37.30, -78.40, 2), ("Tappahannock", 37.92, -76.86, 2),
    ("Big Stone Gap", 36.87, -82.78, 2), ("Va. Beach", 36.85, -75.98, 2), ("Kitty Hawk", 36.06, -75.70, 2),
    ("Southport", 33.92, -78.02, 2), ("Murphy", 35.09, -84.03, 2), ("Wilson", 35.72, -77.92, 2),
]
# temperature color ramp (deg F): deep purple -> blue -> green -> yellow -> orange -> red -> magenta
TEMP_STOPS = [(10, (120, 90, 200)), (25, (80, 120, 235)), (35, (70, 175, 245)), (45, (70, 205, 205)),
              (55, (90, 205, 120)), (65, (200, 225, 80)), (75, (255, 205, 60)), (85, (255, 140, 45)),
              (95, (235, 70, 55)), (105, (185, 35, 110))]


def temp_color(f):
    if f <= TEMP_STOPS[0][0]:
        return TEMP_STOPS[0][1]
    for (t0, c0), (t1, c1) in zip(TEMP_STOPS, TEMP_STOPS[1:]):
        if f <= t1:
            u = (f - t0) / (t1 - t0)
            return tuple(int(c0[i] + (c1[i] - c0[i]) * u) for i in range(3))
    return TEMP_STOPS[-1][1]


def _rgb(c):
    return alertinfo.hex_rgb(c) if isinstance(c, str) else tuple(c)


def _counties():
    out = []
    for c in alertinfo.counties().values():
        st = STATES.get(c["fips"][:2])
        if st:
            bw, be, bs, bn = c["bb"]
            out.append({"st": st, "c": c, "lon": (bw + be) / 2, "lat": (bs + bn) / 2})
    return out


# ------------------------------------------------------------------ map
def stencil_map(w, h, cfg, layers=None, painter=None, cities=None, tags=True, alpha=0.93, bg=(13, 21, 38, 255), view=None, shade_lines=False):
    """RGBA map (supersampled) of the VA + NC stencil.  layers: [(rgb, polys)] drawn bottom -> top;
    painter(draw, proj): gridded fill (NDFD); cities: [(name, lat, lon, tier, text|None)]."""
    W_, H_ = z(w), z(h)
    ws, es, ss, ns = outlookmap._view(w, h, tuple(view or cfg.get("state_stencil_view") or VIEW))
    proj = lambda x, y: ((x - ws) / (es - ws) * W_, (ns - y) / (ns - ss) * H_)
    lay = Image.new("RGBA", (W_, H_), bg)
    d = ImageDraw.Draw(lay, "RGBA")
    cs = [k for k in _counties() if alertinfo.in_view(k["c"], ws, es, ss, ns)]
    cs.sort(key=lambda k: k["c"]["lsad"].lower() == "city")
    masks = {s: Image.new("L", (W_, H_), 0) for s in STATES.values()}
    for k in cs:
        for p in k["c"]["polys"]:
            pts = [proj(x, y) for x, y in p[0]]
            d.polygon(pts, fill=STENCIL)
            ImageDraw.Draw(masks[k["st"]]).polygon(pts, fill=255)
    mask = ImageChops.lighter(*masks.values())
    ov = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    for col, polys in layers or []:
        one = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        od = ImageDraw.Draw(one)
        for p in polys:
            od.polygon([proj(x, y) for x, y, *_ in p[0]], fill=(*col, 255))
            for hole in p[1:]:
                od.polygon([proj(x, y) for x, y, *_ in hole], fill=(0, 0, 0, 0))
        ov.alpha_composite(one)
    if painter:
        painter(ImageDraw.Draw(ov), proj)
    a = ImageChops.multiply(ov.getchannel("A").point(lambda v: int(v * alpha)), mask)
    ov.putalpha(a)
    lay.alpha_composite(ov)
    d = ImageDraw.Draw(lay, "RGBA")
    for k in cs:  # county lines
        for p in k["c"]["polys"]:
            pts = [proj(x, y) for x, y in p[0]]
            d.line(pts + [pts[0]], fill=(*STENCIL_EDGE[:3], 95), width=max(1, z(0.8)))
    if shade_lines:  # dark county lines through the shaded areas
        dk = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dk)
        for k in cs:
            for p in k["c"]["polys"]:
                pts = [proj(x, y) for x, y in p[0]]
                dd.line(pts + [pts[0]], fill=(20, 28, 46, 200), width=max(1, z(1.3)))
        dk.putalpha(ImageChops.multiply(dk.getchannel("A"), a.point(lambda v: 255 if v > 8 else 0)))
        lay.alpha_composite(dk)
    kk = 2 * max(1, z(1.1)) + 1  # state outlines: edge of each state's mask
    for m in masks.values():
        edge = ImageChops.subtract(m.filter(ImageFilter.MaxFilter(kk)), m.filter(ImageFilter.MinFilter(kk)))
        lay.paste(Image.new("RGBA", (W_, H_), (232, 240, 252, 255)), (0, 0), edge.point(lambda v: int(v * 0.92)))
    d = ImageDraw.Draw(lay, "RGBA")
    cl = cities if cities is not None else [(*c, None) for c in CITIES]
    if tags:  # small gray state tags, centred in each state and kept clear of every city label
        import numpy as np
        blocked = _cities(d, proj, W_, H_, cl, draw=False)
        tl = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        td = ImageDraw.Draw(tl)
        ft = font("bold", 46)
        for st, m in masks.items():
            ys, xs = np.nonzero(np.asarray(m))
            if not len(xs):
                continue
            cx, cy = float(xs.mean()), float(ys.mean())
            tw, th = td.textlength(st, font=ft) / 2 + z(8), z(24)
            ma = np.asarray(m)
            best = None
            for r in range(0, z(260), z(6)):  # spiral outwards from the centroid until a clear spot is found
                for k in range(1 if r == 0 else 16):
                    ang = 2 * math.pi * k / 16
                    px, py = cx + r * math.cos(ang), cy + r * math.sin(ang) * 0.8
                    box = (px - tw, py - th, px + tw, py + th)
                    ix0, iy0, ix1, iy1 = (int(v) for v in box)
                    if ix0 < 0 or iy0 < 0 or ix1 >= W_ or iy1 >= H_:
                        continue
                    if ma[iy0, ix0] and ma[iy0, ix1] and ma[iy1, ix0] and ma[iy1, ix1] and \
                            not any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1] for b in blocked):
                        best = (px, py)
                        break
                if best:
                    break
            if best:
                td.text(best, st, font=ft, fill=(*TAG_COL, TAG_ALPHA), anchor="mm")
        lay.alpha_composite(tl)
        d = ImageDraw.Draw(lay, "RGBA")
    _cities(d, proj, W_, H_, cl)
    return lay


def _cities(d, proj, W_, H_, cities, draw=True):
    placed = []
    f1, f2, fv = font("bold", 16), font("medium", 13), font("bold", 25)
    for name, la, lo, tier, val in cities:
        x, y = proj(lo, la)
        if not (z(14) < x < W_ - z(14) and z(14) < y < H_ - z(14)):
            continue
        fn = f1 if tier == 1 else f2
        nm = name.upper()
        tw = max(d.textlength(nm, font=fn), d.textlength(val, font=fv) if val else 0)
        th = z(17 if tier == 1 else 14) + (z(26) if val else 0)
        box = (x - tw / 2 - z(4), y - th / 2 - z(3), x + tw / 2 + z(4), y + th / 2 + z(3))
        if any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1] for b in placed):
            continue
        placed.append(box)
        if not draw:
            continue
        if val:  # name small over a big temperature
            d.text((x, y - z(13)), nm, font=fn, fill=(255, 255, 255, 235), anchor="mm", stroke_width=z(2.2),
                   stroke_fill=(13, 21, 38, 255))
            d.text((x, y + z(8)), val, font=fv, fill=(255, 255, 255, 255), anchor="mm", stroke_width=z(2.6),
                   stroke_fill=(13, 21, 38, 255))
        else:
            r = z(3.4)
            d.ellipse([x - r, y - r - z(7), x + r, y + r - z(7)], fill=(255, 255, 255, 255), outline=(13, 21, 38, 255),
                      width=z(1.2))
            d.text((x, y + z(6)), nm, font=fn, fill=(255, 255, 255, 255), anchor="mm", stroke_width=z(2.2),
                   stroke_fill=(13, 21, 38, 255))
    return placed


# ------------------------------------------------------------------ side panel
def _tag(cv, x, y, st, size):
    """The small gray low-opacity state legend tag."""
    cv.text(x, y, st, size, "bold", (*TAG_COL, TAG_ALPHA), anchor="lm")


def _panel(cv, box, label, cards, meaning, legend):
    """cards: [{"st","value","col","detail"}]; legend(cv, x, y, w) draws the key at the bottom."""
    x, y, w, h = box
    compact = h < 560
    cv.rect(x, y, w, h, C["panel"], r=18)
    cv.text(x + 26, y + (18 if compact else 26), label, 20 if compact else 22, "bold", C["muted"], anchor="lt")
    cy = y + (50 if compact else 70)
    leg_h = 74 if compact else 96
    mean_h = 96 if compact else 170
    ch = min(190, (y + h - cy - leg_h - mean_h - 30) / max(1, len(cards)) - 12)
    for card in cards:
        cv.rect(x + 20, cy, w - 40, ch, (255, 255, 255, 14), r=14)
        _tag(cv, x + 40, cy + ch * 0.22, card["st"], 26 if compact else 32)
        bh = ch * 0.52
        col = card.get("col") or (70, 86, 112)
        cv.rect(x + 100, cy + ch * 0.06, w - 140, bh, (*col, 255), r=10)
        lum = 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2]
        cv.text(x + 100 + (w - 140) / 2, cy + ch * 0.06 + bh / 2, card["value"], 34 if not compact else 26, "bold",
                (20, 28, 46) if lum > 150 else C["text"], anchor="mm", maxw=w - 170)
        cv.text(x + 40, cy + ch * 0.78, card["detail"], 20 if not compact else 17, "medium", C["muted"], anchor="lm",
                maxw=w - 80)
        cy += ch + 12
    cv.line([(x + 26, cy + 4), (x + w - 26, cy + 4)], (255, 255, 255, 60), 1.5)
    cv.text(x + 26, cy + 14, "WHAT IT MEANS", 19 if compact else 21, "bold", C["muted"], anchor="lt")
    cv.paragraph(x + 26, cy + (40 if compact else 46), meaning, 21 if compact else 25, "regular", w - 52,
                 max_lines=3 if compact else 5, lh=1.28)
    legend(cv, x + 26, y + h - leg_h + 6, w - 52)


def _legend_chips(cv, x, y, w, items):
    f = 17
    wd = [cv.width(t, f, "bold") + 40 for _, t in items]
    per_row = []
    row, used = [], 0
    for it, ww in zip(items, wd):
        if used + ww > w and row:
            per_row.append(row)
            row, used = [], 0
        row.append((it, ww))
        used += ww + 8
    per_row.append(row)
    for r, row in enumerate(per_row):
        cx = x
        for (col, t), ww in row:
            cv.rect(cx, y + r * 34 + 4, 20, 20, (*col, 255), r=4)
            cv.text(cx + 28, y + r * 34 + 14, t, f, "bold", anchor="lm")
            cx += ww + 8


def _bar(cv, x, y, w, stops, lo, hi, unit, ticks):
    n = 80
    for i in range(n):
        v = lo + (hi - lo) * (i + 0.5) / n
        cv.rect(x + w * i / n, y + 6, w / n + 0.8, 22, (*stops(v), 255))
    for t in ticks:
        tx = x + w * (t - lo) / (hi - lo)
        cv.line([(tx, y + 28), (tx, y + 35)], (255, 255, 255, 220), 2)
        cv.text(tx, y + 54, f"{t:g}", 17, "bold", anchor="ms")
    cv.text(x + w, y + 70, unit, 15, "bold", C["muted"], anchor="rs")


# ------------------------------------------------------------------ outlook helpers
def _day_name(day, feats, pkg, cfg):
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.fromisoformat(pkg["issued"]).astimezone(timezone.utc)
    t = feats[0].get("times") if feats else None
    dt = outlooks.outlook_day_date(day, now, t)
    today = now.astimezone(tz).date()
    nm = "TODAY" if dt == today else "TOMORROW" if dt == today + timedelta(days=1) else dt.strftime("%A").upper()
    return f"{nm}, {dt.strftime('%b').upper()} {dt.day}"


def _src(pkg, real):
    return "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else real


def _cat_graphic(kind, day, feats, pkg, cfg):
    cats = outlooks.SPC_CATS if kind == "spc" else outlooks.ERO_CATS
    top_n = 5 if kind == "spc" else 4
    shown = [f for f in feats if f["level"] > 0]
    cs = _counties()
    best = {"VA": (0, None, 0), "NC": (0, None, 0)}
    tot = {"VA": 0, "NC": 0}
    for k in cs:
        tot[k["st"]] += 1
        lv = max([f["level"] for f in feats if f["level"] > 0 and outlooks.contains(f["polys"], k["lon"], k["lat"])] or [0])
        if lv:
            b = best[k["st"]]
            best[k["st"]] = (max(b[0], lv), None, b[2] + 1)
    cards = []
    for st in ("VA", "NC"):
        lv, _, n = best[st]
        c = next((c for c in cats if c[0] == lv), None) if lv else None
        if c:
            cards.append({"st": st, "value": f"{c[2].upper()}  ({c[0]}/{top_n})", "col": _rgb(c[3]),
                          "detail": f"RISK AREA TOUCHES {round(100 * n / tot[st])}% OF {st} COUNTIES"})
        else:
            cards.append({"st": st, "value": "NO SEVERE RISK" if kind == "spc" else "NO RISK", "col": None,
                          "detail": "NOTHING IN THE OUTLOOK FOR " + st})
    topv = max(best["VA"][0], best["NC"][0])
    topc = next((c for c in cats if c[0] == topv), None) if topv else None
    meaning = topc[4] if topc else ("Severe thunderstorms are not expected in Virginia or North Carolina."
                                    if kind == "spc" else "Flash flooding is not expected in Virginia or North Carolina.")
    if topc:
        who = [s for s in ("VA", "NC") if best[s][0] == topv]
        meaning = f"Highest risk: {topc[2]} in {' and '.join(who)}. " + meaning
    cv = Canvas(cfg)
    title = "SEVERE WEATHER OUTLOOK" if kind == "spc" else "EXCESSIVE RAINFALL OUTLOOK"
    center = "STORM PREDICTION CENTER" if kind == "spc" else "WEATHER PREDICTION CENTER"
    cv.header(title, f"VA & NC  ·  DAY {day}  ·  {_day_name(day, feats, pkg, cfg)}  ·  {center}")
    (mx, my, mw, mh), pbox = cv.split()
    layers = [(_rgb(f["color"]), f["polys"]) for f in sorted(shown, key=lambda f: f["level"])]
    _paste_rounded(cv, stencil_map(mw, mh, cfg, layers), mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    chips = [(_rgb(c[3]), f"{c[0]} {c[1]}") for c in cats if c[0]]
    _panel(cv, pbox, "HIGHEST RISK IN EACH STATE", cards, meaning,
           lambda c, x, y, w: _legend_chips(c, x, y, w, chips))
    cv.footer(pkg, source=_src(pkg, "NOAA " + center.title()))
    return cv


QPF_STEPS = [t for t, _ in outlooks.QPF_COLORS]


def _qpf_range(lo, vals):
    hi = next((v for v in vals if v > lo + 1e-6), None)
    return f'{lo:g}–{hi:g}"' if hi else f'{lo:g}"+'


def _qpf_graphic(q, pkg, cfg):
    feats, period = q["features"], q["period"]
    a, _, b = period.partition("-")
    span = f"DAYS {a}-{b} TOTAL" if b else f"DAY {a} TOTAL"
    vals = sorted({f["value"] for f in feats})
    tz = ZoneInfo(cfg["timezone"])
    end = (datetime.fromisoformat(pkg["issued"]).astimezone(timezone.utc) - timedelta(hours=12)).date() + \
        timedelta(days=int(b or a))
    per = {"VA": [], "NC": []}
    for k in _counties():
        inside = [f["value"] for f in feats if outlooks.contains(f["polys"], k["lon"], k["lat"])]
        per[k["st"]].append((max(inside) if inside else 0.0, k))
    cards = []
    for st in ("VA", "NC"):
        vs = [v for v, _ in per[st]]
        mx_ = max(vs) if vs else 0
        avg = sum(vs) / len(vs) if vs else 0
        wet = max((k for v, k in per[st] if v == mx_), key=lambda k: 0, default=None)
        if mx_ > 0:
            cards.append({"st": st, "value": "UP TO " + _qpf_range(mx_, vals), "col": outlooks.qpf_color(mx_),
                          "detail": f"STATE AVERAGE ~{avg:.1f}\"  ·  {round(100 * sum(v > 0 for v in vs) / len(vs))}% OF COUNTIES WET"})
        else:
            cards.append({"st": st, "value": "LITTLE OR NO RAIN", "col": None, "detail": f"NO MEASURABLE TOTALS FOR {st}"})
    top = max((c for c in cards), key=lambda c: 0)
    mxall = max((max([v for v, _ in per[s]] or [0]) for s in per), default=0)
    meaning = (f"The heaviest rain over this period is {_qpf_range(mxall, vals).replace('–', ' to ').replace(chr(34) + '+', chr(34) + ' or more')}. "
               "Totals are the WPC forecast for the whole period, not a single storm.") if mxall else \
        "Little or no rain is expected in Virginia or North Carolina over this period."
    cv = Canvas(cfg)
    cv.header("RAINFALL FORECAST", f"VA & NC  ·  {span}  ·  THROUGH {end.strftime('%a %b').upper()} {end.day}")
    (mx, my, mw, mh), pbox = cv.split()
    layers = [(outlooks.qpf_color(f["value"]), f["polys"]) for f in sorted(feats, key=lambda f: f["value"])]
    _paste_rounded(cv, stencil_map(mw, mh, cfg, layers), mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))

    def legend(c, x, y, w):
        top_in = 12.0
        xin = lambda v: x + w * min(v, top_in) / top_in
        edges = QPF_STEPS + [top_in]
        for (t, col), nxt in zip(outlooks.QPF_COLORS, edges[1:]):
            c.rect(xin(t), y + 6, xin(nxt) - xin(t) + 0.5, 20, (*col, 255))
        for i in range(0, 13, 2):
            c.line([(xin(i), y + 26), (xin(i), y + 33)], (255, 255, 255, 220), 2)
            c.text(xin(i), y + 54, str(i), 17, "bold", anchor="ms")
        c.text(x + w, y + 70, "INCHES", 15, "bold", C["muted"], anchor="rs")

    _panel(cv, pbox, "RAINFALL TOTALS BY STATE", cards, meaning, legend)
    cv.footer(pkg, source=_src(pkg, "NOAA Weather Prediction Center"))
    return cv


def _spc48_graphic(spc48, pkg, cfg):
    """Day 4-8 severe outlook: one VA + NC stencil per day (15% / 30% areas), in a grid."""
    cv = Canvas(cfg)
    now = datetime.fromisoformat(pkg["issued"]).astimezone(timezone.utc)
    tz = ZoneInfo(cfg["timezone"])
    d1 = outlooks.outlook_day_date(1, now)
    cv.header("SEVERE WEATHER OUTLOOK", "VA & NC  ·  DAYS 4-8  ·  STORM PREDICTION CENTER")
    days = sorted(spc48)
    cols = 2 if cv.tall else 3
    rows_n = math.ceil((len(days) + 1) / cols)
    gap = 18
    top, bot = cv.top, cv.bottom - 4
    cw = (cv.W - 2 * cv.M - gap * (cols - 1)) / cols
    ch = (bot - top - gap * (rows_n - 1)) / rows_n
    cs = _counties()
    cells = []
    for i, dn in enumerate(days):
        feats = spc48[dn]
        r, c = divmod(i, cols)
        x, y = cv.M + c * (cw + gap), top + r * (ch + gap)
        dt = d1 + timedelta(days=dn - 1)
        cv.rect(x, y, cw, ch, C["panel"], r=16)
        cv.text(x + 22, y + 34, f"DAY {dn}", 28, "bold", anchor="lm")
        cv.text(x + cw - 22, y + 34, f"{dt.strftime('%a').upper()} {dt.strftime('%b').upper()} {dt.day}", 24, "bold", C["muted"], anchor="rm")
        mh = ch - 62 - 44
        lay = stencil_map(cw - 24, mh, cfg, [(_rgb(f["color"]), f["polys"]) for f in feats], cities=[], tags=False, alpha=0.95)
        _paste_rounded(cv, lay, x + 12, y + 56)
        top_lv = max([k for k in (1, 2) if any(f["level"] == k for f in feats)] or [0])
        if top_lv:
            touched = {st: 0 for st in ("VA", "NC")}
            for k in cs:
                if any(outlooks.contains(f["polys"], k["lon"], k["lat"]) for f in feats):
                    touched[k["st"]] += 1
            where = " & ".join(st for st, n in touched.items() if n) or "NEAR VA / NC"
            txt, col = (f"{'30%' if top_lv == 2 else '15%'} RISK · {where}"), _rgb(next(f["color"] for f in feats if f["level"] == top_lv))
        else:
            txt, col = "NO SEVERE AREA OUTLINED", C["muted"]
        cv.text(x + 22, y + ch - 24, txt, 22, "bold", col, anchor="lm", maxw=cw - 44)
    n = len(days)  # legend / explainer in the next free cell
    r, c = divmod(n, cols)
    x, y = cv.M + c * (cw + gap), top + r * (ch + gap)
    cv.rect(x, y, cw, ch, C["panel"], r=16)
    cv.text(x + 22, y + 34, "WHAT THE COLORS MEAN", 24, "bold", C["muted"], anchor="lm")
    for j, (pct, (lab, colh)) in enumerate(sorted(outlooks.SPC48.items())):
        yy = y + 78 + j * 66
        cv.rect(x + 22, yy, 40, 40, (*_rgb(colh), 255), r=8)
        cv.text(x + 78, yy + 20, f"{lab} CHANCE OF SEVERE WEATHER", 22, "bold", anchor="lm", maxw=cw - 100)
    cv.paragraph(x + 22, y + 78 + 2 * 66 + 6, "Chance of severe storms within 25 miles of any point. No shading means predictability is too low or "
                 "severe weather is not expected.", 19, "regular", cw - 44, max_lines=5, lh=1.3, fill=C["muted"])
    cv.footer(pkg, source=_src(pkg, "NOAA Storm Prediction Center"))
    return cv


def outlook_graphics(pkg, cfg):
    data = pkg.get("_outlooks")
    if not data:
        return None
    out = []
    if (data.get("spc48") or {}) and cfg.get("spc_day48", True) and len(data["spc48"]) >= 3:
        out.append(("state_spc_day4_8", _spc48_graphic(data["spc48"], pkg, cfg)))
    for kind, key in (("spc", "state_spc_days"), ("ero", "state_ero_days")):
        for day, feats in sorted((data.get(kind) or {}).items(), key=lambda kv: int(kv[0])):
            if int(day) in (cfg.get(key) or [1, 2, 3]):
                out.append((f"state_{kind}_day{int(day)}", _cat_graphic(kind, int(day), feats, pkg, cfg)))
    maps = dict(data.get("qpf_maps") or {})
    for period, q in sorted(maps.items(), key=lambda kv: int(kv[0].split("-")[-1])):
        if q.get("features") and period in (cfg.get("state_qpf_periods") or ["1-2", "1-3", "1-5", "1-7"]):
            a, _, b = period.partition("-")
            tag = f"{int(b) - int(a) + 1}day" if b else f"day{a}"
            out.append((f"state_qpf_{tag}", _qpf_graphic(q, pkg, cfg)))
    return out or None


# ------------------------------------------------------------------ NDFD temperatures
def fetch_temps(cfg, cache_dir, now_utc, debug=False):
    """-> {"lat","lon","highs":{date:grid},"lows":{date:grid},"errors"} (deg F) over VA + NC."""
    from . import ndfdmap
    out = {"errors": []}
    try:
        import eccodes  # noqa: F401
        import numpy as np  # noqa: F401
    except Exception:
        out["errors"].append("state temperature maps need ecCodes + numpy")
        print("  ! " + out["errors"][-1])
        return out
    tz = ZoneInfo(cfg["timezone"])
    box = (-90.0, -70.0, 30.0, 43.0)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    lnow = now_utc.astimezone(tz)
    first = lnow.date() if lnow.hour < 17 else lnow.date() + timedelta(days=1)
    last = None
    for sector in cfg.get("ndfd_sectors", ["midatlan", "conus"]):
        try:
            highs, lows, lat, lon = {}, {}, None, None
            for elem in ("maxt", "mint"):
                for vp in ("001-003", "004-007"):
                    path = ndfdmap._download(ndfdmap.TGFTP.format(sector=sector, vp=vp, elem=elem),
                                             cache / f"ndfd_{sector}_{vp}_{elem}.bin", cfg["user_agent"])
                    for valid, la, lo, v in ndfdmap._messages(path, box):
                        lat, lon = la, lo
                        lt = valid.astimezone(tz)
                        f = (v - 273.15) * 9 / 5 + 32
                        if elem == "maxt":
                            day = lt.date() if lt.hour >= 5 else lt.date() - timedelta(days=1)
                            highs.setdefault(day, f)
                        else:
                            day = lt.date() + (timedelta(days=1) if lt.hour >= 12 else timedelta())
                            lows.setdefault(day, f)
            if lat is None or not ndfdmap._covers(lat, lon, VIEW):
                raise RuntimeError(f"{sector} sector doesn't cover VA + NC")
            highs = {d: g for d, g in highs.items() if d >= first}
            lows = {d: g for d, g in lows.items() if d >= first}
            if not highs and not lows:
                raise RuntimeError("no highs/lows in the forecast")
            return {"lat": lat, "lon": lon, "highs": highs, "lows": lows, "errors": []}
        except Exception as ex:
            last = ex
            if debug:
                print(f"   [state temps] {sector} failed: {ex}")
    out["errors"].append(f"NDFD state temperatures: {last}")
    print(f"  ! state temperature maps unavailable: {last}")
    return out


def sample_temps(now_utc, tz):
    import numpy as np
    lat = np.linspace(30.0, 43.0, 300)[:, None] * np.ones((1, 330))
    lon = np.ones((300, 1)) * np.linspace(-90.0, -70.0, 330)[None, :]
    elev = np.clip((-78.5 - lon) / 4.0, 0, 1) * 7 + np.clip((lat - 35) / 4, 0, 1) * 3  # cooler mountains / north
    coast = np.clip((lon + 77.5) / 2.5, 0, 1)
    today = now_utc.astimezone(tz).date()
    highs = {today + timedelta(days=i): h - elev + 2 * coast + 1.5 * np.sin(lon * 1.3) * np.cos(lat * 1.7)
             for i, h in enumerate((74, 70, 62, 58))}
    lows = {today + timedelta(days=i): l - 1.4 * elev + 2 * coast + np.sin(lon * 1.1) * np.cos(lat * 1.4)
            for i, l in enumerate((52, 48, 42, 38))}
    return {"lat": lat, "lon": lon, "highs": highs, "lows": lows, "errors": []}


def _crop(td, grid):
    import numpy as np
    w, e, s, n = VIEW
    m = (td["lon"] >= w - 3.2) & (td["lon"] <= e + 3.2) & (td["lat"] >= s - 3.2) & (td["lat"] <= n + 3.2)
    r, c = np.where(m)
    sl = (slice(r.min(), r.max() + 1), slice(c.min(), c.max() + 1))
    return td["lat"][sl], td["lon"][sl], grid[sl]


def _nearest(lat, lon, grid, la, lo):
    import numpy as np
    d = (lat - la) ** 2 + ((lon - lo) * math.cos(math.radians(la))) ** 2
    j, i = np.unravel_index(np.nanargmin(d), d.shape)
    v = grid[j, i]
    return None if v != v else float(v)


def _temp_graphic(td, kind, idx, date, pkg, cfg, clean=False):
    """kind: "highs" | "lows"."""
    from .ndfdmap import _cell_painter
    hi = kind == "highs"
    lat, lon, grid = _crop(td, td[kind][date])
    bins = [(t - 0.01 if t > 0 else -999, temp_color(t + 1)) for t in range(-10, 121, 2)]
    bins[0] = (-999, bins[0][1])
    paint = _cell_painter({"lat": lat, "lon": lon, "val": grid}, bins, alpha=255, smooth=1)
    per = {"VA": [], "NC": []}
    for k in _counties():
        v = _nearest(lat, lon, grid, k["lat"], k["lon"])
        if v is not None:
            per[k["st"]].append((v, k))
    cities = []
    for name, la, lo, tier in CITIES:
        v = _nearest(lat, lon, grid, la, lo)
        if v is not None:
            cities.append((name, la, lo, tier, f"{round(v)}°"))
    word = "HIGH" if hi else "LOW"
    cards = []
    for st in ("VA", "NC"):
        pts = per[st]
        if not pts:
            continue
        top, bot = max(pts, key=lambda p: p[0]), min(pts, key=lambda p: p[0])
        a, b = round(bot[0]), round(top[0])
        cards.append({"st": st, "value": f"{word}S {a}° – {b}°" if a != b else f"{word}S {a}°",
                      "col": temp_color(top[0] if hi else (a + b) / 2),
                      "detail": f"{'WARMEST' if hi else 'MILDEST'}: {top[1]['c']['name'].upper()} {b}°  ·  "
                                f"{'COOLEST' if hi else 'COLDEST'}: {bot[1]['c']['name'].upper()} {a}°"})
    allv = [v for s in per.values() for v, _ in s]
    mn, mxv = round(min(allv)), round(max(allv))
    tz = ZoneInfo(cfg["timezone"])
    today = datetime.fromisoformat(pkg["issued"]).astimezone(tz).date()
    nm = "TODAY" if date == today else "TOMORROW" if date == today + timedelta(days=1) else date.strftime("%A").upper()
    if hi:
        meaning = f"Afternoon highs range from {mn}° to {mxv}° across Virginia and North Carolina. "
        meaning += "Mountains and the higher terrain run coolest; the coast and Piedmont run warmer." if mxv - mn > 8 else \
            "Temperatures are close to uniform statewide."
    else:
        meaning = f"Overnight lows range from {mn}° to {mxv}°. "
        meaning += "Valleys and the mountains get coldest; the coast and cities stay mildest." if mxv - mn > 8 else \
            "Lows are close to uniform statewide."
    if mn <= 32:
        meaning += " Freezing temperatures are possible in the coldest spots."
    cv = Canvas(cfg)
    cv.header(f"{'HIGH' if hi else 'LOW'} TEMPERATURES", f"VA & NC  ·  {nm}, {date.strftime('%b').upper()} {date.day}  ·  NWS NDFD")
    if clean:  # banner, logo, legend and footer, but no side panel: the stencil is centered across the graphic
        lo_, hi_ = 10 * math.floor((mn - 3) / 10), 10 * math.ceil((mxv + 3) / 10)
        mx, my, mw, mh = cv.M, 150, cv.W - 2 * cv.M, cv.H - 150 - 28
        lay = stencil_map(mw, mh, cfg, painter=paint, cities=cities, alpha=0.96, bg=(0, 0, 0, 0),
                          view=cfg.get("state_clean_view") or (-84.12, -74.98, 33.585, 39.765))
        base = cv.img.convert("RGBA")
        base.alpha_composite(lay, (z(mx), z(my)))
        cv.img = base.convert("RGB")
        cv.d = ImageDraw.Draw(cv.img, "RGBA")
        lw = 520 if not cv.tall else min(cv.W - 2 * cv.M, 560)
        cv.rect(cv.W - cv.M - lw - 14, cv.H - 130, lw + 28, 96, (13, 21, 38, 215), r=12)
        _bar(cv, cv.W - cv.M - lw, cv.H - 126, lw, temp_color, lo_, hi_, "°F", list(range(lo_, hi_ + 1, 10)))
        cv.footer(pkg, source=_src(pkg, "NWS NDFD"))
        return cv
    (mx, my, mw, mh), pbox = cv.split()
    _paste_rounded(cv, stencil_map(mw, mh, cfg, painter=paint, cities=cities, alpha=0.96), mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    lo_, hi_ = 10 * math.floor((mn - 3) / 10), 10 * math.ceil((mxv + 3) / 10)
    legend = lambda c, x, y, w: _bar(c, x, y, w, temp_color, lo_, hi_, "°F", list(range(lo_, hi_ + 1, 10)))
    _panel(cv, pbox, f"{word} TEMPERATURE BY STATE", cards, meaning, legend)
    cv.footer(pkg, source=_src(pkg, "NWS NDFD"))
    return cv


def temp_graphics(pkg, cfg):
    td = pkg.get("_statetemps") or {}
    if "highs" not in td:
        return None
    out = []
    n = cfg.get("state_temp_days", 3)
    for kind in ("highs", "lows"):
        for i, d in enumerate(sorted(td[kind])[:n], 1):
            out.append((f"state_{kind}_day{i}", _temp_graphic(td, kind, i, d, pkg, cfg)))
            if cfg.get("state_temp_clean", True):
                out.append((f"state_{kind}_day{i}_map", _temp_graphic(td, kind, i, d, pkg, cfg, clean=True)))
    return out or None
