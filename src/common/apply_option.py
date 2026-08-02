"""**The apply-seam** — the closed-form hypothetical transition (POC-T4, contract frozen by POC-T0 /
Issue #259, ADR-0092 §4-T0 item 3, ADR-0098).

`apply_option(model, option)` answers *what would the board be if I did this?* — arithmetically, from
the StateModel, stepping no engine. It is what lets the Turn Planner price a play by **differencing**
(`state_value(after) − state_value(before)`) and compose a candidate sequence without spending the
2-vCPU grader budget on a forked simulation per branch.

**INERT.** T0 ships the option-kind table, the signatures and the docstrings; T4 (Issue #263)
implements the transitions. Every modelled transition raises `NotImplementedError` rather than
returning the model unchanged — an identity stub would price every play at exactly 0.0, which is a
real and plausible answer, so an unimplemented build would read as "this play is worthless" rather
than as "this play is unimplemented".

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
KIND_SCOPE = "kind"              # the kind itself is unmodelled
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

#: Kinds ELIGIBLE for the engine fallback. Eligibility is not the fate: the per-option determinism
#: proof, a real board and a 1-ply call all still have to hold, or the option refuses.
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
    board, and the composer would collapse two genuinely different lines into one candidate."""

    #: Snapshot zones the transition reads. Meaningless unless ``complete``.
    reads: frozenset[str] = frozenset()
    #: Snapshot zones the transition writes. Meaningless unless ``complete``.
    writes: frozenset[str] = frozenset()
    #: Is this footprint exhaustive? False (the default) is the fail-closed answer.
    complete: bool = False
    #: Does taking this option REVEAL information (draw / search / reveal)? A revealer changes the
    #: OPTION SET, not only the board, so it can never join a commutative block whatever its
    #: read/write sets say — reordering around a reveal changes what the later choices are.
    reveals_information: bool = False


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
#: Only the four closed-form kinds carry a complete footprint: their write-set follows from the
#: rulebook, not from a card's text. Everything else defaults to the fail-closed `Footprint()` —
#: incomplete, so it commutes with nothing — and `_PLAY` is the one that matters: a Trainer play
#: writes whatever its Effect Clauses write, which is per-card, so the KIND cannot claim a complete
#: footprint even though its structural half (the card leaves hand) is known. T4 supplies the
#: per-option footprint by unioning `snapshot_coverage.CLAUSE_WRITES` over the card's clauses.
#:
#: **A kind whose footprint touches an `owed` zone must not be trusted as MODELLED until that zone is
#: homed** — that is §3c's "hard, loud failure rather than a silent zero" as a rule T4 can check, via
#: :func:`footprints_writing_unhomed`. Modelling a transition whose write-set the snapshot cannot
#: hold produces a delta that under-reports, and an under-reported delta is a pruned option.
FOOTPRINTS: dict[int, Footprint] = {
    _ATTACH: Footprint(
        reads=frozenset({"my_hand_ids", "bodies_in_play", "allowance_energy_attached"}),
        writes=frozenset({"attached_energy", "my_hand_ids", "allowance_energy_attached"}),
        complete=True),
    _EVOLVE: Footprint(
        reads=frozenset({"my_hand_ids", "bodies_in_play"}),
        # "Evolving keeps attached cards + damage counters; CLEARS Special Conditions and attack
        # effects" (`docs/rules.md` §4, rulebook-sourced). So this writes a zone that is still OWED —
        # which `footprints_writing_unhomed()` reports rather than letting it price 0.
        writes=frozenset({"bodies_in_play", "my_hand_ids", "special_conditions"}),
        complete=True),
    _RETREAT: Footprint(
        reads=frozenset({"bodies_in_play", "attached_energy", "allowance_retreat_used"}),
        # Also clears Special Conditions: they are cleared "when it leaves the Active spot OR
        # evolves" (`docs/rules.md` §8) — the leaving half, easy to miss because the evolve half is
        # the one the rules text puts first.
        writes=frozenset({"bodies_in_play", "attached_energy", "my_discard_contents",
                          "allowance_retreat_used", "special_conditions"}),
        complete=True),
    # _PLAY is deliberately ABSENT: per-card effects mean the kind has no complete footprint, and
    # `footprint()` returns the fail-closed default for anything not listed here.
}


