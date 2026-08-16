"""Deck-neutral demand and known-card coverage for Bellman value calculations.

This module describes recipient-specific opportunities, access odds, and optimistic ceilings.
It never assigns decision utility, steps a rules engine, or samples a hidden card.
"""
from __future__ import annotations

from collections import Counter
import copy
from dataclasses import dataclass
from functools import lru_cache
import hashlib
from time import perf_counter

from .damage import bench_reach
from .fetch import REACH, WINDOW, fetch_target_matches
from .energy import ENERGY_COLORLESS, pays_energy_type, provision_units, unmet_cost_slots
from .information import OutcomeGroup, hypergeometric_classes
from .option_equivalence import option_source_card
from .scouting.card_text import name_in_family
from .strategy.context import _ACTIVE, _BENCH


DEFAULT_BENCH_CAPACITY = 5
DEFAULT_ENERGY_CODE = 0
FLOAT_TIE_DIGITS = 12
MINIMUM_BODY_HP = 10
NEXT_STAGE_OFFSET = 1
NEXT_TURN_OPTION_DISCOUNT = 1.0
BENCH_HEAL_VALUE_SHARE = 0.25
HEAL_DAMAGE_PER_VALUE = 200.0
#: A second fetch step is a second place the line breaks. Ordering only: its one job is keeping
#: the front of a chain behind the tutor that reaches the card outright.
CHAIN_STEP_DISCOUNT = 0.5
#: The one need whose answering cards are named by a printed clause rather than by the hint.
NEED_CLAUSE_KIND = "damage_boost"
#: Benching the Pokemon IS the scored action, so its fetch fires; other triggers stay refused.
PLAY_TRIGGER = "on_bench_play"


def _record_id(value) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()[:20]


@lru_cache(maxsize=8192)
def _identity_record_id(identity) -> str:
    return _record_id(identity)


def semantic_action_key(action) -> str:
    # The solver asks for the same identity's key in every ordering pass; identities are
    # immutable, so the digest is memoized rather than recomputed per call.  An identity
    # carrying unhashable parts cannot be memoized; digest it directly.
    identity = action.identity
    try:
        return _identity_record_id(identity)
    except TypeError:
        return _record_id(identity)


@dataclass(frozen=True)
class ActionFocus:
    action_key: str
    family: str
    path_ids: tuple[str, ...]
    score: float
    reason: str
    coverage: tuple[str, ...] = ()


#: Distinct-outcome coverage saturates here so declaration volume cannot dominate ordering.
COVERAGE_DISTINCT_CAP = 3


def outcome_identity(kind, recipient_serial, recipient_card_id, target_card_ids,
                     waypoint) -> str:
    """One desired outcome's identity, keyed on the bound recipient body — never the authoring
    selector or strategy identifier — so equal declarations collapse to one need."""
    targets = ",".join(str(int(card_id)) for card_id in sorted(target_card_ids or ()))
    return f"{kind}|{recipient_serial}|{recipient_card_id}|{targets}|{int(waypoint)}"


@dataclass(frozen=True)
class SequenceCoverage:
    """Strategy coverage of a searched prefix or candidate continuation."""

    tier: tuple[float, float] = (0.0, 0.0)
    outcomes: tuple[str, ...] = ()


def combined_coverage(parts) -> SequenceCoverage:
    parts = tuple(parts)
    tier = max((part.tier for part in parts), default=(0.0, 0.0))
    outcomes = tuple(dict.fromkeys(
        key for part in parts for key in part.outcomes))
    return SequenceCoverage(tier, outcomes)


@dataclass(frozen=True)
class StrategyBeam:
    focused: tuple[ActionFocus, ...]
    safety: tuple[ActionFocus, ...]
    unknown: tuple[dict, ...]
    paths: tuple[dict, ...]
    features: tuple[dict, ...]
    elapsed_ms: float
    exhausted: bool
    held: tuple[ActionFocus, ...] = ()
    inactive: tuple[ActionFocus, ...] = ()


