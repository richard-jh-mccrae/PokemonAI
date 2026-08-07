"""The closed-form combat scorers: what an attack, a copied attack or a top-deck play is worth on this board.

Every KO / damage judgment delegates to `CombatMath` (ADR-0052) — the methods here shape its inputs and price the
result, they never re-derive damage."""
from __future__ import annotations


from dataclasses import replace

from common import board_delta
from common.deciders.facts import Board
from common.strategy.combat import _EFFICIENCY
from common.strategy.context import ENERGY_RECOVER, KO_SCORE, _ATTACK, _CARD, _TO_DECK


_RECOIL_DOOM = 100         # charge a NON-KO attack whose recoil FLIPS a safe Active doomed (Wild Press at
                           # 80 HP) — combat-scale; a KO/snipe-KO or already-doomed Active is never charged

# `_FOLLOWUP_W` is GONE (Issue #384). ADR-0061's weight on the FORCED follow-up a locking attack
# leaves behind now lives — value unchanged — as `FOLLOWUP_W` in `strategy/context.py`, imported by
# this module's star import above, because `state_value`'s terminal `next_turn_cost` leg prices the
# same forfeited follow-up as `_lock_sequence_cost` below and two copies of one weight is what
# nothing stops drifting. A local alias was written first and DELETED on review: it preserved
# exactly the two-spellings state the move existed to end, which is the `_DENIAL_ITEM_COST` lesson
# (a rate that never meets an expression is a rate nothing stops drifting) one level up.
_LOCK_KO = 0.3             # KO-branch sub-prize variant: among equal-prize KOs keep the nuke off cooldown

_RECOVER_KO = 0.25         # KO-branch sub-prize variant: "the cheaper KO that also develops" —

_RECOVER_KO_CAP = 0.75     # capped < 1, never overrides a real prize difference (like bench-snipe)

_RESISTANCE = 30           # damage Resistance subtracts when defender resists attacker's type.
                           # Printed per-card fact, not in CSV (type only) — verified uniform -30 across 47
                           # resistant Pokémon via tools/sim/probe_resistance.py. Applied AFTER Weakness.

_SELF_RETURN_ESCAPE = 50   # per-prize CREDIT for a self-return attack (Meowth ex Tuck Tail) that bounces a
                           # DOOMED multi-prize Active to hand, denying the opponent the prize(s); non-KO
                           # branch only, so a real KO always wins (mirror of _RECOIL_DOOM, a survival credit)


