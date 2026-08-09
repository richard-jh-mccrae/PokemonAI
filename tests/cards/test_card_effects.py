"""Parametric Effect Clauses — pure classifier + table + loader (ADR-0032 item 6).

Lib-free: synthetic probe records (shape mirrors cg/api.py ``Log``) -> clause dicts
``{kind, amount, restriction?, rider?}``. The magnitudes the boolean Function Tags
discard (heal amount, draw count) are kept here; tags stay boolean (ADR-0006).
"""
import json
import re

import pytest

from meta_tracker.card_effects import (
    _union_overrides, accumulate_effects, apply_overrides, build_effect_table,
    classify_effect_clauses, merge_clauses)

#: PLAYABILITY gated on paying a COST. Narrow on purpose: a bare `only if` would also catch BOARD
#: conditions, TURN restrictions and Naveen's *"can't DRAW"*, none of which is a payment.
_PRINTED_GATE = re.compile(r"only if you (?:discard|put)\b"
                           r"|if you can[’']t (?:discard|put) [^.]{0,60}from your hand", re.I)


def _printed_text(card: dict) -> str:
    """Every Ability line the engine prints for a card, joined — a Trainer's whole effect."""
    return "\n".join(a.get("text") or "" for a in card.get("abilities") or [])


def _rec(logs, actor=0, contexts=None):
    return {"actor": actor, "logs": logs, "contexts": contexts or []}


def _heal(value, player=0, counter=False):
    return {"type": 16, "playerIndex": player, "value": value, "putDamageCounter": counter}


def _draw(player=0):
    return {"type": 4, "playerIndex": player}


def _move(frm, to, player=0):
    return {"type": 6, "playerIndex": player, "fromArea": frm, "toArea": to}


# --- heal amount (REQ-EFFECT-0001) -------------------------------------------------

@pytest.mark.req("REQ-EFFECT-0001")
def test_heal_amount_is_measured_from_hp_change():
    # HP_CHANGE(16) value>0, actor's side, not a damage counter -> heal clause w/ magnitude
    out = classify_effect_clauses({"category": "item"}, probe=_rec([_heal(60)]))
    assert out == [{"kind": "heal", "amount": 60}]


@pytest.mark.req("REQ-EFFECT-0001")
def test_heal_amount_is_per_target_max_not_sum():
    # "heal 40 from each" logs one HP_CHANGE per target -> clause carries the
    # per-target magnitude (board-independent), not the board-dependent sum
    out = classify_effect_clauses({}, probe=_rec([_heal(40), _heal(40)]))
    assert out == [{"kind": "heal", "amount": 40}]
    # capped partial heal + a full one -> max observed wins
    out = classify_effect_clauses({}, probe=_rec([_heal(30), _heal(60)]))
    assert out == [{"kind": "heal", "amount": 60}]


@pytest.mark.req("REQ-EFFECT-0001")
def test_damage_and_counters_and_opponent_hp_are_not_heal():
    assert classify_effect_clauses({}, probe=_rec([_heal(-30)])) == []          # damage
    assert classify_effect_clauses({}, probe=_rec([_heal(30, counter=True)])) == []  # counter fx
    assert classify_effect_clauses({}, probe=_rec([_heal(30, player=1)])) == []      # opp's mon


# --- draw count (REQ-EFFECT-0002) ---------------------------------------------------

@pytest.mark.req("REQ-EFFECT-0002")
def test_draw_count_is_number_of_actor_draw_logs():
    # DRAW(4) logs one card each -> count the boolean `draw` tag discards
    out = classify_effect_clauses({}, probe=_rec([_draw(), _draw(), _draw()]))
    assert out == [{"kind": "draw", "amount": 3}]


@pytest.mark.req("REQ-EFFECT-0002")
def test_opponent_draws_are_not_my_draw_clause():
    assert classify_effect_clauses({}, probe=_rec([_draw(player=1)])) == []


# --- energy riders (REQ-EFFECT-0003) ------------------------------------------------

@pytest.mark.req("REQ-EFFECT-0003")
def test_heal_then_own_energy_to_hand_is_bounce_rider():
    # Wally's Compassion pattern: heal, then my Energy leaves in-play ENERGY(8)
    # area for my HAND(2) in same resolution
    out = classify_effect_clauses({}, probe=_rec([_heal(120), _move(8, 2)]))
    assert out == [{"kind": "heal", "amount": 120, "rider": "bounce_energy_to_hand"}]


@pytest.mark.req("REQ-EFFECT-0003")
def test_heal_then_own_energy_to_discard_is_discard_rider():
    # Super Potion pattern (verified in a real probe record): heal 60 then ENERGY(8)->DISCARD(3)
    out = classify_effect_clauses({}, probe=_rec([_heal(60), _move(8, 3)]))
    assert out == [{"kind": "heal", "amount": 60, "rider": "discard_own_energy"}]


@pytest.mark.req("REQ-EFFECT-0003")
def test_energy_move_without_or_before_a_heal_is_no_rider():
    # rider = "heal FOLLOWED BY the move" — cost paid before the heal, or a
    # move with no heal at all, isn't a heal rider
    assert classify_effect_clauses({}, probe=_rec([_move(8, 2)])) == []
    out = classify_effect_clauses({}, probe=_rec([_move(8, 3), _heal(60)]))
    assert out == [{"kind": "heal", "amount": 60}]


