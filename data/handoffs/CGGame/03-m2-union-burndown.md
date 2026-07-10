# M2 — chain interpreter + 50-union burn-down 🔶 ACTIVE — resume here

**Status:** in progress 2026-07-10 (commit `a509725`). The interpreter is LIVE and proven
(Ultra Ball / Poffin / Mega Signal cascades replay green inside real games); ~10 union
trainers authored; the 5 agent-deck traces are the burn-down queue. **Goal:** mirror + cross
matches of `mega_starmie` / `mega_lucario` / `dragapult_ex` replay clean; then curate those
traces into `tests/fixtures/parity/` so the CI gate owns the union.

## The loop (this IS the job)

```bash
python tools/parity/replay_diff.py data/parity/ms_mirror_*.trace.json.gz data/parity/ml_dx_*.trace.json.gz
# → first divergence names a card/op → author it → re-run. One divergence at a time.
```

- **A missing trainer PLAY option** (`native: {type:7,index:i}` absent from cgpy) → look up
  hand index i in the frame's god hand (`Trace.load(...).frames[k]["god"]["players"][mover]["hand"]`),
  read that card's text in `src/cgpy/defs/card_data.json`, author its ChainDef in
  `src/cgpy/defs/chain_overrides.json` (schema per existing entries: `legal` conditions +
  `play` ops).
- **A missing op** → add an executor to `src/cgpy/chain.py` `OPS` (two-phase pattern: pose a
  select when `"answer" not in fr.vars`, act on the answer otherwise; keep frames plain-data).
  Name it after the native verb (`dsl_vocabulary.json`) when the mapping is direct, `x`-prefix
  composites.
- **An extra cgpy option** → a legality condition is missing/wrong (the engine peeks real
  state; e.g. coin-gated effects like Crushing Hammer are offered even with NO opp energy).
- **A state/log mismatch** → a mutation-order or visibility rule; fix at the emit site.

## The live queue (divergences as of handoff — regenerate if data/parity was cleaned)

| Trace | Frame | Diff | Reading |
|---|---|---|---|
| ms_mirror_1000 | f7 | native PLAY vs cgpy ATTACH at option[0] | next un-def'd trainer in that hand (check god hand f7) |
| ms_mirror_1001 | f6 | native ATTACH vs cgpy PLAY at option[0] | cgpy offers a trainer the native does NOT (legality too loose) — likely one of the just-authored defs; check which card + why native omits it |
| ms_mirror_1002 | f4 | native ATTACH vs cgpy PLAY at option[2] | same class as 1001 |
| ml_dx_2000 | f4 | option[0].index 0 vs 1 | ordering/legality shift in the lucario/dragapult hands — un-def'd trainer or over-offered def |
| ml_dx_2001 | f7 | native discard EMPTY vs cgpy has Ultra Ball | **trainer discard TIMING: Ultra Ball is NOT in the discard during its cost select.** The current "discard immediately on play" rule (turn.py PLAY-trainer branch) is Poffin-derived and WRONG for Ultra Ball — likely: the card goes to discard on RESOLUTION (or after costs). Re-pin with both samples; check where Poffin actually sat during its ToBench select (the earlier reading may have misattributed). |

## Remaining union cards to author (union = 50; texts in `defs/card_data.json`)

- **Trainers/Stadiums/Tools (26 total; done: 1121 Ultra Ball, 1086 Poffin, 1123 Switch,
  1120 Crushing Hammer, 1097 Night Stretcher, 1213 Judge, 1227 Lillie's, 1182 Boss's Orders,
  1145 Mega Signal):** 1080 Unfair Stamp (KO'd-last-turn gate + both-shuffle-draw asym),
  1122 Pokégear 3.0 (LOOK top-7 machinery: deck→LOOKING moves, filtered reveal, rest back +
  shuffle), 1141 Premium Power Pro (this-turn damage marker), 1142 Fighting Gong (search
  basic-{F} energy OR pokemon, reveal, to hand), 1152 Poké Pad (search no-Rule-Box pokemon),
  1159 Hero's Cape (TOOL attach flow + maxHp +100), 1174 Air Balloon (TOOL, retreat −2),
  1189 Salvatore (search evolution-of-own-in-play, no-ability filter), 1198 Crispin (search 2
  distinct basic energies, attach one + hand one), 1211 Black Belt's Training (this-turn +40
  vs ex marker), 1219 Petrel (search Trainer to hand), 1223 Harlequin (both shuffle + coin +
  conditional), 1225 Hilda (search evolution + energy), 1229 Wally's Compassion (heal-all on a
  Mega + energy bounce rider), 1240 Rosa's Encouragement (prize-count gate; draw), 1252
  Gravity Mountain (STADIUM: Stage-2 HP −30 both sides + stadium replace flow), 1260 Risky
  Ruins (STADIUM: trigger on non-{D} basic benching).
