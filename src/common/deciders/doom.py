"""`active_doomed` and the reads behind it: can the opponent KO my Active next turn.

WORST-CASE by design (ADR-0045). A relaxation is CONSULTED (`_doom_relax_consulted`), never assumed."""
from __future__ import annotations




class DoomMixin:
    """The survival read: can my Active be KO'd next turn."""

    def _doom_recur_fueled(self, oa: dict | None, opp: dict | None) -> bool:
        """Their Active LINE refuels from their discard (`discard_energy_recur`) AND that discard holds
        Basic Energy — fuel the charged budget cannot see, so the matched relax stands down."""
        if not (oa and opp and self.functions):
            return False
        ids = {oa.get("id")} | set(self.combat.forward_card_ids(oa.get("id")))
        if not any("discard_energy_recur" in self.functions.tags(i) for i in ids if i is not None):
            return False
        return bool(self._discard_energy_counts(opp.get("discard") or [])[1])

    def _recur_fueled_oa(self, oa: dict | None, opp: dict | None) -> dict | None:
        """Augments `oa`'s energies with its discard-recur reload for the CHARGED relax (ADR-0076 S2).
        Same discard source as `_doom_recur_fueled`: were they to disagree, the relax would fire blind."""
        if not (oa and opp and self.stats):
            return oa
        disc = self._discard_energy_counts(opp.get("discard") or [])[1]
        if not disc:
            return oa
        # DELIBERATE CombatMath bypass (POC-T1's documented list): the one-fact-source rule above.
        fuel = self.combat.discard_recur_fuel(oa, disc, forward_ids=self._forward_card_ids)
        if fuel <= 0:
            return oa
        st = self.stats.get(oa.get("id"))
        etype = getattr(st, "energyType", None)
        return dict(oa, energies=list(oa.get("energies") or []) + [etype] * fuel)

    def _doom_relax_inputs(self, oa: dict | None, opp: dict | None) -> tuple:
        """``(matched, fueled, read_oa)`` for the matched-Read doom relax. ``read_oa`` carries the fuel
        reload only when `recur_fuel_relax` is armed AND fuel is possible."""
        matched = getattr(self, "_incoming_budget", None) is not None
        fueled = self._doom_recur_fueled(oa, opp)
        read_oa = self._recur_fueled_oa(oa, opp) if (fueled and self.recur_fuel_relax) else oa
        return matched, fueled, read_oa

    def _active_doomed(self, ma: dict | None, oa: dict | None, opp: dict | None = None) -> bool:
        """The opponent can KO my Active next turn. Two γ-gated policies (ADR-0064 §4): a matched Read
        consults the CHARGED curve, which may only CLEAR a doom, never cry one. Never relax on a guess."""
        ctx = self._opp_attack_context
        my_hp = (ma or {}).get("hp", 0) or 0
        model = self._state_model
        if model is None or not my_hp:
            return False                    # no snapshot / no live Active: no claim
        # BOTH legs are the SAME curve at DIFFERENT policies, which is what makes a disagreement a
        # statement about POLICY rather than about two pieces of code.
        worst = model.theirs.doomed(ma, bodies=[oa], context=ctx)
        if not (worst and self.doom_matched_relax):
            return worst
        matched, fueled, read_oa = self._doom_relax_inputs(oa, opp)
        if not self._doom_relax_consulted(worst, matched, fueled):
            return worst
        return model.theirs.doomed(ma, bodies=[read_oa], charged=self._DOOM_CHARGED, context=ctx)

    def _doom_relax_consulted(self, worst: bool, matched: bool, fueled: bool) -> bool:
        """Does the CHARGED relax DECIDE this frame? RELAX-ONLY, so `worst` is a precondition. Named
        rather than inlined because `test_doom_matched_relax.py` asserts on it and must not re-derive."""
        return bool(worst and self.doom_matched_relax and matched
                    and (not fueled or self.recur_fuel_relax))

    def _active_best_attack_locked(self, ma: dict | None) -> bool:
        """My Active's HIGHEST-damage attack is transient-locked this turn (ADR-0033 tracker). SERIAL-
        gated, so the grant expires with a swap — a fresh benched copy restores the attack."""
        grant = self._transients.grant_for_serial((ma or {}).get("serial"))
        if not grant:
            return False
        if grant.get("self_lock"):
            return True
        same = grant.get("same_lock")
        if same is None:
            return False
        stat = self.stats.get((ma or {}).get("id")) if self.stats else None
        aids = getattr(stat, "attacks", None) or ()
        if not aids:
            return False
        best = max(aids, key=self._attack_damage)
        return same == best

    def _opp_turns_to_ready(self, p: dict | None) -> int | None:
        """Turns until ONE opponent body is ready, from VISIBLE facts only — the deny-slot deadline, at
        the slow 1-attach/turn policy. None on any gap, so the caller emits no slot (fail-closed)."""
        model = self._state_model
        if model is None:
            return None
        return model.theirs.turns_to_afford(p)
