# Synthesis — Fetched Article → Strategy Digest

Source-agnostic. Reads a **Fetched Article** (any adapter), writes
`data/strategy/<handle>_<slug>_strategy.md` from
[assets/STRATEGY_DIGEST.template.md](../assets/STRATEGY_DIGEST.template.md). Precondition:
`access == complete` — never run on a paywalled/truncated/no-transcript Fetched Article.

## The prime directive

The Digest is the **input to a later grill**, not a weight change. Your job is to distil the author's
strategy into clean, scope-tagged English claims with signal *hints* — never to author Hypotheses, mint
ids, or assign weights. Weights are ladder-tuned seeds ([weights.md](../../../../docs/weights.md)); a weight
guessed from an article is noise the grill must discard. Stay honest: you are summarizing someone else's
prose, not inventing the agent's internals.

## Step 0 — Vintage & format check (load-bearing)

Before bucketing, place the source in TIME. The competition is Scarlet & Violet **Mega-era** + the
simulator deltas ([../../../../docs/rules.md](../../../../docs/rules.md)). A source older than that (a
Sword & Shield-era article/video, ~2020–2022) is a **different format**: card pool, many rules, and the
entire meta differ.

- Read the Fetched Article's `date`. If it predates the current format (or the content is visibly from an
  old pool — cards/decks not in `data/EN_Card_Data.csv`), set the Digest's `vintage` header to the era
  and add a one-line **staleness banner** at the top of the Digest.
- **General principles transfer; specifics don't.** Prize trading, tempo/sequencing, mulligan theory,
  deckbuilding ratios, resource management, practice methodology → still valid `general` / `process`.
  Deck lists, card interactions, matchup calls, "best deck" claims → **format-bound**: route them to
  **`Out-of-Scope (stale)`**, do NOT manufacture `opponent:<archetype>` or `our-deck` entries from a dead
  format. If a stale specific *illustrates* a transferable principle, keep the principle as `general` and
  drop the card names.
- When in doubt about whether a point is principle or format-specific, it's format-specific → stale.

## Step 1 — Sort every point into an Actionability Bucket

Read the whole body, then bucket each distinct point:

- **Agent-Doctrine** — convertible to a Pilot **Hypothesis** or a **Matchup Brief**: in-game decision
  rules, deck strengths/weaknesses, counter-lines, prize math, sequencing, meta reads, when a line comes
  online. This is the grill's input; give it the most care.
- **Process** — informs OUR *workflow*, not the Pilot: practice/testing methodology that maps to our
  training, gauntlet, or self-play (e.g. "run ~100 solo reps of a new deck to learn its lines" ≈ our
  self-play corpus; "check prizes and take notes every game" ≈ our telemetry/blunder loop). One short
  line each — enough to act on later.
- **Out-of-Scope** — pure human-improvement advice with no repo home ("teach weaker players", "practice
  in groups of 3+", "verbalize your plays"), **plus `(stale)` format-bound specifics** from an
  old-format source (Step 0). Capture in one line each and flag non-actionable, so the Digest proves the
  source was fully mined rather than skimmed.

If a point is genuinely two things (a meta read that also implies a counter-line), split it.

## Step 2 — For each Agent-Doctrine entry, fill the four fields

1. **Scope** — exactly one of:
   - `general` — deck-agnostic doctrine → `docs/general-strategy.md`.
   - `our-deck:<deck>` — bears on one of our agents (`src/agents/<deck>/`).
   - `opponent:<archetype>` — how an opponent wins / how to beat it → a Matchup Brief.
2. **Target Home** — best-effort concrete artifact:
   - `general` → `docs/general-strategy.md`.
   - `opponent:<archetype>` → `docs/matchups/<slug>.md` — match the foreign deck name to a tracked
     **Archetype** ([CONTEXT.md](../../../../CONTEXT.md)) where you can; if it doesn't map, leave it as a
     *described-opponent note* (name the key Pokémon) and say "no tracked Archetype match".
   - `our-deck:<deck>` → `src/agents/<deck>/STRATEGY.md`.
3. **Claim + why** — the assertion in one or two sentences, plus why it wins games. Concrete, testable.
4. **Candidate Signal** — a NON-BINDING hint at what a future Hypothesis might key on. Reach, in order,
   for something that already exists:
   - a **Function Tag** (what a card does — [card-functions.md](../../../../docs/card-functions.md) /
     `src/common/card_functions.json`),
   - an engine **CardStat** fact (HP, prize value, weakness, retreat, attack cost),
   - a **board** condition or a **Context** field the Pilot already reads
     ([general-strategy.md](../../../../docs/general-strategy.md), `src/cg/api.py` enums),
   - or the literal **"needs a new signal"** when nothing fits (a real, useful outcome — it tells the
     grill new infra is required).
   **Never** write a weight, an id, or a `when()` trigger. This is a pointer, not a rule.

## Step 3 — Provenance header + write

Fill the template's header from the Fetched Article: `source`, `handle`, `title` (verbatim, JP stays JP),
`url`, `source_id`, `date`, `language`, `access`, plus a one-line "what it covers". Keep the whole Digest
**English** — preserve only the JP title/handle/load-bearing deck & card names. Do not reproduce the
source body.

## Step 4 — Routing summary (printed to the user, not the file)

Group the Agent-Doctrine entries by Target Home and print the next grill per group:
- `general` → run general-strategy authoring against `docs/general-strategy.md`.
- `opponent:<archetype>` → `/matchup-genie <slug>`; check `src/common/scouting/briefs/` — **exists**
  (refine) vs **new**.
- `our-deck:<deck>` → `/deck-genie <deck>` or `/deck-align <deck>`; check `src/agents/<deck>/STRATEGY.md`
  exists.
Auto-run nothing.

## Guards

- **Card facts are the author's claims.** If the author asserts a card interaction/attack number, attach
  it as *their* claim — do not assert it as truth. `data/EN_Card_Data.csv` + the engine remain ground
  truth; the downstream grill verifies before shipping ("verify, don't recall", per the project CLAUDE.md).
- **Foreign deck names are not always tracked Archetypes.** Map when confident; otherwise a described
  note. Never invent an Archetype string.
- **Thin or vague content → say so.** An article that's mostly Out-of-Scope produces a small
  Agent-Doctrine bucket; that's a correct result, not a reason to pad with fabricated doctrine.
