"""Backward line topology — a hand card that can NEVER be played must cover no slot (Issue #288,
ADR-0104).

Two halves, tested together because the gate is only sound if both hold: ``common.playability`` (the
pure oracle — backward reachability over ``CardStat.evolvesFrom`` NAMES against in play / hand / the
"not provably gone" deck read, to full CHAIN depth, with the Rare Candy escape and fail-OPEN
epistemics) and ``pilot._resolve_needs`` (the consumer — an unplayable row supplies NO slot of ANY
kind, where the shipped ``deploy`` factor only zeroed the value of the card's own slots).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from common import needs, playability
from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

REPO = Path(__file__).resolve().parents[2]

# Real card ids, verified at data/EN_Card_Data.csv (never from memory).
BELDUM, METANG, METAGROSS = 274, 275, 276      # Beldum -> Metang -> Metagross (170 HP, Stage 2)
SLOWPOKE, SLOWKING = 162, 163                  # slowking's 4x -> 3x engine line (the Role is declared
                                               # by the fixture — see `_engine_pilot`)
KYUREM = 144                                   # a Basic on slowking's list, on no evolution line
DUNSPARCE, DUDUNSPARCE = 305, 66               # dragapult_ex's stranded-engine risk
DREEPY, DRAKLOAK, DRAGAPULT = 119, 120, 121
MUNKIDORI = 112                                # a Basic — an Active that is on no evolution line
RARE_CANDY = 1079
LILLIES = 1227                                 # Lillie's Determination — a draw Supporter


# ============================================================ the pure oracle
def _pool():
    """A synthetic pool carrying one 3-stage line, one single-hop line, a Basic, a Trainer and a
    Rare Candy — enough to exercise every branch without the engine."""
    return DictCardStatProvider({
        BELDUM: CardStat(BELDUM, name="Beldum", hp=60),
        METANG: CardStat(METANG, name="Metang", hp=100, evolvesFrom="Beldum"),
        METAGROSS: CardStat(METAGROSS, name="Metagross", hp=170, evolvesFrom="Metang", stage2=True),
        SLOWPOKE: CardStat(SLOWPOKE, name="Slowpoke", hp=80),
        SLOWKING: CardStat(SLOWKING, name="Slowking", hp=120, evolvesFrom="Slowpoke"),
        RARE_CANDY: CardStat(RARE_CANDY, name="Rare Candy", cardType=1),
    })


def _playable(cid, *, in_play=(), hand=(), deck=(), candy=False, stats=None):
    """``candy`` mirrors `Zones.rare_candy`'s tri-state: True / False / None (no tag table)."""
    stats = stats if stats is not None else _pool()
    return playability.playable_from_hand(
        cid, stats=stats,
        zones=playability.zones(stats, in_play_ids=in_play, hand_ids=hand, deck_ids=deck,
                               rare_candy_reachable=candy))


@pytest.mark.req("REQ-NEEDS-0017")
def test_a_basic_a_trainer_and_an_unknown_card_are_always_playable():
    """The gate is EVOLUTION-only. A Basic needs nothing but a Bench slot, a Trainer nothing at all,
    and a card the pool cannot read is not a card we may call dead (fail OPEN)."""
    assert _playable(BELDUM)                       # a Basic, with nothing anywhere
    assert _playable(RARE_CANDY)                   # an Item
    assert _playable(99999)                        # unknown id — no claim


@pytest.mark.req("REQ-NEEDS-0017")
def test_an_evolution_is_playable_from_any_one_of_the_three_zones():
    """In play / in hand / still unseen in deck — ANY one suffices, and each is a genuinely
    different route (evolve it now; bench it then evolve; draw it then bench then evolve)."""
    assert _playable(SLOWKING, in_play=[SLOWPOKE])
    assert _playable(SLOWKING, hand=[SLOWPOKE])
    assert _playable(SLOWKING, deck=[SLOWPOKE])
    assert not _playable(SLOWKING)                 # Slowpoke nowhere -> provably dead


