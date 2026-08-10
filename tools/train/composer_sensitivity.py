"""Deterministic Composer sensitivity probes (Issue #493).

This is an audit lab, not a runtime shadow.  It builds controlled ``StateModel`` snapshots, applies
real options through :mod:`common.apply_option`, and asks the live Composer about one-ply admission
and final candidate presence.  Large corpus evidence lives in a fixture; synthetic observations are
constructed here and never written back to Corrections.

    python tools/train/composer_sensitivity.py --all --out reports/composer-sensitivity.json
    python tools/train/composer_sensitivity.py --case mega-starmie-wally-attach
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Mapping, Sequence

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common import apply_option as ao                                    # noqa: E402
from common import board_expectation as bx                               # noqa: E402
from common import composer as cp                                        # noqa: E402
from common import currency, needs, retreat_cost                         # noqa: E402
from common.cards import CardFunctions                                   # noqa: E402
from common.deciders.attach import AttachMixin                           # noqa: E402
from common.deciders.evolve import EvolveMixin                           # noqa: E402
from common.deciders.facts import Board                                  # noqa: E402
from common.deciders.heal import HealMixin                               # noqa: E402
from common.effects import CardEffects                                   # noqa: E402
from common.evolve_value import EvolveInputs, evolve_value               # noqa: E402
from common.option_equivalence import class_of, option_equivalence       # noqa: E402
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider  # noqa: E402
from common.state_model import StateModel                                # noqa: E402
from common.state_value import (                                         # noqa: E402
    FAMILIES,
    attack_ev_legs,
    state_value,
    value_breakdown,
    value_difference,
)
from common.strategy.combat import Budget, CombatMath                    # noqa: E402
from common.strategy.context import (                                    # noqa: E402
    _ACTIVE,
    _ATTACH,
    _ATTACK,
    _BENCH,
    _END,
    _EVOLVE,
    _MAIN,
    _NUMBER,
    _PLAY,
    _RETREAT,
)
from common.strategy.planning.ko_classes import KoClassMixin              # noqa: E402
from train.apply_parity import zone_facts                                # noqa: E402

SCHEMA_VERSION = "composer-sensitivity/3"
SUMMARY_SCHEMA_VERSION = "composer-sensitivity-summary/3"
SEED = 493
FIXTURE = REPO / "tests" / "fixtures" / "composer_sensitivity" / "ms_wally_attach_f69.json"
_INVENTORY_CONTEXT: ContextVar[object | None] = ContextVar(
    "composer_sensitivity_inventory", default=None)

# Synthetic ids are deliberately outside shipped card data.  Identity is never used as a policy
# class; the identity metamorphic case proves that equivalent mechanics retain the same result.
SYN_BODY = 990_001
SYN_BODY_CLONE = 990_002
SYN_OPP = 990_003
SYN_WATER = 990_010
SYN_FIRE = 990_011
SYN_TOOL = 990_012
SYN_FETCH = 990_013
SYN_BASIC = 990_020
SYN_EVOLUTION = 990_021
REFUSED_CARD = 1153  # Lumiose Galette: heal is carried; condition removal remains unmodelled.
HEAL_CARD = 1222     # Fennel: shipped, full clause; heal 40 from each of my Pokemon.
SYN_ATTACK_CHEAP = 991_001
SYN_ATTACK_BIG = 991_002
SYN_ATTACK_OPP = 991_003
WATER, FIRE, COLORLESS = 3, 2, 0


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, check=True, capture_output=True,
            text=True, encoding="utf-8",
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - provenance degrades visibly, never changes the measurement
        return "unknown"


def _jsonable(value):
    """Stable JSON projection.  Tuple/list distinctions are not semantic report fields."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        value = round(value, 12)
        return 0.0 if value == 0.0 else value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if hasattr(value, "_asdict"):
        return _jsonable(value._asdict())
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (set, frozenset)):
        return [_jsonable(v) for v in sorted(value, key=repr)]
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return repr(value)


def _value_snapshot(model) -> dict:
    breakdown = value_breakdown(model)
    workings = {family.family: family.value_prizes for family in breakdown.families}
    terminals = []
    for leg in attack_ev_legs(model):
        terminal_total, ev, gap = cp.terminal_ev(
            model, {"type": _ATTACK, "attackId": leg.attack_id})
        if ev is None or gap:
            raise RuntimeError(f"terminal seam refused attack {leg.attack_id}: {gap}")
        terminals.append({"attack_id": leg.attack_id, "total": float(terminal_total),
                          "working": ev.working()})
    legs = {family.family: [leg.as_dict() for leg in family.legs]
            for family in breakdown.families}
    legs["terminal"] = terminals
    return _jsonable({"total": breakdown.total, "workings": workings, "legs": legs,
                      "registry_identity": breakdown.registry_identity,
                      "statuses": {family.family: family.status.value
                                   for family in breakdown.families}})


def _family_result(model, name: str):
    return next(family for family in value_breakdown(model).families if family.family == name)


def _delta(before_model, after_model) -> dict:
    difference = value_difference(before_model, after_model)
    families = {family.family: family.delta for family in difference.families}
    legs = {
        f"{family.family}.{leg.key}": leg.as_dict()
        for family in difference.families for leg in family.legs
        if leg.before != leg.after or leg.before_status is not leg.after_status
    }
    return {"total": difference.delta, "families": families, "legs": legs}


def _changed(before_model, after_model) -> list[str]:
    before, after = zone_facts(before_model), zone_facts(after_model)
    return sorted(zone for zone in sorted(set(before) | set(after)) if before.get(zone) != after.get(zone))


def _card_id(model, option: Mapping) -> int | None:
    """Card source of an option on this exact board; used only for clause-completeness metadata."""
    obs = model.source_obs or {}
    players = ((obs.get("current") or {}).get("players")) or []
    seat = int(model.my_index)
    me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    index = option.get("index")
    if option.get("area") in (None, 2) and isinstance(index, int):
        hand = me.get("hand") or []
        if 0 <= index < len(hand) and hand[index]:
            return hand[index].get("id")
    return None


def _cover(model, option: Mapping):
    cid = _card_id(model, option)
    effects = getattr(model.combat, "effects", None)
    return effects.clauses_cover(cid) if cid is not None and effects is not None else None


def _apply_one(model, option: Mapping) -> tuple[object | None, str, dict]:
    """Apply one resolved action and choose a deferred class through Composer's public ranker."""
    if ao.is_terminal(option):
        return None, ao.TERMINAL, {"reason": "terminal actions have no successor StateModel"}
    result = ao.apply_option(model, option, clauses_cover=_cover(model, option),
                             expand_deferred_targets=True)
    if isinstance(result, ao.Refusal):
        return None, ao.REFUSED, {"scope": result.scope, "reason": result.reason}
    if isinstance(result, ao.Expectation):
        choice = cp.rank_targets(model, result)
        if choice.best is None:
            return None, ao.REFUSED, {"reason": "deferred expectation enumerated no target class"}
        return choice.best.model, ao.MODELLED, {
            "resolution": result.resolution, "chosen_target": list(choice.best.fingerprint),
            "target_classes": len(choice.scored), "bounds": choice.working(),
        }
    if isinstance(result, ao.ScalarTransition):
        return result.model, ao.MODELLED, {"scalar": float(result.scalar)}
    if isinstance(result, ao.EngineResolved):
        return result.model, ao.ENGINE_RESOLVED, {"clause_gap": result.clause_gap}
    return result, ao.MODELLED, {}


def apply_sequence(model, options: Sequence[Mapping], indices: Sequence[int]) -> tuple[object, list[dict]]:
    """Force root-menu actions in the named order, re-resolving stamped identities after each step."""
    stamped = [cp.stamp_origin(model, option) for option in options]
    current = model
    rows = []
    for ordinal, index in enumerate(indices, 1):
        if not isinstance(index, int) or not 0 <= index < len(stamped):
            rows.append(_action_row(ordinal, index, None, ao.REFUSED,
                                    {"reason": "index is outside the root menu"}))
            break
        option = cp.resolve_against(current, stamped[index])
        if option is None:
            rows.append(_action_row(ordinal, index, None, ao.REFUSED,
                                    {"reason": "stamped source or target no longer exists"}))
            break
        footprint = ao.option_footprint(current, option, clauses_cover=_cover(current, option))
        after, fate, detail = _apply_one(current, option)
        changed = [] if after is None else _changed(current, after)
        rows.append(_action_row(ordinal, index, option, fate, detail, footprint, changed))
        if after is None:
            break
        current = after
    return current, rows


def _action_row(ordinal: int, index, option, fate: str, detail: dict,
                footprint=None, changed=()) -> dict:
    return _jsonable({
        "ordinal": ordinal, "index": index, "option": dict(option or {}), "fate": fate,
        "changed_dimensions": list(changed),
        "declared_reads": sorted(getattr(footprint, "reads", ()) or ()),
        "declared_writes": sorted(getattr(footprint, "writes", ()) or ()),
        "footprint_complete": bool(getattr(footprint, "complete", False)),
        "detail": detail,
    })


def _admission_reason(margin) -> str:
    if margin.always_expand:
        return "always-expand"
    if margin.in_beam:
        return "hard-top-k"
    if margin.admitted:
        return "epsilon-band"
    return "cut"


def _candidate_row(result, sequence: Sequence[int]) -> dict:
    target = tuple(int(i) for i in sequence)

    def indices(candidate):
        return tuple(step.index for step in candidate.steps)

    exact = [c for c in result.candidates if indices(c) == target]
    prefixes = [c for c in result.candidates if indices(c)[:len(target)] == target]
    selection = [c for c in result.selection_candidates if indices(c) == target]
    faithful_exact = [c for c in exact if not c.coverage_gap]
    faithful_prefixes = [c for c in prefixes if not c.coverage_gap]
    faithful_selection = [c for c in selection if not c.coverage_gap]
    chosen = result.chosen
    chosen_indices = indices(chosen) if chosen is not None else ()

    def candidate(candidate):
        return {"coverage_gap": candidate.coverage_gap,
                "faithful": not bool(candidate.coverage_gap),
                "score": candidate.score,
                "retained_for_diagnostics": candidate in result.selection_candidates,
                "survived_terminal_dominance": (
                    not candidate.coverage_gap and candidate in result.selection_candidates)}

    return _jsonable({
        "sequence": list(target), "generated_exact": bool(exact),
        "generated_as_prefix": bool(prefixes),
        "faithful_generated_exact": bool(faithful_exact),
        "faithful_generated_as_prefix": bool(faithful_prefixes),
        # A refused gap candidate is retained for diagnosis, not admitted as a scored survivor.
        "survived_terminal_dominance": bool(faithful_selection),
        "refused_gap_placeholder_only": bool(exact and not faithful_exact),
        "coverage_gaps": sorted({c.coverage_gap for c in exact if c.coverage_gap}),
        "matching_candidates": [candidate(c) for c in exact],
        "chosen": (chosen is not None and not chosen.coverage_gap
                   and chosen_indices == target),
        "final_score": max((c.score for c in faithful_exact), default=None),
        "matching_scores": sorted({c.score for c in faithful_exact}),
    })


