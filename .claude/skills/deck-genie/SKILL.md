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
   - `src/common/general_strategy.py` + `docs/general-strategy.md` — the ~20 deck-agnostic
     Hypotheses you'll reconcile against. Know them cold before grilling.
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

### Phase 2 · Wide web research (cited)

Search the web for how this archetype is actually played. Query the payoff + signature cards (e.g.
"Mega Starmie ex deck guide", "Cinderace Turbo Flare combo"). Look for: the core gameplan, optimal
sequencing, key combos, standard opening lines, matchup notes, tech-card reasoning. Fetch the 2–4
best sources and **synthesise with citations** into the doc's Research section — this project cites
its strategy sources (mirror the `docs/general-strategy.md` bibliography).

These sets can be bleeding-edge with thin coverage. When you can't find solid sourcing, **say so and
flag the gap as an assumption to confirm** — never paper over it with invented lines. Present the
findings; the user confirms or corrects. Their correction outranks the web.

**Verify card-interaction legality against the actual card text, not the guide.** Web articles
routinely get tutor targets / evolution eligibility / "this can't be fetched" wrong — e.g.
confusing "has no Ability" with "has no attacks or effects." When a claim hinges on a rules
interaction, check it against the engine facts (or an engine probe) and surface the conflict for the
user rather than adopting it. If the **Workflow** tool is available, a fan-out research pass
(parallel search angles → deep-read → adversarially verify each claim against the card facts → cited
synthesis) is a strong fit and catches exactly these misreads; plain inline web search is the
fallback when subagents aren't available.

### Phase 3 · Exhaustive card-by-card grill (the heart)

Go through **every** card and lock exactly how it's meant to be used. **Open each card's block with
its mechanical profile pulled straight from the dump — CardStat (HP / weakness / retreat / prize /
stage), its `card_functions.json` tags, and the full cost / damage / effect text of every attack and
ability — so the mechanics are unambiguous before you grill usage.** Read
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

As each card's usage locks, record its disposition against the General Strategy. For every relevant
general Hypothesis, pick one:

- **covers-as-is** — the general rule already handles this; name it, do nothing.
- **override-candidate** — the deck wants this rule stronger/weaker/off; record a **seed weight**
  override by id (banded per [docs/weights.md](../../../docs/weights.md)). Seeds are starting
  points the ladder later tunes — that's allowed; inventing a *final* number is not the goal.
- **conflicts** — the general rule actively misplays this deck; note why (candidate for override
  to a low/zero weight, or a deck rule that outweighs it).
- **gap → new deck Hypothesis** — nothing general covers it. Draft it: `id`, `rationale`,
  plain-English **trigger sketch** (referencing real `Context`/`Board` fields — see
  [references/authoring.md](references/authoring.md)), seed weight, `status="assumed"`.

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
