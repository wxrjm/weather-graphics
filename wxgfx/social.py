"""Minimal-text, big-type layouts for the social sizes (square 1080x1080, post 1080x1350, vertical 1080x1920).

A phone screen shows these at about a third of the design size, so each card carries a handful of huge elements:
one icon, a giant number, a short word or two. The detailed versions stay for the wide (TV / OBS) size.
Map graphics use bigtext.py (giant headline + callouts on the map); these are the non-map forecast cards.
Config: "social_minimal": false switches all of this off.
"""
import re

from .icons import draw_icon
from .theme import C

NEUTRAL = (70, 86, 112)
RATE = {"GOOD": ((60, 200, 120), "SMOOTH"), "OK": ((250, 205, 60), "HEADS UP"), "SLOW": ((250, 140, 50), "EXTRA TIME")}


def _area(cv):
    return cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top


def _ink(col):
    return (20, 28, 46) if 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2] > 150 else (255, 255, 255)


def _pill(cv, cx, cy, text, col, size):
    w = cv.width(text, size, "bold") + size * 1.1
    h = size * 1.7
    cv.rect(cx - w / 2, cy - h / 2, w, h, (*col, 255), r=h / 2)
    cv.text(cx, cy, text, size, "bold", _ink(col), anchor="mm")


def _temp_from(text):
    m = re.search(r"(\d{1,3})\s*[–-]\s*(\d{1,3})\s*°", text or "")
    if m:
        return f"{m.group(1)}–{m.group(2)}°"
    m = re.search(r"(\d{1,3})\s*°", text or "")
    return f"{m.group(1)}°" if m else ""


# ---------------------------------------------------------------- DAILY
def daily(cv, t, d, pkg):
    x, top, W, H = _area(cv)
    hero_h = H * {"vertical": 0.56, "post": 0.58}.get(cv.fmt, 0.6)
    cv.rect(x, top, W, hero_h, C["panel"], r=22)
    vert = cv.fmt == "vertical"
    ic = min(hero_h * 0.5, W * 0.3)
    if vert:  # icon on top, big numbers below
        draw_icon(cv, d["icon"], x + W / 2, top + hero_h * 0.2, min(hero_h * 0.3, 280))
        hs, hx, lx, ny = 270, x + W * 0.38, x + W * 0.8, top + hero_h * 0.56
    else:
        draw_icon(cv, d["icon"], x + W * 0.19, top + hero_h * 0.36, ic)
        hs, hx, lx, ny = min(hero_h * 0.4, 190), x + W * 0.55, x + W * 0.86, top + hero_h * 0.46
    cv.text(hx, ny, f"{d['high']}°", hs, "bold", anchor="ms")
    cv.text(hx, ny + 40, "HIGH", 32, "medium", C["muted"], anchor="ms")
    cv.text(lx, ny, f"{d['low']}°", hs * 0.5, "medium", C["muted"], anchor="ms")
    cv.text(lx, ny + 40, "LOW", 32, "medium", C["muted"], anchor="ms")
    cv.paragraph(x + W / 2, top + hero_h * 0.74, (t.get("headline") or d["headline"]).upper(), 58 if cv.fmt == "vertical" else 50,
                 "bold", W - 70, max_lines=2, anchor="ma", lh=1.1)
    rows = (t.get("timeline") or [])[:4]
    if rows:
        sy = top + hero_h + 20
        sh = H - hero_h - 20
        gap = 14
        cw = (W - gap * (len(rows) - 1)) / len(rows)
        for i, r in enumerate(rows):
            cx0 = x + i * (cw + gap)
            cv.rect(cx0, sy, cw, sh, C["panel"], r=18)
            night = r["label"] in ("EVENING", "OVERNIGHT")
            cv.text(cx0 + cw / 2, sy + sh * 0.17, r["label"], min(32, cw * 0.15), "bold", anchor="mm", maxw=cw - 16)
            if r.get("icon"):
                draw_icon(cv, r["icon"], cx0 + cw / 2, sy + sh * 0.52, min(sh * 0.4, cw * 0.62), night=night)
            tt = _temp_from(r.get("text"))
            if tt:
                cv.text(cx0 + cw / 2, sy + sh * 0.86, tt, min(48, cw * 0.24), "bold", anchor="mm", maxw=cw - 16)
    cv.footer(pkg)
    return cv


