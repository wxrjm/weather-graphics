"""Data for the 'extra' graphics. All sources are free and keyless; each is fetched independently
and a failure only skips the graphic that needs it.

  NOAA CO-OPS tides API      tides, water level, water temperature (Sewells Point 8638610)
  NOAA NWPS (water.noaa.gov) Sewells Point surge forecast + official flood stages (SWPV2)
  api.weather.gov products   CLI (ORF climate report), SRF (surf zone), CWF (coastal waters)
  api.weather.gov alerts     today's warning counts
  RCC ACIS                   ORF daily records, normals, first-freeze climatology
  EPA Envirofacts            hourly UV index forecast by ZIP
  aviationweather.gov        KORF METAR + TAF
  NHC / NOAA mapservices     active storms, 7-day outlook areas, forecast cones
"""
import json
import math
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

COOPS = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NWPS = "https://api.water.noaa.gov/nwps/v1/gauges"
NWS = "https://api.weather.gov"
ACIS = "https://data.rcc-acis.org/StnData"
EPA_UV = "https://data.epa.gov/efservice/getEnvirofactsUVHOURLY/ZIP/{zip}/JSON"
AWC = "https://aviationweather.gov/api/data"
AIRNOW_RA = "https://files.airnowtech.org/airnow/today/reportingarea.dat"
OM_AQ = "https://air-quality-api.open-meteo.com/v1/air-quality"
NHC_STORMS = "https://www.nhc.noaa.gov/CurrentStorms.json"
NHC_SERVICE = "https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/NHC_tropical_weather/MapServer"


class Http:
    def __init__(self, ua, cache_dir, debug=False):
        self.ua, self.debug = ua, debug
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)

    def get(self, url, params=None, accept="application/json", data=None, raw=False, timeout=40):
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": accept},
                                     data=json.dumps(data).encode() if data is not None else None)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        last = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    b = r.read().decode("utf-8", "replace")
                return b if raw else json.loads(b)
            except Exception as e:
                last = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"{url.split('?')[0]}: {last}")

    def cached(self, name, max_age_s, fn):
        p = self.cache / name
        if p.exists() and time.time() - p.stat().st_mtime < max_age_s:
            return json.loads(p.read_text())
        v = fn()
        p.write_text(json.dumps(v))
        return v

    def log(self, *a):
        if self.debug:
            print("   [extras]", *a)

    def product_texts(self, ptype, loc, n=6):
        """Latest n NWS text products of a type/location, newest first."""
        lst = self.get(f"{NWS}/products/types/{ptype}/locations/{loc}", accept="application/ld+json")
        out = []
        for item in (lst.get("@graph") or [])[:n]:
            p = self.get(item["@id"], accept="application/ld+json")
            out.append(p.get("productText") or "")
        return out


# ====================================================================== TIDES
def _coops(http, station, **params):
    q = {"station": station, "units": "english", "time_zone": "lst_ldt", "format": "json",
         "application": "wx_graphics_keyless"}
    q.update(params)
    return http.get(COOPS, q)


def _local(ts, tz):
    return datetime.strptime(ts, "%Y-%m-%d %H:%M").replace(tzinfo=tz)


def fetch_tides(http, cfg, now, tz):
    st = cfg.get("tide_station", "8638610")
    gauge = cfg.get("tide_nwps_gauge", "SWPV2")
    begin = now.strftime("%Y%m%d")
    rng = int(cfg.get("tide_hours", 72)) + 36  # from midnight today through the end of the chart window
    hilo = _coops(http, st, product="predictions", datum="MLLW", interval="hilo", begin_date=begin, range=rng)
    hourly = _coops(http, st, product="predictions", datum="MLLW", interval="h", begin_date=begin, range=rng)
    stages, fcst, nws_obs = None, None, None
    try:  # official NWS forecast + observations (same data as water.noaa.gov/gauges/SWPV2 "official" hydrograph)
        meta = http.get(f"{NWPS}/{gauge}")
        cats = (meta.get("flood") or {}).get("categories") or {}
        stages = {k: (cats.get(k) or {}).get("stage") for k in ("action", "minor", "moderate", "major")}
        stages = {k: v for k, v in stages.items() if isinstance(v, (int, float)) and v > -900} or None
        sf = http.get(f"{NWPS}/{gauge}/stageflow")
        pts = lambda blk: [(datetime.fromisoformat(d["validTime"].replace("Z", "+00:00")).astimezone(tz), float(d["primary"]))
                           for d in (blk or {}).get("data", []) if d.get("primary") not in (None, -999)]
        fcst, nws_obs = pts(sf.get("forecast")), pts(sf.get("observed"))
        http.log(f"NWPS {gauge}: {len(fcst)} forecast points (issued {(sf.get('forecast') or {}).get('issuedTime')}), "
                 f"{len(nws_obs)} observations")
    except Exception as e:
        http.log(f"NWPS {gauge}: {e}")
    obs = {}
    if not nws_obs:
        try:
            obs = _coops(http, st, product="water_level", datum="MLLW", date="recent")
        except Exception:
            obs = {}
    return parse_tides(hilo, hourly, obs, stages, fcst, cfg, now, tz, nws_obs=nws_obs)


