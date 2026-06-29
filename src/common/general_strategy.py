"""General Strategy — the deck-agnostic doctrine the Pilot applies beneath every deck's own
Strategy (see docs/general-strategy.md, ADR-0008). Pure data: weighted, status-tracked,
rationale-carrying Hypotheses keyed on universal Function Tags + engine card stats. Weights are
seeds on the docs/weights.md scale, ladder-tuned and overridable by id (ADR-0009).
"""
from common.strategy import Hypothesis, Plan, Strategy

# OptionType values (cg/api.py): playing a card from hand / attaching a card / evolving.
_PLAY, _ATTACH, _EVOLVE = 7, 8, 9
_RETREAT = 12       # OptionType.RETREAT — pay the retreat cost to switch the Active out
_YES = 1            # OptionType.YES — the "redraw the cards?" affirmative at a Mulligan select
_MAIN = 0           # SelectContext.MAIN — the open turn menu (play/attach/evolve/retreat/attack/end)
_MULLIGAN = 42      # SelectContext.MULLIGAN ("Would you like to redraw the cards?")
_ATTACH_FROM = 21   # SelectContext.ATTACH_FROM — choose the Pokémon to attach an Energy to
_DAMAGE = 15        # SelectContext.DAMAGE — choose which Pokémon an attack deals damage to (a snipe)
_TO_HAND = 7        # SelectContext.TO_HAND — a search: choose which card to add to your hand
_TO_ACTIVE = 4      # SelectContext.TO_ACTIVE — promote a benched Pokémon to the Active Spot
_DISCARD = 8        # SelectContext.DISCARD — choose which card(s) to discard (e.g. Ultra Ball's cost)
_ACTIVE = 4         # AreaType.ACTIVE
_BENCH = 5          # AreaType.BENCH
_SUPPORTER = 3      # CardType.SUPPORTER — a gust on this card costs the one-per-turn Supporter slot
_BENCH_MAX = 5      # a full Bench holds 5 — a bench-filler can place nothing once you're here
_THIN_BENCH = 2     # below this many benched Pokémon the board is underdeveloped — a starter need
_WINCON_ROLES = {"win_condition", "primary_attacker"}
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


