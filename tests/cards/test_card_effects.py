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

#: The printed sentence that makes a `cost` a PLAYABILITY GATE rather than a price, in the two forms
#: the pool prints it. Quoted from the engine dump `tools/meta_tracker/cards.json`
#: (`all_card_data()`), never recalled:
#:
#: * *"You can use this card only if you discard 2 other cards from your hand."* — 1121 Ultra Ball
#: * *"…(If you can't put 2 cards from your hand on the bottom of your deck, you can't use this
#:   card.)"* — 1200 Kofu, which states the same restriction the other way round
#:
#: The apostrophe is U+2019 in the dump, not the ASCII one it is tempting to type, so the pattern
#: accepts both — a detail worth spelling out because getting it wrong yields an instrument that
#: matches NOTHING and a guard that passes vacuously.
#:
#: **This lives in the test, deliberately, and must not migrate into `src/`.** The compendium is
#: hand-authored against the engine's card text and read back as data; `effect_overrides.json`'s own
#: `_note_fetch` says the runtime *"never parses card text at runtime OR build time"*. So this is a
#: rot-guard that grades the authored store against the printed card — the same job
#: `tests/scouting/test_tool_holder_facts.py` does for holder facts — not a production parser.
_PRINTED_GATE = re.compile(r"only if you (?:discard|put)|can[’']t use this card", re.I)


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
def test_shipped_gust_clauses_carry_the_target_the_trigger_and_the_riders():
    """Issue #303: the `gust` kind — *"Switch in 1 of your opponent's Benched Pokemon to the Active
    Spot"* — the highest-exposure family the POC-A2 census refused. All 7 pool sites round-trip
    override -> build -> `card_effects.json` with the fields the printed cards need, so the mechanic
    lives in the representation rather than in a text parse or the 5-rung weight ladder it dissolves.

    The load-bearing distinctions, each pinned because dropping one silently under-declares a card:
    `target` tells Lisia's Appeal (Benched **Basic** only) from the other six; `trigger: on_evolve`
    is what routes Hariyama's and Hop's Dubwool's clause onto the `_EVOLVE` site the engine actually
    poses (Issue #305 measured that a triggered Ability rides that option and poses no `_ABILITY` of
    its own); and a coin-gated gust composes as 1120 Crushing Hammer already does — a `coin` clause
    whose `effect` NAMES the gust, never a `probability` field on `gust` itself."""
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
    # The completeness verdicts ride with them. Five carry the whole printed card; the two that do
    # not are RULED incomplete rather than left unruled — the undecided `Team Rocket's` name family
    # (the 1115 / 1134 / 1215 / 1220 ruling) and the coin stating a 50/50 as a certainty (1120's).
    assert [eff.covers(c) for c in (1182, 674, 310, 1088, 1204)] == ["full"] * 5
    assert eff.covers(1218) == "partial" and eff.clauses_cover(1218) is False
    assert eff.covers(1124) == "partial" and eff.clauses_cover(1124) is False


@pytest.mark.req("REQ-EFFECT-0004")
def test_shipped_stadium_clauses_carry_the_effect_the_magnitude_and_the_body_predicate():
    """Issue #304: `stadium_static` and `stadium_trigger`. Six pool Stadiums round-trip override ->
    build -> `card_effects.json`, each with the fields its printed text needs.

    Two kinds rather than one, because the 22 Stadiums in the pool are five unrelated effect shapes
    wearing a single card type — one `stadium` kind would be a union of everything or a lie. Neither
    kind carries a write-set; the clause's `effect` does, which is 1120 Crushing Hammer's shape.

    The load-bearing fields, each pinned because dropping one silently mis-states a card:

    * `amount` is **SIGNED** — Gravity Mountain is −30 HP and Lively Stadium is +30, and an unsigned
      read would turn the pool's one Stadium that *shrinks* Stage 2s into one that grows them.
    * `symmetric` is on all six: every one prints *"both yours and your opponent's"*, so a Stadium I
      play helps my opponent too, and pricing my own half alone would make every Stadium look free.
    * `timing` carries the Weakness/Resistance ORDER the two damage modifiers print, which decides
      whether the ×2 lands on the modified number or the printed one.
    * `on: "bench_play"` is Risky Ruins' trigger EVENT, and it is deliberately **not** spelled
      `trigger`: that key routes a clause to a SITE (`on_evolve` / `on_bench_play` / `on_attach`),
      and using it here would file this clause on an option the engine never poses for a Stadium —
      which would orphan it and silently un-cover the card."""
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
    # All six carry their whole printed card. The two predicates that could have been ruled
    # `partial` are not, and each defers to a verdict already shipped for the SAME predicate rather
    # than being decided fresh here: 1247's `no_rule_box` is what 1152 Poke Pad is ruled `full` on,
    # and its discard-pile sentence is 1096 Poke Vital A's *"a property of the card once it is in the
    # discard"*. 1255's `Hop's` family is decided by `name_in_family`'s prefix test over a body
    # ALREADY IN PLAY, which that function's own docstring separates from Issue #301's hidden-deck
    # question — the reason 1115 / 1134 / 1215 / 1220 are `partial`.
    assert [eff.covers(c) for c in (1244, 1247, 1251, 1252, 1255, 1260)] == ["full"] * 6
    assert all(eff.clauses_cover(c) is True for c in (1244, 1247, 1251, 1252, 1255, 1260))


