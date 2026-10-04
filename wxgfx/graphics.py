"""Each graphic: fn(pkg, cfg) -> Canvas (or None when not relevant today)."""
from .theme import Canvas, C, z
from .icons import draw_icon

NIGHT_ICONS = True


def _days_from(pkg, start, n):
    return pkg["days"][start:start + n]


# ---------------------------------------------------------------- 7 DAY
def seven_day(pkg, cfg):
    cv = Canvas(cfg)
    evening = pkg.get("evening_mode")
    cols = []
    days = pkg["days"]
    if evening and days:
        d = days[0]
        cols.append({"label": "TONIGHT", "sub": d["date_label"], "icon": d["night_icon"], "night": True,
                     "big": d["low"], "small": None, "cond": d["night_cond"], "pop": d["night_pop"]})
        rest = days[1:7]
    else:
        rest = days[:7]
    for i, d in enumerate(rest):
        label = "TODAY" if (not evening and i == 0) else d["dow"]
        cols.append({"label": label, "sub": d["date_label"], "icon": d["icon"], "night": False,
                     "big": d["high"], "small": d["low"], "cond": d["cond"], "pop": d["pop"]})
    cols = cols[:7]
    cv.header(f"{len(cols)}-DAY FORECAST", pkg["location"]["area"])
    if cv.tall:
        return _seven_day_rows(cv, cols, pkg)
    n = len(cols)
    gap, x0, top, h = 16, 70, 205, 800
    cw = (1780 - gap * (n - 1)) / n
    for i, c in enumerate(cols):
        x = x0 + i * (cw + gap)
        cx = x + cw / 2
        cv.rect(x, top, cw, h, C["panel_hi"] if i == 0 else C["panel"], r=18)
        cv.rect(x, top, cw, 8, C["rule"], r=4)
        cv.text(cx, top + 72, c["label"], 44, "bold", anchor="ms", maxw=cw - 20)
        cv.text(cx, top + 110, c["sub"].upper(), 24, "medium", C["muted"], anchor="ms")
        draw_icon(cv, c["icon"], cx, top + 245, min(170, cw * 0.72), night=c["night"])
        if c["small"] is None:  # tonight column
            cv.text(cx, top + 470, f"{c['big']}°", 90, "bold", anchor="ms")
            cv.text(cx, top + 515, "LOW", 26, "medium", C["muted"], anchor="ms")
        else:
            cv.text(cx, top + 470, f"{c['big']}°", 90, "bold", anchor="ms")
            cv.text(cx, top + 530, f"{c['small']}°", 46, "medium", C["muted"], anchor="ms")
        cv.paragraph(cx, top + 565, c["cond"], 27, "medium", cw - 26, max_lines=3, anchor="ma", lh=1.2)
        pop = c["pop"] or 0
        if pop >= 20:
            cv.text(cx, top + h - 34, f"{pop}%", 40, "bold", C["rain"], anchor="ms")
            cv.text(cx, top + h - 80, "RAIN", 20, "medium", C["rain"], anchor="ms")
        else:
            cv.text(cx, top + h - 34, "—", 40, "bold", C["muted"], anchor="ms")
    cv.footer(pkg)
    return cv


