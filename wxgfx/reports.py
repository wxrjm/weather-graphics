"""Observed-report graphics (all free, no keys):

  * rain_reports        CoCoRaHS 24-hour rain totals (7 AM observations) via the Iowa Environmental Mesonet:
                        https://mesonet.agron.iastate.edu/api/1/daily.geojson?network=VA_COCORAHS&date=YYYY-MM-DD
  * storm_snow_reports  \\
  * storm_rain_reports   >  NWS Local Storm Reports (IEM: geojson/lsr.geojson?wfos=AKQ) and Public Information
  * storm_wind_reports  /   Statements (api.weather.gov PNS products, the **METADATA** report block)

Values are plotted as colored tags on the county map, highest first (lower ones that would overlap are dropped),
with the top reports listed in the side panel. A graphic is only made when there are reports to show.
"""
import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from PIL import ImageDraw

from . import fullscreen, outlooks
from .alertmap import DEFAULT_CITIES, _paste_rounded
from .outlookmap import VIEW_BOX, _side, _view, draw_map
from .theme import Canvas, font, z

IEM = "https://mesonet.agron.iastate.edu"
NWS = "https://api.weather.gov"
SNOW_COLS = [(0.1, (190, 215, 255)), (1, (130, 175, 255)), (2, (80, 130, 245)), (4, (60, 80, 220)), (6, (130, 70, 210)),
             (8, (175, 60, 200)), (12, (220, 70, 170)), (18, (240, 120, 200))]
WIND_COLS = [(0, (120, 200, 255)), (30, (110, 220, 140)), (40, (250, 220, 60)), (50, (250, 150, 40)), (58, (230, 50, 40)),
             (75, (190, 60, 210))]


def _col(v, bins):
    c = bins[0][1]
    for t, cc in bins:
        if v >= t - 1e-9:
            c = cc
    return c


def rain_col(v):
    return outlooks.qpf_color(max(v, 0.01))


def _get(url, ua, accept="application/geo+json"):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": accept})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _in_box(lon, lat, box, pad=0.3):
    w, e, s, n = box
    return w - pad <= lon <= e + pad and s - pad <= lat <= n + pad


# ------------------------------------------------------------------ CoCoRaHS
def cocorahs_day(ua, day, states, box):
    out = []
    for st in states:
        q = urllib.parse.urlencode({"network": f"{st}_COCORAHS", "date": day.isoformat()})
        d = _get(f"{IEM}/api/1/daily.geojson?{q}", ua)
        for f in d.get("features", []):
            p, g = f.get("properties") or {}, f.get("geometry") or {}
            if g.get("type") != "Point" or p.get("precip") is None:
                continue
            lon, lat = g["coordinates"][:2]
            if not _in_box(lon, lat, box):
                continue
            v = float(p["precip"])
            out.append({"name": p.get("name") or p.get("station"), "lat": lat, "lon": lon,
                        "value": 0.001 if 0 < v < 0.005 else round(v, 2), "id": p.get("station")})
    return out


def fetch_cocorahs(cfg, now):
    ua = cfg["user_agent"]
    box = tuple(cfg.get("reports_view") or cfg.get("outlook_view") or VIEW_BOX)
    states = cfg.get("cocorahs_states", ["VA", "NC", "MD"])
    for day in (now.date(), now.date() - timedelta(days=1)):  # morning reports trickle in; fall back to yesterday
        reps = cocorahs_day(ua, day, states, box)
        if len(reps) >= cfg.get("cocorahs_min_reports", 15):
            return {"date": day.isoformat(), "reports": reps}
    return {"date": day.isoformat(), "reports": reps}


# ------------------------------------------------------------------ LSR + PNS
def _kind(text):
    t = (text or "").upper()
    if "SNOW" in t or "SLEET" in t:
        return "snow"
    if "RAIN" in t or "PRECIP" in t:
        return "rain"
    if "GUST" in t or "WND" in t or "WIND" in t:
        return "wind"
    return None


