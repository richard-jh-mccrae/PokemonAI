"""Beam search over within-turn action SEQUENCES, scored by end-state differencing::

    score(sequence) = state_value(end board) + EV(terminal action),   EV(end-turn) = 0

ARMED as the MAIN decider (ADR-0131); it ABSTAINS on a tie rather than overrule the sequencer. Rulings:
ADR-0092 / 0121 / 0129 / 0131; blind spots `data/leaf_lab/wave3-rulings.md` §3b; caps whitelisted at
`sound_rules.composer-budget-caps`."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from common import apply_option as ao
from common import board_choice
from common import board_expectation as bx
from common import snapshot_coverage
from common.board_delta import Unmodellable
from common.option_equivalence import (
    AREA_ACTIVE, AREA_BENCH, AREA_HAND, canonical_keys, class_representatives, fan_out,
    option_equivalence,
)
from common.state_value import attack_ev, attack_ev_legs, state_value
from common.strategy.context import _ATTACH, _ATTACK, _END, _EVOLVE, _PLAY, _RETREAT


#: How many candidate sequences survive each pruning step. **Derived from a TIME budget, not tuned and
#: not derived from acceptance coverage** — the whitelist entry carries the arithmetic.
BEAM_WIDTH = 4

#: Maximum actions BEFORE the terminal action — the deepest commutative block the lattice may reach.
#: Costs nothing over 2 on today's corpus; kept at 4 because that saturation is a seam-coverage fact.
SEQUENCE_DEPTH = 4

#: Beam-admission band, **in prizes**: a candidate within this of the k-th survives. It IS
#: `family_diag.DECIDER_FLOOR`, re-declared because `tools/` must never be a `src/` dependency.
EPSILON = 0.005

def _bench_max(model) -> int:
    """The engine's own ``benchMax`` for my side, or `board_delta`'s fallback — so the two halves of
    "is this deploy legal" cannot disagree about the cap."""
    from common.board_delta import bench_max
    return bench_max(getattr(model, "source_obs", None) or {}, int(getattr(model, "my_index", 0)))


#: ADR-0095 decision 1's six tiers over StateModel facts. The two Pilot-side KO_SCORE nuances are
#: deliberately NOT reproduced: both are score-conditional, and a canonical ORDER must not be.
TIER_INFORMATIVE = 0     # free AND informative: a draw / search / dig, a Bench fill, an evolve
TIER_COMMIT_FREE = 1     # free but COMMITTING: an Item / Stadium play that reveals nothing
TIER_SUPPORTER = 2       # the one-per-turn Supporter
TIER_COMMITMENT = 3      # the blind / costly commitments: the Energy attach, a Tool equip
TIER_SHUFFLE = 4         # a hand-SHUFFLE Supporter — it nukes the hand, so attach before it
TIER_ENDER = 5           # the turn-ENDER, plus Retreat / End / anything uncharacterised

#: The tag that makes a Supporter a hand-NUKE, so an Energy attach sequences ahead of it.
_SHUFFLE_TAG = "shuffle_hand"


@dataclass(frozen=True)
class Step:
    """``option`` is the dict **as applied** — re-resolved and STRIPPED of the origin stamp.
    ``index`` is the depth-0 menu index the composer would COMMIT if this sequence wins."""

    option: Mapping
    index: int
    tier: int
    fate: str
    #: The instance a deferred-target expansion chose. **Advisory, not a commitment**: the follow-up
    #: select RE-DECIDES on the real board through the same :func:`rank_targets` (ADR-0121 D6).
    chosen_target: tuple = ()
    target_classes: int = 0


@dataclass(frozen=True)
class Candidate:
    """``score = leaf + terminal_ev``, with ``EV(end-turn) = 0``. A non-empty ``coverage_gap`` means
    the seam could not price something — REPORTED, never silently competing with a scored sequence."""

    steps: tuple = ()
    terminal: Mapping | None = None
    terminal_index: int | None = None
    leaf: float = 0.0
    terminal_ev: float = 0.0
    score: float = 0.0
    coverage_gap: str = ""
    truncated: int = 0

    @property
    def first_index(self):
        if self.steps:
            return self.steps[0].index
        return self.terminal_index

    def working(self) -> dict:
        return {"leaf": self.leaf, "terminal_ev": self.terminal_ev, "score": self.score,
                "steps": len(self.steps), "truncated": self.truncated,
                "coverage_gap": self.coverage_gap}


@dataclass(frozen=True)
class Bounds:
    """**Both** bounds of one expectation node, plus what the cap dropped. Reported rather than
    reduced: the two are wrong in OPPOSITE directions and the gap is this seam's exposure."""

    index: int
    best: float
    expected: float
    classes: int
    truncated: int
    total_probability: float

    def working(self) -> dict:
        return {"index": self.index, "best": self.best, "expected": self.expected,
                "gap": self.best - self.expected, "classes": self.classes,
                "truncated": self.truncated, "total_probability": self.total_probability}


