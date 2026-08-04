"""**The apply-seam parity lane** — the recorded native engine as the answer key (POC-T4/1,
Issue #382; ADR-0098's decision 4, Issue #263 § *Parity + retirement*).

`common.apply_option` predicts the board after one option, arithmetically, without stepping an
engine. This module is what makes that claim checkable rather than argued: it replays the committed
native traces (`tests/fixtures/parity/*.trace.json.gz`, schema `parity-trace/1`, 377 files) ONE STEP
AT A TIME through the seam and diffs the model the seam produced against the model built from the
**next recorded frame**.

## Three properties, each load-bearing

**The reference is the recorded NATIVE trace, never cgpy.** Checking a hand-written model against a
reimplementation that is itself only partly at parity would be checking a model against a model
(`apply_option`'s own header). The trace IS the native side, which is also what keeps this lane
DLL-free and therefore runnable on both platforms.

**A divergence is a ruled seam BUG, never an accepted approximation.** The remedy is
`apply_option.QUARANTINED_KINDS`: a kind with an open divergence refuses, so the planner degrades to
always-expand *visibly* and the telemetry names the kind — rather than the seam quietly mis-playing
it. The lane reports; a human rules; the registry records the ruling.

**A REFUSAL is not a divergence.** The seam declaring itself blind is the honest answer and the
contract's own always-expand path; only a seam that produced a BOARD and got it wrong is a defect.
The two are counted separately and the refusal reasons are grouped, because that grouping IS the
modelling backlog for POC-T4/2 and beyond.

## What is compared: the facts the value layer reads

Not the raw observation — the seam is allowed to differ from the engine on anything no equation
reads (a serial ordering inside a zone, a log line). What it may not differ on is the SNAPSHOT, so
the projection is taken from `common.snapshot_coverage`'s own registry: every `HOMED` zone's declared
``home`` path, resolved against the real `StateModel` classes. That registry is the committed answer
to *"what state can a card effect write, and where does the snapshot hold it?"*, so a zone this lane
compares is a zone somebody declared, and a zone nobody declared cannot be silently skipped here —
it is missing from the registry, which its own audit test is what catches.

## Running it

    python tools/train/apply_parity.py                 # every committed trace
    python tools/train/apply_parity.py --limit 25      # a subset, the shape CI runs
    python tools/train/apply_parity.py --kinds 8,9     # only ATTACH and EVOLVE steps

`tests/parity/test_apply_seam_parity.py` is the budget-tagged wrapper; it runs a subset per test
session and takes the full sweep on demand.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from common import apply_option as seam                                    # noqa: E402
from common import snapshot_coverage as sc                                 # noqa: E402
from common.cards import CardFunctions                                     # noqa: E402
from common.effects import CardEffects                                     # noqa: E402
from common.scouting.provider import (DictCardStatProvider, _build_cache,  # noqa: E402
                                      build_attack_stats, load_attack_overrides)
from common.state_model import StateModel                                  # noqa: E402
from common.strategy.combat import CombatMath                              # noqa: E402

TRACES = REPO / "tests" / "fixtures" / "parity"


def offline_combat() -> CombatMath:
    """A `CombatMath` over cgpy's committed card/attack tables — **no DLL**.

    `EngineCardStatProvider` reads `cg.api.all_card_data()`, which maps the native library; cgpy
    ships the same tables as JSON (`src/cgpy/defs/`, minted from the DLL by
    `tools/parity/snapshot_tables.py`) precisely so the parity lane can be platform-free. The
    transform is the SHIPPED one (`provider._build_cache` / `build_attack_stats` with the audit
    overrides), not a second reading of the tables — a lane that parsed card facts its own way would
    be testing its own parser.
    """
    from cgpy.compat import api as cgapi
    attacks = cgapi.all_attack()
    stats = _build_cache(cgapi.all_card_data(), attacks)
    provider = DictCardStatProvider(stats,
                                    attacks=build_attack_stats(attacks, load_attack_overrides()))
    return CombatMath(provider, functions=CardFunctions.load(), transients=None,
                      effects=CardEffects.load())


# ── the comparison projection ─────────────────────────────────────────────────────────────────────


def _project(value):
    """A comparable projection of whatever a snapshot ``home`` path resolves to.

    `BodyView`s and tuples of them are the case that needs a rule: they are objects, so ``==`` is
    identity and every comparison would "diverge". Projected to the facts a value equation actually
    asks a body — who it is, how hurt it is, what it is carrying — which is the same standard the
    module docstring sets for the zones themselves."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (frozenset, set)):
        return tuple(sorted(str(v) for v in value))
    if isinstance(value, dict):
        return tuple(sorted((str(k), _project(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_project(v) for v in value)
    if hasattr(value, "card_id"):                        # a BodyView
        return (value.card_id, value.hp_remaining, value.damage_counters,
                value.energy_key, value.tool_ids, value.prize_value)
    return repr(value)


def _resolve(model, path: str):
    """Walk a dotted ``home`` path off ``model``, descending into a tuple of bodies elementwise.

    ``mine.bench.prize_value`` is a per-BODY read over a container, exactly as the registry writes
    it; ``mine.active.tool_ids`` is a per-body read over a possibly-absent one. Both are handled
    here so the registry's own spelling is what this lane consumes."""
    node = model
    for part in path.split("."):
        if node is None:
            return None
        if isinstance(node, tuple):
            node = tuple(getattr(b, part, None) for b in node)
            continue
        node = getattr(node, part, None)
    return node


def zone_facts(model) -> dict:
    """``{zone id: projection}`` over every `HOMED` zone in `snapshot_coverage.WRITABLE`.

    The registry is the source of what to compare, so this lane cannot quietly stop checking a zone:
    dropping one means dropping it from `WRITABLE`, and `test_snapshot_coverage` is what refuses
    that."""
    out = {}
    for zone_id, paths in sc.homes().items():
        out[zone_id] = tuple(_project(_resolve(model, p)) for p in paths)
    return out


# ── the lane ──────────────────────────────────────────────────────────────────────────────────────


@dataclass
class Divergence:
    """One frame where the seam produced a board and the engine disagreed about it."""
    trace: str
    frame: int
    kind: int
    card_id: int | None
    zone: str
    seam_value: object
    engine_value: object

    def __str__(self) -> str:
        return (f"{self.trace} f{self.frame} kind={self.kind} card={self.card_id} "
                f"zone={self.zone}\n    seam:   {self.seam_value!r}\n    engine: {self.engine_value!r}")


@dataclass
class Report:
    """What one sweep found. Counts first, because the shape of the answer is the finding."""
    traces: int = 0
    frames: int = 0
    #: Steps whose chosen option is a kind this seam declares MODELLED — the lane's whole population.
    modelled_steps: int = 0
    #: …of which produced a board and matched the next recorded frame on every homed zone.
    verified: int = 0
    #: …of which refused. Not a defect: the seam declaring itself blind is the contract's own
    #: always-expand path, and the reasons ARE the modelling backlog.
    refused: int = 0
    #: …of which could not be compared (the next frame is the opponent's perspective, so there is no
    #: same-orientation model to diff against). Reported rather than silently dropped.
    incomparable: int = 0
    divergences: list = field(default_factory=list)
    refusal_reasons: dict = field(default_factory=dict)
    by_kind: dict = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.divergences

    def diverging_kinds(self) -> frozenset:
        return frozenset(d.kind for d in self.divergences)

    def __str__(self) -> str:
        head = (f"{self.traces} traces / {self.frames} frames — {self.modelled_steps} modelled steps: "
                f"{self.verified} verified · {self.refused} refused · "
                f"{self.incomparable} incomparable · {len(self.divergences)} DIVERGED")
        lines = [head, "  per kind: " + ", ".join(
            f"{k}: {v['verified']}v/{v['refused']}r/{v['diverged']}d"
            for k, v in sorted(self.by_kind.items()))]
        for d in self.divergences[:20]:
            lines.append("  " + str(d))
        if len(self.divergences) > 20:
            lines.append(f"  … and {len(self.divergences) - 20} more")
        return "\n".join(lines)


def _load(path: Path) -> dict:
    with gzip.open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def _chosen_option(frame: dict):
    """The single option a frame's recorded ``choice`` answers, or None.

    Multi-pick answers (``maxCount > 1`` grabs) are skipped rather than approximated: the seam models
    ONE option, and folding a two-card grab into one transition would be measuring something else."""
    choice = frame.get("choice")
    menu = ((frame.get("obs") or {}).get("select") or {}).get("option") or ()
    if not choice or len(choice) != 1:
        return None
    index = choice[0]
    return menu[index] if isinstance(index, int) and 0 <= index < len(menu) else None


def _card_of(obs: dict, option: dict, seat: int):
    """The hand card an option names, for the report's backlog grouping. None when it names none."""
    if "index" not in option or option.get("area") not in (None, 2):
        return None
    players = ((obs.get("current") or {}).get("players")) or []
    hand = (players[seat] or {}).get("hand") or () if 0 <= seat < len(players) else ()
    index = option.get("index")
    return hand[index].get("id") if isinstance(index, int) and 0 <= index < len(hand) else None


def replay(path: Path, *, combat, kinds=None, report: Report | None = None) -> Report:
    """Replay one trace through the seam, accumulating into ``report``."""
    report = report or Report()
    body = _load(path)
    frames = body.get("frames") or []
    report.traces += 1
    report.frames += len(frames)
    effects = combat.effects
    for k in range(len(frames) - 1):
        option = _chosen_option(frames[k])
        if not option:
            continue
        kind = int(option.get("type", -1))
        if kind not in seam.TRANSITION_KINDS or (kinds and kind not in kinds):
            continue
        obs, next_obs = frames[k]["obs"], frames[k + 1]["obs"]
        seat = (obs.get("current") or {}).get("yourIndex", 0)
        report.modelled_steps += 1
        tally = report.by_kind.setdefault(kind, {"verified": 0, "refused": 0, "diverged": 0,
                                                 "incomparable": 0})
        if (next_obs.get("current") or {}).get("yourIndex") != seat:
            report.incomparable += 1
            tally["incomparable"] += 1
            continue
        card_id = _card_of(obs, option, seat)
        pre = StateModel.build(obs, combat=combat, my_index=seat)
        result = seam.apply_option(
            pre, option, clauses_cover=(effects.clauses_cover(card_id) if card_id else None))
        if seam.must_expand(result):
            report.refused += 1
            tally["refused"] += 1
            reason = result.reason.split(" — ")[0]
            report.refusal_reasons[reason] = report.refusal_reasons.get(reason, 0) + 1
            continue
        after = seam.require_model(result)
        engine = StateModel.build(next_obs, combat=combat, my_index=seat)
        ours, theirs = zone_facts(after), zone_facts(engine)
        bad = [z for z in theirs if ours.get(z) != theirs[z]]
        if bad:
            tally["diverged"] += 1
            for zone in bad:
                report.divergences.append(Divergence(path.name, k, kind, card_id, zone,
                                                     ours.get(zone), theirs[zone]))
        else:
            report.verified += 1
            tally["verified"] += 1
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
