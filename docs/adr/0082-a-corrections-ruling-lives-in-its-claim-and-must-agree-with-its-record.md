# ADR-0082 — A Correction's ruling lives in its **Claim**, and a Claim must AGREE with its record

**Status:** Accepted (grilled 2026-07-29, `/grill-with-docs` during the Issue #187 review — five
locked decisions, one of them a mid-grill withdrawal). **Build = Issue #211.**
**Extends [ADR-0072](0072-mid-build-swaps-are-gated-by-deterministic-instruments.md)
decisions 3–4** (the `claims` block and the Held-out Ledger) to the fixture generation that predates
them. Does **not** supersede anything.

⚠️ **Number claimed 2026-07-29 with `docs/adr/README.md` reading "Next free number: 0082".** Six
collisions in four days precede this one; if another 0082 merges first this renumbers on rebase. Cite
the issue alongside the number.

**Context issues:** Issue #187 (S4-deny — the review this grill ran during), Issue #199 (S3c, closed —
where the f29 adjudication was routed and not done), Issue #177 (where f29 was actually re-ruled),
Issue #167 (ADR-0072's build, which shipped `claims`), Issue #165 (the Turn Planner, cited as a
generic owner for the KO-vs-free-Item family), Issue #136 (the Value System tracker),
ADR-0049 (Correction identity = the Scope's subject), ADR-0062 (the denial oracle, whose f29 row this
touches), ADR-0072 (the Claim vocabulary this extends).

## Context

The grill started as a narrow question: is `82749168-29`'s recorded `correct=[2]` stale, given a
candidate Salvatore → Mega Starmie ex → Ignition Energy → free-retreat → Nebula Beam 2-prize KO line?

**It was already re-ruled**, on 2026-07-28 during Issue #177's grill (`2d647ba`, on `main`):
`correct=[10]` Play Salvatore, with a source-verified rationale. Every leg re-verified in this grill:

| claim | source | verdict |
|---|---|---|
| Salvatore may evolve a body put into play this turn | `EN_Card_Data.csv` id 1189, printed text | ✔ |
| Mega Starmie ex ← Staryu, Stage 1, no Ability (so Salvatore can fetch it) | id 1031 | ✔ |
| Nebula Beam `●●●` / 210 | id 1031 | ✔ |
| Ignition Energy provides `{C}{C}{C}` on an Evolution, discards EOT | id 17 | ✔ |
| Cinderace retreat 0 (CSV `n/a` encodes 0) | `CardStat.retreatCost` via `EngineCardStatProvider` | ✔ |
| Terapagos ex 130/230, `ex=True` / `megaEx=False` → **2 prizes** | id 176 + `docs/rules.md` §6 | ✔ |
| evolving into a Mega ex does **not** end your turn | `docs/rules.md` §4 (rulebook L335) | ✔ |

So the issue-tracker trail was the thing that was wrong, not the corpus. The corpus record is correct
and the shipped Pilot picks `[10]`. What was stale is the **test fixture**.

### The trail worth recording, because it is the failure mode

