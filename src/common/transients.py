"""Transient attack effects — the match-scoped tracker (ADR-0033).

The observation exposes NO per-Pokémon effect state, so grants are inferred from the log stream and
bound to the attacking serial: a body that left the Active (retreat / evolve / KO) presents a
different serial and never matches. Coin-gated transients are NOT tracked.
"""
from __future__ import annotations

_TURN_START = 2
_ATTACK = 15


class TransientTracker:
    """One live grant per side; ``attack_stat`` is a callable ``attackId -> AttackStat | None``."""

    def __init__(self, attack_stat) -> None:
        self._attack_stat = attack_stat
        self._by_side: dict[int, dict] = {}
        self._last_turn = 0

    def observe(self, obs: dict) -> None:
        try:
            turn = ((obs or {}).get("current") or {}).get("turn") or 0
            if turn and turn < self._last_turn:             # a turn regression means a NEW match
                self._by_side.clear()
            if turn:
                self._last_turn = turn
            for lg in (obs or {}).get("logs") or []:
                t = (lg or {}).get("type")
                side = lg.get("playerIndex")
                if t == _TURN_START and side is not None:
                    self._by_side.pop(side, None)
                elif t == _ATTACK and side is not None:
                    grant = self._grant_fields(lg.get("attackId"), lg.get("serial"))
                    if grant:
                        self._by_side[side] = grant
        except Exception:
            return

    def _grant_fields(self, attack_id, serial) -> dict | None:
        st = self._attack_stat(attack_id) if attack_id is not None else None
        if st is None:
            return None
        grant: dict = {}
        if getattr(st, "nextTurnReduction", 0):
            grant["reduction"] = st.nextTurnReduction
        if getattr(st, "nextTurnPreventAll", False):
            grant["prevent_all"] = True
        if getattr(st, "nextTurnSelfLock", False):
            grant["self_lock"] = True
        if getattr(st, "nextTurnSameAttackLock", False):
            grant["same_lock"] = attack_id
        if getattr(st, "nextTurnSelfBonus", 0):
            grant["self_bonus"] = st.nextTurnSelfBonus
        if not grant:
            return None
        grant["serial"] = serial
        return grant

    def grant_for_serial(self, serial) -> dict | None:
        if serial is None:
            return None
        for grant in self._by_side.values():
            if grant.get("serial") == serial:
                return grant
        return None


_PLAY = 10


class TurnBoostTracker:
    """Flat damage-boosts live THIS turn, per side; ``card_stat`` is ``cardId -> CardStat | None``.
    Tool boosts (Maximum Belt) are NOT tracked here — an attached Tool is visible board state."""

    def __init__(self, card_stat) -> None:
        self._card_stat = card_stat
        self._by_side: dict[int, list] = {}     # side -> [(amount, attackerType|None, vsEx), …]
        self._last_turn = 0

    def observe(self, obs: dict) -> None:
        try:
            turn = ((obs or {}).get("current") or {}).get("turn") or 0
            if turn and turn < self._last_turn:             # a turn regression means a NEW match
                self._by_side.clear()
            if turn:
                self._last_turn = turn
            for lg in (obs or {}).get("logs") or []:
                t = (lg or {}).get("type")
                side = lg.get("playerIndex")
                if t == _TURN_START:
                    self._by_side.clear()
                elif t == _PLAY and side is not None:
                    st = self._card_stat(lg.get("cardId"))
                    if (st is not None and getattr(st, "damageBoost", 0)
                            and not st.is_pokemon and not st.is_tool):
                        self._by_side.setdefault(side, []).append(
                            (st.damageBoost, st.damageBoostType, st.damageBoostVsEx))
        except Exception:
            return

    def boosts_for(self, side) -> tuple:
        """The live ``(amount, attackerType|None, vsExOnly)`` boosts for this side's attacks."""
        if side is None:
            return ()
        return tuple(self._by_side.get(side, ()))
