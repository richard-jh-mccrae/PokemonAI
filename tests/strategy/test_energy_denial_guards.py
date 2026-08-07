"""Energy denial, ADR-0062 amendment — the three guards the shipped oracle was missing.

All three are pinned against REAL captured frames, never hand-built menus — an invented board
manufactures a fake misplay.

  1. A BOOSTER MUST SCALE THE ORACLE, NEVER ADD TO IT. A flat positive rung stacked on a signed
     tactical can always resurrect a hold, and a free Item at score > 0 is tiered ahead of
     everything by `_finish_turn_last`.
  2. A DOOMED ACTIVE IS NOT A BLANK BOARD. *"I am about to KO their Active"* says nothing about a
     benched body banking Energy: hammer the bench, then take the KO.
  3. ENERGY ON A PRE-EVOLUTION IS BANKED, NOT SPENT — `docs/rules.md` says evolving keeps attached
     cards. The third test below is the CEILING on that credit, which is why it is discounted.
"""
import json
import sys
from pathlib import Path

import pytest

from common.pilot import _DENY_RELEVANCE_K

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"

HAMMER = 1120                       # Crushing Hammer


def _fx(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _pilot(agent, *, deny_relevance=True):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    p = _build_pilot(agent)[0]
    p.deny_relevance = deny_relevance
    p.deny_strip_delta = deny_relevance
    return p


def _hammer_indices(pilot, obs):
    """Option indices that PLAY a Crushing Hammer, read off the captured select."""
    select = obs["select"]
    out = []
    for i, o in enumerate(select["option"]):
        if pilot._option_card_id(obs, select, o) == HAMMER:
            out.append(i)
    return out


# --- guard 1: a booster must SCALE the oracle, never ADD to it -------------------------------------

# Kept parametrized rather than inlined so reinstating a second instrument is a one-line change; the
# `magnitude` arm tested the ADR-0062 OFF path, which Issue #228 deleted.
@pytest.mark.parametrize("armed", [True], ids=["relevance"])
def test_the_unfavored_booster_cannot_resurrect_a_hammer_the_oracle_declined(armed):
    """Bare bench, and my Active can already KO — so Deny Relevance reaches 0 STRUCTURALLY: the
    liveness gate zeroes the bench and the redundancy gate zeroes the Active we are about to KO."""
    fx = _fx("ms_hammer_unfavored_override_f17.json")
    pilot = _pilot("mega_starmie", deny_relevance=armed)
    obs = fx["obs"]
    hammers = _hammer_indices(pilot, obs)
    assert hammers, "fixture no longer offers a Crushing Hammer"
    chosen = pilot.explain(obs).chosen
    assert chosen[0] not in hammers, (
        f"played the Hammer {chosen} into a KO turn with a bare opponent bench "
        f"(hammer options {hammers}) -- a flat booster overrode the priced oracle")


class _HammerCtx:
    """The only three Context fields `_denial_play_tactical` reads."""
    option_type, tags, card_id = 7, ["energy_denial"], HAMMER       # 7 = _PLAY


# See the note above: the `magnitude` arm tested the ADR-0062 OFF path, deleted by Issue #228.
@pytest.mark.parametrize("armed", [True], ids=["relevance"])
@pytest.mark.parametrize("fixture, expect_positive", [
    ("ms_hammer_forward_form_riolu_f12.json", True),                # a real strip is on the table
    ("ms_hammer_unfavored_override_f17.json", False),               # a whiff: bare bench, doomed Active
])
def test_the_unfavored_read_scales_the_denial_and_can_never_flip_its_sign(fixture, expect_positive,
                                                                         armed):
    """`_DENIAL_UNFAVORED` is a MULTIPLIER, so it cannot rescue a whiff (0 x anything) or a hold (a
    negative stays negative). SCALE-INVARIANT, so the property held against the magnitude oracle too."""
    pilot = _pilot("mega_starmie", deny_relevance=armed)
    obs = _fx(fixture)["obs"]
    board = pilot._board(obs, obs["select"])

    # `_denial_play_tactical` takes the observation because `_deny_relevance_best` must be able to
    # recompute off `obs` when the Board carries an ABSENT (None) read rather than a measured zero.
    pilot._unfavored = lambda _b: True
    boosted = pilot._denial_play_tactical(obs, board, _HammerCtx())
    pilot._unfavored = lambda _b: False
    plain = pilot._denial_play_tactical(obs, board, _HammerCtx())

    if expect_positive:
        assert boosted > plain > 0, f"unfavored must amplify a live denial ({boosted} vs {plain})"
    else:
        assert boosted <= 0, (
            f"the unfavored Read resurrected a Hammer the oracle declined (scored {boosted}) -- "
            "a booster that can flip the sign is an override, not a boost")


# --- guard 2: a doomed Active is not a blank board ------------------------------------------------

def test_the_hammer_still_hits_the_BENCH_on_a_turn_i_knock_out_their_active():
    """Their Active dies anyway, but a benched body sits on exactly its attack cost, so the count
    BINDS and the strip puts that nuke out of reach. A KO turn must not blank the whole board."""
    fx = _fx("ms_hammer_bench_while_koing_active_f26.json")
    pilot = _pilot("mega_starmie")
    obs = fx["obs"]
    board = pilot._board(obs, obs["select"])
    assert board.active_can_ko, "fixture is not a KO turn"
    assert pilot._deny_relevance_best(obs, board) > 0, (
        "the doomed Active blanked the whole board -- a benched body banking Energy is still worth "
        "stripping on a KO turn")


def test_the_doomed_active_is_dropped_from_the_denial_max_not_the_whole_board():
    """Asserted on the per-body ROWS rather than as a fall in the board best, so it names WHICH
    contribution the gate removed instead of inferring it from a decrease."""
    fx = _fx("ms_hammer_bench_while_koing_active_f26.json")
    pilot = _pilot("mega_starmie")
    obs = fx["obs"]
    board = pilot._board(obs, obs["select"])
    cur = obs["current"]
    opp = cur["players"][1 - cur["yourIndex"]]
    oa = next((p for p in (opp.get("active") or []) if p), None)
    bench = [b for b in (opp.get("bench") or []) if b]
    assert oa and bench, "fixture must have an opponent Active and a benched body"

    ungated = pilot._relevance_terms(oa, doomed=frozenset(), area="active", bi=0)
    gated = pilot._relevance_terms(oa, doomed=frozenset({("active", 0)}), area="active", bi=0)
    bench_rel = pilot._relevance_terms(bench[0], doomed=frozenset(), area="bench", bi=0)

    assert ungated["relevance_fire"] > 0, (
        f"the Active must have something to drop, or the gate proves nothing "
        f"(ungated {ungated['relevance_fire']})")
    assert gated["relevance_fire"] == 0.0, (
        f"the redundancy gate must zero the doomed Active's own reading (got {gated['relevance_fire']})")
    assert bench_rel["relevance_fire"] > 0, "the bench must be the surviving reading"
    assert board.deny_relevance_best == pytest.approx(bench_rel["relevance_fire"]), (
        f"the drop took the whole board instead of the Active alone -- best "
        f"{board.deny_relevance_best} vs the bench's {bench_rel['relevance_fire']}")


# --- guard 3: Energy on a pre-evolution is BANKED, not spent ---------------------------------------

RIOLU, MEGA_LUCARIO = 677, 678     # Riolu: Accelerating Stab {F} 30. Mega Lucario ex: Aura Jab {F}
                                   # 130 / Mega Brave {F}{F} 270 (verified, data/EN_Card_Data.csv).
ACCELERATING_STAB = 30             # Riolu's own attack -- the price the "denial-now" reading paid.


def test_a_pre_evolutions_energy_is_priced_by_what_it_will_pay_for_not_what_it_pays_now():
    """`docs/rules.md`: evolving keeps attached cards, so a Riolu's `{F}` is BANKED for the Mega
    Lucario ex line. On the fixture's REAL Riolu — a synthetic body's Energy type will not resolve."""
    pilot = _pilot("mega_starmie")
    obs = _fx("ms_hammer_forward_form_riolu_f12.json")["obs"]
    pilot._board(obs, obs["select"])          # establish the per-decision state the read runs under

    cur = obs["current"]
    opp = cur["players"][1 - cur["yourIndex"]]
    riolu = next((p for p in (opp.get("active") or []) if p), None)
    assert riolu and riolu.get("id") == RIOLU, "fixture no longer has their Riolu Active"
    row = pilot._relevance_terms(riolu, doomed=frozenset(), area="active", bi=0)
    assert _DENY_RELEVANCE_K * row["relevance"] > ACCELERATING_STAB, (
        f"a Riolu banking Energy toward Mega Lucario ex is still priced at its own Accelerating Stab "
        f"({_DENY_RELEVANCE_K * row['relevance']} vs {ACCELERATING_STAB})")
    assert row["relevance_forward"] > 0, (
        "the lift must come from the FORWARD form, not from some other leg of the read")

    hammers = _hammer_indices(pilot, obs)
    assert hammers, "fixture no longer offers a Crushing Hammer"
    scored = pilot.explain(obs).options
    assert scored[hammers[0]].score > 5.0, (
        "the forward form must lift this Hammer clear of the +5.00 knife-edge it passed on before")


def test_the_forward_credit_is_discounted_so_it_cannot_bury_a_line_advance():
    """The CEILING on the forward credit: at FACE VALUE the Hammer buries both the evolve and the
    retreat-to-wall. The payoff is a turn away and contingent on them holding the evolution."""
    pilot = _pilot("dragapult_ex")
    obs = _fx("dx_hammer_forward_form_guard_f32.json")["obs"]
    hammers = _hammer_indices(pilot, obs)
    assert hammers, "fixture no longer offers a Crushing Hammer"
    chosen = pilot.explain(obs).chosen
    assert chosen[0] not in hammers, (
        f"the forward credit buried the line advance and played the Hammer {chosen} "
        f"(hammer options {hammers}) -- `_DENIAL_FORWARD` is too generous")
