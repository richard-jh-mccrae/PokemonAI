"""**The apply-seam**: `apply_option(model, option)` answers *what would the board be if I did this?*
closed-form, so the planner prices a play by differencing. **On the hot path** — `composer.compose`
calls it per candidate step, and the composer decides MAIN. ADR-0092, ADR-0098, ADR-0131.

Every option resolves to one fate (:func:`fate`), and a silent no-op is never one: an unmodelled
option returning the model unchanged prices at 0.0, which reads as *worthless* rather than
*unmodelled* — so it returns a :class:`Refusal`. Transitions are LAZY, never an eager deep copy per
branch, riding the lazy StateModel of ADR-0068. The arithmetic is `common.board_delta` /
`common.board_expectation` / `common.board_choice`; this module is the CONTRACT only.

`_search_api` (`strategy/planner.py`) survives Issue #263 as exactly this narrow engine fallback, so
do not design as if it disappears.

**It cannot capture information value**: an informative card played before a committing one reaches
the same end state, so no ordering of them differs there. Structural rule (ADR-0095), not a defect.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

# Engine option types via the strategy context, which owns the DLL-free mirror — never re-spelled.
from common import snapshot_coverage
from common.strategy.context import (
    _ABILITY, _ATTACH, _ATTACHED_TOOL, _ATTACK, _CARD, _DISCARD_IN_PLAY, _END, _ENERGY, _ENERGY_CARD,
    _EVOLVE, _NO, _NUMBER, _PLAY, _RETREAT, _SKILL, _SPECIAL_CONDITION, _YES,
)

# ── coverage classes ──────────────────────────────────────────────────────────────────────────────

#: Closed-form transition promised for the KIND; an option inside it may still refuse per-card.
MODELLED = "modelled"
#: Eligible for the engine fallback; :func:`fate` decides per option.
ENGINE_RESOLVED = "engine-resolved"
#: Ends the turn: there is no ``model'`` at all, and the beam terminates here.
TERMINAL = "terminal"
#: Declared, and knowingly unmodelled. Ordering must always-expand it.
REFUSED = "refused"
#: Not in the table. The engine enum grows during the competition — a live case, not a theoretical one.
UNDECLARED = "undeclared"

#: The player picks a CHOSEN class; a DEALT class is resolved by chance before play continues.
CHOSEN = "chosen"
DEALT = "dealt"
_EXPECTATION_RESOLUTIONS = frozenset({CHOSEN, DEALT})

#: TERMINAL is not among them (a turn-ender has no transition); UNDECLARED is a refusal reason.
FATES = (MODELLED, ENGINE_RESOLVED, REFUSED)

#: Why a call refused, carried on the :class:`Refusal`. :data:`KIND_SCOPE` is no longer EMITTED by
#: :func:`apply_option` (Issue #299), but is kept: :func:`coverage` still reports the table's class.
KIND_SCOPE = "kind"              # the kind itself is unmodelled — no longer emitted (Issue #299)
OPTION_SCOPE = "option"          # kind is modelled, this option's card effect is not
UNDECLARED_SCOPE = "undeclared"  # the option vocabulary grew underneath us
QUARANTINE_SCOPE = "quarantine"  # parity divergence found for this kind (ADR-0098 decision 4)
DEPTH_SCOPE = "depth"            # depth >= 2: the board is synthesized, the engine cannot take it
NONDETERMINISM_SCOPE = "nondeterminism"   # unproven or proven-not deterministic — fail closed
NO_ENGINE_SCOPE = "no-engine"    # eligible, but the caller supplied no `_search_api` seam

# ── the option-kind table ─────────────────────────────────────────────────────────────────────────

#: **Total over `OptionType`**: 1-ply ordering visits every option on a live menu. Default REFUSED —
#: the kind IS its effect. Demotion needs a ruling; census in `docs/plans/apply-seam-coverage.md`.
KIND_COVERAGE: dict[int, str] = {
    _PLAY: MODELLED,             # the card leaves hand; its effect may still refuse per-option
    _ATTACH: MODELLED,
    _EVOLVE: MODELLED,           # body substituted in place (ADR-0070's shape)
    _RETREAT: MODELLED,
    _ATTACK: TERMINAL,
    _END: TERMINAL,
    _NUMBER: REFUSED,            # "how many?" — meaning belongs to the effect asking
    _YES: REFUSED,               # activate an optional effect
    _NO: REFUSED,                # declining is NOT identity: the card may still be spent
    _CARD: REFUSED,              # meaning is the SelectContext's (snipe / search / discard target)
    _ATTACHED_TOOL: REFUSED,
    _ENERGY_CARD: REFUSED,
    _ENERGY: REFUSED,
    _ABILITY: ENGINE_RESOLVED,   # the kind IS its effect, but many Abilities touch no RNG and no
                                 # hidden zone, so the engine fallback can price them 1-ply
    _DISCARD_IN_PLAY: REFUSED,
    _SKILL: REFUSED,             # an ORDERING of simultaneous effects, not a board transition
    _SPECIAL_CONDITION: REFUSED,
}

TRANSITION_KINDS: frozenset[int] = frozenset(
    k for k, c in KIND_COVERAGE.items() if c == MODELLED)

#: **Documentation, not the gate** (Issue #299): the engine route is open to every declared
#: non-terminal kind and the gate is :func:`fate`'s per-option proof. Name kept deliberately.
ENGINE_ROUTE_KINDS: frozenset[int] = frozenset(
    k for k, c in KIND_COVERAGE.items() if c == ENGINE_RESOLVED)

#: The turn is over, so there is no ``model'`` — the beam terminates here (`docs/rules.md` §3).
TERMINAL_KINDS: frozenset[int] = frozenset(
    k for k, c in KIND_COVERAGE.items() if c == TERMINAL)

REFUSED_KINDS: frozenset[int] = frozenset(
    k for k, c in KIND_COVERAGE.items() if c == REFUSED)

@dataclass(frozen=True)
class Footprint:
    """Which snapshot fields a kind's transition READS and WRITES — Issue #263 proves commutativity
    from them. **Fail closed**: ``complete=False`` commutes with NOTHING; its sets are a FLOOR only."""

    reads: frozenset[str] = frozenset()
    writes: frozenset[str] = frozenset()
    complete: bool = False
    #: A revealer changes the OPTION SET, so it never commutes whatever its read/write sets say. No
    #: :data:`FOOTPRINTS` entry sets it — revealing is a CARD property (:func:`option_footprint`).
    reveals_information: bool = False
    #: ``{(zone, serial)}`` — WHICH instances, for `snapshot_coverage.ELEMENT_ZONES` (ADR-0098 Amd D).
    #: Empty means UNRESOLVED, which conflicts: element-level is a licence, never an obligation.
    read_elements: frozenset[tuple[str, int]] = frozenset()
    #: The same for writes. A KIND has no instance, so every :data:`FOOTPRINTS` entry leaves both empty.
    write_elements: frozenset[tuple[str, int]] = frozenset()


@dataclass(frozen=True)
class EngineResolved:
    """A transition the ENGINE produced, not the clause vocabulary. A wrapper rather than a bare model
    so a caller cannot use the answer without seeing the route; `require_model` unwraps it."""

    model: object | None = None
    kind: int = -1
    #: Telemetry payload, and it **must name the CARD**, not only the kind (Issue #299):
    #: ``"<card id> <card name>: <gap>"``. ONE field — the modelling backlog groups by this string.
    clause_gap: str = ""


@dataclass(frozen=True)
class Refusal:
    """*"I cannot model this option"* — a first-class RESULT, not an exception and never a quietly
    unchanged model, which would price at exactly 0.0 delta and bury the gap."""

    kind: int
    #: One of the ``*_SCOPE`` constants — which way this seam is blind here.
    scope: str
    reason: str


#: Per-kind READ/WRITE footprints, in `snapshot_coverage` field vocabulary. `_PLAY` is deliberately
#: INCOMPLETE — a KIND cannot claim what a CARD writes; :func:`option_footprint` is the per-option one.
FOOTPRINTS: dict[int, Footprint] = {
    # A Tool arrives as ATTACH exactly like an Energy: it writes `attached_tools` (plus
    # `damage_counters` for a flat HP grant) and spends no allowance. Issue #382.
    _ATTACH: Footprint(
        reads=frozenset({"my_hand_ids", "bodies_in_play", "allowance_energy_attached"}),
        writes=frozenset({"attached_energy", "attached_tools", "damage_counters", "my_hand_ids",
                          "allowance_energy_attached"}),
        complete=True),
    # `new_in_play` both read and written: *cannot evolve the turn it was played* (`docs/rules.md`
    # §4), and the evolved body itself arrives new-in-play. `reads` is state the kind DEPENDS on.
    _EVOLVE: Footprint(
        reads=frozenset({"my_hand_ids", "bodies_in_play", "new_in_play"}),
        # Evolving CLEARS Special Conditions (`docs/rules.md` §4); `damage_counters` homes the HP
        # read a Stadium's static delta re-takes on the new stage (Issue #410).
        writes=frozenset({"bodies_in_play", "my_hand_ids", "special_conditions", "new_in_play",
                          "damage_counters"}),
        complete=True),
    _RETREAT: Footprint(
        reads=frozenset({"bodies_in_play", "attached_energy", "allowance_retreat_used"}),
        # Special Conditions clear when a body LEAVES the Active spot too (`docs/rules.md` §8).
        writes=frozenset({"bodies_in_play", "attached_energy", "my_discard_contents",
                          "allowance_retreat_used", "special_conditions"}),
        complete=True),
    # `_PLAY`'s STRUCTURAL FLOOR, `complete=False`: the zones the card's TYPE alone implies. A Stadium
    # play writes BOTH discards — whose discard depends on whose Stadium was displaced (rulebook L78).
    _PLAY: Footprint(
        reads=frozenset({"my_hand_ids", "stadium", "allowance_stadium_played",
                         "allowance_supporter_played", "bench_occupancy"}),
        writes=frozenset({"my_hand_ids", "my_discard_contents", "their_discard_contents",
                          "stadium", "allowance_stadium_played", "allowance_supporter_played",
                          "bodies_in_play", "bench_occupancy", "new_in_play", "damage_counters"}),
        complete=False),
}


def footprint(kind: int) -> Footprint:
    """This kind's footprint, or the fail-closed default (incomplete ⇒ commutes with nothing)."""
    return FOOTPRINTS.get(int(kind), Footprint())