def search_snapshot(model, options: Sequence[Mapping], *, focus=(), sequences=(),
                    k=cp.BEAM_WIDTH, epsilon=cp.EPSILON, depth=1,
                    shed=None) -> dict:
    """Composer telemetry without a runtime hook: all fields come from ``ComposerResult``."""
    result = cp.compose(model, options, k=k, epsilon=epsilon, depth=depth, shed=shed)
    equiv = option_equivalence(options, model.source_obs)
    one_ply = []
    for index in focus:
        klass = sorted(class_of(equiv, int(index)))
        representative = min(klass)
        margin = result.margin_for(representative)
        one_ply.append({
            "index": int(index), "equivalence_class": klass, "representative": representative,
            **margin.working(), "admission_reason": _admission_reason(margin),
            "cutoff_margin": margin.margin_to_kth,
        })
    chosen = result.chosen
    return _jsonable({
        "status": "composed", "k": k, "epsilon": epsilon, "depth": depth,
        "one_ply": one_ply,
        "candidate_presence": [_candidate_row(result, sequence) for sequence in sequences],
        "chosen": (None if chosen is None else {
            "sequence": [step.index for step in chosen.steps],
            "terminal_index": chosen.terminal_index, "score": chosen.score,
            "coverage_gap": chosen.coverage_gap,
            "faithful": not bool(chosen.coverage_gap),
        }),
        "gaps": list(result.gaps),
    })


def _blank_search(reason: str) -> dict:
    return {"status": "not-run", "k": cp.BEAM_WIDTH, "epsilon": cp.EPSILON,
            "depth": cp.SEQUENCE_DEPTH, "one_ply": [], "candidate_presence": [],
            "chosen": None, "gaps": [reason]}


def _unknown(actions: Sequence[dict], extra=(), unread_extra=()) -> dict:
    dimensions, reasons = set(), []
    for action in actions:
        if action.get("fate") == ao.REFUSED:
            dimensions.update(action.get("declared_writes") or ())
            reasons.append(action.get("detail", {}).get("reason") or "apply seam refused")
    for dimension, reason in extra:
        dimensions.add(dimension)
        reasons.append(reason)
    forced_unread = set()
    for dimension, reason in unread_extra:
        forced_unread.add(dimension)
        reasons.append(reason)
    # The static join is authoritative and fail-closed.  Consume its reusable API instead of
    # duplicating (or silently weakening) the authored ownership semantics in this lab.
    import composer_value_coverage as coverage
    inventory = _INVENTORY_CONTEXT.get() or _coverage_inventory()
    unread = set(forced_unread)
    for dimension in sorted({d for a in actions for d in a.get("changed_dimensions", ())}):
        summary = coverage.owner_summary(dimension, inventory=inventory)
        if not getattr(summary, "absolute_owners", ()) and not getattr(summary, "terminal_owners", ()):
            unread.add(dimension)
    return {"dimensions": sorted(dimensions), "unread_dimensions": sorted(unread),
            "reasons": sorted(set(reasons))}


@lru_cache(maxsize=1)
def _coverage_inventory():
    """One static census per sweep; its module-level helper otherwise rebuilds for every zone."""
    import composer_value_coverage as coverage
    return coverage.build_inventory()


def _case_record(name: str, key: str, before_model, after_model, actions, *, local, search,
                 control, source="synthetic", unknown_extra=(), unread_extra=()) -> dict:
    before, after = _value_snapshot(before_model), _value_snapshot(after_model)
    if isinstance(source, str):
        source = {"kind": source, "fixture": None, "provenance": {}}
    return _jsonable({
        "case": name, "key": key, "source": source, "seed": SEED,
        "command": f"python tools/train/composer_sensitivity.py --case {name}",
        "before": before, "actions": actions, "after": after,
        "deltas": _delta(before_model, after_model), "local": local, "search": search,
        "unknown": _unknown(actions, unknown_extra, unread_extra), "positive_control": control,
    })


def _local(owner: str, unit: str, before, after, *, working=None) -> dict:
    delta = None
    if isinstance(before, (int, float)) and not isinstance(before, bool) \
            and isinstance(after, (int, float)) and not isinstance(after, bool):
        delta = float(after) - float(before)
    return _jsonable({"owner": owner, "unit": unit, "before": before, "after": after,
                      "delta": delta, "working": working or {}})


def _ordered_sequence(label: str, indices: Sequence[int], before_model, after_model,
                      actions: Sequence[dict], *, local: dict) -> dict:
    """One order's complete transition/value contract, independent of the case's primary order."""
    before, after = _value_snapshot(before_model), _value_snapshot(after_model)
    return _jsonable({
        "label": label,
        "indices": list(indices),
        "before": before,
        "actions": list(actions),
        "after": after,
        "deltas": _delta(before_model, after_model),
        "local": local,
    })


# -- minimal synthetic boards ------------------------------------------------------------------


def _card(card_id: int, serial: int, seat=0) -> dict:
    return {"id": card_id, "serial": serial, "playerIndex": seat}


def _body(card_id=SYN_BODY, *, serial=1, hp=220, max_hp=220, energies=(), energy_ids=(),
          tools=(), pre=(), appear=False, seat=0) -> dict:
    cards = [_card(cid, 100 + n, seat) for n, cid in enumerate(energy_ids)]
    return {"id": card_id, "serial": serial, "playerIndex": seat, "hp": hp, "maxHp": max_hp,
            "appearThisTurn": appear, "energies": list(energies), "energyCards": cards,
            "tools": list(tools), "preEvolution": list(pre)}


def _player(*, active, bench=(), hand=(), prizes=4, deck_count=40, seat=0) -> dict:
    return {"active": [active] if active else [], "bench": list(bench), "benchMax": 5,
            "hand": list(hand), "handCount": len(hand), "discard": [],
            "prize": [None] * prizes, "deckCount": deck_count,
            "asleep": False, "burned": False, "confused": False, "paralyzed": False,
            "poisoned": False}


def _obs(*, mine, theirs=None, options=(), turn=2) -> dict:
    theirs = theirs or _player(active=_body(SYN_OPP, serial=50, hp=220, max_hp=220, seat=1), seat=1)
    return {
        "current": {"players": [mine, theirs], "yourIndex": 0, "turn": turn, "result": -1,
                    "firstPlayer": 1, "energyAttached": False, "supporterPlayed": False,
                    "stadiumPlayed": False, "retreated": False, "stadium": [], "looking": None},
        "logs": [],
        "select": {"context": _MAIN, "minCount": 1, "maxCount": 1,
                   "option": [dict(option) for option in options]},
    }


def _stats(*, attacks: str = "multi", body_id=SYN_BODY, opponent_damage=0) -> tuple[dict, dict]:
    if attacks == "single":
        body_attacks = (SYN_ATTACK_CHEAP,)
        max_damage, max_cost, min_cost, min_damage = 120, 1, 1, 120
        attack_rows = {SYN_ATTACK_CHEAP: AttackStat(SYN_ATTACK_CHEAP, name="Water One",
                                                     damage=120, cost=1, energyTypes=(WATER,))}
    elif attacks == "partial":
        body_attacks = (SYN_ATTACK_BIG,)
        max_damage, max_cost, min_cost, min_damage = 210, 3, 3, 210
        attack_rows = {SYN_ATTACK_BIG: AttackStat(SYN_ATTACK_BIG, name="Water Three",
                                                  damage=210, cost=3,
                                                  energyTypes=(WATER, WATER, WATER))}
    else:
        body_attacks = (SYN_ATTACK_CHEAP, SYN_ATTACK_BIG)
        max_damage, max_cost, min_cost, min_damage = 210, 3, 1, 120
        attack_rows = {
            SYN_ATTACK_CHEAP: AttackStat(SYN_ATTACK_CHEAP, name="Jetting Identity-Free",
                                         damage=120, cost=1, energyTypes=(WATER,)),
            SYN_ATTACK_BIG: AttackStat(SYN_ATTACK_BIG, name="Nebula Identity-Free",
                                       damage=210, cost=3,
                                       energyTypes=(WATER, COLORLESS, COLORLESS)),
        }
    stat_rows = {
        body_id: CardStat(body_id, name="Synthetic Attacker", hp=220, energyType=WATER,
                          maxDamage=max_damage, maxDamageCost=max_cost, minAttackCost=min_cost,
                          minCostDamage=min_damage, attacks=body_attacks, retreatCost=2,
                          stage="basic", synthetic=True),
        SYN_OPP: CardStat(SYN_OPP, name="Synthetic Opponent", hp=220, maxDamage=opponent_damage,
                          maxDamageCost=(1 if opponent_damage else 0),
                          minAttackCost=(1 if opponent_damage else None), minCostDamage=opponent_damage,
                          attacks=((SYN_ATTACK_OPP,) if opponent_damage else ()), stage="basic",
                          synthetic=True),
        SYN_WATER: CardStat(SYN_WATER, name="Synthetic Water", cardType=5, energyType=WATER,
                            synthetic=True),
        SYN_FIRE: CardStat(SYN_FIRE, name="Synthetic Fire", cardType=5, energyType=FIRE,
                           synthetic=True),
        SYN_TOOL: CardStat(SYN_TOOL, name="Synthetic Mobility Tool", cardType=2,
                           retreatReduction=2, synthetic=True),
        SYN_FETCH: CardStat(SYN_FETCH, name="Synthetic Open Search", cardType=1, synthetic=True),
        SYN_BASIC: CardStat(SYN_BASIC, name="Synthetic Basic", hp=70, stage="basic", synthetic=True),
        SYN_EVOLUTION: CardStat(SYN_EVOLUTION, name="Synthetic Stage One", hp=280, stage="stage1",
                                evolvesFrom="Synthetic Attacker", maxDamage=max_damage,
                                maxDamageCost=max_cost, minAttackCost=min_cost,
                                minCostDamage=min_damage, attacks=body_attacks, synthetic=True),
    }
    if body_id != SYN_BODY:
        stat_rows[SYN_BODY] = CardStat(SYN_BODY, name="Synthetic Attacker", hp=220, stage="basic",
                                       synthetic=True)
    if opponent_damage:
        attack_rows[SYN_ATTACK_OPP] = AttackStat(SYN_ATTACK_OPP, name="Threshold Hit",
                                                  damage=opponent_damage, cost=1,
                                                  energyTypes=(WATER,))
    return stat_rows, attack_rows


@lru_cache(maxsize=None)
def synthetic_combat(attacks="multi", body_id=SYN_BODY, opponent_damage=0) -> CombatMath:
    stats, attack_rows = _stats(attacks=attacks, body_id=body_id, opponent_damage=opponent_damage)
    provider = DictCardStatProvider(stats, attacks=attack_rows)
    effects = CardEffects({
        str(SYN_FETCH): [{"kind": "fetch", "target": "basic_pokemon", "zone": "deck",
                          "amount": 1}],
        "_covers": {str(SYN_FETCH): {"covers": "full", "reason": "synthetic fetch is the whole card"}},
    })
    return CombatMath(provider, CardFunctions({}), transients=None, effects=effects)


