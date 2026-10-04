"""River flood forecast graphics from NWS river forecasts (NWPS, keyless):
  https://api.water.noaa.gov/nwps/v1/gauges/{LID}             flood stages + impact statements
  https://api.water.noaa.gov/nwps/v1/gauges/{LID}/stageflow   observed + official forecast hydrograph

A graphic is ONLY made for a gauge whose forecast (or latest reading) reaches action stage or higher,
plus a summary list when any gauge does. Gauges with no flooding make nothing.
"""
import json
import urllib.request
from datetime import datetime, timedelta

from PIL import ImageDraw

from .theme import C, Canvas, z

NWPS = "https://api.water.noaa.gov/nwps/v1/gauges"
ORDER = [None, "action", "minor", "moderate", "major"]
CAT = {None: ("BELOW ACTION STAGE", (70, 180, 100)), "action": ("ACTION STAGE", (255, 232, 0)),
       "minor": ("MINOR FLOODING", (255, 150, 0)), "moderate": ("MODERATE FLOODING", (230, 30, 30)),
       "major": ("MAJOR FLOODING", (190, 60, 220))}
DEFAULT_GAUGES = [  # AKQ-area river forecast points (Hampton Roads DMA + nearby)
    {"lid": "FKNV2", "name": "Blackwater River at Franklin"},
    {"lid": "SEBV2", "name": "Nottoway River near Sebrell"},
    {"lid": "ZUNV2", "name": "Blackwater River near Zuni"},
    {"lid": "DNDV2", "name": "Blackwater River at Dendron"},
    {"lid": "RVDV2", "name": "Nottoway River near Riverdale"},
    {"lid": "STYV2", "name": "Nottoway River near Stony Creek"},
    {"lid": "RAWV2", "name": "Nottoway River near Rawlings"},
    {"lid": "EPOV2", "name": "Meherrin River at Emporia"},
    {"lid": "LAWV2", "name": "Meherrin River near Lawrenceville"},
    {"lid": "MTCV2", "name": "Appomattox River at Matoaca"},
    {"lid": "WONN7", "name": "Chowan River near Winton"},
]


def category(v, stages):
    cat = None
    for k in ORDER[1:]:
        if stages.get(k) is not None and v >= stages[k]:
            cat = k
    return cat


def _get(url, ua):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _series(block, tz):
    out = []
    for d in (block or {}).get("data") or []:
        v = d.get("primary")
        if v is None or v <= -900:
            continue
        out.append((datetime.fromisoformat(d["validTime"].replace("Z", "+00:00")).astimezone(tz), float(v)))
    return out


def build_gauge(g, meta, sf, now, tz):
    """meta = /gauges/{lid} JSON, sf = /stageflow JSON -> normalized gauge dict (or None if no stages)."""
    cats = (meta.get("flood") or {}).get("categories") or {}
    stages = {k: (cats.get(k) or {}).get("stage") for k in ORDER[1:]}
    stages = {k: v for k, v in stages.items() if isinstance(v, (int, float)) and v > -900}
    if not stages:
        return None
    obs = [p for p in _series(sf.get("observed"), tz) if p[0] >= now - timedelta(days=3)]
    fc = _series(sf.get("forecast"), tz)
    impacts = sorted(((float(i["stage"]), i.get("statement", "").strip()) for i in (meta.get("flood") or {}).get("impacts") or []
                      if isinstance(i.get("stage"), (int, float))), reverse=True)
    allv = [v for _, v in fc] + [v for _, v in obs[-1:]]
    crest = max(fc, key=lambda p: p[1]) if fc else (obs[-1] if obs else None)
    worst = category(max(allv), stages) if allv else None
    return {"lid": g["lid"], "name": g.get("name") or meta.get("name"), "stages": stages, "observed": obs, "forecast": fc,
            "issued": ((sf.get("forecast") or {}).get("issuedTime")), "crest": crest,
            "now": obs[-1] if obs else None, "worst": worst, "impacts": impacts,
            "units": (sf.get("forecast") or sf.get("observed") or {}).get("primaryUnits", "ft")}


