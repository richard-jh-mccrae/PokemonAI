# Phase B — emit the Brief JSON (gated; human commits)

Only after `docs/matchups/<slug>.md` is signed off. This turns the locked doctrine into the machine
`src/common/scouting/briefs/<slug>.json` the Read/Posture layer consumes, and proves it before the human
commits. It's the counterpart to deck-genie's Phase B — but the Brief is *data*, not code, so the gate is
a deterministic validator, not per-Hypothesis trigger checks.

## 1 · Author against the LIVE inputs — never from memory

- **`data/meta/decks/<slug>/deck.csv`** — the deck the threats/targets must reference. Every `threat` /
  `target` card name must be a card actually in this list (the validator enforces it).
- **`data/meta/decks/index.json`** — the `label` and **`covers`** for this slug. Copy `covers`
  **verbatim**; it's what routes every variant to this one Brief (the Read matches `read.candidates[0]`
  against it). Don't hand-edit it.
- **[assets/opponent_properties.json](../assets/opponent_properties.json)** — the registered lever keys.
  Reuse one where it fits; mint a new key only when nothing does.
- **[assets/brief.schema.json](../assets/brief.schema.json)** — the Brief shape.

## 2 · Map the locked doctrine to the Brief

| Doc section | Brief field |
|---|---|
| §1 how-it-wins tempo | `tempo` (`fast`/`midrange`/`slow`) + `summary` |
| §3 seam → `opponent_properties` | `opponent_properties: { "<key>": <value> }` — each key registered |
| §4 threats | `threats: [ { card, why } ]` |
| §4 targets | `targets: [ { card, role, why } ]` — role ∈ `fragile_preevo` / `prize_liability` / `engine` |
| index.json | `slug`, `label`, `covers` (verbatim) |
| §2 sources | `sources: [ "name — url" ]` |

**Minting a new `opponent_properties` key** is a real event: add it to
`assets/opponent_properties.json` with `consumer: "unwired"` and a `note` describing the lever it *will*
drive, and **call it out in the diff** — the consumer must wire it before it does anything. Until then
the key is an inert forward contract. Prefer reusing an existing key; the vocabulary stays small on
purpose. **Asserting a WIRED key is a high-bar call** — check the registry's `consumer` field: e.g.
`opp_is_engine_dependent` drives the ADR-0038 engine lever, and the stress A/B priced a wrong assertion
at ~4% win-rate. Assert only what the weakness grill actually established.

## 3 · Gate — the deterministic validator

```
python .claude/skills/matchup-genie/scripts/validate_brief.py <slug>
```

It hard-fails on: missing/mistyped required fields; `slug` ≠ filename; empty `covers`; a `covers` string
already covered by ANOTHER shipped Brief (`match_brief` routes alphabetically-first — a collision
misroutes silently; ADR-0038 hardening); a `threat`/`target` card **not present in the deck** (catches
typos / hallucinated cards — the analogue of deck-genie's trigger checks); an illegal `target` role. It
**warns** (does not fail) on: `covers` diverging from `index.json` (the meta regenerates, so a drift is
worth a look, not a block); an `opponent_properties` key not in the registry (mint it, don't ignore it).
Fix every hard failure; resolve every warning consciously.

## 4 · Suite-green (cheap safety)

`python -m pytest tests/ -q` should stay green. A Brief is LIVE data since ADR-0038 — the Pilot's
`brief_preevo`/`brief_engine` levers score off its `fragile_preevo`/`engine` targets and
`opp_is_engine_dependent` (see docs/scouting.md's consumer table) — and the suite pins the shipped
dir's covers-collision freedom, so run it, don't assume.

## 5 · Present the diff — the human commits

Show `src/common/scouting/briefs/<slug>.json` (+ any `assets/opponent_properties.json` additions) as a
diff, with a one-line note: the archetype, its `covers` count, the seams it encodes (`opponent_properties`
keys), and the validator result. Note any newly-minted key as "needs consumer wiring." The human reviews
and commits. The Brief's effect on play is confirmed later by A/B (ADR-0038's evidence gate) — the wired
levers (`fragile_preevo`/`engine` targets, `opp_is_engine_dependent`) act as soon as the Brief ships;
the skill never self-validates gameplay impact.

**Commit-message convention:** every matchup-genie commit message **begins with `matchup: `** (e.g.
`matchup: Cinderace / Mega Starmie ex counterplay doctrine`). This applies whether the human commits or
the skill drafts/squashes the commit — the prefix namespaces the Brief work in the log. Keep the rest
terse + imperative.

## Anti-patterns

- A `target`/`threat` card the deck doesn't run — the validator hard-fails it; ground every card in the dump.
- A relativized Brief ("good for our Cinderace") — the Brief is objective + shared; relativization is the
  agent's job (`/deck-genie`).
- Editing `covers` by hand — it must match `index.json` so variants route correctly.
- Minting an `opponent_properties` key silently — always register + flag it; an unregistered key is a
  dangling contract nothing will ever read.
- Precision-inventing a lever's effect — you assert the *weakness* (a fact about the deck); the *lever
  strength* is the consumer's + the ladder's job later.
