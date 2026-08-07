"""Snipe Relevance (ADR-0085): one `[0,1]` scalar per bench target — `tera_veto x (their_plan x my_route)` — plus the
threat ranking it reads.

A PRODUCT of two conjunctive sides, so nothing sums and no stand-down clause is needed. That is the whole reason it
replaced six additive rungs whose bonuses summed across different bodies and out-voted a free prize."""
from __future__ import annotations


from common.deciders.facts import Board
from common.scouting.matchup_plan import BodyFacts, MatchupPlan, build_matchup_plan, derive_general_roles
from common.snipe_relevance import K as _SNIPE_RELEVANCE_K
from common.strategy.context import KO_SCORE, _BENCH, _CARD, _DAMAGE


_ENERGIZED_SNIPE_TIER = 100000  # energized benched target is strictly higher snipe TIER than any
                           # bare one — attacks SOONER (imminence), sniped before a bigger latent
                           # threat (ADR-0020). Within a tier, threat magnitude orders the choice.

_SNIPE_THREAT_PRIZE_FLOOR = 5   # deny an ENERGIZED off-Prize-Path attacker (don't treat it as prize-
                           # redundant) while I still hold >= this many prizes — early game, the imminent
                           # threat will bleed my prizes before I close; below it I race my committed path
                           # (ms f39 snipe @6 vs 83667237-107 stand-down @4, symmetric boards). Calibrated
                           # on 2 corrections — a ladder-tuned floor.

# `_HAND_SIZE_ATTACKER_BOOST` (a flat +500 for a line reaching a hand-size attacker) was DELETED by
# Issue #213. It was a proxy for a fact `_threat_damage_pair` now computes exactly, so keeping both
# would double-count one card fact; and as a flat constant keyed off a Function Tag covering exactly
# one card in the pool, it could never generalise to any other scaling attacker.
_PREVENT_EX_SNIPE_BOOST = 500  # snipe-rank boost for a benched body whose line reaches a Pokémon that
                           # PREVENTS my ex attacker's damage (`prevent_ex_damage`, e.g. Dwebble→Crustle) —
                           # hard counter once evolved, snipe the fragile pre-evo NOW (ep82225138 f46).

# `_DENIAL_ITEM_COST = 10` DELETED 2026-08-02 (Issue #261 item 2f, old Issue #212). It priced "the
# value of KEEPING the Hammer" — an Item is finite, and `_finish_turn_last` tiers a free Item ahead
# of everything, so a purely positive term could never decline one. That reasoning is GENERAL and the
# constant was not: its only consumer was gated shut for every card outside `energy_denial`, so the
# finiteness price existed for Crushing / Enhanced Hammer and for nothing else in the pool.
# `common/hold_value.py` + `_item_hold_price` now own it for every free-Item decider, off the same
# Needs assignment the refresh SHED and the discard decider already decide on. The value survives as
# `hold_value.ITEM_HOLD_FLOOR` (re-homed, deliberately not re-derived — Issue #212 scoped that out),
# and the ~1.0 worth<->damage rate it implied is now explicit as `currency.ITEM_HOLD_WORTH_RATE`.
_BRIEF_THREAT_BOOST = 1.25 # Deny Relevance's Brief SHARPENER (ADR-0080 decision 2, Issue #199): a body
                           # the matched Matchup Brief names among its `threats` is scored up, then
                           # clipped back into [0,1]. A MULTIPLIER, never a source — authored scouting
                           # sharpens a read that already works without it, which is what keeps the
                           # instrument correct against the unbriefed decks the Kaggle grader is made
                           # of (only 8 Briefs exist). It cannot promote a whiff: 0 x anything is 0,
                           # so a Brief can never make an irrelevant Energy worth taking — the same
                           # discipline `_DENIAL_UNFAVORED` follows below ("a booster must scale the
                           # oracle, never add to it", ADR-0063).


