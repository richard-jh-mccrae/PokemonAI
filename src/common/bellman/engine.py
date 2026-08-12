"""Neutral cgpy transition provider for Bellman search."""
from __future__ import annotations

from collections import Counter
import copy
from dataclasses import replace
from math import comb

from .algebra import Actor, Chance, Deterministic, Terminal, Unknown, WeightedEdge
from .information import BellmanDeckProfile, CausalNeeds, DrawClass, Need, OutcomeRng, hypergeometric_classes
from .options import LegalAction, enumerate_legal_actions
from .state import DecisionState
from .value import WORTH_PER_PRIZE
from common.strategy.context import (
    _ACTIVE, _ATTACH_FROM, _BENCH, _CARD, _DAMAGE, _DECK, _DISCARD, _DISCARD_ENERGY, _HAND,
    _HEAL, _LOOKING, _MAIN, _MOVE_CARD, _SUPPORTER, _SWITCH, _TO_ACTIVE, _TO_HAND, _YES, _NO,
)


DEFAULT_RNG_SEED = 0
HEAL_PREVIEW_BUDGET = 80
SEARCH_PREVIEW_BUDGET = 96
SEARCH_SEQUENCE_TAGS = frozenset({"search", "bench_fill"})
MANUAL_COIN_CONTEXT = 46
BENCH_DAMAGE_CONTEXT = _DAMAGE
BENCH_DAMAGE_AMOUNT = 50
AREA_PRIZE = 6
FULL_PRIZE_COUNT = 6
REFRESH_DRAW_WITH_FULL_PRIZES = 8
REFRESH_DRAW_AFTER_PRIZE = 6
REVEAL_DEPTH = 7
COIN_HEADS_DRAW = 5
COIN_TAILS_DRAW = 3
COIN_BRANCH_PROBABILITY = 0.5
CHANCE_MASS_TOLERANCE = 1e-12
ENERGY_REMOVAL_INDEX_SLOT = 2


def _expand(counts) -> list[int]:
    return [int(card_id) for card_id, count in counts for _ in range(int(count))]


def _take(cards: tuple[int, ...], count: int) -> list[int]:
    if not cards:
        return []
    copies = list(cards)
    while len(copies) < count:
        copies.extend(cards)
    return copies[:count]


def _own_prize_export(engine, seat: int) -> dict[int, int]:
    board = engine.gs.players[seat]
    return dict(Counter(engine.gs.card_id(serial) for serial in board.prize))


