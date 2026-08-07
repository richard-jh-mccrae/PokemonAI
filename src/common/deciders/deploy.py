"""The deploy decider (ADR-0086): what benching this body is worth against the prizes it exposes, plus the resupply and
recover reads behind it.

Exposure is priced as a COST, never as a veto — a 2-prize body with an Ability payoff can still be the right bench."""
from __future__ import annotations


import copy
import dataclasses

from common.deciders.facts import Board, _slot_cid
from common.deciders.hand import _ENGINE_KEEP_TAGS, _ENGINE_SUPPORTER_KEEP
from common.grading import HORIZON as _HORIZON
from common.strategy.context import ENERGY_RECOVER, _BENCH_MAX, _BENCH_PLACEMENT_CONTEXTS, _MAIN, _PLAY, _TO_BENCH



class DeployMixin:
    """What putting this body on the Bench is worth, against what it exposes."""

    def _is_body_card(self, cid) -> bool:
        """``cid`` is a Pokémon — a card that costs a BENCH slot, which is the only capacity the
        deploy path bounds. A Trainer covering a draw need takes no slot, so it is not a supplier
        here however much the assignment values it."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        return bool(st is not None and getattr(st, "is_pokemon", False))

    def _deploy_offered_ids(self, obs: dict, select: dict) -> list:
        """The card ids a `_TO_BENCH` select actually OFFERS, one per option — the Poffin-class
        fetch's revealed candidates (ADR-0086 decision 6's third entry point).

        These are deck cards, but they are **not** deck RESUPPLY: the search has already found them
        and the only remaining question is which go onto the Bench. So they are certain suppliers,
        exactly like a body in hand, and `_deploy_supplier_rows` takes them as such. One row per
        OPTION rather than per distinct id, because two copies of the same species are two physical
        bodies that can both be placed.

        Read off the MENU, which during `_greedy_grab`'s re-score still lists candidates already
        taken this multi-pick. That is deliberate rather than overlooked: the greedy re-scores
        against a virtual board where those bodies are already in play, so the needs they covered are
        closed and their rows are eligible for nothing — while `my_bench` has risen, which is what
        actually tightens the capacity. Filtering them out would need the acquired set threaded
        through the trace path for no change in the answer."""
        return [cid for opt in (select.get("option") or [])
                if self._is_body_card(cid := self._option_card_id(obs, select, opt))]

    def _deploy_supplier_rows(self, obs: dict, board: Board, *, offered=()):
        """``(ready_rows, deck_rows)`` — the bodies competing for my free Bench slots, split by
        CERTAINTY because the two are not interchangeable (ADR-0086 decision 2).

        Only POKÉMON: capacity here is BENCH capacity, and a Trainer covering a draw need costs no
        Bench slot.

        **The split is the whole point, and the first build got it wrong.** Deck-reachable bodies
        were handed to the assignment as full rival SUPPLIERS, so every hand copy had a deck twin
        covering the same slot — and a body whose slot a sibling already covers prices 0 (the
        sets-not-sums rule, working exactly as designed). With the deck always holding a twin, that
        zeroed nearly every deploy in the corpus and the sweep read `(no-deploy)` on frames the agent
        obviously should bench.

        A deck copy is NOT a substitute for one in hand: you have to draw it. So the deck leg enters
        as slot **RESUPPLY** — the odds the closure re-fills that slot anyway, which discounts the
        held copy to ``v × (1 − r)`` — which is what `resupply` exists for and what decision 2's
        "weighted by Deck-Content Odds" describes.

        ``offered`` is what makes the split about CERTAINTY rather than about the zone. A
        `_TO_BENCH` candidate is a deck card the search has ALREADY found, so no draw stands between
        it and the Bench — it belongs on the ready side with the hand, and its copy is removed from
        the deck counts so the same physical card cannot also re-supply the slot it is about to
        fill (which would discount it against itself)."""
        me = self._my_player(obs)
        counts = self._unseen_deck_counts(me, board)

        offered = [cid for cid in offered if self._is_body_card(cid)]
        if offered:
            counts = dict(counts)
            for cid in offered:
                if counts.get(cid, 0) > 0:
                    counts[cid] -= 1
            counts = {cid: n for cid, n in counts.items() if n > 0}

        ready_rows = []
        for c in (me.get("hand") or []):
            cid = (c or {}).get("id")
            if self._is_body_card(cid):
                ready_rows.append({"i": len(ready_rows), "cid": cid, "zone": "hand",
                                   "worth": round(self._role_value(cid), 1),
                                   "deploy": self._deploy_odds(cid, board, counts), "fuel": False})
        for cid in offered:
            ready_rows.append({"i": len(ready_rows), "cid": cid, "zone": "offered",
                               "worth": round(self._role_value(cid), 1),
                               "deploy": self._deploy_odds(cid, board, counts), "fuel": False})
        deck_rows = []
        for cid in sorted(c for c in counts if self._is_body_card(c)):
            deck_rows.append({"i": len(ready_rows) + len(deck_rows), "cid": cid, "zone": "deck",
                              "worth": round(self._role_value(cid), 1),
                              "deploy": self._deploy_odds(cid, board, counts), "fuel": False})
        return ready_rows, deck_rows

    def _deploy_line_deadline(self, me: dict, cid) -> int:
        """When the line THIS held body belongs to comes online, in turns — the deploy path's
        readiness read.

        `_line_readiness_deadline` answers the held-PAYOFF direction ("is my Riolu in play, so this
        Mega is live?"). For a held BASE it is structurally 99: nothing in play forward-evolves INTO
        a Basic, so no base is ever found. Correct for the shed question it was built for, and
        useless for this one — deploying a base is precisely what STARTS its clock.

        So a held body that is itself a line pre-evolution reads its own hop instead: benching it now
        means evolving next turn, so a single-hop base (Riolu -> Mega Lucario ex) is deadline 1.
        Anything else defers to the payoff-direction helper unchanged."""
        if cid is None:
            return 99
        if cid in self._line_preevo_set():
            forward = self._forward_card_ids(cid) or ()
            if any(f in self._wincon_set() or f in self._line_member_set() for f in forward):
                return 1                       # bench now, evolve next turn
        return self._line_readiness_deadline(me, cid)

    def _deploy_resupply(self, board: Board, slots: list, elig_all: list, hand_n: int,
                         deck_rows: list) -> list:
        """Per-slot RESUPPLY from the deck leg: how likely the closure re-fills each slot without
        spending a Bench slot on a held body now.

        The odds a deck body actually arrives, not merely that it exists: its Deck-Content Odds
        (`deck_contains_probability` — could it be prized?) times the `deploy` gate the resolver
        already applies per row (a dead evolution re-supplies nothing). A RANKED read, so it weights
        the marginal and never gates it (ADR-0074)."""
        resupply = [0.0] * len(slots)
        for k, row in enumerate(deck_rows):
            j_set = elig_all[hand_n + k] if hand_n + k < len(elig_all) else ()
            if not j_set:
                continue
            p = 1.0
            if hasattr(board, "deck_contains_probability"):
                try:
                    p = float(board.deck_contains_probability(row["cid"]))
                except Exception:
                    p = 1.0
            odds = max(0.0, min(1.0, p * float(row.get("deploy", 1.0))))
            for j in j_set:
                if 0 <= j < len(resupply):
                    resupply[j] = max(resupply[j], odds)
        # The CLOSING EDGE — whether the deck delivers IN TIME, not merely whether it delivers.
        # `_resolve_needs`' own docstring specifies this rule and records it as not yet landed: "a
        # deadline-0 slot must take resupply 0.0 regardless of how many the deck could re-draw,
        # because one needed THIS turn is not re-drawable in time" — the same reasoning behind the
        # deploy-now spike and the deadline-0 answer-doom slot.
        #
        # It is what stops SCARCITY standing in for URGENCY. Without it two equal-tier lines are
        # separated by re-drawability alone, so a win-condition base the deck holds more of sinks
        # beneath a scarcer secondary line — 83661652-44, where Makuhita priced 16.67 against Riolu's
        # 2.19 because the deck held no more Makuhita and 87% odds of another Riolu. Both facts are
        # true; they are answers to different questions.
        #
        # Graded against the shared HORIZON rather than a constant invented here: a latent slot
        # (deadline 99) keeps its full re-access credit, a deadline-1 slot keeps ~1/9 of it.
        for j, s in enumerate(slots):
            dl = max(0, int(getattr(s, "deadline", 99) or 0))
            resupply[j] *= min(1.0, dl / float(_HORIZON))
        return resupply

    def _last_ditch_spent(self, me: dict) -> bool:
        """Has a "Last-Ditch" Ability already fired this turn?

        Read SOUNDLY off the board rather than tracked: the card's own text caps it at one per turn
        ("You can't use more than 1 Ability that has 'Last-Ditch' in its name each turn"), and the
        Ability fires on the bench-drop — so a `supporter_tutor` body that ``appearThisTurn`` IS the
        spent use. Same field `_deploy_now_ids` reads for evolution eligibility."""
        for b in (me.get("bench") or []):
            if not b or not b.get("appearThisTurn"):
                continue
            tags = set(self.functions.tags(b.get("id"))) if self.functions else set()
            if "supporter_tutor" in tags:
                return True
        return False

    def _deploy_decision(self, obs: dict, select: dict, board: Board, option: dict):
        """Price ONE candidate Bench deployment — the Pilot half of ADR-0086: resolve board facts
        into `DeployInputs` and delegate. None when the switch is off or the option is not a body
        reaching my Bench.

        **All three entry points** decision 6 names are live: `_PLAY` (7) at `_MAIN`, `_SETUP_BENCH`
        (2, refused by decision 9 before it ever reaches a price) and `_TO_BENCH` (5, the
        Poffin-class fetch). The third abstained silently until Issue #261 item 2d, because the
        candidate is a DECK card and the supplier lookup read hand rows only — so every option on
        that select tied and the pick fell to menu position."""
        if not getattr(self, "deploy_value", False):
            return None
        ctx = select.get("context")
        if ctx != _MAIN and ctx not in _BENCH_PLACEMENT_CONTEXTS:
            return None
        if ctx == _MAIN and option.get("type") != _PLAY:
            return None
        cid = self._option_card_id(obs, select, option)
        if not self._is_body_card(cid):
            return None
        stat = self.stats.get(cid)

        from common import needs
        from common.deploy_value import DeployInputs, deploy_value

        me = self._my_player(obs)
        offered = self._deploy_offered_ids(obs, select) if ctx == _TO_BENCH else ()
        ready_rows, deck_rows = self._deploy_supplier_rows(obs, board, offered=offered)
        index = next((r["i"] for r in ready_rows if r["cid"] == cid), None)
        if index is None:
            return None
        # One resolve over BOTH sides so the slot indices line up, then the READY rows are the
        # SUPPLIERS and the deck rows become per-slot RESUPPLY (they are not substitutes — you have
        # to draw a deck copy).
        slots, elig_all = self._resolve_needs(obs, board, ready_rows + deck_rows,
                                              include_general=False)
        elig = elig_all[:len(ready_rows)]
        # Re-stamp each LINE slot with the deploy-path deadline before the resupply clamp reads
        # it: `_resolve_needs` supplies the held-PAYOFF direction, which is structurally 99 for
        # a held base. Scoped here so the discard and refresh sites are untouched.
        slots = [dataclasses.replace(s, deadline=self._deploy_line_deadline(me, _slot_cid(s)))
                 if _slot_cid(s) is not None else s for s in slots]
        resupply = self._deploy_resupply(board, slots, elig_all, len(ready_rows), deck_rows)
        capacity = max(0, _BENCH_MAX - int(board.my_bench or 0))
        assignment = needs.deploy_marginal(slots, elig, resupply, index, capacity=capacity)

        tags = set(self.functions.tags(cid)) if self.functions else set()
        # WHERE THE BODY COMES FROM decides whether the trigger exists at all, and it is a card fact
        # rather than a policy: every bench-drop Ability in the pool reads "when you play this
        # Pokémon FROM YOUR HAND onto your Bench" (`data/EN_Card_Data.csv` — Meowth ex 1071's
        # Last-Ditch Catch, Iron Leaves ex 75, Drilbur 81, Farfetch'd 123, Bloodmoon Ursaluna 135,
        # Durant ex 198, Chien-Pao 209; the two "to evolve" siblings are a different trigger again).
        # A Poffin-class fetch puts the body there from the DECK, so the clause is unsatisfiable —
        # the same DERIVED zero decision 3 gives `_SETUP_BENCH`, for the same kind of reason.
        can_fire = ("supporter_tutor" in tags and ctx == _MAIN
                    and not self._last_ditch_spent(me))
        ability_marginal, ability_odds = 0.0, 0.0
        if can_fire:
            ability_marginal, ability_odds = self._supporter_fetch_need(obs, board)

        inp = DeployInputs(
            assignment_marginal=assignment,
            ability_marginal=ability_marginal,
            ability_odds=ability_odds,
            ability_can_fire=can_fire,
            supporter_quota_spent=bool((obs.get("current") or {}).get("supporterPlayed")),
            accel_unlock=self._deploy_accel_unlock(obs, board, cid),
            exposure_prizes=self._deploy_exposure_prizes(obs, select, board, option, stat),
            phase=self._needs_phase_scale(board),
        )
        value = deploy_value(inp)
        return {"cid": cid, "capacity": capacity, **value.working()}

    def _supporter_fetch_need(self, obs: dict, board: Board):
        """``(worth marginal, odds)`` for a bench-drop Supporter tutor — decision 3's Ability leg.

        WHAT the fetch is worth is the best need a Supporter can fill that nothing held already
        covers (`draw_engine` / `supply_wincon`, the kinds `supporter_tutor` supplies). WHETHER it
        lands is the Deck-Content Odds that such a Supporter is still in deck. Both are RANKED
        reads, so they weight the leg and never gate it (ADR-0074).

        This is what makes "bench it only when we need a SPECIFIC Supporter" arithmetic: a position
        whose draw need is met scores 0 however certainly the deck holds one.

        The two slots are built HERE rather than looked up in `_resolve_needs`' output, and that is
        the whole point. That resolver derives slots FROM THE HELD ROWS — `draw_engine` is emitted
        only `if engines:` (I hold an engine) and `supply_wincon` only `if tutors:` (I hold a tutor).
        Correct for keep-value, where a slot exists to price a card you have; exactly inverted for
        this question, where the need exists BECAUSE I hold nothing that meets it. Asking the
        resolver for an UNCOVERED slot of those kinds is therefore near-unsatisfiable, and the leg
        measured 0 on every board — the real mega_lucario deck holding six Supporters included.
        Slot VALUES still come from `needs`, so the two derivations cannot drift.

        Odds range over the DECKLIST, not `board.deck_known_counts`: the counts are empty until the
        tracker anchors, and iterating them zeroed the leg whenever tracking was unavailable —
        gating on a missing signal, which is the fail direction ADR-0074 forbids. A provably-gone
        Supporter is dropped (`deck_empty_ids`, the SOUND read); otherwise
        `deck_contains_probability` already returns 1.0 when the odds are uncomputable."""
        from common import needs
        me = self._my_player(obs)
        hand_ids = list(board.hand_ids or ())

        def _held_engine_supporter() -> bool:
            for cid in hand_ids:
                st = self.stats.get(cid) if self.stats else None
                tags = set(self.functions.tags(cid)) if self.functions else set()
                if "engine" in self._roles_of(cid):
                    return True
                if (st is not None and getattr(st, "is_supporter", False)
                        and (_ENGINE_KEEP_TAGS & tags) and "hand_disruption" not in tags):
                    return True
            return False

        def _held_tutor() -> bool:
            return any("tutor" in self._roles_of(cid)
                       or ({"rush_evolve", "tutor_mega"}
                           & (set(self.functions.tags(cid)) if self.functions else set()))
                       for cid in hand_ids)

        draw_need = 0.0
        if not _held_engine_supporter():
            online = sum(1 for pid in board.in_play_ids if "engine" in self._roles_of(pid))
            draw_need = needs.draw_engine_slot(engines_online=online,
                                               value=_ENGINE_SUPPORTER_KEEP).value
        supply_need = 0.0
        if not _held_tutor():
            supply = needs.supply_wincon_slot(
                wincon_in_hand=bool(getattr(board, "wincon_in_hand", False)), target_reachable=True)
            supply_need = supply.value if supply is not None else 0.0
        if draw_need <= 0 and supply_need <= 0:
            return 0.0, 0.0

        # Match the need against the Supporters the deck ACTUALLY holds, one at a time, instead of
        # asserting the slot's tier and then asking separately whether "a Supporter" survives. A need
        # no reachable Supporter can fill is not a need this Ability answers: neither deck's Supporter
        # line reaches the win-condition (mega_lucario's Petrel is `tutor_trainer` — Trainers, not the
        # Mega), so an unconditioned `supply_wincon` claim paid +10 on every board and made Meowth ex
        # always worth benching, which is the opposite of "bench it only when we need a SPECIFIC
        # Supporter". The wincon leg now requires a Supporter whose own fetch closure reaches it.
        wincon = self._wincon_set()
        empty = getattr(board, "deck_empty_ids", frozenset()) or frozenset()
        best_value = best_odds = 0.0
        for cid in set(self.deck or ()):
            st = self.stats.get(cid) if self.stats else None
            if st is None or not getattr(st, "is_supporter", False) or cid in empty:
                continue
            tags = set(self.functions.tags(cid)) if self.functions else set()
            value = 0.0
            if draw_need > 0 and (_ENGINE_KEEP_TAGS & tags) and "hand_disruption" not in tags:
                value = draw_need
            if supply_need > 0 and wincon and (self._chain_fetch_targets(cid) & wincon):
                value = max(value, supply_need)
            if value <= 0:
                continue
            odds = (board.deck_contains_probability(cid)
                    if hasattr(board, "deck_contains_probability") else 1.0)
            odds = max(0.0, min(1.0, float(odds)))
            # Rank by the WEIGHTED yield: a slightly smaller need that is far likelier to be there is
            # the better reason to bench. The leg then reports that candidate's own pair, so the odds
            # never travel attached to a need some other Supporter would have filled.
            if value * odds > best_value * best_odds:
                best_value, best_odds = value, odds
        return float(best_value), float(best_odds)

    def _needs_phase_scale(self, board: Board) -> float:
        """`needs.phase_scale` off the live board — the prize-proximity sharpener the exposure leg
        rides. Neutral (1.0) when the race read is unavailable, so a missing signal never inflates
        or deletes the term."""
        from common import needs
        try:
            return float(needs.phase_scale(
                race_ahead=getattr(board, "race_ahead", None),
                opp_prizes_remaining=int(getattr(board, "opp_prizes_remaining", 0) or 0)))
        except Exception:
            return 1.0

    def _deploy_accel_unlock(self, obs: dict, board: Board, cid) -> float:
        """Decision 8's accel-unlock leg: the DAMAGE the Attach Budget realises because a legal
        landing spot now exists.

        The value belongs to the ACCELERATOR's stranded Energy, not to the recipient's own role —
        which is why this is not a tier bump on the body's line slot. `_recover_units` already prices
        a rider's real yield under three bounds (printed ceiling, matching fuel in the source zone,
        and the recipients' remaining NEED), and its need bound is exactly what makes a bench-targeted
        rider credit 0 on an empty Bench. So the counterfactual is that same function evaluated on the
        board WITH the candidate benched, which is ADR-0069's `this_turn` shape applied to a deploy.

        Three behaviours fall out instead of being asserted, and they are the flat +20 rung's
        hand-written stand-down conditions:

        * 0 when the accelerator is not Active (`accel_recipient_missing` is False — nothing stranded);
        * 0 when a recipient is already benched (same signal — the Energy already lands);
        * PROPORTIONAL to the rider's real yield, so a 3-Energy Aura Jab pays more than a 1-Energy
          trickle, which the flat rung could not express at all.

        Priced per Energy at `ENERGY_RECOVER` — the shipped, DERIVED median damage-per-Energy over
        every attack costing >= 2 (`160/3`, ADR-0078 via Issue #172) — rather than a constant invented
        for this leg. Damage-denominated already, so it does NOT ride the deploy band."""
        if not board.accel_recipient_missing or not self.stats or cid is None:
            return 0.0
        stat = self.stats.get(cid)
        if stat is None or not getattr(stat, "is_pokemon", False):
            return 0.0
        if cid not in self._line_member_set():        # only a Line member receives (the glossary term)
            return 0.0
        active = self._my_active(obs)
        aid, best = None, 0.0
        for candidate in (getattr(self.stats.get((active or {}).get("id")), "attacks", None) or ()):
            st = self._attack_stat(candidate)
            if st is not None and getattr(st, "recoverN", 0) > 0:
                aid = candidate
                break
        if aid is None:
            return 0.0
        # The hypothetical board: the candidate is on the Bench, so the rider has somewhere to land.
        hypo = copy.deepcopy(obs)
        me = hypo["current"]["players"][hypo["current"].get("yourIndex", 0)]
        me["bench"] = list(me.get("bench") or []) + [{"id": cid, "hp": getattr(stat, "hp", 0),
                                                      "energies": [], "appearThisTurn": True}]
        units = self._recover_units(aid, {}, board, hypo)   # dmg_ctx unused by the fuel/need bounds
        best = max(0.0, float(units)) * ENERGY_RECOVER
        return best

    def _deploy_exposure_prizes(self, obs: dict, select: dict, board: Board, option: dict,
                                stat) -> float:
        """The exposure leg's prize-equivalents (decision 5): the Prize-Path DELTA, and nothing else.

        How much does benching this body shorten the opponent's cheapest route (`_bench_path_delta`)?
        Sharp, board-aware, and zero against a body they cannot reach.

        **Where the Path cannot be read, this contributes ZERO** — decision 6, verbatim: *"a term that
        cannot be computed contributes ZERO, never a guess."* That matters in practice rather than in
        principle: the Path is unreadable on 189 of the corpus's non-Set-Up frames (both pregame
        Actives face down is the obvious case, but far from the only one).

        A FALLBACK stood here and is now DELETED, and the history is worth keeping because it is a
        lesson about scope. It guessed the body's own prize liability — the excess over a 1-prize
        body — and was added for ONE reason: at `_SETUP_BENCH` a derived-zero Ability leg plus a zero
        exposure lands at exactly 0.0, and the optional-select take-fewer drops only `score < 0`, so
        Meowth ex survived the pregame on `setup_bench_decline_f3`. Decision 9 now refuses every
        pregame placement by RULE, so that reason is gone — and with it went two more pregame patches
        that had accreted on the same spot (a `setup_placed_ids` redundancy charge, and before it a
        flat full-prize Set-Up charge measured and rejected for also declining the win-condition Line
        base). Amendment F was a fourth, proposed and withdrawn the same day.

        Removing it was checked, not assumed: both ADR-0072 gates still PASS and the suite stays
        green, so the guess was carrying none of the rulings. Four patches on one context, none of
        them load-bearing, is what a missing rule looks like from the inside.
        """
        delta = self._bench_path_delta(obs, select, option, stat, board)
        if delta > 0.0:
            return delta
        return 0.0                         # unreadable Path: decision 6 says ZERO, never a guess

    def _recover_units(self, attack_id, dmg_ctx: dict, board: Board, obs: dict) -> float:
        """Energy this attack's accel rider would actually attach AND that a recipient can
        actually USE — the development the Tactical layer credits (Aura Jab / Turbo Flare:
        attack + accelerate).

        Three independent bounds, all closed-form:
          1. `recoverN`   — the card's printed ceiling (Aura Jab: "attach up to 3").
          2. the matching Basic-Energy FUEL in the rider's SOURCE zone (`recoverSource`):
             "discard" → my open discard (`my_discard_basic_energy`, ADR-0061: re-sourced from the
             Board so it is the one truth for my discard fuel — `_damage_context` keeps its own
             attacker-relative copy because it must also serve the Incoming direction);
             "deck" → the whole-deck search's pool (`_deck_basic_energy_fuel`: the EXPECTED count
             off the one Count Triple derivation, ADR-0077 — a ranked count consumer reads
             `expected`, and anchored the leg collapses to the exact integer).
          3. the recipients' remaining NEED (ADR-0061). The old code checked only that the Bench was
             non-empty, so 3 {F} onto a Lunatone/Solrock support bench scored an identical +225 to 3
             {F} onto a Riolu that becomes the second Mega Lucario ex — and that +225 is exactly what
             tips Aura Jab (130) over Mega Brave (270). Energy nobody can pay an attack with is not
             development. Need is measured against each recipient's FORWARD form too, so a Riolu
             counts the {F}{F} its Mega Brave will cost, not the {F} its Quick Attack costs today.
             The same need gate makes Turbo Flare on an EMPTY bench credit 0 — the "firing blanks"
             signal the mega_starmie deck rules hand-encoded (hypergeometric-fetch-closure §Round 13).
        """
        st = self._attack_stat(attack_id)
        if not st or not getattr(st, "recoverN", 0):
            return 0.0
        if getattr(st, "recoverSource", None) == "deck":
            fuel = self._deck_basic_energy_fuel(st.recoverEnergyType)   # EXPECTED — fractional
        else:
            by_type = (board.my_discard_basic_energy or {})             # the discard is PUBLIC: exact
            fuel = (by_type.get(st.recoverEnergyType, 0) if st.recoverEnergyType is not None
                    else sum(by_type.values()))
        need = self._recover_recipient_need(st, board, obs)
        return max(0.0, min(float(st.recoverN), float(fuel), float(need)))

    def _recover_recipient_need(self, st, board: Board, obs: dict) -> int:
        """Total Energy the rider's recipients still LACK to pay an attack — theirs or their forward
        evolution's (the dearest, since that is what the line is being built toward). 0 when the
        rider's target scope has no recipient at all (a bench-targeted recover with an empty Bench
        attaches nothing), which preserves the old empty-Bench guard as a special case."""
        me = self._my_player(obs)
        pool = []
        if st.recoverTarget in (None, "any", "bench"):
            pool += [p for p in (me.get("bench") or []) if p]
        if st.recoverTarget in (None, "any", "self"):
            pool += [p for p in (me.get("active") or []) if p]
        total = 0
        for p in pool:
            cid = p.get("id")
            forms = {cid} | set(self._forward_card_ids(cid) or ())
            costs = [self._attack_cost(aid)
                     for f in forms
                     for aid in (getattr(self.stats.get(f), "attacks", None) or ())
                     if self.stats and self.stats.get(f)]
            if not costs:
                continue
            total += max(0, max(costs) - len(p.get("energies") or []))
        return total

    def _is_benchable_body(self, cid) -> bool:
        """A benchable body: a Basic Pokémon (`is_pokemon` and no `evolvesFrom` — it grounds out on
        the field itself, not as an evolution). Staryu/Riolu yes; Cinderace (evolves from Raboot) no."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        return bool(st and getattr(st, "is_pokemon", False) and not getattr(st, "evolvesFrom", None))

    def _hand_has_benchable_body(self, me: dict) -> bool:
        """True if a benchable Basic Pokémon is already IN HAND (deploy it directly)."""
        return any(self._is_benchable_body(c.get("id")) for c in (me.get("hand") or []) if c)

    def _hand_can_develop_body(self, me: dict) -> bool:
        """True if the HAND can put a body on the board this turn — a benchable Basic directly, OR a
        fetcher that produces one (`bench_fill` Poffin / `tutor_pokemon` Ball can grab a Basic). NOT a
        `tutor_mega` (Mega Signal fetches the payoff, which still needs its base). The line between a
        genuinely stranded hand (f40 — no body, no fetcher) and a developable one (ep83667237 f120 —
        a Poffin and an Ultra Ball on hand, so the Energy has a home coming and is NOT illiquid)."""
        if self._hand_has_benchable_body(me):
            return True
        body_fetch = {"bench_fill", "tutor_pokemon"}
        for c in (me.get("hand") or []):
            cid = c.get("id") if c else None
            if cid is not None and self.functions and (body_fetch & set(self.functions.tags(cid))):
                return True
        return False

    def _has_energy_recipient(self, board: Board, me: dict) -> bool:
        """True if an Energy card has a live home on my board: a benched body (bench bodies are not the
        doomed Active), a non-doomed Active, or a benchable body in hand to deploy onto. False is the
        f40 shape — a doomed Active, an empty Bench and no body in hand — where held Energy cannot be
        attached to anything that will attack, so its latent worth is illiquid."""
        if board.my_bench > 0:
            return True
        if not board.active_doomed and any(me.get("active") or []):
            return True
        return self._hand_can_develop_body(me)

    def _board_has_stage2(self, player: dict | None) -> bool:
        """True when this player has a Stage 2 Pokémon in play (`CardStat.stage2`) — the Gravity
        Mountain tech read (its −30 HP hits exactly Stage 2s, both sides)."""
        if not (self.stats and player):
            return False
        for p in ((player.get("active") or []) + (player.get("bench") or [])):
            st = self.stats.get((p or {}).get("id")) if p else None
            if st is not None and getattr(st, "stage2", False):
                return True
        return False

    def _board_has_colorless_ability(self, player: dict | None) -> bool:
        """True when this player has a Colorless Pokémon WITH an Ability in play — the Team Rocket's
        Watchtower read ({C} Pokémon lose their Abilities under it, both sides)."""
        if not (self.stats and player):
            return False
        for p in ((player.get("active") or []) + (player.get("bench") or [])):
            st = self.stats.get((p or {}).get("id")) if p else None
            if (st is not None and st.hp > 0 and st.energyType == 0
                    and getattr(st, "hasAbility", False)):
                return True
        return False

    def _hand_basic_energy(self, hand: list) -> dict:
        """{EnergyType: count} of Basic Energy cards in my hand — the last-attachable-Energy read
        (`CardStat.cardType` BASIC_ENERGY=5, mirroring `_discard_energy_counts`)."""
        counts: dict = {}
        for c in hand:
            st = self.stats.get((c or {}).get("id")) if (self.stats and c) else None
            if st is not None and st.is_typed_basic_energy:
                counts[st.energyType] = counts.get(st.energyType, 0) + 1
        return counts

    def _no_supporter_in_hand(self, me: dict) -> bool:
        """True if MY hand holds no Supporter card (cardType 3). Read by `bench-the-supporter-tutor`:
        bench a `supporter_tutor` Pokémon (Meowth ex) to fetch a Supporter only when we don't already
        hold one. Unknown stats -> False (don't assert the trigger — never bench the 2-prize ex blind)."""
        if not self.stats:
            return False
        for c in (me.get("hand") or []):
            st = self.stats.get((c or {}).get("id"))
            if st is not None and st.is_supporter:
                return False
        return True
