"""Parametric Effect Clauses — pure classifier + table + loader (ADR-0032 item 6).

Lib-free: synthetic probe records (shape mirrors cg/api.py ``Log``) -> clause dicts
``{kind, amount, restriction?, rider?}``. The magnitudes the boolean Function Tags
discard (heal amount, draw count) are kept here; tags stay boolean (ADR-0006).
"""
import json

import pytest

from meta_tracker.card_effects import (
    accumulate_effects, apply_overrides, build_effect_table, classify_effect_clauses,
    merge_clauses)


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
    """WP3: the 3 agents' draw-ENGINE abilities and Trainer/Supporter accel carry parametric clauses in
    the shipped `card_effects.json` (verified against engine ability/attack text) — so the mechanic lives
    in the representation, never a card-text parse. Pins the load-bearing amount/condition/rider per card."""
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
    # Crispin's FULL yield (issue #137 / ADR-0067): "up to 2 Basic Energy cards of different types …
    # put 1 of them into your hand. Attach the other." — `amount` is the ATTACH half, `to_hand` the
    # hand half the turn's one manual attach then plays, `distinct_types` the "different types" guard.
    # The Attach Budget needs both halves to see the 2-cost typed reach that dp f70 turned on.
    assert eff.clauses(1198)[0] == {"kind": "accel", "amount": 1, "source": "deck",
                                    "target": "any_pokemon", "energy": "basic",
                                    "to_hand": 1, "distinct_types": True}
    # The hand half rides the ACCEL clause and is still NOT a fetch clause — a Supporter is slot-dead
    # after a Supporter refresh, so the gamble energy-closure (which counts any `basic_energy` fetch
    # clause) must not treat it as an out.
    assert all(c["kind"] != "fetch" for c in eff.clauses(1198))


@pytest.mark.req("REQ-EFFECT-0004")
def test_shipped_supporter_trainer_coin_and_energy_provide_clauses():
    """WP3 tail: the 3 agents' Supporter/Trainer tutors, the coin denial, and Ignition's on-Evolution
    energy provision carry parametric clauses (verified against engine card text). The Supporter/Trainer
    fetch targets are OUTSIDE `_FETCH_POKEMON_TARGETS`, so the Pokémon-only `_search_deck_set` ignores
    them — they never disturb the whiff/redundancy signals; they are foundation for the Supporter-tutor
    closure branch. Ultra Ball's discard-2 cost rides its Pokémon fetch clause (still Pokémon-typed)."""
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
    # Bianca's Devotion: prior run shipped capped ungated measurement (heal 250);
    # accumulate keeps it (distinct key) — post-accumulate stamp must replace ALL
    # heal clauses w/ the gated text-verified one, other kinds surviving
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
    """Run the real override -> build -> `card_effects.json` path over a two-card pool.

    The builder is the thing under test, not a re-implementation of it: `covers` is a hand ruling
    that must survive the same accumulate/re-stamp machinery the clauses do, and the way a data field
    dies is by being added to the authored file and dropped somewhere in the pipe."""
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
    """The verdict is authored beside the clauses and must arrive in the shipped artifact intact —
    verdict AND reason, because a verdict nobody can re-check against the printed card is a bare
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
    # The authored `_note` rides along: it is what tells a reader of the shipped artifact where the
    # field is edited, and the numeric filter that keeps `_note` out of the card walk must not also
    # strip it from the file.
    assert shipped["_note"] == "fixture"
    # And an unruled card is UNKNOWN, not assumed complete.
    assert fx.covers(9999) is None


@pytest.mark.req("REQ-EFFECT-0018")
def test_a_partial_clause_set_fails_closed_at_the_seams_tri_state(tmp_path):
    """What the round-trip is *for*: `clauses_cover` is the argument `apply_option.fate` takes, and a
    partial set must answer `False` (refuse) rather than `True` (model three quarters of the card and
    price the rest at exactly 0)."""
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
    """`card_effects.json` is `{cardId: [clauses]}` plus one reserved key. The loader must skip it —
    treating the verdict block as a 59th card's clause list would be a silent corruption of the
    representation every fetch/heal/accel consumer reads."""
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
    """The artifact itself, not a fixture. Every card with clauses carries a verdict, and the two
    named holes Issue #300 was opened for are the ones asserted: Surfer's switch and Crushing
    Hammer's coin both declare PARTIAL rather than passing as complete."""
    from pathlib import Path
    from common.effects import CardEffects
    eff = CardEffects.load(Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json")
    assert eff.covers(1203) == "partial" and eff.clauses_cover(1203) is False   # Surfer
    assert eff.covers(1120) == "partial" and eff.clauses_cover(1120) is False   # Crushing Hammer
    assert eff.covers(1121) == "full" and eff.clauses_cover(1121) is True       # Ultra Ball
