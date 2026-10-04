"""Hurricane-threat graphics, written to output/<run>/Tropical/ (and output/latest/Tropical/).
Made only while a storm threatens the area (see tropical.is_threat). Numbered so they sort in briefing order.

New graphics: storm snapshot, local track & cone, intensity forecast, advisory schedule, wind chances, wind
arrival, wind timeline, storm surge map, Sewells Point surge+tide vs history, tropical watches/warnings map,
NWS hurricane statement, threat matrix, evacuations (manual), preparedness checklist, storm timeline,
history comparison, closest approach, power outages (manual).
Storm-mode copies (with a storm ribbon): peak gusts, high tides, storm rainfall, excessive rainfall, rivers,
tornado risk, and the after-storm rain / wind / storm reports.
"""
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from . import alertinfo, outlooks, tropical as T
from .alertmap import _paste_rounded, draw_cities
from .extras import BAD, GOOD, NEUTRAL, OK_, SEVERE, WARN, _ink, area, grid, pill, tile
from .outlookmap import _legend_chips, _view, draw_map
from .theme import C, Canvas, font, z

CAT_COL = {0: (90, 170, 255), 1: (255, 220, 60), 2: (255, 160, 40), 3: (240, 80, 40), 4: (220, 30, 60), 5: (200, 70, 210)}
TS_COL = (110, 210, 140)
WW_COL = {"HWR": ((230, 30, 40), "HURRICANE WARNING"), "HWA": ((255, 120, 200), "HURRICANE WATCH"),
          "TWR": ((40, 110, 255), "TROPICAL STORM WARNING"), "TWA": ((250, 220, 60), "TROPICAL STORM WATCH"),
          "SSW": ((200, 70, 210), "STORM SURGE WARNING"), "SSA": ((210, 160, 255), "STORM SURGE WATCH")}
LEVEL_COL = {"None": NEUTRAL, "Low": (90, 170, 255), "Elevated": OK_, "Moderate": WARN, "High": BAD, "Extreme": SEVERE,
             "Limited": OK_, "Significant": WARN, "Extensive": BAD, "Devastating": SEVERE}
PROB_COLS = [(5, (40, 120, 70)), (10, (60, 160, 80)), (20, (110, 200, 90)), (30, (220, 220, 60)), (40, (250, 190, 60)),
             (50, (250, 150, 40)), (60, (240, 110, 40)), (70, (230, 60, 40)), (80, (170, 30, 40)), (90, (150, 60, 190))]
TROP_EVENTS = ["Storm Surge Warning", "Hurricane Warning", "Storm Surge Watch", "Hurricane Watch",
               "Tropical Storm Warning", "Tropical Storm Watch", "Extreme Wind Warning", "Hurricane Local Statement"]


# ------------------------------------------------------------------ helpers
def _tz(cfg):
    return ZoneInfo(cfg["timezone"])


