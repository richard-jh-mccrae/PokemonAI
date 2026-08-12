"""Neutral cgpy transition provider for Bellman search."""
from __future__ import annotations

from collections import Counter
import copy

from .algebra import (
    Actor, Chance, Deterministic, Edge, RevealChoice, RevealOutcome, Terminal, Unknown, WeightedEdge,
)
from .options import LegalAction, enumerate_legal_actions
from .state import DecisionState
from .information import draw_outcomes, reveal_sets
from .fetch import WINDOW, fetch_target_matches
from common.strategy.context import (
    _ACTIVE, _ATTACH_FROM, _BENCH, _CARD, _DAMAGE, _DECK, _DISCARD, _DISCARD_ENERGY, _HAND,
    _LOOKING, _MAIN, _MOVE_CARD, _SWITCH, _TO_ACTIVE, _TO_HAND, _YES, _NO,
)


DEFAULT_RNG_SEED = 0
MANUAL_COIN_CONTEXT = 46
BENCH_DAMAGE_CONTEXT = _DAMAGE
AREA_PRIZE = 6
COIN_BRANCH_PROBABILITY = 0.5
ENERGY_REMOVAL_INDEX_SLOT = 2
DEFAULT_REVEAL_AMOUNT = 1
SHUFFLE_OWN_HAND_RIDER = "shuffle_own_hand_in"


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


class _ForcedShuffleRng:
    """Delegate RNG except for one own-deck shuffle whose top identities define a chance branch."""

    def __init__(self, delegate, game_state, seat: int, top_ids):
        self.delegate = delegate
        self.game_state = game_state
        self.seat = int(seat)
        self.top_ids = tuple(int(card_id) for card_id in top_ids)
        self.used = False

    def shuffle(self, sequence, *, seat: int) -> None:
        self.delegate.shuffle(sequence, seat=seat)
        if self.used or int(seat) != self.seat:
            return
        remaining, chosen = list(sequence), []
        for card_id in self.top_ids:
            serial = next((serial for serial in remaining
                           if self.game_state.card_id(serial) == card_id), None)
            if serial is None:
                raise ValueError(f"sampled shuffle card {card_id} is unavailable")
            remaining.remove(serial)
            chosen.append(serial)
        sequence[:] = remaining + list(reversed(chosen))
        self.used = True

    def __getattr__(self, name):
        return getattr(self.delegate, name)