- **Effect-Pokémon (15):** abilities need the ABILITY option path (options.py has none yet —
  once-per-turn tracking + `abilityPlay`/activated split): 66 Dudunsparce, 112 Munkidori,
  120 Drakloak, 140 Fezandipiti ex, 666 Cinderace (Explosiveness handled; Turbo Flare attack
  = search 3 basic energies → attach), 673/674 Hariyama line (Wild Press recoil), 675
  Lunatone, 676 Solrock (Cosmic Beam requiresBench), 1071 Meowth ex (Tuck Tail self-return).
  Attack riders route through `damage.py`'s M2 seams + attack programs (`kind:"attack"`):
  121 Dragapult ex Phantom Dive (benchSpread 6 counters via `remainDamageCounter`), 235 Budew
  Itchy Pollen (ITEM-LOCK: next-turn marker gating opp PLAY options!), 305 Dunsparce
  Trading Places (self-switch), 678 Mega Lucario ex Aura Jab (attach ≤3 {F} from discard) /
  Mega Brave (same-attack lock marker), 1031 Mega Starmie ex Jetting Blow (bench snipe —
  DAMAGE select ctx 15) / Nebula Beam (ignore W/R), 140 Cruel Arrow (100 to any 1), 677 Riolu
  Accelerating Stab (self lock marker), 17 Ignition Energy (SPECIAL ENERGY: discard-at-EOT
  trigger).
- Expect NEW machinery for: LOOKING zone flows, TOOL attach, STADIUM zone + replace, ability
  options + once-per-turn state, attack effect programs + coin attacks, this-turn/next-turn
  markers (the `Marker` field on `PokemonInPlay` is there, unused), bench-damage selects
  (ctx 13/14/15 with `remainDamageCounter`), item-lock gating of MAIN options.

## Method notes / traps (earned this session)

- **Trust live-obs traces over visualize decodes**; when two traces disagree with your rule,
  capture more games before theorizing — the Mulligan YesNo took 3 wrong models until
  vanilla traces isolated it (it's the Explosiveness keep-or-redraw choice, nothing else).
- Multi-select answers apply in GIVEN index order against the pre-removal zone (resolve all
  serials first, then remove) — already handled in `_setup_apply`/ops; keep the pattern.
- ex/megaEx KOs (2/3 prizes) have NEVER been exercised — the multi-prize pick shape
  (repeated single selects vs one multi-select) is UNPINNED; the first mirror trace with an
  ex KO pins it (`_pose_prize_pick` + `prizes_left` loop is the seam).
- Unexercised guesses to watch: Judge/Lillie's hand-return order + draw order (actor first?),
  search min-counts (Mega Signal min=0 guessed), the MULLIGAN "No" branch CHK log, promotion
  MOVE log shape (t6 BENCH→ACTIVE guessed), evolved-stack KO discard order, bench facedown
  rendering during setup windows, deck-search whiff legality (offered when zero matches?).
- When the union goes green: `capture_match.py` all three mirrors + three crosses with fresh
  seeds, replay clean, then copy those traces to `tests/fixtures/parity/` (that lands the
  M2 gate) and re-assert the ADR-0032 goldens on cgpy (Nebula Beam 1488=210 through Crustle,
  Jetting Blow 1487=0 active +50 bench, Resistance −30, Weakness ×2).

## Files you'll touch

`src/cgpy/defs/chain_overrides.json` (defs) · `src/cgpy/chain.py` (ops + legality) ·
`src/cgpy/options.py` (ABILITY options, item-lock gating, TOOL/STADIUM play) ·
`src/cgpy/turn.py` (play-flow branches, markers, checkup conditions when they arrive) ·
`src/cgpy/damage.py` (rider/ignore seams) · `src/cgpy/state.py` (Marker usage).
