"""SPC convective outlooks, WPC Excessive Rainfall Outlooks and WPC QPF -> normalized polygons.

All sources are free/keyless:
  * SPC:  https://www.spc.noaa.gov/products/outlook/dayNotlk_cat.lyr.geojson  (direct GeoJSON)
          fallback: NOAA mapservices SPC_wx_outlks MapServer
  * ERO:  WPC GeoJSON, fallback NOAA mapservices wpc_precip_hazards MapServer
  * QPF:  NOAA mapservices wpc_qpf MapServer
MapServer layer IDs change over time, so layers are found by NAME (e.g. "Day 1 ... Excessive").
Every normalized feature is {"level", "code", "name", "color", "polys"} (or "value" for QPF),
where polys = [[exterior_ring, hole, ...], ...] in lon/lat.
"""
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

MAPSERVICES = "https://mapservices.weather.noaa.gov/vector/rest/services"
SPC_GEOJSON = "https://www.spc.noaa.gov/products/outlook/day{d}otlk_cat.lyr.geojson"
SPC_SERVICE = f"{MAPSERVICES}/outlooks/SPC_wx_outlks/MapServer"
ERO_GEOJSON = "https://www.wpc.ncep.noaa.gov/exper/eromap/geojson/Day{d}_Latest.geojson"
ERO_SERVICE = f"{MAPSERVICES}/hazards/wpc_precip_hazards/MapServer"
QPF_SERVICE = f"{MAPSERVICES}/precip/wpc_qpf/MapServer"

SPC_CATS = [  # level, code, name, official SPC fill, meaning (SPC's own category descriptions)
    (0, "TSTM", "General Thunderstorms", "#C1E9C1", "Thunderstorms possible, but severe storms are not expected."),
    (1, "MRGL", "Marginal", "#66A366", "Isolated severe storms possible, limited in duration, coverage or intensity."),
    (2, "SLGT", "Slight", "#F6F67F", "Scattered severe storms possible. Short-lived, not widespread; a few intense storms possible."),
    (3, "ENH", "Enhanced", "#E6C27F", "Numerous severe storms possible. More persistent and widespread; a few intense."),
    (4, "MDT", "Moderate", "#E67F7F", "Widespread severe storms likely. Long-lived, widespread and intense."),
    (5, "HIGH", "High", "#FF7FFF", "Widespread severe storms expected. Long-lived, very widespread and particularly intense."),
]
ERO_CATS = [
    (1, "MRGL", "Marginal", "#6FCB6F", "Isolated flash flooding possible (at least a 5% chance)."),
    (2, "SLGT", "Slight", "#FFE44D", "Scattered flash flooding possible (at least a 15% chance)."),
    (3, "MDT", "Moderate", "#FF4040", "Numerous flash flooding events possible (at least a 40% chance)."),
    (4, "HIGH", "High", "#FF40FF", "Widespread flash flooding expected (at least a 70% chance)."),
]
QPF_COLORS = [  # threshold (in) -> fill; classic NWS precipitation scale (matches Ricky's reference bar)
    (0.01, (4, 233, 231)), (0.10, (1, 159, 244)), (0.25, (3, 0, 244)), (0.50, (2, 253, 2)),
    (0.75, (1, 197, 1)), (1.00, (0, 142, 0)), (1.50, (253, 248, 2)), (2.00, (229, 188, 0)),
    (2.50, (253, 149, 0)), (3.00, (253, 0, 0)), (4.00, (205, 1, 4)), (5.00, (167, 2, 0)),
    (6.00, (248, 0, 253)), (7.00, (208, 1, 215)), (8.00, (152, 84, 198)), (9.00, (113, 40, 155)),
    (10.00, (150, 150, 150)),
]
BBOX = (-85.5, 32.5, -73.0, 40.8)  # VA + NC (statewide map) plus margin


def qpf_color(v):
    col = QPF_COLORS[0][1]
    for t, c in QPF_COLORS:
        if v + 1e-6 >= t:
            col = c
    return col


# ------------------------------------------------------------------ http
class Fetcher:
    def __init__(self, user_agent, debug=False):
        self.ua, self.debug = user_agent, debug

    def json(self, url, params=None):
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    def log(self, *a):
        if self.debug:
            print("   [outlooks]", *a)

    def find_layer(self, service, want):
        """want(name_lower) -> bool. Returns (id, name) of the first matching leaf layer."""
        info = self.json(service, {"f": "json"})
        layers = info.get("layers", [])
        if self.debug:
            for l in layers:
                self.log(f"{service.rsplit('/services/', 1)[-1]}  layer {l['id']}: {l['name']}")
        for l in layers:
            if not l.get("subLayerIds") and want(l["name"].lower()):
                return l["id"], l["name"]
        return None, None

    def query(self, service, layer_id):
        w, s, e, n = BBOX
        return self.json(f"{service}/{layer_id}/query", {
            "where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": 4326, "f": "geojson",
            "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects"})