@dataclass(frozen=True)
class Margin:
    """How close the chosen line's FIRST step came to the beam cutoff. ``in_beam`` is False when it
    survived only on the epsilon band or not at all — the beam-width sizing signal."""

    rank: int | None = None
    k: int = 0
    ranked: int = 0
    in_beam: bool = False
    admitted: bool = False
    always_expand: bool = False
    chosen_delta: float | None = None
    kth_delta: float | None = None
    margin_to_kth: float | None = None

    def working(self) -> dict:
        return {"rank": self.rank, "k": self.k, "ranked": self.ranked, "in_beam": self.in_beam,
                "admitted": self.admitted, "always_expand": self.always_expand,
                "chosen_delta": self.chosen_delta, "kth_delta": self.kth_delta,
                "margin_to_kth": self.margin_to_kth}


@dataclass(frozen=True)
class ComposerResult:
    """``fanned`` spreads each Option-Equivalence class's 1-ply delta over its members; ``order`` is
    the depth-0 ranking. **``chosen`` is None on a menu the seam can price nothing on** — a REPORT."""

    chosen: Candidate | None = None
    candidates: tuple = ()
    margin: Margin = field(default_factory=Margin)
    fanned: tuple = ()
    order: tuple = ()
    admitted: frozenset = frozenset()
    always_expanded: frozenset = frozenset()
    blocks: tuple = ()
    gaps: tuple = ()
    #: Both bounds of every expectation node this run met, newest last; the gap is its exposure.
    bounds: tuple = ()
    stats: dict = field(default_factory=dict)

    def margin_for(self, index: int) -> Margin:
        """The margin telemetry for ANY depth-0 option — the acceptance claim is about the option the
        HUMAN ruled, and measuring the composer's own pick would pass by construction."""
        return _margin_at(self.order, self.always_expanded, self.admitted, self.margin.k, index)


def resolve_against(model, option: Mapping) -> dict | None:
    """``option`` re-pointed at the INSTANCES it named, on the board ``model`` actually holds — None
    when one is gone. A stored dict replayed from a permuted position applies a different play."""
    obs = getattr(model, "source_obs", None) or {}
    seat = int(getattr(model, "my_index", 0))
    named = option.get("playerIndex")
    if named is not None and int(named) != seat:
        return dict(option)                      # an option about THEIR board keys nothing of mine
    players = ((obs.get("current") or {}).get("players")) or []
    me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    out = dict(option)

    hand_serial, body_serial = _origin_serials(option)
    if hand_serial is not None:
        index = _index_of(me.get("hand") or (), hand_serial)
        if index is None:
            return None
        out["index"] = index
    if body_serial is not None:
        for area, zone in ((AREA_ACTIVE, "active"), (AREA_BENCH, "bench")):
            index = _index_of(me.get(zone) or (), body_serial)
            if index is not None:
                out["inPlayArea"], out["inPlayIndex"] = area, index
                break
        else:
            return None
    return out


#: The instance key rides the option DICT, not a parallel map — the dict is what travels through the
#: beam. Private-by-name: a leading underscore is not a legal engine field.
_ORIGIN = "_composer_origin"


def stamp_origin(model, option: Mapping) -> dict:
    """Stamp serial plus card id: fixture serial reuse must not re-point an option to another card."""
    hand_serial, body_serial = ao.option_serials(model, option)
    return {**option, _ORIGIN: (_origin_key(model, option, hand_serial, hand=True),
                                _origin_key(model, option, body_serial, hand=False))}


def _origin_serials(option: Mapping):
    """The stamped instance key, or ``(None, None)``. Unstamped means *"nothing to re-resolve"*,
    never *"resolve it from the current indices"* — that is the silent failure this prevents."""
    origin = option.get(_ORIGIN)
    if not origin:
        return None, None
    return origin[0], origin[1]


def _origin_key(model, option: Mapping, serial, *, hand: bool):
    """``(serial, card id)`` where both facts exist; a bare serial preserves unknown-card handling."""
    if serial is None:
        return None
    obs = getattr(model, "source_obs", None) or {}
    seat = int(getattr(model, "my_index", 0))
    players = ((obs.get("current") or {}).get("players")) or []
    me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    if hand:
        cards, index = me.get("hand") or (), option.get("index")
    else:
        area = "active" if option.get("inPlayArea") == AREA_ACTIVE else "bench"
        cards, index = me.get(area) or (), option.get("inPlayIndex")
    card = cards[index] if isinstance(index, int) and 0 <= index < len(cards) else None
    card_id = card.get("id") if isinstance(card, Mapping) else None
    return (serial, card_id) if card_id is not None else serial


def _index_of(cards, key):
    serial, card_id = key if isinstance(key, tuple) else (key, None)
    for i, card in enumerate(cards or ()):
        if card and card.get("serial") == serial and (card_id is None or card.get("id") == card_id):
            return i
    return None


def strip_origin(option: Mapping) -> dict:
    """Separate from :func:`resolve_against` so the boundary is not a matter of call order."""
    return {k: v for k, v in option.items() if k != _ORIGIN}


