"""`dont-waste-discard-energy` (general Strategy) + its supporting Pilot signals.

A discard-at-end-of-turn Energy (Ignition, tag `discard_eot`) is wasted unless the Pokémon it goes on
attacks this turn — see docs/tuning/methodology.md (worked example) and the Cinderace Turbo Flare line.
"""
from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Board, Context, Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy

_RULE = next(h for h in GENERAL_STRATEGY.hypotheses if h.id == "dont-waste-discard-energy")
_ATTACH, _ACTIVE, _BENCH = 8, 4, 5


def _ctx(**kw):
    base = dict(plan=None, select_context=None, option_type=_ATTACH, card_id=17,
                tags=["discard_eot"], attach_target_area=_ACTIVE, attach_target_roles=[],
                board=Board(turn=3, reusable_energy_in_hand=False))
    base.update(kw)
    return Context(**base)


def _fires(**kw):
    return bool(_RULE.when(_ctx(**kw)))


def test_fires_on_a_benched_target():
    """Benched Pokémon can't attack this turn -> a discard Energy on it is wasted."""
    assert _fires(attach_target_area=_BENCH)


def test_fires_on_the_first_turn_going_first():
    """Turn 1 (first player) can't attack at all -> wasted."""
    assert _fires(board=Board(turn=1, reusable_energy_in_hand=False))


def test_fires_when_a_reusable_basic_is_in_hand():
    """A reusable Basic is available -> attach that, save the discard Energy."""
    assert _fires(board=Board(turn=3, reusable_energy_in_hand=True))


def test_does_not_fire_on_the_turbo_flare_line():
    """Active target, turn>1, no reusable Basic -> attaching to attack THIS turn is correct."""
    assert not _fires()


def test_does_not_fire_onto_the_wincon_even_with_a_basic_in_hand():
    """On the win-condition the discard Energy's bulk acceleration (e.g. CCC) is the payoff."""
    assert not _fires(board=Board(turn=3, reusable_energy_in_hand=True),
                      attach_target_roles=["win_condition"])


def test_does_not_fire_for_a_non_discard_energy():
    """A plain Basic attach (no `discard_eot` tag) is never penalised, even to the Bench."""
    assert not _fires(tags=[], attach_target_area=_BENCH)


def _pilot():
    stats = DictCardStatProvider({
        3: CardStat(cardId=3, hp=0, energyType=3),       # Basic {W} Energy -> reusable
        17: CardStat(cardId=17, hp=0, energyType=0),     # Ignition (special, colourless) -> not
        1182: CardStat(cardId=1182, hp=0, energyType=0),  # a Trainer -> not (energyType 0, NOT None)
        666: CardStat(cardId=666, hp=160, energyType=2),  # a Pokémon -> not (hp>0)
    })
    return Pilot(Strategy(), deck=[], stats=stats, functions=CardFunctions({17: ["discard_eot"]}))


def test_reusable_energy_detection_excludes_trainers_and_discard_energy():
    """REQ-PILOT-0020: the engine reports energyType 0 for Trainers AND Ignition, so only a *typed*
    Basic (energyType not in {None,0}) that isn't `discard_eot` counts as a reusable Energy."""
    p = _pilot()
    assert p._has_reusable_energy([{"id": 3}])                              # a Basic
    assert not p._has_reusable_energy([{"id": 17}, {"id": 1182}, {"id": 666}])  # special / trainer / mon


def test_attach_target_resolves_the_inplay_fields():
    """REQ-PILOT-0021: an attach option's target is `inPlayArea`/`inPlayIndex` (the Pokémon), distinct
    from `area`/`index` (the Energy card in hand)."""
    p = Pilot(Strategy(), deck=[])
    obs = {"current": {"yourIndex": 0, "players": [{"active": [{"id": 666}], "bench": [{"id": 1030}]}]}}
    assert p._attach_target(obs, {"inPlayArea": _ACTIVE, "inPlayIndex": 0})["id"] == 666
    assert p._attach_target(obs, {"inPlayArea": _BENCH, "inPlayIndex": 0})["id"] == 1030
    assert p._attach_target(obs, {"type": _ATTACH}) is None
