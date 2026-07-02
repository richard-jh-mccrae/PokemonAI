---
name: deck-genie
description: >
  Build a deck's complete playing doctrine for the PokemonAI Pilot, end to end, from its
  deck.csv + deck.txt. Produces a grilled, research-backed STRATEGY.md doctrine doc and then —
  only after you sign off — the executable, gated src/agents/<deck>/strategy.py ready to play.
  Use this whenever the user wants to author, design, plan, or deeply think through how a
  specific deck/agent should be played: "build the strategy for <deck>", "write the doctrine for
  this agent", "how should mega_starmie play", "grill me on this deck", "/deck-genie <deck>", or
  when a new agent dir has a deck.csv with no real strategy.py yet. This is the deck-LEVEL
  counterpart to the deck-agnostic General Strategy. Do NOT use it for tuning weights from blunder
  corrections (that's /blunder-buster) or for tagging card functions (that's the card-functions
  pipeline).
---

# deck-genie — author a deck's playing doctrine

Turn a deck (`deck.csv` + `deck.txt`) into a coherent, intensely-grilled playing strategy for the
Pilot — first as a human-readable **STRATEGY.md doctrine doc**, then (after sign-off) as the
executable **`strategy.py`** the agent actually plays. The doctrine is built on top of the existing
[General Strategy](../../../docs/general-strategy.md): you decide which general Hypotheses already
cover this deck, which to override, and where the deck needs a brand-new rule.

**Invocation:** `/deck-genie <deck>` (e.g. `/deck-genie mega_starmie`). Any extra prose the user
adds is deck context (intended playstyle, known matchups, pet lines) — fold it into Phase 1.

## The two phases and the one gate (read first — this is the ADR-0017 contract)

The deliverable arrives in two phases with **your explicit sign-off** as the gate between them:

- **Phase A → `src/agents/<deck>/STRATEGY.md`** — the doctrine: overview, cited research,
  exhaustive card-by-card usage, combos/sequencing/opening hands, and a General-Strategy
  disposition table. Every new rule is written as `id` + `rationale` + a *plain-English trigger
  sketch* + seed weight. **No executable lambdas yet.** We grill this until it's locked.
- **Gate** — present the finished doc, resolve the last contradictions, get an explicit "ship it."
- **Phase B → `src/agents/<deck>/strategy.py`** — only now translate the locked doctrine into real
  `when()` lambdas, Roles, Lines, params; validate against the three gates below; present a diff.
  **The human commits.**

Why this shape: [ADR-0017](../../../docs/adr/0017-corrections-compile-to-hypotheses.md) rejects
*unreviewed* auto-written `when()` — not executable strategy itself. `/blunder-buster` already
writes executable triggers; it's allowed because they're **gated and human-committed**. Here the
intense grill **is** the review, and the gates are deterministic. Writing lambdas before the doc is
locked is the thing the ADR forbids — don't.

## Workflow

Phases 3–4 interleave (you reconcile a card against the General Strategy the moment its usage
locks). The grilling discipline and the per-category question banks live in
[references/grilling-playbook.md](references/grilling-playbook.md) — read it before Phase 3.

### Phase 0 · Orient (deterministic — do this silently, then show Phase 1)

1. Confirm `src/agents/<deck>/deck.csv` and `deck.txt` exist.
2. **Dump the facts — this is the mechanical basis for every card discussion** (the engine is ground
   truth; the committed `cards.json` is stale, so never hand-transcribe HP / cost / attack text):
   `python .claude/skills/deck-genie/scripts/dump_deck.py <deck>`
   It joins **three** sources per card and prints a category-organised overview — pull all three, a
   stat block alone or a tag alone is not enough to understand a card:
   - **engine `CardData` stats** — HP, weakness, resistance, retreat, prize value, stage,
     ex/megaEx/tera/aceSpec, evolvesFrom;
   - **engine `Attack` data** — every attack's exact energy **cost**, **damage**, and full effect
     **text**, plus each ability's name + text;
   - **`card_functions.json`** — the behavioral **function tags** (`draw`, `search`, `energy_accel`,
     `clutch_heal`, `discard_eot`, `rush_evolve`, …) that the General Strategy fires on.
   Capture it into the working doc verbatim — it's the substrate. **Ground every mechanical claim in
   this dump, never in memory or a web guide.** (`--json` emits the machine form if you need it.)
