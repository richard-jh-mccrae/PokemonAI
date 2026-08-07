"""The Attach BUDGET and the unit algebra it is paid in: what an Energy card supplies, which capacity group it competes
in, and whether a set of units covers a cost.

Split out of `combat.py` so an oracle family can price an attack without importing the oracle back."""
from __future__ import annotations


from dataclasses import dataclass, field
from itertools import combinations


_RECUR_RELOAD_CAP = 3      # the max Basic Energy a `discard_energy_recur` line reloads from its OWN
                           # discard in one turn — VERIFIED at source (EN_Card_Data.csv): Mega Lucario
                           # ex 678 Aura Jab up to 3 Basic {F}; Archaludon ex 190 Assemble Alloy up to
                           # 2 Basic {M}. Bounds the discard-fuel above the strongest verified reload.

DISCARD_SUPPLY = "discard"     # the shared capacity group every discard-drawing effect competes in

#: The colours ONE **Energy Unit** already on a body can pay, keyed by the ``EnergyType`` code the
#: engine puts in ``Pokemon.energies`` (Issue #297). Empty = WILD, and it means "every colour", never
#: "unknown"; the unknown case is handled by :func:`unit_colours`'s fallback.
#:
#: Listed here are the codes that do NOT simply pay their own colour; ``GRASS``..``DRAGON`` (1-9)
#: fall through to ``{code}``. Codes from `src/cg/api.py` ``EnergyType``; the per-card provisions
#: below are from the **printed provision column** of `data/EN_Card_Data.csv` — NOT from
#: ``CardStat.energyType``, which is the card's own colour tag and is 0 for most Special Energy
#: whatever it provides (Team Rocket's Energy is the trap: ``energyType`` 0, provision
#: ``{Team Rocket}{Team Rocket}``).
#:
#:   * ``COLORLESS = 0`` — a colourless unit pays a colourless slot and NOTHING else. This is the
#:     one that used to be wrong: an attached Ignition Energy renders ``[0, 0, 0]``, the old read
#:     resolved code 0 through the card table (no card 0 -> ``None`` -> wild), and three colourless
#:     units became three blank cheques that could fund a typed ``{F}{F}`` line. `AttachUnit` and
#:     `_special_energy_groups` both already SAID ``{0}`` — the same Ignition sitting in HAND was
#:     priced colourless-only — so the attached leg was the one place contradicting the contract.
#:     Five pool cards provide ``{C}``: Boomerang 9, Mist 11, Enriching 13, Spiky 14, Ignition 17
#:     (three units).
#:   * ``RAINBOW = 10`` ("Every Types") — genuinely wild. Three pool cards print the rainbow-class
#:     ``{A}``: Neo Upper 10 (``{A}{A}``), Legacy 12, Prism 16. The code appears once in the
#:     committed corpus, on an opponent body.
#:   * ``TEAM_ROCKET = 11`` ("PSYCHIC and DARKNESS") — pays either of those two. **Team Rocket's
#:     Energy (card 15) prints ``{Team Rocket}{Team Rocket}``**, so this is a pool card, not a
#:     hypothetical; it is simply absent from the committed corpus because no shipped agent deck
#:     runs it. Which code the engine renders for it is therefore UNVERIFIED here — no board we hold
#:     carries one — so this entry is what happens IF it renders as 11, stated rather than left as a
#:     silent hole.
#:
#: ``DRAGON = 9`` needs no entry — it pays its own colour like 1-8 — and no pool card provides it.
#: Worth stating anyway, because it is where the old card-id round-trip's coincidence actually
#: stopped: at **8**, not 9. Card 9 is Boomerang Energy, whose ``energyType`` is 0, so a DRAGON unit
#: resolved to neither a colour nor "unresolvable" and counted as nothing at all.
_UNIT_COLOURS = {
    0: frozenset({0}),
    10: frozenset(),
    11: frozenset({5, 7}),
}

#: ``EnergyType.RAINBOW`` — the engine's own code for *"Every Types"*, and so the unit code for an
#: Energy whose colour this build cannot pin down. Not a sentinel: it is a real enum member that
#: :func:`unit_colours` already resolves to the empty (WILD) colour set, which is the fail-OPEN
#: reading :meth:`CombatMath.attack_type_payable` gives an unresolvable attached Energy anyway. Using
#: it keeps the degraded reading inside the ``energies`` vocabulary instead of beside it.
WILD_CODE = 10

