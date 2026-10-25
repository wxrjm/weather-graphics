"""Wind-gust graphics for KORF:
  gust_table_48  - next 48 hours as a table (max gust / sustained wind / direction per 3-hour block), from the NWS
                   forecast already in the package (pkg["wind_hourly"]).
  gust_peaks     - TEXT-ONLY graphic: highest gust reported in the past 24 and 48 hours (Norfolk Intl + nearby
                   stations), from NWS station observations (api.weather.gov/stations/<id>/observations, no key).
"""
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .theme import Canvas, C

STATIONS = [("KORF", "Norfolk Intl"), ("KNGU", "Norfolk NAS"), ("KPHF", "Newport News"), ("KLFI", "Langley AFB"),
            ("KNTU", "Oceana NAS"), ("KCPK", "Chesapeake"), ("KECG", "Elizabeth City"), ("KFKN", "Franklin"),
            ("KWAL", "Wallops Island"), ("KPVG", "Hampton Roads Exec")]
KMH = 0.621371
BANDS = [(0, (170, 215, 235), True), (15, (95, 170, 215), False), (25, (45, 115, 185), False),
         (40, (30, 60, 140), False), (58, (120, 30, 120), False)]


def _band(g):
    col, dark = BANDS[0][1], BANDS[0][2]
    for lo, c, d in BANDS:
        if g is not None and g >= lo:
            col, dark = c, d
    return col, dark


