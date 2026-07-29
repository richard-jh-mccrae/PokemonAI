"""grimmsnarl_ex — Strategy (declarative doctrine). See docs/agent-architecture.md.

Marnie's Grimmsnarl ex CHIP-AND-SHOVEL CONTROL. Two co-dependent lines:

  1. WIN CONDITION — Marnie's Impidimp -> Marnie's Morgrem -> Marnie's Grimmsnarl ex
     (Stage 2, 320 HP). `Punk Up` (Ability, on evolving from hand) searches the deck for up to
     5 Basic {D} Energy and attaches them to your Marnie's Pokémon in any way — the whole
     acceleration engine fires ONCE, on the evolve. `Shadow Bullet` ({D}{D}, 180) also puts
     30 on one of the opponent's Benched Pokémon.
  2. CHIP ENGINE — Snorunt -> Froslass. `Freezing Shroud` puts 1 damage counter on EVERY
     Pokémon with an Ability during Pokémon Checkup, BOTH sides, except Froslass. Munkidori
     (`Adrena-Brain`, needs {D} attached) then moves up to 3 damage counters from one of OUR
     Pokémon to one of THEIRS. Froslass' self-chip is therefore FUEL, not a cost: it loads our
     own bodies so Munkidori can shovel it across.

     ⚠ Freezing Shroud hits our own Munkidori AND our own Grimmsnarl ex (Punk Up is an Ability).
     Only Froslass is exempt. Verified from data/EN_Card_Data.csv, not recalled.

Support: Budew (`Itchy Pollen`, free item-lock — best going SECOND), Spikemuth Gym (once per
player's turn, search a Marnie's Pokémon to hand — SYMMETRIC, the opponent gets it too),
Yveltal (1-of tech: `Clutch` denies the retreat, `Dark Feather` 110 as a Basic {D} attacker).

DECK-BUILD DELTAS vs the source list (two cards absent from the competition pool — verified
against data/EN_Card_Data.csv, and the pool is the authority):
  - Special Red Card CRI 82 (Item)  -> Accompanying Flute TWM 142 (Item), user-chosen. Trades
    late-game hand-shrink for board disruption: forcing Basics onto their Bench feeds Boss's
    Orders targets and Shadow Bullet's 30 bench splash.
  - Gwynn PBL 78 (Supporter) x2     -> Naveen POR 79 x2, user-chosen. Keeps the discard-then-
    refill shape (and the discard still loads Night Stretcher).

DECLARATIONS ONLY — this deck carries ZERO deck Hypotheses so far. The playing doctrine has
NOT been authored yet: run `/deck-genie grimmsnarl_ex` to produce STRATEGY.md + Strategy
Proposals, then `/update-strategy` to author any genuinely deck-bound rules (ADR-0046). Until
then the agent rides the General Strategy, keyed on the declarations below. Known candidates
for that grill, deliberately NOT guessed at here:
  - `Punk Up` is a one-shot on-evolve accel, not a repeatable accel body — whether it earns an
    `accel_source` Role (and whether that misfires the opening rules on a Stage 2) is a
    deck-genie question, so the Role is withheld rather than guessed.
  - the Froslass self-chip -> Munkidori shovel loop has no general-layer equivalent.
  - Spikemuth Gym is symmetric; when to drop it (and when to deny it) is unmodelled.
  - Accompanying Flute (id 1091) currently carries NO behavioral tag in card_functions.json.

Pure data: no engine, no control flow. Weights are seeds — ladder-tuned per deck via
tuned.json overrides by id (ADR-0009).
"""
from common.strategy import Line, Strategy

# --- Card ids (grimmsnarl_ex/deck.csv; resolved by tools/deck_convert.py 2026-07-26) ------
IMPIDIMP, MORGREM, GRIMMSNARL_EX = 646, 647, 648
SNORUNT, FROSLASS, MUNKIDORI = 860, 104, 112
BUDEW, YVELTAL = 235, 689
DARKNESS = 7
LILLIES, BOSS_ORDERS, PETREL, NAVEEN = 1227, 1182, 1219, 1239
POKE_PAD, BUDDY_POFFIN, NIGHT_STRETCHER, RARE_CANDY = 1152, 1086, 1097, 1079
POKEGEAR, SECRET_BOX, ACCOMPANYING_FLUTE, AIR_BALLOON = 1122, 1092, 1091, 1174
SPIKEMUTH_GYM = 1259

# Per-deck Role overlay on the universal Function Tags (sparse — only deck-intentional cards).
# Roles ARE the deck's opt-in to the role-keyed General Strategy rules.
ROLES = {
    GRIMMSNARL_EX: ["win_condition", "primary_attacker"],
    IMPIDIMP:      ["win_condition_base"],       # Line pre-evo (the Line drives line-piece rules)
    FROSLASS:      ["engine"],                   # Freezing Shroud = the chip half of the loop
    MUNKIDORI:     ["engine"],                   # Adrena-Brain = the shovel half; needs {D} attached
    # (Snorunt + Budew carried a `starter` Role until 2026-07-28; ADR-0078 retired it — it drove
    #  nothing, since a hand holding any Basic never reaches the mulligan prompt that read it.
    #  ⚠️ This deck is PRE-DOCTRINE (no STRATEGY.md / aligned.json / tuned.json), so it is exempt from
    #  the `starter_priority` completeness invariant and declares none. Consequence, accepted in
    #  ADR-0078 amendment A: with the five old Set-Up-Active rungs deleted, NOTHING scores this deck's
    #  pregame Active pick and it falls to the engine's option-index order. Authoring the ranking —
    #  Budew's free item-lock, Yveltal as the only real attacker (Dark Feather 110), Munkidori's 110-HP
    #  body, and the two 70-HP Line bases that want the Bench — is /deck-genie's job, and /deck-align's
    #  drift check ("≥2 startable bodies, no starter_priority") is what surfaces it.)
    YVELTAL:       ["secondary_attacker"],       # 1-of Basic {D} tech: Clutch retreat-denial / 110
    BOSS_ORDERS:   ["gust"],                     # the `gust` TAG/Role drives the Gust doctrine (ADR-0022)
    PETREL:        ["tutor"], POKE_PAD: ["tutor"], BUDDY_POFFIN: ["tutor"],
    NIGHT_STRETCHER: ["recovery"],
    ACCOMPANYING_FLUTE: ["disruption"],
}

STRATEGY = Strategy(
    name="grimmsnarl_ex",
    lines=[Line(path=[IMPIDIMP, MORGREM, GRIMMSNARL_EX], payoff=GRIMMSNARL_EX,
                role="win_condition"),
           Line(path=[SNORUNT, FROSLASS], payoff=FROSLASS, role="engine")],
    roles=ROLES,
    params={"setup_energy_target": 2,   # Shadow Bullet is {D}{D}; Punk Up front-loads up to 5
            "search_budget": 0,          # inert since ADR-0064; kept at 0 to hold the submission
                                         # manifest at Tier-0 (test-pinned), as the other agents do.
            "preferred_start": "second",  # Budew's free item-lock wants the go-second turn (the
                                          # general `honor-preferred-start` reads this at the toss)
            "my_archetype": "Marnie's Grimmsnarl ex / Froslass / Munkidori",  # Posture key (ADR-0026)
            # NB "reactivity" is deliberately UNSET: only the value "solitaire" is consumed
            # (planner.py `_forgo_ko`), and this control deck is explicitly not that.
            },
    hypotheses=[],                       # empty by design — doctrine not yet authored (see docstring)
)
