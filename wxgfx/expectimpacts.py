"""WHAT TO EXPECT - IMPACTS: the What To Expect time-block grid with three rows -- RAIN, WINDS, TIDES -- where each
block is colour-coded by impact level (green = minor ... red / purple = severe).  Data driven, renders every cycle.
Levels: rain = total inches in the block; winds = peak gust; tides = highest tide in the block vs NWS flood stages."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import extras_data as X
from .theme import C, Canvas
from .timelines import _blocks, _rows

NONE_COL = (255, 255, 255, 14)
GREEN, YELLOW, ORANGE, RED, PURPLE = (46, 190, 90), (255, 214, 0), (255, 140, 0), (235, 52, 52), (170, 70, 230)
# one colour scale for all three rows: green = low, yellow = minor, orange = moderate, red = high, purple = severe
RAIN_L = [(1.0, "VERY HEAVY", PURPLE), (0.5, "HEAVY", RED), (0.25, "MODERATE", ORANGE), (0.1, "LIGHT", YELLOW), (0.02, "SPRINKLES", GREEN)]
WIND_L = [(70, "DESTRUCTIVE", PURPLE), (58, "DAMAGING", RED), (46, "STRONG", ORANGE), (35, "WINDY", YELLOW), (25, "BREEZY", GREEN)]
TIDE_L = {"major": ("MAJOR", RED), "moderate": ("MODERATE", ORANGE), "minor": ("MINOR", YELLOW), "action": ("NEAR FLOOD", GREEN)}
LEGEND = [("LOW", GREEN), ("MINOR", YELLOW), ("MODERATE", ORANGE), ("HIGH", RED), ("SEVERE", PURPLE)]


def _pick(v, table):
    for lo, lab, col in table:
        if v >= lo:
            return lab, col
    return None


def _hm(t):
    return t.strftime("%I%p").lstrip("0").lower()


def _block_cells(pkg, cfg, tz, blocks):
    gust = {}
    for h in pkg.get("hourly_ext") or []:
        gust[datetime.fromisoformat(h["time"]).astimezone(tz)] = max(h.get("gust") or 0, h.get("wind") or 0)
    td = (pkg.get("_extras") or {}).get("tides") or {}
    tides = [t for t in td.get("tides", []) if t["type"] == "H"]
    out = []
    for b in blocks:
        ts = [r["t"] for r in b["rows"]]
        t0, t1 = min(ts), max(ts) + timedelta(hours=1)
        rain = sum(r["q"] for r in b["rows"])
        g = max((gust.get(t, 0) for t in ts), default=0)
        rc = _pick(rain, RAIN_L)
        gc = _pick(g, WIND_L)
        tc = None
        for t in tides:
            tt = t["time"].astimezone(tz)
            if t0 <= tt < t1:
                cat = X.flood_category(t["ft"], td.get("stages") or {})
                if cat in TIDE_L and (tc is None or list(TIDE_L).index(cat) < list(TIDE_L).index(tc[0])):
                    tc = (cat, tt)
        out.append({
            "rain": None if not rc else (rc[0], rc[1], f"{rain:.2f}\"" if rain < 1 else f"{rain:.1f}\""),
            "wind": None if not gc else (gc[0], gc[1], f"GUSTS {int(5 * round(g / 5))} MPH"),
            "tide": None if not tc else (TIDE_L[tc[0]][0], TIDE_L[tc[0]][1], f"HIGH {_hm(tc[1])}"),
        })
    return out


def what_to_expect_impacts(pkg, cfg):
    rows, tz = _rows(pkg, cfg)
    blocks = _blocks(rows[:72])
    if len(blocks) < 3:
        return None
    cells = _block_cells(pkg, cfg, tz, blocks)
    lines = [("rain", "RAIN", (60, 165, 255)), ("wind", "WINDS", (240, 200, 70)), ("tide", "TIDES", (88, 200, 255))]
    cv = Canvas(cfg)
    cv.header("WHAT TO EXPECT", f"RAIN  ·  WINDS  ·  TIDES  ·  {pkg['location']['area'].upper()}")
    M = cv.M
    tx, ty, tw = M, cv.top, cv.W - 2 * M
    leg_h = 70
    th = cv.bottom - cv.top - leg_h - 14
    labw = 250 if not cv.tall else 190
    hh = 120 if not cv.tall else 104
    cw = (tw - labw) / len(blocks)
    rh = (th - hh) / len(lines)
    cv.rect(tx, ty, tw, th, C["panel"], r=14)
    cv.rect(tx, ty, tw, hh, (255, 255, 255, 30), r=14)
    for i, b in enumerate(blocks):
        cx = tx + labw + i * cw + cw / 2
        s = 40 if not cv.tall else 30
        cv.text(cx, ty + hh * 0.34, b["dow"], s, "bold", anchor="mm", maxw=cw - 14)
        cv.text(cx, ty + hh * 0.72, b["part"], s, "bold", C["muted"] if b["part"] != "NIGHT" else (150, 175, 255), anchor="mm", maxw=cw - 14)
        if i:
            cv.line([(tx + labw + i * cw, ty + 10), (tx + labw + i * cw, ty + th - 10)], (255, 255, 255, 60), 1.6)
    for j, (key, lab, col) in enumerate(lines):
        ry = ty + hh + j * rh
        cv.line([(tx + 14, ry), (tx + tw - 14, ry)], (255, 255, 255, 120), 2)
        cv.rect(tx, ry + 14, 8, rh - 28, (*col, 255), r=3)
        cv.text(tx + 34, ry + rh / 2, lab, 44 if not cv.tall else 32, "bold", anchor="lm", maxw=labw - 44)
        for i, c in enumerate(cells):
            v = c[key]
            bx, bw = tx + labw + i * cw + 8, cw - 16
            if not v:
                cv.rect(bx, ry + 16, bw, rh - 32, NONE_COL, r=14)
                cv.text(bx + bw / 2, ry + rh / 2, "—", 40, "bold", (255, 255, 255, 70), anchor="mm")
                continue
            name, fill, sub = v
            cv.rect(bx, ry + 16, bw, rh - 32, (*fill, 255), r=14)
            tc = (10, 16, 30) if 0.299 * fill[0] + 0.587 * fill[1] + 0.114 * fill[2] > 110 else (255, 255, 255)
            big = min(34 if not cv.tall else 26, (bw - 14) / max(4.5, len(name) * 0.66))
            cv.text(bx + bw / 2, ry + rh / 2 - big * 0.55, name, big, "bold", tc, anchor="mm", maxw=bw - 12)
            cv.text(bx + bw / 2, ry + rh / 2 + big * 0.75, sub, big * (0.62 if not cv.tall else 0.82), "medium", tc, anchor="mm", maxw=bw - 12)
    # legend
    ly = ty + th + 14
    cv.rect(tx, ly, tw, leg_h, C["panel"], r=12)
    cv.text(tx + 24, ly + leg_h / 2, "IMPACT LEVEL" if not cv.tall else "LEVEL", 24 if not cv.tall else 20, "bold", C["muted"], anchor="lm")
    x = tx + (250 if not cv.tall else 150)
    step = (tw - (x - tx) - 10) / len(LEGEND)
    for nm, col in LEGEND:
        cv.rect(x, ly + leg_h / 2 - 13, 26, 26, (*(col or (255, 255, 255)), 255 if col else 40), r=6)
        cv.text(x + 36, ly + leg_h / 2, nm, 24 if not cv.tall else 18, "bold", anchor="lm", maxw=step - 46)
        x += step
    cv.footer(pkg)
    return cv
