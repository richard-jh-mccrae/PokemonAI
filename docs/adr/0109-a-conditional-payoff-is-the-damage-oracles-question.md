# ADR-0109 — A conditional payoff is the damage oracle's question, not a new condition vocabulary

**Status:** Accepted (built 2026-08-02, `/implement` on
[Issue #287](https://github.com/richard-jh-mccrae/PokemonAI/issues/287), T3.5/9 of the Value System
POC).
**Implements** the term-sufficiency audit's finding **F11** (`ADR-0104`).
**Applies [ADR-0032](0032-card-knowledge-is-an-engine-audited-effect-compendium.md)** (per-attack effect facts live on
`AttackStat` and every closed-form damage estimate routes through the ONE oracle) and
**[ADR-0068](0068-the-statemodel-is-a-lazy-pure-snapshot-shared-by-side.md)** (a board fact is answered off the
snapshot, once).
**Amends [ADR-0092 §4-T3](0092-the-value-system-poc-builds-by-differencing-tracks-with-wave-rulings.md)'s `readiness` family** — `body_payoff` is no
longer the printed `CardStat.maxDamage` roll-up. The equation (`payoff × odds × relevance`), its
scale and its `blind_to` list are untouched; only the number fed into `payoff` changes, and it
changes on exactly the cards that carry a board condition.
**Supersedes nothing.** It **refutes** the fix Issue #287 proposed — see *The rejected option*.

**Context issues:** Issue #287 (this build), Issue #278 (the T3.5 parent track), Issue #279 (whose
merged `damage_context` supplies the gate's input), Issue #262 (T3, which shipped `_ready_bodies`),
Issue #268 (the audit).

## Context

`readiness` prices *what a body achieves once it is online*. `_ready_bodies` read that number off
`CardStat.maxDamage` — the PRINTED roll-up over a card's attacks — and a printed number cannot carry
a board condition.

`mega_lucario` runs **3× Solrock** and **2× Lunatone** (`src/agents/mega_lucario/deck.csv`), and they
are each other's enablers. Verified at source (`data/EN_Card_Data.csv`):

* **Solrock (676)** Basic, HP 110, {F}, weak {G}, retreat 1 — **Cosmic Beam `{F}` 70**: *"If you
  don't have Lunatone on your Bench, this attack does nothing. This attack's damage isn't affected
  by Weakness or Resistance."* It is Solrock's **only** attack.
* **Lunatone (675)** Basic, HP 110, {F} — Ability **Lunar Cycle** (*"if you have Solrock in play"*)
  and Power Gem `{F}{F}` 50.

`EngineCardStatProvider` reports `maxDamage=70` for Solrock either way. So a Solrock with no Lunatone
benched scored the same readiness as one that had it; benching the Lunatone moved the term by
**exactly 0**, and under Issue #263's uniform 1-ply ordering a 0 delta is *never explored*, not
merely undervalued. Losing the Lunatone — to a Boss's Orders, to a Knock Out — cost nothing either,
so the agent had no reason to defend the enabler.

## Decision

**1. The payoff a term prices is the damage oracle's answer, not the card's printed roll-up.**

`StateModel.attack_payoff(body) -> AttackPayoff(attack_id, damage)` returns the best attack the
body can actually pay off with **on this board**. It walks the body's own attacks and prices each through the shipped
`CombatMath.predicted_damage` → `damage.compute_active_damage`, which already owns the gate: the
`requiresBench` leg returns 0 when a named partner is absent from `atk_bench_names`.

The call is **matchup-free** — no defender, so no Weakness/Resistance, no defender prevention, no
transient grant — exactly as the printed roll-up it replaces carried none. Who is exposed to whom is
`threat`'s and `survival`'s question, and pricing it here as well would be the double-counting
`state_value`'s registry exists to forbid. The bound is `"exact"`, not `"max"`: the `"max"` bound
deliberately keeps a conditional attack's ceiling because Incoming is a worst case and the opponent
may bench the partner before attacking, whereas this read is about a board as it stands.

**2. A gated maximum falls back to the best attack that still pays — it does not zero the body.**

Mesprit's Guardian Burst is dead without both Uxie and Azelf, but Full Heart is not. Zeroing the body
would price a real option at nothing.

**3. The attack id travels with the damage, in one record.**

`readiness_odds` asks `readiness_p` about the payoff attack. Once a gated maximum can fall back, the
two legs can name different attacks — and pairing one attack's damage with another's probability is
the saturation defect the payoff/odds split exists to prevent (Issue #262's own note: a saturated
term has zero derivative, so the attach that completes the cost prices at 0 and is never explored).
Returning `(attack_id, damage)` together makes the mismatch unspellable.

**4. The question lives on the side, and only there.** `BodyView.payoff_attack` — the printed-only,
body-scoped twin — is **deleted**, not left beside the new read. It could not see the Bench, which is
the entire bug, and its sole consumer was the line this ADR fixes. Two answers to "which attack pays
best", free to disagree in exactly the case that matters, is the drift `damage_context` was extracted
under (Issue #279). `_SideBase.bench_names` is likewise extracted from its inline comprehension in
`damage_facts` so the gate and the context read one list.

## The rejected option — and why the issue's own fix was refuted

Issue #287 specified: *"Extend the existing `condition` field from draw clauses to a **payoff**
clause, add the clause for the gated attacks… Condition vocabulary is per-card and must be
enumerated… A clause whose condition string the evaluator does not recognise must fail LOUD."*

Three measurements against `HEAD` retired it.

**The precedent it rests on does not evaluate anything.** `"solrock_in_play"` appears in
`src/common/card_effects.json` (Lunatone's draw clause) as **data only** — no evaluator in `src/`
recognises the string. The two that exist know three conditions between them
(`planner._condition_holds`: `remaining_hp_30_or_less`, `energy_3_plus`;
`combat._AttachCtx.condition_met`: `more_prizes_remaining_than_opp`) and both fail *closed* on
anything else. So the attack side was never "the half without a clause" — the draw side's condition
is not read either.

**The capability was already shipped, one layer down.**
`scouting.card_text.parse_attack_bench_requirement` parses Cosmic Beam's own sentence into
`AttackStat.requiresBench = ("Lunatone",)`; `strategy/damage.py` has zeroed the attack on an unmet
partner since ADR-0032; and Issue #279's merged `StateModel.damage_context` supplies
`atk_bench_names`. Building a second, hand-enumerated condition vocabulary beside a parser that reads
the card text would have violated the parent track's own **"Compose, don't invent"** rule. It also
dissolves the LOUD-on-unknown requirement: there is no vocabulary to be ignorant of — the parser
either extracts partner names from the printed sentence or returns `None`.

**Two of the three named cards are not this bug.** Walking the whole card set with that parser finds
exactly **two** gated attacks — Solrock (676) and Mesprit (216), and Mesprit is in no shipped deck.

| card | printed | `maxDamage` | verdict |
|---|---|---|---|
| Solrock 676 | Cosmic Beam {F} 70, *"nothing if no Lunatone on your Bench"* | **70** | the real over-price; fixed here |
| Metagross 276 | Conjoined Beams {P}{P} **130**, *"+150 more if Beldum and Metang are on your Bench"* | **130** | **refuted.** The provider takes the attack's printed damage, so the conditional bonus was never counted. The issue's own test — *"the +150 leg never counts"* — passes on the unfixed tree. |
| Kyurem 144 | Plasma Bane is an **Ability** making *Trifrost* cost `{C}` when their discard holds a "Colress" card; Trifrost's damage is a free-target 110×3 | **0** | **refuted.** A *cost* gate, not a damage gate, and in the opposite direction. At `maxDamage` 0 the body is skipped by `_ready_bodies` outright. If the cheapened cost is worth pricing it belongs to `readiness_odds`, not here. |

Recorded rather than quietly rescoped: no clause was added to `card_effects.json`, and no condition
vocabulary was enumerated, because neither is owed.

## Consequences

* `readiness` now moves on benching, losing, or gusting away a bench-partner enabler. That is the
  point: the develop that arms Solrock, and the defence of the Lunatone that keeps it armed, are both
  visible to 1-ply differencing for the first time.
* A gated body whose only attack is dead contributes nothing to `readiness` — the same treatment
  `_ready_bodies` already gave a 0-damage support body.
* `body_payoff` now depends on MY **Bench contents**. This is not a second claim on
  `development.bench_slot_price`: that prices how many slots remain, this prices what one attack can
  land, and the two never read the same number. Recorded in the family's `composition`.
* **Cost, measured** (60 corpus frames): the `attack_payoff` read is **1.80 µs** per body on first call and
  **1.40 µs** memoized (~2.7 bodies to a board). `state_value` on a fresh model measured **8.37 ms
  median / 17.28 ms p95 before** and **8.14 ms / 13.79 ms after** — no measurable regression, since a
  fresh evaluation is dominated by the model's own lazy derivations. The leaf-profile tripwire
  (`tests/strategy/test_leaf_profile.py`) is re-pinned with those numbers, as its own rule requires.
* The read is on `_SideBase`, so `threat` can compose it when Issue #281's lane reaches the same
  question for THEIR bodies. Nothing does yet, and nothing here pretends otherwise.
* **The residual gap is NAMED, not dissolved.** Retiring the LOUD-on-unknown requirement removes a
  vocabulary, not a blind spot: the parser's `None` is itself a silent pass. Walking the set for
  *"this attack does nothing"* finds 24 attacks — 10 coin flips (the `damageMin`/`damageMax` family,
  a different question), the 2 bench-partner gates now priced, and **12 unread board conditions**
  (no Stadium — Fan Rotom 174; a Bench-count floor — Victini 490; an exact hand size — Medicham 884;
  hand parity — Iron Boulder 971; defender predicates — Sawk 602, Camerupt 857, Basculin 577; their
  prize count — Hop's Cramorant 311; pay-from-hand discards — Decidueye 129, Lurantis 398, Ceruledge
  797). Each still prices its printed damage. **Exposure across the five shipped decks is 0** (the
  deck-csv walk finds only Solrock 676), so Issue #278's *"add only what the four decks need"* keeps
  them out of this build — and `readiness.blind_to` now carries them with their addresses, which is
  the mechanism Issue #263 reads to tell a genuine zero from an uncovered one. Closing any of them
  is another parser in `scouting/card_text.py` plus a context key, never the rejected vocabulary.
* **Both gates PASS** — leaf-lab 0 unruled `OK → MISS`, Decision Gate **0 picks moved**. Neither
  baseline re-captured. A green gate on a change that moves a term is a claim that needs a positive
  control, so one was run rather than assumed: walking every replayable corpus frame, the gate
  changes the payoff on **54 bodies** (22 mine, 32 theirs) and leaves **2229** byte-identical to
  `maxDamage`. Every one of the 54 is a Solrock with no Lunatone benched — 70 → 0. So the term
  genuinely moves on real boards and no ruled decision followed it; "green" here is not "never
  exercised".
