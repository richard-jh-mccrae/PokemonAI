"""BASELINE cluster: ENERGY — the deck-agnostic Energy-decision reflexes (ADR-0016, ADR-0025).

Pure-data General-Strategy Hypotheses that fire on an ATTACH select (or the energy_accel PLAY that
feeds one). NO Pilot Mixin — the Tactical half of energy (readiness, will-it-die) lives in the Pilot
per ADR-0016; this file is only the tunable positional weights.
"""
from common.strategy.context import _ACTIVE, _ATTACH, _ATTACH_FROM, _BENCH, _PLAY, _WINCON_ROLES
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="concentrate-energy-on-wincon",
        rationale="Concentrate Energy on ONE win-condition attacker rather than spreading it thin. "
                  "`power-up-attacker` fires on any bare body (so the agent dribbles one Energy onto "
                  "each, and `build-active-wincon` only sees the Active), leaving a benched Mega Starmie "
                  "ex stuck a turn from its payoff. This fires on the win-condition carrying the MOST "
                  "Energy while still short of its biggest attack (`board.priority_wincon_slot`) — the "
                  "one closest to online — so the third Energy tops up the 2-Energy Mega before a bare "
                  "Staryu or an empty second Mega. The Active is skipped once it can already KO (its "
                  "turn is done — feed the benched successor). Above `power-up-attacker` (+15) so the "
                  "concentrate beats the spread.",
        when=lambda c: c.option_type == _ATTACH and c.attach_target_is_priority_wincon,
        weight=25, status="testing"),
    Hypothesis(
        id="prefer-reusable-over-burst",
        rationale="When attaching to your win-condition and a REUSABLE Basic Energy is in hand, prefer "
                  "it over a discard-at-end-of-turn burst Energy (`discard_eot`, e.g. Ignition): both "
                  "advance the attacker by one, but the burst is a finite one-shot best saved for the "
                  "turn that genuinely needs its bulk (CCC -> Nebula Beam in a single attach). A small "
                  "nudge that only breaks the Basic-vs-Ignition tie toward the reusable Energy — a "
                  "burst that UNLOCKS a knockout this turn is tactical (KO_SCORE via the lethal-attach "
                  "lookahead) and still dominates, so this never blocks the Ignition you actually need. "
                  "Fills the gap `dont-waste-discard-energy` leaves (it exempts the win-condition), and "
                  "co-fires harmlessly with a deck's own conserve rule.",
        when=lambda c: c.option_type == _ATTACH and "discard_eot" in c.tags
        and bool(_WINCON_ROLES & set(c.attach_target_roles)) and c.board.reusable_energy_in_hand,
        weight=-12, status="testing"),
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
        id="prefer-active-attach-in-setup",
        rationale="Given the choice of WHERE to put the turn's manual Energy, prefer the ACTIVE "
                  "attacker over a benched pre-evolution. The Active can use the Energy THIS turn "
                  "(attack / an accelerator's attack like Turbo Flare); a benched pre-evolution "
                  "cannot attack and may be several steps from its payoff. `power-up-attacker` fires "
                  "on every needy body equally, so Active-vs-Bench is a dead heat that the "
                  "`attach_to_needy_line` tie-break then resolves toward the benched Line base — "
                  "dumping the Energy on a Staryu while the Active Cinderace (opener / accelerator) "
                  "goes bare (ep83007714 f7). This small nudge feeds the Active instead. Fires only "
                  "when the Active still NEEDS Energy to attack (so it never over-stacks a finished "
                  "Active) and is NOT doomed (a doomed Active hands the Energy to its successor — "
                  "`dont-feed-the-doomed`). Small (+8) so it only breaks the Active-vs-Bench tie and "
                  "never overrides a real priority (concentrate/build/accel).",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _ATTACH
        and c.attach_target_area == _ACTIVE and c.attach_target_needs
        and not c.board.active_doomed,
        weight=8, status="testing"),
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
        id="spread-attach-to-the-needy",
        rationale="At an attach-target select (SelectContext ATTACH_FROM — the engine's recipient-pick "
                  "step for a multi-attach effect, e.g. Cinderace's Turbo Flare 'attach a Basic Energy "
                  "to a Benched Pokémon'), put the Energy on a body that still NEEDS it to attack rather "
                  "than piling a surplus on one already online. The target-pick mirror of "
                  "`power-up-attacker` (the MAIN-menu attach discipline), so the deck spreads its "
                  "accelerated Energy across the Bench (a bare Staryu) instead of over-stacking an "
                  "already-powered attacker (a 3-Energy Mega Starmie ex). Same +15 nudge; fires only on "
                  "a positively-needy recipient (`attach_from_target_needs`), so it never steals the "
                  "attach onto an unknown target.",
        when=lambda c: c.select_context == _ATTACH_FROM and c.attach_from_target_needs,
        weight=15, status="testing"),
    Hypothesis(
        id="dont-feed-the-doomed",
        rationale="If your Active will be Knocked Out next turn and you have a benched Pokémon, "
                  "don't sink this Energy into the doomed Active — attach to the successor (or just "
                  "retreat into it) instead, so you aren't rebuilding from nothing after it falls. "
                  "Fires at BOTH the ATTACH_FROM recipient-pick (a multi-attach effect targeting the "
                  "Active) AND the open-menu manual ATTACH onto the Active. The open-menu branch is "
                  "gated to a NON-win-condition Active (a spent opener like Cinderace): a doomed "
                  "win-condition Active may still be worth building (`build-active-wincon`), but "
                  "burning the turn's Energy on a doomed spent opener you're about to retreat is pure "
                  "waste — e.g. attaching an Ignition to a doomed Cinderace one frame before retreating "
                  "it into a ready benched Mega Starmie ex (ep83007714 f65). Sinks the attach below "
                  "zero so the Retreat-into-the-successor (`retreat-to-ready-attacker`) is taken instead. "
                  "The open-menu branch fires ONLY on an OFF-LINE doomed Active (`not "
                  "attach_target_is_line_member`): a doomed pre-evolution on the win-condition Line "
                  "(a Staryu about to evolve into Mega Starmie ex) KEEPS the Energy through evolution, "
                  "so feeding it — even before a hand-shuffle — is correct (ep82522726 f7), not waste.",
        when=lambda c: c.board.active_doomed and c.board.my_bench > 0 and (
            (c.select_context == _ATTACH_FROM and c.option_area == _ACTIVE)
            or (c.option_type == _ATTACH and c.attach_target_area == _ACTIVE
                and not c.attach_target_is_line_member)),
        weight=-30, status="assumed"),
    Hypothesis(
        id="dont-waste-discard-energy",
        rationale="A discard-at-end-of-turn Energy (e.g. Ignition Energy — Function Tag `discard_eot`) "
                  "is wasted unless the Pokémon it goes on attacks THIS turn AND actually needs the "
                  "burst. Don't attach it to a benched Pokémon (it can't attack this turn), on the "
                  "first turn going first (you can't attack at all), when a reusable Basic Energy is "
                  "already in hand (attach that and save the discard Energy), or onto a non-wincon "
                  "that can ALREADY afford every attack it has (it gains nothing — the burst is just "
                  "discarded; e.g. Ignition onto a Cinderace already holding a {W} for its 1-cost "
                  "Turbo Flare) — except onto your win-condition, where the discard Energy's bulk "
                  "acceleration (e.g. CCC on an Evolution toward Nebula Beam) is the whole point.",
        when=lambda c: c.option_type == _ATTACH and "discard_eot" in c.tags and (
            c.attach_target_area == _BENCH                              # benched can't attack this turn
            or c.board.turn <= 1                                        # first turn going first: no attack
            or (c.board.reusable_energy_in_hand                         # a reusable Basic is available …
                and not (_WINCON_ROLES & set(c.attach_target_roles)))   # … and this isn't the wincon
            or (not c.attach_target_needs and not c.attach_target_under_max  # already affords every attack …
                and not (_WINCON_ROLES & set(c.attach_target_roles)))), # … and not the wincon: pure waste
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
                  "stops the moment the big attack is online and never over-stacks a finished attacker. "
                  "Carve-out: stands down for a one-shot discard-EOT Energy (`discard_eot`, e.g. Ignition) "
                  "when the Active's CHEAP attack already KOs (`active_cheap_attack_kos`) — the big attack "
                  "isn't needed this turn, so endorsing the burn would needlessly fight a deck's "
                  "conserve-the-burst rule (e.g. mega_starmie `conserve-ignition-prefer-water`); a reusable "
                  "Energy is never penalised, so 'prefer the reusable' wins by its full margin.",
        when=lambda c: c.option_type == _ATTACH and c.attach_target_area == _ACTIVE
        and bool(_WINCON_ROLES & set(c.attach_target_roles)) and c.attach_target_under_max
        and not ("discard_eot" in c.tags and c.board.active_cheap_attack_kos),
        weight=20, status="testing"),
]
