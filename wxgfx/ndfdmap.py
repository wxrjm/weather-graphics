"""NDFD gridded maps on the county stencil: snowfall forecast and wind speed / gust forecast.

Data: the official NDFD GRIB2 files on tgftp.nws.noaa.gov (free, no key), full 2.5 km grid.
  snow  = ds.snow.bin  (6-hr snowfall, metres)       -> total over the next N hours
  wind  = ds.wspd.bin  (sustained wind, m/s)          -> max over the next 24 hours
  gust  = ds.wgust.bin (wind gust, m/s)                -> max over the next 24 hours
GRIB2 decoding needs the free ecCodes library + numpy (see README: `pip install eccodes numpy`).
If they're missing these graphics are skipped with a message; nothing else is affected.
"""
import os
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import outlookmap
from .alertmap import _paste_rounded
from .theme import Canvas, C, z

TGFTP = "https://tgftp.nws.noaa.gov/SL.us008001/ST.opnl/DF.gr2/DC.ndfd/AR.{sector}/VP.{vp}/ds.{elem}.bin"

SNOW_BINS = [  # inches -> color (light blue -> purple -> pink, broadcast-style)
    (0.1, (200, 226, 246)), (0.5, (150, 200, 240)), (1, (98, 164, 232)), (2, (52, 120, 214)),
    (3, (32, 82, 190)), (4, (22, 52, 150)), (6, (112, 80, 200)), (8, (150, 60, 190)),
    (10, (192, 52, 168)), (12, (226, 64, 128)), (18, (244, 120, 120)), (24, (252, 180, 180)),
]
WIND_BINS = [  # mph -> color
    (5, (170, 222, 236)), (10, (110, 196, 214)), (15, (70, 170, 170)), (20, (120, 200, 90)),
    (25, (220, 220, 70)), (30, (248, 190, 50)), (35, (246, 140, 40)), (40, (232, 84, 40)),
    (50, (206, 40, 60)), (60, (170, 30, 130)), (75, (200, 90, 220)),
]


def _bin(v, bins):
    col = None
    for t, c in bins:
        if v + 1e-9 >= t:
            col = c
    return col


