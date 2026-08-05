"""The HEAL target select (ctx 17) — `Pilot._heal_target_tactical` (Issue #409).

Before this term nothing in the strategy layer gated on `SelectContext.HEAL` at all, so every
option scored 0.0 and `_order_key` fell through to `canonical_keys`, a lexicographically sorted JSON
board fragment whose first differing field is the AREA — `ACTIVE` 4 against `BENCH` 5. The Pilot
therefore healed the Active on every board, for every heal card, as an artefact of string
comparison rather than a policy anyone chose.

**Validation is BY CONSTRUCTION, and that is forced rather than chosen** (Issue #409 R5). Measured
over all 28 committed correction files: **372** ruled frames carry a select context and **zero** of
them are ctx 17 (nor ctx 16, its sibling), so *"no ruled frame moves"* is vacuous here and cannot be
the bar. What stands in for it:

* the four REAL multi-option ctx-17 boards in the committed parity corpus, used as **constructed
  fixtures** — their board states are genuine engine output, and their recorded ``choice`` is
  discarded. Every one of those traces carries ``meta.policy = "chaos:seed=NNNN"``:
  `tools/parity/capture_match.py` drives them with a randomised policy to exercise the engine, so
  the picks are NOISE. Reading them as rulings would anchor this file to a coin flip, which is
  exactly why the numbers asserted below are the term's own legs and not the trace's choice.
* unit assertions on each leg of the equation, including the fail-closed floor.

The corpus census itself is asserted (`test_corpus_ctx17_census_is_what_the_equation_was_built_on`)
so a future capture that adds ctx-17 frames makes this file say so rather than silently drifting.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from common.cards import CardFunctions
from common.effects import CardEffects
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.context import _ACTIVE, _BENCH, _CARD, _HEAL, _MAIN
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import card_opt, make_select, poke, state

REPO = Path(__file__).resolve().parents[2]
PARITY = REPO / "tests" / "fixtures" / "parity"

WALLYS = 1229          # Wally's Compassion — heal all from 1 of your Mega ex, bounce its Energy
POTION = 1117          # Potion — heal 30 from 1 of your Pokémon (no restriction, no rider)
JACINTHE = 1241        # Jacinthe — heal 150 from 1 of your {P} Pokémon
DRAGON_ELIXIR = 1105   # Dragon Elixir — `restriction: active_dragon_only`, unreadable => fail closed
BIANCA = 1190          # Bianca's Devotion — heal all, `condition: remaining_hp_30_or_less`
M_STARMIE = 1031       # Mega Starmie ex — 330 HP, Jetting Blow {W} 120 (+50 bench), Nebula Beam ●●● 210
STARYU = 1030
CAPE = 1159            # Hero's Cape — +100 HP


# ─────────────────────────────────────────────────────────── the four real corpus boards
#: ``(trace, frame)`` of every ctx-17 step in the committed parity corpus that offers a real CHOICE
#: (menu width 2). The other eleven ctx-17 steps are width 1 — forced, no decision to make.
REAL_CHOICES = [("ms_mirror_1001", 90), ("v2_ms_mirror_5000", 82),
                ("v2_ms_mirror_5000", 126), ("v2_ms_mirror_5001", 100)]


def _frame(trace: str, index: int) -> dict:
    with gzip.open(PARITY / f"{trace}.trace.json.gz", "rt", encoding="utf-8") as fh:
        return json.load(fh)["frames"][index]


def _shipped_pilot():
    """mega_starmie's REAL Pilot — every kill-switch at its shipped default, exactly as `main.py`
    builds it. The corpus boards are all Mega Starmie mirrors, so this is the agent that actually
    faced them."""
    import sys
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot("mega_starmie")[0]


def _legs(pilot, frame: dict):
    """``[(is_active, term, gain, bounce), …]`` per option of a ctx-17 frame, plus the Pilot's pick."""
    obs = frame["obs"]
    sel, cur = obs["select"], obs["current"]
    yi = cur["yourIndex"]
    board = pilot._board(obs)
    cid = sel["effect"]["id"]
    zone = {_ACTIVE: "active", _BENCH: "bench"}
    out = []
    for o in sel["option"]:
        body = cur["players"][o.get("playerIndex", yi)][zone[o["area"]]][o["index"]]
        stat = pilot.stats.get(body["id"])
        is_active = o["area"] == _ACTIVE
        attach = 0 if board.energy_attached else pilot._best_hand_attach_units(board.hand_ids, stat)
        cand = pilot._heal_body_candidate(cid, stat, is_active=is_active, cur_hp=body["hp"],
                                          attached=len(body["energies"]), attach_units=attach,
                                          max_hp=body["maxHp"])
        gain = pilot._heal_survival_gain(obs, board, body, stat, cid, cand[0], is_active=is_active)
        bounce = pilot._heal_bounce_cost(obs, board, body, cand[1], is_active=is_active)
        out.append((is_active, pilot._heal_target_tactical(obs, sel, board, o), gain, bounce))
    return out, pilot.explain(obs).chosen


