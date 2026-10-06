"""Build the phone-friendly gallery page from output/latest.

    python tools/build_site.py output/latest _site

Makes _site/index.html (tabs for Wide / Vertical / Post / Square, grouped sections, light JPG thumbnails,
tap to view full size with Download + Share buttons) and copies the full-size PNGs next to it.
Used by the GitHub workflow; also works locally (open _site/index.html).
"""
import html
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

FORMATS = [("wide", "Wide", "16:9 · TV / YouTube", ""), ("vertical", "Vertical", "9:16 · Stories / Reels", "vertical"),
           ("post", "Post", "4:5 · FB / IG feed", "post"), ("square", "Square", "1:1 · FB / IG", "square")]
SECTIONS = [  # (title, test on file stem) - first match wins
    ("Hurricane Threat", lambda n: n.startswith("T_")),
    ("Alerts & Be Weather Aware", lambda n: n.startswith(("alert", "weather_aware", "warning_count"))),
    ("Forecast", lambda n: n in ("daily", "what_to_know", "7day", "hourly", "current", "commute", "weekend",
                                 "above_average", "holiday_countdown")),
    ("Charts", lambda n: n in ("feels_like", "wind_chill", "dewpoints", "rain_totals", "wind", "sun_uv",
                               "air_quality")),
    ("Big Text Maps", lambda n: n.endswith("_big")),
    ("Full-Screen Maps", lambda n: n.endswith("_full") or n == "drought"),
    ("Severe & Rain Outlooks", lambda n: n.startswith(("spc_", "ero_", "wpc_qpf", "cpc_"))),
    ("Winter", lambda n: n.startswith(("snow", "ice_prob", "wssi"))),
    ("Wind Maps", lambda n: n in ("wind_map", "gust_map")),
    ("Tides & Flooding", lambda n: n.startswith(("tides", "high_tides", "tidal_flood", "river", "beach"))),
    ("Climate", lambda n: n in ("yesterday", "month_rain", "record_watch", "first_freeze")),
    ("Frost & Freeze", lambda n: n.startswith("frost_")),
    ("More", lambda n: True),
]
NICE = {"7day": "7-Day Forecast", "what_to_know": "What To Know", "weather_aware": "Be Weather Aware",
        "spc_day1": "SPC Day 1", "spc_day2": "SPC Day 2", "spc_day3": "SPC Day 3", "ero_day1": "Excessive Rain Day 1",
        "ero_day2": "Excessive Rain Day 2", "ero_day3": "Excessive Rain Day 3", "sun_uv": "Sun & UV",
        "yesterday": "Climate Report", "month_rain": "Rainfall So Far", "feels_like": "Heat Index"}


def nice(stem):
    if stem.startswith("T_"):  # Tropical folder: "T_05_wind_chances" -> "Wind Chances"
        import re as _re
        return _re.sub(r"^T_\d+_", "", stem).replace("_", " ").title().replace("Nhc", "NHC")
    if stem in NICE:
        return NICE[stem]
    full = stem.endswith("_full")
    s = stem[:-5] if full else stem
    s = NICE.get(s, s.replace("wpc_qpf_", "Rain ").replace("_state", " (VA/NC)").replace("_", " ").title()
                 .replace("Day1", "Day 1").replace("Day2", "Day 2").replace("Day3", "Day 3").replace("Days1-3", "Days 1-3")
                 .replace("In ", '" ').replace("Cpc", "CPC").replace("Wssi", "WSSI").replace("Spc", "SPC")
                 .replace("Ero", "Excessive Rain").replace("D8 14", "Days 8-14").replace("D3 7", "Days 3-7"))
    return s + (" · Full Screen" if full else "")