def _still_legal(model, option: Mapping) -> bool:
    """Would the engine still offer this option on ``model``'s board? Only the limits an EARLIER STEP
    of this sequence can spend; a first-turn evolve is safe by construction (`docs/rules.md` §3/§4)."""
    kind = ao.transition_kind(option)
    if kind == _RETREAT:
        return not model.retreated
    card = _option_card_stat(model, option)
    if kind == _ATTACH:
        if card is None:
            return False
        if getattr(card, "is_tool", False):
            body = _target_body(model, option)
            return body is not None and not body.tool_ids
        return not model.energy_attached
    if kind == _EVOLVE:
        body = _target_body(model, option)
        return body is not None and not body.new_in_play
    if kind == _PLAY:
        if card is None:
            return False
        if getattr(card, "is_supporter", False):
            return not model.supporter_played
        if getattr(card, "is_stadium", False):
            return not model.stadium_played and model.stadium_id != card.cardId
        if getattr(card, "is_pokemon", False) and not getattr(card, "evolvesFrom", None):
            return len(model.mine.bench) < _bench_max(model)
        return True                              # an Item — no per-turn allowance and no capacity
    return True                                  # terminal kinds and anything the seam refuses


def _option_card_stat(model, option: Mapping):
    """FROM HAND: every §3 allowance is keyed on what is PLAYED, not on what it lands on."""
    obs = getattr(model, "source_obs", None) or {}
    seat = int(getattr(model, "my_index", 0))
    players = ((obs.get("current") or {}).get("players")) or []
    me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    area, index = option.get("area"), option.get("index")
    if area not in (None, AREA_HAND) or not isinstance(index, int) or index < 0:
        return None
    hand = me.get("hand") or ()
    if index >= len(hand) or not hand[index]:
        return None
    return model.card_stat(hand[index].get("id"))


def _target_body(model, option: Mapping):
    area, index = option.get("inPlayArea"), option.get("inPlayIndex")
    if not isinstance(index, int) or index < 0:
        return None
    if area == AREA_ACTIVE:
        active = model.mine.active
        return active if index == 0 else None
    if area == AREA_BENCH:
        bench = model.mine.bench
        return bench[index] if index < len(bench) else None
    return None


#: `trigger` -> the option KIND that clause fires with. `test_composer.py` asserts this covers exactly
#: `snapshot_coverage.CLAUSE_SELECTORS["trigger"]`, so a new value cannot fall through to "no ride".
_TRIGGER_KIND = {"on_attach": _ATTACH, "on_evolve": _EVOLVE, "on_bench_play": _PLAY,
                 "on_attack": _ATTACK}


def _reveal_rides(model, option: Mapping) -> bool:
    """Does a revealing clause actually FIRE here? Narrower than the footprint's *"can this CARD
    reveal at all?"*. Fail closed: an untriggered clause rides a `_PLAY` and no other kind."""
    from common.board_delta import card_clauses
    kind = ao.transition_kind(option)
    card = _option_card_stat(model, option)
    if card is None:
        return kind == _PLAY                       # unreadable: keep the conservative `_PLAY` answer
    for clause in card_clauses(getattr(model, "combat", None), card.cardId) or ():
        values = set(snapshot_coverage.clause_values(clause))
        if not (values & snapshot_coverage.REVEALING_CLAUSES):
            continue
        trigger = clause.get("trigger")
        if trigger is not None:
            if _TRIGGER_KIND.get(trigger) == kind:
                return True
        elif kind == _PLAY:
            return True
    return False


def canonical_tier(model, option: Mapping, footprint=None) -> int:
    """This option's information-before-commitment TIER (ADR-0095 decision 1). TOTAL over the menu
    even though a revealing option can never join a block, so no key falls through to menu position."""
    kind = ao.transition_kind(option)
    if kind in (_ATTACK, _END, _RETREAT):
        return TIER_ENDER
    card = _option_card_stat(model, option)
    # A hand shuffle hides the resulting cards rather than revealing a usable choice.  It therefore
    # must retain the post-attach tier even though its draw clause is marked as a potential revealer.
    if kind == _PLAY and card is not None and getattr(card, "is_supporter", False) \
            and _shuffles_hand(model, card):
        return TIER_SHUFFLE
    fp = footprint if footprint is not None else ao.option_footprint(model, option)
    if fp.reveals_information:
        return TIER_INFORMATIVE
    if kind == _EVOLVE:
        return TIER_INFORMATIVE                  # "evolve a benched Pokemon" rides the free band
    if kind == _ATTACH:
        return TIER_COMMITMENT                   # Energy AND Tool: a Tool is an `_ATTACH` (tier 3)
    if kind == _PLAY and card is not None:
        if getattr(card, "is_supporter", False):
            return TIER_SUPPORTER
        if getattr(card, "is_pokemon", False):
            return TIER_INFORMATIVE              # a Bench fill is free and reveals a better target
        return TIER_COMMIT_FREE                  # an Item / a Stadium: free but committing
    return TIER_ENDER                            # uncharacterised: last, fail closed


