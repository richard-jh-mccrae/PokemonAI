# CGGame Parity Burn-Down — Session Handoff (ADR-0050)

**Purpose:** resume the `src/cgpy` parity burn-down (drive the kaggle-episode ladder from
**227/434 green → 434/434**). This doc is self-contained: it has the resume protocol, the
per-card method, the strategic ordering, the **fan-out procedure**, every reusable script,
and the hard-won gotchas. Read it top to bottom once, then use §9 as your toolbox.

Primary memory: `~/.claude/.../memory/cgpy-standalone-engine.md` (same facts, terser).
Pins ledger: `docs/pyeng/determinism.md` (§1–10+). CI: `docs/ci.md` + `.github/filters.yml`.

---

## 0. What cgpy is, in one paragraph

`src/cgpy/` is a pure-Python twin of the native `src/cg` engine (the DLL), built to **exact
parity**. It never imports `cg`. The proof it's faithful = the **parity gate**: committed
native traces replay through cgpy with zero divergence (`tests/parity/`, ~1177 tests, DLL-free
because the trace *is* the native side). The burn-down target is the **kaggle-episode ladder**:
434 real meta-deck games (`data/replays/*/episode-*.json.gz`) convert god-free and replay
through cgpy; each one that replays with zero divergence is "green". We are at **227/434**.

**The method (never deviate):** capture native behavior → replay through cgpy → the differ
reports the FIRST divergence with a JSON path → implement exactly that → repeat. Divergences
are the specification. Never model from card text alone — the competition sim overrides the
official rules and the mainline TCG (see CLAUDE.md). Text tells you *what* to look for; the
divergence tells you the *exact* shape. When a rule seems ambiguous, capture more traces.

---

## 1. Cold-start / resume protocol

```bash
# 1. Fresh branch off the UPDATED main (the ADR-0050 branch is already merged).
cd <the main checkout, e.g. C:/Users/Richard/Projects/PokemonAI>
git checkout main && git pull
git checkout -b claude/cgpy-parity-<topic>
# (or use a worktree; note episodes live only in the MAIN checkout — see §2)

# 2. Sanity: the gate is green (~1177 passed, DLL-free, ~6-9 min).
python -m pytest tests/parity -q

# 3. Recreate the ladder + diagnostic scripts in your scratchpad (copy from §9).

# 4. Run the ladder to get the current queue (the ranked to-do list).
python <scratch>/ladder.py            # writes attr.jsonl + prints the tally
```

**Ground rules that always hold:** never touch `src/cg/`; cgpy never imports `cg`; every
native-behavior claim comes from a probe or a trace divergence, never from memory/training;
all option building/ordering lives in `src/cgpy/options.py`; a def-less card exercised at
runtime must raise `UnsupportedCard`, never guess. Windows + Linux both first-class (pathlib,
`encoding="utf-8"`, no OS assumptions).

---

## 2. Where everything lives

