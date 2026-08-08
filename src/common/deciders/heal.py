"""Healing and damage-counter placement: which body a heal insures, which slot takes the next counter, what a bounce costs.

Counter placement is a SEQUENTIAL greedy — the engine re-asks per counter with the updated board."""
from __future__ import annotations


from collections import Counter

from common.deciders.facts import Board
from common.strategy.combat import CURRENT_FORMS_ONLY, UNCHARGED
from common.strategy.context import (_ACTIVE, _BENCH, _CARD, _DAMAGE_COUNTER, _DAMAGE_COUNTER_ANY, _HEAL, _NUMBER,
                                     _REMOVE_DAMAGE_COUNTER, _REMOVE_DAMAGE_COUNTER_COUNT)



class HealMixin:
    """Heals, counter placement and the counter-mover's source/amount picks."""

    def _best_counter_slot(self, obs: dict, select: dict) -> tuple | None:
        """The opponent Pokémon to place THIS counter on (area, index, playerIndex): a KO-set member closest to
        dying, else the lowest-remaining-HP target. Serves ctx 14 and a counter-mover's ctx 13 ADD."""
        if select.get("context") not in (_DAMAGE_COUNTER_ANY, _DAMAGE_COUNTER):
            return None
        yi = (obs.get("current") or {}).get("yourIndex", 0)
        rem = int(select.get("remainDamageCounter", 0))
        budget = rem * 10 if rem else 30      # ctx 14 carries the count; a counter-mover (ctx 13) -> up to 3
        cands = []                                                  # (option, hp, prize)
        for o in (select.get("option") or []):
            if o.get("type") != _CARD or o.get("playerIndex") == yi:   # opponent-owned targets only
                continue
            poke = self._option_pokemon(obs, select, o)
            hp = (poke or {}).get("hp")
            if not poke or not hp:
                continue
            if o.get("area") == _BENCH and self._is_tera(poke.get("id")):
                continue                                            # a benched Tera takes no damage
            cands.append((o, hp, self._prize_value({"id": poke.get("id")})))
        if not cands:
            return None
        subset = self._best_ko_subset([(hp, pv) for _, hp, pv in cands], budget)
        if subset:
            o = min((cands[i] for i in subset), key=lambda c: c[1])[0]   # finish the closest-to-dying
        else:
            o = min(cands, key=lambda c: (c[1], -c[2]))[0]               # pre-load: lowest HP, tie higher prize
        return (o.get("area"), o.get("index"), o.get("playerIndex"))

    def _best_counter_source_slot(self, obs: dict, select: dict) -> tuple | None:
        """At a REMOVE_DAMAGE_COUNTER (ctx 16) source select, OUR MOST-DAMAGED body — the biggest heal.
        Returns (area, index, playerIndex), or None off ctx 16 / nothing damaged."""
        if select.get("context") != _REMOVE_DAMAGE_COUNTER:
            return None
        yi = (obs.get("current") or {}).get("yourIndex", 0)
        best, best_dmg = None, 0
        for o in (select.get("option") or []):
            if o.get("type") != _CARD or o.get("playerIndex") != yi:   # our own bodies only
                continue
            poke = self._option_pokemon(obs, select, o)
            if not poke:
                continue
            dmg = int(poke.get("maxHp") or 0) - int(poke.get("hp") or 0)   # damage counters on it
            if dmg > best_dmg:
                best, best_dmg = (o.get("area"), o.get("index"), o.get("playerIndex")), dmg
        return best

    def _heal_target_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """Which of my Pokémon a heal heals (ctx 17): ``survival_gain − bounce_cost``. A tactical, so
        `_order_key`'s tie-break survives; NOT ctx-16's most-damaged rule, which can't see the bounce rider."""
        if (select or {}).get("context") != _HEAL or option.get("type") != _CARD:
            return 0.0
        state = obs.get("current") or {}
        yi = state.get("yourIndex", 0)
        if option.get("playerIndex", yi) != yi:
            return 0.0                                # a heal only ever reaches MY own bodies
        cid = ((select or {}).get("effect") or {}).get("id")
        body = self._option_pokemon(obs, select, option)
        stat = self.stats.get(body.get("id")) if (self.stats and body) else None
        if cid is None or not body or stat is None or not self._state_model:
            return 0.0
        is_active = option.get("area") == _ACTIVE
        attached = len(body.get("energies") or [])
        attach_units = (0 if board.energy_attached
                        else self._best_hand_attach_units(board.hand_ids, stat))
        # The restore ceiling is the BODY's `maxHp`, not the card's printed HP: a Hero's Cape (+100) puts a
        # 330-HP Mega Starmie ex on 430, and `amount: "all"` heals to that.
        cand = self._heal_body_candidate(cid, stat, is_active=is_active,
                                         cur_hp=int(body.get("hp") or 0),
                                         attached=attached, attach_units=attach_units,
                                         max_hp=int(body.get("maxHp") or 0) or None)
        if cand is None:
            return 0.0                                # unreadable target: 0.0, never a guess (R3)
        healed_hp, energy_total = cand
        # `attach_units` is threaded rather than re-derived: the bounce leg needs the SAME manual attach the
        # candidate was priced against.
        return (self._heal_survival_gain(obs, body, stat, cid, healed_hp, is_active=is_active)
                - self._heal_bounce_cost(obs, body, energy_total, attach_units,
                                         is_active=is_active))

    def _heal_survival_gain(self, obs: dict, body: dict, stat, cid,
                            healed_hp: int, *, is_active: bool) -> float:
        """What healing ``body`` to ``healed_hp`` BUYS, in damage: prizes the KO would have handed them (only
        when doom actually flips) plus ``min(restored, reach)``. `UNCHARGED` — the doom policy, named."""
        from common.currency import prize_to_damage
        cur_hp = int(body.get("hp") or 0)
        reach = int(self._state_model.theirs.incoming(
            body, 1, bodies=[self._opp_active(obs)], charged=UNCHARGED,
            forward_ids=CURRENT_FORMS_ONLY, context=self._opp_attack_context,
            my_benched=not is_active))
        prizes = 0.0
        if reach >= cur_hp and self._heal_body_averts_doom(
                cid, stat, is_active=is_active, cur_hp=cur_hp, incoming=reach,
                max_hp=int(body.get("maxHp") or 0) or None):
            prizes = float(getattr(stat, "prize_value", 0) or 0)
        denied = min(max(0, int(healed_hp) - cur_hp), reach)
        return prize_to_damage(prizes) + float(denied)

    def _heal_bounce_cost(self, obs: dict, body: dict, energy_total: int, attach_units: int, *,
                          is_active: bool) -> float:
        """What healing ``body`` FORFEITS this turn, floored at 0; **0.0 for a benched body** — only the Active
        swings. ``E_after`` passes no ``body``, so post-bounce Energy is WILD: a bounce re-attaches any type."""
        if not is_active:
            return 0.0                                # only the Active swings this turn
        opp = self._opp_active(obs)
        if not (opp and opp.get("hp")):
            return 0.0
        before = self._best_affordable_damage(
            body.get("id"), len(body.get("energies") or []) + attach_units, opp, body=body,
            extra_units=attach_units)
        after = self._best_affordable_damage(body.get("id"), int(energy_total), opp)
        return max(0.0, float(before) - float(after))

    def _max_counter_move_number(self, select: dict) -> int:
        """The LARGEST count offered at a REMOVE_DAMAGE_COUNTER_COUNT (ctx 40) select; 0 off ctx 40."""
        if select.get("context") != _REMOVE_DAMAGE_COUNTER_COUNT:
            return 0
        return max((int(o.get("number", 0)) for o in (select.get("option") or [])
                    if o.get("type") == _NUMBER), default=0)

    def _heal_insures_the_last_wincon(self, cid, me: dict) -> bool:
        """Is held ``cid`` the `clutch_heal` keeping my LAST win-condition alive? The unseen-pool clause is
        load-bearing: "our last wincon" is a claim about COPIES REMAINING, not about board shape."""
        if not (self.functions and "clutch_heal" in set(self.functions.tags(cid))):
            return False
        active = next((b for b in (me.get("active") or []) if b), None)
        wincons = self._wincon_set()
        if not active or active.get("id") not in wincons:
            return False
        bench = [b for b in (me.get("bench") or []) if b]
        if any(b.get("id") in wincons for b in bench):
            return False                       # the line survives the KO
        hand = [c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None]
        if any(h in wincons and self._successor_evolvable_now(me, h) for h in hand):
            return False                       # a successor lands this turn
        preevos = self._line_preevo_set()
        if not preevos:
            return False                       # a Basic wincon has no line to exhaust
        if any(b.get("id") in preevos for b in bench) or any(h in preevos for h in hand):
            return False
        from collections import Counter
        unseen = Counter(self.deck)
        unseen.subtract(self._visible_card_counts(me))
        return not any(unseen.get(pid, 0) > 0 for pid in preevos)
