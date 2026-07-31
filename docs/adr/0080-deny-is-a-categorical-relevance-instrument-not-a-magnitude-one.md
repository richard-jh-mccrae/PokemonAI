# ADR-0080 — Deny is a CATEGORICAL RELEVANCE instrument, not a magnitude one: the Worth Damage Rate is not needed, it is MOOT

**Status:** Accepted (grilled 2026-07-29, `/grill-with-docs` on Issue #199 — five locked decisions).
Supersedes ADR-0078 decision 1 for the deny instrument and **withdraws** its one-backend claim for
deny. Builds in Issue #187 (recharted); Issue #199 closes as the shared layer, reduced.

**Renumbered 0079 → 0080 on rebase (2026-07-29).** The number was claimed at grill time and collided,
exactly as `docs/adr/README.md` predicts. Issue #161's *the Set-Up Active pick is one deck
declaration* merged first and KEEPS 0079 under the standing first-merged rule — itself already
renumbered 0075→0077→0078→0079 across three earlier rebases, which is the whole lesson in one
document. **Fifth collision in four days.** Cite the issue alongside the number
("ADR-0080, Issue #199"); the number is a rebase artifact, not an identifier.

**Context issues:** Issue #199 (this grill, S3c), Issue #187 (S4-deny, rechartered by decision 4),
Issue #188 (S4-snipe, unblocked), Issue #189 (S4-gust, re-inherits the Amendment E debt),
Issue #136 (the Value System tracker), ADR-0078 (the three-scales ADR this partly supersedes),
ADR-0062 (the denial oracle), ADR-0065 (the no-fudge discipline), ADR-0076 (the slot-family split),
ADR-0027 (the Brief / card-fact split decision 2 relies on).

## Context

ADR-0078 chartered S3c to build a **Worth Damage Rate** — damage per card-worth point — so deny's
keep price could be read out of the shared prize-denominated marginal. Decision 3 there required a
corpus anchor before any value was chosen, and set **gate 2**: *a keep-side deny anchor exists after
capture*. That gate has now been run. It fails, and then the ruling that settled it made it
irrelevant.

### The DISCARD sweep is complete and comes back empty

Corpus-wide there are **12** `Discard`-context frames (against 279 `Main`). Exactly **one** holds a
Hammer — `86091435-68`, the frame ADR-0078 already knew about. Build-shape step 1's sweep produced no
new candidate. There is nothing else to adjudicate.

### The one anchor is DEGENERATE, not merely one-sided

ADR-0078 recorded `86091435-68` as *"directional, so it bounds the rate on one side only."* Measured,
it is weaker than that. On that board the opponent's Active is Archaludon ex 160/300 carrying **one**
`{M}`, and its attack is Metal Defender `{M}{M}{M}` 220 (`data/EN_Card_Data.csv`, id 190). It cannot
attack with 1 Energy and cannot attack with 0, so:

```
strip_shift = 0     deny_value = 0.000        (the ADR-0078 strip marginal, deny_strip_delta ON)
opp_denial_best     = 0.0                     (the INCUMBENT ADR-0062 oracle, same frame)
```

Both instruments price the strip the user ruled valuable at exactly **zero**. Since
`worth_equiv = m × PRIZE_DAMAGE_RATE / WORTH_DAMAGE_RATE`, an `m` of 0 makes the rate **divide out** —
no value of it is derivable from this frame, under any Δ policy. Re-policying the Δ does not rescue
it.

Worse, the bound is against zero on the other side too: the two cards the endorsed pick pitches —
**Risky Ruins** (no Role, no `TAG_TIER` tag) and **Lillie's Determination** (tags `draw` /
`shuffle_hand`, neither in `TAG_TIER`) — both price **0.0**, confirmed live in the DP. Even with a
nonzero `m` the ruling would only assert *worth(Hammer) > 0*, which every positive rate satisfies.

**Gate 2 therefore fails on the evidence.** To derive the rate one needs a Hammer ranked against a
card of known NONZERO worth, in both directions. No such frame exists and none can be manufactured
from the corpus as it stands.

### The user's doctrine, which reframes the question entirely

Put to the grill 2026-07-29, and **verified at source** card-by-card:

