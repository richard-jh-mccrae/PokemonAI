# Term sufficiency audit — do `state_value`'s terms cover what actually wins games? (POC-A1, 2026-08-01)

**Issue #268** — the parallel audit track for the Value System POC (ADR-0092). Read-only: no `src/`
change, no rung change, no term implementation. It walks the **decks**, deliberately, because the
corpus cannot find this class of gap — both gates prove "no unruled regression versus what the OLD
rung-driven agent chose on OLD frames", so a term the new architecture needs and the old agent never
exercised leaves no trace in them.

**Why the stakes are asymmetric.** Under differencing a play that moves state no term reads prices at
**exactly 0 delta**, and at Issue #263's uniform 1-ply ordering a 0 delta means *never explored*, not
*undervalued*. A missing term is therefore not an inaccuracy; it is a class of play the agent
structurally cannot choose. Worse, the seam is not neutral about it: `_PLAY` is MODELLED as *"the
card leaves hand"* (`apply_option.KIND_COVERAGE`), so a card whose effect the clause vocabulary
cannot express does not price at 0 — it prices at **minus the hand value of the card spent**. An
unpriced effect is thus strictly worse than a no-op.

## What this was audited against, and why that is not the issue's literal instruction

Issue #268 says to audit against Issue #262's spec if the terms are not yet implemented. They **are**
implemented — on branch `claude/issue-262-w0l5xt`, unmerged at the time of writing — so this audit
reads the **implementation** (`src/common/state_value.py` at that branch, 1160 lines, 7 families) and
not the issue body. That is the stronger source: a spec cannot tell you that `_exposed_bodies` omits
the `context` kwarg (finding **F2**), and half the findings below are of exactly that shape. `main`
still carries the T0 inert contract (6 families, every entry point raising `NotImplementedError`);
auditing that would have measured nothing.

Where the two disagree, the branch wins and it is flagged inline. `attack_ev` is the one term audited
**against its spec**: the pure function exists and is complete, but it has no StateModel-side
extractor and is not summed into `state_value` — Issue #263 wires it. Verdicts naming `attack_ev`
therefore read *"covered by spec, unwired"*, never *"covered"*.

**Sources read** (every card fact and rule verified at source per CLAUDE.md's cardinal rule — none
recalled): `data/EN_Card_Data.csv`; `docs/rules.md`; `src/common/card_functions.json`;
`src/common/card_effects.json`; `src/common/snapshot_coverage.py`; `src/common/apply_option.py`;
`src/common/state_model.py`; `src/common/strategy/{combat,damage}.py`;
`src/agents/{dragapult_ex,mega_lucario,mega_starmie}/STRATEGY.md`; the four `deck.csv` lists;
`docs/matchups/*.md` (8 archetypes).

## The registry as audited — what each family reads, at the granularity that decides verdicts

| Family | Reads (code, not docstring) | The granularity that matters |
|---|---|---|
| `prize_race` | `PrizeRace.my_prizes_remaining`, `.opp_prizes_remaining` | counts only; no deck count, no turn number |
| `survival` | per MY body: `prize_value` × `halve(turns_to_ko_me − 1)`, rank-graded; `predicted_loss` | the clock is an **integer**; `turns_to_ko_me` is called **without `context`** |
| `threat` | `needs.opponent_target_value` over reachable KOs | gate is `best_reachable_damage ≥ target.hp_remaining` — **printed damage, opponent-independent**; their **Active only**; `survival_shift` passed as 0 |
| `readiness` | per MY body: printed `maxDamage` × `max(readiness_p, halve(turns_to_afford))` × role relevance | payoff is the body's **own printed form**; nothing reads who is Active |
| `hand` | `needs` resolution: `assignment_coverage`, `re_access`, `latent_worth` | the `set_keep_v2` spine; all-zero when no resolution is supplied |
| `development` | per MY body: deploy relevance, forward `owed_damage` hop-discounted, line reachability, escalating bench-slot price | **my side only**; reads *forward* topology, never *backward* (a missing pre-evolution) |
| `attack_ev` *(terminal, unwired)* | `damage` (caller supplies, W/R applied), `target_hp`, `target_prizes`, `ko_probability`, riders, economy, `next_turn_cost` | a pure function; **no extractor exists**, so every rider value is whatever T4 passes |

## Coverage matrix — concept × deck exposure × verdict × owning term

Exposure is **card count in that deck's 60**. `—` = the deck does not run the concept. `[R]` marks a
concept already named on a `blind_to` deliberate-ignore list (recorded as ruled, not re-litigated);
`[N]` marks one that appears on no list.