| Thing | Path |
|---|---|
| The twin | `src/cgpy/` — `options.py` (option gen + payability), `chain.py` (the effect interpreter + `OPS` registry + `_card_matches` filters + `check_legal`), `damage.py` (damage pipeline + `scale_count` + `apply_defender_mods`), `turn.py` (turn flow, attack apply, `_checkup`, evolve), `render.py`, `state.py`, `defs/` (the JSON defs) |
| Defs | `src/cgpy/defs/chain_overrides.json` (hand-authored, wins) + `generated_chains.json` (seeded stubs incl. `deferred`). `def_for()` merges override-over-generated. |
| The replayer | `src/cgpy/verify/replayer.py` — the god-free reveal-oracle binding (draws/coins/prizes/listings). **This is where the deck-reconstruction infra work lives (Phase 1).** |
| The differ | `src/cgpy/verify/differ.py` — `first_divergence(theirs, ours)` returns `Divergence(path, native, ours)`. |
| Episodes (the ladder corpus) | `data/replays/*/episode-*-replay.json.gz` — **434 games, GITIGNORED, only in the MAIN checkout.** A worktree does NOT have them; point scripts at the main checkout's `data/replays`. |
| Native capture / onboard tools | `tools/parity/` — `capture_card.py <id>` (drive native to exercise a card → micro-trace), `from_cabt.py` (episode → god-free trace via `convert()`), `onboard_card.py`, `report.py` (rebuild `data/engine/coverage.json` op-coverage ledger), `replay_diff.py`. |
| Gate + fixtures | `tests/parity/` (test_cabt_replays.py = the episode fixtures; test_op_conformance.py = every OP needs a committed pin; test_replay_fixtures.py = the micro-trace corpus in `tests/fixtures/parity/`). Fixtures: `tests/fixtures/parity/*.trace.json.gz` (god micro-traces) + `tests/fixtures/episode-*.json.gz` (cabt episodes) + `tests/fixtures/match-replay.json`. |
| Enums | `src/cgpy/schema.py` — `LogType`, `CardType`, `EnergyType`, `SelectContext`, `AreaType`, `OptionType`, `SelectType`. |
| Card data | `data/EN_Card_Data.csv` (human) + `src/cgpy/defs/card_data.json` (snapshot). |
| Pins | `docs/pyeng/determinism.md`. CI: `docs/ci.md`, `.github/filters.yml` (the `parity` filter), `.github/workflows/ci.yml`. |

---

## 3. The per-card recipe (the core loop)

For each queue item (a card id / attack id that is the first divergence of ≥1 episode):

1. **Identify** — `ladder.py` tags each episode's first divergence (e.g. `MISS play 1197 Xerosic`,
   `MISS attack 1042 Riptide`, `UnsupportedCard('attack 1046 ...')`, `nonselect:current`).
2. **Read the card text** at source: `data/EN_Card_Data.csv` (grep the id). This tells you what
   to look for — NOT the exact mechanic.
3. **Pin the native shape** — find an episode that exercises the card and dump native's frames
   around it (`dumpf.py`, `diff_opts.py`, `scan_reactive.py` in §9). Get the exact: select
   context, min/max count, option encoding, log order, damage value, timing.
4. **Model it** — add/extend a def in `chain_overrides.json` and, if needed, an op in `chain.py`
   (register in `OPS`) or a branch in `damage.py`/`turn.py`/`options.py`. **Reuse existing ops
   first** (see §9 catalogue).
5. **Verify on the real episodes** — run `diff_opts.py <ep>` on episodes that use the card. Aim
   for CLEAN; if it advances-but-diverges-elsewhere, that's a *different* blocker (fine).
6. **Measure + regression-check** — `ladder.py --diff <baseline.jsonl>` prints net CLEAN change
   AND any REGRESSED episode. **A regression is a hard stop — diagnose before committing.** (This
   caught the Xerosic over-offer that index-shifted a clean episode — see §10.)
7. **Fixture** — add a clean episode that exercises the card to `test_cabt_replays.py` (+ its
   frame count). If you added a new OP, it needs a conformance pin (§10 "op conformance").
8. **Gate + commit** — `python -m pytest tests/parity -q` (green), then one commit per card/batch
   with the `ladder A -> B/434` in the subject.

**Commit discipline:** terse imperative subject `cgpy <Card>: <what>; ladder A -> B/434`; body
explains the pin (episode + frame) + any gotcha; end with the Co-Authored-By trailer. One batch
= one commit + one gate run (the applier-drain-conveyor shape). Always run the `--diff` before
committing.

---

## 4. Remaining work (227/434) — buckets + the strategic order

From the last full ladder run (`attr_nz.jsonl`-equivalent). Numbers = episodes whose FIRST
divergence falls in the bucket; many also have deeper blockers.

