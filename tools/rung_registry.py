"""Where every retired scoring rung went, and which module owns each decision seam — as DATA, not
prose, because only the WHAT can be machine-verified. `tests/test_rung_registry.py` asserts it; the
ADR keeps the WHY.

Lives in `tools/` because a retirement record is build-time history: `tools/submit` packages only
`src/common` and `src/cg`, so nothing here reaches a Kaggle submission (ADR-0004).
"""
from __future__ import annotations

from typing import NamedTuple

# `Fold.into` sentinels. Each says "do NOT go looking for a symbol", and says why not.
EMERGENT = "EMERGENT"        # no code asserts it; the replacing equation produces the behaviour
SUBSUMED = "SUBSUMED"        # deleted because another mechanism already covered the fact; nothing was added
REVERTED = "REVERTED"        # built, then deleted because it MEASURED worse; nothing replaced it
UNRECORDED = "UNRECORDED"    # genuinely retired, but no ADR or fold note in the repo says where it went
UNREPLACED = "UNREPLACED"    # deleted, and the note says OUTRIGHT that nothing has taken the family over
                             # yet. Distinct from UNRECORDED (nobody wrote it down) and from SUBSUMED
                             # (something already covered it): here the gap is the recorded finding.

# The Kaggle competition package deliberately excludes these shared valuations (Issue #459).  They are
# NOT `FOLDED`: Mega Lucario and Dragapult retain the legacy general strategy, outside competition scope.
TARGET_RUNTIME_RETIRED = frozenset({
    "use-acceleration",
    "prefer-active-attach-in-setup",
    "feed-the-line-for-disruptor-lock",
    "place-counter-to-convert",
    "move-counters-off-the-damaged",
    "move-max-counters",
    "prefer-rush-evolve-tutor",
    "dont-rush-evolve-without-target",
    "open-the-declared-starter",
    "phase-stabilize-prefer-heal",
    "phase-close-stop-developing",
    "play-safe-when-ahead-on-prizes",
    "fetch-the-wincon",
    "prefer-payoff-over-preevo",
    "fetch-base-before-stranded-payoff",
    "fetch-energy-when-starved",
    "fetch-the-attack-color",
    "fetch-the-ability-fuel-color",
    "attach-off-color-at-fixed-recipient",
    "prefer-bench-fill-first",
    "dont-recycle-the-dead",
    "recover-to-refill-bench",
    "dont-search-a-probable-whiff",
    "search-the-confirmed-hit",
    "dont-tutor-the-held-wincon",
    "dont-tutor-the-baseless-wincon-turn-one",
    "prefer-wincon-line-piece",
    "develop-the-cheap-prize-wall-line",
    "fetch-a-starter",
    "develop-the-item-lock-opener",
    "dont-fetch-the-setup-only-opener",
    "fetch-the-support",
    "fetch-when-it-fills-a-need",
    "play-a-tutor-for-the-unfound-wincon",
    "costly-fetch-sheds-junk",
    "dont-shed-a-live-card",
    "dont-shed-a-key-card",
    "grab-a-gust-supporter-for-the-ko",
    "grab-the-chain-opener",
    "demote-the-costly-chain-opener",
    "dont-spend-the-last-route-to-a-wanted-evolution",
    "dont-grab-a-card-already-in-hand",
    "grab-what-i-can-play-this-turn",
    "dont-strand-the-evolving-engine",
    "dont-fetch-an-unplayable-evolution-payoff",
    "dont-grab-a-baseless-mid-evolution",
    "hold-costly-fetch-when-line-assembled",
    "dont-costly-tutor-when-starved-and-developed",
    "dont-fetch-before-the-deadline",
    "dont-shuffle-away-the-deferred-fetch",
    "demote-needless-search-supporter-in-setup",
    "fetch-deck-priority",
    "attach-before-hand-shuffle",
    "dont-refresh-into-a-probable-miss",
})

