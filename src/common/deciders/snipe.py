"""Snipe Relevance (ADR-0085): one `[0,1]` scalar per bench target — `tera_veto x (their_plan x my_route)` —
plus the threat ranking it reads. A PRODUCT, so nothing sums and no stand-down clause is needed."""
from __future__ import annotations


from common.deciders.facts import Board
from common.scouting.matchup_plan import BodyFacts, MatchupPlan, build_matchup_plan, derive_general_roles
from common.snipe_relevance import K as _SNIPE_RELEVANCE_K
from common.strategy.context import KO_SCORE, _BENCH, _CARD, _DAMAGE


_ENERGIZED_SNIPE_TIER = 100000  # a TIER, not a bonus: energized = imminent, so it outranks any bigger
                           # latent threat (ADR-0020). Within a tier, threat magnitude orders.

_SNIPE_THREAT_PRIZE_FLOOR = 5   # deny an ENERGIZED off-Prize-Path attacker while I hold >= this many
                           # prizes; below it I race my committed path. Ladder-tuned on 2 corrections.

_PREVENT_EX_SNIPE_BOOST = 500  # a benched line reaching `prevent_ex_damage` hard-counters my ex attacker
                           # once evolved — snipe the fragile pre-evo NOW.

_BRIEF_THREAT_BOOST = 1.25 # the Brief SHARPENER (ADR-0080 decision 2): a MULTIPLIER, never a source, so
                           # 0 x anything stays 0 and authored scouting can never promote a whiff.