def _is_reusable_energy(stat, tags) -> bool:
    """A reusable (non-discard) Energy card: hp 0 with a real `energyType`, not tagged
    `discard_eot`. The engine reports `energyType == 0` for Trainers AND colourless specials
    (e.g. Ignition), so a typed Basic is `energyType not in (None, 0)`."""
    return bool(stat and stat.hp == 0 and stat.energyType not in (None, 0)
                and "discard_eot" not in tags)


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
        id="fetch-the-wincon",
        rationale="When a search lets you choose which card to take into your hand (e.g. Ultra Ball), "
                  "pull your win-condition / primary attacker first — getting the payoff into hand is "
                  "the highest-value fetch, because you can then develop it on your own terms. Fires "
                  "off the universal `win_condition` / `primary_attacker` Role, so any deck inherits "
                  "it. Stands down when the payoff is ALREADY in play (no dead second copy) and when "
                  "you are energy-starved (0 Energy on the Active, none in hand) — there "
                  "`fetch-energy-when-starved` should win, since a Pokémon you can't power does nothing.",
        when=lambda c: c.select_context == _TO_HAND and bool(_WINCON_ROLES & set(c.roles))
        and not c.board.wincon_in_play
        and not (c.board.my_active_energy == 0 and not c.board.reusable_energy_in_hand),
        weight=30, status="testing"),
    Hypothesis(
        id="fetch-energy-when-starved",
        rationale="When a search lets you choose a card AND your Active has no Energy and you have "
                  "none in hand, take a reusable Basic Energy — you need to power an attack now, and "
                  "a Pokémon or a discard-at-end-of-turn Energy (Ignition) won't do that. This also "
                  "prefers a reusable Basic over a discard Energy at the same search.",
        when=lambda c: c.select_context == _TO_HAND and c.board.my_active_energy == 0
        and not c.board.reusable_energy_in_hand and _is_reusable_energy(c.stat, c.tags),
        weight=25, status="testing"),
    Hypothesis(
        id="prefer-bench-fill-first",
        rationale="A card that fetches Basics straight onto your Bench (Function Tag `bench_fill`, "
                  "e.g. Buddy-Buddy Poffin) is best played FIRST in a thin deck — it develops the "
                  "Bench and shrinks the deck, raising the quality of every later draw/search, and "
                  "feeds spread-Energy attacks (e.g. Cinderace loading the Bench). Played in setup "
                  "AND while racing (refill a Bench thinned by knockouts before the turn-ending "
                  "attack). Stands down once the Bench is full, where a bench-filler places nothing.",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and "bench_fill" in c.tags and c.board.my_bench < _BENCH_MAX,
        weight=15, status="testing"),
    Hypothesis(
        id="dont-search-an-empty-deck",
        rationale="A deck-search / tutor (Buddy-Buddy Poffin → Basic Pokémon to the Bench; Mega "
                  "Signal → a Mega Evolution ex; Ultra Ball → any Pokémon) is a dead card once the "
                  "deck holds none of what it can fetch. Stand it down when the deck is PROVABLY "
                  "empty of EVERY card the search can pull — all copies accounted for OUTSIDE the "
                  "deck (hand + discard + board + revealed prizes vs the known 60-card list), read "
                  "off `Context.search_targets_exhausted` (built on the sound `deck_definitely_empty_of`"
                  " + each card's fetch-filter). SOUND, never probabilistic: a copy that could still "
                  "sit in the hidden prizes leaves the signal silent, so the search is suppressed "
                  "only when the whiff is CERTAIN — keep the spare card rather than burn it. Outweighs "
                  "`prefer-bench-fill-first` / `dig-before-commit` so a guaranteed-whiff search drops "
                  "below End. (Mirrors `dont-rush-evolve-without-target` for a tutor with no target.)",
        when=lambda c: c.option_type == _PLAY and c.search_targets_exhausted,
        weight=-60, status="testing"),
    Hypothesis(
        id="dont-tutor-the-held-wincon",
        rationale="A tutor that can fetch ONLY the win-condition (e.g. Mega Signal → a Mega "
                  "Evolution ex, the deck's lone Mega being the payoff) is redundant once the "
                  "win-condition is already in hand — it would only dig a second, dead copy. Stand "
                  "it down (read off `Context.search_redundant_wincon`: the search's fetch-set ⊆ the "
                  "win-condition set AND `wincon_in_hand`) so the agent develops / attaches instead "
                  "of burning the turn on a useless dig. Mirrors the deck's `tutor-the-wincon` gate "
                  "(`not wincon_in_hand`) but ACTIVELY penalises, cancelling `dig-before-commit`'s "
                  "blanket endorsement of any search. Stays silent for a flexible tutor (Ultra Ball "
                  "can also fetch a pre-evolution / opener, so its fetch-set isn't ⊆ the wincon).",
        when=lambda c: c.option_type == _PLAY and c.search_redundant_wincon,
        weight=-45, status="testing"),
    Hypothesis(
        id="prefer-wincon-line-piece",
        rationale="When fetching a card into hand (a search), prefer one that builds your win-"
                  "condition LINE — a pre-evolution on the path to the payoff (e.g. Staryu → Mega "
                  "Starmie) over an off-line opener / accelerator (e.g. Cinderace). At a PROMOTE "
                  "(bring a benched Pokémon to the Active Spot) only do this when the payoff is in "
                  "hand to evolve it THIS turn — otherwise promoting a bare pre-evolution just "
                  "exposes your fragile evolution base (see `promote-the-staller`). Ranks below "
                  "`fetch-the-wincon` (the payoff itself) and `fetch-energy-when-starved`.",
        when=lambda c: c.card_is_line_preevo and (
            c.select_context == _TO_HAND
            or (c.select_context == _TO_ACTIVE and c.board.wincon_in_hand)),
        weight=18, status="testing"),
    Hypothesis(
        id="fetch-a-starter",
        rationale="When a search lets you choose a card AND your board is underdeveloped (fewer than "
                  "two benched Pokémon in SETUP), take a startable Basic Pokémon — a body you can play "
                  "down to develop the Bench and open a turn of plays. The fallback grab rung beneath "
                  "the win-condition rungs (`fetch-the-wincon` / `prefer-wincon-line-piece`): when no "
                  "Line piece is on offer you still want board presence over an off-need card. Gap-gated "
                  "— stands down once the Bench is developed (you no longer lack a starter). 'Starter' "
                  "is derived structurally (a Basic: hp > 0, no `evolvesFrom`), so any deck inherits it.",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_starter
        and c.plan == Plan.SETUP and c.board.my_bench < _THIN_BENCH,
        weight=12, status="testing"),
    Hypothesis(
        id="fetch-the-support",
        rationale="When a search lets you choose a card AND you have no engine/support Pokémon in play, "
                  "take one — a Pokémon whose Ability draws, accelerates Energy or searches (Function "
                  "Tags `energy_accel`/`draw`/`search`/`dig`). An online engine multiplies every later "
                  "turn, so when you lack one it is a high-value grab, second only to the win-condition "
                  "and energy-when-starved. Gap-gated off `Board.support_in_play` — stands down once an "
                  "engine is online (no dead second engine). Derived structurally (a Pokémon carrying an "
                  "engine tag), so any deck inherits it; a deck refines which engine via its Roles.",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_support
        and not c.board.support_in_play,
        weight=15, status="testing"),
    Hypothesis(
        id="fetch-when-it-fills-a-need",
        rationale="Whether-to-PLAY a fetch (ADR-0023, decision A): play it when its reachable deck set "
                  "still holds a card you currently LACK — `Context.fetch_fills_a_need`, the lookahead "
                  "that scores the best grab with the SAME grab rungs (shared oracle) before the search "
                  "reveals the deck. The positive endorsement a discard-COST fetch otherwise misses: "
                  "`dig-before-commit` stands down for `cost_discard` (Ultra Ball), so without this an "
                  "Ultra Ball that can fetch your unfound win-condition had no driver to be played. "
                  "Modest, so it sequences as a commitment (`_finish_turn_last`) after the free digs; "
                  "silent on a whiff / when nothing is lacking (best grab value 0). Weighted BELOW a "
                  "free, needed development — a discard-cost dig should not outrank powering your "
                  "attacker (`power-up-attacker` nets +10), the ep82228640-fr7 shape — which also stands "
                  "in for the deferred cost-netting (the 2-card cost makes the net value lower than the "
                  "raw grab). The full cost-netting (subtract the shed cards) and Plan-scaled bar remain.",
        when=lambda c: c.option_type == _PLAY and c.fetch_fills_a_need,
        weight=8, status="testing"),
    Hypothesis(
        id="fetch-deck-priority",
        rationale="Tier-3 escape hatch (ADR-0023): when the deck declares an explicit ordered "
                  "`Strategy.fetch_priority`, grab the highest-priority card on that list that the "
                  "search actually reveals — the combo deck's override of the derived importance rungs "
                  "(it knows a specific piece matters more than the generic win-condition/starter/support "
                  "ladder). Fires on the single best-ranked present candidate (`card_is_top_fetch_priority`, "
                  "resolved cross-option in `Board.top_fetch_priority_id`), weighted above the derived "
                  "grab rungs so the deck's stated order wins. Empty list (most decks) -> silent.",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_top_fetch_priority,
        weight=40, status="testing"),
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
        id="gust-for-the-ko",
        rationale="Play a gust Supporter (Function Tag `gust`, e.g. Boss's Orders — switch one of the "
                  "opponent's Benched Pokémon into the Active Spot) only when it converts to a Knock Out "
                  "this turn: drag up a benched Pokémon your Active can KO, reaching a prize you couldn't "
                  "otherwise (often a high-prize ex/Mega hiding behind a wall). Fires only when such a KO "
                  "exists (`Board.gust_best_ko_prizes > 0`); otherwise HOLD it — gusting a target you "
                  "can't KO gifts the opponent, benching their committed Active safe and handing you "
                  "nothing. The SETUP-before-wincon stand-down only applies to a SUPPORTER gust (it "
                  "costs your one Supporter slot); a free ITEM gust (Pokémon Catcher) into a KO fires "
                  "even in setup. The KO must also beat any FREE KO of the current Active — both attacking it "
                  "(`active_ko_prizes`) and poison/burn finishing it at the next Checkup "
                  "(`active_condition_ko_prizes`); gusting that Active off would only cure it. "
                  "(Whether-to-play only; which benched Pokémon to drag up is the gust SWITCH "
                  "target-select rule. ADR-0022.)",
        when=lambda c: c.option_type == _PLAY and "gust" in c.tags
        and c.board.gust_best_ko_prizes > max(c.board.active_ko_prizes,
                                              c.board.active_condition_ko_prizes)
        and not (getattr(c.stat, "cardType", None) == _SUPPORTER       # Supporter-economy damping only
                 and c.plan == Plan.SETUP and not c.board.wincon_in_play),
        weight=50, status="assumed"),
    Hypothesis(
        id="gust-for-the-stall",
        rationale="Defensive stall-gust (tier 5) — a LAST resort when you're stuck. When your Active is "
                  "doomed, you have no gustable KO and can't KO their Active, but they have an "
                  "energyless, high-retreat benched Pokémon, play a gust Supporter to drag that body "
                  "into the Active Spot: it can't attack and they must spend a turn retreating it, "
                  "buying you a setup turn. Weighted low (below every tutor/draw) so it only wins the "
                  "Supporter slot when nothing else advances you — and it never fires unless you're "
                  "actually under threat. Never stall-gust an Active that carries a special condition "
                  "(`opp_active_condition_gift`) — switching it to the bench CLEARS the condition "
                  "(rules.md §8), so the stall would hand the opponent a free cure. (Mechanically weak: "
                  "a gust doesn't stop a normal retreat, so it only bites on a high retreat cost. ADR-0022.)",
        when=lambda c: c.option_type == _PLAY and "gust" in c.tags
        and c.board.active_doomed
        and c.board.gust_best_ko_prizes == 0 and c.board.active_ko_prizes == 0
        and c.board.stall_target_exists
        and not c.board.opp_active_condition_gift,
        weight=10, status="assumed"),
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
        id="attach-before-hand-shuffle",
        rationale="Attach the Energy you are holding BEFORE playing a card that throws your hand away "
                  "(Function Tag `shuffle_hand`, e.g. Harlequin / Lillie's Determination — each "
                  "'shuffle your hand into your deck'). That card discards any Energy still in hand, "
                  "so playing it first wastes the attachment you could have made (and can shuffle away "
                  "a game-winning Energy). Fires only when a reusable Energy is in hand and you have "
                  "not yet attached this turn — weighted to push the hand-shuffle below an endorsed "
                  "attach AND below 0, so `_finish_turn_last` sequences it last (dig with non-shuffle "
                  "searches first, attach, then refresh the hand).",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.reusable_energy_in_hand and not c.board.energy_attached,
        weight=-60, status="testing"),
    Hypothesis(
        id="hold-wincon-dont-shuffle",
        rationale="Don't shuffle a usable win-condition out of your hand with a hand-shuffling draw "
                  "Supporter (Function Tag `shuffle_hand`, e.g. Lillie's Determination / Judge — "
                  "'shuffle your hand into your deck'). When the win-condition (a Line payoff) is in "
                  "hand, refilling sends it back into the deck, costing the turn you could deploy it — "
                  "hold it and dig another way. Complements `attach-before-hand-shuffle` (which guards "
                  "held Energy) and `keep-key-cards-at-discard` (which guards a cost-discard): this "
                  "guards the hand-shuffle of the PAYOFF itself. Moderate — it nets negative against "
                  "`dig-before-commit` but is NOT absolute, so a genuinely dead hand still refills (the "
                  "win-condition returns to the deck, recoverable; only a tempo cost).",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.wincon_in_hand,
        weight=-25, status="assumed"),
    Hypothesis(
        id="refresh-when-hand-is-dead",
        rationale="Play a Shuffle-Refresh (Function Tag `shuffle_hand`, e.g. Lillie's Determination / "
                  "Judge — 'shuffle your hand into your deck, then draw') ONLY when your hand is dead: no "
                  "other card in it yields a positive-scoring play this turn (`Board.hand_is_dead`, a full "
                  "play-scan of the hand) AND the deck still holds a card you lack (`deck_holds_a_need`). "
                  "ADR-0024 decision (A) — a refresh is not a dig (it DESTROYS the hand), so it is a "
                  "last-resort hand reload, reached only when nothing else is worth doing; this is 'use "
                  "your key cards first' proven structurally (every useful card outscores the refresh). "
                  "Reuses the Fetch keep-value comparator: a live card keeps the hand off this gate, so we "
                  "never shuffle away a hand we'd fetch back. Small positive — beats End (≈0), loses to any "
                  "real play; a dead hand can't contain a better Supporter, so the one-per-turn slot "
                  "economy is subsumed. Never preempts an attack (the scan is hand-only; the turn-ending "
                  "attack stays an `_finish_turn_last` tier-2 commitment, so a dead-hand + lethal refreshes "
                  "THEN KOs the same turn). Layer A; the stochastic pull-EV refinement is deferred.",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.hand_is_dead and c.board.deck_holds_a_need,
        weight=8, status="testing"),
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
    Hypothesis(
        id="prefer-good-in-discard",
        rationale="The deck-override of the discard side (ADR-0023): a recursion / discard-fed deck "
                  "marks cards it WANTS in the discard with the Role `discard_fodder` (e.g. a Pokémon "
                  "a Night-Stretcher/Sacred-Ash line recurs, or Energy a discard-pull accelerator "
                  "reclaims). At a forced discard, prefer pitching such a card — for that deck the bin "
                  "is an asset, so its keep-value in hand is low. Reads the deck Role directly; silent "
                  "for any deck that declares no `discard_fodder`. Outranks the generic "
                  "`discard-the-redundant` (the deck's stated synergy beats a plain duplicate).",
        when=lambda c: c.select_context == _DISCARD and "discard_fodder" in c.roles,
        weight=25, status="testing"),
    Hypothesis(
        id="discard-the-redundant",
        rationale="At a forced discard (e.g. Ultra Ball's cost), shed the card whose need is already "
                  "met first — the lowest keep-value. v1's redundancy signal is a hand copy of a "
                  "Pokémon already in play (`Context.card_is_redundant`): a duplicate body you don't "
                  "need a second of right now. A positive weight ranks it ABOVE a still-needed card as "
                  "the pitch, the mirror of the grab comparator (shed what you'd not fetch back). Pairs "
                  "with `keep-key-cards-at-discard`, which floors the engine pieces / win-condition so "
                  "they are never the pitch — together: pitch the redundant, protect the key.",
        when=lambda c: c.select_context == _DISCARD and c.card_is_redundant,
        weight=20, status="testing"),
    Hypothesis(
        id="keep-key-cards-at-discard",
        rationale="At a cost-discard (e.g. Ultra Ball's 'discard 2 cards from your hand'), don't throw "
                  "away your engine pieces — a discard-at-end-of-turn burst Energy (Function Tag "
                  "`discard_eot`, e.g. Ignition Energy: finite, non-recyclable, the one-attach CCC that "
                  "powers Nebula Beam) or your win-condition. A negative weight ranks those LAST among "
                  "the discard candidates, so the agent sheds a redundant Supporter instead. (Which "
                  "card a search FETCHES is `fetch-the-wincon`; this guards what a cost DISCARDS.)",
        when=lambda c: c.select_context == _DISCARD
        and ("discard_eot" in c.tags or c.card_is_wincon),
        weight=-30, status="testing"),
]

GENERAL_STRATEGY = Strategy(name="general", hypotheses=HYPOTHESES)
