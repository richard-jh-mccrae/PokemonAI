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
        rationale="Concentrate Energy on the win-condition slot closest to online "
                  "(`board.priority_wincon_slot`, most Energy while still short of its biggest attack) "
                  "instead of `power-up-attacker` spreading one Energy per bare body. Active is skipped "
                  "once it can already KO (feed the benched successor instead); above `power-up-attacker` "
                  "(+15) so concentrate beats spread.",
        when=lambda c: c.option_type == _ATTACH and c.attach_target_is_priority_wincon,
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
                  "one already online.",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _ATTACH
        and c.attach_target_needs,
        weight=15, status="assumed"),
    Hypothesis(
        id="prefer-active-attach-in-setup",
        rationale="Prefer the ACTIVE attacker over a benched pre-evolution for the turn's manual Energy — "
                  "the Active can use it THIS turn, fixing the dead-heat tie that left Active Cinderace "
                  "bare while Energy went to Staryu (ep83007714 f7). Fires only when the Active needs "
                  "Energy and isn't doomed; small (+8), only breaks the Active-vs-Bench tie.",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _ATTACH
        and c.attach_target_area == _ACTIVE and c.attach_target_needs
        and not c.board.active_doomed,
        weight=8, status="testing"),
    Hypothesis(
        id="attach-energy-last",
        rationale="Attach Energy late in the turn — it's irreversible, so draw/search/development go "
                  "first to reveal the best target.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type == _ATTACH,
        weight=-5, status="assumed"),
    Hypothesis(
        id="advance-the-accel-pieces",
        rationale="During SETUP, advance PLAY/ATTACH of cards Role-tagged `accel_source` (e.g. Ignition "
                  "Energy: one attach = CCC on an Evolution) — role-keyed so it's silent for decks "
                  "without any. Co-fires additively with `build-active-wincon` (+20)/`power-up-attacker` "
                  "(+15)/`attach-energy-last` (-5); folded from mega_starmie `accel-into-main`.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type in (_PLAY, _ATTACH)
        and "accel_source" in c.roles,
        weight=30, status="assumed"),
    Hypothesis(
        id="use-acceleration",
        rationale="Energy acceleration multiplies the one manual attachment per turn — tempo-positive "
                  "for any deck, so prioritize playing it.",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and "energy_accel" in c.tags,
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
                  "f7).",
        when=lambda c: c.board.active_doomed and c.board.my_bench > 0 and (
            (c.select_context == _ATTACH_FROM and c.option_area == _ACTIVE)
            or (c.option_type == _ATTACH and c.attach_target_area == _ACTIVE
                and not c.attach_target_is_line_member
                and not c.attach_feeds_firing_accel)),   # firing accelerator isn't "spent" — feed it
        weight=-30, status="assumed"),
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
        when=lambda c: c.option_type == _ATTACH and c.attach_target_area == _ACTIVE
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
                  "burst stays KO_SCORE tactical and dominates.",
        when=lambda c: c.option_type == _ATTACH and c.attach_target_area == _ACTIVE
        and bool(_WINCON_ROLES & set(c.attach_target_roles))
        and c.board.active_doomed and not c.attach_target_needs
        and c.board.my_bench > 0,
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
]
