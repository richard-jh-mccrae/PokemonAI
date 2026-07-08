<!--
Strategy Proposal queue file. One or more proposals, each a `## ` entry.
Lives in data/strategy/proposals/. Producers append; update-strategy drains (status: open).
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md
-->

## <short-proposal-title>
- id: <stable-slug>
- source: <strategy-ingest | blunder-buster | deck-genie | matchup-genie | deck-align>
- target_layer: <general-hypothesis | deck-strategy | matchup-brief | planner-code>
- for: <general | deck:<deck> | opponent:<archetype>>
- candidate_signal: <Function Tag / CardStat / board-or-Context field / "needs a new signal">
- verification_contract: <verifier | score-diff | brief-validator | seed-ladder>
- provenance: <link to source doc + locator>
- status: open

**Spec (authoring spec — thin; WHAT the change must do and WHY it wins, not the finished code):**
<one short paragraph>