def _model(obs, *, combat=None, needs_supplier=None, role_worth=None, deck=()):
    return StateModel.build(obs, combat=combat or synthetic_combat(), my_index=0,
                            deck=deck, needs=needs_supplier, role_worth=role_worth)


class _AttachOracle(AttachMixin):
    """Tiny audit harness around the shipped Build Standing equation; no re-expression here."""
    def __init__(self, combat):
        self.combat = combat
        self.stats = combat.stats
        self.strategy = SimpleNamespace(partners={})

    def _wincon_lines(self):
        return ()

    def _line_preevo_set(self):
        return set()


def _build_delta(model, body: dict, energy_type: int) -> float:
    """The root damage adapter over the canonical shared standing profile."""
    from common.state_value import combat_build_profile, energy_supply_for_units
    before = combat_build_profile(model, body).value_prizes
    after = combat_build_profile(
        model, body, supply=energy_supply_for_units((energy_type,))).value_prizes
    return (after - before) * currency.PRIZE_DAMAGE_RATE


def _energy_probe(name: str, *, attacks: str, energy_id: int, key: str,
                  expected_direction: str, expected_leaf: str) -> dict:
    combat = synthetic_combat(attacks)
    target = _body()
    mine = _player(active=target, hand=[_card(energy_id, 10)])
    options = [{"type": _ATTACH, "area": 2, "index": 0,
                "inPlayArea": _ACTIVE, "inPlayIndex": 0}, {"type": _END}]
    model = _model(_obs(mine=mine, options=options), combat=combat)
    after, actions = apply_sequence(model, options, [0])
    local_delta = _build_delta(model, target, WATER if energy_id == SYN_WATER else FIRE)
    search = search_snapshot(model, options, focus=[0], sequences=[[0]])
    total_delta = float(state_value(after)) - float(state_value(model))
    before_payoff = model.mine.attack_payoff(model.mine.active)
    after_payoff = after.mine.attack_payoff(after.mine.active)
    after_target = after.source_obs["current"]["players"][0]["active"][0]
    reachable_before = float(combat.best_reachable_damage(target, budget=Budget()))
    reachable_after = float(combat.best_reachable_damage(after_target, budget=Budget()))
    leaf_matches = ((expected_leaf == "positive" and total_delta > 0)
                    or (expected_leaf == "zero" and total_delta == 0))
    passed = (actions[0]["fate"] == ao.MODELLED and leaf_matches
              and ((expected_direction == "positive" and local_delta > 0)
                   or (expected_direction == "zero" and local_delta == 0)))
    local = _local(
        "common.deciders.attach.AttachMixin._attach_build_delta", "damage", 0.0, local_delta,
        working={"energy_type": WATER if energy_id == SYN_WATER else FIRE,
                  "attack_shape": attacks,
                 "leaf_payoff_attack_before": getattr(before_payoff, "attack_id", None),
                 "leaf_payoff_attack_after": getattr(after_payoff, "attack_id", None),
                  "best_reachable_damage_before": reachable_before,
                  "best_reachable_damage_after": reachable_after,
                  "delta_prizes_equivalent": local_delta / currency.PRIZE_DAMAGE_RATE,
                  "classification": "SHARED-EXACT",
                  "root_shared_parity_error": 0.0},
    )
    control = {"case": name, "passed": passed,
               "expectation": f"local={expected_direction}; leaf={expected_leaf}",
               "observed_total_delta": total_delta,
               "observed_local_delta": local_delta}
    return _case_record(name, key, model, after, actions, local=local, search=search,
                        control=control)


def energy_typed_match() -> dict:
    row = _energy_probe("energy-typed-match", attacks="single", energy_id=SYN_WATER,
                        key="synthetic:typed-water-fully-unlocks-one-water",
                        expected_direction="positive", expected_leaf="positive")
    working = row["local"]["working"]
    working["single_attack_fully_unlocked"] = (
        working["best_reachable_damage_before"] == 0.0
        and working["best_reachable_damage_after"] == 120.0)
    row["positive_control"]["passed"] = bool(
        row["positive_control"]["passed"] and working["single_attack_fully_unlocked"])
    # This control deliberately has a zero leaf: pair it to the same attach/Build instrument on the
    # live partial-cost board, where the readiness family moves positively.
    positive = energy_partial_cost()
    row["positive_control"].update({
        "case": positive["case"],
        "passed": bool(row["positive_control"]["passed"]
                       and positive["positive_control"]["passed"]
                       and positive["deltas"]["total"] > 0),
        "positive_total_delta": positive["deltas"]["total"],
        "positive_local_delta": positive["local"]["delta"],
    })
    return _jsonable(row)


def energy_typed_mismatch() -> dict:
    row = _energy_probe("energy-typed-mismatch", attacks="single", energy_id=SYN_FIRE,
                        key="synthetic:typed-fire-does-not-pay-water", expected_direction="zero",
                        expected_leaf="zero")
    positive = energy_typed_match()
    row["positive_control"].update({
        "case": positive["case"],
        "passed": bool(row["positive_control"]["passed"]
                       and positive["positive_control"]["passed"]),
        "positive_total_delta": positive["deltas"]["total"],
        "positive_local_delta": positive["local"]["delta"],
    })
    return row


def energy_partial_cost() -> dict:
    row = _energy_probe("energy-partial-cost", attacks="partial", energy_id=SYN_WATER,
                        key="synthetic:one-of-three-water", expected_direction="positive",
                        expected_leaf="positive")
    working = row["local"]["working"]
    working["partial_progress_without_unlock"] = (
        working["best_reachable_damage_before"] == 0.0
        and working["best_reachable_damage_after"] == 0.0)
    row["positive_control"]["passed"] = bool(
        row["positive_control"]["passed"] and working["partial_progress_without_unlock"])
    return _jsonable(row)


def energy_multi_attack() -> dict:
    row = _energy_probe("energy-multi-attack", attacks="multi", energy_id=SYN_WATER,
                        key="synthetic:{W}:120+{WCC}:210", expected_direction="positive",
                        expected_leaf="positive")
    leaf = float(row["deltas"]["total"])
    local_prizes = float(row["local"]["working"]["delta_prizes_equivalent"])
    combat = synthetic_combat("multi")
    before_body = _body()
    after_body = _body(energies=(WATER,), energy_ids=(SYN_WATER,))
    body_stat = combat.stats.get(before_body["id"])
    attack_rows = tuple(combat.stats.attack(attack_id) for attack_id in body_stat.attacks)
    attack_rows = tuple(attack for attack in attack_rows if attack is not None)
    cheaper = min(attack_rows, key=lambda attack: (attack.cost, -attack.damage, attack.attackId))
    larger = max(attack_rows, key=lambda attack: (attack.damage, -attack.cost, -attack.attackId))
    reachable_before = float(combat.best_reachable_damage(before_body, budget=Budget()))
    reachable_after = float(combat.best_reachable_damage(after_body, budget=Budget()))
    selected_before = row["local"]["working"]["leaf_payoff_attack_before"]
    selected_after = row["local"]["working"]["leaf_payoff_attack_after"]
    profile_model = _model(_obs(mine=_player(active=before_body)), combat=combat)
    from common.state_value import combat_build_profile, energy_supply_for_units
    shared_after = combat_build_profile(
        profile_model, before_body, supply=energy_supply_for_units((WATER,)))
    cheaper_unlocked = (reachable_before == 0.0 and reachable_after == float(cheaper.damage))
    larger_selected = selected_before == larger.attackId and selected_after == larger.attackId
    row["local"]["working"].update({
        "attack_catalog": [
            {"attack_id": attack.attackId, "cost": attack.cost, "damage": attack.damage,
             "energy_types": list(attack.energyTypes)}
            for attack in sorted(attack_rows, key=lambda attack: attack.attackId)
        ],
        "cheaper_attack_id": cheaper.attackId,
        "larger_attack_id": larger.attackId,
        "cheaper_attack_fully_unlocked": cheaper_unlocked,
        "best_reachable_damage_before": reachable_before,
        "best_reachable_damage_after": reachable_after,
        "legacy_payoff_selected_larger": larger_selected,
        "shared_winning_attack_id": shared_after.winning_attack_id,
        "shared_candidates": [candidate.as_dict() for candidate in shared_after.candidates],
        "classification": "SHARED-EXACT",
        "root_shared_parity_error": 0.0,
        "leaf_to_local_ratio": (leaf / local_prizes) if local_prizes else None,
    })
    row["positive_control"].update({
        "passed": bool(row["positive_control"]["passed"] and local_prizes > leaf > 0
                       and cheaper.cost == 1 and cheaper.damage == 120
                       and larger.cost == 3 and larger.damage == 210
                       and cheaper_unlocked and shared_after.winning_attack_id == cheaper.attackId),
        "expectation": "the one-Water attack owns the shared envelope; leaf applies existing economics",
    })
    return _jsonable(row)


def energy_removal() -> dict:
    """The exact inverse counterfactual over the same controlled snapshots."""
    combat = synthetic_combat("partial")
    options = [{"type": _ATTACH, "area": 2, "index": 0,
                "inPlayArea": _ACTIVE, "inPlayIndex": 0}, {"type": _END}]
    zero = _model(_obs(mine=_player(active=_body(), hand=[_card(SYN_WATER, 10)]),
                       options=options), combat=combat)
    one, forward_actions = apply_sequence(zero, options, [0])
    inverse = _action_row(1, None, {"audit_mutation": "remove attached Water"},
                          "controlled-fixture", {}, None, _changed(one, zero))
    forward = float(state_value(one)) - float(state_value(zero))
    backward = float(state_value(zero)) - float(state_value(one))
    local_forward = _build_delta(zero, _body(), WATER)
    local_prizes = -local_forward / currency.PRIZE_DAMAGE_RATE
    local = _local("common.deciders.attach.AttachMixin._attach_build_delta", "damage",
                   local_forward, 0.0,
                   working={"inverse_of": "energy-partial-cost", "forward_delta": local_forward,
                            "delta_prizes_equivalent": local_prizes,
                            "classification": (
                                "ALIGNED" if local_prizes == backward
                                else "LOSSY-REEXPRESSION")})
    control = {"case": "energy-partial-cost", "passed": backward < 0 and backward == -forward,
               "expectation": "removal is the exact sign inverse of the positive attach control",
               "observed_total_delta": backward, "forward_total_delta": forward,
               "forward_action_fate": forward_actions[0]["fate"]}
    return _case_record("energy-removal", "synthetic:remove-one-water", one, zero, [inverse],
                        local=local, search=_blank_search("controlled inverse has no engine menu"),
                        control=control)


