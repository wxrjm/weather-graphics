"""Hazard Outlooks: the NWS Graphical Hazardous Weather Outlook (GHWO), keyless.

Data (per forecast office, default Wakefield "akq"; https://www.weather.gov/ghwo?wfo=akq):
  https://www.weather.gov/source/<wfo>/ghwo/chicklet.json   hazards x 7 days, each day's top level colour + image path
  https://www.weather.gov/source/<wfo>/ghwo/legend.json     what each level (0-4) means, per hazard
  https://www.weather.gov/images/<wfo>/ghwo/<Hazard>Day<N>.jpg   the office's risk map for that hazard and day

Graphics (folder "Hazard Outlooks"):
  hazout_week                 7-day grid: every hazard against every day, plus what the top levels mean
  hazout_<hazard>_day<N>      the VA/NC stencil map for each hazard-day that has a risk (level 1-4)

The risk maps are only published as pictures, so they are read back into a level grid: each pixel is mapped to
latitude/longitude with the office calibration in CALIB (an affine fit to city dots), then classified by colour
(yellow=1, orange=2, red=3, purple=4).  That is approximate; the week grid and the legend text come straight from the JSON.
Config: ghwo_wfo, ghwo_max_maps (default 12), ghwo_hide_empty (default true), ghwo_hidden (rows the NWS page also hides).
"""
import colorsys
import io
import json
import math
import re
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from . import statemaps
from .statemaps import _counties, _legend_chips, _panel, _rgb, _src, stencil_map
from .alertmap import _paste_rounded
from .theme import C, Canvas, z
from PIL import ImageDraw

BASE = "https://www.weather.gov"
UA = {"User-Agent": "korf-graphics (weather graphics script)"}
LEVEL_COL = {0: "#ededed", 1: "#f4f257", 2: "#fa9441", 3: "#e52207", 4: "#be32d0"}
LEVEL_WORD = {0: "NONE", 1: "LEVEL 1", 2: "LEVEL 2", 3: "LEVEL 3", 4: "LEVEL 4"}
HIDDEN = ("Thunderstorm Wind Risk", "Hail Risk")  # the NWS page hides these two rows too

# pixel = a * lon + b / pixel_y = c * lat + d for the 1024x768 GHWO images; map_box = the part with the map (no header/legend)
CALIB = {
    "akq": {"size": (1024, 768), "ax": 177.85, "bx": 14204.33, "ay": -206.27, "by": 8095.72, "map_box": (0, 70, 1024, 700)},
}
VIEWS = {"akq": (-79.9, -74.1, 35.94, 39.0)}  # the area the office's own GHWO map shows (west, east, south, north)
GRID = (33.6, 39.7, -84.2, -75.0)  # lat0, lat1, lon0, lon1 of the level grid
STEP = 0.04


def _get(url, as_bytes=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        data = r.read()
    return data if as_bytes else json.loads(data)


def _level_of(color, legend=None):
    c = (color or "").lower()
    for lv, h in LEVEL_COL.items():
        if c == h:
            return lv
    return 0


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower().replace("risk", "")).strip("_")


def _hue_level(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if s < 0.5 or v < 0.35:
        return 0
    deg = h * 360
    if 45 <= deg <= 70:
        return 1
    if 15 <= deg < 45:
        return 2
    if deg < 15 or deg > 340:
        return 3
    if 250 <= deg <= 330:
        return 4
    return 0


def classify(img, wfo):
    """GHWO picture -> {"lat","lon","val"} level grid (val 0-4), or None when this office isn't calibrated."""
    import numpy as np
    cal = CALIB.get(wfo)
    if not cal:
        return None
    img = img.convert("RGB")
    if img.size != tuple(cal["size"]):
        img = img.resize(cal["size"])
    a = np.asarray(img).astype(np.float32) / 255
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    d = mx - mn
    s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    hue = np.zeros_like(mx)
    dd = np.maximum(d, 1e-6)
    hue = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) * 60
    lvl = np.zeros(mx.shape, dtype=np.int8)
    ok = (s >= 0.5) & (mx >= 0.35)
    lvl[ok & (hue >= 45) & (hue <= 70)] = 1
    lvl[ok & (hue >= 15) & (hue < 45)] = 2
    lvl[ok & ((hue < 15) | (hue > 340))] = 3
    lvl[ok & (hue >= 250) & (hue <= 330)] = 4
    x0, y0, x1, y1 = cal["map_box"]
    box = np.zeros(lvl.shape, bool)
    box[y0:y1, x0:x1] = True
    lvl = np.where(box, lvl, 0)
    lats = np.arange(GRID[0], GRID[1] + 1e-9, STEP)
    lons = np.arange(GRID[2], GRID[3] + 1e-9, STEP)
    LO, LA = np.meshgrid(lons, lats)
    px = np.round(cal["ax"] * LO + cal["bx"]).astype(int)
    py = np.round(cal["ay"] * LA + cal["by"]).astype(int)
    val = np.zeros(LO.shape, dtype=np.float32)
    inside = (px >= 3) & (px < cal["size"][0] - 3) & (py >= 3) & (py < cal["size"][1] - 3)
    # majority vote over a 7x7 window so JPEG fuzz and thin outlines don't make speckles
    pxc, pyc = px[inside], py[inside]
    stack = []
    for lv in (1, 2, 3, 4):
        m = (lvl == lv).astype(np.float32)
        k = np.zeros_like(m)
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                k += np.roll(np.roll(m, dy, 0), dx, 1)
        stack.append(k[pyc, pxc])
    st = np.stack(stack)  # (4, n)
    best = st.argmax(0) + 1
    ok2 = st.max(0) >= 20  # of 49 pixels
    out = np.zeros(pxc.shape, dtype=np.float32)
    out[ok2] = best[ok2]
    val[inside] = out
    return {"lat": LA.astype(np.float32), "lon": LO.astype(np.float32), "val": val}