class SnipeMixin:
    """How much a bench target is worth hitting, as one bounded scalar."""

    def _weakest_snipe_hp(self, obs: dict, select: dict | None) -> int | None:
        """Least HP among the benched Pokémon a DAMAGE select can snipe. None off a Damage select."""
        if not select or select.get("context") != _DAMAGE:
            return None
        hps = []
        for o in (select.get("option") or []):
            if o.get("type") == _CARD and o.get("area") == _BENCH:
                poke = self._option_pokemon(obs, select, o)
                hp = (poke or {}).get("hp") or 0
                if hp:
                    hps.append(hp)
        return min(hps) if hps else None

    def _strongest_forward_snipe(self, obs: dict, select: dict | None) -> int | None:
        """Greatest forward-evolution damage among the benched Pokémon a DAMAGE select can snipe — the
        most dangerous latent evolving threat. None off a Damage select or with no forward chain."""
        if not select or select.get("context") != _DAMAGE:
            return None
        best = None
        for o in (select.get("option") or []):
            if o.get("type") == _CARD and o.get("area") == _BENCH:
                fwd = self._target_forward_damage(obs, select, o)
                if fwd is not None and (best is None or fwd > best):
                    best = fwd
        return best

    def _target_forward_form_in_play(self, obs: dict, select: dict, option: dict) -> bool:
        """Is this bench snipe target a PRE-EVOLUTION whose evolved form is ALREADY in play (ADR-0044)?
        If so the pre-evo is redundant — chip the ready form directly. FAIL-CLOSED on any missing fact."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return False
        poke = self._option_pokemon(obs, select, option)
        cid = (poke or {}).get("id")
        fwd_ids = self._forward_card_ids(cid) if cid is not None else frozenset()
        if not fwd_ids:
            return False
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        opp_ids = {p.get("id") for p in ((opp.get("active") or []) + (opp.get("bench") or [])) if p}
        return bool(fwd_ids & opp_ids)

    def _snipe_ko_available(self, opp: dict, snipe_damage: int) -> bool:
        """Does my Active's snipe rider KNOCK OUT some benched opponent body — a free prize, on which
        every POSITIONAL snipe term stands down. A benched Tera is never a KO target (it takes no damage)."""
        if not snipe_damage:
            return False
        for b in (opp.get("bench") or []):
            if not b:
                continue
            stat = self.stats.get(b.get("id")) if self.stats else None
            if stat is not None and getattr(stat, "tera", False):
                continue
            hp = b.get("hp") or 0
            if hp and snipe_damage >= hp:
                return True
        return False

    def _snipe_damage(self, obs: dict, my_active_id: int | None, select: dict | None) -> int:
        """The bench-snipe rider at a DAMAGE select — max over my Active's attacks, since the select
        carries no attackId. Bench snipes ignore Weakness/Resistance, so `rider >= HP` is the exact KO test."""
        if not select or select.get("context") != _DAMAGE:
            return 0
        stat = self.stats.get(my_active_id) if (self.stats and my_active_id is not None) else None
        if not stat:
            return 0
        return max((self.combat.rider_snipe(aid) for aid in (stat.attacks or ())), default=0)

    def _target_threat_rank(self, obs: dict, select: dict, option: dict,
                            read=None, gamma: float = 0.0) -> float | None:
        """Snipe-priority THREAT rank for a benched DAMAGE target; None off a Damage/bench option.
        Select filtering only — :meth:`_body_threat_rank` defines the ordering."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        poke = self._option_pokemon(obs, select, option)
        if (poke or {}).get("id") is None:
            return None
        return self._body_threat_rank(obs, poke, read, gamma)

    def _snipe_ko_dominator(self, ctx) -> float:
        """STRUCTURAL dominator (ADR-0085 decision 1): a bench snipe that KNOCKS OUT is a free PRIZE.
        `K x relevance` is bounded by 350, so no positional stack can ever reach `KO_SCORE` and outvote it."""
        return KO_SCORE if (self.snipe_relevance and ctx.target_kos) else 0.0

    def _snipe_tera_veto(self, ctx) -> float:
        """STRUCTURAL veto: a benched Tera takes NO damage from attacks (`docs/rules.md` §185), so a rider
        aimed there is always wasted. Orders it LAST; never REMOVES it — a forced select must still answer."""
        return -KO_SCORE if ctx.target_is_bench_tera else 0.0

    def _body_threat_rank(self, obs: dict, poke: dict, read=None, gamma: float = 0.0) -> float:
        """Select-independent threat-rank core: ranks ANY benched opponent body, so the Planner's
        `ko_key_threat` rung and the DAMAGE-select snipe share one order. 0 on a missing id/provider."""
        cid = (poke or {}).get("id")
        if cid is None:
            return 0.0
        stat = self.stats.get(cid) if self.stats else None
        own, fwd = self._threat_damage_pair(cid, stat)
        fwd = self._read_modulated_forward(cid, fwd, read, gamma)   # lever C (ADR-0026): Read-accurate forward
        rank = float(max(own, fwd))
        rank += 0.001 * own                                   # more-evolved tie-break (Drakloak>Dreepy)
        if self.functions:
            line = {cid} | self._forward_card_ids(cid)
            my_active = self.stats.get(self._my_active_id(obs)) if self.stats else None
            if (my_active and my_active.is_ex_body
                    and any("prevent_ex_damage" in self.functions.tags(i) for i in line)):
                rank += _PREVENT_EX_SNIPE_BOOST
        if poke.get("energies"):                              # energized = imminent: a higher snipe tier
            rank += _ENERGIZED_SNIPE_TIER
        return rank

    def _threat_own_damage(self, cid, stat) -> float:
        """A body's OWN biggest hit — see :meth:`_threat_damage_pair` for the two policies."""
        if not self.scaled_threat_rank:
            return float(stat.maxDamage if stat else 0)
        return float(self.combat.threat_ceiling(
            cid, context=self._opp_attack_context))

    def _threat_damage_pair(self, cid, stat) -> tuple[float, float]:
        """``(own, forward)`` damage for the threat rank. ``scaled_threat_rank`` ON prices both through
        the Damage Formula (Issue #213); OFF is the PRINTED-only read, kept as the flag's incident lever."""
        own = self._threat_own_damage(cid, stat)
        if not self.scaled_threat_rank:
            fwd_fn = getattr(self.stats, "forward_max_damage", None)
            return own, float((fwd_fn(cid) or 0) if fwd_fn is not None else 0)
        return own, float(self.combat.forward_threat_ceiling(
            cid, context=self._opp_attack_context))

    def _forward_card_ids(self, cid: int | None) -> frozenset:
        """Card ids the snipe target's evolution line evolves INTO (provider primitive; empty when no
        provider / dead-end / unknown id)."""
        fci = getattr(self.stats, "forward_card_ids", None)
        return fci(cid) if (fci is not None and cid is not None) else frozenset()

    @staticmethod
    def _read_modulated_forward(cid: int, fwd: float, read, gamma: float) -> float:
        """Lever C (ADR-0026): scale generic forward-evolution damage by the Read. Confirmed line → full;
        recognized but no such line → ×(1−γ); no Read → unchanged."""
        if not gamma or not fwd or read is None:
            return fwd
        confirmed = any(p.seen_cardId == cid for p in read.evolution_paths)
        return fwd if confirmed else fwd * (1.0 - gamma)

    def _snipe_relevance_terms(self, obs: dict, select: dict, board: Board, option: dict,
                               ctx) -> dict | None:
        """Board plumbing for Snipe Relevance (ADR-0085; `common/snipe_relevance.py` scores). None off a
        bench-DAMAGE option. `incoming` is the CEILING and `turns_to_afford` the FLOOR — split on purpose."""
        if not (self.snipe_relevance and self.stats):
            return None
        if ((select or {}).get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        body = self._option_pokemon(obs, select, option)
        if not body:
            return None
        cache = getattr(self, "_snipe_relevance_cache", None)
        if cache is None:
            cache = self._snipe_relevance_cache = {}
        key = id(body)
        if key in cache:
            return cache[key]

        from common import snipe_relevance as srel
        ma, oa = self._my_active(obs), self._opp_active(obs)
        if not ma:
            return None

        cid = body.get("id")
        # `context=` makes the Damage Formula's `per_unit x count(variable)` term visible (Issue #213);
        # without it a bench-count scaler prices at its PRINTED base, 10x low. `bodies=[body]`: THIS body.
        model = self._state_model
        if model is None:
            return None                      # no snapshot: the instrument contributes nothing
        incoming = model.theirs.incoming(ma, 1, bodies=[body], charged=None, opp_active=oa,
                                         context=self._opp_attack_context,
                                         switch_enabler=self._opp_switch_enabler())
        tta = model.theirs.turns_to_afford(body)
        # Same reason for the forward leg: the PRINTED forward index drops the scaling term outright.
        forward_damage = 0.0
        if cid is not None:
            _own, forward_damage = self._threat_damage_pair(cid, self.stats.get(cid))

        # `my_energy` is what my Active carries NOW, so `turns_to_ko` reads the attack I can AFFORD.
        rider = board.snipe_damage or 0
        hp = body.get("hp") or 0
        my_energy = len((ma.get("energies") or []))
        t_before = self.combat.turns_to_ko(ma.get("id"), my_energy, body)
        chipped = dict(body)
        chipped["hp"] = max(1, hp - 2 * rider)
        t_after = self.combat.turns_to_ko(ma.get("id"), my_energy, chipped) if (hp and rider) else None

        # ROUTE side, not threat (decision 9): `prevent_ex_damage` makes the line IMMUNE to my ex
        # attacker once evolved, so my route through it closes permanently.
        my_stat = self.stats.get(ma.get("id")) if ma.get("id") is not None else None
        prevents_my_ex = bool(
            self.functions and my_stat and getattr(my_stat, "is_ex_body", False) and cid is not None
            and any("prevent_ex_damage" in self.functions.tags(i)
                    for i in ({cid} | self._forward_card_ids(cid))))

        # Only the SIGN travels: `_BRIEF_THREAT_BOOST` supplies the magnitude, so no rate is invented
        # to map a damage-scale MatchupPlan priority into the [0,1] band (ADR-0065).
        priority = 0.0
        plan = getattr(board, "matchup_plan", None)
        if plan is not None and cid is not None:
            priority = plan.priority(cid) or 0.0

        got = srel.target_relevance(
            plan=srel.TheirPlanInputs(
                incoming_damage=incoming, turns_to_afford=tta,
                forward_damage=forward_damage,
                is_strongest_forward=bool(getattr(ctx, "target_is_strongest_forward", False)),
                forward_form_in_play=bool(getattr(ctx, "target_forward_form_in_play", False)),
                is_forced_promotion=bool(getattr(ctx, "target_is_forced_promotion", False)),
                prize_redundant=bool(getattr(ctx, "target_prize_redundant", False)),
                promotion_mirage=bool(getattr(ctx, "target_promotion_mirage", False)),
                is_tera=bool(getattr(ctx, "target_is_bench_tera", False)),
                brief_priority=priority),
            route=srel.MyRouteInputs(
                turns_to_ko_before=t_before, turns_to_ko_after=t_after,
                hp_remaining=hp, rider_damage=rider,
                prize_value=model.theirs.view_of(body).prize_value,
                prizes_needed=max(1, int(getattr(board, "my_prizes_remaining", 6) or 6)),
                prevents_my_ex=prevents_my_ex),
            brief_boost=_BRIEF_THREAT_BOOST)
        cache[key] = got
        return got

    def _snipe_relevance_tactical(self, obs: dict, select: dict, board: Board, option: dict,
                                  ctx) -> float:
        """`K x relevance`, the armed snipe target score (ADR-0085). `K = MAX_ATTACK_DAMAGE` is the
        normalizer itself, so the product lands back in DAMAGE units — never `PRIZE_DAMAGE_RATE`."""
        if board.snipe_ko_available:
            return 0.0
        got = self._snipe_relevance_terms(obs, select, board, option, ctx)
        if not got:
            return 0.0
        return _SNIPE_RELEVANCE_K * got["relevance"]

    def _snipe_brief_priority(self, obs: dict, select: dict, option: dict, plan, ctx) -> float:
        """This option's signed Brief priority; 0.0 when unbriefed. ONE owner — the tiebreak reads it for
        candidate AND peers and the two must agree exactly. ``ctx`` is REQUIRED: it gates the POSITIVE leg."""
        cid = (self._option_pokemon(obs, select, option) or {}).get("id")
        if plan is None or cid is None:
            return 0.0
        priority = float(plan.priority(cid) or 0.0)
        if priority > 0:
            from common import snipe_relevance as srel
            gated = srel.TheirPlanInputs(
                prize_redundant=bool(getattr(ctx, "target_prize_redundant", False)),
                promotion_mirage=bool(getattr(ctx, "target_promotion_mirage", False)),
                is_tera=bool(getattr(ctx, "target_is_bench_tera", False))).brief_boost_gated()
            if gated:
                return 0.0
        return priority

    def _snipe_brief_peers(self, obs: dict, select: dict, board: Board) -> list[tuple[float, float]]:
        """``[(relevance, brief_priority)]`` per bench target, once per decision. Read off the SELECT,
        not the board: ranking against a body no option targets would invent a tie the engine never posed."""
        cached = getattr(self, "_snipe_peer_cache", None)
        if cached is not None:
            return cached
        plan = getattr(board, "matchup_plan", None)
        peers, seen = [], set()
        for o in (select.get("option") or ()):
            if o.get("type") != _CARD or o.get("area") != _BENCH:
                continue
            # DEDUPED by bench slot: a duplicate would read as a rival to the strict-maximum test and
            # silently mute the tiebreak. No corpus frame poses one today — a guard, not a fix.
            slot = o.get("index")
            if slot in seen:
                continue
            octx = self._context(obs, select, board, o)   # ONE ctx per peer: relevance and the gate
            got = self._snipe_relevance_terms(obs, select, board, o, octx)   # must read the same facts
            if got is None:
                continue
            seen.add(slot)
            peers.append((got["relevance"],
                          self._snipe_brief_priority(obs, select, o, plan, octx)))
        self._snipe_peer_cache = peers
        return peers

    def _snipe_brief_tiebreak(self, obs: dict, select: dict, board: Board, option: dict,
                              ctx) -> float:
        """The Brief Tiebreak — ordering BENEATH relevance, never a term in it (ADR-0085 Amendment H).
        Unlike `_deny_strip_delta_tiebreak` it DOES fire at zero relevance: the Brief is independent."""
        if not self.snipe_relevance or board.snipe_ko_available:
            return 0.0
        got = self._snipe_relevance_terms(obs, select, board, option, ctx)
        if got is None:
            return 0.0
        from common import snipe_relevance as srel
        mine = self._snipe_brief_priority(obs, select, option,
                                          getattr(board, "matchup_plan", None), ctx)
        return srel.brief_tiebreak(self._snipe_brief_peers(obs, select, board),
                                   got["relevance"], mine)

    def _bench_doomed_by_me(self, ma: dict | None, bench_list) -> frozenset:
        """Indices into ``bench_list`` MY Active can Knock Out this turn — the bench half of the Deny
        Relevance redundancy gate (ADR-0080 decision 1). Reach counts a distributable SPREAD, not just a rider."""
        st = self.stats.get(ma.get("id")) if (ma and self.stats) else None
        if not st:
            return frozenset()
        attached = len((ma.get("energies") or []))
        reach = max((max(self.combat.rider_snipe(aid), self.combat.rider_spread(aid))
                     for aid in (getattr(st, "attacks", ()) or ())
                     if self.combat.attack_cost(aid) <= attached), default=0)
        bench = [(b.get("id"), b.get("hp", 0)) for b in bench_list]
        return self.combat.bench_ko_indices(bench, reach)

    def _general_body_facts(self, opp: dict) -> dict:
        """``{card id: BodyFacts}`` per opponent in-play body, for the MatchupPlan's **general** tier.
        The Pilot RESOLVES, the scouting layer DERIVES. Empty without a provider (fail-CLOSED, ADR-0067)."""
        if not opp:
            return {}
        facts = {}
        for p in (opp.get("active") or []) + (opp.get("bench") or []):
            cid = (p or {}).get("id")
            if cid is None or cid in facts:
                continue
            tags = frozenset(self.functions.tags(cid)) if self.functions else frozenset()
            stat = self.stats.get(cid) if self.stats else None
            # The ONE home for "how hard does this body hit, now and once evolved", so the derived
            # `attacker` / `fragile_preevo` split cannot disagree with the snipe/Planner threat order.
            own, fwd = self._threat_damage_pair(cid, stat)
            facts[cid] = BodyFacts(
                tags=tags,
                # `_prize_value` is the ONE adapter for KO yield (ADR-0056) and a ruled POC-T1 bypass:
                # prize yield is CARD knowledge, constant all game, so it stays on the oracle.
                prize_value=self._prize_value(p),
                own_damage=own, forward_damage=fwd,
                damage_boost=int(getattr(stat, "damageBoost", 0) or 0),
                grants_free_retreat=bool(getattr(stat, "retreatFreeGrant", None)),
                ability_fuel=bool(getattr(stat, "abilityEnergyTypes", ()) or ()))
        return facts

    def _matchup_plan(self, opp: dict, brief_roles: dict, read, gamma: float):
        """Compose the ADR-0051 MatchupPlan — the opponent target-priority spine. Three tiers: curated
        ``brief_roles``, γ-gated ``read.targets``, then the always-on general derivation. Inert when OFF."""
        if not self.matchup_targeting:
            return MatchupPlan()
        read_roles = {t.cardId: t.role for t in (read.targets if read else [])}
        general = derive_general_roles(self._general_body_facts(opp))
        return build_matchup_plan(brief_roles=brief_roles, read_roles=read_roles,
                                  general_roles=general, gamma=gamma)
