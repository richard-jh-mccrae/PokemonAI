"""Transient attack effects — the match-scoped tracker (ADR-0033).

138 attacks grant "during your (opponent's) next turn" effects (Frost Barrier's −30, prevent-all
walls, self-locks, next-turn bonuses, retreat-locks). The observation exposes NO per-Pokémon effect
state, so the ONLY route is inference from the log stream (deck-tracker precedent, `OwnCardModel`):
an `ATTACK` log whose attack carries transient fields grants an effect for that side, bound to the
attacking serial; the grant expires when the granter's NEXT turn starts (exactly the "during your
opponent's next turn" window). Serial-binding gives leave-the-Active expiry for free: a retreated /
evolved / KO'd body presents a different serial (or none), so a stale grant simply never matches.

Sound by construction: grants are deterministic facts read from the same logs the engine emitted —
never probabilistic. Coin-gated transients are NOT tracked (the flip isn't in the fields we parse);
under-crediting a defender's possible shield is the safe direction for my attack math.

Per-viewer log replay (each obs replays everything since that seat's last select — the audit's
finding) is handled by idempotency: re-observing the same ATTACK re-sets the identical grant, and
expiry keys on TURN_START markers inside the same ordered stream.
"""
from __future__ import annotations

_TURN_START = 2
_ATTACK = 15


class TransientTracker:
    """Match-scoped store of live transient grants, one per side (a side attacks once per turn).

    Args:
        attack_stat: callable ``attackId -> AttackStat | None`` (the Pilot's ``_attack_stat``).
    """

    def __init__(self, attack_stat) -> None:
        self._attack_stat = attack_stat
        self._by_side: dict[int, dict] = {}     # side -> live grant (see _grant_fields)
        self._last_turn = 0

    def observe(self, obs: dict) -> None:
        """Consume one observation's logs; never raises (a malformed obs is ignored)."""
        try:
            turn = ((obs or {}).get("current") or {}).get("turn") or 0
            if turn and turn < self._last_turn:             # NEW match: state must not leak
                self._by_side.clear()
            if turn:
                self._last_turn = turn
            for lg in (obs or {}).get("logs") or []:
                t = (lg or {}).get("type")
                side = lg.get("playerIndex")
                if t == _TURN_START and side is not None:
                    self._by_side.pop(side, None)           # granter's next turn: grant expires
                elif t == _ATTACK and side is not None:
                    grant = self._grant_fields(lg.get("attackId"), lg.get("serial"))
                    if grant:
                        self._by_side[side] = grant
        except Exception:
            return

    def _grant_fields(self, attack_id, serial) -> dict | None:
        """The transient grant an attack creates, or None when it grants nothing."""
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
        if getattr(st, "nextTurnDefenderRetreatLock", False):
            grant["retreat_lock"] = True
        if not grant:
            return None
        grant["serial"] = serial
        return grant

    def grant_for_serial(self, serial) -> dict | None:
        """The live grant bound to this body (any side), or None. Serial-gated: a body that left
        the Active (retreat / evolve / KO) presents a different serial and never matches."""
        if serial is None:
            return None
        for grant in self._by_side.values():
            if grant.get("serial") == serial:
                return grant
        return None
