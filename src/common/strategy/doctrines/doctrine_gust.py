"""DOCTRINE: Gust (Boss's Orders) — ADR-0022. One file, end to end.

A gust forces the opponent to switch a benched Pokémon into their Active Spot: TWO decisions over ONE
closed-form KO oracle (`_can_ko`, lifted to any bench defender) — whether to play it, and which body to
drag up. All KO / prize magnitude lives in `GustMixin` so the tuner never ingests a KO_SCORE seed.
"""
from __future__ import annotations

from common.currency import PRIZE_DAMAGE_RATE   # the ONE damage->prize crossing
from common.grading import halve                # ...and the ONE hop discount (ADR-0070 §6)
from common.needs import _SURVIVAL_CAP, line_prize_advance   # the sub-prize bound; the Denial leg
from common.strategy.context import (KO_SCORE, _BENCH, _CARD, _EVOLVING_THREAT_DMG, _PLAY,
                                      _SUPPORTER, _SWITCH)
from common.strategy.strategy import Hypothesis, Plan

_STALL_RETREAT = 1           # min retreat cost of a STRANDABLE energyless body
_STALL_EX_BONUS = 3          # keystone bump: stranding an energyless opponent EX beats a fungible
                             # pre-evo by more than a point of retreat cost; << KO_SCORE so a KO wins
_EVOLVING_GUST_DENIAL = 0.5  # OFF-BRANCH ONLY since ADR-0119 decision 5 — dead on the live path. It
                             # survives so `scaled_threat_rank=False` restores the printed read exactly.
_MATCHUP_GUST_SCALE = 0.004  # ADR-0051: scales a MatchupPlan role priority into the sub-prize tie-break band
# `_WINCON_DENIAL_PRIZES` (ADR-0051) DELETED by ADR-0119 decision 2 — `needs.line_prize_advance` derives it.
_ENERGY_DENIAL_PER = 0.2     # ADR-0066: sub-prize per SUNK Energy on a KO-able gust target — a KO
_ENERGY_DENIAL_CAP = 0.8     # destroys everything attached, so prefer the loaded body. Capped < 1 prize.
_LOADED_KO_SWING = 2         # ADR-0066: the Energy-denial margin over the baseline Active KO that
                             # justifies spending the gust Supporter on an EQUAL-prize KO.


