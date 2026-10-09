#!/usr/bin/env python3
"""KORF weather graphics: NDFD -> forecast package -> themed 1920x1080 PNGs.

  python run.py                    live NDFD for KORF (+ overrides.json if enabled)
  python run.py --edit             build, open forecast.json in your editor, render when you close it
  python run.py --from FILE.json   fully manual: render from a forecast file, no NDFD fetch
  python run.py --template         write manual_forecast.json to fill in by hand
  python run.py --sample           offline test with synthetic NDFD data
  python run.py --only 7day,daily  render a subset
"""
import argparse
import json
import os
import re
import time
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from wxgfx import extended, folders, graphics, outlookmap, outlooks, overrides, sample, spchazards, summarize, theme  # noqa: E402
from wxgfx.ndfd import Grid  # noqa: E402
from wxgfx.nws import NWSClient  # noqa: E402


def load_cfg(path):
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    if cfg.get("logo_path") and not Path(cfg["logo_path"]).is_absolute():
        cfg["logo_path"] = str(ROOT / cfg["logo_path"])
    return cfg


def build(cfg, now, use_sample):
    tz = ZoneInfo(cfg["timezone"])
    loc = cfg["location"]
    if use_sample:
        gp, al, obs = sample.build(now, tz)
    else:
        nws = NWSClient(cfg["user_agent"], ROOT / "cache")
        print(f"Fetching NDFD gridpoint for {loc['station']} ({loc['lat']}, {loc['lon']})...")
        gp = nws.gridpoint(loc["lat"], loc["lon"])
        al = nws.alerts_area(cfg.get("alert_states", ["VA", "NC", "MD"]))
        obs = nws.latest_obs(loc["station"])
    grid = Grid(gp, tz)
    if cfg.get("extended_rainfall", True):
        if use_sample:
            hourly, model = sample.extended_qpf(grid), "sample"
        else:
            print("Fetching NBM rainfall guidance for days beyond the NDFD rainfall forecast...")
            hourly, model = extended.fetch_hourly_precip(loc["lat"], loc["lon"], cfg["user_agent"])
        grid.add_extended_qpf(hourly, model)
    pkg = summarize.build_package(grid, now, cfg, al, obs)
    if use_sample:
        pkg["source"] = "SAMPLE DATA"
    return pkg


def open_editor(path):
    editor = os.environ.get("EDITOR") or ("notepad" if os.name == "nt" else "nano")
    print(f"Opening {path.name} in {editor} — save and close it to render.")
    subprocess.run([editor, str(path)])


