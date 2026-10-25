"""New graphics (all keyless NOAA / NWS data):

  obs_rain          Observed rainfall, past 24 / 48 / 72 hours (NWS MRMS radar rainfall estimates) -
                    local map + side panel, and the VA/NC stencil
  city_table        City-by-city forecast table (12 Hampton Roads + OBX towns: high, low, rain chance, wind, gust)
  rain_timing       "When will it rain?" 48-hour strip: hourly rain chance + intensity
  state_fields      VA/NC stencil maps from NDFD: wind, gusts, rain chance, snow, frost/freeze, dew points
  hr_temps          Hampton Roads close-up high / low temperature maps (stencil)
  aurora            Aurora / Kp forecast (NOAA Space Weather Prediction Center)
  sunset_quality    Sunrise + sunset times with an estimated color-quality rating (from forecast sky cover)
  degree_days       Heating / cooling degree days for the week ahead

Data: pkg["_obsrain"], pkg["_fields"], pkg["_aurora"] (run.py fetches them) and the forecast package itself.
"""
import io
import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from . import alertinfo, ndfdmap, outlooks, outlookmap, statemaps
from .alertmap import _paste_rounded
from .theme import C, Canvas, font, z

MRMS = "https://mapservices.weather.noaa.gov/raster/rest/services/obs/mrms_qpe/ImageServer/exportImage"
OBS_BOX = (-85.2, -74.0, 33.5, 40.0)  # lon w, e, lat s, n -- VA + NC plus a buffer
OBS_STEP = 0.02
SWPC_KP = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
SWPC_OVATION = "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json"

RAIN_BINS = [(t, c) for t, c in outlooks.QPF_COLORS if t in (0.01, 0.10, 0.25, 0.50, 1.00, 1.50, 2.00, 3.00, 4.00, 6.00)]
POP_BINS = [(20, (200, 236, 190)), (30, (160, 222, 160)), (40, (120, 208, 130)), (50, (80, 190, 104)),  # green table; under 20% is not shaded
            (60, (50, 168, 86)), (70, (30, 146, 76)), (80, (22, 128, 72)), (90, (12, 104, 62))]
DEW_BINS = [(35, (196, 176, 128)), (45, (214, 204, 134)), (50, (176, 214, 140)), (55, (120, 200, 120)),
            (60, (70, 186, 150)), (65, (60, 170, 212)), (70, (244, 204, 72)), (75, (242, 134, 52)), (80, (220, 60, 60))]
FROST_BINS = [(-36, (140, 222, 244)), (-32.5, (70, 130, 240)), (-28.5, (150, 80, 220))]  # on -low: frost / freeze / hard freeze
FROST_KEY = [((140, 222, 244), "FROST  33–36°"), ((70, 130, 240), "FREEZE  29–32°"), ((150, 80, 220), "HARD FREEZE  ≤28°")]

TOWNS = [  # (label, lat, lon, state)
    ("Norfolk", 36.85, -76.29, "VA"), ("Virginia Beach", 36.85, -75.98, "VA"), ("Chesapeake", 36.74, -76.25, "VA"),
    ("Suffolk", 36.73, -76.58, "VA"), ("Hampton", 37.03, -76.35, "VA"), ("Newport News", 37.08, -76.47, "VA"),
    ("Williamsburg", 37.27, -76.71, "VA"), ("Franklin", 36.68, -76.94, "VA"), ("Eliz. City", 36.30, -76.22, "NC"),
    ("Eastern Shore", 37.71, -75.75, "VA"), ("Nags Head", 35.96, -75.62, "NC"), ("Hatteras", 35.22, -75.69, "NC"),
]
HR_CITIES = [  # close-up labels (name, lat, lon, tier)
    ("Norfolk", 36.85, -76.29, 1), ("Virginia Beach", 36.85, -75.98, 1), ("Chesapeake", 36.72, -76.24, 1),
    ("Hampton", 37.03, -76.35, 1), ("Newport News", 37.08, -76.49, 2), ("Williamsburg", 37.27, -76.71, 1),
    ("Suffolk", 36.73, -76.58, 1), ("Smithfield", 36.98, -76.63, 2), ("Franklin", 36.68, -76.94, 2),
    ("Eliz. City", 36.30, -76.22, 1), ("Edenton", 36.06, -76.61, 2), ("Nags Head", 35.96, -75.62, 1),
    ("Hatteras", 35.22, -75.69, 2), ("Gloucester", 37.41, -76.53, 2), ("West Point", 37.53, -76.80, 2),
    ("Eastern Shore", 37.71, -75.75, 1), ("Richmond", 37.54, -77.44, 1), ("Emporia", 36.69, -77.54, 2),
    ("Windsor", 36.80, -76.74, 2), ("Currituck", 36.45, -76.02, 2), ("Plymouth", 35.87, -76.75, 2),
    ("Petersburg", 37.23, -77.40, 2), ("Cape Charles", 37.26, -76.02, 2), ("Tappahannock", 37.92, -76.86, 2),
    ("Ahoskie", 36.28, -76.99, 2), ("Murfreesboro", 36.44, -77.10, 2),
]
HR_VIEW = (-78.1, -74.8, 35.1, 38.0)


def _tz(cfg):
    return ZoneInfo(cfg["timezone"])


def _src(pkg, real):
    return "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else real


def _day_name(d, today):
    return "TODAY" if d == today else "TOMORROW" if d == today + timedelta(days=1) else d.strftime("%A").upper()


def _today(pkg, cfg):
    return datetime.fromisoformat(pkg["issued"]).astimezone(_tz(cfg)).date()


def _bin(v, bins):
    col = None
    for t, c in bins:
        if v is not None and v >= t:
            col = c
    return col


def _at(f, lon, lat, grid=None):
    """Nearest-cell value of field dict f (lat / lon 2-D) at a point."""
    import numpy as np
    g = f["val"] if grid is None else grid
    d = (f["lat"] - lat) ** 2 + ((f["lon"] - lon) * math.cos(math.radians(lat))) ** 2
    j, i = np.unravel_index(np.nanargmin(d), d.shape)
    if d[j, i] > 0.5 ** 2:
        return None
    v = g[j, i]
    return None if v != v else float(v)


# =============================================================== DATA: observed rainfall (MRMS radar QPE)
MRMS_NCEP = "https://mrms.ncep.noaa.gov/data/2D/"