@pytest.mark.req("REQ-NEEDS-0017")
def test_the_walk_is_the_whole_chain_not_one_hop():
    """A Metang in HAND does not make a Metagross playable when every Beldum is gone: the Metang
    itself can never reach the board, so neither can what sits on top of it."""
    assert _playable(METAGROSS, deck=[BELDUM, METANG])
    assert _playable(METAGROSS, in_play=[METANG])          # the Stage 1 is already down
    assert not _playable(METAGROSS, hand=[METANG])         # ...but a HELD one still needs a Beldum
    assert _playable(METAGROSS, hand=[METANG], deck=[BELDUM])


@pytest.mark.req("REQ-NEEDS-0017")
def test_an_unresolvable_previous_stage_fails_open():
    """*Unreadable is not unplayable.* An ``evolvesFrom`` the pool holds no printing of makes no
    claim either way, so the card keeps its eligibility."""
    stats = DictCardStatProvider({
        METAGROSS: CardStat(METAGROSS, name="Metagross", hp=170, evolvesFrom="Metang", stage2=True),
    })                                             # no Metang printing at all
    assert _playable(METAGROSS, stats=stats)


@pytest.mark.req("REQ-NEEDS-0017")
def test_rare_candy_keeps_a_stage_two_alive_over_a_dead_stage_one():
    """Rare Candy (id 1079) puts a Stage 2 onto a Basic, skipping the Stage 1, so a missing Stage 1
    does NOT prove a Stage 2 dead. Without the escape this is the gate's own false positive."""
    assert _playable(METAGROSS, in_play=[BELDUM], candy=True)
    assert _playable(METAGROSS, deck=[BELDUM], candy=True)
    assert not _playable(METAGROSS, in_play=[BELDUM], candy=False)
    # the escape is Stage-2-only: Rare Candy cannot put a Stage 1 onto anything
    assert not _playable(SLOWKING, deck=[RARE_CANDY], candy=True)


@pytest.mark.req("REQ-NEEDS-0017")
def test_the_rare_candy_root_must_actually_be_a_basic():
    """The card says *"Choose 1 of your **Basic** Pokémon in play"*, so the root must evolve from
    nothing. Shown on a synthetic four-stage chain — no real line is this deep."""
    stats = DictCardStatProvider({
        1: CardStat(1, synthetic=True, name="Root", hp=60),
        2: CardStat(2, synthetic=True, name="S1", hp=80, evolvesFrom="Root"),
        3: CardStat(3, synthetic=True, name="S2", hp=110, evolvesFrom="S1", stage2=True),
        4: CardStat(4, synthetic=True, name="S3", hp=160, evolvesFrom="S2", stage2=True),
        RARE_CANDY: CardStat(RARE_CANDY, name="Rare Candy", cardType=1),
    })
    # S3's two-hops-down card is S1, which is NOT a Basic -> no escape, even with the Candy live.
    assert not _playable(4, in_play=[1], deck=[2], candy=True, stats=stats)
    # ...while the genuine Basic -> Stage 1 -> Stage 2 shape does take it.
    assert _playable(3, in_play=[1], candy=True, stats=stats)


@pytest.mark.req("REQ-NEEDS-0017")
def test_the_shipped_tag_table_marks_exactly_the_rare_candy_card():
    """The tag replaced `planner._RARE_CANDY_ID`, so the two must not silently diverge: a second
    tagged card would widen the escape for every deck at once."""
    table = CardFunctions.load()
    tagged = {cid for cid in range(1, 2000)
              if playability.RARE_CANDY_TAG in set(table.tags(cid))}
    assert tagged == {RARE_CANDY}


@pytest.mark.req("REQ-NEEDS-0017")
def test_an_unreadable_tag_table_is_not_a_missing_rare_candy():
    """`Zones.rare_candy` is TRI-STATE: ``False`` is *provably no Rare Candy*, ``None`` is *no
    Function Tag table to ask*. Collapsing them calls a Stage 2 dead on a fact never checked."""
    stats = _pool()
    assert not _playable(METAGROSS, in_play=[BELDUM], candy=False, stats=stats)
    assert _playable(METAGROSS, in_play=[BELDUM], candy=None, stats=stats)
    # ...and the tri-state changes nothing for a card the escape could never save.
    assert not _playable(SLOWKING, candy=None, stats=stats)