def fetch(cfg, now, tz, debug=False):
    ua = cfg["user_agent"]
    out = []
    for g in cfg.get("river_gauges") or DEFAULT_GAUGES:
        try:
            meta = _get(f"{NWPS}/{g['lid']}", ua)
            sf = _get(f"{NWPS}/{g['lid']}/stageflow", ua)
            got = build_gauge(g, meta, sf, now, tz)
            if debug:
                print(f"   [rivers] {g['lid']}: crest {got and got['crest']}, worst {got and got['worst']}")
            if got:
                out.append(got)
        except Exception as e:
            print(f"  ! river gauge {g['lid']}: {e}")
    return out


def flooding(gauges, cfg):
    least = cfg.get("river_min_category", "action")
    return [g for g in gauges if g["worst"] and ORDER.index(g["worst"]) >= ORDER.index(least)]


# ------------------------------------------------------------------ drawing
def _t(dt):
    return dt.strftime("%a %I %p").replace(" 0", " ").upper() if dt else "--"


def _hydrograph(cv, box, g, now):
    x, y, w, h = box
    cv.rect(x, y, w, h, C["panel"], r=16)
    px0, px1, py0, py1 = x + 92, x + w - 30, y + 30, y + h - 92
    st = g["stages"]
    pts = g["observed"] + g["forecast"]
    if not pts:
        return
    vals = [v for _, v in pts]
    lo = min(vals) - 1.0
    hi = max(max(vals) + 1.5, (st.get("minor") or st.get("action") or max(vals)) + 1.0)
    t0, t1 = min(t for t, _ in pts), max(t for t, _ in pts)
    X_ = lambda t: px0 + (t - t0).total_seconds() / max(1, (t1 - t0).total_seconds()) * (px1 - px0)
    Y_ = lambda v: py1 - (v - lo) / (hi - lo) * (py1 - py0)
    keys = [k for k in ORDER[1:] if st.get(k) is not None]
    for i, k in enumerate(keys):  # category bands
        v = st[k]
        if v >= hi:
            continue
        nxt = st.get(keys[i + 1]) if i + 1 < len(keys) else None
        top = Y_(min(nxt, hi)) if nxt and nxt < hi else py0
        col = CAT[k][1]
        cv.rect(px0, top, px1 - px0, Y_(max(v, lo)) - top, (*col, 50))
        cv.line([(px0, Y_(v)), (px1, Y_(v))], (*col, 230), 2)
        cv.text(px1 - 8, Y_(v) - 6, f"{k.upper()} {v:g} FT", 17, "bold", col, anchor="rs")
    step = max(1, round((hi - lo) / 6))
    v = int(lo) + 1
    while v < hi:  # y axis
        cv.text(px0 - 14, Y_(v), f"{v}'", 18, "bold", C["muted"], anchor="rm")
        cv.line([(px0, Y_(v)), (px1, Y_(v))], (255, 255, 255, 22), 1)
        v += step
    d = t0.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    while d < t1:  # day lines
        cv.line([(X_(d), py0), (X_(d), py1)], (255, 255, 255, 40), 1)
        d += timedelta(days=1)
    d = t0.replace(hour=12, minute=0, second=0, microsecond=0)
    while d < t1:  # day names centered on each day
        if t0 <= d:
            cv.text(X_(d), py1 + 30, d.strftime("%a").upper() + f" {d.day}", 18, "bold", C["muted"], anchor="ms")
        d += timedelta(days=1)
    if g["observed"]:
        cv.line([(X_(t), Y_(v)) for t, v in g["observed"]], (120, 190, 255, 255), 4)
    if g["forecast"]:
        seg = ([g["observed"][-1]] if g["observed"] else []) + g["forecast"]
        cv.line([(X_(t), Y_(v)) for t, v in seg], (255, 255, 255, 255), 4)
    if now and t0 <= now <= t1:
        cv.line([(X_(now), py0), (X_(now), py1)], (255, 255, 255, 120), 2)
        cv.text(X_(now) + 6, py0 + 4, "NOW", 16, "bold", C["muted"], anchor="lt")
    if g["crest"] and g["forecast"]:
        ct, cvv = g["crest"]
        r = 9
        cv.d.ellipse([z(X_(ct) - r), z(Y_(cvv) - r), z(X_(ct) + r), z(Y_(cvv) + r)],
                     fill=(*CAT[category(cvv, st)][1], 255), outline=(255, 255, 255, 255), width=z(2))
        cv.text(X_(ct), Y_(cvv) - 20, f"CREST {cvv:.1f} FT", 20, "bold", anchor="ms")
    lx = x + 26
    cv.line([(lx, y + h - 22), (lx + 34, y + h - 22)], (120, 190, 255, 255), 4)
    cv.text(lx + 44, y + h - 22, "OBSERVED", 16, "bold", C["muted"], anchor="lm")
    cv.line([(lx + 160, y + h - 22), (lx + 194, y + h - 22)], (255, 255, 255, 255), 4)
    cv.text(lx + 204, y + h - 22, "NWS FORECAST", 16, "bold", C["muted"], anchor="lm")


