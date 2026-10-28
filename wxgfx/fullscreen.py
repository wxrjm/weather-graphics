"""Full-screen map layout: the map fills the entire image, the title floats over a dark fade at the
top, and the information runs in bars along the bottom (headline card + local value chips).

Used for the drought monitor and as "_full" twins of the other map graphics (config "fullscreen_maps").
map_fn(pw, ph, view) must return an RGBA image z(pw) x z(ph) (outlookmap.draw_map does).
"""
from PIL import Image, ImageDraw

from .theme import C, Canvas, z


def expand_view(box, top_frac, bot_frac):
    """Grow a (w, e, s, n) box so its contents land in the visible middle of the image."""
    w, e, s, n = box
    span = (n - s) / max(0.2, 1 - top_frac - bot_frac)
    return w, e, s - span * bot_frac, n + span * top_frac


def _fade(cv, y0, y1, a0, a1):
    """Vertical navy fade between y0 and y1 (alpha a0 -> a1)."""
    W_, h = z(cv.W), max(1, z(y1 - y0))
    grad = Image.new("L", (1, h))
    for i in range(h):
        grad.putpixel((0, i), int(a0 + (a1 - a0) * i / max(1, h - 1)))
    band = Image.new("RGBA", (W_, h), (13, 21, 38, 255))
    band.putalpha(grad.resize((W_, h)))
    base = cv.img.convert("RGBA")
    base.alpha_composite(band, (0, z(y0)))
    cv.img = base.convert("RGB")
    cv.d = ImageDraw.Draw(cv.img, "RGBA")


def _ink(col):
    return (20, 28, 46) if 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2] > 150 else C["text"]


def credit(cv, text, right=None, bottom=None):
    """Small 'data from' strip in the bottom-right corner (e.g. "DATA: NADOCAST MODEL")."""
    if not text:
        return
    lab = "DATA FROM"
    f1, f2 = 14, 19
    w = cv.width(lab, f1, "bold") + cv.width(text, f2, "bold") + 46
    h = 38
    x1 = right if right is not None else cv.W - cv.M
    y1 = bottom if bottom is not None else cv.H - 18
    x0, y0 = x1 - w, y1 - h
    cv.rect(x0, y0, w, h, (13, 21, 38, 235), r=10)
    cv.rect(x0, y0, 6, h, (88, 150, 255, 255), r=3)
    cv.text(x0 + 18, y0 + h / 2 + 1, lab, f1, "bold", C["muted"], anchor="lm")
    cv.text(x0 + 26 + cv.width(lab, f1, "bold"), y0 + h / 2 + 1, text, f2, "bold", anchor="lm")
    return w


def layout(cv):
    """Bar-area geometry for the current format: (bars_top, n_cols, n_rows)."""
    if not cv.tall:
        return cv.H - 75 - 176, 4, 2
    if cv.fmt == "vertical":
        return cv.H - 75 - 520, 2, 4
    if cv.fmt == "square":
        return cv.H - 75 - 300, 2, 2
    return cv.H - 75 - 360, 2, 3


SIDE_W = 560  # width of the info column on the right of wide full-screen graphics
SIDE_GAP = 26


def view_for(cv, box):
    from . import outlookmap
    if not cv.tall:  # wide: info column on the right -> push the map's content into the left part of the image
        W, H = cv.W, cv.H
        b = expand_view(box, 215 / H, 75 / H)
        w0, e0, s0, n0 = outlookmap._view(W, H, b)
        avail = (W - cv.M - SIDE_W - SIDE_GAP) / W  # share of the width left for the map's content
        content = (box[1] - box[0]) / (e0 - w0)
        g = max(1.0, content / avail)
        cx, cy = (w0 + e0) / 2, (s0 + n0) / 2
        sx, sy = (e0 - w0) * g, (n0 - s0) * g
        shift = (1 - avail) / 2 * 0.0 + (SIDE_W + SIDE_GAP + cv.M - cv.M) / 2 / W  # content centre moves left by half the column
        w1, e1 = cx - sx / 2, cx + sx / 2
        return w1 + shift * sx, e1 + shift * sx, cy - sy / 2, cy + sy / 2
    bars_top, _, _ = layout(cv)
    top_frac = 210 / cv.H
    bot_frac = (cv.H - bars_top + 64) / cv.H
    return expand_view(box, top_frac, bot_frac)