@pytest.mark.req("REQ-NEEDS-0017")
def test_a_setup_only_opener_is_still_unplayable_from_hand():
    """The `opener` route (Cinderace's Explosiveness) is deliberately NOT an escape: it reaches only
    the ACTIVE spot, only during Set Up, before any consumer of this oracle runs."""
    pilot = _agent_pilot("mega_starmie")
    assert 666 in pilot._stranded_evolution_set()
    rows, _slots, elig = _slots_for(pilot, _obs([666], active=1030))   # 1030 = Staryu
    assert _covered(rows, elig, 666) == set()


@pytest.mark.req("REQ-NEEDS-0017")
def test_a_name_cycle_grounds_out_instead_of_recursing_forever():
    """A malformed pool where two cards evolve from each other must terminate — and ground out as
    UNPLAYABLE, since such a chain never reaches a Basic (the `_stranded_evolution_set` rule)."""
    stats = DictCardStatProvider({
        1: CardStat(1, synthetic=True, name="A", hp=60, evolvesFrom="B"),
        2: CardStat(2, synthetic=True, name="B", hp=60, evolvesFrom="A"),
    })
    assert not _playable(1, hand=[2], stats=stats)


# ============================================================ the resolver gate
def _obs(hand, *, active, bench=(), discard=(), turn=6):
    return {"current": {"players": [
        {"active": [{"id": active, "hp": 100, "maxHp": 100, "energies": []}],
         "bench": [{"id": b, "hp": 100, "maxHp": 100, "energies": []} for b in bench],
         "hand": [{"id": c} for c in hand],
         "discard": [{"id": c} for c in discard],
         "prizes": [None] * 6},
        {"active": [{"id": active, "hp": 100, "maxHp": 100, "energies": []}], "bench": []},
    ], "yourIndex": 0, "turn": turn}}


def _slots_for(pilot, obs):
    """The hand rows resolved through the ONE resolver, plus each row's covered slot indices."""
    board = pilot._board_hypothetical(obs)
    rows = pilot._needs_hand_rows(obs, board)
    slots, elig = pilot._resolve_needs(obs, board, rows)
    return rows, slots, elig


def _covered(rows, elig, cid) -> set:
    return {j for k, r in enumerate(rows) if r["cid"] == cid for j in elig[k]}


