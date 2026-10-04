"""Turn NDFD hourly grids into a plain forecast package (dict).

Every graphic renders ONLY from this package, so the package can be saved as
forecast.json, hand-edited, partially overridden, or written entirely by hand.
"""
import math
from datetime import datetime, timedelta, time as dtime

HOUR = timedelta(hours=1)

WX_TYPES = {  # ndfd weather -> (priority, display name, icon)
    "thunderstorms": (10, "Storms", "tstorm"),
    "snow": (9, "Snow", "snow"),
    "snow_showers": (9, "Snow Showers", "snow"),
    "blowing_snow": (8, "Blowing Snow", "snow"),
    "freezing_rain": (8, "Freezing Rain", "mix"),
    "freezing_drizzle": (7, "Freezing Drizzle", "mix"),
    "sleet": (7, "Sleet", "mix"),
    "rain": (6, "Rain", "rain"),
    "rain_showers": (5, "Showers", "showers"),
    "drizzle": (4, "Drizzle", "rain"),
    "fog": (2, "Fog", "fog"),
    "freezing_fog": (2, "Freezing Fog", "fog"),
    "haze": (1, "Haze", None),
    "smoke": (1, "Smoke", None),
}
COVERAGE = {  # coverage -> (strength, phrase template)
    "slight_chance": (2, "Slight Chance of {}"), "isolated": (2, "Isolated {}"),
    "patchy": (2, "Patchy {}"), "chance": (4, "Chance of {}"),
    "scattered": (4, "Scattered {}"), "areas": (4, "Areas of {}"),
    "occasional": (5, "Occasional {}"), "periods": (5, "Periods of {}"),
    "likely": (7, "{} Likely"), "numerous": (7, "Numerous {}"),
    "widespread": (7, "Widespread {}"), "definite": (9, "{}"),
}
PRECIP_ICONS = {"tstorm", "snow", "mix", "rain", "showers"}
DIRS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
EMOJI = {"clear": "☀️", "few": "🌤️", "partly": "⛅", "mostly_cloudy": "🌥️", "cloudy": "☁️",
         "showers": "🌦️", "rain": "🌧️", "tstorm": "⛈️", "snow": "🌨️", "mix": "🌨️",
         "fog": "🌫️", "wind": "💨"}


