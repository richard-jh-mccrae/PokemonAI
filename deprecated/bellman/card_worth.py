"""Frozen tag-era card Worth used only by the deprecated Bellman teacher."""
PRIMARY_ATTACKER_TIER = 30.0
BACKUP_ATTACKER_TIER = 20.0
ATTACKER_LINE_BASE_TIER = 25.0
PREEVOLUTION_TIER = 25.0
ROLE_TIER = {
    "primary_attacker": PRIMARY_ATTACKER_TIER, "backup_attacker": BACKUP_ATTACKER_TIER,
    "preevolution": PREEVOLUTION_TIER, "engine": 12.0, "support_pokemon": 12.0,
    "disruption_target": 12.0, "accel_source": 12.0, "counter_mover": 12.0,
    "item_locker": 12.0, "search_engine": 12.0, "retreat_assist": 12.0,
    "healer": 12.0, "stall_pokemon": 12.0,
}
ROLE_ALIASES = {"fragile_preevo": "preevolution", "threat": "primary_attacker",
                "draw_engine": "engine", "energy_accel": "accel_source"}
ENERGY_TIER = 8.0
ACE_SPEC_TIER = 25.0
KNOWN_CARD_FLOOR = 5.0

FUNCTION_TIER = {
    "energy_accel": 12.0, "search": 10.0, "dig": 10.0, "bench_fill": 10.0,
    "item_lock": 10.0, "tutor_energy": 10.0, "tutor_pokemon": 10.0,
    "tutor_mega": 10.0, "tutor_trainer": 10.0, "supporter_tutor": 10.0,
    "draw": 8.0, "shuffle_hand": 8.0, "energy_denial": 6.0, "switch": 5.0,
    "stall": 5.0,
}
TAG_TIER = {"discard_eot": 30.0, "clutch_heal": 20.0, "gust": 10.0, "recycle": 10.0}
_FUNCTION_ROLES = (
    ("accel_source", frozenset({"discard_eot", "provides_evo:3"})),
    ("tutor", frozenset({"bench_fill", "rush_evolve", "tutor_energy", "tutor_mega",
                          "tutor_pokemon", "tutor_trainer"})),
    ("disruption", frozenset({"energy_denial", "hand_disruption", "item_lock"})),
    ("gust", frozenset({"gust"})),
    ("recovery", frozenset({"clutch_heal", "heal", "recycle"})),
)


def function_role(tags):
    tags = frozenset(str(tag) for tag in tags)
    return next((role for role, markers in _FUNCTION_ROLES if tags & markers), None)


def role_value(roles, is_ace_spec=False, is_typed_basic_energy=False, tags=(),
               is_known_card=False, worth_override=0.0):
    return max(
        max((ROLE_TIER.get(ROLE_ALIASES.get(role, role), 0.0) for role in roles), default=0.0),
        max((TAG_TIER.get(tag, 0.0) for tag in tags), default=0.0),
        max((FUNCTION_TIER.get(tag, 0.0) for tag in tags), default=0.0),
        ACE_SPEC_TIER if is_ace_spec else 0.0,
        ENERGY_TIER if is_typed_basic_energy else 0.0,
        KNOWN_CARD_FLOOR if is_known_card else 0.0,
        max(0.0, float(worth_override or 0.0)),
    )