| # | Strategic concept (from doctrine / matchup docs / card text) | drag | luca | star | slow | Verdict | Owning term |
|---|---|---|---|---|---|---|---|
| 1 | Weakness ×2 as the KO route | 7 | 16 | 10 | 18 | **PARTIAL** `[N]` | `threat` (gate), `attack_ev` |
| 2 | Opponent's hand size drives their damage (`handSizeDamage`) | — | — | — | — | **PARTIAL** `[N]` | `survival` |
| 3 | Multi-prize body's loss is prize-**lethal** | 5 | 4 | 3 | 8 | **UNCOVERED** `[N]` | none (structural) |
| 4 | Trainer damage-boost to cross a KO breakpoint | — | 7 | — | 1 | **UNCOVERED** `[N]` | none |
| 5 | Standing chip on THEIR bench as a cross-turn asset | 6 | — | 3 | 4 | **UNCOVERED** `[N]` | `threat` (partly `[R]`) |
| 6 | Snipe the pre-evo to deny a forward payoff | 6 | — | 3 | 4 | **UNCOVERED** `[R]`\* | `development` (my-side only) |
| 7 | Deck-order manipulation (put known cards on top) | — | — | — | 8 | **UNCOVERED** `[N]` | none (`deck_order` = HIDDEN) |
| 8 | End-of-turn energy decay (`discard_eot`) | — | — | 4 | — | **UNCOVERED** `[N]` | `readiness` |
| 9 | Companion-body gated attack / ability | — | 5 | — | 4 | **UNCOVERED** `[N]` | `readiness` |
| 10 | A hand card that is topologically unplayable (no base) | — | — | — | 2 | **UNCOVERED** `[N]` | `hand` / `development` |
| 11 | Hand disruption (Judge / Stamp / Harlequin) | 2 | 3 | 2 | — | **UNCOVERED** `[R]` | `threat` |
| 12 | Stadium in play | 2 | 2 | — | 4 | **UNCOVERED** `[R]` | `development` |
| 13 | Attached Tools (defensive HP, retreat, riders) | — | 2 | 1 | 2 | **UNCOVERED** `[R]` | `survival` |
| 14 | Energy denial / resource strip | 4 | — | 4 | — | **UNCOVERED** `[R]` | `threat` |
| 15 | Who occupies the **Active** slot | ✓ | ✓✓ | ✓ | ✓ | **UNCOVERED** `[R]` | `readiness` |
| 16 | Ability readiness (evolve to switch an engine on) | 9 | 5 | 4 | 10 | **UNCOVERED** `[R]` | `readiness` |
| 17 | Special conditions (Confuse / Paralyze / …) | 2 | — | — | — | **UNCOVERED** `[R]` | `survival` |
| 18 | Sub-turn healing (heal below one turn of incoming) | 2 | 1 | 4 | — | **UNCOVERED** `[R]` | `survival` |
| 19 | Opponent action-economy lock (item lock) | 1 | — | — | — | **UNCOVERED** `[N]` | `attack_ev` (rider) |
| 20 | Their board topology / their line completing | n/a | n/a | n/a | n/a | **UNCOVERED** `[R]` | `development` |
| 21 | Deck-out as a second race | — | — | — | — | **UNCOVERED** `[R]` | `prize_race` |
| 22 | Bench-slot scarcity / spare-body cliff | ✓ | ✓ | ✓ | ✓ | **COVERED** | `development.bench_slot_price` |
| 23 | Evolution line topology, forward | ✓ | ✓ | ✓ | ✓ | **COVERED** | `development.evolve_marginal` |
| 24 | Hold the evolve until the body is armed | ✓ | ✓ | ✓ | ✓ | **COVERED** | `readiness` × `development` |
| 25 | Keep multi-prize bodies off the exposed seat | ✓ | ✓ | ✓ | ✓ | **COVERED** | `survival` |
| 26 | Gust a soft body Active to convert it | 3 | 4 | 1 | — | **COVERED** | `threat` (their Active) |
| 27 | Bench-empty doom (a KO ends the match) | ✓ | ✓ | ✓ | ✓ | **COVERED** | `survival.predicted_loss` |
| 28 | Hand quality / spend-vs-hold | ✓ | ✓ | ✓ | ✓ | **COVERED** | `hand` |
| 29 | Prize lead + proximity | ✓ | ✓ | ✓ | ✓ | **COVERED** | `prize_race` |
| 30 | Self-lock attack (Mega Brave / Accelerating Stab) | — | 6 | — | 2 | **COVERED (spec)** | `attack_ev.next_turn_cost` |
| 31 | Attack-as-acceleration (Aura Jab, Turbo Flare) | — | 3 | 4 | — | **COVERED (spec)** | `attack_ev.economy` |
| 32 | Effect-ignoring attacks (Nebula Beam / Cosmic Beam) | — | 3 | 3 | — | **COVERED (spec)** | `attack_ev.damage` |
| 33 | Rush-evolve bypassing the played-this-turn gate | — | — | 4 | — | **COVERED** | `development` (hop consumed) |
| 34 | Comeback gate (Rosa's: only when behind) | 1 | — | — | — | **COVERED** | `prize_race` (engine gates legality) |

\* **#6 is ruled only in half.** `threat.blind_to` rules out *reaching* a benched body (deferred to
`attack_ev`'s snipe rider). It says nothing about the **value of what is denied** — that the body
sniped is a wincon pre-evolution. That half appears on no list; see **F5**.

Counts for #1 are weakness-exposed bodies in that deck's own 60 (`mega_lucario` 16/16 and
`mega_starmie` 10/10: every Pokémon in the list carries a printed weakness; `slowking` 18/20 —
Kyurem is the exception; `dragapult_ex` 7/16, its Dragon line having none, which is itself a
doctrine pillar). #2 has no card in our four decks — its exposure is entirely opponent-side and is
argued in **F2**. #15 is not card-countable; `✓✓` marks `mega_lucario`, where the dual-Mega
retreat-swap makes it a win-plan critical path. #16 counts ability-bearing Pokémon cards. #20 and
#21 are properties of a term, not card counts.

**Concept → finding.** The matrix numbers concepts; the next section numbers findings, and they are
different sequences because ruled omissions are collapsed into one ledger entry. The map:
1→F1 · 2→F2 · 3→F3 · 4→F4 · 5→F6 · 6→F5 · 7→F7 · 8→F8 · 9→F11 · 10→F12 · 11→F9 · 19→F13 ·
12-18, 20, 21→F10 (the ruled ledger) · 22-34 are COVERED and raise no finding.

## Ranked findings

Ranked by **exposure**: cards × decks, and whether the concept sits on a win-plan's critical path. A
gap on a 1-of tech card is noise; a gap on a wincon line is a blocker.

---

### F1 — `threat`'s reachability gate is weakness-blind, and blind in **both directions**  ·  BLOCKER

**Unread dimension.** Damage as the defender actually takes it. `threat`'s gate is
`model.mine.best_reachable_damage(active) >= target.hp_remaining`, and `best_reachable_damage` is
documented as *"the biggest **PRINTED** damage … **Opponent-independent**"* (`combat.py:1136-1143`).
It applies no Weakness ×2, no Resistance −30, no `preventsDamageFrom`, no `damageReduction`, no
`preventsDamageAtLeast`, and no live damage boost — all of which `strategy/damage.py:114-149`
implements and every live Pilot consumer goes through.