class StrategyBeamBuilder:
    """Order legal actions against one immutable planning-epoch Strategy Snapshot."""

    _URGENCY = {"high": 3.0, "medium": 2.0, "low": 1.0}
    _CONVICTION = {"high": 3.0, "medium": 2.0, "low": 1.0}

    def __init__(self, snapshot, *, effects=None, stats=None, registry=None, width=8,
                 sequence_coverage=False, information_partition=False):
        self.snapshot = snapshot
        self.effects = effects
        self.stats = stats
        self.registry = registry
        self.width = max(1, int(width))
        self.sequence_coverage = bool(sequence_coverage)
        self.information_partition = bool(information_partition)
        #: Outcome identities the searched prefix already advanced; they stop adding coverage.
        self.prefix_outcomes: tuple[str, ...] = ()
        self.last_odds: dict[str, float] = {}
        self.last_reachability: dict[str, str] = {}
        self.last_beam: StrategyBeam | None = None

    @staticmethod
    def hint_outcome(hint) -> str:
        return outcome_identity(
            hint.kind, getattr(hint, "recipient_serial", None),
            getattr(hint, "recipient_card_id", None),
            tuple(getattr(hint, "target_card_ids", ()) or ()),
            int(getattr(hint, "waypoint", 0)))

    def urgency(self, state, hint) -> str:
        turn = int((state.obs.get("current") or {}).get("turn", 0))
        if hint.deadline == "immediate":
            return "high"
        if hint.deadline == "next_turn":
            return "high" if turn > int(self.snapshot.turn) else "low"
        options = tuple((state.obs.get("select") or {}).get("option") or ())
        # An offered attack marks the commit point where the turn is about to be spent; a
        # merely-legal End is on almost every main-phase menu and signals no such urgency.
        closing = any(int(option.get("type", -1)) == 13 for option in options)
        return "high" if closing else "medium"

    def outcome_statuses(self, state) -> tuple[dict, ...]:
        own = self._player(state)
        opponent = self._opponent(state)
        rows = []
        for hint in self.snapshot.hints:
            status = "unknown"
            own_bodies = tuple(own.get("active") or ()) + tuple(own.get("bench") or ())
            opponent_bodies = (tuple(opponent.get("active") or ())
                               + tuple(opponent.get("bench") or ()))
            if hint.kind == "damage_setup":
                target = next(
                    (body for body in opponent_bodies if body
                     and int(body.get("serial", -1)) == hint.recipient_serial), None)
                in_range = int(getattr(hint, "amount", 1))
                # amount > 1 is an authored in-range threshold; the default 1 keeps
                # target-left-the-board as the only satisfaction.
                if target is None or (in_range > 1 and int(target.get("hp", 0)) <= in_range):
                    status = "satisfied"
            elif hint.kind == "deploy" and hint.target_card_ids and any(
                    body and int(body.get("id", -1)) in hint.target_card_ids
                    for body in own.get("bench") or ()):
                status = "satisfied"
            elif hint.kind == "evolve" and hint.target_card_ids and any(
                    body and int(body.get("serial", -1)) == hint.recipient_serial
                    and int(body.get("id", -1)) in hint.target_card_ids
                    for body in own_bodies):
                status = "satisfied"
            elif hint.kind == "heal":
                body = next((body for body in own_bodies if body
                             and int(body.get("serial", -1)) == hint.recipient_serial), None)
                if body and int(body.get("hp", 0)) >= int(body.get("maxHp", body.get("hp", 0))):
                    status = "satisfied"
            if status == "unknown":
                status = self.last_reachability.get(hint.strategy_id, status)
            rows.append({
                "strategy_id": hint.strategy_id,
                "bundle_id": getattr(hint, "bundle_id", None),
                "waypoint": int(getattr(hint, "waypoint", 0)),
                "kind": hint.kind,
                "recipient": getattr(hint, "recipient", None),
                "recipient_serial": getattr(hint, "recipient_serial", None),
                "recipient_card_id": getattr(hint, "recipient_card_id", None),
                "target_card_ids": tuple(getattr(hint, "target_card_ids", ())),
                "urgency": self.urgency(state, hint),
                "conviction": getattr(hint, "conviction", getattr(hint, "confidence", "low")),
                "status": status,
            })
        # A bundle advances one waypoint at a time: hints past the lowest still-live waypoint
        # are held.  Deep search focus (solver deep_strategy) is a separate waypoint effect.
        frontiers: dict[str, int] = {}
        for row in rows:
            if row["bundle_id"] is not None and row["status"] not in {
                    "satisfied", "impossible"}:
                bundle = str(row["bundle_id"])
                frontiers[bundle] = min(
                    frontiers.get(bundle, row["waypoint"]), row["waypoint"])
        for row in rows:
            if (row["bundle_id"] is not None
                    and row["status"] not in {"satisfied", "impossible"}
                    and row["waypoint"] > frontiers[str(row["bundle_id"])]):
                row["status"] = "held"
        return tuple(rows)

    @staticmethod
    def _option(state, action):
        options = tuple((state.obs.get("select") or {}).get("option") or ())
        if len(action.selection) != 1:
            return None
        index = action.selection[0]
        return options[index] if 0 <= index < len(options) else None

    @staticmethod
    def _player(state):
        players = ((state.obs.get("current") or {}).get("players") or ())
        seat = int(getattr(state, "root_seat", 0))
        return players[seat] if 0 <= seat < len(players) and players[seat] else {}

    @staticmethod
    def _opponent(state):
        players = ((state.obs.get("current") or {}).get("players") or ())
        seat = 1 - int(getattr(state, "root_seat", 0))
        return players[seat] if 0 <= seat < len(players) and players[seat] else {}

    def _source_card_id(self, state, action) -> int | None:
        option = self._option(state, action)
        card = option_source_card(option, state.obs)
        return int(card["id"]) if card and card.get("id") is not None else None

    def _recipient_serial(self, state, action) -> int | None:
        option = self._option(state, action)
        if not option:
            return None
        area = option.get("inPlayArea", option.get("area"))
        index = option.get("inPlayIndex", option.get("index"))
        owner = option.get("playerIndex")
        owner = int(getattr(state, "root_seat", 0)) if owner is None else int(owner)
        player = self._player(state) if owner == int(getattr(state, "root_seat", 0)) \
            else self._opponent(state)
        bodies = ((player.get("active") or ()) if area == _ACTIVE else
                  (player.get("bench") or ()) if area == _BENCH else ())
        body = bodies[index] if isinstance(index, int) and 0 <= index < len(bodies) else None
        return int(body["serial"]) if body and body.get("serial") is not None else None

    def _body_by_serial(self, state, serial):
        if serial is None:
            return None
        player = self._player(state)
        bodies = tuple(player.get("active") or ()) + tuple(player.get("bench") or ())
        return next((body for body in bodies if body
                     and int(body.get("serial", -1)) == int(serial)), None)

    def _funding_energy_ids(self, state, hint) -> tuple[int, ...]:
        """Deck Energy that advances a printed attack cost the recipient cannot yet pay.

        An attack's cost is a card fact. Reading it from the stat provider keeps a deck from
        restating it in a declaration, where a half-named cost silently scores the other half
        at zero and nothing catches the drift when the card is reprinted.
        """
        body = self._body_by_serial(state, hint.recipient_serial)
        stat = self.stats.get(body.get("id")) if body and self.stats is not None else None
        if stat is None:
            return ()
        provisions = tuple(body.get("energies") or ())
        owed = {energy_type
                for attack_id in getattr(stat, "attacks", ()) or ()
                for _slot, energy_type in unmet_cost_slots(
                    provisions, getattr(self.stats.attack(attack_id), "energyTypes", ()) or ())}
        if not owed:
            return ()
        # A Colorless slot accepts anything, so a body owing one looks funded by every Energy in
        # the deck -- including one another body needs by type. While a printed TYPE is still
        # owed anywhere, only Energy paying a typed slot counts; Colorless-only bodies still
        # take any Energy, because for them nothing else is true.
        wanted = {energy_type for energy_type in owed
                  if energy_type != ENERGY_COLORLESS} or owed
        return tuple(sorted(
            int(card_id) for card_id, count in state.deck_counts
            if count > 0 and bool(getattr(self.stats.get(card_id), "is_energy", False))
            and any(pays_energy_type(
                int(getattr(self.stats.get(card_id), "energyType", DEFAULT_ENERGY_CODE) or 0),
                energy_type) for energy_type in wanted)))

    def _funds_the_cost(self, state, hint, source_id) -> bool:
        if hint.target_card_ids:
            return source_id in hint.target_card_ids
        eligible = self._funding_energy_ids(state, hint)
        return not eligible or source_id in eligible

    def _eligible_targets(self, state, hint) -> tuple[int, ...]:
        if hint.target_card_ids:
            targets = tuple(card_id for card_id in hint.target_card_ids
                            if dict(state.deck_counts).get(card_id, 0) > 0)
            if hint.kind == "deploy" and self.registry is not None:
                hand = tuple(int(card["id"]) for card in self._player(state).get("hand") or ()
                             if card and card.get("id") is not None)
                available = set(hand) | {
                    int(card_id) for card_id, count in state.deck_counts if count > 0
                }
                # The reachability test belongs to Evolution BASES only: a base is worth
                # searching for while something can still evolve onto it. A Basic with no
                # Line at all is already its own payoff, so it never had a top to lose.
                targets = tuple(
                    base for base in targets
                    if base not in self.registry.line_parents.values()
                    or any(parent == base and top in available
                           for top, parent in self.registry.line_parents.items())
                )
            return targets
        if hint.kind == "fund_attack" and self.stats is not None:
            return self._funding_energy_ids(state, hint) or tuple(
                int(card_id) for card_id, count in state.deck_counts
                if count > 0 and bool(getattr(self.stats.get(card_id), "is_energy", False))
            )
        return self._need_cards(state, hint)

    def _need_cards(self, state, hint) -> tuple[int, ...]:
        """Deck cards whose PRINTED effect answers a need that declares no card ids."""
        if hint.kind != NEED_CLAUSE_KIND or self.effects is None:
            return ()
        return tuple(
            int(card_id) for card_id, count in state.deck_counts if count > 0
            and any(clause.get("kind") == NEED_CLAUSE_KIND
                    for clause in self.effects.clauses(card_id))
        )

    def _chain_reach(self, state, clause, eligible, pool) -> float:
        """One extra hop: this clause fetches a card that ITSELF fetches something eligible."""
        # Meowth ex fetches a Supporter, never the boost card, so it matched nothing directly -
        # yet it fronts a real line. Both accesses multiplied, then discounted below the direct.
        if self.effects is None or self.stats is None:
            return 0.0
        supporter_spent = bool((state.obs.get("current") or {}).get("supporterPlayed"))
        here = int(clause.get("dig", 0) or 0)
        best = 0.0
        for card_id, count in state.deck_counts:
            card_id = int(card_id)
            if count <= 0 or card_id in eligible:
                continue
            link = self.stats.get(card_id)
            if not _matches_on_play(clause, link):
                continue
            # The only link is a Supporter and this turn's Supporter is spent: the line is dead
            # until next turn, so it earns nothing now.
            if supporter_spent and bool(getattr(link, "is_supporter", False)):
                continue
            reach = access_probability(pool, here, (card_id,)) if here else 1.0
            for onward in self.effects.clauses(card_id):
                if onward.get("kind") != "fetch" or onward.get("zone") != "deck":
                    continue
                matching = tuple(target for target in eligible
                                 if _demand_fetch_target_matches(
                                     onward, self.stats.get(target)))
                if not matching:
                    continue
                depth = int(onward.get("dig", 0) or 0)
                onward_odds = access_probability(pool, depth, matching) if depth else 1.0
                best = max(best, reach * onward_odds * CHAIN_STEP_DISCOUNT)
        return best

    def _access_odds(self, state, action, hint) -> float:
        source_id = self._source_card_id(state, action)
        if source_id is None or self.effects is None:
            return 0.0
        source_stat = self.stats.get(source_id) if self.stats is not None else None
        if hint.kind == "low_cost_information_access":
            if bool(getattr(source_stat, "is_supporter", False)) or self.stats is None:
                return 0.0
            pool = tuple(card_id for card_id, count in state.deck_counts for _ in range(count))
            best = 0.0
            for clause in self.effects.clauses(source_id):
                if clause.get("cost_required") or discard_cost(clause):
                    continue
                if clause.get("kind") == "draw":
                    if clause.get("condition") is not None:
                        continue
                    best = max(best, float(int(clause.get("amount", 0) or 0) > 0))
                    continue
                if clause.get("kind") != "fetch" or clause.get("zone") != "deck":
                    continue
                depth = int(clause.get("dig", 0) or 0)
                matching = tuple(card_id for card_id in pool
                                 if _demand_fetch_target_matches(
                                     clause, self.stats.get(card_id)))
                best = max(best, access_probability(pool, depth, matching) if depth else
                           float(bool(matching)))
            return best
        eligible = self._eligible_targets(state, hint)
        if not eligible:
            return 0.0
        pool = tuple(card_id for card_id, count in state.deck_counts for _ in range(count))
        best = 0.0
        for clause in self.effects.clauses(source_id):
            kind = clause.get("kind")
            if kind == "draw":
                best = max(best, access_probability(
                    pool, int(clause.get("amount", 0) or 0), eligible))
            elif kind == "fetch" and clause.get("zone") == "deck":
                matching = tuple(card_id for card_id in eligible
                                 if _demand_fetch_target_matches(
                                     clause, self.stats.get(card_id)))
                depth = int(clause.get("dig", 0) or 0)
                best = max(best, access_probability(pool, depth, matching) if depth else
                           float(bool(matching)))
                best = max(best, self._chain_reach(state, clause, eligible, pool))
            elif kind == "accel" and clause.get("source") == "deck":
                # Energy acceleration is a funding OUT: it reaches the same deck Energy a
                # fetch would, so it earns the same certainty of access.
                if clause.get("trigger") or clause.get("condition"):
                    continue
                matching = tuple(card_id for card_id in eligible
                                 if _accel_target_matches(clause, self.stats.get(card_id)))
                best = max(best, float(bool(matching)))
        return best

    def _priority(self, state, action) -> tuple[
            float, tuple[str, ...], tuple, SequenceCoverage]:
        """Score, matched hint ids, lexicographic search rank, and distinct outcome coverage."""
        matched = []
        advanced: dict[str, tuple[float, float]] = {}
        priority = 0.0
        recipient = self._recipient_serial(state, action)
        source_id = self._source_card_id(state, action)
        source_stat = self.stats.get(source_id) if source_id is not None and self.stats else None
        statuses = {row["strategy_id"]: row for row in self.outcome_statuses(state)}
        tiers: list[tuple[float, float, float]] = []
        for hint in self.snapshot.hints:
            if statuses[hint.strategy_id]["status"] in {"satisfied", "impossible", "held"}:
                continue
            probability = 0.0
            via_access = False
            if (hint.kind == "fund_attack" and action.identity.kind == "attach"
                    and recipient == hint.recipient_serial
                    and self._funds_the_cost(state, hint, source_id)
                    and bool(getattr(source_stat, "is_energy", False))):
                probability = 1.0
            elif (hint.kind == "fund_ability" and action.identity.kind == "attach"
                  and recipient == hint.recipient_serial
                  and (not hint.target_card_ids or source_id in hint.target_card_ids)
                  and bool(getattr(source_stat, "is_energy", False))):
                probability = 1.0
            elif (hint.kind == "use_ability" and action.identity.kind == "ability"
                  and recipient == hint.recipient_serial):
                probability = 1.0
            elif hint.kind == "item_lock" and action.identity.kind == "attack":
                active = next((body for body in self._player(state).get("active") or () if body), {})
                if (self.registry is not None and "item_lock" in self.registry.functions.get(
                        int(active.get("id", 0)), ())):
                    probability = 1.0
            elif (hint.kind == "evolve" and action.identity.kind == "evolve"
                  and recipient == hint.recipient_serial
                  and (not hint.target_card_ids or source_id in hint.target_card_ids)):
                probability = 1.0
            elif (hint.kind in {"heal", "damage_boost"} and action.identity.kind == "play"
                  and self.effects is not None
                  and source_id is not None
                  and any(clause.get("kind") == hint.kind
                          for clause in self.effects.clauses(source_id))):
                probability = 1.0
            elif (hint.kind == "deploy" and action.identity.kind == "play"
                  and (not hint.target_card_ids or source_id in hint.target_card_ids)
                  and bool(getattr(source_stat, "is_pokemon", False))
                  and str(getattr(source_stat, "stage", "")).lower() == "basic"):
                probability = 1.0
            elif (hint.kind == "play_card"
                  and action.identity.kind == "play" and source_id is not None
                  and source_id in hint.target_card_ids):
                probability = 1.0
            elif hint.kind == "damage_setup" and action.identity.kind == "attack":
                option = self._option(state, action) or {}
                attack_id = option.get("attackId")
                attack = (self.stats.attack(attack_id)
                          if self.stats is not None and attack_id is not None else None)
                target_exists = any(
                    int(body.get("serial", -1)) == hint.recipient_serial
                    for body in self._opponent(state).get("bench") or () if body)
                if hint.target_card_ids and target_exists:
                    active = next((body for body in self._player(state).get("active") or ()
                                   if body), {})
                    active_id = int(active.get("id", 0))
                    if (active_id in hint.target_card_ids
                            and bench_reach(attack) > 0):
                        probability = 1.0
                elif target_exists and bench_reach(attack) > 0:
                    probability = 1.0
            elif hint.kind == "status_setup" and action.identity.kind == "attack":
                active = next((body for body in self._player(state).get("active") or () if body), {})
                active_id = int(active.get("id", 0))
                if (self.registry is not None and "confuse" in self.registry.functions.get(
                        active_id, ()) and (not hint.target_card_ids
                                           or active_id in hint.target_card_ids)):
                    probability = 1.0
            elif (hint.kind == "damage_setup" and action.identity.kind == "card"
                  and recipient == hint.recipient_serial):
                probability = 1.0
            elif (action.identity.kind == "card" and source_id is not None
                  and source_id in hint.target_card_ids):
                probability = 1.0
            elif action.identity.kind in {"play", "ability"} and not bool(
                    getattr(source_stat, "is_supporter", False)
                    and (state.obs.get("current") or {}).get("supporterPlayed")):
                probability = self._access_odds(state, action, hint)
                via_access = True
            if probability <= 0.0:
                continue
            matched.append(hint.strategy_id)
            self.last_reachability[hint.strategy_id] = (
                "guaranteed" if probability >= 1.0 else "probabilistic")
            key = semantic_action_key(action)
            self.last_odds[key] = max(self.last_odds.get(key, 0.0), probability)
            urgency = self._URGENCY[self.urgency(state, hint)]
            conviction = self._CONVICTION[getattr(
                hint, "conviction", getattr(hint, "confidence", "low"))]
            priority = max(priority, urgency * 100.0 + conviction * 10.0 + probability)
            tiers.append((urgency, conviction, probability))
            # An access match may only FIND the need; it has not advanced it.  Coverage counts
            # certain direct advances, so one action never counts alternatives it reaches.
            if not via_access:
                outcome = self.hint_outcome(hint)
                incumbent = advanced.get(outcome, (0.0, 0.0))
                advanced[outcome] = max(incumbent, (urgency, conviction))
        if not matched:
            return 0.0, (), (), SequenceCoverage()
        advanced_tier = max(advanced.values(), default=(0.0, 0.0))
        if not self.sequence_coverage:
            return (priority, tuple(sorted(set(matched))), (priority,),
                    SequenceCoverage(advanced_tier, tuple(sorted(advanced))))
        primary = max(row[:2] for row in tiers)
        best_probability = max(row[2] for row in tiers)
        prefix = set(self.prefix_outcomes)
        coverage = tuple(sorted(key for key in advanced if key not in prefix))
        top_tier = (self._URGENCY["high"], self._CONVICTION["high"])
        protected = sum(1 for key in coverage if advanced[key] == top_tier)
        rank = (
            *primary,
            float(min(COVERAGE_DISTINCT_CAP, protected)),
            float(min(COVERAGE_DISTINCT_CAP, len(coverage))),
            best_probability,
        )
        return (priority, tuple(sorted(set(matched))), rank,
                SequenceCoverage(advanced_tier, coverage))

    def _look_class_action(self, state, action) -> bool:
        # An unknown card must not jump the queue: no effects or no source fails OPEN
        # into the commitment class.
        source_id = self._source_card_id(state, action)
        if self.effects is None or source_id is None:
            return False
        return look_class_clauses(self.effects.clauses(source_id))

    def action_priority(self, state, action) -> float:
        return self._priority(state, action)[0]

    def action_coverage(self, state, action) -> SequenceCoverage:
        """Pure per-action projection; fold a sequence's with ``combined_coverage``."""
        return self._priority(state, action)[3]

    def rank_legal(self, state, actions) -> tuple:
        """Strategy-first legal order with stable deterministic completion."""
        actions = tuple(actions)
        beam = self.build(state, actions)
        focus = {row.action_key: index for index, row in enumerate(beam.focused)}
        return tuple(sorted(actions, key=lambda action: (
            focus.get(semantic_action_key(action), len(actions)), action.identity,
            action.selection,
        )))

    def build(self, state, actions, *, ranking=None) -> StrategyBeam:
        started = perf_counter()
        self.last_odds = {}
        # An impossible mark is an epoch-scoped external proof (no in-repo producer yet — a
        # caller-owned contract); every other reachability entry is rebuilt from this build.
        self.last_reachability = {
            strategy_id: status for strategy_id, status in self.last_reachability.items()
            if status == "impossible"}
        focused = []
        ranks: dict[str, tuple] = {}
        safety = []
        unknown = []
        inactive = []
        leading: set[str] = set()
        information_ids = {
            hint.strategy_id for hint in self.snapshot.hints
            if hint.kind == "low_cost_information_access"
        }
        for action in actions:
            key = semantic_action_key(action)
            priority, strategy_ids, rank, coverage = self._priority(state, action)
            if action.identity.kind in {"attack", "end", "retreat"}:
                safety.append(ActionFocus(key, action.identity.kind, (), 0.0, "safety"))
                if priority <= 0.0:
                    continue
            if priority > 0.0:
                if (self.information_partition
                        and information_ids.intersection(strategy_ids)
                        and self._look_class_action(state, action)):
                    leading.add(key)
                ranks[key] = rank
                focused.append(ActionFocus(
                    key, action.identity.kind, strategy_ids, priority, "strategy_hint",
                    coverage.outcomes if self.sequence_coverage else ()))
            else:
                inactive.append(ActionFocus(
                    key, action.identity.kind, (), 0.0, "no_strategy_hint"))
        # A live look is cheaper and reversible, not preferred: a sequencing class ABOVE
        # the ladder, never a rung inside it.  Liveness is the access matcher's.
        focused = tuple(sorted(
            focused, key=lambda row: (
                0 if row.action_key in leading else 1,
                tuple(-value for value in ranks[row.action_key]),
                (0 if row.family == "evolve" else
                 1 if information_ids.intersection(row.path_ids) else
                 2 if row.family == "attach" else 3),
                row.action_key,
            ))[:self.width])
        elapsed = (perf_counter() - started) * 1000.0
        statuses = self.outcome_statuses(state)
        self.last_beam = StrategyBeam(
            focused, tuple(safety), tuple(unknown), tuple(statuses), (), elapsed, False,
            (), tuple(inactive),
        )
        return self.last_beam


