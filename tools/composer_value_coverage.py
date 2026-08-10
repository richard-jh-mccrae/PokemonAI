"""Issue #493: deterministic mechanic -> value -> Composer coverage census.

This is an audit tool, not a runtime registry.  Its source populations come from the shipped card
stores and the runtime registries; the small authored tables in this module only join those source
facts to semantic owners.  A source addition therefore either enters the inventory or fails a
closed completeness check -- it cannot disappear because a report fixture forgot to mention it.

Usage::

    python tools/composer_value_coverage.py --out docs/plans/composer-valuation-coverage.md
    python tools/composer_value_coverage.py --check docs/plans/composer-valuation-coverage.md
    python tools/composer_value_coverage.py --json reports/composer-valuation-coverage.json
"""
from __future__ import annotations

import argparse
import ast
import collections
import dataclasses
import hashlib
import json
import re
import runpy
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType, SimpleNamespace


_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
_TOOLS = _ROOT / "tools"
for _path in (_SRC, _TOOLS):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import apply_seam_coverage as apply_census                              # noqa: E402
from common import apply_option as seam                                 # noqa: E402
from common import snapshot_coverage as snapshots                       # noqa: E402
from common import state_value                                          # noqa: E402
from common.scouting import provider as stat_provider                    # noqa: E402
from common.scouting.provider import AttackStat, CardStat                # noqa: E402
from common.strategy.context import (                                    # noqa: E402
    _ABILITY, _ATTACH, _ATTACHED_TOOL, _ATTACK, _CARD, _DISCARD_IN_PLAY,
    _END, _ENERGY, _ENERGY_CARD, _EVOLVE, _NO, _NUMBER, _PLAY, _RETREAT,
    _SKILL, _SPECIAL_CONDITION, _YES,
)


SCHEMA_VERSION = 5
AUDIT_BASE_SHA = "5a7c8f696913379316bf6c3fcf82aca7f4d84d3b"
DEFAULT_OUT = _ROOT / "docs" / "plans" / "composer-valuation-coverage.md"
BEGIN = "<!-- BEGIN GENERATED: tools/composer_value_coverage.py -->"
END = "<!-- END GENERATED -->"

SHARED_EXACT = "SHARED-EXACT"
LEAF_ONLY = "LEAF-ONLY"
LOCAL_ONLY = "LOCAL-ONLY"
LOSSY_REEXPRESSION = "LOSSY-REEXPRESSION"
DUPLICATE_CONFLICT = "DUPLICATE/CONFLICT"
UNVALUED_MODELLED = "UNVALUED-MODELED"
DELIBERATE_ZERO = "DELIBERATE-ZERO"
UNKNOWN_REFUSED = "UNKNOWN/REFUSED"
SEARCH_LOSS = "SEARCH-LOSS"
CLASSIFICATIONS = (
    SHARED_EXACT,
    LEAF_ONLY,
    LOCAL_ONLY,
    LOSSY_REEXPRESSION,
    DUPLICATE_CONFLICT,
    UNVALUED_MODELLED,
    DELIBERATE_ZERO,
    UNKNOWN_REFUSED,
    SEARCH_LOSS,
)


class CoverageError(RuntimeError):
    """The source population no longer closes over the authored audit join."""


def _ordered(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}))


@dataclass(frozen=True)
class Exposure:
    """Prioritisation only.  Zero exposure never removes a completeness record."""

    cards: int = 0
    mechanic_sites: int = 0
    decks: int = 0
    deck_copies: int = 0
    meta_builds: int = 0
    meta_copies: float = 0.0
    corpus_frames: int = 0


@dataclass(frozen=True)
class AuditRecord:
    """The locked Issue #493 audit-only schema, represented with immutable tuples."""

    mechanic_key: str
    source_kind: str
    source_symbol_or_site: str
    transition_fate: str
    written_dimensions: tuple[str, ...] = ()
    absolute_owners: tuple[str, ...] = ()
    local_owners: tuple[str, ...] = ()
    runtime_callers: tuple[str, ...] = ()
    leaf_path: tuple[str, ...] = ()
    search_path: tuple[str, ...] = ()
    # Valuation ownership and search survival are orthogonal.  ``classification`` stays the
    # mechanism's valuation class; a proved beam loss is carried as this overlay instead of erasing
    # the reason the later state was valuable in the first place.
    classification: str = UNKNOWN_REFUSED
    search_overlay: str = ""
    evidence: tuple[str, ...] = ()
    deliberate_ruling: str = ""
    exposure: Exposure = Exposure()
    live_owner: str = ""

    def __post_init__(self) -> None:
        if self.classification not in CLASSIFICATIONS or self.classification == SEARCH_LOSS:
            raise ValueError(f"unknown coverage class {self.classification!r}")
        if self.classification == DELIBERATE_ZERO and not self.deliberate_ruling.strip():
            raise ValueError(f"{self.mechanic_key}: a deliberate zero requires a citation")
        if self.search_overlay not in {"", SEARCH_LOSS}:
            raise ValueError(f"{self.mechanic_key}: invalid search overlay {self.search_overlay!r}")
        if self.search_overlay == SEARCH_LOSS and not any(
                "probe" in item.lower() for item in self.evidence):
            raise ValueError(f"{self.mechanic_key}: SEARCH-LOSS requires probe evidence")
        for field in ("written_dimensions", "absolute_owners", "local_owners", "runtime_callers",
                      "leaf_path", "evidence"):
            value = getattr(self, field)
            if value != _ordered(value):
                raise ValueError(f"{self.mechanic_key}: {field} must be a sorted unique tuple")


@dataclass(frozen=True)
class EquationCandidate:
    key: str
    path: str
    line: int
    disposition: str
    reason: str
    runtime_callers: tuple[str, ...] = ()
    absolute_owners: tuple[str, ...] = ()
    local_owners: tuple[str, ...] = ()
    classification: str = ""


@dataclass(frozen=True)
class ProviderField:
    """Closed declaration ledger; only observed-nondefault rows become mechanic records."""

    class_name: str
    field_name: str
    observed_nondefault: bool
    observed_cards: tuple[int, ...]
    observed_sites: int
    override_sites: int
    runtime_callers: tuple[str, ...]
    declaration_only_reason: str = ""


@dataclass(frozen=True)
class DimensionOwnership:
    dimension: str
    absolute_owners: tuple[str, ...]
    terminal_owners: tuple[str, ...]
    local_owners: tuple[str, ...]
    unread_reasons: tuple[str, ...]
    unknown_reasons: tuple[str, ...]


@dataclass(frozen=True)
class Inventory:
    schema_version: int
    source_sha: str
    records: tuple[AuditRecord, ...]
    populations: tuple[tuple[str, int], ...]
    equation_candidates: tuple[EquationCandidate, ...]
    provider_fields: tuple[ProviderField, ...]
    registry_identity: str = ""

    def records_by_written_dimension(self) -> Mapping[str, tuple[AuditRecord, ...]]:
        grouped: dict[str, list[AuditRecord]] = collections.defaultdict(list)
        for record in self.records:
            for dimension in record.written_dimensions:
                grouped[dimension].append(record)
        return MappingProxyType({
            dimension: tuple(sorted(records, key=_record_key))
            for dimension, records in sorted(grouped.items())
        })

    def owner_summary(self, dimension: str) -> DimensionOwnership:
        records = self.records_by_written_dimension().get(dimension, ())
        # A multi-write clause/site owns one economic consequence, not every Cartesian
        # (owner, dimension) pair in its aggregate row.  The one-dimensional WRITABLE record is the
        # authoritative join for sensitivity lookup; other rows contribute only unread evidence.
        authority = tuple(record for record in records
                          if record.source_kind == "writable-state"
                          and record.written_dimensions == (dimension,))
        owners = {owner for record in authority for owner in record.absolute_owners}
        terminal = {owner for owner in owners if owner.startswith("terminal:")}
        absolute = owners - terminal
        local = {owner for record in authority for owner in record.local_owners}
        unread = {
            evidence
            for record in records
            if not record.absolute_owners and record.classification != UNKNOWN_REFUSED
            for evidence in record.evidence
        }
        unknown = {
            evidence
            for record in records
            if record.classification == UNKNOWN_REFUSED
            for evidence in record.evidence
        }
        return DimensionOwnership(
            dimension=dimension,
            absolute_owners=_ordered(absolute),
            terminal_owners=_ordered(terminal),
            local_owners=_ordered(local),
            unread_reasons=_ordered(unread),
            unknown_reasons=_ordered(unknown),
        )

    def population(self, name: str) -> int:
        return dict(self.populations)[name]

    def as_dict(self) -> dict:
        return _jsonable(self)


def with_search_loss(record: AuditRecord, *probe_evidence: str) -> AuditRecord:
    """Return ``record`` with a proved SEARCH-LOSS overlay while retaining its valuation class."""
    evidence = _ordered((*record.evidence, *probe_evidence))
    if not any("probe" in item.lower() for item in probe_evidence):
        raise ValueError("SEARCH-LOSS overlay requires named probe evidence")
    return dataclasses.replace(record, search_overlay=SEARCH_LOSS, evidence=evidence)


@dataclass(frozen=True)
class SourceSite:
    """Immutable copy of the legacy census projection plus a stable per-card ordinal."""

    card_id: int
    ordinal: int
    name: str
    category: str
    kind: int
    kind_name: str
    label: str
    fate: str
    report_class: str
    cause: str
    note: str
    family: str
    expressible: bool
    clauses_json: str
    has_effect: bool

    def as_legacy_row(self) -> dict:
        return {
            "card_id": self.card_id,
            "name": self.name,
            "category": self.category,
            "kind": self.kind,
            "site": self.label,
            "fate": self.fate,
            "class": self.report_class,
            "cause": self.cause,
            "note": self.note,
            "family": self.family,
            "expressible": self.expressible,
            "clauses": json.loads(self.clauses_json),
        }


@dataclass(frozen=True)
class PositiveControl:
    pool_cards: int
    sites: int
    matched: bool
    legacy_digest: str
    census_digest: str
    fate_counts: tuple[tuple[str, int], ...]


# Explicit enum spellings avoid reverse-looking-up unrelated integer constants in context.py.
OPTION_KINDS: tuple[tuple[int, str], ...] = (
    (_NUMBER, "NUMBER"),
    (_YES, "YES"),
    (_NO, "NO"),
    (_CARD, "CARD"),
    (_ATTACHED_TOOL, "ATTACHED_TOOL"),
    (_ENERGY_CARD, "ENERGY_CARD"),
    (_ENERGY, "ENERGY"),
    (_PLAY, "PLAY"),
    (_ATTACH, "ATTACH"),
    (_EVOLVE, "EVOLVE"),
    (_ABILITY, "ABILITY"),
    (_DISCARD_IN_PLAY, "DISCARD_IN_PLAY"),
    (_RETREAT, "RETREAT"),
    (_ATTACK, "ATTACK"),
    (_END, "END"),
    (_SKILL, "SKILL"),
    (_SPECIAL_CONDITION, "SPECIAL_CONDITION"),
)
KIND_NAMES = MappingProxyType(dict(OPTION_KINDS))


# Snapshot-zone ids and TermFamily.reads deliberately are different vocabularies.  This is the
# authored semantic join the existing registries cannot derive by string equality.
ZONE_OWNERS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "my_discard_contents": ("state:readiness",),
    "their_discard_contents": ("state:survival",),
    "my_hand_ids": ("state:hand", "state:readiness", "state:development"),
    "their_hand_size": ("state:threat",),
    "my_deck_count": (),
    "their_deck_count": (),
    "deck_odds": ("state:hand", "state:development", "state:readiness"),
    "my_prizes": ("state:prize_race",),
    "their_prizes": ("state:prize_race",),
    "stadium": ("state:survival", "state:threat", "state:readiness"),
    "bodies_in_play": ("state:survival", "state:threat", "state:readiness", "state:development"),
    "attached_energy": ("state:survival", "state:threat", "state:readiness", "terminal:attack_ev"),
    "damage_counters": ("state:survival", "state:threat", "terminal:attack_ev"),
    "allowance_energy_attached": ("state:readiness", "state:threat"),
    "allowance_supporter_played": ("state:readiness", "state:threat"),
    "allowance_ability_used": (),
    # Conditional by Tool class: damageBoost Tools enter the shared damage oracle; retreat-only
    # fields remain ADR-0135 local-only and hpBonus is separately represented through HP/clocks.
    "attached_tools": ("state:readiness", "state:threat", "terminal:attack_ev"),
    "special_conditions": (),
    "allowance_retreat_used": (),
    "transient_grants": ("state:survival", "state:readiness", "terminal:attack_ev"),
    "bench_occupancy": ("state:development",),
    "allowance_stadium_played": (),
    "this_turn_damage_boosts": ("state:readiness", "state:threat", "terminal:attack_ev"),
    "new_in_play": (),
    "deck_order": (),
})

ZONE_LOCAL_OWNERS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "my_discard_contents": ("common.needs.removal_score", "common.hold_value.hold_price"),
    "their_discard_contents": ("common.deciders.deny.DenyMixin._deny_strip_delta_tiebreak",),
    "my_hand_ids": ("common.needs.assignment_value", "common.hold_value.hold_price"),
    "their_hand_size": (),
    "my_deck_count": (),
    "their_deck_count": (),
    "deck_odds": ("common.board_expectation.expectation",),
    # `strategy.objectives.race_values` is attack-sequence wall arithmetic; despite its name it
    # does not consume either player's remaining Prize count.  Those counts are leaf-only.
    "my_prizes": (),
    "their_prizes": (),
    "stadium": ("common.deciders.tactical.TacticalMixin._stadium_hp_shift",),
    "bodies_in_play": ("common.deploy_value.deploy_value", "common.evolve_value.evolve_value",
                       "common.promote_retreat_value.promote_value"),
    "attached_energy": ("common.deciders.attach.AttachMixin._attach_value",
                        "common.strategy.combat_math.reach.ReachMixin.readiness_p"),
    "damage_counters": ("common.deciders.heal.HealMixin._heal_survival_gain",
                        "common.strategy.combat_math.clocks.ClockMixin.survival_clock"),
    "allowance_energy_attached": ("common.deciders.attach.AttachMixin._attach_value",),
    "allowance_supporter_played": (),
    "allowance_ability_used": (),
    "attached_tools": ("common.deciders.attach.AttachMixin._tool_attach_value",),
    "special_conditions": (),
    "allowance_retreat_used": ("common.promote_retreat_value.promote_value",),
    "transient_grants": ("common.strategy.combat_math.reach.ReachMixin.readiness_p",),
    "bench_occupancy": ("common.deploy_value.deploy_value",),
    "allowance_stadium_played": (),
    "this_turn_damage_boosts": ("common.strategy.combat_math.reach.ReachMixin.best_reachable_damage",),
    "new_in_play": (),
    "deck_order": (),
})

# Search/legality reads are independent of scalar valuation ownership.  Only source-proved Composer
# reads are named; an unowned dimension no longer receives a fictional state-value path.
ZONE_SEARCH_CONSUMERS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "allowance_energy_attached": ("composer:_still_legal@305",),
    "allowance_supporter_played": ("composer:_still_legal@313",),
    "allowance_ability_used": ("composer:_still_legal@294",),
    "allowance_retreat_used": ("composer:_still_legal@297",),
    "allowance_stadium_played": ("composer:_still_legal@315",),
    "attached_tools": ("composer:_still_legal@304",),
    "bench_occupancy": ("composer:_still_legal@317",),
    "new_in_play": ("composer:_still_legal@308",),
    "stadium": ("composer:_still_legal@315",),
})

EXACT_ZONES = frozenset()

# Empty write sets are dispatch/parameter mechanics, not evidence of zero value.
EMPTY_CLAUSE_JOIN: Mapping[str, tuple[tuple[str, ...], tuple[str, ...], str]] = MappingProxyType({
    "coin": (("state:hand", "state:development"), ("common.board_expectation._coin_expectation",),
             LOSSY_REEXPRESSION),
    "stadium_static": (("state:survival", "state:threat", "state:readiness"), (), LEAF_ONLY),
    "stadium_trigger": (("state:survival", "state:threat", "state:readiness"), (), LEAF_ONLY),
    "damage_reduction": (("state:survival", "terminal:attack_ev"),
                         ("common.strategy.damage.compute_active_damage",), LOSSY_REEXPRESSION),
    "damage_boost": (("state:readiness", "state:threat", "terminal:attack_ev"),
                     ("common.strategy.damage.compute_active_damage",), LOSSY_REEXPRESSION),
    "prevent_damage": (("state:survival", "terminal:attack_ev"),
                       ("common.strategy.damage.compute_active_damage",), LOSSY_REEXPRESSION),
})


COMPOSER_SEARCH_CONSUMERS: tuple[tuple[str, str, str], ...] = (
    ("common.state_model:semantic_state_key", "exact modeled-state identity", DELIBERATE_ZERO),
    ("common.composer:frontier_key", "exact frontier identity", DELIBERATE_ZERO),
    ("common.composer:canonical_tier", "structural ordering", DELIBERATE_ZERO),
    ("common.option_equivalence:option_equivalence", "sibling equivalence", DELIBERATE_ZERO),
    ("common.option_equivalence:class_representatives", "representative collapse", DELIBERATE_ZERO),
    ("common.composer:commutative_blocks", "commutative canonicalisation", DELIBERATE_ZERO),
    ("common.composer:_one_ply", "one-ply ordering", LEAF_ONLY),
    ("common.composer:_rank", "one-ply rank", LEAF_ONLY),
    ("common.composer:_expand_all", "depth-wide sequence expansion", LEAF_ONLY),
    ("common.composer:_deduplicate_nodes", "exact frontier deduplication", DELIBERATE_ZERO),
    ("common.composer:_admission_score", "one-action admission estimate", LEAF_ONLY),
    ("common.composer:_retain_nodes", "single depth-wide cutoff", LEAF_ONLY),
    ("common.composer:compose_reference", "bounded reference search", LEAF_ONLY),
    ("common.composer:selection_key", "final tie ordering", LEAF_ONLY),
    ("common.composer:_selection_candidates", "terminal dominance and ties", LEAF_ONLY),
    ("common.composer:terminal_ev", "terminal value", LEAF_ONLY),
    ("common.composer:continuation_ev", "continuation value", LEAF_ONLY),
    ("common.composer:_stop_here", "stop-here terminal zero", DELIBERATE_ZERO),
)

SEARCH_ZERO_RULINGS: Mapping[str, tuple[str, str]] = MappingProxyType({
    "common.state_model:semantic_state_key": (
        "ADR-0138: only full exact modeled-state equality may collapse a frontier node", "ADR-0138"),
    "common.composer:frontier_key": (
        "ADR-0138: remaining legal semantic actions and boundary context are part of equality", "ADR-0138"),
    "common.composer:canonical_tier": (
        "ADR-0095: information precedes commitment when equal end states cannot carry reveal value",
        "ADR-0095",
    ),
    "common.option_equivalence:option_equivalence": (
        "Issues #263/#385: only exact sibling identity may collapse one-ply options",
        "Issues #263/#385",
    ),
    "common.option_equivalence:class_representatives": (
        "Issues #263/#385: an exact sibling class consumes one stable representative",
        "Issues #263/#385",
    ),
    "common.composer:commutative_blocks": (
        "Issue #385: canonical order is zero-valued only for footprint-proven commutativity",
        "Issue #385",
    ),
    "common.composer:_deduplicate_nodes": (
        "ADR-0138: proven-equal results merge only after every conflicting transition executes", "ADR-0138"),
    "common.composer:_stop_here": (
        "ADR-0129: a deliberate stop-here carries exactly zero terminal EV and no continuation",
        "ADR-0129",
    ),
})

# Search helpers consume these registered owners, directly or through their candidate/node scalar.
# Keeping this join explicit avoids presenting an invented ``composed-score`` family as a value
# owner.  Structural/zero-valued helpers intentionally have no entry.
_ALL_STATE_OWNERS = tuple(sorted(f"state:{family.name}" for family in state_value.REGISTRY))
SEARCH_CONSUMER_OWNERS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "common.composer:_one_ply": (*_ALL_STATE_OWNERS, "terminal:attack_ev"),
    "common.composer:_rank": (*_ALL_STATE_OWNERS, "terminal:attack_ev"),
    "common.composer:_expand_all": (*_ALL_STATE_OWNERS, "terminal:attack_ev"),
    "common.composer:_admission_score": (*_ALL_STATE_OWNERS, "terminal:attack_ev"),
    "common.composer:_retain_nodes": (*_ALL_STATE_OWNERS, "terminal:attack_ev"),
    "common.composer:compose_reference": (*_ALL_STATE_OWNERS, "terminal:attack_ev"),
    "common.composer:selection_key": (*_ALL_STATE_OWNERS, "terminal:attack_ev"),
    "common.composer:_selection_candidates": (*_ALL_STATE_OWNERS, "terminal:attack_ev"),
    "common.composer:terminal_ev": ("terminal:attack_ev",),
    "common.composer:continuation_ev": ("terminal:attack_ev",),
})

_EQUATION_TOKENS = ("value", "marginal", "standing", "readiness", "equity", "worth", "payoff", "score")
_EXPLICIT_EQUATIONS = frozenset({
    "common.board_expectation:_coin_expectation",
    "common.board_expectation:_draw_window_expectation",
    "common.board_expectation:_dig_expectation",
    "common.board_expectation:expectation",
    "common.deciders.heal:HealMixin._heal_survival_gain",
    "common.deciders.deny:DenyMixin._lock_sequence_cost",
    "common.deciders.attach:AttachMixin._attach_build_delta",
    "common.state_value:combat_build_profile",
    "common.state_value:combat_realization",
    "common.state_value:readiness_supply_delta",
    "common.deciders.heal:HealMixin._heal_bounce_cost",
    "common.hold_value:hold_price",
    "common.retreat_cost:effective_retreat_cost",
    "common.strategy.combat_math.clocks:ClockMixin.survival_clock",
    "common.strategy.combat_math.energy:EnergyMixin._attack_slots",
    "common.strategy.combat_math.reach:ReachMixin.best_affordable_ko_value",
})

