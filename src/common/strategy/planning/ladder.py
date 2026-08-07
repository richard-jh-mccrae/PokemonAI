"""The Goal LADDER: what to plan when no win is provable — KO for prizes, KO the key threat, stabilize, heal, lock, or
deliberately forgo a KO.

Ranked against each other by the same leaf, so the ladder is an ordering over goals rather than a chain of special
cases."""
from __future__ import annotations


from common.strategy.context import _ACTIVE, _BENCH, _EVOLVE, _PLAY, _RETREAT
from common.strategy.planning.turn_line import TurnLine, _GOAL_LINE


_PLANNER_PATH_W = 25.0         # Tier-3 (ADR-0040): the KO'd key threat sits on MY cheapest Prize
                               # Path — sub-prize, ranks lines within the rung, never beats a prize

_PLANNER_ENABLER_FREE = 8.0    # cheapest-enabler tier (ADR-0031): a FREE direct-evolve (evolved form
                               # already in hand, pre-evo legally evolvable this turn) is the cheapest
                               # first step to the SAME KO — no card leaves the deck, no tutor spent.

_PLANNER_GAMEPLAN_W = 20.0     # ADR-0045 (S3): a candidate line SERVING the Match Planner's directed goal
                               # gets this × the Game Plan's confidence — sub-prize (< one KO_SCORE), ranks
                               # WITHIN a rung, never beats a prize; kill-switch `match_planner_steer`

_PLANNER_DECKOUT_W = 5.0       # BUILD 2 (`opp_resource_reads`): a sub-prize nudge toward pressing a KO/grind
                               # line when the opponent is near deck-out. `opp_deckout_in_turns` is SOUND
                               # (deck count is public); the finer prized-last-copy read is probabilistic
                               # (opp hand hidden) and deliberately NOT used. Sub-prize — never a reorder.

_PLANNER_DECKOUT_TURNS = 3     # "near deck-out" horizon: fire only when they exhaust within this many turns


