# ADR-0044: The deferred opponent-choice residue is narrow closed-form reads, not revived escalation search

**Status.** Accepted (grilled 2026-07-06, `/grill-with-docs`) + **Built 2026-07-06** (`/tdd`) +
**flipped DEFAULT ON 2026-07-06** (user decision — see *Amendment*). Both reads ship behind kill-switches
`snipe_prize_redundant` / `forced_promotion` (now **DEFAULT ON**; the switches remain for a one-line
revert), gated `REQ-READ-0001..0006` in
[tests/strategy/test_opponent_choice_reads.py](../../tests/strategy/test_opponent_choice_reads.py) and
the #30 KO-Race ordering gate `REQ-OBJ-0014` in
[tests/strategy/test_objectives.py](../../tests/strategy/test_objectives.py); full suite green.
Resolves the three deferred 2026-07-04 corrections in
[deferred-multi-turn-criticals.md](../todo/deferred-multi-turn-criticals.md) §2026-07-04. Extends
[ADR-0040](0040-match-judgment-is-per-turn-closed-form-objectives.md) (Prize Path / Path Denial / KO
Race) and the [ADR-0026](0026-posture-generic-core-is-net-new-read-levers.md)/Tier-4 opponent model. New
glossary terms *Forced-Promotion Read*, *Prize-Redundant Target* in
[src/common/CONTEXT.md](../../src/common/CONTEXT.md).

**Context.** The 2026-07-04 mega_starmie blunder round deferred three corrections as capability-gaps
tagged "needs M3/M4 multi-turn + opponent-modelling":

- `83661649-30` — pick the KO-Race attack *sequence* (Jetting Blow over Nebula Beam; "also anticipate
  the opp's Wally heal"). Same shape as `a21472`.
- `83667237-107` — opponent **prize-trajectory** (I need 4 = one Mega Lucario + 1; snipe the small,
  **deny** the 2nd Mega). Same shape as `b4649`.
- `83661649-45` — **forward-promotion** read (their Active is dead; pre-chip the benched Mega Starmie
  ex they will promote, not the energized Staryu).

Since deferral, T3 (Prize Path / KO Race, ADR-0040) and the T4 predicted-attacker overlay landed, and
the T6 engine-tree escalation (ADR-0043) — the literal "multi-turn search" — was **built and
REGRESSED** (44 % mirror A/B), parked default OFF; its own gap-list puts the unlock at the T5
value-model leaf (also regressed, parked) plus a real opponent-deck reply model, not trigger breadth.

A **real-Pilot re-measure** (2026-07-06, shipped T0–T4-ON agent) settled which are actually still open:

| # | today | cause |
|---|---|---|
| 30 | **already covered** — the KO Race flips Jetting **189.9** > Nebula **184.7**; toggling `objectives_race` off restores the old Nebula blunder (119.9 < 209.7) — **proven causal** | closed-form, done |
| 107 | still snipes the redundant benched Mega Lucario `[1]`=62 vs the small `[3]`=0 | (a) `path_target_ids` card-id leak onto the duplicate species; (b) prize-blind threat-rank (top-threat 30 + energized 20 = 50 survives even without the +12 leak) |
| 45 | still snipes the energized Staryu `[0]`=50 vs the benched wincon `[1]`=0 | the "energized = imminent attacker" heuristic misfires when the Active is dead and a promotion is forced |

None needs search: one is done, two are closed-form-addressable.

**Decision.** Resolve all three with **narrow closed-form reads**; T6 stays parked.

1. **#30 — covered by the KO Race.** Lock it with a `REQ-OBJ` **ordering-invariant** gate (the
   Jetting-family attack's tactical > the Nebula-family's on the captured state, `objectives_race` ON) —
   robust to the *correct* develop-first sequencing that makes `chosen == [2]` the wrong assertion, and
   it exercises the **no-path race-credit** branch (`path_target_ids` empty here) that `a21472`
   /`REQ-OBJ-0001` does not. The "anticipate the Wally heal" note is opponent-choice residue that does
   **not** change the pick — a full heal only *strengthens* Jetting (the banked bench chip survives a
   heal that erases direct damage) — so it stays the T6-class residue, out of scope.

2. **#107 — off-path prize-redundant snipe suppression + body-identity keying.** Two defects:
   (a) `path_target_ids` is **card-id-keyed**, so with a duplicate species (two Mega Lucario ex) the
   on-path credit for the *active* copy leaks onto the *benched redundant* copy — fix by matching the
   **specific body identity** in the snipe consumer while **keeping** card-id keying for `_sticky_path`'s
   cross-turn coherence; (b) even without the leak the redundant Mega scores 50 on **prize-blind**
   threat-rank vs the on-path small's 0 — fix with a **Prize-Redundant Target** suppression: dampen the
   snipe threat-rank boost on a target off my cheapest Prize Path whose prizes **overshoot** my remaining
   count and that is **not** an imminent threat to me this turn (the offensive twin of Path Denial —
   "don't chip a body I provably don't need to KO"). **Definition of done is intent-based**: the snipe
   goes to an on-path 1-prize body (Lunatone *or* Makuhita), **never** the redundant benched Mega.

3. **#45 — a Forced-Promotion Read.** When the opponent's Active is **doomed** (my attack KOs it, or it
   is already at 0 HP) a promotion is forced next turn; predict the promoted body as their **highest
   eventual-threat ready body** (the win-condition by attack power, **energy-independent** — they have
   acceleration to power it), and **redirect the snipe** there, overriding the energized-imminence tier
   **for that pick only**. This corrects **Incoming**'s affordability-based "next promotion = hardest
   *affordable* body" for the OFFENSIVE pre-chip; Incoming's worst-case *defensive* read is untouched.

