"""Energy denial, ADR-0062 amendment — the three guards the shipped oracle was missing.

ADR-0062 priced the Crushing Hammer correctly (`coin x what the strip takes away - the cost of
keeping the Item`) and then left three holes around it. All three are pinned here against REAL
captured frames, never hand-built menus (see the isolated-probe lesson: an invented board
manufactures a fake misplay).

  1. A BOOSTER MUST SCALE THE ORACLE, NEVER ADD TO IT.  `disrupt-when-unfavored` (+18) rode a stale
     `opp_denial_best > 0` gate -- the raw PRESENCE of denial -- while the oracle's actual verdict is
     the priced play value, which can be zero or negative. A flat positive rung stacked on a signed
     tactical can always resurrect a hold, and a free Item at score > 0 is tiered ahead of everything
     by `_finish_turn_last`. ms 83968638 f17 (CRITICAL) is the live case.

  2. A DOOMED ACTIVE IS NOT A BLANK BOARD.  The stand-down keyed on `active_can_ko` and zeroed the
     WHOLE denial. But "I am about to KO their Active" only says the ACTIVE's Energy is worthless to
     strip -- it dies anyway. It says nothing about a benched body banking Energy. Hammer the bench,
     then take the KO. ms 82748422 f26.

  3. ENERGY ON A PRE-EVOLUTION IS BANKED, NOT SPENT.  `denial_value` read the target's OWN attacks, so
     a Riolu holding 1 Energy priced at 30 (Accelerating Stab {F}) -- when rules.md:98 says "Evolving
     keeps attached cards", and that same Energy pays Mega Lucario ex's Aura Jab ({F}, 130) the turn
     it evolves. ms 82225643 f12 is the case FOR it; dragapult 85046350 f32 is the CEILING on it --
     un-discounted, the forward form turns a Hammer we must not play from +10 into +40.
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

# The `magnitude` arm tested the ADR-0062 OFF path, DELETED by Issue #228 under tracker directive 1
# ("rungs an equation replaces are DELETED, not suppressed"). This file anticipated exactly that:
# "retiring the magnitude path later cannot regress this frame". The `relevance` arm is kept
# parametrized rather than inlined so reinstating a second instrument is a one-line change.
@pytest.mark.parametrize("armed", [True], ids=["relevance"])
def test_the_unfavored_booster_cannot_resurrect_a_hammer_the_oracle_declined(armed):
    """ms 83968638 f17, CRITICAL. Their Active is an Abra on 1 Energy and their bench is bare; my
    Active can already KO. The oracle prices the Hammer at 0 (it stands down on `active_can_ko`) --
    and `disrupt-when-unfavored` fired +18 on top, so the Hammer was played right before the KO.

    Human: "Must use turn planner to see that using Crushing Hammer here is a waste. we will KO the
    opponents active."

    This frame is the f17 RE-DERIVATION the ADR-0078 re-audit owed: armed, the hold no longer depends
    on the magnitude oracle standing down at all -- Deny Relevance reaches 0 structurally, because
    its liveness gate zeroes a bare bench and its redundancy gate zeroes the Active we are about to
    Knock Out. Same verdict, derived rather than guarded, which is why retiring the magnitude path
    could not regress this frame -- and Issue #228 has now retired it, so this is the sole remaining
    instrument rather than the second of two.
    """
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
    """The whole fix, stated as one property: `_DENIAL_UNFAVORED` is a MULTIPLIER, so it amplifies a
    denial that is already worth something and is powerless over one that is not.

    Multiplying cannot rescue a whiff (0 x anything is 0) or a hold (a negative stays negative) --
    which is precisely what the retired flat +18 did. Both directions are pinned on real boards.

    This is the LEVER A re-expression test (ADR-0080 Amendment B, user ruling 2026-07-30). ADR-0078
    decision 6 would have retired `_DENIAL_UNFAVORED` outright; that retirement is withdrawn, because
    deny reads `needs.phase_scale` on no surface and this is Lever A's last live consumer. Instead
    its SUBJECT moved -- it scales `K x relevance` exactly as it scaled the damage magnitude, and the
    property is SCALE-INVARIANT, which is why the assertion below reads verbatim as it did against
    the magnitude oracle. It used to run on both instruments; Issue #228 deleted that one, so the
    invariance is now recorded here in prose and asserted against the surviving instrument only.
    """
    pilot = _pilot("mega_starmie", deny_relevance=armed)
    obs = _fx(fixture)["obs"]
    board = pilot._board(obs, obs["select"])

    # `_denial_play_tactical` takes the observation as well since Issue #228: the fire rung reads
    # `_deny_relevance_best`'s cache-or-compute ladder, which must be able to recompute off `obs`
    # when the Board carries an ABSENT (None) read rather than a measured zero.
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
    """ms 82748422 f26. Their Active is a Cinderace my Jetting Blow will KO this turn -- its Energy is
    worthless to strip, it dies anyway. But a benched Mega Starmie ex sits on 3 Energy (Nebula Beam
    ``●●●`` 210: on exactly 3 the count BINDS, so the strip puts that nuke out of reach). Hammering
    the bench and THEN taking the KO costs nothing; the old `active_can_ko` stand-down zeroed the
    whole board and left it untouched.

    Read off the armed instrument (`_deny_relevance_best`) since Issue #228 deleted
    `Board.opp_denial_best` with the rest of the ADR-0062 magnitude oracle. The claim is unchanged:
    a KO turn must not blank the board."""
    fx = _fx("ms_hammer_bench_while_koing_active_f26.json")
    pilot = _pilot("mega_starmie")
    obs = fx["obs"]
    board = pilot._board(obs, obs["select"])
    assert board.active_can_ko, "fixture is not a KO turn"
    assert pilot._deny_relevance_best(obs, board) > 0, (
        "the doomed Active blanked the whole board -- a benched body banking Energy is still worth "
        "stripping on a KO turn")


def test_the_doomed_active_is_dropped_from_the_denial_max_not_the_whole_board():
    """The narrow claim, stated directly on the oracle: the redundancy gate must remove ONLY the
    Active's contribution.

    **The reference moved (Issue #228).** It used to be asserted as a strict FALL of
    `_opp_denial_best(opp, active_doomed=...)` -- their Active (Cinderace, 1 Energy) out-denied the
    benched Mega Starmie ex once `_DENIAL_BENCH` discounted the bench, so dropping the Active moved
    the max. Both of those are gone: the method with the magnitude oracle, and the bench discount
    with ADR-0084 decision 5. Armed the bench is the argmax outright (0.60 vs the Active's 0.14), so
    there is no fall left to observe.

    So the claim is asserted DIRECTLY on the per-body rows instead, which is strictly more precise --
    it names which contribution the gate removed rather than inferring it from a decrease:

      * the Active carries a real reading to drop (ungated relevance > 0), so the gate is not being
        credited for a body that was worth nothing anyway;
      * gating it zeroes exactly that reading;
      * and the board's best is still positive and is the BENCH's reading, untouched.
    """
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
    """ms 82225643 f12. Their Active is a Riolu holding 1 Energy.

    Riolu's OWN attack is Accelerating Stab ({F}, 30) -- so denial-now prices the strip at 30, and the
    Hammer scraped through at +5.00 only because that Riolu happened to be ACTIVE (on the bench, where
    a pre-evolution normally banks Energy, the retired `_DENIAL_BENCH` discount would have taken it
    to -6.25 and we would have held).

    But rules.md:98 -- "Evolving keeps attached cards" -- and Riolu is the SOLE pre-evolution of Mega
    Lucario ex (a single hop; there is no intermediate Lucario in this set). That Energy is not paying
    for a 30-damage Accelerating Stab. It is being BANKED for the Mega Lucario ex line -- Aura Jab
    ({F}, 130) and, since a lone ``{F}`` sits inside Mega Brave's ``{F}{F}`` slot too, Mega Brave
    ({F}{F}, 270), which is the top of the line the armed read scans and therefore what it prices.

    Human: "next turn he might evolve to opponents main attacker, mega lucario."

    **The reference moved (Issue #228).** The oracle half was `pilot._denial_at(riolu) > 30`; that
    method went with the ADR-0062 magnitude path. The same claim is read off the armed instrument's
    per-body row, on the fixture's REAL Riolu rather than a hand-built one -- the Provider has to
    resolve the attached Energy's type for the read to see anything at all, which a synthetic
    ``{"energies": ["F"]}`` body cannot supply. The board-level half below is unchanged."""
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
    """dragapult 85046350 f32 (CRITICAL) -- the CEILING on the forward credit, and the reason
    `_DENIAL_FORWARD` is a discount rather than face value.

    Their Active is a Cynthia's Gabite on 1 Energy. Priced on its own attack the strip denies 40 and
    the Hammer scores +10, which loses to the evolve (20) and the retreat-to-wall (30). Credit its
    forward form (Garchomp) at FACE VALUE and the strip denies 100, the Hammer jumps to +40, buries
    both -- and the CRITICAL comes straight back.

    Human: "We are about to KO their active, so why play Crushing hammer first?" (There is no KO this
    turn -- my Active is a 70-HP Dreepy, theirs a 100/100 Gabite; the human means the LINE, and their
    `correct` is the evolve.) The forward payoff is a turn away and contingent on them holding the
    evolution: it is worth something, but never its full face.
    """
    pilot = _pilot("dragapult_ex")
    obs = _fx("dx_hammer_forward_form_guard_f32.json")["obs"]
    hammers = _hammer_indices(pilot, obs)
    assert hammers, "fixture no longer offers a Crushing Hammer"
    chosen = pilot.explain(obs).chosen
    assert chosen[0] not in hammers, (
        f"the forward credit buried the line advance and played the Hammer {chosen} "
        f"(hammer options {hammers}) -- `_DENIAL_FORWARD` is too generous")