3. **Read what already exists**, so you build on it rather than reinvent:
   - `src/common/strategy/baseline/baseline_*.py` (clustered by decision-context; ADR-0025) +
     `docs/general-strategy.md` — the deck-agnostic Hypotheses you'll reconcile against. Know them
     cold before grilling.
   - `src/agents/<deck>/strategy.py` — a prior pass may already have Roles/Lines/Hypotheses.
   - `src/agents/<deck>/STRATEGY.md` — **if it exists, you're resuming.** Read its progress
     checklist and pick up where it left off; don't restart.
4. Start (or reopen) `STRATEGY.md` from [assets/STRATEGY.template.md](assets/STRATEGY.template.md).

### Phase 1 · Deck overview (present, then confirm)

From the dump, organise the deck and present a tight overview — don't just relay the dump, *read*
it:

- **Win condition & Line(s)** — the evolution path(s) basic → payoff, and how the deck takes 6
  prizes given prize values (Mega-ex = 3, ex = 2, else 1). This becomes `Strategy.lines`.
- **Main attacker(s)** vs **supporting Pokémon** (openers, accelerators, walls, pivots).
- **Trainers by purpose** — group the Supporters/Items/Tools/Stadium by what they *do* (draw,
  search, bench-fill, gust, disruption, recovery, rush-evolve…), reading the function tags.
- **Energy** — count, types, and any special Energy (e.g. discard-at-EOT) and what it enables.

Fold in the user's extra context. Then **ask them to confirm the win condition and their read of
the deck's gameplan** before you spend a research pass — a wrong premise here poisons everything
downstream.

### Phase 2 · Aggressive parallel web research (cited — the default, not optional)

These decks are **well-known, well-documented, highly competitive** meta lists — there is *lots* of
coverage, and **every single card is in the list on purpose.** The bar here is to know **exactly why
and how** each card is used, sourced — fast and thorough. So **fan out as many research agents as the
deck needs and run them concurrently**; a single inline web search is not enough.

Build **three research streams** from the Phase-0 dump + the Phase-1 overview, then fan them all out
**at once**:

1. **Archetype sweep** — search angles keyed to the payoff + signature cards: core gameplan, optimal
   sequencing, key combos, standard opening lines (first vs second), matchup notes, tech-card
   reasoning, and current decklist ratios. (e.g. `"<payoff> deck guide"`, `"<archetype> combo turn 1"`.)
2. **Per-confusing-card deep dives (point 3)** — list **every card whose purpose isn't self-evident**
   from its tags + the win condition: off-type tech, a lone 1-of, an attacker that isn't the payoff,
   anything that makes you ask *"why is THIS here?"* (the canonical case: a **Munkidori in a Dragapult
   deck**). Give **each** its own agent that web-searches the card **by name in this deck's context**
   and returns its job, companion cards, setup, sequencing, and anti-patterns. A card you can't
   explain is a card to deep-dive.
3. **Trainer-by-trainer purpose (point 4)** — **every** Supporter / Item / Tool / Stadium / special
   Energy gets a purpose agent. Generic staples get a terse standard purpose; deck-specific or unusual
   inclusions (and odd counts) get searched. None are skipped — every trainer is there on purpose.

**Primary path — the shipped research workflow** (if the `Workflow` tool is available; invoking this
skill *is* the opt-in to run it). It fans out all three streams concurrently, deep-reads the sources,
**adversarially verifies every claim against the engine card facts**, and returns a cited synthesis +
a list of web-vs-facts `conflicts`:

```
Workflow({ scriptPath: ".claude/skills/deck-genie/scripts/research.js", args: {
  deck:            "<deck>",
  gameplan:        "<the CONFIRMED Phase-1 overview / win condition>",
  facts:           "<the full Phase-0 dump markdown — ground truth>",
  angles:          [ { key: "gameplan",   q: "..." }, { key: "combos", q: "..." }, ... ],
  confusing_cards: [ { name: "Munkidori", why: "off-type; not the payoff" }, ... ],
  trainers:        [ { name: "Buddy-Buddy Poffin", tags: "search,bench_fill" }, ... ],
}})
```

