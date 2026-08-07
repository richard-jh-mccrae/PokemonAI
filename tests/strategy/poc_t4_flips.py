"""The POC-T4/5 FLIP TABLE — corpus frames whose DECISION moved when the composer took the wheel.

Issue #386 swaps the rung ladder for `common.composer`'s within-turn sequence search. On most ruled
frames the agent plays the same option it did before. On these it does not, and each one is a
question for a human rather than a number to make green.

**This table is the wave-3 packet in machine-readable form.** Every row names the fixture, what the
human ruled, what the composer plays instead, and — the part that decides what to DO about it — the
DIAGNOSIS, measured at the composer's own seam rather than inferred from the score:

* ``REFUSAL`` — `compose` declines to model the human's option at all, so it is never a candidate
  the beam can commit. **No scoring change reaches these frames.** They are not rulings about
  valuation; they are the seam's coverage boundary showing up as a decision. The reason string is
  the seam's own, quoted.
* ``VALUATION`` — the seam DID price the human's option and the composer ranked something above it.
  These are the real rulings: two mechanisms looked at the same board and disagreed about what is
  worth more. ``d(ruled)`` and ``d(composer)`` are the two 1-ply deltas, in prizes.

Both are marked `xfail(strict=True)`, deliberately. Strict is what stops this becoming a graveyard:
the day a frame is ruled and the behaviour returns, the XPASS turns the suite red and someone has to
come back and promote it. An xfail table nobody is forced to revisit is worse than a deleted test,
because it looks like coverage.

The assertions themselves are NOT rewritten. Each test keeps asserting the human's `correct` option,
verbatim, because that is the ruling — the only thing this table changes is whether failing to meet
it stops the build today.

──────────────────────────────────────────────────────────────────────────────────────────────────
HOW THE DIAGNOSIS COLUMN WAS MEASURED, AND THE THREE INSTRUMENTS THAT GOT IT WRONG FIRST
──────────────────────────────────────────────────────────────────────────────────────────────────
This column was rebuilt from scratch after the first version proved to be measuring something else.
Recording the failures, because each one returned a clean, plausible, WRONG answer rather than an
error, and the next person reaching for the obvious tool will reach for the same three:

1. **A bare `apply_option` is not what the composer asks.** It REFUSES a `_PLAY` whose clauses
   reveal information; `compose` routes that exact case to `board_expectation` and PRICES it. Same
   option, same board, opposite verdicts. This produced a whole fictitious *"REVEAL family"* of
   coverage ceilings — frames that are in fact priced and outranked, i.e. rulable.
2. **`ruled_index in compose(...).order` is vacuous.** `_refuse` emits a `_Ranked` with
   ``delta=0.0``, so a refused option sits in `order` beside the priced ones. Everything came back
   PRICED, including the five that genuinely refuse.
3. **`_frame_of(option)` cannot be reconstructed by the caller.** A fixture's option dict carries no
   serials, so its frame is ``(hand None, body None)`` while the gaps `compose` emits carry real
   ones. The keys never matched, so again everything came back PRICED.

What works: a refusal is a PER-OPTION property, independent of the rest of the menu — so compose a
menu holding **that option alone** and read `gaps`. Nothing to key, nothing to match. The check
discriminates (5 REFUSED / 12 PRICED across this table), which is the positive control that says it
is looking at something.

Net correction: **3 of the 8 rows originally recorded as REFUSAL are valuation disagreements**, and
2 more had the right verdict for the wrong reason.
"""
import pytest