class SnipeMixin:
    """How much a bench target is worth hitting, as one bounded scalar."""

    def _weakest_snipe_hp(self, obs: dict, select: dict | None) -> int | None:
        """Least HP among the benched Pokémon a DAMAGE select can snipe — the target closest to a
        knockout (a prize). None off a Damage select. Resolves each option's target the same way
        the snipe Hypotheses do, so the owner/zone indexing matches `target_energy`."""
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
        most dangerous latent evolving threat (e.g. Riolu→Mega Lucario ex 270 over Makuhita→Hariyama
        210). None off a Damage select or when no provider/forward chain. Resolves each target the
        same way the snipe Hypotheses do, so the indexing matches `target_forward_damage`."""
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
        """True iff this bench DAMAGE snipe target is a PRE-EVOLUTION whose evolved form is ALREADY on
        the opponent's board (any of the target's `_forward_card_ids` is an opponent in-play id) — the
        ADR-0044 discriminator that keeps `snipe-the-evolving-threat` from pre-chipping a redundant
        pre-evo when the ready wincon it becomes is already present (chip the ready form directly). False
        off a bench Damage option, for a non-evolving target, or when the forward form is not yet in play
        (the developing-wincon case f75/f47). FAIL-CLOSED (returns False) on any missing fact."""
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
        """Some benched opponent body is KNOCKED OUT by my Active's snipe rider — so a free prize is on
        offer and every POSITIONAL snipe rung stands down (`snipe-for-the-ko` +60 is the only score a KO
        target should need). Gating each rung on its OWN `target_kos` was not enough: the bonuses fire on
        a DIFFERENT, non-KO body and their SUM (top-threat 30 + forced-promotion 40 + evolving-threat 45
        = 115) out-voted the prize (ms 82754241 f45, 82753102 f63). A benched Tera body is never a KO
        target — it takes no damage from attacks while Benched. 0 off a DAMAGE select, so this is False."""
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
        """The bench-snipe rider my Active's attack deals at a DAMAGE select — max over my Active's
        attacks (Jetting Blow 50). The DAMAGE select carries no attackId, but a snipe always comes
        from my Active, so its biggest snipe rider is the damage a chosen target would take. 0 off a
        Damage select / no Active / no snipe attack. Bench snipes ignore Weakness/Resistance, so this
        is the exact KO test (`rider >= target HP`)."""
        if not select or select.get("context") != _DAMAGE:
            return 0
        stat = self.stats.get(my_active_id) if (self.stats and my_active_id is not None) else None
        if not stat:
            return 0
        return max((self.combat.rider_snipe(aid) for aid in (stat.attacks or ())), default=0)

    def _target_threat_rank(self, obs: dict, select: dict, option: dict,
                            read=None, gamma: float = 0.0) -> float | None:
        """Snipe-priority THREAT rank for a benched DAMAGE target (None off a Damage/bench option).

        Higher = snipe first when no KO is available. This method only filters the select context and
        delegates to :meth:`_body_threat_rank`, which defines the ordering (own printed damage vs
        forward-evolution damage, plus the more-evolved and energized tie-breaks). The Brief's
        target-role boosts live in the MatchupPlan (ADR-0051), not here."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        poke = self._option_pokemon(obs, select, option)
        if (poke or {}).get("id") is None:
            return None
        return self._body_threat_rank(obs, poke, read, gamma)

    def _snipe_ko_dominator(self, ctx) -> float:
        """STRUCTURAL dominator: a bench snipe that KNOCKS OUT its target is a free PRIZE.

        The armed replacement for `snipe-for-the-ko`'s +60 weight, and the same move the Tera veto
        already made — from a tuner-mutable positional weight to a KO_SCORE-class Tactical term
        (ADR-0085 decision 1). The weight form is the documented blunder class: its own rationale
        records `top-threat 30 + forced-promotion 40 + evolving-threat 45 = 115` on an un-KO-able
        Grookey out-voting `60` on the KO-able Applin (`82754241-45`, and `97-vs-72` on
        `82753102-63`). Gating each rung on its own `target_kos` was not enough, because the bonuses
        fire on a DIFFERENT body and their SUM out-voted the prize.

        As a dominator that is unrepresentable: `K x relevance` is bounded by `MAX_ATTACK_DAMAGE`
        (350), so no relevance score can approach `KO_SCORE` (1000), and no future leg or Brief
        multiplier can reintroduce the misplay. `ctx.target_kos` is already false for a benched Tera
        (it takes no damage at all), so the two dominators cannot both fire on one body."""
        return KO_SCORE if (self.snipe_relevance and ctx.target_kos) else 0.0

    def _snipe_tera_veto(self, ctx) -> float:
        """STRUCTURAL veto: a benched Tera Pokémon takes NO damage from attacks at all ("prevent all
        damage done to this Pokémon by attacks", `CardStat.tera`; rules.md §185) — so aiming a snipe
        rider or a damage counter there is ALWAYS strictly wasted, on every board, forever. That is a
        CARD FACT, not a preference, so it lives in the Tactical layer (like every other KO/damage
        fact) rather than as a tunable positional weight.

        Supersedes the retired `dont-snipe-a-benched-tera` (−60 positional, `status="assumed"` — i.e.
        TUNER-MUTABLE). That weight only ever held by a 10-point margin: the reachable positional stack
        is `snipe-the-top-threat` (30) + `snipe-the-threat` (20) = 50, and adding `snipe-on-the-path`
        (12) reaches 62 and DEFEATS it. The bigger rungs are excluded elsewhere — `snipe-for-the-ko` via
        `target_kos`, `snipe-the-forced-promotion` via `_forced_promotion_key`, and
        `snipe-the-evolving-threat` only because no Tera card currently has `forward_max_damage > 0`, a
        DATA accident rather than a guarantee. One weight-tune or one new snipe rung would silently
        reintroduce the misplay (ms 81785223 f45: Wellspring Mask Ogerpon ex). A KO_SCORE-class veto
        dominates any positional stack, so nothing can outvote it.

        Orders the Tera LAST; it does NOT remove the option — when a benched Tera is the ONLY target the
        select is forced and the rider is wasted either way, so the agent must still answer. `ctx`'s
        `target_is_bench_tera` is already scoped to a bench target at a DAMAGE select."""
        return -KO_SCORE if ctx.target_is_bench_tera else 0.0

    def _body_threat_rank(self, obs: dict, poke: dict, read=None, gamma: float = 0.0) -> float:
        """The select-independent threat-rank core behind `_target_threat_rank` — rank ANY benched
        opponent body (a raw player-dict Pokémon), so the Planner's KO-the-key-threat rung can rank
        the bench at the MAIN menu with exactly the same order the DAMAGE-select snipe uses. 0 when
        the id/provider is missing (an unknowable body never outranks a known threat). This stays the
        generic (card-fact + Read-modulated) threat order.

        SURVIVES ADR-0085's deletion pass despite its snipe-flavoured constants, because the snipe
        target pick is no longer its only consumer — `planner.py:_ko_key_threat_lines` ranks the
        opponent bench with it for the ADR-0031 `ko_key_threat` Goal-Ladder rung (`planner_key_threat`,
        shipped ON), and `test_posture_read.py` covers its ADR-0026 lever-C read modulation. So
        `_ENERGIZED_SNIPE_TIER` and `_PREVENT_EX_SNIPE_BOOST` stay live here: they are snipe-NAMED but
        Planner-SHARED, and retiring them is a Planner behaviour change owing its own gate, not part
        of decision 5's scope."""
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
            if (my_active and my_active.is_ex_body                    # I attack with an ex/Mega ex …
                    and any("prevent_ex_damage" in self.functions.tags(i) for i in line)):  # … can't touch
                rank += _PREVENT_EX_SNIPE_BOOST                        # this line once evolved — kill now
        if poke.get("energies"):                              # energized = imminent: a higher snipe tier
            rank += _ENERGIZED_SNIPE_TIER
        return rank

    def _threat_own_damage(self, cid, stat) -> float:
        """A body's OWN biggest hit — see :meth:`_threat_damage_pair` for the two policies.

        Split out because ``_forced_promotion_key`` wants only this half, per benched body: asking
        for the pair there would walk each line's forward forms and throw the answer away.
        """
        if not self.scaled_threat_rank:
            return float(stat.maxDamage if stat else 0)
        return float(self.combat.threat_ceiling(
            cid, context=self._opp_attack_context))

    def _threat_damage_pair(self, cid, stat) -> tuple[float, float]:
        """``(own, forward)`` damage for the threat rank — the body's own biggest hit and the
        biggest its line evolves into.

        ``scaled_threat_rank`` ON (Issue #213) prices both through the Damage Formula against the
        live board (``CombatMath.threat_ceiling`` / ``forward_threat_ceiling``), so a scaling
        attacker is ranked by what it would actually hit for. OFF reproduces the historical
        PRINTED-only read (``CardStat.maxDamage`` + the provider's forward index) byte-for-byte,
        as the flag's incident lever.

        The printed read is why this needed fixing: it drops the Damage Formula's whole
        ``per_unit x count(variable)`` term, so Alakazam ranks at its forward index's 10 and
        Lillie's Clefairy ex at 20 — and the flat `_HAND_SIZE_ATTACKER_BOOST` that used to paper
        over the first of those covered exactly one card in the pool and nothing else.
        """
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
        """Lever C (ADR-0026): scale M0's generic forward-evolution damage by the Read. Recognized (γ>0)
        and the Read predicts THIS body's line (it is a `seen_cardId` on an evolution_path) → trust the
        signal in full; recognized but the archetype runs no such line → suppress it (×(1−γ)); unknown
        (γ=0) or no Read → the generic signal, unchanged. Suppressing denied lines is the accuracy win —
        M0 ranks by the pool's scariest descendant; the Read says whether THIS deck actually runs it."""
        if not gamma or not fwd or read is None:
            return fwd
        confirmed = any(p.seen_cardId == cid for p in read.evolution_paths)
        return fwd if confirmed else fwd * (1.0 - gamma)

    def _snipe_relevance_terms(self, obs: dict, select: dict, board: Board, option: dict,
                               ctx) -> dict | None:
        """The SNIPE instrument's value — **Snipe Relevance** (ADR-0085, Issue #188;
        `common/snipe_relevance.py` owns the scoring, this owns the board plumbing).

        Mirrors `_relevance_terms` for the sibling instrument. Returns None off a bench-DAMAGE option
        or without the stats provider, so the caller contributes nothing rather than guessing.

        Everything `their_plan` needs comes off the **Threat Clock** rather than
        `_body_threat_rank` (ADR-0045's own thesis, and ADR-0085 decision 3), which is what wins the
        self-lock and damage-scaler reads for free instead of re-deriving them. The two policies are
        SPLIT on purpose (decision 8) and must not be collapsed by a later refactor:

          * `incoming(..., charged=None)` — the CEILING, for how HARD they can hit. Under-counting
            their reach feeds them the wincon (ADR-0064's hidden-burst lesson).
          * `turns_to_afford(..., attaches_per_turn=1)` — the SLOW rules-floor clock (`rules.md` §3)
            for how SOON. It credits no ATTACH acceleration, but it does credit the line's own
            discard recursion (Issue #204), because that reload is a printed card effect outside the
            attach quota rather than a guess about their hand. Over-counting their speed only wastes
            a rider, so this leg's fail direction tolerates the extra credit.

        The route side reads `combat.turns_to_ko`, which prices the body **as an Active** against my
        real attack — the *"once it moves into active"* the user's ruling asks for — rather than
        counting rider hits, and over a TWO-chip window because a one-chip read scores `82756021-57`'s
        correct answer at zero."""
        if not (self.snipe_relevance and self.stats):
            return None
        if ((select or {}).get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None      # the incumbent rungs' exact scope — a non-CARD bench option at a DAMAGE
                             # select was scored by nothing before and must stay that way
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
        # `context=` is what makes the Damage Formula's `per_unit x count(variable)` term visible
        # (Issue #213). WITHOUT it a bench-count scaler prices at its PRINTED base — Lillie's
        # Clefairy ex reads 20 instead of the up-to-200 it actually hits for — so `imminence` and
        # `forced`, which both take this number, under-read a whole card class by 10x. Every other
        # decider-facing `incoming` call in this file passes the `_board` stash; this one must too.
        # ADR-0085 decision 7 bar 4 named exactly this case and could only be met once Issue #213's
        # combined-bench scaler family landed, which it now has.
        #
        # Off the SNAPSHOT (POC-T1). `bodies=[body]` is the point: this instrument asks what THIS ONE
        # body threatens, not what their whole board does, and `charged=None` states the CEILING
        # policy the docstring above rules for it rather than inheriting the Read's budget.
        model = self._state_model
        if model is None:
            return None                      # no snapshot: the instrument contributes nothing
        incoming = model.theirs.incoming(ma, 1, bodies=[body], charged=None, opp_active=oa,
                                         context=self._opp_attack_context,
                                         switch_enabler=self._opp_switch_enabler())
        tta = model.theirs.turns_to_afford(body)
        # The forward leg reads through Issue #213's pair accessor for the same reason and behind the
        # same `scaled_threat_rank` lever, rather than the provider's PRINTED forward index (which
        # drops the scaling term outright — it returns 0 for card 272).
        forward_damage = 0.0
        if cid is not None:
            _own, forward_damage = self._threat_damage_pair(cid, self.stats.get(cid))

        # The route side. `rider` is my repeatable bench reach; `my_energy` is what my Active carries
        # NOW, so `turns_to_ko` reads the attack I can actually afford (on `82756021-57` that is
        # Jetting Blow 120, not Nebula Beam 210 — which is why that body reads 3 turns, not 2).
        rider = board.snipe_damage or 0
        hp = body.get("hp") or 0
        my_energy = len((ma.get("energies") or []))
        t_before = self.combat.turns_to_ko(ma.get("id"), my_energy, body)
        chipped = dict(body)
        chipped["hp"] = max(1, hp - 2 * rider)
        t_after = self.combat.turns_to_ko(ma.get("id"), my_energy, chipped) if (hp and rider) else None

        # `_PREVENT_EX_SNIPE_BOOST` re-homed to the ROUTE side (decision 9): a line reaching
        # `prevent_ex_damage` does not hit me harder once evolved, it becomes IMMUNE to my ex
        # attacker — so my route through it closes permanently and this turn is the last one it exists.
        my_stat = self.stats.get(ma.get("id")) if ma.get("id") is not None else None
        prevents_my_ex = bool(
            self.functions and my_stat and getattr(my_stat, "is_ex_body", False) and cid is not None
            and any("prevent_ex_damage" in self.functions.tags(i)
                    for i in ({cid} | self._forward_card_ids(cid))))

        # The ADR-0051 MatchupPlan steer, folded in as the Brief MULTIPLIER (decision 5). Its
        # positive/negative asymmetry lives in the pure scorer, where it is testable.
        # Only the SIGN travels: `_BRIEF_THREAT_BOOST` supplies the magnitude, so no rate is invented
        # to map a damage-scale MatchupPlan priority into the [0,1] band (ADR-0065's no-fudge rule).
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
        """`K x relevance`, the armed snipe target score (ADR-0085 decisions 1-13).

        `K = MAX_ATTACK_DAMAGE`, which is the normalizer itself, so `K x relevance` lands back in
        DAMAGE units and the armed term is a strict generalisation of the band the deleted rungs
        competed in rather than a re-scaling — the identity ADR-0080 Amendment B derived for deny and
        ADR-0085 Amendment A1 adopted here. It deliberately does NOT go through
        `currency.PRIZE_DAMAGE_RATE`: relevance is a `[0,1]` scalar, not a prize-denominated value, so
        a prizes-to-damage rate would convert nothing.

        Stands down on a KO target exactly as every positional rung did — `snipe-for-the-ko` and the
        Tera veto remain STRUCTURAL dominators outside the scalar (decision 1)."""
        if board.snipe_ko_available:
            return 0.0
        got = self._snipe_relevance_terms(obs, select, board, option, ctx)
        if not got:
            return 0.0
        return _SNIPE_RELEVANCE_K * got["relevance"]

    def _snipe_brief_priority(self, obs: dict, select: dict, option: dict, plan, ctx) -> float:
        """This option's signed MatchupPlan/Brief priority, or 0.0 when nothing is briefed.

        One owner, because the tiebreak reads it twice — once for the candidate and once per peer —
        and the two readings MUST agree exactly: the comparison is `!=` against a strict maximum, so
        any drift between them silently turns a winner into a non-winner.

        **A POSITIVE priority stands down on a redundant / mirage / benched-Tera body** (Issue #395),
        through `TheirPlanInputs.brief_boost_gated()` — the ONE home for that rule, whose own
        docstring already names *"the three gates a later leg would have to remember to add itself
        to"*. This tiebreak was that later leg and it had not: the MULTIPLIER stood down on a benched
        Tera while the tiebreak still handed it a strict-maximum bonus, so a body that takes NO damage
        from attacks at all could be ordered ABOVE one that can hold the counters.

        Latent before this issue — a Brief could always have named a Tera — and reached daily by
        widening the general tier, since a derived role now lands on nearly every in-play body. The
        asymmetry is preserved exactly: a NEGATIVE (`avoid`) priority is never gated, because a
        booster must scale the oracle while a de-prioritizer may always apply.

        ``ctx`` is REQUIRED rather than defaulted: a caller that omitted it would silently skip the
        stand-down and get the pre-fix reading back, which is the shape of defect this argument
        exists to close."""
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
        """``[(relevance, brief_priority)]`` over every bench target this menu offers, once per
        decision. Peers are read off the SELECT, not off the board: a body no option targets is not a
        candidate, and ranking against it would invent a tie the engine never posed."""
        cached = getattr(self, "_snipe_peer_cache", None)
        if cached is not None:
            return cached
        plan = getattr(board, "matchup_plan", None)
        peers, seen = [], set()
        for o in (select.get("option") or ()):
            if o.get("type") != _CARD or o.get("area") != _BENCH:
                continue
            # DEDUPED by bench slot, as the deny sibling dedupes by its `(area, index)` key. Two
            # options naming the SAME body would otherwise enter twice, and the strict-maximum test
            # (`sum(p == best) > 1`) would read that duplicate as a rival and silently mute the
            # tiebreak on a board where the Brief does express a preference. No corpus DAMAGE frame
            # offers a body twice today, so this is a guard against a shape the engine may pose
            # rather than a fix for one it does.
            slot = o.get("index")
            if slot in seen:
                continue
            octx = self._context(obs, select, board, o)          # ONE ctx per peer: the relevance
            got = self._snipe_relevance_terms(obs, select, board, o, octx)   # terms and the priority
            if got is None:                                       # gate must read the same reads
                continue
            seen.add(slot)
            peers.append((got["relevance"],
                          self._snipe_brief_priority(obs, select, o, plan, octx)))
        self._snipe_peer_cache = peers
        return peers

    def _snipe_brief_tiebreak(self, obs: dict, select: dict, board: Board, option: dict,
                              ctx) -> float:
        """The **Brief Tiebreak** — ordering BENEATH relevance, never a term in it (ADR-0085
        Amendment H).

        Relevance stays the sole ranker. Among options it scores EXACTLY equal, the signed
        MatchupPlan/Brief priority orders them instead of the engine's option index. Because this is a
        comparison key rather than a value, decision 2's conjunctive product is untouched and *"either
        alone is worthless"* stays literally true.

        **Why it exists.** The deletion pass (Amendment E) turned the Brief steer from a signed ADDEND
        into a MULTIPLIER, and a multiplier cannot express a preference over a zero: where `their_plan`
        is 0 for every target the product is 0 for all of them however the Brief reads them, and the
        pick fell to option index (Amendment E3).

        ⚠️ **Diverges from `_deny_strip_delta_tiebreak` on exactly one line, deliberately.** That sibling
        guards ``not rel -> 0.0`` (*"nothing relevant — not a zero"*); this one fires at zero. The
        difference is the SOURCE of the ordering signal, not taste: `strip_shift` is DERIVED from the
        same board, so ordering by it at zero relevance would re-assert a fact relevance already priced
        at nothing, whereas the Brief priority is INDEPENDENT AUTHORED scouting — a zero `their_plan`
        says the threat clock is silent about this body, not that the Brief is wrong about it.
        Decision 2's *"authored scouting can never promote a whiff"* is preserved exactly as written:
        it protects a whiff from outranking a NON-whiff, and on an all-zero menu there is nothing of
        value to promote it above.

        **No sign guard, unlike the sibling's ``best > 0``.** A strict maximum is the whole test. That
        admits the neutral-over-``avoid`` case — two bodies tied on relevance where the Brief only
        says *don't poke the draw engine* — which a positive-only guard would drop, and which is the
        half of the ADR-0051 steer that survives on a board where nothing is imminent. It also cannot
        manufacture a preference: when every tied candidate carries the same priority (the two
        IDENTICAL Riolu on `81905522-75` both read `fragile_preevo`) there is no strict maximum and
        this returns 0.0, so decision 7's recorded miss stays missing.

        The bonus is DERIVED, never hardcoded: half the finest distinction relevance actually draws on
        THIS menu, falling back to ``1 / K`` — one damage unit — when it draws none, which is exactly
        the all-zero case. A fixed epsilon would be sized against relevance's current arithmetic and
        would rot silently the moment a term changed it (the ADR-0063 failure mode). Half of the
        smallest real gap can never overtake a difference relevance itself settled, and the result is
        a fraction of one damage unit — small enough to order a tie without swamping the other
        tacticals summed into the same option score.
        """
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
        """Indices into ``bench_list`` of benched opponent bodies MY Active can Knock Out this turn.

        The bench half of the Deny Relevance redundancy gate (ADR-0080 decision 1, step 2): *"or
        maybe its a benched pokemon that we can snipe and KO. same thing, no hammer on that specific
        pokemon."* The Active half is `board.active_can_ko` (ADR-0063's drop, which ADR-0078's
        re-audit ruled NOT subsumed and required to survive any swap).

        Reads the biggest bench REACH among the attacks my Active can currently AFFORD — the same
        `attack_cost(aid) <= attached` affordability test `can_ko_affordable` uses, and the same
        instantaneous framing as the rest of deny (the user's ruling of 2026-07-28): what we can do
        with the board as it stands, crediting no attach of our own.

        Reach is the max of the single-target snipe rider and the DISTRIBUTABLE spread total, because
        a spread reads *"in any way you like"* and so may land entirely on one body. Covering only
        the snipe rider would have left the gate blind on Dragapult ex — whose Phantom Dive is a
        6-counter spread, not a snipe — i.e. blind on one of our own three decks.

        Fail-open to the empty set without stats: an unknown attacker is not evidence that a body is
        dying, and this gate SUPPRESSES relevance, so failing open keeps the Hammer's value rather
        than inventing a corpse."""
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
        """``{card id: BodyFacts}`` for every opponent in-play body — the deck-agnostic card facts
        the MatchupPlan's **general** tier derives its roles from (`matchup_plan.BodyFacts`).

        The Pilot RESOLVES, the scouting layer DERIVES: that is `build_matchup_plan`'s existing
        contract (*"Pure — the Pilot supplies the facts"*), and keeping it means the `avoid` prize
        gate is testable at the scouting seam rather than stranded here.

        Superseded `_draw_engine_ids`, which returned bare ids and therefore could express only one
        rule and no gate. Empty when there is no provider or no opponent — no facts, no general
        claim (fail-CLOSED, ADR-0067)."""
        if not opp:
            return {}
        facts = {}
        for p in (opp.get("active") or []) + (opp.get("bench") or []):
            cid = (p or {}).get("id")
            if cid is None or cid in facts:
                continue
            tags = frozenset(self.functions.tags(cid)) if self.functions else frozenset()
            stat = self.stats.get(cid) if self.stats else None
            # `_threat_damage_pair` is the ONE home for "how hard does this body hit, now and once
            # evolved" — the same pair `_body_threat_rank` ranks the bench with, so the derived
            # `attacker` / `fragile_preevo` split cannot disagree with the threat order the snipe
            # and Planner rungs already use. It prices through the Damage Formula when
            # `scaled_threat_rank` is on, so a scaling attacker is read at what it would really hit
            # for rather than at its printed 10.
            own, fwd = self._threat_damage_pair(cid, stat)
            facts[cid] = BodyFacts(
                tags=tags,
                # `_prize_value` is the ONE adapter for "what does a KO here yield" (ADR-0056), and
                # it is the POC-T1 census's already-ruled bypass: prize yield is CARD knowledge,
                # constant all game, so it stays on the oracle while only the RACE lives on the
                # model (ADR-0052). Going through it rather than `self.combat` directly keeps this
                # off the census's undocumented list without minting a second licence.
                prize_value=self._prize_value(p),
                own_damage=own, forward_damage=fwd,
                # The three `enabler` facts, all already parsed by `card_text.py` — no new tag was
                # needed for the role, which was Issue #395 D5's finding rather than its proposal.
                damage_boost=int(getattr(stat, "damageBoost", 0) or 0),
                grants_free_retreat=bool(getattr(stat, "retreatFreeGrant", None)),
                ability_fuel=bool(getattr(stat, "abilityEnergyTypes", ()) or ()))
        return facts

    def _matchup_plan(self, opp: dict, brief_roles: dict, read, gamma: float):
        """Compose the ADR-0051 MatchupPlan for this decision — the unified opponent target-
        priority spine read by the snipe/gust consumers. Empty (inert) when the kill-switch is
        off. Curated ``brief_roles`` (already resolved to ids) is the top tier; ``read.targets``
        Intel is the γ-gated speculative tier; the general card-fact derivation is the always-on
        floor. Pure over the resolved inputs — the composition lives in
        ``matchup_plan.build_matchup_plan`` and the general tier's RULES live in
        ``matchup_plan.derive_general_roles``; this method only resolves the facts (Issue #395 D5)."""
        if not self.matchup_targeting:
            return MatchupPlan()
        read_roles = {t.cardId: t.role for t in (read.targets if read else [])}
        general = derive_general_roles(self._general_body_facts(opp))
        return build_matchup_plan(brief_roles=brief_roles, read_roles=read_roles,
                                  general_roles=general, gamma=gamma)
