"""The Pilot's ENERGY-CARD signals — the reads the attach decider's burst discipline stands on.

The five `discard_eot` rungs this file used to pin (`dont-waste-discard-energy` and its family) are
DELETED (#139, ADR-0069 §7). Their behaviour now lives in the decider's equation — honest printed
provision, the evaporation loss, the no-KO cap, the resource tie-break — and is pinned as BEHAVIOUR
in `test_attach_decider.py`, at the decision seam rather than on a rung's `when()`.

What stays here is what those rungs READ: the signals themselves. `_has_reusable_energy` and
`_reusable_hand_energy_id` are the same predicate at two arities (does one exist / which one), and
the no-KO cap is only sound while they cannot disagree.
"""
from card_facts import ignition_tags                    # the committed Ignition Energy tags, ONE copy
from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy

_ATTACH, _ACTIVE, _BENCH = 8, 4, 5


def _pilot():
    stats = DictCardStatProvider({
        3: CardStat(cardId=3, hp=0, energyType=3),        # Basic {W} Energy -> reusable
        17: CardStat(cardId=17, hp=0, energyType=0),      # Ignition (special, colourless) -> not
        1182: CardStat(synthetic=True, cardId=1182, hp=0, energyType=0),  # a Trainer -> not (energyType 0, NOT None)
        666: CardStat(cardId=666, hp=160, energyType=2),  # a Pokémon -> not (hp>0)
    })
    return Pilot(Strategy(), deck=[], stats=stats, functions=CardFunctions({17: ignition_tags()}))


def test_reusable_energy_detection_excludes_trainers_and_discard_energy():
    """REQ-PILOT-0020: the engine reports energyType 0 for Trainers AND Ignition, so only a *typed*
    Basic (energyType not in {None,0}) that isn't `discard_eot` counts as a reusable Energy."""
    p = _pilot()
    assert p._has_reusable_energy([{"id": 3}])                                  # a Basic
    assert not p._has_reusable_energy([{"id": 17}, {"id": 1182}, {"id": 666}])  # special/trainer/mon


def test_the_burst_caps_conservation_alternative_is_the_same_predicate():
    """The cap compares against a specific card while the board fact is a boolean; if they disagreed
    the cap would fire with no alternative to fall back on. exists <-> which one."""
    p = _pilot()
    obs = {"current": {"yourIndex": 0,
                       "players": [{"hand": [{"id": 17}, {"id": 1182}, {"id": 666}]}]}}
    assert p._reusable_hand_energy_id(obs) is None
    assert not p._has_reusable_energy(obs["current"]["players"][0]["hand"])
    obs["current"]["players"][0]["hand"].append({"id": 3})
    assert p._reusable_hand_energy_id(obs) == 3
    assert p._has_reusable_energy(obs["current"]["players"][0]["hand"])


def test_attach_target_resolves_the_inplay_fields():
    """REQ-PILOT-0021: an attach option's target is `inPlayArea`/`inPlayIndex` (the Pokémon), distinct
    from `area`/`index` (the Energy card in hand)."""
    p = Pilot(Strategy(), deck=[])
    obs = {"current": {"yourIndex": 0, "players": [{"active": [{"id": 666}], "bench": [{"id": 1030}]}]}}
    assert p._attach_target(obs, {"inPlayArea": _ACTIVE, "inPlayIndex": 0})["id"] == 666
    assert p._attach_target(obs, {"inPlayArea": _BENCH, "inPlayIndex": 0})["id"] == 1030
    assert p._attach_target(obs, {"type": _ATTACH}) is None
