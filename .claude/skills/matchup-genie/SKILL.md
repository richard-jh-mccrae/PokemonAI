---
name: matchup-genie
description: >
  Build the OBJECTIVE counterplay doctrine for ONE opponent archetype for the PokemonAI Read/Posture
  layer from its exported deck.csv. Produces a grilled, research-backed docs/matchups/<slug>.md
  doctrine and then ENDS at fodder — a matchup-brief Strategy Proposal in data/strategy/proposals/
  (ADR-0046); it does NOT write the Brief JSON. The /update-strategy skill authors the self-describing
  src/common/scouting/briefs/<slug>.json Brief (routing variants via covers:) from that proposal.
  Use whenever the user wants to analyze, scout, or write the game-plan AGAINST a specific opponent
  deck/archetype: "build the matchup brief for <archetype>", "how do we beat <deck>", "author the
  counterplay for this deck", "/matchup-genie <slug>", or after the meta-tracker deck export
  (data/meta/decks/) surfaces a deck worth countering. This is the opponent-facing counterpart to
  deck-genie (which authors how OUR deck plays). Do NOT use it to tune weights from blunder
  corrections (that's /blunder-buster), tag card functions (the card-functions pipeline), or author
  our own deck's strategy (that's /deck-genie).
---

# matchup-genie — author one opponent's counterplay doctrine

Turn ONE opponent deck (an exported `deck.csv` + `deck.txt`) into a coherent, intensely-grilled
**objective** counterplay doctrine for the Read/Posture layer — a human-readable
**`docs/matchups/<slug>.md`** and, from it, a **Strategy Proposal** that `/update-strategy` turns into
the machine **`src/common/scouting/briefs/<slug>.json`** Brief. matchup-genie is a **producer**
(ADR-0046): it analyses + grills + proposes; it never writes the Brief JSON. This is deck-genie *flipped
to the opponent*: deck-genie asks "how does OUR deck play?"; matchup-genie asks "how does THIS deck win,
and how do we beat it?" ([ADR-0027](../../../docs/adr/0027-matchup-brief-is-hand-authored-opponent-doctrine.md)).

**Invocation:** `/matchup-genie <slug>` (e.g. `/matchup-genie hop_s_trevenant_hop_s_snorlax`). The slug
is a directory under `data/meta/decks/` produced by the meta-tracker deck export. Any extra prose is
matchup context — fold it into Phase 1.

## Inputs & the two outputs (the ADR-0027 contract)

**Input — ONE chosen deck, no meta knowledge.** matchup-genie owns *no* ranking or archetype discovery.
The user reads the meta-tracker's `data/meta/decks/index.json` menu (the play-rate ranking; item 1) and
points this skill at one `data/meta/decks/<slug>/deck.csv`. That `index.json` entry also carries the
cluster's `label` and **`covers`** (the member Archetype strings) — you read them, you don't derive them.

The deliverable arrives in two phases with **your explicit sign-off** as the gate between them:

- **Phase A → `docs/matchups/<slug>.md`** — the objective doctrine: how the opponent wins, its tempo,
  its **exploitable weaknesses**, the **threats** to respect and the **targets** to disrupt/snipe, and
  the objective counterplay. Cited. **No Brief JSON yet.** Grill it until locked.
- **Gate** — present the finished doc, resolve the last contradictions, get an explicit "ship it."
- **Phase B → a Strategy Proposal in `data/strategy/proposals/`** — a `target_layer: matchup-brief`
  record (`verification_contract: brief-validator`) whose `spec` is the locked doctrine's Brief-field
  content (`covers`, `opponent_properties`, `threats`, `targets`) and whose `provenance` links to the
  doctrine. **matchup-genie stops here.** `/update-strategy` writes `src/common/scouting/briefs/<slug>.json`,
  runs `validate_brief.py`, and the human commits (ADR-0046).

Why this shape: the Brief is runtime-consumed data, so it follows the doc-before-code rule
([ADR-0017](../../../docs/adr/0017-corrections-compile-to-hypotheses.md)); [ADR-0046](../../../docs/adr/0046-strategy-authoring-splits-analysis-proposes-one-skill-applies.md)
puts the JSON authoring + validator gate in the one applier. The intense grill **is** the doctrine review.
Writing the Brief here — before the doc is locked, and in the wrong skill — is what these ADRs forbid.

## What it is NOT

- **Not meta-aware.** No ranking, no "which deck next" — the user chose the deck. (That's the
  meta-tracker, item 1.)
- **Objective, not relativized.** The Brief is *shared across all our decks*. Write "this deck is
  engine-dependent; its Dudunsparce is the seam" — **never** "I'm Mega Starmie, so…". Each of our agents
  relativizes the Brief via its own Read-conditioned Hypotheses (that's `/deck-genie`'s job).
