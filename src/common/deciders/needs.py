"""The needs LEDGER (ADR-0127): what my board still needs, what each held card covers, and what holding it is worth.

Supply priced without demand inverts every card play. `_resolve_needs` is the one assignment; every keep/shed/grab
site consumes it rather than re-deciding."""
from __future__ import annotations

from dataclasses import dataclass

from common.card_worth import ENERGY_TIER
from common.deciders.facts import Board
from common.deciders.hand import _ENGINE_KEEP_TAGS, _ENGINE_SUPPORTER_KEEP


# The LATENT-worth discount on a held card filling no specific need. Sized at the readiness leaf's bench
# position weight (`_READINESS_BENCH_DISCOUNT` 0.45) — a hand card is ~one deploy away, like a benched body.
_GENERAL_WORTH_W = 0.45

_GENERAL_ILLIQUID_FLOOR = 0.15  # a general-worth card whose value needs board state it hasn't got (an Energy
                           # with no body able to receive and attack with it). NOT 0 — residual future worth
                           # keeps it above outright-dead cards in pitch order. Derived, never a card list.


@dataclass(frozen=True)
class _ResolvedNeeds:
    """Backward-compatible two-value resolver result carrying weighted supply edges."""
    slots: list
    eligibility: list
    edge_values: list
    unknowns: tuple = ()

    def __iter__(self):
        yield self.slots
        yield self.eligibility

    @property
    def graph(self):
        from common.needs import CoverageEdge, NeedGraph
        coverage = tuple(tuple(CoverageEdge(j, self.edge_values[i].get(j, self.slots[j].value))
                               for j in sorted(row))
                         for i, row in enumerate(self.eligibility))
        return NeedGraph(tuple(self.slots), coverage, self.unknowns)