def render(pkg, cfg, out_dir, only=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    enabled = cfg.get("graphics") or list(graphics.GRAPHICS)
    made = []
    formats = [f for f in (cfg.get("formats") or ["wide", "vertical", "post"]) if f in theme.FORMATS]
    for fmt in formats:
        theme.set_format(fmt)
        if len(formats) > 1:
            print(f" [{fmt} {theme.FORMATS[fmt][0]}x{theme.FORMATS[fmt][1]}]")
        for name in enabled:
            if only and name not in only:
                continue
            fn = graphics.GRAPHICS.get(name)
            if not fn:
                continue
            try:
                cv = fn(pkg, cfg)
            except Exception as e:  # one bad graphic shouldn't kill the run
                print(f"  ! {name} ({fmt}) failed: {e!r}")
                if os.environ.get("WX_TRACE"):  # set WX_TRACE=1 to see the full traceback
                    import traceback
                    traceback.print_exc()
                continue
            if cv is None:
                if fmt == formats[0]:
                    print(f"  - {name}: not relevant today, skipped")
                continue
            for fname, c in (cv if isinstance(cv, list) else [(name, cv)]):
                path = folders.path_for(out_dir, fname, fmt, cfg)  # "<NN Category>/<Size>/<name>.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                c.save(path)
                made.append(path)
                print(f"  + {path.relative_to(out_dir)}")
                spec = getattr(c, "full_spec", None)
                if spec and cfg.get("fullscreen_maps", True):  # full-screen twin: map fills the image
                    try:
                        from wxgfx import fullscreen
                        fpath = path.with_name(f"{path.stem}_full.png")
                        fullscreen.render(pkg, cfg, **spec).save(fpath)
                        made.append(fpath)
                        print(f"  + {fpath.relative_to(out_dir)}")
                    except Exception as e:
                        print(f"  ! {fname}_full ({fmt}) failed: {e!r}")
                if spec and cfg.get("bigtext_maps", True) and fmt in (cfg.get("bigtext_formats") or ["square"]):
                    try:  # "big text" social twin: giant headline, callouts on the map, tagline banner, logo
                        from wxgfx import bigtext
                        bpath = path.with_name(f"{path.stem}_big.png")
                        bigtext.render(pkg, cfg, fname, **spec).save(bpath)
                        made.append(bpath)
                        print(f"  + {bpath.relative_to(out_dir)}")
                    except Exception as e:
                        print(f"  ! {fname}_big ({fmt}) failed: {e!r}")
    theme.set_format("wide")
    saved = {k: v for k, v in pkg.items() if not k.startswith("_")}
    prev = latest_dir(cfg) / "forecast.json"
    if prev.exists():  # partial runs (--only) keep the editor's SPC / Be Weather Aware reference values
        try:
            old = json.loads(prev.read_text(encoding="utf-8"))
            for k in ("spc_outlook", "weather_aware"):
                if k not in saved and k in old:
                    saved[k] = old[k]
        except (OSError, json.JSONDecodeError):
            pass
    (out_dir / "forecast.json").write_text(json.dumps(saved, indent=2, default=str), encoding="utf-8")
    (out_dir / "caption.txt").write_text(summarize.caption(pkg), encoding="utf-8")
    return made


def _swap_in(src, dst):
    """Copy then atomically replace, so OBS never reads a half-written file."""
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copyfile(src, tmp)
    for _ in range(5):
        try:
            os.replace(tmp, dst)
            return True
        except PermissionError:  # Windows: file briefly locked by OBS/Explorer
            time.sleep(0.4)
    tmp.unlink(missing_ok=True)
    print(f"  ! couldn't update {dst.name} (file in use)")
    return False


def latest_dir(cfg):
    """The always-current folder (config "latest_folder", default "latest_rickywx").
    An old output/latest from before the rename is moved over once, so nothing is lost."""
    new = ROOT / "output" / (cfg.get("latest_folder") or "latest_rickywx")
    old = ROOT / "output" / "latest"
    if not new.exists() and old.is_dir() and old != new:
        try:
            old.rename(new)
        except OSError:
            pass
    return new


def update_latest(out, latest, prune=True):
    """Mirror out/ (and every subfolder: "04 Rain & Flooding/Square/"...) into latest/.
    prune=False (partial --only runs): keep the graphics that weren't remade this time."""
    _update_dir(out, latest, prune)
    for sub in out.iterdir():
        if sub.is_dir():
            update_latest(sub, latest / sub.name, prune)
    if prune and latest.exists():  # e.g. Tropical/ once the storm is gone: empty it, keep the folder for OBS
        for sub in latest.iterdir():
            if sub.is_dir() and not (out / sub.name).exists():
                for f in sub.rglob("*.png"):
                    try:
                        f.unlink()
                    except OSError:
                        pass
                if sub.name in ("vertical", "post", "square", "Tropical"):  # old flat layout: tidy away
                    for d in sorted(sub.rglob("*"), key=lambda p: -len(p.parts)) + [sub]:
                        try:
                            d.rmdir() if d.is_dir() else None
                        except OSError:
                            pass


def _update_dir(out, latest, prune=True):
    """Refresh output/latest_rickywx IN PLACE (never delete the folder OBS is watching).
    Alert graphics get fixed names alert_1.png ... alert_N.png so OBS sources don't need re-pointing,
    and removes graphics that weren't made this run (e.g. an expired alert)."""
    latest.mkdir(parents=True, exist_ok=True)
    keep = set()
    for f in sorted(out.iterdir()):
        if f.is_file():
            m = re.match(r"((?:alert|river)_\d+)_.+\.png$", f.name)
            name = f"{m.group(1)}.png" if m else f.name  # fixed alert names; full names stay in the dated folder
            _swap_in(f, latest / name)
            keep.add(name)
    for f in latest.iterdir():
        if prune and f.is_file() and f.name not in keep:
            try:
                f.unlink()
            except OSError:
                pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--sample", action="store_true", help="use synthetic data (no network)")
    ap.add_argument("--from", dest="from_file", help="render from a forecast JSON (manual mode)")
    ap.add_argument("--edit", action="store_true", help="edit the forecast before rendering")
    ap.add_argument("--overrides", default=str(ROOT / "overrides.json"))
    ap.add_argument("--no-overrides", action="store_true")
    ap.add_argument("--template", action="store_true", help="write manual_forecast.json and exit")
    ap.add_argument("--only", help="comma list of graphics")
    ap.add_argument("--outlook-debug", action="store_true",
                    help="print the SPC/WPC layers and attributes found (use if an outlook graphic is missing)")
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    theme.configure(cfg)
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.now(tz)

    if args.from_file:
        pkg = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        pkg.setdefault("source", "MANUAL")
        pkg.setdefault("location", {}).setdefault("area", cfg["location"].get("area", "Hampton Roads Area"))
        pkg["issued"] = now.isoformat()
        pkg["issued_label"] = now.strftime("%I:%M %p %a %b ").lstrip("0") + str(now.day)
    else:
        pkg = build(cfg, now, args.sample)
        if args.template:
            p = ROOT / "manual_forecast.json"
            pkg["source"] = "MANUAL"
            p.write_text(json.dumps(pkg, indent=2), encoding="utf-8")
            print(f"Wrote {p} — edit the values, then: python run.py --from manual_forecast.json")
            return
        if not args.no_overrides:
            pkg = overrides.apply(pkg, overrides.load(args.overrides))

    only_set = set(args.only.split(",")) if args.only else None
    if not args.no_overrides:  # big-text wording for the square social maps
        pkg["bigtext"] = (overrides.load(args.overrides) or {}).get("bigtext") or pkg.get("bigtext")
    if "outlooks" in (cfg.get("graphics") or []) and (only_set is None or "outlooks" in only_set):
        if args.sample:
            pkg["_outlooks"] = sample.sample_outlooks()
        else:
            print("Fetching SPC outlooks, WPC excessive rainfall outlooks and WPC QPF...")
            pkg["_outlooks"] = outlooks.fetch_all(cfg, debug=args.outlook_debug)
        auto = outlookmap.spc_info(pkg["_outlooks"], cfg)
        auto.update(pkg.get("spc_outlook") or {})  # a --from file's own SPC text wins
        pkg["spc_outlook"] = auto
    if "tropical_pack" in (cfg.get("graphics") or []) and (only_set is None or "tropical_pack" in only_set):
        from wxgfx import tropical
        if args.sample:
            pkg["_tropical"] = tropical.sample(now, cfg)
        else:
            print("Checking the tropics (NHC + NWS hurricane products)...")
            pkg["_tropical"] = tropical.fetch(cfg, now, debug=args.outlook_debug)
        pkg["tropical_manual"] = (overrides.load(args.overrides) or {}).get("tropical") if not args.no_overrides else None
    if "reports" in (cfg.get("graphics") or []) and (only_set is None or "reports" in only_set):
        from wxgfx import reports
        if args.sample:
            pkg["_reports"] = reports.sample(now)
        else:
            print("Fetching CoCoRaHS rain reports and NWS storm reports...")
            pkg["_reports"] = reports.fetch(cfg, now, {"rain_reports", "storm_reports"})
    if "ffg" in (cfg.get("graphics") or []) and (only_set is None or "ffg" in only_set):
        from wxgfx import ffg
        if args.sample:
            pkg["_ffg"] = ffg.sample()
        else:
            print("Fetching flash flood guidance...")
            pkg["_ffg"] = ffg.fetch(cfg, debug=args.outlook_debug)
    if "drought" in (cfg.get("graphics") or []) and (only_set is None or "drought" in only_set):
        from wxgfx import drought
        if args.sample:
            pkg["_drought"] = drought.sample(now)
        else:
            print("Fetching the U.S. Drought Monitor and Norfolk rainfall totals...")
            pkg["_drought"] = drought.fetch(cfg, now, debug=args.outlook_debug)
    if "river_flooding" in (cfg.get("graphics") or []) and (only_set is None or "river_flooding" in only_set):
        from wxgfx import rivers
        if args.sample:
            pkg["_rivers"] = rivers.sample(now, tz)
        else:
            print("Fetching NWS river forecasts...")
            pkg["_rivers"] = rivers.fetch(cfg, now, tz, debug=args.outlook_debug)
    if "cpc_hazards" in (cfg.get("graphics") or []) and (only_set is None or "cpc_hazards" in only_set):
        from wxgfx import cpcmap
        if args.sample:
            pkg["_cpc"] = cpcmap.sample(now)
        else:
            print("Fetching CPC hazards outlook...")
            pkg["_cpc"] = cpcmap.fetch_all(cfg, debug=args.outlook_debug)
    if "winter_maps" in (cfg.get("graphics") or []) and (only_set is None or "winter_maps" in only_set):
        from wxgfx import wintermap
        if args.sample:
            pkg["_winter"] = wintermap.sample()
        else:
            print("Fetching WPC snow/ice probabilities and the Winter Storm Severity Index...")
            pkg["_winter"] = wintermap.fetch_all(cfg, debug=args.outlook_debug)
    if "frost_risk" in (cfg.get("graphics") or []) and (only_set is None or "frost_risk" in only_set):
        from wxgfx import frost
        utc_now = now.astimezone(timezone.utc)
        if args.sample:
            pkg["_frost"] = frost.sample(utc_now, tz)
        else:
            print("Fetching NDFD lows, wind and sky cover for frost risk...")
            pkg["_frost"] = frost.fetch(cfg, ROOT / "cache", utc_now, debug=args.outlook_debug)
    if "ndfd_maps" in (cfg.get("graphics") or []) and (only_set is None or "ndfd_maps" in only_set):
        from wxgfx import ndfdmap
        utc_now = now.astimezone(timezone.utc)
        if args.sample:
            pkg["_ndfdmaps"] = ndfdmap.sample(utc_now)
        else:
            print("Fetching NDFD snowfall and wind grids...")
            pkg["_ndfdmaps"] = ndfdmap.fetch(cfg, ROOT / "cache", utc_now, debug=args.outlook_debug)
    from wxgfx import extras, extras_data, extras_sample
    enabled = set(cfg.get("graphics") or [])
    want = set()
    for g, needs in extras_data.NEEDS.items():
        if g in enabled and (only_set is None or g in only_set or "weather_aware" in (only_set or ())):
            want |= needs
    if "weather_aware" in enabled and (only_set is None or "weather_aware" in only_set):
        want |= {"tides", "beach"}  # coastal flooding + rip currents feed the day's main concern
    if want or "weather_aware" in enabled:
        tz_ = ZoneInfo(cfg["timezone"])
        if args.sample:
            pkg["_extras"] = extras_sample.build(cfg, now, tz_)
        elif want:
            print("Fetching tides, beach, climate, UV, aviation and tropical data...")
            pkg["_extras"] = extras_data.fetch_all(cfg, ROOT / "cache", now, tz_, want, debug=args.outlook_debug)
    if "weather_aware" in enabled:
        pkg["weather_aware"] = pkg.get("weather_aware") or extras.aware_info(pkg, cfg)
    if not args.no_overrides:
        wa = (overrides.load(args.overrides) or {}).get("weather_aware")
        if wa:
            if wa.get("hide"):
                pkg["weather_aware"] = None
            else:
                pkg["weather_aware"] = {**(pkg.get("weather_aware") or {"title": "", "details": []}),
                                        **{k: v for k, v in wa.items() if not k.startswith("_")}}
                print("  Be Weather Aware: your edits applied")
        spc_edits = (overrides.load(args.overrides) or {}).get("spc") or {}
        for day, edit in spc_edits.items():
            if not day.startswith("_") and day in (pkg.get("spc_outlook") or {}):
                spchazards.apply_edits(pkg["spc_outlook"][day], edit)
                print(f"  SPC day {day}: your hazard edits applied")

    if args.edit:
        tmp = ROOT / "output" / "_edit_forecast.json"
        tmp.parent.mkdir(exist_ok=True)
        hidden = {k: v for k, v in pkg.items() if k.startswith("_")}  # map polygons: not for hand-editing
        tmp.write_text(json.dumps({k: v for k, v in pkg.items() if k not in hidden}, indent=2), encoding="utf-8")
        open_editor(tmp)
        pkg = {**json.loads(tmp.read_text(encoding="utf-8")), **hidden}
        if "MANUAL" not in pkg.get("source", ""):
            pkg["source"] = pkg.get("source", "NWS NDFD") + " + MANUAL EDITS"

    summarize.round_pops(pkg)  # rain chances always to the nearest 10%, even hand-entered ones
    stamp = now.strftime("%Y-%m-%d_%H%M")
    out = ROOT / "output" / stamp
    only = set(args.only.split(",")) if args.only else None
    print(f"Rendering to {out}")
    made = render(pkg, cfg, out, only)
    update_latest(out, latest_dir(cfg), prune=only is None)
    print(f"Done: {len(made)} graphics  (also copied to output/{latest_dir(cfg).name})")
    clean_old_runs(cfg, now)


def clean_old_runs(cfg, now):
    """Delete dated run folders (output/YYYY-MM-DD_HHMM) older than config "keep_days" (default 14; 0 = keep all).
    Only folders named like a run are touched - never latest_rickywx, cache, or anything you made yourself."""
    days = cfg.get("keep_days", 14)
    if not days or days <= 0:
        return
    cutoff = now.replace(tzinfo=None) - timedelta(days=days)
    gone = 0
    for d in (ROOT / "output").iterdir():
        if not d.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{4}", d.name):
            continue
        try:
            made = datetime.strptime(d.name, "%Y-%m-%d_%H%M")
        except ValueError:
            continue
        if made < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            gone += not d.exists()
    if gone:
        print(f"Cleaned up {gone} run folder{'s' if gone != 1 else ''} older than {days} days")


if __name__ == "__main__":
    main()