class CgpyTransitionProvider:
    """Forkable full-rules engine adapter.  It enumerates and applies; it never ranks."""

    def __init__(self, root: DecisionState, *, registry=None, needs: CausalNeeds | None = None,
                 engine=None, production_chance: bool = False):
        self.root = root
        self.registry = registry
        self.profile = BellmanDeckProfile.from_registry(registry) if registry else BellmanDeckProfile()
        self.needs = needs or CausalNeeds(profile=self.profile)
        self.production_chance = bool(production_chance)
        self._engines: dict[str, object] = {}
        self._attack_committed: dict[str, bool] = {}
        self._local_nested = False
        self._root_turn = int((root.obs.get("current") or {}).get("turn", 0))
        self._error = ""
        try:
            if engine is not None:
                self._engines[root.semantic_key] = engine
                self._attack_committed[root.semantic_key] = False
                return
            from cgpy.rng import SeededRng
            from cgpy.search import state_from_obs

            obs = root.obs
            current = obs.get("current") or {}
            players = current.get("players") or ()
            me = players[root.root_seat] if len(players) > root.root_seat else {}
            opp = players[1 - root.root_seat] if len(players) > 1 else {}
            own_deck = _expand(root.deck_counts)
            own_prize = _expand(root.prize_counts)
            if len(own_prize) < len(me.get("prize") or ()):
                pool = _take(root.deck, len(me.get("prize") or ()) + int(me.get("deckCount", 0)))
                own_prize = pool[:len(me.get("prize") or ())]
                own_deck = pool[len(own_prize):]
            own_deck = _take(tuple(own_deck or root.deck), int(me.get("deckCount", 0)))
            filler = tuple(root.deck)
            engine = state_from_obs(
                obs, own_deck, own_prize,
                _take(filler, int(opp.get("deckCount", 0))),
                _take(filler, len(opp.get("prize") or ())),
                _take(filler, int(opp.get("handCount", 0))), [],
                manual_coin=True, rng=SeededRng(DEFAULT_RNG_SEED),
            )
            self._engines[root.semantic_key] = engine
            self._attack_committed[root.semantic_key] = False
        except Exception as exc:  # noqa: BLE001 - becomes first-class Unknown
            context = int(((root.obs.get("select") or {}).get("context", -1)))
            if context != _MAIN:
                self._local_nested = True
                self._error = ""
            else:
                self._error = f"{type(exc).__name__}: {exc}"

    @property
    def available(self) -> bool:
        return not self._error

    def actions(self, state: DecisionState) -> tuple[LegalAction, ...]:
        if not self._local_nested and state.semantic_key not in self._engines:
            return ()
        return enumerate_legal_actions(state.obs)

    def preview_checkpoint(self):
        """Opaque engine-key snapshot used to release speculative forks after one root preview."""
        return frozenset(self._engines), frozenset(self._attack_committed)

    def preview_restore(self, checkpoint) -> None:
        engine_keys, attack_keys = checkpoint
        for key in tuple(self._engines):
            if key not in engine_keys:
                del self._engines[key]
        for key in tuple(self._attack_committed):
            if key not in attack_keys:
                del self._attack_committed[key]

    def actor(self, state: DecisionState) -> Actor:
        if self._local_nested:
            return Actor.OURS
        engine = self._engines.get(state.semantic_key)
        if engine is None:
            return Actor.OURS
        return Actor.OURS if engine.select_seat == state.root_seat else Actor.OPPONENT

    def _tags(self, card_id) -> frozenset[str]:
        return frozenset((self.registry.functions.get(int(card_id), ())
                          if self.registry is not None and card_id is not None else ()))

    def preview_node_budget(self, state, action, default: int) -> int:
        """Expanded-state allowance based only on the effect's mechanical branching."""
        context = int(((state.obs.get("select") or {}).get("context", -1)))
        if context == _HEAL:
            return max(default, HEAL_PREVIEW_BUDGET)
        engine = self._engines.get(state.semantic_key)
        if engine is None or action.identity.kind != "play":
            return default
        card_id, _serial = self._played_card_id(engine, action)
        tags = self._tags(card_id)
        # Heal resolves a target, returned stack/Energy, a replacement attachment, then attack.
        if "heal" in tags:
            return max(default, HEAL_PREVIEW_BUDGET)
        # Search often owns mandatory discard and deck-target menus before returning to Main.
        return max(default, SEARCH_PREVIEW_BUDGET) if tags.intersection(
            SEARCH_SEQUENCE_TAGS) else default

    def transition(self, state: DecisionState, action: LegalAction):
        if self._local_nested:
            return self._local_nested_transition(state, action)
        engine = self._engines.get(state.semantic_key)
        if engine is None:
            return Unknown("engine state unavailable", self._error or state.semantic_key)
        try:
            information = self._information_transition(state, engine, action)
            if information is not None:
                return information
            child = engine.fork()
            child.step(list(action.selection))
            if child.gs.pending is not None and int(child.gs.pending.context) == MANUAL_COIN_CONTEXT:
                return self._coin_transition(state, child, action)
            return self._register_successor(state, child, action)
        except Exception as exc:  # noqa: BLE001 - an engine gap is explicit
            return Unknown("cgpy transition failed", f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _body(players, seat, area, index):
        if not 0 <= seat < len(players):
            return None
        zone = "active" if int(area) == _ACTIVE else "bench" if int(area) == _BENCH else None
        bodies = players[seat].get(zone) if zone else None
        return bodies[index] if bodies and 0 <= index < len(bodies) else None

    def _local_nested_transition(self, state, action):
        """Resolve a recorded mid-effect menu when its opaque historical frame is unavailable.

        Live searches retain the exact cgpy frame.  Old correction observations do not, so this
        adapter applies the one visible, fully specified nested consequence and stops.  It is an
        engine-fact bridge, not a target chooser.
        """
        try:
            obs = copy.deepcopy(state.obs)
            adjustments = []
            select = obs.get("select") or {}
            options = select.get("option") or ()
            picked = [options[index] for index in action.selection]
            current = obs.get("current") or {}
            players = current.get("players") or []
            context = int(select.get("context", -1))
            if context == BENCH_DAMAGE_CONTEXT:
                for option in picked:
                    target_seat = int(option["playerIndex"])
                    target_index = int(option["index"])
                    body = self._body(players, target_seat,
                                      int(option["area"]), target_index)
                    if body is None:
                        raise ValueError("damage target is absent")
                    body["hp"] = max(0, int(body.get("hp", 0)) - BENCH_DAMAGE_AMOUNT)
                    if body["hp"] == 0 and int(option["area"]) == _BENCH:
                        card_id = int(body.get("id", 0))
                        facts = self.registry.facts.get(card_id) if self.registry else None
                        prizes = max(1, int(getattr(facts, "prize_value", 1)))
                        players[target_seat]["bench"].pop(target_index)
                        mine = players[state.root_seat].get("prize") or []
                        del mine[:min(prizes, len(mine))]
            elif context == _ATTACH_FROM:  # generic visible Energy placement
                card = copy.deepcopy(select.get("contextCard"))
                if not card:
                    raise ValueError("attach-from menu has no context Energy")
                for option in picked:
                    body = self._body(players, int(option["playerIndex"]),
                                      int(option["area"]), int(option["index"]))
                    if body is None:
                        raise ValueError("Energy recipient is absent")
                    body.setdefault("energyCards", []).append(card)
                    facts = self.registry.facts.get(int(card.get("id", 0))) if self.registry else None
                    energy_type = card.get("energyType", getattr(facts, "energy_type", None))
                    if energy_type is not None:
                        body.setdefault("energies", []).append(int(energy_type))
            elif context == _DISCARD_ENERGY:  # mandatory attached-Energy payment / denial target
                removals = []
                for option in picked:
                    body = self._body(players, int(option["playerIndex"]),
                                      int(option["area"]), int(option["index"]))
                    if body is None:
                        raise ValueError("Energy holder is absent")
                    removals.append((body, int(option["playerIndex"]),
                                     int(option["energyIndex"])))
                # Multiple picks can name the same holder; remove high indices first so every
                # option keeps the engine menu's original Energy-card indexing.
                removals.sort(key=lambda row: row[ENERGY_REMOVAL_INDEX_SLOT], reverse=True)
                for body, seat, energy_index in removals:
                    cards = body.get("energyCards") or []
                    if not 0 <= energy_index < len(cards):
                        raise ValueError("attached Energy index is absent")
                    card = cards.pop(energy_index)
                    units = body.get("energies") or []
                    if energy_index < len(units):
                        units.pop(energy_index)
                    players[seat].setdefault("discard", []).append(card)
            elif context == _TO_ACTIVE:  # forced promotion
                for option in picked:
                    seat = int(option["playerIndex"])
                    index = int(option["index"])
                    promoted = players[seat]["bench"].pop(index)
                    old = next((body for body in (players[seat].get("active") or ()) if body), None)
                    players[seat]["active"] = [promoted]
                    if old and int(old.get("hp", 0)) > 0:
                        players[seat].setdefault("bench", []).append(old)
            elif context == _SWITCH:  # an ordinary switch/retreat target
                for option in picked:
                    seat = int(option["playerIndex"])
                    index = int(option["index"])
                    promoted = players[seat]["bench"].pop(index)
                    old = next((body for body in (players[seat].get("active") or ()) if body), None)
                    players[seat]["active"] = [promoted]
                    if old:
                        players[seat].setdefault("bench", []).append(old)
            elif context == _TO_HAND:  # visible deck/discard/looking card to hand
                deck_listing = select.get("deck") or ()
                prize_picks = []
                for option in picked:
                    seat = int(option["playerIndex"])
                    area, index = int(option["area"]), int(option["index"])
                    if area == _DECK:
                        card = copy.deepcopy(deck_listing[index])
                    elif area == _LOOKING:
                        card = copy.deepcopy((current.get("looking") or ())[index])
                    elif area == _DISCARD:
                        card = copy.deepcopy(players[seat]["discard"][index])
                    elif area == AREA_PRIZE:
                        # A post-KO prize menu exposes only interchangeable card backs.  Credit the
                        # observable prize progress now; the revealed card enters the real next
                        # observation and is valued after the mandatory replan.
                        prize_picks.append((seat, index))
                        continue
                    else:
                        raise ValueError(f"unsupported to-hand source area {area}")
                    players[seat].setdefault("hand", []).append(card)
                for seat, index in sorted(prize_picks, reverse=True):
                    prizes = players[seat].get("prize") or []
                    if not 0 <= index < len(prizes):
                        raise ValueError("prize index is absent")
                    prizes.pop(index)
            else:
                return Unknown("historical nested frame unavailable",
                               f"select context {context}")
            current["turnActionCount"] = int(current.get("turnActionCount", 0)) + 1
            obs["select"] = None
            obs["bellmanHistoricalMain"] = True
            obs["bellmanHistoricalContext"] = context
            successor = state.with_observation(obs).with_adjustments(adjustments)
            return Terminal(successor, "isolated historical nested selection")
        except Exception as exc:  # noqa: BLE001 - stays explicit
            return Unknown("historical nested transition failed", f"{type(exc).__name__}: {exc}")

    def _state_from_engine(self, state, child, *, adjustments=()):
        from cgpy.search import export_token

        observation = child.observation(
            viewer=state.root_seat, sbi_token=export_token(child.gs))
        observation["own_prizes"] = _own_prize_export(child, state.root_seat)
        return state.with_observation(observation).with_adjustments(adjustments)

    def _register_successor(self, state, child, action, *, adjustments=()):
        try:
            successor = self._state_from_engine(state, child, adjustments=adjustments)
            committed = self._attack_committed.get(state.semantic_key, False) or \
                action.identity.kind == "attack"
            self._engines[successor.semantic_key] = child
            self._attack_committed[successor.semantic_key] = committed
            if child.result != -1:
                result = "win" if child.result == state.root_seat else "loss"
                return Terminal(successor, result)
            pending = child.gs.pending
            passed_turn = (pending is not None and pending.seat != state.root_seat
                           and int(child.gs.turn) != self._root_turn
                           and int(pending.context) == _MAIN)
            if committed and passed_turn:
                return Terminal(successor, "attack resolved")
            return Deterministic(successor)
        except Exception as exc:  # noqa: BLE001 - an engine gap is explicit
            return Unknown("cgpy transition failed", f"{type(exc).__name__}: {exc}")

    def _coin_transition(self, state, child, action):
        source_id = None
        if child.gs.frames:
            source_id = child.gs.card_id(child.gs.frames[-1].source)
        if "hand_disruption" in self._tags(source_id):
            return self._harlequin_coin_transition(state, child, action)
        edges = []
        for index, option in enumerate(child.gs.pending.options):
            if int(option.get("type", -1)) not in (_YES, _NO):
                continue
            branch = child.fork()
            branch.step([index])
            node = self._register_successor(state, branch, action)
            label = "heads" if int(option.get("type")) == _YES else "tails"
            edges.append(WeightedEdge(COIN_BRANCH_PROBABILITY, label, node))
        if len(edges) != len((_YES, _NO)):
            return Unknown("manual coin menu malformed", repr(child.gs.pending.options))
        return Chance(tuple(edges))

    @staticmethod
    def _force_top_ids(engine, seat, draw_ids):
        deck = engine.gs.players[seat].deck
        remaining, chosen = list(deck), []
        for card_id in draw_ids:
            serial = next((serial for serial in remaining
                           if engine.gs.card_id(serial) == card_id), None)
            if serial is None:
                raise ValueError(f"requested unavailable top card {card_id}")
            remaining.remove(serial)
            chosen.append(serial)
        deck[:] = remaining + list(reversed(chosen))

    def _harlequin_coin_transition(self, state, child, action):
        pool_ids = [child.gs.card_id(serial)
                    for serial in child.gs.players[state.root_seat].deck]
        counts = Counter(pool_ids)
        needs = self.needs.derive(state.obs, deck_counts=counts)
        edges = []
        for index, option in enumerate(child.gs.pending.options):
            option_type = int(option.get("type", -1))
            if option_type not in (_YES, _NO):
                continue
            draws = COIN_HEADS_DRAW if option_type == _YES else COIN_TAILS_DRAW
            for outcome, expected_adjustment in self._outcome_classes(pool_ids, draws, needs):
                draw_ids, adjustment = self._representative_ids(pool_ids, needs, outcome,
                                                                self.registry)
                if expected_adjustment is not None:
                    adjustment = expected_adjustment
                branch = child.fork()
                self._force_top_ids(branch, state.root_seat, draw_ids)
                branch.step([index])
                node = self._register_successor(
                    state, branch, action, adjustments=(("chance.hand", adjustment),))
                label = ("heads" if option_type == _YES else "tails") + ":" + outcome.label
                edges.append(WeightedEdge(COIN_BRANCH_PROBABILITY * outcome.probability, label, node))
        if not edges:
            return Unknown("Harlequin coin menu malformed", repr(child.gs.pending.options))
        return Chance(tuple(edges))

    def _played_card_id(self, engine, action):
        if action.identity.kind != "play" or len(action.selection) != 1:
            return None, None
        option = engine.gs.pending.options[action.selection[0]]
        index = option.get("index")
        hand = engine.gs.players[self.root.root_seat].hand
        if not isinstance(index, int) or not 0 <= index < len(hand):
            return None, None
        serial = hand[index]
        return engine.gs.card_id(serial), serial

    @staticmethod
    def _representative_ids(pool, needs, outcome, registry):
        remaining = list(pool)
        selected = []
        claimed = set()
        expected_worth = 0.0
        for need, count in zip(needs, outcome.counts):
            eligible = [card_id for card_id in remaining
                        if card_id in need.card_ids and card_id not in claimed]
            claimed.update(need.card_ids)
            if count:
                chosen = eligible[:count]
                for card_id in chosen:
                    remaining.remove(card_id)
                selected.extend(chosen)
                mean = (sum(registry.worth(card_id) for card_id in eligible) / len(eligible)
                        if registry and eligible else 0.0)
                expected_worth += mean * count
        complement = [card_id for card_id in remaining if card_id not in claimed]
        mean = (sum(registry.worth(card_id) for card_id in complement) / len(complement)
                if registry and complement else 0.0)
        if registry:
            ordered = sorted(complement, key=lambda card_id: (abs(registry.worth(card_id) - mean),
                                                               card_id))
        else:
            ordered = sorted(complement)
        chosen_other = ordered[:outcome.remainder]
        selected.extend(chosen_other)
        expected_worth += mean * outcome.remainder
        actual = sum(registry.worth(card_id) for card_id in selected) if registry else 0.0
        return selected, (expected_worth - actual) / WORTH_PER_PRIZE

    def _outcome_classes(self, pool, draws, needs):
        exact = hypergeometric_classes(pool, draws, needs)
        if not self.production_chance or not needs:
            return tuple((outcome, None) for outcome in exact)
        grouped = {}
        for outcome in exact:
            key = tuple(bool(count) for count in outcome.counts)
            grouped.setdefault(key, []).append(outcome)
        rows = []
        pool = list(pool)
        claimed = {card_id for need in needs for card_id in need.card_ids}
        complement = [card_id for card_id in pool if card_id not in claimed]
        complement_mean = (sum(self.registry.worth(card_id) for card_id in complement) /
                           len(complement) if self.registry and complement else 0.0)
        for presence, members in sorted(grouped.items()):
            probability = sum(member.probability for member in members)
            conditional = [sum(member.probability * member.counts[index]
                               for member in members) / probability
                           for index in range(len(needs))]
            counts = tuple(int(flag) for flag in presence)
            representative = DrawClass(
                probability, counts, draws - sum(counts),
                ",".join(f"{need.key}={'present' if flag else 'absent'}"
                         for need, flag in zip(needs, presence)),
            )
            selected, _unused = self._representative_ids(
                pool, needs, representative, self.registry)
            expected_worth = 0.0
            if self.registry:
                for need, count in zip(needs, conditional):
                    eligible = [card_id for card_id in pool if card_id in need.card_ids]
                    mean = (sum(self.registry.worth(card_id) for card_id in eligible) /
                            len(eligible) if eligible else 0.0)
                    expected_worth += mean * count
                expected_worth += complement_mean * (draws - sum(conditional))
            actual = (sum(self.registry.worth(card_id) for card_id in selected)
                      if self.registry else 0.0)
            rows.append((representative, (expected_worth - actual) / WORTH_PER_PRIZE))
        return tuple(rows)

    def _information_transition(self, state, engine, action):
        card_id, source = self._played_card_id(engine, action)
        tags = self._tags(card_id)
        if "dig" in tags:
            return self._pokegear_transition(state, engine, action)
        if not ("shuffle_hand" in tags and "hand_disruption" not in tags):
            return None
        board = engine.gs.players[state.root_seat]
        pool_serials = list(board.deck) + [serial for serial in board.hand if serial != source]
        pool_ids = [engine.gs.card_id(serial) for serial in pool_serials]
        draws = (REFRESH_DRAW_WITH_FULL_PRIZES if len(board.prize) == FULL_PRIZE_COUNT
                 else REFRESH_DRAW_AFTER_PRIZE)
        counts = Counter(pool_ids)
        needs = self.needs.derive(state.obs, deck_counts=counts)
        edges = []
        serial_to_card = {serial: engine.gs.card_id(serial) for serial in engine.gs.cards}
        for outcome, expected_adjustment in self._outcome_classes(pool_ids, draws, needs):
            draw_ids, adjustment = self._representative_ids(pool_ids, needs, outcome, self.registry)
            if expected_adjustment is not None:
                adjustment = expected_adjustment
            branch = engine.fork()
            branch.gs.rng = OutcomeRng(seat=state.root_seat, serial_to_card=serial_to_card,
                                       draw_ids=draw_ids)
            branch.step(list(action.selection))
            node = self._register_successor(
                state, branch, action, adjustments=(("chance.hand", adjustment),))
            edges.append(WeightedEdge(outcome.probability, outcome.label, node))
        return Chance(tuple(edges))

    def _pokegear_transition(self, state, engine, action):
        board = engine.gs.players[state.root_seat]
        pool_ids = [engine.gs.card_id(serial) for serial in board.deck]
        supporter_ids = sorted({engine.gs.card_id(serial) for serial in board.deck
                                if int(engine.gs.stat(serial).cardType) == _SUPPORTER})
        if self.production_chance:
            return self._pokegear_precedence_transition(
                state, engine, action, pool_ids, supporter_ids)
        needs = tuple(Need(f"supporter:{card_id}", (card_id,),
                           self.registry.worth(card_id) if self.registry else 0.0,
                           "Pokégear reveal identity changes the reachable Supporter continuation")
                      for card_id in supporter_ids)
        edges = []
        for outcome, _adjustment in self._outcome_classes(
                pool_ids, min(REVEAL_DEPTH, len(pool_ids)), needs):
            top_ids, _adjustment = self._representative_ids(pool_ids, needs, outcome, self.registry)
            branch = engine.fork()
            self._force_top_ids(branch, state.root_seat, top_ids)
            branch.step(list(action.selection))
            node = self._register_successor(state, branch, action)
            edges.append(WeightedEdge(outcome.probability, outcome.label, node))
        return Chance(tuple(edges))

    def _pokegear_precedence_transition(self, state, engine, action, pool_ids, supporter_ids):
        """Exact partition by the highest portable-Worth Supporter revealed.

        Lower identities inside the same reveal cannot improve this bounded branch's first pick;
        the real reveal is replanned without this compression.
        """
        draws, total = min(REVEAL_DEPTH, len(pool_ids)), len(pool_ids)
        denominator = comb(total, draws) if total >= draws else 1
        ordered = sorted(supporter_ids,
                         key=lambda card_id: (self.registry.worth(card_id)
                                              if self.registry else 0.0, -card_id),
                         reverse=True)
        counts = Counter(pool_ids)
        preceding = 0
        edges = []
        non_supporters = [card_id for card_id in pool_ids if card_id not in supporter_ids]
        for card_id in ordered:
            copies = counts[card_id]
            without_prior = comb(total - preceding, draws) if total - preceding >= draws else 0
            without_current = (comb(total - preceding - copies, draws)
                               if total - preceding - copies >= draws else 0)
            probability = (without_prior - without_current) / denominator
            preceding += copies
            if probability <= 0.0:
                continue
            fillers = list(non_supporters)
            if len(fillers) < draws - 1:
                fillers.extend(other for other in pool_ids
                               if other != card_id and other not in fillers)
            top_ids = [card_id] + fillers[:draws - 1]
            branch = engine.fork()
            self._force_top_ids(branch, state.root_seat, top_ids)
            branch.step(list(action.selection))
            node = self._register_successor(state, branch, action)
            edges.append(WeightedEdge(probability, f"best-supporter:{card_id}", node))
        none_probability = ((comb(len(non_supporters), draws) / denominator)
                            if len(non_supporters) >= draws else 0.0)
        if none_probability > 0.0:
            branch = engine.fork()
            self._force_top_ids(branch, state.root_seat, non_supporters[:draws])
            branch.step(list(action.selection))
            node = self._register_successor(state, branch, action)
            edges.append(WeightedEdge(none_probability, "no-supporter", node))
        mass = sum(edge.probability for edge in edges)
        if not edges or abs(mass - 1.0) > CHANCE_MASS_TOLERANCE:
            return Unknown("Pokégear precedence mass malformed", str(mass))
        return Chance(tuple(edges))


__all__ = ("CgpyTransitionProvider",)