def parse_lsr(d):
    out = []
    for f in d.get("features", []):
        p = f.get("properties") or {}
        kind = _kind(p.get("typetext"))
        if kind is None or "DMG" in (p.get("typetext") or ""):
            continue
        try:
            v = float(p.get("magnitude"))
        except (TypeError, ValueError):
            continue
        if (p.get("unit") or "").upper() in ("KT", "KTS", "KNOTS"):
            v *= 1.15078
        out.append({"kind": kind, "value": round(v, 2), "lat": float(p["lat"]), "lon": float(p["lon"]),
                    "name": p.get("city") or "", "time": p.get("valid"), "src": "LSR",
                    "note": (p.get("remark") or "")[:120]})
    return out


def parse_pns_metadata(text):
    """NWS PNS '**METADATA**' lines:
    :10/01/2026,0700 AM, VA, Virginia Beach, 2 SW Virginia Beach, 36.80, -76.02, RAIN, 2.35, Inch, CoCoRaHS, 24 hr total"""
    out = []
    if "METADATA" not in (text or "").upper():
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith(":") or line.count(",") < 8:
            continue
        f = [x.strip() for x in line[1:].split(",")]
        try:
            lat, lon = float(f[5]), float(f[6])
            v = float(f[8])
        except (ValueError, IndexError):
            continue
        kind = _kind(f[7])
        if kind is None:
            continue
        unit = f[9].upper() if len(f) > 9 else ""
        if unit.startswith("KT") or unit.startswith("KNOT"):
            v *= 1.15078
        out.append({"kind": kind, "value": round(v, 2), "lat": lat, "lon": lon, "name": f[4] or f[3],
                    "time": f"{f[0]} {f[1]}", "src": "PNS", "note": f[11] if len(f) > 11 else ""})
    return out