def unit_colours(code) -> frozenset:
    """The colours ONE attached **Energy Unit** can pay, from its ``EnergyType`` code.

    An unrecognised code — a new set's enum member this build predates — falls back to WILD, which
    is the same fail-OPEN direction :meth:`CombatMath.attack_type_payable` already applies to
    anything it cannot pin down. Codes 1-9 pay their own colour; see :data:`_UNIT_COLOURS` for the
    three that do not."""
    if code in _UNIT_COLOURS:
        return _UNIT_COLOURS[code]
    return frozenset({code}) if isinstance(code, int) and 1 <= code <= 9 else frozenset()

def units_for_codes(codes) -> tuple:
    """``EnergyType`` UNIT codes as Budget units — the ONE translation from the ``energies``
    vocabulary into :class:`AttachUnit`.

    Every reading of a unit's colour goes through :func:`unit_colours` here, so Energy already on a
    body and Energy a hypothetical attach would put there are typed by the same rule. Until Issue
    #418 the hand-side readers spelled the pool as ``frozenset({etype})`` instead, which agrees with
    :func:`unit_colours` on the eight Basic colours and on colourless — and disagrees on exactly the
    two codes :data:`_UNIT_COLOURS` exists for (RAINBOW pays anything, TEAM_ROCKET pays {P} or {D}).
    That is the Issue #297 split one door over, so it has one home now."""
    return tuple(AttachUnit(unit_colours(code)) for code in codes)

@dataclass(frozen=True)
class AttachUnit:
    """ONE Energy unit that could sit on a body — the atom of the **Attach Budget**.

    ``types``: the EnergyTypes this unit may take. Empty = ANY type (an attached Energy whose card
    doesn't resolve — fail-open, matching :meth:`CombatMath.attack_type_payable`'s ``wild_units``).
    A colourless/special unit carries ``{0}`` and so pays only colourless slots.

    ``groups``: capacity groups this unit draws from, each policed by the Budget's ``caps``. Two
    kinds compose: a per-CARD group whose cap is one-per-colour realises "up to 2 Basic Energy of
    DIFFERENT types" (Crispin), and ``DISCARD_SUPPLY``, whose cap is the visible pile, stops the
    turn's discard-drawing effects from collectively claiming Energy the pile does not hold.

    ``source``: the ZONE this unit is drawn from, ``"deck"`` marking the only uncertain one — the
    hidden zone whose fetch can whiff (ADR-0074, #175). Everything else is certain at decision time
    (an Energy in hand, a discard-sourced attach over the public pile, an Energy already attached)
    and carries ``None``, contributing probability 1.0. Purely descriptive: no affordability check
    reads it, so the boolean Budget is unchanged by its presence.
    """
    types: frozenset = field(default_factory=frozenset)
    groups: tuple = ()
    source: str | None = None