# ---------------------------------------------------------------- 7 DAY
def seven_day(cv, cols, pkg):
    x, top, W, H = _area(cv)
    n, gap = len(cols), 12
    rh = (H - gap * (n - 1)) / n
    big = min(86, rh * 0.62)
    for i, c in enumerate(cols):
        y = top + i * (rh + gap)
        cv.rect(x, y, W, rh, C["panel_hi"] if i == 0 else C["panel"], r=16)
        cv.rect(x, y, 10, rh, C["rule"], r=4)
        cy = y + rh / 2
        cv.text(x + 36, cy, c["label"], min(54, rh * 0.42), "bold", anchor="lm", maxw=W * 0.30)
        draw_icon(cv, c["icon"], x + W * 0.44, cy + 2, min(130, rh * 0.9), night=c["night"])
        cv.text(x + W * 0.64, cy + big * 0.05, f"{c['big']}°", big, "bold", anchor="mm")
        if c["small"] is not None:
            cv.text(x + W * 0.795, cy + big * 0.05, f"{c['small']}°", big * 0.64, "medium", C["muted"], anchor="mm")
        else:
            cv.text(x + W * 0.795, cy, "LOW", big * 0.4, "medium", C["muted"], anchor="mm")
        pop = c["pop"] or 0
        if pop >= 30:
            _pill(cv, x + W - 78, cy, f"{pop}%", C["rain"], min(36, rh * 0.28))
    cv.footer(pkg)
    return cv


