"""Sound-side (wind-tide) flooding: Sandbridge, Back Bay and the northern Currituck Sound with a SOUTH wind.

A steady south wind pushes Currituck Sound water north into Back Bay, flooding the sound side of Sandbridge, Back Bay,
Pungo/Creeds, Knotts Island and Carova (there's no tide in the sound - the wind does it). This graphic:
  * map: a detailed shoreline (OpenStreetMap water, wxgfx/data/coast_water_se_va.png), the sound shoreline that floods
    shaded by risk (strongest at the north end where the water piles up), and wind-stream particles blowing from the
    forecast direction
  * panel: risk level, the windows with south winds strong enough to push water (most likely flooding times), and an
    hourly wind timeline
Wind: NWS hourly gridpoint forecast over Back Bay (config "sound_point"), falling back to the KORF forecast.
Made only when a south-wind window is in the next "sound_hours" (72) hours ("sound_flood_always": true to force).
"""
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import fullscreen, outlookmap
from .alertmap import STENCIL, STENCIL_EDGE, _paste_rounded
from .theme import C, Canvas, font, z

DATA = Path(__file__).resolve().parent / "data"
MAP_BOX = (-76.13, -75.80, 36.33, 36.80)  # w, e, s, n: Pungo/Sandbridge south to Corolla
SEEDS = [(36.68, -75.96), (36.42, -75.90)]  # Back Bay, Currituck Sound (finds the connected sound water)
PLACES = [  # (name, lat, lon, kind) kind: town / water
    ("SANDBRIDGE", 36.735, -75.938, "town"), ("PUNGO", 36.735, -76.030, "town"), ("CREEDS", 36.618, -76.032, "town"),
    ("KNOTTS ISLAND", 36.515, -75.925, "town"), ("CAROVA", 36.535, -75.868, "town"), ("COROLLA", 36.376, -75.830, "town"),
    ("BACK BAY", 36.665, -75.972, "water"), ("CURRITUCK SOUND", 36.420, -75.935, "water"),
    ("ATLANTIC OCEAN", 36.60, -75.82, "water"),
]
LEVELS = {  # level: (head value, banner, color)
    0: ("NO FLOODING EXPECTED", "No south-wind flooding expected", (70, 86, 112)),
    1: ("FLOODING POSSIBLE", "Minor sound-side flooding possible", (240, 205, 60)),
    2: ("FLOODING LIKELY", "Sound-side flooding likely", (245, 150, 40)),
    3: ("SIGNIFICANT FLOODING", "Significant sound-side flooding", (228, 60, 60)),
}
DIRS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


# ------------------------------------------------------------------ data
def _deg(d):
    if d is None:
        return None
    if isinstance(d, (int, float)):
        return float(d)
    d = str(d).upper()
    return DIRS.index(d) * 22.5 if d in DIRS else None


def fetch(cfg, now, tz, pkg, debug=False):
    """-> {"hours": [{"t": aware dt, "wind": mph, "gust": mph, "deg": deg}], "where": text}"""
    la, lo = cfg.get("sound_point") or (36.65, -75.97)
    try:
        from .ndfd import Grid
        from .nws import NWSClient
        nws = NWSClient(cfg["user_agent"], Path(__file__).resolve().parents[1] / "cache")
        url = nws.get(f"https://api.weather.gov/points/{la:.4f},{lo:.4f}")["properties"]["forecastGridData"]
        grid = Grid(nws.get(url), tz)
        t0 = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        hours = []
        for i in range(cfg.get("sound_hours", 72)):
            t = t0 + timedelta(hours=i)
            ws = grid.value_at("windSpeed", t)
            if ws is None:
                continue
            hours.append({"t": t, "wind": ws, "gust": grid.value_at("windGust", t), "deg": grid.value_at("windDirection", t)})
        if hours:
            return {"hours": hours, "where": "NWS forecast over Back Bay"}
        raise RuntimeError("no hourly winds")
    except Exception as e:
        if debug:
            print(f"   [sound] Back Bay point forecast failed ({e!r}); using the KORF forecast")
    hours = []
    for h in (pkg.get("wind_hourly") or [])[:cfg.get("sound_hours", 72)]:
        hours.append({"t": datetime.fromisoformat(h["time"]).astimezone(tz), "wind": h.get("wind"), "gust": h.get("gust"),
                      "deg": _deg(h.get("dir"))})
    return {"hours": hours, "where": "NWS forecast (Norfolk airport)"}