def _shuffles_hand(model, card) -> bool:
    functions = getattr(getattr(model, "combat", None), "functions", None)
    if functions is None:
        return False
    try:
        return _SHUFFLE_TAG in (functions.tags(card.cardId) or ())
    except Exception:                            # noqa: BLE001 — an unknown card is not a shuffler
        return False


def canonical_key(model, option: Mapping, index: int, canon: str, footprint=None) -> tuple:
    """``canon`` is the ADR-0103 fingerprint, so permuting the menu invents no new keys."""
    return (canonical_tier(model, option, footprint), canon, index)


def commutative_blocks(model, options: Sequence[Mapping], indices=None) -> tuple:
    """For TELEMETRY — the beam asks :func:`_admissible_in_block` instead. Fail closed."""
    prints = {i: ao.option_footprint(model, options[i])
              for i in (range(len(options)) if indices is None else indices)
              if not ao.is_terminal(options[i])}
    blocks: list[list[int]] = []
    for i in sorted(prints):
        for block in blocks:
            if all(ao.footprints_commute(prints[i], prints[j]) for j in block):
                block.append(i)
                break
        else:
            blocks.append([i])
    return tuple(tuple(b) for b in blocks if len(b) > 1)


def subset_lattice(members: Sequence) -> tuple:
    """Every SUBSET of ``members`` in one canonical order — ``2**n`` tuples, never the
    ``sum(n!/(n-k)!)`` ordered prefixes. The same rule :func:`_admissible_in_block` applies."""
    out = [()]
    for member in members:
        out = out + [prefix + (member,) for prefix in out]
    return tuple(out)


def _admissible_in_block(key, block_keys) -> bool:
    """Only when ``key`` sorts strictly after every member — the rule that turns the beam's tree into
    the SUBSET lattice, generating each subset exactly once instead of merging duplicates after."""
    return all(key > other for other in block_keys)


def terminal_ev(model, option: Mapping) -> tuple:
    """``(EV in prizes, AttackEV or None, coverage-gap reason)`` for a TERMINAL option. ⚠️ Reads
    `AttackEV.total`, never the working-dict sum, which is FROZEN ASYMMETRIC. No leg = a GAP, not 0."""
    kind = ao.transition_kind(option)
    if kind == _END:
        return 0.0, None, ""
    if kind != _ATTACK:
        return 0.0, None, f"option kind {kind} is terminal but is neither attack nor end-turn"
    attack_id = option.get("attackId")
    for leg in attack_ev_legs(model):
        if leg.attack_id == attack_id:
            ev = attack_ev(**leg.kwargs)
            return float(ev.total), ev, ""
    return 0.0, None, (
        f"attack {attack_id!r} has no `attack_ev_legs` leg on this board — its EV is UNKNOWN, and "
        f"pricing it 0.0 would rank a real attack below every scored line")


def continuation_ev(model) -> float:
    """The best terminal action still REACHABLE, in prizes — the second summand of a CUT line
    (ADR-0129). ⚠️ Answers from the BOARD, not the menu, so :func:`_stop_here` must not inherit it."""
    return max((float(attack_ev(**leg.kwargs).total) for leg in attack_ev_legs(model)), default=0.0)


@dataclass(frozen=True)
class ScoredTarget:
    """One instance of a deferred target, scored on the board it produces; ``rank`` is 1-based."""

    rank: int
    leaf: float
    model: object
    fingerprint: tuple = ()
    probability: float = 0.0


@dataclass(frozen=True)
class TargetChoice:
    """``leaf`` is the score that ORDERS — the MAX over the enumeration — while ``expected`` is the
    availability-weighted mean carried alongside as the reported lower bound."""

    scored: tuple = ()
    leaf: float = 0.0
    expected: float = 0.0
    truncated: int = 0
    total_probability: float = 0.0

    @property
    def best(self) -> ScoredTarget | None:
        return self.scored[0] if self.scored else None

    @property
    def runner_up(self) -> float | None:
        return self.scored[1].leaf if len(self.scored) > 1 else None

    def working(self) -> dict:
        return {"classes": len(self.scored), "leaf": self.leaf, "expected": self.expected,
                "gap": self.leaf - self.expected, "runner_up": self.runner_up,
                "truncated": self.truncated, "total_probability": self.total_probability}


def rank_targets(model, expectation) -> TargetChoice:
    """**THE evaluator for a deferred target — one entry point, BOTH sites** (ADR-0121 decision 6):
    the MAIN menu and the follow-up select, which REPLANS rather than replaying a commitment."""
    scored = sorted(
        (ScoredTarget(rank=0, leaf=float(state_value(c.model)), model=c.model,
                      fingerprint=tuple(c.fingerprint or ()), probability=float(c.probability))
         for c in expectation.classes),
        key=lambda s: (-s.leaf, s.fingerprint))
    ranked = tuple(ScoredTarget(rank=n + 1, leaf=s.leaf, model=s.model, fingerprint=s.fingerprint,
                                probability=s.probability) for n, s in enumerate(scored))
    mass = float(expectation.total_probability)
    return TargetChoice(
        scored=ranked,
        leaf=ranked[0].leaf if ranked else 0.0,
        expected=(sum(s.probability * s.leaf for s in ranked) / mass) if mass > 0.0 else 0.0,
        truncated=int(expectation.truncated), total_probability=mass)


