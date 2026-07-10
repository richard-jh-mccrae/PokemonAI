# Multi-step lethal verification (ADR-0050)

The Lethal Solver proves a win real by forking the native engine from an observation's
`search_begin_input`, stepping a candidate line, and driving the follow-up selects through the pilot's
own `decide()` to the engine's verdict (`_engine_confirms_win`, `src/common/strategy/planner.py`). This
note is the operator's guide to the two pieces ADR-0050 added so that **multi-step** lines
(retreat/tutor/fetch/attach compositions) verify end-to-end offline.

## The seeding fix (Phase 1)

The engine verify predicts my hidden zones for `search_begin`. It used to seed them with an id-sorted
**decklist prefix** (`self.deck[:n]`), which — because `deck.csv` is id-sorted — hid the high-id utility
band (retreat Tools, gusts, boosters) and false-refuted any line that fetched one.

`Pilot._seed_zones` now seeds the **exact** remaining split from the deck tracker: `your_deck` =
`decklist − visible − prizes` (`_deck_known_counts`), `your_prize` = `obs['own_prizes']`. This is exact
whenever the tracker has anchored the prizes (mid-game, post first search reveal) — which is exactly
when a fetch line is even generated (the fetch tiers gate on `deck_definitely_has`). Unanchored, it
falls back to the prefix; that is sound because only non-fetch lines, whose verdict is
deck-independent, reach the search pre-anchor.

- **Never seed the deck+prize pool into `your_deck`.** Over-counting a prized copy into the deck could
  let the engine fetch a card that is actually all prized and **false-confirm a phantom win** — the one
  catastrophic Solver error. The exact split is the soundness.
- Kill-switch: `lethal_seed_exact` (param, default **on**; `main.py` for all three agents). Off = the
  old prefix behavior.

## The tool (Phase 2)

- **Backfill** — `python tools/train/backfill_seed.py` adds `search_begin_input` (content-joined from
  the replay's step observation; the film obs a Correction stores is seed-stripped) and the exact
  `own_prizes` (replaying the seat's history through `OwnCardModel`) to correction fixtures, so a
  single captured frame becomes cascade-ready. New captures get both by default.
- **Probe** — `python tools/sim/lethal_probe.py <fixture.json> --agent <deck> --step <i>` dumps every
  follow-up select the policy reaches after the first step, with each option's resolved `card_id` /
  `inPlayArea` / `inPlayIndex`. Author follow-up-steering hooks against these real encodings, never
  guesses.
- **Gate** — `tests/lethal_helpers.py::engine_confirms(fixture, pilot)` drives a seeded fixture's line
  through the cascade and returns the verdict (`True` win / `False` refuted / `None` undetermined or
  no seed). It is the end-to-end gate for multi-step lethal proposals
  (`update-strategy/references/authoring-gates.md`, `planner-code`): a closed-form-only line that would
  pass a seed-less unit retest returns `False` here.

## Worked example — correction 84071010:f15 (the deferred `lethal-retreat-enabler`)

Active Makuhita (retreat 2, 0 energy) blocks a benched Mega Lucario ex; opponent Active Riolu (80 HP),
bench empty. The win: Team Rocket's Petrel (tutor a Trainer) → **Air Balloon** (−{C}{C} retreat) → play
it onto Makuhita → free-retreat → promote Mega Lucario ex → Aura Jab 130 ≥ 80 → **WIN** (hand-verified
through the engine). Of the deck's two Air Balloons one is prized; exact seeding puts the one
deck-certain copy in the tutor menu (the prefix hid both, id 1174 sitting past `deck[:44]`). Building
the follow-up hooks so `decide()` drives this line — and gating them on
`engine_confirms(f15) is True` — is the Phase-3 consumer this tool unblocks.
