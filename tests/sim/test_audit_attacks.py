"""Attack-audit pure helpers (ADR-0032 item 5, measurement half): panel selection, deck
construction, scenario planning, log-window damage extraction, record shaping, merge.

Lib-free — the engine drive-shell is covered by ``tests/test_audit_attacks_engine.py``.
"""
import pytest

from sim.audit_attacks import (
    CRUSTLE, _missing_typed, attack_window, bench_fodder, board_snapshot, build_side_deck,
    damage_from_window, error_record, evolution_chain, merge_records, pick_panel,
    plan_scenarios, record_key, shape_record,
)

# Synthetic pool: plain dicts, same as drive-shell builds from all_card_data().
W, F, P, G, FIRE = 3, 6, 5, 1, 2   # EnergyType ints


def _mon(hp, etype=W, weak=None, resist=None, basic=True, ability=False, tera=False,
         ex=False, mega=False, evolves_from=None, name="Mon"):
    return {"name": name, "pokemon": True, "basic": basic, "hp": hp, "energyType": etype,
            "weakness": weak, "resistance": resist, "hasAbility": ability, "tera": tera,
            "ex": ex, "megaEx": mega, "evolvesFrom": evolves_from}


def _pool():
    return {
        10: _mon(130, etype=F, name="Attacker"),                     # Fighting attacker
        20: _mon(310, weak=G, name="BigVanilla"),                    # vanilla vs F: no F-weak/resist
        21: _mon(120, weak=G, name="SmallVanilla"),
        30: _mon(270, weak=F, name="BigWeak"),                       # weak to Fighting
        31: _mon(90, weak=F, name="SmallWeak"),
        40: _mon(130, resist=F, name="Resist"),                      # resists Fighting
        41: _mon(220, resist=F, ability=True, name="ResistAbility"), # bigger, but has ability
        50: _mon(200, weak=F, tera=True, name="TeraWeak"),           # tera excluded from panel
        60: _mon(70, name="Staryu2"),
        61: _mon(330, basic=False, mega=True, evolves_from="Staryu2", name="MegaTip"),
        CRUSTLE: _mon(150, etype=G, weak=FIRE, basic=False, ability=True,
                      evolves_from="Dwebble2", name="Crustle"),
        344: _mon(70, etype=G, name="Dwebble2"),
    }


# --- panel selection (REQ-AUDIT-0001) ---------------------------------------------------


@pytest.mark.req("REQ-AUDIT-0001")
def test_panel_vanilla_is_highest_hp_basic_with_no_ability_no_matchup():
    panel = pick_panel(_pool()[10], _pool())
    assert panel["vanilla"] == 20            # 310 HP, not weak/resist to Fighting, no ability


@pytest.mark.req("REQ-AUDIT-0001")
def test_panel_weak_matches_attacker_type_and_prefers_hp():
    panel = pick_panel(_pool()[10], _pool())
    assert panel["weak"] == 30               # weak to F, 270 > 90; tera 50 excluded


@pytest.mark.req("REQ-AUDIT-0001")
def test_panel_resist_prefers_no_ability_over_hp():
    panel = pick_panel(_pool()[10], _pool())
    assert panel["resist"] == 40             # ability-free 130 beats 220-with-ability


@pytest.mark.req("REQ-AUDIT-0001")
def test_panel_missing_matchup_is_none_not_a_guess():
    pool = _pool()
    water_attacker = _mon(100, etype=W)      # nothing in pool weak/resist to Water
    panel = pick_panel(water_attacker, pool)
    assert panel["weak"] is None and panel["resist"] is None


@pytest.mark.req("REQ-AUDIT-0001")
def test_panel_prevent_ex_only_for_ex_attackers():
    pool = _pool()
    assert pick_panel(_mon(100, ex=True), pool)["prevent_ex"] == CRUSTLE
    assert pick_panel(_mon(100, mega=True), pool)["prevent_ex"] == CRUSTLE
    assert pick_panel(_mon(100), pool)["prevent_ex"] is None


