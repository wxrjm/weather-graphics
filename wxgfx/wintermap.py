"""WPC winter graphics on the county stencil (keyless NOAA map services):

  * Snow / ice probabilities - WPC Probabilistic Winter Precipitation (PWPF): chance of at least
    4", 8", 12" of snow and 0.25"+ of ice for Days 1-3.
      https://mapservices.weather.noaa.gov/vector/rest/services/precip/wpc_prob_winter_precip/MapServer
  * Winter Storm Severity Index (WSSI) - overall impact, Days 1, 2, 3 and 1-3.
      https://mapservices.weather.noaa.gov/vector/rest/services/outlooks/wpc_wssi/MapServer

Each map comes as a Hampton Roads version and (winter_state_map) a Virginia & North Carolina version.
Maps with nothing in the map area are skipped, so out of season this makes no graphics.
"""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import outlooks
from .alertmap import _paste_rounded
from .outlookmap import DMA_POINTS, POINTS, STATE_CITIES, STATE_VIEW, _legend_chips, _side, draw_map
from .theme import Canvas, z

PWPF_SERVICE = f"{outlooks.MAPSERVICES}/precip/wpc_prob_winter_precip/MapServer"
WSSI_SERVICE = f"{outlooks.MAPSERVICES}/outlooks/wpc_wssi/MapServer"

# WPC publishes these as three probability bands
SNOW_PROB = [  # level, label, fill, word
    (1, "10–39%", (140, 190, 245), "a low"),
    (2, "40–69%", (54, 110, 225), "a moderate"),
    (3, "70%+", (140, 64, 200), "a high"),
]
ICE_PROB = [
    (1, "10–39%", (245, 182, 224), "a low"),
    (2, "40–69%", (214, 93, 177), "a moderate"),
    (3, "70%+", (139, 30, 122), "a high"),
]
WSSI_CATS = [  # level, code, label, official WSSI fill, what to expect (WPC's impact descriptions)
    (1, "WINTER WEATHER AREA", "Winter Weather Area", (210, 223, 231),
     "Expect winter weather. Remain alert and use caution while traveling."),
    (2, "MINOR", "Minor Impacts", (250, 245, 163),
     "Expect a few inconveniences to normal activities. Use caution while driving."),
    (3, "MODERATE", "Moderate Impacts", (247, 150, 47),
     "Expect disruptions to daily life. Hazardous driving conditions; use extra caution. Closures are possible."),
    (4, "MAJOR", "Major Impacts", (230, 31, 38),
     "Expect considerable disruptions to daily life. Dangerous or impossible driving; avoid travel if possible."),
    (5, "EXTREME", "Extreme Impacts", (120, 83, 161),
     "Expect substantial disruptions. Travel not advised; extensive closures. Life-saving actions may be needed."),
]
CHIP = {1: "WINTER WX", 2: "MINOR", 3: "MODERATE", 4: "MAJOR", 5: "EXTREME"}


# ------------------------------------------------------------------ classification
def prob_level(props):
    """PWPF 'outlook' is like 'Slight (10-39%)' / 'SLGT: AT LEAST 10% PROB'; dn is a numeric code."""
    s = " ".join(str(v) for k, v in props.items() if isinstance(v, str) and k.lower() in ("outlook", "label", "name"))
    up = s.upper()
    if up:
        if "HIGH" in up or "70" in up:
            return 3
        if "MOD" in up or "MDT" in up or "40" in up:
            return 2
        if "SLGT" in up or "SLIGHT" in up or "10" in up:
            return 1
    dn = props.get("dn", props.get("DN"))
    if isinstance(dn, (int, float)):
        if dn >= 70:
            return 3
        if dn >= 40:
            return 2
        if dn >= 10:
            return 1
        if 1 <= dn <= 3:
            return int(dn)
    return None


def wssi_level(props):
    s = str(props.get("impact") or props.get("IMPACT") or "").upper()
    if not s:
        s = " ".join(str(v) for v in props.values() if isinstance(v, str)).upper()
    for lvl, code, *_ in reversed(WSSI_CATS):
        if code in s:
            return lvl
    if "LIMITED" in s:
        return 1
    return None


def _norm(feats, levelf):
    out = []
    for f in feats:
        props = f.get("properties") or {}
        lvl = levelf(props)
        polys = outlooks.polys_of(f.get("geometry"))
        if not lvl or not polys or not outlooks._in_view(polys):
            continue
        out.append({"level": lvl, "polys": polys, "times": {k: str(v) for k, v in outlooks._times(props).items()}})
    out.sort(key=lambda x: x["level"])
    return out