> 1. Does the opponent have any Energy attached to any Pokémon? If no — hold the Hammer.
> 2. Does the body carry Energy AND do we KO it this turn (Active by attack, or benched by snipe)?
>    If so, no Hammer on *that specific* Pokémon.
> 3. For any Energy-carrying body we do not KO, read posture: is the Energy on their **wincon**? Is it
>    the **correct type**? Or is it fuelling a **supporting ability** we want muted?

with five worked rulings, every card fact of which checks out:

| ruling | the card fact that makes it right |
|---|---|
| KO their Lucario; bench has Riolu + Solrock, each 1 Energy → **hammer the Riolu** | Riolu → **Mega Lucario ex** (678) is a single hop, Aura Jab `{F}` 130 / Mega Brave `{F}{F}` 270. Solrock (676) Cosmic Beam *"does nothing"* without Lunatone benched. |
| Munkidori we cannot KO, `{D}` + `{P}` → **hammer the `{D}`** | Adrena-Brain fires *"if this Pokémon has any {D} Energy attached"*; Mind Bend costs `{P}●`. The `{D}` is pure ability-fuel. |
| Dragapult with a stray `{D}` + a `{R}` → **hammer the `{R}` only** | Phantom Dive costs `{R}{P}` 200. The `{D}` advances neither. (Jet Headbutt `●` 70 still eats it — the strip denies Phantom Dive, not all offence.) |
| Meowth ex with an Energy → **ignore** | Last-Ditch Catch needs no Energy; Tuck Tail is `●●●` for 60. |
| Makuhita, single Energy → **"maybe"** | Corkscrew Punch `{F}` 10 / Confront `{F}{F}` 30 — a real but marginal target. Grades, not gates. |