def _mrms_grib(prod, cfg, cache_dir, hrs, debug=False):
    """Download the newest NCEP MRMS QPE GRIB2 (regular 0.01 deg lat/lon, mm) and crop it to OBS_BOX -> (lat, lon, inches, valid)."""
    import gzip
    import re
    import eccodes
    import numpy as np
    ua = {"User-Agent": cfg["user_agent"]}
    base = f"{MRMS_NCEP}{prod}/"
    names = []
    try:
        with urllib.request.urlopen(urllib.request.Request(base, headers=ua), timeout=60) as r:
            names = re.findall(r'href="(MRMS_[^"]+_\d{8}-\d{6}\.grib2\.gz)"', r.read().decode("utf-8", "replace"))
    except Exception as ex:
        if debug:
            print(f"   [obs rain] directory listing failed ({ex}); trying the .latest file")
    fn = max(names, key=lambda x: re.search(r"(\d{8}-\d{6})", x).group(1)) if names else f"MRMS_{prod}.latest.grib2.gz"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"mrms_{hrs}hr.grib2"
    with urllib.request.urlopen(urllib.request.Request(base + fn, headers=ua), timeout=180) as r:
        path.write_bytes(gzip.decompress(r.read()))
    w, e, s_, n = OBS_BOX
    with open(path, "rb") as f:
        gid = eccodes.codes_grib_new_from_file(f)
        try:
            ni, nj = eccodes.codes_get(gid, "Ni"), eccodes.codes_get(gid, "Nj")
            lat1, lon1 = eccodes.codes_get(gid, "latitudeOfFirstGridPointInDegrees"), eccodes.codes_get(gid, "longitudeOfFirstGridPointInDegrees")
            di, dj = eccodes.codes_get(gid, "iDirectionIncrementInDegrees"), eccodes.codes_get(gid, "jDirectionIncrementInDegrees")
            up = bool(eccodes.codes_get(gid, "jScansPositively"))
            vd, vt = eccodes.codes_get(gid, "validityDate"), eccodes.codes_get(gid, "validityTime")
            vals = eccodes.codes_get_values(gid).reshape(nj, ni)
        finally:
            eccodes.codes_release(gid)
    lon1 = lon1 - 360 if lon1 > 180 else lon1
    lats = lat1 + (1 if up else -1) * dj * np.arange(nj)
    lons = lon1 + di * np.arange(ni)
    ri, ci = np.where((lats >= s_) & (lats <= n))[0], np.where((lons >= w) & (lons <= e))[0]
    step = max(1, int(round(OBS_STEP / di)))
    ri, ci = ri[::step], ci[::step]
    v = vals[np.ix_(ri, ci)].astype(np.float32)
    v = np.where((v < 0) | (v > 9000), np.nan, v / 25.4)  # missing / no coverage -> NaN; mm -> inches
    v = np.where(v > 60, np.nan, v)
    lat2, lon2 = np.meshgrid(lats[ri], lons[ci], indexing="ij")
    valid = datetime.strptime(f"{vd}{vt:04d}", "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    return lat2, lon2, v, valid


def _mrms_imageserver(hrs, cfg):
    """Fallback: the NWS MRMS ImageServer (radar-only, inches). Rejects output that looks like colour classes instead of inches."""
    import numpy as np
    w, e, s, n = OBS_BOX
    W, H = int(round((e - w) / OBS_STEP)), int(round((n - s) / OBS_STEP))
    q = urllib.parse.urlencode({
        "bbox": f"{w},{s},{e},{n}", "bboxSR": 4326, "imageSR": 4326, "size": f"{W},{H}", "format": "tiff",
        "pixelType": "F32", "compression": "None", "renderingRule": json.dumps({"rasterFunction": f"rft_{hrs}hr"}),
        "interpolation": "RSP_NearestNeighbor", "f": "image"})
    req = urllib.request.Request(MRMS + "?" + q, headers={"User-Agent": cfg["user_agent"]})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if data[:4] not in (b"II*\x00", b"MM\x00*"):
        raise RuntimeError("service did not return a TIFF: " + data[:120].decode("utf-8", "replace"))
    im = Image.open(io.BytesIO(data))
    arr = np.array(im, dtype=np.float32)
    if arr.ndim != 2:
        raise RuntimeError(f"expected one band of rainfall, got an image of shape {arr.shape}")
    if arr.shape != (H, W):
        arr = np.array(Image.fromarray(arr).resize((W, H), Image.NEAREST))
    arr = np.where((arr < 0) | (arr > 60), np.nan, arr)
    fin = arr[np.isfinite(arr)]
    if fin.size and (np.mean(fin == 1.0) > 0.4 or np.all(fin == np.round(fin))):
        raise RuntimeError("ImageServer values look like class codes, not inches (many exactly 1.0 / all whole numbers)")
    lat = np.linspace(n - OBS_STEP / 2, s + OBS_STEP / 2, H)[:, None] * np.ones((1, W))
    lon = np.ones((H, 1)) * np.linspace(w + OBS_STEP / 2, e - OBS_STEP / 2, W)[None, :]
    return lat, lon, arr


def fetch_obs_rain(cfg, cache_dir, now_utc, debug=False):
    """-> {24: {"lat","lon","val"(inches)}, 48.., 72.., "kind": {hrs: "gauge"|"radar"}, "errors", "asof"}.
    Order: NCEP MRMS multi-sensor (radar + rain gauges), NCEP MRMS radar-only, then the NWS ImageServer."""
    import numpy as np
    out = {"errors": [], "asof": now_utc, "kind": {}}
    try:
        import eccodes  # noqa: F401
        have_grib = True
    except Exception:
        have_grib = False
        out["errors"].append("ecCodes missing: using the ImageServer fallback")
    for hrs in cfg.get("obs_rain_hours", [24, 48, 72]):
        got, why = None, []
        if have_grib:
            for prod, kind in ((f"MultiSensor_QPE_{hrs}H_Pass2", "gauge"), (f"RadarOnly_QPE_{hrs}H", "radar")):
                try:
                    lat, lon, arr, valid = _mrms_grib(prod, cfg, cache_dir, hrs, debug)
                    got = (lat, lon, arr, kind, f"{prod} valid {valid:%Y-%m-%d %H:%MZ}")
                    break
                except Exception as ex:
                    why.append(f"{prod}: {ex}")
        if got is None:
            try:
                lat, lon, arr = _mrms_imageserver(hrs, cfg)
                got = (lat, lon, arr, "radar", "NWS MRMS ImageServer")
            except Exception as ex:
                why.append(f"ImageServer: {ex}")
        if got is None:
            out["errors"].append(f"observed rainfall {hrs} hr: " + " | ".join(why))
            print(f"  ! observed rainfall {hrs} hr unavailable: " + " | ".join(why))
            continue
        lat, lon, arr, kind, src = got
        out[hrs] = {"lat": lat, "lon": lon, "val": arr}
        out["kind"][hrs] = kind
        if debug:
            fin = arr[np.isfinite(arr)]
            print(f"   [obs rain] {hrs} hr from {src}: {fin.size} cells, max {np.nanmax(arr):.2f} in, "
                  f"{100 * float(np.mean(fin >= 0.01)):.1f}% wet, {100 * float(np.mean(fin == 0)):.1f}% exactly 0")
            for why_ in why:
                print(f"   [obs rain]   skipped {why_}")
    return out


def sample_obs_rain(now_utc):
    import numpy as np
    w, e, s, n = OBS_BOX
    W, H = int(round((e - w) / OBS_STEP)), int(round((n - s) / OBS_STEP))
    lat = np.linspace(n, s, H)[:, None] * np.ones((1, W))
    lon = np.ones((H, 1)) * np.linspace(w, e, W)[None, :]
    blob = lambda cx, cy, sx, sy: np.exp(-(((lon - cx) / sx) ** 2 + ((lat - cy) / sy) ** 2))
    out = {"errors": [], "asof": now_utc}
    for hrs, k in ((24, 1.0), (48, 1.7), (72, 2.3)):
        v = k * (2.2 * blob(-76.4, 36.7, 1.0, 0.7) + 1.4 * blob(-77.9, 37.6, 1.2, 0.5) + 0.9 * blob(-79.3, 35.4, 1.6, 0.8)) \
            + 0.15 * np.abs(np.sin(lon * 3) * np.cos(lat * 4))
        out[hrs] = {"lat": lat, "lon": lon, "val": np.where(v < 0.02, 0.0, v)}
    return out


# =============================================================== DATA: NDFD daily fields over VA + NC
def fetch_fields(cfg, cache_dir, now_utc, debug=False):
    """Daily NDFD grids over VA/NC -> {"lat","lon","highs","lows","pop","wind","gust","dew":{date: grid}, "snow", "errors"}."""
    out = {"errors": []}
    try:
        import eccodes  # noqa: F401
        import numpy as np
    except Exception:
        out["errors"].append("NDFD state maps need ecCodes + numpy")
        print("  ! " + out["errors"][-1])
        return out
    tz = _tz(cfg)
    box = statemaps.VIEW
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    today = now_utc.astimezone(tz).date()
    ua = cfg["user_agent"]
    f32 = lambda a: np.asarray(a, dtype=np.float32)
    plan = {  # element: (target dict, how to combine, convert, day of the message, vps)
        "maxt": ("highs", "first", lambda v: (v - 273.15) * 9 / 5 + 32),
        "mint": ("lows", "first", lambda v: (v - 273.15) * 9 / 5 + 32),
        "pop12": ("pop", "max", lambda v: v),
        "wspd": ("wind", "max", lambda v: v * 2.23694),
        "wgust": ("gust", "max", lambda v: v * 2.23694),
        "td": ("dew", "max", lambda v: (v - 273.15) * 9 / 5 + 32),
        "snow": ("snow", "sum", lambda v: v * 39.3701),
    }
    last = None
    for sector in cfg.get("ndfd_sectors", ["midatlan", "conus"]):
        try:
            res = {k: {} for k, _, _ in plan.values()}
            snow_end, lat, lon = None, None, None
            for elem, (key, how, conv) in plan.items():
                for vp in ("001-003", "004-007"):
                    if elem in ("wspd", "wgust", "td", "snow") and vp == "004-007":
                        continue  # hourly / 6-hourly fields: the next 3 days are plenty
                    try:
                        path = ndfdmap._download(ndfdmap.TGFTP.format(sector=sector, vp=vp, elem=elem),
                                                 cache / f"ndfd_{sector}_{vp}_{elem}.bin", ua)
                    except Exception as ex:
                        if vp == "004-007":
                            continue
                        raise
                    for valid, la, lo, v in ndfdmap._messages(path, box):
                        lat, lon = la, lo
                        v = f32(conv(v))
                        lt = valid.astimezone(tz)
                        if elem == "maxt":
                            day = lt.date() if lt.hour >= 5 else lt.date() - timedelta(days=1)
                        elif elem == "mint":
                            day = lt.date() + (timedelta(days=1) if lt.hour >= 12 else timedelta())
                        elif elem == "pop12":
                            day = (valid - timedelta(hours=6)).astimezone(tz).date()
                        else:
                            day = lt.date()
                        if day < today:
                            continue
                        if key == "snow":
                            if valid <= now_utc + timedelta(hours=72):
                                res["snow"]["total"] = np.nansum([res["snow"]["total"], v], axis=0) if "total" in res["snow"] else v
                                snow_end = valid
                            continue
                        d = res[key]
                        if how == "first":
                            d.setdefault(day, v)
                        else:
                            d[day] = np.fmax(d[day], v) if day in d else v
            if lat is None or not ndfdmap._covers(lat, lon, box):
                raise RuntimeError(f"{sector} sector doesn't cover VA + NC")
            if not res["highs"] and not res["lows"]:
                raise RuntimeError("no highs/lows in the forecast")
            snow = res.pop("snow").get("total")
            out.update(res)
            out.update({"lat": lat, "lon": lon, "snow": snow, "snow_end": snow_end, "sector": sector})
            if debug:
                print(f"   [fields] {sector}: highs {len(res['highs'])} lows {len(res['lows'])} pop {len(res['pop'])} "
                      f"wind {len(res['wind'])} dew {len(res['dew'])}")
            return out
        except Exception as ex:
            last = ex
            if debug:
                print(f"   [fields] {sector} failed: {ex}")
    out["errors"].append(f"NDFD state fields: {last}")
    print(f"  ! NDFD state maps unavailable: {last}")
    return out


def sample_fields(now_utc, tz):
    import numpy as np
    base = statemaps.sample_temps(now_utc, tz)
    lat, lon = base["lat"], base["lon"]
    blob = lambda cx, cy, sx, sy: np.exp(-(((lon - cx) / sx) ** 2 + ((lat - cy) / sy) ** 2))
    today = now_utc.astimezone(tz).date()
    days = [today + timedelta(days=i) for i in range(4)]
    f = lambda a: np.asarray(a, dtype=np.float32)
    pop = {d: f(np.clip(15 + 70 * blob(-77.2 + 1.2 * i, 36.2 + 0.4 * i, 2.2, 1.4) + 8 * i, 0, 100)) for i, d in enumerate(days)}
    wind = {d: f(9 + (6 + 5 * i) * blob(-75.6, 36.2, 2.2, 1.6) + 5 * blob(-80.5, 37.5, 1.5, 1.0)) for i, d in enumerate(days)}
    gust = {d: f(w * 1.5 + 4) for d, w in wind.items()}
    dew = {d: f(58 + 8 * np.clip((-80 - lon) / -5, 0, 1) - 2 * (lat - 36) - 4 * i + 3 * blob(-77, 35, 2, 1.5)) for i, d in enumerate(days)}
    snow = f(np.clip(4 * blob(-81.3, 36.4, 1.1, 0.6) + 2.5 * blob(-79.8, 38.6, 0.9, 0.7) - 0.3, 0, None))
    lows = {d: v - (10 if i >= 2 else 0) for i, (d, v) in enumerate(sorted(base["lows"].items()))}
    return {"lat": lat, "lon": lon, "highs": base["highs"], "lows": lows, "pop": pop, "wind": wind, "gust": gust,
            "dew": dew, "snow": snow, "snow_end": now_utc + timedelta(hours=72), "errors": []}


# =============================================================== DATA: aurora (SWPC)
def _get_json(url, ua):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_aurora(cfg, debug=False):
    out = {"errors": []}
    try:
        rows = _get_json(SWPC_KP, cfg["user_agent"])
        kp = []
        for r in rows[1:]:
            t = datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            kp.append({"time": t, "kp": float(r[1]), "kind": r[2]})
        out["kp"] = kp
    except Exception as ex:
        out["errors"].append(f"Kp forecast: {ex}")
        print(f"  ! Kp forecast unavailable: {ex}")
    try:
        ov = _get_json(SWPC_OVATION, cfg["user_agent"])
        out["ovation"] = [(c[0] - 360 if c[0] > 180 else c[0], c[1], c[2]) for c in ov["coordinates"] if c[1] >= 20 and c[2] > 0]
        out["forecast_time"] = ov.get("Forecast Time")
    except Exception as ex:
        out["errors"].append(f"OVATION aurora: {ex}")
        print(f"  ! OVATION aurora model unavailable: {ex}")
    return out


def sample_aurora(now_utc):
    import numpy as np
    t0 = now_utc.replace(minute=0, second=0, microsecond=0)
    t0 = t0 - timedelta(hours=t0.hour % 3)
    vals = [2.33, 3.0, 3.67, 4.33, 5.0, 5.67, 4.33, 3.33, 3.0, 2.67, 2.33, 2.0, 2.67, 3.33, 4.0, 3.67, 3.0, 2.33, 2.0, 1.67, 1.33, 2.0, 2.33, 2.67]
    kp = [{"time": t0 + timedelta(hours=3 * i), "kp": v, "kind": "predicted"} for i, v in enumerate(vals)]
    ov = []
    for lat in range(30, 80):
        for lon in range(-170, -50):
            ring = 60 + 4 * math.cos(math.radians(lon + 100) * 1.0)
            a = 80 * math.exp(-((lat - ring) / 4.0) ** 2) + 8 * math.exp(-((lat - (ring - 12)) / 3) ** 2)
            if a >= 1:
                ov.append((lon, lat, a))
    return {"kp": kp, "ovation": ov, "errors": [], "forecast_time": now_utc.isoformat()}


# =============================================================== shared drawing helpers
def _header_clean(cfg, title, sub):
    cv = Canvas(cfg)
    cv.header(title, sub)
    return cv


def _chips(cv, x_right, y, items, title=None):
    f = 18
    wd = [cv.width(t, f, "bold") + 44 for _, t in items]
    total = sum(wd) + 24
    th = 28 if title else 0
    x = x_right - total
    cv.rect(x, y, total, 52 + th, (13, 21, 38, 225), r=10)
    if title:
        cv.text(x + 14, y + 8, title, 15, "bold", C["muted"], anchor="lt")
    cx = x + 12
    for (col, t), w_ in zip(items, wd):
        cv.rect(cx, y + th + 15, 22, 22, (*col, 255), r=4)
        cv.text(cx + 30, y + th + 26, t, f, "bold", anchor="lm")
        cx += w_


def _bar_legend(cv, bins, unit, title):
    bw = min(900, 64 * len(bins) + 40)
    x, y = cv.W - cv.M - bw, cv.H - 118
    cv.rect(x - 10, y - 30, bw + 20, 100, (13, 21, 38, 215), r=12)
    cv.text(x + 4, y - 22, title, 17, "bold", C["muted"], anchor="lt")
    ndfdmap._color_bar(cv, x, y, bins, unit, bw)


def _clean_map(cv, cfg, paint, cities, view=None, tags=True, alpha=0.96, region=None):
    mx, my, mw, mh = region or (cv.M, 150, cv.W - 2 * cv.M, cv.H - 150 - 28)
    lay = statemaps.stencil_map(mw, mh, cfg, painter=paint, cities=cities, alpha=alpha,
                                bg=(13, 21, 38, 255) if region else (0, 0, 0, 0), tags=tags,
                                view=view or cfg.get("state_clean_view") or (-84.12, -74.98, 33.585, 39.765))
    base = cv.img.convert("RGBA")
    base.alpha_composite(lay, (z(mx), z(my)))
    cv.img = base.convert("RGB")
    cv.d = ImageDraw.Draw(cv.img, "RGBA")


def _crop(f, view, pad=3.2):
    import numpy as np
    w, e, s, n = view
    m = (f["lon"] >= w - pad) & (f["lon"] <= e + pad) & (f["lat"] >= s - pad) & (f["lat"] <= n + pad)
    r, c = np.where(m)
    sl = (slice(r.min(), r.max() + 1), slice(c.min(), c.max() + 1))
    return {"lat": f["lat"][sl], "lon": f["lon"][sl], "val": f["val"][sl]}


def _field_graphic(cfg, pkg, title, sub, field, bins, unit, legend_title, fmt, source, view=None, tags=True,
                   city_pool=None, smooth=1, legend=None, min_label=None, region=None, after=None):
    """Header + logo + legend + footer + the stencil filled with `field` (dict lat/lon/val); city values via fmt(v)."""
    cv = _header_clean(cfg, title, sub)
    f = _crop(field, view or statemaps.VIEW)
    paint = ndfdmap._cell_painter(f, bins, alpha=255, smooth=smooth)
    cities = []
    for name, la, lo, tier in city_pool or [c for c in statemaps.CITIES]:
        v = _at(f, lo, la)
        if v is None:
            continue
        cities.append((name, la, lo, tier, None if (min_label is not None and v < min_label) else fmt(v)))
    _clean_map(cv, cfg, paint, cities, view=view, tags=tags, region=region)
    if after:
        after(cv, cities)
    if legend:
        legend(cv)
    else:
        _bar_legend(cv, bins, unit, legend_title)
    cv.footer(pkg, source=_src(pkg, source))
    return cv


# =============================================================== 1) OBSERVED RAINFALL
def _rain_txt(v):
    if v is None or v < 0.01:
        return "NONE"
    return f'{v:.2f}"' if v < 10 else f'{v:.1f}"'


def obs_rain_graphics(pkg, cfg):
    data = pkg.get("_obsrain") or {}
    tz = _tz(cfg)
    asof = datetime.fromisoformat(pkg["issued"]).astimezone(tz)
    when = asof.strftime("%I %p %a").lstrip("0").upper()
    out = []
    import numpy as np
    for hrs in cfg.get("obs_rain_hours", [24, 48, 72]):
        f = data.get(hrs)
        if not f:
            continue
        kind = (data.get("kind") or {}).get(hrs, "radar")
        tag = "RADAR + GAUGE ESTIMATE" if kind == "gauge" else "RADAR-ESTIMATED"
        srcname = "NWS MRMS multi-sensor rainfall analysis" if kind == "gauge" else "NWS MRMS radar rainfall estimate"
        sub = f"PAST {hrs} HOURS  ·  AS OF {when}  ·  {tag}"
        loc = cfg["location"]

        def head(v, hrs=hrs):
            return (_rain_txt(v) + " FELL") if v is not None and v >= 0.01 else "NO RAIN"

        def meaning(v, hrs=hrs):
            if v is None or v < 0.01:
                return f"Little or no rain has fallen in the Hampton Roads area in the past {hrs} hours."
            return (f"About {_rain_txt(v)} of rain at Norfolk over the past {hrs} hours. " +
                    ("Radar estimate adjusted with rain gauges; individual gauges are still the ground truth." if kind == "gauge" else
                     "Radar-only estimates can run high or low; gauge reports are the ground truth."))

        gm = _crop(f, cfg.get("outlook_view") or outlookmap.VIEW_BOX, pad=1.0)
        out.append((f"obs_rain_{hrs}hr", ndfdmap._map_graphic(
            gm, RAIN_BINS, "IN", "OBSERVED RAINFALL", sub, head, meaning, None, pkg, cfg,
            lambda v: _rain_txt(v), view=None, smooth=1, rows_title="RAINFALL ESTIMATES",
            source=srcname)))
        if cfg.get("obs_rain_state", True):
            keymax = float(np.nanmax(f["val"])) if f["val"].size else 0
            out.append((f"obs_rain_{hrs}hr_state", _field_graphic(
                cfg, pkg, "OBSERVED RAINFALL", f"VA & NC  ·  PAST {hrs} HOURS  ·  AS OF {when}  ·  {tag}",
                f, RAIN_BINS, "IN", "RAINFALL (INCHES)", lambda v: _rain_txt(v).replace("NONE", "0"),
                srcname, min_label=0.01)))
    return out or None


# =============================================================== 2) STATE NDFD FIELDS + HR TEMPS
def _daylist(d, n):
    return sorted(d)[:n]


def state_field_graphics(pkg, cfg):
    fd = pkg.get("_fields") or {}
    if "lat" not in fd:
        return None
    today = _today(pkg, cfg)
    n = cfg.get("state_field_days", 3)
    out = []
    mk = lambda grid: {"lat": fd["lat"], "lon": fd["lon"], "val": grid}
    round5 = lambda v: int(5 * round(v / 5))
    specs = [  # key, name, title, bins, unit, legend title, label fmt, source
        ("wind", "state_wind", "WIND FORECAST", ndfdmap.WIND_BINS, "MPH", "PEAK SUSTAINED WIND (MPH)", lambda v: f"{round(v)}"),
        ("gust", "state_gust", "WIND GUSTS", ndfdmap.WIND_BINS, "MPH", "PEAK WIND GUST (MPH)", lambda v: f"{round5(v)}"),
        ("pop", "state_pop", "CHANCE OF RAIN", POP_BINS, "%", "CHANCE OF PRECIPITATION (%)  ·  UNDER 20% NOT SHADED", lambda v: f"{int(10 * round(v / 10))}%"),
        ("dew", "state_dew", "DEW POINTS", DEW_BINS, "°F", "PEAK DEW POINT (°F)", lambda v: f"{round(v)}°"),
    ]
    for key, name, title, bins, unit, ltitle, fmt in specs:
        for i, d in enumerate(_daylist(fd.get(key) or {}, n), 1):
            sub = f"VA & NC  ·  {_day_name(d, today)}, {d.strftime('%b').upper()} {d.day}  ·  NWS NDFD"
            grid = fd[key][d]
            if key == "pop":  # shade by the same nearest-10% value that is printed, so nothing under 20% is coloured
                import numpy as np
                grid = np.round(grid / 10.0) * 10.0
            out.append((f"{name}_day{i}", _field_graphic(cfg, pkg, title, sub, mk(grid), bins, unit, ltitle, fmt, "NWS NDFD")))
    snow = fd.get("snow")
    if snow is not None:
        import numpy as np
        if float(np.nanmax(snow)) >= cfg.get("snow_map_min", 0.1) or cfg.get("snow_map_always"):
            end = fd.get("snow_end")
            sub = "VA & NC  ·  NEXT 72 HOURS" + (f"  ·  THROUGH {end.astimezone(_tz(cfg)).strftime('%a %I %p').lstrip('0').upper()}" if end else "") + "  ·  NWS NDFD"
            out.append(("state_snow", _field_graphic(cfg, pkg, "SNOWFALL FORECAST", sub, mk(snow), ndfdmap.SNOW_BINS, "IN",
                                                     "SNOWFALL (INCHES)", lambda v: ndfdmap._snow_txt(v).replace("UNDER ", "<"),
                                                     "NWS NDFD", min_label=0.1)))
        else:
            print("  - state_snow: no snow in the forecast, skipped")
    # frost / freeze: lows of 36 F or colder
    lows = fd.get("lows") or {}
    for i, d in enumerate(_daylist(lows, n), 1):
        import numpy as np
        low = lows[d]
        if float(np.nanmin(low)) > 36 and not cfg.get("state_frost_always"):
            print(f"  - state_frost_day{i}: no lows at or below 36°, skipped")
            continue
        sub = f"VA & NC  ·  LOWS {_day_name(d, today)}, {d.strftime('%b').upper()} {d.day}  ·  NWS NDFD"
        out.append((f"state_frost_day{i}", _field_graphic(
            cfg, pkg, "FROST & FREEZE RISK", sub, mk(-low), FROST_BINS, "", "", lambda v: f"{round(-v)}°", "NWS NDFD",
            legend=lambda cv: _chips(cv, cv.W - cv.M, cv.H - 130, FROST_KEY, "OVERNIGHT LOW"))))
    return out or None


def hr_temp_graphics(pkg, cfg):
    fd = pkg.get("_fields") or {}
    if "lat" not in fd:
        return None
    from .tempdrop import ORANGE
    today = _today(pkg, cfg)
    mk = lambda grid: {"lat": fd["lat"], "lon": fd["lon"], "val": grid}
    view = tuple(cfg.get("hr_temp_view") or HR_VIEW)
    out = []
    for key, word, name in (("highs", "HIGH", "hr_highs"), ("lows", "LOW", "hr_lows")):
        for i, d in enumerate(_daylist(fd.get(key) or {}, cfg.get("state_field_days", 3)), 1):
            g = fd[key][d]
            import numpy as np
            vals = _crop(mk(g), view, pad=0.5)["val"]
            lo_, hi_ = 5 * math.floor(float(np.nanpercentile(vals, 2)) / 5), 5 * math.ceil(float(np.nanpercentile(vals, 98)) / 5)
            hi_ = max(hi_, lo_ + 10)
            bins = [(t, statemaps.temp_color(t + 1)) for t in range(lo_ - 10, hi_ + 11, 1)]
            bins[0] = (-999, bins[0][1])
            bar = [(t, c) for t, c in bins if t != -999 and (t - lo_) % 5 == 0 and lo_ <= t <= hi_]
            sub = f"HAMPTON ROADS & OBX  ·  {_day_name(d, today)}, {d.strftime('%b').upper()} {d.day}  ·  NWS NDFD"
            out.append((f"{name}_day{i}", _field_graphic(
                cfg, pkg, f"{word} TEMPERATURES", sub, mk(g), bins, "°F", f"{word} TEMPERATURE (°F)", lambda v: f"{round(v)}°",
                "NWS NDFD", view=view, tags=False, city_pool=HR_CITIES, smooth=1, region=HR_REGION,
                after=lambda cv, cities, word=word: _hr_panel(cv, cities, word),
                legend=lambda cv, lo_=lo_, hi_=hi_, word=word: _temp_bar(cv, lo_, hi_, f"{word} TEMPERATURE (°F)"))))
    return out or None


HR_REGION = (70, 196, 840, 826)


def _hr_panel(cv, cities, word):
    """Right-hand city list for the Hampton Roads close-up: every labelled town, ranked."""
    px, py, pw_, ph_ = 940, 196, cv.W - cv.M - 940, 730
    cv.rect(px, py, pw_, ph_, C["panel"], r=18)
    cv.text(px + 26, py + 22, f"{word}S BY TOWN", 21, "bold", C["muted"], anchor="lt")
    rows = sorted([(n, float(t.rstrip("°"))) for n, la, lo, tier, t in cities if t], key=lambda r: -r[1])
    rows = [r for r in rows if r[0] != "Eastern Shore"][:16]
    half = (len(rows) + 1) // 2
    cw_ = (pw_ - 52 - 30) / 2
    for i, (n, v) in enumerate(rows):
        col, k = divmod(i, half)
        x = px + 26 + col * (cw_ + 30)
        y = py + 62 + k * 66
        cv.rect(x, y, cw_, 56, (20, 31, 54, 235), r=10)
        cv.rect(x, y, 8, 56, (*statemaps.temp_color(v), 255), r=3)
        cv.text(x + 24, y + 28, n.upper(), 19, "bold", anchor="lm", maxw=cw_ - 110)
        cv.text(x + cw_ - 16, y + 28, f"{v:.0f}°", 28, "bold", anchor="rm")


def _temp_bar(cv, lo_, hi_, title):
    lw = 520
    cv.rect(cv.W - cv.M - lw - 14, cv.H - 140, lw + 28, 108, (13, 21, 38, 215), r=12)
    cv.text(cv.W - cv.M - lw, cv.H - 132, title, 17, "bold", C["muted"], anchor="lt")
    statemaps._bar(cv, cv.W - cv.M - lw, cv.H - 122, lw, statemaps.temp_color, lo_, hi_, "°F", list(range(lo_, hi_ + 1, 5)))


# =============================================================== 3) CITY-BY-CITY TABLE
def city_table_graphics(pkg, cfg):
    fd = pkg.get("_fields") or {}
    if "lat" not in fd:
        return None
    today = _today(pkg, cfg)
    towns = [tuple(t) for t in (cfg.get("city_table_towns") or TOWNS)]
    days = sorted(set(fd.get("highs", {})) | set(fd.get("lows", {})))[:cfg.get("city_table_days", 2)]
    out = []
    mk = lambda g: {"lat": fd["lat"], "lon": fd["lon"], "val": g}
    for k, d in enumerate(days, 1):
        rows = []
        for name, la, lo, st in towns:
            get = lambda key: (_at(mk(fd[key][d]), lo, la) if d in (fd.get(key) or {}) else None)
            rows.append({"name": name, "st": st, "hi": get("highs"), "lo": get("lows"), "pop": get("pop"),
                         "wind": get("wind"), "gust": get("gust")})
        out.append((f"city_table_day{k}", _table(cfg, pkg, d, today, rows)))
    return out or None


def _table(cfg, pkg, d, today, rows):
    cv = Canvas(cfg)
    cv.header("CITY-BY-CITY FORECAST", f"{_day_name(d, today)}, {d.strftime('%b').upper()} {d.day}  ·  HAMPTON ROADS & OUTER BANKS  ·  NWS NDFD")
    x0, x1 = cv.M, cv.W - cv.M
    top = 205 if not cv.tall else 215
    n = len(rows)
    hh = 46
    rh = min(66, (cv.H - 70 - top - hh) / n)
    cols = [("HIGH", 0.50, "°"), ("LOW", 0.61, "°"), ("RAIN", 0.72, "%"), ("WIND", 0.84, ""), ("GUST", 0.95, "")]
    if cv.tall:
        cols = [("HIGH", 0.42, "°"), ("LOW", 0.56, "°"), ("RAIN", 0.70, "%"), ("WIND", 0.84, ""), ("GUST", 0.97, "")]
    W_ = x1 - x0
    cv.rect(x0, top, W_, hh, (255, 255, 255, 30), r=10)
    cv.text(x0 + 24, top + hh / 2, "CITY", 22, "bold", C["muted"], anchor="lm")
    for lab, fx, _ in cols:
        cv.text(x0 + W_ * fx, top + hh / 2, lab + (" MPH" if lab in ("WIND", "GUST") else ""), 19 if cv.tall else 22, "bold", C["muted"], anchor="rm")
    for r_, r in enumerate(rows):
        y = top + hh + 6 + r_ * rh
        cv.rect(x0, y, W_, rh - 6, (255, 255, 255, 16 if r_ % 2 else 26), r=10)
        statemaps._tag(cv, x0 + 22, y + (rh - 6) / 2, r["st"], 24)
        cv.text(x0 + 82, y + (rh - 6) / 2, r["name"].upper(), min(32, rh * 0.5), "bold", anchor="lm", maxw=W_ * 0.3)
        for lab, fx, suf in cols:
            v = r[{"HIGH": "hi", "LOW": "lo", "RAIN": "pop", "WIND": "wind", "GUST": "gust"}[lab]]
            x = x0 + W_ * fx
            if v is None:
                cv.text(x, y + (rh - 6) / 2, "--", 28, "bold", C["muted"], anchor="rm")
                continue
            if lab == "RAIN":
                vv, col = int(10 * round(v / 10)), (_bin(v, POP_BINS) or (70, 86, 112))
            elif lab in ("HIGH", "LOW"):
                vv, col = round(v), statemaps.temp_color(v)
            else:
                vv = round(v) if lab == "WIND" else int(5 * round(v / 5))
                col = _bin(v, ndfdmap.WIND_BINS) or (70, 86, 112)
            pw = 118 if not cv.tall else 96
            ph = (rh - 6) * 0.72
            cv.rect(x - pw, y + (rh - 6 - ph) / 2, pw, ph, (*col, 255), r=8)
            lum = 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2]
            cv.text(x - pw / 2, y + (rh - 6) / 2, f"{vv}{suf}", min(30, ph * 0.62), "bold", (20, 28, 46) if lum > 150 else C["text"], anchor="mm")
    cv.footer(pkg, source=_src(pkg, "NWS NDFD"))
    return cv


