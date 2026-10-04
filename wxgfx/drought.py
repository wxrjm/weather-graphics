"""U.S. Drought Monitor map (Virginia & North Carolina) + Norfolk rainfall deficits, full-screen layout.

Data (free, no key):
  * Drought Monitor polygons - Esri Living Atlas copy of the weekly USDM map (National Drought Mitigation
    Center), field dm = 0..4 (D0..D4). Backup: FEMA's Drought_Current map service. (droughtmonitor.unl.edu's
    own /data/ folder is off-limits to scripts per its robots.txt, so it isn't used.)
  * Rainfall vs normal - RCC ACIS daily precipitation + 1991-2020 daily normals for Norfolk Intl (ORFthr).
"""
from datetime import date, datetime, timedelta, timezone

from . import fullscreen, outlooks
from .outlookmap import DMA_POINTS, STATE_CITIES, STATE_VIEW, _legend_chips, draw_map

ESRI = "https://services9.arcgis.com/RHVPKKiFTONKtxq3/arcgis/rest/services/US_Drought_Intensity_v1/FeatureServer"
FEMA = "https://gis.fema.gov/arcgis/rest/services/Partner/Drought_Current/MapServer"
ACIS = "https://data.rcc-acis.org/StnData"
CATS = [  # dm, code, name, official USDM color
    (0, "D0", "Abnormally Dry", (255, 255, 0)),
    (1, "D1", "Moderate Drought", (252, 211, 127)),
    (2, "D2", "Severe Drought", (255, 170, 0)),
    (3, "D3", "Extreme Drought", (230, 0, 0)),
    (4, "D4", "Exceptional Drought", (115, 0, 0)),
]
PERIODS = [(30, "LAST 30 DAYS"), (60, "LAST 60 DAYS"), (90, "LAST 90 DAYS"), ("ytd", "SINCE JAN 1")]


def _dm(props):
    for k in ("dm", "DM", "Dm"):
        v = props.get(k)
        if isinstance(v, (int, float)) and 0 <= v <= 4:
            return int(v)
    return None


def fetch_map(cfg, debug=False):
    fx = outlooks.Fetcher(cfg["user_agent"], debug)
    for service, layer in ((ESRI, 3), (FEMA, 0)):
        try:
            data = fx.query(service, layer)
            feats = data.get("features", [])
            out, valid = [], None
            for f in feats:
                p = f.get("properties") or {}
                dm = _dm(p)
                polys = outlooks.polys_of(f.get("geometry"))
                if dm is None or not polys:
                    continue
                out.append({"dm": dm, "polys": polys})
                for k in ("ddate", "DDATE", "valid_end", "map_date"):
                    v = p.get(k)
                    if isinstance(v, (int, float)) and v > 1e11:
                        valid = datetime.fromtimestamp(v / 1000, timezone.utc).date().isoformat()
                    elif isinstance(v, str) and v[:4].isdigit():
                        valid = v[:10] if "-" in v else f"{v[:4]}-{v[4:6]}-{v[6:8]}"
            fx.log(f"drought: {len(out)} areas from {service.split('/services/')[1]}, valid {valid}")
            if feats:
                return {"areas": sorted(out, key=lambda a: a["dm"]), "valid": valid}
        except Exception as e:
            print(f"  ! drought map ({service.split('/')[2]}): {e}")
    return None


def _num(x):
    if x in ("T", "t"):
        return 0.0
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def deficits(rows, today):
    """rows: [[date, obs, normal], ...] -> per-period totals vs normal (days with missing obs are skipped)."""
    out = []
    for per, label in PERIODS:
        start = date(today.year, 1, 1) if per == "ytd" else today - timedelta(days=per - 1)
        obs = norm = 0.0
        n = miss = 0
        for d, o, nm in rows:
            dd = date.fromisoformat(d)
            if dd < start or dd > today:
                continue
            o, nm = _num(o), _num(nm)
            if nm is None:
                continue
            if o is None:
                miss += 1
                continue
            obs += o
            norm += nm
            n += 1
        if n:
            out.append({"label": label, "obs": round(obs, 2), "normal": round(norm, 2), "dep": round(obs - norm, 2),
                        "pct": round(100 * obs / norm) if norm else None, "missing": miss})
    return out