# Deck-local third-runtime rungs intentionally retained outside the Kaggle competition package (Issue #459).
LEGACY_DECK_RUNTIME_RUNG_IDS = {
    "mega_lucario": frozenset({
        "attach-solrock-over-line-base", "fetch-the-missing-engine-half", "dont-fetch-the-redundant-piece",
        "dont-fetch-the-inert-engine-piece", "dont-bench-a-redundant-engine-piece", "spring-heave-ho-when-it-pays",
        "heave-ho-decline-without-payoff", "heave-ho-gust-when-it-pays", "fire-lunar-cycle",
        "grab-lunar-cycle-fuel", "dont-lunar-cycle-away-the-last-attachable-f", "lunar-cycle-the-weak-preevo-last-f",
    }),
    "dragapult_ex": frozenset({"bench-the-comeback-drawer"}),
}


class Fold(NamedTuple):
    """One retired rung. `into` is a `module:Qual.name` symbol, a LIVE rung id, or a sentinel above."""

    adr: str    # zero-padded ADR number, or "" when nothing records this retirement
    into: str
    note: str   # one line; the WHY lives in the ADR


class Decider(NamedTuple):
    """One decision seam and the module that owns it end to end."""

    owner: str      # "module:Qual.name" — resolvable
    flag: str       # `common.runtime.PROFILE` kill-switch, or "" when the seam is unconditional
    adr: str


#: Decision seam -> its owner. The first thing to read when wiring into an existing decision: equation
#: deciders (each kill-switched), doctrine Mixins (ADR-0008), and the turn planner.
DECIDERS: dict[str, Decider] = {
    "attach": Decider("common.pilot:Pilot._attach_value", "attach_value", "0069"),
    "evolve": Decider("common.evolve_value:evolve_value", "evolve_value", "0070"),
    "deploy": Decider("common.deploy_value:deploy_value", "deploy_value", "0086"),
    "promote_retreat": Decider("common.promote_retreat_value:promote_value", "promote_retreat_value", "0100"),
    "deny": Decider("common.deny_relevance:strip_relevance", "deny_relevance", "0080"),
    "snipe": Decider("common.snipe_relevance:target_relevance", "snipe_relevance", "0085"),
    "gust": Decider("common.strategy.doctrines.doctrine_gust:GustMixin", "", "0022"),
    "fetch": Decider("common.strategy.doctrines.doctrine_fetch:FetchMixin", "", "0023"),
    "shuffle_refresh": Decider("common.strategy.doctrines.doctrine_shuffle_refresh:ShuffleRefreshMixin", "", "0024"),
    # The Planner runs unconditionally; `lethal_family` switches its TOP (win) rung, not the whole ladder.
    "turn_plan": Decider("common.strategy.planner:PlannerMixin.plan_turn", "lethal_family", "0037"),
}

