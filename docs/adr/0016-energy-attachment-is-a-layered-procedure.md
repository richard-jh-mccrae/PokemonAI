# ADR-0016: Energy attachment is a layered, override-able procedure

**Context.** Attaching Energy is the core tempo engine of the game, and the deep dive (2026-06-25)
surfaced gaps. (1) The agent had no positive driver to attach at all — it only attached when a deck
rule happened to reward a specific card (the special accel Energy), so it never powered up plain
attackers. (2) Readiness was a single hand-authored scalar per Line (`ready=Ready(energy=3)`),
blind to multi-attack Pokémon: Mega Starmie ex is "online" with **1** Water (Jetting Blow,
120 + 50 snipe) but the deck only modelled its 3-Energy Nebula Beam, so it sat in SETUP with a live
attacker and suppressed the cheap attack. Good attachment also depends on "will my Active die next
turn?" and "which attacker comes online next" — universal in *procedure* but specific in their
*inputs*. And some advanced decks will need to override attachment outright (sacrifice lines,
Energy-moving toolboxes).

**Decision.** Energy attachment is a **layered procedure**, not per-deck logic:

- **① General Strategy — universal reflex rules.** Deck-agnostic, id'd, weighted Hypotheses in
  `common/strategy/baseline/baseline_energy.py` (relocated from `common/general_strategy.py` by
  ADR-0025): `power-up-attacker` (attach every turn), `use-acceleration`
  (prioritise the `energy_accel` Function Tag), `dont-feed-the-doomed` (don't sink Energy into an
  Active that will be Knocked Out next turn when a benched successor exists), `attach-energy-last`
  (sequence the attachment after draw/search).
- **② Deck Strategy — parameters, not logic.** `lines` (win-condition path + payoff), `roles`
  (`win_condition` / `primary_attacker` / `accel_source` / `starter`), `params`. The deck supplies
  *facts*; the general procedure reads them.
- **③ Tactical Evaluator — engine-computed, never authored.** Readiness, "will it die",
  cheapest-sufficient, weakness — derived from engine card stats (`minAttackCost`, `maxDamage`,
  `weakness`), not hand-written numbers.

**Readiness is engine-derived.** A Line's `ready.energy` defaults to `None` → the Pilot derives
"online" from the payoff's **cheapest attack cost** (`CardStat.minAttackCost`); a deck may still
pin an explicit threshold. `build-before-attack` likewise gates on the Tactical Evaluator's
**value** (a meaningful-damage floor), not a binary is-KO, so a strong sub-KO attack isn't muted.

**Decks override through a declarative ladder, least→most invasive:** (1) **retune / disable** any
general rule by id (`overrides`, [ADR-0009](0009-training-methodology.md)); (2) **augment** with
the deck's own Hypotheses (merged additively — a sacrifice deck adds a positive rule that offsets
`dont-feed-the-doomed`); (3) **reparameterize** via `params` / line data. The enabling commitment:
every general energy rule is an **id'd Hypothesis** — ③'s engine math only *feeds* those rules,
never decides alone — so all override channels apply uniformly and decks stay pure data
([ADR-0008](0008-pilot-is-a-layered-rules-pipeline.md)).

**Considered options.** A single per-deck attach-priority callable (rejected: imperative deck code,
breaks ADR-0008's declarative-data principle; reachable later as a *declarative* priority spec once
the attach target is exposed to the scorer). A hand-authored readiness scalar (rejected: blind to
multi-attack Pokémon, one more number to keep in sync on reprints).

**Consequences.** "Consider all attacks / cheapest-sufficient / will-it-die" fall out of engine
stats, so one improvement to the general procedure lifts every deck. Full attach-*target* awareness
(type-match; routing the doomed Active's Energy to a specific successor) needs the attach target
exposed to the scorer (the `ATTACH_FROM` sub-select) — partially landed (`Context.option_area`,
`dont-feed-the-doomed`); the rest is the next increment.
