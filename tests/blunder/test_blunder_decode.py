"""Rendering engine option dicts into human-readable dropdown labels."""
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.decisions import iter_decisions
from train.blunder.decode import option_label

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"


def _frame(ctx):
    return next(d for d in iter_decisions(load_replay(FIXTURE)) if d.select_context == ctx)


def test_main_option_labels_resolve_against_board():
    """Cards resolve by (area, index) position in the full-info board; the Attach target carries
    its disambiguating board descriptor (slot + current/max HP)."""
    d = _frame("Main")              # opts: Play, Play, Play, Attach, End
    labels = [option_label(o, d.current) for o in d.options]
    assert labels[-1] == "End turn"
    assert labels[3] == "Attach Basic {D} Energy → Munkidori (active · 110/110)"
    assert labels[0].startswith("Play ")


def test_card_select_labels_resolve_card_names():
    """REQ-BLUNDER-0008: Card-select options resolve to the referenced card name,
    including the top-level `looking` zone (deck/hand cards stay a bare name)."""
    bench = _frame("ToBench")
    assert option_label(bench.options[0], bench.current) == "Budew"
    hand = _frame("ToHand")         # area 12 == looking
    assert option_label(hand.options[0], hand.current) == "Lillie's Determination"


def test_identical_bench_copies_are_disambiguated():
    """REQ-BLUNDER-0011: two same-named Pokemon on the bench render distinct labels --
    slot index, current/max HP and attached-energy count tell the copies apart."""
    sw = _frame("Switch")           # two 'Mega Starmie ex' on bench, one energised
    labels = [option_label(o, sw.current) for o in sw.options]
    assert labels[0] == "Mega Starmie ex (bench 1 · 330/330 · 1⚡)"
    assert labels[1] == "Mega Starmie ex (bench 2 · 330/330)"
    assert labels[0] != labels[1]


def test_attack_label_names_the_move():
    """REQ-BLUNDER-0011: an Attack option resolves its move name from the engine
    (attackId -> name), so a two-attack Pokemon no longer renders 'Attack' twice."""
    current = {"yourIndex": 0, "players": [{}, {}]}
    assert option_label({"type": "Attack", "attackId": 489}, current) == "Attack with Combustion"
    # unknown id degrades to a non-misleading, still-distinct label (never bare 'Attack')
    assert option_label({"type": "Attack", "attackId": -1}, current) == "Attack #-1"


def test_opponent_owned_target_is_marked():
    """REQ-BLUNDER-0011: a target on the opponent's board is prefixed 'opp' so a
    snipe / Boss / Crushing-Hammer target shows whose Pokemon it is."""
    current = {
        "yourIndex": 0,
        "players": [
            {"active": [{"name": "Munkidori", "hp": 110, "maxHp": 110, "energyCards": []}]},
            {"bench": [{"name": "Riolu", "hp": 60, "maxHp": 70,
                        "energyCards": [{"name": "x"}]}]},
        ],
    }
    opt = {"type": "Card", "area": 5, "index": 0, "playerIndex": 1}   # opp bench 0
    assert option_label(opt, current) == "opp Riolu (bench 1 · 60/70 · 1⚡)"


def test_evolve_label_shows_which_basic_is_targeted():
    """REQ-BLUNDER-0011: Evolve names the resulting card AND the disambiguated basic it
    evolves (inPlayArea/inPlayIndex) -- previously only the hand card was shown."""
    current = {
        "yourIndex": 0,
        "players": [{
            "hand": [{"name": "Mega Starmie ex"}],
            "bench": [{"name": "Staryu", "hp": 60, "maxHp": 60, "energyCards": []},
                      {"name": "Staryu", "hp": 60, "maxHp": 60, "energyCards": []}],
        }, {}],
    }
    opt = {"type": "Evolve", "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 1}
    assert option_label(opt, current) == "Evolve Mega Starmie ex → Staryu (bench 2 · 60/60)"


def test_engine_integer_option_types_render_like_their_named_equivalents():
    """Corrections preserve the engine's integer enum; a report must not expose bare `9` / `13`."""
    current = {
        "yourIndex": 0,
        "players": [{
            "hand": [{"name": "Mega Starmie ex"}],
            "bench": [{"name": "Staryu", "hp": 60, "maxHp": 60, "energyCards": []}],
        }, {}],
    }
    option = {"type": 9, "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 0}
    assert option_label(option, current) == "Evolve Mega Starmie ex → Staryu (bench 1 · 60/60)"


def test_observation_card_ids_are_enriched_for_report_labels():
    """The agent observation omits visible card names but the committed card table resolves them."""
    current = {
        "yourIndex": 0,
        "players": [{
            "hand": [{"id": 1031}],
            "bench": [{"id": 1030, "hp": 60, "maxHp": 60, "energyCards": []}],
        }, {}],
    }
    option = {"type": 9, "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 0}
    assert option_label(option, current) == "Evolve Mega Starmie ex → Staryu (bench 1 · 60/60)"