#: Retired rung id -> where it went, grouped by the swap that killed it. PERMANENT: entries are NOT pruned
#: when the last `src/` mention goes, because an ADR naming a retired rung still needs this lookup.
FOLDED: dict[str, Fold] = {
    # --- ADR-0069, the attach decider (Issue #139). Nineteen rungs -> one axes-sum marginal.
    "advance-the-accel-pieces": Fold(
        "0069", "common.pilot:Pilot._attach_value",
        "the attach side of acceleration is the decider's accel_value; NOT re-routed into the planner"),
    "arm-the-doomed-active": Fold(
        "0069", "common.pilot:Pilot._attach_value",
        "the survival gate credits ANY attack tonight, not only the biggest"),
    "attach-energy-last": Fold(
        "0069", "common.pilot:Pilot._finish_turn_last",
        "the -5 rung became a structural tier: free development, then Supporter, then ATTACH"),
    # A fold record tracks the MEASUREMENT that retired a rung, never the merge that landed it — so
    # these two stand even though a revert briefly un-landed them.
    "aurajab-skip-partnerless-solrock": Fold(
        "", "common.pilot:Pilot._attach_value",
        "Issue #425: Strategy.partners alone decided ml f87, so the deck rung was measured redundant"),
    "gravity-mountain-vs-stage2": Fold(
        "", "common.pilot:Pilot._boost_lethal_tactical",
        "Issue #424: the boost reaches the card through its card_effects.json clause, not a deck-side id"),
    # --- PR #447 (Issue #386) deleted the rung LADDER. Destinations below are transcribed from
    #     main's own tombstone notes, never inferred.
    "dig-before-commit": Fold(
        "0092", "common.composer:compose",
        "a beam over within-turn sequences scores the dig's successor states by construction"),
    "use-the-draw-engine-ability": Fold(
        "0092", "common.composer:compose", "same claim as dig-before-commit: act informatively, then commit"),
    "dont-spend-unneeded-supporter": Fold(
        "0092", UNREPLACED,
        "BUILD 4's two Board signals still name it; nothing scores off them since the ladder went"),
    "dont-waste-clutch-heal": Fold(
        "0092", "common.composer:compose", "a heal is priced by the survival delta it buys"),
    "hold-clutch-heal": Fold(
        "0092", "common.composer:compose", "the whole HEAL cluster went; the survival delta is the price"),
    "deploy-hp-tool": Fold(
        "0028", "common.composer:compose", "deleted with the Tool doctrine's MAIN-phase half"),
    "hold-the-retreat-tool-with-no-retreat": Fold(
        "0028", "common.composer:compose", "deleted with the Tool doctrine's MAIN-phase half"),
    # The three ids `_finish_turn_last`'s two tiers matched as INLINE string literals. Registrable only
    # since PR #448 deleted those tiers: while a tier still named an id, the harvest read it as LIVE.
    "gust-for-the-ko": Fold(
        "0132", UNREPLACED,
        "hole is TOTAL: CLAUSE_WRITES['gust'] blocks _covers, so rung, tier and leaf are all silent"),
    "gust-for-the-loaded-equal-ko": Fold(
        "0132", UNREPLACED, "sibling gate for the loaded-attacker EQUAL-prize case; same total hole"),
    "retreat-to-wall-the-line": Fold(
        "0132", "common.composer:compose",
        "a narrowing, not a break: the composer scores the retreat in-sequence on 63.4% of MAIN frames"),
    "gust-for-the-stall": Fold(
        "0092", "common.composer:compose", "gust-then-attack is a SEQUENCE; the composer compares it as one"),
    "stall-gust-over-dev-when-starved": Fold(
        "0092", "common.composer:compose", "gust-then-attack is a SEQUENCE; the composer compares it as one"),
    "gust-to-strand-the-key-attacker": Fold(
        "0092", "common.composer:compose", "gust-then-attack is a SEQUENCE; the composer compares it as one"),
    "dont-gift-a-refresh-when-favored": Fold(
        "", "common.strategy.refresh:refills_opponent",
        "the rung went with baseline_disruption; its SIGN GATE is the surviving half"),
    "play-risky-ruins-when-net-positive": Fold(
        "0092", UNREPLACED, "dragapult's own note: the Stadium family it priced is NOT yet taken over"),
    "unfair-stamp-comeback-posture": Fold("", UNRECORDED, "went with the ladder; no note names a successor"),
    "concentrate-accel-on-one-line-body": Fold(
        "", UNRECORDED, "named by a live rationale in mega_lucario; no note names a successor"),
    "build-active-wincon": Fold(
        "0069", "common.pilot:Pilot._attach_value", "the attack axis' typed convex build toward the line payoff"),
    "concentrate-energy-on-wincon": Fold(
        "0069", "common.pilot:Pilot._attach_value", "concentration falls out of the attack axis' convexity"),
    "conserve-burst-when-no-ko": Fold(
        "0069", "common.pilot:Pilot._attach_value", "the burst discipline's no-KO cap against the best reusable Basic"),
    "conserve-discard-energy-prefer-basic": Fold(
        "0069", "common.pilot:Pilot._attach_value", "the burst discipline's resource tie-break"),
    "dont-feed-the-doomed": Fold(
        "0069", "common.pilot:Pilot._attach_value", "the survival gate and its evolution-escape"),
    "dont-fund-the-non-attacking-body": Fold(
        "0069", "common.pilot:Pilot._attach_value",
        "the board-evaluated role gate, which zeroes the attack axis only"),
    "dont-waste-discard-energy": Fold(
        "0069", "common.pilot:Pilot._attach_value", "the burst discipline's evaporation loss on an uncashed one-shot"),
    "dont-waste-off-type-energy": Fold(
        "0069", EMERGENT, "build is a typed slot-fraction, so an Energy filling no slot already scores zero"),
    "feed-the-firing-accelerator": Fold(
        "0069", "common.pilot:Pilot._attach_value", "the forward build an accelerator's routed Energy buys"),
    "power-up-attacker": Fold(
        "0069", "common.pilot:Pilot._attach_value", "the attack axis' tonight-counterfactual under the Attach Budget"),
    "spread-attach-to-the-needy": Fold(
        "0069", "common.pilot:Pilot._attach_value", "spreading is what convexity declines; it was never the goal"),

    # --- ADR-0070, the evolve decider (Issue #140).
    "advance-the-evolution-line": Fold("0070", "common.evolve_value:evolve_value", "the decider's deploy term"),
    "evolve-into-wincon": Fold("0070", "common.evolve_value:evolve_value", "the decider's deploy term"),
    "evolve-the-energized-body-first": Fold(
        "0070", "common.pilot:Pilot._prefer_soonest_arming_evolve",
        "amendment M: deploy cancels per slot, so the equation could not express it and a tie-break was rebuilt"),
    "hold-evolution-until-attacker-ready": Fold(
        "0070", "common.evolve_value:evolve_value", "the dragapult deck rung is income_loss (folded via ADR-0034)"),

    # --- ADR-0086 / ADR-0096, the deploy marginal (Issue #197, Issue #261 item 2d).
    "bench-fill-a-basic": Fold("0086", "common.deploy_value:deploy_value", "decision 6: a CARD-target bench candidate"),
    "bench-the-supporter-tutor": Fold(
        "0086", "common.deploy_value:deploy_value", "the ability leg's need-matched yield"),
    "develop-a-basic-in-setup": Fold(
        "0086", "common.deploy_value:deploy_value", "DEPLOY_WORTH_SCALE is pinned to reproduce its +12 band"),
    "develop-the-accel-recipient": Fold(
        "0086", "common.deploy_value:deploy_value", "DEPLOY_WORTH_SCALE is pinned to reproduce its +20 band"),
    "develop-the-wincon-base-first": Fold(
        "0086", "common.deploy_value:deploy_value", "DEPLOY_WORTH_SCALE is pinned to reproduce its +6 band"),
    "dont-bench-multiprize": Fold(
        "0086", "common.deploy_value:deploy_value", "one of three vetoes a slot PRICE out-ranks; the defect was cost, not identity"),
    "dont-bench-onto-their-path": Fold(
        "0086", "common.deploy_value:deploy_value", "decision 5: bench_path_delta in turns, not a flat penalty"),
    "dont-pre-bench-a-redundant-utility": Fold(
        "0086", "common.deploy_value:deploy_value", "a redundant body prices its own displacement against the slot"),
    "dont-pre-bench-the-supporter-tutor": Fold(
        "0086", "common.deploy_value:deploy_value", "zero at _SETUP_BENCH by derivation: pregame triggers no Ability"),
    "keep-a-bench": Fold(
        "0096", "common.pilot:Pilot._empty_bench_forced",
        "decision 2: the filter runs after _finish_turn_last and wins outright, so the +60 was a third guard"),
    "pre-position-attacker": Fold(
        "0086", "common.deploy_value:deploy_value", "DEPLOY_WORTH_SCALE is pinned to reproduce its +25 band"),

    # --- ADR-0100, the promote/retreat equation (Issue #141). Eleven of twelve rungs.
    "dont-promote-into-their-prize-reach": Fold("0100", EMERGENT, "prize Exposure plus the fatal step"),
    "dont-promote-onto-their-path": Fold(
        "0100", SUBSUMED, "S7c: they attack the Active BECAUSE it is the Active; path membership changes nothing"),
    "hold-position-in-setup": Fold(
        "0100", EMERGENT,
        "a setup retreat pays real retreat_cost for a destination not worth promoting - the ruling's WEAKEST claim"),
    "interpose-the-cheap-attacker-to-preserve-the-wincon": Fold(
        "0100", EMERGENT, "prize Exposure plus the fatal step"),
    "promote-the-accelerator-for-the-ko": Fold(
        "0100", "common.pilot:Pilot._promote_ko_tactical", "S11: the pick site's own Knock-Out layer"),
    "promote-the-ko-attacker": Fold(
        "0100", "common.pilot:Pilot._promote_ko_tactical", "S11: reuses the same best_affordable_ko_value oracle"),
    "promote-the-powered-attacker": Fold(
        "", UNRECORDED,
        "no ADR names its retirement; Board.best_promote_slot survives and still feeds the equation"),
    "promote-the-ready-wincon": Fold("0100", EMERGENT, "my_yield is real reachable damage, not a readiness band"),
    "promote-the-staller": Fold(
        "0100", EMERGENT, "S6a: disposable IS the exposure term, so the rung decomposes with no remainder"),
    "retreat-to-ready-attacker": Fold("0100", EMERGENT, "destination value minus retreat cost"),
    "swap-out-the-locked-attacker": Fold("0100", EMERGENT, "a transient-locked attack scores less on its own option"),

    # --- ADR-0085, snipe relevance (#188). The six-rung additive DAMAGE(15) stack.
    "dont-snipe-a-benched-tera": Fold(
        "0085", "common.pilot:Pilot._snipe_tera_veto", "a KO_SCORE-class Tactical no positional stack can outvote"),
    "snipe-for-the-ko": Fold("0085", "common.pilot:Pilot._snipe_ko_dominator", "the armed replacement for its +60"),
    "snipe-on-the-path": Fold("0085", "common.snipe_relevance:target_relevance", "my prize-route leg"),
    "snipe-the-evolving-threat": Fold("0085", "common.snipe_relevance:target_relevance", "the forward leg"),
    "snipe-the-forced-promotion": Fold("0085", "common.snipe_relevance:target_relevance", "their-plan leg"),
    "snipe-the-threat": Fold("0085", "common.snipe_relevance:target_relevance", "their-plan leg"),
    "snipe-the-top-threat": Fold(
        "0085", "common.snipe_relevance:target_relevance",
        "was an argmax-equality boolean standing in for 'is this the biggest?'"),

    # --- ADR-0079, the Set-Up ACTIVE pick. Five rungs -> one deck declaration.
    "dont-open-multiprize-active": Fold(
        "0079", "common.strategy.strategy:Strategy.starter_priority", "a guard that second-guessed an explicit rank"),
    "dont-open-with-the-engine": Fold(
        "0079", "common.strategy.strategy:Strategy.starter_priority", "a guard that second-guessed an explicit rank"),
    "open-the-accelerator": Fold(
        "0079", "common.strategy.strategy:Strategy.starter_priority", "a deck opinion expressed by proxy Role"),
    "open-the-item-lock-starter": Fold(
        "0079", "common.strategy.strategy:Strategy.starter_priority", "a deck opinion expressed by proxy Tag"),
    "start-solrock-over-lunatone": Fold(
        "0079", "common.strategy.strategy:Strategy.starter_priority", "ids live in the declaration, never a trigger"),

    # --- ADR-0102, hand-size relief (Issue #261 item 2c).
    "disrupt-when-unfavored": Fold(
        "0102", "common.pilot:Pilot._hand_size_relief_tactical", "SUBSTITUTED, not re-expressed: no Read is consulted"),
    "play-harlequin-vs-hand-size": Fold(
        "0102", "common.pilot:Pilot._hand_size_relief_tactical", "a flat proxy for the damage Powerful Hand scales off"),
    "strip-the-stacked-engine-hand": Fold(
        "0102", "common.pilot:Pilot._hand_size_relief_tactical", "took _STACKED_HAND = 6 with it, as its last reader"),

    # --- ADR-0065, card Worth: the _DISCARD ladder and the shuffle keep-floors.
    "discard-the-dead-opener": Fold(
        "0065", "common.pilot:Pilot._discard_equation_rows", "the ladder's positive-pitch premise at source, not its weight"),
    "discard-the-hand-duplicate": Fold(
        "0065", "common.strategy.doctrines.doctrine_fetch:FetchMixin._shed_signals", "the junk band's replaceable clause"),
    "discard-the-redundant": Fold(
        "0065", "common.strategy.doctrines.doctrine_fetch:FetchMixin._shed_signals", "the junk band's costs-nothing clause"),
    "discard-the-redundant-tutor": Fold(
        "0065", "common.strategy.planner:PlannerMixin._deploy_odds", "the premise survives as a Worth factor on keep_cost"),
    "hold-successor-when-doomed": Fold(
        "0065", "common.gate_library:closing_gate_reaccess",
        "the pressure gate: a card answering the doom has a deadline no probabilistic redraw can bank against"),
    "hold-wincon-dont-shuffle": Fold(
        "0065", "common.pilot:Pilot._refresh_shed_keepcost", "the hand-QUALITY guards fold in as one currency"),
    "hold-irreplaceable-tool-dont-shuffle": Fold(
        "0065", "common.pilot:Pilot._refresh_shed_keepcost", "the graded SHED prices a held ACE SPEC at its role tier"),
    "hold-line-piece-dont-shuffle": Fold(
        "0065", "common.pilot:Pilot._refresh_shed_keepcost", "was the flat SHED's hand-quality proxy"),
    "hold-wincon-with-base-dont-shuffle": Fold(
        "0065", "common.pilot:Pilot._refresh_shed_keepcost", "was the flat SHED's hand-quality proxy"),
    "keep-engine-supporter-at-discard": Fold(
        "0065", "common.pilot:Pilot._discard_equation_rows", "seam-D: a Worth floor, not a keep floor - re-access still discounts it"),
    "keep-gust-and-recovery-at-discard": Fold(
        "0065", "common.card_worth:TAG_TIER", "behavioural tag -> worth points, which the oracle could not see before"),
    "keep-key-cards-at-discard": Fold(
        "0065", "common.card_worth:TAG_TIER", "its lowest protected tier became the fetch shed's `key` bar"),

    # --- Single-rung retirements, each with its own record.
    "dont-refresh-for-nothing": Fold(
        "0024", REVERTED, "the sound deck_holds_a_need veto regressed 43%/47% at the 2026-07-03 A/B"),
    "dont-shuffle-away-the-bigger-hand": Fold(
        "0060", "common.strategy.refresh:hand_swing", "required a hand_disruption tag, so it could not reach Lillie's at all"),
    "grab-a-draw-supporter-in-setup": Fold(
        "0122", "common.pilot:Pilot._grab_refresh_value",
        "amendment: a refresh is priced by its real pull, so the flat +10 floor and its tie-break both went"),
    "play-energy-denial": Fold(
        "0062", "common.pilot:_DENIAL_PLAY_W", "price the quantity denied; the flat +20 paid the same for 270 as for 70"),
    "refresh-when-hand-is-dead": Fold(
        "0024", SUBSUMED, "amendment: dig-before-commit's +20 plays a dead-hand refresh anyway"),

    # --- ADR-0034 deck -> general folds. The destination is a LIVE rung, not a symbol.
    "fetch-the-engine-first": Fold(
        "0034", "fetch-the-missing-engine-half", "the replacement is role/quantity-aware, not blanket-engine"),
    "never-fetch-cinderace": Fold("0034", "dont-fetch-the-setup-only-opener", "structural, and general once stated"),
    "prefer-going-second": Fold("0034", "honor-preferred-start", "reads Strategy.preferred_start instead of one deck"),
    "tutor-the-wincon": Fold("0034", "play-a-tutor-for-the-unfound-wincon", "general once the wincon Role carried it"),
}

#: Id-SHAPED tokens in `src/` prose that were never scoring rungs — so `FOLDED` is not asked to
#: explain a retirement that never happened. Unlike `FOLDED`, an entry here may be removed.
NOT_A_RUNG: dict[str, str] = {}

#: RATCHET on how many `src/` sites still name a retired rung: it may only SHRINK. The one legitimate
#: reason to raise it — registering newly-retired rungs widens the scan's reach — must be stated here.
MAX_MENTIONS = 39                        # 228 -> 39: the 2026-08-08 prose reduction drained the rest
