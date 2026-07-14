"""God-free cabt episodes convert and replay divergence-free (ADR-0059 M4).

Real meta-deck games through the reveal-oracle path: draw/coin binding from the
mover's own windows, prize identities at take time, deck order from revealed
listings, look-at-top-N pre-binding from DECK->LOOKING move logs. DLL-free.
REQ-CGPY-0002.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "parity"))

from from_cabt import convert  # noqa: E402

from cgpy.verify.replayer import replay  # noqa: E402

FIXTURES = REPO / "tests" / "fixtures"

EPISODES = [
    ("match-replay.json", 60),              # arena episode (Iono deck; card 269)
    ("episode-81364540-replay.json.gz", 43),  # kaggle episode (look-reveal binding)
    ("episode-84073333-replay.json.gz", 111),  # Lucky Helmet reactive draw-2-when-damaged
    ("episode-82749168-replay.json.gz", 96),   # Sparkling Crystal Tera cost -1
    ("episode-82229122-replay.json.gz", 110),  # Deluxe Bomb reactive counters; Crustle snipe
    ("episode-85046764-replay.json.gz", 152),  # Relicanth Memory Dive: Archaludon ex uses
                                               # Duraludon's Hammer In / Raging Hammer
    ("episode-83285531-replay.json.gz", 84),   # Nebula Beam ignore-effects pierces Full
                                               # Metal Lab's -30 (+ Memory Dive)
    ("episode-82234130-replay.json.gz", 114),  # Latias ex Skyliner: Basic Pokémon retreat free
    ("episode-83692318-replay.json.gz", 144),  # clean Froslass-deck game (Munkidori/Risky-Ruins
                                               # counter placements; general counter coverage)
    ("episode-83286739-replay.json.gz", 83),   # Xerosic's Machinations: opponent discards to 3
    ("episode-83665001-replay.json.gz", 51),   # Sacred Ash: shuffle Pokémon from discard to deck
    ("episode-82871172-replay.json.gz", 153),  # Full Moon Rondo: +20 damage per benched
                                               # Pokémon (both sides)
    ("episode-84895564-replay.json.gz", 42),   # Mega Kangaskhan ex Run Errand: draw 2,
                                               # Active-only, 1×/turn globally
    ("episode-83970983-replay.json.gz", 41),   # Kyogre Riptide: 20 per Basic {W} in
                                               # discard, then shuffle those into deck
    ("episode-83695982-replay.json.gz", 183),  # Energy Recycler: shuffle Basic Energy
                                               # from discard to deck (xPickDiscard)
    ("episode-85687852-replay.json.gz", 14),   # Prism Energy attach un-deferred
    ("episode-82229613-replay.json.gz", 40),   # Team Rocket's Transceiver: deck-search a
                                               # "Team Rocket" Supporter to hand
    ("episode-83690879-replay.json.gz", 56),   # Mega Abomasnow ex Hammer-lanche: mill top 6,
                                               # 100 damage per Basic {W} milled (mill-output
                                               # reveal-binding + milled_basic_energy scale)
    ("episode-83119861-replay.json.gz", 55),   # Powerglass end-of-turn tool: after TURN_END,
                                               # may attach a Basic Energy from discard to the
                                               # Active holder (suspendable between-turns select)
    ("episode-83691502-replay.json.gz", 167),  # Prime Catcher: ACE SPEC gust + self-switch
    ("episode-85164605-replay.json.gz", 147),  # Wondrous Patch: attach a Basic {P} from discard
                                               # to a benched {P} Pokémon (discard-source distribute)
    ("episode-83486999-replay.json.gz", 132),  # Blaziken ex Seething Spirit: attach a Basic
                                               # Energy from discard to a Pokémon (xDiscardEnergyAttachChoose)
    ("episode-83665798-replay.json.gz", 46),   # Tool Scrapper: discard up to 2 tools in play
                                               # (xDiscardToolsInPlay)
    ("episode-83457493-replay.json.gz", 112),  # Kieran: "Choose 1" — switch OR +30 vs ex/V
                                               # (xFirstEffectChoose splices the picked branch)
    ("episode-85605555-replay.json.gz", 121),  # Dusclops Cursed Blast ability offered at MAIN
                                               # (xCurseBlast def; effect exercised in the guard below)
    ("episode-82871056-replay.json.gz", 33),   # Secret Box (ACE SPEC): discard 3 others, then
                                               # search Item/Tool/Supporter/Stadium (costHandTrash
                                               # + xDeckToHandBuckets)
    ("episode-83459752-replay.json.gz", 75),   # Larry's Skill: discard hand, search Pokémon/
                                               # Supporter/Basic Energy (xDiscardHandDraw n=0 + buckets)
    ("episode-85711162-replay.json.gz", 74),    # Alakazam Psychic Draw via Rare Candy: a skip-
                                                # evolve fires the Stage-2's onEvolve triggered ask
                                                # (op_rare_candy_evolve queues the onEvolve trigger)
    ("episode-83971785-replay.json.gz", 44),    # Hariyama Heave-Ho Catcher: onEvolve ask is
                                                # SUPPRESSED when the opponent has no benched
                                                # Pokémon (oppBenchExists legal gate — no gust target)
    ("episode-81907835-replay.json.gz", 84),    # Jamming Tower play-enable: the stadium is offered
                                                # + placed; its tools-inert passive is a verified
                                                # no-op here (stadium:{} — passive deferred to Phase 4)
    ("episode-84897913-replay.json.gz", 51),    # Area Zero Underdepths play-enable: offered +
                                                # placed; the Tera bench_max=8 passive stays <=5 here
    ("episode-84077723-replay.json.gz", 56),    # Dizzying Valley play-enable: the confused-no-recover
                                                # -on-evolve passive is a verified no-op (no such evolve)
    ("episode-82871704-replay.json.gz", 91),    # Area Zero Underdepths bench_max=8: a player with a
                                                # Tera in play benches a 6th+ Pokémon (effective_bench_max)
    ("episode-85609929-replay.json.gz", 118),   # Area Zero bench_max=8, second deck (Tera bench > 5)
]


@pytest.mark.parametrize("name,frames", EPISODES, ids=lambda v: str(v))
def test_cabt_episode_replays_clean(name, frames):
    path = FIXTURES / name
    if name.endswith(".gz"):
        payload = json.loads(gzip.decompress(path.read_bytes()))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    trace = convert(payload)
    assert len(trace.frames) == frames, "conversion shrank — the episode changed?"
    report = replay(trace)
    assert report.clean, f"\n{report}"


def test_froslass_freezing_shroud_fires():
    """Froslass "Freezing Shroud" puts a Checkup damage counter on every ability-Pokémon
    (both sides, except Froslass). This episode isn't clean end-to-end (a later,
    unrelated blocker), but WITHOUT the ability cgpy diverges at the very first
    Freezing-Shroud checkup (frame 54: both Drakloak + both Munkidori take a counter,
    the Froslass Active skipped); WITH it, the replay sails well past. Guards the
    between-turns counter placement + order without needing a fully-clean fixture."""
    path = FIXTURES / "episode-83697279-replay.json.gz"
    payload = json.loads(gzip.decompress(path.read_bytes()))
    report = replay(convert(payload))
    assert report.frames_green > 54, (
        f"Freezing Shroud regressed — diverged at the checkup:\n{report}")


def _guard(name: str, min_green: int, what: str) -> None:
    """A card whose op fires but whose episode has a LATER unrelated blocker: assert the
    replay sails past the op's frames (the '+0 verified groundwork' pattern)."""
    path = FIXTURES / name
    payload = json.loads(gzip.decompress(path.read_bytes()))
    report = replay(convert(payload))
    assert report.frames_green > min_green, f"{what} regressed:\n{report}"