def _place_legend(cv, overlay, subtitle):
    """Put the legend in the top banner: on the subtitle line when it fits beside the subtitle, otherwise on a row
    right under the banner rule."""
    from PIL import Image
    S = z(1)
    probe = Canvas(cv.cfg)
    probe.img = Image.new("RGB", cv.img.size, (0, 0, 0))
    probe.d = ImageDraw.Draw(probe.img, "RGBA")
    full_w = cv.W - 2 * cv.M
    overlay(probe, 0, 100, full_w)
    bb = probe.img.getbbox()
    if not bb:
        return
    dx0, dy0 = bb[0] / S, bb[1] / S - 100
    lw, lh = (bb[2] - bb[0]) / S, (bb[3] - bb[1]) / S
    size = cv.fit(subtitle.upper(), 27 if not cv.tall else 24, "bold", cv.W - 2 * cv.M - (430 if not cv.tall else 220))
    sub_end = cv.M + 2 + cv.width(subtitle.upper(), size, "bold")
    right_limit = cv.W - cv.M - (250 if not cv.tall else 130)
    if lh <= 60 and sub_end + 30 + lw <= right_limit:
        overlay(cv, sub_end + 30 - dx0, 155 - lh / 2 - dy0, lw)  # same line as the subtitle
    else:
        overlay(cv, cv.M - dx0, 192 - dy0, full_w)  # row under the rule


def attach(cv, **spec):
    """Remember how to redraw this map graphic full-screen (run.py makes the '_full' twin)."""
    cv.full_spec = spec
    return cv