def parse(chick, legend, wfo):
    """chicklet.json + legend.json -> {"wfo","gen","hazards":[{"name","desc","periods":[{"n","date","start","level","color"}]}], "legend":{name:{lvl:def}}}"""
    leg = {}
    for h in legend.get("hazards", []):
        leg[h["name"]] = {int(k): v.get("definition", "") for k, v in h.get("category", {}).items()}
    hz = []
    for h in chick.get("hazards", []):
        per = []
        for key, p in sorted(h.get("periods", {}).items(), key=lambda kv: int(re.sub(r"\D", "", kv[0]) or 0)):
            per.append({"n": int(re.sub(r"\D", "", key) or 0), "date": p.get("date", ""), "start": p.get("validStartTime", ""),
                        "level": _level_of(p.get("color")), "color": p.get("color"), "image": p.get("imagePath")})
        hz.append({"name": h["name"], "desc": re.sub(r"<[^>]+>", "", h.get("description", "")), "periods": per})
    return {"wfo": wfo, "gen": chick.get("generation_time_LT") or chick.get("generation_time", ""), "hazards": hz, "legend": leg, "grids": {}}


def fetch(cfg, cache_dir, now_utc, debug=False):
    wfo = (cfg.get("ghwo_wfo") or "akq").lower()
    try:
        chick = _get(f"{BASE}/source/{wfo}/ghwo/chicklet.json")
        legend = _get(f"{BASE}/source/{wfo}/ghwo/legend.json")
    except Exception as e:
        print(f"  ! GHWO fetch failed for {wfo}: {e}")
        return None
    gd = parse(chick, legend, wfo)
    if wfo not in CALIB:
        print(f"  - GHWO {wfo}: no map calibration yet, only the 7-day grid will be made")
        return gd
    from PIL import Image
    want = [(h, p) for h in gd["hazards"] if h["name"] not in (cfg.get("ghwo_hidden") or HIDDEN) for p in h["periods"] if p["level"] > 0 and p.get("image")]
    want.sort(key=lambda hp: (-hp[1]["level"], hp[1]["n"]))
    for h, p in want[: int(cfg.get("ghwo_max_maps", 12))]:
        try:
            img = Image.open(io.BytesIO(_get(BASE + p["image"], True)))
            gd["grids"][(h["name"], p["n"])] = classify(img, wfo)
        except Exception as e:
            print(f"  ! GHWO image {p['image']}: {e}")
    return gd