class GoalLadderMixin:
    """The below-win goals, and the lines that serve each."""

    def _gameplan_goal_bonus(self, line_goal: str, board) -> float:
        """The Match Planner seam (ADR-0045 S3): a confidence-scaled sub-prize bump when a candidate Turn
        Line's goal serves the Game Plan's directed Turn Goal — the Game Plan steering the Turn Planner's
        ranking, never beating a prize. Silent unless ``match_planner_steer`` is on and the Game Plan
        directs a goal (withheld on low confidence, so a low-confidence plan never steers)."""
        if not getattr(self, "match_planner_steer", False):
            return 0.0
        gp = getattr(board, "game_plan", None)
        if gp is None or not gp.directed_goal:
            return 0.0
        return (_PLANNER_GAMEPLAN_W * gp.confidence
                if line_goal in _GOAL_LINE.get(gp.directed_goal, ()) else 0.0)

    def _deckout_grind_bonus(self, board) -> float:
        """BUILD 2 (`opp_resource_reads`, DEFAULT OFF): a sub-prize nudge toward pressing a KO/grind line
        when the opponent is near deck-out. ``board.opp_deckout_in_turns`` is SOUND — the opponent's deck
        count is public, so the exhaustion horizon is calibrated, not asserted; the finer "deny their
        LAST prized copy" read is probabilistic (their hand is hidden) and is deliberately NOT used here.
        Silent unless the flag is on AND a near-term deck-out is known; the bump is sub-prize/sub-survival
        (< one KO_SCORE), so it only ranks WITHIN a rung and never reorders a real prize/survival delta
        (ADR-0031 decision 3)."""
        if not getattr(self, "opp_resource_reads", False):
            return 0.0
        t = getattr(board, "opp_deckout_in_turns", None)
        if t is None or t > _PLANNER_DECKOUT_TURNS:
            return 0.0
        return _PLANNER_DECKOUT_W

    def _condition_holds(self, condition, board) -> bool:
        """Evaluate a clause's dynamic ``condition`` gate against the Board — TRUE only when the
        gate is absent or PROVABLY satisfied right now. The two board-checkable gates (Bianca's
        remaining-HP, Jumbo Ice Cream's attached-Energy) are evaluated; any other condition string
        fails closed (never plan on an amount that might not materialise).

        The Active-spot reading of :meth:`_condition_holds_for`, which is the same gate asked of an
        arbitrary body — see there for why both gates are per-TARGET at the card text."""
        return self._condition_holds_for(condition, cur_hp=board.my_active_hp,
                                         attached=board.my_active_energy)

    def _condition_holds_for(self, condition, *, cur_hp: int, attached: int) -> bool:
        """:meth:`_condition_holds` asked of ONE body rather than of my Active (Issue #409) — same
        vocabulary, same fail-closed default, the two board-checkable gates read against ``cur_hp``
        and ``attached`` instead of the Board's Active fields.

        **Both gates are per-TARGET at the card text, verified at source** (`EN_Card_Data.csv`), so
        this is the reading the Active form was a special case of rather than a widening of scope:
        1190 Bianca's Devotion is *"Heal all damage from 1 of your Pokémon that has 30 HP or less
        remaining"* — the HP clause qualifies the CHOSEN Pokémon, not the Active; 1147 Jumbo Ice
        Cream is *"Heal 80 damage from your Active Pokémon that has 3 or more Energy attached"*,
        where the Energy clause likewise qualifies the target and the Active-spot half rides its own
        ``restriction: active_only``. Reading either off the Active while healing a benched body
        would answer a question about the wrong Pokémon."""
        if not condition:
            return True
        if condition == "remaining_hp_30_or_less":
            return bool(cur_hp) and cur_hp <= 30
        if condition == "energy_3_plus":
            return attached >= 3
        return False

    def _heal_candidate(self, cid: int, board, active_stat) -> tuple[int, int] | None:
        """What playing heal-card ``cid`` on my Active would leave: ``(healed_hp, energy_total)``
        — the post-heal HP and the total Energy the Active can still pay an attack with this turn
        (attached after the card's rider, plus the manual attach if unused). Two sources, clause
        first (ADR-0032 4b): an Effect Clause (`kind: heal` with the measured ``amount`` and its
        ``rider``/``restriction``) generalizes the tag path; the `clutch_heal` Function Tag stays
        as the fallback (full heal + bounce — Wally's) for a clause-blind Pilot. None when ``cid``
        heals nothing, a restriction excludes my Active (``mega_only`` on a non-Mega), or the
        clause carries a ``condition`` the closed form can't evaluate (fail-closed: don't plan on
        an amount that might not materialise).

        **The two board-scaled magnitudes (Issue #349) are deliberately NOT read, and that is a
        ruling rather than an omission** — this asks one question, *what does my ACTIVE end up on?*
        ``each_of`` widens the SET a heal reaches and never the amount any one body receives, so 1222
        Fennel's *"Heal 40 damage from each of your Pokémon"* leaves my Active on exactly the 40 a
        single-target 40 would; reading it as a multiplier would credit 200 on a full board and
        manufacture a KO_SCORE-class phantom survival. ``amount_per`` DOES multiply, and ignoring it
        UNDER-credits — this method's own stated error direction, so it stands down from a line that
        would have worked rather than committing to one that would not. No `heal` clause carries it
        today; `_heal_averts_doom` carries the same ruling for the same reason."""
        attach = 0 if board.energy_attached else self._best_hand_attach_units(board.hand_ids, active_stat)
        return self._heal_body_candidate(cid, active_stat, is_active=True,
                                         cur_hp=board.my_active_hp,
                                         attached=board.my_active_energy, attach_units=attach)

    def _heal_body_candidate(self, cid: int, stat, *, is_active: bool, cur_hp: int, attached: int,
                             attach_units: int, max_hp: int | None = None) -> tuple[int, int] | None:
        """:meth:`_heal_candidate` asked of ANY of my bodies — Active **or** benched (Issue #409).
        ``(healed_hp, energy_total)`` for the body described by ``stat`` / ``cur_hp`` / ``attached``,
        or None when no clause of ``cid`` can reach it. The Active form above is this method with the
        Board's Active fields, so the two readings cannot drift.

        The generalization is forced by the HEAL target select (``SelectContext.HEAL``, 17): the
        engine has already resolved the play and is asking WHICH body, so every term is per-target.
        Restriction, condition, healed amount and the rider's Energy consequence are all clause facts
        about the *chosen* Pokémon — Wally's Compassion puts the Energy attached to *that* Pokémon
        into hand, Super Potion discards an Energy from *that* Pokémon — and the Active-only form
        could only ever answer them for one of the candidates.

        ``attach_units`` is the manual attach still available this turn, folded into ``energy_total``
        exactly as the Active form folds it. For a BENCHED body it is what a re-attach could restore,
        never what it can attack with — only the Active swings, which is why
        :meth:`pilot.Pilot._heal_bounce_cost` prices a benched bounce at 0 rather than reading this.

        Issue #349's ``each_of`` / ``amount_per`` stay unread here for the reason
        :meth:`_heal_candidate` gives at length, and that ruling is INHERITED rather than reopened
        (Issue #409 R4): an ``each_of`` card heals every body and so poses no target select at all,
        which is why widening the reading to a second area does not widen the question.

        ``max_hp`` is the CEILING a heal restores to, and it is a parameter because the card's printed
        HP is not always it: a **Hero's Cape** (1159, *"+100 HP"*) puts a 330-HP Mega Starmie ex on a
        board ``maxHp`` of 430, and ``amount: "all"`` heals to that. A caller holding the body dict
        passes its ``maxHp`` and gets the right answer; the default is ``stat.hp``, which is what
        :meth:`_heal_candidate` reads off the Board today and so leaves the shipped survival
        consumers exactly where they were. Measured on `ms_mirror_1001` f90, where the printed
        default under-heals a caped Active by 100."""
        max_hp = int(max_hp) if max_hp else (getattr(stat, "hp", 0) or 0)
        for clause in (self.effects.clauses(cid) if self.effects else ()):
            if clause.get("kind") != "heal":
                continue
            if not self._condition_holds_for(clause.get("condition"), cur_hp=cur_hp,
                                             attached=attached):
                continue                              # gate fails / not board-checkable: fail-closed
            if not self._heal_restriction_targets(clause.get("restriction"), stat,
                                                  is_active=is_active):
                continue
            amount = clause.get("amount")
            healed = max_hp if amount == "all" else min(max_hp, cur_hp + int(amount or 0))
            rider = clause.get("rider")
            if rider == "bounce_energy_to_hand":
                energy_total = attach_units           # all Energy bounced; only re-attach pays
            elif rider == "discard_own_energy":
                energy_total = max(0, attached - 1) + attach_units
            else:
                energy_total = attached + attach_units
            return (healed, energy_total)
        # The legacy Function-Tag fallback stays ACTIVE-ONLY, and deliberately (Issue #409 R3): the
        # tag records "full heal + Energy bounce" and nothing about WHICH bodies the card may reach,
        # so on a benched candidate it would be a guess at a restriction rather than a reading of one
        # — Wally's `mega_only` is a clause fact the tag cannot carry. Fail closed instead; the
        # Active path is unchanged, which is what keeps the shipped survival consumers still.
        if is_active and self.functions and "clutch_heal" in self.functions.tags(cid):
            return (max_hp, attach_units)             # legacy tag path: full heal + Energy bounce
        return None

    def _best_hand_attach_units(self, hand_ids, active_stat) -> int:
        """Energy units the best single attach from MY hand (``hand_ids``) provides my Active — 3
        for a discard-burst special (`discard_eot`, Ignition: CCC) onto an Evolution, 1 for any
        other Energy card, 0 when the hand holds none. `_attach_provision_codes`'s model,
        hand-scanned: the 6858 heal-then-attach line re-powers Nebula Beam with the bounced-around
        Ignition, and a heal whose re-attach doesn't exist can no longer fake a preserved KO. Also
        the gust-affordability read (`_board`'s ``payable`` — the f31 no-energy gust gate).

        The per-card provision is `CombatMath.provision_codes` since Issue #418, so the hand leg and
        the board leg cannot disagree about what one Ignition is worth on one holder."""
        best = 0
        for cid in hand_ids:
            st = self.stats.get(cid) if self.stats else None
            if st is None or getattr(st, "hp", 0):
                continue
            tags = self.functions.tags(cid) if self.functions else []
            # an Energy card: a typed Energy, a Basic/Special by cardType, or the colourless
            # discard-burst special (engine reports Ignition's energyType as 0 — cf `_has_reusable_energy`)
            if not (getattr(st, "energyType", 0) not in (None, 0)
                    or st.is_energy
                    or "discard_eot" in tags):
                continue
            best = max(best, len(self.combat.provision_codes_or_floor(cid, active_stat)))
        return best

    def _plan_fingerprint(self, obs, select) -> tuple:
        """A hashable/comparable snapshot of everything a plan depends on — the turn, both boards
        (id / energy / HP per Pokémon), my hand, my prize count, the manual-attach flag, and the option
        signature. Any reveal (a draw, a search, a KO, a new turn) changes it, so the cache re-plans; an
        unchanged board reuses the committed line."""
        cur = obs.get("current") or {}
        me, opp = self._my_player(obs), self._opp_player(obs)

        def body(p):
            return (p.get("id"), len(p.get("energies") or []), p.get("hp")) if p else None

        def side(pl):
            return (tuple(body(x) for x in (pl.get("active") or [])),
                    tuple(body(x) for x in (pl.get("bench") or [])))

        hand = tuple(sorted(c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None))
        opts = tuple((o.get("type"), o.get("attackId"), o.get("area"), o.get("index"),
                      o.get("inPlayArea"), o.get("inPlayIndex")) for o in (select.get("option") or []))
        return (cur.get("turn"), side(me), side(opp), hand, len(me.get("prize") or []),
                bool(cur.get("energyAttached")), opts)

    def _ko_for_prizes_lines(self, obs, select, board, options, traces) -> list:
        """The **KO-for-prizes** goal (ADR-0031 phase 1-2): multi-step enabling lines that unlock an
        otherwise-missed KO of the opponent's Active, each valued by the leaf-eval scalar (prizes
        dominant + my Active's survival vs Incoming + the threat removed). One candidate per enabling
        first-step (retreat into a benched attacker; evolve the Active; play an energy-tutor
        Supporter), each regressed to "does this body, after the step PLUS this turn's one attach,
        KO?" and evaluated at its end-of-turn board. Empty when no such line exists."""
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp"):
            return []
        opp_player = self._opp_player(obs)
        # Every line's attach capacity is the TYPED Attach Budget built for its OWN attacker
        # (ADR-0075) — each builder calls `_ko_line_pricing` itself, because the Budget is per target
        # body and cannot be computed once for the menu. The retired `extra + accel_*` count and the
        # `enabler_consumes_supporter` split it needed are both subsumed: the manual attach is a leg
        # of the Budget, and a line that plays a Supporter as its enabling step passes
        # `supporter_spent=True` rather than zeroing a separate accel term.
        threat = self._threat_magnitude(opp)
        lines = []
        for i, o in enumerate(options):
            cost = 0.0                                    # cheapest-enabler tier (ADR-0031): an enabler
                                                          # that PRESERVES deck/slot resources outranks a
                                                          # tutor reaching the SAME KO; 0 = the scarce
                                                          # Supporter tutor (last), sub-prize throughout
            if o.get("type") == _RETREAT:
                cand = self._retreat_ko_candidate(obs, board, opp, opp_player)
                kind, cost = "retreat", _PLANNER_ENABLER_FREE   # spends no card/slot — a free enabler
            elif o.get("type") == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                cand = self._evolve_ko_candidate(obs, select, board, o, opp, opp_player)
                kind, cost = "free evolve", _PLANNER_ENABLER_FREE
            elif o.get("type") == _EVOLVE and o.get("inPlayArea") == _BENCH:
                retreat_on_menu = any(x.get("type") == _RETREAT for x in options)
                cand = self._free_evolve_ko_candidate(obs, select, board, o, opp, opp_player,
                                                      retreat_on_menu)
                kind, cost = "free evolve", _PLANNER_ENABLER_FREE
            elif o.get("type") == _PLAY and self._is_evolution_tutor(obs, select, o):
                retreat_on_menu = any(x.get("type") == _RETREAT for x in options)
                cand = self._tutor_evolve_ko_candidate(obs, board, opp, opp_player, retreat_on_menu)
                kind = "evolution tutor"                  # a Supporter — least-preferred enabler (cost 0)
            elif (o.get("type") == _PLAY and getattr(self, "enabler_item_composer", False)
                  and self._is_item_pokemon_tutor(obs, select, o)):
                retreat_on_menu = any(x.get("type") == _RETREAT for x in options)
                cand = self._item_evolve_ko_candidate(obs, select, board, o, opp, opp_player,
                                                      retreat_on_menu)
                kind, cost = "item tutor", self._item_enabler_cost(board)   # BUILD 4: the Item's edge over
                #                       the scarce Supporter tutor is CONDITIONAL on preserving the slot
            elif (o.get("type") == _PLAY and getattr(self, "enabler_item_composer", False)
                  and self._is_rare_candy(obs, select, o)):
                retreat_on_menu = any(x.get("type") == _RETREAT for x in options)
                cand = self._rare_candy_ko_candidate(obs, select, board, o, opp, opp_player,
                                                     retreat_on_menu)
                kind, cost = "rare candy", self._item_enabler_cost(board)   # BUILD 1: a Basic->Stage2 skip
                #                       Item — tiered like the item tutor (slot-preservation credit)
            elif o.get("type") == _PLAY:
                cand = self._supporter_ko_candidate(obs, select, board, o, opp, opp_player)
                kind = "energy tutor"
            else:
                continue
            if cand is None:
                continue
            prizes, survives, *rest = cand
            # ADR-0074 decision 4 (#175): the prize term is weighted by P(the line's Energy is
            # really there) for the RANKED consumers that carry one. The hard-rung invariant is
            # restated in expectation — a positional score can never outrank a REALISABLE prize —
            # so a line that is unlikely to happen can now lose to one that will. Candidates
            # carrying no probability pass 1.0 and are byte-identical to before.
            line_p = max(0.0, min(1.0, float(rest[0]))) if rest else 1.0
            value = self._leaf_value(prizes=prizes * line_p, active_survives=survives,
                                     threat_removed=threat)
            value += self._gameplan_goal_bonus("ko_for_prizes", board)       # ADR-0045 seam (S3)
            value += self._deckout_grind_bonus(board)                        # BUILD 2 seam (opp_resource_reads)
            value += cost                                 # sub-prize/sub-survival: breaks a same-KO tie
                                                          # among enablers, never over a real prize delta
            odds = "" if line_p >= 1.0 else f" at p={line_p:.2f}"
            lines.append(TurnLine(next_step=[i], goal="ko_for_prizes", value=value,
                                  rationale=(f"plan (ko_for_prizes): {kind} unlocks a "
                                             f"{int(prizes)}-prize KO{odds}")))
        return lines

    def _ko_key_threat_lines(self, obs, select, board, options) -> list:
        """The **KO-the-key-threat** goal (the Goal Ladder's middle rung, CONTEXT.md *Turn Goal*;
        `planner_key_threat`): ENABLING lines that unlock a bench-snipe KO of the opponent's benched
        TOP-threat body — the greatest shared threat rank (`_body_threat_rank`: eventual attack
        power, forward evolution, energized/hand-size boosts). A snipe-KO already ON the menu needs
        no rung (the Tactical layer credits its prize KO_SCORE-class), but no closed-form hook scores
        the STEP that reaches one — `_retreat_to_lethal_tactical` and the KO-for-prizes generators
        test KOs of the ACTIVE only — so a retreat into the sniper, an evolve that brings the snipe
        attack online, or the energy tutor that powers it is invisible to the greedy scorer and the
        biggest future attacker survives. Bench snipes ignore W/R so ``rider >= hp`` is the exact KO
        test (`_snipe_ko_prizes`'s rule), and a Tera body is snipe-immune. Candidates join the
        KO-for-prizes pool: the leaf scalar ranks across the rungs (prizes dominant, then the removed
        threat's magnitude)."""
        opp_player = self._opp_player(obs)
        bench = [p for p in (opp_player.get("bench") or []) if p]
        if not bench:
            return []
        ranked = [(self._body_threat_rank(obs, p, board.read, board.posture_confidence), p)
                  for p in bench]
        if getattr(self, "ko_target_whiff", False):
            # BUILD 1 (DEFAULT OFF): among EQUAL-threat-rank targets prefer the one the opponent is
            # LEAST able to replace — lowest `copies_left_odds` of its own line. Threat rank stays the
            # dominant key, so this is a pure tiebreak; it never promotes a lesser threat. Fails OPEN
            # (`copies_left_odds` → 1.0 for an unrecognized opponent, so all-equal → no reorder).
            top_rank, top = max(ranked, key=lambda t: (t[0], -self._whiff_odds(board, t[1])))
        else:
            top_rank, top = max(ranked, key=lambda t: t[0])
        top_stat = self.stats.get(top.get("id")) if self.stats else None
        own_mag = float(getattr(top_stat, "maxDamage", 0) or 0) if top_stat else 0.0
        fwd_fn = getattr(self.stats, "forward_max_damage", None)
        fwd_mag = float(fwd_fn(top.get("id")) or 0) if fwd_fn is not None else 0.0
        threat_mag = max(own_mag, fwd_mag)             # the SAME damage basis the rank uses — a
                                                       # 0-printed body with a monster forward line
                                                       # (the Evolving-Threat case) still counts
        hp = top.get("hp", 0)
        if top_rank <= 0 or threat_mag <= 0 or not hp or self._is_tera(top.get("id")):
            return []                                 # nothing benched actually threatens (or Tera-immune)
        me = self._my_player(obs)
        opp = self._opp_active(obs)
        others = [p for p in ([opp] + [p for p in bench if p is not top]) if p]
        extra = 1 if (board.reusable_energy_in_hand and not board.energy_attached) else 0
        prizes = self._prize_value(top)
        lines = []
        for i, o in enumerate(options):
            if o.get("type") == _RETREAT:
                cand = self._retreat_snipe_candidate(me, others, hp, extra)
                kind = "retreat"
            elif o.get("type") == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                evolved_id = self._option_card_id(obs, select, o)
                if not self._affords_snipe_ko(evolved_id, board.my_active_energy + extra, hp):
                    continue
                estat = self.stats.get(evolved_id) if self.stats else None
                my_hp = getattr(estat, "hp", 0) or 0
                cand = (bool(my_hp) and self._incoming_worst(evolved_id, my_hp, others) < my_hp)
                kind = "evolve"
            elif o.get("type") == _PLAY:
                if (board.energy_attached or board.reusable_energy_in_hand
                        or not self._is_energy_tutor(obs, select, o)):
                    continue                          # mirrors `_supporter_ko_candidate`'s gate
                cand = self._retreat_snipe_candidate(me, others, hp, extra=1)
                kind = "energy tutor"
            else:
                continue
            if cand is None:
                continue
            value = self._leaf_value(prizes=prizes, active_survives=bool(cand),
                                     threat_removed=threat_mag)
            if (getattr(self, "objectives_path", False)          # Tier-3 (ADR-0040): a key threat ON my
                    and top.get("id") in board.path_target_ids):  # cheapest Prize Path advances the MATCH
                value += _PLANNER_PATH_W                          # win — sub-prize bump, ranks within rung
            value += self._gameplan_goal_bonus("ko_key_threat", board)       # ADR-0045 seam (S3)
            value += self._deckout_grind_bonus(board)                        # BUILD 2 seam (opp_resource_reads)
            lines.append(TurnLine(
                next_step=[i], goal="ko_key_threat", value=value,
                rationale=f"plan (ko_key_threat): {kind} unlocks the snipe-KO of the benched key threat"))
        return lines