# ------------------------------------------------------------------ geometry
def polys_of(geom):
    if not geom:
        return []
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    if geom["type"] == "GeometryCollection":
        return [p for g in geom.get("geometries", []) for p in polys_of(g)]
    return []


def _in_ring(x, y, ring):
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][:2]
        xj, yj = ring[j][:2]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def contains(polys, lon, lat):
    return any(_in_ring(lon, lat, p[0]) and not any(_in_ring(lon, lat, h) for h in p[1:]) for p in polys)


def _in_view(polys):
    w, s, e, n = BBOX
    return any(w <= x <= e and s <= y <= n for p in polys for x, y, *_ in p[0][::max(1, len(p[0]) // 50)]) or \
        any(contains([p], (w + e) / 2, (s + n) / 2) for p in polys)


# ------------------------------------------------------------------ classification
def _category(props, cats):
    """Find the outlook category from whatever attribute names the source uses."""
    codes = {c[1]: c for c in cats}
    words = [(c[2].lower(), c) for c in cats]
    best = None
    for k, v in props.items():
        if not isinstance(v, str):
            continue
        s = v.strip()
        up = s.upper()
        hit = codes.get(up) or codes.get(up.split()[0] if up else "")
        if not hit:
            low = s.lower()
            if "general thunder" in low:
                hit = codes.get("TSTM")
            else:
                for w, c in words:
                    if re.search(rf"\b{w}\b", low) and ("risk" in low or "%" in low or len(low) < 40):
                        hit = c
                        break
        if hit and (best is None or hit[0] > best[0]):
            best = hit
    if best is None:  # numeric fallbacks (SPC DN: 2=TSTM..8=HIGH)
        dn = props.get("DN") or props.get("dn")
        if isinstance(dn, (int, float)) and cats is SPC_CATS and 2 <= dn <= 8:
            best = cats[int(dn) - 2 if dn <= 3 else int(dn) - 3 if dn != 8 else 5]
    return best


def _qpf_value(props):
    pri = sorted(props.items(), key=lambda kv: 0 if re.search(r"qpf|value|contour|amount|thresh", kv[0], re.I) else
                 1 if re.search(r"label|name", kv[0], re.I) else 2)
    for k, v in pri:
        if re.search(r"id$|objectid|shape|area|len", k, re.I):
            continue
        if isinstance(v, (int, float)) and 0 < v <= 40:
            return float(v)
        if isinstance(v, str):
            m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(?:\"|in|inch|inches)?\s*$", v)
            if m and 0 < float(m.group(1)) <= 40:
                return float(m.group(1))
    return None


def _times(props):
    out = {}
    for k, v in props.items():
        kl = k.lower()
        for tag in ("valid", "expire", "issue", "start", "end"):
            if tag in kl and v not in (None, ""):
                out.setdefault(tag, v)
    return out


def _parse_time(v):
    if isinstance(v, (int, float)) and v > 1e11:  # epoch ms (ArcGIS)
        return datetime.fromtimestamp(v / 1000, timezone.utc)
    if isinstance(v, str):
        s = v.strip()
        for fmt in ("%Y%m%d%H%M", "%Y%m%d%H"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def outlook_day_date(day, now_utc, props_times=None):
    """Convective/ERO days run 12Z->12Z. Use the product's VALID time when given."""
    t = _parse_time((props_times or {}).get("valid")) or _parse_time((props_times or {}).get("start"))
    if t:
        return t.date()
    return (now_utc - timedelta(hours=12)).date() + timedelta(days=day - 1)


# ------------------------------------------------------------------ product fetchers
def _normalize_cat(features, cats):
    out = []
    for f in features:
        props = f.get("properties") or {}
        c = _category(props, cats)
        polys = polys_of(f.get("geometry"))
        if not c or not polys or not _in_view(polys):
            continue
        out.append({"level": c[0], "code": c[1], "name": c[2], "color": c[3], "polys": polys,
                    "times": {k: str(v) for k, v in _times(props).items()}})
    out.sort(key=lambda x: x["level"])
    return out


def _day_match(name, day):
    m = re.search(r"day[s]?\s*(\d)(?:\s*[-–]\s*(\d))?", name)
    return bool(m) and int(m.group(1)) == day and not m.group(2)


def fetch_spc(fx, day):
    try:
        data = fx.json(SPC_GEOJSON.format(d=day))
        fx.log(f"SPC day {day}: {len(data.get('features', []))} features from spc.noaa.gov")
        if data.get("features"):
            fx.log("  sample properties:", data["features"][0].get("properties"))
        return _normalize_cat(data.get("features", []), SPC_CATS), "spc.noaa.gov"
    except Exception as e:
        fx.log(f"SPC GeoJSON failed ({e}); trying mapservices")
    lid, name = fx.find_layer(SPC_SERVICE, lambda n: _day_match(n, day) and ("categorical" in n or "convective" in n)
                              and not re.search(r"tornado|wind|hail|prob", n))
    if lid is None:
        raise RuntimeError(f"no SPC day {day} layer found")
    data = fx.query(SPC_SERVICE, lid)
    fx.log(f"SPC day {day}: layer '{name}', {len(data.get('features', []))} features")
    return _normalize_cat(data.get("features", []), SPC_CATS), "mapservices"


def fetch_ero(fx, day):
    try:
        data = fx.json(ERO_GEOJSON.format(d=day))
        fx.log(f"ERO day {day}: {len(data.get('features', []))} features from wpc GeoJSON")
        if data.get("features"):
            fx.log("  sample properties:", data["features"][0].get("properties"))
            return _normalize_cat(data["features"], ERO_CATS), "wpc"
    except Exception as e:
        fx.log(f"ERO GeoJSON failed ({e}); trying mapservices")
    lid, name = fx.find_layer(ERO_SERVICE, lambda n: _day_match(n, day) and ("excessive" in n or "ero" in n.split()))
    if lid is None:
        raise RuntimeError(f"no ERO day {day} layer found")
    data = fx.query(ERO_SERVICE, lid)
    feats = data.get("features", [])
    fx.log(f"ERO day {day}: layer '{name}', {len(feats)} features")
    if feats:
        fx.log("  sample properties:", feats[0].get("properties"))
    return _normalize_cat(feats, ERO_CATS), "mapservices"


def _period_match(name, period):
    """period like '1-7' or '1'."""
    a, _, b = period.partition("-")
    m = re.search(r"day[s]?\s*(\d)\s*(?:[-–]|to|through)\s*(\d)", name)
    if b:
        if m:
            return m.group(1) == a and m.group(2) == b
        # some layers are named by hours instead ("48 Hour QPF" = days 1-2)
        h = re.search(r"(\d{2,3})\s*[- ]?\s*(?:hr|hour)", name.lower())
        return a == "1" and bool(h) and int(h.group(1)) == 24 * int(b)
    return _day_match(name, int(a))


def fetch_qpf(fx, periods):
    last = None
    for period in periods:
        try:
            lid, name = fx.find_layer(QPF_SERVICE, lambda n: _period_match(n, period))
        except Exception as e:
            last = e
            break
        if lid is None:
            fx.log(f"QPF: no layer for days {period}")
            continue
        data = fx.query(QPF_SERVICE, lid)
        feats = data.get("features", [])
        fx.log(f"QPF days {period}: layer '{name}', {len(feats)} features")
        if feats:
            fx.log("  sample properties:", feats[0].get("properties"))
        out = []
        for f in feats:
            props = f.get("properties") or {}
            v = _qpf_value(props)
            polys = polys_of(f.get("geometry"))
            if v is None or not polys or not _in_view(polys):
                continue
            out.append({"value": v, "polys": polys, "times": {k: str(x) for k, x in _times(props).items()}})
        out.sort(key=lambda x: x["value"])
        return out, period
    raise RuntimeError(f"no WPC QPF layer found ({last or 'check --outlook-debug'})")


def fetch_all(cfg, debug=False):
    fx = Fetcher(cfg["user_agent"], debug)
    from . import spchazards
    res = {"spc": {}, "probs": {}, "ero": {}, "qpf": None, "errors": []}
    for d in cfg.get("spc_days", [1, 2, 3]):
        try:
            res["spc"][d], _ = fetch_spc(fx, d)
            res["probs"][d] = spchazards.fetch(fx, d)
        except Exception as e:
            res["errors"].append(f"SPC day {d}: {e}")
    for d in cfg.get("ero_days", [1, 2, 3]):
        try:
            res["ero"][d], _ = fetch_ero(fx, d)
        except Exception as e:
            res["errors"].append(f"ERO day {d}: {e}")
    if cfg.get("wpc_qpf", True):
        res["qpf_maps"] = {}
        for period in cfg.get("qpf_maps", ["1-2", "1-3", "1-5", "1-7"]):  # one map per period
            try:
                feats, got = fetch_qpf(fx, [period])
                res["qpf_maps"][got] = {"period": got, "features": feats}
            except Exception as e:
                res["errors"].append(f"WPC QPF days {period}: {e}")
    for e in res["errors"]:
        print(f"  ! {e}")
    return res
