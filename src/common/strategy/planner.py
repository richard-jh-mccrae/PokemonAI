"""The Turn Planner (ADR-0031/0037): the eager whole-turn optimizer and the Pilot's ONE planning
entry point — the **Lethal Solver is its sound top rung**.

A deck-agnostic Pilot Mixin that runs at the start of my turn. ``plan_turn`` runs the Goal Ladder:

    locked-line replay -> win rung -> the closed-form KO pool -> gamble rung -> **the composer**

The **win rung** is first (the Lethal Solver, ADR-0030 — sound, engine-verified, preempting every
heuristic goal); the KO pool and the Gamble rung generate closed-form enabling lines by working
backward from a prioritized set of **Turn Goals**; and the bottom rung is `common.composer`, which
decides every MAIN single-pick frame the rungs above declined. See
``docs/adr/0037-lethal-solver-is-the-turn-planners-top-rung.md`` and the *Turn Planner* / *Turn
Goal* / *Turn Line* / *Lethal Solver* terms in ``common/CONTEXT.md``.

**The composer is the MAIN decider** (POC-T4/5, Issue #386; ADR-0092 §4-T4). It is not "below the
tuned Hypothesis scoring" — it REPLACES the greedy argmax at MAIN, which is why the heal, Tool-equip,
gust whether-to-play, draw/dig economy, hand-disruption, Stadium and `retreat-to-wall-the-line` rung
families were deleted in the same change and why `stabilize-then-KO` and the `forgo-KO` gate are gone
from this module. A rung asserting a preference the leaf can compute by differencing end states is a
second opinion about the same board, and ADR-0092 decision 4 allows exactly one.

**Two soundness regimes, one module.** The win rung locks only a GUARANTEED win: min-bound damage
floors, worst-case coins, and the `_engine_confirms_win` verdict-driver (refute drops the candidate;
an unreachable verdict keeps the sound closed-form lock). Everything below it is **heuristic** — it
SCORES rather than proves — so the win rung stays preempting and a scored line can never override a
verified one. That ordering is Issue #263's ruling and its reason is asymmetric cost: a missed win
costs a turn, a phantom win costs the match.

**Layer-on-top (ADR-0031 decision 6) applies to the closed-form KO pool, not to the composer.** The
pool empties whenever the tuned menu already reaches a KO, so it only ever adds a line greedy would
MISS. The composer has no such gate by design: a decider that fires only where a heuristic says
greedy is unsure would leave greedy deciding everywhere else, which is the thing being replaced.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from common import composer, needs, playability
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


_COMPOSER_GAP_K = 8           # composer rung: how many coverage-gap reasons ride the sparse `composer`
                              # telemetry block. A cap, not a filter — the count is in `stats`, so a
                              # truncated list can never read as "that was all of them". Sized to keep a
                              # per-decision record readable; the exhaustive list is the lab's job
                              # (`tools/train/composer_lab.py`), which replays the same frames offline.


def _tied_first_steps(result, chosen) -> list:
    """Menu indices whose best sequence ties ``chosen``'s score — the composer having NO OPINION
    about which action to take first. **ADR-0131 decision 2.**

    Compared at `composer._SCORE_PLACES`, the same float-noise floor `selection_key` uses, so this
    reads "tied" exactly where that key does and the two cannot drift apart into a decision that is
    a tie to one and not to the other.

    **Why a tie must not be broken by the composer.** `selection_key` breaks it — by Worth, then by
    a stable card-id sort — and that is right when the tie is between members of one Option
    Equivalence Class, which is a tie about nothing. It is wrong when the tie is between genuinely
    different actions, because there the composer is reporting *"these end the turn in the same
    place"*, which is not the same claim as *"take this one"*. `sound_rules.
    information-before-commitment` is the standing ruling on what to do instead, and it is explicit
    that this case exists and is not reachable from the end state: *"both orders reach the same end
    state, so no function of that state separates them (ADR-0095 decision 3)."* A composer is a
    function of the end state.

    Measured on that ADR's own anchor frame, `ms_information_before_commitment_f11`: the composer
    prices SEVEN of the ten options at exactly 0.0 — the ruled Pokégear 3.0, both Crushing Hammers,
    both Tools, an attach and End — and `selection_key` hands the turn to the attach. The human
    ruled the dig, `_finish_turn_last` sequences the dig first, and the composer's own numbers say
    it has no view either way.

    So this is the FOURTH defer, and the same kind as the three the caller already documents: a
    refusal to guess. The tuned scoring keeps the turn, which is where the structural sequencer
    lives. Equivalence-class ties are unaffected — the ladder picks a class member too, and a tie
    about nothing stays a tie about nothing whichever mechanism resolves it.
    """
    from common.composer import _SCORE_PLACES
    if not getattr(result, "candidates", ()):
        return []
    key = round(chosen.score, _SCORE_PLACES)
    mine = chosen.first_index
    tied = {c.first_index for c in result.candidates
            if c.first_index is not None and c.first_index != mine
            and not c.coverage_gap and round(c.score, _SCORE_PLACES) == key}
    return sorted(tied)


class PlannerMixin(
    # the ladder, top rung first: a provable win, else the best goal, else a priced gamble
    WinLineMixin, GoalLadderMixin, GambleMixin, KoClassMixin,
    # what every rung is ranked by
    LeafValueMixin,
):
    """Pilot-side Turn Planner. ``plan_turn`` returns a :class:`TurnLine` to commit, or None to defer
    to the tuned scoring. Depends on Pilot internals (``_opp_active``, ``_best_affordable_ko_value``,
    ``_prize_value``, the per-option ``OptionTrace``), so it is mixed into the Pilot."""

    def plan_turn(self, obs, select, board, options, traces) -> TurnLine | None:
        """The best committed Turn Line this turn, or None. Only acts at the single-pick MAIN menu;
        every other context (search, snipe, mulligan, multi-select) defers to the tuned scoring.

        The Goal Ladder runs top-down (ADR-0037): the **win rung** first — the Lethal Solver's sound
        lock, which preempts every heuristic goal and never enters ranking — then the closed-form KO
        pool, the Gamble rung, and finally **the composer** (POC-T4/5, Issue #386), which decides
        every MAIN frame the rungs above declined. Plan once, cache, re-plan on reveal (ADR-0031 decision 5): the verdict (win lock
        included) is cached as turn-scoped state keyed by a board fingerprint, so the plan — and the
        win rung's engine verify — is computed once per board and re-derived only when a search/draw
        reveals information that changes the fingerprint (`lethal_refuted` is thereby counted
        per-plan, not per-decision). While an engine sim is re-running my policy (``_planning``), it
        stays closed-form and uncached so it never launches a nested search."""
        if not self._planning:                        # per-plan engine-refute count (telemetry). A verify
            self._lethal_refutes = 0                  # cascade re-runs decide() -> re-enters here under
                                                      # _planning: never wipe the OUTER decision's count
                                                      # mid-scan (an in-sim call can't refute anyway — the
                                                      # verify gate is closed)
        if select.get("context") != _MAIN or select.get("maxCount", 0) != 1:
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
        # Tier-6 escalation (ADR-0043) REMOVED — deprecated by ADR-0064 Decision 6 (its depth-2 reply
        # sim was blind to hidden-hand development; already inert in production, search_budget=0).
        if line is None:                              # POC-T4/5: the composer, unflagged and ungated —
            line = self._composer_line(obs, select, board, options, traces)   # the MAIN decider
        self._turn_plan = (fp, line)
        return line

    def _closed_form_plan(self, obs, select, board, options, traces) -> TurnLine | None:
        """The single closed-form Goal-Ladder verdict (no engine) — the mid-sim / switch-off pick:
        the best candidate by closed-form leaf value, ties to the first generated (the original
        single-line behavior, exactly)."""
        candidates = self._closed_form_candidates(obs, select, board, options, traces)
        return max(candidates, key=lambda ln: ln.value) if candidates else None

    def _closed_form_candidates(self, obs, select, board, options, traces) -> list:
        """ALL candidate Turn Lines from closed-form generation, highest rung first.

        The pool is strictly layer-on-top: it empties when the tuned machinery already reaches a KO
        (any option scored KO_SCORE-class), else it holds every **KO-for-prizes** enabling line plus —
        behind the `planner_key_threat` switch — every **KO-the-key-threat** snipe line (the Goal
        Ladder's middle rung, CONTEXT.md: the leaf scalar ranks across the two, prizes dominant).

        **`stabilize-then-KO` was the third generator and is DELETED** (POC-T4/5, Issue #386;
        Issue #263 § *Position in the ladder*). It was a hand-authored two-step maneuver — heal, then
        KO — and the composer scores a heal-then-attack SEQUENCE by construction: the heal is an
        ordinary MODELLED option and the attack leg is `attack_ev`. A hand-authored stand-in for what
        differencing computes generally is exactly what ADR-0092 retires, so the rule died rather
        than moving. Its corpus frames are composer acceptance cases."""
        if any(t.tactical >= KO_SCORE for t in traces):
            return []
        candidates = self._ko_for_prizes_lines(obs, select, board, options, traces)
        if self.planner_key_threat:
            candidates += self._ko_key_threat_lines(obs, select, board, options)
        return candidates

    def _deferral_value(self, traces) -> float:
        """What the turn is worth if the pool commits NOTHING — the tuned/greedy pick's own score.

        ADR-0074 decision 5 (#175) replaces `_commit_best`'s constant `< KO_SCORE` floor with this.
        The constant breaks under a weighted prize term: a 1-prize KO at p=0.87 scores 870 and would
        be vetoed outright, though an 87%-likely prize is plainly worth taking. Comparing against
        the real alternative needs no threshold — which is the rule ADR-0074 decision 1 sets.

        Measured commensurate before adoption (`tools/train/probes/rung_scale.py`, 72 firing frames
        over dragapult_ex + mega_lucario): the tuned top sits at 20-210 while pool values sit at
        1009-3035, cleanly separated, and the comparison vetoes nothing the constant floor did not.
        The pool is layer-on-top (it is empty whenever the tuned menu already reaches a KO), so
        `tactical` is never KO-class here and this really is the positional alternative.

        0.0 with no traces — an unreadable alternative never vetoes a line."""
        return max((getattr(t, "score", 0.0) or 0.0 for t in (traces or ())), default=0.0)

    def _commit_best(self, obs, candidates, *, traces=()) -> TurnLine | None:
        """The line to commit from the candidate pool: the closed-form best, floored.

        **The engine RANKING seam is DELETED** (POC-T4/5, Issue #386; Issue #263 § *Parity +
        retirement*, *"the runtime engine rollout … retire[s]"*). It forward-simmed every candidate
        to its end-of-turn board through `_engine_leaf_value` and ranked by that — one SAMPLE of a
        shuffle-riding sim, whose value provably swings across processes (ml f24: 7000 / 162 / 129 /
        89 / 57.5 for the same first step). Ranking end states is now the composer's job and it does
        it closed-form, so a second, sampled opinion about the same board is exactly the
        double-source ADR-0092 decision 4 forbids. Deleted with it: `_engine_rank` (the OFF path's
        value-sharpener), the `planner_engine_rank` kill-switch, and `TurnLine.ranked_by`'s
        ``"engine"`` value.

        The weighted-goal floor is unchanged and still the only veto here (ADR-0074 decision 5,
        Issue #175): a `_WEIGHTED_GOALS` line that is not worth more than the tuned alternative
        defers rather than commits."""
        if not candidates:
            return None
        best = max(candidates, key=lambda ln: ln.value)
        if best.goal in _WEIGHTED_GOALS and best.value <= self._deferral_value(traces):
            return None                                  # loses to the alternative — defer
        return best

    # ═══ THE COMPOSER RUNG (POC-T4/5, Issue #386) — the MAIN decider ══════════════════════════════
    # The bottom of the ladder and the widest rung on it. Every MAIN single-pick decision the rungs
    # above declined is composed as a within-turn SEQUENCE (`common.composer`), and the winning
    # sequence's FIRST action is committed. There is no flag and no fire-gate: the dark state lived
    # exactly one sub-issue (Issue #385), and a composer that only fires where a heuristic says
    # greedy is unsure would still leave the greedy argmax deciding — which is the thing this
    # replaces.
    #
    # **The swap IS the deletion.** The develop ROLLOUT rung stood here and is gone with its whole
    # apparatus (`_develop_rollout_line`, `_develop_should_fire`, `_develop_candidates_record`, the
    # `develop_rollout` flag, the `plan_candidates` telemetry, `_engine_leaf_value`, and
    # `_simulate_line`'s ``stream`` half of the Issue #178 machinery). So are the MAIN-phase rung
    # families the composer now prices by differencing — heal, the Tool equip band, gust
    # whether-to-play, the draw/dig economy, hand disruption, the Stadium deck rung and
    # `retreat-to-wall-the-line`. A rung asserting a preference the leaf can compute is a second
    # opinion about the same board, and the PR body lists every deleted id.

    def _composer_line(self, obs, select, board, options, traces) -> TurnLine | None:
        """The composer's committed first action as a ``goal="compose"`` Turn Line, or None.

        `common.composer.compose` beams over within-turn sequences, transitions them through
        `apply_option` and scores each end state as ``state_value(end board) + EV(terminal action)``
        (Issue #263 § *Terminal-action valuation*). The winning sequence's first action is what this
        decision commits; the rest of the sequence is NOT locked — the engine re-presents a menu after
        every action and `plan_turn`'s fingerprint cache re-plans on any reveal, so the beam is
        re-run rather than replayed. That is deliberate: a locked line is the win rung's mechanism
        and it is locked only because the engine VERIFIED it.

        **Three defers, and each is a refusal to guess rather than a gate:**

        * no `chosen` — the seam could price nothing on this menu, which is the honest answer at a
          select whose every option is a card effect (Issue #385's ``chosen is None`` report). The
          tuned scoring keeps the turn.
        * `chosen.coverage_gap` — the winning candidate exists only because something REFUSED, and
          *"a refusal is an unknown, not a zero"*. Committing an unknown because nothing scored
          above it is precisely the silent competition Issue #263 forbids.
        * no `first_index` — the empty stop-now line names no menu option, so there is nothing to
          commit.

        **The margin telemetry is emitted, not optional** (Issue #263 § *Beam-quality package*
        item 3): the chosen first step's 1-ply rank relative to *k* and its margin to the k-th
        candidate ride the Decision's sparse ``composer`` block, so a first step that barely survived
        the beam is visible in the live trace BEFORE it fails silently on an unseen board.

        ``search_api`` is threaded because `_search_api` is `fate()`'s ENGINE-RESOLVED route and
        Issue #263 § *Parity + retirement* preserves it by name. It is INERT until a caller also
        supplies a per-option determinism proof — `fate`'s gate is *provably* deterministic, and its
        `None` default refuses — so wiring it changes nothing today and is the seam being kept open
        rather than a route being opened.

        ``shed`` is NOT inert, and it is threaded because this method is the only caller that can.
        `compose` cannot reach a Pilot, so a costed search (Ultra Ball's *"discard 2 other cards"*)
        must be told WHICH cards the live decider would pay before its pool can be enumerated; left
        `None` the seam REFUSES it by name rather than pricing it unpaid. Unwired, that refusal was
        every Ultra Ball in the pool — the composer had no opinion about the deck's most-played
        Item, and `Pilot.cost_shed_indices` (public and model-shaped for exactly this call, see its
        docstring) sat unused. Found from `test_blunder_20260629`, whose composer `gaps` named the
        missing seam in as many words."""
        my_index = int((obs.get("current") or {}).get("yourIndex") or 0)
        try:
            model = self._leaf_state_model(obs, my_index)
            result = composer.compose(model, options,
                                      search_api=getattr(self, "_search_api", None),
                                      shed=self.cost_shed_indices)
        except Exception:
            return None                                  # a modelling slip never crashes the decision
        chosen = result.chosen
        self._composer_trace = {"margin": result.margin.working(), "stats": result.stats,
                                "gaps": list(result.gaps)[:_COMPOSER_GAP_K]}
        if chosen is None or chosen.first_index is None or chosen.coverage_gap:
            return None
        tied = _tied_first_steps(result, chosen)
        if tied:
            self._composer_trace["tied_first_steps"] = tied
            return None
        self._composer_trace["chosen"] = chosen.working()
        self._composer_trace["steps"] = [s.index for s in chosen.steps]
        # …and the committed index NAMED, because `steps` cannot carry it on a terminal line: an
        # attack or an End has no steps, so `steps` is `[]` and the block explained a pick it could
        # not identify. `first_index` is the one field a trace reader joins to `chosen` (ADR-0019
        # legibility — the record must never leave "top-score not chosen" looking like a bug).
        self._composer_trace["first_index"] = chosen.first_index
        return TurnLine(next_step=[chosen.first_index], goal="compose", value=chosen.score,
                        rationale="compose: the best within-turn sequence's first action",
                        ranked_by="composer", kind="sequence")

    # ═══ THE WIN RUNG — the Lethal Solver (ADR-0030/0037): sound, engine-verified, preempts all ═══
    # Everything in this section is SOUND by construction: min-bound damage floors, worst-case
    # coins, engine verdicts. It never trades against the heuristic rungs — a win, when locked,
    # owns the decision. A false Lethal is the one catastrophic error (a miss costs a turn; a
    # phantom loses the game), so soundness beats completeness throughout.

    # ═══ THE HEURISTIC RUNGS — rank-grade, never a guarantee (ADR-0031) ═══

    # ═══ THE GAMBLE RUNG — Tier-2 (ADR-0039): closed-form expectimax over Outcome Classes ═══
    # Deliberately probabilistic and BELOW every deterministic goal: it runs only when the win rung
    # and the whole heuristic pool passed. Exact probabilities (tracker-anchored hypergeometrics),
    # closed-form branch values, NO engine sim through the chance node (a fork is ONE predicted
    # determinization — untrusted for prediction-dependent outcomes). Depth-1 by construction.
