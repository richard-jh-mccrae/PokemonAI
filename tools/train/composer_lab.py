"""Composer lab — replay corpus frames through the **sequence composer** and report what it would do
(POC-T4/4, Issue #385; spec Issue #263 § *The composer lab*).

An **OFFLINE tool, run on demand** — never a runtime shadow (ADR-0092 decision 4). It is T4/5's
pre-arming evidence and T4/7's verification instrument, and at this commit the composer it drives is
DARK, so nothing here changes a decision anywhere.

    python tools/train/composer_lab.py                      # the whole corpus
    python tools/train/composer_lab.py --agent dragapult_ex
    python tools/train/composer_lab.py --frame 85046350-32  # ONE frame, with its verbatim ideal line
    python tools/train/composer_lab.py --acceptance         # f32 / f35 / f82 in-beam at this width
    python tools/train/composer_lab.py --epsilon-sweep      # tune EPSILON against the corpus
    python tools/train/composer_lab.py --out reports/composer.json

## Every column is LABELLED, because a column that can be misread WILL be misread

The `family_diag.py` lesson (Issue #356): a session that had read the surrounding docs still misread
an instrument's columns, so the disambiguating sentence has to be in the OUTPUT and not in a
docstring. Three different things are rendered side by side here and they are three different
questions:

* **`composer`** — the first action the composer's best sequence commits to. NOT a decision the agent
  made; the composer is dark and nothing calls it.
* **`chosen`** — what the agent ACTUALLY did, read off the Correction. It is the committed decision,
  produced by the whole Pilot ladder, of which the leaf is one rung.
* **`ruled`** — the human's `correct` picks. The only one of the three that is a judgement.

Agreement is reported against BOTH, and neither is called "right" by this tool: the composer agreeing
with `chosen` says it reproduces today's agent, and agreeing with `ruled` says it plays better. They
are different results and collapsing them would hide which one happened.

## What it does NOT do, stated so the gap is not mistaken for a pass

**It does not grade the 41 verbatim ideal turn sequences automatically.** Those are developer prose
(`data/leaf_lab/wave3-rulings.md` § *Ideal turn sequences*, indexed by Issue #291 §3c), and the file
says outright *"Do not tidy these"* — a sequence parsed into option indices has already been
interpreted once, which is precisely what the verbatim convention exists to prevent. So the lab
RENDERS the developer's line verbatim beside the composer's, and a human reads them. Issue #291's
index is consumed for the `kind` column (`sequence` / `pointer` / `verdict-only`), because 16 of the
41 name a single action and cannot falsify a sequence composer at all.

## The acceptance frames, and the one this lab cannot yet settle

Issue #263's five named targets were located by Issue #291 §3c (they are ruled in fixtures, not in
that file) and are carried here as :data:`ACCEPTANCE` so `--acceptance` can check the property
Issue #385 actually asks for: **their first steps IN-BEAM at the chosen width**, demonstrated by the
margin telemetry rather than by the line merely appearing.

⚠️ **f32 and f35 are a retreat maneuver, and Issue #392 is the open ruling on whether a retreat can
reach the beam at all.** A `_RETREAT` option is the bare `{"type": 12}` in 5807 of 5807 offered
occurrences across the parity corpus, so its 1-ply delta is the allowance bit and nothing else — a
near-zero against a leaf that scores the board. `--acceptance` therefore MEASURES the rank rather
than asserting it, and prints the ruling's issue number beside a miss. Conforming that measurement
by widening the beam until it passes would be answering a developer's design call with a constant.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common import composer as cp                              # noqa: E402

#: `data/leaf_lab/wave3-rulings.md`, the durable ruling record this lab READS and never writes.
RULINGS = REPO / "data" / "leaf_lab" / "wave3-rulings.md"

#: The sentence that has to be in the OUTPUT rather than in this docstring (the Issue #356 lesson).
COLUMN_CAVEAT = (
    "**`composer` is not what the agent did.** It is `common.composer.compose`'s best sequence, and "
    "the composer is DARK at this commit — nothing in production calls it. `chosen` is the committed "
    "decision read off the Correction (the whole Pilot ladder, of which the leaf is one rung), and "
    "`ruled` is the human's judgement — taken from the committed FIXTURE where one has re-ruled the "
    "frame (`ruled_from`), because a re-ruling never rewrites the `data/corrections/` record and the "
    "record's own `correct` is then the stale one. Agreement is reported against both `chosen` and "
    "`ruled` because they are different questions: matching `chosen` means the composer reproduces "
    "today's agent, matching `ruled` means it plays better.")

#: Issue #263's five named acceptance targets, located by Issue #291 §3c — *"they are NOT missing"* —
#: with the fixture each one is ruled in. Frame keys are the `gates.correction_frame_key` form.
ACCEPTANCE = {
    "85046350|0|decision|32": ("f32", "dragapult_hammer_over_develop_f32.json — the "
                               "retreat-to-sacrificial-item-lock-wall maneuver "
                               "(docs/plans/turn-planner-retreat-to-item-lock-wall.md)"),
    "86091435|0|decision|35": ("f35", "dp_hold_evolve_until_typed_ready_f35.json — the only "
                               "`turn_plan.intended_line` in the fixture store; its 4b branch IS the "
                               "f32 maneuver, so f32 and f35 are the SAME class"),
    "85785609|0|turn|8": ("f82", "dp_evolve_energized_line_body_first_f82.json — the Adrena-Brain "
                          "KO line; full chain in Issue #165's body (ADR-0070 §C)"),
}

#: The open BEAM-ADMISSION ruling a retreat-first acceptance frame runs into. Named in the output so a
#: miss reads as *"this is the ruling that is owed"* rather than as *"widen the beam until it passes"*.
RETREAT_RULING = ("Issue #392 — a `_RETREAT` option is TARGETLESS (5807/5807 in the parity corpus), "
                  "so its 1-ply delta is the allowance bit alone and a plain top-k beam prunes it "
                  "before the follow-up `_SWITCH` that carries the maneuver's value. RULED, not "
                  "tuned.")


# ── Issue #291 §3c's index, consumed rather than re-derived ──────────────────────────────────────


def fixture_rulings() -> dict:
    """``{frame key: [ruled option index]}`` from the committed FIXTURES — the authoritative ruling
    where one exists, overriding the `data/corrections/` record.

    **This is not defensive plumbing; it is a defect this lab shipped with.** A Correction's
    ``correct`` is the record as first tagged, and a re-ruling lands in the fixture store as a
    ``claims.decision`` block rather than by rewriting the record — `gates.ruling_index`'s own
    docstring says so outright: *"Read-only. No Correction record is rewritten."* So a frame that has
    been re-ruled reads TWO ways, and the store's way is the stale one.

    **f32 is exactly that frame, and it is one of Issue #263's three named acceptance targets.**
    `dragapult_hammer_over_develop_f32.json` rules `correct: [3]` — the `_RETREAT`, labelled *"Retreat
    Dreepy → promote Budew (sacrificial item-lock wall)"* — and records that it *"is a 2026-07-10
    REFRAME of that record's correct=[1]"*. Reading the store gave `[1]`, an `_EVOLVE`, which made
    this lab grade the acceptance criterion against an option the developer had superseded, and made
    a session conclude Issue #392's blocking premise was false when it is true.

    Read through `gates.iter_keyed_fixtures` — *"THE one corpus walk"* — rather than a second glob,
    for the reason that module gives: a hand-built second reader is the drift ADR-0087 charges for one
    store over, and it already cost the Decision Gate 203 of its 372 keys."""
    from train.gates import iter_keyed_fixtures
    out = {}
    for _path, _fx, key, claims in iter_keyed_fixtures():
        if claims.decision and claims.decision.correct:
            out[key] = list(claims.decision.correct)
    return out


def ideal_index(path: Path = RULINGS) -> dict:
    """``{frame key: {"kind", "agent"}}`` from Issue #291 §3c's INDEX table.

    Consumed, never re-derived: the classification rule (*"an entry is a `sequence` when the
    developer's line names two or more ordered actions"*) is a ruling recorded in that file, and a
    second implementation of it here would drift while both stayed internally consistent. Parsed off
    the table because the table IS the artifact Issue #291 delivered.

    **SCOPED to that one section, not swept over the file.** The `| n | frame | ... |` row shape is
    not unique in `wave3-rulings.md` — an unscoped sweep returned **48** rows against the artifact's
    own stated **41**, silently folding in the closeout batch's owner tables. The count mismatch is
    the only tell, which is why `test_composer_lab.py` asserts Issue #291's exact 22 / 3 / 16 split
    rather than merely that some rows parsed: an instrument that over-collects still looks like it
    works."""
    rows = {}
    if not path.exists():
        return rows
    section = path.read_text(encoding="utf-8").split("### INDEX", 1)
    if len(section) < 2:
        return rows
    for line in section[1].split("\n### ", 1)[0].splitlines():
        if not re.match(r"^\|\s*\d+\s*\|", line):
            continue
        # Split on UNESCAPED pipes only. A frame key is `<ep>|<seat>|<scope>|<subject>`, which
        # Markdown forces to be written `\|` inside a table cell — and three of these rows are
        # pointers whose KIND column embeds another frame key. A plain `[^|]+` column match therefore
        # stops inside that key and shifts every later column: it parsed the agent of those three
        # rows as `0\`, which is the middle of an episode id. Caught because the agent column stopped
        # being one of the two decks the artifact says it is.
        cells = [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", line)]
        if len(cells) < 5:
            continue
        key = cells[2].strip("`")
        rows[key] = {"kind": re.sub(r"[*⚠️]", "", cells[3]).strip(), "agent": cells[4]}
    return rows


def ideal_sequences(path: Path = RULINGS) -> dict:
    """``{frame key: the developer's line, VERBATIM}`` from § *Ideal turn sequences*.

    Read exactly as written — typos, abbreviations and all — because the file says so in its own
    header and means it: *"a sequence rewritten in your words has already been interpreted once"*.
    This lab prints them; it never parses them into option indices."""
    out = {}
    if not path.exists():
        return out
    text = path.read_text(encoding="utf-8")
    for hit in re.finditer(r"^- `([^`]+)` — (.+?)(?=^- `|^\n[#*]|\Z)", text, flags=re.M | re.S):
        out[hit.group(1)] = " ".join(hit.group(2).split())
    return out


# ── the off-policy exposure (Issue #412), REPORTED and never filtered on ─────────────────────────


#: The MAIN select context, from `board_delta`'s own vocabulary rather than a literal `0` here — the
#: composer's grading base is the MAIN menu, and a second spelling of which integer that is would be
#: the drift ADR-0087 charges for one store over.
from common.board_delta import CONTEXT_MAIN as _CONTEXT_MAIN     # noqa: E402


def off_policy_index(corrections) -> dict:
    """``{(agent, episode id): [every Correction in that episode]}`` — the input
    `grab_sweep._off_policy` takes.

    Built here rather than inside the row loop because it is a property of the whole store: the scan
    asks *"did the human rule against an EARLIER decision in this same turn?"*, which no single frame
    can answer about itself."""
    by_ep: dict = {}
    for c in corrections:
        by_ep.setdefault((c.agent, c.episode_id), []).append(c)
    return by_ep


def off_policy_reasons(correction, by_ep: dict) -> list:
    """Why this frame is not cleanly gradeable, or ``[]`` — `grab_sweep._off_policy`, **consumed**.

    Issue #412's doctrine is *a follow-up select is only gradeable if the decision that opened it was
    correct*: if the human ruled against an earlier decision in the same turn, this board is one the
    agent should never have reached, and what it does here is not evidence about what it does.

    The detector is deliberately reused rather than re-spelled. `grab_sweep._off_policy` is already
    **context-agnostic** — only its `_ctx7` caller is scoped to `_TO_HAND` selects — so pointing it at
    the MAIN population is a change of population, not of instrument, and a second implementation
    here would be the drift ADR-0087 charges for one store over.

    ⚠️ **This lab REPORTS the count and never filters on it.** Issue #412 ruled the doctrine for the
    *follow-up select*; extending it to MAIN -> MAIN within one turn is a **generalisation the
    developer has not ruled on**, and silently dropping those frames would be conforming to an
    unruled premise — exactly what this track forbids. Issue #412 owns the ruling; this column is the
    measurement it would be ruled against."""
    from train.grab_sweep import _off_policy
    return list(_off_policy(correction, by_ep))


def off_policy_control(corrections) -> dict:
    """The POSITIVE CONTROL for the column above: the same detector, over the ctx-7 population it was
    built for and ruled on.

    *"Found nothing"* and *"my instrument is broken"* return the same empty output, so a MAIN-context
    count is worth nothing on its own. Issue #412 measured **15 of 30** ctx-7 frames flagged; if this
    control comes back silent, the reading against the MAIN population is an artifact and must not be
    reported as a finding."""
    from train.grab_sweep import _TO_HAND
    by_ep = off_policy_index(corrections)
    ctx7 = [c for c in corrections
            if ((c.obs or {}).get("select") or {}).get("context") == _TO_HAND]
    flagged = sum(1 for c in ctx7 if off_policy_reasons(c, by_ep))
    return {"population": len(ctx7), "flagged": flagged,
            "healthy": bool(ctx7) and flagged > 0}


# ── one frame ────────────────────────────────────────────────────────────────────────────────────


def compose_frame(pilot, correction, *, rulings=None, by_ep=None, k=None, epsilon=None,
                  depth=None) -> dict:
    """Run the composer on ONE corpus frame and record all three answers plus the telemetry.

    ``rulings`` is :func:`fixture_rulings`' map and OVERRIDES the Correction's own ``correct`` where a
    committed fixture has re-ruled the frame. Not optional in practice — see that function for the
    acceptance target this lab graded against a superseded ruling until it existed.

    Builds the model through `pilot._leaf_state_model` — the SAME seam the planner leaf uses and the
    same one `value_lab.py` builds through — rather than assembling one here. A harness that built its
    own model would be measuring a board the agent never scores, which is the instrument/rung drift
    the decider sweeps rotted from.

    A failure is CAPTURED, never raised: the coverage job is to report which frames the composer
    cannot run on and why, and a harness that stops at the first one answers *"is there a failure"*
    instead of *"how many, and where"*."""
    from train.gates import correction_frame_key

    obs = correction.obs or {}
    options = (obs.get("select") or {}).get("option") or []
    my_index = ((obs.get("current") or {}).get("yourIndex")) or 0
    key = correction_frame_key(correction)
    ruled = (rulings or {}).get(key)
    row = {"key": key, "agent": getattr(correction, "agent", None),
           "options": len(options),
           "chosen": list(correction.chosen or []),
           "ruled": list(ruled if ruled is not None else (correction.correct or [])),
           "ruled_from": "fixture" if ruled is not None else "correction",
           # Issue #412's exposure — REPORTED, never filtered on. See `off_policy_reasons`.
           "off_policy": off_policy_reasons(correction, by_ep) if by_ep else [],
           # The select context, carried so the off-policy count can be scoped to the population
           # this composer actually grades on. `0` is MAIN; everything else is a follow-up select,
           # where Issue #412's doctrine is already RULED rather than a generalisation.
           "context": ((obs.get("select") or {}).get("context")),
           "composer": None, "steps": None, "score": None, "margin": None, "ruled_margin": None,
           "gaps": [], "bounds": [], "ms": None, "leaf_evals": None, "blocks": None,
           "coverage_gap": "", "expanded_families": None, "expansion_children": None,
           "no_scorable": False, "error": None}
    if not options:
        row["error"] = "frame carries no select menu"
        return row
    kwargs = {kw: v for kw, v in (("k", k), ("epsilon", epsilon), ("depth", depth))
              if v is not None}
    try:
        t0 = time.perf_counter()
        model = pilot._leaf_state_model(obs, my_index)
        result = cp.compose(model, options, **kwargs)
        row["ms"] = (time.perf_counter() - t0) * 1000.0
    except Exception as exc:                     # noqa: BLE001 — the finding IS the exception
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row
    chosen = result.chosen
    row["margin"] = result.margin.working()
    row["gaps"] = list(result.gaps)
    # §S3.5: BOTH bounds per expectation node. The gap between them is the epistemic exposure the
    # max-over-an-availability-weighted-enumeration carries, and it is recorded rather than argued.
    row["bounds"] = [b.working() for b in result.bounds]
    row["leaf_evals"] = result.stats["leaf_evals"]
    row["expanded_families"] = result.stats["expanded_families"]
    row["expansion_children"] = result.stats["expansion_children"]
    row["blocks"] = [list(b) for b in result.blocks]
    # The RULED option's own rank — a DIFFERENT question from the composer's, and the one both
    # Issue #385's lab acceptance and Issue #392's criterion actually ask: *"f32/f35/f82's first
    # steps IN-BEAM at the chosen width"* is about the maneuver the human ruled, which is the option
    # a beam would prune. Measuring the composer's own pick would pass by construction. Best of the
    # ruled picks, since any of them satisfies the ruling (`gates.satisfies_human`'s reading).
    ruled = [result.margin_for(i).working() for i in row["ruled"]]
    if ruled:
        row["ruled_margin"] = min(ruled, key=lambda m: (m["rank"] is None, m["rank"] or 0))
    row["no_scorable"] = chosen is None or (chosen.first_index is None and not chosen.steps)
    if chosen is not None:
        row["composer"] = chosen.first_index
        row["steps"] = [s.index for s in chosen.steps]
        row["score"] = chosen.score
        row["coverage_gap"] = chosen.coverage_gap
    return row


def _agrees(row, column: str) -> bool | None:
    """Does the composer's first action land inside ``row[column]``? None when there is nothing to
    compare — an empty ruling or a frame the composer could not run on."""
    picks = row.get(column) or []
    if row.get("composer") is None or not picks:
        return None
    return row["composer"] in picks


# ── the corpus ───────────────────────────────────────────────────────────────────────────────────


def composer_lab_report(pilot_for, corrections, **kwargs) -> dict:
    """Aggregate over the corpus: agreement against both columns, margins, wall-clock, gaps."""
    rows, skipped = [], 0
    rulings = fixture_rulings()
    by_ep = off_policy_index(corrections)
    for c in corrections:
        if not (getattr(c, "obs", None) or {}):
            continue
        pilot = pilot_for(getattr(c, "agent", None))
        if pilot is None:
            skipped += 1
            continue
        rows.append(compose_frame(pilot, c, rulings=rulings, by_ep=by_ep, **kwargs))
    ran = [r for r in rows if r["error"] is None and r["composer"] is not None]
    times = sorted(r["ms"] for r in ran)
    bounds = [b for r in rows for b in r["bounds"]]
    margins = [r["margin"]["margin_to_kth"] for r in ran
               if r["margin"] and r["margin"]["margin_to_kth"] is not None]
    return {
        "caveat": COLUMN_CAVEAT,
        "caps": {"beam_width": kwargs.get("k") or cp.BEAM_WIDTH,
                 "sequence_depth": kwargs.get("depth") or cp.SEQUENCE_DEPTH,
                 "epsilon": kwargs.get("epsilon") if kwargs.get("epsilon") is not None
                 else cp.EPSILON},
        "n": len(rows), "ran": len(ran), "failed": sum(1 for r in rows if r["error"]),
        "skipped_agent": skipped,
        "agree_chosen": sum(1 for r in ran if _agrees(r, "chosen")),
        "agree_ruled": sum(1 for r in ran if _agrees(r, "ruled")),
        "comparable_chosen": sum(1 for r in ran if _agrees(r, "chosen") is not None),
        "comparable_ruled": sum(1 for r in ran if _agrees(r, "ruled") is not None),
        "in_beam": sum(1 for r in ran if r["margin"] and r["margin"]["in_beam"]),
        "ruled_in_beam": sum(1 for r in rows if r["ruled_margin"] and r["ruled_margin"]["in_beam"]),
        # ADMITTED is the weaker and honest reading: a terminal or a refused option survives pruning
        # unconditionally, carrying delta 0.0 because it was never applied, so counting it as
        # `in_beam` would report a tie at zero as a preference. Both numbers are printed.
        "ruled_admitted": sum(1 for r in rows if r["ruled_margin"] and r["ruled_margin"]["admitted"]),
        "ruled_comparable": sum(1 for r in rows if r["ruled_margin"]),
        # Not a failure and not a pass: at a non-MAIN select every option is a `_CARD`/`_YES`/
        # `_NUMBER` whose whole content is a card effect, so the seam refuses all of them and the
        # composer has no opinion. Counted apart from `failed` so neither is read as the other.
        "no_scorable": sum(1 for r in rows if r["no_scorable"] and not r["error"]),
        "median_ms": statistics.median(times) if times else None,
        "p95_ms": _percentile(times, 0.95), "max_ms": max(times) if times else None,
        "median_margin": statistics.median(margins) if margins else None,
        "multi_step": sum(1 for r in ran if len(r["steps"] or ()) > 1),
        "blocks_found": sum(1 for r in ran if r["blocks"]),
        "gap_frames": sum(1 for r in ran if r["gaps"]),
        # §S7 D4: an expanded family is ONE beam slot holding N scored instances. Both numbers are
        # printed because their RATIO is what says whether the parent-slot rule is doing any work.
        "expanded_families": sum(r["expanded_families"] or 0 for r in ran),
        "expansion_children": sum(r["expansion_children"] or 0 for r in ran),
        "expansion_frames": sum(1 for r in ran if r["expanded_families"]),
        # §S3.5: both bounds per expectation node, and the GAP between them — the over-read the max
        # carries against the under-read `.expected()` carries. Neither is smoothed into a third.
        "expectation_nodes": len(bounds),
        "median_bound_gap": statistics.median([b["gap"] for b in bounds]) if bounds else None,
        "max_bound_gap": max((b["gap"] for b in bounds), default=None),
        "truncated_nodes": sum(1 for b in bounds if b["truncated"]),
        # §S10.2 (Issue #412) — REPORTED, NOT filtered. See `off_policy_reasons`. Scoped to the MAIN
        # population as well as reported whole, because MAIN is this composer's grading base and it
        # is the ONLY half where the doctrine is an unruled generalisation: at a follow-up select
        # Issue #412 has already ruled it.
        "off_policy": sum(1 for r in rows if r["off_policy"]),
        "off_policy_ruled": sum(1 for r in rows if r["off_policy"] and r["ruled"]),
        "off_policy_main": sum(1 for r in rows
                               if r["off_policy"] and r["context"] == _CONTEXT_MAIN and r["ruled"]),
        "ruled_main": sum(1 for r in rows if r["context"] == _CONTEXT_MAIN and r["ruled"]),
        "off_policy_control": off_policy_control(corrections),
        "rows": rows,
    }


#: `value_lab`'s order-statistic rule, IMPORTED rather than re-spelled. The two labs' tails have to be
#: comparable — this one reports the composer's per-decision wall-clock against the leaf unit cost
#: that one reports — and `value_lab._percentile`'s own docstring argues for exactly one spelling,
#: because a product of two hand-written percentile conventions is not a percentile of anything.
from train.value_lab import _percentile                        # noqa: E402


def epsilon_sweep(pilot_for, corrections, bands) -> list:
    """How many frames each epsilon band RESCUES — the measurement Issue #263 requires instead of a
    guessed constant (*"epsilon tuned against the corpus via the lab below, never guessed"*).

    A band that rescues nothing is not a band; a band that rescues everything is not a cutoff.

    ⚠️ **The number reported is `band_only`, and the first draft of this function reported one that
    could not move.** It counted frames whose chosen first step was `in_beam`-false and inside the
    band — but `in_beam` means *earned a scored top-k slot*, which is a property of the RANKING and is
    invariant in epsilon by construction, so the metric read the same at every band and would have
    "measured" a tuned constant without ever testing it. That is the vacuous-instrument failure
    `decider_lab`'s own docstring exists about, caught here by the numbers refusing to move.

    `band_only` is the honest population: the chosen first step ranked BELOW k and survived pruning
    anyway. `agree_ruled` is carried beside it because a band that changes what is admitted without
    changing any answer has bought nothing."""
    out = []
    for band in bands:
        rpt = composer_lab_report(pilot_for, corrections, epsilon=band)
        ran = [r for r in rpt["rows"] if r["margin"]]
        band_only = sum(1 for r in ran
                        if r["margin"]["admitted"] and not r["margin"]["always_expand"]
                        and (r["margin"]["rank"] or 0) > r["margin"]["k"])
        out.append({"epsilon": band, "ran": rpt["ran"], "in_beam": rpt["in_beam"],
                    "band_only": band_only, "agree_ruled": rpt["agree_ruled"],
                    "agree_chosen": rpt["agree_chosen"]})
    return out


# ── rendering ────────────────────────────────────────────────────────────────────────────────────


def _print_report(rpt, *, frame=None, index=None, verbatim=None) -> None:
    caps = rpt["caps"]
    print(f"\n=== composer lab: {rpt['n']} frames "
          f"({rpt['ran']} composed, {rpt['failed']} FAILED, {rpt['skipped_agent']} agent-skip) ===")
    print(f"  caps: beam_width={caps['beam_width']}  sequence_depth={caps['sequence_depth']}  "
          f"epsilon={caps['epsilon']}   (whitelisted: sound_rules.composer-budget-caps)")
    print(f"\n  {rpt['caveat']}\n")
    print(f"  composer == chosen : {rpt['agree_chosen']}/{rpt['comparable_chosen']}"
          "    (reproduces today's agent)")
    print(f"  composer == ruled  : {rpt['agree_ruled']}/{rpt['comparable_ruled']}"
          "    (plays what the human ruled)")
    print(f"  composer 1st in beam: {rpt['in_beam']}/{rpt['ran']}"
          "    (hard top-k; the rest survived on the epsilon band or not at all)")
    print(f"  RULED 1st admitted  : {rpt['ruled_admitted']}/{rpt['ruled_comparable']}"
          "    <- the property Issue #385/#392 ask about: would a beam have REACHED the human's line")
    print(f"     ... of which EARNED a scored top-k slot: {rpt['ruled_in_beam']}"
          "    (the rest are terminals/refusals, admitted unconditionally at delta 0.0)")
    print(f"  no scorable option  : {rpt['no_scorable']}"
          "    (every option refused — a non-MAIN select; a REPORT, not a failure)")
    print(f"  multi-step lines   : {rpt['multi_step']}    commutative blocks found: "
          f"{rpt['blocks_found']}    frames with a coverage gap: {rpt['gap_frames']}")
    ctl = rpt["off_policy_control"]
    print(f"  OFF-POLICY (Issue #412): {rpt['off_policy_main']}/{rpt['ruled_main']} ruled MAIN "
          f"frames — this composer's grading base   ({rpt['off_policy']}/{rpt['n']} over all "
          f"contexts)"
          "\n     REPORTED, NOT filtered — a follow-up select is only gradeable if the decision that"
          "\n     opened it was correct, but extending that from follow-up-select to MAIN->MAIN"
          "\n     within a turn is a generalisation NOBODY HAS RULED ON. Issue #412 owns it."
          f"\n     positive control (the ctx-7 population the detector was ruled on): "
          f"{ctl['flagged']}/{ctl['population']} flagged"
          + ("" if ctl["healthy"] else "   <- ⚠️ CONTROL SILENT: the count above means nothing"))
    print(f"  deferred-target expansion: {rpt['expanded_families']} families -> "
          f"{rpt['expansion_children']} scored instances over {rpt['expansion_frames']} frames"
          "    (D4: each family is ONE beam slot, taken by its best child)")
    if rpt["expectation_nodes"]:
        print(f"  expectation nodes  : {rpt['expectation_nodes']}   BOTH bounds reported — "
              f"median max-minus-expected {rpt['median_bound_gap']:+.5f}, "
              f"max {rpt['max_bound_gap']:+.5f} prizes"
              f"   ({rpt['truncated_nodes']} truncated by the branch cap)")
    if rpt["median_ms"] is not None:
        print(f"\n  wall-clock per decision: median {rpt['median_ms']:.2f} ms | "
              f"P95 {rpt['p95_ms']:.2f} ms | max {rpt['max_ms']:.2f} ms")
    if rpt["median_margin"] is not None:
        print(f"  median margin to the k-th candidate: {rpt['median_margin']:+.4f} prizes")

    failed = [r for r in rpt["rows"] if r["error"]]
    if failed:
        print(f"\n  FAILED ({len(failed)}) — named, never counted:")
        for r in failed[:20]:
            print(f"    {r['key']:<28} {r['error']}")
        if len(failed) > 20:
            print(f"    ... and {len(failed) - 20} more")

    if frame:
        for r in [x for x in rpt["rows"] if frame in (x["key"] or "")]:
            _print_frame(r, index or {}, verbatim or {})


def _print_frame(row, index: dict, verbatim: dict) -> None:
    print(f"\n--- {row['key']} ({row['agent']}) ---")
    if row["error"]:
        print(f"    ERROR {row['error']}")
        return
    print(f"    composer  first action {row['composer']}   sequence {row['steps']}   "
          f"score {row['score']:+.4f} prizes")
    print(f"    chosen    {row['chosen']}      <- what the agent ACTUALLY did (the Correction)")
    print(f"    ruled     {row['ruled']}      <- the human's judgement "
          f"(from the {row['ruled_from']})")
    print(f"    margin(composer) {row['margin']}")
    print(f"    margin(RULED)    {row['ruled_margin']}"
          "   <- did the beam REACH the human's first step")
    if row["off_policy"]:
        print(f"    ⚠️ OFF-POLICY (Issue #412, reported not filtered): {row['off_policy']}")
    if row["bounds"]:
        print("    expectation nodes — BOTH bounds; `best` (max) ORDERS, `expected` is the "
              "reported lower bound:")
        for b in row["bounds"][:6]:
            print(f"      option {b['index']}: best {b['best']:+.5f}  expected {b['expected']:+.5f}"
                  f"  gap {b['gap']:+.5f}  over {b['classes']} classes"
                  + (f"  (+{b['truncated']} TRUNCATED, mass {b['total_probability']:.3f})"
                     if b["truncated"] else ""))
    if row["blocks"]:
        print(f"    commutative blocks: {row['blocks']}")
    if row["gaps"]:
        print("    coverage gaps (a refusal is an unknown, NOT a zero):")
        for gap in row["gaps"][:8]:
            print(f"      {gap}")
    meta = index.get(row["key"])
    if meta:
        print(f"    ideal-line kind: {meta['kind']}   (Issue #291 §3c's index)")
    line = verbatim.get(row["key"])
    if line:
        print("    the developer's line, VERBATIM — read it against the sequence above; this tool "
              "never parses it:")
        print(f"      {line}")


def _print_acceptance(rpt) -> None:
    """Issue #385's lab acceptance: f32 / f35 / f82's first steps IN-BEAM at the chosen width."""
    print("\n=== acceptance frames — Issue #263's five named targets, located by Issue #291 §3c ===")
    print("  The property is the MARGIN TELEMETRY (rank at 1-ply relative to k), not the line merely")
    print("  appearing. A miss re-sizes the width FROM THE MEASUREMENT — or, for a retreat-first")
    print("  maneuver, is the open ruling below rather than anything to tune.\n")
    seen = set()
    for row in rpt["rows"]:
        target = ACCEPTANCE.get(row["key"])
        if not target:
            continue
        seen.add(row["key"])
        label, where = target
        # The RULED first step, never the composer's own — see `compose_frame`. A harness that
        # measured its own answer would report a pass whenever it answered at all.
        margin = row["ruled_margin"] or {}
        verdict = ("IN BEAM" if margin.get("in_beam")
                   else "ADMITTED" if margin.get("admitted") else "MISS")
        print(f"  {label:<5} {row['key']:<26} {verdict:<9} ruled first step: rank "
              f"{margin.get('rank')} of k={margin.get('k')} over {margin.get('ranked')} ranked   "
              f"margin {margin.get('margin_to_kth')}"
              + ("   (always-expand: a terminal/refusal, delta 0.0 by construction)"
                 if margin.get("always_expand") else ""))
        print(f"        ruled {row['ruled']} (from the {row['ruled_from']})   "
              f"composer {row['composer']} (sequence {row['steps']})")
        print(f"        {where}")
        if not margin.get("admitted"):
            print(f"        ⚠️ {RETREAT_RULING}")
    for key, (label, where) in ACCEPTANCE.items():
        if key not in seen:
            print(f"  {label:<5} {key:<26} NOT IN CORPUS   (not replayable from this store)")
            print(f"        {where}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--store", type=Path, default=None,
                    help="corrections file or tree (default: the committed corpus)")
    ap.add_argument("--agent", default=None, help="only this agent's frames")
    ap.add_argument("--frame", default=None,
                    help="print ONE frame: the composer's sequence, the committed decision, the "
                         "ruling, and the developer's verbatim ideal line if there is one")
    ap.add_argument("--acceptance", action="store_true",
                    help="report f32 / f35 / f82's first steps IN-BEAM at the chosen width")
    ap.add_argument("--epsilon-sweep", action="store_true",
                    help="how many frames each epsilon band rescues (the tuning measurement)")
    ap.add_argument("--beam-width", type=int, default=None)
    ap.add_argument("--depth", type=int, default=None)
    ap.add_argument("--epsilon", type=float, default=None)
    ap.add_argument("--out", type=Path, default=None, help="write the report as JSON")
    args = ap.parse_args(argv)

    from train.blunder.store import DEFAULT_ROOT, load_corrections
    from train.leaf_lab import _cgpy_pilot_builder, _git_rev

    corrs = load_corrections(args.store or DEFAULT_ROOT)
    if args.agent:
        corrs = [c for c in corrs if c.agent == args.agent]
    builder = _cgpy_pilot_builder()

    if args.epsilon_sweep:
        sweep = epsilon_sweep(builder, corrs, [0.0, 0.001, 0.005, 0.01, 0.05, 0.1])
        print("\n=== epsilon sweep — the band is MEASURED against the corpus, never guessed ===")
        for band in sweep:
            print(f"  epsilon {band['epsilon']:<6} earned top-k {band['in_beam']:>4}/{band['ran']:<4}"
                  f"   admitted by the BAND ALONE {band['band_only']:>4}"
                  f"   agree(ruled) {band['agree_ruled']:>4}"
                  f"   agree(chosen) {band['agree_chosen']:>4}")
        if args.out:
            from train.gates import write_json_artifact
            write_json_artifact(args.out, {"git_rev": _git_rev(), "epsilon_sweep": sweep})
            print(f"-> {args.out}")
        return 0

    rpt = composer_lab_report(builder, corrs, k=args.beam_width, epsilon=args.epsilon,
                              depth=args.depth)
    _print_report(rpt, frame=args.frame, index=ideal_index(), verbatim=ideal_sequences())
    if args.acceptance:
        _print_acceptance(rpt)
    if args.out:
        from train.gates import write_json_artifact
        write_json_artifact(args.out, {"git_rev": _git_rev(), "agent": args.agent, **rpt})
        print(f"-> {args.out}")
    # 0 even with failures: this REPORTS, it does not gate. A metric nobody has ruled on must not
    # start failing `main` — the doctrine `gates.py` carries and `value_lab.py` restates.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
