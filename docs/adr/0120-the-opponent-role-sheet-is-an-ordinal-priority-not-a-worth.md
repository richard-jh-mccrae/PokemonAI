# ADR-0120 - The opponent role sheet is an ORDINAL PRIORITY, not a worth — and it did not measure

**Status:** Accepted (design session on Issue #395, 2026-08-05); BUILT. **Amends ADR-0051** (its role
table becomes a declared registry and gains four members) and **supersedes
`docs/plans/gusting-keepcost-design.md` §2**, which designed the same sheet as a *worth*. Also
completes `docs/card-functions.md`'s tag reference, which claimed to be the full vocabulary while
ten shipped tags had no row — now asserted both ways against `TAG_REGISTRY`. Does **not**
discharge ADR-0101's parked hand-disruption prerequisite — see Decision 7, which is the point of this
ADR a later reader is most likely to get wrong.

## Context

The agent could not see *why* an opponent's Pokémon mattered beyond its prize count and how fast it
kills us. Roles and Function Tags reach the **steering** layer — snipe and gust priority, threat
rank, the damage oracle — and never the prize-denominated `opponent_target_value` currency. Nobody
wrote that split down and nothing enforced it, and three defects had grown in the gap. All three were
measured from shipped data, are reproducible offline, and are independent of each other.

**Fact 1 — the largest role population in the scouting artifact was inert.** `artifact.json` assigns
`attacker` to **530** opponent bodies across 122 archetypes. `matchup_plan.role_priority` was
`_ROLE_PRIORITY.get(role or "", 0)` and `attacker` was not in the table, so every one of those
assignments resolved to 0 with **no error, no log and no test**. `Scout._target_role` emits two more
(`support`, `unknown`) that were equally absent. *Positive control:* the same walk reported
`fragile_preevo` (221), `primary_attacker` (182) and `engine` (46) as consumed, so the instrument
distinguished the two cases.

**Fact 2 — the `avoid` −80 steer was firing on the opposite card class.** `pilot._draw_engine_ids`
forced `avoid` on any in-play opponent body carrying the `draw` tag:

```
Mega Kangaskhan ex   756   300 HP   3 prizes   draw, stall, dig:2   -> forced to avoid −80
Fezandipiti ex       140   210 HP   2 prizes   draw                 -> forced to avoid −80
Dudunsparce           66   140 HP   1 prize    draw, stall, dig:3   -> avoid −80  (correct)
Meowth ex           1071   170 HP   2 prizes   search, supporter_tutor -> escapes (no `draw`)
```

Its provenance is `_GENERAL`, so it fired **unscaled by γ** — full strength against an opponent we
had not recognised — and `build_matchup_plan` writes that tier **after** Read-Intel, so it
**overwrote** the `primary_attacker` the dossier had correctly assigned. Every existing test of the
rule passed card id 66, the one card where it is correct, and the derivation had **no direct test at
all**. The developer's ruling: *"Prize math must be a part of the equation. If they have a wall and
draw engine like Mega Kangaskhan, and we can KO it, that's 3 prize cards… a key strategy of the
Dragapult deck with its 4 Boss's Orders is to place a single damage counter on Fezandipiti ex,
reducing its HP to 200, then next turn gust it up for a KO and match victory."*

**Fact 3 — a documented command silently deleted 11 hand-authored tag instances.** Eleven tag
instances lived in `src/common/card_functions.json` and in **neither** the prober's derived set
**nor** `tools/meta_tracker/function_overrides.json`, so `python tools/build_card_functions.py
--fresh` deleted all eleven: `--fresh` sets `prior = {}` and the monotonic accumulate union was the
only thing preserving them. One was `prevent_ex_damage` on **345 Crustle** — the damage oracle's
ex-immunity read, `_body_threat_rank`'s `+500` and snipe relevance's `prevents_my_ex` leg, all three
lost in one command with nothing red. CI could not see it: `test_card_functions_oracle.py` asserted
**overrides ⊆ table** and only that direction, and `function_audit._CUES` is a 17-tag whitelist that
*exempts* unknown vocabulary — the exact inversion of `snapshot_coverage.undeclared_clauses`. 25 of
42 shipped tags were audited by nothing.

