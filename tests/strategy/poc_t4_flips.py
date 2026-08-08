"""The POC-T4/5 FLIP TABLE (Issue #386) — corpus frames whose DECISION moved when the composer took
the wheel. Each row is a question for a human, not a number to make green.

``REFUSAL`` means `compose` declines to model the human's option, so NO scoring change reaches the
frame; ``VALUATION`` means it priced it and ranked another above. To classify one, compose a menu
holding that option ALONE and read `gaps` — a refusal is a per-option property, and every attempt
to read it off the full menu (`apply_option` directly, membership in `.order`, re-deriving
`_frame_of`) returns a clean, plausible, WRONG answer.

`xfail(strict=True)` throughout: an XPASS is what forces a fixed frame back to a human, and an
xfail table nobody must revisit reads as coverage. The assertions still name the human's ruling.
"""
import pytest

#: ``fixture id -> (diagnosis, ruled, composer, note)``. The indices are documentation;
#: `test_the_flip_table_still_describes_real_flips` is what keeps them honest.
FLIPS = {
    # ══ REFUSAL — the seam cannot model the human's option, so no weighting reaches these ════════
    # Causes: RNG, MULTI-WRITE (`_covers`, Issue #300), UNPROVEN (`deterministic=None`).
    "ml0705_petrel_over_lillies_f27": (
        "REFUSAL", [1], [0],
        "RNG — 1227 Lillie's Determination: clause 'shuffle_own_hand_in' consults RNG, and a "
        "simulated shuffle is one sample rather than a distribution. (The first pass recorded this "
        "as a `draw` reveal; that was the bare seam's answer, not the composer's.)"),
    "ml0705_refill_undeployable_f44": (
        "REFUSAL", [0], [2],
        "RNG — 1227 Lillie's Determination, same clause and same cause as f27"),
    "dragapult_poffin_whiff_take_gust_ko_f79": (
        "VALUATION", [4], [6],
        "gust is now a closed choice transition (Issue #455), so this remains a decision-level "
        "valuation disagreement rather than a coverage ceiling"),
    "dragapult_gust_ko_over_accel_f81": (
        "VALUATION", [2], [4],
        "gust is now a closed choice transition (Issue #455); composer still takes its 2.25-prize line"),
    "pilot_cd91": (
        "VALUATION", [3], [4],
        "gust is now a closed choice transition (Issue #455), so this is no longer a seam refusal"),
    "pilot_6f14": (
        "REFUSAL", [4], [5],
        "RNG — 1223 Harlequin: clause 'shuffle_both_hands' consults RNG, the same cause as Lillie's "
        "Determination above. Two RNG cards account for three rows in this table"),
    "pilot_e1db": (
        "VALUATION", [1], [4],
        "Wally's heal/bounce is now a closed choice transition (Issue #455); this is a valuation "
        "disagreement, not an unavailable board"),

    # ══ VALUATION — the seam priced the human's option and ranked another above it ════════════════
    # ``d(...)`` in each note is a 1-ply delta, in prizes.
    "dragapult_dont_feed_draw_engine_f21": (
        "VALUATION", [1], [4],
        "don't feed the draw engine the only {D} — d(ruled) 0.0667 vs 0.0670. Three ten-thousandths "
        "of a prize decide it; this is a tie in everything but arithmetic"),
    "ml_air_balloon_on_the_active_f87": (
        "VALUATION", [0], [7],
        "a Tool attach is not an Energy attach — d(ruled) 0.0 vs 0.075"),
    "dragapult_concentrate_line_preevo_f85": (
        "VALUATION", [3], [7],
        "the corpus's first 2-stage line: a STARTED pre-evo should hold the concentrate slot. "
        "d(ruled) −0.03 — the composer prices the human's play BELOW doing nothing — vs 2.25"),
    "dp_evolve_energized_line_body_first_f82": (
        "VALUATION", [1], [2],
        "evolve the ENERGIZED line body first — d(ruled) 0.1832 vs 0.2763"),
    "pr_whether_dont_retreat_f9": (
        "VALUATION", [1], [0],
        "decline the needless retreat; the ruled option is TERMINAL (attack/end) so it is priced by "
        "terminal EV and never refused — a valuation call by construction. d(ruled) 0.0 vs 0.0622"),
    "dp_hold_evolve_until_typed_ready_f35": (
        "VALUATION", [1], [0],
        "hold the evolve until the typed Energy is ready — d(ruled) 0.075 vs 0.5923. **Re-classified "
        "from REFUSAL:** the first pass read a bare `apply_option`, which refuses card 1152's fetch "
        "clause; the composer prices it through `board_expectation`. A scoring change DOES reach "
        "this frame"),
    "dragapult_hammer_no_threat_f6": (
        "VALUATION", [2], [4],
        "don't burn the Hammer with no threat on the board — d(ruled) 0.075 vs d(composer) 0.0667. "
        "**Re-classified from REFUSAL, and the more interesting half is the numbers:** the ruled "
        "option prices HIGHER at 1 ply and still loses, so this flip is a depth effect — some "
        "later step in the composer's sequence pays for the cheaper first move. A 1-ply weight "
        "cannot fix it and a 1-ply reading cannot diagnose it"),
    "dp_evolve_the_draw_engine_f40": (
        "VALUATION", [0], [1],
        "income-ON one-shot burst: the evolve equation's own promoted TARGET (#140). d(ruled) "
        "−0.0039 vs 1.0 — the composer sees a whole prize in the alternative. Worth noting that it "
        "was promoted from a target to a pin when `evolve_value` landed, and the composer moves it "
        "back — two deciders, opposite verdicts, on a frame a human already ruled once"),
    "pr_whether_should_retreat_f37": (
        "VALUATION", [3], [2],
        "take the retreat into the finisher — d(ruled) 0.0022 vs 2.4333, the widest margin in this "
        "table"),
    "ms_fetch_one_turn_early_judge_exposure_f17": (
        "VALUATION", [5], [2],
        "don't fetch a turn early into Judge exposure — attack now. d(ruled) **2.076** vs 0.075, the "
        "THIRD specimen of `f88`'s shape and the one that makes it a pattern rather than a one-off: "
        "on all three the composer prices the human's ruling an order of magnitude higher at 1 ply "
        "and the sequence overturns it"),
    "ml0705_ultraball_starved_f17": (
        "VALUATION", [3], [2],
        "save the costly tutor while starved and developed — d(ruled) 0.0 vs 0.075. The two-card "
        "discard is now PRICED (the `shed` wiring, §4 of the packet) rather than refused, so this "
        "frame became a valuation question the moment the seam was completed"),
    "ml_dont_wake_the_giant_with_the_locking_ko_f88": (
        "VALUATION", [1], [0],
        "take the lock-free attack rather than waking the giant — and the numbers are the story: the "
        "composer prices the RULED option at **2.509** prizes and the one it plays at **0.075**, a "
        "33x gap in the ruling's favour at 1 ply. It plays the 0.075 anyway, so the whole decision "
        "is coming from what the sequence does AFTER the first step. The most expensive depth "
        "effect in this table and the one most worth a human eye"),
    "ml_lethal_retreat_boost_to_ko_f24": (
        "VALUATION", [5], [3],
        "the retreat-boost lethal line. The TIE-DEFER fires here, so the composer abstains and the "
        "tuned ladder answers [3] — this row's disagreement belongs to the ladder, not the composer, "
        "and it was already failing before the defer landed. Historically the repo's determinism "
        "tracer frame (#178): it answered [5] or [3] depending on the engine-RNG position, because "
        "the develop rung ranked simmed leaf values that were samples of a seeded shuffle. That rung "
        "is now deleted, so the answer is a property of the board again — just not the ruled one"),
    "ml_ppp_attack_transient_locked_f69": (
        "VALUATION", [1], [0],
        "**Re-classified from REFUSAL, and it is a TIE**: d(ruled) 0.0 and d(composer) 0.0. The "
        "composer has no opinion, so the tie-defer hands the turn to the tuned ladder — which picks "
        "[0], not the ruled [1]. That makes this the only surviving row whose disagreement belongs "
        "to the LADDER rather than to the composer, and the one the composer cannot be asked to fix"),
}

