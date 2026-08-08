"""Printed card facts and the damage arithmetic over them: what an attack costs, what it deals, what
a body yields in prizes, what riders it carries. Every Weakness/Resistance adjustment goes through
the pure `damage.py` seam — this module reads the stats and hands them over."""
from __future__ import annotations


from common.strategy.damage import compute_active_damage, wr_adjust



class CardFactsMixin:
    """Card facts and the damage arithmetic over them (the Stat Provider seam, ADR-0056)."""

    def attack_stat(self, attack_id):
        if self.stats is None:
            return None
        return getattr(self.stats, "attack", lambda _aid: None)(attack_id)

    def attack_cost(self, attack_id, default=99):
        """``default`` when no record resolves; 99 is the fail-CLOSED sentinel."""
        st = self.attack_stat(attack_id)
        return st.cost if st is not None else default

    def attack_damage(self, attack_id) -> int:
        st = self.attack_stat(attack_id)
        return st.damage if st is not None else 0

    def _card_stat(self, card_id):
        return self.stats.get(card_id) if (self.stats and card_id is not None) else None

    def _grant(self, poke: dict | None) -> dict | None:
        if self._transients is None:
            return None
        return self._transients.grant_for_serial((poke or {}).get("serial"))

    def predicted_damage(self, attacker_id: int | None, attack_id, defender: dict | None, *,
                         bound: str = "exact", context: dict | None = None) -> float:
        """The damage oracle (ADR-0032 E1) — the ONE closed-form path every Tier-0 damage estimate
        routes through. ``bound`` picks a conditional attack's floor/ceiling/printed."""
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
        """The worst damage ``attacker_stat``'s attacks deal to ``defender`` — per-attack when EVERY
        record resolves, else card-level. Does NOT filter by the opponent's Energy: over-estimate."""
        if not attacker_stat:
            return 0
        aids = tuple(a for a in (attacker_stat.attacks or ()) if a != exclude_attack)
        if aids and all(self.attack_stat(a) is not None for a in aids):
            # Incoming is the WORST case: a conditional attack threatens its ceiling.
            return max(self.predicted_damage(attacker_stat.cardId, a, defender, bound="max",
                                             context=context)
                       for a in aids)
        return self.card_level_damage(attacker_stat, defender, context=context)

    def card_level_damage(self, attacker_stat, defender: dict | None = None, *,
                          context: dict | None = None) -> float:
        """The ONE card-level damage fallback, for a body whose attack table is unavailable:
        ``maxDamage`` x W/R, max'd with the hand-size scaler. The counter leg skips W/R by rule."""
        if not attacker_stat:
            return 0
        d_stat = self._card_stat((defender or {}).get("id"))
        printed = wr_adjust(attacker_stat, d_stat, attacker_stat.maxDamage or 0)
        hand = (context or {}).get("atk_hand") or 0
        return max(printed, (getattr(attacker_stat, "handSizeDamage", 0) or 0) * hand)

    def threat_ceiling(self, card_id, *, context: dict | None = None) -> int:
        """How dangerous this body is on the CURRENT board. Deliberately DEFENDER-FREE and W/R-free
        — folding a defender in would swing the snipe order on my own Active's typing."""
        return int(self.predicted_max_damage(self._card_stat(card_id), None, context=context))

    def forward_threat_ceiling(self, card_id, *, context: dict | None = None) -> int:
        """The greatest :meth:`threat_ceiling` among the forms this line evolves INTO — what makes an
        Evolving Threat readable, where the printed forward index reads Alakazam at 10."""
        return max((self.threat_ceiling(fid, context=context)
                    for fid in self.forward_card_ids(card_id)), default=0)

    def prize_value(self, poke: dict | None) -> int:
        """Prizes a knockout yields — Mega ex 3, ex 2, else 1 (ADR-0056); 1 for an unknown body."""
        stat = self._card_stat((poke or {}).get("id"))
        return stat.prize_value if stat else 1

    def is_tera(self, card_id) -> bool:
        """A Tera Pokémon takes NO damage while BENCHED, so no bench-snipe/spread math may credit
        damage there. Fail-OPEN (False) without stats: a phantom snipe prize could lock a false Lethal."""
        st = self._card_stat(card_id)
        return bool(getattr(st, "tera", False))

    def rider_snipe(self, attack_id) -> int:
        st = self.attack_stat(attack_id)
        return st.benchSnipe if st else 0

    def rider_spread(self, attack_id) -> int:
        st = self.attack_stat(attack_id)
        return st.benchSpread if st else 0

    def rider_recoil(self, attack_id) -> int:
        """The attack's unconditional self-damage (0 unknown). Read by the simultaneous-draw guard
        (ADR-0022 #2 — recoil that KOs my own Active makes a "win" a DRAW) and `_recoil_flips_doom`."""
        st = self.attack_stat(attack_id)
        return st.recoil if st else 0

    def forward_card_ids(self, card_id) -> frozenset:
        """Card ids this line evolves INTO; empty with no provider / dead end / unknown id."""
        fci = getattr(self.stats, "forward_card_ids", None)
        return fci(card_id) if (fci is not None and card_id is not None) else frozenset()
