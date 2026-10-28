"""Output folder layout.

"category" (default): output/<run>/<Category>/<name>.png for wide, plus Vertical/, Post/, Square/ inside each category
                      e.g. "Rain & Flooding/3 Day Rainfall Potential.png", "Rain & Flooding/Square/3 Day Rainfall Potential Big Text.png"
"flat"    (old):      output/<run>/<name>.png (wide), vertical/, post/, square/, Tropical/
Pick with config "output_layout". The same layout is mirrored into output/latest_rickywx.
"""
import re

CATEGORIES = [  # (folder, test on the graphic name with _full/_big removed) - first match wins
    ("Holidays", lambda n: n == "holiday_countdown" or n.endswith("_forecast")),
    ("Forecast", lambda n: n in ("daily", "what_to_know", "7day", "hourly", "current", "commute", "weekend",
                                    "holiday_countdown", "rain_timing", "sunset_quality", "precip_timeline", "today_vs_tomorrow", "what_to_expect") or n.startswith(("fronts_", "city_table"))),
    ("Safety Graphics", lambda n: n.startswith("safety_")),
    ("SPC Outlooks", lambda n: n.startswith(("spc_", "state_spc"))),
    ("Severe & Alerts", lambda n: n.startswith(("nadocast", "alert", "weather_aware", "warning_count"))),
    ("Temperature", lambda n: n.startswith(("feels_like", "wind_chill", "dewpoints", "above_average", "below_average", "record_watch",
                                               "first_freeze", "frost_", "freeze_", "temp_drop", "state_highs", "state_lows", "state_dew", "state_frost", "hr_highs", "hr_lows", "degree_days", "temp_vs_normal"))),
    ("Rain & Flooding", lambda n: n.startswith(("rain_totals", "wpc_qpf", "ero_", "state_qpf", "state_ero", "obs_rain", "state_pop", "ffg_", "rain_reports",
                                                   "storm_rain_reports", "river"))),
    ("Snow & Ice", lambda n: n.startswith(("snow", "state_snow", "ice_", "wssi", "storm_snow_reports"))),
    ("Wind", lambda n: n.startswith(("state_wind", "state_gust")) or n in ("wind", "wind_map", "gust_map", "storm_wind_reports", "gust_table_48", "gust_peaks", "gust_bars_48", "gust_bars_48_dir", "outage_risk")),
    ("Tides & Coast", lambda n: n.startswith(("tides", "tide_error", "high_tides", "tidal_flood", "beach", "sound_flood"))),
    ("Tropical", lambda n: n.startswith(("tropics", "Tropical/"))),
    ("Long Range", lambda n: n.startswith("cpc_")),
    ("Climate & Drought", lambda n: n in ("yesterday", "month_rain", "drought", "drought_stencil")),
    ("Air Quality & Sun", lambda n: n in ("air_quality", "sun_uv", "aurora")),
    ("Aviation", lambda n: n == "aviation"),
    ("More", lambda n: True),
]
SIZES = {"wide": "Wide", "vertical": "Vertical", "post": "Post", "square": "Square"}
SIZE_KEYS = {v: k for k, v in SIZES.items()}


ACRONYMS = {"spc", "ero", "qpf", "wpc", "ndfd", "cpc", "ffg", "uv", "nws", "va", "nc", "hrbt", "mmmbt", "wssi", "nhc", "aqi",
            "ahps", "obx", "nao", "enso", "dma", "orf", "cwg", "oem", "mrms", "pm", "am", "id", "tv"}
WORDS = {"obs": "Observed", "pop": "Rain Chance", "dew": "Dew Points", "gust": "Gusts", "gusts": "Gusts", "hr": "Hampton Roads",
         "wx": "Weather", "temps": "Temperatures", "temp": "Temperature", "ero": "Excessive Rain", "feels": "Feels", "wo": "With",
         "d8": "Days 8-14", "d3": "Days 3-7", "tidal": "Tidal", "t": ""}
SMALL = {"of", "and", "vs", "to", "the", "in", "for", "at", "on"}
RAW_PREFIX = ("alert_", "river_")  # kept lower-case with their number so OBS can still find alert_1.png ... via the latest-folder rename


