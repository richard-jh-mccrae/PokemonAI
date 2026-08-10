"""The Turn Planner (ADR-0031/0037): the Pilot's ONE planning entry. ``plan_turn`` runs the Goal
Ladder — locked-line replay -> win rung -> closed-form KO pool -> gamble rung -> the composer.

The win rung (Lethal Solver, ADR-0030) is SOUND and preempts every heuristic rung below it; a scored
line may never override a verified one. The composer (`common.composer`, ADR-0092 §4-T4) decides MAIN
and provenance-backed CARD continuations when the earlier rungs decline.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations

from common import action_cost, composer, needs, playability
from common.apply_engine import CARD_CONTINUATION_CONTEXTS
from common.board_delta import Unmodellable
from common.option_equivalence import AREA_DECK
from common.state_model import StateModel
from common.state_value import WIN_PRIZES, state_value
from common.strategy.combat import Budget, units_for_codes
from common.strategy.context import (_ACTIVE, _ATTACH, _ATTACK, _ATTACKER_ROLES, _BASIC_ENERGY, _BENCH,
                                     _COIN_HEAD, _END, _EVOLVE, _MAIN, _PLAY, _RETREAT, _SPECIAL_ENERGY,
                                     _TO_HAND, KO_SCORE)

# --- the families (`common/strategy/planning/`) ---
from common.strategy.planning.gamble import (GambleMixin, _PLANNER_ENABLER_ITEM_SLOT, _PLANNER_ENABLER_ITEM_BASE)  # noqa: F401
from common.strategy.planning.ko_classes import KoClassMixin
from common.strategy.planning.ladder import (GoalLadderMixin, _PLANNER_PATH_W, _PLANNER_ENABLER_FREE,
                                             _PLANNER_GAMEPLAN_W, _PLANNER_DECKOUT_W, _PLANNER_DECKOUT_TURNS)  # noqa: F401
from common.strategy.planning.leaf import (LeafValueMixin, _PLANNER_SURVIVAL_W, _PLANNER_THREAT_W,
                                           _PLANNER_THREAT_CAP, _PLANNER_DEV_W, _PLANNER_DEV_CAP,
                                           _PLANNER_VALUE_W, _LINE_CAP, _CLASS_B_SPEND_IDS, _ABILITY_FIRE_IDS)  # noqa: F401
from common.strategy.planning.readiness import (_READINESS_CAP, _READINESS_BODY_CAP, _READINESS_BENCH_DISCOUNT,
                                                _READINESS_PROMO_MAX, _READINESS_MOBILITY_W, _READINESS_ATTACK_W,
                                                _READINESS_SATURATED, _READINESS_ABILITY_VALUE,
                                                _READINESS_ENGINE_ABILITY)  # noqa: F401
from common.strategy.planning.turn_line import (_prune_none, _PRIZE_AREA, _rng_probe, _GOAL_LINE, TurnLine,
                                                _WEIGHTED_GOALS, _composed_rank)  # noqa: F401
from common.strategy.planning.wins import WinLineMixin


def _tied_first_steps(result, chosen, options, traces) -> list:
    """Menu indices whose best sequence ties ``chosen``'s score at `apply_option.SCORE_PLACES` — the
    composer having NO OPINION about which action to take first, so the caller defers (ADR-0131)."""
    from common.apply_option import SCORE_PLACES
    candidates = getattr(result, "selection_candidates", ()) or getattr(result, "candidates", ())
    if not candidates:
        return []

    def score_before_residual(candidate) -> float:
        """Compare Composer knowledge before its ordinal residual.

        A residual-only attack/End distinction is intentionally handed to Pilot: its tactical
        oracle may know an attack rider (for example, a copied top-deck attack) Composer cannot.
        The final trace still pays the residual, so a true no-op loses to End after this abstention.
        """
        terminal = getattr(candidate, "terminal", None) or {}
        return float(candidate.score) + action_cost.residual_cost_prizes(terminal.get("type"))

    key = round(score_before_residual(chosen), SCORE_PLACES)
    mine = chosen.first_index

    def distinct(index: int) -> bool:
        """False for two copies of the same revealed-by-menu deck card: one decision, two indices."""
        if not (isinstance(mine, int) and 0 <= mine < len(options)
                and isinstance(index, int) and 0 <= index < len(options)):
            return True
        left, right = options[mine], options[index]
        left_id = getattr(traces[mine], "card_id", None) if mine < len(traces) else None
        right_id = getattr(traces[index], "card_id", None) if index < len(traces) else None
        return not (left.get("area") == right.get("area") == AREA_DECK
                    and left.get("type") == right.get("type")
                    and left.get("playerIndex") == right.get("playerIndex")
                    and left_id is not None and left_id == right_id)

    tied = set()
    for candidate in candidates:
        if candidate.coverage_gap or round(score_before_residual(candidate), SCORE_PLACES) != key:
            continue
        indices = {candidate.first_index}
        indices.update(path[0] for path in getattr(candidate, "origin_indices", ()) if path)
        tied.update(index for index in indices
                    if index is not None and index != mine and distinct(index))
    return sorted(tied)


class PlannerMixin(
    # base order IS ladder order, top rung first
    WinLineMixin, GoalLadderMixin, GambleMixin, KoClassMixin,
    LeafValueMixin,
):
    """Pilot-side Turn Planner. ``plan_turn`` returns a :class:`TurnLine` to commit, or None to defer
    to the tuned scoring. Depends on Pilot internals, so it is mixed into the Pilot."""

    def plan_turn(self, obs, select, board, options, traces) -> TurnLine | None:
        """The best committed Turn Line at MAIN or a replayable single-pick CARD continuation."""
        if not self._planning:                        # never wipe the OUTER decision's refute count when
            self._lethal_refutes = 0                  # a verify cascade re-enters here under _planning
        context = select.get("context")
        if context == _MAIN:
            eligible = select.get("maxCount", 0) == 1
        else:
            minimum = select.get("minCount", 0)
            maximum = select.get("maxCount", 0)
            # A continuation can commit exactly one card.  A multi-pick menu (Turbo Flare's
            # 0--3 Basic Energy selection, for example) must fall through to the multi-pick
            # selector; a composed TurnLine only carries one next-step index.
            eligible = (context in CARD_CONTINUATION_CONTEXTS
                        and 0 <= minimum <= 1
                        and maximum == 1)
        if not eligible:
            return None
        if self._planning:                            # mid engine-sim: closed-form only, never nest search
            win = self._win_line(obs, select, board, options, traces)
            if win is not None:
                return win
            return self._closed_form_plan(obs, select, board, options, traces)
        fp = self._plan_fingerprint(obs, select)
        if self._turn_plan is not None and self._turn_plan[0] == fp:
            return self._turn_plan[1]                 # cache hit: re-plan only on reveal (fingerprint change)
        self._gamble_trace = None                     # fresh plan: clear the gamble working-trace (the
        self._composer_trace = None                   # sparse `gamble` / `composer` telemetry blocks)
        line = self._win_line(obs, select, board, options, traces)
        if line is None:
            candidates = self._closed_form_candidates(obs, select, board, options, traces)
            line = self._commit_best(obs, candidates, traces=traces)
        if line is None:                              # Tier-2 Gamble rung (ADR-0039): below every
            line = self._best_gamble_line(obs, select, board, options, traces)   # deterministic goal
        # Tier-6 escalation (ADR-0043) REMOVED — deprecated by ADR-0064 decision 6.
        if line is None:                              # POC-T4/5: the composer, unflagged and ungated —
            line = self._composer_line(obs, select, board, options, traces)   # the MAIN decider
        self._turn_plan = (fp, line)
        return line

    def _closed_form_plan(self, obs, select, board, options, traces) -> TurnLine | None:
        """The single closed-form Goal-Ladder verdict (no engine) — the mid-sim / switch-off pick:
        best candidate by closed-form leaf value, ties to the first generated."""
        candidates = self._closed_form_candidates(obs, select, board, options, traces)
        return max(candidates, key=lambda ln: ln.value) if candidates else None

    def _closed_form_candidates(self, obs, select, board, options, traces) -> list:
        """All closed-form lines. A cost-positive stabilize+KO line preempts a status-quo KO;
        otherwise this layer is empty when tuned scoring already reaches a KO."""
        stabilize = self._stabilize_then_ko_lines(obs, select, board, options, traces)
        if stabilize:
            return stabilize
        if any(t.tactical >= KO_SCORE for t in traces):
            return []
        candidates = self._ko_for_prizes_lines(obs, select, board, options, traces)
        if self.planner_key_threat:
            candidates += self._ko_key_threat_lines(obs, select, board, options)
        return candidates

    def _stabilize_then_ko_lines(self, obs, select, board, options, traces) -> list:
        """Heal a doomed Active first when a costed re-attach still KOs and flips post-KO survival."""
        if not board.active_doomed:
            return []
        if not any(o.get("type") in (_ATTACK, _ATTACH) and t.tactical >= KO_SCORE
                   for o, t in zip(options, traces)):
            return []
        opp = self._opp_active(obs)
        opp_player = self._opp_player(obs)
        active_stat = (self.stats.get(board.my_active_id)
                       if (self.stats and board.my_active_id is not None) else None)
        if not (opp and active_stat and opp_player):
            return []

        me = self._my_player(obs)
        active_body = next((p for p in (me.get("active") or []) if p), None)
        if active_body is None:
            return []
        attached_codes = tuple(active_body.get("energies") or ())
        attach_choices = {((), 0.0)}
        if not board.energy_attached:
            for option in options:
                if option.get("type") != _ATTACH or option.get("inPlayArea") != _ACTIVE:
                    continue
                energy_id = self._option_card_id(obs, select, option)
                energy_stat = self.stats.get(energy_id) if (self.stats and energy_id is not None) else None
                if energy_stat is None:
                    continue
                codes = tuple(self.combat.provision_codes_or_floor(energy_id, active_stat))
                if codes:
                    attach_choices.add((codes, self._role_value(energy_id)))

        lines = []
        promoters = opp_player.get("bench") or []
        for index, option in enumerate(options):
            if option.get("type") != _PLAY:
                continue
            card_id = self._option_card_id(obs, select, option)
            if card_id is None:
                continue
            card_cost = self._role_value(card_id)
            if card_cost <= 0:
                continue
            best = None
            for attach_codes, attach_cost in attach_choices:
                healed = self._heal_body_candidate(
                    card_id, active_stat, is_active=True, cur_hp=board.my_active_hp,
                    attached=board.my_active_energy, attach_units=len(attach_codes))
                if healed is None:
                    continue
                healed_hp, energy_total = healed
                incoming = self._incoming_worst(board.my_active_id, healed_hp, promoters)
                if not (board.my_active_hp <= incoming < healed_hp):
                    continue
                # The heal helper owns the post-rider COUNT. Preserve the exact colours of whatever
                # attached units remain, then put the hypothetical manual attach in the typed Budget.
                # This covers bounce-all, discard-one, and ordinary heals without letting a {C}
                # provider phantom-pay a specific attack slot.
                retained = energy_total - len(attach_codes)
                if not 0 <= retained <= len(attached_codes):
                    continue
                if retained == len(attached_codes):
                    retained_states = (attached_codes,)
                else:
                    retained_states = tuple({
                        tuple(attached_codes[i] for i in keep)
                        for keep in combinations(range(len(attached_codes)), retained)
                    })
                budget = Budget(options=(units_for_codes(attach_codes),))
                ko_value = max((self._best_affordable_ko_value(
                    obs, board, opp, board.my_active_id, energy_total,
                    body={**active_body, "energies": list(codes)}, budget=budget)
                    for codes in retained_states), default=0.0)
                if ko_value <= 0:
                    continue
                total_cost = card_cost + attach_cost
                prizes = self._prize_value(opp)
                benefit = self._leaf_value(
                    prizes=prizes, active_survives=True,
                    threat_removed=self._threat_magnitude(opp))
                benefit += ko_value - (KO_SCORE + prizes)
                net = benefit - total_cost
                if net > 0 and (best is None or net > best[0]):
                    best = (net, benefit, total_cost)
            if best is None:
                continue
            net, benefit, total_cost = best
            lines.append(TurnLine(
                next_step=[index], goal="stabilize_then_ko", value=net,
                rationale=(f"heal, re-attach, KO: {benefit:.1f} benefit - "
                           f"{total_cost:.1f} card cost = {net:.1f}"),
                ranked_by="cost-benefit", kind="sequence"))
        return lines

    def _deferral_value(self, traces) -> float:
        """What the turn is worth if the pool commits NOTHING — the tuned/greedy pick's own score
        (ADR-0074 decision 5). 0.0 with no traces: an unreadable alternative never vetoes a line."""
        return max((getattr(t, "score", 0.0) or 0.0 for t in (traces or ())), default=0.0)

    def _commit_best(self, obs, candidates, *, traces=()) -> TurnLine | None:
        """The closed-form best of the candidate pool, floored: a `_WEIGHTED_GOALS` line worth no
        more than the tuned alternative defers rather than commits (ADR-0074 decision 5)."""
        if not candidates:
            return None
        best = max(candidates, key=lambda ln: ln.value)
        if best.goal in _WEIGHTED_GOALS and best.value <= self._deferral_value(traces):
            return None                                  # loses to the alternative — defer
        return best

    # ═══ THE COMPOSER RUNG (POC-T4/5, Issue #386) — the MAIN / seeded-continuation decider.

    def _composer_line(self, obs, select, board, options, traces) -> TurnLine | None:
        """The composer's committed first action as a ``goal="compose"`` Turn Line, or None. ``shed``
        must be threaded: unwired, `compose` REFUSES every costed search. ``search_api`` is inert."""
        my_index = int((obs.get("current") or {}).get("yourIndex") or 0)
        live_model = self._state_model
        try:
            model = self._leaf_state_model(obs, my_index)
            context = (select or {}).get("context")
            result = composer.compose(model, options,
                                      search_api=self._composer_search_api(obs),
                                      shed=self.cost_shed_indices,
                                      continuation_boundary=context in CARD_CONTINUATION_CONTEXTS,
                                      required_pick=(context in CARD_CONTINUATION_CONTEXTS
                                                     and int((select or {}).get("minCount") or 0) >= 1))
        except Unmodellable:
            return None
        finally:
            # Building Composer leaves recursively asks the Pilot-owned needs callback, which builds
            # hypothetical Boards. The root attach resolver runs after Composer and must never read
            # whichever projected hand happened to be evaluated last.
            self._state_model = live_model
        chosen = result.chosen
        self._composer_trace = {"margin": result.margin.working(), **result.working()}
        continuation = context in CARD_CONTINUATION_CONTEXTS
        coverage_gap = continuation and any(delta is None for delta in result.fanned)
        if coverage_gap or chosen is None or chosen.first_index is None or chosen.coverage_gap:
            return None
        first_card = getattr(traces[chosen.first_index], "card_id", None)
        first_tags = set(self.functions.tags(first_card)) if (self.functions and first_card is not None) else set()
        if board.recycle_dead_only and "recycle" in first_tags:
            # The leaf can see that a card returned to hand exists, but only Board owns the
            # zone/playability fact that this recycler can return no usable card.  Do not let an
            # unrealizable known-card floor turn a pure-cost recycle into a composed first step.
            self._composer_trace["dead_recycle_refused"] = chosen.first_index
            return None
        if ("cost_discard" in first_tags and traces[chosen.first_index].score <= 0.0
                and len(chosen.steps) == 1 and chosen.terminal_ev <= 0.0):
            # A costly fetch with neither a priced target nor a follow-on terminal has realised no
            # benefit.  A tiny hand-ledger movement cannot pay its discard cost or outrank End.
            self._composer_trace["pure_cost_fetch_refused"] = chosen.first_index
            return None
        if options[chosen.first_index].get("type") == _ATTACH:
            attach_row = self._attach_value(obs, select, board, options[chosen.first_index])
            direct_kos = [i for i, trace in enumerate(traces)
                          if options[i].get("type") == _ATTACK and trace.tactical >= KO_SCORE]
            other_positive_setup = any(
                options[i].get("type") not in (_ATTACH, _ATTACK, _END) and trace.score > 0.0
                for i, trace in enumerate(traces))
            if (attach_row is not None and float(attach_row["tactical"]) <= 0.0
                    and direct_kos and not other_positive_setup):
                winner = max(direct_kos, key=lambda i: (traces[i].tactical, -i))
                self._composer_trace["pure_cost_attach_before_ko_refused"] = chosen.first_index
                return TurnLine(next_step=[winner], goal="compose", value=float(traces[winner].score),
                                rationale="cost-benefit: take the decisive attack before a non-beneficial attach",
                                ranked_by="cost-benefit", kind="boundary")
        tied = _tied_first_steps(result, chosen, options, traces)
        if options[chosen.first_index].get("type") == _ATTACH:
            attach_override = self._attach_sequence_override(
                obs, select, board, options, traces, chosen.first_index,
                composed_result=result, score_epsilon=composer.EPSILON, same_line_only=True)
            if attach_override is not None:
                index, reason = attach_override
                self._composer_trace["attach_cost_benefit_override"] = {
                    "from": chosen.first_index, "to": index, "reason": reason}
                return TurnLine(next_step=[index], goal="compose", value=float(traces[index].score),
                                rationale=reason, ranked_by="cost-benefit", kind="boundary")
        if tied:
            self._composer_trace["tied_first_steps"] = tied
            return None
        retreat_override = self._retreat_sequence_override(
            select, board, options, traces, chosen.first_index)
        if retreat_override is not None:
            index, reason = retreat_override
            self._composer_trace["retreat_cost_benefit_override"] = {
                "from": chosen.first_index, "to": index, "reason": reason}
            return TurnLine(next_step=[index], goal="compose", value=float(traces[index].score),
                            rationale=reason, ranked_by="cost-benefit", kind="boundary")
        fetch_override = self._fetch_sequence_override(
            obs, select, board, options, traces, chosen.first_index, composed_result=result)
        if fetch_override is not None:
            index, reason = fetch_override
            self._composer_trace["fetch_cost_benefit_override"] = {
                "from": chosen.first_index, "to": index, "reason": reason}
            return TurnLine(next_step=[index], goal="compose", value=float(traces[index].score),
                            rationale=reason, ranked_by="cost-benefit", kind="boundary")
        refresh_override = self._refresh_sequence_override(
            obs, select, options, traces, chosen.first_index)
        if refresh_override is not None:
            index, reason = refresh_override
            self._composer_trace["refresh_cost_benefit_override"] = {
                "from": chosen.first_index, "to": index, "reason": reason}
            return TurnLine(next_step=[index], goal="compose", value=float(traces[index].score),
                            rationale=reason, ranked_by="cost-benefit", kind="boundary")
        attach_override = self._attach_sequence_override(
            obs, select, board, options, traces, chosen.first_index,
            composed_result=result, score_epsilon=composer.EPSILON)
        if attach_override is not None:
            index, reason = attach_override
            self._composer_trace["attach_cost_benefit_override"] = {
                "from": chosen.first_index, "to": index, "reason": reason}
            return TurnLine(next_step=[index], goal="compose", value=float(traces[index].score),
                            rationale=reason, ranked_by="cost-benefit", kind="boundary")
        self._composer_trace["chosen"] = chosen.working()
        self._composer_trace["steps"] = [s.index for s in chosen.steps]
        # `steps` is [] on a terminal line (attack / End), so the committed index is named separately
        self._composer_trace["first_index"] = chosen.first_index
        return TurnLine(next_step=[chosen.first_index], goal="compose", value=chosen.score,
                        rationale="compose: the best within-turn sequence's first action",
                        ranked_by="composer", kind="sequence")

    def _composer_search_api(self, obs):
        """Resolve the injected test seam or the packaged engine only for seeded live observations."""
        injected = getattr(self, "_search_api", None)
        if injected is not None:
            return injected
        if not getattr(self, "leaf_followups", False):
            return None
        context = ((obs or {}).get("select") or {}).get("context")
        if context not in CARD_CONTINUATION_CONTEXTS or not (obs or {}).get("search_begin_input"):
            return None
        from cg import api
        return api
