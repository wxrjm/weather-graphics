"""Tidal flooding forecast map: the bay, rivers and coastline shaded by the forecast flood category
for the next high tide(s), built from the NWS tide gauge forecasts.

How the shading is made (extrapolated between gauges):
  1. Each gauge's forecast high tide is turned into a flood index on its OWN flood stages:
     action = 1, minor = 2, moderate = 3, major = 4 (linear in between), so gauges with different
     datums/stages can be blended fairly.
  2. Every water point within `tidal_radius_km` of a gauge gets an inverse-distance-weighted blend
     of the nearby gauges' index (beyond the last gauge the nearest value is carried out = extrapolation).
  3. A thin strip of shoreline is shaded too, to show low-lying waterfront flooding.
One map per high tide cycle that reaches `tidal_map_min_category` (minor by default) somewhere.
"""
import math
from datetime import timedelta

from PIL import ImageChops, Image, ImageDraw, ImageFilter

from . import alertinfo
from .alertmap import STENCIL, STENCIL_EDGE, _paste_rounded, draw_cities
from .outlookmap import _legend_chips, _side, _view
from .theme import Canvas, C, font, z

TIDAL_VIEW = (-77.45, -75.35, 36.55, 38.05)  # w, e, s, n: James/York/Rappahannock mouths to the Eastern Shore
BAY_VIEW = (-77.25, -75.55, 36.7, 38.0)  # lower Bay: just north of Tangier Island down to Cape Henry / Hampton Roads (tidal_bay_view overrides)
CATS = [  # index threshold, key, label, color
    (1.0, "action", "NEAR FLOOD STAGE", (255, 220, 0)),
    (2.0, "minor", "MINOR", (255, 140, 0)),
    (3.0, "moderate", "MODERATE", (235, 45, 30)),
    (4.0, "major", "MAJOR", (150, 50, 200)),
]
ORDER = [None, "action", "minor", "moderate", "major"]


def _stages(st):
    st = dict(st or {})
    if st.get("minor") is None:
        return None
    st.setdefault("action", st["minor"] - 0.5)
    st.setdefault("moderate", st["minor"] + 1.0)
    st.setdefault("major", st["moderate"] + 1.0)
    return st


def flood_index(v, st):
    """action=1, minor=2, moderate=3, major=4; linear between, below action goes under 1."""
    a, mi, mo, ma = st["action"], st["minor"], st["moderate"], st["major"]
    if v < a:
        return 1 - (a - v) / max(0.1, mi - a)
    for lo, hi, base in ((a, mi, 1), (mi, mo, 2), (mo, ma, 3)):
        if v < hi:
            return base + (v - lo) / max(0.1, hi - lo)
    return 4 + (v - ma) / max(0.1, ma - mo)


def _cat_of(idx):
    hit = None
    for t, key, lab, col in CATS:
        if idx >= t - 1e-6:
            hit = (t, key, lab, col)
    return hit


def events(sites, cfg, max_lag_h=5):
    """Group each gauge's high tides into tide cycles keyed on the reference gauge's highs."""
    usable = [s for s in sites if s.get("highs") and _stages(s.get("stages")) and s.get("lat") is not None]
    if not usable:
        return []
    ref = next((s for s in usable if s.get("lid") == cfg.get("tidal_ref_gauge", "SWPV2")), usable[0])
    out = []
    for h in ref["highs"]:
        t0 = h["time"]
        pts = []
        for s in usable:
            near = min(s["highs"], key=lambda x: abs((x["time"] - t0).total_seconds()))
            if abs((near["time"] - t0).total_seconds()) > max_lag_h * 3600:
                continue
            st = _stages(s["stages"])
            pts.append({"name": s["name"], "lat": s["lat"], "lon": s["lon"], "ft": near["ft"], "time": near["time"],
                        "idx": flood_index(near["ft"], st), "stages": st})
        if pts:
            out.append({"time": t0, "points": pts, "max_idx": max(p["idx"] for p in pts)})
    return out