def parse_tides(hilo, hourly, obs, stages, fcst, cfg, now, tz, nws_obs=None):
    default = cfg.get("tide_flood_stages") or {"action": 4.0, "minor": 4.5, "moderate": 5.5, "major": 6.5}
    stages = stages or default
    # window: exactly the NWS forecast period (no data beyond it); 48 h of predicted tide if the NWS forecast is missing
    fut = [f for f in (fcst or []) if f[0] >= now - timedelta(hours=1)]
    end = fut[-1][0] if len(fut) >= 6 else now + timedelta(hours=int(cfg.get("tide_hours_fallback", 48)))
    H = max(1, round((end - now).total_seconds() / 3600))
    astro = [{"time": _local(p["t"], tz), "ft": float(p["v"]), "type": p["type"]}
             for p in hilo.get("predictions", [])]
    astro = [t for t in astro if now - timedelta(hours=1) <= t["time"] <= end]
    win = [f for f in (fcst or []) if now - timedelta(hours=1) <= f[0] <= end]
    n_ex = H // 12 + 2
    if len(win) >= 6:  # high/low times + heights from the OFFICIAL NWS forecast (includes surge)
        ex = [{"time": t, "ft": round(v, 1), "type": "H"} for t, v in find_extrema(win, now, "H", n=n_ex)] + \
             [{"time": t, "ft": round(v, 1), "type": "L"} for t, v in find_extrema(win, now, "L", n=n_ex)]
        tides = sorted(ex, key=lambda x: x["time"])
        tide_src = "NWS"
    else:
        tides, tide_src = astro, "astronomical"
    curve = [(_local(p["t"], tz), float(p["v"])) for p in hourly.get("predictions", [])]
    curve = [c for c in curve if now - timedelta(hours=6) <= c[0] <= end]
    if nws_obs:
        observed = [o for o in nws_obs if now - timedelta(hours=6) <= o[0] <= now]
    else:
        observed = [(_local(p["t"], tz), float(p["v"])) for p in (obs.get("data") or []) if p.get("v") not in ("", None)]
        observed = [o for o in observed if o[0] >= now - timedelta(hours=6)][::5]  # 6-min -> 30-min
    # surge: observed minus predicted at the latest observation
    anomaly = None
    if observed and curve:
        t_last, v_last = observed[-1]
        near = min(curve, key=lambda c: abs((c[0] - t_last).total_seconds()))
        if abs((near[0] - t_last).total_seconds()) < 5400:
            anomaly = round(v_last - near[1], 1)
    use_fcst = bool(fcst)
    series = [f for f in (fcst or []) if now - timedelta(hours=1) <= f[0] <= end] or \
        [(t, v + (anomaly or 0)) for t, v in curve if t >= now]
    extension = []  # nothing is drawn past the end of the NWS forecast
    highs = [t for t in tides if t["type"] == "H"]
    peak = max(series, key=lambda s: s[1]) if series else None
    if tide_src == "NWS" and highs:  # same refined high tide as the table
        top = max((h for h in highs if h["time"] <= end and not h.get("src")), key=lambda h: h["ft"], default=None)
        if top:
            peak = (top["time"], top["ft"])
    return {"station_name": cfg.get("tide_station_name", "Sewells Point (Norfolk)"), "tides": tides, "curve": curve,
            "observed": observed, "forecast": series, "extension": extension, "hours": H,
            "forecast_end": series[-1][0] if (use_fcst and series) else None,
            "forecast_source": "NWS" if use_fcst else "astronomical+anomaly",
            "tide_times_source": tide_src,
            "anomaly": anomaly, "stages": stages, "peak": peak, "next_high": highs[0] if highs else None}


def flood_category(ft, stages):
    for k in ("major", "moderate", "minor", "action"):
        if stages.get(k) is not None and ft >= stages[k]:
            return k
    return None


def fetch_water_temp(http, cfg):
    for st in cfg.get("water_temp_stations", ["8638610", "8638901", "8639348"]):
        try:
            d = _coops(http, st, product="water_temperature", date="latest")
            v = d.get("data", [{}])[0].get("v")
            if v not in (None, ""):
                return round(float(v))
        except Exception:
            continue
    return None


# ====================================================================== HIGH TIDES AT SEVERAL SITES
DEFAULT_TIDE_SITES = [
    {"name": "Sewells Point", "nwps": "SWPV2", "coops": "8638610"},
    {"name": "Yorktown", "nwps": "YKTV2", "coops": "8637689"},
    {"name": "Jamestown", "nwps": "JSFV2", "search": "Jamestown"},
    {"name": "Lynnhaven Inlet", "nwps": "LHNV2", "search": "Lynnhaven"},
    {"name": "Nassawadox", "nwps": "NSWV2", "search": "Nassawadox"},
]
DEFAULT_TIDE_SITES_2 = [  # second high tide graphic
    {"name": "Kiptopeke", "nwps": "KPTV2", "coops": "8632200"},
    {"name": "Hudgins", "nwps": "WCKV2", "search": "Hudgins"},
    {"name": "Smithfield", "nwps": "SMSV2", "search": "Smithfield"},
    {"name": "Suffolk", "nwps": "NMDV2", "search": "Nansemond River at Suffolk"},
    {"name": "Money Point", "nwps": "MNPV2", "coops": "8639348"},
]


TIDAL_MAP_EXTRA = [  # more gauges for the tidal flooding map (positions refined from the NWS gauge data at run time)
    {"name": "CBBT", "nwps": "CHBV2", "lat": 36.967, "lon": -76.113},
    {"name": "Little Creek", "nwps": "LCEV2", "lat": 36.917, "lon": -76.176},
    {"name": "Rudee Inlet", "nwps": "RDIV2", "lat": 36.832, "lon": -75.968},
    {"name": "Cape Charles", "nwps": "CPCV2", "lat": 37.265, "lon": -76.024},
    {"name": "Windmill Point", "nwps": "WNDV2", "lat": 37.616, "lon": -76.290},
    {"name": "Hampton River", "nwps": "HMNV2", "lat": 37.020, "lon": -76.335},
    {"name": "Midtown Tunnel", "nwps": "EZMV2", "lat": 36.858, "lon": -76.315},
    {"name": "Grandy Village", "nwps": "ELGV2", "lat": 36.855, "lon": -76.255},
    {"name": "West Point", "nwps": "WSPV2", "lat": 37.532, "lon": -76.796},
    {"name": "Mobjack Bay", "nwps": "MJBV2", "lat": 37.350, "lon": -76.330},
    {"name": "Tangier Island", "nwps": "PRTV2", "lat": 37.826, "lon": -75.992},
    {"name": "Bailey Creek", "nwps": "BLYV2", "lat": 36.773, "lon": -76.297},
]
SITE_COORDS = {  # approximate gauge positions for the high tide sites (used if the gauge data has none)
    "SWPV2": (36.947, -76.330), "YKTV2": (37.227, -76.479), "JSFV2": (37.220, -76.791), "LHNV2": (36.905, -76.090),
    "NSWV2": (37.485, -75.950), "KPTV2": (37.166, -75.988), "WCKV2": (37.480, -76.320), "SMSV2": (36.982, -76.621),
    "NMDV2": (36.739, -76.583), "MNPV2": (36.778, -76.302),
}


