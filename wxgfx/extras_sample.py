"""Offline sample inputs in each source's REAL format, pushed through the same parsers as live data."""
import math
import random
from datetime import date, datetime, timedelta, timezone

from . import extras_data as X

CLI_TEXT = """
000
CDUS41 KAKQ 300531
CLIORF

CLIMATE REPORT
NATIONAL WEATHER SERVICE WAKEFIELD VA
131 AM EDT WED SEP 30 2026

...................................

...THE NORFOLK VA CLIMATE SUMMARY FOR SEPTEMBER 29 2026...

CLIMATE NORMAL PERIOD: 1991 TO 2020
CLIMATE RECORD PERIOD: 1874 TO 2026


WEATHER ITEM   OBSERVED TIME   RECORD YEAR NORMAL DEPARTURE LAST
                VALUE   (LST)  VALUE       VALUE  FROM      YEAR
                                                  NORMAL
...................................................................
TEMPERATURE (F)
 YESTERDAY
  MAXIMUM         89    242 PM  93    1986  78     11       80
  MINIMUM         71    623 AM  45    1888  63      8       66
  AVERAGE         80                        71      9       73

PRECIPITATION (IN)
  YESTERDAY        0.12          2.87 1924   0.13  -0.01     0.00
  MONTH TO DATE    3.18                      4.36  -1.18     5.02
  SINCE SEP 1      3.18                      4.36  -1.18     5.02
  SINCE JAN 1     38.44                     37.86   0.58    41.20

SNOWFALL (IN)
  YESTERDAY        0.0           0.0  2025   0.0    0.0      0.0
"""

CLI_TODAY_TEXT = """
000
CDUS41 KAKQ 302131
CLIORF

CLIMATE REPORT
NATIONAL WEATHER SERVICE WAKEFIELD VA
531 PM EDT WED SEP 30 2026

...................................

...THE NORFOLK VA CLIMATE SUMMARY FOR SEPTEMBER 30 2026...
VALID TODAY AS OF 0500 PM LOCAL TIME.

CLIMATE NORMAL PERIOD: 1991 TO 2020
CLIMATE RECORD PERIOD: 1874 TO 2026


WEATHER ITEM   OBSERVED TIME   RECORD YEAR NORMAL DEPARTURE LAST
                VALUE   (LST)  VALUE       VALUE  FROM      YEAR
                                                  NORMAL
...................................................................
TEMPERATURE (F)
 TODAY
  MAXIMUM         84    147 PM  94    1986  77      7       79
  MINIMUM         70    641 AM  44    1888  62      8       65
  AVERAGE         77                        70      7       72

PRECIPITATION (IN)
  TODAY            0.31          2.10 1945   0.13   0.18     0.00
  MONTH TO DATE    3.49                      4.49  -1.00     5.02
  SINCE SEP 1      3.49                      4.49  -1.00     5.02
  SINCE JAN 1     38.75                     37.99   0.76    41.20

SNOWFALL (IN)
  TODAY            0.0           0.0  2025   0.0    0.0      0.0
"""

def _tidal_sample(cfg, now, base):
    """Storm surge building to moderate flooding around Norfolk, major on the bayside Eastern Shore."""
    out = []
    for site in X.tidal_map_sites(cfg):
        if site.get("lat") is None:
            continue
        lat, lon = site["lat"], site["lon"]
        surge = 1.9 + 1.1 * max(0, (lat - 36.9)) * 2.2 * (1 if lon > -76.15 else 0.35) + (0.5 if lon < -76.5 else 0)
        st = {"action": 4.0, "minor": 4.5, "moderate": 5.5, "major": 6.5}
        lag = (abs(lon + 76.0) * 2.0)
        series = [(base + timedelta(minutes=30 * k),
                   1.4 + surge * min(1, k / 40) + 1.35 * math.cos(2 * math.pi * (k / 2 - 4.2 - lag) / 12.42))
                  for k in range(0, 60 * 2)]
        out.append({"name": site["name"], "lid": site.get("nwps"), "stages": st, "source": "NWS forecast",
                    "lat": lat, "lon": lon,
                    "highs": [{"time": t, "ft": round(v, 1), "cat": X.flood_category(v, st)} for t, v in X.find_highs(series, now, n=4)]})
    return out


