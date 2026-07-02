"""BASELINE cluster: BENCH — bench development & prize-liability reflexes (ADR-0025).

Keep a body to promote, don't expose loose multi-prizers, pre-position the next attacker. Pure data,
no Mixin. The `_multi_prize` / `_is_pokemon` CardStat predicates live here because only the bench
rules read them.
"""
from common.strategy.context import _BENCH_MAX, _EVOLVE, _PLAY, _WINCON_ROLES
from common.strategy.strategy import Hypothesis, Plan


def _multi_prize(stat) -> bool:
    """A 2-prize (ex) or 3-prize (Mega ex) liability — read straight off the engine CardStat."""
    return bool(stat and (stat.ex or stat.megaEx))


def _is_pokemon(stat) -> bool:
    """A Pokémon (Trainers / Energy report hp 0) — so a PLAY of it develops the Bench."""
    return bool(stat and stat.hp > 0)


HYPOTHESES = [
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
        id="pre-position-attacker",
        rationale="While racing, keep developing the next attacker on the Bench so a Knocked-Out "
                  "Active is replaced without losing a turn.",
        when=lambda c: c.plan == Plan.RACE and c.option_type == _PLAY and _is_pokemon(c.stat),
        weight=25, status="assumed"),
    Hypothesis(
        id="develop-the-accel-recipient",
        rationale="A bench-accelerator in the Active Spot (an `accel_source`-Role Pokémon whose "
                  "attack loads the BENCH, e.g. Cinderace's Turbo Flare) accelerates onto NOTHING "
                  "while the Bench holds no win-condition-Line recipient "
                  "(`board.accel_recipient_missing`). Developing one is then the top setup priority: "
                  "endorse playing a Line pre-evolution or a bench-filler (Function Tag `bench_fill`) "
                  "to give the acceleration a target — and, via the base, the eventual payoff. Rides "
                  "ALONGSIDE the `keep-a-bench` / `prefer-bench-fill-first` reflexes (which already "
                  "handle the held-bencher cases); the FETCH side — grab the deployable base over a "
                  "stranded payoff — is `fetch-base-before-stranded-payoff` (its general pair since "
                  "2026-06-30). Stands down once a recipient is benched or the Active isn't the "
                  "accelerator; a positive endorsement of development only, so a turn with no "
                  "recipient to find still attacks. Folded from mega_starmie "
                  "`develop-turbo-flare-recipient` (same trigger + weight) — the signal was already "
                  "general Board vocabulary.",
        when=lambda c: c.option_type == _PLAY and c.board.accel_recipient_missing
        and (c.card_is_line_preevo or "bench_fill" in c.tags)
        and c.board.my_bench < _BENCH_MAX,
        weight=20, status="assumed"),
]