# ------------------------------------------------------------------ fetch
def _layer_name(n):
    return n.replace("_", " ").lower()


def fetch_all(cfg, debug=False):
    fx = outlooks.Fetcher(cfg["user_agent"], debug)
    res = {"snow": {}, "ice": {}, "wssi": {}, "errors": []}
    days = cfg.get("winter_days", [1, 2, 3])
    for d in days:
        for thr in cfg.get("snow_prob_thresholds", [4, 8, 12]):
            try:
                lid, name = fx.find_layer(PWPF_SERVICE, lambda n: re.search(rf"day\s*{d}\b", _layer_name(n))
                                          and "snow" in n and re.search(rf"\b{thr}\s*inch", _layer_name(n)))
                if lid is None:
                    raise RuntimeError("layer not found (run --outlook-debug)")
                data = fx.query(PWPF_SERVICE, lid)
                feats = data.get("features", [])
                fx.log(f"PWPF day {d} {thr}in: layer '{name}', {len(feats)} features")
                if feats:
                    fx.log("  sample properties:", feats[0].get("properties"))
                res["snow"].setdefault(d, {})[thr] = _norm(feats, prob_level)
            except Exception as e:
                res["errors"].append(f"WPC snow probability day {d} {thr}in: {e}")
        if cfg.get("ice_prob", True):
            try:
                lid, name = fx.find_layer(PWPF_SERVICE, lambda n: re.search(rf"day\s*{d}\b", _layer_name(n)) and "ic" in n
                                          and ("icing" in n or "ice" in n))
                if lid is None:
                    raise RuntimeError("layer not found (run --outlook-debug)")
                res["ice"][d] = _norm(fx.query(PWPF_SERVICE, lid).get("features", []), prob_level)
            except Exception as e:
                res["errors"].append(f"WPC ice probability day {d}: {e}")
    for period in cfg.get("wssi_periods", ["1", "2", "3", "1-3"]):
        a, _, b = period.partition("-")

        def want(n, a=a, b=b):
            n = _layer_name(n)
            if "overall" not in n and "impact" not in n:
                return False
            m = re.search(r"days?\s*(\d)(?:\s*[-–]\s*(\d))?", n)
            return bool(m) and m.group(1) == a and (m.group(2) or "") == b
        try:
            lid, name = fx.find_layer(WSSI_SERVICE, want)
            if lid is None:
                raise RuntimeError("layer not found (run --outlook-debug)")
            data = fx.query(WSSI_SERVICE, lid)
            feats = data.get("features", [])
            fx.log(f"WSSI {period}: layer '{name}', {len(feats)} features")
            if feats:
                fx.log("  sample properties:", feats[0].get("properties"))
            res["wssi"][period] = _norm(feats, wssi_level)
        except Exception as e:
            res["errors"].append(f"WSSI {period}: {e}")
    for e in res["errors"]:
        print(f"  ! {e}")
    return res


# ------------------------------------------------------------------ graphics
def _start_date(day, feats, now_utc):
    for f in feats[:1]:
        t = outlooks._parse_time(f["times"].get("start"))
        if t:
            return t.date()
    return (now_utc - timedelta(hours=12)).date() + timedelta(days=day - 1)


def _period_label(period, feats, pkg, cfg):
    """'DAY 1 · TODAY, SEP 30' or 'DAYS 1-3 · SEP 30 – OCT 2'. WPC days run 7 AM -> 7 AM (12Z)."""
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.fromisoformat(pkg["issued"]).astimezone(timezone.utc)
    today = now.astimezone(tz).date()
    a, _, b = str(period).partition("-")
    d0 = _start_date(int(a), feats, now)
    md = lambda d: f"{d.strftime('%b').upper()} {d.day}"
    if b:
        d1 = d0 + timedelta(days=int(b) - int(a))
        return f"DAYS {a}-{b}  ·  {md(d0)} – {md(d1)}"
    name = "TODAY" if d0 == today else "TOMORROW" if d0 == today + timedelta(days=1) else d0.strftime("%A").upper()
    return f"DAY {a}  ·  {name}, {md(d0)}"


def _at(feats, lon, lat):
    return max((f["level"] for f in feats if outlooks.contains(f["polys"], lon, lat)), default=0)