def _aq_sample(now):
    d0, d1 = now.strftime("%m/%d/%y"), (now + timedelta(days=1)).strftime("%m/%d/%y")
    disc = ("Southerly flow and plenty of sunshine will allow ozone to build into the Moderate range this afternoon. "
            "A cold front Thursday brings cleaner air for the end of the week.")
    return "\n".join([
        f"{d0}|{d0}|19:00|EDT|-1|O|Y|Hampton Roads|VA|36.8500|-76.2900|OZONE|47|Good|No||Virginia DEQ",
        f"{d0}|{d0}|19:00|EDT|-1|O|N|Hampton Roads|VA|36.8500|-76.2900|PM2.5|31|Good|No||Virginia DEQ",
        f"{d0}|{d0}||EDT|0|F|Y|Hampton Roads|VA|36.8500|-76.2900|OZONE|62|Moderate|No|{disc}|Virginia DEQ",
        f"{d0}|{d1}||EDT|1|F|Y|Hampton Roads|VA|36.8500|-76.2900|OZONE|-1|Good|No|{disc}|Virginia DEQ",
        f"{d0}|{d0}|19:00|EDT|-1|O|Y|Richmond|VA|37.5400|-77.4400|OZONE|55|Moderate|No||Virginia DEQ",
    ])


SRF_TEXT = """
SRFAKQ

Surf Zone Forecast
National Weather Service Wakefield VA
400 AM EDT Wed Sep 30 2026

VAZ098-302000-
Virginia Beach-
400 AM EDT Wed Sep 30 2026

.TODAY...
Rip Current Risk*...........Moderate.
Surf Height.................2 to 3 feet.
Water Temperature...........73 degrees.
Weather.....................Mostly sunny.
Max UV Index................6.

.TONIGHT...
Rip Current Risk*...........Moderate.

$$

NCZ102-302000-
Northern Outer Banks-
Including the beaches of Corolla and Duck
400 AM EDT Wed Sep 30 2026

.TODAY...
Rip Current Risk*...........High.
Surf Height.................3 to 4 feet.
Water Temperature...........75 degrees.
Max UV Index................6.

$$

VAZ099-100-302000-
Accomack-Northampton-
400 AM EDT Wed Sep 30 2026

.TODAY...
Rip Current Risk*...........Low.
Surf Height.................1 to 2 feet.
Water Temperature...........71 degrees.

$$
"""

CWF_TEXT = """
CWFAKQ

Coastal Waters Forecast for Virginia and North Carolina
National Weather Service Wakefield VA
400 AM EDT Wed Sep 30 2026

ANZ632-302000-
Chesapeake Bay from New Point Comfort to Little Creek VA-
400 AM EDT Wed Sep 30 2026

.TODAY...SW winds 10 to 15 kt. Waves 1 to 2 ft.
.TONIGHT...SW winds 10 to 15 kt, increasing to 15 to 20 kt after midnight. Waves 2 ft.
.THU...SW winds 15 to 20 kt with gusts up to 25 kt. Waves 2 to 3 ft.

$$

ANZ634-302000-
Chesapeake Bay from Little Creek VA to Cape Henry VA including the Chesapeake Bay Bridge Tunnel-
400 AM EDT Wed Sep 30 2026

.TODAY...SW winds 10 to 15 kt. Waves 1 to 2 ft.
.TONIGHT...SW winds 15 kt. Waves 2 ft.

$$

ANZ656-302000-
Coastal waters from Cape Charles Light to Virginia-North Carolina border out to 20 nm-
400 AM EDT Wed Sep 30 2026

.TODAY...S winds 10 to 15 kt. Seas 3 to 4 ft.
.TONIGHT...SW winds 15 to 20 kt. Seas 3 to 5 ft.

$$
"""


def _tides_raw(now, tz):
    """Semi-diurnal tide ~ Sewells Point (range ~2.8 ft about MSL 1.5 ft MLLW)."""
    start = datetime.combine(now.date(), datetime.min.time(), tz)
    hourly, hilo = [], []
    f = lambda h: 1.55 + 1.45 * math.cos(2 * math.pi * (h - 4.2) / 12.42) + 0.12 * math.cos(2 * math.pi * h / 24.8)
    for i in range(110):
        t = start + timedelta(hours=i)
        hourly.append({"t": t.strftime("%Y-%m-%d %H:%M"), "v": f"{f(i):.3f}"})
    for i in range(110 * 10):
        h = i / 10
        a, b, c = f(h - 0.1), f(h), f(h + 0.1)
        if (b > a and b >= c) or (b < a and b <= c):
            hilo.append({"t": (start + timedelta(hours=h)).strftime("%Y-%m-%d %H:%M"), "v": f"{b + 0.9:.3f}",
                         "type": "H" if b > a else "L"})
    obs = [{"t": (now - timedelta(minutes=6 * k)).strftime("%Y-%m-%d %H:%M"),
            "v": f"{f((now - timedelta(minutes=6 * k) - start).total_seconds() / 3600) + 0.9:.3f}"} for k in range(60)][::-1]
    return {"predictions": hilo}, {"predictions": [{"t": x["t"], "v": f"{float(x['v']) + 0.9:.3f}"} for x in hourly]}, {"data": obs}


