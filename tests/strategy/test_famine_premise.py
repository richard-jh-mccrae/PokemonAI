"""The famine premise at the DECISION seam — boards the recorded corpus cannot supply (Issue #142).

Each test mutates a real recorded observation. They are deliberately NOT in `data/corrections/`:
that store is the record of HUMAN rulings, so a synthetic authored `correct` would be a fabricated one.

Rules verified at `docs/rulebook.txt`: Asleep (L190) and Paralyzed (L206) cannot attack or retreat,
and L215 makes those the ONLY two conditions that block retreat.
"""
import copy
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "tests" / "fixtures" / "corrections" / "dp_stall_gust_false_famine_accel_f70.json"

BOSS = 1182                     # Boss's Orders — the gust Supporter the stall family plays
E_R, E_P = 2, 5                 # Basic {R} / {P} Energy card ids


def _obs():
    return copy.deepcopy(json.loads(FIX.read_text(encoding="utf-8"))["obs"])


def _me(obs):
    cur = obs["current"]
    return cur["players"][cur.get("yourIndex", 0)]


def _pilot():
    """A FRESH shipped dragapult Pilot per call — the statefulness lesson."""
    import importlib.util
    import sys
    sys.path.insert(0, str(REPO / "tools"))
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot("dragapult_ex")[0]


def _board(pilot, obs):
    return pilot._board(obs, obs.get("select"), carried=pilot.carried())


def _famine(obs) -> bool:
    return _board(_pilot(), obs).active_famine


# ── the rule-level leg: a body the rules will not let attack ────────────────────────────────────

@pytest.mark.parametrize("condition", ["paralyzed", "asleep"])
def test_a_blocked_active_is_a_famine_however_much_energy_it_holds(condition):
    """The oracle reads the RULE, not just the cost: attached Energy makes the body look payable."""
    obs = _obs()
    me = _me(obs)
    me["active"][0]["energies"] = [E_R, E_P]        # comfortably pays Phantom Dive's {R}{P}
    me[condition] = True
    assert _famine(obs) is True, f"{condition} blocks the attack (rulebook L190/L206)"


def test_an_unblocked_active_with_the_same_energy_is_not_a_famine():
    """The control: identical board, no condition, so the test above isolates the CONDITION."""
    obs = _obs()
    _me(obs)["active"][0]["energies"] = [E_R, E_P]
    assert _famine(obs) is False


def test_a_confused_active_is_not_a_famine():
    """Confusion makes you flip a coin before attacking; it does not forbid the attack (L215)."""
    obs = _obs()
    me = _me(obs)
    me["active"][0]["energies"] = [E_R, E_P]
    me["confused"] = me["poisoned"] = me["burned"] = True
    assert _famine(obs) is False


# ── the affordability leg: the accel reach the retired `+1` could not see ───────────────────────

def test_the_oracle_reads_the_whole_budget_where_the_retired_plus_one_read_one_unit():
    """Crispin attaches one Basic by its effect AND hands a second the unspent manual attach plays,
    so the Budget is two units — which is what reaches a 2-cost TYPED attack."""
    pilot = _pilot()
    _board(pilot, _obs())
    mine = pilot._state_model.mine
    budget = mine.attach_budget(mine.active)
    assert budget.size >= 2, "Crispin's two halves are the whole point of the oracle"
    assert mine.active_famine is False


# `test_the_stall_gust_stands_down_on_the_f70_board` was DELETED (Issue #386) with the rung it
# consumed; the famine premise itself is asserted directly above.


# ── fail direction: "I cannot tell" must never read as a PROVABLE famine ────────────────────────

def _blind_model(energies, *, turn=5, **flags):
    """A StateModel whose Stat Provider resolves NOTHING — the unreadable-body case."""
    from common.state_model import StateModel
    from common.strategy.combat import CombatMath
    from common.scouting.provider import DictCardStatProvider
    me = {"active": [{"id": 999, "hp": 100, "energies": list(energies)}], "bench": [], "hand": [],
          "prize": [None] * 4, "deckCount": 30}
    me.update(flags)
    obs = {"current": {"players": [me, {"active": [], "bench": [], "prize": [None] * 6}],
                       "yourIndex": 0, "turn": turn}}
    return StateModel.build(obs, combat=CombatMath(DictCardStatProvider({}), functions=None,
                                                   transients=None))


def test_an_unreadable_body_is_not_a_famine():
    """`reachable_attach` fails CLOSED: negating that would turn "I cannot tell" into "PROVABLE
    famine"."""
    assert _blind_model([1, 1, 1]).mine.active_famine is False
    assert _blind_model([]).mine.active_famine is False       # even with nothing attached


def test_the_rule_leg_still_claims_a_famine_without_reading_a_stat():
    """Paralysis and turn-1-going-first hold even when nothing about the body resolves."""
    assert _blind_model([1, 1, 1], paralyzed=True).mine.active_famine is True
    assert _blind_model([1, 1, 1], turn=1).mine.active_famine is True


def test_a_body_less_side_makes_no_famine_claim():
    from common.state_model import StateModel
    from common.strategy.combat import CombatMath
    from common.scouting.provider import DictCardStatProvider
    obs = {"current": {"players": [{"active": [], "bench": [], "hand": [], "prize": [None] * 4},
                                   {"active": [], "bench": [], "prize": [None] * 6}],
                       "yourIndex": 0, "turn": 5}}
    m = StateModel.build(obs, combat=CombatMath(DictCardStatProvider({}), functions=None,
                                                transients=None))
    assert m.mine.active_famine is False


# ── the one row this phase deliberately starts firing on ───────────────────────────────────────

def test_an_armed_active_holding_an_accelerator_is_not_told_to_swing():
    """Issue #142 ruling A. `active_unarmed_but_able` is gated on 0 attached Energy, so merely
    HOLDING an accelerator cannot suppress a stall an armed Active may legitimately take."""
    obs = _obs()
    _me(obs)["active"][0]["energies"] = [E_R, E_P]     # ARMED, and Crispin is still in hand
    board = _board(_pilot(), obs)
    assert board.my_active_energy > 0
    assert board.active_famine is False                # it can attack — not a famine either way
    assert board.active_unarmed_but_able is False, (
        "an ARMED Active must not be told to swing-instead-of-stall; holding an accel is irrelevant")


def test_an_unarmed_active_reaching_an_attack_is_told_to_swing():
    """The complement: no Energy, but the Crispin line still reaches an attack (this IS f70)."""
    board = _board(_pilot(), _obs())
    assert board.my_active_energy == 0
    assert board.active_unarmed_but_able is True
