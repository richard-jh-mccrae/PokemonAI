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
_ENERGY = 6   # OptionType.ENERGY — an attached Energy unit (the Crushing Hammer discard target)
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
_DISCARD_ENERGY = 30      # pick which Energy to discard from an opponent's Pokémon (Crushing Hammer,
                          # post-heads). Options are OptionType.ENERGY over their ACTIVE **and** BENCH
                          # (engine: `op_trash_energy_enemy`, cgpy/chain.py, trace-pinned ms_mirror_1002
                          # f14) — the card says "1 of your opponent's Pokémon", not "Active".
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
_ATTACH_TO = 22   # pick the CARD (Energy) to attach to a FIXED Pokémon — recipient not per-option
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

# ── LogType (cg/api.py) ──
_MOVE_CARD = 6  # LogType.MOVE_CARD — a card moved face-up (the pregame Active/Bench placement logs)

# ── scoring / classification vocabulary ──
KO_SCORE = 1000            # a KO option dominates a mere chip
#: Per-Energy value of a recover rider (Aura Jab: "attach up to N Basic {X} from discard") on a
#: NON-KO turn. **DERIVED, not tuned** (ADR-0073 §3: every term is damage at a derived rate) — the
#: MEDIAN damage-per-Energy over the 305 attacks in `data/EN_Card_Data.csv` costing >= 2 Energy,
#: exactly `160/3`. Cost >= 2 is the population an accel rider funds: a rider dumping 3 Energy pays
#: for multi-Energy attackers, and `_recover_recipient_need` already measures need against the
#: recipient's FORWARD form. A test recomputes it from the CSV, so a future set re-derives it.
#:
#: It shipped as a tuned 75 — reverse-engineered from ONE side ("chip-scale, so fueled Aura Jab beats
#: bare Mega Brave") with nothing holding the top, and ~6% over it. Two human rulings bracket the
#: rate at `46.63 < E < 70.85`: ADR-0061's Aura Jab line from below, and ep81904064 f44 from above
#: (at 75 the agent retreated into Cinderace for a 50-damage Turbo Flare rather than attack for 210).
#:
#: Lives HERE rather than in `pilot` because the promote/retreat equation reads it too (ADR-0073 §3b:
#: retreating INTO Cinderace must credit what attacking WITH Cinderace credits), and `pilot` imports
#: that equation — so one leaf owner is what keeps the two readings from drifting apart.
ENERGY_RECOVER = 160 / 3
_SUPPORTER = 3             # CardType.SUPPORTER — gust on this card costs the one-per-turn Supporter slot
_TOOL_CARD = 2             # CardType.TOOL — a Pokémon Tool. Arrives as OptionType.ATTACH exactly like an
                           # Energy, so the Energy hypotheses must test `attach_is_energy` (ml f87)
_BASIC_ENERGY = 5          # CardType.BASIC_ENERGY — fungible Energy: spare = always a future attach,
_SPECIAL_ENERGY = 6        # CardType.SPECIAL_ENERGY — …never a redundant pitch, so excluded from
                           # hand-duplicate discard signal (cf. `discard-the-hand-duplicate`)
_METAL = 8                 # EnergyType.METAL — the predicate Archaludon's board-level retreat grant
                           # scopes to ("all of your Pokémon that have {M} Energy attached")
_BENCH_MAX = 5             # full Bench holds 5 — bench-filler places nothing once you're here
_THIN_BENCH = 2            # below this many benched Pokémon board's underdeveloped — a starter need
_OPENER_TAG = "opener"     # Function Tag: card whose Ability opens Active Spot (Explosiveness)
# (_STARTER_ROLE "starter" RETIRED 2026-07-28, ADR-0078: it drove nothing. Its only consumer was
#  `_hand_startable`, which the mulligan rule reads -- and a hand holding any Basic never reaches
#  that prompt (rulebook L224), so the Role mattered only for a non-Basic starter, i.e. Cinderace,
#  which carries the `opener` TAG anyway. Naming a deck's openers is now `Strategy.starter_priority`.)
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

# POSTURE thresholds (Lever A, ADR-0026) — the Read's verdict on whether a straight race loses. Shared
# vocabulary: the Hypothesis layer reads them (baseline_disruption) AND the priced denial oracle scales
# by them (`Pilot._unfavored`), so they must have exactly one home.
_POSTURE_UNFAVORED = 0.45     # matchup favorability at/below which a straight race loses
_POSTURE_FAVORED = 0.55       # ...at/above which deny the opponent outs (the favored half's mirror;
                              # 0.45-0.55 = the noise band around the 0.5 prior)
_POSTURE_MIN_COVERAGE = 0.25  # min matchup coverage to trust the favorability prior

__all__ = [
    "_PLAY", "_ATTACH", "_EVOLVE", "_RETREAT", "_CARD", "_YES", "_NO", "_ATTACK", "_END",
    "_ENERGY", "_DISCARD_ENERGY",
    "_MAIN", "_SETUP_ACTIVE", "_SETUP_BENCH", "_SWITCH", "_TO_ACTIVE", "_TO_BENCH", "_TO_HAND",
    "_DISCARD", "_DAMAGE", "_DAMAGE_COUNTER_ANY", "_DAMAGE_COUNTER", "_REMOVE_DAMAGE_COUNTER",
    "_REMOVE_DAMAGE_COUNTER_COUNT", "_ABILITY", "_NUMBER", "_ATTACH_FROM", "_ATTACH_TO", "_IS_FIRST", "_MULLIGAN", "_GRAB_CONTEXTS",
    "_HAND", "_DECK", "_ACTIVE", "_BENCH", "_LOOKING", "_ZONE", "_MOVE_CARD",
    "KO_SCORE", "ENERGY_RECOVER", "_METAL",
    "_SUPPORTER", "_TOOL_CARD", "_BASIC_ENERGY", "_SPECIAL_ENERGY", "_BENCH_MAX", "_THIN_BENCH",
    "_OPENER_TAG", "_WINCON_ROLES", "_ENGINE_TAGS", "_ATTACKER_ROLES",
    "_UTILITY_TAGS", "_EVOLVING_THREAT_DMG",
    "_POSTURE_UNFAVORED", "_POSTURE_FAVORED", "_POSTURE_MIN_COVERAGE",
]
