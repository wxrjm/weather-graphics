"""7-day temperature vs normal: a centre line (normal) with a bar above (warmer) or below (cooler) each day, labelled +/- degrees.

The bar is the day's average temperature ((high + low) / 2) against the normal average for that date (ORF approximate 1991-2020
normals from summarize.normal_temps).  Config: temp_normal_metric "mean" (default) | "high" | "low".
"""
from datetime import date as _date

from .summarize import normal_temps
from .theme import C, Canvas

WARM, COOL, NEAR = (255, 150, 50), (88, 170, 255), (150, 165, 190)


def _s(v):
    return f"+{v}°" if v > 0 else f"-{abs(v)}°" if v < 0 else "0°"


def temp_vs_normal_graphic(pkg, cfg):
    days = [d for d in (pkg.get("days") or [])[:7] if d.get("high") is not None and d.get("low") is not None]
    if len(days) < 3:
        return None
    metric = cfg.get("temp_normal_metric", "mean")
    rows = []
    for d in days:
        nh, nl = normal_temps(_date.fromisoformat(d["date"]))
        nh, nl = round(nh), round(nl)
        val, norm = {"high": (d["high"], nh), "low": (d["low"], nl)}.get(metric, ((d["high"] + d["low"]) / 2, (nh + nl) / 2))
        rows.append({"d": d, "dep": round(val - norm), "norm": norm, "val": val, "nh": nh, "nl": nl})
    avg = sum(r["dep"] for r in rows) / len(rows)
    word = {"high": "HIGH TEMPERATURES", "low": "LOW TEMPERATURES"}.get(metric, "AVERAGE TEMPERATURE")
    cv = Canvas(cfg)
    cv.header("ABOVE OR BELOW AVERAGE", f"NEXT {len(rows)} DAYS  ·  {word} VS NORMAL  ·  {pkg['location']['area'].upper()}")
    # chart
    cx, cy, cw, ch = cv.M, 205, cv.W - 2 * cv.M, cv.H - 205 - 100
    cv.rect(cx, cy, cw, ch, C["panel"], r=16)
    lim = max(6, 2 * -(-max(abs(r["dep"]) for r in rows) // 2) + 2)
    top, bot = cy + 80, cy + ch - 140
    zero = (top + bot) / 2
    sc = (bot - top) / 2 / lim
    step = 2 if lim <= 12 else 5
    g = -(lim // step) * step
    while g <= lim:
        yy = zero - g * sc
        if g:
            cv.line([(cx + 70, yy), (cx + cw - 20, yy)], (255, 255, 255, 30), 1)
            cv.text(cx + 58, yy, f"{g:+d}", 16, "bold", C["muted"], anchor="rm")
        g += step
    cv.text(cx + 24, cy + 18, "DEGREES ABOVE (+) OR BELOW (-) NORMAL", 18, "bold", C["muted"], anchor="lt")
    cv.text(cx + cw - 24, cy + 18, "ORANGE = WARMER   ·   BLUE = COOLER", 16, "bold", C["muted"], anchor="rt")
    cv.text(cx + 58, zero, "NORMAL", 14, "bold", C["text"], anchor="rm")
    n = len(rows)
    x0, x1 = cx + 80, cx + cw - 24
    slot = (x1 - x0) / n
    bw = min(120, slot * 0.58)
    for i, r in enumerate(rows):
        mx = x0 + slot * (i + 0.5)
        col = WARM if r["dep"] > 0 else COOL if r["dep"] < 0 else NEAR
        h = r["dep"] * sc
        if r["dep"]:
            cv.rect(mx - bw / 2, min(zero, zero - h), bw, abs(h), (*col, 255), r=8)
        up = r["dep"] >= 0
        cv.text(mx, (zero - h - 10) if up else (zero - h + 10), _s(r["dep"]), 32, "bold", anchor="mb" if up else "mt")
        cv.text(mx, bot + 22, r["d"]["dow"], 28, "bold", anchor="mt")
        cv.text(mx, bot + 58, f"{r['d']['high']}° / {r['d']['low']}°", 20, "bold", C["muted"], anchor="mt")
        cv.text(mx, bot + 84, f"NORMAL {r['nh']}° / {r['nl']}°", 15, "medium", C["muted"], anchor="mt")
    cv.line([(cx + 70, zero), (cx + cw - 20, zero)], (255, 255, 255, 230), 3)  # the normal line
    cv.footer(pkg, source=("SAMPLE DATA" if "SAMPLE" in pkg.get("source", "") else "NWS NDFD · NORFOLK 1991-2020 NORMALS (APPROX.)"))
    return cv