def _frame(cv, feats, colors, cfg, statewide, outline):
    (mx, my, mw, mh), panel = cv.split()
    layers = [(colors[f["level"]], f["polys"]) for f in feats]
    if statewide:
        dma = set(cfg.get("dma_counties") or (cfg.get("alert_counties") or []) + ["37055"])
        lay = draw_map(layers, mw, mh, cfg, outline=outline, view=cfg.get("state_view") or STATE_VIEW, dma=dma,
                       cities=cfg.get("state_map_cities") or STATE_CITIES)
    else:
        lay = draw_map(layers, mw, mh, cfg, outline=outline)
    _paste_rounded(cv, lay, mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    return (mx, my, mw, mh), panel


def _full(cv, title, subtitle, feats, colors, cfg, statewide, outline, chips, val, head_col, meaning, rows, pkg):
    from . import fullscreen
    layers = [(colors[f["level"]], f["polys"]) for f in feats]
    if statewide:
        dma = set(cfg.get("dma_counties") or (cfg.get("alert_counties") or []) + ["37055"])
        mfn = lambda pw, ph, view: draw_map(layers, pw, ph, cfg, outline=outline, view=view, dma=dma,
                                            cities=cfg.get("state_map_cities") or STATE_CITIES)
        box = tuple(cfg.get("state_view") or STATE_VIEW)
    else:
        from .outlookmap import VIEW_BOX
        mfn = lambda pw, ph, view: draw_map(layers, pw, ph, cfg, outline=outline, view=view)
        box = tuple(cfg.get("outlook_view") or VIEW_BOX)
    fullscreen.attach(cv, title=title, subtitle=subtitle, map_fn=mfn, box=box,
                      head_label=cfg["location"].get("area", "HAMPTON ROADS AREA").upper(), head_value=val,
                      head_col=head_col, meaning=meaning, rows=rows,
                      overlay=lambda c, x, y, mw_: _legend_chips(c, x, y, chips, mw_), source=_src(pkg))
    return cv


def _points(cfg, statewide):
    return (cfg.get("dma_points") or DMA_POINTS) if statewide else (cfg.get("outlook_points") or POINTS)


def _src(pkg):
    return "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NOAA Weather Prediction Center"


def prob_graphic(kind, day, thr, feats, pkg, cfg, statewide=False):
    cats = SNOW_PROB if kind == "snow" else ICE_PROB
    colors = {c[0]: c[2] for c in cats}
    amount = f'{thr}"+ OF SNOW' if kind == "snow" else '0.25"+ OF ICE'
    cv = Canvas(cfg)
    where = "VIRGINIA & NORTH CAROLINA  ·  " if statewide else ""
    title = "SNOWFALL PROBABILITY" if kind == "snow" else "ICE PROBABILITY"
    subtitle = f"{where}CHANCE OF {amount}  ·  {_period_label(day, feats, pkg, cfg)}"
    cv.header(title, subtitle)
    (mx, my, mw, mh), (px, py, pw_, ph_) = _frame(cv, feats, colors, cfg, statewide, outline=True)
    _legend_chips(cv, mx + 16, my + mh - 60, [(c[2], c[1]) for c in cats], mw - 32)
    loc = cfg["location"]
    lvl = _at(feats, loc["lon"], loc["lat"])
    what = f"at least {thr} inches of snow" if kind == "snow" else "at least a quarter inch of ice"
    if lvl:
        c = cats[lvl - 1]
        val, head_col = f"{c[1]} CHANCE", c[2]
        meaning = f"WPC gives the Hampton Roads area {c[3]} ({c[1]}) chance of {what} on Day {day}."
    else:
        val, head_col = "UNDER 10%", (70, 86, 112)
        meaning = f"The chance of {what} in the Hampton Roads area on Day {day} is less than 10%."
    rows = []
    for name, la, lo in _points(cfg, statewide):
        pl = _at(feats, lo, la)
        rows.append((name, cats[pl - 1][2] if pl else None, cats[pl - 1][1] if pl else "< 10%"))
    _side(cv, px, py, pw_, ph_, head_col, cfg["location"].get("area", "HAMPTON ROADS AREA").upper(), val, meaning,
          rows, f"CHANCE OF {amount}  ·  " + ("HAMPTON ROADS DMA" if statewide else "LOCAL"))
    cv.footer(pkg, source=_src(pkg))
    return _full(cv, title, subtitle, feats, colors, cfg, statewide, True, [(c[2], c[1]) for c in cats], val, head_col,
                 meaning, rows, pkg)


def wssi_graphic(period, feats, pkg, cfg, statewide=False):
    colors = {c[0]: c[3] for c in WSSI_CATS}
    cv = Canvas(cfg)
    where = "VIRGINIA & NORTH CAROLINA  ·  " if statewide else ""
    subtitle = f"{where}{_period_label(period, feats, pkg, cfg)}  ·  EXPECTED IMPACTS"
    cv.header("WINTER STORM SEVERITY INDEX", subtitle)
    (mx, my, mw, mh), (px, py, pw_, ph_) = _frame(cv, feats, colors, cfg, statewide, outline=False)
    _legend_chips(cv, mx + 16, my + mh - 60, [(c[3], CHIP[c[0]]) for c in WSSI_CATS], mw - 32)
    loc = cfg["location"]
    lvl = _at(feats, loc["lon"], loc["lat"])
    if lvl:
        c = WSSI_CATS[lvl - 1]
        val, head_col, meaning = c[2].upper(), c[3], c[4]
    else:
        val, head_col = "NO IMPACTS", (70, 86, 112)
        meaning = "No winter storm impacts are expected in the Hampton Roads area over this period."
    rows = []
    for name, la, lo in _points(cfg, statewide):
        pl = _at(feats, lo, la)
        rows.append((name, WSSI_CATS[pl - 1][3] if pl else None, CHIP[pl] if pl else "NONE"))
    _side(cv, px, py, pw_, ph_, head_col, cfg["location"].get("area", "HAMPTON ROADS AREA").upper(), val, meaning,
          rows, "HAMPTON ROADS DMA IMPACTS" if statewide else "LOCAL IMPACTS")
    cv.footer(pkg, source=_src(pkg))
    return _full(cv, "WINTER STORM SEVERITY INDEX", subtitle, feats, colors, cfg, statewide, False,
                 [(c[3], CHIP[c[0]]) for c in WSSI_CATS], val, head_col, meaning, rows, pkg)


def winter_graphics(pkg, cfg):
    data = pkg.get("_winter")
    if not data:
        return None
    always = cfg.get("winter_always", False)
    states = [False, True] if cfg.get("winter_state_map", True) else [False]
    out = []

    def add(name, feats, make):
        if not feats and not always:
            print(f"  - {name}: nothing in the map area, skipped")
            return
        for st in states:
            out.append((name + ("_state" if st else ""), make(st)))

    for day, by_thr in sorted((data.get("snow") or {}).items(), key=lambda kv: int(kv[0])):
        for thr, feats in sorted(by_thr.items(), key=lambda kv: float(kv[0])):
            add(f"snow_prob_{thr}in_day{day}", feats,
                lambda st, d=int(day), t=thr, f=feats: prob_graphic("snow", d, t, f, pkg, cfg, st))
    for day, feats in sorted((data.get("ice") or {}).items(), key=lambda kv: int(kv[0])):
        add(f"ice_prob_day{day}", feats, lambda st, d=int(day), f=feats: prob_graphic("ice", d, None, f, pkg, cfg, st))
    for period, feats in sorted((data.get("wssi") or {}).items(), key=lambda kv: (len(kv[0]), kv[0])):
        a, _, b = period.partition("-")
        tag = f"days{a}-{b}" if b else f"day{a}"
        add(f"wssi_{tag}", feats, lambda st, p=period, f=feats: wssi_graphic(p, f, pkg, cfg, st))
    return out or None


def sample():
    """Made-up winter storm west/north of Hampton Roads for offline testing."""
    from .sample import _ellipse
    band = lambda lvls: [{"level": l, "polys": _ellipse(cx, cy, rx, ry, 0.5, wobble=0.07), "times": {}}
                         for l, (cx, cy, rx, ry) in lvls]
    snow1 = {4: band([(1, (-78.2, 37.4, 2.4, 1.2)), (2, (-78.0, 37.5, 1.5, 0.8)), (3, (-77.9, 37.6, 0.8, 0.45))]),
             8: band([(1, (-78.4, 37.7, 1.4, 0.7)), (2, (-78.3, 37.8, 0.7, 0.4))]),
             12: band([(1, (-78.6, 37.9, 0.6, 0.35))])}
    snow2 = {4: band([(1, (-76.8, 36.9, 1.6, 0.9)), (2, (-76.6, 36.9, 0.8, 0.5))]), 8: [], 12: []}
    wssi = lambda s: band([(1, (-77.8 + s, 37.2, 3.0, 1.6)), (2, (-77.7 + s, 37.3, 2.0, 1.1)),
                           (3, (-77.9 + s, 37.5, 1.2, 0.7)), (4, (-78.3 + s, 37.7, 0.5, 0.3))])
    return {"snow": {1: snow1, 2: snow2, 3: {4: [], 8: [], 12: []}},
            "ice": {1: band([(1, (-79.2, 36.4, 1.2, 0.5)), (2, (-79.3, 36.4, 0.5, 0.25))]), 2: [], 3: []},
            "wssi": {"1": wssi(0), "2": band([(1, (-76.6, 36.9, 1.8, 1.0)), (2, (-76.5, 36.9, 0.9, 0.5))]),
                     "3": [], "1-3": wssi(0.4)},
            "errors": []}
