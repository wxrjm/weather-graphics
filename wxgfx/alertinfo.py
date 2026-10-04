"""NWS alert parsing: colors, affected counties (from SAME/FIPS codes), polygons and
a plain-language summary pulled from the WHAT / WHEN / IMPACTS / HAZARD text blocks."""
import json
import re
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "region_counties.json"

# Official NWS hazard map colors (weather.gov/help-map), plus a keyword fallback.
COLORS = {
    "Tornado Warning": "#FF0000", "Extreme Wind Warning": "#FF8C00",
    "Severe Thunderstorm Warning": "#FFA500", "Flash Flood Warning": "#8B0000",
    "Flash Flood Emergency": "#8B0000", "Tornado Watch": "#FFFF00",
    "Severe Thunderstorm Watch": "#DB7093", "Flash Flood Watch": "#2E8B57", "Flood Watch": "#2E8B57",
    "Flood Warning": "#00FF00", "Flood Advisory": "#00FF7F", "Flood Statement": "#00FF00",
    "Hurricane Warning": "#DC143C", "Hurricane Watch": "#FF00FF",
    "Tropical Storm Warning": "#B22222", "Tropical Storm Watch": "#F08080",
    "Storm Surge Warning": "#B524F7", "Storm Surge Watch": "#DB7FF7",
    "Coastal Flood Warning": "#228B22", "Coastal Flood Watch": "#66CDAA",
    "Coastal Flood Advisory": "#7CFC00", "Coastal Flood Statement": "#6B8E23",
    "Blizzard Warning": "#FF4500", "Ice Storm Warning": "#8B008B",
    "Winter Storm Warning": "#FF69B4", "Winter Storm Watch": "#4682B4",
    "Winter Weather Advisory": "#7B68EE", "Lake Effect Snow Warning": "#008B8B",
    "High Wind Warning": "#DAA520", "High Wind Watch": "#B8860B", "Wind Advisory": "#D2B48C",
    "Extreme Heat Warning": "#C71585", "Excessive Heat Warning": "#C71585",
    "Extreme Heat Watch": "#800000", "Excessive Heat Watch": "#800000", "Heat Advisory": "#FF7F50",
    "Extreme Cold Warning": "#0000FF", "Extreme Cold Watch": "#5F9EA0",
    "Cold Weather Advisory": "#AFEEEE", "Wind Chill Advisory": "#AFEEEE",
    "Freeze Warning": "#483D8B", "Freeze Watch": "#00FFFF", "Frost Advisory": "#6495ED",
    "Dense Fog Advisory": "#708090", "Dense Smoke Advisory": "#F0E68C",
    "Red Flag Warning": "#FF1493", "Fire Weather Watch": "#FFDEAD",
    "Special Weather Statement": "#FFE4B5", "Air Quality Alert": "#808080",
    "Rip Current Statement": "#40E0D0", "High Rip Current Risk": "#40E0D0",
    "Beach Hazards Statement": "#40E0D0", "High Surf Advisory": "#BA55D3",
    "High Surf Warning": "#228B22", "Small Craft Advisory": "#D8BFD8", "Gale Warning": "#DDA0DD",
    "Storm Warning": "#9400D3", "Hurricane Force Wind Warning": "#CD5C5C",
}
PRIORITY = ["Tornado Warning", "Extreme Wind Warning", "Flash Flood Emergency", "Severe Thunderstorm Warning",
            "Flash Flood Warning", "Hurricane Warning", "Storm Surge Warning", "Tornado Watch",
            "Severe Thunderstorm Watch", "Tropical Storm Warning", "Hurricane Watch", "Storm Surge Watch",
            "Blizzard Warning", "Ice Storm Warning", "Winter Storm Warning", "Extreme Heat Warning",
            "Excessive Heat Warning", "Coastal Flood Warning", "Flood Warning", "High Wind Warning"]
WATCH_HAZARDS = {
    "Tornado": "tornadoes and severe thunderstorms", "Severe Thunderstorm": "severe thunderstorms with damaging winds and large hail",
    "Flood": "flooding from heavy rain", "Hurricane": "hurricane conditions within 48 hours",
    "Tropical Storm": "tropical storm conditions within 48 hours", "Storm Surge": "life-threatening storm surge",
    "Winter Storm": "significant snow, sleet or ice", "High Wind": "damaging high winds", "Heat": "dangerous heat",
    "Freeze": "freezing temperatures", "Fire Weather": "rapid wildfire spread",
}
STATE_ABBR = {"51": "VA", "37": "NC", "24": "MD", "10": "DE", "11": "DC"}


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def color_for(event):
    if event in COLORS:
        return hex_rgb(COLORS[event])
    e = event.lower()
    for key, col in [("warning", "#E8303A"), ("watch", "#FFB000"), ("advisory", "#E8D44D"),
                     ("statement", "#5AA8FF")]:
        if key in e:
            return hex_rgb(col)
    return hex_rgb("#5AA8FF")


_counties = None


def counties():
    global _counties
    if _counties is None:
        raw = json.loads(DATA.read_text())
        _counties = {c["fips"]: c for c in raw["counties"]}
        for c in _counties.values():  # bounding box for fast off-map culling
            xs = [x for p in c["polys"] for x, _ in p[0]]
            ys = [y for p in c["polys"] for _, y in p[0]]
            c["bb"] = (min(xs), max(xs), min(ys), max(ys))
        global _state_lines
        _state_lines = raw.get("state_lines", [])
    return _counties


_state_lines = None


def state_lines():
    counties()
    return _state_lines or []


def in_view(c, w, e, s, n):
    bw, be, bs, bn = c["bb"]
    return be >= w and bw <= e and bn >= s and bs <= n


