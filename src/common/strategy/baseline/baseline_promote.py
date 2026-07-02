"""BASELINE cluster: PROMOTE — which benched Pokémon to bring up after a Knock Out, at a TO_ACTIVE
select (ADR-0025). Ready wincon first; otherwise a disposable staller over a bare pre-evolution.
Pure data, no Mixin.
"""
from common.strategy.context import _SWITCH, _TO_ACTIVE
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="promote-the-accelerator-for-the-ko",
        rationale="When your Active is Knocked Out and a benched ACCELERATOR (Role `accel_source`, e.g. "
                  "Cinderace whose Turbo Flare searches Energy onto the Bench) can itself Knock Out the "
                  "opponent's Active this turn (`promote_target_kos`), promote IT — not the win-condition. "
                  "You take the prize from the front AND its attack loads the benched win-condition for "
                  "next turn, leaving the wincon a fresh, fully-built attacker rather than spending it on "
                  "a KO an accelerator could take. Ranks above `promote-the-ready-wincon` (which would "
                  "burn the wincon on the same KO) — the forward-search promote (ep82756664 f97).",
        when=lambda c: c.select_context == _TO_ACTIVE and "accel_source" in c.roles
        and c.promote_target_kos,
        weight=50, status="testing"),
    Hypothesis(
        id="interpose-the-cheap-attacker-to-preserve-the-wincon",
        rationale="At a forced promote after a Knock Out (TO_ACTIVE), when a benched higher-prize "
                  "win-condition is available, DON'T lead with it — promote a CHEAPER body that can act "
                  "(`promote_target_can_attack`, `card_prize_value` below the benched wincon's) to soak "
                  "the next hit for one prize and keep the multi-prize finisher fresh on the Bench. Prize "
                  "denial: feeding a 3-prize Mega Starmie ex when the opponent needs <=3 can hand them the "
                  "game outright, whereas a 1-prize Cinderace costs them a whole KO to take a single prize "
                  "— then you promote the fresh, fully-built finisher. HARD VETO when the opponent needs "
                  "only ONE prize (`opp_prizes_remaining < 2`): any KO wins for them then, so a sacrifice "
                  "just gives it away — lead with your strongest body. Fires on any of three drivers: "
                  "(a) `promote_target_hits_weakness` — the cheap body strikes the opponent's Active on its "
                  "Weakness (x2 chip, Cinderace's Fire into a Fire-weak Archaludon ex / Duraludon), a "
                  "favourable trade; (b) an accelerator (`accel_source`) whose attack loads the Bench while "
                  "the benched finisher isn't fully powered (`bench_wincon_underpowered`) and Basic Energy "
                  "remains to fetch (`basic_energy_in_deck`) — promoting it powers the finisher to full off "
                  "the Bench, which promoting the finisher directly (one attach/turn) can't; (c) "
                  "`opp_has_played_gust` — the opponent has shown a Boss's Orders-style gust, so they can "
                  "drag the benched finisher out anyway; interpose to tax that gust. Scores +50 on the "
                  "cheap body vs `promote-the-ready-wincon` (+40) on the wincon, so the sacrifice is chosen; "
                  "additive with `promote-the-accelerator-for-the-ko` (+50) when the cheap body can also KO "
                  "this turn (ADR-0031 prize-economy at a promote).",
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
        rationale="When you bring up a new Active — a forced promote after a Knock Out (TO_ACTIVE) OR "
                  "the new-Active pick when you retreat (SWITCH) — promote the READY win-condition, "
                  "your live attacker, rather than a pre-evolution or a staller. Fires per-option on "
                  "the BEST benched wincon to promote (`is_best_promote_target` == the most-built "
                  "ready wincon, `board.best_promote_slot`): so among several Mega Starmie ex it picks "
                  "the 3-Energy, Hero's-Cape one that can KO — not a bare 0-Energy copy or whichever "
                  "sits at bench slot 0 (ep83007714 f104 promote, f92 retreat). (Previously read a "
                  "board-level 'some wincon is ready' flag at TO_ACTIVE only, so it rewarded every "
                  "wincon option equally and never fired at SWITCH.) Below "
                  "`promote-the-accelerator-for-the-ko` (+50), which promotes a KO-capable accelerator "
                  "over the wincon to keep the wincon fresh (ep82756664 f97).",
        when=lambda c: c.select_context in (_TO_ACTIVE, _SWITCH) and c.card_is_wincon
        and c.is_best_promote_target,
        weight=40, status="testing"),
    Hypothesis(
        id="promote-the-staller",
        rationale="When your Active is Knocked Out and you can NEITHER promote a powered win-condition "
                  "NOR evolve a benched pre-evolution into a READY attacker this turn, promote a "
                  "disposable opener / wall (Function Tag `opener`, e.g. Cinderace) instead of a bare "
                  "pre-evolution — it stalls, keeps the fragile pre-evolution safe on the Bench, can "
                  "be retreated for free once you draw the evolution, and can attack if you find "
                  "Energy. The evolve gate is `evolve_to_ready_wincon_available` (payoff in hand AND a "
                  "pre-evolution with enough Energy that the evolved attacker can attack): with only a "
                  "BARE pre-evolution, evolving it just exposes a dead 0-Energy wincon, so the staller "
                  "wins even though the payoff is in hand (ep82753102 f120).",
        when=lambda c: c.select_context == _TO_ACTIVE and "opener" in c.tags
        and not c.board.evolve_to_ready_wincon_available and not c.board.bench_wincon_ready,
        weight=20, status="testing"),
]
