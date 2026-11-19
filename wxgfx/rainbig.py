"""Big-text rainfall outlook: how much rain Norfolk could see in the next 48 hours and the next 5 days.

Giant headline, two big total cards (48 hours / 5 days, coloured by amount, with the likely range), the daily
amounts as small bars, a one-line summary, and a navy tagline banner like the other Big Text graphics.
Data: NWS NDFD rainfall (hourly for 48 h; daily totals for 5 days, using model guidance past NDFD's ~3-day limit).
Config: rain_big_days (5), rain_big_hours (48).
"""
from datetime import datetime

from .bigtext import NAVY, _wrap2
from .summarize import qpf_range
from .theme import C, Canvas

RAMP = [(0.0, (150, 165, 190)), (0.05, (150, 200, 244)), (0.25, (66, 138, 224)), (0.75, (253, 149, 0)),
        (1.5, (230, 40, 50)), (3.0, (190, 70, 210))]


def _col(q):
    c = RAMP[0][1]
    for t, k in RAMP:
        if q >= t:
            c = k
    return c


def _range(q):
    r = qpf_range(q)
    return r or ("A trace to a few hundredths" if q >= 0.01 else "No measurable rain")


def _amount(q):
    return f'{q:.2f}"' if q >= 0.01 else "0.00\""


def _word(q):
    return ("DRY" if q < 0.05 else "LIGHT RAIN" if q < 0.25 else "MODERATE RAIN" if q < 0.5 else "HEAVY RAIN" if q < 1.25
            else "VERY HEAVY RAIN")


def _card(cv, x, y, w, h, label, q, sub, col, tall):
    cv.rect(x, y, w, h, (255, 255, 255, 18), r=18)
    cv.rect(x, y + 18, 10, h - 36, (*col, 255), r=5)
    cv.text(x + 40, y + 24, label, 34 if not tall else 36, "bold", C["muted"], anchor="lt")
    if tall:
        size = cv.fit(_amount(q), 170, "bold", w * 0.5)
        cv.text(x + 40, y + h * 0.58, _amount(q), size, "bold", col, anchor="lm", stroke=1.5)
        cv.text(x + w - 34, y + h * 0.5, _word(q), 36, "bold", anchor="rm", maxw=w * 0.42)
        cv.text(x + w - 34, y + h * 0.5 + 48, _range(q).upper(), 28, "medium", C["muted"], anchor="rm", maxw=w * 0.45)
    else:  # two columns: label, huge number, then the wording underneath
        size = cv.fit(_amount(q), 190, "bold", w - 80)
        cv.text(x + 40, y + h * 0.5, _amount(q), size, "bold", col, anchor="lm", stroke=1.5)
        cv.text(x + 40, y + h - 92, _word(q), 40, "bold", anchor="lt", maxw=w - 70)
        cv.text(x + 40, y + h - 44, _range(q).upper(), 28, "medium", C["muted"], anchor="lt", maxw=w - 70)
    return y + h


def rain_totals_big(pkg, cfg):
    hrs = (pkg.get("hourly_ext") or [])[:cfg.get("rain_big_hours", 48)]
    ndays = cfg.get("rain_big_days", 5)
    start = 1 if pkg.get("evening_mode") else 0
    days = pkg["days"][start:start + ndays]
    have = [d for d in days if d.get("qpf") is not None]
    if len(hrs) < 24 or not have:
        return None
    q48 = sum(h.get("qpf") or 0 for h in hrs)
    q5 = sum(d["qpf"] for d in have)
    nd = len(have)
    cv = Canvas(cfg)
    W, H, M, tall = cv.W, cv.H, cv.M, cv.tall
    cv.logo(134 if not tall else 150)
    title = "HOW MUCH RAIN COULD WE SEE?"
    if tall:
        lines, size = _wrap2(cv, title, W - 2 * M - 260, 112)
    else:
        size = cv.fit(title, 96, "bold", W - 2 * M - 330)
        lines = (title,)
    for i, l in enumerate(lines):
        cv.text(M, 40 + size * (i + 1) * 1.0 + (i * 6), l, size, "bold", anchor="ls")
    top = 40 + size * len(lines) + 40
    cv.line([(M, top), (W - M, top)], C["rule"], 3)
    tag_h = 110
    bottom = H - tag_h - 24
    top += 24
    gap = 22
    # 48-hour and 5-day cards
    avail = bottom - top
    if tall:
        ch = (avail - gap) * 0.30
        y = _card(cv, M, top, W - 2 * M, ch, f"NEXT {len(hrs)} HOURS", q48, "", _col(q48), tall) + gap
        y2 = _card(cv, M, y, W - 2 * M, ch, f"NEXT {nd} DAYS", q5, "", _col(q5), tall) + gap
    else:
        ch, cw = avail * 0.56, (W - 2 * M - gap) / 2
        _card(cv, M, top, cw, ch, f"NEXT {len(hrs)} HOURS", q48, "", _col(q48), tall)
        _card(cv, M + cw + gap, top, cw, ch, f"NEXT {nd} DAYS", q5, "", _col(q5), tall)
        y2 = top + ch + gap
    # daily bars
    bh = bottom - y2
    cv.rect(M, y2, W - 2 * M, bh, (255, 255, 255, 14), r=18)
    n = len(have)
    slot = (W - 2 * M - 60) / n
    vmax = max(0.5, max(d["qpf"] for d in have) * 1.15)
    base = y2 + bh - 60
    tp = y2 + 56
    for i, d in enumerate(have):
        cx = M + 30 + slot * (i + 0.5)
        q = d["qpf"]
        bh_ = max(4, (base - tp - 20) * q / vmax) if q >= 0.01 else 4
        col = _col(q)
        cv.rect(cx - slot * 0.28, base - bh_, slot * 0.56, bh_, (*col, 255), r=8)
        cv.text(cx, base - bh_ - 10, _amount(q), 30 if not tall else 32, "bold", anchor="ms", maxw=slot - 8)
        cv.text(cx, base + 40, d["dow"], 30 if not tall else 32, "bold", C["muted"], anchor="ms")
    # tagline banner (same look as the other Big Text graphics)
    ty = H - tag_h
    cv.rect(0, ty, W, tag_h, (*NAVY, 255))
    cv.line([(0, ty), (W, ty)], (255, 255, 255, 200), 3)
    wet = max(have, key=lambda d: d["qpf"])
    if q5 < 0.05:
        tag = "NO SIGNIFICANT RAIN EXPECTED"
    else:
        tag = f"{len(hrs)} HR: {_amount(q48)}  ·  {nd} DAY: {_amount(q5)}"
        if wet["qpf"] >= 0.25:
            tag = f"WETTEST: {wet['dow_long'].upper()}  ·  " + tag if cv.width(tag, 44, "bold") < W * 0.55 else tag
    ts = cv.fit(tag, 50, "bold", W - 2 * M, floor=24)
    cv.text(W / 2, ty + tag_h / 2 + 2, tag, ts, "bold", (255, 255, 255), anchor="mm", maxw=W - 2 * M)
    return cv


def rain_big_graphics(pkg, cfg):
    g = rain_totals_big(pkg, cfg)
    return [("rain_totals_big", g)] if g else None
