# Gusting Round 0 — the measurement pass (results)

**Status.** MEASURED 2026-07-19, per `gusting-grill-spec.md` §Round 0. All 29 gust-adjacent
corrections replayed through the real `Pilot.explain()` with a FRESH pilot per replay
(`train.tuner.retest.retest`, built via `tune._build_pilot` — the statefulness lesson honored).
Grep reproduced exactly 29 unique keys: the spec's 25 plus `82867148-48`, `86089120-14`,
`86091435-119`, `86091435-13`. Raw per-option traces (scores, fired rules, reorder flags) were
inspected for every failing key; board gust-signals (`gust_best_ko_prizes`, famine gates) were
probed directly for the surviving failures.

**Headline: the cluster dissolved.** 29 corrections → **3 genuinely-open gust failures**, one per
leg, each a SMALL targeted fix. The corrections do NOT motivate the full five-shadow
opponent-keep-cost collapse the seed doc imagines — the anti-speculation hazard fired, as the spec
itself predicted ("the right outcome may be a much SMALLER build").

## Method notes (read before trusting any `fixed=False`)

- `retest()` is a single-frame probe: `chosen_after` is the FIRST action of a whole-turn sequence.
  `_finish_turn_last` (pilot.py:1182) resequences a Main menu (free digs → Supporter → attach →
  shuffle → attack), so `chosen_after ≠ correct` where the correct option is merely later in the
  tier order is an ARTIFACT, not a failure. Every failing key below was disambiguated by card
  identity (Supporter?), tier, and the `reordered`/`deferred` telemetry markers.