def _impact_for(g, v):
    for stage, txt in g["impacts"]:
        if stage <= v + 0.05 and txt:
            return stage, txt
    return None


def gauge_graphic(g, pkg, cfg, now):
    cv = Canvas(cfg)
    cv.header("RIVER FLOOD FORECAST", g["name"].upper())
    x, y, w, h = cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top
    if not cv.tall:
        chart, panel = (x, y, w * 0.62, h), (x + w * 0.62 + 22, y, w * 0.38 - 22, h)
    else:
        ch = h * (0.58 if cv.fmt == "vertical" else 0.42 if cv.fmt == "square" else 0.5)
        chart, panel = (x, y, w, ch), (x, y + ch + 20, w, h - ch - 20)
    _hydrograph(cv, chart, g, now)
    px, py, pw, ph = panel
    cv.rect(px, py, pw, ph, C["panel"], r=16)
    lab, col = CAT[g["worst"]]
    crest = g["crest"]
    cv.text(px + 26, py + 24, "FORECAST CREST", 21, "bold", C["muted"], anchor="lt")
    cv.text(px + 26, py + 58, f"{crest[1]:.1f} FT" if crest else "--", 66 if not cv.tall else 58, "bold", anchor="lt")
    cv.text(px + pw - 26, py + 70, _t(crest[0]) if crest else "", 24, "bold", C["muted"], anchor="rt")
    bh = 64
    cy = py + 150
    cv.rect(px + 26, cy, pw - 52, bh, (*col, 255), r=12)
    ink = (20, 28, 46) if 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2] > 150 else C["text"]
    cv.text(px + pw / 2, cy + bh / 2, lab, 30, "bold", ink, anchor="mm", maxw=pw - 80)
    ry = cy + bh + 24
    nowv = g["now"]
    st = g["stages"]
    facts = [("LATEST", f"{nowv[1]:.1f} FT  ·  {_t(nowv[0])}" if nowv else "--"),
             ("FLOOD STAGE", f"{st['minor']:g} FT" if st.get("minor") is not None else "--"),
             ("ACTION STAGE", f"{st['action']:g} FT" if st.get("action") is not None else "--")]
    for k, v in facts:
        cv.text(px + 26, ry, k, 20, "bold", C["muted"], anchor="lt")
        cv.text(px + pw - 26, ry, v, 22, "bold", anchor="rt")
        ry += 38
    imp = _impact_for(g, crest[1]) if crest else None
    if imp and py + ph - ry > 120:  # only when there's room for at least two lines
        ry += 8
        cv.line([(px + 26, ry), (px + pw - 26, ry)], (255, 255, 255, 60), 1.5)
        ry += 16
        cv.text(px + 26, ry, f"AT {imp[0]:g} FT", 20, "bold", C["muted"], anchor="lt")
        lines = max(1, int((py + ph - ry - 52) // 31))
        cv.paragraph(px + 26, ry + 34, imp[1], 24, "regular", pw - 52, max_lines=lines, lh=1.28)
    cv.footer(pkg, source="SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NWS River Forecast")
    return cv


def summary_graphic(gs, pkg, cfg, now):
    cv = Canvas(cfg)
    cv.header("RIVER FLOODING", "RIVERS FORECAST TO REACH ACTION STAGE OR HIGHER")
    x, y, w, h = cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top
    gs = sorted(gs, key=lambda g: -ORDER.index(g["worst"]))[:8]
    gap = 14
    rh = min(150, (h - gap * (len(gs) - 1)) / max(1, len(gs)))
    for i, g in enumerate(gs):
        ry = y + i * (rh + gap)
        lab, col = CAT[g["worst"]]
        cv.accent_row(x, ry, w, rh, bar=col)
        crest = g["crest"]
        if not cv.tall:
            cv.text(x + 34, ry + rh / 2 - 4, g["name"].upper(), min(32, rh * 0.26), "bold", anchor="ls", maxw=w * 0.42)
            nowv = g["now"]
            cv.text(x + 34, ry + rh / 2 + 30, f"NOW {nowv[1]:.1f} FT" if nowv else "", 20, "bold", C["muted"], anchor="ls")
            cv.text(x + w * 0.5, ry + rh / 2 - 4, f"CREST {crest[1]:.1f} FT" if crest else "--", min(34, rh * 0.28), "bold", anchor="ls")
            cv.text(x + w * 0.5, ry + rh / 2 + 30, _t(crest[0]) if crest else "", 20, "bold", C["muted"], anchor="ls")
            bw = 330
            cv.rect(x + w - bw - 20, ry + rh / 2 - 30, bw, 60, (*col, 255), r=12)
            ink = (20, 28, 46) if 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2] > 150 else C["text"]
            cv.text(x + w - bw / 2 - 20, ry + rh / 2, lab, 24, "bold", ink, anchor="mm", maxw=bw - 20)
        else:
            cv.text(x + 30, ry + 22, g["name"].upper(), min(28, rh * 0.2), "bold", anchor="lt", maxw=w - 60)
            cv.text(x + 30, ry + rh - 24, (f"CREST {crest[1]:.1f} FT  ·  {_t(crest[0])}" if crest else ""), min(24, rh * 0.17),
                    "bold", C["muted"], anchor="ls", maxw=w * 0.55)
            pw_ = cv.width(lab, 20, "bold") + 30
            cv.rect(x + w - pw_ - 20, ry + rh - 58, pw_, 40, (*col, 255), r=20)
            ink = (20, 28, 46) if 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2] > 150 else C["text"]
            cv.text(x + w - pw_ / 2 - 20, ry + rh - 38, lab, 20, "bold", ink, anchor="mm")
    cv.footer(pkg, source="SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NWS River Forecast")
    return cv


