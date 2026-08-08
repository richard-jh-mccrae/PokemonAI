"""BASELINE cluster: SNIPE — the COUNTER-placement selects only (ADR-0025, ADR-0085): contexts 13/14
(placement) plus the counter-mover's SOURCE(16) and AMOUNT(40). The DAMAGE(15) bench-snipe target
pick is `common/snipe_relevance.py`'s. Pure data, no Mixin."""
from common.strategy.context import (_DAMAGE_COUNTER, _DAMAGE_COUNTER_ANY,
                                     _REMOVE_DAMAGE_COUNTER, _REMOVE_DAMAGE_COUNTER_COUNT)
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    # The six DAMAGE(15) target rungs are DELETED (ADR-0085, Issue #188; fold map in
    # `tools/rung_registry.py`) — `common/snipe_relevance.py` replaces that additive stack, and ships ON.

    # DAMAGE_COUNTER_ANY (14): a "put N counters in any way you like" spread, or a counter-mover's
    # "onto opponent" target. One counter (10) per select; the budget is `remainDamageCounter`.
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

    # Counter-mover (Munkidori Adrena-Brain): these two own the SOURCE (16) and AMOUNT (40) picks.
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