def fetch_rain(cfg, today, ua):
    import json
    import urllib.request
    end = today - timedelta(days=1)  # through yesterday (today isn't complete)
    body = {"sid": cfg.get("acis_station", "ORFthr"), "sdate": date(end.year - 1, end.month, 1).isoformat(),
            "edate": end.isoformat(),
            "elems": [{"name": "pcpn", "interval": "dly"}, {"name": "pcpn", "interval": "dly", "normal": "1"}]}
    req = urllib.request.Request(ACIS, data=json.dumps(body).encode(), headers={"User-Agent": ua,
                                                                                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = json.loads(r.read().decode()).get("data", [])
    return {"through": end.isoformat(), "periods": deficits(rows, end)}


def fetch(cfg, now, debug=False):
    res = {"map": None, "rain": None}
    res["map"] = fetch_map(cfg, debug)
    try:
        res["rain"] = fetch_rain(cfg, now.date(), cfg["user_agent"])
    except Exception as e:
        print(f"  ! Norfolk rainfall (ACIS): {e}")
    return res


def _cat_at(areas, lon, lat):
    best = None
    for a in areas:
        if outlooks.contains(a["polys"], lon, lat) and (best is None or a["dm"] > best):
            best = a["dm"]
    return best


def _md(iso):
    d = date.fromisoformat(iso)
    return f"{d.strftime('%b').upper()} {d.day}"


def drought_graphic(pkg, cfg):
    data = pkg.get("_drought")
    if not data or not (data.get("map") or data.get("rain")):
        return None
    mp = data.get("map") or {"areas": [], "valid": None}
    areas = mp["areas"]
    layers = [(CATS[a["dm"]][3], a["polys"]) for a in areas]
    dma = set(cfg.get("dma_counties") or (cfg.get("alert_counties") or []) + ["37055"])
    box = tuple(cfg.get("drought_view") or STATE_VIEW)

    def map_fn(pw, ph, view):
        return draw_map(layers, pw, ph, cfg, outline=False, view=view, dma=dma,
                        cities=cfg.get("state_map_cities") or STATE_CITIES)

    loc = cfg["location"]
    here = _cat_at(areas, loc["lon"], loc["lat"])
    if here is None:
        head_val, head_col = "NO DROUGHT", (70, 180, 100)
    else:
        c = CATS[here]
        head_val, head_col = f"{c[1]}  ·  {c[2].upper()}", c[3]
    rain = data.get("rain") or {}
    pers = rain.get("periods") or []
    p90 = next((p for p in pers if p["label"] == "LAST 90 DAYS"), None)
    meaning = ""
    if p90:
        meaning = (f"Norfolk has had {p90['obs']:.2f}\" of rain in the last 90 days, "
                   f"{abs(p90['dep']):.2f}\" {'below' if p90['dep'] < 0 else 'above'} normal"
                   + (f" ({p90['pct']}% of normal)." if p90.get("pct") is not None else "."))
    rows = []
    for p in pers:
        col = (230, 60, 50) if p["dep"] <= -1 else (255, 170, 0) if p["dep"] < 0 else (70, 180, 100)
        short = p["label"].replace("LAST ", "").replace("SINCE ", "Since ").title()
        rows.append((short + (f" · {p['pct']}% of normal" if p.get("pct") is not None else ""), col,
                     f"{'+' if p['dep'] >= 0 else '−'}{abs(p['dep']):.2f}\""))
    for name, la, lo in (cfg.get("drought_points") or [DMA_POINTS[1], DMA_POINTS[4], DMA_POINTS[11], DMA_POINTS[14]]):
        dm = _cat_at(areas, lo, la)
        rows.append((name, CATS[dm][3] if dm is not None else None, CATS[dm][1] if dm is not None else "NONE"))
    valid = f"VALID {_md(mp['valid'])}" if mp.get("valid") else "U.S. DROUGHT MONITOR"
    thru = f"  ·  RAIN THROUGH {_md(rain['through'])}" if rain.get("through") else ""

    def legend(cv, x, y, maxw):
        full = maxw > 1500
        _legend_chips(cv, x, y, [(c[3], f"{c[1]} " + (c[2].upper() if full else
                                                    ("DRY" if c[0] == 0 else c[2].split()[0].upper()))) for c in CATS], maxw)

    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "U.S. Drought Monitor (NDMC/USDA/NOAA) · ACIS"
    return fullscreen.render(pkg, cfg, "DROUGHT MONITOR", f"VIRGINIA & NORTH CAROLINA  ·  {valid}{thru}", map_fn, box,
                             "NORFOLK", head_val, head_col, meaning, rows, overlay=legend, source=src)


def sample(now):
    from .sample import _ellipse
    areas = [{"dm": 0, "polys": _ellipse(-78.2, 36.9, 3.4, 1.8, 0.4, wobble=0.07)},
             {"dm": 1, "polys": _ellipse(-77.6, 36.9, 2.2, 1.1, 0.4, wobble=0.08)},
             {"dm": 2, "polys": _ellipse(-77.2, 36.95, 1.0, 0.55, 0.4, wobble=0.08)},
             {"dm": 0, "polys": _ellipse(-80.8, 35.4, 1.2, 0.7, 0.2, wobble=0.06)}]
    end = now.date() - timedelta(days=1)
    rows = []
    d = date(end.year - 1, end.month, 1)
    import math
    while d <= end:
        nm = 0.13 + 0.03 * math.sin(2 * math.pi * (d.timetuple().tm_yday - 200) / 365)
        dry = (end - d).days < 75
        o = (0.9 if d.day % 9 == 0 else 0.0) if dry else (1.0 if d.day % 7 == 0 else 0.05)
        rows.append([d.isoformat(), f"{o:.2f}", f"{nm:.2f}"])
        d += timedelta(days=1)
    return {"map": {"areas": areas, "valid": (now.date() - timedelta(days=2)).isoformat()},
            "rain": {"through": end.isoformat(), "periods": deficits(rows, end)}}
