"""The evolve decider's Pilot-side half (ADR-0070): assemble `EvolveInputs`, and price the SUBSTITUTION an evolve
forecloses.

The equation itself is `common/evolve_value.py` — this module supplies the board facts it needs and nothing more."""
from __future__ import annotations


from common.deciders.facts import Board
from common.evolve_value import EvolveBody, EvolveInputs, evolve_value
from common.strategy.combat import HARVEST_UNAVOIDABLE
from common.strategy.context import _ABILITY, _ACTIVE, _ATTACKER_ROLES, _CARD, _EVOLVE, _EVOLVES_FROM, _ZONE



class EvolveMixin:
    """Board facts for the evolve decider, plus the substitution it forecloses."""

    def _evolve_side(self, obs: dict, board: Board, raw: dict | None, card_id, *,
                     is_active: bool, bench=None) -> EvolveBody:
        """Read ONE body — the pre-evolution as it stands, or the hypothetical form it becomes —
        into the decider's damage-currency view (ADR-0070 §2).

        The hypothetical result carries the pre-evolution's attached Energy, because evolving keeps
        attached cards (rules.md §4). Only the ACTIVE can swing tonight, and the player going first
        cannot attack on turn 1 (rules.md §2), so `this_turn` is 0 elsewhere rather than optimistic."""
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
        # The SNAPSHOT owns both sides' body lists (ADR-0068 / ADR-0071 decision 7) — read them from
        # it so the harvest and the promotion gate cannot drift from the rest of the turn's reads.
        # `bench` is caller-supplied because the RESULT side reads a substituted bench, not the
        # board's; falling back to the real bench keeps a direct caller sound.
        my_bench = list(bench) if bench is not None else self._my_bench_raws(obs)
        opp_active = (model.theirs.active_raw if model is not None
                      else next((p for p in (opp.get("active") or []) if p), None))
        if model is None:
            # No snapshot — a board that never went through `_board()`. Both clocks then make NO
            # CLAIM, which is what `EvolveBody`'s own declared defaults mean (`arm=None` fail-closed,
            # `ko=_HORIZON` safe); reaching past the model to the oracle here is exactly the bypass
            # POC-T1 exists to close, and the alternative — a second, model-free clock path — is the
            # "answered three ways at three fidelities" disease ADR-0068 was written for.
            return EvolveBody(this_turn=float(this_turn), payoff_damage=payoff)
        return EvolveBody(
            this_turn=float(this_turn), payoff_damage=payoff,
            # MY armed clock, off the snapshot (POC-T1): `mine.turns_to_afford` IS this read with
            # `typed=True` baked in — the typed leg is not optional for my own bodies, because
            # over-crediting an off-colour Energy prices an unpayable line as armed (ADR-0070 §2).
            # ``exclude_expiring`` (Issue #418 R4, developer-ruled 2026-08-06) on BOTH sides, because
            # this is a FORWARD clock and `MySide.turns_to_afford`'s own docstring states the rule:
            # *"A FORWARD clock counting an Energy that will not be there is not conservative, it is
            # wrong."* A Staryu carrying one Ignition is not one attach nearer Nebula Beam next turn
            # than a Staryu carrying nothing — the card is discarded at the end of THIS turn.
            #
            # The symmetry is the ruling, not a nicety. Excluding on the RESULT alone judges the
            # post-evolution honestly while still crediting the pre-evolution's vanishing card as
            # forward progress, and the mismatch reads as a PENALTY for evolving: measured on
            # `ms_mirror_1001` f15 bench 0 it prices the evolve at −26.25, the worst option on the
            # menu, where both-sides returns it to a clean 0.00 tie with the Ignition-less Staryu
            # beside it (ADR-0125's table).
            arm=model.mine.turns_to_afford(raw, exclude_expiring=True),
            # AREA-AT-DAMAGE-TIME (ADR-0070 §9): an evolve does not move the body, so the area it
            # occupies now IS the area the reply lands on — the one place the board read is sound.
            #
            # HARVEST READING (ADR-0071 decision 3): this is a RESCUE read — it asks what evolving
            # BUYS — so it declares UNAVOIDABLE. A benched knockout the opponent can simply redirect
            # onto another body in range denies nothing; crediting it inflates every bench rescue.
            # The bench snapshot is passed because a shared rider budget is unrepresentable from one
            # body alone, and `key_ids` is deck-DECLARED (CombatMath is deck-agnostic).
            #
            # The energy policy is the snapshot's THREADED one (the Read's `_incoming_budget`) — no
            # `charged=` here, because this consumer wants exactly the default the Read supplies.
            ko=model.theirs.turns_to_ko_me(raw,
                                           context=self._opp_attack_context,
                                           my_benched=not is_active,
                                           my_bench=my_bench, key_ids=self._harvest_key_ids(),
                                           reading=HARVEST_UNAVOIDABLE,
                                           opp_active=opp_active,
                                           switch_enabler=self._opp_switch_enabler()))

    def _opp_switch_enabler(self) -> bool:
        """Can the opponent promote a benched attacker WITHOUT paying retreat — the enabler leg of
        the promotion gate (ADR-0071 decision 6).

        True unless a switch-class out is PROVABLY gone: `copies_left_odds` returns 0 for a card only
        when every copy in the matched Read's representative build is already accounted for on the
        board or in the discard, so `p > 0` is exactly ADR-0067's *not-provably-absent* test — and a
        copy sitting in their hidden HAND counts as unseen, which is the case that matters here.
        Only the `switch` tag: a `gust` card drags one of MY bodies up, it does not promote theirs.

        Same shape as `_opp_hand_strip_odds`, **opposite fail direction**. That one claims no
        exposure on a guess because a veto must not fire on one; this one claims FULL exposure,
        because it OPENS a threat gate — and the gate can only ever make a survival read less
        pessimistic. CONTEXT.md's Threat Clock: *"A survival read must never under-prepare; a prep
        read off by a turn is recoverable."* So no facade, no functions table, no confident Read, or
        any error all mean "assume they can switch"."""
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
        """Card ids the OPPONENT prefers to knock out among equal-prize targets — my deck-declared
        attacker/line Roles (ADR-0071 decision 8). A sub-prize tie-break, never a magnitude: it
        cannot represent an opponent who forfeits a prize to kill an engine piece.

        `_ATTACKER_ROLES` rather than `_WINCON_ROLES` because the narrow pair is verified INERT on
        the Bench — the wincon itself is usually Active or in hand, and what sits benched is its
        base (dragapult_ex declares Dreepy `win_condition_base`, Munkidori `counter_mover`, and
        Dunsparce no Role at all). A deck declaring no Roles degrades to pure prize-max."""
        cached = getattr(self, "_harvest_key_id_cache", None)
        if cached is None:                            # deck Roles are static for the Pilot's life
            roles = getattr(self.strategy, "roles", None) or {}
            cached = frozenset(cid for cid, r in roles.items() if _ATTACKER_ROLES & set(r or ()))
            self._harvest_key_id_cache = cached
        return cached

    def _evolve_income_delta(self, raw: dict | None, card_id, *, is_active: bool) -> float:
        """Δ`readiness_p` an Ability's dig buys on this body — what the engine is actually worth
        (ADR-0070 §3), as odds rather than a tier.

        Zero on a body that ALREADY reaches, which is what makes a redundant engine worth exactly
        nothing with no saturation rule, and what collapses the hold the moment the body is armed.
        Otherwise the exact hypergeometric that the dig finds an enabler that WOULD pay — checked
        per candidate Energy type against a Budget built as though that card were in hand. Fail-
        CLOSED at 0.0 (ADR-0067): an untagged dig depth, or an enabler that still would not pay, is
        worth nothing rather than its bare draw odds."""
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
            # NAME the epistemic. `deck_energy_counts` holds `CountTriple`s, which refuse to be a
            # bare number precisely so a consumer cannot smuggle an estimate into sound math
            # (ADR-0068). A dig's odds ARE an estimate — ADR-0070 §3 calls income "an ODDS read,
            # never a tier" — so `expected` is the leg. `floor` is the leg for comparisons against a
            # COST, and while prizes are hidden it is 0 for almost every energy type: passing the
            # triple itself used to raise TypeError into `draw_hit_probability`'s "bad input -> 0.0"
            # guard, which silently zeroed §3, §7 and amendment B on EVERY board (#167).
            # Truncated, not rounded — the conservative direction for an endorser.
            copies = int(getattr(count, "expected", count) or 0)
            # DELIBERATE CombatMath bypass (POC-T1's documented list; `test_combat_bypass_census`):
            # a HYPOTHETICAL enabler Budget. Every argument is a model read, but the TARGET is a form
            # the board does not carry in this configuration, and the model's route builds a Budget
            # for a body it holds. Inventing a `MySide` method per hypothetical would move the
            # assembly, not remove it.
            enabler = self.combat.attach_budget(
                raw, mine.hand_ids, energy_attached=mine.energy_attached,
                supporter_played=mine.supporter_played,
                deck_energy_types=mine.deck_energy_types,
                hand_energy_types=frozenset(mine.hand_energy_types) | {etype},
                discard_energy_counts=mine.discard_energy_counts,
                target_benched=not is_active,
                more_prizes_than_opp=mine.more_prizes_than_opp)
            # ADR-0074 decision 6 (#175): this priced the DRAW honestly while leaving the enabler
            # Budget's deck-fetch leg a fail-open boolean, so a line resting on the last copy of a
            # colour read identically to one resting on three. Both are priced now; with an
            # anchored deck `pay_p` is exactly 1.0 and the reading is unchanged.
            pay_p = self.combat.reachable_attach_p(raw, None, budget=enabler,
                                                   p_by_type=mine.deck_energy_p)
            if pay_p > 0.0:
                best = max(best, pay_p * draw_hit_probability(copies, pool, depth))
        return best

    def _evolve_decision(self, obs: dict, board: Board, ctx, option: dict):
        """The EVOLVE DECIDER: price ONE evolve option (ADR-0070). Returns the per-option TERM row —
        the decider's legible working — or None to abstain: the kill-switch is OFF, or this is not
        an EVOLVE option.

        While the switch is OFF the `baseline_evolution` rungs decide alone, which is the swap
        protocol (ADR-0069 §8): both deciders stay alive until the corpus flips are user-ruled."""
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
            # An Ability the engine still offers has NOT been used this turn — the menu is the fact,
            # never an assumption about whether the tier-0 sequencer already fired it (ADR-0070 §7).
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
        """The BODY-SUBSTITUTED delta both evolve readers share (ADR-0070 §2): read the
        pre-evolution ``raw`` and the hypothetical form it becomes into two `EvolveBody` readings,
        against the SAME bench with exactly one body swapped. Returns
        ``(body, result, result_raw)``.

        Extracted (Issue #417) because a SECOND caller arrived — `_evolve_target_tactical`, the
        `_EVOLVES_FROM` (ctx 18) target select — and the substitution below is exactly the kind of
        subtle, comment-carrying step two hand-rolled copies are free to drift apart on (ADR-0087:
        one store per fact). `_evolve_decision`'s gate, inputs and return are unchanged; only the
        five statements that were already a self-contained unit moved.

        The two callers differ ONLY in where the pair of card ids comes from. At MAIN an `_EVOLVE`
        option names its body by ``inPlayArea``/``inPlayIndex`` and the evolution by the option's own
        hand card (`ctx.card_id`); at ctx 18 the option names the BODY (so `ctx.card_id` resolves to
        the pre-evolution, not the target) and the evolution rides on ``select["contextCard"]["id"]``.
        Everything downstream of that pair is identical, which is why it lives here once."""
        body_cid = raw.get("id")
        bench = self._my_bench_raws(obs)
        body = self._evolve_side(obs, board, raw, body_cid, is_active=is_active, bench=bench)
        # The result inherits the pre-evolution's attached Energy CARDS (rules.md §4) and its slot,
        # so the hypothetical body differs from the real one ONLY in which card it is — exactly the
        # substitution the deploy delta is asking about…
        rstat = self.stats.get(target_cid) if self.stats else None
        # …and its attached Energy CARDS are RE-READ against the new stage, never copied (Issue #418
        # D3). The provision is a property of the holder as well as of the card: one Ignition Energy
        # renders `[0]` on a Basic Staryu and `[0, 0, 0]` on Mega Starmie ex, so copying ``energies``
        # verbatim hands the result side a board the engine would never produce. `board_delta._evolve`
        # — the APPLY seam for the very same substitution — has always re-derived it; the decider had
        # no reading of the evolution clause at all. `restage_energy` declines (returns the body
        # unchanged) when the cards cannot be re-derived or the model already disagrees with this
        # board, so an unreadable card degrades to the old copy rather than to a guess.
        result_raw = dict(self.combat.restage_energy(raw, rstat) or raw, id=target_cid)
        if rstat is not None and getattr(rstat, "hp", None):
            result_raw["hp"] = rstat.hp
        # SUBSTITUTE the hypothetical into the bench rather than reading it alone. `result_raw` is a
        # COPY, so without this the Harvest would read B among its bench-mates and R in isolation —
        # and R would look fragile purely for being alone, which is not a fact about evolving. Both
        # sides must see the same bench with exactly one body swapped (ADR-0070's body-substituted
        # delta; ADR-0071 makes the bench read sensitive to the company a body keeps).
        result_bench = [result_raw if b is raw else b for b in bench]
        result = self._evolve_side(obs, board, result_raw, target_cid, is_active=is_active,
                                   bench=result_bench)
        return body, result, result_raw

    def _evolve_target_tactical(self, obs: dict, select: dict, board: Board, option: dict,
                                ctx) -> float:
        """Rank WHICH of my in-play Pokémon a searched-out evolution is put ONTO, at the
        `_EVOLVES_FROM` target select (ctx 18, Issue #417).

        Salvatore evolves a body straight out of the deck, bypassing hand: *"Search your deck for a
        card that has no Abilities and evolves from 1 of your Pokémon, and put it onto that Pokémon
        to evolve it."* The engine poses `_EVOLVES_TO` (19, which physical deck copy — moot, every
        corpus option is an interchangeable copy of one species) and then this one, which is the real
        decision: with three Staryu in play, WHICH becomes the Mega Starmie ex.

        **Nothing scored it.** `_evolve_decision`'s guard is ``ctx.option_type != _EVOLVE``, and
        `_EVOLVE` (9) is a MAIN-menu ACTION type; every ctx-18 option carries `_CARD` (3), so the
        decider abstains here unconditionally. `_prefer_soonest_arming_evolve` carries the identical
        ``type == _EVOLVE`` gate, so its own insight — *put the evolution where the Energy already
        is* — is exactly relevant here and exactly unreachable here. With every option at 0.0 the
        pick fell through to `_order_key`'s canonical-fingerprint leg, the same string-sort artefact
        `_heal_target_tactical` records for ctx 17.

        **No new equation.** `evolve_value` is a pure function of two `EvolveBody` readings and
        nothing in it is MAIN-specific, so this term is `_evolve_decision`'s own body re-pointed at
        ctx-18's option shape through the shared `_evolve_substitution`. What it measures is
        `deploy(R) − deploy(B)` — and that already carries the survival dimension the mechanic
        creates: evolving keeps attached cards AND damage counters (rules.md §4), so a *damaged* body
        arrives relatively healthier (absolute damage fixed, ceiling jumped), which `EvolveBody.ko`
        reads off the body's actual HP at damage time. Nothing extra to model.

        **The two income legs are structurally zero here, by the CARD rather than by assumption.**
        Salvatore's clause carries ``"no_ability": true`` (`card_effects.json` 1189), so the search
        target is guaranteed Ability-less and `ready_gain` is 0 by the card's own restriction;
        `ready_loss` is 0 for every body this deck can offer (Staryu has no Ability). Both are left
        at their `EvolveInputs` defaults rather than plumbed — see the call site's own note, which
        flags what a deck running such a search over an Ability-BEARING pre-evolution would owe.

        A **tactical**, not an override: `_option_trace` already carries a family of context-gated
        target terms (`_gust_target_tactical` ctx 3, `_snipe_relevance_tactical` ctx 15,
        `_denial_target_tactical` ctx 30, `_heal_target_tactical` ctx 17), and routing through
        ``tactical`` preserves `_order_key`'s canonical tie-break (ADR-0103) instead of bypassing it.
        A SIBLING of `_evolve_decision` rather than a widening of its gate: that decider's return
        also drives `_prefer_soonest_arming_evolve`'s ordering and is stored as ``evolve_working`` on
        `OptionTrace`, and neither consumer was built to see a select.

        Fails CLOSED at 0.0 on anything it cannot price — no ``contextCard``, an unresolvable option
        body, no snapshot — matching `_heal_target_tactical`'s R3 and `_evolve_decision`'s own
        ``or {}`` discipline. Every option then reads 0.0 and the ordering degrades to today's
        behaviour rather than to a wrong answer."""
        if (select or {}).get("context") != _EVOLVES_FROM or option.get("type") != _CARD:
            return 0.0
        state = obs.get("current") or {}
        yi = state.get("yourIndex", 0)
        if option.get("playerIndex", yi) != yi:
            return 0.0                        # the evolution only ever lands on MY own bodies
        # The target rides on the SELECT, not the option: `ctx.card_id` here resolves the option's
        # own (area, index) and so names the PRE-EVOLUTION — the wrong card for any reader that
        # assumes it is "the card this option is about" the way it is at MAIN. `context_card_id` is
        # the DECLARED store for `select.contextCard` (it already feeds mega_lucario's ACTIVATE
        # rungs), so this reads it rather than minting a second walk of the same field (ADR-0087).
        # That is also why this term takes `ctx` where its ctx-17 sibling does not:
        # `_heal_target_tactical` reads `select.effect.id`, for which no Context field exists.
        target_cid = getattr(ctx, "context_card_id", None)
        raw = self._option_pokemon(obs, select, option)
        if target_cid is None or not raw or self._state_model is None:
            return 0.0
        body, result, _result_raw = self._evolve_substitution(
            obs, board, raw, target_cid, is_active=(option.get("area") == _ACTIVE))
        # `ready_gain`/`ready_loss` LEFT AT THEIR DEFAULTS (0.0), and that is a ruling rather than an
        # omission: the searching card's own clause restricts the target to an Ability-less card, so
        # the gain leg cannot fire; the loss leg is zero for every pre-evolution this select can
        # currently offer. A future deck posing ctx 18 over an Ability-BEARING pre-evolution would
        # owe `_evolve_income_delta` plumbing here — flagged, not silently assumed (Issue #417).
        return evolve_value(EvolveInputs(body=body, result=result)).total

    def _ability_on_menu(self, obs: dict, card_id) -> bool:
        """Is this card's Ability still offered on the current menu — i.e. not yet used this turn?
        Abilities fire "per the ability's own text" (rules.md:91), and the engine simply stops
        offering a once-per-turn one after use, so the MENU is the fact. False without a menu.

        An ABILITY option names its body by **slot** (``area``/``index``) and carries no ``cardId``
        at all, so matching on one was False on every board ever built — silently killing
        ``body_ability_on_menu`` (§7's "this turn's use is forfeit" half of the split-horizon loss)
        and ``result_ability_now`` (which un-halves a gain that fires THIS turn). Resolve the slot
        and compare the card sitting in it (#167)."""
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
        """The in-play Pokémon an EVOLVE option would evolve (its ``inPlayArea``/``inPlayIndex`` body).
        None off an EVOLVE option or when the slot can't be resolved."""
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
        """Energy COUNT on the body an EVOLVE option would evolve — so a rule can HOLD a win-condition
        evolution until the payoff can attack. None off EVOLVE."""
        body = self._evolve_body(obs, option)
        return None if body is None else len(body.get("energies") or [])
