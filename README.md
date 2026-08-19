# ESA Estimate Accuracy Model

What speedrun slots **actually** take at ESA marathons, measured — and the model
fitted from it. **558 runs with real timed slots across four events**:
ESA Summer 2022, ESA Summer 2025, ESA Winter 2026 and ESA Summer 2026,
compared against the runners' submitted (Oengus) estimates.

The canonical output is [`model/model.json`](model/model.json) — regenerate it
any time with `python3 scripts/build_model.py`.

## Definitions

```
run    = TimerEnd − TimerStart           # the speedrun itself
speech = IntroTime + OutroTime           # on-stream, never in any estimate
slot   = intro speech + run + outro      # what the run occupies between setups
setup  = this Start − previous End
```

## Findings

1. **Runner estimates are honest — use them raw.** The median run finishes
   ~2:30 *under* its estimate; only a third run over. Never inflate estimates:
   they are the best run-time predictor available, and padding double-counts.
2. **The speeches are the systematic unbooked cost.** Intro + outro add a flat
   ~2:30 median (p80 ~4:00) per run regardless of length. That tax alone puts
   ~half of all slots over their estimate even though most runs finish under.
3. **Overhead is additive, not proportional.** The p80 slot overrun is a
   near-constant **+3–4 min for every run length under 2 h** (+8 min above).
   Correlation of overrun with estimate size ≈ 0.
4. **Setup is the real schedule drain.** ~60% of setups exceed the 10-minute
   default (median ~11:30, p80 ~17:00) — +10 h of unbooked drift across two
   events. **Book 15 minutes, not 10.**
5. **Per-runner bias does not replicate** between events (corr −0.12, n=24
   repeat runners). "Runner X always overruns" is noise — build nothing on it.
6. **Tails are asymmetric.** A blown no-reset run loses 10–19 min (p95); a
   great run saves only a few. Worst *relative* risk: sub-20-minute runs
   (p80 ×1.26). Worst *absolute* risk: >2 h runs (p80 +8 min).

### Out-of-sample check

The model was first fitted on S22 + S25 + W26 (379 runs). ESA Summer 2026's
timing sheets arrived afterwards and matched the predictions: 50% of slots
over, median slot Δ −4 s, p80 +3.5 min, whole-event drift −1.4 h over 179 runs.

## The model (v2, fitted on all four events)

| Estimate bucket | n | slot/est p50 | p80 | Δ p80 |
|---|---:|---:|---:|---:|
| < 20 m | 65 | 1.069 | 1.258 | +3 m |
| 20–40 m | 131 | 1.025 | 1.155 | +4 m |
| 40–60 m | 92 | 1.001 | 1.096 | +3 m |
| 1–2 h | 168 | 0.984 | 1.058 | +4 m |
| > 2 h | 102 | 1.008 | 1.047 | +8 m |

```
slot_p50  = estimate × slot_ratio_p50(bucket)      # honest booking
slot_p80  = estimate + 3–4 min   (< 2 h)           # near-flat
          = estimate + 8 min     (> 2 h)
setup     : book 15:00 (p50 11:30, p80 17:00) — the current 10:00 fails ~60% of the time
flag_risk : estimate < 20 min  (relative spread ×1.26 p80)
          ∨ estimate > 2 h     (absolute tail +8 m)
```

Per-event summaries, exact quantiles and these rules live in
[`model/model.json`](model/model.json).

## Repository layout

```
data/run-timings/         one canonical CSV per event/stream (+ originals/, the source workbooks)
data/horaro/              final public Horaro schedules (JSON)
data/oengus/              Oengus submissions 2024–2026 (JSON) — estimate provenance
data/derived/             matched runs, VOD durations (S25's slot source), intermediates
scripts/convert_xlsx.py   run-timing workbook → canonical CSV
scripts/build_model.py    fits everything → model/model.json
scripts/fetch.py          re-downloads Horaro/Oengus sources (polite pacing)
scripts/analyze*.py       the original research analyses (Horaro caveat, VOD calibration)
model/model.json          THE deliverable — versioned fitted model
report/report.html        interactive research report (v1 fit, three events)
```

## Adding a new event

1. Drop the run-timing workbook (tab `runtimings`) into `data/run-timings/originals/`.
2. `python3 scripts/convert_xlsx.py "data/run-timings/originals/<file>.xlsx" data/run-timings/esa-<season>-<year>[-sN].csv`
3. `python3 scripts/build_model.py` — refits and rewrites `model/model.json`.
4. Commit both.

The converter recomputes Actual/%Off/Setup from the raw timestamps (the xlsx
exports carry formulas, not values; setup = gap to the previous slot, validated
exact against the W26 sheet, blanked above 2 h = overnight break).

## Method notes & caveats

- **Archived Horaro is NOT real times.** 92–94% of its "final" lengths still
  equal the submitted estimate (ESA amends start drift live, not lengths).
  Never regress on it — it concludes estimates are near-perfect.
- **S25 has no timing sheet**; its slot times are YouTube VOD cut durations,
  which equal sheet slot times to the second (median 0 s, p90 ±2 s, validated
  on 94 W26 runs covered by both sources). Its speech/setup split is therefore
  unavailable; component stats come from the sheet events.
- Speech/opening rows and runs without valid timer data are excluded.
- Only scheduled runs are observable — which is the scheduling use case.

Research trail: the [interactive report](report/report.html) and the ESA
Summer 2026 feedback triage board carry these findings as MEASURED items.
