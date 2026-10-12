"""Frost risk and freeze potential maps for the whole Mid-Atlantic and close up on Hampton Roads.

Both use the NDFD overnight lows already fetched for frost_risk (pkg["_frost"]) -- full-bleed map, a navy fade
behind the title, city callouts with the forecast low, and a legend.
  frost_region      frost risk class (patchy / likely / freeze / hard freeze: lows adjusted for wind + cloud cover)
  freeze_potential  how cold the low gets: 36 or colder / 32 freeze / 28 hard freeze / 24 / 20
NDFD has no probabilities, so these are risk categories (not percent chances).  A map is only made for a night when
something in the view reaches the level (config frost_min_level / freeze_min_temp, default 32; frost_always forces).
"""
import math
from zoneinfo import ZoneInfo

from PIL import ImageDraw

from . import frost, fullscreen, outlookmap
from .tempdrop import LOCAL_CITIES, LOCAL_VIEW, MIDATL_CITIES, MIDATL_VIEW, _crop, _pick
from .theme import C, Canvas, z

FREEZE_CLASSES = [  # (low <=, color, legend text)
    (36, (206, 230, 248), "36° OR COLDER"), (32, (88, 170, 255), "32° FREEZE"), (28, (62, 112, 224), "28° HARD FREEZE"),
    (24, (110, 76, 214), "24° OR COLDER"), (20, (206, 62, 170), "20° OR COLDER"),
]

def _bins_for_freeze():
    return sorted([(-t - 0.0, c) for t, c, _ in FREEZE_CLASSES], key=lambda b: b[0])


def _point_vals(night, pool):
    rows = []
    for name, la, lo in pool:
        low = frost._at(night, night["low"], lo, la)
        if low is None:
            continue
        k = frost.level(low, frost._at(night, night["wind"], lo, la), frost._at(night, night["sky"], lo, la)) or 0
        rows.append({"name": name, "lat": la, "lon": lo, "low": round(low), "lvl": k, "drop": -round(low)})
    return rows


def _band(low):
    for t, c, txt in reversed(FREEZE_CLASSES):
        if low <= t:
            return c, txt
    return None, None


def _card(cv, r, px, py, boxes, bounds, big, kind):
    fs = 46 if big else 38
    nm = 21 if big else 18
    if kind == "frost":
        col, lab = frost.LEVELS[r["lvl"]][3], frost.LEVELS[r["lvl"]][1]
    else:
        col, txt = _band(r["low"])
        lab = {"36° OR COLDER": "NEAR FREEZING", "32° FREEZE": "FREEZE", "28° HARD FREEZE": "HARD FREEZE"}.get(txt, "SEVERE FREEZE") if txt else "ABOVE FREEZING"
        col = col or (70, 86, 112)
    t1 = f"{r['low']}°"
    lf = nm - 4
    bw = max(cv.width(t1, fs) + 18 + cv.width(lab, lf, "bold"), cv.width(r["name"].upper(), nm)) + 48
    bh = fs * 1.35 + nm * 1.9
    bx0, by0, bx1, by1 = bounds
    spots = [(px + 20, py - bh / 2), (px - 20 - bw, py - bh / 2), (px - bw / 2, py - bh - 22), (px - bw / 2, py + 22),
             (px + 20, py - bh - 6), (px - 20 - bw, py - bh - 6), (px + 20, py + 6), (px - 20 - bw, py + 6)]
    best = None
    for x, y in spots:
        x = min(max(x, bx0), bx1 - bw)
        y = min(max(y, by0), by1 - bh)
        hit = (x - 8 < px < x + bw + 8 and y - 8 < py < y + bh + 8) or any(
            x < b[0] + b[2] + 10 and b[0] < x + bw + 10 and y < b[1] + b[3] + 10 and b[1] < y + bh + 10 for b in boxes)
        if not hit:
            best = (x, y)
            break
    if best is None:
        return False
    x, y = best
    boxes.append((x, y, bw, bh))
    cv.d.ellipse([z(px - 11), z(py - 11), z(px + 11), z(py + 11)], fill=(255, 255, 255, 255), outline=(13, 21, 38, 255),
                 width=z(3))
    cv.rect(x, y, bw, bh, (20, 31, 54, 235), r=12)
    cv.rect(x, y + 10, 7, bh - 20, (*col, 255), r=3)
    cv.text(x + 24, y + 12, r["name"].upper(), nm, "bold", C["text"], anchor="lt")
    ty = y + nm * 1.55 + fs * 0.62
    cv.text(x + 24, ty, t1, fs, "bold", C["text"], anchor="lm")
    cv.text(x + 24 + cv.width(t1, fs) + 16, ty + 3, lab, lf, "bold", col if sum(col) > 260 else C["muted"], anchor="lm")
    return True


