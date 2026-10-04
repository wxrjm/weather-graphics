"""'Possible hazards' for the SPC graphics, from SPC's probabilistic outlooks at Norfolk.

Days 1-2: separate tornado / damaging wind / large hail probabilities (+ significant-severe areas).
Day 3:    one combined 'any severe' probability.
Every row is editable: overrides.json -> "spc" (see README), or `python run.py --edit`.
"""
from . import outlooks

SPC = "https://www.spc.noaa.gov/products/outlook/"
HAZ_FILES = {  # key -> (probability file, significant-severe files [old "sig", new "cig"])
    "torn": ("day{d}otlk_torn", ["day{d}otlk_sigtorn", "day{d}otlk_cigtorn"]),
    "wind": ("day{d}otlk_wind", ["day{d}otlk_sigwind", "day{d}otlk_cigwind"]),
    "hail": ("day{d}otlk_hail", ["day{d}otlk_sighail", "day{d}otlk_cighail"]),
    "any": ("day{d}otlk_prob", ["day{d}otlk_sigprob", "day{d}otlk_cigprob"]),
}
LEVEL_COLORS = {"NOT EXPECTED": (70, 86, 112), "LOW": (102, 163, 102), "POSSIBLE": (246, 226, 90),
                "ELEVATED": (240, 160, 60), "HIGH": (228, 60, 60), "VERY HIGH": (230, 90, 230), "N/A": (70, 86, 112)}

# (min %, level, text) -- highest matching row wins
WORDING = {
    "torn": ("TORNADOES", [
        (0, "NOT EXPECTED", "Tornadoes are not expected."),
        (2, "LOW", "A brief, weak tornado can't be ruled out."),
        (5, "POSSIBLE", "A few tornadoes are possible."),
        (10, "ELEVATED", "Several tornadoes are possible; a couple could be strong."),
        (15, "HIGH", "Tornadoes are likely, some could be strong."),
        (30, "VERY HIGH", "A tornado outbreak is possible, including strong tornadoes."),
    ], "Strong tornadoes (EF2+) possible."),
    "wind": ("DAMAGING WINDS", [
        (0, "NOT EXPECTED", "Damaging winds are not expected."),
        (5, "LOW", "An isolated damaging gust (60+ mph) is possible."),
        (15, "POSSIBLE", "Scattered 60+ mph gusts could bring down trees and power lines."),
        (30, "ELEVATED", "Numerous damaging gusts are possible; power outages likely where storms hit."),
        (45, "HIGH", "Widespread damaging winds likely, possibly a line of storms (derecho-type)."),
        (60, "VERY HIGH", "Widespread, destructive wind damage is expected."),
    ], "Gusts of 75+ mph possible."),
    "hail": ("LARGE HAIL", [
        (0, "NOT EXPECTED", "Large hail is not expected."),
        (5, "LOW", "Isolated quarter-size (1\") hail is possible."),
        (15, "POSSIBLE", "Scattered large hail, quarter size (1\") or larger."),
        (30, "ELEVATED", "Large hail is likely in the strongest storms."),
        (45, "HIGH", "Numerous reports of large, damaging hail expected."),
        (60, "VERY HIGH", "Widespread very large hail expected."),
    ], "Hail 2\"+ (hen egg or larger) possible."),
    "any": ("SEVERE STORMS", [
        (0, "NOT EXPECTED", "Severe storms are not expected."),
        (5, "LOW", "An isolated severe storm is possible."),
        (15, "POSSIBLE", "Scattered severe storms possible: damaging winds, hail or a tornado."),
        (30, "ELEVATED", "Numerous severe storms possible."),
        (45, "HIGH", "Widespread severe weather is likely."),
        (60, "VERY HIGH", "A major severe weather event is expected."),
    ], "Significant severe weather possible."),
}


def _prob(props):
    for k in ("LABEL", "label", "DN", "dn"):
        v = props.get(k)
        if v is None:
            continue
        try:
            f = float(str(v).strip().rstrip("%"))
        except ValueError:
            continue
        return round(f * 100) if f < 1 else round(f)  # "0.05" -> 5, 5 -> 5
    return None


