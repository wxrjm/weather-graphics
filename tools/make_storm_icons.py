"""Build the tropical storm symbols in wxgfx/data/storm_icons/ (run once; the PNGs ship with the project).

L.png      low / remnant / post-tropical / disturbance   (red serif "L")
TS.png     tropical depression or storm                  (red ring + two tails, open center)
1.png-5.png hurricane category 1-5                       (red filled swirl, white number)
Drawn 4x larger than saved and downsampled for smooth edges. A thin white halo keeps them readable on the
dark navy maps.
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "wxgfx" / "data" / "storm_icons"
RED = (213, 0, 0, 255)
S = 1024           # working size
SAVE = 256         # saved size
R = 170            # ring outer radius
SERIF = sys.argv[1] if len(sys.argv) > 1 else "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
NUMFONT = str(ROOT / "fonts" / "Poppins-Bold.ttf")


def tail(d, cx, cy, flip):
    """Curved, tapering tail: spirals outward from the ring and sweeps away, thinning to a point."""
    pts_out, pts_in = [], []
    n = 80
    for i in range(n + 1):
        t = i / n
        ang = math.radians(180 - 160 * t)          # left side -> sweeping over the top to the right
        rad = R * (0.62 + 1.30 * t ** 1.1)         # grows away from the ring (outer edge starts flush with it)
        half = R * 0.38 * (1 - t) ** 0.9 + 2       # tapers to a point
        x, y = cx + rad * math.cos(ang), cy - rad * math.sin(ang)
        nx, ny = math.cos(ang), -math.sin(ang)     # outward normal-ish
        pts_out.append((x + nx * half, y + ny * half))
        pts_in.append((x - nx * half, y - ny * half))
    poly = pts_out + pts_in[::-1]
    if flip:
        poly = [(2 * cx - x, 2 * cy - y) for x, y in poly]
    d.polygon(poly, fill=RED)


def swirl(filled, label=None):
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = cy = S / 2
    tail(d, cx, cy, False)
    tail(d, cx, cy, True)
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=RED)
    if not filled:
        h = R * 0.50
        d.ellipse([cx - h, cy - h, cx + h, cy + h], fill=(0, 0, 0, 0))
    if label:
        f = ImageFont.truetype(NUMFONT, int(R * 1.25))
        d.text((cx, cy + R * 0.06), label, font=f, fill=(255, 255, 255, 255), anchor="mm")
    return im


def letter_l():
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(SERIF, int(S * 0.62))
    d.text((S / 2, S / 2), "L", font=f, fill=RED, anchor="mm")
    return im


def halo(im, px=18):
    a = im.getchannel("A").filter(ImageFilter.MaxFilter(px * 2 + 1)).filter(ImageFilter.GaussianBlur(3))
    out = Image.new("RGBA", im.size, (255, 255, 255, 0))
    out.putalpha(a.point(lambda v: int(v * 0.85)))
    out.alpha_composite(im)
    return out


def save(im, name, pad=1.0):
    bbox = im.getchannel("A").getbbox()
    side = (max(bbox[2] - bbox[0], bbox[3] - bbox[1]) + 8) * pad
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    sq = im.crop((int(cx - side / 2), int(cy - side / 2), int(cx + side / 2), int(cy + side / 2)))
    sq.resize((SAVE, SAVE), Image.LANCZOS).save(OUT / f"{name}.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    save(halo(letter_l()), "L", pad=1.45)  # the L reads a bit smaller than the swirls, like NHC
    save(halo(swirl(False)), "TS")
    for c in range(1, 6):
        save(halo(swirl(True, str(c))), str(c))
    print("wrote", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))
