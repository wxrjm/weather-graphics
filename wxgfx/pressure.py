"""7-day pressure trend and an "aches & pains" forecast for Norfolk.

Data: Open-Meteo hourly sea-level pressure (free, no key; NDFD has no pressure).
Graphics (Forecast folder):
  pressure_trend   the next 7 days of pressure as a line; fast 24-hour rises / falls are coloured, highs and lows marked
  aches_pains      pressure chart + one card per day, rated only on pressure DROPS (biggest 12-hour fall that day);
                   rises and steady pressure are LOW.  Includes a how-to-read explainer and level key.
Config: aches_drop_thresholds_mb (default [2, 5, 9] mb in 12 hours).
"""
import json
import math
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .theme import C, Canvas, z

URL = "https://api.open-meteo.com/v1/forecast"
MB_TO_IN = 0.0295300
LEVELS = [  # name, colour, short explanation
    ("LOW", (70, 180, 100), "Steady pressure"),
    ("MODERATE", (240, 205, 60), "Some pressure change"),
    ("HIGH", (245, 150, 40), "Big pressure swing"),
    ("VERY HIGH", (228, 60, 60), "Sharp pressure swing"),
]


def fetch(lat, lon, cfg):
    q = {"latitude": lat, "longitude": lon, "hourly": "pressure_msl", "timezone": "GMT", "forecast_days": 8, "past_days": 1}
    req = urllib.request.Request(f"{URL}?{urllib.parse.urlencode(q)}", headers={"User-Agent": cfg["user_agent"]})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  ! pressure forecast unavailable: {e}")
        return None
    series = [(datetime.fromisoformat(t).replace(tzinfo=timezone.utc), float(v))
              for t, v in zip(d["hourly"]["time"], d["hourly"]["pressure_msl"]) if v is not None]
    return {"series": series, "source": "OPEN-METEO"} if len(series) > 48 else None


def sample(now_utc):
    start = now_utc.replace(minute=0, second=0, microsecond=0) - timedelta(hours=24)
    series = []
    for k in range(24 * 9):
        t = start + timedelta(hours=k)
        h = k / 24
        p = 1017 + 4 * math.sin(h / 3.2 * 2 * math.pi) - 9 * math.exp(-((h - 4.6) / 0.5) ** 2) + 0.6 * math.sin(k / 12 * math.pi)
        series.append((t, p))
    return {"series": series, "source": "SAMPLE"}


