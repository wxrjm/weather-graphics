"""Output folder layout.

"category" (default): output/<run>/<NN Category>/<Size>/<name>.png   e.g. "04 Rain & Flooding/Square/wpc_qpf_3day_big.png"
"flat"    (old):      output/<run>/<name>.png (wide), vertical/, post/, square/, Tropical/
Pick with config "output_layout". The same layout is mirrored into output/latest_rickywx.
"""
import re

CATEGORIES = [  # (folder, test on the graphic name with _full/_big removed) - first match wins
    ("01 Forecast", lambda n: n in ("daily", "what_to_know", "7day", "hourly", "current", "commute", "weekend",
                                    "holiday_countdown")),
    ("02 Severe & Alerts", lambda n: n.startswith(("spc_", "alert", "weather_aware", "warning_count"))),
    ("03 Temperature", lambda n: n.startswith(("feels_like", "wind_chill", "dewpoints", "above_average", "record_watch",
                                               "first_freeze", "frost_"))),
    ("04 Rain & Flooding", lambda n: n.startswith(("rain_totals", "wpc_qpf", "ero_", "ffg_", "rain_reports",
                                                   "storm_rain_reports", "river"))),
    ("05 Snow & Ice", lambda n: n.startswith(("snow", "ice_", "wssi", "storm_snow_reports"))),
    ("06 Wind", lambda n: n in ("wind", "wind_map", "gust_map", "storm_wind_reports")),
    ("07 Tides & Coast", lambda n: n.startswith(("tides", "high_tides", "tidal_flood", "beach"))),
    ("08 Tropical", lambda n: n.startswith(("tropics", "Tropical/"))),
    ("09 Long Range", lambda n: n.startswith("cpc_")),
    ("10 Climate & Drought", lambda n: n in ("yesterday", "month_rain", "drought")),
    ("11 Air Quality & Sun", lambda n: n in ("air_quality", "sun_uv")),
    ("12 Aviation", lambda n: n == "aviation"),
    ("13 More", lambda n: True),
]
SIZES = {"wide": "Wide", "vertical": "Vertical", "post": "Post", "square": "Square"}
SIZE_KEYS = {v: k for k, v in SIZES.items()}


def base_name(name):
    return re.sub(r"_(full|big)$", "", name)


def category(name):
    b = base_name(name)
    return next(folder for folder, test in CATEGORIES if test(b))


def path_for(out_dir, name, fmt, cfg):
    """Where graphic `name` (may start with "Tropical/") in format `fmt` is saved."""
    if (cfg.get("output_layout") or "category") == "flat":
        if name.startswith("Tropical/"):
            return out_dir / "Tropical" / ("" if fmt == "wide" else fmt) / f"{name.split('/', 1)[1]}.png"
        return (out_dir if fmt == "wide" else out_dir / fmt) / f"{name}.png"
    leaf = name.split("/", 1)[1] if name.startswith("Tropical/") else name
    return out_dir / category(name) / SIZES.get(fmt, fmt) / f"{leaf}.png"