def look_class_clauses(clauses) -> bool:
    """A look digs a bounded deck slice; a whole-deck tutor (or pure draw) is a commitment."""
    fetches = tuple(clause for clause in clauses if clause.get("kind") == "fetch")
    return bool(fetches) and all(clause.get("dig") for clause in fetches)


def access_probability(pool_ids, draws: int, eligible_ids) -> float:
    eligible = tuple(sorted(set(int(card_id) for card_id in eligible_ids)))
    if draws <= 0 or not eligible:
        return 0.0
    classes = hypergeometric_classes(
        pool_ids, draws, (OutcomeGroup("demand", eligible),))
    return sum(outcome.probability for outcome in classes if outcome.counts[0] > 0)


def _accel_target_matches(clause, stat) -> bool:
    """An accel clause reaches Basic Energy, optionally one printed type."""
    if not bool(getattr(stat, "is_basic_energy", False)):
        return False
    required_type = clause.get("energy_type")
    return required_type is None or getattr(stat, "energyType", None) == required_type


def _matches_on_play(clause, stat) -> bool:
    """As ``_demand_fetch_target_matches``, but a bench-play trigger does not disqualify."""
    # That matcher refuses every triggered clause, right for a rider we do not control. Benching
    # Meowth ex IS the scored action, so refusing its fetch hides a line rather than pricing risk.
    if clause.get("trigger") == PLAY_TRIGGER:
        clause = {key: value for key, value in clause.items() if key != "trigger"}
    return _demand_fetch_target_matches(clause, stat)


