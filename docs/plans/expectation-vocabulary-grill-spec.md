# Expectation-node vocabulary widening — grill + implementation spec (Issue #394, POC-T4/2b)

**Status:** ready to implement. Every number below is MEASURED on the 377 committed native traces
(`tests/fixtures/parity/`); every card fact is quoted from the engine's own `all_card_data()` dump
(`tools/meta_tracker/cards.json`) or the engine chain definitions (`src/cgpy/defs/`). Nothing here is
recalled.

---

## 0. The instrument, and its positive control

The measurement walks the same population `tools/train/apply_parity.py` does — one step per frame
whose recorded `choice` names a single option, `_PLAY` only, skipping the steps where the next frame
is the opponent's perspective — builds the `StateModel`, asks `apply_option.apply_option`, and for
every step it refuses asks `board_expectation.expectation` and records the refusal.

**Positive control:** it reproduces `board_expectation`'s own shipped backlog table exactly —

```
706 refused _PLAY steps · 81 enumerated · class counts 1–11, ZERO truncated
223 no `draw`/`fetch`   98 multi-clause   85 RNG   69 cost   48 amount
 45 not-unconditional   23 non-Trainer    17 dest   8 whiff   7 draw   2 discard-zone
```

If the buckets had not summed to the header's own figures the instrument would be broken, not the
codebase. They do.

The instrument is committed as **`tools/train/expectation_census.py`**, beside the parity lane whose
walk it borrows — a re-runnable measurement rather than a number someone once quoted, on the
precedent `tools/apply_seam_coverage.py` sets. Two reports off one pass:

```
python tools/train/expectation_census.py            # the refusal backlog (the control above)
python tools/train/expectation_census.py --sizes    # the branching measurement for BRANCH_CAP
```