| # eps | Bucket | Effort | Verifiable now? |
|---|---|---|---|
| ~63 | **A. Deck-reconstruction infra** (deck-drift, 1046 mill, Poffin discard, deckCount, draw-underrun) | HARD (one shared root) | it IS the blocker |
| 44 | **C. Per-card asks** (ctx43/ctx0 "you may" riders) | medium each, diffuse | often no (block earlier) |
| 43 | **B. Deferred cards** (play/attach/ability) | low–medium, reuse | mixed |
| 25 | **D. Stadium passives** | medium, verification-hard | usually no |
| 14 | **E. Rabbit-holes** (Mega Brave megaEx timing, 1267) | hard | no |
| ~18 | other/unclassified | — | — |

### The load-bearing insight

**The god-free deck-reconstruction infra (bucket A) is the keystone.** It is not just ~63
episodes — it is the wall that stops *most of the rest from being verifiable*. All last session:
"the card's fix is correct but the episode diverges earlier on deck-drift, so I can't confirm it
clean" (1046, 1267, Ogerpon downstream, half the ctx asks). Fix the infra once → those ~63 clear
AND every other episode replays *past* the wall, so the per-card tail becomes independently
verifiable and a chunk cascades green for free. **Do NOT grind per-card behind this wall** — that
is the inefficient path (the +0/+1 outcomes of last session were episodes stacking blockers).

### The efficient sequence

1. **Phase 1 — build the deck-reconstruction infra** (§5). The keystone. Done once.
2. **Phase 2 — re-run `ladder.py`**, re-rank. A chunk cascades clean; the tail is now verifiable.
3. **Phase 3 — the parallel fan-out sweep** (§7) over the re-ranked B/C/D tail. Embarrassingly
   parallel; this is the multi-agent-workflow phase.
4. **Phase 4 — the hard tail** (§8): Mega Brave megaEx/re-evolve timing, Jamming Tower retro-toggle,
   accumulated-damage residuals. Sequential, careful.

---

## 5. Phase 1 — the deck-reconstruction infra (the keystone)

