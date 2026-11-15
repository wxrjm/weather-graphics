"""NBM 10-day highs and lows for Norfolk.

Data: the National Blend of Models (NBM) daily max / min temperature from Open-Meteo (model ncep_nbm_conus, free, no key),
falling back to Open-Meteo's best-match blend if NBM isn't available. Days are local calendar days.
Graphic (Temperature folder): nbm_10day - one column per day, a bar from the low up to the high coloured by temperature,
the high above and the low below, weekday and date underneath.
"""
import json
import math
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from .statemaps import temp_color
from .theme import C, Canvas, z

URL = "https://api.open-meteo.com/v1/forecast"


def fetch(lat, lon, cfg, days=10):
    for model in ("ncep_nbm_conus", "best_match"):
        q = {"latitude": lat, "longitude": lon, "daily": "temperature_2m_max,temperature_2m_min", "temperature_unit": "fahrenheit",
             "timezone": cfg["timezone"], "forecast_days": days + 1}
        if model != "best_match":
            q["models"] = model
        req = urllib.request.Request(f"{URL}?{urllib.parse.urlencode(q)}", headers={"User-Agent": cfg["user_agent"]})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))["daily"]
        except Exception as e:
            print(f"  ! NBM temperatures ({model}) unavailable: {e}")
            continue
        hi = d.get("temperature_2m_max") or d.get(f"temperature_2m_max_{model}") or []
        lo = d.get("temperature_2m_min") or d.get(f"temperature_2m_min_{model}") or []
        rows = [{"date": t, "high": h, "low": l} for t, h, l in zip(d["time"], hi, lo) if h is not None and l is not None]
        if len(rows) >= 7:
            return {"rows": rows, "model": "NBM" if model != "best_match" else "MODEL BLEND"}
    return None


def sample(now, tz):
    base = now.astimezone(tz).date()
    rows = []
    for i in range(11):
        h = 58 + 8 * math.sin(i / 3.0) - (6 if i in (4, 5) else 0)
        rows.append({"date": (base + timedelta(days=i)).isoformat(), "high": h, "low": h - 15 - 3 * math.cos(i)})
    return {"rows": rows, "model": "NBM"}


def nbm_graphic(pkg, cfg):
    nd = pkg.get("_nbm_temps")
    if not nd:
        return None
    today = datetime.fromisoformat(pkg["issued"]).date()
    rows = [r for r in nd["rows"] if date.fromisoformat(r["date"]) >= today][:cfg.get("nbm_days", 10)]
    if len(rows) < 5:
        return None
    for r in rows:
        r["hi"], r["lo"] = int(math.floor(r["high"] + 0.5)), int(math.floor(r["low"] + 0.5))
    cv = Canvas(cfg)
    cv.header("10 DAY HIGHS & LOWS", f"{pkg['location'].get('name', 'NORFOLK').upper()}  ·  NATIONAL BLEND OF MODELS ({nd['model']})")
    tall = cv.H > cv.W
    x0, y0 = cv.M, 205
    W, H = cv.W - 2 * cv.M, cv.H - 205 - 105
    cv.rect(x0, y0, W, H, C["panel"], r=18)
    n = len(rows)
    cw = W / n
    top, bot = y0 + 80, y0 + H - 130  # vertical room for the bars (values sit above / below)
    vmax = max(r["hi"] for r in rows) + 2
    vmin = min(r["lo"] for r in rows) - 2

    def Y(v):
        return bot - (bot - top) * (v - vmin) / (vmax - vmin)

    bw = min(56, cw * 0.42)
    for i, r in enumerate(rows):
        cx = x0 + cw * (i + 0.5)
        if i:
            cv.rect(x0 + cw * i - 0.75, y0 + 20, 1.5, H - 40, (255, 255, 255, 22))
        yh, yl = Y(r["hi"]), Y(r["lo"])
        # bar from the low to the high, blended low colour -> high colour, with rounded ends
        from PIL import Image, ImageDraw
        bwp, bhp = max(2, z(bw)), max(2, z(yl - yh))
        grad = Image.new("RGB", (bwp, bhp))
        gd = ImageDraw.Draw(grad)
        for k in range(bhp):
            gd.line([(0, k), (bwp, k)], fill=temp_color(r["hi"] - (r["hi"] - r["lo"]) * k / max(1, bhp - 1)))
        mask = Image.new("L", (bwp, bhp), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, bwp - 1, bhp - 1], radius=min(bwp, bhp) // 2, fill=255)
        cv.img.paste(grad, (z(cx - bw / 2), z(yh)), mask)
        fs = 34 if not tall else 24
        cv.text(cx, yh - 12, f"{r['hi']}°", fs, "bold", anchor="ms")
        cv.text(cx, yl + 12, f"{r['lo']}°", fs - 6, "bold", (190, 210, 235), anchor="mt")
        dd = date.fromisoformat(r["date"])
        cv.text(cx, y0 + H - 70, "TODAY" if dd == today else dd.strftime("%a").upper(), 24 if not tall else 17, "bold", anchor="mm", maxw=cw - 6)
        cv.text(cx, y0 + H - 38, f"{dd.month}/{dd.day}", 18 if not tall else 14, "medium", C["muted"], anchor="mm")
    cv.footer(pkg, source=f"NWS NATIONAL BLEND OF MODELS VIA OPEN-METEO")
    return cv


def nbm_graphics(pkg, cfg):
    g = nbm_graphic(pkg, cfg)
    return [("nbm_10day", g)] if g else None
