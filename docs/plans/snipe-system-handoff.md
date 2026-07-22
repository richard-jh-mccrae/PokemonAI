# The Snipe system — architecture, status & fold candidate (handoff, 2026-07-22)

**For a session working on snipe targeting.** Companion: `snipe-targeting-grill-scope-handoff.md`
(the corpus-sweep scoping) and `turn-planner-snipe-and-gust-scenarios.md` §A (the threshold-race
scenario). This doc is the *system* picture: what sniping is, where it lives, its build status, and
the standing ADR-0065 question — **it is a rung pile, not a folded oracle.**

## What "sniping" is here

Choosing WHICH opponent Pokémon to damage at a bench-target select. Two engine contexts:
- **`DAMAGE` (15)** — the bench-snipe rider (Jetting Blow's +50, etc.): pick one benched body.
- **`DAMAGE_COUNTER_ANY` (14)** — spread placement (Phantom Dive's 6 counters, Munkidori) — a
  distinct knapsack problem, handled by `place-counter-to-convert` + the two counter-mover rungs.

## Where it lives

- **`src/common/strategy/baseline/baseline_snipe.py`** — the Hypotheses (below). Pure data, no Mixin
  (ADR-0025).
- **Tactical layer (`pilot.py`)** — the KO_SCORE-class dominators that must beat any positional stack:
  `_snipe_ko_prizes` (a snipe that KOs = a prize) and `_snipe_tera_veto` (a **benched Tera** takes 0
  damage — a CARD FACT, `rules.md §185`, retired from being a tunable −60 weight to a structural veto
  after it lost on points: see Frame 0 / `82749168-38`).
- **Shared machinery it READS (the risk surface):** `board.strongest_threat_rank`,
  `target_is_top_threat` / `target_is_threat` (`_target_energy` / `_target_forward_damage`),
  `snipe_ko_available`, and the ADR-0044 prize guards `target_prize_redundant` /
  `target_promotion_mirage` / `evolving_wincon_on_bench`. **These are shared with other deciders — a
  blind poke risks the frames that already pass.**

## Rung inventory (6 target rungs + 3 counter rungs) — the staple

| id | wt | fires when | reads |
|---|---|---|---|
| `snipe-for-the-ko` | 60 | rider KOs the target (`target_kos`) | — (dominates; every positional rung stands down on any KO) |
| `snipe-the-evolving-threat` | 45 | pre-evo whose forward form is a wincon-class attacker, form NOT yet in play | `target_is_strongest_forward`, `target_forward_form_in_play` |
| `snipe-the-forced-promotion` | 40 | their Active is dead → pre-chip the READY wincon they must promote | `target_is_forced_promotion` |
| `snipe-the-top-threat` | 30 | no KO → biggest threat by rank | `strongest_threat_rank`, ADR-0044 guards |
| `snipe-the-threat` | 20 | energized bench body (imminence signal on top of top-threat) | `target_is_threat` |
| `snipe-on-the-path` | 12 | target on my cheapest prize route (ADR-0040) | `target_on_path` |
| `place-counter-to-convert` | 30 | `DAMAGE_COUNTER_ANY`/`_COUNTER` spread | `best_counter_slot` (knapsack) |
| `move-counters-off-the-damaged` | 30 | Munkidori source select | `best_counter_source_slot` |
| `move-max-counters` | 30 | Munkidori amount select | `is_max_counter_move` |

Scores **stack additively** — e.g. an energized forced-promotion top-threat on-path = `40+30+20+12`
plus the tactical KO term (observed `602 = Σrungs + tac 500`). Weights are hand-seeded / ladder-tuned,
statuses `testing`/`assumed`.

## Status (verified on `origin/main`, 2026-07-22)

- **Driving:** yes — these rungs decide the `Damage` select live.
- **Coverage:** the **no-KO role-ranking layer passes every corpus frame** (retested all 23 `Damage`
  disagreements — see the scope handoff). The KO case is dominated correctly. **16/18 replayable**
  (the "3 misses" was overcounted: `82749168-38` is refuted).
- **The one live gap:** the **threshold-race** (`83667237-107`) — a multi-turn race the single-turn
  rungs can't express (Makuhita scores 0; pilot takes an on-path body). Plus `81905522-75`, an
  unfixable transposition.

## The standing ADR-0065 question — FOLD CANDIDATE

The snipe read is the **last un-folded opponent-read rung pile** — 6 additive weighted rungs, the
exact analog of the old discard equation *before* the Needs successor replaced it. The clean
opponent reads (threat/doom via the combat oracle; deny via Needs assignment) are one-currency; snipe
is not. A folded **snipe marginal oracle** would price each target in ONE currency —
`prize_value(the target's line) × imminence(energy / turns-to-attacker) × path_membership −
redundancy(ADR-0044 guards)`, with the KO + Tera veto staying as tactical dominators — instead of
summing six positional bonuses. That fold is the ADR-0065 treatment sniping still needs; the
threshold-race term drops in naturally as an *imminence-over-my-window* factor rather than a 7th rung.

## Open work (ranked)

1. **Threshold-race** (the live gap) — grill frame-by-frame (`83667237-107` + the uncaptured
   `ep83037962-49`), then a `snipe_sweep` bench over the 23 DAMAGE frames (hold the role reads, fix the
   ruled). Do NOT blind-poke the shared threat-rank / prize-guard machinery. Details: scope handoff +
   scenarios §A.
2. **Fold the 6 rungs into a marginal oracle** (ADR-0065) — the Needs-for-snipe pass. Bench = the same
   `snipe_sweep`; acceptance = byte-identical on the 16 role reads, plus the threshold-race fix.