def footprints_writing_unhomed() -> dict:
    """``{kind: [owed zone ids]}`` — kinds writing state the snapshot cannot hold. EMPTY since T1, and
    may only SHRINK. Blind per-CARD: a card with no clauses unions to the empty set (Issue #383)."""
    owed = set(snapshot_coverage.unhomed())
    out = {}
    for kind, fp in FOOTPRINTS.items():
        hit = sorted((fp.writes | fp.reads) & owed)
        if hit:
            out[kind] = hit
    return out


def footprints_commute(a: Footprint, b: Footprint) -> bool:
    """The disjointness test: both complete, neither revealing, no read/write or write/write overlap.
    ELEMENT-level for `snapshot_coverage.ELEMENT_ZONES`; unresolved beats precise (ADR-0098 Amd D)."""
    if not (a.complete and b.complete):
        return False
    if a.reveals_information or b.reveals_information:
        return False
    if _collides(a.reads, a.read_elements, b.writes, b.write_elements):
        return False
    if _collides(b.reads, b.read_elements, a.writes, a.write_elements):
        return False
    return not _collides(a.writes, a.write_elements, b.writes, b.write_elements)


def _collides(zones_x, elements_x, zones_y, elements_y) -> bool:
    """A shared zone collides unless BOTH sides resolved it to instances AND those are disjoint."""
    for zone in zones_x & zones_y:
        if zone not in snapshot_coverage.ELEMENT_ZONES:
            return True
        here = {s for z, s in elements_x if z == zone}
        there = {s for z, s in elements_y if z == zone}
        if not here or not there or (here & there):
            return True
    return False