def _demand_fetch_target_matches(clause, stat) -> bool:
    if clause.get("trigger") or clause.get("condition"):
        return False
    family = clause.get("name_family")
    if family and not name_in_family(getattr(stat, "name", None), family):
        return False
    base = {key: value for key, value in clause.items()
            if key not in {"dig", "name_family"}}
    reading = WINDOW if base.get("target") == "supporter" else REACH
    return fetch_target_matches(base, stat, reading=reading)


@dataclass(frozen=True)
class DemandSlot:
    """One board demand and the direct card identities that can satisfy it."""

    key: str
    direct: tuple[tuple[int, float], ...]
    timing: str = "immediate"
    recipient: str = ""
    capability: str = ""
    slot: str = ""
    ceiling: float = 0.0
    alternative: str = ""


@dataclass(frozen=True)
class CoverageEdge:
    """A card's value when assigned to one demand."""

    demand_index: int
    value: float
    fetched_target: int | None = None
    exclusive_group: str = ""
    alternative: str = ""
    constraints: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ResolvedAssignment:
    """Maximum non-duplicated assignment over card-to-demand coverage."""

    value: float
    covered_mask: int
    used_card_mask: int = 0


@dataclass(frozen=True)
class RetainedOption:
    """A deterministic next-turn option requiring visible hand positions."""

    key: str
    required_cards: tuple[int, ...]
    value: float
    description: str