def _window(pd, now, tz, days=7):
    """Series from now through the next `days` local days, in local time."""
    end = (now.astimezone(tz) + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    return [(t.astimezone(tz), p) for t, p in pd["series"] if now - timedelta(hours=1) <= t <= end]


def _d24(pd):
    """{utc time: change over the previous 24 hours (mb)}"""
    look = {t: p for t, p in pd["series"]}
    return {t: p - look[t - timedelta(hours=24)] for t, p in pd["series"] if (t - timedelta(hours=24)) in look}


def _inhg(mb):
    return mb * MB_TO_IN


# ------------------------------------------------------------------ pressure trend
def trend_graphic(pkg, cfg):
    pd = pkg.get("_pressure")
    if not pd:
        return None
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.fromisoformat(pkg["issued"]).astimezone(timezone.utc)
    pts = _window(pd, now, tz)
    if len(pts) < 48:
        return None
    d24 = _d24(pd)
    fast = cfg.get("pressure_fast_mb", 6)
    cv = Canvas(cfg)
    cv.header("PRESSURE TREND", f"{pkg['location'].get('name', 'NORFOLK').upper()}  ·  NEXT 7 DAYS  ·  SEA-LEVEL PRESSURE")
    x0, y0 = cv.M, 205
    W, H = cv.W - 2 * cv.M, cv.H - 205 - 105
    cv.rect(x0, y0, W, H, C["panel"], r=18)
    px0, px1 = x0 + 120, x0 + W - 120
    py0, py1 = y0 + 70, y0 + H - 95
    vals = [p for _, p in pts]
    lo, hi = min(vals), max(vals)
    pad = max(2.0, (hi - lo) * 0.18)
    lo, hi = lo - pad, hi + pad
    t0, t1 = pts[0][0], pts[-1][0]
    span = (t1 - t0).total_seconds()

    def X(t):
        return px0 + (px1 - px0) * (t - t0).total_seconds() / span

    def Y(p):
        return py1 - (py1 - py0) * (p - lo) / (hi - lo)

    # gridlines: every 0.10 inHg, mb on the right
    step = 0.10 / MB_TO_IN
    g = math.ceil(lo / step) * step
    while g <= hi:
        y = Y(g)
        cv.rect(px0, y, px1 - px0, 1.5, (255, 255, 255, 28))
        cv.text(px0 - 14, y, f"{_inhg(g):.2f}", 18, "bold", C["muted"], anchor="rm")
        cv.text(px1 + 14, y, f"{round(g)}", 16, "medium", C["muted"], anchor="lm")
        g += step
    cv.text(px0 - 14, py0 - 40, "inHg", 16, "bold", C["muted"], anchor="rm")
    cv.text(px1 + 14, py0 - 40, "mb", 16, "bold", C["muted"], anchor="lm")
    # day columns
    day = (t0 + timedelta(days=1)).replace(hour=0, minute=0)
    first = t0
    while first < t1:
        nxt = min(day, t1)
        cx = (X(first) + X(nxt)) / 2
        if X(nxt) - X(first) > 70:
            cv.text(cx, py1 + 30, first.strftime("%a").upper(), 24 if not cv.tall else 18, "bold", anchor="mm")
            cv.text(cx, py1 + 58, f"{first.month}/{first.day}", 16, "medium", C["muted"], anchor="mm")
        if day < t1:
            cv.rect(X(day) - 1, py0 - 10, 2, py1 - py0 + 10, (255, 255, 255, 40))
        first, day = day, day + timedelta(days=1)
    # filled area + coloured line
    d = cv.d
    poly = [(z(X(t)), z(Y(p))) for t, p in pts] + [(z(X(t1)), z(py1)), (z(X(t0)), z(py1))]
    d.polygon(poly, fill=(88, 170, 255, 45))
    for (ta, pa), (tb, pb) in zip(pts, pts[1:]):
        ch = d24.get(tb.astimezone(timezone.utc), 0)
        col = (245, 150, 40) if ch <= -fast else (70, 200, 190) if ch >= fast else (255, 255, 255)
        d.line([(z(X(ta)), z(Y(pa))), (z(X(tb)), z(Y(pb)))], fill=(*col, 255), width=z(7))
    # highs / lows
    for kind, (t, p) in (("H", max(pts, key=lambda r: r[1])), ("L", min(pts, key=lambda r: r[1]))):
        x, y = X(t), Y(p)
        d.ellipse([z(x - 9), z(y - 9), z(x + 9), z(y + 9)], fill=(13, 21, 38, 255), outline=(255, 255, 255, 255), width=z(3))
        col = (88, 170, 255) if kind == "H" else (228, 60, 60)
        ty = y - 30 if kind == "H" else y + 30
        cv.text(x, ty, f"{kind}  {_inhg(p):.2f}\"", 24, "bold", col, anchor="mm", stroke=3, stroke_fill=(13, 21, 38, 255))
    # key
    kx = px0 + 20
    for col, lab in (((255, 255, 255), "STEADY"), ((245, 150, 40), f"FALLING FAST (≥{round(_inhg(fast), 2):.2f}\" / 24 HR)"),
                     ((70, 200, 190), "RISING FAST")):
        cv.rect(kx, y0 + 26, 34, 8, (*col, 255), r=4)
        cv.text(kx + 44, y0 + 30, lab, 17, "bold", C["muted"], anchor="lm")
        kx += 44 + cv.width(lab, 17) + 34
    cv.footer(pkg, source=f"{pd.get('source', 'OPEN-METEO')} MODEL BLEND")
    return cv


# ------------------------------------------------------------------ aches & pains (pressure DROPS only)
LEVEL_NAMES = ["LOW", "MODERATE", "HIGH", "VERY HIGH"]


def _part(t):
    h = t.hour
    return "overnight" if h < 5 else "morning" if h < 12 else "afternoon" if h < 17 else "evening" if h < 21 else "night"


def _when(t):
    return f"{t.strftime('%A')} {_part(t)}"


def _drops(pd, tz, now):
    """[(local time, 12-hour pressure FALL in mb (0 when not falling))] for every hour from now on."""
    look = {t: p for t, p in pd["series"]}
    out = []
    for t, p in pd["series"]:
        if t < now - timedelta(hours=1):
            continue
        prev = look.get(t - timedelta(hours=12))
        if prev is not None:
            out.append((t.astimezone(tz), max(0.0, prev - p)))
    return out


def _day_levels(pkg, cfg, pd, tz, now):
    """One row per day: level from the biggest 12-hour pressure FALL that day.  Rises and steady pressure are never penalised."""
    th = cfg.get("aches_drop_thresholds_mb") or [2, 5, 9]
    d24 = _d24(pd)
    drops = _drops(pd, tz, now)
    today = now.astimezone(tz).date()
    out = []
    for i in range(7):
        day = today + timedelta(days=i)
        dd = [(t, v) for t, v in drops if t.date() == day]
        if not dd:
            continue
        t, v = max(dd, key=lambda r: r[1])
        lv = sum(v >= x for x in th)
        ch24 = [c for tt, c in d24.items() if tt.astimezone(tz).date() == day]
        net = sum(ch24) / len(ch24) if ch24 else 0
        out.append({"day": day, "lv": lv, "drop": v if lv else 0, "t": t, "net": net})
    return out


def _arrow(cv, cx, cy, kind, col, s=22):
    """kind: down / up / flat -- drawn with polygons (the font has no arrow glyphs)."""
    pts = {"down": [(0, s), (-s * 0.8, -s * 0.1), (-s * 0.28, -s * 0.1), (-s * 0.28, -s), (s * 0.28, -s), (s * 0.28, -s * 0.1), (s * 0.8, -s * 0.1)],
           "up": [(0, -s), (-s * 0.8, s * 0.1), (-s * 0.28, s * 0.1), (-s * 0.28, s), (s * 0.28, s), (s * 0.28, s * 0.1), (s * 0.8, s * 0.1)],
           "flat": [(s, 0), (-s * 0.1, -s * 0.8), (-s * 0.1, -s * 0.28), (-s, -s * 0.28), (-s, s * 0.28), (-s * 0.1, s * 0.28), (-s * 0.1, s * 0.8)]}[kind]
    cv.d.polygon([(z(cx + x), z(cy + y)) for x, y in pts], fill=(*col, 255))


def _summary(rows, drops, tz):
    """(headline, sentence) describing the biggest pressure fall of the week."""
    worst = max(rows, key=lambda r: (r["drop"], -r["day"].toordinal()))
    if worst["lv"] == 0:
        return "NO BIG PRESSURE DROPS", "Pressure stays steady or rising all week, so weather-related aches and headaches are less likely."
    end = worst["t"]
    win = [(t, v) for t, v in drops if end - timedelta(hours=30) <= t <= end + timedelta(hours=6)]
    # the fall: highest pressure before the low, to the low
    return (f"BIGGEST DROP: {worst['day'].strftime('%A').upper()}",
            f"Pressure falls about {worst['drop']:.0f} mb in 12 hours, bottoming out {_when(worst['t'])}. "
            f"Drops like this can set off joint pain and headaches for people sensitive to weather.")


def aches_graphic(pkg, cfg):
    pd = pkg.get("_pressure")
    if not pd:
        return None
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.fromisoformat(pkg["issued"]).astimezone(timezone.utc)
    rows = _day_levels(pkg, cfg, pd, tz, now)
    if len(rows) < 3:
        return None
    pts = _window(pd, now, tz)
    if len(pts) < 48:
        return None
    drops = _drops(pd, tz, now)
    th = cfg.get("aches_drop_thresholds_mb") or [2, 5, 9]
    head, sent = _summary(rows, drops, tz)
    cv = Canvas(cfg)
    cv.header("ACHES & PAINS FORECAST", "NEXT 7 DAYS  ·  BASED ON PRESSURE DROPS")
    tall = cv.H > cv.W
    M = cv.M
    W = cv.W - 2 * M
    ink = lambda col: (20, 28, 46) if col[0] + col[1] > 300 else (255, 255, 255)
    # ---- headline + sentence
    cv.text(M, cv.top + 26, head, 44 if not tall else 40, "bold", anchor="lm")
    cv.paragraph(M, cv.top + 62, sent, 26 if not tall else 27, "regular", W, max_lines=2, lh=1.25, fill=(210, 220, 238))
    # ---- layout boxes
    cards_h = 215 if not tall else 270
    cy = cv.bottom - cards_h
    chart_y = cv.top + (130 if not tall else 150)
    if tall:
        ex_h = 250
        cy = cv.bottom - cards_h - ex_h - (14 if ex_h else 0)
        chart = (M, chart_y, W, cy - chart_y - 14)
        expl = (M, cy + cards_h + 14, W, ex_h)
    else:
        chart = (M, chart_y, W * 0.64, cy - chart_y - 14)
        expl = (M + chart[2] + 16, chart_y, W - chart[2] - 16, chart[3])
    # ---- chart
    x0, y0, w, h = chart
    cv.rect(x0, y0, w, h, C["panel"], r=18)
    cv.text(x0 + 24, y0 + 30, "Sea-level pressure", 24 if not tall else 24, "bold", anchor="lm")
    cv.text(x0 + w - 24, y0 + 30, "MB · NEXT 7 DAYS", 16, "bold", C["muted"], anchor="rm")
    px0, px1 = x0 + 28, x0 + w - 70
    py0, py1 = y0 + 78, y0 + h - 56
    vals = [p for _, p in pts]
    lo, hi = min(vals) - 2, max(vals) + 2
    t0, t1 = pts[0][0], pts[-1][0]
    span = (t1 - t0).total_seconds()
    X = lambda t: px0 + (px1 - px0) * (t - t0).total_seconds() / span
    Y = lambda p: py1 - (py1 - py0) * (p - lo) / (hi - lo)
    step = 5
    g = math.ceil(lo / step) * step
    while g <= hi:
        cv.rect(px0, Y(g), px1 - px0, 1.5, (255, 255, 255, 28))
        cv.text(px1 + 12, Y(g), f"{g:.0f}", 16, "medium", C["muted"], anchor="lm")
        g += step
    day = (t0 + timedelta(days=1)).replace(hour=0, minute=0)
    first = t0
    while first < t1:
        nxt = min(day, t1)
        if X(nxt) - X(first) > 60:
            cv.text((X(first) + X(nxt)) / 2, py1 + 28, first.strftime("%a").upper(), 20 if not tall else 17, "bold", anchor="mm")
        if day < t1:
            cv.rect(X(day) - 1, py0 - 8, 2, py1 - py0 + 8, (255, 255, 255, 30))
        first, day = day, day + timedelta(days=1)
    d = cv.d
    d.polygon([(z(X(t)), z(Y(p))) for t, p in pts] + [(z(X(t1)), z(py1)), (z(X(t0)), z(py1))], fill=(88, 170, 255, 45))
    fall = {t: v for t, v in drops}
    RED = (228, 70, 70)
    for (ta, pa), (tb, pb) in zip(pts, pts[1:]):
        col = RED if fall.get(tb, 0) >= th[0] and pb < pa + 0.05 else (88, 190, 255)
        d.line([(z(X(ta)), z(Y(pa))), (z(X(tb)), z(Y(pb)))], fill=(*col, 255), width=z(7 if not tall else 6))
    # mark the low point of the worst drop
    worst = max(rows, key=lambda r: r["drop"])
    if worst["lv"]:
        wt = min((r for r in pts if abs((r[0] - worst["t"]).total_seconds()) < 3600 * 3), key=lambda r: r[1], default=None)
        if wt:
            x, y = X(wt[0]), Y(wt[1])
            d.ellipse([z(x - 10), z(y - 10), z(x + 10), z(y + 10)], fill=(255, 255, 255, 255))
            cv.text(x + 20, y - 4, f"{worst['drop']:.0f} MB DROP IN 12 HRS", 20 if not tall else 18, "bold", (255, 150, 150), anchor="lm",
                    stroke=3, stroke_fill=(13, 21, 38, 255))
    # ---- day cards
    gap = 10
    cw = (W - gap * 6) / 7 if len(rows) == 7 else (W - gap * (len(rows) - 1)) / len(rows)
    for i, r in enumerate(rows):
        x = M + i * (cw + gap)
        col = LEVELS[r["lv"]][1]
        hot = r["lv"] >= 2
        cv.rect(x, cy, cw, cards_h, C["panel"], r=14)
        if hot:
            cv.d.rounded_rectangle([z(x), z(cy), z(x + cw), z(cy + cards_h)], radius=z(14), outline=(*col, 255), width=z(4))
        cv.text(x + cw / 2, cy + 36, r["day"].strftime("%a").upper(), 32 if not tall else 26, "bold", anchor="mm", maxw=cw - 8)
        cv.text(x + cw / 2, cy + 68, f"{r['day'].month}/{r['day'].day}", 18, "medium", C["muted"], anchor="mm")
        bw = cw - 24
        cv.rect(x + 12, cy + 88, bw, 40, (*col, 255), r=8)
        cv.text(x + cw / 2, cy + 108, LEVEL_NAMES[r["lv"]], 20 if not tall else 14, "bold", ink(col), anchor="mm", maxw=bw - 6)
        if r["lv"]:
            _arrow(cv, x + cw / 2, cy + 160, "down", col)
            lab, sub = "Dropping", f"−{r['drop']:.0f} mb"
        else:
            _arrow(cv, x + cw / 2, cy + 160, "up" if r["net"] > 1.5 else "flat", (70, 180, 100))
            lab, sub = ("Rising", "no drop") if r["net"] > 1.5 else ("Steady", "no drop")
        cv.text(x + cw / 2, cy + 196 if not tall else cy + 200, f"{lab}  {sub}" if not tall else lab, 17 if not tall else 15, "bold", anchor="mm", maxw=cw - 8)
        if tall:
            cv.text(x + cw / 2, cy + 224, sub, 15, "medium", C["muted"], anchor="mm", maxw=cw - 8)
    # ---- explainer + legend
    if True:
        ex, ey, ew, eh = expl
        cv.rect(ex, ey, ew, eh, C["panel"], r=18)
        cv.text(ex + 24, ey + 36, "HOW TO READ THIS", 24, "bold", anchor="lm")
        cv.paragraph(ex + 24, ey + 66, "Only pressure DROPS count. A fast fall in air pressure is when people sensitive to weather changes most often "
                     "report joint pain, arthritis flare-ups and headaches. Rising or steady pressure is rated LOW.",
                     19 if not tall else 21, "regular", ew - 48, max_lines=5, lh=1.25, fill=(210, 220, 238))
        ly = ey + (eh - 4 * 38 - 36) if not tall else ey + 150
        items = [(0, f"Under {th[0]} mb drop in 12 hrs"), (1, f"{th[0]}-{th[1]} mb drop in 12 hrs"),
                 (2, f"{th[1]}-{th[2]} mb drop in 12 hrs"), (3, f"{th[2]}+ mb drop in 12 hrs")]
        if tall:
            for k, (lv, txt) in enumerate(items):
                col = LEVELS[lv][1]
                lx = ex + 24 + (k % 2) * (ew / 2 - 8)
                lyy = ey + 150 + (k // 2) * 44
                cv.rect(lx, lyy, 120, 34, (*col, 255), r=17)
                cv.text(lx + 60, lyy + 17, LEVEL_NAMES[lv], 15, "bold", ink(col), anchor="mm", maxw=110)
                cv.text(lx + 130, lyy + 17, txt, 16, "medium", anchor="lm", maxw=ew / 2 - 170)
        else:
            for k, (lv, txt) in enumerate(items):
                col = LEVELS[lv][1]
                lyy = ey + eh - 4 * 46 - 14 + k * 46
                cv.rect(ex + 24, lyy, 150, 36, (*col, 255), r=18)
                cv.text(ex + 99, lyy + 18, LEVEL_NAMES[lv], 18, "bold", ink(col), anchor="mm")
                cv.text(ex + 190, lyy + 18, txt, 19, "medium", anchor="lm", maxw=ew - 210)
    cv.footer(pkg, source=f"{pd.get('source', 'OPEN-METEO')} PRESSURE · GENERAL AWARENESS, NOT MEDICAL ADVICE")
    return cv


def pressure_graphics(pkg, cfg):
    out = []
    for name, fn in (("pressure_trend", trend_graphic), ("aches_pains", aches_graphic)):
        g = fn(pkg, cfg)
        if g:
            out.append((name, g))
    return out or None
