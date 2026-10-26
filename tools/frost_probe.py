"""Shows exactly what the frost / freeze maps see around Virginia Beach.

    python tools/frost_probe.py            (live NDFD min-temp grid, same download the maps use)
    python tools/frost_probe.py --sample   (offline test)

For each spot it prints the nearest NDFD grid cell (and how far away it is), then a 7x7 block of forecast lows
(deg F) around it: '--' = no data (water / off-grid), so you can see whether the oceanfront cells are real values
or missing, and which inland cells would be pulling the contour colder. It also prints the NWS point forecast low
for the same spot so the two can be compared. Results are also saved to frost_probe.txt.
"""
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402
from wxgfx import frost, ndfdmap  # noqa: E402

SPOTS = [("VA Beach Oceanfront", 36.85, -75.98), ("Great Neck / Lynnhaven", 36.88, -76.05), ("Princess Anne / Pungo", 36.72, -76.02),
         ("Back Bay / Sandbridge", 36.70, -75.93), ("Norfolk (ORF)", 36.8946, -76.2012)]
out = []


def say(s=""):
    print(s)
    out.append(s)


def nws_low(lat, lon, ua):
    try:
        g = lambda u: json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": ua}), timeout=30))
        p = g(f"https://api.weather.gov/points/{lat},{lon}")["properties"]
        per = g(p["forecast"])["properties"]["periods"]
        n = next(x for x in per if not x["isDaytime"])
        return f'{n["name"]}: {n["temperature"]}F'
    except Exception as ex:
        return f"unavailable ({ex.__class__.__name__})"


def main():
    cfg = json.load(open(ROOT / "config.json", encoding="utf-8"))
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.now(timezone.utc)
    if "--sample" in sys.argv:
        data = frost.sample(now, tz)
    else:
        data = frost.fetch(cfg, ROOT / "cache", now, debug=True)
    if not data["nights"]:
        say("No frost grids: " + "; ".join(data["errors"]))
        return
    nt = data["nights"][0]
    say(f"GRIB info: {ndfdmap.SCAN_INFO}   (rows_flipped > 0 means the stripe fix was applied)")
    say(f"Night: {nt['label']}   grid shape {nt['low'].shape}")
    for name, la, lo in SPOTS:
        d = (nt["lat"] - la) ** 2 + ((nt["lon"] - lo) * math.cos(math.radians(la))) ** 2
        j, i = np.unravel_index(np.nanargmin(d), d.shape)
        km = math.sqrt(d[j, i]) * 111
        low = nt["low"][j, i]
        say(f"\n{name}  ({la}, {lo})  nearest cell at ({nt['lat'][j, i]:.3f}, {nt['lon'][j, i]:.3f}), {km:.1f} km away")
        say(f"  map low {'--' if low != low else round(float(low))}F   NWS point forecast {nws_low(la, lo, cfg['user_agent']) if '--sample' not in sys.argv else 'skipped'}")
        say("  7x7 block of lows (rows = north to south, columns = west to east):")
        for jj in range(j - 3, j + 4):
            row = []
            for ii in range(i - 3, i + 4):
                ok = 0 <= jj < nt["low"].shape[0] and 0 <= ii < nt["low"].shape[1]
                v = nt["low"][jj, ii] if ok else float("nan")
                row.append(" -- " if v != v else f"{v:4.0f}")
            say("   " + " ".join(row) + ("   <- center row" if jj == j else ""))
    (ROOT / "frost_probe.txt").write_text("\n".join(out), encoding="utf-8")
    say("\nSaved frost_probe.txt - send me that file.")


main()