@pytest.mark.req("REQ-EFFECT-0003")
def test_opponent_energy_move_is_not_my_rider():
    # knocking opponent's Energy off (energy_denial territory) isn't my heal's rider
    out = classify_effect_clauses({}, probe=_rec([_heal(60), _move(8, 3, player=1)]))
    assert out == [{"kind": "heal", "amount": 60}]


# --- overrides union (REQ-EFFECT-0004) ----------------------------------------------

@pytest.mark.req("REQ-EFFECT-0004")
def test_override_replaces_measured_clauses_of_the_same_kind():
    # probe under-measures a capped heal; hand-verified override wins its kind,
    # measured clauses of other kinds survive
    probe = _rec([_heal(40), _draw(), _draw()])
    ovr = [{"kind": "heal", "amount": "all", "restriction": "mega_only",
            "rider": "bounce_energy_to_hand"}]
    out = classify_effect_clauses({}, probe=probe, overrides=ovr)
    assert {"kind": "draw", "amount": 2} in out
    heals = [c for c in out if c["kind"] == "heal"]
    assert heals == ovr


@pytest.mark.req("REQ-EFFECT-0004")
def test_multi_clause_override_of_one_kind_ships_whole():
    # Arven's Sandwich: heal 30 active-only + heal 100 if Arven's — both clauses ship
    ovr = [{"kind": "heal", "amount": 30, "restriction": "active_only"},
           {"kind": "heal", "amount": 100, "restriction": "arvens_pokemon"}]
    out = classify_effect_clauses({}, probe=_rec([_heal(30)]), overrides=ovr)
    assert out == sorted(ovr, key=lambda c: str(c))