def _bounced_evolution(retained_after):
    """Same evolved state with only its retained attachment returned to hand."""
    obs = copy.deepcopy(retained_after.source_obs)
    me = obs["current"]["players"][0]
    evolved = me["active"][0]
    old_energy = evolved["energyCards"][0]
    evolved["energies"] = []
    evolved["energyCards"] = []
    me["hand"] = list(me.get("hand") or ()) + [old_energy]
    me["handCount"] = len(me["hand"])
    return retained_after.rebuilt(obs), old_energy


class _EvolveOracle(EvolveMixin, AttachMixin):
    """Small harness around the shipped evolve substitution and its pure value equation."""

    def __init__(self, model, combat):
        self._state_model = model
        self.combat = combat
        self.stats = combat.stats
        self.functions = CardFunctions({})
        self.strategy = SimpleNamespace(roles={}, partners={})
        self.opponent = None
        self._opp_attack_context = None

    def _wincon_lines(self):
        return ()

    def _line_preevo_set(self):
        return set()

    @staticmethod
    def _opp_player(obs):
        current = obs.get("current") or {}
        players = current.get("players") or ()
        seat = 1 - int(current.get("yourIndex", 0))
        return players[seat] if 0 <= seat < len(players) and players[seat] else {}

    def _my_bench_raws(self, _obs):
        return list(self._state_model.mine.bench_raws)


def _evolution_equation(model, combat) -> dict:
    """Read retain and bounce through one real substitution and one controlled result-side re-read."""
    obs = model.source_obs
    raw = obs["current"]["players"][0]["active"][0]
    oracle = _EvolveOracle(model, combat)
    board = Board(turn=model.mine.turn)
    body, retained_result, retained_raw = oracle._evolve_substitution(
        obs, board, raw, SYN_EVOLUTION, is_active=True)
    bounced_raw = copy.deepcopy(retained_raw)
    bounced_raw["energies"] = []
    bounced_raw["energyCards"] = []
    bounced_result = oracle._evolve_side(
        obs, board, bounced_raw, SYN_EVOLUTION, is_active=True,
        bench=oracle._my_bench_raws(obs))
    retained_value = evolve_value(EvolveInputs(body=body, result=retained_result))
    bounced_value = evolve_value(EvolveInputs(body=body, result=bounced_result))
    return {
        "body": _jsonable(body),
        "retained_result": _jsonable(retained_result),
        "bounced_result": _jsonable(bounced_result),
        "retained_result_raw": _jsonable(retained_raw),
        "bounced_result_raw": _jsonable(bounced_raw),
        "retained_value": _jsonable(retained_value),
        "bounced_value": _jsonable(bounced_value),
    }


def evolution_retains_attachments() -> dict:
    combat = synthetic_combat("multi")
    energy_card = _card(SYN_WATER, 100)
    target = _body(energies=(WATER,), energy_ids=(SYN_WATER,))
    # Keep the same serial used by `_body`'s generated energy reference for an exact retained-card check.
    energy_card = target["energyCards"][0]
    mine = _player(active=target, hand=[_card(SYN_EVOLUTION, 20)])
    options = [{"type": _EVOLVE, "area": 2, "index": 0,
                "inPlayArea": _ACTIVE, "inPlayIndex": 0}, {"type": _END}]
    model = _model(_obs(mine=mine, options=options), combat=combat)
    after, actions = apply_sequence(model, options, [0])
    evolved = after.source_obs["current"]["players"][0]["active"][0]
    retained = evolved.get("energyCards") == [energy_card] and evolved.get("energies") == [WATER]
    bounced, bounced_energy = _bounced_evolution(after)
    paired_changed = _changed(after, bounced)
    equation = _evolution_equation(model, combat)
    retained_local = float(equation["retained_value"]["total"])
    bounced_local = float(equation["bounced_value"]["total"])
    leaf_delta = float(state_value(after)) - float(state_value(bounced))
    local = _local("common.evolve_value.evolve_value", "damage", bounced_local, retained_local,
                   working={"substitution_owner": (
                                "common.deciders.evolve.EvolveMixin._evolve_substitution"),
                            "retained_energy_serials": [c.get("serial") for c in evolved["energyCards"]],
                            "bounced_energy_serials": [],
                            "bounced_to_hand_serial": bounced_energy.get("serial"),
                            "paired_changed_dimensions": paired_changed,
                            "retained_vs_bounced_leaf_delta": leaf_delta,
                            "retained_vs_bounced_local_delta": retained_local - bounced_local,
                            "isolated_from_same_evolution": True,
                            "classification": "LOSSY-REEXPRESSION",
                            "equation": equation,
                            "policy": "retain"})
    control = {"case": "evolution-retains-attachments",
               "passed": bool(retained and "attached_energy" in paired_changed
                              and retained_local > bounced_local and leaf_delta > 0),
               "expectation": "the shipped substitution retains Energy and evolve_value prices that retained result above the paired bounce",
               "observed_total_delta": float(state_value(after)) - float(state_value(model)),
               "paired_bounce_total_delta": float(state_value(bounced)) - float(state_value(model)),
               "paired_local_delta": retained_local - bounced_local,
               "paired_leaf_delta": leaf_delta}
    return _case_record("evolution-retains-attachments", "synthetic:evolve-retain", model, after,
                        actions, local=local,
                        search=search_snapshot(model, options, focus=[0], sequences=[[0]]),
                        control=control)


def evolution_bounces_attachments() -> dict:
    """Hypothetical negative control: same evolution with the attachment moved back to hand."""
    combat = synthetic_combat("multi")
    target = _body(energies=(WATER,), energy_ids=(SYN_WATER,))
    mine = _player(active=target, hand=[_card(SYN_EVOLUTION, 20)])
    options = [{"type": _EVOLVE, "area": 2, "index": 0,
                "inPlayArea": _ACTIVE, "inPlayIndex": 0}, {"type": _END}]
    before = _model(_obs(mine=mine, options=options), combat=combat)
    retained_after, retained_actions = apply_sequence(before, options, [0])
    retained_body = _body_with_serial(retained_after, 20) or {}
    retained_ok = (retained_actions[0]["fate"] == ao.MODELLED
                   and retained_body.get("energies") == [WATER])
    after, old_energy = _bounced_evolution(retained_after)
    action = _action_row(1, None, {"audit_mutation": "bounce retained attachment"},
                         "controlled-fixture", {}, None, _changed(retained_after, after))
    equation = _evolution_equation(before, combat)
    retained_local = float(equation["retained_value"]["total"])
    bounced_local = float(equation["bounced_value"]["total"])
    retained_leaf = float(state_value(retained_after))
    bounced_leaf = float(state_value(after))
    local = _local("common.evolve_value.evolve_value", "damage", retained_local, bounced_local,
                   working={"policy": "bounce", "runtime_policy": "retain",
                            "substitution_owner": (
                                "common.deciders.evolve.EvolveMixin._evolve_substitution"),
                            "isolated_from_same_evolution": True,
                            "retained_energy_serials": [old_energy.get("serial")],
                            "bounced_energy_serials": [],
                            "bounced_to_hand_serial": old_energy.get("serial"),
                            "common_before_total": float(state_value(before)),
                            "retained_sequence_total": retained_leaf,
                            "bounced_sequence_total": bounced_leaf,
                            "retained_vs_bounced_leaf_delta": retained_leaf - bounced_leaf,
                            "retained_vs_bounced_local_delta": retained_local - bounced_local,
                            "classification": "LOSSY-REEXPRESSION",
                            "equation": equation})
    changed = set(action["changed_dimensions"])
    control = {"case": "evolution-retains-attachments",
               "passed": bool(retained_ok and "attached_energy" in changed
                              and retained_local > bounced_local and retained_leaf > bounced_leaf),
               "expectation": "the controlled bounce reverses both the shipped local evolve claimant and its leaf signal",
               "observed_total_delta": bounced_leaf - retained_leaf,
               "observed_local_delta": bounced_local - retained_local,
               "positive_total_delta": float(state_value(retained_after)) - float(state_value(before))}
    return _case_record("evolution-bounces-attachments", "synthetic:evolve-bounce-control",
                        retained_after, after, [action], local=local,
                        search=_blank_search("hypothetical attachment policy has no runtime option"),
                        control=control)


class _HealOracle(HealMixin, KoClassMixin):
    """Minimal harness joining the two shipped owners used by ``_heal_survival_gain``."""

    def __init__(self, model):
        self._state_model = model
        self._opp_attack_context = None
        self.effects = CardEffects.load()

    @staticmethod
    def _opp_active(obs):
        current = obs.get("current") or {}
        players = current.get("players") or ()
        seat = 1 - int(current.get("yourIndex", 0))
        active = players[seat].get("active") if 0 <= seat < len(players) and players[seat] else ()
        return active[0] if active else None

def _heal_probe(name: str, *, before_hp: int, after_hp: int, crosses: bool) -> dict:
    combat = synthetic_combat("single", opponent_damage=100)
    opponent = _player(active=_body(SYN_OPP, serial=50, hp=220, max_hp=220,
                                    energies=(WATER,), energy_ids=(SYN_WATER,), seat=1), seat=1)
    mine = _player(active=_body(hp=before_hp, max_hp=120))
    before = _model(_obs(mine=mine, theirs=opponent, options=()), combat=combat)
    obs = copy.deepcopy(before.source_obs)
    obs["current"]["players"][0]["active"][0]["hp"] = after_hp
    after = before.rebuilt(obs, reuse_their_side=True)
    oracle = _HealOracle(before)
    clauses = oracle.effects.clauses(HEAL_CARD)
    action = _action_row(
        1, None,
        {"audit_mutation": f"heal {after_hp - before_hp}", "effect_card_id": HEAL_CARD},
        "controlled-fixture", {"card_id": HEAL_CARD, "clauses": clauses}, None,
        _changed(before, after),
    )
    before_exposure = next((leg.value_prizes for leg in _family_result(before, "survival").legs
                            if leg.key == "exposure.rank.0"), 0.0)
    after_exposure = next((leg.value_prizes for leg in _family_result(after, "survival").legs
                           if leg.key == "exposure.rank.0"), 0.0)
    before_body = before.source_obs["current"]["players"][0]["active"][0]
    stat = combat.stats.get(before_body["id"])
    doom_averted = bool(oracle._heal_body_averts_doom(
        HEAL_CARD, stat, is_active=True, cur_hp=before_hp, incoming=100, max_hp=120))
    local_gain = float(oracle._heal_survival_gain(
        before.source_obs, before_body, stat, HEAL_CARD, after_hp, is_active=True))
    prize_branch_damage = float(currency.prize_to_damage(stat.prize_value)) if doom_averted else 0.0
    local = _local("common.deciders.heal.HealMixin._heal_survival_gain", "damage",
                   0.0, local_gain,
                   working={"incoming_damage": 100, "crosses_leaf_threshold": crosses,
                            "equation_invoked": (
                                "common.deciders.heal.HealMixin._heal_survival_gain"),
                             "restored_hp": after_hp - before_hp,
                             "leaf_exposure_before": before_exposure,
                             "leaf_exposure_after": after_exposure,
                             "effect_card_id": HEAL_CARD,
                             "effect_clauses": clauses,
                             "doom_owner": (
                                 "common.strategy.planning.ko_classes."
                                 "KoClassMixin._heal_body_averts_doom"),
                             "doom_averted": doom_averted,
                             "doom_prize_damage": prize_branch_damage,
                             "classification": "LOSSY-REEXPRESSION"})
    difference = value_difference(before, after)
    survival_delta = next(family.delta for family in difference.families
                          if family.family == "survival")
    expected_gain = float(after_hp - before_hp) + prize_branch_damage
    passed = ((after_exposure > before_exposure and survival_delta > 0) if crosses
              else (after_exposure == before_exposure and survival_delta == 0))
    passed = bool(passed and doom_averted is crosses and local_gain == expected_gain
                  and clauses == ({"kind": "heal", "amount": 40, "target": "any_pokemon",
                                   "each_of": True},))
    control = {"case": name, "passed": passed,
               "expectation": ("the local restored-HP leg is positive in both cases; only the "
                               "leaf survival family is positive across its integer threshold"),
               "observed_total_delta": survival_delta,
               "exposure_before": before_exposure, "exposure_after": after_exposure}
    return _case_record(name, f"shipped:1222-heal-{before_hp}-to-{after_hp}", before, after, [action],
                         local=local, search=_blank_search("controlled HP threshold has no root option"),
                         control=control,
                         source={"kind": "shipped-card-control", "fixture": None,
                                 "provenance": {"card_id": HEAL_CARD, "name": "Fennel"}})