def commutes(kind_a: int, kind_b: int) -> bool:
    """The KIND-level door onto :func:`footprints_commute`; :func:`option_footprint` is per-option."""
    return footprints_commute(footprint(kind_a), footprint(kind_b))


def option_footprint(model, option: Mapping, *, clauses_cover: bool | None = None) -> Footprint:
    """The per-OPTION footprint: the kind's structural floor, narrowed, plus this card's clause writes
    (Issue #383). Fail-closed — no clauses, an undeclared clause value or an unknown card ⇒ incomplete."""
    from common.board_delta import card_clauses      # the ONE home of the clause walk
    if is_terminal(option):
        return Footprint()
    kind = transition_kind(option)
    base = footprint(kind)
    card = _option_card(model, option)
    clauses = card_clauses(getattr(model, "combat", None), card[0]) if card is not None else ()
    # A separate walk from `board_delta._clause_writes` (which RAISES on RNG/reveal): a footprint must
    # DESCRIBE a revealer, and `clause_zones` stays apart from the floor so rule 3 can re-read a zone.
    clause_zones, reveals, undeclared = set(), False, False
    for clause in clauses:
        for value in snapshot_coverage.clause_values(clause):
            zones = snapshot_coverage.CLAUSE_WRITES.get(value)
            if zones is None:
                undeclared = True
                continue
            clause_zones |= zones
            reveals = reveals or value in snapshot_coverage.REVEALING_CLAUSES
    # Rule 1: `clauses_cover is True` completes the floor only when there ARE clauses it covered.
    complete = ((base.complete or (clauses_cover is True and bool(clauses)))
                and clauses_cover is not False
                and not undeclared
                and card is not None)
    # Narrowing applies to the FLOOR; the clause union goes on TOP, or a `gust`'s write is stripped.
    drop = _structural_drop(model, kind, card)
    reads = (set(base.reads) - drop) | clause_zones
    writes = (set(base.writes) - drop) | clause_zones
    hand_serial, body_serial = option_serials(model, option)
    body_serial = _deployed_body_serial(model, kind, card, hand_serial, body_serial)
    return Footprint(reads=frozenset(reads), writes=frozenset(writes), complete=bool(complete),
                     reveals_information=reveals,
                     read_elements=_elements(reads, hand_serial, body_serial),
                     write_elements=_elements(writes, hand_serial, body_serial))


