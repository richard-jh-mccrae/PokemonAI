"""Slowking declarations for the shared Bellman runtime.

Attrition toolbox (Ross Cawthon, NAIC 2026 4th). Slowking's Seek Inspiration ({P}{C}) discards
the top card of OUR deck and, when it is a non-Rule-Box Pokémon, uses one of its attacks — so
Kyurem (Trifrost 110x3), Probopass (Obliterating Nose 260) and Zeraora (Thunder Raid 210 bench
snipe) are ammunition that never attacks from the board: Academy at Night (hand -> deck top) and
Ciphermaniac's Codebreaking (search 2 -> deck top, chosen order) load the shot, and Boomerang
Energy re-attaches itself after a copied energy-discarding attack. Mega Kangaskhan ex opens
Active for Run Errand draws and Latias ex's Skyliner retreats it out free; Lillie's Clefairy ex
flips Dragon Weakness to {P}.

Probopass stands in for Cawthon's Metagross CRI 61 (the always-300 Metallic Hammer): the pool has
no CRI set, and 260 with the Boomerang refund is its best legal ceiling (developer-approved swap).
"""
from common.strategy import (
    ActivationCondition, DesiredFact, PrizePlan, Roles, Strategy, StrategyHint,
)

# Card ids — slowking/deck.csv.
SLOWPOKE, SLOWKING = 162, 163
KYUREM, PROBOPASS, ZERAORA = 144, 1047, 377
MEGA_KANGASKHAN_EX, LATIAS_EX, LILLIES_CLEFAIRY_EX = 756, 184, 272
MEOWTH_EX, FEZANDIPITI_EX = 1071, 140
PSYCHIC_ENERGY, TELEPATH_PSYCHIC_ENERGY, BOOMERANG_ENERGY = 5, 19, 9
LILLIES_DETERMINATION, CIPHERMANIACS_CODEBREAKING, ACADEMY_AT_NIGHT = 1227, 1188, 1248
POKE_PAD, ULTRA_BALL, WONDROUS_PATCH, NIGHT_STRETCHER = 1152, 1121, 1146, 1097
SECRET_BOX, SWITCH, BRAVE_BANGLE, LUCKY_HELMET = 1092, 1123, 1175, 1156

SEEK_INSPIRATION = "slowking.seek_inspiration"
SLOWPOKE_BODY = f"own.body.card:{SLOWPOKE}:readiest"
SLOWKING_BODY = f"own.body.card:{SLOWKING}:readiest"


def _hint(identifier, kind, recipient, *, conditions=(), targets=(), deadline="this_turn",
          confidence="high", bundle_id=None, waypoint=0):
    return StrategyHint(
        f"slowking.{identifier}", "deck", tuple(conditions),
        (DesiredFact(kind, recipient, target_card_ids=tuple(targets)),),
        recipient, deadline, confidence, "slowking.strategy",
        bundle_id=bundle_id, waypoint=waypoint,
    )


ROLES = Roles({
    SLOWPOKE: ["primary_attacker"],
    SLOWKING: ["primary_attacker"],
    # Ammunition: their attacks fire THROUGH Seek Inspiration, never from the board (Probopass has
    # no Nosepass here and can never even be played). The attacker role keeps their held Worth above
    # discard-fodder — losing the last copy loses the attack it carries.
    KYUREM: ["backup_attacker"],
    PROBOPASS: ["backup_attacker"],
    ZERAORA: ["backup_attacker"],
    MEGA_KANGASKHAN_EX: ["draw_engine"],
    LATIAS_EX: ["backup_attacker", "retreat_assist"],
    LILLIES_CLEFAIRY_EX: ["backup_attacker"],
    MEOWTH_EX: ["search_engine"],
    FEZANDIPITI_EX: ["backup_attacker", "draw_engine"],
}, ready={SLOWKING: 2})


