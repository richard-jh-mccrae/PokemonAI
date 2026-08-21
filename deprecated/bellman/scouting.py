"""Frozen Brief-role resolver retained only for the deprecated Bellman teacher."""
from __future__ import annotations

from dataclasses import dataclass, field

from common.observation import ObservationState
from common.scouting.briefs import load_briefs
from common.scouting.pokemon_roles import general_pokemon_roles
from common.scouting.scorer import posterior


_LEGACY_PROPERTIES = {
    "alakazam": {
        "opp_hand_size_attacker": True, "opp_single_prize": True, "opp_tempo": "midrange"},
    "archaludon_ex_cinderace": {
        "opp_is_heal_wall": True, "opp_accel_dependent": True, "opp_tempo": "slow"},
    "cinderace_mega_starmie_ex": {
        "opp_tempo": "fast", "opp_pierces_active_effects": True},
    "cornerstone_mask_ogerpon_ex_crustle_mega_kangaskhan_ex": {
        "opp_tempo": "slow", "opp_ex_damage_immune": True,
        "opp_effect_immune_bodies": True, "opp_is_heal_wall": True,
        "opp_pierces_active_effects": True},
    "crustle": {
        "opp_ex_damage_immune": True, "opp_caps_big_hits": True,
        "opp_is_heal_wall": True, "opp_pierces_active_effects": True,
        "opp_single_prize": True},
    "cynthia_s_garchomp_ex_cynthia_s_roserade_cynthia_s_spiritomb": {
        "opp_tempo": "midrange", "opp_donk_vulnerable": True,
        "opp_effect_immune_bodies": True, "opp_comeback_disruptor": True},
    "dipplin_thwackey_volbeat": {
        "opp_tempo": "fast", "opp_donk_vulnerable": True,
        "opp_comeback_disruptor": True},
    "dragapult_ex": {
        "opp_tempo": "midrange", "opp_spreads_bench": True,
        "opp_item_locks": True, "opp_comeback_disruptor": True},
    "froslass_marnie_s_grimmsnarl_ex": {
        "opp_tempo": "midrange", "opp_spreads_bench": True,
        "opp_comeback_disruptor": True},
    "hariyama_mega_lucario_ex_solrock": {"opp_tempo": "midrange"},
    "hop_s_trevenant_hop_s_snorlax": {
        "opp_single_prize": True, "opp_tempo": "midrange",
        "opp_special_energy_fragile": True, "opp_effect_immune_bodies": True},
    "hydrapple_ex_meganium_teal_mask_ogerpon_ex": {
        "opp_tempo": "midrange", "opp_comeback_disruptor": True},
    "kyogre_mega_abomasnow_ex": {
        "opp_tempo": "slow", "opp_no_pivot": True,
        "opp_deckout_vulnerable": True},
    "latias_ex_mega_kangaskhan_ex_slowking": {
        "opp_tempo": "midrange", "opp_is_engine_dependent": True},
    "mega_froslass_ex_mega_lopunny_ex": {
        "opp_tempo": "fast", "opp_is_heal_wall": True,
        "opp_pierces_active_effects": True, "opp_effect_immune_bodies": True},
    "n_s_zekrom_n_s_reshiram_n_s_zoroark_ex": {"opp_is_engine_dependent": True},
}


@dataclass
class LegacyRead:
    candidates: list[tuple[str, float]] = field(default_factory=list)
    unknown_mass: float = 1.0


class LegacyScout:
    def __init__(self, artifact):
        self.artifact = artifact
        self._evidence = set()

    def observe(self, state):
        if not isinstance(state, ObservationState):
            return LegacyRead()
        for body in state.them.bodies:
            self._evidence.add(body.card.card_id)
            self._evidence.update(card.card_id for card in (
                body.energy_cards + body.tools + body.pre_evolution))
        self._evidence.update(card.card_id for card in state.them.discard)
        candidates, unknown = posterior(
            self.artifact.priors, self.artifact.card_inclusion,
            self.artifact.background, self._evidence)
        return LegacyRead(candidates, unknown)


def load_legacy_briefs():
    briefs = load_briefs(strict=True)
    for brief in briefs:
        brief.opponent_properties = dict(_LEGACY_PROPERTIES.get(brief.slug, {}))
    return briefs


def match_legacy_brief(briefs, read):
    if not read.candidates:
        return None
    key = read.candidates[0][0].replace("’", "'")
    return next((brief for brief in briefs
                 if any(key == cover.replace("’", "'") for cover in brief.covers)), None)


_TARGET_ROLE_ORDER = (
    "primary_attacker", "backup_attacker", "accel_source", "counter_mover",
    "draw_engine", "search_engine", "healer", "stall_pokemon", "support_pokemon")


def evolution_line(card_ids, ids_for_name, stat_for_id, forward_ids) -> frozenset[int]:
    line = {int(card_id) for card_id in card_ids}
    if stat_for_id is None:
        return frozenset(line)
    if forward_ids is not None:
        for card_id in tuple(line):
            line.update(int(descendant) for descendant in forward_ids(card_id) or ())
    pending = list(line)
    while pending:
        stat = stat_for_id(pending.pop())
        parent = getattr(stat, "evolvesFrom", None) if stat is not None else None
        for ancestor in ids_for_name(parent) if parent else ():
            if int(ancestor) not in line:
                line.add(int(ancestor))
                pending.append(int(ancestor))
    return frozenset(line)


def resolve_brief_cards(brief, ids_for_name, *, stat_for_id=None, forward_ids=None):
    threat_ids = set()
    role_claims: dict[int, set[str]] = {}
    primary_ids = set()
    for entry in brief.pokemon or ():
        roles = tuple(entry.get("roles") or ())
        ids = {int(card_id) for card_id in ids_for_name(entry.get("card", "")) or ()}
        if stat_for_id is not None:
            generic = general_pokemon_roles(ids, _StatLookup(stat_for_id, forward_ids))
            for card_id, card_roles in generic.items():
                role_claims.setdefault(card_id, set()).update(card_roles)
        if {"primary_attacker", "backup_attacker"}.intersection(roles):
            threat_ids.update(ids)
        for card_id in ids:
            role_claims.setdefault(card_id, set()).update(roles)
        if "primary_attacker" in roles:
            primary_ids.update(ids)
    primary_line = evolution_line(primary_ids, ids_for_name, stat_for_id, forward_ids)
    threat_ids.update(primary_line)
    for card_id in primary_line:
        role_claims.setdefault(card_id, set()).add("primary_attacker")
    targets = {card_id: next((role for role in _TARGET_ROLE_ORDER if role in roles), None)
               for card_id, roles in role_claims.items()}
    return frozenset(threat_ids), {card_id: role for card_id, role in targets.items() if role}


class _StatLookup:
    def __init__(self, get, forward_card_ids=None):
        self.get = get
        self.forward_card_ids = forward_card_ids or (lambda _card_id: ())


__all__ = ("evolution_line", "resolve_brief_cards")