def render(pkg, cfg, title, subtitle, map_fn, box, head_label, head_value, head_col, meaning, rows,
           overlay=None, source=None, callout_rows=None, big_caption=None, big_tagline=None, credit_text=None):
    """overlay(cv, x, y, maxw) draws a legend / color bar just above the bars (returns nothing)."""
    from . import alertmap
    from .outlookmap import VIEW_BOX
    if tuple(box) in (tuple(VIEW_BOX), tuple(cfg.get("outlook_view") or VIEW_BOX)):
        # local maps: zoom in on the Hampton Roads DMA (the bars take up the bottom of the frame)
        box = tuple(cfg.get("fullscreen_local_view") or (-77.7, -75.2, 36.05, 37.85))
    cv = Canvas(cfg)
    side = not cv.tall
    bars_top, ncol, nrow = layout(cv)
    sx = cv.W - cv.M - SIDE_W  # left edge of the right-hand info column (wide only)
    if side:
        alertmap.KEEP_OUT[:] = [(0, 0, cv.W, 245), (sx - 14, 0, cv.W, cv.H)]  # no map labels under the banner / info column
    else:
        alertmap.KEEP_OUT[:] = [(0, 0, cv.W, 245), (0, bars_top - 84, cv.W, cv.H)]
    try:
        lay = map_fn(cv.W, cv.H, view_for(cv, box))
    finally:
        alertmap.KEEP_OUT[:] = []
    base = cv.img.convert("RGBA")
    base.alpha_composite(lay.resize(base.size) if lay.size != base.size else lay)
    cv.img = base.convert("RGB")
    cv.d = ImageDraw.Draw(cv.img, "RGBA")
    _fade(cv, 0, 250, 235, 0)
    if side:
        _fade(cv, cv.H - 150, cv.H, 0, 235)
    else:
        _fade(cv, bars_top - 110, cv.H, 0, 245)
    cv.header(title, subtitle)
    if overlay:
        _place_legend(cv, overlay, subtitle)
    M, W = cv.M, cv.W - 2 * cv.M
    bottom = cv.H - 75
    if side:
        hx, hy, hw, hh = sx, 215, SIDE_W, 196
        gx, gy, gw = sx, hy + hh + 6, SIDE_W
        gh = bottom - gy
        ncol, nrow = 1, 8
    elif not cv.tall:
        hx, hy, hw, hh = M, bars_top, 560, bottom - bars_top
        gx, gy, gw, gh = M + 580, bars_top, W - 580, bottom - bars_top
    else:
        hh = 150 if cv.fmt != "square" else 142
        hx, hy, hw = M, bars_top, W
        gx, gy, gw, gh = M, bars_top + hh + 14, W, bottom - bars_top - hh - 14
    # headline card
    if side:  # one panel holds the headline and every value row
        nrows = min(len(rows), 8)
        rh0 = min(80, (gh - 4) / max(1, nrows)) if nrows else 0
        cv.rect(hx, hy, hw, min(bottom - hy, hh + 4 + nrows * rh0 + 12), (20, 31, 54, 235), r=16)
    else:
        cv.rect(hx, hy, hw, hh, (20, 31, 54, 235), r=16)
    cv.rect(hx, hy, 10, hh, (*head_col, 255), r=5)
    cv.text(hx + 30, hy + 18, head_label, 19, "bold", C["muted"], anchor="lt", maxw=hw - 50)
    pw = min(hw - 60, cv.width(head_value, 34, "bold") + 44)
    cv.rect(hx + 30, hy + 48, pw, 52, (*head_col, 255), r=12)
    cv.text(hx + 30 + pw / 2, hy + 74, head_value, 34, "bold", _ink(head_col), anchor="mm", maxw=pw - 24)
    if meaning:
        cv.paragraph(hx + 30, hy + 110, meaning, 19, "regular", hw - 60, max_lines=3 if side else 2 if not cv.tall else 1, lh=1.22)
    # value chips
    rows = rows[:ncol * nrow]
    if rows:
        gap = 0 if side else 12
        cw = (gw - gap * (ncol - 1)) / ncol
        nr = -(-len(rows) // ncol)
        rh = min(80, (gh - gap * (nr - 1)) / max(1, nr))
        if side:
            gy += 4
            cv.line([(gx + 24, gy - 6), (gx + gw - 24, gy - 6)], (255, 255, 255, 50), 2)
        for k, (name, col, val) in enumerate(rows):
            r, c = divmod(k, ncol)
            x, y = gx + c * (cw + gap), gy + r * (rh + gap)
            if not side:
                cv.rect(x, y, cw, rh, (20, 31, 54, 235), r=12)
            elif k:
                cv.line([(x + 24, y), (x + cw - 24, y)], (255, 255, 255, 28), 1)
            cv.rect(x + 14, y + rh * 0.22, 14, rh * 0.56, (*col, 255) if col else (70, 86, 112, 255), r=4)
            if rh >= 60:  # two lines: small label over a big value
                cv.text(x + 40, y + rh * 0.3, name.upper(), min(17, rh * 0.22), "bold", C["muted"], anchor="lm",
                        maxw=cw - 56)
                cv.text(x + 40, y + rh * 0.68, val, min(30, rh * 0.4), "bold", anchor="lm", maxw=cw - 56)
            else:
                fs = min(24, rh * 0.36)
                cv.text(x + 40, y + rh / 2, name, fs, "medium", anchor="lm", maxw=cw * 0.55)
                cv.text(x + cw - 16, y + rh / 2, val, fs, "bold", anchor="rm", maxw=cw * 0.4)
    cv.footer(pkg, source=source, show_source=bool(source) and not (credit_text and cv.tall))
    credit(cv, credit_text)
    return cv
