#!/usr/bin/env python3
"""Match final Horaro run lengths against Oengus submission estimates.

Outputs matched.csv (one row per matched run) + a printed summary with
match-rate diagnostics, error distribution, and amendment-rate caveat.
"""
import json, re, csv, unicodedata, statistics, pathlib
from collections import defaultdict

OUT = pathlib.Path(__file__).parent

EVENTS = {  # analysis event -> (horaro files, oengus file)
    "ESA Winter 2026": (["horaro-2026-winter1.json", "horaro-2026-winter2.json"], "oengus-ESA-Win26.json"),
    "ESA Summer 2025": (["horaro-2025-summer1.json", "horaro-2025-summer2.json"], "oengus-ESA-Sum25.json"),
}

BREAK_RE = re.compile(r"^(break|intermission|opening|closing|finale|sleep|day \d|setup|the checkpoint|hype|prehype|pre-show|preshow|end of|donation|showcase\?*$)", re.I)

def norm(s):
    if not s: return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)  # strip markdown links
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())

def tokens(s): return set(norm(s).split())

def jacc(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb: return 0.0
    return len(ta & tb) / len(ta | tb)

def iso_dur_seconds(s):
    if not s: return None
    m = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", s)
    if not m: return None
    h, mi, se = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + se

# ---- load Horaro runs -------------------------------------------------------
def load_horaro(files):
    runs = []
    for f in files:
        d = json.load(open(OUT / f))
        d = d.get("data", d)
        cols = d["columns"]
        gi, ci = cols.index("Game"), cols.index("Category")
        pi = cols.index("Player(s)") if "Player(s)" in cols else None
        for item_idx, it in enumerate(d["items"]):
            game_raw = it["data"][gi] or ""
            game = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", game_raw).strip()
            cat = (it["data"][ci] or "").strip() if ci is not None else ""
            players_raw = (it["data"][pi] or "") if pi is not None else ""
            players = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", players_raw)
            if not game or BREAK_RE.search(game): continue
            runs.append({
                "schedule": f.replace("horaro-", "").replace(".json", ""), "item_idx": item_idx,
                "game": game, "category": cat, "players": players,
                "length_s": it["length_t"], "scheduled": it["scheduled"],
            })
    return runs

# ---- load Oengus categories -------------------------------------------------
def load_oengus(f):
    cats = []
    for sub in json.load(open(OUT / f)):
        uname = (sub.get("user") or {}).get("username", "")
        for g in sub.get("games", []):
            for c in g.get("categories", []):
                est = iso_dur_seconds(c.get("estimate"))
                if est is None: continue
                cats.append({
                    "game": g.get("name", ""), "category": c.get("name", ""),
                    "runner": uname, "type": c.get("type", "SINGLE"),
                    "estimate_s": est, "console": g.get("console", ""),
                })
    return cats

def match_event(runs, cats):
    by_game = defaultdict(list)
    for c in cats: by_game[norm(c["game"])].append(c)
    matched, unmatched = [], []
    for r in runs:
        ng, nc = norm(r["game"]), norm(r["category"])
        pool = by_game.get(ng)
        how = "exact-game"
        if not pool:
            best, score = None, 0.0
            for g, cl in by_game.items():
                s = jacc(r["game"], g)
                if s > score: best, score = cl, s
            if score >= 0.6: pool, how = best, f"fuzzy-game({score:.2f})"
        if not pool:
            unmatched.append(r); continue
        # rank by category similarity, then runner presence in players
        def cat_score(c):
            s = 1.0 if norm(c["category"]) == nc else jacc(c["category"], r["category"])
            if norm(c["runner"]) and norm(c["runner"]) in norm(r["players"]): s += 0.5
            return s
        best = max(pool, key=cat_score)
        s = cat_score(best)
        if s < 0.3:
            unmatched.append(r); continue
        matched.append({**r, "est_s": best["estimate_s"], "sub_cat": best["category"],
                        "runner": best["runner"], "run_type": best["type"], "how": how, "score": round(s, 2)})
    return matched, unmatched

def fmt(sec):
    sign = "-" if sec < 0 else ""
    sec = abs(int(sec))
    return f"{sign}{sec//3600}:{(sec%3600)//60:02d}:{sec%60:02d}"

all_rows = []
for ev, (hf, of) in EVENTS.items():
    runs, cats = load_horaro(hf), load_oengus(of)
    matched, unmatched = match_event(runs, cats)
    for m in matched: m["event"] = ev; all_rows.append(m)
    deltas = [m["length_s"] - m["est_s"] for m in matched]
    exact = sum(1 for d in deltas if d == 0)
    over = sum(1 for d in deltas if d > 0)
    under = sum(1 for d in deltas if d < 0)
    print(f"\n=== {ev} ===")
    print(f"schedule rows (runs): {len(runs)} · oengus categories: {len(cats)}")
    print(f"matched: {len(matched)} ({100*len(matched)/max(1,len(runs)):.0f}%) · unmatched: {len(unmatched)}")
    print(f"UNCHANGED length==estimate: {exact} ({100*exact/max(1,len(matched)):.0f}%)  ← amendment-rate caveat")
    print(f"ran LONG: {over} · ran SHORT: {under}")
    changed = [d for d in deltas if d != 0]
    if changed:
        print(f"among AMENDED rows: median {fmt(statistics.median(changed))} · mean {fmt(statistics.mean(changed))}")
    ratios = [m["length_s"] / m["est_s"] for m in matched if m["est_s"] > 0 and m["length_s"] != m["est_s"]]
    if ratios:
        print(f"amended length/estimate ratio: median {statistics.median(ratios):.3f} · p90 {sorted(ratios)[int(len(ratios)*0.9)]:.3f}")
    if unmatched[:5]:
        print("sample unmatched:", [f"{u['game'][:28]} | {u['category'][:20]}" for u in unmatched[:5]])

with open(OUT / "matched.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["event","schedule","item_idx","game","category","sub_cat","runner","players","run_type","est_s","length_s","scheduled","how","score"])
    w.writeheader()
    for m in all_rows: w.writerow({k: m.get(k) for k in w.fieldnames})
print(f"\nwrote matched.csv ({len(all_rows)} rows)")
