# Promote / retreat — grill-session seed: the prize-trade differential

**Status.** SEED — NOT designed, NOT built. The shadow ruling
(`docs/plans/shadow-equations-ruling.md`) applies: once the grill settles the design, the equation
ships as a SHADOW emitter beside the promote ladder regardless of how many corrections the ladder
already satisfies; swaps stay corpus + score-diff gated. Supersedes the attach spec's
"sibling consumer" paragraph, which under-called this family as "a cheap composition of two
existing oracles" — the user's counterexamples (below) refute that: readiness is hand-AND-closure
aware, and the value is a TRADE over an exchange window, not a single-body score.

## The musing (user, 2026-07-19)

> "Which Pokémon to promote after an own KO depends highly on not only their readiness but also
> prize mapping. For example: a Cinderace with zero Energy — when we have 1 Energy or an Energy
> fetcher in hand — promoted after the 1st Mega Starmie is KO'd, even though a benched Mega
> Starmie WITH Energy is on the bench. Mega Lucario has similar combinations:
> Solrock > Lucario > Hariyama > Lucario."

Two deck-declared trade patterns: the 1-prize accelerator soaks while it CHARGES the bench
(Cinderace's Turbo Flare = damage + 3-Energy bench accel), and the alternating sacrifice ladder
(1-prize bridge → wincon strike → 1-prize trade star (210) → wincon).

## The hypothesis (the equation)

Promote value is a **prize-trade differential over the exchange window**, not survival × threat:

```
promote_value(B) = Σ over the exchange window t:
      my_yield(B, t)          ← B's fundable actions: damage/KO it can actually pay for on turn t
                                 (hand + CLOSURE + accel riders — the gamble's one-attach-short
                                 Outcome-Class machinery pointed at B), PLUS what B's tenure lets
                                 the BENCH develop (Cinderace: 3 Energy/turn onto the wincon — a
                                 development rate, the preservation dividend)
    − their_yield(B, t)       ← prize_value(B) × P(they KO B on turn t | ADR-0064 incoming),
                                 weighted by PRIZE-MAP ASYMMETRY: prizes near their goal cost
                                 super-linearly (their last prize is unaffordable — today's hard
                                 vetoes are the step-function version of this curve)
```

The Cinderace case falls out: zero on-body Energy but a funded Turbo Flare THIS turn (1 Energy or
a fetcher in hand — the closure) → high my_yield (attack + charges the Mega) at their_yield of
just 1 cheap prize; promoting the energized Mega instead zeroes the accel dividend and exposes
2-3 prizes to the ADR-0064 incoming. The alternating Lucario ladder is HYPOTHESISED to be
**greedy-emergent** — each promote re-evaluating the local differential reproduces the
alternation without a declared sequence (grill question §1; declare the residue only if
measurement refutes emergence).

## Inventory — this ladder is the most-hardened family; respect it (verified 2026-07-19)

`baseline_promote.py` (+ retreat cousins): `interpose-the-cheap-attacker-to-preserve-the-wincon`
(+50 — three drivers: weakness trade / **the Cinderace case verbatim**: `accel_source` +
`bench_wincon_underpowered` + `basic_energy_in_deck` / gust tax; HARD VETO at
`opp_prizes_remaining < 2`; stands down on `opp_cannot_punish_wincon`, ADR-0064 D4),
`promote-the-ko-attacker` (+45, attach-this-turn-aware KO), `promote-the-ready-wincon` (+40,
per-option best target — the f104 first-bench-slot blindness fix), `dont-promote-into-their-prize-
reach` (−20 — "make them take six individual prizes, not two Megas", four stand-downs),
`promote-the-staller` (+20), `dont-promote-onto-their-path`. The boolean gates already encode much
of the trade intelligence; the QUANTITIES are flattened to five fixed weights whose partial order
(+50 > +45 > +40 > +20 > −20) is the hand-tuned shadow of the differential.

**What is genuinely missing (the user's two points, made precise):**
1. **Closure-aware readiness.** `interpose`'s driver (b) checks `basic_energy_in_deck` and
   `promote_target_can_attack` checks attachable-this-turn — neither sees "an Energy FETCHER in
   hand" (Fighting Gong / Energy Search / Ultra Ball chains). The gamble's one-attach-short +
   closure-outs machinery (`_gamble_ko_classes` / `_fetch_reaches_slot`) is EXACTLY this quantity,
   already built, never pointed at the promote target. Correction `82753102-120` is the live
   evidence (a promote decided by what was NOT in hand).
2. **The prize map as a quantity.** Today: step-function vetoes at `opp_prizes < 2` and
   `card_prize_value >= opp_prizes_remaining`. The equation form: a goal-distance weighting on
   their_yield (super-linear near their goal), which also prices the MIDDLE cases the vetoes skip
   (opp at 3-4 prizes with a 2-prize body — currently unpriced).
3. **The preservation dividend as a rate.** The accel driver is a boolean; Cinderace's 3/turn vs
   Aura Jab's discard-recover vs nothing are different dividends — `_recover_units` computes the
   number already.

## Round 0 — measurement (fresh pilot per replay; join reviewed.json)

~31 trade-flavoured corrections (grep promote/sacrif/interpose/wall/trade in rationales) + the 14
`bad_retreat` + relevant `bad_target`. Exemplars: `83037962-70` (the user's Cinderace pattern,
human-praised in an OPPONENT: "they promoted Cinderace after a KO, that was smart"),
`82753102-120` (hand-aware promote), `83007714-104` (first-bench-slot blindness — check it's
covered by the per-option fix), `82751468-14` (attach → retreat → KO sequencing),
`83116081-76`. Classify: already-passing / readiness-leg / prize-map-leg / dividend-leg /
sequence-leg. This family's rationales cite many ml/ms fixtures — expect a HIGH pass rate; the
shadow ruling makes that fine (construction proceeds; swap priority follows the failures).

## Grill agenda

1. **Greedy emergence vs declared sequence.** Does the local differential reproduce
   Solrock>Lucario>Hariyama>Lucario on replayed boards? If yes, no sequence machinery — the
   alternation is emergent. If no, the residue is a deck-declared trade PLAN (Lines-style overlay,
   Tier-3 adjacency) — declare, don't derive.
2. **The exchange window.** One exchange (their next KO) or until the race flips? ADR-0064's
   incoming is one-turn; a multi-turn window needs the 2ply machinery
   (`2ply-opponent-survival-grill-spec.md`) — grill the smallest window that prices the examples.
3. **The prize-map curve.** Shape + where it lives (the equation's their_yield weight vs the hard
   rungs' jurisdiction — the horizon discipline says match-deciding stays with hard vetoes; the
   curve prices the BAND between).
4. **Readiness reuse.** Point the gamble's Outcome-Class assembly at the promote target (hand +
   closure + accel), fail-closed. This is shared machinery — no new closure code.
5. **Retreat's extra term.** Retreat COST (the Energy paid — worth via card_worth) and the
   retreat-blocked cases; `82751468-14`'s attach→retreat→KO shows sequencing coupling with the
   attach oracle (same currency, same trace).
6. **Fold/survive.** The five weights fold into the differential; the HARD vetoes survive as the
   step edges of the prize curve (or the curve subsumes them — grill); `dont-promote-onto-their-
   path` (information/tempo) likely survives on its own axis.

## Hazards

- This family is ADR-0031/0044/0064-hardened with additive interactions (+50 stacking with +45) —
  the re-audit surface is the promote/retreat pins across `test_blunder_*` and the ADR-0064
  scenario suite. Seed calibration at the current partial order (the ADR-0060 anchor pattern).
- The +76 shape: the preservation dividend is an endorser — cap it (a dividend can never exceed
  the preserved wincon's own worth × its deadline odds).
- Anti-speculation as amended: high Round-0 pass rate expected; build the shadow anyway (the
  ruling), swap only measured failures first.

## Build shape (per the shadow ruling)

Phase 1: the shadow differential, emitted per promote/retreat option (terms: fundable-attack
P, dividend rate, their_yield with the curve, the window) + the agreement bit. Phase 2: staged
swaps by Round-0 + shadow-disagreement ranking; the alternating-ladder emergence test decides
whether any sequence residue is declared. Coordinates with the attach oracle (shared readiness +
currency; retreat couples to attach sequencing) — likely the SAME grill session should own both
agendas' §readiness question.
