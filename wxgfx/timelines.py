"""Three broadcast-style forecast graphics in the Ricky Matthews theme:
   precip_timeline    - smooth rain-chance curve with the precip type colored underneath (rain / snow / wintry mix / storms)
   today_vs_tomorrow  - big split-screen temperature comparison (today's high vs tomorrow morning's low)
   what_to_expect     - rain / storms / wintry mix / snow timing table across the next six time blocks
All of them read pkg["hourly_ext"] (hourly temp, rain chance, qpf and precip type) and return None when there's nothing to show.
"""
import math
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter

from .theme import C, Canvas, z

TYPES = {  # ptype -> (fill rgb, label)
    "rain": ((60, 165, 255), "RAIN"),
    "tstorm": ((253, 149, 0), "STORMS"),
    "snow": ((4, 233, 231), "SNOW"),
    "mix": ((222, 98, 224), "WINTRY MIX"),
    "ice": ((255, 110, 190), "FREEZING RAIN"),
}


def _rows(pkg, cfg):
    tz = ZoneInfo(cfg["timezone"])
    out = []
    for h in pkg.get("hourly_ext") or []:
        out.append({"t": datetime.fromisoformat(h["time"]).astimezone(tz), "temp": h.get("temp"), "pop": h.get("pop") or 0,
                    "q": h.get("qpf") or 0.0, "pt": h.get("ptype"), "cond": h.get("cond"), "icon": h.get("icon")})
    return out, tz


def _hr(t):
    return t.strftime("%I%p").lstrip("0")


def _wet(r):
    return r["pt"] and r["pop"] >= 30


# ------------------------------------------------------------------ PRECIPITATION TIMELINE
def precip_timeline(pkg, cfg):
    rows, tz = _rows(pkg, cfg)
    n = min(len(rows), cfg.get("precip_timeline_hours", 36))
    rows = rows[:n]
    if n < 12 or max(r["pop"] for r in rows) < 20:
        return None
    cv = Canvas(cfg)
    cv.header("PRECIPITATION TIMELINE", f"NEXT {n} HOURS  ·  {pkg['location']['area'].upper()}")
    M = cv.M
    px, py, pw, ph = M, cv.top, cv.W - 2 * M, cv.bottom - cv.top
    cv.rect(px, py, pw, ph, C["panel"], r=18)
    x0, x1 = px + 130, px + pw - 80
    y0, y1 = py + 60, py + ph - 130  # 100% line, baseline
    for p_ in (20, 40, 60, 80, 100):
        yy = y1 - (y1 - y0) * p_ / 100
        cv.line([(x0, yy), (x1, yy)], (255, 255, 255, 70), 1.6)
        cv.text(x0 - 18, yy, f"{p_}%", 34 if not cv.tall else 30, "bold", anchor="rm")
    cv.line([(x0, y1), (x1, y1)], (255, 255, 255, 230), 5)
    step = (x1 - x0) / (n - 1)

    def yv(v):
        return y1 - (y1 - y0) * v / 100

    def curve(x):  # cosine-smoothed rain chance at pixel x
        f = min(max((x - x0) / step, 0), n - 1)
        i = min(int(f), n - 2)
        u = (1 - math.cos(math.pi * (f - i))) / 2
        return rows[i]["pop"] * (1 - u) + rows[i + 1]["pop"] * u, rows[round(f)]

    # type-colored fill under the curve
    x = x0
    while x < x1:
        v, r = curve(x + 1)
        if _wet(r):
            col, _ = TYPES[r["pt"]]
            cv.rect(x, yv(v), 3.2, y1 - yv(v), (*col, 175))
        x += 2
    # the curve itself
    pts = [(xx, yv(curve(xx)[0])) for xx in [x0 + k * 3 for k in range(int((x1 - x0) / 3) + 1)]]
    cv.line(pts, (255, 255, 255, 245), 7)
    # run labels (contiguous same-type stretches)
    runs, cur = [], None
    for i, r in enumerate(rows):
        k = r["pt"] if _wet(r) else None
        if cur and cur[0] == k:
            cur[2] = i
        else:
            cur = [k, i, i]
            runs.append(cur)
    for k, a, b in runs:
        if not k:
            continue
        xa, xb = x0 + a * step, x0 + (b + 1) * step
        xb = min(xb, x1)
        mid = (xa + xb) / 2
        lab = TYPES[k][1]
        size = 44 if not cv.tall else 36
        if xb - xa >= cv.width(lab, size) * 0.9 or (xb - xa) >= 150:
            cv.text(mid, y1 - 52, lab.title() if k != "tstorm" else "Storms", size, "bold", stroke=3, anchor="mm", maxw=max(xb - xa - 10, 100))
        if k in ("ice", "mix") and xb - xa >= 100:
            top = min(yv(curve(mid)[0]), y1 - 140) - 150
            tri = [(mid, top), (mid - 58, top + 100), (mid + 58, top + 100)]
            cv.d.polygon([(z(a_), z(b_)) for a_, b_ in tri], fill=(255, 255, 255, 235))
            cv.text(mid, top + 80, "!", 54, "bold", TYPES[k][0], anchor="ms")
            cv.text(mid, top + 128, ("Freezing Rain" if k == "ice" else "Wintry Mix") + " Possible", 32 if not cv.tall else 26, "bold", TYPES[k][0], stroke=3, anchor="mm")
    # time labels every 6 hours
    for i, r in enumerate(rows):
        if r["t"].hour % 6 == 0:
            xx = x0 + i * step
            cv.line([(xx, y1), (xx, y1 + 14)], (255, 255, 255, 220), 3)
            cv.text(xx, y1 + 28, r["t"].strftime("%a").upper(), 30 if not cv.tall else 26, "bold", anchor="mt")
            cv.text(xx, y1 + 64, _hr(r["t"]).upper(), 38 if not cv.tall else 30, "bold", anchor="mt")
    cv.footer(pkg)
    return cv


