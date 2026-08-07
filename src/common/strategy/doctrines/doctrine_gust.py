"""DOCTRINE: Gust (Boss's Orders) — ADR-0022. One file, end to end.

A gust forces the opponent to switch a benched Pokémon into their Active Spot. It is TWO Pilot
decisions over ONE closed-form KO oracle (`_can_ko`, lifted to any bench defender): *whether to
play it* and *which benched Pokémon to drag up*. All KO / lethal / prize value lives in the Tactical
layer here (`GustMixin`, mixed into `common.pilot.Pilot`) so the weight-tuner never ingests a
KO_SCORE-magnitude seed; only the two positional weights (`HYPOTHESES`) are tunable. ONE oracle feeds
both decisions, so the play-reason and the picked target agree by construction. See
docs/general-strategy.md and docs/adr/0022-gust-is-closed-form-lethal-lookahead.md.
"""
from __future__ import annotations

from common.currency import PRIZE_DAMAGE_RATE   # the ONE damage->prize crossing
from common.grading import halve                # ...and the ONE hop discount (ADR-0070 §6)
from common.needs import _SURVIVAL_CAP, line_prize_advance   # the sub-prize bound; the Denial leg
from common.strategy.context import (KO_SCORE, _BENCH, _CARD, _EVOLVING_THREAT_DMG, _PLAY,
                                      _SUPPORTER, _SWITCH)
from common.strategy.strategy import Hypothesis, Plan

_STALL_RETREAT = 1           # min retreat cost of a STRANDABLE energyless body: no Energy of its own
_STALL_EX_BONUS = 3          # keystone bump: stranding an energyless opponent EX (2-prize, win-condition-
                             # class body that burns a full turn to retreat) beats a fungible pre-evo by
                             # more than a point of retreat cost (ml f41); << KO_SCORE so a KO still wins
                             # to discard -> can't pay ANY retreat cost (≥1) -> opponent must first
                             # spend a turn's attach to retreat it — real tempo cost even at 1 (ep82754875)
_EVOLVING_GUST_DENIAL = 0.5  # OFF-BRANCH ONLY since ADR-0119 decision 5 — dead on the live path.
                             # It was the flat sub-prize tie-break for gusting a latent evolving
                             # threat, tripped by a PRINTED damage threshold. `_gust_forward_denial`
                             # now reads the board-priced `forward_threat_ceiling` as a magnitude;
                             # this survives solely to let `scaled_threat_rank=False` restore the
                             # printed read byte-for-byte, which is what keeps that incident lever
                             # honest. Do not tune it — it is a historical value, not a live one.
                             # (`_EVOLVING_THREAT_DMG` is NOT in the same position: it lives in
                             # `strategy/context.py` and is still read live by the snipe-relevance
                             # forward leg and `baseline_snipe`.)
_MATCHUP_GUST_SCALE = 0.004  # ADR-0051: scale a MatchupPlan role priority (base ≤100, γ-pre-scaled) into
                             # the gust sub-prize tie-break band — prize_liability 100 → 0.4, so the worst
                             # stack (0.5 evolving + 0.4 matchup) stays < 1 prize and never overrides a
                             # real prize difference. Aligns the gust target pick with the snipe order.
# `_WINCON_DENIAL_PRIZES = 1.5` stood here (ADR-0051 Phase 3b) — a flat γ-scaled, role-scoped bump for
# gusting the opponent's WIN-CONDITION line. DELETED by ADR-0119 decision 2, not relocated: the
# question it answered ("what does this line BECOME") is now read from card facts by
# `needs.line_prize_advance` over `CombatMath.forward_line_prize`, at `_gust_target_tactical`. Three
# things improved — an authored constant became a derivation; the γ-gate went, so it fires on an
# unrecognised opponent instead of reading 0; and the role-gate went, so any line with a bigger
# forward form is priced rather than only the two roles a Brief had curated.
_ENERGY_DENIAL_PER = 0.2     # ADR-0066: sub-prize per SUNK Energy on a KO-able gust target — a KO
_ENERGY_DENIAL_CAP = 0.8     # destroys everything attached (the ADR-0062 marginal strip, pointed across
                             # the table), so among equal-prize targets prefer the loaded body. Capped
                             # < 1 prize: breaks ties, never overrides a real prize difference.