@dataclass(frozen=True)
class RetainedAssignment:
    """Best compatible set of deterministic next-turn options."""

    value: float
    options: tuple[RetainedOption, ...]


def body_rows(player):
    for area in ("active", "bench"):
        for index, body in enumerate(player.get(area) or ()):
            if body:
                yield area, index, body


def discard_cost(clause) -> int:
    cost = str(clause.get("cost") or "")
    if not cost.startswith("discard_"):
        return 0
    try:
        return max(0, int(cost.split("_", 1)[1]))
    except (TypeError, ValueError):
        return 0


def coverage_signature(edges: dict[int, float]) -> tuple[tuple[int, float], ...]:
    return tuple(sorted((int(index), round(float(value), FLOAT_TIE_DIGITS))
                        for index, value in edges.items() if value > 0.0))


def best_assignment(signatures, demand_count: int, *, target_counts=None) -> ResolvedAssignment:
    """Assign tokens to demands without reusing a fetched deck target.

    Plain ``(demand_index, value)`` pairs remain valid direct-resource edges. ``CoverageEdge`` adds
    an optional fetched target; its limited count is consumed only when that edge is selected.
    """
    target_counts = target_counts or {}
    target_ids = tuple(sorted(int(card_id) for card_id, count in target_counts.items() if count > 0))
    target_positions = {card_id: index for index, card_id in enumerate(target_ids)}
    initial_counts = tuple(int(target_counts[card_id]) for card_id in target_ids)
    dp = {(0, initial_counts, ()): (0.0, 0)}
    for card_index, signature in enumerate(signatures):
        advanced = dict(dp)
        for (mask, available, alternatives), (value, used) in dp.items():
            for raw_edge in signature:
                if isinstance(raw_edge, CoverageEdge):
                    demand_index, edge_value, target, group, alternative = (
                        raw_edge.demand_index, raw_edge.value, raw_edge.fetched_target,
                        raw_edge.exclusive_group, raw_edge.alternative)
                    constraints = raw_edge.constraints
                else:
                    demand_index, edge_value = raw_edge
                    target = None
                    group = alternative = ""
                    constraints = ()
                bit = 1 << demand_index
                if mask & bit:
                    continue
                selected = dict(alternatives)
                choices = constraints + (((group, alternative),) if group else ())
                if any(choice_group in selected and selected[choice_group] != choice
                       for choice_group, choice in choices):
                    continue
                selected.update(choices)
                next_available = available
                if target is not None:
                    position = target_positions.get(int(target))
                    if position is None or available[position] <= 0:
                        continue
                    next_available = (*available[:position], available[position] - 1,
                                      *available[position + 1:])
                new_mask = mask | bit
                candidate = (value + edge_value, used | (1 << card_index))
                state = (new_mask, next_available, tuple(sorted(selected.items())))
                previous = advanced.get(state)
                if (previous is None or
                        (round(candidate[0], FLOAT_TIE_DIGITS), candidate[1])
                        > (round(previous[0], FLOAT_TIE_DIGITS), previous[1])):
                    advanced[state] = candidate
        dp = advanced
    (mask, _available, _alternatives), (value, used) = max(
        dp.items(), key=lambda row: (round(row[1][0], FLOAT_TIE_DIGITS), row[0][0], row[1][1]))
    return ResolvedAssignment(value, mask, used)


def best_retained_assignment(options: tuple[RetainedOption, ...]) -> RetainedAssignment:
    """Weighted set packing over visible cards and mutually exclusive opportunity keys."""
    if not options:
        return RetainedAssignment(0.0, ())
    keys = {key: index for index, key in enumerate(sorted(
        {option.key for option in options}))}
    dp: dict[tuple[int, int], tuple[float, tuple[RetainedOption, ...]]] = {(0, 0): (0.0, ())}
    for option in options:
        card_mask = sum(1 << index for index in option.required_cards)
        key_mask = 1 << keys[option.key]
        advanced = dict(dp)
        for (used_cards, used_keys), (value, chosen) in dp.items():
            if used_cards & card_mask or used_keys & key_mask:
                continue
            state = (used_cards | card_mask, used_keys | key_mask)
            candidate = (value + option.value, (*chosen, option))
            previous = advanced.get(state)
            if previous is None or round(candidate[0], FLOAT_TIE_DIGITS) > round(
                    previous[0], FLOAT_TIE_DIGITS):
                advanced[state] = candidate
        dp = advanced
    value, chosen = max(dp.values(), key=lambda row: (
        round(row[0], FLOAT_TIE_DIGITS), tuple(option.description for option in row[1])))
    return RetainedAssignment(value, chosen)


