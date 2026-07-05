"""BASELINE cluster: RETREAT — the open-menu Retreat decision (ADR-0025). Hold position while setting
up; retreat a spent body into a ready benched win-condition; swap out a cooldown-locked attacker.
Pure data, no Mixin.
"""
from common.strategy.context import _MAIN, _PLAY, _RETREAT
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="hold-position-in-setup",
        rationale="During setup, don't retreat the Active — it's still your starter/accelerator and "
                  "a setup retreat wastes the whole turn. Discourages Retreat at the open turn menu "
                  "while Plan is SETUP.",
        when=lambda c: not c.board.line_ready and c.select_context == _MAIN
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
    Hypothesis(
        id="swap-out-the-locked-attacker",
        rationale="When your Active's BIG attack is transient-locked this turn — it used a \"can't use "
                  "<this attack> during your next turn\" nuke last turn (Mega Brave class, ADR-0033) — "
                  "and a benched win-condition is already powered (`bench_wincon_ready`), swap: Retreat "
                  "or play a `switch` Item so the FRESH copy attacks at full strength while the locked "
                  "one cools down on the Bench (the lock is serial-bound, so leaving the Active clears "
                  "it). The dual-Mega cadence: two powered Megas + a swap = the nuke EVERY turn instead "
                  "of every other. `retreat-to-ready-attacker` can't cover this (it stands down when the "
                  "Active IS the wincon); the new-Active pick is `promote-the-ready-wincon` at the SWITCH "
                  "select. Fires on both the Retreat option and a `switch`-tagged PLAY (Switch Item — "
                  "free, keeps the attached Energy and the Tool slot); if the Active's affordable "
                  "lock-free attack still KOs, that KO wins on tactical regardless.",
        when=lambda c: c.select_context == _MAIN
        and (c.option_type == _RETREAT or (c.option_type == _PLAY and "switch" in c.tags))
        and c.board.active_best_attack_locked and c.board.bench_wincon_ready,
        weight=35, status="assumed"),
]