The f29 adjudication request was filed on Issue #187, relocated to Issue #199, and never performed
there — Issue #199 worked the *other* anchor (`86091435-68`) and closed. Its close-out routed the
generic "a positive-scoring free Item is tiered ahead of a KO" family to Issue #165's Turn Planner,
but nothing ever filed *this* frame anywhere. Meanwhile the actual re-ruling had already happened, two
days earlier, in a third issue (Issue #177) that the trail does not mention. **Prose hand-offs between
issues lost the frame in both directions at once** — which is ADR-0072's own thesis (*"a re-ruling is a
state the instruments read, not prose in a swap-review doc"*) arriving from a new direction.

### The measurement: three disjoint key schemes

Sweeping all 136 committed fixtures under `tests/fixtures/corrections/`:

| key carried | count | of which carry a `claims` block |
|---|---|---|
| `episode` + `frame` (loose pair) | 34 | **0** |
| `frame_key` (`episode\|seat\|scope\|n`) | 8 | **8** |
| neither | 94 | 4 |

**Perfectly disjoint.** Two generations that never met: every fixture that adopted ADR-0072's `claims`
block dropped (or never had) a joinable key in the older shape, and every fixture carrying the older
pair predates `claims`. The loose `episode`/`frame` pair is *not* ADR-0049's identity, which is the
Scope's subject — so it does not join to a Correction the way `frame_key` does.

A first sweep of this grill reported "6 divergences" while joining only on `episode`/`frame`; it was
blind to the `frame_key` population and its classification was wrong for two of the six. Recorded
because the same blindness is what the guard in decision 2 exists to prevent.

### What the six actually are

| fixture | fixture says | record says | reading |
|---|---|---|---|
| `ms_doom_relax_bare_terapagos_f29` | `[2]` | `[10]` (re-ruled 2026-07-28, Issue #177) | **real** — stale, no sibling |
| `ml_dead_hand_full_refresh_f15` | `[0]` + a dated DoD re-tag | `[1]` | **real** — a verified win the record denies |
| `dp_doom_guard_archaludon_1e_f35` | `[2]` | `[1]` (re-ruled 2026-07-26, Issue #167) | **not drift** — sibling `dp_hold_evolve_until_typed_ready_f35` carries `frame_key 86091435\|0\|decision\|35` and `claims.decision.correct=[1]`, matching |
| `ms_prefer_cheap_evolution_enabler_f41` | `[4]` | `[3]` | **not drift** — sibling `ms_item_over_supporter_indifferent_f41` carries `frame_key 85164605\|1\|decision\|41`, `claims.decision.correct=[3]`, `owner #145`, `ruled 2026-07-27` (*"valid but immaterial here"*) |
| 5 seeded fixtures | — | — | **not drift** — obs differs **only** by `own_prizes` + `search_begin_input` (ADR-0050 reseeding) |
| 2 × `ms0705_*` | `agent_choice` / `human_wanted` | `chosen` / `correct` | **not drift** — an older field-naming, same rationale |

So **ADR-0072's mechanism works wherever it was adopted.** Both frames that had a `claims` sibling had
their re-ruling captured correctly, machine-readably, with `owner`/`ruled`/`why`. The two real defects
are both in the pre-`claims` generation, which has nowhere to put a re-ruling.

### The f29 stale value is inert *today*, and that is luck

`parse_claims` (`tools/train/gates.py:181`) synthesises a Decision Claim from a fixture's top-level
`correct` when no `claims` block is present — deliberate back-compat, *"so all ~130 committed fixtures
keep exactly their present meaning with no edit."* So a stale `correct` **is** a stale Claim wherever
`parse_claims` is reached. It is reached via `held_out_frames`, which skips any fixture without a
`frame_key` — and f29 has none. The Leaf Lab scores **Corrections**, not fixtures
(`leaf_lab.py:176`). So f29's stale value currently feeds no gate. Back-fill `frame_key` onto it, as
decision 1 requires, and it *would* — which is why decision 2's check is a precondition of decision 1,
not a follow-up to it.

## Decisions

1. **Back-fill `frame_key` and an explicit `claims.decision` onto the 34 loose-keyed fixtures.**
   ADR-0072's vocabulary becomes universal rather than partial; the loose `episode`/`frame` pair stops
   being a second, non-joining identity. `parse_claims`'s back-compat synthesis stays, so the
   back-fill is incremental and nothing breaks mid-migration.

2. **A Decision Claim must AGREE with its Correction's `correct`, joined by `frame_key` — with exactly
   two declared escapes.** An `owner` (a Held-out Frame, ruled out of this decider's scope) or a dated
   `why` (a re-ruling recorded on the fixture). An *undeclared* disagreement fails. Both escapes are
   already-shipped ADR-0072 fields, so this adds an invariant, not a schema.

3. **The Correction is the ruling of record; the Claim is where an instrument reads it.** Not a
   contradiction of decision 2's escapes: a fixture may *record* a re-ruling, but it must say so in a
   dated `why`, and a re-ruling that changes what the human believes belongs in the Correction. The
   Leaf Lab scores Corrections, so a record left wrong keeps feeding bad ranking signal however many
   fixtures are right.

4. **`82749168-29`: sync the fixture from the record** (`[2]` → `[10]`). The record is correct and
   verified; nothing about the ruling is in doubt.

5. **`84071010-15`: promote the fixture's `[0]` into the record**, preserving the 2026-07-05 original
   inline as superseded, with a `reviewed.json` disposition and `category` moving
   `wrong_supporter` → `missed_win`. Verified at source this grill: our Active Makuhita 50/80 carries
   **no Energy** and retreat 2, so it cannot retreat unaided; Petrel (id 1219) searches *any* Trainer,
   and Air Balloon (id 1174, `−{C}{C}`) is in the deck; Balloon → Makuhita makes retreat **0**; the
   benched Mega Lucario ex already holds 1 `{F}` and Aura Jab is `{F}`/**130** (id 678) ≥ the
   opponent's Riolu **80** (id 677); their bench is **0 of 5**, so `docs/rules.md` §7 condition 2
   (*no Pokémon in play to replace a KO'd Active*) makes it a **win on turn 3**. Supporter, attach and
   retreat were all unspent. The record's `[1]` Lillie's Determination is a stochastic 8-card redraw
   that declines a guaranteed win.

## Consequences

- **ADR-0062 gets Amendment A** (decision 4's knock-on). Its f29 row is *numerically intact* — the
  Hammer prices exactly `−1.25` on HEAD, and the derived bound `_DENIAL_BENCH < 30/70 = 0.43` still
  holds, because it needs f29 to *not play* the Hammer and Salvatore-instead-of-Hammer satisfies that
  as well as attach-instead-of-Hammer did. What changed is that the frame now doubles as a missed-KO
  anchor, and the rationale ADR-0062 quotes is superseded. **Issue #187's acceptance criterion
  ("Deny 5/5 holds") is unaffected** — verified, not assumed.
- **`ms_prefer_cheap_evolution_enabler_f41` and `dp_doom_guard_archaludon_1e_f35` need no ruling
  change.** Their top-level `correct` is vestigial next to a sibling's Claim. Back-filling them under
  decision 1 must reconcile *to the sibling*, not to a fresh adjudication — and the f41 pair is the
  standing example of why: promoting its `[4]` into the record, as an earlier decision in this grill
  would have done, would have overwritten a live `owner #145` user ruling dated 2026-07-27.
- **Two fixtures for one frame is legal and load-bearing.** The pairs above assert different things
  about the same board (a doom shadow vs a re-ruled pick; a planner commitment vs a held-out
  indifference). Decision 2's check keys on `frame_key`, so it must tolerate several fixtures per
  frame and compare each Claim independently.
- **The 5 seeded fixtures need an obs comparison modulo `own_prizes` + `search_begin_input`.** A naive
  byte-compare reports them as divergent; they are ADR-0050 reseeding, not drift.
- **The 94 keyless fixtures stay keyless for now.** An unknown subset is genuinely synthetic and an
  unknown subset is record-derived-but-unjoinable (`dp_hold_evolve_until_typed_ready_f35` proves the
  latter exists — it carries a real frame's re-ruling *and* a `frame_key`, but no `episode`/`frame`).
  Distinguishing them is not chartered here and is **named, not silently dropped**.
- **Reference discipline:** `ms0705_bosss_over_harlequin_f78` and `ms0705_gust_cinderace_only_ko_f79`
  use `agent_choice`/`human_wanted` where the rest use `chosen`/`correct`. Normalising them is part of
  decision 1's back-fill.

## Alternatives rejected

- **A record-is-truth resolver: strip the ruling off record-backed fixtures entirely and have tests
  read it through a join.** *Provisionally accepted mid-grill and then withdrawn* — it was proposed
  before the `claims` block was found, and it would have built a second, competing authority mechanism
  beside a shipped ADR-backed one that demonstrably works. Recorded rather than quietly dropped
  because the withdrawal is the most useful thing in this ADR: the first three sweeps of a 136-file
  corpus all joined on the wrong key, and the design that followed from them was wrong in the same
  shape.
- **Fix `f29` and `f15` only, no back-fill and no check.** Leaves the two-generation split, so the
  next re-ruling lands in whichever generation its author happens to touch. That split *is* the cause.
- **Rewrite ADR-0062's quoted rationale in place** instead of amending. Destroys the record of what
  motivated the decision, which is most of an ADR's value.
- **Fold this into Issue #187.** The ruling is corpus-wide, not instrument-specific, so by ADR-0076
  decision 3's own principle it does not belong in the instrument's issue — and a back-fill across 34
  fixtures would make a deny-instrument diff unreviewable.


## Amendment A (2026-07-29) — two build-shape corrections found while implementing (Issue #211)

Both are corrections to *this ADR's* build shape, not to its decisions. Recorded because each was
written from a field-name observation without reading the consumer, which is the same mistake in
miniature that the ADR itself is about.

**1. "Normalise the two `agent_choice`/`human_wanted` fixtures to `chosen`/`correct`" is WITHDRAWN.**
Those field names are not an older schema — they **invert** the usual one. `ms0705_bosss_over_harlequin_f78`
and `ms0705_gust_cinderace_only_ko_f79` are **REFUTED** Corrections (`reviewed.json`, `disposition:
refuted`, human acknowledgement 2026-07-09), and `tests/strategy/test_blunder_20260709.py` asserts:

```python
assert dec.chosen == fx["agent_choice"]      # the agent is right
assert dec.chosen != fx["human_wanted"]      # the human's ask is refuted
```

Renaming `human_wanted` to `correct` would have asserted that a refuted pick is the ruling. They
therefore assert **no pick**, `parse_claims` synthesises no Decision Claim for them, and they are
exempt from the `frame_key` back-fill — recorded as `ASSERTS_NO_PICK` plus a test that fails if either
ever gains a `correct`, so the exemption cannot go stale.

**2. Decision 5's provenance was wrong: `84071010-15` was re-ruled 2026-07-13, not by this grill.**
`reviewed.json` already carried a `fixed` entry for it, round **2026-07-13**, whose reason states
outright: *"Fixture re-tagged correct=[0] (Petrel), category missed_win."* So the ruling, the category
change and the source verification all predate ADR-0082 by sixteen days — what never happened is the
**propagation to the record**, which is precisely the drift this ADR exists to make loud. Consequences:
no new ledger entry was added for it (the existing one is accurate and dated), and the record's note
dates the ruling 2026-07-13 with 2026-07-29 as the propagation. The independent re-verification this
grill performed stands; it was confirmation, not adjudication. That same 2026-07-13 entry also explains
why the fixture carries `own_prizes` + `search_begin_input` (*"so the tracker anchors and
deck_definitely_has(Air Balloon)=True"*), which independently corroborates `SEEDED_OBS_KEYS`.

**Two things the build added beyond the recorded shape**, both closing holes the decisions imply but
did not name:

- **A fixture's top-level `correct` must equal an explicit `claims.decision.correct`.** 33 test modules
  read `fx["correct"]` directly, so the back-fill keeps both in sync rather than deleting the former —
  which is what makes it non-breaking, and which opens a drift the gate would not otherwise see.
- **Every record-backed fixture must declare a `frame_key`** (a completeness invariant). Claim Agreement
  opts in on that key, so a fixture with a joinable identity and no key is silently ungated — exactly
  how the two lost re-rulings stayed lost. Coverage went 8 → 40 fixtures.

**Also flagged, deliberately not fixed here:** `fixed` is not in `review_correction.py`'s
`DISPOSITIONS` (`refuted | deferred | covered`), yet the committed ledger holds **four** `fixed`
entries and one `deferred-multi-turn`, and nothing validates the value on load (`partition_reviewed`
checks only presence). So the sanctioned CLI cannot produce entries the data already relies on.
Widening a closed vocabulary is an ADR-shaped decision, not an implementation detail.
