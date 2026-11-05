"""Model data maps: rainfall and wind from several forecast models.

Two sources, both free:
  * Open-Meteo (https://open-meteo.com/en/docs)  -> GFS, ECMWF IFS, ICON, GEM, HRRR, NBM point forecasts requested on a grid
    (multi-location calls) and drawn as smooth maps. No key for non-commercial use; set "open_meteo_apikey" in config.json for
    commercial use (it then uses customer-api.open-meteo.com).
  * NOAA RRFS (Rapid Refresh Forecast System, the 3 km model that replaces HRRR/NAM/RAP) -> real GRIB2 from the operational
    AWS bucket (noaa-rrfs-ops-pds) or NOMADS, fetched with .idx byte ranges so only the few fields we need are downloaded.
    Rainfall, sustained wind, peak gusts and simulated radar. GRIB decoding needs ecCodes + numpy like the NDFD maps.

Graphic keys:  model_maps  (per-model rain + gust maps and the side-by-side comparisons)
               rrfs_maps    (RRFS rain, wind, gust and a 4-frame simulated radar)
Everything fails soft: a model that can't be fetched is skipped with a message; nothing else is affected.
"""
import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import ndfdmap, outlookmap
from .alertmap import _paste_rounded
from .theme import C, Canvas, z

MODEL_VIEW = (-78.8, -73.6, 35.0, 38.8)  # w, e, s, n -- centered on Norfolk (-76.2, 36.9)
OM_URL = "https://api.open-meteo.com/v1/forecast"
OM_URL_PAID = "https://customer-api.open-meteo.com/v1/forecast"
OM_MODELS = {  # our key -> (Open-Meteo model id, label)
    "gfs": ("gfs_seamless", "GFS"), "ecmwf": ("ecmwf_ifs025", "ECMWF"), "icon": ("icon_seamless", "ICON"),
    "gem": ("gem_seamless", "GEM"), "hrrr": ("gfs_hrrr", "HRRR"), "nbm": ("ncep_nbm_conus", "NBM"),
}
OM_META = {"gfs": "ncep_gfs025", "ecmwf": "ecmwf_ifs025", "icon": "dwd_icon", "gem": "cmc_gem_gdps", "hrrr": "ncep_hrrr_conus",
           "nbm": "ncep_nbm_conus"}  # Open-Meteo /data/<id>/static/meta.json -> last_run_initialisation_time
OM_CYCLE = {"gfs": (6, 5), "ecmwf": (6, 7), "icon": (6, 4), "gem": (12, 5), "hrrr": (1, 2), "nbm": (1, 1.5)}  # (hours between runs, hours until available)
DEFAULT_MODELS = ["gfs", "ecmwf", "icon", "hrrr"]
DEFAULT_COMPARE = ["ecmwf", "gfs", "icon", "rrfs"]
LABELS = {**{k: v[1] for k, v in OM_MODELS.items()}, "rrfs": "RRFS"}

RRFS_BASES = [  # tried in order; the first that has the cycle wins (all share rrfs.YYYYMMDD/HH/ below the base)
    "https://noaa-rrfs-ops-pds.s3.amazonaws.com/",
    "https://nomads.ncep.noaa.gov/pub/data/nccf/com/rrfs/prod/",
    "https://nomads.ncep.noaa.gov/pub/data/nccf/com/rrfs/v1.0/",
    "https://nomads.ncep.noaa.gov/pub/data/nccf/com/rrfs/para/",
]

RAIN_BINS = [  # inches -> color
    (0.01, (170, 222, 170)), (0.1, (110, 200, 120)), (0.25, (50, 170, 70)), (0.5, (30, 130, 50)),
    (1, (250, 230, 70)), (1.5, (240, 180, 40)), (2, (240, 130, 30)), (3, (230, 60, 40)),
    (4, (190, 30, 30)), (6, (210, 60, 200)), (8, (140, 70, 200)),
]
GUST_BINS = [  # mph
    (15, (170, 222, 236)), (20, (110, 196, 214)), (25, (70, 170, 170)), (30, (120, 200, 90)),
    (35, (220, 220, 70)), (40, (248, 190, 50)), (45, (246, 140, 40)), (50, (232, 84, 40)),
    (58, (206, 40, 60)), (65, (170, 30, 130)), (75, (200, 90, 220)),
]
RADAR_BINS = [  # dBZ
    (10, (110, 205, 230)), (15, (60, 150, 230)), (20, (40, 100, 220)), (25, (70, 200, 80)), (30, (30, 160, 50)),
    (35, (20, 120, 40)), (40, (250, 230, 60)), (45, (250, 170, 40)), (50, (240, 90, 40)), (55, (220, 30, 40)),
    (60, (170, 20, 90)), (65, (220, 60, 200)), (70, (255, 255, 255)),
]
PANEL_VIEW = (-78.1, -74.3, 35.0, 38.8)  # narrower than MODEL_VIEW: tall side-by-side panels show more north-south
PANEL_CITIES = [("Richmond", 37.54, -77.44, 1), ("Raleigh", 35.78, -78.64, 1),
                ("Salisbury", 38.36, -75.60, 2), ("Nags Head", 35.96, -75.62, 2), ("Wilmington", 34.23, -77.94, 2)]


