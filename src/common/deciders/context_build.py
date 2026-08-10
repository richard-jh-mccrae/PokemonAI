"""Assembles the per-option `Context`: one option measured against the Board.

Every field is derived HERE, once, so a rung reads a named fact instead of re-walking the option dict."""
from __future__ import annotations


from common.deciders.facts import Board, Context
from common.deciders.plan_choice import _min_attack_cost
from common.strategy.combat import Budget
from common.strategy.context import (_ACTIVE, _ATTACH, _ATTACH_FROM, _ATTACKER_ROLES, _BENCH, _CARD, _DAMAGE,
                                     _ENGINE_TAGS, _EVOLVING_THREAT_DMG, _MOVE_CARD, _NUMBER, _PLAY, _SWITCH,
                                     _TO_ACTIVE, _TO_HAND, _UTILITY_TAGS, _ZONE)



class ContextMixin:
    """Builds the `Context` for one option."""

    def _context(self, obs: dict, select: dict, board: Board, option: dict) -> Context:
        state = obs.get("current") or {}
        plan = board.phase                # the DERIVED advisory phase (ADR-0040) — no rule gates on
                                          # it since the gate-ban migration; traces still record it
        cid = self._option_card_id(obs, select, option)
        roles = self._roles_of(cid)
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        card_is_line_preevo = cid is not None and cid in self._line_preevo_set()
        card_is_recognized_line_preevo = cid is not None and cid in self._recognized_line_preevo_set()
        card_is_wincon = cid is not None and cid in self._wincon_set()
        card_is_starter = bool(stat and stat.hp > 0 and not stat.evolvesFrom)
        card_is_support = bool(stat and stat.hp > 0 and (_ENGINE_TAGS & set(tags)))
        card_is_utility_body = bool(stat and stat.hp > 0 and self._is_utility_body(cid))
        card_is_top_fetch_priority = cid is not None and cid == board.top_fetch_priority_id
        card_is_top_starter = cid is not None and cid == board.top_starter_id
        card_is_redundant = cid is not None and cid in board.in_play_ids
        card_is_hand_duplicate = cid is not None and cid in board.hand_duplicate_ids
        # Energy is fungible — a second copy is always a future attach, never redundant
        fungible = bool(stat and stat.is_energy)
        card_already_in_hand = bool(select.get("context") == _TO_HAND and cid is not None
                                    and not fungible and cid in board.hand_ids)
        card_unplayable_this_turn = bool(
            select.get("context") == _TO_HAND and board.supporter_played
            and bool(stat and stat.is_supporter))
        card_chain_value = (self._chain_grab_value(board, cid, plan, obs=obs)
                            if select.get("context") == _TO_HAND and cid is not None else 0.0)
        card_spends_last_evolution_route = (
            card_chain_value > 0 and self._spends_last_evolution_route(select, board, cid))
        fetch_fills_a_need = (option.get("type") == _PLAY
                              and self._fetch_fills_a_need(board, cid, plan, obs=obs))
        fetch_target_deferred = (fetch_fills_a_need
                                 and self._fetch_target_deferred(obs, cid, board, plan))
        refresh_shuffles_deferred = (option.get("type") == _PLAY and "shuffle_hand" in tags
                                     and self._held_fetch_deferred(obs, cid, board, plan))
        target_energy = self._target_energy(obs, select, option)
        target_hp = self._target_hp(obs, select, option)
        target_is_weakest = (target_hp is not None and board.weakest_bench_hp is not None
                             and target_hp == board.weakest_bench_hp)
        target_forward_damage = self._target_forward_damage(obs, select, option)
        target_is_strongest_forward = (
            target_forward_damage is not None and board.strongest_forward_bench is not None
            and target_forward_damage == board.strongest_forward_bench
            and target_forward_damage >= _EVOLVING_THREAT_DMG)
        target_is_bench_tera = bool(select.get("context") == _DAMAGE and option.get("area") == _BENCH
                                    and stat is not None and getattr(stat, "tera", False))
        target_kos = bool(board.snipe_damage and target_hp and board.snipe_damage >= target_hp
                          and not target_is_bench_tera)   # Tera: no damage while Benched
        target_on_path = self._target_on_path(obs, select, option, board)   # Tier-3 (ADR-0040)
        bench_path_delta = self._bench_path_delta(obs, select, option, stat, board)
        bench_shortens = bench_path_delta > 0.0     # the sign; one source, no drift
        promote_on_their_path = (select.get("context") in (_TO_ACTIVE, _SWITCH)
                                 and self._promote_target_on_their_path(obs, select, option, board))
        target_rank = self._target_threat_rank(
            obs, select, option, board.read, board.posture_confidence)
        promote_target_kos = (select.get("context") == _TO_ACTIVE
                              and self._promote_target_kos(obs, select, option))
        is_best_promote_target = (
            select.get("context") in (_TO_ACTIVE, _SWITCH) and board.best_promote_slot is not None
            and option.get("playerIndex", state.get("yourIndex", 0)) == state.get("yourIndex", 0)
            and (option.get("area"), option.get("index")) == board.best_promote_slot)
        is_ko_promote_target = (
            select.get("context") in (_TO_ACTIVE, _SWITCH) and board.ko_promote_slot is not None
            and option.get("playerIndex", state.get("yourIndex", 0)) == state.get("yourIndex", 0)
            and (option.get("area"), option.get("index")) == board.ko_promote_slot)
        card_prize_value = self._prize_value({"id": cid}) if cid is not None else 1
        promote_target_can_attack = self._promote_target_can_attack(obs, select, option)
        promote_target_hits_weakness = self._promote_target_hits_weakness(obs, select, option)
        at_target = self._attach_target(obs, option)
        at_roles = self._roles_of(at_target.get("id")) if at_target else []
        # the body an attach FUNDS, at either seam: manual ATTACH (inPlayArea/inPlayIndex) or the accel
        # ATTACH_FROM recipient pick (area/index).
        fund_target = at_target
        if fund_target is None and select.get("context") == _ATTACH_FROM:
            fund_target = self._option_pokemon(obs, select, option)
        attach_target_is_utility_body = bool(
            fund_target and self._is_utility_body(fund_target.get("id")))
        at_is_line_member = bool(
            at_target and at_target.get("id") in (self._line_preevo_set() | self._wincon_set()))
        attach_target_is_priority_wincon = (
            option.get("type") == _ATTACH and board.priority_wincon_slot is not None
            and (option.get("inPlayArea"), option.get("inPlayIndex")) == board.priority_wincon_slot)
        attach_feeds_firing_accel = (
            option.get("type") == _ATTACH and option.get("inPlayArea") == _ACTIVE
            and "accel_source" in at_roles and self._attach_target_needs(at_target)
            and not board.accel_recipient_missing and not board.bench_wincon_ready)
        search_exhausted, redundant_wincon, baseless_wincon = self._search_signals(option, cid, board)
        search_unlikely = self._search_probable_whiff(option, cid, board)
        search_confirmed = self._search_confirmed_hit(option, cid, board, plan, obs=obs)
        sheds_junk, sheds_live, sheds_key = self._shed_signals(obs, option, tags, board, plan)
        refresh_miss = self._refresh_probable_miss(option, cid, tags, board, obs, plan)
        attach_from_needs = self._attach_from_target_needs(obs, select, option)
        attach_from_concentrate = (select.get("context") == _ATTACH_FROM
                                   and board.attach_from_concentrate_slot is not None
                                   and (option.get("area"), option.get("index"))
                                   == board.attach_from_concentrate_slot)   # ATTACH_FROM encodes the
                                   # recipient in area/index, not inPlayArea/inPlayIndex
        # ADR-0044 opponent-choice snipe reads (kill-switched; DAMAGE bench-target only)
        snipe_ctx = (select.get("context") == _DAMAGE and option.get("type") == _CARD
                     and option.get("area") == _BENCH)
        snipe_poke = self._option_pokemon(obs, select, option) if snipe_ctx else None
        target_is_forced_promotion = bool(
            snipe_ctx and getattr(self, "forced_promotion", False) and board.opp_active_doomed
            and board.forced_promotion_key is not None
            and snipe_poke is not None and id(snipe_poke) == board.forced_promotion_key)
        target_prize_redundant = bool(                 # off my committed path — chip here doesn't advance it
            snipe_ctx and getattr(self, "snipe_prize_redundant", False)
            and board.my_path_turns is not None and not target_on_path
            and not target_is_forced_promotion
            # A high-prize body I never need is avoided ALWAYS; a low-prize off-path body only when I
            # am not under pressure. The prize-position threshold that sat here is DELETED (ADR-0085).
            and (card_prize_value >= 2 or not board.active_doomed))
        target_promotion_mirage = bool(                # their Active dead, but NOT who they promote
            snipe_ctx and getattr(self, "forced_promotion", False) and board.opp_active_doomed
            and board.forced_promotion_key is not None and not target_is_forced_promotion)
        return Context(plan=plan, select_context=select.get("context"),
                       option_type=option.get("type"), card_id=cid, option_area=option.get("area"),
                       attach_target_area=option.get("inPlayArea"), attach_target_roles=at_roles,
                       attach_target_needs=self._attach_target_needs(at_target),
                       attach_is_energy=self._attach_is_energy(stat),
                       attach_target_is_utility_body=attach_target_is_utility_body,
                       attach_target_under_max=self._attach_target_under_max(at_target),
                       attach_target_is_priority_wincon=attach_target_is_priority_wincon,
                       attach_fuels_dormant_ability=self._attach_fuels_dormant_ability(stat, at_target),
                                  attach_feeds_firing_accel=attach_feeds_firing_accel,
                       attach_target_is_line_member=at_is_line_member,
                       attach_target_is_draw_engine=self._is_draw_engine_body((at_target or {}).get("id")),
                       attach_from_target_needs=attach_from_needs,
                       attach_from_target_is_concentrate=attach_from_concentrate,
                       card_is_line_preevo=card_is_line_preevo, card_is_wincon=card_is_wincon,
                       card_is_recognized_line_preevo=card_is_recognized_line_preevo,
                       card_forward_payoff_prize=self.combat.forward_line_prize(cid)[0],
                       card_evolution_baseless=self._evolution_baseless(obs, cid),
                       card_base_unreachable=self._card_base_unreachable(obs, cid, board),
                       card_is_starter=card_is_starter, card_is_support=card_is_support,
                       card_is_utility_body=card_is_utility_body,
                       card_is_top_fetch_priority=card_is_top_fetch_priority,
                       card_is_top_starter=card_is_top_starter,
                       card_is_redundant=card_is_redundant,
                       card_is_hand_duplicate=card_is_hand_duplicate,
                       card_already_in_hand=card_already_in_hand,
                       card_unplayable_this_turn=card_unplayable_this_turn,
                       card_chain_value=card_chain_value,
                       card_spends_last_evolution_route=card_spends_last_evolution_route,
                       fetch_fills_a_need=fetch_fills_a_need,
                       fetch_target_deferred=fetch_target_deferred,
                       refresh_shuffles_deferred_fetch=refresh_shuffles_deferred,
                       target_energy=target_energy, target_is_threat=bool(target_energy),
                       target_hp=target_hp, target_is_weakest=target_is_weakest,
                       target_is_strongest_forward=target_is_strongest_forward,
                       target_forward_form_in_play=self._target_forward_form_in_play(obs, select, option),
                       target_forward_damage=target_forward_damage,
                       target_kos=target_kos,                        target_is_bench_tera=target_is_bench_tera,
                       target_on_path=target_on_path, target_prize_redundant=target_prize_redundant,
                       target_is_forced_promotion=target_is_forced_promotion,
                       target_promotion_mirage=target_promotion_mirage,
                       bench_shortens_their_path=bench_shortens,
                       bench_path_delta=bench_path_delta,
                       promote_target_on_their_path=promote_on_their_path,
                       counter_is_best_placement=(
                           board.best_counter_slot is not None
                           and (option.get("area"), option.get("index"),
                                option.get("playerIndex")) == board.best_counter_slot),
                       counter_is_source_pick=(
                           board.best_counter_source_slot is not None
                           and (option.get("area"), option.get("index"),
                                option.get("playerIndex")) == board.best_counter_source_slot),
                       is_max_counter_move=(
                           option.get("type") == _NUMBER and board.max_counter_move_number > 0
                           and int(option.get("number", 0)) == board.max_counter_move_number),
                       evolve_body_energy=self._evolve_body_energy(obs, option),
                       promote_target_kos=promote_target_kos,
                       is_best_promote_target=is_best_promote_target,
                       is_ko_promote_target=is_ko_promote_target,
                       card_prize_value=card_prize_value,
                       promote_target_can_attack=promote_target_can_attack,
                       promote_target_hits_weakness=promote_target_hits_weakness,
                       card_stranded_evolution=(cid is not None
                                                and cid in self._stranded_evolution_set()),
                       roles=roles, tags=tags, stat=stat, board=board, params=self.strategy.params,
                       context_card_id=((select.get("contextCard") or {}).get("id")),
                       search_targets_exhausted=search_exhausted,
                       search_redundant_wincon=redundant_wincon,
                       search_baseless_wincon=baseless_wincon,
                       search_targets_unlikely=search_unlikely,
                       search_confirmed_hit=search_confirmed,
                       fetch_sheds_junk=sheds_junk, fetch_sheds_live=sheds_live,
                       fetch_sheds_key=sheds_key, refresh_probable_miss=refresh_miss)

    # Fetch doctrine (comparator, whiff/redundant signals, lookahead, greedy multi-pick) is in
    # doctrine_fetch.FetchMixin.
    def _attach_target(self, obs: dict, option: dict) -> dict | None:
        """The Pokémon an attach option puts Energy on — `inPlayArea`/`inPlayIndex`, distinct from
        `area`/`index`, which point at the Energy card in hand."""
        area, index = option.get("inPlayArea"), option.get("inPlayIndex")
        if area is None or index is None:
            return None
        state = obs.get("current") or {}
        players = state.get("players") or []
        pi = option.get("playerIndex", state.get("yourIndex", 0))
        if not (0 <= pi < len(players)) or players[pi] is None:
            return None
        cards = players[pi].get(_ZONE.get(area))
        if not cards or not (0 <= index < len(cards)) or cards[index] is None:
            return None
        return cards[index]

    def _attach_target_needs(self, target: dict | None) -> bool:
        """The attach target still needs Energy to attack (carries fewer than its cheapest cost).
        Fail-OPEN: only suppress an attach on a positive confirmation that the target is online."""
        if not target:
            return True
        have = len((target.get("energies") or []))
        return have < _min_attack_cost(self.stats, target.get("id"))

    def _is_utility_body(self, card_id: int | None) -> bool:
        """This body exists to DRAW / TUTOR / STALL, not to attack. Read from Roles and Function Tags,
        never by card id. Fail-CLOSED, so a missing tag never suppresses an attach."""
        if card_id is None:
            return False
        roles = set(self.strategy.roles.get(card_id, []))
        if roles & _ATTACKER_ROLES:
            return False
        if card_id in (self._line_preevo_set() | self._wincon_set()):
            return False
        if "engine" in roles:
            return True
        if not self.functions:
            return False
        tags = set(self.functions.tags(card_id))
        for fwd in self._forward_card_ids(card_id):
            tags |= set(self.functions.tags(fwd))
        return bool(_UTILITY_TAGS & tags)

    def _attach_is_energy(self, stat) -> bool:
        """This ATTACH option's CARD is an Energy, not a Pokémon Tool — the engine reports both through
        `OptionType.ATTACH`. Fail-OPEN (True) when the stat is unknown."""
        if stat is None:
            return True
        return not (stat is not None and stat.is_tool)

    def _attach_fuels_dormant_ability(self, energy_stat, target: dict | None) -> bool:
        """This ATTACH's typed Basic Energy is a colour the TARGET's Ability needs and the target holds
        none — the predicate behind the **Ability Fuel** channel (ADR-0069 §1). Sound-or-silent."""
        etype = getattr(energy_stat, "energyType", None) if energy_stat else None
        if etype in (None, 0) or getattr(energy_stat, "hp", 1) != 0:   # a typed Basic Energy only
            return False
        if not target:
            return False
        tst = self.stats.get(target.get("id")) if self.stats else None
        fuels = [t for t in (getattr(tst, "abilityEnergyTypes", ()) or ()) if t not in (0, None)]
        if etype not in fuels:
            return False
        return self._attached_type_counts(target).get(etype, 0) == 0

    def _in_play_attack_colors(self, me: dict) -> frozenset:
        """Non-colourless Energy types my in-play bodies' attacks require — what a fetched Basic Energy
        could be USED for now. Empty without stats (silent, never a false steer)."""
        if not self.stats:
            return frozenset()
        out = set()
        for p in ((me.get("active") or []) + (me.get("bench") or [])):
            st = self.stats.get(p.get("id")) if p else None
            for aid in (getattr(st, "attacks", ()) or ()):
                ast = self._attack_stat(aid)
                for t in (getattr(ast, "energyTypes", ()) or ()):
                    if t not in (0, None):
                        out.add(t)
        return frozenset(out)

    def _in_play_ability_fuel_colors(self, me: dict) -> frozenset:
        """Colours my in-play bodies need SOLELY to switch an Ability on — no attack cost sees these."""
        if not self.stats:
            return frozenset()
        out = set()
        for p in ((me.get("active") or []) + (me.get("bench") or [])):
            st = self.stats.get(p.get("id")) if p else None
            out.update(t for t in (getattr(st, "abilityEnergyTypes", ()) or ()) if t not in (0, None))
        return frozenset(out)

    def _in_play_unfueled_ability_colors(self, me: dict) -> frozenset:
        """`_in_play_ability_fuel_colors` restricted to bodies with NONE of that colour attached."""
        if not self.stats:
            return frozenset()
        out = set()
        for p in ((me.get("active") or []) + (me.get("bench") or [])):
            st = self.stats.get(p.get("id")) if p else None
            fuels = [t for t in (getattr(st, "abilityEnergyTypes", ()) or ()) if t not in (0, None)]
            if not fuels:
                continue
            attached = self._attached_type_counts(p)
            out.update(t for t in fuels if attached.get(t, 0) == 0)
        return frozenset(out)

    def _setup_placed_ids(self, obs: dict) -> frozenset:
        """Card ids placed during PREGAME setup, off the MOVE_CARD logs: the just-placed Active shows
        only there (obs still reads `active=[None]`). Scoped to turn 0; empty off setup."""
        state = obs.get("current") or {}
        if state.get("turn"):                              # 0/None only — pregame setup window
            return frozenset()
        yi = state.get("yourIndex", 0)
        out = set()
        for lg in (obs.get("logs") or []):
            if (lg.get("type") == _MOVE_CARD and lg.get("playerIndex") == yi
                    and lg.get("toArea") in (_ACTIVE, _BENCH) and lg.get("cardId") is not None):
                out.add(lg["cardId"])
        return frozenset(out)

    def _is_draw_engine_body(self, cid) -> bool:
        """A DRAW-ENGINE body: a `draw`/`stall` tag on it or on a forward form. The CONSUMER must also
        exclude win-condition Line members, or a wincon pre-evo whose Stage 1 draws is mislabelled."""
        if not (self.functions and cid is not None):
            return False
        draw = {"draw", "stall"}
        if draw & set(self.functions.tags(cid)):
            return True
        return any(draw & set(self.functions.tags(f)) for f in self._forward_card_ids(cid))

    def _evolution_baseless(self, obs: dict, cid: int | None) -> bool:
        """Grab candidate `cid` is an EVOLUTION with no copy of its base in play or hand — a dead grab.
        SOUND: only visible own zones, and an evolved base shows as its evolution's top card."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        base_name = getattr(st, "evolvesFrom", None) if st else None
        if not base_name:
            return False
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        bodies = (me.get("active") or []) + (me.get("bench") or []) + (me.get("hand") or [])
        for b in bodies:
            bst = self.stats.get(b.get("id")) if (b and self.stats) else None
            if bst and getattr(bst, "name", None) == base_name:
                return False
        return True

    def _card_base_unreachable(self, obs: dict, cid: int | None, board) -> bool:
        """`cid` is an EVOLUTION whose base is provably ungettable — baseless AND absent from the search
        reveal or the sound deck oracle. FAIL-CLOSED when the base name resolves to no ids."""
        if not self._evolution_baseless(obs, cid):
            return False                                  # base in play/hand (or a Basic) -> reachable
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        base_name = getattr(st, "evolvesFrom", None) if st else None
        ids_for_name = getattr(self.stats, "ids_for_name", None)
        base_ids = set(ids_for_name(base_name)) if (ids_for_name and base_name) else set()
        if not base_ids:
            return False                                  # unresolvable base -> fail open (don't suppress)
        sd = board.search_deck_ids
        if sd is not None:
            return not bool(base_ids & sd)                # base absent from the search pool -> unreachable
        return all(board.deck_definitely_empty_of(bid) for bid in base_ids)   # sound oracle fallback

    def _attach_target_under_max(self, target: dict | None) -> bool:
        """`_attach_target_needs` against `maxDamageCost` instead. Fail-CLOSED on any unknown."""
        if not target:
            return False
        stat = self.stats.get(target.get("id")) if self.stats else None
        cost = getattr(stat, "maxDamageCost", None) if stat else None
        if cost is None:
            return False
        return len((target.get("energies") or [])) < cost

    def _active_arm_available(self, ma: dict | None, bench_wincon_ready: bool) -> bool:
        """Go-down-swinging is available: a real ATTACKER whose biggest attack this turn's Attach Budget
        would COMPLETE, with no ready benched wincon to retreat into. Fail-CLOSED."""
        if ma is None or not self.stats or bench_wincon_ready or self._is_utility_body(ma.get("id")):
            return False
        model = self._state_model
        body = model.mine.active if model is not None else None
        stat = self.stats.get(ma.get("id"))
        aids = (getattr(stat, "attacks", None) or ()) if stat is not None else ()
        if body is None or not aids:
            return False
        biggest = max(aids, key=self._attack_damage)
        # DELIBERATE CombatMath bypass (POC-T1's documented list): the EMPTY-Budget leg. The biggest
        # attack must NOT be payable empty but MUST be under the full budget, taken off the model below.
        if self.combat.reachable_attach(ma, biggest, budget=Budget()):
            return False                    # already armed — there is nothing left for an attach to complete
        return bool(model.mine.reachable_attach(body, biggest))

    def _immediate_preevo_in_play(self, me: dict) -> bool:
        preevos = self._payoff_immediate_preevo_set()
        if not preevos:
            return False
        return any(p and p.get("id") in preevos
                   for p in ((me.get("active") or []) + (me.get("bench") or [])))

    def _deploy_now_ids(self, me: dict, turn: int) -> frozenset:
        """Hand evolutions playable onto an ELIGIBLE in-play base THIS turn — the base must have been in
        play since last turn (rules.md §4: no evolving a body the turn it arrives, none at all on t1)."""
        if not self.stats or turn <= 1:
            return frozenset()
        eligible = {getattr(self.stats.get(b.get("id")), "name", None)
                    for b in ((me.get("active") or []) + (me.get("bench") or []))
                    if b and not b.get("appearThisTurn")}
        eligible.discard(None)
        out = set()
        for c in (me.get("hand") or []):
            cid = c.get("id") if c else None
            st = self.stats.get(cid) if cid is not None else None
            if st is not None and getattr(st, "evolvesFrom", None) in eligible:
                out.add(cid)
        return frozenset(out)

    def _attach_from_target_needs(self, obs: dict, select: dict, option: dict) -> bool:
        """`_attach_target_needs` for the ATTACH_FROM recipient pick. Fail-CLOSED on an unknown target."""
        if select.get("context") != _ATTACH_FROM:
            return False
        poke = self._option_pokemon(obs, select, option)
        if not poke:
            return False
        return len((poke.get("energies") or [])) < _min_attack_cost(self.stats, poke.get("id"))

    def _attach_from_concentrate_slot(self, me: dict, select: dict | None = None) -> tuple | None:
        """(AreaType, index) of the Line body to CONCENTRATE accelerated Energy on at an ATTACH_FROM
        select — RESTRICTED to the bodies this select offers (Aura Jab loads the Bench only)."""
        offered = None
        if select is not None:
            offered = {(o.get("area"), o.get("index")) for o in (select.get("option") or [])}
            if not offered:
                offered = None
        members = self._line_member_set()
        if not members:
            return None
        wincon = self._wincon_set()
        payoff_cost = 0
        for line in self.strategy.lines:                  # how much Energy the built body ultimately wants
            st = self.stats.get(line.payoff) if self.stats else None
            payoff_cost = max(payoff_cost, (getattr(st, "maxDamageCost", 0) or 0) if st else 0)
        best = None                                       # ((is_wincon, energy), area, index)
        for area, bodies in ((_ACTIVE, me.get("active") or []), (_BENCH, me.get("bench") or [])):
            for i, p in enumerate(bodies):
                if not p or p.get("id") not in members:
                    continue
                if offered is not None and (area, i) not in offered:
                    continue                              # this effect can't load that body
                e = len((p.get("energies") or []))
                if payoff_cost and e >= payoff_cost:      # already at payoff cost — don't over-stack it
                    continue
                # prefer the EVOLVED win-condition over a pre-evolution, then the most Energy
                rank = (p.get("id") in wincon, e)
                if best is None or rank > best[0]:
                    best = (rank, area, i)
        return (best[1], best[2]) if best else None

    def _target_energy(self, obs: dict, select: dict, option: dict) -> int | None:
        """Energy on the body a bench attack-target option points at — the snipe 'threat' signal."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        poke = self._option_pokemon(obs, select, option)
        return len(poke.get("energies") or []) if poke else None

    def _target_hp(self, obs: dict, select: dict, option: dict) -> int | None:
        """Remaining HP of the benched target — the snipe 'weakest' signal."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        poke = self._option_pokemon(obs, select, option)
        return (poke or {}).get("hp") if poke else None

    def _target_forward_damage(self, obs: dict, select: dict, option: dict) -> int | None:
        """Max damage the benched snipe target's line eventually reaches — the Evolving Threat signal
        (ADR-0020), max'd with a hand-size scaler's calculated damage. None on any gap."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        fwd = getattr(self.stats, "forward_max_damage", None)   # None if no/old provider
        if fwd is None:
            return None
        poke = self._option_pokemon(obs, select, option)
        cid = (poke or {}).get("id")
        if cid is None:
            return None
        printed = fwd(cid) or 0
        dmg = max(printed, self._forward_hand_size_damage(obs, cid))
        return dmg or None

    def _forward_hand_size_damage(self, obs: dict, cid: int | None) -> int:
        """`handSizeDamage` x the OPPONENT's hand size — "for each card in YOUR hand", theirs not mine."""
        if not self.stats or cid is None:
            return 0
        line = {cid} | self._forward_card_ids(cid)
        per_card = max((getattr(self.stats.get(i), "handSizeDamage", 0) or 0 for i in line), default=0)
        if per_card <= 0:
            return 0
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        hand = opp.get("handCount")
        if hand is None:
            hand = len(opp.get("hand") or [])
        return per_card * (hand or 0)
