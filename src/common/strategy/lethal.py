"""The Lethal Solver (ADR-0030): the eager, sound, this-turn win-detector.

A deck-agnostic **core-Tactical** Mixin (NOT a card doctrine): at the start of my turn it works
backward from prizes to find a GUARANTEED win THIS turn and, if one exists, LOCKS the line so the
Pilot takes exactly its steps. **Sound by construction** — it never locks a false Lethal (a miss
costs a turn; a phantom loses the game). See ``docs/adr/0030-winning-this-turn-is-an-eager-engine-
verified-lethal-solver.md`` and the *Lethal* / *Lethal Line* / *Lethal Solver* terms in
``common/CONTEXT.md``.

The **closed-form layer** (`find_lethal_line`) detects a direct KO that wins — by prize-out or by
emptying the opponent's board — and the single enabling develops that unlock it: an Energy attach, a
retreat into a ready benched win-condition, or evolving the Active. Soundness is judged per-attack by
the attack's own prize yield (`_attack_wins`), never a coarse "some KO exists" guess. The **Engine
Search backstop** (`_engine_confirms_win`, Tier-1) forward-simulates a known line's moves through the
simulator's own search and reads its `result` — the grading engine is the authority.

Still to build: driving a full MULTI-step line to terminal *inside* the search (re-running the policy
on each intermediate `SearchState`) and gating the lock on it; and strict execute-only across the whole
turn (a turn-scoped locked line the Pilot follows step by step and vetoes everything else against).
"""
from __future__ import annotations

from dataclasses import dataclass

from common.strategy.context import _ACTIVE, _ATTACH, _ATTACK, _EVOLVE, _MAIN, _RETREAT, KO_SCORE


@dataclass
class LethalLine:
    """A locked, guaranteed win on the current turn: the option index(es) to take at THIS decision
    (``next_step``), a one-line ``rationale`` for the legibility trace, and a ``kind`` tag (``direct``
    / ``unlock`` / ``evolve``) so the Decision Telemetry (ADR-0019) lets a blunder correction be
    filtered and clustered by *how* the win was reached. A multi-step line surfaces one step per
    decision as the engine re-opens the turn menu. ``verified`` is the engine backstop's verdict on
    the lock (``lethal_verify``): True = the engine's own search confirmed the win; None = not
    checked (switch off / multi-step kind / engine unavailable). A False never rides here — a
    refuted candidate is dropped, not locked."""
    next_step: list
    rationale: str = ""
    kind: str = ""
    verified: bool | None = None


