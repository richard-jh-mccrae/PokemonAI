"""`hold-clutch-heal`: hold an energy-bouncing heal (Wally's Compassion, tag `clutch_heal`) until the
Active is doomed, then play it first (it outranks the attach) so the bounce doesn't waste a fresh
attachment — heal, re-power, attack. See docs/tuning/methodology.md and docs/card-functions.md."""
from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Board, Context, Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Plan, Strategy

_RULE = next(h for h in GENERAL_STRATEGY.hypotheses if h.id == "hold-clutch-heal")
_PLAY, _ATTACH = 7, 8


def _ctx(**kw):
    base = dict(plan=Plan.RACE, select_context=0, option_type=_PLAY, card_id=1229,
                tags=["heal", "clutch_heal"], board=Board(active_doomed=True))
    base.update(kw)
    return Context(**base)


def test_fires_only_for_a_clutch_heal_when_the_active_is_doomed():
    assert bool(_RULE.when(_ctx()))                                    # doomed + clutch_heal + play
    assert not _RULE.when(_ctx(board=Board(active_doomed=False)))      # not doomed -> hold it
    assert not _RULE.when(_ctx(tags=["heal"]))                        # plain heal (no energy bounce)
    assert not _RULE.when(_ctx(option_type=_ATTACH))                  # not a play


def test_clutch_heal_outranks_the_attach_when_the_active_is_doomed():
    """The whole point of the sequencing: with the Active about to be KO'd, Play Wally's must beat
    attaching to it — so the heal (which bounces all Energy to hand) happens BEFORE any fresh attach."""
    stats = DictCardStatProvider({
        1031: CardStat(cardId=1031, hp=330, megaEx=True),     # my Mega ex (max HP 330)
        999: CardStat(cardId=999, hp=200, maxDamage=300),     # opponent's Active: 300 dmg >> my 50 HP
        3: CardStat(cardId=3, hp=0, energyType=3),            # Basic Energy in hand
    })
    funcs = CardFunctions({1229: ["heal", "clutch_heal"]})
    pilot = Pilot(Strategy(), deck=[], general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = {"select": {"context": 0, "maxCount": 1, "option": [
        {"index": 0, "type": _PLAY},                                          # Play Wally's (hand[0])
        {"area": 2, "index": 1, "inPlayArea": 4, "inPlayIndex": 0, "type": _ATTACH}]},  # Attach Basic -> Active
        "current": {"yourIndex": 0, "turn": 5, "players": [
            {"active": [{"id": 1031, "hp": 50, "energies": [1, 2, 3]}], "bench": [{"id": 1030}],
             "hand": [{"id": 1229}, {"id": 3}]},
            {"active": [{"id": 999, "hp": 200}], "bench": []}]}}

    assert pilot._board(obs).active_doomed                            # the premise
    dec = pilot.explain(obs)
    wally, attach = dec.options[0], dec.options[1]
    assert "hold-clutch-heal" in {h.id for h, _ in wally.fired}
    assert wally.score > attach.score                                # heal sequenced before the attach
    assert dec.chosen == [0]                                          # ... and it's the chosen play