def healing_crosses_threshold() -> dict:
    return _heal_probe("healing-crosses-threshold", before_hp=80, after_hp=120, crosses=True)


def healing_not_across_threshold() -> dict:
    row = _heal_probe("healing-not-across-threshold", before_hp=40, after_hp=80, crosses=False)
    positive = healing_crosses_threshold()
    row["positive_control"].update({
        "case": positive["case"],
        "passed": bool(row["positive_control"]["passed"]
                       and positive["positive_control"]["passed"]),
        "positive_total_delta": positive["deltas"]["total"],
        "positive_local_delta": positive["local"]["delta"],
    })
    return row


def mobility_retreat_tool() -> dict:
    combat = synthetic_combat("single")
    target = _body()
    mine = _player(active=target, hand=[_card(SYN_TOOL, 30)])
    options = [{"type": _ATTACH, "area": 2, "index": 0,
                "inPlayArea": _ACTIVE, "inPlayIndex": 0}, {"type": _END}]
    before = _model(_obs(mine=mine, options=options), combat=combat)
    after, actions = apply_sequence(before, options, [0])
    stat_of = combat.stats.get
    after_body = after.source_obs["current"]["players"][0]["active"][0]
    cost_before = retreat_cost.effective_retreat_cost(target, stat_of=stat_of,
                                                       my_bodies=[target], combat=combat)
    cost_after = retreat_cost.effective_retreat_cost(after_body, stat_of=stat_of,
                                                      my_bodies=[after_body], combat=combat)
    local = _local("common.retreat_cost.effective_retreat_cost", "energy-units",
                   cost_before, cost_after,
                   working={"benefit": cost_before - cost_after,
                            "classification": "LOCAL-ONLY"})
    leaf_delta = float(state_value(after)) - float(state_value(before))
    positive = mobility_retreat_enables_modeled_retreat()
    control = {"case": positive["case"],
               "passed": bool(cost_after < cost_before
                              and positive["positive_control"]["passed"]
                              and positive["positive_control"]["observed_retreat_leaf_delta"] > 0),
               "expectation": "shipped retreat oracle moves even if the absolute leaf is blind",
               "observed_total_delta": leaf_delta, "observed_local_delta": cost_after - cost_before,
               "positive_total_delta": positive["deltas"]["total"],
               "positive_local_delta": positive["local"]["delta"],
               "positive_retreat_leaf_delta": (
                   positive["positive_control"]["observed_retreat_leaf_delta"])}
    return _case_record("mobility-retreat-tool", "synthetic:retreat-2-to-0", before, after, actions,
                        local=local, search=search_snapshot(before, options, focus=[0], sequences=[[0]]),
                        control=control,
                        unread_extra=(("attached_tools",
                                       "ADR-0135: retreatReduction mobility has no absolute owner"),))


def mobility_retreat_enables_modeled_retreat() -> dict:
    """Same-instrument control: cost reduction enables a resolved, leaf-positive retreat."""
    combat = synthetic_combat("single", opponent_damage=100)
    target = _body(hp=80, max_hp=220)
    promoted = _body(SYN_BODY_CLONE, serial=2, hp=220, max_hp=220,
                     energies=(WATER,), energy_ids=(SYN_WATER,))
    opponent = _player(active=_body(SYN_OPP, serial=50, hp=220, max_hp=220,
                                    energies=(WATER,), energy_ids=(SYN_WATER,), seat=1), seat=1)
    mine = _player(active=target, bench=[promoted],
                   hand=[_card(SYN_TOOL, 31)])
    attach_options = [{"type": _ATTACH, "area": 2, "index": 0,
                       "inPlayArea": _ACTIVE, "inPlayIndex": 0}, {"type": _END}]
    before = _model(_obs(mine=mine, theirs=opponent, options=attach_options), combat=combat)
    after_tool, attach_actions = apply_sequence(before, attach_options, [0])
    retreat_options = [{"type": _RETREAT}]
    after, retreat_actions = apply_sequence(after_tool, retreat_options, [0])
    retreat_actions[0]["ordinal"] = 2
    actions = attach_actions + retreat_actions
    stat_of = combat.stats.get
    after_body = after_tool.source_obs["current"]["players"][0]["active"][0]
    cost_before = retreat_cost.effective_retreat_cost(
        target, stat_of=stat_of, my_bodies=[target], combat=combat)
    cost_after = retreat_cost.effective_retreat_cost(
        after_body, stat_of=stat_of, my_bodies=[after_body], combat=combat)
    energy_before = len(target.get("energyCards") or target.get("energies") or ())
    energy_after = len(after_body.get("energyCards") or after_body.get("energies") or ())
    affordable_before, affordable_after = energy_before >= cost_before, energy_after >= cost_after
    retreat_leaf_delta = float(state_value(after)) - float(state_value(after_tool))
    promoted_serial = after.source_obs["current"]["players"][0]["active"][0].get("serial")
    local = _local(
        "common.retreat_cost.effective_retreat_cost", "energy-units", cost_before, cost_after,
        working={"benefit": cost_before - cost_after,
                 "affordable_before": affordable_before,
                 "affordable_after": affordable_after,
                 "post_attach_retreat_fate": retreat_actions[0]["fate"],
                 "retreat_allowance_spent": bool(after.retreated),
                 "promoted_active_serial": promoted_serial,
                 "retreat_leaf_delta": retreat_leaf_delta,
                 "classification": "MODELED-POSITIVE-CONTROL"},
    )
    control = {
        "case": "mobility-retreat-enables-modeled-retreat",
        "passed": bool(all(row["fate"] == ao.MODELLED for row in actions)
                       and not affordable_before and affordable_after and after.retreated
                       and promoted_serial == 2 and retreat_leaf_delta > 0.0),
        "expectation": "the same live cost oracle enables a resolved retreat whose resulting board moves the leaf positively",
        "observed_total_delta": float(state_value(after)) - float(state_value(before)),
        "observed_retreat_leaf_delta": retreat_leaf_delta,
        "observed_local_delta": cost_after - cost_before,
    }
    return _case_record(
        "mobility-retreat-enables-modeled-retreat", "synthetic:tool-then-reasked-retreat",
        before, after, actions, local=local,
        search=search_snapshot(before, attach_options, focus=[0], sequences=[[0]]),
        control=control,
    )


def _represented_needs(obs: dict, seat: int):
    hand = tuple(c.get("id") for c in ((obs.get("current") or {}).get("players") or [])[seat]
                 .get("hand", ()) if c)
    if SYN_BASIC not in hand:
        return needs.Resolution(hand_ids=hand, eligibility=tuple(() for _ in hand))
    slot = needs.Slot("deploy_now", 8.0, 0, "synthetic-bench-demand")
    eligibility = tuple((0,) if cid == SYN_BASIC else () for cid in hand)
    return needs.Resolution(slots=(slot,), eligibility=eligibility, resupply=(0.0,), hand_ids=hand)


def _unrepresented_needs(obs: dict, seat: int):
    hand = tuple(c.get("id") for c in ((obs.get("current") or {}).get("players") or [])[seat]
                 .get("hand", ()) if c)
    present = SYN_BASIC in hand
    latent = 8.0 if present else 0.0
    return needs.Resolution(hand_ids=hand, eligibility=tuple(() for _ in hand),
                            latent_worth=latent,
                            latent_by_hand=tuple(8.0 if cid == SYN_BASIC else 0.0 for cid in hand))


def _hand_probe(name: str, supplier: Callable, represented: bool) -> dict:
    combat = synthetic_combat("single")
    mine = _player(active=_body(), hand=[_card(SYN_BASIC, 40)])
    options = [{"type": _PLAY, "index": 0}, {"type": _END}]
    before = _model(_obs(mine=mine, options=options), combat=combat,
                    needs_supplier=supplier, role_worth=lambda cid: 30.0 if cid == SYN_BASIC else 0.0)
    after, actions = apply_sequence(before, options, [0])
    before_hand, after_hand = _family_result(before, "hand"), _family_result(after, "hand")
    blegs = {leg.key: leg.value_prizes for leg in before_hand.legs}
    alegs = {leg.key: leg.value_prizes for leg in after_hand.legs}
    local_before, local_after = before_hand.value_prizes, after_hand.value_prizes
    raw_before = sum(value for key, value in blegs.items() if key != "bound_adjustment")
    raw_after = sum(value for key, value in alegs.items() if key != "bound_adjustment")
    hand_family_delta = next(family.delta for family in value_difference(before, after).families
                             if family.family == "hand")
    if represented:
        passed = (blegs["assignment_coverage"] == -blegs["slot_demand"]
                  and alegs["assignment_coverage"] == alegs["slot_demand"] == 0.0
                  and raw_before == raw_after == 0.0
                  and local_before == local_after == 0.0 and hand_family_delta == 0.0)
        classification = "retired-valid-demand"
    else:
        passed = (blegs["hand_worth"] > 0.0 and alegs["hand_worth"] == 0.0
                  and raw_before > 0.0 and raw_after == 0.0
                  and local_before > 0.0 and local_after == 0.0
                  and hand_family_delta == local_after - local_before)
        classification = "unrepresented-bench-demand"
    local = _local("common.state_value.hand", "prizes",
                   local_before, local_after,
                   working={"before_legs": blegs, "after_legs": alegs,
                             "equation": (
                                 "assignment_coverage + re_access + hand_worth - slot_demand"),
                             "raw_signed_worth_before": raw_before,
                             "raw_signed_worth_after": raw_after,
                             "conversion_and_cap_invoked": True,
                             "hand_family_delta": hand_family_delta,
                             "classification": classification})
    control = {"case": name, "passed": passed,
               "expectation": ("coverage and valid demand retire with zero signed hand delta"
                               if represented else
                                "unrepresented -8 raw Worth passes through live prize conversion"),
               "observed_total_delta": float(state_value(after)) - float(state_value(before))}
    return _case_record(name, f"synthetic:{classification}", before, after, actions, local=local,
                        search=search_snapshot(before, options, focus=[0], sequences=[[0]]),
                        control=control)


