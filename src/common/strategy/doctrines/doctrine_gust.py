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

from common.strategy.context import (KO_SCORE, _BENCH, _CARD, _EVOLVING_THREAT_DMG, _PLAY,
                                      _SUPPORTER, _SWITCH)
from common.strategy.strategy import Hypothesis, Plan

_STALL_RETREAT = 1           # min retreat cost of a STRANDABLE energyless body: no Energy of its own
                             # to discard -> can't pay ANY retreat cost (≥1) -> opponent must first
                             # spend a turn's attach to retreat it — real tempo cost even at 1 (ep82754875)
_EVOLVING_GUST_DENIAL = 0.5  # sub-prize tie-break for gusting a latent evolving threat (< 1 prize, so
                             # never overrides a real prize difference)
_BRIEF_GUST_DENIAL = 0.4     # γ-scaled sub-prize tie-break for gusting a Brief target (ADR-0038):
                             # fragile_preevo, or engine gated on opp_is_engine_dependent. 0.4 so the
                             # worst stack (0.5 evolving + 0.4γ brief) stays < 1 prize — the Brief
                             # aligns the gust pick with the snipe order, never beats a prize difference


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
        if my_stat and (my_stat.minAttackCost or 99) > payable:
            return 0                                     # the KO premise is unpayable this turn (f31)
        if not self._can_ko(my_stat, target):
            return 0
        return (KO_SCORE + self._prize_value(target) + self._gust_target_denial(board, target)
                + self._gust_forward_denial(target) + self._gust_brief_denial(board, target)
                + self._gust_snipe_synergy(board, my_stat, target))

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
        t_hp = (target or {}).get("hp", 0)
        t_stat = self.stats.get(target.get("id")) if (self.stats and target) else None
        if not (my_stat and t_hp):
            return 0
        others, removed = [], False                      # bench left after target is dragged Active
        for entry in board.opp_bench:
            if not removed and tuple(entry) == (target.get("id"), t_hp):
                removed = True
                continue
            others.append(tuple(entry))
        best = 0
        for aid in (getattr(my_stat, "attacks", None) or ()):
            # per-attack oracle (ADR-0032): KO check honors the attack's own ignore flags
            if self.predicted_damage(getattr(my_stat, "cardId", None), aid, target) >= t_hp:
                best = max(best, self._snipe_ko_prizes(others, self._rider_snipe(aid)))
        return best

    def _gust_forward_denial(self, target: dict) -> float:
        """Sub-prize tie-break: removing a target whose evolution LINE becomes an attacker
        (`forward_max_damage` >= `_EVOLVING_THREAT_DMG`) is worth a little extra — denies a latent
        threat before it comes online. Reuses the ADR-0020 forward-evolution provider primitive (the
        shared value sub-term, not the snipe Hypothesis's weight). < 1 prize, so it breaks ties among
        equal-prize targets without ever overriding a real prize difference."""
        fwd = getattr(self.stats, "forward_max_damage", None)
        cid = (target or {}).get("id")
        if fwd is None or cid is None:
            return 0
        return _EVOLVING_GUST_DENIAL if (fwd(cid) or 0) >= _EVOLVING_THREAT_DMG else 0

    def _gust_brief_denial(self, board, target: dict) -> float:
        """γ-scaled sub-prize tie-break for gusting a Matchup-Brief target (ADR-0038): a
        `fragile_preevo` (payoff-denial — the gust+KO the Brief doctrine names), or an `engine` body
        when the Brief asserts `opp_is_engine_dependent`. Keyed on the Brief's resolved role ids so
        the gust pick agrees with the sharpened snipe order; γ and the per-lever kill-switches keep
        it silent vs an unrecognized opponent or an unwired agent. 0 otherwise."""
        cid = (target or {}).get("id")
        gamma = getattr(board, "posture_confidence", 0.0)
        if cid is None or not gamma:
            return 0
        role = board.brief_target_role(cid)
        if self.brief_preevo and role == "fragile_preevo":
            return gamma * _BRIEF_GUST_DENIAL
        if (self.brief_engine and role == "engine"
                and bool(board.opp_property("opp_is_engine_dependent", False))):
            return gamma * _BRIEF_GUST_DENIAL
        return 0

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
        return stat.retreatCost if (stat and stat.retreatCost >= _STALL_RETREAT) else 0

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
        if my_stat and (my_stat.minAttackCost or 99) > payable:
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
        if my_stat and (my_stat.minAttackCost or 99) > payable:
            return 0                                     # cheapest attack unpayable this turn
        best = 0
        for b in (opp.get("bench") or []):
            if b and self._can_ko(my_stat, b):
                best = max(best, self._prize_value(b))
        return best

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
            if stat and stat.retreatCost >= _STALL_RETREAT and (stat.ex or stat.megaEx):
                return True
        return False


