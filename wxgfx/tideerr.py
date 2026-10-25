"""Sewells Point tide forecast check: how far above or below the NWS (AHPS / NWPS) forecast the recent tides ran.

The NWS gauge page only ever shows the CURRENT forecast, so past forecasts are archived by every run
(cache/tide_forecast_archive.json).  Each observed high/low tide is then compared with what the forecast
issued at least `tide_err_min_lead` hours earlier said that same tide would be.  The graphic fills in as
the archive builds up (run it at least every 6 hours; a day or two of runs gives a full picture).

Live data: NWPS API (the successor of the AHPS hydrograph XML), gauge SWPV2, keyless.
Config: tide_gauge (SWPV2), tide_err_hours (72), tide_err_min_lead (6), tide_err_name.
"""
import json
import math
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .theme import C, Canvas

URL = "https://api.water.noaa.gov/nwps/v1/gauges/{g}/stageflow"
ARCHIVE = "tide_forecast_archive.json"
BLUE, ORANGE, GREY = (88, 170, 255), (255, 150, 50), (150, 165, 190)


def _t(s):
    s = str(s).replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _series(block):
    out = []
    for r in (block or {}).get("data", []):
        v = r.get("primary")
        if v is None or v < -900:
            continue
        out.append((_t(r["validTime"]), float(v)))
    return sorted(out)


