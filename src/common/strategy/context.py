"""Engine vocabulary — the option/select/area enum mirrors and shared scoring constants the Pilot
and every doctrine read (cg/api.py enums). Kept in one leaf module so the doctrine modules
(doctrine_gust / doctrine_fetch / doctrine_shuffle_refresh) and general_strategy can import the same constants
without depending on common.pilot (which would be a cycle). `Board` / `Context` themselves live in
common.pilot (Context's default `field(default_factory=Board)` binds them together); the doctrine
modules only need these scalars + Function-Tag / Role name sets.
"""

# ── OptionType (cg/api.py) ──
_PLAY = 7     # play card from hand (bare hand `index`, no `area`)
_ATTACH = 8   # attach Energy (the one irreversible per-turn commitment)
_EVOLVE = 9   # evolve a Pokémon in play
_RETREAT = 12 # swap Active out -> changes who can attack
_CARD = 3     # card-target option (attack snipe target, gust SWITCH target)
_YES = 1      # "redraw the cards?" affirmative at a Mulligan select
_ATTACK = 13  # attack (the turn-ender)
_END = 14     # end the turn

# ── SelectContext (cg/api.py) ──
_MAIN = 0         # open turn menu (play/attach/evolve/retreat/attack/end); attack-last applies here
_SETUP_ACTIVE = 1 # SETUP_ACTIVE_POKEMON — pick who takes Active Spot during Set Up
_SETUP_BENCH = 2  # SETUP_BENCH_POKEMON — place a benched Pokémon during Set Up
_SWITCH = 3       # swap into Active Spot (own retreat OR a Boss's gust target)
_TO_ACTIVE = 4    # promote a benched Pokémon to Active Spot
_TO_BENCH = 5     # fetch a Pokémon straight onto Bench (Buddy-Buddy Poffin)
_TO_HAND = 7      # search: pick which card to add to hand
_DISCARD = 8      # pick which card(s) to discard (e.g. Ultra Ball's cost)
_DAMAGE = 15      # pick which Pokémon an attack damages (bench snipe)
_DAMAGE_COUNTER_ANY = 14  # place a damage counter "in any way you like" (Phantom Dive spread) — one
                          # counter (10) per select, `select.remainDamageCounter` = counters left,
                          # `select.effect.id` = source card
_DAMAGE_COUNTER = 13      # ADD a damage counter to a Pokémon — a counter-mover's TARGET (Munkidori
                          # Adrena-Brain "to 1 of your opponent's": opponent-owned options)
_REMOVE_DAMAGE_COUNTER = 16       # REMOVE a damage counter — the counter-mover's SOURCE (Munkidori
                                  # "from 1 of your Pokémon": self-owned options; removing = a heal)
_REMOVE_DAMAGE_COUNTER_COUNT = 40 # how many counters to move (NUMBER options {1,2,3})
_ABILITY = 10     # OptionType.ABILITY — use an in-play Ability at the MAIN menu (Adrena-Brain)
_NUMBER = 0       # OptionType.NUMBER — a numeric choice option ({number: N})
_ATTACH_FROM = 21 # pick the Pokémon to attach Energy to
_IS_FIRST = 41    # IS_FIRST — coin-toss "Would you like to go first?" (YesNo)
_NO = 2           # OptionType.NO — decline (the _YES sibling; coin-toss "go second" option)
_MULLIGAN = 42    # "Would you like to redraw the cards?"
_COIN_HEAD = 46   # COIN_HEAD — "Do you want to choose heads?" (only under manual_coin; a sound
                  # engine-verify must BAIL here rather than choose the flip — ADR-0030)

# fetch-grab selects: maxCount>1 here = single multi-pick resolved GREEDILY w/ gap-update +
# take-fewer (not static top-N) so a satisfied need isn't double-grabbed (ADR-0023). Others stay top-N.
_GRAB_CONTEXTS = frozenset({_TO_HAND, _TO_BENCH, _SETUP_BENCH})

# ── AreaType (cg/api.py) ──
_HAND = 2     # AreaType.HAND
_DECK = 1     # AreaType.DECK — search candidate; ids revealed in select's `deck` list
_ACTIVE = 4   # AreaType.ACTIVE
_BENCH = 5    # AreaType.BENCH
_LOOKING = 12  # AreaType.LOOKING — a face-up reveal (Pokégear/search top-N) in `current.looking`;
              # a grab option's candidate resolves there (None entry = facedown, unresolvable)