def build(src, dst, repo=None):
    src, dst = Path(src), Path(dst)
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    issued, caption = None, ""
    fj = src / "forecast.json"
    if fj.exists():
        try:
            issued = json.loads(fj.read_text(encoding="utf-8")).get("issued_label")
        except (OSError, ValueError):
            pass
    if (src / "caption.txt").exists():
        caption = (src / "caption.txt").read_text(encoding="utf-8").strip()
    tabs = []
    for key, label, hint, sub in FORMATS:
        folder = src / sub if sub else src
        pngs = sorted(folder.glob("*.png")) if folder.exists() else []
        tfolder = src / "Tropical" / sub if sub else src / "Tropical"
        tpngs = sorted(tfolder.glob("*.png")) if tfolder.exists() else []
        if not pngs and not tpngs:
            continue
        (dst / "img" / key).mkdir(parents=True)
        (dst / "thumb" / key).mkdir(parents=True)
        groups = {t: [] for t, _ in SECTIONS}
        for p in tpngs + pngs:
            tgt = dst / "img" / key / (("T_" if p in tpngs else "") + p.name)
            shutil.copy2(p, tgt)
            p = tgt
            im = Image.open(p).convert("RGB")
            im.thumbnail((480, 480), Image.LANCZOS)
            im.save(dst / "thumb" / key / (p.stem + ".jpg"), quality=78, optimize=True)
            sect = next(t for t, test in SECTIONS if test(p.stem))
            groups[sect].append(p)
        tabs.append((key, label, hint, groups))
    stamp = issued or datetime.now().strftime("%-I:%M %p %a %b %-d")
    run_url = f"https://github.com/{repo}/actions/workflows/weather-graphics.yml" if repo else None
    parts = []
    for i, (key, label, hint, groups) in enumerate(tabs):
        body = []
        for title, items in groups.items():
            if not items:
                continue
            cards = "".join(
                f'<button class="card" data-full="img/{key}/{html.escape(p.name)}" data-name="{html.escape(p.name)}">'
                f'<img loading="lazy" src="thumb/{key}/{html.escape(p.stem)}.jpg" alt="{html.escape(nice(p.stem))}">'
                f'<span>{html.escape(nice(p.stem))}</span></button>' for p in items)
            body.append(f'<h2>{html.escape(title)} <small>{len(items)}</small></h2><div class="grid g-{key}">{cards}</div>')
        parts.append(f'<section id="t-{key}" class="tab{" on" if i == 0 else ""}"><p class="hint">{html.escape(hint)}</p>'
                     + "".join(body) + "</section>")
    tabbar = "".join(f'<button class="tb{" on" if i == 0 else ""}" data-t="{k}">{html.escape(l)}</button>'
                     for i, (k, l, _, _) in enumerate(tabs))
    page = TEMPLATE.replace("{{STAMP}}", html.escape(stamp)).replace("{{TABS}}", tabbar).replace("{{BODY}}", "".join(parts)) \
        .replace("{{CAPTION}}", html.escape(caption)).replace("{{RUN}}", (
            f'<a class="run" href="{run_url}">Run now ↗</a>' if run_url else ""))
    (dst / "index.html").write_text(page, encoding="utf-8")
    (dst / ".nojekyll").write_text("")
    print(f"Built {dst / 'index.html'}: {sum(len(v) for t in tabs for v in t[3].values())} images")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0d1526"><meta name="apple-mobile-web-app-capable" content="yes">