def _elements(zones, hand_serial, body_serial) -> frozenset:
    """``{(zone, serial)}`` for the element zones this option resolves — which serial keys which zone
    is `snapshot_coverage`'s CARD_KEYED / BODY_KEYED split. Omitted ⇒ unresolved ⇒ conflicts."""
    out = set()
    for zone in zones & snapshot_coverage.ELEMENT_ZONES:
        serial = (hand_serial if zone in snapshot_coverage.CARD_KEYED_ZONES
                  else body_serial if zone in snapshot_coverage.BODY_KEYED_ZONES else None)
        if serial is not None:
            out.add((zone, serial))
    return frozenset(out)


def _deployed_body_serial(model, kind: int, card, hand_serial, body_serial):
    """A Basic deploy's new body carries the HAND card's serial (`board_delta._play`), so
    `bodies_in_play` resolves. Basic ONLY — a Trainer moves someone else's body, so it stays unresolved."""
    if body_serial is not None or kind != _PLAY or card is None or hand_serial is None:
        return body_serial
    stat = model.card_stat(card[0])
    is_basic = bool(getattr(stat, "is_pokemon", False)) and not getattr(stat, "evolvesFrom", None)
    return hand_serial if is_basic else None


def option_serials(model, option: Mapping):
    """``(hand card serial, targeted body serial)``, either may be None. Public for `common.composer`,
    which re-resolves a permuted block member by instance, never by a stale hand index (Issue #385)."""
    from common.option_equivalence import AREA_ACTIVE, AREA_BENCH, AREA_HAND
    obs = getattr(model, "source_obs", None) or {}
    players = ((obs.get("current") or {}).get("players")) or []
    seat = int(getattr(model, "my_index", 0))
    named = option.get("playerIndex")
    if named is not None and int(named) != seat:
        return None, None                     # the option is about THEIR board; I key nothing here
    me = players[seat] if 0 <= seat < len(players) and players[seat] else {}

    def serial_at(cards, index):
        if not isinstance(index, int) or not 0 <= index < len(cards) or not cards[index]:
            return None
        return (cards[index] or {}).get("serial")

    # A `_PLAY` names its hand index bare, with no `area` — so this cannot filter on AREA_HAND.
    hand = serial_at(me.get("hand") or (), option.get("index")) \
        if option.get("area") in (None, AREA_HAND) else None
    area, index = option.get("inPlayArea"), option.get("inPlayIndex")
    if area == AREA_ACTIVE:
        body = serial_at(me.get("active") or (), index)
    elif area == AREA_BENCH:
        body = serial_at(me.get("bench") or (), index)
    else:
        body = None
    return hand, body


