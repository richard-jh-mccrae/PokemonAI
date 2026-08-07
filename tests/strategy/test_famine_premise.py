"""The famine premise, at the DECISION seam — the frames the recorded corpus cannot supply (#142).

The Decision Gate (`famine_decider_sweep.py`, run at the deletion commit) replayed all 332 recorded
Corrections through both premises and found **zero** flips. That is an honest result and a narrow
one: the shipped interim `+1` patch already fixed dragapult f70, so the corpus holds no board that
DISCRIMINATES the retired premise from the oracle. The sweep went with the premise it compared
against, so the guard against a silent revert lives here instead.

Each test below is a board where the two premises genuinely disagree, built by mutating a real
recorded observation rather than inventing one. They are deliberately NOT added to
`data/corrections/` — that store is the record of HUMAN rulings, read by the tuner and the Leaf Lab,
and a synthetic frame carrying an authored `correct` would be a fabricated ruling in it.

Rules verified at source (`docs/rulebook.txt`), never recalled:
  * L206 — "If a Pokémon is Paralyzed, it cannot attack or retreat."
  * L190 — the same sentence for Asleep.
  * L215 — Asleep and Paralyzed are the ONLY two conditions that block retreat.
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
    """The discriminator the corpus has no frame for. Energy on the body makes the RETIRED premise
    read "payable", so it denies the famine and the stall stands down — on a Pokémon the rulebook
    forbids from attacking at all. The oracle reads the rule, not just the cost."""
    obs = _obs()
    me = _me(obs)
    me["active"][0]["energies"] = [E_R, E_P]        # comfortably pays Phantom Dive's {R}{P}
    me[condition] = True
    assert _famine(obs) is True, f"{condition} blocks the attack (rulebook L190/L206)"
    # The retired premise read this board as PAYABLE (Energy is attached) and denied the famine.
    # That gap is what these frames exist to keep closed now that it can no longer be A/B'd.


def test_an_unblocked_active_with_the_same_energy_is_not_a_famine():
    """The control: identical board, no condition. Keeps the test above honest — it is isolating
    the CONDITION, not some other property of this board."""
    obs = _obs()
    _me(obs)["active"][0]["energies"] = [E_R, E_P]
    assert _famine(obs) is False


def test_a_confused_active_is_not_a_famine():
    """Confusion makes you flip a coin before attacking; it does not forbid the attack (rulebook
    L215 lists only Asleep and Paralyzed as blocking). A famine premise that treated every condition
    alike would stall a turn it could have attacked in."""
    obs = _obs()
    me = _me(obs)
    me["active"][0]["energies"] = [E_R, E_P]
    me["confused"] = me["poisoned"] = me["burned"] = True
    assert _famine(obs) is False


# ── the affordability leg: the accel reach the retired `+1` could not see ───────────────────────

def test_the_oracle_reads_the_whole_budget_where_the_retired_plus_one_read_one_unit():
    """The f70 board itself no longer discriminates — the shipped `+1` patch already denies the
    famine there — so this asserts the PROPERTY that made the patch insufficient: the Budget on this
    board carries a two-unit option (Crispin attaches one Basic by its effect AND hands a second of
    a different type the unspent manual attach plays), which is what reaches a 2-cost TYPED attack.
    A revert to a one-unit model would leave `size` at 1 and this red."""
    pilot = _pilot()
    _board(pilot, _obs())
    mine = pilot._state_model.mine
    budget = mine.attach_budget(mine.active)
    assert budget.size >= 2, "Crispin's two halves are the whole point of the oracle"
    assert mine.active_famine is False


# `test_the_stall_gust_stands_down_on_the_f70_board` is DELETED here (POC-T4/5, Issue #386).
# `stall-gust-over-dev-when-starved` went with the gust doctrine's whether-to-play band, so its only
# behavioural assertion — `not in fired` — is now true of every board, and the `assert boss` beside
# it is a menu-shape guard, not a claim about the agent.
#
# Named successor: the FAMINE PREMISE this file is about is untouched and is asserted directly above
# (`mine.active_famine is False` on the f70 board, with the attach-budget size that makes it
# non-vacuous). What is gone is only the downstream rung that consumed it.


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
    """`reachable_attach` fails CLOSED — an unknown CardStat makes NO claim, so it returns False.
    Negating that would turn "I cannot tell" into "PROVABLE famine" and fire the +105 stall this
    premise exists to kill. The retired signal was explicit about the direction ("True on unknown
    stats — the starved stall-gust must only fire on a PROVABLE famine", ep83457493 f20)."""
    assert _blind_model([1, 1, 1]).mine.active_famine is False
    assert _blind_model([]).mine.active_famine is False       # even with nothing attached


def test_the_rule_leg_still_claims_a_famine_without_reading_a_stat():
    """The one claim that needs no card knowledge: the rules forbid the attack outright. Paralysis
    and turn-1-going-first hold even when nothing about the body resolves."""
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
    """The deliberate behaviour change (#142 ruling A), pinned so it cannot pass silently.

    The retired pair of guards did not compose: the accel half never checked that the Active was
    UNARMED, so merely HOLDING a Crispin suppressed a stall that an armed Active may legitimately
    take. The collapsed clause is gated on 0 attached Energy, so an armed Active reads
    `active_unarmed_but_able` False and the stall-gust family is free to fire — where the retired
    `not active_attack_payable_via_accel` clause blocked it."""
    obs = _obs()
    _me(obs)["active"][0]["energies"] = [E_R, E_P]     # ARMED, and Crispin is still in hand
    board = _board(_pilot(), obs)
    assert board.my_active_energy > 0
    assert board.active_famine is False                # it can attack — not a famine either way
    assert board.active_unarmed_but_able is False, (
        "an ARMED Active must not be told to swing-instead-of-stall; holding an accel is irrelevant")


def test_an_unarmed_active_reaching_an_attack_is_told_to_swing():
    """The complement, on the same board: strip the Energy and the Crispin line still reaches an
    attack, so the Active is unarmed-but-able and the stall stands down (this IS f70)."""
    board = _board(_pilot(), _obs())
    assert board.my_active_energy == 0
    assert board.active_unarmed_but_able is True