def tidal_map_sites(cfg):
    seen, out = set(), []
    for s in (cfg.get("tide_sites") or DEFAULT_TIDE_SITES) + (cfg.get("tide_sites_2") or DEFAULT_TIDE_SITES_2) + \
            (cfg.get("tidal_map_sites") or TIDAL_MAP_EXTRA):
        key = s.get("nwps") or s["name"]
        if key in seen:
            continue
        seen.add(key)
        s = dict(s)
        if s.get("lat") is None and s.get("nwps") in SITE_COORDS:
            s["lat"], s["lon"] = SITE_COORDS[s["nwps"]]
        out.append(s)
    return out


def _refine(s, i):
    """Parabola through the 3 points around an hourly peak/trough -> its real time and height."""
    (t0, v0), (t1, v1), (t2, v2) = s[i - 1], s[i], s[i + 1]
    h0, h2 = (t0 - t1).total_seconds() / 3600, (t2 - t1).total_seconds() / 3600
    if h0 >= 0 or h2 <= 0:
        return t1, v1
    # fit v = a*x^2 + b*x + v1 through (h0, v0), (0, v1), (h2, v2)
    den = h0 * h2 * (h0 - h2)
    if not den:
        return t1, v1
    a = (h2 * (v0 - v1) - h0 * (v2 - v1)) / den
    b = (h0 * h0 * (v2 - v1) - h2 * h2 * (v0 - v1)) / den
    if not a:
        return t1, v1
    x = max(h0, min(h2, -b / (2 * a)))
    return t1 + timedelta(hours=x), v1 + b * x + a * x * x


def find_extrema(series, now, kind="H", n=2, min_gap_h=6):
    """High (H) or low (L) tides after now from a (time, ft) forecast series, refined between points."""
    s = sorted(series)
    sign = 1 if kind == "H" else -1
    out = []
    for i in range(1, len(s) - 1):
        t, v = s[i]
        if t < now - timedelta(minutes=30):
            continue
        win = [sign * x[1] for x in s if abs((x[0] - t).total_seconds()) <= 7200]
        if sign * v >= max(win) and sign * v > sign * s[i - 1][1] - 1e-9:
            tt, vv = _refine(s, i)
            if out and (tt - out[-1][0]).total_seconds() < min_gap_h * 3600:
                if sign * vv > sign * out[-1][1]:
                    out[-1] = (tt, vv)
                continue
            out.append((tt, vv))
    return out[:n]


def find_highs(series, now, n=2, min_gap_h=6):
    """Local maxima (high tides) after now from a (time, ft) series."""
    return find_extrema(series, now, "H", n, min_gap_h)


def _nwps_lookup(http, names, bbox):
    """Find NWPS gauge IDs by name inside a bounding box."""
    w, s, e, n = bbox
    try:
        d = http.get(NWPS, {"bbox.xmin": w, "bbox.ymin": s, "bbox.xmax": e, "bbox.ymax": n, "srid": "EPSG_4326"})
    except Exception as ex:
        http.log(f"NWPS gauge search: {ex}")
        return {}
    found = {}
    for g in d.get("gauges", []):
        nm = (g.get("name") or "").lower()
        for want in names:
            if want.lower() in nm and want not in found:
                found[want] = g.get("lid")
                http.log(f"NWPS: '{want}' -> {g.get('lid')} ({g.get('name')})")
    return found


def fetch_high_tides(http, cfg, now, tz, sites=None, n_highs=2):
    sites = sites or cfg.get("tide_sites") or DEFAULT_TIDE_SITES
    lookup = _nwps_lookup(http, [s["search"] for s in sites if s.get("search") and not s.get("nwps")],
                          tuple(cfg.get("tide_search_bbox") or (-77.3, 36.6, -75.5, 37.9)))
    out = []
    for site in sites:
        lid = site.get("nwps") or lookup.get(site.get("search", ""))
        stages, series, src = None, [], None
        lat, lon = site.get("lat"), site.get("lon")
        if lid:
            try:
                meta = http.get(f"{NWPS}/{lid}")
                lat, lon = meta.get("latitude") or lat, meta.get("longitude") or lon
                cats = (meta.get("flood") or {}).get("categories") or {}
                stages = {k: (cats.get(k) or {}).get("stage") for k in ("action", "minor", "moderate", "major")}
                stages = {k: v for k, v in stages.items() if isinstance(v, (int, float)) and v > -900} or None
                f = http.get(f"{NWPS}/{lid}/stageflow/forecast")
                series = [(datetime.fromisoformat(d["validTime"].replace("Z", "+00:00")).astimezone(tz), float(d["primary"]))
                          for d in f.get("data", []) if d.get("primary") not in (None, -999)]
                src = "NWS forecast" if series else None
            except Exception as ex:
                http.log(f"NWPS {lid}: {ex}")
        highs = find_highs(series, now, n=n_highs) if series else []
        if not highs and site.get("coops"):
            try:
                hl = _coops(http, site["coops"], product="predictions", datum="MLLW", interval="hilo",
                            begin_date=now.strftime("%Y%m%d"), range=48)
                highs = [(_local(p["t"], tz), float(p["v"])) for p in hl.get("predictions", [])
                         if p["type"] == "H" and _local(p["t"], tz) >= now - timedelta(minutes=30)][:n_highs]
                src = "astronomical tide"
            except Exception as ex:
                http.log(f"CO-OPS {site['coops']}: {ex}")
        out.append({"name": site["name"], "lid": lid, "stages": stages or site.get("stages"), "source": src,
                    "lat": lat, "lon": lon,
                    "highs": [{"time": t, "ft": round(v, 1),
                               "cat": flood_category(v, stages or site.get("stages") or {}) if (stages or site.get("stages")) else None}
                              for t, v in highs]})
    return out


# ====================================================================== BEACH & BOATING
def _sections(text):
    return [s for s in re.split(r"\n\s*\$\$\s*\n", text) if s.strip()]


def parse_srf(text, wanted):
    """Surf Zone Forecast -> {place: {"rip": "Moderate", "surf": "2 to 3 feet", "uv": 7, "water": 71}}."""
    out = {}
    for sec in _sections(text):
        head = sec[:600].lower()
        place = next((p for p, keys in wanted.items() if any(k.lower() in head for k in keys)), None)
        if not place or place in out:
            continue
        m = re.search(r"\n\.(TODAY|THIS AFTERNOON|TONIGHT|REST OF TODAY|[A-Z]+DAY)\.\.\.(.*?)(?=\n\.[A-Z ]+\.\.\.|\Z)", sec, re.S)
        blk = m.group(2) if m else sec

        def grab(label):
            mm = re.search(label + r"[^\n.]*?\.{2,}\s*([^\n]+?)\.?\s*(?:\n|$)", blk, re.I)
            return mm.group(1).strip() if mm else None
        rip = grab(r"Rip Current Risk\*?")
        out[place] = {"period": (m.group(1).title() if m else ""), "rip": rip.split()[0].title() if rip else None,
                      "rip_text": rip, "surf": grab(r"Surf Height"), "uv": grab(r"(?:Max )?UV Index"),
                      "water": grab(r"Water Temperature"), "wx": grab(r"Weather")}
    return out


