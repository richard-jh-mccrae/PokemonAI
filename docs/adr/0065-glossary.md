# Ubiquitous Language — the card-worth oracle (ADR-0065)

Companion vocabulary doc for ADR-0065 (not an ADR itself — same convention as `0050-glossary.md`).
Four plain words for the oracle's two independent features; use these in code, tests, commits, and
grill docs. Agreed with the user 2026-07-19.

## The two features (do not conflate)

| Term | Definition | Module | Aliases to avoid |
| --- | --- | --- | --- |
| **Worth** | What a card or action is worth to the plan, on THIS board — a valuation of common mechanics (roles, tags, ACE-SPEC, energy) with respect to board state. Has NO opinion about probability. | `common/card_worth.py` | value, score (ambiguous with the Tier-0 tactical score), currency (that's the *property* of worth being one scale, not worth itself) |
| **Odds** | The chance of having, reaching, rebuilding, or funding something, by a given draw window — pure deck math. Has NO opinion about value. | `common/deck_odds.py` | probability (fine in prose, but "Odds" is the code-facing noun), chance |

Every card/action equation in this codebase is their product:

```
value = Worth × Odds
```

- **keep_cost** = Worth × (1 − Odds of getting it back) × Gates — Odds pointed BACKWARDS (closure)
- **the gamble** = Worth of the KO × Odds of assembling the enabler — Odds pointed FORWARDS
- **tutor-chain grab** = Worth of the end target × Closure walked recursively
- **gusting** (`gusting-keepcost-design.md`) = THEIR Worth × MY Odds of removing it — Worth pointed
  across the table
- **attach / promote** (seeded, not built) = Worth of the attack/trade × Odds of funding it by a Gate

## The two supporting primitives

| Term | Definition | Module | Aliases to avoid |
| --- | --- | --- | --- |
| **Gates** | WHEN a card's Worth is live — the deadline factor. An undeployable evolution's Worth is gated to 0 (the base is provably gone); a dead fetcher (every target provably gone) likewise; a deploy-now body spikes. Evolution + fetcher (searcher/recycler) gates built; quota/pressure gates scoped, not built. | `common/gate_library.py` | deadline (fine in prose; "Gates" is the code-facing noun), timing |
| **Closure** | WHAT can reach what — the tutor/recycle/search graph over the card REPRESENTATION (`card_effects.json` FETCH clauses + `CardStat`), never a text parse. Pure graph; carries no Odds or Worth of its own. | `common/fetch_closure.py` | reach (avoid as a noun — used adjectivally, "reachable"), the graph (fine in prose) |

## Relationships

- **Worth** needs **Gates** to know if it is currently realisable (an evolution's Worth is 0 while
  its base is unreachable) — Gates is a FACTOR of Worth, not a separate valuation.
- **Odds** needs **Closure** to know the outs — a re-access probability is Odds computed over the
  Closure's target set (`fetch_closure.reaccess_outs`), not a literal-card count.
- **Worth** and **Odds** are independently reusable: `keep_cost` points Odds backwards (can I get
  it back?) where the gamble points Odds forwards (can I assemble it?); the gusting design points
  Worth across the table (their plan, not mine). Each side's reuse across four+ different
  equations is why the two stayed separate modules rather than one combined "value" module.
- A **shadow equation** (`shadow-equations-ruling.md`) is any Worth×Odds product built and emitted
  at the decision point BEFORE its swap against an existing rung family is corpus-gated — the
  emission itself carries no opinion on whether it should decide yet.

## Example dialogue

> **Dev:** "The keep-cost function takes a `reaccess_odds` parameter — is that the same thing as
> the card's worth?"
>
> **Domain expert:** "No — two different features. **Worth** is `role_value(cid)`: what the card
> is worth to the plan, full stop, no probability involved. **Odds** is
> `draw_hit_probability(outs, pool, draws)`: the chance you draw or fetch it back, no opinion about
> whether it's worth having. `keep_cost` MULTIPLIES them — Worth × (1 − Odds of getting it back)."
>
> **Dev:** "And the `outs` in that Odds call — where do those come from?"
>
> **Domain expert:** "The **Closure** — `fetch_closure.reaccess_outs` walks the tutor graph to
> count every deck-search that can pull this card back, not just its own copies. Closure is a pure
> graph query; Odds turns that count into a probability over the draw window."
>
> **Dev:** "So if I wanted an undeployable Mega ex to cost less to shuffle away — is that an Odds
> change or a Worth change?"
>
> **Domain expert:** "Neither alone — it's a **Gates** change. `gate_library.deploy_odds` factors
> INTO `keep_cost` as a third multiplier: `role_value × deploy_odds × (1 − reaccess)`. An
> undeployable evolution's Gates factor collapses to 0, so its Worth is 0 REGARDLESS of how good
> its Odds of re-access are — a dead card is cheap to shuffle no matter how easy it is to get back."

## Flagged ambiguities

- **"Value"** in casual conversation can mean Worth, the Worth×Odds product, or the Tier-0
  tactical score (a different, older currency — KO_SCORE-scaled, not Worth-scaled). Say **Worth**
  when you mean the card_worth tier, and **tactical score** for the Tier-0 number; "value" alone in
  code/commits should be avoided once this glossary lands.
- **"Closure" vs "reachability"** — Closure is the noun for the module/graph; "reachable" is the
  adjective for a specific target (`fetch_target_matches` returns whether ONE target is reachable
  from ONE clause). Don't say "the reachability module."
- **"Gate" (singular) vs "the gate library"** — a single Hypothesis stand-down that happens to be
  deadline-shaped (e.g. the retired `hold-successor-when-doomed`) is NOT automatically "a Gate" in
  this vocabulary unless it is implemented as a `deploy_odds`-style factor inside Worth. Card-fact
  deadline predicates that live as rung `when=` conditions (e.g. seam B's
  `dont-fetch-before-the-deadline`) are deadline logic but outside the Gates module until/unless a
  future convergence folds them in — say "a deadline predicate," not "a Gate," for those.
