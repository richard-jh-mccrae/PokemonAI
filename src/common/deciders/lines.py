"""The win-condition LINES: which cards form them, which member is missing, which slot is the priority, and whether
the payoff can still be reached.

A Line is the deck's own declaration (`Strategy.lines`); everything here reads it rather than inferring intent."""
from __future__ import annotations


from common.deciders.plan_choice import _min_attack_cost
from common.strategy.context import _ACTIVE, _BENCH



class LineMixin:
    """The win-condition lines and their in-play state."""

    def _wincon_lines(self) -> list:
        """Declared Lines whose payoff IS the win-condition — never a `secondary_attacker` Line (ADR-0048).
        The whole win-condition machinery is scoped to these."""
        return [l for l in self.strategy.lines if getattr(l, "role", "win_condition") == "win_condition"]

    def _wincon_set(self) -> set:
        """Card ids that ARE the win-condition: a `_wincon_lines` payoff, or a `win_condition` /
        `primary_attacker` Role. Match-invariant, so memoised — `_context` reads it per option."""
        cached = getattr(self, "_wincon_set_cache", None)
        if cached is not None:
            return cached
        wincon = {line.payoff for line in self._wincon_lines()}
        wincon |= {cid for cid, r in self.strategy.roles.items()
                   if {"win_condition", "primary_attacker"} & set(r)}
        self._wincon_set_cache = wincon
        return wincon

    def _wincon_prize_value(self) -> int:
        """Greatest prize value among my declared win-condition bodies (ADR-0048); 0 if none."""
        wincon = self._wincon_set()
        return max((self._prize_value({"id": c}) for c in wincon), default=0) if wincon else 0

    def _wincon_in_hand(self, me: dict) -> bool:
        """Is the win-condition card already in my hand — so a tutor needn't dig for another?"""
        wincon = self._wincon_set()
        return bool(wincon) and any(c and c.get("id") in wincon for c in (me.get("hand") or []))

    def _wincon_in_hand_undeployable(self, me: dict) -> bool:
        """An EVOLUTION wincon in hand with NO base to deploy it: not in play, its Line HAS a pre-evolution,
        and none sits in play or hand. Dead this turn — `hold-wincon-dont-shuffle` must let it go."""
        if not (self._wincon_in_hand(me) and not self._wincon_in_play(me)):
            return False
        if not self._line_preevo_set():                    # Basic-payoff wincon — benchable, keep it
            return False
        return not (self._line_preevo_in_play(me) or self._line_preevo_in_hand(me))

    def _wincon_in_play(self, me: dict) -> bool:
        """Is my win-condition already on my Active or Bench — so a fetch Hypothesis can stand down?"""
        wincon = {line.payoff for line in self.strategy.lines}
        wincon |= {cid for cid, r in self.strategy.roles.items()
                   if {"win_condition", "primary_attacker"} & set(r)}
        if not wincon:
            return False
        board = (me.get("active") or []) + (me.get("bench") or [])
        return any(p and p.get("id") in wincon for p in board)

    def _wincon_payoff_ids(self) -> frozenset:
        """The deck's declared WIN-CONDITION Line payoffs — the Opener Marginal's gate (ADR-0081 A). NOT
        `_wincon_set`, which also unions in every ROLE-tagged body: broader than ADR-0081 d4 allows."""
        cached = getattr(self, "_wincon_payoff_cache", None)
        if cached is not None:
            return cached
        payoffs = frozenset(p for p in (getattr(ln, "payoff", None) for ln in self._wincon_lines())
                            if p is not None)
        self._wincon_payoff_cache = payoffs
        return payoffs

    def _line_preevo_set(self) -> set:
        """Non-payoff members of a WIN-CONDITION Line's path. NARROW by design — a secondary-attacker Line's
        base is NOT in it (the broadened, credit-giving set is `_recognized_line_preevo_set`). Memoised."""
        cached = getattr(self, "_line_preevo_cache", None)
        if cached is not None:
            return cached
        self._line_preevo_cache = {cid for line in self._wincon_lines()
                                   for cid in line.path if cid != line.payoff}
        return self._line_preevo_cache

    def _recognized_line_preevo_set(self) -> set:
        """Pre-evolutions of EVERY declared attacker Line — win-condition AND secondary (ADR-0048). Read only
        by the preference rungs. Falls back to the narrow set when the kill-switch is OFF. Memoised."""
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
        """Is my Active a wincon-line pre-evo far below what it evolves into? 'Weak' = own maxDamage under half
        the forward form's max, so a real-attacker pre-evo still keeps its Energy. FAIL-CLOSED on unknowns."""
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
        """Is a Line pre-evolution on my Active/Bench — so a rush-evolve tutor has something to evolve?"""
        preevos = self._line_preevo_set()
        if not preevos:
            return False
        board = (me.get("active") or []) + (me.get("bench") or [])
        return any(p and p.get("id") in preevos for p in board)

    def _line_preevo_in_hand(self, me: dict) -> bool:
        """The hand-side companion of `_line_preevo_in_play`."""
        preevos = self._line_preevo_set()
        if not preevos:
            return False
        return any(c and c.get("id") in preevos for c in (me.get("hand") or []))

    def _successor_evolvable_now(self, me: dict, cid) -> bool:
        """Can payoff ``cid``, held in HAND, legally evolve a body in play **this turn**? Both clauses matter:
        an `evolvesFrom` name match AND not `appearThisTurn` (`docs/rules.md` §4)."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        base = getattr(st, "evolvesFrom", None) if st is not None else None
        if not base:
            return False
        bodies = (me.get("active") or []) + (me.get("bench") or [])
        return any(b and not b.get("appearThisTurn")
                   and getattr(self.stats.get(b.get("id")), "name", None) == base
                   for b in bodies)

    def _line_readiness_deadline(self, me: dict, cid) -> int:
        """How soon a held wincon comes online, as the deadline the refresh-SHED window clamps to: base in play
        AND powered = 1, base unpowered = 2, no base in play = 99 (latent, re-fetchable). Fail-open to 99."""
        if cid is None:
            return 99
        board = [p for p in ((me.get("active") or []) + (me.get("bench") or [])) if p]
        bases = [p for p in board if cid in self._forward_card_ids(p.get("id"))]
        if not bases:
            return 99
        return 1 if any(p.get("energies") for p in bases) else 2

    def _bench_line_member_needs(self, me: dict) -> bool:
        """Does a BENCHED body on a win-condition Line's path still need Energy for its cheapest attack — an
        un-powered line waiting on the bench? Role-gated, so decks without a declared Line never trip it."""
        members = self._line_member_set()
        if not members:
            return False
        return any(p and p.get("id") in members and self._attach_target_needs(p)
                   for p in (me.get("bench") or []))

    def _line_member_set(self) -> set:
        """Every card id on a WIN-CONDITION Line's path — pre-evolutions AND the payoff. The bodies a bench
        accelerator can usefully load; scoped so a secondary Line never redirects the recipient hunt."""
        return {cid for line in self._wincon_lines() for cid in line.path}

    def _payoff_immediate_preevo_set(self) -> set:
        """Path members ONE hop below a payoff. For a single-hop Line this equals `_line_preevo_set`; for a
        multi-stage one it is only the Stage 1 (Drakloak), never the Stage-0 base (Dreepy)."""
        out = set()
        for line in self._wincon_lines():
            path = line.path or []
            if line.payoff in path:
                i = path.index(line.payoff)
                if i > 0:
                    out.add(path[i - 1])
        return out

    def _payoff_immediate_preevo_available(self, me: dict) -> bool:
        """Is a payoff's IMMEDIATE pre-evolution in play OR hand — the payoff exactly one evolution from
        deployable? False on a multi-stage Line while only a deeper base is around."""
        imm = self._payoff_immediate_preevo_set()
        if not imm:
            return False
        zones = (me.get("active") or []) + (me.get("bench") or []) + (me.get("hand") or [])
        return any(p and p.get("id") in imm for p in zones)

    def _roles_of(self, cid) -> list:
        """The deck-DECLARED Roles plus the DERIVED `accel_source` for a body whose attack carries a
        bench-target accel rider — derivation-first, declaration as the confirm/override."""
        if cid is None:
            return []
        roles = self.strategy.roles.get(cid, [])
        if cid in self._derived_accel_body_ids() and "accel_source" not in roles:
            roles = [*roles, "accel_source"]
        return roles

    def _derived_accel_body_ids(self) -> frozenset:
        """Deck Pokémon whose ATTACK carries a bench-target energy-accel rider (``recoverTarget == "bench"``).
        Self-target chargers are NOT bench accelerators. Memoised; empty without stats/deck."""
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
        """Is my Active a bench-accelerator with NO Line member benched to receive the Energy — so the accel
        attack would fire blanks? The trigger for developing a recipient first."""
        accel = ({cid for cid, r in self.strategy.roles.items() if "accel_source" in r}
                 | self._derived_accel_body_ids())
        ma = next((p for p in (me.get("active") or []) if p), None)
        if not (accel and ma and ma.get("id") in accel):
            return False
        members = self._line_member_set()
        return not any(b and b.get("id") in members for b in (me.get("bench") or []))

    def _evolve_to_ready_wincon_available(self, me: dict) -> bool:
        """Is the wincon in hand AND a benched pre-evo able to become a READY attacker THIS turn — inherited
        Energy plus one manual attach reaching its cheapest cost? IMMEDIATE pre-evo only: one hop, not two."""
        if not self._wincon_in_hand(me):
            return False
        preevos = self._payoff_immediate_preevo_set()   # IMMEDIATE pre-evo only — a deeper Stage-0 base is
        wincon = self._wincon_set()                      # more than one evolution from a ready attacker
        if not (preevos and wincon):
            return False
        thresh = min((_min_attack_cost(self.stats, w) for w in wincon), default=1)
        extra = 1 if self._has_reusable_energy(me.get("hand") or []) else 0   # one manual attach this turn
        return any(p and p.get("id") in preevos and len(p.get("energies") or []) + extra >= thresh
                   for p in (me.get("bench") or []))

    def _priority_wincon_slot(self, me: dict, active_lethal: bool,
                              active_doomed: bool = False) -> tuple | None:
        """(AreaType, index) of the ONE win-condition to concentrate Energy on — of those short of their biggest
        attack, the one carrying the most. A BARE pre-evo is NOT a slot: nothing started, nothing to concentrate.

        A cheap Active attack taking this turn's Knock Out does not finish that body's build.  Exclude
        it only when it is doomed; otherwise spreading to a bare backup throws away progress toward
        the stronger attack on the surviving primary.
        """
        wincon = self._wincon_set()
        if not wincon:
            return None
        best = None                                  # (energy, area, index)
        active = (me.get("active") or [])
        if not active_doomed:
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
        # Pass 2 (multi-stage lines): no win-condition BODY is buildable, so concentrate on the LINE PRE-EVO
        # carrying the MOST Energy while still short of its payoff's biggest attack cost.
        zones = ((_ACTIVE, active if not active_doomed else []),
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
        """Does a benched wincon already carry its cheapest attack cost — a powered finisher to retreat into?"""
        wincon = self._wincon_set()
        if not wincon:
            return False
        return any(p and p.get("id") in wincon
                   and len(p.get("energies") or []) >= _min_attack_cost(self.stats, p.get("id"))
                   for p in (me.get("bench") or []))

    def _opp_cannot_punish_wincon(self, me: dict, opp: dict | None) -> bool:
        """ADR-0064 Decision 4: can the opponent's reachable Incoming NOT KO my best benched wincon next turn?
        **Matched-Read only** — unmatched fails CLOSED, since under-counting their reach feeds them the wincon."""
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
        # AREA-AT-DAMAGE-TIME (ADR-0070 §9): every consumer decides whether to EXPOSE this body in the Active
        # Spot, so they reply against it as the ACTIVE — full printed damage, not the bench riders.
        incoming = model.theirs.reachable_incoming(
            {"id": wincon.get("id"), "hp": wincon.get("hp")},
            context=self._opp_attack_context, my_benched=False)
        return incoming < wincon.get("hp")

    def _bench_wincon_prize_value(self, me: dict) -> int:
        """Greatest prize value among my BENCHED wincons, 0 if none — the prize interposing keeps off the
        front line."""
        wincon = self._wincon_set()
        if not wincon:
            return 0
        return max((self._prize_value(p) for p in (me.get("bench") or [])
                    if p and p.get("id") in wincon), default=0)

    def _bench_wincon_underpowered(self, me: dict) -> bool:
        """Does a benched wincon carry fewer Energy than its ``maxDamageCost`` — so an accelerator promote can
        power it off-Bench, which promoting the finisher directly cannot?"""
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