- `reviewed.json` was joined first; 3 keys are `refuted` (bad corrections — they now serve as
  PINS defending the KO leg's stand-down gate), 5 are `covered`/`fixed` set-asides.

## Tally

| bucket | count | keys |
|---|---|---|
| pass outright (`fixed=True`) | 17 | 81904451-15, 82525101-14ᵖ, 82751468-70, 82754875-52, 82867148-48ᵖ, 83053965-91, 83456015-38, 83457493-20, 83457493-31ᵖ, 85045840-8, 85045840-10, 85046350-79ᵖ, 85046350-81, 85785067-41, 85785606-19, 85786096-70, 86089120-14 |
| effectively passing (artifact) | 3 | 82523164-55 (recorded `correct` index was a mislabel — pilot picks the rationale's intended 70HP Dwebble; reviewed=covered), 82751468-57 (chosen Night Stretcher is a free Item; Boss's Orders +30 `gust-to-strand` is the top Supporter and still plays this turn — sequencing artifact), 82753102-109 (the live Boss's blunder is GONE: it now scores 0; pilot digs with Hilda then attacks — residual attack-pick nuance is out of gust scope) |
| covered / shipped, residuals out of gust scope | 3 | 83661652-19 (poor-stall gust gone; residual is attach doctrine), 83667237-107 (ADR-0044 shipped: snipe off the redundant Mega; residual on-path-110HP vs Makuhita-80HP is a Damage-select nuance), 85058574-109 (degenerate match-planner note; multi-turn layer parked in deferred-multi-turn-criticals.md — see drift note below) |
| refuted → KO-leg pins | 3 | 82224509-46, 82525741-58, 83966968-78 (each: the gust/KO leg correctly stands its ground; human correction forgoes a KO) |
| **genuinely open** | **3** | **85163079-30, 86091435-119, 86091435-13** |

ᵖ = already a pin in `test_hyperclosure_corpus.py`.

**Drift note (85058574-109):** the 2026-07-11 review recorded `decide()==correct==[9]` (evolve).
Today's replay picks `[8]` (Boss's, `gust-for-the-ko` 50) FIRST, evolve second — same turn, same
line (the human's own line gusts AND evolves), so benign, but the degenerate-pin claim in
`reviewed.json` no longer holds frame-exactly. Presumably the dragapult f79/f81 tier-0
KO-enabling-gust resequencing landed after that review.

## The three open failures — mechanism, verified at source

### 1. `85163079-30` — whether-to-gust: the PLAY side has NO denial input at all

Board (probed): opp Active Cinderace 110HP (KO-able, 1 prize); opp bench **Staryu 70HP carrying
4 Energy** — their fully-loaded Mega Starmie wincon pre-evo. `gust_best_ko_prizes=1`,
`active_ko_prizes=1` → `gust-for-the-ko`'s strict `>` gate fails on the 1==1 tie → Boss's Orders
scores 0.0 and the pilot takes the plain Cinderace KO. Read was LIVE (γ=1.0, brief
`cinderace_mega_starmie_ex`) — irrelevant, because **every denial term in the doctrine
(`_gust_wincon_denial`, `_gust_matchup_priority`, `_gust_forward_denial`, `_gust_target_denial`)
lives on the SWITCH target-pick side** (`_gust_target_tactical`, doctrine_gust.py:59) — a select
the pilot only reaches AFTER deciding to play the card. The whether-to-play side
(`gust-for-the-ko`, doctrine_gust.py:296) is a pure prize comparison.

This is the canonical `their_keep_cost` miss — and note its inputs here are **board-visible, no
Read required**: 4 sunk Energies (ADR-0062's marginal energy-denial, pointed across the table) +
the `evolvesFrom` forward line (the deriver mirror). A thin, derivable keep-cost term on the play
side would break this tie; the full role-sheet/closure/deadline machinery is not needed for this
correction.

### 2. `86091435-119` — KO leg: the gust baseline is SNIPE-BLIND

Board (probed): opp Active Archaludon ex 400HP (`active_ko_prizes=0`); opp bench Relicanth 40HP.
`gust_best_ko_prizes=1` > 0 → `gust-for-the-ko` fires (+50) and spends Boss's Orders dragging
Relicanth up to KO it. But the human's line takes the SAME body for free: Phantom Dive's 60-damage
bench rider KOs the 40HP Relicanth while attacking — the menu attack (tac 1000.8, deferred) already
collects that prize with Boss's Orders still in hand, and the turn's Supporter slot free for
development. The gate's baseline (`active_ko_prizes` + `active_condition_ko_prizes`) counts direct
and Checkup KOs but NOT snipe-rider KOs, so a gust that is redundant with the snipe fires anyway.

Spec said the KO leg is "already an equation — leave alone unless a correction says otherwise."
This correction says otherwise: the fix is a correction TO the equation (a snipe-inclusive
baseline in the `gust-for-the-ko` gate / `_gust_best_ko_prizes` comparison), not a new currency.
(Opponent was unrecognized — brief null, cov 0.0 — but that is not the failure: prize math alone
already says stand down.)

### 3. `86091435-13` — stall leg: strand value must be MARGINAL (with-vs-without)

Board (probed): turn 2 famine (active_doomed, no attack payable) — famine gates all true, so
`stall-gust-over-dev-when-starved` (+95, doctrine_gust.py:337) fires. But the opponent's CURRENT
Active is a 0-Energy Duraludon 230 (`opp_active_can_damage_us=False`) and the gust target is…
another 0-Energy Duraludon 130. Swapping one stranded wall for another denies NOTHING — "doesn't
really make a difference" (the human; correct = Retreat). The mild sibling `gust-for-the-stall`
carries the `opp_active_can_damage_us` gate and correctly stands down; the famine sibling
deliberately dropped that gate (the forward-lethal-Riolu case) and so has no marginality test at
all. This is ADR-0062/0063's ruling — denial is marginal, never a flat bounty — applied to
TEMPO: stall(T) = strand value of T MINUS the strand value of the Active they already have stuck.
A gate-shaped fix (or a marginal stall term); no new currency needed.

## What Round 0 says to each grill question (spec §agenda)

1. **When may denial OUTRANK a prize?** The corpus shows only the EQUAL-prize tie (85163079-30:
   1v1, break toward the loaded wincon). NO correction asks denial to outrank a strictly larger
   prize. The grill can likely settle for: keep-cost breaks ties and sub-prize gaps only —
   no worth-points↔prizes exchange rate needed yet.
2. **Derive vs declare.** The one live denial miss is fully board-derivable (sunk Energy +
   `evolvesFrom`). Round 0 gives no evidence that brief-declared roles are needed on the play
   side. Derive-first, declare-as-correction stands.
3. **Their closure coverage.** No correction in this corpus turns on re-access/rebuildability.
   Defer; the haircut-vs-coverage ruling can wait for evidence.
4. **Their deadline/gates.** Same — no correction turns on it. Defer.
5. **Stall currency.** 86091435-13 answers the spec's open question directly: stall does NOT need
   the one currency; it needs a MARGINALITY test (with-vs-without the swap). The "legitimate
   answer: not everything must converge" branch is the measured one.
6. **Which shadows fold?** The five shadows produced ZERO failing corrections on the target-pick
   side. Nothing in this corpus forces the fold. The only structural gap is that NO denial term
   exists on the play side (finding 1).
7. **Opportunity cost.** 86091435-119 is an opportunity-cost failure INSIDE the existing gate
   (snipe-blind baseline) — fix the equation, don't add a term.

## Recommended build shape (for the grill to confirm — much smaller than the seed doc)

1. **KO-leg gate fix:** make the `gust-for-the-ko` baseline snipe-inclusive (a menu attack whose
   rider already KOs the gust target stands the gust down). Pin: 86091435-119; re-check the three
   refuted pins still stand down.
2. **Famine-stall marginality gate:** `stall-gust-over-dev-when-starved` requires the strand to be
   an IMPROVEMENT over the opponent's current Active (e.g. `opp_active_can_damage_us` OR the gust
   target strands harder than the body it frees). Pin: 86091435-13; keep ep83457493 f20 passing
   (its famine stall was real — the freed Cinderace faced a forward-lethal line).
3. **A thin play-side keep-cost tie-break:** on an equal-prize gust-KO tie, credit the target's
   sunk Energy (marginal, ADR-0062 pointed across the table) and forward line — board-derived,
   γ-free, sub-prize (breaks ties, never overrides a strictly bigger prize). Pin: 85163079-30;
   the refuted 82224509-46 (equal-prize tie where the human was WRONG to gust — the pre-evo
   carried nothing) becomes the counter-pin proving the tie-break stays sub-prize.

Everything else in the seed doc — the full `their_keep_cost` equation, role sheets, their-closure,
their-deadline — stays SEED: measured, found unsupported by the current corpus, build nothing
(the grab/pitch precedent). Re-open when ladder corrections produce the evidence.
