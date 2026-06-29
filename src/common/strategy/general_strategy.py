"""General Strategy — the deck-agnostic doctrine the Pilot applies beneath every deck's own Strategy
(see docs/general-strategy.md, ADR-0008). Pure data: weighted, status-tracked, rationale-carrying
Hypotheses keyed on universal Function Tags + engine card stats. Weights are seeds on the
docs/weights.md scale, ladder-tuned and overridable by id (ADR-0009).

This module owns the deck-agnostic BASELINE rules (opening / sequencing / energy / bench / snipe /
promote / retreat / tool / disruption) and ASSEMBLES the full General Strategy by appending the three
card-archetype doctrines, each of which lives in its own module — Hypotheses AND Pilot-side code
together (the `*Mixin` the Pilot inherits):
  • Gust (Boss's Orders)  doctrine_gust   ADR-0022
  • Fetch (Search)        doctrine_fetch  ADR-0023
  • Shuffle-Refresh       doctrine_shuffle_refresh  ADR-0024
The Pilot scores `GENERAL_STRATEGY.hypotheses` as one flat list (order is irrelevant — the score is a
sum); grouping by doctrine is purely for authoring/legibility.
"""
from common.strategy.context import (_ACTIVE, _ATTACH, _ATTACH_FROM, _BENCH, _DAMAGE, _EVOLVE, _MAIN,
                                      _MULLIGAN, _PLAY, _RETREAT, _TO_ACTIVE, _WINCON_ROLES, _YES)
from common.strategy.doctrine_fetch import HYPOTHESES as FETCH_HYPOTHESES
from common.strategy.doctrine_gust import HYPOTHESES as GUST_HYPOTHESES
from common.strategy.doctrine_shuffle_refresh import HYPOTHESES as REFRESH_HYPOTHESES
from common.strategy.strategy import Hypothesis, Plan, Strategy

# An evolution line "becomes an attacker" once it can OHKO a median body (median HP = 100; 100 is
# ~p76 of damaging attacks). Tunable seed for `snipe-the-evolving-threat` (ADR-0020, docs/rules.md).
EVOLVING_THREAT_DMG = 100
# NOTE: the old `build-before-attack` / `dont-chip-with-a-doomed-active` chip-penalty rules (and the
# `_CHIP_CEILING` they used) were removed — the Pilot's `_finish_turn_last` ("attack last") now
# sequences development ahead of the turn-ending attack structurally, so a blanket chip penalty is
# redundant and was harming play (it dropped a useful chip below End when no development remained).


def _multi_prize(stat) -> bool:
    """A 2-prize (ex) or 3-prize (Mega ex) liability — read straight off the engine CardStat."""
    return bool(stat and (stat.ex or stat.megaEx))


def _is_pokemon(stat) -> bool:
    """A Pokémon (Trainers / Energy report hp 0) — so a PLAY of it develops the Bench."""
    return bool(stat and stat.hp > 0)