# Exact semantic joins only.  An unlisted local owner defaults to LOCAL-ONLY; it never gains a
# fictional ``state:semantic-counterpart`` merely because its filename resembles a leaf concept.
# Values are (valuation class, real registered counterpart owners, route, technical evidence).
EQUATION_SEMANTICS: Mapping[str, tuple[str, tuple[str, ...], str, str]] = MappingProxyType({
    "common.apply_option:Expectation.best": (
        LOSSY_REEXPRESSION, _ALL_STATE_OWNERS, "#494",
        "maximum aggregation over registered state_value outcomes recomposes all state families"),
    "common.apply_option:Expectation.expected": (
        LOSSY_REEXPRESSION, _ALL_STATE_OWNERS, "#494",
        "probability-weighted aggregation over registered state_value outcomes recomposes all families"),
    "common.board_choice:_build_standing": (
        SHARED_EXACT, ("state:readiness",), "#495",
        "board choice is a damage-currency adapter over combat_build_profile"),
    "common.board_choice:rank_retreat": (
        LOSSY_REEXPRESSION,
        ("state:prize_race", "state:readiness", "state:survival", "state:threat",
         "terminal:attack_ev"), "#494",
        "CHOICE_REGISTRY retreat prefilter recomposes promote/prize/build terms at a local horizon"),
    "common.board_expectation:_coin_expectation": (
        LOSSY_REEXPRESSION, ("state:development", "state:hand"), "#494",
        "local information expectation is not an end-state oracle"),
    "common.board_expectation:_dig_expectation": (
        LOSSY_REEXPRESSION, ("state:development", "state:hand"), "#494",
        "local information expectation is not an end-state oracle"),
    "common.board_expectation:_draw_window_expectation": (
        LOSSY_REEXPRESSION, ("state:development", "state:hand"), "#494",
        "local information expectation is not an end-state oracle"),
    "common.board_expectation:expectation": (
        LOSSY_REEXPRESSION, ("state:development", "state:hand"), "#494",
        "local information expectation is not an end-state oracle"),
    "common.deciders.attach:AttachMixin._attach_build_delta": (
        SHARED_EXACT, ("state:readiness",), "#495",
        "exact before/after combat_build_profile difference crossed only by PRIZE_DAMAGE_RATE"),
    "common.state_value:combat_build_profile": (
        SHARED_EXACT, ("state:readiness",), "#495",
        "canonical per-attack persistent build owner consumed by root and readiness"),
    "common.state_value:combat_realization": (
        SHARED_EXACT, ("state:readiness",), "#495",
        "canonical build/current/future envelope consumed by readiness and runtime adapters"),
    "common.state_value:readiness_supply_delta": (
        SHARED_EXACT, ("state:readiness",), "#495",
        "exact capped readiness-family marginal used by weighted Needs and dig/evolve consumers"),
    "common.state_value:position_state_value": (
        SHARED_EXACT, ("state:readiness", "state:survival"), "#500",
        "canonical attack-realization plus nonterminal body-exposure position projection"),
    "common.state_value:active_position_potential": (
        SHARED_EXACT, ("state:readiness",), "#500",
        "canonical best legal current-turn pivot option owned by readiness"),
    "common.state_value:active_position_delta": (
        SHARED_EXACT, ("state:readiness",), "#500",
        "exact before/after marginal of canonical pivot-option ownership"),
    "common.deciders.attach:AttachMixin._attach_readiness": (
        LOSSY_REEXPRESSION, ("state:readiness",), "#495",
        "attach readiness is a local marginal over a separate leaf composition"),
    "common.deciders.attach:AttachMixin._attach_value": (
        LOSSY_REEXPRESSION, ("state:readiness",), "#495",
        "attach marginal and leaf readiness are separately composed"),
    "common.deciders.attach:AttachMixin._burst_capped_tonight": (
        LOSSY_REEXPRESSION, ("state:readiness", "terminal:attack_ev"), "#495",
        "local reusable-Energy/KO burst cap differs from readiness and terminal attack horizons"),
    "common.deciders.attach:AttachMixin._build_standing": (
        LOSSY_REEXPRESSION, ("state:readiness",), "#495",
        "Build Standing selects and scales attack progress differently from readiness"),
    "common.deciders.attach:AttachMixin._tool_attach_value": (
        LOSSY_REEXPRESSION, ("state:readiness",), "#500",
        "Tool tactical projects the canonical active-position readiness delta"),
    "common.deciders.heal:HealMixin._heal_survival_gain": (
        LOSSY_REEXPRESSION, ("state:survival",), "#492 backlog",
        "continuous restored-HP/prize denial versus the leaf's integer survival clock"),
    "common.deciders.heal:HealMixin._heal_bounce_cost": (
        LOSSY_REEXPRESSION, ("state:readiness", "terminal:attack_ev"), "#495",
        "local immediate damage forfeiture and leaf readiness/terminal EV use different horizons"),
    "common.deciders.deny:DenyMixin._lock_sequence_cost": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "live tactical damage-scale next-turn lock cost versus terminal attack_ev's "
        "prize-denominated lock leg"),
    "common.deciders.deny:DenyMixin._denial_play_tactical": (
        LOSSY_REEXPRESSION, ("state:readiness", "state:threat"), "#494",
        "local play-score scaling of typed strip relevance differs from absolute composition"),
    "common.deciders.deny:DenyMixin._denial_target_tactical": (
        LOSSY_REEXPRESSION, ("state:readiness", "state:threat"), "#494",
        "local target-score scaling of typed strip relevance differs from absolute composition"),
    "common.deciders.evolve:EvolveMixin._evolve_income_delta": (
        LOSSY_REEXPRESSION, ("state:readiness",), "#495",
        "local readiness-probability delta is composed separately from the absolute readiness leaf"),
    "common.deciders.deploy:DeployMixin._deploy_accel_unlock": (
        LOSSY_REEXPRESSION, ("state:readiness",), "#495",
        "local recovery-unlock damage credit is separately composed from absolute readiness"),
    "common.deciders.deploy:DeployMixin._deploy_exposure_prizes": (
        LOSSY_REEXPRESSION,
        ("state:prize_race", "state:survival", "terminal:attack_ev"), "#494",
        "local bench-path prize delta differs from survival, prize-race, and terminal composition"),
    "common.deciders.hand:HandMixin._refresh_swing": (
        LOSSY_REEXPRESSION, ("state:hand", "state:threat"), "#494",
        "local cycle/shed/strip/fresh/gift equation and the hand/threat leaves use different "
        "inputs and units"),
    "common.deciders.needs:NeedsMixin._item_hold_price": (
        LOSSY_REEXPRESSION, ("state:hand",), "#494",
        "local damage-denominated spend price projects the absolute hand assignment ledger"),
    "common.deciders.needs:NeedsMixin._general_liquidity": (
        LOSSY_REEXPRESSION, ("state:hand",), "#494",
        "local latent-Worth liquidity multiplier is one projection of the absolute hand ledger"),
    "common.deciders.promote:PromoteRetreatMixin._promote_closure": (
        LOSSY_REEXPRESSION, ("state:readiness",), "#495",
        "local damage-times-readiness delta and the absolute readiness leaf compose different horizons"),
    "common.deciders.promote:PromoteRetreatMixin._promote_tempo_step": (
        LOSSY_REEXPRESSION, ("state:survival", "state:threat"), "#494",
        "local incoming-curve step is recomposed by survival and threat"),
    "common.deciders.promote:PromoteRetreatMixin._promote_wall_progress": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local multi-turn wall progress and terminal one-ply attack EV use different horizons"),
    "common.deciders.snipe:SnipeMixin._snipe_brief_priority": (
        LOSSY_REEXPRESSION, ("state:threat",), "#494",
        "local Brief priority is a separate ordering projection of target threat"),
    "common.deciders.snipe:SnipeMixin._snipe_brief_tiebreak": (
        LOSSY_REEXPRESSION, ("state:threat",), "#494",
        "local strict-maximum Brief tiebreak differs from the absolute threat aggregation"),
    "common.deciders.snipe:SnipeMixin._snipe_ko_dominator": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local KO_SCORE dominator and terminal attack_ev independently price the bench KO"),
    "common.deciders.snipe:SnipeMixin._snipe_relevance_tactical": (
        LOSSY_REEXPRESSION,
        ("state:prize_race", "state:survival", "state:threat", "terminal:attack_ev"), "#494",
        "local damage-scale projection of conjunctive target relevance differs from absolute values"),
    "common.deciders.snipe:SnipeMixin._read_modulated_forward": (
        LOSSY_REEXPRESSION, ("state:threat",), "#494",
        "local Read-confidence forward-damage modulation differs from absolute threat aggregation"),
    "common.deciders.snipe:SnipeMixin._snipe_tera_veto": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local negative-KO_SCORE Tera veto and terminal attack_ev use different eligibility paths"),
    "common.deciders.lethal:LethalMixin._grab_enabler_lethal_tactical": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local KO_SCORE-plus-prize enabler equation and terminal attack_ev use different units/legs"),
    "common.deciders.lethal:LethalMixin._grab_retreat_tool_lethal_tactical": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local KO_SCORE-plus-prize retreat-Tool equation and terminal attack_ev use different units/legs"),
    "common.deciders.lethal:LethalMixin._grab_lethal_tactical": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local KO_SCORE-plus-prize grab equation and terminal attack_ev independently compose the KO"),
    "common.deciders.lethal:LethalMixin._attach_retreat_tool_lethal_tactical": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local attach/retreat-Tool KO equation and terminal attack_ev independently compose the KO"),
    "common.deciders.lethal:LethalMixin._attach_lethal_tactical": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local attach-to-KO equation and terminal attack_ev independently compose the KO"),
    "common.deciders.lethal:LethalMixin._retreat_to_lethal_tactical": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local retreat-to-KO equation and terminal attack_ev independently compose the KO"),
    "common.deciders.lethal:LethalMixin._boost_lethal_tactical": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local damage-boost KO equation and terminal attack_ev independently compose the KO"),
    "common.deciders.tactical:TacticalMixin._tactical": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "closed-form local attack/KO/prize score and terminal attack_ev independently compose combat"),
    "common.deciders.tactical:TacticalMixin._copied_attack_tactical": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "copied-attack KO/prize/rider equation and terminal attack_ev independently compose combat"),
    "common.deciders.tactical:TacticalMixin._copy_top_tactical": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "top-card copied-attack maximum and terminal attack_ev use different candidate horizons"),
    "common.deciders.tactical:TacticalMixin._self_return_escape_credit": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local denied-prize escape credit is absent from terminal attack_ev's self-return model"),
    "common.deciders.tactical:TacticalMixin._top_deck_tactical": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "top-deck KO floor/copy score and terminal attack_ev independently price the attack"),
    "common.deciders.board_build:BoardMixin._typed_boost_total": (
        LOSSY_REEXPRESSION, ("state:readiness", "state:threat", "terminal:attack_ev"), "#494",
        "local typed Tool-boost total and shared damage profiles feed separately composed valuations"),
    "common.deciders.lines:LineMixin._bench_wincon_prize_value": (
        LOSSY_REEXPRESSION, ("state:survival", "terminal:attack_ev"), "#494",
        "local Bench win-condition prize selector is not the survival clock or terminal KO payoff"),
    "common.deciders.lines:LineMixin._wincon_prize_value": (
        LOSSY_REEXPRESSION, ("state:survival", "terminal:attack_ev"), "#494",
        "local strategy-role prize selector is not the survival clock or terminal KO payoff"),
    "common.deck_value:deck_card_worth": (
        LOCAL_ONLY, (), "#494",
        "hidden-pool Worth equation is consumed by local board expectation, not an absolute family"),
    "common.deck_value:deck_draw_worth": (
        LOCAL_ONLY, (), "#494",
        "blind-draw Worth equation is consumed by local board expectation, not an absolute family"),
    "common.deploy_value:deploy_value": (
        LOSSY_REEXPRESSION,
        ("state:development", "state:hand", "state:prize_race", "state:readiness",
         "state:survival", "terminal:attack_ev"), "#494",
        "local assignment, acceleration, and prize-exposure terms recompose absolute families"),
    "common.evolve_value:EvolveBody.p_arrive": (
        LOSSY_REEXPRESSION, ("state:readiness",), "#495",
        "local halved arming probability is recomposed by the absolute readiness leaf"),
    "common.evolve_value:EvolveBody.p_survive": (
        LOSSY_REEXPRESSION, ("state:survival",), "#494",
        "local arm-versus-KO survival probability and the survival clock use different horizons"),
    "common.evolve_value:EvolveBody.deploy": (
        LOSSY_REEXPRESSION,
        ("state:development", "state:readiness", "state:survival"), "#495",
        "local immediate/forward deploy maximum recomposes development, readiness, and survival"),
    "common.evolve_value:evolve_value": (
        LOSSY_REEXPRESSION, ("state:development", "state:readiness", "state:survival"), "#495",
        "local deploy and readiness-income delta recomposes development, readiness, and survival"),
    "common.hold_value:hold_price": (
        LOSSY_REEXPRESSION, ("state:hand",), "#494",
        "local hold/removal price and the signed hand ledger are separately composed"),
    "common.needs:assignment_value": (
        LOSSY_REEXPRESSION, ("state:hand",), "#494",
        "assignment coverage is one signed leg of the absolute hand ledger"),
    "common.needs:keep_v2": (
        LOSSY_REEXPRESSION, ("state:hand",), "#494",
        "per-card assignment marginal is one local projection of the absolute hand ledger"),
    "common.needs:set_keep_v2": (
        LOSSY_REEXPRESSION, ("state:hand",), "#494",
        "set assignment marginal is one local projection of the absolute hand ledger"),
    "common.needs:pitch_gain": (
        LOSSY_REEXPRESSION, ("state:hand",), "#494",
        "pitch-fuel credit is netted locally while the hand leaf composes the full assignment"),
    "common.needs:phase_scale": (
        LOSSY_REEXPRESSION, ("state:survival", "state:threat"), "#494",
        "local prize-race phase multiplier is separately composed into survival/threat decisions"),
    "common.strategy.planning.gamble:GambleMixin._gamble_det_baseline": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local deterministic tactical/damage baseline and terminal attack EV use different horizons"),
    "common.strategy.planning.gamble:GambleMixin._composed_line_p": (
        LOSSY_REEXPRESSION, ("state:readiness", "terminal:attack_ev"), "#495",
        "local KO-line probability ratio recomposes readiness and terminal attack feasibility"),
    "common.strategy.planning.gamble:GambleMixin._item_enabler_cost": (
        LOSSY_REEXPRESSION, ("state:hand",), "#494",
        "local Supporter-slot enabler cost credit is one projection of the hand ledger"),
    "common.strategy.planning.wins:WinsMixin._retreat_shortfall": (
        LOCAL_ONLY, (), "#492 backlog",
        "ADR-0135 mobility shortfall is intentionally local-only"),
    "common.strategy.planning.turn_line:_composed_rank": (
        LOSSY_REEXPRESSION,
        ("state:prize_race", "state:survival", "terminal:attack_ev"), "#494",
        "local expected-prize/survival ordering key differs from absolute and terminal composition"),
    "common.needs:deploy_marginal": (
        LOSSY_REEXPRESSION, ("state:development", "state:hand"), "#494",
        "local deploy assignment marginal spans two separately composed leaf families"),
    "common.needs:removal_score": (
        LOSSY_REEXPRESSION, ("state:hand", "state:readiness"), "#494",
        "local removal price spans hand and readiness with different units"),
    "common.promote_retreat_value:promote_value": (
        LOSSY_REEXPRESSION,
        ("state:prize_race", "state:readiness", "state:threat", "terminal:attack_ev"), "#500",
        "sub-lethal yield, closure, tempo, and fatal residual excludes canonical position terms"),
    "common.promote_retreat_value:PromoteBody.my_yield": (
        LOSSY_REEXPRESSION, ("state:readiness", "state:threat"), "#495",
        "local reachable-damage/acceleration yield recomposes readiness and threat"),
    "common.promote_retreat_value:PromoteBody.tempo_denied": (
        LOSSY_REEXPRESSION, ("state:threat",), "#494",
        "local item-lock tempo ceiling is one projection of the absolute threat curve"),
    "common.promote_retreat_value:PromoteBody.fatal": (
        LOSSY_REEXPRESSION, ("state:prize_race", "terminal:attack_ev"), "#494",
        "local KO_SCORE fatal band and prize-race/terminal endgame values use different scales"),
    "common.promote_retreat_value:RetreatSide.retreat_cost": (
        LOCAL_ONLY, (), "#492 backlog",
        "ADR-0135 mobility cost has no absolute Tool/retreat-marker owner"),
    "common.retreat_cost:effective_retreat_cost": (
        SHARED_EXACT, ("state:readiness",), "#500",
        "canonical legal-retreat input consumed by active-position readiness"),
    "common.retreat_cost:attached_retreat_delta": (
        SHARED_EXACT, ("state:readiness",), "#500",
        "canonical Tool mobility input consumed by effective_retreat_cost"),
    "common.currency:target_value_to_worth": (
        LOCAL_ONLY, (), "#494",
        "explicit prize-to-Worth seam conversion used by the local Needs resolver; no absolute "
        "state family consumes this converted scalar"),
    "common.state_model:MySide._forward_payoff": (
        SHARED_EXACT, ("state:development",), "#494",
        "the development leaf consumes this exact zone-aware ForwardPayoff through "
        "MySide.forward_payoff"),
    "common.state_model:MySide._role_worth_of": (
        SHARED_EXACT, ("state:development", "state:hand", "state:readiness"), "#494",
        "development/readiness body relevance and the Needs callback consume this exact role-Worth "
        "resolver through MySide.role_worth"),
    "common.state_model:_SideBase.attack_payoff": (
        SHARED_EXACT, ("state:readiness",), "#494",
        "the readiness leaf and board-choice code consume the same payable-attack oracle"),
    "common.strategy.combat_math.forward:ForwardLineMixin.forward_payoff_terms": (
        LOCAL_ONLY, (), "#494",
        "opponent forward-line denial equation; state:development is deliberately my-side only"),
    "common.strategy.combat_math.budget:Budget.realising_p": (
        SHARED_EXACT, ("state:readiness",), "#495",
        "local and absolute readiness paths consume the same typed Budget assignment probability"),
    "common.strategy.combat_math.harvest:HarvestMixin.bench_snipe_bonus": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local capped damage-rider tiebreak and terminal prize-denominated rider value are separate equations"),
    "common.strategy.combat_math.harvest:HarvestMixin.bench_spread_bonus": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local capped damage-rider tiebreak and terminal prize-denominated rider value are separate equations"),
    "common.strategy.combat_math.harvest:HarvestMixin.snipe_ko_prizes": (
        SHARED_EXACT, ("terminal:attack_ev",), "#494",
        "StateModel._attack_profile and Tactical consume the same exact integer prize oracle"),
    "common.strategy.combat_math.harvest:HarvestMixin.spread_ko_prizes": (
        SHARED_EXACT, ("terminal:attack_ev",), "#494",
        "StateModel._attack_profile and Tactical consume the same exact integer prize oracle"),
    "common.strategy.combat_math.clocks:ClockMixin.incoming": (
        LOSSY_REEXPRESSION, ("state:survival",), "#494",
        "local one-step damage reads and survival's accumulated integer clock recompose this oracle"),
    "common.strategy.combat_math.clocks:ClockMixin._reach_form_damage": (
        LOSSY_REEXPRESSION, ("state:survival",), "#494",
        "per-form incoming damage is consumed only by the classified survival incoming equation"),
    "common.strategy.combat_math.clocks:ClockMixin.turns_to_afford": (
        LOSSY_REEXPRESSION, ("state:readiness",), "#495",
        "local integer arming clock is halved/composed by the absolute readiness family"),
    "common.strategy.combat_math.clocks:ClockMixin.turns_to_afford_attack": (
        SHARED_EXACT, ("state:readiness",), "#495",
        "one named attack's typed deficit and evolution hops feed its own future candidate"),
    "common.strategy.combat_math.clocks:ClockMixin.turns_to_ko": (
        LOCAL_ONLY, (), "#494",
        "local objective/snipe KO-race clock; no registered family consumes this target-side scalar"),
    "common.strategy.combat_math.energy:EnergyMixin.match_attack_slots": (
        SHARED_EXACT, ("state:readiness",), "#495",
        "authoritative typed assignment used by build, future feasibility, and clocks"),
    "common.strategy.combat_math.energy:EnergyMixin.attack_cost_slots": (
        LEAF_ONLY, ("state:readiness", "terminal:attack_ev"), "#495",
        "tri-state typed cost fact consumed by canonical combat owners"),
    "common.strategy.combat_math.energy:EnergyMixin.reachable_attach_p": (
        LOSSY_REEXPRESSION, ("state:readiness",), "#495",
        "local evolve delta and absolute readiness compose this probability through different horizons"),
    "common.strategy.combat_math.reach:ReachMixin.attack_realising_p": (
        LOSSY_REEXPRESSION, ("state:readiness",), "#495",
        "planner gamble and absolute readiness share Budget.realising_p but apply different fail behavior"),
    "common.strategy.combat_math.reach:ReachMixin.best_affordable_damage": (
        LOCAL_ONLY, (), "#494",
        "local lethal damage maximum; no registered absolute family consumes this scalar"),
    "common.strategy.combat_math.reach:ReachMixin.readiness_p": (
        SHARED_EXACT, ("state:readiness",), "#495",
        "the state readiness leaf reaches this exact probability oracle through MySide.readiness_p"),
    "common.strategy.combat_math.reach:ReachMixin.best_reachable_damage": (
        LOCAL_ONLY, (), "#495",
        "printed reachable-damage maximum is consumed by local attach/board equations only"),
    "common.strategy.combat_math.reach:ReachMixin.best_affordable_ko_value": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local affordable-KO maximum includes KO_SCORE, efficiency, and rider heuristics while "
        "terminal attack_ev composes prize-denominated KO/chip/rider/economy/lock legs"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_tactical": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local last-prize Gust KO score and terminal attack_ev independently compose the win"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_energy_denial": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local sunk-Energy KO tiebreak and terminal attack economy use different scales"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_forward_denial": (
        LOSSY_REEXPRESSION, ("state:threat", "terminal:attack_ev"), "#494",
        "local forward-line denial tiebreak recomposes threat and terminal attack value"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_matchup_priority": (
        LOSSY_REEXPRESSION, ("state:threat",), "#494",
        "local MatchupPlan priority tiebreak is a separate projection of target threat"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_snipe_synergy": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local extra KO-prize synergy and terminal rider value are separately composed"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_target_tactical": (
        LOSSY_REEXPRESSION, ("state:prize_race", "state:threat", "terminal:attack_ev"), "#494",
        "local Gust target KO/prize/denial sum recomposes prize, threat, and terminal values"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_stall_target_tactical": (
        LOSSY_REEXPRESSION, ("state:survival", "state:threat", "terminal:attack_ev"), "#494",
        "local stall-Gust retreat/EX score differs from survival, threat, and terminal horizons"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_target_denial": (
        LOSSY_REEXPRESSION, ("state:survival", "terminal:attack_ev"), "#494",
        "local prize denial from removing a live threat differs from survival and terminal values"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._snipe_after_gust_prizes": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local same-attack post-Gust rider prizes and terminal rider value use different target sets"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._active_ko_prizes": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local affordable Active KO prize baseline and terminal attack EV use different units"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._active_condition_ko_prizes": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local Checkup-condition KO prize baseline is outside terminal attack EV's attack-only leg"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_best_ko_prizes": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local best Gust target prize maximum and terminal attack EV use different menus"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_best_total_prizes": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local Gust main-plus-rider prize maximum and terminal attack EV use different menus"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._menu_attack_total_prizes": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local non-Gust main-plus-rider prize maximum and terminal attack EV use different menus"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_ko_energy_swing_calc": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local sunk-Energy margin for a Gust KO differs from terminal attack economy"),
    "common.strategy.objectives:ObjectivesMixin._race_attack_tactical": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local multi-turn wall/chip attack score and terminal one-ply attack EV use different horizons"),
    "common.strategy.objectives:ObjectivesMixin._their_turns_to_ko": (
        LOSSY_REEXPRESSION, ("state:survival", "terminal:attack_ev"), "#494",
        "local opponent KO-clock read and survival/terminal values use different horizons"),
    "common.strategy.objectives:_best_rest_chip": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local multi-turn incidental-chip optimiser and terminal one-ply rider value differ"),
    "common.strategy.objectives:plan_confidence": (
        LOSSY_REEXPRESSION,
        ("state:prize_race", "state:survival"), "#494",
        "local race/survival feasibility score differs from the two registered family compositions"),
    "common.strategy.objectives:prize_paths": (
        LOSSY_REEXPRESSION, ("state:prize_race", "terminal:attack_ev"), "#494",
        "local multi-body cheapest-prize path and absolute/terminal prize values use different horizons"),
    "common.snipe_relevance:rider_reach": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local repeated bench-rider reach and terminal one-ply rider value use different horizons"),
    "common.snipe_relevance:brief_tiebreak": (
        LOSSY_REEXPRESSION, ("state:threat",), "#494",
        "local strict-order Brief quantum is a separate projection of target threat"),
    "common.strategy.denial:coin_odds": (
        LOCAL_ONLY, (), "#494",
        "printed denial coin probability is consumed only by local denial equations"),
    "common.strategy.refresh:hand_swing": (
        LOSSY_REEXPRESSION, ("state:hand", "state:threat"), "#494",
        "local refresh hand-count swing differs from hand/threat value composition"),
    "common.strategy.refresh:net_change": (
        LOSSY_REEXPRESSION, ("state:hand", "state:threat"), "#494",
        "local expected my/opponent hand-net equation differs from hand/threat composition"),
    "common.strategy.refresh:own_draw_count": (
        LOSSY_REEXPRESSION, ("state:hand",), "#494",
        "local refresh draw-count equation is one input to the absolute hand ledger"),
    "common.strategy.refresh:fresh_cards": (
        LOSSY_REEXPRESSION, ("state:threat",), "#494",
        "local opponent fresh-card count is separately scaled by the threat equation"),
    "common.card_worth:keep_cost": (
        LOSSY_REEXPRESSION, ("state:hand",), "#494",
        "local reaccess/deadline keep cost is one projection of the absolute hand assignment ledger"),
    "common.card_worth:role_value": (
        LOSSY_REEXPRESSION, ("state:development", "state:hand", "state:readiness"), "#494",
        "the exact role-Worth scalar feeds only development/readiness body relevance and hand Needs"),
    "common.deny_relevance:strip_relevance": (
        LOSSY_REEXPRESSION, ("state:readiness", "state:threat"), "#494",
        "local typed strip relevance recomposes attack readiness and forward threat in a bounded band"),
    "common.deny_relevance:normalize": (
        LOSSY_REEXPRESSION, ("state:readiness", "state:threat"), "#494",
        "local setback-damage normalization is a component of typed readiness/threat relevance"),
    "common.snipe_relevance:target_relevance": (
        LOSSY_REEXPRESSION,
        ("state:prize_race", "state:survival", "state:threat", "terminal:attack_ev"), "#494",
        "local conjunctive threat/prize-route relevance differs from absolute and terminal composition"),
    "common.snipe_relevance:ko_delta": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local KO-clock improvement and terminal one-ply attack EV use different horizons"),
    "common.snipe_relevance:prize_share": (
        LOSSY_REEXPRESSION, ("state:prize_race", "terminal:attack_ev"), "#494",
        "local saturated prize-route share differs from prize-race and terminal composition"),
    "common.strategy.planning.leaf:LeafValueMixin._leaf_value": (
        LOSSY_REEXPRESSION,
        ("state:development", "state:prize_race", "state:readiness", "state:survival",
         "state:threat", "terminal:attack_ev"), "#494",
        "planner leaf recomposes registered board families with KO_SCORE and independent caps/weights"),
    "common.strategy.planning.leaf:LeafValueMixin._keep_cost": (
        LOSSY_REEXPRESSION, ("state:hand",), "#494",
        "planner keep-cost wrapper applies the classified hand keep oracle at a local deadline"),
    "common.strategy.planning.leaf:LeafValueMixin._hand_keep": (
        LOSSY_REEXPRESSION, ("state:hand",), "#494",
        "planner per-copy keep-cost sum is separately composed from the absolute hand ledger"),
    "common.strategy.planning.leaf:LeafValueMixin._line_account": (
        LOCAL_ONLY, (), "#494",
        "offline search path's signed fired/spend account has no registered absolute-family owner"),
    "common.strategy.objectives:race_values": (
        LOSSY_REEXPRESSION, ("terminal:attack_ev",), "#494",
        "local multi-turn KO-race map and terminal one-ply attack EV use different horizons"),
    "common.strategy.planning.leaf:LeafValueMixin._role_value": (
        LOSSY_REEXPRESSION, ("state:development", "state:hand", "state:readiness"), "#494",
        "planner role/tag Worth feeds Needs plus development/readiness body relevance through "
        "separately composed leaves"),
})