**Symptom:** cgpy's god-free reconstructed hidden zones (deck order + which cards are in prizes
vs deck) drift from native's true zones. First observed as the **Buddy-Buddy Poffin (card 1086)
discard class**: cgpy kept duplicate ≤70-HP Basics in the deck that native had dealt to the
prize row, so cgpy poses a bench search native (whiffing) skips. The search is just the first
REVEAL that exposes an *earlier* prize-deal drift. Also surfaces as `deckCount` off-by-N and, via
`1046 Hammer-lanche` (mill top 6 → discard), as `discard[].id` mismatches (cgpy mills the wrong
cards because its deck-top ≠ native's).

**Why it happens:** facedown prize deals never log serials. The replayer binds deck-top / prize
identities *provisionally* and reconciles them lazily from later reveals (draw serials, revealed
deck listings, `DECK->LOOKING` look-at-top-N moves — the four "reveal-oracle channels" in
`replayer.py`). When a card's identity is ambiguous between deck and prizes and never gets a
disambiguating reveal before it matters (a search filter, a mill, a deckCount render), cgpy's
guess drifts.

**The spike (do this FIRST, before committing to a design):**
1. Characterize the drift across ALL bucket-A episodes. Extend `ladder.py` to, for each
   deck-drift episode, dump: the divergence path, the drifting serial(s), and the frame where
   the provisional bind was made vs where it diverged. Ask: is it ONE root (the prize-deal
   duplicate-Basics drift) or several?
2. The likely fix: **stronger hidden-zone identity tracking in `verify/replayer.py`** — track the
   set of *possible* identities for each facedown slot and narrow it monotonically as reveals
   arrive, rather than committing a provisional identity early. Where a search/mill/render needs
   an identity that's still ambiguous, defer/reconcile against native's observed outcome (the
   episode's own later frames are ground truth).
3. This is real design work. Timebox the spike; write the finding into determinism.md before
   implementing. It unblocks the most and enables Phase 3 — worth the investment.

Known non-issues to not chase: Crustle 533 "Sturdy" (survive-at-10) is NOT in the corpus (0 eps);
`nonselect:current` is heterogeneous — ~12 are this infra, the rest are accumulated small damage
diffs (handle case-by-case in Phase 4, not as one root).

---

## 6. Phase 2 — re-rank

After Phase 1 lands: `python -m pytest tests/parity -q` (green), then `ladder.py` fresh. Save the
new `attr.jsonl` as the Phase-3 baseline. Re-bucket. Expect the counts to shift materially and
many "blocked earlier" cards to become first-divergence (and verifiable).

---

## 7. Phase 3 — the parallel fan-out sweep (THE fan-out procedure)

The re-ranked B/C/D tail is **independent per card** and each follows the identical §3 recipe.
This is the ideal multi-agent workflow. **Multi-agent workflows require explicit user opt-in**
(the keyword "ultracode", "use a workflow", or a direct ask) — do NOT auto-launch one. If opted
in, structure it like this; if not, do the same recipe serially, one card per commit.

### 7a. Scope the work-list first (inline, before fanning out)

Run `ladder.py`, take the top-N first-divergence card ids that are NOT bucket-A/E (those are
Phases 1/4). For each, pre-attach: the card text (grep EN_Card_Data.csv) and 1–3 episodes that
exercise it (from the attr.jsonl). This is the fan-out input — you must know the work-list shape
before the orchestration step, so discover it inline.

### 7b. The workflow shape

Pipeline, one item per card/cluster, each stage below. Use `pipeline()` (no barrier) so a fast
card commits while a slow one is still modeling. ~8–12 concurrent is the cap anyway.

```
export const meta = { name: 'cgpy-parity-sweep', description: '...', phases: [
  { title: 'Pin' }, { title: 'Model' }, { title: 'Verify' } ] }

// args = [{cardId, kind, text, episodes:[...]}, ...]  (the pre-scoped work-list)
const results = await pipeline(args,
  // Stage Pin: dump native frames around the card in one episode → the exact shape.
  card => agent(`Pin the native select/damage/log shape of ${card.kind} ${card.cardId}
    "${card.text}" in episode ${card.episodes[0]}. Use dumpf.py/diff_opts.py. Return the
    exact {context, min, max, option-encoding, log-order, damage} as JSON.`,
    { phase:'Pin', schema: SHAPE }),
  // Stage Model+Verify: author the def/op, verify on the card's episodes, report diff.
  (shape, card) => agent(`Model ${card.cardId} from this pinned shape ${JSON.stringify(shape)}.
    Add a def to chain_overrides.json (reuse an existing OP if one fits — see the catalogue).
    Verify with diff_opts.py on ${card.episodes.join(',')}. Report: files changed, whether the
    card's episodes go clean/advance, and any new op added.`,
    { phase:'Model', schema: RESULT, isolation:'worktree' }))   // worktree: parallel file edits
