"""Extra graphics: tides, beach & boating, yesterday at ORF, rainfall so far, record watch,
first freeze, commute, weekend planner, sun & UV, tropical outlook, warning counter,
ORF aviation, and Be Weather Aware. Every layout adapts to wide / vertical / post."""
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from . import extras_data as X
from .icons import draw_icon
from .theme import C, Canvas, font, z

GOOD, OK_, WARN, BAD, SEVERE = (70, 180, 100), (240, 205, 60), (245, 150, 40), (228, 60, 60), (200, 70, 210)
NEUTRAL = (70, 86, 112)
DARK_TXT = (20, 28, 46)


# ------------------------------------------------------------------ helpers
def _ex(pkg):
    return pkg.get("_extras") or {}


def _tz(cfg):
    return ZoneInfo(cfg["timezone"])


def _t(dt):
    return dt.strftime("%I:%M %p").lstrip("0") if dt else "--"


def _lum(c):
    return 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]


def _ink(c):
    return DARK_TXT if _lum(c) > 150 else C["text"]


def area(cv):
    return cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top


def grid(x, y, w, h, n, cols, gap=18):
    rows = -(-n // cols)
    cw, rh = (w - gap * (cols - 1)) / cols, (h - gap * (rows - 1)) / rows
    return [(x + (i % cols) * (cw + gap), y + (i // cols) * (rh + gap), cw, rh) for i in range(n)]


def tile(cv, box, label, value, sub=None, bar=None, vsize=None, sub2=None):
    x, y, w, h = box
    cv.accent_row(x, y, w, h, bar=bar)
    vs = vsize or min(78, h * 0.34, w * 0.2)
    cv.text(x + 30, y + min(46, h * 0.2), label, min(26, h * 0.12), "bold", C["muted"], anchor="ls", maxw=w - 50)
    cv.text(x + 30, y + h * 0.52 + vs * 0.35, value, vs, "bold", anchor="ls", maxw=w - 50)
    if sub:
        cv.text(x + 30, y + h * 0.52 + vs * 0.35 + min(42, h * 0.16), sub, min(28, h * 0.1), "medium", C["muted"],
                anchor="ls", maxw=w - 50)
    if sub2:
        cv.text(x + 30, y + h * 0.52 + vs * 0.35 + min(80, h * 0.29), sub2, min(26, h * 0.095), "medium", C["muted"],
                anchor="ls", maxw=w - 50)


def pill(cv, x, y, text, col, size=20, anchor="l"):
    w = cv.width(text, size, "bold") + 28
    h = size * 1.6
    x0 = x if anchor == "l" else x - w
    cv.rect(x0, y, w, h, (*col, 255), r=h / 2)
    cv.text(x0 + w / 2, y + h / 2, text, size, "bold", _ink(col), anchor="mm")
    return w


def footer(cv, pkg):
    cv.footer(pkg, show_source=False)


# ================================================================== TIDES
FLOOD_WORDS = {None: ("NO FLOODING EXPECTED", GOOD, "Water levels stay below flood stage."),
               "action": ("NEAR FLOOD STAGE", OK_, "Water may reach the most vulnerable low spots and ramps."),
               "minor": ("MINOR TIDAL FLOODING", WARN, "Minor flooding of low-lying roads and properties near high tide."),
               "moderate": ("MODERATE TIDAL FLOODING", BAD, "Numerous roads flooded; avoid driving through water."),
               "major": ("MAJOR TIDAL FLOODING", SEVERE, "Widespread, dangerous flooding. Follow local officials.")}


def _tide_chart(cv, box, td, tz):
    x, y, w, h = box
    cv.rect(x, y, w, h, C["panel"], r=16)
    px0, px1, py0, py1 = x + 86, x + w - 30, y + 34, y + h - 60
    st = td["stages"]
    series = td["forecast"] or []
    allv = [v for _, v in td["curve"]] + [v for _, v in series] + [v for _, v in td["observed"]]
    lo = min(-0.5, min(allv, default=0) - 0.3)
    hi = max((st.get("moderate") or 5.5) + 0.6, max(allv, default=4) + 0.6)
    ext = td.get("extension") or []
    allv += [v for _, v in ext]
    lo = min(lo, min(allv, default=0) - 0.3)
    hi = max(hi, max(allv, default=4) + 0.6)
    t0 = min([t for t, _ in td["curve"]] + [t for t, _ in td["observed"]], default=None)
    t1 = max([t for t, _ in td["curve"]] + [t for t, _ in series] + [t for t, _ in ext], default=None)
    if not t0 or not t1:
        return
    X_ = lambda t: px0 + (t - t0).total_seconds() / (t1 - t0).total_seconds() * (px1 - px0)
    Y_ = lambda v: py1 - (v - lo) / (hi - lo) * (py1 - py0)
    for k, col in (("minor", WARN), ("moderate", BAD), ("major", SEVERE)):
        v = st.get(k)
        if v is None or v > hi:
            continue
        nxt = {"minor": st.get("moderate"), "moderate": st.get("major"), "major": None}[k]
        top = Y_(min(nxt, hi)) if nxt and nxt < hi else py0
        cv.rect(px0, top, px1 - px0, Y_(v) - top, (*col, 55))
        cv.line([(px0, Y_(v)), (px1, Y_(v))], (*col, 230), 2)
        cv.text(px1 - 8, Y_(v) - 6, f"{k.upper()} {v:g}'", 17, "bold", col, anchor="rs")
    step = 1 if hi - lo <= 7 else 2
    v = math.ceil(lo)
    while v <= hi:
        cv.line([(px0, Y_(v)), (px1, Y_(v))], (255, 255, 255, 28), 1)
        cv.text(px0 - 12, Y_(v), f"{v}'", 18, "medium", C["muted"], anchor="rm")
        v += step
    span_h = (t1 - t0).total_seconds() / 3600
    tick = 6 if (px1 - px0) / max(1, span_h) * 6 >= 70 else 12  # keep the time labels from crowding
    t = t0.replace(minute=0, second=0) + timedelta(hours=(tick - t0.hour % tick) % tick)
    while t <= t1:
        if not t.hour:  # midnight: a faint day divider
            cv.line([(X_(t), py0), (X_(t), py1)], (255, 255, 255, 34), 1.5)
        cv.line([(X_(t), py1), (X_(t), py1 + 8)], (255, 255, 255, 120), 2)
        lab = (t.strftime("%I%p").lstrip("0") if t.hour != 12 else "NOON") if t.hour else t.strftime("%a").upper()
        cv.text(X_(t), py1 + 34, lab, 18 if w < 1000 else 20, "bold" if not t.hour else "medium",
                C["text"] if not t.hour else C["muted"], anchor="ms")
        t += timedelta(hours=tick)
    cv.line([(X_(a), Y_(b)) for a, b in td["curve"]], (176, 190, 212, 150), 2)
    if series:
        cv.line([(X_(a), Y_(b)) for a, b in series], (88, 200, 255, 255), 5)
    if len(ext) > 1:  # beyond the end of the NWS forecast: tide + surge carried forward, dashed
        pts = [(X_(a), Y_(b)) for a, b in ext]
        for k in range(0, len(pts) - 1, 2):
            cv.line(pts[k:k + 2], (88, 200, 255, 150), 4)
    if td["observed"]:
        cv.line([(X_(a), Y_(b)) for a, b in td["observed"]], (255, 255, 255, 255), 5)
    now_x = X_(series[0][0]) if series else None
    if now_x:
        cv.line([(now_x, py0), (now_x, py1)], (255, 255, 255, 110), 2)
        cv.text(now_x + 6, py0 + 16, "NOW", 16, "bold", C["muted"], anchor="ls")
    for tt in td["tides"]:
        if t0 <= tt["time"] <= t1 and tt["type"] == "H":
            cv.text(X_(tt["time"]), Y_(tt["ft"]) - 14, f"{tt['ft']:.1f}'", 18, "bold", anchor="ms", stroke=1.5)
    lx = px0 + 12
    fc_lab = "NWS FORECAST" if td.get("forecast_source") == "NWS" else "FORECAST (TIDE + SURGE NOW)"
    keys = [("OBSERVED", (255, 255, 255)), (fc_lab, (88, 200, 255)), ("ASTRONOMICAL TIDE", (176, 190, 212))]
    if len(ext) > 1:
        keys.append(("PAST NWS FORECAST (DASHED)", (88, 200, 255)))
    for label, col in keys:
        cv.rect(lx, py1 - 26, 18, 6, (*col, 255))
        cv.text(lx + 26, py1 - 17, label, 15, "bold", C["muted"], anchor="lm")
        lx += cv.width(label, 15, "bold") + 60


def tides(pkg, cfg):
    td = _ex(pkg).get("tides")
    if not td:
        return None
    tz = _tz(cfg)
    cv = Canvas(cfg)
    fe = td.get("forecast_end")
    span = (f"THROUGH {fe.strftime('%a').upper()} {_t(fe)}  ·  NWS FORECAST" if fe
            else f"NEXT {td.get('hours', 48)} HOURS  ·  PREDICTED TIDE")
    cv.header("TIDES & COASTAL FLOODING", f"{td['station_name']}  ·  {span}")
    x, y, w, h = area(cv)
    if cv.tall:
        ch = h * (0.46 if cv.fmt == "vertical" else 0.44)
        chart, side = (x, y, w, ch), (x, y + ch + 18, w, h - ch - 18)
    else:
        chart, side = (x, y, 1160, h), (x + 1180, y, w - 1180, h)
    _tide_chart(cv, chart, td, tz)
    sx, sy, sw, sh = side
    cv.rect(sx, sy, sw, sh, C["panel"], r=16)
    peak = td["peak"]
    cat = X.flood_category(peak[1], td["stages"]) if peak else None
    words, col, meaning = FLOOD_WORDS[cat]
    cv.text(sx + 26, sy + 24, "PEAK WATER LEVEL", 20, "bold", C["muted"], anchor="lt")
    if peak:
        cv.text(sx + 26, sy + 104, f"{peak[1]:.1f} FT", 64, "bold", anchor="ls")
        cv.text(sx + 26, sy + 138, f"{peak[0].strftime('%a').upper()} {_t(peak[0])}  ·  MLLW", 22, "medium", C["muted"],
                anchor="ls")
    cv.rect(sx + 26, sy + 160, sw - 52, 64, (*col, 255), r=12)
    cv.text(sx + sw / 2, sy + 192, words, 30, "bold", _ink(col), anchor="mm", maxw=sw - 80)
    used = cv.paragraph(sx + 26, sy + 240, meaning, 22, "regular", sw - 52, max_lines=2, lh=1.25)
    ty = sy + 240 + used + 18
    if td.get("anomaly") is not None:
        cv.text(sx + 26, ty, f"Running {abs(td['anomaly']):.1f} ft {'above' if td['anomaly'] >= 0 else 'below'} the "
                              f"predicted tide right now", 20, "medium", C["muted"], anchor="lt", maxw=sw - 52)
        ty += 36
    cv.line([(sx + 26, ty), (sx + sw - 26, ty)], (255, 255, 255, 60), 1.5)
    ty += 12
    official = td.get("tide_times_source", "NWS" if td.get("forecast_source") == "NWS" else "astronomical") == "NWS"
    cv.text(sx + 26, ty, "HIGH & LOW TIDES  ·  " + ("OFFICIAL NWS FORECAST" if official else "ASTRONOMICAL (NWS FORECAST UNAVAILABLE)"),
            17, "bold", C["muted"], anchor="lt", maxw=sw - 52)
    ty += 30
    ncol = 2 if sw > 900 else 1
    fit = max(1, int((sy + sh - 16 - ty) // 33)) * ncol  # every high & low in the window that fits (rows >= 33 px)
    rows = td["tides"][:fit]
    per = -(-len(rows) // ncol)
    rh = min(52, (sy + sh - 16 - ty) / max(1, per))
    cw = (sw - 52 - (30 if ncol == 2 else 0)) / ncol
    for k, t in enumerate(rows):
        c, r = divmod(k, per)
        cx, yy = sx + 26 + c * (cw + 30), ty + r * rh
        hl = t["type"] == "H"
        cv.text(cx, yy + rh / 2, "HIGH" if hl else "LOW", min(24, rh * 0.5), "bold", (88, 200, 255) if hl else C["muted"], anchor="lm")
        cv.text(cx + cw * 0.28, yy + rh / 2, f"{t['time'].strftime('%a')} {_t(t['time'])}", min(24, rh * 0.5), "medium", anchor="lm")
        cv.text(cx + cw, yy + rh / 2, f"{t['ft']:.1f} ft" + ("*" if t.get("src") else ""), min(24, rh * 0.5), "bold",
                anchor="rm")
    footer(cv, pkg)
    return cv


# ================================================================== HIGH TIDES (MULTI-SITE)
CAT_BOX = {None: ("NO FLOODING", (70, 180, 100)), "action": ("ACTION STAGE", (255, 232, 0)),
           "minor": ("MINOR FLOODING", (255, 153, 0)), "moderate": ("MODERATE FLOODING", (235, 30, 30)),
           "major": ("MAJOR FLOODING", (190, 60, 240))}


def _high_card(cv, box, hgh, stages_known):
    x, y, w, h = box
    lab, col = CAT_BOX[hgh["cat"]] if stages_known else ("NO FLOOD STAGE SET", NEUTRAL)
    cv.rect(x, y, w, h, (255, 255, 255, 14), r=12)
    f = min(34, h * 0.24, w * 0.072)
    cv.text(x + 22, y + h * 0.4, f"{hgh['time'].strftime('%a').upper()} {_t(hgh['time'])}", f, "bold", anchor="ls", maxw=w * 0.55)
    cv.text(x + 22, y + h * 0.4 + f * 1.3, f"{hgh['ft']:.1f} FT", f * 1.05, "bold", (88, 200, 255), anchor="ls")
    bw_ = w * 0.44
    cv.rect(x + w - bw_ - 14, y + h * 0.16, bw_, h * 0.68, (*col, 255), r=10)
    cv.paragraph(x + w - bw_ / 2 - 14, y + h * 0.16, lab, min(24, h * 0.17, bw_ * 0.1), "bold", bw_ - 16, max_lines=2, anchor="ma",
                 valign="middle", box_h=h * 0.68, lh=1.05, fill=_ink(col))


def high_tides(pkg, cfg, key="high_tides"):
    sites = [s for s in (_ex(pkg).get(key) or []) if s.get("highs")]
    if not sites:
        return None
    cv = Canvas(cfg)
    cv.header("HIGH TIDE FORECAST", "NEXT TWO HIGH TIDES  ·  WATER LEVEL IN FEET (MLLW)")
    x, y, w, h = area(cv)
    n = len(sites)
    gap = 14
    rh = (h - gap * (n - 1)) / n
    for i, s in enumerate(sites):
        ry = y + i * (rh + gap)
        worst = max((hh["cat"] for hh in s["highs"]), key=lambda c: [None, "action", "minor", "moderate", "major"].index(c))
        bar = CAT_BOX[worst][1] if s.get("stages") else NEUTRAL
        cv.accent_row(x, ry, w, rh, bar=bar)
        if not cv.tall:
            cv.text(x + 34, ry + rh / 2 - 6, s["name"].upper(), min(36, rh * 0.26), "bold", anchor="ls", maxw=360)
            if s.get("source") == "astronomical tide":
                cv.text(x + 34, ry + rh / 2 + 26, "ASTRONOMICAL TIDE ONLY", 16, "bold", C["muted"], anchor="ls")
            cards = grid(x + 420, ry + 12, w - 440, rh - 24, 2, 2, 16)
        else:
            nf = min(30, rh * 0.16)
            cv.text(x + 30, ry + 16 + nf, s["name"].upper(), nf, "bold", anchor="ls", maxw=w * 0.6)
            if s.get("source") == "astronomical tide":
                cv.text(x + w - 24, ry + 16 + nf, "ASTRONOMICAL", 15, "bold", C["muted"], anchor="rs")
            cards = grid(x + 24, ry + 30 + nf, w - 48, rh - 44 - nf, 2, 2, 14)
        for hgh, box in zip(s["highs"][:2], cards):
            _high_card(cv, box, hgh, bool(s.get("stages")))
    # legend
    lx, ly = cv.M, cv.H - 62 if cv.tall else cv.H - 34
    if not cv.tall:
        lx = cv.W - cv.M
        for key in ("major", "moderate", "minor", "action", None):
            lab, col = CAT_BOX[key]
            wtxt = cv.width(lab, 15, "bold")
            lx -= wtxt + 40
            cv.rect(lx, ly - 15, 18, 18, (*col, 255), r=4)
            cv.text(lx + 24, ly - 6, lab, 15, "bold", C["muted"], anchor="lm")
    footer(cv, pkg)
    return cv


# ================================================================== BEACH & BOATING
RIP_COL = {"Low": GOOD, "Moderate": OK_, "High": BAD}


def beach(pkg, cfg):
    b = _ex(pkg).get("beach")
    if not b or not (b.get("srf") or b.get("marine")):
        return None
    uv = _ex(pkg).get("uv") or []
    cv = Canvas(cfg)
    cv.header("BEACH & BOATING", "RIP CURRENTS  ·  SURF  ·  BAY & COASTAL WATERS")
    x, y, w, h = area(cv)
    places = list(b.get("srf", {}).items())[:3]
    marine = list(b.get("marine", {}).items())[:3]
    if cv.tall:
        bh = h * (0.5 if cv.fmt == "vertical" else 0.48)
        boxes = grid(x, y, w, bh, max(1, len(places)), 1, 14)
        mbox = (x, y + bh + 18, w, h - bh - 18)
    else:
        boxes = grid(x, y, w, 330, max(1, len(places)), max(1, len(places)), 20)
        mbox = (x, y + 350, w, h - 350)
    for (name, s), (bx, by, bw, bh_) in zip(places, boxes):
        rip = s.get("rip") or "N/A"
        col = RIP_COL.get(rip, NEUTRAL)
        cv.accent_row(bx, by, bw, bh_, bar=col)
        big = cv.tall
        cv.text(bx + 30, by + (40 if not big else bh_ * 0.34), name.upper(), 30 if not big else min(30, bh_ * 0.2), "bold",
                anchor="ls", maxw=bw * (0.9 if not big else 0.36))
        if not big:
            cv.text(bx + 30, by + 80, "RIP CURRENT RISK", 18, "bold", C["muted"], anchor="ls")
            cv.rect(bx + 30, by + 96, bw - 60, 70, (*col, 255), r=12)
            cv.text(bx + bw / 2, by + 131, rip.upper(), 38, "bold", _ink(col), anchor="mm")
            cv.text(bx + 30, by + 216, "SURF", 18, "bold", C["muted"], anchor="ls")
            cv.text(bx + 30, by + 256, (s.get("surf") or "--").replace(" feet", " ft"), 34, "bold", anchor="ls", maxw=bw / 2 - 40)
            cv.text(bx + bw / 2 + 10, by + 216, "WATER", 18, "bold", C["muted"], anchor="ls")
            wt = (s.get("water") or "").replace(" degrees", "°") or (f"{b['water_temp']}°" if b.get("water_temp") else "--")
            cv.text(bx + bw / 2 + 10, by + 256, wt, 34, "bold", anchor="ls")
            if s.get("uv"):
                cv.text(bx + 30, by + 300, f"MAX UV {s['uv']}", 20, "bold", C["muted"], anchor="ls")
        else:
            cv.text(bx + 30, by + bh_ * 0.34 + 36, f"Surf {(s.get('surf') or '--').replace(' feet', ' ft')}  ·  "
                                                    f"Water {(s.get('water') or '--').replace(' degrees', '°')}",
                    min(22, bh_ * 0.15), "medium", C["muted"], anchor="ls", maxw=bw * 0.5)
            pw = min(bw * 0.4, 380)
            cv.rect(bx + bw - pw - 24, by + bh_ * 0.2, pw, bh_ * 0.6, (*col, 255), r=12)
            cv.text(bx + bw - pw / 2 - 24, by + bh_ * 0.36, "RIP CURRENTS", min(16, bh_ * 0.11), "bold", _ink(col), anchor="mm")
            cv.text(bx + bw - pw / 2 - 24, by + bh_ * 0.58, rip.upper(), min(36, bh_ * 0.24), "bold", _ink(col), anchor="mm")
    mx, my, mw, mh = mbox
    cv.rect(mx, my, mw, mh, C["panel"], r=16)
    cv.text(mx + 26, my + 22, "BOATING FORECAST", 20, "bold", C["muted"], anchor="lt")
    if uv:
        pk = max(uv, key=lambda u: u["uv"])
        cat, ucol = X.uv_category(pk["uv"])
        pill(cv, mx + mw - 26, my + 14, f"PEAK UV {pk['uv']} {cat}", ucol, 17, anchor="r")
    ry = my + 62
    n = max(1, len(marine))
    rh = (my + mh - 14 - ry) / n
    for label, m in marine:
        cv.rect(mx + 26, ry + 4, 6, rh - 16, C["rule"])
        cv.text(mx + 46, ry + 4, label.upper(), min(24, rh * 0.22), "bold", anchor="lt", maxw=mw * 0.6)
        cv.paragraph(mx + 46, ry + 4 + min(24, rh * 0.22) * 1.4, f"{m['period']}: {m['text']}",
                     min(24, rh * 0.2), "regular", mw - 90, max_lines=2 if rh < 150 else 3, lh=1.22)
        ry += rh
    if not marine:
        cv.text(mx + 26, my + 80, "Marine forecast unavailable.", 24, "regular", C["muted"], anchor="lt")
    footer(cv, pkg)
    return cv


# ================================================================== YESTERDAY / RAIN SO FAR
def _dep(v, unit="°"):
    if v is None:
        return ""
    if unit == '"':
        return f"{abs(v):.2f}\" {'ABOVE' if v > 0 else 'BELOW'} NORMAL" if abs(v) >= 0.005 else "NORMAL"
    return f"{abs(v):.0f}{unit} {'ABOVE' if v > 0 else 'BELOW'} NORMAL" if v else "NORMAL"


def _in(v):
    if v is None:
        return "--"
    return "TRACE" if 0 < v < 0.005 else f'{v:.2f}"'


def yesterday(pkg, cfg):
    cli = _ex(pkg).get("cli")
    if not cli or not cli.get("maximum"):
        return None
    cv = Canvas(cfg)
    d = date.fromisoformat(cli["date"]) if cli.get("date") else None
    today = cli.get("which") != "yesterday"
    title = "YESTERDAY AT ORF" if not today else "TODAY AT ORF"
    thru = f"  ·  THROUGH {cli['as_of']}" if today and cli.get("as_of") else "  ·  SO FAR" if today else ""
    cv.header(title, (f"NORFOLK INTERNATIONAL AIRPORT  ·  {d.strftime('%A, %b').upper()} {d.day}" if d
                      else "NORFOLK INTERNATIONAL AIRPORT") + thru)
    x, y, w, h = area(cv)
    mx_, mn, pd, pm = cli.get("maximum", {}), cli.get("minimum", {}), cli.get("precip_day", {}), cli.get("precip_month", {})
    items = []
    for lab, r in (("HIGH", mx_), ("LOW", mn)):
        dep = r.get("departure")
        col = BAD if (dep or 0) >= 5 else (88, 150, 255) if (dep or 0) <= -5 else C["rule"]
        rec = f"RECORD {r['record']:.0f}° ({r['record_year']})" if r.get("record") is not None else None
        if r.get("record_flag"):
            rec = "NEW RECORD!"
            col = SEVERE
        items.append((lab, f"{r['obs']:.0f}°" if r.get("obs") is not None else "--",
                      _dep(dep) + (f" ({r['normal']:.0f}°)" if r.get("normal") is not None else ""), rec, col))
    items.append(("RAINFALL", _in(pd.get("obs")), f"NORMAL {_in(pd.get('normal'))}",
                  f"RECORD {pd['record']:.2f}\" ({pd['record_year']})" if pd.get("record") else None,
                  (88, 170, 255) if (pd.get("obs") or 0) > 0 else C["rule"]))
    if pm:
        items.append(("MONTH TO DATE", _in(pm.get("obs")), _dep(pm.get("departure"), '"'),
                      f"NORMAL {_in(pm.get('normal'))}", (88, 170, 255)))
    cols = 2 if cv.tall else len(items)
    for (lab, val, sub, sub2, col), box in zip(items, grid(x, y, w, h, len(items), cols, 22)):
        tile(cv, box, lab, val, sub, bar=col, sub2=sub2, vsize=min(130 if not cv.tall else 110, box[3] * 0.34, box[2] * 0.3))
    footer(cv, pkg)
    return cv


def _bar_pair(cv, box, title, obs, normal, dep):
    x, y, w, h = box
    cv.rect(x, y, w, h, C["panel"], r=16)
    cv.text(x + 30, y + 30, title, 26, "bold", C["muted"], anchor="lt")
    top = max(obs or 0, normal or 0) * 1.15 or 1
    bx, bw = x + 200, w - 250
    for i, (lab, v, col) in enumerate((("OBSERVED", obs, (88, 170, 255)), ("NORMAL", normal, (176, 190, 212)))):
        by = y + 100 + i * (h - 200) / 2.2
        bh = min(70, (h - 200) / 3)
        cv.text(x + 30, by + bh / 2, lab, 22, "bold", anchor="lm")
        cv.rect(bx, by, bw, bh, (255, 255, 255, 20), r=10)
        cv.rect(bx, by, max(12, bw * (v or 0) / top), bh, (*col, 255), r=10)
        cv.text(bx + max(12, bw * (v or 0) / top) + 14, by + bh / 2, _in(v), 30, "bold", anchor="lm")
    col = GOOD if (dep or 0) >= 0 else WARN
    txt = (f"{abs(dep):.2f}\" SURPLUS" if dep >= 0 else f"{abs(dep):.2f}\" DEFICIT") if dep is not None else "--"
    pill(cv, x + 30, y + h - 70, txt, col, 26)


def month_rain(pkg, cfg):
    cli = _ex(pkg).get("cli")
    if not cli or not cli.get("precip_month"):
        return None
    cv = Canvas(cfg)
    d = date.fromisoformat(cli["date"]) if cli.get("date") else None
    asof = f" ({cli['as_of']})" if cli.get("which") != "yesterday" and cli.get("as_of") else ""
    cv.header("RAINFALL SO FAR", f"NORFOLK INTERNATIONAL AIRPORT  ·  THROUGH {d.strftime('%b').upper()} {d.day}{asof}" if d else "")
    x, y, w, h = area(cv)
    pm, py = cli["precip_month"], cli.get("precip_year") or {}
    boxes = grid(x, y, w, h, 2, 1 if cv.tall else 2, 22)
    _bar_pair(cv, boxes[0], (d.strftime("%B").upper() if d else "THIS MONTH"), pm.get("obs"), pm.get("normal"), pm.get("departure"))
    _bar_pair(cv, boxes[1], f"{d.year if d else ''} SO FAR", py.get("obs"), py.get("normal"), py.get("departure"))
    footer(cv, pkg)
    return cv


# ================================================================== RECORD WATCH
def record_watch(pkg, cfg):
    ac = _ex(pkg).get("acis")
    if not ac:
        return None
    start = 1 if pkg.get("evening_mode") else 0
    days = pkg["days"][start:start + 5]
    rows = []
    for d in days:
        k = d["date"][5:]
        r = ac["records"].get(k) or {}
        n = ac["normals"].get(k) or {}
        near_hot = r.get("hi") is not None and d["high"] is not None and d["high"] >= r["hi"] - 2
        near_warm_low = r.get("hi_min") is not None and d["low"] is not None and d["low"] >= r["hi_min"] - 1
        near_cold = r.get("lo") is not None and d["low"] is not None and d["low"] <= r["lo"] + 2
        flag = "NEAR RECORD HEAT" if near_hot else "NEAR RECORD WARM LOW" if near_warm_low else \
            "NEAR RECORD COLD" if near_cold else None
        rows.append({"d": d, "rec": r, "norm": n, "flag": flag})
    cv = Canvas(cfg)
    cv.header("RECORD WATCH", "NORFOLK INTERNATIONAL AIRPORT  ·  FORECAST vs NORMAL vs RECORD")
    x, y, w, h = area(cv)
    if cv.tall:
        boxes = grid(x, y, w, h, len(rows), 1, 14)
    else:
        boxes = grid(x, y, w, h, len(rows), len(rows), 18)
    for row, (bx, by, bw, bh) in zip(rows, boxes):
        d, r, n = row["d"], row["rec"], row["norm"]
        col = BAD if row["flag"] and "COLD" not in row["flag"] else (88, 150, 255) if row["flag"] else C["rule"]
        cv.accent_row(bx, by, bw, bh, bar=col)
        if not cv.tall:
            cx = bx + bw / 2 + 4
            cv.text(cx, by + 56, d["dow"], 44, "bold", anchor="ms")
            cv.text(cx, by + 90, d["date_label"].upper(), 22, "medium", C["muted"], anchor="ms")
            ys = by + 150
            for lab, val, c in (("FORECAST HIGH", d["high"], C["text"]), ("NORMAL", n.get("hi"), C["muted"]),
                                ("RECORD", r.get("hi"), (255, 120, 110))):
                cv.text(cx, ys, lab, 18, "bold", C["muted"], anchor="ms")
                cv.text(cx, ys + 66, f"{val:.0f}°" if val is not None else "--", 60 if lab.startswith("F") else 48, "bold", c, anchor="ms")
                if lab == "RECORD" and r.get("hi_yr"):
                    cv.text(cx, ys + 96, f"({r['hi_yr']})", 20, "medium", C["muted"], anchor="ms")
                ys += 150
            cv.text(cx, by + bh - 110, f"LOW {d['low']}°  ·  NORMAL {n.get('lo', 0):.0f}°" if n.get("lo") is not None else f"LOW {d['low']}°",
                    19, "medium", C["muted"], anchor="ms", maxw=bw - 30)
            if row["flag"]:
                pill(cv, cx - (cv.width(row["flag"], 16, "bold") + 28) / 2, by + bh - 76, row["flag"], col, 16)
        else:
            cy = by + bh / 2
            f = min(44, bh * 0.3)
            cv.text(bx + 30, cy - 2, d["dow"], f, "bold", anchor="ls")
            cv.text(bx + 30, cy + f * 0.75, d["date_label"].upper(), f * 0.5, "medium", C["muted"], anchor="ls")
            cols = [("FORECAST", d["high"], C["text"]), ("NORMAL", n.get("hi"), C["muted"]),
                    ("RECORD", r.get("hi"), (255, 120, 110))]
            for i, (lab, val, c) in enumerate(cols):
                cx = bx + bw * (0.36 + i * 0.19)
                cv.text(cx, cy - f * 0.55, lab, min(17, f * 0.4), "bold", C["muted"], anchor="ms")
                cv.text(cx, cy + f * 0.6, f"{val:.0f}°" if val is not None else "--", f * 1.05, "bold", c, anchor="ms")
            if r.get("hi_yr"):
                cv.text(bx + bw * 0.74, cy + f * 1.05, f"({r['hi_yr']})", min(17, f * 0.38), "medium", C["muted"], anchor="ms")
            if row["flag"]:
                cv.rect(bx + bw - 24 - 14, by + 10, 14, bh - 20, (*col, 255), r=7)
                cv.text(bx + bw - 50, cy, "NEAR RECORD", min(16, f * 0.36), "bold", col, anchor="rm")
    footer(cv, pkg)
    return cv


# ================================================================== FIRST FREEZE
def first_freeze(pkg, cfg):
    ac = _ex(pkg).get("acis")
    if not ac or not ac.get("freeze"):
        return None
    fz = ac["freeze"]
    today = date.fromisoformat(pkg["issued"][:10])
    season = (date(today.year, 9, 15) <= today <= date(today.year, 12, 31)) or today.month <= 1
    if fz.get("this_season"):
        season = season and (today - date.fromisoformat(fz["this_season"])).days <= 3
    if not season and not cfg.get("first_freeze_always"):
        return None
    lows = [(d["dow"], d["low"]) for d in pkg["days"][:8] if d.get("low") is not None]
    coldest = min(lows, key=lambda x: x[1]) if lows else None
    med = date.fromisoformat(fz["median"])
    days_to = (med - today).days
    cv = Canvas(cfg)
    cv.header("FIRST FREEZE", f"NORFOLK INTERNATIONAL AIRPORT  ·  32° OR COLDER  ·  {fz['years']}-YEAR HISTORY")
    x, y, w, h = area(cv)
    fmt = lambda s: (lambda d: f"{d.strftime('%b').upper()} {d.day}")(date.fromisoformat(s)) if s else "--"
    if fz.get("this_season"):
        head, sub = "FIRST FREEZE REACHED", f"{fmt(fz['this_season'])}, {date.fromisoformat(fz['this_season']).year}"
        hcol = (88, 150, 255)
    else:
        head, sub = "AVERAGE FIRST FREEZE", f"{fmt(fz['median'])}" + (f"  ·  {days_to} DAYS AWAY" if days_to > 0 else "")
        hcol = (120, 190, 240)
    big_h = h * (0.42 if not cv.tall else 0.34)
    cv.rect(x, y, w, big_h, C["panel"], r=18)
    cv.rect(x, y, 10, big_h, (*hcol, 255), r=4)
    cv.text(x + w / 2, y + big_h * 0.3, head, 30, "bold", C["muted"], anchor="mm")
    cv.text(x + w / 2, y + big_h * 0.62, sub, min(96, w * 0.08), "bold", anchor="mm", maxw=w - 80)
    if coldest:
        msg = (f"COLDEST FORECAST LOW: {coldest[1]}° ({coldest[0]})" + ("  ·  FREEZE POSSIBLE" if coldest[1] <= 34 else
                                                                          "  ·  NO FREEZE IN SIGHT"))
        cv.text(x + w / 2, y + big_h * 0.87, msg, 24, "bold", BAD if coldest[1] <= 34 else C["muted"], anchor="mm", maxw=w - 60)
    items = [("EARLIEST", fmt(fz["earliest"]), str(date.fromisoformat(fz["earliest"]).year)),
             ("LATEST", fmt(fz["latest"]), str(date.fromisoformat(fz["latest"]).year)),
             ("LAST YEAR", fmt(fz.get("last_season")), str(date.fromisoformat(fz["last_season"]).year) if fz.get("last_season") else "")]
    boxes = grid(x, y + big_h + 22, w, h - big_h - 22, 3, 1 if cv.fmt == "vertical" else 3, 20)
    for (lab, val, sub), box in zip(items, boxes):
        tile(cv, box, lab, val, sub, bar=(120, 190, 240))
    footer(cv, pkg)
    return cv


# ================================================================== COMMUTE
RATE_COL = {"GOOD": GOOD, "OK": OK_, "SLOW": WARN}


def commute(pkg, cfg):
    wins = pkg.get("commute") or []
    if not wins:
        return None
    cv = Canvas(cfg)
    cv.header("COMMUTE FORECAST", f"{pkg['location']['area']}  ·  YOUR NEXT TWO DRIVES")
    x, y, w, h = area(cv)
    for win, (bx, by, bw, bh) in zip(wins, grid(x, y, w, h, len(wins), 1 if cv.tall else len(wins), 22)):
        col = RATE_COL.get(win["rating"], NEUTRAL)
        cv.rect(bx, by, bw, bh, C["panel"], r=18)
        cv.rect(bx, by, bw, 10, (*col, 255), r=4)
        cv.text(bx + 34, by + 64, f"{win['day']} {win['label'].split()[0]}", 40 if not cv.tall else min(40, bh * 0.1), "bold",
                anchor="ls", maxw=bw * 0.62)
        cv.text(bx + 34, by + 100, win["when"], 24, "medium", C["muted"], anchor="ls")
        pill(cv, bx + bw - 30, by + 34, {"GOOD": "SMOOTH", "OK": "HEADS UP", "SLOW": "ALLOW EXTRA TIME"}[win["rating"]], col, 20, "r")
        ic = min(170, bh * 0.3, bw * 0.3)
        draw_icon(cv, win["icon"], bx + 34 + ic / 2, by + 130 + ic / 2, ic)
        tt = f"{win['temp_min']}°" if win["temp_min"] == win["temp_max"] else f"{win['temp_min']}–{win['temp_max']}°"
        cv.text(bx + 60 + ic, by + 130 + ic * 0.55, tt, min(84, ic * 0.55), "bold", anchor="ls")
        cv.text(bx + 60 + ic, by + 130 + ic * 0.55 + 42, win["cond"], 28, "medium", C["muted"], anchor="ls", maxw=bw - ic - 100)
        ny = by + 130 + ic + 30
        for note in win["notes"][:4]:
            lines = cv.wrap(note, 26, "regular", bw - 100)
            if ny + len(lines) * 34 > by + bh - 10:
                break
            cv.rect(bx + 34, ny + 6, 12, 12, (*col, 255), r=6)
            for i, ln in enumerate(lines):
                cv.text(bx + 60, ny + i * 34, ln, 26, "regular", anchor="lt")
            ny += len(lines) * 34 + 12
    footer(cv, pkg)
    return cv


# ================================================================== WEEKEND
TAG_COL = {"BEACH": (250, 205, 90), "YARD WORK": (110, 200, 110), "OUTDOOR PLANS": (88, 180, 255),
           "BOATING": (90, 210, 210), "INDOOR DAY": (176, 190, 212), "MIXED BAG": (176, 190, 212)}


def weekend(pkg, cfg):
    wk = pkg.get("weekend") or []
    if not wk:
        return None
    cv = Canvas(cfg)
    cv.header("WEEKEND PLANNER", pkg["location"]["area"])
    x, y, w, h = area(cv)
    for d, (bx, by, bw, bh) in zip(wk, grid(x, y, w, h, len(wk), 1 if cv.tall else len(wk), 22)):
        cv.rect(bx, by, bw, bh, C["panel"], r=18)
        cv.rect(bx, by, bw, 10, C["rule"], r=4)
        s = min(1.0, bh / 780)
        cv.text(bx + 34, by + 70 * s + 10, d["day"], 50 * s, "bold", anchor="ls")
        cv.text(bx + 34, by + 104 * s + 10, d["date_label"].upper(), 24 * s, "medium", C["muted"], anchor="ls")
        cv.text(bx + bw - 34, by + 78 * s + 10, f"{d['high']}° / {d['low']}°", 56 * s, "bold", anchor="rs")
        cv.text(bx + bw - 34, by + 110 * s + 10, d["cond"], 24 * s, "medium", C["muted"], anchor="rs", maxw=bw * 0.5)
        py0 = by + 140 * s + 10
        ph = bh * 0.52
        parts = d["parts"]
        for p, (qx, qy, qw, qh) in zip(parts, grid(bx + 24, py0, bw - 48, ph, len(parts), len(parts), 14)):
            cv.rect(qx, qy, qw, qh, (255, 255, 255, 14), r=12)
            cv.text(qx + qw / 2, qy + 36 * s + 4, p["label"], 22 * s, "bold", C["muted"], anchor="ms", maxw=qw - 10)
            draw_icon(cv, p["icon"], qx + qw / 2, qy + qh * 0.42, min(qw * 0.55, qh * 0.4), night=p["label"] == "EVENING")
            cv.text(qx + qw / 2, qy + qh * 0.78, f"{p['temp']}°", min(48, qh * 0.14), "bold", anchor="ms")
            if (p["pop"] or 0) >= 20:
                cv.text(qx + qw / 2, qy + qh * 0.92, f"{p['pop']}% RAIN", min(20, qh * 0.06), "bold", C["rain"], anchor="ms")
        ty = py0 + ph + 26 * s
        cv.text(bx + 34, ty, "GOOD FOR", 20 * s, "bold", C["muted"], anchor="lt")
        tx, ty2 = bx + 34, ty + 34 * s
        for tag in d["tags"]:
            tw = cv.width(tag, 22 * s, "bold") + 28
            if tx + tw > bx + bw - 30:
                tx, ty2 = bx + 34, ty2 + 50 * s
            pill(cv, tx, ty2, tag, TAG_COL.get(tag, NEUTRAL), 22 * s)
            tx += tw + 12
    footer(cv, pkg)
    return cv


# ================================================================== SUN & UV
def sun_uv(pkg, cfg):
    ex = _ex(pkg)
    sun, uv = ex.get("sun"), ex.get("uv") or []
    if not sun:
        return None
    today = datetime.fromisoformat(pkg["issued"]).date()
    uv = [u for u in uv if u["time"].date() == today]
    cv = Canvas(cfg)
    cv.header("SUN & UV", f"{pkg['location']['area']}  ·  {today.strftime('%A, %b').upper()} {today.day}")
    x, y, w, h = area(cv)
    hrs, mins = divmod(int(sun["daylight_s"] // 60), 60)
    ch = sun["change_s"]
    chg = f"{'+' if ch >= 0 else '−'}{int(abs(ch) // 60)}m {int(abs(ch) % 60)}s vs yesterday"
    tiles_ = [("SUNRISE", _t(sun["sunrise"]), f"Golden hour until {_t(sun['golden_am'][1])}", (250, 190, 80)),
              ("SUNSET", _t(sun["sunset"]), f"Golden hour from {_t(sun['golden_pm'][0])}", (245, 130, 70)),
              ("DAYLIGHT", f"{hrs}h {mins}m", chg, (120, 190, 240))]
    pk = max(uv, key=lambda u: u["uv"]) if uv else None
    if pk:
        cat, ucol = X.uv_category(pk["uv"])
        burn = {"LOW": "Minimal protection needed", "MODERATE": "Sunscreen midday", "HIGH": "Sunscreen, hat, shade 10-4",
                "VERY HIGH": "Burns in ~15 min: cover up", "EXTREME": "Burns in <10 min: avoid midday sun"}[cat]
        tiles_.append((f"PEAK UV  ·  {_t(pk['time']).replace(':00', '')}", f"{pk['uv']} {cat}", burn, ucol))
    th = h * (0.45 if not cv.tall else 0.5)
    for (lab, val, sub, col), box in zip(tiles_, grid(x, y, w, th, len(tiles_), 2 if cv.tall else len(tiles_), 20)):
        tile(cv, box, lab, val, sub, bar=col, vsize=min(64, box[3] * 0.3, box[2] * 0.15))
    cy = y + th + 22
    cx0, cw_, chh = x, w, h - th - 22
    cv.rect(cx0, cy, cw_, chh, C["panel"], r=16)
    cv.text(cx0 + 26, cy + 22, "UV INDEX BY HOUR", 20, "bold", C["muted"], anchor="lt")
    if uv:
        uvs = [u for u in uv if 6 <= u["time"].hour <= 20]
        n = len(uvs)
        slot = (cw_ - 60) / max(1, n)
        top, bot = cy + 70, cy + chh - 50
        vmax = max(11, max(u["uv"] for u in uvs))
        for i, u in enumerate(uvs):
            bxx = cx0 + 30 + i * slot
            bh_ = (bot - top) * u["uv"] / vmax
            _, col = X.uv_category(u["uv"])
            if u["uv"] > 0:
                cv.rect(bxx + slot * 0.15, bot - bh_, slot * 0.7, bh_, (*col, 255), r=6)
                cv.text(bxx + slot / 2, bot - bh_ - 10, str(u["uv"]), min(24, slot * 0.4), "bold", anchor="ms")
            if i % (2 if slot < 60 else 1) == 0:
                cv.text(bxx + slot / 2, bot + 32, u["time"].strftime("%I%p").lstrip("0"), min(18, slot * 0.3), "bold",
                        C["muted"], anchor="ms")
    else:
        cv.text(cx0 + 26, cy + 80, "UV forecast unavailable.", 24, "regular", C["muted"], anchor="lt")
    footer(cv, pkg)
    return cv


# ================================================================== TROPICS
_land = None


def _atlantic():
    global _land
    if _land is None:
        _land = json.loads((Path(__file__).parent / "data" / "atlantic_land.json").read_text())
    return _land


RISK_COL = lambda p: (250, 220, 70) if (p or 0) < 40 else (250, 150, 40) if (p or 0) <= 60 else (230, 50, 50)
CLASS_NAME = {"HU": "HURRICANE", "TS": "TROPICAL STORM", "TD": "TROPICAL DEPRESSION", "STS": "SUBTROPICAL STORM",
              "SD": "SUBTROPICAL DEPRESSION", "PTC": "POTENTIAL TROPICAL CYCLONE", "PC": "POST-TROPICAL", "TY": "TYPHOON"}


def _cat(kt):
    if not kt:
        return ""
    for c, lim in ((5, 137), (4, 113), (3, 96), (2, 83), (1, 64)):
        if kt >= lim:
            return f"CAT {c}"
    return ""


def _trop_map(cv, box, tr, cfg):
    x, y, w, h = box
    W_, H_ = z(w), z(h)
    lay = Image.new("RGBA", (W_, H_), (17, 27, 47, 255))
    d = ImageDraw.Draw(lay, "RGBA")
    vw, ve, vs, vn = cfg.get("tropics_view") or (-100, -12, 6, 46)
    cx, cy = (vw + ve) / 2, (vs + vn) / 2
    k = math.cos(math.radians(cy))
    span_y = max(vn - vs, (ve - vw) * k * h / w)
    span_x = span_y * w / h / k
    w0, e0, s0, n0 = cx - span_x / 2, cx + span_x / 2, cy - span_y / 2, cy + span_y / 2
    P = lambda lo, la: ((lo - w0) / (e0 - w0) * W_, (n0 - la) / (n0 - s0) * H_)
    data = _atlantic()
    for c in data["countries"]:
        for p in c["polys"]:
            d.polygon([P(a, b) for a, b in p[0]], fill=(38, 55, 84, 255), outline=(98, 120, 152, 255))
    for ln in data.get("state_lines", []):
        d.line([P(a, b) for a, b in ln], fill=(98, 120, 152, 160), width=max(1, z(0.8)))
    ov = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for a in tr.get("areas", []):
        col = RISK_COL(a.get("chance7"))
        for p in a["polys"]:
            od.polygon([P(*pt[:2]) for pt in p[0]], fill=(*col, 110), outline=(*col, 255))
    for cne in tr.get("cones", []):
        for p in cne["polys"]:
            od.polygon([P(*pt[:2]) for pt in p[0]], fill=(255, 255, 255, 60), outline=(255, 255, 255, 220))
    lay.alpha_composite(ov)
    d = ImageDraw.Draw(lay, "RGBA")
    f = font("bold", 22)
    for a in tr.get("areas", []):
        pts = [pt for p in a["polys"] for pt in p[0]]
        ax = sum(p[0] for p in pts) / len(pts)
        ay = sum(p[1] for p in pts) / len(pts)
        px, py = P(ax, ay)
        r = z(12)
        col = RISK_COL(a.get("chance7"))
        d.line([(px - r, py - r), (px + r, py + r)], fill=(*col, 255), width=z(4))
        d.line([(px - r, py + r), (px + r, py - r)], fill=(*col, 255), width=z(4))
        d.text((px, py - z(18)), f"{a.get('chance7') or '?'}%", font=f, fill=(255, 255, 255, 255), anchor="ms",
               stroke_width=z(3), stroke_fill=(13, 21, 38, 255))
    for s in tr.get("storms", []):
        if s.get("lat") is None:
            continue
        px, py = P(s["lon"], s["lat"])
        from . import stormicons
        stormicons.draw_storm(d, px, py, z(54), s.get("wind_kt"), s.get("class"))  # L / open swirl / filled + category
        d.text((px + z(32), py), (s.get("name") or "").upper(), font=font("bold", 24), fill=(255, 255, 255, 255),
               anchor="lm", stroke_width=z(3), stroke_fill=(13, 21, 38, 255))
    lx, ly = P(cfg["location"]["lon"], cfg["location"]["lat"])
    d.regular_polygon((lx, ly, z(9)), 4, rotation=45, fill=(255, 255, 255, 255))
    d.text((lx - z(14), ly), "NORFOLK", font=font("bold", 17), fill=(255, 255, 255, 255), anchor="rm",
           stroke_width=z(3), stroke_fill=(13, 21, 38, 255))
    from .alertmap import _paste_rounded
    _paste_rounded(cv, lay, x, y)
    cv.d.rounded_rectangle([z(x), z(y), z(x + w), z(y + h)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))


def tropics(pkg, cfg):
    tr = _ex(pkg).get("tropics")
    if tr is None:
        return None
    today = date.fromisoformat(pkg["issued"][:10])
    in_season = date(today.year, 6, 1) <= today <= date(today.year, 11, 30)
    if not in_season and not tr.get("storms") and not tr.get("areas") and not cfg.get("tropics_always"):
        return None
    cv = Canvas(cfg)
    cv.header("TROPICAL OUTLOOK", "ATLANTIC BASIN  ·  NEXT 7 DAYS")
    (mx, my, mw, mh), (px, py, pw, ph) = cv.split()
    _trop_map(cv, (mx, my, mw, mh), tr, cfg)
    cv.rect(px, py, pw, ph, C["panel"], r=18)
    cy = py + 24
    storms, areas = tr.get("storms") or [], tr.get("areas") or []
    small = ph < 700
    cv.text(px + 26, cy, "ACTIVE STORMS", 20, "bold", C["muted"], anchor="lt")
    cy += 36
    if not storms:
        cv.text(px + 26, cy, "None", 26, "regular", anchor="lt")
        cy += 50
    for s in storms[:3]:
        col = (230, 60, 60) if s.get("class") == "HU" else (250, 190, 50) if s.get("class") in ("TS", "STS") else (90, 170, 255)
        cv.rect(px + 26, cy, 8, 86 if not small else 70, (*col, 255), r=3)
        nm = f"{CLASS_NAME.get(s.get('class'), s.get('class') or '')} {(s.get('name') or '').upper()}"
        cv.text(px + 48, cy + 2, nm, 28 if not small else 24, "bold", anchor="lt", maxw=pw - 90)
        mph = round((s.get("wind_kt") or 0) * 1.15078 / 5) * 5
        det = f"{mph} mph {_cat(s.get('wind_kt'))}".strip() + (f"  ·  moving {s['move']} {s['move_mph']} mph" if s.get("move") else "")
        cv.text(px + 48, cy + (46 if not small else 38), det, 22 if not small else 19, "medium", C["muted"], anchor="lt", maxw=pw - 90)
        cy += (104 if not small else 84)
    cv.line([(px + 26, cy), (px + pw - 26, cy)], (255, 255, 255, 60), 1.5)
    cy += 18
    cv.text(px + 26, cy, "AREAS TO WATCH", 20, "bold", C["muted"], anchor="lt")
    cy += 36
    if not areas:
        cv.paragraph(px + 26, cy, "No new development expected in the next 7 days.", 24, "regular", pw - 52, max_lines=2)
    for i, a in enumerate(areas[:4]):
        if cy + 60 > py + ph - 10:
            break
        col = RISK_COL(a.get("chance7"))
        cv.rect(px + 26, cy + 4, 22, 22, (*col, 255), r=4)
        risk = "LOW" if (a.get("chance7") or 0) < 40 else "MEDIUM" if (a.get("chance7") or 0) <= 60 else "HIGH"  # NHC bins
        cv.text(px + 60, cy + 16, f"{risk} CHANCE", 24 if not small else 21, "bold", anchor="lm")
        cv.text(px + pw - 26, cy + 16, f"2-DAY {a.get('chance2') if a.get('chance2') is not None else '--'}%   7-DAY "
                                       f"{a.get('chance7') if a.get('chance7') is not None else '--'}%",
                22 if not small else 19, "bold", C["muted"], anchor="rm")
        cy += 50 if not small else 42
    footer(cv, pkg)
    return cv


# ================================================================== WARNING COUNTER
WARN_COLORS = {"Tornado Warning": (255, 40, 40), "Severe Thunderstorm Warning": (255, 165, 0),
               "Flash Flood Warning": (139, 0, 0), "Special Marine Warning": (255, 165, 0)}
WARN_SHORT = {"Tornado Warning": "TORNADO", "Severe Thunderstorm Warning": "SEVERE T-STORM",
              "Flash Flood Warning": "FLASH FLOOD", "Special Marine Warning": "SPECIAL MARINE"}


def warning_count(pkg, cfg):
    wc = _ex(pkg).get("warn_counts")
    if not wc:
        return None
    if not any(wc["state"].values()) and not cfg.get("warning_count_always"):
        return None
    today = datetime.fromisoformat(pkg["issued"]).date()
    cv = Canvas(cfg)
    cv.header("TODAY'S WARNINGS", f"ISSUED SINCE MIDNIGHT  ·  {today.strftime('%A, %b').upper()} {today.day}")
    x, y, w, h = area(cv)
    cols = [("HAMPTON ROADS", wc["area"]), ("VIRGINIA", wc["state"])]
    evs = [e for e in X.WARN_EVENTS if e != "Special Marine Warning" or cfg.get("count_marine", True)]
    for (title, cnt), (bx, by, bw, bh) in zip(cols, grid(x, y, w, h, 2, 1 if cv.tall else 2, 24)):
        cv.rect(bx, by, bw, bh, C["panel"], r=18)
        cv.text(bx + bw / 2, by + 50, title, 34, "bold", anchor="ms")
        tot = sum(cnt[e] for e in evs)
        cv.text(bx + bw / 2, by + 84, f"{tot} TOTAL", 22, "bold", C["muted"], anchor="ms")
        rows = grid(bx + 24, by + 110, bw - 48, bh - 130, len(evs), 1 if not cv.tall else 2, 12)
        for e, (rx, ry, rw, rh) in zip(evs, rows):
            col = WARN_COLORS[e]
            cv.accent_row(rx, ry, rw, rh, bar=col)
            cv.text(rx + 30, ry + rh / 2, WARN_SHORT[e], min(28, rh * 0.26), "bold", anchor="lm", maxw=rw * 0.65)
            cv.text(rx + rw - 30, ry + rh / 2, str(cnt[e]), min(74, rh * 0.62), "bold", col if _lum(col) > 60 else C["text"],
                    anchor="rm")
    footer(cv, pkg)
    return cv


# ================================================================== AVIATION
def aviation(pkg, cfg):
    av = _ex(pkg).get("aviation")
    if not av or not av.get("metar"):
        return None
    m, taf = av["metar"], av.get("taf") or {}
    cv = Canvas(cfg)
    cv.header(f"{av['icao'][1:]} AVIATION WEATHER", f"NORFOLK INTERNATIONAL  ·  METAR {_t(m['time'])}" if m.get("time") else "")
    x, y, w, h = area(cv)
    col = X.FLT_COLORS[m["cat"]]
    cat_full = {"VFR": "VISUAL FLIGHT RULES", "MVFR": "MARGINAL VFR", "IFR": "INSTRUMENT FLIGHT RULES", "LIFR": "LOW IFR"}[m["cat"]]
    temp = f"{m['temp']:.0f}°C / {m['temp'] * 9 / 5 + 32:.0f}°F" if m.get("temp") is not None else "--"
    ceil = f"{m['ceiling']:,} ft" if m.get("ceiling") else "None"
    vis = f"{m['vis']:g}{'+' if (m['vis'] or 0) >= 10 else ''} SM" if m.get("vis") is not None else "--"
    tiles_ = [("WIND", m["wind"]), ("VISIBILITY", vis), ("CEILING", ceil), ("SKY", m["sky"]),
              ("TEMP / DEW", f"{temp.split(' / ')[0]} / {m['dewp']:.0f}°C" if m.get("dewp") is not None else temp),
              ("ALTIMETER", f"{m['altim']:.2f} inHg" if isinstance(m.get("altim"), (int, float)) else "--")]
    if cv.tall:
        bh = 190 if cv.fmt == "vertical" else 150
        badge = (x, y, w, bh)
        tbox = (x, y + bh + 18, w, h * (0.42 if cv.fmt == "vertical" else 0.4))
        tafbox = (x, tbox[1] + tbox[3] + 18, w, y + h - (tbox[1] + tbox[3] + 18))
    else:
        badge = (x, y, 520, 330)
        tbox = (x + 540, y, w - 540, 330)
        tafbox = (x, y + 350, w, h - 350)
    bx, by, bw, bh_ = badge
    cv.rect(bx, by, bw, bh_, (*col, 255), r=18)
    cv.text(bx + bw / 2, by + bh_ * 0.46, m["cat"], min(120, bh_ * 0.5), "bold", _ink(col), anchor="mm")
    cv.text(bx + bw / 2, by + bh_ * 0.8, cat_full, min(26, bh_ * 0.13), "bold", _ink(col), anchor="mm")
    for (lab, val), box in zip(tiles_, grid(*tbox, 6, 3 if not cv.tall else 2, 14)):
        tile(cv, box, lab, val, vsize=min(38, box[3] * 0.3, box[2] * 0.11))
    tx, ty, tw, th = tafbox
    cv.rect(tx, ty, tw, th, C["panel"], r=16)
    cv.text(tx + 26, ty + 22, "TAF: NEXT 24 HOURS", 20, "bold", C["muted"], anchor="lt")
    raw = m.get("raw") or ""
    per = (taf.get("periods") or [])[:6]
    if per:
        area_y, area_h = ty + 60, th - 60 - (70 if not cv.tall else 64)
        boxes = grid(tx + 24, area_y, tw - 48, area_h, len(per), len(per) if not cv.tall else 1, 10)
        for p, (px, py, pw, ph) in zip(per, boxes):
            c = X.FLT_COLORS[p["cat"]]
            cv.rect(px, py, pw, ph, (*c, 60), r=12)
            cv.rect(px, py, pw if not cv.tall else 10, 10 if not cv.tall else ph, (*c, 255), r=4)
            when = f"{p['from'].strftime('%a').upper()} {_t(p['from']).replace(':00', '')}"
            if not cv.tall:
                cv.text(px + 16, py + 44, when, 20, "bold", anchor="ls", maxw=pw - 24)
                cv.text(px + 16, py + 92, p["cat"], 40, "bold", c, anchor="ls")
                lines = [p["wind"], (f"{p['vis']:g}{'+' if (p['vis'] or 0) >= 6 else ''} SM" if p.get("vis") is not None else ""),
                         (f"Ceiling {p['ceiling']:,}" if p.get("ceiling") else "No ceiling"), p["wx"]]
                yy = py + 130
                for ln in [l for l in lines if l]:
                    cv.text(px + 16, yy, ln, 19, "medium", C["muted"], anchor="ls", maxw=pw - 24)
                    yy += 30
            else:
                f = min(24, ph * 0.3)
                cv.text(px + 26, py + ph / 2, when, f, "bold", anchor="lm", maxw=pw * 0.26)
                cv.text(px + pw * 0.3, py + ph / 2, p["cat"], f * 1.3, "bold", c, anchor="lm")
                det = ", ".join(l for l in [p["wind"], f"{p['vis']:g} SM" if p.get("vis") is not None else "",
                                            f"cig {p['ceiling']:,}" if p.get("ceiling") else "", p["wx"]] if l)
                cv.text(px + pw * 0.47, py + ph / 2, det, f * 0.8, "medium", C["muted"], anchor="lm", maxw=pw * 0.51)
    cv.text(tx + 26, ty + th - 26, raw, 18 if not cv.tall else 15, "medium", C["muted"], anchor="ls", maxw=tw - 52)
    footer(cv, pkg)
    return cv


# ================================================================== BE WEATHER AWARE
def aware_info(pkg, cfg):
    """Pick the single biggest weather concern for the day. Returns a JSON-friendly dict or None."""
    from . import alertinfo, outlooks
    cands = []
    target = pkg["days"][pkg["today"]["day_index"]] if pkg.get("days") else {}
    when_day = "TOMORROW" if pkg.get("evening_mode") else "TODAY"
    timing = (target.get("day_timing") or "").replace("mainly in the ", "").upper()
    # 1. active alerts for the home area
    for a in pkg.get("alerts") or []:
        if not a.get("affects_home", True):
            continue
        ev = a["event"]
        rank = 100 if "Warning" in ev else 80 if "Watch" in ev else 55 if "Advisory" in ev else 40
        rank += 10 if ev.startswith(("Tornado", "Hurricane", "Extreme", "Flash Flood Emergency")) else 0
        det = [f"{r['label'].title()}: {r['text']}" for r in (a.get("summary") or []) if r["label"] in ("WHAT", "IMPACTS")][:2]
        act = next((r["text"] for r in a.get("summary") or [] if r["label"] == "ACTION"), "")
        cands.append((rank, {"title": ev.upper(), "when": a.get("ends_label", "").upper(), "details": det, "action": act,
                             "color": a.get("color", "#E8303A"), "icon": "alert"}))
    # 2. SPC severe risk at home
    so = (pkg.get("spc_outlook") or {}).get("2" if pkg.get("evening_mode") else "1") or {}
    lvl = next((c[0] for c in outlooks.SPC_CATS if c[1] == so.get("category")), 0)
    if lvl >= 1:
        hz = [h for h in so.get("hazards") or [] if h["label"] != "LIGHTNING" and h["level"] not in ("NOT EXPECTED",)][:3]
        col = next(c[3] for c in outlooks.SPC_CATS if c[0] == lvl)
        cands.append((45 + lvl * 8, {"title": "SEVERE STORMS POSSIBLE", "when": f"{when_day} {timing}".strip(),
                                     "details": [f"{so.get('headline', '').title()}: {so.get('meaning', '')}"] +
                                                [f"{h['label'].title()}: {h['text']}" for h in hz],
                                     "action": "Have a way to get warnings and know where you'd shelter.",
                                     "color": col, "icon": "tstorm"}))
    # 3. flash flooding (ERO) at home
    ero = ((pkg.get("_outlooks") or {}).get("ero") or {}).get(2 if pkg.get("evening_mode") else 1) or []
    loc = cfg["location"]
    home = max([f["level"] for f in ero if outlooks.contains(f["polys"], loc["lon"], loc["lat"])], default=0)
    if home >= 2:
        c = next(c for c in outlooks.ERO_CATS if c[0] == home)
        cands.append((50 + home * 8, {"title": "FLASH FLOODING POSSIBLE", "when": f"{when_day} {timing}".strip(),
                                      "details": [f"{c[2]} Risk ({c[0]} of 4): {c[4]}",
                                                  f"Rain totals: {target.get('qpf', 0) or 0:.2f}\" forecast at Norfolk."],
                                      "action": "Turn around, don't drown. Avoid flooded underpasses and roads.",
                                      "color": c[3], "icon": "rain"}))
    # 4. forecast hazards
    hi, gust, low = target.get("max_hi") or 0, target.get("max_gust") or 0, target.get("low")
    if hi >= 100:
        cands.append((60 if hi >= 105 else 42, {"title": "DANGEROUS HEAT" if hi >= 105 else "HEAT & HUMIDITY",
                                                "when": f"{when_day} AFTERNOON", "details": [
                f"Heat index up to {hi}°.", f"High near {target.get('high')}° with dewpoints in the {(target.get('max_dew') or 70) // 10 * 10}s."],
                "action": "Hydrate, take breaks in the shade or A/C, never leave kids or pets in cars.",
                "color": "#FF7F50" if hi < 105 else "#C71585", "icon": "heat"}))
    if gust >= 40:
        cands.append((48, {"title": "STRONG WINDS", "when": when_day, "details": [
            f"Gusts up to {gust} mph.", "Tree limbs and power lines could come down; bridges may see restrictions."],
            "action": "Secure outdoor items. Use caution on the HRBT, MMMBT and CBBT.", "color": "#DAA520", "icon": "wind"}))
    wc = target.get("min_wc")
    if wc is not None and wc <= 10:
        cands.append((45, {"title": "BITTER COLD", "when": when_day, "details": [f"Wind chills as low as {wc}°."],
                           "action": "Dress in layers; bring pets inside; protect pipes.", "color": "#5F9EA0", "icon": "cold"}))
    if (target.get("snow") or 0) >= 0.5:
        cands.append((58, {"title": "SNOW", "when": when_day, "details": [f"Around {target['snow']:.1f}\" possible at Norfolk."],
                           "action": "Slow down and leave extra room on untreated roads and bridges.", "color": "#7B68EE",
                           "icon": "snow"}))
    if low is not None and low <= 32:
        cands.append((35, {"title": "FREEZE", "when": f"{when_day} NIGHT", "details": [f"Low near {low}°."],
                           "action": "Protect plants, pets and exposed pipes.", "color": "#483D8B", "icon": "cold"}))
    if "Fog" in (target.get("cond") or ""):
        cands.append((30, {"title": "DENSE FOG", "when": f"{when_day} MORNING", "details": [target.get("cond")],
                           "action": "Use low beams and leave extra following distance.", "color": "#708090", "icon": "fog"}))
    ex = pkg.get("_extras") or {}
    td = ex.get("tides")
    if td and td.get("peak"):
        cat = X.flood_category(td["peak"][1], td["stages"])
        if cat in ("minor", "moderate", "major"):
            words, _, meaning = FLOOD_WORDS[cat]
            cands.append(({"minor": 44, "moderate": 62, "major": 85}[cat],
                          {"title": words, "when": f"NEAR HIGH TIDE {td['peak'][0].strftime('%a').upper()} {_t(td['peak'][0])}",
                           "details": [f"Sewells Point peaks near {td['peak'][1]:.1f} ft MLLW.", meaning],
                           "action": "Don't drive through flooded roads. Move cars from low-lying lots.",
                           "color": "#228B22", "icon": "tide"}))
    srf = ((ex.get("beach") or {}).get("srf") or {})
    if any((v.get("rip") == "High") for v in srf.values()):
        where = ", ".join(k for k, v in srf.items() if v.get("rip") == "High")
        cands.append((34, {"title": "DANGEROUS RIP CURRENTS", "when": when_day, "details": [f"High rip current risk: {where}."],
                           "action": "Swim near a lifeguard. If caught, swim parallel to shore.", "color": "#40E0D0",
                           "icon": "wave"}))
    if (target.get("qpf") or 0) >= 1 and target.get("qpf_src") == "ndfd":
        cands.append((33, {"title": "HEAVY RAIN", "when": f"{when_day} {timing}".strip(),
                           "details": [f"Around {target['qpf']:.2f}\" of rain forecast at Norfolk."],
                           "action": "Expect ponding on roads; allow extra travel time.", "color": "#1E90FF", "icon": "rain"}))
    if not cands:
        return None
    cands.sort(key=lambda c: -c[0])
    top = cands[0][1]
    top["also"] = [c[1]["title"] for c in cands[1:3]]
    return top


def _aware_symbol(cv, cx, cy, s, col):
    """Big rounded warning triangle with '!'."""
    pts = [(cx, cy - s * 0.58), (cx + s * 0.62, cy + s * 0.48), (cx - s * 0.62, cy + s * 0.48)]
    cv.d.polygon([(z(a), z(b)) for a, b in pts], fill=(*col, 255))
    cv.d.line([(z(a), z(b)) for a, b in pts + [pts[0]]], fill=(255, 255, 255, 255), width=z(s * 0.05), joint="curve")
    ink = _ink(col)
    cv.rect(cx - s * 0.055, cy - s * 0.24, s * 0.11, s * 0.42, (*ink, 255), r=s * 0.05)
    cv.rect(cx - s * 0.065, cy + s * 0.25, s * 0.13, s * 0.13, (*ink, 255), r=s * 0.065)


def weather_aware(pkg, cfg):
    info = pkg.get("weather_aware")
    if not info:
        return None
    from . import alertinfo
    col = alertinfo.hex_rgb(info.get("color", "#E8303A")) if isinstance(info.get("color"), str) else tuple(info["color"])
    cv = Canvas(cfg)
    day = datetime.fromisoformat(pkg["issued"])
    cv.header("BE WEATHER AWARE", f"{pkg['location']['area']}  ·  {day.strftime('%A, %b').upper()} {day.day}",
              rule_color=col)
    x, y, w, h = area(cv)
    if cv.tall:
        bh = h * (0.36 if cv.fmt == "vertical" else 0.34)
        ban, det = (x, y, w, bh), (x, y + bh + 20, w, h - bh - 20)
    else:
        ban, det = (x, y, 700, h), (x + 724, y, w - 724, h)
    bx, by, bw, bh_ = ban
    cv.rect(bx, by, bw, bh_, C["panel"], r=20)
    cv.rect(bx, by, bw, 12, (*col, 255), r=4)
    if cv.tall:
        s = min(bh_ * 0.62, 300)
        _aware_symbol(cv, bx + 40 + s * 0.62, by + bh_ / 2 + 10, s, col)
        tx, tw = bx + 80 + s * 1.24, bw - (120 + s * 1.24)
        cv.paragraph(tx, by + 30, info["title"], 58 if cv.fmt == "vertical" else 48, "bold", tw, max_lines=3, lh=1.05,
                     valign="middle", box_h=bh_ * 0.7)
        cv.text(tx, by + bh_ - 36, info.get("when", ""), 24, "bold", col if _lum(col) > 70 else C["muted"], anchor="ls", maxw=tw)
    else:
        s = 330
        _aware_symbol(cv, bx + bw / 2, by + 230, s, col)
        cv.paragraph(bx + bw / 2, by + 440, info["title"], 60, "bold", bw - 70, max_lines=3, anchor="ma", lh=1.05)
        cv.text(bx + bw / 2, by + bh_ - 44, info.get("when", ""), 28, "bold", col if _lum(col) > 70 else C["muted"],
                anchor="ms", maxw=bw - 60)
    dx, dy, dw, dh = det
    cv.rect(dx, dy, dw, dh, C["panel"], r=20)
    cy = dy + 30
    cv.text(dx + 30, cy, "WHAT TO KNOW", 22, "bold", C["muted"], anchor="lt")
    cy += 44
    items = [d for d in info.get("details") or [] if d][:4]
    act = info.get("action")
    also = info.get("also") or []
    avail = dy + dh - cy - (150 if act else 20) - (60 if also else 0)
    for size in range(34, 18, -1):
        need = sum(len(cv.wrap(d, size, "regular", dw - 110)) * size * 1.28 + 22 for d in items)
        if need <= avail:
            break
    for d in items:
        lines = cv.wrap(d, size, "regular", dw - 110)
        cv.rect(dx + 34, cy + size * 0.35, 14, 14, (*col, 255), r=7)
        for i, ln in enumerate(lines):
            cv.text(dx + 66, cy + i * size * 1.28, ln, size, "regular", anchor="lt")
        cy += len(lines) * size * 1.28 + 22
    if act:
        ay = dy + dh - 140 - (60 if also else 0)
        cv.rect(dx + 24, ay, dw - 48, 116, (*col, 45), r=14)
        cv.rect(dx + 24, ay, 10, 116, (*col, 255), r=4)
        cv.text(dx + 54, ay + 16, "WHAT TO DO", 18, "bold", C["muted"], anchor="lt")
        cv.paragraph(dx + 54, ay + 44, act, 26, "medium", dw - 110, max_lines=2, lh=1.2)
    if also:
        cv.text(dx + 30, dy + dh - 34, "ALSO: " + "  ·  ".join(also), 20, "bold", C["muted"], anchor="ls", maxw=dw - 60)
    footer(cv, pkg)
    return cv


# ================================================================== AIR QUALITY
def _aq_short(cat):
    return {"Unhealthy for Sensitive Groups": "UNHEALTHY (SENSITIVE)"}.get(cat, cat.upper())


def _aq_scale(cv, x, y, w, h):
    segs = [(0, 50), (51, 100), (101, 150), (151, 200), (201, 300), (301, 500)]
    sw = w / len(segs)
    for i, ((a, b), c) in enumerate(zip(segs, X.AQI_CATS)):
        cv.rect(x + i * sw, y, sw - 4, h, (*c[2], 255), r=6)
        lab = {"Unhealthy for Sensitive Groups": "SENSITIVE"}.get(c[1], c[1].upper())
        fs = min(17, h * 0.42)
        cv.text(x + i * sw + (sw - 4) / 2, y + h / 2, f"{lab} {a}-{b}" if sw > 200 else lab, fs, "bold",
                _ink(c[2]), anchor="mm", maxw=sw - 14)


def air_quality(pkg, cfg):
    aq = _ex(pkg).get("aqi")
    if not aq or not (aq.get("current") or aq.get("days")):
        return None
    tz = _tz(cfg)
    now = datetime.fromisoformat(pkg["issued"]).astimezone(tz)
    cv = Canvas(cfg)
    where = (aq.get("area") or pkg["location"]["area"]).upper()
    cv.header("AIR QUALITY", f"{where}  ·  CURRENT AQI & FORECAST")
    x, y, w, h = area(cv)
    scale_h = 44
    h -= scale_h + 18
    _aq_scale(cv, x, y + h + 18, w, scale_h)
    cur = aq.get("current")
    days = aq.get("days") or []
    if not cv.tall:
        cbox = (x, y, w * 0.36, h)
        fx, fy, fw, fh = x + w * 0.36 + 22, y, w * 0.64 - 22, h
    else:
        ch = h * (0.21 if cv.fmt == "vertical" else 0.36)
        cbox = (x, y, w, ch)
        fx, fy, fw, fh = x, y + ch + 20, w, h - ch - 20
    # ---- current
    bx, by, bw, bh = cbox
    cv.rect(bx, by, bw, bh, C["panel"], r=18)
    if cur and cur.get("aqi") is not None:
        c = X.aqi_cat(cur["aqi"])
        tlabel = ""
        if cur.get("time"):
            try:
                tlabel = datetime.strptime(cur["time"], "%H:%M").strftime("%I %p").lstrip("0")
            except ValueError:
                tlabel = cur["time"]
        cv.text(bx + 28, by + 26, "RIGHT NOW" + (f"  ·  {tlabel}" if tlabel else ""), 22, "bold", C["muted"], anchor="lt")
        r_ = min(bw * 0.24, bh * (0.2 if cv.tall else 0.17))
        cx_, cy_ = (bx + 28 + r_, by + 70 + r_) if cv.tall else (bx + bw / 2, by + bh * 0.13 + r_)
        cv.d.ellipse([z(cx_ - r_), z(cy_ - r_), z(cx_ + r_), z(cy_ + r_)], fill=(*c[2], 255))
        cv.text(cx_, cy_ + r_ * 0.04, str(cur["aqi"]), r_ * 0.95, "bold", _ink(c[2]), anchor="mm")
        if cv.tall:
            tx, ty, tw = cx_ + r_ + 34, by + 78, bw - (cx_ + r_ + 34 - bx) - 28
            ty = cy_ - 50
            pill(cv, tx, ty, _aq_short(c[1]), c[2], 24)
            cv.text(tx, ty + 66, f"MAIN POLLUTANT: {cur.get('param', '').upper()}", 22, "bold", C["muted"], anchor="lt", maxw=tw)
            cv.paragraph(tx, ty + 104, c[3], 23, "regular", tw, max_lines=4)
        else:
            ty = cy_ + r_ + 30
            w_ = cv.width(_aq_short(c[1]), 24, "bold") + 28
            pill(cv, bx + bw / 2 - w_ / 2, ty, _aq_short(c[1]), c[2], 24)
            cv.text(bx + bw / 2, ty + 72, f"MAIN POLLUTANT: {cur.get('param', '').upper()}", 21, "bold", C["muted"],
                    anchor="ms", maxw=bw - 40)
            cv.paragraph(bx + 28, ty + 98, c[3], 24, "regular", bw - 56, max_lines=4)
        if cur.get("source") == "model":
            cv.text(bx + bw - 24, by + 28, "MODEL ESTIMATE", 15, "bold", C["muted"], anchor="rt")
    else:
        cv.text(bx + 28, by + 26, "RIGHT NOW", 22, "bold", C["muted"], anchor="lt")
        cv.text(bx + 28, by + 80, "Current reading unavailable.", 26, "regular", C["muted"], anchor="lt")
    # ---- forecast
    disc = aq.get("discussion") or ""
    disc_h = 0
    if disc and not (cv.tall and cv.fmt == "post"):
        disc_h = 120 if not cv.tall else 130
    n = max(1, len(days))
    if cv.tall:
        boxes = [(fx, fy + i * ((fh - disc_h) / n), fw, (fh - disc_h) / n - 12) for i in range(n)]
    else:
        boxes = grid(fx, fy, fw, fh - disc_h, n, n, 16)
    model_used = False
    for d, (dx, dy, dw, dh) in zip(days, boxes):
        dd = date.fromisoformat(d["date"])
        name = "TODAY" if dd == now.date() else "TOMORROW" if dd == now.date() + timedelta(days=1) and cv.tall else dd.strftime("%a").upper()
        c = X.aqi_cat(d.get("aqi"), None if d.get("aqi") is not None else d.get("cat")) or (0, d.get("cat") or "--", NEUTRAL, "")
        val = str(d["aqi"]) if d.get("aqi") is not None else "--"
        model_used |= d.get("source") == "model"
        cv.rect(dx, dy, dw, dh, C["panel"], r=16)
        if not cv.tall:
            cv.rect(dx, dy, dw, 12, (*c[2], 255), r=6)
            cv.text(dx + dw / 2, dy + 52, name, 26, "bold", anchor="ms")
            cv.text(dx + dw / 2, dy + 76, f"{dd.strftime('%b').upper()} {dd.day}", 18, "bold", C["muted"], anchor="ms")
            vs = min(96, dw * 0.42)
            if val == "--":  # official forecast gives a category but no number
                lines = cv.wrap(_aq_short(c[1]), 30, "bold", dw - 24)
                for i, ln in enumerate(lines[:3]):
                    cv.text(dx + dw / 2, dy + dh * 0.5 + i * 36, ln, 30, "bold", c[2] if _lum(c[2]) > 60 else C["text"], anchor="ms")
                lines = []
            else:
                cv.text(dx + dw / 2, dy + dh * 0.5 + vs * 0.35, val, vs, "bold", c[2] if _lum(c[2]) > 60 else C["text"], anchor="ms")
                lines = cv.wrap(_aq_short(c[1]), 19, "bold", dw - 20)
            for i, ln in enumerate(lines[:2]):
                cv.text(dx + dw / 2, dy + dh * 0.5 + vs * 0.35 + 40 + i * 24, ln, 19, "bold", anchor="ms")
            cv.text(dx + dw / 2, dy + dh - 46, (d.get("param") or "").upper(), 18, "bold", C["muted"], anchor="ms")
            if d.get("action"):
                cv.text(dx + dw / 2, dy + dh - 20, "ACTION DAY", 16, "bold", BAD, anchor="ms")
            elif d.get("source") == "model":
                cv.text(dx + dw / 2, dy + dh - 20, "MODEL*", 15, "bold", C["muted"], anchor="ms")
        else:
            cv.rect(dx, dy, 10, dh, (*c[2], 255), r=4)
            fs = min(30, dh * 0.34)
            cv.text(dx + 30, dy + dh / 2, name, fs, "bold", anchor="lm", maxw=dw * 0.3)
            if val != "--":
                cv.text(dx + dw * 0.33, dy + dh / 2, val, fs * 1.4, "bold", anchor="lm")
            pill(cv, dx + dw - 22, dy + dh / 2 - fs * 0.55, _aq_short(c[1]) + ("*" if d.get("source") == "model" else ""),
                 c[2], min(20, fs * 0.6), anchor="r")
    if disc_h:
        dy = fy + fh - disc_h + 8
        cv.rect(fx, dy, fw, disc_h - 8, C["panel"], r=14)
        cv.paragraph(fx + 22, dy + 16, disc, 20, "regular", fw - 44, max_lines=4, lh=1.25)
    if model_used:
        cv.text(cv.W - cv.M, cv.H - 34, "* MODEL GUIDANCE (NO OFFICIAL FORECAST)", 16, "bold", C["muted"], anchor="rs")
    footer(cv, pkg)
    return cv


# ================================================================== ABOVE AVERAGE
WARM_COLS = [(20, (200, 30, 90)), (15, (230, 50, 40)), (10, (245, 110, 40)), (0, (250, 165, 55))]


def _warm_col(dep):
    return next(c for t, c in WARM_COLS if dep >= t)


def warm_days(pkg, cfg):
    """Forecast days whose high beats the 1991-2020 normal by at least warm_departure_min (default 5F)."""
    ac = _ex(pkg).get("acis")
    if not ac or not ac.get("normals"):
        return [], []
    start = 1 if pkg.get("evening_mode") else 0
    allrows = []
    for d in pkg["days"][start:start + 7]:
        n = (ac["normals"].get(d["date"][5:]) or {}).get("hi")
        if n is None or d.get("high") is None:
            continue
        allrows.append({"d": d, "normal": round(n), "dep": round(d["high"] - n)})
    need = cfg.get("warm_departure_min", 5)
    return [r for r in allrows if r["dep"] >= need], allrows


def _dep_strip(cv, box, allrows, need):
    x, y, w, h = box
    cv.rect(x, y, w, h, C["panel"], r=16)
    cv.text(x + 24, y + 20, "DEGREES ABOVE / BELOW AVERAGE  ·  NEXT 7 DAYS", 19, "bold", C["muted"], anchor="lt")
    n = len(allrows)
    if not n:
        return
    slot = (w - 48) / n
    top, bot = y + 64, y + h - 44
    neg = max([-r["dep"] for r in allrows] + [0])
    pos = max([r["dep"] for r in allrows] + [1])
    mid = top + (bot - top) * max(0.55, min(0.72, pos / (pos + neg + 1e-6)))
    span = max(pos, neg, 8)
    cv.line([(x + 24, mid), (x + w - 24, mid)], (255, 255, 255, 70), 2)
    for i, r in enumerate(allrows):
        cx = x + 24 + slot * (i + 0.5)
        bh_ = ((mid - top - 30) if r["dep"] >= 0 else (bot - mid - 34)) * abs(r["dep"]) / span
        warm = r["dep"] >= need
        col = _warm_col(r["dep"]) if r["dep"] > 0 else (88, 150, 255)
        alpha = 255 if warm or r["dep"] < 0 else 110
        if r["dep"] == 0:
            cv.text(cx, mid - 10, "0°", min(24, slot * 0.3), "bold", C["muted"], anchor="ms")
        elif r["dep"] > 0:
            cv.rect(cx - slot * 0.28, mid - bh_, slot * 0.56, max(3, bh_), (*col, alpha), r=6)
            cv.text(cx, mid - bh_ - 8, f"+{r['dep']}°", min(24, slot * 0.3), "bold", C["text"] if warm else C["muted"], anchor="ms")
        else:
            cv.rect(cx - slot * 0.28, mid, slot * 0.56, max(3, bh_), (*col, alpha), r=6)
            cv.text(cx, mid + bh_ + 26, f"{r['dep']}°", min(24, slot * 0.3), "bold", C["muted"], anchor="ms")
        cv.text(cx, bot + 30, r["d"]["dow"][:3].upper(), min(20, slot * 0.28), "bold", C["text"] if warm else C["muted"], anchor="ms")


def above_average(pkg, cfg):
    warm, allrows = warm_days(pkg, cfg)
    if not warm:
        return None
    need = cfg.get("warm_departure_min", 5)
    cv = Canvas(cfg)
    area_ = pkg["location"].get("area", "Hampton Roads Area").upper()
    x, y, w, h = area(cv)
    strip_h = 230 if not cv.tall else (380 if cv.fmt == "vertical" else 250)
    hh = h - strip_h - 20
    _dep_strip(cv, (x, y + hh + 20, w, strip_h), allrows, need)
    if len(warm) == 1:
        r = warm[0]
        d, col = r["d"], _warm_col(r["dep"])
        cv.header("WARMER THAN AVERAGE", f"{area_}  ·  {d['dow'].upper()}, {d['date_label'].upper()}")
        cv.rect(x, y, w, hh, C["panel"], r=18)
        cv.rect(x, y, 12, hh, (*col, 255), r=6)
        if not cv.tall:
            cv.text(x + 70, y + 60, d["dow"].upper(), 40, "bold", anchor="lt")
            big = min(250, hh * 0.55)
            cv.text(x + 60, y + hh * 0.5 + big * 0.42, f"+{r['dep']}°", big, "bold", col, anchor="ls")
            cv.text(x + 70, y + hh - 50, "ABOVE AVERAGE", 34, "bold", C["muted"], anchor="ls")
            tx = x + w * 0.46
            for i, (lab, val) in enumerate((("FORECAST HIGH", f"{d['high']}°"), ("AVERAGE HIGH", f"{r['normal']}°"))):
                ty = y + 70 + i * (hh - 120) / 2
                cv.text(tx, ty, lab, 24, "bold", C["muted"], anchor="lt")
                cv.text(tx, ty + 34, val, min(120, hh * 0.24), "bold", C["text"] if i == 0 else C["muted"], anchor="lt")
            if d.get("icon"):
                draw_icon(cv, d["icon"], x + w - 150, y + hh / 2 - 20, min(180, hh * 0.4))
            if d.get("cond"):
                cv.text(x + w - 150, y + hh / 2 + min(180, hh * 0.4) / 2 + 30, d["cond"].upper(), 22, "bold", C["muted"],
                        anchor="mt", maxw=260)
        else:
            cv.text(x + w / 2, y + 60, d["dow"].upper(), 44, "bold", anchor="mt")
            big = min(260, hh * 0.4)
            cv.text(x + w / 2, y + 120 + big * 0.85, f"+{r['dep']}°", big, "bold", col, anchor="ms")
            cv.text(x + w / 2, y + 170 + big * 0.85, "ABOVE AVERAGE", 32, "bold", C["muted"], anchor="ms")
            gap_top, gap_bot = y + 200 + big * 0.85, y + hh - 190
            if d.get("icon") and gap_bot - gap_top > 150:
                ic = min(220, (gap_bot - gap_top) * 0.6)
                draw_icon(cv, d["icon"], x + w / 2, (gap_top + gap_bot) / 2 - 20, ic)
                if d.get("cond"):
                    cv.text(x + w / 2, (gap_top + gap_bot) / 2 + ic / 2 + 10, d["cond"].upper(), 26, "bold", C["muted"],
                            anchor="mt", maxw=w - 80)
            for i, (lab, val) in enumerate((("FORECAST HIGH", f"{d['high']}°"), ("AVERAGE HIGH", f"{r['normal']}°"))):
                cx = x + w * (0.27 + 0.46 * i)
                cv.text(cx, y + hh - 150, lab, 22, "bold", C["muted"], anchor="ms")
                cv.text(cx, y + hh - 50, val, 86, "bold", C["text"] if i == 0 else C["muted"], anchor="ms")
    else:
        avg = round(sum(r["dep"] for r in warm) / len(warm))
        peak = max(warm, key=lambda r: r["dep"])
        run = all(allrows.index(b) - allrows.index(a) == 1 for a, b in zip(warm, warm[1:]))
        when = (f"{warm[0]['d']['dow'].upper()} – {warm[-1]['d']['dow'].upper()}" if run
                else f"{len(warm)} OF THE NEXT {len(allrows)} DAYS")
        cv.header("WARM STRETCH" if run else "WARMER THAN AVERAGE", f"{area_}  ·  {when}  ·  AVERAGE +{avg}°")
        n = len(warm)
        cols = n if not cv.tall else (1 if n <= 3 else 2)
        boxes = grid(x, y, w, hh, n, cols, 16)
        for r, (bx, by, bw, bh) in zip(warm, boxes):
            d, col = r["d"], _warm_col(r["dep"])
            cv.rect(bx, by, bw, bh, C["panel"], r=16)
            cv.rect(bx, by, bw, 12, (*col, 255), r=6)
            if r is peak:
                cv.text(bx + bw - 18, by + 30, "WARMEST", 15, "bold", col, anchor="rt")
            cv.text(bx + bw / 2, by + min(64, bh * 0.2), d["dow"].upper()[:3] if bw < 300 else d["dow"].upper(),
                    min(34, bh * 0.14), "bold", anchor="ms")
            cv.text(bx + bw / 2, by + min(94, bh * 0.3), d["date_label"].upper(), min(19, bh * 0.08), "bold", C["muted"], anchor="ms")
            big = min(110, bw * 0.38, bh * 0.32)
            ic = min(120, bw * 0.4, bh * 0.22)
            if d.get("icon") and bh > 330:
                draw_icon(cv, d["icon"], bx + bw / 2, by + bh * 0.42, ic)
                cv.text(bx + bw / 2, by + bh * 0.68 + big * 0.36, f"+{r['dep']}°", big, "bold", col, anchor="ms")
            else:
                cv.text(bx + bw / 2, by + bh * 0.56 + big * 0.36, f"+{r['dep']}°", big, "bold", col, anchor="ms")
            cv.text(bx + bw / 2, by + bh - min(60, bh * 0.2), f"HIGH {d['high']}°", min(28, bh * 0.1), "bold", anchor="ms")
            cv.text(bx + bw / 2, by + bh - min(28, bh * 0.09), f"AVG {r['normal']}°", min(20, bh * 0.08), "bold", C["muted"], anchor="ms")
    footer(cv, pkg)
    return cv


GRAPHICS = {
    "weather_aware": weather_aware, "tides": tides, "high_tides": high_tides,
    "high_tides_2": lambda pkg, cfg: high_tides(pkg, cfg, "high_tides_2"), "beach": beach, "yesterday": yesterday, "month_rain": month_rain,
    "record_watch": record_watch, "above_average": above_average, "first_freeze": first_freeze, "commute": commute, "weekend": weekend,
    "sun_uv": sun_uv, "air_quality": air_quality, "tropics": tropics, "warning_count": warning_count, "aviation": aviation,
}