def footprint(kind: int) -> Footprint:
    """This kind's footprint, or the **fail-closed default** (incomplete ⇒ commutes with nothing).

    A `dict.get` with a safe default rather than a KeyError: an option kind the table has not
    characterised must degrade to "assume it conflicts", never to a crash on the ordering path."""
    return FOOTPRINTS.get(int(kind), Footprint())


def footprints_writing_unhomed() -> dict:
    """``{kind: [owed zone ids]}`` — kinds whose transition writes state the snapshot cannot hold.

    **Not empty, and that is the finding.** `_EVOLVE` and `_RETREAT` both clear Special Conditions
    (`docs/rules.md` §4 and §8) and `special_conditions` has no snapshot home yet; `_RETREAT` also
    reads and writes the retreat allowance, which has none either. Under differencing that is the
    exact §3c failure: part of what the transition did is invisible, so the delta under-reports and
    at ordering time an under-reported delta is a pruned option.

    Surfaced as a function rather than a comment so T1 (Issue #260) has a generated work list and
    `test_snapshot_coverage.py` can assert the set only ever SHRINKS."""
    owed = set(snapshot_coverage.unhomed())
    out = {}
    for kind, fp in FOOTPRINTS.items():
        hit = sorted((fp.writes | fp.reads) & owed)
        if hit:
            out[kind] = hit
    return out


def commutes(kind_a: int, kind_b: int) -> bool:
    """May Issue #263 collapse these two orderings into one candidate?

    True iff **both** footprints are complete, **neither** reveals information, neither reads what
    the other writes, and they do not both write the same field. Every clause is a veto, and the
    default answer is False — an unknown footprint commutes with nothing, including itself."""
    a, b = footprint(kind_a), footprint(kind_b)
    if not (a.complete and b.complete):
        return False
    if a.reveals_information or b.reveals_information:
        return False
    if a.reads & b.writes or b.reads & a.writes:
        return False
    return not (a.writes & b.writes)