def sample(now_utc, tz):
    import numpy as np
    base = now_utc.astimezone(tz)
    names = ["Severe Thunderstorm Risk", "Tornado Risk", "Lightning Risk", "Excessive Rainfall Risk", "Wind Risk", "Frost/Freeze Risk",
             "Fog Risk", "Fire Weather Risk", "Extreme Cold Risk", "Winter Storm Risk", "Coastal Flood Risk", "High Surf Risk"]
    plan = {"Frost/Freeze Risk": [0, 2, 3, 2, 0, 1, 0], "Wind Risk": [1, 1, 0, 0, 0, 0, 0], "Coastal Flood Risk": [0, 0, 1, 2, 1, 0, 0],
            "High Surf Risk": [0, 1, 2, 2, 1, 0, 0], "Fog Risk": [0, 1, 0, 0, 0, 0, 0], "Excessive Rainfall Risk": [0, 0, 0, 1, 0, 0, 0]}
    defs = {1: "Some risk is possible.", 2: "A moderate risk is expected.", 3: "A significant risk is expected.", 4: "An extreme risk is expected."}
    hz, leg = [], {}
    for nm in names:
        lv = plan.get(nm, [0] * 7)
        per = []
        for i in range(7):
            d = base + __import__("datetime").timedelta(days=i)
            per.append({"n": i + 1, "date": d.strftime("%A, %B %d, %Y"), "start": "07:00AM", "level": lv[i], "color": LEVEL_COL[lv[i]], "image": None})
        hz.append({"name": nm, "desc": "", "periods": per})
        leg[nm] = {0: "No risk", 1: f"{nm.replace(' Risk', '')}: " + defs[1], 2: defs[2], 3: defs[3], 4: defs[4]}
    leg["Frost/Freeze Risk"] = {0: "No frost or freeze risk", 1: "Patchy frost possible.", 2: "Frost likely; a freeze is possible in colder spots.",
                                3: "A widespread freeze is likely.", 4: "A hard freeze is expected."}
    LA, LO = np.meshgrid(np.arange(GRID[0], GRID[1] + 1e-9, STEP), np.arange(GRID[2], GRID[3] + 1e-9, STEP), indexing="ij")
    gd = {"wfo": "akq", "gen": base.strftime("%Y-%m-%dT%H:%M:%S"), "hazards": hz, "legend": leg, "grids": {}}
    for h in hz:
        for p in h["periods"]:
            if p["level"] and h["name"] not in HIDDEN:
                val = np.zeros(LA.shape, np.float32)
                cx = -77.6 + 0.2 * p["n"]
                cy = 37.0
                dist = np.hypot((LO - cx) * 0.8, LA - cy)
                val[dist < 1.6] = 1
                if p["level"] >= 2:
                    val[dist < 1.0] = 2
                if p["level"] >= 3:
                    val[dist < 0.5] = 3
                val[LO > -75.9] = 0
                gd["grids"][(h["name"], p["n"])] = {"lat": LA.astype(np.float32), "lon": LO.astype(np.float32), "val": val}
    return gd


# ------------------------------------------------------------------ graphics
def _day_lbl(date):
    try:
        d = datetime.strptime(date, "%A, %B %d, %Y")
        return d.strftime("%a").upper(), f"{d.month}/{d.day}"
    except Exception:
        return date[:3].upper(), ""


def _title(name):
    return name.replace(" Risk", "").replace("Frost/Freeze", "Frost & Freeze")


def _visible(gd, cfg):
    hidden = cfg.get("ghwo_hidden") or HIDDEN
    return [h for h in gd["hazards"] if h["name"] not in hidden]


def week_graphic(gd, pkg, cfg):
    rows = _visible(gd, cfg)
    if cfg.get("ghwo_hide_empty", True):
        rows = [h for h in rows if any(p["level"] for p in h["periods"])]
    cv = Canvas(cfg)
    cv.header("HAZARDOUS WEATHER OUTLOOK", f"7-DAY HAZARD RISKS  ·  NWS {gd['wfo'].upper()}")
    x0, y0 = cv.M, 205 if not cv.tall else 225
    W = cv.W - 2 * cv.M
    if not rows:
        cv.rect(x0, y0, W, 220, C["panel"], r=18, outline=(255, 255, 255, 235), ow=3)
        cv.text(x0 + W / 2, y0 + 110, "NO HAZARD RISKS THIS WEEK", 44, "bold", anchor="mm", maxw=W - 60)
        cv.footer(pkg, source="NWS Graphical Hazardous Weather Outlook")
        return cv
    ndays = max(len(h["periods"]) for h in rows)
    labw = min(360, W * 0.3)
    top = rows[0]["periods"]
    gap = 8
    cw = (W - labw - 10) / ndays
    avail = cv.H - y0 - 150
    rh = min(104, (avail - 70) / max(1, len(rows)))
    for i, p in enumerate(top):
        wd, md = _day_lbl(p["date"])
        cx = x0 + labw + 10 + i * cw + cw / 2
        cv.text(cx, y0 + 4, wd, 24, "bold", anchor="mt")
        cv.text(cx, y0 + 34, md, 18, "medium", C["muted"], anchor="mt")
    ry = y0 + 70
    for h in rows:
        cv.rect(x0, ry, W, rh - gap / 2, C["panel"], r=12)
        cv.text(x0 + 18, ry + (rh - gap / 2) / 2, _title(h["name"]).upper(), 22, "bold", anchor="lm", maxw=labw - 24)
        for i, p in enumerate(h["periods"]):
            cx = x0 + labw + 10 + i * cw
            col = _rgb(LEVEL_COL[p["level"]])
            cv.rect(cx + 4, ry + 6, cw - 8, rh - gap / 2 - 12, (*col, 255 if p["level"] else 70), r=9)
            if p["level"]:
                cv.text(cx + cw / 2, ry + (rh - gap / 2) / 2, str(p["level"]), 28, "bold", (20, 28, 46) if p["level"] < 3 else (255, 255, 255), anchor="mm")
        ry += rh
    ly = ry + 14
    chips = [(_rgb(LEVEL_COL[i]), f"LEVEL {i}") for i in (1, 2, 3, 4)]
    _legend_chips(cv, x0, ly, W, chips)
    if not cv.minimal:
        best = max(rows, key=lambda h: max(p["level"] for p in h["periods"]))
        lv = max(p["level"] for p in best["periods"])
        txt = gd["legend"].get(best["name"], {}).get(lv, "")
        if txt:
            cv.paragraph(x0, ly + 46, f"Highest: {_title(best['name'])} (level {lv}). {txt}", 22, "regular", W, max_lines=2, lh=1.25)
    cv.footer(pkg, source="NWS Graphical Hazardous Weather Outlook")
    return cv


