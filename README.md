# KORF Weather Graphics

Pulls NWS NDFD gridded forecast data for Norfolk International (KORF), writes plain-English
summaries, and renders 1920x1080 PNGs in the Meteorologist Ricky Matthews navy style.


Rain chances are always rounded to the nearest 10% (37% → 40%, 25% → 30%), including numbers you type in by hand.

**Run it in the cloud / from your phone:** see `CLOUD_SETUP.md`. A GitHub workflow (`.github/workflows/weather-graphics.yml`)
makes the graphics on a schedule or on demand from the GitHub app, publishes a phone gallery page
(`tools/build_site.py`) and copies everything to Google Drive.
## Setup (Windows / conda)
    conda create -n wxgfx python=3.11 -y
    conda activate wxgfx
    pip install -r requirements.txt
    python run.py --sample      # offline test
    python run.py               # live NDFD

Output: `output/<date_time>/` and a copy in `output/latest/` (stable path for OBS/Facebook).
Each run also writes `forecast.json` (everything the graphics were drawn from) and `caption.txt`
(a ready-to-paste Facebook post).

## Graphics
| file | what |
|---|---|
| daily.png | Today's (tomorrow's after 3 PM) forecast: hi/lo, headline, morning→overnight timeline, summary |
| what_to_know.png | Auto talking points: alerts, storms, rain totals, heat, wind, freeze, cooldowns, dry stretch, weekend |
| 7day.png | 7-day; after 3 PM leads with TONIGHT |
| hourly.png | Next 24 h temps, icons, rain chance |
| feels_like.png | Heat index bands; only when heat index reaches `heat_index_min` |
| wind_chill.png | Blue bands starting at 30° and dropping 5° per band (extra bands added for colder values); bars grow taller as it gets colder; only when a wind chill is at or below ~35° |
| dewpoints.png | Dewpoint comfort scale (your Awesome → Instant Sweat bands) |
| rain_totals.png | Daily QPF + week total |
| wind.png | Peak gusts on a banded scale |
| current.png | Latest KORF observation |
| alerts.png | List of every active alert for your area |
| alert_N_<event>.png | One per active alert: county map shaded in the official NWS hazard color (warning polygon outlined when there is one), title with the alert name and expiration, and a side panel listing the counties/cities plus WHAT / WHEN / IMPACTS / ACTION summarized from the alert text |

Turn graphics on/off in `config.json` → `"graphics"`.

## Weather Graphics Editor (point-and-click)
Double-click **Weather Graphics Editor.bat** (or `python weather_graphics_editor.py`). It opens
http://localhost:8770 in your browser and saves `config.json` / `overrides.json` in place (a `.bak`
of each is kept). Tabs:
- **Graphics & sizes**: check which graphics and which sizes each run makes, plus the "always show" switches.
- **Forecast edits**: each day's high/low/rain %/condition/icon/headline/summary, the daily graphic's
  title, headline, summary and morning-to-overnight text, and your own What To Know list. Grey text is
  the automatic forecast; blue-outlined boxes are your edits; "Use my forecast edits" turns them on/off.