It is DLL-free (the trace is the native side, cgpy's committed tables supply the card facts), so it
runs on Windows and Linux alike. Acceptance criterion A2 is *"re-run this and paste the table"*.

---

## 1. Four corrections to the issue's premises

The issue's scope rests on four factual claims. **Three are false and one is unmeasured**; each
changes what gets built.

### C1 — "nothing in the clause vocabulary distinguishes AND from OR" is FALSE

`snapshot_coverage.CLAUSE_PARAMETERS` already declares it:

```python
"choice": "the clause is one alternative of a choose-one card",     # snapshot_coverage.py:714
```

Six cards carry it, and `card_effects.json`'s own `_covers` prose states the convention outright —
Dawn (1231): *"all three search legs … they **ADD**, so no `choice`"*; Brock's Scouting (1210):
*"both modes … as `choice` clauses, so the two caps are **alternatives rather than a sum**"*.

The engine agrees mechanically. `src/cgpy/chain.py` carries **two distinct ops**:

| op | docstring | relation |
|---|---|---|
| `xDeckToHandBuckets` | *"one ctx TO_HAND min0 max1 select **per bucket** in order … ONE shuffle at the end"* | AND |
| `xDeckToHandEitherOr` | *"pick 1 poses min0 max1 over the **UNION** of both filters"* | OR |

Cross-referencing all 13 multi-leg reveal cards against their engine chain, **`choice` is correct on
11 and missing on 2** — and those 2 carry **69 of the 98** multi-clause corpus steps:

| card | printed text (engine dump) | engine op | `choice` | steps |
|---|---|---|---|---|
| 1097 Night Stretcher | *"a Pokémon **or** a Basic Energy card"* | one `effectTrashToHand`, union filter | **absent** ✗ | 42 |
| 1142 Fighting Gong | *"a Basic {F} Energy card **or** a Basic {F} Pokémon"* | one `effectDeckToHandAndShuffle`, `anyOf` | **absent** ✗ | 27 |
| 1231 Dawn · 1194 Colress's Tenacity · 1092 Secret Box · 1206 Larry's Skill | *"…, …, **and** …"* | `xDeckToHandBuckets` | absent ✓ | 8 · 0 · 0 · 0 |
| 1225 Hilda | *"an Evolution Pokémon **and** an Energy card"* | `xDeckTakeSequenceAndShuffle` | absent ✓ | 10 |
| 1094 · 1110 · 1184 · 1215 · 1238 | *"up to N **in any combination**"* | one union-filter op | present ✓ | 4 · 2 · 0 · 0 · 0 |
| 1210 Brock's Scouting | *"up to 2 Basic **or** 1 Evolution"* | `xDeckToHandEitherOr` | present ✓ | 5 |

So the 98 steps are **69 mis-declared disjunctions + 18 true conjunctions + 11 correctly-declared
disjunctions**, not 98 conjunctions.

### C2 — `choice` is currently DEAD, and its one reader misreads it

`board_expectation._HANDLED_FETCH_KEYS` lists `"choice"` with the comment *"a flag that only says the
player picks, which is already this node's whole semantics."* That is not what the compendium
declares, and it is **unreachable today**: every `choice` carrier is multi-leg, and `_sole_clause`
refuses multi-leg cards *before* `_check_clause` ever runs (verified — zero single-reveal-clause cards
carry the flag). Grepping `src/`, `tests/` and `tools/`, **no code reads the flag at all.**

It becomes load-bearing the instant item 1 admits multi-leg cards. Left as written, the widening
would read Brock's Scouting's OR as an AND.

### C3 — item 3's population is 90% not a hand problem

| card | steps | `dest` | engine op |
|---|---|---|---|
| 1086 Buddy-Buddy Poffin | **41** | **bench** | `effectDeckToBenchAndShuffle` min0 max2 |
| 1126 Precious Trolley | **2** | **bench** | `effectDeckToBenchAndShuffle` min0 max60 |
| 1205 Cyrano | 4 | hand | `effectDeckToHandAndShuffle` min0 max3 |
| 1082 Hyper Aroma | 1 | hand | `effectDeckToHandAndShuffle` min0 max3 |

Building m-subset **hand** classes — item 3 exactly as scoped — retires **4 steps** (Hyper Aroma's
one step has an empty pool and refuses regardless). The other **43** need the deploy transition.

### C4 — item 4's intersection is TOTAL, and the issue's stated reason is wrong for half of it

The issue asks to *"measure the intersection before scoping it."* Measured: **23 of 23**.

Every non-Trainer reveal carrier in the whole compendium (6 cards: 19, 66, 120, 140, 675, 1071)
carries a `trigger` or a `condition` — both rejected by `fetch_is_unconditional`. The three that
appear in the corpus split into **two populations with different reasons**:

| card | steps | why it must refuse |
|---|---|---|
| 1071 Meowth ex | 12 | `trigger: on_bench_play` — the clause DOES ride the play, but the reach predicate rejects it, and its `target: supporter` is deadness-only in `fetch_target_matches` (ADR-0073) so the pool is empty anyway. Double-gated. |
| 675 Lunatone · 140 Fezandipiti ex | 7 · 4 | `condition: solrock_in_play` / `pokemon_ko_last_turn` — these clauses are **Abilities**, a separate `_ABILITY` option. Deploying the body searches nothing. |

The issue's premise — *"a reveal riding a Pokémon does not put its source card in the discard"* —
holds only for Meowth ex. For the other 11 steps, modelling the deploy as an expectation node would
not be under-scoped, it would be **flatly wrong**: the clause does not fire on that option at all.

The "23" is additionally a **gate-order artifact**: `expectation()` runs the card-type gate before
`_check_clause`, so all 23 land in the non-Trainer bucket. Swap the order and they move into
`not-unconditional` (45 → 68). It is not an independent population.

---

## 2. Decision record

> Ruled here, so the build does not re-litigate them. Each cites the code or measurement it rests on.

**D1 — `choice` means *the legs share ONE budget drawn from the UNION of their target classes*, and
its two sub-shapes are told apart by a mechanical discriminator already present in the data:
all legs carry the same `amount` ⇒ shared-cap union; the amounts differ ⇒ exclusive either-or.**
Verified 8/8 against the engine op across every carrier (same-amount → one union-filter op;
Brock's Scouting alone, amounts 2 and 1, → `xDeckToHandEitherOr`). The declared docstring is
sharpened accordingly. Rejected alternative: a new `relation: and|or` field — it would duplicate a
fact `choice` plus `amount` already carries, and `_covers` prose already reads the absence of
`choice` as ADD.

**D2 — the two mis-declared cards are a COMPENDIUM defect and are fixed at the authoring source
(`tools/meta_tracker/effect_overrides.json`), never in the shipped artifact.** The fix is behaviourally
inert today (C2: nothing reads the flag), which is what makes it separable and safely first.
*Verified precondition:* `python tools/build_card_effects.py --limit 0` re-stamps
`src/common/card_effects.json` **byte-identically** with no native engine (`--limit 0` skips the
probe; `cmp` clean, `git status` clean).

**D3 — a disjunction becomes ONE pool; a conjunction becomes a JOINT enumeration; an either-or
refuses.** The conjunction is a cross product, and the issue's fear that this *"reintroduces the
combinatorics `BRANCH_CAP` exists to bound"* is measured false: max product across every conjunction
step in the corpus is **4** (Hilda), and Dawn's is **0**. Returning only leg 1 instead was rejected —
the module's unit is *"the board after the reveal has FULLY resolved"*, and a one-leg answer for a
three-leg card is exactly the three-quarters-of-a-card modelling `_covers` exists to refuse.

**D4 — the cost's discard set has ONE definition, and `board_expectation` does not own it.** The set
the composer must assume is the set the live decider will actually pick
(`Pilot._discard_needs_pick` → `needs.cheapest_removal`), because predicting with any other formula
is precisely the drift ADR-0103 Amendment A extracted `needs.removal_score` to close. The Pilot-side
computation is extracted to one method and the expectation node receives its ANSWER through a `shed`
seam. Rejected alternatives: (a) pricing the cost UNPAID — unsound in the over-valuing direction, which
this codebase does not take by default; (b) reading `model.mine.needs` — that resolution is the LEAF's
(`include_general=False`, no pitch terms) and `_as_discard_rows`' own docstring rules that *"a
`cost_discard` fetch … really are discarded, so discard semantics are the correct ones"*; using the
leaf resolution would silently price the shed in the wrong context.

**D5 — the m-card enumerator is a MULTISET enumerator, not `itertools.combinations`, and it needs a
closed form `deck_odds` does not have.** A pool is `{card id: unseen copies}`, so an m-subset may take
two copies of one card; and the availability of *two* copies is not `p_contains`, which answers ≥1.
`deck_odds.p_contains_at_least(unseen, prizes_hidden, deck_count, k)` is added and `p_contains`
DELEGATES to it (k=1), so there is one derivation. **Verified against brute-force enumeration over the
full small-parameter grid (D≤7, K≤6, u≤6, k≤3): zero mismatches, and it reproduces the shipped
`p_contains` exactly at k=1.**

**D6 — item 4 is DECLINED, and the gate order is fixed so the backlog stops lying.** 23/23 already
blocked (C4). A new, more actionable gate is added for the 11 ability-clause steps.

**D7 — `dest: bench` is SPLIT OUT to Issue #410, not built here.** It was specced in this document as
a scope extension; on measurement it earned its own issue instead. Two findings moved it:
its 43 bucket steps are **15** enumerable, not 30 — **Risky Ruins gates 15 of the 28 live-pool Poffin
steps**, and all 17 gated steps are that one Stadium — and recovering them means APPLYING a Stadium
trigger, which is a different kind of change from a reveal-vocabulary widening.

Grilling it further widened #410 well past this spec's reach: of the Stadium gate's **104** seam
refusals, **73 are steps the in-play Stadium provably cannot affect** (19 evolutions into a Stage 1
while a Stage-2-only modifier is out, and so on), so the dominant fix there is a gate that asks
whether the clause reaches the body — not clause application at all. #410 now owns that, both
appliers (Risky Ruins' trigger and Gravity Mountain's static delta), the bench destination, and
§3.4's two `board_delta` promotions (nothing left in this spec needs them — items 1 and 2 are hand
writes). **This spec keeps item 3 hand-only: 4 corpus steps.**

The reasoning that made it look like one issue is still sound and is recorded there: the deploy floor
already exists
(`board_delta._play`'s Basic-Pokémon branch: full HP bar, `appearThisTurn`, bench cap, `_stadium_gate`)
and the value side already exists (`needs.deploy_marginal(..., capacity=K)`, whose capacity bound is
*"an exact restriction of the same DP, not a heuristic"*). Flagged as an extension rather than smuggled
in. `dest: in_play` (17 Salvatore steps, `xDeckEvolveInPlayAndShuffle` — an evolve-in-place) stays
REFUSED: it is the evolve transition, not a deploy.

---

## 2.5 P0 — a BLOCKING prerequisite, LANDED as Issue #408 / PR #411: `CardStat.stage` was never populated

> ✅ **MERGED (PR #411, 2026-08-06). This branch is rebased onto it, so the prerequisite is
> DISCHARGED** and §4.4's empty-leg SKIP is now sound. Kept in full below because it is the reason
> §4.4 is written the way it is, and because two of its corrections became this spec's own evidence
> rules (§8 constraints 1–3). Verified on the rebased branch: `stage` is populated for all 1061
> Pokémon (`basic` 600 / `stage1` 345 / `stage2` 116), and `provider.stage_from_card` is on `main`.
>
> **The re-measurement is the acceptance, and it holds:** with `stage1`/`stage2` newly matchable, the
> census still reports **706 refused / 81 enumerated** and every bucket unchanged — because Dawn's
> Stage-1/Stage-2 legs and Hyper Aroma's pool are empty on those corpus boards for a BOARD reason,
> exactly as this section predicted with a corrected matcher before #411 existed.

**`fetch_target_matches`' `stage1` and `stage2` target classes match NOTHING, in production, and
always have.** Found by sizing the conjunction legs pool-wide and getting two zeroes that no deck
could explain.

Evidence, all mechanical:

* `CardStat.stage` is declared (`provider.py:138`) and **never assigned** by `_build_cache` — the
  SHIPPED transform, used by production's `EngineCardStatProvider` and by the offline lane alike.
  Measured: `stage` is `None` for **all 1267** cards, while the engine's own dump has it for 1061.
* `fetch_target_matches` gates those classes on `getattr(stat, "stage", None) != "stage1"` /
  `"stage2"` (`fetch_closure.py:210-215`), so both are unsatisfiable.
* The engine exposes the facts outright — `cg.api.CardData` carries **`basic`, `stage1` and
  `stage2`, all `bool`** (`api.py:473-475`). `_build_cache` copies `stage2` alone and drops the
  other two.

**The fix, verified exact, and it must not be a fourth spelling of the same question.**
`tools/meta_tracker/dump_cards.py` **already has** the canonical derivation — `stage_of(c)`:

```python
if c.basic:  return "basic"
if c.stage1: return "stage1"
if c.stage2: return "stage2"
return None
```

Checked against the shipped dump for **all 1267 cards: zero mismatches** (the 206 non-Pokémon
correctly return `None`, all three booleans being False). So the fix is to move this function into
`common/scouting/provider.py` as `stage_from_card(c)`, call it from `_build_cache`, and have
`dump_cards.stage_of` delegate to it — that file already puts `src` on `sys.path`, and tools may
import `src` while the reverse is forbidden. **Do not re-spell it in `_build_cache`**: a second copy
of "what stage is this?" is precisely the drift ADR-0087 charges for, and it is how this field came
to have one writer and no reader in the first place. (A derivation from `evolvesFrom` is equally
exact on today's pool and was rejected for the same reason — `c.basic/stage1/stage2` is the engine's
own answer; inferring a printed stage from an evolution name is a second reading.)

**Impact, stated precisely rather than dramatised:**

| consumer | effect | status |
|---|---|---|
| `fetch_target_matches` reach (`stage1`/`stage2`) | 345 + 116 cards unreachable pool-wide — Hyper Aroma (`target: stage1`) reaches nothing, Dawn's legs 2 and 3 reach nothing | live UNDER-count (the safe direction) |
| the doctrine's deadness reading | **no fabricated claim** — `_shed_signals`' caller guards with `bool(deadness_set) and all(...)` (`doctrine_fetch.py:141`), so an empty set yields `exhausted = False` | safe, checked |
| `pilot._retreat_free_granted` | a `retreatFreeGrant == "basic"` grant can never fire; **Latias ex (184)** *"Your Basic Pokémon in play have no Retreat Cost"* is its only carrier | latent — no shipped deck runs Latias ex |

**It does NOT move any number in this spec, and that is the point.** Re-measured with a corrected
matcher (positive control: it newly matches 345 stage1 + 116 stage2 cards, and all four of
hydrapple's own Stage 1/2 members), Dawn's legs stay `(2, 0, 0)` and Hyper Aroma's pool stays 0 on
every corpus step — those copies really were outside the deck when the card was played.

**Why it is nevertheless BLOCKING for §4.4.** A conjunction leg that is *unmatchable* is
indistinguishable from a leg that is *empty on this board*, and §4.4 SKIPS an empty leg. With the
defect present, Dawn on a board where the Stage 1 is still in the deck would enumerate one leg of
three and report `truncated = 0` — a complete-looking enumeration of a third of the card, which is
exactly the failure `_covers` exists to prevent. The corpus cannot catch this (measured above), so it
is guarded by a TEST rather than by a measurement: a fixture board holding an unseen Stage 1 and
Stage 2 must produce a three-leg product.

**Landed as Issue #408 / PR #411, merged first, as specced.** It was a **production behaviour change** — it
un-blinds 461 cards to two target classes, and measured, it moves exactly one agent (hydrapple: four
line pieces gain +2 re-access outs from its 2× Dawn; all five other agents are unchanged) — so it
ships alone and `score_diff`-gated rather than folded into item 1. #408 carries the full spec: the
canonical derivation, the fixture-audit vocabulary mapping, and the instrument gap that let it
survive (`test_cardstat_fixture_facts.py` cannot see helper-constructed `CardStat` rows, and the only
fixtures using the production vocabulary are built through a helper).

**Two claims in #408's body were FALSIFIED by its own build, and both are recorded here because they
are this spec's evidence rules, not footnotes.** (1) *"No shipped deck runs Latias ex"* — false;
slowking runs 2×, and the grep behind the claim could not have found it, because `deck.csv` holds
bare ids one per line **and is CRLF**. (2) R4's *"every non-Pokémon type → None"* breaks on five
Antique Fossil cards (Item `cardType`, engine `basic=True`). The first is why §8's constraints demand
a positive control before any "none found", and why every deck scan in this spec reads
CRLF-safely.

---

## 3. Shared machinery (build this first — items 1–3 all consume it)

### 3.1 `src/common/deck_odds.py` — the ≥k closed form

```python
def p_contains_at_least(unseen_copies, prizes_hidden, deck_count, k=1) -> float:
    """P(my deck still holds >= ``k`` copies of a card), from the same hypergeometric split of its
    ``unseen_copies`` over the ``deck_count + prizes_hidden`` hidden positions that :func:`p_contains`
    takes. ``k=1`` IS `p_contains`, which delegates here — one derivation, because a multi-card
    delivery may take two copies of one card and "is a second copy available?" is a different
    question from "is a first?".

        P(deck >= k) = SUM_{j=0}^{u-k} C(K, j) * C(D, u-j) / C(H, u)

    — j of the u copies landing in the K prize slots, the rest in the D deck slots. Never raises;
    bad input -> 1.0 ("assume present"), the SUPPRESSOR direction `p_contains` documents."""
```

Guards, in order: `k <= 0 → 1.0`; bad input → `1.0`; `u < k or d < k → 0.0`; `k_prizes <= 0 → 1.0`;
`u - K >= k → 1.0` (pigeonhole). `p_contains` becomes a one-line delegation, so its 5 shipped
edge-case behaviours are preserved by construction rather than by re-spelling.

> **Do not** re-derive this in `board_expectation`. ADR-0087 charges for a hand-built second key
> exactly here.

### 3.2 `src/common/snapshot_coverage.py` — the cost-count registry

The count currently *"lives in the value's name"* (that module's own words). Splitting the string is
wrong — `discard_hand` and `bottom_2` do not parse that way. Add a declared table beside
`CLAUSE_WRITES`, keyed by the same `cost` vocabulary values:

```python
#: Each `cost` value -> how many cards it takes from my hand, and WHERE they go. Declared rather
#: than parsed out of the value's name: `discard_hand` takes an unbounded count and `bottom_2` does
#: not discard at all, so a `value.split("_")[-1]` reader would be wrong on half the vocabulary.
#: `None` count means "the whole hand". Keys MUST equal the `cost` keys of CLAUSE_WRITES — asserted
#: by :func:`cost_vocabulary_agrees`, so a new cost value cannot arrive with a write-set and no count.
COST_CARDS: dict[str, tuple[int | None, str]] = {
    "discard_1":    (1,    "discard"),
    "discard_2":    (2,    "discard"),
    "discard_3":    (3,    "discard"),
    "discard_hand": (None, "discard"),
    "bottom_2":     (2,    "deck_bottom"),
}
```

Plus an audit `cost_vocabulary_agrees()` asserting `set(COST_CARDS) == {every cost value in
CLAUSE_WRITES}`, wired into `tests/strategy/test_snapshot_coverage.py`. This is the "a new clause
value fails a test rather than silently pricing 0" rule applied to the fourth axis.

### 3.3 The `choice` audit — TWO gates, in two homes, because they answer two questions

**(a) Internal consistency — `snapshot_coverage.choice_relation_problems(table)`.** Clause-set-local,
so it lives beside the other compendium audits and takes no new dependency:

```python
def choice_relation_problems(table) -> list[str]:
    """Every multi-leg reveal clause set whose declared relation is internally incoherent.

    Flags: `choice` on SOME legs but not all (a half-declared relation — nothing can read it);
    `choice` with differing `amount` across MORE than two legs (D1's either-or shape is a two-branch
    alternative by construction, and no third branch has ever been ruled); and a `choice` leg set
    whose legs disagree on `zone` / `dest` / `cost` (one budget cannot span two destinations)."""
```

**(b) The relation itself — a TEST that cross-checks the compendium against the ENGINE.** This is the
instrument that actually caught 1097 and 1142, and it cannot live in `snapshot_coverage`: the answer
is in `src/cgpy/defs/chain_overrides.json` + `generated_chains.json`, and `common` does not import
`cgpy`. A test may read both stores, and "these two stores must agree" is exactly what a test is for.

The rule, verified 13/13 across every multi-leg reveal card:

| engine `play` op | relation |
|---|---|
| `xDeckToHandBuckets`, `xDeckTakeSequenceAndShuffle` (one select per leg) | **conjunction** — no `choice` |
| `xDeckToHandEitherOr` | **either-or** — `choice`, amounts differ |
| a single op over a union filter (`effectTrashToHand`, `effectDeckToHandAndShuffle`, `xPickDiscard`, `xLookTopMayTakeThenShuffle`) | **union** — `choice`, amounts equal |

Cards whose engine entry is `deferred: "unparsed effect text"` (Colress's Tenacity is one) are
SKIPPED with their names printed, never silently passed — an unparsed card is not evidence of
agreement, and a test that quietly counted it as a pass would be the vacuous-gate failure this repo
keeps naming. **This is the gate that would have caught the two defects**, and it exists so the third
one fails a test instead of shipping.

### 3.4 `src/common/board_delta.py` — two promotions, MOVED to Issue #410

`stadium_gate` and `bench_body` were specced here while D7 was in scope. Nothing left in THIS spec
needs either — items 1 and 2 are hand writes, and item 3 is hand-only after §6.2 — so both move to
Issue #410 with the destination that wants them. Recorded rather than deleted so a reader of the
commit order does not go looking for a step that is no longer here.

### 3.5 `src/common/needs.py` — no change

Checked and deliberately unchanged. `cheapest_removal` already clamps `picks` to the row count, and
already treats absent/short `deadness`/`tiebreak` as neutral, so D4's caller needs nothing new.

---

## 4. Item 1 — conjunctions, disjunctions, either-or

### 4.1 The compendium fix (D2)

In `tools/meta_tracker/effect_overrides.json`, add `"choice": true` to **both** legs of 1097 and both
legs of 1142, and rewrite their `_covers` reasons to state the relation and its evidence:

```jsonc
"1097": [{"kind":"fetch","target":"basic_energy","zone":"discard","choice":true},
         {"kind":"fetch","target":"pokemon","zone":"discard","choice":true}],
"1142": [{"kind":"fetch","target":"basic_energy","zone":"deck","energy_type":6,"choice":true},
         {"kind":"fetch","target":"basic_pokemon","zone":"deck","energy_type":6,"choice":true}],
```

`_covers` reasons become, respectively: *"both discard-fetch legs (Pokemon, Basic Energy) carried, as
a DISJUNCTION — the card prints 'a Pokémon **or** a Basic Energy card' and the engine resolves it as
one `effectTrashToHand` min1 max1 over a `pokemonOrBasicEnergy` filter, so the two legs share one
budget (`choice`)"*, and the `anyOf`-filter equivalent for Fighting Gong.

Then `python tools/build_card_effects.py --limit 0` and commit the re-stamped artifact. The diff must
touch **only** those two entries and their `_covers` rows — anything else means the accumulate path
moved and the change is not inert.

**⚠️ Do the `.gitattributes` rule FIRST, or this step is a whole-file diff on Windows.**
`src/common/card_effects.json` sits under the bare `* text=auto` default with **no explicit `eol=`**,
and PR #411 established the root cause for its sibling: on Windows the checkout EOL for such a file
follows `core.eol` (default `native` → CRLF), *independent of `core.autocrlf`*. The builder writes LF
(`out.write_bytes(...)`, deliberately — its own comment says *"this repo builds on Windows and grades
on Linux, so the store must not depend on which one last touched it"*), so on a Windows checkout the
rebuild rewrites every line and A7's inertness check fails on a change that is genuinely inert.

Add, beside PR #411's rule for `card_functions.json` and for the same reason:

```gitattributes
src/common/card_effects.json text eol=lf
```

Verified: the blob is already LF, so this changes no bytes — it stops the *checkout* from diverging.
**The CI line-ending guard cannot catch this** — `ci.yml:58` matches `attr/text eol=lf` only, so a
file under bare `text=auto` is invisible to it (PR #411 surveyed 29 such JSON stores, 14 already
carrying CRLF blobs). Scoped to this one file, not the directory: PR #411 declined a bulk fix because
`attack_overrides.json` has a test that deliberately tolerates platform-native output.

### 4.2 `board_expectation` — replacing `_sole_clause`

`_sole_clause` is replaced by **`_reveal_legs(combat, card_id, stat) -> tuple[tuple[dict, ...], str]`**
returning the reveal clauses and their RELATION, one of `"single"` / `"union"` / `"conjunction"`.

```
no reveal clause                                    -> refuse (unchanged message)
a non-revealing companion clause present            -> refuse (unchanged message)
one reveal clause                                   -> ("single")
several, every leg carries `choice`, amounts EQUAL  -> ("union")
several, every leg carries `choice`, amounts DIFFER -> refuse: an exclusive either-or with
        per-branch caps (Brock's Scouting: "up to 2 Basic OR 1 Evolution"); the branches have
        different sizes, so one budget cannot describe both
several, NO leg carries `choice`                    -> ("conjunction")
several, SOME legs carry `choice`                   -> refuse: a HALF-DECLARED relation; the
        compendium is internally inconsistent for this card and guessing which half is right is
        exactly what D1's audit exists to prevent
ANY leg whose `target` is reach-gated               -> refuse (§4.4 rule 3): the class matches
        nothing STRUCTURALLY (`FETCH_DEADNESS_ONLY_TARGETS`), on every board, so skipping it would
        model a fraction of the card while reporting a complete enumeration. Checked HERE, on the
        clause, ahead of any pool — Secret Box and Larry's Skill are the two carriers
```

The gated-leg check is deliberately in `_reveal_legs` rather than in the conjunction branch: it is a
property of the clause set, it applies to a union identically, and a board-shaped question (*"is this
pool empty?"*) must never be the thing that answers it.

`_check_clause` runs **per leg**, with two amendments:

- the `amount` gate is relaxed to *"every leg carries the SAME amount"* for a union, and to the
  per-leg amount for a conjunction (each bucket is min0/max1 — verified in `op_deck_to_hand_buckets`);
- the empty-pool refusal moves from the whole card to the ENUMERATION (§4.4).

For a union, the **cost / zone / dest / reach** gates must agree across legs; a card whose legs
disagree refuses (no such card exists today — asserted by a test, not assumed).

### 4.3 The union pool

```python
def outcome_pool(model, clauses) -> dict:      # `clauses` was a single clause; now a sequence
    """... A card matching ANY leg is in the pool, counted ONCE — the same union walk
    `fetch_closure.class_reaccess_outs` already performs for a tutor that reaches two of a slot's
    classes ("summing per-class `reaccess_outs` would double-count")."""
    return {cid: n for cid, n in (model.mine.unseen_counts or {}).items()
            if n > 0 and any(fetch_target_matches(c, model.card_stat(cid)) for c in clauses)}
```

Backwards compatible via a single-element tuple, so the `"single"` path is literally unchanged.

**Measured:** Fighting Gong's union pool is **1–6 (median 4)** across its 27 steps — comfortably
inside `BRANCH_CAP` 12. (Night Stretcher's reaches **12** — the cap value itself, so it fits with
nothing to spare and the very next card in that deck would truncate; it stays refused as a
`zone: discard` choice node, but the figure is recorded for whoever lands the discard zone.)

### 4.4 The conjunction enumeration

Per leg, an independent pool. The classes are the **cross product**, with two rules:

1. **An empty leg SKIPS.** The engine does exactly this — `op_deck_to_hand_buckets`: *"Empty buckets
   skip with a tac bump (deck-search convention)"* — so a whiffing leg contributes no card and the
   play still resolves. This is not cosmetic: **Dawn's Stage-1 and Stage-2 legs are empty on all 8
   corpus steps**, so a whole-card empty-pool refusal would retire zero of them while a per-leg skip
   retires all 8.
2. **Refuse only when EVERY leg is empty** — that is the provably-whiffing search the existing
   refusal is for.
3. **⚠️ A leg whose TARGET CLASS is reach-gated REFUSES the whole card — it must never be read as
   an empty leg.** This is the same failure mode P0 (§2.5) describes, from a second and *deliberate*
   source: `fetch_target_matches` gates `supporter` and `any` to the DEADNESS reading only
   (`FETCH_DEADNESS_ONLY_TARGETS`, ADR-0073), so such a leg matches nothing **structurally**, on
   every board, forever. Rule 1 would swallow it and report a complete enumeration of a card it
   modelled three quarters of.

   Measured pool-wide: **Secret Box** (legs item 77 / stadium 26 / **supporter 0** / tool 27) and
   **Larry's Skill** (basic_energy 8 / pokemon 1061 / **supporter 0**) each carry exactly one such
   leg. Both have **zero corpus steps**, so this rule costs no coverage and closes a soundness hole
   that would otherwise only surface off-corpus.

   The discriminator is a property of the CLAUSE, not of the board — `clause["target"] in
   fetch_closure.FETCH_DEADNESS_ONLY_TARGETS` (measured: exactly `{"supporter", "any"}`) — so it is
   decided before any pool is built, and it reuses the shipped set rather than re-listing which
   classes are gated.

   **Applies to a UNION too**, and belongs in `_reveal_legs` beside the relation rather than in the
   conjunction branch: a gated leg silently shrinks a union's pool exactly as it silently drops a
   conjunction's leg. Measured across every multi-leg card, the only two carriers are the two
   conjunctions above — a union's analogous holes (`dig` on Bug Catching Set, `name_family` on
   Ethan's Adventure) are already refused per-leg by `_check_clause`'s reach gate, so no union
   changes behaviour. Placed generally anyway, because "no carrier today" is not a guarantee.

Copy accounting: the joint enumeration walks a **multiset** over the union of the pools, so a card
taken by leg A is not available to leg B beyond its `unseen_counts`. All five conjunction cards in the
compendium have pairwise-disjoint legs today (`cardType` is a single exclusive enum, so
item/tool/supporter/stadium cannot overlap; Dawn's basic/stage1/stage2 are stage-exclusive; Hilda's
and Colress's energy-vs-Pokémon likewise) — **verified, and the enumerator still respects copy counts
so the guarantee does not rest on which cards happen to exist.**

Joint weight = the product of per-card `p_contains_at_least` terms (§3.1), normalised over the
enumerated set. **State the epistemic honestly in the header:** the legs share one prize split so the
marginals are not independent; this is a product of marginals used as an availability WEIGHT, which is
the same epistemic class the single-card case already documents, not a joint probability claim.

**Measured:** cross-product size is **1–4 (median 4)** for Hilda and **0** for Dawn. `BRANCH_CAP`
never binds on any conjunction in the corpus.

### 4.5 The cost, paid ONCE

Secret Box repeats `cost: discard_3` on all four legs and Larry's Skill repeats `cost: discard_hand`
on all three. `_covers` already rules this: *"one cost paid once across a multi-leg find."* The
enumerator charges the cost **once per play**, never once per leg.

**Honest status: this rule has NO live carrier and is built fail-closed anyway.** Secret Box and
Larry's Skill are the only cost-bearing conjunctions in the compendium, and §4.4 rule 3 makes both
refuse outright on their reach-gated `supporter` leg — so the once-per-play charge is unreachable
today. It is implemented and tested regardless, on a SYNTHETIC two-leg costed card, because the
alternative (omit it, and let a future card charge four times) is a silent over-count. Recorded here
in the same spirit as `board_expectation`'s own note that *"absent from the counts is not absent from
the code"* — a reader grepping for a corpus step behind this rule will find none, and should not
conclude the rule is dead weight.

---

## 5. Item 2 — costed searches

### 5.1 One definition of the shed set (D4)

**`src/common/pilot.py`** — extract from `doctrine_fetch._shed_signals`:

```python
def cost_shed_indices(self, obs, board, *, exclude_cid, picks) -> tuple[int, ...]:
    """The HAND INDICES the forced-discard decider would shed to pay a `picks`-card cost — the
    same objective `_discard_needs_pick` minimises at the real select (`needs.cheapest_removal`
    over `_as_discard_rows` of the whole-hand v2 rows), so a prediction and the pick that follows
    it cannot disagree. Resupply and intrinsics are all-0.0 for `_shed_signals`' own reasons: a
    forced discard opens no redraw window, and no v1 post-gate hedge exists over the HAND rows.
    () when nothing is priceable or the hand cannot pay."""
```

`_shed_signals` is refactored onto it, and its **hardcoded `2` is replaced by the parsed cost count**
(§3.2) — today it prices Canari's `discard_1` and Secret Box's `discard_3` as if they cost two.

### 5.2 The `shed` seam on `board_expectation`

```python
def expectation(model, option, *, seat_index=None, context=None, cap=BRANCH_CAP, shed=None):
```

`shed` is `Callable[[int], Sequence[int]] | None` — given the cost's card count, return the HAND
INDICES that pay it. When a clause carries a `cost` and `shed is None`, refuse with a message naming
the missing seam rather than the missing model:

> *"its `cost` takes N cards from my hand and no `shed` oracle was supplied — WHICH cards is the
> forced-discard decider's answer (`needs.cheapest_removal`), and manufacturing a second one here is
> the drift ADR-0103 Amendment A closed. Pass `shed=` (the Pilot's `cost_shed_indices`)."*

**This deliberately keeps the module Pilot-free.** The Pilot owns board→slots; `common.board_expectation`
owns arithmetic — the same split `MySide.needs` and `state_value._hand_legs` already keep, and the
boundary `tests/strategy/test_state_value.py:3311` asserts at import.

Validation of the returned set, all refusals (a bad oracle must not silently corrupt a board):
indices in range; **no duplicates**; **the played card's own index excluded** (the cards are
*"2 **other** cards from your hand"*); exactly `count` of them, or the whole remaining hand for
`discard_hand`.

### 5.3 The writer

`_revealed` gains the cost leg, applied **before** the fetch — the engine's own order
(`chain_overrides.json` 1121: `play: [costHandTrash, effectDeckToHandAndShuffle]`):

1. remove the played card from hand (existing `take_from_hand`);
2. remove the shed indices from hand, append them to my discard (`docs/rulebook.txt` L78 — mine);
3. append the played card to my discard;
4. append the found card(s) to hand; adjust `handCount` / `deckCount`;
5. spend the Supporter allowance if the source is one.

**Verified non-interaction:** the cost does NOT move the pool. `MySide.unseen_counts` is *decklist
minus `visible_counts`*, and `visible_counts` already counts `hand` **and** `discard` — so a card
moving hand→discard leaves `unseen_counts`, `deck_count` and `prizes_hidden` untouched, and the
availability weights are unchanged. This is why the cost can be applied in the same synthesis without
re-deriving the pool.

**`bottom_2` REFUSES** (Kofu 1200) and the reason is exactly the above read backwards: it returns two
cards to the DECK, so `my_deck_count` goes UP and two known cards become unseen — the pool moves, and
`deck_order` (the registry's one `hidden` zone) is written. It reaches the cost gate on no corpus step
anyway (Kofu's clause is a `draw`, refused earlier).

### 5.4 The behavioural-tag backfill

`src/common/card_functions.json` carries `cost_discard` on **exactly one** card (1121 Ultra Ball)
while the compendium knows five with discard costs. Add the tag to 1187 Morty's Conviction, 1208 Iris's
Fighting Spirit, 1233 Canari and 1092 Secret Box (`discard_hand` carriers 1192/1206 are excluded — the
tag is about a *payable gate*, and `discard_hand` prints an instruction, always payable, per
`CLAUSE_WRITES`' own reconciliation).

⚠️ This one is **not inert**: `doctrine_fetch` has **8** rungs gated on `"cost_discard" in c.tags`, so
the four new carriers start firing them. It therefore lands as its **own commit** with a
`score_diff` run, and if it moves rulings it is reverted and re-filed — it is a doctrine change
wearing a compendium change's clothes.

**Name the expected mover, do not just "run `score_diff`".** PR #411's acceptance item 6 was
undeliverable as written because its only mover had no `strategy.py` and could not be built as a
Pilot — so `score_diff` reported `0 divergent` as a *null control*, not as evidence. Measured here
across all six decks (CRLF-safe read — `deck.csv` is CRLF, which silently broke a naive `grep` in
PR #411):

| new carrier | decks running it |
|---|---|
| 1092 Secret Box | **grimmsnarl_ex (BUILT)**, slowking (no `strategy.py`) |
| 1187 Morty's Conviction · 1208 Iris's Fighting Spirit · 1233 Canari | **none** |

So the expected and only expected mover is **grimmsnarl_ex**. A `0 divergent` result here is a
genuine null and must be reported as one; movement on any other built agent is a build failure.

**Measured search space:** hand sizes 3–9 at the 65 Ultra Ball steps ⇒ `C(hand−1, 2)` ≤ **28**
subsets, against `cheapest_removal`'s own *"n ≤ ~10 ⇒ ≤ ~250 subsets — trivial."*

---

## 6. Item 3 — multi-card deliveries (hand only; the bench destination is Issue #410)

### 6.1 The multiset enumerator

```python
def _multisets(pool: dict, m: int) -> list[tuple[int, ...]]:
    """Every size-``m`` MULTISET of card ids from ``pool``, each id repeated at most its unseen
    copies — sorted, so two processes enumerate one set (the reproducibility guarantee
    `option_equivalence.class_representatives` keeps for the same reason). `combinations` is the
    wrong tool: a pool is `{card id: copies}` and a 3-card Cyrano may legally take two Mega Lucario
    ex, which a set-based walk cannot express."""
```

`m` is clamped to `min(amount, sum(pool.values()))` — a search delivers *"up to"* its amount
(`min: 0` on every engine op), so a pool smaller than the amount is a smaller delivery, **not** a
refusal.

`amount: "all"` is **not handled here** and stays refused: its only carrier is Precious Trolley,
which delivers to the Bench, so resolving it needs the bench room clamp that goes with Issue #410.
Enumerating an unbounded `"all"` against a hand write would be modelling a card no card is.

Weight of a multiset = `Π p_contains_at_least(unseen[cid], hidden, left, k=multiplicity)` — this is
where §3.1's new form is load-bearing, and the only place `p_contains` alone would have been wrong.

Fingerprint becomes the **m-tuple** of per-card fingerprints, sorted — the generalisation
`_fingerprint`'s own docstring already anticipates (*"a multi-card delivery is the shape this
generalises into"*), and `OutcomeClass.fingerprint` is already declared a tuple.

**⚠️ The synthesized serial must not collide, and today's convention would.** `_revealed` stamps the
found card `serial = -card_id` — *"negative so an eye on a dump can tell it from an engine one"* —
which is unique only while a delivery brings ONE card. A multiset class taking two copies of the same
id would mint two instances with the identical serial, and serial is how every zone tells two
otherwise-identical cards apart. Use **`-(card_id * 100 + ordinal)`** with `ordinal` the 0-based
index within this delivery: still negative, still card-legible, and collision-free across cards
because ids are three digits. `_fingerprint` is unaffected either way (`option_equivalence`'s
`_without_serial` drops the field — that is exactly why a synthesized instance is sound to
fingerprint), so this matters for the BOARD, not for the class identity. Asserted by a test on a
two-copies class.

**Measured:** `C(pool, m)` is **1–3** (Poffin), **1** (Cyrano). `BRANCH_CAP` does not bind. The
general bound is stated in the header rather than left implicit: for a pool of *p* distinct ids and
delivery *m*, the class count is at most the multiset coefficient `C(p + m − 1, m)` — for a 3-card
delivery from an 11-wide pool, **≤ 286** (an over-estimate, since the per-card copy cap trims it) —
an order of magnitude past the cap, so **truncation is expected off-corpus and the reporting path is
what makes that legible.**

### 6.2 The bench destination — SPLIT OUT to Issue #410

`dest: "bench"` (Buddy-Buddy Poffin 41 steps, Precious Trolley 2) is **not built here**. It needs a
deploy floor rather than a hand write, and — measured — **Risky Ruins gates 15 of the 28 live-pool
Poffin steps**, so the destination alone is worth 15 and only applying that Stadium trigger takes it
to 30. That applier wants the parity lane (via `board_delta._play`) to verify its arithmetic, which
this inert module cannot offer.

Issue #410 owns all of it — and, on grilling, considerably more: the Stadium gate refuses **104**
seam steps and **73 of them are steps the Stadium cannot reach**, so #410's largest and cheapest part
is narrowing that gate, with the two appliers and this destination on top. §3.4's promotions go with
it.

`dest: "in_play"` (17 Salvatore steps) stays refused in both places: `xDeckEvolveInPlayAndShuffle` is
an evolve-in-place, so its floor is `_evolve`'s, not a deploy's.

**This spec's item 3 is therefore hand-only — Cyrano's 4 corpus steps** — and the multiset enumerator
of §6.1 is built here, since Issue #410 consumes it.

---

## 7. Item 4 — DECLINED, plus a gate-order fix

No enumeration is built. Two changes, both about telling the truth. **The gate ORDER is the whole
change, so it is spelled out once, in full, rather than described twice:**

```
1. _reveal_legs        no reveal clause / non-revealing companion / the relation (§4.2)
2. NEW: the ability gate   a reveal clause on a non-Trainer fires on this `_PLAY` ONLY if it
                           carries `trigger: on_bench_play`
3. _check_clause       per leg: RNG, draw, reach, zone, cost, amount, dest, unknown keys
4. the card-type floor "only an Item or a Supporter resolves to my discard on a search"
5. the pool            empty-pool / no-availability
```

Gate 2's wording:

> Lunatone's `solrock_in_play` and Fezandipiti ex's `pokemon_ko_last_turn` are **Abilities** — a
> separate `_ABILITY` option — so deploying the body reveals nothing, and pricing the deploy as an
> expectation node would be wrong rather than merely incomplete.

**Where the 23 land under that order, measured:** 11 at gate 2 (Lunatone 7 + Fezandipiti ex 4) and
**12 at gate 3** (Meowth ex — it carries `trigger: on_bench_play`, so gate 2 passes it and the reach
predicate refuses it as *"not the unconditional whole-deck search"*). The card-type floor at gate 4
keeps **0** of them, which is the point: it was never the actionable answer for any of the 23.

The existing ordering comment is amended rather than deleted — its measurement (*"the order moved 79
corpus steps out of the card-type bucket"*) stays true of the reveal-first gate, which does not move.
The header's backlog table is rewritten with the resulting buckets (`not the unconditional` 45 → 57,
a new `an Ability, not this option` 11, `only an Item or a Supporter` 23 → 0) and the DECLINE reason
recorded next to the counted backlog, per the issue's acceptance criterion.

**Recorded and deliberately NOT done:** Meowth ex's 12 steps stay refused even with `trigger` honoured,
because `target: supporter` is deadness-only in `fetch_target_matches` (ADR-0073), so its pool is
always empty. Un-gating that is *"a deliberate change to the out-count … made with a measurement"* in
that ADR's own words, it moves the gamble/closure out-count for every Supporter tutor in the pool, and
it is **not** this issue's to make.

---

## 8. Acceptance, and how each claim is checked

| # | Criterion | Check |
|---|---|---|
| A1 | Every item BUILT or DECLINED with its reason in the module header | review |
| A2 | Corpus coverage re-measured, not claimed | `python tools/train/expectation_census.py`; header table replaced with its output |
| A3 | `BRANCH_CAP` re-checked against the new distribution | the class-count histogram + `--sizes`, same run |
| A4 | No engine shuffle; `NONDETERMINISTIC_CLAUSES` still refused | existing tests, unchanged |
| A5 | Suite green | `python -m pytest tests/ -q` |
| A6 | Both ADR-0072 gates **byte-identical** for commits 1–8 | `apply_option`'s own docstring: *"Nothing in production calls this yet."* Verified — `grep` for `apply_option`/`board_delta` in `pilot.py` / `runtime.py` / `strategy/` returns **0 hits**. Commit 9 is the ONLY live change (§5.4) |
| A7 | The compendium re-stamp is inert | `git status --porcelain` clean after rebuild; diff touches 2 entries + 2 `_covers`. **Add the `.gitattributes` rule first — see §4.1** |
| A8 | The parity lane is unmoved | `APPLY_PARITY_FULL=1 pytest tests/parity/test_apply_seam_parity.py` |
| A9 | P0: every card's `CardStat.stage` agrees with the engine's own `basic`/`stage1`/`stage2` | new test, all 1267 cards |
| A10 | P0 is the ONE spelling of the stage question | `dump_cards.stage_of` delegates; asserted by test |
| A11 | A conjunction leg that is unmatchable cannot masquerade as empty | fixture board with an unseen Stage 1 **and** Stage 2 yields a three-leg product (§2.5) |

**Projected coverage: 81 → 198 of 706 (11.5% → 28.0%).**

Counted per step against the measured pool, **not** by totalling the refusal buckets — a step whose
pool is empty on its own board keeps refusing on the shipped provably-whiffing rule, which is correct
behaviour and not a shortfall. Totalling the buckets would have claimed 200; the honest figure is 198.

| build | bucket steps | ENUMERABLE | why the gap |
|---|---|---|---|
| baseline | — | 81 | — |
| item 1 disjunction — Fighting Gong | 27 | **27** | — |
| item 1 conjunction — Hilda 10, Dawn 8 | 18 | **18** | Dawn's empty Stage-1/2 legs SKIP (§4.4) |
| item 2 cost — Ultra Ball | 65 | **64** | 1 step: no reachable Pokémon left unseen |
| item 2+3 — Canari (needs cost AND amount) | 4 | **4** | — |
| item 3 hand m-subset — Cyrano 4, Hyper Aroma 1 | 5 | **4** | Hyper Aroma's only step has an empty pool |
| item 4 | 23 | **0** | declined (§7) |
| ~~D7 bench~~ | ~~43~~ | — | **split out to Issue #410** (§6.2) |

Reproduce with `python tools/train/expectation_census.py --json out.json`, then count rows with
`union > 0` per card — the same arithmetic, from the same walk.

⚠️ **A6 vs A2 — the one place these criteria pull against each other.** Item 2's coverage is
CONDITIONAL on a caller supplying `shed`, and `apply_parity`'s lane builds bare models. The
re-measurement therefore reports **both** numbers — with and without the oracle — and the header
states which is which. Reporting only the higher one would be the silent-cap failure this module was
built to avoid.

### Test plan

New tests in `tests/strategy/test_board_expectation.py`, on the existing DLL-free fixture seam
(`DictCardStatProvider` + hand-built zones); the shipped `_CLAUSES` rows for the new cards are copied
verbatim from `card_effects.json`, as that file's convention requires.

**⚠️ New `CardStat` rows are audited, and Issue #408 changed how.** `test_cardstat_fixture_facts.py`
walks every `CardStat(...)` in `tests/` and diffs its declared facts against
`data/EN_Card_Data.csv`. Two consequences for the rows this spec adds — both new since PR #411:

* **`stage` is now audited in the CANONICAL vocabulary** (`"basic"` / `"stage1"` / `"stage2"` /
  `None`), because #408 mapped `_csv_truth` off the raw CSV string. **This matters directly for
  item 1's conjunction test**, which needs a real Stage 1 and a real Stage 2 to give Dawn's legs
  something to match: a hand-built row must declare `stage="stage1"` / `"stage2"` (and `stage2=True`
  for a Stage 2), matching the card's real facts. `"Stage 1"` — the pre-#408 fixture spelling — is
  now a test failure.
* **Any row whose facts do NOT match its real card must carry `synthetic=True`**, and a synthetic row
  may not keep the real card's name. #408 also rekeyed `SYNTHETIC_SOURCE_NAME_SITES` from
  `(path, line, cardId)` to `(path, enclosing_def, cardId)`, so adding rows above an existing entry no
  longer shifts the ledger — but a new synthetic row that reuses a source name still needs its own
  entry.

The existing `_STATS` rows in this file declare no `stage` today, so the risk is confined to the rows
this spec adds. Cheapest safe route: prefer real cards with real facts and declare only what the test
needs.

1. a `choice` union enumerates ONE pool over both legs (Fighting Gong's shape)
2. a conjunction enumerates the cross product — **use HILDA, not Dawn**. Hilda's legs are `energy` +
   `evolution`, which match the EXISTING fixture pool (`E_F`, `Mega Lucario ex`) and read **no
   `stage` field at all**, so this test needs no new `CardStat` row and carries no ordering
   dependency on PR #411's fixture-audit change (§8 constraint 2). Dawn's cross product needs
   `stage="stage1"`/`"stage2"` rows, whose audited ground truth CHANGES with #411 — verified: all 14
   rows in `test_board_expectation.py` are visible to `test_cardstat_fixture_facts.py`
2b. an EMPTY leg SKIPS rather than refusing — Dawn's measured shape, and the test that would have
   caught treating leg-emptiness as a whiff. **Land this one AFTER #411**, since before it Dawn's
   stage legs are empty for the wrong reason (an unmatchable matcher, not an empty board) and the
   test would pass vacuously
3. every leg empty still refuses
4. an either-or (differing amounts) refuses with its own message (Brock's Scouting)
5. a half-declared relation refuses (synthetic — no card has this shape, which is the point)
6. a costed search with `shed` enumerates; the shed cards land in my discard and leave my hand
7. a costed search WITHOUT `shed` refuses naming the seam
8. a `shed` returning the played card's own index / a duplicate / the wrong count refuses
9. one cost, paid once, across a multi-leg find (Secret Box) — and, separately, that Secret Box's
    reach-gated `supporter` leg makes the whole card REFUSE rather than skip (§4.4 rule 3)
10. an m-card delivery enumerates multisets INCLUDING a two-copies-of-one-card class, weighted by
    `p_contains_at_least` (the class a `combinations` walk would silently drop)
11. `m` clamps to the pool rather than refusing
12. `amount: "all"` refuses (its only carrier is a bench delivery — Issue #410's)
13. `dest: bench` and `dest: in_play` BOTH still refuse here — the bench destination is Issue #410's
14. the item-4 gates: an ability-clause deploy refuses with the new message; the backlog order is
    asserted so a future reorder is a deliberate act

In `tests/strategy/test_deck_odds.py`: `p_contains_at_least` against brute-force enumeration over the
small-parameter grid, and `p_contains(u,K,D) == p_contains_at_least(u,K,D,1)` as an identity.

In `tests/strategy/test_snapshot_coverage.py`: `COST_CARDS` covers exactly the `cost` values in
`CLAUSE_WRITES`; `choice_relation_problems` is empty over the shipped compendium **and** bites on a
synthetic half-declared card.

A new cross-store test (§3.3b) asserting every multi-leg card's declared relation against its engine
chain op, with `deferred` entries skipped BY NAME. Its own positive control: reverting 1097's
`choice` must turn the test red — a relation audit that stays green after the defect is reintroduced
is not an audit.

### Commit order (each independently revertible)

0. **P0 — Issue #408**, a SEPARATE PR merged before this branch (§2.5). **Item 1's conjunction must
   not land before it** — §4.4's empty-leg SKIP is unsound while a leg can be silently unmatchable.
   This branch rebases onto it, so item 1's `score_diff` is taken against #408's merged state.
1. `deck_odds.p_contains_at_least` + delegation + tests — pure, no consumer
2. `snapshot_coverage.COST_CARDS` + `choice_relation_problems` + audits
3. compendium `choice` fix (1097, 1142) + re-stamp — **inert**, A7
4. ~~`board_delta` promotions~~ — moved to Issue #410 with the destination that needs them (§3.4)
5. item 1 (relation, union pool, conjunction enumeration)
6. item 3 — the multiset enumerator, HAND destination only (Issue #410 consumes it)
7. item 2 (`cost_shed_indices`, the `shed` seam, the writer)
8. item 4 (declines, gate order, header rewrite) + the re-measurement
9. `cost_discard` tag backfill — **separate, `score_diff`-gated, revertible on its own** (§5.4)

---

## 9. Card usage — decided, not asked

Every ruling below was decidable at source; none needs a human. Recorded so the build does not
reopen them.

- **Precious Trolley (1126)** *"any number of Basic Pokémon onto your Bench"* — `amount: "all"`
  resolves to the pool clamped by bench room (the engine spells it: `max: 60`, clamped by
  `effective_bench_max − len(bench)`). Decided, but the ruling travels with **Issue #410**: this card
  delivers to the Bench, so it refuses here.
- **Larry's Skill (1206)** *"Discard your hand and search…"* — `discard_hand` needs no choice at all
  (every other card goes), and the played Larry's is already out of hand when it resolves. Its three
  finds are a conjunction; the cost is paid once.
- **Secret Box (1092)** — four legs, `discard_3` repeated on each, paid once (`_covers` rules it).
  Its item/tool/supporter/stadium legs cannot overlap: `cardType` is a single exclusive enum.
- **Meowth ex (1071)** — refused; the blocker is ADR-0073's Supporter gate, not this vocabulary (§7).
- **Brock's Scouting (1210)** — refused as an either-or; also out of the single-card scope at
  `amount: 2`.
- **Ethan's Adventure (1215)** — `name_family` stays undecidable (`fetch_closure` documents the index
  that would be needed); unchanged by this issue.
