"""SPC Day 1 / Day 2 tornado, damaging-wind and large-hail outlooks, as
   spc_<hazard>_day<N>   one graphic per hazard per day: VA + NC stencil map in SPC's probability colors,
                         hatching where significant severe is possible, highest risk in each state, plain-language meaning
   spc_3panel_day<N>     three side-by-side Hampton Roads maps (Tornado / High Wind / Large Hail) with a LOW-ELEVATED-
                         MEDIUM-HIGH key, a risk call-out under each map and the date along the bottom.
Data comes from the SPC probability polygons already fetched with the outlooks (pkg["_outlooks"]["probs"]).
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageChops, ImageDraw

from . import outlookmap, outlooks, spchazards, statemaps
from .alertmap import _paste_rounded
from .theme import C, Canvas, z

HAZ = {  # key -> (name on the single graphics, 3-panel title, single-graphic file key, probability colors)
    "torn": ("TORNADO", "TORNADO", "tornado"),
    "wind": ("DAMAGING WIND", "HIGH WIND", "wind"),
    "hail": ("LARGE HAIL", "LARGE HAIL", "hail"),
}
PROB_COLORS = {  # SPC's official probability colors
    "torn": [(2, (0, 139, 0)), (5, (139, 71, 38)), (10, (255, 200, 0)), (15, (255, 0, 0)), (30, (255, 0, 255)), (45, (145, 44, 238)), (60, (16, 78, 139))],
    "wind": [(5, (139, 71, 38)), (15, (255, 200, 0)), (30, (255, 0, 0)), (45, (255, 0, 255)), (60, (145, 44, 238))],
    "hail": [(5, (139, 71, 38)), (15, (255, 200, 0)), (30, (255, 0, 0)), (45, (255, 0, 255)), (60, (145, 44, 238))],
}
FOUR = [("LOW", (255, 214, 0)), ("ELEVATED", (255, 140, 0)), ("MEDIUM", (235, 40, 40)), ("HIGH", (255, 40, 255))]
FOUR_AT = {"torn": [2, 5, 10, 15], "wind": [5, 15, 30, 45], "hail": [5, 15, 30, 45]}  # % that starts each of the four levels
HR_VIEW = (-77.1, -75.5, 36.45, 37.45)


def _color(key, p):
    col = None
    for t, c in PROB_COLORS[key]:
        if p >= t:
            col = c
    return col


def _lum(c):
    return 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]


def _day_info(data, day, pkg, cfg):
    now = datetime.fromisoformat(pkg["issued"]).astimezone(timezone.utc)
    feats = (data.get("spc") or {}).get(day) or (data.get("spc") or {}).get(str(day)) or []
    t = feats[0].get("times") if feats else None
    dt = outlooks.outlook_day_date(day, now, t)
    today = now.astimezone(ZoneInfo(cfg["timezone"])).date()
    nm = "TODAY" if dt == today else "TOMORROW" if dt == today + timedelta(days=1) else dt.strftime("%A").upper()
    return dt, f"{nm}, {dt.strftime('%b').upper()} {dt.day}"


def _src(pkg):
    return "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NOAA Storm Prediction Center"


def _probs(data, day):
    p = data.get("probs") or {}
    return p.get(day) or p.get(str(day)) or {}


# ------------------------------------------------------------------ one hazard, VA + NC
def _hatch(sig):
    def paint(d, proj):
        base = d._image
        W, H = base.size
        m = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(m)
        for polys in sig:
            for p in polys:
                md.polygon([proj(x, y) for x, y, *_ in p[0]], fill=255)
        hat = Image.new("L", (W, H), 0)
        hd = ImageDraw.Draw(hat)
        step = z(12)
        for k in range(-H, W, step):
            hd.line([(k, H), (k + H, 0)], fill=255, width=max(2, z(2.4)))
        mask = ImageChops.multiply(m, hat)
        layer = Image.new("RGBA", (W, H), (10, 16, 30, 255))
        layer.putalpha(mask.point(lambda v: int(v * 0.9)))
        base.alpha_composite(layer)
    return paint


def _hazard_graphic(key, day, data, pkg, cfg):
    name, _, _ = HAZ[key]
    d = _probs(data, day).get(key)
    if d is None:
        return None
    areas = sorted(d.get("areas") or [], key=lambda a: a["prob"])
    sig = d.get("sig") or []
    cs = statemaps._counties()
    best = {"VA": (0, 0), "NC": (0, 0)}
    tot = {"VA": 0, "NC": 0}
    for k in cs:
        tot[k["st"]] += 1
        ps = [a["prob"] for a in areas if outlooks.contains(a["polys"], k["lon"], k["lat"])]
        if ps:
            b = best[k["st"]]
            best[k["st"]] = (max(b[0], max(ps)), b[1] + 1)
    cards = []
    for st in ("VA", "NC"):
        p, n = best[st]
        if p:
            cards.append({"st": st, "value": f"{p}%  ·  {_level_word(key, p)}", "col": _color(key, p),
                          "detail": f"RISK AREA TOUCHES {round(100 * n / max(1, tot[st]))}% OF {st} COUNTIES"})
        else:
            cards.append({"st": st, "value": "NO RISK", "col": None, "detail": "NOTHING IN THE OUTLOOK FOR " + st})
    top = max(best["VA"][0], best["NC"][0])
    word = spchazards.WORDING[key]
    meaning = next(t for m, _, t in reversed(word[1]) if top >= m)
    if sig:
        meaning += f" Hatching marks where significant severe weather is possible: {word[2][0].lower() + word[2][1:]}"
    dt, label = _day_info(data, day, pkg, cfg)
    cv = Canvas(cfg)
    cv.header(f"{name} OUTLOOK", f"VA & NC  ·  DAY {day}  ·  {label}  ·  STORM PREDICTION CENTER")
    (mx, my, mw, mh), pbox = cv.split()
    layers = [(_color(key, a["prob"]) or (120, 140, 170), a["polys"]) for a in areas if a["prob"] >= PROB_COLORS[key][0][0]]
    _paste_rounded(cv, statemaps.stencil_map(mw, mh, cfg, layers, painter=_hatch(sig) if sig else None), mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    chips = [(c, f"{t}%") for t, c in PROB_COLORS[key]] + ([((60, 72, 96), "HATCH = SIG.")] if sig else [])
    statemaps._panel(cv, pbox, "HIGHEST CHANCE IN EACH STATE", cards, meaning,
                     lambda c, x, y, w: statemaps._legend_chips(c, x, y, w, chips))
    cv.footer(pkg, source=_src(pkg))
    return cv


def _level_word(key, p):
    return next(l for m, l, _ in reversed(spchazards.WORDING[key][1]) if p >= m)


# ------------------------------------------------------------------ three panels, Hampton Roads
def _four_level(key, p):
    lv = -1
    for i, t in enumerate(FOUR_AT[key]):
        if p >= t:
            lv = i
    return lv


def _hr_risk(key, areas, view):
    """-> (level 0-3 or -1, share of the view it covers, (dx, dy) centre offset in -1..1)."""
    w, e, s, n = view
    pts = [(w + (e - w) * (i + 0.5) / 12, s + (n - s) * (j + 0.5) / 12) for i in range(12) for j in range(12)]
    levels = []
    for lo, la in pts:
        ps = [a["prob"] for a in areas if outlooks.contains(a["polys"], lo, la)]
        levels.append(_four_level(key, max(ps)) if ps else -1)
    top = max(levels)
    if top < 0:
        return -1, 0.0, (0, 0)
    hit = [(pts[i], levels[i]) for i in range(len(pts)) if levels[i] == top]
    frac = len(hit) / len(pts)
    cx = sum(p[0][0] for p in hit) / len(hit)
    cy = sum(p[0][1] for p in hit) / len(hit)
    return top, frac, ((cx - (w + e) / 2) / ((e - w) / 2), (cy - (s + n) / 2) / ((n - s) / 2))


def _where(frac, off):
    if frac >= 0.8:
        return "ENTIRE AREA"
    dx, dy = off
    ns = "NORTH" if dy > 0.25 else "SOUTH" if dy < -0.25 else ""
    ew = "EAST" if dx > 0.25 else "WEST" if dx < -0.25 else ""
    d = (ns + ("" if not (ns and ew) else "") + ew).strip()
    if ns and ew:
        d = ns + ew.lower()
        d = {"NORTHeast": "NORTHEAST", "NORTHwest": "NORTHWEST", "SOUTHeast": "SOUTHEAST", "SOUTHwest": "SOUTHWEST"}[d]
    if not d:
        return "PARTS OF THE AREA" if frac >= 0.2 else "CENTRAL PART"
    return (d + " PART") if frac < 0.5 else d


def _three_panel(day, data, pkg, cfg):
    probs = _probs(data, day)
    if not any(k in probs for k in HAZ):
        return None
    view = tuple(cfg.get("spc_hr_view") or HR_VIEW)
    dt, label = _day_info(data, day, pkg, cfg)
    cv = Canvas(cfg)
    cv.header("SEVERE WEATHER RISKS", f"HAMPTON ROADS  ·  DAY {day}  ·  {label}")
    M, gap = cv.M, 22
    top, bot = cv.top, cv.bottom - 70
    if cv.tall:
        ph = (bot - top - 2 * gap) / 3
        boxes = [(M, top + i * (ph + gap), cv.W - 2 * M, ph) for i in range(3)]
    else:
        pw = (cv.W - 2 * M - 2 * gap) / 3
        boxes = [(M + i * (pw + gap), top, pw, bot - top) for i in range(3)]
    loc = cfg["location"]
    for (key, (_, title, _)), (px, py, pw_, ph_) in zip(HAZ.items(), boxes):
        d = probs.get(key) or {"areas": [], "sig": []}
        areas = d.get("areas") or []
        lvl, frac, off = _hr_risk(key, areas, view)
        cv.rect(px, py, pw_, ph_, C["panel"], r=16)
        if cv.tall:
            mw_, mh_ = pw_ * 0.5 - 12, ph_ - 20
            mx, my = px + 10, py + 10
            rx, rw = px + pw_ * 0.5 + 6, pw_ * 0.5 - 16
            ry, rh = py + 10, ph_ - 20
        else:
            mw_, mh_ = pw_ - 20, ph_ - 44 - 78 - 134 - 40
            mx, my = px + 10, py + 10
            rx, rw = px + 10, pw_ - 20
            ry, rh = my + mh_ + 10, ph_ - mh_ - 30
        by_level = [[] for _ in FOUR]
        for a in sorted(areas, key=lambda a: a["prob"]):
            li = _four_level(key, a["prob"])
            if li >= 0:
                by_level[li].append(a["polys"])
        layers = [(FOUR[i][1], [p for polys in by_level[i] for p in polys]) for i in range(4) if by_level[i]]
        mp = outlookmap.draw_map(layers, mw_, mh_, cfg, outline=True, view=view, water_alpha=0.3,
                                 skip_pts=[(loc["lat"], loc["lon"])])
        _paste_rounded(cv, mp, mx, my)
        # key strip, title, call-out (stacked in the right column on tall graphics)
        sh = 40
        sy = ry if cv.tall else ry
        seg = rw / 4
        for i, (lab, col) in enumerate(FOUR):
            cv.rect(rx + i * seg, sy, seg - 2, sh, (*col, 255), r=6 if i in (0, 3) else 0)
            cv.text(rx + i * seg + seg / 2 - 1, sy + sh / 2, lab, 15 if not cv.tall else 13, "bold",
                    (13, 21, 38) if _lum(col) > 120 else (255, 255, 255), anchor="mm", maxw=seg - 8)
        ty = sy + sh + 8
        th = 74 if not cv.tall else 80
        cv.rect(rx, ty, rw, th, (10, 16, 30, 255), r=10)
        cv.text(rx + rw / 2, ty + th / 2, title, 42 if not cv.tall else 34, "bold", anchor="mm", maxw=rw - 24)
        by = ty + th + 8
        bh = (ry + rh) - by
        col = FOUR[lvl][1] if lvl >= 0 else None
        cv.rect(rx, by, rw, bh, (244, 247, 252, 255), r=10)
        if col:
            cv.rect(rx, by, 10, bh, (*col, 255), r=4)
        if lvl < 0:
            big, small = "NO RISK", "NOT IN THE OUTLOOK FOR THE AREA"
        else:
            nm = FOUR[lvl][0]
            big = nm + " RISK"
            small = _where(frac, off) if frac < 0.8 else "ENTIRE AREA"
            if any(outlooks.contains(polys, loc["lon"], loc["lat"]) for polys in (d.get("sig") or [])):
                small += "  ·  SIGNIFICANT POSSIBLE"
        cv.text(rx + rw / 2 + 4, by + bh * 0.4, big, 36 if not cv.tall else 30, "bold", (13, 21, 38), anchor="mm", maxw=rw - 40)
        cv.text(rx + rw / 2 + 4, by + bh * 0.76, small, 19 if not cv.tall else 17, "bold", (70, 84, 110), anchor="mm", maxw=rw - 40)
    # date bar
    cv.rect(M, bot + 14, cv.W - 2 * M, 52, (255, 255, 255, 24), r=12)
    cv.text(cv.W / 2, bot + 40, f"{dt:%A}   ·   {dt:%B} {dt.day}, {dt.year}", 34, "bold", anchor="mm")
    cv.footer(pkg, source=_src(pkg))
    return cv


# ------------------------------------------------------------------ registry entries
def _days(data, cfg, key):
    return [int(d) for d in (cfg.get(key) or [1, 2]) if int(d) in (1, 2) and (_probs(data, int(d)))]


def hazard_graphics(pkg, cfg):
    data = pkg.get("_outlooks")
    if not data:
        return None
    out = []
    for day in _days(data, cfg, "spc_hazard_days"):
        for key, (_, _, fk) in HAZ.items():
            cv = _hazard_graphic(key, day, data, pkg, cfg)
            if cv:
                out.append((f"spc_{fk}_day{day}", cv))
    return out or None


def three_panel_graphics(pkg, cfg):
    data = pkg.get("_outlooks")
    if not data:
        return None
    out = []
    for day in _days(data, cfg, "spc_3panel_days"):
        cv = _three_panel(day, data, pkg, cfg)
        if cv:
            out.append((f"spc_3panel_day{day}", cv))
    return out or None