Each ships behind a **kill-switch**, A/B-measured, default-ON only on a passing A/B (ADR-0009/0021), and
is **γ-gated** so an unrecognized opponent / unknown path suppresses or predicts nothing (structural
no-regression).

**Band-contract reconciliation (with ADR-0040).** ADR-0040 forbids objectives from being eligibility
**gates** and caps **phase** labels at small additive bands. #107/#45 let an objective **dominate** the
threat read — but *narrowly*: only on a target/snipe pick, only when the path / forced promotion is known
(γ-gated), and as a **sound** consequence ("chip on a prize-redundant body is wasted"; "a doomed Active
forces a promote"), not an *estimated* phase mode. Scoped dominance on a soft, non-committal chip is
inside ADR-0040's spirit — the phantom-lethal risk it guards against is a *match-scale lock*, which a
50-damage snipe target is not.

**Rejected.**
- **Revive T6 escalation for the residue.** The built two-ply tree regressed; its unlock is the T5 leaf
  + a real opponent model, not trigger breadth. A soft chip and an already-covered attack pick don't
  justify that investment, and two of the three aren't even opponent-choice-*dominated*.
- **Make threat-rank globally prize-aware** (fold "advances my count" into `strongest_threat_rank`):
  cleanest single source of truth, but that rank feeds the planner key-threat rung + promote + snipe — a
  large regression surface for a snipe-local fix.
- **Rebalance threat-rank so wincons outrank energized bench-sitters generally** (#45): removes the
  energized-imminence signal that is *correct* when the Active is healthy.
- **A literal Makuhita-exact gate for #107**: needs a snipe-completability refinement to the path's `+1`
  selection; over-fits one board when the intent (avoid the redundant Mega) is the general principle.
- **Re-key `path_target_ids` on body identity everywhere**: breaks `_sticky_path`'s deliberate card-id
  cross-turn coherence.

**Build note (2026-07-06).** Implementation sharpened the `target_prize_redundant` condition: "prizes
redundant to my count" reads as **off my committed cheapest path** (I reach my total without this body),
which is why an off-path *low*-prize small (Makuhita) is also deprioritized in 83667237-107 — the
committed path already takes its `+1` via Lunatone, so chip on any other body doesn't advance it, and the
snipe lands on the on-path small (the intent DoD). The "not an imminent threat to me" guard is realized
as: a high-prize body I never need is avoided **always**, a low-prize off-path body only when I am **not**
under pressure (`not board.active_doomed` — else keep threat-denial). `opp_active_doomed` is scoped to the
**certainly-forced** case (their Active at ≤0 HP), which is 83661649-45 and cleanly avoids colliding with
83667237-107 (where I *can* KO their live Active but no promotion is yet forced); the broader "my attack
KOs it this turn" trigger is a deferred refinement. Body-identity keying uses `id(body)` (stable within
one decision) so it never disturbs `_sticky_path`'s card-id cross-turn coherence.

**Consequences.** New kill-switches (or a fold under `objectives_path`), each A/B'd before default-ON.
The snipe baseline gains the off-path-redundant suppression and the forced-promotion redirect;
`objectives.py`'s on-path snipe check matches the specific body identity. `deferred-multi-turn-criticals.md`
records the three resolved (a `REQ-OBJ` gate for #30; build-this-closed-form for #107/#45). T6 remains
parked with its ADR-0043 evidence unchanged. The value model's feature set is unaffected (these are
target-selection reads, not new leaf features).

## Amendment — flipped DEFAULT ON without the ladder A/B (2026-07-06)

**Context.** The Decision above ships each read behind a kill-switch, default-OFF, "A/B'd before
default-ON" (the ADR-0009/0021 convention). The natural A/B leg for `snipe_prize_redundant` is the
**mega_starmie-vs-mega_lucario** matchup — 83667237-107 IS that matchup (the two Mega Lucario ex). But
mega_lucario is currently **too weak to serve as an A/B opponent**: mega_starmie wins the pairing
regardless, so the leg cannot measure the read's effect (the signal is swamped by the skill gap). A
mirror A/B would exercise neither read's core case.

**Decision.** Flip both switches **DEFAULT ON** now (`main.py` × 3 agents + `_build_pilot`
`.get(..., True)`), substituting **manual ladder-match correction review** for the automated A/B — the
user gathers real ladder games and tags any misplay the reads cause, which is a *stronger* signal than a
skill-gap-masked A/B for exactly these opponent-choice situations. The kill-switches remain, so a
correction that indicts either read is a **one-line revert** (`.get(..., True)` → `False`) or a
per-deck `params` override.

**Why acceptable.** Default-OFF was byte-identical to the prior agent (proven), so the blast radius is
confined to the specific snipe decisions these reads touch (an off-committed-path high-prize body; a
forced promotion) — both sound, closed-form, γ-gated. The reads never override a KO (`snipe-for-the-ko`
still wins) and never touch the sound Lethal/Planner rungs. The risk is an *unmeasured* mirror-winrate
delta; it is bounded, reversible, and now watched via ladder corrections rather than a one-shot A/B.

**Rejected.** *Wait for a stronger mega_lucario* (blocks the fix indefinitely on an unrelated deck's
strength); *mirror-only A/B* (doesn't exercise 107's cross-matchup core); *keep default-OFF and hand-set
the param in ladder runs* (the shipped agent — what the grader runs — would still make the blunders).