def _km(lat1, lon1, lat2, lon2):
    k = math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot((lon1 - lon2) * 111.32 * k, (lat1 - lat2) * 110.57)


def draw_tidal_map(ev, pw, ph, cfg, view=None, radius=None, mark="ref"):
    W_, H_ = z(pw), z(ph)
    w, e, s, n = _view(pw, ph, tuple(view or cfg.get("tidal_view") or TIDAL_VIEW))
    proj = lambda x, y: ((x - w) / (e - w) * W_, (n - y) / (n - s) * H_)
    unproj = lambda px, py: (w + px / W_ * (e - w), n - py / H_ * (n - s))
    lay = Image.new("RGBA", (W_, H_), (17, 27, 47, 255))
    d = ImageDraw.Draw(lay, "RGBA")
    land = Image.new("L", (W_, H_), 0)
    ld = ImageDraw.Draw(land)
    cs = [c for c in alertinfo.counties().values() if alertinfo.in_view(c, w, e, s, n)]
    for c in cs:
        for p in c["polys"]:
            pts = [proj(x, y) for x, y in p[0]]
            d.polygon(pts, fill=STENCIL)
            ld.polygon(pts, fill=255)
    # ---- flood index field on a coarse grid, then smoothed up to full size
    radius = radius or cfg.get("tidal_radius_km", 22)
    step = max(6, W_ // 360)  # coarse grid, smoothed later (keeps full-screen sizes fast)
    gw, gh = W_ // step + 1, H_ // step + 1
    idx_img = Image.new("L", (gw, gh), 0)
    msk_img = Image.new("L", (gw, gh), 0)
    ip, mp = idx_img.load(), msk_img.load()
    pts = ev["points"]
    for gy in range(gh):
        for gx in range(gw):
            lon, lat = unproj(gx * step, gy * step)
            num = den = 0.0
            dmin = 1e9
            for p in pts:
                dk = _km(lat, lon, p["lat"], p["lon"])
                dmin = min(dmin, dk)
                wgt = 1.0 / max(0.5, dk) ** 2.5
                num += wgt * p["idx"]
                den += wgt
            if den and dmin <= radius:
                ip[gx, gy] = max(0, min(255, int(round(num / den * 50))))  # idx 0..5 -> 0..250
                mp[gx, gy] = 255
    idx_full = idx_img.resize((W_, H_), Image.BICUBIC).filter(ImageFilter.GaussianBlur(z(7)))
    msk_full = msk_img.resize((W_, H_), Image.BILINEAR).filter(ImageFilter.GaussianBlur(z(6))).point(
        lambda v: max(0, min(255, (v - 96) * 4)))  # soft edge instead of a hard cut
    water = land.point(lambda v: 255 - v)
    shore = water.filter(ImageFilter.MaxFilter(max(3, (z(cfg.get("tidal_shore_px", 7)) // 2) * 2 + 1)))  # water grown a few px onto land
    area = Image.composite(shore, Image.new("L", (W_, H_), 0), msk_full)
    lut = []
    for v in range(256):
        c = _cat_of(v / 50.0)
        lut.append(c)
    min_t = next(t for t, k, *_ in CATS if k == cfg.get("tidal_map_shade_from", "action"))
    ov = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    for t, key, lab, col in CATS:
        if t < min_t:
            continue
        band = idx_full.point(lambda v, t=t: max(0, min(255, int((v - (t * 50 - 4)) * 32))))  # ~8-level ramp
        band = ImageChops.multiply(band, area.filter(ImageFilter.GaussianBlur(z(1.2))))
        layer = Image.new("RGBA", (W_, H_), (*col, 0))
        layer.putalpha(band.point(lambda v: int(v * 0.86)))
        ov.alpha_composite(layer)
    lay.alpha_composite(ov)
    d = ImageDraw.Draw(lay, "RGBA")
    lw = max(1, z(1))
    for c in cs:
        for p in c["polys"]:
            pts_ = [proj(x, y) for x, y in p[0]]
            d.line(pts_ + [pts_[0]], fill=(*STENCIL_EDGE[:3], 150), width=lw)
    for ln in alertinfo.state_lines():
        d.line([proj(x, y) for x, y in ln], fill=(214, 226, 244, 230), width=max(3, z(1.8 * cfg.get("state_line_scale", 2.2))), joint="curve")
    plan = _gauge_plan(d, proj, W_, H_, ev["points"], all_=(mark == "all")) if mark else []
    from . import alertmap
    alertmap.KEEP_OUT[:] = [tuple(v / z(1) for v in b) for _, b, _ in plan]  # city names stay clear of the plotted levels
    try:
        draw_cities(d, proj, W_, H_, cfg, bottom_pad=80)
    finally:
        alertmap.KEEP_OUT[:] = []
    _draw_gauges(d, plan)
    return lay


def _is_sewells(p):
    return "sewells" in p["name"].lower()


def _short(n):
    return "SEWELLS POINT" if "sewells" in n.lower() else n.split(",")[0].strip().upper()[:16]


def _gauge_plan(d, proj, W_, H_, pts, all_=False):
    """Choose which gauges get a label (Sewells Point first, then worst-flooding first; overlapping labels are skipped)."""
    ordered = sorted(pts, key=lambda p: (not _is_sewells(p), -p["idx"]))
    if not all_:
        ordered = [p for p in ordered if _is_sewells(p)][:1]
    placed, plan = [], []
    for p in ordered:
        big = _is_sewells(p)
        x, y = proj(p["lon"], p["lat"])
        if not (z(20) < x < W_ - z(20) and z(20) < y < H_ - z(90)):
            continue
        fn, fv = (font("bold", 20), font("bold", 38)) if big else (font("bold", 17), font("bold", 30))
        nm, val = _short(p["name"]), f"{p['ft']:.1f}'"
        tw = max(d.textlength(nm, font=fn), d.textlength(val, font=fv))
        th = z(30 if big else 26) + z(40 if big else 32)
        box = (x - tw / 2 - z(6), y - th - z(18), x + tw / 2 + z(6), y + z(12))
        if box[1] < z(8) or box[0] < z(8) or box[2] > W_ - z(8) or any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1] for b in placed):
            continue
        placed.append(box)
        plan.append((p, box, (x, y, big, nm, val, fn, fv)))
    return plan


def _draw_gauges(d, plan):
    for p, box, (x, y, big, nm, val, fn, fv) in plan:
        c = _cat_of(p["idx"])
        col = c[3] if c else (70, 180, 100)
        r = z(11 if big else 8)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*col, 255), outline=(255, 255, 255, 255), width=z(3 if big else 2.4))
        vy = y - r - z(8) - fv.size * 0.5
        d.text((x, vy), val, font=fv, fill=(255, 255, 255, 255), anchor="mm", stroke_width=z(3), stroke_fill=(13, 21, 38, 255))
        d.text((x, vy - fv.size * 0.5 - fn.size * 0.75), nm, font=fn, fill=(255, 255, 255, 245), anchor="mm",
               stroke_width=z(2.4), stroke_fill=(13, 21, 38, 255))


def _window(ev, tz):
    ts = sorted(p["time"] for p in ev["points"] if p["idx"] >= 2) or sorted(p["time"] for p in ev["points"])
    a, b = ts[0].astimezone(tz), ts[-1].astimezone(tz)
    a = a.replace(minute=0)
    b = (b + timedelta(minutes=59)).replace(minute=0)
    part = lambda t: "MORNING" if 5 <= t.hour < 12 else "AFTERNOON" if 12 <= t.hour < 17 else "EVENING" if 17 <= t.hour < 21 else "NIGHT"
    hr = lambda t: t.strftime("%I %p").lstrip("0")
    day = a.strftime("%A").upper()
    if b - a < timedelta(minutes=61):
        b = a + timedelta(hours=2)
    return f"{day} {part(a)}  ·  {hr(a)} – {hr(b)}"


def tidal_graphic(ev, pkg, cfg, tz, bay=False, peak=False):
    view = tuple((cfg.get("tidal_bay_view") if bay else cfg.get("tidal_view")) or (BAY_VIEW if bay else TIDAL_VIEW))
    radius = cfg.get("tidal_bay_radius_km", 48) if bay else None  # bigger reach: fills the open middle of the Bay
    title = "CHESAPEAKE BAY TIDAL FLOODING" if bay else "TIDAL FLOODING FORECAST"
    sub = _window(ev, tz)
    if peak:  # the single highest tide in the 72-hour cycle, with its day and time
        pr = next((p for p in sorted(ev["points"], key=lambda p: -p["idx"]) if "sewells" in p["name"].lower()),
                  sorted(ev["points"], key=lambda p: -p["idx"])[0])
        pt = pr["time"].astimezone(tz)
        title = "BAY HIGHEST TIDE · NEXT 72 HRS" if bay else "HIGHEST TIDE · NEXT 72 HOURS"
        sub = f"{pt.strftime('%A').upper()} {pt.strftime('%I:%M %p').lstrip('0')}  ·  {pr['name'].upper()} {pr['ft']:.1f} FT MLLW"
    cv = Canvas(cfg)
    cv.header(title, sub)
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    _paste_rounded(cv, draw_tidal_map(ev, mw, mh, cfg, view=view, radius=radius), mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    shade_from = cfg.get("tidal_map_shade_from", "action")
    chips = [(c[3], c[2]) for c in reversed(CATS) if ORDER.index(c[1]) >= ORDER.index(shade_from)]
    _legend_chips(cv, mx + 16, my + mh - 60, chips, mw - 32)
    pts = sorted(ev["points"], key=lambda p: -p["idx"])
    ref = next((p for p in pts if "sewells" in p["name"].lower()), pts[0])
    c = _cat_of(ref["idx"])
    head = f"{c[2]} FLOODING" if c and c[1] != "action" else ("NEAR FLOOD STAGE" if c else "NO FLOODING")
    head_col = c[3] if c else (70, 180, 100)
    worst = _cat_of(pts[0]["idx"])
    meaning = (f"Sewells Point forecast {ref['ft']:.1f} ft MLLW at {ref['time'].astimezone(tz).strftime('%I:%M %p').lstrip('0')}. "
               + (f"Worst: {worst[2].title()} at {pts[0]['name']}." if worst and pts[0] is not ref else ""))
    rows = []
    for p in pts:
        pc = _cat_of(p["idx"])
        rows.append((p["name"], pc[3] if pc else None, f"{p['ft']:.1f} FT"))
    shown = rows[:16]
    cb = next((r for r in rows if r[0] == "CBBT"), None)  # always show the Bay Bridge-Tunnel
    if cb and cb not in shown:
        shown = shown[:15] + [cb]
    _side(cv, px, py, pw_, ph_, head_col, "SEWELLS POINT (NORFOLK)", head, meaning, shown, "FORECAST HIGH TIDE  ·  FT MLLW")
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NWS tide gauge forecasts (shading interpolated between gauges)"
    cv.footer(pkg, source=src)
    from . import fullscreen
    fullscreen.attach(cv, title=title, subtitle=sub,
                      map_fn=lambda pw, ph, view: draw_tidal_map(ev, pw, ph, cfg, view=view, radius=radius),
                      box=view, head_label="SEWELLS POINT (NORFOLK)",
                      head_value=head, head_col=head_col, meaning=meaning, rows=shown,
                      overlay=lambda c, x, y, mw_: _legend_chips(c, x, y, chips, mw_), source=src)
    return cv


def tidal_values_graphic(ev, pkg, cfg, tz, bay=False):
    """Just the map (no side panel): every gauge's forecast high tide plotted on it, colored by flood category."""
    view = tuple((cfg.get("tidal_bay_view") if bay else cfg.get("tidal_view")) or (BAY_VIEW if bay else TIDAL_VIEW))
    radius = cfg.get("tidal_bay_radius_km", 48) if bay else None
    pr = next((p for p in ev["points"] if _is_sewells(p)), sorted(ev["points"], key=lambda p: -p["idx"])[0])
    pt = pr["time"].astimezone(tz)
    cv = Canvas(cfg)
    cv.header("BAY HIGH TIDE LEVELS" if bay else "HIGH TIDE LEVELS",
              f"{pt.strftime('%A').upper()} {pt.strftime('%I:%M %p').lstrip('0')}  ·  FEET MLLW  ·  NEXT 72 HOURS")
    mx, my, mw, mh = cv.M, 196, cv.W - 2 * cv.M, cv.H - 196 - 70
    _paste_rounded(cv, draw_tidal_map(ev, mw, mh, cfg, view=view, radius=radius, mark="all"), mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    shade_from = cfg.get("tidal_map_shade_from", "action")
    chips = [(c[3], c[2]) for c in reversed(CATS) if ORDER.index(c[1]) >= ORDER.index(shade_from)]
    _legend_chips(cv, mx + 16, my + mh - 60, chips, mw - 32)
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NWS tide gauge forecasts (shading interpolated between gauges)"
    cv.footer(pkg, source=src)
    return cv


def tidal_graphics(pkg, cfg):
    from zoneinfo import ZoneInfo
    sites = (pkg.get("_extras") or {}).get("tidal_map")
    if not sites:
        return None
    tz = ZoneInfo(cfg["timezone"])
    least = cfg.get("tidal_map_min_category", "minor")
    need = next(t for t, k, *_ in CATS if k == least)
    evs = [e for e in events(sites, cfg) if e["max_idx"] >= need or cfg.get("tidal_map_always", False)]
    if not evs:
        print(f"  - tidal_flood_map: no {least} tidal flooding forecast, nothing exported")
        return None
    out = [(f"tidal_flood_map_{i}", tidal_graphic(e, pkg, cfg, tz)) for i, e in enumerate(evs[:cfg.get("tidal_map_max", 2)], 1)]
    if cfg.get("tidal_peak_map", True):  # one map for the highest tide in the next 72 hours (always made)
        from datetime import datetime
        now = datetime.now(tz)
        hrs = cfg.get("tidal_peak_hours", 72)
        def top(evl):
            win = [e for e in evl if now - timedelta(hours=2) <= e["time"] <= now + timedelta(hours=hrs)]
            return max(win, key=lambda e: (e["max_idx"], max(p["ft"] for p in e["points"]))) if win else None
        pe = top(events(sites, cfg))
        if pe:
            out.append(("tidal_flood_peak", tidal_graphic(pe, pkg, cfg, tz, peak=True)))
            out.append(("tidal_flood_values", tidal_values_graphic(pe, pkg, cfg, tz)))
        if cfg.get("tidal_bay_map", True):
            pb = top(events(sites, cfg, max_lag_h=7))
            if pb:
                out.append(("tidal_flood_peak_bay", tidal_graphic(pb, pkg, cfg, tz, bay=True, peak=True)))
                out.append(("tidal_flood_values_bay", tidal_values_graphic(pb, pkg, cfg, tz, bay=True)))
    if cfg.get("tidal_bay_map", True):  # whole Chesapeake Bay + rivers: wider tide-lag window, wider interpolation reach
        bevs = [e for e in events(sites, cfg, max_lag_h=7) if e["max_idx"] >= need or cfg.get("tidal_map_always", False)]
        out += [(f"tidal_flood_bay_{i}", tidal_graphic(e, pkg, cfg, tz, bay=True))
                for i, e in enumerate(bevs[:cfg.get("tidal_map_max", 2)], 1)]
    return out
