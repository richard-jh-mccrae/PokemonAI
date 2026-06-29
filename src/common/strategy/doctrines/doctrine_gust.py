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

_STALL_RETREAT = 2           # retreat cost that makes a stranded energyless body a real tempo cost — the
                             # defensive stall-gust only bothers with a target this expensive to retreat
_EVOLVING_GUST_DENIAL = 0.5  # sub-prize tie-break for gusting a latent evolving threat (< 1 prize, so it
                             # never overrides a real prize difference)


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
        if option.get("playerIndex", yi) == yi:          # my own retreat, not a gust of the opponent
            return 0
        target = self._option_pokemon(obs, select, option)
        if not target:
            return 0
        my_stat = self.stats.get(board.my_active_id) if self.stats else None
        if not self._can_ko(my_stat, target):
            return 0
        return (KO_SCORE + self._prize_value(target) + self._gust_target_denial(board, target)
                + self._gust_forward_denial(target))

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
        if not target or (target.get("energies") or []):       # energized -> not a stall body (a gift)
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
        # the target attacks ME: target = attacker, my Active = defender (Weakness AND Resistance).
        incoming = self._wr_adjusted(t_stat, self.stats.get(board.my_active_id), t_stat.maxDamage or 0)
        if board.my_active_hp and incoming >= board.my_active_hp:
            return self._prize_value({"id": board.my_active_id})
        return 0

    # ── Board-signal builders (called from Pilot._board to populate the gust gap signals) ──
    def _active_ko_prizes(self, ma: dict | None, oa: dict | None) -> int:
        """Prizes from Knocking Out the opponent's CURRENT Active with my cheapest attack this turn
        (0 if I can't) — the baseline a gust must beat (gusting benches their current Active, so a gust
        is only worth the Supporter for a strictly bigger KO)."""
        if not (self.stats and ma and oa):
            return 0
        return self._prize_value(oa) if self._can_ko(self.stats.get(ma.get("id")), oa) else 0

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

    def _gust_best_ko_prizes(self, ma: dict | None, opp: dict | None) -> int:
        """Best prizes among the opponent's benched Pokémon my Active could Knock Out this turn after
        gusting it to the Active Spot — the whether-to-play signal for a gust Supporter (ADR-0022).
        Applies the shared `_can_ko` oracle to each bench defender; the max `_prize_value` among the
        KO-able ones (0 if none). Closed-form off engine stats, no Search."""
        if not (self.stats and ma and opp):
            return 0
        my_stat = self.stats.get(ma.get("id"))
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


# ── the two tunable positional weights (the rest of the doctrine is the Tactical layer above) ──
HYPOTHESES = [
    Hypothesis(
        id="gust-for-the-ko",
        rationale="Play a gust Supporter (Function Tag `gust`, e.g. Boss's Orders — switch one of the "
                  "opponent's Benched Pokémon into the Active Spot) only when it converts to a Knock Out "
                  "this turn: drag up a benched Pokémon your Active can KO, reaching a prize you couldn't "
                  "otherwise (often a high-prize ex/Mega hiding behind a wall). Fires only when such a KO "
                  "exists (`Board.gust_best_ko_prizes > 0`); otherwise HOLD it — gusting a target you "
                  "can't KO gifts the opponent, benching their committed Active safe and handing you "
                  "nothing. The SETUP-before-wincon stand-down only applies to a SUPPORTER gust (it "
                  "costs your one Supporter slot); a free ITEM gust (Pokémon Catcher) into a KO fires "
                  "even in setup. The KO must also beat any FREE KO of the current Active — both attacking it "
                  "(`active_ko_prizes`) and poison/burn finishing it at the next Checkup "
                  "(`active_condition_ko_prizes`); gusting that Active off would only cure it. "
                  "(Whether-to-play only; which benched Pokémon to drag up is the gust SWITCH "
                  "target-select rule. ADR-0022.)",
        when=lambda c: c.option_type == _PLAY and "gust" in c.tags
        and c.board.gust_best_ko_prizes > max(c.board.active_ko_prizes,
                                              c.board.active_condition_ko_prizes)
        and not (getattr(c.stat, "cardType", None) == _SUPPORTER       # Supporter-economy damping only
                 and c.plan == Plan.SETUP and not c.board.wincon_in_play),
        weight=50, status="assumed"),
    Hypothesis(
        id="gust-for-the-stall",
        rationale="Defensive stall-gust (tier 5) — a LAST resort when you're stuck. When your Active is "
                  "doomed, you have no gustable KO and can't KO their Active, but they have an "
                  "energyless, high-retreat benched Pokémon, play a gust Supporter to drag that body "
                  "into the Active Spot: it can't attack and they must spend a turn retreating it, "
                  "buying you a setup turn. Weighted low (below every tutor/draw) so it only wins the "
                  "Supporter slot when nothing else advances you — and it never fires unless you're "
                  "actually under threat. Never stall-gust an Active that carries a special condition "
                  "(`opp_active_condition_gift`) — switching it to the bench CLEARS the condition "
                  "(rules.md §8), so the stall would hand the opponent a free cure. (Mechanically weak: "
                  "a gust doesn't stop a normal retreat, so it only bites on a high retreat cost. ADR-0022.)",
        when=lambda c: c.option_type == _PLAY and "gust" in c.tags
        and c.board.active_doomed
        and c.board.gust_best_ko_prizes == 0 and c.board.active_ko_prizes == 0
        and c.board.stall_target_exists
        and not c.board.opp_active_condition_gift,
        weight=10, status="assumed"),
]
