"""The closed-form combat scorers: what an attack, a copied attack or a top-deck play is worth here.

Every KO / damage judgment delegates to `CombatMath` (ADR-0052); nothing here re-derives damage."""
from __future__ import annotations


from dataclasses import replace

from common import board_delta
from common.deciders.facts import Board
from common.strategy.combat import _EFFICIENCY
from common.strategy.context import ENERGY_RECOVER, KO_SCORE, _ATTACK, _CARD, _TO_DECK


_RECOIL_DOOM = 100         # charge a NON-KO attack whose recoil FLIPS a safe Active doomed (Wild Press at
                           # 80 HP) — combat-scale; a KO/snipe-KO or already-doomed Active is never charged

_LOCK_KO = 0.3             # KO-branch sub-prize variant: among equal-prize KOs keep the nuke off cooldown

_RECOVER_KO = 0.25         # KO-branch sub-prize variant: "the cheaper KO that also develops" —

_RECOVER_KO_CAP = 0.75     # capped < 1, never overrides a real prize difference (like bench-snipe)

_RESISTANCE = 30           # subtracted when the defender resists the attacker's type, AFTER Weakness. Not
                           # in the CSV; verified uniform across all 47 (tools/sim/probe_resistance.py).

_SELF_RETURN_ESCAPE = 50   # per-prize CREDIT for a self-return attack bouncing a DOOMED multi-prize Active
                           # to hand. Non-KO branch only, so a real KO always wins.


