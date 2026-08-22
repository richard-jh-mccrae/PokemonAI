"""The **Damage Formula's scaler context** — one builder, two suppliers (Issue #279).

`compute_active_damage` prices a scaling attack over a CLOSED variable vocabulary (ADR-0032, ADR-0083;
``src/common/CONTEXT.md`` under *Damage Formula*). This module assembles that dict and nothing else —
deliberately pure: no engine, no observation, no StateModel, no Pilot.

:class:`SideFacts` is direction-NEUTRAL; :func:`damage_context` is the only place that decides which
side plays which role. The ``both_`` class is direction-symmetric, so one key serves either attacker.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True)
class SideFacts:
    """One side's countables for the Damage Formula — **direction-neutral**: every field records what
    THIS side has, never what it is doing. Fail-closed by default, so an unread side makes NO claim."""

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
    #: The NAMES of every Pokémon this side has IN PLAY — Active first, then Bench (the Bench IS in play,
    #: `docs/rulebook.txt` L559). Distinct from :attr:`bench_names`; ``""`` for an unresolvable body.
    in_play_names: Sequence[str] = ()
    #: One entry PER in-play body (Active first, then Bench): that body's printed attack NAMES. Nested
    #: rather than flattened because the predicate counts BODIES. ``()`` for a body that does not resolve.
    in_play_attack_names: Sequence[Sequence[str]] = ()
    #: ``((amount, attackerEnergyType|None, vsExOnly), ...)`` — flat damage boosts live for this side's
    #: attacks: this-turn Trainer plays and Tools on its Active. Open info in either direction.
    damage_boosts: Sequence[tuple] = ()
    #: Cards left in this side's deck, EXACT — ``None`` unless the deck tracker has anchored the
    #: prizes. Only ever known for my own side.
    deck_count: int | None = None
    #: ``{EnergyType: count}`` of Basic Energy still in that exactly-known deck; ``None`` alongside
    #: an unanchored :attr:`deck_count`.
    deck_basic_by_type: Mapping[int, int] | None = None


def bench_gate_context(bench_names: Sequence[str]) -> dict:
    """The MATCHUP-FREE slice of an attacker's context: just the bench-partner condition's input. The
    full :func:`damage_context` carries the defender's countables, so it would swing on who is Active."""
    return {"atk_bench_names": tuple(bench_names)}


def damage_context(attacker: SideFacts, defender: SideFacts) -> dict:
    """The scaler context for ONE direction: ``attacker``'s attack against ``defender`` — the ONE place a
    per-side fact becomes an ``atk_``/``def_``/``both_`` key. The deck pair is OMITTED, never zeroed."""
    ctx = {
        "atk_hand": attacker.hand_size,
        "def_hand": defender.hand_size,
        "def_active_energy": defender.active_energy,
        "atk_active_energy": attacker.active_energy,
        "atk_bench": attacker.bench_count,
        "def_bench": defender.bench_count,
        # `both_` is the THIRD direction class beside atk_/def_ (ADR-0083 §4): a variable counting BOTH
        # sides at once. The sum is direction-symmetric, so ONE key is right whichever side attacks.
        "both_bench": attacker.bench_count + defender.bench_count,
        "both_active_energy": attacker.active_energy + defender.active_energy,
        # The attacker's DISCARD is open info for BOTH players. `atk_discard_energy` is the documented
        # exception to "every variable name IS a context key" — the attack's own type filter selects.
        "atk_discard_energy_total": attacker.discard_energy_total,
        # COPIED, not aliased: a supplier's histogram may be its own memoized field, and `SideFacts`
        # being frozen does not freeze a Mapping inside it.
        "atk_discard_basic_by_type": dict(attacker.discard_basic_by_type or {}),
        "atk_bench_names": tuple(attacker.bench_names),
        "atk_boosts": tuple(attacker.damage_boosts),
        "atk_self_counters": attacker.active_counters,
        "def_counters": defender.active_counters,
        "atk_prizes_taken": attacker.prizes_taken,
        "def_prizes_taken": defender.prizes_taken,
        # The three CLOSED filtered counts (Issue #225) — a predicate over a zone rather than its size.
        # FLAT names because each predicate is closed; deliberately NOT migrated onto the open form.
        "atk_bench_stage2": attacker.bench_stage2,
        "def_counters_all": defender.counters_in_play,
        "def_ex_in_play": defender.ex_in_play,
        # The OPEN filtered counts (ADR-0115): these keys carry RAW MATERIAL, and the oracle reduces it
        # with the filter the attack itself carries. `both_in_play_names` is direction-symmetric.
        "both_in_play_names": tuple(attacker.in_play_names) + tuple(defender.in_play_names),
        "atk_in_play_attack_names": tuple(tuple(n) for n in attacker.in_play_attack_names),
    }
    if attacker.deck_count is not None:
        ctx["atk_deck_count"] = attacker.deck_count
        ctx["atk_deck_basic_by_type"] = dict(attacker.deck_basic_by_type or {})
    return ctx


__all__ = ("SideFacts", "bench_gate_context", "damage_context")