def hand_spend_retires_demand() -> dict:
    row = _hand_probe("hand-spend-retires-demand", _represented_needs, True)
    signal = _hand_probe("hand-spend-unrepresented-demand", _unrepresented_needs, False)
    row["positive_control"].update({
        "case": signal["case"],
        "passed": bool(row["positive_control"]["passed"]
                       and signal["positive_control"]["passed"]
                       and abs(signal["local"]["delta"]) > 0.0
                       and abs(signal["deltas"]["families"]["hand"]) > 0.0),
        "positive_total_delta": signal["deltas"]["total"],
        "positive_local_delta": signal["local"]["delta"],
        "positive_hand_family_delta": signal["deltas"]["families"]["hand"],
        "positive_signal_magnitude": abs(signal["local"]["delta"]),
    })
    return row


def hand_spend_unrepresented_demand() -> dict:
    return _hand_probe("hand-spend-unrepresented-demand", _unrepresented_needs, False)


def _apply_information_sequence(model, options, indices):
    """Force a revealing expectation plus ordinary actions through the same seams Composer calls."""
    stamped = [cp.stamp_origin(model, option) for option in options]
    current, rows = model, []
    for ordinal, index in enumerate(indices, 1):
        option = cp.resolve_against(current, stamped[index])
        if option is None:
            rows.append(_action_row(ordinal, index, None, ao.REFUSED,
                                    {"reason": "stamped source vanished"}))
            break
        fp = ao.option_footprint(current, option, clauses_cover=_cover(current, option))
        if fp.reveals_information:
            try:
                result = bx.expectation(current, option, score=state_value)
                choice = cp.rank_targets(current, result)
                after = choice.best.model if choice.best else None
                fate, detail = ao.MODELLED, {"resolution": result.resolution,
                                             "target_classes": len(choice.scored),
                                             "structural_reveal": True}
            except Exception as exc:  # noqa: BLE001 - a gap must remain a visible refusal
                after, fate = None, ao.REFUSED
                detail = {"reason": f"{type(exc).__name__}: {exc}"}
        else:
            after, fate, detail = _apply_one(current, option)
        changed = [] if after is None else _changed(current, after)
        rows.append(_action_row(ordinal, index, option, fate, detail, fp, changed))
        if after is None:
            break
        current = after
    return current, rows


def information_ordering() -> dict:
    combat = synthetic_combat("single")
    mine = _player(active=_body(), hand=[_card(SYN_FETCH, 40), _card(SYN_WATER, 41)],
                   deck_count=1, prizes=0)
    options = [{"type": _PLAY, "index": 0},
               {"type": _ATTACH, "area": 2, "index": 1,
                "inPlayArea": _ACTIVE, "inPlayIndex": 0}, {"type": _END}]
    before = _model(_obs(mine=mine, options=options), combat=combat, deck=(SYN_BASIC,))
    informative_first, actions = _apply_information_sequence(before, options, [0, 1])
    commitment_first, reverse_actions = _apply_information_sequence(before, options, [1, 0])
    same = zone_facts(informative_first) == zone_facts(commitment_first)
    tiers = [cp.canonical_tier(before, option) for option in options[:2]]
    search = search_snapshot(before, options, focus=[0, 1],
                             sequences=[[0, 1], [1, 0]], depth=2)
    presence = {tuple(row["sequence"]): row for row in search["candidate_presence"]}
    informative_presence = presence[(0, 1)]
    commitment_presence = presence[(1, 0)]
    informative_total = float(state_value(informative_first))
    commitment_total = float(state_value(commitment_first))
    equal_value = informative_total == commitment_total
    search_loss = bool(
        same and equal_value
        and not informative_presence["faithful_generated_as_prefix"]
        and commitment_presence["faithful_generated_as_prefix"]
        and (search["chosen"] or {}).get("sequence") == [1, 0]
    )
    finding = {
        "classification": "structural-ordering-owner",
        "search_overlay": "SEARCH-LOSS",
        "issue": 496,
        "qualifying_search_loss": search_loss,
        "valuation_gap": informative_total - commitment_total,
        "informative_first_present": informative_presence["faithful_generated_as_prefix"],
        "commitment_first_present": commitment_presence["faithful_generated_as_prefix"],
        "chosen_sequence": (search["chosen"] or {}).get("sequence"),
    }
    ordered_sequences = [
        _ordered_sequence(
            "informative then commitment", [0, 1], before, informative_first, actions,
            local=_local("common.composer.canonical_tier", "structural-tier", 0, tiers[0],
                         working={"first_step": "informative"}),
        ),
        _ordered_sequence(
            "commitment then informative", [1, 0], before, commitment_first, reverse_actions,
            local=_local("common.composer.canonical_tier", "structural-tier", 0, tiers[1],
                         working={"first_step": "commitment"}),
        ),
    ]
    local = _local("common.composer.canonical_tier", "structural-tier", tiers[0], tiers[1],
                   working={"same_final_state": same,
                             "structural_ordering_owner": "composer.canonical_tier:TIER_INFORMATIVE",
                            "informative_first": [0, 1], "commitment_first": [1, 0],
                             "reveal_predicate": bool(ao.option_footprint(
                                 before, options[0], clauses_cover=True).reveals_information),
                             "reverse_action_fates": [a["fate"] for a in reverse_actions],
                             "ordered_sequences": ordered_sequences,
                             "finding": finding})
    control = {"case": "information-ordering",
                "passed": (same and tiers[0] == cp.TIER_INFORMATIVE
                            and tiers[1] == cp.TIER_COMMITMENT
                            and all(a["fate"] == ao.MODELLED for a in actions + reverse_actions)
                            and search_loss),
                "expectation": ("equal-value structural-ordering owner plus qualifying #496 "
                                "SEARCH-LOSS overlay"),
                "observed_total_delta": informative_total - float(state_value(before)),
                "valuation_gap": informative_total - commitment_total,
                "qualifying_search_loss": search_loss}
    return _case_record("information-ordering", "synthetic:same-final-structural-order",
                         before, informative_first, actions, local=local,
                         search=search, control=control)


def equivalent_identities() -> dict:
    original_combat = synthetic_combat("multi")
    original_options = [{"type": _ATTACH, "area": 2, "index": 0,
                         "inPlayArea": _ACTIVE, "inPlayIndex": 0}, {"type": _END}]
    original_before = _model(_obs(mine=_player(active=_body(),
                                                hand=[_card(SYN_WATER, 10)]),
                                  options=original_options), combat=original_combat)
    original_after, _original_actions = apply_sequence(original_before, original_options, [0])
    combat = synthetic_combat("multi", SYN_BODY_CLONE)
    mine = _player(active=_body(SYN_BODY_CLONE), hand=[_card(SYN_WATER, 10)])
    options = [{"type": _ATTACH, "area": 2, "index": 0,
                "inPlayArea": _ACTIVE, "inPlayIndex": 0}, {"type": _END}]
    before = _model(_obs(mine=mine, options=options), combat=combat)
    after, actions = apply_sequence(before, options, [0])
    clone_delta = float(state_value(after)) - float(state_value(before))
    original_delta = float(state_value(original_after)) - float(state_value(original_before))
    original_local_delta = _build_delta(original_before, _body(SYN_BODY), WATER)
    clone_local_delta = _build_delta(before, _body(SYN_BODY_CLONE), WATER)
    original_stat = original_combat.stats.get(SYN_BODY)
    attack_costs = [
        list(attack.energyTypes)
        for attack in sorted(
            (original_combat.attack_stat(attack_id)
             for attack_id in (getattr(original_stat, "attacks", ()) or ())),
            key=lambda attack: (attack.cost, attack.attackId))
        if attack is not None
    ]
    local = _local("common.deciders.attach.AttachMixin._attach_build_delta", "damage",
                   original_local_delta, clone_local_delta,
                   working={"original_body_id": SYN_BODY, "clone_body_id": SYN_BODY_CLONE,
                            "mechanic_signature": {
                                "attached_energy_type": WATER,
                                "attack_energy_types": attack_costs,
                            },
                            "original_leaf_total_delta": original_delta,
                            "clone_leaf_total_delta": clone_delta,
                            "original_local_damage_delta": original_local_delta,
                            "clone_local_damage_delta": clone_local_delta})
    control = {"case": "energy-multi-attack",
               "passed": (clone_delta == original_delta
                          and clone_local_delta == original_local_delta
                          and actions[0]["fate"] == ao.MODELLED),
               "expectation": "renaming the body preserves both leaf and Build Standing deltas",
               "observed_total_delta": clone_delta, "original_total_delta": original_delta,
               "original_local_delta": original_local_delta,
               "clone_local_delta": clone_local_delta}
    return _case_record("equivalent-identities", "synthetic:identity-metamorphic", before, after,
                        actions, local=local,
                        search=search_snapshot(before, options, focus=[0], sequences=[[0]]),
                        control=control)


def refused_effect() -> dict:
    stats, attack_rows = _stats(attacks="single")
    stats[REFUSED_CARD] = CardStat(
        REFUSED_CARD, name="Lumiose Galette", cardType=1, synthetic=True)
    combat = CombatMath(DictCardStatProvider(stats, attacks=attack_rows), CardFunctions({}),
                        transients=None, effects=CardEffects.load())
    options = [{"type": _PLAY, "index": 0}, {"type": _END}]
    before = _model(_obs(mine=_player(active=_body(), hand=[_card(REFUSED_CARD, 50)]),
                         options=options), combat=combat)
    after, actions = apply_sequence(before, options, [0])
    clauses_cover = combat.effects.clauses_cover(REFUSED_CARD)
    actions[0]["detail"].update({"card_id": REFUSED_CARD, "clauses_cover": clauses_cover})
    positive_combat = synthetic_combat("single")
    positive_options = [{"type": _ATTACH, "area": 2, "index": 0,
                         "inPlayArea": _ACTIVE, "inPlayIndex": 0}, {"type": _END}]
    positive_before = _model(_obs(mine=_player(active=_body(),
                                                hand=[_card(SYN_WATER, 10)]),
                                  options=positive_options), combat=positive_combat)
    _positive_after, positive_actions = apply_sequence(positive_before, positive_options, [0])
    local = _local("none - shipped effect is refused", "unknown", None, None,
                   working={"classification": "UNKNOWN/REFUSED",
                            "card_id": REFUSED_CARD,
                            "clauses_cover": clauses_cover,
                            "refusal_scope": actions[0]["detail"].get("scope"),
                            "declared_writes": actions[0]["declared_writes"],
                            "reason": actions[0]["detail"].get("reason")})
    control = {"case": "energy-typed-match",
               "passed": (actions[0]["fate"] == ao.REFUSED and clauses_cover is False
                          and bool(actions[0]["declared_writes"])
                          and positive_actions[0]["fate"] == ao.MODELLED),
               "expectation": "refusal is unknown, while a modelled action moves through the same instrument",
               "observed_total_delta": 0.0}
    return _case_record("refused-effect", "shipped:1153-partial-condition-removal", before, after,
                        actions,
                        local=local, search=search_snapshot(before, options, focus=[0], sequences=[[0]]),
                        control=control,
                        source={"kind": "shipped-card-control", "fixture": None,
                                "provenance": {"card_id": REFUSED_CARD,
                                               "name": "Lumiose Galette"}})


