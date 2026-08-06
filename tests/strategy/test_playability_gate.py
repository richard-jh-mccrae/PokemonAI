"""Backward line topology — a hand card that can NEVER be played must cover no slot (Issue #288,
ADR-0104; the term-sufficiency audit's F12).

`development.line_topology` asks the FORWARD question (is this line's payoff still reachable?).
Nothing asked the mirror one: is this hand card's own PRE-EVOLUTION still reachable? Without it the
needs assignment happily hands a slot to a card that can never leave the hand — `slowking` runs 2×
Metagross (Stage 2, ``evolvesFrom`` **Metang**, id 276, 170 HP — verified at
``data/EN_Card_Data.csv``) with **no Metang and no Beldum** on the list, and an engine evolution
covers the `draw_engine` slot at the engine tier even with every copy of its base in the discard.

The engine half of that was written on `grimmsnarl_ex`'s Snorunt -> Froslass and re-pointed at
`slowking`'s Slowpoke -> Slowking when PR #436 deleted the deck (2026-08-06). Two consequences are
named where they bite rather than papered over: the `engine` Role is now the FIXTURE's declaration
(`_engine_pilot`), because no surviving shipped deck declares it on an evolution; and the Rare
Candy escape lost its last shipped-deck instance, because no surviving deck runs Rare Candy.

Two halves, tested here together because the gate is only sound if both hold:

  * ``common.playability`` — the pure oracle. Backward reachability over ``CardStat.evolvesFrom``
    NAMES against three zones (in play / hand / the sound "not provably gone" deck read), walked to
    full CHAIN depth, with the Rare Candy escape (a Stage 2 may skip its Stage 1 onto the root
    Basic — card text verified at ``data/EN_Card_Data.csv`` id 1079) and fail-OPEN epistemics
    (*unreadable is not unplayable*).
  * ``pilot._resolve_needs`` — the consumer. An unplayable row supplies NO slot of ANY kind, which
    is strictly more than the shipped ``deploy`` factor did: that factor zeroes the VALUE of the
    slots keyed on the card itself (`line`, `general`), but left the row ELIGIBLE for every shared
    slot — so a dead Froslass both covered the draw need and RAISED its price.
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
    itself can never reach the board, so neither can what sits on top of it. The one-hop reading
    the audit's cheapest-fix line describes would call this playable."""
    assert _playable(METAGROSS, deck=[BELDUM, METANG])
    assert _playable(METAGROSS, in_play=[METANG])          # the Stage 1 is already down
    assert not _playable(METAGROSS, hand=[METANG])         # ...but a HELD one still needs a Beldum
    assert _playable(METAGROSS, hand=[METANG], deck=[BELDUM])


@pytest.mark.req("REQ-NEEDS-0017")
def test_an_unresolvable_previous_stage_fails_open():
    """*Unreadable is not unplayable.* An evolution whose ``evolvesFrom`` names a card the pool
    holds no printing of makes no claim either way, so it keeps its eligibility — the same fail
    direction `gate_library.deploy_odds` documents."""
    stats = DictCardStatProvider({
        METAGROSS: CardStat(METAGROSS, name="Metagross", hp=170, evolvesFrom="Metang", stage2=True),
    })                                             # no Metang printing at all
    assert _playable(METAGROSS, stats=stats)


@pytest.mark.req("REQ-NEEDS-0017")
def test_rare_candy_keeps_a_stage_two_alive_over_a_dead_stage_one():
    """Rare Candy (Item, id 1079 — *"Choose 1 of your Basic Pokémon in play. If you have a Stage 2
    card in your hand that evolves from that Pokémon, put that card onto the Basic Pokémon to
    evolve it, skipping the Stage 1"*, verified at data/EN_Card_Data.csv) means a missing Stage 1
    does NOT prove a Stage 2 dead. Without the escape this is the gate's own false-positive, and
    `grimmsnarl_ex` — 1 Rare Candy + the Marnie's Impidimp -> Morgrem -> Grimmsnarl ex line — is a
    SHIPPED deck that can reach it."""
    assert _playable(METAGROSS, in_play=[BELDUM], candy=True)
    assert _playable(METAGROSS, deck=[BELDUM], candy=True)
    assert not _playable(METAGROSS, in_play=[BELDUM], candy=False)
    # the escape is Stage-2-only: Rare Candy cannot put a Stage 1 onto anything
    assert not _playable(SLOWKING, deck=[RARE_CANDY], candy=True)