- **Not our-deck strategy** (`/deck-genie`) and **not weight tuning** (`/blunder-buster`).

## Workflow

Phases 3–4 interleave (map a weakness to a Brief field the moment it locks). The per-topic question
banks + grill discipline live in [references/counterplay-playbook.md](references/counterplay-playbook.md)
— read it before Phase 3. The Brief emit gate lives in [references/authoring.md](references/authoring.md).

### Phase 0 · Orient (deterministic — do this silently, then show Phase 1)

1. Confirm `data/meta/decks/<slug>/deck.csv` + `deck.txt` exist. Read `data/meta/decks/index.json` and
   pull this slug's **`label`** and **`covers`** — the Brief will carry them verbatim.
2. **Dump the opponent's card facts** (engine is ground truth; `cards.json` is stale — never
   hand-transcribe HP / cost / attack text). **Reuse deck-genie's dumper, pointed at the export dir:**
   `python .claude/skills/deck-genie/scripts/dump_deck.py --deck-dir data/meta/decks/<slug>`
   It joins engine `CardData` + `Attack` + `card_functions.json` tags. Capture it verbatim — it's the
   substrate for every threat/target/weakness claim. (`--json` for the machine form.)
3. **Read what already exists:** [ADR-0027](../../../docs/adr/0027-matchup-brief-is-hand-authored-opponent-doctrine.md)
   + [ADR-0003](../../../docs/adr/0003-scouting-knowledge-is-a-shipped-artifact.md) (the auto-Dossier —
   the Brief adds the *gameplan* the Dossier can't derive); the threats/targets role vocab in
   [CONTEXT.md](../../../CONTEXT.md) and `tools/meta_tracker/compile_scouting.py` (`_dossier_intel`); the
   opponent-property vocab in [src/common/scouting/opponent_properties.json](../../../src/common/scouting/opponent_properties.json); any
   sibling Brief in `src/common/scouting/briefs/`. **If `docs/matchups/<slug>.md` exists, you're
   resuming** — read its progress checklist and pick up; don't restart.
4. Start (or reopen) the doc from [assets/MATCHUP.template.md](assets/MATCHUP.template.md).

### Phase 1 · Opponent overview (present, then confirm)

From the dump, present a tight read of **how this deck wins** — win condition + prize math (Mega-ex=3 /
ex=2 / else=1), the Line(s) and when they come **online**, the main attacker(s), the draw/search
**engine**, acceleration, and tempo. Fold in the user's context. Then **ask them to confirm the
opponent's win condition and your read of its gameplan** before spending a research pass — a wrong
premise here poisons the counterplay.

### Phase 2 · Counterplay research (parallel, cited — the default)

These are well-documented meta decks: there's coverage of both *how they win* and *how they're beaten*.
Build the streams from the Phase-0 dump + Phase-1 overview and fan them out **at once** via the shipped
workflow (invoking this skill is the opt-in):

```
Workflow({ scriptPath: ".claude/skills/matchup-genie/scripts/research.js", args: {
  archetype: "<label>",
  gameplan:  "<the CONFIRMED Phase-1 how-it-wins>",
  facts:     "<the full Phase-0 dump markdown — ground truth>",
  angles:          [ { key: "gameplan", q: "..." }, { key: "counters", q: "how to beat <archetype>" }, ... ],
  key_cards:       [ { name: "Hop's Trevenant", why: "main attacker / item-lock" }, ... ],
}})
```

It runs an archetype sweep (how it wins + optimal lines), a **counterplay/weakness sweep** ("how to beat
X", "X bad matchups", "X weaknesses"), and per-key-card deep dives (its threats + engine — how they
function and how to neutralize), **adversarially verifies every claim against the engine facts**, and
returns a cited synthesis (`how_it_wins`, `tempo`, `weaknesses`, `threats`, `targets`, `counter_lines`,
`gaps`, `sources`) + web-vs-facts `conflicts`. **Fallback (no Workflow):** fan the same streams out with
parallel `Agent` calls, then verify each claim against the facts yourself. Land it in `MATCHUP.md` §2.

**Guards (load-bearing):** engine facts **override** the web (Scarlet & Violet *Mega-era* + simulator
deltas — use the web for *strategy/counterplay*, never *mechanics*; verify interaction legality against
the actual card text). Thin coverage → flag the gap, never invent. The user outranks the web.

### Phase 3 · Weakness grill (the heart)

Interrogate the deck into an **exploitable-seam map** — see
[references/counterplay-playbook.md](references/counterplay-playbook.md) for the question banks. For each
seam, one branch at a time, resolve: the **weakness** (tempo window, engine dependence, fragile pre-evo,
prize liability, donk vulnerability, dead-draw lines, bad type matchup) and the concrete **exploit**.
Every seam must resolve to something a future Board lever or a threat/target could read — if it can't,
flag it. In parallel, lock the **threats** (its attackers we must respect) and the **targets** (what to
disrupt/snipe), using the Dossier role vocab: `fragile_preevo`, `prize_liability`, `engine` (attackers
go in `threats`).

### Phase 4 · Brief-field reconciliation (interleaved with Phase 3)

As each seam locks, map it to the machine Brief:
- **`opponent_properties`** — reuse an existing key from
  [src/common/scouting/opponent_properties.json](../../../src/common/scouting/opponent_properties.json) where one fits; **mint a new key
  only when nothing does**, add it to that registry with `consumer: "unwired"`, and **flag it** — a new
  key is a forward contract the (separate, unbuilt) consumer must wire onto `Board`. Keys stay a small,
  growing vocabulary (like Function Tags / Roles).
- **`threats` / `targets`** — objective card-level intel, each with a one-line `why`.

### Phase 5 · Lock & sign-off (the gate)

Present the finished `MATCHUP.md`. Hunt contradictions (a weakness with no exploit; a target that isn't
in the deck; a claim that fights the engine facts). Get an **explicit sign-off**. Do not emit the Brief
without it.

### Phase 6 · Phase B — emit the Strategy Proposal (the fodder hand-off; ADR-0046)

Write one **Strategy Proposal** record into `data/strategy/proposals/` (contract:
[../update-strategy/references/strategy_proposal_contract.md](../update-strategy/references/strategy_proposal_contract.md)):
`source: matchup-genie`, `target_layer: matchup-brief`, `for: opponent:<archetype>`,
`verification_contract: brief-validator`, `provenance` → `docs/matchups/<slug>.md`. The `spec` carries
the locked Brief content the applier needs: `covers` (verbatim from `index.json`), `opponent_properties`
(reuse a registered key where one fits; a **new** key is flagged in the spec as an unwired forward
contract), `threats`, `targets` — as doctrine, **not** hand-written JSON.

**matchup-genie stops here — it does not write `briefs/<slug>.json` or run the validator.**
`/update-strategy` authors the JSON (schema: [src/common/scouting/brief.schema.json](../../../src/common/scouting/brief.schema.json)), runs
`python .claude/skills/matchup-genie/scripts/validate_brief.py <slug>` (schema + `covers` non-empty &
matching `index.json` + every threat/target card in the deck + legal target roles + registered
`opponent_properties`), presents the diff, and the human commits (its commit message begins with
`matchup: `).

## Completion discipline — build to feature-complete (no convenient stopping points)

The Phase-5 sign-off is the ONLY approval gate in this skill. Once the user grants it (or gives a
standing "full build" / "go" authorization), Phase B runs to **complete in one continuous push**: the
Strategy Proposal written to the queue, its `spec` carrying the full locked Brief content, its
`provenance` linked to the doctrine. Hard rules:

- **Never end a turn reporting remaining work** ("Brief drafted; remaining: validation — say go").
  If you can name the next item, do it now instead of asking.
- **A "clean, resumable point" is never a reason to stop.** Resumability (below) covers involuntary
  interruption — context limits, crashes, the user stopping you — not voluntary pauses.
- **Standing authorization persists across items**; never re-confirm per item or per milestone.
- **Legitimate stops, exhaustively:** (a) a genuinely NEW scope decision the user must make (not
  re-confirmation of the already-agreed plan), or (b) a hard blocker you cannot resolve yourself.
  Everything else: keep building.

## Resumability

The grill spans sessions. `MATCHUP.md`'s **Progress checklist** is the source of truth. On re-invoke:
re-run the dump (cheap), read the doc, resume from the checklist. Never silently restart a matchup that
already has a doc in progress. Resumability exists for involuntary interruption only — it is never a
license to stop voluntarily (see Completion discipline).

## Guardrails

- **Doc before proposal; no Brief JSON in this skill.** No proposal until `MATCHUP.md` is signed off
  (ADR-0017); matchup-genie never writes `briefs/<slug>.json` — that's `/update-strategy` (ADR-0046).
- **Engine is ground truth** for card facts; **the user is ground truth** for intent; the **web is a
  prior**. When they conflict, the user wins and you record why.
- **Objective, deck-neutral.** No "our deck" reasoning in the Brief — that's each agent's relativization.
- **`covers` comes from `index.json`, not memory** — it's what routes every variant to this one Brief.
- **Never claim a target the deck doesn't run** — the validator hard-fails it; ground every card in the dump.
- **No convenient stopping points.** After sign-off, run Phase B to complete; never end a turn
  listing remaining work (see Completion discipline).
