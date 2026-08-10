"""The rollout LEAF: what a candidate turn's END state is worth.

One engine-backed term (`KO_SCORE x state_value`, ADR-0092) plus the closed-form account: survival, threat,
development, and the line's own spend. `turn_value = leaf(end) - sum(spend)` — a development that consumed a one-shot
is not free just because the end board looks the same."""
from __future__ import annotations


from common import needs
from common.state_model import StateModel
from common.strategy.context import KO_SCORE, _DISCARD
from common.strategy.planning.readiness import _READINESS_CAP
from common.strategy.planning.turn_line import _prune_none


# Leaf-eval term weights (ADR-0031 decision 4). Prizes KO_SCORE-weighted + DOMINANT — positional terms
# sum below one prize, so no positional board outranks a real KO (hard-rung invariant, decision 3).
_PLANNER_SURVIVAL_W = 50.0     # my Active survives predicted Incoming after the line (full turn)

_PLANNER_THREAT_W = 0.1        # per-point value of threat magnitude removed by the KO …

_PLANNER_THREAT_CAP = 100.0    # … capped, so a big threat still can't rival a prize

_PLANNER_DEV_W = 1.0           # development left on my end-of-turn board (engine-rank phase: bodies

_PLANNER_DEV_CAP = 100.0       # + attached Energy, `_board_development`) … capped below a prize

_PLANNER_VALUE_W = 80.0        # Tier-5 (ADR-0042): the Automatic Value Model's P(win) on the simmed
                               # end-of-turn board scales into a sub-prize band (< one KO_SCORE), so
                               # the learned leaf breaks prize-EQUAL ties, never overriding a prize

_LINE_CAP = 100.0             # the line account's POSITIVE contribution is capped so the hard-rung
                              # invariant holds strictly; the NEGATIVE spend side is deliberately uncapped

_CLASS_B_SPEND_IDS = frozenset({   # spend account: NEGATIVE weights for spending a scarce resource
    # ⚠️ a member no Strategy ships can never reach `OptionTrace.fired`, so the set silently reads
    # bigger than it is. Interlock: `tests/strategy/test_rung_id_literals_are_live.py`.
    "dont-search-an-empty-deck",
})

_ABILITY_FIRE_IDS = frozenset({    # POSITIVE weights for USING a beneficial setup Ability: the cards
    # drawn are a future resource the end board cannot show. Same shipped-roster interlock as above.
    "bench-the-comeback-drawer",
})