**Why this is not a rounding error.** `threat` is gated, not scaled: below the threshold it returns
`()` and the whole family reads **0.0**. So the error is a cliff, and it falls both ways.

- *Under-claim.* `mega_starmie`'s own doctrine encodes "lead Jetting Blow when the Active is
  Water-weak with ≤240 HP" — printed 120, doubled 240 (verified: Mega Starmie ex id 1031, Jetting
  Blow `[{W}]` 120; `docs/rules.md` §5, S&V prints ×2). Under the printed gate every one of those
  KOs reads *unreachable* and the position prices as though the opponent's Active were untouchable.
- *Over-claim.* `docs/matchups/crustle.md` seam 1: Crustle's Rock Inn means *"a pure-ex deck cannot
  damage an active Crustle at all"* (`CardStat.preventsDamageFrom`). The printed gate says reachable;
  the real damage is 0. `threat` then prices a KO that cannot happen.

**Exposure.** Every Pokémon in `mega_lucario` (16) and `mega_starmie` (10) carries a printed
weakness; `slowking` 18 of 20, `dragapult_ex` 7 of 16 (its Dragon line has none — which is itself a
doctrine pillar). **Seven of the eight matchup docs name a weakness KO as the primary counterplay lever**
(alakazam Darkness ×2 + Fighting −30; archaludon Fire ×2; crustle Fire ×2; cinderace_mega_starmie
Lightning ×2; hariyama_mega_lucario Psychic ~170 on the 340 body; hop's Darkness/Fighting;
kyogre_mega_abomasnow Metal ×2). This is the single most repeated strategic concept in the entire
opponent-facing corpus.

**Cheapest fix.** Do not write new math — `threat`'s reachability read is the wrong oracle for a
question that has a right one. Read the damage model against the actual defender instead of the
printed number; no new constant, and it closes the over-claim and the under-claim together.

> **Corrected 2026-08-01 while specifying Issue #278 S3** — the first draft of this paragraph said
> *"replace the gate's `best_reachable_damage` with `predicted_max_damage`, one call site"*, and both
> halves were wrong. `predicted_max_damage` is the **Incoming** (worst-case) read and explicitly
> *"does NOT filter by the opponent's Energy affordability"* (`combat.py:359-361`), so it is the wrong
> instrument for an OFFENSIVE gate. And `best_reachable_damage` must not be replaced at all: it is the
> counterfactual leg of the attach marginal (ADR-0069 §2) and is deliberately opponent-independent, so
> retuning it moves the corpus-ruled `attach_value`. The correct shape is a SIBLING that keeps
> `reachable_attach`'s Budget filter and swaps the damage read to the per-attack `predicted_damage`,
> plus a model accessor — see Issue #278 S3 for the specified version, which is authoritative over
> this line.

**Ruled?** **New.** No `blind_to` entry mentions Weakness, Resistance or damage prevention. The
registry's own `registry_gaps()` cannot see it: it is self-referential and only catches facts
somebody already typed into a `does_not_read`.

---

### F2 — `survival` drops the hand-size damage scaler by omitting one kwarg  ·  BLOCKER

**Unread dimension.** The opponent's hand size, where their attack scales on it.

`_exposed_bodies` calls `model.theirs.turns_to_ko_me(b.body, my_benched=…, my_bench=…,
opp_active=…)` and passes **no `context`**. The hand-size leg reads the hand straight from that
context: `hand = (context or {}).get("atk_hand") or 0` (`combat.py:396`), so with no context it
contributes 0 and the clock is computed off printed damage alone. `combat.py:770-773` states the
invariant this breaks in as many words: *"all six Incoming call sites thread the per-decision
context"*. `state_value` is the seventh, and it does not. The two live suppliers do
(`pilot.py:5799`, `objectives.py:357`).

**Why it matters.** `docs/matchups/alakazam.md` — **rank 2 by play-rate, 32.1% of tracked episodes**
— is built on this one fact: *"Its damage **is** its hand size (Powerful Hand, no floor,
Active-only), so the premium lever is hand disruption timed to the swing turn."* With `atk_hand`
absent, an Alakazam holding twelve cards and an Alakazam holding two produce the **same**
`turns_to_ko_me`, so `survival` is flat across the exact axis the matchup turns on — and the Judge /
Unfair Stamp / Harlequin play that answers it (F9) prices 0 in `threat` for a separate reason. Both
readings of the same board fact are dark at once.

**Exposure.** No card in our four decks scales on hand size; the exposure is entirely opponent-side
and it is the second-most-played archetype in the tracked meta. `CardStat.handSizeDamage` already
exists and is already parsed — this is a dropped argument, not a missing capability.

**Cheapest fix.** Thread a context into the `turns_to_ko_me` call in `_exposed_bodies` and the
`reachable_incoming` call in `_predicted_loss`. `theirs.hand_size` is a HOMED zone
(`snapshot_coverage.WRITABLE`) with a live accessor (`state_model.py:788`), so the fact is available;
what is missing is the argument.

> **Corrected 2026-08-01 while specifying Issue #278 S2** — the first draft said *"pass
> `context={"atk_hand": model.theirs.hand_size}`, two kwargs"*, and a literal reading of that would
> introduce a worse bug than it fixes. The clock memoizes on **`id(context)`**
> (`state_model.py:818`, `:867`), so a freshly-allocated dict per call busts the memo on every call —
> and a freed dict's `id` can be reused by a later allocation, letting two different contexts collide
> on one memo entry. The context must be allocated ONCE per model. It must also be
> **direction-aware**: the Damage Formula's variables are named relative to the attacker, so
> `survival` needs the `theirs` reading and `threat` (F1) needs `mine` — one dict is wrong for both.
> Issue #278 S1 specifies the shared `StateModel.damage_context(attacker=…)` accessor that S2, S3 and
> S4 all consume, and is authoritative over this line.