class GustMixin:
    """The Pilot-side closed-form half of the Gust doctrine (mixed into `Pilot`). Reads shared Pilot
    helpers and the per-decision `Board` it is handed."""

    def _gust_tactical(self, obs: dict, select: dict, board, option: dict) -> float:
        """KO_SCORE-class value for PLAYING a gust card when the gust takes my LAST prize(s). Fires only
        when a direct attack on the current Active does NOT — else just attack (ADR-0022)."""
        if option.get("type") != _PLAY:
            return 0
        cid = self._option_card_id(obs, select, option)
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        mp = board.my_prizes_remaining
        if ("gust" in tags and mp > 0
                and board.gust_best_ko_prizes >= mp and board.active_ko_prizes < mp):
            return KO_SCORE + board.gust_best_ko_prizes
        return 0

    def _gust_target_tactical(self, obs: dict, select: dict, board, option: dict) -> float:
        """KO_SCORE-class value for a gust TARGET option at a SWITCH select (ADR-0022). Guarded to
        opponent-owned options — SWITCH is ALSO my own retreat. 0 for an un-KO-able target."""
        if (select.get("context") != _SWITCH or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return 0
        yi = (obs.get("current") or {}).get("yourIndex", 0)
        if option.get("playerIndex", yi) == yi:          # my own retreat, not a gust of opponent
            return 0
        target = self._option_pokemon(obs, select, option)
        if not target:
            return 0
        my_stat = self.stats.get(board.my_active_id) if self.stats else None
        payable = board.my_active_energy + (0 if board.energy_attached
                                            else self._best_hand_attach_units(board.hand_ids, my_stat))
        if my_stat and not my_stat.can_pay_cheapest(payable):
            return 0                                     # the KO premise is unpayable this turn (f31)
        if not self._gust_can_ko(my_stat, target):
            return 0
        # THE LINE'S PRIZE, not the body's own (ADR-0119 decision 2). This call site does NOT go through
        # `_opponent_target_rows`, so it must take the reading itself rather than inherit `prize_advance`.
        line_prize, line_hops = self.combat.forward_line_prize(target.get("id"))
        advance = line_prize_advance(own_prize=self._prize_value(target),
                                     max_line_prize=line_prize, hops=line_hops)
        return (KO_SCORE + advance + self._gust_target_denial(board, target)
                + self._gust_forward_denial(target) + self._gust_matchup_priority(board, target)
                + self._gust_energy_denial(target)
                + self._gust_snipe_synergy(board, my_stat, target))

    def _gust_energy_denial(self, target: dict) -> float:
        """Sub-prize tie-break for the SUNK Energy a gust-KO destroys (ADR-0066): among equal-prize KO-able
        bodies prefer the loaded one. Capped < 1 prize, so it never overrides a real prize difference."""
        n = len((target or {}).get("energies") or [])
        return min(_ENERGY_DENIAL_CAP, _ENERGY_DENIAL_PER * n)

    def _gust_can_ko(self, my_stat, body: dict | None) -> bool:
        """The gust oracle's KO test for a BENCH defender: the cheapest-attack summary OR any per-attack
        prediction reaching its HP (ADR-0066). ONE test feeds the play gate, the totals and the pick."""
        if self._can_ko(my_stat, body):
            return True
        hp = (body or {}).get("hp", 0)
        if not (my_stat and hp):
            return False
        return any(self.predicted_damage(getattr(my_stat, "cardId", None), aid, body) >= hp
                   for aid in (getattr(my_stat, "attacks", None) or ()))

    def _gust_snipe_synergy(self, board, my_stat, target: dict) -> int:
        """Extra prize when KOing the gusted target ALSO lets my bench rider finish a SECOND benched
        Pokémon. A full prize, not a tie-break; it never overrides a higher-prize target."""
        return self._snipe_after_gust_prizes(board.opp_bench, my_stat, target)

    def _snipe_after_gust_prizes(self, opp_bench, my_stat, target: dict) -> int:
        """The bench-tuple core of `_gust_snipe_synergy`, shared with the Board-signal builders that run
        before a `Board` exists. ``opp_bench`` is the ((cardId, hp), …) snapshot INCLUDING the target."""
        t_hp = (target or {}).get("hp", 0)
        if not (my_stat and t_hp):
            return 0
        others, removed = [], False                      # bench left after target is dragged Active
        for entry in opp_bench:
            if not removed and tuple(entry) == (target.get("id"), t_hp):
                removed = True
                continue
            others.append(tuple(entry))
        best = 0
        for aid in (getattr(my_stat, "attacks", None) or ()):
            # per-attack oracle (ADR-0032): KO check honors the attack's own ignore flags
            if self.predicted_damage(getattr(my_stat, "cardId", None), aid, target) >= t_hp:
                best = max(best,
                           self._snipe_ko_prizes(others, self.combat.rider_snipe(aid)),
                           # the spread rider is the same drag-and-finish synergy (ADR-0066;
                           # ep85046350 f81: gust Roserade, Phantom Dive KOs it AND the Gible)
                           self._spread_ko_prizes(others, self.combat.rider_spread(aid)))
        return best

    def _gust_forward_denial(self, target: dict) -> float:
        """Sub-prize tie-break: removing a target whose evolution LINE becomes an attacker. BOARD-PRICED
        and a MAGNITUDE (ADR-0119 decision 5); rides `scaled_threat_rank`, capped at `_SURVIVAL_CAP`."""
        cid = (target or {}).get("id")
        if cid is None:
            return 0
        if not getattr(self, "scaled_threat_rank", True):
            fwd = getattr(self.stats, "forward_max_damage", None)      # the OFF branch, verbatim
            if fwd is None:
                return 0
            return _EVOLVING_GUST_DENIAL if (fwd(cid) or 0) >= _EVOLVING_THREAT_DMG else 0
        reach = float(self.combat.forward_threat_ceiling(
            cid, context=getattr(self, "_opp_attack_context", None)) or 0.0)
        if reach <= 0.0:
            return 0
        # DISCOUNT BY THE HOPS TO THE BEST-**DAMAGE** FORM, which is what `reach` measured.
        # `forward_line_prize`'s hops answer a different question, and the two genuinely diverge.
        _, hops = self.combat.forward_payoff_terms(cid)
        return min(_SURVIVAL_CAP, (reach / PRIZE_DAMAGE_RATE) * halve(hops))

    def _gust_matchup_priority(self, board, target: dict) -> float:
        """ADR-0051 sub-prize tie-break: among equal-value KO-able bodies prefer the MatchupPlan's
        highest-priority one. Only POSITIVE priorities apply; 0 when the plan is inert."""
        cid = (target or {}).get("id")
        if cid is None:
            return 0.0
        return max(0.0, board.matchup_plan.priority(cid)) * _MATCHUP_GUST_SCALE

    def _gust_stall_target_tactical(self, obs: dict, select: dict, board, option: dict) -> float:
        """Small value for a defensive stall-gust TARGET: an ENERGYLESS, high-retreat opponent benched body,
        scaled by `retreatCost`. Far below KO_SCORE, so it only decides among non-KO options (ADR-0022)."""
        if (select.get("context") != _SWITCH or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return 0
        yi = (obs.get("current") or {}).get("yourIndex", 0)
        if option.get("playerIndex", yi) == yi:
            return 0
        target = self._option_pokemon(obs, select, option)
        if not target or (target.get("energies") or []):       # energized -> not a stall body (gift)
            return 0
        stat = self.stats.get(target.get("id")) if self.stats else None
        if not (stat and stat.retreatCost >= _STALL_RETREAT):
            return 0
        # Keystone-aware: an energyless opponent EX is a far better strand than a fungible pre-evo —
        # mirror the play-side keystone read so the target picker agrees with it.
        return stat.retreatCost + (_STALL_EX_BONUS if stat.is_ex_body else 0)

    def _gust_target_denial(self, board, target: dict) -> int:
        """Defensive value of removing `target`: when it is a LIVE threat that would KO my Active, return my
        Active's prize value — prizes-first is a trap (ADR-0022). 0 for an inert target."""
        if not (self.stats and target and (target.get("energies") or [])):
            return 0
        t_stat = self.stats.get(target.get("id"))
        if not t_stat:
            return 0
        # target attacks ME: target = attacker, my Active = defender — per-attack oracle max
        incoming = self._predicted_max_damage(t_stat, {"id": board.my_active_id})
        if board.my_active_hp and incoming >= board.my_active_hp:
            return self._prize_value({"id": board.my_active_id})
        return 0

    # ── Board-signal builders (called from Pilot._board to populate gust gap signals) ──
    def _active_ko_prizes(self, ma: dict | None, oa: dict | None, payable: int = 99) -> int:
        """Prizes from KOing the opponent's CURRENT Active with the BEST attack I can AFFORD — the baseline
        a gust must beat. ``payable`` = the Energy my Active can really pay; an unaffordable KO is no KO."""
        if not (self.stats and ma and oa):
            return 0
        my_stat = self.stats.get(ma.get("id"))
        if my_stat and not my_stat.can_pay_cheapest(payable):
            return 0                                     # can't afford ANY attack this turn
        # KO via the cheapest attack OR the best AFFORDABLE attack — the latter catches an EXPENSIVE
        # menu KO the cheap summary misses, so a gust must beat the real best direct KO.
        return self._prize_value(oa) if (self._can_ko(my_stat, oa)
                                         or self._active_can_ko(ma, oa)) else 0

    def _opp_active_condition_gift(self, opp: dict | None) -> bool:
        """True if the opponent's Active carries ANY special condition — gusting it off to the bench would
        CLEAR it (rules.md §8), handing them a free cure. The guard the stall-gust checks."""
        if not opp:
            return False
        return any(opp.get(k) for k in ("poisoned", "burned", "asleep", "paralyzed", "confused"))

    def _active_condition_ko_prizes(self, opp: dict | None, oa: dict | None) -> int:
        """Prizes from the opponent's Active dying to poison/burn at the upcoming Checkup (the fixed ticks,
        rulebook L193/L209). A free KO, so an offensive gust must beat it — gusting cures the condition."""
        if not (self.stats and opp and oa):
            return 0
        hp = oa.get("hp", 0)
        tick = (10 if opp.get("poisoned") else 0) + (20 if opp.get("burned") else 0)
        return self._prize_value(oa) if (0 < hp <= tick) else 0

    def _gust_best_ko_prizes(self, ma: dict | None, opp: dict | None, payable: int = 99) -> int:
        """Best prizes among the opponent's benched Pokémon my Active could KO this turn after gusting it
        Active (ADR-0022). ``payable`` gates it on Energy I can really pay — an unpayable KO endorses nothing."""
        if not (self.stats and ma and opp):
            return 0
        my_stat = self.stats.get(ma.get("id"))
        if my_stat and not my_stat.can_pay_cheapest(payable):
            return 0                                     # cheapest attack unpayable this turn
        best = 0
        for b in (opp.get("bench") or []):
            if b and self._gust_can_ko(my_stat, b):
                best = max(best, self._prize_value(b))
        return best

    def _gust_best_total_prizes(self, ma: dict | None, opp: dict | None, payable: int = 99) -> int:
        """`_gust_best_ko_prizes` PLUS the same-attack rider on the bench that REMAINS after the gust — the
        gust line's FULL prize take this turn (ADR-0066). Equal to the plain read for a rider-less body."""
        if not (self.stats and ma and opp):
            return 0
        my_stat = self.stats.get(ma.get("id"))
        if my_stat and not my_stat.can_pay_cheapest(payable):
            return 0
        bench = tuple((b.get("id"), b.get("hp", 0)) for b in (opp.get("bench") or []) if b)
        best = 0
        for b in (opp.get("bench") or []):
            if b and self._gust_can_ko(my_stat, b):
                best = max(best, self._prize_value(b)
                           + self._snipe_after_gust_prizes(bench, my_stat, b))
        return best

    def _menu_attack_total_prizes(self, ma: dict | None, oa: dict | None, opp: dict | None,
                                  payable: int = 99) -> int:
        """Best TOTAL prizes ONE menu attack takes this turn WITHOUT a gust — the snipe-aware baseline a
        gust must beat (ADR-0066). Never below `_active_ko_prizes`, so the old baseline is subsumed."""
        if not (self.stats and ma):
            return 0
        my_stat = self.stats.get(ma.get("id"))
        if my_stat and not my_stat.can_pay_cheapest(payable):
            return 0
        bench = tuple((b.get("id"), b.get("hp", 0)) for b in ((opp or {}).get("bench") or []) if b)
        oa_hp = (oa or {}).get("hp", 0)
        best = 0
        for aid in (getattr(my_stat, "attacks", None) or ()):
            main = (self._prize_value(oa)
                    if oa_hp and self.predicted_damage(getattr(my_stat, "cardId", None),
                                                       aid, oa) >= oa_hp else 0)
            rider = max(self._snipe_ko_prizes(bench, self.combat.rider_snipe(aid)),
                        self._spread_ko_prizes(bench, self.combat.rider_spread(aid)))
            best = max(best, main + rider)
        return max(best, self._active_ko_prizes(ma, oa, payable))

    def _gust_ko_energy_swing_calc(self, ma: dict | None, oa: dict | None, opp: dict | None,
                                   payable: int = 99) -> int:
        """Sunk-Energy margin of the gust-KO line over the baseline Active KO (ADR-0066): the Energy a
        best-prize KO-able gust target carries, MINUS what the direct Active KO would already destroy."""
        if not (self.stats and ma and opp):
            return 0
        my_stat = self.stats.get(ma.get("id"))
        if my_stat and not my_stat.can_pay_cheapest(payable):
            return 0
        best_prize, loaded = 0, 0
        for b in (opp.get("bench") or []):
            if not (b and self._gust_can_ko(my_stat, b)):
                continue
            p = self._prize_value(b)
            if p > best_prize:
                best_prize, loaded = p, len(b.get("energies") or [])
            elif p == best_prize:
                loaded = max(loaded, len(b.get("energies") or []))
        if best_prize == 0:
            return 0
        base = (len((oa or {}).get("energies") or [])
                if self._active_ko_prizes(ma, oa, payable) > 0 else 0)
        return loaded - base

    def _forward_danger(self, body: dict | None) -> int:
        """How dangerous this body is left IN PLACE: max of its own printed ceiling and its line's forward
        ceiling — a body evolves in the Active Spot without retreating, so a Riolu-shaped wall is not one."""
        if not (self.stats and body):
            return 0
        stat = self.stats.get(body.get("id"))
        own = getattr(stat, "maxDamage", 0) or 0
        fwd_fn = getattr(self.stats, "forward_max_damage", None)
        fwd = (fwd_fn(body.get("id")) or 0) if fwd_fn else 0
        return max(own, fwd)

    def _stall_swap_pointless(self, opp: dict | None) -> bool:
        """True when the famine stall-gust would swap one stranded wall for an equal-or-worse one (ADR-0066),
        so the gust denies nothing. Stall value is with-vs-without the swap, never a flat strand bounty."""
        if not (self.stats and opp):
            return False
        oa = (opp.get("active") or [None])[0]
        if not oa or (oa.get("energies") or []):
            return False
        a_stat = self.stats.get(oa.get("id"))
        if not (a_stat and a_stat.retreatCost >= _STALL_RETREAT):
            return False
        a_danger = self._forward_danger(oa)
        for b in (opp.get("bench") or []):
            if not b or (b.get("energies") or []):
                continue
            st = self.stats.get(b.get("id"))
            if (st and st.retreatCost >= _STALL_RETREAT
                    and self._forward_danger(b) < a_danger):
                return False                     # a strictly tamer wall exists — the swap still gains
        return True

    def _stall_target_exists(self, opp: dict | None) -> bool:
        """True if the opponent has an ENERGYLESS, high-retreat benched Pokémon — the stall-gust candidate.
        Energyless = can't attack once stranded; high-retreat = a real tempo cost (ADR-0022)."""
        if not (self.stats and opp):
            return False
        for b in (opp.get("bench") or []):
            if not b or (b.get("energies") or []):
                continue
            stat = self.stats.get(b.get("id"))
            if stat and stat.retreatCost >= _STALL_RETREAT:
                return True
        return False

    def _stall_target_is_keystone(self, opp: dict | None) -> bool:
        """True if a stall-gust target is the opponent's KEY attacker — an ex / Mega ex. Stranding their
        main attacker is high-value disruption, so it can win the Supporter slot over a redundant dig."""
        if not (self.stats and opp):
            return False
        for b in (opp.get("bench") or []):
            if not b or (b.get("energies") or []):
                continue
            stat = self.stats.get(b.get("id"))
            if stat and stat.retreatCost >= _STALL_RETREAT and stat.is_ex_body:
                return True
        return False


# ── WHETHER-TO-PLAY band DELETED (Issue #386): the sequence composer makes that comparison by
# construction. The TARGET-pick side above is untouched — it is the firing equation's own machinery.
HYPOTHESES = []
