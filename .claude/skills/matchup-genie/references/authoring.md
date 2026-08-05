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
- **[src/common/scouting/opponent_properties.json](../../../../src/common/scouting/opponent_properties.json)** — the registered lever keys.
  Reuse one where it fits; mint a new key only when nothing does.
- **[src/common/scouting/brief.schema.json](../../../../src/common/scouting/brief.schema.json)** — the Brief shape.

## 2 · Map the locked doctrine to the Brief

| Doc section | Brief field |
|---|---|
| §1 how-it-wins tempo | `tempo` (`fast`/`midrange`/`slow`) + `summary` |
| §3 seam → `opponent_properties` | `opponent_properties: { "<key>": <value> }` — each key registered |
| §4 threats | `threats: [ { card, why } ]` |
| §4 targets | `targets: [ { card, role, why } ]` — role ∈ `prize_liability` / `fragile_preevo` / `disruption_target` / `attacker` / `enabler` / `engine` (neutral) / `avoid` (see SKILL.md for the semantics; all feed the ADR-0051 MatchupPlan, and the closed registry is `matchup_plan.ROLE_REGISTRY` — an undeclared role fails the vocabulary lint, Issue #395) |
| index.json | `slug`, `label`, `covers` (verbatim) |
| §2 sources | `sources: [ "name — url" ]` |

**Minting a new `opponent_properties` key** when no existing key fits is a **default action, not a user
question** — mint it: add it to `src/common/scouting/opponent_properties.json` with `consumer: "unwired"` and a `note`
describing the lever it *will* drive, and **call it out in the diff**. A minted key is cheap, inert data
(a forward contract) — the consumer must wire it before it does anything, so until then it changes no
play. Prefer reusing an existing key first; the vocabulary stays small on purpose (reuse-first, not
mint-rarely). Do **not** build the consumer here — that's evidence-gated downstream (ADR-0026).
**Asserting a WIRED key is a high-bar call** — check the registry's `consumer` field and assert only a
key whose consumer is actually live, since a wrong assertion changes real play (a stress A/B once priced
a wrong assertion at ~4% win-rate). Assert only what the weakness grill actually established. (Historical
note: `opp_is_engine_dependent` drove the old ADR-0038 engine lever, now RETIRED — engines are hunted via
the `disruption_target` target role, ADR-0051; that key is UNWIRED again.)

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

`python -m pytest tests/ -q` should stay green. A Brief is LIVE data — the Pilot resolves its
`targets` roles into the ADR-0051 **MatchupPlan** spine, consumed by the bench snipe
(`_snipe_matchup_tactical`), the gust target pick (`_gust_matchup_priority`), and the wincon-denial gust
(`_gust_wincon_denial`), all γ-gated under the single `matchup_targeting` kill-switch (the old
ADR-0038 `brief_preevo`/`brief_engine`/`opp_is_engine_dependent` levers are retired). The suite also pins
the shipped dir's covers-collision freedom, so run it, don't assume.

## 5 · Present the diff — the human commits

Show `src/common/scouting/briefs/<slug>.json` (+ any `src/common/scouting/opponent_properties.json` additions) as a
diff, with a one-line note: the archetype, its `covers` count, the seams it encodes (`opponent_properties`
keys), and the validator result. Note any newly-minted key as "needs consumer wiring." The human reviews
and commits. The Brief's effect on play is validated later on the ladder (ship-and-refine) — the
MatchupPlan spine acts on its `targets` roles as soon as the Brief ships (`matchup_targeting` default ON,
γ-gated); the skill never self-validates gameplay impact.

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
