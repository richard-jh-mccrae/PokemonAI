"""Healing and damage-counter placement: which body a heal insures, which slot takes the next counter, what a bounce
costs.

Counter placement is a SEQUENTIAL greedy — the engine re-asks per counter with the updated board, so the single-best-
slot pick is the correct answer to each ask."""
from __future__ import annotations


from collections import Counter

from common.deciders.facts import Board
from common.strategy.combat import CURRENT_FORMS_ONLY, UNCHARGED
from common.strategy.context import (_ACTIVE, _BENCH, _CARD, _DAMAGE_COUNTER, _DAMAGE_COUNTER_ANY, _HEAL, _NUMBER,
                                     _REMOVE_DAMAGE_COUNTER, _REMOVE_DAMAGE_COUNTER_COUNT)



class HealMixin:
    """Heals, counter placement and the counter-mover's source/amount picks."""

    def _best_counter_slot(self, obs: dict, select: dict) -> tuple | None:
        """At a DAMAGE_COUNTER_ANY (ctx 14) placement select — one counter (10 dmg) per select, budget
        ``remainDamageCounter`` — the OPPONENT Pokémon to place THIS counter on: (1) if the remaining
        counters can complete one or more KOs (`_best_ko_subset` over the opp targets within the budget),
        place on the KO-set member closest to dying (finish it first, so the sequential per-counter
        greedy maximizes same-turn prizes); (2) else pre-load the lowest-remaining-HP opp target
        (concentrate toward a future KO). Returns (area, index, playerIndex) or None (off ctx 14 / no
        opponent target). A benched Tera takes no damage, so it's excluded (a phantom placement).
        Serves BOTH the Phantom Dive spread (DAMAGE_COUNTER_ANY, budget = `remainDamageCounter`) and a
        counter-mover's ADD-to-opponent target (DAMAGE_COUNTER — Munkidori, which doesn't carry a
        per-select count, so the budget falls back to its 3-counter (30) maximum)."""
        if select.get("context") not in (_DAMAGE_COUNTER_ANY, _DAMAGE_COUNTER):
            return None
        yi = (obs.get("current") or {}).get("yourIndex", 0)
        rem = int(select.get("remainDamageCounter", 0))
        budget = rem * 10 if rem else 30      # ctx 14 carries the count; a counter-mover (ctx 13) -> up to 3
        cands = []                                                  # (option, hp, prize)
        for o in (select.get("option") or []):
            if o.get("type") != _CARD or o.get("playerIndex") == yi:   # opponent-owned targets only
                continue
            poke = self._option_pokemon(obs, select, o)
            hp = (poke or {}).get("hp")
            if not poke or not hp:
                continue
            if o.get("area") == _BENCH and self._is_tera(poke.get("id")):
                continue
            cands.append((o, hp, self._prize_value({"id": poke.get("id")})))
        if not cands:
            return None
        subset = self._best_ko_subset([(hp, pv) for _, hp, pv in cands], budget)
        if subset:
            o = min((cands[i] for i in subset), key=lambda c: c[1])[0]   # finish the closest-to-dying
        else:
            o = min(cands, key=lambda c: (c[1], -c[2]))[0]               # pre-load: lowest HP, tie higher prize
        return (o.get("area"), o.get("index"), o.get("playerIndex"))

    def _best_counter_source_slot(self, obs: dict, select: dict) -> tuple | None:
        """At a REMOVE_DAMAGE_COUNTER (ctx 16) source select — where a counter-mover (Munkidori
        Adrena-Brain) removes counters FROM one of OUR Pokémon — pick our MOST-DAMAGED body: removing
        its counters is the biggest heal (the deck's reverse-heal, offense + heal in one move). Returns
        (area, index, playerIndex) of that body, or None (off ctx 16 / nothing damaged)."""
        if select.get("context") != _REMOVE_DAMAGE_COUNTER:
            return None
        yi = (obs.get("current") or {}).get("yourIndex", 0)
        best, best_dmg = None, 0
        for o in (select.get("option") or []):
            if o.get("type") != _CARD or o.get("playerIndex") != yi:   # our own bodies only
                continue
            poke = self._option_pokemon(obs, select, o)
            if not poke:
                continue
            dmg = int(poke.get("maxHp") or 0) - int(poke.get("hp") or 0)   # damage counters on it
            if dmg > best_dmg:
                best, best_dmg = (o.get("area"), o.get("index"), o.get("playerIndex")), dmg
        return best

    def _heal_target_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """Rank WHICH of my Pokémon a heal card heals, at the HEAL target select (ctx 17, Issue
        #409).

        Nothing scored this select at all. `SelectContext.HEAL` appeared nowhere in the strategy
        layer — not as a constant, not in a `Hypothesis.when`, not in a tactical — so every option
        came back 0.0 and `_order_key` fell through to its canonical-fingerprint leg, which sorts a
        serialized JSON board fragment lexicographically. `option_fingerprint` writes ``[area, card]``
        and `AreaType.ACTIVE` is 4 against `BENCH`'s 5, so ``"4" < "5"`` and **the Pilot healed the
        Active on every board, for every heal card** — not as a policy anyone chose, as an artefact of
        string comparison. Same class of defect `_deploy_decision` records for `_TO_BENCH` before
        Issue #261 item 2d.

        **The rule is NOT the ctx-16 one, and the corpus says why.** `_best_counter_source_slot`
        picks our MOST-DAMAGED body at `_REMOVE_DAMAGE_COUNTER`, which is right there and wrong here:
        at `v2_ms_mirror_5000` f126 the most-damaged body IS the Active (120 to the bench's 50) — but
        healing it under Wally's Compassion bounces its **two attached Energy** to hand, and
        `hold-clutch-heal`'s own rationale is that the play works only when you *"heal, re-power, and
        still attack the same turn"*. Most-damaged is a proxy that cannot see the rider. So:

            heal_target_value(body) = survival_gain(body) − bounce_cost(body)

        and the two legs pull OPPOSITE ways by construction — the Active has the most survival to
        gain and the most to lose by being stripped — which is exactly why a one-dimensional rule
        cannot express the f126 dilemma.

        A **tactical**, not an override returning ``(area, index)`` like the ctx-16 selector.
        `_option_trace` already carries a family of context-gated TARGET terms doing exactly this —
        `_denial_target_tactical` (ctx 30), `_snipe_relevance_tactical` (ctx 15),
        `_gust_target_tactical` (ctx 3) — so a fourth member is the established shape, and routing
        through ``tactical`` PRESERVES `_order_key`'s canonical tie-break (ADR-0103) instead of
        bypassing it. The ctx-16 override predates that family and is not extended.

        **Every option on this menu is a heal target**, so the two legs are weighed only against each
        other; the term is a pure argmax within the select and never competes with a scorer elsewhere.

        Fails CLOSED at 0.0 on anything it cannot price (R3) — an unreadable restriction or a
        condition the closed form can't evaluate contributes nothing rather than a guess, and the
        ordering then degrades to today's behaviour rather than to a wrong answer. Every shipped heal
        reader already errs this way: `_heal_body_candidate` skips an unevaluable ``condition``,
        `_heal_restriction_targets` refuses an unknown ``restriction``."""
        if (select or {}).get("context") != _HEAL or option.get("type") != _CARD:
            return 0.0
        state = obs.get("current") or {}
        yi = state.get("yourIndex", 0)
        if option.get("playerIndex", yi) != yi:
            return 0.0                                # a heal only ever reaches MY own bodies
        cid = ((select or {}).get("effect") or {}).get("id")
        body = self._option_pokemon(obs, select, option)
        stat = self.stats.get(body.get("id")) if (self.stats and body) else None
        if cid is None or not body or stat is None or not self._state_model:
            return 0.0
        is_active = option.get("area") == _ACTIVE
        attached = len(body.get("energies") or [])
        attach_units = (0 if board.energy_attached
                        else self._best_hand_attach_units(board.hand_ids, stat))
        # The restore ceiling is the BODY's `maxHp`, not the card's printed HP: a Hero's Cape (+100)
        # puts a 330-HP Mega Starmie ex on 430, and `amount: "all"` heals to that. Measured on
        # `ms_mirror_1001` f90, where reading the printed HP under-heals the caped Active by 100 and
        # so under-reads its survival.
        cand = self._heal_body_candidate(cid, stat, is_active=is_active,
                                         cur_hp=int(body.get("hp") or 0),
                                         attached=attached, attach_units=attach_units,
                                         max_hp=int(body.get("maxHp") or 0) or None)
        if cand is None:
            return 0.0                                # unreadable target: 0.0, never a guess (R3)
        healed_hp, energy_total = cand
        # `attach_units` is threaded rather than re-derived: the bounce leg needs the SAME manual
        # attach the candidate was priced against, and a second `_best_hand_attach_units` call is a
        # second chance to disagree with the first.
        return (self._heal_survival_gain(obs, body, stat, cid, healed_hp, is_active=is_active)
                - self._heal_bounce_cost(obs, body, energy_total, attach_units,
                                         is_active=is_active))

    def _heal_survival_gain(self, obs: dict, body: dict, stat, cid,
                            healed_hp: int, *, is_active: bool) -> float:
        """What healing ``body`` to ``healed_hp`` BUYS, in damage currency — the positive leg of
        `_heal_target_tactical`'s objective (Issue #409 R2).

        **REACH is the whole read.** ``incoming`` against this body, at the policy
        `Board.incoming_active_damage` already uses, answers R2's question literally — *what can
        actually reach it?* — and it is area-correct by construction: for the Active it is the
        opponent's biggest attack; for a benched body `my_benched=True` routes
        `CombatMath.form_damage_vs` to the snipe/spread RIDERS only, because printed damage always
        lands on the Active (ADR-0070 §9), and to a flat 0 for a Tera (rules.md §185). So the bench
        asymmetry R2 names is DERIVED from a shipped read rather than authored as a discount: a
        benched body nobody can hit has ``reach`` 0 and this whole leg is 0.0.

        Two terms on that one read:

        * **the prizes the knockout would have handed them** — credited only when the body is doomed
          NOW and the heal flips it (`_heal_body_averts_doom` at the same ``reach``). A Mega ex is 3
          Prizes, a Staryu 1; `prize_to_damage` crosses to the damage scale on the shipped
          `PRIZE_DAMAGE_RATE`. Saving a body that dies anyway, or one that was never in danger, is
          worth nothing and reads 0.
        * **the damage the heal DENIES their next swing** — ``min(hp restored, reach)``, in damage,
          at the same 1.0 points-per-damage `_denial_target_tactical` prices a strip at. This is the
          leg that separates two bodies whose doom does not flip, and the cap is what makes it a
          reading rather than a raw count: HP restored beyond what can actually be taken back off
          this body buys nothing, which is the same "score it by what it actually denies" the
          Crushing Hammer target ranker is built on.

        **`needs.survival_value` was tried here and REJECTED, measured** — recorded because it is the
        obvious instrument and the reason it fails is not obvious. It is the natural fit on paper:
        the sub-prize turns-of-survival currency, over the Δ on `turns_to_ko_me`, exactly as
        `_hand_size_relief_tactical` reads it. Two things sank it, both on real corpus boards:

        * its `phase_scale` multiplier is [0, 1] and hits **exactly 0** when I am comfortably ahead —
          at `v2_ms_mirror_5000` f126 (my 2 Prizes to their 6) it clamps to 0, zeroing the only
          discriminator on the very frame this issue exists to fix, and handing the pick straight
          back to the canonical string sort this term replaces. A scaler calibrated to stop survival
          outranking a PRIZE has nothing to weigh at a select where every option is a heal target.
        * the turns-Δ systematically INVERTS the ranking it is asked for. A benched body is chipped
          for 50 a turn and an Active hit for 210, so healing the bench always buys more *turns* —
          at f82 it read the bench 90 to the Active's 15, i.e. it rewarded a body precisely for being
          hard to reach. ``min(restored, reach)`` reads the same board the other way round, which is
          the way R2 asks for.

        The energy policy is `UNCHARGED` — the DOOM policy, named rather than inherited, for the
        reason `_hand_size_relief_tactical` states at length: a survival read must never say *"I
        cannot tell what this costs, so assume it cannot reach me"*, and threading the Read's own
        budget would let a matched Brief quietly relax it (ADR-0064 keeps that per-consumer).
        `CURRENT_FORMS_ONLY` matches `Board.incoming_active_damage`: a heal's breakpoint is tested
        against what the body in front of me hits for TODAY."""
        from common.currency import prize_to_damage
        cur_hp = int(body.get("hp") or 0)
        reach = int(self._state_model.theirs.incoming(
            body, 1, bodies=[self._opp_active(obs)], charged=UNCHARGED,
            forward_ids=CURRENT_FORMS_ONLY, context=self._opp_attack_context,
            my_benched=not is_active))
        prizes = 0.0
        if reach >= cur_hp and self._heal_body_averts_doom(
                cid, stat, is_active=is_active, cur_hp=cur_hp, incoming=reach,
                max_hp=int(body.get("maxHp") or 0) or None):
            prizes = float(getattr(stat, "prize_value", 0) or 0)
        denied = min(max(0, int(healed_hp) - cur_hp), reach)
        return prize_to_damage(prizes) + float(denied)

    def _heal_bounce_cost(self, obs: dict, body: dict, energy_total: int, attach_units: int, *,
                          is_active: bool) -> float:
        """What healing ``body`` FORFEITS this turn, in damage — the negative leg of
        `_heal_target_tactical`'s objective (Issue #409 R2): the attack the heal's Energy rider
        takes away.

        ``best_affordable(E_before) − best_affordable(E_after)``, floored at 0 — the deny oracle's
        own shape (ADR-0062), pointed at my own body instead of theirs. ``E_after`` is
        `_heal_body_candidate`'s ``energy_total``, which is where the rider is already modelled:
        ``bounce_energy_to_hand`` leaves only the manual re-attach paying (Wally's), and
        ``discard_own_energy`` takes one (Super Potion). A clause with no Energy rider leaves the two
        reads equal and the cost is 0 by arithmetic rather than by a branch.

        **0.0 for a benched body, and that is the ruling rather than an approximation** (R2: *"zero
        for a body that was not going to attack this turn"*). Only the Active can swing, so stripping
        a benched body's Energy forfeits no damage THIS turn — it costs future tempo, which this term
        deliberately does not price. The direction is the honest one for a *cost*: under-counting a
        bench bounce can only make the bench look more attractive, and the bench is the option the
        survival leg already refuses to pay for.

        The two reads are deliberately ASYMMETRIC on the colour gate. ``E_before`` passes the real
        ``body``, so a specific-type slot its attached Energy cannot cover fails the attack.
        ``E_after`` does not, so the post-bounce Energy counts as WILD — because it IS wild: a bounce
        rider returns the cards to hand and the re-attach may bring back any of the bounced types,
        which is the same reading `_stabilize_then_ko_lines` states outright when it skips ``body``
        (*"a bounce rider re-attaches ANY bounced type — attached counts are stale here"*). Fail-open
        on the after-read is the direction that under-states the cost.

        ``attach_units`` is threaded in by the caller rather than re-derived here, so both legs price
        against the SAME manual attach `_heal_body_candidate` folded into ``energy_total`` — a second
        `_best_hand_attach_units` call is a second chance to disagree with the first."""
        if not is_active:
            return 0.0                                # only the Active swings this turn
        opp = self._opp_active(obs)
        if not (opp and opp.get("hp")):
            return 0.0
        before = self._best_affordable_damage(
            body.get("id"), len(body.get("energies") or []) + attach_units, opp, body=body,
            extra_units=attach_units)
        after = self._best_affordable_damage(body.get("id"), int(energy_total), opp)
        return max(0.0, float(before) - float(after))

    def _max_counter_move_number(self, select: dict) -> int:
        """At a REMOVE_DAMAGE_COUNTER_COUNT (ctx 40) select, the LARGEST count offered (move as many
        counters as possible — max offense + max heal). 0 off ctx 40."""
        if select.get("context") != _REMOVE_DAMAGE_COUNTER_COUNT:
            return 0
        return max((int(o.get("number", 0)) for o in (select.get("option") or [])
                    if o.get("type") == _NUMBER), default=0)

    def _heal_insures_the_last_wincon(self, cid, me: dict) -> bool:
        """Is held card ``cid`` the heal keeping my LAST win-condition alive? — the user's wave-2
        ruling on ep83969481 f55, stated as a board fact: *"preserve our healer when we only have a
        single wincon remaining."*

        All four clauses are load-bearing, and each removes a way this could over-fire:

        1. ``cid`` carries ``clutch_heal`` — the emergency-heal tag, not any heal (a routine heal is
           latent worth and keeps the general slot);
        2. my Active IS a win-condition (`_wincon_set`) — healing a filler body insures nothing;
        3. no OTHER win-condition body is in play — a second copy on the Bench means the line
           survives the KO, which is exactly ep83661649 f30 (two Mega Starmie ex in play), and that
           frame must NOT take this slot;
        4. the line CANNOT BE REBUILT — no pre-evolution of it survives anywhere reachable: not on
           the Bench, not in hand, and **not in the unseen pool** (deck + face-down prizes).

        Clause 4 reads the unseen pool deliberately, and an earlier draft that stopped at the board
        was measurably wrong: with only the board clauses it fired on *any* empty Bench under a
        wincon Active and cost the Discrimination Gate `82525101|1|decision|87` (rank 1 -> 2), a
        board whose deck still holds Staryu. "Our last wincon" is a claim about COPIES REMAINING, not
        about board shape — on ep83969481 f55 the real fact is that both Staryu are in the discard,
        which strands the spare Mega Starmie ex still sitting in the deck.

        That distinction is also what keeps this off §6's double-counting list. An empty Bench under
        a knock-outable Active already carries two guards (`empty-bench-filter`, `_predicted_loss`),
        and the POC plan names putting it there a third time as the error to avoid. This is a
        different fact — the win-condition LINE being exhausted — and it prices a held card rather
        than gating a move."""
        if not (self.functions and "clutch_heal" in set(self.functions.tags(cid))):
            return False
        active = next((b for b in (me.get("active") or []) if b), None)
        wincons = self._wincon_set()
        if not active or active.get("id") not in wincons:
            return False
        bench = [b for b in (me.get("bench") or []) if b]
        if any(b.get("id") in wincons for b in bench):
            return False                       # the line survives the KO — ep83661649 f30
        hand = [c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None]
        if any(h in wincons and self._successor_evolvable_now(me, h) for h in hand):
            return False                       # a successor lands this turn
        preevos = self._line_preevo_set()
        if not preevos:
            return False                       # a Basic wincon has no line to exhaust
        if any(b.get("id") in preevos for b in bench) or any(h in preevos for h in hand):
            return False
        from collections import Counter
        unseen = Counter(self.deck)
        unseen.subtract(self._visible_card_counts(me))
        return not any(unseen.get(pid, 0) > 0 for pid in preevos)
