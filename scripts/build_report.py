#!/usr/bin/env python3
"""Generate the public report (docs/index.html, served by GitHub Pages) from
the timing data + model/model.json. Self-contained HTML — inline SVG charts,
no external assets. Rebuild after build_model.py whenever data changes:

    python3 scripts/build_model.py && python3 scripts/build_report.py
"""
import csv, glob, json, pathlib, re, statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
model = json.load(open(ROOT / "model/model.json"))

def hms(s):
    if not s or not str(s).strip(): return None
    try: p = [int(x) for x in str(s).strip().split(":")]
    except ValueError: return None
    if len(p) == 3: return p[0]*3600 + p[1]*60 + p[2]
    if len(p) == 2: return p[0]*60 + p[1]
    return None

def pct(xs, p):
    xs = sorted(xs); return xs[min(len(xs)-1, int(len(xs)*p))]

def event_name(path):
    m = re.match(r"esa-(\w+)-(\d{4})", pathlib.Path(path).stem)
    return f"ESA {m.group(1).title()} {m.group(2)}" if m else pathlib.Path(path).stem

rows = []
for f in sorted(glob.glob(str(ROOT / "data/run-timings/*.csv"))):
    ev = event_name(f)
    for r in csv.DictReader(open(f)):
        game, cat = (r.get("GameName") or "").strip(), (r.get("CategoryName") or "").strip()
        if not game or "speech" in game.lower() or "speech" in cat.lower(): continue
        est, run = hms(r.get("Estimate")), hms(r.get("Actual Time"))
        if not est or not run or est <= 0: continue
        try: slot = int(r["EndTimestamp"]) - int(r["StartTimestamp"])
        except (KeyError, ValueError): slot = None
        if not slot or slot < run: continue
        rows.append({"ev": ev, "e": est, "s": slot, "run": run,
                     "setup": hms(r.get("Setup Time"))})
for r in csv.DictReader(open(ROOT / "data/derived/matched-vod.csv")):
    if r["event"] == "ESA Summer 2025":
        rows.append({"ev": "ESA Summer 2025", "e": int(r["est_s"]), "s": int(r["vod_s"]),
                     "run": None, "setup": None})

