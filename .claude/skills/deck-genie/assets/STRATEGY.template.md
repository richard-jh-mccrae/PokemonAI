# <Deck> — Playing Doctrine

> Phase-A deliverable of `/deck-genie`. The human-readable strategy the deck plays; the executable
> `strategy.py` is generated from this **after sign-off** (ADR-0017). Build on the
> [General Strategy](../../../docs/general-strategy.md): reuse, override, or extend — don't restate.

**Status:** `drafting | locked | shipped` · **Last grilled:** <date> · **Author:** deck-genie + <user>

## Progress checklist (resumability — keep current)

- [ ] Phase 0 facts dumped
- [ ] Phase 1 overview confirmed
- [ ] Phase 2 research synthesised + confirmed
- [ ] Phase 3 card-by-card: `<n>/<total>` cards locked
- [ ] Phase 4 General-Strategy disposition complete
- [ ] Phase 5 signed off → Phase B authorised

Cards still to grill: <list>. Open questions: <list>.

## 1 · Overview

- **Win condition:** <how the deck takes 6 prizes; the prize math given Mega-ex=3 / ex=2 / else=1>
- **Line(s):** <basic → payoff evolution path(s)> · **online at:** <energy / cheapest attack>
- **Main attacker(s):** <…>
- **Supporting Pokémon:** <openers / accelerators / walls / pivots and their jobs>
- **Engine (draw/search):** <…> · **Acceleration:** <…> · **Disruption:** <…> · **Recovery:** <…>
- **Energy:** <count, types, special-energy behaviour>
- **User context:** <anything the user supplied about playstyle / matchups>

## 2 · Research synthesis (cited)

<How the archetype is played per the web: gameplan, key combos, standard lines, matchups, tech
choices. Mark anything thinly-sourced as an assumption to confirm. Cite every source.>

**Sources:** <name — URL> · <name — URL>

## 3 · Card-by-card

One block per card. Repeat for all <total> cards. (Facts auto-filled from the dump; usage is grilled.)

### <count>× <Card name>  — <Role(s)> · tags: `<tag>`
- **Mechanics:** <from the dump — HP/weakness/retreat/prize/stage; each attack cost→damage→effect; ability text>
- **Use:** <exactly when and why it's played>
- **Sequencing:** <when in the turn / relative to other cards>
- **Combos:** <cards it enables or needs>
- **Hand interactions:** <what it wants alongside it; dead-card cases>
- **Anti-patterns:** <when NOT to play it>
- **General-Strategy disposition:** <covers-as-is `<id>` | override `<id>` @ seed `<w>` | conflicts `<id>` | gap → new `<deck-id>`>

## 4 · Combos, sequencing & opening hands

- **Combos:** <each multi-card engine: minimum hand, what breaks it>
- **Sequencing ladder (developing turn):** <default order + carve-outs>
- **Opening hands:** <dream / median / survivable; worst keepable hand; first vs second>
- **Plan mapping:** SETUP = <…> · RACE = <flips when Line ready> · STABILIZE = <behind> · CLOSE = <ahead>

## 5 · General-Strategy disposition table

| General Hypothesis | Disposition | Seed weight | Why (deck-specific reasoning) |
|---|---|---|---|
| `dig-before-commit` | covers-as-is / override / conflicts / — | — | <…> |
| … | … | … | … |

## 6 · New deck Hypotheses (drafts — trigger sketches, NOT lambdas yet)

### `<deck-hyp-id>` · seed weight <w> · status: assumed
> <rationale — plain competitive reasoning, as it will read in the decision trace>

**Trigger sketch:** <plain English referencing real Context/Board fields — e.g. "on a SETUP PLAY of
a card tagged `accel_source`">. **Reads:** <fields>. **Fires:** <plan/context>.

## 7 · Roles, Lines, params (the executable shape, pre-code)

```
roles  = { <CARD>: ["<role>"], ... }
lines  = [ Line(path=[<BASIC>, <PAYOFF>], payoff=<PAYOFF>, role="win_condition") ]
params = { "setup_energy_target": <n>, "search_budget": 0 }
```

## 8 · Open questions / deferred

<Anything needing new Context infra, unresolved matchup reads, or rules waiting on ladder evidence.>
