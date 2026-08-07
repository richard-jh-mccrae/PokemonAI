"""The evolve decider's Pilot-side half (ADR-0070): assemble `EvolveInputs` and price the SUBSTITUTION
an evolve forecloses. The equation itself is `common/evolve_value.py`."""
from __future__ import annotations


from common.deciders.facts import Board
from common.evolve_value import EvolveBody, EvolveInputs, evolve_value
from common.strategy.combat import HARVEST_UNAVOIDABLE
from common.strategy.context import _ABILITY, _ACTIVE, _ATTACKER_ROLES, _CARD, _EVOLVE, _EVOLVES_FROM, _ZONE



class EvolveMixin:
    """Board facts for the evolve decider, plus the substitution it forecloses."""

    def _evolve_side(self, obs: dict, board: Board, raw: dict | None, card_id, *,
                     is_active: bool, bench=None) -> EvolveBody:
        """Read ONE body into the decider's damage-currency view (ADR-0070 §2). Only the ACTIVE can
        swing tonight, and going first cannot attack on turn 1 (rules.md §2), so `this_turn` is 0."""
        from common.state_model import BodyView
        raw = raw or {}
        st = self._line_payoff_stat(card_id)
        payoff = float(getattr(st, "maxDamage", 0) or 0) if st is not None else 0.0
        this_turn = 0.0
        mine = self._state_model.mine if self._state_model is not None else None
        if mine is not None and is_active and board.turn > 1:
            this_turn = mine.best_reachable_damage(
                BodyView(raw, combat=self.combat, is_active=True))
        opp = self._opp_player(obs) or {}
        model = self._state_model
        # `bench` is caller-supplied because the RESULT side reads a SUBSTITUTED bench, not the
        # board's; falling back to the real bench keeps a direct caller sound.
        my_bench = list(bench) if bench is not None else self._my_bench_raws(obs)
        opp_active = (model.theirs.active_raw if model is not None
                      else next((p for p in (opp.get("active") or []) if p), None))
        if model is None:
            # No snapshot: both clocks make NO CLAIM, which is what `EvolveBody`'s declared defaults
            # mean (`arm=None` fail-closed, `ko=_HORIZON` safe). Never reach past the model instead.
            return EvolveBody(this_turn=float(this_turn), payoff_damage=payoff)
        return EvolveBody(
            this_turn=float(this_turn), payoff_damage=payoff,
            # ``exclude_expiring`` on BOTH sides (Issue #418 R4): a FORWARD clock counting an Energy
            # that will not be there is wrong, and excluding on the result alone PENALISES evolving.
            arm=model.mine.turns_to_afford(raw, exclude_expiring=True),
            # A RESCUE read — what evolving BUYS — so the harvest declares UNAVOIDABLE (ADR-0071 D3):
            # a benched knockout they can redirect onto another body in range denies nothing.
            ko=model.theirs.turns_to_ko_me(raw,
                                           context=self._opp_attack_context,
                                           my_benched=not is_active,
                                           my_bench=my_bench, key_ids=self._harvest_key_ids(),
                                           reading=HARVEST_UNAVOIDABLE,
                                           opp_active=opp_active,
                                           switch_enabler=self._opp_switch_enabler()))

    def _opp_switch_enabler(self) -> bool:
        """Can the opponent promote a benched attacker WITHOUT paying retreat (ADR-0071 D6) — the
        `switch` tag only. Fails to TRUE: it OPENS a threat gate, so any gap means "assume they can"."""
        if self.opponent is None or not self.functions:
            return True
        try:
            odds = self.opponent.copies_left_odds()
            if not odds:                              # unrecognized opponent — cannot rule one out
                return True
            return any(p > 0 for cid, p in odds.items() if "switch" in self.functions.tags(cid))
        except Exception:
            return True

    def _harvest_key_ids(self) -> frozenset:
        """Card ids the OPPONENT prefers to KO among equal-prize targets (ADR-0071 D8) — a sub-prize
        TIE-BREAK, never a magnitude. A deck declaring no Roles degrades to pure prize-max."""
        cached = getattr(self, "_harvest_key_id_cache", None)
        if cached is None:                            # deck Roles are static for the Pilot's life
            roles = getattr(self.strategy, "roles", None) or {}
            cached = frozenset(cid for cid, r in roles.items() if _ATTACKER_ROLES & set(r or ()))
            self._harvest_key_id_cache = cached
        return cached

    def _evolve_income_delta(self, raw: dict | None, card_id, *, is_active: bool) -> float:
        """Δ`readiness_p` an Ability's dig buys on this body (ADR-0070 §3) — ODDS, never a tier, so a
        redundant engine is worth exactly nothing with no saturation rule. Fail-CLOSED at 0.0."""
        from common.deck_odds import draw_hit_probability
        from common.state_model import BodyView
        depth = self.functions.dig_depth(card_id) if self.functions is not None else 0
        mine = self._state_model.mine if self._state_model is not None else None
        if depth <= 0 or mine is None or not raw:
            return 0.0
        if mine.reachable_attach(BodyView(raw, combat=self.combat, is_active=is_active), None):
            return 0.0
        pool = mine.deck_count
        best = 0.0
        for etype, count in (mine.deck_energy_counts or {}).items():
            # `expected`, not `floor`: a dig's odds ARE an estimate, and `floor` is the leg for a
            # comparison against a COST. TRUNCATED, the conservative direction for an endorser.
            copies = int(getattr(count, "expected", count) or 0)
            # DELIBERATE CombatMath bypass (POC-T1's documented list; `test_combat_bypass_census`):
            # a HYPOTHETICAL enabler Budget, for a form the board does not carry.
            enabler = self.combat.attach_budget(
                raw, mine.hand_ids, energy_attached=mine.energy_attached,
                supporter_played=mine.supporter_played,
                deck_energy_types=mine.deck_energy_types,
                hand_energy_types=frozenset(mine.hand_energy_types) | {etype},
                discard_energy_counts=mine.discard_energy_counts,
                target_benched=not is_active,
                more_prizes_than_opp=mine.more_prizes_than_opp)
            # Both the draw AND the enabler Budget's deck-fetch leg are priced (ADR-0074 D6); with an
            # anchored deck `pay_p` is exactly 1.0.
            pay_p = self.combat.reachable_attach_p(raw, None, budget=enabler,
                                                   p_by_type=mine.deck_energy_p)
            if pay_p > 0.0:
                best = max(best, pay_p * draw_hit_probability(copies, pool, depth))
        return best

    def _evolve_decision(self, obs: dict, board: Board, ctx, option: dict):
        """Price ONE evolve option (ADR-0070) as a legible TERM row, or None to abstain. While the
        kill-switch is OFF the `baseline_evolution` rungs decide alone (the ADR-0069 §8 swap protocol)."""
        if not getattr(self, "evolve_value", False):
            return None
        if ctx.option_type != _EVOLVE or ctx.card_id is None:
            return None
        raw = self._evolve_body(obs, option) or {}
        body_cid = raw.get("id")
        me = self._my_player(obs)
        is_active = any(raw is p for p in (me.get("active") or []))
        body, result, result_raw = self._evolve_substitution(obs, board, raw, ctx.card_id,
                                                             is_active=is_active)
        btags = self.functions.tags(body_cid) if (self.functions and body_cid is not None) else []
        inp = EvolveInputs(
            body=body, result=result,
            ready_gain=self._evolve_income_delta(result_raw, ctx.card_id, is_active=is_active),
            ready_loss=self._evolve_income_delta(raw, body_cid, is_active=is_active),
            # An Ability the engine still OFFERS has not been used this turn — the menu is the fact
            # (ADR-0070 §7), never an assumption about what the tier-0 sequencer already fired.
            result_ability_now=self._ability_on_menu(obs, ctx.card_id),
            body_ability_on_menu=self._ability_on_menu(obs, body_cid),
            body_ability_oneshot=("self_shuffle" in btags),
            hold_turns=(body.arm or 0))
        val = evolve_value(inp)
        return {"deploy": val.deploy, "income_gain": val.income_gain,
                "income_loss": val.income_loss, "tactical": val.total,
                "body": {"this_turn": body.this_turn, "arm": body.arm, "ko": body.ko},
                "result": {"this_turn": result.this_turn, "arm": result.arm, "ko": result.ko}}

    def _evolve_substitution(self, obs: dict, board: Board, raw: dict, target_cid, *,
                             is_active: bool):
        """The BODY-SUBSTITUTED delta both evolve readers share (ADR-0070 §2): two `EvolveBody` readings
        against the SAME bench with exactly one body swapped, as ``(body, result, result_raw)``."""
        body_cid = raw.get("id")
        bench = self._my_bench_raws(obs)
        body = self._evolve_side(obs, board, raw, body_cid, is_active=is_active, bench=bench)
        rstat = self.stats.get(target_cid) if self.stats else None
        # The result keeps the pre-evolution's Energy CARDS (rules.md §4) but RE-READ against the new
        # stage, never copied: provision depends on the HOLDER too (Issue #418 D3).
        result_raw = dict(self.combat.restage_energy(raw, rstat) or raw, id=target_cid)
        if rstat is not None and getattr(rstat, "hp", None):
            result_raw["hp"] = rstat.hp
        # SUBSTITUTE into the bench rather than reading the hypothetical alone: `result_raw` is a COPY,
        # so otherwise the Harvest reads it in isolation and it looks fragile purely for being alone.
        result_bench = [result_raw if b is raw else b for b in bench]
        result = self._evolve_side(obs, board, result_raw, target_cid, is_active=is_active,
                                   bench=result_bench)
        return body, result, result_raw

    def _evolve_target_tactical(self, obs: dict, select: dict, board: Board, option: dict,
                                ctx) -> float:
        """Rank WHICH in-play Pokémon a searched-out evolution lands ON (`_EVOLVES_FROM`, ctx 18). A
        SIBLING of `_evolve_decision`, whose `_EVOLVE` gate no ctx-18 option can pass. Fails CLOSED."""
        if (select or {}).get("context") != _EVOLVES_FROM or option.get("type") != _CARD:
            return 0.0
        state = obs.get("current") or {}
        yi = state.get("yourIndex", 0)
        if option.get("playerIndex", yi) != yi:
            return 0.0                        # the evolution only ever lands on MY own bodies
        # The target rides on the SELECT, not the option: here `ctx.card_id` names the PRE-EVOLUTION.
        # `context_card_id` is the DECLARED store for `select.contextCard` (ADR-0087).
        target_cid = getattr(ctx, "context_card_id", None)
        raw = self._option_pokemon(obs, select, option)
        if target_cid is None or not raw or self._state_model is None:
            return 0.0
        body, result, _result_raw = self._evolve_substitution(
            obs, board, raw, target_cid, is_active=(option.get("area") == _ACTIVE))
        # `ready_gain`/`ready_loss` LEFT AT THEIR DEFAULTS by ruling: the searching card restricts its
        # target to an Ability-less one. An Ability-BEARING pre-evolution would owe plumbing here.
        return evolve_value(EvolveInputs(body=body, result=result)).total

    def _ability_on_menu(self, obs: dict, card_id) -> bool:
        """Is this card's Ability still offered — i.e. not yet used this turn? The MENU is the fact. An
        ABILITY option names its body by SLOT (``area``/``index``) and carries no ``cardId`` at all."""
        if card_id is None:
            return False
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        for o in ((obs.get("select") or {}).get("option") or ()):
            if o.get("type") != _ABILITY:
                continue
            bodies = me.get(_ZONE.get(o.get("area"), "")) or []
            idx = o.get("index")
            if idx is None or not (0 <= idx < len(bodies)) or not bodies[idx]:
                continue
            if bodies[idx].get("id") == card_id:
                return True
        return False

    def _evolve_body(self, obs: dict, option: dict) -> dict | None:
        """The body an EVOLVE option evolves — ``inPlayArea``/``inPlayIndex``, not ``area``/``index``."""
        if option.get("type") != _EVOLVE:
            return None
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        bodies = me.get(_ZONE.get(option.get("inPlayArea"), "")) or []
        idx = option.get("inPlayIndex")
        if idx is None or not (0 <= idx < len(bodies)) or not bodies[idx]:
            return None
        return bodies[idx]

    def _evolve_body_energy(self, obs: dict, option: dict) -> int | None:
        body = self._evolve_body(obs, option)
        return None if body is None else len(body.get("energies") or [])