@pytest.mark.req("REQ-EFFECT-0004")
def test_shipped_draw_engine_and_accel_clauses_are_in_the_representation():
    """The mechanic lives in the representation, never a card-text parse."""
    from pathlib import Path
    from common.effects import CardEffects
    eff = CardEffects.load(Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json")
    # Draw engines (abilities): amount + the gating condition / self-effect rider.
    assert eff.clauses(66) == ({"kind": "draw", "amount": 3, "condition": "once_per_turn_ability",
                                "rider": "shuffle_self_in"},)                       # Dudunsparce
    assert eff.clauses(120)[0] == {"kind": "draw", "amount": 1, "window": 2,        # Drakloak: look 2, take 1
                                   "condition": "once_per_turn_ability", "rider": "other_to_bottom"}
    assert eff.clauses(140)[0]["condition"] == "pokemon_ko_last_turn"               # Fezandipiti ex
    assert eff.clauses(675)[0] == {"kind": "draw", "amount": 3, "condition": "solrock_in_play",
                                   "rider": "discard_basic_f_energy"}               # Lunatone
    assert eff.clauses(1080)[0]["amount"] == 5 and eff.clauses(1080)[0]["condition"] == "pokemon_ko_last_turn"
    # Trainer / Supporter accel: Rosa's discard→Stage-2 (prize-behind gate); Crispin's deck→attach.
    assert eff.clauses(1240)[0] == {"kind": "accel", "amount": 2, "source": "discard", "target": "stage2",
                                    "energy": "basic", "condition": "more_prizes_remaining_than_opp"}
    # Crispin (ADR-0067): `amount` is the ATTACH half, `to_hand` the hand half the turn's one manual
    # attach then plays, `distinct_types` the "different types" guard. The Budget needs both halves.
    assert eff.clauses(1198)[0] == {"kind": "accel", "amount": 1, "source": "deck",
                                    "target": "any_pokemon", "energy": "basic",
                                    "to_hand": 1, "distinct_types": True}
    # The hand half rides the ACCEL clause and is NOT a fetch clause: a Supporter is slot-dead after
    # a Supporter refresh, so the gamble energy-closure must not count it as an out.
    assert all(c["kind"] != "fetch" for c in eff.clauses(1198))


@pytest.mark.req("REQ-EFFECT-0004")
def test_shipped_supporter_trainer_coin_and_energy_provide_clauses():
    """The Supporter/Trainer fetch targets are OUTSIDE `_FETCH_POKEMON_TARGETS`, so the Pokémon-only
    `_search_deck_set` ignores them and they never disturb the whiff/redundancy signals."""
    from pathlib import Path
    from common.effects import CardEffects
    eff = CardEffects.load(Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json")
    assert eff.clauses(1219) == ({"kind": "fetch", "target": "trainer", "zone": "deck"},)   # Petrel
    assert eff.clauses(1122)[0] == {"kind": "fetch", "target": "supporter", "zone": "deck", "dig": 7}
    assert eff.clauses(1071)[0] == {"kind": "fetch", "target": "supporter", "zone": "deck",
                                    "trigger": "on_bench_play"}                              # Meowth ex
    assert eff.clauses(1120) == ({"kind": "coin", "effect": "discard_opp_energy", "amount": 1},)
    assert eff.clauses(17)[0] == {"kind": "energy_provide", "amount": 1, "amount_on_evolution": 3,
                                  "type": "colorless", "rider": "discard_eot"}               # Ignition
    ultra = eff.clauses(1121)[0]                                                             # Ultra Ball
    assert ultra["target"] == "pokemon" and ultra["cost"] == "discard_2"


@pytest.mark.req("REQ-EFFECT-0004")
def test_shipped_gust_clauses_carry_the_target_the_trigger_and_the_riders():
    """Issue #303. `trigger: on_evolve` routes a clause onto the `_EVOLVE` site the engine poses;
    a coin-gated gust composes as a `coin` clause whose `effect` NAMES the gust."""
    from pathlib import Path
    from common.effects import CardEffects
    eff = CardEffects.load(Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json")
    assert eff.clauses(1182) == ({"kind": "gust", "target": "any"},)             # Boss's Orders
    assert eff.clauses(674) == ({"kind": "gust", "target": "any", "trigger": "on_evolve",
                                 "condition": "once_per_turn_ability"},)         # Hariyama
    assert eff.clauses(310) == ({"kind": "gust", "target": "any",
                                 "trigger": "on_evolve"},)                       # Hop's Dubwool
    assert eff.clauses(1088) == ({"kind": "gust", "target": "any",
                                  "rider": "self_switch"},)                      # Prime Catcher
    assert eff.clauses(1204) == ({"kind": "gust", "target": "basic",
                                  "rider": "confuse_target"},)                   # Lisia's Appeal
    assert eff.clauses(1218) == ({"kind": "gust", "target": "any", "rider": "self_switch",
                                  "name_family": "Team Rocket's"},)              # TR Giovanni
    assert eff.clauses(1124) == ({"kind": "coin", "effect": "gust",
                                  "target": "any"},)                             # Pokemon Catcher
    # The two that do not carry the whole card are RULED incomplete rather than left unruled: the
    # undecided `Team Rocket's` name family, and the coin stating a 50/50 as a certainty.
    assert [eff.covers(c) for c in (1182, 674, 310, 1088, 1204)] == ["full"] * 5
    assert eff.covers(1218) == "partial" and eff.clauses_cover(1218) is False
    assert eff.covers(1124) == "partial" and eff.clauses_cover(1124) is False


@pytest.mark.req("REQ-EFFECT-0004")
def test_shipped_stadium_clauses_carry_the_effect_the_magnitude_and_the_body_predicate():
    """Issue #304. `amount` is SIGNED, `symmetric` is on all six, `timing` carries the W/R ORDER,
    and `on:` is the trigger EVENT — `trigger:` would file the clause on a SITE Stadiums never pose."""
    from pathlib import Path
    from common.effects import CardEffects
    eff = CardEffects.load(Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json")
    assert eff.clauses(1252) == ({"kind": "stadium_static", "effect": "hp_delta", "amount": -30,
                                  "applies_to": "stage2", "symmetric": True},)   # Gravity Mountain
    assert eff.clauses(1251) == ({"kind": "stadium_static", "effect": "hp_delta", "amount": 30,
                                  "applies_to": "basic", "symmetric": True},)    # Lively Stadium
    assert eff.clauses(1244) == ({"kind": "stadium_static", "effect": "damage_reduction",
                                  "amount": 30, "applies_to": "metal",
                                  "source": "opponent_attack",
                                  "timing": "after_weakness_resistance",
                                  "symmetric": True},)                           # Full Metal Lab
    assert eff.clauses(1255) == ({"kind": "stadium_static", "effect": "damage_boost", "amount": 30,
                                  "applies_to": "name_family", "name_family": "Hop's",
                                  "target": "opponent_active",
                                  "timing": "before_weakness_resistance",
                                  "symmetric": True},)                           # Postwick
    assert eff.clauses(1247) == ({"kind": "stadium_static", "effect": "prevent_damage",
                                  "applies_to": "no_rule_box", "source": "opponent_attack",
                                  "source_class": "ex_or_v",
                                  "symmetric": True},)                        # Neutralization Zone
    assert eff.clauses(1260) == ({"kind": "stadium_trigger", "on": "bench_play",
                                  "effect": "damage_counters", "amount": 2,
                                  "applies_to": "basic_non_dark", "symmetric": True},)  # Risky Ruins
    # All six carry their whole printed card; the two predicates that could have been ruled `partial`
    # each defer to a verdict already shipped for the SAME predicate rather than being decided here.
    assert [eff.covers(c) for c in (1244, 1247, 1251, 1252, 1255, 1260)] == ["full"] * 6
    assert all(eff.clauses_cover(c) is True for c in (1244, 1247, 1251, 1252, 1255, 1260))


@pytest.mark.req("REQ-EFFECT-0004")
def test_the_conditional_draw_supporters_state_the_card_and_not_the_probe_s_best_case():
    """Issue #302. A probe measures ONE resolution, which cannot state a card whose count depends on
    the board: `to_hand_size` excludes `amount`, `amount_if` REPLACES it, `cost_required` gates it."""
    from pathlib import Path
    from common.effects import CardEffects
    eff = CardEffects.load(Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json")
    # (1) the conditional second tier — the base, then the magnitude that replaces it
    assert eff.clauses(1227) == ({"kind": "draw", "amount": 6,                # Lillie's Determination
                                  "amount_if": {"condition": "exactly_6_prizes_remaining",
                                                "amount": 8},
                                  "rider": "shuffle_own_hand_in"},)
    assert eff.clauses(1199) == ({"kind": "draw", "amount": 4,                             # Lacey
                                  "amount_if": {"condition": "opp_3_or_fewer_prizes", "amount": 8},
                                  "rider": "shuffle_own_hand_in"},)
    assert eff.clauses(1181) == ({"kind": "draw", "amount": 2,                    # Billy & O'Nare
                                  "amount_if": {"condition": "hand_size_10_plus_after_draw",
                                                "amount": 4}},)
    # (2) refill-to-N, never draw-N — and `amount` is absent, not merely different
    assert eff.clauses(1239) == ({"kind": "draw", "to_hand_size": 5},)                     # Naveen
    assert eff.clauses(1216) == ({"kind": "draw", "to_hand_size": 5,           # TR Ariana, 5 or 8
                                  "amount_if": {"condition": "all_own_pokemon_team_rocket",
                                                "to_hand_size": 8}},)
    assert eff.clauses(1203) == ({"kind": "draw", "to_hand_size": 5,                       # Surfer
                                  "rider": "self_switch"},)
    for refill in (1203, 1208, 1216, 1239):
        assert "amount" not in eff.clauses(refill)[0], refill
    # (3) a cost that GATES playability, and one that merely charges for it
    assert eff.clauses(1208) == ({"kind": "draw", "to_hand_size": 6,           # Iris's Fighting Spirit
                                  "cost": "discard_1", "cost_required": True},)
    assert eff.clauses(1200) == ({"kind": "draw", "amount": 4,                             # Kofu
                                  "cost": "bottom_2", "cost_required": True},)
    assert eff.clauses(1192) == ({"kind": "draw", "amount": 5, "cost": "discard_hand"},)   # Carmine
    # 1121 Ultra Ball is a GATE too (Issue #372): it prints the same restriction 1208 does, and was
    # missed only because it is a `fetch` while that issue's 14 were all `draw`.
    assert eff.clauses(1121) == ({"kind": "fetch", "target": "pokemon", "zone": "deck",
                                  "cost": "discard_2", "cost_required": True},)     # Ultra Ball
    # "one card per opponent BENCHED Pokemon" is a board-scaled count: `amount: 1` multiplied by the
    # count `amount_per` names, never the flat 3 the probe measured (a number the card never prints).
    assert eff.clauses(1187) == ({"kind": "draw", "amount": 1, "amount_per": "their_bench",
                                  "cost": "discard_1", "cost_required": True},)
    # The coin pair — `kind: "draw"`, so the override replaces the measured draw rather than
    # doubling it, with the heads leg as the base and the tails leg as the replacement.
    assert eff.clauses(1223) == ({"kind": "draw", "amount": 5,                          # Harlequin
                                  "amount_if": {"condition": "coin_tails", "amount": 3},
                                  "opponent_amount": 3,
                                  "opponent_amount_if": {"condition": "coin_tails", "amount": 5},
                                  "rider": "shuffle_both_hands"},)
    assert eff.clauses(1237) == ({"kind": "draw", "amount": 6,                             # Lucian
                                  "amount_if": {"condition": "coin_tails", "amount": 3},
                                  "rider": "both_hands_to_bottom"},)
    assert all(c["kind"] == "draw" and len(eff.clauses(cid)) == 1
               for cid in (1223, 1237) for c in eff.clauses(cid))
    # Judge gains the rider its own count never needed; Unfair Stamp is UNCHANGED — its own leg was
    # already exact, which is why it is in the issue's 14 for the opponent leg alone.
    assert eff.clauses(1213) == ({"kind": "draw", "amount": 4,                              # Judge
                                  "opponent_amount": 4, "rider": "shuffle_both_hands"},)
    assert eff.clauses(1080) == ({"kind": "draw", "amount": 5,                     # Unfair Stamp
                                  "condition": "pokemon_ko_last_turn",
                                  "opponent_amount": 2,
                                  "rider": "shuffle_both_hands"},)
    assert [eff.covers(c) for c in (1181, 1187, 1192, 1199, 1200, 1203, 1208, 1213, 1216, 1223,
                                    1227)] == ["full"] * 11
    assert eff.covers(1080) == "full" and eff.clauses_cover(1080) is True
    for still_partial in (1237, 1239):
        assert eff.covers(still_partial) == "partial", still_partial
        assert eff.clauses_cover(still_partial) is False, still_partial
    # Two cards OUTSIDE the issue's 14 move with them, because one store cannot hold two verdicts for
    # one shape: 1214 is 1199's predicate exactly, and 1206 prints 1192's *"Discard your hand"*.
    assert eff.clauses(1214) == ({"kind": "draw", "amount": 2,
                                  "amount_if": {"condition": "opp_3_or_fewer_prizes", "amount": 4}},)
    assert [c["cost"] for c in eff.clauses(1206)] == ["discard_hand"] * 3
    assert [eff.covers(c) for c in (1206, 1214)] == ["full", "full"]
    assert [c["cost"] for c in eff.clauses(1092)] == ["discard_3"] * 4               # the precedent


@pytest.mark.parametrize("clause", [
    {"kind": "draw", "amount": 4, "opponent_amount": 0},
    {"kind": "draw", "amount": 4, "opponent_amount": 4, "opponent_amount_if": []},
    {"kind": "draw", "amount": 4, "opponent_amount": 4,
     "opponent_amount_if": {"condition": "coin_tails", "amount": 0}},
    {"kind": "draw", "amount": 4,
     "amount_if": {"condition": "coin_tails", "amount": 3},
     "opponent_amount_if": {"condition": "coin_tails", "amount": 5}},
    {"kind": "draw", "amount": 4, "opponent_amount": 4,
     "opponent_amount_if": {"condition": "coin_tails", "amount": 5}},
    {"kind": "draw", "amount": 4,
     "amount_if": {"condition": "coin_heads", "amount": 3}, "opponent_amount": 4,
     "opponent_amount_if": {"condition": "coin_tails", "amount": 5}},
])
def test_builder_rejects_malformed_opponent_draw_fields(clause):
    from common.snapshot_coverage import opponent_draw_problems
    payload = {"_covers": {"9999": {"covers": "full", "reason": "fixture"}},
               "9999": [clause]}
    assert opponent_draw_problems(payload)


def test_effect_builder_refuses_to_write_malformed_opponent_draw_fields(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({
        "9999": [{"kind": "draw", "amount": 4, "opponent_amount": 0}],
        "_covers": {"9999": {"covers": "full", "reason": "fixture"}},
    }), encoding="utf-8")
    out = tmp_path / "effects.json"
    result = subprocess.run([
        sys.executable, str(Path(__file__).resolve().parents[2] / "tools" / "build_card_effects.py"),
        "--limit", "0", "--fresh", "--overrides", str(overrides), "--out", str(out),
    ], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode != 0
    assert "opponent_amount must be a positive integer" in result.stdout
    assert not out.exists()


@pytest.mark.req("REQ-EFFECT-0004")
def test_cost_required_agrees_with_the_printed_gate_on_every_cost_bearing_card():
    """Issue #372: a `cost` carries `cost_required` IF AND ONLY IF the card prints a restriction on
    PAYING THAT COST — not on playability, which is wider and would catch ten BOARD conditions."""
    from pathlib import Path
    from common.effects import CardEffects
    from meta_tracker.cards import load_cards
    cards = load_cards()
    eff = CardEffects.load(Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json")

    # (0) CONTROLS, before any conclusion is drawn from a silence: the instrument must FIRE on both
    #     printed phrasings and stay QUIET on every near-miss the pool actually contains.
    assert _PRINTED_GATE.search(_printed_text(cards[1187]))          # "only if you discard another…"
    assert _PRINTED_GATE.search(_printed_text(cards[1200]))          # "If you can’t put 2 cards…"
    for ungated in (1192,   # Carmine — "Discard your hand and draw 5 cards.", an instruction
                    1206,   # Larry's Skill — "Discard your hand and search your deck…", ditto
                    1079,   # Rare Candy — "You can’t use this card during your first turn."
                    1230,   # Grimsley's Move — the same turn restriction
                    1239,   # Naveen — "(If you can’t DRAW any cards in this way…)"; discard is "may"
                    1101,   # Call Bell — "only if you go second", a BOARD condition
                    1201):  # Briar — "only if your opponent has exactly 2 Prize cards remaining"
        assert not _PRINTED_GATE.search(_printed_text(cards[ungated])), ungated
    # …and the instrument is not merely quiet on those: it finds exactly the seven real cost gates.
    assert {cid for cid in cards if _PRINTED_GATE.search(_printed_text(cards[cid]))} == \
        {1092, 1121, 1148, 1187, 1200, 1208, 1233}

    costed = {cid: eff.clauses(cid) for cid in sorted(cards)
              if any("cost" in c for c in eff.clauses(cid))}
    # The domain is non-empty and is the whole cost axis — an iteration that silently shrank to zero
    # would satisfy every assertion below without measuring anything.
    assert set(costed) == {1092, 1121, 1187, 1192, 1200, 1206, 1208, 1233}, sorted(costed)

    # (1) THE INVARIANT, both directions.
    for cid, clauses in costed.items():
        gated = bool(_PRINTED_GATE.search(_printed_text(cards[cid])))
        for clause in clauses:
            if "cost" not in clause:
                continue
            assert clause.get("cost_required", False) is gated, (
                f"card {cid} {cards[cid]['name']}: printed gate={gated}, "
                f"cost_required={clause.get('cost_required')!r}")

    # (2) One card, one reading — a multi-leg find must not gate some legs and price the others.
    #     Repeating the cost on every leg is the shipped shape for one cost paid once.
    for cid, clauses in costed.items():
        readings = {c.get("cost_required", False) for c in clauses if "cost" in c}
        assert len(readings) == 1, f"card {cid} reads its own cost two ways: {readings}"
    assert [c.get("cost_required") for c in eff.clauses(1092)] == [True] * 4
    assert [c.get("cost_required") for c in eff.clauses(1206)] == [None] * 3

    # (3) The five cards printing the SAME sentence end up with ONE reading — the issue's headline,
    #     asserted on the sentence itself rather than on the ids, so a sixth printing joins it free.
    same_sentence = {cid for cid in cards
                     if "only if you discard" in _printed_text(cards[cid]).lower()}
    assert same_sentence == {1092, 1121, 1148, 1187, 1208, 1233}, sorted(same_sentence)
    assert all(c["cost_required"] is True
               for cid in same_sentence - {1148} for c in eff.clauses(cid))

    # (4) 1148 Blowtorch is the DEFERRAL as a tripwire: it prints the gate but has no compendium
    #     entry, because no `cost` value expresses a TYPED single-card discard.
    assert _PRINTED_GATE.search(_printed_text(cards[1148]))
    assert eff.clauses(1148) == ()


@pytest.mark.req("REQ-EFFECT-0004")
def test_a_coin_kinded_override_would_leave_the_measured_draw_clause_standing():
    """`_union_overrides` keeps every measured clause whose `kind` is not among the override's, so a
    `coin`-kinded override would ship BOTH and claim the card draws twice."""
    measured = [{"kind": "draw", "amount": 5}]
    as_coin = _union_overrides(measured, [{"kind": "coin", "effect": "draw", "amount": 5}])
    assert len(as_coin) == 2 and {c["kind"] for c in as_coin} == {"coin", "draw"}
    as_draw = _union_overrides(measured, [{"kind": "draw", "amount": 5,
                                           "amount_if": {"condition": "coin_tails", "amount": 3}}])
    assert as_draw == [{"kind": "draw", "amount": 5,
                        "amount_if": {"condition": "coin_tails", "amount": 3}}]


@pytest.mark.req("REQ-EFFECT-0004")
def test_override_only_card_needs_no_probe():
    ovr = [{"kind": "heal", "amount": 150}]
    assert classify_effect_clauses({}, overrides=ovr) == ovr


# --- condition gates (REQ-EFFECT-0011) -----------------------------------------------

@pytest.mark.req("REQ-EFFECT-0011")
def test_override_condition_passes_through_the_union():
    # Jumbo Ice Cream: probe measures the 80 but not the 3+-Energy gate; override
    # carries the gate, replaces ungated measured clause — condition verbatim
    ovr = [{"kind": "heal", "amount": 80, "restriction": "active_only",
            "condition": "energy_3_plus"}]
    out = classify_effect_clauses({}, probe=_rec([_heal(80), _draw()]), overrides=ovr)
    assert {"kind": "draw", "amount": 1} in out
    assert [c for c in out if c["kind"] == "heal"] == ovr


@pytest.mark.req("REQ-EFFECT-0011")
def test_merge_keeps_distinct_condition_variants_separate():
    # clauses differing only in condition are different clauses (like restriction
    # variants) — merge must not collapse a gated heal into an ungated one
    a = [{"kind": "heal", "amount": 10, "condition": "played_supporter_this_turn"}]
    b = [{"kind": "heal", "amount": 40}]
    assert merge_clauses(a, b) == sorted(a + b, key=lambda c: str(c))


# --- override union survives accumulation (REQ-EFFECT-0012) ---------------------------

@pytest.mark.req("REQ-EFFECT-0012")
def test_apply_overrides_stamps_kind_over_an_accumulated_table():
    # Bianca's Devotion: accumulate keeps the prior capped ungated heal (distinct key), so the
    # post-accumulate stamp must replace ALL heal clauses, with other kinds surviving.
    table = {1190: [{"kind": "heal", "amount": 250},
                    {"kind": "heal", "amount": "all",
                     "condition": "remaining_hp_30_or_less"},
                    {"kind": "draw", "amount": 2}]}
    ovr = {1190: [{"kind": "heal", "amount": "all",
                   "condition": "remaining_hp_30_or_less"}]}
    out = apply_overrides(table, ovr)
    assert out[1190] == sorted(ovr[1190] + [{"kind": "draw", "amount": 2}],
                               key=lambda c: str(c))


@pytest.mark.req("REQ-EFFECT-0012")
def test_apply_overrides_adds_override_only_cards_and_leaves_others_alone():
    table = {1117: [{"kind": "heal", "amount": 30}]}
    ovr = {1242: [{"kind": "heal", "amount": 10,
                   "condition": "played_supporter_this_turn"}]}
    out = apply_overrides(table, ovr)
    assert out[1117] == [{"kind": "heal", "amount": 30}]      # untouched
    assert out[1242] == ovr[1242]                              # probe-unreachable card ships


# --- graceful degradation (REQ-EFFECT-0005) -----------------------------------------

@pytest.mark.req("REQ-EFFECT-0005")
def test_sparse_or_absent_probe_degrades_to_empty():
    assert classify_effect_clauses({}) == []
    assert classify_effect_clauses({}, probe=None) == []
    assert classify_effect_clauses({}, probe={}) == []
    assert classify_effect_clauses({}, probe=_rec([])) == []
    assert classify_effect_clauses({}, probe={"logs": [{}]}) == []      # no actor, empty log
    assert classify_effect_clauses({}, probe=_rec([{"type": 16}])) == []  # HP_CHANGE, no value


# --- per-record merge + table build (REQ-EFFECT-0006) --------------------------------

@pytest.mark.req("REQ-EFFECT-0006")
def test_merge_clauses_takes_max_amount_per_kind():
    a = [{"kind": "heal", "amount": 30}]           # a capped pass
    b = [{"kind": "heal", "amount": 60}]           # a fully-damaged pass
    assert merge_clauses(a, b) == [{"kind": "heal", "amount": 60}]


@pytest.mark.req("REQ-EFFECT-0006")
def test_build_table_classifies_each_record_separately():
    # records must NOT be concatenated: heal in pass A + unrelated energy move in
    # pass B must not fabricate a rider; two 3-card draws must not sum to 6
    cards = {7: {"category": "supporter"}}
    recs = {7: [_rec([_heal(60)]), _rec([_move(8, 3)]),
                _rec([_draw(), _draw(), _draw()]), _rec([_draw(), _draw(), _draw()])]}
    table = build_effect_table(cards, recs)
    assert table[7] == [{"kind": "draw", "amount": 3}, {"kind": "heal", "amount": 60}]


@pytest.mark.req("REQ-EFFECT-0006")
def test_build_table_omits_clauseless_cards_and_applies_overrides():
    cards = {1: {"category": "item"}, 2: {"category": "item"}}
    table = build_effect_table(cards, {}, overrides={1: [{"kind": "heal", "amount": 150}]})
    assert table == {1: [{"kind": "heal", "amount": 150}]}   # 2 has no clauses -> omitted


# --- cross-run accumulation (REQ-EFFECT-0007) ----------------------------------------

@pytest.mark.req("REQ-EFFECT-0007")
def test_accumulate_is_monotonic_max_merge():
    new = {1: [{"kind": "heal", "amount": 60}]}
    prior = {1: [{"kind": "heal", "amount": 30}, {"kind": "draw", "amount": 2}],
             2: [{"kind": "draw", "amount": 3}]}
    acc = accumulate_effects(new, prior)
    assert acc[1] == [{"kind": "draw", "amount": 2}, {"kind": "heal", "amount": 60}]
    assert acc[2] == [{"kind": "draw", "amount": 3}]     # prior-only card never dropped


@pytest.mark.req("REQ-EFFECT-0007")
def test_accumulate_all_amount_beats_any_int():
    new = {1: [{"kind": "heal", "amount": 90}]}
    prior = {1: [{"kind": "heal", "amount": "all"}]}
    assert accumulate_effects(new, prior)[1] == [{"kind": "heal", "amount": "all"}]


@pytest.mark.req("REQ-EFFECT-0007")
def test_accumulate_keeps_distinct_restriction_or_rider_variants():
    # override-authored clause variants (distinct restriction) never collapse
    prior = {1: [{"kind": "heal", "amount": 30, "restriction": "active_only"},
                 {"kind": "heal", "amount": 100, "restriction": "arvens_pokemon"}]}
    acc = accumulate_effects({}, prior)
    assert acc == {1: sorted(prior[1], key=lambda c: str(c))}


# --- runtime loader (REQ-EFFECT-0008) -----------------------------------------------

@pytest.mark.req("REQ-EFFECT-0008")
def test_loader_reads_table_and_defaults_missing_cards_to_empty(tmp_path):
    from common.effects import CardEffects
    p = tmp_path / "card_effects.json"
    p.write_text(json.dumps({"1112": [{"kind": "heal", "amount": 60,
                                       "rider": "discard_own_energy"}]}), encoding="utf-8")
    fx = CardEffects.load(p)
    assert fx.clauses(1112) == ({"kind": "heal", "amount": 60, "rider": "discard_own_energy"},)
    assert fx.clauses(9999) == ()


@pytest.mark.req("REQ-EFFECT-0008")
def test_loader_fails_safe_to_empty_when_file_absent(tmp_path):
    from common.effects import CardEffects
    fx = CardEffects.load(tmp_path / "nope.json")
    assert fx.clauses(1112) == ()


# --- clause-set completeness: `_covers` (REQ-EFFECT-0018, Issue #300) ----------------

def _covers_round_trip(tmp_path, overrides: dict):
    """Run the REAL override -> build -> `card_effects.json` path over a two-card pool: the builder
    is the thing under test, not a re-implementation of it."""
    import importlib.util
    from pathlib import Path
    ovr = tmp_path / "effect_overrides.json"
    ovr.write_bytes(json.dumps(overrides).encode("utf-8"))
    out = tmp_path / "card_effects.json"
    spec = importlib.util.spec_from_file_location(
        "build_card_effects", Path(__file__).resolve().parents[2] / "tools" / "build_card_effects.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    table = mod.apply_overrides({}, mod._load_overrides(ovr))
    payload = {"_covers": mod._load_covers(ovr)}
    payload.update({str(cid): cls for cid, cls in sorted(table.items())})
    out.write_bytes(json.dumps(payload).encode("utf-8"))
    return out


@pytest.mark.req("REQ-EFFECT-0018")
def test_covers_survives_the_override_to_build_to_compendium_round_trip(tmp_path):
    """Verdict AND reason: a verdict nobody can re-check against the printed card is a bare
    assertion."""
    from common.effects import CardEffects
    out = _covers_round_trip(tmp_path, {
        "_note": "fixture",
        "1112": [{"kind": "heal", "amount": 60, "rider": "discard_own_energy"}],
        "1203": [{"kind": "draw", "amount": 1}],
        "_covers": {
            "_note": "fixture",
            "1112": {"covers": "full", "reason": "heal 60 + the discard rider"},
            "1203": {"covers": "partial", "reason": "the card SWITCHES the Active first"},
        },
    })
    fx = CardEffects.load(out)
    shipped = json.loads(out.read_text(encoding="utf-8"))["_covers"]
    assert fx.covers(1112) == "full" and fx.covers(1203) == "partial"
    assert "SWITCHES" in shipped["1203"]["reason"]
    # The numeric filter that keeps the authored `_note` out of the card walk must not also strip
    # it from the file.
    assert shipped["_note"] == "fixture"
    # And an unruled card is UNKNOWN, not assumed complete.
    assert fx.covers(9999) is None


@pytest.mark.req("REQ-EFFECT-0018")
def test_a_partial_clause_set_fails_closed_at_the_seams_tri_state(tmp_path):
    """`clauses_cover` is the argument `apply_option.fate` takes: a partial set must REFUSE rather
    than model three quarters of the card and price the rest at exactly 0."""
    from common.effects import CardEffects
    fx = CardEffects.load(_covers_round_trip(tmp_path, {
        "1112": [{"kind": "heal", "amount": 60}],
        "1203": [{"kind": "draw", "amount": 1}],
        "_covers": {"1112": {"covers": "full", "reason": "r"},
                    "1203": {"covers": "partial", "reason": "r"}},
    }))
    assert fx.clauses_cover(1112) is True
    assert fx.clauses_cover(1203) is False
    assert fx.clauses_cover(9999) is None


@pytest.mark.req("REQ-EFFECT-0018")
def test_the_covers_block_is_not_mistaken_for_a_cards_clauses(tmp_path):
    """`card_effects.json` is `{cardId: [clauses]}` plus one reserved key the loader must skip."""
    from common.effects import CardEffects
    out = _covers_round_trip(tmp_path, {
        "1112": [{"kind": "heal", "amount": 60}],
        "_covers": {"1112": {"covers": "full", "reason": "r"}},
    })
    fx = CardEffects.load(out)
    assert fx.clauses(1112) == ({"kind": "heal", "amount": 60},)
    assert "_covers" in json.loads(out.read_text(encoding="utf-8"))
    assert fx.clauses(0) == ()


@pytest.mark.req("REQ-EFFECT-0018")
def test_the_shipped_compendium_rules_every_clause_bearing_card(tmp_path):
    """The artifact itself, not a fixture: every card with clauses carries a verdict."""
    from pathlib import Path
    from common.effects import CardEffects
    eff = CardEffects.load(Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json")
    for closed_form in (1120, 1213, 1223):
        assert eff.covers(closed_form) == "full" and eff.clauses_cover(closed_form) is True
    assert eff.covers(1121) == "full" and eff.clauses_cover(1121) is True       # Ultra Ball
    assert eff.covers(1203) == "full" and eff.clauses_cover(1203) is True       # Surfer, Issue #302


# ── the RELATION, cross-checked against the engine's own ops ───────────────────────────────────────


@pytest.mark.req("REQ-CARDS-0001")
def test_every_multi_leg_relation_agrees_with_the_engine_chain_op():
    """A cross-STORE check: the engine settles the three multi-leg shapes with three STRUCTURALLY
    different ops, so the compendium's `choice` flags are checkable against the chain store."""
    from pathlib import Path
    from common.effects import CardEffects
    from common.fetch_closure import reveal_legs
    from common.snapshot_coverage import REVEALING_CLAUSES

    root = Path(__file__).resolve().parents[2]
    eff = CardEffects.load(root / "src" / "common" / "card_effects.json")
    payload = json.loads((root / "src" / "common" / "card_effects.json").read_text(encoding="utf-8"))
    chains = json.loads((root / "src" / "cgpy" / "defs" / "chain_overrides.json")
                        .read_text(encoding="utf-8"))

    #: The engine op that settles each relation. `xPickDiscard` carries its union in an `anyOf`
    #: filter exactly as `effectDeckToHandAndShuffle` does, so both read off the FILTER not the op.
    _CONJUNCTION_OPS = {"xDeckToHandBuckets", "xDeckTakeSequenceAndShuffle"}
    _EITHER_OR_OPS = {"xDeckToHandEitherOr"}

    def declared_relation(clauses):
        """Deliberately not `reveal_legs`: that layers this node's SCOPE refusals on top of the
        relation, and a scope limit is not a disagreement about what the card does."""
        legs = [c for c in clauses if c.get("kind") in REVEALING_CLAUSES]
        flags = [bool(c.get("choice")) for c in legs]
        if not any(flags):
            return "conjunction"
        caps = {c.get("amount", 1) for c in legs}
        return "union" if len(caps) == 1 else "either-or"

    def engine_relation(entry):
        """The relation the engine's own `play` chain implies, or None when it says nothing."""
        for op in entry.get("play") or ():
            name = op.get("op")
            if name in _CONJUNCTION_OPS:
                return "conjunction"
            if name in _EITHER_OR_OPS:
                return "either-or"
            filt = op.get("filter") or {}
            if "anyOf" in filt or filt.get("pokemonOrBasicEnergy"):
                return "union"
        return None

    checked, skipped = [], []
    for key, clauses in payload.items():
        if not str(key).lstrip("-").isdigit() or not isinstance(clauses, list):
            continue
        cid = int(key)
        if len([c for c in clauses if c.get("kind") in REVEALING_CLAUSES]) < 2:
            continue
        entry = chains.get(str(cid))
        expected = engine_relation(entry) if entry else None
        if expected is None:
            skipped.append(cid)
            continue
        assert declared_relation(clauses) == expected, (
            f"card {cid}: the compendium DECLARES {declared_relation(clauses)!r} and the engine "
            f"chain implies {expected!r}")
        # A seam refusal for a DIFFERENT reason (a reach-gated leg is a scope limit, not a
        # relation) is not a disagreement, so it is skipped rather than counted as one.
        try:
            assert reveal_legs(eff.clauses(cid)).relation == expected, cid
        except ValueError as gap:
            assert "either-or" in str(gap) or "reach-gated" in str(gap), (cid, str(gap))
        checked.append(cid)

    # The vacuity guard and the named skips — a green cross-store check means nothing if it compared
    # nothing, and a silent skip list is how a card slips out of an audit it used to be in.
    assert len(checked) >= 6, f"only {len(checked)} cards cross-checked: {sorted(checked)}"
    assert 1097 in checked and 1142 in checked, "the two cards this audit exists for must be checked"
    assert sorted(skipped) == [1094, 1110, 1215, 1238], (
        f"the no-override skip list moved: {sorted(skipped)} — add the entry or rule the skip")


@pytest.mark.req("REQ-CARDS-0001")
def test_the_cross_store_relation_audit_BITES_when_the_compendium_is_reverted():
    """The positive control the criterion names explicitly: reverting 1097's `choice` must turn the
    check above red. Asserted on an in-memory revert rather than by editing the store."""
    from pathlib import Path
    from common.effects import CardEffects
    from common.fetch_closure import reveal_legs

    root = Path(__file__).resolve().parents[2]
    shipped = CardEffects.load(root / "src" / "common" / "card_effects.json").clauses(1097)
    assert reveal_legs(shipped).relation == "union"          # as shipped, agreeing with the engine
    reverted = [{k: v for k, v in c.items() if k != "choice"} for c in shipped]
    assert reveal_legs(reverted).relation == "conjunction"   # the pre-fix reading the engine refutes