STRATEGY = Strategy(
    name="slowking",
    roles=ROLES,
    # The COMPLETE pregame ACTIVE ranking, best first (ADR-0079). Run Errand only draws from the
    # Active Spot, so Mega Kangaskhan ex opens; single-prize bodies before the two-prize techs.
    starter_priority=(MEGA_KANGASKHAN_EX, SLOWPOKE, KYUREM, ZERAORA, LATIAS_EX,
                      FEZANDIPITI_EX, MEOWTH_EX, LILLIES_CLEFAIRY_EX),
    partners={SLOWKING: (ACADEMY_AT_NIGHT,)},
    # Boomerang funds every copied discard-all attack; Academy at Night is the only guaranteed
    # stack. Neither carries a role or a paying tag, so both price as shed fodder without this.
    worth_overrides={BOOMERANG_ENERGY: 12.0, ACADEMY_AT_NIGHT: 12.0},
    prize_plan=PrizePlan(routes=(
        # Attrition: six single-prize bodies is the whole race.
        (SLOWKING, SLOWKING, SLOWKING, SLOWPOKE, SLOWPOKE, SLOWPOKE),
        # The wall fell: a lost Mega Kangaskhan (3) leaves three Slowkings to give.
        (MEGA_KANGASKHAN_EX, SLOWKING, SLOWKING, SLOWKING),
    )),
    params={
        "preferred_start": "first",  # no turn-1 attack exists; going first fires Trifrost first
        "use_general_card_strategies": True,
    },
    strategies=(
        # --- The Seek Inspiration line: charge a benched Slowpoke, evolve, keep firing. --------
        _hint("fund_the_benched_slowpoke", "fund_attack", SLOWPOKE_BODY,
              conditions=(
                  ActivationCondition(f"own.card.{SLOWPOKE}.in_play", "eq", True),
                  ActivationCondition(f"own.card.{SLOWPOKE}.energy_count", "lt", 2),
              ), bundle_id=SEEK_INSPIRATION, waypoint=0),
        _hint("evolve_slowpoke_to_slowking", "evolve", SLOWPOKE_BODY,
              conditions=(ActivationCondition(f"own.card.{SLOWPOKE}.in_play", "eq", True),),
              targets=(SLOWKING,), deadline="immediate",
              bundle_id=SEEK_INSPIRATION, waypoint=1),
        _hint("fund_active_seek_inspiration", "fund_attack", "own.active",
              conditions=(
                  ActivationCondition("own.active.card_id", "eq", SLOWKING),
                  ActivationCondition("own.active.attack_ready", "eq", False),
              ), deadline="immediate", bundle_id=SEEK_INSPIRATION, waypoint=2),
        # Wondrous Patch is bench-only, so the NEXT Slowking charges behind the active one; a lone
        # charged Slowking up front with nothing behind it is this deck's classic loss pattern.
        _hint("fund_the_understudy_slowking", "fund_attack", SLOWKING_BODY,
              conditions=(
                  ActivationCondition(f"own.card.{SLOWKING}.in_play", "eq", True),
                  ActivationCondition(f"own.card.{SLOWKING}.energy_count", "lt", 2),
              ), confidence="medium"),

        # --- The stack: put ammunition on top of the deck before the attack. ------------------
        _hint("academy_gates_the_stack", "play_card", "own.bench",
              targets=(ACADEMY_AT_NIGHT,), confidence="medium"),
        _hint("ciphermaniac_stacks_two_deep", "play_card", "own.active",
              conditions=(ActivationCondition(f"own.card.{SLOWKING}.in_play", "eq", True),),
              targets=(CIPHERMANIACS_CODEBREAKING,), confidence="low"),
        _hint("bangle_arms_the_copied_hit", "play_card", "own.active",
              conditions=(ActivationCondition("own.active.card_id", "eq", SLOWKING),),
              targets=(BRAVE_BANGLE,), confidence="low"),

        # --- Development. Wanted every turn, never at the cost of a closing attack. -----------
        _hint("establish_benched_slowpoke", "deploy", "own.bench", targets=(SLOWPOKE,),
              conditions=(ActivationCondition("own.bench.space", "gt", 0),)),
        _hint("establish_benched_latias", "deploy", "own.bench", targets=(LATIAS_EX,),
              conditions=(ActivationCondition("own.bench.space", "gt", 0),),
              confidence="medium"),
        _hint("meowth_fetches_a_supporter", "deploy", "own.bench", targets=(MEOWTH_EX,),
              conditions=(ActivationCondition("own.bench.space", "gt", 0),),
              confidence="low"),

        # --- Abilities that are pure profit on their turn. ------------------------------------
        _hint("run_errand_from_the_active_spot", "use_ability",
              f"own.body.card:{MEGA_KANGASKHAN_EX}:first",
              conditions=(ActivationCondition(
                  "turn.ability.card_ids", "contains", MEGA_KANGASKHAN_EX),),
              targets=(MEGA_KANGASKHAN_EX,), deadline="immediate"),
        _hint("flip_the_script_after_their_ko", "use_ability",
              f"own.body.card:{FEZANDIPITI_EX}:first",
              conditions=(ActivationCondition(
                  "turn.ability.card_ids", "contains", FEZANDIPITI_EX),),
              targets=(FEZANDIPITI_EX,), deadline="immediate", confidence="medium"),

        # --- Promotion after a loss: the readiest Slowking, else the drawing wall. ------------
        _hint("promote_the_readiest_slowking", "promote", SLOWKING_BODY,
              conditions=(
                  ActivationCondition("own.active.card_id", "eq", None),
                  ActivationCondition(f"own.card.{SLOWKING}.in_play", "eq", True),
              ), targets=(SLOWKING,)),
        _hint("promote_kangaskhan_to_draw", "promote",
              f"own.body.card:{MEGA_KANGASKHAN_EX}:first",
              conditions=(ActivationCondition("own.active.card_id", "eq", None),),
              targets=(MEGA_KANGASKHAN_EX,), confidence="medium"),
        _hint("promote_slowpoke_stopgap", "promote", f"own.body.card:{SLOWPOKE}:first",
              conditions=(ActivationCondition("own.active.card_id", "eq", None),),
              targets=(SLOWPOKE,), confidence="low"),
    ),
)
