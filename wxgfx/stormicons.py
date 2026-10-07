"""Tropical system symbols (wxgfx/data/storm_icons, built by tools/make_storm_icons.py):
  L   - low / disturbance / remnant / post-tropical
  TS  - tropical depression or tropical storm (open swirl)
  1-5 - hurricane category (filled swirl with the number)
"""
from functools import lru_cache
from pathlib import Path

from PIL import Image

DIR = Path(__file__).resolve().parent / "data" / "storm_icons"
LOW_CLASSES = {"LO", "DB", "EX", "PT", "PTC", "PC", "RL", "WV", "REMNANTS", "POST-TROPICAL", "DISTURBANCE"}


def saffir(kt):
    for c, lim in ((5, 137), (4, 113), (3, 96), (2, 83), (1, 64)):
        if (kt or 0) >= lim:
            return c
    return 0


def kind(wind_kt=None, cls=None, dvlbl=None):
    """-> "L", "TS" or "1".."5".  cls = NHC classification (HU, TS, TD, STS, PTC, LO...);
    dvlbl = NHC forecast-point label (D, S, H, M, L...)."""
    c, v = (cls or "").upper(), (dvlbl or "").upper()
    if c in LOW_CLASSES or v in ("L", "X", "LO", "EX"):
        return "L"
    if c == "HU" or v in ("H", "M") or (wind_kt or 0) >= 64:
        return str(max(1, saffir(wind_kt)))
    return "TS"


@lru_cache(maxsize=64)
def _icon(k, px):
    im = Image.open(DIR / f"{k}.png").convert("RGBA")
    return im.resize((px, px), Image.LANCZOS)


def draw(d, cx, cy, size, k):
    """Paste symbol k centered at (cx, cy) on the image behind ImageDraw d (pixel units, already scaled)."""
    px = max(8, int(round(size)))
    img, icon = getattr(d, "_image", d), _icon(k, px)
    if img.mode == "RGBA":
        from .outlookmap import composite_at
        composite_at(img, icon, cx - px / 2, cy - px / 2)
    else:  # RGB canvas: paste through the icon's own alpha
        img.paste(icon, (int(round(cx - px / 2)), int(round(cy - px / 2))), icon)


def draw_storm(d, cx, cy, size, wind_kt=None, cls=None, dvlbl=None):
    draw(d, cx, cy, size, kind(wind_kt, cls, dvlbl))