def test_eri_reveals_and_discards_items():
    # Eri: opp reveals hand, discard up to 2 Item cards found (xOppHandRevealDiscardMulti).
    _guard("episode-82225138-replay.json.gz", 22, "Eri")


def test_lucian_bottoms_hands_and_coin_draws():
    # Lucian: both bottom their hands, then coin -> draw 6/3 (xBothBottomHandCoinDraw).
    _guard("episode-85687339-replay.json.gz", 28, "Lucian")


def test_energy_swatter_reveals_and_bottoms_energy():
    # Energy Swatter: reveal opp hand, put a found Energy on the bottom of their deck
    # (xOppHandRevealChooseFiltered).
    _guard("episode-82006648-replay.json.gz", 5, "Energy Swatter")


def test_dusknoir_cursed_blast_self_ko():
    # Dusknoir Cursed Blast: put 13 counters on 1 opp Pokémon, then self-KO + opp claims
    # its prize inline (xCurseBlast, the mid-turn ability self-KO path).
    _guard("episode-83689598-replay.json.gz", 31, "Cursed Blast")


def test_ogerpon_teal_dance_fires():
    """Teal Mask Ogerpon ex "Teal Dance": attach a Basic {G} from hand to THIS Pokémon,
    then draw a card. This episode isn't clean end-to-end (a later, unrelated blocker),
    but WITHOUT the ability cgpy diverges at the very first activation (frame ~20: the
    ATTACH_TO {G} pick → ATTACH + DRAW, no ATTACH_FROM since it self-targets); WITH it
    the replay reaches frame 40. Guards the holderSelf + thenDraw attach branch."""
    path = FIXTURES / "episode-81906755-replay.json.gz"
    payload = json.loads(gzip.decompress(path.read_bytes()))
    report = replay(convert(payload))
    assert report.frames_green > 21, (
        f"Teal Dance regressed — diverged at the ability:\n{report}")