def _base(t):
    s = t.get("storm") or {}
    try:
        return datetime.fromisoformat(str(s.get("updated")).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def pt_time(p, base, tz):
    v = p.get("valid") or ""
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(tz)
    except ValueError:
        return (base + timedelta(hours=p.get("tau") or 0)).astimezone(tz)


def _when(dt):
    return dt.strftime("%a %-I %p").upper() if dt else "--"


def _storm_title(t):
    s = t.get("storm") or {}
    return f"{(s.get('kind') or 'Storm').upper()} {(s.get('name') or '').upper()}".strip()


def _col(kt):
    c = T.saffir(kt)
    return CAT_COL[c] if c else (TS_COL if (kt or 0) >= 34 else CAT_COL[0])


def _pcol(p):
    c = NEUTRAL
    for t_, cc in PROB_COLS:
        if p >= t_:
            c = cc
    return c


def ribbon(cv, t):
    txt = _storm_title(t)
    w = cv.width(txt, 18, "bold") + 30
    x, y = cv.W - cv.M - w, cv.H - 58
    cv.rect(x, y, w, 34, (*BAD, 255), r=17)
    cv.text(x + w / 2, y + 17, txt, 18, "bold", anchor="mm")


def _footer(cv, pkg, t, src):
    cv.footer(pkg, source=("SAMPLE DATA" if t.get("sample") else src))
    ribbon(cv, t)


def _proj(pw, ph, box):
    W_, H_ = z(pw), z(ph)
    w, e, s, n = _view(pw, ph, box)
    return W_, H_, (lambda x, y: ((x - w) / (e - w) * W_, (n - y) / (n - s) * H_)), (w, e, s, n)


def base_map(pw, ph, box, cfg, cities=True):
    """Gulf/Atlantic/eastern US basemap (offline): land, states, lakes."""
    from .cpcmap import EAST_CITIES, base
    W_, H_, P, view = _proj(pw, ph, box)
    lay = Image.new("RGBA", (W_, H_), (17, 27, 47, 255))
    d = ImageDraw.Draw(lay, "RGBA")
    b = base()
    for p in b["land"]:
        d.polygon([P(x, y) for x, y in p[0]], fill=(29, 41, 63, 255))
    for st in b["states"]:
        for p in st["polys"]:
            d.polygon([P(x, y) for x, y in p[0]], fill=(38, 55, 84, 255), outline=(98, 120, 152, 255))
    for p in b["lakes"]:
        d.polygon([P(x, y) for x, y in p[0]], fill=(17, 27, 47, 255))
    return lay, P, view


def _poly(d, P, polys, fill=None, outline=None, width=1):
    for p in polys:
        pts = [P(*pt[:2]) for pt in p[0]]
        if fill:
            d.polygon(pts, fill=fill)
        if outline:
            d.line(pts + [pts[0]], fill=outline, width=width, joint="curve")


def _storm_icon(d, x, y, r, col):
    d.ellipse([x - r, y - r, x + r, y + r], fill=(*col, 255), outline=(255, 255, 255, 255), width=max(1, int(r / 5)))
    d.arc([x - 2 * r, y - 2 * r, x + 0.2 * r, y + 0.2 * r], 270, 360, fill=(*col, 255), width=max(2, int(r / 3)))
    d.arc([x - 0.2 * r, y - 0.2 * r, x + 2 * r, y + 2 * r], 90, 180, fill=(*col, 255), width=max(2, int(r / 3)))


def _norfolk(d, P, cfg, label=True):
    lx, ly = P(cfg["location"]["lon"], cfg["location"]["lat"])
    d.regular_polygon((lx, ly, z(8)), 4, rotation=45, fill=(255, 255, 255, 255), outline=(13, 21, 38, 255))
    if label:
        d.text((lx - z(12), ly), "NORFOLK", font=font("bold", 16), fill=(255, 255, 255, 255), anchor="rm",
               stroke_width=z(3), stroke_fill=(13, 21, 38, 255))


def _frame(cv, lay, x, y, w, h):
    _paste_rounded(cv, lay, x, y)
    cv.d.rounded_rectangle([z(x), z(y), z(x + w), z(y + h)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))


def _split(cv):
    (mx, my, mw, mh), panel = cv.split()
    return (mx, my, mw, mh), panel


def _rows_panel(cv, box, title, rows, head=None):
    """rows: [(label, value, color)]"""
    x, y, w, h = box
    cv.rect(x, y, w, h, C["panel"], r=18)
    yy = y + 24
    if head:
        lab, val, col, sub = head
        cv.text(x + 26, yy, lab, 21, "bold", C["muted"], anchor="lt")
        cv.rect(x + 26, yy + 34, w - 52, 76, (*col, 255), r=12)
        cv.text(x + w / 2, yy + 72, val, 36, "bold", _ink(col), anchor="mm", maxw=w - 80)
        yy += 126
        if sub:
            used = cv.paragraph(x + 26, yy, sub, 22, "regular", w - 52, max_lines=3, lh=1.25)
            yy += used + 14
        cv.line([(x + 26, yy), (x + w - 26, yy)], (255, 255, 255, 60), 1.5)
        yy += 14
    cv.text(x + 26, yy, title, 20, "bold", C["muted"], anchor="lt")
    yy += 36
    n = max(1, len(rows))
    ncol = 2 if w > 900 else 1
    per = -(-n // ncol)
    rh = min(54, (y + h - 14 - yy) / per)
    cw = (w - 52 - (30 if ncol == 2 else 0)) / ncol
    for k, (lab, val, col) in enumerate(rows):
        c_, r_ = divmod(k, per)
        cx, ry = x + 26 + c_ * (cw + 30), yy + r_ * rh
        if ry + rh > y + h - 6:
            break
        cv.rect(cx, ry + rh * 0.16, 18, rh * 0.68, (*col, 255) if col else (*NEUTRAL, 255), r=4)
        fs = min(25, rh * 0.5)
        cv.text(cx + 30, ry + rh / 2, lab, fs, "medium", anchor="lm", maxw=cw * 0.55)
        cv.text(cx + cw, ry + rh / 2, val, fs, "bold", anchor="rm", maxw=cw * 0.45)


def _canvas(cfg, title, sub):
    cv = Canvas(cfg)
    cv.header(title, sub)
    return cv


def track_view(t, cfg):
    loc = cfg["location"]
    lats = [loc["lat"]] + [p["lat"] for p in t.get("points") or []][:6] + [t["storm"]["lat"]]
    lons = [loc["lon"]] + [p["lon"] for p in t.get("points") or []][:6] + [t["storm"]["lon"]]
    pad = 2.5
    w, e, s, n = min(lons) - pad - 2, max(lons) + pad, min(lats) - pad, max(lats) + pad
    if e - w < (n - s) * 1.3:  # keep some width so a north-moving storm isn't a thin strip
        cx = (w + e) / 2
        w, e = cx - (n - s) * 0.65, cx + (n - s) * 0.65
    return (w, e, s, n)


# ------------------------------------------------------------------ 01 storm snapshot
def g_snapshot(t, pkg, cfg):
    s, loc, tz = t["storm"], cfg["location"], _tz(cfg)
    kt = s.get("wind_kt") or 0
    cat = T.saffir(kt)
    col = _col(kt)
    cv = _canvas(cfg, _storm_title(t), f"NHC ADVISORY  ·  {_when(_base(t).astimezone(tz))}")
    x, y, w, h = area(cv)
    dist = T.miles(loc["lat"], loc["lon"], s["lat"], s["lon"])
    dirn = T.bearing(loc["lat"], loc["lon"], s["lat"], s["lon"])
    mph = round(kt * 1.15078 / 5) * 5
    hero = (x, y, w, h * 0.38) if not cv.tall else (x, y, w, h * 0.3)
    bx, by, bw, bh = hero
    cv.rect(bx, by, bw, bh, C["panel"], r=18)
    cv.rect(bx, by, 12, bh, (*col, 255), r=6)
    cv.text(bx + 40, by + 30, "CATEGORY" if cat else "STATUS", 22, "bold", C["muted"], anchor="lt")
    cv.text(bx + 40, by + bh * 0.62, str(cat) if cat else ("TS" if kt >= 34 else "TD"), min(170, bh * 0.62), "bold", col, anchor="ls")
    cv.text(bx + bw * 0.34, by + bh * 0.42, f"{dist:,.0f} MILES {dirn}", min(64, bh * 0.22), "bold", anchor="ls", maxw=bw * 0.63)
    cv.text(bx + bw * 0.34, by + bh * 0.42 + 46, "OF NORFOLK", 24, "bold", C["muted"], anchor="ls")
    cv.text(bx + bw * 0.34, by + bh * 0.42 + 96, f"MOVING {s.get('move_dir') or '--'} AT {s.get('move_mph') or '--'} MPH", 26,
            "bold", anchor="ls")
    tiles = [("MAX WINDS", f"{mph} MPH", f"{kt:.0f} kt", col),
             ("PRESSURE", f"{s.get('pressure') or '--'} MB", f"{(s.get('pressure') or 0) * 0.02953:.2f} inHg" if s.get("pressure") else "", C["rule"]),
             ("LOCATION", f"{abs(s['lat']):.1f}°{'N' if s['lat'] >= 0 else 'S'} {abs(s['lon']):.1f}°{'W' if s['lon'] < 0 else 'E'}",
              "Center position", C["rule"])]
    ca = T.closest_approach(t.get("points") or [], loc["lat"], loc["lon"], _base(t))
    if ca:
        tiles.append(("CLOSEST APPROACH", f"{ca[1]:.0f} MI {ca[2]}", _when(ca[0].astimezone(tz)), BAD if ca[1] < 100 else WARN))
    cols = 2 if cv.tall else len(tiles)
    for (lab, val, sub, c), box in zip(tiles, grid(x, y + bh + 20, w, h - bh - 20, len(tiles), cols, 18)):
        tile(cv, box, lab, val, sub, bar=c, vsize=min(64, box[3] * 0.3, box[2] * 0.16))
    _footer(cv, pkg, t, "National Hurricane Center")
    return cv


# ------------------------------------------------------------------ 02 track & cone
def _ww_code(props):
    v = " ".join(str(x) for x in props.values() if isinstance(x, str)).upper()
    for code in ("SSW", "SSA", "HWR", "HWA", "TWR", "TWA"):
        if code in v:
            return code
    if "HURRICANE WARNING" in v:
        return "HWR"
    if "HURRICANE WATCH" in v:
        return "HWA"
    if "TROPICAL STORM WARNING" in v:
        return "TWR"
    if "TROPICAL STORM WATCH" in v:
        return "TWA"
    return None


def cone_map(t, cfg, pw, ph, box):
    lay, P, _ = base_map(pw, ph, box, cfg)
    d = ImageDraw.Draw(lay, "RGBA")
    ov = Image.new("RGBA", lay.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    _poly(od, P, t.get("cone") or [], fill=(255, 255, 255, 70), outline=(255, 255, 255, 230), width=z(2.5))
    lay.alpha_composite(ov)
    d = ImageDraw.Draw(lay, "RGBA")
    for ln in t.get("ww") or []:
        code = _ww_code(ln["props"])
        if code:
            d.line([P(*c) for c in ln["coords"]], fill=(*WW_COL[code][0], 255), width=z(7), joint="curve")
    past = t.get("past") or []
    if len(past) > 1:
        d.line([P(p["lon"], p["lat"]) for p in past] + [P(t["storm"]["lon"], t["storm"]["lat"])], fill=(200, 210, 230, 200),
               width=z(2.5))
    pts = t.get("points") or []
    if len(pts) > 1:
        d.line([P(p["lon"], p["lat"]) for p in pts], fill=(255, 255, 255, 255), width=z(3))
    tz = _tz(cfg)
    base = _base(t)
    for i, p in enumerate(pts):
        x, y = P(p["lon"], p["lat"])
        c = _col(p.get("wind_kt"))
        r = z(9 if i else 13)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*c, 255), outline=(13, 21, 38, 255), width=z(2))
        cat = T.saffir(p.get("wind_kt"))
        lab = str(cat) if cat else ("S" if (p.get("wind_kt") or 0) >= 34 else "D")
        d.text((x, y), lab, font=font("bold", 12), fill=_ink(c) + (255,), anchor="mm")
        if i:
            d.text((x + z(16), y), _when(pt_time(p, base, tz)), font=font("bold", 14), fill=(255, 255, 255, 255),
                   anchor="lm", stroke_width=z(3), stroke_fill=(13, 21, 38, 255))
    sx, sy = P(t["storm"]["lon"], t["storm"]["lat"])
    _storm_icon(d, sx, sy, z(13), _col(t["storm"].get("wind_kt")))
    _norfolk(d, P, cfg)
    return lay


def g_cone(t, pkg, cfg):
    cv = _canvas(cfg, "FORECAST TRACK & CONE", f"{_storm_title(t)}  ·  NATIONAL HURRICANE CENTER")
    (mx, my, mw, mh), (px, py, pw_, ph_) = _split(cv)
    box = tuple(cfg.get("tropical_track_view") or track_view(t, cfg))
    _frame(cv, cone_map(t, cfg, mw, mh, box), mx, my, mw, mh)
    codes = sorted({_ww_code(l["props"]) for l in t.get("ww") or []} - {None}, key=list(WW_COL).index)
    chips = [(WW_COL[c][0], WW_COL[c][1]) for c in codes] or [((255, 255, 255), "CONE OF UNCERTAINTY")]
    _legend_chips(cv, mx + 16, my + mh - 60, chips, mw - 32)
    tz, base = _tz(cfg), _base(t)
    rows = []
    for p in (t.get("points") or [])[:9]:
        kt = p.get("wind_kt") or 0
        cat = T.saffir(kt)
        rows.append((_when(pt_time(p, base, tz)).title(), f"{round(kt * 1.15078 / 5) * 5:.0f} mph" + (f" · Cat {cat}" if cat else ""),
                     _col(kt)))
    ca = T.closest_approach(t.get("points") or [], cfg["location"]["lat"], cfg["location"]["lon"], base)
    head = ("CLOSEST TO NORFOLK", f"{ca[1]:.0f} MI {ca[2]}" if ca else "--", BAD if ca and ca[1] < 100 else WARN,
            f"Around {_when(ca[0].astimezone(tz)).title()}. The center can be anywhere in the cone; impacts extend well outside it."
            if ca else "")
    _rows_panel(cv, (px, py, pw_, ph_), "FORECAST POSITIONS", rows, head)
    _footer(cv, pkg, t, "National Hurricane Center")
    return cv


# ------------------------------------------------------------------ 03 intensity forecast
def g_intensity(t, pkg, cfg):
    cv = _canvas(cfg, "INTENSITY FORECAST", f"{_storm_title(t)}  ·  MAX SUSTAINED WINDS (MPH)")
    x, y, w, h = area(cv)
    cv.rect(x, y, w, h, C["panel"], r=18)
    tz, base = _tz(cfg), _base(t)
    pts = [p for p in (t.get("past") or [])[-4:] if p.get("wind_kt")] + list(t.get("points") or [])
    if not pts:
        return None
    px0, px1, py0, py1 = x + 110, x + w - 40, y + 50, y + h - 90
    vmax = 160
    bands = [(0, 38, "TD", CAT_COL[0]), (39, 73, "TS", TS_COL), (74, 95, "CAT 1", CAT_COL[1]), (96, 110, "CAT 2", CAT_COL[2]),
             (111, 129, "CAT 3", CAT_COL[3]), (130, 156, "CAT 4", CAT_COL[4]), (157, 160, "CAT 5", CAT_COL[5])]
    Y = lambda v: py1 - v / vmax * (py1 - py0)
    for lo, hi, lab, c in bands:
        cv.rect(px0, Y(hi), px1 - px0, Y(lo) - Y(hi), (*c, 38))
        cv.text(px0 - 14, (Y(lo) + Y(hi)) / 2, lab, 17, "bold", c, anchor="rm")
    times = [p.get("tau") or 0 for p in pts]
    t0, t1 = min(times), max(times) or 1
    X = lambda tau: px0 + (tau - t0) / max(1, (t1 - t0)) * (px1 - px0)
    xy = [(X(p.get("tau") or 0), Y((p.get("wind_kt") or 0) * 1.15078)) for p in pts]
    cv.line(xy, (255, 255, 255, 255), 4)
    for p, (xx, yy) in zip(pts, xy):
        mph = round((p.get("wind_kt") or 0) * 1.15078 / 5) * 5
        c = _col(p.get("wind_kt"))
        cv.d.ellipse([z(xx - 10), z(yy - 10), z(xx + 10), z(yy + 10)], fill=(*c, 255), outline=(13, 21, 38, 255), width=z(2))
        cv.text(xx, yy - 20, f"{mph}", 20, "bold", anchor="ms")
        if (p.get("tau") or 0) >= 0:
            cv.text(xx, py1 + 34, _when(pt_time(p, base, tz)).replace(" ", "\n", 1).split("\n")[0], 17, "bold", C["muted"], anchor="ms")
            cv.text(xx, py1 + 56, _when(pt_time(p, base, tz)).split(" ", 1)[1], 15, "medium", C["muted"], anchor="ms")
    if t0 < 0:
        cv.line([(X(0), py0), (X(0), py1)], (255, 255, 255, 120), 2)
        cv.text(X(0) + 8, py0 + 4, "NOW", 16, "bold", C["muted"], anchor="lt")
    _footer(cv, pkg, t, "National Hurricane Center")
    return cv


# ------------------------------------------------------------------ 04 advisory schedule
def g_advisories(t, pkg, cfg):
    tz = _tz(cfg)
    now = datetime.fromisoformat(pkg["issued"]).astimezone(tz)
    cv = _canvas(cfg, "NEXT NHC ADVISORIES", f"{_storm_title(t)}  ·  ALL TIMES {now.strftime('%Z')}")
    x, y, w, h = area(cv)
    utc = now.astimezone(timezone.utc)
    full = [3, 9, 15, 21]  # full advisories at 03/09/15/21 UTC (11 PM/5 AM/11 AM/5 PM EDT)
    inter = [0, 6, 12, 18]  # intermediate advisories (when watches/warnings are in effect)
    ev = []
    for dh in range(0, 30):
        tt = (utc + timedelta(hours=dh)).replace(minute=0, second=0, microsecond=0)
        if tt <= utc:
            continue
        if tt.hour in full:
            ev.append((tt, "FULL ADVISORY", "New track, cone, intensity forecast and wind probabilities", BAD))
        elif tt.hour in inter and t.get("ww"):
            ev.append((tt, "INTERMEDIATE ADVISORY", "Updated position and intensity (track/cone unchanged)", WARN))
    ev = ev[:6]
    nxt = ev[0][0] if ev else None
    if nxt:
        mins = int((nxt - utc).total_seconds() // 60)
        hero = (x, y, w, 180)
        cv.rect(*hero, C["panel"], r=18)
        cv.text(x + 36, y + 30, "NEXT UPDATE", 22, "bold", C["muted"], anchor="lt")
        cv.text(x + 36, y + 140, nxt.astimezone(tz).strftime("%-I:%M %p %a").upper(), 80, "bold", anchor="ls")
        cv.text(x + w - 36, y + 120, f"IN {mins // 60}H {mins % 60:02d}M", 44, "bold", (250, 205, 90), anchor="rs")
    rows_y = y + 200
    rh = min(110, (y + h - rows_y) / max(1, len(ev)) - 10)
    for i, (tt, lab, sub, col) in enumerate(ev):
        ry = rows_y + i * (rh + 10)
        cv.accent_row(x, ry, w, rh, bar=col)
        cv.text(x + 34, ry + rh / 2, tt.astimezone(tz).strftime("%a %-I:%M %p").upper(), min(30, rh * 0.36), "bold", anchor="lm")
        cv.text(x + w * (0.34 if not cv.tall else 0.42), ry + rh * 0.38, lab, min(22, rh * 0.26), "bold", col, anchor="lm")
        cv.text(x + w * (0.34 if not cv.tall else 0.42), ry + rh * 0.7, sub, min(18, rh * 0.2), "medium", C["muted"], anchor="lm",
                maxw=w * (0.62 if not cv.tall else 0.55))
    _footer(cv, pkg, t, "National Hurricane Center schedule")
    return cv


# ------------------------------------------------------------------ 05 wind chances
def g_wind_chances(t, pkg, cfg):
    probs = t.get("probs") or {}
    if not probs.get(34):
        return None
    cv = _canvas(cfg, "CHANCE OF DAMAGING WINDS", f"{_storm_title(t)}  ·  NEXT 5 DAYS  ·  NHC WIND PROBABILITIES")
    (mx, my, mw, mh), (px, py, pw_, ph_) = _split(cv)
    box = tuple(cfg.get("tropical_local_view") or (-79.5, -73.5, 34.3, 39.3))
    lay, P, _ = base_map(mw, mh, box, cfg)
    ov = Image.new("RGBA", lay.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for b in probs[34]:
        _poly(od, P, b["polys"], fill=(*_pcol(b["pct"]), 170))
    lay.alpha_composite(ov)
    d = ImageDraw.Draw(lay, "RGBA")
    draw_cities(d, P, lay.width, lay.height, cfg, bottom_pad=80)
    _frame(cv, lay, mx, my, mw, mh)
    _legend_chips(cv, mx + 16, my + mh - 60, [(c, f"{p}%") for p, c in PROB_COLS[1:]], mw - 32)
    rows = []
    for name, la, lo in cfg.get("tropical_points") or T.LOCAL_POINTS:
        p34, p50, p64 = (T.prob_at(probs.get(k), lo, la) for k in (34, 50, 64))
        rows.append((name, f"{p34:.0f}% · {p50:.0f}% · {p64:.0f}%", _pcol(p34)))
    loc = cfg["location"]
    p34 = T.prob_at(probs.get(34), loc["lon"], loc["lat"])
    p64 = T.prob_at(probs.get(64), loc["lon"], loc["lat"])
    _rows_panel(cv, (px, py, pw_, ph_), "TROPICAL STORM · 58 MPH · HURRICANE", rows,
                ("NORFOLK  ·  TROPICAL-STORM-FORCE WINDS", f"{p34:.0f}% CHANCE", _pcol(p34),
                 f"Chance of 39+ mph sustained winds in the next 5 days. Hurricane-force (74+ mph): {p64:.0f}%."))
    _footer(cv, pkg, t, "National Hurricane Center wind speed probabilities")
    return cv


# ------------------------------------------------------------------ 06 arrival time
def _arrival_at(lines, lat, lon):
    """Nearest isochrone label to the point (lines are 'arrival time' contours)."""
    best = None
    for ln in lines or []:
        lab = ln["props"].get("arrival_time") or ln["props"].get("name") or ""
        for (x0, y0), (x1, y1) in zip(ln["coords"], ln["coords"][1:]):
            dx, dy = x1 - x0, y1 - y0
            tt = max(0, min(1, ((lon - x0) * dx + (lat - y0) * dy) / (dx * dx + dy * dy + 1e-12)))
            dd = math.hypot(lon - (x0 + tt * dx), lat - (y0 + tt * dy))
            if best is None or dd < best[0]:
                best = (dd, lab)
    return best[1] if best else None


def g_arrival(t, pkg, cfg):
    if not (t.get("likely") or t.get("earliest")):
        return None
    cv = _canvas(cfg, "WHEN WILL THE WINDS ARRIVE?", f"{_storm_title(t)}  ·  TROPICAL-STORM-FORCE WINDS (39+ MPH)")
    (mx, my, mw, mh), (px, py, pw_, ph_) = _split(cv)
    box = tuple(cfg.get("tropical_track_view") or track_view(t, cfg))
    lay = cone_map(t, cfg, mw, mh, box)
    W_, H_, P, _ = _proj(mw, mh, box)
    d = ImageDraw.Draw(lay, "RGBA")
    for key, col in (("earliest", (250, 205, 90)), ("likely", (255, 255, 255))):
        for ln in t.get(key) or []:
            pts = [P(*c) for c in ln["coords"]]
            d.line(pts, fill=(*col, 230), width=z(2.5 if key == "likely" else 1.8), joint="curve")
            lab = (ln["props"].get("arrival_time") or ln["props"].get("name") or "").upper()
            if lab and key == "likely":
                mxp = pts[len(pts) // 2]
                d.text(mxp, lab, font=font("bold", 14), fill=(255, 255, 255, 255), anchor="mm", stroke_width=z(3),
                       stroke_fill=(13, 21, 38, 255))
    _frame(cv, lay, mx, my, mw, mh)
    _legend_chips(cv, mx + 16, my + mh - 60, [((255, 255, 255), "MOST LIKELY"), ((250, 205, 90), "EARLIEST REASONABLE")], mw - 32)
    rows = []
    for name, la, lo in cfg.get("tropical_points") or T.LOCAL_POINTS:
        e, l_ = _arrival_at(t.get("earliest"), la, lo), _arrival_at(t.get("likely"), la, lo)
        rows.append((name, f"{(e or '--')} / {(l_ or '--')}".upper(), WARN))
    loc = cfg["location"]
    e, l_ = _arrival_at(t.get("earliest"), loc["lat"], loc["lon"]), _arrival_at(t.get("likely"), loc["lat"], loc["lon"])
    _rows_panel(cv, (px, py, pw_, ph_), "EARLIEST / MOST LIKELY", rows,
                ("NORFOLK  ·  MOST LIKELY ARRIVAL", (l_ or "--").upper(), WARN,
                 f"Earliest reasonable: {(e or '--')}. Finish preparations before the earliest time."))
    _footer(cv, pkg, t, "National Hurricane Center arrival times")
    return cv


# ------------------------------------------------------------------ 08 wind timeline
def g_wind_timeline(t, pkg, cfg):
    wh = t.get("sample_wind") or pkg.get("wind_hourly") or []
    if not wh:
        return None
    tz = _tz(cfg)
    cv = _canvas(cfg, "WIND TIMELINE", f"NORFOLK  ·  HOURLY WIND & GUSTS  ·  NATIONAL WEATHER SERVICE")
    x, y, w, h = area(cv)
    cv.rect(x, y, w, h, C["panel"], r=18)
    pts = wh[:96]
    px0, px1, py0, py1 = x + 90, x + w - 30, y + 40, y + h - 80
    vmax = max(80, max((p["gust"] or p["wind"] or 0) for p in pts) + 10)
    Y = lambda v: py1 - v / vmax * (py1 - py0)
    for lim, lab, c in ((39, "TROPICAL STORM", TS_COL), (58, "DAMAGING", WARN), (74, "HURRICANE", BAD)):
        if lim < vmax:
            cv.line([(px0, Y(lim)), (px1, Y(lim))], (*c, 200), 2)
            cv.text(px1 - 6, Y(lim) - 6, f"{lab} {lim}", 15, "bold", c, anchor="rs")
    for v in range(0, int(vmax) + 1, 20):
        cv.text(px0 - 12, Y(v), str(v), 17, "bold", C["muted"], anchor="rm")
    bw = (px1 - px0) / len(pts)
    for i, p in enumerate(pts):
        g = p["gust"] or p["wind"] or 0
        ws = p["wind"] or 0
        c = BAD if g >= 74 else WARN if g >= 58 else TS_COL if g >= 39 else (88, 150, 255)
        cv.rect(px0 + i * bw, Y(g), max(1, bw - 1), py1 - Y(g), (*c, 110))
        cv.rect(px0 + i * bw, Y(ws), max(1, bw - 1), py1 - Y(ws), (*c, 255))
    for i, p in enumerate(pts):
        tt = datetime.fromisoformat(p["time"]).astimezone(tz)
        if tt.hour == 0:
            cv.line([(px0 + i * bw, py0), (px0 + i * bw, py1)], (255, 255, 255, 50), 1)
        if tt.hour == 12:
            cv.text(px0 + i * bw, py1 + 34, tt.strftime("%a").upper(), 20, "bold", anchor="ms")
    top = max(pts, key=lambda p: p["gust"] or 0)
    tt = datetime.fromisoformat(top["time"]).astimezone(tz)
    cv.text(px0 + 10, py0 + 6, f"PEAK GUST {top['gust']} MPH  ·  {_when(tt)}", 22, "bold", anchor="lt")
    cv.text(px0 + 10, py1 + 64, "SOLID = SUSTAINED WIND   ·   LIGHT = GUSTS", 15, "bold", C["muted"], anchor="ls")
    _footer(cv, pkg, t, "NWS NDFD")
    return cv


# ------------------------------------------------------------------ 09 storm surge map
def g_surge_map(t, pkg, cfg):
    sg = t.get("surge")
    if not sg:
        return None
    cv = _canvas(cfg, "STORM SURGE FLOODING", f"{_storm_title(t)}  ·  PEAK WATER ABOVE GROUND  ·  NHC")
    (mx, my, mw, mh), (px, py, pw_, ph_) = _split(cv)
    w, s, e, n = sg["box"]
    box = (w, e, s, n)
    lay = draw_map([], mw, mh, cfg, outline=False, view=box, water_alpha=0)
    W_, H_, P, _ = _proj(mw, mh, box)
    x0, y0 = P(w, n)
    x1, y1 = P(e, s)
    im = sg["image"].resize((max(1, int(x1 - x0)), max(1, int(y1 - y0))), Image.NEAREST)
    lay.paste(im, (int(x0), int(y0)), im)
    d = ImageDraw.Draw(lay, "RGBA")
    draw_cities(d, P, lay.width, lay.height, cfg, bottom_pad=80)
    _frame(cv, lay, mx, my, mw, mh)
    _legend_chips(cv, mx + 16, my + mh - 60, [(c, l.replace(" above ground", "").replace("Greater than", ">").upper())
                                              for c, l in sg["legend"]], mw - 32)
    rows = []
    for name, la, lo in cfg.get("tropical_points") or T.LOCAL_POINTS:
        lab = T.surge_at(sg, lo, la)
        c = next((cc for cc, ll in sg["legend"] if ll == lab), None)
        rows.append((name, (lab or "None shown").replace(" above ground", "").replace("Greater than", ">"), c))
    _rows_panel(cv, (px, py, pw_, ph_), "SHORELINE NEAR EACH CITY", rows,
                ("LIFE-THREATENING STORM SURGE", "POSSIBLE", BAD,
                 "Reasonable worst case: water rising this high above normally dry ground. Follow evacuation orders."))
    _footer(cv, pkg, t, "NHC Potential Storm Surge Flooding")
    return cv


# ------------------------------------------------------------------ 10 Sewells Point surge + tide
def g_sewells(t, pkg, cfg):
    sw = t.get("sewells")
    if not sw or not sw.get("forecast"):
        return None
    tz = _tz(cfg)
    cv = _canvas(cfg, "SEWELLS POINT WATER LEVEL", "NWS FORECAST (TIDE + SURGE) vs HISTORIC STORMS  ·  FT MLLW")
    x, y, w, h = area(cv)
    cw = w if cv.tall else w * 0.66
    ch = h * 0.6 if cv.tall else h
    cv.rect(x, y, cw, ch, C["panel"], r=18)
    obs = [(datetime.fromisoformat(a), b) for a, b in sw.get("observed") or []][-48:]
    fc = [(datetime.fromisoformat(a), b) for a, b in sw["forecast"]][:96]
    allp = obs + fc
    hist = sw.get("historic") or []
    vmax = max([b for _, b in allp] + [hh["ft"] for hh in hist[:3]] + [7]) + 0.6
    vmin = min(b for _, b in allp) - 0.5
    px0, px1, py0, py1 = x + 80, x + cw - 30, y + 40, y + ch - 70
    t0, t1 = allp[0][0], allp[-1][0]
    X = lambda tt: px0 + (tt - t0).total_seconds() / max(1, (t1 - t0).total_seconds()) * (px1 - px0)
    Y = lambda v: py1 - (v - vmin) / (vmax - vmin) * (py1 - py0)
    st = sw.get("stages") or {}
    for k, c in (("minor", WARN), ("moderate", BAD), ("major", SEVERE)):
        if st.get(k):
            cv.line([(px0, Y(st[k])), (px1, Y(st[k]))], (*c, 200), 2)
            cv.text(px0 + 6, Y(st[k]) - 6, f"{k.upper()} {st[k]:g}'", 15, "bold", c, anchor="ls")
    for hh in hist[:3]:
        cv.line([(px0, Y(hh["ft"])), (px1, Y(hh["ft"]))], (255, 255, 255, 110), 1)
        cv.text(px1 - 6, Y(hh["ft"]) - 6, f"{hh['name'].upper()} {hh['ft']:.2f}'", 15, "bold", C["muted"], anchor="rs")
    for v in range(math.ceil(vmin), int(vmax) + 1):
        cv.text(px0 - 12, Y(v), f"{v}'", 16, "bold", C["muted"], anchor="rm")
    if len(obs) > 1:
        cv.line([(X(a), Y(b)) for a, b in obs], (255, 255, 255, 255), 4)
    cv.line([(X(a), Y(b)) for a, b in fc], (88, 200, 255, 255), 4)
    pk = max(fc, key=lambda p: p[1])
    cv.d.ellipse([z(X(pk[0]) - 9), z(Y(pk[1]) - 9), z(X(pk[0]) + 9), z(Y(pk[1]) + 9)], fill=(*BAD, 255),
                 outline=(255, 255, 255, 255), width=z(2))
    cv.text(X(pk[0]), Y(pk[1]) - 18, f"PEAK {pk[1]:.1f} FT", 20, "bold", anchor="ms")
    d0 = t0.astimezone(tz).replace(hour=12, minute=0, second=0, microsecond=0)
    while d0 < t1:
        if d0 > t0:
            cv.text(X(d0), py1 + 34, d0.strftime("%a").upper(), 18, "bold", C["muted"], anchor="ms")
        d0 += timedelta(days=1)
    sx, sy, sw_, sh = (x, y + ch + 18, w, h - ch - 18) if cv.tall else (x + cw + 20, y, w - cw - 20, h)
    cat = "MAJOR" if pk[1] >= (st.get("major") or 99) else "MODERATE" if pk[1] >= (st.get("moderate") or 99) else \
        "MINOR" if pk[1] >= (st.get("minor") or 99) else "BELOW FLOOD STAGE"
    rows = [(hh["name"], f"{hh['ft']:.2f} ft", WARN) for hh in hist[:6]]
    rank = 1 + sum(1 for hh in hist if hh["ft"] > pk[1])
    _rows_panel(cv, (sx, sy, sw_, sh), "HIGHEST ON RECORD", rows,
                ("FORECAST PEAK", f"{pk[1]:.1f} FT", BAD if cat in ("MAJOR", "MODERATE") else WARN,
                 f"{cat.title()} flooding {_when(pk[0].astimezone(tz)).title()}. Would rank #{rank} on record."))
    _footer(cv, pkg, t, "NWS NWPS SWPV2")
    return cv


# ------------------------------------------------------------------ 11 tropical watches/warnings
def g_trop_alerts(t, pkg, cfg):
    alerts = [a for a in (pkg.get("alerts") or []) + (t.get("sample_alerts") or []) if a.get("event") in TROP_EVENTS]
    if not alerts:
        return None
    order = {e: i for i, e in enumerate(TROP_EVENTS)}
    alerts = sorted(alerts, key=lambda a: order.get(a["event"], 99))
    cs = alertinfo.counties()
    seen, layers = set(), []
    for a in reversed(alerts):  # draw least severe first
        col = alertinfo.hex_rgb(a.get("color") or "#888888")
        polys = [p for f in a.get("fips") or [] if f in cs for p in cs[f]["polys"]]
        layers.append((col, polys))
    cv = _canvas(cfg, "TROPICAL WATCHES & WARNINGS", f"{_storm_title(t)}  ·  NWS WAKEFIELD")
    (mx, my, mw, mh), (px, py, pw_, ph_) = _split(cv)
    _frame(cv, draw_map(layers, mw, mh, cfg, outline=True), mx, my, mw, mh)
    ev = []
    for a in alerts:
        if a["event"] not in seen:
            seen.add(a["event"])
            ev.append(a)
    _legend_chips(cv, mx + 16, my + mh - 60, [(alertinfo.hex_rgb(a.get("color") or "#888"), a["event"].upper()) for a in ev], mw - 32)
    rows = [(a["event"], (a.get("ends_label") or "").replace("until ", "").upper(), alertinfo.hex_rgb(a.get("color") or "#888"))
            for a in ev]
    home = next((a for a in alerts if a.get("affects_home")), alerts[0])
    _rows_panel(cv, (px, py, pw_, ph_), "IN EFFECT", rows,
                ("NORFOLK", home["event"].upper(), alertinfo.hex_rgb(home.get("color") or "#888"), home.get("headline") or ""))
    _footer(cv, pkg, t, "NWS alerts")
    return cv


# ------------------------------------------------------------------ 16 hurricane statement
def g_hls(t, pkg, cfg):
    h_ = t.get("hls")
    if not h_:
        return None
    cv = _canvas(cfg, "HURRICANE LOCAL STATEMENT", f"NWS WAKEFIELD  ·  {h_.get('issued') or ''}")
    x, y, w, h = area(cv)
    cv.rect(x, y, w, 120 if not cv.tall else 160, (*BAD, 255), r=16)
    cv.paragraph(x + 30, y + 22, h_.get("headline") or _storm_title(t), 28 if not cv.tall else 26, "bold", w - 60, max_lines=3, lh=1.2)
    yy = y + (140 if not cv.tall else 180)
    if h_.get("situation"):
        cv.rect(x, yy, w, 170 if not cv.tall else 260, C["panel"], r=16)
        cv.text(x + 26, yy + 18, "SITUATION", 19, "bold", C["muted"], anchor="lt")
        cv.paragraph(x + 26, yy + 50, h_["situation"], 22, "regular", w - 52, max_lines=4 if not cv.tall else 7, lh=1.25)
        yy += (190 if not cv.tall else 280)
    secs = list((h_.get("sections") or {}).items())
    if secs:
        boxes = grid(x, yy, w, y + h - yy, len(secs), 2 if (cv.tall or len(secs) > 2) else len(secs), 16)
        icons = {"WIND": WARN, "SURGE": SEVERE, "FLOODING RAIN": (88, 170, 255), "TORNADOES": BAD}
        for (k, txt), (bx, by, bw, bh) in zip(secs, boxes):
            cv.accent_row(bx, by, bw, bh, bar=icons.get(k, C["rule"]))
            cv.text(bx + 30, by + 18, k, 20, "bold", icons.get(k, C["muted"]), anchor="lt")
            cv.paragraph(bx + 30, by + 50, txt, 20, "regular", bw - 50, max_lines=int((bh - 60) // 25), lh=1.22)
    _footer(cv, pkg, t, "NWS Wakefield Hurricane Local Statement")
    return cv


# ------------------------------------------------------------------ 17 threat matrix
def _level(threat_text, impacts):
    s = (threat_text or "").lower()
    if impacts:
        return impacts.title()
    for word, lvl in (("extreme", "Extreme"), ("major", "High"), ("life-threatening", "High"), ("moderate", "Moderate"),
                      ("few", "Elevated"), ("minor", "Elevated"), ("isolated", "Low")):
        if word in s:
            return lvl
    return "None"


def g_threats(t, pkg, cfg):
    tc = t.get("tcv")
    if not tc or not tc.get("threats"):
        return None
    cv = _canvas(cfg, "HURRICANE THREATS", f"{(tc.get('name') or 'NORFOLK').upper()}  ·  NWS WAKEFIELD THREAT ASSESSMENT")
    x, y, w, h = area(cv)
    names = {"WIND": "WIND", "SURGE": "STORM SURGE", "FLOODING RAIN": "FLOODING RAIN", "TORNADO": "TORNADOES"}
    items = [(names[k], v) for k, v in tc["threats"].items() if k in names]
    boxes = grid(x, y, w, h, len(items), 2 if (len(items) > 2 or cv.tall) else len(items), 18)
    if cv.tall and cv.fmt == "vertical":
        boxes = grid(x, y, w, h, len(items), 1, 14)
    for (lab, v), (bx, by, bw, bh) in zip(items, boxes):
        lvl = _level(v.get("threat"), v.get("impacts"))
        col = LEVEL_COL.get(lvl, NEUTRAL)
        cv.rect(bx, by, bw, bh, C["panel"], r=16)
        cv.rect(bx, by, bw, 12, (*col, 255), r=6)
        cv.text(bx + 26, by + 34, lab, 26, "bold", anchor="lt")
        pill(cv, bx + bw - 26, by + 28, f"{lvl.upper()} IMPACTS" if v.get("impacts") else lvl.upper(), col, 18, anchor="r")
        yy = by + 80
        for k_, txt in (("FORECAST", v.get("peak") or v.get("latest")), ("THREAT", v.get("threat")), ("ACT", v.get("act"))):
            if not txt or yy > by + bh - 50:
                continue
            cv.text(bx + 26, yy, k_, 16, "bold", C["muted"], anchor="lt")
            used = cv.paragraph(bx + 26, yy + 22, txt, 20, "regular", bw - 52, max_lines=2 if bh < 380 else 3, lh=1.22)
            yy += used + 34
    _footer(cv, pkg, t, "NWS Wakefield Tropical Cyclone Watch/Warning (TCV)")
    return cv


# ------------------------------------------------------------------ 18 evacuations (manual)
def g_evac(t, pkg, cfg):
    ev = (pkg.get("tropical_manual") or {}).get("evacuations") or cfg.get("tropical_evacuations") or []
    cv = _canvas(cfg, "EVACUATIONS", "KNOW YOUR ZONE  ·  KNOWYOURZONE.VIRGINIA.GOV")
    x, y, w, h = area(cv)
    if not ev:
        cv.rect(x, y, w, h, C["panel"], r=18)
        cv.text(x + w / 2, y + h * 0.36, "NO EVACUATION ORDERS", 56, "bold", anchor="mm")
        cv.paragraph(x + 80, y + h * 0.46, "None entered yet. Look up your evacuation zone at KnowYourZone.Virginia.gov and "
                                           "follow your city or county's official orders.", 28, "regular", w - 160, max_lines=3,
                     anchor="la")
    else:
        rh = min(130, (h - 14 * (len(ev) - 1)) / len(ev))
        for i, e_ in enumerate(ev):
            ry = y + i * (rh + 14)
            col = BAD if "mandatory" in (e_.get("type") or "").lower() else WARN
            cv.accent_row(x, ry, w, rh, bar=col)
            cv.text(x + 34, ry + rh * 0.38, (e_.get("locality") or "").upper(), min(34, rh * 0.3), "bold", anchor="lm", maxw=w * 0.45)
            cv.text(x + 34, ry + rh * 0.72, f"ZONES {e_.get('zones') or '--'}", min(22, rh * 0.2), "bold", C["muted"], anchor="lm")
            pill(cv, x + w - 30, ry + rh / 2 - 18, ((e_.get("type") or "Voluntary") + " evacuation").upper(), col, 20, anchor="r")
            if e_.get("when"):
                cv.text(x + w * 0.5, ry + rh / 2, e_["when"], min(22, rh * 0.2), "medium", anchor="lm", maxw=w * 0.25)
    _footer(cv, pkg, t, "Local emergency management")
    return cv


# ------------------------------------------------------------------ 19 preparedness
PHASES = [
    ("48+ HOURS OUT", ["Know your evacuation zone and route", "Refill prescriptions; get cash", "Fuel vehicles and generators",
                       "Water: 1 gallon / person / day for 3+ days", "Batteries, flashlights, radio, chargers"]),
    ("24-36 HOURS OUT", ["Bring in or tie down outdoor items", "Move vehicles to higher ground", "Check on neighbors",
                         "Charge phones; set alerts on", "Leave now if you're in an evacuation zone"]),
    ("DURING THE STORM", ["Stay inside, away from windows", "Never drive through flooded roads", "Generators outside only",
                          "Interior room on lowest floor for tornado warnings", "Keep your radio / phone alerts on"]),
    ("AFTER THE STORM", ["Stay out of floodwater", "Avoid downed power lines", "Photograph damage for insurance",
                         "Check on neighbors", "Wait for the all-clear before returning"]),
]


def g_prepare(t, pkg, cfg):
    tz = _tz(cfg)
    now = datetime.fromisoformat(pkg["issued"]).astimezone(tz)
    lines = (pkg.get("tropical_manual") or {}).get("prepare") or cfg.get("tropical_prepare") or PHASES
    arr = _arrival_at(t.get("earliest"), cfg["location"]["lat"], cfg["location"]["lon"])
    ca = T.closest_approach(t.get("points") or [], cfg["location"]["lat"], cfg["location"]["lon"], _base(t))
    hrs = (ca[0] - now.astimezone(timezone.utc)).total_seconds() / 3600 if ca else 99
    now_i = 0 if hrs > 48 else 1 if hrs > 12 else 2 if hrs > -12 else 3
    cv = _canvas(cfg, "HURRICANE PREPAREDNESS", f"{_storm_title(t)}  ·  WHAT TO DO NOW")
    x, y, w, h = area(cv)
    boxes = grid(x, y, w, h, len(lines), 1 if cv.tall and cv.fmt == "vertical" else 2, 16)
    for i, ((title, items), (bx, by, bw, bh)) in enumerate(zip(lines, boxes)):
        on = i == now_i
        col = BAD if on else C["rule"]
        cv.rect(bx, by, bw, bh, C["panel"] if not on else (40, 58, 92), r=16)
        cv.rect(bx, by, 10, bh, (*col, 255), r=5)
        cv.text(bx + 30, by + 20, title, 24, "bold", col if on else C["text"], anchor="lt")
        if on:
            pill(cv, bx + bw - 22, by + 16, "NOW", BAD, 16, anchor="r")
        rh = min(42, (bh - 70) / max(1, len(items)))
        for k, it in enumerate(items):
            yy = by + 64 + k * rh
            cv.rect(bx + 30, yy + rh * 0.25, rh * 0.45, rh * 0.45, (255, 255, 255, 40), r=4)
            cv.text(bx + 30 + rh * 0.7, yy + rh / 2, it, min(21, rh * 0.52), "medium", anchor="lm", maxw=bw - 80)
    _footer(cv, pkg, t, "NWS / Ready.gov")
    return cv


# ------------------------------------------------------------------ 21 storm timeline
def g_timeline(t, pkg, cfg):
    tz = _tz(cfg)
    now = datetime.fromisoformat(pkg["issued"]).astimezone(tz)
    loc = cfg["location"]
    days = [now.date() + timedelta(days=i) for i in range(5)]
    lanes = []
    e = _arrival_at(t.get("earliest"), loc["lat"], loc["lon"])
    l_ = _arrival_at(t.get("likely"), loc["lat"], loc["lon"])
    ca = T.closest_approach(t.get("points") or [], loc["lat"], loc["lon"], _base(t))
    wh = t.get("sample_wind") or pkg.get("wind_hourly") or []
    windy = [datetime.fromisoformat(p["time"]).astimezone(tz) for p in wh if (p.get("gust") or 0) >= 39]
    if windy:
        lanes.append(("TROPICAL STORM WINDS", windy[0], windy[-1], TS_COL, f"from {e or _when(windy[0])}"))
    hur = [datetime.fromisoformat(p["time"]).astimezone(tz) for p in wh if (p.get("gust") or 0) >= 74]
    if hur:
        lanes.append(("HURRICANE-FORCE GUSTS", hur[0], hur[-1], BAD, ""))
    sw = t.get("sewells") or {}
    st = (sw.get("stages") or {}).get("minor") or 4.5
    hi = [(datetime.fromisoformat(a).astimezone(tz), b) for a, b in sw.get("forecast") or [] if b >= st]
    if hi:
        pk = max(hi, key=lambda p: p[1])
        lanes.append(("TIDAL FLOODING (SEWELLS PT)", hi[0][0], hi[-1][0], SEVERE, f"peak {pk[1]:.1f} ft {_when(pk[0])}"))
    wet = [d for d in pkg.get("days") or [] if (d.get("qpf") or 0) >= 0.5]
    if wet:
        d0 = datetime.fromisoformat(wet[0]["date"]).replace(tzinfo=tz)
        d1 = datetime.fromisoformat(wet[-1]["date"]).replace(tzinfo=tz) + timedelta(hours=23)
        lanes.append(("HEAVY RAIN", d0, d1, (88, 170, 255), f"{sum(d.get('qpf') or 0 for d in wet):.1f}\" forecast"))
    spc = pkg.get("spc_outlook") or {}
    trn = [int(k) for k, v in spc.items() if v.get("category") and v.get("category") != "TSTM"]
    if trn:
        d0 = datetime.combine(now.date() + timedelta(days=min(trn) - 1), datetime.min.time(), tz)
        lanes.append(("TORNADO RISK", d0, d0 + timedelta(days=max(trn) - min(trn) + 1), WARN, ""))
    if not lanes and not ca:
        return None
    cv = _canvas(cfg, "STORM TIMELINE", f"{_storm_title(t)}  ·  WHAT TO EXPECT AND WHEN  ·  NORFOLK")
    x, y, w, h = area(cv)
    cv.rect(x, y, w, h, C["panel"], r=18)
    lx = x + (330 if not cv.tall else 30)
    t0 = datetime.combine(days[0], datetime.min.time(), tz)
    t1 = t0 + timedelta(days=5)
    gx0, gx1 = lx, x + w - 30
    X = lambda tt: gx0 + max(0, min(1, (tt - t0).total_seconds() / (t1 - t0).total_seconds())) * (gx1 - gx0)
    top = y + 70
    for i, d in enumerate(days):
        xx = X(datetime.combine(d, datetime.min.time(), tz))
        cv.line([(xx, top - 10), (xx, y + h - 20)], (255, 255, 255, 40), 1)
        cv.text(xx + (gx1 - gx0) / 10, y + 40, d.strftime("%a %-d").upper(), 22, "bold", anchor="ms")
    nx = X(now)
    cv.line([(nx, top - 10), (nx, y + h - 20)], (255, 255, 255, 160), 2)
    n = len(lanes) + (1 if ca else 0)
    rh = min(110, (y + h - 30 - top) / max(1, n))
    for i, (lab, a, b, col, note) in enumerate(lanes):
        ry = top + i * rh
        if cv.tall:
            cv.text(x + 30, ry + 14, lab, 18, "bold", col, anchor="lt")
            by_ = ry + 40
        else:
            cv.text(x + 30, ry + rh / 2, lab, 20, "bold", col, anchor="lm", maxw=290)
            by_ = ry + rh * 0.25
        bh = rh * (0.4 if cv.tall else 0.5)
        cv.rect(X(a), by_, max(10, X(b) - X(a)), bh, (*col, 235), r=bh / 2)
        if note:
            cv.text(min(X(b) + 10, gx1 - 180), by_ + bh / 2, note, 17, "bold", anchor="lm", maxw=200)
    if ca:
        ry = top + len(lanes) * rh
        when = ca[0].astimezone(tz)
        cv.text(x + 30, ry + (14 if cv.tall else rh / 2), "CLOSEST APPROACH", 20 if not cv.tall else 18, "bold", C["text"],
                anchor="lt" if cv.tall else "lm")
        cy = ry + (52 if cv.tall else rh / 2)
        _storm_icon(cv.d, z(X(when)), z(cy), z(14), _col(ca[3]))
        cv.text(X(when) + 34, cy, f"{ca[1]:.0f} MI {ca[2]}  ·  {_when(when)}", 18, "bold", anchor="lm")
    _footer(cv, pkg, t, "NHC / NWS")
    return cv


# ------------------------------------------------------------------ 22 history
def g_history(t, pkg, cfg):
    sw = t.get("sewells") or {}
    hist = sw.get("historic") or []
    if not hist or not sw.get("forecast"):
        return None
    pk = max(b for _, b in sw["forecast"])
    items = sorted(hist[:7] + [{"name": f"{(t.get('storm') or {}).get('name') or 'THIS STORM'} (forecast)", "ft": pk, "date": "",
                                "now": True}], key=lambda r: -r["ft"])
    cv = _canvas(cfg, "HOW DOES IT COMPARE?", "SEWELLS POINT PEAK WATER LEVEL  ·  FT MLLW")
    x, y, w, h = area(cv)
    cv.rect(x, y, w, h, C["panel"], r=18)
    vmax = max(r["ft"] for r in items) + 0.5
    rh = (h - 60) / len(items)
    for i, r in enumerate(items):
        ry = y + 30 + i * rh
        col = BAD if r.get("now") else (88, 150, 255)
        lab = r["name"].upper() + (f"  ({r['date'][:4]})" if r.get("date") and r["date"][:4] not in r["name"] else "")
        cv.text(x + 30, ry + rh / 2, lab, min(22, rh * 0.32), "bold", col if r.get("now") else C["text"], anchor="lm",
                maxw=w * 0.38 if not cv.tall else w * 0.5)
        bx0 = x + (w * 0.42 if not cv.tall else w * 0.52)
        bw = (x + w - 140 - bx0) * r["ft"] / vmax
        cv.rect(bx0, ry + rh * 0.2, bw, rh * 0.6, (*col, 255), r=8)
        cv.text(bx0 + bw + 14, ry + rh / 2, f"{r['ft']:.2f}'", min(26, rh * 0.38), "bold", anchor="lm")
    _footer(cv, pkg, t, "NWS NWPS historic crests")
    return cv


# ------------------------------------------------------------------ 23 closest approach
def g_closest(t, pkg, cfg):
    loc, tz = cfg["location"], _tz(cfg)
    ca = T.closest_approach(t.get("points") or [], loc["lat"], loc["lon"], _base(t))
    if not ca:
        return None
    cv = _canvas(cfg, "CLOSEST APPROACH", f"{_storm_title(t)}  ·  NHC FORECAST TRACK")
    (mx, my, mw, mh), (px, py, pw_, ph_) = _split(cv)
    box = tuple(cfg.get("tropical_track_view") or track_view(t, cfg))
    lay = cone_map(t, cfg, mw, mh, box)
    W_, H_, P, _ = _proj(mw, mh, box)
    d = ImageDraw.Draw(lay, "RGBA")
    pts = t.get("points") or []
    best = None
    for a, b in zip(pts, pts[1:]):
        for i in range(21):
            f = i / 20
            la, lo = a["lat"] + (b["lat"] - a["lat"]) * f, a["lon"] + (b["lon"] - a["lon"]) * f
            dd = T.miles(loc["lat"], loc["lon"], la, lo)
            if best is None or dd < best[0]:
                best = (dd, la, lo)
    if best:
        d.line([P(loc["lon"], loc["lat"]), P(best[2], best[1])], fill=(*BAD, 255), width=z(3))
    _frame(cv, lay, mx, my, mw, mh)
    kt = ca[3]
    rows = [("Distance", f"{ca[1]:.0f} miles", BAD if ca[1] < 100 else WARN), ("Direction from Norfolk", ca[2], C["rule"]),
            ("Time", _when(ca[0].astimezone(tz)).title(), C["rule"]),
            ("Forecast strength", f"{round(kt * 1.15078 / 5) * 5:.0f} mph" + (f" (Cat {T.saffir(kt)})" if T.saffir(kt) else ""), _col(kt))]
    _rows_panel(cv, (px, py, pw_, ph_), "DETAILS", rows,
                ("CLOSEST PASS", f"{ca[1]:.0f} MI {ca[2]}", BAD if ca[1] < 100 else WARN,
                 "Based on the center line of the NHC forecast; the center could pass anywhere within the cone."))
    _footer(cv, pkg, t, "National Hurricane Center")
    return cv


# ------------------------------------------------------------------ 25 power outages (manual)
def g_outages(t, pkg, cfg):
    po = (pkg.get("tropical_manual") or {}).get("outages") or cfg.get("tropical_outages") or t.get("sample_outages") or {}
    if not po:
        return None
    cv = _canvas(cfg, "POWER OUTAGES", "CUSTOMERS WITHOUT POWER")
    x, y, w, h = area(cv)
    items = sorted(po.items(), key=lambda kv: -float(kv[1]))
    total = sum(float(v) for _, v in items)
    rows = [(k, f"{int(float(v)):,}", BAD if float(v) > 10000 else WARN if float(v) > 1000 else OK_) for k, v in items]
    _rows_panel(cv, (x, y, w, h), "BY LOCALITY", rows, ("TOTAL", f"{int(total):,}", BAD, "Entered from utility outage maps."))
    _footer(cv, pkg, t, "Utility outage maps (entered manually)")
    return cv


# ------------------------------------------------------------------ storm-mode copies
COPIES = [  # (output name, graphic key, sub-graphic name or None)
    ("07_peak_gusts", "ndfd_maps", "gust_map"), ("12_high_tides", "high_tides", None),
    ("12_high_tides_2", "high_tides_2", None), ("13_storm_rainfall", "outlooks", "wpc_qpf_3day"),
    ("14_excessive_rainfall", "outlooks", "ero_day1"), ("15_river_flooding", "river_flooding", "river_flooding"),
    ("20_tornado_risk", "outlooks", "spc_day1"), ("24_after_rain_reports", "reports", "rain_reports"),
    ("24_after_wind_reports", "reports", "storm_wind_reports"), ("24_after_storm_rain", "reports", "storm_rain_reports"),
]
NEW = [("01_storm_snapshot", g_snapshot), ("02_track_cone", g_cone), ("03_intensity_forecast", g_intensity),
       ("04_advisory_schedule", g_advisories), ("05_wind_chances", g_wind_chances), ("06_wind_arrival", g_arrival),
       ("08_wind_timeline", g_wind_timeline), ("09_storm_surge_map", g_surge_map), ("10_sewells_point_surge", g_sewells),
       ("11_tropical_alerts", g_trop_alerts), ("16_hurricane_statement", g_hls), ("17_threat_matrix", g_threats),
       ("18_evacuations", g_evac), ("19_prepare", g_prepare), ("21_storm_timeline", g_timeline),
       ("22_history_compare", g_history), ("23_closest_approach", g_closest), ("25_power_outages", g_outages)]


def tropical_graphics(pkg, cfg):
    t = pkg.get("_tropical")
    if not t or not t.get("active") or not t.get("storm"):
        print("  - tropical: no storm threatening the area, Tropical folder not made")
        return None
    out = []
    for name, fn in NEW:
        try:
            cv = fn(t, pkg, cfg)
        except Exception as e:
            print(f"  ! Tropical/{name}: {e!r}")
            continue
        if cv is not None:
            out.append((f"Tropical/{name}", cv))
    from . import graphics as G
    cache = {}
    for name, key, sub in COPIES:
        fn = G.GRAPHICS.get(key)
        if not fn:
            continue
        try:
            if key not in cache:
                cache[key] = fn(pkg, cfg)
            res = cache[key]
        except Exception as e:
            print(f"  ! Tropical/{name}: {e!r}")
            continue
        if res is None:
            continue
        items = res if isinstance(res, list) else [(key, res)]
        cv = next((c for n, c in items if n == (sub or key)), None)
        if cv is None:
            continue
        ribbon(cv, t)
        cv.full_spec = None
        out.append((f"Tropical/{name}", cv))
    return out or None
