"""**The resolution-parity lane** — the recorded native engine as the answer key for a CHOICE node
(POC-T4/5, Issue #392; ADR-TEMP-392 decision 7).

`tools/train/apply_parity.py` diffs the seam's board against the **next** recorded frame, which is
the right reference for a point transition: one option, one engine step, one frame. A Deferred-Target
Option is not that shape. The engine answers a `_RETREAT` by setting ``current.retreated`` and then
posing the rest as separate selects — `_DISCARD_ENERGY` (context 30) for the cost, `_SWITCH` (context
3) for the promotion — so the board `common.board_choice` predicts is one the engine reaches only
after two or three FURTHER frames, outside the existing lane's reach entirely.

That is exactly the gap an unverified synthesis would live in. `board_choice` writes a board no
committed test compares against reality and then feeds it to `state_value`, which is the failure mode
Issue #382's lane exists to prevent one layer down. So this module walks each Deferred-Target Option
**past its follow-up selects to the first settled frame**, reads the target the trace records as
taken, and diffs the synthesized board against the recorded one on every homed zone.

## What is and is not verifiable, stated rather than implied

**Only the TAKEN branch.** The counterfactuals — the boards the other candidates would have reached —
are unobserved by construction: the engine played one line and recorded one. This lane therefore
cannot prove the enumeration is *complete*, and it does not claim to.

**What it can prove, and does, is stronger than it first looks.** Two independent things are checked
per step:

1. **The taken target is IN the enumerated space.** A systematic enumeration error — an off-by-one in
   the Bench indices, a discard set the product never forms, a body class the resolver excludes —
   makes the taken instance unfindable, and it cannot survive 2254 taken branches.
2. **The synthesized board for that instance equals the recorded one**, on every `HOMED` zone in
   `snapshot_coverage.WRITABLE`, by the same projection `apply_parity` uses. So a wrong Bench
   placement, a mis-derived ``energies`` list, a forgotten discard write, an uncleared Special
   Condition or a missed allowance is a CI failure rather than a runtime surprise.

**This is also what makes ADR-TEMP-392 decision 6 checkable rather than asserted.** That decision has
the follow-up select REPLAN through the same ranker and leaf rather than committing to the MAIN-site
pick; its soundness rests on the two sites seeing the same board. One evaluator over two boards this
lane proves equal cannot disagree, so a MAIN-site/select-site divergence becomes a CI condition.

**Synthetic fixtures alone were rejected.** A hand-built expectation encodes the author's model of the
engine, which is the same model the expander encodes — so it would agree with itself and prove
nothing. `tests/strategy/test_board_choice.py` carries the synthetic half for the paths no trace
exercises (truncation, refusals); this lane carries the arithmetic.

## How the taken target is read, and why NOT off the select options

The obvious route is to read the ctx-30 and ctx-3 answers and reconstruct the instance from them. It
is the brittle one: the `_DISCARD_ENERGY` selects are SEQUENTIAL, so each answer's index is into a
list the previous answer already shortened, and a lane that got that shift wrong would be testing its
own index arithmetic.

So the taken instance is read off the **settled observation itself**, by ``serial`` — the promoted
body is whichever body is Active there, and the discarded cards are the multiset difference of the
retreating body's ``energyCards`` before and after. That IS the trace's record of what was taken, and
it is exact.

⚠️ **This is not circular, and the reason matters.** Deriving *which* candidate was taken from the
after-frame decides one thing only: which member of the enumerated space to score. The synthesis then
runs independently and is compared on **every homed zone** — Bench placement, the re-derived
``energies``, the discard contents, the retreat allowance, the Special-Condition flags, both sides'
prize counts and deck facts. Every one of those is a way the synthesis can be wrong while the taken
instance is read correctly, and the injected-defect controls in
`tests/train/test_choice_parity.py` are what prove the diff bites.

## Population, and the full sweep's result

The **2254** `_RETREAT` steps `apply_parity`'s own sweep exercises over the committed corpus
(`tests/fixtures/parity/*.trace.json.gz`). The census's 63 `_PLAY` steps are NOT in scope: their
clause application does not exist at any layer (`board_choice`'s header records that gap as unowned),
so `deferred_target` refuses them and there is no synthesized board to diff.

Measured at this commit — **377 traces / 37 983 frames / 2254 choice steps**::

    2200  verified   (10 of them on the relaxed discard ORDER above)
      14  refused    — the modelling backlog, grouped below
      40  unsettled  — no same-orientation MAIN frame follows; 17 traces simply end mid-resolution
                       and 23 pass the turn there (a retreat taken as the last action of a turn)
       0  NOT ENUMERATED
       0  DIVERGED

The 14 refusals split two ways, and **both are inherited rather than introduced**:

* **12 — an untagged Special Energy.** `board_delta.units_for_cards` cannot derive what Legacy /
  Mist / Neo Upper / Enriching / Grow Grass Energy provide (no `provides:N` Function Tag), so the
  surviving ``energies`` list cannot be re-derived. That is the shared primitive's own fail-closed
  refusal (ADR-0067), reached through this node rather than caused by it.
* **2 — an unmodelled free-retreat grant.** Ethan's Magcargo (356), *"If this Pokémon has no Energy
  attached, it has no Retreat Cost"* — a fourth grant shape nothing parses. `common.retreat_cost`'s
  header records it, including that `Pilot._effective_retreat_cost` has the same gap and over-charges
  the pivot by the full convex build delta.

A refusal is not a divergence. The node declaring itself blind is the contract's own always-expand
path, and the grouped reasons ARE the backlog — which is why `--backlog` prints them.

## Running it

    python tools/train/choice_parity.py                 # every committed trace
    python tools/train/choice_parity.py --limit 25      # a subset, the shape CI runs
    python tools/train/choice_parity.py --kinds 12      # only `_RETREAT` steps

`tests/train/test_choice_parity.py` is the wrapper; `.github/workflows/ci.yml` gates it.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _root in (REPO / "src", REPO / "tools"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

# The sibling lane is IMPORTED, never re-spelled: `offline_combat`, the homed-zone projection, the
# trace loader and the chosen-option reader are each the one answer to a question both lanes ask, and
# a second copy would let the two report different numbers for one corpus.
from train.apply_parity import (TRACES, chosen_option, load,               # noqa: E402
                                offline_combat, zone_facts)
from common import board_choice, board_delta                               # noqa: E402
from common.state_model import StateModel                                  # noqa: E402

#: The kinds this lane walks. `board_choice.CHOICE_KINDS` is the source, so a kind promoted there
#: without a lane entry cannot go silently unverified.
KINDS = frozenset(board_choice.CHOICE_KINDS)

#: Zones compared as a MULTISET rather than a sequence — **one zone, and the relaxation is measured
#: rather than assumed.**
#:
#: A retreat paying a Retreat Cost of 2 discards two Energy cards, and the engine appends them in the
#: order the ctx-30 selects were ANSWERED. That order is a property of the policy that recorded the
#: trace, not of the rules: `docs/rulebook.txt` L142 says only *"you must discard 1 Energy … for each
#: [C]"*, and nothing anywhere assigns an order to a simultaneous discard. A synthesis holding one
#: option cannot know it, and inferring it from this corpus would be fitting to the agent that played
#: it — every committed trace is our own self-play.
#:
#: **Measured over the full corpus: 10 of 2254 steps differ, all in this one zone, all with identical
#: multisets, every one a two-card discard whose pair is transposed** (`enrich_9002` f10 node
#: ``(13, 5)`` / engine ``(5, 13)`` is the smallest). The relaxation is therefore exactly as wide as
#: the artifact and no wider: a retreat that discarded the WRONG card still fails here, because the
#: multiset changes. :attr:`Report.order_only` counts every step that took it, so a growing number is
#: visible rather than swallowed.
_ORDER_INSENSITIVE = frozenset({"my_discard_contents"})


def _multiset(value):
    """``value`` flattened to a sorted multiset of leaf strings — the order-insensitive reading."""
    out = []
    for item in value or ():
        out.extend(item if isinstance(item, (list, tuple)) else [item])
    return sorted(str(v) for v in out)


@dataclass
class Divergence:
    """One step where the choice node produced a board and the settled frame disagreed about it."""
    trace: str
    frame: int
    settled: int
    kind: int
    zone: str
    node_value: object
    engine_value: object

    def __str__(self) -> str:
        return (f"{self.trace} f{self.frame}->f{self.settled} kind={self.kind} zone={self.zone}\n"
                f"    node:   {self.node_value!r}\n    engine: {self.engine_value!r}")


@dataclass
class Report:
    """What one sweep found. Counts first, because the shape of the answer is the finding."""
    traces: int = 0
    frames: int = 0
    #: Steps whose chosen option is a kind `board_choice` declares a CHOICE node — the population.
    choice_steps: int = 0
    #: …of which enumerated a space, found the taken instance in it, and matched on every homed zone.
    verified: int = 0
    #: …of which refused. Not a defect: the node declaring itself blind is the contract's own
    #: always-expand path, and the reasons ARE the modelling backlog.
    refused: int = 0
    #: …of which never reached a settled frame (the trace ends, or the turn passes mid-resolution).
    unsettled: int = 0
    #: …of which matched everywhere except a zone in :data:`_ORDER_INSENSITIVE`, on ORDER alone.
    #: Counted, never silent: this is the one comparison the lane relaxes, and a reader must be able
    #: to see how often it is being leaned on.
    order_only: int = 0
    #: …of which enumerated a space the TAKEN instance is not in. **An enumeration defect**, counted
    #: apart from a zone divergence because the two are different bugs: this one says the space is
    #: wrong, the other says the arithmetic is.
    unenumerated: list = field(default_factory=list)
    divergences: list = field(default_factory=list)
    refusal_reasons: dict = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.divergences and not self.unenumerated

    def __str__(self) -> str:
        head = (f"{self.traces} traces / {self.frames} frames — {self.choice_steps} choice steps: "
                f"{self.verified} verified ({self.order_only} on a relaxed discard ORDER) · "
                f"{self.refused} refused · {self.unsettled} unsettled · "
                f"{len(self.unenumerated)} NOT ENUMERATED · {len(self.divergences)} DIVERGED")
        lines = [head]
        for miss in self.unenumerated[:10]:
            lines.append(f"  taken target not in the enumerated space: {miss}")
        for d in self.divergences[:20]:
            lines.append("  " + str(d))
        if len(self.divergences) > 20:
            lines.append(f"  … and {len(self.divergences) - 20} more")
        return "\n".join(lines)


def settled_frame(frames: list, start: int, seat: int):
    """The index of the first frame after ``start`` that is back at the MAIN menu for ``seat`` — the
    board the option's whole resolution settled to, follow-up selects and all.

    None when the trace ends first or the turn passes mid-resolution. Reported as ``unsettled`` rather
    than skipped silently, because a population that shrinks without saying so is a lane whose
    denominator nobody can size work against."""
    for j in range(start + 1, len(frames)):
        obs = frames[j].get("obs") or {}
        if ((obs.get("current") or {}).get("yourIndex")) != seat:
            return None                       # the turn passed — no same-orientation settled board
        if ((obs.get("select") or {}).get("context")) == board_delta.CONTEXT_MAIN:
            return j
    return None


def _serials(cards) -> list:
    return [(c or {}).get("serial") for c in (cards or ())]


def taken_retreat(before: dict, after: dict, seat: int):
    """The retreat candidate the trace records as TAKEN — ``(discarded card indices, promoted bench
    index)``, in :func:`common.board_choice.target_space`'s own coordinates, or None.

    Read by ``serial`` off the two observations, never reconstructed from the select answers — the
    module header carries the argument. None whenever the two frames do not describe a retreat this
    lane can key (no Active either side, the promoted body absent from the pre-state Bench), which is
    a fact to report rather than a shape to guess at."""
    def side(obs):
        players = ((obs.get("current") or {}).get("players")) or []
        return players[seat] if 0 <= seat < len(players) else None
    pre, post = side(before), side(after)
    if not pre or not post:
        return None
    a = next((b for b in (pre.get("active") or ()) if b), None)
    promoted = next((b for b in (post.get("active") or ()) if b), None)
    if not a or not promoted:
        return None
    bench = list(pre.get("bench") or ())
    index = next((i for i, b in enumerate(bench)
                  if b and b.get("serial") == promoted.get("serial")), None)
    if index is None:
        return None                           # the new Active did not come off the pre-state Bench
    # The retreating body, found on the settled Bench by its own serial, is what says which Energy
    # cards went: everything it no longer carries. Indices are into the PRE-state list, which is the
    # coordinate `target_space` enumerates in.
    landed = next((b for b in (post.get("bench") or ()) if b and b.get("serial") == a.get("serial")),
                  None)
    kept = set(_serials((landed or {}).get("energyCards")))
    discarded = tuple(i for i, c in enumerate(a.get("energyCards") or ())
                      if (c or {}).get("serial") not in kept)
    return (discarded, index)


#: How each kind's taken instance is read off the settled frame. Keyed like `board_choice`'s own
#: registries, so a kind gains a lane entry in the same shape it gains a target space.
TAKEN = {12: taken_retreat}          # `strategy.context._RETREAT`; imported via CHOICE_KINDS above


def replay(path: Path, *, combat, kinds=None, report: Report | None = None) -> Report:
    """Replay one trace's Deferred-Target Options through the choice node, into ``report``."""
    report = report or Report()
    body = load(path)
    frames = body.get("frames") or []
    decks = (body.get("meta") or {}).get("decks") or [[], []]
    report.traces += 1
    report.frames += len(frames)
    for k in range(len(frames) - 1):
        option = chosen_option(frames[k])
        if not option:
            continue
        kind = int(option.get("type", -1))
        if kind not in KINDS or (kinds and kind not in kinds):
            continue
        obs = frames[k]["obs"]
        seat = (obs.get("current") or {}).get("yourIndex", 0)
        if ((obs.get("select") or {}).get("context")) != board_delta.CONTEXT_MAIN:
            continue                          # not the MAIN menu — the node refuses it by contract
        report.choice_steps += 1
        j = settled_frame(frames, k, seat)
        if j is None:
            report.unsettled += 1
            continue
        deck = decks[seat] if seat < len(decks) else []
        pre = StateModel.build(obs, combat=combat, my_index=seat, deck=deck)
        candidate = TAKEN[kind](obs, frames[j]["obs"], seat)
        # ONE try around the whole synthesis, because every refusal it can raise is one
        # `board_choice.deferred_target` would raise for the same option — the space resolver's own
        # (an unreadable cost, an empty Bench) and the shared copy-on-write primitives' (an untagged
        # Special Energy whose provision `units_for_cards` cannot derive). Catching only the first
        # would report a modelling gap as a lane crash, which is the one outcome that tells a reader
        # nothing.
        try:
            space = board_choice.target_space(pre, option, seat_index=seat)
            if candidate is None:
                raise board_delta.Unmodellable(
                    "the settled frame does not describe a retreat this lane can key — no readable "
                    "Active either side, or the new Active did not come off the pre-state Bench")
            # Membership in the EQUIVALENCE the space enumerates, never on the raw coordinates: which
            # of eight identical Energy cards the engine named is not a decision, and the space
            # enumerates one representative per multiset (`board_choice.candidate_class`).
            taken_class = board_choice.candidate_class(pre, option, candidate, seat_index=seat)
            reachable = {board_choice.candidate_class(pre, option, c, seat_index=seat)
                         for c in space}
            # …and the ARITHMETIC on exactly what happened: the taken candidate realised verbatim, so
            # the surviving card order is the engine's own, not a canonical representative's.
            after_obs, _fingerprint = board_choice.realise(pre, option, candidate, seat_index=seat)
        except board_delta.Unmodellable as gap:
            report.refused += 1
            reason = str(gap).split(" — ")[0]
            report.refusal_reasons[reason] = report.refusal_reasons.get(reason, 0) + 1
            continue
        if taken_class not in reachable:
            report.unenumerated.append(
                f"{path.name} f{k}->f{j} kind={kind} taken={candidate!r} class={taken_class!r} "
                f"space={len(space)}")
            continue
        ours = zone_facts(pre.rebuilt(after_obs, reuse_their_side=True))
        theirs = zone_facts(StateModel.build(frames[j]["obs"], combat=combat, my_index=seat,
                                             deck=deck))
        bad, relaxed = [], False
        for zone, engine_value in theirs.items():
            if ours.get(zone) == engine_value:
                continue
            if zone in _ORDER_INSENSITIVE and _multiset(ours.get(zone)) == _multiset(engine_value):
                relaxed = True
                continue
            bad.append(zone)
        for zone in bad:
            report.divergences.append(Divergence(path.name, k, j, kind, zone,
                                                 ours.get(zone), theirs[zone]))
        if not bad:
            report.verified += 1
            report.order_only += int(relaxed)
    return report


def sweep(*, limit=None, kinds=None, combat=None, traces=None) -> Report:
    """Replay ``limit`` traces (all of them by default), in a stable order."""
    combat = combat or offline_combat()
    paths = list(traces) if traces is not None else sorted(TRACES.glob("*.trace.json.gz"))
    if limit:
        paths = paths[:limit]
    report = Report()
    for path in paths:
        replay(path, combat=combat, kinds=kinds, report=report)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=None, help="replay only the first N traces")
    ap.add_argument("--kinds", default=None,
                    help="comma-separated engine OptionType ints to restrict the sweep to")
    ap.add_argument("--backlog", action="store_true",
                    help="print the grouped refusal reasons (the modelling backlog)")
    args = ap.parse_args(argv)
    kinds = frozenset(int(k) for k in args.kinds.split(",")) if args.kinds else None
    report = sweep(limit=args.limit, kinds=kinds)
    print(report)
    if args.backlog:
        print("\nrefusal backlog (reason -> steps):")
        for reason, count in sorted(report.refusal_reasons.items(), key=lambda kv: -kv[1]):
            print(f"  {count:6d}  {reason}")
    return 0 if report.clean else 1


if __name__ == "__main__":                                  # pragma: no cover — CLI
    raise SystemExit(main())