@pytest.mark.req("REQ-NEEDS-0017")
def test_the_rare_candy_root_must_actually_be_a_basic():
    """The card says *"Choose 1 of your **Basic** Pokémon in play"*. Reading the root as "whatever is
    two hops down" would fire the escape on a body Rare Candy cannot legally target, so the root is
    confirmed to evolve from nothing. Shown on a synthetic four-stage chain — no real line is this
    deep, which is exactly why an assumption here would never be caught by a shipped deck."""
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
    """The tag replaced `planner._RARE_CANDY_ID`, so the two must not silently diverge: card 1079
    carries it and nothing else does. A second tagged card would widen the escape for every deck at
    once, which is the kind of change that should fail a test rather than pass unnoticed."""
    table = CardFunctions.load()
    tagged = {cid for cid in range(1, 2000)
              if playability.RARE_CANDY_TAG in set(table.tags(cid))}
    assert tagged == {RARE_CANDY}


@pytest.mark.req("REQ-NEEDS-0017")
def test_an_unreadable_tag_table_is_not_a_missing_rare_candy():
    """`Zones.rare_candy` is TRI-STATE. ``False`` means *provably no Rare Candy*; ``None`` means the
    caller had no Function Tag table to ask. Collapsing the second into the first would let the gate
    call a Stage 2 dead on the strength of a fact it never checked — and, because the oracle has two
    callers, would have them fail in opposite directions on the same missing table."""
    stats = _pool()
    assert not _playable(METAGROSS, in_play=[BELDUM], candy=False, stats=stats)
    assert _playable(METAGROSS, in_play=[BELDUM], candy=None, stats=stats)
    # ...and the tri-state changes nothing for a card the escape could never save.
    assert not _playable(SLOWKING, candy=None, stats=stats)


@pytest.mark.req("REQ-NEEDS-0017")
def test_a_setup_only_opener_is_still_unplayable_from_hand():
    """The `opener` route is deliberately NOT an escape. Cinderace (id 666, Stage 2, `evolvesFrom`
    Raboot) carries Explosiveness — *"If this Pokémon is in your hand when you are setting up to
    play, you may put it face down in the Active Spot"* (verified at data/EN_Card_Data.csv) — and
    `mega_starmie` runs 4 with no Raboot on the list.

    That route reaches only the ACTIVE spot, only during Set Up, before any consumer of this oracle
    runs; every site that asks is one a setup-only opener genuinely cannot reach. So the shipped
    verdict stands, and the rung built on it (`dont-fetch-the-setup-only-opener`: *"in hand it is a
    dead card"*) keeps its premise."""
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
    """`slowking` has no authored ``strategy.py`` (it is Issue #149's validation deck, not an agent),
    so its Pilot is built here from the committed 60-card ``deck.csv`` plus the win-condition roles
    a strategy would declare for Metagross. Those roles are the point: without them the line slot
    carries no worth and the defect the audit found cannot be shown at all.

    ``roles`` REPLACES that overlay for the engine-side cases below. Both halves of the Role table
    are the fixture's, not a shipped declaration, and the docstrings that use them say so — the
    alternative is not a more honest test, it is no test, because after PR #436 deleted
    `grimmsnarl_ex` (2026-08-06) NO shipped deck declares the `engine` Role on an evolution, which
    is the only shape the engine leg of the gate can bite."""
    from common.runtime import build_pilot
    agent_dir = REPO / "src" / "agents" / "slowking"
    deck = [int(x) for x in (agent_dir / "deck.csv").read_text(encoding="utf-8").splitlines()[:60] if x.strip()]
    deck = deck[:60 - len(deck_extra)] + list(deck_extra)
    strategy = Strategy(roles=dict(roles) if roles is not None
                        else {METAGROSS: ["win_condition", "primary_attacker"]})
    return build_pilot(strategy, deck)


def _engine_pilot():
    """The engine-leg fixture: `slowking`'s committed list — 4× Slowpoke -> 3× Slowking, 4× Lillie's
    Determination — with the `engine` Role DECLARED on Slowking so the evolution is an engine BODY
    and Lillie's is the engine SUPPORTER beside it. That is exactly the two-tier shape the band
    reads off (`ROLE_TIER["engine"]` = the body tier, `_ENGINE_SUPPORTER_KEEP` = the supporter one),
    and it is the shape `grimmsnarl_ex`'s Snorunt -> Froslass + Naveen carried before the deck was
    deleted.

    Said plainly, because the Role is the load-bearing part: Slowking's own text is *Seek
    Inspiration*, an attack, NOT a draw ability — the `engine` Role here is the FIXTURE's
    declaration standing in for the one a doctrine would make, the same licence `_slowking_pilot`
    already takes with Metagross. The multi-copy base is why this deck and not another: the
    "one copy still unseen" direction needs a base the discard can partly, not wholly, account for,
    and `dragapult_ex`'s Dudunsparce engine runs a SINGLE Dunsparce."""
    return _slowking_pilot(roles={SLOWKING: ["engine"]})