#: Rows RETIRED by the tie-defer (`planner._tied_first_steps`). Kept by name because a flip table
#: that only grows is one nobody trusts to have been re-measured.
RETIRED_BY_THE_TIE_DEFER = ("ml0703_develop_riolu_not_shuffle_f40",
                            "ml_dont_energize_the_supporter_tutor_f84",
                            "ml_lunar_cycle_over_inert_bench_attach_f16")

#: CORPUS RECORD frames, keyed ``(episode, frame)`` — the key `decider_lab`'s gate already uses.
#: A separate dict because `FLIPS`' guards resolve every key to a `tests/fixtures/corrections/` file.
CORPUS_RECORD_FLIPS = {
    ("83969481", 55): (
        "VALUATION", 4, [0],
        "ep83969481 f55 (wave-2 ruling): preserve the healer while a single wincon remains, then "
        "ATTACK. The composer prices the ruled attack at **2.430** prizes and the option it plays at "
        "**0.112** — the second specimen of `f88`'s shape, a 21x gap in the ruling's favour at one "
        "ply that the sequence overturns. Everything this test asserts ABOVE the decision — the "
        "insurance slot at 20.0 with deadline 1, no latency haircut, the refresh declined — still "
        "holds; only the decision moved"),
    ("83457493", 31): (
        "REFUSAL", 4, [5],
        "ep83457493 f31: the Harlequin play remains unavailable at the one-option seam because its "
        "multi-leg card shape is outside Issue #455's Boss-only gust synthesis"),
    ("85163079", 30): (
        "REFUSAL", 1, [2],
        "MULTI-WRITE — Boss's Orders again (choice key 'gust'). The loaded-equal-KO gust, the pin "
        "the `gust-for-the-loaded-equal-ko` swing gate was sized on"),
    ("86091435", 119): (
        "REFUSAL", 1, [0],
        "the human-adjudicated 2-prize drag-and-spread remains outside Issue #455's Boss-only gust "
        "synthesis, so this card shape still refuses at the one-option seam"),
}

