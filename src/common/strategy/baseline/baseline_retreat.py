"""BASELINE cluster: RETREAT — the open-menu Retreat decision (ADR-0025). Hold position while setting
up; retreat a spent body into a ready benched win-condition. Pure data, no Mixin.
"""
from common.strategy.context import _MAIN, _RETREAT
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="hold-position-in-setup",
        rationale="During setup, don't retreat the Active — you're still developing and want the "
                  "Active (your starter / energy accelerator) to attack; a setup retreat wastes "
                  "the whole turn. Discourages the Retreat option at the open turn menu while the "
                  "Plan is still SETUP.",
        when=lambda c: c.plan == Plan.SETUP and c.select_context == _MAIN
        and c.option_type == _RETREAT,
        weight=-25, status="testing"),
    Hypothesis(
        id="retreat-to-ready-attacker",
        rationale="When your Active is NOT your win-condition (e.g. a spent opener like Cinderace) "
                  "and a benched win-condition is already powered up enough to attack, retreat into "
                  "it — bring your real attacker to the front to finish the turn. Weighted to beat a "
                  "weak chip from the spent Active but never a real attack or a knockout (a lethal "
                  "always wins on tactical).",
        when=lambda c: c.select_context == _MAIN and c.option_type == _RETREAT
        and c.board.bench_wincon_ready and not c.board.active_is_wincon,
        weight=60, status="testing"),
]