# ------------------------------------------------------------------ observed gusts
def fetch(cfg, now, tz, debug=False):
    """-> {"stations": [{"id","name","obs":[(aware_dt, gust_mph|None, wind_mph|None)]}], "now": now}"""
    from .nws import NWSClient
    nws = NWSClient(cfg["user_agent"], Path(__file__).resolve().parents[1] / "cache")
    start = (now - timedelta(hours=49)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sts = [(s[0], s[1]) for s in (cfg.get("gust_stations") or STATIONS)]
    out = []
    for sid, name in sts:
        try:
            d = nws.get(f"/stations/{sid}/observations?start={start}&limit=500")
        except Exception as e:
            if debug:
                print(f"   [gusts] {sid} failed: {e}")
            continue
        obs = []
        for f in d.get("features", []):
            p = f.get("properties", {})
            try:
                t = datetime.fromisoformat(p["timestamp"].replace("Z", "+00:00")).astimezone(tz)
            except Exception:
                continue
            g, w = (p.get("windGust") or {}).get("value"), (p.get("windSpeed") or {}).get("value")
            obs.append((t, None if g is None else g * KMH, None if w is None else w * KMH))
        if obs:
            out.append({"id": sid, "name": name, "obs": obs})
        if debug:
            print(f"   [gusts] {sid}: {len(obs)} obs, max gust {max([o[1] for o in obs if o[1] is not None] or [0]):.0f}")
    return {"stations": out, "now": now}


def sample(now, tz):
    import random
    rnd = random.Random(4)
    out = []
    for i, (sid, name) in enumerate(STATIONS[:8]):
        obs = []
        for h in range(48, 0, -1):
            t = now - timedelta(hours=h)
            base = 12 + 14 * math.exp(-((h - 20) / 9) ** 2) + rnd.uniform(-3, 3) + i % 3
            gust = base * 1.5 if base > 15 else None
            obs.append((t, gust, base))
        out.append({"id": sid, "name": name, "obs": obs})
    return {"stations": out, "now": now}


def _peak(obs, now, hours):
    cut = now - timedelta(hours=hours)
    best = None
    for t, g, w in obs:
        if t >= cut and g is not None and (best is None or g > best[0]):
            best = (g, t)
    return best


def _when(t):
    return f"{t.strftime('%a').upper()} {t.strftime('%I:%M %p').lstrip('0')}"


# ------------------------------------------------------------------ text-only observed peaks
def gust_peaks(pkg, cfg):
    data = pkg.get("_gusts")
    if not data or not data["stations"]:
        return None
    now = data["now"]
    rows = []
    for s in data["stations"]:
        rows.append((s["name"], s["id"], _peak(s["obs"], now, 24), _peak(s["obs"], now, 48)))
    if not any(r[3] for r in rows):
        print("  - gust_peaks: no gusts reported in the past 48 hours, skipped")
        return None
    cv = Canvas(cfg)
    cv.header("PEAK WIND GUSTS", "Highest reported · past 24 and 48 hours")
    M, W = cv.M, cv.W
    top = cv.top
    best24 = max((r for r in rows if r[2]), key=lambda r: r[2][0], default=None)
    best48 = max((r for r in rows if r[3]), key=lambda r: r[3][0], default=None)
    if cv.tall:
        cw, ch = W - 2 * M, 250 if cv.fmt != "square" else 190
        boxes = [(M, top, cw, ch), (M, top + ch + 20, cw, ch)]
        ty = top + 2 * ch + 50
    else:
        cw, ch = (W - 2 * M - 30) // 2, 330
        boxes = [(M, top, cw, ch), (M + cw + 30, top, cw, ch)]
        ty = top + ch + 40
    for (x, y, w, h), label, b in zip(boxes, ("PAST 24 HOURS", "PAST 48 HOURS"), (best24, best48)):
        pk = b[2 if label.endswith("24 HOURS") else 3] if b else None
        col = _band(pk[0])[0] if pk else (70, 86, 112)
        cv.rect(x, y, w, h, C["panel"], r=18)
        cv.rect(x, y, 14, h, col, r=7)
        cv.text(x + 44, y + 52, label, 30 if not cv.tall else 26, "bold", C["muted"], anchor="ls")
        if pk:
            big = 150 if not cv.tall else (120 if cv.fmt != "square" else 96)
            cv.text(x + 44, y + 52 + big * 0.95, f"{pk[0]:.0f}", big, "bold", anchor="ls")
            bw = cv.width(f"{pk[0]:.0f}", big, "bold")
            cv.text(x + 44 + bw + 16, y + 52 + big * 0.95, "MPH", big * 0.28, "bold", C["muted"], anchor="ls")
            cv.text(x + 44, y + h - 26, f"{b[0].upper()} · {_when(pk[1])}", 28 if not cv.tall else 24, "bold",
                    anchor="ls", maxw=w - 70)
        else:
            cv.text(x + 44, y + h / 2 + 30, "NO GUSTS REPORTED", 44 if not cv.tall else 36, "bold", C["muted"], anchor="ls")
    # station table
    cv.text(M, ty, "BY STATION", 24, "bold", C["muted"], anchor="ls")
    rows.sort(key=lambda r: -((r[3] or (0,))[0]))
    avail = cv.bottom - (ty + 16)
    n = min(len(rows), 8 if not cv.tall else 10)
    rh = min(58 if not cv.tall else 84, avail / (n + 1))
    cx = [M + 34, W - M - 300, W - M - 24] if not cv.tall else [M + 34, W - M - 250, W - M - 24]
    y = ty + 16
    fs = int(rh * 0.5)
    cv.text(cx[1], y + rh * 0.7, "24 HR", fs * 0.8, "bold", C["muted"], anchor="rs")
    cv.text(cx[2], y + rh * 0.7, "48 HR", fs * 0.8, "bold", C["muted"], anchor="rs")
    y += rh
    for name, sid, p24, p48 in rows[:n]:
        cv.rect(M, y, W - 2 * M, rh - 6, C["panel"], r=8)
        top_g = (p48 or (0,))[0] if p48 else None
        cv.rect(M + 10, y + 8, 12, rh - 22, _band(top_g)[0] if top_g is not None else (70, 86, 112), r=5)
        cv.text(cx[0], y + (rh - 6) * 0.68, name.upper(), fs, "bold", anchor="ls", maxw=cx[1] - cx[0] - 150)
        for xx, p, anc in ((cx[1], p24, "rs"), (cx[2], p48, "rs")):
            if p:
                cv.text(xx, y + (rh - 6) * 0.68, f"{p[0]:.0f} MPH", fs, "bold", anchor=anc)
            else:
                cv.text(xx, y + (rh - 6) * 0.68, "—", fs, "bold", C["muted"], anchor=anc)
        y += rh
    cv.footer(pkg, source="SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NWS station observations")
    return cv


# ------------------------------------------------------------------ 48-hour forecast table
def r5(v):
    return None if v is None else int(5 * round(v / 5.0))


def _blocks(pkg, step=3, total=48):
    hrs = pkg.get("wind_hourly") or []
    out = []
    for i in range(0, min(total, len(hrs)), step):
        blk = hrs[i:i + step]
        g = [h["gust"] for h in blk if h.get("gust") is not None]
        w = [h["wind"] for h in blk if h.get("wind") is not None]
        t = datetime.fromisoformat(blk[0]["time"])
        pk = max((h for h in blk if h.get("gust") is not None), key=lambda h: h["gust"], default=blk[0])
        out.append({"t": t, "gust": r5(max(g)) if g else None, "wind": r5(max(w)) if w else None,
                    "dir": (pk.get("dir") or blk[0].get("dir") or "")})
    return out


def gust_table_48(pkg, cfg):
    blocks = _blocks(pkg)
    if len(blocks) < 6:
        return None
    cv = Canvas(cfg)
    peak = max((b for b in blocks if b["gust"] is not None), key=lambda b: b["gust"], default=None)
    sub = f"{pkg['location']['area']} · NEXT 48 HOURS"
    cv.header("WIND GUST FORECAST", sub)
    M, W = cv.M, cv.W
    top, bot = cv.top, cv.bottom - (40 if cv.tall else 30)
    cols = [blocks[:8], blocks[8:16]] if not cv.tall else [blocks]
    n_rows = len(cols[0]) + 1
    gap = 30
    cw = (W - 2 * M - gap * (len(cols) - 1)) / len(cols)
    rh = (bot - top - (60 if peak else 0)) / n_rows
    rh = min(rh, 96)
    fs = max(20, int(rh * 0.46))
    y0 = top
    if peak:
        pt = peak["t"]
        cv.text(M, y0 + 34, f"PEAK: {peak['gust']:.0f} MPH · {pt.strftime('%a').upper()} {pt.strftime('%I %p').lstrip('0')}",
                30 if not cv.tall else 26, "bold", C["sun"], anchor="ls")
        y0 += 60
    for ci, col in enumerate(cols):
        x = M + ci * (cw + gap)
        xs = [x + 18, x + cw * 0.40, x + cw * 0.64, x + cw * 0.88]
        hy = y0 + rh * 0.68
        cv.text(xs[0], hy, "TIME", fs * 0.75, "bold", C["muted"], anchor="ls")
        cv.text(xs[1], hy, "GUST", fs * 0.75, "bold", C["muted"], anchor="ms")
        cv.text(xs[2], hy, "WIND", fs * 0.75, "bold", C["muted"], anchor="ms")
        cv.text(xs[3], hy, "FROM", fs * 0.75, "bold", C["muted"], anchor="ms")
        for ri, b in enumerate(col):
            y = y0 + rh * (ri + 1)
            cv.rect(x, y, cw, rh - 6, C["panel"], r=8)
            t = b["t"]
            lab = f"{t.strftime('%a').upper()} {t.strftime('%I %p').lstrip('0')}"
            cv.text(xs[0], y + (rh - 6) * 0.68, lab, fs, "bold", anchor="ls")
            if b["gust"] is not None:
                colr, dark = _band(b["gust"])
                cv.rect(xs[1] - cw * 0.1, y + 5, cw * 0.2, rh - 16, colr, r=8)
                cv.text(xs[1], y + (rh - 6) * 0.68, f"{b['gust']:.0f}", fs, "bold", (13, 21, 38) if dark else (255, 255, 255), anchor="ms")
            else:
                cv.text(xs[1], y + (rh - 6) * 0.68, "—", fs, "bold", C["muted"], anchor="ms")
            cv.text(xs[2], y + (rh - 6) * 0.68, "—" if b["wind"] is None else f"{b['wind']:.0f}", fs, "bold", anchor="ms")
            cv.text(xs[3], y + (rh - 6) * 0.68, b["dir"], fs, "bold", C["muted"], anchor="ms")
    cv.text(M, cv.H - 62 if cv.tall else cv.H - 62, "MPH · HIGHEST GUST AND SUSTAINED WIND IN EACH 3-HOUR BLOCK", 18, "medium", C["muted"], anchor="ls")
    cv.footer(pkg)
    return cv


COMPASS = {n: i * 22.5 for i, n in enumerate("N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW".split())}


def _arrow(cv, cx, cy, size, from_deg, fill, outline=(15, 25, 45, 200)):
    """Arrow centred on (cx, cy) pointing the way the wind blows (opposite of the 'from' direction)."""
    from .theme import z
    a = math.radians(from_deg + 180.0)
    ux, uy = math.sin(a), -math.cos(a)  # screen-space unit vector (north = up)
    px, py = -uy, ux
    L, hw, sw = size * 0.5, size * 0.34, size * 0.11
    tip = (cx + ux * L, cy + uy * L)
    base = (cx + ux * (L - size * 0.46), cy + uy * (L - size * 0.46))
    tail = (cx - ux * L, cy - uy * L)
    head = [tip, (base[0] + px * hw, base[1] + py * hw), (base[0] - px * hw, base[1] - py * hw)]
    shaft = [(tail[0] + px * sw, tail[1] + py * sw), (base[0] + px * sw, base[1] + py * sw),
             (base[0] - px * sw, base[1] - py * sw), (tail[0] - px * sw, tail[1] - py * sw)]
    for poly in (shaft, head):
        cv.d.polygon([(z(x), z(y)) for x, y in poly], fill=fill, outline=outline)


def gust_bars_48_dir(pkg, cfg):
    """Same bars, plus a wind-direction arrow at the base of each bar (points where the wind is blowing toward)."""
    return gust_bars_48(pkg, cfg, arrows=True)


def gust_bars_48(pkg, cfg, arrows=False):
    """Bar graph, left to right, one bar per 2 hours (max gust in the block), rounded to the nearest 5 mph."""
    blocks = _blocks(pkg, step=2)
    if len(blocks) < 6:
        return None
    cv = Canvas(cfg)
    cv.header("WIND GUST FORECAST", f"{pkg['location']['area']} · NEXT 48 HOURS · EACH BAR = 2 HOURS" + (" · ARROWS SHOW WHERE THE WIND IS BLOWING TOWARD" if arrows else ""))
    M, W = cv.M, cv.W
    x0, x1 = M + 70, W - M
    y_top, y_bot = cv.top + 70, cv.bottom - 170
    gmax = max([b["gust"] or 0 for b in blocks] + [20])
    ymax = int(math.ceil((gmax + 5) / 10.0) * 10)
    cv.rect(M - 10, cv.top + 10, W - 2 * M + 20, cv.bottom - cv.top - 40, C["panel"], r=16)
    for v in range(0, ymax + 1, 10):
        yy = y_bot - v / ymax * (y_bot - y_top)
        cv.line([(x0, yy), (x1, yy)], (255, 255, 255, 40), 2)
        cv.text(x0 - 12, yy + 8, str(v), 22, "bold", C["muted"], anchor="rs")
    n = len(blocks)
    slot = (x1 - x0) / n
    bw = slot * 0.7
    peak = max(blocks, key=lambda b: b["gust"] or 0)
    for i, b in enumerate(blocks):
        cx = x0 + slot * (i + 0.5)
        g = b["gust"]
        if g is not None:
            h = g / ymax * (y_bot - y_top)
            col, dark = _band(g)
            cv.rect(cx - bw / 2, y_bot - h, bw, max(h, 3), col, r=5)
            wv = b["wind"]
            if wv:
                wh = wv / ymax * (y_bot - y_top)
                cv.rect(cx - bw * 0.16, y_bot - wh, bw * 0.32, wh, (255, 255, 255, 120 if not dark else 150), r=3)
            cv.text(cx, y_bot - h - 10, str(g), 26 if not cv.tall else 20, "bold", C["sun"] if b is peak else None, anchor="ms")
            if arrows and b["dir"] in COMPASS:
                asz = min(bw * 0.95, 40)
                if h >= asz + 12:  # bar tall enough: arrow sits inside the bar, at its base
                    _arrow(cv, cx, y_bot - asz * 0.5 - 8, asz, COMPASS[b["dir"]], (20, 28, 46, 255) if dark else (255, 255, 255, 255),
                           outline=(255, 255, 255, 120) if dark else (15, 25, 45, 160))
                else:  # short bar: arrow just above the baseline label area
                    _arrow(cv, cx, y_bot - h - 42, asz, COMPASS[b["dir"]], (255, 255, 255, 255))
        t = b["t"]
        if i % 2 == 0:
            cv.text(cx + slot / 2, y_bot + 36, t.strftime("%I%p").lstrip("0").replace("AM", "A").replace("PM", "P"),
                    22 if not cv.tall else 17, "bold", C["muted"], anchor="ms")
        if t.hour in (0, 1) or i == 0:
            cv.line([(cx - slot / 2, y_bot), (cx - slot / 2, y_bot + 96)], (255, 255, 255, 90), 2)
            cv.text(cx - slot / 2 + 8, y_bot + 92, t.strftime("%A" if not cv.tall else "%a").upper(), 24 if not cv.tall else 19, "bold", anchor="ls")
    cv.text(x0, y_top - 22, f"PEAK: {peak['gust']} MPH · {peak['t'].strftime('%a').upper()} {peak['t'].strftime('%I %p').lstrip('0')}",
            28 if not cv.tall else 24, "bold", C["sun"], anchor="ls")
    cv.text(x1, y_bot + 130 if not cv.tall else y_bot + 130, "MPH · MAX GUST (COLOR) · SUSTAINED WIND (WHITE) · ROUNDED TO 5" + (" · ARROW = WIND DIRECTION" if arrows else ""), 18, "medium", C["muted"], anchor="rs")
    cv.footer(pkg)
    return cv


def gust_graphics(pkg, cfg):
    out = []
    for name, fn in (("gust_table_48", gust_table_48), ("gust_peaks", gust_peaks)):
        cv = fn(pkg, cfg)
        if cv is not None:
            out.append((name, cv))
    return out or None