#: Decision-level gust records reclassified by Issue #455. They are valuation work, never evidence
#: that the structural play can be safely treated as an identity transition.
GUST_RECLASSIFIED = ("dragapult_poffin_whiff_take_gust_ko_f79", "dragapult_gust_ko_over_accel_f81",
                     "pilot_cd91")

REFUSALS = {k for k, v in FLIPS.items() if v[0] == "REFUSAL"}
VALUATIONS = {k for k, v in FLIPS.items() if v[0] == "VALUATION"}


def reason(name: str) -> str:
    """Diagnosis first, so `-rx` output separates a coverage ceiling from a valuation call."""
    kind, ruled, got, note = FLIPS[name]
    tail = ("no scoring change reaches this frame" if kind == "REFUSAL"
            else "the seam priced the ruled option and the composer ranked another above it")
    return f"POC-T4/5 {kind} flip (Issue #386): ruled {ruled}, composer {got} — {note}. {tail}"


def record_reason(ep: str, fr: int) -> str:
    kind, ruled, got, note = CORPUS_RECORD_FLIPS[(ep, fr)]
    tail = ("no scoring change reaches this frame" if kind == "REFUSAL"
            else "the seam priced the ruled option and the composer ranked another above it")
    return (f"POC-T4/5 {kind} flip (Issue #386): ep{ep} f{fr}, ruled {ruled}, composer {got} — "
            f"{note}. {tail}")


def marks(name: str):
    """Callers spelled `marks(name)[0].kwargs["reason"]` raise `IndexError` AT COLLECTION once a name
    leaves the table — deliberate: a softer return would leave a stale strict xfail reading as cover."""
    if name not in FLIPS:
        return ()
    return (pytest.mark.xfail(strict=True, reason=reason(name)),)


def param(name: str, *rest, id=None):
    """The FIXTURE NAME is the first value."""
    return pytest.param(name, *rest, id=id or name, marks=marks(name))


def param_for(fixture: str, *values, id=None):
    """For parametrisations whose first column is NOT the fixture. Kept separate from `param` because
    a helper guessing which argument is the fixture eventually marks the wrong row."""
    return pytest.param(*values, id=id or fixture, marks=marks(fixture))