_ZONE = {2: "hand", 3: "discard", 4: "active", 5: "bench"}  # AreaType -> player-dict zone key

# ── scoring / classification vocabulary ──
KO_SCORE = 1000            # a KO option dominates a mere chip
_SUPPORTER = 3             # CardType.SUPPORTER — gust on this card costs the one-per-turn Supporter slot
_TOOL_CARD = 2             # CardType.TOOL — a Pokémon Tool. Arrives as OptionType.ATTACH exactly like an
                           # Energy, so the Energy hypotheses must test `attach_is_energy` (ml f87)
_BASIC_ENERGY = 5          # CardType.BASIC_ENERGY — fungible Energy: spare = always a future attach,
_SPECIAL_ENERGY = 6        # CardType.SPECIAL_ENERGY — …never a redundant pitch, so excluded from
                           # hand-duplicate discard signal (cf. `discard-the-hand-duplicate`)
_BENCH_MAX = 5             # full Bench holds 5 — bench-filler places nothing once you're here
_THIN_BENCH = 2            # below this many benched Pokémon board's underdeveloped — a starter need
_OPENER_TAG = "opener"     # Function Tag: card whose Ability opens Active Spot (Explosiveness)
_STARTER_ROLE = "starter"  # deck Role: card the deck intends to open with
_WINCON_ROLES = {"win_condition", "primary_attacker"}
_ENGINE_TAGS = frozenset({"energy_accel", "draw", "search", "dig"})  # a "support/engine" Pokémon's
                           # Ability does one of these — the `fetch-the-support` importance signal +
                           # `support_in_play` gap gate (an engine already online needs no tutor)
_ATTACKER_ROLES = frozenset({"win_condition", "primary_attacker", "secondary_attacker",
                             "win_condition_base", "accel_source"})  # deck Roles meaning "this body
                           # attacks (or its attack IS the accel engine)" — the exemption half of the
                           # utility-body read below.
_UTILITY_TAGS = frozenset({"draw", "dig", "search", "supporter_tutor", "stall"})  # a body that exists
                           # to DRAW / TUTOR / STALL, never to attack — read off its OWN tags or its
                           # forward evolution's (Dunsparce→Dudunsparce). Energy on such a body is
                           # wasted while any attacker can take it (`dont-fund-the-non-attacking-body`).
                           # Deliberately NOT `_ENGINE_TAGS`: an `energy_accel` body accelerates BY
                           # attacking (Cinderace's Turbo Flare), so it must keep taking Energy.
_EVOLVING_THREAT_DMG = 100 # evolution line "becomes an attacker" at >= this dmg (ADR-0020)

__all__ = [
    "_PLAY", "_ATTACH", "_EVOLVE", "_RETREAT", "_CARD", "_YES", "_NO", "_ATTACK", "_END",
    "_MAIN", "_SETUP_ACTIVE", "_SETUP_BENCH", "_SWITCH", "_TO_ACTIVE", "_TO_BENCH", "_TO_HAND",
    "_DISCARD", "_DAMAGE", "_DAMAGE_COUNTER_ANY", "_DAMAGE_COUNTER", "_REMOVE_DAMAGE_COUNTER",
    "_REMOVE_DAMAGE_COUNTER_COUNT", "_ABILITY", "_NUMBER", "_ATTACH_FROM", "_IS_FIRST", "_MULLIGAN", "_GRAB_CONTEXTS",
    "_HAND", "_DECK", "_ACTIVE", "_BENCH", "_LOOKING", "_ZONE",
    "KO_SCORE", "_SUPPORTER", "_TOOL_CARD", "_BASIC_ENERGY", "_SPECIAL_ENERGY", "_BENCH_MAX", "_THIN_BENCH",
    "_OPENER_TAG", "_STARTER_ROLE", "_WINCON_ROLES", "_ENGINE_TAGS", "_ATTACKER_ROLES",
    "_UTILITY_TAGS", "_EVOLVING_THREAT_DMG",
]