def county_label(fips):
    c = counties().get(fips)
    if not c:
        return None
    if c["lsad"].lower() == "city" and any(o["name"] == c["name"] and o["fips"] != fips and o["fips"][:2] == fips[:2]
                                           for o in counties().values()):
        return f"{c['name']} City"  # e.g. Franklin City vs Franklin County
    return c["name"]


def _clean(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    if s and sum(ch.isupper() for ch in s) > 0.7 * sum(ch.isalpha() for ch in s):  # old ALL-CAPS text
        s = ". ".join(x.strip().capitalize() for x in s.lower().split(". "))
    return s


def _sentences(s, n=2, limit=230):
    parts = re.split(r"(?<=[.!?])\s+", s)
    out = ""
    for p in parts[:n]:
        if out and len(out) + len(p) > limit:
            break
        out = f"{out} {p}".strip()
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0] + "…"
    return out


def summarize_text(p, until_label):
    desc = p.get("description") or ""
    instr = p.get("instruction") or ""
    sec = {}
    for m in re.finditer(r"\*\s*([A-Z][A-Z /]+?)\.\.\.(.*?)(?=\n\s*\*|\Z)", desc, re.S):
        sec[m.group(1).strip()] = _clean(m.group(2))
    for key in ("HAZARD", "SOURCE", "IMPACT", "IMPACTS"):
        m = re.search(rf"^{key}\.\.\.(.*?)(?=\n\s*\n|\n[A-Z ]+\.\.\.|\Z)", desc, re.S | re.M)
        if m and key not in sec:
            sec[key] = _clean(m.group(1))
    lead = ""
    m = re.search(r"\*\s*(At \d.*?)(?=\n\s*\n|\n\s*\*|\Z)", desc, re.S)  # "* At 630 PM, a storm was..."
    if m:
        lead = _clean(m.group(1))
    for para in re.split(r"\n\s*\n", desc):
        para = para.strip()
        if lead:
            break
        if (para and not para.startswith("*") and not re.match(r"^[A-Z ]+\.\.\.", para)
                and not re.search(r"has issued|remains valid|is in effect for|following areas", para, re.I)):
            lead = _clean(para)
    event = p.get("event", "")
    if not lead and not sec.get("WHAT") and "Watch" in event:
        what_h = next((v for k, v in WATCH_HAZARDS.items() if k in event), "hazardous weather")
        lead = f"Conditions are favorable for {what_h} across the watch area."

    rows = []
    what = sec.get("WHAT") or (f"{sec['HAZARD']}." if sec.get("HAZARD") else "") or _sentences(lead, 1) or _clean(p.get("headline"))
    if sec.get("HAZARD") and lead:
        what = f"{sec['HAZARD'].rstrip('.')}. {_sentences(lead, 1, 170)}"
    rows.append(("WHAT", _sentences(what, 2)))
    rows.append(("WHEN", _sentences(sec.get("WHEN") or until_label[:1].upper() + until_label[1:] + ".", 1, 160)))
    imp = sec.get("IMPACTS") or sec.get("IMPACT")
    if imp:
        rows.append(("IMPACTS", _sentences(imp, 2)))
    if instr:
        rows.append(("ACTION", _sentences(_clean(instr), 1, 170)))
    elif "Watch" in event:
        rows.append(("ACTION", "Have a way to get warnings. Be ready to act quickly if a warning is issued."))
    return [{"label": l, "text": t} for l, t in rows if t]


def _until(p, tz):
    ends = p.get("ends") or p.get("expires")
    if not ends:
        return "until further notice"
    e = datetime.fromisoformat(ends).astimezone(tz)
    return "until " + e.strftime("%I:%M %p %A").lstrip("0").replace(":00 ", " ")


def _polygon(geom):
    if not geom:
        return None
    if geom["type"] == "Polygon":
        return geom["coordinates"][0]
    if geom["type"] == "MultiPolygon":
        return max((poly[0] for poly in geom["coordinates"]), key=len)
    return None


def parse(features, tz, cfg):
    focus = set(cfg.get("alert_counties") or [])
    home = cfg["location"].get("fips")
    out, seen = [], set()
    for f in features:
        p = f.get("properties", {})
        if p.get("status", "Actual") != "Actual" or p.get("messageType") == "Cancel":
            continue
        fips = sorted({c[1:] for c in (p.get("geocode") or {}).get("SAME", []) if len(c) == 6 and c[1:3] in STATE_ABBR})
        if focus and not (set(fips) & focus):
            continue
        key = (p.get("event"), tuple(fips), p.get("ends") or p.get("expires"))
        if key in seen:
            continue
        seen.add(key)
        until = _until(p, tz)
        event = p.get("event", "Alert")
        out.append({
            "event": event, "severity": p.get("severity"),
            "color": "#%02X%02X%02X" % color_for(event),
            "headline": p.get("headline") or "", "ends_label": until,
            "fips": fips, "area_desc": p.get("areaDesc") or "",
            "affects_home": bool(home and home in fips) or not fips,
            "polygon": _polygon(f.get("geometry")),
            "summary": summarize_text(p, until),
        })
    sev = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3}
    rank = lambda a: (PRIORITY.index(a["event"]) if a["event"] in PRIORITY else 99, sev.get(a["severity"], 4))
    out.sort(key=rank)
    return out


def areas_text(alert):
    """'VA: Norfolk, Virginia Beach · NC: Currituck' from FIPS; falls back to areaDesc."""
    by_state = {}
    for f in alert.get("fips", []):
        name = county_label(f)
        if name:
            by_state.setdefault(STATE_ABBR[f[:2]], []).append(name)
    if not by_state:
        return alert.get("area_desc", "").replace(";", ",")
    order = ["VA", "NC", "MD", "DE", "DC"]
    return {st: sorted(set(by_state[st])) for st in sorted(by_state, key=order.index)}
