"""The `TurnLine` a planner family returns, its goal vocabulary, and the two module helpers that shape one.

Split out of `planner.py` so a family can build a line without importing the planner back."""
from __future__ import annotations


from dataclasses import dataclass


def _prune_none(v):
    """Convert an ``asdict``-ed engine Observation into the dict shape the LIVE obs has, so the Pilot's
    ``decide`` can be re-run on an intermediate SearchState. ``asdict`` keeps optional dataclass fields
    as ``None`` keys (e.g. ``option.playerIndex``), but the engine's live JSON OMITS them — the
    difference matters for ``option.get("playerIndex", yourIndex)``-style lookups, which otherwise read
    ``None`` and crash. Drops None-VALUED dict keys; KEEPS None list ELEMENTS (a facedown Active / a
    facedown prize slot is a meaningful ``None`` that carries the zone's count)."""
    if isinstance(v, dict):
        return {k: _prune_none(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [_prune_none(x) for x in v]
    return v

_PRIZE_AREA = 6                # AreaType.PRIZE — a hidden-zone pick: the sim's ids are predictions,
                               # so a recorded prize pick is policy-driven at replay (ADR-0037 stage 3)

def _rng_probe(cgapi, my_index: int, *, prize: bool):
    """Build ``saw(observation) -> bool``: did these logs consume engine RANDOMNESS on MY behalf?

    ONE rule, two consumers (#178). ``search_begin`` is seeded from `_seed_zones` with a predicted
    MULTISET for the hidden zones and the engine shuffles it into an order we never see. An outcome
    that turned on a card the ENGINE picked out of one of those zones is therefore not a fact about
    the position, for two INDEPENDENT reasons — and the rule below is worth its keep on either:

      1. **Epistemic, and it holds for every draw.** The order is our PREDICTION. In the real game
         nobody knows it either, so a line whose value depends on what came off the top is a guess
         about a hidden zone, however faithfully the engine repeats it.
      2. **Mechanical, and it is what makes a frame FLAP.** A shuffle DURING the line — the
         Professor's-Research class, shuffle your hand in and draw — is not reproducible: measured
         on ml f24, one Pilot re-running the identical sim drew a different 8 cards every call.

    Do not narrow this to (2). ``search_begin``'s OWN seeding shuffle *is* reproducible given
    identical inputs (`docs/pyeng/determinism.md` §4, re-measured 2026-07-27: identical draws across
    processes and across intervening searches), so a rule keyed on reproducibility alone would let a
    pre-shuffle draw through — and reproducing a guess does not make it knowledge.

    Counts, for ``playerIndex == my_index`` (their reveals land after my turn has passed):

      * ``DRAW`` — off the deck top;
      * ``MOVE_CARD`` ``DECK``→``LOOKING`` (a top-N peek) or ``DECK``→``DISCARD`` (a mill);
      * ``MOVE_CARD`` out of ``PRIZE`` — only when ``prize=True``. A face-down prize's id is our own
        prediction, which can change a resulting BOARD; it cannot change a WIN VERDICT, which is
        invariant to which prize is taken (ADR-0050, `_engine_confirms_win`).

    Plus any ``COIN`` flip, whoever flipped it.

    NOT counted, measured 2026-07-27: a bare ``SHUFFLE`` (every seeded search shuffles, and a shuffle
    nobody then looks at changes nothing) and a ``DECK``→``HAND``/field **search** (the deck is
    revealed and WE pick by identity, so the order decides nothing — all the hidden-zone traffic the
    ml f26/f48 tutor lines have). Absent under a backend that emits no such logs, where the probe
    finds nothing and behavior is unchanged."""
    _logs = getattr(cgapi, "LogType", None)
    coin_t = getattr(_logs, "COIN", None)
    draw_t = getattr(_logs, "DRAW", None)
    move_t = getattr(_logs, "MOVE_CARD", None)
    _a = getattr(cgapi, "AreaType", None)
    deck_a, prize_a = getattr(_a, "DECK", None), getattr(_a, "PRIZE", None)
    positional = {(int(deck_a), int(x))
                  for x in (getattr(_a, "LOOKING", None), getattr(_a, "DISCARD", None))
                  if deck_a is not None and x is not None}

    def saw(ob) -> bool:
        for lg in (getattr(ob, "logs", None) or ()):
            t = getattr(lg, "type", None)
            if coin_t is not None and t == coin_t:
                return True
            if getattr(lg, "playerIndex", None) != my_index:
                continue
            if draw_t is not None and t == draw_t:
                return True
            if move_t is None or t != move_t:
                continue
            fr, to = getattr(lg, "fromArea", None), getattr(lg, "toArea", None)
            if fr is None:
                continue
            if prize and prize_a is not None and int(fr) == int(prize_a):
                return True
            if to is not None and (int(fr), int(to)) in positional:
                return True
        return False

    return saw

#
# Rare Candy (Item, SVI 191) — the Basic→Stage-2 evolve SKIP — is matched by its `rare_candy` Function Tag
# (`common.playability.RARE_CANDY_TAG`), so there is no constant here any more. There WAS one, a bare
# `_RARE_CANDY_ID = 1079` justified as "behaviorally unique, single card, no other consumer". Issue #288's
# playability gate is the second consumer and asks about a card in HAND OR DECK, which no option-id
# comparison answers — so the justification expired and ADR-0006's rule applies. Card text verified at
# data/EN_Card_Data.csv id 1079.
# ═══ WP1/WP5 — Stage-1 fetch CLOSURE for the Gamble Rung (hypergeometric-fetch-closure spec) ═══════
# The tutor/recycle PREDICATES a drawn card needs to enable a one-short KO (type-lock, source zone,
# target class) live in the card REPRESENTATION — `card_effects.json` FETCH clauses (ADR-0032),
# authored in `tools/meta_tracker/effect_overrides.json` and verified against engine card text, so the
# closure NEVER parses card text (Round 11 ruling). Fighting Gong's generic `tutor_energy` tag can't
# carry its {F}-lock; its `{"kind":"fetch","target":"basic_energy","energy_type":6}` clause does. The
# consumers are `_fetch_reaches_slot` (energy, WP1) and `_fetch_reaches_pokemon` (Pokémon, WP5).
_GOAL_LINE = {"ko_on_path": {"ko_for_prizes", "ko_key_threat"},   # the directed goal → the candidate line
              "trade": {"ko_for_prizes"}}                # goals that serve it. `survive` had exactly one —
              # `stabilize_then_ko`, deleted by POC-T4/5 — and is dropped rather than left mapping to the
              # empty set, so `_gameplan_goal_bonus` cannot silently pay 0 for a goal it looks like it
              # serves. `develop`/`close` were never here: they defer to the composer.

@dataclass
class TurnLine:
    """A committed sequence of this-turn actions achieving a **Turn Goal**: the option index(es) to
    take at THIS decision (``next_step``), the ``goal`` it serves (for legibility / telemetry
    clustering), the leaf-eval ``value`` of the resulting board, and a one-line ``rationale``. A
    multi-step line surfaces one step per decision as the engine re-opens the turn menu.

    ``goal == "win"`` is the Lethal Solver's lock (ADR-0030/0037) — the ONE unified line type covers
    both regimes, and telemetry serialises a win line under the wire-compatible ``lethal`` key. Win
    lines carry ``kind`` (``direct`` / ``unlock`` / ``evolve``, so a correction can cluster by *how*
    the win was reached) and ``verified`` — the engine backstop's verdict on the lock
    (``lethal_verify``): True = the engine's own search confirmed the win; None = not checked
    (switch off / unverifiable kind / engine unavailable). A False never rides here — a refuted
    candidate is dropped, not locked.

    ``ranked_by`` records how a HEURISTIC committed line was VALUED: ``"composer"`` = the sequence
    composer's end-state score (POC-T4/5); None = the closed-form leaf. Its third value ``"engine"``
    is GONE with the runtime rollout that produced it — `_commit_best` no longer forward-sims
    candidates and `planner_engine_rank` no longer exists. ``diverged`` likewise recorded that
    ranking overriding the closed-form pick and is now always False for pool lines. Win lines never
    enter ranking (they preempt it).

    ``kind == "sequence"`` marks a composer line: its ``next_step`` is the FIRST action of a
    multi-action sequence that was scored whole, and the rest is deliberately not locked — the beam
    is re-run on the next decision rather than replayed, because only the win rung's engine verify
    earns a lock."""
    next_step: list
    goal: str = ""
    value: float = 0.0
    rationale: str = ""
    ranked_by: str | None = None
    diverged: bool = False
    kind: str = ""
    verified: bool | None = None

_WEIGHTED_GOALS = ("ko_for_prizes", "ko_key_threat")   # the rungs whose prize term #175 weights

def _composed_rank(cand):
    """Order composed KO candidates by EXPECTED prizes (ADR-0074 decision 4, #175) — a 2-prize line
    that is 40% to whiff must lose to a certain 1-prize line, which raw prize count cannot express.
    Survival stays the tiebreak below it."""
    prizes, survives, p = cand
    return (prizes * p, survives)