EQUATION_CONSUMER_OVERRIDES: Mapping[
    str, tuple[tuple[str, ...], str, str]
] = MappingProxyType({
    "common.apply_option:Expectation.ordering": (
        _ALL_STATE_OWNERS, LOSSY_REEXPRESSION,
        "resolution dispatcher carrying state_value into Expectation.best/expected"),
    "common.multi_pick:leaf_pick_indices": (
        _ALL_STATE_OWNERS, LEAF_ONLY,
        "iterative marginal consumer of the complete state_value registry; returns chosen indices"),
    "common.deciders.attach:AttachMixin._attach_value_tactical": (
        ("state:readiness",), LOSSY_REEXPRESSION,
        "tactical projection of the classified Attach decision; no independent value claim"),
    "common.deciders.deck_view:DeckViewMixin._deck_basic_energy_fuel": (
        ("state:readiness",), LOSSY_REEXPRESSION,
        "expected deck-fuel input consumed by local acceleration and absolute readiness equations"),
    "common.deciders.deploy:DeployMixin._needs_phase_scale": (
        ("state:survival", "state:threat"), LOSSY_REEXPRESSION,
        "board adapter to the classified phase_scale equation; no independent value claim"),
    "common.deciders.board_build:BoardMixin._incoming_active_damage": (
        ("state:survival",), LEAF_ONLY,
        "direct incoming-damage delegate consumed by board doom and the registered survival path"),
    "common.deciders.evolve:EvolveMixin._evolve_target_tactical": (
        ("state:development", "state:readiness", "state:survival"), LOSSY_REEXPRESSION,
        "direct tactical projection of evolve_value.total; no independent value claim"),
    "common.deciders.hand:HandMixin._grab_refresh_value": (
        ("state:hand", "state:threat"), LOSSY_REEXPRESSION,
        "GRAB projection of the classified refresh swing; no independent value claim"),
    "common.deciders.hand:HandMixin._refresh_swing_tactical": (
        ("state:hand", "state:threat"), LOSSY_REEXPRESSION,
        "PLAY projection of the classified refresh swing; no independent value claim"),
    "common.deciders.hand:HandMixin._refresh_shed_keepcost": (
        ("state:hand",), LOSSY_REEXPRESSION,
        "refresh shed component consumes the classified set_keep assignment oracle"),
    "common.deciders.hand:HandMixin._hand_size_relief_tactical": (
        ("state:survival",), LOSSY_REEXPRESSION,
        "local hand-size relief is a delta of the registered survival clock"),
    "common.deciders.promote:PromoteRetreatMixin._attached_retreat_delta": (
        (), LOCAL_ONLY,
        "adapter to ADR-0135 attached mobility units; no independent value claim"),
    "common.deciders.snipe:SnipeMixin._target_threat_rank": (
        ("state:threat",), LOSSY_REEXPRESSION,
        "selection-filtering adapter to the classified body threat rank"),
    "common.deciders.tactical:TacticalMixin._bench_snipe_bonus": (
        ("terminal:attack_ev",), LOSSY_REEXPRESSION,
        "delegate to CombatMath bench_snipe_bonus; wrapper defines no independent oracle"),
    "common.deciders.tactical:TacticalMixin._bench_spread_bonus": (
        ("terminal:attack_ev",), LOSSY_REEXPRESSION,
        "delegate to CombatMath bench_spread_bonus; wrapper defines no independent oracle"),
    "common.deciders.tactical:TacticalMixin._snipe_ko_prizes": (
        ("terminal:attack_ev",), LEAF_ONLY,
        "delegate to the exact CombatMath snipe-prize oracle; wrapper defines no value"),
    "common.deciders.tactical:TacticalMixin._spread_ko_prizes": (
        ("terminal:attack_ev",), LEAF_ONLY,
        "delegate to the exact CombatMath spread-prize oracle; wrapper defines no value"),
    "common.strategy.combat_math.clocks:ClockMixin.survival_clock": (
        ("state:survival",),
        LEAF_ONLY,
        "shared combat clock consumed by the registered survival path; not an independent local owner"),
    "common.strategy.combat_math.energy:EnergyMixin._attack_slots": (
        ("state:readiness", "terminal:attack_ev"),
        LEAF_ONLY,
        "typed-cost adapter consumed by readiness/terminal combat; computes slots, not economic value"),
    "common.strategy.combat_math.energy:EnergyMixin.matched_slots": (
        ("state:readiness",), LEAF_ONLY,
        "compatibility adapter to match_attack_slots; defines no independent value"),
    "common.deciders.lethal:LethalMixin._best_affordable_ko_value": (
        (), "", "pure forwarding adapter to CombatMath.best_affordable_ko_value; no new value claim"),
    "common.deciders.order:OrderMixin._score_order": (
        (), "", "orders already-scored traces; consumes scores but defines no economic oracle"),
    "common.deciders.tactical:TacticalMixin._prize_value": (
        (), "", "pure forwarding adapter to CombatMath/CardStat.prize_value; no new value claim"),
    "common.deciders.attach:AttachMixin._attach_progress": (
        ("state:readiness",), LOSSY_REEXPRESSION,
        "convex Energy-value component consumed by the separately composed Attach/readiness equations"),
    "common.deciders.heal:HealMixin._heal_target_tactical": (
        ("state:readiness", "state:survival", "terminal:attack_ev"), LOSSY_REEXPRESSION,
        "combines the classified heal-survival and bounce-cost equations; wrapper consumer"),
    "common.deciders.promote:PromoteRetreatMixin._promote_ko_tactical": (
        ("terminal:attack_ev",), LOSSY_REEXPRESSION,
        "forwarding consumer of best_affordable_ko_value; no independent KO value claim"),
    "common.state_model:MySide.forward_payoff": (
        ("state:development",), LEAF_ONLY,
        "memoizing adapter to MySide._forward_payoff; the development leaf owns the consumption"),
    "common.state_model:MySide.readiness_p": (
        ("state:readiness",), LEAF_ONLY,
        "typed StateModel adapter to the shared CombatMath readiness probability oracle"),
    "common.state_model:MySide.role_worth": (
        ("state:development", "state:hand", "state:readiness"), LEAF_ONLY,
        "memoizing adapter to MySide._role_worth_of; not an independent value equation"),
    "common.state_model:MySide.best_reachable_damage": (
        (), LOCAL_ONLY,
        "memoizing adapter to CombatMath.best_reachable_damage; no independent value claim"),
    "common.needs:Resolution.set_keep": (
        ("state:hand",), LOSSY_REEXPRESSION,
        "Resolution adapter to set_keep_v2; no independent assignment value claim"),
    "common.strategy.combat_math.budget:_pay_best_p": (
        ("state:readiness",), LEAF_ONLY,
        "typed assignment-probability implementation consumed through Budget.realising_p"),
    "common.strategy.combat_math.budget:_pay_best_p.assign": (
        ("state:readiness",), LEAF_ONLY,
        "recursive assignment component of _pay_best_p; no independent economic claim"),
    "common.strategy.combat_math.clocks:ClockMixin.doomed_incoming": (
        ("state:survival",), LEAF_ONLY,
        "direct one-turn incoming delegate consumed by the registered survival clock"),
    "common.strategy.combat_math.clocks:ClockMixin.reachable_incoming": (
        ("state:survival",), LEAF_ONLY,
        "direct next-turn incoming delegate consumed by the registered survival path"),
    "common.strategy.combat_math.clocks:ClockMixin.turns_to_ko_me": (
        ("state:survival",), LEAF_ONLY,
        "direct SurvivalClock.turns projection consumed by the registered survival path"),
    "common.strategy.combat_math.cards:CardFactsMixin.predicted_damage": (
        ("state:readiness", "state:survival", "state:threat", "terminal:attack_ev"),
        LOSSY_REEXPRESSION,
        "shared damage implementation consumed with different contexts/horizons across value owners"),
    "common.deciders.views:ViewsMixin.predicted_damage": (
        ("state:readiness", "state:survival", "state:threat", "terminal:attack_ev"),
        LOSSY_REEXPRESSION,
        "Pilot adapter to CombatMath.predicted_damage; no independent damage equation"),
    "common.deciders.views:ViewsMixin._predicted_max_damage": (
        ("state:survival", "state:threat", "terminal:attack_ev"), LOSSY_REEXPRESSION,
        "Pilot adapter to CombatMath.predicted_max_damage; no independent damage equation"),
    "common.strategy.combat_math.cards:CardFactsMixin.prize_value": (
        ("state:survival", "terminal:attack_ev"), LEAF_ONLY,
        "CardStat prize accessor consumed by body/terminal paths; no independent scalar composition"),
    "common.strategy.combat_math.reach:ReachMixin.best_reachable_damage_vs": (
        ("state:threat",), LEAF_ONLY,
        "the threat family consumes this exact damage-oracle output as its active-target gate"),
    "common.strategy.combat_math.reach:ReachMixin.best_reachable_bench_damage": (
        ("state:threat",), LEAF_ONLY,
        "the threat family consumes this exact rider output as its benched-target gate"),
})

EQUATION_EXCLUSIONS: Mapping[str, str] = MappingProxyType({
    "common.apply_option:Expectation.total_probability": (
        "enumerated branch-mass/truncation diagnostic; it is a probability fact, not a value"),
    "common.board_choice:_rank_discard": (
        "declared Role-Worth ordering key used only to cap transition classes; it enters no score"),
    "common.board_choice:gust_rank_key.key": (
        "nested menu sort key over already-valued rows; it orders exact ties and enters no score"),
    "common.board_choice:role_span": (
        "dimensionless role-priority normalizer used only by a menu sort key"),
    "common.board_expectation:_class_weight": (
        "hypergeometric transition-class availability weight; the expectation owner prices outcomes"),
    "common.board_delta:stadium_hp_delta": (
        "transition HP modifier returned to board_delta; survival/value owners price the resulting state"),
    "common.opponent_resources:OpponentResourceModel.hand_size_delta": (
        "observed turn-to-turn hand-count delta; downstream equations decide whether it has value"),
    "common.opponent_resources:OpponentResourceModel.discard_delta": (
        "observed turn-to-turn discard-count delta; downstream equations decide whether it has value"),
    "common.scouting.forward_index:_ForwardIndex.max_forward_damage": (
        "maximum printed provider damage fact; downstream combat/value equations own its pricing"),
    "common.deciders.attach:AttachMixin._line_payoff_stat": (
        "CardStat selection adapter; returns provider metadata, not economic value"),
    "common.deciders.attach:AttachMixin._payoff_attack_id": (
        "attack identifier selector; returns structural metadata, not an economic scalar"),
    "common.deciders.deploy:DeployMixin._recover_units": (
        "usable Energy-unit count; the classified acceleration-unlock equation supplies its price"),
    "common.deciders.lethal:LethalMixin._attach_lethal_tactical.best_affordable": (
        "nested damage optimiser inside the classified attach-lethal equation; no separate price"),
    "common.deciders.lethal:LethalMixin._best_affordable_damage": (
        "pure forwarding adapter to CombatMath.best_affordable_damage; no new value claim"),
    "common.deciders.lines:LineMixin._payoff_immediate_preevo_available": (
        "boolean availability predicate; payoff in the symbol name is not a value result"),
    "common.deciders.lines:LineMixin._line_readiness_deadline": (
        "integer deadline fact passed into readiness equations; it is not itself a value"),
    "common.deciders.plan_choice:_posture_gamma": (
        "bounded scouting-confidence coefficient; downstream equations own every priced use"),
    "common.deciders.snipe:SnipeMixin._snipe_brief_peers": (
        "list of peer relevance/priority inputs; the classified Brief tiebreak owns the scalar"),
    "common.deciders.snipe:SnipeMixin._threat_damage_pair": (
        "two mechanical damage projections; downstream threat-rank equations own their pricing"),
    "common.composer:_same_terminal_payoff": (
        "structural equality predicate over already-valued terminal candidates"),
    "common.scouting.provider:CardStat.prize_value": (
        "derived card-fact accessor; provider ownership is censused in the provider ledger"),
    "common.scouting.card_text:_parse_tool_hp_bonus": (
        "raw card-text parser returning a provider stat payload; it does not price the Tool"),
    "common.scouting.card_text:_parse_tool_attack_cost_reduction": (
        "raw card-text parser returning a provider stat payload; it does not price the Tool"),
    "common.state_model:BodyView.damage_counters": (
        "raw observed damage-counter count; registered/local equations price its downstream use"),
    "common.state_model:_SideBase.prizes_taken": (
        "raw prize-count state fact; registered/local equations price its downstream use"),
    "common.state_model:MySide.prizes_hidden": (
        "raw hidden-prize count used by odds calculations; it is not an economic value"),
    "common.deck_tracker:OwnCardModel._prizes_after_logged_takes": (
        "Counter bookkeeping snapshot after logged prize takes; it is not a scalar value equation"),
    "common.board_choice:choice_key": (
        "registry option-kind identifier; an integer key is structural metadata, not economic value"),
    "common.state_model:TheirSide.forward_payoff": (
        "unused memoizing side adapter; no production caller under src/common"),
})

# Factor 1 is terminal/win/prize impact, broader than a terminal-registry edge.  These source-pinned
# equations directly read/compute KO or prize progress; arbitrary name matches never set the factor.
TERMINAL_WIN_PRIZE_EQUATIONS: Mapping[str, str] = MappingProxyType({
    "common.apply_option:Expectation.best": (
        "maximises production state_value outcomes including prize-race value"),
    "common.apply_option:Expectation.expected": (
        "probability-weights production state_value outcomes including prize-race value"),
    "common.apply_option:Expectation.ordering": (
        "dispatches the production state_value outcome aggregation"),
    "common.board_choice:rank_retreat": (
        "prefilter includes PromoteBody fatal/prize exposure"),
    "common.deploy_value:deploy_value": (
        "includes the deployed body's bench-path prize exposure"),
    "common.deciders.deploy:DeployMixin._deploy_exposure_prizes": (
        "returns the deployed body's exposed prize liability"),
    "common.deciders.lethal:LethalMixin._grab_enabler_lethal_tactical": (
        "returns KO_SCORE plus prize value"),
    "common.deciders.lethal:LethalMixin._grab_retreat_tool_lethal_tactical": (
        "returns KO_SCORE plus prize value"),
    "common.deciders.lethal:LethalMixin._grab_lethal_tactical": (
        "returns KO_SCORE plus prize value"),
    "common.deciders.lethal:LethalMixin._attach_retreat_tool_lethal_tactical": (
        "prices an attach/retreat-Tool KO"),
    "common.deciders.lethal:LethalMixin._attach_lethal_tactical": (
        "prices an attach-enabled KO"),
    "common.deciders.lethal:LethalMixin._retreat_to_lethal_tactical": (
        "prices a retreat-enabled KO"),
    "common.deciders.lethal:LethalMixin._boost_lethal_tactical": (
        "prices a damage-boost-enabled KO"),
    "common.deciders.lines:LineMixin._bench_wincon_prize_value": (
        "selects the bench win-condition prize value"),
    "common.deciders.lines:LineMixin._wincon_prize_value": (
        "selects the active win-condition prize value"),
    "common.deciders.snipe:SnipeMixin._snipe_ko_dominator": (
        "returns KO_SCORE for a bench-snipe KO"),
    "common.deciders.snipe:SnipeMixin._snipe_tera_veto": (
        "returns negative KO_SCORE for an impossible bench KO"),
    "common.deciders.tactical:TacticalMixin._tactical": (
        "closed-form attack score contains KO/prize terms"),
    "common.deciders.tactical:TacticalMixin._copied_attack_tactical": (
        "copied-attack score contains KO/prize and denied-prize terms"),
    "common.deciders.tactical:TacticalMixin._copy_top_tactical": (
        "maximises copied attacks carrying KO/prize terms"),
    "common.deciders.tactical:TacticalMixin._self_return_escape_credit": (
        "prices prizes denied by a self-returning attack"),
    "common.deciders.tactical:TacticalMixin._top_deck_tactical": (
        "uses a KO_SCORE floor and copied KO/prize score"),
    "common.needs:line_prize_advance": (
        "computes line-level prize advance"),
    "common.promote_retreat_value:PromoteBody.fatal": (
        "returns KO_SCORE at a fatal prize boundary"),
    "common.promote_retreat_value:promote_value": (
        "includes the fatal KO_SCORE residual"),
    "common.snipe_relevance:target_relevance": (
        "includes prize-route share in the target score"),
    "common.snipe_relevance:ko_delta": (
        "computes improvement in the local KO clock"),
    "common.snipe_relevance:prize_share": (
        "computes saturated prize-route progress"),
    "common.strategy.combat_math.clocks:ClockMixin.turns_to_ko": (
        "computes local KO-race progress"),
    "common.strategy.combat_math.harvest:HarvestMixin.snipe_ko_prizes": (
        "returns exact prizes taken by a snipe KO"),
    "common.strategy.combat_math.harvest:HarvestMixin.spread_ko_prizes": (
        "returns exact prizes taken by spread KOs"),
    "common.strategy.combat_math.reach:ReachMixin.best_affordable_ko_value": (
        "maximises KO_SCORE plus prize/rider value"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_tactical": (
        "returns KO_SCORE plus prizes for a game-winning Gust"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_snipe_synergy": (
        "returns extra prizes from a same-attack bench KO"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._snipe_after_gust_prizes": (
        "returns exact same-attack rider prizes after Gust"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._active_ko_prizes": (
        "returns exact prizes from the current Active KO"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._active_condition_ko_prizes": (
        "returns exact prizes from a Checkup condition KO"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_best_ko_prizes": (
        "maximises prizes over Gust KO targets"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_best_total_prizes": (
        "maximises main plus rider prizes over Gust targets"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._menu_attack_total_prizes": (
        "maximises main plus rider prizes without Gust"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_ko_energy_swing_calc": (
        "compares sunk Energy on prize-taking KO lines"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_target_tactical": (
        "returns KO_SCORE plus line-prize and denial terms"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_stall_target_tactical": (
        "ranks a prize-bearing EX stall target"),
    "common.strategy.doctrines.doctrine_gust:GustMixin._gust_target_denial": (
        "returns prizes denied by removing a live threat"),
    "common.strategy.objectives:ObjectivesMixin._race_attack_tactical": (
        "prices multi-turn KO-race progress"),
    "common.strategy.objectives:ObjectivesMixin._their_turns_to_ko": (
        "computes the opponent's KO clock"),
    "common.strategy.objectives:race_values": (
        "computes multi-turn KO-race values"),
    "common.strategy.objectives:prize_paths": (
        "computes the cheapest path satisfying the remaining-prize target"),
    "common.strategy.planning.ladder:GoalLadderMixin._deckout_grind_bonus": (
        "nudges planning toward the opponent deck-out win route"),
    "common.strategy.planning.gamble:GambleMixin._composed_line_p": (
        "computes the probability of a composed KO line"),
    "common.strategy.planning.gamble:GambleMixin._gamble_det_baseline": (
        "baseline may carry an already-scored KO/prize tactical"),
    "common.strategy.planning.leaf:LeafValueMixin._leaf_value": (
        "directly multiplies KO_SCORE by prizes taken"),
    "common.state_value:prize_race": (
        "directly computes prize lead and prize proximity"),
    "common.state_value:state_value": (
        "sums the registered prize_race family with the other board families"),
    "common.state_value:_terms": (
        "yields the registered prize_race term into state_value composition"),
})

