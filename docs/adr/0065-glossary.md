# Ubiquitous Language — the card-worth oracle (ADR-0065)

Companion vocabulary doc for ADR-0065 (not an ADR itself — same convention as `0050-glossary.md`).
Six plain words: the umbrella quantity (**Value**, ratified 2026-07-20) over five independent
features (Worth · Odds · Gates · Closure · Needs — Needs ratified 2026-07-19, built WP-N1–N8); use
these in code, tests, commits, and grill docs. Agreed with the user 2026-07-19/20.

## The two features (do not conflate)

| Term | Definition | Module | Aliases to avoid |
| --- | --- | --- | --- |
| **Worth** | What a card or action is worth to the plan, on THIS board — a valuation of common mechanics (roles, tags, ACE-SPEC, energy) with respect to board state. Has NO opinion about probability. | `common/card_worth.py` | value, score (ambiguous with the Tier-0 tactical score), currency (that's the *property* of worth being one scale, not worth itself) |
| **Odds** | The chance of having, reaching, rebuilding, or funding something, by a given draw window — pure deck math. Has NO opinion about value. | `common/deck_odds.py` | probability (fine in prose, but "Odds" is the code-facing noun), chance |

## The umbrella term: Value (ratified with the user 2026-07-20)

**Value** = what a card or body means RIGHT NOW — its Worth shaped by the situation (Needs, Odds,
Gates), asked of a SPECIFIC QUESTION at a specific moment. One quantity, many questions:

| Question | Asks | The site |
| --- | --- | --- |
| **keep** Value | what do I lose if this card leaves my hand? | the discard decider, the refresh SHED, the gamble floor |
| **deny** Value | what do I gain by removing/dragging THEIRS? | the gust target pick, the Hammer, the deny slots |
| **attach** Value | which body does this Energy advance most? | the attach oracle (seeded, `attach-valuation-grill-spec.md`) |
| **snipe** Value | which of their bodies does damage deny most? | the snipe target pick |

The word "keep-value" is NOT the umbrella — it is the keep QUESTION's Value and nothing more (the
2026-07-20 correction: the keep-value-v2 line's name made the one variant sound like the whole).
Say **Value** for the contextual quantity, **Worth** for the context-free tier underneath it, and
name the question when it matters ("the Mega's keep Value", "their Staryu's deny Value"). Code
symbols keep their question-specific names (`keep_v2`, `keep_cost`, the gust tacticals) — they name
questions correctly; only umbrella USAGE changes.

Every question's equation is the same product:

```
Value(question, moment) = Worth × Odds × Gates    (Needs supplying WHICH worth is live)
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
| **Gates** | WHEN a card's Worth is live — the deadline factor. An undeployable evolution's Worth is gated to 0 (the base is provably gone); a dead fetcher (every target provably gone) likewise; a doom-answering card under pressure SPIKES to full worth (the closing edge); a duplicate of a once-per-turn card sheds by rank (the quota window). All four legs built 2026-07-18/19. | `common/gate_library.py` | deadline (fine in prose; "Gates" is the code-facing noun), timing |
| **Closure** | WHAT can reach what — the tutor/recycle/search graph over the card REPRESENTATION (`card_effects.json` FETCH clauses + `CardStat`), never a text parse. Pure graph; carries no Odds or Worth of its own. | `common/fetch_closure.py` | reach (avoid as a noun — used adjectivally, "reachable"), the graph (fine in prose) |
| **Needs** | WHAT the position requires — deadline-tagged slots derived from board state (fund-attack, evolve-now, answer-the-doom, quota turns, discard-fuel; opponent-side from visible zones + turns-to-ready lookahead). A card's keep-value is its MARGINAL slot coverage under exact assignment (`keep_v2` — the counterfactual with re-assignment); Gates re-derive as "a slot with a deadline" and dissolve as each re-derives (the DISSOLUTION LEDGER). **Ratified 2026-07-19 (keep-value v2 grill); WP-N1–N5 built** — the module, the exact-assignment engine, the Pilot resolver (`pilot._needs_v2`/`_resolve_needs`), the DISCARD DECIDER SWAP (`Pilot.needs_keep_value` armed ON — v2 decides the forced discard, superseding v1), the refresh-SHED MAGNITUDE shadow (which proved v2 not-yet-ready there), and the general-worth slot (latent hand worth on the leaf's `contribution × saturation` terms, halving the refresh under-pricing). The readiness-leaf fold (WP-N5b, blocked on hand-visibility plumbing) + the gamble/refresh swaps stay staged; the gate stack stays live for those sites — `keep-value-needs-assignment-grill-spec.md`. | `common/needs.py` | needs list / wants (say Needs/slots), gate (during the transition — a gate is a derived VIEW of a slot) |

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

- **"Value"** — RESOLVED 2026-07-20 (see the umbrella section above): Value IS the ratified name
  for the contextual Worth×Odds×Gates quantity, qualified by its question (keep/deny/attach/snipe).
  Two residual cautions: say **Worth** when you mean the context-free tier, and **tactical score**
  for the Tier-0 number (a different, older currency — KO_SCORE-scaled, not Worth-scaled); bare
  "value" without a question is still ambiguous in code — qualify it.
- **"Closure" vs "reachability"** — Closure is the noun for the module/graph; "reachable" is the
  adjective for a specific target (`fetch_target_matches` returns whether ONE target is reachable
  from ONE clause). Don't say "the reachability module."
- **"Gate" (singular) vs "the gate library"** — a single Hypothesis stand-down that happens to be
  deadline-shaped (e.g. the retired `hold-successor-when-doomed`) is NOT automatically "a Gate" in
  this vocabulary unless it is implemented as a `deploy_odds`-style factor inside Worth. Card-fact
  deadline predicates that live as rung `when=` conditions (e.g. seam B's
  `dont-fetch-before-the-deadline`) are deadline logic but outside the Gates module until/unless a
  future convergence folds them in — say "a deadline predicate," not "a Gate," for those.
