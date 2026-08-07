# ADR-0033: Transient attack effects are a log-inferred, match-scoped tracker

**Status.** Accepted & built 2026-07-02 (TDD; the completion plan's P2 —
`docs/todo/effect-compendium-completion.md` (since removed)). Extends
[ADR-0032](0032-card-knowledge-is-an-engine-audited-effect-compendium.md).
**Amended 2026-07-02 (wiring pass): the `retreat_lock` field is DELETED, not wired.** An engine
probe settled its fate: the engine **enforces** the 22 "Defending Pokémon can't retreat" effects
by **omitting the RETREAT option** from the locked side's next-turn menu (control turn with
Energy + Bench: RETREAT offered; every post-Corner turn: absent — gated as
[tests/sim/test_retreat_lock_engine.py](../../tests/sim/test_retreat_lock_engine.py),
REQ-TRANS-0006). A menu-driven, this-turn-only Pilot therefore gains nothing from tracking it:
my-side locks are self-enforcing (engine sims inherit the real state too), tightening the
opponent-side **Incoming** on a lock would be UNSOUND (a hidden Switch-class card still swaps),
and the one honest consumer (a gust-doctrine "don't gust away the Active my lock strands") is
untriggerable by any shipped deck (none of the 22 lock attacks is in ours) — a rule that can never
fire can never earn its keep. Parse + `AttackStat` field + tracker grant removed; re-add them only
alongside a real consumer.

**Context.** 138 attacks grant "during your (opponent's) next turn" effects — pool-verified:
17 defender takes-less (Frost Barrier, Reflect), 6 prevent-all walls, 23 self-locks ("this Pokémon
can't attack / use attacks"), 18 self-referential named locks, 2 self next-turn bonuses, 22
Defending-can't-retreat, plus a ledgered tail (coin-gated variants, hand-locks, cost-raisers).
The observation exposes **no per-Pokémon effect state** (`Pokemon` = id/serial/hp/maxHp/energies/
tools only), so a live shield or lock is invisible to the closed form — the agent would whiff into
a prevent-all wall, over-fear a self-locked attacker, or under-fear a bonused one.

**Decision.** Track them the way the deck tracker tracks hidden cards — **deterministically from
the log stream**, match-scoped, never probabilistically:

1. **Fields on `AttackStat`** (`parse_attack_transients`, text-seeded like every other tier):
   `nextTurnReduction`, `nextTurnPreventAll`, `nextTurnSelfLock`, `nextTurnSameAttackLock`
   (only when the named attack IS this attack), `nextTurnSelfBonus`. Coin-gated transients are NOT
   parsed — the flip isn't knowable, and under-crediting a possible enemy shield is the safe
   direction for my attack math. (Retreat-locks were parsed originally and deleted by the 2026-07-02
   amendment above — the engine enforces them at the menu.)
2. **`TransientTracker`** (`common/transients.py`): consumes each observation's logs; an `ATTACK`
   log whose attack carries transient fields grants an effect for that side, **bound to the
   attacking serial**; the grant expires when the granter's next `TURN_START` fires — exactly the
   "during your opponent's next turn" window. Serial-binding gives leave-the-Active expiry free
   (retreat/evolve/KO → new serial → no match). Per-viewer log replays are idempotent (one grant
   slot per side — a side attacks once per turn); a turn regression (new match) resets. The Pilot
   observes only the REAL stream (`_planning` guards out engine-sim futures).
3. **Consumers.** The oracle takes `defender_transient` (reduction / prevent-all applied after
   W/R, pierced by `ignoresEffects` — the same rule the Drednaw threshold follows); the wrapper
   resolves it by defender serial, so every Tier-0 site (tactical, Lethal-min, KO oracles,
   Incoming) sees live shields. `_incoming_active_damage` reads attacker-side grants: a self-lock
   zeroes their Active's threat, a same-attack lock excludes that attack from the max, a
   self-bonus raises it.

**Engine verification** (`tests/sim/test_transients_engine.py`): a two-sided drive — Sigilyph uses
Reflect (−40) every turn, Shaymin's plain Rear Kick 50 lands **10 = 50 − 40** on every hit. A
first draft with a Fighting attacker measured 0 and thereby confirmed the composition order too:
resistance (−30) then the transient (−40), floored at 0 — matching the oracle's ordering.

**Considered options.** *Expose effects from the engine* — not available (the obs simply lacks
them). *Probabilistic inference* — rejected: grants are deterministic facts in the logs; guessing
adds unsoundness for nothing. *Ignore the family* — rejected by prevalence (138 attacks) and by
the phantom-KO direction: attacking into an untracked prevent-all wall wastes the exact turns the
compendium exists to save.

**Consequences.** Named cross-attack locks, coin-gated shields, hand/item/supporter locks and
cost-raisers stay on the ledger (tracked fields exist for none of them; retreat-locks are
engine-enforced at the menu and deliberately untracked — the 2026-07-02 amendment). The
tracker is the first match-scoped state INSIDE the Pilot; the `_planning` guard is the invariant
that keeps engine-sim futures from polluting it.

**Measured engine fact (composition order).** The engine applies **resistance before** a defender
takes-less transient: an Okidogi draft measured resistance −30 and then Reflect −40 against the base
70. `tests/sim/test_transients_engine.py` therefore picks a Shaymin/Sigilyph pair that is neither
weak nor resisted, so the transient is the only modifier on the hit and the reading is clean.
