"""Countdown to the holidays: the next holiday in a big spotlight (emoji, days to go, date), plus the
next few after it.

Holiday dates are computed (fixed dates, "nth weekday" rules, Easter), so nothing is downloaded.
Emoji art: Twemoji (CC-BY 4.0), pre-rendered PNGs in wxgfx/data/holiday_icons/.
Config: holiday_count, holidays_off (names to skip), holidays_extra ([{name, date: "MM-DD" or
"YYYY-MM-DD", icon: twemoji code}]) for birthdays, Hanukkah, local events, etc.
"""
from datetime import date, datetime, timedelta
from pathlib import Path

from PIL import Image

from .icons import draw_icon
from .theme import C, Canvas, z

ICON_DIR = Path(__file__).parent / "data" / "holiday_icons"


def _nth(year, month, weekday, n):
    """n-th weekday (Mon=0) of a month; n=-1 = last."""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    return date(y, month, (h + l_ - 7 * m + 114) % 31 + 1)


def holidays_for(year):
    """(date, name, icon, greeting)"""
    return [
        (date(year, 1, 1), "New Year's Day", "1f38a", "Happy New Year!"),
        (_nth(year, 1, 0, 3), "Martin Luther King Jr. Day", "1f54a", "Honoring Dr. King today"),
        (date(year, 2, 14), "Valentine's Day", "2764", "Happy Valentine's Day!"),
        (_nth(year, 2, 0, 3), "Presidents' Day", "1f1fa-1f1f8", "Happy Presidents' Day!"),
        (date(year, 3, 17), "St. Patrick's Day", "2618", "Happy St. Patrick's Day!"),
        (easter(year), "Easter", "1f430", "Happy Easter!"),
        (_nth(year, 5, 6, 2), "Mother's Day", "1f490", "Happy Mother's Day!"),
        (_nth(year, 5, 0, -1), "Memorial Day", "1f1fa-1f1f8", "Remembering those who served"),
        (_nth(year, 6, 6, 3), "Father's Day", "1f454", "Happy Father's Day!"),
        (date(year, 6, 19), "Juneteenth", "1f389", "Happy Juneteenth!"),
        (date(year, 7, 4), "Independence Day", "1f386", "Happy Fourth of July!"),
        (_nth(year, 9, 0, 1), "Labor Day", "1f6e0", "Happy Labor Day!"),
        (date(year, 10, 31), "Halloween", "1f383", "Happy Halloween!"),
        (date(year, 11, 11), "Veterans Day", "1f396", "Thank you, veterans"),
        (_nth(year, 11, 3, 4), "Thanksgiving", "1f983", "Happy Thanksgiving!"),
        (date(year, 12, 24), "Christmas Eve", "1f385", "Merry Christmas Eve!"),
        (date(year, 12, 25), "Christmas", "1f384", "Merry Christmas!"),
        (date(year, 12, 31), "New Year's Eve", "1f942", "Happy New Year's Eve!"),
    ]


def upcoming(today, cfg, n=None):
    n = n or cfg.get("holiday_count", 6)
    off = {s.lower() for s in cfg.get("holidays_off") or []}
    out = []
    for y in (today.year, today.year + 1):
        out += [h for h in holidays_for(y) if h[1].lower() not in off]
        for x in cfg.get("holidays_extra") or []:
            try:
                ds = x["date"]
                d = date.fromisoformat(ds) if len(ds) == 10 else date(y, int(ds[:2]), int(ds[3:5]))
            except (KeyError, ValueError):
                continue
            if len(ds) == 10 and d.year != y:
                continue
            out.append((d, x["name"], x.get("icon", "1f4c5"), x.get("greeting", f"Happy {x['name']}!")))
    out = sorted({(d, nm): (d, nm, ic, g) for d, nm, ic, g in out if d >= today}.values())
    return out[:n]


def _emoji(cv, code, cx, cy, size):
    p = ICON_DIR / f"{code}.png"
    if not p.exists():
        p = ICON_DIR / "1f4c5.png"
    im = Image.open(p).convert("RGBA").resize((int(z(size)), int(z(size))), Image.LANCZOS)
    cv.img.paste(im, (int(z(cx - size / 2)), int(z(cy - size / 2))), im)


def _until(days):
    return "TODAY!" if days == 0 else "TOMORROW" if days == 1 else f"{days} DAYS"