def choose_target(model, option: Mapping, *, seat_index=None, cap=None, ranker=None):
    """The MAIN-site front door onto :func:`rank_targets`; None when the space is unmodellable."""
    from common import board_choice
    kwargs = {} if cap is None else {"cap": cap}
    try:
        expectation = board_choice.deferred_target(
            model, dict(option), seat_index=seat_index, ranker=ranker, **kwargs)
    except Unmodellable:
        return None
    return rank_targets(model, expectation)


#: Places :func:`selection_key`'s score leg is compared at — **a float-noise floor, NOT a band, and
#: deliberately not :data:`EPSILON`** (ADR-0128): one ULP decided a corpus frame before it existed.
_SCORE_PLACES = 12


def selection_key(model, candidate: Candidate) -> tuple:
    """The ONE ordering key for choosing among candidates: score, then touched-card Worth, then a
    card-id sort and the menu index. Never falls through to raw generation order."""
    worth, card_id = 0.0, -1
    step = candidate.steps[0] if candidate.steps else None
    option = step.option if step is not None else candidate.terminal
    if option is not None:
        stat = _option_card_stat(model, option)
        if stat is not None:
            card_id = int(getattr(stat, "cardId", -1) or -1)
            worth = float(model.mine.role_worth(stat.cardId))
    index = candidate.first_index
    return (bool(candidate.coverage_gap), -round(candidate.score, _SCORE_PLACES), -worth, card_id,
            index if index is not None else 1 << 30)


@dataclass(frozen=True)
class _Node:
    model: object
    steps: tuple = ()
    used: frozenset = frozenset()
    block: tuple = ()            # canonical keys of the open block's members
    block_prints: tuple = ()     # their footprints, for the pairwise commutativity test
    truncated: int = 0
    leaf: float = 0.0


def compose(model, options: Sequence[Mapping], *, k: int = BEAM_WIDTH, epsilon: float = EPSILON,
            depth: int = SEQUENCE_DEPTH, search_api=None, deterministic=None,
            clauses_cover=None, shed=None) -> ComposerResult:
    """``deterministic`` / ``clauses_cover`` / ``shed`` are caller-supplied per-option seams, each a
    value or an ``option -> value`` callable. **Pure and bit-identical**; wall-clock is not enforced."""
    if int(k) < 1 or int(depth) < 0:
        # Caller error, so it RAISES where a modelling gap refuses. Not pedantry: `k=0` indexes the
        # k-th as [-1] and admits the entire menu — a beam that silently stops being one.
        raise ValueError(
            f"k={k!r}, depth={depth!r}: a beam must keep at least one candidate and cannot search a "
            f"negative number of plies. k=0 would index the k-th candidate as [-1] and admit "
            f"everything, which reads as a working beam while being none.")
    t0 = time.perf_counter()
    obs = getattr(model, "source_obs", None) or {}
    options = list(options or [])
    equiv = option_equivalence(options, obs)
    reps = class_representatives(equiv, len(options))
    canon = canonical_keys(options, obs)
    stamped = [stamp_origin(model, o) for o in options]

    state = _Run(k=k, epsilon=epsilon, depth=depth, search_api=search_api,
                 deterministic=deterministic, clauses_cover=clauses_cover, shed=shed,
                 canon=canon, reps=reps, stamped=stamped)

    root = _Node(model=model, leaf=float(state_value(model)))
    frontier, root_ranked = [root], None
    for ply in range(depth + 1):
        expanded = []
        for node in frontier:
            ranked = _rank(state, node)
            if node is root:
                root_ranked = ranked
            expanded.extend(_expand(state, node, ranked))
        if not expanded:
            break
        if ply == depth:
            state.depth_truncated += len(expanded)
            break
        frontier = _prune_nodes(state, expanded)

    ranked0 = root_ranked or []
    chosen = min(state.candidates, key=lambda c: selection_key(model, c)) \
        if state.candidates else None
    return ComposerResult(
        chosen=chosen,
        candidates=tuple(sorted(state.candidates, key=lambda c: selection_key(model, c))),
        margin=_margin(state, ranked0, chosen),
        fanned=tuple(fan_out([state.one_ply.get(i) for i in range(len(options))], equiv)),
        order=tuple((e.index, e.delta) for e in ranked0 if not e.refused),
        admitted=_admitted_indices(state, ranked0), always_expanded=_free_indices(ranked0),
        blocks=commutative_blocks(model, stamped, reps),
        gaps=tuple(state.gaps),
        bounds=tuple(state.bounds),
        stats={"leaf_evals": state.leaf_evals, "nodes": state.nodes,
               "candidates": len(state.candidates), "truncated": state.truncated,
               "depth_truncated": state.depth_truncated,
               "expectation_nodes": len(state.bounds),
               "expanded_families": state.expanded_families,
               "expansion_children": state.expansion_children,
               "ms": (time.perf_counter() - t0) * 1000.0})


