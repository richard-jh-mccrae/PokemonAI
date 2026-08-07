"""The needs LEDGER (ADR-0127): what my board still needs, what each held card covers, and what holding it is therefore
worth.

Supply priced without demand inverts every card play — one Energy retires 16 Worth of need for 8 Worth of coverage.
`_resolve_needs` is the one assignment; every keep/shed/grab site consumes it rather than re-deciding."""
from __future__ import annotations


from common.card_worth import ENERGY_TIER
from common.deciders.facts import Board
from common.deciders.hand import _ENGINE_KEEP_TAGS, _ENGINE_SUPPORTER_KEEP


# WP-N5 (keep-value v2): the LATENT-worth discount on a held card that fills no specific need — its
# role tier is real board value even without an open slot (the readiness leaf's `contribution` for
# the HAND), but a not-yet-deployed card is worth less than one filling a live need. Sized at the
# leaf's bench position weight (`_READINESS_BENCH_DISCOUNT` 0.45 — a hand card is ~one deploy away,
# like a benched body). De-duplicated by the assignment (one slot per distinct card).
_GENERAL_WORTH_W = 0.45

_GENERAL_ILLIQUID_FLOOR = 0.15  # piece 2b (the shed's Hole-2 fix): a general-worth card whose value
                           # needs board state it hasn't got — an Energy with NO body that can receive
                           # and attack with it (a doomed Active, an empty Bench, no benchable body in
                           # hand) — prices at this fraction of its latent tier, not the full catalog
                           # worth. Illiquid held value you cannot spend is not worth clinging to over a
                           # refresh (ep83038055 f40: Ignition 13.5 + a bare {W} propped the shed above
                           # the redraw with no attacker in sight). NOT 0 — a residual future worth once
                           # a body lands keeps it above outright-dead cards in pitch order. Derived from
                           # the board, never a card list; a live recipient restores full worth (f65: an
                           # Ignition kept for the BENCHED Mega Starmie stays fully priced).


