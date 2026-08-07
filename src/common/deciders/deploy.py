"""The deploy decider (ADR-0086): what benching this body is worth against the prizes it exposes.

Exposure is a COST, never a veto — a 2-prize body with an Ability payoff can still be the right bench."""
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
        """``cid`` costs a BENCH slot — the only capacity the deploy path bounds. A Trainer covering a
        draw need takes no slot, so it is not a supplier here however much the assignment values it."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        return bool(st is not None and getattr(st, "is_pokemon", False))

    def _deploy_offered_ids(self, obs: dict, select: dict) -> list:
        """Card ids a `_TO_BENCH` select OFFERS, one row per OPTION — already-found deck cards, so
        CERTAIN suppliers, never resupply. Cards taken earlier in a multi-pick stay listed harmlessly."""
        return [cid for opt in (select.get("option") or [])
                if self._is_body_card(cid := self._option_card_id(obs, select, opt))]

    def _deploy_supplier_rows(self, obs: dict, board: Board, *, offered=()):
        """``(ready_rows, deck_rows)`` — bodies competing for free Bench slots, split by CERTAINTY
        (ADR-0086 D2). A deck copy is slot RESUPPLY; as a rival supplier it zeroes its hand twin."""
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
        """Turns until THIS held body's line comes online. `_line_readiness_deadline` answers the
        held-PAYOFF direction and is structurally 99 for a held base, so a base reads its own hop."""
        if cid is None:
            return 99
        if cid in self._line_preevo_set():
            forward = self._forward_card_ids(cid) or ()
            if any(f in self._wincon_set() or f in self._line_member_set() for f in forward):
                return 1                       # bench now, evolve next turn
        return self._line_readiness_deadline(me, cid)

    def _deploy_resupply(self, board: Board, slots: list, elig_all: list, hand_n: int,
                         deck_rows: list) -> list:
        """Per-slot RESUPPLY from the deck leg: the odds a deck body actually ARRIVES, not merely that
        it exists. A RANKED read, so it weights the marginal and never gates it (ADR-0074)."""
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
        # The CLOSING EDGE — does the deck deliver IN TIME, not merely deliver. Without it SCARCITY
        # stands in for URGENCY. Graded against the shared HORIZON, not a constant invented here.
        for j, s in enumerate(slots):
            dl = max(0, int(getattr(s, "deadline", 99) or 0))
            resupply[j] *= min(1.0, dl / float(_HORIZON))
        return resupply

    def _last_ditch_spent(self, me: dict) -> bool:
        """Has a "Last-Ditch" Ability already fired this turn? Read SOUNDLY off the board: it is capped
        at one per turn and fires on the bench-drop, so a `supporter_tutor` at ``appearThisTurn`` IS it."""
        for b in (me.get("bench") or []):
            if not b or not b.get("appearThisTurn"):
                continue
            tags = set(self.functions.tags(b.get("id"))) if self.functions else set()
            if "supporter_tutor" in tags:
                return True
        return False

    def _deploy_decision(self, obs: dict, select: dict, board: Board, option: dict):
        """Price ONE candidate Bench deployment — the Pilot half of ADR-0086. All three entry points
        are live: `_PLAY` at `_MAIN`, `_SETUP_BENCH` (refused by decision 9) and `_TO_BENCH`."""
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
        # One resolve over BOTH sides so the slot indices line up; the READY rows are the SUPPLIERS
        # and the deck rows become per-slot RESUPPLY.
        slots, elig_all = self._resolve_needs(obs, board, ready_rows + deck_rows,
                                              include_general=False)
        elig = elig_all[:len(ready_rows)]
        # Re-stamp each LINE slot with the deploy-path deadline before the resupply clamp reads it.
        # Scoped here so the discard and refresh sites are untouched.
        slots = [dataclasses.replace(s, deadline=self._deploy_line_deadline(me, _slot_cid(s)))
                 if _slot_cid(s) is not None else s for s in slots]
        resupply = self._deploy_resupply(board, slots, elig_all, len(ready_rows), deck_rows)
        capacity = max(0, _BENCH_MAX - int(board.my_bench or 0))
        assignment = needs.deploy_marginal(slots, elig, resupply, index, capacity=capacity)

        tags = set(self.functions.tags(cid)) if self.functions else set()
        # A CARD FACT, not a policy: every bench-drop Ability in the pool reads "when you play this
        # Pokémon FROM YOUR HAND onto your Bench", so a deck-sourced placement cannot satisfy it.
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
        """``(worth marginal, odds)`` for a bench-drop Supporter tutor (ADR-0086 D3). The slots are built
        HERE — `_resolve_needs` derives slots FROM held rows, and this need exists because I hold none."""
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

        # Match the need against the Supporters the deck ACTUALLY holds, one at a time: a need no
        # reachable Supporter can fill is not a need this Ability answers.
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
            # Rank by the WEIGHTED yield, then report that candidate's own pair, so the odds never
            # travel attached to a need some other Supporter would have filled.
            if value * odds > best_value * best_odds:
                best_value, best_odds = value, odds
        return float(best_value), float(best_odds)

    def _needs_phase_scale(self, board: Board) -> float:
        """`needs.phase_scale` off the live board. Neutral (1.0) when the race read is unavailable, so
        a missing signal never inflates or deletes the exposure term."""
        from common import needs
        try:
            return float(needs.phase_scale(
                race_ahead=getattr(board, "race_ahead", None),
                opp_prizes_remaining=int(getattr(board, "opp_prizes_remaining", 0) or 0)))
        except Exception:
            return 1.0

    def _deploy_accel_unlock(self, obs: dict, board: Board, cid) -> float:
        """ADR-0086 decision 8's accel-unlock leg: `_recover_units` on the board WITH the candidate
        benched, priced at `ENERGY_RECOVER` — damage-denominated, so it does NOT ride the deploy band."""
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
        """The exposure leg's prize-equivalents (ADR-0086 D5): the Prize-Path DELTA, and nothing else.
        Where the Path cannot be read this contributes ZERO, never a guess (D6)."""
        delta = self._bench_path_delta(obs, select, option, stat, board)
        if delta > 0.0:
            return delta
        return 0.0                         # unreadable Path: decision 6 says ZERO, never a guess

    def _recover_units(self, attack_id, dmg_ctx: dict, board: Board, obs: dict) -> float:
        """Energy this accel rider would attach AND a recipient can USE — the min of the printed
        `recoverN`, the fuel in the rider's SOURCE zone, and the recipients' remaining NEED (ADR-0061)."""
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
        """Energy the rider's recipients still LACK to pay an attack — theirs or their forward form's,
        whichever is dearest. 0 when the rider's target scope has no recipient at all."""
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
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        return bool(st and getattr(st, "is_pokemon", False) and not getattr(st, "evolvesFrom", None))

    def _hand_has_benchable_body(self, me: dict) -> bool:
        return any(self._is_benchable_body(c.get("id")) for c in (me.get("hand") or []) if c)

    def _hand_can_develop_body(self, me: dict) -> bool:
        """The HAND can put a body on the board this turn — a benchable Basic, or a fetcher that
        produces one. NOT a `tutor_mega`: that fetches the payoff, which still needs its base."""
        if self._hand_has_benchable_body(me):
            return True
        body_fetch = {"bench_fill", "tutor_pokemon"}
        for c in (me.get("hand") or []):
            cid = c.get("id") if c else None
            if cid is not None and self.functions and (body_fetch & set(self.functions.tags(cid))):
                return True
        return False

    def _has_energy_recipient(self, board: Board, me: dict) -> bool:
        """An Energy card has a live home: a benched body, a non-doomed Active, or a benchable body in
        hand. False means held Energy is ILLIQUID — nothing that will attack can receive it."""
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
        """My hand holds no Supporter. Unknown stats -> False, so the trigger is never asserted blind."""
        if not self.stats:
            return False
        for c in (me.get("hand") or []):
            st = self.stats.get((c or {}).get("id"))
            if st is not None and st.is_supporter:
                return False
        return True