# ---------------------------------------------------------------- NEXT 24 HOURS
def hourly(cv, hrs, pkg):
    x, top, W, H = _area(cv)
    vert = cv.fmt == "vertical"
    step = 3 if vert else 4
    picks = hrs[::step][:8 if vert else 6]
    cols = 2 if vert else 3
    rows = -(-len(picks) // cols)
    gap = 16
    cw, ch = (W - gap * (cols - 1)) / cols, (H - gap * (rows - 1)) / rows
    for i, h in enumerate(picks):
        cx0, cy0 = x + (i % cols) * (cw + gap), top + (i // cols) * (ch + gap)
        cv.rect(cx0, cy0, cw, ch, C["panel"], r=20)
        hr = int(h["time"][11:13])
        cv.text(cx0 + cw / 2, cy0 + ch * 0.13, h["label"], min(46, ch * 0.14), "bold", C["muted"], anchor="mm")
        draw_icon(cv, h["icon"], cx0 + cw / 2, cy0 + ch * 0.43, min(ch * 0.4, cw * 0.55), night=not (7 <= hr < 19))
        cv.text(cx0 + cw / 2, cy0 + ch * 0.74, f"{h['temp']}°", min(100, ch * 0.24), "bold", anchor="mm")
        pop = h.get("pop") or 0
        if pop >= 30:
            _pill(cv, cx0 + cw / 2, cy0 + ch * 0.9, f"{pop}% RAIN", C["rain"], min(30, ch * 0.07))
    cv.footer(pkg)
    return cv


# ---------------------------------------------------------------- CURRENT
def current(cv, o, tiles, pkg):
    x, top, W, H = _area(cv)
    vert = cv.fmt == "vertical"
    hero_h = H * (0.7 if vert else 0.66)
    cv.rect(x, top, W, hero_h, C["panel"], r=22)
    draw_icon(cv, o["icon"], x + W * 0.5 if vert else x + W * 0.25, top + hero_h * (0.2 if vert else 0.4),
              min(hero_h * 0.34, 260) if vert else min(hero_h * 0.5, 260), night=o.get("night", False))
    ts = min(hero_h * 0.4, 250)
    if vert:
        cv.text(x + W / 2, top + hero_h * 0.7, f"{o['temp']}°", ts, "bold", anchor="ms")
        cv.paragraph(x + W / 2, top + hero_h * 0.8, (o["cond"] or "").upper(), 56, "bold", W - 80, max_lines=2, anchor="ma", lh=1.1)
    else:
        cv.text(x + W * 0.7, top + hero_h * 0.55, f"{o['temp']}°", ts, "bold", anchor="ms")
        cv.paragraph(x + W / 2, top + hero_h * 0.72, (o["cond"] or "").upper(), 52, "bold", W - 80, max_lines=1, anchor="ma")
    want = [t for t in tiles if t[0] in ("FEELS LIKE", "WIND")]
    ty = top + hero_h + 20
    th = H - hero_h - 20
    gap = 18
    tw = (W - gap) / 2
    for i, (label, val) in enumerate(want):
        tx = x + i * (tw + gap)
        cv.accent_row(tx, ty, tw, th)
        cv.text(tx + 34, ty + th * 0.3, label, min(38, th * 0.16), "bold", C["muted"], anchor="ls")
        cv.text(tx + 34, ty + th * 0.74, val.replace("None", "--"), min(90, th * 0.4), "bold", anchor="ls", maxw=tw - 56)
    cv.footer(pkg)
    return cv


# ---------------------------------------------------------------- COMMUTE
def commute(cv, wins, pkg):
    x, top, W, H = _area(cv)
    n, gap = len(wins), 20
    bh = (H - gap * (n - 1)) / n
    for i, win in enumerate(wins):
        col, word = RATE.get(win["rating"], (NEUTRAL, ""))
        by = top + i * (bh + gap)
        cv.rect(x, by, W, bh, C["panel"], r=22)
        cv.rect(x, by, W, 12, (*col, 255), r=5)
        cv.text(x + 40, by + bh * 0.17, f"{win['day']} {win['label'].split()[0]}".upper(), min(60, bh * 0.15), "bold", anchor="lm",
                maxw=W * 0.58)
        _pill(cv, x + W - 40 - (cv.width(word, 30, "bold") + 33) / 2, by + bh * 0.17, word, col, 30)
        ic = min(bh * 0.46, W * 0.3)
        draw_icon(cv, win["icon"], x + 40 + ic / 2, by + bh * 0.6, ic)
        tt = f"{win['temp_min']}°" if win["temp_min"] == win["temp_max"] else f"{win['temp_min']}–{win['temp_max']}°"
        cv.text(x + 70 + ic, by + bh * 0.58, tt, min(110, bh * 0.28), "bold", anchor="lm", maxw=W - ic - 110)
        cv.text(x + 70 + ic, by + bh * 0.8, win["cond"].upper(), min(40, bh * 0.1), "bold", C["muted"], anchor="lm", maxw=W - ic - 110)
    cv.footer(pkg)
    return cv


# ---------------------------------------------------------------- WEEKEND
def weekend(cv, wk, pkg, tag_col):
    x, top, W, H = _area(cv)
    n, gap = len(wk), 20
    bh = (H - gap * (n - 1)) / n
    for i, d in enumerate(wk):
        by = top + i * (bh + gap)
        cv.rect(x, by, W, bh, C["panel"], r=22)
        cv.rect(x, by, W, 12, C["rule"], r=5)
        cv.text(x + 44, by + bh * 0.2, d["day"].upper(), min(80, bh * 0.2), "bold", anchor="lm", maxw=W * 0.5)
        ic = min(bh * 0.5, W * 0.3)
        draw_icon(cv, d["parts"][1]["icon"] if d.get("parts") and len(d["parts"]) > 1 else d["parts"][0]["icon"],
                  x + 44 + ic / 2, by + bh * 0.62, ic)
        hs = min(150, bh * 0.36)
        cv.text(x + W * 0.62, by + bh * 0.52, f"{d['high']}°", hs, "bold", anchor="mm")
        cv.text(x + W * 0.88, by + bh * 0.54, f"{d['low']}°", hs * 0.56, "medium", C["muted"], anchor="mm")
        cv.text(x + W * 0.62, by + bh * 0.8, d["cond"].upper(), min(40, bh * 0.09), "bold", C["muted"], anchor="mm", maxw=W * 0.5)
        if d.get("tags"):
            tag = d["tags"][0]
            _pill(cv, x + W - 40 - (cv.width(tag, 30, "bold") + 33) / 2, by + bh * 0.2, tag, tag_col.get(tag, NEUTRAL), 30)
    cv.footer(pkg)
    return cv