<title>Weather Graphics</title>
<style>
:root{--bg:#0d1526;--panel:#1b2a45;--panel2:#22345a;--text:#f3f6fb;--muted:#9fb0cc;--accent:#58c8ff}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:5;background:linear-gradient(#1b2b46,#0d1526);padding:14px 16px 10px;
border-bottom:1px solid #2a3c60}
h1{margin:0;font-size:20px;letter-spacing:.3px}.sub{color:var(--muted);font-size:13px;margin-top:2px;
display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.run{color:var(--accent);text-decoration:none;font-weight:600}
.tabs{display:flex;gap:6px;margin-top:10px;overflow-x:auto}
.tb{flex:0 0 auto;border:0;border-radius:999px;padding:8px 14px;background:var(--panel);color:var(--muted);
font-weight:600;font-size:14px}.tb.on{background:var(--accent);color:#08213a}
main{padding:6px 16px 40px;max-width:1200px;margin:0 auto}
.tab{display:none}.tab.on{display:block}.hint{color:var(--muted);font-size:12px;margin:10px 0 0}
h2{font-size:15px;margin:22px 0 10px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px}
h2 small{font-weight:400;opacity:.7}
.grid{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(160px,1fr))}
.g-wide{grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}
.card{border:0;padding:0;background:var(--panel);border-radius:12px;overflow:hidden;text-align:left;color:var(--text);
cursor:pointer}.card img{width:100%;display:block;background:#0a1120}
.card span{display:block;padding:7px 9px 9px;font-size:13px;font-weight:600}
.cap{background:var(--panel);border-radius:12px;padding:12px;margin-top:22px;white-space:pre-wrap;font-size:14px}
.btn{border:0;border-radius:10px;padding:10px 14px;font-weight:700;font-size:14px;background:var(--panel2);
color:var(--text);text-decoration:none;display:inline-block}.btn.pri{background:var(--accent);color:#08213a}
#v{position:fixed;inset:0;z-index:20;background:rgba(5,9,18,.96);display:none;flex-direction:column}
#v.on{display:flex}#v .top{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;
padding-top:max(12px,env(safe-area-inset-top))}#v .nm{font-weight:700;font-size:14px;overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}#v .img{flex:1;display:flex;align-items:center;justify-content:center;
padding:8px;min-height:0}#v img{max-width:100%;max-height:100%;border-radius:8px}
#v .bar{display:flex;gap:8px;justify-content:center;padding:12px 14px;padding-bottom:max(14px,env(safe-area-inset-bottom))}
</style></head><body>
<header><h1>Weather Graphics</h1><div class="sub"><span>Updated {{STAMP}}</span>{{RUN}}</div>
<div class="tabs">{{TABS}}</div></header>
<main>{{BODY}}<h2>Caption</h2><div class="cap" id="cap">{{CAPTION}}</div>
<p><button class="btn" id="copycap">Copy caption</button></p></main>
<div id="v"><div class="top"><span class="nm" id="vn"></span><button class="btn" id="vx">Close</button></div>
<div class="img"><img id="vi" alt=""></div>
<div class="bar"><button class="btn pri" id="vs">Share</button><a class="btn" id="vd" download>Download</a>
<a class="btn" id="vo" target="_blank" rel="noopener">Open</a></div></div>
<script>
const $=s=>document.querySelector(s);
document.querySelectorAll('.tb').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.tb,.tab').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');$('#t-'+b.dataset.t).classList.add('on');
  try{localStorage.setItem('tab',b.dataset.t)}catch(e){}});
try{const t=localStorage.getItem('tab');const b=t&&document.querySelector('.tb[data-t="'+t+'"]');if(b)b.click()}catch(e){}
let cur=null;
document.querySelectorAll('.card').forEach(c=>c.onclick=()=>{
  cur=c;const u=c.dataset.full+'?v='+Date.now();$('#vi').src=u;$('#vd').href=c.dataset.full;
  $('#vd').setAttribute('download',c.dataset.name);$('#vo').href=c.dataset.full;
  $('#vn').textContent=c.querySelector('span').textContent;$('#v').classList.add('on');});
$('#vx').onclick=()=>{$('#v').classList.remove('on');$('#vi').src='';};
$('#vs').onclick=async()=>{
  if(!cur)return;
  try{const r=await fetch(cur.dataset.full,{cache:'no-store'});const b=await r.blob();
    const f=new File([b],cur.dataset.name,{type:'image/png'});
    if(navigator.canShare&&navigator.canShare({files:[f]})){await navigator.share({files:[f]});return;}
  }catch(e){if(e.name==='AbortError')return;}
  window.open(cur.dataset.full,'_blank');};
$('#copycap').onclick=async()=>{try{await navigator.clipboard.writeText($('#cap').textContent);
  $('#copycap').textContent='Copied!';setTimeout(()=>$('#copycap').textContent='Copy caption',1500)}catch(e){}};
</script></body></html>
"""

if __name__ == "__main__":
    a = sys.argv[1:]
    build(a[0] if a else "output/latest", a[1] if len(a) > 1 else "_site", os.environ.get("GITHUB_REPOSITORY"))
