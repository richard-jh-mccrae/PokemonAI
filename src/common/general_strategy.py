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
_ACTIVE = 4         # AreaType.ACTIVE
_BENCH = 5          # AreaType.BENCH
_BENCH_MAX = 5      # a full Bench holds 5 — a bench-filler can place nothing once you're here
_WINCON_ROLES = {"win_condition", "primary_attacker"}
_CHIP_CEILING = 100  # build-before-attack suppresses only attacks weaker than this (docs/weights.md)


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
        rationale="During setup, play draw and search cards first — see more of your deck and "
                  "find your pieces before making irreversible plays like attaching Energy.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type == _PLAY
        and ("draw" in c.tags or "search" in c.tags),
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
                  "happens.)",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _ATTACH,
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
        id="build-before-attack",
        rationale="During setup, don't end your turn chipping with a weak attack (below a "
                  "meaningful-damage floor) — your turn ends when you attack, so develop your "
                  "board instead unless the attack scores a knockout or real damage.",
        when=lambda c: c.plan == Plan.SETUP and c.is_attack and not c.is_ko
        and c.tactical < _CHIP_CEILING,
        weight=-20, status="assumed"),
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
        weight=-40, status="testing"),
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
                  "win-condition online a turn early.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type == _PLAY and "rush_evolve" in c.tags,
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
        rationale="During setup, a card that fetches Basics straight onto your Bench (Function Tag "
                  "`bench_fill`, e.g. Buddy-Buddy Poffin) is best played FIRST in a thin deck — it "
                  "develops the Bench and shrinks the deck, raising the quality of every later "
                  "draw/search. A gentle nudge to sequence it ahead of hand-refill tutors. Stands "
                  "down once the Bench is full, where a bench-filler can place nothing.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type == _PLAY and "bench_fill" in c.tags
        and c.board.my_bench < _BENCH_MAX,
        weight=15, status="testing"),
    Hypothesis(
        id="dont-chip-with-a-doomed-active",
        rationale="The RACE-phase analog of build-before-attack: when your Active is about to be "
                  "Knocked Out and the only attack is a weak, non-lethal chip, don't spend the turn "
                  "attacking — your Active dies next turn regardless, so develop your successor "
                  "(attach Energy to the Bench / play a Pokémon) instead of rebuilding from nothing. "
                  "RACE-only (build-before-attack already governs SETUP, and stacking both would over-"
                  "penalise); gated to a sub-threshold, non-KO attack, so it never suppresses a Knock "
                  "Out or a real, meaningful attack.",
        when=lambda c: c.plan == Plan.RACE and c.board.active_doomed and c.is_attack
        and not c.is_ko and c.tactical < _CHIP_CEILING,
        weight=-40, status="testing"),
]

GENERAL_STRATEGY = Strategy(name="general", hypotheses=HYPOTHESES)