def round_pop(v):
    """Rain chances always go to the nearest 10% (37 -> 40, 24 -> 20, 5 -> 10, 4 -> 0)."""
    if v is None:
        return None
    try:
        return int((float(v) + 5) // 10 * 10)  # half rounds up (25 -> 30), not banker's rounding
    except (TypeError, ValueError):
        return v


def round_pops(obj):
    """Round every 'pop' / '*_pop' value in a forecast package (also catches manual edits/overrides)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if (k == "pop" or k.endswith("_pop")) and isinstance(v, (int, float)):
                obj[k] = round_pop(v)
            elif not k.startswith("_"):
                round_pops(v)
    elif isinstance(obj, list):
        for v in obj:
            round_pops(v)
    return obj


def rnd(v):
    return None if v is None else int(round(v))


def compass(deg):
    return None if deg is None else DIRS[int((deg % 360) / 22.5 + 0.5) % 16]


def normal_temps(d):
    """Approximate ORF 1991-2020 normals (cosine fit). Good to ~2F."""
    phase = math.cos(2 * math.pi * (d.timetuple().tm_yday - 203) / 365.25)
    return 69.8 + 20.2 * phase, 53.2 + 19.8 * phase


def sky_words(sky, night):
    if sky is None:
        return "Partly Cloudy", "partly"
    if sky <= 12:
        return ("Clear" if night else "Sunny"), "clear"
    if sky <= 37:
        return ("Mostly Clear" if night else "Mostly Sunny"), "few"
    if sky <= 62:
        return "Partly Cloudy", "partly"
    if sky <= 87:
        return "Mostly Cloudy", "mostly_cloudy"
    return "Cloudy", "cloudy"


def timing_phrase(hours):
    """Local datetimes where precip is favored -> 'mainly this afternoon' etc."""
    if not hours:
        return ""
    buckets = []
    for h in sorted({t.hour for t in hours}):
        b = ("overnight" if h < 6 else "morning" if h < 12 else
             "afternoon" if h < 18 else "evening")
        if b not in buckets:
            buckets.append(b)
    if len(buckets) >= 3:
        return "at times"
    if len(buckets) == 2:
        return f"in the {buckets[0]} and {buckets[1]}"
    return f"mainly in the {buckets[0]}"


def summarize_window(grid, start, end, night=False):
    """Condition / icon / numbers for an arbitrary local time window."""
    temps = grid.series("temperature", start, end)
    pops = grid.series("probabilityOfPrecipitation", start, end)
    sky = grid.series("skyCover", start, end)
    gust = grid.series("windGust", start, end)
    wspd = grid.series("windSpeed", start, end)
    wdir = grid.series("windDirection", start, end)
    qpf = sum(grid.series("quantitativePrecipitation", start, end))
    snow = sum(grid.series("snowfallAmount", start, end))
    pop = round_pop(max(pops) if pops else 0)  # nearest 10%
    sky_avg = sum(sky) / len(sky) if sky else None

    best, wet_hours, fog_hours = None, [], 0
    wx_hours = grid.weather_in(start, end)
    for t, vals in wx_hours:
        fog_hours += any(WX_TYPES.get(v.get("weather"), (0, 0, None))[2] == "fog" for v in vals)
    fog_ok = fog_hours >= max(1, len(wx_hours) / 3)
    for t, vals in wx_hours:
        p = grid.pop_at(t)
        for v in vals:
            info = WX_TYPES.get(v.get("weather"))
            if not info:
                continue
            is_precip = info[2] in PRECIP_ICONS
            if is_precip and p < 15:
                continue
            if info[2] == "fog" and not fog_ok:
                continue
            if not is_precip and info[2] != "fog":
                continue
            cov = COVERAGE.get(v.get("coverage"), (3, "{}"))
            score = (info[0] if is_precip else info[0] - 10, cov[0])
            if best is None or score > best[0]:
                best = (score, v["weather"], v.get("coverage"))
            if is_precip:
                wet_hours.append(t.astimezone(grid.tz))

    sky_label, icon = sky_words(sky_avg, night)
    cond, wx_name = sky_label, None
    if best:
        _, w, c = best
        name, wx_icon = WX_TYPES[w][1], WX_TYPES[w][2]
        tmpl = COVERAGE.get(c, (0, "{}"))[1]
        wx_name = name
        cond = tmpl.format(name)
        if wx_icon == "rain" and COVERAGE.get(c, (0,))[0] < 5:
            wx_icon = "showers"
        if wx_icon:
            icon = wx_icon
        if wx_icon == "fog" and pop < 15:
            cond = f"{sky_label}, {tmpl.format(name)}"
    max_gust = max(gust) if gust else None
    if icon not in PRECIP_ICONS and icon != "fog" and max_gust and max_gust >= 35:
        icon = "wind"
        cond = f"{sky_label} & Windy"

    return {
        "cond": cond, "icon": icon, "pop": round_pop(pop), "sky": rnd(sky_avg),
        "wx": wx_name, "wet_timing": timing_phrase(wet_hours),
        "temp_min": rnd(min(temps)) if temps else None,
        "temp_max": rnd(max(temps)) if temps else None,
        "qpf": round(qpf, 2), "snow": round(snow, 1),
        "gust": None if max_gust is None else int(5 * round(max_gust / 5)),  # gusts to nearest 5 mph
        "wind": rnd(sum(wspd) / len(wspd)) if wspd else None,
        "wind_dir": compass(sum(wdir) / len(wdir)) if wdir else None,
    }


def _period_value(periods, start, end, fn):
    hits = [v for s, e, v in periods if s < end.astimezone(s.tzinfo) and e > start.astimezone(s.tzinfo)]
    return rnd(fn(hits)) if hits else None


def qpf_range(q):
    if q < 0.05:
        return None
    if q < 0.25:
        return 'Under a quarter inch'
    steps = [(0.5, '0.25–0.5"'), (0.75, '0.5–0.75"'), (1.0, '0.75–1"'),
             (1.5, '1–1.5"'), (2.0, '1.5–2"'), (3.0, '2–3"'), (99, '3"+')]
    return next(t for lim, t in steps if q < lim)


def temp_word(high):
    return ("HOT" if high >= 92 else "WARM" if high >= 80 else "MILD" if high >= 65
            else "COOL" if high >= 50 else "COLD" if high >= 35 else "FRIGID")


def make_headline(d):
    parts = [temp_word(d["high"]) if d["high"] is not None else ""]
    if d["high"] and d["high"] >= 75 and (d["max_dew"] or 0) >= 68:
        parts[0] += " & HUMID"
    icon, pop = d["icon"], d["pop"] or 0
    t = d["day_timing"]
    ampm = "PM " if "afternoon" in t or "evening" in t else "AM " if "morning" in t else ""
    if icon == "tstorm" and pop >= 30:
        parts.append(f"{ampm if 'at times' not in t else ''}STORMS")
    elif icon in ("rain", "showers") and pop >= 50:
        parts.append("RAINY" if icon == "rain" else f"{ampm}SHOWERS")
    elif icon in ("rain", "showers", "tstorm") and pop >= 20:
        parts.append("A FEW SHOWERS")
    elif icon in ("snow", "mix"):
        parts.append("WINTRY MIX" if icon == "mix" else "SNOW")
    elif icon == "wind":
        parts.append("WINDY")
    else:
        parts.append(d["cond"].upper().replace("MOSTLY SUNNY", "LOTS OF SUN"))
    if (d["max_gust"] or 0) >= 30 and icon != "wind":
        parts.append("BREEZY")
    return ", ".join(p for p in parts if p)


def sentence(s):
    return s[:1].upper() + s[1:].lower() if s else s


def make_text(d, night_part):
    s = []
    lead = d["cond"] if d["icon"] not in PRECIP_ICONS else d.get("sky_cond", "Partly Cloudy")
    humid = " and humid" if (d["max_dew"] or 0) >= 68 and (d["high"] or 0) >= 75 else ""
    s.append(f"{sentence(lead)}{humid} with a high near {d['high']}°.")
    pop = d["pop"] or 0
    if d["icon"] in PRECIP_ICONS and pop >= 20:
        timing = f" {d['day_timing']}" if d["day_timing"] else ""
        s.append(f"{sentence(d['cond'])}{timing} ({pop}% chance).")
        r = qpf_range(d["qpf"] or 0)
        if r and (d["qpf"] or 0) >= 0.25 and d.get("qpf_src") == "ndfd":
            s.append(f"Rainfall: {r}.")
    if (d["max_hi"] or 0) >= 95:
        s.append(f"Heat index values up to {d['max_hi']}°.")
    if (d["max_gust"] or 0) >= 25:
        s.append(f"{d['wind_dir'] or ''} winds {d['wind_avg']} mph, gusting to {d['max_gust']}.".strip())
    if d.get("departure") is not None and abs(d["departure"]) >= 6:
        s.append(f"That's about {abs(d['departure'])}° {'above' if d['departure'] > 0 else 'below'} normal.")
    if night_part and d["low"] is not None:
        s.append(f"Tonight: {d['night_cond'].lower()}, low near {d['low']}°.")
    return " ".join(s)


def build_day(grid, date):
    tz = grid.tz
    d0 = datetime.combine(date, dtime(0), tz)
    day_s, day_e = d0 + 7 * HOUR, d0 + 19 * HOUR
    ngt_s, ngt_e = day_e, d0 + 31 * HOUR
    day = summarize_window(grid, day_s, day_e)
    ngt = summarize_window(grid, ngt_s, ngt_e, night=True)
    full = summarize_window(grid, d0, d0 + 24 * HOUR)
    high = _period_value(grid.max_t, day_s, day_e, max) or day["temp_max"]
    low = _period_value(grid.min_t, ngt_s + 2 * HOUR, ngt_e, min) or ngt["temp_min"]
    his = grid.series("heatIndex", d0, d0 + 24 * HOUR)
    wcs = grid.series("windChill", d0, d0 + 24 * HOUR) or \
        [v for v in grid.series("apparentTemperature", d0, d0 + 24 * HOUR) if v <= 50]
    dews = grid.series("dewpoint", day_s, day_e)
    nh, _ = normal_temps(date)
    sky_cond, _ = sky_words(day["sky"], False)
    qpf, qpf_src = grid.rain_total(d0, d0 + 24 * HOUR)
    d = {
        "date": date.isoformat(),
        "dow": date.strftime("%a").upper(), "dow_long": date.strftime("%A"),
        "date_label": f"{date.strftime('%b')} {date.day}",
        "high": high, "low": low,
        "cond": day["cond"], "sky_cond": sky_cond, "icon": day["icon"], "pop": day["pop"],
        "day_timing": day["wet_timing"],
        "night_cond": ngt["cond"], "night_icon": ngt["icon"], "night_pop": ngt["pop"],
        "qpf": None if qpf is None else round(qpf, 2), "qpf_src": qpf_src, "snow": full["snow"],
        "max_gust": full["gust"], "wind_avg": day["wind"], "wind_dir": day["wind_dir"],
        "max_hi": rnd(max(his)) if his else high,
        "min_wc": rnd(min(wcs)) if wcs else None,
        "max_dew": rnd(max(dews)) if dews else None,
        "departure": (high - round(nh)) if high is not None else None,
    }
    d["headline"] = make_headline(d)
    d["text"] = make_text(d, night_part=True)
    return d


def build_timeline(grid, date):
    tz = grid.tz
    d0 = datetime.combine(date, dtime(0), tz)
    rows = []
    for label, a, b, night in [("MORNING", 6, 12, False), ("AFTERNOON", 12, 18, False),
                               ("EVENING", 18, 24, True), ("OVERNIGHT", 24, 30, True)]:
        w = summarize_window(grid, d0 + a * HOUR, d0 + b * HOUR, night=night)
        if w["temp_min"] is None:
            continue
        rng = (f"{w['temp_min']}°" if w["temp_min"] == w["temp_max"]
               else f"{w['temp_min']}–{w['temp_max']}°")
        rng_word = "Temps" if label != "OVERNIGHT" else "Falling to"
        if label == "OVERNIGHT":
            rng = f"{w['temp_min']}°"
        text = f"{sentence(w['cond'])}. {rng_word} {rng}."
        if (w["pop"] or 0) >= 20:
            text += f" Rain chance {w['pop']}%."
        if (w["gust"] or 0) >= 25:
            text += f" Gusts to {w['gust']} mph."
        rows.append({"label": label, "text": text, "icon": w["icon"]})
    return rows


def build_hourly(grid, now, hours=24):
    out = []
    t0 = now.replace(minute=0, second=0, microsecond=0) + HOUR
    for i in range(hours):
        t = t0 + i * HOUR
        w = summarize_window(grid, t, t + HOUR, night=not (7 <= t.hour < 19))
        temp = grid.value_at("temperature", t)
        if temp is None:
            continue
        out.append({"time": t.isoformat(), "label": t.strftime("%I%p").lstrip("0"),
                    "temp": rnd(temp), "pop": round_pop(grid.pop_at(t)), "icon": w["icon"]})
    return out


def what_to_know(days, alerts, start_idx):
    """Rule-based talking points, ranked; top 4 are used."""
    items = []
    look = days[start_idx:start_idx + 4]
    if alerts:
        a = alerts[0]
        more = f" (+{len(alerts) - 1} more)" if len(alerts) > 1 else ""
        items.append((100, f"{a['event'].upper()}:", f"In effect {a['ends_label']}{more}."))
    storms = [d for d in look if d["icon"] == "tstorm" and (d["pop"] or 0) >= 30]
    if storms:
        d = storms[0]
        items.append((90, "STORMS:", f"{sentence(d['cond'])} {d['dow_long']} {d['day_timing']}. Rain chance {d['pop']}%."))
    snow = [d for d in look if (d["snow"] or 0) >= 0.1]
    if snow:
        tot = sum(d["snow"] for d in snow)
        items.append((95, "SNOW:", f"Around {tot:.1f}\" possible, mainly {snow[0]['dow_long']}."))
    rain3 = sum(d["qpf"] or 0 for d in look[:3] if d.get("qpf_src") in ("ndfd", "mixed"))
    if rain3 >= 0.25:
        wet = [d for d in look[:3] if (d["qpf"] or 0) >= 0.1]
        items.append((80, "RAIN TOTALS:", f"{qpf_range(rain3)} through {wet[-1]['dow_long'] if wet else 'midweek'}."))
    hi = max(look, key=lambda d: d["max_hi"] or 0)
    if (hi["max_hi"] or 0) >= 100:
        items.append((88, "HEAT:", f"Heat index up to {hi['max_hi']}° {hi['dow_long']}. Hydrate and limit time outdoors."))
    elif (hi["max_hi"] or 0) >= 95:
        items.append((65, "HEAT & HUMIDITY:", f"Feels-like temps in the upper 90s {hi['dow_long']}."))
    gd = max(look, key=lambda d: d["max_gust"] or 0)
    if (gd["max_gust"] or 0) >= 30:
        items.append((75, "WIND:", f"Gusts up to {gd['max_gust']} mph {gd['dow_long']}. Secure loose items."))
    cold = [d for d in look if d["low"] is not None and d["low"] <= 32]
    if cold:
        items.append((85, "FREEZE:", f"Lows near {cold[0]['low']}° {cold[0]['dow_long']} night. Protect pipes, plants & pets."))
    highs = [(d, d["high"]) for d in look if d["high"] is not None]
    for (a, ha), (b, hb) in zip(highs, highs[1:]):
        if ha - hb >= 8:
            items.append((60, "COOLDOWN:", f"Highs drop from {ha}° {a['dow_long']} to {hb}° {b['dow_long']}."))
            break
        if hb - ha >= 8:
            items.append((60, "WARMUP:", f"Highs jump from {ha}° {a['dow_long']} to {hb}° {b['dow_long']}."))
            break
    dews = [d for d in look if d["max_dew"] is not None]
    for a, b in zip(dews, dews[1:]):
        if a["max_dew"] >= 66 and b["max_dew"] <= 58:
            items.append((55, "HUMIDITY:", f"Much less humid starting {b['dow_long']}."))
            break
    dry = [d for d in days[start_idx:] if (d["pop"] or 0) < 20 and (d["night_pop"] or 0) < 20]
    if len(dry) >= 3:
        items.append((30, "DRY STRETCH:", f"{len(dry)} of the next {len(days) - start_idx} days look rain-free."))
    wk = [d for d in days[start_idx:] if d["dow"] in ("SAT", "SUN")][:2]
    if wk:
        items.append((35, "WEEKEND:", " | ".join(f"{d['dow'].title()}: {d['cond']}, {d['high']}°" for d in wk)))
    if len(items) < 4:
        d = days[start_idx]
        items.append((20, f"{d['dow_long'].upper()}:", d["text"].split(". ")[0] + "."))
    items.sort(key=lambda x: -x[0])
    return [{"label": l, "text": t} for _, l, t in items[:4]]


def parse_alerts(features, tz):
    out = []
    for f in features:
        p = f.get("properties", {})
        ends = p.get("ends") or p.get("expires")
        label = ""
        if ends:
            e = datetime.fromisoformat(ends).astimezone(tz)
            label = "until " + e.strftime("%I:%M %p %a").lstrip("0")
        out.append({"event": p.get("event", "Alert"), "severity": p.get("severity"),
                    "headline": p.get("headline") or "", "ends_label": label})
    order = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3}
    out.sort(key=lambda a: order.get(a["severity"], 4))
    return out


def parse_obs(obs, tz):
    if not obs:
        return None
    p = obs.get("properties", {})

    def v(k, conv=lambda x: x):
        x = (p.get(k) or {}).get("value")
        return None if x is None else conv(x)
    c2f = lambda c: rnd(c * 9 / 5 + 32)
    kmh = lambda k: rnd(k * 0.621371)
    temp = v("temperature", c2f)
    if temp is None:
        return None
    ts = datetime.fromisoformat(p["timestamp"]).astimezone(tz)
    feels = v("heatIndex", c2f) or v("windChill", c2f) or temp
    return {
        "time_label": ts.strftime("%I:%M %p").lstrip("0"), "temp": temp,
        "cond": p.get("textDescription") or "", "dewpoint": v("dewpoint", c2f),
        "humidity": v("relativeHumidity", rnd), "feels_like": feels,
        "wind_dir": compass(v("windDirection")), "wind": v("windSpeed", kmh),
        "gust": v("windGust", kmh),
        "pressure": v("barometricPressure", lambda pa: round(pa / 3386.39, 2)),
        "visibility": v("visibility", lambda m: round(m / 1609.34, 1)),
        "icon": _obs_icon(p.get("textDescription") or "", ts), "night": not (7 <= ts.hour < 19),
    }


def _obs_icon(text, ts):
    t = text.lower()
    night = not (7 <= ts.hour < 19)
    for key, icon in [("thunder", "tstorm"), ("snow", "snow"), ("freezing", "mix"),
                      ("rain", "rain"), ("drizzle", "rain"), ("shower", "showers"),
                      ("fog", "fog"), ("mist", "fog"), ("overcast", "cloudy"),
                      ("mostly cloudy", "mostly_cloudy"), ("partly", "partly"),
                      ("few", "few"), ("clear", "clear"), ("fair", "clear"), ("sunny", "clear")]:
        if key in t:
            return icon
    return "partly"


def build_package(grid, now, cfg, alerts_raw=None, obs_raw=None):
    tz = grid.tz
    first = now.date()
    days = []
    for i in range(8):
        date = first + timedelta(days=i)
        d0 = datetime.combine(date, dtime(0), tz)
        if grid.end and d0 + 12 * HOUR > grid.end:
            break
        days.append(build_day(grid, date))
    evening = now.hour >= cfg.get("evening_switch_hour", 15)
    target = 1 if evening else 0
    from . import alertinfo
    alerts = alertinfo.parse(alerts_raw or [], tz, cfg)
    loc = cfg["location"]
    return {
        "source": "NWS NDFD",
        "location": {"name": loc["name"], "short": loc["short"], "station": loc["station"],
                     "area": loc.get("area", "Hampton Roads Area")},
        "issued": now.isoformat(),
        "issued_label": now.strftime("%I:%M %p %a %b ").lstrip("0") + str(now.day),
        "ndfd_updated": grid.update_time,
        "evening_mode": evening,
        "today": {"day_index": target,
                  "title": "TOMORROW'S FORECAST" if evening else "TODAY'S FORECAST",
                  "timeline": build_timeline(grid, first + timedelta(days=target))},
        "days": days,
        "what_to_know": what_to_know(days, [a for a in alerts if a.get("affects_home", True)], target),
        "hourly": build_hourly(grid, now),
        "commute": build_commute(grid, now, cfg),
        "weekend": build_weekend(grid, now, days),
        "current": parse_obs(obs_raw, tz),
        "alerts": alerts,
        "rain_guidance": {"ndfd_through": grid.qpf_end.astimezone(tz).isoformat() if grid.qpf_end else None,
                          "model": grid.ext_model},
    }


def _vis_min(grid, a, b):
    v = grid.series("visibility", a, b) if "visibility" in grid.h else []
    return min(v) if v else None


def build_commute(grid, now, cfg):
    """Next two drive windows (AM 6-9, PM 4-7): conditions, temps, rain, wind, fog, sun glare."""
    from .extras_data import sun_times
    tz, loc = grid.tz, cfg["location"]
    wins = []
    for dd in range(0, 3):
        d = now.date() + timedelta(days=dd)
        for label, a, b in (("MORNING COMMUTE", 6, 9), ("EVENING COMMUTE", 16, 19)):
            s = datetime.combine(d, dtime(a), tz)
            e = datetime.combine(d, dtime(b), tz)
            if e <= now + timedelta(minutes=30):
                continue
            w = summarize_window(grid, s, e, night=False)
            if w["temp_min"] is None:
                continue
            rise, sset = sun_times(d, loc["lat"], loc["lon"], tz)
            glare = None
            if (w["sky"] or 100) < 60:
                if label.startswith("MORNING") and rise and s - timedelta(minutes=30) <= rise <= e:
                    glare = "Sun glare for eastbound drivers after sunrise"
                if label.startswith("EVENING") and sset and s <= sset <= e + timedelta(minutes=30):
                    glare = "Sun glare for westbound drivers near sunset"
            notes = []
            if (w["pop"] or 0) >= 30:
                notes.append(f"Rain chance {w['pop']}%: allow extra time, wet roads")
            if w.get("wx") and "Fog" in (w["wx"] or ""):
                notes.append("Fog could cut visibility")
            if (w["gust"] or 0) >= 30:
                notes.append(f"Gusty winds to {w['gust']} mph on bridges and the HRBT/MMMBT")
            if w["temp_min"] is not None and w["temp_min"] <= 32 and (w["pop"] or 0) >= 20:
                notes.append("Watch for icy spots on bridges and overpasses")
            if glare:
                notes.append(glare)
            if not notes:
                notes.append("No weather issues expected")
            day = "TODAY" if d == now.date() else "TOMORROW" if d == now.date() + timedelta(days=1) else d.strftime("%A").upper()
            wins.append({"label": label, "day": day, "when": f"{a % 12 or 12}–{b % 12 or 12} {'AM' if a < 12 else 'PM'}",
                         "cond": w["cond"], "icon": w["icon"], "temp_min": w["temp_min"], "temp_max": w["temp_max"],
                         "pop": w["pop"], "gust": w["gust"], "notes": notes,
                         "rating": "GOOD" if notes == ["No weather issues expected"] else
                         ("SLOW" if any("Rain" in n or "Fog" in n or "icy" in n for n in notes) else "OK")})
            if len(wins) == 2:
                return wins
    return wins


def build_weekend(grid, now, days):
    """Sat/Sun split into morning/afternoon/evening with 'good for' tags."""
    tz = grid.tz
    today = now.date()
    sat = today + timedelta(days=(5 - today.weekday()) % 7)
    if today.weekday() == 6:
        sat = today - timedelta(days=1)
    out = []
    for d in (sat, sat + timedelta(days=1)):
        if d < today:
            continue
        info = next((x for x in days if x["date"] == d.isoformat()), None)
        if not info:
            continue
        d0 = datetime.combine(d, dtime(0), tz)
        parts = []
        for label, a, b, night in (("MORNING", 7, 12, False), ("AFTERNOON", 12, 17, False), ("EVENING", 17, 22, True)):
            w = summarize_window(grid, d0 + a * HOUR, d0 + b * HOUR, night=night)
            if w["temp_min"] is None:
                continue
            parts.append({"label": label, "cond": w["cond"], "icon": w["icon"], "pop": w["pop"],
                          "temp": w["temp_max"] if not night else w["temp_min"]})
        hi, pop, gust = info.get("high") or 0, info.get("pop") or 0, info.get("max_gust") or 0
        tags = []
        if hi >= 78 and pop < 30 and gust < 25:
            tags.append("BEACH")
        if 50 <= hi <= 88 and pop < 30:
            tags.append("YARD WORK")
        if pop < 25 and gust < 30:
            tags.append("OUTDOOR PLANS")
        if gust < 20 and pop < 30:
            tags.append("BOATING")
        if pop >= 50:
            tags.append("INDOOR DAY")
        out.append({"day": d.strftime("%A").upper(), "date_label": info["date_label"], "high": info["high"],
                    "low": info["low"], "cond": info["cond"], "icon": info["icon"], "pop": info["pop"],
                    "parts": parts, "tags": tags or ["MIXED BAG"]})
    return out


def caption(pkg):
    """Facebook-ready post text."""
    d = pkg["days"][pkg["today"]["day_index"]]
    loc = pkg["location"]
    lines = [f"{EMOJI.get(d['icon'], '')} {loc.get('area', loc['short'])} Forecast — {d['dow_long']}, {d['date_label']}",
             "", d["headline"].title().replace("Pm ", "PM ").replace("Am ", "AM "), d["text"], "", "7-DAY:"]
    start = 1 if pkg.get("evening_mode") else 0
    for x in pkg["days"][start:start + 7]:
        pop = f" · {x['pop']}%" if (x["pop"] or 0) >= 20 else ""
        lines.append(f"{x['dow'].title()}: {EMOJI.get(x['icon'], '')} {x['high']}°/{x['low']}° {x['cond']}{pop}")
    if pkg["what_to_know"]:
        lines += ["", "WHAT TO KNOW:"] + [f"• {w['label'].rstrip(':').title()}: {w['text']}" for w in pkg["what_to_know"]]
    return "\n".join(lines)
