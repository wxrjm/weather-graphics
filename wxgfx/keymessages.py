"""KEY MESSAGES: the main impacts expected this week as a numbered list (recurring, fully automatic).

Every run it ranks what the forecast data says matters most -- active NWS alerts, wintry weather, tidal flooding, storms,
rainfall, wind, freeze / heat, big temperature swings -- and shows the top few as numbered cards (colour bar by hazard),
beside a map of the most relevant NDFD field (snow, else peak gusts) or, when no gridded data is available, a
this-week-at-a-glance day strip.  Wide: map left / cards right.  Tall / social: map on top, cards below.
Config: key_messages_count (3 wide, 4 on tall formats by default when there is room), key_messages_days (look-ahead, 5).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from . import extras_data as X
from .icons import draw_icon
from .summarize import qpf_range
from .theme import C, Canvas, z

KIND_COL = {"alert": (235, 64, 64), "snow": (4, 233, 231), "tides": (88, 200, 255), "storms": (253, 149, 0),
            "rain": (60, 165, 255), "wind": (240, 200, 70), "freeze": (150, 175, 255), "heat": (255, 120, 60),
            "temps": (190, 200, 220), "other": (170, 184, 208)}
TIDE_WORD = {"action": "Near flood stage", "minor": "Minor tidal flooding", "moderate": "Moderate tidal flooding",
             "major": "Major tidal flooding"}
TIDE_RANK = {"action": 1, "minor": 2, "moderate": 3, "major": 4}


def _r5(v):
    return int(5 * round(v / 5))


def _part(t):
    h = t.hour
    return "overnight" if h < 5 else "morning" if h < 12 else "afternoon" if h < 17 else "evening" if h < 21 else "night"


def _when(t):
    return f"{t.strftime('%a')} {_part(t)}"


def _hm(t):
    return t.strftime("%I:%M %p").lstrip("0").replace(":00", "").lower()


# ---------------------------------------------------------------- impact detection
def _rain(pkg, cfg, tz, start, n):
    days = pkg["days"][start:start + n]
    tot = sum(d["qpf"] or 0 for d in days if d.get("qpf_src") in ("ndfd", "mixed"))
    rng = qpf_range(tot)
    if not rng or tot < 0.25:
        return None
    rows = [h for h in (pkg.get("hourly_ext") or [])[:96] if (h.get("qpf") or 0) >= 0.02]
    when = ""
    if rows:
        a = datetime.fromisoformat(rows[0]["time"]).astimezone(tz)
        b = datetime.fromisoformat(rows[-1]["time"]).astimezone(tz)
        when = f", mainly {_when(a)}" if _when(a) == _when(b) else f", mainly {_when(a)} into {_when(b)}"
    score = 84 if tot >= 1.0 else 78 if tot >= 0.5 else 66
    return (score, "rain", "RAIN", f"{rng.replace('Under a quarter inch', 'Under 0.25 inch')} of rain possible{when}.")


def _wind(pkg, start, n):
    days = pkg["days"][start:start + n]
    d = max(days, key=lambda x: x["max_gust"] or 0, default=None)
    g = (d or {}).get("max_gust") or 0
    if g < 25:
        return None
    hi, lo = _r5(g), max(20, _r5(g * 0.7))
    extra = " Power outages possible." if g >= 45 else " Secure loose outdoor items." if g >= 35 else ""
    return (86 if g >= 50 else 76 if g >= 40 else 68 if g >= 30 else 54, "wind", "WINDS",
            f"{lo}-{hi} mph gusts likely {d['dow_long']}.{extra}")


def _tides(pkg, cfg, tz):
    td = (pkg.get("_extras") or {}).get("tides")
    if not td or not td.get("stages"):
        return None
    hits = []
    for t in td["tides"]:
        if t["type"] != "H":
            continue
        cat = X.flood_category(t["ft"], td["stages"])
        if cat in ("minor", "moderate", "major"):
            hits.append((t["time"].astimezone(tz), cat, t["ft"]))
    if not hits:
        return None
    hits.sort()
    worst = max((h[1] for h in hits[:6]), key=lambda c: TIDE_RANK[c])
    h2 = hits[:2]
    if len(h2) == 2 and h2[0][1] == h2[1][1]:
        txt = f"{TIDE_WORD[h2[0][1]]} {_when(h2[0][0])} ({_hm(h2[0][0])}) and {_when(h2[1][0])} ({_hm(h2[1][0])})."
    else:
        txt = "; ".join(f"{TIDE_WORD[c]} {_when(t)} ({_hm(t)})" for t, c, _ in h2) + "."
    return ({"minor": 82, "moderate": 92, "major": 98}[worst], "tides", "TIDES", txt)


def _alert(pkg):
    al = [a for a in pkg.get("alerts") or [] if a.get("affects_home", True)]
    if not al:
        return None
    a = al[0]
    more = f" (+{len(al) - 1} more)" if len(al) > 1 else ""
    return (100, "alert", a["event"].upper(), f"In effect {a['ends_label']}{more}.")


_WTK_KIND = {"STORMS": ("storms", "STORMS"), "SNOW": ("snow", "SNOW"), "FREEZE": ("freeze", "FREEZE"),
             "HEAT": ("heat", "HEAT"), "HEAT & HUMIDITY": ("heat", "HEAT & HUMIDITY"), "COOLDOWN": ("temps", "COOLDOWN"),
             "WARMUP": ("temps", "WARMUP"), "HUMIDITY": ("other", "HUMIDITY")}
_WTK_SCORE = {"snow": 95, "storms": 90, "freeze": 85, "heat": 80, "temps": 60, "other": 50}


def _temps(pkg, start, n):
    ds = pkg["days"][start:start + n]
    hi = [d["high"] for d in ds if d["high"] is not None]
    lo = [d["low"] for d in ds if d["low"] is not None]
    if not hi or not lo:
        return None
    return (40, "temps", "TEMPERATURES",
            f"Highs {min(hi)}-{max(hi)}°, lows {min(lo)}-{max(lo)}° through {ds[-1]['dow_long']}.")


def impacts(pkg, cfg):
    tz = ZoneInfo(cfg["timezone"])
    start = 1 if pkg.get("evening_mode") and len(pkg["days"]) > 1 else 0
    n = cfg.get("key_messages_days", 5)
    out = [x for x in (_alert(pkg), _tides(pkg, cfg, tz), _rain(pkg, cfg, tz, start, n), _wind(pkg, start, n)) if x]
    seen = {x[2] for x in out}
    for w in pkg.get("what_to_know") or []:
        lab = w["label"].rstrip(":").upper()
        if lab not in _WTK_KIND:
            continue
        kind, title = _WTK_KIND[lab]
        if title in seen:
            continue
        out.append((_WTK_SCORE.get(kind, 50), kind, title, w["text"]))
        seen.add(title)
    t = _temps(pkg, start, n)
    if t:
        out.append(t)
    d = pkg["days"][start]
    out.append((10, "other", "OUTLOOK", d["text"].split(". ")[0].rstrip(".") + "."))
    out.sort(key=lambda x: -x[0])
    return out


# ---------------------------------------------------------------- drawing
def _map_panel(cv, box, pkg, cfg):
    """Left / top panel: the most relevant gridded NDFD field, else a day strip.  Returns True if drawn."""
    data = pkg.get("_ndfdmaps") or {}
    field = None
    try:
        import numpy as np
        from . import ndfdmap, outlookmap
        from .alertmap import _paste_rounded
        sn, gu = data.get("snow"), data.get("gust")
        if sn is not None and sn["val"].size and float(np.nanmax(sn["val"])) >= cfg.get("snow_map_min", 0.1):
            field, bins, unit, label, view, smooth = sn, ndfdmap.SNOW_BINS, "IN", "SNOWFALL FORECAST", None, 0
        elif gu is not None:
            field, bins, unit, label = gu, ndfdmap.WIND_BINS, "MPH", "PEAK WIND GUSTS · NEXT 24 HOURS"
            view, smooth = ndfdmap._wind_box(cfg), cfg.get("wind_smooth", 2)
        if field is not None:
            x, y, w, h = box
            lay = outlookmap.draw_map([], w, h, cfg, outline=False,
                                      painter=ndfdmap._cell_painter(field, bins, smooth=smooth), view=view)
            _paste_rounded(cv, lay, x, y)
            cv.d.rounded_rectangle([z(x), z(y), z(x + w), z(y + h)], radius=z(18), outline=(255, 255, 255, 90), width=z(2))
            ext = tuple(view or cfg.get("outlook_view") or outlookmap.VIEW_BOX)
            lb = ndfdmap._trim_bins(bins, ndfdmap._plotted_range(field, ext))
            ndfdmap._color_bar(cv, x + 16, y + h - 70, lb, unit, w - 32)
            sz = 26 if not cv.tall else 30
            tw = cv.width(label, sz, "bold") + 34
            cv.rect(x + 16, y + 16, tw, sz * 1.9, (6, 12, 26, 220), r=12)
            cv.text(x + 33, y + 16 + sz * 0.95, label, sz, "bold", anchor="lm")
            return True
    except Exception as e:  # a missing / odd grid must never kill the graphic
        print(f"  - key_messages: map skipped ({e!r})")
    _week_strip(cv, box, pkg)
    return True


def _week_strip(cv, box, pkg):
    x, y, w, h = box
    cv.rect(x, y, w, h, C["panel"], r=18)
    start = 1 if pkg.get("evening_mode") and len(pkg["days"]) > 1 else 0
    days = pkg["days"][start:start + (5 if not cv.tall else 5)]
    if h > 520:
        cv.text(x + 28, y + 40, "THIS WEEK AT A GLANCE", 26 if not cv.tall else 30, "bold", C["muted"], anchor="lm")
    n = len(days)
    cw = (w - 40) / max(1, n)
    for i, d in enumerate(days):
        cx = x + 20 + cw * (i + 0.5)
        cv.text(cx, y + h * 0.14, d["dow"], 34 if not cv.tall else 36, "bold", anchor="mm")
        draw_icon(cv, d["icon"], cx, y + h * 0.38, min(120 if h > 520 else 90, cw * 0.78))
        cv.text(cx, y + h * 0.63, f"{d['high']}°", 52 if not cv.tall else 48, "bold", anchor="mm")
        cv.text(cx, y + h * 0.78, f"{d['low']}°", 32, "medium", C["muted"], anchor="mm")
        pop = d["pop"] or 0
        cv.text(cx, y + h * 0.92, f"{pop}%" if pop >= 20 else "—", 34, "bold", C["rain"] if pop >= 20 else C["muted"], anchor="mm")


def _card(cv, box, num, kind, title, text):
    x, y, w, h = box
    col = KIND_COL.get(kind, KIND_COL["other"])
    cv.rect(x, y, w, h, C["panel"], r=16)
    cv.rect(x, y + 14, 9, h - 28, (*col, 255), r=4)
    r = min(34, h * 0.17)
    cx, cy = x + 34 + r, y + 20 + r + 4
    cv.d.ellipse([z(cx - r), z(cy - r), z(cx + r), z(cy + r)], fill=(255, 255, 255, 255))
    cv.text(cx, cy, str(num), r * 1.15, "bold", (10, 22, 48), anchor="mm")
    ts = 40 if not cv.tall else 42
    cv.text(cx + r + 22, cy, title, ts, "bold", col, anchor="lm", maxw=w - (r * 2 + 90))
    ty = cy + r + 12
    cv.paragraph(x + 34, ty, text, 29 if not cv.tall else 33, "medium", w - 64, max_lines=4, lh=1.22, fill=(226, 232, 244),
                 anchor="la", valign="top", box_h=y + h - ty - 12)


def key_messages(pkg, cfg):
    items = impacts(pkg, cfg)
    cv = Canvas(cfg)
    cv.header("KEY MESSAGES", f"MAIN IMPACTS THIS WEEK  ·  {pkg['location']['area'].upper()}")
    (mx, my, mw, mh), (px, py, pw_, ph_) = cv.split()
    n = cfg.get("key_messages_count", 4 if (cv.tall and cv.fmt == "vertical") else 3)
    items = items[:n]
    if cv.tall:  # give the cards more room than the default half/half split
        tot = (py + ph_) - my
        mh = tot * 0.30
        py, ph_ = my + mh + 16, tot - mh - 16
    _map_panel(cv, (mx, my, mw, mh), pkg, cfg)
    gap = 16
    ch = (ph_ - gap * (len(items) - 1)) / len(items)
    for i, (_, kind, title, text) in enumerate(items):
        _card(cv, (px, py + i * (ch + gap), pw_, ch), i + 1, kind, title, text)
    cv.footer(pkg, source="National Weather Service (NDFD)" if "SAMPLE" not in pkg.get("source", "") else "SAMPLE DATA")
    cv.used_split = False  # its own card layout: no map-only twin
    return cv