```

**Critical fan-out constraints (bake into the prompts):**
- Each agent works in an **isolated git worktree** (`isolation:'worktree'`) because they all edit
  `chain_overrides.json` and would conflict otherwise. The orchestrator MERGES their def additions
  afterward (they're independent JSON keys — union them).
- Agents only ADD a def key (and maybe one OP); they do NOT run the full gate or the ladder (too
  slow ×N, and the ladder needs the whole merged state). They return their DEF + any new OP + the
  per-episode diff_opts result.
- **The orchestrator does the end-join, serially:** union all def keys into `chain_overrides.json`,
  add all new OPS, then run ONE `ladder.py --diff <phase2-baseline>` (regression check across the
  merged set — an agent's fix can regress another's episode) + ONE `pytest tests/parity -q`. Add
  fixtures for the cleanly-verified cards. Commit in batches.
- Give each agent the §9 script contents + the §10 gotchas in its prompt (menu-gate lesson,
  op-conformance, board-visible-scale rule). They will re-derive them otherwise.

### 7c. What NOT to fan out

Bucket A (Phase 1, shared infra — one focused effort), bucket E (rabbit-holes — need deep
sequential attention), and anything needing a new cross-cutting op/hook (do those inline so the
whole codebase sees them). Fan out only the "def + maybe-reuse-op" cards.

---

## 8. Phase 4 — the hard tail

- **Mega Brave 983** (megaEx self-lock): the sim does NOT enforce `selfLockNextTurn` for a Mega
  Pokémon ex (Mega Lucario uses Mega Brave 3× consecutive, ep-83238610 f96/f103/f104) but DOES
  for Riolu's Accelerating Stab 981 (f35). A naive `not megaEx` gate made it WORSE (56 vs 104
  green) — the lock also interacts with re-evolution / exact turn timing. Needs proper turn-timing
  + re-evolve-reset analysis. Deferred; do not gate naively.
- **Jamming Tower 1246** (tools-inert stadium): must retro-toggle the mutate-model hpBonus →
  HP-recompute + KO pass when it enters/leaves. Hard.
- **Area Zero Underdepths 1250**: Tera → dynamic bench_max 8 (and discard-to-5 when no Tera).
- **Stadium passives generally** (bucket D): un-defering a stadium needs its passive too (affects
  later frames), and the passive is usually UNVERIFIABLE from the corpus (episodes block earlier),
  so they gain +0 with an unverified passive. Neutralization Zone 1247 was fully modeled + reverted
  for exactly this reason. Only ship a stadium passive if a clean episode exercises it.
- **1267 Horrifying Revenge / 363 Voltaic Chain**: scaling attacks; 1267 unverifiable (all Hop's
  episodes block earlier). 363 = family-energy scale var (`{L} on all Iono's mons`), verifiable if
  an episode reaches it. Retry these after Phase 1 (episodes may replay further).
- **Accumulated-damage `nonselect:current` residuals**: case-by-case; usually a small defender-side
  reduction cgpy misses (the FML-pierce / defender-mod family in `apply_defender_mods`).

---

## 9. Toolbox — reusable scripts (recreate in scratchpad)

Set `MAIN` = the main checkout (episodes live there, gitignored). `REPO` = your worktree root.

### 9a. `ladder.py` — the ladder + attribution + regression diff

