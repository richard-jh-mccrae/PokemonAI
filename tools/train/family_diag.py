"""**Which `state_value` FAMILY decided this flip** — the per-frame attribution the wave scan sheet
cannot give.

    python tools/train/leaf_lab.py diff --baseline data/leaf_lab/baseline.json --out gate.json
    python tools/train/family_diag.py --diff gate.json --out data/leaf_lab/t3-term-diagnosis.md

`wave_scan.py` answers *which frames does the leaf get wrong* and hands them to a human to rule.
This answers the question that comes AFTER the ruling: *which term is responsible*. It simulates the
developer's ruled option and the leaf's top-ranked option, scores both end boards with
`state_value(..., working=...)`, and prints the per-family delta — so a flip stops being "the leaf
ranked it 4th" and becomes "`development` credited a card play +0.20 that nothing charged for".

It exists because of what the un-attributed view cost. Wave 3 closed with 65 frames still gating and
one diagnosis available for all of them — *"the leaf cannot represent sequencing within a turn"* —
which is true of 31 of them and says nothing about the other 34. Reading the family deltas split
those 34 into two clusters with different owners in a single pass (`data/leaf_lab/t3-term-diagnosis.md`),
and surfaced two defects no ruling had named: `threat` saturating into a one-bit term, and `hand`
reading exactly 0.0000 on every leaf board.

**How to read the output.** A family marked `FLAT` moved not at all between the two lines, so it did
not participate in the decision. A term flat on EVERY frame is inert on this path, which is a
stronger finding than a term that is merely wrong — a wrong term can be re-weighted, an inert one is
a blind spot (`state_value.blind_spots`). The `line acct` row is reported beside the families
because it is the only spend charge on the leaf path and is NOT part of the scalar
(`planner._engine_leaf_value` adds it outside), so a comparison that ignored it would mis-attribute
every card play.

**Whose decision is which column** (Issue #356). `leaf` is `_engine_leaf_value`'s argmax over the
menu — ONE rung feeding `_commit_best`, not the agent's answer. `chosen` is what the agent actually
committed, read off the Correction. They are different objects and on real frames they are different
values: on the twelve frames Issue #330 quotes they differ on **12 of 12**. Three issues read the
`leaf` column as the agent's behaviour and filed a claim off it that the corpus does not support, so
both columns are now rendered, explicitly compared, and counted in the header. A `--keys` list must
declare `--source` for the same reason: handed decider-corpus keys — frames selected because the
*live agent* got them wrong — this tool still produces a *leaf* diagnosis, and an unlabelled key list
is the input that produced the false claim.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

#: Below this, in prizes, a family's delta is reported but never named as the frame's DECIDER. The
#: two frames it excludes moved on `readiness` by 0.0034 and 0.0004 prizes — 3.4 and 0.4 points on
#: the leaf's KO_SCORE axis — which is not a term making a judgement, it is float noise wearing one.
#: Naming a decider there would send the next reader after a term that did nothing.
DECIDER_FLOOR = 0.005

#: The one sentence that has to be in the OUTPUT rather than in a docstring, because the misreading
#: happened to a session that had read the surrounding docs (Issue #356). Named so the test can
#: assert on the rendered artifact instead of on a paraphrase of it.
LEAF_CAVEAT = ("**`leaf` is not what the agent did.** It is `planner._engine_leaf_value`'s argmax "
               "over the menu — ONE rung feeding `_commit_best`, which other rungs reach before a "
               "decision is committed. `chosen` is the committed decision, read off the Correction. "
               "`agent ⊨ ruled` is `gates.satisfies_human` (`correct ⊆ chosen`, ADR-0085 Amendment "
               "J), never argmax equality. `ruled` is the ONE index that was simulated: where a "
               "ruling names several, only the first is scored here.")

#: Why THESE frames are in front of you — a property of the key list, not of any frame. Fails closed:
#: `--keys` has no source it can infer, so it must be told one.
SOURCE_CAVEAT = {
    "leaf": ("**Source: leaf.** These keys came from a `leaf_lab.py diff` — frames selected because "
             "the LEAF ranks them wrong. `chosen` is shown for context; the agent may have committed "
             "something else entirely."),
    "decider": ("**Source: decider.** These keys came from the DECIDER corpus — frames selected "
                "because the LIVE AGENT got them wrong. This tool scores the LEAF, so it explains at "
                "most one rung of that failure. Read `chosen` for what the agent did; a `leaf` row "
                "here is a hypothesis about one input to that decision, not a diagnosis of it."),
}


def agent_columns(correction, leaf_top, label, *, equiv=None) -> dict:
    """The AGENT-side columns the leaf columns keep getting mistaken for (Issue #356).

    ``label`` is the caller's index→text renderer, threaded rather than rebuilt so `chosen` is
    formatted by the same `_option_summary` as `ruled` and `leaf` — three columns rendered three ways
    would invite the reader to attribute a wording difference to a decision difference.

    * ``chosen`` — EVERY index the agent committed, joined. A multi-pick select is one decision with
      several slots, and keeping only the first would reproduce this issue's defect in the new column.
      A recorded DECLINE (``[]``) is named rather than left blank; an unreplayable pick is ``?``.
    * ``leaf_is_chosen`` — literal, un-widened: did the leaf's single argmax name exactly the agent's
      pick? It answers "would this row's `leaf` cell have misled me", which is a question about the
      RENDERING, so widening it by equivalence would be answering a different one.
    * ``agent_satisfies_ruled`` — `gates.satisfies_human`, the repo's ONE agreement predicate.
      Equality is the wrong test and measurably so: reading it as equality scored `DISCARD` 1/12
      where the honest number was 10/12. ``equiv`` is threaded in, exactly as both gates thread it.
    """
    from train.gates import satisfies_human

    chosen = None if correction.chosen is None else list(correction.chosen)
    correct = None if correction.correct is None else list(correction.correct)
    if chosen is None:
        rendered = "?"
    elif not chosen:
        rendered = "(declined)"
    else:
        rendered = " + ".join(label(i) for i in chosen)
    return {"chosen": rendered,
            "leaf_is_chosen": chosen is not None and leaf_top is not None and chosen == [leaf_top],
            "agent_satisfies_ruled": satisfies_human(chosen, correct, equiv=equiv)}


def _working(pilot, obs, idx) -> tuple:
    """`state_value`'s per-family breakdown for the end board of taking option ``idx`` first.

    Rides `planner._simulate_line` and `planner._leaf_state_model` rather than rebuilding either, so
    the boards scored here are byte-for-byte the ones the Discrimination Gate ranks. A diagnostic
    that scored its OWN reconstruction would attribute flips to terms the agent never evaluated."""
    from train.leaf_lab import _PLACEHOLDER_SBI
    from common.state_value import state_value

    obs = {**obs, "search_begin_input": obs.get("search_begin_input") or _PLACEHOLDER_SBI}
    pilot._planning = True                       # the rung's reentrancy guard (never nest a search)
    try:
        sim = pilot._simulate_line(obs, [idx])
    except Exception as exc:
        return None, f"sim raised {exc!r}"
    finally:
        pilot._planning = False
    if sim is None:
        return None, "sim unavailable"
    end, my_index, _start_prizes, _result, line_val, _coins, _stream = sim
    working: dict = {}
    try:
        total = state_value(pilot._leaf_state_model(end, my_index), working=working)
    except Exception as exc:
        return None, f"state_value raised {exc!r}"
    return {"total": total, "line": float(line_val), "working": working}, None


def diagnose(keys, *, corrections=None) -> list:
    """One attribution record per frame: the two options, every family's delta, and the DECIDER.

    The decider is the family with the largest delta AGAINST the ruled option — the term that has to
    change for the frame to flip back. Ties and sub-:data:`DECIDER_FLOOR` margins report ``None``
    rather than the argmax of noise."""
    from common.option_equivalence import option_equivalence
    from train.blunder.frame_view import _Cards, _option_summary
    from train.gates import keyed_corrections
    from train.leaf_lab import _cgpy_pilot_builder, board_leaf_values

    keyed = dict(corrections if corrections is not None else keyed_corrections(None))
    pilot_for, cards = _cgpy_pilot_builder(), _Cards()
    out = []
    for key in keys:
        c = keyed.get(key)
        if c is None:
            out.append({"key": key, "error": "not in corpus"})
            continue
        opts = (c.obs.get("select") or {}).get("option") or []
        cur = c.obs.get("current") or {}
        pilot = pilot_for(c.agent)
        values = board_leaf_values(pilot, c.obs)
        top = max((i for i, v in enumerate(values) if v is not None),
                  key=lambda i: values[i], default=None)
        mine = (list(c.correct or []) or [None])[0]

        def label(i):
            if i is None or i >= len(opts):
                return "?"
            return " ".join(_option_summary(i, opts[i], cur, cards, c.seat).split())

        row = {"key": key, "agent": c.agent, "category": c.category,
               "ruled": label(mine), "leaf": label(top),
               **agent_columns(c, top, label, equiv=option_equivalence(opts, c.obs))}
        ruled, err_r = _working(pilot, c.obs, mine) if mine is not None else (None, "no ruled index")
        leaf, err_l = _working(pilot, c.obs, top) if top is not None else (None, "no leaf index")
        if ruled is None or leaf is None:
            out.append({**row, "error": f"ruled: {err_r or 'ok'} / leaf: {err_l or 'ok'}"})
            continue
        deltas = {n: float(ruled["working"].get(n, 0.0)) - float(leaf["working"].get(n, 0.0))
                  for n in sorted(set(ruled["working"]) | set(leaf["working"]))}
        against = {n: d for n, d in deltas.items() if d < -DECIDER_FLOOR}
        out.append({**row, "deltas": deltas,
                    "ruled_terms": dict(ruled["working"]), "leaf_terms": dict(leaf["working"]),
                    "line_delta": ruled["line"] - leaf["line"],
                    "total_delta": ruled["total"] - leaf["total"],
                    "decider": min(against, key=against.get) if against else None})
    return out


def render(rows: list, *, issue: str, source: str) -> str:
    """The diagnosis as Markdown. ``source`` says where the KEYS came from and is mandatory — see
    :data:`SOURCE_CAVEAT`; an unlabelled key list is the input this instrument's defect rode in on."""
    if source not in SOURCE_CAVEAT:
        raise ValueError(f"source must be one of {sorted(SOURCE_CAVEAT)}, got {source!r}")
    ok = [r for r in rows if "deltas" in r]
    families = sorted({n for r in ok for n in r["deltas"]})
    inert = [n for n in families if all(abs(r["deltas"][n]) <= 1e-9 for r in ok)]
    tally = Counter(r["decider"] or "(below floor)" for r in ok)
    comparable = [r for r in rows if "leaf_is_chosen" in r]
    diverged = sum(1 for r in comparable if not r["leaf_is_chosen"])

    out = [f"# `state_value` term diagnosis — the {len(rows)} frames (Issue {issue})", "",
           "**Generated, never hand-maintained** — regenerate with `tools/train/family_diag.py`",
           "(see its docstring). Every number is the per-family delta between the developer's ruled",
           "option and the leaf's top-ranked one, both scored on the board",
           "`planner._simulate_line` actually produces. `decider` is the family that has to change",
           "for the frame to flip back.", "",
           SOURCE_CAVEAT[source], "",
           LEAF_CAVEAT, "",
           f"**`leaf` DIFFERS from `chosen` on {diverged} of {len(comparable)} frames** — so on those "
           "rows the `leaf` cell is not a record of the agent's behaviour and no claim about what the "
           "agent does may be read off it.", "",
           "**Inert on every frame** (flat on both sides of every comparison — a family that did not",
           "participate in any of these decisions at all, which is a blind spot rather than a",
           f"mis-weighting): {', '.join(f'`{n}`' for n in inert) or '(none)'}.", "",
           "**Deciders:** " + ", ".join(f"`{n}` {k}" for n, k in tally.most_common()), "",
           "| frame | agent | category | decider | ruled | leaf | chosen (agent played) | "
           "leaf vs chosen | agent ⊨ ruled | " +
           " | ".join(f"Δ {n}" for n in families) + " | Δ line |",
           "|---|---|---|---|---|---|---|---|---|" + "---|" * (len(families) + 1)]
    esc = lambda s: (s or "").replace("|", "\\|")                      # noqa: E731 — table cells
    for r in sorted(rows, key=lambda r: (r.get("decider") or "~", r.get("category") or "", r["key"])):
        # The agent-side cells are read off the CORPUS, so they survive a leaf failure and are
        # rendered on an errored row too — blanking them would hide the one column this issue adds.
        # A row with no Correction at all (`not in corpus`) knows NEITHER, and says so with `—`
        # rather than falling through to `DIFFERS`/`disagrees`, which would assert a comparison
        # nothing performed — the same defect one column over.
        known = "leaf_is_chosen" in r
        agent_cells = (f"{esc(r.get('chosen')) if known else '—'} | "
                       f"{('same' if r['leaf_is_chosen'] else '**DIFFERS**') if known else '—'} | "
                       f"{('satisfies' if r['agent_satisfies_ruled'] else 'disagrees') if known else '—'} |")
        if "deltas" not in r:
            out.append(f"| `{esc(r['key'])}` | {r.get('agent', '')} | {r.get('category', '')} "
                       f"| **{r.get('error', 'error')}** | {esc(r.get('ruled'))} | {esc(r.get('leaf'))} "
                       f"| {agent_cells}" + " |" * (len(families) + 1))
            continue
        out.append(f"| `{esc(r['key'])}` | {r['agent']} | {r['category']} "
                   f"| **{r['decider'] or '—'}** | {esc(r['ruled'])} | {esc(r['leaf'])} | {agent_cells} "
                   + " | ".join(f"{r['deltas'][n]:+.4f}" for n in families)
                   + f" | {r['line_delta']:+.1f} |")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Attribute Discrimination-Gate flips to state_value terms")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--diff", type=Path,
                     help="a `leaf_lab.py diff --out` artifact; every GATING flip in it is diagnosed")
    src.add_argument("--keys", type=Path, help="a file of frame keys, one per line; REQUIRES --source")
    ap.add_argument("--source", choices=sorted(SOURCE_CAVEAT),
                    help="where a --keys list came from. Mandatory with --keys and refused with "
                         "--diff, which is a leaf_lab artifact and says so itself.")
    ap.add_argument("--out", type=Path, required=True, help="the Markdown diagnosis to write")
    ap.add_argument("--issue", default="#262", help="the track issue the frames belong to")
    args = ap.parse_args(argv)

    if args.diff:
        if args.source and args.source != "leaf":
            ap.error("--diff is a leaf_lab.py artifact; --source decider contradicts it")
        source = "leaf"
        diff = json.loads(args.diff.read_text(encoding="utf-8"))
        excused = set(diff.get("held_out") or {}) | set(diff.get("voided") or {})
        keys = [k for k in (diff.get("ok_to_miss") or []) if k not in excused]
    else:
        # FAILS CLOSED (Issue #356). A bare key list is exactly what three issues fed this tool
        # before reading its LEAF column as the AGENT's behaviour; the tool cannot infer the
        # provenance, so it refuses rather than diagnosing an unlabelled corpus.
        if not args.source:
            ap.error("--keys requires --source {leaf,decider}: a key list carries no provenance and "
                     "the diagnosis means different things per source (see SOURCE_CAVEAT)")
        source = args.source
        keys = [ln.strip() for ln in args.keys.read_text(encoding="utf-8").splitlines() if ln.strip()]

    rows = diagnose(keys)
    # LF bytes: this file is committed and read on both platforms (CLAUDE.md), and `write_text`
    # would frame it per whichever OS ran the command.
    args.out.write_bytes(render(rows, issue=args.issue, source=source).encode("utf-8"))
    print(f"{len(rows)} frames diagnosed -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