@dataclass(frozen=True)
class Budget:
    """The **Attach Budget** — this turn's full attach capacity toward ONE body (ADR-0067).

    ``options`` are the legal play-sets (the Items always play; each Supporter is an alternative to
    every other; the single manual attach picks one Energy source). Affordability asks whether ANY
    option pays, so a Supporter choice that is smaller but better-TYPED is never lost to a bigger
    one — exact, not a best-by-count guess. Options are not disjoint: the no-Supporter and
    no-manual-attach sets are emitted alongside their supersets, which is harmless because
    payability is monotone in units, so a subset never wins where its superset loses.

    ``caps`` bound how many units of each type a group may realise at once, so a set of units can
    be individually legal yet jointly infeasible — which is exactly the truth about one discard
    pile shared by two accelerators. An option therefore carries units it may not be able to use
    together: read it through :attr:`size` or :func:`_can_pay`, never as a raw ``len``.
    """
    options: tuple = ((),)
    caps: dict = field(default_factory=dict)

    @property
    def size(self) -> int:
        """Units the best option can SIMULTANEOUSLY realise under ``caps`` — the Budget's headline
        magnitude. Counting raw units would over-report: two Wondrous Patches over a single {P} in
        the discard are two units but one attach."""
        return max((self._realisable(option) for option in self.options), default=0)

    def realising_p(self, slots, p_by_type: dict, attached=()) -> float:
        """P(this Budget actually pays ``slots``) — the **Probability Leg** applied to the assignment
        the payment really uses (ADR-0074 decision 3, #175).

        Prices the DEPENDENCY, not the pantry: over every feasible assignment of units to slots
        (``attached`` Energy first, then one Budget option), the probability is the product of
        ``p_by_type`` over the distinct **deck-sourced** types that assignment consumes; every
        certain unit — attached, in hand, from the public discard — contributes 1.0. The maximum
        over assignments is returned, so a KO payable entirely from hand scores exactly 1.0 even on
        a deck depleted of the type some *other* card in the option could have fetched. 0.0 when no
        assignment pays at all.

        Distinct TYPES, not units: two deck units of one colour are priced at P(>=1 copy), not
        P(>=1) squared. The per-card one-per-colour cap (Crispin's "2 Basic Energy of DIFFERENT
        types") makes same-type double demand off a single card impossible; across two fetch cards
        it is an over-claim, stated here rather than silently modelled.
        """
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
    """Per-decision zone facts the clause interpreter reads (never board objects).

    The two Energy zones are read at DIFFERENT precisions on purpose (ADR-0067): the deck is
    hidden, so it is a *not-provably-empty* type SET; the discard is public, so it is an exact
    per-type COUNT that caps what the turn's discard-drawing effects can jointly take."""
    deck: frozenset = field(default_factory=frozenset)
    discard: dict = field(default_factory=dict)
    benched: bool = False
    more_prizes: bool = False

    def source_types(self, source) -> frozenset:
        """The Energy types a clause's SOURCE zone can still supply; empty for an unmodelled zone
        (fail-CLOSED — an unreadable source yields nothing)."""
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
    """What one playable hand card offers: units it attaches BY ITS EFFECT (independent of the
    turn's manual attach), units it merely puts in HAND (which the manual attach must play), and
    the per-card capacity ``cap`` its own group is policed by ({} when it needs no group)."""
    is_supporter: bool
    effect_units: tuple
    hand_yields: tuple
    group: object = None
    cap: dict = field(default_factory=dict)

def _pay_best_p(slots, units, caps, p_by_type: dict) -> float:
    """Max over feasible assignments of ``units`` to ``slots`` of the product of ``p_by_type`` over
    the distinct DECK-sourced types the assignment consumes (ADR-0074). 0.0 when nothing pays.

    Mirrors :func:`_can_pay`'s matcher exactly — same slot ordering, same per-group capacity
    charging — so an assignment this scores is one ``_can_pay`` would have accepted, and a Budget
    that cannot pay scores 0.0 rather than a probability. Bounded identically (<=4 slots, a handful
    of units, a few colours), with the search pruned the moment a branch cannot beat the incumbent.
    """
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
    """Can ``units`` cover an attack's per-slot cost ``slots`` (EnergyType codes; 0 = colourless)?

    Exact. Every slot — colourless ones too — is matched to a DISTINCT unit that takes one concrete
    type from its pool, and each choice is charged against every capacity group the unit belongs to
    (``caps``: group -> {EnergyType: max units}). Charging colourless slots matters: an Energy spent
    paying a colourless slot still leaves the discard pile, so skipping it would let one card in the
    pile fund two slots. A unit inside a group with no pool to name a type from cannot be charged,
    so it is refused — fail-CLOSED, per ADR-0067.

    Bounded and tiny: costs run to 4 slots, budgets to a handful of units, pools to a few colours.
    Typed slots are ordered first so an impossible colour prunes before any colourless branching."""
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
    """How many of ``slots`` ``units`` can SIMULTANEOUSLY pay — the partial-credit reading of
    :func:`_can_pay`, and the arithmetic behind typed slot-fraction build progress (ADR-0069 §3).

    Defined AS a search over sub-costs of :func:`_can_pay` rather than as a second assignment
    routine: "fits" (build) and "reaches" (:meth:`CombatMath.reachable_attach`) must be the same
    matcher, so a partial match can never disagree with the payability it is a fraction of. Bounded
    and tiny — costs run to a handful of slots, so the ``2**len(slots)`` subset walk is smaller than
    the assignment inside it.
    """
    n = len(slots)
    if n == 0 or not units:
        return 0
    for k in range(min(n, len(units)), 0, -1):
        for subset in combinations(range(n), k):
            if _can_pay(tuple(slots[i] for i in subset), units, caps):
                return k
    return 0