# =============================================================== 4) RAIN TIMING STRIP
INTENSITY = [(0.0, (110, 128, 160), "DRY"), (0.005, (150, 200, 244), "LIGHT"), (0.05, (66, 138, 224), "MODERATE"),
             (0.15, (253, 149, 0), "HEAVY"), (0.30, (230, 40, 50), "VERY HEAVY")]


def _intensity(q):
    c = INTENSITY[0]
    for t in INTENSITY:
        if q is not None and q >= t[0] and (t[0] > 0 or q > 0):
            c = t
    return c


def rain_timing_graphic(pkg, cfg):
    hrs = (pkg.get("hourly_ext") or [])[:cfg.get("rain_timing_hours", 48)]
    if len(hrs) < 12:
        return None
    tz = _tz(cfg)
    rows = [{"t": datetime.fromisoformat(h["time"]).astimezone(tz), "pop": h.get("pop") or 0, "q": h.get("qpf") or 0.0} for h in hrs]
    wet = [r for r in rows if r["pop"] >= 40 or r["q"] >= 0.01]
    total = sum(r["q"] for r in rows)
    cv = Canvas(cfg)
    cv.header("WHEN WILL IT RAIN?", f"NEXT {len(rows)} HOURS  ·  {pkg['location']['area'].upper()}  ·  NWS NDFD")
    fmt = lambda t: t.strftime("%a %I %p").lstrip("0").upper().replace(" 0", " ")
    # summary tiles
    if wet:
        start, end = wet[0]["t"], wet[-1]["t"]
        peak = max(rows, key=lambda r: (r["q"], r["pop"]))
        tiles = [("RAIN STARTS", fmt(start) if start > rows[0]["t"] else "NOW", (88, 170, 255)),
                 ("RAIN ENDS", fmt(end) if end < rows[-1]["t"] else "AFTER THIS WINDOW", (88, 170, 255)),
                 ("WETTEST HOUR", fmt(peak["t"]), (253, 149, 0)),
                 (f"{len(rows)}-HR RAIN TOTAL", f'{total:.2f}"' if total >= 0.01 else "TRACE", (4, 233, 231))]
        summary = (f"Rain is most likely from {fmt(start)} to {fmt(end)}"
                   + (f", with the heaviest rain around {fmt(peak['t'])}." if peak["q"] >= 0.02 else "."))
    else:
        tiles = [("RAIN CHANCE", f"{max(r['pop'] for r in rows)}% MAX", (88, 170, 255)), ("RAIN STARTS", "NONE EXPECTED", (88, 170, 255)),
                 ("WETTEST HOUR", "--", (253, 149, 0)), (f"{len(rows)}-HR RAIN TOTAL", "0.00\"", (4, 233, 231))]
        summary = f"No meaningful rain is expected over the next {len(rows)} hours."
    # longest dry stretch
    best, cur = (0, None, None), None
    for r in rows:
        if r["pop"] < 30 and r["q"] < 0.01:
            cur = cur or [r["t"], r["t"], 0]
            cur[1], cur[2] = r["t"], cur[2] + 1
            if cur[2] > best[0]:
                best = (cur[2], cur[0], cur[1])
        else:
            cur = None
    if best[0] >= 4 and wet:
        summary += f" Longest dry stretch: {fmt(best[1])} to {fmt(best[2])}."
    ty = 205
    tw = (cv.W - 2 * cv.M - 3 * 18) / 4
    for k, (lab, val, col) in enumerate(tiles):
        x = cv.M + k * (tw + 18)
        cv.rect(x, ty, tw, 100, (20, 31, 54, 235), r=12)
        cv.rect(x, ty, 7, 100, (*col, 255), r=3)
        cv.text(x + 24, ty + 14, lab, 19, "bold", C["muted"], anchor="lt")
        cv.text(x + 24, ty + 48, val, 32, "bold", anchor="lt", maxw=tw - 40)
    # chart
    cx, cy, cw, ch = cv.M, ty + 122, cv.W - 2 * cv.M, cv.H - (ty + 122) - 150
    cv.rect(cx, cy, cw, ch, C["panel"], r=16)
    px0, px1, py0, py1 = cx + 90, cx + cw - 30, cy + 30, cy + ch - 70
    for p_ in (0, 25, 50, 75, 100):
        yy = py1 - (py1 - py0) * p_ / 100
        cv.line([(px0, yy), (px1, yy)], (255, 255, 255, 40 if p_ else 90), 1.2)
        cv.text(px0 - 14, yy, f"{p_}%", 19, "bold", C["muted"], anchor="rm")
    n = len(rows)
    bw = (px1 - px0) / n
    for i, r in enumerate(rows):
        x = px0 + i * bw
        h = (py1 - py0) * r["pop"] / 100
        lab, col = _intensity(r["q"])[2], _intensity(r["q"])[1]
        if r["pop"]:
            cv.rect(x + bw * 0.1, py1 - h, bw * 0.8, h, (*col, 255), r=min(6, bw * 0.3))
        if r["t"].hour == 0 or i == 0:  # day divider
            cv.line([(x, py0 - 6), (x, py1 + 40)], (255, 255, 255, 110), 1.5)
            cv.text(x + 8, py1 + 44, r["t"].strftime("%a %b ").upper() + str(r["t"].day), 20, "bold", anchor="lt")
        if r["t"].hour % 3 == 0:
            cv.text(x + bw / 2, py1 + 8, r["t"].strftime("%I%p").lstrip("0").lower().replace("m", ""), 17, "bold", C["muted"], anchor="mt")
    # legend + summary
    _chips(cv, cv.W - cv.M, cv.H - 138, [(c, lab) for _, c, lab in INTENSITY], "BAR HEIGHT = RAIN CHANCE  ·  COLOR = HOURLY RAIN")
    cv.text(cv.M, cv.H - 118, summary, 24, "bold", anchor="lt", maxw=cv.W - 2 * cv.M - 760)
    cv.footer(pkg, source=_src(pkg, "NWS NDFD"))
    return cv


