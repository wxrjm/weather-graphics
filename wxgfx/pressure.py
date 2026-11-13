"""7-day pressure trend and an "aches & pains" forecast for Norfolk.

Data: Open-Meteo hourly sea-level pressure (free, no key; NDFD has no pressure).
Graphics (Forecast folder):
  pressure_trend   the next 7 days of pressure as a line; fast 24-hour rises / falls are coloured, highs and lows marked
  aches_pains      one card per day; the bigger the 24-hour pressure swing that day (either direction), the higher
                   the level, bumped one level when the high temperature swings 15°F+ from the day before
Config: aches_thresholds_mb (default [5, 8, 12]), aches_temp_swing (default 15).
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


# ------------------------------------------------------------------ aches & pains
def _day_levels(pkg, cfg, pd, tz, now):
    d24 = _d24(pd)
    th = cfg.get("aches_thresholds_mb") or [5, 8, 12]
    swing_f = cfg.get("aches_temp_swing", 15)
    highs = {d["date"]: d.get("high") for d in pkg.get("days", [])}
    today = now.astimezone(tz).date()
    out = []
    for i in range(7):
        day = today + timedelta(days=i)
        ch = [(t, c) for t, c in d24.items() if t.astimezone(tz).date() == day and t >= now - timedelta(hours=1)]
        if not ch:
            continue
        t, c = max(ch, key=lambda r: abs(r[1]))
        lv = sum(abs(c) >= x for x in th)
        why = ("Pressure falling" if c < 0 else "Pressure rising") if lv else "Steady pressure"
        h1, h0 = highs.get(day.isoformat()), highs.get((day - timedelta(days=1)).isoformat())
        if h1 is not None and h0 is not None and abs(h1 - h0) >= swing_f:
            lv = min(3, lv + 1)
            why += " + temp swing"
        out.append({"day": day, "lv": lv, "ch": c, "why": why})
    return out


def aches_graphic(pkg, cfg):
    pd = pkg.get("_pressure")
    if not pd:
        return None
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.fromisoformat(pkg["issued"]).astimezone(timezone.utc)
    rows = _day_levels(pkg, cfg, pd, tz, now)
    if len(rows) < 3:
        return None
    cv = Canvas(cfg)
    cv.header("ACHES & PAINS FORECAST", "NEXT 7 DAYS  ·  BASED ON 24-HOUR PRESSURE CHANGES")
    x0, y0 = cv.M, 205
    W = cv.W - 2 * cv.M
    n = len(rows)
    tall = cv.H > cv.W
    today = now.astimezone(tz).date()
    if tall:  # Post / Vertical: one row per day
        ch_ = cv.H - y0 - (190 if cv.minimal else 260)
        rh = ch_ / n
        for i, r in enumerate(rows):
            y = y0 + i * rh
            name, col, _ = LEVELS[r["lv"]]
            cv.rect(x0, y, W, rh - 10, C["panel"], r=14)
            mid = y + (rh - 10) / 2
            cv.text(x0 + 24, mid - 12, "TODAY" if r["day"] == today else r["day"].strftime("%a").upper(), 30, "bold", anchor="lm")
            cv.text(x0 + 24, mid + 20, f"{r['day'].month}/{r['day'].day}", 18, "medium", C["muted"], anchor="lm")
            bx, bw = x0 + 170, 300
            cv.rect(bx, y + 10, bw, rh - 30, (*col, 255), r=10)
            cv.text(bx + bw / 2, mid, name, 30, "bold", (20, 28, 46) if col[0] + col[1] > 300 else (255, 255, 255), anchor="mm")
            sign = "+" if r["ch"] > 0 else "−" if r["ch"] < 0 else ""
            cv.text(x0 + W - 24, mid - 12, f"{sign}{abs(_inhg(r['ch'])):.2f}\"  ·  {abs(r['ch']):.0f} MB / 24 HR", 24, "bold", anchor="rm")
            cv.text(x0 + W - 24, mid + 20, r["why"].upper(), 16, "bold", (*col, 255), anchor="rm")
    else:
        gap = 12
        cw = (W - gap * (n - 1)) / n
        ch_ = cv.H - y0 - (190 if cv.minimal else 260)
        for i, r in enumerate(rows):
            x = x0 + i * (cw + gap)
            name, col, _ = LEVELS[r["lv"]]
            cv.rect(x, y0, cw, ch_, C["panel"], r=16)
            cv.text(x + cw / 2, y0 + 34, "TODAY" if r["day"] == today else r["day"].strftime("%a").upper(), 34, "bold", anchor="mm", maxw=cw - 10)
            cv.text(x + cw / 2, y0 + 72, f"{r['day'].month}/{r['day'].day}", 20, "medium", C["muted"], anchor="mm")
            by, bh = y0 + 110, ch_ - 250
            cv.rect(x + 12, by, cw - 24, bh, (*col, 255), r=12)
            ink = (20, 28, 46) if col[0] + col[1] > 300 else (255, 255, 255)
            words = name.split(" ")
            for k, wd in enumerate(words):
                cv.text(x + cw / 2, by + bh / 2 + (k - (len(words) - 1) / 2) * 34 * 1.15, wd, 34, "bold", ink, anchor="mm", maxw=cw - 34)
            sign = "+" if r["ch"] > 0 else "−" if r["ch"] < 0 else ""
            cv.text(x + cw / 2, by + bh + 46, f"{sign}{abs(_inhg(r['ch'])):.2f}\"", 30, "bold", anchor="mm")
            cv.text(x + cw / 2, by + bh + 84, f"{abs(r['ch']):.0f} MB / 24 HR", 15, "medium", C["muted"], anchor="mm")
            cv.paragraph(x + cw / 2, by + bh + 104, r["why"].upper(), 15, "bold", cw - 20, max_lines=2, lh=1.15, anchor="ma", fill=(*col, 255))
    ly = y0 + ch_ + 22
    lx = x0
    for name, col, _ in LEVELS:
        lab = name
        w = cv.width(lab, 20) + 44
        cv.rect(lx, ly, w, 40, (*col, 255), r=20)
        cv.text(lx + w / 2, ly + 20, lab, 20, "bold", (20, 28, 46) if col[0] + col[1] > 300 else (255, 255, 255), anchor="mm")
        lx += w + 12
    if not cv.minimal:
        cv.paragraph(x0, ly + 58, "Big rises or drops in air pressure over a day can bring more joint pain, arthritis flare-ups and headaches "
                     "for people who are sensitive to weather changes. General awareness only, not medical advice.", 20, "regular", W,
                     max_lines=2, lh=1.25, fill=C["muted"])
    cv.footer(pkg, source=f"{pd.get('source', 'OPEN-METEO')} PRESSURE · NWS TEMPERATURES")
    return cv


def pressure_graphics(pkg, cfg):
    out = []
    for name, fn in (("pressure_trend", trend_graphic), ("aches_pains", aches_graphic)):
        g = fn(pkg, cfg)
        if g:
            out.append((name, g))
    return out or None
