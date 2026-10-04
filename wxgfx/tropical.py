"""Tropical threat data for the 'Tropical' graphics folder (all free, no keys):

  * NHC CurrentStorms.json                      active storms, position, intensity, motion, bin (AT1..AT5)
  * NHC tropical MapServer (mapservices.weather.noaa.gov/tropical/.../NHC_tropical_weather)
        <bin> Forecast Points / Track / Cone / Watch-Warning / Past Points
        <bin> Earliest Reasonable / Most Likely Arrival Time (of tropical-storm-force winds)
        Probabilistic Winds 34 / 50 / 64 kts     (wind speed probabilities, 5-day cumulative)
        Image_Inun_<bin>                         Potential Storm Surge Flooding (ft above ground)
  * api.weather.gov  HLS (Hurricane Local Statement) and TCV (watch/warning + threat breakdown) from NWS Wakefield
  * NWPS SWPV2 (Sewells Point)                  official surge+tide forecast and historic crests

The Tropical folder is only made when a storm threatens the area (cone, 34-kt wind chances, tropical
watches/warnings, or distance), or always with "tropical_always": true.
"""
import base64
import io
import json
import math
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from PIL import Image

from . import outlooks

NHC_STORMS = "https://www.nhc.noaa.gov/CurrentStorms.json"
NHC = "https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/NHC_tropical_weather/MapServer"
NWS = "https://api.weather.gov"
NWPS = "https://api.water.noaa.gov/nwps/v1/gauges"
BOX = (-100.0, 10.0, -55.0, 50.0)  # query box (w, s, e, n): Gulf + western Atlantic
SURGE_BOX = (-77.6, 35.5, -75.2, 38.2)  # w, s, e, n for the surge image
STORM_NAMES = [  # (date, name) for labeling Sewells Point historic crests
    ("1933-08-23", "1933 Hurricane"), ("1936-09-18", "1936 Hurricane"), ("1962-03-07", "Ash Wednesday Storm"),
    ("2003-09-18", "Hurricane Isabel"), ("2009-11-12", "Nor'Ida"), ("2011-08-27", "Hurricane Irene"),
    ("2016-10-09", "Hurricane Matthew"), ("1998-02-04", "Feb 1998 Nor'easter"), ("2006-11-22", "Nov 2006 Nor'easter"),
    ("2009-11-13", "Nor'Ida"), ("2019-09-06", "Hurricane Dorian"), ("2023-09-23", "Ophelia"),
]
LOCAL_POINTS = [("Norfolk", 36.85, -76.29), ("VA Beach", 36.84, -75.98), ("Chesapeake", 36.72, -76.24),
                ("Hampton", 37.03, -76.35), ("Williamsburg", 37.27, -76.71), ("Eastern Shore", 37.55, -75.82),
                ("Eliz. City", 36.30, -76.22), ("Outer Banks", 35.95, -75.62), ("Richmond", 37.54, -77.44),
                ("Ocean City", 38.34, -75.08)]


