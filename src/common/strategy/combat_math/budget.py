"""The Attach BUDGET and the unit algebra it is paid in: what an Energy card supplies, which capacity
group it competes in, and whether a set of units covers a cost. Split out of `combat.py` so an
oracle family can price an attack without importing the oracle back."""
from __future__ import annotations


from dataclasses import dataclass, field
from itertools import combinations


_RECUR_RELOAD_CAP = 3      # max Basic Energy a `discard_energy_recur` line reloads from its OWN
                           # discard in one turn. VERIFIED in EN_Card_Data.csv: Mega Lucario ex 678's
                           # Aura Jab takes 3 Basic {F}, the strongest reload in the set.

DISCARD_SUPPLY = "discard"     # the shared capacity group every discard-drawing effect competes in

#: Colours ONE **Energy Unit** on a body can pay, keyed by its ``Pokemon.energies`` code (Issue #297).
#: Empty = WILD, EVERY colour and never "unknown". Only codes that do not pay their own colour.
_UNIT_COLOURS = {
    0: frozenset({0}),
    10: frozenset(),
    11: frozenset({5, 7}),
}

#: ``EnergyType.RAINBOW`` — a real enum member, not a sentinel, and the code this build gives an
#: Energy whose colour it cannot pin down; :func:`unit_colours` resolves it to the WILD (empty) set.
WILD_CODE = 10

def unit_colours(code) -> frozenset:
    """The colours ONE attached **Energy Unit** can pay, from its ``EnergyType`` code. An
    unrecognised code — a newer set's member — falls back to WILD, the same fail-OPEN direction."""
    if code in _UNIT_COLOURS:
        return _UNIT_COLOURS[code]
    return frozenset({code}) if isinstance(code, int) and 1 <= code <= 9 else frozenset()

def units_for_codes(codes) -> tuple:
    """``EnergyType`` UNIT codes as Budget units — the ONE translation from the ``energies``
    vocabulary into :class:`AttachUnit`, so attached and hypothetical Energy are typed by one rule."""
    return tuple(AttachUnit(unit_colours(code)) for code in codes)

@dataclass(frozen=True)
class AttachUnit:
    """ONE Energy unit that could sit on a body — the atom of the **Attach Budget**. Empty ``types``
    = ANY (fail-open); ``source="deck"`` marks the only UNCERTAIN zone and no check reads it."""
    types: frozenset = field(default_factory=frozenset)
    groups: tuple = ()
    source: str | None = None

@dataclass(frozen=True)
class Budget:
    """This turn's full attach capacity toward ONE body (ADR-0067). Affordability asks whether ANY
    ``options`` set pays; ``caps`` make a set jointly infeasible, so read :attr:`size`, never ``len``."""
    options: tuple = ((),)
    caps: dict = field(default_factory=dict)

    @property
    def size(self) -> int:
        """Units the best option can SIMULTANEOUSLY realise under ``caps``. Raw units over-report:
        two Wondrous Patches over a single {P} in the discard are two units but one attach."""
        return max((self._realisable(option) for option in self.options), default=0)

    def realising_p(self, slots, p_by_type: dict, attached=()) -> float:
        """P(this Budget actually pays ``slots``) — the Probability Leg over the assignment the
        payment really uses (ADR-0074 decision 3). Distinct deck-sourced TYPES, not units."""
        if not slots:
            return 1.0
        best = 0.0
        for option in self.options:
            p = _pay_best_p(tuple(slots), tuple(attached) + tuple(option), self.caps, p_by_type)
            if p > best:
                best = p
                if best >= 1.0:
                    break                          # certain — no assignment can beat it
        return best

    def _realisable(self, units) -> int:
        n = len(units)
        while n > 0 and not _can_pay((0,) * n, units, self.caps):
            n -= 1
        return n

@dataclass(frozen=True)
class _AttachCtx:
    """Per-decision zone facts the clause interpreter reads (never board objects). The two Energy
    zones differ by PRECISION on purpose (ADR-0067): hidden deck = type SET, public discard = COUNT."""
    deck: frozenset = field(default_factory=frozenset)
    discard: dict = field(default_factory=dict)
    benched: bool = False
    more_prizes: bool = False

    def source_types(self, source) -> frozenset:
        """Energy types a clause's SOURCE zone can supply; empty for an unmodelled one (fail-CLOSED)."""
        if source == "deck":
            return self.deck
        if source == "discard":
            return frozenset(t for t, n in self.discard.items() if n > 0)
        return frozenset()

    def condition_met(self, condition) -> bool:
        """A clause's play CONDITION; False for an unmodelled one (fail-CLOSED)."""
        return {"more_prizes_remaining_than_opp": self.more_prizes}.get(condition, False)

