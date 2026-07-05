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
                  "other snipe priority.",
        when=lambda c: c.select_context == _DAMAGE and c.target_kos,
        weight=60, status="testing"),
    Hypothesis(
        id="snipe-the-top-threat",
        rationale="When no target can be KO'd, hit the biggest threat by `board.strongest_threat_rank` "
                  "(own or forward-evolution damage) — sees already-evolved ex/Mega ex attackers by "
                  "printed damage, prefers the more-developed body on a shared line, and boosts lines "
                  "that certainly reach a hand-size attacker, so it never pokes a low-HP support mon. "
                  "Stands down on a KO target (that's snipe-for-the-ko).",
        when=lambda c: c.select_context == _DAMAGE and c.target_is_top_threat and not c.target_kos,
        weight=30, status="testing"),
    Hypothesis(
        id="snipe-the-threat",
        rationale="A benched Pokémon already carrying Energy is closest to attacking, so sniping it "
                  "denies the opponent their next attacker rather than poking a bare benchsitter. "
                  "Co-fires with `snipe-the-top-threat` (`_target_threat_rank` already tiers energized "
                  "targets above bare ones) as the legible imminence signal on top of it.",
        when=lambda c: c.select_context == _DAMAGE and c.target_is_threat,
        weight=20, status="testing"),
    Hypothesis(
        id="snipe-on-the-path",
        rationale="Tier-3 Prize Path (ADR-0040): this target sits on my cheapest route to my remaining "
                  "prizes, so its damage/KO advances the MATCH win, not just the board. A path-economy "
                  "axis stacking with the threat rank — a low-threat 1-prize body can still be the "
                  "right path member ('KO one Mega + snipe 3 smalls'). Silent when the path is unknown "
                  "(runs through bodies not yet in play) or the `objectives_path` switch is off.",
        when=lambda c: c.select_context == _DAMAGE and c.target_on_path,
        weight=12, status="testing"),
    # NOTE: flat `snipe-the-weakest`/`snipe-the-evolving-threat`/`snipe-the-strongest-evolving-threat`
    # RETIRED — `snipe-the-top-threat` subsumes all 3 (round-b7e483a bad-target blunders). `EVOLVING_THREAT_DMG` floor stays (Read consumer may still ref it).

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
