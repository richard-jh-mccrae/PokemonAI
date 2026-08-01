"""**The apply-seam** — the closed-form hypothetical transition (POC-T4, contract frozen by POC-T0 /
Issue #259, ADR-0092 §4-T0 item 3, ADR-TEMP-259e).

`apply_option(model, option)` answers *what would the board be if I did this?* — arithmetically, from
the StateModel, stepping no engine. It is what lets the Turn Planner price a play by **differencing**
(`state_value(after) − state_value(before)`) and compose a candidate sequence without spending the
2-vCPU grader budget on a forked simulation per branch.

**INERT.** T0 ships the option-kind table, the signatures and the docstrings; T4 (Issue #263)
implements the transitions. Every transition raises `NotImplementedError` rather than returning the
model unchanged — an identity stub would price every play at exactly 0.0, which is a real and
plausible answer, so an unimplemented build would read as "this play is worthless" rather than as
"this play is unimplemented".

## Why closed-form and not the engine

The native engine CAN fork — `search_begin` / `search_step` (`src/cg/api.py`) fork an independent
position and the Pilot already uses them live for the Lethal Solver. The fork was declined for the
POC anyway, on two measured objections (ADR-TEMP-259e):

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
(`_finish_turn_last`'s information-before-commitment boundary, ADR-TEMP-259b), and is not a defect in
this module. Recorded here because the alternative is a later track assuming the planner will
discover it, and quietly shipping an agent that commits before it digs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

# The engine's own vocabulary, never re-spelled (CLAUDE.md: option types come from `src/cg/api.py`).
# Imported through the strategy context, which is the module that already owns the DLL-free mirror of
# those enums — a second transcription here is the drift ADR-0087 charges for one store over.
from common.strategy.context import _ATTACH, _ATTACK, _END, _EVOLVE, _PLAY, _RETREAT

#: A transition that is not a transition: the turn is over, so there is no ``model'`` to return. Both
#: members END the turn (`docs/rules.md` §3 — an attack ends your turn, and it is 1 per turn), which
#: is why the planner's beam terminates on them rather than sequencing past them.
TERMINAL_KINDS: frozenset[int] = frozenset({_ATTACK, _END})

#: Every option kind the planner sequences and this seam therefore promises to transition.
#: Deliberately a declared SET rather than a dispatch table with a default branch: a kind absent here
#: is refused loudly by `transition_kind`, where a silent fallthrough would mis-price it as a no-op.
TRANSITION_KINDS: frozenset[int] = frozenset({_PLAY, _ATTACH, _EVOLVE, _RETREAT})


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
    returns the distribution rather than a sampled representative. `state_value` of an Expectation is
    the probability-weighted sum over its classes.

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


class UnsupportedTransition(NotImplementedError):
    """This seam was asked for a transition it does not declare.

    Fail loud, never guess — the same discipline cgpy applies to a def-less card (`UnsupportedCard`).
    A seam that returned the model unchanged for an unknown kind would price that play at exactly
    0.0, and 0.0 is a real answer, so the planner would confidently decline a play it simply cannot
    model."""


def transition_kind(option: Mapping) -> int:
    """The option's engine ``type``, checked against what this seam declares.

    Raises `UnsupportedTransition` for a kind that is neither transitional nor terminal, so an option
    vocabulary that grows (an ABILITY at the main menu, a SKILL ordering) surfaces as a refusal at
    the seam rather than as a mis-priced no-op three layers up."""
    kind = int((option or {}).get("type", -1))
    if kind not in TRANSITION_KINDS and kind not in TERMINAL_KINDS:
        raise UnsupportedTransition(f"option type {kind} is not declared by the apply-seam")
    return kind


def is_terminal(option: Mapping) -> bool:
    """Does taking this option END the turn? Attack and End do (`docs/rules.md` §3).

    A terminal option has no ``model'``: the planner scores the state it was reached FROM and stops
    the beam there, rather than transitioning into a turn that no longer belongs to me."""
    return transition_kind(option) in TERMINAL_KINDS


def apply_option(model, option: Mapping):
    """The board after taking ``option`` — closed-form, engine-free.

    Returns a new `StateModel` for a deterministic transition, or an :class:`Expectation` over
    outcome classes for a stochastic one. Never mutates ``model``: the planner holds the pre-state
    while it evaluates alternatives, and a transition that edited in place would corrupt every
    sibling branch.

    Raises `ValueError` for a TERMINAL option — attack and end-turn have no successor state, and
    silently returning the unchanged model would let a beam sequence actions past the end of the
    turn. Callers test `is_terminal` first; that is the contract.

    Raises `UnsupportedTransition` for an option kind the seam does not declare, and
    `NotImplementedError` until T4 (Issue #263) implements the kinds it does.

    **Quarantine** (ADR-TEMP-259e decision 4): when the parity lane finds a divergence for an option
    kind, that kind is marked unverified and the planner refuses to enumerate sequences through it,
    deferring to the whitelisted sound ladder. `quarantined_kinds` is the registry that decision
    reads; a parity failure therefore DEGRADES the agent rather than silently mis-playing it."""
    if is_terminal(option):
        raise ValueError(
            "attack and end-turn are TERMINAL — they end the turn, so there is no successor state; "
            "test `is_terminal(option)` before calling")
    raise NotImplementedError("apply_option is POC-T4 (Issue #263); T0 freezes the contract only")


def quarantined_kinds() -> frozenset[int]:
    """Option kinds the parity lane has found diverging — the planner must not enumerate through
    these (ADR-TEMP-259e decision 4).

    Empty until T4 wires the parity lane. The registry lives here rather than in the planner because
    the seam is what diverges: the planner is one consumer of that fact, and a second consumer (the
    coverage gate's report, the telemetry line) must read the same answer.

    **Telemetry is not optional.** A quarantined kind must be named, with its reason, wherever the
    agent reports what it did — a degraded agent that looks merely bad is indistinguishable from a
    broken one, and the whole point of quarantine is that the difference is visible."""
    return frozenset()


__all__: Sequence[str] = (
    "TERMINAL_KINDS", "TRANSITION_KINDS", "OutcomeClass", "Expectation", "UnsupportedTransition",
    "transition_kind", "is_terminal", "apply_option", "quarantined_kinds",
)
