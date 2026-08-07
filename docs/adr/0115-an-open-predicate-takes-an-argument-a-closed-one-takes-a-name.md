# ADR-0115 — A scaler predicate that is OPEN takes an argument; one that is CLOSED keeps its flat name

**Status:** Accepted (developer-ruled 2026-08-03 on Issue #361 — *"GROW THE VOCABULARY: a
filtered-count family"*). Build: Issue #361. **Extends ADR-0083 §4 and supersedes, for open
predicates only, the flat-names-only reading that Issue #225 / POC-T1 recorded in
`src/common/CONTEXT.md`.** It does not overturn ADR-0032's Damage Formula shape
(`base + per_unit × count(variable)`), ADR-0083 §2's measurement rule, or ADR-0108's provenance
contract — all three are honoured below.

**Number is a rebase artifact.** Drafted as `ADR-0115` per `docs/adr/README.md`'s "claim nothing,
cite the issue, renumber at rebase"; `/open-pr` finalizes it. **Cite it as Issue #361.**

**Context issues:** Issue #361 (this ruling and build), Issue #225 / POC-T1 (the flattening decision
this qualifies), Issue #213 / ADR-0083 (the vocabulary rules), Issue #355 (the forward guard that
stopped this class being created again), Issue #364 (owns the measurement debt this ships),
ADR-0032, ADR-0108.

## Context

Two shipped `unaudited` overrides froze a per-unit attack as a flat constant:

| attack | card | printed text (`data/EN_Card_Data.csv`; `src/cgpy/defs/attack_data.json` says `damage: 0`) | shipped |
|---|---|---|---|
| 651 | 462 Team Rocket's Weezing | *"This attack does 40 damage for each Pokémon in play that has "Koffing" or "Weezing" in its name (both yours and your opponent's)."* | `{"damage": 80}` |
| 708 | 501 Palpitoad | *"This attack does 40 damage for each of your Pokémon in play that has the Round attack."* | `{"damage": 80}` |

Both print 0, so the override was the *only* source of the number, and 80 is 40 × 2 — one board's
count, frozen. On the common board where the attacker is the single matching Pokémon the engine
deals 40 and the oracle promised 80. That is `over_prediction`, the soundness class
`tools/sim/ci_audit_gate.py` exists to fail; it was invisible only because neither attack sits on
`_GATE_ATTACKS`. Worse than the magnitude: the entries carried **no `scaleVar` at all**, so nothing
downstream could tell the number was board-dependent.

Issue #355's `_fixed_damage` now refuses to CREATE another entry of this class (a printed-0 attack
whose own sentence says "for each"). By design it does not retract the two already shipped — the
generator may not silently retract what it did not author.

**The reason this needed a ruling rather than a patch.** `src/common/strategy/damage_context.py`
carried this, verbatim, above its three filtered counts:

> the two FILTERED counts (Issue #225, POC-T1) — a predicate over a zone rather than the zone's size,
> **carrying flat names because the vocabulary deliberately did NOT grow a filtered-count FORM to
> hold them** (`src/common/CONTEXT.md`)

`atk_bench_stage2`, `def_ex_in_play` and `def_counters_all` are predicates flattened into atoms **on
purpose**. Fixing 651 and 708 the same way means shipping `both_in_play_koffing_weezing` — which is
not a vocabulary, it is a card list wearing one.

## Decision

### 1. The split is CLOSED vs OPEN, and Issue #225's flattening governs only the closed half

A filtered count's predicate is **closed** when its argument set is finite and engine-known: a stage
(`atk_bench_stage2`), a rule box (`def_ex_in_play`), a damage counter (`def_counters_all`). A flat
name states such a predicate *in full*, and the context can pre-reduce it to an integer. Issue #225's
decision stands unchanged for these.

A predicate is **open** when its argument is arbitrary: a name substring ("Koffing", "Weezing") or an
attack name ("Round"). Flattening an open predicate does not name a fact — it hardcodes a card list
into the vocabulary, and the next card with the *same text* needs a new variable *name* rather than a
new argument. ADR-0083 §4's own test for growing a class is that "the very next candidate has the
same shape", and here it demonstrably does: the pool already holds four `Round` attacks (707, 708,
710, 1214) differing only in per-unit.

