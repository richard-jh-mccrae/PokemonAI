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

# Leaf-eval term weights (ADR-0031 decision 4). Prizes are KO_SCORE-weighted and DOMINANT — sum of
# every positional term caps below one prize, so a positional score can never outrank a real KO
# (hard-rung invariant, decision 3). Seeded + tunable; Base Value Model (ADR-0007) replaces the
# whole scalar later.
_PLANNER_SURVIVAL_W = 50.0     # my Active survives predicted Incoming after the line (full turn)
_PLANNER_THREAT_W = 0.1        # per-point value of threat magnitude removed by the KO …
_PLANNER_THREAT_CAP = 100.0    # … capped, so a big threat still can't rival a prize
_PLANNER_DEV_W = 1.0           # dev toward win-condition (seeded; exercised from P3 on)


@dataclass
class TurnLine:
    """A committed sequence of this-turn actions achieving a **Turn Goal**: the option index(es) to
    take at THIS decision (``next_step``), the ``goal`` it serves (for legibility / telemetry
    clustering), the leaf-eval ``value`` of the resulting board, and a one-line ``rationale``. A
    multi-step line surfaces one step per decision as the engine re-opens the turn menu."""
    next_step: list
    goal: str = ""
    value: float = 0.0
    rationale: str = ""


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
        line = self._closed_form_plan(obs, select, board, options, traces)
        if line is not None:
            line = self._engine_rank(obs, line)       # Tier-1: sharpen value on exact end-of-turn board
        self._turn_plan = (fp, line)
        return line

    def _closed_form_plan(self, obs, select, board, options, traces) -> TurnLine | None:
        """The Goal-Ladder verdict from closed-form generation (no engine), highest rung first.

        **Stabilize-then-KO** is checked FIRST because it is the one goal that fires EVEN when a
        status-quo KO exists — it combines the heal + KO the greedy scorer treats as mutually exclusive.
        Below it, **KO-for-prizes** is strictly layer-on-top: it stands down when the tuned machinery
        already reaches a KO (any option scored KO_SCORE-class), supplying only a KO otherwise MISSED."""
        stabilize = self._stabilize_then_ko_line(obs, select, board, options, traces)
        if stabilize is not None:
            return stabilize
        if any(t.tactical >= KO_SCORE for t in traces):
            return None
        return self._ko_for_prizes_line(obs, select, board, options, traces)

    def _stabilize_then_ko_line(self, obs, select, board, options, traces) -> TurnLine | None:
        """The **stabilize-then-KO** goal (ADR-0031): when my Active is DOOMED yet can also KO this turn,
        a clutch-heal (Wally's Compassion — heal a Mega ex to FULL, then bounce all its Energy to hand)
        played FIRST lets me heal AND still take the KO (re-attach one Energy, then the cheapest KO
        attack). It combines the heal + KO goals the greedy scorer can't: its `active_can_ko` suppressor
        drops the heal whenever a KO is available — the exact trap that caused 0cbc (`heal-and-stall` and
        `heal-and-KO` conflated). Fires ONLY when healing genuinely stabilises (full HP beats the
        **Incoming**) AND the KO survives the Energy bounce (a re-attach still affords it), so it never
        heals-and-stalls and never forfeits the prize. A winning KO is owned by the Lethal Solver upstream,
        so this only ever combines a heal with a NON-winning KO."""
        if not board.active_doomed:
            return None
        if not any(o.get("type") == _ATTACK and t.tactical >= KO_SCORE
                   for o, t in zip(options, traces)):
            return None                               # no KO on menu -> nothing to preserve; defer to hold-clutch-heal
        opp = self._opp_active(obs)
        active_stat = (self.stats.get(board.my_active_id)
                       if (self.stats and board.my_active_id is not None) else None)
        if not (opp and active_stat):
            return None
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
            return TurnLine(next_step=[i], goal="stabilize_then_ko", value=value,
                            rationale="plan (stabilize_then_ko): heal, re-power, still KO for the prize")
        return None

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

    def _ko_for_prizes_line(self, obs, select, board, options, traces) -> TurnLine | None:
        """The **KO-for-prizes** goal (ADR-0031 phase 1-2): a multi-step enabling line that unlocks an
        otherwise-missed KO of the opponent's Active, ranked by the leaf-eval scalar (prizes dominant +
        my Active's survival vs Incoming + the threat removed). Generates one candidate per enabling
        first-step (retreat into a benched attacker; evolve the Active), each regressed to "does this
        body, after the step PLUS this turn's one attach, KO?" and evaluated at its end-of-turn board.
        Commits the highest-leaf-value line's first step. None when no such line exists."""
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp"):
            return None
        opp_player = self._opp_player(obs)
        extra = 1 if (board.reusable_energy_in_hand and not board.energy_attached) else 0
        threat = self._threat_magnitude(opp)
        best = None                                   # (value, prizes, index, kind)
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
            if best is None or value > best[0]:
                best = (value, prizes, i, kind)
        if best is None:
            return None
        value, prizes, idx, kind = best
        return TurnLine(next_step=[idx], goal="ko_for_prizes", value=value,
                        rationale=f"plan (ko_for_prizes): {kind} unlocks a {int(prizes)}-prize KO")

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
        the threat removed + my Active's survival vs Incoming + development toward the win-condition.
        The positional terms sum to less than one prize, so a bigger KO always ranks first — a
        positional score can NEVER outrank a real prize (the hard-rung invariant, ADR-0031 decision 3).
        Hand-weighted + tunable; the Base Value Model (ADR-0007) is the drop-in replacement later."""
        return (KO_SCORE * prizes
                + min(_PLANNER_THREAT_CAP, _PLANNER_THREAT_W * threat_removed)
                + (_PLANNER_SURVIVAL_W if active_survives else 0.0)
                + _PLANNER_DEV_W * development)

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
        return self._leaf_value(prizes=prizes_taken, active_survives=survives)

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
