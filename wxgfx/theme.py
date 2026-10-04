"""Drawing primitives in the Meteorologist Ricky Matthews look:
navy gradient card, bold white uppercase headers with a rule, left accent bars.
Everything is drawn at 2x and downsampled for clean edges. Design coords are 1920x1080.
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, S = 1920, 1080, 2
# output formats: wide = TV/OBS/YouTube, vertical = Stories/Reels/TikTok (9:16), post = FB/IG feed (4:5)
FORMATS = {"wide": (1920, 1080), "vertical": (1080, 1920), "post": (1080, 1350), "square": (1080, 1080)}
FMT = "wide"


def set_format(name):
    global FMT
    FMT = name if name in FORMATS else "wide"
ROOT = Path(__file__).resolve().parent.parent

C = {
    "bg_top": (27, 43, 70), "bg_bot": (13, 21, 38), "glow": (44, 74, 112),
    "panel": (255, 255, 255, 16), "panel_hi": (255, 255, 255, 26),
    "text": (255, 255, 255), "muted": (176, 190, 212), "rule": (255, 255, 255),
    "bar": (236, 233, 224), "rain": (88, 170, 255), "sun": (255, 198, 41),
    "cloud": (236, 241, 248), "cloud_dark": (150, 162, 182), "bolt": (255, 214, 0),
    "shadow": (10, 16, 30),
}
FONT_FILES = {"bold": "Poppins-Bold.ttf", "medium": "Poppins-Medium.ttf",
              "regular": "Poppins-Regular.ttf", "light": "Poppins-Light.ttf"}
_fonts = {}


def configure(cfg):
    for k, v in (cfg.get("colors") or {}).items():
        C[k] = tuple(v)
    for k, v in (cfg.get("fonts") or {}).items():
        FONT_FILES[k] = v


def font(weight, size):
    key = (weight, size)
    if key not in _fonts:
        p = Path(FONT_FILES[weight])
        if not p.is_absolute():
            p = ROOT / "fonts" / p
        _fonts[key] = ImageFont.truetype(str(p), int(size * S))
    return _fonts[key]


def z(v):
    return int(round(v * S))


def _background(w, h):
    size = (w * S, h * S)
    mask = Image.linear_gradient("L").resize(size)
    img = Image.composite(Image.new("RGB", size, C["bg_bot"]), Image.new("RGB", size, C["bg_top"]), mask)
    # soft top-left glow: blurred ellipse at low res, upscaled
    small = Image.new("L", (240, int(240 * h / w)), 0)
    ImageDraw.Draw(small).ellipse([-90, -80, 110, 70], fill=150)
    m = small.filter(ImageFilter.GaussianBlur(28)).resize(size, Image.BICUBIC)
    return Image.composite(Image.new("RGB", size, C["glow"]), img, m)


class Canvas:
    def __init__(self, cfg):
        self.cfg = cfg
        self.fmt = FMT
        self.W, self.H = FORMATS[FMT]
        self.tall = self.H >= self.W  # square uses the narrow layouts too
        self.square = self.H == self.W
        self.M = 70 if not self.tall else 56  # side margin
        self.img = _background(self.W, self.H)  # RGB so RGBA fills blend
        self.d = ImageDraw.Draw(self.img, "RGBA")

    # ---- primitives (design coordinates) ----
    def rect(self, x, y, w, h, fill, r=0):
        self.d.rounded_rectangle([z(x), z(y), z(x + w), z(y + h)], radius=z(r), fill=fill)

    def line(self, pts, fill, width):
        self.d.line([(z(a), z(b)) for a, b in pts], fill=fill, width=z(width), joint="curve")

    def text(self, x, y, s, size, weight="bold", fill=None, anchor="la", stroke=0, stroke_fill=None, maxw=None):
        size = self.fit(s, size, weight, maxw) if maxw else size
        self.d.text((z(x), z(y)), s, font=font(weight, size), fill=fill or C["text"], anchor=anchor,
                    stroke_width=z(stroke), stroke_fill=stroke_fill or C["shadow"])
        return size

    def width(self, s, size, weight="bold"):
        return self.d.textlength(s, font=font(weight, size)) / S

    def fit(self, s, size, weight, maxw, floor=14):
        while size > floor and self.width(s, size, weight) > maxw:
            size -= 1
        return size

    def wrap(self, s, size, weight, maxw):
        lines, cur = [], ""
        for word in s.split():
            t = f"{cur} {word}".strip()
            if self.width(t, size, weight) <= maxw or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def paragraph(self, x, y, s, size, weight, maxw, max_lines=4, lh=1.32, fill=None, anchor="la", valign=None, box_h=None):
        """Wrap text; shrink until it fits max_lines. valign='middle' centers in box_h."""
        while True:
            lines = self.wrap(s, size, weight, maxw)
            if len(lines) <= max_lines or size <= 16:
                break
            size -= 1
        total = len(lines) * size * lh
        if valign == "middle" and box_h:
            y = y + (box_h - total) / 2
        for i, ln in enumerate(lines):
            ax = x
            self.text(ax, y + i * size * lh, ln, size, weight, fill, anchor=anchor)
        return total

    def layer(self, draw_fn):
        """Draw onto a transparent layer (allows erasing, e.g. moon crescents)."""
        lay = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        draw_fn(ImageDraw.Draw(lay))
        self.img = Image.alpha_composite(self.img.convert("RGBA"), lay).convert("RGB")
        self.d = ImageDraw.Draw(self.img, "RGBA")

    # ---- theme pieces ----
    @property
    def top(self):
        """First usable y below the header."""
        return 205

    @property
    def bottom(self):
        """Last usable y above the footer."""
        return self.H - 75

    def split(self):
        """(map_box, panel_box) for map + side-panel graphics: side by side when wide, stacked when tall."""
        top, M = self.top, self.M
        if not self.tall:
            return (70, top, 1020, 800), (1120, top, 730, 800)
        mw = self.W - 2 * M
        mh = int(mw * (1.0 if self.fmt == "vertical" else 0.42 if self.fmt == "square" else 0.52))
        py = top + mh + 22
        return (M, top, mw, mh), (M, py, mw, self.bottom - py)

    def header(self, title, subtitle=None, rule_color=None, subtitle_color=None):
        M, maxw = self.M, self.W - 2 * self.M - (220 if self.tall else 430)
        self.text(M, 118, title.upper(), 60 if not self.tall else 54, "bold", anchor="ls", maxw=maxw)
        rule_y = 134
        if subtitle:
            self.text(M + 2, 164, subtitle.upper(), 27 if not self.tall else 24, "bold", subtitle_color, anchor="ls",
                      maxw=maxw + (0 if not self.tall else 20))
            rule_y = 178
        self.line([(M, rule_y), (self.W - M, rule_y)], rule_color or C["rule"], 2.5 if not rule_color else 5)
        self.logo(rule_y)
        return rule_y

    def logo(self, rule_y):
        path = self.cfg.get("logo_path")
        if path and Path(path).exists():
            lg = Image.open(path).convert("RGBA")
            h = z(112 if not self.tall else 100)
            lg = lg.resize((int(lg.width * h / lg.height), h), Image.LANCZOS)
            self.img.paste(lg, (z(self.W - self.M) - lg.width, z(rule_y - 8) - h), lg)
            self.d = ImageDraw.Draw(self.img, "RGBA")
            return
        # text wordmark fallback (drop your real logo PNG in via config "logo_path")
        cx, base = self.W - self.M - 108, rule_y - 8
        from . import icons
        icons.cloud_outline(self, cx, base - 78, 70)
        self.spaced(cx, base - 30, "METEOROLOGIST", 13, "medium", 3)
        self.text(cx, base - 4, self.cfg.get("brand_name", "RICKY MATTHEWS").upper(), 20, "bold", anchor="ms")

    def spaced(self, cx, y, s, size, weight, spacing):
        total = sum(self.width(ch, size, weight) for ch in s) + spacing * (len(s) - 1)
        x = cx - total / 2
        for ch in s:
            self.text(x, y, ch, size, weight, C["muted"], anchor="ls")
            x += self.width(ch, size, weight) + spacing

    def accent_row(self, x, y, w, h, bar=None):
        self.rect(x + 8, y, w - 8, h, C["panel"])
        self.rect(x, y, 8, h, bar or C["rule"])

    def footer(self, pkg, show_location=False, source=None, show_source=True):
        loc = pkg["location"]
        src = source or pkg.get("source", "NWS NDFD")
        parts = ([f"{loc['name'].upper()} ({loc['station']})"] if show_location else []) + \
                ([f"DATA: {src.upper()}"] if show_source else []) + [f"GRAPHIC CREATED: {pkg['issued_label'].upper()}"]
        self.text(self.M, self.H - 34, "  ·  ".join(parts), 19 if not self.tall else 18, "medium", C["muted"],
                  anchor="ls", maxw=self.W - 2 * self.M)

    def save(self, path):
        self.img.resize((self.W, self.H), Image.LANCZOS).save(path, optimize=True)
