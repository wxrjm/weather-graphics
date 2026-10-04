"""CPC U.S. Hazards Outlook graphics (Days 8-14, plus Days 3-7 when that layer has data) on a wide
eastern-U.S. map from the Great Lakes to the Gulf. One graphic with all hazards except rain, and a
separate heavy-rain / flooding graphic.

Data (free, no key): NOAA mapservices CPC Weather Hazards service
  https://mapservices.weather.noaa.gov/vector/rest/services/hazards/cpc_weather_hazards/MapServer
Each polygon has a 'label' (e.g. "Heavy Precipitation", "Much Below Normal Temperatures") and its own
start/end dates. Layers are found by name ("8-14 Day Temperature Outlook", ...).
Basemap: wxgfx/data/us_east_base.json (Natural Earth land & lakes, US Census states; offline).
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from . import outlooks
from .alertmap import STENCIL, STENCIL_EDGE, _paste_rounded, draw_cities
from .outlookmap import _legend_chips, _side, _view
from .theme import Canvas, z

SERVICE = f"{outlooks.MAPSERVICES}/hazards/cpc_weather_hazards/MapServer"
QUERY_BBOX = (-105.0, 20.0, -60.0, 53.0)
EAST_VIEW = (-95.0, -71.0, 24.5, 47.8)  # Great Lakes to the Gulf coast
EAST_CITIES = [  # (name, lat, lon, tier)
    ("Norfolk", 36.85, -76.29, 1), ("Chicago", 41.88, -87.63, 1), ("Detroit", 42.33, -83.05, 1),
    ("Atlanta", 33.75, -84.39, 1), ("New York", 40.71, -74.01, 1), ("Washington", 38.90, -77.04, 1),
    ("Nashville", 36.16, -86.78, 1), ("Charlotte", 35.23, -80.84, 1), ("New Orleans", 29.95, -90.07, 1),
    ("Jacksonville", 30.33, -81.66, 1), ("St. Louis", 38.63, -90.20, 1), ("Pittsburgh", 40.44, -80.00, 1),
    ("Raleigh", 35.78, -78.64, 2), ("Richmond", 37.54, -77.44, 2), ("Philadelphia", 39.95, -75.17, 2),
    ("Cleveland", 41.50, -81.69, 2), ("Buffalo", 42.89, -78.88, 2), ("Indianapolis", 39.77, -86.16, 2),
    ("Louisville", 38.25, -85.76, 2), ("Memphis", 35.15, -90.05, 2), ("Birmingham", 33.52, -86.80, 2),
    ("Tampa", 27.95, -82.46, 2), ("Miami", 25.76, -80.19, 2), ("Columbia", 34.00, -81.03, 2),
    ("Knoxville", 35.96, -83.92, 2), ("Charleston", 32.78, -79.93, 2), ("Mobile", 30.69, -88.04, 2),
    ("Jackson", 32.30, -90.18, 2), ("Cincinnati", 39.10, -84.51, 2), ("Milwaukee", 43.04, -87.91, 2),
    ("Boston", 42.36, -71.06, 2), ("Houston", 29.76, -95.37, 2),
]

# keyword (lowercase) -> (short legend name, color, rain?) ; colors from CPC's own map service renderer
HAZARDS = [
    ("flooding occurring", "Flooding Occurring", (76, 0, 115), True),
    ("flooding likely", "Flooding Likely", (223, 115, 255), True),
    ("flooding possible", "Flooding Possible", (232, 190, 255), True),
    ("heavy precip", "Heavy Precipitation", (0, 230, 169), True),
    ("heavy rain", "Heavy Rain", (38, 115, 0), True),
    ("heavy snow", "Heavy Snow", (0, 132, 168), False),
    ("heavy ice", "Heavy Ice", (255, 0, 197), False),
    ("freezing rain", "Freezing Rain", (255, 0, 197), False),
    ("severe", "Severe Weather", (230, 152, 0), False),
    ("excessive heat", "Excessive Heat", (168, 0, 0), False),
    ("hazardous heat", "Hazardous Heat", (168, 0, 0), False),
    ("much above", "Much Above Normal Temps", (255, 0, 0), False),
    ("much below", "Much Below Normal Temps", (0, 92, 230), False),
    ("hazardous cold", "Hazardous Cold", (0, 92, 230), False),
    ("frost", "Frost / Freeze", (197, 0, 255), False),
    ("freeze", "Frost / Freeze", (197, 0, 255), False),
    ("high wind", "High Winds", (205, 170, 102), False),
    ("wave", "Significant Waves", (255, 211, 127), False),
    ("wildfire", "Critical Wildfire Risk", (60, 60, 60), False),
    ("rapid onset drought", "Rapid Onset Drought", (168, 112, 0), False),
    ("drought", "Severe Drought", (115, 38, 0), False),
]
RAIN_MEANING = {
    "Flooding Occurring": "Flooding is occurring or imminent.",
    "Flooding Likely": "Flooding is likely.",
    "Flooding Possible": "Flooding is possible.",
    "Heavy Precipitation": "A heavy precipitation event is favored.",
    "Heavy Rain": "A heavy rain event is favored.",
}

_BASE = None


def base():
    global _BASE
    if _BASE is None:
        _BASE = json.loads((Path(__file__).parent / "data" / "us_east_base.json").read_text(encoding="utf-8"))
    return _BASE


def classify(label):
    low = (label or "").lower()
    for key, name, col, rain in HAZARDS:
        if key in low:
            return name, col, rain
    return (label or "Hazard").title(), (150, 150, 170), False


def _date(v):
    if isinstance(v, (int, float)) and v > 1e11:
        return datetime.fromtimestamp(v / 1000, timezone.utc).date()
    t = outlooks._parse_time(v) if v else None
    return t.date() if t else None


# ------------------------------------------------------------------ fetch
def fetch_all(cfg, debug=False):
    fx = outlooks.Fetcher(cfg["user_agent"], debug)
    res = {"periods": {}, "errors": []}
    w, s, e, n = QUERY_BBOX
    for period in cfg.get("cpc_periods", ["8-14", "3-7"]):
        feats = []
        for kind in ("temperature", "precipitation", "wildfire|drought"):
            try:
                lid, name = fx.find_layer(SERVICE, lambda nm: period in nm.replace("–", "-") and re.search(kind, nm))
                if lid is None:
                    continue
                data = fx.json(f"{SERVICE}/{lid}/query", {
                    "where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": 4326, "f": "geojson",
                    "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects"})
                got = data.get("features", [])
                fx.log(f"CPC {period} {kind}: layer '{name}', {len(got)} features")
                for f in got:
                    p = f.get("properties") or {}
                    fx.log("  ", {k: v for k, v in p.items() if not k.startswith(("st_", "idp_ingest"))})
                    polys = outlooks.polys_of(f.get("geometry"))
                    if not polys:
                        continue
                    label = p.get("label") or p.get("hazard") or p.get("Hazards") or ""
                    d0, d1 = _date(p.get("start_date") or p.get("start_dt2")), _date(p.get("end_date") or p.get("end_dt2"))
                    feats.append({"label": label, "start": d0.isoformat() if d0 else None,
                                  "end": d1.isoformat() if d1 else None, "polys": polys})
            except Exception as ex:
                res["errors"].append(f"CPC {period} {kind}: {ex}")
        res["periods"][period] = feats
    for e_ in res["errors"]:
        print(f"  ! {e_}")
    return res


# ------------------------------------------------------------------ map
def draw_east_map(items, pw, ph, cfg, view=None):
    """items: [(rgb, polys)] drawn in order (bigger areas first so small ones stay visible)."""
    W_, H_ = z(pw), z(ph)
    w, e, s, n = _view(pw, ph, tuple(view or cfg.get("cpc_view") or EAST_VIEW))
    proj = lambda x, y: ((x - w) / (e - w) * W_, (n - y) / (n - s) * H_)
    b = base()
    lay = Image.new("RGBA", (W_, H_), (17, 27, 47, 255))
    d = ImageDraw.Draw(lay, "RGBA")
    land = Image.new("L", (W_, H_), 0)
    ld = ImageDraw.Draw(land)

    def poly_fill(dr, p, fill, hole=(0, 0, 0, 0)):
        dr.polygon([proj(x, y) for x, y in p[0]], fill=fill)
        for h in p[1:]:
            dr.polygon([proj(x, y) for x, y in h], fill=hole)

    for p in b["land"]:  # Canada / Mexico / islands (dimmer than the U.S.)
        poly_fill(d, p, (29, 41, 63, 255), (17, 27, 47, 255))
        poly_fill(ld, p, 255, 0)
    for st in b["states"]:
        for p in st["polys"]:
            poly_fill(d, p, STENCIL, (17, 27, 47, 255))
    for p in b["lakes"]:
        poly_fill(d, p, (17, 27, 47, 255))
        poly_fill(ld, p, 0, 0)
    ov = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    for col, polys in items:
        one = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        od = ImageDraw.Draw(one)
        for p in polys:
            poly_fill(od, p, (*col, 175))
        ov.alpha_composite(one)
    a = ov.getchannel("A")
    ov.putalpha(Image.composite(a, a.point(lambda v: int(v * 0.4)), land))
    lay.alpha_composite(ov)
    d = ImageDraw.Draw(lay, "RGBA")
    for st in b["states"]:
        for p in st["polys"]:
            pts = [proj(x, y) for x, y in p[0]]
            d.line(pts + [pts[0]], fill=(*STENCIL_EDGE[:3], 255), width=max(1, z(1.3)), joint="curve")
    for col, polys in items:  # hazard outlines
        for p in polys:
            pts = [proj(x, y) for x, y, *_ in p[0]]
            d.line(pts + [pts[0]], fill=(*col, 255), width=z(2.6), joint="curve")
    draw_cities(d, proj, W_, H_, cfg, bottom_pad=80, cities=cfg.get("cpc_cities") or EAST_CITIES)
    return lay


def _span(a, b):
    if not a:
        return ""
    a, b = datetime.fromisoformat(a).date(), (datetime.fromisoformat(b).date() if b else None)
    s = f"{a.strftime('%b').upper()} {a.day}"
    if b and b != a:
        s += f"–{b.day}" if b.month == a.month else f"–{b.strftime('%b').upper()} {b.day}"
    return s


def hazard_graphic(period, feats, pkg, cfg, rain):
    feats = [f for f in feats if classify(f["label"])[2] == rain]
    area = lambda f: sum(abs(sum(x0 * y1 - x1 * y0 for (x0, y0, *_), (x1, y1, *_) in zip(p[0], p[0][1:]))) for p in f["polys"])
    feats = sorted(feats, key=area, reverse=True)
    cv = Canvas(cfg)
    starts = sorted(f["start"] for f in feats if f.get("start"))
    ends = sorted(f["end"] for f in feats if f.get("end"))
    when = _span(starts[0], ends[-1]) if starts and ends else ""
    title = "HEAVY RAIN OUTLOOK" if rain else "WEATHER HAZARDS OUTLOOK"
    subtitle = f"DAYS {period}" + (f"  ·  {when}" if when else "") + "  ·  CLIMATE PREDICTION CENTER"
    cv.header(title, subtitle)
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    items = [(classify(f["label"])[1], f["polys"]) for f in feats]
    _paste_rounded(cv, draw_east_map(items, mw, mh, cfg), mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    seen, chips = set(), []
    for f in sorted(feats, key=lambda f: classify(f["label"])[0]):
        name, col, _ = classify(f["label"])
        if name not in seen:
            seen.add(name)
            chips.append((col, name.upper()))
    _legend_chips(cv, mx + 16, my + mh - 60, chips or [((70, 86, 112), "NO HAZARDS HIGHLIGHTED")], mw - 32)
    loc = cfg["location"]
    here = [f for f in feats if outlooks.contains(f["polys"], loc["lon"], loc["lat"])]
    if here:
        top = here[-1]  # smallest (most specific) area covering us
        name, col, _ = classify(top["label"])
        head, head_col = name.upper(), col
        dates = _span(top.get("start"), top.get("end"))
        if rain:
            meaning = f"{RAIN_MEANING.get(name, name + '.')} CPC includes the Hampton Roads area" + (f", {dates}." if dates else ".")
        else:
            meaning = f"CPC highlights {name.lower()} for the Hampton Roads area" + (f", {dates}." if dates else ".")
    else:
        head, head_col = "NO HAZARD", (70, 86, 112)
        meaning = ("No heavy rain or flooding hazard is highlighted for the Hampton Roads area in this period."
                   if rain else "No weather hazards are highlighted for the Hampton Roads area in this period.")
    rows = []
    for f in sorted(feats, key=lambda f: (f.get("start") or "", classify(f["label"])[0])):
        name, col, _ = classify(f["label"])
        rows.append((name, col, _span(f.get("start"), f.get("end")) or f"DAYS {period}"))
    if not rows:
        rows.append(("None on the map", None, "—"))
    _side(cv, px, py, pw_, ph_, head_col, cfg["location"].get("area", "HAMPTON ROADS AREA").upper(), head, meaning,
          rows[:12], "HAZARDS ON THE MAP")
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NOAA Climate Prediction Center"
    cv.footer(pkg, source=src)
    from . import fullscreen
    legend = chips or [((70, 86, 112), "NO HAZARDS HIGHLIGHTED")]
    fullscreen.attach(cv, title=title, subtitle=subtitle,
                      map_fn=lambda pw, ph, view: draw_east_map(items, pw, ph, cfg, view=view),
                      box=tuple(cfg.get("cpc_view") or EAST_VIEW),
                      head_label=cfg["location"].get("area", "HAMPTON ROADS AREA").upper(), head_value=head,
                      head_col=head_col, meaning=meaning, rows=rows,
                      overlay=lambda c, x, y, mw_: _legend_chips(c, x, y, legend, mw_), source=src)
    return cv


def cpc_graphics(pkg, cfg):
    data = pkg.get("_cpc")
    if not data:
        return None
    out = []
    for period, feats in sorted((data.get("periods") or {}).items(), key=lambda kv: -int(kv[0].split("-")[0])):
        tag = period.replace("-", "_")
        other = [f for f in feats if not classify(f["label"])[2]]
        rain = [f for f in feats if classify(f["label"])[2]]
        if other or (period == "8-14" and cfg.get("cpc_show_empty", True)):
            out.append((f"cpc_hazards_d{tag}", hazard_graphic(period, feats, pkg, cfg, rain=False)))
        else:
            print(f"  - cpc_hazards_d{tag}: no hazards in the map area, skipped")
        if rain or cfg.get("cpc_rain_always", False):
            out.append((f"cpc_heavy_rain_d{tag}", hazard_graphic(period, feats, pkg, cfg, rain=True)))
        else:
            print(f"  - cpc_heavy_rain_d{tag}: no heavy rain area, skipped")
    return out or None


def sample(now):
    """Made-up Days 8-14 hazards for offline testing."""
    from datetime import timedelta
    from .sample import _ellipse
    d0 = now.date() + timedelta(days=7)
    iso = lambda k: (d0 + timedelta(days=k)).isoformat()
    return {"periods": {"8-14": [
        {"label": "Much Below Normal Temperatures", "start": iso(1), "end": iso(4),
         "polys": _ellipse(-86.0, 41.5, 7.5, 4.0, 0.2, wobble=0.06)},
        {"label": "High Winds", "start": iso(0), "end": iso(2), "polys": _ellipse(-78.5, 42.8, 4.5, 2.0, 0.3, wobble=0.05)},
        {"label": "Heavy Snow", "start": iso(2), "end": iso(3), "polys": _ellipse(-80.5, 43.0, 3.0, 1.2, 0.3, wobble=0.05)},
        {"label": "Heavy Precipitation", "start": iso(0), "end": iso(2),
         "polys": _ellipse(-78.0, 35.5, 5.5, 2.4, 0.55, wobble=0.07)},
        {"label": "Flooding Possible", "start": iso(1), "end": iso(5), "polys": _ellipse(-80.5, 34.5, 2.2, 1.2, 0.5)},
    ]}, "errors": []}
