"""The printed card facts and the damage arithmetic over them: what an attack costs, what it deals, what a body yields in
prizes, and what riders it carries.

Every Weakness / Resistance adjustment goes through the pure `damage.py` seam — this module reads the stats and hands
them over, it never re-derives the formula."""
from __future__ import annotations


from common.strategy.damage import compute_active_damage, wr_adjust



class CardFactsMixin:
    """Card-level facts and the damage arithmetic over them."""

    # --- record access (the Stat Provider seam, ADR-0056) ------------------------------
    def attack_stat(self, attack_id):
        """The attack's ``AttackStat`` off the provider; None unknown / stat-blind."""
        if self.stats is None:
            return None
        return getattr(self.stats, "attack", lambda _aid: None)(attack_id)

    def attack_cost(self, attack_id, default=99):
        """The attack's Energy count; ``default`` when no record resolves (99 = fail-closed)."""
        st = self.attack_stat(attack_id)
        return st.cost if st is not None else default

    def attack_damage(self, attack_id) -> int:
        """The attack's printed damage; 0 for an unknown attack."""
        st = self.attack_stat(attack_id)
        return st.damage if st is not None else 0

    def _card_stat(self, card_id):
        return self.stats.get(card_id) if (self.stats and card_id is not None) else None

    def _grant(self, poke: dict | None) -> dict | None:
        """The live transient grant on a body (serial-gated), or None."""
        if self._transients is None:
            return None
        return self._transients.grant_for_serial((poke or {}).get("serial"))

    # --- the damage core ----------------------------------------------------------------
    def predicted_damage(self, attacker_id: int | None, attack_id, defender: dict | None, *,
                         bound: str = "exact", context: dict | None = None) -> float:
        """The damage oracle (ADR-0032 E1): damage ``attack_id`` deals to the defending Active —
        the ONE closed-form path every Tier-0 damage estimate routes through. Resolves ids to
        stats/tags, then delegates to the pure ``compute_active_damage`` (the unit the engine
        audit diffs). Honors the attack's ignore flags: Nebula Beam lands 210 through Crustle's
        ex-prevention; Jetting Blow is zeroed (its bench rider is a separate path). ``bound``
        picks a conditional attack's floor/ceiling/printed — Lethal reads "min", Incoming "max"."""
        d_id = (defender or {}).get("id")
        return compute_active_damage(
            self.attack_stat(attack_id),
            self._card_stat(attacker_id),
            self._card_stat(d_id),
            frozenset(self.functions.tags(d_id)) if (self.functions and d_id is not None)
            else frozenset(),
            bound=bound, context=context,
            defender_transient=self._grant(defender))

    def predicted_max_damage(self, attacker_stat, defender: dict | None, *,
                             exclude_attack=None, context: dict | None = None) -> float:
        """The worst damage ``attacker_stat``'s attacks deal to ``defender`` — max over the
        per-attack oracle when EVERY attack's record resolves (a partially-known table never
        SHRINKS a worst case), else the card-level ``maxDamage`` x W/R (``wr_adjust`` — the one
        card-level rule). ``context`` prices the attacker's scalers (the opponent-context dict
        the Pilot stashes per decision — hand size, bench, attached Energy, open discard).

        NOTE: does NOT filter by the opponent's Energy affordability — the Incoming estimate
        assumes the opponent can power its biggest attack (conservative over-estimate; see
        docs/todo/incoming-affordability.md before changing this)."""
        if not attacker_stat:
            return 0
        aids = tuple(a for a in (attacker_stat.attacks or ()) if a != exclude_attack)
        if aids and all(self.attack_stat(a) is not None for a in aids):
            # bound="max": Incoming is the WORST case — a coin/conditional attack threatens its
            # ceiling ("If heads, +20" counts the 20), so survival math never under-plans
            return max(self.predicted_damage(attacker_stat.cardId, a, defender, bound="max",
                                             context=context)
                       for a in aids)
        return self.card_level_damage(attacker_stat, defender, context=context)

    def card_level_damage(self, attacker_stat, defender: dict | None = None, *,
                          context: dict | None = None) -> float:
        """The ONE card-level damage fallback — used when no per-attack record resolves.

        ``maxDamage`` x Weakness/Resistance (the single card-level rule), max'd with the hand-size
        scaler's ``handSizeDamage`` x the attacker's hand. Counter placement is not "damage", so
        that leg deliberately skips W/R.

        Exists because both fallback paths used to hand-roll the hand-size leg themselves and did
        it differently: the Threat-Clock form enumeration credited it as an EITHER/OR against the
        printed roll-up, while the incoming read added it unconditionally beside the per-attack
        oracle. One fact, two hand-rolled call sites, free to drift — and they did.

        The per-attack path prices the hand-size attack through the Damage Formula's ``atk_hand``
        scaler, so this fallback exists only for a body whose attack table is unavailable (a
        partial provider). It reads the hand STRAIGHT from ``context``, without the "a card is
        spent to evolve" decrement the old forward-only branch applied: one representation beats
        two, and reading the full hand is the pessimistic direction on a survival read.
        """
        if not attacker_stat:
            return 0
        d_stat = self._card_stat((defender or {}).get("id"))
        printed = wr_adjust(attacker_stat, d_stat, attacker_stat.maxDamage or 0)
        hand = (context or {}).get("atk_hand") or 0
        return max(printed, (getattr(attacker_stat, "handSizeDamage", 0) or 0) * hand)

    def threat_ceiling(self, card_id, *, context: dict | None = None) -> int:
        """How dangerous this body is on the CURRENT board — its biggest attack priced through the
        Damage Formula (printed base + ``per_unit x count(variable)``), 0 when unknown.

        Deliberately DEFENDER-FREE and Weakness/Resistance-free, exactly like the ``maxDamage`` it
        replaces in the threat rank: it answers "how dangerous is this body", not "how much does it
        hit my current Active for". Folding a defender in would make the snipe order swing on my
        own Active's typing, and the Evolving Threat signal is deck-agnostic by construction.

        Fail-safe on an unknown variable: a scaler whose variable is absent from ``context``
        contributes 0, leaving the printed base — never a crash, never an invented count.

        Defender-free is expressed by passing NO defender to :meth:`predicted_max_damage`, rather
        than by re-deriving its per-attack-else-card-level rule here: two copies of that rule are
        free to drift, which is the exact failure :meth:`card_level_damage` was extracted to end.
        """
        return int(self.predicted_max_damage(self._card_stat(card_id), None, context=context))

    def forward_threat_ceiling(self, card_id, *, context: dict | None = None) -> int:
        """The greatest :meth:`threat_ceiling` among the forms this body's line evolves INTO — the
        board-priced counterpart of the provider's printed-only forward index. 0 for a dead-end
        line or an unknown id.

        This is what makes an Evolving Threat readable: a pre-evolution's own printed damage says
        nothing about the attacker its line reaches, and the printed forward index reads Alakazam
        at 10 because its whole threat lives in a scaling term.
        """
        return max((self.threat_ceiling(fid, context=context)
                    for fid in self.forward_card_ids(card_id)), default=0)

    # --- card-tier combat facts -----------------------------------------------------------
    def prize_value(self, poke: dict | None) -> int:
        """Prizes a knockout of this body yields — Mega ex 3, ex 2, else 1 (the record's own
        question, ADR-0056); 1 for an unknown body."""
        stat = self._card_stat((poke or {}).get("id"))
        return stat.prize_value if stat else 1

    def is_tera(self, card_id) -> bool:
        """A Tera Pokémon — takes NO damage from attacks while BENCHED (engine ``CardData.tera``),
        so no bench-snipe/spread math may ever credit damage against it there. Fail-open (False)
        without stats: a phantom snipe-prize vs Tera could lock a false Lethal."""
        st = self._card_stat(card_id)
        return bool(getattr(st, "tera", False))

    def rider_snipe(self, attack_id) -> int:
        """The attack's unconditional bench-snipe rider damage (0 unknown)."""
        st = self.attack_stat(attack_id)
        return st.benchSnipe if st else 0

    def rider_spread(self, attack_id) -> int:
        """The attack's distributable opp-bench spread total (0 unknown)."""
        st = self.attack_stat(attack_id)
        return st.benchSpread if st else 0

    def rider_recoil(self, attack_id) -> int:
        """The attack's unconditional self-damage (0 unknown).

        Read by the simultaneous-draw guard (ADR-0022 #2 — recoil that KOs my own Active turns a
        "win" into a DRAW) and by `_recoil_flips_doom` (a non-KO recoil that hands them a free KO).
        Was UNCONSUMED until POC-T1 (Issue #260) deleted the Pilot's byte-identical private copy and
        re-pointed both callers here — the ADR-0052 consolidation this and its two siblings were
        always meant to be the one home for."""
        st = self.attack_stat(attack_id)
        return st.recoil if st else 0

    # --- Incoming (worst-case, opponent-static — the survival reads) ------------------------
    def forward_card_ids(self, card_id) -> frozenset:
        """Card ids the body's evolution line evolves INTO (the provider primitive; empty when
        no provider / dead-end / unknown id)."""
        fci = getattr(self.stats, "forward_card_ids", None)
        return fci(card_id) if (fci is not None and card_id is not None) else frozenset()
