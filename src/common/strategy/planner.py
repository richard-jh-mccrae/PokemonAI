"""The Turn Planner (ADR-0031): the eager whole-turn optimizer, generalizing the Lethal Solver from
the *win* goal to a **Goal Ladder**.

A deck-agnostic Pilot Mixin that runs at the start of my turn, AFTER the sound
:class:`~common.strategy.lethal.LethalMixin` (win is the hard top rung, taken there unchanged) and
BEFORE the tuned Hypothesis scoring. It works backward from a closed, prioritized set of **Turn
Goals** to generate a few candidate **Turn Lines**, and commits the best — steering this decision
toward that line's next step. See ``docs/adr/0031-turn-planner-is-goal-directed-engine-simulated-
tier1-search.md`` and the *Turn Planner* / *Turn Goal* / *Turn Line* terms in ``common/CONTEXT.md``.

**Layer-on-top (ADR-0031 decision 6).** The Planner commits only when a line reaches an outcome the
tuned per-option scoring would MISS — otherwise it defers, so the proven default is unchanged. The
first goal built is **KO-for-prizes**: a multi-step enabling line (retreat into a benched attacker, or
evolve the Active, then this turn's one attach) that unlocks a KO the greedy scorer can't see because
no single option scores it. Higher rungs (KO the key threat, stabilise-then-KO), engine-simulated
ranking, and the turn-scoped committed-line cache arrive in later phases.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from common.strategy.context import _ACTIVE, _ATTACK, _EVOLVE, _MAIN, _PLAY, _RETREAT, KO_SCORE


def _prune_none(v):
    """Convert an ``asdict``-ed engine Observation into the dict shape the LIVE obs has, so the Pilot's
    ``decide`` can be re-run on an intermediate SearchState. ``asdict`` keeps optional dataclass fields
    as ``None`` keys (e.g. ``option.playerIndex``), but the engine's live JSON OMITS them — the
    difference matters for ``option.get("playerIndex", yourIndex)``-style lookups, which otherwise read
    ``None`` and crash. Drops None-VALUED dict keys; KEEPS None list ELEMENTS (a facedown Active / a
    facedown prize slot is a meaningful ``None`` that carries the zone's count)."""
    if isinstance(v, dict):
        return {k: _prune_none(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [_prune_none(x) for x in v]
    return v

# Leaf-eval term weights (ADR-0031 decision 4). Prizes KO_SCORE-weighted + DOMINANT — positional terms
# sum below one prize, never outrank real KO (hard-rung invariant, decision 3). Base Value Model (ADR-0007) replaces later.
_PLANNER_SURVIVAL_W = 50.0     # my Active survives predicted Incoming after the line (full turn)
_PLANNER_THREAT_W = 0.1        # per-point value of threat magnitude removed by the KO …
_PLANNER_THREAT_CAP = 100.0    # … capped, so a big threat still can't rival a prize
_PLANNER_DEV_W = 1.0           # development left on my end-of-turn board (engine-rank phase: bodies
_PLANNER_DEV_CAP = 100.0       # + attached Energy, `_board_development`) … capped below a prize


@dataclass
class TurnLine:
    """A committed sequence of this-turn actions achieving a **Turn Goal**: the option index(es) to
    take at THIS decision (``next_step``), the ``goal`` it serves (for legibility / telemetry
    clustering), the leaf-eval ``value`` of the resulting board, and a one-line ``rationale``. A
    multi-step line surfaces one step per decision as the engine re-opens the turn menu.
    ``ranked_by`` records how the committed line was VALUED when multi-candidate engine ranking ran
    (`planner_engine_rank`): "engine" = its own sim's leaf value; "closed" = the closed-form value
    (its sim was unavailable); None = ranking never ran (switch off / engine absent / mid-sim).
    ``diverged`` = the ranking committed a DIFFERENT line than the closed form would have — the A/B
    divergence signal."""
    next_step: list
    goal: str = ""
    value: float = 0.0
    rationale: str = ""
    ranked_by: str | None = None
    diverged: bool = False


class PlannerMixin:
    """Pilot-side Turn Planner. ``plan_turn`` returns a :class:`TurnLine` to commit, or None to defer
    to the tuned scoring. Depends on Pilot internals (``_opp_active``, ``_best_affordable_ko_value``,
    ``_prize_value``, the per-option ``OptionTrace``), so it is mixed into the Pilot."""

    def plan_turn(self, obs, select, board, options, traces) -> TurnLine | None:
        """The best committed Turn Line this turn, or None. Only acts at the single-pick MAIN menu;
        every other context (search, snipe, mulligan, multi-select) defers to the tuned scoring.

        Plan once, cache, re-plan on reveal (ADR-0031 decision 5): the verdict is cached as turn-scoped
        state keyed by a board fingerprint, so the (engine-ranked) plan is computed once per board and
        re-derived only when a search/draw reveals information that changes the fingerprint. While an
        engine sim is re-running my policy (``_planning``), it stays closed-form and uncached so it never
        launches a nested search."""
        if select.get("context") != _MAIN or select.get("maxCount", 0) != 1:
            return None
        if self._planning:                            # mid engine-sim: closed-form only, never nest search
            return self._closed_form_plan(obs, select, board, options, traces)
        fp = self._plan_fingerprint(obs, select)
        if self._turn_plan is not None and self._turn_plan[0] == fp:
            return self._turn_plan[1]                 # cache hit: re-plan only on reveal (fingerprint change)
        candidates = self._closed_form_candidates(obs, select, board, options, traces)
        line = self._commit_best(obs, candidates)
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

        **Stabilize-then-KO** rules the pool alone when it fires — it is the one goal alive EVEN when
        a status-quo KO exists (it combines the heal + KO the greedy scorer treats as mutually
        exclusive), and mixing lower rungs under it would trade the heal away. Below it, the pool is
        strictly layer-on-top: it empties when the tuned machinery already reaches a KO (any option
        scored KO_SCORE-class), else it holds every **KO-for-prizes** enabling line plus — behind the
        `planner_key_threat` switch — every **KO-the-key-threat** snipe line (the Goal Ladder's middle
        rung, CONTEXT.md: the leaf scalar ranks across the two, prizes dominant)."""
        stabilize = self._stabilize_then_ko_lines(obs, select, board, options, traces)
        if stabilize:
            return stabilize
        if any(t.tactical >= KO_SCORE for t in traces):
            return []
        candidates = self._ko_for_prizes_lines(obs, select, board, options, traces)
        if self.planner_key_threat:
            candidates += self._ko_key_threat_lines(obs, select, board, options)
        return candidates

    def _commit_best(self, obs, candidates) -> TurnLine | None:
        """The line to commit from the candidate pool — the multi-candidate ENGINE RANKING seam
        (ADR-0031 P3 completed; `planner_engine_rank`).

        OFF (default) or engine absent: the closed-form best, its value engine-SHARPENED when
        available (the original behavior, byte-identical). ON: every candidate is forward-simmed to
        its end-of-turn board and ranked by the ENGINE leaf value — a candidate whose sim is
        unavailable keeps its closed-form value (same scale, decision 7: never lose a line to a
        failed fork). If even the best ranked value collapses below one prize, the pool's premise
        failed in sim — defer to the tuned scoring (the natural veto: the sim is trusted for ranking,
        and an all-candidates refute means there is nothing left to rank). ``diverged`` records a
        pick the closed form would not have made."""
        if not candidates:
            return None
        closed_best = max(candidates, key=lambda ln: ln.value)
        if not self.planner_engine_rank:
            return self._engine_rank(obs, closed_best)   # status quo: sharpen the committed value only
        ranked = []
        for cand in candidates:
            self._planning = True                        # per-sim reentrancy guard (never nest a search)
            try:
                val = self._engine_leaf_value(obs, cand.next_step)
            finally:
                self._planning = False
            ranked.append((val if val is not None else cand.value, val is not None, cand))
        best_val, engine_valued, best = max(ranked, key=lambda t: t[0])
        if best_val < KO_SCORE:
            return None                                  # every candidate's prize premise failed in sim
        return replace(best, value=best_val,
                       ranked_by=("engine" if engine_valued else "closed"),
                       diverged=(best is not closed_best))

    def _stabilize_then_ko_lines(self, obs, select, board, options, traces) -> list:
        """The **stabilize-then-KO** goal (ADR-0031): when my Active is DOOMED yet can also KO this turn,
        a clutch-heal (Wally's Compassion — heal a Mega ex to FULL, then bounce all its Energy to hand)
        played FIRST lets me heal AND still take the KO (re-attach one Energy, then the cheapest KO
        attack). It combines the heal + KO goals the greedy scorer can't: its `active_can_ko` suppressor
        drops the heal whenever a KO is available — the exact trap that caused 0cbc (`heal-and-stall` and
        `heal-and-KO` conflated). A candidate fires ONLY when healing genuinely stabilises (full HP beats
        the **Incoming**) AND the KO survives the Energy bounce (a re-attach still affords it), so it never
        heals-and-stalls and never forfeits the prize. A winning KO is owned by the Lethal Solver upstream,
        so this only ever combines a heal with a NON-winning KO. Every valid heal option is a candidate
        (they were all `return`-first before multi-candidate ranking; ties still break to the first)."""
        if not board.active_doomed:
            return []
        if not any(o.get("type") == _ATTACK and t.tactical >= KO_SCORE
                   for o, t in zip(options, traces)):
            return []                                 # no KO on menu -> nothing to preserve; defer to hold-clutch-heal
        opp = self._opp_active(obs)
        active_stat = (self.stats.get(board.my_active_id)
                       if (self.stats and board.my_active_id is not None) else None)
        if not (opp and active_stat):
            return []
        lines = []
        for i, o in enumerate(options):
            if o.get("type") != _PLAY:
                continue
            cid = self._option_card_id(obs, select, o)
            if cid is None:
                continue
            cand = self._heal_candidate(cid, board, active_stat)
            if cand is None:
                continue
            healed_hp, energy_total = cand
            if healed_hp <= board.incoming_active_damage:
                continue                              # heal can't outlast the Incoming
            if self._best_affordable_ko_value(obs, board, opp, board.my_active_id, energy_total) <= 0:
                continue                              # heal's Energy cost would forfeit the KO
            value = self._leaf_value(prizes=self._prize_value(opp), active_survives=True,
                                     threat_removed=self._threat_magnitude(opp))
            lines.append(TurnLine(next_step=[i], goal="stabilize_then_ko", value=value,
                                  rationale="plan (stabilize_then_ko): heal, re-power, still KO for the prize"))
        return lines

    def _condition_holds(self, condition, board) -> bool:
        """Evaluate a clause's dynamic ``condition`` gate against the Board — TRUE only when the
        gate is absent or PROVABLY satisfied right now. The two board-checkable gates (Bianca's
        remaining-HP, Jumbo Ice Cream's attached-Energy) are evaluated; any other condition string
        fails closed (never plan on an amount that might not materialise)."""
        if not condition:
            return True
        if condition == "remaining_hp_30_or_less":
            return bool(board.my_active_hp) and board.my_active_hp <= 30
        if condition == "energy_3_plus":
            return board.my_active_energy >= 3
        return False

    def _heal_candidate(self, cid: int, board, active_stat) -> tuple[int, int] | None:
        """What playing heal-card ``cid`` on my Active would leave: ``(healed_hp, energy_total)``
        — the post-heal HP and the total Energy the Active can still pay an attack with this turn
        (attached after the card's rider, plus the manual attach if unused). Two sources, clause
        first (ADR-0032 4b): an Effect Clause (`kind: heal` with the measured ``amount`` and its
        ``rider``/``restriction``) generalizes the tag path; the `clutch_heal` Function Tag stays
        as the fallback (full heal + bounce — Wally's) for a clause-blind Pilot. None when ``cid``
        heals nothing, a restriction excludes my Active (``mega_only`` on a non-Mega), or the
        clause carries a ``condition`` the closed form can't evaluate (fail-closed: don't plan on
        an amount that might not materialise)."""
        max_hp = getattr(active_stat, "hp", 0) or 0
        attach = 0 if board.energy_attached else 1
        for clause in (self.effects.clauses(cid) if self.effects else ()):
            if clause.get("kind") != "heal":
                continue
            if not self._condition_holds(clause.get("condition"), board):
                continue                              # gate fails / not board-checkable: fail-closed
            restriction = clause.get("restriction")
            if restriction == "mega_only" and not getattr(active_stat, "megaEx", False):
                continue
            amount = clause.get("amount")
            healed = max_hp if amount == "all" else min(max_hp, board.my_active_hp + int(amount or 0))
            rider = clause.get("rider")
            if rider == "bounce_energy_to_hand":
                energy_total = attach                 # all Energy bounced; only re-attach pays
            elif rider == "discard_own_energy":
                energy_total = max(0, board.my_active_energy - 1) + attach
            else:
                energy_total = board.my_active_energy + attach
            return (healed, energy_total)
        if self.functions and "clutch_heal" in self.functions.tags(cid):
            return (max_hp, attach)                   # legacy tag path: full heal + Energy bounce
        return None

    def _engine_rank(self, obs, line: TurnLine) -> TurnLine:
        """Refine a committed line's leaf VALUE with the Tier-1 engine sim (ADR-0031 phase 3) — the exact
        end-of-turn board rather than the closed-form approximation — when the engine is available. The
        closed-form gate already CHOSE the line (a KO the greedy scorer misses), so the choice is
        unchanged; the sim sharpens ``value`` for telemetry and future multi-candidate ranking. Guards
        against reentrancy and falls back to the closed-form value when the engine is absent (unit path)
        or the sim errors — never crashes (decision 7)."""
        if self._planning or not (obs or {}).get("search_begin_input"):
            return line
        self._planning = True
        try:
            val = self._engine_leaf_value(obs, line.next_step)
        finally:
            self._planning = False
        return replace(line, value=val) if val is not None else line

    def _plan_fingerprint(self, obs, select) -> tuple:
        """A hashable/comparable snapshot of everything a plan depends on — the turn, both boards
        (id / energy / HP per Pokémon), my hand, my prize count, the manual-attach flag, and the option
        signature. Any reveal (a draw, a search, a KO, a new turn) changes it, so the cache re-plans; an
        unchanged board reuses the committed line."""
        cur = obs.get("current") or {}
        me, opp = self._my_player(obs), self._opp_player(obs)

        def body(p):
            return (p.get("id"), len(p.get("energies") or []), p.get("hp")) if p else None

        def side(pl):
            return (tuple(body(x) for x in (pl.get("active") or [])),
                    tuple(body(x) for x in (pl.get("bench") or [])))

        hand = tuple(sorted(c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None))
        opts = tuple((o.get("type"), o.get("attackId"), o.get("area"), o.get("index"),
                      o.get("inPlayArea"), o.get("inPlayIndex")) for o in (select.get("option") or []))
        return (cur.get("turn"), side(me), side(opp), hand, len(me.get("prize") or []),
                bool(cur.get("energyAttached")), opts)

    def _ko_for_prizes_lines(self, obs, select, board, options, traces) -> list:
        """The **KO-for-prizes** goal (ADR-0031 phase 1-2): multi-step enabling lines that unlock an
        otherwise-missed KO of the opponent's Active, each valued by the leaf-eval scalar (prizes
        dominant + my Active's survival vs Incoming + the threat removed). One candidate per enabling
        first-step (retreat into a benched attacker; evolve the Active; play an energy-tutor
        Supporter), each regressed to "does this body, after the step PLUS this turn's one attach,
        KO?" and evaluated at its end-of-turn board. Empty when no such line exists."""
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp"):
            return []
        opp_player = self._opp_player(obs)
        extra = 1 if (board.reusable_energy_in_hand and not board.energy_attached) else 0
        threat = self._threat_magnitude(opp)
        lines = []
        for i, o in enumerate(options):
            if o.get("type") == _RETREAT:
                cand = self._retreat_ko_candidate(obs, board, opp, opp_player, extra)
                kind = "retreat"
            elif o.get("type") == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                cand = self._evolve_ko_candidate(obs, select, board, o, opp, opp_player, extra)
                kind = "evolve"
            elif o.get("type") == _PLAY:
                cand = self._supporter_ko_candidate(obs, select, board, o, opp, opp_player)
                kind = "energy tutor"
            else:
                continue
            if cand is None:
                continue
            prizes, survives = cand
            value = self._leaf_value(prizes=prizes, active_survives=survives, threat_removed=threat)
            lines.append(TurnLine(next_step=[i], goal="ko_for_prizes", value=value,
                                  rationale=f"plan (ko_for_prizes): {kind} unlocks a {int(prizes)}-prize KO"))
        return lines

    def _ko_key_threat_lines(self, obs, select, board, options) -> list:
        """The **KO-the-key-threat** goal (the Goal Ladder's middle rung, CONTEXT.md *Turn Goal*;
        `planner_key_threat`): ENABLING lines that unlock a bench-snipe KO of the opponent's benched
        TOP-threat body — the greatest shared threat rank (`_body_threat_rank`: eventual attack
        power, forward evolution, energized/hand-size boosts). A snipe-KO already ON the menu needs
        no rung (the Tactical layer credits its prize KO_SCORE-class), but no closed-form hook scores
        the STEP that reaches one — `_retreat_to_lethal_tactical` and the KO-for-prizes generators
        test KOs of the ACTIVE only — so a retreat into the sniper, an evolve that brings the snipe
        attack online, or the energy tutor that powers it is invisible to the greedy scorer and the
        biggest future attacker survives. Bench snipes ignore W/R so ``rider >= hp`` is the exact KO
        test (`_snipe_ko_prizes`'s rule), and a Tera body is snipe-immune. Candidates join the
        KO-for-prizes pool: the leaf scalar ranks across the rungs (prizes dominant, then the removed
        threat's magnitude)."""
        opp_player = self._opp_player(obs)
        bench = [p for p in (opp_player.get("bench") or []) if p]
        if not bench:
            return []
        ranked = [(self._body_threat_rank(obs, p, board.read, board.posture_confidence), p)
                  for p in bench]
        top_rank, top = max(ranked, key=lambda t: t[0])
        top_stat = self.stats.get(top.get("id")) if self.stats else None
        threat_mag = float(getattr(top_stat, "maxDamage", 0) or 0) if top_stat else 0.0
        hp = top.get("hp", 0)
        if top_rank <= 0 or threat_mag <= 0 or not hp or self._is_tera(top.get("id")):
            return []                                 # nothing benched actually threatens (or Tera-immune)
        me = self._my_player(obs)
        opp = self._opp_active(obs)
        others = [p for p in ([opp] + [p for p in bench if p is not top]) if p]
        extra = 1 if (board.reusable_energy_in_hand and not board.energy_attached) else 0
        prizes = self._prize_value(top)
        lines = []
        for i, o in enumerate(options):
            if o.get("type") == _RETREAT:
                cand = self._retreat_snipe_candidate(me, others, hp, extra)
                kind = "retreat"
            elif o.get("type") == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                evolved_id = self._option_card_id(obs, select, o)
                if not self._affords_snipe_ko(evolved_id, board.my_active_energy + extra, hp):
                    continue
                estat = self.stats.get(evolved_id) if self.stats else None
                my_hp = getattr(estat, "hp", 0) or 0
                cand = (bool(my_hp) and self._incoming_worst(evolved_id, my_hp, others) < my_hp)
                kind = "evolve"
            elif o.get("type") == _PLAY:
                if (board.energy_attached or board.reusable_energy_in_hand
                        or not self._is_energy_tutor(obs, select, o)):
                    continue                          # mirrors `_supporter_ko_candidate`'s gate
                cand = self._retreat_snipe_candidate(me, others, hp, extra=1)
                kind = "energy tutor"
            else:
                continue
            if cand is None:
                continue
            value = self._leaf_value(prizes=prizes, active_survives=bool(cand),
                                     threat_removed=threat_mag)
            lines.append(TurnLine(
                next_step=[i], goal="ko_key_threat", value=value,
                rationale=f"plan (ko_key_threat): {kind} unlocks the snipe-KO of the benched key threat"))
        return lines

    def _retreat_snipe_candidate(self, me, others, target_hp: int, extra: int):
        """``active_survives`` (bool) for the best benched body that, once retreated INTO (its Energy
        plus this turn's one attach), affords an attack whose bench-snipe rider KOs the ``target_hp``
        key threat — or None when no benched body reaches one. Among the capable bodies it prefers
        the one that SURVIVES the opponent's remaining Incoming (the sniped threat excluded)."""
        best = None
        for p in (me.get("bench") or []):
            if not p:
                continue
            if not self._affords_snipe_ko(p.get("id"), len(p.get("energies") or []) + extra, target_hp):
                continue
            my_hp = p.get("hp", 0)
            survives = bool(my_hp) and self._incoming_worst(p.get("id"), my_hp, others) < my_hp
            if best is None or survives > best:
                best = survives
        return best

    def _affords_snipe_ko(self, body_id, energy: int, target_hp: int) -> bool:
        """True iff ``body_id`` carrying ``energy`` can pay an attack whose unconditional bench-snipe
        rider (`_rider_snipe`) reaches ``target_hp`` — the exact snipe-KO test (no W/R on the Bench)."""
        stat = self.stats.get(body_id) if (self.stats and body_id is not None) else None
        if not (stat and target_hp):
            return False
        return any(self.attack_costs.get(aid, 99) <= energy and self._rider_snipe(aid) >= target_hp
                   for aid in (stat.attacks or ()))

    def _is_energy_tutor(self, obs, select, option) -> bool:
        """This PLAY option is a `tutor_energy` Trainer (Hilda class) — it searches an attachable
        Energy into hand, supplying the attach an enabling line lacks (the 4298 shape)."""
        cid = self._option_card_id(obs, select, option)
        return bool(cid is not None and self.functions and "tutor_energy" in self.functions.tags(cid))

    def _retreat_ko_candidate(self, obs, board, opp, opp_player, extra: int):
        """``(prizes, active_survives)`` for the best benched body that KOs the opponent's Active AFTER a
        retreat plus this turn's one attach — but that does NOT already KO at its current Energy (that
        single-step case is the existing ``_retreat_to_lethal_tactical`` hook's job). Among the KO-capable
        bodies (all take the same prize off the shared target) it prefers the one that SURVIVES the
        opponent's post-KO Incoming. None when no benched body needs the attach to reach a KO. Reuses the
        shared sound KO valuation (``_best_affordable_ko_value``: Weakness/Resistance, ex-immunity)."""
        me = self._my_player(obs)
        best = None                                   # (prizes, survives)
        for p in (me.get("bench") or []):
            if not p:
                continue
            energy = len(p.get("energies") or [])
            if self._best_affordable_ko_value(obs, board, opp, p.get("id"), energy) > 0:
                continue                              # retreat alone already KOs — existing hook owns it
            if not (extra and self._best_affordable_ko_value(obs, board, opp, p.get("id"), energy + extra) > 0):
                continue
            cand = (self._prize_value(opp), self._survives_after_ko(p.get("id"), p.get("hp", 0), opp_player))
            if best is None or cand > best:           # prefer more prizes, then survival (bool > bool)
                best = cand
        return best

    def _supporter_ko_candidate(self, obs, select, board, option, opp, opp_player):
        """``(prizes, active_survives)`` if playing a **tutor-energy Supporter** (Hilda: search an Energy
        into hand — the ``tutor_energy`` tag) unlocks an otherwise-missed retreat→attach→KO. The Supporter
        SUPPLIES the attachable Energy the plain retreat line lacks: with that fetched Energy modelled as
        this turn's one attach, a benched body KOs the opponent's Active after a retreat. The enabling
        first step here is the Supporter, not a retreat/evolve — no closed-form hook scores it, so it is
        net-new (corpus 4298). Fires ONLY when no reusable Energy is already in hand (else the plain
        retreat line covers it) AND the turn's one attach is still available (else the fetched Energy can't
        power the KO this turn). None otherwise. Reuses the sound retreat-KO valuation."""
        if board.energy_attached or board.reusable_energy_in_hand:
            return None
        cid = self._option_card_id(obs, select, option)
        if cid is None or not (self.functions and "tutor_energy" in self.functions.tags(cid)):
            return None
        return self._retreat_ko_candidate(obs, board, opp, opp_player, extra=1)

    def _evolve_ko_candidate(self, obs, select, board, option, opp, opp_player, extra: int):
        """``(prizes, active_survives)`` if EVOLVING the Active unlocks a KO of the opponent's Active this
        turn — the evolved form (the option's in-hand card) inherits the Active's Energy and, with this
        turn's one attach, its best affordable attack KOs. Evolving then attacking is legal the same turn
        (rules.md §evolution). No closed-form hook scores an evolve-unlock, so this is always net-new.
        Survival uses the evolved form's HP (closed-form approximation; the P3 engine-sim is exact).
        None when evolving doesn't reach a KO."""
        evolved_id = self._option_card_id(obs, select, option)
        if evolved_id is None:
            return None
        energy = board.my_active_energy
        if self._best_affordable_ko_value(obs, board, opp, evolved_id, energy + extra) <= 0:
            return None
        estat = self.stats.get(evolved_id) if self.stats else None
        my_hp = getattr(estat, "hp", 0) or 0          # evolved max HP — P3 engine-sim resolves damage exactly
        return (self._prize_value(opp), self._survives_after_ko(evolved_id, my_hp, opp_player))

    # ---- leaf evaluation (ADR-0031 decision 4): scalar over the resulting end-of-turn board ---------
    def _leaf_value(self, *, prizes: float, active_survives: bool, threat_removed: float = 0.0,
                    development: float = 0.0) -> float:
        """The leaf-eval scalar over a resulting board: prizes taken (dominant, KO_SCORE-weighted) +
        the threat removed + my Active's survival vs Incoming + the development left on my board
        (engine-rank phase input, `_board_development`; 0 for closed-form candidates). EVERY
        positional term is capped, and their capped sum stays below one prize, so a bigger KO always
        ranks first — a positional score can NEVER outrank a real prize (the hard-rung invariant,
        ADR-0031 decision 3). Hand-weighted + tunable; the Base Value Model (ADR-0007) is the drop-in
        replacement later."""
        return (KO_SCORE * prizes
                + min(_PLANNER_THREAT_CAP, _PLANNER_THREAT_W * threat_removed)
                + (_PLANNER_SURVIVAL_W if active_survives else 0.0)
                + min(_PLANNER_DEV_CAP, _PLANNER_DEV_W * development))

    def _survives_after_ko(self, my_id, my_hp, opp_player) -> bool:
        """True if my body (``my_id`` at ``my_hp``) survives the opponent's Incoming AFTER I KO their
        Active this turn — their best affordable REMAINING attacker (a benched body they promote) can't
        KO it. The 1-ply survival term for the leaf-eval (ADR-0031 decision 2); the opponent's Active is
        excluded because the line Knocks it Out. False when my HP is unknown."""
        bench = (opp_player or {}).get("bench") or []
        return bool(my_hp) and self._incoming_worst(my_id, my_hp, bench) < my_hp

    def _incoming_worst(self, my_id, my_hp: int, opp_bodies) -> int:
        """The worst Weakness/Resistance-adjusted damage the opponent's affordable attackers among
        ``opp_bodies`` could deal to my body next turn — the closed-form **Incoming** (CONTEXT.md): the
        hardest-hitting body whose Energy plus one attach affords an attack, their predicted next
        promotion. An upper-bound estimate (counts each body's biggest attack once it can afford its
        cheapest), so a survival check is conservative. 0 when unknown."""
        my_stat = self.stats.get(my_id) if (self.stats and my_id is not None) else None
        if not (my_stat and my_hp):
            return 0
        worst = 0
        for p in opp_bodies:
            if not p:
                continue
            pstat = self.stats.get(p.get("id")) if self.stats else None
            if not pstat:
                continue
            energy = len(p.get("energies") or []) + 1          # allow one attach next turn
            if (pstat.minAttackCost or 99) <= energy:
                worst = max(worst, int(self._predicted_max_damage(pstat, {"id": my_id})))
        return worst

    def _threat_magnitude(self, opp) -> float:
        """The threat magnitude of the opponent's Active — its biggest printed attack — as the
        ``threat_removed`` term when a line KOs it. A coarse "how dangerous was the body I removed"
        signal; 0 when unknown."""
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

    # ---- Tier-1 Engine Search (ADR-0031 phase 3): simulate a line to its end-of-turn board -----------
    def _engine_leaf_value(self, obs, first_step) -> float | None:
        """The leaf-eval value of a candidate line computed on its ENGINE-SIMULATED end-of-turn board
        (ADR-0031 phase 3): the exact prizes taken and my Active's survival vs Incoming, read off the
        board the simulator produces rather than closed-form-approximated. A line that finishes the game
        in my favour scores above any prize count (dominant). None when the search is unavailable — the
        caller then keeps the closed-form leaf value (never crashes, decision 7)."""
        sim = self._simulate_line(obs, first_step)
        if sim is None:
            return None
        end, my_index, start_prizes, result = sim
        players = (end.get("current") or {}).get("players") or []
        me = players[my_index] if 0 <= my_index < len(players) and players[my_index] else {}
        opp = players[1 - my_index] if 0 <= 1 - my_index < len(players) and players[1 - my_index] else {}
        if result == my_index:                            # line wins outright — dominant
            return KO_SCORE * (start_prizes + 1)
        prizes_taken = max(0, start_prizes - len(me.get("prize") or []))
        active = next((p for p in (me.get("active") or []) if p), None)
        survives = False
        if active and active.get("hp"):
            bodies = (opp.get("active") or []) + (opp.get("bench") or [])
            survives = self._incoming_worst(active.get("id"), active.get("hp", 0), bodies) < active.get("hp", 0)
        return self._leaf_value(prizes=prizes_taken, active_survives=survives,
                                development=self._board_development(me))

    @staticmethod
    def _board_development(me: dict) -> float:
        """The development left on MY simmed end-of-turn board — the `_PLANNER_DEV_W` term's input
        (ADR-0031 decision 4, exercised from the engine-rank phase): bodies in play plus the Energy
        attached to them. A coarse, engine-readable progress measure that splits prize-equal lines
        toward the one that leaves the stronger board (e.g. a line that spent nothing over one that
        stripped the Bench); `_leaf_value` caps its contribution below a prize."""
        bodies = [p for p in ((me.get("active") or []) + (me.get("bench") or [])) if p]
        return 10.0 * len(bodies) + 5.0 * sum(len(p.get("energies") or []) for p in bodies)

    def _simulate_line(self, obs, first_step, max_steps: int = 40):
        """Forward-simulate a candidate line through the Engine Search to my end-of-turn board (the
        Tier-1 seam). Steps ``first_step``, then re-runs my own closed-form policy (``decide``) on each
        intermediate SearchState until my turn ends (the select passes to the opponent) or the game
        finishes — the ADR-0031 "re-running the policy on each intermediate SearchState." Returns
        ``(end_obs_dict, my_index, start_prizes, result)`` or **None** when the search is unavailable,
        the observation carries no ``search_begin_input``, or anything errors (the caller falls back to
        the closed-form value — never crashes).

        Heuristic, not sound (ADR-0031): coins auto-resolve (``manual_coin=False``) and the opponent's
        hidden zones are predicted from my own deck list, so the end-of-turn board is trusted for
        ranking, not as a guarantee. The live game is untouched (the search forks an independent sim).
        Lazy DLL import keeps the fast unit suite from ever loading the native engine."""
        if not (obs or {}).get("search_begin_input") or not first_step:
            return None
        try:
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
        deck = list(self.deck)

        def take(n):
            return deck[: max(0, n)]

        try:
            ob = cgapi.to_observation_class(obs)
            st = cgapi.search_begin(ob, take(me.get("deckCount", 0)), take(start_prizes),
                                    take(opp.get("deckCount", 0)), take(len(opp.get("prize") or [])),
                                    take(opp.get("handCount", 0)), [], manual_coin=False)
            st = cgapi.search_step(st.searchId, list(first_step))
            for _ in range(max_steps):
                o = st.observation
                c = o.current
                if c is None or c.result != -1 or o.select is None or c.yourIndex != my_index:
                    break                                 # game over, or my turn ended
                st = cgapi.search_step(st.searchId, list(self.decide(_prune_none(asdict(o)))))
            end = _prune_none(asdict(st.observation))
            result = st.observation.current.result if st.observation.current else -1
            cgapi.search_end()
            return (end, my_index, start_prizes, result)
        except Exception:
            try:
                cgapi.search_end()
            except Exception:
                pass
            return None