def parse_cwf(text, zones):
    """Coastal Waters Forecast -> {zone_label: "TODAY: SW winds 10 to 15 kt. Waves 1 to 2 ft."}."""
    out = {}
    flat = text.replace("\r", "")
    for code, label in zones.items():
        m = re.search(code + r".*?\n(.*?)(?=\n\$\$|\Z)", flat, re.S)
        if not m:
            continue
        body = m.group(1)
        periods = re.findall(r"\n\.([A-Z ]+)\.\.\.(.*?)(?=\n\.[A-Z ]+\.\.\.|\Z)", "\n" + body, re.S)
        if periods:
            name, txt = periods[0]
            txt = re.sub(r"\s+", " ", txt).strip()
            nxt = ""
            if len(periods) > 1:
                nxt = f"{periods[1][0].title()}: " + re.sub(r"\s+", " ", periods[1][1]).strip()
            out[label] = {"period": name.title(), "text": _sentence_case(txt), "next": _sentence_case(nxt)}
    return out


def _sentence_case(s):
    if s and sum(c.isupper() for c in s) > 0.6 * sum(c.isalpha() for c in s):
        s = ". ".join(p.strip().capitalize() for p in s.lower().split(". "))
        s = re.sub(r"\b(kt|ft|nm)\b", lambda m: m.group(1), s)
        s = re.sub(r"\b(n|ne|e|se|s|sw|w|nw|nne|ene|ese|sse|ssw|wsw|wnw|nnw)\b(?= winds| wind|\s+\d| to )",
                   lambda m: m.group(1).upper(), s)
    return s


def fetch_beach(http, cfg):
    wanted = cfg.get("srf_places") or {"VA Beach": ["Virginia Beach"], "Outer Banks": ["Currituck", "Outer Banks"],
                                       "Eastern Shore": ["Accomack", "Northampton", "Eastern Shore"]}
    zones = cfg.get("marine_zones") or {"ANZ632": "Lower Bay", "ANZ634": "Bay Mouth / CBBT", "ANZ656": "Coastal Waters"}
    srf, cwf = {}, {}
    try:
        for t in http.product_texts("SRF", cfg.get("srf_office", "AKQ"), 2):
            srf = parse_srf(t, wanted)
            if srf:
                break
    except Exception as e:
        http.log(f"SRF: {e}")
    try:
        cwf = parse_cwf(http.product_texts("CWF", cfg.get("cwf_office", "AKQ"), 1)[0], zones)
    except Exception as e:
        http.log(f"CWF: {e}")
    return {"srf": srf, "marine": cwf, "water_temp": fetch_water_temp(http, cfg)}


# ====================================================================== CLIMATE REPORT (CLI)
def _num(tok):
    tok = tok.strip().rstrip("R")
    if tok in ("T",):
        return 0.001
    try:
        return float(tok)
    except ValueError:
        return None


def parse_cli(text):
    """NWS daily climate report -> dict (yesterday's or today's values)."""
    t = text.replace("\r", "")
    m = re.search(r"CLIMATE SUMMARY FOR\s+([A-Z]+\s+\d{1,2}\s+\d{4})", t)
    day = datetime.strptime(m.group(1).title(), "%B %d %Y").date() if m else None
    which = "yesterday" if re.search(r"\n\s*YESTERDAY\s*\n", t) else "today"
    res = {"date": day.isoformat() if day else None, "which": which}
    a = re.search(r"VALID (?:TODAY )?AS OF\s+(\d{3,4})\s*([AP]M)", t)
    if a:  # afternoon/evening report for today: "VALID TODAY AS OF 0500 PM LOCAL TIME"
        hhmm = a.group(1).zfill(4)
        h, mi = int(hhmm[:2]), int(hhmm[2:])
        res["as_of"] = f"{h or 12}{':%02d' % mi if mi else ''} {a.group(2)}"
    tsec = re.search(r"TEMPERATURE \(F\)(.*?)(?:PRECIPITATION|\n\n\n)", t, re.S)
    if tsec:
        for name in ("MAXIMUM", "MINIMUM", "AVERAGE"):
            mm = re.search(rf"^\s*{name}\s+(.*)$", tsec.group(1), re.M)
            if not mm:
                continue
            toks = mm.group(1).split()
            obs = _num(toks[0]) if toks else None
            rest = toks[1:]
            if len(rest) >= 2 and rest[1] in ("AM", "PM"):
                tm, rest = f"{rest[0]} {rest[1]}", rest[2:]
            else:
                tm = None
            vals = [_num(x) for x in rest]
            rec = {"obs": obs, "time": tm, "record_flag": toks[0].endswith("R") if toks else False}
            if len(vals) >= 5:
                rec.update(record=vals[0], record_year=int(vals[1]) if vals[1] else None)
            if len(vals) >= 3:
                rec.update(normal=vals[-3], departure=vals[-2], last_year=vals[-1])
            res[name.lower()] = rec
    psec = re.search(r"PRECIPITATION \(IN\)(.*?)(?:SNOWFALL|DEGREE DAYS|\n\n\n)", t, re.S)
    if psec:
        for key, pat in (("day", r"(?:YESTERDAY|TODAY)"), ("month", r"MONTH TO DATE"), ("year", r"SINCE JAN 1")):
            mm = re.search(rf"^\s*{pat}\s+(.*)$", psec.group(1), re.M)
            if not mm:
                continue
            toks = mm.group(1).split()
            vals = [_num(x) for x in toks]
            rec = {"obs": vals[0]}
            if len(vals) >= 4:
                rec.update(normal=vals[-3], departure=vals[-2], last_year=vals[-1])
            if key == "day" and len(vals) >= 6:
                rec.update(record=vals[1], record_year=int(vals[2]) if vals[2] else None)
            res["precip_" + key] = rec
    return res


