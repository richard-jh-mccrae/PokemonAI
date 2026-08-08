"""Render a human-readable per-run **tuning report** (Markdown) from a ``TuneResult``.

One file per `/blunder-buster` run (`docs/tuning/runs/<deck>_<ts>.md`): what was tuned, why, and by
how much, plus the new-rule proposals and the corrections that still need a rule. Written for a
non-specialist to learn the system and to showcase the agent's progress; the math is explained once
in ``docs/tuning/methodology.md`` and linked from each report.
"""
from __future__ import annotations

# docs/weights.md bands — |weight| -> what that magnitude means, for a legible "by how much".
# Boundaries sit in gaps between documented tiers (0-5 / 10-20 / 30-50 / 60-100).
_BANDS = [(7.5, "faint tiebreaker"), (25, "normal preference"), (55, "strong preference"),
          (100, "near-imperative"), (float("inf"), "combat-scale")]


def _band(weight) -> str:
    mag = abs(float(weight))
    label = next(name for ceil, name in _BANDS if mag <= ceil)
    return f"{label}{' penalty' if weight < 0 else ''}"


def _why(correction, limit: int = 160) -> str:
    r = (correction.rationale or "").strip().replace("\n", " ")
    return (r[:limit] + "…") if len(r) > limit else r


def _move(correction) -> str:
    return f"`{correction.chosen_label}` → `{correction.correct_label}`"


def _at(correction) -> str:
    """**What the report prints must be what the writer accepts** (ADR-0090 decision 4). Distinct
    from `_where`, which stays prose: that answers *where to look*, this answers *what to type*."""
    from train.blunder.reviewed import review_key
    return review_key(correction)


def _where(proposal) -> str:
    """Where to find an open blunder. A scoped one (ADR-0049) is located by its Scope's subject —
    the Anchor frame is only where the human happened to be looking when they tagged it."""
    if proposal.scope == "turn":
        return f"ep {proposal.episode_id} turn {proposal.subject} (seat {proposal.seat})"
    return f"ep {proposal.episode_id} f{proposal.frame}"


def _driving(result, hid: str):
    """The W-route corrections whose constraint moves ``hid`` (with sign: +1 favours correct)."""
    return [(c, con.deltas[hid]) for c, con in result.w_items if hid in con.deltas]


def render_run_report(agent: str, result, seeds: dict, changed: dict, *, reg: float,
                      when_iso: str, build: str | None, n_corrections: int,
                      methodology: str = "../methodology.md", reviewed=None) -> str:
    """``changed`` is the sparse map actually SHIPPED (`io.sparse_overrides`), against ``seeds``."""
    sat = result.n_constraints - len(result.unsatisfied)
    verdict = ("fit **adopted**" if result.fit_adopted else
               "authored weights **kept** (the fit could not satisfy more without overfitting)")
    out = [
        f"# Tuning run — {agent}",
        "",
        f"- **When:** {when_iso}  ·  **Build:** `{build or 'unfiled'}`  ·  **Corrections:** {n_corrections}",
        f"- **Conservatism (`reg`):** {reg}  ·  see [how this works]({methodology})",
        f"- **Weight fit:** {sat}/{result.n_constraints} ranking constraints satisfied — {verdict} "
        f"(the authored seeds alone satisfy {result.base_satisfied}).",
        "",
    ]

    out.append("## Weights tuned")
    if changed:
        for hid, new in sorted(changed.items()):
            old = seeds.get(hid, 0)
            delta = float(new) - float(old)
            out.append(f"- **`{hid}`: {old} → {new}** ({delta:+.2f}, {_band(new)}).")
            drivers = _driving(result, hid)
            if drivers:
                ups = sum(1 for _, s in drivers if s > 0)
                downs = len(drivers) - ups
                out.append(f"  - Moved by {len(drivers)} correction(s) "
                           f"({ups} want it higher, {downs} lower). For example:")
                for c, _s in drivers[:2]:
                    out.append(f"    - {_at(c)} [{c.category}] {_move(c)} — “{_why(c)}”")
    else:
        out.append("- _None._ The fit ships a weight change only when it satisfies **strictly more** "
                   "corrections than the authored seeds; here it did not, so the legible priors are "
                   "kept. (Lower `--reg` to let clean corrections move weights more; the ladder A/B "
                   "is the real test.) The leverage this round is in the new rules below.")
    out.append("")

    out.append("## New rules proposed (need a human-authored `when()`)")
    if result.proposals:
        for p in result.proposals:
            # A scoped proposal (ADR-0049) proposes planner code, not a `when()` — it carries no
            # seed weight, and the scope says which plan layer to look in.
            scope = "" if p.scope == "decision" else f"{p.scope}-scope, "
            out.append(f"- **{p.category}** ({_where(p)}, {scope}seed w={p.seed_weight}): "
                       f"{p.trigger_sketch}")
            if p.rationale:
                out.append(f"  - “{p.rationale.strip()[:200]}”")
    else:
        out.append("- _None._")
    out.append("")

    out.append("## Corrections that need a rule, not a weight (unsatisfied)")
    out.append("_The weight fit cannot make `correct ≻ chosen` here by reweighting existing "
               "hypotheses — they are contradictory, or the distinction needs a new rule._")
    if result.unsatisfied:
        for c in result.unsatisfied:
            out.append(f"- {_at(c)} [{c.category}] {_move(c)} — “{_why(c)}”")
    else:
        out.append("- _None._")
    out.append("")

    if reviewed:
        out.append("## Already reviewed (excluded from fresh work)")
        out.append("_Assessed in an earlier round and recorded in `data/corrections/reviewed.json` — "
                   "not re-surfaced here. `refuted` are also dropped from the weight fit._")
        for c, entry in reviewed:
            e = entry or {}
            out.append(f"- {_at(c)} **{e.get('disposition', '?')}** {_move(c)} — "
                       f"“{e.get('reason', '')}”")
        out.append("")
    return "\n".join(out) + "\n"
