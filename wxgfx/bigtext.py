""""Big text" social layout (square by default): a huge two-line headline across the top, the map filling
the middle, colored value callouts dropped right on the map, a white time-period caption, a bold tagline
banner along the bottom, and the logo.

Made as "<name>_big.png" twins of every map graphic (anything that has a full-screen spec), in the formats
listed in config "bigtext_formats" (default ["square"]). Turn off with "bigtext_maps": false.

Text options (all optional) go in overrides.json -> "bigtext", or config.json -> "bigtext_text":
  "bigtext": {
    "*":        {"tagline": "HEAVY RAIN AND WIND INTO NEXT WEEK"},          # every big-text graphic
    "wpc_qpf_d1_3": {"title": "NOR'EASTER RAIN ACCUMULATIONS",
                     "caption": "Saturday Through Monday", "callouts": 3}  # one graphic
  }
title    - the headline (wraps to two lines; default = the graphic's title)
caption  - the white box on the map (default = the time part of the subtitle)
tagline  - bottom banner (default = "<AREA>: <headline value>")
callouts - how many value boxes to drop on the map (default 4, 0 = none)
"""
import math

from PIL import Image, ImageDraw

from . import alertmap
from .theme import C, Canvas, font, z

NAVY = (22, 42, 78)
NAVY_DK = (13, 26, 52)


def _coords(cfg):
    from . import outlookmap
    pts = {}
    for name, la, lo, *_ in (list(outlookmap.STATE_CITIES) + list(outlookmap.DMA_POINTS) + list(outlookmap.POINTS)
                             + [tuple(p) for p in (cfg.get("outlook_points") or [])]):
        pts[name] = (la, lo)
    try:
        from . import cpcmap
        for c in getattr(cpcmap, "CITIES", []):
            pts.setdefault(c[0], (c[1], c[2]))
    except Exception:
        pass
    return pts


def _opts(pkg, cfg, name):
    o = {}
    for src in (cfg.get("bigtext_text") or {}, pkg.get("bigtext") or {}):
        for key in ("*", name, name.rsplit("_full", 1)[0]):
            if isinstance(src.get(key), dict):
                o.update({k: v for k, v in src[key].items() if v not in (None, "")})
    return o


def _wrap2(cv, s, maxw, max_size):
    """Split into <= 2 balanced lines and find the biggest size that fits."""
    words = s.split()
    best = (s,)
    if len(words) > 1:
        cands = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
        best = min(cands, key=lambda ls: max(cv.width(l, 100, "bold") for l in ls))
        if cv.width(s, 100, "bold") * max_size / 100 <= maxw and len(s) <= 14:
            best = (s,)
    size = max_size
    while size > 40 and max(cv.width(l, size, "bold") for l in best) > maxw:
        size -= 2
    return best, size


def _ink(col):
    return (20, 28, 46) if 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2] > 150 else (255, 255, 255)


def _pick_callouts(rows, coords, proj, area, n):
    """Choose up to n rows with distinct values, spread across the map (greedy farthest-point)."""
    x0, y0, x1, y1 = area
    cands = []
    for row in rows:  # (name, color, value) or (name, color, value, (lat, lon)) with an exact spot
        name, col, val = row[:3]
        if not col or not val or str(val).upper() in ("N/A", "--", "NONE", "0", "0%", "<2%"):
            continue
        if len(row) > 3 and row[3]:
            la, lo = row[3]
        elif name in coords:
            la, lo = coords[name]
        else:
            continue
        px, py = proj(lo, la)
        if x0 <= px <= x1 and y0 <= py <= y1:
            cands.append((name, col, str(val), px, py))
    picked, seen = [], set()
    # strongest value first (rows usually list the local point first), then spread out
    while cands and len(picked) < n:
        if not picked:
            c = cands[0]
        else:
            c = max(cands, key=lambda c: (c[2] not in seen, min(math.hypot(c[3] - p[3], c[4] - p[4]) for p in picked)))
            if c[2] in seen and min(math.hypot(c[3] - p[3], c[4] - p[4]) for p in picked) < 260:
                break
        picked.append(c)
        seen.add(c[2])
        cands.remove(c)
    return picked