def fetch(fx, day):
    """-> {"torn": {"prob": 5, "sig": False}, ...} at nothing yet; raw polygons for the point test."""
    keys = ["torn", "wind", "hail"] if day <= 2 else ["any"]
    out = {}
    for key in keys:
        base, sigs = HAZ_FILES[key]
        feats = []
        try:
            data = fx.json(SPC + base.format(d=day) + ".lyr.geojson")
            for f in data.get("features", []):
                p = _prob(f.get("properties") or {})
                polys = outlooks.polys_of(f.get("geometry"))
                if p and polys:
                    feats.append({"prob": p, "polys": polys})
            fx.log(f"SPC day {day} {key}: {len(feats)} probability areas")
        except Exception as e:
            fx.log(f"SPC day {day} {key} unavailable: {e}")
            continue
        sig = []
        for s in sigs:
            try:
                data = fx.json(SPC + s.format(d=day) + ".lyr.geojson")
                sig += [outlooks.polys_of(f.get("geometry")) for f in data.get("features", [])]
            except Exception:
                pass
        out[key] = {"areas": feats, "sig": [p for p in sig if p]}
    return out


def at_point(probs, lon, lat):
    res = {}
    for key, d in (probs or {}).items():
        p = max([a["prob"] for a in d.get("areas", []) if outlooks.contains(a["polys"], lon, lat)], default=0)
        sig = any(outlooks.contains(polys, lon, lat) for polys in d.get("sig", []))
        res[key] = {"prob": p, "sig": sig}
    return res


def rows_for(point, cat_level):
    """Plain-language hazard rows for the side panel."""
    rows = []
    for key in ("torn", "wind", "hail", "any"):
        if key not in point:
            continue
        name, table, sig_text = WORDING[key]
        p, sig = point[key]["prob"], point[key]["sig"]
        lvl, text = next((l, t) for m, l, t in reversed(table) if p >= m)
        if sig and p:
            text = f"{text} {sig_text}"
        rows.append({"label": name, "level": lvl, "prob": p, "text": text})
    # most important first (wind usually leads in Hampton Roads)
    order = ["VERY HIGH", "HIGH", "ELEVATED", "POSSIBLE", "LOW", "NOT EXPECTED"]
    rows.sort(key=lambda r: order.index(r["level"]))
    if cat_level is not None and cat_level >= 0:
        rows.append({"label": "LIGHTNING", "level": "POSSIBLE", "prob": None,
                     "text": "Frequent lightning in any storm. When thunder roars, go indoors."})
    if not rows:
        rows = [{"label": "HAZARD DETAILS", "level": "N/A", "prob": None,
                 "text": "SPC hazard probabilities weren't available. Add your own in overrides.json."}]
    return rows


ALIASES = {"tornado": "TORNADOES", "tornadoes": "TORNADOES", "wind": "DAMAGING WINDS", "winds": "DAMAGING WINDS",
           "damaging winds": "DAMAGING WINDS", "hail": "LARGE HAIL", "large hail": "LARGE HAIL",
           "lightning": "LIGHTNING", "severe": "SEVERE STORMS", "severe storms": "SEVERE STORMS"}


def apply_edits(day_info, edit):
    """edit = overrides.json -> spc -> "<day>".
    headline / meaning / title override the risk box; "hazards" is either a full list (replaces)
    or a dict keyed by hazard name: {"level": ..., "text": ...} edits, {"hide": true} removes,
    an unknown name adds a new row."""
    if not edit:
        return day_info
    for k in ("headline", "meaning", "hazards_title", "category"):
        if k in edit:
            day_info[k] = edit[k]
    hz = edit.get("hazards")
    if isinstance(hz, list):
        day_info["hazards"] = [{"label": h.get("label", "").upper(), "level": h.get("level", "POSSIBLE").upper(),
                                "prob": h.get("prob"), "text": h.get("text", "")} for h in hz]
    elif isinstance(hz, dict):
        rows = day_info["hazards"]
        for name, ch in hz.items():
            if name.startswith("_"):
                continue
            label = ALIASES.get(name.lower(), name.upper())
            row = next((r for r in rows if r["label"] == label), None)
            if ch.get("hide"):
                day_info["hazards"] = rows = [r for r in rows if r["label"] != label]
                continue
            if row is None:
                row = {"label": label, "level": "POSSIBLE", "prob": None, "text": ""}
                rows.append(row)
            if "level" in ch:
                row["level"] = ch["level"].upper()
                row["prob"] = ch.get("prob")  # your level replaces SPC's %, unless you give one
            elif "prob" in ch:
                row["prob"] = ch["prob"]
            if "text" in ch:
                row["text"] = ch["text"]
            row["edited"] = True
    day_info["edited"] = True
    return day_info