class TacticalMixin:
    """The per-option combat value, over the `CombatMath` oracle."""

    def _tactical(self, obs: dict, board: Board, option: dict) -> float:
        """Closed-form combat value (Tier-0): printed damage (x2 on Weakness) vs the opponent
        Active's HP. A knockout dominates; otherwise the chip is worth its damage. A bench-snipe rider
        that KNOCKS OUT a benched Pokémon banks a full PRIZE — it is a knockout, scored KO_SCORE-class
        like any other (ADR-0022 #14, ep82749168 f62: a 120+50-snipe that finishes a benched Dreepy
        beats a 210 chip on an un-KO-able Active); a rider that only chips adds a sub-prize tiebreak. A
        game-winning KO whose forced recoil is a SIMULTANEOUS double-KO is a draw, not a win (#2)."""
        if option.get("type") != _ATTACK:
            return 0
        attack_id = option.get("attackId")
        opp = self._opp_active(obs)
        hp = (opp or {}).get("hp", 0)
        # Damage oracle (ADR-0032): prevention/W/R pierced by the attack's own ignore flags; a
        # prevented ACTIVE hit (0) no longer hides bench-snipe credit below. Context scores scalers exactly.
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
        # DELIBERATE CombatMath bypass (POC-T1's documented list): card knowledge, constant all
        # game. `PrizeRace`'s own docstring keeps per-body prize YIELD on the oracle and only the
        # RACE on the model (ADR-0052) — and every caller of this adapter passes a SYNTHETIC
        # `{"id": cid}`, which is a card question, not a board one.
        return self.combat.prize_value(poke)

    def _attached_type_counts(self, target: dict) -> dict:
        # DELIBERATE CombatMath bypass (POC-T1's documented list): pure typed arithmetic over a
        # body's own `energies`, with no other board input — so two readers cannot disagree, which
        # is the drift this track's census exists to prevent. Called with synthetic bodies.
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
        """SCOPED doom read (evolve carve-out only): the opponent's Active can ACTUALLY KO next turn —
        `active_doomed` AND their Active can afford its biggest attack NOW (count check). Deliberately
        NOT the global affordability-blind doom oracle (docs/todo/incoming-affordability.md)."""
        if not board.active_doomed:
            return False
        oa = self._opp_active(obs)
        st = self.stats.get(oa.get("id")) if (oa and self.stats) else None
        cost = getattr(st, "maxDamageCost", None) if st else None
        return cost is not None and len(oa.get("energies") or []) >= cost

    def _stadium_hp_shift(self, obs: dict, card_id, defender_stat) -> int | None:
        """How playing this Stadium MOVES the defender's rendered HP — ``delta_after − delta_now``.

        The COUNTERFACTUAL half of `board_delta.stadium_hp_delta`, which prices the Stadium already
        in play. Both readings come from that one shipped function, so the `applies_to` class test
        (`board_delta._admits`; ``stage2`` for Gravity Mountain) decides which bodies a Stadium
        reaches by the shipped predicate rather than by a second branch here. A Stadium that does not
        reach this defender therefore contributes 0 structurally.

        **A DIFFERENCE of two readings, because playing a Stadium DISPLACES the one in play** —
        *"Only one Stadium can be in play at a time—if a new one comes into play, discard the old one
        and end its effects"* (`docs/rulebook.txt` L136), which `board_delta._play`'s Stadium branch
        models. Without the subtraction, replacing an opponent's Gravity Mountain with our own would
        read as a fresh −30 when the −30 was already on the board and the true gain is 0.

        ``delta_now`` is SUBTRACTED rather than added because the engine's observation already
        renders the in-play Stadium into the body it reports: `cgpy/render.py:pokemon_dict` returns
        ``hp = p.hp + delta`` and ``maxHp = p.max_hp + delta``, never storing either (`ml_dx_2001`:
        Dragapult ex 290/290 at f172 with Gravity Mountain out, 320/320 at f181 without it). So
        ``opp_hp`` arrives with the current delta baked in and the shift is what CHANGES.

        None — *unknown, refuse* — when either reading names a clause the seam cannot price, which
        includes a defender with no `CardStat` (the `applies_to` test cannot be evaluated).

        ⚠️ **The subtraction stopped being a forward contract at Issue #433, and the change of state
        is the point.** It shipped INERT: only two cards in the pool carry an `hp_delta` clause at
        all — 1252 and 1251 — and neither could put a non-zero ``delta_now`` under a legal play.
        1252 over 1252 is not one (*"You can't play a Stadium card if a Stadium with the same name is
        already in play"*, `docs/rulebook.txt` L137, enforced at `cgpy/options.py`), and **1251
        refused**, for want of a ``basic`` resolver in `board_delta._APPLIES_TO`.

        That resolver now exists, so ``delta_now`` is LIVE: with Lively Stadium out, a Basic defender
        is rendered 30 HP above its printed maximum, and playing **any** other Stadium ends that lift.
        Measured on the shipped term — a Basic rendered at 300 with Mega Brave's 270 on the board is
        out of reach until Risky Ruins displaces the Lively, at which point the shift is −30, the bar
        falls to 270 and the play is priced KO_SCORE-class. A one-sided add would have read that
        board as 0 and missed the knockout, which is exactly the case the subtraction was written
        for before one existed."""
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
        """True when this NON-KO attack's unconditional recoil turns my currently-SAFE Active into a
        free KO for the opponent — outright self-KO (recoil >= my HP on a chip attack), or the
        post-recoil HP falls inside their next-turn reach (`_active_doomed` re-asked at hp−recoil).
        The Wild-Press survival guard: 210 self-70 is fine as a prize trade (the KO branch is never
        charged) but not as a chip that leaves an 80-HP Psychic-weak body for nothing. Stands down
        when the Active is ALREADY doomed — chipping big before it dies is right."""
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
        """Tactical CREDIT for a self-returning attack (Meowth ex Tuck Tail: "Put this Pokémon and all
        attached cards into your hand") when the Active is a DOOMED multi-prize body — bouncing it to
        hand denies the opponent the 2 (ex) / 3 (Mega ex) prizes it was about to bank, and re-arms a
        bench-drop Ability. Mirror of `_RECOIL_DOOM` but a survival CREDIT: it lives in the NON-KO
        branch only, so a real KO (scored KO_SCORE) always wins. 0 unless the attack self-returns, the
        Active is ex/megaEx, and it is doomed — so a healthy Meowth never scoops itself away for tempo."""
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