# --- chain + deck construction (REQ-AUDIT-0002/0003) ------------------------------------


@pytest.mark.req("REQ-AUDIT-0003")
def test_evolution_chain_walks_names_basic_first():
    assert evolution_chain(61, _pool()) == [60, 61]
    assert evolution_chain(10, _pool()) == [10]           # Basic is its own chain


@pytest.mark.req("REQ-AUDIT-0002")
def test_side_deck_is_60_with_four_of_each_chain_card():
    deck = build_side_deck([60, 61], [W, W, W])
    assert len(deck) == 60
    assert deck.count(60) == 4 and deck.count(61) == 4
    assert deck.count(3) == 52                            # Water fill (EnergyType 3 -> card 3)


@pytest.mark.req("REQ-AUDIT-0002")
def test_side_deck_maps_colorless_to_a_real_energy_card():
    deck = build_side_deck([10], [0, 0, 0])               # colorless cost -> plays basic Energy
    assert len(deck) == 60
    assert all(c in (10, 3) for c in deck)


@pytest.mark.req("REQ-AUDIT-0002")
def test_side_deck_seeds_bench_fodder_within_copy_limits():
    deck = build_side_deck([344, CRUSTLE], [0], fodder=[20, 30])
    assert len(deck) == 60
    assert deck.count(20) == 4 and deck.count(30) == 4    # snipe targets drawable


@pytest.mark.req("REQ-AUDIT-0002")
def test_bench_fodder_picks_sturdy_clean_bodies_and_respects_exclude():
    picks = bench_fodder(_pool(), exclude={20}, n=2)
    assert picks == [30, 10]           # top HP after exclude; no ability (41), no tera (50)


@pytest.mark.req("REQ-AUDIT-0002")
def test_missing_typed_tracks_the_typed_cost_not_just_the_count():
    assert _missing_typed([G, 0], []) == {1}          # {G}{C}: Grass card 1 still needed
    assert _missing_typed([G, 0], [W]) == {1}         # Water attach never pays the {G}
    assert _missing_typed([G, 0], [G]) == set()       # typed met; count gate covers {C}
    assert _missing_typed([0, 0, 0], []) == set()     # all-colorless: nothing typed to chase


# --- scenario planning (REQ-AUDIT-0008) --------------------------------------------------


@pytest.mark.req("REQ-AUDIT-0008")
def test_plan_covers_the_full_panel_without_sweep():
    plans = plan_scenarios(_pool()[10], _pool())
    names = [p["scenario"] for p in plans]
    assert names == ["vanilla", "weak", "resist"]         # non-ex attacker: no prevent_ex
    assert all(p["sweep"] is None for p in plans)


@pytest.mark.req("REQ-AUDIT-0008")
def test_plan_keeps_unmeasurable_scenarios_with_no_defender():
    plans = plan_scenarios(_mon(100, etype=W), _pool())   # no Water-weak/resist bodies
    by_name = {p["scenario"]: p for p in plans}
    assert by_name["weak"]["defender"] is None            # explicit could-not-measure, not dropped


@pytest.mark.req("REQ-AUDIT-0008")
def test_sweep_adds_single_variable_points_on_vanilla_only():
    plans = plan_scenarios(_pool()[10], _pool(), sweep=True)
    sweeps = [p for p in plans if p["sweep"]]
    assert {(p["sweep"]["var"], p["sweep"]["step"]) for p in sweeps} == {
        ("energy", 1), ("energy", 2), ("hand", 2), ("hand", 4)}
    assert all(p["scenario"] == "vanilla" for p in sweeps)
    assert all(p["defender"] == 20 for p in sweeps)
    e1 = next(p for p in sweeps if p["sweep"] == {"var": "energy", "step": 1})
    assert e1["extra_energy"] == 1 and e1["delay_turns"] == 0
    h2 = next(p for p in sweeps if p["sweep"] == {"var": "hand", "step": 2})
    assert h2["delay_turns"] == 2 and h2["extra_energy"] == 0