def test_corpus_ctx17_census_is_what_the_equation_was_built_on():
    """The ground truth Issue #409 measured, re-measured here so a later capture cannot quietly
    change it: 15 ctx-17 steps over the 377 committed traces, 11 of them FORCED (menu width 1) and
    4 offering a real choice; Wally's Compassion x14 and Potion x1; every one a mandatory single
    pick (`minCount`/`maxCount` 1/1)."""
    steps, widths, cards = 0, {}, {}
    for path in sorted(PARITY.glob("*.trace.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            frames = json.load(fh)["frames"]
        for fr in frames:
            sel = (fr.get("obs") or {}).get("select") or {}
            if sel.get("context") != _HEAL:
                continue
            steps += 1
            widths[len(sel["option"])] = widths.get(len(sel["option"]), 0) + 1
            cid = (sel.get("effect") or {}).get("id")
            cards[cid] = cards.get(cid, 0) + 1
            assert (sel.get("minCount"), sel.get("maxCount")) == (1, 1)
    assert steps == 15
    assert widths == {1: 11, 2: 4}
    assert cards == {WALLYS: 14, POTION: 1}


@pytest.mark.parametrize("trace,index", REAL_CHOICES)
def test_the_four_real_boards_rank_by_the_equation_and_not_by_a_string_sort(trace, index):
    """Every real ctx-17 choice in the corpus now scores STRICTLY apart, and the winner is the body
    the equation prefers rather than whichever fingerprint sorts first.

    On all four the Active wins — and that is a result, not the old bug re-expressed: on each board
    the Active is the body actually being attacked, so it carries the whole ``survival_gain`` while
    the benched Mega ex is reachable only by Jetting Blow's 50-damage rider. The proof that the
    *equation* is deciding rather than the AREA field is
    `test_the_bounce_rider_flips_the_pick_when_the_re_attach_is_gone`, where the same f126 board with
    its re-attach removed picks the BENCH.

    The recorded ``choice`` on these frames is deliberately NOT asserted: `meta.policy` is
    ``chaos:seed=NNNN`` on every trace, so it is a random pick and proves nothing about good play."""
    pilot = _shipped_pilot()
    legs, chosen = _legs(pilot, _frame(trace, index))
    assert len(legs) == 2
    (active_is_active, active_term, _ag, _ab), (bench_is_active, bench_term, _bg, _bb) = legs
    assert (active_is_active, bench_is_active) == (True, False)
    assert active_term != bench_term, "a tie hands the pick back to the canonical string sort"
    assert active_term > bench_term
    assert chosen == [0]


def test_bounce_cost_is_zero_on_every_real_corpus_board_and_the_reason_is_the_re_attach():
    """**A measured correction to Issue #409's own reading of f126.** The issue names
    `v2_ms_mirror_5000` f126 as *the* discriminating frame because healing its Active bounces two
    attached Energy. On the real board that costs NOTHING: the hand holds an Ignition Energy (17,
    {C}{C}{C} on an Evolution), so the one manual attach still affords Nebula Beam's ●●● and
    ``best_affordable(before) == best_affordable(after)``. The same holds on the other three.

    Recorded as an assertion rather than a footnote because it is the premise of the next test — the
    dilemma is real, but the corpus does not happen to contain it, so it has to be CONSTRUCTED."""
    pilot = _shipped_pilot()
    for trace, index in REAL_CHOICES:
        legs, _ = _legs(pilot, _frame(trace, index))
        assert [round(b, 6) for _a, _t, _g, b in legs] == [0.0, 0.0], f"{trace} f{index}"


def test_the_bounce_rider_flips_the_pick_when_the_re_attach_is_gone():
    """R2's dilemma, on `v2_ms_mirror_5000` f126's real board with its two Ignition Energy removed
    from hand — the ONE change, so everything else is genuine engine output.

    The Active is now the most-damaged body (120 to the bench's 50) **and** the wrong target: healing
    it bounces its two {W}, and with no re-attach in hand that forfeits Jetting Blow outright. The
    ctx-16 rule (`_best_counter_source_slot`'s most-damaged body) picks the Active here; this term
    picks the BENCH, which is the whole reason R2 refuses to reuse it."""
    pilot = _shipped_pilot()
    frame = _frame("v2_ms_mirror_5000", 126)
    cur = frame["obs"]["current"]
    me = cur["players"][cur["yourIndex"]]
    me["hand"] = [c for c in me["hand"] if c["id"] != 17]      # drop the Ignition: no re-attach
    me["handCount"] = len(me["hand"])
    legs, chosen = _legs(pilot, frame)
    (_a, active_term, active_gain, active_bounce), (_b, bench_term, _bg, bench_bounce) = legs
    assert active_bounce > 0, "bouncing two {W} off the Active must forfeit Jetting Blow"
    assert bench_bounce == 0.0                                 # a benched body swings for nothing
    assert active_term == active_gain - active_bounce
    assert active_term < bench_term                            # ... so the BENCH is healed
    assert chosen == [1]


# ────────────────────────────────────────────────────────────── the equation, leg by leg
def _stats(**over):
    table = {
        M_STARMIE: CardStat(cardId=M_STARMIE, hp=330, megaEx=True, energyType=3,
                            evolvesFrom="Staryu"),
        STARYU: CardStat(cardId=STARYU, hp=70, energyType=3),
        CAPE: CardStat(cardId=CAPE, hp=0),
        3: CardStat(cardId=3, hp=0, energyType=3),
        999: CardStat(synthetic=True, cardId=999, hp=200, maxDamage=200),
    }
    table.update(over)
    return DictCardStatProvider(table)


def _pilot(*, effects=None, stats=None):
    return Pilot(Strategy(), deck=[], general_strategy=GENERAL_STRATEGY,
                 stats=stats or _stats(), functions=CardFunctions({WALLYS: ["heal", "clutch_heal"]}),
                 effects=effects if effects is not None else CardEffects.load())


def _heal_obs(*, cid=WALLYS, active, bench, hand=(), opp_active=None, opp_max_damage=200,
              options=None):
    """A ctx-17 select over ``active`` + ``bench``, with the resolving heal card on `select.effect`."""
    opp = opp_active if opp_active is not None else poke(999, hp=200, max_hp=200)
    cur = state(active=active, bench=list(bench), hand=list(hand), opp_active=opp,
                prizes=6, opp_prizes=6)
    opts = options if options is not None else [card_opt(_ACTIVE, 0), card_opt(_BENCH, 0)]
    obs = make_select(opts, context=_HEAL, type=_CARD, current=cur, effect={"id": cid})
    return obs, opp_max_damage


def _term(pilot, obs, option):
    return pilot._heal_target_tactical(obs, obs["select"], pilot._board(obs), option)


def test_the_constant_lands_where_the_enum_says_it_should():
    """AC8: `strategy/context.py` used to jump straight from `_REMOVE_DAMAGE_COUNTER` (16) to
    `_REMOVE_DAMAGE_COUNTER_COUNT` (40), so the next reader looking for 17 found nothing at all."""
    from cg.api import SelectContext
    assert _HEAL == int(SelectContext.HEAL) == 17


def test_off_ctx_17_the_term_is_silent():
    """Gated, like every sibling target term — so nothing outside the HEAL select can move."""
    pilot = _pilot()
    obs, _ = _heal_obs(active=poke(M_STARMIE, hp=100, max_hp=330, energy_card=3, energy=2),
                       bench=[poke(M_STARMIE, hp=300, max_hp=330)])
    obs["select"]["context"] = _MAIN
    assert _term(pilot, obs, obs["select"]["option"][0]) == 0.0


def test_a_bench_body_no_attack_can_reach_gains_nothing():
    """AC3 / R2's bench asymmetry, and it is DERIVED rather than authored: `incoming(my_benched=True)`
    reads the snipe/spread RIDERS only, because printed damage always lands on the Active
    (ADR-0070 §9). So a benched body no opponent attack can reach gains nothing from being healed,
    however damaged it is.

    Both arms are real boards and real cards, because the claim is about card facts. NEGATIVE: swap
    `v2_ms_mirror_5001` f100's opponent Active for a **Staryu**, whose only attack is Water Gun {W}
    20 with no rider at all (`EN_Card_Data.csv`) — the benched Mega ex becomes unreachable and its
    gain drops to exactly 0. POSITIVE CONTROL, same instrument on the untouched frame: the real
    opponent is a **Mega Starmie ex**, whose Jetting Blow *"also does 50 damage to 1 of your
    opponent's Benched Pokémon"*, so reach is 50 and the gain is non-zero. Without the control, a
    broken reach read and a genuinely-unreachable body return the same 0.0."""
    pilot = _shipped_pilot()
    frame = _frame("v2_ms_mirror_5001", 100)
    obs = frame["obs"]
    yi = obs["current"]["yourIndex"]
    bench_body = obs["current"]["players"][yi]["bench"][0]
    stat = pilot.stats.get(bench_body["id"])
    reachable = pilot._heal_survival_gain(obs, pilot._board(obs), bench_body, stat, WALLYS,
                                          bench_body["maxHp"], is_active=False)
    assert reachable > 0.0                                     # positive control: the 50 rider lands

    obs["current"]["players"][1 - yi]["active"] = [poke(STARYU, hp=70, max_hp=70, energy_card=3,
                                                        energy=1)]
    unreachable = pilot._heal_survival_gain(obs, pilot._board(obs), bench_body, stat, WALLYS,
                                            bench_body["maxHp"], is_active=False)
    assert unreachable == 0.0                                  # Water Gun carries no bench rider


def test_a_benched_bounce_costs_nothing_because_only_the_active_swings():
    """AC4's first half (R2: *"zero for a body that was not going to attack this turn"*)."""
    pilot = _pilot()
    obs, _ = _heal_obs(active=poke(M_STARMIE, hp=300, max_hp=330),
                       bench=[poke(M_STARMIE, hp=10, max_hp=330, energy_card=3, energy=3)])
    board = pilot._board(obs)
    bench_body = obs["current"]["players"][0]["bench"][0]
    assert pilot._heal_bounce_cost(obs, board, bench_body, 0, is_active=False) == 0.0


def test_an_unreadable_restriction_contributes_exactly_zero_and_never_a_guess():
    """AC5 / R3. Dragon Elixir's ``active_dragon_only`` is not in the restriction vocabulary — it is
    a recorded, deliberate under-count (`snapshot_coverage.UNCONSUMED_SELECTORS`) — so the clause
    fails CLOSED and the option contributes 0.0. Jacinthe's ``psychic_only`` is readable and simply
    does not match a {W} body, which is the same 0.0 for a different reason: a refusal, not a guess.

    The positive control sits alongside: Potion, unrestricted, on the identical board is NON-zero —
    so the 0.0s above are the restriction speaking and not a dead code path."""
    pilot = _pilot()
    board_kw = dict(active=poke(M_STARMIE, hp=100, max_hp=330),
                    bench=[poke(M_STARMIE, hp=300, max_hp=330)])
    for cid in (DRAGON_ELIXIR, JACINTHE):
        obs, _ = _heal_obs(cid=cid, **board_kw)
        assert _term(pilot, obs, obs["select"]["option"][0]) == 0.0, cid
    obs, _ = _heal_obs(cid=POTION, **board_kw)
    assert _term(pilot, obs, obs["select"]["option"][0]) > 0.0     # positive control


def test_an_unevaluable_condition_fails_closed_too():
    """R3 again, on the other gate. Bianca's Devotion is ``condition: remaining_hp_30_or_less``, and
    the condition qualifies the CHOSEN Pokémon (card text, `EN_Card_Data.csv`): *"Heal all damage
    from 1 of your Pokémon that has 30 HP or less remaining."* A body above 30 HP is refused; one at
    or below it is priced. Reading the gate off the ACTIVE — which is what the pre-#409 reader did —
    would answer for the wrong Pokémon whenever the target is benched."""
    pilot = _pilot()
    stat = pilot.stats.get(M_STARMIE)
    healthy = pilot._heal_body_candidate(BIANCA, stat, is_active=False, cur_hp=300, attached=0,
                                         attach_units=0, max_hp=330)
    frail = pilot._heal_body_candidate(BIANCA, stat, is_active=False, cur_hp=20, attached=0,
                                       attach_units=0, max_hp=330)
    assert healthy is None                         # 300 HP left: the gate is not satisfied
    assert frail == (330, 0)                       # 20 HP left: heal all, no Energy rider


def test_the_restore_ceiling_is_the_body_not_the_printed_card():
    """A Hero's Cape (+100) puts a 330-HP Mega Starmie ex on a board ``maxHp`` of 430, and
    ``amount: "all"`` heals to THAT. Measured on `ms_mirror_1001` f90, where reading the printed HP
    under-heals the caped Active by a full 100."""
    pilot = _pilot()
    stat = pilot.stats.get(M_STARMIE)
    assert pilot._heal_body_candidate(WALLYS, stat, is_active=True, cur_hp=190, attached=0,
                                      attach_units=0, max_hp=430) == (430, 0)
    assert pilot._heal_body_candidate(WALLYS, stat, is_active=True, cur_hp=190, attached=0,
                                      attach_units=0) == (330, 0)      # default: printed HP


def test_the_pick_survives_a_permuted_menu_and_is_not_the_string_sort():
    """AC6: the ordering is a function of the BOARD, not of where an option sits in the menu — and,
    critically, **not of `canonical_keys`' string order**, which is what decided before this term
    existed.

    The board has to be one where the two disagree, or the test is vacuous. `canonical_keys` writes
    ``[area, card]`` and sorts lexicographically, so ``"4" < "5"`` makes it pick the ACTIVE on every
    board ever — a fixture the equation also resolves to the Active would pass with the term deleted.
    So this uses the one board where the equation says BENCH: f126 with its re-attach removed. The
    same body is healed from either menu order, and it is the body the string sort would NOT have
    chosen."""
    pilot = _shipped_pilot()
    frame = _frame("v2_ms_mirror_5000", 126)
    obs = frame["obs"]
    cur = obs["current"]
    me = cur["players"][cur["yourIndex"]]
    me["hand"] = [c for c in me["hand"] if c["id"] != 17]      # drop the Ignition: no re-attach
    me["handCount"] = len(me["hand"])
    active_opt, bench_opt = obs["select"]["option"]
    assert active_opt["area"] == _ACTIVE and bench_opt["area"] == _BENCH

    obs["select"]["option"] = [active_opt, bench_opt]
    assert pilot.explain(obs).chosen == [1]            # the BENCH, at index 1
    obs["select"]["option"] = [bench_opt, active_opt]
    assert pilot.explain(obs).chosen == [0]            # ... the same BENCH, now at index 0


# ─────────────────────────────────────────────── the body-generic readers (AC2)
_RESTRICTIONS = (None, "active_only", "mega_only", "psychic_only", "active_dragon_only",
                 "arvens_pokemon")


@pytest.mark.parametrize("restriction", _RESTRICTIONS)
def test_the_active_restriction_reader_is_byte_identical_to_the_body_generic_one(restriction):
    """AC2: `_heal_restriction_ok` is now `_heal_restriction_targets(..., is_active=True)`, and the
    two agree on the WHOLE shipped vocabulary. ``active_only`` is the one term the Active-only form
    could not express — it had to hardcode True, which is correct for its own caller and would
    silently offer a benched Cook / Lumiose Galette target if reused unchanged."""
    pilot = _pilot()
    for stat in (pilot.stats.get(M_STARMIE), pilot.stats.get(STARYU)):
        assert (pilot._heal_restriction_ok(restriction, stat)
                == pilot._heal_restriction_targets(restriction, stat, is_active=True))
    assert pilot._heal_restriction_targets("active_only", pilot.stats.get(M_STARMIE),
                                           is_active=False) is False


def test_only_wallys_is_in_any_shipped_deck_so_no_active_path_decision_can_move():
    """AC2's *"preserved bit-for-bit"*, measured rather than asserted.

    `_heal_candidate` used to check ``mega_only`` INLINE and let every other restriction through;
    it now routes the shared `_heal_restriction_targets`, which additionally refuses an unknown one
    and type-gates ``psychic_only``. That is strictly more correct, and the census below is why it
    moves nothing: **Wally's Compassion is the only `kind: heal` card in any shipped deck**, and its
    ``mega_only`` reads identically under both spellings. A deck that later fields Dragon Elixir or
    Jacinthe will get the corrected reading, and this test will say so by failing."""
    import csv
    healers = {cid for cid, clauses in CardEffects.load()._table.items()
               if any(c.get("kind") == "heal" for c in clauses)}
    assert len(healers) >= 13, "the heal family shrank — re-check what this census covers"
    for deck in sorted((REPO / "src" / "agents").glob("*/deck.csv")):
        with open(deck, encoding="utf-8-sig") as fh:
            ids = {int(v) for row in csv.DictReader(fh) for v in row.values()
                   if v and str(v).strip().isdigit()}
        assert ids & healers in ({}, set(), {WALLYS}), f"{deck.parent.name}: {ids & healers}"


def test_the_legacy_clutch_heal_tag_path_stays_active_only():
    """R3 at the fallback. The `clutch_heal` Function Tag records *"full heal + Energy bounce"* and
    nothing about WHICH bodies the card may reach, so on a benched candidate it would be a guess at a
    restriction rather than a reading of one — Wally's ``mega_only`` is a clause fact the tag cannot
    carry. Clause-blind, the Active still gets its legacy answer and the Bench gets None."""
    pilot = _pilot(effects=CardEffects({}))            # clause-blind: only the tag path is left
    stat = pilot.stats.get(M_STARMIE)
    assert pilot._heal_body_candidate(WALLYS, stat, is_active=True, cur_hp=100, attached=2,
                                      attach_units=1, max_hp=330) == (330, 1)
    assert pilot._heal_body_candidate(WALLYS, stat, is_active=False, cur_hp=100, attached=2,
                                      attach_units=1, max_hp=330) is None
