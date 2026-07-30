"""BASELINE cluster: SNIPE — choosing WHICH opponent Pokémon to damage/target (ADR-0025).

Owns the two adjacent bench-targeting decision-contexts: the DAMAGE(15) bench-snipe (energized threat >
evolving threat > weakest, guarded so they never double-count) AND the DAMAGE_COUNTER_ANY(14) "place a
counter in any way you like" spread placement (Phantom Dive / Munkidori — `place-counter-to-convert`).
Pure data, no Mixin. `EVOLVING_THREAT_DMG` (the line-becomes-an-attacker floor) lives here because only
the snipe rules read it.
"""
from common.strategy.context import (_DAMAGE, _DAMAGE_COUNTER, _DAMAGE_COUNTER_ANY,
                                     _REMOVE_DAMAGE_COUNTER, _REMOVE_DAMAGE_COUNTER_COUNT)
from common.strategy.strategy import Hypothesis

# Evolution line "becomes an attacker" once it can OHKO a median body (median HP = 100; 100 is
# ~p76 of damaging attacks). Tunable seed for `snipe-the-evolving-threat` (ADR-0020, docs/rules.md).
EVOLVING_THREAT_DMG = 100

HYPOTHESES = [
    # --- unified threat order (ADR-0020 follow-up): bench KO = PRIZE; else snipe biggest attacker.
    # Supersedes 4 flat priorities below (kept back-compat) — `_target_threat_rank` sees evolved ex + hand-size lines, never picks low-HP SUPPORT. ---
    Hypothesis(
        id="snipe-for-the-ko",
        rationale="If a damage-select's snipe rider KOs the target (remaining HP <= rider, which ignores "
                  "Weakness/Resistance), take it — a free prize beats any positional snipe. Outranks every "
                  "other snipe priority: each positional rung now stands down whenever ANY KO is on offer "
                  "(`board.snipe_ko_available`). Gating each rung on its own `target_kos` was not enough — "
                  "the bonuses fire on a DIFFERENT body and their SUM out-voted the prize (top-threat 30 + "
                  "forced-promotion 40 + evolving-threat 45 = 115 on an un-KO-able Grookey, vs 60 on the "
                  "KO-able Applin: ms 82754241 f45, and 97-vs-72 in 82753102 f63). A positional weight must "
                  "never override a KO, and neither may the sum of three.",
        when=lambda c: not c.snipe_relevance_armed and c.select_context == _DAMAGE and c.target_kos,
        weight=60, status="testing"),
    # NOTE: `dont-snipe-a-benched-tera` (−60) RETIRED — a benched Tera takes NO damage from attacks at
    # all (`CardStat.tera`; rules.md §185), so sniping one is ALWAYS strictly wasted. That is a CARD
    # FACT, not a preference, and it must never compete on points: as a tunable positional weight
    # (`status="assumed"`) it held only by a 10-point margin (top-threat 30 + threat 20 = 50 < 60) and
    # was DEFEATED once `snipe-on-the-path` (+12) also fired. It now lives in the Tactical layer as the
    # structural `Pilot._snipe_tera_veto` (KO_SCORE-class), which dominates any positional stack, so no
    # weight-tune and no future snipe rung can reintroduce the misplay (ms 81785223 f45: Wellspring Mask
    # Ogerpon ex). The Tera is ordered LAST but still selectable when it is the ONLY bench target.
    Hypothesis(
        id="snipe-the-top-threat",
        rationale="When no target can be KO'd, hit the biggest threat by `board.strongest_threat_rank` "
                  "(own or forward-evolution damage) — sees already-evolved ex/Mega ex attackers by "
                  "printed damage, prefers the more-developed body on a shared line, and boosts lines "
                  "that certainly reach a hand-size attacker, so it never pokes a low-HP support mon. "
                  "Stands down on a KO target (that's snipe-for-the-ko).",
        when=lambda c: not c.snipe_relevance_armed and (c.select_context == _DAMAGE and c.target_is_top_threat and not c.board.snipe_ko_available
                        and not c.target_prize_redundant       # ADR-0044: don't chip a body I don't need
                        and not c.target_promotion_mirage      # ADR-0044: nor a non-promotion imminence mirage
                        and not (c.board.evolving_wincon_on_bench and not c.target_is_strongest_forward)),
                                                               # stand down off the developing higher-prize wincon
        weight=30, status="testing"),
    Hypothesis(
        id="snipe-the-threat",
        rationale="A benched Pokémon already carrying Energy is closest to attacking, so sniping it "
                  "denies the opponent their next attacker rather than poking a bare benchsitter. "
                  "Stands down on a KO target — every positional rung must, or their SUM out-votes the "
                  "free prize (ms 82754241 f45 / 82753102 f63). "
                  "Co-fires with `snipe-the-top-threat` (`_target_threat_rank` already tiers energized "
                  "targets above bare ones) as the legible imminence signal on top of it.",
        when=lambda c: not c.snipe_relevance_armed and (c.select_context == _DAMAGE and c.target_is_threat and not c.board.snipe_ko_available
                        and not c.target_prize_redundant       # ADR-0044: don't chip a body I don't need
                        and not c.target_promotion_mirage      # ADR-0044: nor a non-promotion imminence mirage
                        and not (c.board.evolving_wincon_on_bench and not c.target_is_strongest_forward)),
                                                               # stand down off the developing higher-prize wincon
        weight=20, status="testing"),
    Hypothesis(
        id="snipe-on-the-path",
        rationale="Tier-3 Prize Path (ADR-0040): this target sits on my cheapest route to my remaining "
                  "prizes, so its damage/KO advances the MATCH win, not just the board. A path-economy "
                  "axis stacking with the threat rank — a low-threat 1-prize body can still be the "
                  "right path member ('KO one Mega + snipe 3 smalls'). Stands down on a KO target — the path "
                  "axis must not stack onto the others past `snipe-for-the-ko`. Silent when the path is unknown "
                  "(runs through bodies not yet in play) or the `objectives_path` switch is off.",
        when=lambda c: not c.snipe_relevance_armed and c.select_context == _DAMAGE and c.target_on_path and not c.board.snipe_ko_available,
        weight=12, status="testing"),
    Hypothesis(
        id="snipe-the-forced-promotion",
        rationale="ADR-0044 Forced-Promotion Read: the opponent's Active is dead, so a promotion is "
                  "FORCED next turn — they bring up their highest-value READY attacker (the "
                  "win-condition, energy-independent), not the energized bench-sitter that merely "
                  "carries Energy now. Pre-chip that body this turn. Overrides the energized-imminence "
                  "tier for this pick (its mirages are suppressed); silent while their Active is alive.",
        when=lambda c: not c.snipe_relevance_armed and (c.select_context == _DAMAGE and c.target_is_forced_promotion
                        and not c.board.snipe_ko_available
                        and not (c.board.evolving_wincon_on_bench and not c.target_is_strongest_forward)),
                                                               # stand down off the developing higher-prize wincon
        weight=40, status="testing"),
    Hypothesis(
        id="snipe-the-evolving-threat",
        rationale="Chip a benched PRE-EVOLUTION whose forward evolution becomes a win-condition-class "
                  "attacker (`target_is_strongest_forward`: `forward_max_damage` strongest on the Bench "
                  "AND >= EVOLVING_THREAT_DMG) — damage counters CARRY THROUGH evolution (rules.md), so "
                  "pre-chipping Riolu (→ Mega Lucario ex 270) softens the eventual wall a turn early. "
                  "RESTORED after the round-b7e483a retirement wrongly assumed `snipe-the-top-threat` "
                  "subsumed it: `_target_threat_rank` lands `snipe-the-top-threat` (+30) / "
                  "`snipe-the-forced-promotion` (+40) on the CURRENT bulky body (Hariyama/Lunatone, 0 "
                  "forward) while the developing wincon pre-evo scored 0 (ms corrections f75/f47, human "
                  "domain-expert, 4 games). GATED by `not target_forward_form_in_play` — the ADR-0044 "
                  "discriminator: it stands down when the opponent ALREADY has the evolved wincon on the "
                  "board (chip the ready form directly, not the redundant pre-evo — the exact case in "
                  "test_45/test_107 that a naive restore regressed), and fires only when the wincon is "
                  "still developing (form absent). +45 beats the forced-promotion pick where it fires. "
                  "Stands down on a KO target (`snipe-for-the-ko` +60 owns that). SEED; ladder-tuned.",
        when=lambda c: not c.snipe_relevance_armed and (c.select_context == _DAMAGE and c.target_is_strongest_forward
                        and not c.target_forward_form_in_play and not c.board.snipe_ko_available),
        weight=45, status="assumed"),
    # NOTE: flat `snipe-the-weakest`/`snipe-the-strongest-evolving-threat` RETIRED — `snipe-the-top-threat`
    # subsumes them (round-b7e483a). `snipe-the-evolving-threat` RESTORED 2026-07-09 with the
    # `target_forward_form_in_play` discriminator (it was NOT subsumed — the forward-wincon pre-evo scored
    # 0). `EVOLVING_THREAT_DMG` floor stays.

    # --- DAMAGE_COUNTER_ANY: distribute a "put N counters in any way you like" spread (Phantom Dive)
    # or a counter-mover's "onto opponent" target (Munkidori). Distinct engine context (14) from the
    # snipe DAMAGE(15) select — one counter (10) per select, budget in `remainDamageCounter`. ---
    Hypothesis(
        id="place-counter-to-convert",
        rationale="At a DAMAGE_COUNTER_ANY spread-placement select (Phantom Dive's 6 counters, one per "
                  "select; Munkidori Adrena-Brain's 'onto opponent' target), put the counter on the "
                  "knapsack-optimal opponent Pokémon (`board.best_counter_slot`): when the remaining "
                  "counters can complete one or more KOs, finish the closest-to-dying member of the "
                  "highest-prize KO set (maximizing this-turn prizes); else pre-load the lowest-HP "
                  "target (concentrate toward a future KO). The engine re-asks per counter with the "
                  "updated board, so the single-best-slot pick IS the correct sequential greedy. The "
                  "snipe cluster is DAMAGE(15)-only, so without this the ctx-14 placement is unguided. "
                  "Also serves a counter-mover's ADD-to-opponent target (DAMAGE_COUNTER 13, Munkidori).",
        when=lambda c: (c.select_context in (_DAMAGE_COUNTER_ANY, _DAMAGE_COUNTER)
                        and c.counter_is_best_placement),
        weight=30, status="assumed"),

    # --- Counter-mover (Munkidori Adrena-Brain: move <=3 counters ours->theirs). The ADD target is
    # `place-counter-to-convert` above (ctx 13); these two own the SOURCE (ctx 16) + AMOUNT (ctx 40). ---
    Hypothesis(
        id="move-counters-off-the-damaged",
        rationale="At a REMOVE_DAMAGE_COUNTER source select (Munkidori's 'from 1 of your Pokémon'), pull "
                  "the counters off OUR most-damaged body (`board.best_counter_source_slot`) — the biggest "
                  "heal, and the deck's reverse-heal that wins the mirror (peel residual Phantom Dive / "
                  "Risky-Ruins chip off the win-con line while the same move chips the opponent). Removing "
                  "counters IS a heal, so the source pick is where the healing lands.",
        when=lambda c: c.select_context == _REMOVE_DAMAGE_COUNTER and c.counter_is_source_pick,
        weight=30, status="assumed"),
    Hypothesis(
        id="move-max-counters",
        rationale="At a REMOVE_DAMAGE_COUNTER_COUNT select, move the MOST counters offered "
                  "(`is_max_counter_move`) — max damage relocated onto the opponent AND max heal off our "
                  "own body. The counter-mover is once/turn, so there is no reason to under-move.",
        when=lambda c: c.select_context == _REMOVE_DAMAGE_COUNTER_COUNT and c.is_max_counter_move,
        weight=30, status="assumed"),
]
