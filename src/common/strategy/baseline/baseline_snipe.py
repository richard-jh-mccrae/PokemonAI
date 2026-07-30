"""BASELINE cluster: SNIPE — the COUNTER-placement selects (ADR-0025).

Since ADR-0085 (Issue #188) this module owns only the counter contexts: the DAMAGE_COUNTER_ANY(14)
"place a counter in any way you like" spread placement (Phantom Dive / Munkidori —
`place-counter-to-convert`), plus the counter-mover's SOURCE(16) and AMOUNT(40) picks. The DAMAGE(15)
bench-snipe target pick that used to live here is now decided by `common/snipe_relevance.py`; see the
note in `HYPOTHESES` for what was deleted and why. Pure data, no Mixin.

`EVOLVING_THREAT_DMG` was removed with the rungs — the surviving reader is
`common/strategy/context.py`'s own `_EVOLVING_THREAT_DMG`, which the Snipe Relevance forward leg
reaches through `target_is_strongest_forward`.
"""
from common.strategy.context import (_DAMAGE_COUNTER, _DAMAGE_COUNTER_ANY,
                                     _REMOVE_DAMAGE_COUNTER, _REMOVE_DAMAGE_COUNTER_COUNT)
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    # --- The SIX DAMAGE(15) target rungs that used to live here are DELETED (ADR-0085, Issue #188).
    # `snipe-for-the-ko` (60), `snipe-the-evolving-threat` (45), `snipe-the-forced-promotion` (40),
    # `snipe-the-top-threat` (30), `snipe-the-threat` (20) and `snipe-on-the-path` (12) were an
    # ADDITIVE stack, and the stack itself was the defect: bonuses firing on DIFFERENT bodies summed
    # and out-voted a free prize (30 + 40 + 45 = 115 on an un-KO-able Grookey vs 60 on the KO-able
    # Applin, ms 82754241 f45), which is why five of the six carried a hand-written stand-down clause
    # against `snipe_ko_available` and two more against `evolving_wincon_on_bench`. Every such clause
    # is a guard bolted on to stop the sum, not a statement about the board.
    #
    # `common/snipe_relevance.py` replaces all six with ONE `[0,1]` scalar under hard gates —
    # `relevance = tera_veto (x) (their_plan * my_route)` — where the ordering is a PRODUCT of two
    # conjunctive sides, so nothing sums and no stand-down clause is needed. `snipe-for-the-ko` lives
    # on as the structural `Pilot._snipe_ko_dominator` (KO_SCORE-class), OUTSIDE the scalar, because a
    # free prize is not a graded preference.
    #
    # Deleted, not suppressed (#136 standing directive 1). `snipe_relevance` therefore ships ON and
    # OFF is documented DEGRADED MODE, never a rollback — the `attach_value` / `evolve_value` /
    # `promote_retreat_value` precedent. The THREE counter rungs below are out of scope (decision 5)
    # and untouched: they own different select contexts (13/14/16/40), not the DAMAGE(15) pick.

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