def _np():
    import numpy as np
    return np


def _view_box(cfg):
    return tuple(cfg.get("model_view") or MODEL_VIEW)


# ------------------------------------------------------------------ small helpers
def _rain_txt(v):
    if v is None or v != v:
        return "N/A"
    if v < 0.01:
        return "NONE"
    return f'{v:.2f}"' if v < 1 else f'{v:.1f}"'


def _bin_color(v, bins):
    col = None
    for t, c in bins:
        if v is not None and v == v and v + 1e-9 >= t:
            col = c
    return col


def _gust_round(v, step=5):
    return int(step * round(v / step))


def _dbz_txt(v):
    if v is None or v != v or v < 10:
        return "DRY"
    if v < 30:
        return "LIGHT RAIN"
    if v < 40:
        return "RAIN"
    if v < 50:
        return "HEAVY RAIN"
    return "STORMS"


def _when(t, tz):
    lt = t.astimezone(tz)
    return f"{lt.strftime('%a').upper()} {lt.strftime('%I %p').lstrip('0')}"


# ------------------------------------------------------------------ Open-Meteo
def _http_json(url, ua, cache_file, max_age_s):
    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < max_age_s:
        return json.loads(cache_file.read_text())
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            cache_file.write_text(json.dumps(data))
            return data
        except urllib.error.HTTPError as ex:
            body = ex.read()[:300].decode("utf-8", "replace")
            last = RuntimeError(f"HTTP {ex.code} {body}")
            if ex.code == 429 and attempt < 2:  # rate limited: wait and try again
                time.sleep(25 * (attempt + 1))
                continue
            break
        except Exception as ex:  # network blip
            last = ex
            time.sleep(3)
    raise last


def _om_points(cfg):
    np = _np()
    w, e, s, n = _view_box(cfg)
    step = float(cfg.get("model_grid_step", 0.6))
    pad = step * 1.5
    lats = np.arange(s - pad, n + pad + 1e-6, step)
    lons = np.arange(w - pad, e + pad + 1e-6, step)
    return lats, lons


def _pick(h, var):
    if var in h:
        return h[var]
    for k in h:
        if k.startswith(var + "_"):  # multi-model responses suffix the variable with the model id
            return h[k]
    return None