@pytest.mark.req("REQ-NEEDS-0017")
def test_slowkings_metagross_covers_no_slot_but_one_with_a_metang_does():
    """The audit's headline case. `slowking`'s list holds 2× Metagross and neither Metang nor
    Beldum, so a held Metagross is a 170-HP card that can never be played — it must supply NOTHING.
    Swap a Metang onto the list and the same card, on the same board, is live again."""
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
    """Soundness, the direction that matters: the deck read is *not provably gone*, never *seen*.
    Three of `slowking`'s four Slowpoke in the discard leaves one unseen (deck or a face-down
    prize), so the held Slowking is still a live engine and keeps its slot.

    The Active is Kyurem, a Basic on no evolution line, precisely so the base is absent from PLAY —
    a Slowpoke Active would make the Slowking playable for a reason that has nothing to do with the
    deck read this test is about."""
    pilot = _engine_pilot()
    rows, slots, elig = _slots_for(pilot, _obs([SLOWKING], active=KYUREM,
                                               discard=[SLOWPOKE] * 3))
    covered = _covered(rows, elig, SLOWKING)
    assert covered and any(slots[j].kind == "draw_engine" for j in covered)


@pytest.mark.req("REQ-NEEDS-0017")
def test_a_stranded_engine_neither_covers_the_draw_need_nor_raises_its_price():
    """The live defect. With all four Slowpoke in the discard a held Slowking can never be played —
    yet it used to (a) cover the `draw_engine` slot, so the REAL draw Supporter beside it priced at
    0 and shed for free, and (b) set that slot's band to the engine-BODY tier (12) instead of the
    engine-supporter band (8), because the band reads off the eligible rows. Both are gone: the slot
    prices as if the dead body were not in hand at all.

    Written against `grimmsnarl_ex`'s Snorunt -> Froslass + Naveen and re-pointed at `slowking`'s
    Slowpoke -> Slowking + Lillie's Determination when PR #436 deleted that deck (2026-08-06). Same
    two-tier shape, same two assertions; see `_engine_pilot` for what the fixture declares and why
    it has to."""
    pilot = _engine_pilot()
    gone = [SLOWPOKE] * 4
    rows, slots, elig = _slots_for(pilot, _obs([SLOWKING, LILLIES], active=KYUREM, discard=gone))
    assert _covered(rows, elig, SLOWKING) == set()

    engine = [j for j, s in enumerate(slots) if s.kind == "draw_engine"]
    assert len(engine) == 1
    supporter_row = next(k for k, r in enumerate(rows) if r["cid"] == LILLIES)
    assert engine[0] in elig[supporter_row], "the real draw Supporter still covers the draw need"

    # and the Supporter's keep-value is the one a lone Supporter earns — the dead body no longer
    # covers the need out from under it, nor inflates what covering it is worth.
    solo = _engine_pilot()
    _r2, s2, _e2 = _slots_for(solo, _obs([LILLIES], active=KYUREM, discard=gone))
    band = next(s.value for s in s2 if s.kind == "draw_engine")
    assert slots[engine[0]].value == pytest.approx(band)
    resupply = [0.0] * len(slots)
    assert needs.keep_v2(slots, elig, resupply, supporter_row) == pytest.approx(band)

    # The positive control the two assertions above need: with the base still reachable the SAME
    # board prices the need at the strictly higher engine-BODY band. Without this a gate that simply
    # stopped emitting an engine need at all would satisfy every assertion above.
    live = _engine_pilot()
    _r3, s3, e3 = _slots_for(live, _obs([SLOWKING, LILLIES], active=KYUREM, discard=[SLOWPOKE] * 3))
    body_band = next(s.value for s in s3 if s.kind == "draw_engine")
    assert body_band > band, (body_band, band)
    assert _covered(_r3, e3, SLOWKING), "the live engine body still covers the draw need"


