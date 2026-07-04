# Scouting — opponent recognition & the Read

Deck-agnostic runtime capability (`src/common/scouting/`). It watches what
the opponent reveals, recognizes the **Archetype** it's facing, and produces the
**Read**: a live, per-turn assessment (candidates + confidence, predicted development,
objective threats/targets). It **does not act** — that's **Posture**, a consumer of the
Read (deck-specific, out of scope here).

Glossary: [common/CONTEXT.md](../src/common/CONTEXT.md). Decisions:
[ADR-0003](adr/0003-scouting-knowledge-is-a-shipped-artifact.md) (shipped artifact +
engine stats), [ADR-0004](adr/0004-shared-common-packaged-per-submission.md) (shared
`common/`, package step). Grader constraints (≤~10 min/match, tight per-move budget,
no internet, fresh process per match) are summarized under *Runtime* below.
Reference consumer: [demos/rules-based-lucario.py](../demos/rules-based-lucario.py).

## Architecture

Two knowledge sources, split by what's static vs meta-dependent:

```
meta.db ──┐                                   (offline, tools/)
cards.json┤─► build_scouting_artifact.py ─► common/scouting/artifact.json  (shipped)
          │     recency decay · band-balanced priors                │
          │     signatures · dossiers · threat/target roles         │
                                                                     ▼
                       ┌─────────────── Scout (runtime, common/) ──────────────┐
 obs each decision ──► │ accumulate revealed cards → Naive-Bayes posterior      │ ─► Read
 cg.all_card_data() ─► │ + injected card-stat cache → threats / targets         │
                       └────────────────────────────────────────────────────────┘
```

- **Shipped meta artifact** — point-in-time, recency-weighted, regenerated and
  re-bundled as the meta shifts. Meta knowledge only; cards referenced by `cardId`.
- **Card stats** (hp/weakness/resistance/abilities/attacks) — read from the
  already-loaded `cg` engine at startup and cached; authoritative, never stale.

## The Read (public contract)

```python
@dataclass
class Read:
    candidates:      list[tuple[str, float]]   # top-3 (archetype, posterior), desc
    unknown_mass:    float                      # posterior not explained by any archetype
    confidence:      tuple[float, float]        # (top posterior, margin over 2nd)
    evolution_paths: list[EvoPath]              # in-play Pokémon → predicted line top
    expected_cards:  list[tuple[int, float]]    # not-yet-seen key cardIds, by P(card|A)
    threats:         list[Intel]                # objective attackers
    targets:         list[Intel]                # objective high-value removal points
```

`Intel` carries `cardId`, `role`, `seen: bool`, and stats resolved via the card-stat
cache. **Objective framing**: threats/targets describe the opponent's capabilities and
vulnerabilities; relativizing to *my* deck (does it KO me? can I exploit the weakness?)
is the consumer's job. The Read **never raises**.

## Recognition (the scorer)

Presence-only Naive Bayes over the set `E` of distinct opponent `cardId`s revealed so
far this match (active, bench, discard, attached energy/tools/preEvolution, and
`PLAY`/`EVOLVE`/`MOVE` logs):

```
score(A) = prior(A) · ∏_{c∈E} P(c ∈ deck | A)          for each archetype A
score(U) = prior(U) · ∏_{c∈E} background(c)            the "unknown / off-meta" hypothesis
posterior(A) = score(A) / (Σ_A score(A) + score(U));   unknown_mass = score(U) / (…)
```

- **Presence-only**: update on cards seen; never penalize for not-yet-seen cards.
- **Smoothing**: `P(c|A)` has a small floor so a tech card absent from sampled lists
  can't zero out a true archetype.
- **Signatures** fall out for free: a card with `P(c|A)/background(c)` ≫ 1 (Solrock →
  Mega Lucario ex) spikes the posterior the instant it appears. Top-lift cards per
  archetype are also surfaced in the dossier for explainability.