def _est_run(key, now_utc):
    """Most recent run that should be out by now (used when Open-Meteo's meta file can't be read)."""
    step, delay = OM_CYCLE.get(key, (6, 5))
    t = now_utc - timedelta(hours=delay)
    return t.replace(hour=int(t.hour // step * step), minute=0, second=0, microsecond=0)


def _om_run(key, cfg, cache, now_utc):
    """-> model initialisation time (UTC). Open-Meteo's meta.json when reachable, else a schedule-based estimate."""
    try:
        url = f"https://api.open-meteo.com/data/{OM_META[key]}/static/meta.json"
        d = _http_json(url, cfg["user_agent"], cache / f"meta_{OM_META[key]}.json", 900)
        t = d.get("last_run_initialisation_time")
        if t:
            return datetime.fromtimestamp(int(t), tz=timezone.utc)
    except Exception:
        pass
    return _est_run(key, now_utc)


def fetch_om(cfg, cache_dir, now_utc, debug=False):
    """-> {"om": {key: {label, lat, lon, times, rain, gust, wind}}, "errors": [...]}; stacks are (time, lat, lon) numpy arrays."""
    np = _np()
    out = {"om": {}, "errors": [], "now": now_utc}
    ua = cfg["user_agent"]
    cache = Path(cache_dir) / "models"
    cache.mkdir(parents=True, exist_ok=True)
    lats, lons = _om_points(cfg)
    pts = [(la, lo) for la in lats for lo in lons]
    chunk = int(cfg.get("model_chunk", 50))
    key_api = cfg.get("open_meteo_apikey") or ""
    base = OM_URL_PAID if key_api else OM_URL
    max_age = int(cfg.get("model_cache_min", 150)) * 60
    for key in cfg.get("model_list") or DEFAULT_MODELS:
        if key not in OM_MODELS:
            continue
        mid, label = OM_MODELS[key]
        try:
            rain = np.full((0, len(lats) * len(lons)), np.nan)
            times = None
            cols = {"precipitation": [], "wind_gusts_10m": [], "wind_speed_10m": []}
            for c0 in range(0, len(pts), chunk):
                part = pts[c0:c0 + chunk]
                q = {"latitude": ",".join(f"{p[0]:.3f}" for p in part), "longitude": ",".join(f"{p[1]:.3f}" for p in part),
                     "hourly": "precipitation,wind_gusts_10m,wind_speed_10m", "models": mid,
                     "forecast_days": int(cfg.get("model_days", 4)), "precipitation_unit": "inch", "wind_speed_unit": "mph",
                     "timezone": "GMT"}
                if key_api:
                    q["apikey"] = key_api
                url = base + "?" + urllib.parse.urlencode(q, safe=",")
                cf = cache / f"om_{hashlib.md5(url.encode()).hexdigest()[:16]}.json"
                data = _http_json(url, ua, cf, max_age)
                if isinstance(data, dict):
                    if data.get("error"):
                        raise RuntimeError(data.get("reason") or "API error")
                    data = [data]
                for item in data:
                    h = item["hourly"]
                    if times is None:
                        times = [datetime.strptime(t, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc) for t in h["time"]]
                    for var in cols:
                        arr = _pick(h, var)
                        cols[var].append(np.array([np.nan if x is None else x for x in arr], dtype=float)
                                         if arr is not None else np.full(len(times), np.nan))
                time.sleep(float(cfg.get("model_pause_s", 0.4)))
            shape = (len(times), len(lats), len(lons))
            stacks = {v: np.stack(a, axis=1).reshape(shape) for v, a in cols.items()}  # (t, point) -> (t, lat, lon)
            if np.isnan(stacks["precipitation"]).all():
                raise RuntimeError("no precipitation data returned for this model")
            out["om"][key] = {"label": label, "lat": lats, "lon": lons, "times": times, "rain": stacks["precipitation"],
                              "gust": stacks["wind_gusts_10m"], "wind": stacks["wind_speed_10m"],
                              "run": _om_run(key, cfg, cache, now_utc)}
            if debug:
                print(f"   [models] {label}: {len(pts)} points, {len(times)} hours")
        except Exception as ex:
            out["errors"].append(f"{label}: {ex}")
            print(f"  ! {label} (Open-Meteo) unavailable: {ex}")
    return out


def _interp_axis(a, f, axis):
    np = _np()
    n = a.shape[axis]
    pos = np.linspace(0, n - 1, (n - 1) * f + 1)
    i0 = np.clip(np.floor(pos).astype(int), 0, n - 2)
    t = (pos - i0).reshape([-1 if k == axis else 1 for k in range(a.ndim)])
    return np.take(a, i0, axis) * (1 - t) + np.take(a, i0 + 1, axis) * t


def om_field(m, kind, now_utc, hours, up=6):
    """Window a model's hourly stack -> a smooth map field {lat, lon, val, start, end, full}; rain = total, gust/wind = max."""
    np = _np()
    t = m["times"]
    idx = [i for i, x in enumerate(t) if now_utc < x <= now_utc + timedelta(hours=hours)]
    if not idx:
        return None
    stack = m[kind][idx]
    ok = ~np.isnan(stack).all(axis=(1, 2))
    if not ok.any():
        return None
    last = int(np.where(ok)[0].max())  # models with a short horizon (HRRR) stop early
    stack = stack[:last + 1]
    end = t[idx[last]]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        val = np.nansum(stack, axis=0) if kind == "rain" else np.nanmax(stack, axis=0)
    val = np.where(np.isnan(stack).all(axis=0), np.nan, val)
    lat, lon = m["lat"], m["lon"]
    val = _interp_axis(_interp_axis(val, up, 0), up, 1)
    la = np.linspace(lat[0], lat[-1], val.shape[0])
    lo = np.linspace(lon[0], lon[-1], val.shape[1])
    k = int(round(2.0 / max(1e-6, la[1] - la[0])))  # continue the edge values ~2 degrees out so zoomed-out views have no hard edge
    val = np.pad(val, k, mode="edge")
    la = np.concatenate([la[0] - (la[1] - la[0]) * np.arange(k, 0, -1), la, la[-1] + (la[1] - la[0]) * np.arange(1, k + 1)])
    lo = np.concatenate([lo[0] - (lo[1] - lo[0]) * np.arange(k, 0, -1), lo, lo[-1] + (lo[1] - lo[0]) * np.arange(1, k + 1)])
    lon2, lat2 = np.meshgrid(lo, la)
    return {"lat": lat2, "lon": lon2, "val": val, "start": now_utc, "end": end,
            "full": end >= now_utc + timedelta(hours=hours - 1.5), "hours": hours, "sector": m["label"]}


# ------------------------------------------------------------------ RRFS (NOAA GRIB2)
def _get(url, ua, rng=None, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": ua, **({"Range": rng} if rng else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


_IDX = {}


def _idx(base, cyc, prod, fhr, ua):
    """Parse the .idx of one RRFS file -> [(start, end or None, var, level, fcst)] in file order, or None if it isn't there."""
    url = _rrfs_url(base, cyc, prod, fhr)
    if url in _IDX:
        return _IDX[url]
    try:
        txt = _get(url + ".idx", ua, timeout=30).decode("utf-8", "replace")
    except Exception:
        _IDX[url] = None
        return None
    rows = []
    for ln in txt.splitlines():
        p = ln.split(":")
        if len(p) >= 6 and p[1].isdigit():
            rows.append((int(p[1]), p[3], p[4], p[5]))
    out = []
    for k, (off, var, lev, fc) in enumerate(rows):
        out.append((off, rows[k + 1][0] - 1 if k + 1 < len(rows) else None, var, lev, fc))
    _IDX[url] = out or None
    return _IDX[url]


def _rrfs_url(base, cyc, prod, fhr, dom="conus"):
    return f"{base}rrfs.{cyc:%Y%m%d}/{cyc:%H}/rrfs.t{cyc:%H}z.{prod}.3km.f{fhr:03d}.{dom}.grib2"


def _find_cycle(now_utc, bases, ua, prod, cycle_hours, lead_fn, hours_ahead, max_back=40, debug=False):
    """Latest cycle (hour in cycle_hours) whose forecast hour needed for `hours_ahead` hours past now already exists.
    -> (base, cycle_datetime, first_fhr, last_fhr)"""
    t = (now_utc - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    for _ in range(max_back):
        if t.hour in cycle_hours:
            fa = lead_fn(now_utc - t)
            fb = fa + hours_ahead
            for base in bases:
                if _idx(base, t, prod, fb, ua):
                    if debug:
                        print(f"   [rrfs] cycle {t:%Y-%m-%d %HZ} from {base}  (f{fa:03d}..f{fb:03d})")
                    return base, t, fa, fb
        t -= timedelta(hours=1)
    raise RuntimeError("no recent RRFS cycle found (looked at " + ", ".join(b.split('/')[2] for b in bases) + ")")


def _rrfs_msgs(base, cyc, prod, fhr, wants, ua, cache, box, stride, debug=False):
    """Download just the wanted messages of one RRFS file (idx byte ranges) and decode them.
    wants = [(key, var, level_regex, fcst_regex or None)] -> {key: (valid, lat, lon, vals)} (decimated by `stride`)."""
    rows = _idx(base, cyc, prod, fhr, ua)
    if not rows:
        return {}
    chosen = []
    for key, var, lev, fc in wants:
        for r in rows:
            if r[2] == var and re.search(lev, r[3]) and (fc is None or re.search(fc, r[4])):
                chosen.append((r, key))
                break
    if not chosen:
        if debug:
            seen = sorted({f"{r[2]}:{r[3]}:{r[4]}" for r in rows if r[2] in {w[1] for w in wants}})[:12]
            print(f"   [rrfs] f{fhr:03d}: wanted fields not found; same variables in the file: {seen}")
        return {}
    chosen.sort(key=lambda c: c[0][0])
    tag = hashlib.md5((base + prod + "|".join(c[1] + c[0][4] for c in chosen)).encode()).hexdigest()[:10]
    dest = cache / f"rrfs_{cyc:%Y%m%d%H}_f{fhr:03d}_{tag}.grib2"
    if not dest.exists():
        buf = b""
        for (start, end, *_), _k in chosen:
            buf += _get(_rrfs_url(base, cyc, prod, fhr), ua, f"bytes={start}-{end if end is not None else ''}", timeout=180)
        dest.write_bytes(buf)
    res = {}
    msgs = list(ndfdmap._messages(dest, box))
    if len(msgs) != len(chosen):
        raise RuntimeError(f"f{fhr:03d}: expected {len(chosen)} fields, decoded {len(msgs)}")
    for (_r, key), (valid, la, lo, vals) in zip(chosen, msgs):
        res[key] = (valid, la[::stride, ::stride], lo[::stride, ::stride], vals[::stride, ::stride])
    return res


def fetch_rrfs(cfg, cache_dir, now_utc, debug=False):
    """-> {"rrfs": {cycle, rain, wind, gust, radar:[(valid, field)]}, "errors": [...]}"""
    out = {"rrfs": {}, "errors": [], "now": now_utc}
    try:
        import eccodes  # noqa: F401
        np = _np()
    except Exception:
        out["errors"].append("RRFS needs ecCodes + numpy:  pip install eccodes numpy")
        print("  ! " + out["errors"][-1])
        return out
    ua = cfg["user_agent"]
    cache = Path(cache_dir) / "rrfs"
    cache.mkdir(parents=True, exist_ok=True)
    for old in cache.glob("rrfs_*.grib2"):  # keep the cache small: old cycles are never reused
        if time.time() - old.stat().st_mtime > 8 * 3600:
            old.unlink()
    bases = cfg.get("rrfs_bases") or RRFS_BASES
    box = _view_box(cfg)
    stride = int(cfg.get("rrfs_stride", 2))
    hours = int(cfg.get("model_compare_hours", 48))
    ghours = int(cfg.get("model_gust_hours", 24))
    step = 3  # the conus 2dfld product is written every 3 hours
    prod = "2dfld"
    res = out["rrfs"]
    to_field = lambda la, lo, v, start, end, **k: {"lat": la, "lon": lo, "val": v, "start": start, "end": end,
                                                    "sector": "RRFS", "hours": k.get("hours"), "full": True}
    lead3 = lambda d: int((d.total_seconds() // 3600) // step * step)
    # ---- rainfall + wind + gusts: latest 00/06/12/18Z run (those go out to 84 h)
    try:
        base, cyc, fa, fb = _find_cycle(now_utc, bases, ua, prod, (0, 6, 12, 18), lead3, hours, debug=debug)
        res["cycle"] = cyc
        acc = {}
        for f in {fa, fb}:
            if f == 0:
                continue
            m = _rrfs_msgs(base, cyc, prod, f, [("apcp", "APCP", "surface", rf"^0-{f} hour acc fcst")], ua, cache, box, stride, debug)
            if "apcp" in m:
                acc[f] = m["apcp"]
        if fb in acc and (fa == 0 or fa in acc):
            _, la, lo, vb = acc[fb]
            va = acc[fa][3] if fa else 0
            rain = np.clip(vb - va, 0, None) / 25.4  # kg/m2 -> inches
            res["rain"] = to_field(la, lo, rain, now_utc, cyc + timedelta(hours=fb), hours=fb - fa)
        else:  # no 0-N hour totals in this file: add up the 3-hourly buckets instead
            tot, la, lo, n_ok = 0, None, None, 0
            for f in range(fa + step, fb + 1, step):
                m = _rrfs_msgs(base, cyc, prod, f, [("apcp", "APCP", "surface", rf"^{f - step}-{f} hour acc fcst")], ua, cache, box, stride, debug)
                if "apcp" in m:
                    _, la, lo, v = m["apcp"]
                    tot = tot + np.nan_to_num(v)
                    n_ok += 1
            if n_ok == (fb - fa) // step and la is not None:
                res["rain"] = to_field(la, lo, np.clip(tot, 0, None) / 25.4, now_utc, cyc + timedelta(hours=fb), hours=fb - fa)
            else:
                raise RuntimeError("RRFS rainfall totals not found in the 2dfld files (see --outlook-debug for the field names)")
        # winds
        gw = [("gust", "GUST", "surface", None), ("u", "UGRD", "10 m above ground", None), ("v", "VGRD", "10 m above ground", None)]
        gmax = wmax = la = lo = None
        for f in range(fa + step, min(fb, fa + ghours) + 1, step):
            m = _rrfs_msgs(base, cyc, prod, f, gw, ua, cache, box, stride, debug)
            if "gust" in m:
                la, lo, g = m["gust"][1], m["gust"][2], m["gust"][3] * 2.23694
                gmax = g if gmax is None else np.fmax(gmax, g)
            if "u" in m and "v" in m:
                w = np.hypot(m["u"][3], m["v"][3]) * 2.23694
                wmax = w if wmax is None else np.fmax(wmax, w)
                la, lo = m["u"][1], m["u"][2]
        gend = cyc + timedelta(hours=min(fb, fa + ghours))
        if gmax is not None:
            res["gust"] = to_field(la, lo, gmax, now_utc, gend, hours=ghours)
        if wmax is not None:
            res["wind"] = to_field(la, lo, wmax, now_utc, gend, hours=ghours)
    except Exception as ex:
        out["errors"].append(f"RRFS rain/wind: {ex}")
        print(f"  ! RRFS rain/wind unavailable: {ex}")
    # ---- simulated radar: newest run of any hour (hourly runs reach 18 h)
    try:
        nfr, rstep = int(cfg.get("rrfs_radar_frames", 4)), int(cfg.get("rrfs_radar_step", 3))
        ahead = (nfr - 1) * rstep
        base, cyc, fa, fb = _find_cycle(now_utc, bases, ua, prod, tuple(range(24)), lambda d: int(math.ceil(d.total_seconds() / 3600 / step) * step),
                                        ahead, debug=debug)
        frames = []
        for k in range(nfr):
            f = fa + k * rstep
            m = _rrfs_msgs(base, cyc, prod, f, [("refc", "REFC", "entire atmosphere", None)], ua, cache, box, stride, debug)
            if "refc" in m:
                valid, la, lo, v = m["refc"]
                frames.append((valid, {"lat": la, "lon": lo, "val": np.where(v > 0, v, np.nan), "start": valid, "end": valid,
                                       "sector": "RRFS", "hours": 0, "full": True}))
        if len(frames) >= 2:
            res["radar"] = frames
            res.setdefault("radar_cycle", cyc)
        else:
            raise RuntimeError("RRFS composite reflectivity (REFC) not found")
    except Exception as ex:
        out["errors"].append(f"RRFS radar: {ex}")
        print(f"  ! RRFS simulated radar unavailable: {ex}")
    return out


# ------------------------------------------------------------------ drawing
def _src(pkg, label):
    if "SAMPLE" in pkg.get("source", ""):
        return "SAMPLE DATA" + ("  ·  " + label.split("·")[-1].strip() if "·" in label else "")
    return label


def _range_txt(field, kind, cfg):
    """Headline range from the colors plotted within a radius of Norfolk (rain: 0.5" steps, wind: 5 mph steps)."""
    np = _np()
    loc = cfg["location"]
    rad = float(cfg.get("model_range_radius_mi", 35))
    dy = (field["lat"] - loc["lat"]) * 69.0
    dx = (field["lon"] - loc["lon"]) * 69.0 * math.cos(math.radians(loc["lat"]))
    v = field["val"][np.hypot(dx, dy) <= rad]
    v = v[v == v]
    if v.size == 0:
        return None
    lo, hi = float(np.nanmin(v)), float(np.nanmax(v))
    if kind == "rain":
        if hi < 0.1:
            return "NO RAIN"
        a, b = math.floor(lo * 2) / 2, math.ceil(hi * 2) / 2
        b = max(b, a + 0.5)
        return f'UP TO {b:g}"' if a <= 0 else f'{a:g}–{b:g}"'
    a, b = int(lo // 5 * 5), int(math.ceil(hi / 5) * 5)
    b = max(b, a + 5)
    return f"UP TO {b} MPH" if a <= 0 else f"{a}–{b} MPH"


def _single(field, kind, label, tag, pkg, cfg, tz):
    """One model, one map (rain total / peak gust / sustained wind) with the local list + full-screen twin."""
    np = _np()
    view = _view_box(cfg)
    end = field["end"]
    if kind == "rain":
        bins, unit = RAIN_BINS, "IN"
        title = f"{label} RAINFALL FORECAST"
        sub = f"NEXT {field['hours']} HOURS  ·  THROUGH {_when(end, tz)}  ·  {tag}"
        rng = _range_txt(field, "rain", cfg)
        head = lambda v: rng or (_rain_txt(v) if v and v >= 0.01 else "NO RAIN")
        meaning = lambda v: (f"The {label} model has {rng.lower() if rng else _rain_txt(v)} of rain around Norfolk through {_when(end, tz).title()}. "
                             "Model output is guidance, not a forecast: rain totals vary from run to run.") if (rng or "") != "NO RAIN" and (v and v >= 0.01) \
            else f"The {label} model keeps the Hampton Roads area dry through {_when(end, tz).title()}."
        fmt_row = _rain_txt
    else:
        bins, unit = GUST_BINS, "MPH"
        nm = "PEAK WIND GUSTS" if kind == "gust" else "SUSTAINED WINDS"
        title = f"{label} {nm}"
        sub = f"{'MAX ' if kind == 'wind' else ''}NEXT {field['hours']} HOURS  ·  THROUGH {_when(end, tz)}  ·  {tag}"
        rng = _range_txt(field, kind, cfg)
        head = lambda v: rng or (f"{_gust_round(v)} MPH" if v is not None else "N/A")
        what = "gusts" if kind == "gust" else "sustained winds"
        meaning = lambda v: (f"The {label} model shows {what} of {rng.lower() if rng else 'about ' + str(_gust_round(v)) + ' mph'} around Norfolk over the next "
                             f"{field['hours']} hours." + (" Secure loose outdoor items." if kind == "gust" and v and v >= 40 else "")) \
            if v is not None else "Wind data unavailable."
        fmt_row = lambda v: f"{_gust_round(v)} mph" if v is not None else "--"
    return ndfdmap._map_graphic(field, bins, unit, title, sub, head, meaning, None, pkg, cfg, fmt_row, view=view, smooth=0,
                                rows_title="LOCAL MODEL VALUE", source=_src(pkg, tag))


def _panels(cfg, pkg, title, subtitle, panels, bins, unit, pill_fn, summary=None, view=None, range_kind=None):
    """Side-by-side map panels. panels = [(label, sub_label, field)] (2-4)."""
    np = _np()
    cv = Canvas(cfg)
    cv.header(title, subtitle)
    n = len(panels)
    M, gap = cv.M, 18
    top = cv.top
    foot = 112 if summary else 76  # room for the color bar (and the summary line above it)
    bot = cv.bottom - foot
    if not cv.tall and cv.fmt != "square":
        cols, rows = n, 1
    elif n == 2:
        cols, rows = (1, 2)
    elif n == 3:
        cols, rows = (1, 3)
    else:
        cols, rows = 2, 2
    if cv.fmt == "square" and n == 3:
        cols, rows = 3, 1
    pw = (cv.W - 2 * M - gap * (cols - 1)) / cols
    ph = (bot - top - gap * (rows - 1)) / rows
    box = tuple(view or cfg.get("model_panel_view") or PANEL_VIEW)
    loc = cfg["location"]
    city = (loc.get("short") or "Norfolk").upper()
    for k, (label, sublabel, field) in enumerate(panels):
        r, c = divmod(k, cols)
        px, py = M + c * (pw + gap), top + r * (ph + gap)
        lay = outlookmap.draw_map([], pw, ph, cfg, outline=False, painter=ndfdmap._cell_painter(field, bins), view=box,
                                  cities=PANEL_CITIES)
        _paste_rounded(cv, lay, px, py)
        cv.d.rounded_rectangle([z(px), z(py), z(px + pw), z(py + ph)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
        # model name + run info
        tw = cv.width(label, 32, "bold")
        cv.rect(px + 12, py + 12, tw + 34, 54, (13, 21, 38, 232), r=12)
        cv.text(px + 29, py + 39, label, 32, "bold", anchor="lm")
        if sublabel:
            sw = cv.width(sublabel, 18, "bold")
            cv.rect(px + 12, py + 72, sw + 26, 34, (13, 21, 38, 215), r=9)
            cv.text(px + 25, py + 89, sublabel, 18, "bold", C["muted"], anchor="lm")
        # Norfolk marker
        w_, e_, s_, n_ = outlookmap._view(pw, ph, box)
        mx, my = px + (loc["lon"] - w_) / (e_ - w_) * pw, py + (n_ - loc["lat"]) / (n_ - s_) * ph
        cv.text(mx, my, city, 24, "bold", anchor="mm", stroke=3.5)  # Norfolk is the center of the map, labeled instead of a dot
        # local value pill
        v = ndfdmap._value_at(field, loc["lon"], loc["lat"])
        rt = _range_txt(field, range_kind, cfg) if range_kind else None
        txt = f"{city}  {rt or pill_fn(v)}"
        vw = cv.width(txt, 28, "bold")
        col = _bin_color(v, bins) or (70, 86, 112)
        cv.rect(px + 12, py + ph - 62, vw + 46, 50, (13, 21, 38, 235), r=12)
        cv.rect(px + 22, py + ph - 52, 10, 30, (*col, 255), r=4)
        cv.text(px + 42, py + ph - 37, txt, 28, "bold", anchor="lm")
    if summary:
        cv.text(M, cv.bottom - 86, summary, 25, "bold", anchor="lm", maxw=cv.W - 2 * M)
    rngs = [r for r in (ndfdmap._plotted_range(f, box) for _l, _s, f in panels) if r]
    if rngs:  # legend only covers values that appear in at least one panel
        bins = ndfdmap._trim_bins(bins, (min(r[0] for r in rngs), max(r[1] for r in rngs)))
    ndfdmap._color_bar(cv, M, cv.bottom - 62, bins, unit, cv.W - 2 * M)
    return cv


def _compare(kind, now_utc, pkg, cfg, tz):
    """Rain / gust comparison across models (Open-Meteo models + RRFS when it's available)."""
    data = pkg.get("_models") or {}
    om, rrfs = data.get("om") or {}, data.get("rrfs") or {}
    hours = int(cfg.get("model_compare_hours", 48)) if kind == "rain" else int(cfg.get("model_gust_hours", 24))
    panels = []
    for key in cfg.get("model_compare") or DEFAULT_COMPARE:
        if key == "rrfs":
            f = rrfs.get("rain" if kind == "rain" else "gust")
            sub = f"{rrfs['cycle']:%HZ} RUN" if f and rrfs.get("cycle") else ""
        elif key in om:
            f = om_field(om[key], "rain" if kind == "rain" else "gust", now_utc, hours)
            sub = f"{om[key]['run']:%HZ} RUN" if om[key].get("run") else ""
        else:
            continue
        if not f or (key != "rrfs" and not f.get("full")):
            continue
        if key == "rrfs" and f.get("hours") and f["hours"] < hours - 3:
            continue
        panels.append((LABELS[key], sub, f))
    if len(panels) < 2:
        return None
    panels = panels[:4]
    loc = cfg["location"]
    vals = [(lab, ndfdmap._value_at(f, loc["lon"], loc["lat"])) for lab, _s, f in panels]
    vals = [(a, b) for a, b in vals if b is not None]
    st = (loc.get("short") or "Norfolk").upper()
    if kind == "rain":
        title, bins, unit, pill = "MODEL RAINFALL COMPARISON", RAIN_BINS, "IN", _rain_txt
        sub = f"NEXT {hours} HOURS  ·  " + "  ·  ".join(p[0] for p in panels)
        summ = None
        if len(vals) >= 2:
            hi, lo_ = max(vals, key=lambda x: x[1]), min(vals, key=lambda x: x[1])
            fl = {a: f for a, _s, f in panels}
            rr = lambda lab, v: _range_txt(fl[lab], "rain", cfg) or _rain_txt(v)
            summ = f"AROUND {st}:  WETTEST {hi[0]} {rr(*hi)}   ·   DRIEST {lo_[0]} {rr(*lo_)}"
    else:
        title, bins, unit, pill = "MODEL WIND GUST COMPARISON", GUST_BINS, "MPH", lambda v: f"{_gust_round(v)} MPH" if v is not None else "N/A"
        sub = f"PEAK GUSTS  ·  NEXT {hours} HOURS  ·  " + "  ·  ".join(p[0] for p in panels)
        summ = None
        if len(vals) >= 2:
            hi, lo_ = max(vals, key=lambda x: x[1]), min(vals, key=lambda x: x[1])
            fl = {a: f for a, _s, f in panels}
            rg = lambda lab, v: _range_txt(fl[lab], "gust", cfg) or f"{_gust_round(v)} MPH"
            summ = f"AROUND {st}:  STRONGEST {hi[0]} {rg(*hi)}   ·   LIGHTEST {lo_[0]} {rg(*lo_)}"
    cv = _panels(cfg, pkg, title, sub, panels, bins, unit, pill, summ, range_kind=kind)
    srcs = ["Open-Meteo"] + (["NOAA RRFS"] if any(p[0] == "RRFS" for p in panels) else [])
    cv.footer(pkg, source=_src(pkg, " + ".join(srcs)))
    return cv


def model_graphics(pkg, cfg):
    data = pkg.get("_models")
    if not data or not (data.get("om")):
        return None
    now = data.get("now") or datetime.now(timezone.utc)
    tz = ZoneInfo(cfg["timezone"])
    out = []
    rain_h, gust_h = int(cfg.get("model_rain_hours", 72)), int(cfg.get("model_gust_hours", 24))
    np = _np()
    for key, m in data["om"].items():
        label = m["label"]
        otag = "OPEN-METEO" + (f"  ·  {m['run']:%HZ} RUN" if m.get("run") else "")
        f = om_field(m, "rain", now, rain_h)
        if f is not None and (np.nanmax(f["val"]) >= 0.01 or cfg.get("model_maps_always")):
            f["hours"] = max(1, int(round((f["end"] - now).total_seconds() / 3600)))
            out.append((f"model_rain_{key}", _single(f, "rain", label, otag, pkg, cfg, tz)))
        g = om_field(m, "gust", now, gust_h)
        if g is not None:
            g["hours"] = max(1, int(round((g["end"] - now).total_seconds() / 3600)))
            out.append((f"model_gust_{key}", _single(g, "gust", label, otag, pkg, cfg, tz)))
    for kind in ("rain", "gust"):
        cv = _compare(kind, now, pkg, cfg, tz)
        if cv:
            out.append((f"model_compare_{kind}", cv))
        else:
            print(f"  - model_compare_{kind}: fewer than 2 models cover the full window, skipped")
    return out or None


def rrfs_graphics(pkg, cfg):
    data = (pkg.get("_models") or {}).get("rrfs")
    if not data:
        return None
    now = data.get("now") or datetime.now(timezone.utc)
    tz = ZoneInfo(cfg["timezone"])
    np = _np()
    out = []
    cyc = data.get("cycle")
    tag = f"NOAA RRFS 3 KM" + (f"  ·  {cyc:%HZ} RUN" if cyc else "")
    r = data.get("rain")
    if r is not None and (np.nanmax(r["val"]) >= 0.01 or cfg.get("model_maps_always")):
        out.append(("rrfs_rain", _single(r, "rain", "RRFS", tag, pkg, cfg, tz)))
    for kind in ("gust", "wind"):
        f = data.get(kind)
        if f is not None:
            out.append((f"rrfs_{kind}", _single(f, kind, "RRFS", tag, pkg, cfg, tz)))
    frames = data.get("radar")
    if frames:
        panels = [(_when(v, tz), "", f) for v, f in frames[:4]]
        rc = data.get("radar_cycle")
        sub = "SIMULATED RADAR  ·  NOAA RRFS 3 KM" + (f"  ·  {rc:%HZ} RUN" if rc else "")
        cv = _panels(cfg, pkg, "FUTURE RADAR", sub, panels, RADAR_BINS, "DBZ", _dbz_txt)
        cv.footer(pkg, source=_src(pkg, "NOAA RRFS model simulation, not real radar"))
        out.append(("rrfs_radar", cv))
    return out or None


# ------------------------------------------------------------------ sample data (offline tests)
def sample(now_utc, cfg):
    """Synthetic model output on the same structures the fetchers return."""
    np = _np()
    lats, lons = _om_points(cfg)
    nt = 96
    times = [now_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=i + 1) for i in range(nt)]
    LON, LAT = np.meshgrid(lons, lats)

    def storm(shift, amp, horizon):
        rain = np.zeros((nt, len(lats), len(lons)))
        gust = np.zeros_like(rain)
        for i in range(nt):
            cx = -80.5 + (i + shift) * 0.11  # a band moving west -> east
            cy = 36.2 + 0.4 * math.sin(i / 12)
            band = np.exp(-(((LON - cx) / 0.9) ** 2 + ((LAT - cy) / 1.3) ** 2))
            rain[i] = amp * 0.16 * band
            gust[i] = 14 + 32 * band * amp + 6 * np.exp(-(((LON + 75.4) / 1.2) ** 2 + ((LAT - 36.4) / 1.0) ** 2))
        rain[horizon:] = np.nan
        gust[horizon:] = np.nan
        return rain, gust, gust * 0.62

    out = {"om": {}, "errors": [], "now": now_utc}
    for key, (shift, amp, hz) in {"gfs": (0, 1.0, nt), "ecmwf": (3, 1.35, nt), "icon": (-3, 0.8, nt), "hrrr": (1, 1.1, 48),
                                  "gem": (5, 1.2, nt), "nbm": (0, 0.95, nt)}.items():
        rain, gust, wind = storm(shift, amp, hz)
        out["om"][key] = {"label": LABELS[key], "lat": lats, "lon": lons, "times": times, "rain": rain, "gust": gust, "wind": wind,
                          "run": _est_run(key, now_utc)}
    # RRFS-like 3 km grid
    la = np.linspace(33.0, 40.9, 260)
    lo = np.linspace(-81.9, -71.9, 330)
    lo2, la2 = np.meshgrid(lo, la)
    blob = lambda cx, cy, sx, sy: np.exp(-(((lo2 - cx) / sx) ** 2 + ((la2 - cy) / sy) ** 2))
    cyc = now_utc.replace(hour=(now_utc.hour // 6) * 6, minute=0, second=0, microsecond=0)
    mk = lambda v, hrs: {"lat": la2, "lon": lo2, "val": v, "start": now_utc, "end": now_utc + timedelta(hours=hrs),
                         "sector": "RRFS", "hours": hrs, "full": True}
    rain = 2.4 * blob(-76.4, 36.6, 0.9, 0.7) + 1.1 * blob(-78.0, 37.8, 1.0, 0.6)
    gust = 18 + 34 * blob(-75.5, 36.3, 1.1, 0.9)
    frames = []
    for k in range(4):
        cx = -79.6 + 1.6 * k
        z_ = 62 * blob(cx, 36.8 + 0.2 * k, 0.8, 0.6) + 40 * blob(cx - 1.4, 37.6, 0.7, 0.3) + 20 * blob(cx + 2.5, 35.6, 0.9, 0.4)
        frames.append((now_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=3 * k + 1),
                       mk(np.where(z_ > 5, z_, np.nan), 0)))
    out["rrfs"] = {"cycle": cyc, "rain": mk(rain, 48), "gust": mk(gust, 24), "wind": mk(gust * 0.6, 24), "radar": frames,
                   "radar_cycle": cyc}
    return out
