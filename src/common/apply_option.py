"""**The apply-seam** — the closed-form hypothetical transition (POC-T4, contract frozen by POC-T0 /
Issue #259, ADR-0092 §4-T0 item 3, ADR-0098).

`apply_option(model, option)` answers *what would the board be if I did this?* — arithmetically, from
the StateModel, stepping no engine. It is what lets the Turn Planner price a play by **differencing**
(`state_value(after) − state_value(before)`) and compose a candidate sequence without spending the
2-vCPU grader budget on a forked simulation per branch.

**Still INERT AT RUNTIME, but no longer a stub.** T0 froze the option-kind table, the signatures and
the docstrings; POC-T4/1 (Issue #382) implemented the transitions, the ENGINE-RESOLVED execution path
and the parity lane that proves them; POC-T4/2 (Issue #383) added the per-OPTION footprint
(:func:`option_footprint`) and, in `common.board_expectation`, the enumeration that fills an
:class:`Expectation`'s outcome classes. Nothing in production calls this yet — the composer arms at
T4/4-5 (Issues #385/#386) — so the module ships measured and unwired.

The **arithmetic** lives one module out on both halves: `common.board_delta` for the deterministic
point transitions, `common.board_expectation` for the stochastic ones. This module stays the
CONTRACT, in one file, over plain data — which is also why :func:`apply_option`'s dispatch is
unchanged by T4/2: routing a revealing option to an Expectation is a behaviour change, and the
composer is what makes it.

Where a transition used to `raise NotImplementedError`, it now either returns a board or returns a
`Refusal` naming what it could not write. The distinction the old stub existed to protect is
unchanged and is now the transitions' own rule: **a seam that cannot model an option must never
return the model unchanged.** An identity return prices the play at exactly 0.0, which is a real and
plausible answer, so it would read as *"this play is worthless"* rather than as *"this play is
unmodelled"* — and at ordering time those are the difference between never explored and undervalued.

The arithmetic itself lives in `common.board_delta` (the closed-form observation synthesis) and
`common.apply_engine` (the one-step engine drive), so this module stays what it was designed to be:
the CONTRACT, in one file, over plain data.

## Three fates, and a silent no-op is never one of them (Issue #259 §3b, ruled 2026-08-01)

Every option on a menu resolves to exactly one fate:

* **MODELLED** — a closed-form transition from Effect Clauses. Always preferred.
* **ENGINE-RESOLVED** — the clause vocabulary has a gap, *but* the effect is **provably
  deterministic**, the board is REAL, and the call is 1-ply. Simulate through the existing
  `_search_api` seam, read the result back into a StateModel, difference normally. **Emits
  telemetry** — a bridge that makes the vocabulary gap visible for later modelling, never a resting
  place. That is why it returns an :class:`EngineResolved` wrapper rather than a bare model: the
  caller cannot use the answer without seeing that the engine produced it.
* **REFUSED** — everything else, and the composer answers a refusal by always-expanding.

## The fate is PER-OPTION, not per-kind (Issue #299, ruled 2026-08-02 — ADR-0098 Amendment C)

The kind table and the fate answer two different questions, and until Issue #299 the first one
silently decided the second:

* :data:`KIND_COVERAGE` answers *"is there a uniform board transition for this KIND?"*
* :func:`fate` answers *"can we resolve THIS option's card effect?"*

Conflating them cost the seam its two biggest levers, both measured by the POC-A2 census
(`docs/plans/apply-seam-coverage.md`):

1. **The engine bridge was pointed at the wrong kind.** `_ABILITY` was the only member of
   :data:`ENGINE_ROUTE_KINDS`, and every live `_ABILITY` option in the 372-frame corpus (17 of them)
   is Drakloak's Recon Directive or Lunatone's Lunar Cycle — both deck-reading draw engines, both
   fail-closed REFUSED. The bridge resolved **zero** live options. Meanwhile **46 refused sites** on
   MODELLED kinds carried no RNG, hidden-zone or opponent-choice marker at all — exactly the shape
   §3b calls ENGINE-RESOLVED, refused only because of the kind they sat on.
2. **Clause-complete cards were unreachable.** Drakloak, Lunatone, Dudunsparce and Fezandipiti ex
   each carry Effect Clauses covering their whole Ability, and every one routed to the engine and
   was refused there for nondeterminism. That is a routing bug, not a coverage gap.

So the resolution order is now, in one place (:func:`fate`):

    quarantined                               -> REFUSED (a parity divergence outranks all evidence)
    TERMINAL                                  -> not a fate; ask `is_terminal` (apply_option raises)
    UNDECLARED                                -> REFUSED (the vocabulary moved underneath us)
    clauses_cover is True                     -> MODELLED, whatever the kind says          (Q2)
    kind MODELLED and clauses_cover not False -> MODELLED (the structural path, unchanged)
    depth 0 + deterministic + search_api      -> ENGINE-RESOLVED, for ANY declared kind    (Q1)
    otherwise                                 -> REFUSED

**`KIND_COVERAGE` itself is unchanged** — this ruling promotes and demotes nothing, because the
composer's pruning depends on the table and §3b forbids demoting a kind without a ruling. What
changed is that the table stopped being the *gate*: the gate is now the per-option proof.

**The two new ways in are both fail-closed, and both keep ADR-0067's yield convention.** A complete
clause set (`clauses_cover=True`) is strictly better evidence than a kind-level default — it is
closed-form, deterministic in distribution, and it is what the compendium exists to provide. A
*partial* one (`False`, Issue #300's `_covers: partial` verdict) now REFUSES a kind the table calls
MODELLED, which is the whole point of declaring it: before this wiring a partial set priced as a
complete one and the uncovered leg differenced to exactly 0.

**The gate is "provably deterministic", NOT "unmodelled".** An unmodelled effect that *might* touch
RNG is REFUSED, fail-closed, per ADR-0067's yield convention — which is why ``deterministic`` is
tri-state and its `None` (unproven) default refuses. Two independent reasons, both fatal:

1. The engine has **no deal-seed**. A shuffle-riding sim returns ONE SAMPLE, not a distribution —
   exactly Issue #178's defect, and the same measurement behind ADR-0098's declined engine route
   (ml f24: 7000 / 162 / 129 / 122 / 89 / 57.5 for one first step across processes).
2. Nondeterminism breaks the deterministic replay **both gates depend on**. A frame whose decision
   depends on a coin flip cannot be ruled, so it cannot be graded, so the gate that protects it is
   vacuous.

Refused outright, therefore: opponent-choice effects (an accepted POC gap — there is no opponent
model), anything riding the shuffle, and **anything at depth ≥ 2 inside a sequence**. Depth ≥ 2 is
not a policy choice: the preceding steps were closed-form applies, so the board at that point is a
*synthesized* StateModel, and a synthesized model cannot be handed back to the native engine.

`_search_api` (`strategy/planner.py`, the seam the leaf lab injects `cgpy` into) is **preserved on
purpose**. Issue #263 retires it as a *runtime rollout*; it survives as exactly this narrow
fallback, so do not design as if it disappears.

## The seam is on the HOT path, at 1 ply, for EVERY option (amended 2026-08-01)

Issue #263's composer was amended: its beam ordering heuristic is **uniform 1-ply differencing** —
apply each candidate through this seam, score `state_value` on the result, rank by the delta. It
replaced *"the firing per-seam equations provide the local ordering"*, which left heal / fetch /
tool / stadium / draw with no local price at all, so they would have sorted to zero and been pruned
before the leaf ever saw them.

Three consequences, all of them contract rather than implementation advice:

1. **The kind table is TOTAL.** :data:`KIND_COVERAGE` classifies *every* `OptionType` member, not
   only the four kinds that appear mid-sequence, because ordering visits every option on the menu.
2. **An option this seam cannot model returns a :class:`Refusal`, never a silent no-op.** A no-op
   prices the option at exactly 0.0 delta, which at ordering time reads as *never explore this*
   rather than *this is undervalued*, and hides the gap permanently. A Refusal is visible to the
   composer, which answers it by **always-expanding** — see :func:`must_expand`, which is where that
   policy lives so no caller re-derives it.
3. **Transitions are LAZY.** A per-candidate-per-decision cost budget rules out an eager deep copy
   per branch. Transitions mutate only what the caller reads, riding the lazy StateModel of ADR-0068
   (a pure snapshot whose fields resolve on demand and whose reuse is by side, never by patch).

The measured shape of "every option kind", over the 372 corpus frames both gates read
(`data/corrections/*/corrections.jsonl`, 2026-08-01):

    MAIN menu  PLAY 699 · ATTACH 796 · EVOLVE 49 · ABILITY 17 · RETREAT 146 · ATTACK 231 · END 279
    elsewhere  CARD 507 · SKILL 2
    never seen DISCARD(11), and every YesNo / Count / Energy / attached-card kind

ABILITY is the one that makes the amendment concrete: 17 live MAIN-menu options that the pre-amendment
table did not declare at all.

## Why closed-form and not the engine

The native engine CAN fork — `search_begin` / `search_step` (`src/cg/api.py`) fork an independent
position and the Pilot already uses them live for the Lethal Solver. The fork was declined for the
POC anyway, on two measured objections (ADR-0098):

1. **Single sample, not expectation.** Past a shuffle a rollout returns one Monte-Carlo draw from the
   sim's own RNG. Measured on ml f24, 2026-07-27: the same first step scored
   7000 / 162 / 129 / 122 / 89 / 57.5 across processes.
2. **Offline invisibility — decisive.** `search_begin` needs `search_begin_input`, which exists only
   on a live agent observation: **0 of 372 gate frames** carry it (5 seeded fixtures do). A decision
   taken through an engine route is invisible to the Discrimination Gate, the Decision Gate, the leaf
   lab and the correction corpus — un-gradeable, un-rulable, un-tunable.

The engine survives as the **parity answer key**, never a runtime path: recorded native traces
(`parity-trace/1`, ADR-0059) replay one step at a time through this seam and the resulting StateModel
is diffed against the next frame's. The reference is the recorded NATIVE trace, never cgpy — checking
a hand-written model against a reimplementation that is itself only partly at parity would be
checking a model against a model.

## What this seam CANNOT do, stated rather than discovered

**It cannot capture information value.** Playing an informative card before a committing one versus
after reaches the SAME end state, so no function of that end state separates the two orderings. The
value of digging first is that later choices can *condition on what was revealed*, which appears only
when a planner evaluates a contingent policy rather than a committed sequence — and contingent-policy
planning is depth-2 search, scoped OUT of the POC by ADR-0092 (post-POC Issue #150).

So information-first sequencing stays a STRUCTURAL rule on the sound-rule whitelist
(`_finish_turn_last`'s information-before-commitment boundary, ADR-0095), and is not a defect in
this module. Recorded here because the alternative is a later track assuming the planner will
discover it, and quietly shipping an agent that commits before it digs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

# The engine's own vocabulary, never re-spelled (CLAUDE.md: option types come from `src/cg/api.py`).
# Imported through the strategy context, which is the module that already owns the DLL-free mirror of
# those enums — a second transcription here is the drift ADR-0087 charges for one store over.
from common import snapshot_coverage
from common.strategy.context import (
    _ABILITY, _ATTACH, _ATTACHED_TOOL, _ATTACK, _CARD, _DISCARD_IN_PLAY, _END, _ENERGY, _ENERGY_CARD,
    _EVOLVE, _NO, _NUMBER, _PLAY, _RETREAT, _SKILL, _SPECIAL_CONDITION, _YES,
)

# ── coverage classes ──────────────────────────────────────────────────────────────────────────────

#: This seam promises a closed-form transition for the kind. An individual option inside a modelled
#: kind may still fall to another fate — a Trainer's *effect* is per-card even though "the card
#: leaves my hand" is structural — which is why the fate is a RESULT and not only a table lookup.
MODELLED = "modelled"
#: Eligible for the engine fallback: the clause vocabulary has a gap here, so the fate depends on the
#: per-option determinism proof, the board being real, and the call being 1-ply.
ENGINE_RESOLVED = "engine-resolved"
#: Ends the turn: there is no ``model'`` at all, and the beam terminates here.
TERMINAL = "terminal"
#: Declared, and knowingly unmodelled. Ordering must always-expand it.
REFUSED = "refused"
#: Not in the table. `src/cg/api.py` says outright that *"new elements may be appended to the Enum
#: during the competition"*, so this is a live case on the grader, not a theoretical one.
UNDECLARED = "undeclared"

#: The three fates §3b resolves every option to. `TERMINAL` is not among them — a turn-ender has no
#: transition to have a fate about — and `UNDECLARED` is a refusal reason, not a fate.
FATES = (MODELLED, ENGINE_RESOLVED, REFUSED)

#: Why a particular call refused, carried on the :class:`Refusal`. The composer treats them all the
#: same way (always-expand); the coverage gate and the telemetry line do not.
#:
#: :data:`KIND_SCOPE` is **no longer emitted by** :func:`apply_option` (Issue #299). Once the engine
#: route opened to every declared non-terminal kind, "this kind has no uniform transition" stopped
#: being the reason an option refuses — the reason is whichever ENGINE precondition it missed, which
#: is the nearest miss and the actionable one. The name is kept rather than deleted because
#: :func:`coverage` still reports the table's REFUSED class, :func:`refuse` is public for T4, and a
#: scope the telemetry has already seen must not quietly change meaning.
KIND_SCOPE = "kind"              # the kind itself is unmodelled — see the note above
OPTION_SCOPE = "option"          # kind is modelled, this option's card effect is not
UNDECLARED_SCOPE = "undeclared"  # the option vocabulary grew underneath us
QUARANTINE_SCOPE = "quarantine"  # parity divergence found for this kind (ADR-0098 decision 4)
DEPTH_SCOPE = "depth"            # depth >= 2: the board is synthesized, the engine cannot take it
NONDETERMINISM_SCOPE = "nondeterminism"   # unproven or proven-not deterministic — fail closed
NO_ENGINE_SCOPE = "no-engine"    # eligible, but the caller supplied no `_search_api` seam

# ── the option-kind table ─────────────────────────────────────────────────────────────────────────

#: **Total over `OptionType`.** Every member is classified, because 1-ply ordering visits every
#: option on a live select menu — not just the kinds that appear mid-sequence.
#:
#: The default for anything not structurally transitional is :data:`REFUSED`, deliberately: a kind
#: whose whole content is a card effect (ABILITY, the YesNo activations, the Count picks) has no
#: uniform board transition to write, and declaring one anyway would be the mis-pricing this table
#: exists to prevent. T4 may promote individual kinds as the effect compendium covers them; it may
#: not demote a modelled kind without a ruling, because the composer's pruning depends on it.
KIND_COVERAGE: dict[int, str] = {
    # Structural transitions: the board change is the same shape for every card of the kind.
    _PLAY: MODELLED,             # the card leaves hand; its effect may still refuse per-option
    _ATTACH: MODELLED,           # Energy or Tool onto a body — the one irreversible per-turn spend
    _EVOLVE: MODELLED,           # body substituted in place (ADR-0070's shape)
    _RETREAT: MODELLED,          # Active swaps with a benched body
    # Turn-enders.
    _ATTACK: TERMINAL,
    _END: TERMINAL,
    # No uniform transition — the kind IS its effect. Always-expand rather than always-prune.
    _NUMBER: REFUSED,            # "how many?" — meaning belongs to the effect asking
    _YES: REFUSED,               # activate an optional effect
    _NO: REFUSED,                # declining is NOT identity: the card may still be spent
    _CARD: REFUSED,              # meaning is the SelectContext's (snipe / search / discard target)
    _ATTACHED_TOOL: REFUSED,
    _ENERGY_CARD: REFUSED,
    _ENERGY: REFUSED,
    _ABILITY: ENGINE_RESOLVED,   # 17 live MAIN options in the corpus. No uniform transition — the
                                 # kind IS its effect — but many Abilities touch no RNG and no hidden
                                 # zone, so the engine fallback can price them 1-ply while the
                                 # compendium catches up. Per-option determinism proof still gates it.
    _DISCARD_IN_PLAY: REFUSED,   # never observed in 372 frames — no evidence to model against
    _SKILL: REFUSED,             # an ORDERING of simultaneous effects, not a board transition
    _SPECIAL_CONDITION: REFUSED,
}

#: Every option kind this seam promises to transition CLOSED-FORM. **Derived**, never listed twice:
#: a hand-kept second copy is exactly the drift ADR-0087 charges for one store over.
TRANSITION_KINDS: frozenset[int] = frozenset(
    k for k, c in KIND_COVERAGE.items() if c == MODELLED)

#: Kinds the table PREFERS to send to the engine — the ones with no uniform closed-form transition
#: to fall back to.
#:
#: **This is documentation, not the gate** (Issue #299). It gated :func:`fate` until 2026-08-02;
#: since the ruling the engine route is open to every declared non-terminal kind and the gate is the
#: per-option proof (`depth == 0`, `deterministic is True`, a live ``search_api``). Membership here
#: now says only *"the kind table has no closed-form answer for this kind, so the engine is the only
#: route it will ever have"* — which is why `_ABILITY` is in it and `_PLAY` is not, even though a
#: `_PLAY` whose card effect no clause covers reaches the same route.
#:
#: Kept under its original name deliberately: it is exported and tested, and silently repurposing a
#: name that used to gate is how a later reader concludes the gate is still here. See the note beside
#: :data:`__all__`.
ENGINE_ROUTE_KINDS: frozenset[int] = frozenset(
    k for k, c in KIND_COVERAGE.items() if c == ENGINE_RESOLVED)

#: A transition that is not a transition: the turn is over, so there is no ``model'`` to return. Both
#: members END the turn (`docs/rules.md` §3 — an attack ends your turn, and it is 1 per turn), which
#: is why the planner's beam terminates on them rather than sequencing past them.
TERMINAL_KINDS: frozenset[int] = frozenset(
    k for k, c in KIND_COVERAGE.items() if c == TERMINAL)

#: Declared and knowingly unmodelled. Named so the coverage gate can report what the seam is blind
#: to, rather than that number being discoverable only by reading the table.
REFUSED_KINDS: frozenset[int] = frozenset(
    k for k, c in KIND_COVERAGE.items() if c == REFUSED)

@dataclass(frozen=True)
class Footprint:
    """Which snapshot fields a kind's transition READS and WRITES (Issue #259 §3b, 2026-08-01).

    Issue #263 consumes both to prove **commutativity** and collapse orderings into one canonical
    candidate per subset: two options commute iff neither reads what the other writes and they do not
    both write the same field. Field names come from `snapshot_coverage.WRITABLE`, one vocabulary, so
    a footprint cannot name a zone the completeness registry has never heard of.

    **Fail closed.** ``complete=False`` — unknown or partial — means the kind commutes with NOTHING.
    A footprint that under-reports is worse than none: it would license a reorder that changes the
    board, and the composer would collapse two genuinely different lines into one candidate.

    **An INCOMPLETE footprint may still carry sets, and they are a FLOOR** (Issue #304). `_PLAY` is
    the case: the zones a play touches *structurally* — decidable from the card's type alone, before
    any effect text is read — are known, while the per-card effect on top of them is not. Declaring
    the floor licenses nothing, because :func:`commutes` ignores both sets unless ``complete``; what
    it does is state what T4 must at LEAST write, so a transition that forgets the Stadium it
    displaced fails a reading rather than passing silently."""

    #: Snapshot zones the transition reads. Ignored by :func:`commutes` unless ``complete``; on an
    #: incomplete footprint they are the declared FLOOR, never an exhaustive set.
    reads: frozenset[str] = frozenset()
    #: Snapshot zones the transition writes. Ignored by :func:`commutes` unless ``complete``; on an
    #: incomplete footprint they are the declared FLOOR, never an exhaustive set.
    writes: frozenset[str] = frozenset()
    #: Is this footprint exhaustive? False (the default) is the fail-closed answer.
    complete: bool = False
    #: Does taking this option REVEAL information (draw / search / reveal)? A revealer changes the
    #: OPTION SET, not only the board, so it can never join a commutative block whatever its
    #: read/write sets say — reordering around a reveal changes what the later choices are.
    #:
    #: **No entry in :data:`FOOTPRINTS` sets it, and that is correct rather than an omission**: it is
    #: a property of the CARD, so it is armed per-option by :func:`option_footprint` off
    #: `snapshot_coverage.REVEALING_CLAUSES` (POC-T4/2, Issue #383). A KIND does not reveal; a
    #: Pokégear does.
    reveals_information: bool = False
    #: ``{(zone, serial)}`` — WHICH instances this option reads, for the zones
    #: `snapshot_coverage.ELEMENT_ZONES` declares instance-separable (developer ruling 2026-08-04,
    #: recorded in ADR-0098 Amendment D). Empty means UNRESOLVED, which conflicts: being
    #: element-level is a licence to speak instance-wise, never an obligation to.
    read_elements: frozenset[tuple[str, int]] = frozenset()
    #: ``{(zone, serial)}`` — the same for writes. A KIND has no instance, so every entry in
    #: :data:`FOOTPRINTS` leaves both empty and :func:`commutes` is unchanged by the ruling.
    #: :func:`option_footprint` is where instances exist, and therefore where the refinement lives.
    write_elements: frozenset[tuple[str, int]] = frozenset()


@dataclass(frozen=True)
class EngineResolved:
    """A transition the **engine** produced, not the clause vocabulary — the ENGINE-RESOLVED fate.

    A wrapper rather than a bare model on purpose. §3b requires this route to emit telemetry, because
    it is *a bridge that makes the vocabulary gap visible for later modelling, never a resting
    place*. Returning the model unwrapped would make the telemetry a convention every caller could
    forget; returning this makes the engine's involvement part of the value the caller must handle.

    `require_model` unwraps it; `must_expand` is False for it (it IS resolved)."""

    #: The resulting StateModel, read back from the simulated board. `None` until T4.
    model: object | None = None
    #: The engine `OptionType` this priced.
    kind: int = -1
    #: The clause-vocabulary gap that forced the fallback — what to model next. Never blank in
    #: practice; this is the telemetry payload.
    #:
    #: **It must name the CARD, not only the kind** (Issue #299). While the route was `_ABILITY`-only
    #: the kind was nearly an identifier; now that every declared non-terminal kind can reach it, a
    #: backlog line reading *"kind 7"* covers 699 corpus `_PLAY` options and is unreadable as work.
    #: The convention is ``"<card id> <card name>: <what the clause vocabulary cannot say>"``, e.g.
    #: ``"1182 Boss's Orders: no `gust` clause kind"``. Deliberately this ONE field rather than a
    #: second card field: the modelling backlog is grouped by this string, and two fields would let
    #: half of it be dropped by a caller that only filled the older one.
    clause_gap: str = ""


@dataclass(frozen=True)
class Refusal:
    """*"I cannot model this option"* — a first-class RESULT of :func:`apply_option`, not an
    exception and never a quietly-unchanged model.

    This is the amendment's load-bearing shape. Under 1-ply differencing an unmodelled option that
    returned the model unchanged would price at exactly 0.0 delta, and 0.0 sorts near the bottom of
    every menu that has a real play on it — so the composer would never explore it, and the gap
    would never surface as anything but an agent that mysteriously ignores Pokégear. A Refusal makes
    the gap a fact the composer reads and the telemetry reports."""

    #: The engine `OptionType` that was asked for.
    kind: int
    #: One of :data:`KIND_SCOPE` / :data:`OPTION_SCOPE` / :data:`UNDECLARED_SCOPE` /
    #: :data:`QUARANTINE_SCOPE` — which of the four ways this seam can be blind applies here.
    scope: str
    #: Human-readable, and destined for the telemetry line. Never blank.
    reason: str


#: Per-kind READ/WRITE footprints, in `snapshot_coverage` field vocabulary (Issue #259 §3b).
#:
#: Only three kinds carry a COMPLETE footprint: their write-set follows from the rulebook, not from
#: a card's text. Everything else defaults to the fail-closed `Footprint()` — incomplete, so it
#: commutes with nothing. `_PLAY` is the fourth closed-form kind and is deliberately INCOMPLETE: a
#: Trainer play writes whatever its Effect Clauses write, which is per-card, so the KIND cannot
#: claim a complete footprint. :func:`option_footprint` is the per-OPTION answer (POC-T4/2,
#: Issue #383) — it unions `snapshot_coverage.CLAUSE_WRITES` over the card's clauses on top of this
#: floor and arms `reveals_information` off `REVEALING_CLAUSES`. **This table is unchanged by that**,
#: and deliberately so: a KIND still cannot claim what a CARD writes, so `commutes` licenses exactly
#: what it licensed before.
#:
#: **A kind whose footprint touches an `owed` zone must not be trusted as MODELLED until that zone is
#: homed** — that is §3c's "hard, loud failure rather than a silent zero" as a rule T4 can check, via
#: :func:`footprints_writing_unhomed`. Modelling a transition whose write-set the snapshot cannot
#: hold produces a delta that under-reports, and an under-reported delta is a pruned option.
FOOTPRINTS: dict[int, Footprint] = {
    # `attached_tools` joined at T4/1 (Issue #382) and is not a widening of what the kind does — it
    # is the declaration catching up with a card type the kind always carried. A Pokémon Tool
    # *"arrives as OptionType.ATTACH exactly like an Energy"* (`common/strategy/context.py`), and it
    # writes the TOOL zone rather than the Energy one and spends no allowance. Declaring only the
    # Energy leg made this footprint under-report for every Tool equip, which is the direction
    # :class:`Footprint` calls *"worse than none"*. It changes no `commutes()` answer — `_ATTACH`
    # already conflicts with every complete footprint on `my_hand_ids` / `bodies_in_play` — and
    # `attached_tools` is HOMED, so `footprints_writing_unhomed()` stays empty.
    #
    # `damage_counters` joined for the same reason and from the same measurement: a Tool's flat HP
    # grant lands the instant it is attached, on both the current and the maximum — `ms_mirror_1000`
    # f13, Hero's Cape (1159) taking a Staryu from 70/70 to 170/170 — and `damage_counters` is the
    # zone that homes the HP read (`…active.hp_remaining`), exactly as `snapshot_coverage` already
    # reads Gravity Mountain's `hp_delta`.
    _ATTACH: Footprint(
        reads=frozenset({"my_hand_ids", "bodies_in_play", "allowance_energy_attached"}),
        writes=frozenset({"attached_energy", "attached_tools", "damage_counters", "my_hand_ids",
                          "allowance_energy_attached"}),
        complete=True),
    # `new_in_play` joined at T4/3 (Issue #391) on BOTH sides of the footprint, and each side is a
    # different sentence in `docs/rules.md` §4:
    #
    #   READ  — *"Cannot evolve a Pokémon **the turn it was played/put into play**"*. The bit is the
    #           legality input for this whole kind, which is what makes `[play Basic, evolve it]`
    #           illegal — Issue #263's own worked 2-ply sequence. Declaring the read is what lets
    #           `footprints_commute` refuse that ordering for the reason the rule gives, rather than
    #           incidentally via `my_hand_ids`.
    #   WRITE — the evolved body arrives new-in-play itself. Measured, not reasoned: `board_delta`'s
    #           `_evolve` sets `appearThisTurn: True` on the substituted body (`alakazam_9000` f127),
    #           and a COMPLETE footprint that omitted it would under-report, which
    #           :class:`Footprint` calls *worse than none*.
    #
    # It changes no `commutes()` answer: `_ATTACH` and `_RETREAT` write neither, and two `_EVOLVE`s
    # already collide on whole-zone `special_conditions`.
    #
    # ⚠️ `board_delta._evolve` does not literally look the bit up — the engine only OFFERS a legal
    # evolve, so the transition never has to re-check it. A footprint's `reads` is the state the
    # kind's legality and result DEPEND on, not the lines the Python executes; `_RETREAT` already
    # declares `allowance_retreat_used` as a read it likewise never consults. Under-declaring a read
    # is the direction that silently collapses two genuinely different lines into one candidate.
    _EVOLVE: Footprint(
        reads=frozenset({"my_hand_ids", "bodies_in_play", "new_in_play"}),
        # "Evolving keeps attached cards + damage counters; CLEARS Special Conditions and attack
        # effects" (`docs/rules.md` §4, rulebook-sourced). So this writes a zone that is still OWED —
        # which `footprints_writing_unhomed()` reports rather than letting it price 0.
        #
        # `damage_counters` joined at Issue #410: an in-play Stadium's STATIC HP delta re-reads the
        # body an evolution re-classes (Gravity Mountain's *"-30 HP"* on the Stage 2 it becomes), and
        # `damage_counters` is the zone homing the HP read — the same reading `snapshot_coverage`
        # gives `hp_delta` and the same one `_ATTACH`'s Tool grant already declares.
        writes=frozenset({"bodies_in_play", "my_hand_ids", "special_conditions", "new_in_play",
                          "damage_counters"}),
        complete=True),
    _RETREAT: Footprint(
        reads=frozenset({"bodies_in_play", "attached_energy", "allowance_retreat_used"}),
        # Also clears Special Conditions: they are cleared "when it leaves the Active spot OR
        # evolves" (`docs/rules.md` §8) — the leaving half, easy to miss because the evolve half is
        # the one the rules text puts first.
        writes=frozenset({"bodies_in_play", "attached_energy", "my_discard_contents",
                          "allowance_retreat_used", "special_conditions"}),
        complete=True),
    # `_PLAY`'s STRUCTURAL FLOOR (Issue #304), `complete=False`: everything here follows from the
    # played card's TYPE, with no effect text read. The per-card effect adds to it, which is what
    # `complete=False` says — so `commutes` still refuses `_PLAY` against everything, including
    # itself, exactly as it did when this entry was absent.
    #
    # The Stadium legs are why the entry exists at all. A Stadium REPLACES the one in play, and
    # displacing one that is hurting me is a real play the seam could not see while nothing named
    # the zone. Checked at source, not recalled:
    #
    #   `docs/rulebook.txt` L135-137 — *"A Stadium stays in play when you play it. Only one Stadium
    #     can be in play at a time—if a new one comes into play, discard the old one and end its
    #     effects. You can't play a Stadium card if a Stadium with the same name is already in
    #     play."* (The glossary at L622 restates it.)
    #   `docs/rulebook.txt` L112 — *"Play Trainer cards (as many as you want, but only one Supporter
    #     card and one Stadium card per turn)."* L138 the same.
    #   `docs/rules.md` §3 — *"Play a Stadium | **1** (and only if it differs from the one in play)"*.
    #   `docs/rulebook.txt` L78 — *"Each player has their own discard pile. Cards taken out of play
    #     go to the discard pile"*, which is why displacement writes BOTH discards: the old Stadium
    #     is discarded, and whose discard that is depends on whose Stadium it was.
    #
    # Zone by zone, and which structural sub-case of `_PLAY` each one comes from:
    #   my_hand_ids                  every play — the card leaves my hand
    #   my_discard_contents          an Item / Supporter played goes to my discard; so does my own
    #                                Stadium when I replace it
    #   their_discard_contents       displacing THEIR Stadium puts THEIR card in THEIR discard
    #   stadium                      read (is it a different name? L137) and written (the swap)
    #   allowance_stadium_played     read (spent already?) and written (spending it)
    #   allowance_supporter_played   the same pair for a Supporter play
    #   bodies_in_play               a Basic deploy puts a body on the Bench
    #   bench_occupancy              read (is the Bench full?) and written by that deploy
    #   new_in_play                  that same deploy — the body arrives NEW IN PLAY, so it cannot
    #                                evolve this turn (`docs/rules.md` §4). Written, never read: a
    #                                play's own legality does not depend on it. Joined at T4/3
    #                                (Issue #391); `board_delta._play` already set the bit and no
    #                                declaration named it.
    #   damage_counters              that same deploy AGAIN, under a Stadium whose trigger taxes it:
    #                                Risky Ruins' *"place 2 damage counters"* on a Basic non-{D}
    #                                arriving on the Bench. Joined at Issue #410 with the applier.
    #                                `stadium` is already a declared READ, which is what makes the
    #                                write conditional on the board rather than on the card.
    _PLAY: Footprint(
        reads=frozenset({"my_hand_ids", "stadium", "allowance_stadium_played",
                         "allowance_supporter_played", "bench_occupancy"}),
        writes=frozenset({"my_hand_ids", "my_discard_contents", "their_discard_contents",
                          "stadium", "allowance_stadium_played", "allowance_supporter_played",
                          "bodies_in_play", "bench_occupancy", "new_in_play", "damage_counters"}),
        complete=False),
}


def footprint(kind: int) -> Footprint:
    """This kind's footprint, or the **fail-closed default** (incomplete ⇒ commutes with nothing).

    A `dict.get` with a safe default rather than a KeyError: an option kind the table has not
    characterised must degrade to "assume it conflicts", never to a crash on the ordering path."""
    return FOOTPRINTS.get(int(kind), Footprint())


def footprints_writing_unhomed() -> dict:
    """``{kind: [owed zone ids]}`` — kinds whose transition writes state the snapshot cannot hold.

    **EMPTY since T1 (Issue #260), and that is what the finding turned into.** It was NOT empty at
    T0: `_EVOLVE` and `_RETREAT` both clear Special Conditions (`docs/rules.md` §4 and §8) and
    `special_conditions` had no snapshot home, and `_RETREAT` read and wrote a retreat allowance
    that had none either. Under differencing that is the exact §3c failure — part of what the
    transition did is invisible, so the delta under-reports, and at ordering time an under-reported
    delta is a PRUNED option.

    T1 homed both zones, so the work list this generated is done and the function survives as the
    standing check that a NEW footprint zone does not re-open it. `test_snapshot_coverage.py`
    asserts the set EMPTY, in the direction that matters: it may only ever SHRINK.

    ⚠️ **What this guard cannot reach, so no later reader trusts it further than it goes**
    (Issue #282). It is keyed on :data:`FOOTPRINTS`, which is per-KIND, and the one kind whose whole
    content is a card effect — `_PLAY` — carries only a structural FLOOR there. The per-OPTION answer
    is :func:`option_footprint` (POC-T4/2, Issue #383).
    **A card with no clauses unions to the empty set**, so a `_PLAY` whose effect the compendium has
    never heard of writes NOTHING as far as any clause walk can tell and passes here in silence. That
    is not hypothetical: Premium Power Pro (1141), Black Belt's Training (1211) and Brave Bangle
    (1175) all return `None` from `card_effects.json`, and their whole effect is the parsed
    `CardStat.damageBoost` triple. `snapshot_coverage.clauses_writing_unhomed()` has the same blind
    spot for the same reason — it walks the compendium, and these cards are not in it.

    **What DID close for those cards is one level up, and only there.** :func:`option_footprint`
    refuses to call such a footprint complete — an absent compendium entry leaves ``clauses_cover``
    at `None`, which fails closed — so the three cards commute with nothing instead of reading as
    "writes nothing, therefore conflicts with nobody". That protects the COMMUTATIVITY licence; it
    does not put a zone in any registry, so this function is exactly as blind to them as it was.

    So this function answers *"does a declared write-set name a zone with no home?"*, never *"is the
    write-set declared at all?"*. The second question belongs to the ENUMERATION
    (`snapshot_coverage.WRITABLE`, whose `this_turn_damage_boosts` entry exists because of exactly
    this gap), and a zone nobody enumerated cannot be reported by any assertion here.

    Surfaced as a function rather than a comment so T1 (Issue #260) had a generated work list and
    `test_snapshot_coverage.py` can assert the set only ever SHRINKS."""
    owed = set(snapshot_coverage.unhomed())
    out = {}
    for kind, fp in FOOTPRINTS.items():
        hit = sorted((fp.writes | fp.reads) & owed)
        if hit:
            out[kind] = hit
    return out


def footprints_commute(a: Footprint, b: Footprint) -> bool:
    """**The disjointness test itself**, over two footprints — the ONE home of Issue #263's
    commutativity rule.

    True iff **both** footprints are complete, **neither** reveals information, neither reads what
    the other writes, and they do not both write the same field. Every clause is a veto, and the
    default answer is False — an unknown footprint commutes with nothing, including itself.

    Two doors open onto this and neither re-spells it: :func:`commutes` asks it per KIND (the
    kind-table answer) and :func:`option_footprint` produces the per-OPTION footprints a caller pairs
    here. A second copy of the rule is the drift ADR-0087 charges for one store over, and it would be
    invisible — each copy would stay internally consistent while disagreeing about one pair.

    **Granularity is ELEMENT-level for the zones that hold instances** — the T0 §3b contract
    extension the developer GRANTED on 2026-08-04 (Issue #383 §B item 2, requested as a wave-packet
    ruling line on Issue #263; the ruling is recorded in ADR-0098 Amendment D). For a zone
    in `snapshot_coverage.ELEMENT_ZONES`, two writes collide only when they name the SAME instance;
    every other zone stays whole-zone, which is what keeps the spec's own required rejections:
    ``bench_occupancy`` still refuses two Basics contending for the last Bench slot, and
    ``allowance_energy_attached`` still refuses two Energy attaches.

    **Unresolved beats precise.** A footprint that names an element zone without naming an instance
    is an UNKNOWN there and conflicts with every other write to it, however precisely the other side
    named itself. That is what keeps a targetless `_RETREAT` and a whole-hand shuffle
    non-commutative, and it is why the refinement widens what can be PROVED disjoint without widening
    what is ASSUMED disjoint."""
    if not (a.complete and b.complete):
        return False
    if a.reveals_information or b.reveals_information:
        return False
    if _collides(a.reads, a.read_elements, b.writes, b.write_elements):
        return False
    if _collides(b.reads, b.read_elements, a.writes, a.write_elements):
        return False
    return not _collides(a.writes, a.write_elements, b.writes, b.write_elements)


def _collides(zones_x, elements_x, zones_y, elements_y) -> bool:
    """Do these two zone-sets touch, once element granularity is applied?

    One helper for all three of :func:`footprints_commute`'s comparisons, so the read-vs-write and
    write-vs-write questions cannot drift apart — they are the same disjointness question asked over
    different pairs of sets.

    A shared zone collides unless BOTH sides resolved it to instances AND those instances are
    disjoint. Three ways to collide, in the order they are checked: the zone is not
    instance-separable at all; one side left it unresolved; or they named the same instance."""
    for zone in zones_x & zones_y:
        if zone not in snapshot_coverage.ELEMENT_ZONES:
            return True
        here = {s for z, s in elements_x if z == zone}
        there = {s for z, s in elements_y if z == zone}
        if not here or not there or (here & there):
            return True
    return False


def commutes(kind_a: int, kind_b: int) -> bool:
    """May Issue #263 collapse these two orderings into one candidate, judging by KIND alone?

    The kind-level door onto :func:`footprints_commute`. `_PLAY` can never pass here, because a
    Trainer play writes whatever its Effect Clauses write and the KIND cannot claim a complete
    footprint for that — :func:`option_footprint` is the per-option answer."""
    return footprints_commute(footprint(kind_a), footprint(kind_b))


def option_footprint(model, option: Mapping, *, clauses_cover: bool | None = None) -> Footprint:
    """**The per-OPTION footprint** — the kind's structural floor plus this card's own clause writes
    (POC-T4/2, Issue #383; the design named at :data:`FOOTPRINTS`).

    ``clauses_cover`` is the SAME tri-state :func:`fate` takes and means the same thing:
    `True` = the card's Effect Clauses cover its whole printed effect, `False` = Issue #300's
    *partial* verdict, `None` = no compendium verdict (which includes *"this card has no printed
    effect at all"*, a distinction only the caller can make — see :func:`fate`'s closing paragraph).

    **Three fail-closed rules, each of which has already cost something somewhere:**

    1. **A card with NO clauses is UNKNOWN, never an empty write-set.** A union over no clauses is
       ``frozenset()``, which reads as *"conflicts with nobody"* and would license every reorder
       involving the card. That is not hypothetical — Premium Power Pro (1141), Black Belt's Training
       (1211) and Brave Bangle (1175) return nothing from `card_effects.json` while their whole effect
       is the parsed `CardStat.damageBoost` triple, and it is the same blind spot
       :func:`footprints_writing_unhomed` records. **An empty clause list therefore cannot be
       completed by ``clauses_cover=True`` either**, which is a real gate and not a restatement of
       the `None` one: `CardEffects.clauses_cover` returns `None` for a card it has never heard of,
       but a CALLER may pass `True` (its own join, which :func:`fate` requires it to make), and
       without this gate that would complete a footprint over the compendium's silence.
    2. **A clause value nobody declared makes the whole footprint unknown.** Contributing no zones
       and calling the result exhaustive is the under-report :class:`Footprint` calls *worse than
       none*; `snapshot_coverage.CLAUSE_WRITES` is the registry and its audit test is what catches a
       new clause kind at the source.
    3. **Every zone a clause WRITES is also declared READ.** `CLAUSE_WRITES` is a write registry and
       §3b's per-clause read-set is not shipped, so the reads are over-reported. That direction can
       only make :func:`footprints_commute` refuse a block it might have allowed; under-reporting a
       read is the direction that silently collapses two genuinely different lines into one
       candidate.

    Never raises — it runs on the ordering hot path, where a raise is a forfeited grader match over
    an option we merely could not characterise. An unresolvable card yields the kind's floor, marked
    incomplete."""
    from common.board_delta import card_clauses      # the ONE home of the clause walk
    if is_terminal(option):
        return Footprint()                    # no transition, so no footprint to have
    kind = transition_kind(option)
    base = footprint(kind)
    card = _option_card(model, option)
    clauses = card_clauses(getattr(model, "combat", None), card[0]) if card is not None else ()
    # A separate walk from `board_delta._clause_writes`, and deliberately so: that one RAISES on an
    # undeclared value, on RNG and on a reveal, because a transition that cannot write the board must
    # refuse. A footprint has no board to write — it must still DESCRIBE a revealing option, since
    # describing one is how :func:`footprints_commute` vetoes it. Same registry, opposite policies,
    # which is why the walk is not shared while the clause lookup (`card_clauses`) is.
    #
    # `clause_zones` is tracked apart from the floor so rule 3 can reach a zone the floor ALREADY
    # writes: `_PLAY` writes `bodies_in_play` structurally and declares no read of it, while a `gust`
    # clause both writes and reads it. Folding the two sets first would drop exactly that overlap.
    clause_zones, reveals, undeclared = set(), False, False
    for clause in clauses:
        for value in snapshot_coverage.clause_values(clause):
            zones = snapshot_coverage.CLAUSE_WRITES.get(value)
            if zones is None:
                undeclared = True
                continue
            clause_zones |= zones
            reveals = reveals or value in snapshot_coverage.REVEALING_CLAUSES
    # Rule 1, enforced rather than merely described: `clauses_cover is True` completes the `_PLAY`
    # floor only when there are CLAUSES for it to have covered. A caller asserting coverage over an
    # empty clause list is asserting it over the compendium's silence, and that silence is exactly
    # what makes 1141 / 1211 / 1175 read as writing nothing.
    complete = ((base.complete or (clauses_cover is True and bool(clauses)))
                and clauses_cover is not False
                and not undeclared
                and card is not None)
    # The narrowing applies to the FLOOR, and the clause union goes on TOP of the result — never the
    # other way round, or a Supporter's `gust` would have its `bodies_in_play` write stripped back off
    # by the sub-case narrowing that knows nothing about it.
    drop = _structural_drop(model, kind, card)
    reads = (set(base.reads) - drop) | clause_zones
    writes = (set(base.writes) - drop) | clause_zones
    hand_serial, body_serial = option_serials(model, option)
    body_serial = _deployed_body_serial(model, kind, card, hand_serial, body_serial)
    return Footprint(reads=frozenset(reads), writes=frozenset(writes), complete=bool(complete),
                     reveals_information=reveals,
                     read_elements=_elements(reads, hand_serial, body_serial),
                     write_elements=_elements(writes, hand_serial, body_serial))


def _elements(zones, hand_serial, body_serial) -> frozenset:
    """``{(zone, serial)}`` for the element zones this option can actually RESOLVE.

    Which serial keys which zone comes from `snapshot_coverage`'s own split
    (:data:`~common.snapshot_coverage.CARD_KEYED_ZONES` /
    :data:`~common.snapshot_coverage.BODY_KEYED_ZONES`, from which `ELEMENT_ZONES` is derived) rather
    than from a second list here — the two serials come from different halves of the option
    (``area``/``index`` vs ``inPlayArea``/``inPlayIndex``) and mixing them up would be silent: a
    footprint would still look precise while naming the wrong instance.

    A zone whose key is unavailable — a `_RETREAT` names no body, a `_PLAY` names no in-play target —
    is simply left out, which makes it *unresolved* and therefore conflicting. Silence here is the
    fail-closed answer, never an assertion that the zone is untouched."""
    out = set()
    for zone in zones & snapshot_coverage.ELEMENT_ZONES:
        serial = (hand_serial if zone in snapshot_coverage.CARD_KEYED_ZONES
                  else body_serial if zone in snapshot_coverage.BODY_KEYED_ZONES else None)
        if serial is not None:
            out.add((zone, serial))
    return frozenset(out)


def _deployed_body_serial(model, kind: int, card, hand_serial, body_serial):
    """A Basic deploy's new body carries the HAND CARD's serial, so `bodies_in_play` is resolvable
    for a `_PLAY` that names no in-play target at all.

    Read at source rather than assumed — `board_delta._play` builds the benched body as
    ``{"id": card_id, "serial": card.get("serial"), ...}`` from the very card it took out of my hand.

    **Narrow on purpose, and the narrowness is the soundness.** This fires ONLY for a Basic Pokémon.
    A Trainer's `_PLAY` also declares `bodies_in_play` in the structural floor, but a Trainer that
    moves a body moves someone ELSE's — a `gust` writes the OPPONENT's Active — so keying that write
    by my hand card's serial would be false precision, and false precision is the one direction that
    licenses a reorder which changes the board. A Trainer therefore leaves the zone UNRESOLVED, which
    conflicts.

    Without this, two Basic deploys are refused by an unresolved `bodies_in_play` rather than by
    `bench_occupancy` — still the right answer, but for the wrong reason, which would leave the
    ruling's named last-Bench-slot rejection doing no actual work. Found by mutating
    `ELEMENT_ZONES` and watching the rejection test stay green."""
    if body_serial is not None or kind != _PLAY or card is None or hand_serial is None:
        return body_serial
    stat = model.card_stat(card[0])
    is_basic = bool(getattr(stat, "is_pokemon", False)) and not getattr(stat, "evolvesFrom", None)
    return hand_serial if is_basic else None


def option_serials(model, option: Mapping):
    """``(hand card serial, targeted body serial)``, either of which may be None.

    **Public since POC-T4/4** (Issue #385), and for the reason its own ruling comment gives: the
    composer emits a block's subsets in an order the original menu did not have, so a stored option
    dict replayed from a permuted position names its card by a STALE hand index — and the failure is
    silent, because a shifted index still resolves to *a* legal card. The composer re-resolves each
    block member by the instance key this function already produces (`common.composer.resolve_against`)
    rather than re-deriving the same walk beside it, which is the drift ADR-0087 charges for one
    store over. It was private only because nothing outside this module had yet needed an option's
    instance identity.

    The engine's ``serial`` is the instance number, and it is the SAME field ADR-0091's Option
    Equivalence deliberately IGNORES. That is not a contradiction and is worth stating once: the
    fingerprint drops it because two indistinguishable bodies are ONE decision, while commutativity
    keeps it because two writes to indistinguishable bodies are still TWO writes. Same field,
    opposite questions.

    Never raises — it runs on the ordering hot path, and an unresolvable reference must degrade to
    *unresolved* (which conflicts) rather than to a crash.

    **The seat is honoured, not assumed.** An option carries `playerIndex` (the field
    `option_equivalence.option_fingerprint` reads for exactly this), and an option naming the
    OPPONENT's board must resolve to None here rather than to my own body at that index — a serial
    from the wrong side is FALSE PRECISION, which is the one direction that can license a bad
    reorder. Unreachable today (only `_ATTACH` and `_EVOLVE` carry complete footprints and both
    target my own bodies), and guarded anyway: the cost is one comparison and the failure mode is
    silent."""
    from common.option_equivalence import AREA_ACTIVE, AREA_BENCH, AREA_HAND
    obs = getattr(model, "source_obs", None) or {}
    players = ((obs.get("current") or {}).get("players")) or []
    seat = int(getattr(model, "my_index", 0))
    named = option.get("playerIndex")
    if named is not None and int(named) != seat:
        return None, None                     # the option is about THEIR board; I key nothing here
    me = players[seat] if 0 <= seat < len(players) and players[seat] else {}

    def serial_at(cards, index):
        if not isinstance(index, int) or not 0 <= index < len(cards) or not cards[index]:
            return None
        return (cards[index] or {}).get("serial")

    # A `_PLAY` names its hand index bare, with no `area` at all — the same default `_option_card`
    # takes, and the reason this cannot just filter on `area == AREA_HAND`.
    hand = serial_at(me.get("hand") or (), option.get("index")) \
        if option.get("area") in (None, AREA_HAND) else None
    area, index = option.get("inPlayArea"), option.get("inPlayIndex")
    if area == AREA_ACTIVE:
        body = serial_at(me.get("active") or (), index)
    elif area == AREA_BENCH:
        body = serial_at(me.get("bench") or (), index)
    else:
        body = None
    return hand, body


def _structural_drop(model, kind: int, card) -> frozenset:
    """Zones to DROP from the KIND's structural floor, narrowing it to the ONE sub-case this option
    actually takes.

    **Why a kind footprint over-declares at all.** `_ATTACH` and `_PLAY` each cover several sub-cases
    that never co-occur, and a KIND cannot know which one a given option is — so its entry is the
    UNION, which is the right answer for a table and the wrong one for an option. The per-OPTION
    answer can tell them apart, and it must: while `_PLAY` declared every sub-case's zones, two Basic
    deploys collided on `stadium`, both discards and two allowances that neither of them writes, so
    the last-Bench-slot rejection the 2026-08-04 ruling NAMES was never the thing doing the
    rejecting. Found by mutating `snapshot_coverage.ELEMENT_ZONES` and watching the test stay green.

    **Applied to the FLOOR only, never to the clause union.** A Supporter's `gust` writes
    `bodies_in_play`, which the Pokémon sub-case's narrowing would otherwise strip back off — so the
    caller subtracts this from ``base`` and unions the clause zones on top of the result, in that
    order. Reversing them would delete a real card effect's write.

    Every sub-case below is the write-set `common.board_delta` actually returns, read off that module
    rather than reasoned about:

    * `_ATTACH` **Tool leg** — `attached_tools` (+ `damage_counters` for a flat HP grant); spends no
      allowance, since `docs/rules.md` §3 caps only the MANUAL Energy attachment
      (*"Attach Energy from hand | **1** (manual attachment; card effects can add more)"*) and a Tool
      is an ordinary Trainer play.
    * `_ATTACH` **Energy leg** — `attached_energy` + `allowance_energy_attached`.
    * `_PLAY` **Basic Pokémon deploy** — exactly ``{"my_hand_ids", "bodies_in_play",
      "bench_occupancy", "new_in_play"}``, plus ``damage_counters``. The fourth joined at T4/3
      (Issue #391) from the same source as the other three: it is `board_delta._play`'s own returned
      write-set, and the deployed body arrives with ``appearThisTurn: True``. The fifth joined at
      Issue #410, when a Stadium bench trigger became something the seam APPLIES rather than refuses.
    * `_PLAY` **Stadium** — `my_hand_ids`, `stadium`, `allowance_stadium_played`, and whichever
      discard owned the displaced one (`docs/rulebook.txt` L78 — *"Each player has their own discard
      pile"*), so BOTH discards stay declared: which one is written depends on whose Stadium it was,
      and that is not decidable from the option.
    * **Anything else** — no narrowing at all. A Trainer's `_PLAY` has no measured structural
      write-set (`board_delta._play` refuses it outright), so the full floor stands. Fail closed.

    `damage_counters` is kept for EVERY Tool rather than only one whose `hpBonus` clears
    `applies_to_holder` — the deliberate over-report, since an extra declared write can only make
    :func:`footprints_commute` refuse a block while a missing one would license a bad reorder.

    :data:`FOOTPRINTS`'s `_ATTACH` entry is the UNION of two legs that never both fire, because a
    KIND cannot know which card is being attached. The per-OPTION answer can, and it must: without
    this split an Energy and a Tool would collide on `allowance_energy_attached` and Issue #263's own
    worked triple could not commute even under the element ruling.

    Read at source rather than inferred — `board_delta._attach` branches on `CardStat.cardType`:

    * **Tool leg** — writes `attached_tools`, plus `damage_counters` for a flat HP grant. Spends no
      allowance: `docs/rules.md` §3 caps only the MANUAL Energy attachment, and *"a Tool is an
      ordinary Trainer play with no such cap"*.
    * **Energy leg** — writes `attached_energy` and `allowance_energy_attached`.
    * Both write `my_hand_ids`.

    `damage_counters` is kept for EVERY Tool rather than only for one whose `hpBonus` clears
    `applies_to_holder`, which is the deliberate over-report: an extra declared write can only make
    :func:`footprints_commute` refuse a block, while a missing one would license a bad reorder."""
    if card is None or kind not in (_ATTACH, _PLAY):
        return frozenset()
    stat = model.card_stat(card[0])
    if stat is None:
        return frozenset()                      # unknown card — keep the union, fail closed
    floor = footprint(kind)
    everything = floor.reads | floor.writes
    if kind == _ATTACH:
        if getattr(stat, "is_tool", False):
            return frozenset({"attached_energy", "allowance_energy_attached"})
        if getattr(stat, "is_energy", False):
            return frozenset({"attached_tools", "damage_counters"})
        return frozenset()                      # neither leg — `board_delta._attach` refuses it
    # `_PLAY`, and only for the two sub-cases `board_delta._play` actually models.
    if getattr(stat, "is_pokemon", False) and not getattr(stat, "evolvesFrom", None):
        # `damage_counters` is KEPT for every deploy rather than only under a taxing Stadium, for the
        # Tool leg's reason one paragraph up: whether Risky Ruins is in play is a fact about the
        # BOARD, and this function is handed only the option and the card. An extra declared write
        # can only make `footprints_commute` refuse a block; a missing one would license a reorder
        # that changes the board (Issue #410).
        return frozenset(everything - {"my_hand_ids", "bodies_in_play", "bench_occupancy",
                                       "new_in_play", "damage_counters"})
    if getattr(stat, "is_stadium", False):
        return frozenset(everything - {"my_hand_ids", "stadium", "allowance_stadium_played",
                                       "my_discard_contents", "their_discard_contents"})
    return frozenset()                          # a Trainer play — no measured floor, so keep it all


@dataclass(frozen=True)
class OutcomeClass:
    """One branch of an :class:`Expectation` — a distinguishable result of a stochastic effect.

    Classes are enumerated by **Option Equivalence** identity (ADR-0091 fingerprints), not by card
    identity: two indistinguishable reveals are ONE outcome, so the branching factor is the number of
    decisions the reveal actually poses rather than the number of cards it could name."""

    #: Probability of this class, from `common.deck_odds` hypergeometrics. Never an engine shuffle.
    #:
    #: For a SEARCH it is an availability weight normalised over the matching pool, not a chance-node
    #: probability — the deck is revealed to the searcher, so the only chance it rides is the prize
    #: split (`common.board_expectation`'s header carries the epistemics and the consequence: a
    #: search's :meth:`Expectation.expected` is a LOWER bound on the choice node's true max).
    probability: float
    #: The resulting StateModel for this branch. Filled by `common.board_expectation.expectation`
    #: (POC-T4/2, Issue #383); `None` on a hand-built class.
    model: object | None = None
    #: The Option-Equivalence fingerprint this class collapses.
    fingerprint: tuple = ()


@dataclass(frozen=True)
class Expectation:
    """The return of a STOCHASTIC transition — a probability-weighted set of outcome classes.

    Draw-N and search-reveal do not have *a* result, they have a distribution, and the honest seam
    returns the distribution rather than a sampled representative.

    **Orderable at 1 ply, not merely expandable** (amended 2026-08-01). The composer ranks a draw
    Supporter against a Tool attach on the same scale before it decides whether to expand anything,
    so an Expectation has to yield a single comparable number on demand. An expectation shape usable
    only inside a sequence expansion would leave every draw Supporter unranked, which is the pruning
    failure the ordering amendment exists to fix.

    **Two numbers, and WHICH ONE ORDERS was settled against this docstring** (POC-T4/4, Issue #385
    §S3; amended here 2026-08-06). The 2026-08-01 text named :meth:`expected` *"the 1-ply ordering
    number"*, and that sentence predates both producing modules' own rulings — `board_expectation`'s
    header (*"For a choice node the true value is the max … The composer takes the max over
    `classes`"*, unchanged since Issue #383's first commit) and `board_choice.deferred_target`
    (*"the composer takes the max over `classes`, never `.expected()`"*). Those rule the seam's
    contract, so:

    * :meth:`best` — the **max**, and the number that ORDERS. Both producers emit CHOICE nodes: a
      deck search reveals the whole deck and the player *picks*, and a deferred target is a pick by
      construction. The value of a choice is the value of the best branch.
    * :meth:`expected` — the availability-weighted mean, kept as a reported **lower-bound
      diagnostic**. Its behaviour is unchanged.

    Both are reported per node by `tools/train/composer_lab.py`, because each is wrong in a
    different direction — `expected` under-reads a choice, `best` over-reads a 5%-likely target at
    its full value — and the GAP between them is the epistemic exposure this seam carries. Recorded
    rather than smoothed away by picking a third number nobody ruled on.

    **Branching is capped**, and this seam promises only the shape: the cap VALUE is
    `common.board_expectation.BRANCH_CAP` (POC-T4/2, Issue #383), a structural constant chosen from
    the measured post-Option-Equivalence menu-width P95 rather than a tuned strategy weight — that
    module's header carries the derivation and the cross-check against the grader's own per-decision
    floor. Whatever cap is chosen, the truncation must be REPORTED rather than silent: a capped
    enumeration that reads as a complete one is the "no silent caps" failure, and it would make an
    under-explored line look confidently valued."""

    classes: Sequence[OutcomeClass] = field(default_factory=tuple)
    #: Classes dropped by the branching cap. Non-zero means the enumeration is INCOMPLETE and the
    #: value is a lower-confidence estimate; the planner is entitled to know that.
    truncated: int = 0

    @property
    def total_probability(self) -> float:
        """Sums to 1.0 on a complete enumeration; less when ``truncated`` is non-zero. The gap IS the
        truncation, which is what makes a capped branch legible instead of merely smaller."""
        return float(sum(c.probability for c in self.classes))

    def best(self, score: Callable[[object], float]) -> float:
        """The MAXIMUM of ``score`` over the enumerated classes — **the 1-ply ordering number**.

        Both producers of an :class:`Expectation` emit a CHOICE node, and this is the value of a
        choice. `board_expectation` enumerates a search's reachable boards, and a search is not a
        chance node in the way a draw is: the player sees the whole deck and *chooses*, so
        :attr:`OutcomeClass.probability` there is an **availability weight** — *"is this target in
        the deck at all"*, `deck_odds.p_contains` — rather than a chance-node probability.
        `board_choice` enumerates a deferred target, which is a pick by construction.

        Deliberately ignores :attr:`OutcomeClass.probability`, because averaging over a set the
        chooser gets to pick from prices the choice as if it were made for them. What the weights
        DO carry — that the best branch may not be available — is real exposure and is reported
        rather than folded in: see :meth:`expected` and the class docstring's *two numbers* note.

        Raises `ValueError` on an empty enumeration, for :meth:`expected`'s reason: no classes is an
        un-enumerated effect, and 0.0 is a real answer that would read as one."""
        if not self.classes:
            raise ValueError(
                "cannot order an Expectation with no enumerated classes — that is an un-enumerated "
                "effect, and returning 0.0 would price it as a worthless one")
        return max(float(score(c.model)) for c in self.classes)

    def expected(self, score: Callable[[object], float]) -> float:
        """``score`` averaged over the enumerated classes — a reported **lower-bound diagnostic**,
        NOT the ordering number.

        :meth:`best` orders (see the class docstring). This one is kept, unchanged, because the gap
        between the two bounds is the honest measure of what an availability-weighted enumeration
        does not know, and `tools/train/composer_lab.py` emits both per node so that exposure is
        visible instead of argued about.

        **Renormalised over the enumerated mass**, i.e. the expectation CONDITIONAL on the branches
        that survived the cap. The alternative — treating truncated mass as contributing 0 — biases
        exactly against the widest enumerations, and the widest enumerations are the draw and search
        effects this amendment exists to stop pruning. `total_probability` still exposes the gap, so
        a caller that wants to discount an incomplete enumeration can; it is just not this method's
        job to do it silently.

        Raises `ValueError` on zero enumerated mass rather than returning 0.0: an Expectation with
        no classes is an un-enumerated effect, and 0.0 is a real answer that would read as one."""
        mass = self.total_probability
        if mass <= 0.0:
            raise ValueError(
                "cannot order an Expectation with no enumerated mass — that is an un-enumerated "
                "effect, and returning 0.0 would price it as a worthless one")
        return float(sum(c.probability * float(score(c.model)) for c in self.classes) / mass)


class UnsupportedTransition(NotImplementedError):
    """A caller that REQUIRED a model got a :class:`Refusal` instead — see :func:`require_model`.

    Raised only off the ordering path. The parity lane replaying a recorded native trace cannot
    proceed on a refusal: a step it cannot model is a coverage gap that must fail the run, not a
    branch to expand. The composer never sees this exception — it reads :func:`must_expand`."""


def transition_kind(option: Mapping) -> int:
    """The option's engine ``type``.

    **Never raises.** It did before the 2026-08-01 ordering amendment, when the seam was only asked
    about the four kinds that appear mid-sequence. Now every option on a live menu passes through
    here on the ordering hot path, and `src/cg/api.py` warns that the enum grows during the
    competition — so a raise here is a forfeited grader match over an option we merely could not
    price. Unrecognised kinds surface as :data:`UNDECLARED` from :func:`coverage` and as a
    :class:`Refusal` from :func:`apply_option`, which is loud in the place that can act on it."""
    return int((option or {}).get("type", -1))


def coverage(kind: int) -> str:
    """How this seam handles ``kind``: :data:`MODELLED` / :data:`ENGINE_RESOLVED` /
    :data:`TERMINAL` / :data:`REFUSED` / :data:`UNDECLARED`.

    Kind-level only — :data:`ENGINE_RESOLVED` here means *eligible*, not decided; :func:`fate` is
    what resolves an actual option, because the determinism proof, the board's realness and the ply
    depth are all properties of the call rather than of the kind.

    A quarantined kind reads as REFUSED, so quarantine and the table give ONE answer rather than the
    planner having to consult two registries and agree with itself (ADR-0098 decision 4)."""
    kind = int(kind)
    if kind in quarantined_kinds():
        return REFUSED
    return KIND_COVERAGE.get(kind, UNDECLARED)


def fate(option: Mapping, *, depth: int = 0, search_api=None, deterministic: bool | None = None,
         clauses_cover: bool | None = None, deferred_target: bool | None = None) -> str:
    """Which of §3b's three :data:`FATES` this **specific call** resolves to.

    ``depth``          — plies already applied. 0 is the live observation; ≥ 1 means the board is a
                         SYNTHESIZED StateModel, which the native engine cannot be handed.
    ``search_api``     — the `_search_api` seam (`strategy/planner.py`). Absent ⇒ no engine route.
    ``deterministic``  — the per-option proof, **tri-state**. `True` = proved to touch no RNG and no
                         hidden zone. `False` = proved otherwise. `None` = *unproven*, which refuses:
                         the gate is "provably deterministic", not "unmodelled", and ADR-0067's yield
                         convention says fail closed.
    ``clauses_cover``  — do this option's own Effect Clauses cover the WHOLE printed effect? Also
                         tri-state, from `CardEffects.clauses_cover(card_id)` over
                         `card_effects.json`'s `_covers` verdict (Issue #300): `True` full, `False`
                         partial, `None` unruled-or-absent.
    ``deferred_target``— does this option defer its target to a follow-up select AND is expansion
                         armed? `common.board_choice.has_deferred_target` joined with the caller's
                         `deferred_target_expansion` flag (POC-T4/5, Issue #392). The caller does the
                         join because the flag is deployment config and this module is pure.

    **The resolution order** (Issue #299, ADR-0098 Amendment C — see this module's header for the
    measurement behind it):

    1. TERMINAL is not a fate. Ask :func:`is_terminal` first; this reports `REFUSED` rather than
       inventing a fourth answer, and :func:`apply_option` raises.
    2. A **quarantined** kind refuses, ahead of every gate below (ADR-0098 decision 4). A parity
       divergence is a statement that the seam's model of this kind is WRONG, so no per-option
       evidence can speak over it — least of all a clause set, which is a claim about the card.
    3. UNDECLARED refuses. The engine grew a kind underneath us, so **nothing is known about it at
       all** — not even whether it has a structural half — and a clause verdict speaks for the
       card's EFFECT, never for the half of the transition the kind contributes. Fail closed, loudly.

       This is deliberately NARROWER than "any kind the table does not call MODELLED". A kind the
       table marks REFUSED is not an unknown: :data:`KIND_COVERAGE` rules that such a kind's *"whole
       content is a card effect"* — which is precisely what a complete clause set covers, and is the
       same argument that makes step 4 rescue `_ABILITY`. Refusing `_SKILL` or `_YES` on evidence
       that rescues `_ABILITY` would contradict step 4 rather than reinforce it.
    4. ``clauses_cover is True`` ⇒ **MODELLED, whatever the kind says.** A complete clause set is
       strictly better evidence than a kind-level default: closed-form, deterministic in
       distribution, and precisely what the compendium exists to provide. This is what makes
       Drakloak, Lunatone, Dudunsparce and Fezandipiti ex reachable — four `_ABILITY` cards whose
       clauses already covered the whole Ability while the kind table sent them to an engine that
       refused them for nondeterminism.
    5. A MODELLED kind stays MODELLED **unless ``clauses_cover is False``.** `False` is Issue #300's
       *partial* verdict and it now refuses, which is the entire reason that verdict was declared: a
       partial set used to price as a complete one and the uncovered leg differenced to exactly 0.
    5b. ``deferred_target is True`` ⇒ **MODELLED**, as a CHOICE node (Issue #392). It sits after the
       two MODELLED tests and before the engine ones on purpose. Placed EARLIER it would speak over
       quarantine and over Issue #300's *partial* verdict, which are statements that the seam's model
       of this option is wrong — no target enumeration can outrank those. Placed LATER it would be
       unreachable for any deferred-target option whose kind is not already MODELLED, which is the
       only population it adds: a `_RETREAT` is MODELLED at step 5 and reaches
       :func:`apply_option`'s choice branch anyway, so what this step actually buys is that a future
       deferred-target member does not have to be MODELLED-by-kind to be EXPANDED. The SHAPE, not the
       fate, is what changes — :func:`apply_option` returns an `Expectation` where it would have
       returned a `StateModel`, which is a return shape that function already declares.
    6. Otherwise the **engine route**, open to every declared non-terminal kind rather than to
       :data:`ENGINE_ROUTE_KINDS` alone: `depth == 0` **and** ``deterministic is True`` **and** a
       live ``search_api``.
    7. Otherwise REFUSED, and :func:`apply_option` carries the per-precondition scope.

    **Why ``None`` does NOT refuse at step 5.** Both falsey answers fail closed *as a clause
    verdict*, but `None` also covers *"this option has no card effect for a clause to cover"* — a
    vanilla Basic's deploy, a Basic Energy attach, a Tool attach — which is most of the pool and is
    structurally MODELLED by construction. Refusing on `None` would therefore refuse the structural
    transitions this seam exists to provide. The residue is real and belongs to the CALLER: T4 must
    pass `False`, not `None`, for a card that HAS a printed effect no clause covers. `None` from
    `CardEffects.clauses_cover` cannot tell those two apart — it is absence of a compendium entry —
    so the caller has to join it against whether the card carries effect text at all. The POC-A2
    census does exactly that (`tools/apply_seam_coverage.py:resolve`) and is the worked example."""
    kind = transition_kind(option)
    if kind in quarantined_kinds():
        return REFUSED
    how = coverage(kind)
    if how == TERMINAL or how == UNDECLARED:
        return REFUSED
    if clauses_cover is True:
        return MODELLED
    if how == MODELLED and clauses_cover is not False:
        return MODELLED
    if deferred_target is True:
        return MODELLED
    if depth >= 1:
        return REFUSED
    if deterministic is not True:
        return REFUSED
    return ENGINE_RESOLVED if search_api is not None else REFUSED


def is_terminal(option: Mapping) -> bool:
    """Does taking this option END the turn? Attack and End do (`docs/rules.md` §3).

    A terminal option has no ``model'``: the planner scores the state it was reached FROM and stops
    the beam there, rather than transitioning into a turn that no longer belongs to me."""
    return coverage(transition_kind(option)) == TERMINAL


def refuse(option: Mapping, reason: str, *, scope: str = OPTION_SCOPE) -> Refusal:
    """Build a :class:`Refusal` for ``option``.

    Public because T4 needs it from *inside* a modelled kind: "the card leaves my hand" is structural
    for every `_PLAY`, but a Trainer's effect is per-card, so a `_PLAY` of a card the effect
    compendium does not cover refuses at :data:`OPTION_SCOPE` while the kind stays modelled. One
    constructor so every refusal carries the same fields and reaches the same telemetry."""
    if not (reason or "").strip():
        raise ValueError("a Refusal must say why — it is destined for the telemetry line")
    return Refusal(kind=transition_kind(option), scope=scope, reason=reason)


def must_expand(result: object) -> bool:
    """**The ordering policy, in one place.** True when ``result`` is a :class:`Refusal`, meaning the
    composer must ALWAYS-EXPAND that option rather than prune it.

    Written as a named policy rather than left to each caller's `isinstance` check, because the
    tempting reading of a refusal at ordering time is the wrong one: an option with no price looks
    like an option with no value. It has no *estimate*; expanding is how the beam finds out."""
    return isinstance(result, Refusal)


def require_model(result: object):
    """``result`` if it is a model or an :class:`Expectation`; raise otherwise.

    Unwraps an :class:`EngineResolved` — a caller that needs the board does not care which route
    produced it, and the wrapper exists to make the route visible, not to obstruct use.

    For callers that cannot proceed on a refusal — the ADR-0098 parity lane above all, where a step
    the seam cannot model is a coverage gap that must fail the run. **The ordering path must not call
    this**; it calls :func:`must_expand` and expands."""
    if must_expand(result):
        r: Refusal = result  # type: ignore[assignment]
        raise UnsupportedTransition(
            f"option type {r.kind} refused ({r.scope}): {r.reason} — this caller requires a model")
    if isinstance(result, EngineResolved):
        return result.model
    return result


def apply_option(model, option: Mapping, *, depth: int = 0, search_api=None,
                 deterministic: bool | None = None, clauses_cover: bool | None = None,
                 expand_deferred_targets: bool = False):
    """The board after taking ``option``.

    Returns one of four shapes:

    * a new `StateModel` for a deterministic closed-form transition (the MODELLED fate);
    * an :class:`Expectation` over outcome classes for a stochastic one;
    * an :class:`EngineResolved` wrapping the model the engine produced (the ENGINE-RESOLVED fate);
    * a :class:`Refusal` — **never a silently unchanged model**, because that prices the option at
      0.0 delta and buries the gap (see :class:`Refusal`).

    ``depth`` / ``search_api`` / ``deterministic`` gate the engine route; ``clauses_cover`` decides
    the MODELLED half. :func:`fate` owns the resolution order and the reason for each step — this
    function mirrors it exactly and adds only the refusal SCOPES, which are the work each refusal
    names.

    **Lazy, never an eager deep copy.** 1-ply ordering runs this once per candidate per decision, so
    a transition materialises only the fields the caller reads, riding the lazy pure snapshot of
    ADR-0068. Never mutates ``model``: the planner holds the pre-state while it evaluates
    alternatives, and a transition that edited in place would corrupt every sibling branch.

    Raises `ValueError` for a TERMINAL option — attack and end-turn have no successor state, and
    silently returning the unchanged model would let a beam sequence actions past the end of the
    turn. Callers test `is_terminal` first; that is the contract. (A terminal option is an API
    misuse, not a modelling gap, which is why it raises where a gap refuses.)

    **The MODELLED transition may still refuse, at :data:`OPTION_SCOPE`** (POC-T4/1, Issue #382).
    The fate answers *"is this option's card effect resolvable?"*; the transition answers *"can the
    seam WRITE the resulting board?"*, and those are different questions for a kind whose structural
    half is uniform. A Supporter's `_PLAY` is the worked case: the card leaving my hand is structural
    for every play, but the effect IS the play, and the engine does not even move the card to the
    discard on the same step when the effect opens a select. `common.board_delta` names what it
    cannot write, and the refusal carries that sentence to the telemetry line.

    **Quarantine** (ADR-0098 decision 4): when the parity lane finds a divergence for an option kind,
    that kind is marked unverified and refuses here, so the planner degrades to always-expand and the
    telemetry names the kind. A parity failure therefore DEGRADES the agent visibly rather than
    silently mis-playing it.

    **``expand_deferred_targets`` opts into the CHOICE node** (POC-T4/5, Issue #392), and ships OFF —
    `runtime.PROFILE["deferred_target_expansion"]` is False until Issue #385's composer arms it. A
    parameter rather than a module-level read because this module is pure and the flag is deployment
    config, and DEFAULT-OFF because the ADR-0098 parity lane and both ADR-0072 gates must keep seeing
    the seam they saw at Issue #382: with it off, a `_RETREAT` still resolves through
    `board_delta._retreat` to the allowance-only point transition the recorded native trace shows.

    With it ON, an option whose target is deferred to a follow-up select returns an `Expectation` over
    the boards that target can reach — and **never falls back** to the point transition on a refusal.
    The fallback is the whole defect: a retreat's point delta is the allowance bit alone, which prices
    at ~0.0 and reads at ordering time as *never explore this*. A `Refusal` is the honest answer,
    because it is the always-expand path."""
    kind = transition_kind(option)
    if kind in quarantined_kinds():
        return refuse(option, f"option kind {kind} is quarantined by the parity lane",
                      scope=QUARANTINE_SCOPE)
    how = coverage(kind)
    if how == TERMINAL:
        raise ValueError(
            "attack and end-turn are TERMINAL — they end the turn, so there is no successor state; "
            "test `is_terminal(option)` before calling")
    if how == UNDECLARED:
        return refuse(option, f"option kind {kind} is not in the seam's coverage table",
                      scope=UNDECLARED_SCOPE)
    # Is this a CHOICE node? Asked once, here, and threaded into `fate` so the two cannot disagree
    # about the same option — the census mirrors `fate` while the composer calls this function, which
    # is exactly the shape where a second answer would be invisible.
    deferred = False
    if expand_deferred_targets:
        from common import board_choice
        deferred = board_choice.has_deferred_target(
            model, option, seat_index=int(getattr(model, "my_index", 0)))
    # The FATE is `fate`'s to decide — asked ONCE, never re-derived. A second copy of the resolution
    # order here is the drift ADR-0087 charges for one store over, and it would be invisible: the
    # census mirrors `fate` while the composer calls this, so a disagreement would price the same
    # option two ways with nothing to say so. What this function adds is only the SCOPE.
    resolved = fate(option, depth=depth, search_api=search_api, deterministic=deterministic,
                    clauses_cover=clauses_cover, deferred_target=deferred or None)
    if resolved == REFUSED:
        # Quarantine, TERMINAL and UNDECLARED already returned above, so a refusal here is an ENGINE
        # precondition — and exactly which one is the work owed. Each gets its OWN scope, because the
        # coverage report needs to tell "we never proved this deterministic" from "the caller wired
        # no engine" from "we were two plies deep": three different pieces of work.
        if depth >= 1:
            return refuse(
                option,
                f"depth {depth}: the board is a synthesized StateModel from a prior closed-form "
                f"apply, and a synthesized model cannot be handed back to the native engine",
                scope=DEPTH_SCOPE)
        if deterministic is not True:
            return refuse(
                option,
                "not PROVABLY deterministic (`deterministic=%r`) — the gate is proof, not absence of "
                "a model: the engine has no deal-seed, so a shuffle-riding sim is one sample rather "
                "than a distribution, and nondeterminism breaks the replay both gates depend on"
                % (deterministic,),
                scope=NONDETERMINISM_SCOPE)
        if search_api is None:
            return refuse(option, "no `_search_api` seam supplied, so there is no engine to resolve "
                                  "through", scope=NO_ENGINE_SCOPE)
    if resolved == ENGINE_RESOLVED:
        from common import apply_engine
        after = apply_engine.resolve(model, option, search_api=search_api)
        if after is None:
            return refuse(
                option,
                "the engine route was eligible but produced no board — the observation carries no "
                "`search_begin_input` (0 of 372 gate frames do), the option is not on this menu, or "
                "the engine raised",
                scope=NO_ENGINE_SCOPE)
        return EngineResolved(model=after, kind=kind, clause_gap=_clause_gap(model, option))
    if deferred:
        return _choice(model, option)
    return _modelled(model, option)


def _choice(model, option: Mapping):
    """The CHOICE node: an `Expectation` over the boards this option's deferred target can reach.

    `common.board_choice` owns the arithmetic, exactly as `common.board_delta` does for
    :func:`_modelled` — so this function contributes no card or rule knowledge of its own and
    `tools/train/choice_parity.py` has exactly one thing to diff.

    A refusal is returned as a `Refusal` at :data:`OPTION_SCOPE` and **never as the point transition**:
    the fate has already ruled this option a choice node, and quietly answering with the board the
    engine's own step produced would hand the composer the ~0.0 allowance-only delta this node exists
    to replace — an option with no value, where what we have is an option with no estimate."""
    # Imported inside the body for :func:`_modelled`'s own reason — `board_delta` and `board_choice`
    # both import the contract shapes from here, so a module-level import would be a cycle.
    from common import board_choice
    from common.board_delta import Unmodellable
    try:
        return board_choice.deferred_target(model, option)
    except Unmodellable as gap:
        return refuse(option, str(gap))


def _modelled(model, option: Mapping):
    """The closed-form transition: synthesize the post-action observation, then build a FRESH model.

    Fresh rather than patched, for the memo-staleness reason `StateModel.rebuilt` spells out —
    ``state_value`` caches its per-family dict on the model and nothing invalidates that key. The
    rules arithmetic is `common.board_delta`'s, so this function contributes no card or rule
    knowledge of its own and the parity lane has exactly one thing to diff.

    Their side is REUSED when the synthesis never reached across the table, which is most of the
    time: the delta reports that from what it actually wrote, rather than the caller re-deriving it
    from a hash of the result."""
    from common import board_delta
    obs = getattr(model, "source_obs", None)
    if not obs:
        return refuse(option, "the model carries no source observation to transition from — it was "
                              "constructed directly rather than through `StateModel.build`")
    context = ((obs.get("select") or {}).get("context"))
    try:
        delta = board_delta.transition(obs, option, seat_index=getattr(model, "my_index", 0),
                                       combat=model.combat, context=context)
    except board_delta.Unmodellable as gap:
        return refuse(option, str(gap))
    return model.rebuilt(delta.obs, reuse_their_side=delta.shares_opponent)


def _clause_gap(model, option: Mapping) -> str:
    """The ENGINE-RESOLVED telemetry line: ``"<card id> <card name>: <what the vocabulary cannot
    say>"``.

    It must name the CARD (Issue #299): with the route open to every declared non-terminal kind, a
    backlog line reading *"kind 7"* covers 699 corpus `_PLAY` options at once and is unreadable as
    work. The card is resolved through the option's own zone references — the same
    ``(area, index)`` / ``(inPlayArea, inPlayIndex)`` pair `common.option_equivalence` fingerprints —
    so an option shape that carries no resolvable reference degrades to naming the kind, which is
    strictly better than naming nothing."""
    card = _option_card(model, option)
    kind = transition_kind(option)
    if card is None:
        return (f"option kind {kind}: no Effect Clause covers this option's card effect, so the "
                f"engine resolved it")
    cid, name = card
    return f"{cid} {name}: no Effect Clause covers this effect, so the engine resolved it"


def _option_card(model, option: Mapping):
    """``(card id, card name)`` for the card an option names, or None.

    Prefers the HAND reference (the card being played/attached/evolved into) over the in-play one,
    because that is the card whose effect the vocabulary is missing. A `_PLAY` names its hand index
    bare, with no ``area`` at all, which is why the first pass defaults to the hand rather than
    skipping. Never raises: it runs on the telemetry path of the ordering hot loop."""
    from common.option_equivalence import AREA_ACTIVE, AREA_BENCH, AREA_DISCARD, AREA_HAND
    obs = getattr(model, "source_obs", None) or {}
    players = ((obs.get("current") or {}).get("players")) or []
    seat = int(getattr(model, "my_index", 0))
    me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    zones = {AREA_HAND: "hand", AREA_DISCARD: "discard",
             AREA_ACTIVE: "active", AREA_BENCH: "bench"}
    for area_key, index_key in (("area", "index"), ("inPlayArea", "inPlayIndex")):
        area = option.get(area_key)
        index = option.get(index_key)
        zone = zones.get(area) if area is not None else ("hand" if area_key == "area" else None)
        if zone is None or not isinstance(index, int) or index < 0:
            continue
        cards = me.get(zone) or ()
        if index >= len(cards) or not cards[index]:
            continue
        cid = cards[index].get("id")
        stat = model.card_stat(cid)
        return cid, (getattr(stat, "name", None) or "?")
    return None


#: Option kinds the parity lane has found diverging. **Empty, and that is a MEASUREMENT** — the lane
#: over the committed 377-trace corpus replays every modelled kind divergence-free
#: (`tests/parity/test_apply_seam_parity.py`). It is a ruling record, not a scratch pad: an entry is
#: added only with the divergence filed, exactly as a gate baseline is only re-captured on a verdict.
QUARANTINED_KINDS: frozenset[int] = frozenset()


def quarantined_kinds() -> frozenset[int]:
    """Option kinds the parity lane has found diverging — the planner must not enumerate through
    these (ADR-0098 decision 4).

    Reads :data:`QUARANTINED_KINDS`, which the lane's findings populate. The registry lives here
    rather than in the planner because the seam is what diverges: the planner is one consumer of that
    fact, and a second consumer (the coverage gate's report, the telemetry line) must read the same
    answer.

    **Telemetry is not optional.** A quarantined kind must be named, with its reason, wherever the
    agent reports what it did — a degraded agent that looks merely bad is indistinguishable from a
    broken one, and the whole point of quarantine is that the difference is visible.

    **Two names for two jobs**, which is why this is a function over a constant rather than either
    alone: :data:`QUARANTINED_KINDS` is the RULING RECORD — the data a human edits when a divergence
    is filed — while this is the READ every consumer makes, and a read is what a test can
    `monkeypatch` to exercise the degraded path without touching a ruling record. Both are exported
    for that reason, not by oversight."""
    return QUARANTINED_KINDS


# Two exported names changed MEANING in Issue #299 without changing spelling, and both are called
# out here as well as at their definitions, because `__all__` is where an importer looks first:
#
#   `ENGINE_ROUTE_KINDS` no longer GATES the engine route — it documents which kinds the table has no
#     closed-form answer for. The gate is the per-option proof in `fate`.
#   `KIND_SCOPE` is no longer EMITTED by `apply_option`, for the same reason: the kind table stopped
#     deciding fates, so a refusal names the engine precondition it missed instead.
__all__: Sequence[str] = (
    "MODELLED", "ENGINE_RESOLVED", "TERMINAL", "REFUSED", "UNDECLARED", "FATES",
    "KIND_SCOPE", "OPTION_SCOPE", "UNDECLARED_SCOPE", "QUARANTINE_SCOPE", "DEPTH_SCOPE",
    "NONDETERMINISM_SCOPE", "NO_ENGINE_SCOPE",
    "KIND_COVERAGE", "TERMINAL_KINDS", "TRANSITION_KINDS", "ENGINE_ROUTE_KINDS", "REFUSED_KINDS",
    "Footprint", "FOOTPRINTS", "footprint", "commutes", "footprints_commute", "option_footprint",
    "option_serials",
    "EngineResolved", "Refusal", "OutcomeClass", "Expectation", "UnsupportedTransition",
    "transition_kind", "coverage", "fate", "is_terminal", "refuse", "must_expand", "require_model",
    "apply_option", "quarantined_kinds", "QUARANTINED_KINDS",
)