def _structural_drop(model, kind: int, card) -> frozenset:
    """Zones to DROP from the KIND's floor, narrowing it to the sub-case this option takes — a kind
    entry is the UNION of sub-cases that never co-occur. Each sub-case is `board_delta`'s write-set."""
    if card is None or kind not in (_ATTACH, _PLAY):
        return frozenset()
    stat = model.card_stat(card[0])
    if stat is None:
        return frozenset()                      # unknown card — keep the union, fail closed
    floor = footprint(kind)
    everything = floor.reads | floor.writes
    if kind == _ATTACH:
        if getattr(stat, "is_tool", False):
            return frozenset({"attached_energy", "allowance_energy_attached"})
        if getattr(stat, "is_energy", False):
            return frozenset({"attached_tools", "damage_counters"})
        return frozenset()                      # neither leg — `board_delta._attach` refuses it
    # `_PLAY`, and only for the two sub-cases `board_delta._play` actually models.
    if getattr(stat, "is_pokemon", False) and not getattr(stat, "evolvesFrom", None):
        # Kept for every deploy: whether Risky Ruins is in play is a BOARD fact this cannot see.
        return frozenset(everything - {"my_hand_ids", "bodies_in_play", "bench_occupancy",
                                       "new_in_play", "damage_counters"})
    if getattr(stat, "is_stadium", False):
        return frozenset(everything - {"my_hand_ids", "stadium", "allowance_stadium_played",
                                       "my_discard_contents", "their_discard_contents"})
    return frozenset()                          # a Trainer play — no measured floor, so keep it all


@dataclass(frozen=True)
class OutcomeClass:
    """One branch of an :class:`Expectation`. Classes are enumerated by ADR-0091 Option Equivalence
    identity, not card identity, so the branching factor is the decisions posed, not the cards."""

    #: From `common.deck_odds` hypergeometrics, never an engine shuffle. For a SEARCH it is an
    #: availability weight, not a chance-node probability — so :meth:`Expectation.expected` is a bound.
    probability: float
    #: The resulting StateModel for this branch; `None` on a hand-built class.
    model: object | None = None
    fingerprint: tuple = ()


@dataclass(frozen=True)
class Expectation:
    """Outcome classes whose resolution says whether the player chooses or chance deals one."""

    classes: Sequence[OutcomeClass] = field(default_factory=tuple)
    #: Classes dropped by the branching cap; non-zero ⇒ the enumeration is INCOMPLETE.
    truncated: int = 0
    resolution: str = CHOSEN

    def __post_init__(self):
        if self.resolution not in _EXPECTATION_RESOLUTIONS:
            raise ValueError(f"unknown Expectation resolution {self.resolution!r}")

    @property
    def total_probability(self) -> float:
        """Sums to 1.0 on a complete enumeration; the gap IS the truncation."""
        return float(sum(c.probability for c in self.classes))

    def best(self, score: Callable[[object], float]) -> float:
        """The maximum class score. It orders CHOSEN outcomes, ignoring their probabilities."""
        if not self.classes:
            raise ValueError(
                "cannot order an Expectation with no enumerated classes — that is an un-enumerated "
                "effect, and returning 0.0 would price it as a worthless one")
        return max(float(score(c.model)) for c in self.classes)

    def expected(self, score: Callable[[object], float]) -> float:
        """The probability-weighted class score, renormalised over the enumerated mass."""
        mass = self.total_probability
        if mass <= 0.0:
            raise ValueError(
                "cannot order an Expectation with no enumerated mass — that is an un-enumerated "
                "effect, and returning 0.0 would price it as a worthless one")
        return float(sum(c.probability * float(score(c.model)) for c in self.classes) / mass)

    def ordering(self, score: Callable[[object], float]) -> float:
        """The value that orders this resolution: max for CHOSEN, expectation for DEALT."""
        return self.best(score) if self.resolution == CHOSEN else self.expected(score)