# --- log-window damage extraction (REQ-AUDIT-0004) ---------------------------------------

_ATTACK, _HP, _TURN_START, _TURN_END, _COIN = 15, 16, 2, 3, 22


def _obs(active_serial=900, active_hp=310, bench=(), seat=1, my_serial=100, my_hp=130):
    def pk(serial, hp):
        return {"serial": serial, "hp": hp, "maxHp": hp, "id": 1, "energies": [3]}
    players = [
        {"active": [pk(my_serial, my_hp)], "bench": [], "hand": [{"id": 3}] * 5},
        {"active": [pk(active_serial, active_hp)], "bench": [pk(s, h) for s, h in bench]},
    ]
    if seat == 0:
        players.reverse()
    return {"current": {"players": players, "yourIndex": 0}}


@pytest.mark.req("REQ-AUDIT-0004")
def test_snapshot_maps_serials_to_slots():
    snap = board_snapshot(_obs(bench=[(901, 70)]), 1)
    assert snap["active"] == {"serial": 900, "hp": 310}
    assert snap["bench"] == [{"serial": 901, "hp": 70}]


@pytest.mark.req("REQ-AUDIT-0004")
def test_attack_window_slices_from_the_attack_to_the_turn_boundary():
    logs = [
        {"type": 4},                                       # pre-attack draw: excluded
        {"type": _ATTACK, "attackId": 147},
        {"type": _HP, "serial": 900, "value": -70},
        {"type": _TURN_END},
        {"type": _HP, "serial": 900, "value": -10},        # next-turn poison tick: excluded
    ]
    win = attack_window(logs, 147)
    assert [l.get("value") for l in win if l["type"] == _HP] == [-70]


@pytest.mark.req("REQ-AUDIT-0004")
def test_attack_window_is_empty_when_the_attack_never_fired():
    assert attack_window([{"type": 4}], 147) == []


@pytest.mark.req("REQ-AUDIT-0004")
def test_attack_window_uses_the_last_replayed_chunk_not_the_first():
    # Engine logs are per-viewing-player: defender-view chunk REPLAYS the turn, so a naive
    # first-occurrence slice stops at the replayed boundary and drops rider damage.
    attacker_view = [{"type": _ATTACK, "attackId": 1487},
                     {"type": _HP, "serial": 900, "value": -120}]
    defender_view = [{"type": _TURN_END},                  # defender's own prev turn end
                     {"type": _TURN_START},
                     {"type": _ATTACK, "attackId": 1487},  # same attack, replayed
                     {"type": _HP, "serial": 900, "value": -120},
                     {"type": _HP, "serial": 901, "value": -50},   # the snipe rider
                     {"type": _TURN_END}]
    win = attack_window(attacker_view + defender_view, 1487)
    assert [l.get("value") for l in win if l["type"] == _HP] == [-120, -50]   # no double-count


@pytest.mark.req("REQ-AUDIT-0004")
def test_damage_splits_active_bench_and_self_by_serial():
    snap_def = board_snapshot(_obs(bench=[(901, 70), (902, 70)]), 1)
    snap_me = board_snapshot(_obs(), 0)
    window = [
        {"type": _ATTACK, "attackId": 1487},
        {"type": _HP, "serial": 900, "value": -120},       # defender Active
        {"type": _HP, "serial": 902, "value": -50},        # bench snipe
        {"type": _HP, "serial": 100, "value": -30},        # my recoil
        {"type": _COIN, "head": True},
    ]
    d = damage_from_window(window, snap_def, snap_me)
    assert d["dealtActive"] == 120
    assert d["dealtBench"] == [50]
    assert d["dealtSelf"] == 30
    assert d["coinLogs"] == 1
    assert d["koed"] is False


@pytest.mark.req("REQ-AUDIT-0004")
def test_damage_flags_a_ko_when_dealt_reaches_hp():
    snap_def = board_snapshot(_obs(active_hp=70), 1)
    window = [{"type": _ATTACK, "attackId": 1}, {"type": _HP, "serial": 900, "value": -70}]
    d = damage_from_window(window, snap_def, board_snapshot(_obs(active_hp=70), 0))
    assert d["koed"] is True


