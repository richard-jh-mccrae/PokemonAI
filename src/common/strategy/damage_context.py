"""The **Damage Formula's scaler context** — one builder, two suppliers (Issue #279, POC-T3.5).

`compute_active_damage` prices a scaling attack as ``base + per_unit x count(variable)`` over a
CLOSED vocabulary of visible-state variables (ADR-0032, ADR-0083; the vocabulary itself is
documented in ``src/common/CONTEXT.md`` under *Damage Formula*). The counts arrive as a plain dict —
``context`` — whose keys ARE the variable names, so the oracle stays one dict lookup per scaler.

This module owns the assembly of that dict, and nothing else. It is deliberately pure: no engine,
no observation, no StateModel, no Pilot. The two live suppliers hand it two :class:`SideFacts`
records and get the context back.

**Why it is a module rather than a method on either supplier.** Before this, the ONE full
construction lived on the Pilot, and Issue #279's substrate needed a second one on the StateModel
(``state_value`` may read nothing but the model — the sole-supplier ruling,
``docs/plans/value-system-poc-plan.md`` §4-T0). Two hand-rolled builders of one fact is
precisely the defect ``CombatMath.card_level_damage`` was extracted to end — *"One fact, two
hand-rolled call sites, free to drift — and they did"* (``strategy/combat.py``) — so the shape is
pulled out here instead, and ``tests/strategy/test_damage_context.py`` pins the two suppliers
key-for-key on real corpus frames.

**Direction is the whole design.** The Formula's variables are named relative to *who is attacking*
(``atk_*`` / ``def_*``), so "their attack on me" and "my attack on them" are two different dicts
built from the same two sides in opposite roles. :class:`SideFacts` is therefore direction-NEUTRAL —
it records what a side HAS, never what it is doing — and :func:`damage_context` is the only place
that decides which side plays which role. The ``both_`` class (ADR-0083 §4, Issue #213) is the one
direction-symmetric family: it sums the two halves, so a single key is correct whichever side
attacks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True)
class SideFacts:
    """One side's countables for the Damage Formula — **direction-neutral**.

    Every field records what THIS side has; none of them knows whether this side is attacking. That
    is what makes the record reusable in both roles and what stops a mirrored key from being built
    at the gathering site, where the two suppliers would have to agree about it independently.

    **Fail-closed by default.** Every field's default is its identity — 0, empty, or ``None`` for
    the deck pair whose absence is a real distinction (see :func:`damage_context`). A side the
    supplier could not read therefore makes NO claim, rather than a zero-shaped one; the oracle's
    own rule is that a variable absent from the context contributes 0 to the damage, which is a
    sound floor and a weak ceiling (``strategy/damage.py``).
    """

    #: Cards in this side's hand. A COUNT on both sides — the only honest read of a hidden zone,
    #: and the engine gives the opponent's as ``handCount`` and never the contents.
    hand_size: int = 0
    #: Energy UNITS attached to this side's Active (``BodyView.energy_count``'s reading — the raw
    #: count the rules speak in, not the typed histogram a cost SHAPE is matched against).
    active_energy: int = 0
    #: Bodies on this side's Bench.
    bench_count: int = 0
    #: Prize cards this side has already taken — ``6 - remaining`` (rulebook L57/L102), and 0 when
    #: the zone is absent rather than 6 (an absent zone claims nothing).
    prizes_taken: int = 0
    #: Damage counters on this side's ACTIVE — ``(maxHp - hp) // 10``.
    active_counters: int = 0
    #: Damage counters on EVERY body this side has in play, Active and Bench. A different variable
    #: from :attr:`active_counters`, which is why it is a separate field and not a projection.
    counters_in_play: int = 0
    #: Stage 2 Pokémon on this side's Bench — fail-CLOSED per body (an unresolvable card is not
    #: counted; over-reading one's own bench is the direction that manufactures a phantom lethal).
    bench_stage2: int = 0
    #: This side's Pokémon ``{ex}`` in play. Mega Evolution Pokémon ex count — a Mega Evolution
    #: Pokémon ex IS an ``{ex}`` (``docs/rulebook.txt`` L337).
    ex_in_play: int = 0
    #: Every Energy CARD in this side's discard — Basic and Special alike. The discard is public in
    #: both directions (``docs/rulebook.txt`` L541), so this is a sound count and never an estimate.
    discard_energy_total: int = 0
    #: ``{EnergyType: count}`` of BASIC Energy in this side's discard — the typed filter a
    #: Riptide-class scaler ("for each Basic {W} Energy card in your discard pile") reads.
    discard_basic_by_type: Mapping[int, int] = field(default_factory=dict)
    #: The NAMES of this side's Benched Pokémon, in bench order — the bench-partner condition's
    #: input ("does nothing without Lunatone on your Bench"). ``""`` for an unresolvable body.
    bench_names: Sequence[str] = ()
    #: ``((amount, attackerEnergyType|None, vsExOnly), ...)`` — flat damage boosts live for this
    #: side's attacks: this-turn Trainer plays and Tools attached to this side's Active. Both are
    #: open information in either direction, so both are read for whichever side is attacking.
    damage_boosts: Sequence[tuple] = ()
    #: Cards left in this side's deck, EXACT — ``None`` unless the deck tracker has anchored the
    #: prizes. Only ever known for my own side.
    deck_count: int | None = None
    #: ``{EnergyType: count}`` of Basic Energy still in that exactly-known deck; ``None`` alongside
    #: an unanchored :attr:`deck_count`.
    deck_basic_by_type: Mapping[int, int] | None = None


def damage_context(attacker: SideFacts, defender: SideFacts) -> dict:
    """The scaler context for ONE direction: ``attacker``'s attack against ``defender``.

    The ONE place a per-side fact becomes an ``atk_``/``def_``/``both_`` key. Callers pick the
    direction by choosing which side to pass first; nothing downstream re-decides it.

    Three families of key, all in one dict because the oracle takes one dict:

    * the **scaler variables** proper — every name here is a ``scaleVar`` the text parser can emit
      (``scouting/card_text.py``) or one shipped as a per-``attackId`` override
      (``common/attack_overrides.json``);
    * the **attacker's private riders** the oracle reads off the same dict — ``atk_bench_names``
      (a bench-partner condition), ``atk_boosts`` (flat Trainer/Tool boosts, applied before
      Weakness/Resistance);
    * the **hidden deck pair** ``atk_deck_count`` / ``atk_deck_basic_by_type``, present only when
      the attacker's deck is exactly known.

    The deck pair is OMITTED rather than zeroed when unanchored, and the distinction is load-bearing:
    the oracle's hidden-scaler leg branches on ``deck_n and fuel is not None`` to choose between a
    pigeonhole floor / hypergeometric mean and its no-deck-facts fallback, so a present-but-zero pair
    is a positive claim ("the deck holds nothing") that an unresolved prize split cannot support.
    """
    ctx = {
        "atk_hand": attacker.hand_size,
        "def_hand": defender.hand_size,
        "def_active_energy": defender.active_energy,
        "atk_active_energy": attacker.active_energy,
        "atk_bench": attacker.bench_count,
        "def_bench": defender.bench_count,
        # `both_` is the THIRD direction class beside atk_/def_ (ADR-0083 §4, Issue #213): a
        # variable counting BOTH sides at once ("for each Benched Pokémon (both yours and your
        # opponent's)"). The sum is direction-symmetric, so ONE key is correct whichever side
        # attacks — no mirroring, and the oracle keeps a single lookup per scaler.
        "both_bench": attacker.bench_count + defender.bench_count,
        "both_active_energy": attacker.active_energy + defender.active_energy,
        # the attacker's DISCARD — open info for BOTH players, so an opponent's Riptide is exactly
        # priceable from THEIR visible discard. `atk_discard_energy` is the single documented
        # exception to "every variable name IS a context key": it reads whichever of these two the
        # attack's own type filter selects (`strategy/damage.py`).
        "atk_discard_energy_total": attacker.discard_energy_total,
        # COPIED, not aliased. A supplier's histogram may be its own memoized field — the
        # StateModel's `discard_energy_counts` is, and it also feeds the Attach Budget — while the
        # context is handed to arbitrary consumers. `SideFacts` is frozen; a Mapping inside it is
        # not, so sharing the object would let a context reader corrupt a snapshot field. Small
        # dicts, and the whole context is memoized per direction, so the copy is paid once.
        "atk_discard_basic_by_type": dict(attacker.discard_basic_by_type or {}),
        "atk_bench_names": tuple(attacker.bench_names),
        "atk_boosts": tuple(attacker.damage_boosts),
        "atk_self_counters": attacker.active_counters,
        "def_counters": defender.active_counters,
        "atk_prizes_taken": attacker.prizes_taken,
        "def_prizes_taken": defender.prizes_taken,
        # the two FILTERED counts (Issue #225, POC-T1) — a predicate over a zone rather than the
        # zone's size, carrying flat names because the vocabulary deliberately did NOT grow a
        # filtered-count FORM to hold them (`src/common/CONTEXT.md`).
        "atk_bench_stage2": attacker.bench_stage2,
        "def_counters_all": defender.counters_in_play,
        "def_ex_in_play": defender.ex_in_play,
    }
    if attacker.deck_count is not None:
        ctx["atk_deck_count"] = attacker.deck_count
        ctx["atk_deck_basic_by_type"] = dict(attacker.deck_basic_by_type or {})
    return ctx


__all__ = ("SideFacts", "damage_context")