@dataclass(frozen=True)
class ScalarTransition:
    """Known board writes plus a closed-form value for information the snapshot cannot hold."""

    model: object
    scalar: float


class UnsupportedTransition(NotImplementedError):
    """A caller that REQUIRED a model got a :class:`Refusal`. Raised only off the ordering path — the
    composer never sees it; it reads :func:`must_expand`."""


def transition_kind(option: Mapping) -> int:
    """The option's engine ``type``. **Never raises**: the enum grows during the competition, and a
    raise on the ordering hot path is a forfeited grader match over an option we could not price."""
    return int((option or {}).get("type", -1))


def coverage(kind: int) -> str:
    """Kind-level handling. :data:`ENGINE_RESOLVED` here means *eligible*, not decided — :func:`fate`
    resolves an actual option. A quarantined kind reads REFUSED, so there is ONE answer, not two."""
    kind = int(kind)
    if kind in quarantined_kinds():
        return REFUSED
    return KIND_COVERAGE.get(kind, UNDECLARED)


def fate(option: Mapping, *, depth: int = 0, search_api=None, deterministic: bool | None = None,
         clauses_cover: bool | None = None, deferred_target: bool | None = None) -> str:
    """Which fate this call resolves to (Issue #299, ADR-0098 Amd C). Fail-closed: `deterministic=None`
    refuses, and `clauses_cover=None` means *no printed effect* too, so the CALLER passes `False`."""
    kind = transition_kind(option)
    if kind in quarantined_kinds():
        return REFUSED
    how = coverage(kind)
    if how == TERMINAL or how == UNDECLARED:
        return REFUSED
    if clauses_cover is True:
        return MODELLED
    if how == MODELLED and clauses_cover is not False:
        return MODELLED
    if deferred_target is True:
        return MODELLED
    if depth >= 1:
        return REFUSED
    if deterministic is not True:
        return REFUSED
    return ENGINE_RESOLVED if search_api is not None else REFUSED


def is_terminal(option: Mapping) -> bool:
    """Does taking this option END the turn? Attack and End do (`docs/rules.md` §3)."""
    return coverage(transition_kind(option)) == TERMINAL


def refuse(option: Mapping, reason: str, *, scope: str = OPTION_SCOPE) -> Refusal:
    """Build a :class:`Refusal`. Public: T4 refuses per-OPTION from inside a MODELLED kind."""
    if not (reason or "").strip():
        raise ValueError("a Refusal must say why — it is destined for the telemetry line")
    return Refusal(kind=transition_kind(option), scope=scope, reason=reason)


def must_expand(result: object) -> bool:
    """True for a :class:`Refusal`: the composer must ALWAYS-EXPAND rather than prune. An option with
    no price is not an option with no value — it has no estimate."""
    return isinstance(result, Refusal)


def require_model(result: object):
    """``result`` if it is a model or an :class:`Expectation` (unwrapping :class:`EngineResolved`);
    raise otherwise. **The ordering path must not call this** — it calls :func:`must_expand`."""
    if must_expand(result):
        r: Refusal = result  # type: ignore[assignment]
        raise UnsupportedTransition(
            f"option type {r.kind} refused ({r.scope}): {r.reason} — this caller requires a model")
    if isinstance(result, EngineResolved):
        return result.model
    return result


