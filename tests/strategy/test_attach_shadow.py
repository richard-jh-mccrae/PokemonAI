"""ATTACH shadow oracle — Phase-1 shadow of the energy-attach valuation grill (attach-valuation-
grill-spec.md "Grill rulings — 2026-07-21").

The shadow prices EVERY energy-attach option at a real attach decision in one currency and emits its
per-option working + top pick (`eq_pick`) + the agreement bit vs the shipped rungs' `chosen`. It
DECIDES NOTHING — like `discard_shadow` / `refresh_shadow` it is an evidence bridge (the fourth
shadow, ADR-0065), sparse (`None` off a real attach choice or mid-sim), and never changes `decide()`.

Two styles, mirroring `test_discard_shadow.py`:
  * Style A — synthetic hand-built boards pin the ruled TERMS deterministically.
  * Style B — replay committed correction frames; assert the shadow FIRES and (for the terms already
    built) that `eq_pick` matches the human `correct`. Frames awaiting a later increment are xfail,
    tagged with the ruling they need.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.telemetry import to_record

REPO = Path(__file__).resolve().parents[2]

ATTACH, HAND, ACTIVE, BENCH, MAIN = 8, 2, 4, 5, 0
_TOOL, _BASIC_ENERGY, _SPECIAL_ENERGY = 2, 5, 6
MEGA, STARYU, WATER, IGNITION, CAPE = 1031, 1030, 3, 17, 1100
LUNATONE = 675        # engine-only body — a non-attacking role
SOLROCK = 676         # a co-dependent engine body: worthless without a Lunatone in play (Ruling 6)


def _attach(hand_idx, area, in_idx):
    return {"type": ATTACH, "area": HAND, "index": hand_idx, "inPlayArea": area, "inPlayIndex": in_idx}


def _stats():
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                       minCostDamage=120, minAttackCost=1, maxDamageCost=3, evolvesFrom="Staryu"),
        STARYU: CardStat(STARYU, name="Staryu", hp=70, maxDamage=20, minCostDamage=20,
                         minAttackCost=1, maxDamageCost=1),
        LUNATONE: CardStat(LUNATONE, name="Lunatone", hp=110, maxDamage=50, minCostDamage=50,
                           minAttackCost=2, maxDamageCost=2, hasAbility=True),
        SOLROCK: CardStat(SOLROCK, name="Solrock", hp=110, maxDamage=70, minCostDamage=70,
                          minAttackCost=1, maxDamageCost=1),
        WATER: CardStat(WATER, name="Water", cardType=_BASIC_ENERGY, energyType=3),
        IGNITION: CardStat(IGNITION, name="Ignition", cardType=_SPECIAL_ENERGY, energyType=0),
        CAPE: CardStat(CAPE, name="Hero's Cape", cardType=_TOOL, aceSpec=True, hpBonus=100),
    })


def _pilot():
    funcs = CardFunctions({IGNITION: ["discard_eot"]})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], STARYU: ["starter"],
                            LUNATONE: ["engine"], SOLROCK: ["secondary_attacker", "engine"]},
                     partners={SOLROCK: [LUNATONE], LUNATONE: [SOLROCK]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=funcs)


def _obs(bench, hand, options, active=None, turn=6):
    me = {"active": [active], "bench": bench, "hand": hand}
    return {"current": {"players": [me, {"active": [None], "bench": []}], "yourIndex": 0, "turn": turn},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1, "option": options}}


def _row_for(shadow, index):
    return next((r for r in shadow["eq"] if r["i"] == index), None)


# ---------------------------------------------------------------- Style A: the ruled terms

@pytest.mark.req("REQ-ATTACH-SHADOW-0001")
def test_shadow_fires_and_emits_the_agreement_bit():
    p = _pilot()
    bench = [{"id": MEGA, "energies": [WATER, WATER], "hp": 330}, {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": WATER}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    dec = p.explain(obs)
    s = dec.attach_shadow
    assert s is not None
    assert set(s) >= {"eq", "eq_pick", "picks", "agree"}
    assert s["eq_pick"] == 0                       # concentrate onto the 2-Energy Mega, not the bare Staryu
    assert s["agree"] == (s["eq_pick"] in dec.chosen)


@pytest.mark.req("REQ-ATTACH-SHADOW-0002")
def test_energy_only_gate_abstains_on_a_tool():
    # Ruling 3: Hero's Cape rides OptionType.ATTACH but carries no Energy — never priced.
    p = _pilot()
    active = {"id": MEGA, "energies": [WATER, WATER], "hp": 330}   # 2->3 crosses to Nebula (positive)
    hand = [{"id": CAPE}, {"id": WATER}]
    opts = [_attach(0, ACTIVE, 0), _attach(1, ACTIVE, 0)]   # Cape -> active, Water -> active
    obs = _obs([], hand, opts, active=active)
    s = p.explain(obs).attach_shadow
    assert s is not None
    assert _row_for(s, 0) is None                  # the Tool abstains (no row)
    assert s["abstained"] == 1
    assert _row_for(s, 1) is not None              # the Water is priced
    assert s["eq_pick"] == 1


@pytest.mark.req("REQ-ATTACH-SHADOW-0003")
def test_resource_class_prefers_reusable_basic_over_burst_same_target():
    # Ruling resource-class: Ignition vs Water both top the active Mega 2->3 (Nebula); prefer the Basic.
    p = _pilot()
    active = {"id": MEGA, "energies": [WATER, WATER], "hp": 330}
    hand = [{"id": IGNITION}, {"id": WATER}]
    opts = [_attach(0, ACTIVE, 0), _attach(1, ACTIVE, 0)]   # Ignition -> active, Water -> active
    obs = _obs([], hand, opts, active=active)
    s = p.explain(obs).attach_shadow
    assert _row_for(s, 0)["marginal"] == _row_for(s, 1)["marginal"]     # same readiness bought
    assert _row_for(s, 0)["resource_cost"] > _row_for(s, 1)["resource_cost"]  # burst costs more
    assert s["eq_pick"] == 1                       # -> attach the reusable Water


@pytest.mark.req("REQ-ATTACH-SHADOW-0004")
def test_over_attach_marginal_is_zero_on_a_maxed_body():
    # A Mega already at its biggest-attack cost (3) gains nothing; the needy Staryu wins.
    p = _pilot()
    bench = [{"id": MEGA, "energies": [WATER, WATER, WATER], "hp": 330},
             {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": WATER}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    s = p.explain(obs).attach_shadow
    assert _row_for(s, 0)["marginal"] == 0.0       # maxed Mega: over-attach
    assert _row_for(s, 1)["marginal"] > 0.0        # bare Staryu still needs it
    assert s["eq_pick"] == 1


@pytest.mark.req("REQ-ATTACH-SHADOW-0005")
def test_role_gate_zeros_a_non_attacking_body():
    # Ruling 5b: an engine-only Lunatone gets 0 value even though it has a nominal attack.
    p = _pilot()
    bench = [{"id": LUNATONE, "energies": [], "hp": 110}, {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": WATER}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    s = p.explain(obs).attach_shadow
    assert _row_for(s, 0)["marginal"] == 0.0       # Lunatone: non-attacking role, gated
    assert s["eq_pick"] == 1                       # -> the Staryu attacker


@pytest.mark.req("REQ-ATTACH-SHADOW-0011")
def test_partner_conditional_engine_gated_when_partner_absent():
    # Ruling 6: a Solrock with NO Lunatone in play is a dead attacker -> gated to 0; the Staryu wins.
    p = _pilot()
    bench = [{"id": SOLROCK, "energies": [], "hp": 110}, {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": WATER}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    s = p.explain(obs).attach_shadow
    assert _row_for(s, 0)["marginal"] == 0.0       # partnerless Solrock: gated
    assert s["eq_pick"] == 1                        # -> the Staryu


@pytest.mark.req("REQ-ATTACH-SHADOW-0012")
def test_partner_conditional_engine_valued_when_partner_present():
    # With a Lunatone in play the pairing is live -> Solrock (Cosmic Beam 70) out-values the Staryu (20).
    p = _pilot()
    bench = [{"id": SOLROCK, "energies": [], "hp": 110}, {"id": STARYU, "energies": [], "hp": 70},
             {"id": LUNATONE, "energies": [], "hp": 110}]
    obs = _obs(bench, [{"id": WATER}],
               [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])   # Solrock, Staryu
    s = p.explain(obs).attach_shadow
    assert _row_for(s, 0)["marginal"] > 0.0        # partner present: Solrock is live
    assert s["eq_pick"] == 0                        # -> the Solrock (70 > 20)


@pytest.mark.req("REQ-ATTACH-SHADOW-0006")
def test_midsim_guard_and_telemetry_wiring():
    p = _pilot()
    bench = [{"id": MEGA, "energies": [WATER, WATER], "hp": 330}, {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": WATER}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    dec = p.explain(obs)
    assert to_record(dec).get("attach_shadow") == dec.attach_shadow   # rides the wire when present
    p._planning = True
    assert p.explain(obs).attach_shadow is None                       # silent under an engine sim


@pytest.mark.req("REQ-ATTACH-SHADOW-0007")
def test_shadow_is_silent_off_an_attach_decision():
    p = _pilot()
    obs = _obs([{"id": STARYU, "energies": [], "hp": 70}], [{"id": WATER}],
               [{"type": 12}, {"type": 11}])       # Retreat / End — no attach option
    assert p.explain(obs).attach_shadow is None


@pytest.mark.req("REQ-ATTACH-SHADOW-0014")
def test_agree_is_slot_based_not_raw_index():
    # The agreement bit compares the resolved target SLOT (area, position), not the raw option index.
    # Two IDENTICAL Water->ACTIVE copies (options 0 and 1) + one Water->BENCH (option 2). The oracle
    # picks the active (Mega 2->3 crosses to Nebula, beats the bare Staryu build), eq_pick=0. When the
    # rung's `chosen` is the OTHER active copy (index 1, same slot), that is AGREEMENT — raw-index
    # would have called it a false disagreement (the 82523811-59 / 82750161-59 hazard).
    p = _pilot()
    active = {"id": MEGA, "energies": [WATER, WATER], "hp": 330}
    obs = _obs([{"id": STARYU, "energies": [], "hp": 70}],
               [{"id": WATER}, {"id": WATER}, {"id": WATER}],
               [_attach(0, ACTIVE, 0), _attach(1, ACTIVE, 0), _attach(2, BENCH, 0)], active=active)
    sel = obs["select"]
    board = p._board(obs, sel)
    options = sel["option"]
    s_same = p._attach_shadow(obs, sel, board, options, [], chosen=[1])   # duplicate ACTIVE slot
    assert s_same["eq_pick"] == 0
    assert s_same["agree"] is True                 # index 1 is the SAME (ACTIVE,0) slot as eq_pick 0
    s_diff = p._attach_shadow(obs, sel, board, options, [], chosen=[2])   # the BENCH slot
    assert s_diff["agree"] is False                # a genuine target disagreement


# ---------------------------------------------------------------- Style B: corpus replay

def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _frame(ep, fr):
    for jf in sorted((REPO / "data" / "corrections").glob("*/corrections.jsonl")):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if str(d.get("episode_id")) == ep and d.get("decision", {}).get("frame") == fr:
                return d
    raise AssertionError(f"correction {ep}-{fr} not found")


def _agent(rec) -> str:
    """The buildable agent whose Strategy scores this frame. Some early corrections carry a blank
    `agent` (pre-attribution) or an opponent handle (`SkiChu`) that has no `src/agents/` dir — both
    are mega_starmie-archetype boards (Cinderace / Staryu / Mega Starmie ex), so score them on the
    mega_starmie pilot."""
    a = rec.get("agent") or ""
    return a if a in {"dragapult_ex", "mega_lucario", "mega_starmie", "slowking"} else "mega_starmie"


# frame -> (expectation, xfail-reason). expectation "pick" => eq_pick in the human `correct`;
# "abstain" => eq_pick is None (oracle declines to attach). A non-None reason xfails the frame,
# tagged with the later-increment ruling it needs. The tractable terms assert now.
_CORPUS = {
    ("82227388", 7): ("abstain", None),            # Ruling 3: all-Tool menu -> oracle declines to attach
    ("86088989", 63): ("pick", None),              # over-attach: no 3rd Energy on a 2-cost Lucario
    ("85046350", 21): ("pick", None),              # Ruling 5: don't power the Dunsparce draw-engine
    ("86089638", 18): ("pick", None),              # Ruling 5 + type-fit: on-type onto the Dreepy line
    ("83037962", 48): ("pick", None),              # doomed-DON'T-feed: 2 on a body needing 3 that dies = 0
    ("82749168", 61): ("pick", None),              # Ruling 1: concentrate on the started (2-Energy) carrier
    # Ruling 1: build the survivable 400-HP ACTIVE carrier (opp has Hariyama 150 / Riolu 180 that only
    # Nebula 210 KOs) rather than starting a fresh bench Mega. correct re-tagged [6]->[1] (2026-07-21;
    # the [6] tag was a redundant bench index identical to chosen). Assert the ACTIVE target — options
    # 1/3/5 are identical Basic->active copies, so pin the area, not one redundant index.
    ("82523811", 59): (("area", ACTIVE), None),
    ("83664340", 45): ("pick", None),              # Ruling 2a: arm the doomed Active (Jetting this turn)
    # Ruling 2b (overkill cap): active already KOs & nothing on the board needs the bigger attack ->
    # develop the benched second threat. correct=[1] tags Ignition->bench[0]; the energy is incidental
    # (target correction), and the oracle picks the durable Basic onto the same bench[0] target.
    ("82750161", 59): (("target", BENCH, 0), None),
    ("83037962", 70): ("pick", None),              # Ruling 4: feed the accelerator (Turbo Flare routes 3)
    ("84889539", 87): ("pick", None),              # Ruling 6: route to the Riolu line, not a partnerless Solrock
}


@pytest.mark.req("REQ-ATTACH-SHADOW-0010")
def test_accel_routing_drives_the_feed():
    # Ruling 4: on 83037962-70 feeding the Active Cinderace wins because Turbo Flare ROUTES ~3 Basic
    # onto the survivable bench carrier (a full Nebula build) — NOT because of Cinderace's own 50 attack.
    rec = _frame("83037962", 70)
    s = _tune()._build_pilot(_agent(rec))[0].explain(rec["obs"]).attach_shadow
    pick = next(r for r in s["eq"] if r["i"] == s["eq_pick"])
    assert pick["target"] == 666                        # Cinderace, the accelerator
    assert pick["accel_value"] > pick["this_turn"]      # routing value, not the accelerator's own attack


@pytest.mark.req("REQ-ATTACH-SHADOW-0008")
@pytest.mark.parametrize("ep,fr", list(_CORPUS))
def test_corpus_shadow_fires(ep, fr):
    rec = _frame(ep, fr)
    dec = _tune()._build_pilot(_agent(rec))[0].explain(rec["obs"])
    assert dec.attach_shadow is not None, f"{ep}-{fr}: attach shadow did not fire"


@pytest.mark.req("REQ-ATTACH-SHADOW-0009")
@pytest.mark.parametrize("ep,fr", list(_CORPUS))
def test_corpus_shadow_agrees_with_correct(ep, fr, request):
    expectation, reason = _CORPUS[(ep, fr)]
    if reason:
        request.node.add_marker(pytest.mark.xfail(reason=reason, strict=False))
    rec = _frame(ep, fr)
    correct = rec.get("correct") or []
    dec = _tune()._build_pilot(_agent(rec))[0].explain(rec["obs"])
    s = dec.attach_shadow
    assert s is not None
    if expectation == "abstain":
        assert s["eq_pick"] is None, f"{ep}-{fr}: expected abstain, got eq_pick={s['eq_pick']}"
    elif isinstance(expectation, tuple) and expectation[0] == "area":
        opt = rec["obs"]["select"]["option"][s["eq_pick"]]
        assert opt.get("inPlayArea") == expectation[1], \
            f"{ep}-{fr}: eq_pick target area {opt.get('inPlayArea')} != {expectation[1]}"
    elif isinstance(expectation, tuple) and expectation[0] == "target":
        opt = rec["obs"]["select"]["option"][s["eq_pick"]]
        assert (opt.get("inPlayArea"), opt.get("inPlayIndex")) == (expectation[1], expectation[2]), \
            f"{ep}-{fr}: eq_pick target {(opt.get('inPlayArea'), opt.get('inPlayIndex'))} != {expectation[1:]}"
    else:
        assert s["eq_pick"] in correct, f"{ep}-{fr}: eq_pick={s['eq_pick']} not in correct={correct}"


@pytest.mark.req("REQ-ATTACH-SHADOW-0013")
def test_corpus_shadow_silent_on_a_supporter_selection_frame():
    # 85786096-70 (dragapult_ex, slow_setup): the correct play is "Play Crispin" over "Play Boss's
    # Orders" — a WHICH-SUPPORTER decision. Every option is _PLAY (type 7); there is NO _ATTACH
    # option, so the energy-attach oracle prices nothing and must stay SILENT. A committed-board
    # guard that the fires-only eligibility filter (the attach_sweep probe) correctly EXCLUDES an
    # energy-adjacent _PLAY frame — kept out of _CORPUS, which asserts the shadow FIRES.
    rec = _frame("85786096", 70)
    dec = _tune()._build_pilot(_agent(rec))[0].explain(rec["obs"])
    assert dec.attach_shadow is None
