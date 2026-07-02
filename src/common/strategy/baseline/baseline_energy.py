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
        id="advance-the-accel-pieces",
        rationale="During SETUP, advance your own acceleration pieces — PLAY or ATTACH a card the "
                  "deck Roles `accel_source` (e.g. Ignition Energy: one attach = CCC on an "
                  "Evolution; or benching/feeding a bench-accelerator). Role-keyed: the deck opts "
                  "in by naming its accelerators, so the rule stays silent for decks without any. "
                  "NB this co-fires additively with the other SETUP energy rules on an attach "
                  "toward the win-condition (`build-active-wincon` +20, `power-up-attacker` +15, "
                  "`attach-energy-last` -5) — tune it against that cluster, not alone. Folded from "
                  "mega_starmie `accel-into-main` (same trigger + weight).",
        when=lambda c: c.plan == Plan.SETUP and c.option_type in (_PLAY, _ATTACH)
        and "accel_source" in c.roles,
        weight=30, status="assumed"),
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
        id="concentrate-accel-on-one-line-body",
        rationale="The CONCENTRATE counterpart of `spread-attach-to-the-needy` at an ATTACH_FROM "
                  "(bench-accelerator recipient) select: pile the accelerated Energy onto the ONE "
                  "win-condition-Line body already closest to the payoff (`attach_from_concentrate_slot` "
                  "— the Line member carrying the most Energy, still short of the Mega's biggest-attack "
                  "cost) rather than dribbling one Energy onto each bare Staryu. `spread-attach-to-the-"
                  "needy` reads a 1-Energy Staryu as 'done' (it clears Staryu's OWN 1-cost attack), but "
                  "the deck's real payoff is the evolved Mega Starmie ex at 3 Energy (Nebula Beam) — so "
                  "fill ONE Staryu toward that before starting another (ep83116081 f21). Above the spread "
                  "nudge (+20 > +15) so the started body wins the recipient pick; when every Line body is "
                  "bare it fires on the first, still starting exactly one.",
        when=lambda c: c.attach_from_target_is_concentrate,
        weight=20, status="testing"),
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
                and not c.attach_target_is_line_member
                and not c.attach_feeds_firing_accel)),   # a firing accelerator isn't "spent" — feed it
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
        id="conserve-discard-energy-prefer-basic",
        rationale="A discard-at-end-of-turn burst Energy (`discard_eot`, e.g. Ignition — 4 copies, "
                  "discarded each turn, not recoverable) is a finite resource whose value is the "
                  "big-attack turn. So don't spend it when the win-condition's CHEAP attack already "
                  "Knocks Out the opponent's Active AND a reusable Basic is in hand: attach the "
                  "Basic (and take the cheap KO), saving the burst for a turn that genuinely needs "
                  "the bulk. Stands down when the cheap attack CAN'T KO — it never blocks the burst "
                  "you actually need. The strong, KO-aware sibling of the tie-break nudge "
                  "`prefer-reusable-over-burst` (−12, which co-fires here); `build-active-wincon` "
                  "carries the matching carve-out (stands down for a `discard_eot` attach when "
                  "`active_cheap_attack_kos`), and `dont-waste-discard-energy` exempts the wincon — "
                  "so 'prefer the Basic' wins by this rule's full margin. Folded from mega_starmie "
                  "`conserve-ignition-prefer-water` (same trigger + weight).",
        when=lambda c: c.option_type == _ATTACH and "discard_eot" in c.tags
        and c.attach_target_area == _ACTIVE and bool(_WINCON_ROLES & set(c.attach_target_roles))
        and c.board.reusable_energy_in_hand and c.board.active_cheap_attack_kos,
        weight=-40, status="assumed"),
    Hypothesis(
        id="conserve-burst-when-no-ko",
        rationale="`dont-waste-discard-energy` EXEMPTS the win-condition — a burst Energy's bulk "
                  "acceleration (Ignition CCC toward Nebula Beam) is normally the whole point. But when "
                  "the opponent's Active can't be Knocked Out this turn even by my BIGGEST attack fully "
                  "powered (`not board.active_maxed_kos`, e.g. Nebula Beam 210 vs a 230-HP Mega Lucario), "
                  "reaching that big attack buys NO KO — so don't spend the one-shot discard-EOT Energy "
                  "on it. Attach the reusable Basic instead (its cheap attack — Jetting Blow 120 + a "
                  "50-snipe — is at least as useful and KEEPS the Ignition for a turn it can finish the "
                  "job; ep83116501 f70). Fires only on a `discard_eot` attach to the ACTIVE win-condition "
                  "with a reusable Basic in hand as the alternative, so it never strips a genuinely "
                  "KO-enabling burst (that keeps its exemption via `active_maxed_kos`).",
        when=lambda c: c.option_type == _ATTACH and "discard_eot" in c.tags
        and c.attach_target_area == _ACTIVE and bool(_WINCON_ROLES & set(c.attach_target_roles))
        and not c.board.active_maxed_kos and c.board.reusable_energy_in_hand,
        weight=-30, status="testing"),
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
                  "isn't needed this turn, so endorsing the burn would needlessly fight the "
                  "conserve-the-burst rule (`conserve-discard-energy-prefer-basic`); a reusable "
                  "Energy is never penalised, so 'prefer the reusable' wins by its full margin.",
        when=lambda c: c.option_type == _ATTACH and c.attach_target_area == _ACTIVE
        and bool(_WINCON_ROLES & set(c.attach_target_roles)) and c.attach_target_under_max
        and not ("discard_eot" in c.tags and c.board.active_cheap_attack_kos),
        weight=20, status="testing"),
    Hypothesis(
        id="dont-overbuild-the-doomed-wincon",
        rationale="Stop piling Energy onto a DOOMED win-condition Active that can ALREADY attack this "
                  "turn — build the benched successor instead. `concentrate-energy-on-wincon` (+25) and "
                  "`build-active-wincon` (+20) both keep loading the Active win-condition toward its "
                  "BIGGEST attack (Mega Starmie's CCC Nebula Beam), but if that Active will be Knocked "
                  "Out next turn it never lives to fire it — the extra Energy (the 2nd/3rd attach beyond "
                  "the cheapest attack it can already make) is buried with it. So when the Active is the "
                  "wincon PAYOFF, is doomed, already affords its cheapest attack (`not attach_target_"
                  "needs` — it still attacks THIS turn for the trade), and a Bench exists to build, sink "
                  "this attach below the successor's `power-up-attacker` (+15): the Energy goes to the "
                  "body that will still be alive to use it (ep83037962 f48 — 2nd Water onto a doomed "
                  "210-HP Mega instead of the benched Staryu). This is the payoff-side complement of "
                  "`dont-feed-the-doomed` (which guards an OFF-line doomed opener but deliberately "
                  "exempts the win-condition Line): a pre-evolution keeps its Energy THROUGH evolution "
                  "so is still worth feeding, but the fully-evolved payoff does not. Weighted to cancel "
                  "the concentrate+build stack (−45); a burst that UNLOCKS a lethal THIS turn is still "
                  "KO_SCORE tactical and dominates, so it never blocks a genuinely game-winning attach.",
        when=lambda c: c.option_type == _ATTACH and c.attach_target_area == _ACTIVE
        and bool(_WINCON_ROLES & set(c.attach_target_roles))
        and c.board.active_doomed and not c.attach_target_needs
        and c.board.my_bench > 0,
        weight=-45, status="testing"),
    Hypothesis(
        id="feed-the-firing-accelerator",
        rationale="Feed the turn's manual Energy to an ACTIVE accelerator (a Pokémon whose attack "
                  "accelerates Energy to the Bench — `accel_source` Role, e.g. Cinderace's Turbo Flare: "
                  "attach 3 Basic Energy to your Benched Pokémon) when it still NEEDS that Energy to "
                  "fire (Turbo Flare costs 1) — one manual attach becomes SEVERAL on the Bench, far more "
                  "than dribbling one Energy onto a benched body that can't attack anyway. This holds "
                  "even when the accelerator is DOOMED: use its acceleration one last time to power the "
                  "successor before it falls (the prize math — they still have to Knock Out the loaded "
                  "wincon after taking the accelerator; ep83037962 f70, a peer mirror line). Fires off "
                  "`attach_feeds_firing_accel` (accelerator Active + needs Energy + a bench recipient "
                  "present + no ready benched wincon to retreat into instead), so it stays clear of the "
                  "retreat-into-a-ready-attacker case (ep83007714 f65). Strong (+35) — it must beat "
                  "`concentrate-energy-on-wincon` (+25) loading a bench body directly; and it stands "
                  "`dont-feed-the-doomed` down (a firing accelerator is not a spent opener).",
        when=lambda c: c.attach_feeds_firing_accel,
        weight=35, status="testing"),
    Hypothesis(
        id="dont-attach-discard-energy-turn1",
        rationale="Never attach a `discard_eot` Energy (Ignition Energy — 'discard it at the end of "
                  "your turn') on turn 1 going first (`board.turn <= 1`): the starting player CANNOT "
                  "attack on turn 1 (rules.md §first-turn), so the burst Energy is discarded at end of "
                  "turn having powered NOTHING — pure waste of your one manual attach (rules.md:31). "
                  "A hard penalty because it must dominate the accelerator rewards "
                  "(`feed-the-firing-accelerator` +35 / `advance-the-accel-pieces` +30) that otherwise "
                  "reward feeding the Active accelerator (Cinderace) an Ignition it cannot fire this "
                  "turn — the exact regression the human flagged (ep83053965 f6). Gated on `turn <= 1` "
                  "(the sound, engine-verifiable 'cannot attack' case), so it never touches a real "
                  "attacking turn where Ignition unlocks a big attack (that stays `dont-waste-discard-"
                  "energy`'s softer call).",
        when=lambda c: c.option_type == _ATTACH and "discard_eot" in c.tags
        and c.board.turn <= 1,
        weight=-60, status="testing"),
]
