"""Builds icons/ : one transparent PNG per icon the graphics use + icon_sheet.png (labelled contact sheet).
Run: python tools/make_icon_sheet.py"""
import math
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw  # noqa: E402

from wxgfx import fronts, icons, stormicons, theme  # noqa: E402
from wxgfx.theme import C, font  # noqa: E402

OUT = ROOT / "icons"
PX = 512  # individual icon size


class _Fake:
    def __init__(self):
        self.img = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))

    def layer(self, fn):
        fn(ImageDraw.Draw(self.img))


def cond(kind, night=False):
    f = _Fake()
    icons.draw_icon(f, kind, PX / theme.S / 2, PX / theme.S / 2 + 6, 210, night=night)
    return f.img


def front(kind):
    im = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = [(40, 330), (170, 250), (300, 230), (470, 150)]
    fronts.draw_front(d, pts, kind, 2.0, motion=(0.4, -1.0))
    return im


def letter(ch, col):
    im = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((PX / 2, PX / 2 - 20), ch, font=font("bold", 150), fill=(*col, 255), anchor="mm", stroke_width=6, stroke_fill=(10, 16, 30, 255))
    d.text((PX / 2, PX / 2 + 150), "1012", font=font("bold", 48), fill=(255, 255, 255, 255), anchor="mm", stroke_width=5, stroke_fill=(10, 16, 30, 255))
    return im


def storm(k):
    return Image.open(stormicons.DIR / f"{k}.png").convert("RGBA").resize((PX, PX), Image.LANCZOS)


SECTIONS = [
    ("DAYTIME CONDITIONS", [
        ("clear_day", "Clear / Sunny", lambda: cond("clear")), ("few_day", "Mostly Sunny", lambda: cond("few")),
        ("partly_day", "Partly Cloudy", lambda: cond("partly")), ("mostly_cloudy", "Mostly Cloudy", lambda: cond("mostly_cloudy")),
        ("cloudy", "Cloudy", lambda: cond("cloudy")), ("showers_day", "Showers", lambda: cond("showers")),
        ("rain", "Rain", lambda: cond("rain")), ("tstorm", "Thunderstorms", lambda: cond("tstorm")),
        ("snow", "Snow", lambda: cond("snow")), ("mix", "Wintry Mix / Sleet", lambda: cond("mix")),
        ("fog", "Fog", lambda: cond("fog")), ("wind", "Windy", lambda: cond("wind"))]),
    ("NIGHT CONDITIONS", [
        ("clear_night", "Clear", lambda: cond("clear", True)), ("few_night", "Mostly Clear", lambda: cond("few", True)),
        ("partly_night", "Partly Cloudy", lambda: cond("partly", True)), ("showers_night", "Showers", lambda: cond("showers", True))]),
    ("FRONTS & PRESSURE", [
        ("front_cold", "Cold Front", lambda: front("cold")), ("front_warm", "Warm Front", lambda: front("warm")),
        ("front_stationary", "Stationary Front", lambda: front("stationary")), ("front_occluded", "Occluded Front", lambda: front("occluded")),
        ("front_trough", "Trough", lambda: front("trough")), ("pressure_high", "High Pressure", lambda: letter("H", (88, 170, 255))),
        ("pressure_low", "Low Pressure", lambda: letter("L", (255, 96, 96)))]),
    ("TROPICAL", [
        ("tropical_low", "Tropical Low", lambda: storm("L")), ("tropical_storm", "Tropical Storm", lambda: storm("TS")),
        ("hurricane_1", "Hurricane 1", lambda: storm("1")), ("hurricane_2", "Hurricane 2", lambda: storm("2")),
        ("hurricane_3", "Hurricane 3", lambda: storm("3")), ("hurricane_4", "Hurricane 4", lambda: storm("4")),
        ("hurricane_5", "Hurricane 5", lambda: storm("5"))]),
]


def main():
    theme.configure({}) if False else None
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "individual").mkdir(parents=True)
    cols, cell, pad, head = 6, 300, 30, 70
    rows = sum(math.ceil(len(items) / cols) for _, items in SECTIONS)
    W = cols * cell + 2 * pad
    H = 170 + rows * (cell + 40) + len(SECTIONS) * head + pad
    sheet = theme._background(W, H) if hasattr(theme, "_background") else Image.new("RGB", (W, H), C["bg_bot"])
    sheet = sheet.resize((W, H)).convert("RGB")
    d = ImageDraw.Draw(sheet, "RGBA")  # RGBA mode blends translucent cards instead of overwriting
    d.text((pad, 50), "WEATHER ICON SHEET", font=font("bold", 50), fill=(255, 255, 255, 255), anchor="lm")
    d.text((pad, 118), "METEOROLOGIST RICKY MATTHEWS  ·  icons used in the weather graphics", font=font("medium", 24), fill=(*C["muted"], 255), anchor="lm")
    y = 170
    for title, items in SECTIONS:
        d.text((pad, y + 28), title, font=font("bold", 30), fill=(*C["rain"], 255), anchor="lm")
        d.line([(pad, y + 54), (W - pad, y + 54)], fill=(255, 255, 255, 70), width=2)
        y += head
        for i, (fn, label, mk) in enumerate(items):
            im = mk()
            im.save(OUT / "individual" / f"{fn}.png")
            cx, cy = pad + (i % cols) * cell, y + (i // cols) * (cell + 40)
            d.rounded_rectangle([cx + 8, cy, cx + cell - 8, cy + cell + 30], radius=18, fill=(255, 255, 255, 16))
            t = im.resize((cell - 70, cell - 70), Image.LANCZOS)
            sheet.paste(t, (cx + 35, cy + 14), t)
            fs = 17
            while fs > 9 and d.textlength(label.upper(), font=font("bold", fs)) > cell - 30:
                fs -= 1
            d.text((cx + cell / 2, cy + cell - 20), label.upper(), font=font("bold", fs), fill=(255, 255, 255, 255), anchor="mm")
            d.text((cx + cell / 2, cy + cell + 8), fn + ".png", font=font("regular", 14), fill=(*C["muted"], 255), anchor="mm")
        y += math.ceil(len(items) / cols) * (cell + 40)
    sheet.convert("RGB").save(OUT / "icon_sheet.png")
    print("wrote", OUT, len(list((OUT / "individual").glob("*.png"))), "icons")


if __name__ == "__main__":
    main()