def apply_option(model, option: Mapping, *, depth: int = 0, search_api=None,
                 deterministic: bool | None = None, clauses_cover: bool | None = None,
                 expand_deferred_targets: bool = False):
    """The board after taking ``option``: a `StateModel`, an :class:`Expectation`, an :class:`EngineResolved`
    or a :class:`Refusal` — never a silent no-op, never a mutation. ``expand_deferred_targets`` ships OFF."""
    kind = transition_kind(option)
    if kind in quarantined_kinds():
        return refuse(option, f"option kind {kind} is quarantined by the parity lane",
                      scope=QUARANTINE_SCOPE)
    how = coverage(kind)
    if how == TERMINAL:
        raise ValueError(
            "attack and end-turn are TERMINAL — they end the turn, so there is no successor state; "
            "test `is_terminal(option)` before calling")
    if how == UNDECLARED:
        return refuse(option, f"option kind {kind} is not in the seam's coverage table",
                      scope=UNDECLARED_SCOPE)
    # The native seed retains effect-frame state a CARD target cannot identify, so this preempts
    # generic CARD refusal; all other contexts follow `fate` and `_CARD` coverage stays REFUSED.
    if kind == _CARD:
        from common import apply_engine
        if apply_engine.continuation_index(model, option, card_kind=_CARD, depth=depth) is not None:
            if search_api is None:
                return refuse(option, "seeded CARD continuation has no `_search_api` seam to replay its "
                                      "live engine frame through", scope=NO_ENGINE_SCOPE)
            after = apply_engine.resolve(model, option, search_api=search_api)
            if after is None:
                return refuse(
                    option,
                    "seeded CARD continuation engine-refused — no state was normalised, no success "
                    "was synthesized, and no context/card fallback was used",
                    scope=NO_ENGINE_SCOPE)
            return EngineResolved(model=after, kind=kind, clause_gap=_clause_gap(model, option))
        if apply_engine.engine_refused_context(model, option, card_kind=_CARD, depth=depth) is not None:
            return refuse(
                option,
                "seeded SETUP_BENCH_POKEMON continuation engine-refused — native replay cannot restore "
                "the opponent Active's `appearThisTurn`; no composer route, state normalisation, "
                "synthetic semantics, or context/card fallback was used",
                scope=NO_ENGINE_SCOPE)
        return refuse(
            option,
            "unowned CARD select — only exact, depth-0 seeded continuations in Issue #464's context "
            "allowlist may use the engine; this call has no context/card fallback",
            scope=OPTION_SCOPE)
    # Asked once, here, and threaded into `fate` so the two cannot disagree about the same option.
    deferred = False
    if expand_deferred_targets:
        from common import board_choice
        deferred = board_choice.has_deferred_target(
            model, option, seat_index=int(getattr(model, "my_index", 0)))
    # The FATE is `fate`'s, asked ONCE. What this function adds is only the SCOPE.
    resolved = fate(option, depth=depth, search_api=search_api, deterministic=deterministic,
                    clauses_cover=clauses_cover, deferred_target=deferred or None)
    if resolved == REFUSED:
        # A refusal here is an ENGINE precondition, and which one is the work owed — a scope each.
        if depth >= 1:
            return refuse(
                option,
                f"depth {depth}: the board is a synthesized StateModel from a prior closed-form "
                f"apply, and a synthesized model cannot be handed back to the native engine",
                scope=DEPTH_SCOPE)
        if deterministic is not True:
            return refuse(
                option,
                "not PROVABLY deterministic (`deterministic=%r`) — the gate is proof, not absence of "
                "a model: the engine has no deal-seed, so a shuffle-riding sim is one sample rather "
                "than a distribution, and nondeterminism breaks the replay both gates depend on"
                % (deterministic,),
                scope=NONDETERMINISM_SCOPE)
        if search_api is None:
            return refuse(option, "no `_search_api` seam supplied, so there is no engine to resolve "
                                  "through", scope=NO_ENGINE_SCOPE)
    if resolved == ENGINE_RESOLVED:
        from common import apply_engine
        after = apply_engine.resolve(model, option, search_api=search_api)
        if after is None:
            return refuse(
                option,
                "the engine route was eligible but produced no board — the observation carries no "
                "`search_begin_input` (0 of 372 gate frames do), the option is not on this menu, or "
                "the engine raised",
                scope=NO_ENGINE_SCOPE)
        return EngineResolved(model=after, kind=kind, clause_gap=_clause_gap(model, option))
    if deferred:
        return _choice(model, option)
    return _modelled(model, option)


def _choice(model, option: Mapping):
    """The CHOICE node: an `Expectation` over the boards this option's deferred target can reach. A
    refusal is a :class:`Refusal`, NEVER the point transition — that ~0.0 delta is what this replaces."""
    # In-body import: `board_delta` / `board_choice` import the contract shapes from here (cycle).
    from common import board_choice
    from common.board_delta import Unmodellable
    try:
        return board_choice.deferred_target(model, option)
    except Unmodellable as gap:
        return refuse(option, str(gap))