So the vocabulary grows a **filtered-count FORM** with exactly two members today:

* `both_in_play_named` — Pokémon in play on **either** side whose card name CONTAINS any filter term.
* `atk_in_play_with_attack` — the **attacker's** in-play bodies HAVING an attack of that name.

`both_` is the direction class ADR-0083 §4 already opened, so 651 needed no new direction machinery.
"In play" is Active **and** Bench (`gs.in_play`), which is a different zone from the `"on your Bench"`
predicate `atk_bench_names` feeds — a lone Team Rocket's Weezing in the Active spot counts itself,
which is precisely why the one-match board reads 40 and not 0.

### 2. Mechanism: the ARGUMENT rides on the AttackStat; the context supplies raw material (option A)

`scaleVar` names the **family**. A new `AttackStat.scaleFilter` carries the predicate's argument. The
context supplies raw material — `both_in_play_names` (a name per in-play body, both seats) and
`atk_in_play_attack_names` (one tuple of attack names **per body**, attacker only) — and
`strategy/damage.py` reduces it at lookup with the attack's own filter, in a branch beside the
existing `atk_discard_energy` exception.

**Why this and not a mapping in the context (option B).** B — `both_in_play_named` maps filter →
count — was priced and rejected on evidence, not taste. `damage_context()` is built once per
direction from two `SideFacts` records and serves *every* attack evaluated against that board. The
filter lives on the **attack**, so the builder would have to enumerate every filter any attack might
ask for. It cannot: it has never seen the attack. The only ways out are to build the context
per-attack (which destroys the one-dict-per-direction memoization and the two-supplier parity test
that pins it key-for-key) or to pre-compute a map over every name substring in the pool (a card list
in the context instead of in the vocabulary — the same defect one layer down).

**Why a parameter is not the mini-language ADR-0083 §4 rejected.** §4 rejected letting `scaleVar`
hold an *expression* (`"atk_bench+def_bench"`), because that turns a closed vocabulary of named facts
into an evaluator inside the damage oracle. There is no expression here and no evaluator: the family
vocabulary stays closed and finite (two members, both listed in `_FILTERED_COUNTS`), and `scaleFilter`
is DATA a named family reads. That is the shape `scaleEnergyType` has given `atk_discard_energy` since
ADR-0032 — *"the single documented exception to 'every variable name IS a context key'"*
(`damage_context.py`, special-cased in `strategy/damage.py` ahead of the generic
`context[attack.scaleVar]` path). **This ruling turns that one exception into a class of three.** The
engine side had already reached the same shape independently and earlier: `scale_count` takes an
`energy_type` beside the var name, and `attack_damage` reads `scale["attackName"]` for
`atk_named_attack`.

### 3. Engine and agent must AGREE on the value; they need not agree on the spelling

`src/cgpy/damage.py` learns `both_in_play_named` (beside its existing `atk_named_attack`), and
`chain_overrides.json` un-defers `attack:651`, which the generated layer had parked as *"unparsed
effect text"* — so cgpy raised `UnsupportedCard` on the very attack the agent was pricing at 80.

708 needed **no** engine work: `generated_chains.json` has priced it `atk_named_attack`/40 all along.
That is independent corroboration of the printed reading, and it is also the reason the two
vocabularies are not unified here. They have always differed in spelling — `all_bench` vs
`both_bench`, `atk_discard_basic_energy` vs `atk_discard_energy` — and renaming the engine's member
would move the shipped ChainDefs for 707/710/1214 too, which this issue is not about. The contract
between them is the **value**: `tests/parity/test_damage_goldens.py` drives both implementations over
the same hand-built board and asserts equality at counts 1 through 4.

### 4. The two rows move to `text_verified`, owned by Issue #364

