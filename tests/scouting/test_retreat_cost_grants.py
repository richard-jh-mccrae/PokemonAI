"""Grant-aware Retreat Cost — the card-knowledge seam and its consumer (ADR-0100 §8, Issue #141).

Three shapes, one named test each, scoped to what our decks and the tracked meta run — NOT a general
effects DSL. Every parse fails CLOSED: an unreadable or unmodelled grant returns nothing and the
caller charges the PRINTED cost. Card text is verified at source in `data/EN_Card_Data.csv`.

The board-level grant is tested against a SYNTHETIC board, deliberately: the only deck running
Latias ex is `slowking`, which has no `strategy.py` (Issue #149) and so owns no corpus frames.

⚠️ LATENT DIVERGENCE, owed to Issue #149: `_effective_retreat_cost` is grant-aware, `_can_retreat`
is not — with Latias ex benched the first prices a free pivot the second denies. Harmless only
because no deck with a strategy module runs a board-level grant. Issue #306 discharged the
attached-Tool half into `Pilot._attached_retreat_delta`; the board-level half is still unshared.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.card_text import (_parse_retreat_free_grant, _parse_tool_retreat_free_at_hp,
                                       _parse_tool_retreat_reduction)
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import MAIN, make_select, opt, poke, state

RETREAT, END = 12, 14
AIR_BALLOON, RESCUE_BOARD, LATIAS_EX, ARCHALUDON = 1174, 1157, 184, 170
WALKER, BENCHIE, WALL = 800, 801, 900
TOWER = 802                     # a Stage 2 with a PRINTED retreat cost and no grant of its own
METAL, A_WALK, A_WALL = 8, 71, 72


class _Skill:
    """The shape the provider walks — an object with `.text`."""

    def __init__(self, text):
        self.text = text


class _Card:
    def __init__(self, *texts):
        self.skills = [_Skill(t) for t in texts]


# ---- the READ (the one card-knowledge seam, ADR-0056) -------------------------------------------

def test_the_flat_tool_reduction_still_reads_air_balloon():
    """The amount is repeated Colorless symbols, so it is COUNTED, not read as a digit."""
    card = _Card("The Retreat Cost of the Pokémon this card is attached to is {C}{C} less.")
    assert _parse_tool_retreat_reduction(card) == 2


def test_rescue_board_reads_both_of_its_legs():
    """Two sentences, two facts: the flat `{C}` always applies, the zeroing only below the threshold."""
    card = _Card("The Retreat Cost of the Pokémon this card is attached to is {C} less. "
                 "If that Pokémon's remaining HP is 30 or less, it has no Retreat Cost.")
    assert _parse_tool_retreat_reduction(card) == 1
    assert _parse_tool_retreat_free_at_hp(card) == 30


def test_latias_ex_reads_as_a_board_level_basic_grant():
    """The predicate travels WITH the grant, so a new card is a parse plus a predicate, never a
    call-site special case."""
    assert _parse_retreat_free_grant(
        _Card("Your Basic Pokémon in play have no Retreat Cost.")) == "basic"


def test_archaludon_reads_as_a_board_level_typed_grant():
    assert _parse_retreat_free_grant(
        _Card("All of your Pokémon that have {M} Energy attached have no Retreat Cost.")) \
        == "metal_attached"


def test_an_unmodelled_grant_parses_to_nothing_so_the_printed_cost_stands():
    """N's Castle sweeps both players' "N's Pokémon in play", a BOARD question; `retreatFreeGrant`
    holds one predicate name evaluated against one body. Authoring it needs a consumer, not a regex."""
    assert _parse_retreat_free_grant(
        _Card("N's Pokémon in play (both yours and your opponent's) have no Retreat Cost.")) is None
    assert _parse_tool_retreat_free_at_hp(_Card("Attach a Pokémon Tool to 1 of your Pokémon.")) == 0


def test_the_real_cards_parse_through_the_engine_provider():
    """A pattern matching hand-typed prose but missing the engine's real skill text fails SILENTLY
    (fail-closed). The real records use a typographic apostrophe, hence the loose match."""
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()
    air, rescue = stats.get(AIR_BALLOON), stats.get(RESCUE_BOARD)
    latias, archaludon = stats.get(LATIAS_EX), stats.get(ARCHALUDON)
    assert (air.retreatReduction, air.retreatFreeAtHp, air.retreatFreeGrant) == (2, 0, None)
    assert (rescue.retreatReduction, rescue.retreatFreeAtHp) == (1, 30)
    assert latias.retreatFreeGrant == "basic"
    assert archaludon.retreatFreeGrant == "metal_attached"
    assert stats.get(1253).retreatFreeGrant is None                      # N's Castle: still unmodelled


# ---- the CONSUMER, on a live board --------------------------------------------------------------

def _pilot(*, grantor=None):
    stats = DictCardStatProvider({
        WALKER: CardStat(WALKER, synthetic=True, name="Walker", hp=120, stage="basic", retreatCost=2,
                         minAttackCost=1, maxDamage=60, maxDamageCost=1, attacks=(A_WALK,)),
        BENCHIE: CardStat(BENCHIE, synthetic=True, name="Benchie", hp=90, stage="basic", retreatCost=1,
                          minAttackCost=1, maxDamage=30, maxDamageCost=1, attacks=(A_WALK,)),
        WALL: CardStat(WALL, synthetic=True, name="Wall", hp=300, minAttackCost=2, maxDamage=60,
                       maxDamageCost=2, attacks=(A_WALL,)),
        TOWER: CardStat(TOWER, synthetic=True, name="Tower", hp=300, stage="stage2", retreatCost=3,
                        minAttackCost=2, maxDamage=60, maxDamageCost=2, attacks=(A_WALL,)),
        RESCUE_BOARD: CardStat(RESCUE_BOARD, synthetic=True, name='Rescue Board', cardType=2,
                               retreatReduction=1, retreatFreeAtHp=30),
        LATIAS_EX: CardStat(LATIAS_EX, synthetic=True, name='Latias ex', hp=210, ex=True, stage="basic",
                            retreatFreeGrant="basic"),
        # No `stage`: card 170 is a Stage 1 at 180 HP, and TOWER already carries the Stage 2 role.
        ARCHALUDON: CardStat(ARCHALUDON, synthetic=True, name='Archaludon', hp=300,
                             retreatFreeGrant="metal_attached"),
    }, attacks={A_WALK: AttackStat(A_WALK, damage=60, cost=1),
                A_WALL: AttackStat(A_WALL, damage=60, cost=2)})
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({}))


def _obs(active, bench):
    return make_select([opt(RETREAT), opt(END)], context=MAIN,
                       current=state(active=active, bench=bench, opp_active=poke(WALL, hp=300),
                                     turn=5))


def test_a_conditional_tool_frees_the_retreat_once_the_holder_is_damaged():
    """Rescue Board shaves ONE at full HP; the same body at 30 HP or less retreats FREE."""
    p = _pilot()
    healthy = poke(WALKER, energy=2, hp=120)
    healthy["tools"] = [{"id": RESCUE_BOARD}]
    damaged = dict(healthy, hp=30)
    assert p._effective_retreat_cost(_obs(healthy, [poke(BENCHIE, hp=90)]), healthy) == 1
    assert p._effective_retreat_cost(_obs(damaged, [poke(BENCHIE, hp=90)]), damaged) == 0


def test_a_board_level_ability_frees_my_basics_from_another_slot():
    """The shape no per-card read could see: the grant lives on a BENCHED body and applies to the
    ACTIVE one."""
    p = _pilot()
    active = poke(WALKER, energy=2, hp=120)                 # printed Retreat Cost 2, a Basic
    without = _obs(active, [poke(BENCHIE, hp=90)])
    with_latias = _obs(active, [poke(LATIAS_EX, hp=210)])
    assert p._effective_retreat_cost(without, active) == 2
    assert p._effective_retreat_cost(with_latias, active) == 0


def test_the_board_level_grant_respects_its_own_predicate():
    """"Your BASIC Pokémon in play" — a Stage 2 gets nothing. `TOWER` carries a printed 3 on purpose:
    against a printed-0 body the assertion would pass whether the predicate refused or not."""
    p = _pilot()
    grantor = [poke(LATIAS_EX, hp=210)]
    stage2 = poke(TOWER, energy=3, hp=300)
    assert p._effective_retreat_cost(_obs(stage2, grantor), stage2) == 3   # refused: not a Basic
    basic = poke(WALKER, energy=2, hp=120)
    assert p._effective_retreat_cost(_obs(basic, grantor), basic) == 0     # granted: a Basic
    assert p._effective_retreat_cost(_obs(basic, [poke(BENCHIE, hp=90)]), basic) == 2  # no grantor


def test_the_grant_predicate_reads_a_value_the_provider_actually_emits():
    """Every board test above hands `_effective_retreat_cost` a `stage` it wrote itself, and until
    Issue #408 the provider wrote none — a fixture is evidence only if production emits that value."""
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()
    slowpoke, slowking = stats.get(162), stats.get(163)     # slowking's line: it runs Latias ex
    assert stats.get(LATIAS_EX).retreatFreeGrant == "basic"
    assert (slowpoke.stage, slowking.stage) == ("basic", "stage1")
    # the join, spelled as the predicate spells it — and its negative half
    assert (slowpoke.stage or "").lower() == "basic"
    assert (slowking.stage or "").lower() != "basic"
    assert slowpoke.retreatCost > 0 and slowking.retreatCost > 0   # printed 0 would be untestable


@pytest.mark.req("REQ-GEN-0026")
def test_a_free_retreat_destroys_no_build_and_so_costs_nothing():
    """`retreat_cost` is the BUILD the discard destroys, so a body that discards nothing pays 0."""
    p = _pilot()
    active = poke(WALKER, energy=2, hp=120)
    obs = _obs(active, [poke(LATIAS_EX, hp=210)])
    row = p.explain(obs).options[0].promote_retreat_working
    assert row is not None and row["retreat_cost"] == 0.0