def river_graphics(pkg, cfg):
    gs = pkg.get("_rivers")
    if gs is None:
        return None
    flood = flooding(gs, cfg)
    if not flood:
        print("  - river_flooding: no river forecast at action stage or higher, nothing exported")
        return None
    now = datetime.fromisoformat(pkg["issued"])
    flood = sorted(flood, key=lambda g: (-ORDER.index(g["worst"]), g["name"]))
    out = [("river_flooding", summary_graphic(flood, pkg, cfg, now))]
    for i, g in enumerate(flood[:cfg.get("river_graphics_max", 6)], 1):
        out.append((f"river_{i}_{g['lid'].lower()}", gauge_graphic(g, pkg, cfg, now)))
    return out


def sample(now, tz):
    """Blackwater at Franklin cresting in minor flood, Nottoway at Sebrell at action stage, the rest normal."""
    import math
    out = []
    for lid, name, base, peak, st in (("FKNV2", "Blackwater River at Franklin", 5.2, 12.4, (6.8, 10.8, 14.8, 18.8)),
                                      ("SEBV2", "Nottoway River near Sebrell", 8.0, 15.6, (14.0, 16.0, 19.0, 23.0)),
                                      ("ZUNV2", "Blackwater River near Zuni", 3.0, 6.0, (9.0, 11.0, 14.0, 18.0))):
        t0 = now - timedelta(days=2)
        obs, fc = [], []
        for k in range(0, 24 * 7, 3):
            t = t0 + timedelta(hours=k)
            v = base + (peak - base) * math.exp(-((k - 24 * 4) / 40.0) ** 2) * (1 if k > 10 else 0.2)
            (obs if t <= now else fc).append((t, round(v, 2)))
        stages = dict(zip(ORDER[1:], st))
        meta = {"flood": {"categories": {k: {"stage": v} for k, v in stages.items()},
                          "impacts": [{"stage": 20.8, "statement": "2nd and Mechanic Streets flooded, Bowers Road residences flooded."},
                                      {"stage": 12.0, "statement": "Water approaches low-lying portions of Armory Drive and the "
                                                                    "Barrett's Landing boat ramp. Lowland flooding along the river."},
                                      {"stage": 15.0, "statement": "Floodwaters reach yards along the river; secondary roads flood."}]}}
        sf = {"observed": {"data": [{"validTime": t.isoformat(), "primary": v} for t, v in obs]},
              "forecast": {"data": [{"validTime": t.isoformat(), "primary": v} for t, v in fc], "primaryUnits": "ft"}}
        out.append(build_gauge({"lid": lid, "name": name}, meta, sf, now, tz))
    return out