# ── the two tunable positional weights (rest of doctrine is the Tactical layer above) ──
HYPOTHESES = [
    Hypothesis(
        id="gust-for-the-ko",
        rationale="Play a gust Supporter (Function Tag `gust`, e.g. Boss's Orders) only when it converts "
                  "to a Knock Out this turn (`Board.gust_best_ko_prizes > 0`) — otherwise HOLD it, since "
                  "gusting an un-KO-able target just benches the opponent's committed Active safely. Must "
                  "beat any FREE KO of the current Active too (attack or poison/burn Checkup finish); the "
                  "SETUP-before-wincon stand-down applies only to the Supporter gust, not a free ITEM gust "
                  "(Pokémon Catcher). Whether-to-play only — target selection is the SWITCH rule (ADR-0022).",
        when=lambda c: c.option_type == _PLAY and "gust" in c.tags
        and c.board.gust_best_ko_prizes > max(c.board.active_ko_prizes,
                                              c.board.active_condition_ko_prizes)
        and not (getattr(c.stat, "cardType", None) == _SUPPORTER       # Supporter-economy damping only
                 and not c.board.line_ready and not c.board.wincon_in_play),
        weight=50, status="assumed"),
    Hypothesis(
        id="gust-for-the-stall",
        rationale="Defensive stall-gust (tier 5, LAST resort): Active doomed, no gustable/direct KO "
                  "available, but the opponent has an energyless high-retreat benched Pokémon — drag it "
                  "Active so they burn a turn retreating it, buying a setup turn. Weighted below every "
                  "tutor/draw so it only wins the slot when nothing else helps; never fires on an Active "
                  "carrying a special condition (`opp_active_condition_gift`), since switching it out "
                  "CLEARS the condition (rules.md §8) and would hand a free cure (ADR-0022).",
        # NOTE (2026-07-10): dragapult f10 wants this to ALSO stand down when the opponent's Active
        # can't actually hurt us. Not authored — the natural gate (`opp_active_can_damage_us`) charges
        # attack affordability, which directly contradicts the deliberate worst-case reading of
        # `active_doomed` (they can attach/burst next turn: docs/todo/incoming-affordability.md,
        # won't-fix) and breaks REQ-GUST-0003. Bounced to the producer for a sharper condition.
        when=lambda c: c.option_type == _PLAY and "gust" in c.tags
        and c.board.active_doomed
        and c.board.gust_best_ko_prizes == 0 and c.board.active_ko_prizes == 0
        and c.board.stall_target_exists
        and not c.board.opp_active_condition_gift,
        weight=10, status="assumed"),
    Hypothesis(
        id="stall-gust-over-dev-when-starved",
        rationale="When my Active is DOOMED (incl. the forward evolves-into-attacker read: their Riolu "
                  "becomes Mega Lucario ex next turn) and I cannot pay ANY attack this turn "
                  "(`active_attack_payable` False — no attached Energy, none in hand), development "
                  "that doesn't remove the doom loses to a hard tempo stall: gust a strandable body "
                  "Active (energyless, high-retreat — it can't attack and may be stuck for turns) and "
                  "deny the evolve-and-KO a turn. Outranks a tutor's dig stack ONLY under the "
                  "energy-famine gate, so normal development is untouched (ep83457493 f20: Boss's "
                  "gust Makuhita ≻ Salvatore while Cinderace faces the Mega Lucario line with zero "
                  "Energy anywhere). Stacks on `gust-for-the-stall`; same condition-gift guard.",
        when=lambda c: c.option_type == _PLAY and "gust" in c.tags
        and c.board.active_doomed
        and not c.board.active_attack_payable
        and c.board.gust_best_ko_prizes == 0 and c.board.active_ko_prizes == 0
        and c.board.stall_target_exists
        and not c.board.opp_active_condition_gift,
        weight=95, status="assumed"),
    Hypothesis(
        id="gust-to-strand-the-key-attacker",
        rationale="When the stall-gust target is the opponent's KEY attacker — an energyless, high-retreat "
                  "ex/Mega ex (`stall_target_is_keystone`) — stranding it Active is far stronger than a "
                  "generic wall: their win-condition can't attack and they burn a full turn retreating it. "
                  "Stacks on `gust-for-the-stall` so it beats a redundant dig for the slot (drag up their "
                  "benched Mega Starmie ex instead of a wasted Salvatore — ep82751468 f57); same guards, "
                  "and a real KO still outranks it on tactical.",
        when=lambda c: c.option_type == _PLAY and "gust" in c.tags
        and c.board.active_doomed
        and c.board.gust_best_ko_prizes == 0 and c.board.active_ko_prizes == 0
        and c.board.stall_target_is_keystone
        and not c.board.opp_active_condition_gift,
        weight=20, status="testing"),
]