**Ruled?** **New**, and of a distinct kind from the rest: this is not a term that declines to read a
fact, it is a term that intends to read it and loses it at the call. `threat.blind_to` names *their
hand* as unread by **`threat`** — it does not license `survival` dropping the scaler.

---

### F3 — Prize-lethality of a specific body's loss is structurally unpriceable  ·  BLOCKER

**Unread dimension.** The interaction between *what a body is worth when it falls* and *how many
prizes the opponent still needs*.

`survival` prices `prize_at_risk × halve(turns_to_ko_me − 1)`; `prize_race` prices the two counts.
Neither may read the other — `survival.does_not_read` names `my_prizes_remaining` explicitly, and
the double-counting rule is enforced by test. So the board fact *"they are at 3 prizes and my Active
is a 3-prize Mega"* — a **loss**, not an exposure — enters the scalar as the same number as *"they
are at 6 prizes and my Active is a 3-prize Mega"*.

**Why the architecture creates it.** This is the disjointness rule producing a blind spot rather than
preventing double-counting. The fact is genuinely a **product** of two dimensions the registry
assigns to different families, and no family is permitted to form it.

**Exposure.** All four decks, and it is `mega_lucario`'s explicitly-flagged **CRITICAL** doctrine
(STRATEGY.md §4, user-ruled 2026-06-29), with a worked example: *"Bad: Solrock → Lucario → Lucario.
Opp KOs Solrock (1) → Lucario (4) → Lucario (7 ≥ 6 → opponent wins). Good: … interleaving a 1-prize
body between Mega exposures buys the turn that wins."* Multi-prize bodies: `slowking` 8,
`dragapult_ex` 5, `mega_lucario` 4, `mega_starmie` 3. The doctrine even names the tractable
per-turn shadow it wants — *"read `Board.opp_prizes_remaining` vs the Active's prize value"* — which
is exactly the read the disjointness rule forbids.

**Ruled?** **New**, and it could not have been ruled: `survival.does_not_read` names
`my_prizes_remaining` as a *double-counting* exclusion (it belongs to `prize_race`), which is a
statement about ownership, not a statement that the product of the two is worthless. `registry_gaps()`
reports nothing because the fact is claimed — just by a family that cannot combine it.