def choose_cli(parsed, now, cfg):
    """After cli_today_after_hour (5 PM), use today's afternoon report when it's out so the climate
    graphics include today; otherwise the last complete day (the 'YESTERDAY' report)."""
    parsed = [p for p in parsed if p and p.get("maximum")]
    if now.hour >= cfg.get("cli_today_after_hour", 17):
        today = next((p for p in parsed if p["which"] == "today" and p.get("date") == now.date().isoformat()), None)
        if today:
            return today
    yest = next((p for p in parsed if p["which"] == "yesterday"), None)
    return yest or next(iter(parsed), None)


def fetch_cli(http, cfg, now):
    texts = http.product_texts("CLI", cfg.get("cli_location", "ORF"), 6)
    got = choose_cli([parse_cli(x) for x in texts if x], now, cfg)
    if got:
        http.log(f"CLI: using the {got['which']} report for {got.get('date')}" + (f" (as of {got['as_of']})" if got.get("as_of") else ""))
    return got


# ====================================================================== AIR QUALITY
AQI_CATS = [  # upper bound, name, EPA color, health message
    (50, "Good", (0, 228, 0), "Air quality is satisfactory. Enjoy outdoor activities."),
    (100, "Moderate", (255, 255, 0), "Unusually sensitive people should consider reducing prolonged or heavy outdoor exertion."),
    (150, "Unhealthy for Sensitive Groups", (255, 126, 0),
     "People with heart or lung disease, older adults, children and teens should reduce prolonged or heavy exertion."),
    (200, "Unhealthy", (255, 0, 0), "Everyone should reduce prolonged or heavy exertion; sensitive groups should avoid it."),
    (300, "Very Unhealthy", (143, 63, 151), "Everyone should avoid prolonged or heavy exertion outdoors."),
    (999, "Hazardous", (126, 0, 35), "Everyone should avoid all physical activity outdoors."),
]
POLLUTANT = {"OZONE": "Ozone", "O3": "Ozone", "PM2.5": "PM2.5", "PM25": "PM2.5", "PM10": "PM10", "NO2": "NO2", "CO": "CO", "SO2": "SO2"}


def aqi_cat(v=None, name=None):
    if name:
        n = name.strip().lower()
        for c in AQI_CATS:
            if c[1].lower() == n or (n.startswith("unhealthy for") and c[0] == 150) or (n == "usg" and c[0] == 150):
                return c
    if v is None or v < 0:
        return None
    return next(c for c in AQI_CATS if v <= c[0])


def _dist_km(a, b, c, d):
    import math as m
    return 6371 * m.acos(min(1, m.sin(m.radians(a)) * m.sin(m.radians(c)) + m.cos(m.radians(a)) * m.cos(m.radians(c)) * m.cos(m.radians(b - d))))


def parse_reportingarea(text, cfg):
    """AirNow reportingarea.dat (pipe-delimited): current observations (O) and forecasts (F)."""
    loc = cfg["location"]
    want = (cfg.get("aqi_area") or "Hampton Roads").lower()
    st = (cfg.get("aqi_state") or "VA").upper()
    rows = []
    for line in text.splitlines():
        f = line.split("|")
        if len(f) < 15:
            continue
        try:
            rows.append({"issue": f[0], "date": datetime.strptime(f[1], "%m/%d/%y").date(), "time": f[2], "tz": f[3],
                         "type": f[5], "primary": f[6] == "Y", "area": f[7], "state": f[8], "lat": float(f[9]),
                         "lon": float(f[10]), "param": POLLUTANT.get(f[11].upper(), f[11]),
                         "aqi": int(f[12]) if f[12].strip().isdigit() else None, "cat": f[13],
                         "action": f[14].strip().lower() == "yes", "disc": f[15].strip() if len(f) > 15 else ""})
        except (ValueError, IndexError):
            continue
    mine = [r for r in rows if r["area"].lower() == want and r["state"] == st]
    if not mine:  # nearest reporting area instead
        near = sorted({(r["area"], r["state"], r["lat"], r["lon"]) for r in rows},
                      key=lambda a: _dist_km(loc["lat"], loc["lon"], a[2], a[3]))
        if near and _dist_km(loc["lat"], loc["lon"], near[0][2], near[0][3]) < 120:
            mine = [r for r in rows if (r["area"], r["state"]) == near[0][:2]]
    if not mine:
        return None
    pick = lambda rs: max(rs, key=lambda r: (r["primary"], r["aqi"] if r["aqi"] is not None else
                                               (aqi_cat(name=r["cat"]) or (0,))[0]))
    obs = [r for r in mine if r["type"] == "O"]
    cur = pick(obs) if obs else None
    days = {}
    for r in mine:
        if r["type"] == "F":
            days.setdefault(r["date"], []).append(r)
    fc = []
    for d, rs in sorted(days.items()):
        r = pick(rs)
        fc.append({"date": d.isoformat(), "aqi": r["aqi"], "cat": r["cat"], "param": r["param"], "action": r["action"],
                   "disc": r["disc"], "source": "forecast"})
    return {"area": mine[0]["area"], "state": mine[0]["state"],
            "current": {"aqi": cur["aqi"], "cat": cur["cat"], "param": cur["param"], "date": cur["date"].isoformat(),
                        "time": cur["time"], "source": "AirNow"} if cur else None,
            "forecast": fc}


def parse_om_aq(d, tz):
    """Open-Meteo air quality (CAMS model): current US AQI + daily max for the next days."""
    cur = d.get("current") or {}
    out = {"current": None, "days": {}}
    if cur.get("us_aqi") is not None:
        o3, pm = cur.get("us_aqi_ozone") or 0, cur.get("us_aqi_pm2_5") or 0
        t = datetime.fromisoformat(cur["time"]).replace(tzinfo=tz) if cur.get("time") else None
        out["current"] = {"aqi": int(round(cur["us_aqi"])), "cat": aqi_cat(cur["us_aqi"])[1],
                          "param": "Ozone" if o3 >= pm else "PM2.5", "date": t.date().isoformat() if t else None,
                          "time": t.strftime("%H:%M") if t else "", "source": "model"}
    h = d.get("hourly") or {}
    for i, ts in enumerate(h.get("time") or []):
        v = (h.get("us_aqi") or [None] * (i + 1))[i]
        if v is None:
            continue
        day = ts[:10]
        o3 = ((h.get("us_aqi_ozone") or [])[i:i + 1] or [0])[0] or 0
        pm = ((h.get("us_aqi_pm2_5") or [])[i:i + 1] or [0])[0] or 0
        best = out["days"].get(day)
        if not best or v > best["aqi"]:
            out["days"][day] = {"date": day, "aqi": int(round(v)), "cat": aqi_cat(v)[1],
                                "param": "Ozone" if o3 >= pm else "PM2.5", "action": False, "disc": "", "source": "model"}
    return out