def sample(now, tz):
    """A south-wind event: S winds build Saturday afternoon, peak 25 mph overnight, ease Sunday morning."""
    t0 = now.astimezone(tz).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    hours = []
    for i in range(72):
        t = t0 + timedelta(hours=i)
        peak = math.exp(-((i - 30) / 9.0) ** 2)
        wind = 7 + 19 * peak + 2 * math.sin(i / 3)
        deg = 200 - 25 * peak + (40 if i < 12 else 0) + (70 if i > 48 else 0)
        hours.append({"t": t, "wind": wind, "gust": wind * 1.4 + 3, "deg": deg % 360})
    return {"hours": hours, "where": "SAMPLE"}


def _south(deg, cfg):
    lo, hi = cfg.get("sound_dirs") or (140, 235)  # SE ... SW: pushes water north up the sound
    return deg is not None and lo <= deg <= hi


def windows(data, cfg):
    """Runs of south wind >= sound_wind_min mph (gaps up to 2 h bridged), at least sound_min_hours long."""
    need, min_h = cfg.get("sound_wind_min", 15), cfg.get("sound_min_hours", 4)
    hrs = data.get("hours") or []
    flags = [_south(h["deg"], cfg) and (h["wind"] or 0) >= need for h in hrs]
    for i in range(1, len(flags) - 1):  # bridge lulls of 1-2 hours inside a run
        if not flags[i] and flags[i - 1]:
            k = next((k for k in range(i, min(i + 3, len(flags))) if flags[k]), None)
            if k is not None:
                for m in range(i, k):
                    flags[m] = True
    out, i = [], 0
    while i < len(hrs):
        if not flags[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(hrs) and flags[j + 1]:
            j += 1
        seg = hrs[i:j + 1]
        if len(seg) >= min_h:
            winds = sorted(h["wind"] or 0 for h in seg)
            peak = winds[-1]
            typical = winds[int(len(winds) * 0.75)]
            gust = max((h["gust"] or 0) for h in seg)
            dur = len(seg)
            lvl = 3 if (typical >= 25 and dur >= 6) or (typical >= 20 and dur >= 18) else \
                2 if (typical >= 20 and dur >= 6) or (typical >= 15 and dur >= 12) else 1
            degs = [h["deg"] for h in seg if h["deg"] is not None]
            mean = math.degrees(math.atan2(sum(math.sin(math.radians(d)) for d in degs),
                                           sum(math.cos(math.radians(d)) for d in degs))) % 360
            start, end = seg[0]["t"], seg[-1]["t"] + timedelta(hours=1)
            hi0 = start + (end - start) * 0.4  # water keeps rising while the wind blows; highest late in the run
            out.append({"start": start, "end": end, "hours": dur, "peak": peak, "typical": typical, "gust": gust,
                        "deg": mean, "dir": DIRS[int(mean / 22.5 + 0.5) % 16], "level": lvl,
                        "high_start": hi0, "high_end": end + timedelta(hours=cfg.get("sound_lag_hours", 2))})
        i = j + 1
    return out


# ------------------------------------------------------------------ map
_mask_cache = {}


def _mask():
    if "m" not in _mask_cache:
        meta = json.loads((DATA / "coast_water_se_va.json").read_text())
        _mask_cache["m"] = (Image.open(DATA / "coast_water_se_va.png").convert("L"), meta)
    return _mask_cache["m"]


def _crop(view, size):
    """Water mask (255 = water) and the connected sound water, cropped to view and scaled to size (px)."""
    im, meta = _mask()
    W, E, S, N = meta["bounds"]
    r = meta["res_deg"]
    w, e, s, n = view
    x0, y0 = (w - W) / r, (N - n) / r
    x1, y1 = (e - W) / r, (N - s) / r
    pad = 4
    bx0, by0, bx1, by1 = int(math.floor(x0)) - pad, int(math.floor(y0)) - pad, int(math.ceil(x1)) + pad, int(math.ceil(y1)) + pad
    big = Image.new("L", (bx1 - bx0, by1 - by0), 0)
    big.paste(im, (-bx0, -by0))
    east = int(round(im.width - bx0))  # beyond the data's east edge it's all ocean
    if east < big.width:
        big.paste(255, (max(0, east), 0, big.width, big.height))
    sound = Image.new("L", big.size, 0)
    filled = big.copy()
    for la, lo in SEEDS:
        sx, sy = int((lo - W) / r) - bx0, int((N - la) / r) - by0
        if 0 <= sx < big.width and 0 <= sy < big.height and filled.getpixel((sx, sy)) == 255:
            ImageDraw.floodfill(filled, (sx, sy), 128)
    sound = filled.point(lambda v: 255 if v == 128 else 0)
    box = (x0 - bx0, y0 - by0, x1 - bx0, y1 - by0)

    def scale(m):
        return m.resize(size, Image.BILINEAR, box=box).filter(ImageFilter.GaussianBlur(max(2, size[0] / 500)))  # soften the jagged source shoreline
    return scale(big), scale(sound)


def _ramp(img, lo=110, hi=145):
    return img.point(lambda v: 0 if v <= lo else 255 if v >= hi else int((v - lo) * 255 / (hi - lo)))


def _particles(lay, view, wind_deg, mph, seed=11):
    """Wind-stream particles: short glowing trails that flow with the wind, with an arrowhead at the front."""
    W_, H_ = lay.size
    w, e, s, n = view
    rnd = random.Random(seed)
    ov = Image.new("RGBA", lay.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    to = math.radians((wind_deg + 180) % 360)  # direction the air moves toward
    ux, uy = math.sin(to), -math.cos(to)        # screen: +x east, +y south
    sp = z(64)
    length = z(70 + min(80, max(0, mph - 10) * 4))
    col = (214, 236, 255)
    for gy in range(-1, int(H_ / sp) + 2):
        for gx in range(-1, int(W_ / sp) + 2):
            x = (gx + rnd.random()) * sp
            y = (gy + rnd.random()) * sp
            phase = rnd.random() * 6.28
            pts = [(x, y)]
            steps = 16
            L = length * (0.6 + 0.6 * rnd.random())
            for k in range(steps):
                px, py = pts[-1]
                bend = 0.32 * math.sin(px / z(160) + py / z(210) + phase)  # gentle meander so it reads as flow
                a = math.atan2(uy, ux) + bend
                pts.append((px + math.cos(a) * L / steps, py + math.sin(a) * L / steps))
            for k in range(steps):
                f = (k + 1) / steps
                d.line([pts[k], pts[k + 1]], fill=(*col, int(20 + 200 * f ** 1.6)), width=max(1, int(z(1.2) + z(2.4) * f)))
            hx, hy = pts[-1]
            px, py = pts[-3]
            a = math.atan2(hy - py, hx - px)
            hs = z(9)
            d.polygon([(hx + math.cos(a) * hs, hy + math.sin(a) * hs),
                       (hx + math.cos(a + 2.5) * hs * 0.8, hy + math.sin(a + 2.5) * hs * 0.8),
                       (hx + math.cos(a - 2.5) * hs * 0.8, hy + math.sin(a - 2.5) * hs * 0.8)], fill=(*col, 235))
    lay.alpha_composite(ov.filter(ImageFilter.GaussianBlur(z(0.4))))


def sound_map(pw, ph, cfg, view, level, wind_deg, mph):
    W_, H_ = z(pw), z(ph)
    view = outlookmap._view(pw, ph, tuple(view or cfg.get("sound_view") or MAP_BOX))
    w, e, s, n = view
    proj = lambda lo, la: ((lo - w) / (e - w) * W_, (n - la) / (n - s) * H_)
    water_raw, sound_raw = _crop(view, (W_, H_))
    water, sound = _ramp(water_raw), _ramp(sound_raw)
    land = ImageChops.invert(water)
    lay = Image.new("RGBA", (W_, H_), (17, 27, 47, 255))
    lay.paste(STENCIL[:3] + (255,), (0, 0), land)
    # county / state lines, kept on land
    lines = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lines)
    from . import alertinfo
    for c in alertinfo.counties().values():
        if alertinfo.in_view(c, w, e, s, n):
            for p in c["polys"]:
                pts = [proj(x, y) for x, y in p[0]]
                ld.line(pts + [pts[0]], fill=(*STENCIL_EDGE[:3], 120), width=max(1, z(1)))
    for ln in alertinfo.state_lines():
        ld.line([proj(x, y) for x, y in ln], fill=(214, 226, 244, 200), width=max(2, z(1.8)))
    lines.putalpha(ImageChops.multiply(lines.getchannel("A"), land))
    lay.alpha_composite(lines)
    # shoreline
    edge = ImageChops.subtract(water.filter(ImageFilter.MaxFilter(3)), water)
    lay.paste((150, 172, 204, 255), (0, 0), edge)
    # risk: sound water tinted + the sound-side shoreline glowing, strongest at the north end
    col = LEVELS[max(1, level)][2]
    ramp = Image.new("L", (1, H_))
    lat_lo, lat_hi = cfg.get("sound_risk_lat", (36.40, 36.58))
    for y in range(H_):
        la = n - (y / H_) * (n - s)
        ramp.putpixel((0, y), int(255 * min(1, max(0, (la - lat_lo) / (lat_hi - lat_lo)))))
    ramp = ramp.resize((W_, H_))
    strength = {0: 0.35, 1: 0.6, 2: 0.82, 3: 1.0}[level]
    tint = ImageChops.multiply(sound, ramp).point(lambda v: int(v * 0.42 * strength))
    t_layer = Image.new("RGBA", (W_, H_), (*col, 0))
    t_layer.putalpha(tint)
    lay.alpha_composite(t_layer)
    reach = max(5, int(z(cfg.get("sound_shore_px", 13))) // 2 * 2 + 1)
    band = ImageChops.multiply(sound.filter(ImageFilter.MaxFilter(reach)), land)
    band = ImageChops.multiply(band, ramp)
    glow = band.filter(ImageFilter.GaussianBlur(z(5))).point(lambda v: int(min(255, v * 1.6) * 0.55 * strength))
    g_layer = Image.new("RGBA", (W_, H_), (*col, 0))
    g_layer.putalpha(glow)
    lay.alpha_composite(g_layer)
    b_layer = Image.new("RGBA", (W_, H_), (*col, 0))
    b_layer.putalpha(band.point(lambda v: int(v * 0.95 * strength)))
    lay.alpha_composite(b_layer)
    # wind
    if wind_deg is not None:
        _particles(lay, view, wind_deg, mph or 15)
    # labels
    d = ImageDraw.Draw(lay, "RGBA")
    for name, la, lo, kind in cfg.get("sound_places") or PLACES:
        x, y = proj(lo, la)
        if not (z(30) < x < W_ - z(30) and z(20) < y < H_ - z(20)):
            continue
        if kind == "town":
            d.ellipse([x - z(5), y - z(5), x + z(5), y + z(5)], fill=(255, 255, 255, 255), outline=(13, 21, 38, 255),
                      width=z(2))
            d.text((x + z(10), y), name, font=font("bold", 19), fill=(255, 255, 255, 255), anchor="lm",
                   stroke_width=z(3), stroke_fill=(13, 21, 38, 255))
        else:
            d.text((x, y), name, font=font("medium", 17), fill=(170, 196, 230, 235), anchor="mm",
                   stroke_width=z(2), stroke_fill=(13, 21, 38, 200))
    return lay


# ------------------------------------------------------------------ graphic
def _t(dt):
    return f"{dt.strftime('%a').upper()} {dt.strftime('%I %p').lstrip('0')}"


def _range(a, b):
    return f"{_t(a)} – {_t(b)}"


def _mph(v):
    return int(5 * round((v or 0) / 5))


def _arrow(cv, cx, cy, deg, size, col):
    """Small arrow pointing where the wind blows TO (from = deg)."""
    a = math.radians((deg + 180) % 360)
    dx, dy = math.sin(a), -math.cos(a)
    px, py = -dy, dx
    tip = (cx + dx * size, cy + dy * size)
    tail = (cx - dx * size, cy - dy * size)
    cv.line([tail, tip], col, max(2, size / 4))
    cv.d.polygon([(z(tip[0] + dx * size * 0.3), z(tip[1] + dy * size * 0.3)),
                  (z(tip[0] - dx * size * 0.45 + px * size * 0.5), z(tip[1] - dy * size * 0.45 + py * size * 0.5)),
                  (z(tip[0] - dx * size * 0.45 - px * size * 0.5), z(tip[1] - dy * size * 0.45 - py * size * 0.5))],
                 fill=col)


def _timeline(cv, box, data, wins, cfg, tz):
    x, y, w, h = box
    hrs = (data.get("hours") or [])[:cfg.get("sound_timeline_hours", 60)]
    if len(hrs) < 6:
        return
    cv.text(x, y, "HOURLY WIND  ·  ARROWS SHOW WHERE IT'S BLOWING", 17, "bold", C["muted"], anchor="lt")
    top, bot = y + 34, y + h - 34
    vmax = max(30, max((hh["gust"] or hh["wind"] or 0) for hh in hrs) + 2)
    n = len(hrs)
    bw = w / n
    t0 = hrs[0]["t"]
    X = lambda t: x + (t - t0).total_seconds() / 3600 * bw
    for wn in wins:  # flood-likely shading
        c = LEVELS[wn["level"]][2]
        a, b = max(x, X(wn["high_start"])), min(x + w, X(wn["high_end"]))
        if b > a:
            cv.rect(a, top, b - a, bot - top, (*c, 46), r=6)
    need = cfg.get("sound_wind_min", 15)
    yv = lambda v: bot - (v / vmax) * (bot - top - 26)
    cv.line([(x, yv(need)), (x + w, yv(need))], (255, 255, 255, 70), 1.5)
    cv.text(x + w, yv(need) - 4, f"{need} MPH", 13, "bold", C["muted"], anchor="rs")
    lvl_of = lambda hh: next((wn["level"] for wn in wins if wn["start"] <= hh["t"] < wn["end"]), 0)
    for i, hh in enumerate(hrs):
        v = hh["wind"] or 0
        lv = lvl_of(hh)
        c = LEVELS[lv][2] if lv else (92, 112, 142)
        cv.rect(x + i * bw + bw * 0.12, yv(v), bw * 0.76, bot - yv(v), (*c, 235 if lv else 160), r=min(3, bw * 0.3))
        if i % 3 == 1 and hh["deg"] is not None:
            _arrow(cv, x + i * bw + bw / 2, top + 12, hh["deg"], min(10, bw * 1.2), (255, 255, 255, 230) if lv else (150, 170, 200, 200))
    for i, hh in enumerate(hrs):
        t = hh["t"].astimezone(tz)
        if t.hour % 12 == 0:
            xx = x + i * bw
            cv.line([(xx, bot), (xx, bot + 6)], (255, 255, 255, 120), 1.5)
            cv.text(xx, bot + 24, (t.strftime("%a").upper() if t.hour == 0 else "NOON"), 14, "bold",
                    C["text"] if t.hour == 0 else C["muted"], anchor="ms")


def sound_flood(pkg, cfg):
    data = pkg.get("_sound")
    if not data or not data.get("hours"):
        return None
    tz = ZoneInfo(cfg["timezone"])
    wins = windows(data, cfg)
    if not wins and not cfg.get("sound_flood_always"):
        print("  - sound_flood: no strong south winds in the forecast, skipped")
        return None
    level = max([wn["level"] for wn in wins] + [0])
    main = max(wins, key=lambda wn: (wn["level"], wn["typical"], wn["hours"])) if wins else None
    head, banner, col = LEVELS[level]
    if main:
        wdeg, wmph = main["deg"], main["typical"]
    else:
        hh = max(data["hours"], key=lambda hh: hh["wind"] or 0)
        wdeg, wmph = hh["deg"], hh["wind"]
    title = "SOUND-SIDE FLOODING"
    subtitle = "SANDBRIDGE, BACK BAY & NORTHERN CURRITUCK SOUND  ·  SOUTH WIND"
    if main:
        meaning = (f"{main['dir']} winds {_mph(main['typical'] - 3)}–{_mph(main['typical'] + 3)} mph"
                   f"{' gusting to ' + str(_mph(main['gust'])) if main['gust'] else ''} {_range(main['start'], main['end']).lower().replace('–', 'to')} "
                   "will push Currituck Sound water north into Back Bay. Low roads and yards on the sound side of "
                   "Sandbridge, Back Bay, Knotts Island and Carova can flood.")
    else:
        meaning = "No long stretch of strong south wind is forecast, so water shouldn't pile up in Back Bay."
    cv = Canvas(cfg)
    cv.header(title, subtitle)
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    _paste_rounded(cv, sound_map(mw, mh, cfg, None, level, wdeg, wmph), mx, my)
    cv.d.rounded_rectangle([z(mx), z(my), z(mx + mw), z(my + mh)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
    # wind badge on the map
    if wdeg is not None:
        bx, by = mx + 18, my + 18
        txt = f"{DIRS[int(wdeg / 22.5 + 0.5) % 16]} {_mph(wmph)} MPH"
        bw_ = cv.width(txt, 24, "bold") + 86
        cv.rect(bx, by, bw_, 60, (13, 21, 38, 225), r=12)
        _arrow(cv, bx + 34, by + 30, wdeg, 15, (255, 255, 255, 255))
        cv.text(bx + 62, by + 31, txt, 24, "bold", anchor="lm")
    # panel
    compact = ph_ < 560
    cv.rect(px, py, pw_, ph_, C["panel"], r=18)
    cv.text(px + 26, py + 22, "SANDBRIDGE · BACK BAY · KNOTTS ISLAND", 19 if compact else 21, "bold", C["muted"], anchor="lt",
            maxw=pw_ - 52)
    bt, bh = py + 54, 60 if compact else 78
    cv.rect(px + 26, bt, pw_ - 52, bh, (*col, 255), r=12)
    lum = 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2]
    cv.text(px + pw_ / 2, bt + bh / 2, head, 32 if compact else 38, "bold", (20, 28, 46) if lum > 150 else C["text"],
            anchor="mm", maxw=pw_ - 80)
    yy = bt + bh + 14
    yy += cv.paragraph(px + 26, yy, meaning, 20 if compact else 23, "regular", pw_ - 52, max_lines=2 if compact else 4, lh=1.26)
    yy += 14
    cv.text(px + 26, yy, "MOST LIKELY FLOODING", 18 if compact else 20, "bold", C["muted"], anchor="lt")
    yy += 32
    room = py + ph_ - yy - (0 if compact else 210)
    rh = 62 if not compact else 50
    shown = wins[:max(1, int(room // (rh + 8)))] if wins else []
    if not shown:
        cv.text(px + 26, yy + 16, "No flooding windows in the next 3 days", 22, "bold", anchor="lm")
        yy += 44
    ncol = 2 if (compact and pw_ > 900 and len(shown) > 1) else 1
    cw = (pw_ - 52 - (16 if ncol == 2 else 0)) / ncol
    for k, wn in enumerate(shown):
        c = LEVELS[wn["level"]][2]
        cx, cy = px + 26 + (k % ncol) * (cw + 16), yy + (k // ncol) * (rh + 8)
        cv.rect(cx, cy, cw, rh, (13, 21, 38, 200), r=10)
        cv.rect(cx, cy, 8, rh, (*c, 255), r=4)
        cv.text(cx + 22, cy + rh * 0.34, _range(wn["high_start"], wn["high_end"]), 22 if not compact else 19, "bold",
                anchor="lm", maxw=cw - 40)
        cv.text(cx + 22, cy + rh * 0.74, f"{wn['dir']} wind {_mph(wn['typical'])} mph, gusts {_mph(wn['gust'])}  ·  "
                f"{LEVELS[wn['level']][1].lower().replace('sound-side flooding', 'flooding')}", 16 if not compact else 14,
                "medium", C["muted"], anchor="lm", maxw=cw - 40)
    yy += -(-len(shown) // ncol) * (rh + 8) + 10
    if not compact and py + ph_ - yy > 150:
        _timeline(cv, (px + 26, yy + 6, pw_ - 52, py + ph_ - yy - 20), data, wins, cfg, tz)
    src = "SAMPLE DATA" if data.get("where") == "SAMPLE" else f"{data.get('where', 'NWS forecast')}"
    cv.footer(pkg, source=f"{src} · shoreline © OpenStreetMap contributors")
    rows = [(_range(wn["high_start"], wn["high_end"]), LEVELS[wn["level"]][2], f"{wn['dir']} {_mph(wn['typical'])} MPH")
            for wn in wins[:4]]
    fullscreen.attach(cv, title=title, subtitle=subtitle,
                      map_fn=lambda pw, ph, view: sound_map(pw, ph, cfg, view, level, wdeg, wmph),
                      box=tuple(cfg.get("sound_view") or MAP_BOX), head_label="SANDBRIDGE · BACK BAY · KNOTTS ISLAND",
                      head_value=head, head_col=col, meaning=meaning, rows=rows,
                      source=f"{src} · shoreline © OpenStreetMap contributors",
                      big_caption=(_range(main["high_start"], main["high_end"]) if main else "NEXT 3 DAYS"),
                      big_tagline=f"SANDBRIDGE · BACK BAY: {head}")
    return [("sound_flood", cv)]