```python
"""Replay every kaggle episode through cgpy; attribute each first divergence to a card.
Usage:
  python ladder.py                      # run, write attr.jsonl, print tally
  python ladder.py --diff BASE.jsonl    # also print net-CLEAN + REGRESSED vs a baseline
"""
import json, sys, re, argparse
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[?]     # set to your worktree root
MAIN = Path(r"C:\Users\Richard\Projects\PokemonAI")   # episodes live here (gitignored)
sys.path.insert(0, str(REPO / "src")); sys.path.insert(0, str(REPO / "tools" / "parity"))
from from_cabt import convert
import cgpy.verify.replayer as rp

cd = {c["cardId"]: c["name"] for c in json.load(open(REPO/"src/cgpy/defs/card_data.json", encoding="utf-8"))}
ad = {a["attackId"]: a.get("name","?") for a in json.load(open(REPO/"src/cgpy/defs/attack_data.json", encoding="utf-8"))}
orig = rp.first_divergence; _cap = {}
def spy(t, o):
    d = orig(t, o)
    if d is not None and "cap" not in _cap: _cap["cap"] = (t, o, d)
    return d
rp.first_divergence = spy

def slot_id(players, seat, area, index):
    b = (players or [{},{}])[seat] or {}
    if area == 4:
        act = b.get("active"); act = next((a for a in act if a), None) if isinstance(act, list) else act
        return (act or {}).get("id")
    bench = b.get("bench") or []
    return bench[index].get("id") if index is not None and index < len(bench) and bench[index] else None

def attribute(theirs, ours, d):
    cur = theirs.get("current") or {}; seat = cur.get("yourIndex", 0); players = cur.get("players")
    hand = ((players or [{},{}])[seat] or {}).get("hand") or []
    ts = theirs.get("select") or {}; os_ = ours.get("select") or {}
    if not d.path.startswith("$.select"): return [f"nonselect:{d.path.split('.')[1][:18]}"]
    if ts.get("context") != 0 or os_.get("context") != 0:
        eff = (ts.get("effect") or {}).get("id"); return [f"ctx{ts.get('context')}:eff={eff}:{cd.get(eff,'')[:24]}"]
    key = lambda o: json.dumps(o, sort_keys=True)
    t_set = Counter(map(key, ts.get("option") or [])); o_set = Counter(map(key, os_.get("option") or []))
    tags = []
    for grp, sign in ((t_set - o_set, "MISS"), (o_set - t_set, "OVER")):
        for k, _n in grp.items():
            o = json.loads(k); t = o.get("type"); i = o.get("index")
            if t == 10:
                cid = slot_id(players, seat, o.get("area"), i)
                tags.append(f"{sign} ability {cid} {cd.get(cid,'')[:24]}" if o.get("area") != 7 else f"{sign} stadium-ability")
            elif t in (7, 8):
                cid = hand[i].get("id") if i is not None and i < len(hand) else None
                tags.append(f"{sign} {'play' if t==7 else 'attach'} {cid} {cd.get(cid,'')[:24]}")
            elif t == 13: tags.append(f"{sign} attack {o.get('attackId')} {ad.get(o.get('attackId'),'')[:24]}")
            else: tags.append(f"{sign} type{t}")
    return tags or [f"select-other:{d.path[8:40]}"]

ap = argparse.ArgumentParser(); ap.add_argument("--diff"); ap.add_argument("--out", default="attr.jsonl")
args = ap.parse_args()
eps = sorted(MAIN.glob("data/replays/*/episode-*-replay.json"))
tally = Counter(); per_ep = []
for i, p in enumerate(eps):
    _cap.clear()
    try:
        rep = rp.replay(convert(json.loads(p.read_text(encoding="utf-8"))))
    except Exception as e:
        tally[f"convert-error {repr(e)[:50]}"] += 1; per_ep.append({"ep": p.name, "tag": "convert-error"}); continue
    if rep.clean: tally["CLEAN"] += 1; per_ep.append({"ep": p.name, "tag": "CLEAN"}); continue
    if rep.error:
        tag = rep.error[rep.error.find("UnsupportedCard"):][:70] if "UnsupportedCard" in rep.error else "error "+rep.error.split(":")[-1][:60]
        tally[tag] += 1; per_ep.append({"ep": p.name, "tag": tag, "green": rep.frames_green}); continue
    tags = attribute(*_cap["cap"]) if "cap" in _cap else ["?"]
    for t in tags: tally[t] += 1
    per_ep.append({"ep": p.name, "tag": ";".join(tags), "green": rep.frames_green, "total": rep.frames_total})
    if (i+1) % 100 == 0: print(f"  {i+1}/{len(eps)}", flush=True)

Path(args.out).write_text("\n".join(json.dumps(r) for r in per_ep), encoding="utf-8")
print(f"\n=== tally ({len(eps)} eps) ===")
for t, n in tally.most_common(40):
    if t != "CLEAN" or True: print(f"{n:4d}  {t}")
if args.diff:
    base = set(json.loads(l)["ep"] for l in open(args.diff, encoding="utf-8") if json.loads(l).get("tag") == "CLEAN")
    now = set(r["ep"] for r in per_ep if r.get("tag") == "CLEAN")
    print(f"\nbaseline {len(base)}  now {len(now)}  net {len(now)-len(base)}")
    print("GAINED:", sorted(x[8:22] for x in now - base))
    print("REGRESSED:", sorted(x[8:22] for x in base - now) or "NONE")
```