**None of this is a magnitude on the damage scale.** It is a liveness gate, a redundancy gate, and a
*relevance* read. And it **reproduces the one ruled keep-side frame that both magnitude instruments
get wrong**: on `86091435-68`, step 1 passes (Energy present), step 2 passes (Archaludon ex at 160/300
is not being KO'd), step 3 fires hard (it is the Brief's #1 named threat — *"the wall + payoff… Metal
Defender (MMM) 220"* — and the attached `{M}` is exactly the type that attack needs) → **hammer it**,
which is precisely the 2026-07-19 ruling. With zero magnitude arithmetic, and therefore with no
exchange rate.

## Decision

**1. Deny is a CATEGORICAL RELEVANCE instrument. The Worth Damage Rate is MOOT, not deferred.**
Deny stops asking *"how much damage does this strip prevent?"* and asks *"is this Energy doing
important work for the opponent's plan?"* Because that question is answered without crossing a scale
boundary, no worth↔damage bridge is required for deny and none ships. `common/currency.py`'s guard
test — which fails the moment someone adds `WORTH_DAMAGE_RATE` without a derivation — **stays**, and
its comment gains this ADR as the reason the constant is absent by design rather than pending.

This **withdraws ADR-0078 decision 1's one-backend claim for deny**: deny no longer reads
`needs.opponent_target_value` on any surface. Snipe and gust are untouched by this ADR.

**2. Relevance is DERIVED from card data; the Brief sharpens it but is never required.**
Three legs, per `(body, energy)` pair:

- **(i) Forward potential** — via the existing all-descendants `forward_card_ids` (S1a). Riolu carries
  Mega Lucario ex; Solrock carries nothing. This makes `_DENIAL_FORWARD = 0.5` **central**, reversing
  ADR-0078's re-audit which had it slated for deletion as *"subsumed by the marginal"*.
- **(ii) Typed unlock** — diff the body's affordable attacks with and without *that specific* Energy
  against its typed `Cost`. This is the leg that rules Dragapult's `{R}` in and its `{D}` out, and
  Meowth ex's Energy out.
- **(iii) Ability fuel** — Munkidori's `{D}`. **The data already exists** (decision 2a).

A matched Brief's `threats[]` is a **multiplier** on the derived rank, never its source.

**2a. Ability-fuel needs NO new data — it reads the shipped `CardStat.abilityEnergyTypes`.**
Corrected during this grill: the requirement was mis-reported as unmodelled after a search of
`card_effects.json` / `card_functions.json`, neither of which is where it lives.
`parse_card_ability_energy` (`scouting/card_text.py:267`, ADR-0032) is anchored on exactly Munkidori's
phrasing — `this Pok.mon has (?:any )?\{(\w)\} Energy attached` → `(7,)` for `{D}` — and
`provider.py:438` populates it on **every** `CardStat`. It is already consumed by the attach marginal
via `_attach_fuels_dormant_ability` (Issue #139).

Deny's leg (iii) is that predicate's **mirror**: the attach marginal prices *fuelling a dormant*
Ability, deny prices *muting a live* one. Same field, opposite sign — which is a reason to read the
same source rather than derive a second, per the `_build_standing` / `_affords` one-function-owns-the-
fact lesson. The `Ability Fuel` term in `src/common/CONTEXT.md` covers both readings.

**Why derived rather than Brief-first: the Brief-free fallback ranks the doctrine BACKWARDS.**
`Scout._target_role` classifies `prize_liability` (an *ex* body) > `attacker` (`maxDamage > 0`) >
`support`. Against an unbriefed deck that puts **Meowth ex top** — the body the doctrine says to
ignore — and makes **Riolu and Solrock indistinguishable**, both merely "attacker". Only 8 Briefs
exist and the Kaggle grader is an unknown deck by default. This also puts the knowledge at the seam
ADR-0027 already draws: card facts in card data, opponent *strategy* in Briefs.

**3. Relevance is a SCALAR in [0,1] that scales the incumbent constants — no new scale.**
`relevance(body, energy) ∈ [0,1]`, 0 for dead (the Meowth) to 1 for critical (the `{M}` on
Archaludon ex). Steps 1–2 are hard gates that force it to 0. Then:

| surface | today | under this ADR |
|---|---|---|
| (a) keep price, `needs.deny_slot` | flat `TAG_TIER["gust"]` 10.0, `/2^t` | `10.0 × max_relevance(board)` |
| (b) fire now, `_denial_play_tactical` | `coin_odds × W × opp_denial_best − 10` | `coin_odds × W × K × relevance − _DENIAL_ITEM_COST` |
| (c) which Energy, `_denial_target_tactical` | `W × area_weight × _denial_at(body)` | `argmax relevance` |

A bucketed enum was rejected (alternatives below) for inventing four undetermined constants where the
scalar keeps exactly one — the incumbent, already-tested `10.0`. `K` in the play rung is a **new**
constant standing where `opp_denial_best` supplied magnitude; it **must be pinned to the incumbent's
observed range so the swap starts behaviour-preserving, and recorded as a preservation choice, never
dressed as a derivation** (ADR-0065).

**4. Issue #199 closes as the shared layer REDUCED; the doctrine builds in Issue #187; gust's debt
returns to Issue #189.** ADR-0076 Decision 3 exists to keep *shared* adjudications out of
instrument-scoped issues; the doctrine ruled here is instrument-specific by construction, so the same
principle sends it to the deny issue. Split:

- **#199 lands and closes:** the `PRIZE_DAMAGE_RATE` hoist (kept — promote/retreat, snipe and gust all
  still consume it), the `_strip_delta_terms` seam **repurposed** (decision 5), a per-body bench-snipe
  primitive for step 2, and this ADR.
- **#187 recharters** from *"repoint deny at the shared marginal"* to *"build the relevance
  instrument"*. Its ADR-0078 guard re-audit survives intact where it does not depend on the marginal:
  the `active_can_ko` drop (ADR-0063) becomes step 2, `coin_odds` survives (ADR-0074),
  `_DENIAL_ITEM_COST` survives, `_DENIAL_FORWARD` is promoted rather than deleted.
- **#188 unblocks now.** Snipe reads nothing from the deny doctrine; holding it behind a relevance
  build it never consumes is pure serialisation.
- **#189 re-inherits ADR-0076 Amendment E's currency debt, with Amendment F reversed.**

**5. The merged strip-Δ machinery is REPURPOSED, not reverted.** `Pilot._strip_delta_terms` already
owns the copy-and-mutate seam (`stripped = dict(b)`; no live primitive touched, no caller's dict
mutated) and — load-bearing — the `_DENY_CHARGED` typed-affordability policy, whose own docstring
records *"Only a charged policy prices the per-attack typed affordability a strip actually attacks."*
That **is** relevance leg (ii). What is replaced is the scoring head
(`needs.opponent_target_value` → `relevance`) and `energies[:-1]` (strip-the-LAST → the typed choice
decision 2 requires). The seam, the `_opponent_target_cache` resolution-once-per-decision promise
(ADR-0076 Amendment C), and the no-Energy whiff floor all survive.

**Grill agenda item 3 is REOPENED and answered.** It was closed on the finding that *"no opponent body
in the corpus holds mixed Energy types,"* which made `energies[:-1]` safe and a `max`-over-Energies
dead code. The doctrine is *specifically* about choosing among mixed types (Dragapult `{R}` not `{D}`;
Munkidori `{D}` not `{P}`), so the typed choice is now **required**, not latent. The corpus-emptiness
finding stands as a statement about the corpus, and is exactly why the validating fixtures must be
authored from the doctrine's worked examples rather than harvested.

## Amendment A — what the build changed about decisions 2 and 5 (2026-07-29, Issue #199)

Built the same day this ADR was written. Two decisions did not survive contact with the code exactly
as written, and both are corrected here rather than left to drift.

**Decision 2a was wrong on a fact, and the correction makes the build cheaper.** It claimed the
Ability-fuel requirement was not machine-readable and budgeted a new Effect Clause kind plus a builder
pass. That came from searching `card_effects.json` and `card_functions.json` — neither of which is
where the fact lives. `parse_card_ability_energy` (`scouting/card_text.py`, ADR-0032) is anchored on
exactly Munkidori's phrasing and `provider.py` populates `CardStat.abilityEnergyTypes` on every card;
the attach marginal (Issue #139) has consumed it since. Deny's leg reads the same field. **No new data
pipeline was built, and none was needed.**

**Decision 5's "repurpose the strip-Δ seam" did not happen, because it turned out not to be needed.**
The decision anticipated replacing `_strip_delta_terms`' scoring head while keeping its
copy-and-mutate seam. In the event the relevance read never mutates a body at all — it scores from
`attached_type_counts` plus the line's attack costs — so there was nothing to copy and mutate. What
survives from that machinery is the *policy*, not the code: the typed per-attack affordability reading
`_DENY_CHARGED` exists to express. `_strip_delta_terms` is therefore left intact behind its own
`deny_strip_delta` flag, and retiring it stays Issue #187's call once it has a consumer, exactly as
that flag's note says. A code review flagged this as "rebuilt, not repurposed" and was right on the
facts; the divergence is recorded here rather than argued away.

**One review finding was rejected, with the arithmetic, and it is worth preserving.** The Issue #199
spec asked the typed-unlock leg to be *"a real affordability diff, not a colour-match"*. Implemented
literally, that breaks **two of the five worked rulings**: Meowth ex stops being ignorable (Tuck Tail
is pure-colourless `●●●`, so any lone Energy reads as a setback toward a 60-damage attack), and
Dragapult ex's stray `{D}` becomes a target (the body sits exactly on Phantom Dive's 2-Energy total,
so a total-count rule flags both Energies). The doctrine overrides the spec text, which was written
before the arithmetic was worked. What the objection *did* surface is real and shipped as clause (2),
the **binding count**: a genuinely typed attack such as `{F}●●` on a body holding exactly `{F}` plus
two others really is broken by stripping one of the others. It is guarded on every specific slot
already being covered — which is precisely what keeps Dragapult's `{D}` out, since there the missing
`{P}` means the type binds rather than the count.

**Also settled during the build:**

- The **bench redundancy gate reads REACH, not a snipe rider** — the max of the single-target rider
  and the distributable spread total, since a spread reads *"in any way you like"* and may land
  entirely on one body. Reading only the rider left the gate blind on Dragapult ex, whose Phantom Dive
  is a 6-counter spread — i.e. blind on one of our own three decks. `combat.bench_ko_indices` takes
  the reach; `snipe_ko_prizes` derives from it so the bench Knock Out rule is stated once.
- The **relevance normalizer** is `MAX_ATTACK_DAMAGE = 350`, the largest attack damage in the set,
  recomputed from the CSV by its test rather than pinned. It maps damage into `[0,1]` and is **not**
  an exchange rate.
- The **mute introduces no constant**: `math.nextafter` puts it one representable step above its own
  body's best attack leg, asserting an order without asserting a magnitude.
- **Rainbow-class Special Energy** (Legacy 12, Neo Upper 10, Prism 16) reads untyped and so scores 0
  on the typed leg. This matches how the shipped `combat.attached_type_counts` already treats it —
  consistent rather than a second, divergent reading of the same fact. Recorded as a known gap.

## Consequences

- **Gate 2 is answered "moot", which is a THIRD outcome its charter did not anticipate.** ADR-0078
  allowed pass or fail and named a reduced-scope fallback for failure. The doctrine dissolves the
  question instead, which is strictly better than the fallback — no scope reduction is taken, because
  nothing that needed the rate survives for deny.
- **Gate 1's PASS becomes evidence about a retired instrument.** Its 21/21 behaviour-preservation and
  the `82748422-26` fix were measured on the marginal deny will no longer read. The result is not
  wrong and the probe (`tools/train/probes/deny_gate1.py`) stays as the harness shape the relevance
  instrument's own gate should copy — but it no longer licenses the swap it was built to license.
  *(**Amendment, Issue #243 / ADR-0089, 2026-07-31**: "stays" is no longer literally true — the
  probe was DELETED. A one-shot investigation whose answer is written down is a RULING, and this ADR
  is that record; the script was scaffolding, blind to 40 corpus records, and forced a flag
  (`deny_strip_delta`) that still ships OFF. The **shape** this bullet points at survives here in
  prose, which is what a later gate would copy anyway. Recover the file from git history if it is
  ever wanted verbatim.)*
- **ADR-0078 Amendments B and C keep their standing** — the instantaneous ruling and the
  saturation/`_SURVIVAL_CAP` correction are both preserved *in policy*: `_DENY_CHARGED` survives as
  relevance leg (ii)'s affordability policy. What lapses is only the two-term *form*.
- **A new constant `K` enters the play rung.** Pinned for preservation, not derived — flagged here so
  it cannot later be cited as though it were measured.
- **The five worked examples become the acceptance fixtures**, and they bind for any deck rather than
  only authored ones: `relevance(Riolu,{F}) > relevance(Solrock,{F})`,
  `relevance(Dragapult,{R}) > relevance(Dragapult,{D})`, `relevance(Munkidori,{D}) >
  relevance(Munkidori,{P})`, `relevance(Meowth ex, ·) ≈ 0`, and Makuhita strictly between dead and
  critical.
- **`combat.snipe_ko_prizes` needs a per-body variant.** It returns an aggregate prize count today;
  step 2's bench clause needs to know *which* benched bodies die. This is the build's only genuinely
  new primitive — legs (i)–(iii) all read existing seams (`forward_card_ids`, `_DENY_CHARGED` typed
  affordability, `CardStat.abilityEnergyTypes`).
- **Gust's debt is deferred with its name on it, not solved.** #189 will hit the same underivable-rate
  wall, and it has no escape route of deny's kind — a gust card's value genuinely *is* a magnitude (it
  drags a body into the Active slot). Recorded so that the next grill starts from this rather than
  rediscovering it.
- `needs.deny_slot`'s `oracle_value` parameter, already flagged a misnomer by ADR-0078, is now
  actively wrong and should be renamed with the swap.

## Alternatives rejected

- **Take ADR-0078's recorded reduced-scope fallback** (keep the flat tier, swap only (b)+(c)). The
  honest answer before the doctrine existed, and what this grill was going to recommend. Superseded:
  it leaves deny's keep price on an underived flat tier *and* leaves the `_finish_turn_last` complaint
  live, where the doctrine addresses both.
- **Block #199 on capturing new corrections** until an anchor brackets the rate. The only path to a
  genuine derivation, but it is an unbounded data-collection campaign holding three issues hostage,
  and the doctrine makes the rate unnecessary rather than merely unmeasured.
- **Re-denominate the whole DP into prize-equivalents** to abolish the worth scale. Looks like the
  architectural root fix, and was rejected on the merits rather than on size: it does not dissolve the
  problem, it **multiplies** it — the same underivable bridge would be needed for ~15 tier constants
  (`ROLE_TIER` ×10, `TAG_TIER` ×4, `ENERGY_TIER`, `ACE_SPEC_TIER`) against the same corpus that just
  came back empty.
- **Set the rate to preserve the incumbent** (10.0 ÷ 0.9 ≈ 11.1). Already rejected by ADR-0078; the
  measurement here strengthens that — the anchor cannot even bound it, so a chosen value would have
  *no* evidential contact at all. The `_PRIZE_UNIT = 12` error (wrong by ~8×) is the standing warning.
- **Relevance as an ordered category** (critical / useful / marginal / dead). More legible in traces
  and each worked example pins to a named bucket, but it buys legibility with four new undetermined
  constants where the scalar keeps one existing one — the `_PRIZE_UNIT` shape at smaller scale — and
  ties inside a bucket need a tiebreak regardless.
- **Relevance as a pure boolean gate** on the flat tier. Byte-smallest and no new arithmetic, but it
  provably cannot express two of the five rulings: Riolu-over-Solrock *is* a ranking, and Makuhita's
  "maybe" is explicitly not a yes or a no.
- **Brief-first with the objective-role fallback.** Cheap — both surfaces are already wired — but
  known-wrong on the unbriefed path, which is the grader's default path: it tops the ranking with the
  Meowth ex the doctrine says to ignore.
- **A hand-authored deny table per matchup.** Maximally precise where authored, zero coverage
  everywhere else, and it is `/matchup-genie` work per archetype in perpetuity.
- **Build the whole doctrine in #199.** Inverts ADR-0076 Decision 3 — an instrument-specific build
  sitting in the shared-layer issue — leaves #187 a stub, and keeps #188 blocked behind work it never
  reads.
- **A new issue for the doctrine, closing both #199 and #187.** Cleanest charter, but discards #187's
  grill history and the parts of the ADR-0078 re-audit that survive unchanged.

## Amendment B — the consumer build (2026-07-30, Issue #187)

Issue #187 wired the three deny surfaces onto the read. Three user rulings settled points where this
ADR's decision-3 table is terser than the shipped code, and then **measuring the corpus with the
switch armed exposed three defects that no compute-only test could have caught** — the read was
correct in isolation and wrong at every consumer. That is the case for wiring an instrument before
trusting it, and each finding is recorded here with the arithmetic rather than fixed silently.

### The three rulings (2026-07-30)

1. **The keep price KEEPS its `/2**t` turns-to-ready grade.** Decision 3's table omits it, but this
   ADR never ruled it retired and relevance is deliberately not imminence-gated — it scans forward
   forms precisely so a Riolu's banked `{F}` scores at all. The grade is therefore the only term
   pricing *when* a threat lands. Emitted per body, so each keeps its own deadline.
2. **The target pick DROPS `_DENIAL_BENCH` — a pure `argmax relevance`.** Relevance already prices a
   benched body's slower clock through its own line scan, so discounting again double-counts. The
   constant stays live on the OFF path and inside `_opp_denial_best`, so ADR-0062's derivation is
   unread while armed, not deleted.
   *Scope correction found by measurement:* the ruling covers the TARGET pick only. Applying it to
   the FIRE rung as well deletes the bound ADR-0062 *derived* `_DENIAL_BENCH` from, and ms f21 flips
   to playing the Hammer the human ruled against. Spending the card and choosing its target are two
   decisions; only one of them prices the promotion delay.
3. **`_DENIAL_UNFAVORED` is RE-EXPRESSED, not retired.** ADR-0078 decision 6 retired it on the
   grounds that it and `needs.phase_scale` *"say the same thing multiplicatively"*. **That retirement
   is withdrawn**: under this ADR deny reads `phase_scale` on no surface, so the substitution
   justifying it no longer exists — and `_denial_play_tactical` is Lever A's (ADR-0026) LAST live
   consumer, so retiring it unreplaced would have deleted Lever A from the codebase as a side effect
   of a deny refactor. Its subject moves instead: it now scales `K x relevance` exactly as it scaled
   the damage magnitude. The property is scale-invariant, which is why
   `test_the_unfavored_read_scales_the_denial_and_can_never_flip_its_sign` holds verbatim against
   both instruments — and that invariance is the evidence the f17 discipline survived.

### Finding A — the FIRE rung must price only what the opponent can afford NOW

Full relevance credits banked potential on purpose (*"Dragapult ex holding `{D}` + `{R}` cannot
afford Phantom Dive yet, and the `{R}` is still the Energy worth taking"*). Correct for deciding
whether a Hammer is worth KEEPING, and wrong for deciding whether to SPEND one: it fires at a threat
that has not arrived. On ms f21/f29 — the **same board**, ruled `[7]` and `[10]`, both against the
Hammer — a benched Dragapult ex holds one `{R}`; Phantom Dive `{R}{P}` needs two.

So `strip_relevance` now also reports `affordable_setback` / `affordable_relevance`, the same scan
restricted to attacks the body can pay for as it stands, and the fire rung reads that while the keep
price and target pick keep the full read. The mute rides with the affordable half: switching off a
live Ability takes effect immediately, so it is never potential.

### Finding B — the binding count was unreachable for pure-colourless costs

`if not need: continue` skipped colourless attacks before clause (2) could evaluate, so every `●●●`
nuke read as a whiff. That re-introduced the exact defect ADR-0062 was written to fix — *"a benched
Mega Starmie ex sitting on 3 Energy unmolested"* (ms f26). The clause now fires on a colourless cost
when `total_attached == total_cost`, which is what separates the two cases the doctrine rules
opposite ways: Mega Starmie ex on 3 `{W}` against Nebula Beam `●●●` 210 is **relevant** (the strip
drops it under), while Meowth ex on 1 against Tuck Tail `●●●` is **not** (it could not attack before
the strip either — the doctrine's flat *"ignore it"*). The equality is doing the work, not the
colourlessness.

### Finding C — the Brief sharpener must not reach the FIRE reading

Decision 2 makes a matched Brief a multiplier on the derived **rank**. Applied to the fire reading it
becomes an override, because that reading alone is compared against `_DENIAL_ITEM_COST`: the 1.25x
boost turns f21's `-1.25` into `+0.94` and plays the Hammer, on a board where the only thing that
changed is that the body is Brief-named. That is the f17 ruling restated for a new booster — *a
booster must scale the oracle, never override it* — so the sharpener is scoped to the rank and the
keep price.

### `_DENY_RELEVANCE_K` is DERIVED, not pinned

Decision 3 called for a new constant *"pinned to the incumbent's observed range and recorded as a
preservation choice, never dressed as a derivation."* Measurement produced something better: since
relevance is `setback / MAX_ATTACK_DAMAGE`, setting `K = MAX_ATTACK_DAMAGE` makes `K x relevance` the
setback **damage**, so the armed fire rung prices in the incumbent's own units and is a strict
generalisation of it rather than a re-scaling. There is no free parameter, and `pilot.py` imports the
normalizer rather than copying its value so a future set re-deriving it from the CSV carries K along.

The identity is what makes the two instruments agree: on f21/f29 both price **exactly `-1.25`**, the
figure ADR-0062 derived `_DENIAL_BENCH` from and ADR-0082 Amendment A re-verified. They diverge only
upward, where relevance sees a setback `_denial_at` cannot — f12 `+55.00` vs `+22.50`, f26 `+16.25`
vs `+1.25`: same sign, same decision, strictly better informed. An earlier pin of `K = 140` (the
largest observed `opp_denial_best`) priced f21 at `-6.50` — still a hold, but no longer the
incumbent's number, and it lost f12 outright.

### Measured result

With `deny_relevance` armed, **every Hammer-bearing frame in the corrections corpus reproduces the
OFF decision** — 12 frames, 0 changed, so the deny 5/5 holds. Kill-switch OFF is byte-identical and
the OFF path is pinned against the documented arithmetic recomputed independently
(`test_off_reproduces_the_documented_incumbent_arithmetic_exactly`), because asserting OFF == OFF
would be vacuous.

### Two corrections to Issue #187's own spec

- **`relevance_energy` cannot be matched against an engine option.** The spec assumed a positional
  match. It indexes `energies` — what the attached cards PROVIDE
  (`cgpy.options.provided_energy`, one entry per unit, so an Ignition Energy contributes three) —
  while a `DISCARD_ENERGY` option's `energyIndex` indexes the attached **cards**. The two coincide
  only on a body holding nothing but single-unit Basic Energy. Rows therefore also carry
  `relevance_by_type`, and surface (c) keys off the option's Provider-resolved TYPE, which is what
  relevance is actually a function of. `relevance_energy` stays as diagnosis.
- **The Issue #199 layer was NOT consumed unchanged**, as the spec claimed. Findings A–C are all
  changes to the read or its plumbing.

### Known limitation, unchanged

A rainbow-class Special Energy still reads untyped and returns the blank record before either clause,
so a `●●●` body paying with one scores 0 even at `total_attached == total_cost`. Consistent with how
`combat.attached_type_counts` already treats it, and recorded rather than fixed.