# -- PR #490 corpus evidence -------------------------------------------------------------------


def load_mega_starmie_fixture(path: Path = FIXTURE) -> dict:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if fixture.get("schema_version") != "composer-sensitivity-fixture/1":
        raise ValueError(f"{path}: unsupported fixture schema {fixture.get('schema_version')!r}")
    if fixture.get("key") != "91393371-69":
        raise ValueError(f"{path}: expected PR #490 frame 91393371-69")
    return fixture


def _body_with_serial(model, serial: int) -> dict | None:
    obs = model.source_obs or {}
    players = ((obs.get("current") or {}).get("players")) or []
    seat = int(model.my_index)
    me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    return next((body for body in list(me.get("active") or ()) + list(me.get("bench") or ())
                 if body and body.get("serial") == serial), None)


def mega_starmie_wally_attach() -> dict:
    fixture = load_mega_starmie_fixture()
    from train.tune import _build_pilot

    pilot, _seeds = _build_pilot(fixture["agent"])
    obs = fixture["obs"]
    model = pilot._leaf_state_model(obs, int(fixture["provenance"]["seat"]))
    options = list((obs.get("select") or {}).get("option") or ())
    order = fixture["action_indices"]
    correct_indices = list(order["wally_then_attach"])
    reverse_indices = list(order["attach_then_wally"])
    correct_after, correct_actions = apply_sequence(model, options, correct_indices)
    wally_after, wally_actions = apply_sequence(model, options, [order["wally"]])
    # The full sequence's second row retains the ROOT-stamped held-Water identity (serial 63).
    # Re-stamping option index 6 after Wally would instead point at the just-bounced serial 71.
    isolated_after = correct_after
    isolated_actions = [copy.deepcopy(correct_actions[1])]
    isolated_actions[0]["ordinal"] = 1
    reverse_after, reverse_actions = apply_sequence(model, options, reverse_indices)

    search = search_snapshot(model, options,
                             focus=[order["wally"], order["attach_mega_starmie"]],
                             sequences=[correct_indices, reverse_indices],
                             k=cp.BEAM_WIDTH, epsilon=cp.EPSILON, depth=cp.SEQUENCE_DEPTH,
                             shed=pilot.cost_shed_indices)
    decision = pilot.explain(obs)
    attach_rows = ((getattr(decision, "attach_working", None) or {}).get("eq") or ())
    root_attach_working = next((row for row in attach_rows
                                if row.get("i") == order["attach_mega_starmie"]), {})
    root_build_delta = float(root_attach_working.get("build", 0.0))
    target_serial = fixture["evidence"]["target_body_serial"]
    root_body = _body_with_serial(model, target_serial) or {}
    wally_body = _body_with_serial(wally_after, target_serial) or {}
    isolated_body = _body_with_serial(isolated_after, target_serial) or {}
    isolated_build_delta = _build_delta(wally_after, wally_body, WATER)
    wally_total = float(state_value(wally_after))
    isolated_total = float(state_value(isolated_after))
    isolated_leaf_delta = isolated_total - wally_total
    correct_body = _body_with_serial(correct_after, fixture["evidence"]["target_body_serial"]) or {}
    reverse_body = _body_with_serial(reverse_after, fixture["evidence"]["target_body_serial"]) or {}
    correct_total = float(state_value(correct_after))
    reverse_total = float(state_value(reverse_after))
    presence = {tuple(row["sequence"]): row for row in search["candidate_presence"]}
    forward_present = presence.get(tuple(correct_indices), {})
    reverse_present = presence.get(tuple(reverse_indices), {})
    one_ply = {row["index"]: row for row in search["one_ply"]}
    root_attach_leaf_delta = one_ply.get(order["attach_mega_starmie"], {}).get("chosen_delta")
    ordered_sequences = [
        _ordered_sequence(
            "Wally then attach", correct_indices, model, correct_after, correct_actions,
            local=_local(
                "common.deciders.attach.AttachMixin._attach_build_delta", "damage",
                0.0, isolated_build_delta,
                working={"isolated_transition": "Wally-only to attach",
                         "final_target_energy_serials": [
                             c.get("serial") for c in correct_body.get("energyCards", ())]},
            ),
        ),
        _ordered_sequence(
            "attach then Wally", reverse_indices, model, reverse_after, reverse_actions,
            local=_local(
                "common.deciders.attach.AttachMixin._attach_build_delta", "damage",
                0.0, root_build_delta,
                working={"isolated_transition": "root attach before Wally",
                         "retained_at_final": False,
                         "final_target_energy_serials": [
                             c.get("serial") for c in reverse_body.get("energyCards", ())]},
            ),
        ),
    ]
    local = _local(
        "common.deciders.attach.AttachMixin._attach_build_delta", "damage", 0.0,
        isolated_build_delta,
        working={
            "isolated_attach_after_wally": {
                "before_total": wally_total,
                "after_total": isolated_total,
                "leaf_delta": isolated_leaf_delta,
                "local_build_delta": isolated_build_delta,
                "target_energy_serials_before": [
                    card.get("serial") for card in wally_body.get("energyCards", ())],
                "target_energy_serials_after": [
                    card.get("serial") for card in isolated_body.get("energyCards", ())],
                "matches_full_forward_state": zone_facts(isolated_after) == zone_facts(correct_after),
                "wally_action_fates": [row["fate"] for row in wally_actions],
                "attach_action_fates": [row["fate"] for row in isolated_actions],
            },
            "root_attach_trace": root_attach_working,
            "root_attach_build_delta": root_build_delta,
            "root_attach_leaf_one_ply_delta": root_attach_leaf_delta,
            "root_target_energy_serials": [
                card.get("serial") for card in root_body.get("energyCards", ())],
            "attach_local_prizes_equivalent": (
                isolated_build_delta / currency.PRIZE_DAMAGE_RATE),
            "classification": "LOSSY-REEXPRESSION",
            "ordered_sequences": ordered_sequences,
            "provenance": fixture["provenance"],
        },
    )
    correct_serials = [c.get("serial") for c in correct_body.get("energyCards", ())]
    reverse_serials = [c.get("serial") for c in reverse_body.get("energyCards", ())]
    control = {
        "case": "mega-starmie-wally-attach",
        "passed": bool(
            all(row["fate"] == ao.MODELLED
                for row in wally_actions + isolated_actions + correct_actions + reverse_actions)
            and zone_facts(isolated_after) == zone_facts(correct_after)
            and [card.get("serial") for card in wally_body.get("energyCards", ())] == []
            and [card.get("serial") for card in isolated_body.get("energyCards", ())]
            == [fixture["evidence"]["held_water_serial"]]
            and correct_serials == [fixture["evidence"]["held_water_serial"]]
            and reverse_serials == []
            and correct_total > reverse_total
            and isolated_build_delta > 0 and isolated_leaf_delta > 0
        ),
        "expectation": ("after Wally bounces the existing Water, attaching the held Water is an "
                        "isolated zero-to-one transition and the retained-Water final state wins; "
                        "default search admission is owned by Issue #496"),
        "observed_total_delta": isolated_leaf_delta,
        "isolated_local_delta": isolated_build_delta,
        "root_sequence_total_delta": correct_total - float(state_value(model)),
        "reverse_total_delta": reverse_total - float(state_value(model)),
    }
    return _case_record(
        "mega-starmie-wally-attach", "91393371-69", wally_after, isolated_after,
        isolated_actions,
        local=local, search=search, control=control,
        source={"kind": "corpus-fixture", "fixture": str(FIXTURE.relative_to(REPO)).replace("\\", "/"),
                "provenance": fixture["provenance"]},
    )


# Stable semantic order: related controls stay adjacent; no menu-generation order leaks here.
CASE_BUILDERS: Mapping[str, Callable[[], dict]] = {
    "energy-typed-match": energy_typed_match,
    "energy-typed-mismatch": energy_typed_mismatch,
    "energy-partial-cost": energy_partial_cost,
    "energy-multi-attack": energy_multi_attack,
    "energy-removal": energy_removal,
    "evolution-retains-attachments": evolution_retains_attachments,
    "evolution-bounces-attachments": evolution_bounces_attachments,
    "healing-crosses-threshold": healing_crosses_threshold,
    "healing-not-across-threshold": healing_not_across_threshold,
    "mobility-retreat-tool": mobility_retreat_tool,
    "mobility-retreat-enables-modeled-retreat": mobility_retreat_enables_modeled_retreat,
    "hand-spend-retires-demand": hand_spend_retires_demand,
    "hand-spend-unrepresented-demand": hand_spend_unrepresented_demand,
    "information-ordering": information_ordering,
    "equivalent-identities": equivalent_identities,
    "refused-effect": refused_effect,
    "mega-starmie-wally-attach": mega_starmie_wally_attach,
}


def case_names() -> tuple[str, ...]:
    return tuple(CASE_BUILDERS)


def run_case(name: str) -> dict:
    try:
        builder = CASE_BUILDERS[name]
    except KeyError as exc:
        raise KeyError(f"unknown sensitivity case {name!r}; choose one of {', '.join(case_names())}") from exc
    return builder()