def _seven_day_rows(cv, cols, pkg):
    """Tall formats: one row per day."""
    M, top, bot = cv.M, cv.top + 6, cv.bottom
    n, gap = len(cols), 12
    rh = (bot - top - gap * (n - 1)) / n
    W = cv.W - 2 * M
    big = min(64, rh * 0.42)
    for i, c in enumerate(cols):
        y = top + i * (rh + gap)
        cv.rect(M, y, W, rh, C["panel_hi"] if i == 0 else C["panel"], r=14)
        cv.rect(M, y, 8, rh, C["rule"], r=3)
        cy = y + rh / 2
        cv.text(M + 30, cy - rh * 0.08, c["label"], min(40, rh * 0.3), "bold", anchor="ls", maxw=200)
        cv.text(M + 30, cy + rh * 0.2, c["sub"].upper(), min(24, rh * 0.18), "medium", C["muted"], anchor="ls")
        draw_icon(cv, c["icon"], M + 300, cy + 2, min(118, rh * 0.82), night=c["night"])
        cv.text(M + 470, cy + big * 0.36, f"{c['big']}°", big, "bold", anchor="ms")
        if c["small"] is not None:
            cv.text(M + 590, cy + big * 0.36, f"{c['small']}°", big * 0.6, "medium", C["muted"], anchor="ms")
        else:
            cv.text(M + 590, cy + big * 0.2, "LOW", big * 0.38, "medium", C["muted"], anchor="ms")
        pop = c["pop"] or 0
        tx, tw = M + 660, W - 660 - (130 if pop >= 20 else 20)
        cv.paragraph(tx, y, c["cond"], min(27, rh * 0.2), "medium", tw, max_lines=2, lh=1.18,
                     valign="middle", box_h=rh)
        if pop >= 20:
            cv.text(M + W - 22, cy + rh * 0.02, f"{pop}%", min(36, rh * 0.27), "bold", C["rain"], anchor="rs")
            cv.text(M + W - 22, cy + rh * 0.24, "RAIN", min(18, rh * 0.14), "medium", C["rain"], anchor="rs")
    cv.footer(pkg)
    return cv


# ---------------------------------------------------------------- DAILY
def daily(pkg, cfg):
    cv = Canvas(cfg)
    t = pkg["today"]
    d = pkg["days"][t["day_index"]]
    cv.header(t.get("title", "TODAY'S FORECAST"), f"{d['dow_long']}, {d['date_label']}  ·  {pkg['location']['area']}")
    if cv.tall:
        return _daily_tall(cv, t, d, pkg)
    # left: icon, hi/lo, headline
    lx, lw, top = 70, 560, 205
    cv.rect(lx, top, lw, 620, C["panel"], r=18)
    draw_icon(cv, d["icon"], lx + lw / 2, top + 150, 230)
    cv.text(lx + lw * 0.3, top + 385, f"{d['high']}°", 104, "bold", anchor="ms")
    cv.text(lx + lw * 0.3, top + 425, "HIGH", 24, "medium", C["muted"], anchor="ms")
    cv.text(lx + lw * 0.72, top + 385, f"{d['low']}°", 72, "medium", C["muted"], anchor="ms")
    cv.text(lx + lw * 0.72, top + 425, "LOW", 24, "medium", C["muted"], anchor="ms")
    cv.paragraph(lx + lw / 2, top + 470, t.get("headline") or d["headline"], 38, "bold", lw - 50, max_lines=3, anchor="ma", lh=1.15)
    # right: timeline rows
    rows = t.get("timeline") or []
    rx, rw = 660, 1190
    rh, gap = (620 - 3 * 14) / 4, 14
    for i, r in enumerate(rows[:4]):
        y = top + i * (rh + gap)
        cv.accent_row(rx, y, rw, rh)
        cv.text(rx + 34, y + rh / 2, r["label"], 42, "bold", anchor="lm", maxw=300)
        if r.get("icon"):
            draw_icon(cv, r["icon"], rx + 405, y + rh / 2 + 4, 92, night=r["label"] in ("EVENING", "OVERNIGHT"))
        cv.paragraph(rx + 480, y + 4, r["text"], 29, "regular", rw - 510, max_lines=3, valign="middle", box_h=rh - 8, lh=1.25)
    # bottom summary
    cv.accent_row(70, 845, 1780, 160)
    cv.paragraph(104, 848, t.get("text") or d["text"], 29, "regular", 1720, max_lines=3, valign="middle", box_h=154, lh=1.3)
    cv.footer(pkg)
    return cv