class LeafValueMixin:
    """The end-of-turn value a candidate line is ranked by."""

    # ---- leaf evaluation (ADR-0031 decision 4): scalar over the resulting end-of-turn board ---------
    def _leaf_value(self, *, prizes: float, active_survives: bool, threat_removed: float = 0.0,
                    development: float = 0.0, value: float = 0.0, readiness: float = 0.0,
                    line: float = 0.0) -> float:
        """The leaf-eval scalar over a board: prizes (dominant, KO_SCORE-weighted) + threat removed +
        survival + readiness + the signed ``line`` account + the value model. Every term below one prize."""
        return (KO_SCORE * prizes
                + min(_PLANNER_THREAT_CAP, _PLANNER_THREAT_W * threat_removed)
                + (_PLANNER_SURVIVAL_W if active_survives else 0.0)
                + min(_PLANNER_DEV_CAP, _PLANNER_DEV_W * development)
                + min(_READINESS_CAP, readiness)
                + _PLANNER_VALUE_W * value
                + min(_LINE_CAP, line))

    def _survives_after_ko(self, my_id, my_hp, opp_player) -> bool:
        """My body survives the opponent's Incoming AFTER I KO their Active — their best REMAINING
        attacker can't KO it. Their Active is excluded because the line Knocks it Out (ADR-0031)."""
        bench = (opp_player or {}).get("bench") or []
        return bool(my_hp) and self._incoming_worst(my_id, my_hp, bench) < my_hp

    def _incoming_worst(self, my_id, my_hp: int, opp_bodies) -> int:
        """The worst W/R-adjusted damage the opponent's affordable attackers among ``opp_bodies`` deal
        my body next turn — an upper bound, so a survival check stays conservative. 0 when unknown."""
        my_stat = self.stats.get(my_id) if (self.stats and my_id is not None) else None
        if not (my_stat and my_hp):                       # unknown my card → no claim (contract-preserving)
            return 0
        model = self._state_model
        if model is None:
            return 0                                      # no snapshot → no claim, as above
        # AREA-AT-DAMAGE-TIME (ADR-0070 §9) is ACTIVE, declared explicitly: this asks about the body
        # that will be Active AFTER my line, so inferring the area would manufacture phantom lethals.
        return int(model.theirs.reachable_incoming(
            {"id": my_id, "hp": my_hp}, bodies=opp_bodies,
            context=self._opp_attack_context, my_benched=False))

    def _threat_magnitude(self, opp) -> float:
        """The threat magnitude of the opponent's Active — its biggest printed attack — as the
        ``threat_removed`` term when a line KOs it. 0 when unknown."""
        stat = self.stats.get((opp or {}).get("id")) if (self.stats and opp) else None
        return float(getattr(stat, "maxDamage", 0) or 0) if stat else 0.0

    def _my_player(self, obs) -> dict:
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        return players[yi] if 0 <= yi < len(players) and players[yi] else {}

    def _opp_player(self, obs) -> dict:
        state = obs.get("current") or {}
        players = state.get("players") or []
        oi = 1 - state.get("yourIndex", 0)
        return players[oi] if 0 <= oi < len(players) and players[oi] else {}

    def _leaf_state_model(self, end, my_index: int):
        """The simulated end-of-turn board as a :class:`StateModel`. ``turn_boosts`` is DELIBERATELY
        not threaded — a Trainer boost is *"During this turn"* and has expired here (Issue #282)."""
        return StateModel.build(
            end, combat=self.combat, my_index=my_index, deck=self.deck,
            role_worth=self._role_value,
            # the BOUND METHOD, not a closure over ``end``: a hypothetical reached through `rebuilt`
            # must resolve its OWN hand, else the `hand` family goes constant (Issue #400 Phase 2)
            needs=self._leaf_needs_resolution)

    def _leaf_needs_resolution(self, end, my_index: int):
        """The `needs.Resolution` for a simulated end board's HAND, or None; never raises. The live
        `_state_model` MUST be restored — `_board_hypothetical` stashes one and this runs LIVE."""
        cur = (end or {}).get("current") or {}
        players = cur.get("players") or []
        me = players[my_index] if 0 <= my_index < len(players) and players[my_index] else {}
        if not me.get("hand"):
            return None
        mobs = {**end, "current": {**cur, "yourIndex": my_index}}
        live_model = getattr(self, "_state_model", None)
        try:
            board = self._board_hypothetical(mobs)
            rows = self._needs_hand_rows(mobs, board)
            discard_context = (mobs.get("select") or {}).get("context") == _DISCARD
            if discard_context:
                rows = self._as_discard_rows(rows, mobs, board)
            if not rows:
                return None
            # A discard projection freezes this root ledger across removals, so general-worth belongs
            # in saturating slots (duplicates cover one slot). Other leaf states retain the latent form.
            resolved = self._resolve_needs(mobs, board, rows,
                                           include_general=discard_context)
            slots, elig = resolved
            edge_values = resolved.edge_values
            if discard_context:
                # A row already classified as discard fuel/fodder has no KEEP supply. Fuel slots remain
                # eligible but are intentionally absent from state_value.hand's demand and coverage.
                elig = [({j for j in row_elig if slots[j].supplied_by_pitch}
                         if rows[i].get("pitch", 0) else row_elig)
                        for i, row_elig in enumerate(elig)]
                edge_values = [
                    {j: value for j, value in row_edges.items() if j in elig[i]}
                    for i, row_edges in enumerate(edge_values)
                ]
            if discard_context:
                latent_by_hand = tuple(0.0 for _ in rows)
            else:
                # deferred import: `common.pilot` imports THIS module, so a top-level import is a cycle
                from common.pilot import _GENERAL_WORTH_W
                resupply = [0.0] * len(slots)
                latent_by_hand = tuple(
                    needs.option_floor_residual(
                        slots, elig, resupply, i,
                        floor=_GENERAL_WORTH_W * self._role_value(r["cid"]),
                        edge_values=edge_values)
                    for i, r in enumerate(rows))
            return needs.Resolution(slots=tuple(slots), eligibility=tuple(elig),
                                    edge_values=tuple(edge_values),
                                    resupply=tuple([0.0] * len(slots)),
                                    hand_ids=tuple(r["cid"] for r in rows),
                                    latent_worth=float(sum(latent_by_hand)),
                                    latent_by_hand=latent_by_hand,
                                    unknowns=resolved.unknowns)
        except Exception:
            return None
        finally:
            # Restore unconditionally: the early `return None` paths above build a Board too.
            self._state_model = live_model

    def _board_hypothetical(self, obs):
        """Build a :class:`Board` on a HYPOTHETICAL obs for FEATURES only. The Carried State snapshot
        stops it writing turn-scoped memory; it does NOT guard the `_state_model` stash — callers do."""
        return self._board(obs, (obs or {}).get("select"), carried=self.carried())

    def _line_account(self, traces, indices) -> float:
        """The SIGNED path term for the CHOSEN options at ONE step: `_ABILITY_FIRE_IDS` credits minus
        `_CLASS_B_SPEND_IDS` magnitudes, off the LIVE tuned weights. Never a score of the end BOARD."""
        total = 0.0
        for i in indices:
            if not (0 <= i < len(traces)):
                continue
            for h, w in (getattr(traces[i], "fired", None) or ()):
                hid = getattr(h, "id", None)
                if w > 0 and hid in _ABILITY_FIRE_IDS:
                    total += w
                elif w < 0 and hid in _CLASS_B_SPEND_IDS:
                    total += w                            # w is negative — a spend subtracts
            total += getattr(traces[i], "attach_spend", 0.0) or 0.0   # the burst evaporation loss
        return total

    def _simulate_line(self, obs, first_step, max_steps: int = 40, *, opponent_reply: bool = False):
        """Forward-simulate a line to my end-of-turn board: ``(end_obs, my_index, start_prizes, result,
        line_account, coins)`` or None. **No production caller** — an OFFLINE engine primitive."""
        if not (obs or {}).get("search_begin_input") or not first_step:
            return None
        cgapi = getattr(self, "_search_api", None)     # injectable search backend (leaf-lab harness sets
        if cgapi is None:                              # cgpy's `cg.api`-shaped surface to re-score tagged
            try:                                       # correction boards offline); production uses native
                from cg import api as cgapi
            except Exception:
                return None
        from dataclasses import asdict
        cur = obs.get("current") or {}
        my_index = cur.get("yourIndex", 0)
        players = cur.get("players") or []
        me = players[my_index] if 0 <= my_index < len(players) and players[my_index] else {}
        opp = players[1 - my_index] if 0 <= 1 - my_index < len(players) and players[1 - my_index] else {}
        start_prizes = len(me.get("prize") or [])
        yd, yp, od, op_, oh = self._seed_zones(obs, me, opp)   # ADR-0050: exact own split when anchored

        def budget_ok() -> bool:
            if not opponent_reply:
                return True                            # Tier-1 sims are unbudgeted (the original path)
            self._search_steps = getattr(self, "_search_steps", 0) + 1
            return self._search_steps <= self.search_budget

        self._planning = True                          # never nest a search inside the reply policy
        line_val = 0.0
        try:
            root = self._evaluate(obs, carried=self.carried())   # the root re-score reads the phase /
            line_val += self._line_account(root.options,         # path memories off the Carried State
                                           list(first_step))     # snapshot and writes neither (ADR-0068)
            ob = cgapi.to_observation_class(obs)
            st = cgapi.search_begin(ob, yd, yp, od, op_, oh, [], manual_coin=False)
            st = cgapi.search_step(st.searchId, list(first_step))
            crossed_my_turn_end = False
            # `leaf_hand_value` captures my hidden hand off the last my-perspective step. It stays
            # OFF: that snapshot is one action stale, and arming it MEASURED worse (Issue #262).
            capture_hand = getattr(self, "leaf_hand_value", False)

            def _held_snapshot(player: dict, current: dict):
                if not player.get("hand"):
                    return None
                return {"hand": player["hand"],
                        "supporterPlayed": bool(current.get("supporterPlayed")),
                        "energyAttached": bool(current.get("energyAttached")),
                        "bodies": (player.get("active") or []) + (player.get("bench") or []),
                        "benchFull": len([b for b in (player.get("bench") or []) if b])
                                     >= (player.get("benchMax") or 5)}

            my_ctx = _held_snapshot(me, cur) if capture_hand else None
            coin_t = getattr(getattr(cgapi, "LogType", None), "COIN", None)

            def _saw_coin(ob) -> bool:
                return coin_t is not None and any(getattr(lg, "type", None) == coin_t
                                                  for lg in (getattr(ob, "logs", None) or ()))

            coins = False
            for _ in range(max_steps):
                o = st.observation
                coins = coins or _saw_coin(o)
                c = o.current
                if c is None or c.result != -1 or o.select is None:
                    break                                 # game over
                mine = c.yourIndex == my_index
                if not mine and not opponent_reply:
                    break                                 # Tier-1: stop at my turn end
                if not mine:
                    crossed_my_turn_end = True             # into the opponent's reply now
                elif crossed_my_turn_end:
                    break                                 # back to MY next turn — the depth-2 leaf
                if not budget_ok():
                    break                                 # per-move engine budget spent
                odict = _prune_none(asdict(o))
                if capture_hand and mine and not crossed_my_turn_end:
                    pcur = odict.get("current") or {}
                    ph = pcur.get("players") or []
                    meh = ph[my_index] if 0 <= my_index < len(ph) and ph[my_index] else {}
                    my_ctx = _held_snapshot(meh, pcur) or my_ctx
                dec = self._evaluate(odict)
                if mine and not crossed_my_turn_end:       # only MY within-turn actions carry a line term
                    line_val += self._line_account(dec.options, dec.chosen)
                st = cgapi.search_step(st.searchId, list(dec.chosen))
            coins = coins or _saw_coin(st.observation)       # the final step's logs (a coin-won attack)
            end = _prune_none(asdict(st.observation))
            if capture_hand and my_ctx:                   # inject my hidden hand + held-context
                epl = (end.get("current") or {}).get("players") or []
                if 0 <= my_index < len(epl) and isinstance(epl[my_index], dict):
                    epl[my_index]["hand"] = my_ctx["hand"]
                    epl[my_index]["heldCtx"] = {k: v for k, v in my_ctx.items() if k != "hand"}
            result = st.observation.current.result if st.observation.current else -1
            cgapi.search_end()
            return (end, my_index, start_prizes, result, line_val, coins)
        except Exception:
            try:
                cgapi.search_end()
            except Exception:
                pass
            return None
        finally:
            self._planning = False

    def _role_value(self, cid) -> float:
        """Card ``cid``'s base worth — the MAX claim over its declared/derived Roles, its behavioural
        tags and the energy / ACE-SPEC fallbacks. Delegates to `card_worth.role_value` (ADR-0065)."""
        from common.card_worth import role_value
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        roles = self._roles_of(cid)
        if cid is not None and cid in self._line_preevo_set():
            roles = [*roles, "win_condition_base"]      # derived worth only — not injected into c.roles
        return role_value(
            roles,
            is_ace_spec=bool(st is not None and getattr(st, "aceSpec", False)),
            is_typed_basic_energy=bool(st is not None and getattr(st, "is_typed_basic_energy", False)),
            tags=self.functions.tags(cid) if (self.functions and cid is not None) else (),
            is_known_card=st is not None,
            worth_override=self.strategy.worth_overrides.get(cid, 0.0))

    def _keep_cost(self, cid, counts: dict, pool: int, draws: int, board=None,
                   shuffled_copies: int = 1, prizes_hidden: int = 0, deck_count=None) -> float:
        """The cost of shuffling ONE held copy of ``cid`` away = role worth × un-recoverability ×
        deadline realisability. Pre-anchor the re-access odds are prize-split-weighted (ADR-0065)."""
        role_value = self._role_value(cid)
        if role_value <= 0:
            return 0.0
        from common import gate_library
        from common.card_worth import keep_cost
        from common.deck_odds import draw_hit_probability
        outs = self._card_reaccess_outs(cid, counts)
        certain = max(1, shuffled_copies)
        if prizes_hidden > 0:
            d = deck_count if deck_count is not None else max(0, sum(counts.values()) - prizes_hidden)
            reaccess = self._prize_split_hit(outs, d, prizes_hidden, pool, draws, certain=certain)
        else:
            reaccess = draw_hit_probability(outs + certain, pool, draws)
        # the CLOSING edge: a doom-answering card's re-access is not bankable against its deadline
        reaccess = gate_library.closing_gate_reaccess(
            reaccess, gate_closing=self._gate_closing(cid, board) if board is not None else False)
        deadline = self._deploy_odds(cid, board, counts) if board is not None else 1.0
        return keep_cost(role_value, reaccess, deadline)

    def _gate_closing(self, cid, board) -> bool:
        """The closing-edge resolver: a closing gate SPIKES keep, because re-access is not bankable
        against a THIS-TURN deadline. Two edges — deploy-now, and pressure while the Active is doomed."""
        if cid is not None and cid in getattr(board, "deploy_now_ids", frozenset()):
            return True
        if not getattr(board, "active_doomed", False):
            return False
        if cid in self._wincon_set() and getattr(board, "line_preevo_in_play", False):
            return True
        tags = self.functions.tags(cid) if self.functions else ()
        return "clutch_heal" in tags or "switch" in tags

    def _hand_keep(self, hand_ids, played_cid, counts: dict, pool: int, draws: int, board=None,
                   prizes_hidden: int = 0, deck_count=None) -> float:
        """Σ keep_cost over the hand a refresh shuffles away — the ONE summation BOTH keep-value sites
        read. ``hand_ids`` is a LIST: duplicates price MARGINALLY, once-per-turn cards by RANK."""
        ids = list(hand_ids)
        if played_cid in ids:
            ids.remove(played_cid)
        from collections import Counter
        from common import gate_library
        played_st = self.stats.get(played_cid) if (self.stats and played_cid is not None) else None
        sup_spent = bool(getattr(board, "supporter_played", False)
                         or (played_st is not None and getattr(played_st, "is_supporter", False)))
        total = 0.0
        for cid, k in Counter(ids).items():
            st = self.stats.get(cid) if self.stats else None
            if st is not None and getattr(st, "is_energy", False):
                spent = bool(getattr(board, "energy_attached", False))
            elif st is not None and getattr(st, "is_supporter", False):
                spent = sup_spent
            else:
                total += k * self._keep_cost(cid, counts, pool, draws, board, shuffled_copies=k,
                                             prizes_hidden=prizes_hidden, deck_count=deck_count)
                continue
            total += sum(self._keep_cost(cid, counts, pool,
                                         gate_library.quota_window(draws, j, quota_spent=spent),
                                         board, shuffled_copies=k,
                                         prizes_hidden=prizes_hidden, deck_count=deck_count)
                         for j in range(1, k + 1))
        return total
