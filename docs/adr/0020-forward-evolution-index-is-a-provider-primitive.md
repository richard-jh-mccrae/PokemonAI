# Forward-evolution knowledge is a provider primitive, distinct from the Read's EvoPath

**Status:** accepted (2026-06-28)

## Context

To snipe a benched pre-evolution *before* it comes online (the **Evolving Threat** signal — e.g.
`Riolu` → `Mega Lucario ex`, frame ep81905522 f75), the agent must know what a card eventually
evolves into and how hard that form hits. Two homes were possible: a **generic, deck-agnostic**
forward map derived from the engine card table, or the Scout's **opponent-specific** `EvoPath` /
`evolution_lines` mined from replays (`read.py`, `scout.py`). They are not interchangeable.

## Decision

Build the generic forward-evolution index as a **provider primitive**: invert `CardStat.evolvesFrom`
(a name) over the stat cache into `name → [descendants]`, walk it multi-hop (cycle/depth-guarded), and
expose `forward_max_damage(card_id) -> int` (max printed damage over a card's descendant forms, 0 if
none). It is built **inside** the provider from the cache it already enumerates — no public
`all_stats()`. The Pilot's `_context` consumes it first (M0, deck-agnostic, works with **no Read**
wired). Later the **same** primitive backs the Scout's off-meta `_evolution_paths` fallback (M2). The
Read refines an Evolving Threat's *accuracy*; it does not replace the generic primitive.

## Why

- At decision time the Pilot holds the provider but **not** the Read (Read→Pilot wiring is M2), so M0
  must source the signal from the provider.
- It's a structural fact, which belongs on the provider per the signal-source rule
  ([ADR-0006](0006-function-tags-single-source-of-structural-facts.md)) — not a behavioral tag, not the Read.
- One shared primitive avoids duplicating the forward-walk across both consumers.

## Consequences

Two evolution data sources coexist **by design** — generic (provider, always on) and opponent-specific
(Read `EvoPath`, confidence-gated). They answer different questions: "what can this card become" vs
"what will *this opponent's* card become." A reader seeing both should not collapse them. The
"attacker" threshold (line damage ≥ 100 ≈ OHKO of a median body; 100 is ~p76 of damaging attacks) is a
tunable constant in `general_strategy.py`, deliberately **not** fixed here.

**Known M0 gaps (accepted; adversarial review 2026-06-28).** This is the opponent-*agnostic upper bound*;
the Read (M2) refines accuracy. Specifically:
1. **Bench-damage-immune pre-evolutions are wastefully sniped.** Some benched bodies take no attack
   damage (broader than the "Tera ex" framing — ≥3 cards carry an unconditional *prevent-all-damage-
   while-Benched* ability **and** evolve into a ≥100 form, e.g. Antique Plume Fossil→Archen, Misty's
   Magikarp→Misty's Gyarados, Poltchageist→Sinistcha ex). `CardStat` has no immunity field today; closing
   this means threading the engine's `tera`/benched-immunity ability into `CardStat`. See `docs/rules.md` §11.
2. **`descendants only` is blind to an already-evolved, energy-less big body** (e.g. Hariyama 210). This
   is intentional — `snipe-the-threat` owns energized bodies; do **not** widen `forward_max_damage` to
   include the card itself.
3. **Affordability is ignored** — the opponent may never power the line. The weight (18 < `snipe-the-threat`
   20) and the `not target_is_threat` gate keep the signal conservative.