def _daily_tall(cv, t, d, pkg):
    M, top, bot, W = cv.M, cv.top, cv.bottom, cv.W - 2 * cv.M
    vert = cv.fmt == "vertical"
    hb = 500 if vert else 330
    cv.rect(M, top, W, hb, C["panel"], r=18)
    ic = 250 if vert else 170
    draw_icon(cv, d["icon"], M + W * 0.26, top + hb * 0.36, ic)
    hs = 118 if vert else 92
    cv.text(M + W * 0.63, top + hb * 0.42, f"{d['high']}°", hs, "bold", anchor="ms")
    cv.text(M + W * 0.63, top + hb * 0.42 + 38, "HIGH", 22, "medium", C["muted"], anchor="ms")
    cv.text(M + W * 0.87, top + hb * 0.42, f"{d['low']}°", hs * 0.66, "medium", C["muted"], anchor="ms")
    cv.text(M + W * 0.87, top + hb * 0.42 + 38, "LOW", 22, "medium", C["muted"], anchor="ms")
    cv.paragraph(M + W / 2, top + hb * (0.72 if vert else 0.7), t.get("headline") or d["headline"],
                 44 if vert else 36, "bold", W - 60, max_lines=2, anchor="ma", lh=1.12)
    sum_h = 250 if vert else 190
    rows = (t.get("timeline") or [])[:4]
    ry0, gap = top + hb + 16, 14
    rh = (bot - sum_h - 16 - ry0 - gap * (max(1, len(rows)) - 1)) / max(1, len(rows))
    for i, r in enumerate(rows):
        y = ry0 + i * (rh + gap)
        cv.accent_row(M, y, W, rh)
        cv.text(M + 30, y + rh / 2, r["label"], min(34, rh * 0.28), "bold", anchor="lm", maxw=240)
        if r.get("icon"):
            draw_icon(cv, r["icon"], M + 320, y + rh / 2 + 3, min(84, rh * 0.68), night=r["label"] in ("EVENING", "OVERNIGHT"))
        cv.paragraph(M + 385, y + 2, r["text"], min(33, rh * 0.21), "regular", W - 410, max_lines=3,
                     valign="middle", box_h=rh - 4, lh=1.22)
    sy = bot - sum_h
    cv.accent_row(M, sy, W, sum_h)
    cv.paragraph(M + 32, sy, t.get("text") or d["text"], 31 if vert else 24, "regular", W - 60, max_lines=6 if vert else 5,
                 valign="middle", box_h=sum_h, lh=1.28)
    cv.footer(pkg)
    return cv


# ---------------------------------------------------------------- WHAT TO KNOW
def what_to_know(pkg, cfg):
    items = pkg.get("what_to_know") or []
    if not items:
        return None
    cv = Canvas(cfg)
    cv.header("WHAT TO KNOW:", pkg["location"]["area"])
    if cv.tall:
        rows = items[:4]
        M, W, gap = cv.M, cv.W - 2 * cv.M, 20
        rh = (cv.bottom - cv.top - 5 - gap * (len(rows) - 1)) / len(rows)
        for i, it in enumerate(rows):
            y = cv.top + 5 + i * (rh + gap)
            cv.accent_row(M, y, W, rh)
            ls = min(54, rh * 0.2)
            cv.text(M + 34, y + 28 + ls * 0.8, it["label"], ls, "bold", anchor="ls", maxw=W - 60)
            cv.paragraph(M + 34, y + 28 + ls * 1.2, it["text"], min(42, rh * 0.15), "regular", W - 64,
                         max_lines=4, valign="middle", box_h=rh - 36 - ls * 1.2, lh=1.25)
        cv.footer(pkg)
        return cv
    top, rh, gap = 210, 180, 24
    lw = max(cv.width(i["label"], 52, "bold") for i in items[:4])
    lw = min(max(lw, 380), 760)
    for i, it in enumerate(items[:4]):
        y = top + i * (rh + gap)
        cv.accent_row(70, y, 1780, rh)
        cv.text(104, y + rh / 2, it["label"], 52, "bold", anchor="lm", maxw=lw)
        cv.paragraph(104 + lw + 40, y, it["text"], 34, "regular", 1780 - lw - 110, max_lines=3,
                     valign="middle", box_h=rh, lh=1.25)
    cv.footer(pkg)
    return cv