**Cheapest fix.** Do not relax disjointness. Make the lethality a **third thing**: extend
`survival.predicted_loss` from a boolean to the terminal-loss family it already is. It is already the
one term allowed to price a *game-ending* fact outside the positional band (`LOSS_PRIZES`,
`_LINE_CAP`'s dominance structure), and *"this body's Knock Out gives them their last prize"* is a
game-ending fact by `docs/rules.md` §7 case 1 exactly as bench-empty doom is case 2. It reads
`opp_prizes_remaining` as a **win-condition test**, not as race value — which is the distinction
`survival.does_not_read` is actually protecting. One extractor change, no new family, and it keeps
`prize_race` the sole owner of the race.

---

### F4 — A Trainer damage-boost prices **negative**  ·  HIGH

**Unread dimension.** Live this-turn damage grants — `transient_grants`, an **OWED** snapshot zone
(`snapshot_coverage.py:111`, owner T1 / Issue #260).

Premium Power Pro, Black Belt's Training and Gravity Mountain have **no Effect Clause entry** in
`card_effects.json` (verified: all three return `None`). Their effect lives in
`CardStat.damageBoost` / `damageBoostType` / `damageBoostVsEx`, which `damage.py:114-125` consumes
via `context["atk_boosts"]` — a context no family builds. So playing one writes nothing any family
reads. And because `_PLAY` is MODELLED as *the card leaves hand*, the delta is not 0: it is
**`hand`'s loss of the card**, i.e. strictly negative. The agent is not merely blind to the boost —
it is priced as a mistake.

**Exposure.** `mega_lucario` runs **7** (4× Premium Power Pro +30 to {F} attacks, 1× Black Belt's
Training +40 vs {ex}, 2× Gravity Mountain −30 to Stage 2), and its **CLOSE** plan is exactly the
breakpoint KO those cards exist to reach: *"Mega Brave 270 + Black Belt's 40 = 310; + Power Pro +30 =
340 reaches the ~320–340 Mega/ex tier."* `slowking` adds Brave Bangle (+30 vs Active {ex}). Every
number in that sequence is a card the agent will price as a self-inflicted hand loss.

**Cheapest fix.** Home the zone, then read it. `transient_grants` is already enumerated as OWED with
a named owner; `CardStat.damageBoost` is already parsed; `damage.py` already consumes it. What is
missing is a snapshot read, which is T1's work item, plus threading `atk_boosts` into the same
context F1 and F2 need. **F1 + F2 + F4 are one context argument**, which is why they should be fixed
together.

**Ruled?** **New.** `development.blind_to` names the STADIUM (so Gravity Mountain's stadium-ness is
ruled, F10) but nothing names a **damage boost**. `footprints_writing_unhomed` is the mechanism
designed to catch a MODELLED kind writing an owed zone — it works off per-card clause unions, and a
card with no clauses unions to the empty set, so it reports nothing here. Worth recording as a
limitation of that guard, not only of this term.

---

### F5 — Denying a forward payoff prices at the target's current worth only  ·  HIGH

**Unread dimension.** Their board's **topology** — that the 70-HP body I can reach is the base of a
330-HP, 3-prize payoff.

`development` is my-side only (`blind_to`: *"their board topology … an accepted POC asymmetry"*).
`threat` prices a target by `needs.opponent_target_value(prize_advance=target.prize_value, …)` —
what the body yields **now**. So killing a Staryu prices 1 prize, the same as killing any other
1-prize body, when the doctrine's whole point is that it erases three.

**Why the ruled entry does not cover it.** `threat.blind_to` rules that *reaching* a benched body is
`attack_ev`'s snipe rider. That is about **reachability**. The **valuation** — that this particular
body is worth more than its prize count because of what it becomes — is on no list. Even after T4
wires the snipe rider, the rider will price the same 1 prize.

**Exposure.** **Seven of the eight matchup docs** make this their primary or secondary lever:
*"snipe/gust a Staryu before it rush-evolves … to trade 1 prize for a denied 3"*;
*"prioritise sniping Snover pre-evolution — a 1-prize cost erases a 3-prize wincon"*; *"snipe the
fragile 80-HP pre-evos (Riolu denies the wincon, Makuhita denies the gust-attacker)"*; *"race the
fragile pre-evos — KO Dreepy (70) / Drakloak (90) before they become the wall"*; plus alakazam
(Abra/Kadabra), archaludon (Duraludon), crustle (Dwebble). Our own decks carry 13 bench-reaching
attackers (Dragapult ex ×3, Mega Starmie ex ×3, Munkidori ×2, Fezandipiti ex ×2, Kyurem ×2,
Zeraora ×1) — and it applies to a plain gust-and-KO too, which every deck has.

**Cheapest fix.** `MySide.forward_payoff` already computes exactly this quantity for my side, and
`development` already consumes it. Point a mirrored read at their bodies and feed it into
`opponent_target_value`'s `prize_advance` as a denial credit. Reuses the shipped forward index
(ADR-0020's provider primitive); no new oracle.

---

### F6 — Standing chip on their bench is not an asset  ·  HIGH

**Unread dimension.** Damage already on the **opponent's benched** bodies.

`threat`'s only target is their **Active** (`_reachable_target_values` returns at most one element).
Their bench bodies' `hp_remaining` is never read. A board where six damage counters sit on their
bench from last turn's Phantom Dive scores identically to a fresh board.

**Why this is the deck's engine, not a nicety.** `dragapult_ex`'s win condition is explicitly
cross-turn: *"Phantom Dive **pre-loads** benched mons with softening chip you cash into prizes on
LATER turns via Munkidori, Fezandipiti Cruel Arrow and Boss's Orders"* — and the doctrine spells out
the timing: *"Phantom Dive is the turn-ender, so Munkidori / Boss's / Cruel Arrow resolve BEFORE it
and convert **prior-turn** chip."* The asset the whole deck accumulates is invisible on the board
between turns, and the gust that converts it (`threat` does see the new Active) is priced as though
the target were fresh.

**Exposure.** `dragapult_ex` 6 (3× Dragapult ex + 2× Munkidori + 1× Fezandipiti ex, plus 2× Risky
Ruins feeding it), `mega_starmie` 3 (Jetting Blow's unconditional 50, `CardStat.benchSnipeDamage`),
`slowking` 4 (2× Kyurem Trifrost 110 to three bodies; Zeraora Thunder Raid 210 to a benched {ex};
Fezandipiti). On `dragapult_ex` it is the **critical path of the win plan**.

**Cheapest fix.** Widen `_reachable_target_values` from their Active to `model.theirs.bodies`, with
the bench leg gated on a snipe route existing rather than on `best_reachable_damage`. The counters
themselves are HOMED (`damage_counters`) and `BodyView.hp_remaining` already reads them, so the fix
is a loop bound and a gate, not new plumbing. Note the interaction with **F1**: fix the gate first or
the widened loop inherits the printed-damage cliff.

**Ruled?** **Half-new.** `threat.blind_to` rules that a benched body is unreachable *this turn*
without a snipe rider, and defers the rider to `attack_ev`. It says nothing about damage **already
standing** on their bench between turns, which is a property of the board and not of any attack — so
`attack_ev` will never price it however completely T4 wires the rider.

---

### F7 — Deck-order manipulation is invisible, and the HIDDEN ruling does not cover it  ·  HIGH (one deck)

**Unread dimension.** **Known** top-of-deck.

`snapshot_coverage` classifies `deck_order` as **HIDDEN**, with the reason: *"Unknowable from an
observation, and the reason the apply-seam refuses anything riding a shuffle."* That is correct for a
shuffle. It is **false for a to-top effect**: Ciphermaniac's Codebreaking (*"Search your deck for 2
cards, shuffle your deck, then put those cards on top of it in any order"*) and Academy at Night
(*"that player may put a card from their hand on top of their deck"*) make the next draws **known**.
Nothing reads it — the cards are still "in deck", so `deck_odds` counts them among the unseen — and
`my_deck_count` is unchanged, so a Codebreaking prices as a pure hand loss (the F4 shape).

**The combo this kills.** `slowking` runs 3× Slowking whose attack is *"Discard the top card of your
deck, and if that card is a Pokémon that doesn't have a Rule Box, choose 1 of its attacks and use it
as this attack"* — a card whose damage **is** the top of the deck, next to 4 Codebreaking whose job
is to put a chosen card there. The deck's central engine prices at zero-minus-a-card.

**Exposure.** `slowking` 8 (4 + 4), zero elsewhere — but `slowking` is Issue #149's validation case,
and a validation deck the value system cannot see is a poor validation.

**Ruled?** **New**, and it corrects a ruling rather than merely sitting outside one: `deck_order`'s
HIDDEN status is justified by an argument that holds for shuffles and does not hold for a to-top
effect. Recorded here as evidence about the *classification*, not only about the terms.

**Cheapest fix.** Split the zone: keep `deck_order` HIDDEN for shuffles and add a **`known_top`**
zone (an ordered tuple of card ids known to be on top, empty by default and cleared by any shuffle),
homed on `MySide`. `hand`'s `re_access` leg is the natural reader — a card known to be on top is
re-access with probability 1, which is exactly what that leg already measures probabilistically. Not
a new family; a new supplier plus one reader.

---

### F8 — `readiness` cannot see that an Energy will evaporate  ·  MEDIUM-HIGH

**Unread dimension.** The `discard_eot` rider on attached Energy.

Ignition Energy (id 17) carries `{"kind": "energy_provide", "amount": 1, "amount_on_evolution": 3,
"type": "colorless", "rider": "discard_eot"}` — verified in `card_effects.json`. `readiness` reads
`readiness_p` and `turns_to_afford`, both of which count what is attached **now**. Attaching Ignition
on a turn that ends without an attack therefore raises `readiness` and then silently loses the card;
worse, `turns_to_afford`'s forward leg will count an Energy that will not be there next turn.

**This is a recorded blunder, not a hypothetical.** `docs/rules.md` §"single most useful distinction"
cites it verbatim as the worked example of a reason-only rule: *"don't attach Ignition T1-going-first
— you can't attack, so it's discarded for nothing, correction ep81903490 f5."* The deck doctrine
repeats it (*"Going first: attach Water (never Ignition — it'd discard unused)"*).

**Exposure.** `mega_starmie` 4 of 13 Energy, and it is the burst half of the deck's two energy
routes (Ignition → CCC → Nebula Beam the turn it evolves). One deck, but on the win plan.

**Cheapest fix.** `readiness_odds` already takes the max of a now-leg and a forward leg; make the
**forward** leg discount Energy carrying `discard_eot`. The rider is already in the clause
vocabulary and already in `CLAUSE_WRITES`. The now-leg stays untouched, which is correct — the Energy
is genuinely there this turn.

**Ruled?** **New.** No `blind_to` entry mentions energy persistence. `survival.blind_to`'s
integer-clock ruling is the nearest neighbour and is a different fact (healing granularity, not
resource decay).

---

### F9 — Hand disruption prices 0 — ruled, and the largest ruled gap by exposure  ·  MEDIUM-HIGH `[RULED]`

Named on `threat.blind_to`: *"their hand and deck — `theirs.hand_size` and `theirs.deck_count` have
suppliers and no reader, so hand disruption (a Judge, a discard effect) prices exactly 0. This is the
single largest uncovered family; T4 must always-expand disruption plays."* **Recorded as ruled — not
re-litigated.** Ranked here only because the audit owes exposure numbers on ruled items too.

**Exposure.** 7 cards across 3 decks (`dragapult_ex` 1× Judge + 1× Unfair Stamp; `mega_lucario` 2×
Judge + 1× Unfair Stamp; `mega_starmie` 2× Harlequin), and the named counterplay against the #2
archetype in the meta (F2). The ruling's mitigation is *"T4 must always-expand disruption plays"* —
which is an ordering escape hatch, not a valuation, so the play will be explored and then scored at
its hand cost. Combined with F2, the entire Alakazam matchup plan is invisible from both ends.

---

### F10 — Ruled-omission ledger (recorded, ranked, **not** re-litigated)

Every one of these appears on a `blind_to` deliberate-ignore list. Per Issue #268's step 4 they are
**ruled omissions, not gaps**. Ranked by exposure so #262/#263 can prioritise them without re-deriving
the numbers.

| Ruled omission | Family | Exposure | Note |
|---|---|---|---|
| The **Stadium** | `development` | 8 cards / 3 decks (Risky Ruins ×2, Gravity Mountain ×2, Academy at Night ×4) | `model.stadium` is HOMED with no reader. Two matchup docs prescribe *"run a stadium to overwrite"* as a lever. Gravity Mountain is also a damage-boost (F4) — the stadium ruling covers only half of it |
| **Energy denial** | `threat` | 8 cards / 2 decks (Crushing Hammer ×4 twice) | `deny_relevance` dark until T2 / Issue #228 |
| **Attached Tools** | `survival` | 5 cards / 3 decks | OWED zone, T1. ADR-0028 built a whole Tool Doctrine on the survival-turns math the swap drops |
| **Ability readiness** | `readiness` | 28 ability-bearing cards across the four decks (9 / 5 / 4 / 10) | The registry itself calls it *"the largest single regression risk in this swap"*. Every draw engine (Recon Directive, Run Away Draw, Lunar Cycle, Run Errand, Flip the Script, Last-Ditch Catch) and Munkidori's counter-move |
| **Who is ACTIVE** | `readiness` | `mega_lucario`'s dual-Mega retreat-swap is a **win-plan critical path**; slowking's Run Errand is Active-only | Compounded by `allowance_retreat_used` being OWED — a retreat's own legality cannot be differenced |
| **Special conditions** | `survival` | 2 cards (Munkidori Mind Bend Confuse) | OWED zone, T1 |
| **Sub-turn healing** | `survival` | 7 heal cards / 3 decks | Explicitly accepted at POC bar: the clock is integer turns |
| **Their board topology** | `development` | all decks | Accepted POC asymmetry — but see **F5**, which is the *valuation* half and is **not** ruled |
| **Deck-out** | `prize_race` | 0 in our decks | Correctly deferred; no corpus frames |
| **My hand on a simulated end board** | `hand` | rollout-only | Does not touch #263's 1-ply ordering, which always scores real boards |
| **The opponent's reply** | `attack_ev` | all decks | Depth-2 out of POC (Issue #150). Note it silently absorbs *"burst beats chip against a heal-wall"*, which three matchup docs make their headline |
| **Opponent-choice riders** | `attack_ev` | few | Mirrors the apply-seam's refusal |
| **Turn number / who went first** | `prize_race` | all decks | Both `preferred_start` decisions (dragapult second, lucario first) are pregame, so unaffected in practice |

---

### F11 — Companion-body gated attacks price their printed damage unconditionally  ·  MEDIUM

**Unread dimension.** An attack or Ability whose effect is gated on **another body being in play**.

`readiness` takes `payoff = CardStat.maxDamage` of the body's own printed form. Solrock's Cosmic Beam
is *"If you don't have Lunatone on your Bench, this attack does nothing"* (verified, id 676) — but
`maxDamage` is 70 either way, so a Solrock with no Lunatone scores the same readiness as one with,
and losing the Lunatone moves nothing. The dependency runs both ways: Lunatone's Lunar Cycle needs
Solrock in play, and *that* one **is** expressible — `card_effects.json` gives Lunatone
`{"kind": "draw", "amount": 3, "condition": "solrock_in_play", …}`. The vocabulary can carry the
condition; the attack side has no clause and `readiness` reads no condition.

**Exposure.** `mega_lucario` 5 (3× Solrock + 2× Lunatone) — the deck's draw engine *and* its early
attacker, both halves of a mutual dependency. `slowking` 4 (2× Metagross, whose Conjoined Beams pays
+150 *"if Beldum and Metang are on your Bench"* and the deck runs neither; 2× Kyurem, whose Plasma
Bane is gated on the **opponent's** discard containing a "Colress" card).

**Cheapest fix.** Extend the existing `condition` field from draw clauses to a payoff clause and have
`_ready_bodies` zero the payoff when the condition fails. The precedent is committed and one card
already uses it.

**Ruled?** **New.** `readiness.blind_to` names Ability readiness (a *missing payoff*); this is the
opposite failure — a payoff that is present in `CardStat` and conditionally worth nothing.

---

### F12 — A hand card that can never be played is priced as coverage  ·  MEDIUM

**Unread dimension.** **Backward** line topology — whether a hand card's pre-evolution exists at all.

`development.line_topology` cancels the evolve credit for a line whose **forward** form is
unreachable. Nothing asks the mirror question. `slowking` runs 2× Metagross — Stage 2, `evolvesFrom`
**Metang** (verified) — and the list contains **no Metang and no Beldum**. Those two cards can never
be played. `hand` prices them through `set_keep_v2`'s assignment, which will happily assign a
170-HP attacker to an attacker slot.

**Why it matters beyond one deck.** The Pilot already ships two guards for exactly this class —
`fetch-base-before-stranded-payoff` and `dont-strand-the-evolving-engine`, the latter built after a
measured priority inversion where the fetch doctrine *preferred tutoring a dead Stage 1 over the
Basic that enables it* (`dragapult_ex` STRATEGY.md §6). Replacing the rung layer with differencing
drops both unless `hand` learns the question.

**Exposure.** 2 cards in 1 deck directly. Structurally: every evolution line in every deck, whenever
the base is prized or discarded — which the `slowking` list makes permanent rather than transient.
That this is the deck Issue #149 nominates as the validation case is not a coincidence.

**Cheapest fix.** `MySide` already has the pool-level forward index; the backward question is
`CardStat.evolvesFrom` resolved against play + hand + the sound "not provably gone" deck read
(`unseen_counts`) the rest of the snapshot already uses. Feed it into the `needs` resolution as a
playability gate so the card covers no slot.

> **Corrected 2026-08-02 by the build (Issue #288, ADR-0103).** Two halves of that line were wrong,
> and both were found by measuring rather than reading.
>
> * *"`CardStat.evolvesFrom` resolved against three zones"* is ONE HOP, and one hop is not the
>   question. A Metang in hand does not make a Metagross playable when every Beldum is gone. The walk
>   is the whole chain, grounding out on a body already in play or on a Basic.
> * It omits **Rare Candy** (*"...put that card onto the Basic Pokémon to evolve it, skipping the
>   Stage 1"*, card text id 1079), so a gate built to the line as written would have called
>   `grimmsnarl_ex`'s win condition dead with the enabler sitting in hand — a false positive worse
>   than the finding.
>
> The finding's own EXPOSURE claim also understated the defect. It is not only that a dead card is
> *priced* as coverage: on `grimmsnarl_ex` a stranded Froslass **covered** the `draw_engine` slot, so
> the live draw Supporter beside it priced at 0 and shed for free, **and** raised that slot's band
> from 8 to 12, because the band reads off its eligible rows. The shipped `deploy` factor could reach
> neither — it prices a card, and this is about which rows are candidates.

**Ruled?** **New.** `development.line_topology` is the forward half and is implemented;
`hand.blind_to` names hand SIZE and information ordering, neither of which is playability.

---

### F13 — Opponent action-economy locks are unpriced  ·  LOW (exposure), notable (structure)

Budew's Itchy Pollen (*"During your opponent's next turn, they can't play any Item cards from their
hand"*, free attack, verified id 235) restricts what the opponent may do next turn. No family reads
opponent capability; `attack_ev.reads` includes `attack_riders`, so it is **arguably** in that term's
spec, but `attack_ev.next_turn_lock` is documented as MY self-lock and no extractor exists. It is
also not `threat`'s ruled *energy denial*.

**Exposure.** 1 card, 1 deck — but it is the reason `dragapult_ex` sets `preferred_start="second"`
(rules.md §2: the first player cannot attack on turn 1), i.e. a 1-of that moved a deck-level
parameter. Ranked LOW on exposure and recorded so it is not mistaken for coverage.

**Cheapest fix.** Name it in `attack_ev.blind_to` if T4 will not price it, so the composer reads a
declared zero rather than an accidental one. That is the cheapest **honest** fix; pricing it needs
the OWED `transient_grants` zone, same as F4.

---

## Verdict — sufficient for X, insufficient for Y

**The six state families are sufficient for the game the corpus contains, and insufficient for the
game the decks are built to play.** That is the expected shape of the result, because the corpus is a
record of what the previous architecture looked at — but the specific line it falls on is sharper
than "some gaps remain", and it is worth stating precisely.

**Sufficient for — and genuinely well-composed on — the *positional development* game.** Bench
topology, evolution lines and their forward payoff, hold-the-evolve timing, hand quality and
spend-vs-hold, prize lead and proximity, bench-empty doom, keeping multi-prize bodies out of the
exposed seat, gusting a soft body Active to convert it. Every one of these is COVERED by a term that
composes a shipped instrument rather than forming a second opinion, and the mid-turn degradation
requirement is met honestly (`readiness_odds` takes the max of a this-turn probability and a forward
clock precisely so a half-built board is not flat). Concepts 22-34 are 13 of the 34 audited, and
they are the ones a *developing* turn is made of. On a develop-corpus frame the terms are sufficient,
and the Discrimination Gate's 33/248 strict rate against a baseline 40/248 is consistent with that:
the leaf did not get worse at the game it was measured on.

**Insufficient for the *combat* game — and the insufficiency is concentrated, not diffuse.** Three of
the four blocker findings are the same structural error seen from three sides: **`state_value` reads
damage as a printed number rather than as the damage model's answer.** `threat` gates on printed
damage (F1). `survival` calls the damage clock without the context that carries the scalers (F2).
Damage boosts have no reader at all (F4). Each is a *dropped argument or a wrong oracle at one call
site*, not a missing equation — which is the good news and the reason they rank as blockers rather
than as research: they are cheap, they are testable, and they are wrong **now**. F1's cliff behaviour
makes it the worst of the three: below the printed threshold the family reads exactly 0.0, so the
term does not degrade toward the truth, it falls off it.

**Insufficient for the *denial* game, and that one is structural.** The single most repeated concept
in the opponent-facing corpus — *snipe the pre-evolution to erase a payoff you could never
out-damage* — prices at the target's current prize count (F5), and the standing chip that converts to
prizes on a later turn is not an asset at all (F6). These are not dropped arguments; they need a term
to learn a question it does not currently ask. They are also the two findings most likely to be
invisible to both gates forever, because a corpus of what the old agent chose contains no frames
where the old agent chose them either.

**One finding indicts the architecture rather than an implementation: F3.** Prize-lethality is a
product of two dimensions the double-counting rule assigns to different families, and the rule
forbids any family from forming it. The recommended fix does not weaken the rule — it routes the
fact to `survival.predicted_loss`, the one term already licensed to price a *game-ending* condition
outside the positional band. The distinction worth preserving is that `survival` must not read prize
counts as **race value**; reading them as a **win-condition test** is a different question and
`docs/rules.md` §7 puts the two cases side by side.

**On the wave-3 `survival`-passivity signal.** The Issue #262 ruling packet flags 15 frames where
*"`survival` lets the leaf buy safety by not developing"*, and asks whether the fix is phase damping.
This audit did not rule those frames, but two findings bear on the question and are worth putting
next to them before a damping constant is chosen: `survival` is currently the **only** family reading
a combat clock (F1 leaves `threat` at 0.0 on every board where the printed gate fails), so it wins
by default rather than by weight; and it reads that clock without the scalers (F2), so its magnitude
is not the clock's true value either. A damping constant fitted before F1 and F2 are fixed would be
fitted to a measurement artifact. The flat 0.3 damping measuring *worse* (69 unruled vs 67) is at
least consistent with that reading.

**What would change the verdict.** F1 + F2 + F4 are **one shared damage context**, consumed at three
call sites, plus one snapshot zone homed. If those land, the terms become sufficient for the combat
game as well, and the residue is F3 (one extractor, no new family), F5 + F6 (two questions terms do
not yet ask), and a ruled ledger whose top three entries — Stadium, Tools, Ability readiness — are
already owed to T1 with named owners. That is a short list, and none of it is research.

> **Sharpened 2026-08-01 during Issue #278's specification.** This paragraph originally read *"one
> context argument threaded through three call sites"*, which understated it: the context has to be
> **model-owned, memo-stable and direction-aware** before any of the three can consume it safely
> (F2's correction note explains why a per-call dict is actively harmful). That is Issue #278's S1 —
> a subtask of its own, ahead of the three fixes, and it changes nothing about this verdict except
> the word "argument". The claim that the three are ONE fact rather than three coincidences survived
> the specification, which was the load-bearing half of the prediction.

## Findings by disposition

Issue #268 says findings become Issue #262 amendments or new issues, decided after this report lands.
The audit did not make that decision; it grouped them so it could be made quickly.

**DECIDED 2026-08-01.** The developer ruled a single remediation track rather than a scatter of
amendments and new issues: **Issue #278 (POC-T3.5)**, inserted into the critical path as
**#262 → #278 → #263**, with all thirteen findings as spec'd subtasks worked one at a time. The
column below records the audit's original suggestion against where each finding actually landed;
**Issue #278 is authoritative** wherever the two differ.

| Finding | Audit's suggestion | Where it landed |
|---|---|---|
| F1, F2, F4 | Issue #262 amendments | **#278 S3, S2, S4** — behind new substrate **S1** (the shared damage context), which the audit did not foresee as its own step |
| F3 | Issue #262 amendment | **#278 S5** — extends `predicted_loss`, as suggested |
| F5, F6 | New issues | **#278 S7, S6** — sequenced S6→S7 (same function) and S6 after S3, or it inherits F1's printed-damage cliff |
| F7, F11, F12 | New issues | **#278 S11, S9, S10**. S11 gated on a design decision before any code; **S10 moved out of `state_value`** into the Pilot's needs resolver, so one fix serves the rung system and the differencing system |
| F8 | Issue #262 amendment | **#278 S8** |
| F9, F10 | No action — ruled | **Out of scope, tabulated with owners** in #278. Do not re-litigate |
| F13 | Issue #262 amendment (documentation) | **#278 S12**, joined by the `deck_order` HIDDEN rationale and, if S11 is declined, `known_top` |
| — | — | **#278 S13** — closeout: reconcile this report, re-measure the passivity signal, record the P95 for #263 |

## Re-running this audit

Nothing here is a one-off measurement; every number is re-derivable from committed data.

- Tag exposure per deck: `card_functions.json` × each `deck.csv` (60 card ids per line).
- Card facts: `data/EN_Card_Data.csv` keyed on card id — never from memory. The
  `Riolu → Mega Lucario ex` single hop (no intermediate Lucario) is the standing worked example.
- Clause coverage: `card_effects.json`; a `None` there next to a card with a real effect is the F4
  shape and is worth checking first for any new card.
- Term reads: `src/common/state_value.py` `REGISTRY` / `TERMINAL_REGISTRY`, plus the `_extractors`
  below `state_value` — the docstrings and the code disagree in exactly the places this audit found,
  so read the extractor, not the family docstring.