def merge_aqi(airnow, model, today, ndays=5):
    """Official AirNow observation/forecast first; CAMS model guidance fills any gaps (marked as model)."""
    an = airnow or {}
    md = model or {"current": None, "days": {}}
    fc = {f["date"]: f for f in an.get("forecast") or []}
    days = []
    for k in range(ndays):
        d = (today + timedelta(days=k)).isoformat()
        f = fc.get(d) or md["days"].get(d)
        if f:
            days.append(f)
    disc = next((f["disc"] for f in an.get("forecast") or [] if f.get("disc")), "")
    return {"area": an.get("area"), "current": an.get("current") or md["current"], "days": days, "discussion": disc}


def fetch_aqi(http, cfg, now, tz):
    loc = cfg["location"]
    airnow = model = None
    try:
        airnow = parse_reportingarea(http.get(AIRNOW_RA, raw=True, accept="text/plain"), cfg)
        http.log("AirNow:", airnow and airnow.get("area"), airnow and airnow.get("current"),
                 len((airnow or {}).get("forecast") or []), "forecast days")
    except Exception as ex:
        http.log(f"AirNow: {ex}")
    try:
        model = parse_om_aq(http.get(OM_AQ, {"latitude": loc["lat"], "longitude": loc["lon"],
                                             "current": "us_aqi,us_aqi_pm2_5,us_aqi_ozone",
                                             "hourly": "us_aqi,us_aqi_pm2_5,us_aqi_ozone",
                                             "timezone": cfg["timezone"], "forecast_days": 5}), tz)
    except Exception as ex:
        http.log(f"Open-Meteo air quality: {ex}")
    if not airnow and not model:
        raise RuntimeError("no air quality data (AirNow and model both unavailable)")
    return merge_aqi(airnow, model, now.date())


# ====================================================================== ACIS (records, normals, freeze)
def fetch_acis(http, cfg, today):
    sid = cfg.get("acis_station", "ORFthr")

    def pull():
        body = {"sid": sid, "sdate": "por", "edate": today.isoformat(),
                "elems": [{"name": "maxt"}, {"name": "mint"}]}
        d = http.get(ACIS, data=body, timeout=90)
        return d.get("data", [])
    rows = http.cached(f"acis_{sid}_{today.isoformat()}.json", 86400, pull)
    norm = None
    try:
        end = today + timedelta(days=10)
        body = {"sid": sid, "sdate": today.isoformat(), "edate": end.isoformat(),
                "elems": [{"name": "maxt", "normal": "1"}, {"name": "mint", "normal": "1"}]}
        norm = http.cached(f"acis_norm_{sid}_{today.isoformat()}.json", 86400,
                           lambda: http.get(ACIS, data=body).get("data", []))
    except Exception as e:
        http.log(f"ACIS normals: {e}")
    return climo_from_rows(rows, norm, today)