# These fingerprints are authored review gates, not the census itself.  The generated report lists
# every member.  A changed digest stops generation until the new source row is dispositioned.
EQUATION_BASELINE_SHA256 = "3ef09639dc3905862ee04fa039f862a32c0392983ac90f8df1f72a9cab49d4bc"
VOCABULARY_BASELINE_SHA256 = "22316ccf76a2319311586785d2dc3ede3b77e6e566c0a15530a2a660d68f5d9b"
STAT_BASELINE_SHA256 = "0ab57ba9897807b8cfbfd97052126c35e6819b24a447ccc3a4b34acfd1eea637"


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return value or "structural"


def _jsonable(value):
    if dataclasses.is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (set, frozenset)):
        return [_jsonable(item) for item in sorted(value, key=repr)]
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _digest(values: Iterable[str]) -> str:
    payload = "\n".join(sorted(values)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def origin_main_sha(root: Path = _ROOT) -> str:
    """The reviewed pre-implementation base, not a moving remote-tracking ref.

    A generated artifact cannot be fresh when its provenance changes merely because ``origin/main``
    advanced after checkout (and shallow PR jobs need not even have that ref).  Updating source
    populations requires deliberately repinning this constant alongside their digest gates.
    """
    del root
    return AUDIT_BASE_SHA


def source_sites(card_ids: Iterable[int] | None = None) -> tuple[SourceSite, ...]:
    cards = apply_census.load_cards()
    effects = apply_census.load_effects()
    covers = apply_census.load_covers()
    ids = set(cards) | set(effects) if card_ids is None else {int(card_id) for card_id in card_ids}
    missing = sorted(ids - set(cards))
    if missing:
        raise CoverageError(f"effect/deck card ids absent from cards.json: {missing}")
    problems = apply_census.validate(ids, cards, effects, covers)
    if problems:
        raise CoverageError("; ".join(problems))
    legacy, _aside = apply_census.census(ids, cards, effects, covers)
    ordinal = collections.Counter()
    out = []
    for site in legacy:
        n = ordinal[site.card_id]
        ordinal[site.card_id] += 1
        out.append(SourceSite(
            card_id=site.card_id,
            ordinal=n,
            name=site.name,
            category=site.category or "",
            kind=site.kind,
            kind_name=KIND_NAMES.get(site.kind, f"UNDECLARED_{site.kind}"),
            label=site.label,
            fate=site.fate,
            report_class=site.report_class,
            cause=site.cause,
            note=site.note,
            family=site.family,
            expressible=bool(site.expressible),
            clauses_json=json.dumps(site.clauses, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            has_effect=site.has_effect,
        ))
    return tuple(out)


def legacy_positive_control() -> PositiveControl:
    cards = apply_census.load_cards()
    effects = apply_census.load_effects()
    covers = apply_census.load_covers()
    decks = apply_census.load_our_decks()
    builds, _priors = apply_census.load_opponent_builds()
    pool = set().union(*(set(counter) for counter in (*decks.values(), *builds.values())))
    legacy, _aside = apply_census.census(pool, cards, effects, covers)
    old_rows = [site.as_row() for site in legacy]
    new_rows = [site.as_legacy_row() for site in source_sites(pool)]
    old_json = json.dumps(old_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    new_json = json.dumps(new_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    fates = collections.Counter(row["fate"] for row in new_rows)
    return PositiveControl(
        pool_cards=len(pool),
        sites=len(new_rows),
        matched=old_rows == new_rows,
        legacy_digest=hashlib.sha256(old_json.encode("utf-8")).hexdigest(),
        census_digest=hashlib.sha256(new_json.encode("utf-8")).hexdigest(),
        fate_counts=tuple(sorted(fates.items())),
    )


def _site_writes(site: SourceSite) -> tuple[str, ...]:
    clauses = json.loads(site.clauses_json)
    writes: set[str] = set()
    if site.kind == _ATTACH:
        if site.category == "tool":
            writes |= {"attached_tools", "my_hand_ids"}
            if any(read.startswith("hpBonus") for read in apply_census.tool_static_reads(
                    apply_census.load_cards()[site.card_id])):
                writes.add("damage_counters")
        else:
            writes |= {"attached_energy", "my_hand_ids", "allowance_energy_attached"}
    elif site.kind == _EVOLVE:
        writes |= {"bodies_in_play", "my_hand_ids", "special_conditions", "new_in_play",
                   "damage_counters"}
    elif site.kind == _PLAY:
        writes.add("my_hand_ids")
        if site.category == "pokemon":
            writes |= {"bodies_in_play", "bench_occupancy", "new_in_play"}
        elif site.category == "stadium":
            writes |= {"my_discard_contents", "their_discard_contents", "stadium",
                       "allowance_stadium_played"}
        else:
            writes.add("my_discard_contents")
            if site.category == "supporter":
                writes.add("allowance_supporter_played")
    elif site.kind == _ABILITY:
        writes.add("allowance_ability_used")
    for clause in clauses:
        for value in snapshots.clause_values(clause):
            writes.update(snapshots.CLAUSE_WRITES.get(value, ()))
    return _ordered(writes)


def _classification(*, fate: str, absolute: tuple[str, ...], local: tuple[str, ...],
                    relation: str = "", deliberate_ruling: str = "") -> str:
    if fate in (seam.REFUSED, seam.ENGINE_RESOLVED, seam.UNDECLARED):
        return UNKNOWN_REFUSED
    if deliberate_ruling:
        return DELIBERATE_ZERO
    if not absolute and not local:
        return UNVALUED_MODELLED
    if local and not absolute:
        return LOCAL_ONLY
    if absolute and local:
        if relation == "exact":
            return SHARED_EXACT
        if relation == "conflict":
            return DUPLICATE_CONFLICT
        return LOSSY_REEXPRESSION
    return LEAF_ONLY


@dataclass
class _ExposureIndex:
    deck_names: dict[int, set[str]]
    deck_copies: collections.Counter
    build_names: dict[int, set[str]]
    meta_copies: dict[int, float]
    corpus_keys: dict[int, set[str]]

    def for_cards(self, card_ids: Iterable[int], *, sites: int = 0) -> Exposure:
        ids = {int(card_id) for card_id in card_ids}
        return Exposure(
            cards=len(ids),
            mechanic_sites=sites,
            decks=len(set().union(*(self.deck_names.get(card_id, set()) for card_id in ids))),
            deck_copies=sum(self.deck_copies.get(card_id, 0) for card_id in ids),
            meta_builds=len(set().union(*(self.build_names.get(card_id, set()) for card_id in ids))),
            meta_copies=round(sum(self.meta_copies.get(card_id, 0.0) for card_id in ids), 6),
            corpus_frames=len(set().union(*(self.corpus_keys.get(card_id, set()) for card_id in ids))),
        )


def _ids_in(value, known: set[int], out: set[int]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"id", "cardId", "card_id"} and isinstance(item, int) and item in known:
                out.add(item)
            _ids_in(item, known, out)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _ids_in(item, known, out)


def _load_corpus_corrections():
    """Load ranking corpus input; unavailable data is an audit failure, never zero exposure."""
    try:
        from train.blunder.store import DEFAULT_ROOT, load_corrections
        return load_corrections(DEFAULT_ROOT)
    except (ImportError, OSError, ValueError) as exc:
        raise CoverageError(f"could not load corpus exposure: {exc}") from exc


def _exposure_index(cards: Mapping[int, dict]) -> _ExposureIndex:
    decks = apply_census.load_our_decks()
    builds, priors = apply_census.load_opponent_builds()
    deck_names: dict[int, set[str]] = collections.defaultdict(set)
    build_names: dict[int, set[str]] = collections.defaultdict(set)
    for name, counter in decks.items():
        for card_id in counter:
            deck_names[card_id].add(name)
    for name, counter in builds.items():
        for card_id in counter:
            build_names[card_id].add(name)
    corpus: dict[int, set[str]] = collections.defaultdict(set)
    corrections = _load_corpus_corrections()
    known = set(cards)
    for n, correction in enumerate(corrections):
        found: set[int] = set()
        _ids_in(getattr(correction, "obs", None), known, found)
        key = str(getattr(correction, "id", "") or f"correction-{n}")
        for card_id in found:
            corpus[card_id].add(key)
    return _ExposureIndex(
        deck_names=dict(deck_names),
        deck_copies=apply_census.our_copies(decks),
        build_names=dict(build_names),
        meta_copies=apply_census.meta_copies(builds, priors),
        corpus_keys=dict(corpus),
    )


def _owners_for(writes: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    absolute = {owner for zone in writes for owner in ZONE_OWNERS[zone]}
    local = {owner for zone in writes for owner in ZONE_LOCAL_OWNERS[zone]}
    return _ordered(absolute), _ordered(local)


def _site_owner_writes(site: SourceSite, writes: tuple[str, ...]) -> tuple[str, ...]:
    """Mechanic consequence writes, excluding option-kind bookkeeping already audited elsewhere.

    Every card played from hand writes ``my_hand_ids`` (and Trainers also move to discard), but that
    does not make every Heal, Tool, or Energy site a Hand mechanic.  The exact transition row keeps
    those dimensions; only the semantic ownership join removes the generic transport writes.
    """
    clause_writes = set()
    for clause in json.loads(site.clauses_json):
        for value in snapshots.clause_values(clause):
            clause_writes.update(snapshots.CLAUSE_WRITES.get(value, ()))
    generic = {"my_hand_ids"}
    if site.kind == _PLAY and site.category not in {"pokemon", "stadium"}:
        generic.add("my_discard_contents")
    generic.update({
        "allowance_energy_attached", "allowance_supporter_played",
        "allowance_ability_used", "allowance_retreat_used", "allowance_stadium_played",
    })
    # Provenance matters: a card's ordinary trip out of hand is transport, while a bounce clause's
    # write back to that same dimension is the mechanic.  Remove only generic-only occurrences.
    return _ordered(set(writes) - (generic - clause_writes))


def _site_records(sites: tuple[SourceSite, ...], exposure: _ExposureIndex) -> list[AuditRecord]:
    records = []
    for site in sites:
        writes = _site_writes(site)
        ownership_writes = _site_owner_writes(site, writes)
        absolute, local = _owners_for(ownership_writes)
        relation = "exact" if ownership_writes and set(ownership_writes) <= EXACT_ZONES else ""
        classification = _classification(fate=site.fate, absolute=absolute, local=local,
                                         relation=relation)
        evidence = [
            f"apply-seam class={site.report_class}",
            f"effect family={site.family or 'structural'}",
        ]
        ignored = sorted(set(writes) - set(ownership_writes))
        if ignored:
            evidence.append(f"option-kind bookkeeping excluded from mechanic ownership={','.join(ignored)}")
        if site.cause:
            evidence.append(f"refusal cause={site.cause}")
        if site.note:
            evidence.append(f"coverage note={site.note}")
        records.append(AuditRecord(
            mechanic_key=f"card-site:{site.kind_name.lower()}:{_slug(site.family)}",
            source_kind="card-effect-site",
            source_symbol_or_site=f"card {site.card_id} {site.name} / {site.label} / site {site.ordinal}",
            transition_fate=site.fate,
            written_dimensions=writes,
            absolute_owners=absolute,
            local_owners=local,
            leaf_path=absolute,
            search_path=("composer:_one_ply", "composer:_admit", "composer:_expand",
                         "composer:_prune_nodes", "composer:selection_key"),
            classification=classification,
            evidence=_ordered(evidence),
            exposure=exposure.for_cards({site.card_id}, sites=1),
            live_owner="#492 backlog" if classification == UNKNOWN_REFUSED else (
                "#495" if "attached_energy" in writes else "#494"),
        ))
    return records


def _attack_and_passive_records(cards: Mapping[int, dict], exposure: _ExposureIndex) -> list[AuditRecord]:
    records = []
    for card_id, card in sorted(cards.items()):
        for ordinal, attack in enumerate(card.get("attacks") or []):
            records.append(AuditRecord(
                mechanic_key="terminal-attack:printed",
                source_kind="terminal-attack-site",
                source_symbol_or_site=(f"card {card_id} {card.get('name', '?')} / attack {ordinal} "
                                       f"{attack.get('name', '?')}"),
                transition_fate=seam.TERMINAL,
                absolute_owners=("terminal:attack_ev",),
                runtime_callers=("common.composer:terminal_ev",),
                leaf_path=("terminal:attack_ev",),
                search_path=("composer:terminal_ev", "composer:_selection_candidates"),
                classification=LEAF_ONLY,
                evidence=("printed attack payoff is canonically owned by attack_ev/attack_ev_legs",),
                exposure=exposure.for_cards({card_id}, sites=1),
                live_owner="terminal:attack_ev",
            ))
        if card.get("category") != "pokemon":
            continue
        for ordinal, ability in enumerate(card.get("abilities") or []):
            text = ability.get("text") or ""
            if apply_census._ability_mode(text) != "passive":
                continue
            records.append(AuditRecord(
                mechanic_key="passive-ability:static-or-unparsed",
                source_kind="passive-ability-site",
                source_symbol_or_site=(f"card {card_id} {card.get('name', '?')} / passive {ordinal} "
                                       f"{ability.get('name', '?')}"),
                transition_fate=seam.UNDECLARED,
                classification=UNKNOWN_REFUSED,
                evidence=("passive Ability has no apply-option transition site; provider recovery is audited separately",),
                exposure=exposure.for_cards({card_id}, sites=1),
                live_owner="#492 backlog",
            ))
    return records


def _option_records() -> list[AuditRecord]:
    records = []
    for kind, name in OPTION_KINDS:
        fate = seam.KIND_COVERAGE[kind]
        writes = _ordered(seam.footprint(kind).writes)
        absolute, local = _owners_for(writes)
        deliberate = ""
        if kind == _ATTACK:
            absolute = ("terminal:attack_ev",)
        elif kind == _END:
            # END is not a leaf owner.  The board is already in ``state_value``; the terminal
            # summand is the accepted exact zero.
            absolute, local = (), ()
            deliberate = ("ADR-0129: END buys nothing beyond the board already scored; "
                          "common.composer.terminal_ev returns exactly 0")
        classification = _classification(fate=fate, absolute=absolute, local=local,
                                         deliberate_ruling=deliberate)
        records.append(AuditRecord(
            mechanic_key=f"option-kind:{name.lower()}",
            source_kind="option-kind",
            source_symbol_or_site=f"common.apply_option.KIND_COVERAGE[{name}]",
            transition_fate=fate,
            written_dimensions=writes,
            absolute_owners=absolute,
            local_owners=local,
            leaf_path=absolute,
            search_path=("composer:_rank", "composer:_admit"),
            classification=classification,
            evidence=_ordered({
                f"footprint complete={seam.footprint(kind).complete}",
                "terminal kinds have no StateModel transition" if fate == seam.TERMINAL else "",
            }),
            deliberate_ruling=deliberate,
            live_owner=("ADR-0129" if kind == _END else
                        "#492 backlog" if classification == UNKNOWN_REFUSED else "#494"),
        ))
    return records


def _zone_records(zone_card_occurrences: Mapping[str, tuple[int, ...]],
                  exposure: _ExposureIndex) -> list[AuditRecord]:
    records = []
    for zone in snapshots.WRITABLE:
        absolute = _ordered(ZONE_OWNERS[zone.id])
        local = _ordered(ZONE_LOCAL_OWNERS[zone.id])
        search_path = _ordered(("composer:state_value leaf",) if absolute else ())
        search_path = _ordered((*search_path, *ZONE_SEARCH_CONSUMERS.get(zone.id, ())))
        fate = "hidden" if zone.status == snapshots.HIDDEN else "modelled-state"
        classification = UNKNOWN_REFUSED if zone.status == snapshots.HIDDEN else _classification(
            fate=fate, absolute=absolute, local=local,
            relation="exact" if zone.id in EXACT_ZONES else "",
        )
        records.append(AuditRecord(
            mechanic_key=f"state-dimension:{zone.id}",
            source_kind="writable-state",
            source_symbol_or_site=f"common.snapshot_coverage.WRITABLE[{zone.id}]",
            transition_fate=fate,
            written_dimensions=(zone.id,),
            absolute_owners=absolute,
            local_owners=local,
            leaf_path=absolute,
            search_path=search_path,
            classification=classification,
            evidence=_ordered({f"status={zone.status}", f"home={zone.home}",
                               f"priced_by={zone.priced_by}", f"owner={zone.owner}",
                               ("mixed Tool classes: damageBoost reaches readiness/threat/terminal; "
                                "ADR-0135 retreat mobility remains local-only"
                                if zone.id == "attached_tools" else ""),
                               ("ADR-0135: retreat mobility is intentionally local-only"
                                if zone.id == "allowance_retreat_used" else "")}),
            exposure=exposure.for_cards(zone_card_occurrences.get(zone.id, ()),
                                        sites=len(zone_card_occurrences.get(zone.id, ()))),
            live_owner=("ADR-0135" if zone.id == "allowance_retreat_used"
                        else "#495" if zone.id == "attached_energy"
                        else "#492 backlog" if classification == UNKNOWN_REFUSED else "#494"),
        ))
    return records


def _selector_occurrences(card_id: int, clause: Mapping) -> tuple[tuple[str, str], ...]:
    """The registry's selector semantics with source-occurrence multiplicity preserved."""
    found = []

    def walk(block: Mapping) -> None:
        for key, value in block.items():
            if isinstance(value, Mapping):
                walk(value)
                continue
            values = value if isinstance(value, (list, tuple)) else (value,)
            for item in values:
                found.extend(snapshots.clause_selectors({card_id: [{key: item}]}))

    walk(clause)
    canonical = set(snapshots.clause_selectors({card_id: [clause]}))
    if set(found) != canonical:
        raise CoverageError(f"selector occurrence walk drifted for card {card_id}")
    return tuple(found)


def _clause_population(effects: Mapping[int, list[dict]]) -> tuple[
        dict[str, tuple[int, ...]], dict[tuple[str, str], tuple[int, ...]]]:
    values: dict[str, list[int]] = collections.defaultdict(list)
    selectors: dict[tuple[str, str], list[int]] = collections.defaultdict(list)
    for card_id, clauses in effects.items():
        for clause in clauses:
            for value in snapshots.clause_values(clause):
                values[value].append(card_id)
            # Selector membership is registry-derived; this occurrence walk additionally preserves
            # repeated identical selectors within one clause (two conditional amounts, for example).
            for key, value in _selector_occurrences(card_id, clause):
                selectors[(key, value)].append(card_id)
    return ({key: tuple(items) for key, items in sorted(values.items())},
            {key: tuple(items) for key, items in sorted(selectors.items())})


def _clause_records(effects: Mapping[int, list[dict]], exposure: _ExposureIndex) -> list[AuditRecord]:
    used_values, used_selectors = _clause_population(effects)
    records = []
    for value in sorted(set(snapshots.CLAUSE_WRITES) | set(used_values)):
        writes = _ordered(snapshots.CLAUSE_WRITES.get(value, ()))
        if not writes:
            absolute, local, classification = EMPTY_CLAUSE_JOIN[value]
            absolute, local = _ordered(absolute), _ordered(local)
        else:
            absolute, local = _owners_for(writes)
            classification = _classification(fate="modelled-clause", absolute=absolute, local=local)
        records.append(AuditRecord(
            mechanic_key=f"effect-clause:{value}",
            source_kind="effect-clause-value",
            source_symbol_or_site=f"common.snapshot_coverage.CLAUSE_WRITES[{value!r}]",
            transition_fate="modelled-clause" if value in snapshots.CLAUSE_WRITES else seam.UNDECLARED,
            written_dimensions=writes,
            absolute_owners=absolute,
            local_owners=local,
            leaf_path=absolute,
            search_path=("composer:_one_ply", "composer:_expand"),
            classification=classification,
            evidence=_ordered({
                f"used by {len(set(used_values.get(value, ())))} cards",
                "empty write set dispatches to companion effect/stat semantics" if not writes else "",
            }),
            exposure=exposure.for_cards(used_values.get(value, ()),
                                        sites=len(used_values.get(value, ()))),
            live_owner=("#495" if "attached_energy" in writes else
                        "#494" if classification != UNKNOWN_REFUSED else "#492 backlog"),
        ))

    allowed_selectors = {
        (str(key), str(value))
        for key, allowed in snapshots.CLAUSE_SELECTORS.items()
        for value in allowed
    }
    for key, value in sorted(allowed_selectors | set(used_selectors)):
        records.append(AuditRecord(
            mechanic_key=f"effect-selector:{key}={value}",
            source_kind="effect-clause-selector",
            source_symbol_or_site=f"common.snapshot_coverage.CLAUSE_SELECTORS[{key!r}]={value!r}",
            transition_fate="parameter",
            classification=DELIBERATE_ZERO,
            evidence=(f"used by {len(set(used_selectors.get((key, value), ())))} cards",),
            deliberate_ruling=("Issue #374: selector values constrain a parent clause; they do not "
                                "write or price an independent consequence"),
            exposure=exposure.for_cards(used_selectors.get((key, value), ()),
                                        sites=len(used_selectors.get((key, value), ()))),
            live_owner="Issue #374",
        ))
    for key in sorted(snapshots.CLAUSE_PARAMETERS):
        records.append(AuditRecord(
            mechanic_key=f"effect-parameter:{key}",
            source_kind="effect-clause-parameter",
            source_symbol_or_site=f"common.snapshot_coverage.CLAUSE_PARAMETERS[{key!r}]",
            transition_fate="parameter",
            classification=DELIBERATE_ZERO,
            evidence=(f"parameter contract={snapshots.CLAUSE_PARAMETERS[key]}",),
            deliberate_ruling=("Issue #262's snapshot-completeness contract (and ADR-0130 for "
                                "`choice`): a parameter changes its parent clause's semantics and "
                                "has no independent state delta"),
            live_owner="Issue #262 / ADR-0130",
        ))
    return records


def _family_records() -> list[AuditRecord]:
    records = []
    for terminal, registry in ((False, state_value.REGISTRY), (True, state_value.TERMINAL_REGISTRY)):
        for family in registry:
            owner = f"terminal:{family.name}" if terminal else f"state:{family.name}"
            records.append(AuditRecord(
                mechanic_key=f"value-family:{'terminal' if terminal else 'state'}:{family.name}",
                source_kind="terminal-family" if terminal else "state-value-family",
                source_symbol_or_site=("common.state_value.TERMINAL_REGISTRY" if terminal else
                                       "common.state_value.REGISTRY") + f"[{family.name}]",
                transition_fate="value-owner",
                absolute_owners=(owner,),
                leaf_path=(owner,),
                search_path=(("composer:terminal_ev",) if terminal else ("composer:state_value leaf",)),
                classification=LEAF_ONLY,
                evidence=_ordered({
                    f"registry_identity={state_value.registry_identity()}",
                    f"unit={family.unit}",
                    f"horizon={family.horizon}",
                    f"consequences={','.join(item.key for item in family.consequences)}",
                    f"bounds={','.join(item.key for item in family.bounds)}",
                    f"reads={','.join(family.reads)}",
                    f"does_not_read={','.join(family.does_not_read)}",
                    f"blind_to={','.join(family.blind_to)}",
                    f"composition={family.composition}",
                }),
                live_owner="#494",
            ))
    return records


@dataclass(frozen=True)
class _Definition:
    key: str
    path: str
    line: int
    leaf: str
    return_annotation: str = ""
    economic_formula: bool = False


_ECONOMIC_FORMULA_TOKENS = (
    "afford", "bonus", "clock", "cost", "credit", "damage", "delta", "equity",
    "harvest", "incoming", "lethal", "marginal", "odds", "payoff", "prize",
    "probability", "readiness", "relevance", "score", "standing", "survival",
    "tactical", "threat", "turns_to", "value", "worth",
)
_NUMERIC_FORMULA_CALLS = frozenset({
    "abs", "ceil", "float", "floor", "halve", "int", "max", "mean", "min", "round", "sum",
})


def _formula_metadata(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, bool]:
    """Return annotation and a conservative AST-only economic-formula nomination.

    Nomination is deliberately broader than the authored semantic table, but narrower than a name
    grep: the function must contain a numeric operation/constructor *and* an economic identifier.
    Boolean gates such as ``can_ko_affordable`` stay consumers even though they read damage/cost.
    Nested definitions are analysed as their own rows, never charged to their enclosing function.
    """
    annotation = _annotation_text(node.returns)
    numeric = False
    has_return = False
    structural_return = False

    class FormulaVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, child):
            return None

        visit_AsyncFunctionDef = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

        def visit_BinOp(self, child):
            nonlocal numeric
            numeric = True
            self.generic_visit(child)

        def visit_AugAssign(self, child):
            nonlocal numeric
            numeric = True
            self.generic_visit(child)

        def visit_Call(self, child):
            nonlocal numeric
            chain = _attribute_chain(child.func)
            if chain and chain[-1].lower() in _NUMERIC_FORMULA_CALLS:
                numeric = True
            self.generic_visit(child)

        def visit_Return(self, child):
            nonlocal has_return, numeric, structural_return
            has_return = True
            if isinstance(child.value, ast.Constant) and isinstance(child.value.value, (int, float)) \
                    and not isinstance(child.value.value, bool):
                numeric = True
            if isinstance(child.value, (ast.Dict, ast.DictComp, ast.List, ast.ListComp, ast.Set,
                                        ast.SetComp, ast.Tuple)):
                structural_return = True
            if isinstance(child.value, ast.Call):
                chain = _attribute_chain(child.value.func)
                leaf = chain[-1] if chain else ""
                if leaf in {"dict", "frozenset", "list", "set", "tuple"} \
                        or (leaf and leaf[:1].isupper()):
                    structural_return = True
            self.generic_visit(child)

    visitor = FormulaVisitor()
    for statement in node.body:
        visitor.visit(statement)
    # Source nomination uses the declared symbol, not incidental identifiers in its body.  A Board
    # constructor that happens to read ``damage`` is still a Board constructor, not a damage oracle.
    semantic = any(token in node.name.lower() for token in _ECONOMIC_FORMULA_TOKENS)
    boolean_result = bool(re.search(r"(?:^|\W)bool(?:$|\W)", annotation))
    annotated_structure = bool(re.search(
        r"(?:^|\W)(?:dict|list|set|frozenset|tuple|Board|Context|Budget)(?:$|\W)", annotation))
    return annotation, bool(has_return and numeric and semantic and not boolean_result
                            and not structural_return and not annotated_structure)


def _module_name(path: Path, root: Path) -> str:
    return "common." + path.relative_to(root / "src" / "common").with_suffix("").as_posix().replace("/", ".")


def _attribute_chain(node: ast.AST) -> tuple[str, ...]:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return tuple(reversed(parts))
    return ()


def _annotation_text(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except (AttributeError, ValueError):
        return ""


def _relative_module(current: str, imported: str | None, level: int) -> str:
    if not level:
        return imported or ""
    prefix = current.split(".")[:-level]
    return ".".join((*prefix, *((imported or "").split(".") if imported else ())))


def _import_aliases(tree: ast.AST, module: str) -> tuple[dict[str, str], dict[str, str]]:
    modules: dict[str, str] = {}
    symbols: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules[alias.asname or alias.name.split(".", 1)[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            imported = _relative_module(module, node.module, node.level)
            for alias in node.names:
                if alias.name != "*":
                    symbols[alias.asname or alias.name] = f"{imported}:{alias.name}"
    return modules, symbols


def _provider_members_by_name() -> Mapping[str, tuple[str, ...]]:
    grouped: dict[str, set[str]] = collections.defaultdict(set)
    for cls in (CardStat, AttackStat):
        for field in dataclasses.fields(cls):
            grouped[field.name].add(cls.__name__)
        for name, member in vars(cls).items():
            if isinstance(member, property):
                grouped[name].add(cls.__name__)
    return MappingProxyType({name: _ordered(classes) for name, classes in grouped.items()})


def _named_provider_hint(name: str, candidates: set[str]) -> set[str]:
    """Conservative receiver-name fallback after flow inference.

    The field must already be a provider member.  This admits conventional ``stat``/``ast`` names
    while refusing unrelated receivers such as ``plan.cost`` and ``profile.damage``.
    """
    value = name.lower()
    attackish = (value in {"a", "ast", "astat", "attack", "attack_stat"}
                 or value.startswith("attack_") or value.endswith("_attack_stat"))
    cardish = (value in {"attacker", "card", "cstat", "defender", "estat", "gstat",
                         "ma_stat", "stat", "st", "t", "tstat"}
                  or value.endswith("_stat"))
    if attackish and "AttackStat" in candidates:
        return {"AttackStat"}
    if cardish and len(candidates) == 1:
        return set(candidates)
    if cardish and "CardStat" in candidates:
        return {"CardStat"}
    return set()


def _provider_expr_types(node: ast.AST, bindings: Mapping[str, set[str]]) -> set[str]:
    if isinstance(node, ast.Name):
        return set(bindings.get(node.id, ()))
    if isinstance(node, ast.IfExp):
        return _provider_expr_types(node.body, bindings) | _provider_expr_types(node.orelse, bindings)
    if isinstance(node, ast.Attribute) and node.attr == "stat":
        return {"CardStat"}
    if isinstance(node, ast.Call):
        chain = _attribute_chain(node.func)
        leaf = chain[-1].lower() if chain else ""
        receiver = ".".join(chain[:-1]).lower()
        if leaf in {"attack", "attack_stat", "_attack_stat"} or "attack_stat" in leaf:
            return {"AttackStat"}
        if leaf in {"card_stat", "stat_of"}:
            return {"CardStat"}
        if leaf == "get" and any(token in receiver for token in ("stats", "card_stat", "provider")):
            return {"CardStat"}
    if isinstance(node, ast.Subscript):
        chain = _attribute_chain(node.value)
        text = ".".join(chain).lower()
        if "attack" in text:
            return {"AttackStat"}
        if "stat" in text:
            return {"CardStat"}
    return set()


def _source_index(root: Path = _ROOT) -> tuple[tuple[_Definition, ...], Mapping[str, tuple[str, ...]],
                                                Mapping[str, tuple[str, ...]]]:
    """Definitions, qualified callees -> callers, and receiver-proved provider reads.

    Bare leaf-name joins are intentionally forbidden: ``plan.cost`` is not an ``AttackStat.cost``
    consumer merely because both attributes have the same spelling.  Unresolved dynamic dispatch is
    omitted rather than guessed; the candidate remains present with zero statically proved callers.
    """
    definitions: list[_Definition] = []
    class_method_targets: dict[str, set[str]] = collections.defaultdict(set)
    class_targets_by_name: dict[str, set[str]] = collections.defaultdict(set)
    class_attribute_annotations: dict[tuple[str, str], str] = {}
    parsed: list[tuple[Path, str, ast.AST, dict[str, str], dict[str, str]]] = []
    source = root / "src" / "common"
    for path in sorted(source.rglob("*.py")):
        module = _module_name(path, root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module_aliases, symbol_aliases = _import_aliases(tree, module)
        parsed.append((path, module, tree, module_aliases, symbol_aliases))
        stack: list[str] = []
        scope_kinds: list[str] = []

        class DefinitionVisitor(ast.NodeVisitor):
            def visit_ClassDef(self, node):
                class_targets_by_name[node.name].add(
                    f"{module}:{'.'.join((*stack, node.name))}")
                stack.append(node.name)
                scope_kinds.append("class")
                self.generic_visit(node)
                scope_kinds.pop()
                stack.pop()

            def visit_AnnAssign(self, node):
                if (scope_kinds and scope_kinds[-1] == "class"
                        and isinstance(node.target, ast.Name)):
                    owner = f"{module}:{'.'.join(stack)}"
                    class_attribute_annotations[(owner, node.target.id)] = _annotation_text(
                        node.annotation)
                self.generic_visit(node)

            def _function(self, node):
                qualname = ".".join((*stack, node.name))
                key = f"{module}:{qualname}"
                return_annotation, economic_formula = _formula_metadata(node)
                definitions.append(_Definition(key, path.relative_to(root).as_posix(), node.lineno,
                                               node.name, return_annotation, economic_formula))
                if scope_kinds and scope_kinds[-1] == "class":
                    class_method_targets[node.name].add(key)
                stack.append(node.name)
                scope_kinds.append("function")
                self.generic_visit(node)
                scope_kinds.pop()
                stack.pop()

            visit_FunctionDef = _function
            visit_AsyncFunctionDef = _function

        DefinitionVisitor().visit(tree)

    definition_keys = {definition.key for definition in definitions}
    class_attribute_targets: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    for owner_field, annotation in class_attribute_annotations.items():
        for class_name, targets in class_targets_by_name.items():
            if re.search(rf"\b{re.escape(class_name)}\b", annotation):
                class_attribute_targets[owner_field].update(targets)
    calls: dict[str, set[str]] = collections.defaultdict(set)
    provider_reads: dict[str, set[str]] = collections.defaultdict(set)
    provider_members = _provider_members_by_name()

    for _path, module, tree, module_aliases, symbol_aliases in parsed:
        stack: list[str] = []
        classes: list[str] = []
        binding_stack: list[dict[str, set[str]]] = [{}]
        object_binding_stack: list[dict[str, set[str]]] = [{}]

        def annotation_object_types(annotation: str) -> set[str]:
            found = set()
            for class_name, targets in class_targets_by_name.items():
                if re.search(rf"\b{re.escape(class_name)}\b", annotation):
                    found.update(targets)
            return found

        def object_types(node: ast.AST | None) -> set[str]:
            if isinstance(node, ast.Name):
                return set(object_binding_stack[-1].get(node.id, ()))
            if isinstance(node, ast.Call):
                chain = _attribute_chain(node.func)
                if chain and chain[-1] in {"expectation", "closed_form_transition"}:
                    # Both seams return apply_option.Expectation (the latter as one member of its
                    # closed-form union); composer narrows it with isinstance before method use.
                    return {"common.apply_option:Expectation"}
                return set()
            if not isinstance(node, ast.Attribute):
                return set()
            bases = object_types(node.value)
            if isinstance(node.value, ast.Name) and node.value.id == "model":
                # The audit scopes use ``model.mine``/``model.theirs`` exclusively for StateModel's
                # typed side protocol, including older unannotated board-choice helpers.
                bases.add("common.state_model:StateModel")
            out = set()
            for base in bases:
                out.update(class_attribute_targets.get((base, node.attr), ()))
                if base == "common.state_model:StateModel" and node.attr == "mine":
                    out.add("common.state_model:MySide")
                elif base == "common.state_model:StateModel" and node.attr == "theirs":
                    out.add("common.state_model:TheirSide")
            return out

        def caller(node) -> str:
            return f"{module}:{'.'.join(stack) or '<module>'}@{node.lineno}"

        def resolve(func: ast.AST) -> str | None:
            if isinstance(func, ast.Name):
                imported = symbol_aliases.get(func.id)
                if imported in definition_keys:
                    return imported
                # Resolve the nearest lexical definition first.  A bare call to an inner helper is
                # not the unrelated module-level function (or another class method) with that leaf.
                for depth in range(len(stack), -1, -1):
                    qualname = ".".join((*stack[:depth], func.id))
                    local = f"{module}:{qualname}"
                    if local in definition_keys:
                        return local
                return None
            chain = _attribute_chain(func)
            if len(chain) < 2:
                return None
            head, tail = chain[0], chain[1:]
            if head in {"self", "cls"} and classes:
                target = f"{module}:{classes[-1]}.{'.'.join(tail)}"
                if target in definition_keys:
                    return target
                # Pilot-style mixins deliberately call methods supplied by a sibling mixin through
                # ``self``; they also reach the composed CombatMath object through ``self.combat``.
                # A unique *class method* with the requested leaf is receiver/protocol evidence,
                # unlike a global bare-name or arbitrary attribute join (``plan.cost`` is untouched).
                mixin_targets = class_method_targets.get(tail[-1], set())
                if len(tail) > 1 and tail[-2] in {"combat", "_combat"}:
                    combat_targets = {
                        key for key in mixin_targets
                        if key.startswith("common.strategy.combat_math.")
                    }
                    if len(combat_targets) == 1:
                        return next(iter(combat_targets))
                if len(mixin_targets) == 1:
                    return next(iter(mixin_targets))
                return None
            typed_targets = set()
            for class_target in object_types(func.value if isinstance(func, ast.Attribute) else None):
                exact = f"{class_target}.{tail[-1]}"
                if exact in definition_keys:
                    typed_targets.add(exact)
                    continue
                class_module = class_target.split(":", 1)[0]
                typed_targets.update(
                    key for key in class_method_targets.get(tail[-1], ())
                    if key.startswith(f"{class_module}:")
                )
            if len(typed_targets) == 1:
                return next(iter(typed_targets))
            if head in module_aliases:
                target = f"{module_aliases[head]}:{'.'.join(tail)}"
                return target if target in definition_keys else None
            if head in symbol_aliases:
                base_module, base_symbol = symbol_aliases[head].split(":", 1)
                module_target = f"{base_module}.{base_symbol}:{'.'.join(tail)}"
                if module_target in definition_keys:
                    return module_target
                target = f"{base_module}:{base_symbol}.{'.'.join(tail)}"
                return target if target in definition_keys else None
            target = f"{module}:{'.'.join(chain)}"
            return target if target in definition_keys else None

        def bind(target: ast.AST, types: set[str]) -> None:
            if not types:
                return
            if isinstance(target, ast.Name):
                binding_stack[-1][target.id] = set(types)
            elif isinstance(target, (ast.Tuple, ast.List)):
                for item in target.elts:
                    bind(item, types)

        def bind_object(target: ast.AST, types: set[str]) -> None:
            if not types:
                return
            if isinstance(target, ast.Name):
                object_binding_stack[-1][target.id] = set(types)
            elif isinstance(target, (ast.Tuple, ast.List)):
                for item in target.elts:
                    bind_object(item, types)

        def receiver_types(node: ast.AST, field: str) -> set[str]:
            candidates = set(provider_members.get(field, ()))
            inferred = _provider_expr_types(node, binding_stack[-1]) & candidates
            if inferred:
                return inferred
            if isinstance(node, ast.Name):
                return _named_provider_hint(node.id, candidates)
            return set()

        class UsageVisitor(ast.NodeVisitor):
            def visit_ClassDef(self, node):
                stack.append(node.name)
                classes.append(".".join(stack))
                self.generic_visit(node)
                classes.pop()
                stack.pop()

            def _function(self, node):
                stack.append(node.name)
                bindings: dict[str, set[str]] = {}
                object_bindings: dict[str, set[str]] = {}
                for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
                    annotation = _annotation_text(arg.annotation)
                    if "AttackStat" in annotation:
                        bindings[arg.arg] = {"AttackStat"}
                    elif "CardStat" in annotation:
                        bindings[arg.arg] = {"CardStat"}
                    object_bindings[arg.arg] = annotation_object_types(annotation)
                binding_stack.append(bindings)
                object_binding_stack.append(object_bindings)
                self.generic_visit(node)
                object_binding_stack.pop()
                binding_stack.pop()
                stack.pop()

            visit_FunctionDef = _function
            visit_AsyncFunctionDef = _function

            def visit_Assign(self, node):
                types = _provider_expr_types(node.value, binding_stack[-1])
                object_values = object_types(node.value)
                for target in node.targets:
                    bind(target, types)
                    bind_object(target, object_values)
                self.generic_visit(node)

            def visit_AnnAssign(self, node):
                annotation = _annotation_text(node.annotation)
                types = ({"AttackStat"} if "AttackStat" in annotation else
                         {"CardStat"} if "CardStat" in annotation else
                         _provider_expr_types(node.value, binding_stack[-1]) if node.value else set())
                bind(node.target, types)
                bind_object(node.target, annotation_object_types(annotation)
                            or (object_types(node.value) if node.value else set()))
                self.generic_visit(node)

            def visit_For(self, node):
                types = _provider_expr_types(node.iter, binding_stack[-1])
                chain = _attribute_chain(node.iter.func) if isinstance(node.iter, ast.Call) else ()
                if chain and chain[-1] == "attached_tool_stats":
                    types = {"CardStat"}
                bind(node.target, types)
                self.generic_visit(node)

            visit_AsyncFor = visit_For

            def visit_comprehension(self, node):
                types = _provider_expr_types(node.iter, binding_stack[-1])
                chain = _attribute_chain(node.iter.func) if isinstance(node.iter, ast.Call) else ()
                if chain and chain[-1] == "attached_tool_stats":
                    types = {"CardStat"}
                bind(node.target, types)
                self.generic_visit(node)

            def visit_Call(self, node):
                target = resolve(node.func)
                if target is not None:
                    calls[target].add(caller(node))
                # Deferred-choice registries carry executable rank functions as qualified keyword
                # values rather than calling them here.  Record that source-proved runtime edge;
                # arbitrary bare attribute-name joins remain forbidden.
                for keyword in node.keywords:
                    if keyword.arg == "rank" and isinstance(keyword.value, ast.Name):
                        registered = resolve(keyword.value)
                        if registered is not None:
                            calls[registered].add(caller(node))
                if (isinstance(node.func, ast.Name) and node.func.id == "getattr"
                        and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
                        and isinstance(node.args[1].value, str)):
                    field = node.args[1].value
                    for class_name in receiver_types(node.args[0], field):
                        provider_reads[f"{class_name}.{field}"].add(caller(node))
                self.generic_visit(node)

            def visit_Attribute(self, node):
                if isinstance(node.ctx, ast.Load):
                    for class_name in receiver_types(node.value, node.attr):
                        provider_reads[f"{class_name}.{node.attr}"].add(caller(node))
                self.generic_visit(node)

        UsageVisitor().visit(tree)
    return (
        tuple(sorted(definitions, key=lambda item: item.key)),
        MappingProxyType({key: _ordered(items) for key, items in sorted(calls.items())}),
        MappingProxyType({key: _ordered(items) for key, items in sorted(provider_reads.items())}),
    )


def _required_equation_scope(definition: _Definition) -> bool:
    path = definition.path.replace("\\", "/")
    name = path.rsplit("/", 1)[-1]
    return (
        name.endswith("value.py")
        or name in {"state_value.py", "needs.py", "hold_value.py",
                    "board_expectation.py", "board_choice.py"}
        or "/common/deciders/" in f"/{path}"
        or "/common/strategy/combat_math/" in f"/{path}"
        or path.endswith("/common/strategy/combat.py")
    )


def _named_equation(definition: _Definition) -> bool:
    return (any(token in definition.leaf.lower() for token in _EQUATION_TOKENS)
            or definition.key in _EXPLICIT_EQUATIONS
            or definition.key in EQUATION_SEMANTICS
            or definition.key in EQUATION_CONSUMER_OVERRIDES
            or definition.key in EQUATION_EXCLUSIONS
            or definition.economic_formula)


def _state_consumer_owners(definition: _Definition) -> tuple[str, ...]:
    module, qualname = definition.key.split(":", 1)
    leaf = definition.leaf
    if module != "common.state_value":
        return ()
    if leaf in state_value.FAMILIES:
        return (f"state:{leaf}",)
    if leaf in state_value.TERMINAL_FAMILIES or leaf.startswith("attack_ev") \
            or leaf.startswith("_attack_"):
        return ("terminal:attack_ev",)
    if leaf == "state_value":
        return _ordered(f"state:{name}" for name in state_value.FAMILIES)
    helpers = {
        "_development_legs": ("state:development",),
        "_exposed_bodies": ("state:survival",),
        "_hand_legs": ("state:hand",),
        "_predicted_loss": ("state:survival",),
        "_reachable_target_values": ("state:threat",),
        "_readiness_odds": ("state:readiness",),
        "_ready_bodies": ("state:readiness",),
        "_survival_clock": ("state:survival",),
        "worth_to_prizes": ("state:hand",),
    }
    return helpers.get(leaf, ())


def _adapter_like(definition: _Definition) -> bool:
    leaf = definition.leaf.lower()
    return (
        leaf == "working"
        or leaf.endswith(("_id", "_ids", "_set", "_types", "_deadline"))
        or definition.key.endswith((":_all_families", ":blind_spots", ":registry_gaps",
                                     ":double_counted"))
        or definition.key in {
            "common.needs:general_worth_slot",
            "common.scouting.provider:CardStat.prize_value",
            "common.state_model:BodyView.prize_value",
        }
    )


def _registered_owner_reach(
        definitions: tuple[_Definition, ...],
        calls: Mapping[str, tuple[str, ...]],
) -> Mapping[str, tuple[str, ...]]:
    """Registered owners reached through receiver-qualified production callers.

    A reviewed semantic equation is the nearest ownership boundary even when it is LOSSY or
    LOCAL-ONLY.  Walking above that boundary would leak every family reached by its composite caller
    back onto one input component.  State-value functions and explicit/search consumers are the
    other real boundaries.
    """
    by_key = {definition.key: definition for definition in definitions}

    def direct(key: str) -> tuple[bool, tuple[str, ...]]:
        definition = by_key.get(key)
        if definition is not None:
            owners = _state_consumer_owners(definition)
            if owners:
                return True, owners
        consumer = EQUATION_CONSUMER_OVERRIDES.get(key)
        if consumer is not None and consumer[1]:
            return True, consumer[0]
        semantic = EQUATION_SEMANTICS.get(key)
        if semantic is not None:
            return True, semantic[1]
        if key in SEARCH_CONSUMER_OWNERS:
            return True, SEARCH_CONSUMER_OWNERS[key]
        return False, ()

    result: dict[str, tuple[str, ...]] = {}
    for definition in definitions:
        owners: set[str] = set()
        pending = [definition.key]
        seen = {definition.key}
        while pending:
            key = pending.pop()
            if key != definition.key:
                boundary, reached = direct(key)
                if boundary:
                    owners.update(reached)
                    # Stop even when the boundary is LOCAL-ONLY and therefore contributes no owner.
                    continue
            for caller_site in calls.get(key, ()):
                caller_key = caller_site.split("@", 1)[0]
                if caller_key not in seen:
                    seen.add(caller_key)
                    pending.append(caller_key)
        result[definition.key] = _ordered(owners)
    return MappingProxyType(dict(sorted(result.items())))


def equation_candidates(root: Path = _ROOT) -> tuple[EquationCandidate, ...]:
    definitions, calls, _provider_reads = _source_index(root)
    registered_reach = _registered_owner_reach(definitions, calls)
    out = []
    for definition in definitions:
        if not (_required_equation_scope(definition) or _named_equation(definition)):
            continue
        module, _qualname = definition.key.split(":", 1)
        semantic = EQUATION_SEMANTICS.get(definition.key)
        consumer_semantic = EQUATION_CONSUMER_OVERRIDES.get(definition.key)
        absolute: tuple[str, ...] = ()
        local: tuple[str, ...] = ()
        classification = ""
        callers = calls.get(definition.key, ())

        if module == "common.snapshot_coverage":
            disposition = "excluded"
            reason = "vocabulary enumeration helper; returns registry members, not economic value"
        elif definition.key in EQUATION_EXCLUSIONS:
            disposition = "excluded"
            reason = EQUATION_EXCLUSIONS[definition.key]
        elif semantic is not None:
            disposition = "owner"
            classification, absolute, _route, reason = semantic
            local = (definition.key.replace(":", "."),)
        elif consumer_semantic is not None:
            absolute, classification, reason = consumer_semantic
            disposition = "consumer" if classification else "excluded"
        elif _adapter_like(definition):
            disposition = "excluded"
            reason = "identity/telemetry/adapter helper; returns metadata rather than economic value"
        elif module == "common.state_value":
            absolute = (_state_consumer_owners(definition)
                        or registered_reach.get(definition.key, ()))
            classification = LEAF_ONLY if absolute else ""
            disposition = "consumer" if classification else "excluded"
            reason = (("registered leaf/terminal implementation or qualified helper path; "
                       "not a local claimant") if classification else
                      "state-value support helper with no registered owner path or scalar claim")
        elif definition.economic_formula:
            disposition = "owner"
            absolute = registered_reach.get(definition.key, ())
            local = (definition.key.replace(":", "."),)
            classification = LOSSY_REEXPRESSION if absolute else LOCAL_ONLY
            if absolute:
                reason = (
                    "AST-proved live numeric economic formula; qualified caller graph reaches "
                    f"{','.join(absolute)}, but identical inputs/units are not proved; fail-closed LOSSY"
                )
            else:
                caller_evidence = (f"{len(callers)} qualified production caller(s)" if callers else
                                   "no statically proved production caller")
                reason = (
                    "AST-proved numeric economic formula with " + caller_evidence +
                    "; no registered absolute oracle is reached; fail-closed LOCAL-ONLY"
                )
        elif registered_reach.get(definition.key):
            disposition = "excluded"
            reason = (
                "non-economic structural/transition/enumeration helper; a qualified caller later "
                f"reaches {','.join(registered_reach[definition.key])}, but call reach is not scalar "
                "value ownership"
            )
        elif callers:
            disposition = "excluded"
            reason = (
                "non-economic structural/boolean/provider helper with qualified production callers; "
                "no numeric scalar value-owner claim"
            )
        else:
            disposition = "excluded"
            reason = (
                "non-economic structural/boolean/provider helper with no statically proved production "
                "caller and no numeric scalar value-owner claim"
            )

        out.append(EquationCandidate(
            key=definition.key,
            path=definition.path,
            line=definition.line,
            disposition=disposition,
            reason=reason,
            runtime_callers=callers,
            absolute_owners=_ordered(absolute),
            local_owners=_ordered(local),
            classification=classification,
        ))
    return tuple(sorted(out, key=lambda candidate: candidate.key))


def _equation_records(
        candidates: tuple[EquationCandidate, ...],
        exposures: Mapping[str, tuple[Exposure, str]] | None = None,
) -> list[AuditRecord]:
    records = []
    exposures = exposures or {}
    for candidate in candidates:
        if candidate.disposition == "excluded" or not candidate.classification:
            continue
        semantic = EQUATION_SEMANTICS.get(candidate.key)
        route = semantic[2] if semantic is not None else (
            "#495" if candidate.key ==
            "common.strategy.combat_math.energy:EnergyMixin._attack_slots" else
            "#492 backlog" if candidate.classification == LOCAL_ONLY else "#494")
        equation_exposure, exposure_evidence = exposures.get(
            candidate.key,
            (Exposure(), "exposure unmeasured: no source mechanic/provider owner join"),
        )
        search_path = _ordered((
            "composer:state_value leaf"
            if any(owner.startswith("state:") for owner in candidate.absolute_owners) else "",
            "composer:terminal_ev"
            if any(owner.startswith("terminal:") for owner in candidate.absolute_owners) else "",
        ))
        records.append(AuditRecord(
            mechanic_key=f"equation:{_slug(candidate.key)}",
            source_kind="local-equation" if candidate.disposition == "owner" else "value-consumer",
            source_symbol_or_site=f"{candidate.key} ({candidate.path}:{candidate.line})",
            transition_fate="not-a-transition",
            absolute_owners=candidate.absolute_owners,
            local_owners=candidate.local_owners,
            runtime_callers=candidate.runtime_callers,
            leaf_path=candidate.absolute_owners,
            search_path=search_path,
            classification=candidate.classification,
            evidence=_ordered((candidate.reason, exposure_evidence,
                               ("terminal_win_prize_impact=1: " +
                                TERMINAL_WIN_PRIZE_EQUATIONS[candidate.key]
                                if candidate.key in TERMINAL_WIN_PRIZE_EQUATIONS else ""))),
            exposure=equation_exposure,
            live_owner=route,
        ))
    return records


def _provider_members() -> tuple[tuple[str, str], ...]:
    out = []
    for cls in (CardStat, AttackStat):
        for field in dataclasses.fields(cls):
            # cardType is backing storage for the canonical ``is_*`` properties below.  Census both
            # would duplicate one class mechanic and the raw enum has no independent consumer.
            if field.name not in {"cardId", "attackId", "name", "synthetic", "cardType"}:
                out.append((cls.__name__, field.name))
        for name, member in vars(cls).items():
            if isinstance(member, property):
                out.append((cls.__name__, name))
    return tuple(sorted(set(out)))


def _field_default(cls, name: str):
    field = next((item for item in dataclasses.fields(cls) if item.name == name), None)
    if field is None:
        return None
    if field.default is not dataclasses.MISSING:
        return field.default
    if field.default_factory is not dataclasses.MISSING:  # pragma: no branch - no factory today
        return field.default_factory()
    return None


def _shipped_provider_stats(cards: Mapping[int, dict]
                            ) -> tuple[dict[int, CardStat], dict[int, AttackStat], dict[int, int]]:
    """Build the provider's pure adapters over cards.json without importing the native engine.

    cards.json omits engine attack ids, so deterministic synthetic ids identify only this census;
    report evidence remains the required ``(card id, attack ordinal/name)`` identity.
    """
    energy = {"colorless": 0, "grass": 1, "fire": 2, "water": 3, "lightning": 4,
              "psychic": 5, "fighting": 6, "darkness": 7, "metal": 8}
    card_type = {"pokemon": 0, "item": 1, "tool": 2, "supporter": 3, "stadium": 4,
                 "basic_energy": 5, "special_energy": 6}
    attack_rows = []
    attack_to_card: dict[int, int] = {}
    card_rows = []
    next_attack_id = 1
    for card_id, card in sorted(cards.items()):
        attack_ids = []
        for attack in card.get("attacks") or ():
            attack_id = next_attack_id
            next_attack_id += 1
            attack_ids.append(attack_id)
            attack_to_card[attack_id] = card_id
            attack_rows.append(SimpleNamespace(
                attackId=attack_id,
                name=attack.get("name") or "",
                damage=int(attack.get("damage") or 0),
                energies=tuple(int(code) for code in (attack.get("energies") or ())),
                text=attack.get("text") or "",
            ))
        stage = card.get("stage")
        skills = tuple(SimpleNamespace(name=ability.get("name") or "",
                                       text=ability.get("text") or "")
                       for ability in (card.get("abilities") or ()))
        card_rows.append(SimpleNamespace(
            cardId=card_id,
            name=card.get("name") or "",
            hp=int(card.get("hp") or 0),
            ex=bool(card.get("ex")),
            megaEx=bool(card.get("megaEx")),
            aceSpec=bool(card.get("aceSpec")),
            skills=skills,
            attacks=tuple(attack_ids),
            basic=stage == "basic",
            stage1=stage == "stage1",
            stage2=stage == "stage2",
            weakness=card.get("weakness"),
            resistance=card.get("resistance"),
            energyType=energy.get(str(card.get("energy") or "").lower()),
            retreatCost=int(card.get("retreat") or 0),
            cardType=card_type.get(card.get("category")),
            evolvesFrom=card.get("evolvesFrom"),
            tera=bool(card.get("tera")),
        ))
    return (stat_provider._build_cache(card_rows, attack_rows),
            stat_provider.build_attack_stats(attack_rows, overrides={}), attack_to_card)


def _provider_ledger(cards: Mapping[int, dict], root: Path = _ROOT) -> tuple[ProviderField, ...]:
    card_stats, attack_stats, attack_to_card = _shipped_provider_stats(cards)
    _definitions, _calls, provider_reads = _source_index(root)
    members = _provider_members()
    observed_cards: dict[tuple[str, str], set[int]] = collections.defaultdict(set)
    observed_sites: collections.Counter = collections.Counter()
    classes = {"CardStat": CardStat, "AttackStat": AttackStat}

    for class_name, table in (("CardStat", card_stats), ("AttackStat", attack_stats)):
        cls = classes[class_name]
        for key, stat in table.items():
            card_id = int(key) if class_name == "CardStat" else attack_to_card[int(key)]
            for member_class, name in members:
                if member_class != class_name:
                    continue
                value = getattr(stat, name)
                declared_field = any(field.name == name for field in dataclasses.fields(cls))
                nondefault = (value != _field_default(cls, name)) if declared_field else bool(value)
                if nondefault:
                    observed_cards[(class_name, name)].add(card_id)
                    observed_sites[(class_name, name)] += 1

    override_counts: collections.Counter = collections.Counter()
    for fields in stat_provider.load_attack_overrides().values():
        for name, value in fields.items():
            if ("AttackStat", name) in members and value != _field_default(AttackStat, name):
                override_counts[("AttackStat", name)] += 1

    out = []
    for class_name, name in members:
        cards_for_field = tuple(sorted(observed_cards.get((class_name, name), set())))
        overrides = int(override_counts.get((class_name, name), 0))
        observed = bool(cards_for_field or overrides)
        callers = tuple(caller for caller in provider_reads.get(f"{class_name}.{name}", ())
                        if not caller.startswith("common.scouting.provider:"))
        out.append(ProviderField(
            class_name=class_name,
            field_name=name,
            observed_nondefault=observed,
            observed_cards=cards_for_field,
            observed_sites=int(observed_sites.get((class_name, name), 0)),
            override_sites=overrides,
            runtime_callers=_ordered(callers),
            declaration_only_reason=("declared default-only on the shipped cards/attack parses and "
                                     "attack overrides" if not observed else ""),
        ))
    return tuple(sorted(out, key=lambda item: (item.class_name, item.field_name)))


def _provider_value_owners(
        direct_callers: tuple[str, ...],
        candidates: Mapping[str, EquationCandidate],
        calls: Mapping[str, tuple[str, ...]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Walk qualified callers upward to real classified value roots, never filename heuristics."""
    absolute: set[str] = set()
    local: set[str] = set()
    queue = collections.deque(caller.split("@", 1)[0] for caller in direct_callers)
    seen = set()
    while queue:
        symbol = queue.popleft()
        if symbol in seen:
            continue
        seen.add(symbol)
        candidate = candidates.get(symbol)
        if candidate is not None:
            absolute.update(candidate.absolute_owners)
            if candidate.disposition == "owner":
                local.update(candidate.local_owners)
            if candidate.classification:
                # This classified equation is the nearest value boundary.  Walking above it would
                # attribute every family/search consumer of a composite parent to this one field.
                continue
        module, qualname = symbol.split(":", 1)
        leaf = qualname.rsplit(".", 1)[-1]
        if symbol in {
            "common.strategy.damage:compute_active_damage",
            "common.strategy.damage:_prevented",
            "common.strategy.damage:wr_adjust",
            "common.strategy.combat_math.cards:CardFactsMixin.predicted_damage",
            "common.strategy.combat_math.cards:CardFactsMixin.predicted_max_damage",
            "common.strategy.combat_math.cards:CardFactsMixin.card_level_damage",
        }:
            absolute.update({"state:readiness", "state:survival", "state:threat",
                             "terminal:attack_ev"})
            continue
        if module == "common.state_value":
            state_owners = _state_consumer_owners(_Definition(symbol, "", 0, leaf))
            absolute.update(state_owners)
            if state_owners:
                continue
        elif module == "common.composer" and leaf in {"terminal_ev", "continuation_ev"}:
            absolute.add("terminal:attack_ev")
            continue
        queue.extend(caller.split("@", 1)[0] for caller in calls.get(symbol, ()))
    return _ordered(absolute), _ordered(local)


def _stat_records(ledger: tuple[ProviderField, ...], exposure: _ExposureIndex,
                  equations: tuple[EquationCandidate, ...], root: Path = _ROOT) -> list[AuditRecord]:
    _definitions, calls, _provider_reads = _source_index(root)
    equation_by_key = {candidate.key: candidate for candidate in equations}
    records = []
    for item in ledger:
        if not item.observed_nondefault:
            continue
        cls_name, field, callers = item.class_name, item.field_name, item.runtime_callers
        absolute, local = _provider_value_owners(callers, equation_by_key, calls)
        written_dimensions: tuple[str, ...] = ()
        forced_classification = ""
        forced_owner = ""
        forced_search_path: tuple[str, ...] = ()
        semantic_evidence: set[str] = set()
        if cls_name == "CardStat" and field in {
                "retreatReduction", "retreatFreeAtHp", "retreatFreeGrant"}:
            absolute = ("state:readiness",)
            local = ()
            forced_classification = SHARED_EXACT
            forced_owner = "#500"
            semantic_evidence.add(
                "Issue #500: active-position readiness consumes canonical retreat legality from "
                f"CardStat.{field}")
        elif cls_name == "CardStat" and field == "hpBonus":
            # This is a distinct Tool class from mobility.  The transition is represented, but the
            # survival leaf observes only integer clock crossings and the local Tool channel abstains.
            absolute = ("state:survival",)
            local = ()
            written_dimensions = ("damage_counters",)
            forced_classification = LOSSY_REEXPRESSION
            forced_owner = "#494"
            semantic_evidence.update({
                "board_delta._attach/evolve_body apply hpBonus to hp/maxHp and declare "
                "damage_counters",
                "state:survival sees hpBonus only when the integer turns_to_ko_me clock crosses; "
                "sub-turn +HP remains a zero delta",
                "ADR-0135: the local Tool-attach channel abstains for the +HP class; no local value "
                "owner remains since Issue #386",
            })
        elif cls_name == "CardStat" and field == "handSizeDamage":
            # The shipped mechanic's live closed-form context is the forward hand-size survival
            # read.  Generic damage-call reach must not attribute unrelated families/terminal legs
            # that do not carry the required hand context.
            absolute = ("state:survival",)
            local = ("common.deciders.context_build.ContextMixin._forward_hand_size_damage",)
            forced_classification = LOSSY_REEXPRESSION
            forced_owner = "#494"
            semantic_evidence.add(
                "authored hand-context join: _forward_hand_size_damage feeds the survival clock; "
                "context-free damage reach does not prove other family ownership")
        elif cls_name == "CardStat" and field in {"ex", "megaEx", "is_ex_body"}:
            absolute = ("state:readiness", "state:survival", "state:threat", "terminal:attack_ev")
            local = (
                "common.deciders.board_build.BoardMixin._typed_boost_total",
                "common.deciders.heal.HealMixin._heal_survival_gain",
                "common.deciders.lethal.LethalMixin._boost_lethal_tactical",
                "common.deciders.lines.LineMixin._bench_wincon_prize_value",
                "common.deciders.lines.LineMixin._wincon_prize_value",
            )
            forced_classification = LOSSY_REEXPRESSION
            forced_owner = "#494"
            semantic_evidence.update({
                f"CardStat.{field} feeds the canonical is_ex_body/prize_value adapters",
                "the adapter reaches boost gates plus survival/terminal prize economics; local line, "
                "heal, and boost equations compose it separately",
            })
        elif cls_name == "CardStat" and field in {"holderNameFamily", "holderNoRuleBox"}:
            absolute = ("state:readiness", "state:survival", "state:threat", "terminal:attack_ev")
            local = (
                "common.deciders.attach.AttachMixin._tool_attach_value",
                "common.deciders.board_build.BoardMixin._typed_boost_total",
                "common.deciders.lethal.LethalMixin._boost_lethal_tactical",
            )
            forced_classification = LOSSY_REEXPRESSION
            forced_owner = "#494"
            semantic_evidence.update({
                f"CardStat.applies_to_holder reads backing gate {field}",
                "the holder gate controls mobility/+HP/damage-boost Tool payloads; those payloads "
                "have distinct local and registered owners",
            })
        elif cls_name == "CardStat" and field == "is_tool":
            absolute = ("state:readiness", "state:survival", "state:threat", "terminal:attack_ev")
            local = (
                "common.deciders.attach.AttachMixin._tool_attach_value",
                "common.deciders.board_build.BoardMixin._typed_boost_total",
                "common.deciders.lethal.LethalMixin._boost_lethal_tactical",
            )
            forced_classification = LOSSY_REEXPRESSION
            forced_owner = "#494"
            semantic_evidence.add(
                "canonical cardType adapter routes Tool payload classes; payload fields, not arbitrary "
                "control-flow reach, establish readiness/survival/threat/terminal and local owners")
        elif cls_name == "CardStat" and field == "is_pokemon":
            absolute = ("state:development", "state:readiness", "state:survival", "state:threat")
            local = ("common.deploy_value.deploy_value",)
            forced_classification = LOSSY_REEXPRESSION
            forced_owner = "#494"
            semantic_evidence.add(
                "canonical hp>0 class adapter routes bodies into board development/combat families; "
                "terminal/prize ownership is carried by attack/prize fields, not this predicate")
        elif cls_name == "CardStat" and field == "is_item":
            absolute = ()
            local = (
                "common.board_expectation.expectation",
                "common.strategy.doctrines.doctrine_fetch.FetchMixin._chain_value_from",
            )
            forced_classification = LOCAL_ONLY
            forced_owner = "#494"
            semantic_evidence.add(
                "Item is a structural play/fetch class consumed by local expectation/chain equations; "
                "its Effect Clauses, not the class predicate, own resulting absolute dimensions")
        elif cls_name == "CardStat" and field == "is_supporter":
            absolute = ("state:readiness", "state:threat")
            local = (
                "common.board_expectation.expectation",
                "common.deciders.evolve.EvolveMixin._evolve_income_delta",
            )
            forced_classification = LOSSY_REEXPRESSION
            forced_owner = "#495"
            semantic_evidence.add(
                "Supporter class gates the shared attach Budget and local information/enabler equations; "
                "no unrelated terminal/state family is inferred from later option control flow")
        elif cls_name == "CardStat" and field == "is_stadium":
            absolute = ("state:readiness", "state:survival", "state:threat")
            local = ()
            forced_classification = LEAF_ONLY
            forced_owner = "#494"
            forced_search_path = ("composer:_still_legal",)
            semantic_evidence.add(
                "Stadium class routes the canonical stadium state/legality path; its static payload is "
                "owned by readiness/survival/threat, with no independent local scalar")
        elif cls_name == "CardStat" and field in {
                "is_energy", "is_basic_energy", "is_typed_basic_energy"}:
            absolute = ("state:readiness",)
            local = ("common.strategy.doctrines.doctrine_fetch.FetchMixin._chain_value_from",)
            forced_classification = LOSSY_REEXPRESSION
            forced_owner = "#495"
            semantic_evidence.add(
                "canonical cardType adapter routes typed Energy into the readiness Budget and local "
                "fetch-chain value; no unrelated state family is inferred from control flow")
        elif cls_name == "CardStat" and field in {
                "damageBoost", "damageBoostType", "damageBoostVsEx"}:
            absolute = ("state:readiness", "state:threat", "terminal:attack_ev")
            local = (
                "common.deciders.board_build.BoardMixin._typed_boost_total",
                "common.deciders.lethal.LethalMixin._boost_lethal_tactical",
            )
            forced_classification = LOSSY_REEXPRESSION
            forced_owner = "#494"
            semantic_evidence.update({
                f"StateModel._SideBase.damage_boosts carries CardStat.{field} into the shared "
                "damage context",
                "state readiness/threat and terminal attack_ev consume the damage oracle; local "
                "lethal/build equations also gate and price the boost",
            })
        elif cls_name == "CardStat" and field == "is_special_energy":
            absolute = ("state:readiness",)
            local = ("common.deciders.attach.AttachMixin._attach_value",)
            forced_classification = LOSSY_REEXPRESSION
            forced_owner = "#495"
            semantic_evidence.update({
                "EnergyMixin._special_energy_groups reads CardStat.is_special_energy into the "
                "typed attach Budget",
                "the same typed Budget reaches the shared readiness oracle and the local Attach "
                "marginal on different compositions",
            })
        elif cls_name == "CardStat" and field == "prize_value":
            absolute = ("state:survival", "terminal:attack_ev")
            local = (
                "common.deciders.heal.HealMixin._heal_survival_gain",
                "common.deciders.lines.LineMixin._bench_wincon_prize_value",
                "common.deciders.lines.LineMixin._wincon_prize_value",
            )
            forced_classification = LOSSY_REEXPRESSION
            forced_owner = "#494"
            semantic_evidence.add(
                "the same CardStat.prize_value feeds different economics: continuous local heal/line "
                "credit, integer-clock survival thresholds, and terminal KO payoff")
        elif cls_name == "AttackStat" and field in {"benchSnipe", "benchSpread"}:
            absolute = (("state:threat", "terminal:attack_ev") if field == "benchSnipe"
                        else ("terminal:attack_ev",))
            local = ("common.strategy.objectives.race_values",)
            forced_classification = LOSSY_REEXPRESSION
            forced_owner = "#494"
            semantic_evidence.update({
                f"StateModel._attack_profile carries AttackStat.{field} into "
                "state_value._attack_rider_value",
                f"CombatMath.rider_{'snipe' if field == 'benchSnipe' else 'spread'} feeds tactical "
                "race/bench consumers through mixin dispatch",
                ("state:threat over-reads multi-target snipe multiplicity"
                 if field == "benchSnipe" else
                 "state:threat deliberately omits spread allocation while terminal attack_ev reads it"),
            })
        elif cls_name == "AttackStat" and field == "recoil":
            absolute = ()
            local = (
                "common.composer._survives_recoil",
                "common.deciders.hand.HandMixin._is_simultaneous_draw",
                "common.deciders.tactical.TacticalMixin._recoil_flips_doom",
            )
            forced_classification = LOCAL_ONLY
            forced_owner = "#494"
            forced_search_path = ("composer:_selection_candidates",)
            semantic_evidence.update({
                "CombatMath.rider_recoil feeds Composer._survives_recoil and tactical draw/doom gates",
                "state_value terminal attack_ev explicitly declares recoil blind: no post-attack board "
                "or prize-denominated recoil cost",
            })
        elif cls_name == "AttackStat" and field == "selfReturn":
            absolute = ()
            local = ("common.deciders.tactical.TacticalMixin._self_return_escape_credit",)
            forced_classification = LOCAL_ONLY
            forced_owner = "#494"
            semantic_evidence.update({
                "TacticalMixin._self_return_escape_credit prices the doomed multi-prize escape",
                "state_value/terminal attack_ev has no post-attack self-return board transition",
            })
        elif cls_name == "AttackStat" and field in {
                "nextTurnPreventAll", "nextTurnReduction", "nextTurnSelfBonus"}:
            absolute = ("state:readiness", "state:survival", "state:threat",
                        "terminal:attack_ev")
            local = ()
            forced_classification = LEAF_ONLY
            forced_owner = "#494"
            semantic_evidence.update({
                f"TransientTracker._grant_fields carries AttackStat.{field} into BodyView.grant",
                "the transient grant reaches shared damage/clock profiles consumed by registered "
                "state families and terminal attack_ev",
            })
        elif cls_name == "AttackStat" and field in {
                "nextTurnSameAttackLock", "nextTurnSelfLock"}:
            absolute = ("terminal:attack_ev",)
            local = ("common.deciders.deny.DenyMixin._lock_sequence_cost",)
            forced_classification = LOSSY_REEXPRESSION
            forced_owner = "#494"
            semantic_evidence.update({
                f"StateModel._attack_profile copies AttackStat.{field} into AttackProfile",
                "state_value.attack_ev_legs prices the lock through _attack_next_turn_cost and "
                "terminal attack_ev",
                "DenyMixin._lock_sequence_cost is the live tactical damage-scale lock equation "
                "called by TacticalMixin._tactical and _copied_attack_tactical",
            })
        classification = forced_classification or _classification(
            fate="modelled-stat", absolute=_ordered(absolute), local=_ordered(local))
        evidence = {f"{len(callers)} AST attribute-read sites"}
        if not callers and not semantic_evidence:
            evidence.add("declared provider field has no runtime attribute reader under src/common")
        elif not callers:
            evidence.add("read through the named canonical provider adapter; backing read collapsed")
        evidence.add(f"observed non-default on {item.observed_sites} shipped parsed records")
        if item.override_sites:
            evidence.add(f"non-default in {item.override_sites} attack override records")
            evidence.add(
                "card/deck/corpus exposure unmeasured: attack override ids are not soundly joinable "
                "to cards.json synthetic attack ids")
        if forced_classification:
            evidence.add("authored provider semantic join")
        evidence.update(semantic_evidence)
        records.append(AuditRecord(
            mechanic_key=f"provider-stat:{cls_name.lower()}:{field}",
            source_kind="card-stat" if cls_name == "CardStat" else "attack-stat",
            source_symbol_or_site=f"common.scouting.provider.{cls_name}.{field}",
            transition_fate="modelled-stat",
            written_dimensions=written_dimensions,
            absolute_owners=absolute,
            local_owners=local,
            runtime_callers=_ordered(callers),
            leaf_path=_ordered(absolute),
            search_path=_ordered((*forced_search_path,
                                  *(("composer:state_value leaf",) if absolute else ()))),
            classification=classification,
            evidence=_ordered(evidence),
            exposure=exposure.for_cards(
                item.observed_cards, sites=item.observed_sites + item.override_sites),
            live_owner=(forced_owner or
                        ("#494" if classification != LOCAL_ONLY else "#492 backlog")),
        ))
    return records


def _equation_exposures(
        candidates: tuple[EquationCandidate, ...],
        sites: tuple[SourceSite, ...],
        cards: Mapping[int, dict],
        provider_fields: tuple[ProviderField, ...],
        stat_records: tuple[AuditRecord, ...],
        exposure: _ExposureIndex,
        root: Path = _ROOT,
) -> Mapping[str, tuple[Exposure, str]]:
    """Join equations to source mechanics without manufacturing equation-site counts.

    A local equation receives exact apply sites or strategy-role declarations that name its owner.
    Provider rows are a fallback when no more specific source site exists.  A leaf consumer receives
    the source rows that name its absolute family.  Provider joins use unique ``field/card`` pairs:
    the shipped parser's occurrence total remains on the provider record, but is not summed across
    fields into a duplicated equation population.
    """
    local_source: dict[str, set[tuple[str, str, int]]] = collections.defaultdict(set)
    absolute_source: dict[str, set[tuple[str, str, int]]] = collections.defaultdict(set)

    for site in sites:
        writes = _site_owner_writes(site, _site_writes(site))
        absolute, local = _owners_for(writes)
        reference = ("card-effect", f"{site.card_id}:{site.ordinal}", site.card_id)
        for owner in local:
            local_source[owner].add(reference)
        for owner in absolute:
            absolute_source[owner].add(reference)

    # Strategy roles are source declarations for the two line-level prize selectors.  Executing the
    # shipped declarative modules is the same loading path used by agents and avoids parsing aliases.
    line_owners = (
        "common.deciders.lines.LineMixin._bench_wincon_prize_value",
        "common.deciders.lines.LineMixin._wincon_prize_value",
    )
    for path in sorted((root / "src" / "agents").glob("*/strategy.py")):
        strategy = runpy.run_path(str(path)).get("STRATEGY")
        if strategy is None or not isinstance(getattr(strategy, "roles", None), Mapping):
            raise CoverageError(f"{path}: shipped strategy has no roles mapping")
        for raw_card_id, roles in sorted(strategy.roles.items()):
            role_names = {str(role) for role in (roles or ())}
            if not role_names & {"primary_attacker", "win_condition"}:
                continue
            card_id = int(raw_card_id)
            reference = ("strategy-role", f"{path.parent.name}:{card_id}", card_id)
            for owner in line_owners:
                local_source[owner].add(reference)

    fields_by_key = {
        (field.class_name.lower(), field.field_name): field
        for field in provider_fields if field.observed_nondefault
    }
    provider_by_reader: dict[str, set[tuple[str, str, int]]] = collections.defaultdict(set)
    for field in fields_by_key.values():
        references = {
            ("provider", f"{field.class_name}.{field.field_name}:{card_id}", card_id)
            for card_id in field.observed_cards
        }
        for caller in field.runtime_callers:
            provider_by_reader[caller.split("@", 1)[0]].update(references)

    for record in stat_records:
        _prefix, class_name, field_name = record.mechanic_key.split(":", 2)
        field = fields_by_key[(class_name, field_name)]
        for card_id in field.observed_cards:
            reference = ("provider", f"{field.class_name}.{field.field_name}:{card_id}", card_id)
            for owner in record.absolute_owners:
                absolute_source[owner].add(reference)

    ko_equation = "common.strategy.combat_math.reach:ReachMixin.best_affordable_ko_value"
    ko_attack_references = {
        ("terminal-attack", f"{card_id}:{ordinal}", int(card_id))
        for card_id, card in cards.items()
        for ordinal, _attack in enumerate(card.get("attacks") or ())
    }
    typed_boost_equation = "common.deciders.board_build:BoardMixin._typed_boost_total"
    typed_boost_references = {
        ("provider", f"{field.class_name}.{field.field_name}:{card_id}", card_id)
        for field in fields_by_key.values()
        if field.class_name == "CardStat"
        and field.field_name in {"damageBoost", "damageBoostType", "damageBoostVsEx"}
        for card_id in field.observed_cards
    }

    result = {}
    for candidate in candidates:
        references: set[tuple[str, str, int]] = set()
        if candidate.disposition == "owner":
            if candidate.key == typed_boost_equation:
                # The equation measures the three boost payload fields.  Holder/ex class gates are
                # separately audited provider mechanics and must not multiply its source exposure.
                references.update(typed_boost_references)
            else:
                for owner in candidate.local_owners:
                    references.update(local_source.get(owner, ()))
            if not references:
                # Direct field reads are mechanically attributable.  Do not expand through an
                # equation's entire helper closure: that would count the same card once per field
                # and turn a composite helper into thousands of duplicate "sites".
                if candidate.key == ko_equation:
                    # This equation maximises over printed attacks; one attack is its natural source
                    # site.  Counting every field it reads would duplicate that same attack.
                    references.update(ko_attack_references)
                else:
                    references.update(provider_by_reader.get(candidate.key, ()))
        elif candidate.disposition == "consumer":
            for owner in candidate.absolute_owners:
                references.update(absolute_source.get(owner, ()))
        if not references:
            continue
        kinds = collections.Counter(kind for kind, _identity, _card_id in references)
        card_ids = [card_id for _kind, _identity, card_id in references]
        detail = ", ".join(f"{kind}={count}" for kind, count in sorted(kinds.items()))
        result[candidate.key] = (
            exposure.for_cards(card_ids, sites=len(references)),
            f"exposure source join: {detail}; unique source sites={len(references)}",
        )
    return MappingProxyType(dict(sorted(result.items())))


def _search_records(root: Path = _ROOT) -> list[AuditRecord]:
    definitions, calls, _attrs = _source_index(root)
    present = {definition.key: definition for definition in definitions}
    missing = [key for key, _label, _classification in COMPOSER_SEARCH_CONSUMERS if key not in present]
    if missing:
        raise CoverageError(f"Composer consumer symbols disappeared: {missing}")
    records = []
    for key, label, classification in COMPOSER_SEARCH_CONSUMERS:
        definition = present[key]
        deliberate = ""
        live_owner = "#496"
        if classification == DELIBERATE_ZERO:
            deliberate, live_owner = SEARCH_ZERO_RULINGS[key]
        absolute = SEARCH_CONSUMER_OWNERS.get(key, ())
        records.append(AuditRecord(
            mechanic_key=f"search-consumer:{_slug(label)}",
            source_kind="composer-search-consumer",
            source_symbol_or_site=f"{key} ({definition.path}:{definition.line})",
            transition_fate="search",
            absolute_owners=absolute,
            runtime_callers=calls.get(key, ()),
            leaf_path=absolute,
            search_path=(f"composer:{label}",),
            classification=classification,
            evidence=_ordered({
                "static search surface; SEARCH-LOSS requires a sensitivity probe",
                f"BEAM_WIDTH={getattr(__import__('common.composer', fromlist=['BEAM_WIDTH']), 'BEAM_WIDTH')}",
                f"SEQUENCE_DEPTH={getattr(__import__('common.composer', fromlist=['SEQUENCE_DEPTH']), 'SEQUENCE_DEPTH')}",
            }),
            deliberate_ruling=deliberate,
            live_owner=live_owner,
        ))
    return records


SENSITIVITY_SUMMARY_SCHEMA = "composer-sensitivity-summary/4"


def _load_sensitivity_summary(inventory: Inventory) -> Mapping:
    """Run and validate the deterministic probe summary against this exact static inventory."""
    # When this file is the CLI's ``__main__``, make the already-loaded module available under the
    # name imported by the sensitivity lab.  This avoids a second static module instance while
    # retaining a lazy import (the sensitivity lab itself imports this audit module).
    sys.modules.setdefault("composer_value_coverage", sys.modules[__name__])
    try:
        from train import composer_sensitivity
        summary = composer_sensitivity.diagnostic_summary(inventory=inventory)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise CoverageError(f"sensitivity diagnostic summary failed closed: {exc}") from exc
    required = {"schema_version", "source_sha", "inventory", "counts", "findings", "proofs",
                "beam_loss_frequency"}
    if not isinstance(summary, Mapping) or not required <= set(summary):
        raise CoverageError("sensitivity diagnostic summary has an incomplete schema")
    if summary["schema_version"] != SENSITIVITY_SUMMARY_SCHEMA:
        raise CoverageError(
            f"sensitivity summary schema drift: {summary['schema_version']!r}")
    if not isinstance(summary["source_sha"], str) or len(summary["source_sha"]) != 40:
        raise CoverageError("sensitivity diagnostic summary lacks a 40-character source SHA")
    joined = summary["inventory"]
    expected_join = {
        "schema_version": inventory.schema_version,
        "source_sha": inventory.source_sha,
        "records": len(inventory.records),
    }
    if joined != expected_join:
        raise CoverageError(f"sensitivity/static inventory join drift: {joined!r} != {expected_join!r}")
    counts, findings, beam = summary["counts"], summary["findings"], summary["beam_loss_frequency"]
    if not isinstance(counts, Mapping) or not isinstance(findings, Mapping) \
            or not isinstance(beam, Mapping):
        raise CoverageError("sensitivity summary count/finding blocks must be mappings")
    for key in ("cases", "controls_passed", "controls_failed", "candidate_sequences",
                "qualifying_search_losses", "local_leaf_disagreements"):
        if not isinstance(counts.get(key), int) or counts[key] < 0:
            raise CoverageError(f"sensitivity summary count {key!r} is missing or invalid")
    for key in ("search_loss", "local_leaf_disagreement"):
        if not isinstance(findings.get(key), list):
            raise CoverageError(f"sensitivity summary findings {key!r} must be a list")
    if counts["qualifying_search_losses"] != len(findings["search_loss"]) \
            or counts["local_leaf_disagreements"] != len(findings["local_leaf_disagreement"]):
        raise CoverageError("sensitivity summary finding counts do not close")
    if not isinstance(beam.get("proven"), bool) or not isinstance(beam.get("reason"), str):
        raise CoverageError("sensitivity beam-loss frequency verdict is malformed")
    if beam["proven"] and not isinstance(beam.get("frequency"), (int, float)):
        raise CoverageError("a proven beam-loss frequency requires a numeric frequency")
    proofs = summary["proofs"]
    if not isinstance(proofs, Mapping) or set(proofs) != {
            "mega_starmie_wally_attach", "identity_independent_attach"}:
        raise CoverageError("sensitivity summary lacks the two required named proofs")
    mega = proofs["mega_starmie_wally_attach"]
    identity = proofs["identity_independent_attach"]
    if not isinstance(mega, Mapping) or mega.get("case") != "mega-starmie-wally-attach" \
            or not isinstance(mega.get("root_one_ply"), Mapping) \
            or not isinstance(mega.get("orders"), Mapping) \
            or not isinstance(mega.get("isolated_attach_after_wally"), Mapping):
        raise CoverageError("Mega Starmie sensitivity proof is malformed")
    if set(mega["root_one_ply"]) != {"wally", "attach_mega_starmie"} \
            or set(mega["orders"]) != {"wally_then_attach", "attach_then_wally"}:
        raise CoverageError("Mega Starmie sensitivity proof lacks exact action/order rows")
    numeric_fields = (
        (mega["root_one_ply"]["wally"], ("rank", "ranked", "chosen_delta")),
        (mega["root_one_ply"]["attach_mega_starmie"], ("rank", "ranked", "chosen_delta")),
        (mega["orders"]["wally_then_attach"], ("after_total_prizes", "total_delta_prizes")),
        (mega["orders"]["attach_then_wally"], ("after_total_prizes", "total_delta_prizes")),
        (mega["isolated_attach_after_wally"],
         ("before_total_prizes", "after_total_prizes", "local_delta_damage",
          "leaf_delta_prizes")),
    )
    if any(not isinstance(row, Mapping)
           or any(not isinstance(row.get(field), (int, float)) or isinstance(row.get(field), bool)
                  for field in fields)
           for row, fields in numeric_fields):
        raise CoverageError("Mega Starmie sensitivity proof has missing/non-numeric measurements")
    if not isinstance(identity, Mapping) or identity.get("case") != "equivalent-identities" \
            or not isinstance(identity.get("original"), Mapping) \
            or not isinstance(identity.get("clone"), Mapping) \
            or identity.get("identity_independent") is not True:
        raise CoverageError("identity-independence sensitivity proof is malformed")
    return summary


def _join_sensitivity_summary(records: tuple[AuditRecord, ...], summary: Mapping
                              ) -> tuple[AuditRecord, ...]:
    """Attach derived probe facts and a semantic digest; no diagnostic number lives in prose."""
    semantic_summary = {key: value for key, value in summary.items() if key != "source_sha"}
    digest = hashlib.sha256(json.dumps(
        semantic_summary, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    counts = summary["counts"]
    beam = summary["beam_loss_frequency"]
    summary_evidence = (
        f"sensitivity_summary_sha256={digest}",
        "sensitivity summary: "
        f"cases={counts['cases']}, controls_passed={counts['controls_passed']}, "
        f"controls_failed={counts['controls_failed']}, "
        f"candidate_sequences={counts['candidate_sequences']}, "
        f"qualifying_search_losses={counts['qualifying_search_losses']}, "
        f"local_leaf_disagreements={counts['local_leaf_disagreements']}",
        "beam-loss frequency " + (
            f"measured: beam_loss_frequency={float(beam['frequency']):.12g}"
            if beam["proven"] else f"unproven: {beam['reason']}"),
    )

    joined_records = list(records)

    def index_of(mechanic_key: str) -> int:
        matches = [index for index, record in enumerate(joined_records)
                   if record.mechanic_key == mechanic_key]
        if len(matches) != 1:
            raise CoverageError(
                f"sensitivity join target {mechanic_key!r} has {len(matches)} records")
        return matches[0]

    search_key = "search-consumer:structural-ordering"
    search_index = index_of(search_key)
    structural = joined_records[search_index]
    structural = dataclasses.replace(
        structural, evidence=_ordered((*structural.evidence, *summary_evidence)))
    for finding in summary["findings"]["search_loss"]:
        if finding.get("case") != "information-ordering" \
                or not finding.get("qualifying_search_loss") \
                or finding.get("search_overlay") != SEARCH_LOSS:
            raise CoverageError(f"unrouted sensitivity SEARCH-LOSS finding: {finding!r}")
        structural = with_search_loss(
            structural,
            "sensitivity probe information-ordering: informative-first line absent while the "
            f"chosen sequence={finding.get('chosen_sequence')}; valuation_gap="
            f"{float(finding.get('valuation_gap', 0.0)):.12g}",
        )
    joined_records[search_index] = structural

    # A disagreement belongs to its exact local owner equation.  Attached-Energy also receives the
    # Attach delta because that WRITABLE row is the ranking/census join used by sensitivity clients.
    for finding in summary["findings"]["local_leaf_disagreement"]:
        owner, case = finding.get("owner"), finding.get("case")
        gap = finding.get("disagreement_prizes")
        if not isinstance(owner, str) or not isinstance(case, str):
            raise CoverageError(f"malformed sensitivity disagreement finding: {finding!r}")
        evidence = (
            f"sensitivity probe {case}: disagreement not prize-commensurate; "
            f"local_unit={finding.get('local_unit')}"
            if gap is None else
            f"sensitivity probe {case}: local_leaf_disagreement={abs(float(gap)):.12g} "
            "prize units"
        )
        targets = [
            record.mechanic_key for record in joined_records
            if record.source_kind == "local-equation" and owner in record.local_owners
        ]
        if owner == "common.deciders.attach.AttachMixin._attach_build_delta":
            targets.append("state-dimension:attached_energy")
        if not targets:
            raise CoverageError(f"no static equation target for sensitivity owner {owner!r}")
        for key in set(targets):
            target_index = index_of(key)
            record = joined_records[target_index]
            joined_records[target_index] = dataclasses.replace(
                record, evidence=_ordered((*record.evidence, evidence)))

    # Exact dynamic claims live in the generated block, not authored prose.  JSON keeps every rank,
    # score, Water-serial, and identity-control field source-derived and digest-covered.
    proofs = summary["proofs"]
    proof_evidence = (
        "sensitivity named proof mega_starmie_wally_attach=" + json.dumps(
            proofs["mega_starmie_wally_attach"], sort_keys=True, separators=(",", ":")),
        "sensitivity named proof identity_independent_attach=" + json.dumps(
            proofs["identity_independent_attach"], sort_keys=True, separators=(",", ":")),
    )
    structural_index = index_of(search_key)
    joined_records[structural_index] = dataclasses.replace(
        joined_records[structural_index],
        evidence=_ordered((*joined_records[structural_index].evidence, proof_evidence[0])))
    energy_index = index_of("state-dimension:attached_energy")
    joined_records[energy_index] = dataclasses.replace(
        joined_records[energy_index],
        evidence=_ordered((*joined_records[energy_index].evidence, *proof_evidence)))
    return tuple(sorted(joined_records, key=_record_key))


def _vocabulary_members(effects: Mapping[int, list[dict]]) -> tuple[str, ...]:
    used_values, used_selectors = _clause_population(effects)
    items = {f"value:{value}" for value in set(snapshots.CLAUSE_WRITES) | set(used_values)}
    items |= {f"parameter:{key}={value}" for key, value in snapshots.CLAUSE_PARAMETERS.items()}
    items |= {
        f"selector:{key}={value}"
        for key, allowed in snapshots.CLAUSE_SELECTORS.items()
        for value in allowed
    }
    items |= {f"used-selector:{key}={value}" for key, value in used_selectors}
    return tuple(sorted(items))


def _check_authored_joins(root: Path, effects: Mapping[int, list[dict]],
                          equations: tuple[EquationCandidate, ...]) -> None:
    kind_keys = {kind for kind, _name in OPTION_KINDS}
    if kind_keys != set(seam.KIND_COVERAGE):
        raise CoverageError(f"OPTION_KINDS drift: {sorted(kind_keys ^ set(seam.KIND_COVERAGE))}")
    zone_keys = {zone.id for zone in snapshots.WRITABLE}
    for name, join in (("ZONE_OWNERS", ZONE_OWNERS), ("ZONE_LOCAL_OWNERS", ZONE_LOCAL_OWNERS)):
        if set(join) != zone_keys:
            raise CoverageError(f"{name} drift: {sorted(set(join) ^ zone_keys)}")
    empty = {key for key, writes in snapshots.CLAUSE_WRITES.items() if not writes}
    if set(EMPTY_CLAUSE_JOIN) != empty:
        raise CoverageError(f"EMPTY_CLAUSE_JOIN drift: {sorted(set(EMPTY_CLAUSE_JOIN) ^ empty)}")

    actual = {
        "equations": _digest(candidate.key for candidate in equations),
        "vocabulary": _digest(_vocabulary_members(effects)),
        "stats": _digest(f"{cls}.{field}" for cls, field in _provider_members()),
    }
    expected = {
        "equations": EQUATION_BASELINE_SHA256,
        "vocabulary": VOCABULARY_BASELINE_SHA256,
        "stats": STAT_BASELINE_SHA256,
    }
    problems = [f"{name} baseline {expected[name]} -> {digest}"
                for name, digest in actual.items() if expected[name] != digest]
    if problems:
        raise CoverageError("; ".join(problems))


def _record_key(record: AuditRecord) -> tuple:
    return (record.mechanic_key, record.source_kind, record.source_symbol_or_site,
            record.classification, record.search_overlay)


def validate_inventory(inventory: Inventory) -> tuple[str, ...]:
    problems = []
    identities = [
        (record.mechanic_key, record.source_kind, record.source_symbol_or_site)
        for record in inventory.records
    ]
    duplicates = [identity for identity, count in collections.Counter(identities).items() if count > 1]
    if duplicates:
        problems.append(f"duplicate record identities: {duplicates[:5]}")
    if inventory.records != tuple(sorted(inventory.records, key=_record_key)):
        problems.append("records are not deterministically sorted")
    if not inventory.records:
        problems.append("empty inventory")
    for candidate in inventory.equation_candidates:
        if candidate.disposition not in {"owner", "consumer", "excluded"}:
            problems.append(f"{candidate.key}: unclassified equation candidate")
        if not candidate.reason.strip():
            problems.append(f"{candidate.key}: empty equation disposition reason")
        if candidate.disposition == "owner" and (not candidate.local_owners
                                                   or not candidate.classification):
            problems.append(f"{candidate.key}: owner lacks local ownership/classification")
        if candidate.disposition != "excluded" and not candidate.classification:
            problems.append(f"{candidate.key}: emitted equation candidate lacks a coverage class")
        if candidate.disposition == "excluded" and (
                candidate.absolute_owners or candidate.local_owners or candidate.classification):
            problems.append(f"{candidate.key}: excluded candidate claims ownership")
    invented = {"state:semantic-counterpart", "state:shared", "state:registered-family",
                "state:composer-consumer", "state:composed-score", "state:continuation"}
    for record in inventory.records:
        fake = invented & set(record.absolute_owners)
        if fake:
            problems.append(f"{record.mechanic_key}: invented owners {sorted(fake)}")
    return tuple(problems)


def build_inventory(root: Path = _ROOT) -> Inventory:
    cards = apply_census.load_cards()
    effects = apply_census.load_effects()
    sites = source_sites()
    exposure = _exposure_index(cards)
    equations = equation_candidates(root)
    provider_fields = _provider_ledger(cards, root)
    _check_authored_joins(root, effects, equations)

    records: list[AuditRecord] = []
    site_records = tuple(_site_records(sites, exposure))
    records.extend(site_records)
    records.extend(_attack_and_passive_records(cards, exposure))
    records.extend(_option_records())

    # Preserve one occurrence per shipped transition site.  ``Exposure.for_cards`` deduplicates the
    # card population independently; factor 2 must not silently collapse repeated mechanic sites.
    zone_card_occurrences: dict[str, list[int]] = collections.defaultdict(list)
    for site in sites:
        for zone in _site_writes(site):
            zone_card_occurrences[zone].append(site.card_id)
    used_values, _used_selectors = _clause_population(effects)
    records.extend(_zone_records(
        {zone: tuple(card_ids) for zone, card_ids in sorted(zone_card_occurrences.items())},
        exposure,
    ))
    records.extend(_clause_records(effects, exposure))
    records.extend(_family_records())
    stat_records = tuple(_stat_records(provider_fields, exposure, equations, root))
    records.extend(stat_records)
    equation_exposures = _equation_exposures(
        equations, sites, cards, provider_fields, stat_records, exposure, root)
    records.extend(_equation_records(equations, equation_exposures))
    records.extend(_search_records(root))

    populations = (
        ("all_cards", len(cards)),
        ("apply_sites", len(sites)),
        ("terminal_attacks", sum(len(card.get("attacks") or []) for card in cards.values())),
        ("passive_abilities", sum(
            card.get("category") == "pokemon"
            and apply_census._ability_mode(ability.get("text") or "") == "passive"
            for card in cards.values() for ability in (card.get("abilities") or []))),
        ("option_kinds", len(seam.KIND_COVERAGE)),
        ("writable_dimensions", len(snapshots.WRITABLE)),
        ("clause_values", len(set(snapshots.CLAUSE_WRITES) | set(used_values))),
        ("clause_parameters", len(snapshots.CLAUSE_PARAMETERS)),
        ("clause_selector_values", sum(len(values) for values in snapshots.CLAUSE_SELECTORS.values())),
        ("state_families", len(state_value.REGISTRY)),
        ("terminal_families", len(state_value.TERMINAL_REGISTRY)),
        ("value_consequences", sum(len(family.consequences)
                                   for family in state_value.REGISTRY + state_value.TERMINAL_REGISTRY)),
        ("provider_declared_members", len(provider_fields)),
        ("provider_observed_nondefault", sum(field.observed_nondefault
                                               for field in provider_fields)),
        ("equation_candidates", len(equations)),
        ("composer_search_consumers", len(COMPOSER_SEARCH_CONSUMERS)),
    )
    inventory = Inventory(
        schema_version=SCHEMA_VERSION,
        source_sha=origin_main_sha(root),
        records=tuple(sorted(records, key=_record_key)),
        populations=tuple(sorted(populations)),
        equation_candidates=equations,
        provider_fields=provider_fields,
        registry_identity=state_value.registry_identity(),
    )
    problems = validate_inventory(inventory)
    if problems:
        raise CoverageError("; ".join(problems))
    summary = _load_sensitivity_summary(inventory)
    inventory = dataclasses.replace(
        inventory, records=_join_sensitivity_summary(inventory.records, summary))
    problems = validate_inventory(inventory)
    if problems:
        raise CoverageError("; ".join(problems))
    return inventory


def records_by_written_dimension(inventory: Inventory | None = None
                                 ) -> Mapping[str, tuple[AuditRecord, ...]]:
    return (inventory or build_inventory()).records_by_written_dimension()


def owner_summary(dimension: str, inventory: Inventory | None = None) -> DimensionOwnership:
    return (inventory or build_inventory()).owner_summary(dimension)


def _md(value) -> str:
    if isinstance(value, (tuple, list)):
        value = ", ".join(str(item) for item in value)
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ") or "—"


def _table(headers: tuple[str, ...], rows: Iterable[Iterable[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(_md(cell) for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def _measured_factor(record: AuditRecord, name: str) -> float | None:
    pattern = re.compile(rf"(?:^|\b){re.escape(name)}=(-?\d+(?:\.\d+)?)\b")
    values = []
    for evidence in record.evidence:
        match = pattern.search(evidence)
        if match:
            values.append(float(match.group(1)))
    return max(values) if values else None


_RANKABLE_SOURCE_KINDS = frozenset({
    "option-kind",
    "writable-state",
    "effect-clause-value",
    "effect-clause-parameter",
    "effect-clause-selector",
    "card-stat",
    "attack-stat",
    "local-equation",
    "value-consumer",
    "composer-search-consumer",
    "state-value-family",
    "terminal-family",
})

# The issue's routing locks #494 as the value-contract prerequisite for the later Energy and search
# tracks.  This last factor is therefore an authored dependency order, not a fabricated measurement.
_DEPENDENCY_ORDER = MappingProxyType({"#494": 3, "#495": 2, "#496": 1, "#492 backlog": 0})


def _ranked_findings(inventory: Inventory) -> list[tuple]:
    """One row per mechanic, lexicographic on the seven locked factors.

    Static class labels are not measurements: LOSSY does not manufacture a disagreement magnitude,
    and SEARCH-LOSS does not manufacture a beam-loss frequency.  Those factors stay visibly
    ``unmeasured`` until a probe emits the named numeric evidence.
    """
    findings = []
    for record in inventory.records:
        # Per-card/attack/passive rows prove source coverage and feed the exposure of their aggregate
        # mechanism.  Emitting them again here would turn one remediation into thousands of rows.
        if record.source_kind not in _RANKABLE_SOURCE_KINDS:
            continue
        if (record.classification in {SHARED_EXACT, LEAF_ONLY, DELIBERATE_ZERO}
                and record.search_overlay != SEARCH_LOSS):
            continue
        terminal = int(any(owner.startswith("terminal:") for owner in record.absolute_owners)
                       or _measured_factor(record, "terminal_win_prize_impact") == 1.0)
        disagreement = _measured_factor(record, "local_leaf_disagreement")
        beam = _measured_factor(record, "beam_loss_frequency")
        dependency = _measured_factor(record, "implementation_dependency")
        if dependency is None:
            dependency = _DEPENDENCY_ORDER.get(record.live_owner)
        exposure_unmeasured = any(
            item.startswith("exposure unmeasured:") for item in record.evidence)
        population_unmeasured = any(
            item.startswith("card/deck/corpus exposure unmeasured:")
            for item in record.evidence)
        factors = (
            terminal,
            record.exposure.mechanic_sites if not exposure_unmeasured else None,
            record.exposure.decks if not (exposure_unmeasured or population_unmeasured) else None,
            record.exposure.corpus_frames if not (exposure_unmeasured or population_unmeasured) else None,
            disagreement,
            beam,
            dependency,
        )
        numeric = tuple(float("-inf") if value is None else float(value) for value in factors)
        display = tuple("unmeasured" if value is None else value for value in factors)
        tie_exposure = (
            record.exposure.cards,
            record.exposure.mechanic_sites,
            record.exposure.decks,
            record.exposure.deck_copies,
            record.exposure.meta_builds,
            record.exposure.meta_copies,
            record.exposure.corpus_frames,
        )
        verdict = record.classification + (
            f" + {record.search_overlay}" if record.search_overlay else "")
        findings.append((numeric, tie_exposure, record.mechanic_key,
                         display, verdict, record.live_owner))
    findings.sort(key=lambda row: (
        tuple(-value for value in row[0]),
        tuple(-value for value in row[1]),
        row[2],
    ))
    return [
        (display, verdict, owner, key)
        for _numeric, _exposure, key, display, verdict, owner in findings
    ]


def render_generated(inventory: Inventory) -> str:
    control = legacy_positive_control()
    counts = collections.Counter(record.classification for record in inventory.records)
    overlay_counts = collections.Counter(record.search_overlay for record in inventory.records)
    L = []
    add = L.append
    add("## 1. Scope, SHA, commands, populations, and controls")
    add("")
    add(f"- Schema: `{inventory.schema_version}`")
    add(f"- Reviewed audit-base SHA: `{inventory.source_sha}`")
    add(f"- State-value registry: `{inventory.registry_identity}`")
    add("- Command: `python tools/composer_value_coverage.py --out "
        "docs/plans/composer-valuation-coverage.md`")
    add(f"- Legacy positive control: **{'PASS' if control.matched else 'FAIL'}**, "
        f"{control.pool_cards} cards / {control.sites} sites / `{control.census_digest}`")
    add("")
    add(_table(("population", "count"), inventory.populations))
    add("")
    add(_table(("classification", "records"),
               ((name, counts[name]) for name in CLASSIFICATIONS if name != SEARCH_LOSS)))
    add("")
    add(f"- `{SEARCH_LOSS}` overlays proved by controlled probes: "
        f"{overlay_counts[SEARCH_LOSS]}")
    add("")
    add("### Provider declaration ledger")
    add("")
    add("Primary mechanic rows below include only shipped non-default values. Default-only "
        "declarations remain here so provider schema growth still fails the authored baseline.")
    add("")
    add(_table(("provider member", "observed non-default", "cards", "parsed/override sites",
                "runtime callers", "declaration-only reason"),
               ((f"{field.class_name}.{field.field_name}", field.observed_nondefault,
                 len(field.observed_cards), f"{field.observed_sites}/{field.override_sites}",
                 len(field.runtime_callers), field.declaration_only_reason)
                for field in inventory.provider_fields)))
    add("")
    add("## 2. Transition coverage")
    add("")
    site_fates = collections.Counter(
        record.transition_fate for record in inventory.records
        if record.source_kind == "card-effect-site")
    add("All shipped apply sites (completeness, never exposure-filtered):")
    add("")
    add(_table(("fate", "sites"), sorted(site_fates.items())))
    add("")
    option_rows = [record for record in inventory.records if record.source_kind == "option-kind"]
    add(_table(("mechanic", "fate", "writes", "verdict"),
               ((r.mechanic_key, r.transition_fate, r.written_dimensions, r.classification)
                for r in option_rows)))
    add("")
    add("## 3. Writable state to absolute/terminal ownership")
    add("")
    zone_rows = [record for record in inventory.records if record.source_kind == "writable-state"]
    add(_table(("dimension", "absolute/terminal owners", "local owners", "verdict"),
               ((r.written_dimensions, r.absolute_owners, r.local_owners, r.classification)
                for r in zone_rows)))
    add("")
    add("## 4. Local equation to leaf parity")
    add("")
    add(_table(("candidate", "disposition", "absolute/terminal owners", "local owners",
                "base class", "callers", "reason"),
               ((c.key, c.disposition, c.absolute_owners, c.local_owners, c.classification or "n/a",
                 len(c.runtime_callers), c.reason)
                for c in inventory.equation_candidates)))
    add("")
    add("## 5. Search survival")
    add("")
    search_rows = [record for record in inventory.records
                   if record.source_kind == "composer-search-consumer"]
    add(_table(("surface", "path", "base valuation class", "search overlay", "owners",
                "evidence"),
               ((r.mechanic_key, r.search_path, r.classification, r.search_overlay or "none",
                 r.absolute_owners, r.evidence) for r in search_rows)))
    add("")
    add("Static census names loss surfaces; only the joined deterministic probe summary may assign "
        "`SEARCH-LOSS`. Its semantic SHA-256 and derived counts are evidence on the structural-"
        "ordering row above. Without a representative denominator, factor 6 remains `unmeasured`.")
    add("")
    add("## 6. Complete mechanism matrix")
    add("")
    add(_table(("mechanic", "source kind", "source symbol/site", "transition", "writes",
                "absolute", "local", "callers", "leaf", "search", "base class",
                "search overlay", "evidence", "ruling", "exposure", "live owner"),
               ((r.mechanic_key, r.source_kind, r.source_symbol_or_site, r.transition_fate,
                  r.written_dimensions, r.absolute_owners, r.local_owners, r.runtime_callers,
                  r.leaf_path, r.search_path, r.classification, r.search_overlay or "none",
                  r.evidence, r.deliberate_ruling,
                 (f"cards={r.exposure.cards}, sites={r.exposure.mechanic_sites}, "
                  f"decks={r.exposure.decks}, copies={r.exposure.deck_copies}, "
                  f"meta={r.exposure.meta_copies}, corpus={r.exposure.corpus_frames}"),
                 r.live_owner) for r in inventory.records)))
    add("")
    add("## 7. Deliberate zeros and unknown/refused")
    add("")
    selected = [record for record in inventory.records
                if record.classification in {DELIBERATE_ZERO, UNKNOWN_REFUSED}]
    grouped = collections.defaultdict(list)
    for record in selected:
        grouped[(record.classification, record.source_kind, record.live_owner)].append(record)
    add(_table(("verdict", "source kind", "records", "ruling/evidence sample", "owner"),
               ((classification, source_kind, len(records),
                 records[0].deliberate_ruling or records[0].evidence, owner)
                for (classification, source_kind, owner), records in sorted(grouped.items()))))
    add("")
    add("## 8. Ranked findings")
    add("")
    add("One row per aggregate semantic mechanic. Per-card apply/attack/passive rows feed aggregate "
        "exposure and are not repeated as remediation rows. Factors are `(terminal impact, shipped "
        "sites, decks, corpus frames, local/leaf disagreement, beam-loss frequency, implementation "
        "dependency)`. `unmeasured` is not replaced by a class-derived proxy. Dependency order is "
        "the accepted route prerequisite `#494 > #495 > #496 > #492 backlog`.")
    add("")
    add(_table(("lexicographic factors", "base class + overlay", "route", "mechanic"),
               _ranked_findings(inventory)))
    add("")
    add("## 9. Sufficiency verdict")
    add("")
    proof_rows = []
    proof_prefix = "sensitivity named proof "
    for record in inventory.records:
        for evidence in record.evidence:
            if evidence.startswith(proof_prefix):
                name, payload = evidence.removeprefix(proof_prefix).split("=", 1)
                proof_rows.append((name, payload))
    proof_rows = sorted(set(proof_rows))
    if proof_rows:
        add("Source-derived controlled proofs (the sensitivity semantic digest covers these exact "
            "ranks/scores/deltas):")
        add("")
        add(_table(("proof", "deterministic result"), proof_rows))
        add("")
    add("Sufficient for a source-complete static transition/value/search census and the controlled "
        "subset recorded by the joined sensitivity-summary digest. Insufficient to establish "
        "repository-wide valuation sufficiency, disagreement frequency, or general beam-loss "
        "frequency.")
    add("")
    add("## 10. Routing")
    add("")
    add("Value contract/ownership → #494; Energy/funding → #495; search/beam → #496; "
        "remaining mechanics → #492 backlog.")
    return "\n".join(L)


def _normalise_lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def splice_generated(existing: str | None, generated: str) -> str:
    generated = _normalise_lf(generated)
    if generated.endswith("\n"):
        raise CoverageError("generated renderer must return content without a trailing newline")
    block = f"{BEGIN}\n\n{generated}\n{END}"
    if existing is None:
        return ("# Composer valuation coverage\n\n"
                "Issue #493 static inventory. Authored verdict may be added outside the generated block.\n\n"
                f"{block}\n")
    existing = _normalise_lf(existing)
    if existing.count(BEGIN) != 1 or existing.count(END) != 1:
        raise CoverageError("report must contain exactly one ordered generated-marker pair")
    start, finish = existing.index(BEGIN), existing.index(END)
    if finish < start:
        raise CoverageError("generated report markers are reversed")
    return existing[:start] + block + existing[finish + len(END):]


def write_report(path: Path, inventory: Inventory) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    text = splice_generated(existing, render_generated(inventory))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_normalise_lf(text).encode("utf-8"))


def check_report(path: Path, inventory: Inventory) -> bool:
    if not path.exists():
        return False
    try:
        existing = _normalise_lf(path.read_bytes().decode("utf-8"))
        expected = splice_generated(existing, render_generated(inventory))
    except (CoverageError, UnicodeDecodeError):
        return False
    # Compare exact bytes after the one allowed normalisation (CRLF/CR -> LF).  In particular, do
    # not hide deleted rows or changed generated whitespace with ``rstrip``.
    return existing.encode("utf-8") == expected.encode("utf-8")


def write_json(path: Path, inventory: Inventory) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(inventory.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_bytes(payload.encode("utf-8"))


def deck_ownership_manifest(agent: str, inventory: Inventory) -> dict:
    """Deck-scoped evidence over the generic audit; policy remains card/deck anonymous."""
    decks = apply_census.load_our_decks()
    if agent not in decks:
        raise CoverageError(f"unknown shipped agent {agent!r}; expected one of {sorted(decks)}")
    card_ids = set(decks[agent])
    cards = apply_census.load_cards()
    sites = source_sites(card_ids)
    site_records = _site_records(sites, _exposure_index(cards))
    rows = []
    for site, record in zip(sites, site_records):
        status = ("REFUSED" if site.fate == seam.REFUSED else
                  "TERMINAL" if site.fate == seam.TERMINAL else
                  "STRUCTURAL" if not site.has_effect else "MODELED")
        persistent = ("SHARED-EXACT" if record.absolute_owners else
                      "NOT-PERSISTENT" if status in {"STRUCTURAL", "TERMINAL"} else
                      "DELIBERATE-ZERO" if record.classification == DELIBERATE_ZERO else
                      "LEAF-ONLY" if record.classification == LEAF_ONLY else record.classification)
        rows.append({
            "card_id": site.card_id, "card_name": site.name,
            "effect_provider": site.family or site.kind_name.lower(),
            "parsed_clauses": json.loads(site.clauses_json),
            "transition_owner": "common.board_delta/common.board_choice/common.board_expectation",
            "transition_status": status,
            "persistent_owners": list(record.absolute_owners),
            "persistent_classification": persistent,
            "local_consumers": list(record.local_owners),
            "calls_canonical_api": bool(record.absolute_owners) or any(
                owner in {"common.deciders.attach.AttachMixin._tool_attach_value",
                          "common.board_choice.rank_retreat"}
                for owner in record.local_owners),
            "search_owner": "Issue #496",
            "evidence": list(record.evidence),
            "explained": bool(record.evidence),
        })
    for card_id in sorted(card_ids):
        card = cards[card_id]
        for ordinal, attack in enumerate(card.get("attacks") or ()):
            rows.append({
                "card_id": card_id, "card_name": card.get("name", "?"),
                "effect_provider": f"attack.{ordinal}", "parsed_clauses": attack,
                "transition_owner": "terminal attack resolution", "transition_status": "TERMINAL",
                "persistent_owners": ["state:readiness"],
                "persistent_classification": "LEAF-ONLY",
                "local_consumers": ["terminal:attack_ev"], "calls_canonical_api": True,
                "search_owner": "Issue #496", "evidence": ["combat profile plus terminal attack_ev"],
                "explained": True,
            })
        if not any(row["card_id"] == card_id for row in rows):
            rows.append({
                "card_id": card_id, "card_name": card.get("name", "?"),
                "effect_provider": card.get("category", "card"), "parsed_clauses": [],
                "transition_owner": "structural card transport", "transition_status": "STRUCTURAL",
                "persistent_owners": [], "persistent_classification": "NOT-PERSISTENT",
                "local_consumers": [], "calls_canonical_api": True, "search_owner": "Issue #496",
                "evidence": ["deck card covered; no independent persistent mechanic"],
                "explained": True,
            })
    forbidden = {LOCAL_ONLY, LOSSY_REEXPRESSION, UNVALUED_MODELLED, UNKNOWN_REFUSED}
    unexplained = [row for row in rows
                   if row["persistent_classification"] in forbidden and not row["explained"]]
    return {"schema_version": "composer-deck-ownership/1", "audit_schema": inventory.schema_version,
            "agent": agent, "source_sha": inventory.source_sha,
            "registry_identity": inventory.registry_identity,
            "cards": [{"card_id": card_id, "name": cards[card_id].get("name", "?"),
                       "copies": decks[agent][card_id]} for card_id in sorted(card_ids)],
            "rows": rows, "unexplained_forbidden": unexplained}


def write_manifest(path: Path, agent: str, inventory: Inventory) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(deck_ownership_manifest(agent, inventory), ensure_ascii=False,
                               indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--out", type=Path)
    group.add_argument("--check", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--agent")
    args = parser.parse_args(argv)
    try:
        inventory = build_inventory()
        if args.agent and args.check:
            raise CoverageError("--agent cannot be combined with --check")
        if args.agent and args.out:
            write_manifest(args.out, args.agent, inventory)
            print(f"wrote {args.out}")
        elif args.check:
            if not check_report(args.check, inventory):
                print(f"STALE: {args.check}; rerun composer_value_coverage.py --out {args.check}",
                      file=sys.stderr)
                return 1
            print(f"fresh: {args.check}")
        elif args.out or not args.json:
            target = args.out or DEFAULT_OUT
            write_report(target, inventory)
            print(f"wrote {target}")
        if args.json:
            write_json(args.json, inventory)
            print(f"wrote {args.json}")
    except CoverageError as error:
        print(f"COVERAGE ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