def _render(pkg, cfg, night, kind, view_box, pool, n_call, area_label):
    cv = Canvas(cfg)
    W, H = cv.W, cv.H
    view = fullscreen.expand_view(view_box, 175 / H, 150 / H)
    nt = _crop(night, outlookmap._view(W, H, view), 3 if view_box[1] - view_box[0] > 5 else 1)
    from .ndfdmap import _cell_painter
    if kind == "frost":
        paint = _cell_painter({"lat": nt["lat"], "lon": nt["lon"], "val": nt["risk"]}, frost.BINS, alpha=215)
    else:
        paint = _cell_painter({"lat": nt["lat"], "lon": nt["lon"], "val": -nt["low"]}, _bins_for_freeze(), alpha=215)
    lay = outlookmap.draw_map([], W, H, cfg, outline=False, painter=paint, view=view, cities=[("-", 0, 0, 2)],
                              water_alpha=0.9, county_lines=False)
    base = cv.img.convert("RGBA")
    base.alpha_composite(lay.resize(base.size) if lay.size != base.size else lay)
    cv.img = base.convert("RGB")
    cv.d = ImageDraw.Draw(cv.img, "RGBA")
    fullscreen._fade(cv, 0, 270, 238, 0)
    fullscreen._fade(cv, H - 190, H, 0, 225)
    title = "FROST RISK" if kind == "frost" else "FREEZE POTENTIAL"
    cv.header(title, f"{night['label']}  ·  {area_label}")
    w_, e_, s_, n_ = outlookmap._view(W, H, view)
    proj = lambda lo_, la: ((lo_ - w_) / (e_ - w_) * W, (n_ - la) / (n_ - s_) * H)
    rows = _point_vals(night, pool)
    boxsize = (330, 120) if not cv.tall else (300, 108)
    picks = _pick(rows, proj, (30, 215, W - 30, H - 235), n_call if not cv.tall else max(5, n_call - 2), boxsize)
    boxes = []
    for r, px, py in picks:
        _card(cv, r, px, py, boxes, (16, 215, W - 16, H - 215), not cv.tall, kind)
    if kind == "frost":
        items = [(lv[3], lv[1].title()) for lv in frost.LEVELS[1:]]
    else:
        items = [(c, t) for _, c, t in FREEZE_CLASSES]
    outlookmap._legend_chips(cv, cv.M, H - 112, items, W - 2 * cv.M)
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NWS NDFD"
    cv.footer(pkg, source=src)
    return cv


def _worst(night, view_box, kind):
    import numpy as np
    m = (night["lon"] >= view_box[0]) & (night["lon"] <= view_box[1]) & (night["lat"] >= view_box[2]) & (night["lat"] <= view_box[3])
    if not m.any():
        return None
    return float(np.nanmax(night["risk"][m])) if kind == "frost" else float(np.nanmin(night["low"][m]))


def _graphics(pkg, cfg, kind):
    nights = (pkg.get("_frost") or {}).get("nights") or []
    out = []
    views = [("midatl", tuple(cfg.get("tempdrop_view") or MIDATL_VIEW), MIDATL_CITIES, cfg.get("tempdrop_callouts", 9),
              "MID-ATLANTIC"),
             ("hr", tuple(cfg.get("tempdrop_local_view") or LOCAL_VIEW), LOCAL_CITIES, cfg.get("tempdrop_local_callouts", 8),
              "HAMPTON ROADS")]
    for i, night in enumerate(nights):
        for key, vb, pool, n_call, label in views:
            w = _worst(night, vb, kind)
            if w is None:
                continue
            ok = (w >= cfg.get("frost_min_level", 1)) if kind == "frost" else (w <= cfg.get("freeze_min_temp", 32))
            if not ok and not cfg.get("frost_always"):
                continue
            name = f"{'frost_region' if kind == 'frost' else 'freeze_potential'}_{key}_{i + 1}"
            out.append((name, _render(pkg, cfg, night, kind, vb, pool, n_call, label)))
    if not out and nights:
        print(f"  - {'frost_region' if kind == 'frost' else 'freeze_potential'}: nothing reaches the level, skipped")
    return out or None


def frost_region_graphics(pkg, cfg):
    return _graphics(pkg, cfg, "frost")


def freeze_potential_graphics(pkg, cfg):
    return _graphics(pkg, cfg, "freeze")
