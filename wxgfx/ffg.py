"""Flash Flood Guidance (FFG) maps: how much rain in 1 / 3 / 6 hours it would take to start flooding small
streams. Lower numbers = wetter ground / more flood-prone.

Data (free, no key): NWS River Forecast Centers' gridded FFG, combined CONUS 5-km grid, updated hourly:
  https://mapservices.weather.noaa.gov/raster/rest/services/precip/rfc_gridded_ffg/MapServer
The service hands out an image, so we export it over VA/NC (lat/lon projection), read every pixel's class from
the service's own legend colors, and redraw it in our colors on the county map. Local values come from the
same pixels.
"""
import base64
import io
import json
import urllib.parse
import urllib.request

from PIL import Image

from . import fullscreen
from .alertmap import _paste_rounded
from .outlookmap import POINTS, VIEW_BOX, _side, draw_map
from .theme import C, Canvas, z

SERVICE = "https://mapservices.weather.noaa.gov/raster/rest/services/precip/rfc_gridded_ffg/MapServer"
GROUP = {1: 0, 3: 4, 6: 8, 12: 12, 24: 16}  # hours -> group layer id (image sublayer = id + 3)
BBOX = (-85.5, 32.5, -73.0, 40.8)  # w, s, e, n (VA + NC + margin)
SIZE = (1250, 830)  # ~1 px per km-ish; the source grid is 5 km
# class index (0 = lowest) -> (label, value for "<", our color). Low guidance = flood-prone = hot colors.
CLASSES = [
    ("< 0.25\"", 0.0, (170, 0, 170)), ("0.25–0.5\"", 0.25, (220, 0, 60)), ("0.5–0.75\"", 0.5, (255, 40, 0)),
    ("0.75–1\"", 0.75, (255, 120, 0)), ("1–1.5\"", 1.0, (255, 190, 0)), ("1.5–2\"", 1.5, (240, 240, 60)),
    ("2–2.5\"", 2.0, (150, 220, 80)), ("2.5–3\"", 2.5, (60, 190, 110)), ("3–4\"", 3.0, (40, 160, 190)),
    ("4–5\"", 4.0, (50, 110, 220)), ("5\"+", 5.0, (100, 70, 190)),
]


def _label_class(label):
    """Map a legend label ('1 to 1.5 inches', 'Less than 0.25 inches', 'Greater than equal to 5') to 0..10."""
    s = label.lower()
    if "less" in s:
        return 0
    if "greater" in s:
        return 10
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*to", s)
    if not m:
        return None
    lo = float(m.group(1))
    return next((i for i, c in enumerate(CLASSES) if abs(c[1] - lo) < 1e-6), None)


def _get(url, ua, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=60) as r:
        b = r.read()
    return b if raw else json.loads(b.decode("utf-8", "replace"))