# =============================================================== 5) AURORA
G_SCALE = [(9, "G5", (255, 70, 120)), (8, "G4", (255, 100, 70)), (7, "G3", (255, 150, 50)), (6, "G2", (255, 205, 60)),
           (5, "G1", (190, 225, 80)), (0, "", (60, 150, 220))]


def _g(kp):
    kr = round(kp)
    for t, g, c in G_SCALE:
        if kr >= t:
            return g, c
    return "", G_SCALE[-1][2]


def aurora_graphic(pkg, cfg):
    data = pkg.get("_aurora") or {}
    kp = data.get("kp")
    if not kp:
        return None
    tz = _tz(cfg)
    now = datetime.fromisoformat(pkg["issued"]).astimezone(timezone.utc)
    fut = [k for k in kp if k["time"] + timedelta(hours=3) > now][:cfg.get("aurora_slots", 24)]
    if not fut:
        return None
    peak = max(fut, key=lambda k: k["kp"])
    g, gcol = _g(peak["kp"])
    loc = cfg["location"]
    ov = data.get("ovation") or []
    local = max([a for lo, la, a in ov if abs(lo - loc["lon"]) <= 1 and abs(la - loc["lat"]) <= 1] or [0])
    cv = Canvas(cfg)
    cv.header("AURORA FORECAST", f"NEXT 3 DAYS  ·  GEOMAGNETIC ACTIVITY  ·  NOAA SPACE WEATHER PREDICTION CENTER")
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    # --- map: US states + OVATION aurora probability
    box = tuple(cfg.get("aurora_view") or (-128, -62, 24, 62))
    w_, e_, s_, n_ = outlookmap._view(mw, mh, box)
    W_, H_ = z(mw), z(mh)
    proj = lambda x, y: ((x - w_) / (e_ - w_) * W_, (n_ - y) / (n_ - s_) * H_)
    lay = Image.new("RGBA", (W_, H_), (8, 14, 28, 255))
    d = ImageDraw.Draw(lay, "RGBA")
    alertinfo.counties()
    for rings in [alertinfo._state_lines or []]:
        pass
    for c in alertinfo.counties().values():
        if alertinfo.in_view(c, w_, e_, s_, n_):
            for p in c["polys"]:
                d.polygon([proj(x, y) for x, y in p[0]], fill=(30, 42, 66, 255))
    glow = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for lo, la, a in ov:
        if not (w_ - 2 <= lo <= e_ + 2 and s_ - 2 <= la <= n_ + 2):
            continue
        x, y = proj(lo, la)
        x2, y2 = proj(lo + 1, la - 1)
        t = min(1.0, a / 60.0)
        col = (int(60 + 120 * t * t), int(230 - 60 * t), int(110 - 30 * t), int(40 + 190 * t))
        gd.rectangle([x, y, x2 + 1, y2 + 1], fill=col)
    from PIL import ImageFilter
    glow = glow.filter(ImageFilter.GaussianBlur(z(5)))
    lay.alpha_composite(glow)
    d = ImageDraw.Draw(lay, "RGBA")
    for ln in alertinfo.state_lines():
        d.line([proj(x, y) for x, y in ln], fill=(214, 226, 244, 150), width=max(1, z(1.2)))
    lx, ly = proj(loc["lon"], loc["lat"])
    r = z(9)
    d.ellipse([lx - r, ly - r, lx + r, ly + r], fill=(255, 255, 255, 255), outline=(13, 21, 38, 255), width=z(2))
    d.text((lx + z(16), ly), "HAMPTON ROADS", font=font("bold", 17), fill=(255, 255, 255, 255), anchor="lm",
           stroke_width=z(2.2), stroke_fill=(13, 21, 38, 255))
    _paste_rounded(cv, lay, mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    cv.text(mx + 20, my + 16, "AURORA PROBABILITY (NOAA OVATION MODEL)", 17, "bold", (230, 240, 255, 230), anchor="lt", stroke=2)
    cv.text(mx + 20, my + mh - 18, "GREEN GLOW = AURORA LIKELY OVERHEAD · CANADA NOT OUTLINED", 15, "bold", C["muted"], anchor="lb")
    # --- panel
    cv.rect(px, py, pw_, ph_, C["panel"], r=18)
    cv.text(px + 26, py + 22, "PEAK ACTIVITY (KP INDEX)", 21, "bold", C["muted"], anchor="lt")
    cv.rect(px + 26, py + 54, pw_ - 52, 84, (*gcol, 255), r=12)
    lum = 0.3 * gcol[0] + 0.59 * gcol[1] + 0.11 * gcol[2]
    cv.text(px + pw_ / 2, py + 96, f"KP {peak['kp']:.0f}" + (f"  ·  {g} STORM" if g else "  ·  QUIET"), 38, "bold",
            (20, 28, 46) if lum > 150 else C["text"], anchor="mm", maxw=pw_ - 80)
    when = peak["time"].astimezone(tz).strftime("%a %I %p").lstrip("0").upper()
    if peak["kp"] >= 7:
        meaning = f"A strong geomagnetic storm is forecast around {when}: aurora could be visible from Virginia on a clear, dark night."
    elif peak["kp"] >= 5:
        meaning = f"A minor storm is forecast around {when}. Aurora should stay well north, but could reach the northern U.S. Virginia usually needs Kp 7 or higher."
    else:
        meaning = "Activity stays low. Aurora stays near the Arctic: no chance from Virginia."
    cv.paragraph(px + 26, py + 154, meaning, 22, "regular", pw_ - 52, max_lines=4, lh=1.28)
    cv.text(px + 26, py + 270, f"AURORA ODDS NEAR HAMPTON ROADS: {'<1' if local < 1 else round(local)}%", 20, "bold", anchor="lt", maxw=pw_ - 52)
    # kp bars
    by0, by1 = py + 330, py + ph_ - 100
    bx0, bx1 = px + 70, px + pw_ - 26
    for k_ in (0, 3, 5, 7, 9):
        yy = by1 - (by1 - by0) * k_ / 9
        cv.line([(bx0, yy), (bx1, yy)], (255, 255, 255, 40), 1)
        cv.text(bx0 - 10, yy, str(k_), 16, "bold", C["muted"], anchor="rm")
    bw = (bx1 - bx0) / len(fut)
    for i, k in enumerate(fut):
        gg, col = _g(k["kp"])
        h = (by1 - by0) * min(k["kp"], 9) / 9
        cv.rect(bx0 + i * bw + 1.5, by1 - h, bw - 3, h, (*col, 255), r=3)
        lt = k["time"].astimezone(tz)
        if lt.hour < 3 or i == 0:
            cv.line([(bx0 + i * bw, by0 - 4), (bx0 + i * bw, by1 + 24)], (255, 255, 255, 90), 1.2)
            cv.text(bx0 + i * bw + 5, by1 + 28, lt.strftime("%a").upper(), 17, "bold", anchor="lt")
    cv.text(px + 26, py + ph_ - 28, "KP 5+ = G1 STORM  ·  KP 7+ = G3  ·  EACH BAR = 3 HOURS", 15, "bold", C["muted"], anchor="lm", maxw=pw_ - 52)
    cv.footer(pkg, source=_src(pkg, "NOAA Space Weather Prediction Center"))
    return cv


# =============================================================== 6) SUNRISE / SUNSET QUALITY
def _score(sky, pop):
    """Estimated color potential from forecast total sky cover + rain chance (a heuristic, not an observation)."""
    if sky is None:
        return None
    s = 100 - abs(sky - 52) * 1.55  # broken clouds catch the most color; clear sky is clean but plain; overcast is dull
    if sky <= 12:
        s = min(s, 38)
    if (pop or 0) >= 50:
        s -= 30
    elif (pop or 0) >= 30:
        s -= 12
    return max(5, min(100, s))


RATINGS = [(75, "GREAT", (255, 120, 70)), (55, "GOOD", (255, 175, 60)), (35, "FAIR", (240, 215, 110)), (0, "POOR", (120, 140, 170))]


def _rating(s):
    return next((n, c) for t, n, c in RATINGS if s >= t)


def sunset_quality_graphic(pkg, cfg):
    from .extras_data import sun_times
    hrs = pkg.get("hourly_ext") or []
    if not hrs:
        return None
    tz = _tz(cfg)
    now = datetime.fromisoformat(pkg["issued"]).astimezone(tz)
    loc = cfg["location"]
    lat, lon = cfg["location"].get("lat", 36.9), cfg["location"].get("lon", -76.2)
    by_t = {datetime.fromisoformat(h["time"]).astimezone(tz).replace(minute=0, second=0, microsecond=0): h for h in hrs}

    def at(t):
        t0 = t.replace(minute=0, second=0, microsecond=0)
        h = by_t.get(t0) or by_t.get(t0 + timedelta(hours=1))
        return (h.get("sky"), h.get("pop")) if h else (None, None)

    cols = []
    for k in range(7):
        d = now.date() + timedelta(days=k)
        rise, sset = sun_times(d, lat, lon, tz)
        entry = {"d": d}
        for nm, t in (("rise", rise), ("set", sset)):
            if t is None or t <= now:
                entry[nm] = None
                continue
            sky, pop = at(t)
            sc = _score(sky, pop)
            entry[nm] = None if sc is None else {"t": t, "sky": sky, "pop": pop, "score": sc}
        if entry["rise"] or entry["set"]:
            cols.append(entry)
        if len(cols) == 5:
            break
    if not cols:
        return None
    cv = Canvas(cfg)
    best = max((c for c in cols for nm in ("rise", "set") if c[nm]), key=lambda c: max((c[nm]["score"] for nm in ("rise", "set") if c[nm])))
    bnm = "set" if (best["set"] and (not best["rise"] or best["set"]["score"] >= best["rise"]["score"])) else "rise"
    cv.header("SUNRISE & SUNSET COLOR", f"{loc['area'].upper()}  ·  NEXT {len(cols)} DAYS  ·  ESTIMATED FROM FORECAST SKY COVER")
    n = len(cols)
    gap = 18
    cw = (cv.W - 2 * cv.M - gap * (n - 1)) / n
    top, bot = 205, cv.H - 190
    today = now.date()
    for i, c in enumerate(cols):
        x = cv.M + i * (cw + gap)
        cv.rect(x, top, cw, bot - top, C["panel"], r=16)
        cv.text(x + cw / 2, top + 26, _day_name(c["d"], today)[:9], 30, "bold", anchor="mt")
        cv.text(x + cw / 2, top + 66, c["d"].strftime("%b ").upper() + str(c["d"].day), 20, "medium", C["muted"], anchor="mt")
        half = (bot - top - 110) / 2
        for j, (nm, lab) in enumerate((("rise", "SUNRISE"), ("set", "SUNSET"))):
            y = top + 106 + j * half
            e = c[nm]
            cv.line([(x + 20, y), (x + cw - 20, y)], (255, 255, 255, 50), 1.2)
            cv.text(x + cw / 2, y + 14, lab, 19, "bold", C["muted"], anchor="mt")
            if not e:
                cv.text(x + cw / 2, y + half / 2 + 10, "--", 30, "bold", C["muted"], anchor="mm")
                continue
            name, col = _rating(e["score"])
            cv.text(x + cw / 2, y + 44, e["t"].strftime("%I:%M %p").lstrip("0"), 30, "bold", anchor="mt")
            cv.rect(x + 20, y + 92, cw - 40, 54, (*col, 255), r=10)
            lum = 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2]
            cv.text(x + cw / 2, y + 119, name, 28, "bold", (20, 28, 46) if lum > 150 else C["text"], anchor="mm")
            # score meter
            cv.rect(x + 20, y + 158, cw - 40, 10, (255, 255, 255, 40), r=5)
            cv.rect(x + 20, y + 158, (cw - 40) * e["score"] / 100, 10, (*col, 255), r=5)
            cv.text(x + cw / 2, y + 180, f"{e['sky']}% CLOUD  ·  {e['pop'] or 0}% RAIN", 16, "bold", C["muted"], anchor="mt", maxw=cw - 30)
    sbest = best[bnm]
    nm_, _ = _rating(sbest["score"])
    msg = (f"Best bet: {_day_name(best['d'], today).title()} {'sunset' if bnm == 'set' else 'sunrise'} "
           f"({sbest['t'].strftime('%I:%M %p').lstrip('0')}), rated {nm_.lower()}. Broken clouds light up best; clear skies look clean but plain, and thick overcast or rain mutes the color.")
    cv.paragraph(cv.M, bot + 22, msg, 24, "bold", cv.W - 2 * cv.M - 700, max_lines=3, lh=1.28)
    _chips(cv, cv.W - cv.M, cv.H - 150, [(c, n_) for _, n_, c in reversed(RATINGS)], "COLOR POTENTIAL (ESTIMATE)")
    cv.footer(pkg, source=_src(pkg, "NWS NDFD sky cover"))
    return cv