def holiday_countdown(pkg, cfg):
    now = datetime.fromisoformat(pkg["issued"])
    today = now.date()
    hs = upcoming(today, cfg)
    if not hs:
        return None
    cv = Canvas(cfg)
    cv.header("HOLIDAY COUNTDOWN", f"{pkg['location'].get('area', 'Hampton Roads Area').upper()}  ·  DAYS TO GO")
    x, y, w, h = cv.M, cv.top, cv.W - 2 * cv.M, cv.bottom - cv.top
    first, rest = hs[0], hs[1:]
    if not cv.tall:
        hero, lst = (x, y, w * 0.44, h), (x + w * 0.44 + 22, y, w * 0.56 - 22, h)
    else:
        hh = h * (0.5 if cv.fmt == "vertical" else 0.36)
        hero, lst = (x, y, w, hh), (x, y + hh + 20, w, h - hh - 20)
        if cv.fmt == "post":
            rest = rest[:4]
    # ---- spotlight
    bx, by, bw, bh = hero
    cv.rect(bx, by, bw, bh, C["panel"], r=18)
    d0, name, icon, greet = first
    days = (d0 - today).days
    f = None  # no forecast on the holiday countdown
    if not cv.tall or cv.fmt == "vertical":
        es = min(230, bh * 0.3)
        _emoji(cv, icon, bx + bw / 2, by + 40 + es / 2, es)
        ty = by + 60 + es
        if days == 0:
            cv.text(bx + bw / 2, ty + 110, "TODAY!", 120, "bold", (250, 205, 90), anchor="ms")
            cv.text(bx + bw / 2, ty + 170, greet.upper(), 34, "bold", anchor="ms", maxw=bw - 50)
        else:
            cv.text(bx + bw / 2, ty + 150, str(days) if days > 1 else "1", 170, "bold", (250, 205, 90), anchor="ms")
            cv.text(bx + bw / 2, ty + 205, ("DAY" if days == 1 else "DAYS") + " UNTIL", 28, "bold", C["muted"], anchor="ms")
            cv.text(bx + bw / 2, ty + 255, name.upper(), 40, "bold", anchor="ms", maxw=bw - 50)
        cv.text(bx + bw / 2, ty + (300 if days else 215), f"{d0.strftime('%A, %B').upper()} {d0.day}", 24, "bold",
                C["muted"], anchor="ms")
        if f:
            fy = by + bh - 70
            cv.rect(bx + 30, fy - 34, bw - 60, 76, (255, 255, 255, 14), r=14)
            draw_icon(cv, f["icon"], bx + 80, fy + 4, 58)
            cv.text(bx + 126, fy - 6, f"{f['high']}° / {f['low']}°", 30, "bold", anchor="lm")
            cv.text(bx + 126, fy + 24, (f.get("cond") or "").upper(), 18, "bold", C["muted"], anchor="lm", maxw=bw - 190)
    else:  # post (4:5): emoji left, countdown stacked on the right
        es = min(220, bh * 0.62)
        _emoji(cv, icon, bx + 40 + es / 2, by + bh / 2, es)
        tx, tw = bx + 80 + es, bw - es - 110
        top = by + bh / 2 - 150
        if days == 0:
            cv.text(tx, top + 100, "TODAY!", 100, "bold", (250, 205, 90), anchor="ls")
            cv.text(tx, top + 160, greet.upper(), 36, "bold", anchor="ls", maxw=tw)
        else:
            cv.text(tx, top + 110, str(days), 130, "bold", (250, 205, 90), anchor="ls")
            cv.text(tx + cv.width(str(days), 130, "bold") + 18, top + 110, ("DAY" if days == 1 else "DAYS") + " UNTIL", 26,
                    "bold", C["muted"], anchor="ls")
            cv.text(tx, top + 175, name.upper(), 44, "bold", anchor="ls", maxw=tw)
        cv.text(tx, top + 220, f"{d0.strftime('%A, %B').upper()} {d0.day}", 24, "bold", C["muted"], anchor="ls", maxw=tw)
        if f:
            draw_icon(cv, f["icon"], tx + 24, top + 272, 46)
            cv.text(tx + 58, top + 272, f"{f['high']}° / {f['low']}°  ·  {(f.get('cond') or '').upper()}", 22, "bold",
                    anchor="lm", maxw=tw - 60)
    # ---- coming up
    lx, ly, lw, lh = lst
    cv.text(lx + 4, ly + 4, "COMING UP", 22, "bold", C["muted"], anchor="lt")
    ly += 40
    lh -= 40
    n = max(1, len(rest))
    gap = 12
    rh = min(150, (lh - gap * (n - 1)) / n)
    for i, (d, nm, ic, _) in enumerate(rest):
        ry = ly + i * (rh + gap)
        cv.rect(lx, ry, lw, rh, C["panel"], r=14)
        es = min(rh * 0.66, 84)
        _emoji(cv, ic, lx + 24 + es / 2, ry + rh / 2, es)
        tx = lx + 48 + es
        cv.text(tx, ry + rh / 2 - 4, nm.upper(), min(30, rh * 0.26), "bold", anchor="ls", maxw=lw - (tx - lx) - 200)
        cv.text(tx, ry + rh / 2 + min(30, rh * 0.26), f"{d.strftime('%a, %b').upper()} {d.day}", min(20, rh * 0.17), "bold",
                C["muted"], anchor="ls")
        dd = (d - today).days
        val = _until(dd)
        cv.text(lx + lw - 26, ry + rh / 2 + min(14, rh * 0.1), val, min(40, rh * 0.32), "bold", (250, 205, 90), anchor="rs")
    cv.footer(pkg, show_source=False)
    return cv
