"""Free-peek dominance: costless deck peeks are searched before neutral commitments."""
from __future__ import annotations

from common import ActionIdentity, Actor, DecisionState, Deterministic, PilotProfile, \
    ProductionSolver, Terminal
from common.commutativity import ActionFootprint
from common.options import LegalAction
from common.value import CardFacts, Potential, ValueOracle, ValueRegistry


CARD = 900
DECK = (CARD,)


def _obs(node, *, board=0.0, context=0):
    return {"node": node, "current": {
        "yourIndex": 0, "turn": 1, "board": board,
        "supporterPlayed": False, "energyAttached": False, "retreated": False,
        "players": [
            {"hand": [], "active": [], "bench": [], "discard": [], "prize": []},
            {"hand": None, "active": [], "bench": [], "discard": [], "prize": []},
        ]}, "select": {"context": context, "option": []}}


REGISTRY = ValueRegistry(functions={CARD: ("search",)}, facts={CARD: CardFacts()})


def _state(node, **kwargs):
    return DecisionState.from_observation(_obs(node, **kwargs), deck=DECK, deck_name="test",
                                          value_registry_identity=REGISTRY.identity)


def _action(kind, index):
    return LegalAction(ActionIdentity(kind, (kind,)), (index,), ((index,),), ())


def _oracle():
    return ValueOracle(REGISTRY, lambda obs: Potential(
        float(obs["current"].get("board", 0.0)),
        (("board", float(obs["current"].get("board", 0.0))),)))


PEEK = _action("play", 0)               # the costless pure deck peek
ATTACH = _action("attach", 1)           # hand/deck-neutral commitment: dominated by peek-first
SHUFFLE = _action("card", 2)            # opaque barrier play (e.g. shuffle-hand): never pruned
ATTACK = _action("attack", 3)           # safety fallback: never pruned
END = _action("end", 4)

FOOTPRINTS = {
    "play": ActionFootprint(("play", "peek"), barrier=True, information_first=True),
    "attach": ActionFootprint(
        ("attach", "energy", "body"),
        frozenset({"hand:energy"}), frozenset({"hand:energy", "body:energy"}), commitment=True),
    "card": ActionFootprint(("card", "shuffle"), barrier=True, commitment=True),
    "attack": ActionFootprint(("attack",), barrier=True, commitment=True),
    "end": ActionFootprint(("end",), barrier=True),
}


class Board:
    def __init__(self, actions):
        self._actions = actions
        good, bad = _state("good", board=5.0), _state("bad", board=1.0)
        self._transitions = {
            "play": Terminal(good, "win"),
            "attach": Terminal(good, "win"),
            "card": Terminal(bad, "win"),
            "attack": Terminal(bad, "win"),
            "end": Terminal(bad, "win"),
        }

    def actions(self, state):
        return self._actions if state.obs["node"] == "root" else ()

    def transition(self, state, action):
        return self._transitions[action.identity.kind]

    def resolve_end(self, state, action):
        return None

    def actor(self, state):
        return Actor.OURS

    def footprint(self, state, action):
        return FOOTPRINTS[action.identity.kind]


def _profile(enabled: float) -> PilotProfile:
    return PilotProfile.resolve(
        global_values={"search.information_dominance_enabled": enabled},
        authored_deck_overrides={}, provenance="test")


def _evaluated_kinds(decision) -> set:
    root = decision.diagnostics["root"]
    kinds = {key.split("'")[1] for key in
             (row.action_key for row in root.alternatives)} if root.alternatives else set()
    kinds.add(decision.action.kind)
    return kinds


def test_neutral_commitment_is_pruned_while_peek_shuffle_and_safety_stay():
    solver = ProductionSolver(Board((PEEK, ATTACH, SHUFFLE, ATTACK, END)), _oracle(),
                              profile=_profile(1.0))
    decision = solver.decide(_state("root"))

    evaluated = _evaluated_kinds(decision)
    assert "attach" not in evaluated
    assert {"play", "card", "attack", "end"} <= evaluated
    production = decision.diagnostics["production"]
    assert production["information_first_permutations_pruned"] == 1
    assert {"proof_type": "information_dominance",
            "pruned": str(ATTACH.identity),
            "retained_event": ("free_peek_first",)} in production["structural_prunes"]


def test_without_a_legal_peek_nothing_is_pruned():
    solver = ProductionSolver(Board((ATTACH, SHUFFLE, ATTACK, END)), _oracle(),
                              profile=_profile(1.0))
    decision = solver.decide(_state("root"))

    assert "attach" in _evaluated_kinds(decision)
    assert decision.diagnostics["production"]["information_first_permutations_pruned"] == 0


def test_kill_switch_restores_the_full_walk():
    solver = ProductionSolver(Board((PEEK, ATTACH, SHUFFLE, ATTACK, END)), _oracle(),
                              profile=_profile(0.0))
    decision = solver.decide(_state("root"))

    assert "attach" in _evaluated_kinds(decision)
    assert decision.diagnostics["production"]["information_first_permutations_pruned"] == 0


# --- Value-aware exemptions (ADR-0140 expansion): the gate defers to what the model knows ----

from types import SimpleNamespace  # noqa: E402

PEEK_CARD, PAYMENT_CARD, SUPPORTER_CARD = 901, 902, 903


from common.cards.card_facts import (  # noqa: E402
    Clause, ITEM, SUPPORTER as SUPPORTER_KIND, TrainerCard)