# =============================================================== 7) DEGREE DAYS
def degree_days_graphic(pkg, cfg):
    days = (pkg.get("days") or [])[:7]
    days = [d for d in days if d.get("high") is not None and d.get("low") is not None]
    if len(days) < 3:
        return None
    base = cfg.get("degree_day_base", 65)
    rows = []
    for d in days:
        mean = (d["high"] + d["low"]) / 2
        rows.append({"d": d, "mean": mean, "hdd": max(0, base - mean), "cdd": max(0, mean - base)})
    thdd, tcdd = sum(r["hdd"] for r in rows), sum(r["cdd"] for r in rows)
    cv = Canvas(cfg)
    cv.header("HEATING & COOLING DEGREE DAYS", f"NEXT {len(rows)} DAYS  ·  BASE {base}°F  ·  {pkg['location']['area'].upper()}")
    # tiles
    ty = 205
    tw = (cv.W - 2 * cv.M - 3 * 18) / 4
    heat_days = sum(r["hdd"] > 0 for r in rows)
    verdict = "HEATING" if thdd > tcdd else "COOLING" if tcdd > thdd else "NEITHER"
    tiles = [("HEATING DEGREE DAYS", f"{thdd:.0f}", (88, 170, 255)), ("COOLING DEGREE DAYS", f"{tcdd:.0f}", (255, 150, 50)),
             ("THIS WEEK NEEDS MORE", verdict, (255, 255, 255)), ("AVERAGE TEMPERATURE", f"{sum(r['mean'] for r in rows) / len(rows):.0f}°", (255, 198, 41))]
    for k, (lab, val, col) in enumerate(tiles):
        x = cv.M + k * (tw + 18)
        cv.rect(x, ty, tw, 108, (20, 31, 54, 235), r=12)
        cv.rect(x, ty, 7, 108, (*col, 255), r=3)
        cv.text(x + 24, ty + 14, lab, 19, "bold", C["muted"], anchor="lt")
        cv.text(x + 24, ty + 48, val, 44, "bold", anchor="lt", maxw=tw - 40)
    # bars
    cx, cy, cw, ch = cv.M, ty + 130, cv.W - 2 * cv.M, cv.H - (ty + 130) - 140
    cv.rect(cx, cy, cw, ch, C["panel"], r=16)
    mx = max(10, max(max(r["hdd"], r["cdd"]) for r in rows))
    n = len(rows)
    slot = (cw - 60) / n
    py0, py1 = cy + 105, cy + ch - 110
    for i, r in enumerate(rows):
        x = cx + 30 + i * slot
        v, col, lab = (r["hdd"], (88, 170, 255), "HDD") if r["hdd"] >= r["cdd"] else (r["cdd"], (255, 150, 50), "CDD")
        h = (py1 - py0) * v / mx
        cv.text(x + slot / 2, cy + 18, r["d"]["dow"], 28, "bold", anchor="mt")
        if v >= 0.5:
            cv.rect(x + slot * 0.2, py1 - h, slot * 0.6, h, (*col, 255), r=8)
        cv.text(x + slot / 2, py1 - h - 8, f"{v:.0f} {lab}" if v >= 0.5 else "0", 24, "bold", anchor="mb")
        cv.text(x + slot / 2, py1 + 14, f"{r['d']['high']}° / {r['d']['low']}°", 22, "bold", C["muted"], anchor="mt")
        cv.text(x + slot / 2, py1 + 46, f"AVG {r['mean']:.0f}°", 20, "medium", C["muted"], anchor="mt")
    cv.line([(cx + 20, py1), (cx + cw - 20, py1)], (255, 255, 255, 120), 2)
    txt = (f"A degree day measures how far the average temperature sits from {base}°F. Heating degree days (blue) mean the furnace runs; "
           "cooling degree days (orange) mean the air conditioning runs. Bigger bars = bigger energy demand.")
    cv.paragraph(cv.M, cv.H - 126, txt, 21, "regular", cv.W - 2 * cv.M, max_lines=3, lh=1.28)
    cv.footer(pkg, source=_src(pkg, "NWS NDFD"))
    return cv