def _get(url, ua, accept="application/json", raw=False, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read()
    return b if raw else json.loads(b.decode("utf-8", "replace"))


def _num(x):
    try:
        return float(re.findall(r"-?\d+(?:\.\d+)?", str(x))[0])
    except (IndexError, TypeError, ValueError):
        return None


def miles(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 7917.5 * math.asin(math.sqrt(max(0, a)))


def bearing(lat1, lon1, lat2, lon2):
    """Compass direction from point 1 to point 2."""
    p = math.pi / 180
    y = math.sin((lon2 - lon1) * p) * math.cos(lat2 * p)
    x = math.cos(lat1 * p) * math.sin(lat2 * p) - math.sin(lat1 * p) * math.cos(lat2 * p) * math.cos((lon2 - lon1) * p)
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    return ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"][
        int((deg + 11.25) // 22.5) % 16]


def saffir(kt):
    for c, lim in ((5, 137), (4, 113), (3, 96), (2, 83), (1, 64)):
        if (kt or 0) >= lim:
            return c
    return 0


def kind_from(kt, cls=""):
    cls = (cls or "").upper()
    if cls in ("PTC", "PC", "PT"):
        return {"PTC": "Potential Tropical Cyclone", "PC": "Post-Tropical Cyclone", "PT": "Post-Tropical Cyclone"}[cls]
    if (kt or 0) >= 64:
        return "Hurricane"
    if (kt or 0) >= 34:
        return "Subtropical Storm" if cls.startswith("S") else "Tropical Storm"
    return "Subtropical Depression" if cls.startswith("S") else "Tropical Depression"


# ------------------------------------------------------------------ NHC map layers
class _Svc:
    def __init__(self, ua, debug=False):
        self.ua, self.debug = ua, debug
        self._layers = None

    def layers(self):
        if self._layers is None:
            self._layers = _get(f"{NHC}/layers?f=json", self.ua).get("layers", [])
        return self._layers

    def find(self, *words):
        for l in self.layers():
            n = l["name"].lower()
            if all(w.lower() in n for w in words):
                return l["id"]
        return None

    def query(self, lid, box=BOX):
        w, s, e, n = box
        q = urllib.parse.urlencode({"where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": 4326,
                                    "f": "geojson", "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope",
                                    "inSR": 4326, "spatialRel": "esriSpatialRelIntersects"})
        d = _get(f"{NHC}/{lid}/query?{q}", self.ua)
        if self.debug:
            fs = d.get("features", [])
            print(f"   [tropical] layer {lid}: {len(fs)} features",
                  (fs[0].get("properties") if fs else ""))
        return d.get("features", [])

    def legend(self, lid):
        lg = _get(f"{NHC}/legend?f=json", self.ua)
        for lay in lg.get("layers", []):
            if lay.get("layerId") == lid:
                out = []
                for e in lay.get("legend", []):
                    if not e.get("imageData"):
                        continue
                    sw = Image.open(io.BytesIO(base64.b64decode(e["imageData"]))).convert("RGBA")
                    px = sw.getpixel((sw.width // 2, sw.height // 2))
                    if px[3] > 0:
                        out.append((px[:3], e.get("label", "")))
                return out
        return []

    def export(self, lid, box, size):
        w, s, e, n = box
        q = urllib.parse.urlencode({"bbox": f"{w},{s},{e},{n}", "bboxSR": 4326, "imageSR": 4326,
                                    "size": f"{size[0]},{size[1]}", "layers": f"show:{lid}", "format": "png32",
                                    "transparent": "true", "f": "image"})
        return Image.open(io.BytesIO(_get(f"{NHC}/export?{q}", self.ua, raw=True))).convert("RGBA")


def _pts(feats):
    out = []
    for f in feats:
        p = {k.lower(): v for k, v in (f.get("properties") or {}).items()}
        g = f.get("geometry") or {}
        if g.get("type") != "Point":
            continue
        lon, lat = g["coordinates"][:2]
        out.append({"lat": lat, "lon": lon, "tau": _num(p.get("tau")), "wind_kt": _num(p.get("maxwind")),
                    "gust_kt": _num(p.get("gust")), "mslp": _num(p.get("mslp")), "label": p.get("datelbl") or "",
                    "full": p.get("fldatelbl") or "", "valid": p.get("validtime") or "", "type": p.get("dvlbl") or "",
                    "adv": p.get("advisnum"), "advdate": p.get("advdate") or ""})
    return out


def _lines(feats):
    out = []
    for f in feats:
        g = f.get("geometry") or {}
        props = {k.lower(): v for k, v in (f.get("properties") or {}).items()}
        cs = g.get("coordinates") or []
        if g.get("type") == "LineString":
            cs = [cs]
        elif g.get("type") != "MultiLineString":
            continue
        for c in cs:
            out.append({"coords": [pt[:2] for pt in c], "props": props})
    return out


def fetch_storm_layers(svc, bin_):
    res = {}
    for key, words in (("points", (bin_, "forecast points")), ("track", (bin_, "forecast track")),
                       ("cone", (bin_, "forecast cone")), ("ww", (bin_, "watch-warning")),
                       ("past", (bin_, "past points")), ("earliest", (bin_, "earliest reasonable")),
                       ("likely", (bin_, "most likely arrival"))):
        lid = svc.find(*words)
        if lid is None:
            continue
        try:
            fs = svc.query(lid)
        except Exception as e:
            print(f"  ! NHC {key}: {e}")
            continue
        if key in ("points", "past"):
            res[key] = sorted(_pts(fs), key=lambda p: p["tau"] if p["tau"] is not None else 0)
        elif key == "cone":
            res[key] = [pp for f in fs for pp in outlooks.polys_of(f.get("geometry"))]
        else:
            res[key] = _lines(fs)
    return res


def fetch_probs(svc):
    out = {}
    for kt in (34, 50, 64):
        lid = svc.find("probabilistic winds", f"{kt} kt")
        if lid is None:
            continue
        try:
            fs = svc.query(lid, (-85, 25, -65, 45))
        except Exception as e:
            print(f"  ! NHC wind probabilities {kt} kt: {e}")
            continue
        bands = []
        for f in fs:
            v = _num((f.get("properties") or {}).get("percentage"))
            polys = outlooks.polys_of(f.get("geometry"))
            if v is not None and polys:
                bands.append({"pct": v, "polys": polys})
        out[kt] = sorted(bands, key=lambda b: b["pct"])
    return out


def prob_at(bands, lon, lat):
    best = 0
    for b in bands or []:
        if b["pct"] > best and outlooks.contains(b["polys"], lon, lat):
            best = b["pct"]
    return best


def fetch_surge(svc, bin_, size=(900, 1000)):
    lid = svc.find(f"image_inun_{bin_}".lower())
    if lid is None:
        return None
    img = svc.export(lid, SURGE_BOX, size)
    if img.getextrema()[3][1] == 0:  # fully transparent: no surge map issued
        return None
    return {"image": img, "legend": svc.legend(lid), "box": SURGE_BOX}


def surge_at(surge, lon, lat):
    if not surge:
        return None
    w, s, e, n = surge["box"]
    img = surge["image"]
    if not (w <= lon <= e and s <= lat <= n):
        return None
    best = None
    x0 = int((lon - w) / (e - w) * img.width)
    y0 = int((n - lat) / (n - s) * img.height)
    for dx in range(-6, 7, 2):  # look a few px around (points sit on the shoreline)
        for dy in range(-6, 7, 2):
            x, y = min(img.width - 1, max(0, x0 + dx)), min(img.height - 1, max(0, y0 + dy))
            r, g, b, a = img.getpixel((x, y))
            if a < 128 or not surge["legend"]:
                continue
            k = min(range(len(surge["legend"])), key=lambda i: sum((c1 - c2) ** 2 for c1, c2 in zip(surge["legend"][i][0], (r, g, b))))
            if best is None or k > best:
                best = k
    return surge["legend"][best][1] if best is not None else None


# ------------------------------------------------------------------ NWS text
def latest_product(ua, ptype, office):
    lst = _get(f"{NWS}/products/types/{ptype}/locations/{office}", ua, "application/ld+json")
    g = lst.get("@graph") or []
    if not g:
        return None, None
    p = _get(g[0]["@id"], ua, "application/ld+json")
    return p.get("productText") or "", p.get("issuanceTime")


THREATS = ["WIND", "SURGE", "FLOODING RAIN", "TORNADO"]
LEVELS = ["None", "Low", "Elevated", "Moderate", "High", "Extreme"]


def parse_tcv(text, zone):
    """Threat breakdown for one zone from a TCV:
    * WIND ... - LATEST LOCAL FORECAST: ... - Peak Wind Forecast: ... - THREAT TO LIFE AND PROPERTY ...: <threat>
    ... - POTENTIAL IMPACTS: <Limited|Significant|Extensive|Devastating>"""
    if not text:
        return None
    segs = re.split(r"\n\s*\$\$\s*\n", text)
    seg = next((s for s in segs if zone.upper() in s.upper().replace("-", "").replace(">", "")), None)
    if seg is None:
        seg = next((s for s in segs if zone[3:] in s and zone[:2] in s), None)
    if seg is None:
        return None
    name = ""
    m = re.search(r"\n([A-Z][A-Za-z/ .'-]+)-\n", seg)
    if m:
        name = m.group(1).strip()
    head = ""
    m = re.search(r"\n([A-Z][A-Z ]*(?:WARNING|WATCH)[^\n]*)", seg)
    if m:
        head = m.group(1).strip()
    out = {"zone": zone, "name": name, "headline": head, "threats": {}}
    for th in THREATS:
        m = re.search(rf"\*\s*{th}[A-Z]*:\s*\n(.*?)(?=\n\s*\*\s*[A-Z][A-Z ]+:|\Z)", seg, re.S)
        if not m:
            continue
        body = m.group(1)
        g = lambda pat: (re.search(pat, body, re.I | re.S).group(1).strip() if re.search(pat, body, re.I | re.S) else "")
        latest = g(r"LATEST LOCAL FORECAST:\s*(.*?)\n\s*-")
        peak = g(r"(?:Peak Wind Forecast|Peak Storm Surge Inundation|Peak Rainfall Amounts|Situation)[^:]*:\s*(.*?)\n")
        threat = g(r"THREAT TO LIFE AND PROPERTY[^:]*:\s*(.*?)\n")
        impacts = g(r"POTENTIAL IMPACTS:\s*(\w+)")
        plan = g(r"PLAN:\s*(.*?)(?:\n\s*-|\Z)")
        act = g(r"ACT:\s*(.*?)(?:\n\s*-|\Z)")
        out["threats"][th] = {"latest": re.sub(r"\s+", " ", latest), "peak": re.sub(r"\s+", " ", peak),
                              "threat": re.sub(r"\s+", " ", threat), "impacts": impacts.title(),
                              "plan": re.sub(r"\s+", " ", plan), "act": re.sub(r"\s+", " ", act)}
    return out


def parse_hls(text):
    """HLS -> {headline, new_info, changes, summary, situation, sections{WIND/SURGE/FLOODING RAIN/TORNADOES: text}}"""
    if not text:
        return None
    t = text.replace("\r", "")
    out = {"headline": "", "summary": "", "situation": "", "sections": {}, "issued": ""}
    m = re.search(r"\n(\d{3,4} [AP]M [A-Z]{3} \w{3} \w{3} \d{1,2} \d{4})", t)
    if m:
        out["issued"] = m.group(1)
    m = re.search(r"\n\s*\.\.\.(.*?)\.\.\.\s*\n", t, re.S)
    if m:
        out["headline"] = re.sub(r"\s+", " ", m.group(1)).strip()
    m = re.search(r"\*\s*STORM INFORMATION:\s*\n(.*?)(?=\n\s*SITUATION OVERVIEW|\n\s*\*\s*[A-Z]|\Z)", t, re.S)
    if m:
        out["summary"] = re.sub(r"\s+", " ", m.group(1)).strip(" -")
    m = re.search(r"SITUATION OVERVIEW\s*-*\s*\n(.*?)(?=\n\s*POTENTIAL IMPACTS|\n\s*PRECAUTIONARY|\Z)", t, re.S)
    if m:
        out["situation"] = re.sub(r"\s+", " ", m.group(1)).strip()
    for sec in ("WIND", "SURGE", "FLOODING RAIN", "TORNADOES"):
        m = re.search(rf"\*\s*{sec}:\s*\n(.*?)(?=\n\s*\*\s*[A-Z][A-Z ]+:|\n\s*PRECAUTIONARY|\n\s*NEXT UPDATE|\Z)", t, re.S)
        if m:
            out["sections"][sec] = re.sub(r"\s+", " ", m.group(1)).strip()
    return out


# ------------------------------------------------------------------ Sewells Point
def fetch_sewells(ua, tz):
    meta = _get(f"{NWPS}/SWPV2", ua)
    cats = (meta.get("flood") or {}).get("categories") or {}
    stages = {k: (cats.get(k) or {}).get("stage") for k in ("action", "minor", "moderate", "major")}
    hist = []
    for c in ((meta.get("flood") or {}).get("crests") or {}).get("historic") or []:
        t, v = c.get("occurredTime"), c.get("stage")
        if not t or v is None:
            continue
        d = t[:10]
        name = next((n for dd, n in STORM_NAMES if abs((datetime.fromisoformat(dd) - datetime.fromisoformat(d)).days) <= 2), None)
        hist.append({"date": d, "ft": float(v), "name": name or d[:4]})
    sf = _get(f"{NWPS}/SWPV2/stageflow", ua)
    pts = lambda blk: [(datetime.fromisoformat(d["validTime"].replace("Z", "+00:00")).astimezone(tz).isoformat(),
                        float(d["primary"])) for d in (blk or {}).get("data", []) if d.get("primary") not in (None, -999)]
    return {"stages": stages, "historic": sorted(hist, key=lambda h: -h["ft"])[:10], "forecast": pts(sf.get("forecast")),
            "observed": pts(sf.get("observed"))[-200:]}


# ------------------------------------------------------------------ main fetch
def choose_storm(storms, cfg):
    loc = cfg["location"]
    best = None
    for s in storms:
        if not str(s.get("id", "")).lower().startswith("al"):
            continue
        lat, lon = _num(s.get("latitudeNumeric")), _num(s.get("longitudeNumeric"))
        if lat is None or lon is None:
            continue
        d = miles(loc["lat"], loc["lon"], lat, lon)
        if best is None or d < best[0]:
            best = (d, s)
    return best


def fetch(cfg, now, debug=False):
    ua = cfg["user_agent"]
    tz = now.tzinfo
    out = {"active": False, "errors": []}
    try:
        storms = _get(NHC_STORMS, ua).get("activeStorms", [])
    except Exception as e:
        out["errors"].append(f"NHC storms: {e}")
        storms = []
    pick = choose_storm(storms, cfg)
    if pick:
        dist, s = pick
        bin_ = s.get("binNumber") or "AT1"
        kt = _num(s.get("intensity"))
        out["storm"] = {"name": s.get("name"), "id": s.get("id"), "bin": bin_, "class": s.get("classification"),
                        "kind": kind_from(kt, s.get("classification")), "wind_kt": kt, "pressure": _num(s.get("pressure")),
                        "lat": _num(s.get("latitudeNumeric")), "lon": _num(s.get("longitudeNumeric")),
                        "move_dir": s.get("movementDir"), "move_mph": _num(s.get("movementSpeed")),
                        "updated": s.get("lastUpdate"), "distance": dist}
        svc = _Svc(ua, debug)
        try:
            out.update(fetch_storm_layers(svc, bin_))
            out["probs"] = fetch_probs(svc)
            out["surge"] = fetch_surge(svc, bin_)
        except Exception as e:
            out["errors"].append(f"NHC map service: {e}")
    office, zone = cfg.get("cwf_office", "AKQ"), cfg.get("tropical_zone", "VAZ095")
    for pt, key in (("TCV", "tcv"), ("HLS", "hls")):
        try:
            txt, issued = latest_product(ua, pt, office)
            if txt and issued and datetime.fromisoformat(issued.replace("Z", "+00:00")) > now - timedelta(hours=18):
                out[key] = parse_tcv(txt, zone) if pt == "TCV" else parse_hls(txt)
        except Exception as e:
            out["errors"].append(f"{pt}: {e}")
    try:
        out["sewells"] = fetch_sewells(ua, tz)
    except Exception as e:
        out["errors"].append(f"Sewells Point: {e}")
    out["active"] = is_threat(out, cfg)
    for e in out["errors"]:
        print(f"  ! tropical {e}")
    return out


def is_threat(t, cfg):
    if cfg.get("tropical_always"):
        return bool(t.get("storm"))
    if t.get("tcv") or t.get("hls"):
        return True
    s = t.get("storm")
    if not s:
        return False
    loc = cfg["location"]
    if any(outlooks.contains([p], loc["lon"], loc["lat"]) for p in t.get("cone") or []):
        return True
    if prob_at((t.get("probs") or {}).get(34), loc["lon"], loc["lat"]) >= cfg.get("tropical_min_prob", 5):
        return True
    near = min([miles(loc["lat"], loc["lon"], p["lat"], p["lon"]) for p in t.get("points") or []] + [s["distance"]])
    return near <= cfg.get("tropical_threat_miles", 400)


def closest_approach(points, lat, lon, start):
    """Interpolate the forecast track hourly -> (time, miles, direction from Norfolk, wind_kt)."""
    pts = [p for p in points if p.get("tau") is not None]
    if len(pts) < 2:
        return None
    best = None
    for a, b in zip(pts, pts[1:]):
        steps = max(1, int(b["tau"] - a["tau"]))
        for i in range(steps + 1):
            f = i / steps
            la, lo = a["lat"] + (b["lat"] - a["lat"]) * f, a["lon"] + (b["lon"] - a["lon"]) * f
            d = miles(lat, lon, la, lo)
            if best is None or d < best[1]:
                kt = (a["wind_kt"] or 0) + ((b["wind_kt"] or 0) - (a["wind_kt"] or 0)) * f
                best = (start + timedelta(hours=a["tau"] + (b["tau"] - a["tau"]) * f), d, bearing(lat, lon, la, lo), kt)
    return best


# ------------------------------------------------------------------ sample storm
def sample(now, cfg):
    """A made-up hurricane moving north off the Carolinas toward Hampton Roads."""
    tz = now.tzinfo
    base = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    track = [(0, 30.2, -76.8, 105), (12, 31.9, -76.6, 100), (24, 33.6, -76.3, 95), (36, 35.3, -75.9, 85),
             (48, 36.8, -75.6, 75), (60, 38.4, -74.8, 60), (72, 40.0, -73.6, 50), (96, 43.5, -70.0, 40), (120, 47.0, -65.0, 35)]
    pts = []
    for tau, la, lo, kt in track:
        t = (base + timedelta(hours=tau)).astimezone(tz)
        pts.append({"lat": la, "lon": lo, "tau": tau, "wind_kt": kt, "gust_kt": kt + 20, "mslp": 1010 - kt * 0.9,
                    "label": t.strftime("%a %-I %p"), "full": "", "valid": t.isoformat(), "type": "H" if kt >= 64 else "S",
                    "adv": "18", "advdate": ""})
    past = [{"lat": 30.2 - 0.8 * i, "lon": -76.8 - 0.5 * i, "tau": -6 * i, "wind_kt": max(35, 105 - 8 * i), "label": "",
             "gust_kt": None, "mslp": None, "full": "", "valid": "", "type": "", "adv": "", "advdate": ""} for i in range(1, 9)][::-1]
    cone = []
    left, right = [], []
    for tau, la, lo, kt in track[:8]:
        r = 0.15 + tau / 120 * 2.6
        left.append([lo - r, la + r * 0.15])
        right.append([lo + r, la - r * 0.15])
    ring = left + right[::-1] + [left[0]]
    cone = [[ring]]
    ellipse = lambda cx, cy, rx, ry, rot=0.5: [[[cx + rx * math.cos(a) * math.cos(rot) - ry * math.sin(a) * math.sin(rot),
                                                  cy + rx * math.cos(a) * math.sin(rot) + ry * math.sin(a) * math.cos(rot)]
                                                 for a in [2 * math.pi * i / 60 for i in range(61)]]]
    probs = {34: [{"pct": p, "polys": [ellipse(-76.0, 36.2, 2.6 - i * 0.35, 3.4 - i * 0.45, 1.2)]}
                  for i, p in enumerate([10, 20, 30, 40, 50, 60, 70, 80, 90])],
             50: [{"pct": p, "polys": [ellipse(-75.8, 36.0, 1.6 - i * 0.3, 2.4 - i * 0.4, 1.2)]}
                  for i, p in enumerate([10, 20, 30, 40, 50])],
             64: [{"pct": p, "polys": [ellipse(-75.6, 35.8, 0.9 - i * 0.3, 1.5 - i * 0.45, 1.2)]}
                  for i, p in enumerate([5, 10, 20])]}
    iso = lambda h, w: [{"coords": [[-80.5 + i * 0.6, 34.0 + h * 0.055 + 0.1 * math.sin(i)] for i in range(12)],
                         "props": {"arrival_time": ((base + timedelta(hours=h)).astimezone(tz)).strftime("%a %-I %p")}}
                        for h in w]
    ww = [{"coords": [[-76.7, 34.6], [-76.0, 35.2], [-75.5, 35.7], [-75.7, 36.5]], "props": {"tcww": "HWR"}},
          {"coords": [[-75.7, 36.5], [-75.95, 36.9], [-75.6, 37.6], [-75.2, 38.4]], "props": {"tcww": "HWA"}},
          {"coords": [[-76.0, 37.0], [-76.3, 37.6], [-76.25, 38.2]], "props": {"tcww": "TWR"}}]
    legend = [((174, 220, 255), "Up to 3 ft above ground"), ((255, 230, 0), "Greater than 3 ft above ground"),
              ((255, 140, 0), "Greater than 6 ft above ground"), ((230, 0, 0), "Greater than 9 ft above ground")]
    img = Image.new("RGBA", (450, 500), (0, 0, 0, 0))
    w, s, e, n = SURGE_BOX
    from .alertinfo import counties
    land = Image.new("L", img.size, 0)
    from PIL import ImageDraw
    ld = ImageDraw.Draw(land)
    for c in counties().values():
        for p in c["polys"]:
            ld.polygon([((x - w) / (e - w) * img.width, (n - y) / (n - s) * img.height) for x, y in p[0]], fill=255)
    from PIL import ImageFilter
    shore = land.filter(ImageFilter.MaxFilter(1)).point(lambda v: 255 if v else 0)
    edge = Image.eval(land.filter(ImageFilter.MinFilter(9)), lambda v: 255 - v)
    band = Image.composite(Image.new("L", img.size, 255), Image.new("L", img.size, 0), land)
    band = Image.composite(band, Image.new("L", img.size, 0), edge)
    px, bp = img.load(), band.load()
    for yy in range(img.height):
        for xx in range(img.width):
            if bp[xx, yy]:
                lon, lat = w + xx / img.width * (e - w), n - yy / img.height * (n - s)
                d = math.hypot((lon + 76.1) * 0.8, lat - 36.95)
                k = 3 if d < 0.25 else 2 if d < 0.55 else 1 if d < 0.95 else 0
                px[xx, yy] = (*legend[k][0], 255)
    peak_t = base + timedelta(hours=46)
    fc = [((base + timedelta(hours=h)).astimezone(tz).isoformat(),
           round(2.2 + 1.35 * math.cos(2 * math.pi * (h - 46) / 12.42) + 3.2 * math.exp(-((h - 46) / 14) ** 2), 2))
          for h in range(0, 96)]
    obs = [((base - timedelta(hours=h)).astimezone(tz).isoformat(), round(2.0 + 1.3 * math.cos(2 * math.pi * (-h - 46) / 12.42) + 0.5, 2))
           for h in range(24, 0, -1)]
    tcv = {"zone": "VAZ095", "name": "Norfolk/Portsmouth", "headline": "HURRICANE WARNING IN EFFECT",
           "threats": {
               "WIND": {"latest": "Hurricane force winds", "peak": "60-75 mph with gusts to 95 mph",
                        "threat": "Potential for wind 74 to 110 mph", "impacts": "Extensive",
                        "plan": "Plan for extreme wind of equivalent CAT 1 or 2 hurricane force.",
                        "act": "Complete preparations to protect life and property. Move to safe shelter before the wind becomes hazardous."},
               "SURGE": {"latest": "Life-threatening storm surge possible", "peak": "4-7 ft above ground somewhere within surge prone areas",
                         "threat": "Potential for storm surge flooding greater than 6 feet above ground", "impacts": "Extensive",
                         "plan": "Plan for life-threatening storm surge flooding.",
                         "act": "Leave immediately if evacuation orders are given for your area."},
               "FLOODING RAIN": {"latest": "Flood Watch is in effect", "peak": "6-10 inches, locally higher",
                                 "threat": "Potential for major flooding rain", "impacts": "Extensive",
                                 "plan": "Emergency plans should include the potential for major flooding from heavy rain.",
                                 "act": "Heed any flood watches and warnings."},
               "TORNADO": {"latest": "", "peak": "", "threat": "Potential for a few tornadoes", "impacts": "Limited",
                           "plan": "Emergency plans should include the potential for a few tornadoes.",
                           "act": "Listen for tornado watches and warnings."}}}
    hls = {"headline": "HURRICANE WARNING IN EFFECT FOR NORFOLK, PORTSMOUTH, VIRGINIA BEACH AND CHESAPEAKE",
           "issued": now.strftime("%-I%M %p EDT %a %b %-d %Y").upper(),
           "summary": "About 420 miles south of Norfolk VA, 30.2N 76.8W. Storm intensity 120 mph. Movement north or 5 degrees at 14 mph.",
           "situation": "Hurricane SAMPLE is forecast to move north, passing just east of the Outer Banks Thursday and near the "
                        "mouth of the Chesapeake Bay Thursday night. Life-threatening storm surge, damaging hurricane-force winds and "
                        "flooding rain are expected across southeast Virginia and northeast North Carolina.",
           "sections": {"WIND": "Prepare for life-threatening wind having possible extensive impacts across coastal southeast Virginia.",
                        "SURGE": "Prepare for life-threatening surge having possible extensive impacts across shorelines of the lower Chesapeake Bay.",
                        "FLOODING RAIN": "Prepare for dangerous rainfall flooding having possible extensive impacts.",
                        "TORNADOES": "Prepare for a tornado event having possible limited impacts."}}
    storm = {"name": "SAMPLE", "id": "al992026", "bin": "AT1", "class": "HU", "kind": "Hurricane", "wind_kt": 105,
             "pressure": 958, "lat": 30.2, "lon": -76.8, "move_dir": "N", "move_mph": 14, "updated": base.isoformat(),
             "distance": miles(cfg["location"]["lat"], cfg["location"]["lon"], 30.2, -76.8)}
    return {"active": True, "storm": storm, "points": pts, "past": past, "cone": cone,
            "track": [{"coords": [[p["lon"], p["lat"]] for p in pts], "props": {}}], "ww": ww, "probs": probs,
            "earliest": iso(0, [12, 24, 36]), "likely": iso(0, [18, 30, 42]),
            "surge": {"image": img, "legend": legend, "box": SURGE_BOX}, "tcv": tcv, "hls": hls,
            "sewells": {"stages": {"action": 4.0, "minor": 4.5, "moderate": 5.5, "major": 6.5},
                        "historic": [{"date": "1933-08-23", "ft": 8.02, "name": "1933 Hurricane"},
                                     {"date": "2003-09-18", "ft": 7.89, "name": "Hurricane Isabel"},
                                     {"date": "2009-11-12", "ft": 7.74, "name": "Nor'Ida"},
                                     {"date": "2011-08-27", "ft": 7.67, "name": "Hurricane Irene"},
                                     {"date": "2016-10-09", "ft": 7.03, "name": "Hurricane Matthew"}],
                        "forecast": fc, "observed": obs},
            "sample_alerts": [
                {"event": "Storm Surge Warning", "color": "#B524F7", "ends_label": "", "affects_home": True,
                 "headline": "Storm Surge Warning issued by NWS Wakefield VA",
                 "fips": ["51710", "51810", "51740", "51650", "51700", "51735", "51131", "51001", "37053", "37055"]},
                {"event": "Hurricane Warning", "color": "#DC143C", "ends_label": "", "affects_home": True,
                 "headline": "Hurricane Warning issued by NWS Wakefield VA",
                 "fips": ["51710", "51810", "51550", "51740", "51650", "51700", "51735", "51131", "51001",
                          "37053", "37055", "37029", "37139", "37143"]},
                {"event": "Tropical Storm Warning", "color": "#B22222", "ends_label": "", "affects_home": False,
                 "headline": "Tropical Storm Warning issued by NWS Wakefield VA",
                 "fips": ["51800", "51093", "51175", "51620", "51199", "51830", "51095", "51073", "51115", "51181",
                          "37041", "37073", "37091"]}],
            "sample_wind": [{"time": (base + timedelta(hours=h)).astimezone(tz).isoformat(),
                             "wind": round(12 + 58 * math.exp(-((h - 46) / 13) ** 2)),
                             "gust": round(18 + 80 * math.exp(-((h - 46) / 12) ** 2)), "dir": "NE"} for h in range(1, 121)],
            "sample_outages": {"Virginia Beach": 61240, "Norfolk": 38410, "Chesapeake": 27150, "Portsmouth": 11980,
                               "Hampton": 9620, "Newport News": 8115, "Suffolk": 6430, "Currituck": 4210},
            "errors": [], "sample": True}