**Fallback — no Workflow:** fan the same three streams out with parallel `Agent` calls (one batch of
tool calls), then **verify each claim against the engine facts yourself** before adopting it. Don't
collapse to one sequential search — keep it parallel and exhaustive.

**Land the results in STRATEGY.md §2** with citations (mirror the `docs/general-strategy.md`
bibliography). The per-card and per-trainer purpose findings **seed the Phase-3 card blocks** so the
grill opens already knowing each card's researched job — you confirm/refine rather than start cold.

**Guards (unchanged and load-bearing):**
- **Engine facts override the web.** These are Scarlet & Violet *Mega-era* cards as the **simulator**
  implements them — stats, costs, attack text and rules deltas differ from the real TCG (and from
  Pocket). Web guides describe the real game; use them for **purpose and strategy** (which transfer),
  never for **mechanics** (which the dump owns). The workflow surfaces `conflicts` for you; on the
  fallback path, **verify card-interaction legality against the actual card text, not the guide** —
  articles routinely get tutor targets / evolution eligibility wrong (e.g. "has no Ability" ≠ "has no
  effects"). Surface every conflict to the user.
- **Thin coverage → flag the gap, never invent.** Some lines are bleeding-edge; if sourcing is thin,
  say so and mark it an assumption to confirm. Keep the synthesis's `confidence` honest.
- **The user outranks the web.** Present the findings; their correction wins, and you record why.

### Phase 3 · Exhaustive card-by-card grill (the heart)

Go through **every** card — **every Pokémon AND every trainer/energy** (point 4: no trainer is
skipped) — and lock exactly how it's meant to be used. **Open each card's block with its mechanical
profile pulled straight from the dump — CardStat (HP / weakness / retreat / prize / stage), its
`card_functions.json` tags, and the full cost / damage / effect text of every attack and ability — so
the mechanics are unambiguous before you grill usage**, *and* with its **researched purpose from Phase
2** (the per-card / per-trainer findings) on the table — so you open already knowing the card's job
and grill to confirm/refine, not from cold. Read
[references/grilling-playbook.md](references/grilling-playbook.md) for the per-category question
banks and the discipline (one card/branch at a time; resolve it before moving on; build off the
General Strategy + research and make the user *confirm*, don't lecture). For each card capture:
intended **Role**, when to play it, **sequencing** priority, **combos** it enables, **hand
interactions**, and **anti-patterns** (when NOT to).

Then grill the cross-card structure that wins games:
- **Combos & sequencing ladders** — what plays in what order on a developing turn.
- **Opening hands** — mulligan keeps; ideal vs survivable turn-1/2 lines going first vs second.
- **Plan mapping** — what SETUP / RACE / STABILIZE / CLOSE look like for *this* deck, and what
  flips the Line to `ready` (the engine derives readiness from the payoff's cheapest attack cost —
  confirm that's right for this deck or set `Ready(energy=…)`).

### Phase 4 · General-Strategy reconciliation (interleaved with Phase 3)

The deck-agnostic **baselines + doctrines** under `src/common/strategy` (read in Phase 0) **likely
already cover most of this deck** (point 5) — draw, search, energy, snipe, promote, retreat, evolution,
heal, gust, fetch, shuffle-refresh. **Default to `covers-as-is`;** reach for a deck rule only where
nothing general fits. As each card's usage locks, record its disposition against the General Strategy:

- **covers-as-is** — the general rule already handles this; name it, do nothing.
- **override-candidate** — the deck wants this rule stronger/weaker/off; record a **seed weight**
  override by id (banded per [docs/weights.md](../../../docs/weights.md)). Seeds are starting
  points the ladder later tunes — that's allowed; inventing a *final* number is not the goal.
- **conflicts** — the general rule actively misplays this deck; note why (candidate for override
  to a low/zero weight, or a deck rule that outweighs it).
- **gap** — nothing general covers it. Draft the rule (`id`, `rationale`, plain-English **trigger
  sketch** over real `Context`/`Board` fields — see [references/authoring.md](references/authoring.md),
  seed weight, `status="assumed"`) and decide **where it lives** by the rule below.

**The expand-vs-override decision (point 6) — where a new rule lives, priority-ordered.** Once the
outline is solid, compare the deck's target strategy against the general one and, for each gap, pick:

1. **Expand the General Strategy (the DEFAULT — ADR-0034).** If the rule's trigger reads **only
   universal vocabulary** (`tags` / `stat` / `board` signals / `roles` / `params`), it lives in the
   general layer — the matching `src/common/strategy/baseline/baseline_<context>.py` cluster or
   doctrine (ADR-0025), under a card-name-free id. **Role-keyed IS general**: the deck opts in by
   assigning the Role — the rule stays silent for decks that don't (precedent: the entire
   mega_starmie fold, 2026-07-02 — the deck now ships `hypotheses=[]`). A deck-intent judgment with
   no structural derivation becomes a **param** a general selector honors (`preferred_start` →
   `honor-preferred-start`). Per-deck strength stays tunable by id via `tuned.json` (ADR-0009).
2. **Deck Hypothesis (the justified exception).** Only when the trigger genuinely needs deck-local
   knowledge NO declaration (Role / Line / param / tag) can carry — and say WHY in the rationale.
   A shipped deck rule is a standing **folding candidate**: once its vocabulary proves general,
   fold it (score-equality gated via `tools/sim/score_diff.py` — capture before, diff after).

Also fill `roles` (the per-deck intent overlay), `lines`, and `params`. Everything lands in
STRATEGY.md — nothing executable yet.

### Phase 5 · Lock & sign-off (the gate)

Present the finished STRATEGY.md. Hunt for the last contradictions (a sequencing rule that fights a
disposition; a combo with no supporting rule). Get an **explicit sign-off**. Do not proceed to
Phase B without it.

### Phase 6 · Phase B — executable strategy.py (gated; human commits)

Read [references/authoring.md](references/authoring.md) and follow it. In short: translate the
locked doctrine into real `when()` lambdas + Roles + Lines + params, authored against the **live**
source (never from memory), then pass all three gates before presenting a diff:

1. **Per-Hypothesis trigger checks** — for each authored rule, build a hand-made observation (like
   `tests/pilot_helpers.py`) proving its `when()` **fires on the intended decision** and **doesn't
   misfire** on an obvious counter-case. This is the from-scratch analogue of the blunder Verifier.
2. **Suite-green** — `python -m pytest tests/ -q` must stay green (catches over-firing on existing
   behaviour / Playability regressions).
3. **Playability** — `python tools/sim/check_agent.py <deck>` (a full self-match + the packaged
   Bundle): no crash, timeout, or illegal move. This is the literal "ready to be played" bar.

Present the diff (strategy.py + the trigger-check test file). The human reviews and commits.
`status` stays `assumed`/`testing`; the ladder A/B confirms or refutes later.

**End state (point 7): a complete, ladder-ready agent.** When the three gates pass, `src/agents/<deck>/`
is a packaged agent — `strategy.py` (its own grilled, research-backed doctrine) + `main.py` Bundle —
that loads, tests green, and survives a full self-match. That is the literal "ready to submit to the
ladder" bar; the deliverable isn't done until it clears it.

## Resumability

An exhaustive grill spans sessions. STRATEGY.md's **Progress checklist** is the source of truth for
what's done vs pending. On re-invoke: re-run the dump (cheap, deterministic), read the doc, resume
from the checklist. Never silently restart a deck that already has a doc in progress.

## Guardrails

- **Doc before code.** No executable `when()` until the doc is signed off (ADR-0017).
- **Engine is ground truth** for card facts; **the user is ground truth** for intent; the **web is
  a prior**, not an authority. When they conflict, the user wins and you record the reasoning.
- **Prefer universal features** (`tags`, `roles`, `board`, `stat`) over hard-coded `card_id`s in
  triggers — a rule that reads a tag generalises; a rule that reads an id is brittle. Use ids only
  for genuinely deck-specific lines.
- **Don't invent `ctx` features** — a trigger may only read what `Context`/`Board` actually expose.
- **Never override a Knock Out with a positional rule** — a KO is worth more than any heuristic
  (see [[forgo-ko-corrections-are-refuted]]). If a drafted rule would suppress a lethal, it's wrong.