# ------------------------------------------------------------------ fetch + decode
def _download(url, dest, ua, max_age_s=1800):
    p = Path(dest)
    if p.exists() and time.time() - p.stat().st_mtime < max_age_s:
        return p
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=120) as r, open(str(p) + ".part", "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    os.replace(str(p) + ".part", p)
    return p


def _messages(path, box):
    """Yield (valid_end_utc, lat2d, lon2d, values2d) cropped to box, using ecCodes."""
    import eccodes
    import numpy as np
    w, e, s, n = box
    crop = None
    with open(path, "rb") as f:
        while True:
            gid = eccodes.codes_grib_new_from_file(f)
            if gid is None:
                break
            try:
                nx, ny = eccodes.codes_get(gid, "Nx"), eccodes.codes_get(gid, "Ny")
                vd, vt = eccodes.codes_get(gid, "validityDate"), eccodes.codes_get(gid, "validityTime")
                valid = datetime.strptime(f"{vd}{vt:04d}", "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
                vals = eccodes.codes_get_values(gid).reshape(ny, nx)
                miss = eccodes.codes_get(gid, "missingValue")
                vals = np.where(vals == miss, np.nan, vals)
                if crop is None:
                    lat = eccodes.codes_get_array(gid, "latitudes").reshape(ny, nx)
                    lon = eccodes.codes_get_array(gid, "longitudes").reshape(ny, nx)
                    lon = np.where(lon > 180, lon - 360, lon)
                    m = (lon >= w - 0.3) & (lon <= e + 0.3) & (lat >= s - 0.3) & (lat <= n + 0.3)
                    if not m.any():
                        raise RuntimeError("sector does not cover the map area")
                    rows, cols = np.where(m)
                    crop = (rows.min(), rows.max() + 1, cols.min(), cols.max() + 1)
                    clat, clon = lat[crop[0]:crop[1], crop[2]:crop[3]], lon[crop[0]:crop[1], crop[2]:crop[3]]
                yield valid, clat, clon, vals[crop[0]:crop[1], crop[2]:crop[3]]
            finally:
                eccodes.codes_release(gid)


def _covers(lat, lon, box):
    w, e, s, n = box
    return lon.min() <= w + 0.5 and lon.max() >= e - 1.5 and lat.min() <= s + 0.3 and lat.max() >= n - 0.3


def fetch(cfg, cache_dir, now_utc, debug=False):
    """-> {"snow": {...}, "wind": {...}, "gust": {...}, "errors": [...]}; fields are numpy grids."""
    out = {"errors": []}
    try:
        import eccodes  # noqa: F401
        import numpy  # noqa: F401
    except Exception:
        out["errors"].append("snow/wind maps need ecCodes + numpy:  pip install eccodes numpy  "
                             "(or: conda install -c conda-forge python-eccodes numpy)")
        print("  ! " + out["errors"][-1])
        return out
    import numpy as np
    box = tuple(cfg.get("outlook_view") or outlookmap.VIEW_BOX)
    ua = cfg["user_agent"]
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    sectors = cfg.get("ndfd_sectors", ["midatlan", "conus"])
    want = {"snow": ("snow", cfg.get("snow_hours", 72)), "wind": ("wspd", 24), "gust": ("wgust", 24)}
    for key, (elem, hours) in want.items():
        if key != "snow" and key not in (cfg.get("wind_maps") or ["wind", "gust"]):
            continue
        end = now_utc + timedelta(hours=hours)
        for sector in sectors:
            try:
                grids, lat = [], None
                for vp in ("001-003",) if hours <= 72 else ("001-003", "004-007"):
                    url = TGFTP.format(sector=sector, vp=vp, elem=elem)
                    path = _download(url, cache / f"ndfd_{sector}_{vp}_{elem}.bin", ua)
                    for valid, la, lo, v in _messages(path, box):
                        lat, lon = la, lo
                        if key == "snow":  # 6-h accumulations: keep periods ending after now, within window
                            if now_utc < valid <= end + timedelta(hours=5):
                                grids.append((valid, v))
                        elif now_utc - timedelta(hours=1) <= valid <= end:
                            grids.append((valid, v))
                if lat is None or not _covers(lat, lon, box):
                    raise RuntimeError(f"{sector} sector doesn't cover the map")
                if not grids:
                    raise RuntimeError("no forecast times in range")
                stack = np.stack([g for _, g in grids])
                if key == "snow":
                    field = np.nansum(stack, axis=0) * 39.3701  # m -> in
                else:
                    field = np.nanmax(stack, axis=0) * 2.23694  # m/s -> mph
                out[key] = {"lat": lat, "lon": lon, "val": field,
                            "start": min(t for t, _ in grids) - (timedelta(hours=6) if key == "snow" else timedelta()),
                            "end": max(t for t, _ in grids), "sector": sector}
                if debug:
                    print(f"   [ndfd] {key}: {sector}, {len(grids)} times, max {np.nanmax(field):.1f}")
                break
            except Exception as ex:
                if debug:
                    print(f"   [ndfd] {key} from {sector} failed: {ex}")
                last = ex
        else:
            out["errors"].append(f"NDFD {key}: {last}")
            print(f"  ! NDFD {key} map unavailable: {last}")
    return out


# ------------------------------------------------------------------ drawing
def _cell_painter(field, bins, alpha=255):
    """Draw every grid cell as a quad whose corners are midpoints between cell centres."""
    import numpy as np
    lat, lon, val = field["lat"], field["lon"], field["val"]

    def pad(a):
        a = np.pad(a, 1, mode="edge")
        a[0, :] = 2 * a[1, :] - a[2, :]
        a[-1, :] = 2 * a[-2, :] - a[-3, :]
        a[:, 0] = 2 * a[:, 1] - a[:, 2]
        a[:, -1] = 2 * a[:, -2] - a[:, -3]
        return (a[:-1, :-1] + a[1:, :-1] + a[:-1, 1:] + a[1:, 1:]) / 4  # corners, shape (ny+1, nx+1)

    clat, clon = pad(lat), pad(lon)

    def paint(d, proj):
        ny, nx = val.shape
        for j in range(ny):
            row = val[j]
            for i in range(nx):
                v = row[i]
                if v != v:  # NaN
                    continue
                col = _bin(v, bins)
                if not col:
                    continue
                d.polygon([proj(clon[j, i], clat[j, i]), proj(clon[j, i + 1], clat[j, i + 1]),
                           proj(clon[j + 1, i + 1], clat[j + 1, i + 1]), proj(clon[j + 1, i], clat[j + 1, i])],
                          fill=(*col, alpha))
    return paint


def _value_at(field, lon, lat):
    import numpy as np
    d = (field["lat"] - lat) ** 2 + ((field["lon"] - lon) * np.cos(np.radians(lat))) ** 2
    j, i = np.unravel_index(np.nanargmin(d), d.shape)
    v = field["val"][j, i]
    return None if v != v else float(v)


def _color_bar(cv, x, y, bins, unit, maxw):
    bw = min(maxw, 64 * len(bins) + 40)
    cv.rect(x, y, bw, 58, (13, 21, 38, 225), r=10)
    seg = (bw - 40) / len(bins)
    for i, (t, c) in enumerate(bins):
        cv.rect(x + 10 + i * seg, y + 8, seg, 18, (*c, 255))
        cv.text(x + 10 + i * seg, y + 48, f"{t:g}", 17, "bold", anchor="ls")
    cv.text(x + bw - 10, y + 48, unit, 15, "bold", C["muted"], anchor="rs")


def _snow_txt(v):
    if v is None or v < 0.1:
        return "NONE"
    if v < 1:
        return 'UNDER 1"'
    steps = [(2, '1–2"'), (3, '2–3"'), (4, '3–4"'), (6, '4–6"'), (8, '6–8"'), (10, '8–10"'),
             (12, '10–12"'), (18, '12–18"'), (24, '18–24"')]
    return next((t for lim, t in steps if v < lim), '24"+')


def _map_graphic(field, bins, unit, title, subtitle, head_txt, meaning, rows, pkg, cfg, fmt_row):
    cv = Canvas(cfg)
    cv.header(title, subtitle)
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    lay = outlookmap.draw_map([], mw, mh, cfg, outline=False, painter=_cell_painter(field, bins))
    _paste_rounded(cv, lay, mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    _color_bar(cv, mx + 16, my + mh - 70, bins, unit, mw - 32)
    hv = _value_at(field, cfg["location"]["lon"], cfg["location"]["lat"])
    head_col = _bin(hv or 0, bins) or (70, 86, 112)
    side_rows = []
    for name, la, lo in cfg.get("outlook_points") or outlookmap.POINTS:
        v = _value_at(field, lo, la)
        side_rows.append((name, _bin(v or 0, bins), fmt_row(v)))
    outlookmap._side(cv, px, py, pw_, ph_, head_col, cfg["location"].get("area", "Hampton Roads Area").upper(),
                     head_txt(hv), meaning(hv), side_rows, "LOCAL FORECAST")
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "National Weather Service (NDFD)"
    cv.footer(pkg, source=src)
    from . import fullscreen
    fullscreen.attach(cv, title=title, subtitle=subtitle,
                      map_fn=lambda pw, ph, view: outlookmap.draw_map([], pw, ph, cfg, outline=False,
                                                                       painter=_cell_painter(field, bins), view=view),
                      box=tuple(cfg.get("outlook_view") or outlookmap.VIEW_BOX),
                      head_label=cfg["location"].get("area", "Hampton Roads Area").upper(), head_value=head_txt(hv),
                      head_col=head_col, meaning=meaning(hv), rows=side_rows,
                      overlay=lambda c, x, y, mw_: _color_bar(c, x, y, bins, unit, mw_), source=src)
    return cv


def _when(t, tz):
    lt = t.astimezone(tz)
    return f"{lt.strftime('%a').upper()} {lt.strftime('%I %p').lstrip('0')}"


def ndfd_maps(pkg, cfg):
    data = pkg.get("_ndfdmaps")
    if not data:
        return None
    tz = ZoneInfo(cfg["timezone"])
    out = []
    snow = data.get("snow")
    if snow is not None:
        import numpy as np
        mx = float(np.nanmax(snow["val"])) if snow["val"].size else 0
        if mx >= cfg.get("snow_map_min", 0.1) or cfg.get("snow_map_always"):
            out.append(("snow_map", _map_graphic(
                snow, SNOW_BINS, "IN", "SNOWFALL FORECAST",
                f"THROUGH {_when(snow['end'], tz)}  ·  NATIONAL WEATHER SERVICE",
                lambda v: _snow_txt(v) if v and v >= 0.1 else "NO SNOW EXPECTED",
                lambda v: (f"NWS forecast snowfall for the Hampton Roads area: {_snow_txt(v).lower().replace('–', ' to ')}. "
                           "Totals can shift quickly with small changes in the storm track.") if v and v >= 0.1
                else "No accumulating snow is in the NWS forecast for the Hampton Roads area.",
                None, pkg, cfg, lambda v: _snow_txt(v).replace("UNDER", "<"))))
        else:
            print("  - snow_map: no snow in the forecast, skipped")
    for key, label in (("wind", "SUSTAINED WINDS"), ("gust", "WIND GUSTS")):
        f = data.get(key)
        if f is None:
            continue
        step = cfg.get("gust_round_to", 5) if key == "gust" else 1  # gusts: nearest 5 mph (10, 15, 20...)
        rnd = lambda v, step=step: int(step * round(v / step))
        out.append((f"{key}_map", _map_graphic(
            f, WIND_BINS, "MPH", "WIND FORECAST" if key == "wind" else "PEAK WIND GUSTS",
            f"{'MAX ' if key == 'wind' else ''}{label}  ·  NEXT 24 HOURS  ·  NATIONAL WEATHER SERVICE",
            lambda v: f"{rnd(v)} MPH" if v is not None else "N/A",
            (lambda v: f"Strongest sustained winds in the Hampton Roads area over the next 24 hours: around {rnd(v)} mph."
             if v is not None else "Wind data unavailable.") if key == "wind" else
            (lambda v: f"Peak gusts in the Hampton Roads area over the next 24 hours: up to {rnd(v)} mph."
             + (" Secure loose outdoor items." if v and v >= 35 else "") if v is not None else "Wind data unavailable."),
            None, pkg, cfg, lambda v: f"{rnd(v)} mph" if v is not None else "--")))
    return out or None


# ------------------------------------------------------------------ sample data
def sample(now_utc):
    """Synthetic NDFD-like grids (2.5 km) for offline testing: a coastal snowstorm + windy day."""
    import numpy as np
    lat = np.linspace(34.9, 39.3, 190)[:, None] * np.ones((1, 230))
    lon = np.ones((190, 1)) * np.linspace(-79.8, -73.8, 230)[None, :]
    blob = lambda cx, cy, sx, sy: np.exp(-(((lon - cx) / sx) ** 2 + ((lat - cy) / sy) ** 2))
    snow = 9 * blob(-76.6, 36.7, 1.1, 0.55) + 3 * blob(-77.8, 37.4, 0.9, 0.6) - 0.6
    wind = 12 + 22 * blob(-75.4, 36.3, 1.2, 1.0) + 6 * blob(-76.2, 37.4, 0.8, 0.5)
    gust = wind * 1.45 + 3
    mk = lambda v, hrs: {"lat": lat, "lon": lon, "val": v, "start": now_utc, "end": now_utc + timedelta(hours=hrs),
                         "sector": "sample"}
    return {"snow": mk(np.clip(snow, 0, None), 48), "wind": mk(wind, 24), "gust": mk(gust, 24), "errors": []}
