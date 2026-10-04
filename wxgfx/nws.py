"""api.weather.gov access: standard library only, with retries and last-good caching."""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://api.weather.gov"


class NWSClient:
    def __init__(self, user_agent, cache_dir):
        self.ua = user_agent
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)

    def get(self, url, retries=4):
        if url.startswith("/"):
            url = BASE + url
        req = urllib.request.Request(url, headers={
            "User-Agent": self.ua, "Accept": "application/geo+json"})
        err = None
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                err = e  # gridpoint endpoint throws intermittent 500s; back off and retry
                time.sleep(2 ** attempt)
        raise RuntimeError(f"NWS request failed: {url} ({err})")

    def _cached(self, name, fetch, max_age_s=None):
        """Fetch fresh; on failure fall back to the last good copy on disk."""
        path = self.cache / name
        if max_age_s and path.exists() and time.time() - path.stat().st_mtime < max_age_s:
            return json.loads(path.read_text())
        try:
            data = fetch()
            path.write_text(json.dumps(data))
            return data
        except Exception as e:
            if path.exists():
                print(f"  ! {e} -- using cached {name}")
                return json.loads(path.read_text())
            raise

    def point(self, lat, lon):
        return self._cached(f"point_{lat}_{lon}.json",
                            lambda: self.get(f"/points/{lat},{lon}"), max_age_s=7 * 86400)

    def gridpoint(self, lat, lon):
        p = self.point(lat, lon)["properties"]
        url = p["forecastGridData"]
        return self._cached("gridpoint_last.json", lambda: self.get(url))

    def alerts(self, lat, lon):
        try:
            return self.get(f"/alerts/active?point={lat},{lon}").get("features", [])
        except Exception as e:
            print(f"  ! alerts unavailable: {e}")
            return []

    def alerts_area(self, states):
        """Active alerts for whole states (deduped); filtered to your counties later."""
        feats, ids = [], set()
        for st in states:
            try:
                for f in self.get(f"/alerts/active?area={st}").get("features", []):
                    if f.get("id") not in ids:
                        ids.add(f.get("id"))
                        feats.append(f)
            except Exception as e:
                print(f"  ! alerts for {st} unavailable: {e}")
        return feats

    def latest_obs(self, station):
        try:
            return self.get(f"/stations/{station}/observations/latest")
        except Exception as e:
            print(f"  ! observation unavailable: {e}")
            return None