# ---------------------------------------------------------------- BANDED CHARTS
def _banded(cv, bands, values, axis=None, bar_color=None, value_fmt="{}", display=None):
    """bands: list of (label, lo, hi, rgb, dark_text) bottom->top. values: [(label, value)]."""
    if cv.tall:
        x0, x1, top, bot = cv.M, cv.W - cv.M - (58 if axis else 0), cv.top, cv.bottom - 110
    else:
        x0, x1, top, bot = 70, 1780 if axis else 1850, 205, 870
    bh = (bot - top) / len(bands)
    lab_max = min(40, bh * 0.62) if not cv.tall else min(32, bh * 0.5)
    for i, (label, lo, hi, col, dark) in enumerate(bands):
        y = bot - (i + 1) * bh
        cv.rect(x0, y, x1 - x0, bh, col)
        cv.text(x0 + 18, y + bh / 2, label, lab_max, "medium",
                (22, 32, 52) if dark else C["text"], anchor="lm", maxw=(x1 - x0) * 0.36 if cv.tall else None)
    if axis:
        ax = x1 + 20
        for i, (label, lo, hi, col, dark) in enumerate(bands):
            cv.text(ax, bot - i * bh, str(lo), 24 if not cv.tall else 21, "medium", C["muted"], anchor="lm")
        cv.text(ax, top, str(bands[-1][2]), 24 if not cv.tall else 21, "medium", C["muted"], anchor="lm")

    def ypos(v):
        if v <= bands[0][1]:
            return bot - 24
        for i, (_, lo, hi, *_r) in enumerate(bands):
            if v <= hi:
                return bot - i * bh - (v - lo) / (hi - lo) * bh
        return top + 6
    n = len(values)
    area0, area1 = (x0 + 620, x1 - 30) if not cv.tall else (x0 + (x1 - x0) * 0.38, x1 - 16)
    slot = (area1 - area0) / n
    bw = min(125, slot * 0.72)
    lab, val = (40, 44) if not cv.tall else (min(34, slot * 0.34), min(40, slot * 0.4))
    for i, (label, v) in enumerate(values):
        cx = area0 + slot * (i + 0.5)
        cv.text(cx, bot + 58 if not cv.tall else bot + 50, label, lab, "medium", anchor="ms")
        if v is None:
            continue
        y = ypos(v)
        cv.rect(cx - bw / 2, y, bw, bot - y, (*(bar_color or C["bar"]), 255))
        cv.text(cx, y - 12, display(v) if display else value_fmt.format(v), val, "bold", anchor="ms", stroke=1.2)


HEAT_BANDS = [("CAUTION", 80, 90, (255, 232, 0), True), ("EXTREME CAUTION", 90, 103, (255, 153, 0), False),
              ("DANGEROUS", 103, 125, (228, 0, 0), False), ("EXTREME DANGER", 125, 140, (150, 0, 255), False)]
CHILL_BANDS = [("CHILLY", 32, 45, (120, 190, 235), True), ("COLD", 20, 32, (60, 130, 210), False),
               ("BITTER", 5, 20, (40, 80, 170), False), ("DANGEROUS", -20, 5, (95, 40, 160), False)]
DEW_BANDS = [("AWESOME", 50, 55, (190, 145, 0), False), ("PLEASANT", 55, 60, (245, 176, 110), True),
             ("STICKY", 60, 65, (222, 236, 216), True), ("HUMID", 65, 70, (186, 216, 166), True),
             ("MISERABLE", 70, 75, (102, 166, 76), False), ("INSTANT SWEAT", 75, 80, (40, 86, 30), False)]
WIND_BANDS = [("LIGHT", 0, 15, (170, 215, 235), True), ("BREEZY", 15, 25, (95, 170, 215), False),
              ("WINDY", 25, 40, (45, 115, 185), False), ("VERY WINDY", 40, 58, (30, 60, 140), False),
              ("DAMAGING", 58, 80, (120, 30, 120), False)]


def _chart_days(pkg, n):
    start = 1 if pkg.get("evening_mode") else 0
    return _days_from(pkg, start, n)


def feels_like(pkg, cfg):
    """Heat index; skipped when it's not hot enough to matter. (Wind chill is its own graphic.)"""
    days = _chart_days(pkg, 5)
    his = [d.get("max_hi") or 0 for d in days]
    wcs = [d.get("min_wc") for d in days if d.get("min_wc") is not None]
    cv = Canvas(cfg)
    if max(his, default=0) >= cfg.get("heat_index_min", 90):
        cv.header("HEAT INDEX VALUES", pkg["location"]["area"])
        _banded(cv, HEAT_BANDS, [(d["dow"], d.get("max_hi")) for d in days], value_fmt="{}")
    else:
        return None
    cv.footer(pkg)
    return cv