@pytest.mark.req("REQ-AUDIT-0004")
def test_zero_damage_attack_reads_as_zero_not_missing():
    snap_def = board_snapshot(_obs(), 1)
    window = [{"type": _ATTACK, "attackId": 1488}]         # ability blocked everything
    d = damage_from_window(window, snap_def, board_snapshot(_obs(), 0))
    assert d["dealtActive"] == 0 and d["dealtBench"] == [] and d["koed"] is False


@pytest.mark.req("REQ-AUDIT-0004")
def test_healing_hp_change_is_not_counted_as_damage():
    snap_def = board_snapshot(_obs(), 1)
    window = [{"type": _ATTACK, "attackId": 1},
              {"type": _HP, "serial": 900, "value": 30}]   # heal, not a hit
    d = damage_from_window(window, snap_def, board_snapshot(_obs(), 0))
    assert d["dealtActive"] == 0


# --- record shaping + merge (REQ-AUDIT-0005/0006/0007) -----------------------------------


def _rec(**kw):
    base = dict(attack_id=1488, attacker_id=1031, scenario="prevent_ex", printed=210,
                defender_id=CRUSTLE, defender_hp=150, defender_bench=2,
                damage={"dealtActive": 210, "dealtBench": [], "dealtSelf": 0,
                        "coinLogs": 0, "koed": True},
                energies=3, hand_size=4, coin=None, sweep=None)
    base.update(kw)
    return shape_record(**base)


@pytest.mark.req("REQ-AUDIT-0005")
def test_record_carries_the_full_measurement_shape():
    r = _rec()
    assert r["attackId"] == 1488 and r["attackerCardId"] == 1031
    assert r["scenario"] == "prevent_ex" and r["printed"] == 210
    assert r["dealtActive"] == 210 and r["dealtBench"] == []
    assert r["defenderCardId"] == CRUSTLE and r["defenderHp"] == 150
    assert r["defenderBench"] == 2                          # whiffed rider vs no target
    assert r["attackerEnergies"] == 3 and r["myHandSize"] == 4
    assert r["coin"] is None and r["koed"] is True
    assert "error" not in r


@pytest.mark.req("REQ-AUDIT-0006")
def test_error_record_is_an_explicit_ledger_entry():
    e = error_record(999, 5, "resist", "no resistant defender for type 3")
    assert e["attackId"] == 999 and e["scenario"] == "resist"
    assert "no resistant defender" in e["error"]


@pytest.mark.req("REQ-AUDIT-0007")
def test_merge_unions_by_key_and_new_measurement_wins():
    old = _rec(damage={"dealtActive": 100, "dealtBench": [], "dealtSelf": 0,
                       "coinLogs": 0, "koed": False})
    new = _rec()
    other = _rec(scenario="vanilla", defender_id=20, defender_hp=310)
    merged = merge_records([old, other], [new])
    assert len(merged) == 2
    assert next(m for m in merged if m["scenario"] == "prevent_ex")["dealtActive"] == 210


@pytest.mark.req("REQ-AUDIT-0007")
def test_merge_never_clobbers_a_success_with_an_error():
    good = _rec()
    err = error_record(1488, 1031, "prevent_ex", "timeout")
    assert record_key(good) == record_key(err)
    merged = merge_records([good], [err])
    assert merged == [good]                                # measurement survives flaky re-run
    # error IS recorded when nothing better exists; success replaces it
    assert merge_records([], [err]) == [err]
    assert merge_records([err], [good]) == [good]


@pytest.mark.req("REQ-AUDIT-0007")
def test_merge_keys_distinguish_coin_and_sweep_variants():
    base = _rec()
    cmin = _rec(coin="min")
    cmax = _rec(coin="max")
    swept = _rec(sweep={"var": "energy", "step": 1})
    merged = merge_records([base], [cmin, cmax, swept])
    assert len(merged) == 4
