#!/usr/bin/env python3
"""Convert an ESA run-timing workbook (tab `runtimings`) to the canonical CSV.

The Google-Sheet CSV exports carry computed values, but xlsx exports carry
FORMULAS for Actual Time / % Off Estimate (and often no Setup Time), so this
recomputes everything from the raw timestamps:

  Actual Time     = TimerEndTimestamp − TimerStartTimestamp
  % Off Estimate  = (actual − estimate) / estimate
  Setup Time      = StartTimestamp − previous row's EndTimestamp
                    (validated exact, 100/100, against the W26 sheet values;
                     blanked when > 2h — that's an overnight break, not setup)

Usage: python3 scripts/convert_xlsx.py <in.xlsx> <out.csv>
"""
import csv, sys
import openpyxl

COLS = ["", "UUID", "GameName", "CategoryName", "PlayerNamesTwitch",
        "StartTimestamp", "EndTimestamp", "TimerStartTimestamp", "TimerEndTimestamp",
        "IntroTime", "OutroTime", "", "Estimate", "Actual Time", "% Off Estimate", "Setup Time"]

def hms(sec):
    sec = int(round(sec))
    return f"{sec//3600}:{(sec%3600)//60:02d}:{sec%60:02d}"

def cell_str(v):
    if v is None: return ""
    if isinstance(v, float) and v.is_integer(): return str(int(v))
    return str(v)

def main(inp, outp):
    wb = openpyxl.load_workbook(inp, read_only=True)
    ws = wb["runtimings"]
    rows = []
    prev_end = None
    for i, raw in enumerate(ws.iter_rows(values_only=True)):
        if i == 0: continue  # header
        vals = list(raw) + [None] * (16 - len(raw))
        uuid, game, cat = vals[1], vals[2], vals[3]
        if not uuid or not game: continue
        try:
            start, end = int(vals[5]), int(vals[6])
            tstart, tend = int(vals[7]), int(vals[8])
        except (TypeError, ValueError):
            continue
        actual = tend - tstart
        est = cell_str(vals[12])
        # estimate as H:MM:SS text; xlsx sometimes yields datetime.time
        if hasattr(vals[12], "hour"):
            est = f"{vals[12].hour:02d}:{vals[12].minute:02d}:{vals[12].second:02d}"
        setup = ""
        if prev_end is not None:
            gap = start - prev_end
            if 0 <= gap <= 7200: setup = hms(gap)
        prev_end = end
        pct = ""
        def est_s(s):
            try:
                p = [int(x) for x in s.split(":")]
                return p[0]*3600 + p[1]*60 + p[2] if len(p) == 3 else None
            except ValueError:
                return None
        es = est_s(est)
        if es: pct = f"{(actual-es)/es*100:.2f}%"
        rows.append(["", cell_str(uuid), cell_str(game), cell_str(cat), cell_str(vals[4]),
                     start, end, tstart, tend, cell_str(vals[9]), cell_str(vals[10]), "",
                     est, hms(actual), pct, setup])
    with open(outp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        w.writerows(rows)
    print(f"{outp}: {len(rows)} rows")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