def _modelled(model, option: Mapping):
    """The closed-form transition: synthesize the post-action observation, then build a FRESH model —
    fresh rather than patched, because ``state_value``'s per-family memo has no invalidation key."""
    from common import board_delta
    obs = getattr(model, "source_obs", None)
    if not obs:
        return refuse(option, "the model carries no source observation to transition from — it was "
                              "constructed directly rather than through `StateModel.build`")
    context = ((obs.get("select") or {}).get("context"))
    try:
        delta = board_delta.transition(obs, option, seat_index=getattr(model, "my_index", 0),
                                       combat=model.combat, context=context)
    except board_delta.Unmodellable as gap:
        return refuse(option, str(gap))
    return model.rebuilt(delta.obs, reuse_their_side=delta.shares_opponent)


def _clause_gap(model, option: Mapping) -> str:
    """The ENGINE-RESOLVED telemetry line, ``"<card id> <card name>: <gap>"`` (Issue #299). Degrades
    to naming the kind when the option carries no resolvable card reference."""
    card = _option_card(model, option)
    kind = transition_kind(option)
    if card is None:
        return (f"option kind {kind}: no Effect Clause covers this option's card effect, so the "
                f"engine resolved it")
    cid, name = card
    return f"{cid} {name}: no Effect Clause covers this effect, so the engine resolved it"


def _option_card(model, option: Mapping):
    """``(card id, card name)`` for the card an option names, or None. Prefers the HAND reference —
    that is the card whose effect the vocabulary is missing, and a `_PLAY` names its index bare."""
    from common.option_equivalence import AREA_ACTIVE, AREA_BENCH, AREA_DISCARD, AREA_HAND
    obs = getattr(model, "source_obs", None) or {}
    players = ((obs.get("current") or {}).get("players")) or []
    seat = int(getattr(model, "my_index", 0))
    me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    zones = {AREA_HAND: "hand", AREA_DISCARD: "discard",
             AREA_ACTIVE: "active", AREA_BENCH: "bench"}
    for area_key, index_key in (("area", "index"), ("inPlayArea", "inPlayIndex")):
        area = option.get(area_key)
        index = option.get(index_key)
        zone = zones.get(area) if area is not None else ("hand" if area_key == "area" else None)
        if zone is None or not isinstance(index, int) or index < 0:
            continue
        cards = me.get(zone) or ()
        if index >= len(cards) or not cards[index]:
            continue
        cid = cards[index].get("id")
        stat = model.card_stat(cid)
        return cid, (getattr(stat, "name", None) or "?")
    return None


#: Option kinds the parity lane found diverging. **Empty, and that is a MEASUREMENT** — a ruling
#: record, never a scratch pad: an entry is added only with the divergence filed.
QUARANTINED_KINDS: frozenset[int] = frozenset()


def quarantined_kinds() -> frozenset[int]:
    """The READ every consumer makes of :data:`QUARANTINED_KINDS` — a function so a test can
    `monkeypatch` the degraded path without editing a ruling record (ADR-0098 decision 4)."""
    return QUARANTINED_KINDS


# Two exported names changed MEANING in Issue #299 without changing spelling: `ENGINE_ROUTE_KINDS` no
# longer GATES the engine route, and `KIND_SCOPE` is no longer EMITTED by `apply_option`.
__all__: Sequence[str] = (
    "MODELLED", "ENGINE_RESOLVED", "TERMINAL", "REFUSED", "UNDECLARED", "FATES",
    "CHOSEN", "DEALT",
    "KIND_SCOPE", "OPTION_SCOPE", "UNDECLARED_SCOPE", "QUARANTINE_SCOPE", "DEPTH_SCOPE",
    "NONDETERMINISM_SCOPE", "NO_ENGINE_SCOPE",
    "KIND_COVERAGE", "TERMINAL_KINDS", "TRANSITION_KINDS", "ENGINE_ROUTE_KINDS", "REFUSED_KINDS",
    "Footprint", "FOOTPRINTS", "footprint", "commutes", "footprints_commute", "option_footprint",
    "option_serials",
    "EngineResolved", "Refusal", "OutcomeClass", "Expectation", "ScalarTransition", "UnsupportedTransition",
    "transition_kind", "coverage", "fate", "is_terminal", "refuse", "must_expand", "require_model",
    "apply_option", "quarantined_kinds", "QUARANTINED_KINDS",
)