@pytest.mark.req("REQ-NEEDS-0017")
def test_the_dragapult_inversion_no_longer_prefers_the_stranded_engine_over_its_base():
    """The measured priority inversion `dont-strand-the-evolving-engine` was built for
    (`dragapult_ex` STRATEGY.md §6): Dudunsparce is `card_is_support`, Dunsparce is not, so the
    fetch doctrine preferred the Stage-1 engine over the Basic that enables it. The deck runs ONE
    Dunsparce — discard it and the resolver must stop pricing the Dudunsparce as coverage, while a
    held Dunsparce keeps every slot it had."""
    pilot = _agent_pilot("dragapult_ex")
    rows, _slots, elig = _slots_for(
        pilot, _obs([DUDUNSPARCE, DREEPY], active=DREEPY, discard=[DUNSPARCE]))
    assert _covered(rows, elig, DUDUNSPARCE) == set()
    assert _covered(rows, elig, DREEPY), "the Basic that builds the win-condition line is untouched"


@pytest.mark.req("REQ-NEEDS-0017")
def test_basics_and_trainers_are_untouched_by_the_gate():
    """Regression: the gate may only ever bite an evolution. A held Basic (Dreepy, the
    win-condition line's base) and a held Trainer (Lillie's Determination, the draw engine) resolve
    to exactly the slots they did before it existed — on the very board that strips the Dudunsparce
    beside them, so the gate is provably firing and provably not touching these two."""
    pilot = _agent_pilot("dragapult_ex")
    obs = _obs([DREEPY, LILLIES, DUDUNSPARCE], active=MUNKIDORI, discard=[DUNSPARCE])
    rows, slots, elig = _slots_for(pilot, obs)
    assert _covered(rows, elig, DUDUNSPARCE) == set()          # the gate IS firing on this board
    assert any(slots[j].kind == "line" for j in _covered(rows, elig, DREEPY))
    assert any(slots[j].kind == "draw_engine" for j in _covered(rows, elig, LILLIES))


@pytest.mark.req("REQ-NEEDS-0017")
def test_rare_candy_in_hand_keeps_the_stage_two_wincon_eligible():
    """The false positive the one-hop reading of the spec would have shipped, driven through the
    RESOLVER rather than the pure oracle. A Beldum in play and no Metang anywhere: the held
    Metagross is still playable — onto that Beldum, skipping the Stage 1 — so the gate must NOT
    strip it, and with the Candy gone the same board DOES.

    This was `grimmsnarl_ex`'s 1 Rare Candy + Marnie's Impidimp -> Morgrem -> Grimmsnarl ex until
    PR #436 deleted the deck (2026-08-06), and it could NOT be re-pointed at a survivor: **no
    shipped deck runs Rare Candy at all** any more (checked across all five `deck.csv`), so the one
    Candy and the one Beldum are added to `slowking`'s committed list here. That is a real loss of
    altitude and worth naming — the escape now has no shipped-deck instance at either layer, only
    `test_rare_candy_keeps_a_stage_two_alive_over_a_dead_stage_one` on the synthetic pool above and
    this fixture-fed resolver case."""
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
    """`_stranded_evolution_set` now walks the SAME oracle rather than its own private copy of the
    recursion. That consolidation also gives it the Rare Candy escape it never had — a real fix, and
    provably a silent one here: no shipped deck holds both a Rare Candy and a stranded evolution, so
    all three answers are byte-identical to the ones the private walk gave.

    Three, not four: `grimmsnarl_ex` (which answered the empty set) was deleted by PR #436
    (2026-08-06). Only the AUTHORED decks are walked — the parameters are the agents with a
    `strategy.py`, which is what `_agent_pilot` loads — so `hydrapple` and `slowking` are absent
    here for the same reason they were before, not as fallout from that deletion."""
    assert _agent_pilot(agent)._stranded_evolution_set() == expected


@pytest.mark.req("REQ-NEEDS-0017")
def test_the_stranded_set_honours_rare_candy():
    """The latent bug the consolidation fixes: a deck whose Stage 1 is absent but which runs Rare
    Candy can still play its Stage 2, so that card is NOT stranded. Shown on a synthetic list
    because no shipped deck is shaped this way."""
    stats = _pool()
    deck = [BELDUM] * 4 + [METAGROSS] * 4 + [SLOWPOKE] * 52
    stranded = Pilot(Strategy(), deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats,
                     functions=CardFunctions({}))._stranded_evolution_set()
    assert stranded == frozenset({METAGROSS}), "no Metang and no Rare Candy — the Stage 2 is dead"

    with_candy = Pilot(Strategy(), deck=deck[:-1] + [RARE_CANDY], general_strategy=GENERAL_STRATEGY,
                       stats=stats,
                       functions=CardFunctions({RARE_CANDY: [playability.RARE_CANDY_TAG]}))
    assert with_candy._stranded_evolution_set() == frozenset()