@pytest.mark.req("REQ-EFFECT-0004")
def test_the_conditional_draw_supporters_state_the_card_and_not_the_probe_s_best_case():
    """**Issue #302.** The 14 draw Supporters whose committed clause was a flat count where the
    printed card is conditional — the worst-served family in the apply-seam census.

    Every one of them was PROBE-MEASURED, never authored: `classify_effect_clauses` counts the
    actor's DRAW logs and this module's header already says a conditional count *"resolves to the
    best observed case"*, so a long game that organically hit Lacey's prize-bonus mode measured 8 and
    shipped 8 as if it were the base. A measurement of ONE resolution cannot state a card whose count
    depends on the board, which is why these are overrides now.

    The three shapes, each pinned because dropping one restores a specific lie:

    * `to_hand_size` — *"draw cards until you have N in your hand"* is a REFILL. It is mutually
      exclusive with `amount`, asserted below, because the number of cards drawn is not knowable
      until resolution and an `amount` beside it would invite a reader to take the wrong one.
    * `amount_if` — the second magnitude REPLACES the first (*"draw 8 cards instead"*), and its
      predicate is named rather than hard-coded, generalising 17 Ignition Energy's shipped
      `amount` + `amount_on_evolution`. `hand_size_10_plus_after_draw` carries the *after* in its
      name on purpose: Billy & O'Nare prints *"Draw 2 cards. Then, if you have 10 or more…"*, so a
      reader testing the PRE-play hand fires the bonus two cards early.
    * `cost_required` — that failing to pay makes the card UNPLAYABLE, which is a different fact from
      the cost merely being expensive. 1192 Carmine's `discard_hand` is the expensive kind and
      carries no such flag: *"Discard your hand and draw 5 cards."* is an instruction, always
      payable, so a gate there would assert a restriction the card does not print.

      **This bullet used to name 1121 Ultra Ball as the expensive kind, and that was wrong** —
      Issue #372 corrected it. Ultra Ball prints *"You can use this card only if you discard 2 other
      cards from your hand"*, the same restriction 1187 and 1208 carry, so it is a gate; it went
      unflagged only because this issue's scope was the 14 partial DRAW clauses and Ultra Ball is a
      `fetch`. The word *"deliberately"* stood in that sentence for a ruling nobody had made. The
      biconditional that replaces it is graded against the engine's own card text in
      `test_cost_required_agrees_with_the_printed_gate_on_every_cost_bearing_card`.

    The two coin cards keep `kind: "draw"` rather than 1120 Crushing Hammer's `kind: "coin"`, for a
    mechanical reason asserted below: `_union_overrides` replaces measured clauses BY KIND, so a
    `coin`-kinded override would leave the probe's measured `draw` clause standing beside it and the
    compendium would claim the card draws twice."""
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
    # 1121 Ultra Ball is a GATE too, since Issue #372 — it prints the same restriction 1208 does and
    # was missed only because it is a `fetch` and this issue's 14 were all `draw`. The assertion here
    # used to be `"cost_required" not in ...`, which recorded that omission rather than grading it.
    assert eff.clauses(1121) == ({"kind": "fetch", "target": "pokemon", "zone": "deck",
                                  "cost": "discard_2", "cost_required": True},)     # Ultra Ball
    # Morty's Conviction stated NO magnitude until Issue #349, because "one card per opponent BENCHED
    # Pokemon" is a board-scaled count no clause field expressed. The fail-closed silence has been
    # REPLACED by the fact it stood in for — never by the flat 3 the probe measured, a number the card
    # never prints: `amount: 1` multiplied by the count `amount_per` names.
    assert eff.clauses(1187) == ({"kind": "draw", "amount": 1, "amount_per": "their_bench",
                                  "cost": "discard_1", "cost_required": True},)
    # The coin pair — `kind: "draw"`, so the override replaces the measured draw rather than
    # doubling it, with the heads leg as the base and the tails leg as the replacement.
    assert eff.clauses(1223) == ({"kind": "draw", "amount": 5,                          # Harlequin
                                  "amount_if": {"condition": "coin_tails", "amount": 3},
                                  "rider": "shuffle_both_hands"},)
    assert eff.clauses(1237) == ({"kind": "draw", "amount": 6,                             # Lucian
                                  "amount_if": {"condition": "coin_tails", "amount": 3},
                                  "rider": "both_hands_to_bottom"},)
    assert all(c["kind"] == "draw" and len(eff.clauses(cid)) == 1
               for cid in (1223, 1237) for c in eff.clauses(cid))
    # Judge gains the rider its own count never needed; Unfair Stamp is UNCHANGED — its own leg was
    # already exact, which is why it is in the issue's 14 for the opponent leg alone.
    assert eff.clauses(1213) == ({"kind": "draw", "amount": 4,                              # Judge
                                  "rider": "shuffle_both_hands"},)
    assert eff.clauses(1080) == ({"kind": "draw", "amount": 5,                     # Unfair Stamp
                                  "condition": "pokemon_ko_last_turn",
                                  "rider": "shuffle_both_hands"},)
    # NINE of the 14 now carry the whole printed card — Morty's Conviction joined the eight at Issue
    # #349, when `amount_per` gave its board-scaled count a field. The five that remain are RULED
    # incomplete with the leg named: four for the SYMMETRIC opponent redraw (a `state_value` term the
    # POC does not have), and Naveen for its optional pre-discard.
    assert [eff.covers(c) for c in (1181, 1187, 1192, 1199, 1200, 1203, 1208, 1216, 1227)] == \
        ["full"] * 9
    for still_partial in (1080, 1213, 1223, 1237, 1239):
        assert eff.covers(still_partial) == "partial", still_partial
        assert eff.clauses_cover(still_partial) is False, still_partial
    # Two cards OUTSIDE the issue's 14 move with them, because one store cannot hold two verdicts
    # for one shape: 1214 Emcee's Hype is 1199 Lacey's predicate exactly, and 1206 Larry's Skill
    # prints 1192 Carmine's *"Discard your hand"* sentence and was ruled partial for the lack of the
    # very field this issue mints. Larry's repeats the cost on all three legs, which is 1092 Secret
    # Box's shipped shape for one cost paid once across a multi-leg find.
    assert eff.clauses(1214) == ({"kind": "draw", "amount": 2,
                                  "amount_if": {"condition": "opp_3_or_fewer_prizes", "amount": 4}},)
    assert [c["cost"] for c in eff.clauses(1206)] == ["discard_hand"] * 3
    assert [eff.covers(c) for c in (1206, 1214)] == ["full", "full"]
    assert [c["cost"] for c in eff.clauses(1092)] == ["discard_3"] * 4               # the precedent


