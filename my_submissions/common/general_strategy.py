"""General Strategy — the deck-agnostic doctrine the Pilot applies beneath every deck's own
Strategy (see docs/general-strategy.md, ADR-0008). Pure data: weighted, status-tracked,
rationale-carrying Hypotheses keyed on universal Function Tags + engine card stats. Weights are
seeds on the docs/weights.md scale, ladder-tuned and overridable by id (ADR-0009).
"""
from common.strategy import Hypothesis, Plan, Strategy

# OptionType values (cg/api.py): playing a card from hand / attaching a card to a Pokémon.
_PLAY, _ATTACH = 7, 8
_WINCON_ROLES = {"win_condition", "primary_attacker"}


def _multi_prize(stat) -> bool:
    """A 2-prize (ex) or 3-prize (Mega ex) liability — read straight off the engine CardStat."""
    return bool(stat and (stat.ex or stat.megaEx))


def _is_pokemon(stat) -> bool:
    """A Pokémon (Trainers / Energy report hp 0) — so a PLAY of it develops the Bench."""
    return bool(stat and stat.hp > 0)


HYPOTHESES = [
    Hypothesis(
        id="dig-before-commit",
        rationale="During setup, play draw and search cards first — see more of your deck and "
                  "find your pieces before making irreversible plays like attaching Energy.",
        when=lambda c: c.plan == Plan.SETUP and ("draw" in c.tags or "search" in c.tags),
        weight=20, status="assumed"),
    Hypothesis(
        id="dont-bench-multiprize",
        rationale="Avoid putting a 2-prize (ex) or 3-prize (Mega ex) Pokémon into play during "
                  "setup unless it's your win-condition attacker — every benched multi-prizer is "
                  "an easy multi-prize knockout the opponent can target.",
        when=lambda c: c.plan == Plan.SETUP and _multi_prize(c.stat)
        and not (_WINCON_ROLES & set(c.roles)),
        weight=-15, status="assumed"),
    Hypothesis(
        id="keep-a-bench",
        rationale="Never leave yourself with an empty Bench — if your Active is Knocked Out and "
                  "you have no Pokémon to promote, you lose on the spot. With an empty Bench, "
                  "develop a Basic.",
        when=lambda c: c.board.my_bench == 0 and c.option_type == _PLAY and _is_pokemon(c.stat),
        weight=60, status="assumed"),
    Hypothesis(
        id="attach-energy-last",
        rationale="Attach Energy late in the turn — it is the one irreversible setup action, so "
                  "play your draw, search and development first to reveal the best target before "
                  "committing.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type == _ATTACH,
        weight=-5, status="assumed"),
    Hypothesis(
        id="pre-position-attacker",
        rationale="While racing, keep developing the next attacker on the Bench so a Knocked-Out "
                  "Active is replaced without losing a turn.",
        when=lambda c: c.plan == Plan.RACE and c.option_type == _PLAY and _is_pokemon(c.stat),
        weight=25, status="assumed"),
    Hypothesis(
        id="build-before-attack",
        rationale="During setup, don't waste the turn chipping with a non-lethal attack — your "
                  "turn ends when you attack, so develop your board instead unless the attack "
                  "scores a knockout.",
        when=lambda c: c.plan == Plan.SETUP and c.is_attack and not c.is_ko,
        weight=-20, status="assumed"),
]

GENERAL_STRATEGY = Strategy(name="general", hypotheses=HYPOTHESES)
