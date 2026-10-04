"""Hourly rainfall guidance beyond NDFD's QPF horizon (~72 h).

NDFD only carries QPF out about 3 days, while rain chances run to day 7. To fill
days 4-7 we pull the National Blend of Models (NBM) hourly precipitation from
Open-Meteo (free, no API key). If NBM isn't available we fall back to Open-Meteo's
blended "best_match" model. Everything here is stdlib only.
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://api.open-meteo.com/v1/forecast"


def fetch_hourly_precip(lat, lon, user_agent, models=("ncep_nbm_conus", "best_match")):
    """-> ({utc_hour_start: inches}, model_used) or ({}, None) on failure."""
    for model in models:
        q = {"latitude": lat, "longitude": lon, "hourly": "precipitation",
             "precipitation_unit": "inch", "timezone": "GMT", "forecast_days": 9}
        if model != "best_match":
            q["models"] = model
        req = urllib.request.Request(f"{URL}?{urllib.parse.urlencode(q)}", headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            times = data["hourly"]["time"]
            vals = data["hourly"].get("precipitation") or data["hourly"].get(f"precipitation_{model}")
            out = {}
            for t, v in zip(times, vals):
                if v is None:
                    continue
                # Open-Meteo precip is the total for the hour ENDING at t
                end = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
                out[end - timedelta(hours=1)] = float(v)
            if out and any(k > datetime.now(timezone.utc) + timedelta(days=4) for k in out):
                return out, model
        except Exception as e:
            print(f"  ! extended rainfall ({model}) unavailable: {e}")
    return {}, None


MODEL_LABELS = {"ncep_nbm_conus": "NBM", "best_match": "model blend", "sample": "sample"}