@dataclass(frozen=True)
class OutcomeClass:
    """One branch of an :class:`Expectation` — a distinguishable result of a stochastic effect.

    Classes are enumerated by **Option Equivalence** identity (ADR-0091 fingerprints), not by card
    identity: two indistinguishable reveals are ONE outcome, so the branching factor is the number of
    decisions the reveal actually poses rather than the number of cards it could name."""

    #: Probability of this class, from `common.deck_odds` hypergeometrics. Never an engine shuffle.
    probability: float
    #: The resulting StateModel for this branch. `None` until T4 (Issue #263).
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
    so an Expectation has to yield a single comparable number on demand: that is :meth:`expected`.
    An expectation shape usable only inside a sequence expansion would leave every draw Supporter
    unranked, which is the pruning failure the ordering amendment exists to fix.

    **Branching is capped** — the cap value is T4's (Issue #263); this seam promises only the shape.
    Whatever cap is chosen, the truncation must be REPORTED rather than silent: a capped enumeration
    that reads as a complete one is the "no silent caps" failure, and it would make an
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

    def expected(self, score: Callable[[object], float]) -> float:
        """``score`` averaged over the enumerated classes — the 1-ply ordering number.

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


def fate(option: Mapping, *, depth: int = 0, search_api=None, deterministic: bool | None = None
         ) -> str:
    """Which of §3b's three :data:`FATES` this **specific call** resolves to.

    ``depth``          — plies already applied. 0 is the live observation; ≥ 1 means the board is a
                         SYNTHESIZED StateModel, which the native engine cannot be handed.
    ``search_api``     — the `_search_api` seam (`strategy/planner.py`). Absent ⇒ no engine route.
    ``deterministic``  — the per-option proof, **tri-state**. `True` = proved to touch no RNG and no
                         hidden zone. `False` = proved otherwise. `None` = *unproven*, which refuses:
                         the gate is "provably deterministic", not "unmodelled", and ADR-0067's yield
                         convention says fail closed.

    Terminal options are not a fate — ask :func:`is_terminal` first; this reports `REFUSED` for them
    rather than inventing a fourth answer, and :func:`apply_option` raises.

    **A fourth gate is owed here: `clauses_cover`** (Issue #299, whose ruling this signature is
    waiting on). MODELLED is currently a pure kind-table lookup, so a `_PLAY` whose Effect Clauses
    cover only PART of the printed card resolves to MODELLED anyway and the uncovered leg differences
    to exactly 0 — the silent-zero failure, arriving through the compendium instead of the snapshot.
    Everything under that gate already exists and is audited: the per-card verdict ships in
    `card_effects.json` (`snapshot_coverage.COVERS_KEY`), `CardEffects.clauses_cover(card_id)` hands
    it over as the tri-state this argument will take — `True` full, `False` partial, `None` unruled —
    and both falsey answers must REFUSE, fail-closed exactly as ``deterministic`` does. Issue #300
    shipped that half; wiring it is #299's, because #299 is also re-deciding the MODELLED/engine
    precedence this gate sits inside and the two cannot be settled separately."""
    how = coverage(transition_kind(option))
    if how == MODELLED:
        return MODELLED
    if how != ENGINE_RESOLVED:
        return REFUSED
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
                 deterministic: bool | None = None):
    """The board after taking ``option``.

    Returns one of four shapes:

    * a new `StateModel` for a deterministic closed-form transition (the MODELLED fate);
    * an :class:`Expectation` over outcome classes for a stochastic one;
    * an :class:`EngineResolved` wrapping the model the engine produced (the ENGINE-RESOLVED fate);
    * a :class:`Refusal` — **never a silently unchanged model**, because that prices the option at
      0.0 delta and buries the gap (see :class:`Refusal`).

    ``depth`` / ``search_api`` / ``deterministic`` gate the engine route only; see :func:`fate` for
    what each means and why ``deterministic=None`` refuses.

    **Lazy, never an eager deep copy.** 1-ply ordering runs this once per candidate per decision, so
    a transition materialises only the fields the caller reads, riding the lazy pure snapshot of
    ADR-0068. Never mutates ``model``: the planner holds the pre-state while it evaluates
    alternatives, and a transition that edited in place would corrupt every sibling branch.

    Raises `ValueError` for a TERMINAL option — attack and end-turn have no successor state, and
    silently returning the unchanged model would let a beam sequence actions past the end of the
    turn. Callers test `is_terminal` first; that is the contract. (A terminal option is an API
    misuse, not a modelling gap, which is why it raises where a gap refuses.)

    Raises `NotImplementedError` for a MODELLED or ENGINE-RESOLVED fate until T4 (Issue #263)
    implements them — never an identity return, for the reason in this module's header.

    **Quarantine** (ADR-0098 decision 4): when the parity lane finds a divergence for an option kind,
    that kind is marked unverified and refuses here, so the planner degrades to always-expand and the
    telemetry names the kind. A parity failure therefore DEGRADES the agent visibly rather than
    silently mis-playing it."""
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
    if how == REFUSED:
        return refuse(option, f"option kind {kind} has no closed-form transition", scope=KIND_SCOPE)
    if how == ENGINE_RESOLVED:
        # Eligible. Each precondition refuses with its OWN scope — the coverage report needs to tell
        # "we never proved this deterministic" from "the caller wired no engine" from "we were two
        # plies deep", because they are three different pieces of work.
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
    raise NotImplementedError("apply_option is POC-T4 (Issue #263); T0 freezes the contract only")


def quarantined_kinds() -> frozenset[int]:
    """Option kinds the parity lane has found diverging — the planner must not enumerate through
    these (ADR-0098 decision 4).

    Empty until T4 wires the parity lane. The registry lives here rather than in the planner because
    the seam is what diverges: the planner is one consumer of that fact, and a second consumer (the
    coverage gate's report, the telemetry line) must read the same answer.

    **Telemetry is not optional.** A quarantined kind must be named, with its reason, wherever the
    agent reports what it did — a degraded agent that looks merely bad is indistinguishable from a
    broken one, and the whole point of quarantine is that the difference is visible."""
    return frozenset()


__all__: Sequence[str] = (
    "MODELLED", "ENGINE_RESOLVED", "TERMINAL", "REFUSED", "UNDECLARED", "FATES",
    "KIND_SCOPE", "OPTION_SCOPE", "UNDECLARED_SCOPE", "QUARANTINE_SCOPE", "DEPTH_SCOPE",
    "NONDETERMINISM_SCOPE", "NO_ENGINE_SCOPE",
    "KIND_COVERAGE", "TERMINAL_KINDS", "TRANSITION_KINDS", "ENGINE_ROUTE_KINDS", "REFUSED_KINDS",
    "Footprint", "FOOTPRINTS", "footprint", "commutes",
    "EngineResolved", "Refusal", "OutcomeClass", "Expectation", "UnsupportedTransition",
    "transition_kind", "coverage", "fate", "is_terminal", "refuse", "must_expand", "require_model",
    "apply_option", "quarantined_kinds",
)