def fetch(cfg, cache_dir, now_utc, debug=False):
    """Download the gauge, add the current forecast to the archive, return {obs, archive, name, units}."""
    gauge = cfg.get("tide_gauge", "SWPV2")
    out = {"obs": [], "archive": [], "name": cfg.get("tide_err_name", "SEWELLS POINT"), "errors": []}
    arch_path = cache_dir / ARCHIVE
    arch = []
    try:
        arch = json.loads(arch_path.read_text())
    except Exception:
        pass
    try:
        req = urllib.request.Request(URL.format(g=gauge), headers={"User-Agent": cfg["user_agent"], "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=40) as r:
            j = json.load(r)
        out["obs"] = _series(j.get("observed"))
        fc = _series(j.get("forecast"))
        issued = (j.get("forecast") or {}).get("issuedTime") or now_utc.isoformat()
        if fc and not any(a["issued"] == issued for a in arch):
            arch.append({"issued": issued, "pts": [[t.isoformat(), v] for t, v in fc]})
        out["units"] = (j.get("observed") or {}).get("primaryUnits", "ft")
        if debug:
            print(f"  tide: {len(out['obs'])} obs, {len(fc)} forecast pts, issued {issued}")
    except Exception as ex:
        out["errors"].append(str(ex))
        print(f"  ! Sewells Point gauge unavailable: {ex}")
    cut = (now_utc - timedelta(days=10)).isoformat()
    arch = [a for a in arch if a["issued"] >= cut][-80:]
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        arch_path.write_text(json.dumps(arch))
    except Exception:
        pass
    out["archive"] = [{"issued": _t(a["issued"]), "pts": [(_t(t), v) for t, v in a["pts"]]} for a in arch]
    return out


def sample(now_utc):
    """Synthetic M2 tide + a storm surge the forecast only half caught."""
    def tide(t):
        h = (t - now_utc).total_seconds() / 3600
        return 2.6 + 1.25 * math.sin(2 * math.pi * h / 12.42) + 0.25 * math.sin(2 * math.pi * h / 24.0)

    def surge(t):
        h = (t - now_utc).total_seconds() / 3600
        return 0.9 * math.exp(-((h + 20) / 16) ** 2) - 0.25 * math.exp(-((h + 55) / 12) ** 2)

    t0 = now_utc.replace(minute=0, second=0, microsecond=0)
    obs = [(t0 - timedelta(minutes=30 * k), tide(t0 - timedelta(minutes=30 * k)) + surge(t0 - timedelta(minutes=30 * k)))
           for k in range(0, 2 * 120)][::-1]
    arch = []
    for k in range(16):
        iss = t0 - timedelta(hours=6 * k)
        pts = []
        for m in range(0, 2 * 72):
            t = iss + timedelta(minutes=30 * m)
            h_ahead = (t - iss).total_seconds() / 3600
            pts.append((t, tide(t) + 0.45 * surge(iss) + 0.1 * math.sin(h_ahead / 5)))
        arch.append({"issued": iss, "pts": pts})
    return {"obs": obs, "archive": arch, "name": "SEWELLS POINT", "errors": [], "units": "ft"}


# ------------------------------------------------------------------ analysis
def _extremes(pts, win_h=3.0):
    """Local highs / lows of a series, alternating, using a +/- win_h window."""
    ex = []
    for i, (t, v) in enumerate(pts):
        w = [x for tt, x in pts if abs((tt - t).total_seconds()) <= win_h * 3600]
        if len(w) < 3:
            continue
        if v == max(w) and v > min(w) + 0.5:
            ex.append((t, v, "HIGH"))
        elif v == min(w) and v < max(w) - 0.5:
            ex.append((t, v, "LOW"))
    out = []
    for e in ex:  # one per tide: collapse plateaus / repeats
        if out and out[-1][2] == e[2] and (e[0] - out[-1][0]) < timedelta(hours=5):
            if (e[2] == "HIGH" and e[1] > out[-1][1]) or (e[2] == "LOW" and e[1] < out[-1][1]):
                out[-1] = e
            continue
        out.append(e)
    return out


def analyze(data, now_utc, hours=72, min_lead=6.0):
    obs = [(t, v) for t, v in data.get("obs", []) if t <= now_utc]
    if len(obs) < 10:
        return None
    start = now_utc - timedelta(hours=hours)
    ev = []
    for t, v, kind in _extremes([p for p in obs if p[0] >= start - timedelta(hours=3)]):
        if t < start or t > now_utc - timedelta(hours=2):  # newest tide needs a few hours of data behind it
            continue
        # forecast issued at least min_lead hours ahead (latest such issuance) that covers this time
        cands = [a for a in data.get("archive", []) if a["issued"] <= t - timedelta(hours=min_lead)
                 and a["pts"] and a["pts"][0][0] <= t <= a["pts"][-1][0]]
        if not cands:
            continue
        a = max(cands, key=lambda x: x["issued"])
        near = [(tt, vv) for tt, vv in a["pts"] if abs((tt - t).total_seconds()) <= 2.5 * 3600]
        if not near:
            continue
        ft, fv = (max(near, key=lambda p: p[1]) if kind == "HIGH" else min(near, key=lambda p: p[1]))
        ev.append({"t": t, "kind": kind, "obs": v, "fc": fv, "err": v - fv, "lead": (t - a["issued"]).total_seconds() / 3600})
    return ev or None


# ------------------------------------------------------------------ graphic
def _signed(v, nd=2):
    return f"{v:+.{nd}f}".replace("+0.00", "0.00").replace("-0.00", "0.00")


def tide_error_graphic(pkg, cfg):
    data = pkg.get("_tideerr")
    if not data:
        return None
    now = datetime.fromisoformat(pkg["issued"]).astimezone(timezone.utc)
    hours = cfg.get("tide_err_hours", 72)
    ev = analyze(data, now, hours, cfg.get("tide_err_min_lead", 6.0))
    if not ev:
        print("  - tide_error: no past forecasts archived yet (needs a day or so of runs), skipped")
        return None
    tz = ZoneInfo(cfg["timezone"])
    errs = [e["err"] for e in ev]
    bias = sum(errs) / len(errs)
    mae = sum(abs(x) for x in errs) / len(errs)
    above = sum(x > 0.1 for x in errs)
    below = sum(x < -0.1 for x in errs)
    last = ev[-1]
    name = data.get("name", "SEWELLS POINT")
    cv = Canvas(cfg)
    cv.header("TIDE FORECAST CHECK", f"{name}  ·  LAST {len(ev)} TIDES  ·  OBSERVED VS NWS FORECAST (AHPS)")
    # tiles
    ty = 205
    tw = (cv.W - 2 * cv.M - 3 * 18) / 4
    side = "ABOVE" if bias > 0.1 else "BELOW" if bias < -0.1 else "NEAR"
    bcol = ORANGE if bias > 0.1 else BLUE if bias < -0.1 else (120, 220, 160)
    lcol = ORANGE if last["err"] > 0.1 else BLUE if last["err"] < -0.1 else (120, 220, 160)
    tiles = [("AVERAGE ERROR", f"{_signed(bias)} FT", bcol, f"{side} FORECAST" if side != "NEAR" else "ON FORECAST"),
             ("AVERAGE MISS (ANY DIRECTION)", f"{mae:.2f} FT", (255, 255, 255), "MEAN ABSOLUTE ERROR"),
             ("MOST RECENT TIDE", f"{_signed(last['err'])} FT", lcol, f"{last['kind']} · {last['t'].astimezone(tz).strftime('%a %I:%M %p').lstrip('0').upper()}"),
             ("ABOVE / BELOW", f"{above} / {below}", (255, 198, 41), "TIDES OFF BY MORE THAN 0.1 FT")]
    for k, (lab, val, col, sub) in enumerate(tiles):
        x = cv.M + k * (tw + 18)
        cv.rect(x, ty, tw, 118, (20, 31, 54, 235), r=12)
        cv.rect(x, ty, 7, 118, (*col, 255), r=3)
        cv.text(x + 24, ty + 12, lab, 18, "bold", C["muted"], anchor="lt", maxw=tw - 40)
        cv.text(x + 24, ty + 40, val, 42, "bold", anchor="lt", maxw=tw - 40)
        cv.text(x + 24, ty + 90, sub, 16, "bold", C["muted"], anchor="lt", maxw=tw - 40)
    # chart
    cx, cy, cw, ch = cv.M, ty + 140, cv.W - 2 * cv.M, cv.H - (ty + 140) - 135
    cv.rect(cx, cy, cw, ch, C["panel"], r=16)
    lim = max(0.5, math.ceil(max(abs(x) for x in errs) * 4) / 4 + 0.05)
    top, bot = cy + 60, cy + ch - 132
    zero = (top + bot) / 2
    sc = (bot - top) / 2 / lim
    cv.text(cx + 24, cy + 16, "FEET ABOVE (+) OR BELOW (-) FORECAST", 18, "bold", C["muted"], anchor="lt")
    cv.text(cx + cw - 24, cy + 16, "ORANGE = HIGHER THAN FORECAST   ·   BLUE = LOWER", 16, "bold", C["muted"], anchor="rt")
    cv.rect(cx + 20, zero - 0.25 * sc, cw - 40, 0.5 * sc, (255, 255, 255, 18))  # +/- 0.25 ft "close" band
    step = 0.25 if lim <= 1 else 0.5 if lim <= 2 else 1.0
    g = -math.floor(lim / step) * step
    while g <= lim + 1e-9:
        yy = zero - g * sc
        cv.line([(cx + 70, yy), (cx + cw - 20, yy)], (255, 255, 255, 40 if g else 120), 1 if g else 2)
        cv.text(cx + 60, yy, _signed(g, 2) if g else "0", 16, "bold", C["muted"], anchor="rm")
        g += step
    n = len(ev)
    x0, x1 = cx + 80, cx + cw - 24
    slot = (x1 - x0) / n
    bw = min(70, slot * 0.62)
    for i, e in enumerate(ev):
        mx = x0 + slot * (i + 0.5)
        col = ORANGE if e["err"] > 0.05 else BLUE if e["err"] < -0.05 else GREY
        h = e["err"] * sc
        cv.rect(mx - bw / 2, min(zero, zero - h), bw, max(3, abs(h)), (*col, 255), r=6)
        up = e["err"] >= 0
        cv.text(mx, (zero - h - 8) if up else (zero - h + 8), _signed(e["err"]), 20, "bold", anchor="mb" if up else "mt")
        lt = e["t"].astimezone(tz)
        ly = bot + 14
        cv.text(mx, ly, e["kind"], 17, "bold", (255, 198, 41) if e["kind"] == "HIGH" else (120, 190, 255), anchor="mt")
        cv.text(mx, ly + 24, lt.strftime("%a").upper(), 17, "bold", anchor="mt")
        cv.text(mx, ly + 46, lt.strftime("%I %p").lstrip("0"), 16, "medium", C["muted"], anchor="mt")
        cv.text(mx, ly + 68, f"{e['obs']:.1f}/{e['fc']:.1f}", 15, "medium", C["muted"], anchor="mt")
    cv.text(cx + 24, cy + ch - 10, "UNDER EACH BAR: OBSERVED / FORECAST HEIGHT (FT)  ·  SHADED BAND = WITHIN 0.25 FT", 14, "bold", C["muted"], anchor="lb")
    # plain-English line
    if abs(bias) <= 0.1 and mae <= 0.15:
        msg = f"Recent tides at Sewells Point have run right on the forecast, missing by only {mae:.2f} ft on average."
    elif abs(bias) <= 0.1:
        msg = (f"Recent tides have been a mix of higher and lower than forecast: they average out close to the forecast, "
               f"but individual tides missed by {mae:.1f} ft.")
    else:
        word = "higher" if bias > 0 else "lower"
        msg = (f"Recent tides have run about {abs(bias):.1f} ft {word} than the NWS forecast on average, "
               f"missing by {mae:.1f} ft in either direction. " +
               ("Forecast crests may be underdone: leave some cushion for flooding." if bias > 0.2 else
                "Forecast crests may be running a bit high." if bias < -0.2 else ""))
    cv.paragraph(cv.M, cv.H - 118, msg, 22, "bold", cv.W - 2 * cv.M, max_lines=2, lh=1.28)
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NWS NWPS / AHPS SWPV2 FORECAST ARCHIVE"
    cv.footer(pkg, source=src)
    return [("tide_error", cv)]
