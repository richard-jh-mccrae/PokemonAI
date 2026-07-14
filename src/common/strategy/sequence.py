"""ORACLE: Horizon-2 attack sequence — ADR-0061. A locking attack's value includes its FORCED
follow-up.

42 attacks in the pool carry a next-turn lock (`AttackStat.nextTurnSelfLock` /
`nextTurnSameAttackLock`), and they are two structurally different things:

- **SAME-ATTACK lock** — *"During your next turn, this Pokémon can't use Mega Brave."* Mega Lucario ex
  has Mega Brave (270, {F}{F}) and Aura Jab (130, {F}). **270 + 130 == 130 + 270.** You can never Mega
  Brave twice in a row whichever you open with, so the lock forbids nothing the other ordering would
  have had: over two turns it costs **zero damage**.
- **FULL lock** — *"During your next turn, this Pokémon can't use attacks."* Blood Moon (240) then
  **nothing** = 240, which LOSES to a lock-free 130/turn attacker's 260. Here the lock costs an entire
  turn of offense — 130 to 280 points, depending on the alternative.

`_LOCK_COST = 40` charged one flat constant for both: a phantom charge on the first, a 5× under-charge
on the second.

**This is multi-turn reasoning without a search.** When an attack locks, next turn's option set is not
a branching space to explore — it is *forced and known*: a full lock means this Pokémon deals 0, a
same-attack lock means next turn is its best OTHER attack. So the sequence is evaluated, not searched.
That is the shape that has shipped here four times (ADR-0039 gamble lines, ADR-0040 objectives,
ADR-0044 opponent-choice reads, the Lethal Solver); the one actual tree — Tier-6 escalation — lost 12
points and stays parked.
"""
from __future__ import annotations


def followup_damage(attack_id, *, affordable: dict, full_lock: bool,
                    same_attack_lock: bool) -> int:
    """Damage this Pokémon can still deal NEXT turn, having used `attack_id` this turn.

    `affordable` is ``{attack_id: damage}`` over the attacks the Active can actually pay for — an
    attack we cannot fund is not a follow-up. Returns 0 when nothing is left (a full lock, or a
    same-attack lock on a Pokémon whose only attack is the locked one); the CALLER must still let a
    lone chip beat passing, exactly as `_lock_cost_applies` never charged the only affordable attack.
    """
    if full_lock:
        return 0                                     # "can't use attacks": the turn is simply gone
    if same_attack_lock:
        return max((d for a, d in affordable.items() if a != attack_id), default=0)
    return max(affordable.values(), default=0)       # no lock: the whole menu is still there


def sequence_damage(this_turn: int | float, followup: int | float, *, weight: float) -> float:
    """Two-turn damage: what this attack deals now, plus the forced follow-up it leaves behind.

    `weight` < 1 discounts the follow-up. Damage THIS turn is certain; next turn's is not — the
    opponent moves in between (they can KO us, heal, or switch the target away). So when two lines
    deal the same total, the front-loaded one wins, which is the right default.

    Pass ``followup=0`` when the Active is `active_doomed`: there IS no next turn for this Pokémon,
    so the follow-up never materialises and every lock is free.
    """
    return this_turn + weight * followup