- `confidence = (posterior(top), posterior(top) − posterior(2nd))`. A 0.55/0.45 split
  is "confident it's one of two", not "confident it's the leader".

## Threats, targets, development

Two layers, so the Read is useful even off-meta:

- **Observed (always)** — built from revealed opponent cards + engine stats. Real
  threats/targets *right now*, `seen=True`. Works against a totally rogue deck.
- **Predicted (when confident)** — dossier-derived not-yet-seen threats, `expected_cards`,
  and archetype `evolution_paths`, `seen=False`. Added once the top candidate clears a
  confidence bar.

`evolution_paths` resolve from the dossier's evolution lines when recognized, else fall
back to the engine's `evolvesFrom` chain (observed Riolu → Lucario regardless of
recognition). Target `role ∈ {engine, fragile_preevo, prize_liability, attacker}`.

## The artifact

```jsonc
{
  "meta":       { "schema_version", "compiled_at", "episode_count", "half_life_days", "hash" },
  "priors":     { "<archetype>": prior },          // band-balanced blend, recency-weighted
  "background": { "<cardId>": p_present },          // for the unknown hypothesis
  "dossiers":   { "<archetype>": {
      "card_inclusion":       { "<cardId>": "P(card in deck | A)" },
      "signatures":           [ { "cardId", "lift" } ],
      "representative_build": [ "<cardId>", … ],    // recency-weighted ~60
      "evolution_lines":      [ [ "basicId", "stage1Id", "topId" ], … ],
      "threats":              [ { "cardId", "role" } ],
      "targets":              [ { "cardId", "role" } ],
      "win_rate":             0.55,                  // marginal vs the field: recency-weighted, shrunk → 0.5
      "win_n":                123.4,                 // weighted decisive games behind win_rate (reliability)
      "matchups":             { "<opponent archetype>": { "win_rate": 0.62, "n": 18.0 } }
  } }
}
```

**Matchup win-rates** (`win_rate`/`win_n`/`matchups`) come from each Episode's
`winner_index` (draws excluded). The per-opponent cell shrinks toward the archetype's
marginal, which shrinks toward 0.5, so a one-game record reads near-neutral rather than
100% — `n` exposes how much evidence backs each number. Bands are **pooled** here (unlike
priors): a win-rate is a ratio, so an over-sampled band doesn't bias it. The consumer
turns this into *favorability* via `common.scouting.matchup_favorability(artifact,
my_archetype, read.candidates)` → `(favorability, coverage)`; low coverage = mostly the
0.5 default, so trust it less. The agent must supply its **own** archetype (known at
build/submit time) — the table is keyed by it.

Dossiers are **band-independent** (an archetype is the same deck everywhere); only the
**prior** varies by band, and we ship a single **band-balanced** blend (averaging
per-band rates avoids the over-sampled, noisy Low band — see CONTEXT.md → Rank Band).

## Matchup Briefs (consumer bridge)

The auto-compiled Dossier has the opponent's *cards*; the hand-authored **Matchup Brief** has the
*gameplan against them* — how the archetype wins, its tempo, exploitable weakness, and which
threats/targets matter ([ADR-0027](adr/0027-matchup-brief-is-hand-authored-opponent-doctrine.md);
authored by the `matchup-genie` skill at `src/common/scouting/briefs/<slug>.json`, human doctrine at
`docs/matchups/<slug>.md`). `common.scouting.briefs` is the consumer bridge (sibling to
`matchup_favorability`):

- `load_briefs()` — fail-safe load of every `briefs/*.json` (a bad file is skipped; empty dir → `[]`).
  No two Briefs may share a `covers` string (`match_brief` takes the alphabetically-first cover) —
  pinned by `test_shipped_briefs_have_no_covers_collision` + a `validate_brief.py` hard check.
- `match_brief(briefs, read)` — routes `read.candidates[0]` (the top archetype) to the Brief whose
  `covers` list contains it, so an archetype's variants all resolve to one Brief. Plain string routing
  (ADR-0027); γ tempers *use*, not the match.