def map_graphic(gd, hz, per, grid, pkg, cfg):
    import numpy as np
    name = hz["name"]
    lat, lon, val = grid["lat"], grid["lon"], grid["val"]
    cs = _counties()
    best = {"VA": (0, 0), "NC": (0, 0)}
    for k in cs:
        j = int(round((k["lat"] - lat[0, 0]) / STEP))
        i = int(round((k["lon"] - lon[0, 0]) / STEP))
        if 0 <= j < val.shape[0] and 0 <= i < val.shape[1] and val[j, i] > 0:
            lv, n = best[k["st"]]
            v = int(val[j, i])
            best[k["st"]] = (max(lv, v), n + 1) if v >= lv else (lv, n)
    top = max(best["VA"][0], best["NC"][0], per["level"])
    cards = []
    for st in ("VA", "NC"):
        lv, n = best[st]
        if lv:
            cards.append({"st": st, "value": LEVEL_WORD[lv] + " OF 4", "col": _rgb(LEVEL_COL[lv]), "detail": f"{n} COUNTIES AT THIS LEVEL"})
        else:
            cards.append({"st": st, "value": "NO RISK", "col": None, "detail": "NOTHING IN THE OUTLOOK FOR " + st})
    wd, md = _day_lbl(per["date"])
    meaning = gd["legend"].get(name, {}).get(top, "")
    cv = Canvas(cfg)
    cv.header(_title(name).upper() + " OUTLOOK", f"{wd} {md}  ·  DAY {per['n']}  ·  NWS {gd['wfo'].upper()}")
    (mx, my, mw, mh), pbox = cv.split()
    bins = [(0.5, _rgb(LEVEL_COL[1])), (1.5, _rgb(LEVEL_COL[2])), (2.5, _rgb(LEVEL_COL[3])), (3.5, _rgb(LEVEL_COL[4]))]
    from .ndfdmap import _cell_painter
    paint = _cell_painter({"lat": lat, "lon": lon, "val": np.where(val > 0, val, np.nan)}, bins, alpha=255, smooth=0)
    _paste_rounded(cv, stencil_map(mw, mh, cfg, painter=paint, alpha=0.96,
                                       view=cfg.get("ghwo_view") or VIEWS.get(gd["wfo"])), mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    chips = [(_rgb(LEVEL_COL[i]), f"LEVEL {i}") for i in (1, 2, 3, 4)]
    _panel(cv, pbox, "HIGHEST RISK IN EACH STATE", cards, meaning, lambda c, x, y, w: _legend_chips(c, x, y, w, chips))
    cv.footer(pkg, source="NWS Graphical Hazardous Weather Outlook")
    return cv


def hazout_graphics(pkg, cfg):
    gd = pkg.get("_ghwo")
    if not gd or not gd.get("hazards"):
        return None
    out = [("hazout_week", week_graphic(gd, pkg, cfg))]
    byname = {h["name"]: h for h in gd["hazards"]}
    for (name, n), grid in gd["grids"].items():
        if grid is None:
            continue
        per = next((p for p in byname[name]["periods"] if p["n"] == n), None)
        if per:
            out.append((f"hazout_{_slug(name)}_day{n}", map_graphic(gd, byname[name], per, grid, pkg, cfg)))
    return out