#: ``fixture id -> (diagnosis, ruled, composer, note)``.
#:
#: ``ruled``/``composer`` are the option indices measured on this branch. They are documentation, not
#: assertions — `test_the_flip_table_still_describes_real_flips` is what keeps them honest, and the
#: strict xfail is what catches a frame that starts agreeing again.
FLIPS = {
    # ══ REFUSAL — the seam cannot model the human's option, so no weighting reaches these ════════
    # Three distinct causes, and they are worth keeping apart because they need different work.
    #
    #   RNG          a clause consults the shuffle. One simulated sample is not a distribution, so
    #                the seam refuses rather than pricing one draw of it.
    #   MULTI-WRITE  the clause writes several zones at once and Issue #300's `_covers` refuses to
    #                model three quarters of a play.
    #   UNPROVEN     `deterministic=None` — the gate is PROOF of determinism, not its absence.
    "ml0705_petrel_over_lillies_f27": (
        "REFUSAL", [1], [0],
        "RNG — 1227 Lillie's Determination: clause 'shuffle_own_hand_in' consults RNG, and a "
        "simulated shuffle is one sample rather than a distribution. (The first pass recorded this "
        "as a `draw` reveal; that was the bare seam's answer, not the composer's.)"),
    "ml0705_refill_undeployable_f44": (
        "REFUSAL", [0], [2],
        "RNG — 1227 Lillie's Determination, same clause and same cause as f27"),
    "dragapult_poffin_whiff_take_gust_ko_f79": (
        "REFUSAL", [4], [6],
        "MULTI-WRITE — choice key 'gust': `CLAUSE_WRITES['gust']` is non-empty ({bodies_in_play, "
        "special_conditions, transient_grants}), so the structural floor is not the whole play "
        "(Issue #300 `_covers`). **This and f81 are the decision-level successors named in "
        "`test_gust.py`'s deletion note, and they do NOT carry the gust fact** — the seam cannot "
        "model a gust, so gusting has no working assertion at decision level. Recorded plainly "
        "rather than left implied by that note."),
    "dragapult_gust_ko_over_accel_f81": (
        "REFUSAL", [2], [4],
        "MULTI-WRITE — choice key 'gust', as f79. Composer takes a 2.25-prize line instead."),
    "pilot_cd91": (
        "REFUSAL", [3], [4],
        "MULTI-WRITE — choice key 'gust', a THIRD gust frame with no working assertion"),
    "pilot_6f14": (
        "REFUSAL", [4], [5],
        "RNG — 1223 Harlequin: clause 'shuffle_both_hands' consults RNG, the same cause as Lillie's "
        "Determination above. Two RNG cards account for three rows in this table"),
    "pilot_e1db": (
        "REFUSAL", [1], [4],
        "a FOURTH refusal cause: choice key 'heal' — *no board synthesis is registered for it*, so "
        "the resulting board cannot be written at all. Distinct from the other three — not RNG, not "
        "an over-broad `_covers`, not an unproven determinism gate, just an unimplemented "
        "transition. The composer takes a 3.107-prize line instead"),

    # ══ VALUATION — the seam priced the human's option and ranked another above it ════════════════
    # These are the frames where a human actually has to choose between two opinions. The two
    # numbers are the 1-ply deltas in prizes: what the composer thinks each option is worth.
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

#: Rows RETIRED from this table by the tie-defer (`planner._tied_first_steps`), 2026-08-07. Kept by
#: name because a flip table that only ever grows is one nobody trusts to have been re-measured, and
#: because each of these is evidence FOR the defer: on all three the composer's own numbers tied, the
#: structural sequencer took the turn back, and it played the human's ruling.
#:
#:   ml0703_develop_riolu_not_shuffle_f40        VALUATION  ruled [3] -> now [3]
#:   ml_dont_energize_the_supporter_tutor_f84    VALUATION  ruled [3] -> now [3]
#:   ml_lunar_cycle_over_inert_bench_attach_f16  REFUSAL    ruled [6] -> now [6]
#:
#: The third is the interesting one: a REFUSAL that resolved with no widening of the seam at all. The
#: refused option was never the problem — the composer committing a line it had no view on was.
RETIRED_BY_THE_TIE_DEFER = ("ml0703_develop_riolu_not_shuffle_f40",
                            "ml_dont_energize_the_supporter_tutor_f84",
                            "ml_lunar_cycle_over_inert_bench_attach_f16")

#: The same table for frames that live in the CORPUS RECORD rather than as a fixture file, keyed
#: ``(episode, frame) -> (diagnosis, ruled, composer, note)``. A separate dict because `FLIPS`'
#: guards resolve every key to `tests/fixtures/corrections/<name>.json` and a record frame has no
#: such file — and because these are the frames `decider_lab`'s gate already tracks by the same key,
#: so a reader can join the two without a second convention.
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
        "ep83457493 f31: the Harlequin play. The ruled option REFUSES at the seam, so no scoring "
        "change reaches this frame; both it and the composer's pick price at 0.0"),
    ("85163079", 30): (
        "REFUSAL", 1, [2],
        "MULTI-WRITE — Boss's Orders again (choice key 'gust'). The loaded-equal-KO gust, the pin "
        "the `gust-for-the-loaded-equal-ko` swing gate was sized on"),
    ("86091435", 119): (
        "REFUSAL", 1, [0],
        "MULTI-WRITE — Boss's Orders again. This one is a HUMAN-ADJUDICATED agent line, not a "
        "correction: the 2-prize drag-and-spread was ruled BETTER than the correction's 1-prize "
        "development line on 2026-07-19. So the composer is not disagreeing with a blunder report, "
        "it is unable to see a line a human explicitly endorsed"),
}

