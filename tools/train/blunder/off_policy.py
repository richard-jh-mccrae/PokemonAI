"""**Is this follow-up frame gradeable at all?** — the shared off-policy detector (Issue #412).

A non-MAIN select exists because the agent played something at an earlier decision. *A follow-up
select is only gradeable if the decision that opened it was correct.* If that earlier play was
itself the blunder, the board is one the agent should never have reached, and a Correction filed on
the follow-up is not evidence about the follow-up decider — it is evidence about a board state that
should not exist. This is `retest_span`'s own doctrine (ADR-0049) — *"it stops at the first
divergence, because every later obs was produced by the line the agent originally played"* — applied
WITHIN a turn instead of across one.

**Why this module exists rather than one sweep's private helper.** The detector shipped inside
`grab_sweep.py` scoped to ctx 7, and `composer_lab.py` already reaches across to import it. 93+ of
the corpus's correction frames are non-MAIN and every sweep and gate that grades them inherits the
exposure; a second implementation per consumer is the drift ADR-0087 charges for one store over.

## The test is a DEPENDENCY test, not a same-turn test (Decision 1, ruled 2026-08-06)

Issue #412 proposed *"any ruled Correction on an earlier frame of the same episode AND turn"*, and
called that detector "sound but incomplete". Measured over the whole corpus it is **incomplete AND
over-broad**, and the over-broad half is the expensive one — it deletes evidence that is perfectly
good. `mega_starmie 81785223-39` is the clean case:

* predecessor f38 ruled *"Should play Pokégear 3.0 to dig for supporter earlier in turn"*
* follow-up f39 ruled *"Should snipe highest threat Pokemon … the only benched pokemon with energy"*

Pokégear 3.0 is `Look at the top 7 cards of your deck … reveal a Supporter` (`EN_Card_Data.csv` id
1122). It cannot touch the opponent's Bench, so the snipe ruling is fully gradeable and the
same-turn detector kills it anyway. Four more ctx-15 frames have that exact shape.

So a candidate is only ungradeable when the ruled-CORRECT predecessor play would have:

* **(a) prevented this select from opening at all** — the Ultra Ball whose search this is, ruled
  "should not have been played"; or an alternative line ending in an attack with no bench-damage
  rider, so no `DAMAGE` select is posed (`Nebula Beam` vs `Jetting Blow`, ids 1031); or
* **(b) changed a board fact the follow-up ruling NAMES** — `Boss's Orders` (id 1182,
  `Switch in 1 of your opponent's Benched Pokémon to the Active Spot`) moving the very Riolu the
  follow-up rules to snipe off the Bench.

Anything else is **orthogonal** and stays gradeable.

That test cannot be computed from the corpus: it needs the predecessor's card text and the
follow-up's prose read together. So this module SEPARATES the two halves it used to conflate —
:func:`candidates` is the mechanical scan, and :data:`RULINGS` is the human's verdict on each
candidate. A candidate nobody has ruled is `UNRULED`: reported, never silently filtered. That is the
same shape the two main-watchdog gates already use for a baseline — a ruling record, never derived
(CLAUDE.md).

## Two bugs the scan carried, both measured

* **Endorsement records were read as blunders.** 15 committed Corrections have ``chosen ==
  correct`` — the human agreeing with the play, filed as a note or a regression guard
  (`85058574-109` is an explicit *"match planner note"*). Reading one as *"an earlier decision was
  ruled wrong"* inverts its meaning. Clears one flag outright and thins two more.
* **``episode_id is None`` collided across sources.** Three ctx-17 records carry no episode: they
  come from committed engine-parity captures (`v2_ms_mirror_5000` / `_5001`), not games. Keyed
  ``(agent, None)`` they all landed in one bucket, so f82 of one trace was scanned as a predecessor
  of f100 of ANOTHER. A null episode is not an episode identity, so no predecessor relation can be
  asserted over one — see :func:`candidates`.

Neither is a judgement call; both are the detector claiming a relation the corpus does not record.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The verdicts a follow-up frame can carry. `UNRULED` is a first-class answer, not a failure: the
#: dependency test needs a human, and an instrument that guessed would manufacture exactly the
#: unfounded confidence this module exists to remove.
GRADEABLE = "GRADEABLE"
OFF_POLICY = "OFF_POLICY"
UNRULED = "UNRULED"

#: The MAIN select context. A MAIN decision is not a follow-up — nothing "opened" it — so the whole
#: doctrine is about the non-MAIN population. Spelled from `board_delta`'s vocabulary by
#: :func:`is_follow_up` rather than as a literal here.
_CONTEXT_MAIN = 0


@dataclass(frozen=True)
class Candidate:
    """One earlier ruled decision in the same turn that MIGHT invalidate a follow-up frame.

    A candidate is a *question*, never a verdict: it says the human ruled against something earlier
    in this turn, not that this frame is therefore ungradeable. :data:`RULINGS` answers it."""
    frame: int
    context: int | None
    category: str
    played: str
    should: str

    def describe(self) -> str:
        return f"f{self.frame} {self.category} ctx{self.context}"


@dataclass(frozen=True)
class Ruling:
    """The developer's verdict on ONE candidate frame, with the reason that justifies it.

    ``reason`` is mandatory and is the whole value of the record: a bare `GRADEABLE` is
    indistinguishable from a frame nobody looked at, and the reasons are what let a later reader
    check the ruling against the card text rather than re-deriving it."""
    verdict: str
    reason: str


def select_context(correction) -> int | None:
    """The Anchor select's context, read off the OBS the frame carries.

    Never off the human-written ``select_context`` label, which is prose — the same rule
    `grab_sweep._ctx7` states and for the same reason."""
    return ((getattr(correction, "obs", None) or {}).get("select") or {}).get("context")


def is_follow_up(correction) -> bool:
    """Is this frame a follow-up select — i.e. one some earlier play in the turn opened?

    A frame with no recorded context is NOT treated as a follow-up: an unknown context cannot
    establish that anything opened it, and guessing would put frames into the population this module
    is here to protect."""
    ctx = select_context(correction)
    return ctx is not None and ctx != _CONTEXT_MAIN


def endorses_the_play(correction) -> bool:
    """Does this Correction AGREE with what was played (``chosen == correct``)?

    Such a record is a note or a regression guard, not a blunder — 15 of them are committed, and
    `85058574-109` says so in its own rationale. It can never be evidence that an earlier decision
    was wrong, because it asserts the opposite. Compared as SETS: ``correct`` is a list of option
    indices whose order the human never ruled on (ADR-0086), so ``[1, 4]`` and ``[4, 1]`` are one
    ruling."""
    correct = list(getattr(correction, "correct", None) or [])
    return bool(correct) and sorted(correct) == sorted(getattr(correction, "chosen", None) or [])


def episode_index(corrections) -> dict:
    """``{(agent, episode id): [every Correction in that episode]}`` — the input the scan takes.

    Built over the whole store rather than inside a row loop because it is a property of the corpus:
    the scan asks *"did the human rule against an EARLIER decision in this same turn?"*, which no
    single frame can answer about itself."""
    by_ep: dict = {}
    for c in corrections:
        by_ep.setdefault((c.agent, c.episode_id), []).append(c)
    return by_ep


def candidates(correction, by_ep: dict) -> list[Candidate]:
    """Every earlier ruled decision in ``correction``'s own turn — the MECHANICAL half.

    Three narrowings, each closing a way the scan claimed a relation the corpus does not record:

    * **a null episode is not an episode identity.** ``episode_id is None`` means the record came
      from somewhere that has no episode — the committed parity captures — so two such records
      cannot be shown to share a game and no predecessor relation may be asserted between them.
      Returns empty rather than scanning a bucket that merges every trace file at once.
    * **an endorsement is not a blunder** (:func:`endorses_the_play`).
    * **a frame is not its own predecessor**, and neither is a later one: strictly ``of < frame``,
      same ``turn``.

    What survives is a QUESTION for :data:`RULINGS`, not an answer."""
    decision = getattr(correction, "decision", None) or {}
    frame, turn = decision.get("frame"), decision.get("turn")
    if frame is None or correction.episode_id is None:
        return []
    out = []
    for other in by_ep.get((correction.agent, correction.episode_id), ()):
        od = getattr(other, "decision", None) or {}
        of = od.get("frame")
        if of is None or of >= frame or od.get("turn") != turn:
            continue
        if endorses_the_play(other):
            continue
        out.append(Candidate(frame=of, context=select_context(other), category=other.category,
                             played=other.chosen_label or "", should=other.correct_label or ""))
    return sorted(out, key=lambda c: c.frame)


def ruling_key(correction) -> tuple:
    """``(agent, episode id, frame)`` — how :data:`RULINGS` addresses one frame.

    Deliberately NOT `gates.correction_frame_key`: that key is ADR-0049's *identity* (which folds
    scope and subject), while a ruling here is about one Anchor frame of one game and must not
    collapse a Turn-scoped record onto a Decision-scoped one."""
    return (correction.agent, correction.episode_id, (getattr(correction, "decision", None) or {}).get("frame"))


#: The developer's verdict on each candidate follow-up frame, with the reason (Issue #412).
#:
#: AUTHORED, never derived — the dependency test needs the predecessor's card text read against the
#: follow-up's prose, which no corpus scan can do. Every entry names the card or mechanic that
#: settles it so a later reader can check the ruling rather than trust it.
#:
#: An `OFF_POLICY` entry may also be recorded for a frame the SCAN cannot see, the way
#: `mega_lucario 84889011-7` needed one: nobody filed a Correction on the play that opened it, so
#: there is no earlier ruled frame to detect. That is the "incomplete" half Issue #412 documented,
#: and it is why this ledger is keyed on the frame rather than on a candidate.
#: Every entry below was ruled 2026-08-06 against Issue #412's review packet
#: (`tools/train/off_policy_census.py --review`), and every card fact cited was read from
#: `data/EN_Card_Data.csv` at ruling time rather than recalled (CLAUDE.md).
RULINGS: dict[tuple, Ruling] = {

    # ── OFF-POLICY (a): the ruled-correct play PREVENTS this select from opening ─────────────────
    ("mega_lucario", 84889011, 7): Ruling(
        OFF_POLICY,
        "Developer ruling, 2026-08-06 (Issue #406 re-grill): 'this one should not have played ultra "
        "ball in the first place. should have just placed Riolu on bench.' The scan cannot see this "
        "— no Correction was ever filed on the play that opened the select. (The select is actually "
        "posed by Poke Pad here rather than Ultra Ball; the ruling is about playing the search at "
        "all.)"),
    ("mega_starmie", 83966968, 79): Ruling(
        OFF_POLICY,
        "This ctx-3 SWITCH menu IS Boss's Orders' own select (id 1182, 'Switch in 1 of your "
        "opponent's Benched Pokemon to the Active Spot'). f78 rules that Harlequin should have been "
        "played instead of Boss's Orders, so under the correct line the select never opens."),
    ("dragapult_ex", 85045840, 14): Ruling(
        OFF_POLICY,
        "f12 rules the Ultra Ball should not have been played at all -- 'Nothing in our hand that we "
        "wish to discard, therefor should save ultra ball for another occasion' -- and this frame is "
        "that Ultra Ball's search (id 1121). No search, no menu."),
    ("mega_lucario", 83661652, 31): Ruling(
        OFF_POLICY,
        "f29 rules 'I would have saved the ultra ball a turn'; this frame is that Ultra Ball's "
        "search (id 1121)."),
    ("mega_lucario", 83661652, 30): Ruling(
        OFF_POLICY,
        "Same Ultra Ball as f31: this frame is its ctx-8 discard COST (id 1121, 'You can use this "
        "card only if you discard 2 other cards from your hand'). f29 rules the Ball should not have "
        "been played, so the cost is never paid."),
    ("mega_starmie", 82228640, 9): Ruling(
        OFF_POLICY,
        "f7 rules 'attach energy first. ultra ball is saved to find mega starmie, which we already "
        "have in hand'; this frame is that Ultra Ball's search."),
    ("mega_lucario", 84889011, 12): Ruling(
        OFF_POLICY,
        "Transitively off-policy through f7, which the developer ruled should not have been played "
        "at all (see that entry). Turn 1 diverges upstream of this frame, so the board here is one "
        "the agent should never have reached."),
    ("dragapult_ex", 83686860, 18): Ruling(
        OFF_POLICY,
        "f13 rules 'End turn' instead of playing Lillie's Determination (id 1227, 'Shuffle your hand "
        "into your deck. Then, draw 6 cards'), calling the turn a total waste. This ctx-8 discard "
        "menu IS that redrawn hand, so under the correct line the turn ends and it never exists."),
    ("mega_starmie", 82224509, 47): Ruling(
        OFF_POLICY,
        "(b) The ruling here is 'should snipe preevolution to opponents main attacker' -- Riolu, on "
        "their BENCH. f46 rules Boss's Orders should have been played on that same Riolu, and "
        "Boss's Orders (id 1182) switches it to the ACTIVE Spot. The correct line removes the very "
        "body this ruling names from the bench-snipe menu."),
    ("mega_starmie", 82749168, 38): Ruling(
        OFF_POLICY,
        "(a) f29's re-ruled rationale spells a whole alternative line ending in Nebula Beam (Mega "
        "Starmie ex, id 1031, {C}{C}{C}/210) rather than Jetting Blow. Nebula Beam carries NO "
        "bench-damage rider, so under the correct line no ctx-15 DAMAGE select is posed at all."),
    ("mega_starmie", 82754241, 45): Ruling(
        OFF_POLICY,
        "(a) f41 rules 'Attack with Turbo Flare' instead of the Crushing Hammer that was played. "
        "Turbo Flare (Cinderace, id 666) does 50 and searches up to 3 Basic Energy onto YOUR Benched "
        "Pokemon -- no opponent bench-damage rider -- and an attack ends the turn. The correct line "
        "poses no bench-snipe select."),
    ("mega_starmie", 82753102, 16): Ruling(
        OFF_POLICY,
        "(b) This ruling is about which SUPPORTER to give up ('we have a mega starmie in hand, i "
        "would have kept the lillies determination and given up the salvatore'). f9 rules Pokegear "
        "3.0 should have been played first, and Pokegear (id 1122) reveals a SUPPORTER from the top "
        "7 -- it can add a third Supporter to the hand and move the very comparison this ruling "
        "makes."),
    ("mega_lucario", 84071010, 53): Ruling(
        OFF_POLICY,
        "(b) f41 already rules 'should grab a solrock in this case ... give it a solrock to allow us "
        "to use lunatones draw ability' (Lunar Cycle, id 675, requires Solrock in play). This frame's "
        "own correct answer is Solrock again, for the same reason -- so if f41 had been played "
        "correctly the premise this ruling rests on has already been satisfied and the right answer "
        "here is not established."),
    ("dragapult_ex", 85046350, 20): Ruling(
        OFF_POLICY,
        "(b) f18 is the ctx-7 grab of the very Energy being attached at this ctx-21 frame, ruled "
        "Basic {D} -> Basic {R} ('save darkness energy for when we have Munkidori'). A different "
        "Energy type is a materially different attach decision, so the correct line changes the "
        "board fact this ruling ranks."),
    ("mega_starmie", 82224509, 31): Ruling(
        OFF_POLICY,
        "(b) The ruling ranks WHICH OF OUR BODIES receives the Energy -- 'Mega Starmie already had 3 "
        "basic energy, therefor should have attached on the other benched mon without any energy'. "
        "f29 rules an evolve should have happened instead of the attack that was taken, which puts "
        "an additional evolved body into exactly that recipient set."),

    # ── GRADEABLE: the flag is a FALSE POSITIVE; the predecessor is orthogonal ───────────────────
    # Recorded explicitly rather than left to fall out of an empty scan. A bare "no candidates" is
    # indistinguishable from a frame nobody looked at, and these frames DO have candidates -- the
    # ruling is what makes them gradeable again.
    ("mega_starmie", 81785223, 39): Ruling(
        GRADEABLE,
        "f38 rules 'Should play Pokegear 3.0 to dig for supporter earlier in turn'. Pokegear (id "
        "1122) looks at the top 7 of YOUR OWN deck for a Supporter -- it cannot touch the opponent's "
        "Bench, which is the only fact this snipe ruling names ('the only benched pokemon with "
        "energy'). Pure sequencing: the attack still fires on the same board."),
    ("mega_starmie", 81785223, 45): Ruling(
        GRADEABLE,
        "Identical shape to f39: f44 is a Pokegear 3.0 sequencing ruling, which cannot move the "
        "opponent's Bench this snipe select ranks."),
    ("mega_starmie", 85164605, 68): Ruling(
        GRADEABLE,
        "f64's ruled-CORRECT play is 'Attack with Jetting Blow' -- the very attack whose bench-snipe "
        "rider poses this select (Mega Starmie ex, id 1031, 'also does 50 damage to 1 of your "
        "opponent's Benched Pokemon'). The correct line opens this menu on the same opponent bench; "
        "the wasted Ultra Ball changed our hand, never their board."),
    ("mega_starmie", 82523811, 61): Ruling(
        GRADEABLE,
        "f59 is the same card to a different recipient (attach Basic {W} to the ACTIVE Mega Starmie "
        "rather than a benched body). Our attach target cannot move the opponent's Bench, and "
        "Jetting Blow costs {W} which the Active already carried, so the attack fires either way."),
    ("mega_starmie", 82752604, 62): Ruling(
        GRADEABLE,
        "Developer ruling, 2026-08-06: 'we are able to evolve our Staryu via the mega signal. attach "
        "energy to the new Starmie. Attack with Jetting Blow to KO active Budew and Snipe a "
        "Drakloak, either one.' f61's correct line therefore ENDS IN JETTING BLOW, whose bench rider "
        "poses this identical select -- and f61's own rationale already talks about sniping their "
        "bench. This was the one genuinely ambiguous ctx-15 frame (Jetting Blow keeps the menu, "
        "Nebula Beam would have removed it); the developer resolved it to Jetting Blow."),
    ("mega_starmie", 85164605, 48): Ruling(
        GRADEABLE,
        "Developer ruling, 2026-08-06: 'Frame discusses who to snipe, not Mega Signal v Salvatore. "
        "either way, if Staryu was played this turn, Salvatore is best, if not, Mega Signal is best "
        "because it doesnt take up the supporter play.' Both routes put the attacker into play, so "
        "the attack fires and the opponent's Bench -- the only thing this ruling ranks -- is "
        "untouched by either. The Salvatore/Mega Signal difference (id 1189 evolves onto a body, "
        "including one played this turn; id 1145 only reaches the hand) is real but is a question "
        "about f41, not about this frame."),
    ("mega_starmie", 81903490, 8): Ruling(
        GRADEABLE,
        "f5 rules Buddy-Buddy Poffin should have been played instead of attaching Ignition Energy. "
        "Poffin (id 1086) searches for up to 2 Basic Pokemon with 70 HP or less; this ruling names "
        "Mega Starmie ex, a Stage 1, which Poffin cannot remove from the deck."),
    ("mega_starmie", 81904064, 19): Ruling(
        GRADEABLE,
        "f17 is pure sequencing ('thin deck with buddy-buddy poffin typically first') -- both cards "
        "are played either way. This select is Hilda's Energy pick (id 1225, an Evolution Pokemon "
        "AND an Energy card), and Poffin removes Basic Pokemon, never Energy."),
    ("mega_starmie", 82749656, 21): Ruling(
        GRADEABLE,
        "f20 is this Ultra Ball's own ctx-8 discard COST, ruled a different pair of hand cards. Which "
        "cards leave the HAND does not change the DECK this search reads, and the ruling names the "
        "Bench and Cinderace's Turbo Flare (id 666)."),
    ("mega_starmie", 82753102, 17): Ruling(
        GRADEABLE,
        "Neither predecessor removes Staryu from the deck, which is what this ruling names. f9 is "
        "Pokegear 3.0 (id 1122, reveals a SUPPORTER only) and f16 is a hand-discard cost."),
    ("mega_lucario", 85058574, 71): Ruling(
        GRADEABLE,
        "This menu offers Fighting Gong (id 1142, an Item), so the select is Team Rocket's Petrel's "
        "Trainer search (id 1219) -- which is exactly what f69 rules SHOULD have been played. "
        "Premium Power Pro (id 1141, +30 damage this turn) touches no deck, so the menu is the same."),
    ("dragapult_ex", 83686860, 33): Ruling(
        GRADEABLE,
        "This ruling's fact is DECK CONTENTS ('we discarded 2 dreepys last turn, we know that there "
        "are no dreepys left in deck, thus choosing drakloak is a complete waste'). f29's correct "
        "play is an evolve from HAND, which cannot change what is left in the deck."),
    ("dragapult_ex", 83686860, 35): Ruling(
        GRADEABLE,
        "The ruling names only Cinderace ('must never select Cinderace, its pointless outside "
        "opening turn'), a general principle no predecessor here touches. f33's alternate grab moves "
        "one card between deck and hand and f29 is an evolve/attach swap; neither speaks to it."),
    ("dragapult_ex", 86091435, 69): Ruling(
        GRADEABLE,
        "The ruling names a full BENCH and the option to evolve Dunsparce. f60 is attach-order "
        "sequencing (Lillie's is still played), f62 is a ctx-34 ability ordering, and f68 is this "
        "Ultra Ball's own hand-discard cost -- none of the three changes the bench count."),
    ("dragapult_ex", 86091728, 47): Ruling(
        GRADEABLE,
        "f43 is a Buddy-Buddy Poffin bench pick ruled Dunsparce+Dreepy -> Budew+Dreepy. BOTH picks "
        "include the Dreepy this ruling needs ('recycle Drakloak, evolve a dreepy, then use Recon "
        "Directive'), so the correct line leaves the named fact intact."),
    ("mega_lucario", 84071010, 45): Ruling(
        GRADEABLE,
        "A general principle about discarding a spare Energy for Mega Lucario ex's Aura Jab. f41's "
        "alternate grab (Makuhita vs Solrock) does not change whether an Energy card is in hand."),
    ("dragapult_ex", 86091435, 68): Ruling(
        GRADEABLE,
        "The ruling names a Drakloak in hand and an active Dreepy to evolve ('Dont ever discard a "
        "Drakloak when it can instead just evolve our active Dreepy'). f60 is attach-order "
        "sequencing and f62 a ctx-34 ability ordering; Lillie's is played under either line and both "
        "named bodies survive it."),
    ("mega_lucario", 85058574, 121): Ruling(
        GRADEABLE,
        "An explicit multi-turn planner ruling that reasons from bodies and HP (Hariyama's Wild "
        "Press 210, Dragapult's 190 remaining, the force-8-prizes doctrine). f114 is a Poke Pad vs "
        "attach swap, which does not move any of those. Its OTHER flagged predecessor, f109, was an "
        "ENDORSEMENT (chosen == correct, an explicit 'match planer note') and no longer scans."),
    ("mega_starmie", 83116081, 21): Ruling(
        GRADEABLE,
        "This select is Turbo Flare's Energy routing (id 666, a DECK search onto our own Bench) and "
        "the ruling names bench Staryu Energy counts. f17 is Harlequin vs Lillie's Determination -- "
        "two shuffle-and-draw Supporters (ids 1223, 1227), neither of which sets those counts."),
    ("dragapult_ex", 86091435, 62): Ruling(
        GRADEABLE,
        "Whether Meowth ex's Last-Ditch Catch fires after benching it (id 1071, 'when you play this "
        "Pokemon from your hand onto your Bench') is untouched by f60's attach-before-shuffle "
        "sequencing ruling."),
}


def classify(correction, by_ep: dict) -> str:
    """`GRADEABLE` | `OFF_POLICY` | `UNRULED` for one follow-up frame.

    A recorded :data:`RULINGS` entry always wins — including on a frame the scan flags nothing for,
    which is how a developer-ruled off-policy frame the corpus cannot see is honoured. Otherwise a
    frame with candidates is `UNRULED` (a question nobody has answered) and a frame with none is
    `GRADEABLE`.

    **Never returns OFF_POLICY on its own reasoning.** The scan's output is a candidate list; only a
    human turns one into a verdict."""
    ruling = RULINGS.get(ruling_key(correction))
    if ruling is not None:
        return ruling.verdict
    return UNRULED if candidates(correction, by_ep) else GRADEABLE


def reasons(correction, by_ep: dict) -> list[str]:
    """Why this frame is not cleanly gradeable, or ``[]`` — the back-compatible string view.

    Kept because `grab_sweep` and `composer_lab` both print it, and because "is this list empty" is
    the honest question a printer asks. A `GRADEABLE` ruling returns ``[]`` even when candidates
    exist: that is the whole point of ruling one."""
    verdict = classify(correction, by_ep)
    if verdict == GRADEABLE:
        return []
    ruling = RULINGS.get(ruling_key(correction))
    if ruling is not None:
        return [f"{ruling.verdict}: {ruling.reason}"]
    return [c.describe() for c in candidates(correction, by_ep)]


def census(corrections) -> dict:
    """The per-context off-policy census — Issue #412 scope item 2, over EVERY non-MAIN context.

    ``{context: {"n", "ruled", "candidates", "off_policy", "gradeable", "unruled", "frames"}}``.
    ``frames`` holds ``(key, verdict, [Candidate])`` so a caller can print the working rather than
    the tally; a bare count is what let ctx 7 be measured and the other eleven contexts assumed."""
    by_ep = episode_index(corrections)
    out: dict = {}
    for c in corrections:
        if not is_follow_up(c):
            continue
        ctx = select_context(c)
        row = out.setdefault(ctx, {"n": 0, "ruled": 0, "candidates": 0, "off_policy": 0,
                                   "gradeable": 0, "unruled": 0, "frames": []})
        row["n"] += 1
        row["ruled"] += 1 if c.correct else 0
        found = candidates(c, by_ep)
        verdict = classify(c, by_ep)
        row["candidates"] += 1 if found else 0
        row[verdict.lower()] += 1
        row["frames"].append((ruling_key(c), verdict, found))
    return out


def control(corrections) -> dict:
    """The POSITIVE CONTROL: does the scan still fire on the ctx-7 population it was ruled on?

    *"Found nothing"* and *"my instrument is broken"* return the same empty output (CLAUDE.md), so
    any census reading is worth nothing without this. Issue #412 measured 15 of 30 ctx-7 frames
    flagged by the same-turn scan; if this comes back silent, every number this module produces is an
    artifact and must not be reported as a finding.

    Counts CANDIDATES, not verdicts, deliberately — the whole point of :data:`RULINGS` is that a
    ruled candidate stops being off-policy, so keying the control on verdicts would make it fade to
    zero exactly as the review succeeds."""
    from train.grab_sweep import _TO_HAND
    by_ep = episode_index(corrections)
    ctx7 = [c for c in corrections if select_context(c) == _TO_HAND]
    flagged = sum(1 for c in ctx7 if candidates(c, by_ep))
    return {"population": len(ctx7), "flagged": flagged,
            "healthy": bool(ctx7) and flagged > 0}