@dataclass
class _Run:
    """A record rather than closure variables, so the helpers below are testable in isolation."""

    k: int
    epsilon: float
    depth: int
    search_api: object
    deterministic: object
    clauses_cover: object
    canon: list
    reps: list
    stamped: list
    #: `None` makes a costed search REFUSE and name the seam, never price its cost as free.
    shed: object = None
    candidates: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    bounds: list = field(default_factory=list)    # both bounds of every expectation node (§S3.5)
    one_ply: dict = field(default_factory=dict)   # depth-0 delta per representative index
    leaf_evals: int = 0
    nodes: int = 0
    truncated: int = 0
    depth_truncated: int = 0
    expanded_families: int = 0        # §S7 D4: options whose deferred target was fanned out
    expansion_children: int = 0       # the instances scored across all of them


def _ask(resolver, option):
    """A callable seam input is asked; anything else passes through."""
    return resolver(option) if callable(resolver) else resolver


def _rank(state: _Run, node: _Node) -> list:
    """Ordered by delta with a deterministic tail, never menu position. Availability is RE-checked."""
    out = []
    for i in state.reps:
        if i in node.used:
            continue
        option = resolve_against(node.model, state.stamped[i])
        if option is None or not _still_legal(node.model, option):
            continue
        entry = _one_ply(state, node, option, i)
        if entry is None:
            continue
        if not node.steps:
            # Recorded HERE, not after admission, so `fanned` answers for every option the menu
            # offered — a None must never mean "pruned" where the caller reads "unfingerprintable".
            state.one_ply[i] = entry.delta
        out.append(entry)
    out.sort(key=lambda e: (e.refused, -float(e.delta or 0.0), e.key))
    return out


@dataclass(frozen=True)
class _Ranked:
    index: int
    option: dict
    key: tuple
    delta: float | None
    after: object            # the model to continue from, or None (terminal / refused / reveal)
    fate: str
    footprint: object
    terminal: bool = False
    reveals: bool = False
    refused: bool = False
    truncated: int = 0
    ev: float = 0.0
    gap: str = ""
    #: The deferred-target expansion this option resolved through, so the `Step` can name WHICH won.
    choice: object = None


