"""The this-turn win search: the ENABLERS that turn a non-lethal board lethal — grab the missing card, attach the missing
Energy, retreat into the attacker that can, boost the damage over the line.

Every leg is sound-only: it fires when the win is provable, never on a rollout estimate (ADR-0030)."""
from __future__ import annotations


from common.deciders.facts import Board
from common.strategy.combat import _EFFICIENCY
from common.strategy.context import KO_SCORE, _ACTIVE, _ATTACH, _CARD, _PLAY, _RETREAT, _TO_HAND


# `_MATCHUP_PRIORITY_SCALE = 5` (ADR-0051) was DELETED with `_snipe_matchup_tactical` by ADR-0085
# decision 5 — its sole consumer. It existed to map a MatchupPlan role priority into a TACTICAL band
# defined relative to "the positional snipe rungs (Σ≲150)", and once those rungs are gone the band it
# named has no lower edge to sit above. The Brief's steer now travels as a MULTIPLIER on a [0,1]
# scalar instead of an addend in a damage-scale band, which is why no replacement rate is needed.
_RETREAT_POSITION_EPS = 0.001  # positioning tie-break for retreat-to-lethal lookahead: when retreating
                           # into a ready wincon takes the SAME KO the spent Active could, prefer it (wincon
                           # ends up Active) — tiny, only breaks exact ties, never beats a real edge.