class NeedsMixin:
    """The needs assignment: demand, coverage, and what a held card is worth."""

    def _needs_v2(self, obs: dict, board: Board, rows: list, picks: int):
        """WP-N3 (keep-value v2, `keep-value-needs-assignment-grill-spec.md`): the Pilot-side needs
        RESOLVER — the live board resolved into `common.needs` slots / per-candidate eligibility /
        resupply, pricing per-row ``keep_v2`` (the raw counterfactual marginal,
        `needs.keep_v2`) and the v2 decider's pick (`needs.cheapest_removal`), hedged at v1's
        POST-GATE keep — the WP-N3 refinement: v2 never prices below the shipped decider (a
        raw-tier floor would undo the gate knowledge), and a firing floor telemeters a missing
        slot. Returns ``(keep_v2 per row, eq2_pick as OPTION indices)``.

        **This DECIDES**, unflagged (swapped in 2026-07-20 by ADR-0065 WP-N4): the forced discard's
        pick IS `eq2_pick` — see `_discard_needs_pick`, the consumer. This line has now been wrong in
        both directions, which is why it says so. It read "SHADOW-ONLY (Round 6): nothing here
        decides" for eleven days after the swap (corrected by POC-T1, Issue #260), then named
        `needs_keep_value` as the arming flag for the twelve days after Issue #261 item 2h stopped
        reading that flag at all (corrected by Issue #319, which deleted it). A stale claim about
        what gates this is worse than no note — it is the sentence a reader trusts when judging
        whether a change here is safe.

        v0 resolver scope (the discard bench's needs — the rest joins in WP-N4):
          * LINE slots per held card class at its line-role tier × the v1 deploy gate (dead
            evolution / dead-fetcher / need-met knowledge CONSUMED per the dissolution ledger); an
            in-play copy MEETS the primary slot; a wincon class adds the half-tier SUCCESSION slot
            (`needs.line_slots` — a spare wincon insures the line, never free).
          * DEPLOY-NOW slots off `Board.deploy_now_ids` (the spike, re-derived: the in-play copy
            does not cover THIS body's evolution).
          * FUND-ATTACK slots = the Active's biggest-attack cost remaining (the spent burst
            re-derived as slot ABSENCE; deadlines from the quota structure).
          * one saturating DRAW-ENGINE slot (engine Roles + the engine-supporter predicate).
          * SUPPLY-WINCON via `needs.supply_wincon_slot` (need-met = slot absence).
          * ANSWER-DOOM under the pressure read (successor / clutch_heal / switch).
          * FUEL slots ride the pitch side (`needs.pitch_gain` — pitching a matching Energy is
            progress).
          * opponent DENY slots (thread 2, the Round-3 ruled read): one per opponent in-play body
            a strip actually bites, valued by the SHIPPED ADR-0062 denial oracle and graded by the
            body's visible turns-to-ready (`_opp_turns_to_ready`) — the Hammer/gust classes' first
            v2 pricing (they still hedge-floor where the graded deny is small; note the oracle is
            DAMAGE-denominated, so a ready threat prices a deny slot above the worth tiers).
        Deferred, documented: probabilistic slot RESUPPLY at THIS site (0.0 here — a forced
        discard has no redraw window; errs toward keep. The REFRESH site's resupply is LIVE —
        `_refresh_slot_resupply` over the refresh draw window), non-Active fund bodies, and
        non-option hand cards as fixed coverage (a real forced discard offers the whole hand).

        The pick's ranking key carries two ORDERING legs below the score (ADR-0106) — see
        `_removal_ranking_legs`. Both only discriminate where the assignment prices removals EQUAL,
        which for a forced discard is the common case: that is what the pitch term exists to rank
        and what a keep FLOOR can never express."""
        from common import needs
        slots, elig = self._resolve_needs(obs, board, rows)
        resupply = [0.0] * len(slots)
        keeps = [round(needs.keep_v2(slots, elig, resupply, k), 1) for k in range(len(rows))]
        pick = needs.cheapest_removal(slots, elig, resupply, [r["keep"] for r in rows], picks,
                                      **self._removal_ranking_legs(rows))
        return keeps, sorted(rows[k]["i"] for k in pick)

    def _resolve_needs(self, obs: dict, board: Board, rows: list, *, include_general: bool = True):
        """The shared keep-value v2 RESOLVER: the live board + the held-card ``rows`` resolved into
        `common.needs` slots and per-row eligibility (which slot indices each row can supply). The
        ONE slot derivation behind BOTH the discard decider (`_needs_v2`) and the refresh SHED
        (`_refresh_shed_keepcost`) — rows need only ``cid``, ``deploy`` (the v1
        gate factor v2 consumes), and ``fuel``. Returns ``(slots, elig)``; the caller owns
        ``resupply`` — all-0.0 where no draw window backs a discount (the discard decider, the
        leaf), `_refresh_slot_resupply` at the refresh site. The slot vocabulary, the corpus-adjudicated
        derivations (the succession slot, Pokémon-only lines, the engine band, the fund/doom/fuel
        legs, the thread-2 opponent DENY leg) and the deferred legs are documented on `_needs_v2`.

        DENY slots and future per-slot resupply (the thread-1 closure discount, not yet landed
        here): the CLOSING-EDGE rule SHOULD apply — a deadline-0 deny slot (their body ready NOW)
        must take resupply 0.0 regardless of how many Hammers the deck could re-draw, because a
        deny needed THIS turn is not re-drawable in time (the same reasoning that makes the
        deploy_now spike and the deadline-0 answer_doom slot un-bankable). Deadline ≥ 1 deny slots
        may take their supplier classes' re-access odds over that window. Vacuous today (resupply
        is all-0.0), recorded here for the resupply thread.

        ``include_general=False`` (WP-N5c, the develop-rung LEAF's term) drops the GENERAL-worth
        slots — a card's latent tier where it fills no SPECIFIC need. Keep-value WANTS them (deciding
        what to shed prices a spare by its latent worth), but the LEAF must NOT: at end-of-turn a
        generically-good card still IN hand is a card I chose not to deploy, so crediting its latent
        worth rewards HOARDING over deploying (the WP-N5b regression — 676/677 held for +23 beat the
        line that played them). The grill's own term is "held cards with a LIVE use" = the SPECIFIC
        needs only (deploy-now / fund / answer-doom / supply-wincon / fuel / line), not latent worth."""
        from common import currency, needs
        from common.card_worth import ROLE_TIER, ACE_SPEC_TIER, ENERGY_TIER, TAG_TIER
        me = self._my_player(obs)
        line_roles = {r for r, kinds in needs.SUPPLIES.items() if "line" in kinds and r in ROLE_TIER}
        slots: list = []
        elig: list = [set() for _ in rows]

        # The PLAYABILITY gate (ADR-0104, Issue #288 — the audit's F12): a card that can NEVER be
        # played covers NOTHING. Applied to the ELIGIBILITY construction rather than to any one
        # slot's value, which is the whole point — the shipped `deploy` factor already zeroes the
        # slots keyed on the card ITSELF (`line`, `general`), but left the row eligible for every
        # SHARED slot, so a stranded engine evolution both covered its deck's draw need (the real
        # Supporter beside it priced 0 and shed for free) and RAISED that slot's band to the
        # engine-BODY tier, because the band reads off its eligible rows. `deploy` is also the wrong
        # predicate to reuse: it folds in the fetcher and need-met gates, whose cards are perfectly
        # playable and must keep supplying. Deriving it here rather than off the rows keeps the ONE
        # resolver answering for every caller — including `_deploy_decision`, whose DECK rows carry
        # no hand zone at all.
        unplayable = self._unplayable_rows(obs, board, rows)

        def _emit(slot, members) -> None:
            suppliers = _playable_only(members)
            if not suppliers:
                return                             # a need only its dead cards could fill is no need
            j = len(slots)
            slots.append(slot)
            for m in suppliers:
                elig[m].add(j)

        def _playable_only(ks) -> list:
            """The candidate rows of a leg, minus the unplayable ones. Applied to EVERY leg's
            candidate list rather than only to `_emit`, because two legs read their SLOT VALUE off
            the candidates: `draw_engine`'s band is the engine-BODY tier if any candidate is an
            engine body, and the general-worth suppression set is keyed off the same list. Filtering
            only at emission would have left a dead engine body pricing its deck's draw need at 12
            instead of the engine-supporter band 8 (measured on `grimmsnarl_ex`'s stranded Froslass;
            that deck was deleted by PR #436, and `tests/strategy/test_playability_gate.py` now
            carries the case on `slowking`'s Slowpoke -> Slowking)."""
            return [k for k in ks if k not in unplayable]

        def _tags(cid) -> set:
            return set(self.functions.tags(cid)) if (self.functions and cid is not None) else set()

        by_cid: dict = {}
        for k, r in enumerate(rows):
            by_cid.setdefault(r["cid"], []).append(k)
        for cid, members in by_cid.items():
            st = self.stats.get(cid) if self.stats else None
            roles = self._roles_of(cid)
            if cid in self._line_preevo_set():
                roles = [*roles, "win_condition_base"]   # the derived line-member worth (WORTH-ONLY)
            # A LINE slot is a BODY to assemble — Pokémon only (an ACE-SPEC Trainer keeps its
            # one-per-deck line claim). An Energy with a line-class derived role (Ignition as
            # `accel_source`) must NOT reopen a line: it resurrects the spent burst the fund-attack
            # absence just re-derived (corpus 83454549-36).
            worth = 0.0
            if st is not None and getattr(st, "is_pokemon", False):
                worth = max((ROLE_TIER[r] for r in roles if r in line_roles), default=0.0)
            if st is not None and getattr(st, "aceSpec", False):
                worth = max(worth, ACE_SPEC_TIER)
            deploy = rows[members[0]].get("deploy", 1.0)
            if worth * deploy > 0:
                # URGENT succession (the answer-doom ruling): MY Active is doomed and this class is
                # the successor with its base already in play — its replacement is needed imminently,
                # so its succession slot goes FULL tier at deadline 0 (the old answer-doom successor
                # spike, re-derived as the line's OWN worth; the successor no longer rides the flat
                # answer-doom slot). Same granularity as the retired answer-doom test.
                # NOTE (Issue #261 wave-2, ep83117367 f34): narrowing this to a base that is
                # EVOLVABLE THIS TURN (`_successor_evolvable_now`) was built and REVERTED — it
                # contradicts the ruling this spike exists for. `line_slots`' own docstring rules the
                # turn-fresh case explicitly: "don't Harlequin away the second Mega Starmie **the
                # turn its Staryu hit the bench**" (ep83037962 f49). The need is created by the Active
                # DYING, not by the evolve being legal today, so a successor whose base arrived this
                # turn is still needed imminently. f34's residual regression is a live ruling conflict
                # between those two frames, recorded in ADR-0101, NOT a defect to patch here.
                urgent = bool(board.active_doomed and cid in self._wincon_set()
                              and getattr(board, "line_preevo_in_play", False))
                # READINESS (piece 1): the primary comes online when its base is in play AND already
                # powered (evolve next turn, attack soon ⇒ deadline 1); a base in play but unpowered,
                # or not yet benched, is a turn further (2). The backup (succession) is one hop behind
                # the primary. Consumed ONLY by the refresh-SHED resupply window (`_refresh_slot_
                # resupply`) — inert for the live discard decider, which reads no deadline. Two live
                # Staryu that make both Mega Starmie imminent lines can no longer be shed for ~nothing.
                line_deadline = self._line_readiness_deadline(me, cid)
                for s in needs.line_slots(f"line:{cid}", value=worth * deploy,
                                          succession=bool(set(roles) & needs.SUCCESSION_ROLES),
                                          primary_met=cid in board.in_play_ids,
                                          succession_urgent=urgent,
                                          deadline=line_deadline,
                                          succ_deadline=line_deadline + 1):
                    _emit(s, members)
            if cid in getattr(board, "deploy_now_ids", frozenset()):
                _emit(needs.deploy_now_slot(f"deploy:{cid}", value=self._role_value(cid)), members)
        tutors = _playable_only([k for k, r in enumerate(rows)
                        if r.get("deploy", 1.0) > 0
                        and ("tutor" in self._roles_of(r["cid"])
                             or ({"rush_evolve", "tutor_mega"} & _tags(r["cid"])))])
        supply = needs.supply_wincon_slot(
            wincon_in_hand=bool(getattr(board, "wincon_in_hand", False)), target_reachable=True)
        if supply is not None and tutors:
            _emit(supply, tutors)

        def _engine(cid) -> bool:
            st = self.stats.get(cid) if self.stats else None
            return ("engine" in self._roles_of(cid)
                    or bool(st is not None and getattr(st, "is_supporter", False)
                            and (_ENGINE_KEEP_TAGS & _tags(cid))
                            and "hand_disruption" not in _tags(cid)))

        engines = _playable_only([k for k, r in enumerate(rows) if _engine(r["cid"])])
        if engines:
            online = sum(1 for pid in board.in_play_ids if "engine" in self._roles_of(pid))
            # The band reads off the eligible suppliers: an engine BODY need is the engine-role
            # tier; a supporter-only need is v1's tuned engine-supporter band (corpus 83686860-11
            # — a 12-point Lillie's out-priced the fund Energies the human keeps).
            band = (ROLE_TIER["engine"]
                    if any("engine" in self._roles_of(rows[k]["cid"]) for k in engines)
                    else _ENGINE_SUPPORTER_KEEP)
            _emit(needs.draw_engine_slot(engines_online=online, value=band), engines)
        active = next((p for p in (me.get("active") or []) if p), None)
        if active is not None:
            ast = self.stats.get(active.get("id")) if self.stats else None
            remaining = max(0, (getattr(ast, "maxDamageCost", 0) or 0)
                            - len(active.get("energies") or []))
            funders = _playable_only([k for k, r in enumerate(rows)
                             if getattr(self.stats.get(r["cid"]) if self.stats else None,
                                        "is_basic_energy", False)
                             or "discard_eot" in _tags(r["cid"])])
            if remaining and funders:
                for s in needs.fund_attack_slots("active", remaining,
                                                 quota_spent=bool(board.energy_attached)):
                    _emit(s, funders)
        if board.active_doomed:
            # The answer-doom slot is now the SWITCH/HEAL rescue only (the successor rides the URGENT
            # succession slot above), VALUED at the doomed body's OWN preserved worth (the grill
            # ruling): saving the Active is worth exactly what the Active is worth — a Switch that
            # rescues a 12-point engine Lunatone earns 12 (ep83661652 f40), a filler active earns ~0
            # and is not worth a card to save. NOT the flat clutch_heal tier, NOT the swap's catalog
            # worth. No slot when the active is worthless (`_role_value` 0 → `answer_doom_slot`
            # emits value 0, priced out by the assignment).
            answers = _playable_only([k for k, r in enumerate(rows)
                             if {"clutch_heal", "switch"} & _tags(r["cid"])])
            preserved = self._role_value(active.get("id")) if active is not None else 0.0
            if answers and preserved > 0:
                _emit(needs.answer_doom_slot(value=preserved), answers)
        # OPPONENT DENY SLOTS (thread 2; the grill's Round-3 ruling — VISIBLE state + basic
        # lookahead of their IN-PLAY bodies only): one slot per opponent body a strip actually
        # bites, VALUED at the DISRUPTION CARD-TIER (the grill's currency ruling, 2026-07-20 — the
        # deny slot is worth the card-worth of holding the strip, ~10 in the ONE currency, NOT the
        # ADR-0062 DAMAGE swing ~140; whether to FIRE the strip is a line evaluation the play-side
        # gust rungs own, not a keep price) and GRADED by the body's visible turns-to-ready
        # (`needs.deny_slot` — a ready threat's strip is worth its full card tier, a far-off one
        # discounts; the 86091435-68 ruling with timing). The ADR-0062 oracle (`_denial_at`) was a
        # GATE only here — `> 0` = the strip BITES this body — and Issue #228 deleted it: relevance
        # > 0 SUBSUMES that gate (it is already 0 for a bare body, for surplus Energy and for one
        # dying to my KO this turn, the `active_can_ko` drop consumed intact). Eligibility
        # routes through the SUPPLIES net: any held row carrying a deny-supplying tag
        # (gust / energy_denial). Fail-closed everywhere: no deny-capable row, no opponent read,
        # unknown stats (`_opp_turns_to_ready` → None) or a strip that bites nothing → NO slot —
        # those rows keep pricing at the shipped hedge. The disruption band is the ONE-currency
        # gust tier (`TAG_TIER["gust"]`, ~10) — NOT each denier's global worth (a role-less Hammer
        # stays worth 0 globally; only its live-strip DENY slot earns the band), so the leaf and
        # every other worth site are untouched.
        # ADR-0076: gust ALWAYS supplies both "deny" and "gust_target" kinds (`needs.SUPPLIES`), but
        # only ONE is ever LIVE for a given decision — armed, gust rows route to their own instrument
        # instead of riding the flat deny tier (a Boss's Orders doesn't strip Energy; pricing it
        # through `deny`'s oracle-value/timing-grade shape never matched what it actually does). OFF
        # (default) leaves `deny_tags` exactly as shipped — byte-identical.
        deny_tags = {src for src, kinds in needs.SUPPLIES.items() if "deny" in kinds}
        gust_tags = {src for src, kinds in needs.SUPPLIES.items() if "gust_target" in kinds}
        if self.gust_target_slots:
            deny_tags = deny_tags - gust_tags
        deniers = _playable_only([k for k, r in enumerate(rows) if deny_tags & _tags(r["cid"])])
        deny_tier = TAG_TIER["gust"]
        # ARMED (ADR-0080, Issue #187): the keep price stops being the FLAT disruption tier and becomes
        # `tier x relevance(this body)` — a Hammer is worth keeping in proportion to how much the
        # Energy it would take is actually doing. The `/2^t` turns-to-ready GRADE is retained (user
        # ruling, 2026-07-30): relevance is deliberately not imminence-gated — it scans the whole line
        # including forward forms, which is what lets a Riolu's banked {F} score at all — so the grade
        # is the only term pricing WHEN the threat lands. Per-body rather than a board-level max, so
        # each body keeps its own deadline; the DP then picks the best assignment, which is the max.
        deny_rel = self._deny_relevance_map(obs, board) if self.deny_relevance else {}
        if deniers and self.deny_relevance:
            state = obs.get("current") or {}
            players = state.get("players") or []
            yi = state.get("yourIndex", 0)
            opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else None
            areas = [("bench", (opp or {}).get("bench") or [])]
            if not board.active_can_ko:
                areas.insert(0, ("active", (opp or {}).get("active") or []))
            for area, bodies in areas:
                for bi, p in enumerate(bodies):
                    # relevance > 0 SUBSUMES the ADR-0062 bite gate: it is already 0 for a body
                    # with no Energy, for surplus Energy, and for one dying to my KO this turn. The
                    # OFF branch here read `_denial_at` as that gate; both are DELETED (Issue #228,
                    # directive 1) and OFF now emits no deny slot at all — degraded, not a rollback.
                    value = deny_tier * max((deny_rel.get((area, bi)) or {}).values(), default=0.0)
                    if not p or value <= 0:
                        continue
                    t = self._opp_turns_to_ready(p)
                    if t is None:
                        continue               # unknown stats — fail closed, no deny slot
                    _emit(needs.deny_slot(f"deny:{area}{bi}:{p.get('id')}",
                                          oracle_value=value, turns_to_ready=t), deniers)
        # GUST-TARGET SLOTS (ADR-0076, kill-switched): held gust-effect Trainer cards keep-priced
        # against the REAL per-body removal value (`_opponent_target_rows`) — reads the per-decision
        # cache `_board()` stashes when one exists (never recomputed
        # twice per decision), falling back to a fresh compute for a hand-built `board` that never
        # went through `_board()` (test fixtures). Not a flat card tier. Bench ONLY — a gust effect
        # forces a switch of a BENCHED Pokémon (verified at source, `doctrine_gust.py`); the
        # opponent's Active is never a legal gust target, so it never opens a slot here (unlike deny,
        # which strips Energy off either area).
        # DENOMINATION (ADR-0107, Issue #313 item 2g — ADR-0080 decision 4 re-inheriting ADR-0076's
        # currency debt): the row's `value` is PRIZE-equivalents and this assignment sums CARD-WORTH
        # points, so it crosses at the seam-scoped `currency.target_value_to_worth` — the marginal's
        # own derived ceiling (3.9) divided out to a [0,1] fraction of the disruption band, which is
        # the identical `band x fraction` shape the armed `deny` slot above already has. Fed raw it
        # topped out at 3.9 against a wincon's 30 and usually lost even to the SAME card's `general`
        # slot (up to 4.5), so the assignment covered a `gust_target` slot on 1 corpus frame in 80 —
        # measured, not inferred. Denominated: 25 in 80.
        if self.gust_target_slots:
            gusters = _playable_only([k for k, r in enumerate(rows) if gust_tags & _tags(r["cid"])])
            if gusters:
                # ONE ladder, `_deny_rows` — this used to open-code the cache-or-compute walk, a
                # second spelling of the same three lines. Issue #228 extracted
                # `_best_area_weighted_relevance` for
                # exactly that reason and would have left this copy behind.
                target_rows = self._deny_rows(obs, board)
                if target_rows:
                    for r in target_rows:
                        if r["area"] != "bench" or r["value"] <= 0:
                            continue           # off-area, or a removal that isn't worth anything
                        _emit(needs.gust_target_slot(
                            f"gust_target:{r['area']}{r['bi']}:{r['id']}",
                            value=currency.target_value_to_worth(r["value"])),
                            gusters)
        fuels = _playable_only([k for k, r in enumerate(rows) if r.get("fuel")])
        if fuels:
            _emit(needs.fuel_slot("fuel", value=ENERGY_TIER), fuels)
        # GENERAL-WORTH slots (WP-N5): a held card with role worth that fills no SPECIFIC need still
        # carries LATENT board value — its tier, discounted (`_GENERAL_WORTH_W`, the leaf's bench
        # position weight) and DE-DUPLICATED (one slot per distinct cid, so spare copies price
        # marginally). Below every specific slot, so a need-filler assigns to its need first; the
        # floor the refresh-SHED sweep (WP-N4b) proved missing — a hand of playable pieces is no
        # longer shuffle-priced at ~0. The readiness leaf's `contribution × saturation` for the HAND.
        # The LEAF opts OUT (`include_general=False`, WP-N5c): at end-of-turn latent worth rewards
        # HOARDING over deploying (676/677 held for +23 beat the line that played them) — the leaf's
        # actionable-resource term is "held cards with a LIVE use" (the specific needs above) only.
        # A card class eligible for the SATURATING draw-engine need gets NO general slot (the
        # duplicate-Supporter ruling, 2026-07-20): one copy fills the one-per-turn need, the SPARE
        # covers nothing and prices 0 — "a second copy of a Supporter is 0; you'll lose it in a
        # shuffle for free" (ep82522698 f36, two Wally's). The residual-worth tiebreak still ranks
        # the spare above outright dead cards in pitch order; it just carries no keep value.
        engine_cids = {rows[k]["cid"] for k in engines}
        seen_general: set = set()
        for cid, members in (by_cid.items() if include_general else ()):
            if cid in seen_general or cid in engine_cids:
                continue
            seen_general.add(cid)
            # A row the PITCH term flags as dead-weight (spent_burst / fuel / dead_opener / stranded
            # / redundant_tutor / fodder) is fodder NOW — no LATENT worth, no general slot (else the
            # general worth RESURRECTS a spent burst v1 correctly zeroed — c4f5, the 83454549-36 trap
            # again). Context-correct: refresh rows carry no pitch flag (a SHUFFLED burst IS a future
            # attach), so they keep their general worth.
            live = [m for m in members if rows[m].get("pitch", 0) == 0]
            if not live:
                continue
            worth = self._role_value(cid)
            deploy = rows[live[0]].get("deploy", 1.0)
            if worth * deploy > 0:
                liq = self._general_liquidity(cid, board, me)   # piece 2b: illiquid latent worth discounts
                # INSURANCE, not latent worth (ADR-0101 amendment, Issue #261 wave-2 ruling on
                # ep83969481 f55): `_GENERAL_WORTH_W` prices a card that is ~one deploy away from
                # mattering. A `clutch_heal` covering an IRREPLACEABLE Active is not one deploy away —
                # it is the survival plan, and the latency haircut is simply the wrong model of it.
                # Full tier at deadline 1 (the threat is NEXT turn, which is why `answer_doom` — a
                # this-turn read — correctly stays shut here; reviewed.json rules exactly that), and
                # the slot takes the answer-doom KIND so it also takes that kind's closing edge:
                # `_refresh_slot_resupply` gives it no re-access credit. Deliberate — the ruling is
                # about CERTAINTY, and a heal you are relying on to survive may not be priced at
                # "I'll probably redraw it". `needs.insure_wincon_slot` carries the reasoning.
                if self._heal_insures_the_last_wincon(cid, me):
                    _emit(needs.insure_wincon_slot(f"insure:{cid}", value=worth * deploy), live)
                    continue
                _emit(needs.general_worth_slot(f"general:{cid}",
                                               value=worth * deploy * _GENERAL_WORTH_W * liq), live)
        return slots, elig

    def _rare_candy_reachable(self, ids) -> bool | None:
        """Does any card in ``ids`` carry the `rare_candy` Function Tag? ``None`` when there is no
        tag table to ask — the tri-state `playability.Zones.rare_candy` documents, and the reason
        this is a method rather than an inline `any(...)` at each of its two call sites."""
        if not self.functions:
            return None
        from common import playability
        return any(playability.RARE_CANDY_TAG in set(self.functions.tags(cid)) for cid in ids)

    def _playability_zones(self, board: Board, counts: dict):
        """The zone reads `common.playability` walks: what is IN PLAY (the walk grounds out there),
        what is REACHABLE (my hand plus the sound ``counts`` deck read), and whether a Rare Candy is
        reachable at all (its Stage-2 escape).

        Rare Candy is found by its `rare_candy` Function Tag rather than by card id — ADR-0006's
        rule, and the reason `planner._is_rare_candy` now reads the same tag instead of a private
        constant. With no tag table the read is ``None``, not ``False``: `Zones.rare_candy` is
        tri-state precisely so a missing table cannot be mistaken for a missing Rare Candy.

        Memoised for the decision on the IDENTITY of its two inputs: `_deploy_odds` asks per ROW, so
        a ten-card hand rebuilt these frozensets ten times over the same board. The cache holds
        strong references to ``board`` and ``counts`` rather than their ``id()``s deliberately — an
        id-keyed cache is a use-after-free waiting to happen, since CPython reuses the address of a
        collected object and the next dict built there would silently read the old answer."""
        from common import playability
        cached = getattr(self, "_playability_zone_cache", None)
        if cached is not None and cached[0] is board and cached[1] is counts:
            return cached[2]
        hand_ids = frozenset(getattr(board, "hand_ids", None) or ())
        deck_ids = frozenset(cid for cid, n in (counts or {}).items() if n > 0)
        zones = playability.zones(self.stats, hand_ids=hand_ids, deck_ids=deck_ids,
                                  in_play_ids=getattr(board, "in_play_ids", None) or (),
                                  rare_candy_reachable=self._rare_candy_reachable(hand_ids | deck_ids))
        self._playability_zone_cache = (board, counts, zones)
        return zones

    def _unplayable_rows(self, obs: dict, board: Board, rows: list) -> frozenset:
        """Row indices whose card can NEVER be played (ADR-0104). The `_resolve_needs` gate.

        Fails OPEN as a whole without a stat provider: with no card facts there is no evidence, and a
        gate that strips eligibility on missing evidence would shed live cards — the fail direction
        the whole keep-value family forbids. A missing Function Tag table is NOT such a case and does
        not disable the gate; the ``evolvesFrom`` question needs no tags, and the one part that does
        (the Rare Candy escape) fails open by itself through `Zones.rare_candy`'s ``None``. Putting
        that epistemic in the oracle rather than here is what keeps this gate and
        `_stranded_evolution_set` — the same oracle's other caller — from failing in opposite
        directions on the same missing table.

        Deck-availability comes from the ONE `_unseen_deck_counts` read, so the gate cannot disagree
        with the `deploy` factor, which resolves the same oracle over the same counts."""
        if not self.stats or not rows:
            return frozenset()
        from common import playability
        counts = self._unseen_deck_counts(self._my_player(obs), board)
        zones = self._playability_zones(board, counts)
        verdict: dict = {}
        dead = set()
        for k, r in enumerate(rows):
            cid = r.get("cid")
            if cid not in verdict:
                verdict[cid] = playability.playable_from_hand(cid, stats=self.stats, zones=zones)
            if not verdict[cid]:
                dead.add(k)
        return frozenset(dead)

    def _needs_hand_rows(self, obs: dict, board: Board, exclude_cid=None) -> list:
        """The whole-hand v2 rows for the refresh SHED: one row per held card (minus ONE copy
        of ``exclude_cid`` — the played refresh, discarded not shuffled, exactly as v1's
        `_hand_keep`), carrying the fields `_resolve_needs` reads (``cid``, ``deploy`` — the v1 gate
        factor v2 consumes — and ``fuel``) plus ``worth`` for display. The refresh analog of
        `_discard_equation_rows`' per-card facts, over the hand instead of the discard options."""
        me = self._my_player(obs)
        hand_ids = [c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None]
        ids = list(hand_ids)
        if exclude_cid in ids:
            ids.remove(exclude_cid)
        counts = self._unseen_deck_counts(me, board)
        fuel_types = self._discard_fuel_types()
        # ``i`` is the ROW ordinal — it indexes this list, which is the alignment `_resolve_needs`'
        # eligibility and `needs.cheapest_removal`'s picks are in. ``hand_i`` is the card's position
        # in the REAL hand, which is a different number the moment `exclude_cid` drops a card before
        # it: with hand [X, Ball, Y] excluding Ball, Y is row 1 and hand index 2. Both are needed and
        # neither can stand in for the other, so both are carried rather than one being re-derived —
        # a caller re-spelling the filter would drift the day this one changes.
        positions = [p for p, cid in enumerate(hand_ids)]
        if exclude_cid in hand_ids:
            positions.pop(hand_ids.index(exclude_cid))
        rows = []
        for k, cid in enumerate(ids):
            st = self.stats.get(cid) if self.stats else None
            fuel = bool(st is not None and getattr(st, "is_basic_energy", False)
                        and (None in fuel_types or getattr(st, "energyType", None) in fuel_types))
            rows.append({"i": k, "hand_i": positions[k], "cid": cid,
                         "worth": round(self._role_value(cid), 1),
                         "deploy": self._deploy_odds(cid, board, counts), "fuel": fuel})
        return rows

    def _item_hold_price(self, obs: dict, board: Board, cid) -> float:
        """What SPENDING held card ``cid`` costs, in the damage currency — the ONE hold price every
        free-Item decider subtracts (Issue #261 item 2f, old Issue #212; the equation and its
        reasoning are `common/hold_value.py`).

        The Pilot-side half is a resolver, nothing more: it reads the hand through the SAME
        `_needs_hand_rows` → `_resolve_needs` pair the refresh SHED (`_refresh_shed_keepcost`) and the
        discard decider (`_needs_v2`) read, and asks `needs.keep_v2` for this card's counterfactual
        marginal. One keep question, one answer — a second opinion about what a held card is worth is
        exactly the drift ADR-0103 amendment A had to unwind on the shed predictor.

        **Resupply is all-0.0, and that is a policy rather than a stub.** It is the discard decider's
        own setting, for the discard decider's own reason: playing a card opens no draw window to
        re-access it through, so nothing discounts the loss. The refresh site is the exception that
        proves it — `_refresh_slot_resupply` exists there because the refresh's printed draw count IS
        a redraw window. Erring toward KEEP is also the safe direction here: it can only make a free
        Item harder to spend.

        The whole hand is priced, INCLUDING the card being played (no `exclude_cid`): the question is
        what losing this copy costs, which is precisely `keep_v2`'s counterfactual, and duplicates
        price marginally through the assignment rather than by hand. A card that is not in hand at all
        (a fetched option, a hand-built test board) resolves to no row and takes the bare floor —
        fail-toward-the-incumbent, since the floor is what the deleted constant charged.

        Memoised per DECISION, keyed by card id: `_denial_play_tactical` runs per option, a hand
        routinely holds two copies of the same Item, and `_resolve_needs` walks the whole hand each
        time. The cache is reset in `_board()`, which is per `_evaluate` — so a rollout step, which
        re-runs `_evaluate` on its own SearchState, gets its own resolution rather than the root's."""
        from common import hold_value, needs
        cache = self._item_hold_cache
        if cid in cache:
            return cache[cid]
        keep = 0.0
        if cid is not None:
            rows = self._needs_hand_rows(obs, board)
            k = next((i for i, r in enumerate(rows) if r["cid"] == cid), None)
            if k is not None:
                slots, elig = self._resolve_needs(obs, board, rows)
                keep = needs.keep_v2(slots, elig, [0.0] * len(slots), k)
        price = cache[cid] = hold_value.hold_price(keep)
        return price

    def _general_liquidity(self, cid, board: Board, me: dict) -> float:
        """PIECE 2b: the LIQUIDITY factor on a general-worth slot ∈ (`_GENERAL_ILLIQUID_FLOOR`, 1] —
        how realizable a card's LATENT worth is on the current board. An Energy with no recipient
        (`_has_energy_recipient` False) prices at the floor: catalog worth you cannot spend is not
        worth holding over a refresh (the shed mirror of piece 1's line-slot readiness — same idea, the
        keep side). 1.0 (unchanged) for everything with a live use, so only the genuinely stranded card
        is discounted; never a card list. Extends to other role-blocked worth (an evolver with no base)
        as the corpus demands — energy is the dominant f40 term and the first cut."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        if st is not None and getattr(st, "is_energy", False) and not self._has_energy_recipient(board, me):
            return _GENERAL_ILLIQUID_FLOOR
        return 1.0
