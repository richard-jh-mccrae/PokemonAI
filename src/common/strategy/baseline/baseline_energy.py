"""BASELINE cluster: ENERGY — the deck-agnostic Energy-decision reflexes (ADR-0016, ADR-0025).

Pure-data General-Strategy Hypotheses that fire on an ATTACH select (or the energy_accel PLAY that
feeds one). NO Pilot Mixin — the Tactical half of energy (readiness, will-it-die) lives in the Pilot
per ADR-0016; this file is only the tunable positional weights.
"""
from common.strategy.context import (_ACTIVE, _ATTACH, _ATTACH_FROM, _ATTACKER_ROLES, _BENCH,
                                     _PLAY, _WINCON_ROLES)
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="concentrate-energy-on-wincon",
        rationale="Concentrate Energy on the win-condition slot closest to online "
                  "(`board.priority_wincon_slot`, most Energy while still short of its biggest attack) "
                  "instead of `power-up-attacker` spreading one Energy per bare body. Active is skipped "
                  "once it can already KO (feed the benched successor instead); above `power-up-attacker` "
                  "(+15) so concentrate beats spread.",
        when=lambda c: c.option_type == _ATTACH and c.attach_is_energy
        and c.attach_target_is_priority_wincon,
        weight=25, status="testing"),
    Hypothesis(
        id="prefer-reusable-over-burst",
        rationale="Prefer a reusable Basic over a discard-at-end-of-turn burst Energy (`discard_eot`, "
                  "e.g. Ignition) when attaching to the win-condition — save the one-shot burst for a "
                  "turn that needs its bulk (CCC -> Nebula Beam). Small tie-break nudge only; a burst that "
                  "unlocks a KO this turn is tactical (KO_SCORE) and still dominates. Fills the gap "
                  "`dont-waste-discard-energy` leaves by exempting the win-condition.",
        when=lambda c: c.option_type == _ATTACH and "discard_eot" in c.tags
        and bool(_WINCON_ROLES & set(c.attach_target_roles)) and c.board.reusable_energy_in_hand,
        weight=-12, status="testing"),
    Hypothesis(
        id="power-up-attacker",
        rationale="Attach an Energy every turn — the core tempo of the game — sequenced after "
                  "draw/search by `attach-energy-last`. Fires only on a Pokémon still needing Energy for "
                  "its cheapest attack, so it spreads to a bare Bench attacker rather than over-stacking "
                  "one already online. Gated on `attach_is_energy`: a Pokémon Tool arrives as the same "
                  "OptionType.ATTACH but provides no Energy, so it must never be priced as one (ml f87: "
                  "Air Balloon scored +15 onto a benched Solrock). The `attach_target_needs` test is an "
                  "ANTI-signal on a non-attacking body — see `dont-fund-the-non-attacking-body`.",
        when=lambda c: c.option_type == _ATTACH and c.attach_is_energy and c.attach_target_needs,
        weight=15, status="assumed"),
    Hypothesis(
        id="dont-fund-the-non-attacking-body",
        rationale="Never put Energy on a body that exists to DRAW / TUTOR / STALL while a real attacker "
                  "can take it — at EITHER funding seam: the turn's manual ATTACH and an accelerator's "
                  "ATTACH_FROM recipient pick. `power-up-attacker` fires on `attach_target_needs` ('carries "
                  "fewer Energy than its cheapest attack cost'), which RANKS THE WORST BODY HIGHEST: a "
                  "Meowth ex needing 3 for Tuck Tail out-scores an already-online Riolu (ml f84), a "
                  "Colorless-cost Dunsparce swallows the deck's only {D} Munkidori fuel (dragapult f21, "
                  "CRITICAL), and at Aura Jab's bench-load every body tied at `spread-attach-to-the-needy` "
                  "+15 so the option index picked Lunatone (ml f121, CRITICAL). `Pilot._is_utility_body` "
                  "reads it universally — an `engine`-only Role, or a `_UTILITY_TAGS` tag on the body or "
                  "its forward evolution — and exempts every attacker Role and Line member, so Solrock "
                  "(secondary_attacker + engine) still takes Energy. −12 nets the utility body below the "
                  "spread (+15 → +3) without pushing a LONE engine body below End, so it still absorbs the "
                  "attach when it is the only legal home. Replaces mega_lucario's `dont-attach-to-the-engine`. "
                  "MUTUALLY EXCLUSIVE with the narrower `dont-power-the-draw-engine` (which owns the _ATTACH "
                  "draw-engine case, dragapult f21): gated `not attach_target_is_draw_engine` so a Dunsparce "
                  "is penalised once, not twice. This rule keeps everything that rule misses — the "
                  "`_ATTACH_FROM` seam (ml f121), and _ATTACH utility bodies that draw via an untagged "
                  "Ability (engine-role Lunatone) or tutor (supporter_tutor Meowth ex, ml f84).",
        when=lambda c: (c.option_type == _ATTACH or c.select_context == _ATTACH_FROM)
        and c.attach_is_energy and c.attach_target_is_utility_body
        and not c.attach_target_is_draw_engine,
        weight=-12, status="assumed"),
    Hypothesis(
        id="dont-waste-off-type-energy",
        rationale="Don't attach an Energy of a TYPE the target already has enough of when its attack "
                  "still LACKS a different specific type (`attach_type_wasted`) — verify the Pokémon's "
                  "energy NEEDS, then attach the type it's short of. A multi-type wincon (Dragapult's "
                  "Phantom Dive [Fire, Psychic]) was fed a 2nd Psychic while the Fire went unmet, "
                  "stranding the attack (ep83686860 f45); the count-only `power-up-attacker`/`build-"
                  "active-wincon` can't see type. −12 nets the wasted attach below the on-type one "
                  "(both otherwise +10) so the needed type wins; silent for single-type decks and "
                  "colourless slots (sound-or-silent, no false suppression).",
        when=lambda c: c.option_type == _ATTACH and c.attach_type_wasted,
        weight=-12, status="assumed"),
    Hypothesis(
        id="prefer-active-attach-in-setup",
        rationale="Prefer the ACTIVE attacker over a benched pre-evolution for the turn's manual Energy — "
                  "the Active can use it THIS turn, fixing the dead-heat tie that left Active Cinderace "
                  "bare while Energy went to Staryu (ep83007714 f7). Fires only when the Active needs "
                  "Energy and isn't doomed; small (+8), only breaks the Active-vs-Bench tie. STANDS DOWN "
                  "when the Active isn't the deck's attacker — no attacker Role (declared or derived "
                  "accel), off every Line — while a benched Line member sits un-powered "
                  "(`bench_line_member_needs`): a role-less tech Active (Munkidori, 86091728 f19) is "
                  "Active incidentally, so the tie goes back to dead-heat and the decide()-only "
                  "`attach_to_needy_line` tie-break develops the benched line instead. The charter case "
                  "keeps its +8 (Cinderace is `accel_source`); the rejected 'next-attack cost already "
                  "covered' framing is measured OUT (the f19 Active is bare — it would never fire).",
        when=lambda c: c.option_type == _ATTACH and c.attach_is_energy
        and c.attach_target_area == _ACTIVE and c.attach_target_needs
        and not c.board.active_doomed
        and not (c.board.bench_line_member_needs                 # an un-powered line waits benched …
                 and not c.attach_target_is_line_member          # … and the Active is off-Line …
                 and not (_ATTACKER_ROLES & set(c.attach_target_roles))),  # … and not a deck attacker
        weight=8, status="testing"),
    Hypothesis(
        id="attach-energy-last",
        rationale="Attach Energy late in the turn — it's irreversible, so draw/search/development go "
                  "first to reveal the best target.",
        when=lambda c: not c.board.line_ready and c.option_type == _ATTACH
        and c.attach_is_energy,                                            # pre-payoff turns
        weight=-5, status="assumed"),                    # (the ADR-0040 gate-ban migration: was plan==SETUP)
    Hypothesis(
        id="advance-the-accel-pieces",
        rationale="During SETUP, advance PLAY/ATTACH of cards Role-tagged `accel_source` (e.g. Ignition "
                  "Energy: one attach = CCC on an Evolution) — role-keyed so it's silent for decks "
                  "without any. Co-fires additively with `build-active-wincon` (+20)/`power-up-attacker` "
                  "(+15)/`attach-energy-last` (-5); folded from mega_starmie `accel-into-main`.",
        when=lambda c: not c.board.line_ready and c.option_type in (_PLAY, _ATTACH)
        and "accel_source" in c.roles,
        weight=30, status="assumed"),
    Hypothesis(
        id="use-acceleration",
        rationale="Energy acceleration multiplies the one manual attachment per turn — tempo-positive "
                  "for any deck, so prioritize playing it.",
        when=lambda c: c.option_type == _PLAY and "energy_accel" in c.tags,
        weight=25, status="assumed"),
    Hypothesis(
        id="spread-attach-to-the-needy",
        rationale="At an ATTACH_FROM recipient-pick (multi-attach effect, e.g. Turbo Flare), put Energy "
                  "on a body that still needs it rather than an already-online one — the target-pick "
                  "mirror of `power-up-attacker`, same +15. Fires only on a positively-needy recipient "
                  "(`attach_from_target_needs`).",
        when=lambda c: c.select_context == _ATTACH_FROM and c.attach_from_target_needs,
        weight=15, status="testing"),
    Hypothesis(
        id="concentrate-accel-on-one-line-body",
        rationale="CONCENTRATE counterpart of `spread-attach-to-the-needy` at ATTACH_FROM: pile "
                  "accelerated Energy onto the win-condition-Line body closest to payoff "
                  "(`attach_from_concentrate_slot`) rather than dribbling one Energy per bare Staryu, "
                  "since a 1-Energy Staryu reads 'done' but the real payoff needs 3 (ep83116081 f21). "
                  "Above the spread nudge (+20 > +15) so a started body wins the pick; still starts "
                  "exactly one when all bodies are bare.",
        when=lambda c: c.attach_from_target_is_concentrate,
        weight=20, status="testing"),
    Hypothesis(
        id="dont-feed-the-doomed",
        rationale="If the Active is doomed next turn and a Bench exists, don't sink Energy into it — "
                  "attach to the successor instead (an Ignition onto doomed Cinderace before retreating "
                  "into ready Mega Starmie ex was pure waste, ep83007714 f65). Open-menu branch is "
                  "gated to a NON-win-condition, OFF-Line doomed Active, since a doomed win-condition "
                  "pre-evolution keeps Energy through evolution and is still worth feeding (ep82522726 "
                  "f7). STANDS DOWN for the offensive item-lock maneuver "
                  "(`can_lock_line_with_disruptor`): there the Active is DELIBERATELY fed to pay its "
                  "enabling retreat into a benched item_lock (dragapult t2, a support-ex PIVOT like "
                  "Fezandipiti ex that this off-Line branch would otherwise starve — the line-preevo "
                  "variant is already exempt via `not attach_target_is_line_member`).",
        when=lambda c: c.board.active_doomed and c.board.my_bench > 0
        and not c.board.can_lock_line_with_disruptor and (
            (c.select_context == _ATTACH_FROM and c.option_area == _ACTIVE)
            or (c.option_type == _ATTACH and c.attach_target_area == _ACTIVE
                and not c.attach_target_is_line_member
                and not c.attach_feeds_firing_accel      # firing accelerator isn't "spent" — feed it
                and not c.board.active_arm_available)),   # go down swinging (off-Line attacker, ml f21/f19)
        weight=-30, status="assumed"),
    Hypothesis(
        id="arm-the-doomed-active",
        rationale="Go down swinging: when the Active is doomed but attaching THIS Energy COMPLETES its "
                  "biggest attack THIS turn (`attach_completes_biggest_attack`), ARM it — a real hit before "
                  "it falls beats banking the Energy on a bench body that can't cash it this turn. ml "
                  "f21/f19: attach the lone {F} to the Active Solrock -> Cosmic Beam 70 NOW (Lunatone is "
                  "benched so it's live), vs `concentrate-energy-on-wincon` (+25) pumping a benched Riolu we "
                  "can't evolve this turn (no Mega Lucario ex in hand). The OFF-Line analogue of "
                  "`dont-overbuild-the-doomed-wincon`'s go-down-swinging stand-down (which the wincon-Role "
                  "attach already gets); +20 lands the Active attach (power-up +15 − attach-last −5 + 20 = "
                  "+30) above the bench pre-evo pump (+20), and pairs with `dont-feed-the-doomed` standing "
                  "down on the same signal. A KO always dominates (KO_SCORE).",
        when=lambda c: c.option_type == _ATTACH and c.attach_target_area == _ACTIVE
        and c.board.active_doomed and c.board.active_arm_available,   # real attacker, biggest attack this
        #   attach completes, no ready benched wincon to retreat into instead (excludes ml 84889011 f24's
        #   utility Lunatone, f42 Makuhita one-short, and the retreat-into-ready-wincon accel case).
        weight=20, status="assumed"),
    Hypothesis(
        id="feed-the-line-for-disruptor-lock",
        rationale="Step 1 of the OFFENSIVE item-lock maneuver (dragapult f20): attach the turn's Energy "
                  "to the fragile line-preevo ACTIVE so it can retreat into a benched item_lock opener "
                  "(Budew) and Itchy-Pollen the opponent's Item turn (`can_lock_line_with_disruptor`). "
                  "The energy is DELIBERATELY spent to pay the enabling retreat, so this overcomes "
                  "`dont-feed-the-doomed` (which reads the early line-preevo Active as doomed) — same as "
                  "`retreat-to-wall-the-line` positively endorses the retreat step. +20 nets the Active "
                  "above a bench recipient (+15) despite the −30 doom penalty. Silent for decks with no "
                  "benched item-lock opener; kill-switched via the signal (`disruptor_lock_maneuver`).",
        when=lambda c: c.board.can_lock_line_with_disruptor and (
            (c.select_context == _ATTACH_FROM and c.option_area == _ACTIVE)
            or (c.option_type == _ATTACH and c.attach_target_area == _ACTIVE)),
        weight=20, status="testing"),
    Hypothesis(
        id="dont-waste-discard-energy",
        rationale="A `discard_eot` Energy (e.g. Ignition) is wasted unless the recipient attacks THIS "
                  "turn and actually needs the burst — don't attach to a benched Pokémon, turn-1-going-"
                  "first, when a reusable Basic is already in hand, or onto a non-wincon that already "
                  "affords every attack it has. Exempts the win-condition, where the burst's bulk "
                  "acceleration (CCC toward Nebula Beam) is the whole point.",
        when=lambda c: c.option_type == _ATTACH and "discard_eot" in c.tags and (
            c.attach_target_area == _BENCH                              # benched can't attack this turn
            or c.board.turn <= 1                                        # first turn going first: no attack
            or (c.board.reusable_energy_in_hand                         # reusable Basic available …
                and not (_WINCON_ROLES & set(c.attach_target_roles)))   # … and not the wincon
            or (not c.attach_target_needs and not c.attach_target_under_max  # already affords every attack …
                and not (_WINCON_ROLES & set(c.attach_target_roles)))), # … and not wincon: pure waste
        weight=-60, status="testing"),   # near-imperative: must beat accel boosts on a wasted attach
    Hypothesis(
        id="conserve-discard-energy-prefer-basic",
        rationale="A `discard_eot` burst Energy (e.g. Ignition, finite/non-recoverable) is wasted if "
                  "spent when the win-condition's cheap attack already KOs and a reusable Basic is in "
                  "hand — attach the Basic instead, saving the burst for a turn that needs the bulk. "
                  "Stands down when the cheap attack can't KO; strong KO-aware sibling of "
                  "`prefer-reusable-over-burst` (-12, co-fires), folded from mega_starmie "
                  "`conserve-ignition-prefer-water`.",
        when=lambda c: c.option_type == _ATTACH and "discard_eot" in c.tags
        and c.attach_target_area == _ACTIVE and bool(_WINCON_ROLES & set(c.attach_target_roles))
        and c.board.reusable_energy_in_hand and c.board.active_cheap_attack_kos,
        weight=-40, status="assumed"),
    Hypothesis(
        id="conserve-burst-when-no-ko",
        rationale="`dont-waste-discard-energy` exempts the win-condition, but when even the fully-powered "
                  "BIGGEST attack can't KO (`not board.active_maxed_kos`, e.g. Nebula Beam 210 vs 230-HP "
                  "Mega Lucario), the big attack buys nothing — attach the reusable Basic instead and "
                  "keep the Ignition for a turn that finishes the job (ep83116501 f70). Fires only on a "
                  "`discard_eot` attach to the ACTIVE win-condition with a reusable Basic available, so a "
                  "genuinely KO-enabling burst keeps its exemption.",
        when=lambda c: c.option_type == _ATTACH and "discard_eot" in c.tags
        and c.attach_target_area == _ACTIVE and bool(_WINCON_ROLES & set(c.attach_target_roles))
        and not c.board.active_maxed_kos and c.board.reusable_energy_in_hand,
        weight=-30, status="testing"),
    Hypothesis(
        id="build-active-wincon",
        rationale="Keep attaching to the ACTIVE win-condition until it affords its BIGGEST attack, not "
                  "just its cheapest — `power-up-attacker` stands down too early (e.g. Mega Starmie at "
                  "1 W already 'needs' nothing) and would otherwise leave Nebula Beam (CCC=210) unbuilt. "
                  "Fires while `attach_target_under_max`; stands down for a `discard_eot` attach when "
                  "the cheap attack already KOs (`active_cheap_attack_kos`), deferring to "
                  "`conserve-discard-energy-prefer-basic`.",
        when=lambda c: c.option_type == _ATTACH and c.attach_is_energy
        and c.attach_target_area == _ACTIVE
        and bool(_WINCON_ROLES & set(c.attach_target_roles)) and c.attach_target_under_max
        and not ("discard_eot" in c.tags and c.board.active_cheap_attack_kos),
        weight=20, status="testing"),
    Hypothesis(
        id="dont-overbuild-the-doomed-wincon",
        rationale="Stop piling Energy onto a DOOMED win-condition Active that already affords its "
                  "cheapest attack — it won't live to fire the bigger one `concentrate-energy-on-wincon` "
                  "(+25)/`build-active-wincon` (+20) keep building toward (ep83037962 f48: 2nd Water onto "
                  "a doomed Mega instead of benched Staryu). Payoff-side complement of "
                  "`dont-feed-the-doomed`; weighted -45 to cancel that stack, though a lethal-unlocking "
                  "burst stays KO_SCORE tactical and dominates. Stands down when THIS attach COMPLETES the "
                  "doomed Active's biggest attack (`attach_completes_biggest_attack`) — go down swinging with "
                  "the payoff attack this last turn (ms 85163079 f51: 2W+1 = Nebula 210), unlike overbuilding "
                  "for a turn that won't come (f48: 1W→2W still short of CCC=3).",
        when=lambda c: c.option_type == _ATTACH and c.attach_target_area == _ACTIVE
        and bool(_WINCON_ROLES & set(c.attach_target_roles))
        and c.board.active_doomed and not c.attach_target_needs
        and c.board.my_bench > 0
        and not c.attach_completes_biggest_attack,  # go down swinging: this attach turns the big attack ON now
        weight=-45, status="testing"),
    Hypothesis(
        id="feed-the-firing-accelerator",
        rationale="Feed Energy to an ACTIVE accelerator (`accel_source` Role, e.g. Cinderace's Turbo "
                  "Flare: attach 3 Basic to the Bench) when it still needs Energy to fire — one manual "
                  "attach becomes several on the Bench, and holds even when the accelerator is doomed "
                  "since it can power the successor before falling (ep83037962 f70). Fires off "
                  "`attach_feeds_firing_accel` (excludes the retreat-into-ready-attacker case, "
                  "ep83007714 f65); strong (+35, beats `concentrate-energy-on-wincon`'s +25) and stands "
                  "`dont-feed-the-doomed` down.",
        when=lambda c: c.attach_feeds_firing_accel,
        weight=35, status="testing"),
    Hypothesis(
        id="dont-attach-discard-energy-turn1",
        rationale="Never attach a `discard_eot` Energy on turn 1 going first (`board.turn <= 1`): the "
                  "starting player can't attack (rules.md §first-turn), so the burst is discarded having "
                  "powered nothing (rules.md:31). Hard penalty (-60) to dominate the accelerator rewards "
                  "(`feed-the-firing-accelerator` +35/`advance-the-accel-pieces` +30) that otherwise fed "
                  "an unfireable Ignition to Cinderace (ep83053965 f6); gated strictly on `turn <= 1` so "
                  "real attacking turns stay `dont-waste-discard-energy`'s softer call.",
        when=lambda c: c.option_type == _ATTACH and "discard_eot" in c.tags
        and c.board.turn <= 1,
        weight=-60, status="testing"),
    Hypothesis(
        id="fuel-the-dormant-ability",
        rationale="Attach the colour that switches a DORMANT in-play Ability on — the {D} a bare "
                  "Munkidori needs for Adrena-Brain (relay ≤3 counters ours→theirs each turn: spreads "
                  "toward multi-KO Phantom Dive turns AND heals the lock body) — over a fungible "
                  "attach elsewhere. The attach-side sibling of `fetch-the-ability-fuel-color` (+5), "
                  "keyed on `attach_fuels_dormant_ability` (the target's `abilityEnergyTypes` colour, "
                  "none attached), whose predicate ALSO exempts the fuel from `dont-waste-off-type-"
                  "energy`'s attack-cost read (86091728 f19: the {D}→Munkidori attach measured −12 "
                  "'wasted'). STANDS DOWN while a benched Line member sits un-powered "
                  "(`bench_line_member_needs`): in setup the line eats first — the 86091728-19 pin's "
                  "priority — and the fuel follows once the line is fed. +5 breaks the tie among "
                  "needy bodies toward the pairing that spends the otherwise-dead colour.",
        when=lambda c: c.option_type == _ATTACH and c.attach_fuels_dormant_ability
        and not c.board.bench_line_member_needs,
        weight=5, status="assumed"),
    Hypothesis(
        id="dont-power-the-draw-engine",
        rationale="Don't sink the turn's Energy into a DRAW-ENGINE body — one carrying a `draw`/`stall` "
                  "tag OR evolving into one (`attach_target_is_draw_engine`: Dunsparce → Dudunsparce) — "
                  "when it is NOT on the win-condition Line and NOT itself a win-condition. The off-color "
                  "{D} (Munkidori fuel) got sunk into the Dunsparce→Dudunsparce engine because Dunsparce's "
                  "Colorless-cost attack made {D} 'payable', so `power-up-attacker` (+15) read it as an "
                  "attacker (dragapult f21). -18 nets that spread below an on-Line body; excludes Line "
                  "members so a wincon pre-evo whose Stage-1 happens to draw (Drakloak's Recon) is never "
                  "demoted; silent for decks with no TAGGED draw-engine (Solrock/Lunatone draw via an "
                  "Ability, untagged, so they never trip it).",
        when=lambda c: c.option_type == _ATTACH and c.attach_target_is_draw_engine
        and not c.attach_target_is_line_member
        and not bool(_WINCON_ROLES & set(c.attach_target_roles)),
        weight=-18, status="testing"),
]
