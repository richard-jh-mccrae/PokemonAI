# ADR-0025: Baseline rules cluster by decision-context; `doctrine_` vs `baseline_`

**Status.** Accepted and BUILT (behavior-neutral) — `common/strategy/baseline/baseline_*.py` holds the
decision-context clusters, `common/strategy/doctrines/doctrine_*.py` the archetype+Mixin doctrines, and
`general_strategy.py` is assembly-only. The convention held: the baseline has since grown past the
original 11 clusters (e.g. `baseline_phases`, `baseline_posture`) without touching `general_strategy.py`.

**Context.** The deck-agnostic General Strategy had grown to 27 baseline Hypotheses in one flat
list in `common/strategy/general_strategy.py`, alongside three card-archetype **doctrines** that had
just been pulled into their own `strategy/doctrines/` subpackage (Gust/Fetch/Shuffle-Refresh —
ADR-0022/0023/0024). Finding "where does rule X live?" in the 27-rule wall was slow for a human and
for the agent. The natural reflex was "make a `doctrine_energy.py` for energy rules" — but that
conflates two different kinds of file. A **doctrine** is one card archetype that owns BOTH its
Hypotheses AND Pilot-side closed-form code (a `*Mixin`: a KO oracle, a value comparator) that cannot
be expressed as a tunable weight. Energy rules are the opposite: pure-data reflexes with no Mixin —
ADR-0016 deliberately splits energy attachment across General Strategy (the weights) + the Tactical
Evaluator (readiness/will-it-die) + deck params, so there is no single energy oracle to own. Calling
an energy grouping a "doctrine" would put two different axes (archetype-with-Mixin vs.
function-theme) under one prefix and re-introduce the very ambiguity the split was meant to remove.

**Decision.** Split the baseline into **clusters by decision-context**, kept distinct from doctrines
by a naming convention:

- **`doctrine_*`** (in `strategy/doctrines/`) = ONE card archetype, anchored to its own ADR, owning
  its Hypotheses **and** a Pilot `*Mixin`. The defining trait is the closed-form code.
- **`baseline_*`** (in `strategy/baseline/`) = a cluster of deck-agnostic General-Strategy
  Hypotheses grouped by the **decision-context they fire on** — `energy`, `snipe`, `promote`,
  `retreat`, `bench`, `tool`, `evolution`, `heal`, `opening`, `sequencing`, `disruption`. Pure data,
  **no Mixin**. Purely a findability split.

**Decision-context is the primary axis**; a card-function theme (`tool`, `evolution`) earns its own
file only when 2+ rules share it. A rule that fits two clusters goes to the context it *fires* on
(the `select` it keys to). Each cluster file's module-local helpers/constants live with it
(`EVOLVING_THREAT_DMG` → `baseline_snipe`; `_multi_prize`/`_is_pokemon` → `baseline_bench`); none is
shared, so there is no baseline util module.

**Assembly mirrors the doctrines idiom.** Each `baseline_*.py` exports `HYPOTHESES`;
`baseline/__init__.py` re-exports the 11 lists under aliased names **and** owns the combined
`BASELINE_HYPOTHESES` roster (the one extension past the doctrines `__init__`, justified by 11
clusters vs. 3 doctrines — it keeps the assembly a clean 4-term sum instead of a 14-term chain).
`general_strategy.py` is now assembly-only: `BASELINE_HYPOTHESES + GUST_ + FETCH_ + REFRESH_`. The
Pilot still scores the result as one flat sum, so cluster boundaries and order are runtime-irrelevant.

**Doctrine cohesion outranks the baseline axis.** `attach-before-hand-shuffle` is an `ATTACH`/energy
rule by the decision-context axis, but it stays in `doctrine_shuffle_refresh` because it only makes
sense within that doctrine's sequencing story (it reads `shuffle_hand` to attach *before* the
shuffle). The decision-context axis governs baseline clustering only; it never scatters a doctrine.

**Considered options.** A `doctrine_energy.py` (rejected: energy has no Mixin and ADR-0016 makes it a
layered procedure, not an archetype — it would put a second, incompatible meaning on the `doctrine_`
prefix). Card-function as the primary axis (rejected: you debug by what the agent *did* — "it
retreated wrong" → `retreat.py` — which is a decision-context, not a card type). A single
`baseline/misc.py` catch-all for the singletons (rejected: `heal`/`opening`/`sequencing` are bets to
grow, and a catch-all becomes a second dumping ground). An aggregating combined list inside
`doctrines/__init__` too (out of scope; 3 doctrines don't need it).

**Consequences.** Two prefixes, one rule each: `doctrine_` = archetype + closed-form Mixin;
`baseline_` = pure-data reflex cluster by decision-context. "Where does rule X live?" is answered by
the select it fires on. Adding a future baseline cluster touches `baseline/__init__.py` (re-export +
the `BASELINE_HYPOTHESES` sum) — not `general_strategy.py`. The split is documented as glossary terms
**Doctrine** and **Baseline Cluster** in `src/common/CONTEXT.md`. No behavior change: the assembled
`GENERAL_STRATEGY` roster (id → weight → status) is identical before and after, guarded by a
characterization test.
