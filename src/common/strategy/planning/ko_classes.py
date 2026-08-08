"""One candidate builder per KO SHAPE: evolve into it, Rare Candy into it, pump it, gust to it, retreat into it, tutor
for it, heal through it.

Each returns the same candidate record, so `_best_gamble_line` ranks shapes against each other rather than preferring
whichever it checked first."""
from __future__ import annotations


from common.strategy.context import KO_SCORE
from common.strategy.planning.turn_line import _composed_rank



class KoClassMixin:
    """Per-shape KO candidates, in one comparable form."""

    def _gamble_ko_classes(self, board, stat, ma, opp, hp: int, counts: dict, hand: list,
                           discard_basic_types: set):
        """The KO-enabling **Outcome Classes** of a refresh draw, one per attack exactly ONE Energy
        short: ``[(copies, ko_value, label, sought_ids, (sup_copies, sup_ids)), …]``. Under-counts."""
        out = []
        attached = self._attached_type_counts(ma)
        hand_ids = [c.get("id") for c in hand]
        for aid in (stat.attacks or ()):
            cost = self._attack_cost(aid)
            if cost != board.my_active_energy + 1:            # exactly one attach short
                continue
            if self.predicted_damage(board.my_active_id, aid, opp) < hp:
                continue
            ast = self._attack_stat(aid)
            types = getattr(ast, "energyTypes", ()) if ast else ()
            from collections import Counter
            need = Counter(t for t in types if t not in (0, None))
            deficit = {t: n - attached.get(t, 0) for t, n in need.items() if n - attached.get(t, 0) > 0}
            if sum(deficit.values()) > 1:
                continue                                      # more than one specific slot short
            want = next(iter(deficit), None)                  # None -> the short slot is colourless

            def _enables(cid) -> bool:
                est = self.stats.get(cid) if self.stats else None
                if not est or est.is_pokemon:
                    return False
                if not est.is_basic_energy:
                    return False                              # Basics only (a special Energy pays
                et = getattr(est, "energyType", None)         # colourless slots — under-counted, safe)
                return (et == want) if want is not None else True
            if any(_enables(cid) for cid in hand_ids):
                continue                                      # hand already holds the Basic enabler
            if any(self._fetch_reaches_slot(want, cid, counts, discard_basic_types)
                   for cid in hand_ids):                      # …or a held fetch card that reaches it:
                continue                                      # deterministic tutor line — no gamble needed
            if not board.supporter_played and any(
                    self._supporter_energy_tutor_reaches(cid, want, counts, discard_basic_types)
                    for cid in hand_ids):                     # a held Supporter tutor + a live slot is
                continue                                      # the deterministic line too (play it now)
            out_ids = {cid for cid, n in counts.items() if n > 0 and _enables(cid)}   # literal Basics
            for tid, n in counts.items():                     # WP1 closure entry points (fetch clauses)
                if n > 0 and tid not in out_ids and self._fetch_reaches_slot(
                        want, tid, counts, discard_basic_types):
                    out_ids.add(tid)
            sup_ids = sorted(tid for tid, n in counts.items() if n > 0 and tid not in out_ids
                             and self._supporter_energy_tutor_reaches(tid, want, counts,
                                                                      discard_basic_types))
            sought = sorted(out_ids)
            copies = sum(counts[cid] for cid in sought)
            if copies <= 0:
                continue
            label = f"a type-{want} Basic Energy" if want is not None else "any Basic Energy"
            out.append((copies, KO_SCORE + self._prize_value(opp), label, sought,
                        (sum(counts[t] for t in sup_ids), sup_ids)))
        return out

    def _gamble_evolution_ko_classes(self, obs, board, ma, opp, counts: dict, hand: list):
        """The **evolution-KO** Outcome Class: draw an evolution of my evolution-eligible Active,
        evolve it, and ITS attack KOs. Same 5-tuples as `_gamble_ko_classes`; errs by under-counting."""
        if ma.get("appearThisTurn"):                          # placed this turn -> can't evolve (§4 L96)
            return []
        base = self.stats.get(ma.get("id")) if (self.stats and ma.get("id") is not None) else None
        if base is None or not getattr(base, "name", None):
            return []
        energy = board.my_active_energy + 1                   # carried Energy + this turn's one attach
        hand_ids = {c.get("id") for c in hand}
        out = []
        for eid in set(self.deck):                            # DIRECT evolutions of the Active in my deck
            st = self.stats.get(eid) if self.stats else None
            if st is None or getattr(st, "evolvesFrom", None) != base.name:
                continue
            if counts.get(eid, 0) <= 0 or eid in hand_ids:    # none left to draw / in hand (deterministic)
                continue
            if self._best_affordable_ko_value(obs, board, opp, eid, energy, body=ma) <= 0:
                continue                                      # the evolved form doesn't reach a KO
            if not board.supporter_played and any(
                    self._supporter_evolution_tutor_reaches(cid, eid, counts) for cid in hand_ids):
                continue                                      # held Supporter tutor + live slot: det line
            out_ids = {eid}
            for tid, n in counts.items():                     # Item Pokémon-tutor closure (fetch clauses)
                if tid == eid or n <= 0 or tid in hand_ids:
                    continue
                tst = self.stats.get(tid) if self.stats else None
                if tst is None or not getattr(tst, "is_item", False):
                    continue                                  # Supporter tutors join only post-Item-refresh
                if self._fetch_reaches_pokemon(eid, tid, counts):   # honours no-Rule-Box / mega predicate
                    out_ids.add(tid)
            sup_ids = sorted(tid for tid, n in counts.items()
                             if n > 0 and tid != eid and tid not in out_ids and tid not in hand_ids
                             and self._supporter_evolution_tutor_reaches(tid, eid, counts))
            sought = sorted(out_ids)
            copies = sum(counts.get(cid, 0) for cid in sought)
            if copies <= 0:
                continue
            out.append((copies, KO_SCORE + self._prize_value(opp),
                        f"the evolution {st.name}", sought,
                        (sum(counts[t] for t in sup_ids), sup_ids)))
        return out

    def _gamble_pump_ko_classes(self, obs, board, stat, ma, opp, hp: int, counts: dict, hand: list):
        """The **damage-pump** KO class: my Active's best AFFORDABLE attack is short of the KO by ≤ one
        ``damageBoost`` Trainer. Gates mirror `_boost_lethal_tactical` exactly; single-copy only."""
        if board.turn <= 1:
            return []
        opp_stat = self.stats.get(opp.get("id")) if (self.stats and opp.get("id") is not None) else None
        ctx = self._damage_context(obs)
        hand_ids = {c.get("id") for c in hand}
        best_dmg = 0
        for aid in (stat.attacks or ()):
            if self._attack_cost(aid) > board.my_active_energy:
                continue                                      # not affordable with current Energy
            dmg = self.predicted_damage(board.my_active_id, aid, opp, context=ctx)
            if dmg >= hp:
                return []                                     # an affordable KO already exists — attack
            best_dmg = max(best_dmg, dmg)
        if best_dmg <= 0:
            return []

        def _crosses(bst) -> bool:
            if bst is None or not getattr(bst, "damageBoost", 0):
                return False
            if bst.damageBoostType is not None and getattr(stat, "energyType", None) != bst.damageBoostType:
                return False                                  # attacker-type gate
            if bst.damageBoostVsEx and not (opp_stat and opp_stat.is_ex_body):
                return False                                  # defender {ex} gate
            if not bst.applies_to_holder(stat):
                return False                                  # the HOLDER gate(s), asked as ONE test so
                                                              # a gate added later reaches this site
            return best_dmg < hp <= best_dmg + bst.damageBoost   # short by ≤ this one boost
        if any(_crosses(self.stats.get(cid) if self.stats else None) for cid in hand_ids):
            return []                                         # held boost crosses -> deterministic line
        item_ids = sorted(bid for bid, n in counts.items() if n > 0
                          and getattr(self.stats.get(bid), "is_item", False)
                          and _crosses(self.stats.get(bid)))
        sup_ids = sorted(bid for bid, n in counts.items() if n > 0
                         and getattr(self.stats.get(bid), "is_supporter", False)
                         and _crosses(self.stats.get(bid)))
        if not item_ids and not sup_ids:
            return []
        return [(sum(counts[b] for b in item_ids), KO_SCORE + self._prize_value(opp),
                 "a damage boost for the KO", item_ids,
                 (sum(counts[b] for b in sup_ids), sup_ids))]

    def _gamble_gust_ko_classes(self, obs, board, ma, opp_player, hand: list, counts: dict):
        """The **gust** KO class: my Active's affordable attack CAN KO a benched target once it is
        dragged up. Value = KO_SCORE + the BENCHED target's prize. Errs by under-counting."""
        best_prizes = self._gust_best_ko_prizes(ma, opp_player, board.my_active_energy)
        if best_prizes <= 0:
            return []
        hand_ids = {c.get("id") for c in hand}

        def _is_gust_trainer(cid) -> bool:
            st = self.stats.get(cid) if self.stats else None
            return bool(st and (st.is_item or st.is_supporter) and self.functions
                        and "gust" in self.functions.tags(cid))
        if any(_is_gust_trainer(cid) for cid in hand_ids):
            return []                                         # held gust -> deterministic gust-KO line
        item_ids = sorted(bid for bid, n in counts.items() if n > 0 and _is_gust_trainer(bid)
                          and getattr(self.stats.get(bid), "is_item", False))
        sup_ids = sorted(bid for bid, n in counts.items() if n > 0 and _is_gust_trainer(bid)
                         and getattr(self.stats.get(bid), "is_supporter", False))
        if not item_ids and not sup_ids:
            return []
        return [(sum(counts[b] for b in item_ids), KO_SCORE + best_prizes,
                 "a gust for the benched KO", item_ids,
                 (sum(counts[b] for b in sup_ids), sup_ids))]

    def _gamble_survival_classes(self, obs, board, me, counts: dict, hand: list):
        """The bench-empty PREDICTED-LOSS class: my Active is doomed and my Bench is EMPTY, so the KO
        LOSES the game. Outs avert it by bench-fill or heal; value = KO_SCORE, exempt from keep-value."""
        if not board.active_doomed or any(b for b in (me.get("bench") or [])):
            return []                                         # not doomed, or a bench body already exists

        def _benchable(cid) -> bool:
            st = self.stats.get(cid) if self.stats else None
            return bool(st and st.is_pokemon and not getattr(st, "evolvesFrom", None))
        hand_ids = {c.get("id") for c in hand}
        if any(_benchable(cid) for cid in hand_ids):
            return []                                         # a Basic in hand -> bench it, no gamble
        # bench-fill outs (always-live): benchable Basics + Poffin's fetch of one.
        out_ids = {cid for cid, n in counts.items() if n > 0 and _benchable(cid)}
        for tid, n in counts.items():                         # Poffin: a bench-fill fetch reaching a Basic
            if n > 0 and tid not in out_ids and any(
                    _benchable(bid) and self._fetch_reaches_pokemon(bid, tid, counts) for bid in counts):
                out_ids.add(tid)
        # heal outs: lift the doomed Active above the incoming (Item -> always-live; Supporter -> supp).
        sup_ids: set = set()
        astat = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        ma = next((p for p in (me.get("active") or []) if p), None)
        cur_hp = (ma or {}).get("hp", 0)
        incoming = board.incoming_active_damage
        if incoming and astat and ma and cur_hp < getattr(astat, "hp", 0):   # damage to heal + a threat
            if any(self._heal_averts_doom(cid, astat, cur_hp, incoming) for cid in hand_ids):
                return []                                     # a held heal averts -> deterministic line
            for hid, n in counts.items():
                if n <= 0 or hid in out_ids or not self._heal_averts_doom(hid, astat, cur_hp, incoming):
                    continue
                hst = self.stats.get(hid) if self.stats else None
                (out_ids if getattr(hst, "is_item", False) else sup_ids).add(hid)
        sought = sorted(out_ids)
        sup = sorted(sup_ids)
        copies = sum(counts[cid] for cid in sought)
        sup_copies = sum(counts[s] for s in sup)
        if copies <= 0 and sup_copies <= 0:
            return []
        return [(copies, KO_SCORE, "a Basic or heal to avoid the loss", sought, (sup_copies, sup))]

    def _heal_restriction_ok(self, restriction, astat) -> bool:
        """Can a heal clause with this ``restriction`` target my (doomed) Active ``astat``? The
        Active-spot reading of :meth:`_heal_restriction_targets`; unknown restriction fails CLOSED."""
        return self._heal_restriction_targets(restriction, astat, is_active=True)

    def _heal_restriction_targets(self, restriction, stat, *, is_active: bool) -> bool:
        """:meth:`_heal_restriction_ok` asked of ANY of my bodies (Issue #409): ``active_only`` is the
        one restriction whose answer depends on where the body stands. Unknown fails CLOSED."""
        if restriction is None:
            return True
        if restriction == "active_only":
            return is_active
        if restriction == "mega_only":
            return bool(getattr(stat, "megaEx", False))
        if restriction == "psychic_only":
            return getattr(stat, "energyType", None) == 5
        return False

    def _heal_averts_doom(self, cid, astat, cur_hp: int, incoming: int) -> bool:
        """A HEAL clause of ``cid`` lifts my doomed Active from ``cur_hp`` ABOVE the ``incoming``.
        ``each_of`` / ``amount_per`` are deliberately unread — see :meth:`_heal_candidate`."""
        return self._heal_body_averts_doom(cid, astat, is_active=True, cur_hp=cur_hp,
                                           incoming=incoming)

    def _heal_body_averts_doom(self, cid, stat, *, is_active: bool, cur_hp: int,
                               incoming: int, max_hp: int | None = None) -> bool:
        """:meth:`_heal_averts_doom` asked of ANY of my bodies (Issue #409) — the ``incoming`` a caller
        hands it makes it area-correct. ``max_hp`` is the restore ceiling, defaulting to printed HP."""
        max_hp = int(max_hp) if max_hp else (getattr(stat, "hp", 0) or 0)
        for cl in (self.effects.clauses(cid) if self.effects else ()):
            if cl.get("kind") != "heal" or cl.get("condition"):
                continue                                      # a gated heal can't be promised
            if not self._heal_restriction_targets(cl.get("restriction"), stat,
                                                  is_active=is_active):
                continue
            amount = cl.get("amount")
            healed = max_hp if amount == "all" else min(max_hp, cur_hp + int(amount or 0))
            if healed > incoming:
                return True
        return False

    def _retreat_snipe_candidate(self, me, others, target_hp: int, extra: int):
        """``active_survives`` for the best benched body that, once retreated INTO, affords a
        bench-snipe KO of the ``target_hp`` key threat — preferring one that survives the Incoming."""
        best = None
        for p in (me.get("bench") or []):
            if not p:
                continue
            if not self._affords_snipe_ko(p.get("id"), len(p.get("energies") or []) + extra, target_hp):
                continue
            my_hp = p.get("hp", 0)
            survives = bool(my_hp) and self._incoming_worst(p.get("id"), my_hp, others) < my_hp
            if best is None or survives > best:
                best = survives
        return best

    def _item_evolve_ko_candidate(self, obs, select, board, option, opp, opp_player,
                                  retreat_on_menu: bool):
        """``(prizes, active_survives)`` if an ITEM fetching an evolution into HAND composes an
        otherwise-missed KO. NARROW: single Item -> single DIRECT evolve -> attack (`_ko_line_pricing`)."""
        if not self.stats:
            return None
        item_id = self._option_card_id(obs, select, option)
        tags = self.functions.tags(item_id) if (self.functions and item_id is not None) else ()
        mega_only = "tutor_mega" in tags and "tutor_pokemon" not in tags   # the item's fetch class
        me = self._my_player(obs)
        bodies = [(p, False) for p in (me.get("active") or []) if p]
        if retreat_on_menu:
            bodies += [(p, True) for p in (me.get("bench") or []) if p]
        best = None
        for body, benched in bodies:
            if body.get("appearThisTurn"):
                continue                                  # can't evolve a body played this turn (rules.md §4)
            base = self.stats.get(body.get("id"))
            if base is None or not getattr(base, "name", None):
                continue
            energy = len(body.get("energies") or [])
            for cid in set(self.deck):
                st = self.stats.get(cid)
                if st is None or getattr(st, "evolvesFrom", None) != base.name:
                    continue
                if mega_only and not getattr(st, "megaEx", False):
                    continue                              # this item cannot fetch a non-Mega evolution
                # ADR-0074 decision 6: the presence leg is WEIGHTED, not gated — gating on
                # `deck_definitely_has` made this RANKED line inert pre-anchor. 0.0 still drops it.
                present_p = board.deck_contains_probability(cid)
                if present_p <= 0.0:
                    continue                              # provably gone — no line to rank
                # the Budget is PER TARGET BODY — its stats gate every accel clause's restriction
                budget, attack_p = self._ko_line_pricing(cid, body, benched=benched)
                if budget is None or self._best_affordable_ko_value(
                        obs, board, opp, cid, energy, bound="min", body=body,
                        attack_p=attack_p, budget=budget) <= 0:
                    continue
                my_hp = getattr(st, "hp", 0) or 0
                cand = (self._prize_value(opp),
                        bool(my_hp) and self._survives_after_ko(cid, my_hp, opp_player),
                        present_p * self._composed_line_p(obs, board, opp, cid,
                                                          energy, body, attack_p,
                                                          budget=budget))
                if best is None or _composed_rank(cand) > _composed_rank(best):
                    best = cand
        return best

    def _rare_candy_ko_candidate(self, obs, select, board, option, opp, opp_player,
                                 retreat_on_menu: bool):
        """``(prizes, active_survives)`` if RARE CANDY composes an otherwise-missed KO by SKIPPING the
        Stage 1. INERT on every shipped deck since PR #436 — forward-looking generality, not dead code."""
        if board.turn <= 1:
            return None                                   # Rare Candy is illegal on your first turn
        if not self.stats:
            return None
        me = self._my_player(obs)
        bodies = [(p, False) for p in (me.get("active") or []) if p]
        if retreat_on_menu:
            bodies += [(p, True) for p in (me.get("bench") or []) if p]
        best = None
        for body, benched in bodies:
            if body.get("appearThisTurn"):
                continue                                  # can't Rare Candy a Basic put into play this turn
            base = self.stats.get(body.get("id"))
            if base is None or not getattr(base, "name", None):
                continue
            if getattr(base, "evolvesFrom", None) is not None:
                continue                                  # Rare Candy targets a BASIC only (nothing evolves into it)
            energy = len(body.get("energies") or [])
            for cid in board.hand_ids:                    # the Stage-2 must ALREADY be in hand
                st = self.stats.get(cid)
                if st is None or not getattr(st, "stage2", False):
                    continue                              # a Stage-2 card only
                if not self._stage2_roots_at(st, base.name):
                    continue                              # its chain must root at THIS Basic (skip Stage 1)
                budget, attack_p = self._ko_line_pricing(cid, body, benched=benched)   # per-candidate
                if budget is None or self._best_affordable_ko_value(
                        obs, board, opp, cid, energy, bound="min", body=body,
                        attack_p=attack_p, budget=budget) <= 0:
                    continue
                my_hp = getattr(st, "hp", 0) or 0
                cand = (self._prize_value(opp),
                        bool(my_hp) and self._survives_after_ko(cid, my_hp, opp_player),
                        self._composed_line_p(obs, board, opp, cid, energy, body,
                                              attack_p, budget=budget))
                if best is None or _composed_rank(cand) > _composed_rank(best):
                    best = cand
        return best

    def _tutor_evolution_wins(self, obs, board, opp, body) -> bool:
        """SOUND: some DIRECT evolution of ``body`` is PROVABLY still in my deck, Salvatore-eligible
        (no Abilities), and takes a min-bound winning KO. One Salvatore = one hop; multi-hop excluded."""
        if not self.stats:
            return False
        base = self.stats.get(body.get("id"))
        if base is None or not getattr(base, "name", None):
            return False
        energy = len(body.get("energies") or [])
        extra = 1 if (board.reusable_energy_in_hand and not board.energy_attached) else 0
        for cid in set(self.deck):
            st = self.stats.get(cid)
            if (st is None or getattr(st, "evolvesFrom", None) != base.name
                    or getattr(st, "hasAbility", False)):
                continue
            if not board.deck_definitely_has(cid):
                continue
            if self._develop_wins(obs, board, opp, cid, energy + extra, body=body):
                return True
        return False

    def _retreat_ko_candidate(self, obs, board, opp, opp_player, *, supporter_spent: bool = True):
        """``(prizes, active_survives)`` for the best benched body that KOs only AFTER a retreat plus
        this turn's one attach. ``supporter_spent`` DEFAULTS TRUE and that is load-bearing (ADR-0075)."""
        me = self._my_player(obs)
        best = None                                   # (prizes, survives)
        for p in (me.get("bench") or []):
            if not p:
                continue
            energy = len(p.get("energies") or [])
            if self._best_affordable_ko_value(obs, board, opp, p.get("id"), energy, body=p) > 0:
                continue                              # retreat alone already KOs — existing hook owns it
            budget, attack_p = self._ko_line_pricing(p.get("id"), p, benched=True,
                                                     supporter_spent=supporter_spent)
            if budget is None or self._best_affordable_ko_value(
                    obs, board, opp, p.get("id"), energy, body=p,
                    budget=budget, attack_p=attack_p) <= 0:
                continue
            cand = (self._prize_value(opp), self._survives_after_ko(p.get("id"), p.get("hp", 0), opp_player))
            if best is None or cand > best:           # prefer more prizes, then survival (bool > bool)
                best = cand
        return best

    def _tutor_evolve_ko_candidate(self, obs, board, opp, opp_player, retreat_on_menu: bool):
        """``(prizes, active_survives)`` if playing an evolution-tutor Supporter (`rush_evolve`)
        unlocks a missed KO. Budget built for the FETCHED evolution, ``supporter_spent=True``."""
        me = self._my_player(obs)
        # (body, benched), not a flat list: the Budget must know where the target SITS — a
        # bench-restricted accel clause funds one and not the other (ADR-0075 decision 4)
        bodies = [(p, False) for p in (me.get("active") or []) if p]
        if retreat_on_menu:
            bodies += [(p, True) for p in (me.get("bench") or []) if p]
        best = None
        for body, benched in bodies:
            base = self.stats.get(body.get("id")) if self.stats else None
            if base is None or not getattr(base, "name", None):
                continue
            energy = len(body.get("energies") or [])
            for cid in set(self.deck):
                st = self.stats.get(cid)
                if (st is None or getattr(st, "evolvesFrom", None) != base.name
                        or getattr(st, "hasAbility", False)):
                    continue
                # ADR-0074 decision 1 forbids a THRESHOLD here: the odds ARE the weight
                present_p = board.deck_contains_probability(cid)
                if present_p <= 0.0:
                    continue                          # provably gone — nothing to rank
                budget, attack_p = self._ko_line_pricing(cid, body, benched=benched,
                                                         supporter_spent=True)
                if budget is None or self._best_affordable_ko_value(
                        obs, board, opp, cid, energy, body=body,
                        budget=budget, attack_p=attack_p) <= 0:
                    continue
                my_hp = getattr(st, "hp", 0) or 0
                cand = (self._prize_value(opp),
                        bool(my_hp) and self._survives_after_ko(cid, my_hp, opp_player),
                        present_p)
                if best is None or _composed_rank(cand) > _composed_rank(best):
                    best = cand
        return best

    def _supporter_ko_candidate(self, obs, select, board, option, opp, opp_player):
        """``(prizes, active_survives)`` if a `tutor_energy` Supporter supplies the attach a plain
        retreat→attach→KO lacks. Fires only with no reusable Energy in hand and the attach unspent."""
        if board.energy_attached or board.reusable_energy_in_hand:
            return None
        if not self._is_energy_tutor(obs, select, option):
            return None
        # The Supporter leg stays OPEN here, unlike the sibling Salvatore line: this Supporter IS the
        # Budget's own energy source, while `rush_evolve` contributes nothing and merely SPENDS the slot.
        return self._retreat_ko_candidate(obs, board, opp, opp_player, supporter_spent=False)

    def _evolve_ko_candidate(self, obs, select, board, option, opp, opp_player):
        """``(prizes, active_survives)`` if EVOLVING the Active unlocks a KO this turn. The Budget is
        built at ``benched=False`` — a bench-restricted clause must NOT fund this line (ADR-0075)."""
        evolved_id = self._option_card_id(obs, select, option)
        if evolved_id is None:
            return None
        energy = board.my_active_energy
        ma = next((p for p in (self._my_player(obs).get("active") or []) if p), None)
        budget, attack_p = self._ko_line_pricing(evolved_id, ma, benched=False,
                                                 supporter_spent=True)   # an EVOLVE spends none
        if budget is None or self._best_affordable_ko_value(
                obs, board, opp, evolved_id, energy, body=ma,
                budget=budget, attack_p=attack_p) <= 0:
            return None
        estat = self.stats.get(evolved_id) if self.stats else None
        my_hp = getattr(estat, "hp", 0) or 0          # evolved max HP — P3 engine-sim resolves damage exactly
        return (self._prize_value(opp), self._survives_after_ko(evolved_id, my_hp, opp_player))

    def _free_evolve_ko_candidate(self, obs, select, board, option, opp, opp_player,
                                  retreat_on_menu: bool):
        """``(prizes, active_survives)`` if a FREE direct-evolve of a BENCHED body unlocks a missed KO
        — the option's presence IS the legality signal. Budget at ``benched=True`` (ADR-0075)."""
        if not retreat_on_menu:
            return None                                   # a benched attacker needs the retreat to attack
        evolved_id = self._option_card_id(obs, select, option)
        if evolved_id is None:
            return None
        idx = option.get("inPlayIndex")
        bench = self._my_player(obs).get("bench") or []
        body = bench[idx] if (idx is not None and 0 <= idx < len(bench)) else None
        if body is None:
            return None
        energy = len(body.get("energies") or [])
        budget, attack_p = self._ko_line_pricing(evolved_id, body, benched=True,
                                                 supporter_spent=True)   # an EVOLVE spends none
        if budget is None or self._best_affordable_ko_value(
                obs, board, opp, evolved_id, energy, body=body,
                budget=budget, attack_p=attack_p) <= 0:
            return None
        estat = self.stats.get(evolved_id) if self.stats else None
        my_hp = getattr(estat, "hp", 0) or 0
        return (self._prize_value(opp),
                bool(my_hp) and self._survives_after_ko(evolved_id, my_hp, opp_player))