class TacticalMixin:
    """The per-option combat value, over the `CombatMath` oracle."""

    def _tactical(self, obs: dict, board: Board, option: dict) -> float:
        """Closed-form combat value (Tier-0). A bench-KO rider is a full PRIZE, scored KO_SCORE-class
        like any other (ADR-0022); a rider that only chips adds a sub-prize tiebreak."""
        if option.get("type") != _ATTACK:
            return 0
        attack_id = option.get("attackId")
        opp = self._opp_active(obs)
        hp = (opp or {}).get("hp", 0)
        dmg_ctx = self._my_damage_context(obs)
        if self.copy_top_value and self._is_seek_inspiration(obs, attack_id):
            copied = self._copy_top_tactical(obs, board, dmg_ctx)
            return copied if copied is not None else -KO_SCORE
        dmg = self.predicted_damage(self._my_active_id(obs), attack_id, opp, context=dmg_ctx)
        eff = _EFFICIENCY * self._attack_cost(attack_id, 0)   # cheaper of equal outcomes wins
        recover = self._recover_units(attack_id, dmg_ctx, board, obs)  # usable re-attachable fuel (Aura Jab)
        lock_cost = self._lock_sequence_cost(attack_id, board)    # damage the lock actually forfeits
        snipe_ko = self._snipe_ko_prizes(board.opp_bench, self.combat.rider_snipe(attack_id))
        spread_ko = self._spread_ko_prizes(board.opp_bench, self.combat.rider_spread(attack_id))
        bench_ko = snipe_ko + spread_ko              # direct opp-bench KO prizes (single-target rider +
                                                     # distributable spread; disjoint — no attack has both)
        if hp and dmg >= hp:
            if self._is_simultaneous_draw(board, attack_id, self._prize_value(opp)):
                return dmg - eff                            # a simultaneous double-KO is a DRAW, not a win
            bonus = bench_ko or (self._bench_snipe_bonus(board, attack_id)   # bench-KO is a full prize;
                                 + self._bench_spread_bonus(board, attack_id))  # else a sub-prize chip tiebreak
            bonus += min(_RECOVER_KO_CAP, _RECOVER_KO * recover)  # sub-prize: the KO that also develops
            bonus -= _LOCK_KO if lock_cost > 0 else 0             # sub-prize: keep the nuke off cooldown
            return KO_SCORE + self._prize_value(opp) - eff + bonus
        if bench_ko:                                        # Active survives, but a snipe rider / a
            return KO_SCORE + bench_ko - eff                # distributable spread KOs benched Pokémon — a PRIZE this turn
        race = self._race_attack_tactical(obs, board, attack_id, dmg_ctx)   # Tier-3 KO Race (ADR-0040):
        if race is not None:                                # vs a standing wall the single hit is fake
            return (race - eff + ENERGY_RECOVER * recover  # value — price the SEQUENCE (chip included,
                    - lock_cost                             # so no separate spread bonus here)
                    - (_RECOIL_DOOM if self._recoil_flips_doom(attack_id, obs, board) else 0)
                    + self._self_return_escape_credit(attack_id, board))
        if self.objectives_race:                            # honest coin pricing for RANKING (ADR-0039):
            lo = self.predicted_damage(self._my_active_id(obs), attack_id, opp, bound="min",
                                       context=dmg_ctx)
            hi = self.predicted_damage(self._my_active_id(obs), attack_id, opp, bound="max",
                                       context=dmg_ctx)
            if hi > lo:                                     # a coin/conditional CHIP ranks by its mean;
                dmg = (lo + hi) / 2                         # the KO test above and every sound path
                                                            # (Lethal floor / Incoming ceiling) untouched
        return (dmg - eff + ENERGY_RECOVER * recover - lock_cost
                - (_RECOIL_DOOM if self._recoil_flips_doom(attack_id, obs, board) else 0)
                + self._bench_spread_bonus(board, attack_id)     # a non-KO spread still chips the Bench (pre-load)
                + self._self_return_escape_credit(attack_id, board))

    def _is_seek_inspiration(self, obs: dict, attack_id) -> bool:
        active_id = self._my_active_id(obs)
        st = self.stats.get(active_id) if (active_id is not None and self.stats) else None
        if not st:
            return False
        attacks = tuple(getattr(st, "attacks", ()) or ())
        return ((active_id == 163 or getattr(st, "name", "") == "Slowking")
                and bool(attacks)
                and attack_id == attacks[0]
                and self._attack_damage(attack_id) == 0)

    def _active_has_seek_inspiration(self, obs: dict) -> bool:
        active_id = self._my_active_id(obs)
        st = self.stats.get(active_id) if (active_id is not None and self.stats) else None
        return any(self._is_seek_inspiration(obs, aid) for aid in (getattr(st, "attacks", ()) or ()))

    def _copy_top_qualifies(self, card_id: int | None) -> bool:
        st = self.stats.get(card_id) if (card_id is not None and self.stats) else None
        return bool(st is not None and getattr(st, "is_pokemon", False)
                    and not getattr(st, "is_ex_body", False))

    def _copy_top_tactical(self, obs: dict, board: Board, dmg_ctx) -> float | None:
        card_id = self._known_top_card_id(board)
        if card_id is None or not self._copy_top_qualifies(card_id):
            return None
        st = self.stats.get(card_id) if self.stats else None
        attacks = tuple(getattr(st, "attacks", ()) or ())
        if not attacks:
            return 0
        return max(self._copied_attack_tactical(obs, board, card_id, aid, dmg_ctx) for aid in attacks)

    def _copied_attack_tactical(self, obs: dict, board: Board, attacker_id: int, attack_id, dmg_ctx) -> float:
        opp = self._opp_active(obs)
        hp = (opp or {}).get("hp", 0)
        dmg = self.predicted_damage(attacker_id, attack_id, opp, context=dmg_ctx)
        recover = self._recover_units(attack_id, dmg_ctx, board, obs)
        lock_cost = self._lock_sequence_cost(attack_id, board)
        snipe_ko = self._snipe_ko_prizes(board.opp_bench, self.combat.rider_snipe(attack_id))
        spread_ko = self._spread_ko_prizes(board.opp_bench, self.combat.rider_spread(attack_id))
        bench_ko = snipe_ko + spread_ko
        if hp and dmg >= hp:
            bonus = bench_ko or (self._bench_snipe_bonus(board, attack_id)
                                 + self._bench_spread_bonus(board, attack_id))
            bonus += min(_RECOVER_KO_CAP, _RECOVER_KO * recover)
            bonus -= _LOCK_KO if lock_cost > 0 else 0
            return KO_SCORE + self._prize_value(opp) + bonus
        if bench_ko:
            return KO_SCORE + bench_ko
        return (dmg + ENERGY_RECOVER * recover - lock_cost
                + self._bench_spread_bonus(board, attack_id))

    def _top_deck_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        if (not self.copy_top_value or select.get("context") != _TO_DECK or option.get("type") != _CARD
                or not self._active_has_seek_inspiration(obs)):
            return 0
        cid = self._option_card_id(obs, select, option)
        if cid is None:
            return -KO_SCORE
        card = self._option_pokemon(obs, select, option) or {}
        serial = card.get("serial", option.get("index", 0))
        probe = replace(board, known_top=((serial, cid),))
        copied = self._copy_top_tactical(obs, probe, self._my_damage_context(obs))
        return copied if copied is not None else -KO_SCORE

    # --- KO-oracle delegates (ADR-0052): combat judgment lives in CombatMath; these wrappers
    # keep the Pilot-side signatures the mixins/doctrines call via `self`.
    def _snipe_ko_prizes(self, opp_bench, rider: int) -> int:
        return self.combat.snipe_ko_prizes(opp_bench, rider)

    def _best_ko_subset(self, items, budget: int) -> frozenset:
        return self.combat.best_ko_subset(items, budget)

    def _spread_ko_prizes(self, opp_bench, spread: int) -> int:
        return self.combat.spread_ko_prizes(opp_bench, spread)

    def _is_tera(self, card_id) -> bool:
        return self.combat.is_tera(card_id)

    def _prize_value(self, poke: dict | None) -> int:
        """Prizes a knockout yields — Mega ex 3, ex 2, else 1 (the KO oracle's read)."""
        # DELIBERATE CombatMath bypass (POC-T1's list): prize YIELD is card knowledge, constant all
        # game, so it stays on the oracle while only the RACE lives on the model (ADR-0052).
        return self.combat.prize_value(poke)

    def _attached_type_counts(self, target: dict) -> dict:
        # DELIBERATE CombatMath bypass (POC-T1's list): pure typed arithmetic over a body's own
        # `energies`, no other board input. Called with synthetic bodies.
        return self.combat.attached_type_counts(target)

    def _attack_type_payable(self, aid, target: dict | None, *, extra_type=None,
                             extra_units: int = 0, wild_units: int = 0) -> bool:
        return self.combat.attack_type_payable(aid, target, extra_type=extra_type,
                                               extra_units=extra_units, wild_units=wild_units)

    def _can_ko(self, my_stat, defender: dict | None) -> bool:
        """My Active's CHEAPEST attack KOs `defender` (the oracle's `can_ko_cheapest`; the
        card-level minCostDamage fallback is retired, ADR-0052)."""
        return self.combat.can_ko_cheapest(my_stat, defender)

    def _active_can_ko(self, ma: dict | None, oa: dict | None) -> bool:
        """My Active's best AFFORDABLE attack KOs the opp Active (backs `Board.active_can_ko`)."""
        return self.combat.can_ko_affordable(ma, oa)

    def _opp_active_can_damage_us(self, ma: dict | None, oa: dict | None) -> bool:
        """Their Active can hurt mine with what it holds NOW (the energy-strip worth read)."""
        return self.combat.can_damage(oa, ma)

    def _active_maxed_kos(self, ma: dict | None, oa: dict | None) -> bool:
        """My Active's biggest attack, fully powered, would KO theirs (the conserve-the-burst read)."""
        return self.combat.maxed_kos(ma, oa)

    def _bench_snipe_bonus(self, board: Board, attack_id) -> float:
        return self.combat.bench_snipe_bonus(board.opp_bench, attack_id)

    def _bench_spread_bonus(self, board: Board, attack_id) -> float:
        return self.combat.bench_spread_bonus(board.opp_bench, attack_id)

    def _valued_attack_types(self, cid) -> tuple:
        """The TYPED cost (per-slot EnergyType codes; 0 = colourless) of a card's biggest-damage attack
        — the payoff attack readiness is measured against. () when unknown."""
        stat = self.stats.get(cid) if self.stats else None
        if not stat or not getattr(stat, "attacks", None):
            return ()
        cands = [a for a in (self.stats.attack(aid) for aid in stat.attacks) if a is not None]
        if not cands:
            return ()
        pick = max(cands, key=lambda a: (getattr(a, "damage", 0) or 0, getattr(a, "cost", 0) or 0))
        return tuple(getattr(pick, "energyTypes", ()) or ())

    @staticmethod
    def _typed_can_pay(cost_types: tuple, have) -> bool:
        """Greedy typed affordability: a coloured cost slot needs a distinct matching-type Energy, a
        colourless slot any leftover. False for an unknown/empty cost."""
        if not cost_types:
            return False
        have = list(have)
        for t in cost_types:
            if t == 0:
                continue
            if t in have:
                have.remove(t)
            else:
                return False
        return len(have) >= sum(1 for t in cost_types if t == 0)

    def _body_doomed_affordable(self, obs: dict, board) -> bool:
        """SCOPED doom read (evolve carve-out only): `active_doomed` AND they can afford the attack NOW.
        Deliberately NOT the global affordability-blind oracle (ADR-0064)."""
        if not board.active_doomed:
            return False
        oa = self._opp_active(obs)
        st = self.stats.get(oa.get("id")) if (oa and self.stats) else None
        cost = getattr(st, "maxDamageCost", None) if st else None
        return cost is not None and len(oa.get("energies") or []) >= cost

    def _stadium_hp_shift(self, obs: dict, card_id, defender_stat) -> int | None:
        """How playing this Stadium MOVES the defender's RENDERED HP — ``delta_after − delta_now``. The
        subtraction is required: a new Stadium DISPLACES the old, and `obs` bakes the current one in."""
        current = obs.get("current") or {}
        try:
            now = board_delta.stadium_hp_delta(
                board_delta.stadium_clauses_for(current, self.combat,
                                                event=board_delta.STADIUM_STATIC,
                                                stat=defender_stat), defender_stat)
            after = board_delta.stadium_hp_delta(
                board_delta.stadium_clauses_of(self.combat, card_id,
                                               event=board_delta.STADIUM_STATIC,
                                               stat=defender_stat), defender_stat)
        except board_delta.Unmodellable:
            return None
        return after - now

    def _recoil_flips_doom(self, attack_id, obs: dict, board: Board) -> bool:
        """Does this NON-KO attack's recoil turn my currently-SAFE Active into a free KO? Stands down
        when it is ALREADY doomed — chipping big before it dies is right."""
        recoil = self.combat.rider_recoil(attack_id)
        hp = board.my_active_hp
        if recoil <= 0 or not hp or board.active_doomed:
            return False
        if recoil >= hp:                                   # a non-KO suicide: a free body, no prize
            return True
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        ma = next((p for p in (me.get("active") or []) if p), None)
        oa = next((p for p in (opp.get("active") or []) if p), None)
        if not ma:
            return False
        return bool(self._active_doomed(dict(ma, hp=hp - recoil), oa, opp))

    def _self_return_escape_credit(self, attack_id, board: Board) -> float:
        """CREDIT for a self-returning attack when the Active is a DOOMED multi-prize body — bouncing it
        denies the prizes. NON-KO branch only, so a real KO always wins."""
        st = self._attack_stat(attack_id)
        if not (st and getattr(st, "selfReturn", False)) or not board.active_doomed:
            return 0
        active = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        if not active or not active.is_ex_body:
            return 0
        return _SELF_RETURN_ESCAPE * active.prize_value

    @staticmethod
    def _known_top_card_id(board: Board) -> int | None:
        if not board.known_top:
            return None
        head = board.known_top[0]
        if isinstance(head, dict):
            cid = head.get("cardId", head.get("id"))
            return int(cid) if cid is not None else None
        if isinstance(head, (tuple, list)) and len(head) >= 2:
            return int(head[1])
        if isinstance(head, int):
            return head
        return None