def fetch_storm(cfg, now):
    ua = cfg["user_agent"]
    wfo = cfg.get("cwf_office", "AKQ")
    hours = cfg.get("storm_reports_hours", 24)
    box = tuple(cfg.get("storm_reports_view") or (-77.9, -75.2, 35.8, 38.0))
    sts = (now.astimezone(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%MZ")
    ets = (now.astimezone(timezone.utc) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%MZ")
    reps, errs = [], []
    try:
        reps += parse_lsr(_get(f"{IEM}/geojson/lsr.geojson?wfos={wfo}&sts={sts}&ets={ets}", ua))
    except Exception as e:
        errs.append(f"LSR: {e}")
    try:
        lst = _get(f"{NWS}/products/types/PNS/locations/{wfo}", ua, "application/ld+json")
        cutoff = now.astimezone(timezone.utc) - timedelta(hours=hours)
        for item in (lst.get("@graph") or [])[:8]:
            t = datetime.fromisoformat(item["issuanceTime"].replace("Z", "+00:00"))
            if t < cutoff:
                continue
            prod = _get(item["@id"], ua, "application/ld+json")
            reps += parse_pns_metadata(prod.get("productText") or "")
    except Exception as e:
        errs.append(f"PNS: {e}")
    reps = [r for r in reps if _in_box(r["lon"], r["lat"], box, 0)]
    seen, uniq = set(), []
    for r in sorted(reps, key=lambda r: -r["value"]):  # drop the same report showing up in both LSR and PNS
        key = (r["kind"], round(r["lat"], 2), round(r["lon"], 2), round(r["value"], 1))
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    for e in errs:
        print(f"  ! storm reports {e}")
    return {"hours": hours, "reports": uniq, "box": box}


def fetch(cfg, now, want):
    out = {}
    if "rain_reports" in want:
        try:
            out["cocorahs"] = fetch_cocorahs(cfg, now)
        except Exception as e:
            print(f"  ! CoCoRaHS: {e}")
    if "storm_reports" in want:
        out["storm"] = fetch_storm(cfg, now)
    return out


# ------------------------------------------------------------------ drawing
def _fmt(kind, v):
    if kind == "wind":
        return f"{v:.0f}"
    if kind == "rain" and 0 < v < 0.005:
        return "T"
    return f"{v:.2f}" if kind == "rain" else f"{v:.1f}"


def _tag_map(items, kind, color_fn, cfg, pw, ph, view, box):
    """County map with value tags; items sorted high -> low so the biggest numbers win collisions."""
    big = [c for c in DEFAULT_CITIES if (c[3] if len(c) > 3 else 1) == 1]
    lay = draw_map([], pw, ph, cfg, outline=False, view=view or box, cities=[("", 0, 0, 1)])  # cities drawn after tags
    W_, H_ = lay.size
    w, e, s, n = _view(pw, ph, tuple(view or box))
    proj = lambda x, y: ((x - w) / (e - w) * W_, (n - y) / (n - s) * H_)
    d = ImageDraw.Draw(lay, "RGBA")
    f = font("bold", 15)
    placed = []
    from .alertmap import KEEP_OUT
    keep = [tuple(z(v) for v in k) for k in KEEP_OUT]
    for r in sorted(items, key=lambda r: -r["value"]):
        x, y = proj(r["lon"], r["lat"])
        txt = _fmt(kind, r["value"])
        tw = d.textlength(txt, font=f)
        bx = (x - tw / 2 - z(6), y - z(11), x + tw / 2 + z(6), y + z(11))
        if bx[0] < z(4) or bx[2] > W_ - z(4) or bx[1] < z(4) or bx[3] > H_ - z(84):
            continue
        if any(bx[0] < b[2] and bx[2] > b[0] and bx[1] < b[3] and bx[3] > b[1] for b in placed + keep):
            continue
        placed.append(bx)
        col = color_fn(r["value"])
        d.rounded_rectangle(bx, radius=z(6), fill=(*col, 245), outline=(13, 21, 38, 255), width=z(1.5))
        ink = (20, 28, 46) if 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2] > 140 else (255, 255, 255)
        d.text((x, y), txt, font=f, fill=ink, anchor="mm")
    from . import alertmap
    saved = list(alertmap.KEEP_OUT)  # city names only where they don't cover a report
    alertmap.KEEP_OUT[:] = saved + [tuple(v / z(1) for v in b) for b in placed]
    try:
        alertmap.draw_cities(d, proj, W_, H_, cfg, bottom_pad=80, cities=big)
    finally:
        alertmap.KEEP_OUT[:] = saved
    return lay


def _short(name):
    name = re.sub(r"\s+", " ", name or "").strip()
    return name if len(name) <= 24 else name[:23] + "…"


def _graphic(kind, reps, title, subtitle, head_label, meaning, color_fn, unit, box, pkg, cfg, src, list_title):
    cv = Canvas(cfg)
    cv.header(title, subtitle)
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    _paste_rounded(cv, _tag_map(reps, kind, color_fn, cfg, mw, mh, None, box), mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    top = sorted(reps, key=lambda r: -r["value"])
    best = top[0]
    head_val = f"{_fmt(kind, best['value'])}{unit}"
    rows = [(_short(r["name"]), color_fn(r["value"]), f"{_fmt(kind, r['value'])}{unit}") for r in top[:16]]
    _side(cv, px, py, pw_, ph_, color_fn(best["value"]), head_label, head_val, meaning, rows, list_title)
    cv.footer(pkg, source=src)
    fullscreen.attach(cv, title=title, subtitle=subtitle,
                      map_fn=lambda pw, ph, view: _tag_map(reps, kind, color_fn, cfg, pw, ph, view, box), box=box,
                      head_label=head_label, head_value=head_val, head_col=color_fn(best["value"]), meaning=meaning,
                      rows=rows, overlay=None, source=src)
    return cv


def report_graphics(pkg, cfg):
    data = pkg.get("_reports") or {}
    sample = "SAMPLE" in pkg.get("source", "")
    out = []
    co = data.get("cocorahs")
    if co and co.get("reports"):
        reps = co["reports"]
        wet = [r for r in reps if r["value"] >= 0.01]
        mx = max((r["value"] for r in reps), default=0)
        if mx >= cfg.get("rain_reports_min", 0.10) or cfg.get("rain_reports_always", False):
            d = date.fromisoformat(co["date"])
            box = tuple(cfg.get("reports_view") or cfg.get("outlook_view") or VIEW_BOX)
            best = max(reps, key=lambda r: r["value"])
            meaning = (f"{len(reps)} CoCoRaHS observers reported; {len(wet)} measured rain. "
                       f"Highest: {best['value']:.2f}\" at {best['name']}.")
            out.append(("rain_reports", _graphic(
                "rain", reps, "RAINFALL REPORTS", f"COCORAHS 24-HOUR TOTALS  ·  ENDING 7 AM {d.strftime('%a %b').upper()} {d.day}",
                "HIGHEST REPORT", meaning, rain_col, '"', box, pkg, cfg,
                "SAMPLE DATA" if sample else "CoCoRaHS volunteer observers (via Iowa Environmental Mesonet)",
                "TOP TOTALS")))
        else:
            print("  - rain_reports: under 0.10\" everywhere, skipped")
    st = data.get("storm")
    if st:
        hrs = st.get("hours", 24)
        box = tuple(st.get("box") or (-77.9, -75.2, 35.8, 38.0))
        src = "SAMPLE DATA" if sample else "NWS Wakefield storm reports & public information statements"
        specs = [("snow", "SNOWFALL REPORTS", '"', lambda v: _col(v, SNOW_COLS), 0.1, "SNOW"),
                 ("rain", "STORM RAINFALL REPORTS", '"', rain_col, 0.01, "RAIN"),
                 ("wind", "PEAK WIND GUST REPORTS", " MPH", lambda v: _col(v, WIND_COLS), 25, "WIND")]
        for kind, title, unit, cf, least, word in specs:
            reps = [r for r in st["reports"] if r["kind"] == kind and r["value"] >= least]
            if not reps:
                print(f"  - storm_{kind}_reports: no {word.lower()} reports in the last {hrs} hours")
                continue
            best = max(reps, key=lambda r: r["value"])
            what = {"snow": "snowfall", "rain": "rainfall", "wind": "wind gust"}[kind]
            meaning = f"{len(reps)} {what} report{'s' if len(reps) != 1 else ''} in the last {hrs} hours. " \
                      f"Highest: {_fmt(kind, best['value'])}{unit} at {best['name']}."
            out.append((f"storm_{kind}_reports", _graphic(
                kind, reps, title, f"LAST {hrs} HOURS  ·  NWS WAKEFIELD", "HIGHEST REPORT", meaning, cf, unit, box,
                pkg, cfg, src, "TOP REPORTS")))
    return out or None


def sample(now):
    import math
    import random
    rnd = random.Random(3)
    reps = []
    for i in range(140):
        lat, lon = 36.3 + rnd.random() * 2.2, -77.6 + rnd.random() * 2.3
        if lon > -75.6 and lat < 37.0:
            continue
        v = max(0, 1.8 * math.exp(-((lon + 76.2) ** 2 / 0.25 + (lat - 36.85) ** 2 / 0.12)) + 0.35 + rnd.uniform(-0.25, 0.25))
        reps.append({"name": f"Station {i}", "lat": lat, "lon": lon, "value": round(v, 2), "id": f"VA-XX-{i}"})
    for nm, la, lo, v in (("Norfolk 2.1 NW", 36.89, -76.31, 2.41), ("Virginia Beach 3.4 SSE", 36.80, -76.02, 2.18),
                          ("Chesapeake 1.2 E", 36.72, -76.22, 1.96), ("Suffolk 4.0 N", 36.79, -76.58, 1.37),
                          ("Hampton 0.8 W", 37.03, -76.36, 1.55)):
        reps.append({"name": nm, "lat": la, "lon": lo, "value": v, "id": nm})
    storm = []
    for nm, la, lo, v in (("Sandbridge", 36.72, -75.94, 58), ("Oceana NAS", 36.82, -76.03, 52), ("Norfolk Intl", 36.90, -76.19, 47),
                          ("CBBT", 37.03, -76.08, 61), ("Hampton", 37.03, -76.35, 44), ("Duck", 36.18, -75.75, 55),
                          ("Cape Charles", 37.27, -76.02, 49), ("Suffolk", 36.73, -76.58, 38)):
        storm.append({"kind": "wind", "value": v, "lat": la, "lon": lo, "name": nm, "src": "LSR", "time": "", "note": ""})
    for nm, la, lo, v in (("2 SW Virginia Beach", 36.80, -76.02, 3.12), ("Norfolk", 36.85, -76.29, 2.64),
                          ("Portsmouth", 36.84, -76.33, 2.20), ("Chesapeake", 36.72, -76.24, 2.95)):
        storm.append({"kind": "rain", "value": v, "lat": la, "lon": lo, "name": nm, "src": "PNS", "time": "", "note": ""})
    return {"cocorahs": {"date": now.date().isoformat(), "reports": reps},
            "storm": {"hours": 24, "reports": storm, "box": (-77.9, -75.2, 35.8, 38.0)}}