class LethalMixin:
    """Enabler plays that make this turn's KO — or the game — reachable."""

    # Gust doctrine's whether-to-play lethal, SWITCH target-select, and Board signals live in
    def _grab_lethal_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for a GRAB (a `_TO_HAND` search/recover CARD option) that supplies THIS
        turn's KO-enabling attach — the recover-the-energy-that-wins lethal (ADR-0030; ms f110, ml
        f26/f48). Fires when the grab yields a reusable Basic Energy (direct — you grabbed it) or a
        `tutor_energy` card the deck can CERTAINLY cash (`_tutor_energy_certain`, or a reusable Energy
        revealed in THIS search's pool), and attaching it — onto the Active, or retreating into a benched
        attacker — delivers a min-bound KO of the opponent's Active (`_best_affordable_ko_value`). Mirrors
        `_attach_lethal_tactical` (any KO, not just a win, scored KO_SCORE + prize), extended to the grab
        select because the win rung (plan_turn) is MAIN-only. Tactical-layer (never a weight), min-bound
        SOUND like the Lethal Solver's closed-form locks. The retreat-into-a-benched-attacker branch is
        not engine-verified (a grab select can't sim the later retreat), but its downside is small: an
        over-claim only grabs an Energy over a body, never throws a game (the real KO still gates the MAIN
        attack). 0 off a grab CARD, turn 1, once the manual attach is spent, or with no KO-enabling grab.

        The retreat branch carries three preconditions it once lacked (ml f39, CRITICAL — it priced a
        useless Energy grab at 1001 and buried the Solrock the deck needed):
          1. **the retreat must be legal** — retreating costs Energy equal to the printed cost
             (rules.md §Retreat), and the Active there was a 0-Energy Meowth ex with retreat 1;
          2. **the grab must be NECESSARY** — the benched Mega already carried two {F} and Aura Jab costs
             one, so the KO existed with or without the fetched Energy (`kos(current)` was never tested);
          3. **the grab must be the MARGINAL Energy** — two Basic {F} already sat in hand, so the grab was
             not the source of the attach at all.
        Any one of them refutes f39; a KO_SCORE-class claim carries all three. The counter-fixture is ml
        84890060 f48, where all three hold (1-Energy Lunatone Active, retreat 1; benched Mega at zero)."""
        if (select.get("context") != _TO_HAND or option.get("type") != _CARD
                or board.turn <= 1 or board.energy_attached or board.my_prizes_remaining <= 0):
            return 0.0
        opp = self._opp_active(obs)
        if opp is None or not (opp or {}).get("hp"):
            return 0.0
        cid = self._option_card_id(obs, select, option)
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        direct = bool(stat and getattr(stat, "hp", 0) == 0
                      and getattr(stat, "energyType", 0) and "discard_eot" not in tags)
        tutor = ("tutor_energy" in tags
                 and (self._tutor_energy_certain(board) or self._search_pool_has_reusable_energy(board)))
        if not (direct or tutor):
            return 0.0
        etype = getattr(stat, "energyType", None) if direct else None      # a tutor's type is WILD
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)

        def kos(attacker_id, energy, body, units=1):
            return self._best_affordable_ko_value(obs, board, opp, attacker_id, energy, bound="min",
                                                  body=body, extra_type=etype, extra_units=units) > 0

        ko = kos(board.my_active_id, board.my_active_energy + 1, ma)
        if not ko and self._can_retreat(ma):              # retreat into a benched attacker, then attach
            ko = any(kos(p.get("id"), len(p.get("energies") or []) + 1, p)
                     # NECESSARY: the body doesn't already take the KO on the Energy it carries
                     and not kos(p.get("id"), len(p.get("energies") or []), p, units=0)
                     for p in (me.get("bench") or []) if p)
        if ko and board.reusable_energy_in_hand and direct:
            ko = False                                    # MARGINAL: a reusable Energy is already in hand,
                                                          # so this grab is not the source of the attach
        return (KO_SCORE + self._prize_value(opp)) if ko else 0.0

    def _grab_enabler_lethal_tactical(self, obs: dict, select: dict, board: Board,
                                      option: dict) -> float:
        """KO_SCORE-class value for grabbing the BODY that turns my Active's conditional attack on —
        the bench-the-enabler lethal (ml f13, CRITICAL). Solrock's Cosmic Beam "does nothing if you
        don't have Lunatone on your Bench" (`AttackStat.requiresBench`); with one {F} already attached
        and the opponent down to a lone 70-HP Staryu, fetching a Lunatone, benching it and attacking
        empties their board and WINS. The Lethal Solver's generator family never puts a body on the
        Bench, so `live_trace.lethal` was null and the grab went to a Riolu.

        SOUND, same standard as the rest of the family: the candidate is a Basic revealed in this
        search's pool (certain), the Bench has room, the attack is already affordable on ATTACHED
        Energy alone (no attach assumed), and the KO must WIN — take my last prize or leave them
        nothing to promote. Any missing piece → 0.0.

        On the bound: `damageMin` is 0 for exactly these attacks, because the requiresBench clause IS
        the conditional the min-bound protects against. We are establishing that condition, so the
        floor would be vacuous. Instead we demand the attack be DETERMINISTIC once the enabler is down
        — no coin, no scaling, no hidden rider (`damageMax == damage`) — and then read the exact
        damage. Anything else conditional and this returns 0.0 rather than guess."""
        if (select.get("context") != _TO_HAND or option.get("type") != _CARD
                or board.turn <= 1 or board.bench_full or board.my_prizes_remaining <= 0):
            return 0.0
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp") or not self.stats:
            return 0.0        # attack records resolve per-aid below (_attack_stat -> None skips), so
                              # no table-level gate — the provider is a record source too (ADR-0056)
        cid = self._option_card_id(obs, select, option)
        stat = self.stats.get(cid) if cid is not None else None
        if not stat or not stat.is_pokemon or stat.evolvesFrom:   # a benchable Basic Pokémon only
            return 0.0
        active = self.stats.get(board.my_active_id) if board.my_active_id is not None else None
        if not active:
            return 0.0
        ctx = self._my_damage_context(obs)
        have = set(ctx.get("atk_bench_names") or ())
        would_have = have | {stat.name}
        for aid in (getattr(active, "attacks", None) or ()):
            ast = self._attack_stat(aid)
            need = getattr(ast, "requiresBench", None)
            if not need or set(need) <= have:                 # unconditional, or already satisfied
                continue
            if not set(need) <= would_have:                   # this body isn't the missing piece
                continue
            if self._attack_cost(aid) > board.my_active_energy:
                continue                                      # affordable on ATTACHED Energy alone
            if not ast.is_deterministic:
                continue                                      # some OTHER clause is conditional — no lock
            dmg = self.predicted_damage(board.my_active_id, aid, opp, bound="exact",
                                        context={**ctx, "atk_bench_names": tuple(would_have)})
            if not (dmg and dmg >= (opp.get("hp") or 0)):
                continue
            wins = (self._prize_value(opp) >= board.my_prizes_remaining or not board.opp_bench)
            if wins and not self._is_simultaneous_draw(board, aid, self._prize_value(opp)):
                return KO_SCORE + self._prize_value(opp)
        return 0.0

    def _grab_retreat_tool_lethal_tactical(self, obs: dict, select: dict, board: Board,
                                           option: dict) -> float:
        """KO_SCORE-class value for grabbing a retreat-reduction Tool (Air Balloon) that FREES a retreat
        into an already-winning benched attacker — the retreat-enabler lethal (ml f15). My Active can't
        retreat now; a benched body, promoted, takes a min-bound WINNING KO
        (`_bench_body_wins_if_promoted`); the grabbed Tool's `retreatReduction` covers the Active's exact
        retreat shortfall. Extends the grab select because the enabler win rung (`_family_win_candidates`
        tier 6) is MAIN-only — the same shape as `_grab_enabler_lethal_tactical`, so the Petrel search
        picks Air Balloon over an off-line Trainer. Gated on `retreat_enabler_lethal`; SOUND (min-bound +
        win). Its downside mirrors the other grab tacticals: an over-claim only grabs the Tool over
        another card, never throws a game (the real retreat + KO still gate the later steps). 0 off a grab
        card, turn 1, or with no such win."""
        if (not getattr(self, "retreat_enabler_lethal", False) or select.get("context") != _TO_HAND
                or option.get("type") != _CARD or board.turn <= 1 or board.my_prizes_remaining <= 0):
            return 0.0
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp"):
            return 0.0
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)
        if ma is None or self._can_retreat(ma):            # only when a Tool is NEEDED to retreat
            return 0.0
        need = self._retreat_shortfall(ma)
        cid = self._option_card_id(obs, select, option)
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (need > 0 and stat is not None and getattr(stat, "retreatReduction", 0) >= need):
            return 0.0
        if not self._bench_body_wins_if_promoted(obs, board, opp, me, ma):
            return 0.0
        return KO_SCORE + self._prize_value(opp)

    def _attach_retreat_tool_lethal_tactical(self, obs: dict, select: dict, board: Board,
                                             option: dict) -> float:
        """KO_SCORE-class value for attaching a retreat-reduction Tool (Air Balloon) to the ACTIVE when it
        frees a retreat into an already-winning benched attacker (ml f15). Steers the Tool onto the body
        that must RETREAT (Makuhita), not the wincon the tool doctrine would otherwise prefer — the
        second half of the retreat-enabler lethal steering, after `_grab_retreat_tool_lethal_tactical`
        picks it in the Petrel search. Same gate/soundness; 0 off an ACTIVE Tool-attach, turn 1, or with
        no such win."""
        if (not getattr(self, "retreat_enabler_lethal", False) or board.turn <= 1
                or option.get("type") != _ATTACH or option.get("inPlayArea") != _ACTIVE
                or board.my_prizes_remaining <= 0):
            return 0.0
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp"):
            return 0.0
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)
        if ma is None or self._can_retreat(ma):            # a Tool is still NEEDED to retreat
            return 0.0
        need = self._retreat_shortfall(ma)
        cid = self._option_card_id(obs, select, option)
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (need > 0 and stat is not None and getattr(stat, "retreatReduction", 0) >= need):
            return 0.0
        if not self._bench_body_wins_if_promoted(obs, board, opp, me, ma):
            return 0.0
        return KO_SCORE + self._prize_value(opp)

    def _search_pool_has_reusable_energy(self, board) -> bool:
        """True iff THIS search's revealed pool (`search_deck_ids`) contains a reusable Basic Energy a
        `tutor_energy` card could cash into this turn's attach — the single-frame complement to
        `_tutor_energy_certain` (which needs the match-scoped tracker anchor the retest lacks). A card is
        reusable Energy when hp 0 with a real `energyType` and not `discard_eot`. False off a search reveal."""
        sd = board.search_deck_ids
        if not sd or not self.stats:
            return False
        for eid in sd:
            est = self.stats.get(eid)
            etags = self.functions.tags(eid) if self.functions else []
            if (est and getattr(est, "hp", 0) == 0 and getattr(est, "energyType", 0)
                    and "discard_eot" not in etags):
                return True
        return False

    # doctrine_gust (GustMixin). `_attach_lethal_tactical` below is the general (non-gust) lethal-ATTACH lookahead.
    def _attach_lethal_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for an ATTACH that UNLOCKS a knockout this turn — attaching this Energy
        to my Active win-condition lets its best now-affordable attack KO the opponent's Active (e.g.
        Ignition → CCC → Nebula Beam 210 vs a 200-HP Active = win). Closed-form lethal lookahead the
        single-action tactical can't see: it models the post-attach Energy through
        `CombatMath.provision_codes` (Issue #418 — a Basic provides one unit of its own colour,
        Ignition provides CCC on an Evolution, per the card text) and asks whether an affordable
        attack reaches the defender's HP (weakness-doubled).

        Fires only when the attach is NECESSARY (the Active can't ALREADY KO — else just attack, don't
        spend the attach) so it never rewards a needless attachment. Lives in the Tactical layer like
        the gust lethal, not as a tunable weight; `_finish_turn_last` then sequences a lethal attach
        first (take the win before digging). 0 otherwise."""
        if option.get("type") != _ATTACH or option.get("inPlayArea") != _ACTIVE:
            return 0
        if board.turn <= 1:        # turn 1 going first: can't attack this turn (rules.md §first-turn),
            return 0               # so no attach is lethal — burst would just be discarded
        opp = self._opp_active(obs)
        opp_hp = (opp or {}).get("hp", 0)
        active_stat = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        if not (active_stat and opp and opp_hp):
            return 0
        eid = self._option_card_id(obs, select, option)
        # The provision, off the ONE seam (Issue #418): count AND colour together, keyed on the
        # ACTIVE as the holder (Mega Starmie evolvesFrom Staryu, so Ignition provides CCC here). A
        # colourless code pays a {C} slot and NEVER a specific one — Ignition can't fund Jetting
        # Blow's {W} — and `()` means the card provides nothing at all, which is what a Pokémon Tool
        # riding `OptionType.ATTACH` provides. This term is KO_SCORE-class, so an over-read here is a
        # phantom knockout.
        codes = self.combat.provision_codes_or_floor(eid, active_stat)
        provided_units = len(codes)
        etype = codes[0] if codes else None
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)
        bench_names = tuple(                                     # requiresBench partner check: an attack
            (self.stats.get(b.get("id")).name if self.stats and self.stats.get(b.get("id")) else "")
            for b in (me.get("bench") or []) if b)               # that "does nothing" w/o a benched
        #                                                          partner (Cosmic Beam needs Lunatone) must
        # not phantom-KO here. The attach is to the ACTIVE, so the Bench is unchanged by it — the current
        # bench IS the partner set the unlocked attack fires under (ml 85709280 f17, CRITICAL: attach→Solrock
        # scored a 1001 phantom KO on an EMPTY bench because no context reached the requiresBench gate).

        def best_affordable(energy: int, extra_units: int = 0) -> float:
            # per-attack oracle (ADR-0032): adjust-then-max, so an ignore-flag attack is seen and a
            # prevented (ex-locked) defender correctly yields 0 — no lethal-attach onto a whiff.
            # Type-guarded (sound-or-silent): a specific-type slot the attach can't fund fails the
            # attack even when the COUNT suffices. Passes `atk_bench_names` (exact bound) so a
            # requiresBench attack with its partner absent is zeroed, not credited a phantom KO.
            # The loop itself is `combat.best_affordable_damage` (Issue #409) — extracted when a
            # third consumer arrived, so the count gate and the colour gate keep ONE home.
            return self._best_affordable_damage(
                board.my_active_id, energy, opp, body=ma, extra_type=etype,
                extra_units=extra_units, context={"atk_bench_names": bench_names})

        cur = board.my_active_energy
        if best_affordable(cur) >= opp_hp:                  # already lethal — no attach needed
            return 0
        if best_affordable(cur + provided_units, extra_units=provided_units) >= opp_hp:
            return KO_SCORE + self._prize_value(opp)
        return 0

    def _retreat_to_lethal_tactical(self, obs: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for a RETREAT that brings a READY benched win-condition to the Active
        Spot where its now-affordable attack KOs the opponent's Active THIS turn — the closed-form
        lookahead that lets the agent retreat a spent opener (e.g. a 1-Energy Cinderace) into the
        powered win-condition and TAKE the knockout with the right attacker, instead of chipping it
        away with the spent body. Mirrors `_attach_lethal_tactical` (a develop that unlocks a KO is
        KO-class), so `_finish_turn_last` and the score compare it on the SAME scale as the Active's
        own attack:

          - it returns the BEST KO value an affordable attack of a ready benched wincon reaches
            (KO_SCORE + prize − efficiency + bench-snipe rider), so when that wincon's KO is strictly
            better (a Jetting Blow 120+50-snipe over a plain chip-KO) the retreat outscores the spent
            Active's attack and wins; when the Active's own attack is the better KO it stays ahead.
          - a tiny positioning epsilon breaks an EXACT tie toward the retreat (the wincon ends up
            Active), never overriding a real tactical edge.

        Never forfeits a knockout: it fires ONLY when a benched attacker KOs the current opponent
        Active for a KO STRICTLY BETTER than the one my CURRENT Active can already take (so the prize is
        still taken, by the better attacker). Fires for a SPENT opener Active that can't KO swapping into
        the ready wincon, AND for any Active that CAN'T KO the opponent — e.g. its damage is prevented by
        an Ability (Crustle's ex-lock): retreat into a benched NON-ex attacker (a Cinderace) that can. So
        it stands down whenever my current Active can ALREADY take this KO (or a better one) — just
        attack, don't waste the retreat (and don't strand a fragile body / its own attack), the
        ep82867148 f62 shape: a Cinderace that already KOs must not retreat into an energised Staryu it
        would rather evolve. Also stands down when no benched body KOs, or stats are missing."""
        if option.get("type") != _RETREAT:
            return 0
        opp = self._opp_active(obs)
        if not (opp and opp.get("hp")):
            return 0
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        ma = next((p for p in (me.get("active") or []) if p), None)
        # Best KO the CURRENT Active can already take (0 if not, incl. ex-immune). Retreat is worth it
        # ONLY for a strictly better KO; same prize via a benched body wastes the Active's attack + turn.
        my_active_ko = self._best_affordable_ko_value(
            obs, board, opp, board.my_active_id, board.my_active_energy, body=ma)
        best = 0.0
        for p in (me.get("bench") or []):
            if not p:
                continue
            energy = len((p.get("energies") or []))
            best = max(best, self._best_affordable_ko_value(obs, board, opp, p.get("id"), energy, body=p))
        if best <= my_active_ko:                         # the Active already takes this KO (or better):
            return 0                                     # just attack — don't waste the retreat
        return best + _RETREAT_POSITION_EPS

    def _best_affordable_ko_value(self, obs: dict, board: Board, opp: dict, attacker_id: int | None,
                                  energy: int, *, bound: str = "exact", body: dict | None = None,
                                  extra_type=None, extra_units: int = 0,
                                  boost_amount: int = 0, boost_type=None,
                                  promote_bench_names=None, attack_p=None, budget=None) -> float:
        """The best KO value a hypothetical attacker reaches vs the opp Active — the KO oracle's
        ``best_affordable_ko_value`` (ADR-0052), handed the Board's ``opp_bench`` snapshot for the
        rider tiebreaks. Signature kept for the planner/tactical call sites (``obs`` vestigial).

        ``budget`` (ADR-0079, #177) hands the oracle the typed **Attach Budget** instead of a wild
        count; ``energy`` is then ignored. ``attack_p`` (ADR-0074, #175) weights a ranked
        consumer's claim. Refuse-then-weight: they are separate concerns on separate parameters."""
        return self.combat.best_affordable_ko_value(
            opp, attacker_id, energy, opp_bench=board.opp_bench, bound=bound, body=body,
            extra_type=extra_type, extra_units=extra_units,
            boost_amount=boost_amount, boost_type=boost_type,
            promote_bench_names=promote_bench_names, attack_p=attack_p, budget=budget)

    def _best_affordable_damage(self, attacker_id, energy: int, defender: dict | None, *,
                                body: dict | None = None, extra_type=None, extra_units: int = 0,
                                bound: str = "exact", context: dict | None = None) -> float:
        """The biggest damage a hypothetical attacker's AFFORDABLE attacks reach — the KO oracle's
        ``best_affordable_damage`` (Issue #409), the sub-lethal sibling of
        :meth:`_best_affordable_ko_value`.

        A PURE forward, unlike that sibling (which injects ``board.opp_bench``) — and that is the
        house shape for reaching `CombatMath`, not an oversight: :meth:`_attack_cost`,
        :meth:`predicted_damage` and :meth:`_attack_type_payable` are each exactly this, so the
        Pilot's call sites speak one vocabulary and the oracle stays the single combat home."""
        return self.combat.best_affordable_damage(
            attacker_id, energy, defender, body=body, extra_type=extra_type,
            extra_units=extra_units, bound=bound, context=context)

    def _boost_lethal_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for a damage-boost Trainer that UNLOCKS a knockout this turn — the
        executable core of the damage-boost OHKO-line model: playing this Premium Power Pro class
        Item/Supporter (+N this turn, an Item stacks across the copies I hold) or attaching this
        Maximum Belt class Tool (+N while attached, vs an ex Active) lifts my Active's best
        affordable attack over the defender's HP (Mega Brave 270 + Belt 50 = 320 = the Dragapult ex
        OHKO). Mirrors `_attach_lethal_tactical`: Tactical-layer (never a tunable weight), fires
        only when the boost is NECESSARY (no affordable attack already KOs — else just attack) and
        the crossing is exact oracle arithmetic (context-priced, so boosts ALREADY played this turn
        are in the base; each further copy's play re-passes this check on the updated context).
        `_finish_turn_last` then sequences the lethal play tier-0, ahead of the attack it enables.
        Skips a crossing whose forced recoil would be a simultaneous draw. 0 otherwise.

        ## Two cards, one question (Issue #424)

        *"Does this play turn a knockout that was not there before?"* is asked by a damage-boost card
        and by an HP-REDUCING Stadium alike, and only the crossing's SIDE differs::

            boost:     dmg + damageBoost * copies  >=  opp_hp
            hp_delta:  dmg                         >=  opp_hp + hp_shift

        so this is ONE term with two legs rather than two terms — the band, the necessity guard, the
        `_is_simultaneous_draw` refusal and the `_EFFICIENCY` discount are identical, and two
        spellings of one decision is the drift `_order_key`'s docstring exists to warn about.
        Gravity Mountain (1252) carries no ``damageBoost`` at all — its whole effect is the clause
        ``{"kind": "stadium_static", "effect": "hp_delta", "amount": -30, "applies_to": "stage2"}``
        (`card_effects.json`) — so it used to exit at the boost guard and fall to a flat rung that,
        by its own rationale, could not tell a board where the −30 crosses a breakpoint from one
        where it does not.

        ``hp_shift`` is SIGNED and nothing branches on its sign, which is what makes an
        HP-*increasing* Stadium priced as making a KO harder for free: it raises the bar the attack
        has to clear, so the crossing simply does not fire."""
        t = option.get("type")
        if board.turn <= 1:            # turn 1 going first: can't attack, no boost is lethal
            return 0
        cid = self._option_card_id(obs, select, option)
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        if st is None:
            return 0
        opp = self._opp_active(obs)
        opp_hp = (opp or {}).get("hp", 0)
        active = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        if not (active and opp and opp_hp):
            return 0
        opp_stat = self.stats.get(opp.get("id")) if self.stats else None
        boost, hp_shift = 0, 0
        if getattr(st, "damageBoost", 0):
            # ── the DAMAGE side: lift my attack over their HP ────────────────────────────────────
            if t == _PLAY and (st.is_item or st.is_supporter):  # Item stacks; a Supporter is one/turn
                copies = 1 if st.is_supporter else self._hand_count_of(obs, cid)
            elif (t == _ATTACH and st.is_tool
                  and option.get("inPlayArea") == _ACTIVE):     # a boost Tool onto my attacker
                copies = 1
            else:
                return 0
            if st.damageBoostType is not None and active.energyType != st.damageBoostType:
                return 0                                        # "your {F} Pokémon" — attacker-type gate
            if not st.applies_to_holder(active):
                return 0                                        # "the Hop's Pokémon this card is attached
                                                                # to" — the owner-family HOLDER gate
            if st.damageBoostVsEx and not (opp_stat and opp_stat.is_ex_body):
                return 0                                        # "{ex}" defender gate (incl. Mega ex)
            boost = st.damageBoost * copies
        elif t == _PLAY and st.is_stadium:
            # ── the HP side: lower their HP under my attack (Issue #424) ─────────────────────────
            shift = self._stadium_hp_shift(obs, cid, opp_stat)
            if shift is None:
                return 0                                        # a clause the seam cannot price
            hp_shift = shift
        else:
            return 0
        need = opp_hp + hp_shift                                # the defender's HP AFTER this play
        if need <= 0:                                           # a body the play alone would floor:
            return 0                                            # not a crossing this term can state
        ctx = self._my_damage_context(obs)
        for aid in (active.attacks or ()):
            cost = self._attack_cost(aid)
            if cost > board.my_active_energy:
                continue
            dmg = self.predicted_damage(board.my_active_id, aid, opp, context=ctx)
            if dmg >= opp_hp:
                return 0                                    # an affordable KO already exists — just attack
        best = 0.0
        for aid in (active.attacks or ()):
            cost = self._attack_cost(aid)
            if cost > board.my_active_energy:
                continue
            dmg = self.predicted_damage(board.my_active_id, aid, opp, context=ctx)
            if dmg <= 0:                                    # a boost never lifts a does-nothing attack
                continue
            if (dmg + boost >= need
                    and not self._is_simultaneous_draw(board, aid, self._prize_value(opp))):
                best = max(best, KO_SCORE + self._prize_value(opp) - _EFFICIENCY * cost)
        return best
