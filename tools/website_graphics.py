"""Build the website graphics bundle from the graphics script's output.

Reads website_graphics.json (the graphics YOU picked), finds each one in
output/latest_rickywx, and writes a ready-to-upload folder (default: _web) with
the PNGs, small thumbnails, a manifest.json and CORS headers. The GitHub
workflow then publishes that folder to Cloudflare Pages (graphics.rickymatthewswx.com).

Usage:  python tools/website_graphics.py [--src output/latest_rickywx] [--out _web]
"""
import argparse, datetime, json, os, re, shutil, sys

try:
    from PIL import Image
except ImportError:
    Image = None

ACRONYMS = {"spc": "SPC", "ero": "ERO", "ffg": "FFG", "wpc": "WPC", "qpf": "QPF", "cpc": "CPC", "uv": "UV", "nhc": "NHC", "nws": "NWS"}


def pretty_title(stem):
    s = re.sub(r"^\d+_", "", stem)
    parts = []
    for w in s.split("_"):
        lw = w.lower()
        m = re.fullmatch(r"d(\d+)", lw)
        if lw in ACRONYMS: parts.append(ACRONYMS[lw])
        elif re.fullmatch(r"day\d", lw): parts.append("Day " + lw[3:])
        elif m: parts.append("Day " + m.group(1))
        elif re.fullmatch(r"\d+", lw): parts.append(lw)
        elif re.fullmatch(r"(\d+)(hr|day)", lw):
            n, u = re.fullmatch(r"(\d+)(hr|day)", lw).groups(); parts.append(n + ("-Hr" if u == "hr" else "-Day"))
        elif lw == "7day": parts.append("7-Day")
        else: parts.append(w.capitalize())
    t = " ".join(parts)
    t = re.sub(r"Day (\d+) (\d+)\b", r"Day \1-\2", t)
    return t.replace("Day 3 7", "Day 3-7")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "item"


def natkey(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def find_graphic(src, name, fmt):
    """Return (category folder name, file path) for a graphic name like 'spc_day1'
    or '02 Severe & Alerts/spc_day1'. Prefers the wide version."""
    want_cat = None
    if "/" in name:
        want_cat, name = name.rsplit("/", 1)
    name = re.sub(r"\.png$", "", name, flags=re.I).lower()
    for d in sorted(os.listdir(src), key=natkey):
        if d.startswith(".") or not os.path.isdir(os.path.join(src, d)):
            continue
        if want_cat and want_cat.lower() not in (d.lower(), re.sub(r"^\d+\s*", "", d).lower()):
            continue
        for folder in (os.path.join(src, d, fmt), os.path.join(src, d)):
            if not os.path.isdir(folder):
                continue
            for fn in os.listdir(folder):
                if fn.lower() == name + ".png":
                    return d, os.path.join(folder, fn)
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join("output", "latest_rickywx"))
    ap.add_argument("--list", default="website_graphics.json")
    ap.add_argument("--out", default="_web")
    a = ap.parse_args()

    cfg = json.load(open(a.list, encoding="utf-8"))
    fmt = cfg.get("format", "Wide")
    entries = cfg.get("graphics", [])
    if not os.path.isdir(a.src):
        sys.exit(f"Graphics folder not found: {a.src}")

    if os.path.isdir(a.out):
        shutil.rmtree(a.out)
    gdir = os.path.join(a.out, "g")
    os.makedirs(gdir)

    cats, order, found, missing = {}, [], 0, []
    for e in entries:
        if isinstance(e, str):
            e = {"name": e}
        name = e["name"]
        folder, path = find_graphic(a.src, name, fmt)
        if not path:
            missing.append(name)
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        cat_name = e.get("category") or re.sub(r"^\d+\s*", "", folder).strip() or folder
        cid = slug(cat_name)
        fname = slug(stem) + ".png"
        shutil.copy2(path, os.path.join(gdir, fname))
        thumb = fname
        if Image:
            thumb = fname[:-4] + ".thumb.webp"
            with Image.open(path) as im:
                im = im.convert("RGB"); im.thumbnail((720, 405)); im.save(os.path.join(gdir, thumb), "WEBP", quality=80)
        if cid not in cats:
            cats[cid] = {"id": cid, "name": cat_name, "items": []}; order.append(cid)
        cats[cid]["items"].append({
            "title": e.get("title") or pretty_title(stem),
            "file": f"g/{fname}", "thumb": f"g/{thumb}",
            "mtime": datetime.datetime.fromtimestamp(os.path.getmtime(path), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "featured": bool(e.get("featured")),
        })
        found += 1

    manifest = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "categories": [cats[c] for c in order]}
    json.dump(manifest, open(os.path.join(a.out, "manifest.json"), "w", encoding="utf-8"), indent=1)
    open(os.path.join(a.out, "_headers"), "w").write(
        "/*\n  Access-Control-Allow-Origin: *\n  Cache-Control: public, max-age=120\n")
    open(os.path.join(a.out, "index.html"), "w").write(
        "<!doctype html><title>RickyMatthewsWX graphics</title><p>Graphics feed for rickymatthewswx.com</p>")

    print(f"Website graphics: {found} included, {len(missing)} not available right now.")
    for m in missing:
        print(f"  - not found (skipped, maybe not issued today): {m}")
    if found == 0:
        sys.exit("No graphics were found - not publishing an empty set.")


if __name__ == "__main__":
    main()
