"""BASELINE cluster: PROMOTE — which benched Pokémon to bring up after a Knock Out, at a TO_ACTIVE
select (ADR-0025). Ready wincon first; otherwise a disposable staller over a bare pre-evolution.
Pure data, no Mixin.
"""
from common.strategy.context import _SWITCH, _TO_ACTIVE
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="promote-the-accelerator-for-the-ko",
        rationale="When Active is KO'd and a benched accelerator (Role `accel_source`) can itself KO the "
                  "opponent's Active this turn (`promote_target_kos`), promote it instead of the "
                  "win-condition — takes the prize AND loads the Bench for next turn, keeping the wincon "
                  "fresh. Ranks above `promote-the-ready-wincon` (ep82756664 f97).",
        when=lambda c: c.select_context == _TO_ACTIVE and "accel_source" in c.roles
        and c.promote_target_kos,
        weight=50, status="testing"),
    Hypothesis(
        id="interpose-the-cheap-attacker-to-preserve-the-wincon",
        rationale="At a forced promote (TO_ACTIVE) with a higher-prize wincon on the Bench, promote a "
                  "cheaper body that can act instead (`promote_target_can_attack`, lower `card_prize_value`) "
                  "to soak the next hit for one prize and keep the finisher fresh — prize denial, since "
                  "feeding a 3-prize wincon when the opponent needs <=3 can hand them the game. HARD VETO "
                  "when the opponent needs only one prize (`opp_prizes_remaining < 2`: lead strongest). "
                  "Fires on any of three drivers: (a) `promote_target_hits_weakness` (favourable Weakness "
                  "trade); (b) an `accel_source` whose attack can fully power an underpowered benched "
                  "finisher (`bench_wincon_underpowered` + `basic_energy_in_deck`); (c) "
                  "`opp_has_played_gust` (tax a shown gust threat). Scores +50 vs `promote-the-ready-wincon` "
                  "(+40), so the sacrifice wins; additive with `promote-the-accelerator-for-the-ko` (+50) "
                  "when it can also KO this turn (ADR-0031).",
        when=lambda c: c.select_context == _TO_ACTIVE and not c.card_is_wincon
        and c.promote_target_can_attack and c.board.opp_prizes_remaining >= 2
        and c.board.bench_wincon_prize_value > c.card_prize_value
        and (c.promote_target_hits_weakness
             or ("accel_source" in c.roles and c.board.bench_wincon_underpowered
                 and c.board.basic_energy_in_deck)
             or c.board.opp_has_played_gust),
        weight=50, status="testing"),
    Hypothesis(
        id="promote-the-ready-wincon",
        rationale="On bringing up a new Active (TO_ACTIVE forced promote or SWITCH retreat pick), promote "
                  "the ready win-condition over a pre-evolution or staller. Fires per-option on the BEST "
                  "benched wincon (`is_best_promote_target`/`board.best_promote_slot`, e.g. the 3-Energy "
                  "Hero's-Cape copy over a bare one — ep83007714 f104 promote, f92 retreat), not a flat "
                  "board-level flag. Below `promote-the-accelerator-for-the-ko` (+50, ep82756664 f97).",
        when=lambda c: c.select_context in (_TO_ACTIVE, _SWITCH) and c.card_is_wincon
        and c.is_best_promote_target,
        weight=40, status="testing"),
    Hypothesis(
        id="promote-the-staller",
        rationale="When Active is KO'd and you can neither promote a powered wincon nor evolve a benched "
                  "pre-evolution into a ready attacker this turn, promote a disposable opener/wall "
                  "(Function Tag `opener`) instead of a bare pre-evolution — it stalls and keeps the "
                  "fragile pre-evolution safe. The evolve gate `evolve_to_ready_wincon_available` requires "
                  "enough Energy to attack post-evolve; a bare pre-evo would just expose a dead 0-Energy "
                  "wincon, so the staller wins even with payoff in hand (ep82753102 f120).",
        when=lambda c: c.select_context == _TO_ACTIVE and "opener" in c.tags
        and not c.board.evolve_to_ready_wincon_available and not c.board.bench_wincon_ready,
        weight=20, status="testing"),
]