def _chill_color(t):
    """0 = icy light blue ... 1 = deep indigo."""
    stops = [(0.0, (196, 228, 250)), (0.3, (110, 180, 235)), (0.55, (45, 120, 205)),
             (0.8, (28, 70, 160)), (1.0, (40, 30, 120))]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if t <= b:
            f = (t - a) / (b - a)
            return tuple(int(ca[i] + (cb[i] - ca[i]) * f) for i in range(3))
    return stops[-1][1]


def wind_chill(pkg, cfg):
    """Blue banded chart: top band is 30°, each band below it 5° colder, adding bands as needed.
    Bars grow with temperature, so a colder wind chill is a SHORTER bar.
    Skipped when no day's wind chill reaches the threshold."""
    import math
    days = _chart_days(pkg, 5)
    vals = [(d["dow"], d.get("min_wc")) for d in days]
    wcs = [v for _, v in vals if v is not None]
    start = cfg.get("wind_chill_start", 30)
    if not wcs or min(wcs) > start + cfg.get("wind_chill_margin", 5):
        return None
    coldest = min(wcs)
    n = max(cfg.get("wind_chill_min_bands", 5), math.ceil((start - coldest) / 5) + 1)  # +1 so coldest bar isn't empty
    n = min(n, 14)
    bands = []  # bottom (coldest, darkest) -> top (30°, lightest); band "X°" spans X-5 .. X
    for i in range(n):
        top_t = start - 5 * (n - 1 - i)
        t = (n - 1 - i) / max(1, n - 1)  # 1 = coldest
        bands.append((f"{top_t}°", top_t - 5, top_t, _chill_color(t), t < 0.3))
    cv = Canvas(cfg)
    cv.header("WIND CHILL VALUES", pkg["location"]["area"])
    _banded(cv, bands, vals, value_fmt="{}°")
    cv.footer(pkg)
    return cv


def dewpoints(pkg, cfg):
    days = _chart_days(pkg, 5)
    cv = Canvas(cfg)
    cv.header("DEWPOINTS", pkg["location"]["area"])
    _banded(cv, DEW_BANDS, [(d["dow"], d.get("max_dew")) for d in days], axis=True)
    cv.footer(pkg)
    return cv


def wind(pkg, cfg):
    days = _chart_days(pkg, 7)
    cv = Canvas(cfg)
    cv.header("PEAK WIND GUSTS", pkg["location"]["area"])
    _banded(cv, WIND_BANDS, [(d["dow"], d.get("max_gust")) for d in days])
    cv.footer(pkg)
    return cv


