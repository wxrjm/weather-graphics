"""Snow probability "rulers": three snow piles on a platform with a ruler in each, big chance-of-at-least percentages.

Two sources:
  * overrides.json  "snow_probs": {"area": "Hampton Roads", "period": "Friday into Saturday (10/23-10/24)",
        "items": [{"label": "At least a trace", "pct": 90, "inches": 0.1}, {"label": "At least 2\"", "pct": 70, "inches": 2},
                  {"label": "4\" or more", "pct": 30, "inches": 4}]}      <- exact numbers you type in (e.g. from NBM / your forecast)
  * automatic: WPC probabilistic winter precipitation (chance of at least 4 / 8 / 12 inches) at the forecast point, shown as
    WPC's probability bands (10-39% / 40-69% / 70%+).  Only made when some chance exists (winter_always: true forces it).
"""
import random

from . import outlooks, wintermap
from .theme import C, Canvas, z

WOOD, WOOD_DARK, WOOD_LIGHT, INK = (224, 178, 106), (176, 128, 66), (240, 204, 146), (86, 54, 22)
BANDS = {0: "<10%", 1: "10-39%", 2: "40-69%", 3: "70%+"}


def _snowfall(cv, n=140):
    rnd = random.Random(7)
    for _ in range(n):
        x, y, r = rnd.uniform(0, cv.W), rnd.uniform(190, cv.H - 60), rnd.choice((2, 2, 3, 3, 4, 6))
        a = rnd.randint(40, 120)
        cv.d.ellipse([z(x - r), z(y - r), z(x + r), z(y + r)], fill=(235, 243, 255, a))


def _platform(cv, cx, y, wd):
    d = cv.d
    d.ellipse([z(cx - wd / 2 - 24), z(y - 22), z(cx + wd / 2 + 24), z(y + 62)], fill=(150, 162, 182, 255))  # rim
    d.ellipse([z(cx - wd / 2 - 14), z(y - 18), z(cx + wd / 2 + 14), z(y + 52)], fill=(52, 62, 84, 255))
    d.ellipse([z(cx - wd / 2 + 10), z(y - 12), z(cx + wd / 2 - 10), z(y + 30)], fill=(70, 82, 106, 255))


def _ruler(cv, cx, base, ppi, top_in=12):
    w = 86
    x0, y0 = cx - w / 2, base - top_in * ppi - 16
    cv.rect(x0 - 3, y0 - 3, w + 6, base - y0 + 3, WOOD_DARK, r=6)
    cv.rect(x0, y0, w, base - y0, WOOD, r=5)
    cv.rect(x0, y0, 12, base - y0, WOOD_LIGHT, r=5)  # lit edge
    for n in range(1, top_in + 1):
        y = base - n * ppi
        cv.line([(x0 + w - 24, y), (x0 + w, y)], INK, 2.2)
        if n < top_in:
            cv.line([(x0 + w - 12, y + ppi / 2), (x0 + w, y + ppi / 2)], INK, 1.5)
        cv.text(x0 + w - 32, y, str(n), 22, "bold", INK, anchor="rm")


def _mound(cv, cx, base, ppi, inches, wd):
    h = max(14, inches * ppi)
    d = cv.d
    d.ellipse([z(cx - wd / 2), z(base - h), z(cx + wd / 2), z(base + h * 0.45 + 10)], fill=(196, 212, 232, 255))  # shaded body
    d.ellipse([z(cx - wd / 2 + 6), z(base - h), z(cx + wd / 2 - 18), z(base + h * 0.3 + 8)], fill=(238, 245, 252, 255))
    d.ellipse([z(cx - wd * 0.28), z(base - h + 3), z(cx + wd * 0.1), z(base - h * 0.35)], fill=(252, 254, 255, 255))  # highlight


def _items(pkg, cfg):
    man = pkg.get("snow_probs")
    if man and man.get("items"):
        items = [(str(i.get("label", "")).upper(), str(i["pct"]).rstrip("%") + "%", float(i.get("inches", 1))) for i in man["items"][:3]]
        return man.get("area") or pkg["location"]["area"], man.get("period") or "", items
    data = pkg.get("_winter") or {}
    loc = cfg["location"]
    for day, by_thr in sorted((data.get("snow") or {}).items(), key=lambda kv: int(kv[0])):
        lv = {t: wintermap._at(feats, loc["lon"], loc["lat"]) for t, feats in by_thr.items()}
        if any(lv.values()) or cfg.get("winter_always"):
            feats = next((f for f in by_thr.values() if f), [])
            period = wintermap._period_label(str(day), feats, pkg, cfg) if feats else f"DAY {day}"
            items = [(f'{t}" OR MORE', BANDS[lv[t]], float(t)) for t in sorted(lv, key=float)[:3]]
            return pkg["location"]["area"], period, items
    return None


def snow_probability_graphic(pkg, cfg):
    got = _items(pkg, cfg)
    if not got:
        print("  - snow_probability: no snow chances at the forecast point, skipped")
        return None
    area, period, items = got
    cv = Canvas(cfg)
    cv.header("SNOW PROBABILITY", ("CHANCE OF AT LEAST  ·  " + period.upper()) if period else "CHANCE OF AT LEAST")
    _snowfall(cv)
    n = len(items)
    colw = (cv.W - 2 * cv.M) / n
    base, ppi = 640, 35
    for i, (label, pct, inches) in enumerate(items):
        cx = cv.M + colw * (i + 0.5)
        _platform(cv, cx, base, 300)
        _ruler(cv, cx, base, ppi)
        _mound(cv, cx, base, ppi, inches, 300)
        cv.text(cx, base + 78, pct, 132 if len(pct) < 5 else 108, "bold", (255, 255, 255), anchor="mm", stroke=5, stroke_fill=(13, 21, 38, 255), maxw=colw - 40)
        cv.rect(cx - 190, base + 148, 380, 56, (70, 86, 116, 240), r=12)
        cv.text(cx, base + 176, label, 27, "bold", anchor="mm", maxw=350)
    cv.text(cv.W / 2, 965, area.upper(), 90, "bold", (255, 255, 255), anchor="mm", stroke=4, stroke_fill=(13, 21, 38, 255), maxw=cv.W - 200)
    src = "SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else ("YOUR FORECAST" if pkg.get("snow_probs") else "NWS WPC PROBABILISTIC WINTER PRECIPITATION")
    cv.footer(pkg, source=src)
    return cv
