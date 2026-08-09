"""The Turn Planner (ADR-0031/0037): the Pilot's ONE planning entry. ``plan_turn`` runs the Goal
Ladder — locked-line replay -> win rung -> closed-form KO pool -> gamble rung -> the composer.

The win rung (Lethal Solver, ADR-0030) is SOUND and preempts every heuristic rung below it; a scored
line may never override a verified one. The composer (`common.composer`, ADR-0092 §4-T4) decides MAIN
and provenance-backed CARD continuations when the earlier rungs decline.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from common import composer, needs, playability
from common.apply_engine import CARD_CONTINUATION_CONTEXTS
from common.board_delta import Unmodellable
from common.option_equivalence import AREA_DECK
from common.state_model import StateModel
from common.state_value import WIN_PRIZES, state_value
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
    key = round(chosen.score, SCORE_PLACES)
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

    tied = {c.first_index for c in candidates
            if c.first_index is not None and c.first_index != mine
            and not c.coverage_gap and round(c.score, SCORE_PLACES) == key
            and distinct(c.first_index)}
    return sorted(tied)


def _unspent_burst_substitute(rows, chosen_index):
    """Prefer a reusable Energy on the same body when Composer picked an evaporating burst."""
    chosen = next((row for row in rows if row.get("i") == chosen_index), None)
    if not chosen or not (chosen.get("burst") and chosen.get("evaporates")):
        return None
    alternatives = [row for row in rows
                    if row.get("slot") == chosen.get("slot") and not row.get("burst")
                    and row.get("tactical", 0.0) > chosen.get("tactical", 0.0)]
    return max(alternatives, key=lambda row: (row["tactical"], -row["i"]))["i"] if alternatives else None


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
            eligible = context in CARD_CONTINUATION_CONTEXTS and 0 <= minimum <= 1 <= maximum
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
        """ALL candidate Turn Lines from closed-form generation, highest rung first. Strictly
        layer-on-top: empty when the tuned machinery already reaches a KO (a KO_SCORE-class trace)."""
        if any(t.tactical >= KO_SCORE for t in traces):
            return []
        candidates = self._ko_for_prizes_lines(obs, select, board, options, traces)
        if self.planner_key_threat:
            candidates += self._ko_key_threat_lines(obs, select, board, options)
        return candidates

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
        chosen = result.chosen
        self._composer_trace = {"margin": result.margin.working(), **result.working()}
        continuation = context in CARD_CONTINUATION_CONTEXTS
        coverage_gap = continuation and any(delta is None for delta in result.fanned)
        if coverage_gap or chosen is None or chosen.first_index is None or chosen.coverage_gap:
            return None
        by_score = self._score_order(obs, options, traces)
        ordered = self._finish_turn_last(obs, board, options, traces, by_score,
                                         int((select or {}).get("maxCount") or 0), context)
        informative = ordered[0] if ordered else None
        info_card = getattr(traces[informative], "card_id", None) if informative is not None else None
        info_tags = set(self.functions.tags(info_card) or ()) if self.functions and info_card else set()
        if (informative is not None and informative != chosen.first_index
                and options[informative].get("type") == _PLAY
                and "dig" in info_tags):
            self._composer_trace["information_first"] = {
                "from": chosen.first_index, "to": informative,
            }
            return TurnLine(next_step=[informative], goal="information", value=chosen.score,
                            rationale="collect information before committing a turn resource",
                            ranked_by="information_first", kind="sequence")
        attach_rows = (self._attach_working(obs, select, board, options) or {}).get("eq", ())
        substitute = _unspent_burst_substitute(attach_rows, chosen.first_index)
        if substitute is not None:
            self._composer_trace["unspent_burst_substitute"] = {
                "from": chosen.first_index, "to": substitute,
            }
            return TurnLine(next_step=[substitute], goal="attach_safety", value=chosen.score,
                            rationale="keep reusable Energy when the burst cannot cash this turn",
                            ranked_by="attach_safety", kind="sequence")
        tied = _tied_first_steps(result, chosen, options, traces)
        if tied:
            self._composer_trace["tied_first_steps"] = tied
            return None
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