# ---------------------------------------------------------------- RAIN TOTALS
def rain_totals(pkg, cfg):
    days = _chart_days(pkg, 7)
    have = [d for d in days if d.get("qpf") is not None]
    total = sum(d["qpf"] for d in have)
    guided = [d for d in have if d.get("qpf_src") in ("guidance", "mixed")]
    cv = Canvas(cfg)
    span = f"{len(have)}-DAY TOTAL" if len(have) == len(days) else f"TOTAL THROUGH {have[-1]['dow'] if have else '--'}"
    cv.header("RAINFALL FORECAST", f"{pkg['location']['area']}  ·  {span}: {total:.2f}\"")
    if cv.tall:
        top, bot, x0, x1 = cv.top + 40, cv.bottom - 130, cv.M + 96, cv.W - cv.M
    else:
        top, bot, x0, x1 = 230, 850, 170, 1850
    tall = cv.tall
    vmax = max(1.0, max((d.get("qpf") or 0 for d in days), default=0) * 1.25)
    step = 0.25 if vmax <= 1.5 else 0.5 if vmax <= 3 else 1.0
    v = 0.0
    while v <= vmax + 1e-6:
        y = bot - v / vmax * (bot - top)
        cv.line([(x0, y), (x1, y)], (255, 255, 255, 40), 1.5)
        cv.text(x0 - 20, y, f'{v:.2f}"', 24 if not tall else 21, "medium", C["muted"], anchor="rm")
        v += step
    slot = (x1 - x0) / len(days)
    fs = (40, 26, 38) if not tall else (min(34, slot * 0.3), 22, min(30, slot * 0.27))
    for i, d in enumerate(days):
        cx = x0 + slot * (i + 0.5)
        cv.text(cx, bot + 56, d["dow"], fs[0], "medium", anchor="ms")
        cv.text(cx, bot + 92, f"{d.get('pop') or 0}%", fs[1], "medium", C["muted"], anchor="ms")
        if d.get("qpf") is None:  # no rainfall data for this day -- don't pretend it's dry
            cv.text(cx, bot - 14, "N/A", fs[2] - 4, "bold", C["muted"], anchor="ms")
            continue
        q = d["qpf"]
        est = d.get("qpf_src") in ("guidance", "mixed")
        y = bot - q / vmax * (bot - top)
        if q >= 0.01:
            bx, bw = cx - slot * 0.3, slot * 0.6
            cv.rect(bx, y, bw, bot - y, (*C["rain"], 120 if est else 255), r=6)
            if est:  # diagonal stripes = model guidance
                cv.d.rounded_rectangle([z(bx), z(y), z(bx + bw), z(bot)], radius=z(6), outline=(*C["rain"], 255), width=z(2))
                k = 0
                while k < bw + (bot - y):
                    a = (bx + max(0, k - (bot - y)), bot - min(k, bot - y))
                    b = (bx + min(k, bw), bot - max(0, k - bw))
                    cv.line([a, b], (*C["rain"], 200), 2)
                    k += 18
        label = (f'{q:.2f}"' if q >= 0.01 else "DRY") + ("*" if est else "")
        cv.text(cx, y - 14, label, fs[2], "bold", anchor="ms", stroke=2)
    cv.text(x0 - 20, bot + 92, "CHANCE", 20 if not tall else 16, "medium", C["muted"], anchor="rs")
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else None
    if guided:
        from .extended import MODEL_LABELS
        m = MODEL_LABELS.get((pkg.get("rain_guidance") or {}).get("model"), "model guidance")
        note = f"* {guided[0]['dow'].title()} onward includes {m} guidance (NWS rainfall amounts only go out 3 days)"
        if tall:
            cv.text(cv.M, cv.H - 62, note.upper(), 16, "medium", C["muted"], anchor="ls", maxw=cv.W - 2 * cv.M)
        else:
            cv.text(1850, 1046, note.upper(), 19, "medium", C["muted"], anchor="rs")
    elif len(have) < len(days):
        note = "N/A = BEYOND THE NWS 3-DAY RAINFALL FORECAST"
        if tall:
            cv.text(cv.M, cv.H - 62, note, 16, "medium", C["muted"], anchor="ls")
        else:
            cv.text(1850, 1046, note, 19, "medium", C["muted"], anchor="rs")
    cv.footer(pkg, source=src)
    return cv


# ---------------------------------------------------------------- HOURLY
def hourly(pkg, cfg):
    hrs = (pkg.get("hourly") or [])[:24]
    if len(hrs) < 6:
        return None
    cv = Canvas(cfg)
    cv.header("NEXT 24 HOURS", pkg["location"]["area"])
    if cv.tall:
        T, B = cv.top, cv.bottom
        x0, x1 = cv.M + 44, cv.W - cv.M - 44
        icon_y, lab_y = T + 75, B - 20
        p_bot = lab_y - 64
        p_top = p_bot - (B - T) * 0.2
        t_top, t_bot = T + 210, p_top - 80
    else:
        x0, x1 = 110, 1810
        t_top, t_bot = 380, 690
        p_top, p_bot = 760, 900
        icon_y, lab_y = 262, 960
    temps = [h["temp"] for h in hrs]
    lo, hi = min(temps) - 3, max(temps) + 3
    step = (x1 - x0) / (len(hrs) - 1)
    pts = [(x0 + i * step, t_bot - (h["temp"] - lo) / (hi - lo) * (t_bot - t_top)) for i, h in enumerate(hrs)]
    # pop bars
    cv.rect(x0 - 30, p_top - 10, x1 - x0 + 60, p_bot - p_top + 20, C["panel"], r=10)
    cv.text(x0 - 20, p_top + 10, "RAIN CHANCE", 20, "medium", C["muted"], anchor="la")
    for i, h in enumerate(hrs):
        pv = h.get("pop") or 0
        if pv >= 10:
            bh = pv / 100 * (p_bot - p_top)
            cv.rect(pts[i][0] - step * 0.35, p_bot - bh, step * 0.7, bh, (*C["rain"], 200), r=3)
    cv.line(pts, C["rule"], 5)
    for i, h in enumerate(hrs):
        x, y = pts[i]
        if i % 3 == 0:
            cv.rect(x - 9, y - 9, 18, 18, C["rule"], r=9)
            cv.text(x, y - 26, f"{h['temp']}°", 40 if not cv.tall else 34, "bold", anchor="ms", stroke=2)
            hr = int(h["time"][11:13])
            draw_icon(cv, h["icon"], x, icon_y, 86 if not cv.tall else 72, night=not (7 <= hr < 19))
            cv.text(x, lab_y, h["label"], 30 if not cv.tall else 25, "bold", anchor="ms")
            if (h.get("pop") or 0) >= 20:
                cv.text(x, p_top + 42, f"{h['pop']}%", 24 if not cv.tall else 21, "bold", C["rain"], anchor="ms")
    cv.footer(pkg)
    return cv