- **SPC hazards**: risk box, color, summary and every hazard row (level, text, hide, add your own) for days 1-3.
- **Be Weather Aware**: title, timing, bullets, what to do, color, or skip it for the day.
- **Settings**: location, alerts, abbreviations, outlook/NDFD options, tide sites, marine zones, stations.
- **Raw JSON**: edit either file directly (checked before it's applied).
- **Render**: save and run the graphics (optionally test data only, or just some graphics) and see the log.
Without the .bat you can still open `Weather Graphics Editor.html` directly, drop the JSON files onto it,
and download the edited files.

## Manual control — three levels
1. **Patch a few values** — `overrides.json`, set `"enabled": true`, list only what you change:
   ```json
   {"enabled": true,
    "days": {"THU": {"high": 86, "pop": 60, "cond": "Scattered Storms", "icon": "tstorm"}},
    "today": {"headline": "HOT & HUMID, PM STORMS",
              "timeline": {"AFTERNOON": {"text": "Storms fire after 2 PM."}}},
    "what_to_know": [{"label": "STORMS:", "text": "Best timing 3-8 PM."}]}
   ```
   Days key by weekday (`THU`), date (`2026-10-01`) or position (`0`). A dict patches a list
   item; a full `[...]` list replaces it. If you change a day's numbers but not its `headline`/`text`,
   those are rewritten automatically to match. Footer shows "+ MANUAL EDITS".
2. **Edit before render** — `python run.py --edit` builds from NDFD, opens the forecast in Notepad,
   renders when you save and close.
3. **Fully manual** — `python run.py --template` writes `manual_forecast.json`; fill it in, then
   `python run.py --from manual_forecast.json` (no NDFD fetch). You can also re-render any past
   `output/.../forecast.json` this way.

Icons: clear, few, partly, mostly_cloudy, cloudy, showers, rain, tstorm, snow, mix, fog, wind.

## Alert maps
- Alerts are pulled for the states in `config.json` → `"alert_states"` and kept only if they touch a
  locality in `"alert_counties"` (FIPS codes; default is Hampton Roads + NE North Carolina + the
  Eastern Shore). Empty list = every alert in those states.
- The map zooms to the alert and always keeps Hampton Roads in view (`"map_home_box"` to change).
  Name abbreviations (map + county list): `"abbreviations"`, e.g. `{"Virginia Beach": "VA Beach"}`.
  City labels come from `"map_cities"` (`[["Norfolk", 36.85, -76.29], ...]`).
- Up to `"alert_graphics_max"` (default 6) are made, most dangerous first (tornado warnings lead).
- County outlines: US Census shoreline-clipped boundaries, bundled in `wxgfx/data/`.
- Manual/testing: in a `--from` forecast file, an alert only needs
  `{"event": "Tornado Warning", "fips": ["51710"], "ends_label": "until 7:15 PM Tuesday"}`;
  color and layout fill in automatically. The alerts actually rendered are in `forecast.json`.

For real-time severe weather, run `python run.py --only alerts,alert_maps` every few minutes from
Task Scheduler (it's fast and only draws what's active).

## Outlook maps (graphic key: `outlooks`)
Drawn on the same county stencil as the alert maps, with a side panel showing the Norfolk-area
category, what it means, and (ERO/QPF) a local list (Norfolk, VA Beach, Chesapeake, Suffolk, Peninsula,
Williamsburg, Eastern Shore, Eliz. City, Outer Banks, Richmond; edit with `"outlook_points"`).
- `spc_dayN.png` - SPC convective outlook (TSTM, 1 MRGL ... 5 HIGH), official SPC colors. The side
  panel shows Norfolk's category and **Possible Hazards**: tornadoes, damaging winds and large hail
  worded from SPC's probability outlooks at Norfolk (Day 3: one combined "severe storms" row), plus
  lightning. Strong-tornado / 75+ mph / 2"+ hail notes are added inside SPC's significant-severe areas.
  **Edit any of it** in `overrides.json` -> `"spc"` (change a level or text, hide a row, add a row,
  replace the headline/summary) or interactively with `python run.py --edit` (`spc_outlook` section).
  The footer then says "+ METEOROLOGIST EDITS".
- `ero_dayN.png` - WPC Excessive Rainfall Outlook (1 MRGL ... 4 HIGH).
- `wpc_qpf_2day.png`, `wpc_qpf_3day.png`, `wpc_qpf_5day.png`, `wpc_qpf_7day.png` - WPC rainfall totals for
  Days 1-2, 1-3, 1-5 and 1-7 (`"qpf_maps"` in config.json picks the periods) on the local map with the NWS 0-12" color bar.
- `wpc_qpf_*_state.png` - the same totals on a Virginia & North Carolina map, with the Hampton Roads DMA outlined and
  DMA amounts in the side panel (`"qpf_state_map": false` turns these off; `"dma_counties"` sets the outline).
Days come from `"spc_days"` / `"ero_days"`. SPC Day 1 is always drawn; any other day with no
risk area on the map is skipped. Map area: `"outlook_view"` = [west, east, south, north].

Sources (all free, no key): SPC's GeoJSON at spc.noaa.gov, and WPC products from
mapservices.weather.noaa.gov. Those map services number their layers differently over time,
so the script finds layers by name. **If an outlook graphic doesn't appear, run**
`python run.py --only outlooks --outlook-debug` - it lists the layers and attribute names it saw.

## Full-screen maps (`"fullscreen_maps": true`)

Every map graphic (SPC, excessive rainfall, WPC rainfall, NWS snow/wind/gust, WPC winter probabilities, WSSI, CPC
hazards, tidal flooding) also comes as `<name>_full.png`: the map fills the whole image, the title floats over a fade at
the top, and the information runs in bars along the bottom (headline card + local value chips + legend). Made in all
four sizes. `"fullscreen_local_view"` sets the zoom for the local Hampton Roads versions.

## Big-text maps (`"bigtext_maps": true`) → `square/<name>_big.png`

Social-feed version of every map graphic: a giant two-line headline across the top, the map filling the middle,
colored value boxes dropped right on the map (e.g. `3–4"`, `SLGT (2/5)`, spread out so they don't overlap), a white
time-period caption, a bold tagline banner across the bottom, and the logo (`logo_path`) in the lower-left of the map.
Square only by default; `"bigtext_formats": ["square", "post"]` adds other sizes. `"bigtext_callouts"` = how many
value boxes (default 4, 0 = none).

Change the words for a storm in `overrides.json` (or `config.json` → `bigtext_text`); `"*"` applies to all of them:

```json
"bigtext": {
  "*": {"tagline": "HEAVY RAIN AND WIND INTO NEXT WEEK"},
  "wpc_qpf_3day": {"title": "NOR'EASTER RAIN ACCUMULATIONS", "caption": "Saturday Through Monday", "callouts": 3}
}
```
Defaults: title = the graphic's title, caption = the time period, tagline = `HAMPTON ROADS AREA: <headline value>`.

## Hurricane threat set (graphic key: `tropical_pack`) → `output/latest/Tropical/`

Made only while a storm threatens (cone over Norfolk, 34-kt wind chance ≥ `tropical_min_prob`, NWS Wakefield
hurricane statements in effect, or the track within `tropical_threat_miles`). Saved to its own folder:
`output/<run>/Tropical/` (wide) with `vertical/`, `post/`, `square/` inside, mirrored to `output/latest/Tropical/`
(emptied automatically once the storm is gone). Numbered in briefing order:

01 storm snapshot · 02 track & cone (watches/warnings, forecast points) · 03 intensity forecast · 04 next NHC advisories ·
05 wind chances (34/50/64 kt, map + cities) · 06 wind arrival (earliest / most likely) · 07 peak gusts · 08 Norfolk wind
timeline · 09 storm surge map (NHC inundation) · 10 Sewells Point surge+tide vs historic storms · 11 tropical watches &
warnings map · 12 high tides · 13 storm rainfall · 14 excessive rainfall · 15 river flooding · 16 Hurricane Local Statement ·
17 threat matrix (wind/surge/rain/tornado from the TCV) · 18 evacuations · 19 preparedness checklist (highlights the
current phase) · 20 tornado risk · 21 storm timeline · 22 history comparison · 23 closest approach · 24 after-storm
reports · 25 power outages.

Data (no keys): NHC CurrentStorms.json and NHC tropical map service (cone, track, points, watches/warnings, wind speed
probabilities, arrival times, potential storm surge flooding), api.weather.gov HLS/TCV from NWS Wakefield, NWPS SWPV2
forecast + historic crests. Evacuations, outages and the checklist are typed in under `"tropical"` in overrides.json
(see the example there). Test the look any time with `python run.py --sample --only tropical_pack`.

## Rain & storm reports (graphic key: `reports`)

- `rain_reports.png` - CoCoRaHS 24-hour rain totals (ending 7 AM) as colored value tags on the county map (NWS rain
  colors; biggest totals win where they'd overlap), with the top totals listed. From the Iowa Environmental Mesonet's
  CoCoRaHS feed (no key). Uses today's reports once enough are in, otherwise yesterday's. Made when anyone reports
  `"rain_reports_min"` (0.10") or more.
- `storm_snow_reports.png`, `storm_rain_reports.png`, `storm_wind_reports.png` - NWS Wakefield Local Storm Reports
  (via IEM) plus the report list at the bottom of NWS Public Information Statements (**METADATA** block), last
  `"storm_reports_hours"` (24). Each is only made when there are reports of that kind; duplicates between the LSRs and
  the PNS are dropped.
- All four also come as `_full` full-screen versions.

## Flash flood guidance (graphic key: `ffg`)

`ffg_1hr.png`, `ffg_3hr.png`, `ffg_6hr.png` (+ `_full` versions) - how much rain in that many hours would start
flooding small streams, from the NWS River Forecast Centers' hourly 5-km gridded Flash Flood Guidance (NOAA map
service, no key). Lower numbers = wetter ground = more flood-prone (hot colors). The panel headlines the lowest
guidance among the local cities and lists each one. `"ffg_hours"` picks the periods (1, 3, 6, 12, 24).

## Drought monitor (graphic key: `drought`)

`drought.png` (full-screen) - the weekly U.S. Drought Monitor (D0-D4, official colors) over Virginia & North Carolina
with the Hampton Roads DMA outlined; Norfolk's drought level; Norfolk rainfall vs normal for the last 30, 60, 90 days and
since Jan 1 (inches above/below and % of normal); drought level for VA Beach, Suffolk, Eastern Shore and Outer Banks.
Data: Esri Living Atlas copy of the USDM map (National Drought Mitigation Center; FEMA's copy as backup) and RCC ACIS
daily rainfall + 1991-2020 normals for ORF. No keys.

## Tidal flooding map (graphic key: `tidal_flood_map`)

`tidal_flood_map_1.png` (and `_2` for the next high tide) - the bay, tidal rivers, oceanfront and shoreline shaded by
forecast flood category (near flood stage / minor / moderate / major) for the high tide window in the title. Only made
when some gauge reaches `"tidal_map_min_category"` (minor). How it's built: each NWS tide gauge's forecast high tide is
scored on that gauge's own flood stages, then blended between gauges by distance and carried out to
`"tidal_radius_km"` from the nearest gauge (that's the extrapolation). Gauges = `tide_sites` + `tide_sites_2` +
`tidal_map_sites` (CBBT, Little Creek, Rudee, Cape Charles, Windmill Point, Tangier, etc.). The side panel lists every
gauge's forecast high tide. Small creeks narrower than the county map's shoreline aren't drawn.

## River flooding (graphic key: `river_flooding`)

Only exported when an NWS river forecast point is forecast at `"river_min_category"` (action stage) or higher:
`river_flooding.png` lists every flooding river; `river_1.png`, `river_2.png` ... (in output/latest) show each one's
observed + forecast hydrograph with flood stage bands, the crest and time, and the NWS impact statement for that level.
Points (`"river_gauges"`): Blackwater River at Franklin (FKNV2), Nottoway River near Sebrell (SEBV2), Blackwater near
Zuni/Dendron, Nottoway near Riverdale/Stony Creek/Rawlings, Meherrin at Emporia/Lawrenceville, Appomattox at Matoaca,
Chowan near Winton.

## Air quality (graphic key: `air_quality`)

Current AQI (big dial, category, main pollutant, health message) plus a 5-day forecast. Official values come from the
AirNow reporting area file (`"aqi_area"`: Hampton Roads; no key) including the Virginia DEQ forecast and discussion;
days with no official forecast use CAMS model guidance from Open-Meteo, marked with *.

## CPC hazards outlook (graphic key: `cpc_hazards`)

From CPC's U.S. Hazards Outlook on NOAA's free map service (no key), drawn on a wide eastern U.S. map from the
Great Lakes to the Gulf (offline basemap: `wxgfx/data/us_east_base.json`).

- `cpc_hazards_d8_14.png` - every hazard except rain (much above/below normal temperatures, high winds, heavy snow,
  ice, severe weather, drought...), each with its own dates. Made every run (`"cpc_show_empty": false` skips it
  when there's nothing).
- `cpc_heavy_rain_d8_14.png` - heavy rain / heavy precipitation and flooding areas only. Made only when CPC has a
  rain area in the map (`"cpc_rain_always": true` forces it).
- The side panel shows whether the Hampton Roads area is included and lists every hazard with its dates.
- `"cpc_periods"` also tries Days 3-7 (`cpc_hazards_d3_7.png`) and makes it only when that layer has data.

## Winter probability & WSSI maps (graphic key: `winter_maps`)

From WPC's free NOAA map services (no key). Each map is made for Hampton Roads and, with
`"winter_state_map": true`, for Virginia & North Carolina (`*_state.png`, DMA outlined, DMA list in the panel).
Maps with nothing in the map area are skipped, so nothing is made out of season (`"winter_always": true` forces them).

- `snow_prob_4in_day1.png`, `snow_prob_8in_day1.png`, `snow_prob_12in_day1.png` (and day2/day3) - WPC chance of at
  least 4"/8"/12" of snow, in WPC's three bands (10-39%, 40-69%, 70%+). `"snow_prob_thresholds"`, `"winter_days"`.
- `ice_prob_day1.png` ... - chance of at least 0.25" of ice (`"ice_prob": false` turns off).
- `wssi_day1.png`, `wssi_day2.png`, `wssi_day3.png`, `wssi_days1-3.png` - Winter Storm Severity Index overall
  impacts (Winter Weather Area, Minor, Moderate, Major, Extreme) with WPC's official colors and what to expect.
  `"wssi_periods"` picks the periods.

If a winter map is missing during a storm, run `python run.py --outlook-debug --only winter_maps` to see the WPC
layers and attributes it found.

## Frost & freeze risk (graphic key: `frost_risk`)

- `frost_risk_table.png` - every local spot (`frost_points`, default the outlook points) × the next `frost_nights` (3)
  nights: forecast low and risk level in colored cells.
- `frost_map_1.png`, `frost_map_2.png`... - a risk map for each night that has frost somewhere (+ `_full` and square
  `_big` versions).

Risk = the NWS (NDFD) overnight low, adjusted for wind and cloud cover overnight (frost needs calm, clear skies):
28° or colder **Hard Freeze** · 29-32° **Freeze** · 33-36° **Frost Likely** (calm & clear) · 37-38° calm & clear, or
33-36° breezy/cloudy **Patchy Frost** · otherwise none. "Calm & clear" = wind under 8 mph and under 50% sky cover.
Only made when something reaches Patchy Frost (`frost_min_level`: 1-4); `"frost_always": true` forces it. Needs
`eccodes` + `numpy` for the map; without them the table falls back to the KORF point forecast.

## Snowfall & wind maps (graphic key: `ndfd_maps`)
Full-resolution (2.5 km) NWS NDFD grids on the county stencil, with a color bar and a local list:
- `snow_map.png` - total forecast snowfall over the next `"snow_hours"` (default 72). Skipped when
  no snow is forecast (`"snow_map_always": true` to force it).
- `wind_map.png` - max sustained wind over the next 24 h; `gust_map.png` - peak gusts, next 24 h
  (`"wind_maps"` picks which).
Data: NDFD GRIB2 files from tgftp.nws.noaa.gov (free, no key; mid-Atlantic sector, CONUS fallback;
cached 30 min). Reading GRIB2 needs ecCodes + numpy, one-time install:

    pip install eccodes numpy
    python -m eccodes selfcheck        (should say "Your system is ready")

or with conda: `conda install -c conda-forge python-eccodes numpy`. Without them, these maps are
skipped with a message and everything else still runs.

## Rainfall amounts
NDFD only issues rainfall amounts (QPF) about 72 hours out, even though rain chances go 7 days.
Past that point the rain graphic uses National Blend of Models (NBM) hourly rainfall from Open-Meteo
(free, no key); those bars are striped and marked `*` with a footnote. If that call fails, those days
show `N/A` instead of pretending it will be dry. Turn off with `"extended_rainfall": false`.

## More graphics (all free, no-key data)
| file | what | data |
|---|---|---|
| weather_aware.png | **Be Weather Aware**: the day's single biggest concern (warnings > watches > SPC/ERO risk > heat, wind, tidal flooding, snow, freeze, fog, rip currents, heavy rain), when, what to know, what to do. Skipped on quiet days. Edit in `overrides.json` -> `"weather_aware"` | everything below |
| tides.png | Sewells Point water level chart (observed, official NWS forecast, astronomical tide for reference) with flood-stage bands, peak level + category, and the next high/low tide times and heights | Official NWS forecast + observations for gauge SWPV2 (the "official" hydrograph on water.noaa.gov/gauges/SWPV2); high/low times come from that forecast. NOAA astronomical predictions are only a labeled backup if the NWS forecast is unavailable |
| high_tides.png | Next two high tides at Sewells Point, Yorktown, Jamestown, Lynnhaven Inlet and Nassawadox: time, forecast level, color-coded flood category box (no flooding / action / minor / moderate / major) | NWS gauge forecasts + official flood stages (gauges found by name; `tide_sites` in config), NOAA tide predictions as backup |
| high_tides_2.png | Same layout for Kiptopeke, Hudgins (Piankatank River), Smithfield (Pagan River), Suffolk (Nansemond River) and Money Point (Elizabeth River) | NWS gauges KPTV2, WCKV2, SMSV2, NMDV2, MNPV2 (`tide_sites_2` in config); NOAA tide predictions as backup for Kiptopeke and Money Point |
| beach.png | Rip current risk (VA Beach, Outer Banks, Eastern Shore), surf, water temp, peak UV, Lower Bay / CBBT / coastal waters forecast | NWS Surf Zone + Coastal Waters forecasts |
| yesterday.png | Yesterday at ORF: high/low vs normal and record, rainfall, month-to-date. After 5 PM (`cli_today_after_hour`) it switches to "Today at ORF" from the NWS afternoon climate report once it's out; `month_rain.png` then includes today too | NWS daily climate report (CLIORF) |
| month_rain.png | Month and year rainfall vs normal, surplus/deficit | CLIORF |
| record_watch.png | Next 5 days: forecast high vs normal vs record, flags near-record days | RCC ACIS (ORF records since 1874) |
| above_average.png | Warmer than average: days whose forecast high is at least `warm_departure_min` (5°) above the 1991-2020 average high. One day = big "+13°" spotlight with forecast vs average high; several days = "Warm Stretch" cards (consecutive) or "Warmer Than Average" (scattered), warmest day marked. Bottom strip shows above/below average for all 7 days. No warm days = no graphic | NWS NDFD highs + ACIS normals (ORF) |
| holiday_countdown.png | Countdown to the next holiday in a spotlight (emoji, days to go, date; "TODAY!" with a greeting on the day) plus the next holidays listed. US holidays are computed (Easter, Thanksgiving, Memorial Day, etc.); add your own with `holidays_extra` (e.g. Hanukkah, Harborfest), skip any with `holidays_off`. Emoji art: Twemoji, CC-BY 4.0 (see wxgfx/data/holiday_icons/ATTRIBUTION.txt) | computed, no download |
| first_freeze.png | Average/earliest/latest first freeze, last year, coldest low in the forecast (Sep 15 until the first freeze) | ACIS |
| commute.png | Your next two drives (6-9 AM, 4-7 PM): rain, fog, gusts on bridges/tunnels, icy spots, sun glare | NDFD |
| weekend.png | Sat/Sun morning/afternoon/evening with "good for" tags | NDFD |
| sun_uv.png | Sunrise/sunset, golden hour, daylight change, hourly UV | calculated + EPA UV (ZIP 23510) |
| tropics.png | Atlantic map: active storms, forecast cones, 7-day outlook areas + list (Jun 1-Nov 30, or anytime there's activity) | NHC |
| warning_count.png | Tornado / severe / flash flood / marine warnings issued today: Hampton Roads vs Virginia (only when > 0) | NWS alerts |
| aviation.png | KORF flight category, decoded METAR, 24-h TAF timeline | aviationweather.gov |

Stations, zones and ZIP are in `config.json` (`tide_station`, `marine_zones`, `uv_zip`, `airport`...).
If one source is down, only its graphic is skipped. `--outlook-debug` also prints details for these.

## Output sizes
Every graphic is made in three shapes (turn any off with `"formats"` in `config.json`):
| folder | size | use |
|---|---|---|
| `output/latest/` | 1920x1080 (16:9) | TV / OBS / YouTube / Restream |
| `output/latest/vertical/` | 1080x1920 (9:16) | Instagram & Facebook Stories, Reels, TikTok, YouTube Shorts |
| `output/latest/post/` | 1080x1350 (4:5) | Facebook & Instagram feed posts (largest size the feed allows) |
| `output/latest/square/` | 1080x1080 (1:1) | Square Facebook/Instagram posts, link posts, profile grids |
Tall versions are re-laid-out, not squeezed: maps stack over their info panel, the 7-day becomes
one row per day, charts reflow. File names are identical across folders.

## Using the graphics in OBS / Restream
`output/latest/` is updated in place every run (files swapped atomically, folder never deleted),
so OBS can point at it permanently. Alert graphics there use fixed names `alert_1.png`, `alert_2.png`...
(most dangerous first); files for alerts that expired are removed.
- One graphic per scene: Image source -> `output/latest/7day.png` (OBS reloads it when it changes).
- Rotation: Image Slide Show source -> add the `output/latest` folder.
- Restream: stream OBS to Restream (Settings -> Stream -> Restream), or upload PNGs in Restream Studio.

## Scheduling
Task Scheduler → Create Basic Task → Action "Start a program" → `run_graphics.bat`
(e.g. 5:00 AM, 11:30 AM, 4:30 PM). NDFD updates roughly hourly.

## Branding
Put your logo PNG (transparent) in the folder and set `"logo_path": "logo.png"`; until then a text
wordmark is drawn. Colors can be overridden in `config.json` → `"colors"` (keys in `wxgfx/theme.py`).

## Notes
- Network: stdlib `urllib`, your User-Agent, retries, and the last good gridpoint is cached in
  `cache/` so a flaky API call still produces graphics.
- "Above/below normal" uses a cosine fit to ORF 1991–2020 normals (±2°).
- `--only 7day,daily` renders a subset.
