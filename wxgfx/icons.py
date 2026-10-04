"""Vector weather icons drawn with Pillow (no image assets needed)."""
import math
from .theme import C, z


def _circle(d, cx, cy, r, fill):
    d.ellipse([z(cx - r), z(cy - r), z(cx + r), z(cy + r)], fill=fill)


def _sun(d, cx, cy, r):
    for i in range(8):
        a = i * math.pi / 4
        d.line([(z(cx + math.cos(a) * r * 1.35), z(cy + math.sin(a) * r * 1.35)),
                (z(cx + math.cos(a) * r * 1.75), z(cy + math.sin(a) * r * 1.75))],
               fill=C["sun"], width=max(2, z(r * 0.16)))
    _circle(d, cx, cy, r, C["sun"])


def _moon(d, cx, cy, r):
    _circle(d, cx, cy, r, (240, 236, 214, 255))
    _circle(d, cx - r * 0.5, cy - r * 0.38, r * 0.82, (0, 0, 0, 0))  # erase -> crescent


def _cloud(d, cx, cy, w, color):
    d.rounded_rectangle([z(cx - w / 2), z(cy), z(cx + w / 2), z(cy + w * 0.3)], radius=z(w * 0.15), fill=color)
    _circle(d, cx - w * 0.2, cy + w * 0.03, w * 0.2, color)
    _circle(d, cx + w * 0.04, cy - w * 0.06, w * 0.26, color)
    _circle(d, cx + w * 0.27, cy + w * 0.08, w * 0.16, color)


def _drops(d, cx, top, w, n=3, color=None):
    color = color or C["rain"]
    for i in range(n):
        x = cx - w * 0.25 + i * w * 0.25
        d.line([(z(x), z(top)), (z(x - w * 0.07), z(top + w * 0.2))], fill=color, width=max(2, z(w * 0.05)))


def _flakes(d, cx, top, w):
    for i in range(3):
        x, y, r = cx - w * 0.25 + i * w * 0.25, top + w * (0.08 if i % 2 else 0.16), w * 0.06
        for k in range(3):
            a = k * math.pi / 3
            d.line([(z(x - math.cos(a) * r), z(y - math.sin(a) * r)),
                    (z(x + math.cos(a) * r), z(y + math.sin(a) * r))], fill=(255, 255, 255, 255), width=max(2, z(w * 0.025)))


def _bolt(d, cx, top, w):
    pts = [(0.02, 0), (-0.12, 0.2), (-0.01, 0.2), (-0.08, 0.38), (0.13, 0.13), (0.02, 0.13), (0.1, 0)]
    d.polygon([(z(cx + x * w), z(top + y * w)) for x, y in pts], fill=C["bolt"])


def draw_icon(cv, kind, cx, cy, size, night=False):
    w = size

    def fn(d):
        body = cy - w * 0.12  # cloud top reference
        if kind == "clear":
            (_moon if night else _sun)(d, cx, cy, w * 0.26)
        elif kind in ("few", "partly", "showers"):
            orb = cx + w * 0.14, cy - w * 0.16
            (_moon if night else _sun)(d, orb[0], orb[1], w * (0.19 if kind != "few" else 0.22))
            cw = w * (0.62 if kind == "few" else 0.78)
            _cloud(d, cx - w * 0.06, body + (w * 0.14 if kind == "few" else w * 0.04), cw, C["cloud"])
            if kind == "showers":
                _drops(d, cx - w * 0.04, body + w * 0.32, w * 0.8)
        elif kind in ("mostly_cloudy", "cloudy"):
            _cloud(d, cx + w * 0.12, body - w * 0.1, w * 0.6, C["cloud_dark"])
            _cloud(d, cx - w * 0.05, body + w * 0.05, w * 0.8, C["cloud"])
        elif kind == "rain":
            _cloud(d, cx, body - w * 0.06, w * 0.86, C["cloud"])
            _drops(d, cx + w * 0.02, body + w * 0.26, w, n=3)
        elif kind == "tstorm":
            _cloud(d, cx, body - w * 0.1, w * 0.86, C["cloud_dark"])
            _drops(d, cx - w * 0.1, body + w * 0.22, w * 0.7, n=2)
            _bolt(d, cx + w * 0.12, body + w * 0.16, w)
        elif kind in ("snow", "mix"):
            _cloud(d, cx, body - w * 0.06, w * 0.86, C["cloud"])
            if kind == "mix":
                _drops(d, cx - w * 0.14, body + w * 0.26, w * 0.6, n=2)
                _flakes(d, cx + w * 0.2, body + w * 0.24, w * 0.6)
            else:
                _flakes(d, cx, body + w * 0.24, w)
        elif kind == "fog":
            _cloud(d, cx, body - w * 0.1, w * 0.72, C["cloud"])
            for i in range(3):
                y = body + w * (0.28 + i * 0.1)
                d.rounded_rectangle([z(cx - w * 0.38 + i * w * 0.04), z(y), z(cx + w * 0.38 - i * w * 0.06), z(y + w * 0.045)],
                                    radius=z(w * 0.02), fill=(200, 208, 222, 255))
        elif kind == "wind":
            for i, (y, ln) in enumerate([(-0.16, 0.62), (0.0, 0.8), (0.16, 0.5)]):
                yy = cy + y * w
                x0 = cx - w * 0.4
                d.line([(z(x0), z(yy)), (z(x0 + ln * w * 0.85), z(yy))], fill=C["cloud"], width=max(2, z(w * 0.05)))
                ex, r = x0 + ln * w * 0.85, w * 0.07
                d.arc([z(ex - r), z(yy - 2 * r), z(ex + r), z(yy)], start=-90, end=110, fill=C["cloud"], width=max(2, z(w * 0.05)))
        else:
            _cloud(d, cx, body, w * 0.8, C["cloud"])

    cv.layer(fn)


def cloud_outline(cv, cx, cy, w):
    """Small line-art cloud + bolt for the text wordmark fallback."""
    def fn(d):
        col = (255, 255, 255, 255)
        lw = max(2, z(2.2))
        d.arc([z(cx - w * 0.45), z(cy - w * 0.05), z(cx - w * 0.05), z(cy + w * 0.35)], 90, 270, fill=col, width=lw)
        d.arc([z(cx - w * 0.25), z(cy - w * 0.3), z(cx + w * 0.25), z(cy + w * 0.2)], 180, 340, fill=col, width=lw)
        d.arc([z(cx + w * 0.05), z(cy - w * 0.05), z(cx + w * 0.45), z(cy + w * 0.35)], 270, 90, fill=col, width=lw)
        d.line([(z(cx - w * 0.25), z(cy + w * 0.35)), (z(cx - w * 0.02), z(cy + w * 0.35))], fill=col, width=lw)
        d.line([(z(cx + w * 0.12), z(cy + w * 0.35)), (z(cx + w * 0.25), z(cy + w * 0.35))], fill=col, width=lw)
        _bolt(d, cx + w * 0.04, cy + w * 0.1, w * 0.9)
    cv.layer(fn)