### 9b. `diff_opts.py <ep>` — replay one episode, show the divergence + native options

```python
import json, sys, re
from pathlib import Path
REPO = Path(__file__).resolve().parents[?]; MAIN = Path(r"C:\Users\Richard\Projects\PokemonAI")
sys.path.insert(0, str(REPO/"src")); sys.path.insert(0, str(REPO/"tools/parity"))
from from_cabt import convert
import cgpy.verify.replayer as rp
cd = {c["cardId"]: c["name"] for c in json.load(open(REPO/"src/cgpy/defs/card_data.json", encoding="utf-8"))}
p = next(MAIN.glob(f"data/replays/*/{sys.argv[1]}"))
rep = rp.replay(convert(json.loads(p.read_text(encoding="utf-8"))))
print(rep)
d = rep.divergence
if d:
    fr = None  # (dig into rep.frame's obs.select.option like the ladder's attribute() to print
               #  native option encodings + resolved card names for the diverging frame)
```

### 9c. `dumpf.py <ep> <lo> <hi>` — dump native frames with real LogType names

```python
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[?]; MAIN = Path(r"C:\Users\Richard\Projects\PokemonAI")
sys.path.insert(0, str(REPO/"src")); sys.path.insert(0, str(REPO/"tools/parity"))
from from_cabt import convert
from cgpy.schema import LogType
LT = {m.value: m.name for m in LogType}
cd = {c["cardId"]: c["name"] for c in json.load(open(REPO/"src/cgpy/defs/card_data.json", encoding="utf-8"))}
tr = convert(json.loads(next(MAIN.glob(f"data/replays/*/{sys.argv[1]}")).read_text(encoding="utf-8")))
for k in range(int(sys.argv[2]), min(int(sys.argv[3]), len(tr.frames))):
    fr = tr.frames[k]; cur = fr["obs"]["current"]; sel = fr["obs"].get("select") or {}
    print(f"\n--- f{k} mover={cur['yourIndex']} ctx={sel.get('context')} "
          f"min={sel.get('minCount')} max={sel.get('maxCount')} nopt={len(sel.get('option') or [])} choice={fr.get('choice')}")
    for l in fr["obs"].get("logs") or []:
        e = {kk: vv for kk, vv in l.items() if kk != "type"}
        print(f"    {LT.get(l.get('type'), l.get('type'))}: {json.dumps(e, ensure_ascii=False)[:140]} {cd.get(l.get('cardId'),'')[:16]}")
```

**Log types you'll use constantly** (from `schema.LogType`): 2 TURN_START, 3 TURN_END, 4 DRAW,
5 DRAW_REVERSE, 6 MOVE_CARD, 10 PLAY, 11 ATTACH, 12 EVOLVE, 15 ATTACK, 16 HP_CHANGE, 22 COIN.
Option types: 7 play, 8 attach, 10 ability, 12 (RETREAT-ish/type-12), 13 attack, 14 END.
SelectContext: 7 TO_HAND, 9 TO_DECK, 21 ATTACH_FROM, 22 ATTACH_TO, 30 DISCARD_ENERGY, 43 YES_NO ask.

### 9d. Capture-verify a new OP (for conformance)

```bash
python tools/parity/capture_card.py <cardId> -n 4 --seed 9000 --prefix foo   # → data/parity/foo_*.trace.json.gz
# then replay each through cgpy; if it FIRES your op and is clean, promote to tests/fixtures/parity/
# and rebuild the ledger: python tools/parity/report.py
```

---

## 10. Gotchas & pins (hard-won — read before modeling)

- **Menu-gates.** A "MISS play" supporter is usually menu-gated by native; offer it unconditionally
  and you OVER-offer → index-shift → you REGRESS a previously-clean episode. Gates seen: Xerosic's
  Machinations `oppHandAbove 3`; Sacred Ash / Lana's Aid / Energy Recycler `discardHas <filter>`;
  Rare Candy / Hand Trimmer legal pairs. **Always run `ladder.py --diff` — a regression is a stop.**