def legend_colors(ua, image_layer):
    """{rgb: class index} from the service legend swatches."""
    lg = _get(f"{SERVICE}/legend?f=json", ua)
    out = {}
    for lay in lg.get("layers", []):
        if lay.get("layerId") != image_layer:
            continue
        for e in lay.get("legend", []):
            k = _label_class(e.get("label", ""))
            if k is None or not e.get("imageData"):
                continue
            sw = Image.open(io.BytesIO(base64.b64decode(e["imageData"]))).convert("RGBA")
            px = sw.getpixel((sw.width // 2, sw.height // 2))
            if px[3] > 0:
                out[px[:3]] = k
    return out


def classify(img, colors):
    """Exported RGBA image -> 'L' image of class index + 1 (0 = no data), by nearest legend color."""
    pal = list(colors.items())
    cache = {}
    src = img.convert("RGBA")
    out = Image.new("L", src.size, 0)
    sp, op = src.load(), out.load()
    for y in range(src.height):
        for x in range(src.width):
            r, g, b, a = sp[x, y]
            if a < 128:
                continue
            key = (r, g, b)
            k = cache.get(key)
            if k is None:
                k = min(pal, key=lambda pc: (pc[0][0] - r) ** 2 + (pc[0][1] - g) ** 2 + (pc[0][2] - b) ** 2)[1]
                cache[key] = k
            op[x, y] = k + 1
    return out


def fetch(cfg, debug=False):
    ua = cfg["user_agent"]
    w, s, e, n = BBOX
    res = {"bbox": BBOX, "grids": {}, "errors": []}
    for hrs in cfg.get("ffg_hours", [1, 3, 6]):
        lid = GROUP.get(int(hrs))
        if lid is None:
            continue
        try:
            colors = legend_colors(ua, lid + 3)
            q = urllib.parse.urlencode({"bbox": f"{w},{s},{e},{n}", "bboxSR": 4326, "imageSR": 4326,
                                        "size": f"{SIZE[0]},{SIZE[1]}", "layers": f"show:{lid + 3}", "format": "png32",
                                        "transparent": "true", "dpi": 96, "f": "image"})
            png = _get(f"{SERVICE}/export?{q}", ua, raw=True)
            img = Image.open(io.BytesIO(png))
            grid = classify(img, colors)
            if debug:
                print(f"   [ffg] {hrs}h: {len(colors)} legend colors, image {img.size}, "
                      f"classes present {sorted(set(grid.getdata()))}")
            res["grids"][int(hrs)] = grid
        except Exception as ex:
            res["errors"].append(f"FFG {hrs}h: {ex}")
            print(f"  ! flash flood guidance {hrs}h: {ex}")
    return res


# ------------------------------------------------------------------ drawing
def _rgb_grid(grid):
    """class grid -> RGBA image in our colors."""
    lut = [(0, 0, 0, 0)] + [(*c[2], 255) for c in CLASSES]
    out = Image.new("RGBA", grid.size)
    out.putdata([lut[v] if v < len(lut) else (0, 0, 0, 0) for v in grid.getdata()])
    return out


def _painter(grid, bbox):
    """Smoothly upscale the class grid (0 = no data, k+1 = class k) so FFG cells blend into soft
    contours instead of stair-stepped blocks."""
    from .outlookmap import smooth_classes, composite_at
    w, s, e, n = bbox
    cols = [c[2] for c in CLASSES]

    def paint(d, proj):
        x0, y0 = proj(w, n)
        x1, y1 = proj(e, s)
        tw, th = int(round(x1 - x0)), int(round(y1 - y0))
        if tw <= 0 or th <= 0:
            return
        cell = tw / max(1, grid.width)
        im = smooth_classes(grid, (tw, th), cols, blur=max(2.0, cell * 1.2))
        composite_at(d._image, im, x0, y0)  # d draws on draw_map's overlay layer
    return paint


def class_at(grid, bbox, lon, lat):
    w, s, e, n = bbox
    if not (w <= lon <= e and s <= lat <= n):
        return None
    x = min(grid.width - 1, int((lon - w) / (e - w) * grid.width))
    y = min(grid.height - 1, int((n - lat) / (n - s) * grid.height))
    v = grid.getpixel((x, y))
    return v - 1 if v else None


def _bar(cv, x, y, maxw):
    bw = min(maxw, 980)
    cv.rect(x, y, bw, 62, (13, 21, 38, 225), r=10)
    seg = (bw - 30) / len(CLASSES)
    for i, c in enumerate(CLASSES):
        cv.rect(x + 15 + i * seg, y + 9, seg - 2, 20, (*c[2], 255), r=3)
        cv.text(x + 15 + i * seg + (seg - 2) / 2, y + 50, c[0].replace("\"", "").replace("< ", "<"), 14, "bold",
                anchor="ms")


def ffg_graphic(hrs, grid, bbox, pkg, cfg):
    cv = Canvas(cfg)
    title = "FLASH FLOOD GUIDANCE"
    subtitle = f"RAIN NEEDED IN {hrs} HOUR{'S' if hrs > 1 else ''} TO FLOOD SMALL STREAMS  ·  NWS RIVER FORECAST CENTERS"
    cv.header(title, subtitle)
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    paint = _painter(grid, bbox)
    _paste_rounded(cv, draw_map([], mw, mh, cfg, outline=False, painter=paint, water_alpha=0), mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    _bar(cv, mx + 16, my + mh - 74, mw - 32)
    rows, local = [], []
    for name, la, lo in cfg.get("outlook_points") or POINTS:
        kk = class_at(grid, bbox, lo, la)
        rows.append((name, CLASSES[kk][2] if kk is not None else None, CLASSES[kk][0] if kk is not None else "N/A"))
        if kk is not None:
            local.append((kk, name))
    hrs_txt = f"{hrs} hour{'s' if hrs > 1 else ''}"
    if not local:
        val, col = "N/A", (70, 86, 112)
        meaning = "Flash flood guidance isn't available for the Hampton Roads area right now."
    else:  # headline = the most flood-prone spot (lowest guidance) in the local list
        k = min(local)[0]
        where = [n for kk, n in local if kk == k]
        lab, _, col = CLASSES[k]
        val = lab
        amt = lab.replace("–", " to ").replace('"+', '" or more').replace("< ", "less than ")
        place = where[0] if len(where) == 1 else ", ".join(where[:-1]) + " and " + where[-1]
        lead = 'Less than 0.25" of rain' if k == 0 else f"As little as {amt} of rain"
        meaning = (f"{lead} in {hrs_txt} could start flooding small streams around {place}."
                   + (" The ground is wet, so it won't take much." if k <= 3 else ""))
    area = cfg["location"].get("area", "Hampton Roads Area").upper()
    area = f"{area}  ·  LOWEST"
    _side(cv, px, py, pw_, ph_, col, area, val, meaning, rows, f"{hrs}-HOUR GUIDANCE  ·  LOCAL")
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NWS River Forecast Centers (Flash Flood Guidance)"
    cv.footer(pkg, source=src)
    fullscreen.attach(cv, title=title, subtitle=subtitle,
                      map_fn=lambda pw, ph, view: draw_map([], pw, ph, cfg, outline=False, painter=paint, view=view, water_alpha=0),
                      box=tuple(cfg.get("outlook_view") or VIEW_BOX), head_label=area, head_value=val, head_col=col,
                      meaning=meaning, rows=rows, overlay=lambda c, x, y, mw_: _bar(c, x, y, mw_), source=src)
    return cv


def ffg_graphics(pkg, cfg):
    data = pkg.get("_ffg")
    if not data or not data.get("grids"):
        return None
    out = []
    for hrs, grid in sorted(data["grids"].items(), key=lambda kv: int(kv[0])):
        out.append((f"ffg_{int(hrs)}hr", ffg_graphic(int(hrs), grid, tuple(data["bbox"]), pkg, cfg)))
    return out


def sample():
    """Fake exported images built from fake legend colors, run through the same decoding as live data."""
    import math
    import random
    rnd = random.Random(7)
    legend = {(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)): k for k in range(len(CLASSES))}
    inv = {k: c for c, k in legend.items()}
    w, s, e, n = BBOX
    res = {"bbox": BBOX, "grids": {}, "errors": []}
    for hrs, base in ((1, 1.2), (3, 1.9), (6, 2.6)):
        img = Image.new("RGBA", (500, 332), (0, 0, 0, 0))
        p = img.load()
        for y in range(img.height):
            for x in range(img.width):
                lon, lat = w + (x + 0.5) / img.width * (e - w), n - (y + 0.5) / img.height * (n - s)
                if lon > -75.4 and lat < 38.6:  # ocean: no data
                    continue
                v = base + 0.9 * math.sin(lon * 1.7) * math.cos(lat * 2.1) + 0.012 * (lat - 36) * (lon + 85) \
                    - 1.1 * math.exp(-((lon + 76.6) ** 2 + (lat - 36.9) ** 2) / 0.35)  # wet spot west of Norfolk
                k = max(0, min(10, next((i for i in range(10, -1, -1) if v >= CLASSES[i][1]), 0)))
                p[x, y] = (*inv[k], 255)
        res["grids"][hrs] = classify(img, legend)
    return res
