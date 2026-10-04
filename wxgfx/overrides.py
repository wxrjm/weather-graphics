"""Manual overrides: deep-merge your edits on top of the NDFD-built package.

Lists (days, timeline, what_to_know...) can be patched by key instead of index:
  "days": {"THU": {"high": 88, "pop": 60}}          day by weekday
  "days": {"2026-10-01": {"cond": "Rain Likely"}}   day by date
  "days": {"0": {...}}                              day by position
  "today": {"timeline": {"AFTERNOON": {"text": "..."}}}
Give a full list ( [...] ) to replace it outright, e.g. your own What To Know rows.
Keys starting with "_" are comments and ignored.
"""
import json
from pathlib import Path

from datetime import date

from .summarize import make_headline, make_text, normal_temps

TEXT_FIELDS = {"headline", "text"}
NUMERIC_FIELDS = {"high", "low", "pop", "cond", "icon", "night_cond", "qpf", "max_gust", "max_hi",
                  "max_dew", "wind_dir", "wind_avg", "day_timing", "departure"}


def _find(lst, key):
    if key.lstrip("-").isdigit():
        i = int(key)
        return i if -len(lst) <= i < len(lst) else None
    k = key.upper()
    for i, x in enumerate(lst):
        if isinstance(x, dict) and (x.get("date") == key or x.get("dow") == k or
                                    str(x.get("label", "")).upper() == k or
                                    str(x.get("event", "")).upper() == k):
            return i
    return None


def merge(base, over, touched=None, path=""):
    if isinstance(over, dict) and isinstance(base, dict):
        for k, v in over.items():
            if k.startswith("_"):
                continue
            base[k] = merge(base.get(k), v, touched, f"{path}.{k}") if k in base else v
            if touched is not None:
                touched.append(f"{path}.{k}")
        return base
    if isinstance(over, dict) and isinstance(base, list):
        for k, v in over.items():
            if k.startswith("_"):
                continue
            i = _find(base, k)
            if i is None:
                print(f"  ! override key '{k}' not found under '{path or 'root'}' — skipped")
                continue
            base[i] = merge(base[i], v, touched, f"{path}[{i}]")
        return base
    return over


def apply(pkg, overrides):
    if not overrides:
        return pkg
    touched = []
    overrides = {k: v for k, v in overrides.items() if k not in ("spc", "weather_aware")}  # SPC edits handled in spchazards
    merge(pkg, overrides, touched)
    # re-write auto text for any day whose numbers you changed but whose text you didn't
    for i, d in enumerate(pkg.get("days", [])):
        keys = {t.split(".")[-1] for t in touched if t.startswith(f".days[{i}].")}
        if keys & NUMERIC_FIELDS:
            if "high" in keys and "departure" not in keys and d.get("high") is not None:
                d["departure"] = d["high"] - round(normal_temps(date.fromisoformat(d["date"]))[0])
            if "headline" not in keys:
                d["headline"] = make_headline(d)
            if "text" not in keys:
                d["text"] = make_text(d, night_part=True)
    if touched:
        pkg["source"] = pkg.get("source", "NWS NDFD").split(" +")[0] + " + MANUAL EDITS"
        print(f"  overrides applied: {len(touched)} field(s)")
    return pkg


def load(path):
    p = Path(path)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("enabled", True) is False:
        return None
    data.pop("enabled", None)
    return data