- `resolve_brief_cards(brief, ids_for_name)` — the matched Brief's name-keyed threats/targets as card
  ids, surfaced on `Board` (`brief_threat_ids`, `brief_target_roles`, and the `opp_property` /
  `brief_target_role` / `brief_target_ids` accessors).

The matched Brief rides on **`Board.brief`**, γ-gated to a recognized opponent (`None` when unknown /
uncovered / Posture off). **Consumption is ADR-0038**: Brief intel *sharpens the owning Tactical
signal* (γ-scaled) rather than minting parallel Hypotheses. The consumer table — what each Brief
surface drives (every agent opts in via `main.py`; pinned by `tests/agents/test_agent_wiring.py`):

| Brief surface | Consumer | Kill-switch |
|---|---|---|
| target `fragile_preevo` | tier-crossing snipe-rank boost in `_body_threat_rank` (snipe rules + planner key-threat rung inherit) + gust-target tie-break | `brief_preevo` |
| target `engine` + `opp_is_engine_dependent` | sub-tier snipe-rank boost + gust tie-break, hard-gated on the asserted bool | `brief_engine` (**default OFF** — the stress leg priced a wrong assertion at ~4%; arms via the first real true-asserting Brief's own A/B) |
| target `prize_liability` | **covered, no lever** — `_prize_value` (ex/Mega off CardStat), `gust_best_ko_prizes`, the Lethal Solver's prize math and `stall_target_is_keystone` already act on prize-heavy bodies | — |
| `threats` (`brief_threat_ids`) | **covered, no lever** — the threat rank sees attackers by printed damage; the defensive half is `active_doomed`'s forward-doom | — |
| `opp_donk_vulnerable` | **deferred** — the snipe half is delivered by the `fragile_preevo` lever; the residual "early aggression" half awaits a true-asserting Brief + correction evidence | — |
| `opp_tempo` | **deferred** — race/stabilize collides with ADR-0026's killed framings (a prior must not drive the Plan) and would double-count Lever A favorability | — |

Weakness ×2 stays the KO oracle's — Brief levers set the *gameplan* (which body wins the target
queue), never combat math (ADR-0038).

## The compiler (offline)

`tools/build_scouting_artifact.py` (a module in the `meta_tracker` package; reuses
`store.py`/`archetype.py`/`cards.py`; stays native-lib-free):

1. Load episodes from `meta.db`; weight each by `0.5 ^ (age_days / HALF_LIFE)` (from
   `end_time`).
2. Per band: recency-weighted archetype play-rate → **band-balanced** blended `priors`.
3. Per archetype: `card_inclusion`, top-lift `signatures`, the recency-weighted
   `representative_build`, `evolution_lines`, and `threat`/`target` role tags (from
   enriched `cards.json`: damage, ex/Mega, weakness, engine list, stage).
4. Per archetype + ordered matchup: recency-weighted **win-rate** from `winner_index`
   (draws excluded), shrunk toward the marginal then 0.5 so thin cells stay sane; bands
   pooled (a ratio, not a count) → `win_rate`, `win_n`, `matchups`.
5. Global `background(c)` from all decks.
6. Stamp provenance; **refuse** to emit below an episode floor (config).

`dump_cards.py` is extended to add `weakness`/`resistance`/`skills`/`attacks` to
`cards.json` (run when the legal pool changes; needs the native lib).

## Runtime (the Scout)

```python
_scout = Scout(load_artifact(), provider=EngineCardStatProvider())  # once at import

def agent(obs_dict):
    if obs_dict.get("select") is None:
        return my_deck                   # first call (60s budget): warm caches here
    read = _scout.observe(obs_dict)      # raw dict in → Read out; never raises
    …                                    # Posture uses read.candidates/threats/targets
```

- **Input**: `observe` takes the raw `obs_dict` (not the `Observation` dataclass), so
  `common.scouting` imports without loading the native engine — keeping tests lib-free.
