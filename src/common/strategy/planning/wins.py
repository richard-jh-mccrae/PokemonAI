"""The SOUND win search: lines that win THIS turn, and the engine replay that confirms them (ADR-0030).

Sound-only by construction — a line locks when the win is provable, never on a rollout estimate, and
`_engine_confirms_win` re-plays it against the real engine before it commits. A phantom win must never outrank a real
one."""
from __future__ import annotations


from dataclasses import replace

from common.strategy.context import KO_SCORE, _ACTIVE, _ATTACH, _ATTACK, _COIN_HEAD, _EVOLVE, _PLAY, _RETREAT
from common.strategy.planning.turn_line import TurnLine, _PRIZE_AREA, _prune_none, _rng_probe



class WinLineMixin:
    """Lines that win this turn, each verified before it locks."""

    def _win_line(self, obs, select, board, options, traces) -> TurnLine | None:
        """The shortest guaranteed win on this turn as a ``goal="win"`` Turn Line, or None. A refute
        DROPS the candidate (never lock a phantom); a None verdict keeps the closed-form lock."""
        if board.my_prizes_remaining <= 0:
            return None
        opp = self._opp_active(obs)
        family = self.lethal_family
        candidates = (self._family_win_candidates(obs, select, board, options, opp) if family
                      else self._legacy_win_candidates(obs, select, board, options, traces, opp))
        for cand in candidates:
            verified = None
            if (self.lethal_verify and not self._planning
                    and (family or cand.kind == "direct")):
                recorded = [] if (family and self.lethal_veto) else None
                verified = (self._engine_confirms_win(obs, [cand.next_step], max_cascade=40,
                                                      record=recorded)
                            if family else self._engine_confirms_win(obs, [cand.next_step]))
                if verified is False:
                    self._lethal_refutes += 1
                    continue                           # the engine says this "win" doesn't win — skip it
                if verified and recorded is not None:  # stage 3: a VERIFIED lock materializes its
                    self._win_lock_store(obs, recorded)   # confirmed cascade for replay
            return replace(cand, verified=verified)
        return None

    def _legacy_win_candidates(self, obs, select, board, options, traces, opp):
        """The pre-family (stage-1) closed-form candidates in their exact order — the
        ``lethal_family=False`` path (ADR-0030): direct KO, then hook-trace unlock, then evolve."""
        # 1) direct: a KO on the menu that wins now.
        for i, o in enumerate(options):
            if o.get("type") == _ATTACK and self._attack_wins(obs, board, o, opp):
                yield TurnLine(next_step=[i], goal="win", kind="direct",
                               rationale="lethal: this KO wins the match")

        # Develops below unlock a KO of opp ACTIVE (closed-form hooks). Wins iff takes my last prize
        # or opp has no bench to promote — under-counts any rider snipe, conservative but sound.
        if not (self._prize_value(opp) >= board.my_prizes_remaining or not board.opp_bench):
            return

        # 2) attach or retreat into a ready bench attacker, unlocking that KO — both KO_SCORE-class;
        # the finishing attack follows on the next menu.
        for i, o in enumerate(options):
            if o.get("type") in (_ATTACH, _RETREAT) and traces[i].tactical >= KO_SCORE:
                yield TurnLine(next_step=[i], goal="win", kind="unlock",
                               rationale="lethal (unlock): a develop enables the winning KO")
        # 3) EVOLVE the Active into a bigger attacker — no closed-form hook scores it, so look up
        # whether the evolved form's best affordable attack KOs (same-turn legal, rules.md §evolution).
        ma = next((p for p in (self._my_player(obs).get("active") or []) if p), None)
        for i, o in enumerate(options):
            if o.get("type") == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                evolved_id = self._option_card_id(obs, select, o)
                if self._best_affordable_ko_value(obs, board, opp, evolved_id, board.my_active_energy,
                                                  bound="min", body=ma) > 0:
                    yield TurnLine(next_step=[i], goal="win", kind="evolve",
                                   rationale="lethal (evolve): evolving enables the winning KO")

    def _family_win_candidates(self, obs, select, board, options, opp):
        """``goal="win"`` candidates from the ONE generator family (ADR-0037), SHORTEST-first. Every
        candidate is min-bound SOUND; an option index is yielded once, at its shortest tier."""
        # tier 0: direct — a KO on the menu that wins now.
        seen = set()
        for i, o in enumerate(options):
            if o.get("type") == _ATTACK and self._attack_wins(obs, board, o, opp):
                seen.add(i)
                yield TurnLine(next_step=[i], goal="win", kind="direct",
                               rationale="lethal: this KO wins the match")
        if board.turn <= 1:
            return                                     # turn 1 going first: no attack this turn, so
                                                       # no develop can cash a win (rules.md §first-turn)
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)
        extra = 1 if (board.reusable_energy_in_hand and not board.energy_attached) else 0
        for tier_extra in (0, extra) if extra else (0,):
            for i, o in enumerate(options):
                if i in seen:
                    continue
                t = o.get("type")
                if t == _ATTACH and o.get("inPlayArea") == _ACTIVE and tier_extra == 0:
                    # Count AND colour off the ONE provision read (Issue #418) — a second lookup for
                    # the type is a second chance to disagree with the first about the same card.
                    codes = self._attach_provision_codes(obs, select, board, o)
                    win = self._develop_wins(obs, board, opp, board.my_active_id,
                                             board.my_active_energy + len(codes), body=ma,
                                             extra_type=codes[0] if codes else None,
                                             extra_units=len(codes))
                    kind, why = "unlock", "lethal (unlock): the attach enables the winning KO"
                elif t == _RETREAT:
                    win = any(self._develop_wins(obs, board, opp, p.get("id"),
                                                 len(p.get("energies") or []) + tier_extra, body=p)
                              for p in (me.get("bench") or []) if p)
                    kind, why = "unlock", "lethal (unlock): the retreat enables the winning KO"
                elif t == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                    win = self._develop_wins(obs, board, opp, self._option_card_id(obs, select, o),
                                             board.my_active_energy + tier_extra, body=ma)
                    kind, why = "evolve", "lethal (evolve): evolving enables the winning KO"
                elif t == _PLAY and self._is_gust(obs, select, o):
                    win = self._gust_win_target(obs, board, board.my_active_energy + tier_extra)
                    kind, why = "gust", "lethal (gust): dragging up the KO-able body wins the match"
                else:
                    continue
                if win:
                    seen.add(i)
                    yield TurnLine(next_step=[i], goal="win", kind=kind, rationale=why)
        # tier 3: the energy-tutor Supporter supplies the attach the line lacks. SOUND only when the
        # deck DEFINITELY still holds a reusable Energy — a probable fetch is never a win.
        retreat_on_menu = any(o.get("type") == _RETREAT for o in options)
        if (not (board.energy_attached or board.reusable_energy_in_hand)
                and self._tutor_energy_certain(board)):
            for i, o in enumerate(options):
                if i in seen or o.get("type") != _PLAY or not self._is_energy_tutor(obs, select, o):
                    continue
                win = self._develop_wins(obs, board, opp, board.my_active_id,
                                         board.my_active_energy + 1, body=ma)
                if not win and retreat_on_menu:
                    win = any(self._develop_wins(obs, board, opp, p.get("id"),
                                                 len(p.get("energies") or []) + 1, body=p)
                              for p in (me.get("bench") or []) if p)
                if win:
                    seen.add(i)
                    yield TurnLine(next_step=[i], goal="win", kind="unlock",
                                   rationale="lethal (unlock): the energy tutor fetches the winning attach")
        # tier 4: the evolution-tutor Supporter (`rush_evolve`) evolves a deck-certain, no-Ability
        # DIRECT evolution onto an in-play body. Its own allowance covers every target, so no timing gate.
        targets = [(p, False) for p in (me.get("active") or []) if p]
        if retreat_on_menu:
            targets += [(p, True) for p in (me.get("bench") or []) if p]
        for i, o in enumerate(options):
            if i in seen or o.get("type") != _PLAY or not self._is_evolution_tutor(obs, select, o):
                continue
            if any(self._tutor_evolution_wins(obs, board, opp, p) for p, _ in targets):
                yield TurnLine(next_step=[i], goal="win", kind="unlock",
                               rationale="lethal (unlock): the evolution tutor evolves the winning attacker")
        # tier 5 (`boost_lethal`): retreat into a benched attacker whose DAMAGE-BOOSTED KO wins. The
        # retreat is the driven step; the boost total is this-turn plays plus playable hand copies.
        if self.boost_lethal and ma is not None:
            for i, o in enumerate(options):
                if i in seen or o.get("type") != _RETREAT:
                    continue
                for j, p in enumerate(me.get("bench") or []):
                    if not p:
                        continue
                    pstat = self.stats.get(p.get("id")) if self.stats else None
                    if pstat is None:
                        continue
                    boost = self._typed_boost_total(obs, pstat, opp)
                    if boost <= 0:                          # no boost applies -> not this tier
                        continue
                    names = self._promote_bench_names(me, j, ma)
                    if self._develop_wins(obs, board, opp, p.get("id"),
                                          len(p.get("energies") or []), body=p,
                                          boost_amount=boost, boost_type=pstat.energyType,
                                          promote_bench_names=names):
                        seen.add(i)
                        yield TurnLine(next_step=[i], goal="win", kind="unlock",
                                       rationale="lethal (boost): retreat into the boosted KO attacker wins")
                        break
        # tier 6 (`retreat_enabler_lethal`): a benched attacker ALREADY wins if promoted but the Active
        # cannot retreat — drive the retreat-reduction Tool, or a Trainer-tutor that certainly reaches one.
        if (self.retreat_enabler_lethal and ma is not None and not self._can_retreat(ma)
                and self._bench_body_wins_if_promoted(obs, board, opp, me, ma)):
            need = self._retreat_shortfall(ma)
            for i, o in enumerate(options):
                if i in seen or o.get("type") != _PLAY or need <= 0:
                    continue
                cid = self._option_card_id(obs, select, o)
                st = self.stats.get(cid) if (self.stats and cid is not None) else None
                tool_in_hand = st is not None and getattr(st, "retreatReduction", 0) >= need
                tutorable = (self._is_trainer_tutor(obs, select, o)
                             and self._deck_has_retreat_tool(board, need))
                if tool_in_hand or tutorable:
                    seen.add(i)
                    yield TurnLine(next_step=[i], goal="win", kind="unlock",
                                   rationale="lethal (unlock): the retreat Tool frees the retreat into the winning KO body")

    def _bench_body_wins_if_promoted(self, obs, board, opp, me, ma) -> bool:
        """SOUND: some benched body, promoted with its CURRENT Energy, takes a min-bound winning KO.
        The retreat itself is supplied by a Tool and is not modeled here."""
        return any(self._develop_wins(obs, board, opp, p.get("id"), len(p.get("energies") or []),
                                      body=p, promote_bench_names=self._promote_bench_names(me, j, ma))
                   for j, p in enumerate(me.get("bench") or []) if p)

    def _retreat_shortfall(self, ma) -> int:
        """Energy the Active is SHORT of paying its EFFECTIVE Retreat Cost (>0 iff it can't retreat
        now). EFFECTIVE, not printed: an ignored Tool SURCHARGE would under-state it (Issue #306)."""
        if not (ma and self.stats):
            return 0
        st = self.stats.get(ma.get("id"))
        if st is None:
            return 0
        eff = getattr(st, "retreatCost", 0) - self._attached_retreat_delta(ma)
        return max(0, eff - len(ma.get("energies") or []))

    def _is_trainer_tutor(self, obs, select, option) -> bool:
        """This PLAY option is a `tutor_trainer` Supporter — it searches ANY Trainer into hand, so it
        can certainly fetch a specific retreat Tool the deck definitely still holds."""
        cid = self._option_card_id(obs, select, option)
        return bool(cid is not None and self.functions and "tutor_trainer" in self.functions.tags(cid))

    def _deck_has_retreat_tool(self, board, need: int) -> bool:
        """SOUND: a retreat-reduction Tool covering ``need`` is PROVABLY still in my deck
        (`Board.deck_definitely_has`) — never a probable fetch."""
        if not self.stats:
            return False
        return any(st is not None and getattr(st, "retreatReduction", 0) >= need
                   and board.deck_definitely_has(cid)
                   for cid in set(self.deck) for st in (self.stats.get(cid),))

    def _develop_wins(self, obs, board, opp, attacker_id, energy, body=None,
                      extra_type=None, extra_units: int = 0,
                      boost_amount: int = 0, boost_type=None, promote_bench_names=None) -> bool:
        """SOUND: this attacker carrying ``energy`` takes a min-bound affordable KO that WINS — it
        reaches my remaining prize count, or their bench is empty. Rider snipes are under-counted."""
        if not (self._prize_value(opp) >= board.my_prizes_remaining or not board.opp_bench):
            return False
        return self._best_affordable_ko_value(obs, board, opp, attacker_id, energy, bound="min",
                                              body=body, extra_type=extra_type,
                                              extra_units=extra_units, boost_amount=boost_amount,
                                              boost_type=boost_type,
                                              promote_bench_names=promote_bench_names) > 0

    def _attach_provision_codes(self, obs, select, board, option) -> tuple:
        """The ``EnergyType`` UNIT codes this ATTACH provides the Active; ``()`` when unresolvable.
        CODES not a count, because the win test needs the COLOUR too (Issue #418)."""
        eid = self._option_card_id(obs, select, option)
        if eid is None:
            return ()
        active_stat = (self.stats.get(board.my_active_id)
                       if (self.stats and board.my_active_id is not None) else None)
        return self.combat.provision_codes_or_floor(eid, active_stat)

    def _is_gust(self, obs, select, option) -> bool:
        """This PLAY option is a gust card (Function Tag `gust`, e.g. Boss's Orders)."""
        cid = self._option_card_id(obs, select, option)
        return bool(cid is not None and self.functions and "gust" in self.functions.tags(cid))

    def _gust_win_target(self, obs, board, energy) -> bool:
        """SOUND: some benched body the gust drags Active is worth my remaining prize count AND my
        Active KOs it (ADR-0022). Dragging never empties their board, so only the prize-out wins."""
        ma = next((p for p in (self._my_player(obs).get("active") or []) if p), None)
        for b in (self._opp_player(obs).get("bench") or []):
            if not b or self._prize_value(b) < board.my_prizes_remaining:
                continue
            if self._best_affordable_ko_value(obs, board, b, board.my_active_id, energy,
                                              bound="min", body=ma) > 0:
                return True
        return False

    def _tutor_energy_certain(self, board) -> bool:
        """SOUND: my deck DEFINITELY still holds a reusable typed Energy a `tutor_energy` Supporter can
        fetch — positive certainty, never the probabilistic estimate. Reusable = not `discard_eot`."""
        if not self.stats:
            return False
        for cid in set(self.deck):
            stat = self.stats.get(cid)
            if not stat or getattr(stat, "hp", 0) or not getattr(stat, "energyType", 0):
                continue
            if self.functions and "discard_eot" in self.functions.tags(cid):
                continue
            if board.deck_definitely_has(cid):
                return True
        return False

    def _attack_wins(self, obs, board, option, opp) -> bool:
        """True iff taking this ATTACK wins THIS turn — its own KO(s) take my last prize, or it empties
        their board. A simultaneous double-KO is a DRAW, not a win (ADR-0022), so it never wins here."""
        aid = option.get("attackId")
        hp = (opp or {}).get("hp", 0)
        # bound="min" is the sound FLOOR: a coin/conditional contributes its worst case, so a phantom
        # Lethal can never lock.
        dmg = self.predicted_damage(self._my_active_id(obs), aid, opp, bound="min",
                                    context=self._damage_context(obs))
        active_ko = bool(hp and dmg >= hp)
        if active_ko and self._is_simultaneous_draw(board, aid, self._prize_value(opp)):
            return False
        prizes_taken = ((self._prize_value(opp) if active_ko else 0)
                        + self._snipe_ko_prizes(board.opp_bench, self.combat.rider_snipe(aid)))
        if prizes_taken >= board.my_prizes_remaining:
            return True
        return active_ko and not board.opp_bench       # KO leaves them no Pokémon to promote

    def _win_lock_store(self, obs, recorded) -> None:
        """Materialize a VERIFIED win line's confirmed cascade as the turn-scoped locked line: entries
        ``{ctx, max, drive, chosen}``. Only a verified lock ever stores one (ADR-0037 stage 3)."""
        self._locked_line = {"turn": (obs.get("current") or {}).get("turn"),
                             "queue": list(recorded)}

    def _option_identity(self, obs, select, option) -> tuple:
        """The live-matchable identity of one select option. Deliberately EXCLUDES the menu index —
        the replay's whole point is index-independence."""
        return (option.get("type"), option.get("attackId"),
                self._option_card_id(obs, select, option),
                option.get("inPlayArea"), option.get("inPlayIndex"), option.get("playerIndex"))

    def replay_locked_line(self, obs, select):
        """The locked line's next step replayed against the live select, as ``(chosen, TurnLine)``, or
        None. Never a blind index: every replayed pick is identity-resolved on the LIVE menu."""
        if not self._planning:                         # mirror the refute counter's reentry guard:
            self._lethal_lost = False                  # an in-sim decide must never clobber the
        lock = self._locked_line                       # outer decision's loss flag
        if not self.lethal_veto or self._planning or lock is None:
            return None
        if lock["turn"] != (obs.get("current") or {}).get("turn"):
            self._locked_line = None                   # a new turn: natural expiry, not a loss
            return None
        if not lock["queue"]:
            self._locked_line = None                   # line fully executed
            return None
        entry = lock["queue"].pop(0)
        if entry.get("drive"):
            return None                                # hidden-zone pick: policy-drives, lock kept
        options = select.get("option") or []
        live = {}
        for i, o in enumerate(options):
            live.setdefault(self._option_identity(obs, select, o), i)
        chosen = []
        for ident in entry.get("chosen") or ():
            i = live.get(tuple(ident))
            if i is None or i in chosen:
                self._locked_line = None               # sim diverged from reality: fall back to
                self._lethal_lost = True               # re-derivation, surface the loss
                return None
            chosen.append(i)
        if not chosen or select.get("context") != entry.get("ctx"):
            self._locked_line = None
            self._lethal_lost = True
            return None
        return (chosen, TurnLine(next_step=chosen, goal="win", kind="replay", verified=True,
                                 rationale="lethal (replay): executing the verified line"))

    def _exact_own_zones(self, obs, me):
        """The EXACT ``(your_deck, your_prize)`` for ``search_begin`` (ADR-0050), else ``(None, None)``.
        NEVER seed the deck+prize POOL into the deck half: the engine would fetch a fully-prized copy."""
        own = (obs or {}).get("own_prizes")
        if not own:
            return None, None
        prizes = {int(k): v for k, v in own.items()}
        known = self._deck_known_counts(me, prizes)
        if not known:
            return None, None
        your_deck = [cid for cid, n in known.items() for _ in range(n)]
        your_prize = [cid for cid, n in prizes.items() for _ in range(n)]
        return your_deck, your_prize

    def _seed_zones(self, obs, me, opp):
        """The hidden-zone predictions for ``search_begin`` (ADR-0050): ``(your_deck, your_prize,
        opp_deck, opp_prize, opp_hand)``. Opponent zones are a my-deck prefix — only the count matters."""
        deck = list(self.deck)

        def take(n):
            return deck[: max(0, n)]

        your_deck = your_prize = None
        if getattr(self, "lethal_seed_exact", True):
            your_deck, your_prize = self._exact_own_zones(obs, me)
        if your_deck is None:
            your_deck, your_prize = take(me.get("deckCount", 0)), take(len(me.get("prize") or []))
        return (your_deck, your_prize, take(opp.get("deckCount", 0)),
                take(len(opp.get("prize") or [])), take(opp.get("handCount", 0)))

    def _engine_confirms_win(self, obs, line_steps, max_cascade: int = 12, record=None):
        """Forward-simulate ``line_steps`` through the engine's OWN search and report ITS verdict
        (ADR-0030). Asymmetric: a True that rode RANDOMNESS demotes to None, a False is left alone."""
        if not (obs or {}).get("search_begin_input") or not line_steps:
            return None
        try:
            from cg import api as cgapi
        except Exception:
            return None
        from dataclasses import asdict
        cur = obs.get("current") or {}
        yi = cur.get("yourIndex", 0)
        players = cur.get("players") or []
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        yd, yp, od, op_, oh = self._seed_zones(obs, me, opp)   # ADR-0050: exact own split when anchored

        was_planning = self._planning
        self._planning = True                          # the cascade re-runs decide(): never nest
        # `observe()` is skipped under `_planning`, so drive the boost tracker from the sim's obs here
        # — snapshot + restore, so the sim's own boost plays never leak into the live match state.
        boost_snap = {k: list(v) for k, v in self._turn_boosts._by_side.items()}
        boost_turn_snap = self._turn_boosts._last_turn
        try:                                           # search, never verify inside a verify
            saw_rng = _rng_probe(cgapi, yi, prize=False)   # the VERDICT question: prize ids are moot
            sampled = False
            ob = cgapi.to_observation_class(obs)
            st = cgapi.search_begin(ob, yd, yp, od, op_, oh, [], manual_coin=True)
            for step in line_steps:
                st = cgapi.search_step(st.searchId, list(step))
                sampled = sampled or saw_rng(st.observation)
            verdict = None
            for _ in range(max_cascade):
                o = st.observation
                sampled = sampled or saw_rng(o)
                c = o.current
                if c and c.result != -1:
                    verdict = c.result == yi           # the engine's own verdict
                    break
                sel = o.select
                if sel is None or c is None:
                    break                              # nothing to drive: undetermined -> None
                if sel.context == _COIN_HEAD:
                    break                              # an unaccounted coin: never choose the flip
                if c.yourIndex != yi:
                    verdict = False                    # passed to the opponent unresolved: no win
                    break
                od = _prune_none(asdict(o))
                if self.boost_lethal:                  # count this-turn boost plays in the running sim
                    self._turn_boosts.observe(od)      # (gated: off -> the cascade is byte-identical)
                chosen = list(self.decide(od))
                if record is not None:
                    osel = od.get("select") or {}
                    opts = osel.get("option") or []
                    picked = [opts[j] for j in chosen if 0 <= j < len(opts)]
                    record.append({
                        "ctx": osel.get("context"), "max": osel.get("maxCount"),
                        "drive": bool(picked) and all(p.get("area") == _PRIZE_AREA for p in picked),
                        "chosen": [self._option_identity(od, osel, p) for p in picked]})
                st = cgapi.search_step(st.searchId, chosen)
            cgapi.search_end()
            if verdict is True and sampled:
                return None                            # confirmed only for THAT shuffle — undetermined
            return verdict                             # (False is left alone: a refute never lies)
        except Exception:
            try:
                cgapi.search_end()
            except Exception:
                pass
            return None
        finally:
            self._planning = was_planning
            self._turn_boosts._by_side = boost_snap        # restore live match state — the sim's own
            self._turn_boosts._last_turn = boost_turn_snap  # boost plays never leak past the verify