The worked example the three converge on is the shipped archetype **Crustle / Mega Kangaskhan ex**,
which no Brief covers, so it runs on dossier roles alone: both Crustle and Mega Kangaskhan ex were
labelled `attacker` and scored 0, and the general `draw` rule then forced the 3-prize Mega to
`avoid`. The developer's correction is what the card facts say: *"Crustle IS their main attacker
specifically because it resists ex Pokémon's attacks, which near every other deck uses as its main.
Mega Kangaskhan is a wall and draw engine, NOT the main attacker."*

## Decisions

### 1. The sheet is an ORDINAL PRIORITY beside `_ROLE_PRIORITY`. It does not enter `card_worth.ROLE_TIER`.

**Forced by a shipped test, not chosen.** `tests/strategy/test_needs.py` runs `for role in ROLE_TIER:
assert needs.SUPPLIES.get(role)`, and every member of `needs.SLOT_KINDS` is a hand-or-board need **of
ours**. An opponent role there turns CI red with no honest slot to name.

Two supports stand independently. The two tables already collide on `engine` (`ROLE_TIER` 12.0 = *a
plan piece worth keeping*, against `_ROLE_PRIORITY` 0 = *do not boost*), so reusing either as the
other's sheet would make that disagreement silent. And ADR-0118/0119 measured that at this seam the
ordering is decided by **which** bodies carry a signal, not by how much — an arm carrying ~20×
another's magnitude bought 1.26× the movement.

**Consequence, verified rather than assumed:** `needs.TARGET_VALUE_CEILING` (3.9) and both rates
derived from it (`state_value._THREAT_W`, `currency.GUST_TARGET_WORTH_RATE`) are unchanged, and are
pinned by a test that also asserts they are still *derived from* the ceiling rather than re-authored
beside it. `tests/strategy/test_leaf_profile.py`'s `STATE_VALUE_PROFILE` and
`test_value_stack_integration.py`'s `CONSUMED` stayed green, which is the standing signal that the
implementation did not drift into a worth.

### 2. One closed role vocabulary, walked off the shipped artifacts.

`ROLE_REGISTRY` declares each legal role's priority, a prose reason, and which STORES may assign it;
`_ROLE_PRIORITY` survives as a **derived view** of it so the numbers have one home. The
mechanism is copied from the effects layer, which is the sibling that already does this correctly:
**declare** → **walk the artifact, never a hand-kept list** (`roles_in_dossiers` / `roles_in_brief`,
which live in the module because *a vocabulary the audit forgets to visit is an audit that passes by
not looking*) → **`undeclared_roles` as the teeth** → **assert with a vacuity guard and a positive
control on the same run**.

Two validators that existed and never ran are folded in: `brief.schema.json` declared the role enum
and nothing in `src/` or `tests/` loaded it, and `validate_brief.py` genuinely enforces it but had no
automated caller — so a hand-edited Brief with a typo'd role shipped green. A test now asserts the
schema's enum equals the registry's BRIEF-assignable half.

**The assigners are three, not two, and a review caught why that matters.** Collapsing the Read and
the Brief into one `matchup` name — mirroring the γ provenance, which really is binary — made
`support` and `unknown` legal in `brief.schema.json`, so a hand-authored Brief could declare
`role: "unknown"`. That is precisely the case the field exists to constrain. Provenance answers *does
γ scale it?* and is a property of an ASSIGNMENT; `assigners` answers *may this store say it?* and is
a property of the ROLE. Two questions, two vocabularies, and the walk now checks each store against
its own permission.

### 3 + 4. The table, and the `avoid` prize gate.

