"""The win-condition LINES: which cards form them, which member is missing, which slot is the priority, and whether the
payoff can still be reached.

A Line is the deck's own declaration (`Strategy.lines`); everything here reads it rather than inferring intent from
card names."""
from __future__ import annotations


from common.deciders.plan_choice import _min_attack_cost
from common.strategy.context import _ACTIVE, _BENCH



class LineMixin:
    """The win-condition lines and their in-play state."""

    def _wincon_lines(self) -> list:
        """The declared Lines whose payoff IS the win-condition (Line role 'win_condition') — never a
        secondary-attacker Line (ADR-0048). The win-condition machinery (`_wincon_set`, `_line_preevo_set`,
        `_line_member_set`, the immediate-pre-evo / concentrate helpers) is scoped to these, so declaring a
        cheap secondary-attacker Line (role 'secondary_attacker') never mislabels its payoff a win-condition
        or its base a wincon pre-evo. A no-op for every existing deck — all declare only 'win_condition'."""
        return [l for l in self.strategy.lines if getattr(l, "role", "win_condition") == "win_condition"]

    def _wincon_set(self) -> set:
        """Card ids that ARE the win-condition — a WIN-CONDITION Line payoff (role-gated, `_wincon_lines`)
        or a card carrying the `win_condition` / `primary_attacker` Role. Match-invariant (pure over the
        fixed `Strategy`), so memoised like `_stranded_evolution_set` — `_context` reads it per option."""
        cached = getattr(self, "_wincon_set_cache", None)
        if cached is not None:
            return cached
        wincon = {line.payoff for line in self._wincon_lines()}
        wincon |= {cid for cid, r in self.strategy.roles.items()
                   if {"win_condition", "primary_attacker"} & set(r)}
        self._wincon_set_cache = wincon
        return wincon

    def _wincon_prize_value(self) -> int:
        """The greatest prize value among my declared win-condition bodies (Mega ex 3 / ex 2 / else 1) —
        the multi-prize payoff a cheap secondary line makes the opponent take MORE, smaller KOs than
        (ADR-0048). 0 if none. Backs `Board.wincon_prize_value`."""
        wincon = self._wincon_set()
        return max((self._prize_value({"id": c}) for c in wincon), default=0) if wincon else 0

    def _wincon_in_hand(self, me: dict) -> bool:
        """True if the win-condition card is already in my hand — a tutor needn't dig for another."""
        wincon = self._wincon_set()
        return bool(wincon) and any(c and c.get("id") in wincon for c in (me.get("hand") or []))

    def _wincon_in_hand_undeployable(self, me: dict) -> bool:
        """True iff an EVOLUTION win-condition is in my hand but has NO base to deploy it: not already
        in play, its Line HAS a pre-evolution (so it isn't a directly-benchable Basic wincon), and no
        pre-evolution sits in play OR hand. Such a card is dead this turn — `hold-wincon-dont-shuffle`
        must let it be shuffled away to dig for a base (ep83966336 f44: Mega Lucario ex held with no
        Riolu anywhere)."""
        if not (self._wincon_in_hand(me) and not self._wincon_in_play(me)):
            return False
        if not self._line_preevo_set():                    # Basic-payoff wincon — benchable, keep it
            return False
        return not (self._line_preevo_in_play(me) or self._line_preevo_in_hand(me))

    def _wincon_in_play(self, me: dict) -> bool:
        """True if my win-condition is already in play — a Strategy Line payoff or a card carrying the
        `win_condition` / `primary_attacker` Role sitting on my Active or Bench. Lets a 'fetch the
        win-condition' Hypothesis stand down once the payoff is on the board (don't pull a dead copy)."""
        wincon = {line.payoff for line in self.strategy.lines}
        wincon |= {cid for cid, r in self.strategy.roles.items()
                   if {"win_condition", "primary_attacker"} & set(r)}
        if not wincon:
            return False
        board = (me.get("active") or []) + (me.get("bench") or [])
        return any(p and p.get("id") in wincon for p in board)

    def _wincon_payoff_ids(self) -> frozenset:
        """The deck's declared WIN-CONDITION Line payoffs. The gate on the Opener Marginal (ADR-0081
        amendment A) — an evolution in hand only reorders the opener when it is what the deck is
        actually trying to build.

        Routed through `_wincon_lines`, so a `secondary_attacker` Line is excluded exactly as it is
        everywhere else in the win-condition machinery (ADR-0048). That role gate is load-bearing
        here, not incidental: mega_lucario declares `Line(MAKUHITA -> HARIYAMA,
        role='secondary_attacker')` for a 210-damage prize wall, and reading it as a payoff would
        promote Makuhita over a declared rank-1 Solrock on the strength of raw damage — the very
        "big number wins" reasoning amendment A rejected.

        **Deliberately NOT `_wincon_set`**, whose first clause is identical. That set additionally
        unions in every card carrying a `win_condition` / `primary_attacker` ROLE, which is a strictly
        broader concept: it would let a role-tagged body that is on no declared Line act as an opener
        payoff, widening the gate past what ADR-0081 decision 4 specifies (*"the `payoff` of one of the
        deck's declared win-condition Lines"*). The two sets coincide for all three authored decks
        today, so the divergence is LATENT — swapping them reddens nothing by accident. The binding
        record is therefore ADR-0081 decision 4 plus its guard test
        (`test_a_ROLE_tagged_body_that_is_no_line_payoff_does_not_promote_its_base`), not this
        docstring, which would be deleted along with the very function a reviewer proposes collapsing.

        Deck-fixed and match-invariant, so memoised in the same shape as `_wincon_set`."""
        cached = getattr(self, "_wincon_payoff_cache", None)
        if cached is not None:
            return cached
        payoffs = frozenset(p for p in (getattr(ln, "payoff", None) for ln in self._wincon_lines())
                            if p is not None)
        self._wincon_payoff_cache = payoffs
        return payoffs

    def _line_preevo_set(self) -> set:
        """Card ids that are a non-payoff member of a WIN-CONDITION Line's path (role-gated,
        `_wincon_lines`) — a pre-evolution that builds toward the win-condition payoff (Staryu on the
        Staryu → Mega Starmie line). NARROW by design: feeds `wincon_base_deployable` /
        `_evolve_to_ready_wincon_available` / the hold/undeployable machinery, so a secondary-attacker
        Line's base is NOT in it (ADR-0048 — the broadened, line-piece-crediting set is
        `_recognized_line_preevo_set`). Match-invariant, memoised (read per option in `_context`)."""
        cached = getattr(self, "_line_preevo_cache", None)
        if cached is not None:
            return cached
        self._line_preevo_cache = {cid for line in self._wincon_lines()
                                   for cid in line.path if cid != line.payoff}
        return self._line_preevo_cache

    def _recognized_line_preevo_set(self) -> set:
        """Pre-evolutions of EVERY declared attacker Line — win-condition AND secondary-attacker
        (ADR-0048). Read ONLY by the preference rungs (`prefer-wincon-line-piece` at a fetch,
        `develop-the-cheap-prize-wall-line`), so a secondary attacker's base (Makuhita) earns the same
        line-piece credit as the wincon base (Riolu) without touching the narrow `_line_preevo_set` the
        deploy/hold machinery rides. Falls back to the narrow win-condition set when the ADR-0048
        kill-switch is OFF — so a declared secondary Line is fully inert then. Match-invariant
        (the kill-switch is fixed too), memoised — read per option in `_context`."""
        cached = getattr(self, "_recognized_preevo_cache", None)
        if cached is not None:
            return cached
        if not self.prize_economy_fetch:
            result = self._line_preevo_set()
        else:
            result = {cid for line in self.strategy.lines for cid in line.path if cid != line.payoff}
        self._recognized_preevo_cache = result
        return result

    def _active_is_weak_preevo(self, ma: dict | None) -> bool:
        """True iff my Active is a WIN-CONDITION line pre-evolution (`_line_preevo_set`) whose OWN printed
        output is a minor chip far below the body it evolves into — attaching an Energy to it buys little
        tempo (Riolu's 30 vs Mega Lucario ex 130/270). Read by mega_lucario's Lunar-Cycle stand-down: with
        the engine online, discard the last {F} to draw 3 rather than sink it into a weak pre-evo whose 30
        chip doesn't change the game's tempo (ml 85058574 f16). 'Weak' = own maxDamage is under half the
        forward form's max, so a real-attacker pre-evo (Makuhita→Hariyama 210) still keeps the {F}. FAIL-CLOSED
        on missing stats / non-preevo active."""
        cid = (ma or {}).get("id")
        if cid is None or cid not in self._line_preevo_set():
            return False
        stat = self.stats.get(cid) if self.stats else None
        own = getattr(stat, "maxDamage", None) if stat else None
        fwd_fn = getattr(self.stats, "forward_max_damage", None) if self.stats else None
        fwd = fwd_fn(cid) if fwd_fn else None
        if not own or not fwd:
            return False
        return own * 2 <= fwd

    def _line_preevo_in_play(self, me: dict) -> bool:
        """True if a non-payoff member of any Line's path (a pre-evolution) is on my Active/Bench —
        so a rush-evolve tutor has something to evolve toward the payoff."""
        preevos = self._line_preevo_set()
        if not preevos:
            return False
        board = (me.get("active") or []) + (me.get("bench") or [])
        return any(p and p.get("id") in preevos for p in board)

    def _line_preevo_in_hand(self, me: dict) -> bool:
        """True if a Line pre-evolution (a base to evolve the payoff from) is in my hand — so I can
        bench it and deploy the payoff. The hand-side companion of `_line_preevo_in_play`."""
        preevos = self._line_preevo_set()
        if not preevos:
            return False
        return any(c and c.get("id") in preevos for c in (me.get("hand") or []))

    def _successor_evolvable_now(self, me: dict, cid) -> bool:
        """Can ``cid`` — a payoff sitting in my HAND — legally evolve a body I have in play **this
        turn**? A pre-evolution matching its ``evolvesFrom`` name must be on my Active/Bench AND must
        not have arrived this turn: `docs/rules.md` §4 `[RULE: rulebook L123-128]` `[ENGINE-LEGAL]`
        — *"cannot evolve a Pokémon the turn it was played/put into play."*

        Consumed by `_heal_insures_the_last_wincon` (clause 3: a successor that LANDS this turn
        means the line is not exhausted, so the heal insures nothing irreplaceable). Deliberately NOT
        `board.line_preevo_in_play`, which asks the looser *"is there anything a rush-evolve tutor
        could aim at"* and is read by other consumers. Both clauses matter: name-matching alone says
        yes on a board where the engine offers no evolve option at all (ep83117367 f34 — two Staryu,
        both benched this turn, so the held Mega Starmie ex has no playable option on the menu).

        It was also built as the URGENT succession spike's gate and REVERTED — see `line_slots`'
        docstring and ADR-0101: that narrowing contradicts the ep83037962 f49 ruling."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        base = getattr(st, "evolvesFrom", None) if st is not None else None
        if not base:
            return False
        bodies = (me.get("active") or []) + (me.get("bench") or [])
        return any(b and not b.get("appearThisTurn")
                   and getattr(self.stats.get(b.get("id")), "name", None) == base
                   for b in bodies)

    def _line_readiness_deadline(self, me: dict, cid) -> int:
        """READINESS (piece 1): how soon a held wincon ``cid`` comes online, as the re-access deadline
        the refresh-SHED window clamps to (`_refresh_slot_resupply`). Keyed on the payoff's BASE being
        in play — the human's own line ("no riolu in play, thus it's worthless at this moment",
        ml ep83966336 f44):

          * a base in play AND already powered ⇒ **1** (evolve next turn, attack soon — hold it);
          * a base in play but unpowered ⇒ **2** (a turn further, still an imminent line — hold it);
          * NO base in play ⇒ **99** (latent — the payoff cannot be assembled soon, it is freely
            re-fetchable once a base lands, so it stays cheap to shuffle away — restores f44).

        Two live Staryu keep both Mega Starmie expensive to shed (deadline 2, ep82752604 f16); a lone
        Mega Lucario with no Riolu down stays sheddable (99). Fail-open: unknown forward-line facts ⇒
        no base found ⇒ 99 (the re-fetchable side, never over-protects)."""
        if cid is None:
            return 99
        board = [p for p in ((me.get("active") or []) + (me.get("bench") or [])) if p]
        bases = [p for p in board if cid in self._forward_card_ids(p.get("id"))]
        if not bases:
            return 99
        return 1 if any(p.get("energies") for p in bases) else 2

    def _bench_line_member_needs(self, me: dict) -> bool:
        """True if a BENCHED body on a declared win-condition Line's path (pre-evolution or payoff,
        `_line_member_set`) still needs Energy for its cheapest attack (`_attach_target_needs`) — an
        un-powered line is waiting on the bench. The board-side gate of `prefer-active-attach-in-
        setup`'s stand-down (86091728 f19: two bare benched Dreepy while the {P} went to Munkidori);
        role-gated via `_wincon_lines`, so decks without a declared Line never trip it."""
        members = self._line_member_set()
        if not members:
            return False
        return any(p and p.get("id") in members and self._attach_target_needs(p)
                   for p in (me.get("bench") or []))

    def _line_member_set(self) -> set:
        """Every card id on a WIN-CONDITION Line's path (role-gated, `_wincon_lines`) — pre-evolutions AND
        the payoff. The Pokémon a bench accelerator (e.g. Cinderace's Turbo Flare) can usefully load Energy
        onto; scoped to the win-condition line so a secondary-attacker Line never silently redirects the
        accelerator's recipient hunt (ADR-0048)."""
        return {cid for line in self._wincon_lines() for cid in line.path}

    def _payoff_immediate_preevo_set(self) -> set:
        """Card ids that are a Line payoff's IMMEDIATE pre-evolution — the path member one hop below
        the payoff (`path[index(payoff) - 1]`). For a SINGLE-HOP Line (Staryu -> Mega Starmie ex) this
        is the Basic base and equals `_line_preevo_set`; for a MULTI-STAGE Line (Dreepy -> Drakloak ->
        Dragapult ex) it is ONLY the Stage-1 (Drakloak), not the Stage-0 base (Dreepy). Lets the
        win-condition readiness signals tell 'the payoff is ONE evolution from deployable/ready' apart
        from 'some Line pre-evo is around somewhere' — the distinction the distance-blind signals
        missed on the corpus's first 2-stage line (dragapult f14/f31; ml f31). Pure + total."""
        out = set()
        for line in self._wincon_lines():
            path = line.path or []
            if line.payoff in path:
                i = path.index(line.payoff)
                if i > 0:
                    out.add(path[i - 1])
        return out

    def _payoff_immediate_preevo_available(self, me: dict) -> bool:
        """True if a payoff's IMMEDIATE pre-evolution is in play OR hand — the payoff is exactly one
        evolution from being deployable. Identical to `_line_preevo_in_play or _line_preevo_in_hand`
        for single-hop Lines (the immediate pre-evo IS the only pre-evo); on a multi-stage Line it is
        False while only a deeper base is around (a lone Dreepy no longer reads the two-hop Dragapult
        ex as base-deployable). Backs `wincon_base_deployable`."""
        imm = self._payoff_immediate_preevo_set()
        if not imm:
            return False
        zones = (me.get("active") or []) + (me.get("bench") or []) + (me.get("hand") or [])
        return any(p and p.get("id") in imm for p in zones)

    def _roles_of(self, cid) -> list:
        """The Context's per-card Roles: the deck-DECLARED list (`strategy.roles`) plus the DERIVED
        `accel_source` for a body whose attack carries a bench-target accel rider
        (`_derived_accel_body_ids` — Turbo Flare / Aura Jab class). Derivation-first, declaration as
        the confirm/override (Round 9): a new deck fielding Cinderace gets the whole accel rung
        family (develop-the-accel-recipient, feed-the-accelerator, promote — `open-the-accelerator`
        was deleted by ADR-0079; the pregame Active pick is `Strategy.starter_priority` now)
        with NO Role declaration; for the existing agents the union is a no-op (both declare it)."""
        if cid is None:
            return []
        roles = self.strategy.roles.get(cid, [])
        if cid in self._derived_accel_body_ids() and "accel_source" not in roles:
            roles = [*roles, "accel_source"]
        return roles

    def _derived_accel_body_ids(self) -> frozenset:
        """Deck Pokémon whose ATTACK carries a bench-target energy-accel rider (`recoverTarget ==
        "bench"`, either zone: Turbo Flare deck-search, Aura Jab discard-recover) — the DERIVED
        bench-accelerator set (hypergeometric-fetch-closure §Round 9: derive from the card
        representation; the deck's `accel_source` Role declaration stays the override/confirm, never
        a parallel system). Self-target chargers (Regi Charge) are NOT bench accelerators. Memoised
        (deck-fixed). Empty without stats/deck."""
        if self._derived_accel_cache is None:
            ids = set()
            for cid in set(self.deck):
                st = self.stats.get(cid) if self.stats else None
                for aid in (getattr(st, "attacks", None) or ()):
                    ast = self._attack_stat(aid)
                    if (ast is not None and getattr(ast, "recoverN", 0)
                            and getattr(ast, "recoverTarget", None) == "bench"):
                        ids.add(cid)
                        break
            self._derived_accel_cache = frozenset(ids)
        return self._derived_accel_cache

    def _accel_recipient_missing(self, me: dict) -> bool:
        """True if my Active is a bench-accelerator (declared `accel_source` Role ∪ the DERIVED
        bench-accel-attack set, e.g. Cinderace's Turbo Flare) but NO Line member sits on my Bench to
        receive the accelerated Energy — so the accel attack would fire blanks. The trigger for
        developing a recipient first. False with no accel body Active or any Line member benched."""
        accel = ({cid for cid, r in self.strategy.roles.items() if "accel_source" in r}
                 | self._derived_accel_body_ids())
        ma = next((p for p in (me.get("active") or []) if p), None)
        if not (accel and ma and ma.get("id") in accel):
            return False
        members = self._line_member_set()
        return not any(b and b.get("id") in members for b in (me.get("bench") or []))

    # (Fetch doctrine greedy multi-pick + gap helpers are in doctrine_fetch.FetchMixin, above.)
    def _evolve_to_ready_wincon_available(self, me: dict) -> bool:
        """True if the win-condition is in hand AND a benched pre-evolution can become a READY attacker
        THIS turn — its Energy (which the evolved Pokémon inherits) PLUS the one manual attach you can
        still make this turn (a reusable Basic in hand) reaches the win-condition's cheapest attack cost.
        So at a promote it is worth bringing up that pre-evolution to evolve. False when the only
        pre-evolution stays bare even after that attach (no Energy on it AND none in hand) — evolving it
        would just expose a dead 0-Energy win-condition, so a staller/accelerator should be promoted
        instead (ep82753102 f120: bare Staryu, no Energy in hand -> Cinderace; ep82226116 f94: bare
        Staryu but a Water in hand -> evolve, the Mega comes online).

        The benched body must be the payoff's IMMEDIATE pre-evolution (one hop) — a Stage-0 Dreepy
        cannot become a Dragapult ex this turn no matter how much Energy it carries, yet the old
        any-pre-evo test said it could, so `promote-the-staller` stood down and the agent promoted a
        fragile bare Dreepy into the Active Spot (dragapult f31, CRITICAL)."""
        if not self._wincon_in_hand(me):
            return False
        preevos = self._payoff_immediate_preevo_set()   # IMMEDIATE pre-evo only — a deeper Stage-0 base is
        wincon = self._wincon_set()                      # >1 evolution from a ready attacker (dragapult f31)
        if not (preevos and wincon):
            return False
        thresh = min((_min_attack_cost(self.stats, w) for w in wincon), default=1)
        extra = 1 if self._has_reusable_energy(me.get("hand") or []) else 0   # one manual attach this turn
        return any(p and p.get("id") in preevos and len(p.get("energies") or []) + extra >= thresh
                   for p in (me.get("bench") or []))

    def _priority_wincon_slot(self, me: dict, active_lethal: bool,
                              active_doomed: bool = False) -> tuple | None:
        """(AreaType, index) of the ONE win-condition Pokémon to concentrate Energy on — among my
        win-condition bodies still short of their biggest attack (`_attach_target_under_max`), the one
        ALREADY carrying the most Energy (closest to firing its payoff hit). The Active is skipped when
        it can already Knock Out the opponent's Active (`active_lethal` — its turn is done, build the
        successor) OR when it is `active_doomed` (it won't survive to fire the payoff, so building it
        for the future is wasted — hand the Energy to a healthy benched wincon instead; a this-turn
        attack off the doomed Active is the Tactical/Planner layer's job, not this positional rule).
        So a powered/dying Active hands the Energy to the benched wincon. None when no buildable wincon
        exists (e.g. only the doomed Active is short) — concentrate then stands down. Backs
        `concentrate-energy-on-wincon` (load one attacker, don't spread; ep83116501 f89).

        EVOLUTION-DISTANCE AWARE (2026-07-10). The evolved payoff is preferred, but the slot also
        considers a Line PRE-EVOLUTION that has ALREADY BEEN STARTED (carries Energy) and is still short
        of the PAYOFF's cost — Energy carries through evolution (rules.md), so finishing a started pre-evo
        IS building the wincon. Without this, a board of pre-evos found nothing and
        `concentrate-energy-on-wincon` stood down, letting `power-up-attacker` spread: a 2nd {P} onto a
        bare Dreepy instead of finishing the started one (dragapult f85), and a whole hand of {F} onto a
        Meowth ex while the 1-Energy Riolu — already 'online' for its own 1-cost attack, so invisible to
        `attach_target_needs` — stayed one Energy short of Mega Brave (ml f84).

        A BARE pre-evo is deliberately NOT a slot: with nothing started there is nothing to concentrate,
        and claiming one would hijack the attach from a genuinely better target (ml f24, where the
        winning line attaches to Solrock and retreats into it)."""
        wincon = self._wincon_set()
        if not wincon:
            return None
        best = None                                  # (energy, area, index)
        active = (me.get("active") or [])
        if not active_lethal and not active_doomed:
            for i, p in enumerate(active):
                if p and p.get("id") in wincon and self._attach_target_under_max(p):
                    e = len(p.get("energies") or [])
                    if best is None or e > best[0]:
                        best = (e, _ACTIVE, i)
        for i, p in enumerate(me.get("bench") or []):
            if p and p.get("id") in wincon and self._attach_target_under_max(p):
                e = len(p.get("energies") or [])
                if best is None or e > best[0]:
                    best = (e, _BENCH, i)
        if best is not None:
            return (best[1], best[2])
        # Pass 2 (multi-stage lines): no win-condition BODY is buildable, so concentrate on the LINE
        # PRE-EVO closest to firing the payoff — the one carrying the MOST Energy while still short of
        # its payoff's biggest attack cost (Energy carries through evolution). Lets
        # `concentrate-energy-on-wincon` finish a started pre-evo instead of `power-up-attacker`
        # dribbling one Energy onto a bare body (dragapult f85). Inert where a win-condition body is in
        # play (Pass 1 wins) — so single-hop decks are unaffected in the common case. A BARE pre-evo
        # (e == 0) is deliberately excluded, so with nothing started the slot stands down and the attach
        # stays free for a genuinely better target (ml f24).
        zones = ((_ACTIVE, active if not (active_lethal or active_doomed) else []),
                 (_BENCH, me.get("bench") or []))
        best_pre = None                                    # (energy, area, index)
        for line in self._wincon_lines():
            payoff_stat = self.stats.get(line.payoff) if self.stats else None
            thresh = getattr(payoff_stat, "maxDamageCost", None) if payoff_stat else None
            if not thresh:
                continue
            preevos = {cid for cid in line.path if cid != line.payoff}
            for area, zone in zones:
                for i, p in enumerate(zone):
                    if p and p.get("id") in preevos:
                        e = len(p.get("energies") or [])
                        if 0 < e < thresh and (best_pre is None or e > best_pre[0]):
                            best_pre = (e, area, i)
        return (best_pre[1], best_pre[2]) if best_pre else None

    def _bench_wincon_ready(self, me: dict) -> bool:
        """True if a benched win-condition / primary attacker already carries enough Energy to attack
        (>= its cheapest attack cost) — a powered finisher worth retreating into."""
        wincon = self._wincon_set()
        if not wincon:
            return False
        return any(p and p.get("id") in wincon
                   and len(p.get("energies") or []) >= _min_attack_cost(self.stats, p.get("id"))
                   for p in (me.get("bench") or []))

    def _opp_cannot_punish_wincon(self, me: dict, opp: dict | None) -> bool:
        """ADR-0064 Decision 4: True when the opponent's reachable Incoming cannot KO my best benched
        win-condition next turn — the return-KO reachability veto behind the interpose / dont-promote
        stand-down (scenario 3: they literally can't afford to punish the exposed wincon, so
        `promote-the-ready-wincon` should win). **Matched-Read only** (Decision 4's safety direction):
        the veto fires solely behind a γ-matched Brief (`_incoming_budget` populated) — we expose a
        3-prize wincon only when we KNOW the archetype and its charged typed-affordability read says no
        lethal is reachable. Unmatched → False (fail CLOSED: keep interpose — under-counting their reach
        would feed them the wincon). Deliberately PESSIMISTIC even when matched (pool-forward evolution
        existence, `evo_min_energy` default 0), so a wincon is never exposed on a phantom-safety read."""
        if getattr(self, "_incoming_budget", None) is None:
            return False                                  # no matched Read → never expose on a guess
        slot = self._best_promote_slot(me)
        if slot is None or opp is None:
            return False
        idx = slot[1]
        bench = me.get("bench") or []
        wincon = bench[idx] if 0 <= idx < len(bench) else None
        if not (wincon and wincon.get("hp")):
            return False
        model = self._state_model
        if model is None:
            return False                                  # no snapshot → never expose on no read
        # AREA-AT-DAMAGE-TIME (ADR-0070 §9): the wincon is benched NOW, but every consumer of this
        # veto decides whether to EXPOSE it in the Active Spot (`interpose-...` stands down so
        # `promote-the-ready-wincon` wins; `dont-promote-into-their-prize-reach` stands down so the
        # promote goes through). So the opponent replies against it as the ACTIVE — the full printed
        # damage, not the bench riders. Declared explicitly: reading it as benched here would grant
        # phantom safety and expose a 3-prize wincon on a false read.
        #
        # Off the SNAPSHOT (POC-T1) with no `charged=`: the guard above already established that the
        # threaded policy IS `_incoming_budget`, so naming it again here would be a second copy of the
        # same decision — and the guard and the read could then drift apart.
        incoming = model.theirs.reachable_incoming(
            {"id": wincon.get("id"), "hp": wincon.get("hp")},
            context=self._opp_attack_context, my_benched=False)
        return incoming < wincon.get("hp")

    def _bench_wincon_prize_value(self, me: dict) -> int:
        """The greatest prize value among my BENCHED win-condition bodies (Mega ex 3 / ex 2 / else 1), 0 if
        none benched. At a forced promote it is the prize I keep OFF the front line by interposing a cheaper
        attacker (`interpose-the-cheap-attacker-to-preserve-the-wincon`)."""
        wincon = self._wincon_set()
        if not wincon:
            return 0
        return max((self._prize_value(p) for p in (me.get("bench") or [])
                    if p and p.get("id") in wincon), default=0)

    def _bench_wincon_underpowered(self, me: dict) -> bool:
        """True if a benched win-condition carries fewer Energy than its highest-damage attack costs
        (`CardStat.maxDamageCost`) — it can't yet fire its payoff hit. Promoting an accelerator (whose attack
        loads the Bench) rather than this finisher lets it reach full Energy off the Bench, which promoting it
        directly (one manual attach/turn) can't. False when every benched wincon is fully powered / costs unknown."""
        wincon = self._wincon_set()
        if not (wincon and self.stats):
            return False
        for p in (me.get("bench") or []):
            if not (p and p.get("id") in wincon):
                continue
            stat = self.stats.get(p.get("id"))
            cost = getattr(stat, "maxDamageCost", None) if stat else None
            if cost is not None and len(p.get("energies") or []) < cost:
                return True
        return False