def climo_from_rows(rows, norm_rows, today):
    """Daily records by MM-DD and first-freeze climatology from a POR daily series."""
    def v(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    rec = {}
    by_season = {}
    this_season = today.year if today.month >= 7 else today.year - 1
    for d, mx, mn in rows:
        dt = date.fromisoformat(d)
        k = dt.strftime("%m-%d")
        mx, mn = v(mx), v(mn)
        r = rec.setdefault(k, {"hi": None, "hi_yr": None, "lo": None, "lo_yr": None, "hi_min": None, "hi_min_yr": None})
        if mx is not None and (r["hi"] is None or mx >= r["hi"]):
            r["hi"], r["hi_yr"] = mx, dt.year
        if mn is not None and (r["lo"] is None or mn <= r["lo"]):
            r["lo"], r["lo_yr"] = mn, dt.year
        if mn is not None and (r["hi_min"] is None or mn >= r["hi_min"]):
            r["hi_min"], r["hi_min_yr"] = mn, dt.year
        if mn is not None and mn <= 32 and dt.month >= 7:
            by_season.setdefault(dt.year, dt)
    firsts = {y: d for y, d in by_season.items()}
    # climatology over the last 30 complete seasons with data
    yrs = sorted(y for y in firsts if this_season - 30 <= y < this_season)
    doy = sorted((firsts[y] - date(y, 7, 1)).days for y in yrs)
    climo = None
    if doy:
        med = doy[len(doy) // 2]
        base = date(today.year if today.month >= 7 else today.year - 1, 7, 1)
        climo = {"median": (base + timedelta(days=med)).isoformat(),
                 "earliest": min(firsts[y] for y in yrs).isoformat(),
                 "latest": max(firsts[y] for y in yrs).isoformat(), "years": len(yrs),
                 "last_season": firsts.get(this_season - 1).isoformat() if firsts.get(this_season - 1) else None,
                 "this_season": firsts.get(this_season).isoformat() if firsts.get(this_season) else None}
    normals = {}
    for row in norm_rows or []:
        normals[row[0][5:]] = {"hi": v(row[1]), "lo": v(row[2])}
    return {"records": rec, "normals": normals, "freeze": climo}


# ====================================================================== UV
def fetch_uv(http, cfg, tz):
    rows = http.get(EPA_UV.format(zip=cfg.get("uv_zip", "23510")))
    return parse_uv(rows, tz)


def parse_uv(rows, tz):
    out = []
    for r in rows or []:
        try:
            t = datetime.strptime(r["DATE_TIME"], "%b/%d/%Y %I %p").replace(tzinfo=tz)
        except (KeyError, ValueError):
            continue
        out.append({"time": t, "uv": int(r.get("UV_VALUE") or 0)})
    return sorted(out, key=lambda x: x["time"])


def uv_category(v):
    return ("LOW", (102, 187, 106)) if v < 3 else ("MODERATE", (250, 216, 60)) if v < 6 else \
        ("HIGH", (245, 150, 40)) if v < 8 else ("VERY HIGH", (228, 52, 52)) if v < 11 else ("EXTREME", (170, 80, 220))


# ====================================================================== SUN (NOAA solar calculator)
def sun_times(d, lat, lon, tz, zenith=90.833):
    """Sunrise/sunset (local datetimes) for date d; NOAA algorithm, ~1 min accuracy."""
    def calc(rising):
        n = d.timetuple().tm_yday
        lng_hour = lon / 15
        t = n + ((6 if rising else 18) - lng_hour) / 24
        M = 0.9856 * t - 3.289
        L = (M + 1.916 * math.sin(math.radians(M)) + 0.020 * math.sin(math.radians(2 * M)) + 282.634) % 360
        RA = math.degrees(math.atan(0.91764 * math.tan(math.radians(L)))) % 360
        RA = (RA + (math.floor(L / 90) * 90 - math.floor(RA / 90) * 90)) / 15
        sin_dec = 0.39782 * math.sin(math.radians(L))
        cos_dec = math.cos(math.asin(sin_dec))
        cos_h = (math.cos(math.radians(zenith)) - sin_dec * math.sin(math.radians(lat))) / (cos_dec * math.cos(math.radians(lat)))
        if abs(cos_h) > 1:
            return None
        H = (360 - math.degrees(math.acos(cos_h))) if rising else math.degrees(math.acos(cos_h))
        T = H / 15 + RA - 0.06571 * t - 6.622
        UT = (T - lng_hour) % 24
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(hours=UT)
    rise, sset = calc(True), calc(False)
    return (rise.astimezone(tz) if rise else None, sset.astimezone(tz) if sset else None)


def sun_info(now, lat, lon, tz):
    d = now.date()
    r, s = sun_times(d, lat, lon, tz)
    r0, s0 = sun_times(d - timedelta(days=1), lat, lon, tz)
    r1, s1 = sun_times(d + timedelta(days=1), lat, lon, tz)
    length = (s - r).total_seconds()
    change = length - (s0 - r0).total_seconds()
    return {"sunrise": r, "sunset": s, "tomorrow_sunrise": r1, "tomorrow_sunset": s1,
            "daylight_s": length, "change_s": change,
            "golden_am": (r, r + timedelta(minutes=45)), "golden_pm": (s - timedelta(minutes=45), s)}


# ====================================================================== AVIATION
def flight_category(ceiling, vis):
    c = ceiling if ceiling is not None else 99999
    v = vis if vis is not None else 99
    if c < 500 or v < 1:
        return "LIFR"
    if c < 1000 or v < 3:
        return "IFR"
    if c <= 3000 or v <= 5:
        return "MVFR"
    return "VFR"


FLT_COLORS = {"VFR": (60, 190, 90), "MVFR": (60, 140, 250), "IFR": (230, 50, 50), "LIFR": (210, 70, 210)}


def _vis(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = v.replace("+", "")
        if "/" in v:
            parts = v.split()
            tot = 0.0
            for p in parts:
                if "/" in p:
                    a, b = p.split("/")
                    tot += float(a) / float(b)
                else:
                    tot += float(p)
            return tot
        try:
            return float(v)
        except ValueError:
            return None
    return float(v)


def _ceiling(clouds):
    bases = [c.get("base") for c in (clouds or []) if c.get("cover") in ("BKN", "OVC", "OVX", "VV") and c.get("base") is not None]
    return min(bases) if bases else None


WX_WORDS = {"-": "light ", "+": "heavy ", "VC": "nearby ", "TS": "thunderstorm", "SH": "showers ", "RA": "rain",
            "DZ": "drizzle", "SN": "snow", "BR": "mist", "FG": "fog", "HZ": "haze", "FZ": "freezing ", "PL": "ice pellets",
            "GR": "hail", "UP": "precip", "FU": "smoke", "SQ": "squalls"}


def wx_plain(s):
    if not s:
        return ""
    out = []
    for tok in s.split():
        w, i = "", 0
        while i < len(tok):
            for k in ("VC", "+", "-", "TS", "SH", "FZ", "RA", "DZ", "SN", "BR", "FG", "HZ", "PL", "GR", "UP", "FU", "SQ"):
                if tok.startswith(k, i):
                    w += WX_WORDS[k]
                    i += len(k)
                    break
            else:
                i += 1
        out.append(w.strip())
    return ", ".join(x for x in out if x)


def _wind_txt(d, s, g):
    if not s:
        return "Calm"
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    dd = "Variable" if d in (None, "VRB") else dirs[int((float(d) % 360) / 22.5 + 0.5) % 16]
    return f"{dd} {s} kt" + (f", gusts {g}" if g else "")


def parse_metar(m, tz):
    ceil, vis = _ceiling(m.get("clouds")), _vis(m.get("visib"))
    t = datetime.fromtimestamp(m["obsTime"], timezone.utc).astimezone(tz) if isinstance(m.get("obsTime"), (int, float)) else None
    sky = ", ".join(f"{c['cover']} {c['base']:,}" if c.get("base") is not None else c.get("cover", "") for c in m.get("clouds") or []) or "Clear"
    return {"raw": m.get("rawOb", ""), "time": t, "cat": flight_category(ceil, vis), "ceiling": ceil, "vis": vis,
            "wind": _wind_txt(m.get("wdir"), m.get("wspd"), m.get("wgst")), "sky": sky,
            "temp": m.get("temp"), "dewp": m.get("dewp"),
            "altim": round(m["altim"] / 33.8639, 2) if isinstance(m.get("altim"), (int, float)) and m["altim"] > 100 else m.get("altim"),
            "wx": wx_plain(m.get("wxString"))}


def parse_taf(t, tz):
    periods = []
    for f in (t or {}).get("fcsts", []):
        ceil, vis = _ceiling(f.get("clouds")), _vis(f.get("visib"))
        periods.append({"from": datetime.fromtimestamp(f["timeFrom"], timezone.utc).astimezone(tz),
                        "to": datetime.fromtimestamp(f["timeTo"], timezone.utc).astimezone(tz),
                        "change": f.get("fcstChange") or "", "cat": flight_category(ceil, vis),
                        "ceiling": ceil, "vis": vis, "wind": _wind_txt(f.get("wdir"), f.get("wspd"), f.get("wgst")),
                        "wx": wx_plain(f.get("wxString"))})
    return {"raw": (t or {}).get("rawTAF", ""), "periods": periods}


def fetch_aviation(http, cfg, tz):
    icao = cfg.get("airport", "KORF")
    metars = http.get(f"{AWC}/metar", {"ids": icao, "format": "json", "hours": 3})
    tafs = http.get(f"{AWC}/taf", {"ids": icao, "format": "json"})
    return {"icao": icao, "metar": parse_metar(metars[0], tz) if metars else None,
            "taf": parse_taf(tafs[0], tz) if tafs else None}


# ====================================================================== WARNING COUNTS
WARN_EVENTS = ["Tornado Warning", "Severe Thunderstorm Warning", "Flash Flood Warning", "Special Marine Warning"]


def fetch_warning_counts(http, cfg, now):
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    local = set(cfg.get("alert_counties") or [])
    counts = {"area": {e: 0 for e in WARN_EVENTS}, "state": {e: 0 for e in WARN_EVENTS}}
    seen = set()
    for st in cfg.get("warning_count_states", ["VA"]):
        d = http.get(f"{NWS}/alerts", {"area": st, "start": start.isoformat(timespec="seconds"),
                                       "message_type": "alert"}, accept="application/geo+json")
        for f in d.get("features", []):
            p = f.get("properties", {})
            ev = p.get("event")
            if ev not in WARN_EVENTS:
                continue
            key = (ev, p.get("sent"), tuple(sorted((p.get("geocode") or {}).get("SAME", []))))
            if key in seen:
                continue
            seen.add(key)
            counts["state"][ev] += 1
            fips = {c[1:] for c in (p.get("geocode") or {}).get("SAME", [])}
            if fips & local:
                counts["area"][ev] += 1
    return counts


# ====================================================================== TROPICS
def fetch_tropics(http, cfg):
    storms = []
    try:
        d = http.get(NHC_STORMS)
        for s in d.get("activeStorms", []):
            if not str(s.get("id", "")).lower().startswith(("al",) if cfg.get("tropics_basin", "al") == "al" else ("",)):
                continue
            storms.append({"name": s.get("name"), "class": s.get("classification"), "wind_kt": _intf(s.get("intensity")),
                           "pressure": _intf(s.get("pressure")), "lat": s.get("latitudeNumeric"), "lon": s.get("longitudeNumeric"),
                           "move": f"{s.get('movementDir') or ''}".strip(), "move_mph": _intf(s.get("movementSpeed")),
                           "id": s.get("id")})
    except Exception as e:
        http.log(f"NHC storms: {e}")
    areas, cones = [], []
    try:
        from .outlooks import Fetcher, polys_of
        fx = Fetcher(http.ua, http.debug)
        info = fx.json(NHC_SERVICE, {"f": "json"})
        layers = [l for l in info.get("layers", []) if not l.get("subLayerIds")]

        def pick(*words, bad=()):
            for l in layers:
                n = l["name"].lower()
                if all(w in n for w in words) and not any(b in n for b in bad):
                    return l["id"]
        for lid, kind in ((pick("7", "day", "area") or pick("seven", "area"), "area"), (pick("cone"), "cone")):
            if lid is None:
                continue
            q = fx.json(f"{NHC_SERVICE}/{lid}/query", {"where": "1=1", "outFields": "*", "returnGeometry": "true",
                                                       "outSR": 4326, "f": "geojson"})
            for f in q.get("features", []):
                p = {k.lower(): v for k, v in (f.get("properties") or {}).items()}
                polys = polys_of(f.get("geometry"))
                if not polys:
                    continue
                if kind == "area":
                    areas.append({"polys": polys, "chance7": _pct(p.get("prob7day") or p.get("prob_7day")),
                                  "chance2": _pct(p.get("prob2day") or p.get("prob_2day")),
                                  "risk": (p.get("risk7day") or "").title()})
                else:
                    cones.append({"polys": polys, "name": p.get("stormname") or p.get("stormnum") or ""})
    except Exception as e:
        http.log(f"NHC map layers: {e}")
    return {"storms": storms, "areas": areas, "cones": cones}


def _intf(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def _pct(x):
    if x is None:
        return None
    m = re.search(r"(\d+)", str(x))
    return int(m.group(1)) if m else None


# ====================================================================== FETCH ALL
def fetch_all(cfg, cache_dir, now, tz, want, debug=False):
    http = Http(cfg["user_agent"], cache_dir, debug)
    loc = cfg["location"]
    out = {"errors": []}
    jobs = {
        "tides": lambda: fetch_tides(http, cfg, now, tz),
        "high_tides": lambda: fetch_high_tides(http, cfg, now, tz),
        "aqi": lambda: fetch_aqi(http, cfg, now, tz),
        "tidal_map": lambda: fetch_high_tides(http, cfg, now, tz, tidal_map_sites(cfg), n_highs=4),
        "high_tides_2": lambda: fetch_high_tides(http, cfg, now, tz, cfg.get("tide_sites_2") or DEFAULT_TIDE_SITES_2),
        "beach": lambda: fetch_beach(http, cfg),
        "cli": lambda: fetch_cli(http, cfg, now),
        "acis": lambda: fetch_acis(http, cfg, now.date()),
        "uv": lambda: fetch_uv(http, cfg, tz),
        "aviation": lambda: fetch_aviation(http, cfg, tz),
        "warn_counts": lambda: fetch_warning_counts(http, cfg, now),
        "tropics": lambda: fetch_tropics(http, cfg),
    }
    for key, fn in jobs.items():
        if key not in want:
            continue
        try:
            out[key] = fn()
        except Exception as e:
            out["errors"].append(f"{key}: {e}")
            print(f"  ! {key} data unavailable: {e}")
    out["sun"] = sun_info(now, loc["lat"], loc["lon"], tz)
    return out


NEEDS = {  # graphic -> data it uses
    "tides": {"tides"}, "high_tides": {"high_tides"}, "high_tides_2": {"high_tides_2"}, "air_quality": {"aqi"}, "tidal_flood_map": {"tidal_map"}, "beach": {"beach", "uv"}, "yesterday": {"cli"}, "month_rain": {"cli"},
    "record_watch": {"acis"}, "above_average": {"acis"}, "first_freeze": {"acis"}, "commute": set(), "weekend": set(),
    "sun_uv": {"uv"}, "tropics": {"tropics"}, "warning_count": {"warn_counts"}, "aviation": {"aviation"},
}