def render(pkg, cfg, name, title, subtitle, map_fn, box, head_label, head_value, head_col, meaning, rows,
           overlay=None, source=None, callout_rows=None, big_caption=None, big_tagline=None, credit_text=None):
    o = _opts(pkg, cfg, name)
    cv = Canvas(cfg)
    cv.social = False  # these layouts are already built for social / full-screen sizes
    W, H = cv.W, cv.H
    M = 34
    # ---- geometry
    title_txt = str(o.get("title") or title).upper()
    model_tag = None  # a leading model name ("RRFS Peak Wind Gusts") moves out of the headline to the map corner
    for mdl in ("ECMWF", "RRFS", "HRRR", "GFS", "ICON", "GEM", "NBM", "HREF", "NDFD"):
        if title_txt.startswith(mdl + " ") and len(title_txt) > len(mdl) + 1:
            model_tag, title_txt = mdl, title_txt[len(mdl) + 1:].strip()
            break
    lines, size = _wrap2(cv, title_txt, W - 2 * M, 128 if H <= W * 1.05 else 120)
    lh = size * 1.02
    cap = str(o.get("caption") or big_caption or (subtitle or "").split("·")[0]).strip()
    cap_in_band = bool(cap) and str(o.get("caption_style", cfg.get("bigtext_caption", "band"))).lower() != "box"
    band_h = int(28 + lh * len(lines) + 24 + (54 if cap_in_band else 0))
    tag_h = 96
    leg_mode = str(o.get("legend", cfg.get("bigtext_legend", "overlay"))).lower()  # overlay|strip|cities|top|none
    leg_h = 186 if leg_mode == "both" else 104 if leg_mode in ("strip", "cities", "top") else 0
    map_y, map_h = band_h + (leg_h if leg_mode == "top" else 0), H - band_h - tag_h - leg_h
    leg_y = band_h if leg_mode == "top" else H - tag_h - leg_h
    # ---- map: fill the middle; local maps zoom to the DMA like the full-screen twins
    from .outlookmap import VIEW_BOX, _view
    if tuple(box) in (tuple(VIEW_BOX), tuple(cfg.get("outlook_view") or VIEW_BOX)):
        box = tuple(cfg.get("bigtext_local_view") or cfg.get("fullscreen_local_view") or (-77.7, -75.2, 36.05, 37.85))
    vw, ve, vs, vn = _view(W, map_h, box)
    proj = lambda lo, la: ((lo - vw) / (ve - vw) * W, (vn - la) / (vn - vs) * map_h)
    logo_box = (M, map_h - 24 - 120, M + 230, map_h - 24)
    cap_size, room = 36, W - M - (logo_box[2] + 18)  # caption sits right of the logo and shrinks to fit
    while cap and cap_size > 20 and cv.width(cap, cap_size, "medium") + 48 > room:
        cap_size -= 2
    cap_w = min(room, cv.width(cap, cap_size, "medium") + 48) if cap else 0
    if cap_in_band:
        cap_w = 0
    cap_box = (W - M - cap_w, map_h - 24 - 70, W - M, map_h - 24) if cap and not cap_in_band else None
    n_call = int(o.get("callouts", cfg.get("bigtext_callouts", 4)))
    n_leg = n_call
    if leg_mode != "overlay":
        n_call = 0  # nothing laid over the map
    picks = _pick_callouts(callout_rows or rows or [], _coords(cfg), proj, (80, 70, W - 80, map_h - 150), n_call)
    call_boxes = []
    for nm, col, val, px, py in picks:
        fs = 58 if len(val) <= 6 else 46 if len(val) <= 10 else 36
        bw, bh = cv.width(val, fs, "bold") + 40, fs * 1.36
        hit = lambda bx, by: any(bx < b[4] + b[6] + 14 and b[4] < bx + bw + 14 and by < b[5] + b[7] + 14
                                 and b[5] < by + bh + 14 for b in call_boxes) or \
            (by + bh > map_h - 160 and (bx < logo_box[2] + 10 or (cap_box and bx + bw > cap_box[0] - 10)))
        for dx, dy in ((0, 0), (0, -(bh + 18)), (0, bh + 18), (bw * 0.7, 0), (-bw * 0.7, 0),
                       (bw * 0.6, -(bh + 18)), (-bw * 0.6, bh + 18)):
            bx = min(max(px - bw / 2 + dx, M), W - M - bw)
            by = min(max(py - bh / 2 + dy, 16), map_h - bh - 16)
            if not hit(bx, by):
                call_boxes.append((nm, col, val, fs, bx, by, bw, bh))
                break
    keep = [(b[4] - 6, b[5] - 6, b[4] + b[6] + 6, b[5] + b[7] + 6) for b in call_boxes] + [logo_box]
    if cap_box:
        keep.append(cap_box)
    alertmap.LABEL_LIMIT.update({"tier": int(cfg.get("bigtext_label_tier", 1)), "max": int(cfg.get("bigtext_max_labels", 9))})
    alertmap.KEEP_OUT[:] = keep  # city labels stay clear of the callouts / caption / logo
    try:
        lay = map_fn(W, map_h, box)
    finally:
        alertmap.KEEP_OUT[:] = []
        alertmap.LABEL_LIMIT.clear()
    base = cv.img.convert("RGBA")
    base.alpha_composite(lay.resize((z(W), z(map_h))) if lay.size != (z(W), z(map_h)) else lay, (0, z(map_y)))
    cv.img = base.convert("RGB")
    cv.d = ImageDraw.Draw(cv.img, "RGBA")
    # ---- headline band
    cv.rect(0, 0, W, band_h, (*NAVY, 255))
    cv.line([(0, band_h), (W, band_h)], (255, 255, 255, 200), 3)
    for i, ln in enumerate(lines):
        cv.text(W / 2, 28 + lh * (i + 0.82), ln, size, "bold", (255, 255, 255), anchor="ms",
                stroke=3, stroke_fill=(8, 16, 34))
    if cap_in_band:  # time period as a small line under the headline, inside the navy band
        cv.text(W / 2, band_h - 22, cap.upper(), 36, "medium", (176, 205, 240), anchor="ms", maxw=W - 2 * M)
    # ---- legend bar (outside the map): value scale ("strip"), places with values ("cities"), or both
    def _legend_row(kind, ry, rh, fs0):
        if kind == "cities":
            items = [(nm.upper(), col, val) for nm, col, val, _, _ in
                     _pick_callouts(callout_rows or rows or [], _coords(cfg), proj, (0, 0, W, map_h), min(n_leg, 3) or 3)]
        else:
            seen, items = set(), []
            for row in (callout_rows or rows or []):
                nm, col, val = row[:3]
                if col and val and str(val).upper() not in ("N/A", "--", "NONE", "0", "0%", "<2%") and str(val) not in seen:
                    seen.add(str(val)); items.append(("", col, str(val)))

            def _num(t):
                try:
                    return float("".join(ch for ch in t[2] if ch.isdigit() or ch in ".-") or 0)
                except ValueError:
                    return 0
            items = sorted(items, key=_num)
            if len(items) > 5:
                idx = [round(i * (len(items) - 1) / 4) for i in range(5)]
                items = [items[i] for i in sorted(set(idx))]
        if not items:
            return
        names = kind == "cities"
        nfs = 28 if fs0 >= 44 else 26
        fs = fs0
        wid = lambda: [cv.width(v, fs, "bold") + 44 + (cv.width(n, nfs, "bold") + 16 if names else 0) for n, _, v in items]
        wids, gap = wid(), 22
        while sum(wids) + gap * (len(items) - 1) > W - 2 * M and fs > 26:
            fs -= 2
            wids = wid()
        x = (W - (sum(wids) + gap * (len(items) - 1))) / 2
        ch = fs * 1.4
        cy = ry + (rh - ch) / 2
        for (n, col, v), w in zip(items, wids):
            if names:
                nw = cv.width(n, nfs, "bold") + 16
                cv.text(x, cy + ch / 2 + 2, n, nfs, "bold", (255, 255, 255), anchor="lm")
                bx, bw = x + nw, w - nw
            else:
                bx, bw = x, w
            cv.rect(bx - 4, cy - 4, bw + 8, ch + 8, (255, 255, 255, 255), r=6)
            cv.rect(bx, cy, bw, ch, (*col, 255), r=4)
            cv.text(bx + bw / 2, cy + ch / 2 + 2, v, fs, "bold", _ink(col), anchor="mm")
            x += w + gap

    if leg_h:
        cv.rect(0, leg_y, W, leg_h, (*NAVY_DK, 255))
        cv.line([(0, leg_y + (leg_h if leg_mode == "top" else 0))] + [(W, leg_y + (leg_h if leg_mode == "top" else 0))],
                (255, 255, 255, 120), 2)
        if leg_mode == "both":
            _legend_row("cities", leg_y + 6, 84, 38)
            cv.line([(M, leg_y + 92), (W - M, leg_y + 92)], (255, 255, 255, 45), 1.5)
            _legend_row("strip", leg_y + 94, 92, 42)
        else:
            _legend_row("cities" if leg_mode == "cities" else "strip", leg_y, leg_h, 46)
    # ---- callouts on the map
    for nm, col, val, fs, bx, by, bw, bh in call_boxes:
        y = map_y + by
        cv.rect(bx - 4, y - 4, bw + 8, bh + 8, (255, 255, 255, 255), r=6)
        cv.rect(bx, y, bw, bh, (*col, 255), r=4)
        cv.text(bx + bw / 2, y + bh / 2 + 2, val, fs, "bold", _ink(col), anchor="mm")
    # ---- caption box
    if cap_box:
        x0, y0, x1, y1 = cap_box
        cv.rect(x0, map_y + y0, x1 - x0, y1 - y0, (255, 255, 255, 245), r=4)
        cv.text((x0 + x1) / 2, map_y + (y0 + y1) / 2 + 2, cap, cap_size, "medium", NAVY_DK, anchor="mm",
                maxw=x1 - x0 - 30)
    # ---- logo (bottom-left of the map, on a soft backing so it reads over any colors)
    from pathlib import Path
    lp = cfg.get("logo_path")
    x0, y0, x1, y1 = logo_box
    cv.rect(x0, map_y + y0, x1 - x0, y1 - y0, (13, 21, 38, 200), r=14)
    if lp and Path(lp).exists():
        lg = Image.open(lp).convert("RGBA")
        hh = z(y1 - y0 - 16)
        lg = lg.resize((int(lg.width * hh / lg.height), hh), Image.LANCZOS)
        if lg.width > z(x1 - x0 - 16):
            ww = z(x1 - x0 - 16)
            lg = lg.resize((ww, int(lg.height * ww / lg.width)), Image.LANCZOS)
        cx = z((x0 + x1) / 2) - lg.width // 2
        cy = z(map_y + (y0 + y1) / 2) - lg.height // 2
        cv.img.paste(lg, (cx, cy), lg)
        cv.d = ImageDraw.Draw(cv.img, "RGBA")
    else:
        cv.text((x0 + x1) / 2, map_y + y0 + 44, "METEOROLOGIST", 16, "medium", C["muted"], anchor="mm")
        cv.text((x0 + x1) / 2, map_y + y0 + 78, cfg.get("brand_name", "RICKY MATTHEWS").upper(), 26, "bold", anchor="mm")
    if model_tag:  # small model label, bottom-right of the map
        lbl = f"MODEL: {model_tag}"
        lw = cv.width(lbl, 26, "bold") + 30
        cv.rect(W - M - lw + 10, map_y + map_h - 14 - 46, lw, 46, (13, 21, 38, 215), r=8)
        cv.text(W - M - lw / 2 + 10, map_y + map_h - 14 - 23 + 1, lbl, 26, "bold", (255, 255, 255), anchor="mm")
    # ---- tagline banner
    ty = H - tag_h
    cv.rect(0, ty, W, tag_h, (*NAVY, 255))
    cv.line([(0, ty), (W, ty)], (255, 255, 255, 200), 3)
    area = (cfg.get("location") or {}).get("area", "Hampton Roads Area").upper()
    tag = str(o.get("tagline") or big_tagline or (f"{area}: {head_value}" if head_value else title_txt)).upper()
    ts = 50
    while ts > 26 and cv.width(tag, ts, "bold") > W - 2 * M:
        ts -= 2
    cv.text(W / 2, ty + tag_h / 2 + 2, tag, ts, "bold", (255, 255, 255), anchor="mm", maxw=W - 2 * M)
    if credit_text:  # small "data from" strip at the bottom of the map, just above the tagline banner
        from .fullscreen import credit
        credit(cv, credit_text, right=W - M, bottom=map_y + map_h - 24 - 70 - 12 if cap_box else map_y + map_h - (66 if model_tag else 14))
    return cv