class CgpyTransitionProvider:
    """Forkable full-rules engine adapter.  It enumerates and applies; it never ranks."""

    def __init__(self, root: DecisionState, *, registry=None, effects=None, stats=None, engine=None):
        self.root = root
        self.registry = registry
        self.effects = effects
        self.stats = stats
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

    def actor(self, state: DecisionState) -> Actor:
        if self._local_nested:
            return Actor.OURS
        engine = self._engines.get(state.semantic_key)
        if engine is None:
            return Actor.OURS
        return Actor.OURS if engine.select_seat == state.root_seat else Actor.OPPONENT

    def transition(self, state: DecisionState, action: LegalAction):
        if self._local_nested:
            return self._local_nested_transition(state, action)
        engine = self._engines.get(state.semantic_key)
        if engine is None:
            return Unknown("engine state unavailable", self._error or state.semantic_key)
        try:
            reveal = self._revealing_transition(state, engine, action)
            if reveal is not None:
                return reveal
            draw = self._drawing_transition(state, engine, action)
            if draw is not None:
                return draw
            child = engine.fork()
            child.step(list(action.selection))
            if child.gs.pending is not None and int(child.gs.pending.context) == MANUAL_COIN_CONTEXT:
                return self._coin_transition(state, child, action)
            return self._register_successor(state, child, action)
        except Exception as exc:  # noqa: BLE001 - an engine gap is explicit
            return Unknown("cgpy transition failed", f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _played_card_id(engine, action):
        if action.identity.kind != "play" or len(action.selection) != 1:
            return None
        option = engine.gs.pending.options[action.selection[0]]
        hand_index = option.get("index")
        hand = engine.gs.players[engine.select_seat].hand
        if not isinstance(hand_index, int) or not 0 <= hand_index < len(hand):
            return None
        return int(engine.gs.card_id(hand[hand_index]))

    @staticmethod
    def _force_top_ids(engine, seat, top_ids):
        deck = engine.gs.players[seat].deck
        remaining, chosen = list(deck), []
        for card_id in top_ids:
            serial = next((serial for serial in remaining
                           if engine.gs.card_id(serial) == card_id), None)
            if serial is None:
                raise ValueError(f"branch requested unavailable card {card_id}")
            remaining.remove(serial)
            chosen.append(serial)
        deck[:] = remaining + list(reversed(chosen))

    def _revealing_transition(self, state, engine, action):
        """Enumerate reveal windows; the resulting engine menu remains a Bellman Choice.

        Probability describes what the window exposes. Which exposed card to take is not encoded
        here: the authoritative engine poses that choice and the solver values each continuation.
        """
        card_id = self._played_card_id(engine, action)
        clauses = self.effects.clauses(card_id) if self.effects is not None and card_id else ()
        dig_clauses = tuple(clause for clause in clauses
                            if clause.get("kind") == "fetch" and clause.get("dig"))
        if not dig_clauses:
            return None
        depths = {int(clause["dig"]) for clause in dig_clauses}
        if len(depths) != 1:
            return Unknown("reveal effect has inconsistent depths", repr(sorted(depths)))
        amounts = {int(clause.get("amount", DEFAULT_REVEAL_AMOUNT)) for clause in dig_clauses}
        if len(amounts) != 1:
            return Unknown("reveal effect has inconsistent amounts", repr(sorted(amounts)))
        pool = [engine.gs.card_id(serial) for serial in engine.gs.players[state.root_seat].deck]
        draw_count = min(depths.pop(), len(pool))
        take_count = amounts.pop()
        if take_count != DEFAULT_REVEAL_AMOUNT:
            return Unknown("multi-card reveal choice is not represented", str(take_count))
        if draw_count <= 0:
            child = engine.fork()
            child.step(list(action.selection))
            return self._register_successor(state, child, action)
        matching = sorted({candidate for candidate in pool if any(
            fetch_target_matches(clause, self.stats.get(candidate) if self.stats else None,
                                 reading=WINDOW)
            for clause in dig_clauses)})
        distributions = reveal_sets(pool, draw_count, matching)
        matching_set = set(matching)
        fillers = [card for card in pool if card not in matching_set]

        def reveal_branch(*, selected=None, visible_card=None):
            visible = [] if visible_card is None else [visible_card]
            available = list(pool)
            for card in visible:
                available.remove(card)
            preferred = [card for card in available if card not in matching_set]
            preferred.extend(card for card in available if card in matching_set)
            top_ids = [*visible, *preferred[:draw_count - len(visible)]]
            branch = engine.fork()
            self._force_top_ids(branch, state.root_seat, top_ids)
            branch.step(list(action.selection))
            pending = branch.gs.pending
            if pending is None:
                if selected is not None:
                    raise ValueError("reveal did not pose its declared choice")
                return self._register_successor(state, branch, action)
            if selected is None:
                branch.step([])
                return self._register_successor(state, branch, action)
            option_index = next((index for index, option in enumerate(pending.options)
                                 if int(option.get("area", -1)) == _LOOKING
                                 and branch.gs.looking is not None
                                 and branch.gs.card_id(
                                     branch.gs.looking[int(option["index"])]) == selected), None)
            if option_index is None:
                raise ValueError(f"revealed card {selected} is not selectable")
            branch.step([option_index])
            return self._register_successor(state, branch, action)

        decline_source = matching[0] if matching else (fillers[0] if fillers else None)
        choices = [Edge("decline", reveal_branch(visible_card=decline_source))]
        choices.extend(Edge(f"card:{card}", reveal_branch(selected=card, visible_card=card))
                       for card in matching)
        outcomes = [RevealOutcome(outcome.probability,
                                  ("decline", *(f"card:{card}" for card in outcome.card_ids)))
                    for outcome in distributions]
        return RevealChoice(Actor.OURS, tuple(choices), tuple(outcomes))

    def _drawing_transition(self, state, engine, action):
        """Branch hidden draws from effect clauses; continuation, never static Worth, values them."""
        card_id = self._played_card_id(engine, action)
        clauses = self.effects.clauses(card_id) if self.effects is not None and card_id else ()
        draw_clauses = tuple(clause for clause in clauses if clause.get("kind") == "draw")
        if len(draw_clauses) != 1:
            return None
        clause = draw_clauses[0]
        if clause.get("opponent_amount") or clause.get("rider") not in (None, SHUFFLE_OWN_HAND_RIDER):
            return None
        from .draws import draw_branches

        players = engine.gs.players
        mine, opponent = players[state.root_seat], players[1 - state.root_seat]
        amounts = draw_branches(
            clause, len(mine.prize), len(opponent.prize), my_hand_size=len(mine.hand))
        if amounts is None or len(amounts) != 1 or amounts[0][1] != 0:
            return None
        draws = amounts[0][0]
        pool = [engine.gs.card_id(serial) for serial in mine.deck]
        if clause.get("rider") == SHUFFLE_OWN_HAND_RIDER:
            played_serial = mine.hand[(engine.gs.pending.options[action.selection[0]])["index"]]
            pool.extend(engine.gs.card_id(serial) for serial in mine.hand if serial != played_serial)
        outcomes = draw_outcomes(pool, draws)
        edges = []
        for index, outcome in enumerate(outcomes):
            branch = engine.fork()
            if clause.get("rider") == SHUFFLE_OWN_HAND_RIDER:
                delegate = branch.gs.rng
                branch.gs.rng = _ForcedShuffleRng(
                    delegate, branch.gs, state.root_seat, outcome.card_ids)
                try:
                    branch.step(list(action.selection))
                finally:
                    branch.gs.rng = delegate
            else:
                self._force_top_ids(branch, state.root_seat, outcome.card_ids)
                branch.step(list(action.selection))
            method = "exact" if outcome.exact else "stratified"
            edges.append(WeightedEdge(outcome.probability, f"{method}:{index}",
                                      self._register_successor(state, branch, action)))
        return Chance(tuple(edges))

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
            select = obs.get("select") or {}
            options = select.get("option") or ()
            picked = [options[index] for index in action.selection]
            current = obs.get("current") or {}
            players = current.get("players") or []
            context = int(select.get("context", -1))
            if context == BENCH_DAMAGE_CONTEXT:
                effect = select.get("effect") or {}
                facts = self.registry.facts.get(int(effect.get("id", 0))) if self.registry else None
                amount = int(getattr(facts, "bench_damage", 0) or 0)
                if amount <= 0:
                    raise ValueError("damage amount is absent from card facts")
                for option in picked:
                    target_seat = int(option["playerIndex"])
                    target_index = int(option["index"])
                    body = self._body(players, target_seat,
                                      int(option["area"]), target_index)
                    if body is None:
                        raise ValueError("damage target is absent")
                    body["hp"] = max(0, int(body.get("hp", 0)) - amount)
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
            successor = state.with_observation(obs)
            return Terminal(successor, "isolated historical nested selection")
        except Exception as exc:  # noqa: BLE001 - stays explicit
            return Unknown("historical nested transition failed", f"{type(exc).__name__}: {exc}")

    def _state_from_engine(self, state, child):
        from cgpy.search import export_token

        observation = child.observation(
            viewer=state.root_seat, sbi_token=export_token(child.gs))
        observation["bellmanActor"] = int(child.select_seat)
        observation["own_prizes"] = _own_prize_export(child, state.root_seat)
        return state.with_observation(observation)

    def _register_successor(self, state, child, action):
        try:
            successor = self._state_from_engine(state, child)
            committed = self._attack_committed.get(state.semantic_key, False) or \
                action.identity.kind == "attack"
            if successor.semantic_key not in self._engines:
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


__all__ = ("CgpyTransitionProvider",)