@dataclass(frozen=True)
class _Contribution:
    """What one playable hand card offers: units it attaches BY ITS EFFECT, units it merely puts in
    HAND (the manual attach must play those), and the per-card ``cap`` its own group is policed by."""
    is_supporter: bool
    effect_units: tuple
    hand_yields: tuple
    group: object = None
    cap: dict = field(default_factory=dict)

def _pay_best_p(slots, units, caps, p_by_type: dict) -> float:
    """Max over feasible assignments of the product of ``p_by_type`` over the DECK-sourced types
    consumed (ADR-0074). Mirrors :func:`_can_pay`'s matcher exactly, so the two cannot disagree."""
    caps = caps or {}
    if len(units) < len(slots):
        return 0.0
    ordered = sorted(slots, key=lambda s: s in (0, None))

    def assign(index, used, spent, taken: frozenset, running: float) -> float:
        if running <= 0.0:
            return 0.0
        if index == len(ordered):
            return running
        want = ordered[index]
        best = 0.0
        for j, unit in enumerate(units):
            if used & (1 << j):
                continue
            if want not in (0, None):
                if unit.types and want not in unit.types:
                    continue
                choices = (want,)
            else:
                choices = tuple(sorted(unit.types)) or (None,)
            for chosen in choices:
                charged, blocked = spent, False
                for group in unit.groups:
                    key = (group, chosen)
                    if charged.get(key, 0) >= caps.get(group, {}).get(chosen, 0):
                        blocked = True
                        break
                    charged = {**charged, key: charged.get(key, 0) + 1}
                if blocked:
                    continue
                nxt, nrun = taken, running
                if unit.source == "deck" and chosen is not None and chosen not in taken:
                    nxt = taken | {chosen}         # each deck TYPE priced once, not per unit
                    nrun = running * float(p_by_type.get(chosen, 0.0))
                got = assign(index + 1, used | (1 << j), charged, nxt, nrun)
                if got > best:
                    best = got
                    if best >= 1.0:
                        return best                # certain — cannot be beaten
        return best

    return assign(0, 0, {}, frozenset(), 1.0)

def _can_pay(slots, units, caps=None) -> bool:
    """Can ``units`` cover the per-slot cost ``slots`` (EnergyType codes; 0 = colourless)? Exact.
    Colourless slots are charged too — an Energy paying one still leaves the pile. Fail-CLOSED."""
    caps = caps or {}
    if len(units) < len(slots):
        return False
    ordered = sorted(slots, key=lambda s: s in (0, None))

    def assign(index, used, spent):
        if index == len(ordered):
            return True
        want = ordered[index]
        for j, unit in enumerate(units):
            if used & (1 << j):
                continue
            if want not in (0, None):
                if unit.types and want not in unit.types:
                    continue
                choices = (want,)
            else:
                choices = tuple(sorted(unit.types)) or (None,)
            for chosen in choices:
                charged, blocked = spent, False
                for group in unit.groups:
                    key = (group, chosen)
                    if charged.get(key, 0) >= caps.get(group, {}).get(chosen, 0):
                        blocked = True
                        break
                    charged = {**charged, key: charged.get(key, 0) + 1}
                if not blocked and assign(index + 1, used | (1 << j), charged):
                    return True
        return False

    return assign(0, 0, {})

def _matched_slots(slots, units, caps=None) -> int:
    """How many of ``slots`` ``units`` can SIMULTANEOUSLY pay (ADR-0069 §3). Defined AS a subset
    search over :func:`_can_pay` so "fits" and "reaches" can never be two different matchers."""
    n = len(slots)
    if n == 0 or not units:
        return 0
    for k in range(min(n, len(units)), 0, -1):
        for subset in combinations(range(n), k):
            if _can_pay(tuple(slots[i] for i in subset), units, caps):
                return k
    return 0
