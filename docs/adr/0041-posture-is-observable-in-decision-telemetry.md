# ADR-0041: Posture is observable in Decision Telemetry (matchup misplays route to a Brief, not a weight)

**Context.** Posture ([ADR-0026](0026-posture-generic-core-is-net-new-read-levers.md)) and Matchup
Briefs ([ADR-0027](0027-matchup-brief-is-hand-authored-opponent-doctrine.md),
[ADR-0038](0038-brief-consumption-sharpens-the-owning-tactical-signal.md)) went live: the Read now
moves play — the γ-scaled snipe/gust levers, favorability, the Brief `fragile_preevo`/`engine` boosts.
But the Read was **invisible after the fact.** The `@T` Decision Telemetry
([ADR-0019](0019-submissions-are-traceable-and-tracked.md)) carried the scoring / Planner / Lethal
verdicts (`opts`, `planned`, `lethal`) but not **who the agent thought it faced.** So a blunder tagged
while facing a recognized archetype couldn't be tied to that matchup; the blunder loop had no way to
see a *wrong Read*, and no way to route a matchup misplay to the layer that owns it. Authoring a
deck-agnostic `when()` for a one-archetype misplay is exactly the incoherence ADR-0038's sharpen-first
routing prevents *inside* the Pilot — the correction loop needed the same discipline.

**Decision.** The Read becomes observable end-to-end, as a byte-cheap **belief snapshot that never
feeds a decision** (it is legibility, like `Decision.read` already was):

- **The Pilot stamps a compact `posture` summary onto every Decision** (`_posture_record(board)`): the
  believed archetype candidates (`cands` = top-k `[archetype, posterior]`), the confidence (`conf`,
  `unknown`), the **applied** Posture strength `gamma` (captures the `posture` kill-switch — `0` =
  off / unrecognized), the modeled matchup `fav`/`cov` (lever A), and the matched Brief `slug`. Sparse:
  `None` when no Scout is wired.
- **`telemetry.to_record` emits it under the `posture` key**, so it rides into every Correction's
  `live_trace` (via `telemetry_log.record_for`), exactly the way `lethal` / `planned` do. The blunder
  inspector shows the believed archetype **at the decision**, and a new **"opponent read was wrong"**
  checkbox writes a **structured `Correction.posture_mismatch` boolean** — distinct from the free-prose
  `rationale`, which still carries the intended line ("vs Mega Lucario ex I should snipe Riolu").
- **The routing surfaces the way the layer verdicts do.** `tune.py` tags each flagged
  `PROPOSE` / `UNSATISFIED` / `SKIP` line `[POSTURE≠ <archetype>]` + a summary banner;
  `data/corrections/tuner/<deck>.json` `open[]` / `skipped[]` entries carry `posture_mismatch` +
  `believed_archetype`. `/blunder-buster` reads `live_trace.posture` on **every** cluster member and
  routes a matchup misplay to the believed archetype's **Matchup Brief / posture lever / recognition**
  (or hands full Brief authoring to `/matchup-genie`) — **never a deck-agnostic weight or `when()`**.
  It becomes a fourth routing axis alongside CRITICAL / `[LETHAL]` / `[PLANNED]`.

*Structured field, not a rationale marker (unlike CRITICAL):* the believed archetype is already
structured (`live_trace.posture`); pairing it with a structured boolean keeps the verdict
machine-queryable without regex, and the two axes are orthogonal — CRITICAL is *urgency*,
`posture_mismatch` is a *factual annotation about the Read*. The intended line stays in the rationale.

*Stamped on the Decision, not recomputed:* `gamma` is derivable from the Read, but the **applied** γ
also captures the kill-switch, and the matched Brief is **not** derivable from the Read alone (it needs
the loaded Briefs). Recording the Board's applied state is the honest snapshot.

**Terminal outcomes for a posture-mismatch** (the exhaustive-completion mandate still holds): `fixed`
(a small, retest-verified Brief/lever change), `covered` (an existing Brief/lever already handles it —
named + confirmed on the real Pilot), `refuted` (the Read was right / the correction is wrong), or a
**named hand-off** — `/matchup-genie <slug>` for full Brief authoring, or the recognition
capability-gap shape when the Scout/artifact itself mis-scored (the artifact is compiled offline,
[ADR-0003](0003-scouting-knowledge-is-a-shipped-artifact.md)). Never a bare `deferred`.

**Consequences.**
- Every blunder now carries **who the agent thought it faced**; a cluster of misplays sharing one
  `believed_archetype` is a signal to sharpen *that matchup's Brief*, not to author a general rule that
  would misfire in every other matchup.
- **Backward-compatible wire + schema.** `posture` is sparse (omitted when no Scout — a non-posture
  agent's `@T` is byte-unchanged); `posture_mismatch` defaults `False` (legacy Corrections and
  pre-posture agent logs read unchanged); the retest before/after is unaffected (it re-derives through
  the same `to_record`).
- Telemetry cost is negligible — top-k candidates + a few rounded scalars per decision; the
  `opts`/`fired` block already dominates the record.
- The inspector's "opponent read was wrong" checkbox is a **process** surface — it complements the
  category vocabulary; a matchup misplay is often *also* a `bad_target` / `sequencing_error`.

**Considered options.**
- *Encode the mismatch as a rationale token (mirror CRITICAL)* — rejected: overloads the rationale with
  two orthogonal axes and forces regex; a boolean is the honest model and the archetype is already
  structured.
- *Emit only the Read candidates; recompute γ / Brief downstream* — rejected: applied γ must capture the
  kill-switch and the Brief isn't derivable from the Read alone; stamping the Board state is truthful
  and cheaper for every consumer.
- *Let `/blunder-buster` author Briefs in-session for every posture miss* — rejected as the default:
  Brief authoring is `/matchup-genie`'s grilled, researched process. blunder-buster makes small
  retest-verified Brief/lever tweaks but **routes** full authoring — the same hand-off shape as a
  capability-gap.
- *Extend ADR-0019/0026 in place vs a new ADR* — new ADR: this is a distinct decision (observability +
  a correction-schema field + a routing axis) spanning three ADRs' surfaces.
