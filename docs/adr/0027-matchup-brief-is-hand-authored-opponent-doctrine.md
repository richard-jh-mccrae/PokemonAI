# ADR-0027: Per-archetype counterplay is a hand-authored Matchup Brief, distinct from the auto-Dossier

**Context.** The auto-compiled Dossier ([ADR-0003](0003-scouting-knowledge-is-a-shipped-artifact.md))
derives, per archetype, the representative build, signatures, threats, targets (auto-roles) and
matchup win-rates — i.e. the *cards*. It cannot derive the *gameplan*: how an archetype wins, its
tempo, its exploitable weakness, and how to posture against it. The M2 generic core
([ADR-0026](0026-posture-generic-core-is-net-new-read-levers.md)) covers all 122 archetypes only at a
basic level (favorability + accurate development). Sophisticated, opponent-specific counterplay — and
the engine-removal lever ADR-0026 declined to make generic — needs hand-authored strategic knowledge,
shared across our decks rather than re-derived in each.

**Decision.** Per-archetype counterplay is a hand-authored **Matchup Brief**: the *objective* strategic
profile of one opponent archetype (how it wins, tempo, exploitable weakness, which threats/targets/
levers matter), shared across all our decks and distinct from the auto-Dossier (the Dossier has the
cards; the Brief has the gameplan against them — see [common/CONTEXT.md](../../src/common/CONTEXT.md)).

- **Authored, not compiled → it lives beside the artifact, never inside it** (the artifact is
  regenerated from the meta daily and would clobber it). The runtime annotations are committed at
  `src/common/scouting/briefs/<slug>.json`; the human doctrine at `docs/matchups/<slug>.md`. Each Brief **self-declares the archetype strings it
  covers** (`covers: [...]`) so variants route to one Brief — the Read consumer matches
  `read.candidates[0]` against every Brief's `covers` list; no separate alias map.
- **Objective/relativized split** (mirroring the Read's own framing): the Brief is *objective* and
  *shared*; each agent **relativizes** it to its own cards via deck-specific Read-conditioned
  Hypotheses ("I'm Mega Starmie; Alakazam scales with hand size → my Harlequin is gold here").
- **Consumption reuses the existing surface.** When an archetype is recognized (`γ`-gated, per
  ADR-0026), its Brief populates `Board` opponent-property fields (`opp_is_engine_dependent`,
  `opp_donk_vulnerable`, …) — *exactly* as the card-fact `opp_has_hand_size_attacker` already does.
  General **or** deck Hypotheses then read those fields (the expand-vs-override rule decides which).
  Briefs are not a parallel system — they are more rows on the Board's opponent-property surface.
  Engine-removal (ADR-0026) lives here.
- **The meta-tracker owns meta knowledge; `matchup-genie` owns none.** `run_meta_tracker.py` produces the
  meta overview — the prevalence ranking, the per-archetype representative `deck.csv`/`deck.txt` export
  (reusing `_representative_build` + `render_txt`), and the variant grouping. The user reads that overview
  and, **at their own cadence, points `matchup-genie` at one chosen `deck.csv`**; the skill does no ranking
  or archetype discovery.
- **`matchup-genie` (a new sibling skill — deck-genie flipped to the opponent) analyzes a single
  user-supplied deck.** Its Phase-0 dump is that one deck (identical to deck-genie's dump path); then a
  counterplay **research fan-out** (engine-verified; web for strategy, not mechanics) over the deck **and
  its close variants**; a weakness grill; a gated `MATCHUP.md`; then a self-describing Brief.
- **Coverage = the head ~8 core strategies (~12 classifier strings, ~90% of games).** The user works down
  the meta-tracker's prevalence ranking **in chunks**, M1-measuring each, and stops when marginal benefit
  drops. The long tail gets the generic core alone — safe because an unknown deck drives `γ→0`.

**Considered options.**
- *Per-deck Read-conditioned Hypotheses only* (the ADR-0008 seam, no shared layer) — rejected:
  re-derives the same opponent analysis in every deck; the goal is shared analysis that agents specialize.
- *Annotate the auto-compiled artifact with the hand-authored knowledge* — rejected: the daily
  recompile clobbers it; authored and compiled knowledge must stay separate files.
- *Make the weakness/engine-removal behaviors generic* — rejected: their tempo value is
  matchup-specific (ADR-0026).

**Consequences.** A small, growing vocabulary of archetype weakness tags accretes as `matchup-genie`
analyzes each archetype (like Function Tags / Roles — closed-ish, extended by process). The Pilot reads
one clean surface (`Board`). The layer depends on M2.0/M2.1a (the Read on `Board`) and the M1 pre-filter
to measure each Brief. `matchup-genie` is authored separately (via the skill-creator flow) when build
begins.