def _agent_pilot(agent: str):
    """The agent's real engine-backed Pilot (`common.runtime.build_pilot`, the ADR-0055 one build)."""
    import importlib.util

    from common.runtime import build_pilot
    agent_dir = REPO / "src" / "agents" / agent
    spec = importlib.util.spec_from_file_location(f"{agent}_playability_strategy",
                                                  agent_dir / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    deck = [int(x) for x in (agent_dir / "deck.csv").read_text(encoding="utf-8").splitlines()[:60] if x.strip()]
    return build_pilot(mod.STRATEGY, deck)


def _slowking_pilot(deck_extra=(), roles=None):
    """`slowking` has no authored ``strategy.py``, so its Pilot is built from the committed
    ``deck.csv`` plus the roles a strategy would declare; ``roles`` REPLACES that overlay."""
    from common.runtime import build_pilot
    agent_dir = REPO / "src" / "agents" / "slowking"
    deck = [int(x) for x in (agent_dir / "deck.csv").read_text(encoding="utf-8").splitlines()[:60] if x.strip()]
    deck = deck[:60 - len(deck_extra)] + list(deck_extra)
    strategy = Strategy(roles=dict(roles) if roles is not None
                        else {METAGROSS: ["win_condition", "primary_attacker"]})
    return build_pilot(strategy, deck)


def _engine_pilot():
    """The `engine` Role on Slowking is the FIXTURE's declaration, not a shipped one — no surviving
    deck declares it on an evolution, which is the only shape the engine leg of the gate can bite."""
    return _slowking_pilot(roles={SLOWKING: ["engine"]})


@pytest.mark.req("REQ-NEEDS-0017")
def test_slowkings_metagross_covers_no_slot_but_one_with_a_metang_does():
    """`slowking`'s list holds 2× Metagross and neither Metang nor Beldum, so a held Metagross can
    never be played. Swap a Metang onto the list and the same card, same board, is live again."""
    dead = _slowking_pilot()
    rows, _slots, elig = _slots_for(dead, _obs([METAGROSS], active=SLOWPOKE))
    assert rows and any(r["cid"] == METAGROSS for r in rows)
    assert _covered(rows, elig, METAGROSS) == set()

    live = _slowking_pilot(deck_extra=(METANG, BELDUM))
    rows, slots, elig = _slots_for(live, _obs([METAGROSS], active=SLOWPOKE))
    covered = _covered(rows, elig, METAGROSS)
    assert covered, "a Metagross whose line is on the list must still cover its own line slot"
    assert any(slots[j].kind == "line" for j in covered)


@pytest.mark.req("REQ-NEEDS-0017")
def test_a_base_in_the_discard_with_a_copy_still_unseen_stays_eligible():
    """The deck read is *not provably gone*, never *seen*. The Active is Kyurem (a Basic on no line)
    precisely so the base is absent from PLAY and only the deck read can keep the Slowking alive."""
    pilot = _engine_pilot()
    rows, slots, elig = _slots_for(pilot, _obs([SLOWKING], active=KYUREM,
                                               discard=[SLOWPOKE] * 3))
    covered = _covered(rows, elig, SLOWKING)
    assert covered and any(slots[j].kind == "draw_engine" for j in covered)


@pytest.mark.req("REQ-NEEDS-0017")
def test_a_stranded_engine_neither_covers_the_draw_need_nor_raises_its_price():
    """An unplayable engine body used to cover the `draw_engine` slot — so the REAL draw Supporter
    priced at 0 and shed for free — and to set that slot's band to the engine-BODY tier."""
    pilot = _engine_pilot()
    gone = [SLOWPOKE] * 4
    rows, slots, elig = _slots_for(pilot, _obs([SLOWKING, LILLIES], active=KYUREM, discard=gone))
    assert _covered(rows, elig, SLOWKING) == set()

    engine = [j for j, s in enumerate(slots) if s.kind == "draw_engine"]
    assert len(engine) == 1
    supporter_row = next(k for k, r in enumerate(rows) if r["cid"] == LILLIES)
    assert engine[0] in elig[supporter_row], "the real draw Supporter still covers the draw need"

    # the Supporter's keep-value is the one a LONE Supporter earns
    solo = _engine_pilot()
    _r2, s2, _e2 = _slots_for(solo, _obs([LILLIES], active=KYUREM, discard=gone))
    band = next(s.value for s in s2 if s.kind == "draw_engine")
    assert slots[engine[0]].value == pytest.approx(band)
    resupply = [0.0] * len(slots)
    assert needs.keep_v2(slots, elig, resupply, supporter_row) == pytest.approx(band)

    # Positive control: with the base reachable the SAME board prices the need at the higher
    # engine-BODY band, so a gate that stopped emitting the need at all cannot pass.
    live = _engine_pilot()
    _r3, s3, e3 = _slots_for(live, _obs([SLOWKING, LILLIES], active=KYUREM, discard=[SLOWPOKE] * 3))
    body_band = next(s.value for s in s3 if s.kind == "draw_engine")
    assert body_band > band, (body_band, band)
    assert _covered(_r3, e3, SLOWKING), "the live engine body still covers the draw need"


@pytest.mark.req("REQ-NEEDS-0017")
def test_the_dragapult_inversion_no_longer_prefers_the_stranded_engine_over_its_base():
    """The inversion `dont-strand-the-evolving-engine` was built for: Dudunsparce is
    `card_is_support` and Dunsparce is not, so the fetch doctrine preferred the engine over its base."""
    pilot = _agent_pilot("dragapult_ex")
    rows, _slots, elig = _slots_for(
        pilot, _obs([DUDUNSPARCE, DREEPY], active=DREEPY, discard=[DUNSPARCE]))
    assert _covered(rows, elig, DUDUNSPARCE) == set()
    assert _covered(rows, elig, DREEPY), "the Basic that builds the win-condition line is untouched"


@pytest.mark.req("REQ-NEEDS-0017")
def test_basics_and_trainers_are_untouched_by_the_gate():
    """The gate may only ever bite an evolution — asserted on the very board that strips the
    Dudunsparce beside them, so the gate is provably firing and provably not touching these two."""
    pilot = _agent_pilot("dragapult_ex")
    obs = _obs([DREEPY, LILLIES, DUDUNSPARCE], active=MUNKIDORI, discard=[DUNSPARCE])
    rows, slots, elig = _slots_for(pilot, obs)
    assert _covered(rows, elig, DUDUNSPARCE) == set()          # the gate IS firing on this board
    assert any(slots[j].kind == "line" for j in _covered(rows, elig, DREEPY))
    assert any(slots[j].kind == "draw_engine" for j in _covered(rows, elig, LILLIES))


@pytest.mark.req("REQ-NEEDS-0017")
def test_rare_candy_in_hand_keeps_the_stage_two_wincon_eligible():
    """The one-hop reading's false positive, driven through the RESOLVER. No shipped deck runs Rare
    Candy any more, so the Candy and the Beldum are added to `slowking`'s committed list here."""
    pilot = _slowking_pilot(deck_extra=(RARE_CANDY, BELDUM))
    rows, _slots, elig = _slots_for(
        pilot, _obs([METAGROSS, RARE_CANDY], active=BELDUM))
    assert _covered(rows, elig, METAGROSS), "Rare Candy still reaches the Stage 2"

    # ...and with the Rare Candy gone too, the same board DOES strip it.
    rows, _slots, elig = _slots_for(
        pilot, _obs([METAGROSS], active=BELDUM, discard=[RARE_CANDY]))
    assert _covered(rows, elig, METAGROSS) == set()


# ============================================================ the consolidation guard
@pytest.mark.req("REQ-NEEDS-0017")
@pytest.mark.parametrize("agent,expected", [
    ("dragapult_ex", frozenset()),
    ("mega_lucario", frozenset()),
    ("mega_starmie", frozenset({666})),          # Cinderace, with no Raboot on the list
])
def test_the_deck_static_stranded_set_is_unchanged_on_every_shipped_deck(agent, expected):
    """`_stranded_evolution_set` walks the SAME oracle rather than a private copy of the recursion,
    which also gives it the Rare Candy escape. Only AUTHORED decks (those with a `strategy.py`)."""
    assert _agent_pilot(agent)._stranded_evolution_set() == expected


@pytest.mark.req("REQ-NEEDS-0017")
def test_the_stranded_set_honours_rare_candy():
    """A deck whose Stage 1 is absent but which runs Rare Candy can still play its Stage 2. Shown on
    a synthetic list because no shipped deck is shaped this way."""
    stats = _pool()
    deck = [BELDUM] * 4 + [METAGROSS] * 4 + [SLOWPOKE] * 52
    stranded = Pilot(Strategy(), deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats,
                     functions=CardFunctions({}))._stranded_evolution_set()
    assert stranded == frozenset({METAGROSS}), "no Metang and no Rare Candy — the Stage 2 is dead"

    with_candy = Pilot(Strategy(), deck=deck[:-1] + [RARE_CANDY], general_strategy=GENERAL_STRATEGY,
                       stats=stats,
                       functions=CardFunctions({RARE_CANDY: [playability.RARE_CANDY_TAG]}))
    assert with_candy._stranded_evolution_set() == frozenset()