_LOADED_KO_SWING = 2         # ADR-0066: the Energy-denial margin (target's sunk Energy minus what the
                             # baseline Active KO already destroys) that justifies spending the gust
                             # Supporter on an EQUAL-prize KO (ep85163079 f30: the 4-Energy Staryu one
                             # turn from Mega Starmie ex vs a 1-Energy Cinderace — same 1 prize, not the
                             # same loss). ≥ 2 so a single-Energy edge never burns Boss's (ep82224509 f46).


class GustMixin:
    """The Pilot-side closed-form half of the Gust doctrine (mixed into `Pilot`). Reads shared Pilot
    helpers (`_can_ko`, `_prize_value`, `_wr_adjusted`, `_option_pokemon`, `_option_card_id`) and the
    per-decision `Board` it is handed."""

    def _gust_tactical(self, obs: dict, select: dict, board, option: dict) -> float:
        """KO_SCORE-class value for PLAYING a gust card (Function Tag `gust`, e.g. Boss's Orders) when
        the gust takes my LAST prize(s) — winning the game. Structural (not a tunable weight), so it
        lives in the Tactical layer like every other knockout rather than as a positional Hypothesis.
        Fires only when the best gustable KO reaches my remaining prize count AND a direct attack on
        the current Active does NOT (else just attack — don't spend the Supporter). 0 otherwise — the
        non-lethal gust is the tunable `gust-for-the-ko` Hypothesis. ADR-0022."""
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
        """KO_SCORE-class value for a gust TARGET option — at a SWITCH select, choosing WHICH of the
        opponent's benched Pokémon to drag into the Active Spot (Boss's Orders; ADR-0022). Scores each
        opponent-owned bench target by whether my Active can KO it after the gust, plus its prize value,
        so the agent drags up the most valuable KO-able body. Guarded to opponent-owned options
        (`playerIndex != yourIndex`) because SWITCH is ALSO my own retreat. 0 for an un-KO-able target
        (a non-KO gust is a blunder) and off any non-gust SWITCH option. The threat / evolving-threat /
        weakest tie-breaks among equal targets are the (widened) snipe Hypotheses."""
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
        # THE LINE'S PRIZE, not the body's own (ADR-0119 decision 2). This is where
        # `_gust_wincon_denial` went: that term added a flat `_WINCON_DENIAL_PRIZES` (1.5) x gamma
        # for a target the MatchupPlan had labelled `prize_liability` / `fragile_preevo`, so it was
        # silent on an unrecognised opponent (gamma 0) and on any wincon line the Brief had not
        # curated. The line-prize reading answers the same question from CARD FACTS, so it fires on
        # every board — and it is derived rather than authored.
        #
        # Stated because it is easy to get wrong when reading the ADR alone: this call site does NOT
        # go through `_opponent_target_rows`, so it does not inherit `prize_advance` from there. It
        # has to take the reading itself, or deleting `_gust_wincon_denial` would silently drop the
        # premium here while the ADR claimed it had merely moved.
        line_prize, line_hops = self.combat.forward_line_prize(target.get("id"))
        advance = line_prize_advance(own_prize=self._prize_value(target),
                                     max_line_prize=line_prize, hops=line_hops)
        return (KO_SCORE + advance + self._gust_target_denial(board, target)
                + self._gust_forward_denial(target) + self._gust_matchup_priority(board, target)
                + self._gust_energy_denial(target)
                + self._gust_snipe_synergy(board, my_stat, target))

    def _gust_energy_denial(self, target: dict) -> float:
        """Sub-prize tie-break for the SUNK Energy a gust-KO destroys (ADR-0066): everything attached
        to the target dies with it, so among equal-prize KO-able bodies prefer the loaded one — the
        ADR-0062 marginal-strip ruling pointed across the table (ep85163079 f30: the 4-Energy Staryu
        over any bare body). Capped < 1 prize so it never overrides a real prize difference."""
        n = len((target or {}).get("energies") or [])
        return min(_ENERGY_DENIAL_CAP, _ENERGY_DENIAL_PER * n)

    def _gust_can_ko(self, my_stat, body: dict | None) -> bool:
        """The gust oracle's KO test for a BENCH defender: the cheapest-attack summary (`_can_ko`)
        OR any per-attack prediction reaching its HP — the `_active_ko_prizes` expensive-menu-KO
        patch (Nebula Beam 210 vs 190 HP, ADR-0052) finished for the bench side (ADR-0066;
        ep85046350 f79/f81: Phantom Dive's 200 KOs the 130-HP Roserade the cheap summary misses).
        One test feeds the play gate, the totals, the energy swing AND the target pick, so the
        play-reason and the picked target keep agreeing by construction."""
        if self._can_ko(my_stat, body):
            return True
        hp = (body or {}).get("hp", 0)
        if not (my_stat and hp):
            return False
        return any(self.predicted_damage(getattr(my_stat, "cardId", None), aid, body) >= hp
                   for aid in (getattr(my_stat, "attacks", None) or ()))

    def _gust_snipe_synergy(self, board, my_stat, target: dict) -> int:
        """Extra prize when KOing the gusted target ALSO lets my bench-snipe rider finish a SECOND
        benched Pokémon — a 2-prize gust+snipe (ep82523164 f55: drag up the 70-HP Dwebble so Jetting
        Blow KOs it AND the 50 snipe finishes the 20-HP Dwebble, over dragging the 20-HP one where the
        snipe reaches nothing). Among my Active's attacks that KO the target, the best snipe-KO prize
        over the bench that REMAINS after the target is dragged Active. A full prize (not a tie-break),
        so it correctly prefers the 2-prize line; never overrides a higher-prize target. 0 otherwise.

        Args:
            board: the per-decision Board (``opp_bench`` snapshot).
            my_stat: my Active's CardStat (its attacks + riders).
            target: the benched Pokémon this gust option drags Active.

        Returns:
            The best extra snipe-KO prize enabled by gusting this target (0 if none).
        """
        return self._snipe_after_gust_prizes(board.opp_bench, my_stat, target)

    def _snipe_after_gust_prizes(self, opp_bench, my_stat, target: dict) -> int:
        """The bench-tuple core of `_gust_snipe_synergy`, shared with the Board-signal builders
        (`_gust_best_total_prizes`) which run before a `Board` exists. ``opp_bench`` is the
        ((cardId, hp), …) snapshot INCLUDING the target (it is removed here)."""
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
        """Sub-prize tie-break: removing a target whose evolution LINE becomes an attacker is worth a
        little extra — it denies a latent threat before it comes online. < 1 prize, so it breaks ties
        among equal-prize targets without ever overriding a real prize difference.

        **The reading is BOARD-PRICED and a MAGNITUDE (ADR-0119 decision 5).** It used to
        threshold the provider's PRINTED forward index — `forward_max_damage >= 100` — and that index
        drops the Damage Formula's whole `per_unit x count(variable)` term, so it reads Alakazam at
        **10** and priced one of the set's scariest evolving lines at exactly 0. Issue #213 already
        migrated the threat rank off that same printed index onto
        `CombatMath.forward_threat_ceiling`; this call site was left behind, and this is it catching
        up. Thresholding was the second flaw: a line at 99 and a line at 400 both scored 0 and 0.5.

        Rides `scaled_threat_rank` — the SAME lever Issue #213 armed for the SAME fact, because one
        fact should have one switch. OFF restores the printed threshold byte-for-byte, which is what
        keeps that lever honest: an incident switch that reverted two of three printed reads would be
        worse than none. That is why `_EVOLVING_GUST_DENIAL` / `_EVOLVING_THREAT_DMG` survive below
        rather than being deleted — they are the OFF branch, dead on the live path.

        Capped at `needs._SURVIVAL_CAP` rather than at a band of its own: this family already has
        exactly one "sub-prize tie-break ceiling" constant, and deriving beats authoring."""
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
        # `forward_line_prize`'s hop count answers a different question — how far away the best
        # PRIZE is — and the two genuinely diverge (a line whose biggest attacker sits at hop 1
        # while its biggest prize sits at hop 2). Discounting a damage quantity by the prize
        # distance was wrong in both directions: it under-discounted the very case decision 5 is
        # justified by (a 1-prize Basic evolving into a 1-prize Stage 1 that hits hard has NO prize
        # gap, so hops read 0 and the discount vanished entirely), and over-discounted any line
        # whose prize form sits deeper than its attacker.
        _, hops = self.combat.forward_payoff_terms(cid)
        return min(_SURVIVAL_CAP, (reach / PRIZE_DAMAGE_RATE) * halve(hops))

    def _gust_matchup_priority(self, board, target: dict) -> float:
        """ADR-0051 sub-prize tie-break for a gust TARGET: among equal-value KO-able bodies, prefer
        dragging up the MatchupPlan's highest-priority one (the wincon, its pre-evo, or a curated
        disruption target), so the gust pick agrees with the snipe order. Only POSITIVE priorities
        apply — a KO-able body is worth its prize regardless of any `avoid` — and the scale keeps it
        << 1 prize, so it never overrides a real prize difference. 0 when the plan is inert
        (`matchup_targeting` off / unrecognized opponent). Supersedes the ADR-0038 `_gust_brief_denial`
        (fragile_preevo/engine only), now covering every role via the one spine."""
        cid = (target or {}).get("id")
        if cid is None:
            return 0.0
        return max(0.0, board.matchup_plan.priority(cid)) * _MATCHUP_GUST_SCALE

    def _gust_stall_target_tactical(self, obs: dict, select: dict, board, option: dict) -> float:
        """Small value for a defensive stall-gust TARGET — at a SWITCH select, an ENERGYLESS,
        high-retreat (>= `_STALL_RETREAT`) opponent benched Pokémon is the body to strand Active (it
        can't attack and costs them a retreat). Scaled by `retreatCost` so the most expensive-to-retreat
        body wins; far below a KO target's KO_SCORE, so it only decides among non-KO options (a real KO
        always outranks a stall). Owner-guarded; 0 otherwise. ADR-0022."""
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
        # Keystone-aware: an energyless opponent EX is a far better strand than a fungible pre-evo — mirror
        # the play-side `gust-to-strand-the-key-attacker` keystone read so the target picker agrees with it
        # (ml f41: strand the 2-prize Meowth ex, weak to our Fighting, over a retreat-2 Riolu pre-evo).
        return stat.retreatCost + (_STALL_EX_BONUS if stat.is_ex_body else 0)

    def _gust_target_denial(self, board, target: dict) -> int:
        """Defensive value of removing `target` via the gust: if it is a LIVE threat — it carries
        Energy AND its biggest attack (weakness-doubled vs my Active) would KO my Active — return my
        Active's prize value, so a live attacker that would take my win-condition outranks a bigger but
        INERT prize (prizes-first is a trap; ADR-0022). 0 for an inert / non-threatening target."""
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
        """Prizes from Knocking Out the opponent's CURRENT Active with the BEST attack I can afford this
        turn (0 if I can't) — the baseline a gust must beat (gusting benches their current Active, so a
        gust is only worth the Supporter for a strictly bigger KO). Uses the best AFFORDABLE attack, not
        just the cheapest: an EXPENSIVE menu KO (Mega Starmie's Nebula Beam 210 vs a 190-HP Active the
        cheap Jetting Blow can't touch) still counts — else `gust-for-the-ko` fires on a gust taking FEWER
        prizes than the direct attack already offers (eb98 / ep83456015 f38: a 3-prize menu KO masked by
        `active_ko_prizes=0`). ``payable`` = the Energy my Active can pay an attack with this turn (attached
        + best unspent hand attach): a KO I cannot afford is no KO (ep83457493 f31)."""
        if not (self.stats and ma and oa):
            return 0
        my_stat = self.stats.get(ma.get("id"))
        if my_stat and not my_stat.can_pay_cheapest(payable):
            return 0                                     # can't afford ANY attack this turn
        # KO via the cheapest attack (`_can_ko`, minCostDamage) OR the best AFFORDABLE attack
        # (`_active_can_ko`, per-attack oracle) — the latter catches an EXPENSIVE menu KO the cheap
        # summary misses (Nebula Beam 210 vs 190 HP), so a gust must beat the real best direct KO.
        return self._prize_value(oa) if (self._can_ko(my_stat, oa)
                                         or self._active_can_ko(ma, oa)) else 0

    def _opp_active_condition_gift(self, opp: dict | None) -> bool:
        """True if the opponent's Active carries ANY special condition (poison/burn/sleep/paralyze/
        confuse) — gusting it off to the bench would CLEAR it (rules.md §8), handing them a free cure.
        The guard the stall-gust checks so it never rescues a working condition. Flags ride as booleans
        on the player dict (PlayerState.poisoned/…). ADR-0022 #10."""
        if not opp:
            return False
        return any(opp.get(k) for k in ("poisoned", "burned", "asleep", "paralyzed", "confused"))

    def _active_condition_ko_prizes(self, opp: dict | None, oa: dict | None) -> int:
        """Prizes from the opponent's CURRENT Active dying to poison/burn at the upcoming Pokémon
        Checkup — its prize value when `0 < hp <= 10*poison + 20*burn` (the fixed per-Checkup ticks,
        rulebook L193/L209), else 0. A free KO I'd take WITHOUT attacking, so an offensive gust must
        beat this too: gusting that Active off to the bench cures it and forfeits the free prize.
        ADR-0022 #10 (offensive baseline)."""
        if not (self.stats and opp and oa):
            return 0
        hp = oa.get("hp", 0)
        tick = (10 if opp.get("poisoned") else 0) + (20 if opp.get("burned") else 0)
        return self._prize_value(oa) if (0 < hp <= tick) else 0

    def _gust_best_ko_prizes(self, ma: dict | None, opp: dict | None, payable: int = 99) -> int:
        """Best prizes among the opponent's benched Pokémon my Active could Knock Out this turn after
        gusting it to the Active Spot — the whether-to-play signal for a gust Supporter (ADR-0022).
        Applies the shared `_can_ko` oracle to each bench defender; the max `_prize_value` among the
        KO-able ones (0 if none). ``payable`` gates the whole signal on the Energy my Active can
        actually pay this turn (attached + the best unspent hand attach) — an unpayable KO must not
        endorse the gust (ep83457493 f31: 0 Energy, no Energy in hand, yet `gust-for-the-ko` fired).
        Closed-form off engine stats, no Search."""
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
        """`_gust_best_ko_prizes` PLUS the same-attack snipe rider on the bench that REMAINS after
        the gust — the gust line's FULL prize take this turn, max over KO-able targets (ADR-0066).
        Equals `gust_best_ko_prizes` for a rider-less attacker, so the plain-KO gate is unchanged;
        with a rider it keeps the 2-prize gust+snipe firing past a snipe-aware baseline
        (ep82523164 f55 vs ep86091435 f119)."""
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
        """Best TOTAL prizes ONE menu attack takes this turn WITHOUT a gust: its main KO of the
        current Active (if any) plus its own bench rider's (snipe or spread) KOs — the snipe-aware
        baseline a gust must beat (ADR-0066). ep86091435 f119: Phantom Dive's 60 spread already
        collects the 40-HP Relicanth, so spending Boss's Orders to drag it up for the SAME prize is
        a wasted Supporter. Never below `_active_ko_prizes` (the per-attack loop can miss a KO the
        cheapest-attack summary sees), so the old baseline is strictly subsumed. Coarse
        affordability (`can_pay_cheapest`, the gust signals' shared gate)."""
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
        """Sunk-Energy margin of the gust-KO line over the baseline Active KO (ADR-0066): the most
        Energy carried by a best-prize KO-able gust target, MINUS the Energy the direct Active KO
        would already destroy (0 when no Active KO exists). A KO destroys everything attached — the
        ADR-0062 marginal strip pointed across the table — so on an equal-prize tie a big positive
        swing (ep85163079 f30: 4-Energy Staryu vs 1-Energy Cinderace → +3) is what the gust
        Supporter actually buys. 0 when no gust KO exists."""
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
        """How dangerous this body is left IN PLACE: the max of its own printed ceiling and its
        evolution line's forward ceiling (`forward_max_damage`, the ADR-0020 provider primitive) —
        a body evolves in the Active Spot without retreating, so a Riolu-shaped wall is not a wall.
        The comparator behind `_stall_swap_pointless` (ADR-0066)."""
        if not (self.stats and body):
            return 0
        stat = self.stats.get(body.get("id"))
        own = getattr(stat, "maxDamage", 0) or 0
        fwd_fn = getattr(self.stats, "forward_max_damage", None)
        fwd = (fwd_fn(body.get("id")) or 0) if fwd_fn else 0
        return max(own, fwd)

    def _stall_swap_pointless(self, opp: dict | None) -> bool:
        """True when the famine stall-gust would swap one stranded wall for an equal-or-worse one
        (ADR-0066): the opponent's CURRENT Active is ITSELF an energyless, high-retreat strand body,
        and no stall candidate on their bench is strictly LESS dangerous in place than it — so the
        gust denies nothing (ep86091435 f13: an energyless Duraludon dragged up over an energyless
        Duraludon, 'doesnt really make a difference'). The ADR-0062/0063 marginality ruling applied
        to tempo: stall value is with-vs-without the swap, never a flat strand bounty. False (swap
        may gain) whenever their Active holds Energy, retreats free, or a tamer wall exists."""
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
        """True if the opponent has an ENERGYLESS, high-retreat (>= `_STALL_RETREAT`) benched Pokémon —
        the defensive stall-gust candidate (drag it Active so they must spend a turn retreating it
        before they can attack). Energyless = can't attack once stranded; high-retreat = a real tempo
        cost. Closed-form off engine stats; needs `CardStat.retreatCost`. ADR-0022."""
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
        """True if a stall-gust target (energyless, high-retreat benched body) is the opponent's KEY
        attacker — an ex / Mega ex (their win-condition-class Pokémon). Stranding their main attacker
        Active, where it can't attack and costs a full turn to retreat, is high-value disruption — far
        more than stranding a generic wall — so it can win the Supporter slot over a redundant dig
        (ep82751468 f57, the mirror: gust their bench Mega Starmie ex). Closed-form off engine stats."""
        if not (self.stats and opp):
            return False
        for b in (opp.get("bench") or []):
            if not b or (b.get("energies") or []):
                continue
            stat = self.stats.get(b.get("id"))
            if stat and stat.retreatCost >= _STALL_RETREAT and stat.is_ex_body:
                return True
        return False


# ── the WHETHER-TO-PLAY band is DELETED (POC-T4/5, Issue #386) ───────────────────────────────────
# Five rungs died here: `gust-for-the-ko` (+50), `gust-for-the-loaded-equal-ko` (+50),
# `gust-for-the-stall` (+10), `stall-gust-over-dev-when-starved` (+95) and
# `gust-to-strand-the-key-attacker` (+20). All five answered ONE question — *"is this worth the
# Supporter slot?"* — by hand-comparing the gust's prize total against the menu's, which is exactly
# the comparison a sequence composer makes by construction: gust-then-attack is a SEQUENCE, and its
# end board carries the prizes taken, the body stranded and the Supporter spent. Issue #263 §
# *The families this prices* retires the band by name, +95 included.
#
# **The TARGET-pick side above is untouched and is not a rung.** `GustMixin` is the firing
# equation's own machinery (ADR-0022 / ADR-0066: which body to drag, the stall-target reads, the
# loaded-KO energy swing), consumed through Board fields by the tactical layer and by the win rung's
# gust generator. Issue #386 says so explicitly — *"the TARGET-pick side is FIRING equation-owned and
# untouched"*.
HYPOTHESES = []
