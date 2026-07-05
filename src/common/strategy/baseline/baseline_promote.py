"""BASELINE cluster: PROMOTE — which benched Pokémon to bring up after a Knock Out, at a TO_ACTIVE
select (ADR-0025). Ready wincon first; otherwise a disposable staller over a bare pre-evolution.
Pure data, no Mixin.
"""
from common.strategy.context import _SWITCH, _TO_ACTIVE
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="dont-promote-onto-their-path",
        rationale="Tier-3 Path Denial (ADR-0040): this promote/switch candidate sits on the "
                  "opponent's cheapest Prize Path — bringing it to the Active Spot walks it into "
                  "exactly the KO they want next ('force 7' means the body they need stays hard to "
                  "reach). A small brake below every positive promote driver: interpose (+50) and "
                  "the ready-wincon promote (+40) still win when their logic applies — this only "
                  "tips otherwise-close picks toward the off-path body.",
        when=lambda c: c.promote_target_on_their_path,
        weight=-8, status="testing"),
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
        id="dont-promote-into-their-prize-reach",
        rationale="At a forced promote (TO_ACTIVE), soften promoting a win-condition whose OWN prize "
                  "value covers the opponent's remaining prizes (`card_prize_value >= "
                  "opp_prizes_remaining`, e.g. a 3-prize Mega ex vs an opponent at 2-3) — KOing it "
                  "hands them the game in one hit, so the wincon should stay benched while a 1-prize "
                  "body soaks (make them take six individual prizes, not two Megas). The per-option "
                  "penalty complement of `interpose-the-cheap-attacker-to-preserve-the-wincon` (+50 on "
                  "the cheap body): that rule needs one of its three drivers; this one bites whenever "
                  "the prize math alone is fatal, netting `promote-the-ready-wincon` (+40) down to +20 "
                  "so ANY viable alternative (interpose +50, staller +20) outranks the fatal promote. "
                  "Stands down when the promoted wincon can itself KO right away "
                  "(`promote_target_kos` — trading KOs while ahead on the exchange is fine), when the "
                  "opponent needs only ONE prize (any KO wins for them — lead the strongest body), and "
                  "when we're CLOSING (my_prizes_remaining <= 2: exposure is how you finish).",
        when=lambda c: c.select_context == _TO_ACTIVE and c.card_is_wincon
        and c.card_prize_value >= c.board.opp_prizes_remaining >= 2
        and not c.promote_target_kos and c.board.my_prizes_remaining > 2,
        weight=-20, status="assumed"),
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