- **Board-visible-scale rule.** A deferred SCALING attack lands cleanly iff its scale source is a
  board-visible zone (bench/energy/discard counts) — Riptide scales on the *discard* → +6 clean.
  Deck-order-dependent scales (Hammer-lanche 1046 mills the deck top) hit the Phase-1 wall → 0.
- **Deferred SPECIAL ENERGY = cheap.** Often just needs the ATTACH OPTION un-deferred (a def to
  exist) — Prism Energy gave +11 on option-set parity alone, no effect modeling (it's deck-ubiquitous).
  `providesOnBasic/OnEvolution/OnStage2` handle conditional provide. Last deferred one: Team Rocket's
  Energy 15 (but absent from corpus).
- **Op conformance.** Every new `OPS` entry needs a committed pin. capture_card can't always fire a
  card (menu-gated at 0 resource → `fired=0`). A god-free cabt trace CANNOT go in `tests/fixtures/parity/`
  (breaks test_search_api's god-frame seeding). Escape: add the op to `UNPINNED` in
  test_op_conformance.py WITH a reason + a committed cabt fixture in test_cabt_replays.py.
- **+0 groundwork is OK to commit IF verified** — Freezing Shroud / Ogerpon Teal Dance gained +0 but
  un-defer real cards and replay clean THROUGH their effect; guarded by a partial-replay test
  (`assert frames_green > N`). Do NOT commit +0 UNVERIFIED code (Neutralization Zone was reverted).
- **Reactive tools fire mid-attack** (Lucky Helmet draw-2-when-damaged): after the HP_CHANGE, before
  the KO sweep, in the ATTACKER's window (`turn._react_damaged_active`). NOT a between-turns hook.
  (Spiky-Energy counter-punch IS between-turns — different.)
- **Froslass "Freezing Shroud"** was the real root of the handoff's mislabeled "Munkidori counter-count"
  class — verify the divergence, don't trust a prior guess.
- **Reuse ops:** `xDeckToHandBuckets` (per-category deck search, Dawn/Colress/Transceiver),
  `xPickDiscard` (discard→hand|deck +shuffle, Sacred Ash/Lana's/Recycler), `xOppHandTrimTo`,
  `xHandEnergyAttachChoose` (+`holderSelf`/`thenDraw` for Ogerpon), `effectDraw`, `condBonus`/`scale`
  in damage.py. Filters: `_card_matches` supports `nameFamily` (apostrophe-normalized), `noRuleBox`,
  `ex`, `basicEnergy`, `energyType`, `cardType`, `anyOf`.
- **CI:** the `parity` filter (`.github/filters.yml`) runs `tests/parity` ONLY when `src/cgpy/**`,
  `tests/parity/**`, `tests/fixtures/parity/**`, or `data/engine/coverage.json` change. A cgpy PR that
  also touches a top-level fixture/other data degrades to full suite (safe). Don't re-add an
  unconditional parity step.
- **Git:** rebase onto main before a PR; force-push with `--force-with-lease`. Episodes are gitignored
  (only in the main checkout) — point scripts at it.

---

## 11. Quick reference — commands

```bash
python -m pytest tests/parity -q                      # the gate (~1177 tests, ~6-9 min)
python -m pytest tests/parity/test_cabt_replays.py tests/parity/test_op_conformance.py -q  # fast subset
python <scratch>/ladder.py --diff <baseline.jsonl>    # ladder + regression check (~4 min)
python <scratch>/diff_opts.py episode-XXXX-replay.json   # one-episode divergence
python <scratch>/dumpf.py episode-XXXX-replay.json 40 55 # native frames 40-55
python tools/parity/report.py                         # rebuild coverage.json op ledger
```

**Current ladder: 227/434. Target: 434/434. Start with the Phase-1 infra spike (§5).**