REQ-PROV-0004's `unaudited` set shrinks by two, which is the intended debt-paydown direction, and
REQ-PROV-0008's contradiction halt does not apply (it is scoped to `text_verified` rulings and to a
narrower `engine_fit`, deliberately — overwriting an `unaudited` value with a fresh reading is the
paydown path). They cannot be `engine_fit`: **no audit sweep axis varies WHICH cards are in play**,
only how many — bench fodder is chosen by HP rank — so the count is pinned at 1 across every point the
harness can produce, and a flat axis at one point cannot name a slope. Issue #364 owns building the
card-identity axis.

## Consequences

- **One shipped damage number moved, in the sound direction.** 651 and 708 fall from a flat 80 to
  `40 × count`, which is 40 on the common board. Any Discrimination/Decision Gate flip is recorded in
  `docs/archive/plans/issue-361-wave3-packet.md`, never conformed.
- **The three closed filtered counts are NOT migrated.** They could be, later; doing it here would
  move the oracle for attacks this ruling never examined. `tests/strategy/test_visible_state_scalers.py`
  is the test that says so.
- **Three sibling `Round` attacks stay under-read.** 707 (Tympole, 20×), 710 (Seismitoad, 70×) and
  1214 (Wigglytuff, 40×) print 0 and carry no override, so the agent prices them at 0 while the
  engine prices them correctly. That is an under-read (sound) rather than the over-read this ruling
  fixed, and shipping them would add three new override entries and three more moved numbers to one
  gate-attribution window. Recorded, not silently left: **Issue #365** owns them.
- **`AttackStat` gains a `name` field.** `atk_in_play_with_attack` names an attack, so the context
  cannot describe a body's attacks without it.
- **Every leaf now pays for material only two attacks in the pool consume.** `damage_context` is ONE
  dict built per direction rather than one per attack (the property `tests/strategy/
  test_damage_context.py` pins), so raw material is gathered whether or not a consumer is on the
  board. Measured as an interleaved, paired in-process A/B — fields live vs neutered, 40 correction
  frames: **+13.7 µs median on `damage_context` both directions (+18.8 %)** and **+29.7 µs median on
  the whole leaf `StateModel.build` + `state_value` (+3.3 %)**. Accepted and recorded in
  `tests/strategy/test_leaf_profile.py`'s `STATE_VALUE_PROFILE`, whose tripwire is what forced the
  measurement; it is roughly two orders below the largest delta this path has already accepted
  (+1.75 ms, Issue #261 item 2d) and ~4 orders below the per-match budget.
- **The `unaudited` debt shrinks from 111 to 109.**

## Alternatives rejected

- **Drop both entries** so the oracle reads the printed 0 and they join the gap ledger. Sound (an
  under-read never manufactures a phantom lethal) and by far the smallest diff. Explicitly ruled
  against by the developer: an attack the oracle says deals nothing is an attack no line ever
  considers — the same blind spot Issue #225 refused to leave 425 in.
- **Flatten anyway** (`both_in_play_koffing_weezing`, `atk_in_play_round`). Preserves "every variable
  name IS a context key" perfectly. Rejected in §1: it puts a card list in the vocabulary, and the
  next card with identical text needs a new name rather than a new argument.
- **Option B, a filter→count mapping in the context.** Rejected in §2 — the builder cannot know a
  filter that lives on an attack it has never seen.
- **An expression in `scaleVar`.** Already rejected by ADR-0083 §4 and not re-opened; §2 states why a
  named family plus a data argument is not one.
- **Rename the engine's `atk_named_attack` to match the agent.** Rejected in §3: it would move the
  shipped ChainDefs of three attacks outside this issue's scope, and value parity — which is what
  actually protects against drift — is asserted directly.
- **Widen `ci_audit_gate.py`'s `_GATE_ATTACKS` to cover 651/708.** Recorded as out of scope by
  Issue #275 and left there; the gate's runtime budget is a separate question from this ruling.