# ---------------------------------------------------------------- CURRENT
def current(pkg, cfg):
    o = pkg.get("current")
    if not o:
        return None
    cv = Canvas(cfg)
    cv.header("CURRENT CONDITIONS", f"{pkg['location']['name']} ({pkg['location']['station']})  ·  {o['time_label']}")
    wind = "Calm" if not o.get("wind") else f"{o.get('wind_dir') or ''} {o['wind']} mph".strip()
    if o.get("gust"):
        wind += f" G{o['gust']}"
    tiles = [("FEELS LIKE", f"{o.get('feels_like')}°"), ("DEWPOINT", f"{o.get('dewpoint')}°"),
             ("HUMIDITY", f"{o.get('humidity')}%"), ("WIND", wind),
             ("PRESSURE", f"{o.get('pressure')}\""), ("VISIBILITY", f"{o.get('visibility')} mi")]
    if cv.tall:
        M, W, top = cv.M, cv.W - 2 * cv.M, cv.top
        vert = cv.fmt == "vertical"
        hb = 640 if vert else 420
        cv.rect(M, top, W, hb, C["panel"], r=18)
        if vert:
            draw_icon(cv, o["icon"], M + W / 2, top + 170, 230, night=o.get("night", False))
            cv.text(M + W / 2, top + 490, f"{o['temp']}°", 190, "bold", anchor="ms")
            cv.paragraph(M + W / 2, top + 530, o["cond"] or "", 42, "medium", W - 80, max_lines=2, anchor="ma", lh=1.1)
        else:
            draw_icon(cv, o["icon"], M + W * 0.27, top + hb * 0.45, 210, night=o.get("night", False))
            cv.text(M + W * 0.7, top + hb * 0.55, f"{o['temp']}°", 170, "bold", anchor="ms")
            cv.paragraph(M + W / 2, top + hb * 0.72, o["cond"] or "", 38, "medium", W - 80, max_lines=1, anchor="ma")
        gx, gy = 22, 20
        ty0 = top + hb + 20
        tw, th = (W - gx) / 2, (cv.bottom - ty0 - 2 * gy) / 3
        for i, (label, val) in enumerate(tiles):
            x = M + (i % 2) * (tw + gx)
            y = ty0 + (i // 2) * (th + gy)
            cv.accent_row(x, y, tw, th)
            cv.text(x + 34, y + th * 0.34, label, min(28, th * 0.16), "bold", C["muted"], anchor="ls")
            cv.text(x + 34, y + th * 0.78, val.replace("None", "--"), min(64, th * 0.36), "bold", anchor="ls", maxw=tw - 60)
        cv.footer(pkg)
        return cv
    cv.rect(70, 205, 700, 800, C["panel"], r=18)
    draw_icon(cv, o["icon"], 420, 360, 240, night=o.get("night", False))
    cv.text(420, 700, f"{o['temp']}°", 200, "bold", anchor="ms")
    cv.paragraph(420, 760, o["cond"] or "", 44, "medium", 620, max_lines=2, anchor="ma", lh=1.15)
    wind = "Calm" if not o.get("wind") else f"{o.get('wind_dir') or ''} {o['wind']} mph".strip()
    if o.get("gust"):
        wind += f" G{o['gust']}"
    tiles = [("FEELS LIKE", f"{o.get('feels_like')}°"), ("DEWPOINT", f"{o.get('dewpoint')}°"),
             ("HUMIDITY", f"{o.get('humidity')}%"), ("WIND", wind),
             ("PRESSURE", f"{o.get('pressure')}\""), ("VISIBILITY", f"{o.get('visibility')} mi")]
    tw, th, gx, gy = 510, 250, 30, 25
    for i, (label, val) in enumerate(tiles):
        x = 800 + (i % 2) * (tw + gx)
        y = 205 + (i // 2) * (th + gy)
        cv.accent_row(x, y, tw, th)
        cv.text(x + 40, y + 70, label, 30, "bold", C["muted"], anchor="ls")
        cv.text(x + 40, y + 180, val.replace("None", "--"), 72, "bold", anchor="ls", maxw=tw - 70)
    cv.footer(pkg)
    return cv


# ---------------------------------------------------------------- ALERTS
ALERT_COLORS = {"warning": (230, 30, 40), "watch": (255, 150, 0), "advisory": (255, 214, 0),
                "statement": (80, 160, 255)}


def alerts(pkg, cfg):
    al = pkg.get("alerts") or []
    if not al:
        return None
    cv = Canvas(cfg)
    cv.header("WEATHER ALERTS", f"IN EFFECT FOR THE {pkg['location']['area']}")
    top, gap = 210, 22
    M, Wd = cv.M, cv.W - 2 * cv.M
    nmax = 4 if not cv.tall else (7 if cv.fmt == "vertical" else 5)
    shown = al[:nmax]
    avail = cv.bottom - top
    rh = min(200, (avail - gap * (len(shown) - 1)) / len(shown))
    for i, a in enumerate(shown):
        y = top + i * (rh + gap)
        kind = next((k for k in ALERT_COLORS if k in a["event"].lower()), "statement")
        bar = tuple(int(a["color"][i:i + 2], 16) for i in (1, 3, 5)) if a.get("color") else ALERT_COLORS[kind]
        cv.accent_row(M, y, Wd, rh, bar=bar)
        cv.rect(M, y, 16, rh, bar)
        cv.text(M + 40, y + rh * 0.38, a["event"].upper(), 50 if not cv.tall else 42, "bold", anchor="lm", maxw=Wd - 70)
        cv.text(M + 40, y + rh * 0.72, a["ends_label"].upper(), 30 if not cv.tall else 26, "medium", C["muted"], anchor="lm")
        if a.get("headline") and rh >= 170:
            cv.text(M + 40, y + rh * 0.9, a["headline"], 22 if not cv.tall else 19, "regular", C["muted"], anchor="lm",
                    maxw=Wd - 70)
    cv.footer(pkg, show_location=False, source="SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "National Weather Service")
    return cv


from .alertmap import alert_maps  # noqa: E402
from .outlookmap import outlook_graphics  # noqa: E402
from .ndfdmap import ndfd_maps  # noqa: E402
from .wintermap import winter_graphics  # noqa: E402
from .cpcmap import cpc_graphics  # noqa: E402
from .rivers import river_graphics  # noqa: E402
from .tidalmap import tidal_graphics  # noqa: E402
from .holidays import holiday_countdown  # noqa: E402
from .drought import drought_graphic  # noqa: E402
from .ffg import ffg_graphics  # noqa: E402
from .reports import report_graphics  # noqa: E402
from .tropicalgfx import tropical_graphics  # noqa: E402
from . import extras as _extras  # noqa: E402

GRAPHICS = {
    "daily": daily, "what_to_know": what_to_know, "7day": seven_day, "hourly": hourly,
    "feels_like": feels_like, "wind_chill": wind_chill, "dewpoints": dewpoints, "rain_totals": rain_totals,
    "wind": wind, "current": current, "alerts": alerts, "alert_maps": alert_maps, "outlooks": outlook_graphics,
    "ndfd_maps": ndfd_maps, "winter_maps": winter_graphics, "cpc_hazards": cpc_graphics, "river_flooding": river_graphics, "tidal_flood_map": tidal_graphics, "holiday_countdown": holiday_countdown, "drought": drought_graphic, "ffg": ffg_graphics, "reports": report_graphics, "tropical_pack": tropical_graphics,
    **_extras.GRAPHICS,
}
