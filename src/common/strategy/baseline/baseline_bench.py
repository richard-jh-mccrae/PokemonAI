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
        rationale="Avoid putting a 2-prize (ex) or 3-prize (Mega ex) Pokémon into play during setup "
                  "unless it's your win-condition attacker — every benched multi-prizer is an easy "
                  "multi-prize knockout for the opponent.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type in (_PLAY, _EVOLVE)
        and _multi_prize(c.stat) and not (_WINCON_ROLES & set(c.roles)),
        weight=-15, status="assumed"),
    Hypothesis(
        id="keep-a-bench",
        rationale="Never leave yourself with an empty Bench — if the Active is Knocked Out with no "
                  "Pokémon to promote, you lose on the spot, so develop a Basic.",
        when=lambda c: c.board.my_bench == 0 and c.option_type == _PLAY and _is_pokemon(c.stat),
        weight=60, status="assumed"),
    Hypothesis(
        id="pre-position-attacker",
        rationale="While racing, keep developing the next attacker on the Bench so a Knocked-Out "
                  "Active is replaced without losing a turn.",
        when=lambda c: c.plan == Plan.RACE and c.option_type == _PLAY and _is_pokemon(c.stat),
        weight=25, status="assumed"),
    Hypothesis(
        id="develop-a-basic-in-setup",
        rationale="During SETUP, play a Basic Pokémon from hand to develop the Bench — the core tempo "
                  "of an evolution deck: lay the Line bases down so they can evolve next turn. The RACE "
                  "mirror `pre-position-attacker` (+25) covers the later game; this fills the SETUP gap "
                  "that left a bare `Play Riolu` at score 0, so a weak chip attack (Meowth's Power Gem) "
                  "or a hand-shuffle out-ranked developing the board and `_finish_turn_last` never "
                  "sequenced the develop first (ep83661652 f29/f33/f40/f44 — mega_lucario 'resisting to "
                  "play basics to bench'). Positive so the develop rides TIER-0, ahead of the tier-2 "
                  "attach / tier-3 shuffle / tier-4 chip attack — develop first, then commit; a real KO "
                  "still dominates (KO_SCORE). Excludes a multi-prize ex (`dont-bench-multiprize` owns "
                  "whether to bench one) and a setup-only `opener` (a stranded body played only turn 1); "
                  "gap-gated on a non-full Bench. mega_starmie develops via `bench_fill`/Turbo Flare so "
                  "it never surfaced this; the deep-evolution decks play their bases from hand.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type == _PLAY and _is_pokemon(c.stat)
        and c.board.my_bench < _BENCH_MAX and not _multi_prize(c.stat) and "opener" not in c.tags,
        weight=12, status="assumed"),
    Hypothesis(
        id="develop-the-accel-recipient",
        rationale="An `accel_source`-Role Active (e.g. Cinderace's Turbo Flare, which loads the Bench) "
                  "accelerates onto nothing while the Bench holds no win-condition-Line recipient "
                  "(`board.accel_recipient_missing`), so endorse playing a Line pre-evolution or "
                  "`bench_fill` card as top setup priority to give it a target. Stands down once a "
                  "recipient is benched or the Active isn't the accelerator; pairs with the FETCH-side "
                  "`fetch-base-before-stranded-payoff` and folds mega_starmie's "
                  "`develop-turbo-flare-recipient` (same trigger + weight).",
        when=lambda c: c.option_type == _PLAY and c.board.accel_recipient_missing
        and (c.card_is_line_preevo or "bench_fill" in c.tags)
        and c.board.my_bench < _BENCH_MAX,
        weight=20, status="assumed"),
]
