"""WPC forecast fronts: where the cold / warm / stationary / occluded fronts and the highs and lows are expected.

Data: the National Forecast Chart vector service (mapservices.weather.noaa.gov ... /outlooks/natl_fcst_wx_chart, no key).
It publishes Day 1, Day 2 and Day 3 as real line features, so those are exact WPC positions.  WPC only publishes
Days 4-7 as pictures, so the vector graphics stop at Day 3 (set `fronts_days` to 1-3).
Graphics (all sizes):
  fronts_outlook     Today / Tomorrow / Day 3 side by side (stacked when tall) -- the "where is the next front" graphic
  fronts_day_1..3    one full-screen map per day with the fronts, H / L pressure centers and a Norfolk marker
Front symbols follow the weather-map convention: blue triangles = cold, red half-circles = warm, alternating =
stationary, purple = occluded, dashed gold = trough.  Symbols sit on the side the front is moving toward (the feed
does not say which side, so it is inferred: east / south of the line).
`"fronts_always": true` makes the graphics even when the map is quiet.
"""
import json
import math
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from PIL import Image, ImageDraw

from . import fullscreen, outlookmap
from .theme import C, Canvas, z

BASE = "https://mapservices.weather.noaa.gov/vector/rest/services/outlooks/natl_fcst_wx_chart/MapServer"
LAYERS = {1: {"fronts": 2, "hl": 1}, 2: {"fronts": 14, "hl": 13}, 3: {"fronts": 26, "hl": 25}}
VIEW_FULL = (-100.0, -64.0, 25.0, 48.5)  # the eastern two-thirds of the U.S., Norfolk lower right of center
VIEW_PANEL = (-98.0, -66.5, 26.0, 47.5)
KORF = (36.90, -76.20)

COLORS = {"cold": (88, 170, 255), "warm": (255, 96, 96), "stationary": (88, 170, 255), "occluded": (190, 128, 255),
          "trough": (255, 198, 41)}
NAMES = {"cold": "Cold front", "warm": "Warm front", "stationary": "Stationary front", "occluded": "Occluded front",
         "trough": "Trough"}


def _kind(text):
    t = (text or "").lower()
    for key, k in (("cold", "cold"), ("warm", "warm"), ("stationary", "stationary"), ("stnry", "stationary"),
                   ("occlu", "occluded"), ("ocfnt", "occluded"), ("trof", "trough"), ("trough", "trough"),
                   ("dry line", "trough"), ("squall", "trough"), ("outflow", "trough")):
        if key in t:
            return k
    return None


