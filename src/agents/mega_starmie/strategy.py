"""mega_starmie — Strategy (declarative doctrine). See docs/agent-architecture.md.

Turbo Mega Starmie ex: open Cinderace (Explosiveness), Turbo Flare to load the bench,
tutor + evolve Staryu -> Mega Starmie ex, then fire Nebula Beam (one Ignition Energy on an
Evolution = CCC). Pure data: no engine, no control flow.

DECLARATIONS ONLY — this deck carries ZERO deck Hypotheses. Every rule it ever authored was
folded into the General Strategy (2026-07-02; the play lives there, keyed on the declarations
below — Roles / Lines / params — so any deck making the same declarations inherits it):

    deck rule (historical)          -> general rule                          (home)
    open-cinderace                  -> open-the-accelerator                  baseline_opening
                                       (SUPERSEDED 2026-07-28, ADR-0079: that rung was deleted
                                       with the rest of the Set-Up Active seam; the opening pick
                                       is now `starter_priority` below + the general
                                       `open-the-declared-starter`)
    accel-into-main                 -> advance-the-accel-pieces              baseline_energy
    develop-turbo-flare-recipient   -> develop-the-accel-recipient           baseline_bench
    tutor-the-wincon                -> play-a-tutor-for-the-unfound-wincon   doctrine_fetch
    never-fetch-cinderace           -> dont-fetch-the-setup-only-opener      doctrine_fetch
                                       (opener tag + stranded-evolution guard: no Raboot in
                                       this deck -> a fetched Cinderace is provably dead)
    conserve-ignition-prefer-water  -> conserve-discard-energy-prefer-basic  baseline_energy
    prefer-going-second             -> params["preferred_start"]="second" +
                                       honor-preferred-start                 baseline_opening
    (earlier folds: Hero's Cape deploy -> Tool doctrine `deploy-hp-tool` ADR-0028; Ignition
    discipline -> `dont-waste-discard-energy`; Boss's Orders -> Gust doctrine ADR-0022.)

Weights stay ladder-tuned per deck via tuned.json overrides by id (ADR-0009) — folding moved
the rules' RESIDENCE, not their tunability.
"""
from common.strategy import Line, Strategy

# --- Card ids (mega_starmie/deck.csv) -------------------------------------
STARYU, MEGA_STARMIE_EX, CINDERACE = 1030, 1031, 666
WATER_ENERGY, IGNITION_ENERGY = 3, 17
MEGA_SIGNAL, BUDDY_POFFIN, SALVATORE, HILDA, ULTRA_BALL = 1145, 1086, 1189, 1225, 1121
CRUSHING_HAMMER, BOSS_ORDERS, WALLYS, NIGHT_STRETCHER = 1120, 1182, 1229, 1097

# Per-deck Role overlay on the universal Function Tags (sparse — only deck-intentional cards).
# Roles ARE the deck's opt-in to the role-keyed General Strategy rules (see docstring table).
ROLES = {
    MEGA_STARMIE_EX: ["win_condition", "primary_attacker"],
    CINDERACE: ["accel_source"],                # Explosiveness opener + Turbo Flare
    # (the `starter` Role on Cinderace + Staryu RETIRED 2026-07-28, ADR-0079 — it drove nothing
    #  and naming the openers is now `starter_priority` below. Cinderace keeps `accel_source`,
    #  which the ATTACH/develop rules read; Staryu is carried by the Line.)
    IGNITION_ENERGY: ["accel_source"],           # CCC on an Evolution = one-attach Nebula Beam
    MEGA_SIGNAL: ["tutor"], SALVATORE: ["tutor"], HILDA: ["tutor"],
    BUDDY_POFFIN: ["tutor"], ULTRA_BALL: ["tutor"],
    CRUSHING_HAMMER: ["disruption"], BOSS_ORDERS: ["gust"],
    WALLYS: ["recovery"], NIGHT_STRETCHER: ["recovery"],
}

STRATEGY = Strategy(
    name="mega_starmie",
    lines=[Line(path=[STARYU, MEGA_STARMIE_EX], payoff=MEGA_STARMIE_EX,
                role="win_condition")],   # readiness engine-derived: online at 1 W (Jetting Blow), not CCC
    roles=ROLES,
    # Who takes the ACTIVE Spot at the pregame pick, best first — the COMPLETE ranking of this
    # deck's startable bodies (ADR-0079). Read by the general `open-the-declared-starter`.
    #   Cinderace (160 HP) — the opener AND the accel engine: Explosiveness puts it in the Active
    #     Spot straight from hand, then Turbo Flare (50) loads the Bench. Was `open-cinderace`,
    #     folded to `open-the-accelerator` (+40) — the exemplar `docs/weights.md` cites for the
    #     core-doctrine band, and the reason this rule seeds at the same 40.
    #   Staryu (70 HP) — the win-condition Line base. It wants the BENCH, evolving into Mega
    #     Starmie ex behind the Cinderace wall, not the most-exposed slot.
    starter_priority=[CINDERACE, STARYU],
    params={"setup_energy_target": 3,    # aspirational target (Nebula Beam CCC) — future attach-priority
            "search_budget": 0,           # inert since ADR-0064 removed the Tier-6 escalation (its only
                                          # functional consumer). Tier-1 engine sims (planner_engine_rank,
                                          # lethal_verify, lethal_family) run UNBUDGETED at 0. Kept at 0 to
                                          # hold the submission manifest at Tier-0 (test-pinned).
            "my_archetype": "Cinderace / Mega Starmie ex",   # Posture favorability key (ADR-0026 lever A)
            "reactivity": "solitaire",    # deck-personality (learnthetcg): turbo aggro plays its own
                                          # game; don't over-react to the opponent. CONSUMED by the
                                          # planner forgo-KO rung (planner.py `_forgo_ko`: a "solitaire"
                                          # deck takes the KO and never forgoes it) — LIVE, default-ON.
            "preferred_start": "second"},  # turbo: attack T1 -> general `honor-preferred-start` (-30 on YES)
    hypotheses=[],                        # empty by design — see fold table in the docstring
)