def _acis_rows(today):
    rnd = random.Random(7)
    rows = []
    d = date(1874, 1, 1)
    while d <= today:
        doy = d.timetuple().tm_yday
        mx = 69.8 + 20.2 * math.cos(2 * math.pi * (doy - 203) / 365.25) + rnd.gauss(0, 7)
        mn = 53.2 + 19.8 * math.cos(2 * math.pi * (doy - 208) / 365.25) + rnd.gauss(0, 7)
        rows.append([d.isoformat(), f"{mx:.0f}", f"{mn:.0f}"])
        d += timedelta(days=1)
    norm = []
    for k in range(11):
        dd = today + timedelta(days=k)
        doy = dd.timetuple().tm_yday
        norm.append([dd.isoformat(), f"{69.8 + 20.2 * math.cos(2 * math.pi * (doy - 203) / 365.25):.0f}",
                     f"{53.2 + 19.8 * math.cos(2 * math.pi * (doy - 208) / 365.25):.0f}"])
    return rows, norm


def build(cfg, now, tz):
    loc = cfg["location"]
    hilo, hourly, obs = _tides_raw(now, tz)
    nws_fcst = [(X._local(p["t"], tz), float(p["v"]) + 0.8) for p in hourly.get("predictions", [])
                if now <= X._local(p["t"], tz) <= now + timedelta(hours=66)]  # official-style forecast: tide + 0.8 ft surge
    tides = X.parse_tides(hilo, hourly, obs, {"action": 4.0, "minor": 4.5, "moderate": 5.5, "major": 6.5},
                          nws_fcst, cfg, now, tz)
    uv_rows = [{"DATE_TIME": (datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=h)).strftime("%b/%d/%Y %I %p").upper(),
                "UV_VALUE": max(0, round(6.4 * math.sin(math.pi * (h - 7) / 12)))} for h in range(6, 21)]
    rows, norm = _acis_rows(now.date())
    metar = {"rawOb": "KORF 301651Z 21012G20KT 10SM FEW035 SCT250 29/21 A2998 RMK AO2 SLP152",
             "obsTime": int((now - timedelta(minutes=12)).timestamp()), "temp": 29, "dewp": 21, "wdir": 210, "wspd": 12,
             "wgst": 20, "visib": "10+", "altim": 1015.4, "clouds": [{"cover": "FEW", "base": 3500}, {"cover": "SCT", "base": 25000}]}
    t0 = int(now.replace(minute=0, second=0).timestamp())
    taf = {"rawTAF": "TAF KORF 301720Z 3018/0124 21012G20KT P6SM FEW040 FM010000 22008KT P6SM SCT040 "
                     "FM011000 23006KT 5SM BR BKN015 FM011400 24010KT P6SM SCT030",
           "fcsts": [{"timeFrom": t0 + 3600, "timeTo": t0 + 8 * 3600, "wdir": 210, "wspd": 12, "wgst": 20, "visib": "6+",
                      "clouds": [{"cover": "FEW", "base": 4000}]},
                     {"timeFrom": t0 + 8 * 3600, "timeTo": t0 + 17 * 3600, "fcstChange": "FM", "wdir": 220, "wspd": 8,
                      "visib": "6+", "clouds": [{"cover": "SCT", "base": 4000}]},
                     {"timeFrom": t0 + 17 * 3600, "timeTo": t0 + 21 * 3600, "fcstChange": "FM", "wdir": 230, "wspd": 6,
                      "visib": 5, "wxString": "BR", "clouds": [{"cover": "BKN", "base": 1500}]},
                     {"timeFrom": t0 + 21 * 3600, "timeTo": t0 + 31 * 3600, "fcstChange": "FM", "wdir": 240, "wspd": 10,
                      "visib": "6+", "clouds": [{"cover": "SCT", "base": 3000}]}]}
    ell = lambda cx, cy, rx, ry: [[[cx + rx * math.cos(a / 20 * math.pi), cy + ry * math.sin(a / 20 * math.pi)] for a in range(41)]]
    tropics = {"storms": [{"name": "Kirk", "class": "HU", "wind_kt": 90, "pressure": 968, "lat": 24.8, "lon": -58.2,
                           "move": "NNW", "move_mph": 12, "id": "al112026"}],
               "areas": [{"polys": [ell(-38, 13, 6, 3)], "chance2": 20, "chance7": 60, "risk": "Medium"},
                         {"polys": [ell(-80, 26.5, 3.5, 2)], "chance2": 0, "chance7": 20, "risk": "Low"}],
               "cones": [{"name": "Kirk", "polys": [[[[-58.2, 24.8], [-60.5, 28], [-62, 32], [-60.5, 36.5], [-55, 38], [-52.5, 34],
                                                       [-55.5, 30], [-57, 27], [-58.2, 24.8]]]]}]}
    base = datetime.combine(now.date(), datetime.min.time(), tz)
    hts, hts2 = [], []
    for name, lag, amp, bump, st in (("Sewells Point", 0.0, 1.45, 0.9, (4.0, 4.5, 5.5, 6.5)),
                                     ("Yorktown", 0.6, 1.25, 1.0, (3.5, 4.0, 5.0, 6.0)),
                                     ("Jamestown", 2.4, 1.05, 1.3, (3.5, 4.0, 5.0, 6.0)),
                                     ("Lynnhaven Inlet", -0.4, 1.35, 1.2, (3.6, 4.1, 5.1, 6.1)),
                                     ("Nassawadox", 1.1, 1.3, 1.4, (3.8, 4.3, 5.3, 6.3)),
                                     ("Kiptopeke", 0.8, 1.3, 1.0, (4.0, 4.5, 5.5, 6.5)),
                                     ("Hudgins", 1.6, 1.0, 1.1, (3.5, 4.0, 5.0, 6.0)),
                                     ("Smithfield", 3.0, 1.1, 1.5, (4.0, 4.5, 5.5, 6.5)),
                                     ("Suffolk", 1.9, 1.5, 1.8, (4.5, 5.0, 6.0, 7.0)),
                                     ("Money Point", 0.3, 1.5, 1.2, (4.5, 5.0, 6.0, 7.0))):
        series = [(base + timedelta(minutes=30 * k),
                   1.55 + bump + amp * math.cos(2 * math.pi * (k / 2 - 4.2 - lag) / 12.42) + 0.1 * math.cos(2 * math.pi * k / 2 / 24.8))
                  for k in range(0, 60 * 2)]
        stg = dict(zip(("action", "minor", "moderate", "major"), st))
        (hts if len(hts) < 5 else hts2).append({"name": name, "lid": None, "stages": stg, "source": "NWS forecast",
                    "highs": [{"time": t, "ft": round(v, 1), "cat": X.flood_category(v, stg)} for t, v in X.find_highs(series, now)]})
    return {
        "high_tides": hts,
        "high_tides_2": hts2,
        "tidal_map": _tidal_sample(cfg, now, base),
        "aqi": X.merge_aqi(X.parse_reportingarea(_aq_sample(now), cfg),
                           {"current": None, "days": {(now.date() + timedelta(days=k)).isoformat():
                                                       {"date": (now.date() + timedelta(days=k)).isoformat(), "aqi": v,
                                                        "cat": X.aqi_cat(v)[1], "param": "PM2.5", "action": False,
                                                        "disc": "", "source": "model"} for k, v in ((2, 44), (3, 58), (4, 38))}},
                           now.date()),
        "tides": tides,
        "beach": {"srf": X.parse_srf(SRF_TEXT, cfg.get("srf_places") or {"VA Beach": ["Virginia Beach"],
                                                                           "Outer Banks": ["Currituck", "Outer Banks"],
                                                                           "Eastern Shore": ["Accomack", "Northampton"]}),
                  "marine": X.parse_cwf(CWF_TEXT, cfg.get("marine_zones") or {"ANZ632": "Lower Bay", "ANZ634": "Bay Mouth / CBBT",
                                                                               "ANZ656": "Coastal Waters"}),
                  "water_temp": 73},
        "cli": X.choose_cli([X.parse_cli(CLI_TODAY_TEXT), X.parse_cli(CLI_TEXT)], now, cfg),
        "acis": X.climo_from_rows(rows, norm, now.date()),
        "uv": X.parse_uv(uv_rows, tz),
        "aviation": {"icao": "KORF", "metar": X.parse_metar(metar, tz), "taf": X.parse_taf(taf, tz)},
        "warn_counts": {"area": {"Tornado Warning": 1, "Severe Thunderstorm Warning": 4, "Flash Flood Warning": 0,
                                 "Special Marine Warning": 2},
                        "state": {"Tornado Warning": 3, "Severe Thunderstorm Warning": 17, "Flash Flood Warning": 2,
                                  "Special Marine Warning": 5}},
        "tropics": tropics,
        "sun": X.sun_info(now, loc["lat"], loc["lon"], tz),
        "errors": [],
    }