def _query(layer, retries=3):
    q = urllib.parse.urlencode({"where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "json"})
    url = f"{BASE}/{layer}/query?{q}"
    err = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KORF-weather-graphics (wxrjm)"})
            with urllib.request.urlopen(req, timeout=40) as r:
                data = json.loads(r.read().decode("utf-8"))
            if "error" in data:
                raise RuntimeError(str(data["error"]))
            return data.get("features") or []
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(2 ** a)
    raise RuntimeError(f"WPC fronts layer {layer}: {err}")


def parse_fronts(features):
    """-> [{"kind", "pts": [(lon, lat), ...]}]"""
    out = []
    for f in features:
        at = f.get("attributes") or {}
        kind = _kind(at.get("feat")) or _kind(at.get("popupconte")) or _kind(" ".join(str(v) for v in at.values()))
        if not kind:
            continue
        for path in (f.get("geometry") or {}).get("paths") or []:
            pts = [(p[0], p[1]) for p in path if len(p) >= 2]
            if len(pts) >= 2:
                out.append({"kind": kind, "pts": pts})
    return out


def parse_centers(features):
    """-> [{"kind": "H"|"L", "p": mb or None, "lon", "lat"}]"""
    out = []
    for f in features:
        at = f.get("attributes") or {}
        blob = " ".join(str(v) for k, v in at.items() if k.lower() in ("feat", "popupconte", "label", "name"))
        low = blob.lower()
        if re.search(r"\blow\b|\bl\b", low) and not re.search(r"\bhigh\b|\bh\b", low):
            kind = "L"
        elif re.search(r"\bhigh\b|\bh\b", low):
            kind = "H"
        else:
            kind = "L" if "low" in low else ("H" if "high" in low else None)
        if not kind:
            continue
        m = re.search(r"\b(9[0-9]{2}|10[0-9]{2})\b", blob)
        g = f.get("geometry") or {}
        if "x" in g and "y" in g:
            lon, lat = g["x"], g["y"]
        elif g.get("paths"):
            lon, lat = g["paths"][0][0][:2]
        elif g.get("points"):
            lon, lat = g["points"][0][:2]
        else:
            continue
        out.append({"kind": kind, "p": int(m.group(1)) if m else None, "lon": lon, "lat": lat})
    return out


def fetch(cfg, cache_dir, now_local, debug=False):
    days = [d for d in (cfg.get("fronts_days") or [1, 2, 3]) if d in LAYERS]
    pkg = {"days": {}, "errors": [], "now": now_local}
    for d in days:
        try:
            ff = _query(LAYERS[d]["fronts"])
            try:
                hl = _query(LAYERS[d]["hl"])
            except Exception as e:  # noqa: BLE001
                hl = []
                pkg["errors"].append(f"day {d} highs/lows: {e}")
            pkg["days"][d] = {"fronts": parse_fronts(ff), "centers": parse_centers(hl)}
            if debug:
                print(f"  fronts day {d}: {len(ff)} line features -> {len(pkg['days'][d]['fronts'])} segments, "
                      f"{len(hl)} H/L features -> {len(pkg['days'][d]['centers'])} centers")
                for f in (ff[:2] + hl[:2]):
                    print("     sample attributes:", {k: v for k, v in (f.get("attributes") or {}).items()})
        except Exception as e:  # noqa: BLE001
            pkg["errors"].append(str(e))
            print(f"  ! fronts day {d}: {e}")
    return pkg


def sample(now_local):
    """Synthetic map: a cold front sweeping through the Ohio Valley, a warm front and a Gulf stationary front."""
    def sh(dx):
        return lambda p: (p[0] + dx, p[1])
    cold = [(-106, 49), (-100, 43), (-96, 38), (-95, 33), (-97, 29)]
    warm = [(-92, 38), (-86, 39), (-81, 39.5), (-77, 38.5)]
    stat = [(-98, 28), (-90, 29.5), (-84, 30), (-79, 31.5)]
    occ = [(-93, 45), (-91, 42), (-92, 38)]
    out = {"days": {}, "errors": [], "now": now_local}
    for i, d in enumerate((1, 2, 3)):
        s = sh(7.5 * i)
        out["days"][d] = {
            "fronts": [{"kind": "cold", "pts": [s(p) for p in cold]}, {"kind": "warm", "pts": [s(p) for p in warm]},
                       {"kind": "stationary", "pts": [(p[0] + 2 * i, p[1] - i) for p in stat]},
                       {"kind": "occluded", "pts": [s(p) for p in occ]},
                       {"kind": "trough", "pts": [(-110 + 4 * i, 36), (-106 + 4 * i, 32)]}],
            "centers": [{"kind": "L", "p": 996 - 2 * i, "lon": -93 + 7.5 * i, "lat": 46}, {"kind": "H", "p": 1024, "lon": -74 + 2 * i, "lat": 32},
                        {"kind": "H", "p": 1030 - i, "lon": -112 + 4 * i, "lat": 42}]}
    return out


# ---------- drawing ----------

def _resample(pts, step):
    """Points every `step` px along the polyline: [(x, y, tx, ty)] with unit tangents."""
    out, carry = [], step / 2
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy)
        if ln < 1e-6:
            continue
        tx, ty = dx / ln, dy / ln
        pos = carry
        while pos < ln:
            out.append((x0 + tx * pos, y0 + ty * pos, tx, ty))
            pos += step
        carry = pos - ln
    return out


def _side(tx, ty, motion):
    """Normal on the side the front moves toward (screen coords: +x east, +y south)."""
    n1, n2 = (-ty, tx), (ty, -tx)
    return n1 if n1[0] * motion[0] + n1[1] * motion[1] >= n2[0] * motion[0] + n2[1] * motion[1] else n2


def _tri(d, x, y, tx, ty, nx, ny, s, col):
    a = (x - tx * s * 0.55, y - ty * s * 0.55)
    b = (x + tx * s * 0.55, y + ty * s * 0.55)
    c = (x + nx * s, y + ny * s)
    d.polygon([a, b, c], fill=(*col, 255), outline=(10, 16, 30, 255))


def _semi(d, x, y, tx, ty, nx, ny, s, col):
    pts = []
    for k in range(13):
        ang = math.pi * k / 12
        px = math.cos(ang) * s * 0.55
        py = math.sin(ang) * s * 0.8
        pts.append((x + tx * px * -1 + nx * py, y + ty * px * -1 + ny * py))
    d.polygon(pts, fill=(*col, 255), outline=(10, 16, 30, 255))


def draw_front(d, pts, kind, scale, motion=(1.0, 0.45)):
    """pts in HI-RES pixels; scale = hi-res px per design px."""
    col = COLORS[kind]
    lw = max(2, int(round(5 * scale)))
    s = 21 * scale
    halo = (10, 16, 30, 235)
    if kind == "trough":
        for seg in _resample(pts, 26 * scale):
            x, y, tx, ty = seg
            d.line([(x - tx * 8 * scale, y - ty * 8 * scale), (x + tx * 8 * scale, y + ty * 8 * scale)], fill=halo, width=lw + 3)
        for seg in _resample(pts, 26 * scale):
            x, y, tx, ty = seg
            d.line([(x - tx * 8 * scale, y - ty * 8 * scale), (x + tx * 8 * scale, y + ty * 8 * scale)], fill=(*col, 255), width=lw)
        return
    if kind == "stationary":
        d.line(pts, fill=halo, width=lw + 4, joint="curve")
    else:
        d.line(pts, fill=halo, width=lw + 4, joint="curve")
    if kind == "stationary":
        # alternating blue (one side) / red (other side), each a short colored dash
        marks = _resample(pts, s * 1.9)
        for k, (x, y, tx, ty) in enumerate(marks):
            nx, ny = _side(tx, ty, motion)
            blue = (k % 2 == 0)
            c = COLORS["cold"] if blue else COLORS["warm"]
            seg = [(x - tx * s * 0.95, y - ty * s * 0.95), (x + tx * s * 0.95, y + ty * s * 0.95)]
            d.line(seg, fill=(*c, 255), width=lw)
            if blue:
                _tri(d, x, y, tx, ty, nx, ny, s * 0.9, c)
            else:
                _semi(d, x, y, tx, ty, -nx, -ny, s * 0.9, c)
        return
    d.line(pts, fill=(*col, 255), width=lw, joint="curve")
    step = s * (2.0 if kind != "occluded" else 2.6)
    for k, (x, y, tx, ty) in enumerate(_resample(pts, step)):
        nx, ny = _side(tx, ty, motion)
        if kind == "cold":
            _tri(d, x, y, tx, ty, nx, ny, s, col)
        elif kind == "warm":
            _semi(d, x, y, tx, ty, nx, ny, s, col)
        else:  # occluded: triangles and half-circles alternate on the same side
            (_tri if k % 2 == 0 else _semi)(d, x, y, tx, ty, nx, ny, s, col)


def _center(d, cv_font_draw, x, y, c, scale):
    """H / L letter with pressure under it (design px sizes * scale)."""
    from .theme import font
    col = (88, 170, 255) if c["kind"] == "H" else (255, 96, 96)
    big = 44
    d.text((x, y), c["kind"], font=font("bold", big * scale / 2), fill=(*col, 255), anchor="mm", stroke_width=max(2, int(3 * scale)),
           stroke_fill=(10, 16, 30, 255))
    if c.get("p"):
        d.text((x, y + 34 * scale), str(c["p"]), font=font("bold", 20 * scale / 2), fill=(255, 255, 255, 255), anchor="mm",
               stroke_width=max(2, int(2.5 * scale)), stroke_fill=(10, 16, 30, 255))


def _paint_map(cv, x, y, w, h, view, data, cfg, scale_ui=1.0, korf=True):
    """Map + fronts into the box (x, y, w, h) in design px.  Returns the projection (design px) of the box."""
    view = tuple(view)
    lay = outlookmap.draw_map([], w, h, cfg, outline=False, view=view, cities=[("-", 0, 0, 2)], water_alpha=0.3,
                              county_lines=False)
    cv.img.paste(lay.convert("RGB"), (z(x), z(y)))
    cv.d = ImageDraw.Draw(cv.img, "RGBA")
    ww, ee, ss, nn = outlookmap._view(w, h, view)
    px = lambda lo, la: (z(x) + (lo - ww) / (ee - ww) * z(w), z(y) + (nn - la) / (nn - ss) * z(h))
    # fronts: clip to the map box via a layer
    layer = Image.new("RGBA", cv.img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer, "RGBA")
    order = {"trough": 0, "stationary": 1, "occluded": 2, "warm": 3, "cold": 4}
    for fr in sorted(data["fronts"], key=lambda f: order[f["kind"]]):
        pts = [px(lo, la) for lo, la in fr["pts"]]
        draw_front(ld, pts, fr["kind"], 2 * scale_ui)
    for c in data["centers"]:
        _center(ld, None, *px(c["lon"], c["lat"]), c, 2 * scale_ui)
    if korf:
        kx, ky = px(KORF[1], KORF[0])
        r = 9 * 2 * scale_ui
        ld.ellipse([kx - r, ky - r, kx + r, ky + r], fill=(255, 255, 255, 255), outline=(10, 16, 30, 255), width=int(3 * 2 * scale_ui / 2))
        from .theme import font
        ld.text((kx + r + 8, ky), "NORFOLK", font=font("bold", 15 * 2 * scale_ui / 2), fill=(255, 255, 255, 255), anchor="lm",
                stroke_width=max(2, int(3 * scale_ui)), stroke_fill=(10, 16, 30, 255))
    box = Image.new("L", cv.img.size, 0)
    ImageDraw.Draw(box).rectangle([z(x), z(y), z(x + w), z(y + h)], fill=255)
    layer.putalpha(Image.composite(layer.getchannel("A"), Image.new("L", cv.img.size, 0), box))
    base = cv.img.convert("RGBA")
    base.alpha_composite(layer)
    cv.img = base.convert("RGB")
    cv.d = ImageDraw.Draw(cv.img, "RGBA")


def _legend(cv, y, kinds):
    items = [(k, NAMES[k]) for k in kinds]
    avail = cv.W - 2 * cv.M
    fs, wsym, gap = (20, 64, 34) if not cv.tall else (17, 52, 22)
    while True:
        total = sum(wsym + 12 + cv.width(n.upper(), fs) + gap for _, n in items) - gap
        if total <= avail - 8 or fs <= 12:
            break
        fs -= 1
        wsym = max(34, wsym - 3)
        gap = max(14, gap - 1)
    x = cv.M
    cv.rect(x - 16, y - 20, total + 32, 52, (20, 31, 54, 235), r=12)
    for k, n in items:
        layer = Image.new("RGBA", cv.img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer, "RGBA")
        draw_front(ld, [(z(x), z(y + 6)), (z(x + wsym), z(y + 6))], k, 1.0)
        base = cv.img.convert("RGBA")
        base.alpha_composite(layer)
        cv.img = base.convert("RGB")
        cv.d = ImageDraw.Draw(cv.img, "RGBA")
        cv.text(x + wsym + 12, y + 6, n.upper(), fs, "bold", C["text"], anchor="lm")
        x += wsym + 12 + cv.width(n.upper(), fs) + gap


def _day_names(now, days):
    out = {}
    base = now.date()
    for d in days:
        dt = base + timedelta(days=d - 1)
        lab = "TODAY" if d == 1 else ("TOMORROW" if d == 2 else dt.strftime("%A").upper())
        out[d] = (lab, dt.strftime("%a %b %-d").upper() if hasattr(dt, "strftime") else "")
    return out


def _fmt_date(dt):
    return f"{dt.strftime('%a %b')} {dt.day}".upper()


def _kinds_in(*datas):
    ks = []
    for dd in datas:
        for f in dd["fronts"]:
            if f["kind"] not in ks:
                ks.append(f["kind"])
    order = ["cold", "warm", "stationary", "occluded", "trough"]
    return sorted(ks, key=order.index)


def _day_graphic(pkg, cfg, d, now):
    data = pkg["days"][d]
    cv = Canvas(cfg)
    W, H = cv.W, cv.H
    view = fullscreen.expand_view(VIEW_FULL, 175 / H, 150 / H)
    _paint_map(cv, 0, 0, W, H, view, data, cfg)
    fullscreen._fade(cv, 0, 270, 238, 0)
    fullscreen._fade(cv, H - 190, H, 0, 225)
    dt = now.date() + timedelta(days=d - 1)
    lab = "TODAY" if d == 1 else ("TOMORROW" if d == 2 else dt.strftime("%A").upper())
    cv.header(f"FRONTS {lab}" if d <= 2 else f"FRONTS {lab}", f"{_fmt_date(dt)}  ·  WPC FORECAST POSITIONS")
    kinds = _kinds_in(data) or ["cold"]
    _legend(cv, H - 112, kinds)
    cv.footer(pkg, source="NWS WPC")
    return cv


def _outlook_graphic(pkg, cfg, days, now):
    cv = Canvas(cfg)
    W, H = cv.W, cv.H
    top, bot = 190, H - 150
    n = len(days)
    gap = 16
    if not cv.tall:
        pw = int((W - 2 * cv.M - gap * (n - 1)) / n)
        ph = bot - top
        boxes = [(cv.M + i * (pw + gap), top, pw, ph) for i in range(n)]
    else:
        pw = W - 2 * cv.M
        ph = int((bot - top - gap * (n - 1)) / n)
        boxes = [(cv.M, top + i * (ph + gap), pw, ph) for i in range(n)]
    for (x, y, w, h), d in zip(boxes, days):
        _paint_map(cv, x, y, w, h, VIEW_PANEL, pkg["days"][d], cfg, scale_ui=0.62 if not cv.tall else 0.52, korf=True)
        dt = now.date() + timedelta(days=d - 1)
        lab = "TODAY" if d == 1 else ("TOMORROW" if d == 2 else dt.strftime("%A").upper())
        fs = 26 if not cv.tall else 24
        tw = cv.width(lab, fs) + 28
        cv.rect(x + 10, y + 10, tw, 44, (20, 31, 54, 235), r=10)
        cv.text(x + 24, y + 32, lab, fs, "bold", C["text"], anchor="lm")
        cv.rect(x + 10, y + 10, 6, 44, (*C["rain"], 255), r=3)
    cv.header("FRONTS: NEXT 3 DAYS", "WPC FORECAST POSITIONS  ·  " + "  ·  ".join(
        _fmt_date(now.date() + timedelta(days=d - 1)) for d in days[:3]) if not cv.tall else "WPC FORECAST POSITIONS")
    _legend(cv, H - 100, _kinds_in(*[pkg["days"][d] for d in days]) or ["cold"])
    cv.footer(pkg, source="NWS WPC")
    return cv


def fronts_graphics(pkg, cfg):
    fr = pkg.get("_fronts")
    if not fr or not fr["days"]:
        return None
    now = fr["now"]
    days = sorted(d for d, v in fr["days"].items() if v["fronts"] or v["centers"])
    if not days:
        return None
    quiet = not any(fr["days"][d]["fronts"] for d in days)
    if quiet and not cfg.get("fronts_always"):
        print("  - fronts: no fronts in the WPC forecast, skipped")
        return None
    pk = dict(pkg)
    pk["_x"] = 1
    pk["days"] = fr["days"]
    out = []
    if len(days) >= 2:
        out.append(("fronts_outlook", _outlook_graphic(pk, cfg, days, now)))
    for d in days:
        out.append((f"fronts_day_{d}", _day_graphic(pk, cfg, d, now)))
    return out