- **Load once**: artifact + card-stat cache on first use (eager, in the 60s first-call
  budget); every per-decision lookup is then O(1).
- **Accumulate**: union revealed opponent cards into a match-scoped set; recompute the
  posterior from the full set each decision (monotonic, stable).
- **Reset**: detect match start and clear state — required because the local self-play
  harness reuses one process across matches (the grader is fresh per match).
- **Card-stat provider is injectable** — engine-backed by default; tests inject a
  `cards.json`-backed provider (lib-free).
- **Band prior**: the blended default (the agent can never observe its own band).
- **Fail-safe**: schema mismatch or load error → degrade to observed-only intel.

## Observability (the Read in telemetry)

The Read is emitted end-to-end so a misplay can be tied to the matchup it happened in
([ADR-0041](adr/0041-posture-is-observable-in-decision-telemetry.md)). Each decision's `@T` Decision
Telemetry record ([ADR-0019](adr/0019-submissions-are-traceable-and-tracked.md)) carries a compact
`posture` block — the believed archetype(s) (`cands`), applied confidence `gamma`, favorability, and
the matched Brief `slug` — sourced from `Board` via `Pilot._posture_record`. It rides into every
blunder Correction's `live_trace`, so the [inspector](blunder-inspector.md) shows *who the agent
thought it faced* and its **"opponent read was wrong"** checkbox routes a matchup misplay to the
Brief / recognition layer, never a deck-agnostic weight. Legibility only — nothing scores off the
emitted block.

## Build & packaging

- **Compile daily** (after the fetch) so the local artifact tracks the meta; **submit
  deliberately** — the shipped artifact freezes at submission.
- `tools/submit/package.py <name>` → copies `agents/<name>/{main.py,deck.csv}` + shared
  `common/` + `cg/` + the artifact into `dist/<name>/`, then zips it. `dist/` is
  gitignored; **commit the artifact** as part of each submission commit (provenance).

## Testing (ISTQB-aligned, native-lib-free)

| Tier | What | How |
|---|---|---|
| Unit — compiler | priors, dossiers, signatures, build | synthetic `meta.db` |
| Unit — Scout | posterior, accumulation, reset, fallback, never-throw | synthetic `Observation`s |
| Integration | recognition converges, reset between matches | the gzipped sample replay frames |

Card data comes from a `cards.json`-backed provider in tests (the existing lib-free
precedent), so the suite needs no native lib. REQ-IDs via `@pytest.mark.req`; run locally
with `python -m pytest tests/ -q` (no CI for this repo — see CLAUDE.md).

## Requirements (traceability)

Promote to `docs/req/` / `requirements.yml` when formalized; tests tag these.

| ID | Requirement |
|---|---|
| REQ-SCOUT-0001 | Identify the opponent at `Archetype` granularity from revealed cards. |
| REQ-SCOUT-0002 | Recognition accumulates across the match and only sharpens. |
| REQ-SCOUT-0003 | Output a ranked top-3 posterior + `unknown_mass` + confidence. |
| REQ-SCOUT-0004 | Provide objective threats/targets (observed always, predicted when confident). |
| REQ-SCOUT-0005 | Predict development (evolution paths + expected cards), engine fallback off-meta. |
| REQ-SCOUT-0006 | Never raise; never exceed the per-move budget; reset per match. |
| REQ-SCOUT-0007 | Knowledge is a shipped, recency-weighted, band-balanced artifact. |
| REQ-SCOUT-0008 | Card stats sourced from the engine at runtime (injectable for tests). |
| REQ-SCOUT-0009 | Compile per-archetype + per-matchup win-rates (shrunk, recency-weighted) for favorability. |

## Deferred

Posture / consumer logic; exact per-move time limit (confirm via Kaggle CLI);
attack-effect-text parsing (raw text shipped, numeric damage/cost used); the runtime
band knob (shipped capability, unused by default).
