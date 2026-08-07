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
        """The shortest guaranteed win on the current turn as a ``goal="win"`` Turn Line, or None.

        Two generation modes (ADR-0037): ``lethal_family`` ON = the ONE generator family
        (`_family_win_candidates` — single+multi-develop, gust, tutor; all min-bound sound), every
        lock engine-verified (`lethal_verify`, cascade-driven to the engine's verdict). OFF = the
        legacy stage-1 rungs (`_legacy_win_candidates` — direct + hook-trace unlock + evolve), with
        verify on DIRECT locks only (a 1-step sim of a multi-step line ends mid-turn and would
        false-refute without the cascade drive the family mode uses). Either way: a refute drops the
        candidate (never lock a phantom, counted in `_lethal_refutes`); a None verdict keeps the
        sound closed-form lock (a coin-floor win can never verify True by construction — the
        min-bound floor is the authority there)."""
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
        """Yield the pre-family (stage-1) closed-form candidates in their exact order — the
        ``lethal_family=False`` path, ADR-0030's shipped rungs (shared-valuation upgrades — e.g.
        the typed-affordability guard — flow through): (1) a KO already
        on the menu that WINS now, judged by the attack's OWN prize yield (`_attack_wins`); (2) an
        Energy attach or a retreat into a READY benched attacker that unlocks the winning KO (the
        KO_SCORE-class closed-form hook traces); (3) an EVOLVE of the Active bringing a bigger
        attacker online (no hook scores it, so its own min-bound lookup)."""
        # 1) direct: a KO on the menu that wins now.
        for i, o in enumerate(options):
            if o.get("type") == _ATTACK and self._attack_wins(obs, board, o, opp):
                yield TurnLine(next_step=[i], goal="win", kind="direct",
                               rationale="lethal: this KO wins the match")

        # Develops below unlock a KO of opp ACTIVE (closed-form hooks). Wins iff takes my last prize
        # or opp has no bench to promote — under-counts any rider snipe, conservative but sound.
        if not (self._prize_value(opp) >= board.my_prizes_remaining or not board.opp_bench):
            return

        # 2) Energy attach (`_attach_lethal_tactical`) or retreat into ready bench attacker
        # (`_retreat_to_lethal_tactical`) unlocking that KO — both KO_SCORE-class; finishing attack
        # follows next menu.
        for i, o in enumerate(options):
            if o.get("type") in (_ATTACH, _RETREAT) and traces[i].tactical >= KO_SCORE:
                yield TurnLine(next_step=[i], goal="win", kind="unlock",
                               rationale="lethal (unlock): a develop enables the winning KO")
        # 3) EVOLVE of Active bringing bigger attacker online — no closed-form hook scores it, so
        # look up: evolved form inherits Active's Energy, best affordable attack must KO (same-turn
        # legal, rules.md §evolution). Typed-affordability guarded like every shared KO valuation.
        ma = next((p for p in (self._my_player(obs).get("active") or []) if p), None)
        for i, o in enumerate(options):
            if o.get("type") == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                evolved_id = self._option_card_id(obs, select, o)
                if self._best_affordable_ko_value(obs, board, opp, evolved_id, board.my_active_energy,
                                                  bound="min", body=ma) > 0:
                    yield TurnLine(next_step=[i], goal="win", kind="evolve",
                                   rationale="lethal (evolve): evolving enables the winning KO")

    def _family_win_candidates(self, obs, select, board, options, opp):
        """Yield ``goal="win"`` candidates from the ONE generator family (ADR-0037), SHORTEST-first:
        tier 0 = a direct KO already on the menu; tier 1 = one develop (attach the Active / retreat
        into a ready body / evolve the Active / gust up a KO-able last-prize body); tier 2 = the same
        develop PLUS this turn's one attach; tier 3 = the energy-tutor Supporter line (fetch the
        attach the line lacks). Every candidate is min-bound SOUND (worst-coin damage floors, exact
        prize math, engine-vetted step legality — an option on the menu IS legal); the develop tiers'
        win test is the conservative legacy precondition (opp-Active prize reaches my remaining count
        or their bench is empty — rider snipes under-counted, never over). An option index is yielded
        once, at its shortest tier (a refuted candidate is not retried at a longer tier: the verify
        cascade drives the same policy either way)."""
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
        # tier 3: the energy-tutor Supporter supplies the attach the line lacks (the 4298 shape,
        # game-winning). SOUND only when the deck DEFINITELY still holds a reusable Energy (the
        # match-scoped tracker's positive certainty) — a probable fetch is never a win.
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
        # tier 4: the evolution-tutor Supporter line (Salvatore, `rush_evolve` — the a212 shape):
        # evolve a deck-certain, no-Ability DIRECT evolution onto an in-play body straight from the
        # deck, then (for a benched body) retreat into it and attach — e.g. Salvatore -> Mega Starmie
        # onto a Staryu, free-retreat the opener, attach, Jetting Blow the last body: bench-empty win.
        # Salvatore's own allowance covers every in-play target (setup-placed / played this turn;
        # anything older is normal-legal), so no timing gate. SOUND on the tracker's positive deck
        # certainty + min-bound KO math; the engine verify cascade backstops the rest.
        targets = [(p, False) for p in (me.get("active") or []) if p]
        if retreat_on_menu:
            targets += [(p, True) for p in (me.get("bench") or []) if p]
        for i, o in enumerate(options):
            if i in seen or o.get("type") != _PLAY or not self._is_evolution_tutor(obs, select, o):
                continue
            if any(self._tutor_evolution_wins(obs, board, opp, p) for p, _ in targets):
                yield TurnLine(next_step=[i], goal="win", kind="unlock",
                               rationale="lethal (unlock): the evolution tutor evolves the winning attacker")
        # tier 5 (`boost_lethal`): retreat into a benched attacker whose DAMAGE-BOOSTED KO wins — the
        # promote-a-benched-{F}-attacker → play N damage-boost Items → swing-lethal shape (ml f24:
        # Solrock's Cosmic Beam 70 + 2x Premium Power Pro = 130 exact OHKOs Duraludon; opp bench empty
        # -> a bench-empty win). The retreat is the driven step; the SWITCH then promotes the boosted
        # body (`promote_ko_aware`'s `is_ko_promote_target`), the Items price at KO_SCORE via
        # `_boost_lethal_tactical` once it is Active, and the final swing is the direct tier-0 KO. The
        # boost total is this-turn plays + playable hand copies (`_typed_boost_total`); the retreated
        # Active benches as the `requiresBench` partner. Min-bound sound; engine-verified on lock.
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
        # tier 6 (`retreat_enabler_lethal`): a benched attacker ALREADY wins if promoted, but the Active
        # can't retreat now — a retreat-reduction Tool (Air Balloon: {C}{C} less) frees the retreat. Drive
        # the Tool play (already in hand), else a Trainer-tutor Supporter (Petrel: "search a Trainer") whose
        # deck DEFINITELY still holds a covering Tool (ml f15: Petrel -> Air Balloon -> onto Makuhita -> free
        # retreat -> promote Mega Lucario ex -> Aura Jab 130 >= Riolu 80, opp bench empty). The tutor pick ->
        # Tool -> Active attach -> retreat -> promote cascade rides re-planning + the steering hooks; SOUND on
        # the tracker's positive deck certainty, and engine-verified on lock (a phantom is dropped).
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
        """SOUND: some benched body, promoted with its CURRENT Energy (a freed retreat brings it Active),
        takes a min-bound winning KO of the opponent's Active. The retreat-enabler tier's win test — the
        retreat itself is supplied by a Tool, not modeled here (``_develop_wins`` values the body as if
        already Active, the retreated Active provably benched via ``_promote_bench_names``)."""
        return any(self._develop_wins(obs, board, opp, p.get("id"), len(p.get("energies") or []),
                                      body=p, promote_bench_names=self._promote_bench_names(me, j, ma))
                   for j, p in enumerate(me.get("bench") or []) if p)

    def _retreat_shortfall(self, ma) -> int:
        """Energy the Active is SHORT of paying its EFFECTIVE Retreat Cost this turn (>0 iff it can't
        retreat now). A retreat-reduction Tool whose reduction covers this frees the retreat (Air Balloon
        −2 on a retreat-2 Makuhita with 0 attached -> shortfall 2 -> free).

        "Effective", not printed, since Issue #306. This used to read the printed cost and ignore the
        Tools ALREADY attached, which merely over-stated the need while every Tool was a discount —
        fail-closed, so it survived. Gravity Gemstone makes a retreat cost {C} MORE
        (`retreatReduction` −1), and an ignored surcharge UNDER-states the need, which would let
        `_grab_retreat_tool_lethal_tactical` / `_attach_retreat_tool_lethal_tactical` accept a Tool
        that does not in fact free the retreat and score the phantom at KO_SCORE. Shared with
        `_can_retreat` through `_attached_retreat_delta`, so the two cannot disagree about a body."""
        if not (ma and self.stats):
            return 0
        st = self.stats.get(ma.get("id"))
        if st is None:
            return 0
        eff = getattr(st, "retreatCost", 0) - self._attached_retreat_delta(ma)
        return max(0, eff - len(ma.get("energies") or []))

    def _is_trainer_tutor(self, obs, select, option) -> bool:
        """This PLAY option is a `tutor_trainer` Supporter (Petrel class) — it searches ANY Trainer card
        into hand, so it can certainly fetch a specific retreat Tool the deck definitely still holds."""
        cid = self._option_card_id(obs, select, option)
        return bool(cid is not None and self.functions and "tutor_trainer" in self.functions.tags(cid))

    def _deck_has_retreat_tool(self, board, need: int) -> bool:
        """SOUND: a retreat-reduction Tool whose reduction covers ``need`` is PROVABLY still in my deck
        (the match tracker's positive certainty, `Board.deck_definitely_has`) — never a probable fetch."""
        if not self.stats:
            return False
        return any(st is not None and getattr(st, "retreatReduction", 0) >= need
                   and board.deck_definitely_has(cid)
                   for cid in set(self.deck) for st in (self.stats.get(cid),))

    def _develop_wins(self, obs, board, opp, attacker_id, energy, body=None,
                      extra_type=None, extra_units: int = 0,
                      boost_amount: int = 0, boost_type=None, promote_bench_names=None) -> bool:
        """SOUND: this attacker, carrying ``energy``, takes a min-bound affordable KO of the
        opponent's Active AND that KO wins — it reaches my remaining prize count or their bench is
        empty (no Pokémon to promote). The family's shared develop-tier win test: worst-coin damage
        floors via ``bound="min"``, rider snipes deliberately under-counted (conservative).
        ``body``/``extra_type``/``extra_units`` forward to the typed-affordability guard (an Energy
        the line provides can't fund a specific-type slot it doesn't match — Ignition never pays a
        {W}); budget beyond attached+extra stays wild (fail-open). ``boost_amount``/``boost_type``/
        ``promote_bench_names`` forward the damage-boost rider (the `boost_lethal` tier: a typed
        this-turn boost + a provably-benched `requiresBench` partner)."""
        if not (self._prize_value(opp) >= board.my_prizes_remaining or not board.opp_bench):
            return False
        return self._best_affordable_ko_value(obs, board, opp, attacker_id, energy, bound="min",
                                              body=body, extra_type=extra_type,
                                              extra_units=extra_units, boost_amount=boost_amount,
                                              boost_type=boost_type,
                                              promote_bench_names=promote_bench_names) > 0

    def _attach_provision_codes(self, obs, select, board, option) -> tuple:
        """The ``EnergyType`` UNIT codes this ATTACH provides the Active — one of its own colour for
        a Basic Energy, CCC for a discard-burst (`discard_eot`, Ignition) onto an Evolution.
        ``()`` when the card can't be resolved or provides no Energy.

        CODES rather than a bare count since Issue #418, off the single seam
        `CombatMath.provision_codes`: the develop-tier win test needs the COLOUR as well (an Energy
        the line provides can't fund a specific-type slot it doesn't match — Ignition never pays a
        {W}), and reading the count here and the colour at the call site is two readings of one
        fact."""
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
        """SOUND: some benched opponent body the gust drags Active is worth my remaining prize count
        AND my Active (at ``energy``) takes a min-bound affordable KO of it — the ADR-0022 gust
        lethal, generated (and locked) by the family rather than hook-scored. Dragging never empties
        their board (the old Active benches), so only the prize-out shape wins here; Tera bench
        immunity is irrelevant (the target is Active when hit)."""
        ma = next((p for p in (self._my_player(obs).get("active") or []) if p), None)
        for b in (self._opp_player(obs).get("bench") or []):
            if not b or self._prize_value(b) < board.my_prizes_remaining:
                continue
            if self._best_affordable_ko_value(obs, board, b, board.my_active_id, energy,
                                              bound="min", body=ma) > 0:
                return True
        return False

    def _tutor_energy_certain(self, board) -> bool:
        """SOUND: my deck DEFINITELY still holds a reusable typed Energy a `tutor_energy` Supporter
        can fetch — the deck tracker's positive certainty (`Board.deck_definitely_has`), never the
        probabilistic estimate. Reusable mirrors `_has_reusable_energy`: an Energy card (hp 0, real
        `energyType`) not tagged `discard_eot`."""
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
        """True iff taking this ATTACK wins the match THIS turn — its own KO(s) take my last prize, or
        it empties the opponent's board. Per-attack and CONSERVATIVE (under-counts riders rather than
        over): a false Lethal is the one catastrophic error, so soundness beats completeness. A
        simultaneous double-KO is a draw, not a win (ADR-0022 #2), so it never wins here."""
        aid = option.get("attackId")
        hp = (opp or {}).get("hp", 0)
        # Damage oracle (ADR-0032): ignore-flag attack (Nebula Beam) KOs through prevent_ex_damage wall old
        # path zeroed. bound="min" = sound FLOOR: coin/conditional contributes worst case, never locks phantom Lethal.
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
        """Materialize a VERIFIED win line's confirmed cascade as the turn-scoped locked line
        (ADR-0037 stage 3, `lethal_veto`): the engine-driven selects, each an entry
        ``{ctx, max, drive, chosen}`` where ``chosen`` is the picked options' identity tuples and
        ``drive`` marks a hidden-zone pick (prize) the replay must policy-drive. Only a verified
        lock ever stores one — a None-verdict lock has no confirmed cascade to replay."""
        self._locked_line = {"turn": (obs.get("current") or {}).get("turn"),
                             "queue": list(recorded)}

    def _option_identity(self, obs, select, option) -> tuple:
        """The live-matchable identity of one select option — type + attack + resolved card +
        in-play target + owner. Deliberately EXCLUDES the option's menu index (the replay's whole
        point is index-independence); a visible-zone card resolves by id, so a sim pick maps onto
        the live menu wherever it sits."""
        return (option.get("type"), option.get("attackId"),
                self._option_card_id(obs, select, option),
                option.get("inPlayArea"), option.get("inPlayIndex"), option.get("playerIndex"))

    def replay_locked_line(self, obs, select):
        """The locked line's next step, replayed against the live select (ADR-0037 stage 3), as
        ``(chosen, TurnLine)`` — or None when there is nothing to replay: veto off, no lock, the
        lock expired (a new turn — natural, silent), the entry is a hidden-zone pick (policy-drives
        it, entry consumed, lock kept), the queue ran dry, or ANY identity failed to match — the
        mismatch path also clears the lock and raises the sparse ``lethal_lost`` flag
        (`_lethal_lost`, telemetry) so a live sim-vs-reality divergence is countable. Never a blind
        index: every replayed pick is identity-resolved on the LIVE menu."""
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
        """(ADR-0050) The EXACT ``(your_deck, your_prize)`` predictions for ``search_begin`` — flat
        card-id lists — from the deck tracker's anchored split: ``your_deck`` = decklist − visible −
        prizes (``_deck_known_counts``), ``your_prize`` = ``obs['own_prizes']``. ``(None, None)`` when
        the prizes are not yet anchored (no ``own_prizes``, or the tracker can't resolve them), so the
        caller keeps the sound decklist-prefix fallback.

        NEVER seeds the deck+prize POOL into the deck half: over-counting a prized copy into the deck
        is exactly what could let the engine fetch a card that is really all prized and false-confirm
        a phantom win (the one catastrophic Solver error). The split is the soundness."""
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
        """(ADR-0050) The hidden-zone predictions for ``search_begin``:
        ``(your_deck, your_prize, opp_deck, opp_prize, opp_hand)``.

        MY deck/prize use the EXACT anchored split (``_exact_own_zones``) when ``lethal_seed_exact`` is
        on and the tracker has anchored; else a decklist prefix — the sound fallback, because only
        non-fetch lines (whose verdict is deck-independent) reach the search unanchored (the fetch
        tiers gate on ``deck_definitely_has``, which needs the anchor). The prefix is what
        false-refuted the high-id enabler band before this fix (`deck.csv` is id-sorted).

        Opponent zones stay a my-deck prefix: a this-turn lethal ends before the opponent acts
        (`_engine_confirms_win` refutes the moment control passes to them), so their hidden content
        cannot change the verdict — only the count must satisfy ``search_begin``."""
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
        """Tier-1 (ADR-0030): forward-simulate ``line_steps`` — a list of per-select index lists, the
        exact moves of a candidate win line — through the engine's OWN search and report whether IT
        declares me the winner. The grading engine, not my closed-form math, is the authority, so it
        also resolves what closed-form is blind to (abilities, status, Tera, evolution/turn-1 timing).

        Distinct from `_simulate_line` by design: THIS is the sound regime (``manual_coin=True``,
        drives to the engine's VERDICT); that is the heuristic ranker (coins auto-resolve, reads the
        end-of-turn BOARD). A winning attack does not flip ``result`` at the attack step: the engine
        first opens MY cascade selects (take the prize(s), pick a snipe/Damage target, pay a cost),
        so after the line's own steps the search keeps driving MY selects through the policy
        (``decide``, under the ``_planning`` guard so nothing nests or pollutes) until the engine
        reaches a verdict — measured live: the prize-take TO_HAND select is what every real win
        parks on.

        Sound and fail-safe:
          * ``manual_coin=True`` so a coin the line doesn't account for surfaces as a COIN_HEAD
            select → **None** rather than trust a chosen flip (never let the policy pick heads).
          * a cascade that DREW off the shuffled deck can only be confirmed as far as that draw:
            a ``True`` there is demoted to **None** (#178). Same rule as the coin, through the door
            the coin rule left open — `_seed_zones` seeds the hidden zones with a predicted MULTISET
            whose ORDER is our guess, so a win that needed a specific card off it is not a guaranteed
            win in the real game, whatever the sim did. Asymmetric on purpose:
            **False is left alone.** A refute is the conservative direction (it drops a candidate and
            costs at most a turn), while demoting refutes to None would let phantom locks through —
            the one catastrophic error. Measured on ml f24 (2026-07-27): its `[correct]`-only
            cascade shuffles its hand back in mid-line and then draws ELEVEN cards off the reshuffled
            deck — every one of them AFTER that shuffle, which is the part the engine does not
            reproduce — and its verdict came back False on most runs and True on some, which is what
            made two suite tests flake through the same frame.
          * the select passing to the OPPONENT with no verdict = the win did not materialize before
            they act → False (a real refute: our win-shapes need no opponent action).
          * an exhausted cascade cap is **None** (undetermined never refutes); so is an unavailable
            search (lib-free suite), a missing ``search_begin_input``, or any error — the caller
            then keeps its sound closed-form verdict.
        The hidden-zone predictions are filled from my own deck list; the cascade's prize picks
        reveal predicted cards but the ``result`` verdict is invariant to WHICH prize is taken (so a
        prize take alone never demotes — `_rng_probe(prize=False)`).
        Lazy DLL import keeps the fast unit suite from ever loading the native engine.

        ``record`` (a list, ADR-0037 stage 3): materialize each cascade select this drive answers as
        ``{ctx, max, drive, chosen}`` — the picked options' identity tuples, ``drive``=True for an
        all-hidden-zone pick (prize area: the sim's ids are predictions, replay must policy-drive) —
        the confirmed-cascade record a verified lock replays (`lethal_veto`)."""
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
        self._planning = True                          # the cascade re-runs decide(): never nest a
        # This-turn boosts PLAYED inside the cascade (the sim's own Premium Power Pro plays) must be
        # priced by the boost tracker so a later step's decide() sees the running total (a multi-copy
        # boost line, ml f24). observe() is skipped under `_planning` for the REAL stream, so drive the
        # tracker explicitly from the sim's obs here — snapshot + restore so the match state a real
        # decision resumes on is untouched (the sim's future never leaks into the live tracker).
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