@pytest.mark.req("REQ-EFFECT-0004")
def test_cost_required_agrees_with_the_printed_gate_on_every_cost_bearing_card():
    """**Issue #372.** One store held two opposite readings of ONE sentence, and every existing check
    was blind to it because every existing check is per-KEY or per-CARD.

    `undeclared_clause_keys` asks *"is `cost_required` a declared key?"* (yes) and `covers_problems`
    asks *"does this card have a verdict?"* (yes). Neither can ask *"do two cards printing the same
    sentence read it the same way?"*, so 1233 Canari and 1187 Morty's Conviction carried the
    character-for-character identical *"You can use this card only if you discard another card from
    your hand."* and disagreed about whether that is a playability gate.

    **The split was scope, not a ruling.** Issue #302 minted `cost_required` while rewriting *the 14
    partial DRAW clauses*, and its §3 named exactly Morty's Conviction, Iris's Fighting Spirit, Kofu
    and Carmine. The three FETCH cards printing the same gate — 1121 Ultra Ball, 1092 Secret Box,
    1233 Canari — were never in that issue's 14, so they were never looked at. #302 even quotes
    *"Ultra Ball's `discard_2`"* as its example of the `cost` field that already existed. The store's
    own prose had already reached the right reading and only the DATA lagged: this file's `_covers`
    reason for 1233 says *"the `discard_1` cost the card is gated on"*, and `_note_fetch_family`
    writes both Canari and Secret Box as *"gated on"* their discard.

    So the invariant graded here is the one the printed card states, not the one #302 happened to
    author: **a `cost` carries `cost_required: true` if and only if the card prints a playability
    gate.** It bites in both directions, which is what makes it a guard rather than a record —
    adding the flag to a card that merely charges a price fails it exactly as omitting it from a
    gated one does.

    Two negatives are asserted rather than left implicit, because a sweep over *"every card with a
    `cost`"* would wrongly catch them: 1192 Carmine's *"Discard your hand and draw 5 cards."* and
    1206 Larry's Skill's *"Discard your hand and search your deck…"* are INSTRUCTIONS, always payable
    — including on a hand holding nothing but the Supporter itself — so `cost_required` there would
    assert a restriction the card does not print.

    And the whole thing carries POSITIVE CONTROLS, because most of what it asserts is a negative: a
    gate regex that matched nothing would make every clause "correctly ungated" and the guard would
    pass while measuring air."""
    from pathlib import Path
    from common.effects import CardEffects
    from meta_tracker.cards import load_cards
    cards = load_cards()
    eff = CardEffects.load(Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json")

    # (0) CONTROLS, before any conclusion is drawn from a silence.
    #     The instrument must FIRE on both printed phrasings and stay QUIET on the two instructions.
    assert _PRINTED_GATE.search(_printed_text(cards[1187]))          # "only if you discard another…"
    assert _PRINTED_GATE.search(_printed_text(cards[1200]))          # "…you can’t use this card."
    assert not _PRINTED_GATE.search(_printed_text(cards[1192]))      # "Discard your hand and draw 5"
    assert not _PRINTED_GATE.search(_printed_text(cards[1206]))      # "Discard your hand and search"

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
    #     1092 Secret Box repeats its cost on all four search legs and 1206 Larry's Skill on all
    #     three, which is the shipped shape for one cost paid once across a multi-leg card.
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

    # (4) 1148 Blowtorch is the DEFERRAL, made into a tripwire instead of a TODO. It prints the gate
    #     — *"You can use this card only if you discard a Basic {R} Energy card from your hand."* —
    #     but has no compendium entry at all, because the cost it needs is a TYPED single-card
    #     discard and no `cost` value expresses that; minting one is a `CLAUSE_WRITES` decision, not
    #     this issue's. 0 copies across our 6 decks, so nothing is mispriced meanwhile. The moment it
    #     gains a `cost`, it joins `costed` above and (1) grades it.
    assert _PRINTED_GATE.search(_printed_text(cards[1148]))
    assert eff.clauses(1148) == ()


@pytest.mark.req("REQ-EFFECT-0004")
def test_a_coin_kinded_override_would_leave_the_measured_draw_clause_standing():
    """The measurement behind the ruling above, made executable rather than asserted in prose.

    `_union_overrides` keeps every measured clause whose `kind` is not among the override's kinds. So
    a `{"kind": "coin", "effect": "draw"}` override over Harlequin's probe-measured `{"kind": "draw",
    "amount": 5}` ships BOTH — a compendium claiming the card draws twice. Keeping `kind: "draw"`
    replaces it, which is why the coin rides as `amount_if` instead of as the clause kind."""
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
    """The artifact itself, not a fixture. Every card with clauses carries a verdict.

    Issue #300 was opened on two named holes, Surfer's switch and Crushing Hammer's coin. Issue #302
    closed the first — the switch is now the `self_switch` rider — so the PARTIAL example here is
    Judge, whose symmetric opponent redraw is a declared unknown rather than unfinished work. The
    coin is unchanged and stays the standing precedent."""
    from pathlib import Path
    from common.effects import CardEffects
    eff = CardEffects.load(Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json")
    assert eff.covers(1213) == "partial" and eff.clauses_cover(1213) is False   # Judge
    assert eff.covers(1120) == "partial" and eff.clauses_cover(1120) is False   # Crushing Hammer
    assert eff.covers(1121) == "full" and eff.clauses_cover(1121) is True       # Ultra Ball
    assert eff.covers(1203) == "full" and eff.clauses_cover(1203) is True       # Surfer, Issue #302
