"""BASELINE cluster: ENERGY — the deck-agnostic Energy-decision reflexes (ADR-0016, ADR-0025).

Pure-data General-Strategy Hypotheses that fire on an ATTACH select (or the energy_accel PLAY that
feeds one). NO Pilot Mixin — the Tactical half of energy (readiness, will-it-die) lives in the Pilot
per ADR-0016; this file is only the tunable positional weights.
"""
from common.strategy.context import _ACTIVE, _ATTACH, _ATTACH_FROM, _BENCH, _PLAY, _WINCON_ROLES
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="power-up-attacker",
        rationale="Attach an Energy every turn — building energy toward an attack is the core "
                  "tempo of the game; without a steady stream of attachments your attackers never "
                  "come online. (Sequenced after draw/search by attach-energy-last, but it still "
                  "happens.) Fires only on a Pokémon that still NEEDS Energy to attack (fewer than "
                  "its cheapest attack cost) — so the agent spreads Energy to a bare Bench attacker "
                  "rather than piling a needless surplus on one that is already online.",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _ATTACH
        and c.attach_target_needs,
        weight=15, status="assumed"),
    Hypothesis(
        id="attach-energy-last",
        rationale="Attach Energy late in the turn — it is the one irreversible setup action, so "
                  "play your draw, search and development first to reveal the best target before "
                  "committing.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type == _ATTACH,
        weight=-5, status="assumed"),
    Hypothesis(
        id="use-acceleration",
        rationale="Energy acceleration multiplies your one manual attachment per turn — getting "
                  "attackers online faster is tempo-positive for any deck, so prioritise playing "
                  "your acceleration.",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and "energy_accel" in c.tags,
        weight=25, status="assumed"),
    Hypothesis(
        id="dont-feed-the-doomed",
        rationale="If your Active will be Knocked Out next turn and you have a benched Pokémon, "
                  "don't sink this Energy into the doomed Active — attach to the successor instead "
                  "so you aren't rebuilding from nothing after it falls.",
        when=lambda c: c.select_context == _ATTACH_FROM and c.option_area == _ACTIVE
        and c.board.active_doomed and c.board.my_bench > 0,
        weight=-30, status="assumed"),
    Hypothesis(
        id="dont-waste-discard-energy",
        rationale="A discard-at-end-of-turn Energy (e.g. Ignition Energy — Function Tag `discard_eot`) "
                  "is wasted unless the Pokémon it goes on attacks THIS turn. Don't attach it to a "
                  "benched Pokémon (it can't attack this turn), on the first turn going first (you "
                  "can't attack at all), or when a reusable Basic Energy is already in hand (attach "
                  "that and save the discard Energy) — except onto your win-condition, where the "
                  "discard Energy's bulk acceleration (e.g. CCC on an Evolution) is the whole point.",
        when=lambda c: c.option_type == _ATTACH and "discard_eot" in c.tags and (
            c.attach_target_area == _BENCH                              # benched can't attack this turn
            or c.board.turn <= 1                                        # first turn going first: no attack
            or (c.board.reusable_energy_in_hand                         # a reusable Basic is available …
                and not (_WINCON_ROLES & set(c.attach_target_roles)))), # … and this isn't the wincon
        weight=-60, status="testing"),   # near-imperative: must beat the accel boosts on a wasted attach
    Hypothesis(
        id="build-active-wincon",
        rationale="Keep attaching Energy to the ACTIVE win-condition until it can fire its BIGGEST "
                  "attack — not just its cheapest. `power-up-attacker` stands down once a Pokémon can "
                  "afford its cheapest attack (Mega Starmie at 1 W already 'needs' nothing — it can "
                  "Jetting Blow), so without this the agent never builds the Active toward its payoff "
                  "hit (Nebula Beam, CCC = 210) and instead diverts the Energy to an idle Bench piece "
                  "or burns the turn on a draw card. Fires only on the Active win-condition that is "
                  "still short of its highest-damage attack cost (`attach_target_under_max`), so it "
                  "stops the moment the big attack is online and never over-stacks a finished attacker.",
        when=lambda c: c.option_type == _ATTACH and c.attach_target_area == _ACTIVE
        and bool(_WINCON_ROLES & set(c.attach_target_roles)) and c.attach_target_under_max,
        weight=20, status="testing"),
]
