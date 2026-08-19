#!/usr/bin/env python3
"""Stage 2: join VOD durations (actual broadcast slot per run) onto the
matched Oengus-estimate rows; quantify error; fit a simple prediction model.

actual = VOD cut duration (includes runner intro + outro speech — the very
overhead runners don't put in their estimate). delta = actual - estimate.
"""
import json, csv, re, statistics, pathlib
from collections import defaultdict

OUT = pathlib.Path(__file__).parent

durations = {}
for line in open(OUT / "durations.tsv"):
    parts = line.rstrip("\n").replace("\\t", "\t").split("\t")
    if len(parts) >= 2 and parts[1] not in ("NA", "None", ""):
        try: durations[parts[0]] = int(float(parts[1]))
        except ValueError: pass

vidmap = json.load(open(OUT / "vid-map.json"))
# (file, item index) -> video id
loc2vid = {}
for vid, locs in vidmap.items():
    for f, idx in locs: loc2vid[(f, idx)] = vid

# rebuild (file, idx) for matched rows by re-walking the schedules the same
# way analyze.py did (row order among run-rows is preserved in matched.csv)
BREAK_RE = re.compile(r"^(break|intermission|opening|closing|finale|sleep|day \d|setup|the checkpoint|hype|prehype|pre-show|preshow|end of|donation|showcase\?*$)", re.I)
def run_rows(f):
    d = json.load(open(OUT / f)); d = d.get("data", d)
    gi = d["columns"].index("Game")
    out = []
    for idx, it in enumerate(d["items"]):
        game_raw = it["data"][gi] or ""
        game = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", game_raw).strip()
        if not game or BREAK_RE.search(game): continue
        out.append((idx, game))
    return out

schedule_files = {"2026-winter1": "horaro-2026-winter1.json", "2026-winter2": "horaro-2026-winter2.json",
                  "2025-summer1": "horaro-2025-summer1.json", "2025-summer2": "horaro-2025-summer2.json"}
runrows = {s: run_rows(f) for s, f in schedule_files.items()}
counters = defaultdict(int)

rows = []
for m in csv.DictReader(open(OUT / "matched.csv")):
    s = m["schedule"]
    vid = loc2vid.get((schedule_files[s], int(m["item_idx"])))
    dur = durations.get(vid) if vid else None
    if dur is None or dur < 60: continue
    est = int(m["est_s"])
    if est <= 0: continue
    rows.append({**m, "est_s": est, "vod_s": dur, "delta_s": dur - est, "ratio": dur / est})

print(f"rows with VOD duration: {len(rows)}")

def fmt(sec):
    sign = "-" if sec < 0 else ""
    sec = abs(int(sec)); return f"{sign}{sec//3600}:{(sec%3600)//60:02d}:{sec%60:02d}"

def pct(xs, p):
    xs = sorted(xs); return xs[min(len(xs)-1, int(len(xs)*p))]

for ev in ["ESA Winter 2026", "ESA Summer 2025", None]:
    sub = [r for r in rows if ev is None or r["event"] == ev]
    if not sub: continue
    deltas = [r["delta_s"] for r in sub]; ratios = [r["ratio"] for r in sub]
    over = sum(1 for d in deltas if d > 60)
    under = sum(1 for d in deltas if d < -60)
    print(f"\n--- {ev or 'COMBINED'} (n={len(sub)}) ---")
    print(f"ran LONGER than estimate: {over} ({100*over/len(sub):.0f}%) · shorter: {under} ({100*under/len(sub):.0f}%)")
    print(f"delta  median {fmt(statistics.median(deltas))} · mean {fmt(statistics.mean(deltas))} · p80 {fmt(pct(deltas,0.8))} · p95 {fmt(pct(deltas,0.95))}")
    print(f"ratio  median {statistics.median(ratios):.3f} · mean {statistics.mean(ratios):.3f} · p80 {pct(ratios,0.8):.3f} · p95 {pct(ratios,0.95):.3f}")

# error by estimate-length bucket
print("\n--- by estimate bucket (combined) ---")
buckets = [(0, 1200, "<20m"), (1200, 2400, "20–40m"), (2400, 3600, "40–60m"), (3600, 7200, "1–2h"), (7200, 10**9, ">2h")]
bucket_stats = []
for lo, hi, label in buckets:
    sub = [r for r in rows if lo <= r["est_s"] < hi]
    if len(sub) < 5: continue
    deltas = [r["delta_s"] for r in sub]; ratios = [r["ratio"] for r in sub]
    st = {"label": label, "n": len(sub), "med_delta": statistics.median(deltas),
          "med_ratio": statistics.median(ratios), "p80_ratio": pct(ratios, 0.8),
          "med_abs_min": statistics.median([abs(d) for d in deltas]) / 60}
    bucket_stats.append(st)
    print(f"{label:>7} n={st['n']:3d} · median delta {fmt(st['med_delta'])} · median ratio {st['med_ratio']:.3f} · p80 ratio {st['p80_ratio']:.3f}")

# by run type
print("\n--- by run type (combined) ---")
for t in ["SINGLE", "RACE", "COOP", "COOP_RACE", "RELAY", "RELAY_RACE", "OTHER"]:
    sub = [r for r in rows if (r["run_type"] or "SINGLE").upper() == t]
    if len(sub) < 4: continue
    deltas = [r["delta_s"] for r in sub]
    print(f"{t:>10} n={len(sub):3d} · median delta {fmt(statistics.median(deltas))} · median ratio {statistics.median([r['ratio'] for r in sub]):.3f}")

# additive vs multiplicative: correlation of delta with estimate
ests = [r["est_s"] for r in rows]; deltas = [r["delta_s"] for r in rows]
n = len(rows)
mx, my = statistics.mean(ests), statistics.mean(deltas)
cov = sum((x-mx)*(y-my) for x, y in zip(ests, deltas)) / n
sx = (sum((x-mx)**2 for x in ests)/n) ** 0.5; sy = (sum((y-my)**2 for y in deltas)/n) ** 0.5
print(f"\ncorr(estimate, delta) = {cov/(sx*sy):.3f}  (≈0 → overhead is ADDITIVE, not proportional)")

# simple model: predicted = a + b*estimate, fit on combined via least squares
b = cov / (sx*sx)
a = my - b*mx
print(f"least squares: delta ≈ {fmt(a)} + {b:.4f}·estimate → predicted = {fmt(a)} + {1+b:.4f}·estimate")
resid = [d - (a + b*e) for e, d in zip(ests, deltas)]
print(f"residual p80 {fmt(pct(resid,0.8))} · p95 {fmt(pct(resid,0.95))}")

json.dump({"rows": rows, "buckets": bucket_stats, "model": {"a": a, "b": b}}, open(OUT / "vod-analysis.json", "w"))
with open(OUT / "matched-vod.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
print("\nwrote vod-analysis.json + matched-vod.csv")