def _named_proofs(rows: Sequence[dict]) -> dict:
    """Source-derived proof blocks consumed by the static report; no diagnostic literal is copied."""
    by_name = {row["case"]: row for row in rows}
    proofs = {}

    mega = by_name.get("mega-starmie-wally-attach")
    if mega is not None:
        if not mega["positive_control"].get("passed"):
            raise ValueError("Mega Starmie proof cannot be emitted from a failed control")
        ordered = {row["label"]: row
                   for row in mega["local"]["working"].get("ordered_sequences", ())}
        if set(ordered) != {"Wally then attach", "attach then Wally"}:
            raise ValueError("Mega Starmie proof requires both named ordered sequences")
        forward, reverse = ordered["Wally then attach"], ordered["attach then Wally"]
        if len(forward["indices"]) != 2 or reverse["indices"] != list(reversed(forward["indices"])):
            raise ValueError("Mega Starmie proof orders are not exact reverses")
        wally_index, attach_index = forward["indices"]
        one_ply = {row["index"]: row for row in mega["search"]["one_ply"]}
        presence = {tuple(row["sequence"]): row
                    for row in mega["search"]["candidate_presence"]}
        if wally_index not in one_ply or attach_index not in one_ply \
                or tuple(forward["indices"]) not in presence \
                or tuple(reverse["indices"]) not in presence:
            raise ValueError("Mega Starmie proof is missing one-ply or ordered-search telemetry")

        def root_action(index: int) -> dict:
            row = one_ply[index]
            return {key: row[key] for key in (
                "index", "rank", "ranked", "chosen_delta", "admitted", "in_beam",
                "admission_reason", "kth_delta", "cutoff_margin", "margin_to_kth")}

        def order_proof(row: dict) -> dict:
            found = presence[tuple(row["indices"])]
            serials = list(row["local"]["working"].get("final_target_energy_serials", ()))
            return {
                "indices": list(row["indices"]),
                "before_total_prizes": row["before"]["total"],
                "after_total_prizes": row["after"]["total"],
                "total_delta_prizes": row["deltas"]["total"],
                "local_delta_damage": row["local"]["delta"],
                "target_water_serials": serials,
                "target_water_count": len(serials),
                "action_fates": [action["fate"] for action in row["actions"]],
                "generated_as_prefix": found["generated_as_prefix"],
                "faithful_generated_as_prefix": found["faithful_generated_as_prefix"],
                "survived_terminal_dominance": found["survived_terminal_dominance"],
                "final_score": found["final_score"],
            }

        isolated = mega["local"]["working"].get("isolated_attach_after_wally") or {}
        required_isolated = {
            "before_total", "after_total", "leaf_delta", "local_build_delta",
            "target_energy_serials_before", "target_energy_serials_after",
            "matches_full_forward_state",
        }
        if not required_isolated <= set(isolated):
            raise ValueError("Mega Starmie proof lacks the isolated Wally-to-attach transition")
        proofs["mega_starmie_wally_attach"] = {
            "case": mega["case"],
            "key": mega["key"],
            "source": mega["source"],
            "root_total_prizes": forward["before"]["total"],
            "root_one_ply": {
                "wally": root_action(wally_index),
                "attach_mega_starmie": root_action(attach_index),
            },
            "orders": {
                "wally_then_attach": order_proof(forward),
                "attach_then_wally": order_proof(reverse),
            },
            "isolated_attach_after_wally": {
                "before_total_prizes": isolated["before_total"],
                "after_total_prizes": isolated["after_total"],
                "local_delta_damage": isolated["local_build_delta"],
                "leaf_delta_prizes": isolated["leaf_delta"],
                "target_water_serials_before": isolated["target_energy_serials_before"],
                "target_water_serials_after": isolated["target_energy_serials_after"],
                "matches_full_forward_state": isolated["matches_full_forward_state"],
            },
        }

    identity = by_name.get("equivalent-identities")
    if identity is not None:
        if not identity["positive_control"].get("passed"):
            raise ValueError("identity-independence proof cannot be emitted from a failed control")
        working = identity["local"]["working"]
        local_equal = (working["original_local_damage_delta"]
                       == working["clone_local_damage_delta"])
        leaf_equal = (working["original_leaf_total_delta"]
                      == working["clone_leaf_total_delta"])
        proofs["identity_independent_attach"] = {
            "case": identity["case"],
            "key": identity["key"],
            "mechanic_signature": working["mechanic_signature"],
            "original": {
                "body_id": working["original_body_id"],
                "local_delta_damage": working["original_local_damage_delta"],
                "leaf_delta_prizes": working["original_leaf_total_delta"],
            },
            "clone": {
                "body_id": working["clone_body_id"],
                "local_delta_damage": working["clone_local_damage_delta"],
                "leaf_delta_prizes": working["clone_leaf_total_delta"],
            },
            "local_delta_equal": local_equal,
            "leaf_delta_equal": leaf_equal,
            "identity_independent": bool(
                local_equal and leaf_equal
                and working["original_body_id"] != working["clone_body_id"]),
        }

    if set(case_names()) <= set(by_name) and set(proofs) != {
            "mega_starmie_wally_attach", "identity_independent_attach"}:
        raise ValueError("complete sensitivity sweep lacks a required named proof")
    return _jsonable(proofs)


def _diagnostic_summary(rows: Sequence[dict], inventory) -> dict:
    """Derive report diagnostics; counts never come from prose or checked-in report literals."""
    import composer_value_coverage as coverage

    required = {"case", "key", "local", "deltas", "search", "actions", "positive_control"}
    if not rows or any(not required <= set(row) for row in rows):
        raise ValueError("sensitivity rows are empty or violate the case schema")
    names = [row["case"] for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("sensitivity rows contain duplicate case names")
    if inventory is None:
        raise ValueError("a static coverage Inventory is required for the diagnostic join")
    problems = tuple(coverage.validate_inventory(inventory))
    if problems:
        raise ValueError("invalid static coverage inventory: " + "; ".join(problems))
    if not isinstance(getattr(inventory, "source_sha", None), str) \
            or len(inventory.source_sha) != 40:
        raise ValueError("static coverage inventory lacks a 40-character source SHA")

    candidate_rows = [candidate for row in rows
                      for candidate in row["search"]["candidate_presence"]]
    classifications = [row["local"]["working"].get("classification") for row in rows]
    search_findings = []
    disagreements = []
    ownership_cache = {}
    for row in rows:
        finding = row["local"]["working"].get("finding") or {}
        if finding.get("qualifying_search_loss"):
            search_findings.append({"case": row["case"], **finding})

        classification = row["local"]["working"].get("classification")
        if classification not in {"LOSSY-REEXPRESSION", "LOCAL-ONLY"}:
            continue
        local_delta = row["local"].get("delta")
        leaf_delta = row["deltas"].get("total")
        if not isinstance(local_delta, (int, float)) or not isinstance(leaf_delta, (int, float)):
            continue
        working = row["local"]["working"]
        local_prizes = working.get("attach_local_prizes_equivalent")
        if local_prizes is None:
            local_prizes = working.get("delta_prizes_equivalent")
        if local_prizes is None and row["local"].get("unit") == "damage":
            local_prizes = float(local_delta) / currency.PRIZE_DAMAGE_RATE
        if local_prizes is None and row["local"].get("unit") == "prizes":
            local_prizes = float(local_delta)
        dimensions = sorted({dimension for action in row["actions"]
                             for dimension in action.get("changed_dimensions", ())})
        declared_writes = sorted({dimension for action in row["actions"]
                                  for dimension in action.get("declared_writes", ())})
        joined_dimensions = sorted(set(dimensions) | set(declared_writes))
        static_join = []
        for dimension in joined_dimensions:
            ownership = ownership_cache.get(dimension)
            if ownership is None:
                ownership = coverage.owner_summary(dimension, inventory=inventory)
                ownership_cache[dimension] = ownership
            static_join.append({
                "mechanic_key": f"state-dimension:{dimension}",
                "dimension": dimension,
                "absolute_owners": ownership.absolute_owners,
                "terminal_owners": ownership.terminal_owners,
                "local_owners": ownership.local_owners,
            })
        disagreements.append(_jsonable({
            "case": row["case"], "key": row["key"], "owner": row["local"]["owner"],
            "classification": classification,
            "changed_dimensions": dimensions,
            "declared_writes": declared_writes,
            "static_join": static_join,
            "local_delta": local_delta, "local_unit": row["local"]["unit"],
            "local_prizes_equivalent": local_prizes,
            "leaf_total_delta_prizes": leaf_delta,
            "disagreement_prizes": (None if local_prizes is None
                                     else float(local_prizes) - float(leaf_delta)),
        }))

    counts = {
        "cases": len(rows),
        "controls_passed": sum(bool(row["positive_control"]["passed"]) for row in rows),
        "controls_failed": sum(not bool(row["positive_control"]["passed"]) for row in rows),
        "candidate_sequences": len(candidate_rows),
        "faithful_candidate_sequences": sum(
            bool(row.get("faithful_generated_as_prefix")) for row in candidate_rows),
        "coverage_gap_candidate_sequences": sum(bool(row.get("coverage_gaps"))
                                                  for row in candidate_rows),
        "refused_gap_placeholders": sum(bool(row.get("refused_gap_placeholder_only"))
                                         for row in candidate_rows),
        "ordered_sequences": sum(len(row["local"]["working"].get("ordered_sequences") or ())
                                 for row in rows),
        "qualifying_search_losses": len(search_findings),
        "lossy_reexpressions": classifications.count("LOSSY-REEXPRESSION"),
        "local_only": classifications.count("LOCAL-ONLY"),
        "unknown_refused": sum(any(action["fate"] == ao.REFUSED for action in row["actions"])
                                for row in rows),
        "local_leaf_disagreements": len(disagreements),
    }
    proofs = _named_proofs(rows)
    return _jsonable({
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "source_sha": _git_sha(),
        "inventory": {"schema_version": inventory.schema_version,
                      "source_sha": inventory.source_sha,
                      "records": len(inventory.records)},
        "counts": counts,
        "findings": {"search_loss": search_findings,
                     "local_leaf_disagreement": disagreements},
        "proofs": proofs,
        "beam_loss_frequency": {
            "proven": False,
            "reason": ("controlled probes establish a qualifying line, not a representative "
                       "frequency denominator"),
        },
    })


def diagnostic_summary(inventory=None, *, names: Sequence[str] | None = None,
                       cases: Sequence[dict] | None = None) -> dict:
    """Reusable, fail-closed static-report join.

    Pass the already-built static ``Inventory`` to keep its validation/source SHA coupled to the
    derived sensitivity evidence.  ``cases`` is for callers that already ran the deterministic sweep.
    """
    if names is not None and cases is not None:
        raise ValueError("pass names or cases, not both")
    selected = case_names() if names is None else tuple(names)
    joined_inventory = _coverage_inventory() if inventory is None else inventory
    token = _INVENTORY_CONTEXT.set(joined_inventory)
    try:
        rows = list(cases) if cases is not None else [run_case(name) for name in selected]
        return _diagnostic_summary(rows, joined_inventory)
    finally:
        _INVENTORY_CONTEXT.reset(token)


def build_report(names: Sequence[str] | None = None) -> dict:
    selected = case_names() if names is None else tuple(names)
    inventory = _coverage_inventory()
    token = _INVENTORY_CONTEXT.set(inventory)
    try:
        rows = [run_case(name) for name in selected]
    finally:
        _INVENTORY_CONTEXT.reset(token)
    return _jsonable({
        "schema_version": SCHEMA_VERSION,
        "source_sha": _git_sha(),
        "seed": SEED,
        "command": "python tools/train/composer_sensitivity.py --all --out reports/composer-sensitivity.json",
        "diagnostic_summary": _diagnostic_summary(rows, inventory),
        "cases": rows,
    })


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--all", action="store_true", help="run every locked sensitivity control")
    choice.add_argument("--case", choices=case_names(), help="run one named control")
    parser.add_argument("--out", type=Path, help="write stable JSON (stdout when omitted)")
    args = parser.parse_args(argv)

    payload = build_report() if args.all else build_report([args.case])
    if args.out:
        _write_json(args.out, payload)
        print(f"-> {args.out}")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
