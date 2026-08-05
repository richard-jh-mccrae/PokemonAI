"""Grant-aware Retreat Cost — the card-knowledge seam and its consumer (ADR-0100 §8, #141).

`retreatReduction` shipped Tool-only and FLAT, which was survivable while a retreat cost 8 points of
card Worth. Under the convex build delta it is not: over-charging one Energy on a 3-slot attacker is
`(3/3)^2 - (2/3)^2 = 5/9 x maxDamage` ~ **117 damage of phantom cost**, and it would be systematic on
an archetype built around free-retreat pivoting.

Three shapes, one named test each, scoped to what our decks and the tracked meta run — NOT a general
effects DSL, per the ruling. Every parse fails CLOSED: an unreadable or unmodelled grant returns
nothing and the caller charges the PRINTED cost, erring toward not retreating rather than toward the
retreat-happy pathology the grill opened on.

Card text verified at source in `data/EN_Card_Data.csv`:
  * Air Balloon (1174): "The Retreat Cost of the Pokémon this card is attached to is {C}{C} less."
  * Rescue Board (1157): "…is {C} less. If that Pokémon's remaining HP is 30 or less, it has no
    Retreat Cost."  — the CONDITIONAL second sentence is the leg the flat read could not carry.
  * Latias ex (184), Skyliner: "Your Basic Pokémon in play have no Retreat Cost."  — BOARD-LEVEL, so
    the granting body is not the body retreating and no per-card read could ever see it. The engine
    cannot supply it either: `retreatCost` exists only on `CardData` as the static printed value.

**One deliberate exception to "test at the highest seam possible."** The board-level grant is tested
against a board here, not a real one, because the only deck running Latias ex is
`slowking` — which has `deck.csv`/`deck.txt` and **no `strategy.py`** (#149 §Charter), so it cannot
be built as a Pilot and owns no corpus frames. The debt is named here rather than implied.

⚠️ **That exception had a cost, and Issue #408 collected it.** Every board test below declares its
own `stage`, and `CardStat.stage` was declared-but-never-written until #408 — so the `grant ==
"basic"` predicate compared against None for every card in the pool while this file stayed green.
The synthetic seam did not merely under-test the grant; it actively concealed that the grant could
not fire at all. `test_the_grant_predicate_reads_a_value_the_provider_actually_emits` is the guard
added for it: a fixture is evidence only if production can emit the value it declares. Note the gate
was dead for TWO independent reasons — the unwritten field and the missing `strategy.py` — and #408
removed only the first, so item 1 below still stands.

**OWED TO #149 — two things, the second sharper than the first:**

1. A real-deck end-to-end test: a `slowking` Pilot on a real frame where the retreat DECISION changes
   because Latias ex is in play, through `decide()` with engine-backed card data — not a synthetic
   statline calling `_effective_retreat_cost` directly.
2. **A KNOWN DIVERGENCE to reconcile.** `_effective_retreat_cost` is now grant-aware; the other
   retreat-cost readers in the codebase are NOT. Measured on a board with Latias ex benched
   and a Basic Active at printed retreat 2 with ZERO Energy attached:

       _effective_retreat_cost(obs, active)  ->  0      (the grant is seen: free retreat)
       _can_retreat(active)                  ->  False  (printed cost 2 > 0 Energy attached)

   So the promote/retreat decider would price a free pivot that the affordability gate denies. The
   "one function owns the fact" lesson ADR-0070 drew for `_build_standing`, not yet applied to
   retreat cost.

   **Partly discharged by Issue #306.** The *attached-Tool* half is now one function:
   `Pilot._attached_retreat_delta` is the single, SIGNED reader that `_effective_retreat_cost`,
   `_can_retreat`, `planner._promotion_ease` and `planner._retreat_shortfall` all call — extracted
   because Gravity Gemstone parses to −1 and the arithmetic stopped being a subtraction of
   non-negatives. `_retreat_shortfall` had omitted it entirely, which merely over-stated the need
   while every Tool was a discount but would UNDER-state it against a surcharge, and that sizes a
   KO_SCORE-class claim. The BOARD-LEVEL half (`retreatFreeGrant`) is still `_effective_retreat_cost`
   alone, so the divergence above stands exactly as written.

   **The five sites that still read the PRINTED cost and consult no Tool at all** — enumerated here
   because #306 made the sign matter, and a list is what stops "the consumers were audited" being
   read as "every retreat-cost reader is correct". Ignoring a Tool DISCOUNT over-states a cost
   (fail-closed, which is why they survived); ignoring a Tool SURCHARGE under-states it, so each is
   named with the direction that miss actually pushes:

   | site | whose body | a missed surcharge makes it… |
   |---|---|---|
   | `objectives.py` `_path_bench_extra` | theirs | read them as MORE mobile — pessimistic about the threat, safe |
   | `combat.py` `_can_promote` | theirs | admit the promotion — documented fail-OPEN by design, safe |
   | `planner.py` `_opp_active_pinned` | theirs | claim "not pinned", so FEWER deferrals — fail-closed, safe |
   | `pilot.py` `_retreat_mobility_credit` | mine | credit a body as retreat-funded one Energy early — a value term, not a claim |
   | `pilot.py` the disruptor-lock retreat guard | mine | believe a retreat is reachable when it is not — a crude guard, explicitly so |

   None is KO_SCORE-class, and Gravity Gemstone is 0 copies across our five decks, so this is a
   recorded boundary rather than a live bug. Wiring the delta into all five would move decisions on
   five unrelated surfaces in a commit that must land one cause at a time — and three of them are
   deliberately fail-open against the opponent, where the fix is not obviously a fix.

   **This is LATENT, not live**: every reader agrees on the four decks that have strategy modules,
   because none of them runs a board-level grant (`grimmsnarl_ex`/`mega_lucario` run Air Balloon,
   which is an attached Tool every reader already handles). It goes live the moment #149 onboards
   slowking — which is exactly why it is recorded here. The fail direction is safe meanwhile:
   `_can_retreat` under-claims, refusing a legal free retreat rather than asserting an illegal one.
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
TOWER = 802                     # a Stage 2 with a PRINTED retreat cost and no grant of its own —
                                # the row the predicate test needs to bite on (see its docstring)
METAL, A_WALK, A_WALL = 8, 71, 72


class _Skill:
    """The shape the provider walks — an object with `.text` (the engine's skill record)."""

    def __init__(self, text):
        self.text = text


class _Card:
    def __init__(self, *texts):
        self.skills = [_Skill(t) for t in texts]


# ---- the READ (the one card-knowledge seam, ADR-0056) -------------------------------------------

def test_the_flat_tool_reduction_still_reads_air_balloon():
    """Unchanged behaviour, pinned so the new clauses cannot regress it. The amount is written as
    repeated Colorless symbols, so it is COUNTED rather than read as a digit."""
    card = _Card("The Retreat Cost of the Pokémon this card is attached to is {C}{C} less.")
    assert _parse_tool_retreat_reduction(card) == 2


def test_rescue_board_reads_both_of_its_legs():
    """The two sentences are two different facts: the flat `{C}` always applies, the zeroing only
    below the threshold. Reading only the first is what made the shipped cost blind to the second."""
    card = _Card("The Retreat Cost of the Pokémon this card is attached to is {C} less. "
                 "If that Pokémon's remaining HP is 30 or less, it has no Retreat Cost.")
    assert _parse_tool_retreat_reduction(card) == 1
    assert _parse_tool_retreat_free_at_hp(card) == 30


def test_latias_ex_reads_as_a_board_level_basic_grant():
    """The board-level shape, pinned at the read (the exception documented above; the live-board
    test is owed to #149). The predicate travels WITH the grant, so adding a card adds a parse and a
    predicate rather than a call-site special case."""
    assert _parse_retreat_free_grant(
        _Card("Your Basic Pokémon in play have no Retreat Cost.")) == "basic"


def test_archaludon_reads_as_a_board_level_typed_grant():
    """The tracked-meta shape: the same board-level mechanism scoped by attached Energy type."""
    assert _parse_retreat_free_grant(
        _Card("All of your Pokémon that have {M} Energy attached have no Retreat Cost.")) \
        == "metal_attached"


def test_an_unmodelled_grant_parses_to_nothing_so_the_printed_cost_stands():
    """FAIL-CLOSED, the ruling's core safety property. N's Castle grants no Retreat Cost to "N's
    Pokémon in play" — an unauthored predicate — so it must parse to None and leave the printed cost
    standing, rather than guess something it cannot evaluate.

    The reason is no longer *"no membership oracle exists"*: Issue #306 built one, for the holder of
    a Tool. It does not rescue this card, and the difference is the point. A Tool's subject is ONE
    body whose name we hold; N's Castle sweeps every "N's Pokémon **in play**", *both players'*,
    which is a board question — and `retreatFreeGrant` carries a single predicate NAME evaluated
    against the one body that wants to retreat, with no shape for a family argument. Authoring it
    means a new predicate and a consumer that can ask the board, not a wider regex."""
    assert _parse_retreat_free_grant(
        _Card("N's Pokémon in play (both yours and your opponent's) have no Retreat Cost.")) is None
    assert _parse_tool_retreat_free_at_hp(_Card("Attach a Pokémon Tool to 1 of your Pokémon.")) == 0


def test_the_real_cards_parse_through_the_engine_provider():
    """The texts above prove the REGEXES; this proves they meet the real card records.

    CLAUDE.md's standing rule — verify card facts at source, never from memory — applied to a parser:
    a pattern that matches hand-typed prose but misses the engine's actual skill text would fail
    silently and fail-closed, which is exactly the shape of bug that hides. Note the real records use
    a typographic apostrophe, which is why the patterns match it loosely."""
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()
    air, rescue = stats.get(AIR_BALLOON), stats.get(RESCUE_BOARD)
    latias, archaludon = stats.get(LATIAS_EX), stats.get(ARCHALUDON)
    assert (air.retreatReduction, air.retreatFreeAtHp, air.retreatFreeGrant) == (2, 0, None)
    assert (rescue.retreatReduction, rescue.retreatFreeAtHp) == (1, 30)
    assert latias.retreatFreeGrant == "basic"
    assert archaludon.retreatFreeGrant == "metal_attached"
    # …and the unmodelled one stays unmodelled against the real record too (fail-closed).
    assert stats.get(1253).retreatFreeGrant is None                      # N's Castle


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
        ARCHALUDON: CardStat(ARCHALUDON, synthetic=True, name='Archaludon', hp=300, stage="stage2",
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
    """Rescue Board on a body at full HP shaves ONE, so a printed 2 still costs 1; the same body at
    30 HP or less retreats for FREE. The conditional leg on a live board, which is the seam this
    grant is testable at."""
    p = _pilot()
    healthy = poke(WALKER, energy=2, hp=120)
    healthy["tools"] = [{"id": RESCUE_BOARD}]
    damaged = dict(healthy, hp=30)
    assert p._effective_retreat_cost(_obs(healthy, [poke(BENCHIE, hp=90)]), healthy) == 1
    assert p._effective_retreat_cost(_obs(damaged, [poke(BENCHIE, hp=90)]), damaged) == 0


def test_a_board_level_ability_frees_my_basics_from_another_slot():
    """The shape no per-card read could see: the grant lives on a BENCHED body and applies to the
    ACTIVE one. Without this, `_effective_retreat_cost` charges the printed 2 — and under the convex
    build delta that is ~117 damage of phantom cost on a built attacker, systematically, for a deck
    built around free pivoting."""
    p = _pilot()
    active = poke(WALKER, energy=2, hp=120)                 # printed Retreat Cost 2, a Basic
    without = _obs(active, [poke(BENCHIE, hp=90)])
    with_latias = _obs(active, [poke(LATIAS_EX, hp=210)])
    assert p._effective_retreat_cost(without, active) == 2
    assert p._effective_retreat_cost(with_latias, active) == 0


def test_the_board_level_grant_respects_its_own_predicate():
    """"Your BASIC Pokémon in play" — a Stage 2 gets nothing, so the predicate is doing real work
    rather than being a blanket free-retreat switch.

    The Stage 2 leg used to assert `== 0` against Archaludon, whose printed cost was 0 anyway: it
    passed whether the predicate refused or not, which is the same defect Issue #408 found in the
    `stage` fixtures. `TOWER` has a printed 3, so a predicate that stopped discriminating fails."""
    p = _pilot()
    grantor = [poke(LATIAS_EX, hp=210)]
    stage2 = poke(TOWER, energy=3, hp=300)
    assert p._effective_retreat_cost(_obs(stage2, grantor), stage2) == 3   # refused: not a Basic
    basic = poke(WALKER, energy=2, hp=120)
    assert p._effective_retreat_cost(_obs(basic, grantor), basic) == 0     # granted: a Basic
    assert p._effective_retreat_cost(_obs(basic, [poke(BENCHIE, hp=90)]), basic) == 2  # no grantor


def test_the_grant_predicate_reads_a_value_the_provider_actually_emits():
    """The link the board tests above cannot supply, and whose absence made all of them vacuous.

    Every test in this section hands `_effective_retreat_cost` a `stage` it wrote itself. Until
    Issue #408 the provider wrote NONE — `CardStat.stage` was declared and never assigned — so the
    `grant == "basic"` predicate compared against None on every real board while these stayed green.
    A fixture is only evidence if production can emit the value it declares, so assert exactly that,
    against the real records: the grantor's `retreatFreeGrant` and the beneficiary's `stage` have to
    meet on the same two strings the predicate joins on.

    slowking's own line, because slowking is the deck that runs Latias ex: Slowpoke is the Basic the
    grant frees, Slowking the Stage 1 it must refuse."""
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()
    slowpoke, slowking = stats.get(162), stats.get(163)
    assert stats.get(LATIAS_EX).retreatFreeGrant == "basic"
    assert (slowpoke.stage, slowking.stage) == ("basic", "stage1")
    # the join, spelled as the predicate spells it — and its negative half
    assert (slowpoke.stage or "").lower() == "basic"
    assert (slowking.stage or "").lower() != "basic"
    # …and the printed costs the grant is worth something against (0 would make it untestable)
    assert slowpoke.retreatCost > 0 and slowking.retreatCost > 0


@pytest.mark.req("REQ-GEN-0026")
def test_a_free_retreat_destroys_no_build_and_so_costs_nothing():
    """The consumer's whole point (§8): `retreat_cost` is the BUILD the discard destroys, so a body
    that discards nothing pays nothing — and the free-pivot line is genuinely available."""
    p = _pilot()
    active = poke(WALKER, energy=2, hp=120)
    obs = _obs(active, [poke(LATIAS_EX, hp=210)])
    row = p.explain(obs).options[0].promote_retreat_working
    assert row is not None and row["retreat_cost"] == 0.0
