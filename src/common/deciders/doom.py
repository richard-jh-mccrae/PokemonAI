"""`active_doomed` and the reads behind it: can the opponent KO my Active next turn.

WORST-CASE by design (ADR-0045). A relaxation is CONSULTED and recorded (`_doom_relax_consulted`), never assumed — a
doom read that quietly softens is the one that gets an attacker killed."""
from __future__ import annotations




class DoomMixin:
    """The survival read: can my Active be KO'd next turn."""

    def _doom_recur_fueled(self, oa: dict | None, opp: dict | None) -> bool:
        """The opponent's Active LINE (current + forward forms) refuels from their discard
        (`discard_energy_recur` — Assemble Alloy re-attaches Basic {M} on evolving) AND that discard
        visibly holds Basic Energy — fuel the charged attach budget cannot see, so the matched relax
        must stand down to worst-case (the S2 recur read models the fuel; the doom swap only refuses
        to relax across it). False when tags/discard are unknown (no extra pessimism on no evidence)."""
        if not (oa and opp and self.functions):
            return False
        ids = {oa.get("id")} | set(self.combat.forward_card_ids(oa.get("id")))
        if not any("discard_energy_recur" in self.functions.tags(i) for i in ids if i is not None):
            return False
        return bool(self._discard_energy_counts(opp.get("discard") or [])[1])

    def _recur_fueled_oa(self, oa: dict | None, opp: dict | None) -> dict | None:
        """ADR-0076 S2 live (survival-only): augments `oa`'s energies with its discard-recur reload
        for the CHARGED relax read — the same current-form-energyType proxy the S2 recur diagnostic
        (the S2 recur diagnostic, deleted by Issue #261 item 2h) already used; precise per-form
        reload TARGETING (Aura Jab feeds the
        BENCH, not itself; Archaludon any {M}) stays a further refinement, not required to make the
        relax gate fuel-aware. Returns `oa` unchanged when there's no fuel, no tag, or the discard/
        stats are unknown — fail-open to the unaugmented read.

        Reads the opponent discard through `_discard_energy_counts(opp)` — the SAME source
        `_doom_recur_fueled` gates on, deliberately (the `_build_standing` / `_affords` lesson: one
        function owns the fact, so two readings cannot drift). An earlier cut read it off
        `_state_model.theirs` instead, which left a live hazard: had the two sources ever
        disagreed, `fueled` could report True while this returned `oa` unaugmented, and the relax
        would then fire on a read that never counted the fuel it stood down for."""
        if not (oa and opp and self.stats):
            return oa
        disc = self._discard_energy_counts(opp.get("discard") or [])[1]
        if not disc:
            return oa
        # DELIBERATE CombatMath bypass (POC-T1's documented list): the ONE-FACT-SOURCE rule stated in
        # this method's own docstring — the relax's `fueled` gate and this augmentation must read the
        # SAME discard, and `_doom_recur_fueled` reads it through `_discard_energy_counts(opp)`.
        fuel = self.combat.discard_recur_fuel(oa, disc, forward_ids=self._forward_card_ids)
        if fuel <= 0:
            return oa
        st = self.stats.get(oa.get("id"))
        etype = getattr(st, "energyType", None)
        return dict(oa, energies=list(oa.get("energies") or []) + [etype] * fuel)

    def _doom_relax_inputs(self, oa: dict | None, opp: dict | None) -> tuple:
        """Shared inputs for the matched-Read doom relax, read by both the live decider
        (`_active_doomed`) and, until Issue #261 item 2h deleted it, its diagnostic, so they could
        not drift: whether a
        γ-matched Brief exists (`matched`), whether the opponent's Active is a POSSIBLE
        discard-recur refueler (`fueled`, `_doom_recur_fueled`'s existing gate), and the oa dict the
        CHARGED read should actually consume (`read_oa`) — augmented with its real fuel reload only
        when `recur_fuel_relax` is armed AND fuel is possible; unaugmented otherwise (today's
        behavior, byte-identical when the kill-switch is OFF)."""
        matched = getattr(self, "_incoming_budget", None) is not None
        fueled = self._doom_recur_fueled(oa, opp)
        read_oa = self._recur_fueled_oa(oa, opp) if (fueled and self.recur_fuel_relax) else oa
        return matched, fueled, read_oa

    def _active_doomed(self, ma: dict | None, oa: dict | None, opp: dict | None = None) -> bool:
        """The opponent can KO my Active next turn (current OR forward-evolved attack).

        Two policies, γ-gated (the doom-shadow grill ruling, 2026-07-23 — the ADR-0064 §4 asymmetry,
        mirroring `_incoming_budget`):

        - **Matched Read** (`doom_matched_relax` ON + `_incoming_budget` populated + no discard-recur
          fuel, OR fuel present but quantified via `recur_fuel_relax`, ADR-0076 S2): RELAX-ONLY
          conjunction — a doom the worst-case oracle cries stands only if the CHARGED Threat-Clock
          curve confirms it (`doomed_incoming` under `_DOOM_CHARGED`: per-attack typed affordability
          at manual + one supporter-accel attach, Ignition burst on Evolutions, PLUS the recur reload
          when `recur_fuel_relax` is armed). The charged read can CLEAR a worst-case doom, never
          manufacture one — its own extra reach (the +1 supporter wild can credit a forward form the
          incumbent's `attached + 1` forward gate does not, e.g. a 1-Energy Makuhita → Wild Press
          210) must not re-open the phantom play-scared class (ADR-0064 §3; the 82525101-14
          Ultra-Ball-discard pin). On the 15-frame disagreement corpus this relaxes exactly the
          ruled-B frames (bare Terapagos ex / 0-Energy Archaludon ex) while every ruled-C frame stays
          doomed (Hammer-lanche density 600, weakness-doubled Mind Bend 120, 1-Energy Metal Defender
          220).
        - **Unmatched / fueled-with-`recur_fuel_relax`-OFF / switch OFF**: the WORST-CASE oracle,
          byte-identical (`combat.active_doomed` — no affordability charge, the hidden-Ignition
          planner_6858 lesson; docs/todo/incoming-affordability.md). Never relax on a guess."""
        ctx = self._opp_attack_context
        my_hp = (ma or {}).get("hp", 0) or 0
        model = self._state_model
        if model is None or not my_hp:
            return False                    # no snapshot / no live Active: no claim
        # BOTH legs are the SAME curve at DIFFERENT policies (POC-T1, Issue #260) — that is the
        # whole content of the fold. `UNCHARGED` is the worst-case doom ceiling the incumbent
        # `active_doomed` spelled as its own implementation; `_DOOM_CHARGED` is the matched-Read
        # relax. Reading them off one method at two policies is what makes "these two disagree on
        # 15 frames" a statement about POLICY rather than about two pieces of code.
        worst = model.theirs.doomed(ma, bodies=[oa], context=ctx)
        if not (worst and self.doom_matched_relax):
            return worst
        matched, fueled, read_oa = self._doom_relax_inputs(oa, opp)
        if not self._doom_relax_consulted(worst, matched, fueled):
            return worst
        return model.theirs.doomed(ma, bodies=[read_oa], charged=self._DOOM_CHARGED, context=ctx)

    def _doom_relax_consulted(self, worst: bool, matched: bool, fueled: bool) -> bool:
        """Does the CHARGED relax read DECIDE this frame, or does the worst-case oracle keep it?

        RELAX-ONLY, so `worst` is a precondition: the charged curve may clear a doom the incumbent
        cries, never manufacture one (the 82525101-14 lesson). Behind that, the γ-gate must have held
        (`matched`) and discard-recur fuel must either be absent or quantified rather than blocking
        (`recur_fuel_relax`, ADR-0076 §2).

        A named predicate rather than an inline `and` chain because it has two readers and they must
        not drift: `_active_doomed` branches on it, and `test_doom_matched_relax.py` asserts on it.
        That test used to read the bit off `Decision.threat_shadow` — a diagnostic Issue #261 item 2h
        deleted — and re-deriving the conjunction in the test would have left the pin asserting
        against its own arithmetic rather than against the decider's."""
        return bool(worst and self.doom_matched_relax and matched
                    and (not fueled or self.recur_fuel_relax))

    def _active_best_attack_locked(self, ma: dict | None) -> bool:
        """True when my Active's HIGHEST-damage attack is transient-locked this turn — it used a
        "can't use <this attack> next turn" attack last turn (Mega Brave class; a blanket self-lock
        counts too). Read off the ADR-0033 tracker, serial-gated: a body that left the Active carries
        a new serial, so the grant expires with the swap — which is exactly why swapping in a fresh
        benched copy restores the attack (the rung is DELETED, ADR-0100 §11 — the swap is
        now emergent from destination value minus retreat cost)."""
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
        """The Round-3 ruled basic lookahead of ONE opponent in-play body, from VISIBLE facts only
        (thread 2, the deny-slot deadline): `needs.turns_to_ready` over

          * the ENERGY DEFICIT — the line's biggest-attack cost (max ``maxDamageCost`` over the
            body's current + forward forms, "fully energized" measured against the threat it
            becomes) minus its attached Energy, at the 1-manual-attach/turn quota (rules.md §3).
            Their card-effect accel is NOT modelled: that can only OVER-state t and UNDER-price
            the deny slot — the fail-closed direction (the hedge keeps the card at v1's price).
          * the FORWARD EVOLUTION HOPS still owed — the ``evolvesFrom`` name-chain depth from this
            body to its line's deepest still-owed form (one evolve per turn, rules.md §4), walked
            over the forward index (`_forward_card_ids`), depth-guarded. A broken/unknown chain
            contributes 0 hops (the deficit leg still grades).

        None — the caller emits NO deny slot (fail-closed, erring toward the shipped hedge) —
        when the body/its stats are unknown or no form's biggest-attack cost is known.

        DELEGATES to `model.theirs.turns_to_afford` (Threat-Clock unification S1c,
        docs/plans/opponent-value-equation-unification.md; re-pointed off the raw oracle onto the
        SNAPSHOT by POC-T1, Issue #260): the deny-clock's energy/evolve model lives on the KO oracle
        beside `incoming` — the Threat Clock's two legs, one home — and the snapshot supplies the
        forward index and the discard the read needs, so no caller assembles them by hand. The slow
        deny policy is the default 1-attach/turn.

        **Their DISCARD RECURSION is now modelled** (Issue #204, landed with this migration): the two
        `discard_energy_recur` lines reload outside the attach quota, so the bare quota under-states
        their clock rather than over-stating it. Their deck-search accel (Punk Up class) is still not
        on THIS leg — it enters the `charged` budget instead (Issue #257), which is the read that can
        express a Supporter quota; leaving it off here is the fail-closed direction for a deny slot.

        None — the caller emits NO deny slot — when there is no snapshot: a board that never went
        through `_board()` has no opponent side to read, and the fail-closed answer is the same one an
        unknown stat gives."""
        model = self._state_model
        if model is None:
            return None
        return model.theirs.turns_to_afford(p)
