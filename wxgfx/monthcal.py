"""Month-so-far calendars for Norfolk: daily highs vs normal, and daily rainfall, with the month's rank on record.

Data: RCC-ACIS (keyless) for the threaded Norfolk record (config acis_station, default "ORFthr"):
  * this month's daily max temp and precipitation, each with the 1991-2020 daily normal
  * every year's same-dates mean high / total rain (season-to-date from the 1st), for the "Nth warmest / driest" rank
Today's cell shows the warmest ASOS reading so far at KORF when the asos_temps data is in the run.
Graphics (Climate & Drought folder): month_highs_cal, month_rain_cal.
"""
import calendar
import json
import math
import urllib.request
from datetime import date, datetime, timedelta

from .theme import C, Canvas

ACIS = "https://data.rcc-acis.org/StnData"
ABOVE, AVG, BELOW = (232, 96, 88), (150, 162, 180), (58, 110, 205)
RAIN = (76, 190, 110)  # green
SNOW = (88, 160, 255)  # blue


def _post(body, ua, timeout=90):
    req = urllib.request.Request(ACIS, data=json.dumps(body).encode(), headers={"User-Agent": ua, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _num(x):
    if x in ("T", "t"):
        return 0.0
    try:
        return float(str(x).rstrip("ASs"))
    except (TypeError, ValueError):
        return None


def _r(x):
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def fetch(cfg, today):
    """Data through yesterday (the last complete day) for yesterday's month."""
    sid = cfg.get("acis_station", "ORFthr")
    end = today - timedelta(days=1)
    start = end.replace(day=1)
    ua = cfg["user_agent"]
    try:
        d = _post({"sid": sid, "sdate": start.isoformat(), "edate": end.isoformat(),
                   "elems": [{"name": "maxt"}, {"name": "maxt", "normal": "1"}, {"name": "pcpn"}, {"name": "pcpn", "normal": "1"}, {"name": "snow"}]}, ua)
        days = [{"date": r[0], "hi": _num(r[1]), "hi_n": _num(r[2]), "rain": _num(r[3]), "trace": str(r[3]).upper().startswith("T"),
                 "rain_n": _num(r[4]), "snow": _num(r[5]) if len(r) > 5 else None,
                 "snow_t": len(r) > 5 and str(r[5]).upper().startswith("T")} for r in d.get("data", [])]
        # every year's same dates (the 1st through this day of the month), worked out from the full daily record
        y = _post({"sid": sid, "sdate": "por", "edate": end.isoformat(), "elems": [{"name": "maxt"}, {"name": "pcpn"}]}, ua, timeout=150)
        nd = end.day
        acc = {}
        for r in y.get("data", []):
            dt = date.fromisoformat(r[0])
            if dt.month != start.month or dt.day > nd:
                continue
            a = acc.setdefault(dt.year, {"hi": [], "rain": []})
            hv, pv = _num(r[1]), _num(r[2])
            if hv is not None:
                a["hi"].append(hv)
            if pv is not None:
                a["rain"].append(pv)
        years = []
        for yr, a in sorted(acc.items()):
            years.append({"year": yr, "hi": sum(a["hi"]) / len(a["hi"]) if len(a["hi"]) >= nd - 1 else None,  # at most one day missing
                          "rain": sum(a["rain"]) if len(a["rain"]) >= nd - 1 else None})
        print(f"  ACIS: {len(years)} years; this year {years[-1] if years else None}")
    except Exception as e:
        print(f"  ! month calendar (ACIS) unavailable: {e}")
        return None
    return {"start": start.isoformat(), "end": end.isoformat(), "days": days, "years": years}


def sample(today):
    import random
    rnd = random.Random(5)
    end = today - timedelta(days=1)
    start = end.replace(day=1)
    days = []
    for i in range((end - start).days + 1):
        dd = start + timedelta(days=i)
        n = 66 - i * 0.25
        hi = round(n + (7 if i < 12 else -7) + rnd.uniform(-4, 4))
        rain = [0, 0, 0, 0.26, 0.14, 0.47, 0, 0, 0, 0, 0, 0, 0, 0, 0][i % 15]
        days.append({"date": dd.isoformat(), "hi": hi, "hi_n": round(n, 1), "rain": rain, "trace": i in (0, 10, 11, 12) and not rain, "rain_n": 0.11,
                     "snow": 1.4 if i == 5 else 0, "snow_t": False})
    years = [{"year": y, "hi": 66 + rnd.uniform(-5, 5), "rain": rnd.uniform(0.2, 3.5)} for y in range(1874, end.year)]
    years.append({"year": end.year, "hi": sum(d["hi"] for d in days) / len(days), "rain": sum(d["rain"] for d in days)})
    return {"start": start.isoformat(), "end": end.isoformat(), "days": days, "years": years}


def _ord(n):
    return f"{n}{'TH' if 10 <= n % 100 <= 20 else {1: 'ST', 2: 'ND', 3: 'RD'}.get(n % 10, 'TH')}"


def _rank(years, key, this_year, high):
    vals = [y for y in years if y[key] is not None]
    me = next((y for y in vals if y["year"] == this_year), None)
    if not me:
        return None, None
    others = [y[key] for y in vals if y["year"] != this_year]
    rank = 1 + sum(1 for v in others if (v > me[key] if high else v < me[key]))
    return rank, min(y["year"] for y in vals)


# ------------------------------------------------------------------ layout
def _layout(cv, start):
    """-> (info column box, calendar box, legend origin) for wide and tall canvases."""
    x0, y0 = cv.M, 200
    W, H = cv.W - 2 * cv.M, cv.H - 200 - 90
    if cv.W > cv.H:
        lw = 520
        return (x0, y0, lw, H - 170), (x0 + lw + 30, y0, W - lw - 30, H), (x0, y0 + H - 150)
    return (x0, y0, W, 220), (x0, y0 + 240, W, H - 240 - 90), (x0, y0 + H - 70)


def _calendar(cv, box, start, cells, today):
    """cells: {day number: (fill rgba or None, big text, small text, big text colour)}"""
    x, y, w, h = box
    gap = 8
    cw = (w - 6 * gap) / 7
    weeks = len(calendar.Calendar(firstweekday=6).monthdayscalendar(start.year, start.month))
    hh = 52
    ch = min(150, (h - hh - gap - (weeks - 1) * gap) / weeks)
    for i, nm in enumerate(("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")):
        cx = x + i * (cw + gap)
        cv.rect(cx, y, cw, hh, (255, 255, 255, 30), r=8)
        cv.text(cx + cw / 2, y + hh / 2, nm, 24 if cw > 150 else 18, "bold", anchor="mm")
    for r_, wk in enumerate(calendar.Calendar(firstweekday=6).monthdayscalendar(start.year, start.month)):
        for c, dn in enumerate(wk):
            if not dn:
                continue
            cx, cy = x + c * (cw + gap), y + hh + gap + r_ * (ch + gap)
            cell = cells.get(dn)
            is_today = start.replace(day=dn) == today
            if cell and cell[0]:
                cv.rect(cx, cy, cw, ch, cell[0], r=10, outline=(255, 255, 255, 255) if is_today else None, ow=4)
            else:
                cv.rect(cx, cy, cw, ch, (255, 255, 255, 10), r=10, outline=(255, 255, 255, 255) if is_today else (255, 255, 255, 50), ow=4 if is_today else 2)
            fs = 22 if cw > 150 else 16
            light = bool(cell and cell[0] and len(cell[0]) == 4 and cell[0][3] > 200 and sum(cell[0][:3]) > 600)
            cv.text(cx + 12, cy + 10, str(dn), fs, "bold", (13, 21, 38) if light else (255, 255, 255, 230), anchor="lt")
            if cell:
                _, big, small, ink = cell
                bs = min(ch * 0.42, cw * 0.36) if len(big) <= 3 else min(ch * 0.3, cw * 0.22)
                cv.text(cx + cw / 2, cy + ch * 0.52, big, bs, "bold", ink, anchor="mm", maxw=cw - 14)
                if small:
                    cv.text(cx + cw / 2, cy + ch * 0.84, small, min(22, ch * 0.16), "bold", ink, anchor="mm", maxw=cw - 10)


def _info(cv, box, blocks):
    """Stacked info cards: [(label, big value, line under)]"""
    x, y, w, h = box
    tall = cv.H > cv.W
    n = len(blocks)
    gap = 18
    if tall:  # side by side
        bw = (w - gap * (n - 1)) / n
        for i, (lab, big, sub) in enumerate(blocks):
            bx = x + i * (bw + gap)
            cv.rect(bx, y, bw, h, C["panel"], r=16)
            cv.text(bx + 24, y + 26, lab, 20, "bold", C["muted"], anchor="lt", maxw=bw - 40)
            cv.text(bx + 24, y + 62, big, 84, "bold", anchor="lt", maxw=bw - 40)
            cv.text(bx + 24, min(y + h - 30, y + 190), sub, 22, "medium", anchor="lb", maxw=bw - 40)
        return
    bh = (h - gap * (n - 1)) / n
    for i, (lab, big, sub) in enumerate(blocks):
        by = y + i * (bh + gap)
        cv.rect(x, by, w, bh, C["panel"], r=16)
        cv.text(x + 32, by + 34, lab, 24, "bold", C["muted"], anchor="lt", maxw=w - 60)
        cv.text(x + 32, by + 80, big, 110, "bold", anchor="lt", maxw=w - 60)
        cv.text(x + 32, min(by + bh - 34, by + 250), sub, 28, "medium", anchor="lb", maxw=w - 60)


def _legend(cv, origin, items):
    x, y = origin
    tall = cv.H > cv.W
    for i, (col, lab) in enumerate(items):
        if tall:
            lx, ly = x + i * (cv.W - 2 * cv.M) / len(items), y
        else:
            lx, ly = x, y + i * 50
        cv.rect(lx, ly, 34, 34, col, r=6, outline=(255, 255, 255, 120), ow=2)
        cv.text(lx + 48, ly + 17, lab, 24 if not tall else 19, "bold", anchor="lm")


def highs_graphic(pkg, cfg):
    md = pkg.get("_monthcal")
    if not md or not md["days"]:
        return None
    start, end = date.fromisoformat(md["start"]), date.fromisoformat(md["end"])
    today = datetime.fromisoformat(pkg["issued"]).date()
    obs = [d for d in md["days"] if d["hi"] is not None and d["hi_n"] is not None]
    if not obs:
        return None
    cells, nabove, navg, nbelow = {}, 0, 0, 0
    for d in obs:
        dep = _r(d["hi"] - d["hi_n"])
        col = ABOVE if dep > 0 else BELOW if dep < 0 else AVG
        nabove += dep > 0
        nbelow += dep < 0
        navg += dep == 0
        cells[date.fromisoformat(d["date"]).day] = ((*col, 255), f"{round(d['hi'])}", f"{'+' if dep > 0 else '−' if dep < 0 else ''}{abs(dep)}" if dep else "AVG",
                                                    (255, 255, 255))
    so_far = None
    asos = pkg.get("_asos") or {}
    korf = next((r for r in asos.get("rows", []) if r["id"] == "KORF"), None)
    if korf and today.month == start.month:
        so_far = korf["hi"]
        cells[today.day] = ((255, 255, 255, 235), f"{so_far}", "SO FAR", (13, 21, 38))
    avg = sum(d["hi"] for d in obs) / len(obs)
    navg_n = sum(d["hi_n"] for d in obs) / len(obs)
    dep = avg - navg_n
    rank, first = _rank(md["years"], "hi", end.year, high=dep >= 0)
    mon = start.strftime("%B").upper()
    cv = Canvas(cfg)
    cv.header(f"{mon} {start.year} HIGHS SO FAR", f"NORFOLK INTERNATIONAL AIRPORT  ·  THROUGH {end.strftime('%b').upper()} {end.day}")
    info, calbox, leg = _layout(cv, start)
    blocks = [(f"{mon} AVG HIGH", f"{avg:.1f}°", f"{'+' if dep >= 0 else '−'}{abs(dep):.1f}° {'above' if dep >= 0 else 'below'} normal")]
    if rank:
        blocks.append((("WARMEST" if dep >= 0 else "COOLEST") + " ON RECORD", _ord(rank), f"{start.strftime('%b')} 1–{end.day} since {first}"))
    _info(cv, info, blocks)
    _calendar(cv, calbox, start, cells, today)
    _legend(cv, leg, [((*ABOVE, 255), f"ABOVE · {nabove} DAY{'S' if nabove != 1 else ''}"), ((*AVG, 255), f"AVERAGE · {navg} DAY{'S' if navg != 1 else ''}"), ((*BELOW, 255), f"BELOW · {nbelow} DAY{'S' if nbelow != 1 else ''}")])
    cv.footer(pkg, source="NOAA RCC-ACIS · NWS")
    return cv


def rain_graphic(pkg, cfg):
    md = pkg.get("_monthcal")
    if not md or not md["days"]:
        return None
    start, end = date.fromisoformat(md["start"]), date.fromisoformat(md["end"])
    today = datetime.fromisoformat(pkg["issued"]).date()
    obs = [d for d in md["days"] if d["rain"] is not None]
    if not obs:
        return None
    cells, wet, dry, trace, snowdays, snowtot = {}, 0, 0, 0, 0, 0.0
    for d in obs:
        dn = date.fromisoformat(d["date"]).day
        sn = d.get("snow") or 0
        if sn >= 0.1 or d.get("snow_t"):  # snow day: blue, melted total big, snowfall underneath
            snowdays += 1
            snowtot += sn
            cells[dn] = ((*SNOW, 255), f"{(d['rain'] or 0):.2f}\"" if (d["rain"] or 0) >= 0.01 else ("T" if d["trace"] else "0.00\""),
                         f"{sn:.1f}\" SNOW" if sn >= 0.1 else "TRACE SNOW", (13, 21, 38))
        elif d["rain"] and d["rain"] >= 0.01:
            wet += 1
            cells[dn] = ((*RAIN, 255), f"{d['rain']:.2f}\"", "", (13, 21, 38))
        else:
            dry += 1
            trace += bool(d["trace"])
            cells[dn] = ((255, 255, 255, 34), "T" if d["trace"] else "", "", (255, 255, 255))
    if today.month == start.month:
        cells.setdefault(today.day, ((255, 255, 255, 34), "", "TODAY", (255, 255, 255)))
    tot = sum(d["rain"] for d in obs)
    norm = sum(d["rain_n"] or 0 for d in obs)
    dep = tot - norm
    rank, first = _rank(md["years"], "rain", end.year, high=dep >= 0)
    mon = start.strftime("%B").upper()
    cv = Canvas(cfg)
    cv.header(f"{mon} {start.year} RAINFALL SO FAR", f"NORFOLK INTERNATIONAL AIRPORT  ·  THROUGH {end.strftime('%b').upper()} {end.day}")
    info, calbox, leg = _layout(cv, start)
    blocks = [(f"{mon} RAIN", f"{tot:.2f}\"", f"{abs(dep):.2f}\" {'above' if dep >= 0 else 'below'} normal ({norm:.2f}\")")]
    if rank:
        blocks.append((("WETTEST" if dep >= 0 else "DRIEST") + " ON RECORD", _ord(rank), f"{start.strftime('%b')} 1–{end.day} since {first}"))
    _info(cv, info, blocks)
    _calendar(cv, calbox, start, cells, today)
    _legend(cv, leg, [((*RAIN, 255), f"RAIN · {wet} DAY{'S' if wet != 1 else ''}")] + ([((*SNOW, 255), f"SNOW · {snowdays} DAY{'S' if snowdays != 1 else ''} ({snowtot:.1f}\")")] if snowdays else []) + [((255, 255, 255, 60), f"DRY · {dry} DAY{'S' if dry != 1 else ''}" + (f" ({trace} TRACE)" if trace else ""))])
    cv.footer(pkg, source="NOAA RCC-ACIS · NWS")
    return cv


def monthcal_graphics(pkg, cfg):
    out = []
    for name, fn in (("month_highs_cal", highs_graphic), ("month_rain_cal", rain_graphic)):
        g = fn(pkg, cfg)
        if g:
            out.append((name, g))
    return out or None