| role | priority | change | reason |
|---|---|---|---|
| `primary_attacker` | 100 | — | the wincon body itself |
| `fragile_preevo` | 90 | — | its pre-evolution — deny the wincon before it comes online |
| `disruption_target` | 60 | — | Brief-curated "remove this"; an explicit human claim outranks a derived one |
| **`attacker`** | **50** | **NEW** | 530 shipped dossier assignments stop resolving to 0 |
| **`enabler`** | **40** | **NEW** | assists the key Pokémon in *how* it attacks (Solrock/Lunatone shape) |
| `engine` | 0 | — | plain accelerant — neutral |
| **`support`** | **0** | **NEW (declare)** | emitted by `Scout._target_role`; no claim, but silence must be a ruling. READ-ONLY — not Brief-assignable |
| **`unknown`** | **0** | **NEW (declare)** | same, and read-only for the same reason |
| `avoid` | −80 | **GATED** | applies only when `prize_value == 1`, off `CombatMath.prize_value` — no new constant |

The **order** is the load-bearing part per Decision 1 and is asserted directly; the magnitudes are
authored and a later measurement may re-rule them without re-ruling the order.

### 5. The derived tier is a pure function, and one of its rules is deliberately narrower than the spec.

The general tier stops being one hard-coded rule and becomes `derive_general_roles(facts)`, pure over
`BodyFacts` the Pilot supplies — matching `build_matchup_plan`'s existing contract, and what keeps
the `avoid` gate testable at the scouting seam instead of stranding it at the Pilot. **Every input
already shipped**, which was the finding rather than the proposal: `CombatMath.prize_value`, the two
damage ceilings `_threat_damage_pair` already computes, and three parsed `CardStat` fields
(`damageBoost`, `retreatFreeGrant`, `abilityEnergyTypes`) that make `enabler` derivable with **no new
Function Tag**.

First match wins, and the order is itself the ruling: `avoid` → `primary_attacker` → `fragile_preevo`
→ `attacker` → `enabler` → `engine`. `avoid` is first because a utility body's incidental attack does
not make it an attacker — Dudunsparce hits for 90 and is still not what removal is for.