class DemandModel:
    """Derive immediate demands and deterministic next-turn visible-hand options."""

    def __init__(self, registry, family_evaluator, *, effects=None, stats=None):
        self.registry = registry
        self.family_evaluator = family_evaluator
        self.effects = effects
        self.stats = stats

    def stat(self, card_id):
        return self.stats.get(int(card_id)) if self.stats is not None and card_id is not None else None

    def potential(self, observation):
        return self.family_evaluator(observation)

    def operation_gain(self, before, after) -> float:
        return max(0.0, float(self.potential(after).total - self.potential(before).total))

    def immediate(self, observation, seat: int) -> tuple[DemandSlot, ...]:
        current = observation.get("current") or {}
        players = current.get("players") or ()
        mine = players[seat] if len(players) > seat else {}
        demands: list[DemandSlot] = []
        rows = tuple(body_rows(mine))

        for area, index, body in rows:
            timing = "next_turn" if body.get("appearThisTurn") else "immediate"
            target = self._next_stage(body.get("id"))
            if target is None:
                continue
            evolved = self._evolve(observation, seat, area, index, target)
            gain = self.operation_gain(observation, evolved)
            if gain > 0.0:
                recipient = self._recipient(area, index, body)
                demands.append(DemandSlot(
                    f"evolve:{recipient}:{target}", ((target, gain),),
                    timing=timing, recipient=recipient, capability="evolve",
                    slot=str(target), ceiling=gain))

        funding_timing = "next_turn" if current.get("energyAttached") else "immediate"
        candidates = tuple(
            (int(card_id), self.stat(card_id)) for card_id in self.registry.facts
            if self.stat(card_id) is not None
            and getattr(self.stat(card_id), "is_energy", False))
        for area, index, body in rows:
            body_stat = self.stat(body.get("id"))
            attacks = tuple(getattr(body_stat, "attacks", ()) or ()) if body_stat else ()
            recipient = self._recipient(area, index, body)
            gains = {}
            for candidate, energy_stat in candidates:
                attached = copy.deepcopy(observation)
                target_body = attached["current"]["players"][seat][area][index]
                units = self._energy_units(candidate, target_body)
                energy_type = getattr(energy_stat, "energyType", None)
                code = DEFAULT_ENERGY_CODE if energy_type is None else int(energy_type)
                target_body.setdefault("energies", []).extend([code] * units)
                target_body.setdefault("energyCards", []).append({"id": candidate})
                gains[candidate] = self.operation_gain(observation, attached)
            for attack_id in attacks:
                attack = (self.stats.attack(attack_id)
                          if self.stats is not None and hasattr(self.stats, "attack") else None)
                if attack is None:
                    continue
                requirements = tuple(getattr(attack, "energyTypes", ()) or ())
                if not requirements:
                    requirements = (ENERGY_COLORLESS,) * int(getattr(attack, "cost", 0) or 0)
                missing_slots = unmet_cost_slots(body.get("energies") or (), requirements)
                allocations = {}
                for candidate, energy_stat in candidates:
                    compatible = sum(
                        pays_energy_type(
                            getattr(energy_stat, "energyType", DEFAULT_ENERGY_CODE)
                            if getattr(energy_stat, "energyType", None) is not None
                            else DEFAULT_ENERGY_CODE,
                            required_type)
                        for _slot_index, required_type in missing_slots
                    )
                    supplied = min(self._energy_units(candidate, body), compatible)
                    if supplied > 0 and gains[candidate] > 0.0:
                        allocations[candidate] = gains[candidate] / supplied
                for slot_index, required_type in missing_slots:
                    direct = tuple(sorted(
                        (candidate, allocations[candidate])
                        for candidate, energy_stat in candidates
                        if candidate in allocations
                        if pays_energy_type(
                            getattr(energy_stat, "energyType", DEFAULT_ENERGY_CODE)
                            if getattr(energy_stat, "energyType", None) is not None
                            else DEFAULT_ENERGY_CODE,
                            required_type)
                    ))
                    if not direct:
                        continue
                    slot = f"{slot_index}:{required_type}"
                    demands.append(DemandSlot(
                        f"fund_attack:{recipient}:{attack_id}:{slot}", direct,
                        timing=funding_timing, recipient=recipient,
                        capability="fund_attack", slot=slot,
                        ceiling=max(value for _card_id, value in direct),
                        alternative=str(attack_id)))

        for area, index, body in rows:
            recipient = self._recipient(area, index, body)
            heal_edges = {}
            for card_id in self.registry.facts:
                clauses = tuple(self.effects.clauses(card_id)) if self.effects is not None else ()
                gains = [self._heal_gain(observation, seat, clause, target=(area, index))
                         for clause in clauses if clause.get("kind") == "heal"]
                gain = max(gains, default=0.0)
                if gain > 0.0:
                    heal_edges[int(card_id)] = gain
            if heal_edges:
                damage = max(0, int(body.get("maxHp", body.get("hp", 0)))
                             - int(body.get("hp", 0)))
                band = str((damage // 30) * 30)
                ceiling = max(heal_edges.values())
                demands.append(DemandSlot(
                    f"heal:{recipient}:{band}", tuple(sorted(heal_edges.items())),
                    recipient=recipient, capability="heal", slot=band, ceiling=ceiling))

        bench_space = max(0, int(mine.get("benchMax", DEFAULT_BENCH_CAPACITY))
                          - len(mine.get("bench") or ()))
        for line in self.registry.lines:
            if not line or bench_space <= 0:
                continue
            base, payoff = int(line[0]), int(line[-1])
            desired = max((route.count(payoff) for route in self.registry.prize_routes), default=1)
            present = sum(int(body.get("id", 0)) in line for _area, _index, body in rows)
            missing = min(bench_space, max(0, desired - present))
            if missing <= 0:
                continue
            deployed = copy.deepcopy(observation)
            stat = self.stat(base)
            hp = int(getattr(stat, "hp", MINIMUM_BODY_HP) or MINIMUM_BODY_HP)
            deployed["current"]["players"][seat].setdefault("bench", []).append(
                {"id": base, "hp": hp, "maxHp": hp, "appearThisTurn": True,
                 "preEvolution": [], "energies": [], "energyCards": [], "tools": []})
            gain = self.operation_gain(observation, deployed)
            if gain > 0.0:
                line_key = "-".join(str(card_id) for card_id in line)
                first_slot = len(mine.get("bench") or ())
                demands.extend(DemandSlot(
                    f"deploy:{line_key}:{first_slot + offset}", ((base, gain),),
                    recipient=line_key, capability="deploy", slot=str(first_slot + offset),
                    ceiling=gain)
                    for offset in range(missing))
        return tuple(demands)

    @staticmethod
    def _recipient(area: str, index: int, body) -> str:
        return str(body.get("serial", f"{area}:{index}:{body.get('id', 0)}"))

    def _heal_gain(self, observation, seat: int, clause: dict, *, target=None) -> float:
        if clause.get("rider") not in (None, "bounce_energy_to_hand"):
            return 0.0
        restriction = clause.get("restriction")
        if restriction not in (None, "active_only", "mega_only"):
            return 0.0
        condition = clause.get("condition")
        if condition not in (None, "energy_3_plus", "remaining_hp_30_or_less",
                             "played_supporter_this_turn"):
            return 0.0
        current = observation.get("current") or {}
        players = current.get("players") or ()
        mine = players[seat] if len(players) > seat else {}
        candidates = list(body_rows(mine))
        if target is not None:
            candidates = [row for row in candidates if row[:2] == target]
        if restriction == "active_only":
            candidates = [row for row in candidates if row[0] == "active"]
        elif restriction == "mega_only":
            candidates = [row for row in candidates
                          if bool(getattr(self.stat(row[2].get("id")), "megaEx", False))]
        if condition == "played_supporter_this_turn" and not current.get("supporterPlayed"):
            return 0.0

        def eligible(body):
            if condition == "energy_3_plus" and len(body.get("energyCards") or ()) < 3:
                return False
            if condition == "remaining_hp_30_or_less" and int(body.get("hp", 0)) > 30:
                return False
            return int(body.get("hp", 0)) < int(body.get("maxHp", body.get("hp", 0)))

        candidates = [row for row in candidates if eligible(row[2])]
        groups = (tuple(candidates),) if clause.get("each_of") else tuple((row,) for row in candidates)
        best = 0.0
        for group in groups:
            healed = copy.deepcopy(observation)
            gain = 0.0
            for area, index, original in group:
                body = healed["current"]["players"][seat][area][index]
                maximum = int(body.get("maxHp", body.get("hp", 0)))
                amount = maximum if clause.get("amount") == "all" else int(clause.get("amount", 0))
                restored = min(maximum - int(original.get("hp", 0)), amount)
                gain += restored / HEAL_DAMAGE_PER_VALUE * (
                    1.0 if area == "active" else BENCH_HEAL_VALUE_SHARE)
                body["hp"] = min(maximum, int(body.get("hp", 0)) + amount)
                gain = max(gain, self.operation_gain(observation, healed))
                if clause.get("rider") == "bounce_energy_to_hand":
                    player = healed["current"]["players"][seat]
                    bounced = tuple(body.get("energyCards") or ())
                    if player.get("hand") is None:
                        player["handCount"] = int(player.get("handCount", 0) or 0) + len(bounced)
                    else:
                        player.setdefault("hand", []).extend(bounced)
                    body["energyCards"] = []
                    body["energies"] = []
            gain = max(gain, self.operation_gain(observation, healed))
            best = max(best, gain)
        return best

    def coverage_slots(self, card_id: int, demands: tuple[DemandSlot, ...], *,
                       supporter_available: bool, discard_capacity: int,
                       available_targets=None, recipient: str | None = None,
                       provision_units: int = 1, recipient_units=None,
                       resource_group: str = "") -> tuple[tuple[CoverageEdge, ...], ...]:
        """Independent resources a card can supply, respecting printed fetch capacity.

        A multi-target fetch contributes one assignment token per printed target.  The tokens are
        capped by matching targets still available in the deck, so a Tutor is never an out once all
        of its relevant targets are visible, discarded, or known prized.
        """
        edges = {index: dict(demand.direct).get(int(card_id), 0.0)
                 for index, demand in enumerate(demands)
                 if recipient is None or demand.recipient == recipient}
        edges = {index: value for index, value in edges.items() if value > 0.0}
        def edge(index, value, target=None, constraints=()):
            demand = demands[index]
            group = (f"{demand.recipient}:{demand.capability}"
                     if demand.alternative else "")
            return CoverageEdge(
                index, value, target, group, demand.alternative, constraints)

        direct = tuple(edge(index, value) for index, value in sorted(edges.items()))
        stat = self.stat(card_id)
        if stat is not None and getattr(stat, "is_energy", False):
            if recipient is None and recipient_units is not None:
                tokens = []
                for unit_index in range(max(recipient_units.values(), default=0)):
                    token = tuple(
                        edge(index, value, constraints=(
                            (f"energy:{resource_group}", demands[index].recipient),))
                        for index, value in sorted(edges.items())
                        if int(recipient_units.get(demands[index].recipient, 1)) > unit_index
                    )
                    if token:
                        tokens.append(token)
                return tuple(tokens)
            units = max(1, int(provision_units))
            return tuple(direct for _ in range(units)) if direct else ()
        if stat is None or getattr(stat, "is_pokemon", False):
            return (direct,) if direct else ()
        if getattr(stat, "is_supporter", False) and not supporter_available:
            return (direct,) if direct else ()
        tokens = []
        clauses = tuple(self.effects.clauses(card_id)) if self.effects is not None else ()
        for clause in clauses:
            kind = clause.get("kind")
            if kind == "fetch":
                if clause.get("zone") != "deck":
                    continue
                if not all(not clause.get(field) for field in
                           ("trigger", "dig", "condition", "name_family")):
                    continue
                if bool(clause.get("cost_required")) and discard_cost(clause) > discard_capacity:
                    continue

                def matches(target, clause=clause):
                    return fetch_target_matches(clause, self.stat(target), reading=REACH)
            elif kind == "accel":
                # Energy acceleration reaches the same deck Energy a fetch would; without this
                # token an accelerator counts as zero outs in every coverage question.
                if clause.get("source") != "deck":
                    continue
                if clause.get("trigger") or clause.get("condition"):
                    continue

                def matches(target, clause=clause):
                    return _accel_target_matches(clause, self.stat(target))
            else:
                continue
            reachable = tuple(
                edge(index, value, int(target))
                for index, demand in enumerate(demands)
                for target, value in demand.direct
                if (matches(target)
                    and (available_targets is None
                         or int(available_targets.get(int(target), 0)) > 0))
            )
            matching_targets = {
                edge.fetched_target for edge in reachable
            }
            remaining_targets = (sum(int(available_targets.get(target, 0))
                                     for target in matching_targets)
                                 if available_targets is not None else len(matching_targets))
            printed_capacity = max(1, int(clause.get("amount", 1) or 1))
            for _ in range(min(printed_capacity, remaining_targets)):
                if reachable:
                    tokens.append(reachable)
        return tuple(token for token in (direct, *tokens) if token)

    def supply_context(self, state, action) -> tuple[int | None, str | None, int]:
        if len(action.selection) != 1 or action.identity.kind not in {"play", "attach", "evolve"}:
            return None, None, 1
        options = tuple((state.obs.get("select") or {}).get("option") or ())
        option_index = action.selection[0]
        option = options[option_index] if 0 <= option_index < len(options) else {}
        players = (state.obs.get("current") or {}).get("players") or ()
        mine = players[state.root_seat] if state.root_seat < len(players) else {}
        hand = mine.get("hand") or ()
        hand_index = option.get("index")
        if not isinstance(hand_index, int) or not 0 <= hand_index < len(hand) or not hand[hand_index]:
            return None, None, 1
        card_id = int(hand[hand_index]["id"])
        if action.identity.kind == "play":
            return card_id, None, 1
        area = option.get("inPlayArea")
        index = option.get("inPlayIndex")
        zone = "active" if area == 4 else "bench" if area == 5 else None
        bodies = mine.get(zone) or () if zone is not None else ()
        if not isinstance(index, int) or not 0 <= index < len(bodies) or not bodies[index]:
            return card_id, None, 1
        body = bodies[index]
        recipient = self._recipient(zone, index, body)
        units = self._energy_units(card_id, body) if action.identity.kind == "attach" else 1
        return card_id, recipient, units

    def energy_units_by_recipient(self, observation, seat: int, card_id: int) -> dict[str, int]:
        players = (observation.get("current") or {}).get("players") or ()
        mine = players[seat] if seat < len(players) else {}
        return {
            self._recipient(area, index, body): self._energy_units(card_id, body)
            for area, index, body in body_rows(mine)
        }

    def uncovered_by_hand(self, demands: tuple[DemandSlot, ...], hand_ids, *,
                          supporter_available: bool, discard_capacity: int,
                          available_targets=None, observation=None,
                          seat: int = 0) -> tuple[DemandSlot, ...]:
        signatures = []
        for resource_index, card_id in enumerate(hand_ids):
            stat = self.stat(card_id)
            recipient_units = (self.energy_units_by_recipient(observation, seat, card_id)
                               if observation is not None and stat is not None
                               and getattr(stat, "is_energy", False) else None)
            signatures.extend(self.coverage_slots(
                int(card_id), demands,
                supporter_available=supporter_available,
                discard_capacity=discard_capacity,
                available_targets=available_targets,
                recipient_units=recipient_units,
                resource_group=f"held:{resource_index}"))
        assignment = best_assignment(signatures, len(demands), target_counts=available_targets)
        return tuple(demand for index, demand in enumerate(demands)
                     if not assignment.covered_mask & (1 << index))

    def covered_by_hand_value(self, demands: tuple[DemandSlot, ...], hand_ids, *,
                              supporter_available: bool, discard_capacity: int,
                              available_targets=None, observation=None, seat: int = 0) -> float:
        signatures = []
        for resource_index, card_id in enumerate(hand_ids):
            stat = self.stat(card_id)
            recipient_units = (self.energy_units_by_recipient(observation, seat, card_id)
                               if observation is not None and stat is not None
                               and getattr(stat, "is_energy", False) else None)
            signatures.extend(self.coverage_slots(
                int(card_id), demands,
                supporter_available=supporter_available,
                discard_capacity=discard_capacity,
                available_targets=available_targets,
                recipient_units=recipient_units,
                resource_group=f"held:{resource_index}"))
        return best_assignment(
            signatures, len(demands), target_counts=available_targets).value

    def next_turn_retained(self, observation, seat: int, hand_ids) -> RetainedAssignment:
        """Value deterministic next-turn uses of cards already visible now."""
        projected = self._next_turn_observation(observation, seat, hand_ids)
        original_player = observation["current"]["players"][seat]
        appeared = {(area, index) for area, index, body in body_rows(original_player)
                    if body.get("appearThisTurn")}
        options: list[RetainedOption] = []
        hand = projected["current"]["players"][seat].get("hand") or ()

        for area, index in sorted(appeared):
            body = projected["current"]["players"][seat][area][index]
            target = self._next_stage(body.get("id"))
            if target is None:
                continue
            for hand_index, card in enumerate(hand):
                if not card or int(card.get("id", 0)) != target:
                    continue
                evolved = self._evolve(projected, seat, area, index, target,
                                       consumed_cards=(hand_index,))
                gain = self.operation_gain(projected, evolved) * NEXT_TURN_OPTION_DISCOUNT
                if gain <= 0.0:
                    continue
                key = f"develop:{area}:{index}"
                option = RetainedOption(key, (hand_index,), gain,
                                        f"evolve:{area}:{index}:{target}")
                options.append(option)

        return best_retained_assignment(tuple(options))

    def new_next_turn_demands(self, observation, seat: int, *, current=None) -> tuple[DemandSlot, ...]:
        """Demands that first become actionable after turn allowances reset."""
        current = self.immediate(observation, seat) if current is None else tuple(current)
        deferred = tuple(demand for demand in current if demand.timing == "next_turn")
        if deferred:
            return deferred
        if current:
            return ()
        projected = self._next_turn_observation(observation, seat, ())
        return self.immediate(projected, seat)

    def _next_stage(self, card_id) -> int | None:
        card_id = int(card_id or 0)
        for line in self.registry.lines:
            if card_id in line[:-1]:
                return int(line[line.index(card_id) + NEXT_STAGE_OFFSET])
        return None

    def _evolve(self, observation, seat: int, area: str, index: int, target: int, *,
                consumed_cards: tuple[int, ...] = ()):
        evolved = copy.deepcopy(observation)
        self._remove_hand_positions(evolved, seat, consumed_cards)
        body = evolved["current"]["players"][seat][area][index]
        previous = int(body.get("id", 0))
        target_stat = self.stat(target)
        old_max = int(body.get("maxHp", body.get("hp", 0)) or 0)
        damage = max(0, old_max - int(body.get("hp", old_max) or 0))
        body.setdefault("preEvolution", []).append({"id": previous})
        body["id"] = int(target)
        body["appearThisTurn"] = True
        if target_stat is not None and int(getattr(target_stat, "hp", 0) or 0) > 0:
            body["maxHp"] = int(target_stat.hp)
            body["hp"] = max(MINIMUM_BODY_HP, int(target_stat.hp) - damage)
        return evolved

    def _energy_units(self, card_id: int, body) -> int:
        return provision_units(
            self.registry.functions, card_id, evolved=bool(body.get("preEvolution")))

    @staticmethod
    def _tag_amount(tags, prefix: str) -> int:
        amounts = []
        for tag in tags:
            if not str(tag).startswith(prefix):
                continue
            try:
                amounts.append(max(0, int(str(tag).split(":", 1)[1])))
            except ValueError:
                continue
        return max(amounts, default=0)

    @staticmethod
    def _remove_hand_positions(observation, seat: int, positions) -> None:
        positions = tuple(positions)
        if not positions:
            return
        player = observation["current"]["players"][seat]
        hand = player.get("hand")
        if hand is None:
            return
        for position in sorted(set(int(value) for value in positions), reverse=True):
            if 0 <= position < len(hand):
                hand.pop(position)
        player["handCount"] = len(hand)

    @staticmethod
    def _next_turn_observation(observation, seat: int, hand_ids):
        projected = copy.deepcopy(observation)
        current = projected["current"]
        current["turn"] = int(current.get("turn", 0)) + 1
        current["supporterPlayed"] = False
        current["energyAttached"] = False
        current["retreated"] = False
        current["stadiumPlayed"] = False
        projected["bellmanActor"] = seat
        player = current["players"][seat]
        player["hand"] = [{"id": int(card_id)} for card_id in hand_ids]
        player["handCount"] = len(player["hand"])
        for _area, _index, body in body_rows(player):
            body["appearThisTurn"] = False
        return projected


__all__ = (
    "ActionFocus", "CoverageEdge", "DemandSlot", "DemandModel", "SequenceCoverage",
    "StrategyBeam",
    "StrategyBeamBuilder",
    "ResolvedAssignment",
    "RetainedAssignment", "RetainedOption", "access_probability", "best_assignment",
    "best_retained_assignment", "combined_coverage", "coverage_signature",
    "look_class_clauses", "outcome_identity", "semantic_action_key",
)
