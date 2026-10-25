"""Holiday forecasts: themed graphics for the holidays coming up in the next week.

  holiday is 0-3 days away  -> hourly forecast for the day (every 2 h; every 3 h when two panels share the graphic)
  holiday is 4-6 days away  -> day-summary forecast (icon, high / low, rain chance, gusts, the written forecast)
  holidays with an eve (Christmas Eve + Christmas, New Year's Eve + New Year's Day) -> ONE graphic, eve and day side by side

Holiday dates come from holidays.py (holidays_off / holidays_extra apply).  Config: holiday_forecast_max (2 graphics),
holiday_forecast_days (6 = how far ahead to look; the forecast package only holds 7 days).
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image

from . import holidays
from .icons import draw_icon
from .theme import C, Canvas, z

PAIRS = {"Christmas Eve": "Christmas", "Christmas": "Christmas", "New Year's Eve": "New Year's", "New Year's Day": "New Year's"}
THEMES = {  # group -> (accent, accent 2, decoration emoji)
    "Christmas": ((222, 72, 72), (70, 170, 105), "2744"),
    "New Year's": ((245, 200, 90), (150, 165, 235), "1f386"),
    "Halloween": ((250, 140, 40), (150, 90, 210), "1f383"),
    "Thanksgiving": ((226, 132, 50), (170, 108, 62), "1f342"),
    "Independence Day": ((225, 70, 70), (90, 140, 235), "1f386"),
    "Valentine's Day": ((240, 100, 150), (222, 62, 92), "2764"),
    "St. Patrick's Day": ((70, 185, 100), (240, 200, 60), "2618"),
    "Easter": ((190, 150, 230), (250, 200, 120), "1f337"),
    "Mother's Day": ((240, 130, 170), (250, 190, 210), "1f490"),
    "Father's Day": ((90, 150, 230), (130, 190, 250), "1f454"),
}
PATRIOTIC = ((225, 70, 80), (90, 140, 235), "1f1fa-1f1f8")
DEFAULT = ((250, 205, 90), (120, 170, 235), "1f4c5")
for _n in ("Memorial Day", "Veterans Day", "Presidents' Day", "Labor Day", "Juneteenth", "Martin Luther King Jr. Day"):
    THEMES[_n] = PATRIOTIC


def _alpha_emoji(cv, code, cx, cy, size, alpha=255):
    p = holidays.ICON_DIR / f"{code}.png"
    if not p.exists():
        p = holidays.ICON_DIR / "1f4c5.png"
    im = Image.open(p).convert("RGBA").resize((int(z(size)), int(z(size))), Image.LANCZOS)
    if alpha < 255:
        im.putalpha(im.getchannel("A").point(lambda v: v * alpha // 255))
    cv.img.paste(im, (int(z(cx - size / 2)), int(z(cy - size / 2))), im)
    from PIL import ImageDraw
    cv.d = ImageDraw.Draw(cv.img, "RGBA")


def _until(n):
    return "TODAY" if n == 0 else "TOMORROW" if n == 1 else f"IN {n} DAYS"


def _hour_cols(hours, tz, d, step):
    """Hourly rows of local date d at 6 AM, 6+step, ... up to 10 PM."""
    by = {}
    for h in hours:
        t = datetime.fromisoformat(h["time"]).astimezone(tz)
        if t.date() == d:
            by[t.hour] = (t, h)
    return [by[hr] for hr in range(6, 23, step) if hr in by]


def _hour_note(cols):
    temps = [h["temp"] for _, h in cols]
    hi, lo = max(cols, key=lambda c: c[1]["temp"]), min(cols, key=lambda c: c[1]["temp"])
    pk = max(cols, key=lambda c: c[1]["pop"] or 0)
    fmt = lambda t: t.strftime("%I %p").lstrip("0")
    rain = pk[1]["pop"] or 0
    msg = f"Temperatures run from {lo[1]['temp']}° at {fmt(lo[0])} to {hi[1]['temp']}° at {fmt(hi[0])}. "
    if rain >= 50:
        msg += f"Rain is likely around {fmt(pk[0])}."
    elif rain >= 30:
        msg += f"A passing shower is possible around {fmt(pk[0])}."
    else:
        msg += "Staying dry."
    return msg


def _panel(cv, box, d, name, greet, n_days, mode, hours, day, tz, th, tint):
    x, y, w, h = box
    a, b, deco = th
    cv.rect(x, y, w, h, (*tint, 30), r=20)
    cv.rect(x, y, w, h, C["panel"], r=20)
    cv.rect(x, y, w, h, (*tint, 34), r=20)
    cv.d.rounded_rectangle([z(x), z(y), z(x + w), z(y + h)], radius=z(20), outline=(*tint, 190), width=z(3))
    _alpha_emoji(cv, deco, x + w - 130, y + h - 130, 230, 34)  # faint themed decoration
    _alpha_emoji(cv, holidays_icon(name), x + 74, y + 74, 96)
    cv.text(x + 140, y + 26, name.upper(), 44 if w > 1200 else 38, "bold", anchor="lt", maxw=w - 170)
    cv.text(x + 142, y + 80, f"{d.strftime('%A, %B').upper()} {d.day}  ·  {_until(n_days)}", 21, "bold", tint, anchor="lt", maxw=w - 170)
    cv.text(x + 142, y + 110, greet.upper(), 17, "bold", C["muted"], anchor="lt", maxw=w - 170)
    by = y + 160
    if mode == "hourly":
        step = 2 if w > 1200 else 3
        cols = _hour_cols(hours, tz, d, step)
        n = len(cols)
        cw = (w - 48) / n
        for i, (t, hh) in enumerate(cols):
            cx = x + 24 + cw * (i + 0.5)
            if i:
                cv.line([(cx - cw / 2, by + 6), (cx - cw / 2, by + 430)], (255, 255, 255, 22), 1.2)
            cv.text(cx, by + 8, t.strftime("%I %p").lstrip("0"), 24 if cw > 120 else 22, "bold", anchor="mt")
            draw_icon(cv, hh.get("icon") or "partly", cx, by + 120, min(110, cw * 0.78), night=not (7 <= t.hour < 19))
            cv.text(cx, by + 200, f"{hh['temp']}°", 50 if cw > 120 else 44, "bold", anchor="mt")
            pop = hh.get("pop") or 0
            cv.rect(cx - 44, by + 282, 88, 40, (60, 130, 230, 90 if pop >= 30 else 30), r=10)
            cv.text(cx, by + 302, f"{pop}%", 22, "bold", (170, 210, 255) if pop >= 30 else C["muted"], anchor="mm")
            cv.paragraph(cx, by + 338, (hh.get("cond") or "").upper(), 14, "bold", cw - 14, max_lines=2, lh=1.15, fill=C["muted"], anchor="ma")
        if cols:
            cv.paragraph(x + 28, by + 420, _hour_note(cols), 28 if w > 1200 else 26, "bold", w - 56, max_lines=4, lh=1.3)
    else:
        draw_icon(cv, day["icon"], x + w * 0.27, by + 150, 230)
        cv.text(x + w * 0.62, by + 40, f"{day['high']}°", 110, "bold", anchor="lt")
        cv.text(x + w * 0.62, by + 160, f"LOW {day['low']}°", 36, "bold", C["muted"], anchor="lt")
        cv.text(x + w / 2, by + 262, (day.get("cond") or "").upper(), 30, "bold", tint, anchor="mt", maxw=w - 56)
        chips = [("RAIN CHANCE", f"{day.get('pop') or 0}%"), ("PEAK GUSTS", f"{day['max_gust']} MPH" if day.get("max_gust") else "--")]
        cwd = (w - 56 - 16) / 2
        for i, (lab, val) in enumerate(chips):
            cx0 = x + 28 + i * (cwd + 16)
            cv.rect(cx0, by + 316, cwd, 96, (13, 21, 38, 200), r=14)
            cv.text(cx0 + 20, by + 328, lab, 16, "bold", C["muted"], anchor="lt")
            cv.text(cx0 + 20, by + 356, val, 36, "bold", anchor="lt", maxw=cwd - 30)
        cv.paragraph(x + 28, by + 436, day.get("text") or day.get("headline") or "", 30, "regular", w - 56, max_lines=4, lh=1.3)


def holidays_icon(name):
    for _d, nm, icon, _g in holidays.holidays_for(2026):
        if nm == name:
            return icon
    return "1f4c5"


def holiday_forecast_graphics(pkg, cfg):
    tz = ZoneInfo(cfg["timezone"])
    today = datetime.fromisoformat(pkg["issued"]).astimezone(tz).date()
    days = {d["date"]: d for d in pkg.get("days") or []}
    hours = pkg.get("hourly_ext") or []
    reach = cfg.get("holiday_forecast_days", 6)
    comming = [h for h in holidays.upcoming(today, cfg, 30) if (h[0] - today).days <= reach]
    groups = {}
    for h in comming:
        groups.setdefault(PAIRS.get(h[1], h[1]), []).append(h)
    out = []
    for key, hs in sorted(groups.items(), key=lambda kv: kv[1][0][0]):
        panels = []
        for d, name, icon, greet in sorted(hs):
            n = (d - today).days
            day = days.get(d.isoformat())
            mode = "hourly" if n <= 3 and len(_hour_cols(hours, tz, d, 3)) >= 3 else "day"
            if mode == "day" and not day:
                continue
            panels.append((d, name, greet, n, mode, day))
        if not panels:
            continue
        th = THEMES.get(key, DEFAULT)
        cv = Canvas(cfg)
        title = f"{key} Forecast" if len(panels) == 1 or key in ("Christmas", "New Year's") else f"{panels[0][1]} Forecast"
        first = panels[0]
        sub = (f"{first[0].strftime('%A, %B').upper()} {first[0].day}" if len(panels) == 1 else
               f"{panels[0][1].upper()} & {panels[1][1].upper()}") + "  ·  " + ("HOUR BY HOUR" if all(p[4] == "hourly" for p in panels) else "DAY BY DAY" if all(p[4] == "day" for p in panels) else "FORECAST")
        cv.header(title, sub, rule_color=(*th[0], 255))
        top, bot = cv.top, cv.bottom - 5
        if len(panels) == 1:
            boxes = [(cv.M, top, cv.W - 2 * cv.M, bot - top)]
        else:
            gap = 24
            pw = (cv.W - 2 * cv.M - gap) / 2
            boxes = [(cv.M, top, pw, bot - top), (cv.M + pw + gap, top, pw, bot - top)]
        for i, ((d, name, greet, n, mode, day), box) in enumerate(zip(panels, boxes)):
            _panel(cv, box, d, name, greet, n, mode, hours, day, tz, th, th[0] if i == 0 else th[1])
        cv.footer(pkg, source=("SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NWS NDFD"))
        slug = key.lower().replace("'", "").replace(".", "").replace(" ", "_")
        out.append((f"{slug}_forecast", cv))
        if len(out) >= cfg.get("holiday_forecast_max", 2):
            break
    return out or None