#: Every gust frame in both tables, named together because they share ONE cause and will be fixed by
#: one change. `CLAUSE_WRITES['gust']` is non-empty, so Issue #300's `_covers` refuses the whole
#: transition and no weighting reaches any of them. Five frames, and between them they are the ONLY
#: decision-level coverage the gust doctrine had: `test_gust.py`'s deletion note named two of these
#: as its successors, and they do not carry the fact. Counted here so the size of the hole is a
#: number rather than an impression.
GUST_REFUSALS = ("dragapult_poffin_whiff_take_gust_ko_f79", "dragapult_gust_ko_over_accel_f81",
                 "pilot_cd91", ("85163079", 30), ("86091435", 119))

REFUSALS = {k for k, v in FLIPS.items() if v[0] == "REFUSAL"}
VALUATIONS = {k for k, v in FLIPS.items() if v[0] == "VALUATION"}


def reason(name: str) -> str:
    """The xfail reason for a flipped fixture — diagnosis first, so a reader of `-rx` output can
    tell a coverage ceiling from a valuation call without opening this file."""
    kind, ruled, got, note = FLIPS[name]
    tail = ("no scoring change reaches this frame" if kind == "REFUSAL"
            else "the seam priced the ruled option and the composer ranked another above it")
    return f"POC-T4/5 {kind} flip (Issue #386): ruled {ruled}, composer {got} — {note}. {tail}"


def record_reason(ep: str, fr: int) -> str:
    """The xfail reason for a CORPUS RECORD flip — same shape as :func:`reason`, different key."""
    kind, ruled, got, note = CORPUS_RECORD_FLIPS[(ep, fr)]
    tail = ("no scoring change reaches this frame" if kind == "REFUSAL"
            else "the seam priced the ruled option and the composer ranked another above it")
    return (f"POC-T4/5 {kind} flip (Issue #386): ep{ep} f{fr}, ruled {ruled}, composer {got} — "
            f"{note}. {tail}")


def marks(name: str):
    """`pytest.mark.xfail(strict=True)` if this fixture is a known flip, else no marks.

    **Callers spelled `marks(name)[0].kwargs["reason"]` raise `IndexError` AT COLLECTION when the
    name leaves this table, and that is the desired behaviour rather than a rough edge.** A row
    leaves because the frame stopped flipping; the decorator that quoted it is then excusing the
    agent from a decision it now gets right, and the caller has to be visited. A softer helper — one
    returning `None`, or a no-op mark — would leave a stale `xfail(strict=True)` in place, which
    turns into an XPASS only if someone runs that file, and reads as considered coverage until then.
    A loud collection error costs one edit and cannot be missed. Three callers were updated this way
    when the tie-defer retired three rows."""
    if name not in FLIPS:
        return ()
    return (pytest.mark.xfail(strict=True, reason=reason(name)),)


def param(name: str, *rest, id=None):
    """`pytest.param` carrying the flip marks — for parametrised corpus tests where only SOME ids
    flipped, so the unflipped ones keep asserting normally. The FIXTURE NAME is the first value."""
    return pytest.param(name, *rest, id=id or name, marks=marks(name))


def param_for(fixture: str, *values, id=None):
    """`pytest.param` marked by ``fixture`` but carrying ``values`` verbatim.

    For parametrisations whose first column is NOT the fixture — `test_evolve_corpus_pin` is
    ``(agent, fixture, leg)`` — where `param` would silently drop a column and change the test's
    arity. Keeping the two helpers separate is deliberate: a marking helper that guesses which
    argument is the fixture is one that eventually marks the wrong row."""
    return pytest.param(*values, id=id or fixture, marks=marks(fixture))