# ------------------------------------------------------------------ TODAY vs TOMORROW MORNING
def _gradient(w, h, top, bot):
    g = Image.linear_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGB", (w, h), bot), Image.new("RGB", (w, h), top), g)


def _panel(cv, x, y, w, h, kind, seed):
    """Paint a weather-flavoured background into a box (sunny sky / cloudy / rainy / snowy / frosty / clear night)."""
    top, bot = {"sun": ((18, 82, 190), (118, 168, 226)), "cloud": ((70, 92, 124), (150, 168, 190)),
                "rain": ((44, 58, 82), (92, 108, 132)), "snow": ((90, 112, 140), (190, 206, 224)),
                "frost": ((26, 52, 60), (120, 160, 168)), "cold": ((20, 42, 90), (74, 118, 176)),
                "night": ((10, 18, 44), (30, 52, 100))}[kind]
    W, H = z(w), z(h)
    img = _gradient(W, H, top, bot).convert("RGBA")
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    rnd = random.Random(seed)
    if kind in ("sun", "cloud", "snow", "cold"):  # soft clouds
        for _ in range(9):
            cx, cy, r = rnd.randint(0, W), rnd.randint(int(H * 0.55), H), rnd.randint(int(W * 0.12), int(W * 0.3))
            d.ellipse([cx - r, cy - r // 2, cx + r, cy + r // 2], fill=(255, 255, 255, 70 if kind != "cloud" else 55))
        lay = lay.filter(ImageFilter.GaussianBlur(z(26)))
    if kind == "sun":
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([-W // 5, -H // 6, W // 3, H // 3], fill=(255, 244, 205, 120))
        lay = Image.alpha_composite(lay, glow.filter(ImageFilter.GaussianBlur(z(60))))
    if kind == "rain":
        d = ImageDraw.Draw(lay)
        for _ in range(180):
            rx, ry = rnd.randint(0, W), rnd.randint(0, H)
            d.line([(rx, ry), (rx - z(6), ry + z(34))], fill=(190, 215, 255, 90), width=z(2))
    if kind in ("frost", "snow"):  # little ice crystals
        d = ImageDraw.Draw(lay)
        for _ in range(230):
            fx, fy, L = rnd.randint(0, W), rnd.randint(0, H), rnd.randint(z(8), z(30))
            a = rnd.random() * math.pi
            for k in range(3):
                b = a + k * math.pi / 3
                d.line([(fx - math.cos(b) * L, fy - math.sin(b) * L), (fx + math.cos(b) * L, fy + math.sin(b) * L)],
                       fill=(235, 248, 255, rnd.randint(70, 150)), width=z(2))
    if kind == "night":
        d = ImageDraw.Draw(lay)
        for _ in range(90):
            sx, sy = rnd.randint(0, W), rnd.randint(0, int(H * 0.7))
            r = rnd.randint(1, z(3))
            d.ellipse([sx, sy, sx + r, sy + r], fill=(255, 255, 255, rnd.randint(90, 220)))
    img = Image.alpha_composite(img, lay).convert("RGB")
    cv.img.paste(img, (z(x), z(y)))
    cv.d = ImageDraw.Draw(cv.img, "RGBA")


def _sky_kind(icon, temp):
    if icon in ("snow", "mix"):
        return "snow"
    if icon in ("rain", "showers", "tstorm"):
        return "rain"
    if icon in ("cloudy", "mostly_cloudy", "fog"):
        return "cloud"
    return "sun"


def today_vs_tomorrow(pkg, cfg):
    rows, tz = _rows(pkg, cfg)
    days = pkg.get("days") or []
    if not days or len(rows) < 8:
        return None
    first = rows[0]["t"]
    if pkg.get("evening_mode"):
        left_lab, left_val, left_icon, left_cond = "RIGHT NOW", rows[0]["temp"], rows[0]["icon"] or "partly", rows[0]["cond"]
    else:
        d0 = days[0]
        left_lab, left_val, left_icon, left_cond = "TODAY", d0["high"], d0["icon"], d0["cond"]
    target = first.date() if first.hour < 6 else first.date() + timedelta(days=1)
    mor = [r for r in rows if r["t"].date() == target and 3 <= r["t"].hour <= 9 and r["temp"] is not None]
    if mor:
        low = min(mor, key=lambda r: r["temp"])
        right_val, right_cond = low["temp"], low["cond"]
    else:
        d1 = days[1] if len(days) > 1 else days[0]
        right_val, right_cond = d1["low"], d1["night_cond"]
    right_lab = "THIS MORNING" if target == first.date() else "TOMORROW MORNING"
    if left_val is None or right_val is None:
        return None
    cv = Canvas(cfg)
    W, H = cv.W, cv.H
    lk = _sky_kind(left_icon, left_val)
    rk = "frost" if right_val <= 32 else "cold" if right_val <= 45 else "night"
    if cv.tall:
        _panel(cv, 0, 0, W, H / 2, lk, 3)
        _panel(cv, 0, H / 2, W, H / 2, rk, 8)
        boxes = [(0, 0, W, H / 2), (0, H / 2, W, H / 2)]
        cv.rect(0, H / 2 - 4, W, 8, (206, 74, 50, 255))
    else:
        _panel(cv, 0, 0, W / 2, H, lk, 3)
        _panel(cv, W / 2, 0, W / 2, H, rk, 8)
        boxes = [(0, 0, W / 2, H), (W / 2, 0, W / 2, H)]
        cv.rect(W / 2 - 4, 0, 8, H, (206, 74, 50, 255))
    delta = right_val - left_val
    for (bx, by, bw, bh), lab, val, cond in zip(boxes, (left_lab, right_lab), (left_val, right_val), (left_cond, right_cond)):
        cx = bx + bw / 2
        two = " " in lab and len(lab) > 9
        words = lab.split(" ", 1) if two else [lab]
        ls = min(112 if not cv.tall else min(96, bh * 0.14), bw / (max(len(w) for w in words) * 0.66))
        ly = by + bh * (0.13 if not cv.tall else 0.09)
        for i, wd in enumerate(words):
            cv.text(cx, ly + i * ls * 1.04, wd, ls, "bold", anchor="mt", stroke=2, stroke_fill=(10, 16, 30, 120))
        ny = by + bh * (0.70 if not cv.tall else 0.73)
        ns = min(bh * (0.5 if not cv.tall else 0.42), bw / 2.1)
        cv.text(cx, ny, f"{val}°", ns, "bold", anchor="ms", stroke=3, stroke_fill=(10, 16, 30, 90))
        if cond:
            cv.text(cx, ny + bh * (0.1 if not cv.tall else 0.06), cond.upper(), 38 if not cv.tall else 32, "bold", (255, 255, 255, 235), anchor="mt", maxw=bw - 100, stroke=2, stroke_fill=(10, 16, 30, 120))
    if abs(delta) >= 3:
        word = f"{abs(delta)}° {'COLDER' if delta < 0 else 'WARMER'}"
        pw_ = cv.width(word, 38) + 64
        px_, py_ = W / 2 - pw_ / 2, (H / 2 - 30 if cv.tall else H - 150)
        if cv.tall:
            py_ = H / 2 - 30
        cv.rect(px_, py_, pw_, 62, (13, 21, 38, 230), r=31)
        cv.text(W / 2, py_ + 31, word, 38, "bold", anchor="mm")
    cv.logo(H - 16 if not cv.tall else H - 52)
    cv.text(cv.M, H - 34, f"DATA: {pkg.get('source', 'NWS NDFD').upper()}  ·  GRAPHIC CREATED: {pkg['issued_label'].upper()}", 19, "medium", (255, 255, 255, 235), anchor="ls", stroke=2, stroke_fill=(10, 16, 30, 160))
    return cv


# ------------------------------------------------------------------ WHAT TO EXPECT
def _blocks(rows, count=6):
    """Consecutive AM (6a-12p) / PM (12p-6p) / Night (6p-6a) blocks starting with the one that contains the first hour."""
    def key(t):
        h = t.hour
        d = t.date()
        if h < 6:
            return d - timedelta(days=1), 2
        return (d, 0 if h < 12 else 1 if h < 18 else 2)
    out = []
    for r in rows:
        k = key(r["t"])
        if not out or out[-1]["k"] != k:
            out.append({"k": k, "rows": []})
        out[-1]["rows"].append(r)
    res = []
    for b in out[:count]:
        d, part = b["k"]
        res.append({"rows": b["rows"], "dow": d.strftime("%a").upper(), "part": ("AM", "PM", "NIGHT")[part]})
    return res


def _cell(rows_):
    """-> {row_key: (label, fill rgb)} for the strongest signal of each precip type in a block."""
    got = {}
    for r in rows_:
        if not _wet(r):
            continue
        k = r["pt"]
        cur = got.get(k, {"pop": 0, "q": 0.0, "n": 0})
        cur["pop"], cur["q"], cur["n"] = max(cur["pop"], r["pop"]), max(cur["q"], r["q"]), cur["n"] + 1
        got[k] = cur
    out = {}
    for k, g in got.items():
        if k == "rain":
            if g["q"] >= 0.15:
                out["rain"] = ("HEAVY RAIN", (255, 196, 0))
            elif g["pop"] >= 60:
                out["rain"] = ("RAIN", (22, 168, 36))
            else:
                out["rain"] = ("SHOWERS", (96, 208, 104))
        elif k == "tstorm":
            out["tstorm"] = ("STORMS" if g["pop"] >= 60 else "SCATTERED STORMS", (255, 140, 0))
        elif k in ("mix", "ice"):
            out["mix"] = ("FREEZING RAIN" if k == "ice" else "WINTRY MIX", (255, 56, 255))
        elif k == "snow":
            out["snow"] = ("SNOW" if g["pop"] >= 60 else "SNOW SHOWERS", (128, 214, 255))
    return out


def what_to_expect(pkg, cfg):
    rows, tz = _rows(pkg, cfg)
    rows = rows[:72]
    blocks = _blocks(rows)
    if len(blocks) < 3:
        return None
    cells = [_cell(b["rows"]) for b in blocks]
    present = {k for c in cells for k in c}
    if not present:
        return None
    lines = [("rain", "RAIN", (60, 165, 255))]
    if "tstorm" in present:
        lines.append(("tstorm", "STORMS", (253, 149, 0)))
    lines += [("mix", "WINTRY MIX", (222, 98, 224)), ("snow", "SNOW", (4, 233, 231))]
    cv = Canvas(cfg)
    cv.header("WHAT TO EXPECT", f"NEXT {len(blocks)} TIME BLOCKS  ·  {pkg['location']['area'].upper()}")
    M = cv.M
    tx, ty, tw, th = M, cv.top, cv.W - 2 * M, cv.bottom - cv.top
    labw = 250 if not cv.tall else 190
    hh = 120 if not cv.tall else 104
    cw = (tw - labw) / len(blocks)
    rh = (th - hh) / len(lines)
    cv.rect(tx, ty, tw, th, C["panel"], r=14)
    cv.rect(tx, ty, tw, hh, (255, 255, 255, 30), r=14)
    for i, b in enumerate(blocks):
        cx = tx + labw + i * cw + cw / 2
        s = 40 if not cv.tall else 30
        cv.text(cx, ty + hh * 0.34, b["dow"], s, "bold", anchor="mm", maxw=cw - 14)
        cv.text(cx, ty + hh * 0.72, b["part"], s, "bold", C["muted"] if b["part"] != "NIGHT" else (150, 175, 255), anchor="mm", maxw=cw - 14)
        if i:
            cv.line([(tx + labw + i * cw, ty + 10), (tx + labw + i * cw, ty + th - 10)], (255, 255, 255, 60), 1.6)
    for j, (key, lab, col) in enumerate(lines):
        ry = ty + hh + j * rh
        cv.line([(tx + 14, ry), (tx + tw - 14, ry)], (255, 255, 255, 120), 2)
        cv.rect(tx, ry + 14, 8, rh - 28, (*col, 255), r=3)
        cv.text(tx + 34, ry + rh / 2, lab, 40 if not cv.tall else 30, "bold", anchor="lm", maxw=labw - 44)
        i = 0
        while i < len(blocks):  # merge neighbouring blocks with the same label into one bar
            c = cells[i].get(key)
            if not c:
                i += 1
                continue
            k = i
            while k + 1 < len(blocks) and cells[k + 1].get(key) == c:
                k += 1
            bx = tx + labw + i * cw + 8
            bw = (k - i + 1) * cw - 16
            cv.rect(bx, ry + 16, bw, rh - 32, (*c[1], 255), r=14)
            lum = 0.299 * c[1][0] + 0.587 * c[1][1] + 0.114 * c[1][2]
            tc = (10, 16, 30) if lum > 95 else (255, 255, 255)
            words = c[0].split(" ", 1) if (bw < 330 and " " in c[0]) else [c[0]]
            size = min(46 if not cv.tall else 34, (rh - 40) / (1.25 * len(words)))
            for q, wd in enumerate(words):
                cv.text(bx + bw / 2, ry + rh / 2 + (q - (len(words) - 1) / 2) * size * 1.2, wd, size, "bold", tc, anchor="mm", maxw=bw - 16)
            i = k + 1
    cv.footer(pkg)
    return cv