def _one_ply(state: _Run, node: _Node, option: dict, index: int):
    """Apply and price one option. CHOSEN outcomes take max; DEALT outcomes take expectation."""
    if ao.is_terminal(option):
        ev, _detail, gap = terminal_ev(node.model, option)
        if gap:
            state.gaps.append(f"{_frame_of(option)}: {gap}")
        return _Ranked(index=index, option=option,
                       key=(TIER_ENDER, state.canon[index], index),
                       delta=ev, after=None, fate=ao.TERMINAL, footprint=ao.Footprint(),
                       terminal=True, ev=ev, gap=gap)
    cover = _ask(state.clauses_cover, option)
    footprint = ao.option_footprint(node.model, option, clauses_cover=cover)
    key = canonical_key(node.model, option, index, state.canon[index], footprint)

    def _refuse(reason: str) -> _Ranked:
        state.gaps.append(f"{_frame_of(option)}: {reason}")
        return _Ranked(index=index, option=option, key=key, delta=None, after=None,
                       fate=ao.REFUSED, footprint=footprint, refused=True, gap=reason)

    try:
        coin = bx.coin_expectation(node.model, option, score=state_value)
    except Unmodellable as gap:
        return _refuse(str(gap))
    if coin is not None:
        state.leaf_evals += len(coin.classes)
        leaf = float(coin.ordering(state_value))
        state.bounds.append(Bounds(index=index, best=float(coin.best(state_value)),
                                   expected=float(coin.expected(state_value)),
                                   classes=len(coin.classes), truncated=0,
                                   total_probability=float(coin.total_probability)))
        return _Ranked(index=index, option=option, key=key, delta=leaf - node.leaf, after=None,
                       fate=ao.MODELLED, footprint=footprint, reveals=True, ev=leaf)

    try:
        scalar = bx.refresh_transition(node.model, option)
    except Unmodellable as gap:
        return _refuse(str(gap))
    if scalar is not None:
        state.leaf_evals += 1
        leaf = float(state_value(scalar.model)) + scalar.scalar
        return _Ranked(index=index, option=option, key=key, delta=leaf - node.leaf, after=None,
                       fate=ao.MODELLED, footprint=footprint, reveals=True, ev=leaf)

    deferred = board_choice.has_deferred_target(
        node.model, option, seat_index=int(getattr(node.model, "my_index", 0)))
    if footprint.reveals_information and _reveal_rides(node.model, option) and not deferred:
        if ao.transition_kind(option) != _PLAY:
            return _refuse(
                "a revealing clause RIDES this option and it is not a `_PLAY`, so neither seam can "
                "price it: `board_expectation` enumerates a played Item/Supporter's search and "
                "refuses a reveal riding another kind, while the point transition consults no "
                "clauses on this kind at all and would apply the structural half while silently "
                "DROPPING the reveal — an under-reported delta, which at ordering time is a pruned "
                "option rather than an undervalued one")
        try:
            result = bx.expectation(node.model, option, shed=state.shed)
        except Unmodellable as gap:
            return _refuse(str(gap))
        state.leaf_evals += len(result.classes)
        try:
            best = float(result.best(state_value))
            lower = float(result.expected(state_value))
            leaf = float(result.ordering(state_value))
        except ValueError as gap:                # an un-enumerated effect: an unknown, not a zero
            return _refuse(str(gap))
        state.truncated += result.truncated
        state.bounds.append(Bounds(index=index, best=best, expected=lower,
                                    classes=len(result.classes), truncated=result.truncated,
                                    total_probability=float(result.total_probability)))
        return _Ranked(index=index, option=option, key=key, delta=leaf - node.leaf, after=None,
                       fate=ao.MODELLED, footprint=footprint, reveals=True,
                       truncated=result.truncated, ev=leaf)

    result = ao.apply_option(node.model, option, depth=len(node.steps),
                             search_api=state.search_api,
                             deterministic=_ask(state.deterministic, option),
                             clauses_cover=cover,
                             expand_deferred_targets=True)
    if ao.must_expand(result):
        return _refuse(f"{result.scope}: {result.reason}")
    if isinstance(result, ao.Expectation):
        # A CHOICE node: score every instance and emit ONE `_Ranked`, so the fan-out is
        # evaluation-time and `k` keeps its pre-expansion meaning. Not a boundary — `after` is set.
        choice = rank_targets(node.model, result)
        state.leaf_evals += len(choice.scored)
        state.expanded_families += 1
        state.expansion_children += len(choice.scored)
        state.truncated += choice.truncated
        state.bounds.append(Bounds(index=index, best=choice.leaf, expected=choice.expected,
                                    classes=len(choice.scored), truncated=choice.truncated,
                                    total_probability=choice.total_probability))
        if choice.best is None:
            return _refuse(
                "the deferred-target space enumerated to zero classes — an un-enumerated effect, "
                "and pricing it 0.0 would rank a real play below every scored line")
        return _Ranked(index=index, option=option, key=key, delta=choice.leaf - node.leaf,
                       after=choice.best.model, fate=ao.MODELLED, footprint=footprint,
                       truncated=choice.truncated, ev=choice.leaf, choice=choice)
    after = ao.require_model(result)
    state.leaf_evals += 1
    leaf = float(state_value(after))
    return _Ranked(index=index, option=option, key=key, delta=leaf - node.leaf, after=after,
                   fate=ao.ENGINE_RESOLVED if isinstance(result, ao.EngineResolved) else ao.MODELLED,
                   footprint=footprint, ev=leaf)


def _step_of(entry: _Ranked) -> Step:
    """One `_Ranked` as the `Step` that leaves this module — the ONE construction site, so the
    origin-stripping and the deferred-target attribution cannot drift between the two callers."""
    choice = entry.choice
    best = None if choice is None else choice.best
    return Step(option=strip_origin(entry.option), index=entry.index, tier=entry.key[0],
                fate=entry.fate,
                chosen_target=() if best is None else best.fingerprint,
                target_classes=0 if choice is None else len(choice.scored))


def _frame_of(option: Mapping) -> str:
    hand, body = _origin_serials(option)
    return f"kind {ao.transition_kind(option)} (hand {hand}, body {body})"


def _admit(state: _Run, ranked: list) -> list:
    """Top-k PLUS anything within :data:`EPSILON` of the k-th — a DIFFERENT mechanism from
    :func:`selection_key`. Terminal and refused entries are admitted UNCONDITIONALLY."""
    free = [e for e in ranked if e.terminal or e.refused]
    scored = [e for e in ranked if not (e.terminal or e.refused)]
    if len(scored) <= state.k:
        return free + scored
    cutoff = scored[state.k - 1].delta - state.epsilon
    return free + [e for e in scored if e.delta >= cutoff]


def _expand(state: _Run, node: _Node, ranked: list) -> list:
    """Turn one node's admitted options into candidates and child nodes. The node ITSELF is always
    emitted; a child that does NOT commute opens a FRESH block, so both orderings are explored."""
    state.nodes += 1
    children = []
    state.candidates.append(_stop_here(state, node))
    for entry in _admit(state, ranked):
        if entry.terminal:
            state.candidates.append(_terminal_candidate(node, entry))
            continue
        if entry.refused or entry.after is None:
            state.candidates.append(_gap_or_reveal_candidate(node, entry))
            continue
        commutes = all(ao.footprints_commute(entry.footprint, fp) for fp in node.block_prints)
        if commutes and node.block and not _admissible_in_block(entry.key, node.block):
            continue                             # this subset already exists in canonical order
        step = _step_of(entry)
        children.append(_Node(
            model=entry.after, steps=node.steps + (step,), used=node.used | {entry.index},
            block=(node.block + (entry.key,)) if commutes else (entry.key,),
            block_prints=(node.block_prints + (entry.footprint,)) if commutes
            else (entry.footprint,),
            truncated=node.truncated + entry.truncated, leaf=node.leaf + entry.delta))
    return children