class NeedsMixin:
    """The needs assignment: demand, coverage, and what a held card is worth."""

    def _needs_v2(self, obs: dict, board: Board, rows: list, picks: int):
        """Per-row ``keep_v2`` plus the v2 decider's pick, hedged at v1's POST-GATE keep. **This DECIDES**,
        unflagged: the forced discard's pick IS `eq2_pick` (ADR-0065 / ADR-0127 hold the slot vocabulary)."""
        from common import needs
        resolved = self._resolve_needs(obs, board, rows)
        slots, elig = resolved
        resupply = [0.0] * len(slots)
        keeps = [round(needs.keep_v2(slots, elig, resupply, k,
                                     edge_values=resolved.edge_values), 1)
                 for k in range(len(rows))]
        pick = needs.cheapest_removal(slots, elig, resupply, [r["keep"] for r in rows], picks,
                                      edge_values=resolved.edge_values,
                                      **self._removal_ranking_legs(rows))
        return keeps, sorted(rows[k]["i"] for k in pick)

    def _resolve_needs(self, obs: dict, board: Board, rows: list, *, include_general: bool = True):
        """The ONE slot derivation behind BOTH the discard decider and the refresh SHED; the caller owns
        ``resupply``. ``include_general=False`` (the LEAF) drops latent worth, which else rewards HOARDING."""
        from common import currency, needs
        from common.card_worth import ROLE_TIER, ACE_SPEC_TIER, ENERGY_TIER, TAG_TIER
        me = self._my_player(obs)
        line_roles = {r for r, kinds in needs.SUPPLIES.items() if "line" in kinds and r in ROLE_TIER}
        slots: list = []
        elig: list = [set() for _ in rows]
        edge_values: list = [{} for _ in rows]
        unknowns: list[str] = []

        # The PLAYABILITY gate (ADR-0104): a card that can NEVER be played covers NOTHING. Applied to
        # ELIGIBILITY, not to any one slot's value — `deploy` only zeroes the slots keyed on the card itself.
        unplayable = self._unplayable_rows(obs, board, rows)

        def _emit(slot, members, values=None) -> None:
            suppliers = _playable_only(members)
            if not suppliers:
                return                             # a need only its dead cards could fill is no need
            j = len(slots)
            slots.append(slot)
            for m in suppliers:
                elig[m].add(j)
                if values is not None and m in values:
                    edge_values[m][j] = float(values[m])

        def _playable_only(ks) -> list:
            """The candidate rows of a leg, minus the unplayable ones. Applied to EVERY leg rather than only
            at `_emit`, because two legs read their SLOT VALUE off the candidate list."""
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
            # A LINE slot is a BODY to assemble — Pokémon only (an ACE-SPEC Trainer keeps its one-per-deck
            # claim). An Energy with a line-class derived role must NOT reopen a line: it resurrects the burst.
            worth = 0.0
            if st is not None and getattr(st, "is_pokemon", False):
                worth = max((ROLE_TIER[r] for r in roles if r in line_roles), default=0.0)
            if st is not None and getattr(st, "aceSpec", False):
                worth = max(worth, ACE_SPEC_TIER)
            deploy = rows[members[0]].get("deploy", 1.0)
            if worth * deploy > 0:
                # URGENT succession: FULL tier at deadline 0. Narrowing it to `_successor_evolvable_now` was
                # BUILT and REVERTED — it contradicts the ruling the spike exists for (ADR-0101).
                urgent = bool(board.active_doomed and cid in self._wincon_set()
                              and getattr(board, "line_preevo_in_play", False))
                # Consumed ONLY by the refresh-SHED resupply window — inert for the live discard decider.
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
            # The band reads off the eligible suppliers: an engine BODY need is the engine-role tier, a
            # supporter-only need is v1's tuned engine-supporter band.
            band = (ROLE_TIER["engine"]
                    if any("engine" in self._roles_of(rows[k]["cid"]) for k in engines)
                    else _ENGINE_SUPPORTER_KEEP)
            _emit(needs.draw_engine_slot(engines_online=online, value=band), engines)
        active = next((p for p in (me.get("active") or []) if p), None)
        model = getattr(self, "_state_model", None)
        if model is not None:
            funders = _playable_only([
                k for k, r in enumerate(rows)
                if getattr(self.stats.get(r["cid"]) if self.stats else None, "is_energy", False)
            ])
            for body_index, body in enumerate(model.mine.bodies):
                key = "active" if body.is_active else f"bench.{body_index - 1}"
                marginals = {}
                for k in funders:
                    supply = model.energy_supply_from_card(rows[k]["cid"])
                    profile = model.combat_realization(body, supply=supply)
                    if profile.status.value == "unknown":
                        unknowns.append(f"fund:{key}:card:{rows[k]['cid']}:provision_or_potential")
                        continue
                    worth = float(model.prizes_to_worth(
                        model.readiness_supply_delta(body, supply)))
                    if worth > 0.0:
                        marginals[k] = worth
                if marginals:
                    slot = needs.Slot("fund_attack", max(marginals.values()),
                                      1 if board.energy_attached else 0,
                                      f"fund:{key}:next_attach")
                    _emit(slot, marginals, values=marginals)
        if board.active_doomed:
            # The answer-doom slot is the SWITCH/HEAL rescue only (the successor rides the URGENT line slot),
            # VALUED at the doomed body's OWN preserved worth — not the clutch_heal tier, not the swap's worth.
            answers = _playable_only([k for k, r in enumerate(rows)
                             if {"clutch_heal", "switch"} & _tags(r["cid"])])
            preserved = self._role_value(active.get("id")) if active is not None else 0.0
            if answers and preserved > 0:
                _emit(needs.answer_doom_slot(value=preserved), answers)
        # DENY slots are valued at the DISRUPTION CARD-TIER, not the ADR-0062 damage swing. ADR-0076: gust
        # supplies both "deny" and "gust_target", but only ONE is ever LIVE; OFF leaves `deny_tags` unchanged.
        deny_tags = {src for src, kinds in needs.SUPPLIES.items() if "deny" in kinds}
        gust_tags = {src for src, kinds in needs.SUPPLIES.items() if "gust_target" in kinds}
        if self.gust_target_slots:
            deny_tags = deny_tags - gust_tags
        deniers = _playable_only([k for k, r in enumerate(rows) if deny_tags & _tags(r["cid"])])
        deny_tier = TAG_TIER["gust"]
        # ARMED (ADR-0080): the keep price becomes `tier x relevance(this body)`. The `/2^t` turns-to-ready
        # GRADE is retained — relevance is deliberately not imminence-gated, so the grade prices WHEN it lands.
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
                    # relevance > 0 SUBSUMES the deleted ADR-0062 bite gate: it is already 0 for a bare body,
                    # for surplus Energy, and for one dying to my KO this turn.
                    value = deny_tier * max((deny_rel.get((area, bi)) or {}).values(), default=0.0)
                    if not p or value <= 0:
                        continue
                    t = self._opp_turns_to_ready(p)
                    if t is None:
                        continue               # unknown stats — fail closed, no deny slot
                    _emit(needs.deny_slot(f"deny:{area}{bi}:{p.get('id')}",
                                          oracle_value=value, turns_to_ready=t), deniers)
        # GUST-TARGET SLOTS (ADR-0076, kill-switched). Bench ONLY — their Active is never a legal gust target,
        # unlike deny. The row's `value` is PRIZE-equivalents, so it crosses to CARD-WORTH here (ADR-0107).
        if self.gust_target_slots:
            gusters = _playable_only([k for k, r in enumerate(rows) if gust_tags & _tags(r["cid"])])
            if gusters:
                target_rows = self._deny_rows(obs, board)   # ONE ladder — never a second cache-or-compute walk
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
        # GENERAL-WORTH slots: LATENT value, discounted and DE-DUPLICATED per cid. A class eligible for the
        # SATURATING draw-engine slot gets none — the spare copy covers nothing.
        engine_cids = {rows[k]["cid"] for k in engines}
        seen_general: set = set()
        for cid, members in (by_cid.items() if include_general else ()):
            if cid in seen_general or cid in engine_cids:
                continue
            seen_general.add(cid)
            # A row the PITCH term flags as dead-weight is fodder NOW — no latent worth, else general worth
            # RESURRECTS a spent burst. Refresh rows carry no pitch flag (a SHUFFLED burst IS a future attach).
            live = [m for m in members if rows[m].get("pitch", 0) == 0]
            if not live:
                continue
            worth = self._role_value(cid)
            deploy = rows[live[0]].get("deploy", 1.0)
            if worth * deploy > 0:
                liq = self._general_liquidity(cid, board, me)   # illiquid latent worth discounts
                # INSURANCE, not latent worth (ADR-0101 amendment): a `clutch_heal` covering an IRREPLACEABLE
                # Active is the survival plan, not one deploy away, so it takes full tier at deadline 1.
                if self._heal_insures_the_last_wincon(cid, me):
                    _emit(needs.insure_wincon_slot(f"insure:{cid}", value=worth * deploy), live)
                    continue
                _emit(needs.general_worth_slot(f"general:{cid}",
                                               value=worth * deploy * _GENERAL_WORTH_W * liq), live)
        return _ResolvedNeeds(slots, elig, edge_values, tuple(unknowns))

    def _rare_candy_reachable(self, ids) -> bool | None:
        """Does any card in ``ids`` carry the `rare_candy` Function Tag? ``None`` when there is no tag table —
        the tri-state `playability.Zones.rare_candy` documents, and why this is a method not an inline `any`."""
        if not self.functions:
            return None
        from common import playability
        return any(playability.RARE_CANDY_TAG in set(self.functions.tags(cid)) for cid in ids)

    def _playability_zones(self, board: Board, counts: dict):
        """The zone reads `common.playability` walks. Memoised on the IDENTITY of its two inputs — strong refs,
        not ``id()``s: CPython reuses a collected object's address, so an id-keyed cache reads a stale answer."""
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
        """Row indices whose card can NEVER be played (ADR-0104) — the `_resolve_needs` gate. Fails OPEN without
        a stat provider; a missing tag table is NOT such a case (`Zones.rare_candy`'s ``None`` handles it)."""
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
        """Whole-hand v2 rows for the refresh SHED: one row per held card, minus ONE copy of ``exclude_cid``
        (the played refresh is discarded, not shuffled), carrying the fields `_resolve_needs` reads."""
        me = self._my_player(obs)
        hand_ids = [c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None]
        ids = list(hand_ids)
        if exclude_cid in ids:
            ids.remove(exclude_cid)
        counts = self._unseen_deck_counts(me, board)
        fuel_types = self._discard_fuel_types()
        # ``i`` is the ROW ordinal (the alignment eligibility and picks are in); ``hand_i`` is the card's
        # position in the REAL hand. Dropping `exclude_cid` diverges them, so both are carried, never derived.
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
        """What SPENDING held ``cid`` costs, in damage — the ONE hold price every free-Item decider subtracts
        (`common/hold_value.py`). Resupply is all-0.0 as POLICY: playing a card opens no draw window."""
        from common import hold_value, needs
        cache = self._item_hold_cache
        if cid in cache:
            return cache[cid]
        keep = 0.0
        if cid is not None:
            rows = self._needs_hand_rows(obs, board)
            k = next((i for i, r in enumerate(rows) if r["cid"] == cid), None)
            if k is not None:
                resolved = self._resolve_needs(obs, board, rows)
                slots, elig = resolved
                keep = needs.keep_v2(slots, elig, [0.0] * len(slots), k,
                                     edge_values=resolved.edge_values)
        price = cache[cid] = hold_value.hold_price(keep)
        return price

    def _general_liquidity(self, cid, board: Board, me: dict) -> float:
        """How realizable a card's LATENT worth is on this board, in (`_GENERAL_ILLIQUID_FLOOR`, 1]. An Energy
        with no recipient prices at the floor; everything with a live use stays 1.0. Never a card list."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        if st is not None and getattr(st, "is_energy", False) and not self._has_energy_recipient(board, me):
            return _GENERAL_ILLIQUID_FLOOR
        return 1.0