deltas = [(r["s"]-r["e"])/60 for r in rows]
dbins = {}
for d in deltas:
    b = max(-30, min(30, int(d//2*2))); dbins[b] = dbins.get(b, 0) + 1
setups = [r["setup"]/60 for r in rows if r["setup"]]
sbins = {}
for s in setups:
    b = min(40, int(s//2*2)); sbins[b] = sbins.get(b, 0) + 1

run_deltas = [r["run"]-r["e"] for r in rows if r["run"]]
comp = model["components"]
per_event = model["per_event"]
kpi = {
    "n": len(rows),
    "run_med": comp["run_vs_estimate_delta"]["p50"],
    "slots_over": round(100*sum(1 for d in deltas if d > 0)/len(deltas)),
    "speech_med": comp["speech"]["p50"],
    "setup_over": comp["setup"]["pct_over_600s"],
    "setup_p80": comp["setup"]["p80"],
}
data = {"scatter": [{"e": r["e"], "s": r["s"], "ev": r["ev"]} for r in rows],
        "dbins": dbins, "sbins": sbins, "model": model["slot_table"],
        "per_event": [{"ev": ev, **st} for ev, st in per_event.items()], "kpi": kpi}

def fmt_sec(sec, signed=True):
    sign = "−" if sec < 0 else ("+" if signed else "")
    sec = abs(int(sec))
    return f"{sign}{sec//60}:{sec%60:02d}"

flat = model["flat_rules"]
HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ESA Estimate Accuracy Model</title>
<style>
  :root { --surface:#fcfcfb; --card:#fff; --ink:#0b0b0b; --ink-2:#52514e; --muted:#8a887f;
    --line:#e7e5e0; --s1:#2a78d6; --s1-soft:#9ec5f4; --gray:#b6b3aa; --neg:#2a78d6; --pos:#eb6834;
    --grid:#efedea; --ref:#b6b3aa; --good:#0ca30c; --crit:#d03b3b; }
  @media (prefers-color-scheme: dark) { :root { --surface:#1a1a19; --card:#232322; --ink:#fff;
    --ink-2:#c3c2b7; --muted:#8f8d83; --line:#383835; --s1:#3987e5; --s1-soft:#2a5787;
    --gray:#5d5b54; --neg:#3987e5; --pos:#d95926; --grid:#2c2c2a; --ref:#5d5b54; } }
  body { background:var(--surface); color:var(--ink); font:15px/1.6 -apple-system,"Segoe UI",Roboto,sans-serif; margin:0; padding:2.2rem 1.1rem 5rem; }
  main { max-width:980px; margin:0 auto; }
  h1 { font-size:1.7rem; margin:.3rem 0 .4rem; letter-spacing:-.01em; }
  h2 { font-size:1.15rem; margin:2.6rem 0 .6rem; }
  .eyebrow { font-size:.72rem; font-weight:700; letter-spacing:.13em; text-transform:uppercase; color:var(--s1); }
  .meta { color:var(--muted); font-size:.85rem; max-width:78ch; }
  p { max-width:72ch; }
  .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:.8rem; margin:1.4rem 0; }
  .kpi { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:.8rem 1rem; }
  .kpi .v { font-size:1.7rem; font-weight:700; font-variant-numeric:tabular-nums; }
  .kpi .l { font-size:.78rem; color:var(--ink-2); line-height:1.35; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:1rem 1.1rem 1.2rem; margin:1rem 0; }
  .card h3 { margin:0 0 .1rem; font-size:.95rem; }
  .sub { color:var(--muted); font-size:.8rem; margin:0 0 .6rem; max-width:78ch; }
  svg { width:100%; height:auto; display:block; }
  .tip { position:fixed; pointer-events:none; background:var(--ink); color:var(--surface); font-size:.75rem; padding:.3rem .55rem; border-radius:6px; opacity:0; transition:opacity .08s; z-index:10; max-width:280px; }
  table { border-collapse:collapse; font-size:.82rem; width:100%; }
  th,td { text-align:right; padding:.3rem .6rem; border-top:1px solid var(--line); font-variant-numeric:tabular-nums; }
  th:first-child,td:first-child { text-align:left; }
  thead th { border-top:none; font-size:.7rem; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }
  .algo { background:var(--card); border:1px solid var(--line); border-left:4px solid var(--s1); border-radius:10px; padding:1rem 1.2rem; }
  pre { background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:.8rem 1rem; overflow-x:auto; font:.82rem/1.6 ui-monospace,Menlo,monospace; }
  .oos { border-left:4px solid var(--good); }
  ul { max-width:74ch; }
  a { color:var(--s1); }
  .foot { color:var(--muted); font-size:.8rem; border-top:1px solid var(--line); margin-top:3rem; padding-top:1rem; }
</style></head><body>
<main>
  <div class="eyebrow">ESA · Estimate Accuracy Model · v__VERSION__</div>
  <h1>What runs actually take: estimates vs reality</h1>
  <p class="meta">__N__ runs with measured slot times across four ESA events — Summer 2022, Summer 2025, Winter 2026 and Summer 2026 — compared against the runners' submitted estimates. Ground truth: ESA run-timing sheets (timer start/stop, intro/outro speech, setup) and frame-exact VOD cut durations, never archived Horaro. Source data, scripts and the fitted <code>model.json</code>: <a href="https://github.com/esamarathon/estimate-accuracy-model">esamarathon/estimate-accuracy-model</a>.</p>

  <div class="kpis">
    <div class="kpi"><div class="v">__RUNMED__</div><div class="l">median run vs estimate — runners finish <b>under</b>, not over</div></div>
    <div class="kpi"><div class="v">__SLOTSOVER__%</div><div class="l">of slots (speech + run) still exceed the estimate</div></div>
    <div class="kpi"><div class="v">__SPEECHMED__</div><div class="l">median intro + outro speech — flat, never in the estimate</div></div>
    <div class="kpi"><div class="v">__SETUPOVER__%</div><div class="l">of setups blow the 10-minute default (p80 __SETUPP80__)</div></div>
    <div class="kpi"><div class="v">+3–4 min</div><div class="l">p80 slot overrun, near-constant under 2 h (+8 min above)</div></div>
  </div>

  <div class="card oos">
    <h3>Out-of-sample: Summer 2026 confirmed the model</h3>
    <p class="sub" style="margin-bottom:0">The model was first fitted on 2022–early-2026 data. ESA Summer 2026's timing sheets arrived after the event and matched the predictions: 50% of slots over estimate, median slot delta −4 s, p80 +3.5 min, and whole-event drift of only −1.4 h across 179 runs — the best-behaved event of the four.</p>
  </div>

  <h2>1 · Estimate vs actual slot, run by run</h2>
  <div class="card">
    <h3>Actual slot time vs submitted estimate — __N__ runs</h3>
    <p class="sub">Log-log · the dashed line is "estimate was exactly right" · slot = intro speech + run + outro speech · hover any point</p>
    <svg id="scatter" viewBox="0 0 900 480" role="img" aria-label="Scatter of estimate versus actual slot time"></svg>
  </div>

  <h2>2 · Where the time goes</h2>
  <div class="card">
    <h3>Slot minus estimate — the whole distribution</h3>
    <p class="sub">2-minute bins, clipped at ±30 · blue = finished under the estimate, orange = ran over</p>
    <svg id="hist" viewBox="0 0 900 300" role="img" aria-label="Histogram of slot minus estimate in minutes"></svg>
  </div>
  <div class="card">
    <h3>Overrun by estimate length — p50 → p80</h3>
    <p class="sub">Median slot overrun (dark) stretching to the 80th percentile (light). Near-constant +3–4 min under two hours: the overhead is <b>additive</b> (speech), not proportional (bad estimates).</p>
    <svg id="dumb" viewBox="0 0 900 260" role="img" aria-label="Dumbbell chart of median to p80 overrun by estimate bucket"></svg>
  </div>
  <div class="card">
    <h3>Setup time vs the 10-minute default</h3>
    <p class="sub">__NSETUP__ timed setups · dashed red = booked today · dashed green = what the data supports</p>
    <svg id="setup" viewBox="0 0 900 280" role="img" aria-label="Histogram of setup minutes with reference lines"></svg>
  </div>
  <div class="card">
    <h3>Per event: how much the schedule actually drifted</h3>
    <p class="sub">Total actual slot time minus total estimated time, whole event. Summer 2026 (highlighted) is the out-of-sample event.</p>
    <svg id="events" viewBox="0 0 900 240" role="img" aria-label="Per-event schedule drift bars"></svg>
  </div>

  <h2>3 · Findings</h2>
  <ul>
    <li><b>Runner estimates are honest — use them raw.</b> The median run finishes __RUNMED__ <i>under</i> its estimate; only a third run over. Estimates have tightened over the years, so the old sandbag buffer is eroding.</li>
    <li><b>The speeches are the systematic error.</b> Intro + outro add a flat __SPEECHMED__ median per run regardless of length — that unbooked tax puts __SLOTSOVER__% of slots over their estimate even though most runs finish under.</li>
    <li><b>The tail is asymmetric.</b> A blown no-reset run loses 10–19 minutes (p95); a great run saves only a few. Worst <i>relative</i> risk: sub-20-minute runs (p80 ×1.26). Worst <i>absolute</i> risk: &gt;2 h runs (p80 +8 m).</li>
    <li><b>Setup — not estimates — drains the schedule.</b> __SETUPOVER__% of setups exceed the booked 10 minutes (p80 __SETUPP80__). Book 15.</li>
    <li><b>Per-runner bias does not replicate</b> between events (corr −0.12 on repeat runners) — "runner X always overruns" is noise.</li>
  </ul>

  <h2>4 · The predictor</h2>
  <div class="algo">
<pre>speech      = 2:30                     # median; 4:00 for p80 planning
run_p50     = estimate × r50(bucket)   # table below — ≈ estimate
slot_p50    = run_p50 + speech         # honest booking
slot_p80    = estimate + 3–4 min       # &lt; 2 h runs — flat
            = estimate + 8 min         # &gt; 2 h runs
setup       : book 15:00, not 10:00    # p50 11:30 · p80 __SETUPP80__
flag_risk   = estimate &lt; 20 min        # relative spread ×1.26 p80
            ∨ estimate &gt; 2 h           # absolute tail +8 m</pre>
    <table><thead><tr><th>estimate bucket</th><th>n</th><th>slot/est p50</th><th>p80</th><th>Δ p50</th><th>Δ p80</th></tr></thead>
    <tbody id="modeltable"></tbody></table>
    <p class="sub" style="margin-top:.6rem">Machine-readable version with exact quantiles: <a href="https://github.com/esamarathon/estimate-accuracy-model/blob/main/model/model.json">model/model.json</a>. A day scheduled at slot_p50 per run + 15-minute setups reproduces historical day totals within ±1%.</p>
  </div>

  <h2>5 · Method &amp; caveats</h2>
  <ul>
    <li><b>Archived Horaro is NOT real times</b> — 92–94% of its "final" lengths still equal the submitted estimate (ESA amends start drift live, not lengths). Regressing on it concludes estimates are near-perfect.</li>
    <li>Summer 2025 has no timing sheet; its slot times are YouTube VOD cut durations, validated to equal sheet slot times to the second (median 0 s, p90 ±2 s, on 94 doubly-covered runs). Its speech/setup split is unavailable.</li>
    <li>Speech/opening rows and runs without valid timer data are excluded. Only scheduled runs are observable — which is the scheduling use case.</li>
  </ul>

  <p class="foot">Generated by <code>scripts/build_report.py</code> from the repository data. To refresh after adding an event: <code>build_model.py</code> then <code>build_report.py</code>.</p>
</main>
<div class="tip" id="tip"></div>
<script>
const DATA = __DATA__;
const tip = document.getElementById("tip");
function showTip(ev, html) { tip.innerHTML = html; tip.style.opacity = 1; tip.style.left = Math.min(innerWidth-300, ev.clientX+14)+"px"; tip.style.top = (ev.clientY+12)+"px"; }
function hideTip() { tip.style.opacity = 0; }
const fmtM = s => (s>=0?"+":"−") + Math.abs(Math.round(s/60)) + "m";
const fmtHM = s => { const h = Math.floor(s/3600), m = Math.round(s%3600/60); return h ? h+"h"+String(m).padStart(2,"0") : m+"m"; };

(function(){ // scatter — single hue (identity isn't this chart's job)
  const W=900,H=480,L=56,R=16,T=12,B=40;
  const lo=Math.log10(4*60), hi=Math.log10(9*3600);
  const x=v=>L+(Math.log10(v)-lo)/(hi-lo)*(W-L-R), y=v=>H-B-(Math.log10(v)-lo)/(hi-lo)*(H-T-B);
  let g="";
  for (const t of [300,600,1200,2400,3600,7200,4*3600,8*3600]) {
    g+=`<line x1="${x(t)}" y1="${T}" x2="${x(t)}" y2="${H-B}" stroke="var(--grid)"/><text x="${x(t)}" y="${H-B+16}" text-anchor="middle" font-size="11" fill="var(--muted)">${fmtHM(t)}</text>`;
    g+=`<line x1="${L}" y1="${y(t)}" x2="${W-R}" y2="${y(t)}" stroke="var(--grid)"/><text x="${L-6}" y="${y(t)+4}" text-anchor="end" font-size="11" fill="var(--muted)">${fmtHM(t)}</text>`;
  }
  g+=`<line x1="${x(4*60)}" y1="${y(4*60)}" x2="${x(9*3600)}" y2="${y(9*3600)}" stroke="var(--ref)" stroke-width="1.5" stroke-dasharray="5 4"/>`;
  for (const p of DATA.scatter) g+=`<circle cx="${x(p.e)}" cy="${y(p.s)}" r="4" fill="var(--s1)" fill-opacity="0.55" data-t="${p.ev} · est ${fmtHM(p.e)} → slot ${fmtHM(p.s)} (${fmtM(p.s-p.e)})"/>`;
  g+=`<text x="${W/2}" y="${H-4}" text-anchor="middle" font-size="11" fill="var(--ink-2)">submitted estimate</text>`;
  g+=`<text transform="rotate(-90)" x="${-(H/2)}" y="14" text-anchor="middle" font-size="11" fill="var(--ink-2)">actual slot</text>`;
  document.getElementById("scatter").innerHTML=g;
})();

(function(){ // delta histogram (diverging by sign)
  const W=900,H=300,L=40,R=16,T=14,B=34, bins=DATA.dbins;
  const keys=Object.keys(bins).map(Number).sort((a,b)=>a-b), maxN=Math.max(...Object.values(bins));
  const x=v=>L+(v+30)/62*(W-L-R), bw=(W-L-R)/31-2;
  let g="";
  for (let n=20;n<=maxN;n+=20) { const yy=H-B-n/maxN*(H-T-B); g+=`<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}" stroke="var(--grid)"/><text x="${L-5}" y="${yy+4}" text-anchor="end" font-size="10" fill="var(--muted)">${n}</text>`; }
  for (const k of keys) { const n=bins[k], h=n/maxN*(H-T-B);
    const col = k<0 ? "var(--neg)" : k>=2 ? "var(--pos)" : "var(--gray)";
    g+=`<rect x="${x(k)}" y="${H-B-h}" width="${bw}" height="${h}" rx="3" fill="${col}" data-t="${k}…${k+2} min: ${n} runs"/>`; }
  g+=`<line x1="${x(0)-1}" y1="${T}" x2="${x(0)-1}" y2="${H-B}" stroke="var(--ink-2)"/>`;
  for (const t of [-30,-20,-10,0,10,20,30]) g+=`<text x="${x(t)+bw/2}" y="${H-B+15}" text-anchor="middle" font-size="10" fill="var(--muted)">${t>0?"+"+t:t}</text>`;
  g+=`<text x="${W/2}" y="${H-3}" text-anchor="middle" font-size="11" fill="var(--ink-2)">actual slot − estimate (minutes) · ±30 clipped</text>`;
  document.getElementById("hist").innerHTML=g;
})();

(function(){ // dumbbell p50→p80 per bucket
  const W=900,H=260,L=90,R=46,T=16,B=36, m=DATA.model;
  const lo=-2, hi=9, x=v=>L+(v-lo)/(hi-lo)*(W-L-R), rowH=(H-T-B)/m.length;
  let g="";
  for (let v=lo;v<=hi;v++){ g+=`<line x1="${x(v)}" y1="${T}" x2="${x(v)}" y2="${H-B}" stroke="var(--grid)"/>`;
    if (v%2===0) g+=`<text x="${x(v)}" y="${H-B+15}" text-anchor="middle" font-size="10" fill="var(--muted)">${v>0?"+"+v:v}m</text>`; }
  g+=`<line x1="${x(0)}" y1="${T}" x2="${x(0)}" y2="${H-B}" stroke="var(--ink-2)"/>`;
  m.forEach((b,i)=>{ const cy=T+rowH*i+rowH/2, x1=x(b.slot_delta_p50_s/60), x2=x(b.slot_delta_p80_s/60);
    g+=`<text x="${L-8}" y="${cy+4}" text-anchor="end" font-size="12" fill="var(--ink-2)">${b.bucket}</text>`;
    g+=`<line x1="${x1}" y1="${cy}" x2="${x2}" y2="${cy}" stroke="var(--s1-soft)" stroke-width="3"/>`;
    g+=`<circle cx="${x1}" cy="${cy}" r="6" fill="var(--s1)" data-t="${b.bucket}: median ${fmtM(b.slot_delta_p50_s)} (n=${b.n})"/>`;
    g+=`<circle cx="${x2}" cy="${cy}" r="6" fill="var(--s1-soft)" stroke="var(--s1)" stroke-width="1.5" data-t="${b.bucket}: p80 ${fmtM(b.slot_delta_p80_s)} (n=${b.n})"/>`;
    g+=`<text x="${Math.max(x1,x2)+12}" y="${cy+4}" font-size="11" fill="var(--ink-2)">${fmtM(b.slot_delta_p80_s)}</text>`; });
  g+=`<text x="${W/2}" y="${H-3}" text-anchor="middle" font-size="11" fill="var(--ink-2)">slot overrun (minutes) · ● median → ○ p80</text>`;
  document.getElementById("dumb").innerHTML=g;
})();

(function(){ // setup histogram + reference lines
  const W=900,H=280,L=40,R=16,T=16,B=34, bins=DATA.sbins;
  const keys=Object.keys(bins).map(Number).sort((a,b)=>a-b), maxN=Math.max(...Object.values(bins));
  const x=v=>L+v/42*(W-L-R), bw=(W-L-R)/21-2;
  let g="";
  for (let n=20;n<=maxN;n+=20){ const yy=H-B-n/maxN*(H-T-B); g+=`<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}" stroke="var(--grid)"/><text x="${L-5}" y="${yy+4}" text-anchor="end" font-size="10" fill="var(--muted)">${n}</text>`; }
  for (const k of keys){ const n=bins[k], h=n/maxN*(H-T-B);
    g+=`<rect x="${x(k)}" y="${H-B-h}" width="${bw}" height="${h}" rx="3" fill="var(--s1)" data-t="${k}–${k+2} min setup: ${n}"/>`; }
  g+=`<line x1="${x(10)}" y1="${T}" x2="${x(10)}" y2="${H-B}" stroke="var(--crit)" stroke-width="1.5" stroke-dasharray="5 4"/><text x="${x(10)+5}" y="${T+12}" font-size="11" fill="var(--crit)">booked: 10m</text>`;
  g+=`<line x1="${x(15)}" y1="${T}" x2="${x(15)}" y2="${H-B}" stroke="var(--good)" stroke-width="1.5" stroke-dasharray="5 4"/><text x="${x(15)+5}" y="${T+12}" font-size="11" fill="var(--good)">proposed: 15m</text>`;
  for (const t of [0,10,20,30,40]) g+=`<text x="${x(t)}" y="${H-B+15}" text-anchor="middle" font-size="10" fill="var(--muted)">${t}${t===40?"+":""}</text>`;
  g+=`<text x="${W/2}" y="${H-3}" text-anchor="middle" font-size="11" fill="var(--ink-2)">setup minutes (2-min bins, 40+ folded)</text>`;
  document.getElementById("setup").innerHTML=g;
})();

(function(){ // per-event drift — emphasis form: S26 accent, rest gray
  const W=900,H=240,L=170,R=60,T=16,B=36, evs=DATA.per_event;
  const drifts=evs.map(e=>e.total_slot_h-e.total_est_h);
  const lo=Math.min(-2,...drifts)-0.4, hi=Math.max(3,...drifts)+0.4;
  const x=v=>L+(v-lo)/(hi-lo)*(W-L-R), rowH=(H-T-B)/evs.length;
  let g="";
  for (let v=Math.ceil(lo);v<=Math.floor(hi);v++){ g+=`<line x1="${x(v)}" y1="${T}" x2="${x(v)}" y2="${H-B}" stroke="var(--grid)"/><text x="${x(v)}" y="${H-B+15}" text-anchor="middle" font-size="10" fill="var(--muted)">${v>0?"+"+v:v}h</text>`; }
  g+=`<line x1="${x(0)}" y1="${T}" x2="${x(0)}" y2="${H-B}" stroke="var(--ink-2)"/>`;
  evs.forEach((e,i)=>{ const d=e.total_slot_h-e.total_est_h, cy=T+rowH*i+rowH/2;
    const oos = e.ev==="ESA Summer 2026";
    const col = oos ? "var(--s1)" : "var(--gray)";
    const x0=x(Math.min(0,d)), x1=x(Math.max(0,d));
    g+=`<text x="${L-8}" y="${cy+4}" text-anchor="end" font-size="12" fill="var(--ink-2)"${oos?' font-weight="700"':''}>${e.ev.replace("ESA ","")}${oos?" ★":""}</text>`;
    g+=`<rect x="${x0}" y="${cy-9}" width="${Math.max(2,x1-x0)}" height="18" rx="4" fill="${col}" data-t="${e.ev}: ${e.total_est_h}h estimated → ${e.total_slot_h}h actual (${d>0?"+":""}${d.toFixed(1)}h over ${e.n} runs)"/>`;
    g+=`<text x="${(d>=0?x1:x0)+(d>=0?6:-6)}" y="${cy+4}" font-size="11" text-anchor="${d>=0?"start":"end"}" fill="var(--ink-2)">${d>0?"+":""}${d.toFixed(1)}h</text>`; });
  g+=`<text x="${W/2}" y="${H-3}" text-anchor="middle" font-size="11" fill="var(--ink-2)">whole-event drift: actual − estimated (hours) · ★ out-of-sample</text>`;
  document.getElementById("events").innerHTML=g;
})();

document.getElementById("modeltable").innerHTML = DATA.model.map(b =>
  `<tr><td>${b.bucket}</td><td>${b.n}</td><td>${b.slot_ratio_p50.toFixed(3)}</td><td>${b.slot_ratio_p80.toFixed(3)}</td><td>${fmtM(b.slot_delta_p50_s)}</td><td>${fmtM(b.slot_delta_p80_s)}</td></tr>`).join("");

document.querySelectorAll("[data-t]").forEach(el => {
  el.addEventListener("mousemove", ev => showTip(ev, el.getAttribute("data-t")));
  el.addEventListener("mouseleave", hideTip);
});
</script>
</body></html>"""

out = (HTML
  .replace("__VERSION__", str(model["version"]))
  .replace("__N__", str(kpi["n"]))
  .replace("__RUNMED__", fmt_sec(kpi["run_med"]))
  .replace("__SLOTSOVER__", str(kpi["slots_over"]))
  .replace("__SPEECHMED__", fmt_sec(kpi["speech_med"]))
  .replace("__SETUPOVER__", str(kpi["setup_over"]))
  .replace("__SETUPP80__", fmt_sec(kpi["setup_p80"], signed=False))
  .replace("__NSETUP__", str(len(setups)))
  .replace("__DATA__", json.dumps(data, separators=(",", ":"))))
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs/index.html").write_text(out)
print(f"docs/index.html · {len(out)//1024} KB · {kpi}")