TITLES = {
    "spc_tornado_day1": "SPC Day 1 Tornado Outlook", "spc_wind_day1": "SPC Day 1 Damaging Wind Outlook", "spc_hail_day1": "SPC Day 1 Large Hail Outlook", "spc_tornado_day2": "SPC Day 2 Tornado Outlook", "spc_wind_day2": "SPC Day 2 Damaging Wind Outlook", "spc_hail_day2": "SPC Day 2 Large Hail Outlook", "spc_3panel_day1": "SPC Day 1 Severe Risks Hampton Roads 3 Panel", "spc_3panel_day2": "SPC Day 2 Severe Risks Hampton Roads 3 Panel", 
    "precip_timeline": "Precipitation Timeline", "today_vs_tomorrow": "Today vs Tomorrow Morning", "what_to_expect": "What To Expect",
    "safety_hurricane_hunters": "Hurricane Hunters Plane Comparison", "safety_urban_flooding": "Urban Area Flooding",
    "safety_high_risk_damage": "High Risk Days Flood Damage", "safety_flood_risk_levels": "Flood Risk Levels",
    "safety_tire_pressure": "Tire Pressure Dropping", "safety_freezing_rain": "Freezing Rain Setup", "safety_wind_impacts": "Wind Impacts",
    "safety_how_hail_forms": "How Hail Forms", "safety_severe_risk_levels": "Severe Weather Risk Levels",
    "safety_tornado_safety": "Tornado Safety",  # whole-name / prefix overrides for the graphics whose snake_case doesn't title-case well
    "tide_error": "Tide Forecast Check", "snow_probability": "Snow Probability", "temp_vs_normal": "Above or Below Average", "outage_risk": "Power Outage Risk", "sun_uv": "Sun & UV", "city_table": "City Forecast Table",
    "obs_rain": "Observed Rainfall", "gust_bars_48": "48 Hour Gust Bars", "gust_bars_48_dir": "48 Hour Gust Bars With Wind Direction", "gust_table_48": "48 Hour Gust Table",
    "gust_peaks": "Peak Gusts", "cpc_8_14": "CPC 8-14 Day", "cpc_3_7": "CPC 3-7 Day", "sound_flood": "Sound Side Flooding",
    "what_to_know": "What to Know", "weather_aware": "Be Weather Aware", "feels_like": "Heat Index", "month_rain": "Rainfall So Far",
    "yesterday": "Climate Report", "state_spc_day4_8": "SPC Day 4-8 Severe Outlook", "drought_stencil": "Drought Monitor VA NC Stencil", "drought": "Drought Monitor", "temp_drop": "Temperature Drop", "wpc_qpf": "Rainfall Potential",
}


def pretty(name):
    """'obs_rain_24hr_state_full' -> 'Observed Rain 24 Hour State Full Screen': Title Case with spaces, ready to share.
    Config "pretty_filenames": false keeps the old snake_case names."""
    name = re.sub(r"^(T_)?\d+_", "", name)  # hurricane-set order numbers ("05_wind_chances") are dropped from the title
    suffix = ""
    for tag, label in (("_full", " Full Screen"), ("_big", " Big Text")):
        if name.endswith(tag):
            name, suffix = name[: -len(tag)], label
    m = re.fullmatch(r"wpc_qpf_(\d+)day(_.+)?", name)  # WPC rainfall: "3 Day Rainfall Potential" (+ " State")
    if m:
        name = f"{m.group(1)}_day_rainfall_potential{m.group(2) or ''}"
    m = re.fullmatch(r"wpc_qpf_day(\d+)(_.+)?", name)
    if m:
        name = f"day_{m.group(1)}_rainfall_potential{m.group(2) or ''}"
    m = re.fullmatch(r"wpc_qpf_d(\d+)_(\d+)(_.+)?", name)
    if m:
        name = f"day_{m.group(1)}-{m.group(2)}_rainfall_potential{m.group(3) or ''}"
    out = []
    head = ""
    for k in sorted(TITLES, key=len, reverse=True):  # longest prefix wins: "obs_rain_24hr" -> "Observed Rainfall" + rest
        if name == k or name.startswith(k + "_"):
            head, name = TITLES[k], name[len(k) + 1:]
            break
    if head:
        out.append(head)
    for i, w in enumerate(name.split("_") if name else []):
        lw = w.lower()
        m = re.fullmatch(r"(\d+)(day|days|hr|hrs|hour|hours|min|mm|in)", lw)
        if lw == "7day":
            out.append("7-Day")
        elif lw == "rain" and i == 0 and name.startswith("rain_"):
            out.append("Rain")
        elif m:
            unit = {"day": "Day", "days": "Day", "hr": "Hour", "hrs": "Hour", "hour": "Hour", "hours": "Hour", "min": "Min"}.get(m.group(2))
            out.append(f"{m.group(1)} {unit}" if unit else w)
        elif re.fullmatch(r"day\d+", lw):
            out.append("Day " + lw[3:])
        elif lw in WORDS:
            if WORDS[lw]:
                out.append(WORDS[lw])
        elif lw in ACRONYMS:
            out.append(lw.upper())
        elif lw in SMALL and i:
            out.append(lw)
        else:
            out.append(w[:1].upper() + w[1:])
    return (" ".join(out) + suffix).strip()


def file_stem(name, cfg):
    return name if cfg.get("pretty_filenames") is False else pretty(name)


def base_name(name):
    return re.sub(r"_(full|big)$", "", name)


def category(name):
    b = base_name(name)
    return next(folder for folder, test in CATEGORIES if test(b))


def path_for(out_dir, name, fmt, cfg):
    """Where graphic `name` (may start with "Tropical/") in format `fmt` is saved."""
    if (cfg.get("output_layout") or "category") == "flat":
        if name.startswith("Tropical/"):
            return out_dir / "Tropical" / ("" if fmt == "wide" else fmt) / f"{file_stem(name.split('/', 1)[1], cfg)}.png"
        return (out_dir if fmt == "wide" else out_dir / fmt) / f"{file_stem(name, cfg)}.png"
    leaf = file_stem(name.split("/", 1)[1] if name.startswith("Tropical/") else name, cfg)
    if fmt == "wide":  # wide sits right in the category folder so it's the first thing you see
        return out_dir / category(name) / f"{leaf}.png"
    return out_dir / category(name) / SIZES.get(fmt, fmt) / f"{leaf}.png"