_CARDS = {
    PEEK_CARD: TrainerCard(PEEK_CARD, "Test Peek", ITEM,
                           clauses=(Clause("fetch", target="supporter", dig=7),)),
    PAYMENT_CARD: TrainerCard(PAYMENT_CARD, "Test Payment", ITEM,
                              clauses=(Clause("fetch", target="pokemon",
                                              cost={"discard": 2}),)),
    SUPPORTER_CARD: TrainerCard(SUPPORTER_CARD, "Test Supporter", SUPPORTER_KIND),
}


def _hand_obs(node, hand_ids, option_count, *, board=0.0):
    return {"node": node, "current": {
        "yourIndex": 0, "turn": 1, "board": board,
        "supporterPlayed": False, "energyAttached": False, "retreated": False,
        "players": [
            {"hand": [{"id": cid, "playerIndex": 0} for cid in hand_ids],
             "active": [], "bench": [], "discard": [], "prize": []},
            {"hand": None, "active": [], "bench": [], "discard": [], "prize": []},
        ]}, "select": {"context": 0,
                       "option": [{"index": i} for i in range(option_count)]}}


def _hand_state(node, hand_ids, deck, option_count, **kwargs):
    return DecisionState.from_observation(
        _hand_obs(node, hand_ids, option_count, **kwargs), deck=deck, deck_name="test",
        value_registry_identity=REGISTRY.identity)


def _rich_oracle():
    return ValueOracle(REGISTRY, lambda obs: Potential(
        float(obs["current"].get("board", 0.0)),
        (("board", float(obs["current"].get("board", 0.0))),)),
        cards=_CARDS)


PEEK_PLAY = LegalAction(ActionIdentity("play", ("peek",)), (0,), ((0,),), ())
PAYMENT_PLAY = LegalAction(ActionIdentity("play", ("payment",)), (1,), ((1,),), ())
ATTACH_2 = LegalAction(ActionIdentity("attach", ("attach",)), (2,), ((2,),), ())
ATTACK_3 = LegalAction(ActionIdentity("attack", ("attack",)), (3,), ((3,),), ())
END_4 = LegalAction(ActionIdentity("end", ("end",)), (4,), ((4,),), ())

RICH_FOOTPRINTS = {
    ("play", ("peek",)): ActionFootprint(("play", "peek"), barrier=True, information_first=True),
    ("play", ("payment",)): ActionFootprint(("play", "payment"), barrier=True, commitment=True),
    ("attach", ("attach",)): ActionFootprint(
        ("attach", "energy", "body"),
        frozenset({"hand:energy"}), frozenset({"hand:energy", "body:energy"}), commitment=True),
    ("attack", ("attack",)): ActionFootprint(("attack",), barrier=True, commitment=True),
    ("end", ("end",)): ActionFootprint(("end",), barrier=True),
}


class RichBoard:
    def __init__(self, actions):
        self._actions = actions
        good, bad = _state("good", board=5.0), _state("bad", board=1.0)
        self._transitions = {
            ("play", ("peek",)): Terminal(good, "win"),
            ("play", ("payment",)): Terminal(good, "win"),
            ("attach", ("attach",)): Terminal(good, "win"),
            ("attack", ("attack",)): Terminal(bad, "win"),
            ("end", ("end",)): Terminal(bad, "win"),
        }

    def actions(self, state):
        return self._actions if state.obs["node"] == "root" else ()

    def transition(self, state, action):
        return self._transitions[(action.identity.kind, action.identity.parts)]

    def resolve_end(self, state, action):
        return None

    def actor(self, state):
        return Actor.OURS

    def footprint(self, state, action):
        return RICH_FOOTPRINTS[(action.identity.kind, action.identity.parts)]


def test_a_dead_peek_orders_nothing():
    # Deck holds no supporter, so the peek's window cannot reveal a target: zero information.
    root = _hand_state("root", (PEEK_CARD,), (PEEK_CARD, CARD), 5)
    solver = ProductionSolver(RichBoard((PEEK_PLAY, ATTACH_2, ATTACK_3, END_4)),
                              _rich_oracle(), profile=_profile(1.0))
    decision = solver.decide(root)

    assert "attach" in _evaluated_kinds(decision)
    assert decision.diagnostics["production"]["information_first_permutations_pruned"] == 0


def test_a_live_peek_still_orders_the_attach():
    root = _hand_state("root", (PEEK_CARD,), (PEEK_CARD, SUPPORTER_CARD), 5)
    solver = ProductionSolver(RichBoard((PEEK_PLAY, ATTACH_2, ATTACK_3, END_4)),
                              _rich_oracle(), profile=_profile(1.0))
    decision = solver.decide(root)

    assert "attach" not in _evaluated_kinds(decision)
    assert decision.diagnostics["production"]["information_first_permutations_pruned"] == 1


def test_a_discard_cost_play_disarms_the_gate():
    # An Ultra Ball-class play is legal, so the peek may be worth more as its payment; only the
    # value calculation can weigh that, and the gate stands down.
    root = _hand_state("root", (PEEK_CARD, PAYMENT_CARD), (PEEK_CARD, PAYMENT_CARD, SUPPORTER_CARD), 5)
    solver = ProductionSolver(RichBoard((PEEK_PLAY, PAYMENT_PLAY, ATTACH_2, ATTACK_3, END_4)),
                              _rich_oracle(), profile=_profile(1.0))
    decision = solver.decide(root)

    assert "attach" in _evaluated_kinds(decision)
    assert decision.diagnostics["production"]["information_first_permutations_pruned"] == 0
