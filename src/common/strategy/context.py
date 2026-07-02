"""Engine vocabulary — the option/select/area enum mirrors and shared scoring constants the Pilot
and every doctrine read (cg/api.py enums). Kept in one leaf module so the doctrine modules
(doctrine_gust / doctrine_fetch / doctrine_shuffle_refresh) and general_strategy can import the same constants
without depending on common.pilot (which would be a cycle). `Board` / `Context` themselves live in
common.pilot (Context's default `field(default_factory=Board)` binds them together); the doctrine
modules only need these scalars + Function-Tag / Role name sets.
"""

# ── OptionType (cg/api.py) ──
_PLAY = 7     # play a card from hand (encoded as a bare hand `index`, no `area`)
_ATTACH = 8   # attach an Energy (the one irreversible per-turn commitment)
_EVOLVE = 9   # evolve a Pokémon in play
_RETREAT = 12 # swap the Active out (changes which Pokémon can attack)
_CARD = 3     # a card-target option (e.g. an attack's snipe target, a gust SWITCH target)
_YES = 1      # the "redraw the cards?" affirmative at a Mulligan select
_ATTACK = 13  # attack (the turn-ender)
_END = 14     # end the turn

# ── SelectContext (cg/api.py) ──
_MAIN = 0         # the open turn menu (play/attach/evolve/retreat/attack/end); attack-last applies here
_SETUP_ACTIVE = 1 # SETUP_ACTIVE_POKEMON — choose which Pokémon takes the Active Spot during Set Up
_SETUP_BENCH = 2  # SETUP_BENCH_POKEMON — place a benched Pokémon during Set Up
_SWITCH = 3       # swap into the Active Spot (my own retreat OR a Boss's gust target)
_TO_ACTIVE = 4    # promote a benched Pokémon to the Active Spot
_TO_BENCH = 5     # fetch a Pokémon straight onto the Bench (Buddy-Buddy Poffin)
_TO_HAND = 7      # a search: choose which card to add to your hand
_DISCARD = 8      # choose which card(s) to discard (e.g. Ultra Ball's cost)
_DAMAGE = 15      # choose which Pokémon an attack deals damage to (a bench snipe)
_ATTACH_FROM = 21 # choose the Pokémon to attach an Energy to
_IS_FIRST = 41    # IS_FIRST — the coin-toss "Would you like to go first?" (YesNo)
_NO = 2           # OptionType.NO — decline (the _YES sibling; the coin-toss "go second" option)
_MULLIGAN = 42    # "Would you like to redraw the cards?"

# fetch-grab selects: a maxCount>1 here is a single multi-pick resolved GREEDILY with gap-update +
# take-fewer (not static top-N) so a satisfied need isn't double-grabbed (ADR-0023). Others stay top-N.
_GRAB_CONTEXTS = frozenset({_TO_HAND, _TO_BENCH, _SETUP_BENCH})

# ── AreaType (cg/api.py) ──
_HAND = 2     # AreaType.HAND
_DECK = 1     # AreaType.DECK — a search candidate; ids are revealed in the select's `deck` list
_ACTIVE = 4   # AreaType.ACTIVE
_BENCH = 5    # AreaType.BENCH
_ZONE = {2: "hand", 3: "discard", 4: "active", 5: "bench"}  # AreaType -> player-dict zone key

# ── scoring / classification vocabulary ──
KO_SCORE = 1000            # an option that knocks out the target dominates a mere chip
_SUPPORTER = 3             # CardType.SUPPORTER — a gust on this card costs the one-per-turn Supporter slot
_BASIC_ENERGY = 5          # CardType.BASIC_ENERGY — fungible Energy: a spare is always a future attach,
_SPECIAL_ENERGY = 6        # CardType.SPECIAL_ENERGY — …never a redundant pitch, so excluded from the
                           # hand-duplicate discard signal (cf. `discard-the-hand-duplicate`)
_BENCH_MAX = 5             # a full Bench holds 5 — a bench-filler can place nothing once you're here
_THIN_BENCH = 2            # below this many benched Pokémon the board is underdeveloped — a starter need
_OPENER_TAG = "opener"     # Function Tag: a card whose Ability opens the Active Spot (Explosiveness)
_STARTER_ROLE = "starter"  # deck Role: a card the deck intends to open with
_WINCON_ROLES = {"win_condition", "primary_attacker"}
_ENGINE_TAGS = frozenset({"energy_accel", "draw", "search", "dig"})  # a "support/engine" Pokémon's
                           # Ability does one of these — the `fetch-the-support` importance signal and
                           # the `support_in_play` gap gate (an engine already online needs no tutor)
_EVOLVING_THREAT_DMG = 100 # an evolution line "becomes an attacker" at >= this damage (ADR-0020)

__all__ = [
    "_PLAY", "_ATTACH", "_EVOLVE", "_RETREAT", "_CARD", "_YES", "_NO", "_ATTACK", "_END",
    "_MAIN", "_SETUP_ACTIVE", "_SETUP_BENCH", "_SWITCH", "_TO_ACTIVE", "_TO_BENCH", "_TO_HAND",
    "_DISCARD", "_DAMAGE", "_ATTACH_FROM", "_IS_FIRST", "_MULLIGAN", "_GRAB_CONTEXTS",
    "_HAND", "_DECK", "_ACTIVE", "_BENCH", "_ZONE",
    "KO_SCORE", "_SUPPORTER", "_BASIC_ENERGY", "_SPECIAL_ENERGY", "_BENCH_MAX", "_THIN_BENCH",
    "_OPENER_TAG", "_STARTER_ROLE", "_WINCON_ROLES", "_ENGINE_TAGS", "_EVOLVING_THREAT_DMG",
]
