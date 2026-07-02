"""BASELINE cluster: RETREAT — the open-menu Retreat decision (ADR-0025). Hold position while setting
up; retreat a spent body into a ready benched win-condition. Pure data, no Mixin.
"""
from common.strategy.context import _MAIN, _RETREAT
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="hold-position-in-setup",
        rationale="During setup, don't retreat the Active — it's still your starter/accelerator and "
                  "a setup retreat wastes the whole turn. Discourages Retreat at the open turn menu "
                  "while Plan is SETUP.",
        when=lambda c: c.plan == Plan.SETUP and c.select_context == _MAIN
        and c.option_type == _RETREAT,
        weight=-25, status="testing"),
    Hypothesis(
        id="retreat-to-ready-attacker",
        rationale="When Active isn't the win-condition and a benched wincon is already powered to "
                  "attack, retreat into it. Weighted to beat a weak chip from the spent Active but "
                  "never a real attack or KO (a lethal always wins on tactical).",
        when=lambda c: c.select_context == _MAIN and c.option_type == _RETREAT
        and c.board.bench_wincon_ready and not c.board.active_is_wincon,
        weight=60, status="testing"),
]