def _stop_here(state: _Run, node: _Node) -> Candidate:
    """Take ``node``'s steps and stop — ``EV(terminal) = 0``. ⚠️ It does NOT carry
    :func:`continuation_ev`: crediting it would let *"commit nothing"* win a decision outright."""
    return Candidate(steps=node.steps, terminal=None, leaf=node.leaf, terminal_ev=0.0,
                     score=node.leaf, truncated=node.truncated)


def _terminal_candidate(node: _Node, entry: _Ranked) -> Candidate:
    """The leaf is the board the terminal action was reached FROM; its EV is the 2nd summand."""
    return Candidate(steps=node.steps, terminal=strip_origin(entry.option),
                     terminal_index=entry.index, leaf=node.leaf, terminal_ev=entry.ev,
                     score=node.leaf + entry.ev, coverage_gap=entry.gap,
                     truncated=node.truncated)


def _gap_or_reveal_candidate(node: _Node, entry: _Ranked) -> Candidate:
    """A line that STOPS at this option. A REVEAL keeps its `best()` and carries
    :func:`continuation_ev`; a REFUSAL keeps the node's leaf — its value is UNKNOWN, not zero."""
    step = _step_of(entry)
    if entry.refused:
        leaf, ev = node.leaf, 0.0
    else:
        leaf, ev = node.leaf + entry.delta, continuation_ev(node.model)
    return Candidate(steps=node.steps + (step,), terminal=None, leaf=leaf, terminal_ev=ev,
                     score=leaf + ev, coverage_gap=entry.gap,
                     truncated=node.truncated + entry.truncated)


def _prune_nodes(state: _Run, nodes: list) -> list:
    """The same top-k-plus-epsilon rule the option ranking uses — one rule, asked twice."""
    if len(nodes) <= state.k:
        return nodes
    ordered = sorted(nodes, key=lambda n: (-n.leaf, tuple(s.index for s in n.steps)))
    cutoff = ordered[state.k - 1].leaf - state.epsilon
    return [n for n in ordered if n.leaf >= cutoff]


def _margin_at(order: tuple, free: frozenset, admitted: frozenset, k: int, index) -> Margin:
    """The ONE margin computation, so the composer's line and the human's are measured alike."""
    kth = order[k - 1][1] if len(order) >= k else None
    if index is None:
        return Margin(k=k, ranked=len(order), kth_delta=kth)
    rank = next((n + 1 for n, (i, _d) in enumerate(order) if i == index), None)
    delta = next((d for i, d in order if i == index), None)
    return Margin(rank=rank, k=k, ranked=len(order),
                  in_beam=rank is not None and rank <= k and index not in free,
                  admitted=index in admitted, always_expand=index in free,
                  chosen_delta=delta, kth_delta=kth,
                  margin_to_kth=None if (delta is None or kth is None) else delta - kth)


def _free_indices(ranked0: list) -> frozenset:
    return frozenset(e.index for e in ranked0 if e.terminal or e.refused)


def _admitted_indices(state: _Run, ranked0: list) -> frozenset:
    return frozenset(e.index for e in _admit(state, ranked0))


def _margin(state: _Run, ranked0: list, chosen: Candidate | None) -> Margin:
    """The chosen line's first step against the beam cutoff. THREE survival fields: *"did it survive"*
    (``admitted`` / ``always_expand``) and *"did it earn its place by score"* (``in_beam``) differ."""
    # Refusals are retained as free diagnostics, but are unscored unknowns rather than one-ply ranks.
    scored = tuple((e.index, e.delta) for e in ranked0 if not e.refused)
    return _margin_at(scored, _free_indices(ranked0),
                      _admitted_indices(state, ranked0), state.k,
                      None if chosen is None else chosen.first_index)


__all__ = (
    "BEAM_WIDTH", "SEQUENCE_DEPTH", "EPSILON",
    "TIER_INFORMATIVE", "TIER_COMMIT_FREE", "TIER_SUPPORTER", "TIER_COMMITMENT", "TIER_SHUFFLE",
    "TIER_ENDER",
    "Step", "Candidate", "Margin", "Bounds", "ComposerResult", "ScoredTarget", "TargetChoice",
    "compose", "selection_key", "terminal_ev", "continuation_ev", "canonical_tier", "canonical_key",
    "commutative_blocks", "subset_lattice", "resolve_against", "stamp_origin", "strip_origin",
    "rank_targets", "choose_target",
)
