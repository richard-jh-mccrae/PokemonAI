"""The promote/retreat decider's Pilot-side half (ADR-0100): assemble `PromoteRetreatInputs`, and choose the slot that
promotes after a KO.

The equation is `common/promote_retreat_value.py`; the retreat COST is `common/retreat_cost.py` (grant-aware, shared
with the Energy-discard target space)."""
from __future__ import annotations


from common import retreat_cost
from common.card_worth import ENERGY_TIER
from common.deciders.attach import _ATTACH_RESOURCE_TIEBREAK
from common.deciders.facts import Board
from common.deciders.plan_choice import _min_attack_cost
from common.grading import HORIZON as _HORIZON
from common.promote_retreat_value import PromoteBody, PromoteRetreatInputs, RetreatSide, promote_value
from common.strategy.combat import HARVEST_UNAVOIDABLE
from common.strategy.context import _BENCH, _MAIN, _PLAY, _RETREAT, _SWITCH, _TO_ACTIVE



class PromoteRetreatMixin:
    """Board facts for the promote/retreat decider, plus the after-KO promote slot."""

    def _promote_body(self, obs: dict, board: Board, raw: dict | None, *, draws: int = 0,
                      bench_after=None) -> PromoteBody:
        """Read ONE body into the promote/retreat decider's damage-currency view (ADR-0100 §3-§7).

        The body is measured AS THE ACTIVE — that is where a promote candidate arrives and where the
        retreating Active currently stands — so its Attach Budget is built at ``target_benched=False``
        (#137 contract hazard 1: a Budget is PER-TARGET-BODY, and the same body budgeted as benched
        vs Active can differ).

        ``bench_after`` is the Bench this body would sit on if it went there — supplied only for the
        RETREATING Active, whose `preservation` needs the bench leg. Without it the bench clock is
        pinned to the Active one, so `preservation` reads a safe ZERO rather than a phantom credit on
        a body nobody is asking about."""
        from common.state_model import BodyView
        raw = raw or {}
        model = self._state_model
        mine = model.mine if model is not None else None
        view = BodyView(raw, combat=self.combat, is_active=True)
        # CARD RULE, not a heuristic: the player going FIRST cannot attack on turn 1
        # (`docs/rules.md` §2 L71-72, rulebook L152), so a body promoted then earns NO attack yield
        # and readying it buys nothing THIS turn. `_evolve_side` gates its own `this_turn` leg on the
        # same fact; without it the equation promises damage the rules forbid and endorses a turn-1
        # pivot on the strength of it (corpus 83007714-8).
        can_swing = board.turn > 1
        reach = float(mine.best_reachable_damage(view)) if (mine is not None and can_swing) else 0.0
        opp = self._opp_player(obs) or {}
        opp_active = (model.theirs.active_raw if model is not None
                      else next((p for p in (opp.get("active") or []) if p), None))
        # Both clocks go through the SNAPSHOT (POC-T1) — no `charged=`, so each takes the Read's
        # threaded `_incoming_budget`, which is exactly the policy the bypass used to pass by hand.
        clock = dict(context=self._opp_attack_context,
                     key_ids=self._harvest_key_ids(), opp_active=opp_active,
                     switch_enabler=self._opp_switch_enabler())
        if model is None:
            # No snapshot — a board that never went through `_board()`. Both clocks then make NO
            # CLAIM, which is what `PromoteBody`'s own declared default (`HORIZON` = safe) means; a
            # model-free second clock path here is the bypass POC-T1 exists to close.
            ko_active = ko_bench = _HORIZON
        else:
            ko_active = model.theirs.turns_to_ko_me(raw, my_benched=False,
                                                    my_bench=self._my_bench_raws(obs), **clock)
            if bench_after is None:
                ko_bench = ko_active                  # not asked — `preservation` reads 0, never a
            else:                                     # phantom rescue credit
                # HARVEST READING (ADR-0071 decision 3): this is a RESCUE read — it asks what
                # retreating BUYS — so it declares UNAVOIDABLE. A benched knockout the opponent can
                # simply redirect onto another body in range denies nothing; crediting it inflates
                # every bench rescue. The 35 bench-immune Tera bodies drop out of the harvest
                # entirely (`combat._harvest_items`, verified), so their bench leg reads the full
                # horizon.
                ko_bench = model.theirs.turns_to_ko_me(raw, my_benched=True,
                                                       my_bench=list(bench_after),
                                                       reading=HARVEST_UNAVOIDABLE, **clock)
        cid = raw.get("id")
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        return PromoteBody(
            reach=reach,
            # Gated on the same card rule: the race leg is still an ATTACK claim, and it REPLACES
            # `reach` rather than adding to it, so leaving it live would re-introduce the turn-1
            # damage the line above just refused.
            wall_progress=self._promote_wall_progress(obs, board, raw) if can_swing else None,
            accel_units=self._promote_accel_units(obs, board, raw) if can_swing else 0.0,
            closure=self._promote_closure(obs, raw, draws=draws if can_swing else 0),
            prizes=self._prize_value(raw),
            ko_active=ko_active, ko_bench=ko_bench,
            tempo_step=self._promote_tempo_step(raw),
            denies_items=("item_lock" in tags and self._opp_items_live()),
            opp_prizes_remaining=board.opp_prizes_remaining,
            takes_ko=self._promote_body_kos(obs, board, raw))

    def _promote_wall_progress(self, obs: dict, board: Board, raw: dict) -> float | None:
        """ADR-0040's per-turn wall progress (``hp / t_star``) for a body promoted into a STANDING
        WALL, or None when the wall does not stand and the body's reachable damage speaks for itself
        (ADR-0100 §3a: "vs a standing wall the single hit is fake value — price the SEQUENCE").

        Scoped to THIS body rather than `board.active_can_ko`, because the question is what B faces
        after arriving. Returns None the moment B can Knock the defender Out: the KO is then the
        tactical layer's (`_promote_ko_tactical`), and the residual must not re-price it.

        Deliberately `hp / t_star` ALONE, without `_race_attack_tactical`'s incidental-chip terms:
        that chip is a tie-break between the attacks of ONE body, and importing it here would let an
        attack-choice tie-break reorder a BODY comparison."""
        from common.strategy.objectives import race_values
        if not getattr(self, "objectives_race", False):
            return None
        opp = self._opp_active(obs)
        hp = (opp or {}).get("hp", 0)
        cid = (raw or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (hp and stat and stat.attacks):
            return None
        energy = len(raw.get("energies") or [])
        table = {}
        for aid in (stat.attacks or ()):
            if self.combat.attack_cost(aid) > energy:
                continue                              # not affordable on the Energy it carries
            dmg = self.predicted_damage(cid, aid, opp)
            if dmg <= 0:
                continue
            if dmg >= hp:
                return None                           # no wall — B takes the KO, the KO layer's turf
            table[aid] = (dmg, 0)                     # chip omitted deliberately (see docstring)
        vals = race_values(table, hp)
        if not vals:
            return None
        return hp / min(t_star for t_star, _chip in vals.values())

    def _promote_accel_units(self, obs: dict, board: Board, raw: dict) -> float:
        """Energy this body's accel rider would actually attach AND a recipient can actually USE —
        the `_recover_units` count (ADR-0100 §3b).

        `max` over the body's AFFORDABLE attacks, because it commits to one attack and picks the
        best: `max` WITHIN the axis, per ADR-0069 §1. Retreating INTO Cinderace must credit what
        attacking WITH Cinderace credits, which the shipped `_DIVIDEND = 5` under-paid ~45x."""
        cid = (raw or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (stat and stat.attacks):
            return 0.0
        energy = len(raw.get("energies") or [])
        best = 0.0
        for aid in (stat.attacks or ()):
            if self.combat.attack_cost(aid) <= energy:
                best = max(best, self._recover_units(aid, {}, board, obs))
        return best

    def _promote_closure(self, obs: dict, raw: dict, *, draws: int) -> float:
        """``max`` over attacks of ``damage(a) x [readiness_p(a | enabler) - readiness_p(a)]`` — the
        odds that THIS turn's dig readies an unready body, priced as probability x the damage it
        unlocks (ADR-0100 §5).

        `_evolve_income_delta` is the wiring this copies, so it inherits that path's fixes rather
        than re-earning them — notably `CountTriple.expected` rather than the raw triple, whose
        absence silently zeroed three of ADR-0070's terms on every board (#167).

        Three sub-rulings hold here. PER ATTACK, never ``attack_id=None`` (which asks the famine
        question across ALL attacks — right for a boolean, wrong for a magnitude, since the reachable
        attack may be the cheap one while the biggest damage belongs to the dear one). ONE Budget per
        target body, at this site's ``target_benched``. And the draw window is SITE-DEPENDENT: the
        caller passes ``draws=0`` at a forced promote, where no play window remains at all.

        Fail-CLOSED at 0.0 throughout (ADR-0067): no dig, no enabler that would still pay, or an
        already-ready body all earn nothing rather than bare draw odds. A body that ALREADY reaches
        has ``Δ = 0``, which is what stops closure double-crediting readiness."""
        from common.state_model import BodyView
        model = self._state_model
        mine = model.mine if model is not None else None
        cid = (raw or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if draws <= 0 or mine is None or not (raw and stat and stat.attacks):
            return 0.0
        view = BodyView(raw, combat=self.combat, is_active=True)
        pool = mine.deck_count
        best = 0.0
        for aid in (stat.attacks or ()):
            dmg = float(self.combat.attack_damage(aid) or 0)
            if dmg <= 0:
                continue
            base = mine.readiness_p(view, aid)
            if base >= 1.0:
                continue                              # already ready — no double credit
            for etype, count in (mine.deck_energy_counts or {}).items():
                # `expected` is the leg: a dig's odds ARE an estimate, and passing the CountTriple
                # itself raises into `draw_hit_probability`'s "bad input -> 0.0" guard (#167).
                copies = int(getattr(count, "expected", count) or 0)
                # DELIBERATE CombatMath bypass (POC-T1's documented list;
                # `test_combat_bypass_census`): a HYPOTHETICAL enabler Budget. Every argument is a
                # model read, but the TARGET is a form the board does not carry in this
                # configuration, and the model's route builds a Budget for a body it holds.
                # Inventing a `MySide` method per hypothetical would move the assembly, not remove it.
                enabler = self.combat.attach_budget(
                    raw, mine.hand_ids, energy_attached=mine.energy_attached,
                    supporter_played=mine.supporter_played,
                    deck_energy_types=mine.deck_energy_types,
                    hand_energy_types=frozenset(mine.hand_energy_types) | {etype},
                    discard_energy_counts=mine.discard_energy_counts,
                    target_benched=False,             # it is being promoted INTO the Active Spot
                    more_prizes_than_opp=mine.more_prizes_than_opp)
                p = mine.readiness_p(view, aid, enabler_budget=enabler, copies=copies,
                                     pool=pool, draws=draws)
                best = max(best, dmg * max(0.0, p - base))
        return best

    def _promote_tempo_step(self, raw: dict) -> float:
        """``incoming(t=2) - incoming(t=1)`` against the body that would be my Active — ONE
        development step's threat growth off the live Threat-Clock curve (ADR-0100 §6).

        The curve's own docstring notes that `t` moves only the ENERGY budget, evolution reach being
        maximal at `t=1`, so the delta IS one step. 0.0 without a snapshot (fail-closed)."""
        model = self._state_model
        if model is None or not raw:
            return 0.0
        ctx = self._opp_attack_context
        return float(max(0, model.theirs.incoming(raw, 2, context=ctx)
                         - model.theirs.incoming(raw, 1, context=ctx)))

    def _opp_items_live(self) -> bool:
        """Does the opponent PROVABLY still hold live Item copies — the gate on `tempo_denied`
        (ADR-0100 §6).

        The shape of `_opp_switch_enabler`, but failing **CLOSED**: no facade, no functions table, no
        matched Read or any error all mean NO CREDIT. That is the opposite fail direction from a
        survival read, and it is the right one here because this term ENDORSES a play, and ADR-0067's
        rule is fail-closed on yield. An item lock that denies nothing must not pay."""
        if self.opponent is None or not self.stats:
            return False
        try:
            odds = self.opponent.copies_left_odds()
            if not odds:                              # unrecognised opponent — claim nothing
                return False
            return any(p > 0 for cid, p in odds.items()
                       if (st := self.stats.get(cid)) is not None and st.is_item)
        except Exception:
            return False

    def _promote_body_kos(self, obs: dict, board: Board, raw: dict) -> bool:
        """Does this body take a Knock Out on arrival — ruling 5's provable-KO stand-down for the
        fatal step (trading while ahead on the exchange is fine). The KO's own MAGNITUDE is not
        priced here; that is `_promote_ko_tactical`'s, summed on the same option (§1, §11)."""
        opp = self._opp_active(obs)
        if not (opp and opp.get("hp") and raw):
            return False
        return self._best_affordable_ko_value(
            obs, board, opp, raw.get("id"), len(raw.get("energies") or []), body=raw) > 0

    def _turn_dig_depth(self, obs: dict) -> int:
        """The cards this turn's REMAINING dig still puts within reach — the closure term's draw
        window (ADR-0100 §5).

        Summed over my in-play bodies whose draw/dig Ability is STILL ON THE MENU, because the menu
        is the fact about whether a use is left (the same argument ADR-0070 §7 makes for
        `body_ability_on_menu`). 0 when nothing is tagged or nothing is offered — fail-closed, and
        automatically 0 at a forced promote, where the menu is a TO_ACTIVE select and no play window
        remains at all (`docs/rulebook.txt` L173-176/L183)."""
        if self.functions is None:
            return 0
        me = self._my_player(obs) or {}
        bodies = [p for p in ((me.get("active") or []) + (me.get("bench") or [])) if p]
        return sum(self.functions.dig_depth(b.get("id")) for b in bodies
                   if b.get("id") is not None and self._ability_on_menu(obs, b.get("id")))

    def _retreat_discard_choice(self, ma: dict, n: int) -> dict:
        """``ma`` as it stands after a retreat discards ``n`` Energy — the GREEDY cheapest-to-lose
        typed choice (ADR-0100 §8).

        A Retreat Cost slot is COLOURLESS (`docs/rules.md` §89, rulebook.txt L142: "discard 1 Energy
        for each ⟨C⟩"), so which Energy goes is genuinely ours to pick — and the engine poses a
        `DISCARD_ENERGY` select over EVERY attached Energy to ask (verified in
        `cgpy/turn.py:_pose_retreat_energy`). Competent play, not optimism: it sheds the unit whose
        removal costs the least Build Standing first, which is off-type waste before matched slots."""
        energies = list(ma.get("energies") or [])
        for _ in range(min(max(0, int(n)), len(energies))):
            keep = max(range(len(energies)),
                       key=lambda i: self._build_standing(
                           dict(ma, energies=energies[:i] + energies[i + 1:])))
            energies.pop(keep)
        return dict(ma, energies=energies)

    def _retreat_cost_legs(self, obs: dict, card_worth: float = 0.0) -> dict:
        """What LEAVING the Active Spot costs (ADR-0100 §8) — the build the discard destroys, plus
        ADR-0069 §5c's resource premium.

        Computed ONCE per menu rather than per destination, because §9's claim is precisely that
        this is CONSTANT across destinations: "`preservation(A)` and `retreat_cost(A)` are CONSTANT
        across destinations, so they belong only on the whether-site's retreat option." Expressing
        that in the code's shape (rather than recomputing an identical answer per bench body) is what
        makes the claim checkable, and it keeps the greedy discard search off the inner loop.

        ``card_worth`` prices a switch-class ITEM instead of an Energy discard (§11's rider): a
        Switch costs a CARD and no Energy, so it destroys no build at all."""
        ma = self._my_active(obs)
        if not ma:
            return {}
        if card_worth > 0.0:                          # a Switch Item pays a card, never a build
            return {"card_worth": float(card_worth)}
        after = self._retreat_discard_choice(ma, self._effective_retreat_cost(obs, ma))
        discarded = list(ma.get("energies") or [])
        for eid in (after.get("energies") or []):     # the multiset difference — what actually goes
            if eid in discarded:
                discarded.remove(eid)
        # ADR-0069 §5c's resource premium: charged on worth ABOVE a reusable Basic, so a plain Basic
        # pays nothing and only a one-shot is nudged. Sub-band — it orders equals.
        premium = _ATTACH_RESOURCE_TIEBREAK * sum(
            max(0.0, self._role_value(eid) - ENERGY_TIER) for eid in discarded)
        return {"build_before": self._build_standing(ma),
                "build_after": self._build_standing(after), "resource_premium": premium}

    def _retreat_side(self, obs: dict, board: Board, *, promoted_raw, cost: dict) -> RetreatSide:
        """The A-side of a voluntary swap, for ONE destination (ADR-0100 §4 preservation, §8 cost).

        Only the PRESERVATION leg is per-destination, and only because the Bench that A lands on
        depends on which body left it — reading A among its CURRENT bench-mates would mis-price the
        Harvest exactly as ADR-0070 warned for the evolve result. The cost legs arrive precomputed
        from :meth:`_retreat_cost_legs`."""
        ma = self._my_active(obs)
        bench_after = [b for b in self._my_bench_raws(obs) if b is not promoted_raw] + [ma]
        return RetreatSide(body=self._promote_body(obs, board, ma, draws=0,
                                                   bench_after=bench_after), **cost)

    def _promote_retreat_decision(self, obs: dict, select: dict, board: Board, ctx, option: dict):
        """The PROMOTE/RETREAT DECIDER: price ONE option (ADR-0100). Returns the per-option TERM row
        — the decider's legible working — or None to abstain: the kill-switch is OFF, or this option
        is neither a body PICK nor a whether-to-retreat action.

        The three sites §9 names, all through ONE evaluator:

        * **pick** (a TO_ACTIVE forced promote or a SWITCH retreat destination) — `promote_value(B)`
          with NO A-side terms, because `preservation`/`retreat_cost` are constant across
          destinations and could change no ordering there.
        * **whether** (a native RETREAT at MAIN, or a switch-class Item PLAY) — the best destination's
          `promote_value(B)` PLUS `preservation(A) - retreat_cost(A)`.
        * **forced promote** — the pick site with the draw window at zero (§5).

        That both sites run this one evaluator is what makes the shipped divergence — retreat BECAUSE
        Cinderace is worth promoting, then promote Budew — structurally impossible rather than
        merely fixed."""
        if not getattr(self, "promote_retreat_value", False):
            return None
        sctx, otype = ctx.select_context, ctx.option_type
        my_index = (obs.get("current") or {}).get("yourIndex", 0)
        if sctx in (_TO_ACTIVE, _SWITCH):
            if option.get("playerIndex") not in (None, my_index):
                return None                           # a Boss's-gust target — the gust equation's turf
            raw = self._option_pokemon(obs, select, option)
            if not raw:
                return None
            # §5: the replacement Active is chosen right after the KO'ing attack resolves or at
            # Checkup, and attacking ends the turn — so at a FORCED promote no play window remains.
            draws = 0 if sctx == _TO_ACTIVE else self._turn_dig_depth(obs)
            body = self._promote_body(obs, board, raw, draws=draws)
            return self._promote_row(promote_value(PromoteRetreatInputs(body=body)), site="pick")
        if sctx != _MAIN:
            return None
        is_switch_item = (otype == _PLAY and "switch" in (ctx.tags or []))
        if otype != _RETREAT and not is_switch_item:
            return None
        # §11's rider: a switch-class ITEM is priced by the SAME equation as a manual retreat, with
        # the card's Worth as the cost — the charter names "SWITCH-class retreats", and two of the
        # deleted rungs fired on a `_PLAY` + `switch` option that the whether-site never saw.
        worth = self._role_value(ctx.card_id) if is_switch_item else 0.0
        if self._my_active(obs) is None:
            return None                               # no readable Active — make no claim
        cost = self._retreat_cost_legs(obs, worth)    # CONSTANT across destinations (§9)
        draws = self._turn_dig_depth(obs)
        best = None
        for raw in self._my_bench_raws(obs):
            if not raw or raw.get("id") is None:
                continue
            val = promote_value(PromoteRetreatInputs(
                body=self._promote_body(obs, board, raw, draws=draws),
                retreat=self._retreat_side(obs, board, promoted_raw=raw, cost=cost)))
            if best is None or val.total > best.total:
                best = val
        return None if best is None else self._promote_row(best, site="whether")

    @staticmethod
    def _promote_row(val, *, site: str) -> dict:
        """The decider's per-option working (ADR-0008/0019 full working), rounded for the wire. This
        DECIDES, so — like the attach and evolve rows — there is no agreement bit: one emission path,
        one truth, and the substrate #146/#148 consume."""
        return {"site": site, "tactical": val.total,
                "my_yield": round(val.my_yield, 2), "closure": round(val.closure, 2),
                "exposure": round(val.exposure, 2), "tempo_denied": round(val.tempo_denied, 2),
                "fatal": round(val.fatal, 2), "preservation": round(val.preservation, 2),
                "retreat_cost": round(val.retreat_cost, 2), "total": round(val.total, 2)}

    def _promote_ko_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for the body PICK that takes the prize — the pick site's own Knock-Out
        layer (ADR-0100 §11), mirroring `_retreat_to_lethal_tactical`.

        Rulings 4/5 defer wins to the Lethal Solver and provable KOs to the Turn Planner, but BOTH are
        MAIN-only (`planner.py:283`; `_retreat_to_lethal_tactical` fires only on a `_RETREAT` option).
        At a TO_ACTIVE/SWITCH body pick those owners DO NOT EXIST, so a strictly sub-lethal equation
        would promote the body that hits hardest over the body that takes the prize.

        Load-bearing at the two selects for DIFFERENT reasons:

        * **SWITCH — REALISATION, not a new decision.** The KO comparison already happened at MAIN,
          but `_retreat_to_lethal_tactical` takes a `max` over the bench and returns only a NUMBER —
          it never says WHICH body won. A sub-lethal pick could therefore retreat *because* Mega
          Lucario ex takes the Knock Out and then promote Cinderace. Both sites calling
          `best_affordable_ko_value` makes the pick land on the body that justified the retreat:
          consistency by construction, §9's argument applied to the KO layer.
        * **TO_ACTIVE — a fresh claim.** Their attack Knocked our Active out and attacking ends the
          turn (`docs/rules.md` §5), so per `docs/rulebook.txt` L176 we promote, their turn ends, and
          OUR turn starts with only the Checkup between — the promoted body swings against
          essentially the same board.

        Decision 1's split is preserved exactly: the KO DELTA is tactical, the sub-lethal residual is
        the equation's, and they SUM on the option. No new constant.

        Rides the SAME `promote_retreat_value` kill-switch as the equation, because it is half of one
        replacement: it takes over from `promote-the-ko-attacker` (+45) and
        `promote-the-accelerator-for-the-ko` (+50), both DELETED. Gating it separately would make OFF
        an incoherent state — a body pick with a KO layer but no residual, which is neither the old
        agent nor the new one. (This supersedes the `promote_ko_aware` kill-switch for SCORING; that
        flag now only feeds `board.ko_promote_slot`'s Context reads.)"""
        if not getattr(self, "promote_retreat_value", False):
            return 0.0
        if select.get("context") not in (_TO_ACTIVE, _SWITCH):
            return 0.0
        my_index = (obs.get("current") or {}).get("yourIndex", 0)
        if option.get("playerIndex") not in (None, my_index):
            return 0.0                                # a gust target (opponent body), not my pick
        opp = self._opp_active(obs)
        if not (opp and opp.get("hp")):
            return 0.0
        raw = self._option_pokemon(obs, select, option)
        if not raw:
            return 0.0
        return self._best_affordable_ko_value(
            obs, board, opp, raw.get("id"), len(raw.get("energies") or []), body=raw)

    def _effective_retreat_cost(self, obs: dict, ma: dict | None) -> int:
        """The Active's Retreat Cost in Energy — the count of Energy a retreat actually discards, and
        so (ADR-0100 §8) the size of the build a retreat destroys. READ-ONLY (mirrors the cost
        arithmetic of `_can_retreat` without its affordability verdict); 0 on an unknown stat.

        Three grant shapes, all fail-CLOSED — an unreadable or unmodelled grant charges the PRINTED
        cost, erring toward not retreating and never toward the retreat-happy pathology:

        1. a flat attached-Tool reduction (Air Balloon −2, `retreatReduction`);
        2. a CONDITIONAL attached Tool (`retreatFreeAtHp` — Rescue Board zeroes the cost outright once
           the holder is down to 30 HP or less);
        3. a BOARD-LEVEL Ability on ANOTHER of my bodies (`retreatFreeGrant` — Latias ex's Skyliner
           gives every Basic of mine no Retreat Cost, and `slowking` runs it).

        Shape 3 is why this now takes ``obs``: the granting body is not the body retreating, so no
        per-card read could ever see it. Under the old flat `x ENERGY_TIER` pricing a missed
        reduction cost 8 points; under the convex build delta, over-charging one Energy on a 3-slot
        attacker is `(3/3)^2 - (2/3)^2 = 5/9 x maxDamage` ~ **117 damage of phantom cost**, and it
        would be systematic on an archetype built around free-retreat pivoting."""
        return retreat_cost.effective_retreat_cost(
            ma, stat_of=self._stat_of, my_bodies=self._my_in_play_raws(obs), combat=self.combat)

    def _attached_retreat_delta(self, body: dict | None) -> int:
        """Σ ``retreatReduction`` over the Tools attached to ``body`` — the SIGNED amount to SUBTRACT
        from a printed Retreat Cost (`common.retreat_cost`, Issue #306)."""
        return retreat_cost.attached_retreat_delta(body, self._stat_of)

    def _can_retreat(self, ma: dict | None) -> bool:
        """My Active can pay its Retreat Cost this turn — attached Energy >= its EFFECTIVE retreat cost
        (printed cost minus the SIGNED `_attached_retreat_delta` — Air Balloon's +2 delta takes the
        cost DOWN by 2, Gravity Gemstone's −1 delta takes it UP by 1;
        rules.md §Retreat: "pay the Retreat cost in Energy"). Fail-CLOSED on an unknown stat: a
        KO_SCORE-class claim must never assume a retreat it cannot prove (ml f39: a 0-Energy Meowth ex
        with retreat 1 "retreated" into a benched Mega and the grab scored 1001). An attached Tool is a
        PROVABLE board fact, so subtracting it stays sound (ml f15: Air Balloon on Makuhita -> retreat
        2−2=0 -> free retreat into the benched Mega Lucario ex)."""
        if not ma or not self.stats:
            return False
        stat = self.stats.get(ma.get("id"))
        if stat is None:
            return False
        cost = max(0, getattr(stat, "retreatCost", 0) - self._attached_retreat_delta(ma))
        if cost == 0:
            return True                                   # free retreat
        return len(ma.get("energies") or []) >= cost

    def _promote_target_kos(self, obs: dict, select: dict, option: dict) -> bool:
        """At a TO_ACTIVE promote, True if the benched Pokémon this option brings up can Knock Out the
        opponent's Active this turn — its cheapest attack reaches the defender's HP (shared `_can_ko`
        oracle). Promoting it takes the prize from the front (and, for an accelerator, also loads the
        Bench). Fail-closed when stats / the target are missing."""
        poke = self._option_pokemon(obs, select, option)
        if not poke:
            return False
        stat = self.stats.get(poke.get("id")) if self.stats else None
        return self._can_ko(stat, self._opp_active(obs))

    def _promote_target_can_attack(self, obs: dict, select: dict, option: dict) -> bool:
        """At a TO_ACTIVE promote, True if the benched Pokémon this option brings up can use an attack
        this turn (Energy >= its cheapest attack cost) — a live attacker worth interposing in front of a
        win-condition, not a dead wall. Fail-closed when the context / stats / target are missing."""
        if select.get("context") != _TO_ACTIVE:
            return False
        poke = self._option_pokemon(obs, select, option)
        cid = (poke or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (poke and stat and stat.minAttackCost is not None):
            return False
        return len(poke.get("energies") or []) >= stat.minAttackCost

    def _promote_target_hits_weakness(self, obs: dict, select: dict, option: dict) -> bool:
        """At a TO_ACTIVE promote, True if the benched Pokémon this option brings up would strike the
        opponent's Active on its Weakness — its type (`energyType`) equals the defender's Weakness type, so
        its attack is doubled (rules.md §5). Makes a cheap interposed attacker a favourable trade (Cinderace's
        Fire into a Fire-weak Archaludon/Duraludon). Fail-closed when the context / stats / Active are missing."""
        if select.get("context") != _TO_ACTIVE:
            return False
        poke = self._option_pokemon(obs, select, option)
        stat = self.stats.get((poke or {}).get("id")) if (self.stats and poke) else None
        oa = self._opp_active(obs)
        opp_stat = self.stats.get((oa or {}).get("id")) if (self.stats and oa) else None
        return bool(stat and opp_stat and stat.energyType is not None
                    and opp_stat.weakness is not None and opp_stat.weakness == stat.energyType)

    def _best_promote_slot(self, me: dict) -> tuple | None:
        """(_BENCH, index) of the benched win-condition best to bring to the Active Spot — the READY
        one (Energy >= its cheapest attack cost) carrying the MOST Energy (closest to its payoff hit),
        so a promote/switch picks the built attacker over a bare same-name copy. None when no benched
        win-condition is ready. Was the per-option picker behind `promote-the-powered-attacker`, which is
        RETIRED with no ADR recording it (tools/rung_registry.py); a bench-index tiebreak keeps it deterministic. Distinct from `_priority_wincon_slot` (which targets the
        one still UNDER its max attack for Energy concentration — the opposite end of the build)."""
        wincon = self._wincon_set()
        if not wincon:
            return None
        best = None                                   # (energy, index)
        for i, p in enumerate(me.get("bench") or []):
            if p and p.get("id") in wincon:
                e = len(p.get("energies") or [])
                if e >= _min_attack_cost(self.stats, p.get("id")) and (best is None or e > best[0]):
                    best = (e, i)
        return (_BENCH, best[1]) if best else None

    def _ko_aware_promote_slot(self, obs: dict, board: Board, me: dict,
                               opp: dict | None) -> tuple | None:
        """(_BENCH, index) of the benched body to promote whose best affordable attack — given the
        Energy attachable THIS turn (the manual attach, when unspent) plus any playable {F}
        damage-boost — Knocks Out the opponent's Active. The KO-aware, boost-inclusive promote pick
        (`promote_ko_aware`): among the benched bodies that reach such a KO it prefers the one already
        carrying the most Energy (deterministic index tiebreak). None when no benched body reaches a
        KO — the picker then stands down (`is_ko_promote_target` false everywhere).

        This is a promote *steering* signal (a Hypothesis then weights it), not a Lethal lock, so it
        may model one planned attach; the KO valuation itself is min-bound sound. It KO-gates (fires
        only on a real KO of the CURRENT opp Active), so it never perturbs a board with no KO and its
        Hypothesis sits below the ADR-0044 interpose promote (deny-prizes still wins its cases). ROLE-
        INDEPENDENT so it works before any deck Strategy is loaded — ml f26/f48: promote Mega Lucario
        ex (Aura Jab 130 >= Tangela 80) over Solrock (70); ml f24: promote the boosted Solrock."""
        if not (opp and opp.get("hp")):
            return None
        ma = next((p for p in (me.get("active") or []) if p), None)
        bench = me.get("bench") or []
        hand_ids = frozenset(c.get("id") for c in (me.get("hand") or [])
                             if c and c.get("id") is not None)
        hand_basic = self._hand_basic_energy(me.get("hand") or [])       # {EnergyType: count}
        best = None                                                      # (energy, index)
        for i, p in enumerate(bench):
            if not p:
                continue
            e = len(p.get("energies") or [])
            pstat = self.stats.get(p.get("id")) if self.stats else None
            # this turn's manual attach, when unspent — typed to the body's own Energy when the hand
            # holds that Basic, else counted WILD (fail-open)
            if not board.energy_attached and self._best_hand_attach_units(hand_ids, pstat) >= 1:
                planned = 1
                ptype = (pstat.energyType if (pstat and pstat.energyType in hand_basic) else None)
            else:
                planned, ptype = 0, None
            boost = self._typed_boost_total(obs, pstat, opp)
            # bodies that WILL sit on my Bench after this promote: the current Active retreats down,
            # every other benched body stays (a requiresBench partner is satisfiable from these)
            bench_names = self._promote_bench_names(me, i, ma)
            ko = self._best_affordable_ko_value(
                obs, board, opp, p.get("id"), e + planned, bound="min", body=p,
                extra_type=ptype, extra_units=planned, boost_amount=boost,
                boost_type=(pstat.energyType if pstat else None), promote_bench_names=bench_names)
            if ko > 0 and (best is None or e > best[0]):
                best = (e, i)
        return (_BENCH, best[1]) if best else None

    def _promote_bench_names(self, me: dict, promoted_index: int, ma: dict | None) -> set:
        """Names on my Bench AFTER promoting bench slot ``promoted_index`` — every other benched body
        plus the current Active (which retreats to the Bench). The `requiresBench` partner set a
        promoted attacker can count on (Cosmic Beam's benched Lunatone is the retreated Active)."""
        names = set()
        for j, b in enumerate(me.get("bench") or []):
            if j == promoted_index or not b:
                continue
            st = self.stats.get(b.get("id")) if self.stats else None
            if st is not None and st.name:
                names.add(st.name)
        ma_stat = self.stats.get((ma or {}).get("id")) if (self.stats and ma) else None
        if ma_stat is not None and ma_stat.name:
            names.add(ma_stat.name)
        return names

    def _forced_promotion_key(self, opp: dict, doomed: bool) -> int | None:
        """ADR-0044 Forced-Promotion Read: when the opponent's Active is doomed (a promotion is
        forced next turn), the body they bring up = their highest OWN-damage READY attacker on the
        Bench (printed max damage, energy-INDEPENDENT — they promote the win-condition and accelerate
        it, not the energized bench-sitter that merely happens to be affordable now). Returns
        ``id(body)`` for exact, duplicate-safe matching against the snipe option; None when not doomed
        / no benched attacker / no provider. Damage is priced by the same scaled read the snipe rank
        uses (``_threat_damage_pair``), which closes the ms f85 gap this used to defer: printed damage
        hid a hand-size attacker's whole threat, so Alakazam's line read 10.

        READY means it can actually ATTACK next turn — attached Energy plus the one manual attach they
        will make reaches some attack's cost. "Energy-INDEPENDENT" was only ever meant to say 'they
        promote the win-condition, not whoever happens to carry Energy now'; read literally it picked a
        0-Energy Latias ex whose only attack costs three, over the 1-Energy Lillie's Clefairy ex that
        would be attacking immediately (ms 81785223 f45). A body that cannot attack next turn is not the
        promotion they will make. Among genuinely ready bodies, printed damage still decides."""
        if not doomed or not self.stats:
            return None
        best = None                                          # (own_damage, hp, id(body))
        for b in (opp.get("bench") or []):
            if not b:
                continue
            stat = self.stats.get(b.get("id"))
            own = self._threat_own_damage(b.get("id"), stat)
            if own <= 0:
                continue
            if getattr(stat, "tera", False):
                continue                                     # Tera on the Bench takes no damage —
                                                             # a pre-chip key I can never chip
            reach = len(b.get("energies") or []) + 1         # + the manual attach on their promote turn
            min_cost = getattr(stat, "minAttackCost", None) if stat else None
            if min_cost is not None and reach < min_cost:
                continue                                     # can't attack next turn — not their promote
            cand = (own, b.get("hp", 0), id(b))
            if best is None or cand[:2] > best[:2]:
                best = cand
        return best[2] if best else None