**One deliberate divergence from the issue's D5 table, recorded because it changes behaviour.** D5
wrote `avoid = engine ∧ prize_value == 1` over `_ENGINE_TAGS`. Taken literally that puts −80 on a
1-prize `energy_accel` body — on **Cinderace, a deck's main attacker** — and tells the agent never to
spend removal there. `strategy/context.py` had already ruled that exact distinction for the
mirror-image question (`_UTILITY_TAGS` excludes `energy_accel` *"because such a body accelerates BY
attacking"*), so the gate reads the set carrying the ruling. `engine` keeps `_ENGINE_TAGS`, so only
the −80 is narrowed. Both sets are imported from their one home rather than restated.

**Two claims in the spec that verification did not support, recorded rather than inherited.**
First, D5's table cited `engine` as `{draw, energy_accel, search, dig, supporter_tutor} & tags`
*"already ships as `context.py:168 _ENGINE_TAGS`"* — false: `_ENGINE_TAGS` is a four-set and
`supporter_tutor` lives in `_UTILITY_TAGS` one line below. The implementation reads the real
`_ENGINE_TAGS`, and no shipped card carries `supporter_tutor` without `search`, so the behavioural
impact is nil — but the spec's cited source did not say what it claimed. Second, *"the 530
assignments are live"* over-states: what changed is that the string now resolves to a real priority
instead of falling through `.get(role, 0)`. For a body IN PLAY the derived tier usually names it too
and, being γ-independent, supersedes the dossier's claim; the dossier's 530 remain the live reading
for the predicted entries the derivation cannot see. Both are corrections of the same defect, and
the precise statement is the one in `ROLE_REGISTRY["attacker"]`.

`primary_attacker` derived from `prize_value >= 2` **over-claims on a 2-prize support ex** — the
matchup-genie playbook's *"`primary_attacker` means THE WINCON, not any fat multi-prize body"*. That is
accepted rather than papered over: `Scout._target_role` already derives exactly this from
`is_ex_body`, so it is precedent rather than invention, and correcting it is the curated Brief's job.
That is the derive-first / Brief-corrects split the tier order already encodes.

### 6. The consumer is a new row field; `value` is untouched.

`_opponent_target_rows` gains `role_priority` beside `prize_advance` / `survival_shift` / `value`,
exactly as `_relevance_terms` and `_strip_delta_terms` attach their legs. `row["value"]` keeps its
prize+clock meaning and its ceiling. A fused scalar would erase what the architecture already gets
right — gust, snipe and deny ask different questions of the same body and each already weighs the
steering layer differently.

The Crustle composition needs **no new gating**, and that is stated because it is the thing most
likely to be "fixed" unnecessarily: role priority raises Crustle as a removal target, the gust
doctrine's existing KO oracle refuses a gust-to-KO because `predicted_damage` reads
`prevent_ex_damage` and returns 0, and the deny/strip path picks it up instead.

### 7. What this does NOT discharge.

`sound_rules.py`'s `firing-equation-constants.reconciliation` and its mirror in `pilot.py` both said
`_REFRESH_OPPONENT_HAND_STRIP` / `_GIFT` *"retire when `gusting-keepcost-design.md` §2's shared
opponent role sheet exists, not before."* **That sheet now exists and the prerequisite is still
UNMET.** Grading those rates needs a **worth over cards we cannot see** — an expectation across their
representative build. This is an **ordinal priority over bodies in play**. Different quantities; the
second does not arrive by citing the first, and `card_worth.role_value` is untouched, so the 59.4%
figure that is the actual reason is unchanged.

Both copies were rewritten **in the same commit**, and the condition is restated as the *quantity*
rather than the *artifact*, so the next reader cannot read "the sheet exists now" as the condition
having been met. Nothing in `validate()` catches this — the claim is free text and the doc
cross-check parses only the id column — so it was a checklist item, not a CI-caught one.

Separately, `firing-equation-constants.entry` now names `scouting.matchup_plan._ROLE_PRIORITY`. It
was an authored magnitude table inside an equation whose shape is right, covered by no whitelist row
at all, and that gap predates this issue. It **extends the existing entry** rather than opening a new
one: a new entry would need its own non-empty reconciliation, and reusing this row's `fact=` string
turns `undeclared_double_guarding()` red while cosmetically differentiating it makes that detector
pass **vacuously**, which is worse.

### 8. The measurement — and it is a NULL result.

`tools/train/probes/role_sheet_sweep.py`, with D8's three corrections each earned by a past failure
on this seam: the arm patch sits at `MatchupPlan.priority` so the OFF arm turns the sheet off *inside
`doctrine_gust` too* (a rows-only sweep would have compared a seam with no role signal against one
with a signal while the layer above already had one); the shams are **sparsity-matched** per
ADR-0118's amendment; and the tie population is counted on the field the ranking sorts, with the
`row["value"]` population printed beside it rather than in place of it.

```
frames posing a 2+ body gust menu   : 247        (of 372 replayable corrections)
opponent bench bodies ranked        : 832
  ...carrying ANY role              : 832  (100.0%)
  ...whose GUST SCORE it moved      : 321  (38.6%)   <- the real sparsity
Flat Ties (equal-prize groups, on the SORTED field)
  OFF  237 groups   tied on gust score 112 (47.3%)   tied on row value 100 (42.2%)
  ON   237 groups   tied on gust score 111 (46.8%)   tied on row value 100 (42.2%)
sham band (ON's own max effect): 0.400000

arm                          bench argmax moved
role sheet                     5/247  ( 2.0%)
sham cid%7    [sparsity]       7/247  ( 2.8%)
sham hp%70    [sparsity]       8/247  ( 3.2%)
sham position [sparsity]      29/247  (11.7%)
```

**The sheet loses to every sparsity-matched sham, including position — the floor.** It broke ONE
Flat Tie group out of 237. The probe's pre-registration predicted it *should* clear its shams; it did
not, and **the prediction is left standing in the docstring rather than edited into agreement with
the result** — the discipline `line_prize_sweep.py` recorded after its own prediction failed.

**So the decision is justified by the defects it closes and NOT by discrimination, and the question
is left OPEN.** This is deliberately the same shape ADR-0119 used. What the number does *not* say is
that the sheet is wrong: ADR-0118's own reading note records that a leg well below its sham has not
thereby been falsified, and 61.4% of the candidates here are bodies the KO oracle refuses in **both**
arms, where the sheet is silent by design (Decision 6). What it does say is that nobody may cite this
change as evidence that role ordering moves gust decisions.

**The commits are not all justified the same way, and this ADR keeps them apart.** Commits 1–2 (the
tag store and the role vocabulary) stand on Facts 1–3: eleven tag instances a documented command
deletes, 530 assignments resolving to 0, a −80 steer landing on 2- and 3-prize bodies. None of them
needs an argmax sweep and none of them is supported by the table above. Only commit 3 rests on the
measurement, and the measurement did not support it.

### 9. One real bug the widening exposed, fixed rather than deferred.

Widening the tier put a positive role on nearly every in-play body, and the suite went red: the
benched-Tera **structural** snipe veto lifted off `-KO_SCORE` to −999.5. Cause — the Brief Tiebreak
read the raw `MatchupPlan` priority while the relevance MULTIPLIER stands a positive one down through
`TheirPlanInputs.brief_boost_gated()`, whose own docstring already names *"the three gates a later leg
would have to remember to add itself to"*. The tiebreak was that later leg and had not added itself,
so a body that takes **no damage from attacks at all** could be ordered above one that can hold the
counters. Latent before this issue (a Brief could always have named a Tera) and reached daily by the
widening. `_snipe_brief_priority` now applies the same gate for the candidate and its peers off one
ctx per peer, so the two readings cannot drift. The negative (`avoid`) side is deliberately not gated:
a booster must scale the oracle, a de-prioritizer may always apply.

### 10. The tag store, as a contract.

`src/common/card_tags.py` gives the Function Tag store the treatment its sibling effects layer
already had: `TAG_REGISTRY` (tag → source, prose reason, consuming modules), `PARAMETRIC_PREFIXES`,
the `tag_vocabulary` walk, and two sets of teeth — `undeclared_tags` (nothing shipped is undeclared)
and `unsourced_tag_instances` (**every shipped instance is reachable by a rebuild**, i.e. `--fresh`
is lossless). The second was RED. `DERIVED_TAGS` is **exported from the classifier** and passed in
rather than re-transcribed, which is both the drift check and what keeps `src/` free of `tools/`.

Ten of the eleven orphans moved into `function_overrides.json` — the only store upstream of the
accumulate step, so the only one `--fresh` cannot drop — each re-verified against
`data/EN_Card_Data.csv`. The eleventh, `hand_size_attacker` on 743 Alakazam, is ruled a genuine
leftover and **deleted rather than adopted**: both consumers went with ADR-0102/Issue #261 item 2c
and no `src/` module reads the string. A tag declared with no consumer is asserted to be read by
nothing, so an "authored ahead of its consumer" label cannot go stale.

The writer moves to `write_bytes` through one `shipped_bytes` function, and the shipped store is
re-emitted through it. That re-emission is an 897/900-line diff and the reason is stated rather than
buried: the store shipped `indent=1` and STRING-sorted while the builder emitted `indent=0` and
INT-sorted, so the next rebuild already reformatted all 275 entries and a one-tag change would have
arrived hidden inside a 275-line diff. Fixing only the line endings would have fixed a smaller
version of the same defect. A test asserts the committed bytes still equal the writer's output.

## Consequences

- The role vocabulary and the tag vocabulary are both closed, walked off the shipped artifacts, and
  bitten by tests carrying vacuity guards and positive controls. A new role string or a new tag now
  fails loudly instead of pricing 0.
- `--fresh` is provably lossless, pinned by a test, and `prevent_ex_damage` on Crustle is pinned by
  name and asserted *reachable*, not merely present.
- 530 `attacker` assignments are live; `avoid` no longer fires on a 2- or 3-prize body.
- **No claim is made that any of this moves a gust decision.** Decision 8 is the record.
- Issue #392's deferred-target ranker can consume `row["role_priority"]`; wiring it is that issue's.
- Out of scope and stated so they are not silently absorbed: the 15 unwired `opponent_properties`
  keys, the Briefs' dropped `why` rationales, retiring the hand-disruption rates (Decision 7), and
  `card_worth.role_value` itself (Decision 1).
