#!/usr/bin/env python3
"""Fit the ESA estimate-accuracy model from every timing sheet in
data/run-timings/*.csv plus the S25 VOD-derived slot rows, and write
model/model.json — the canonical, versioned output of this repository.

Definitions (per run):
  run    = TimerEnd − TimerStart          (the speedrun itself)
  speech = IntroTime + OutroTime          (on-stream, never in the estimate)
  slot   = EndTimestamp − StartTimestamp  (what the run occupies between setups)
  setup  = StartTimestamp − previous EndTimestamp

Usage: python3 scripts/build_model.py
"""
import csv, json, glob, re, statistics, pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUCKETS = [(0, 1200, "<20m"), (1200, 2400, "20-40m"), (2400, 3600, "40-60m"),
           (3600, 7200, "1-2h"), (7200, 10**9, ">2h")]

def hms(s):
    if not s or not str(s).strip(): return None
    try: p = [int(x) for x in str(s).strip().split(":")]
    except ValueError: return None
    if len(p) == 3: return p[0]*3600 + p[1]*60 + p[2]
    if len(p) == 2: return p[0]*60 + p[1]
    return None

def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs)-1, int(len(xs)*p))]

def event_name(path):
    stem = pathlib.Path(path).stem  # e.g. esa-summer-2026-s1
    m = re.match(r"esa-(\w+)-(\d{4})", stem)
    return f"ESA {m.group(1).title()} {m.group(2)}" if m else stem

rows = []
for f in sorted(glob.glob(str(ROOT / "data/run-timings/*.csv"))):
    ev = event_name(f)
    for r in csv.DictReader(open(f)):
        game, cat = (r.get("GameName") or "").strip(), (r.get("CategoryName") or "").strip()
        if not game or "speech" in game.lower() or "speech" in cat.lower(): continue
        est, run = hms(r.get("Estimate")), hms(r.get("Actual Time"))
        if not est or not run or est <= 0: continue
        try:
            slot = int(r["EndTimestamp"]) - int(r["StartTimestamp"])
        except (KeyError, ValueError):
            slot = None
        intro = int(r["IntroTime"]) if (r.get("IntroTime") or "").strip().isdigit() else None
        outro = int(r["OutroTime"]) if (r.get("OutroTime") or "").strip().isdigit() else None
        rows.append({"event": ev, "game": game, "category": cat, "est": est, "run": run,
                     "slot": slot if slot and slot >= run else None,
                     "speech": (intro + outro) if intro is not None and outro is not None else None,
                     "setup": hms(r.get("Setup Time"))})

# S25 has no timing sheet — its slot times come from frame-exact VOD cuts
# (validated ±2s against the W26 sheet; see README). Slot-only rows.
vod_csv = ROOT / "data/derived/matched-vod.csv"
if vod_csv.exists():
    for r in csv.DictReader(open(vod_csv)):
        if r["event"] != "ESA Summer 2025": continue
        rows.append({"event": "ESA Summer 2025", "game": r["game"], "category": r["category"],
                     "est": int(r["est_s"]), "run": None, "slot": int(r["vod_s"]),
                     "speech": None, "setup": None})

events = sorted({r["event"] for r in rows})
print(f"rows: {len(rows)} across {events}")

def stats(xs):
    return {"n": len(xs), "p50": pct(xs, .5), "p80": pct(xs, .8), "p95": pct(xs, .95),
            "mean": round(statistics.mean(xs), 1)}

slot_rows = [r for r in rows if r["slot"]]
run_rows = [r for r in rows if r["run"]]
speech = [r["speech"] for r in rows if r["speech"] is not None]
setups = [r["setup"] for r in rows if r["setup"]]

table = []
for lo, hi, label in BUCKETS:
    sub = [r for r in slot_rows if lo <= r["est"] < hi]
    ratios = [r["slot"]/r["est"] for r in sub]
    deltas = [r["slot"]-r["est"] for r in sub]
    table.append({"bucket": label, "lo_s": lo, "hi_s": min(hi, 86400), "n": len(sub),
                  "slot_ratio_p50": round(pct(ratios, .5), 3), "slot_ratio_p80": round(pct(ratios, .8), 3),
                  "slot_delta_p50_s": int(pct(deltas, .5)), "slot_delta_p80_s": int(pct(deltas, .8))})

per_event = {}
for ev in events:
    sub = [r for r in slot_rows if r["event"] == ev]
    if not sub: continue
    d = [r["slot"]-r["est"] for r in sub]
    per_event[ev] = {"n": len(sub), "slot_delta": stats(d),
                     "pct_slots_over": round(100*sum(1 for x in d if x > 0)/len(d)),
                     "total_est_h": round(sum(r["est"] for r in sub)/3600, 1),
                     "total_slot_h": round(sum(r["slot"] for r in sub)/3600, 1)}

under2h = [r["slot"]-r["est"] for r in slot_rows if r["est"] < 7200]
over2h = [r["slot"]-r["est"] for r in slot_rows if r["est"] >= 7200]

model = {
    "name": "esa-estimate-accuracy-model",
    "version": 2,
    "fitted_on": {ev: per_event.get(ev, {}).get("n", 0) for ev in events},
    "definitions": "slot = intro speech + run + outro speech; the time a run occupies between setups",
    "components": {
        "run_vs_estimate_delta": stats([r["run"]-r["est"] for r in run_rows]) if run_rows else None,
        "speech": stats(speech) if speech else None,
        "setup": {**stats(setups), "pct_over_600s": round(100*sum(1 for s in setups if s > 600)/len(setups))} if setups else None,
    },
    "slot_table": table,
    "flat_rules": {
        "slot_p80_under_2h_s": int(pct(under2h, .8)),
        "slot_p80_over_2h_s": int(pct(over2h, .8)),
        "speech_allowance_p50_s": int(pct(speech, .5)) if speech else None,
        "speech_allowance_p80_s": int(pct(speech, .8)) if speech else None,
        "recommended_setup_default_s": 900,
    },
    "per_event": per_event,
    "notes": [
        "Runner estimates are honest: use them as the run-time predictor; never inflate.",
        "Overhead is additive (speech), not proportional — corr(estimate, overrun) ~ 0.",
        "Per-runner bias does not replicate between events (corr -0.12, n=24): no runner-history features.",
        "Flag tails: <20m runs (worst relative spread) and >2h runs (worst absolute tail).",
    ],
}
(ROOT / "model").mkdir(exist_ok=True)
json.dump(model, open(ROOT / "model/model.json", "w"), indent=2)

print(f"\nslot rows {len(slot_rows)} · run rows {len(run_rows)} · speech {len(speech)} · setups {len(setups)}")
for ev, s in per_event.items():
    print(f"  {ev}: n={s['n']} · {s['pct_slots_over']}% slots over · slot Δ p50 {s['slot_delta']['p50']:+d}s p80 {s['slot_delta']['p80']:+d}s · est {s['total_est_h']}h → {s['total_slot_h']}h")
print("\nbucket table:")
for b in table:
    print(f"  {b['bucket']:>7} n={b['n']:3d} · ratio p50 {b['slot_ratio_p50']:.3f} p80 {b['slot_ratio_p80']:.3f} · Δ p80 {b['slot_delta_p80_s']//60:+d}m")
print(f"\nflat: p80 <2h {model['flat_rules']['slot_p80_under_2h_s']//60:+d}m · >2h {model['flat_rules']['slot_p80_over_2h_s']//60:+d}m")
print("wrote model/model.json")