class LethalMixin:
    """Pilot-side Lethal Solver. ``find_lethal_line`` returns a :class:`LethalLine` to lock, or None.

    Depends on Pilot internals (``_opp_active``, ``_prize_value``, the ``Board`` and per-option
    ``OptionTrace``), so it is mixed into the Pilot rather than standing alone.
    """

    def find_lethal_line(self, obs, select, board, options, traces) -> LethalLine | None:
        """The shortest guaranteed win on the current turn, or None. Only acts at the single-pick
        MAIN menu; every other context (search, snipe, mulligan, multi-select) is untouched."""
        self._lethal_refutes = 0                       # per-decision engine-refute count (telemetry)
        if select.get("context") != _MAIN or select.get("maxCount", 0) != 1:
            return None
        if board.my_prizes_remaining <= 0:
            return None
        opp = self._opp_active(obs)

        # 1) KO already on menu that WINS now (one step). Judged by attack's OWN prize yield
        # (`_attack_wins`) not coarse "KO exists". lethal_verify engine-confirms DIRECT locks only
        # (a 1-step sim of a multi-step line would false-refute); refute drops the candidate.
        for i, o in enumerate(options):
            if o.get("type") == _ATTACK and self._attack_wins(obs, board, o, opp):
                verified = None
                if self.lethal_verify and not self._planning:
                    verified = self._engine_confirms_win(obs, [[i]])
                    if verified is False:
                        self._lethal_refutes += 1
                        continue                       # the engine says this "win" doesn't win — skip it
                return LethalLine(next_step=[i], rationale="lethal: this KO wins the match",
                                  kind="direct", verified=verified)

        # Develops below unlock a KO of opp ACTIVE (closed-form hooks). Wins iff takes my last prize or
        # opp has no bench to promote — under-counts any rider snipe, conservative but sound.
        if not (self._prize_value(opp) >= board.my_prizes_remaining or not board.opp_bench):
            return None

        # 2) Energy attach (`_attach_lethal_tactical`) or retreat into ready bench attacker
        # (`_retreat_to_lethal_tactical`) unlocking that KO — both KO_SCORE-class; finishing attack follows next menu.
        for i, o in enumerate(options):
            if o.get("type") in (_ATTACH, _RETREAT) and traces[i].tactical >= KO_SCORE:
                return LethalLine(next_step=[i], kind="unlock",
                                  rationale="lethal (unlock): a develop enables the winning KO")
        # 3) EVOLVE of Active bringing bigger attacker online — no closed-form hook scores it, so look
        # up: evolved form inherits Active's Energy, best affordable attack must KO (same-turn legal, rules.md §evolution).
        for i, o in enumerate(options):
            if o.get("type") == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                evolved_id = self._option_card_id(obs, select, o)
                if self._best_affordable_ko_value(obs, board, opp, evolved_id, board.my_active_energy,
                                                  bound="min") > 0:
                    return LethalLine(next_step=[i], kind="evolve",
                                      rationale="lethal (evolve): evolving enables the winning KO")
        return None

    def _attack_wins(self, obs, board, option, opp) -> bool:
        """True iff taking this ATTACK wins the match THIS turn — its own KO(s) take my last prize, or
        it empties the opponent's board. Per-attack and CONSERVATIVE (under-counts riders rather than
        over): a false Lethal is the one catastrophic error, so soundness beats completeness. A
        simultaneous double-KO is a draw, not a win (ADR-0022 #2), so it never wins here."""
        aid = option.get("attackId")
        hp = (opp or {}).get("hp", 0)
        # Damage oracle (ADR-0032): ignore-flag attack (Nebula Beam) KOs through prevent_ex_damage wall old
        # path zeroed. bound="min" = sound FLOOR: coin/conditional contributes worst case, never locks phantom Lethal.
        dmg = self.predicted_damage(self._my_active_id(obs), aid, opp, bound="min",
                                    context=self._damage_context(obs))
        active_ko = bool(hp and dmg >= hp)
        if active_ko and self._is_simultaneous_draw(board, aid, self._prize_value(opp)):
            return False
        prizes_taken = ((self._prize_value(opp) if active_ko else 0)
                        + self._snipe_ko_prizes(board.opp_bench, self._rider_snipe(aid)))
        if prizes_taken >= board.my_prizes_remaining:
            return True
        return active_ko and not board.opp_bench       # KO leaves them no Pokémon to promote

    def _engine_confirms_win(self, obs, line_steps, max_cascade: int = 12):
        """Tier-1 (ADR-0030): forward-simulate ``line_steps`` — a list of per-select index lists, the
        exact moves of a candidate Lethal Line — through the engine's OWN search and report whether IT
        declares me the winner. The grading engine, not my closed-form math, is the authority, so it
        also resolves what closed-form is blind to (abilities, status, Tera, evolution/turn-1 timing).

        A winning attack does not flip ``result`` at the attack step: the engine first opens MY
        cascade selects (take the prize(s), pick a snipe/Damage target, pay a cost), so after the
        line's own steps the search keeps driving MY selects through the policy (``decide``, under
        the ``_planning`` guard so nothing nests or pollutes) until the engine reaches a verdict —
        measured live: the prize-take TO_HAND select is what every real win parks on.

        Sound and fail-safe:
          * ``manual_coin=True`` so a coin the line doesn't account for surfaces as a COIN_HEAD
            select → **None** rather than trust a chosen flip (never let the policy pick heads).
          * the select passing to the OPPONENT with no verdict = the win did not materialize before
            they act → False (a real refute: our win-shapes need no opponent action).
          * an exhausted cascade cap is **None** (undetermined never refutes); so is an unavailable
            search (lib-free suite), a missing ``search_begin_input``, or any error — the caller
            then keeps its sound closed-form verdict.
        The hidden-zone predictions are filled from my own deck list; the cascade's prize picks
        reveal predicted cards but the ``result`` verdict is invariant to WHICH prize is taken.
        Lazy DLL import keeps the fast unit suite from ever loading the native engine."""
        if not (obs or {}).get("search_begin_input") or not line_steps:
            return None
        try:
            from cg import api as cgapi
        except Exception:
            return None
        from dataclasses import asdict

        from common.strategy.planner import _prune_none
        _COIN_HEAD = 46                                # SelectContext.COIN_HEAD (manual-coin choice)
        cur = obs.get("current") or {}
        yi = cur.get("yourIndex", 0)
        players = cur.get("players") or []
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        deck = list(self.deck)

        def take(n):
            return deck[: max(0, n)]

        was_planning = self._planning
        self._planning = True                          # the cascade re-runs decide(): never nest a
        try:                                           # search, never verify inside a verify
            ob = cgapi.to_observation_class(obs)
            st = cgapi.search_begin(ob, take(me.get("deckCount", 0)), take(len(me.get("prize") or [])),
                                    take(opp.get("deckCount", 0)), take(len(opp.get("prize") or [])),
                                    take(opp.get("handCount", 0)), [], manual_coin=True)
            for step in line_steps:
                st = cgapi.search_step(st.searchId, list(step))
            verdict = None
            for _ in range(max_cascade):
                o = st.observation
                c = o.current
                if c and c.result != -1:
                    verdict = c.result == yi           # the engine's own verdict
                    break
                sel = o.select
                if sel is None or c is None:
                    break                              # nothing to drive: undetermined -> None
                if sel.context == _COIN_HEAD:
                    break                              # an unaccounted coin: never choose the flip
                if c.yourIndex != yi:
                    verdict = False                    # passed to the opponent unresolved: no win
                    break
                st = cgapi.search_step(st.searchId, list(self.decide(_prune_none(asdict(o)))))
            cgapi.search_end()
            return verdict
        except Exception:
            try:
                cgapi.search_end()
            except Exception:
                pass
            return None
        finally:
            self._planning = was_planning