# ── BASELINE rules (no named doctrine), in authored order ──
HYPOTHESES = [
    Hypothesis(
        id="dig-before-commit",
        rationale="Play draw and search cards before ending your turn — they cost nothing and see "
                  "more of your deck: during setup, dig before irreversible plays like attaching "
                  "Energy; while racing, dig before the turn-ending attack (you still attack the "
                  "same turn — see `_finish_turn_last`). Free card advantage every turn. Stands down "
                  "for a discard-COST search (`cost_discard`, e.g. Ultra Ball pays 2 cards from hand): "
                  "that dig is NOT free, so it earns no free-dig bonus — its real (cost-aware) value "
                  "is left to dedicated rules, and `_finish_turn_last` sequences it as a commitment. "
                  "Also stands down for a Shuffle-Refresh (`shuffle_hand`, e.g. Lillie's Determination): "
                  "it DESTROYS the hand to redraw, the opposite of a dig — so it earns no early-dig bonus "
                  "and is governed by the separate Shuffle-Refresh doctrine (dead-hand fallback), not here.",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and ("draw" in c.tags or "search" in c.tags)
        and "cost_discard" not in c.tags and "shuffle_hand" not in c.tags,
        weight=20, status="assumed"),
    Hypothesis(
        id="dont-bench-multiprize",
        rationale="Avoid putting a 2-prize (ex) or 3-prize (Mega ex) Pokémon into play during "
                  "setup unless it's your win-condition attacker — every benched multi-prizer is "
                  "an easy multi-prize knockout the opponent can target.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type in (_PLAY, _EVOLVE)
        and _multi_prize(c.stat) and not (_WINCON_ROLES & set(c.roles)),
        weight=-15, status="assumed"),
    Hypothesis(
        id="keep-a-bench",
        rationale="Never leave yourself with an empty Bench — if your Active is Knocked Out and "
                  "you have no Pokémon to promote, you lose on the spot. With an empty Bench, "
                  "develop a Basic.",
        when=lambda c: c.board.my_bench == 0 and c.option_type == _PLAY and _is_pokemon(c.stat),
        weight=60, status="assumed"),
    Hypothesis(
        id="keep-a-startable-hand",
        rationale="Don't mulligan away a hand you can already start — if a Pokémon in hand can "
                  "take the Active Spot (a Basic, or one whose Ability lets it open, like "
                  "Explosiveness), keep it rather than redraw and give the opponent a free card.",
        when=lambda c: c.select_context == _MULLIGAN and c.option_type == _YES
        and c.board.hand_startable,
        weight=-40, status="assumed"),
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
        id="pre-position-attacker",
        rationale="While racing, keep developing the next attacker on the Bench so a Knocked-Out "
                  "Active is replaced without losing a turn.",
        when=lambda c: c.plan == Plan.RACE and c.option_type == _PLAY and _is_pokemon(c.stat),
        weight=25, status="assumed"),
    Hypothesis(
        id="hold-position-in-setup",
        rationale="During setup, don't retreat the Active — you're still developing and want the "
                  "Active (your starter / energy accelerator) to attack; a setup retreat wastes "
                  "the whole turn. Discourages the Retreat option at the open turn menu while the "
                  "Plan is still SETUP.",
        when=lambda c: c.plan == Plan.SETUP and c.select_context == _MAIN
        and c.option_type == _RETREAT,
        weight=-25, status="testing"),
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
        id="hold-clutch-heal",
        rationale="A heal that bounces the healed Pokémon's Energy back to hand (Function Tag "
                  "`clutch_heal`, e.g. Wally's Compassion) is a defensive save, not a value heal — "
                  "hold it until your Active is about to be Knocked Out, then play it to survive. "
                  "Firing only when the Active is doomed keeps it off minor damage AND sequences it "
                  "ahead of the energy attach (so the bounce doesn't waste a fresh attachment): heal "
                  "first, then re-power the same turn — Ignition Energy refills the full cost in one "
                  "attach, or a single Energy is enough for a cheap attack — and still attack. Never "
                  "outranks a lethal (a KO is worth far more than a heal).",
        when=lambda c: c.option_type == _PLAY and "clutch_heal" in c.tags and c.board.active_doomed,
        weight=60, status="testing"),
    Hypothesis(
        id="evolve-into-wincon",
        rationale="Evolving into the win-condition (e.g. Staryu → Mega Starmie ex) brings your main "
                  "attacker online — almost always do it when you can. Strongly prefer an Evolve "
                  "option whose result carries the `win_condition` / `primary_attacker` Role over a "
                  "chip attack or lesser development. (A lethal attack still wins — a positional "
                  "weight never beats a KO.)",
        when=lambda c: c.option_type == _EVOLVE and bool(_WINCON_ROLES & set(c.roles)),
        weight=40, status="testing"),
    Hypothesis(
        id="prefer-rush-evolve-tutor",
        rationale="During setup, prefer a card that can rush-evolve your line (Function Tag "
                  "`rush_evolve`, e.g. Salvatore: fetch a Pokémon and evolve it the same turn its "
                  "pre-evolution was played). It collapses two turns of setup into one and gets the "
                  "win-condition online a turn early. Stands down when there's no pre-evolution in "
                  "play to evolve — without an evolution target the rush-evolve does nothing — AND "
                  "when the payoff is already in hand: you can evolve directly this turn, so spending "
                  "a tutor (and a second copy from the deck) to do the same is wasteful (mirrors "
                  "`tutor-the-wincon`'s `not wincon_in_hand` gate).",
        when=lambda c: c.plan == Plan.SETUP and c.option_type == _PLAY and "rush_evolve" in c.tags
        and c.board.line_preevo_in_play and not c.board.wincon_in_hand,
        weight=30, status="testing"),
    Hypothesis(
        id="snipe-the-threat",
        rationale="When an attack lets you choose which benched Pokémon to damage, hit the biggest "
                  "threat. A benched Pokémon already carrying Energy is closest to attacking, so "
                  "sniping it (chip or Knock Out) denies the opponent their next attacker rather "
                  "than poking a bare, not-yet-online benchsitter.",
        when=lambda c: c.select_context == _DAMAGE and c.target_is_threat,
        weight=20, status="testing"),
    Hypothesis(
        id="snipe-the-weakest",
        rationale="When an attack lets you choose a benched Pokémon to damage and none is a live "
                  "Energy-threat, hit the LOWEST-HP one — it's closest to a knockout (a prize, and "
                  "one fewer future attacker) and avoids dumping a small snipe into a high-HP wall "
                  "it can't dent. Ranks below `snipe-the-threat`, so an energy-bearing attacker is "
                  "still sniped first.",
        when=lambda c: c.select_context == _DAMAGE and c.target_is_weakest,
        weight=15, status="testing"),
    Hypothesis(
        id="snipe-the-evolving-threat",
        rationale="When an attack lets you choose a benched Pokémon to damage and none carries "
                  "Energy, hit a fragile pre-evolution whose evolution line becomes a real attacker "
                  "(its line eventually deals >= 100 — enough to OHKO a typical Active, e.g. Riolu → "
                  "Mega Lucario ex). Sniping it now, before it evolves and powers up, denies that "
                  "future threat. Fires only when the target carries no Energy — the energized case "
                  "is `snipe-the-threat`, so the two never double-count — and ranks below it (an "
                  "energized attacker hits sooner). Stacks additively with `snipe-the-weakest`: a "
                  "low-HP evolving target is the best snipe of all. Generic (any deck); the Read "
                  "refines its accuracy at M2.",
        when=lambda c: c.select_context == _DAMAGE and not c.target_is_threat
        and (c.target_forward_damage or 0) >= EVOLVING_THREAT_DMG,
        weight=18, status="testing"),
    Hypothesis(
        id="promote-the-ready-wincon",
        rationale="When your Active is Knocked Out and a benched win-condition is already powered up "
                  "enough to attack, promote IT — bring your live attacker to the front rather than a "
                  "pre-evolution or a staller.",
        when=lambda c: c.select_context == _TO_ACTIVE and c.card_is_wincon
        and c.board.bench_wincon_ready,
        weight=40, status="testing"),
    Hypothesis(
        id="promote-the-staller",
        rationale="When your Active is Knocked Out and you can NEITHER promote a powered win-condition "
                  "NOR evolve a pre-evolution this turn (the payoff isn't in hand), promote a "
                  "disposable opener / wall (Function Tag `opener`, e.g. Cinderace) instead of a bare "
                  "pre-evolution — it stalls, keeps the fragile pre-evolution safe on the Bench, can "
                  "be retreated for free once you draw the evolution, and can attack if you find "
                  "Energy.",
        when=lambda c: c.select_context == _TO_ACTIVE and "opener" in c.tags
        and not c.board.wincon_in_hand and not c.board.bench_wincon_ready,
        weight=20, status="testing"),
    Hypothesis(
        id="retreat-to-ready-attacker",
        rationale="When your Active is NOT your win-condition (e.g. a spent opener like Cinderace) "
                  "and a benched win-condition is already powered up enough to attack, retreat into "
                  "it — bring your real attacker to the front to finish the turn. Weighted to beat a "
                  "weak chip from the spent Active but never a real attack or a knockout (a lethal "
                  "always wins on tactical).",
        when=lambda c: c.select_context == _MAIN and c.option_type == _RETREAT
        and c.board.bench_wincon_ready and not c.board.active_is_wincon,
        weight=60, status="testing"),
    Hypothesis(
        id="save-tool-for-the-attacker",
        rationale="A Pokémon Tool (Function Tag `tool`, e.g. Hero's Cape) is a one-shot equip — don't "
                  "spend it on an off-role Pokémon (a spent opener / accelerator). Hold it for the "
                  "win-condition / primary attacker that will actually carry the game.",
        when=lambda c: c.option_type == _ATTACH and "tool" in c.tags
        and not (_WINCON_ROLES & set(c.attach_target_roles)),
        weight=-15, status="testing"),
    Hypothesis(
        id="protect-ace-spec-tool",
        rationale="An ACE SPEC card is limited to one per deck and is usually irreplaceable (no second "
                  "copy; not recoverable from the discard). So beyond the usual 'hold a Tool for the "
                  "attacker' reluctance, be EXTRA reluctant to spend an ACE SPEC Tool (e.g. Hero's Cape) "
                  "on an off-role Pokémon — a wasted one-of ACE SPEC is gone for the whole game. Stacks "
                  "additively on `save-tool-for-the-attacker` and reads the structural `aceSpec` fact "
                  "off CardStat; fires only off the win-condition, like the base rule.",
        when=lambda c: c.option_type == _ATTACH and "tool" in c.tags
        and c.stat is not None and getattr(c.stat, "aceSpec", False)
        and not (_WINCON_ROLES & set(c.attach_target_roles)),
        weight=-10, status="testing"),
    Hypothesis(
        id="deploy-hp-tool-on-breakpoint",
        rationale="Deploy a +HP Pokémon Tool the turn it changes a combat outcome — not before. Fires "
                  "when your Active win-condition is about to be Knocked Out (`active_doomed`) AND the "
                  "Tool's flat HP boost would lift it ABOVE the incoming hit (e.g. +100 takes 330 -> "
                  "430, dodging a Lightning OHKO that 330 wouldn't survive). Reads the per-Tool HP off "
                  "`CardStat.hpBonus` (parsed from the Tool's text — the engine has no structured field) "
                  "and the weakness-aware `Board.incoming_active_damage`, so it generalises to ANY "
                  "unconditional +HP Tool and ANY weakness — the deck need not hardcode the bonus. Don't "
                  "equip early (that just exposes an irreplaceable card — e.g. an ACE SPEC Hero's Cape — "
                  "to removal); don't waste it when the boost wouldn't save the Pokémon anyway. Gated to "
                  "the win-condition Active (don't burn a one-shot Tool on a disposable body) and a "
                  "positional weight, so a lethal/KO still outranks it.",
        when=lambda c: c.option_type == _ATTACH and "tool" in c.tags
        and c.stat is not None and getattr(c.stat, "hpBonus", 0) > 0
        and c.attach_target_area == _ACTIVE and bool(_WINCON_ROLES & set(c.attach_target_roles))
        and c.board.active_doomed
        and c.board.incoming_active_damage < c.board.my_active_hp + c.stat.hpBonus,
        weight=50, status="testing"),
    Hypothesis(
        id="play-energy-denial",
        rationale="Play an energy-denial Item (Function Tag `energy_denial`, e.g. Crushing Hammer — "
                  "'flip a coin; if heads, discard an Energy from 1 of the opponent's Pokémon') BEFORE "
                  "your turn-ending attack, whenever the opponent has Energy in play to strip. Setting a "
                  "developing attacker back an Energy (e.g. a Riolu about to become Mega Lucario ex, or "
                  "chipping a powered Active toward un-attacking) is free disruption: the Item costs "
                  "nothing, so `_finish_turn_last` sequences it tier 0 and you strip AND still attack the "
                  "same turn (attack-last). A positional weight — a lethal attack still outranks it on "
                  "tactical, so the KO is taken (after the free strip; the attack is just held one slot). "
                  "Stands down when the opponent has no Energy in play: the coin-flip denial whiffs, so "
                  "hold it (which benched/active Pokémon to strip is the engine's target select).",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and "energy_denial" in c.tags and c.board.opp_has_energy_in_play,
        weight=20, status="testing"),
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
    Hypothesis(
        id="dont-rush-evolve-without-target",
        rationale="Don't play a rush-evolve tutor (Function Tag `rush_evolve`, e.g. Salvatore — "
                  "'search for a card that evolves from 1 of your Pokémon and put it onto that Pokémon "
                  "to evolve it') when there is NO pre-evolution in play to evolve — it whiffs, a "
                  "wasted card. The positive `prefer-rush-evolve-tutor` already stands down here; this "
                  "actively penalises the play so the agent attaches / develops instead. Pushes it "
                  "below an endorsed attach and below 0 (sequenced last).",
        when=lambda c: c.option_type == _PLAY and "rush_evolve" in c.tags
        and not c.board.line_preevo_in_play,
        weight=-60, status="testing"),
    Hypothesis(
        id="snipe-the-strongest-evolving-threat",
        rationale="Among benched pre-evolutions whose lines become attackers, snipe the MOST dangerous "
                  "one — the line that eventually deals the most damage (Riolu → Mega Lucario ex 270, "
                  "online at a single Energy, over Makuhita → Hariyama 210). Breaks the tie that the "
                  "flat `snipe-the-evolving-threat` (any line >= 100) leaves, and stacks high enough to "
                  "outweigh `snipe-the-weakest` so the scariest FUTURE attacker is chipped even when it "
                  "is not the lowest-HP body on the Bench. Fires only on the strongest forward threat "
                  "that carries no Energy, and ONLY when no benched target is already energized — an "
                  "imminent (energized) attacker is `snipe-the-threat`'s job and outranks a latent "
                  "evolving one, so this stands down whenever such a threat is on the Bench.",
        when=lambda c: c.select_context == _DAMAGE and c.target_is_strongest_forward
        and not c.target_is_threat and not c.board.bench_threat_present,
        weight=20, status="testing"),
]

# The full deck-agnostic strategy = baseline + the three doctrines (one flat scored list; ADR-0008).
GENERAL_STRATEGY = Strategy(
    name="general",
    hypotheses=HYPOTHESES + GUST_HYPOTHESES + FETCH_HYPOTHESES + REFRESH_HYPOTHESES)
