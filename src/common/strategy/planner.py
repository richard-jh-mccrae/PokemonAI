"""The Turn Planner (ADR-0031/0037): the eager whole-turn optimizer and the Pilot's ONE planning
entry point — the **Lethal Solver is its sound top rung**.

A deck-agnostic Pilot Mixin that runs at the start of my turn. ``plan_turn`` runs the Goal Ladder:

    locked-line replay -> win rung -> the closed-form KO pool -> gamble rung -> **the composer**

The **win rung** is first (the Lethal Solver, ADR-0030 — sound, engine-verified, preempting every
heuristic goal); the KO pool and the Gamble rung generate closed-form enabling lines by working
backward from a prioritized set of **Turn Goals**; and the bottom rung is `common.composer`, which
decides every MAIN single-pick frame the rungs above declined. See
``docs/adr/0037-lethal-solver-is-the-turn-planners-top-rung.md`` and the *Turn Planner* / *Turn
Goal* / *Turn Line* / *Lethal Solver* terms in ``common/CONTEXT.md``.

**The composer is the MAIN decider** (POC-T4/5, Issue #386; ADR-0092 §4-T4). It is not "below the
tuned Hypothesis scoring" — it REPLACES the greedy argmax at MAIN, which is why the heal, Tool-equip,
gust whether-to-play, draw/dig economy, hand-disruption, Stadium and `retreat-to-wall-the-line` rung
families were deleted in the same change and why `stabilize-then-KO` and the `forgo-KO` gate are gone
from this module. A rung asserting a preference the leaf can compute by differencing end states is a
second opinion about the same board, and ADR-0092 decision 4 allows exactly one.

**Two soundness regimes, one module.** The win rung locks only a GUARANTEED win: min-bound damage
floors, worst-case coins, and the `_engine_confirms_win` verdict-driver (refute drops the candidate;
an unreachable verdict keeps the sound closed-form lock). Everything below it is **heuristic** — it
SCORES rather than proves — so the win rung stays preempting and a scored line can never override a
verified one. That ordering is Issue #263's ruling and its reason is asymmetric cost: a missed win
costs a turn, a phantom win costs the match.

**Layer-on-top (ADR-0031 decision 6) applies to the closed-form KO pool, not to the composer.** The
pool empties whenever the tuned menu already reaches a KO, so it only ever adds a line greedy would
MISS. The composer has no such gate by design: a decider that fires only where a heuristic says
greedy is unsure would leave greedy deciding everywhere else, which is the thing being replaced.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from common import composer, needs, playability
from common.state_model import StateModel
from common.state_value import WIN_PRIZES, state_value
from common.strategy.context import (_ACTIVE, _ATTACH, _ATTACK, _ATTACKER_ROLES, _BASIC_ENERGY, _BENCH,
                                     _COIN_HEAD, _END, _EVOLVE, _MAIN, _PLAY, _RETREAT, _SPECIAL_ENERGY,
                                     _TO_HAND, KO_SCORE)


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

# Leaf-eval term weights (ADR-0031 decision 4). Prizes KO_SCORE-weighted + DOMINANT — positional terms
# sum below one prize, never outrank real KO (hard-rung invariant, decision 3). Automatic Value Model (ADR-0007) replaces later.
_PLANNER_SURVIVAL_W = 50.0     # my Active survives predicted Incoming after the line (full turn)
_PLANNER_THREAT_W = 0.1        # per-point value of threat magnitude removed by the KO …
_PLANNER_THREAT_CAP = 100.0    # … capped, so a big threat still can't rival a prize
_PLANNER_DEV_W = 1.0           # development left on my end-of-turn board (engine-rank phase: bodies
_PLANNER_DEV_CAP = 100.0       # + attached Energy, `_board_development`) … capped below a prize
_COMPOSER_GAP_K = 8           # composer rung: how many coverage-gap reasons ride the sparse `composer`
                              # telemetry block. A cap, not a filter — the count is in `stats`, so a
                              # truncated list can never read as "that was all of them". Sized to keep a
                              # per-decision record readable; the exhaustive list is the lab's job
                              # (`tools/train/composer_lab.py`), which replays the same frames offline.


def _tied_first_steps(result, chosen) -> list:
    """Menu indices whose best sequence ties ``chosen``'s score — the composer having NO OPINION
    about which action to take first. **ADR-0131 decision 2.**

    Compared at `composer._SCORE_PLACES`, the same float-noise floor `selection_key` uses, so this
    reads "tied" exactly where that key does and the two cannot drift apart into a decision that is
    a tie to one and not to the other.

    **Why a tie must not be broken by the composer.** `selection_key` breaks it — by Worth, then by
    a stable card-id sort — and that is right when the tie is between members of one Option
    Equivalence Class, which is a tie about nothing. It is wrong when the tie is between genuinely
    different actions, because there the composer is reporting *"these end the turn in the same
    place"*, which is not the same claim as *"take this one"*. `sound_rules.
    information-before-commitment` is the standing ruling on what to do instead, and it is explicit
    that this case exists and is not reachable from the end state: *"both orders reach the same end
    state, so no function of that state separates them (ADR-0095 decision 3)."* A composer is a
    function of the end state.

    Measured on that ADR's own anchor frame, `ms_information_before_commitment_f11`: the composer
    prices SEVEN of the ten options at exactly 0.0 — the ruled Pokégear 3.0, both Crushing Hammers,
    both Tools, an attach and End — and `selection_key` hands the turn to the attach. The human
    ruled the dig, `_finish_turn_last` sequences the dig first, and the composer's own numbers say
    it has no view either way.

    So this is the FOURTH defer, and the same kind as the three the caller already documents: a
    refusal to guess. The tuned scoring keeps the turn, which is where the structural sequencer
    lives. Equivalence-class ties are unaffected — the ladder picks a class member too, and a tie
    about nothing stays a tie about nothing whichever mechanism resolves it.
    """
    from common.composer import _SCORE_PLACES
    if not getattr(result, "candidates", ()):
        return []
    key = round(chosen.score, _SCORE_PLACES)
    mine = chosen.first_index
    tied = {c.first_index for c in result.candidates
            if c.first_index is not None and c.first_index != mine
            and not c.coverage_gap and round(c.score, _SCORE_PLACES) == key}
    return sorted(tied)


_PLANNER_PATH_W = 25.0         # Tier-3 (ADR-0040): the KO'd key threat sits on MY cheapest Prize
                               # Path — sub-prize, ranks lines within the rung, never beats a prize
_PLANNER_ENABLER_FREE = 8.0    # cheapest-enabler tier (ADR-0031): a FREE direct-evolve (evolved form
                               # already in hand, pre-evo legally evolvable this turn) is the cheapest
                               # first step to the SAME KO — no card leaves the deck, no tutor spent.
_PLANNER_ENABLER_ITEM_SLOT = 6.0  # BUILD 4 (`enabler_item_composer`): an Item enabler's credit WHEN it
                               # preserves the scarce one-per-turn Supporter slot for a slot-competing
                               # Supporter in hand (a `gust` Boss's Orders / another high-value Supporter).
                               # Wider gap over the Supporter-tutor path (0) — the preservation is real —
                               # but still below a free direct-evolve (8): the Item spends a card.
_PLANNER_ENABLER_ITEM_BASE = 2.0  # BUILD 4: the SAME Item enabler's credit when NO Supporter competes for
                               # the slot — keeping it is worth little, so the gap shrinks toward the tutor.
                               # All three (free 8 / item 6|2 / supporter 0) stay sub-prize/sub-survival:
                               # they only break a same-KO tie among enablers, never outrank a genuine
                               # prize or survival delta (decision 3).
_PLANNER_VALUE_W = 80.0        # Tier-5 (ADR-0042): the Automatic Value Model's P(win) on the simmed
                               # end-of-turn board scales into a sub-prize band (< one KO_SCORE), so
                               # the learned leaf breaks prize-EQUAL ties, never overriding a prize
_PLANNER_GAMEPLAN_W = 20.0     # ADR-0045 (S3): a candidate line SERVING the Match Planner's directed goal
                               # gets this × the Game Plan's confidence — sub-prize (< one KO_SCORE), ranks
                               # WITHIN a rung, never beats a prize; kill-switch `match_planner_steer`
_PLANNER_DECKOUT_W = 5.0       # BUILD 2 (`opp_resource_reads`): a sub-prize nudge toward pressing a KO/grind
                               # line when the opponent is near deck-out. `opp_deckout_in_turns` is SOUND
                               # (deck count is public); the finer prized-last-copy read is probabilistic
                               # (opp hand hidden) and deliberately NOT used. Sub-prize — never a reorder.
_PLANNER_DECKOUT_TURNS = 3     # "near deck-out" horizon: fire only when they exhaust within this many turns
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


# ═══ READINESS LEAF + SPEND ACCOUNT (board-state-valuation-grill.md / t0-planner-disposition.md,
#     decided 2026-07-16) ═════════════════════════════════════════════════════════════════════════
# The MY-side "how close am I to executing my win" positional term. NO PRODUCTION CALLER since
# POC-T3: `_engine_leaf_value` is `KO_SCORE x state_value(end board) + min(_LINE_CAP, line)`. Gated-
# additive: every term capped so Σ readiness < one prize (KO_SCORE), preserving the hard-rung invariant
# (a positional board never outranks a real prize). The opponent is NOT modelled here (the survival term
# + the later 2-ply own that). The measured problem it fixes: full within-turn search reaches ~36 distinct
# end-boards but the old leaf collapsed them to ~5 values (SOLE-top ~5%). See the grill spec.
_READINESS_CAP = 300.0        # Σ readiness ceiling — the dominant positional term, but < KO_SCORE.
                              # Max positional stack (readiness 300 + survival 50 + threat 100 +
                              # value 40) = 490 < 1000 = KO_SCORE — no positional board outranks a prize.
_READINESS_BODY_CAP = 120.0   # per-body contribution cap — one fully-loaded attacker can't dominate the
                              # sum (a 2nd attacker / the engine stays legible in the total).
_READINESS_BENCH_DISCOUNT = 0.45   # bench position weight FLOOR for attack readiness (Active = 1.0).
                              # v2 (the who's-Active term, 2026-07-20): the FLOOR of `_bench_position_w`'s
                              # PROMOTION-EASE lift toward `_READINESS_PROMO_MAX` — a benched attacker is
                              # nearer-Active when the Active can vacate freely. Degrades to this flat v1
                              # weight when the Active can't retreat free and no switch is visible (or
                              # stats are unknown).
_READINESS_PROMO_MAX = 0.5    # ceiling of the lifted bench weight — promotion is never free (it still
                              # costs the once-per-turn retreat action + the tempo of the swap), so a
                              # benched attacker must NEVER read equal to the same attacker Active.
                              # Measured on the leaf lab (2026-07-20): 1.0 let "hide the loaded attacker
                              # behind a free-retreat wall" boards overtake the human's attacker-in-front
                              # boards (39→37 SOLE / 190→184 shared); 0.75/0.6 still lost frames; 0.5 is
                              # the frontier with ZERO regressed frames (40/190, E 83.8→84.7).
_READINESS_MOBILITY_W = 2.5   # the who's-Active micro-credit: `_active_quality` × this, once per board
                              # (a bench must exist — a good Active with nowhere to go is nothing). The
                              # second who's-Active facet the lift can't reach: a free-retreat body UP
                              # FRONT (Cinderace r0, Lunatone+Air Balloon) or a building line pre-evo is
                              # what the human boards consistently keep, and the dissected residual ties
                              # differ by exactly this when the bench is unloaded. Micro-sized: it splits
                              # exact-value ties, never outranks a real readiness gap (smallest genuine
                              # attack contribution ≈ a 30-chip × 0.45 × 0.45 ≈ 6). HAND-ARMED
                              # (`leaf_hand_value`): measured hand-blind it nets sole +4 but trades a
                              # shared-top frame whose label pivots on HIDDEN-hand context (the held
                              # Lunar-Cycle {F} / the Mega-in-hand attach) — with the injected hand the
                              # context is readable, so the credit rides the hand-visibility arm.
_READINESS_ATTACK_W = 0.45    # damage → readiness scale (Mega Brave 270 × 0.45 = 121 → body cap 120; a
                              # 70 chip → 31): keeps attack readiness the dominant, legible term.
_READINESS_SATURATED = 0.1    # a 2nd in-play body filling a UTILITY/ENGINE role already filled contributes
                              # ~this (a 2nd Lunatone is fodder — "we only ever need one"); ATTACKERS are
                              # never saturated (a 2nd attacker advances the prize race).
_READINESS_ABILITY_VALUE = {  # value of a body's best FIREABLE setup ability, by behavioral Function Tag
    "energy_accel": 55.0,     # (card_functions.json) — draw/accel/dig/tutor abilities are a FIRST-CLASS
    "draw": 45.0,             # contribution in these ability-centric setup decks (Lunatone draw-3,
    "dig": 45.0,              # Drakloak Recon), CO-EQUAL with an attack. A body with an `engine`/
    "search": 40.0,           # `accel_source` Role but no matching tag gets `_READINESS_ENGINE_ABILITY`.
    "tutor_energy": 35.0, "tutor_pokemon": 35.0, "tutor_mega": 35.0,
    "supporter_tutor": 30.0, "recycle": 25.0, "stall": 20.0,
}
_READINESS_ENGINE_ABILITY = 45.0   # fallback ability value for an `engine`/`accel_source`-Role body whose
                              # ability the Function Tags miss (Lunatone's Lunar Cycle draw is
                              # role-declared, untagged — verified: card_functions.json has no id 675).
_LINE_CAP = 100.0             # the line account's POSITIVE contribution is capped here so the hard-rung
                              # invariant holds strictly: max positional (readiness 300 + survival 50 +
                              # threat 100 + value 40 + line 100) = 590 < 1000 = KO_SCORE, so no path term
                              # can lift a positional board over a real prize. The NEGATIVE side (a spend
                              # penalty) is uncapped — it only ever LOWERS a value, never inverts a prize.
_CLASS_B_SPEND_IDS = frozenset({   # the "spend account" rules (t0-planner-disposition.md Decision 1): a
    # NEGATIVE tuned weight whose referent is the SPEND of a scarce resource (a wasted Ultra Ball /
    # `discard_eot` Energy / the one-per-turn Supporter slot / a held gust/heal) — invisible on the end
    # board (spent cards don't show; hand hidden) and legitimately additive along the line (pure spends
    # don't double-count state). REUSED from the live tuned weight set (`OptionTrace.fired`), never
    # re-derived. `turn_value = readiness(end) − Σ spend_costs(line)`.
    # SCOPE, since the stale-membership audit below had to establish it anyway: `_line_account`'s only
    # callers are inside `_simulate_line`, which POC-T4/5 retired as a RUNTIME rollout and kept as the
    # OFFLINE engine primitive the instruments drive. So this account prices no shipped decision today
    # — which is a reason to keep it honest, not a licence to let it rot.
    # NB the five `discard_eot` burst rungs that used to lead this list are DELETED (ADR-0069 §7).
    # Their referent — spending a one-shot Energy that buys nothing — is now the decider's
    # EVAPORATION LOSS, carried on `OptionTrace.attach_spend` and added below, so the account keeps
    # the signal without keeping the weight coincidences.
    # ⚠️ Thirteen dead members were dropped by PR #448, and they did NOT leave together: six went at
    # POC-T4/5, three in merges from 2026-07-18/19/27, and four were never ids at all (stems whose real
    # rungs carried `-dont-shuffle` / `-at-discard`). A member no Strategy ships can never reach
    # `OptionTrace.fired`, so the set read at three times its true size for weeks, costing nothing and
    # showing nothing. `tests/strategy/test_rung_id_literals_are_live.py` is the interlock.
    "dont-rush-evolve-without-target", "dont-refresh-into-a-probable-miss",
    "dont-lunar-cycle-away-the-last-attachable-f", "dont-search-an-empty-deck",
    "dont-search-a-probable-whiff",
})
_ABILITY_FIRE_IDS = frozenset({    # the "ability-readiness co-equal — fire it = value" rules
    # (t0-planner-disposition.md class A): a POSITIVE tuned weight whose referent is the ACTION of USING a
    # beneficial setup Ability (draw/dig/accel) — Lunatone's Lunar Cycle draw-3, Drakloak's Recon Directive.
    # Its value (the CARDS drawn) is a future resource the end board can't show; the greedy continuation
    # converges the boards, so the leaf can't see the draw. Credited POSITIVELY along the simmed line
    # (symmetric to the spend account), REUSED from the live tuned weight set — never re-derived.
    # `advance-the-accel-pieces` / `feed-the-firing-accelerator` are DELETED (ADR-0069 §7) and are
    # deliberately NOT re-routed: their referent was the ATTACH side of acceleration, whose value is
    # now the decider's `accel_value` — forward build the end board DOES show (Energy landing on
    # bench bodies), so crediting it here as well would double-count. `use-acceleration` survives and
    # keeps the PLAY-side credit, which the end board genuinely cannot show.
    # `use-the-draw-engine-ability` left with the SEQUENCING cluster at POC-T4/5 (Issue #386) — see
    # the ⚠️ on `_CLASS_B_SPEND_IDS` above for why an unshipped member is inert rather than wrong,
    # and `baseline/__init__.py` for where its claim went (the composer scores the dig's successor
    # states, so the draw is priced by the board it reaches rather than credited flat here).
    "fire-lunar-cycle", "lunar-cycle-the-weak-preevo-last-f",
    "use-acceleration", "bench-the-comeback-drawer",
})


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


class PlannerMixin:
    """Pilot-side Turn Planner. ``plan_turn`` returns a :class:`TurnLine` to commit, or None to defer
    to the tuned scoring. Depends on Pilot internals (``_opp_active``, ``_best_affordable_ko_value``,
    ``_prize_value``, the per-option ``OptionTrace``), so it is mixed into the Pilot."""

    def plan_turn(self, obs, select, board, options, traces) -> TurnLine | None:
        """The best committed Turn Line this turn, or None. Only acts at the single-pick MAIN menu;
        every other context (search, snipe, mulligan, multi-select) defers to the tuned scoring.

        The Goal Ladder runs top-down (ADR-0037): the **win rung** first — the Lethal Solver's sound
        lock, which preempts every heuristic goal and never enters ranking — then the closed-form KO
        pool, the Gamble rung, and finally **the composer** (POC-T4/5, Issue #386), which decides
        every MAIN frame the rungs above declined. Plan once, cache, re-plan on reveal (ADR-0031 decision 5): the verdict (win lock
        included) is cached as turn-scoped state keyed by a board fingerprint, so the plan — and the
        win rung's engine verify — is computed once per board and re-derived only when a search/draw
        reveals information that changes the fingerprint (`lethal_refuted` is thereby counted
        per-plan, not per-decision). While an engine sim is re-running my policy (``_planning``), it
        stays closed-form and uncached so it never launches a nested search."""
        if not self._planning:                        # per-plan engine-refute count (telemetry). A verify
            self._lethal_refutes = 0                  # cascade re-runs decide() -> re-enters here under
                                                      # _planning: never wipe the OUTER decision's count
                                                      # mid-scan (an in-sim call can't refute anyway — the
                                                      # verify gate is closed)
        if select.get("context") != _MAIN or select.get("maxCount", 0) != 1:
            return None
        if self._planning:                            # mid engine-sim: closed-form only, never nest search
            win = self._win_line(obs, select, board, options, traces)
            if win is not None:
                return win
            return self._closed_form_plan(obs, select, board, options, traces)
        fp = self._plan_fingerprint(obs, select)
        if self._turn_plan is not None and self._turn_plan[0] == fp:
            return self._turn_plan[1]                 # cache hit: re-plan only on reveal (fingerprint change)
        self._gamble_trace = None                     # fresh plan: clear the gamble working-trace (the
        self._composer_trace = None                   # sparse `gamble` / `composer` telemetry blocks)
        line = self._win_line(obs, select, board, options, traces)
        if line is None:
            candidates = self._closed_form_candidates(obs, select, board, options, traces)
            line = self._commit_best(obs, candidates, traces=traces)
        if line is None:                              # Tier-2 Gamble rung (ADR-0039): below every
            line = self._best_gamble_line(obs, select, board, options, traces)   # deterministic goal
        # Tier-6 escalation (ADR-0043) REMOVED — deprecated by ADR-0064 Decision 6 (its depth-2 reply
        # sim was blind to hidden-hand development; already inert in production, search_budget=0).
        if line is None:                              # POC-T4/5: the composer, unflagged and ungated —
            line = self._composer_line(obs, select, board, options, traces)   # the MAIN decider
        self._turn_plan = (fp, line)
        return line

    def _closed_form_plan(self, obs, select, board, options, traces) -> TurnLine | None:
        """The single closed-form Goal-Ladder verdict (no engine) — the mid-sim / switch-off pick:
        the best candidate by closed-form leaf value, ties to the first generated (the original
        single-line behavior, exactly)."""
        candidates = self._closed_form_candidates(obs, select, board, options, traces)
        return max(candidates, key=lambda ln: ln.value) if candidates else None

    def _closed_form_candidates(self, obs, select, board, options, traces) -> list:
        """ALL candidate Turn Lines from closed-form generation, highest rung first.

        The pool is strictly layer-on-top: it empties when the tuned machinery already reaches a KO
        (any option scored KO_SCORE-class), else it holds every **KO-for-prizes** enabling line plus —
        behind the `planner_key_threat` switch — every **KO-the-key-threat** snipe line (the Goal
        Ladder's middle rung, CONTEXT.md: the leaf scalar ranks across the two, prizes dominant).

        **`stabilize-then-KO` was the third generator and is DELETED** (POC-T4/5, Issue #386;
        Issue #263 § *Position in the ladder*). It was a hand-authored two-step maneuver — heal, then
        KO — and the composer scores a heal-then-attack SEQUENCE by construction: the heal is an
        ordinary MODELLED option and the attack leg is `attack_ev`. A hand-authored stand-in for what
        differencing computes generally is exactly what ADR-0092 retires, so the rule died rather
        than moving. Its corpus frames are composer acceptance cases."""
        if any(t.tactical >= KO_SCORE for t in traces):
            return []
        candidates = self._ko_for_prizes_lines(obs, select, board, options, traces)
        if self.planner_key_threat:
            candidates += self._ko_key_threat_lines(obs, select, board, options)
        return candidates

    def _deferral_value(self, traces) -> float:
        """What the turn is worth if the pool commits NOTHING — the tuned/greedy pick's own score.

        ADR-0074 decision 5 (#175) replaces `_commit_best`'s constant `< KO_SCORE` floor with this.
        The constant breaks under a weighted prize term: a 1-prize KO at p=0.87 scores 870 and would
        be vetoed outright, though an 87%-likely prize is plainly worth taking. Comparing against
        the real alternative needs no threshold — which is the rule ADR-0074 decision 1 sets.

        Measured commensurate before adoption (`tools/train/probes/rung_scale.py`, 72 firing frames
        over dragapult_ex + mega_lucario): the tuned top sits at 20-210 while pool values sit at
        1009-3035, cleanly separated, and the comparison vetoes nothing the constant floor did not.
        The pool is layer-on-top (it is empty whenever the tuned menu already reaches a KO), so
        `tactical` is never KO-class here and this really is the positional alternative.

        0.0 with no traces — an unreadable alternative never vetoes a line."""
        return max((getattr(t, "score", 0.0) or 0.0 for t in (traces or ())), default=0.0)

    def _commit_best(self, obs, candidates, *, traces=()) -> TurnLine | None:
        """The line to commit from the candidate pool: the closed-form best, floored.

        **The engine RANKING seam is DELETED** (POC-T4/5, Issue #386; Issue #263 § *Parity +
        retirement*, *"the runtime engine rollout … retire[s]"*). It forward-simmed every candidate
        to its end-of-turn board through `_engine_leaf_value` and ranked by that — one SAMPLE of a
        shuffle-riding sim, whose value provably swings across processes (ml f24: 7000 / 162 / 129 /
        89 / 57.5 for the same first step). Ranking end states is now the composer's job and it does
        it closed-form, so a second, sampled opinion about the same board is exactly the
        double-source ADR-0092 decision 4 forbids. Deleted with it: `_engine_rank` (the OFF path's
        value-sharpener), the `planner_engine_rank` kill-switch, and `TurnLine.ranked_by`'s
        ``"engine"`` value.

        The weighted-goal floor is unchanged and still the only veto here (ADR-0074 decision 5,
        Issue #175): a `_WEIGHTED_GOALS` line that is not worth more than the tuned alternative
        defers rather than commits."""
        if not candidates:
            return None
        best = max(candidates, key=lambda ln: ln.value)
        if best.goal in _WEIGHTED_GOALS and best.value <= self._deferral_value(traces):
            return None                                  # loses to the alternative — defer
        return best

    # ═══ THE COMPOSER RUNG (POC-T4/5, Issue #386) — the MAIN decider ══════════════════════════════
    # The bottom of the ladder and the widest rung on it. Every MAIN single-pick decision the rungs
    # above declined is composed as a within-turn SEQUENCE (`common.composer`), and the winning
    # sequence's FIRST action is committed. There is no flag and no fire-gate: the dark state lived
    # exactly one sub-issue (Issue #385), and a composer that only fires where a heuristic says
    # greedy is unsure would still leave the greedy argmax deciding — which is the thing this
    # replaces.
    #
    # **The swap IS the deletion.** The develop ROLLOUT rung stood here and is gone with its whole
    # apparatus (`_develop_rollout_line`, `_develop_should_fire`, `_develop_candidates_record`, the
    # `develop_rollout` flag, the `plan_candidates` telemetry, `_engine_leaf_value`, and
    # `_simulate_line`'s ``stream`` half of the Issue #178 machinery). So are the MAIN-phase rung
    # families the composer now prices by differencing — heal, the Tool equip band, gust
    # whether-to-play, the draw/dig economy, hand disruption, the Stadium deck rung and
    # `retreat-to-wall-the-line`. A rung asserting a preference the leaf can compute is a second
    # opinion about the same board, and the PR body lists every deleted id.

    def _composer_line(self, obs, select, board, options, traces) -> TurnLine | None:
        """The composer's committed first action as a ``goal="compose"`` Turn Line, or None.

        `common.composer.compose` beams over within-turn sequences, transitions them through
        `apply_option` and scores each end state as ``state_value(end board) + EV(terminal action)``
        (Issue #263 § *Terminal-action valuation*). The winning sequence's first action is what this
        decision commits; the rest of the sequence is NOT locked — the engine re-presents a menu after
        every action and `plan_turn`'s fingerprint cache re-plans on any reveal, so the beam is
        re-run rather than replayed. That is deliberate: a locked line is the win rung's mechanism
        and it is locked only because the engine VERIFIED it.

        **Three defers, and each is a refusal to guess rather than a gate:**

        * no `chosen` — the seam could price nothing on this menu, which is the honest answer at a
          select whose every option is a card effect (Issue #385's ``chosen is None`` report). The
          tuned scoring keeps the turn.
        * `chosen.coverage_gap` — the winning candidate exists only because something REFUSED, and
          *"a refusal is an unknown, not a zero"*. Committing an unknown because nothing scored
          above it is precisely the silent competition Issue #263 forbids.
        * no `first_index` — the empty stop-now line names no menu option, so there is nothing to
          commit.

        **The margin telemetry is emitted, not optional** (Issue #263 § *Beam-quality package*
        item 3): the chosen first step's 1-ply rank relative to *k* and its margin to the k-th
        candidate ride the Decision's sparse ``composer`` block, so a first step that barely survived
        the beam is visible in the live trace BEFORE it fails silently on an unseen board.

        ``search_api`` is threaded because `_search_api` is `fate()`'s ENGINE-RESOLVED route and
        Issue #263 § *Parity + retirement* preserves it by name. It is INERT until a caller also
        supplies a per-option determinism proof — `fate`'s gate is *provably* deterministic, and its
        `None` default refuses — so wiring it changes nothing today and is the seam being kept open
        rather than a route being opened.

        ``shed`` is NOT inert, and it is threaded because this method is the only caller that can.
        `compose` cannot reach a Pilot, so a costed search (Ultra Ball's *"discard 2 other cards"*)
        must be told WHICH cards the live decider would pay before its pool can be enumerated; left
        `None` the seam REFUSES it by name rather than pricing it unpaid. Unwired, that refusal was
        every Ultra Ball in the pool — the composer had no opinion about the deck's most-played
        Item, and `Pilot.cost_shed_indices` (public and model-shaped for exactly this call, see its
        docstring) sat unused. Found from `test_blunder_20260629`, whose composer `gaps` named the
        missing seam in as many words."""
        my_index = int((obs.get("current") or {}).get("yourIndex") or 0)
        try:
            model = self._leaf_state_model(obs, my_index)
            result = composer.compose(model, options,
                                      search_api=getattr(self, "_search_api", None),
                                      shed=self.cost_shed_indices)
        except Exception:
            return None                                  # a modelling slip never crashes the decision
        chosen = result.chosen
        self._composer_trace = {"margin": result.margin.working(), "stats": result.stats,
                                "gaps": list(result.gaps)[:_COMPOSER_GAP_K]}
        if chosen is None or chosen.first_index is None or chosen.coverage_gap:
            return None
        tied = _tied_first_steps(result, chosen)
        if tied:
            self._composer_trace["tied_first_steps"] = tied
            return None
        self._composer_trace["chosen"] = chosen.working()
        self._composer_trace["steps"] = [s.index for s in chosen.steps]
        # …and the committed index NAMED, because `steps` cannot carry it on a terminal line: an
        # attack or an End has no steps, so `steps` is `[]` and the block explained a pick it could
        # not identify. `first_index` is the one field a trace reader joins to `chosen` (ADR-0019
        # legibility — the record must never leave "top-score not chosen" looking like a bug).
        self._composer_trace["first_index"] = chosen.first_index
        return TurnLine(next_step=[chosen.first_index], goal="compose", value=chosen.score,
                        rationale="compose: the best within-turn sequence's first action",
                        ranked_by="composer", kind="sequence")

    # ═══ THE WIN RUNG — the Lethal Solver (ADR-0030/0037): sound, engine-verified, preempts all ═══
    # Everything in this section is SOUND by construction: min-bound damage floors, worst-case
    # coins, engine verdicts. It never trades against the heuristic rungs — a win, when locked,
    # owns the decision. A false Lethal is the one catastrophic error (a miss costs a turn; a
    # phantom loses the game), so soundness beats completeness throughout.

    def _win_line(self, obs, select, board, options, traces) -> TurnLine | None:
        """The shortest guaranteed win on the current turn as a ``goal="win"`` Turn Line, or None.

        Two generation modes (ADR-0037): ``lethal_family`` ON = the ONE generator family
        (`_family_win_candidates` — single+multi-develop, gust, tutor; all min-bound sound), every
        lock engine-verified (`lethal_verify`, cascade-driven to the engine's verdict). OFF = the
        legacy stage-1 rungs (`_legacy_win_candidates` — direct + hook-trace unlock + evolve), with
        verify on DIRECT locks only (a 1-step sim of a multi-step line ends mid-turn and would
        false-refute without the cascade drive the family mode uses). Either way: a refute drops the
        candidate (never lock a phantom, counted in `_lethal_refutes`); a None verdict keeps the
        sound closed-form lock (a coin-floor win can never verify True by construction — the
        min-bound floor is the authority there)."""
        if board.my_prizes_remaining <= 0:
            return None
        opp = self._opp_active(obs)
        family = self.lethal_family
        candidates = (self._family_win_candidates(obs, select, board, options, opp) if family
                      else self._legacy_win_candidates(obs, select, board, options, traces, opp))
        for cand in candidates:
            verified = None
            if (self.lethal_verify and not self._planning
                    and (family or cand.kind == "direct")):
                recorded = [] if (family and self.lethal_veto) else None
                verified = (self._engine_confirms_win(obs, [cand.next_step], max_cascade=40,
                                                      record=recorded)
                            if family else self._engine_confirms_win(obs, [cand.next_step]))
                if verified is False:
                    self._lethal_refutes += 1
                    continue                           # the engine says this "win" doesn't win — skip it
                if verified and recorded is not None:  # stage 3: a VERIFIED lock materializes its
                    self._win_lock_store(obs, recorded)   # confirmed cascade for replay
            return replace(cand, verified=verified)
        return None

    def _legacy_win_candidates(self, obs, select, board, options, traces, opp):
        """Yield the pre-family (stage-1) closed-form candidates in their exact order — the
        ``lethal_family=False`` path, ADR-0030's shipped rungs (shared-valuation upgrades — e.g.
        the typed-affordability guard — flow through): (1) a KO already
        on the menu that WINS now, judged by the attack's OWN prize yield (`_attack_wins`); (2) an
        Energy attach or a retreat into a READY benched attacker that unlocks the winning KO (the
        KO_SCORE-class closed-form hook traces); (3) an EVOLVE of the Active bringing a bigger
        attacker online (no hook scores it, so its own min-bound lookup)."""
        # 1) direct: a KO on the menu that wins now.
        for i, o in enumerate(options):
            if o.get("type") == _ATTACK and self._attack_wins(obs, board, o, opp):
                yield TurnLine(next_step=[i], goal="win", kind="direct",
                               rationale="lethal: this KO wins the match")

        # Develops below unlock a KO of opp ACTIVE (closed-form hooks). Wins iff takes my last prize
        # or opp has no bench to promote — under-counts any rider snipe, conservative but sound.
        if not (self._prize_value(opp) >= board.my_prizes_remaining or not board.opp_bench):
            return

        # 2) Energy attach (`_attach_lethal_tactical`) or retreat into ready bench attacker
        # (`_retreat_to_lethal_tactical`) unlocking that KO — both KO_SCORE-class; finishing attack
        # follows next menu.
        for i, o in enumerate(options):
            if o.get("type") in (_ATTACH, _RETREAT) and traces[i].tactical >= KO_SCORE:
                yield TurnLine(next_step=[i], goal="win", kind="unlock",
                               rationale="lethal (unlock): a develop enables the winning KO")
        # 3) EVOLVE of Active bringing bigger attacker online — no closed-form hook scores it, so
        # look up: evolved form inherits Active's Energy, best affordable attack must KO (same-turn
        # legal, rules.md §evolution). Typed-affordability guarded like every shared KO valuation.
        ma = next((p for p in (self._my_player(obs).get("active") or []) if p), None)
        for i, o in enumerate(options):
            if o.get("type") == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                evolved_id = self._option_card_id(obs, select, o)
                if self._best_affordable_ko_value(obs, board, opp, evolved_id, board.my_active_energy,
                                                  bound="min", body=ma) > 0:
                    yield TurnLine(next_step=[i], goal="win", kind="evolve",
                                   rationale="lethal (evolve): evolving enables the winning KO")

    def _family_win_candidates(self, obs, select, board, options, opp):
        """Yield ``goal="win"`` candidates from the ONE generator family (ADR-0037), SHORTEST-first:
        tier 0 = a direct KO already on the menu; tier 1 = one develop (attach the Active / retreat
        into a ready body / evolve the Active / gust up a KO-able last-prize body); tier 2 = the same
        develop PLUS this turn's one attach; tier 3 = the energy-tutor Supporter line (fetch the
        attach the line lacks). Every candidate is min-bound SOUND (worst-coin damage floors, exact
        prize math, engine-vetted step legality — an option on the menu IS legal); the develop tiers'
        win test is the conservative legacy precondition (opp-Active prize reaches my remaining count
        or their bench is empty — rider snipes under-counted, never over). An option index is yielded
        once, at its shortest tier (a refuted candidate is not retried at a longer tier: the verify
        cascade drives the same policy either way)."""
        # tier 0: direct — a KO on the menu that wins now.
        seen = set()
        for i, o in enumerate(options):
            if o.get("type") == _ATTACK and self._attack_wins(obs, board, o, opp):
                seen.add(i)
                yield TurnLine(next_step=[i], goal="win", kind="direct",
                               rationale="lethal: this KO wins the match")
        if board.turn <= 1:
            return                                     # turn 1 going first: no attack this turn, so
                                                       # no develop can cash a win (rules.md §first-turn)
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)
        extra = 1 if (board.reusable_energy_in_hand and not board.energy_attached) else 0
        for tier_extra in (0, extra) if extra else (0,):
            for i, o in enumerate(options):
                if i in seen:
                    continue
                t = o.get("type")
                if t == _ATTACH and o.get("inPlayArea") == _ACTIVE and tier_extra == 0:
                    # Count AND colour off the ONE provision read (Issue #418) — a second lookup for
                    # the type is a second chance to disagree with the first about the same card.
                    codes = self._attach_provision_codes(obs, select, board, o)
                    win = self._develop_wins(obs, board, opp, board.my_active_id,
                                             board.my_active_energy + len(codes), body=ma,
                                             extra_type=codes[0] if codes else None,
                                             extra_units=len(codes))
                    kind, why = "unlock", "lethal (unlock): the attach enables the winning KO"
                elif t == _RETREAT:
                    win = any(self._develop_wins(obs, board, opp, p.get("id"),
                                                 len(p.get("energies") or []) + tier_extra, body=p)
                              for p in (me.get("bench") or []) if p)
                    kind, why = "unlock", "lethal (unlock): the retreat enables the winning KO"
                elif t == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                    win = self._develop_wins(obs, board, opp, self._option_card_id(obs, select, o),
                                             board.my_active_energy + tier_extra, body=ma)
                    kind, why = "evolve", "lethal (evolve): evolving enables the winning KO"
                elif t == _PLAY and self._is_gust(obs, select, o):
                    win = self._gust_win_target(obs, board, board.my_active_energy + tier_extra)
                    kind, why = "gust", "lethal (gust): dragging up the KO-able body wins the match"
                else:
                    continue
                if win:
                    seen.add(i)
                    yield TurnLine(next_step=[i], goal="win", kind=kind, rationale=why)
        # tier 3: the energy-tutor Supporter supplies the attach the line lacks (the 4298 shape,
        # game-winning). SOUND only when the deck DEFINITELY still holds a reusable Energy (the
        # match-scoped tracker's positive certainty) — a probable fetch is never a win.
        retreat_on_menu = any(o.get("type") == _RETREAT for o in options)
        if (not (board.energy_attached or board.reusable_energy_in_hand)
                and self._tutor_energy_certain(board)):
            for i, o in enumerate(options):
                if i in seen or o.get("type") != _PLAY or not self._is_energy_tutor(obs, select, o):
                    continue
                win = self._develop_wins(obs, board, opp, board.my_active_id,
                                         board.my_active_energy + 1, body=ma)
                if not win and retreat_on_menu:
                    win = any(self._develop_wins(obs, board, opp, p.get("id"),
                                                 len(p.get("energies") or []) + 1, body=p)
                              for p in (me.get("bench") or []) if p)
                if win:
                    seen.add(i)
                    yield TurnLine(next_step=[i], goal="win", kind="unlock",
                                   rationale="lethal (unlock): the energy tutor fetches the winning attach")
        # tier 4: the evolution-tutor Supporter line (Salvatore, `rush_evolve` — the a212 shape):
        # evolve a deck-certain, no-Ability DIRECT evolution onto an in-play body straight from the
        # deck, then (for a benched body) retreat into it and attach — e.g. Salvatore -> Mega Starmie
        # onto a Staryu, free-retreat the opener, attach, Jetting Blow the last body: bench-empty win.
        # Salvatore's own allowance covers every in-play target (setup-placed / played this turn;
        # anything older is normal-legal), so no timing gate. SOUND on the tracker's positive deck
        # certainty + min-bound KO math; the engine verify cascade backstops the rest.
        targets = [(p, False) for p in (me.get("active") or []) if p]
        if retreat_on_menu:
            targets += [(p, True) for p in (me.get("bench") or []) if p]
        for i, o in enumerate(options):
            if i in seen or o.get("type") != _PLAY or not self._is_evolution_tutor(obs, select, o):
                continue
            if any(self._tutor_evolution_wins(obs, board, opp, p) for p, _ in targets):
                yield TurnLine(next_step=[i], goal="win", kind="unlock",
                               rationale="lethal (unlock): the evolution tutor evolves the winning attacker")
        # tier 5 (`boost_lethal`): retreat into a benched attacker whose DAMAGE-BOOSTED KO wins — the
        # promote-a-benched-{F}-attacker → play N damage-boost Items → swing-lethal shape (ml f24:
        # Solrock's Cosmic Beam 70 + 2x Premium Power Pro = 130 exact OHKOs Duraludon; opp bench empty
        # -> a bench-empty win). The retreat is the driven step; the SWITCH then promotes the boosted
        # body (`promote_ko_aware`'s `is_ko_promote_target`), the Items price at KO_SCORE via
        # `_boost_lethal_tactical` once it is Active, and the final swing is the direct tier-0 KO. The
        # boost total is this-turn plays + playable hand copies (`_typed_boost_total`); the retreated
        # Active benches as the `requiresBench` partner. Min-bound sound; engine-verified on lock.
        if self.boost_lethal and ma is not None:
            for i, o in enumerate(options):
                if i in seen or o.get("type") != _RETREAT:
                    continue
                for j, p in enumerate(me.get("bench") or []):
                    if not p:
                        continue
                    pstat = self.stats.get(p.get("id")) if self.stats else None
                    if pstat is None:
                        continue
                    boost = self._typed_boost_total(obs, pstat, opp)
                    if boost <= 0:                          # no boost applies -> not this tier
                        continue
                    names = self._promote_bench_names(me, j, ma)
                    if self._develop_wins(obs, board, opp, p.get("id"),
                                          len(p.get("energies") or []), body=p,
                                          boost_amount=boost, boost_type=pstat.energyType,
                                          promote_bench_names=names):
                        seen.add(i)
                        yield TurnLine(next_step=[i], goal="win", kind="unlock",
                                       rationale="lethal (boost): retreat into the boosted KO attacker wins")
                        break
        # tier 6 (`retreat_enabler_lethal`): a benched attacker ALREADY wins if promoted, but the Active
        # can't retreat now — a retreat-reduction Tool (Air Balloon: {C}{C} less) frees the retreat. Drive
        # the Tool play (already in hand), else a Trainer-tutor Supporter (Petrel: "search a Trainer") whose
        # deck DEFINITELY still holds a covering Tool (ml f15: Petrel -> Air Balloon -> onto Makuhita -> free
        # retreat -> promote Mega Lucario ex -> Aura Jab 130 >= Riolu 80, opp bench empty). The tutor pick ->
        # Tool -> Active attach -> retreat -> promote cascade rides re-planning + the steering hooks; SOUND on
        # the tracker's positive deck certainty, and engine-verified on lock (a phantom is dropped).
        if (self.retreat_enabler_lethal and ma is not None and not self._can_retreat(ma)
                and self._bench_body_wins_if_promoted(obs, board, opp, me, ma)):
            need = self._retreat_shortfall(ma)
            for i, o in enumerate(options):
                if i in seen or o.get("type") != _PLAY or need <= 0:
                    continue
                cid = self._option_card_id(obs, select, o)
                st = self.stats.get(cid) if (self.stats and cid is not None) else None
                tool_in_hand = st is not None and getattr(st, "retreatReduction", 0) >= need
                tutorable = (self._is_trainer_tutor(obs, select, o)
                             and self._deck_has_retreat_tool(board, need))
                if tool_in_hand or tutorable:
                    seen.add(i)
                    yield TurnLine(next_step=[i], goal="win", kind="unlock",
                                   rationale="lethal (unlock): the retreat Tool frees the retreat into the winning KO body")

    def _bench_body_wins_if_promoted(self, obs, board, opp, me, ma) -> bool:
        """SOUND: some benched body, promoted with its CURRENT Energy (a freed retreat brings it Active),
        takes a min-bound winning KO of the opponent's Active. The retreat-enabler tier's win test — the
        retreat itself is supplied by a Tool, not modeled here (``_develop_wins`` values the body as if
        already Active, the retreated Active provably benched via ``_promote_bench_names``)."""
        return any(self._develop_wins(obs, board, opp, p.get("id"), len(p.get("energies") or []),
                                      body=p, promote_bench_names=self._promote_bench_names(me, j, ma))
                   for j, p in enumerate(me.get("bench") or []) if p)

    def _retreat_shortfall(self, ma) -> int:
        """Energy the Active is SHORT of paying its EFFECTIVE Retreat Cost this turn (>0 iff it can't
        retreat now). A retreat-reduction Tool whose reduction covers this frees the retreat (Air Balloon
        −2 on a retreat-2 Makuhita with 0 attached -> shortfall 2 -> free).

        "Effective", not printed, since Issue #306. This used to read the printed cost and ignore the
        Tools ALREADY attached, which merely over-stated the need while every Tool was a discount —
        fail-closed, so it survived. Gravity Gemstone makes a retreat cost {C} MORE
        (`retreatReduction` −1), and an ignored surcharge UNDER-states the need, which would let
        `_grab_retreat_tool_lethal_tactical` / `_attach_retreat_tool_lethal_tactical` accept a Tool
        that does not in fact free the retreat and score the phantom at KO_SCORE. Shared with
        `_can_retreat` through `_attached_retreat_delta`, so the two cannot disagree about a body."""
        if not (ma and self.stats):
            return 0
        st = self.stats.get(ma.get("id"))
        if st is None:
            return 0
        eff = getattr(st, "retreatCost", 0) - self._attached_retreat_delta(ma)
        return max(0, eff - len(ma.get("energies") or []))

    def _is_trainer_tutor(self, obs, select, option) -> bool:
        """This PLAY option is a `tutor_trainer` Supporter (Petrel class) — it searches ANY Trainer card
        into hand, so it can certainly fetch a specific retreat Tool the deck definitely still holds."""
        cid = self._option_card_id(obs, select, option)
        return bool(cid is not None and self.functions and "tutor_trainer" in self.functions.tags(cid))

    def _deck_has_retreat_tool(self, board, need: int) -> bool:
        """SOUND: a retreat-reduction Tool whose reduction covers ``need`` is PROVABLY still in my deck
        (the match tracker's positive certainty, `Board.deck_definitely_has`) — never a probable fetch."""
        if not self.stats:
            return False
        return any(st is not None and getattr(st, "retreatReduction", 0) >= need
                   and board.deck_definitely_has(cid)
                   for cid in set(self.deck) for st in (self.stats.get(cid),))

    def _develop_wins(self, obs, board, opp, attacker_id, energy, body=None,
                      extra_type=None, extra_units: int = 0,
                      boost_amount: int = 0, boost_type=None, promote_bench_names=None) -> bool:
        """SOUND: this attacker, carrying ``energy``, takes a min-bound affordable KO of the
        opponent's Active AND that KO wins — it reaches my remaining prize count or their bench is
        empty (no Pokémon to promote). The family's shared develop-tier win test: worst-coin damage
        floors via ``bound="min"``, rider snipes deliberately under-counted (conservative).
        ``body``/``extra_type``/``extra_units`` forward to the typed-affordability guard (an Energy
        the line provides can't fund a specific-type slot it doesn't match — Ignition never pays a
        {W}); budget beyond attached+extra stays wild (fail-open). ``boost_amount``/``boost_type``/
        ``promote_bench_names`` forward the damage-boost rider (the `boost_lethal` tier: a typed
        this-turn boost + a provably-benched `requiresBench` partner)."""
        if not (self._prize_value(opp) >= board.my_prizes_remaining or not board.opp_bench):
            return False
        return self._best_affordable_ko_value(obs, board, opp, attacker_id, energy, bound="min",
                                              body=body, extra_type=extra_type,
                                              extra_units=extra_units, boost_amount=boost_amount,
                                              boost_type=boost_type,
                                              promote_bench_names=promote_bench_names) > 0

    def _attach_provision_codes(self, obs, select, board, option) -> tuple:
        """The ``EnergyType`` UNIT codes this ATTACH provides the Active — one of its own colour for
        a Basic Energy, CCC for a discard-burst (`discard_eot`, Ignition) onto an Evolution.
        ``()`` when the card can't be resolved or provides no Energy.

        CODES rather than a bare count since Issue #418, off the single seam
        `CombatMath.provision_codes`: the develop-tier win test needs the COLOUR as well (an Energy
        the line provides can't fund a specific-type slot it doesn't match — Ignition never pays a
        {W}), and reading the count here and the colour at the call site is two readings of one
        fact."""
        eid = self._option_card_id(obs, select, option)
        if eid is None:
            return ()
        active_stat = (self.stats.get(board.my_active_id)
                       if (self.stats and board.my_active_id is not None) else None)
        return self.combat.provision_codes_or_floor(eid, active_stat)

    def _is_gust(self, obs, select, option) -> bool:
        """This PLAY option is a gust card (Function Tag `gust`, e.g. Boss's Orders)."""
        cid = self._option_card_id(obs, select, option)
        return bool(cid is not None and self.functions and "gust" in self.functions.tags(cid))

    def _gust_win_target(self, obs, board, energy) -> bool:
        """SOUND: some benched opponent body the gust drags Active is worth my remaining prize count
        AND my Active (at ``energy``) takes a min-bound affordable KO of it — the ADR-0022 gust
        lethal, generated (and locked) by the family rather than hook-scored. Dragging never empties
        their board (the old Active benches), so only the prize-out shape wins here; Tera bench
        immunity is irrelevant (the target is Active when hit)."""
        ma = next((p for p in (self._my_player(obs).get("active") or []) if p), None)
        for b in (self._opp_player(obs).get("bench") or []):
            if not b or self._prize_value(b) < board.my_prizes_remaining:
                continue
            if self._best_affordable_ko_value(obs, board, b, board.my_active_id, energy,
                                              bound="min", body=ma) > 0:
                return True
        return False

    def _tutor_energy_certain(self, board) -> bool:
        """SOUND: my deck DEFINITELY still holds a reusable typed Energy a `tutor_energy` Supporter
        can fetch — the deck tracker's positive certainty (`Board.deck_definitely_has`), never the
        probabilistic estimate. Reusable mirrors `_has_reusable_energy`: an Energy card (hp 0, real
        `energyType`) not tagged `discard_eot`."""
        if not self.stats:
            return False
        for cid in set(self.deck):
            stat = self.stats.get(cid)
            if not stat or getattr(stat, "hp", 0) or not getattr(stat, "energyType", 0):
                continue
            if self.functions and "discard_eot" in self.functions.tags(cid):
                continue
            if board.deck_definitely_has(cid):
                return True
        return False

    def _attack_wins(self, obs, board, option, opp) -> bool:
        """True iff taking this ATTACK wins the match THIS turn — its own KO(s) take my last prize, or
        it empties the opponent's board. Per-attack and CONSERVATIVE (under-counts riders rather than
        over): a false Lethal is the one catastrophic error, so soundness beats completeness. A
        simultaneous double-KO is a draw, not a win (ADR-0022 #2), so it never wins here."""
        aid = option.get("attackId")
        hp = (opp or {}).get("hp", 0)
        # Damage oracle (ADR-0032): ignore-flag attack (Nebula Beam) KOs through prevent_ex_damage wall old
        # path zeroed. bound="min" = sound FLOOR: coin/conditional contributes worst case, never locks phantom Lethal.
        dmg = self.predicted_damage(self._my_active_id(obs), aid, opp, bound="min",
                                    context=self._damage_context(obs))
        active_ko = bool(hp and dmg >= hp)
        if active_ko and self._is_simultaneous_draw(board, aid, self._prize_value(opp)):
            return False
        prizes_taken = ((self._prize_value(opp) if active_ko else 0)
                        + self._snipe_ko_prizes(board.opp_bench, self.combat.rider_snipe(aid)))
        if prizes_taken >= board.my_prizes_remaining:
            return True
        return active_ko and not board.opp_bench       # KO leaves them no Pokémon to promote

    def _win_lock_store(self, obs, recorded) -> None:
        """Materialize a VERIFIED win line's confirmed cascade as the turn-scoped locked line
        (ADR-0037 stage 3, `lethal_veto`): the engine-driven selects, each an entry
        ``{ctx, max, drive, chosen}`` where ``chosen`` is the picked options' identity tuples and
        ``drive`` marks a hidden-zone pick (prize) the replay must policy-drive. Only a verified
        lock ever stores one — a None-verdict lock has no confirmed cascade to replay."""
        self._locked_line = {"turn": (obs.get("current") or {}).get("turn"),
                             "queue": list(recorded)}

    def _option_identity(self, obs, select, option) -> tuple:
        """The live-matchable identity of one select option — type + attack + resolved card +
        in-play target + owner. Deliberately EXCLUDES the option's menu index (the replay's whole
        point is index-independence); a visible-zone card resolves by id, so a sim pick maps onto
        the live menu wherever it sits."""
        return (option.get("type"), option.get("attackId"),
                self._option_card_id(obs, select, option),
                option.get("inPlayArea"), option.get("inPlayIndex"), option.get("playerIndex"))

    def replay_locked_line(self, obs, select):
        """The locked line's next step, replayed against the live select (ADR-0037 stage 3), as
        ``(chosen, TurnLine)`` — or None when there is nothing to replay: veto off, no lock, the
        lock expired (a new turn — natural, silent), the entry is a hidden-zone pick (policy-drives
        it, entry consumed, lock kept), the queue ran dry, or ANY identity failed to match — the
        mismatch path also clears the lock and raises the sparse ``lethal_lost`` flag
        (`_lethal_lost`, telemetry) so a live sim-vs-reality divergence is countable. Never a blind
        index: every replayed pick is identity-resolved on the LIVE menu."""
        if not self._planning:                         # mirror the refute counter's reentry guard:
            self._lethal_lost = False                  # an in-sim decide must never clobber the
        lock = self._locked_line                       # outer decision's loss flag
        if not self.lethal_veto or self._planning or lock is None:
            return None
        if lock["turn"] != (obs.get("current") or {}).get("turn"):
            self._locked_line = None                   # a new turn: natural expiry, not a loss
            return None
        if not lock["queue"]:
            self._locked_line = None                   # line fully executed
            return None
        entry = lock["queue"].pop(0)
        if entry.get("drive"):
            return None                                # hidden-zone pick: policy-drives, lock kept
        options = select.get("option") or []
        live = {}
        for i, o in enumerate(options):
            live.setdefault(self._option_identity(obs, select, o), i)
        chosen = []
        for ident in entry.get("chosen") or ():
            i = live.get(tuple(ident))
            if i is None or i in chosen:
                self._locked_line = None               # sim diverged from reality: fall back to
                self._lethal_lost = True               # re-derivation, surface the loss
                return None
            chosen.append(i)
        if not chosen or select.get("context") != entry.get("ctx"):
            self._locked_line = None
            self._lethal_lost = True
            return None
        return (chosen, TurnLine(next_step=chosen, goal="win", kind="replay", verified=True,
                                 rationale="lethal (replay): executing the verified line"))

    def _exact_own_zones(self, obs, me):
        """(ADR-0050) The EXACT ``(your_deck, your_prize)`` predictions for ``search_begin`` — flat
        card-id lists — from the deck tracker's anchored split: ``your_deck`` = decklist − visible −
        prizes (``_deck_known_counts``), ``your_prize`` = ``obs['own_prizes']``. ``(None, None)`` when
        the prizes are not yet anchored (no ``own_prizes``, or the tracker can't resolve them), so the
        caller keeps the sound decklist-prefix fallback.

        NEVER seeds the deck+prize POOL into the deck half: over-counting a prized copy into the deck
        is exactly what could let the engine fetch a card that is really all prized and false-confirm
        a phantom win (the one catastrophic Solver error). The split is the soundness."""
        own = (obs or {}).get("own_prizes")
        if not own:
            return None, None
        prizes = {int(k): v for k, v in own.items()}
        known = self._deck_known_counts(me, prizes)
        if not known:
            return None, None
        your_deck = [cid for cid, n in known.items() for _ in range(n)]
        your_prize = [cid for cid, n in prizes.items() for _ in range(n)]
        return your_deck, your_prize

    def _seed_zones(self, obs, me, opp):
        """(ADR-0050) The hidden-zone predictions for ``search_begin``:
        ``(your_deck, your_prize, opp_deck, opp_prize, opp_hand)``.

        MY deck/prize use the EXACT anchored split (``_exact_own_zones``) when ``lethal_seed_exact`` is
        on and the tracker has anchored; else a decklist prefix — the sound fallback, because only
        non-fetch lines (whose verdict is deck-independent) reach the search unanchored (the fetch
        tiers gate on ``deck_definitely_has``, which needs the anchor). The prefix is what
        false-refuted the high-id enabler band before this fix (`deck.csv` is id-sorted).

        Opponent zones stay a my-deck prefix: a this-turn lethal ends before the opponent acts
        (`_engine_confirms_win` refutes the moment control passes to them), so their hidden content
        cannot change the verdict — only the count must satisfy ``search_begin``."""
        deck = list(self.deck)

        def take(n):
            return deck[: max(0, n)]

        your_deck = your_prize = None
        if getattr(self, "lethal_seed_exact", True):
            your_deck, your_prize = self._exact_own_zones(obs, me)
        if your_deck is None:
            your_deck, your_prize = take(me.get("deckCount", 0)), take(len(me.get("prize") or []))
        return (your_deck, your_prize, take(opp.get("deckCount", 0)),
                take(len(opp.get("prize") or [])), take(opp.get("handCount", 0)))

    def _engine_confirms_win(self, obs, line_steps, max_cascade: int = 12, record=None):
        """Tier-1 (ADR-0030): forward-simulate ``line_steps`` — a list of per-select index lists, the
        exact moves of a candidate win line — through the engine's OWN search and report whether IT
        declares me the winner. The grading engine, not my closed-form math, is the authority, so it
        also resolves what closed-form is blind to (abilities, status, Tera, evolution/turn-1 timing).

        Distinct from `_simulate_line` by design: THIS is the sound regime (``manual_coin=True``,
        drives to the engine's VERDICT); that is the heuristic ranker (coins auto-resolve, reads the
        end-of-turn BOARD). A winning attack does not flip ``result`` at the attack step: the engine
        first opens MY cascade selects (take the prize(s), pick a snipe/Damage target, pay a cost),
        so after the line's own steps the search keeps driving MY selects through the policy
        (``decide``, under the ``_planning`` guard so nothing nests or pollutes) until the engine
        reaches a verdict — measured live: the prize-take TO_HAND select is what every real win
        parks on.

        Sound and fail-safe:
          * ``manual_coin=True`` so a coin the line doesn't account for surfaces as a COIN_HEAD
            select → **None** rather than trust a chosen flip (never let the policy pick heads).
          * a cascade that DREW off the shuffled deck can only be confirmed as far as that draw:
            a ``True`` there is demoted to **None** (#178). Same rule as the coin, through the door
            the coin rule left open — `_seed_zones` seeds the hidden zones with a predicted MULTISET
            whose ORDER is our guess, so a win that needed a specific card off it is not a guaranteed
            win in the real game, whatever the sim did. Asymmetric on purpose:
            **False is left alone.** A refute is the conservative direction (it drops a candidate and
            costs at most a turn), while demoting refutes to None would let phantom locks through —
            the one catastrophic error. Measured on ml f24 (2026-07-27): its `[correct]`-only
            cascade shuffles its hand back in mid-line and then draws ELEVEN cards off the reshuffled
            deck — every one of them AFTER that shuffle, which is the part the engine does not
            reproduce — and its verdict came back False on most runs and True on some, which is what
            made two suite tests flake through the same frame.
          * the select passing to the OPPONENT with no verdict = the win did not materialize before
            they act → False (a real refute: our win-shapes need no opponent action).
          * an exhausted cascade cap is **None** (undetermined never refutes); so is an unavailable
            search (lib-free suite), a missing ``search_begin_input``, or any error — the caller
            then keeps its sound closed-form verdict.
        The hidden-zone predictions are filled from my own deck list; the cascade's prize picks
        reveal predicted cards but the ``result`` verdict is invariant to WHICH prize is taken (so a
        prize take alone never demotes — `_rng_probe(prize=False)`).
        Lazy DLL import keeps the fast unit suite from ever loading the native engine.

        ``record`` (a list, ADR-0037 stage 3): materialize each cascade select this drive answers as
        ``{ctx, max, drive, chosen}`` — the picked options' identity tuples, ``drive``=True for an
        all-hidden-zone pick (prize area: the sim's ids are predictions, replay must policy-drive) —
        the confirmed-cascade record a verified lock replays (`lethal_veto`)."""
        if not (obs or {}).get("search_begin_input") or not line_steps:
            return None
        try:
            from cg import api as cgapi
        except Exception:
            return None
        from dataclasses import asdict
        cur = obs.get("current") or {}
        yi = cur.get("yourIndex", 0)
        players = cur.get("players") or []
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        yd, yp, od, op_, oh = self._seed_zones(obs, me, opp)   # ADR-0050: exact own split when anchored

        was_planning = self._planning
        self._planning = True                          # the cascade re-runs decide(): never nest a
        # This-turn boosts PLAYED inside the cascade (the sim's own Premium Power Pro plays) must be
        # priced by the boost tracker so a later step's decide() sees the running total (a multi-copy
        # boost line, ml f24). observe() is skipped under `_planning` for the REAL stream, so drive the
        # tracker explicitly from the sim's obs here — snapshot + restore so the match state a real
        # decision resumes on is untouched (the sim's future never leaks into the live tracker).
        boost_snap = {k: list(v) for k, v in self._turn_boosts._by_side.items()}
        boost_turn_snap = self._turn_boosts._last_turn
        try:                                           # search, never verify inside a verify
            saw_rng = _rng_probe(cgapi, yi, prize=False)   # the VERDICT question: prize ids are moot
            sampled = False
            ob = cgapi.to_observation_class(obs)
            st = cgapi.search_begin(ob, yd, yp, od, op_, oh, [], manual_coin=True)
            for step in line_steps:
                st = cgapi.search_step(st.searchId, list(step))
                sampled = sampled or saw_rng(st.observation)
            verdict = None
            for _ in range(max_cascade):
                o = st.observation
                sampled = sampled or saw_rng(o)
                c = o.current
                if c and c.result != -1:
                    verdict = c.result == yi           # the engine's own verdict
                    break
                sel = o.select
                if sel is None or c is None:
                    break                              # nothing to drive: undetermined -> None
                if sel.context == _COIN_HEAD:
                    break                              # an unaccounted coin: never choose the flip
                if c.yourIndex != yi:
                    verdict = False                    # passed to the opponent unresolved: no win
                    break
                od = _prune_none(asdict(o))
                if self.boost_lethal:                  # count this-turn boost plays in the running sim
                    self._turn_boosts.observe(od)      # (gated: off -> the cascade is byte-identical)
                chosen = list(self.decide(od))
                if record is not None:
                    osel = od.get("select") or {}
                    opts = osel.get("option") or []
                    picked = [opts[j] for j in chosen if 0 <= j < len(opts)]
                    record.append({
                        "ctx": osel.get("context"), "max": osel.get("maxCount"),
                        "drive": bool(picked) and all(p.get("area") == _PRIZE_AREA for p in picked),
                        "chosen": [self._option_identity(od, osel, p) for p in picked]})
                st = cgapi.search_step(st.searchId, chosen)
            cgapi.search_end()
            if verdict is True and sampled:
                return None                            # confirmed only for THAT shuffle — undetermined
            return verdict                             # (False is left alone: a refute never lies)
        except Exception:
            try:
                cgapi.search_end()
            except Exception:
                pass
            return None
        finally:
            self._planning = was_planning
            self._turn_boosts._by_side = boost_snap        # restore live match state — the sim's own
            self._turn_boosts._last_turn = boost_turn_snap  # boost plays never leak past the verify

    # ═══ THE HEURISTIC RUNGS — rank-grade, never a guarantee (ADR-0031) ═══

    def _gameplan_goal_bonus(self, line_goal: str, board) -> float:
        """The Match Planner seam (ADR-0045 S3): a confidence-scaled sub-prize bump when a candidate Turn
        Line's goal serves the Game Plan's directed Turn Goal — the Game Plan steering the Turn Planner's
        ranking, never beating a prize. Silent unless ``match_planner_steer`` is on and the Game Plan
        directs a goal (withheld on low confidence, so a low-confidence plan never steers)."""
        if not getattr(self, "match_planner_steer", False):
            return 0.0
        gp = getattr(board, "game_plan", None)
        if gp is None or not gp.directed_goal:
            return 0.0
        return (_PLANNER_GAMEPLAN_W * gp.confidence
                if line_goal in _GOAL_LINE.get(gp.directed_goal, ()) else 0.0)

    def _deckout_grind_bonus(self, board) -> float:
        """BUILD 2 (`opp_resource_reads`, DEFAULT OFF): a sub-prize nudge toward pressing a KO/grind line
        when the opponent is near deck-out. ``board.opp_deckout_in_turns`` is SOUND — the opponent's deck
        count is public, so the exhaustion horizon is calibrated, not asserted; the finer "deny their
        LAST prized copy" read is probabilistic (their hand is hidden) and is deliberately NOT used here.
        Silent unless the flag is on AND a near-term deck-out is known; the bump is sub-prize/sub-survival
        (< one KO_SCORE), so it only ranks WITHIN a rung and never reorders a real prize/survival delta
        (ADR-0031 decision 3)."""
        if not getattr(self, "opp_resource_reads", False):
            return 0.0
        t = getattr(board, "opp_deckout_in_turns", None)
        if t is None or t > _PLANNER_DECKOUT_TURNS:
            return 0.0
        return _PLANNER_DECKOUT_W

    def _condition_holds(self, condition, board) -> bool:
        """Evaluate a clause's dynamic ``condition`` gate against the Board — TRUE only when the
        gate is absent or PROVABLY satisfied right now. The two board-checkable gates (Bianca's
        remaining-HP, Jumbo Ice Cream's attached-Energy) are evaluated; any other condition string
        fails closed (never plan on an amount that might not materialise).

        The Active-spot reading of :meth:`_condition_holds_for`, which is the same gate asked of an
        arbitrary body — see there for why both gates are per-TARGET at the card text."""
        return self._condition_holds_for(condition, cur_hp=board.my_active_hp,
                                         attached=board.my_active_energy)

    def _condition_holds_for(self, condition, *, cur_hp: int, attached: int) -> bool:
        """:meth:`_condition_holds` asked of ONE body rather than of my Active (Issue #409) — same
        vocabulary, same fail-closed default, the two board-checkable gates read against ``cur_hp``
        and ``attached`` instead of the Board's Active fields.

        **Both gates are per-TARGET at the card text, verified at source** (`EN_Card_Data.csv`), so
        this is the reading the Active form was a special case of rather than a widening of scope:
        1190 Bianca's Devotion is *"Heal all damage from 1 of your Pokémon that has 30 HP or less
        remaining"* — the HP clause qualifies the CHOSEN Pokémon, not the Active; 1147 Jumbo Ice
        Cream is *"Heal 80 damage from your Active Pokémon that has 3 or more Energy attached"*,
        where the Energy clause likewise qualifies the target and the Active-spot half rides its own
        ``restriction: active_only``. Reading either off the Active while healing a benched body
        would answer a question about the wrong Pokémon."""
        if not condition:
            return True
        if condition == "remaining_hp_30_or_less":
            return bool(cur_hp) and cur_hp <= 30
        if condition == "energy_3_plus":
            return attached >= 3
        return False

    def _heal_candidate(self, cid: int, board, active_stat) -> tuple[int, int] | None:
        """What playing heal-card ``cid`` on my Active would leave: ``(healed_hp, energy_total)``
        — the post-heal HP and the total Energy the Active can still pay an attack with this turn
        (attached after the card's rider, plus the manual attach if unused). Two sources, clause
        first (ADR-0032 4b): an Effect Clause (`kind: heal` with the measured ``amount`` and its
        ``rider``/``restriction``) generalizes the tag path; the `clutch_heal` Function Tag stays
        as the fallback (full heal + bounce — Wally's) for a clause-blind Pilot. None when ``cid``
        heals nothing, a restriction excludes my Active (``mega_only`` on a non-Mega), or the
        clause carries a ``condition`` the closed form can't evaluate (fail-closed: don't plan on
        an amount that might not materialise).

        **The two board-scaled magnitudes (Issue #349) are deliberately NOT read, and that is a
        ruling rather than an omission** — this asks one question, *what does my ACTIVE end up on?*
        ``each_of`` widens the SET a heal reaches and never the amount any one body receives, so 1222
        Fennel's *"Heal 40 damage from each of your Pokémon"* leaves my Active on exactly the 40 a
        single-target 40 would; reading it as a multiplier would credit 200 on a full board and
        manufacture a KO_SCORE-class phantom survival. ``amount_per`` DOES multiply, and ignoring it
        UNDER-credits — this method's own stated error direction, so it stands down from a line that
        would have worked rather than committing to one that would not. No `heal` clause carries it
        today; `_heal_averts_doom` carries the same ruling for the same reason."""
        attach = 0 if board.energy_attached else self._best_hand_attach_units(board.hand_ids, active_stat)
        return self._heal_body_candidate(cid, active_stat, is_active=True,
                                         cur_hp=board.my_active_hp,
                                         attached=board.my_active_energy, attach_units=attach)

    def _heal_body_candidate(self, cid: int, stat, *, is_active: bool, cur_hp: int, attached: int,
                             attach_units: int, max_hp: int | None = None) -> tuple[int, int] | None:
        """:meth:`_heal_candidate` asked of ANY of my bodies — Active **or** benched (Issue #409).
        ``(healed_hp, energy_total)`` for the body described by ``stat`` / ``cur_hp`` / ``attached``,
        or None when no clause of ``cid`` can reach it. The Active form above is this method with the
        Board's Active fields, so the two readings cannot drift.

        The generalization is forced by the HEAL target select (``SelectContext.HEAL``, 17): the
        engine has already resolved the play and is asking WHICH body, so every term is per-target.
        Restriction, condition, healed amount and the rider's Energy consequence are all clause facts
        about the *chosen* Pokémon — Wally's Compassion puts the Energy attached to *that* Pokémon
        into hand, Super Potion discards an Energy from *that* Pokémon — and the Active-only form
        could only ever answer them for one of the candidates.

        ``attach_units`` is the manual attach still available this turn, folded into ``energy_total``
        exactly as the Active form folds it. For a BENCHED body it is what a re-attach could restore,
        never what it can attack with — only the Active swings, which is why
        :meth:`pilot.Pilot._heal_bounce_cost` prices a benched bounce at 0 rather than reading this.

        Issue #349's ``each_of`` / ``amount_per`` stay unread here for the reason
        :meth:`_heal_candidate` gives at length, and that ruling is INHERITED rather than reopened
        (Issue #409 R4): an ``each_of`` card heals every body and so poses no target select at all,
        which is why widening the reading to a second area does not widen the question.

        ``max_hp`` is the CEILING a heal restores to, and it is a parameter because the card's printed
        HP is not always it: a **Hero's Cape** (1159, *"+100 HP"*) puts a 330-HP Mega Starmie ex on a
        board ``maxHp`` of 430, and ``amount: "all"`` heals to that. A caller holding the body dict
        passes its ``maxHp`` and gets the right answer; the default is ``stat.hp``, which is what
        :meth:`_heal_candidate` reads off the Board today and so leaves the shipped survival
        consumers exactly where they were. Measured on `ms_mirror_1001` f90, where the printed
        default under-heals a caped Active by 100."""
        max_hp = int(max_hp) if max_hp else (getattr(stat, "hp", 0) or 0)
        for clause in (self.effects.clauses(cid) if self.effects else ()):
            if clause.get("kind") != "heal":
                continue
            if not self._condition_holds_for(clause.get("condition"), cur_hp=cur_hp,
                                             attached=attached):
                continue                              # gate fails / not board-checkable: fail-closed
            if not self._heal_restriction_targets(clause.get("restriction"), stat,
                                                  is_active=is_active):
                continue
            amount = clause.get("amount")
            healed = max_hp if amount == "all" else min(max_hp, cur_hp + int(amount or 0))
            rider = clause.get("rider")
            if rider == "bounce_energy_to_hand":
                energy_total = attach_units           # all Energy bounced; only re-attach pays
            elif rider == "discard_own_energy":
                energy_total = max(0, attached - 1) + attach_units
            else:
                energy_total = attached + attach_units
            return (healed, energy_total)
        # The legacy Function-Tag fallback stays ACTIVE-ONLY, and deliberately (Issue #409 R3): the
        # tag records "full heal + Energy bounce" and nothing about WHICH bodies the card may reach,
        # so on a benched candidate it would be a guess at a restriction rather than a reading of one
        # — Wally's `mega_only` is a clause fact the tag cannot carry. Fail closed instead; the
        # Active path is unchanged, which is what keeps the shipped survival consumers still.
        if is_active and self.functions and "clutch_heal" in self.functions.tags(cid):
            return (max_hp, attach_units)             # legacy tag path: full heal + Energy bounce
        return None

    def _best_hand_attach_units(self, hand_ids, active_stat) -> int:
        """Energy units the best single attach from MY hand (``hand_ids``) provides my Active — 3
        for a discard-burst special (`discard_eot`, Ignition: CCC) onto an Evolution, 1 for any
        other Energy card, 0 when the hand holds none. `_attach_provision_codes`'s model,
        hand-scanned: the 6858 heal-then-attach line re-powers Nebula Beam with the bounced-around
        Ignition, and a heal whose re-attach doesn't exist can no longer fake a preserved KO. Also
        the gust-affordability read (`_board`'s ``payable`` — the f31 no-energy gust gate).

        The per-card provision is `CombatMath.provision_codes` since Issue #418, so the hand leg and
        the board leg cannot disagree about what one Ignition is worth on one holder."""
        best = 0
        for cid in hand_ids:
            st = self.stats.get(cid) if self.stats else None
            if st is None or getattr(st, "hp", 0):
                continue
            tags = self.functions.tags(cid) if self.functions else []
            # an Energy card: a typed Energy, a Basic/Special by cardType, or the colourless
            # discard-burst special (engine reports Ignition's energyType as 0 — cf `_has_reusable_energy`)
            if not (getattr(st, "energyType", 0) not in (None, 0)
                    or st.is_energy
                    or "discard_eot" in tags):
                continue
            best = max(best, len(self.combat.provision_codes_or_floor(cid, active_stat)))
        return best

    def _plan_fingerprint(self, obs, select) -> tuple:
        """A hashable/comparable snapshot of everything a plan depends on — the turn, both boards
        (id / energy / HP per Pokémon), my hand, my prize count, the manual-attach flag, and the option
        signature. Any reveal (a draw, a search, a KO, a new turn) changes it, so the cache re-plans; an
        unchanged board reuses the committed line."""
        cur = obs.get("current") or {}
        me, opp = self._my_player(obs), self._opp_player(obs)

        def body(p):
            return (p.get("id"), len(p.get("energies") or []), p.get("hp")) if p else None

        def side(pl):
            return (tuple(body(x) for x in (pl.get("active") or [])),
                    tuple(body(x) for x in (pl.get("bench") or [])))

        hand = tuple(sorted(c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None))
        opts = tuple((o.get("type"), o.get("attackId"), o.get("area"), o.get("index"),
                      o.get("inPlayArea"), o.get("inPlayIndex")) for o in (select.get("option") or []))
        return (cur.get("turn"), side(me), side(opp), hand, len(me.get("prize") or []),
                bool(cur.get("energyAttached")), opts)

    def _ko_for_prizes_lines(self, obs, select, board, options, traces) -> list:
        """The **KO-for-prizes** goal (ADR-0031 phase 1-2): multi-step enabling lines that unlock an
        otherwise-missed KO of the opponent's Active, each valued by the leaf-eval scalar (prizes
        dominant + my Active's survival vs Incoming + the threat removed). One candidate per enabling
        first-step (retreat into a benched attacker; evolve the Active; play an energy-tutor
        Supporter), each regressed to "does this body, after the step PLUS this turn's one attach,
        KO?" and evaluated at its end-of-turn board. Empty when no such line exists."""
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp"):
            return []
        opp_player = self._opp_player(obs)
        # Every line's attach capacity is the TYPED Attach Budget built for its OWN attacker
        # (ADR-0075) — each builder calls `_ko_line_pricing` itself, because the Budget is per target
        # body and cannot be computed once for the menu. The retired `extra + accel_*` count and the
        # `enabler_consumes_supporter` split it needed are both subsumed: the manual attach is a leg
        # of the Budget, and a line that plays a Supporter as its enabling step passes
        # `supporter_spent=True` rather than zeroing a separate accel term.
        threat = self._threat_magnitude(opp)
        lines = []
        for i, o in enumerate(options):
            cost = 0.0                                    # cheapest-enabler tier (ADR-0031): an enabler
                                                          # that PRESERVES deck/slot resources outranks a
                                                          # tutor reaching the SAME KO; 0 = the scarce
                                                          # Supporter tutor (last), sub-prize throughout
            if o.get("type") == _RETREAT:
                cand = self._retreat_ko_candidate(obs, board, opp, opp_player)
                kind, cost = "retreat", _PLANNER_ENABLER_FREE   # spends no card/slot — a free enabler
            elif o.get("type") == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                cand = self._evolve_ko_candidate(obs, select, board, o, opp, opp_player)
                kind, cost = "free evolve", _PLANNER_ENABLER_FREE
            elif o.get("type") == _EVOLVE and o.get("inPlayArea") == _BENCH:
                retreat_on_menu = any(x.get("type") == _RETREAT for x in options)
                cand = self._free_evolve_ko_candidate(obs, select, board, o, opp, opp_player,
                                                      retreat_on_menu)
                kind, cost = "free evolve", _PLANNER_ENABLER_FREE
            elif o.get("type") == _PLAY and self._is_evolution_tutor(obs, select, o):
                retreat_on_menu = any(x.get("type") == _RETREAT for x in options)
                cand = self._tutor_evolve_ko_candidate(obs, board, opp, opp_player, retreat_on_menu)
                kind = "evolution tutor"                  # a Supporter — least-preferred enabler (cost 0)
            elif (o.get("type") == _PLAY and getattr(self, "enabler_item_composer", False)
                  and self._is_item_pokemon_tutor(obs, select, o)):
                retreat_on_menu = any(x.get("type") == _RETREAT for x in options)
                cand = self._item_evolve_ko_candidate(obs, select, board, o, opp, opp_player,
                                                      retreat_on_menu)
                kind, cost = "item tutor", self._item_enabler_cost(board)   # BUILD 4: the Item's edge over
                #                       the scarce Supporter tutor is CONDITIONAL on preserving the slot
            elif (o.get("type") == _PLAY and getattr(self, "enabler_item_composer", False)
                  and self._is_rare_candy(obs, select, o)):
                retreat_on_menu = any(x.get("type") == _RETREAT for x in options)
                cand = self._rare_candy_ko_candidate(obs, select, board, o, opp, opp_player,
                                                     retreat_on_menu)
                kind, cost = "rare candy", self._item_enabler_cost(board)   # BUILD 1: a Basic->Stage2 skip
                #                       Item — tiered like the item tutor (slot-preservation credit)
            elif o.get("type") == _PLAY:
                cand = self._supporter_ko_candidate(obs, select, board, o, opp, opp_player)
                kind = "energy tutor"
            else:
                continue
            if cand is None:
                continue
            prizes, survives, *rest = cand
            # ADR-0074 decision 4 (#175): the prize term is weighted by P(the line's Energy is
            # really there) for the RANKED consumers that carry one. The hard-rung invariant is
            # restated in expectation — a positional score can never outrank a REALISABLE prize —
            # so a line that is unlikely to happen can now lose to one that will. Candidates
            # carrying no probability pass 1.0 and are byte-identical to before.
            line_p = max(0.0, min(1.0, float(rest[0]))) if rest else 1.0
            value = self._leaf_value(prizes=prizes * line_p, active_survives=survives,
                                     threat_removed=threat)
            value += self._gameplan_goal_bonus("ko_for_prizes", board)       # ADR-0045 seam (S3)
            value += self._deckout_grind_bonus(board)                        # BUILD 2 seam (opp_resource_reads)
            value += cost                                 # sub-prize/sub-survival: breaks a same-KO tie
                                                          # among enablers, never over a real prize delta
            odds = "" if line_p >= 1.0 else f" at p={line_p:.2f}"
            lines.append(TurnLine(next_step=[i], goal="ko_for_prizes", value=value,
                                  rationale=(f"plan (ko_for_prizes): {kind} unlocks a "
                                             f"{int(prizes)}-prize KO{odds}")))
        return lines

    def _ko_key_threat_lines(self, obs, select, board, options) -> list:
        """The **KO-the-key-threat** goal (the Goal Ladder's middle rung, CONTEXT.md *Turn Goal*;
        `planner_key_threat`): ENABLING lines that unlock a bench-snipe KO of the opponent's benched
        TOP-threat body — the greatest shared threat rank (`_body_threat_rank`: eventual attack
        power, forward evolution, energized/hand-size boosts). A snipe-KO already ON the menu needs
        no rung (the Tactical layer credits its prize KO_SCORE-class), but no closed-form hook scores
        the STEP that reaches one — `_retreat_to_lethal_tactical` and the KO-for-prizes generators
        test KOs of the ACTIVE only — so a retreat into the sniper, an evolve that brings the snipe
        attack online, or the energy tutor that powers it is invisible to the greedy scorer and the
        biggest future attacker survives. Bench snipes ignore W/R so ``rider >= hp`` is the exact KO
        test (`_snipe_ko_prizes`'s rule), and a Tera body is snipe-immune. Candidates join the
        KO-for-prizes pool: the leaf scalar ranks across the rungs (prizes dominant, then the removed
        threat's magnitude)."""
        opp_player = self._opp_player(obs)
        bench = [p for p in (opp_player.get("bench") or []) if p]
        if not bench:
            return []
        ranked = [(self._body_threat_rank(obs, p, board.read, board.posture_confidence), p)
                  for p in bench]
        if getattr(self, "ko_target_whiff", False):
            # BUILD 1 (DEFAULT OFF): among EQUAL-threat-rank targets prefer the one the opponent is
            # LEAST able to replace — lowest `copies_left_odds` of its own line. Threat rank stays the
            # dominant key, so this is a pure tiebreak; it never promotes a lesser threat. Fails OPEN
            # (`copies_left_odds` → 1.0 for an unrecognized opponent, so all-equal → no reorder).
            top_rank, top = max(ranked, key=lambda t: (t[0], -self._whiff_odds(board, t[1])))
        else:
            top_rank, top = max(ranked, key=lambda t: t[0])
        top_stat = self.stats.get(top.get("id")) if self.stats else None
        own_mag = float(getattr(top_stat, "maxDamage", 0) or 0) if top_stat else 0.0
        fwd_fn = getattr(self.stats, "forward_max_damage", None)
        fwd_mag = float(fwd_fn(top.get("id")) or 0) if fwd_fn is not None else 0.0
        threat_mag = max(own_mag, fwd_mag)             # the SAME damage basis the rank uses — a
                                                       # 0-printed body with a monster forward line
                                                       # (the Evolving-Threat case) still counts
        hp = top.get("hp", 0)
        if top_rank <= 0 or threat_mag <= 0 or not hp or self._is_tera(top.get("id")):
            return []                                 # nothing benched actually threatens (or Tera-immune)
        me = self._my_player(obs)
        opp = self._opp_active(obs)
        others = [p for p in ([opp] + [p for p in bench if p is not top]) if p]
        extra = 1 if (board.reusable_energy_in_hand and not board.energy_attached) else 0
        prizes = self._prize_value(top)
        lines = []
        for i, o in enumerate(options):
            if o.get("type") == _RETREAT:
                cand = self._retreat_snipe_candidate(me, others, hp, extra)
                kind = "retreat"
            elif o.get("type") == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                evolved_id = self._option_card_id(obs, select, o)
                if not self._affords_snipe_ko(evolved_id, board.my_active_energy + extra, hp):
                    continue
                estat = self.stats.get(evolved_id) if self.stats else None
                my_hp = getattr(estat, "hp", 0) or 0
                cand = (bool(my_hp) and self._incoming_worst(evolved_id, my_hp, others) < my_hp)
                kind = "evolve"
            elif o.get("type") == _PLAY:
                if (board.energy_attached or board.reusable_energy_in_hand
                        or not self._is_energy_tutor(obs, select, o)):
                    continue                          # mirrors `_supporter_ko_candidate`'s gate
                cand = self._retreat_snipe_candidate(me, others, hp, extra=1)
                kind = "energy tutor"
            else:
                continue
            if cand is None:
                continue
            value = self._leaf_value(prizes=prizes, active_survives=bool(cand),
                                     threat_removed=threat_mag)
            if (getattr(self, "objectives_path", False)          # Tier-3 (ADR-0040): a key threat ON my
                    and top.get("id") in board.path_target_ids):  # cheapest Prize Path advances the MATCH
                value += _PLANNER_PATH_W                          # win — sub-prize bump, ranks within rung
            value += self._gameplan_goal_bonus("ko_key_threat", board)       # ADR-0045 seam (S3)
            value += self._deckout_grind_bonus(board)                        # BUILD 2 seam (opp_resource_reads)
            lines.append(TurnLine(
                next_step=[i], goal="ko_key_threat", value=value,
                rationale=f"plan (ko_key_threat): {kind} unlocks the snipe-KO of the benched key threat"))
        return lines

    # ═══ THE GAMBLE RUNG — Tier-2 (ADR-0039): closed-form expectimax over Outcome Classes ═══
    # Deliberately probabilistic and BELOW every deterministic goal: it runs only when the win rung
    # and the whole heuristic pool passed. Exact probabilities (tracker-anchored hypergeometrics),
    # closed-form branch values, NO engine sim through the chance node (a fork is ONE predicted
    # determinization — untrusted for prediction-dependent outcomes). Depth-1 by construction.

    def _best_gamble_line(self, obs, select, board, options, traces):
        """The best **Gamble Line** on this menu, or None: play a Hand Refresh (`shuffle_hand`)
        FIRST — before the turn's attach — because the draw probably yields the Energy that turns
        this turn into a KO the held hand cannot reach (the Lillie's-Determination class,
        ADR-0039/REQ-GAMBLE-0001).

        EV = P(enabling Outcome Class) × the enabled KO's tactical value, exact hypergeometric over
        the shuffle-grown pool (tracker-anchored counts + the returned hand); committed only when it
        beats the DETERMINISTIC baseline (the best menu tactical, or the best after-attach chip the
        held Energy reaches) — EV equality is the break-even, never a fixed threshold. Stands down:
        switch off / mid-sim (the engine re-run stays deterministic policy) / turn 1 / attach already
        spent / a KO already on the tuned menu / a protected hand (wincon, line piece, ACE-SPEC Tool
        — the keep-value floors own those shuffles) / pre-anchor (no exact counts, mirroring
        `dont-refresh-into-a-probable-miss`) / the hand already holds an enabler (just attach it).

        Records its full working — or WHY it stood down — on ``self._gamble_trace``, the sparse
        `gamble` block of Decision Telemetry (ADR-0019): the blunder shell shows it as a dropdown so
        a shuffle/fetch correction can see every number behind the (non-)gamble. Never recorded
        mid-sim (an engine re-run must not clobber the live decision's trace)."""
        def stand_down(why):
            if not self._planning:
                self._gamble_trace = {"considered": False, "why": why}
            return None
        if self._planning:
            return None                             # mid engine-sim: silent, never clobber the trace
        if not getattr(self, "gamble_lines", False):
            return stand_down("feature off (gamble_lines)")
        if board.turn <= 1:
            return stand_down("turn 1")
        if board.energy_attached:
            return stand_down("attach already spent this turn")
        if board.active_can_ko:
            return stand_down("active already reaches a KO")
        if any(t.tactical >= KO_SCORE for t in traces):
            return stand_down("a KO is already on the tuned menu")
        # WP6: the binary protected-hand stand-downs (wincon / line pre-evo / ACE-SPEC Tool in hand)
        # are REPLACED by the graded keep-cost priced into the det baseline below — a wincon with its
        # tutors live shuffles cheap, an irreplaceable one-of near its full role value (the currency-
        # zone rule: replace the guard family, never bolt on beside it).
        from common.strategy.doctrines.doctrine_shuffle_refresh import _draw_branches
        me = self._my_player(obs)
        hand = [c for c in (me.get("hand") or []) if c and c.get("id") is not None]
        hand_ids = [c.get("id") for c in hand]                # WP6: for the shuffle keep-cost
        ma = next((p for p in (me.get("active") or []) if p), None)
        opp = self._opp_active(obs)
        hp = (opp or {}).get("hp", 0)
        stat = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        if not (hp and stat and ma):
            return None
        discard_basic_types = {                               # WP1: Basic-Energy types in my visible
            st.energyType for c in (me.get("discard") or [])  # discard — the recycle closure's source
            if c and (st := self.stats.get(c.get("id"))) is not None
            and st.is_basic_energy and st.energyType is not None}
        # WP2 — the closure-COUNTS the classes are built over, and the window `hit` that prices them.
        # ANCHORED (prizes resolved): exact deck counts, a plain window hypergeometric. PRE-ANCHOR:
        # the decklist is still fully known (own deck) — only the prize assignment of unseen copies is
        # random, so build the classes over the unseen counts (`decklist − visible`) and price with the
        # prize-split-weighted window sum. The old `if not deck_known_counts: return None` priced EVERY
        # pre-anchor gamble at ZERO — the modeling-gap-as-caution failure the whole spec attacks.
        counts = board.deck_known_counts
        anchored = bool(counts)
        if anchored:
            class_counts = counts
            deck_count = sum(counts.values())
            prizes_hidden = 0
        else:
            from collections import Counter as _Counter
            unseen = _Counter(self.deck)
            unseen.subtract(self._visible_card_counts(me))    # copies provably outside deck+prizes
            class_counts = {cid: n for cid, n in unseen.items() if n > 0}
            prizes_hidden = sum(1 for p in (me.get("prize") or [])
                                if not (isinstance(p, dict) and p.get("id") is not None))
            deck_count = sum(class_counts.values()) - prizes_hidden   # hidden deck cards (H − prizes)
            if deck_count <= 0 or not class_counts:
                return stand_down("pre-anchor: deck bookkeeping unresolved")
        classes = self._gamble_ko_classes(board, stat, ma, opp, hp, class_counts, hand, discard_basic_types)
        classes = classes + self._gamble_evolution_ko_classes(obs, board, ma, opp, class_counts, hand)
        classes = classes + self._gamble_pump_ko_classes(obs, board, stat, ma, opp, hp, class_counts, hand)
        classes = classes + self._gamble_gust_ko_classes(obs, board, ma, self._opp_player(obs), hand,
                                                         class_counts)
        classes = classes + self._gamble_survival_classes(obs, board, me, class_counts, hand)
        if not classes:
            return stand_down("no one-enabler-short KO class on this board")
        det = self._gamble_det_baseline(board, stat, ma, opp, hp, traces, hand)
        pool = deck_count + max(0, len(hand) - 1)             # the shuffle-grown draw pool
        burst_copies = self._gamble_burst_copies(class_counts, hand, stat)   # the recovery class (below)
        from common.deck_odds import draw_hit_probability, draw_hit_with_engines
        if anchored:
            def hit(cp, n):
                return draw_hit_probability(cp, pool, n)
        else:
            def hit(cp, n):
                return self._prize_split_hit(cp, deck_count, prizes_hidden, pool, n)
        # WP4 — the Stage-2 draw-engine windows, per class (the class's own sought/supplement ids are
        # EXCLUDED so a Drakloak that is itself the sought evolution never double-counts). Engines are
        # an ANCHORED-only sharpening: pre-anchor the prize-split window stays plain (under-count,
        # never a guess about where the engine copies sit).
        class_engines = []
        for _c, _v, _l, sought, (_sc, sup_ids) in classes:
            if anchored:
                class_engines.append(self._gamble_draw_engines(
                    me, class_counts, set(sought) | set(sup_ids)))
            else:
                class_engines.append((0, (), []))
        best = None                                           # (ev, index, rationale)
        evals = []                                            # per (refresh option × class) working rows
        for i, o in enumerate(options):
            if o.get("type") != _PLAY:
                continue
            cid = self._option_card_id(obs, select, o)
            ns = _draw_branches(cid, board)
            if (ns is None or cid is None or not self.functions
                    or "shuffle_hand" not in self.functions.tags(cid)):
                continue
            # The Supporter-tutor supplement is live only for an ITEM refresh (Unfair Stamp) with the
            # one-per-turn Supporter slot unspent — a Supporter refresh spends the slot, so a drawn
            # Supporter tutor is dead in ITS window (spec §Missing, the 4-of-5 rule).
            rst = self.stats.get(cid) if self.stats else None
            sup_live = bool(rst is not None and getattr(rst, "is_item", False)
                            and not board.supporter_played)
            # WP6: the KEEP-COST of shuffling this refresh's hand away (the played refresh itself is
            # discarded, not shuffled) — Σ role value × (1 − re-access odds) over the shuffle redraw,
            # via the shared `_hand_keep` (duplicates priced marginally; one summation with the SHED).
            # The gamble must beat det PLUS this graded floor, replacing the binary protected-hand
            # stand-downs: a KO (≈ KO_SCORE) dwarfs it, an irreplaceable one-of raises the bar.
            hand_keep = self._hand_keep(hand_ids, cid, class_counts, pool, max(ns), board,
                                        prizes_hidden=prizes_hidden, deck_count=deck_count)
            # The refresh CHAIN (spec failure mode B, hand-expansion — built 2026-07-19): a drawn
            # shuffle-refresh inside this window is a fresh full window at the same outs — a drawn
            # Unfair Stamp (Item; live iff one of MY Pokémon was KO'd during their last turn) or a
            # drawn Supporter refresh (live only post-Item-refresh, the `sup_live` slot rule).
            # Anchored-only, like the draw engines (never a guess about where the copies sit).
            ch_c, ch_w = (self._gamble_chain_refreshes(class_counts, sup_live, board)
                          if anchored else (0, 0))
            for (copies, ko_value, label, sought, (sup_copies, _sup_ids)), (e_cp, e_ws, _e_ids) \
                    in zip(classes, class_engines):
                eff = copies + (sup_copies if sup_live else 0)
                if e_cp:
                    # WP4: the missed refresh may still hit a usable draw engine — its window digs
                    # the SAME class outs over the thinned pool (the two-window closed form).
                    p = sum(draw_hit_with_engines(eff, pool, n, e_cp, e_ws) for n in ns) / len(ns)
                else:
                    p = sum(hit(eff, n) for n in ns) / len(ns)
                if ch_c and ch_w:
                    # The chain branch conditions on missing EVERY counted out AND engine, so it is
                    # DISJOINT from the mass above — exactly additive (clamped for safety). Its
                    # fresh window prices the class's RAW copies (no Supporter supplement: a drawn
                    # Supporter refresh spends the slot; conservative for a drawn Stamp) over the
                    # re-shuffled pool (−1, the chain card itself is spent). Chains inside the
                    # chain are not modeled — an endorser under-counts.
                    boost = sum(max(0.0, draw_hit_probability(eff + e_cp + ch_c, pool, n)
                                    - draw_hit_probability(eff + e_cp, pool, n))
                                for n in ns) / len(ns)
                    p = min(1.0, p + boost * draw_hit_probability(copies, max(0, pool - 1), ch_w))
                ev = p * ko_value
                if burst_copies and det > 0:
                    # the RECOVERY class: the miss branch may still redraw the held burst Energy
                    # (returned to the pool by the shuffle) and bank the same after-attach chip the
                    # deterministic line held — the "no {W}, but the Ignition came back → Nebula
                    # anyway" branch. Independence approximation on the conditional (documented;
                    # errs small, and only ever ADDS honest EV to the miss side).
                    p_re = sum(hit(burst_copies, n) for n in ns) / len(ns)
                    ev += (1 - p) * p_re * det
                row = {"i": i, "cid": cid, "draws": max(ns), "label": label,
                       "p": round(p, 3), "ev": round(ev, 1)}
                if sup_live and sup_copies:
                    row["post_item_sup"] = sup_copies         # the Item-refresh Supporter supplement
                if ch_c and ch_w:
                    row["chain_refresh"] = [ch_c, ch_w]       # drawn-refresh chain: copies, window
                if hand_keep:
                    row["keep"] = round(hand_keep, 1)         # WP6: the shuffled-hand keep-cost floor
                evals.append(row)
                bar = det + hand_keep                         # WP6: beat the held line + the keep-cost
                if ev > bar and (best is None or ev - hand_keep > best[0]):
                    best = (ev - hand_keep, i,
                            f"gamble: {p:.0%} the {max(ns)}-card draw finds {label} for the KO "
                            f"(EV {ev:.0f} > held line {det:.0f} + keep {hand_keep:.0f})")
        self._gamble_trace = {                     # the full working, win or stand-down (ADR-0019)
            "considered": True, "anchored": anchored, "prizes_hidden": prizes_hidden,
            "pool": pool, "det": round(det, 1), "burst": burst_copies,
            "classes": [{"label": la, "copies": c, "value": round(v, 1), "sought": s,
                         **({"post_item_sought": si, "post_item_copies": sc} if sc else {}),
                         **({"engine_copies": ec, "engine_windows": list(ew), "engine_ids": ei}
                            if ec else {})}
                        for (c, v, la, s, (sc, si)), (ec, ew, ei) in zip(classes, class_engines)],
            "evals": evals,
            "best": ([best[1], round(best[0], 1)] if best is not None else None)}
        if best is None:
            return None
        return TurnLine(next_step=[best[1]], goal="gamble", value=best[0], rationale=best[2])

    def _prize_split_hit(self, u: int, deck_count: int, prizes_hidden: int, pool: int, draws: int,
                         certain: int = 0) -> float:
        """WP2: P(≥1 enabler in the ``draws``-card refresh) PRE-ANCHOR — the decklist is fully known,
        only the prize assignment of the class's ``u`` unseen enabler copies is random. Sum over
        ``j`` = copies-that-landed-in-the-deck of the hypergeometric prize-split weight × the window
        draw with ``j`` copies: ``Σ_j [C(deck,j)·C(prizes,u−j)/C(deck+prizes,u)] × hit(j, pool, n)``
        — ≤ ``u+1`` plain ``math.comb`` terms (``u ≤ 4`` in practice). The exact closed form the
        ``if not deck_known_counts: return None`` gate replaced with a zero (the modeling-gap-as-
        caution failure the fetch-closure spec attacks). Never raises; bad input → 0.0 (an endorser
        fails closed). Degenerates to the plain window draw when no prizes are hidden.

        ``certain`` = outs KNOWN to be in the drawn pool regardless of the split — the keep-cost
        side's own held copies, shuffled in from HAND (never prize-assignable). They join every
        branch's window draw (``hit(j + certain, …)``); the gain side passes the default 0."""
        from math import comb
        from common.deck_odds import draw_hit_probability
        try:
            u, d, k, certain = int(u), int(deck_count), int(prizes_hidden), int(certain)
        except Exception:
            return 0.0
        if u <= 0 or d <= 0:
            # no unseen outs to split (or no deck for them to sit in) — only the certain copies draw
            return draw_hit_probability(certain, pool, draws) if certain > 0 else 0.0
        if k <= 0:
            return draw_hit_probability(u + certain, pool, draws)   # no hidden prizes -> every copy in deck
        h = d + k
        u = min(u, h)                                          # can't split more copies than positions
        denom = comb(h, u)                                     # u ≤ h -> comb(h, u) > 0, no zero-div
        total = 0.0
        for j in range(max(0, u - k), min(u, d) + 1):          # j = enabler copies landing in the deck
            total += comb(d, j) * comb(k, u - j) / denom * draw_hit_probability(j + certain, pool, draws)
        return max(0.0, min(1.0, total))

    def _gamble_burst_copies(self, counts: dict, hand: list, stat) -> int:
        """Copies (pool-wide, INCLUDING the returned hand copy) of a held `discard_eot` burst Energy
        that funds an attack of my Active by COUNT — the recovery-class enabler: a miss that redraws
        it re-banks the deterministic after-attach line. 0 when no such burst is held."""
        best = 0
        for c in hand:
            cid = c.get("id")
            est = self.stats.get(cid) if (self.stats and cid is not None) else None
            if not est or getattr(est, "hp", 1) != 0:
                continue
            tags = self.functions.tags(cid) if self.functions else []
            if "discard_eot" not in tags:
                continue
            in_hand = sum(1 for c2 in hand if c2.get("id") == cid)
            best = max(best, counts.get(cid, 0) + in_hand)
        return best

    def _closure_stat_of(self, cid):
        return self.stats.get(cid) if (self.stats and cid is not None) else None

    def _closure_clauses_of(self, cid):
        return self.effects.clauses(cid) if self.effects else ()

    def _card_reaccess_outs(self, cid, counts: dict) -> int:
        """WP6/WP7: the copies in my DECK that re-access card ``cid`` once it is shuffled back in — the
        `common.fetch_closure` graph pointed BACKWARDS. Delegates to the ONE shared closure module
        (ADR-0065) so the gamble gain side and the keep-cost read the same implementation."""
        from common import fetch_closure
        return fetch_closure.reaccess_outs(cid, counts, self._closure_stat_of, self._closure_clauses_of)

    def _role_value(self, cid) -> float:
        """WP6/WP7: card ``cid``'s base worth = the MAX claim over its declared / derived Roles
        (`_roles_of` + the line-member derivation below), its behavioural tags (`TAG_TIER` — the
        worth-coverage fix for situational Trainers/special Energy), and the energy / ACE-SPEC
        fallbacks. Delegates to `card_worth.role_value` (ADR-0065) — the ONE currency zone; the Pilot
        only supplies facts.

        **Line-member worth derivation (Round 9 'derive first'; the discard-shadow finding on
        86091435-68).** A non-payoff win-condition Line member (`_line_preevo_set`: Dreepy AND the
        middle Drakloak on Dreepy→Drakloak→Dragapult ex) is worth its `win_condition_base` tier even
        when the deck declared only the base — a Line stage is a plan piece, not junk. WORTH-ONLY: the
        Line-membership fact enters the value currency here but NOT `_roles_of` / `c.roles`. That
        separation outlived its original reason — it kept the tuned discard ladder's routing intact
        across the seam-D migration, and Issue #261 item 2h deleted that ladder — but it stands on its
        own: worth is what a card is WORTH, and `c.roles` is what the deck DECLARED, and a derived
        Line membership is the first and not the second."""
        from common.card_worth import role_value
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        roles = self._roles_of(cid)
        if cid is not None and cid in self._line_preevo_set():
            roles = [*roles, "win_condition_base"]      # derived worth only — not injected into c.roles
        return role_value(
            roles,
            is_ace_spec=bool(st is not None and getattr(st, "aceSpec", False)),
            is_typed_basic_energy=bool(st is not None and getattr(st, "is_typed_basic_energy", False)),
            tags=self.functions.tags(cid) if (self.functions and cid is not None) else ())

    def _keep_cost(self, cid, counts: dict, pool: int, draws: int, board=None,
                   shuffled_copies: int = 1, prizes_hidden: int = 0, deck_count=None) -> float:
        """WP6/WP7: the cost of shuffling ONE held copy of card ``cid`` away = its role worth × how
        UN-recoverable it is (``1 − P(re-draw or re-fetch it in `draws`)`` over the shuffle-grown
        ``pool``, +``shuffled_copies`` outs for the held copies rejoining the deck — 1 for a lone copy;
        a hand-wide summation passes the full duplicate count, `_hand_keep`) × how realisable its role
        is by its deadline (`_deploy_odds`, the gate library — ADR-0065: an undeployable evolution or
        a dead fetcher collapses to 0, shed freely). ``board`` supplies the gate facts; omitted → the
        deadline factor stays 1.0.

        PRE-ANCHOR (``prizes_hidden`` > 0, ``counts`` = the unseen composition): the re-access odds
        are PRIZE-SPLIT-WEIGHTED (`_prize_split_hit`) — the unseen outs split over deck + face-down
        prizes exactly like the gamble's GAIN side, while the shuffled held copies join the pool as
        ``certain`` outs (a hand card is never prize-assignable). Without the weighting the cost side
        counted possibly-prized outs at full strength against a prize-free pool — re-access
        overestimated, keep under-charged, a pre-anchor pro-gamble bias the gain side never had.
        Anchored (``prizes_hidden`` = 0): the plain window draw, unchanged."""
        role_value = self._role_value(cid)
        if role_value <= 0:
            return 0.0
        from common import gate_library
        from common.card_worth import keep_cost
        from common.deck_odds import draw_hit_probability
        outs = self._card_reaccess_outs(cid, counts)
        certain = max(1, shuffled_copies)
        if prizes_hidden > 0:
            d = deck_count if deck_count is not None else max(0, sum(counts.values()) - prizes_hidden)
            reaccess = self._prize_split_hit(outs, d, prizes_hidden, pool, draws, certain=certain)
        else:
            reaccess = draw_hit_probability(outs + certain, pool, draws)
        # The pressure gate (Round 8 §3, the CLOSING edge): a doom-answering card's re-access is not
        # bankable against its deadline — the credit zeroes and the card charges full worth.
        reaccess = gate_library.closing_gate_reaccess(
            reaccess, gate_closing=self._gate_closing(cid, board) if board is not None else False)
        deadline = self._deploy_odds(cid, board, counts) if board is not None else 1.0
        return keep_cost(role_value, reaccess, deadline)

    def _gate_closing(self, cid, board) -> bool:
        """The closing-edge resolver (Round 8 §3: a closing gate SPIKES keep — re-access is not
        bankable against a THIS-TURN deadline, so the card charges full worth). Two closing edges:

        **Deploy-now (ep86091435 f68):** ``cid`` is a hand evolution with an ELIGIBLE in-play base
        this turn (`Board.deploy_now_ids`) — evolving is a live tempo play; pitching/shuffling it
        forfeits the play and re-access can't help (you need it NOW). Fires regardless of doom, and
        REGARDLESS of a same-card copy in play (the benched copy does not cover THIS body's
        evolution — the covered-vs-open discrimination a flat floor misses, ep83686860 f18 keeps
        pitching correctly because its base was placed this turn, so it is NOT in ``deploy_now_ids``).

        **Pressure (the fold of `hold-successor-when-doomed`, ep83037962 f49):** the Active is DOOMED
        and ``cid`` ANSWERS the doom — the SUCCESSOR (a win-condition with a Line pre-evolution in
        play) or an emergency `clutch_heal` / `switch`. Sound facts only; a healthy board with no
        deploy-now keeps the closure discount, so cycling stays free."""
        if cid is not None and cid in getattr(board, "deploy_now_ids", frozenset()):
            return True
        if not getattr(board, "active_doomed", False):
            return False
        if cid in self._wincon_set() and getattr(board, "line_preevo_in_play", False):
            return True
        tags = self.functions.tags(cid) if self.functions else ()
        return "clutch_heal" in tags or "switch" in tags

    def _hand_keep(self, hand_ids, played_cid, counts: dict, pool: int, draws: int, board=None,
                   prizes_hidden: int = 0, deck_count=None) -> float:
        """Σ keep_cost over the hand a refresh shuffles away — the ONE summation BOTH keep-value sites
        read (the WP6 gamble keep-floor below and the refresh SHED, `pilot._refresh_shed_keepcost`), so
        the graded floor is identical by construction. ``hand_ids`` is the hand as a LIST — duplicate
        copies are real cards. The played refresh ``played_cid`` is excluded ONCE (it is discarded, not
        shuffled; a second held copy still shuffles and still charges). Duplicates price MARGINALLY
        (sets-not-sums, spec §Round 7): all k held copies of a card land in the deck together, so each
        copy's re-access odds count all k shuffled siblings as outs — the k-th duplicate is discounted
        by the copies shuffled with it, neither k independent one-ofs (the pre-reconciliation gamble
        over-charge) nor free riders (the pre-reconciliation SHED's frozenset dedup). Pre-anchor,
        ``prizes_hidden`` / ``deck_count`` thread the prize-split weighting into each copy's re-access
        odds (`_keep_cost`); anchored callers pass ``prizes_hidden=0``.

        The QUOTA GATE (spec Round 8 §2, `gate_library.quota_window`): duplicate copies of a
        once-per-turn card (Energy — the manual attach; Supporter — the slot, rules.md §3) charge by
        RANK — the j-th copy's deadline sits j−1 turns away (+1 when this turn's quota is spent:
        `energy_attached`; `supporter_played` or the played refresh itself being a Supporter), and
        each intervening turn widens its re-access window by the natural draw. Rank 1 with the quota
        live is the plain window; non-quota cards keep the uniform marginal price."""
        ids = list(hand_ids)
        if played_cid in ids:
            ids.remove(played_cid)
        from collections import Counter
        from common import gate_library
        played_st = self.stats.get(played_cid) if (self.stats and played_cid is not None) else None
        sup_spent = bool(getattr(board, "supporter_played", False)
                         or (played_st is not None and getattr(played_st, "is_supporter", False)))
        total = 0.0
        for cid, k in Counter(ids).items():
            st = self.stats.get(cid) if self.stats else None
            if st is not None and getattr(st, "is_energy", False):
                spent = bool(getattr(board, "energy_attached", False))
            elif st is not None and getattr(st, "is_supporter", False):
                spent = sup_spent
            else:
                total += k * self._keep_cost(cid, counts, pool, draws, board, shuffled_copies=k,
                                             prizes_hidden=prizes_hidden, deck_count=deck_count)
                continue
            total += sum(self._keep_cost(cid, counts, pool,
                                         gate_library.quota_window(draws, j, quota_spent=spent),
                                         board, shuffled_copies=k,
                                         prizes_hidden=prizes_hidden, deck_count=deck_count)
                         for j in range(1, k + 1))
        return total

    def _deploy_odds(self, cid, board, counts: dict) -> float:
        """The deadline gate (`common.gate_library`, ADR-0065): P(card ``cid``'s role is realisable
        by its deadline). Two card classes are gated today; everything else stays 1.0.

        **Evolution gate (Stage 1):** 1.0 for a playable evolution, 0.0 for a provably-unplayable
        one — nothing it can be put onto can reach the board. Errs toward 1.0 (keep): pre-anchor
        ``counts`` is the unseen deck, so a base still in the decklist keeps its evolution live —
        the gate bites only a genuinely dead card (ml ep83966336 f44: a Mega Lucario ex with every
        Riolu evolved/gone).

        That question is `common.playability`'s (ADR-0104), not this method's, and Issue #288 is why:
        the version inlined here compared ONE ``evolvesFrom`` name against the three zones, which
        gets two cases wrong. It called a Metagross live because a Metang sat in hand with every
        Beldum gone (the chain), and it called `grimmsnarl_ex`'s win condition DEAD whenever its
        Stage 1 was gone even with a Rare Candy in hand (the escape — card text at
        data/EN_Card_Data.csv id 1079). The eligibility gate in `pilot._resolve_needs` asks the same
        question, so the two must answer off one oracle or silently disagree about the same card.

        **Fetcher gate (searcher/recycler leg — acceptance pin ep83457493 f31):** a fetch TRAINER
        whose every target is provably dead — its deck whiff-set exhausted (`_fetch_deadness_set` ⊆
        `Board.deck_empty_ids`, the SOUND predicate behind `dont-search-an-empty-deck`) or its
        recycle pool all-dead (`Board.recycle_dead_only`, behind `dont-recycle-the-dead`) — realises
        no role, so it sheds freely instead of propping up the SHED at its tutor/recovery worth.
        Trainer-only: a Pokémon carrying a `recycle` tag (Kyogre) is a playable body regardless.

        **Need-met gate (the fetcher gate's cousin — ladder-win case ep82753102 f16):** a
        `rush_evolve` / `tutor_mega` WINCON-tutor whose wincon is already in hand
        (`Board.wincon_in_hand`) has its role SATISFIED — nothing left worth fetching — so it too
        collapses to 0. Fires live everywhere `keep_cost` is consumed (gamble keep-floor, refresh
        SHED), mirroring the ladder's `discard-the-redundant-tutor` premise as a Worth factor."""
        from common import gate_library
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        if gate_library.is_evolution(st):
            return gate_library.deploy_odds(st, playable=playability.playable_from_hand(
                cid, stats=self.stats, zones=self._playability_zones(board, counts)))
        if st is not None and not st.is_pokemon and not st.is_energy:
            tags = self.functions.tags(cid) if self.functions else ()
            if ({"rush_evolve", "tutor_mega"} & set(tags)) and getattr(board, "wincon_in_hand", False):
                return gate_library.need_met_odds(need_met=True)   # wincon-tutor, wincon already in hand
            fetch_set = self._fetch_deadness_set(cid)
            empty = getattr(board, "deck_empty_ids", None) or frozenset()
            if fetch_set and all(t in empty for t in fetch_set):
                return gate_library.fetch_deploy_odds(targets_exhausted=True)
            if "recycle" in tags and getattr(board, "recycle_dead_only", False):
                return gate_library.fetch_deploy_odds(targets_exhausted=True)
        return 1.0

    def _slot_basic_in_zone(self, want, lock, zone: str, counts: dict, discard_basic_types: set) -> bool:
        """A Basic Energy that FILLS the missing slot ``want`` (``None`` = colourless: any Basic) AND
        passes the fetch's type ``lock`` is still available in ``zone`` — the deck (``counts``) or the
        visible discard (``discard_basic_types``). The shared availability predicate behind the
        Item closure (`_fetch_reaches_slot`) and the post-Item-refresh Supporter closure."""
        if lock is not None and want is not None and lock != want:
            return False                                      # a type-locked fetch can't supply this slot

        def _ok(et) -> bool:
            if et is None:
                return False
            if want is not None and et != want:               # a specific slot needs its exact type
                return False
            return lock is None or et == lock                 # a locked fetch only finds its lock type

        if zone == "deck":
            return any((st := self.stats.get(c)) is not None and st.is_basic_energy
                       and _ok(getattr(st, "energyType", None))
                       for c, n in counts.items() if n > 0)
        if zone == "discard":
            return any(_ok(et) for et in discard_basic_types)
        return False

    def _fetch_reaches_slot(self, want, cid: int, counts: dict, discard_basic_types: set) -> bool:
        """WP1: True iff card ``cid``'s **FETCH clauses** (``card_effects.json`` / ADR-0032 — the
        parametric tier a boolean Function Tag can't carry) can put a Basic Energy FILLING the missing
        slot ``want`` (``None`` = a colourless slot: any Basic) into hand, its target still reachable in
        the clause's source zone — a whole-deck search (``zone: deck``, a matching Basic still in
        ``counts``) or a recycle (``zone: discard``, a matching Basic type in the visible discard). The
        predicate lives in the card representation, NOT a card-text parse: Fighting Gong's ``{F}`` lock
        is its ``energy_type: 6`` clause, which the generic ``tutor_energy`` tag can't express. () for a
        card with no fetch clause. Errs by under-counting only (an endorser).

        A clause that is not an unconditional, decidable search (`fetch_closure.
        fetch_is_unconditional` — Bug Catching Set's top-7 dig, a board-gated or name-family clause)
        is skipped: this leg asserts the slot CAN be filled, so a probable find would be a fabricated
        endorsement. One shared predicate with the closure, never a re-spelled guard."""
        from common.fetch_closure import fetch_is_unconditional
        return any(cl.get("kind") == "fetch" and cl.get("target") == "basic_energy"
                   and fetch_is_unconditional(cl)
                   and self._slot_basic_in_zone(want, cl.get("energy_type"), cl.get("zone"),
                                                counts, discard_basic_types)
                   for cl in (self.effects.clauses(cid) if self.effects else ()))

    def _supporter_energy_tutor_reaches(self, tid, want, counts: dict, discard_basic_types: set) -> bool:
        """WP1 (Supporter branch): True iff Supporter ``tid`` can put a slot-filling Energy in hand or
        attach it, its target still reachable — LIVE only while the one-per-turn Supporter slot is
        unspent, which inside the refresh window means the refresh itself was an ITEM (Unfair Stamp;
        4/5 refreshes are Supporters and spend the slot — the caller gates on that). Three clause
        shapes (`card_effects.json`): an ``energy``/``basic_energy`` deck fetch (Hilda — Special
        Energy ignored, Basics-only matching, under-count); an UNconditional ``accel`` (Crispin
        attaches directly — bypasses nothing here, the manual attach is unspent anyway; a conditioned
        accel like Rosa's fails closed); the ``trainer`` fetch 2-hop (Petrel → an energy-fetch ITEM
        still in deck whose own target is reachable — spec-verified legal in one turn).

        Both fetch shapes are gated on `fetch_closure.fetch_is_unconditional`, the same predicate the
        closure's reach reading uses: a dig, a board gate or an undecidable name family is not the
        deterministic search this leg's claim rests on. The ``accel`` shape has always failed closed
        on a `condition` for the same reason, and now says so through the shared vocabulary."""
        from common.fetch_closure import fetch_is_unconditional
        st = self.stats.get(tid) if self.stats else None
        if st is None or not st.is_supporter:
            return False
        for cl in (self.effects.clauses(tid) if self.effects else ()):
            kind = cl.get("kind")
            if kind == "fetch" and not fetch_is_unconditional(cl):
                continue
            if (kind == "fetch" and cl.get("zone") == "deck"
                    and cl.get("target") in ("basic_energy", "energy")):
                if self._slot_basic_in_zone(want, cl.get("energy_type"), "deck",
                                            counts, discard_basic_types):
                    return True
            elif kind == "accel" and cl.get("energy") == "basic" and not cl.get("condition"):
                if self._slot_basic_in_zone(want, None, cl.get("source"),
                                            counts, discard_basic_types):
                    return True
            elif kind == "fetch" and cl.get("zone") == "deck" and cl.get("target") == "trainer":
                if any(n > 0 and (ist := self.stats.get(t)) is not None and ist.is_item
                       and self._fetch_reaches_slot(want, t, counts, discard_basic_types)
                       for t, n in counts.items()):
                    return True
        return False

    def _gamble_chain_refreshes(self, counts: dict, sup_live: bool, board) -> tuple:
        """The refresh CHAIN (hypergeometric-fetch-closure §failure mode B, the drawn-expander leg —
        built 2026-07-19): USABLE shuffle-refresh copies still in my DECK whose draw opens a fresh
        full window inside this refresh's window — ``(copies, min_window)``. A drawn Unfair Stamp
        (Item) is usable iff one of MY Pokémon was KO'd during the opponent's last turn
        (`Board.my_pokemon_koed_last_turn` — the card's own play condition); a drawn SUPPORTER
        refresh (Judge / Lillie's / Harlequin) is usable iff the one-per-turn Supporter slot is
        UNSPENT in this window, i.e. the played refresh was an Item (``sup_live`` — the 4-of-5
        rule). Window = each card's own printed draw (`own_draw_count`), MIN across usable types
        (the engine convention — conservative when types mix). ``(0, 0)`` when none usable. Errs by
        under-counting: chains inside the chain, and the measured slot-dead cases (a Pokégear-class
        dig fetching a slot-dead Supporter), are never counted."""
        from common.strategy.refresh import own_draw_count
        copies, window = 0, None
        for tid, n in counts.items():
            if n <= 0 or not self.functions or "shuffle_hand" not in self.functions.tags(tid):
                continue
            st = self.stats.get(tid) if self.stats else None
            if st is None:
                continue
            if getattr(st, "is_item", False):
                if not getattr(board, "my_pokemon_koed_last_turn", False):
                    continue
            elif getattr(st, "is_supporter", False):
                if not sup_live:
                    continue
            else:
                continue
            w = own_draw_count(tid, board.my_prizes_remaining, board.opp_prizes_remaining)
            if not w or w <= 0:
                continue
            copies += n
            window = int(w) if window is None else min(window, int(w))
        return (copies, window or 0)

    def _gamble_draw_engines(self, me: dict, counts: dict, exclude: set) -> tuple:
        """WP4: the refresh window's usable DRAW ENGINES — ``(engine_copies, stage_windows,
        engine_ids)`` for `deck_odds.draw_hit_with_engines`. A drawn engine copy is usable iff its
        ability is unconditional-once-in-play (`draw` clause, ``condition: once_per_turn_ability`` —
        Drakloak's Recon, Dudunsparce's Run Away Draw; Fezandipiti's post-KO gate and Lunatone's
        Solrock+hand-discard gate fail CLOSED — the refresh empties the hand, the gate can't be
        promised) AND an eligible base for it is already on board (rules.md §4: a body in play since
        last turn, ``appearThisTurn`` False — evolving the drawn engine onto it is legal this turn;
        turn ≥ 2 is gated upstream). Depth = board-supported capacity, Σ per line of min(copies in
        pool, eligible bases) — never a hardcoded stage count (spec §recursion point 2). The stage
        window = the MINIMUM usable window (Recon sees 2, take-1 greedy; Run Away Draw sees 3) —
        conservative when lines mix. ``exclude`` drops ids the class already counts as outs (a
        Drakloak that IS the sought evolution never double-counts). Errs by under-counting only."""
        bases: dict = {}                                      # base name -> eligible bodies on board
        for b in ((me.get("active") or []) + (me.get("bench") or [])):
            if not b or b.get("appearThisTurn"):
                continue
            st = self.stats.get(b.get("id")) if self.stats else None
            nm = getattr(st, "name", None)
            if nm:
                bases[nm] = bases.get(nm, 0) + 1
        ids, copies_total, activations, min_window = [], 0, 0, None
        for eid, n in counts.items():
            if n <= 0 or eid in exclude:
                continue
            st = self.stats.get(eid) if self.stats else None
            base = getattr(st, "evolvesFrom", None) if st else None
            if not base or not bases.get(base):
                continue
            for cl in (self.effects.clauses(eid) if self.effects else ()):
                if cl.get("kind") == "draw" and cl.get("condition") == "once_per_turn_ability":
                    window = int(cl.get("window") or cl.get("amount") or 0)
                    if window <= 0:
                        break
                    ids.append(eid)
                    copies_total += n
                    activations += min(n, bases[base])
                    min_window = window if min_window is None else min(min_window, window)
                    break
        if not ids or not activations:
            return 0, (), []
        return copies_total, (min_window,) * activations, sorted(ids)

    def _supporter_evolution_tutor_reaches(self, tid, eid, counts: dict) -> bool:
        """WP5 (Supporter branch): True iff Supporter ``tid`` can deliver the evolution ``eid`` —
        a deck fetch reaching it (Hilda's `evolution` clause; Salvatore's rush-evolve puts it
        straight ONTO the body) or the Petrel 2-hop (→ an Item Pokémon-tutor still in deck that
        reaches it). Live only post-Item-refresh (the caller gates on the Supporter slot).

        The 2-hop's FIRST leg is gated on `fetch_closure.fetch_is_unconditional` like every other
        reach-side reader; the second is `_fetch_reaches_pokemon`, which asks the closure and so
        carries the same gate already."""
        from common.fetch_closure import fetch_is_unconditional
        st = self.stats.get(tid) if self.stats else None
        if st is None or not st.is_supporter:
            return False
        if self._fetch_reaches_pokemon(eid, tid, counts):
            return True
        return any(cl.get("kind") == "fetch" and cl.get("zone") == "deck"
                   and cl.get("target") == "trainer" and fetch_is_unconditional(cl)
                   and any(n > 0 and (ist := self.stats.get(t)) is not None and ist.is_item
                           and self._fetch_reaches_pokemon(eid, t, counts)
                           for t, n in counts.items())
                   for cl in (self.effects.clauses(tid) if self.effects else ()))

    def _fetch_reaches_pokemon(self, target_id: int, cid: int, counts: dict) -> bool:
        """WP5/WP7: True iff card ``cid``'s ``zone: deck`` FETCH clauses can pull the Pokémon
        ``target_id`` (still in ``counts``) — Poké Pad's ``no_rule_box`` never fetches a Rule-Box Mega
        ex. Delegates to the shared `common.fetch_closure` graph (ADR-0065)."""
        from common import fetch_closure
        return fetch_closure.fetch_reaches_pokemon(
            target_id, cid, counts, self._closure_stat_of, self._closure_clauses_of)

    def _gamble_ko_classes(self, board, stat, ma, opp, hp: int, counts: dict, hand: list,
                           discard_basic_types: set):
        """The KO-enabling **Outcome Classes** of a refresh draw: for each of my Active's attacks
        exactly ONE Energy short whose damage fells the opponent's Active, the class of draws whose
        entry points ASSEMBLE a Basic Energy filling the missing slot (its specific type, or any Basic
        for a colourless slot). Entry points = the literal Basic Energy copies PLUS the **fetch-closure
        outs** (WP1): a drawable card with a `basic_energy` FETCH clause (`card_effects.json`, read by
        `_fetch_reaches_slot`) whose target is still reachable — a whole-deck search (Energy Search /
        Fighting Gong {F}-locked / Energy Search Pro) with a matching Basic still in deck, or a recycle
        (Night Stretcher / Energy Retrieval / Max Rod) with a matching Basic in the visible discard.
        Returns ``[(copies, ko_value, label, sought_ids, (sup_copies, sup_ids)), …]`` — ``sought_ids``
        = the deck card ids that ARE the always-live outs (literal ∪ Item closure); the 5th slot is the
        **post-Item-refresh Supporter supplement** (Hilda / Crispin / the Petrel 2-hop,
        `_supporter_energy_tutor_reaches`), counted by the pricing loop ONLY when the refresh being
        priced is an ITEM (Unfair Stamp) and the Supporter slot is unspent — after a Supporter refresh
        the slot is spent and a drawn Supporter tutor is dead (spec §Missing, the 4-of-5 rule). An
        enabler already in HAND — a held Basic, a held fetch Item that reaches the slot, or (slot
        unspent) a held Supporter tutor that reaches it — voids the class (no gamble needed; playing it
        is the deterministic line). Errs by UNDER-counting the outs only (an endorser)."""
        out = []
        attached = self._attached_type_counts(ma)
        hand_ids = [c.get("id") for c in hand]
        for aid in (stat.attacks or ()):
            cost = self._attack_cost(aid)
            if cost != board.my_active_energy + 1:            # exactly one attach short
                continue
            if self.predicted_damage(board.my_active_id, aid, opp) < hp:
                continue
            ast = self._attack_stat(aid)
            types = getattr(ast, "energyTypes", ()) if ast else ()
            from collections import Counter
            need = Counter(t for t in types if t not in (0, None))
            deficit = {t: n - attached.get(t, 0) for t, n in need.items() if n - attached.get(t, 0) > 0}
            if sum(deficit.values()) > 1:
                continue                                      # more than one specific slot short
            want = next(iter(deficit), None)                  # None -> the short slot is colourless

            def _enables(cid) -> bool:
                est = self.stats.get(cid) if self.stats else None
                if not est or est.is_pokemon:
                    return False
                if not est.is_basic_energy:
                    return False                              # Basics only (a special Energy pays
                et = getattr(est, "energyType", None)         # colourless slots — under-counted, safe)
                return (et == want) if want is not None else True
            if any(_enables(cid) for cid in hand_ids):
                continue                                      # hand already holds the Basic enabler
            if any(self._fetch_reaches_slot(want, cid, counts, discard_basic_types)
                   for cid in hand_ids):                      # …or a held fetch card that reaches it:
                continue                                      # deterministic tutor line — no gamble needed
            if not board.supporter_played and any(
                    self._supporter_energy_tutor_reaches(cid, want, counts, discard_basic_types)
                    for cid in hand_ids):                     # a held Supporter tutor + a live slot is
                continue                                      # the deterministic line too (play it now)
            out_ids = {cid for cid, n in counts.items() if n > 0 and _enables(cid)}   # literal Basics
            for tid, n in counts.items():                     # WP1 closure entry points (fetch clauses)
                if n > 0 and tid not in out_ids and self._fetch_reaches_slot(
                        want, tid, counts, discard_basic_types):
                    out_ids.add(tid)
            sup_ids = sorted(tid for tid, n in counts.items() if n > 0 and tid not in out_ids
                             and self._supporter_energy_tutor_reaches(tid, want, counts,
                                                                      discard_basic_types))
            sought = sorted(out_ids)
            copies = sum(counts[cid] for cid in sought)
            if copies <= 0:
                continue
            label = f"a type-{want} Basic Energy" if want is not None else "any Basic Energy"
            out.append((copies, KO_SCORE + self._prize_value(opp), label, sought,
                        (sum(counts[t] for t in sup_ids), sup_ids)))
        return out

    def _gamble_evolution_ko_classes(self, obs, board, ma, opp, counts: dict, hand: list):
        """WP5: the **evolution-KO** Outcome Class — the highest-value un-built gamble class. Where
        ``_gamble_ko_classes`` prices only the CURRENT Active's attacks, this prices "draw an evolution
        of my (evolution-eligible) Active → evolve it → ITS attack KOs": evolving is legal the same
        turn (Active in play since last turn — `appearThisTurn` False, rules.md §4 L96; turn ≥ 2 is
        already gated upstream), keeps the attached Energy (rules.md §4 L98), and a Mega ex does NOT
        end the turn on evolving (rules.md §4 L103), so the evolved form attacks with the carried Energy
        plus this turn's one attach. Outs = the evolution's deck copies PLUS the Item Pokémon-tutor
        closure that fetches it (Ultra Ball / Poké Pad / Mega Signal). The 5th slot carries the
        **post-Item-refresh Supporter supplement** (Hilda's evolution fetch, Salvatore's rush-evolve,
        the Petrel 2-hop — `_supporter_evolution_tutor_reaches`), counted only when the refresh being
        priced is an ITEM (Unfair Stamp) and the Supporter slot is unspent; after a Supporter refresh
        those tutors are slot-dead. An evolution already in HAND voids the class (the deterministic
        evolve-KO owns it, and puts a KO on the menu → the rung stands down upstream); so does a held
        Supporter evolution-tutor while the slot is unspent. Same 5-tuples; errs by under-counting."""
        if ma.get("appearThisTurn"):                          # placed this turn -> can't evolve (§4 L96)
            return []
        base = self.stats.get(ma.get("id")) if (self.stats and ma.get("id") is not None) else None
        if base is None or not getattr(base, "name", None):
            return []
        energy = board.my_active_energy + 1                   # carried Energy + this turn's one attach
        hand_ids = {c.get("id") for c in hand}
        out = []
        for eid in set(self.deck):                            # DIRECT evolutions of the Active in my deck
            st = self.stats.get(eid) if self.stats else None
            if st is None or getattr(st, "evolvesFrom", None) != base.name:
                continue
            if counts.get(eid, 0) <= 0 or eid in hand_ids:    # none left to draw / in hand (deterministic)
                continue
            if self._best_affordable_ko_value(obs, board, opp, eid, energy, body=ma) <= 0:
                continue                                      # the evolved form doesn't reach a KO
            if not board.supporter_played and any(
                    self._supporter_evolution_tutor_reaches(cid, eid, counts) for cid in hand_ids):
                continue                                      # held Supporter tutor + live slot: det line
            out_ids = {eid}
            for tid, n in counts.items():                     # Item Pokémon-tutor closure (fetch clauses)
                if tid == eid or n <= 0 or tid in hand_ids:
                    continue
                tst = self.stats.get(tid) if self.stats else None
                if tst is None or not getattr(tst, "is_item", False):
                    continue                                  # Supporter tutors join only post-Item-refresh
                if self._fetch_reaches_pokemon(eid, tid, counts):   # honours no-Rule-Box / mega predicate
                    out_ids.add(tid)
            sup_ids = sorted(tid for tid, n in counts.items()
                             if n > 0 and tid != eid and tid not in out_ids and tid not in hand_ids
                             and self._supporter_evolution_tutor_reaches(tid, eid, counts))
            sought = sorted(out_ids)
            copies = sum(counts.get(cid, 0) for cid in sought)
            if copies <= 0:
                continue
            out.append((copies, KO_SCORE + self._prize_value(opp),
                        f"the evolution {st.name}", sought,
                        (sum(counts[t] for t in sup_ids), sup_ids)))
        return out

    def _gamble_pump_ko_classes(self, obs, board, stat, ma, opp, hp: int, counts: dict, hand: list):
        """WP5: the **damage-pump** KO class — my Active's best AFFORDABLE attack (current Energy; the
        boost is the missing piece, not Energy) is short of the KO by ≤ one boost, and drawing a
        ``damageBoost`` Trainer (Premium Power Pro {F}+30 Item; Black Belt's +40-vs-ex Supporter) lifts
        it over. Gates mirror `_boost_lethal_tactical` EXACTLY — the attacker-type gate (``energyType``
        vs ``damageBoostType``, "your {F} Pokémon") and the defender ``{ex}`` gate — so the class never
        over-credits a type-locked pump (provider.py:97-100, VERIFIED parsed). Item boosts are
        always-live outs; Supporter boosts ride the post-Item-refresh supplement (5th slot). A held
        boost that crosses voids the class (the deterministic play-it line). Single-copy only (short by
        ≤ one boost — multi-copy stacking is a deeper hypergeometric, deferred); errs by under-counting."""
        if board.turn <= 1:
            return []
        opp_stat = self.stats.get(opp.get("id")) if (self.stats and opp.get("id") is not None) else None
        ctx = self._damage_context(obs)
        hand_ids = {c.get("id") for c in hand}
        best_dmg = 0
        for aid in (stat.attacks or ()):
            if self._attack_cost(aid) > board.my_active_energy:
                continue                                      # not affordable with current Energy
            dmg = self.predicted_damage(board.my_active_id, aid, opp, context=ctx)
            if dmg >= hp:
                return []                                     # an affordable KO already exists — attack
            best_dmg = max(best_dmg, dmg)
        if best_dmg <= 0:
            return []

        def _crosses(bst) -> bool:
            if bst is None or not getattr(bst, "damageBoost", 0):
                return False
            if bst.damageBoostType is not None and getattr(stat, "energyType", None) != bst.damageBoostType:
                return False                                  # attacker-type gate
            if bst.damageBoostVsEx and not (opp_stat and opp_stat.is_ex_body):
                return False                                  # defender {ex} gate
            if not bst.applies_to_holder(stat):
                return False                                  # the HOLDER gate(s): an owner family
                                                              # ("the Hop's Pokémon this card is
                                                              # attached to", Issue #306) or a
                                                              # no-Rule-Box condition (Brave Bangle,
                                                              # Issue #345). Asked as one test, so a
                                                              # gate added later reaches this site
                                                              # without it being edited — which is
                                                              # exactly what happened at Issue #345.
            return best_dmg < hp <= best_dmg + bst.damageBoost   # short by ≤ this one boost
        if any(_crosses(self.stats.get(cid) if self.stats else None) for cid in hand_ids):
            return []                                         # held boost crosses -> deterministic line
        item_ids = sorted(bid for bid, n in counts.items() if n > 0
                          and getattr(self.stats.get(bid), "is_item", False)
                          and _crosses(self.stats.get(bid)))
        sup_ids = sorted(bid for bid, n in counts.items() if n > 0
                         and getattr(self.stats.get(bid), "is_supporter", False)
                         and _crosses(self.stats.get(bid)))
        if not item_ids and not sup_ids:
            return []
        return [(sum(counts[b] for b in item_ids), KO_SCORE + self._prize_value(opp),
                 "a damage boost for the KO", item_ids,
                 (sum(counts[b] for b in sup_ids), sup_ids))]

    def _gamble_gust_ko_classes(self, obs, board, ma, opp_player, hand: list, counts: dict):
        """WP5: the **gust** KO class — my Active can't KO the current opp Active (else the rung stands
        down upstream), but its affordable attack CAN KO a benched target once that target is dragged
        up (per-target weakness via the shared `_gust_best_ko_prizes` / `_can_ko` oracle). Drawing a
        gust Trainer (Boss's Orders 1182 — a Supporter, so it rides the post-Item-refresh supplement;
        an Item gust would be always-live) enables it. Value = KO_SCORE + the BENCHED target's prize
        (not the current Active's). A held gust that reaches voids the class (the deterministic
        `gust-for-the-ko` line, already a KO on the menu). Errs by under-counting (cheapest-attack KO)."""
        best_prizes = self._gust_best_ko_prizes(ma, opp_player, board.my_active_energy)
        if best_prizes <= 0:
            return []
        hand_ids = {c.get("id") for c in hand}

        def _is_gust_trainer(cid) -> bool:
            st = self.stats.get(cid) if self.stats else None
            return bool(st and (st.is_item or st.is_supporter) and self.functions
                        and "gust" in self.functions.tags(cid))
        if any(_is_gust_trainer(cid) for cid in hand_ids):
            return []                                         # held gust -> deterministic gust-KO line
        item_ids = sorted(bid for bid, n in counts.items() if n > 0 and _is_gust_trainer(bid)
                          and getattr(self.stats.get(bid), "is_item", False))
        sup_ids = sorted(bid for bid, n in counts.items() if n > 0 and _is_gust_trainer(bid)
                         and getattr(self.stats.get(bid), "is_supporter", False))
        if not item_ids and not sup_ids:
            return []
        return [(sum(counts[b] for b in item_ids), KO_SCORE + best_prizes,
                 "a gust for the benched KO", item_ids,
                 (sum(counts[b] for b in sup_ids), sup_ids))]

    def _heal_restriction_ok(self, restriction, astat) -> bool:
        """WP5 survival: can a heal clause with this ``restriction`` target my (doomed) Active
        ``astat``? None / ``active_only`` always can; ``mega_only`` needs a Mega ex; ``psychic_only``
        a {P} body. An unknown restriction fails CLOSED (under-count — the endorser never assumes a
        heal it can't verify reaches my Active).

        The Active-spot reading of :meth:`_heal_restriction_targets`, and byte-identical to it over
        the whole shipped vocabulary — ``active_only`` is exactly the term this method could not
        express, and it is trivially satisfied when the body IS the Active."""
        return self._heal_restriction_targets(restriction, astat, is_active=True)

    def _heal_restriction_targets(self, restriction, stat, *, is_active: bool) -> bool:
        """:meth:`_heal_restriction_ok` asked of ANY of my bodies (Issue #409): can a heal clause
        with this ``restriction`` target the body described by ``stat``, sitting in the Active spot
        or on the Bench?

        ``active_only`` is the whole reason this method exists. It is the one restriction whose
        answer DEPENDS on where the body stands, and the Active-only form had to hardcode it True —
        which is correct for its own caller and would silently offer a benched Cook / Lumiose Galette
        / Jumbo Ice Cream target if reused unchanged. Everything else is a card-fact test that reads
        the same from either area: ``mega_only`` a Mega ex (Wally's Compassion), ``psychic_only`` a
        {P} body (Jacinthe; ``EnergyType.PSYCHIC`` = 5, `cg/api.py`).

        An unknown restriction fails CLOSED, unchanged — the ``active_dragon_only`` (1105 Dragon
        Elixir) and ``arvens_pokemon`` (1130 Arven's Sandwich) strings both land here, and
        `snapshot_coverage.UNCONSUMED_SELECTORS` records the first of them as a known, deliberate
        under-count. Fail-closed is Issue #409 R3's rule at the target select too: a body the term
        cannot price contributes 0.0 rather than a guess."""
        if restriction is None:
            return True
        if restriction == "active_only":
            return is_active
        if restriction == "mega_only":
            return bool(getattr(stat, "megaEx", False))
        if restriction == "psychic_only":
            return getattr(stat, "energyType", None) == 5
        return False

    def _heal_averts_doom(self, cid, astat, cur_hp: int, incoming: int) -> bool:
        """WP5 survival: True iff card ``cid`` has a HEAL clause (`card_effects.json`) that lifts my
        doomed Active from ``cur_hp`` ABOVE the ``incoming`` (so next turn's biggest attack no longer
        KOs it) — ``amount: all`` heals to max HP. Only heals whose restriction can target my Active
        count (`_heal_restriction_ok`); a conditional heal (a `condition` gate) fails closed.

        Issue #349's `each_of` / `amount_per` are deliberately not read, for the reason
        `_heal_candidate`'s docstring gives at length: this asks only what MY ACTIVE ends up on, and a
        per-body distribution gives it the same `amount` a single-target heal would. Reading `each_of`
        as a multiplier would promise a survival the board never delivers; ignoring `amount_per`
        under-counts, which is the direction this method already says it errs in.

        The Active-spot reading of :meth:`_heal_body_averts_doom`."""
        return self._heal_body_averts_doom(cid, astat, is_active=True, cur_hp=cur_hp,
                                           incoming=incoming)

    def _heal_body_averts_doom(self, cid, stat, *, is_active: bool, cur_hp: int,
                               incoming: int, max_hp: int | None = None) -> bool:
        """:meth:`_heal_averts_doom` asked of ANY of my bodies (Issue #409): does a heal clause of
        ``cid`` lift the body described by ``stat`` from ``cur_hp`` ABOVE the ``incoming`` that can
        actually reach it, so the next swing no longer knocks it out?

        This is Issue #409 R2's ``survival_gain`` predicate, and the ``incoming`` a caller hands it
        is what makes it area-correct: for the Active that is the opponent's biggest attack; for a
        BENCHED body it is the snipe/spread reach ONLY (printed damage lands on the Active —
        `CombatMath.form_damage_vs`, ADR-0070 §9), which is usually zero, and a body nobody can hit
        gains nothing from being healed. That asymmetry is derived from a shipped read rather than
        authored, which is why it needs no constant of its own.

        A gated heal (any ``condition``) still can't be promised, unchanged from the Active form —
        this predicate feeds survival claims, and the fail direction it errs in is under-counting.
        Note that is STRICTER than :meth:`_heal_body_candidate`, which evaluates the two
        board-checkable gates; the difference is each caller's own policy and is deliberate.

        ``max_hp`` is the restore ceiling, defaulting to the printed HP — see
        :meth:`_heal_body_candidate` for why a +HP Tool makes that a parameter rather than a read."""
        max_hp = int(max_hp) if max_hp else (getattr(stat, "hp", 0) or 0)
        for cl in (self.effects.clauses(cid) if self.effects else ()):
            if cl.get("kind") != "heal" or cl.get("condition"):
                continue                                      # a gated heal can't be promised
            if not self._heal_restriction_targets(cl.get("restriction"), stat,
                                                  is_active=is_active):
                continue
            amount = cl.get("amount")
            healed = max_hp if amount == "all" else min(max_hp, cur_hp + int(amount or 0))
            if healed > incoming:
                return True
        return False

    def _gamble_survival_classes(self, obs, board, me, counts: dict, hand: list):
        """WP5 (survival): the bench-empty PREDICTED-LOSS class — my Active is doomed (opp KOs it next
        turn, ADR-0064 `active_doomed`) AND my Bench is EMPTY, so a KO of my only Pokémon LOSES the
        game (no Pokémon in play → you lose). Two out families avert it: **bench-fill** — any benchable
        Basic, or Poffin's bench-fill fetch of a ≤70-HP Basic still in deck (a KO is no longer
        game-over); and **heal** — a drawn heal that lifts the Active above the incoming
        (`_heal_averts_doom`, e.g. Wally's on a damaged Mega ex). Value = KO_SCORE (a game loss averted
        is ±KO_SCORE-scale by the loss rung; spec §Round 5), EXEMPT from the keep-value blocker. Item
        outs are always-live; Supporter heals ride the post-Item supplement. A held Basic (bench it) or
        a held heal that averts (play it) voids the class — the deterministic line. Errs by
        under-counting."""
        if not board.active_doomed or any(b for b in (me.get("bench") or [])):
            return []                                         # not doomed, or a bench body already exists

        def _benchable(cid) -> bool:
            st = self.stats.get(cid) if self.stats else None
            return bool(st and st.is_pokemon and not getattr(st, "evolvesFrom", None))
        hand_ids = {c.get("id") for c in hand}
        if any(_benchable(cid) for cid in hand_ids):
            return []                                         # a Basic in hand -> bench it, no gamble
        # bench-fill outs (always-live): benchable Basics + Poffin's fetch of one.
        out_ids = {cid for cid, n in counts.items() if n > 0 and _benchable(cid)}
        for tid, n in counts.items():                         # Poffin: a bench-fill fetch reaching a Basic
            if n > 0 and tid not in out_ids and any(
                    _benchable(bid) and self._fetch_reaches_pokemon(bid, tid, counts) for bid in counts):
                out_ids.add(tid)
        # heal outs: lift the doomed Active above the incoming (Item -> always-live; Supporter -> supp).
        sup_ids: set = set()
        astat = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        ma = next((p for p in (me.get("active") or []) if p), None)
        cur_hp = (ma or {}).get("hp", 0)
        incoming = board.incoming_active_damage
        if incoming and astat and ma and cur_hp < getattr(astat, "hp", 0):   # damage to heal + a threat
            if any(self._heal_averts_doom(cid, astat, cur_hp, incoming) for cid in hand_ids):
                return []                                     # a held heal averts -> deterministic line
            for hid, n in counts.items():
                if n <= 0 or hid in out_ids or not self._heal_averts_doom(hid, astat, cur_hp, incoming):
                    continue
                hst = self.stats.get(hid) if self.stats else None
                (out_ids if getattr(hst, "is_item", False) else sup_ids).add(hid)
        sought = sorted(out_ids)
        sup = sorted(sup_ids)
        copies = sum(counts[cid] for cid in sought)
        sup_copies = sum(counts[s] for s in sup)
        if copies <= 0 and sup_copies <= 0:
            return []
        return [(copies, KO_SCORE, "a Basic or heal to avoid the loss", sought, (sup_copies, sup))]

    def _gamble_det_baseline(self, board, stat, ma, opp, hp: int, traces, hand: list) -> float:
        """The DETERMINISTIC baseline a gamble must beat: the best tactical already on the menu, or
        the best after-attach chip the HELD Energy reaches (attach the best hand Energy → biggest
        affordable non-KO damage) — the value the banked line (attach first, refresh after) keeps."""
        det = max((t.tactical for t in traces), default=0.0)
        hand_ids = frozenset(c.get("id") for c in hand)
        units = self._best_hand_attach_units(hand_ids, stat)
        energy_after = board.my_active_energy + units
        # extra_type=0: the held attach is priced as colourless — funds {C} slots only, the
        # conservative read (a held TYPED enabler voids the gamble class upstream anyway). The scan
        # is `combat.best_affordable_damage` (Issue #409), extracted so the affordability rule —
        # count gate AND colour gate, which must stay in lockstep — has one home.
        return max(det, self._best_affordable_damage(board.my_active_id, energy_after, opp,
                                                     body=ma, extra_type=0, extra_units=units))

    def _retreat_snipe_candidate(self, me, others, target_hp: int, extra: int):
        """``active_survives`` (bool) for the best benched body that, once retreated INTO (its Energy
        plus this turn's one attach), affords an attack whose bench-snipe rider KOs the ``target_hp``
        key threat — or None when no benched body reaches one. Among the capable bodies it prefers
        the one that SURVIVES the opponent's remaining Incoming (the sniped threat excluded)."""
        best = None
        for p in (me.get("bench") or []):
            if not p:
                continue
            if not self._affords_snipe_ko(p.get("id"), len(p.get("energies") or []) + extra, target_hp):
                continue
            my_hp = p.get("hp", 0)
            survives = bool(my_hp) and self._incoming_worst(p.get("id"), my_hp, others) < my_hp
            if best is None or survives > best:
                best = survives
        return best

    def _affords_snipe_ko(self, body_id, energy: int, target_hp: int) -> bool:
        """True iff ``body_id`` carrying ``energy`` can pay an attack whose unconditional bench-snipe
        rider (`combat.rider_snipe`) reaches ``target_hp`` — the exact snipe-KO test (no W/R on the Bench)."""
        stat = self.stats.get(body_id) if (self.stats and body_id is not None) else None
        if not (stat and target_hp):
            return False
        return any(self._attack_cost(aid) <= energy and self.combat.rider_snipe(aid) >= target_hp
                   for aid in (stat.attacks or ()))

    def _is_energy_tutor(self, obs, select, option) -> bool:
        """This PLAY option is a `tutor_energy` Trainer (Hilda class) — it searches an attachable
        Energy into hand, supplying the attach an enabling line lacks (the 4298 shape)."""
        cid = self._option_card_id(obs, select, option)
        return bool(cid is not None and self.functions and "tutor_energy" in self.functions.tags(cid))

    def _is_evolution_tutor(self, obs, select, option) -> bool:
        """This PLAY option is a `rush_evolve` Trainer (Salvatore class) — it evolves one of my
        in-play Pokémon straight from the deck, its own allowance covering setup-placed and
        this-turn bodies (so every in-play body is a legal target)."""
        cid = self._option_card_id(obs, select, option)
        return bool(cid is not None and self.functions and "rush_evolve" in self.functions.tags(cid))

    def _whiff_odds(self, board, body) -> float:
        """BUILD 1 helper: P(the opponent still holds ≥1 copy of ``body``'s line) via the Opponent Model
        (`copies_left_odds`). Lower = the opponent is LESS able to replace this body if I KO it — the
        whiff-maximising target. Fails OPEN to 1.0 ("assume replaceable") when no Opponent Model / no
        confident Read, so the tiebreak silently no-ops without a confident recognition."""
        opp_model = getattr(board, "opponent", None)
        if opp_model is None:
            return 1.0
        try:
            return float(opp_model.copies_left_odds((body or {}).get("id")))
        except Exception:
            return 1.0

    def _is_item_pokemon_tutor(self, obs, select, option) -> bool:
        """BUILD 3 helper: this PLAY option is an ITEM that fetches an evolution-form Pokémon into HAND
        (Mega Signal: `tutor_mega`; the generic `tutor_pokemon`) — the composer's committed first step.
        Distinct from `rush_evolve` (evolves straight from the deck — a Supporter) and `tutor_energy`.
        False when the card / its stat / its tags are unknown (fail-closed)."""
        cid = self._option_card_id(obs, select, option)
        if cid is None or not self.functions or not self.stats:
            return False
        stat = self.stats.get(cid)
        if stat is None or not getattr(stat, "is_item", False):
            return False
        tags = self.functions.tags(cid)
        return "tutor_mega" in tags or "tutor_pokemon" in tags

    def _item_enabler_cost(self, board) -> float:
        """BUILD 4 (`enabler_item_composer`): the cost credit for an Item enabler (a pokemon-tutor Item or
        Rare Candy). The Item's only advantage over the Supporter-tutor path (credit 0) is that it does NOT
        spend the scarce one-per-turn Supporter slot. That preservation is worth the WIDER gap
        (``_PLANNER_ENABLER_ITEM_SLOT``) only when a Supporter in hand actually WANTS the slot this turn —
        canonically a `gust` Supporter (Boss's Orders, which could itself drag+KO) or any other high-value
        Supporter (``no_supporter_in_hand`` False ⇒ some Supporter competes). With no Supporter competing,
        keeping the slot is nearly free, so the gap SHRINKS to ``_PLANNER_ENABLER_ITEM_BASE``. Both credits
        stay sub-prize/sub-survival: a same-KO enabler tiebreak, never a reorder over a real prize."""
        competes = self._gust_supporter_in_hand(board) or not board.no_supporter_in_hand
        return _PLANNER_ENABLER_ITEM_SLOT if competes else _PLANNER_ENABLER_ITEM_BASE

    def _gust_supporter_in_hand(self, board) -> bool:
        """BUILD 4 helper: MY hand holds a `gust` Supporter (Boss's Orders class) — the sharpest claimant on
        this turn's one Supporter slot (it can itself drag a benched body up and KO). False without
        stats/functions (fail-closed) — an unrecognized hand never asserts the competing Supporter."""
        if not (self.stats and self.functions):
            return False
        for cid in board.hand_ids:
            st = self.stats.get(cid)
            if st is not None and st.is_supporter and "gust" in self.functions.tags(cid):
                return True
        return False

    def _composed_budget(self, card_id, *, benched: bool, supporter_spent: bool = False):
        """The Attach Budget toward one KO line's attacker, or None without a model.

        The units answer "does this line REACH a KO"; the Budget itself answers "how likely is the
        Energy really there" (ADR-0074 decision 3) — the same oracle read twice, so reach and
        probability can never be computed off different budgets. It is also what ANSWERS the reach
        question (ADR-0075 decision 1), which is the third reading of that same one Budget.

        ``supporter_spent`` closes the Supporter leg for a line that plays a Supporter as its own
        enabling step (ADR-0075 decision 3) — the successor to the retired
        ``enabler_consumes_supporter`` split."""
        model = self._state_model
        if model is None or card_id is None:
            return None
        return model.mine.attach_budget_for_card(card_id, benched=benched,
                                                 supporter_spent=supporter_spent)

    def _composed_attack_p(self, card_id, body, *, benched: bool, supporter_spent: bool = False):
        """``attack_id -> P(the composed line's Energy is really there)`` for this candidate form,
        or None when nothing can be priced (no model / no Budget) — the caller then makes no claim
        and the line keeps its unweighted value, exactly as before #175.

        This is the RANKED-consumer half of ADR-0074's Leg Assignment: the `ko_for_prizes` ladder
        emits a compared scalar, so it weights; the Win Rung gates, so it never calls this."""
        budget = self._composed_budget(card_id, benched=benched, supporter_spent=supporter_spent)
        model = self._state_model
        if budget is None or model is None:
            return None
        p_by_type = model.mine.deck_energy_p
        if not p_by_type:
            return None
        return lambda aid: self.combat.attack_realising_p(
            aid, budget=budget, body=body, p_by_type=p_by_type)

    def _ko_line_pricing(self, card_id, body, *, benched: bool, supporter_spent: bool = False):
        """``(budget, attack_p)`` for ONE KO line's attacker — the single pricing seam EVERY
        ``ko_for_prizes`` builder reads (ADR-0075 decision 4).

        ``card_id`` names the card whose ATTACKS are read (an evolved form still in hand or deck for
        a composed line; the body itself for a retreat line); ``body`` is the on-board dict carrying
        the ATTACHED Energy, which for an evolve line is the PRE-evolution body the Energy carries
        through. ``benched`` places the target for a bench-restricted clause — and since no modelled
        accel clause requires an ACTIVE target, a retreat line takes True: "attach to the benched
        body, then retreat, then attack" is a real sequence and a strict superset.

        One Budget serves refusal and ranking both, so the two can never be computed off different
        budgets (ADR-0075 decision 7 — separate parameters, one source)."""
        budget = self._composed_budget(card_id, benched=benched, supporter_spent=supporter_spent)
        if budget is None:
            return None, None
        return budget, self._composed_attack_p(card_id, body, benched=benched,
                                               supporter_spent=supporter_spent)

    def _item_evolve_ko_candidate(self, obs, select, board, option, opp, opp_player,
                                  retreat_on_menu: bool):
        """BUILD 3 (`enabler_item_composer`, DEFAULT OFF): ``(prizes, active_survives)`` if an ITEM that
        fetches an evolution Pokémon into HAND composes an otherwise-missed KO of the opponent's Active.
        The COMPOSITE line: play the Item (committed step[0]) → fetch the DIRECT evolution of an in-play,
        THIS-TURN-evolvable body (``appearThisTurn`` False — rules.md §4: a body cannot evolve the turn it
        was played) → evolve it → the evolved form, carrying the body's Energy plus this turn's one attach,
        affords a MIN-BOUND KO. The fetched form must be PROVABLY still in my deck (the tracker's positive
        certainty, ``Board.deck_definitely_has``) and fetchable by THIS item (a `tutor_mega` item reaches
        only a Mega ex; `tutor_pokemon` reaches any). A benched body needs the retreat still on the menu to
        reach the Active.

        SOUND energy accounting: the line's attach capacity is the **Attach Budget** built for THIS
        candidate evolved form (``_ko_line_pricing``, #142/#177) — every playable accelerator at its
        clause-quantified yield, target restrictions resolved against the evolved card's stats, and no
        hardcoded manual(1) + accel(1) ceiling. Every KO goes through
        ``_best_affordable_ko_value(bound="min")`` — a coin-conditional attack floors to its min damage, so
        no phantom KO. Value reflects the downstream evolve+attach KO; the caller tiers step[0] via
        ``_item_enabler_cost`` (slot-conditional, BUILD 4).

        NARROW SCOPE — single Item → single DIRECT evolve → attack. TODO (generality deferred): multi-hop
        evolution chains ACROSS turns, the fetched form deployed onto a DIFFERENT body/energy config than
        the one modelled (#2), and chaining a second Pokémon-tutor. None when no composite reaches a KO."""
        if not self.stats:
            return None
        item_id = self._option_card_id(obs, select, option)
        tags = self.functions.tags(item_id) if (self.functions and item_id is not None) else ()
        mega_only = "tutor_mega" in tags and "tutor_pokemon" not in tags   # the item's fetch class
        me = self._my_player(obs)
        bodies = [(p, False) for p in (me.get("active") or []) if p]
        if retreat_on_menu:
            bodies += [(p, True) for p in (me.get("bench") or []) if p]
        best = None
        for body, benched in bodies:
            if body.get("appearThisTurn"):
                continue                                  # can't evolve a body played this turn (rules.md §4)
            base = self.stats.get(body.get("id"))
            if base is None or not getattr(base, "name", None):
                continue
            energy = len(body.get("energies") or [])
            for cid in set(self.deck):
                st = self.stats.get(cid)
                if st is None or getattr(st, "evolvesFrom", None) != base.name:
                    continue
                if mega_only and not getattr(st, "megaEx", False):
                    continue                              # this item cannot fetch a non-Mega evolution
                # ADR-0074 decision 6 (extended, #175): the Pokemon-presence leg is WEIGHTED, not
                # gated. `deck_definitely_has` needs the anchor, so gating on it made this RANKED
                # line inert pre-anchor — exactly the frames the weighting exists to serve. 0.0 is
                # provably-empty and still drops the line; the Win Rung keeps the sound gate.
                present_p = board.deck_contains_probability(cid)
                if present_p <= 0.0:
                    continue                              # provably gone — no line to rank
                # The Budget is PER TARGET BODY, so it is built for THIS candidate evolved form
                # (its stats gate every accel clause's target restriction), not once for the menu.
                budget, attack_p = self._ko_line_pricing(cid, body, benched=benched)
                if budget is None or self._best_affordable_ko_value(
                        obs, board, opp, cid, energy, bound="min", body=body,
                        attack_p=attack_p, budget=budget) <= 0:
                    continue
                my_hp = getattr(st, "hp", 0) or 0
                cand = (self._prize_value(opp),
                        bool(my_hp) and self._survives_after_ko(cid, my_hp, opp_player),
                        present_p * self._composed_line_p(obs, board, opp, cid,
                                                          energy, body, attack_p,
                                                          budget=budget))
                if best is None or _composed_rank(cand) > _composed_rank(best):
                    best = cand
        return best

    def _composed_line_p(self, obs, board, opp, card_id, energy: int, body, attack_p,
                         budget=None) -> float:
        """P(the composed line's KO really lands) — the weighted KO value over the unweighted one,
        i.e. the probability attached to whichever attack the weighted valuation actually picked
        (ADR-0074 decisions 3-4, #175).

        Reading it back off the two valuations, rather than recomputing a "best" attack here, is
        what keeps the weight tied to the line the ranker committed to. 1.0 with nothing to price
        (no model, an unresolvable cost), so an unweighted build is byte-identical."""
        if attack_p is None:
            return 1.0
        raw = self._best_affordable_ko_value(obs, board, opp, card_id, energy,
                                             bound="min", body=body, budget=budget)
        if raw <= 0:
            return 0.0
        weighted = self._best_affordable_ko_value(obs, board, opp, card_id, energy,
                                                  bound="min", body=body, attack_p=attack_p,
                                                  budget=budget)
        return max(0.0, min(1.0, weighted / raw))

    def _is_rare_candy(self, obs, select, option) -> bool:
        """BUILD 1 helper: this PLAY option is Rare Candy — a Basic→Stage-2 evolve SKIP that needs the
        Stage-2 already in hand (NOT a tutor). Verified card text at data/EN_Card_Data.csv id 1079.

        Matched by the `rare_candy` Function Tag (ADR-0006), not by a private id constant. The old
        constant's justification was explicitly *"no other consumer needs the tag"*; Issue #288's
        playability gate needs exactly this fact about a card sitting in HAND OR DECK — a question no
        option-id comparison can answer — so the two would have had to agree by hand. False without a
        tag table, which is this branch's shipped fail direction (the composer is DEFAULT OFF and only
        ever ADDS a line)."""
        cid = self._option_card_id(obs, select, option)
        return bool(self.functions and cid is not None
                    and playability.RARE_CANDY_TAG in set(self.functions.tags(cid)))

    def _rare_candy_ko_candidate(self, obs, select, board, option, opp, opp_player,
                                 retreat_on_menu: bool):
        """BUILD 1 (`enabler_item_composer`, DEFAULT OFF): ``(prizes, active_survives)`` if RARE CANDY
        (id 1079) composes an otherwise-missed KO of the opponent's Active by SKIPPING the Stage 1. The
        legal line (card text, data/EN_Card_Data.csv id 1079; rules.md §4): play Rare Candy (committed
        step[0]) → choose an in-play BASIC (``evolvesFrom`` None) that is NOT ``appearThisTurn`` and NOT on
        turn ≤ 1 ("can't use this card during your first turn or on a Basic Pokémon that was put into play
        this turn") → put an IN-HAND Stage-2 whose chain ROOTS at that Basic (the Stage-2's ``evolvesFrom``
        names a Stage-1 whose ``evolvesFrom`` names the Basic) directly onto it → the Stage-2, carrying the
        Basic's Energy plus this turn's one (sound) attach, affords a MIN-BOUND KO. A benched Basic needs
        the retreat still on the menu to reach the Active.

        Unlike the item tutor, Rare Candy is NOT a tutor — the Stage-2 must ALREADY be in hand
        (``board.hand_ids``), so no ``deck_definitely_has`` whiff-check is needed (in-hand is certain).

        HONEST NOTE (updated 2026-08-06): this branch is **INERT on every shipped deck again**. It was
        recorded inert when none of the then-3 agent decks ran Rare Candy or a Basic→Stage-1→Stage-2 line;
        Issue #288 retired that note because `grimmsnarl_ex` ran both — 1 Rare Candy and Marnie's Impidimp →
        Morgrem → Grimmsnarl ex — and measured the branch correct there on 2026-08-02. PR #436 then deleted
        that deck, and NO surviving deck runs Rare Candy at all (checked across all five `src/agents/*/
        deck.csv`, 2026-08-06), so the branch is forward-looking generality once more. Its real-deck test
        went with the deck; `tests/strategy/test_deferred_planner_cluster.py` carries the whole mechanism on
        a synthetic four-card pool — compose, turn-1, `appearThisTurn`, Stage-2-not-in-hand, and the flag
        gate. The same deletion cost `common.playability`'s Rare Candy escape (ADR-0104 decision 3) its
        shipped-deck instance in the same way.

        Two findings from the 2026-08-02 measurement are worth carrying forward even though the deck is
        gone. The composer is correct on a real engine-backed board, not only on the synthetic pool. And a
        stand-down for want of ENERGY looks exactly like a broken branch from outside — the first probe of
        this code was misread that way, because attack 937 cost {D}{D} and the fixture's Attach Budget could
        offer nothing. None when no composite reaches a KO."""
        if board.turn <= 1:
            return None                                   # Rare Candy is illegal on your first turn
        if not self.stats:
            return None
        me = self._my_player(obs)
        bodies = [(p, False) for p in (me.get("active") or []) if p]
        if retreat_on_menu:
            bodies += [(p, True) for p in (me.get("bench") or []) if p]
        best = None
        for body, benched in bodies:
            if body.get("appearThisTurn"):
                continue                                  # can't Rare Candy a Basic put into play this turn
            base = self.stats.get(body.get("id"))
            if base is None or not getattr(base, "name", None):
                continue
            if getattr(base, "evolvesFrom", None) is not None:
                continue                                  # Rare Candy targets a BASIC only (nothing evolves into it)
            energy = len(body.get("energies") or [])
            for cid in board.hand_ids:                    # the Stage-2 must ALREADY be in hand
                st = self.stats.get(cid)
                if st is None or not getattr(st, "stage2", False):
                    continue                              # a Stage-2 card only
                if not self._stage2_roots_at(st, base.name):
                    continue                              # its chain must root at THIS Basic (skip Stage 1)
                budget, attack_p = self._ko_line_pricing(cid, body, benched=benched)   # per-candidate
                if budget is None or self._best_affordable_ko_value(
                        obs, board, opp, cid, energy, bound="min", body=body,
                        attack_p=attack_p, budget=budget) <= 0:
                    continue
                my_hp = getattr(st, "hp", 0) or 0
                cand = (self._prize_value(opp),
                        bool(my_hp) and self._survives_after_ko(cid, my_hp, opp_player),
                        self._composed_line_p(obs, board, opp, cid, energy, body,
                                              attack_p, budget=budget))
                if best is None or _composed_rank(cand) > _composed_rank(best):
                    best = cand
        return best

    def _stage2_roots_at(self, stage2_stat, basic_name: str) -> bool:
        """BUILD 1 helper: the Stage-2 ``stage2_stat``'s evolution chain roots at the Basic ``basic_name`` —
        i.e. some Stage-1 card is named ``stage2_stat.evolvesFrom`` AND that Stage-1's ``evolvesFrom`` names
        the Basic. Verifies the exact two-hop line Rare Candy skips (Basic → Stage-1 → Stage-2), by name,
        against the real card data (never mainline recall — rules.md §4). False when the intermediate
        Stage-1 can't be resolved."""
        stage1_name = getattr(stage2_stat, "evolvesFrom", None)
        if not stage1_name:
            return False
        for s1_id in self.stats.ids_for_name(stage1_name):
            s1 = self.stats.get(s1_id)
            if s1 is not None and getattr(s1, "evolvesFrom", None) == basic_name:
                return True
        return False

    def _tutor_evolution_wins(self, obs, board, opp, body) -> bool:
        """SOUND: some DIRECT evolution of ``body`` (its `evolvesFrom` names the body) is PROVABLY
        still in my deck (the tracker's positive certainty, `Board.deck_definitely_has`), is
        Salvatore-eligible (no Abilities — the card's own fetch filter), and — carrying the body's
        Energy plus this turn's one attach — takes a min-bound winning KO (`_develop_wins`). The
        family's tier-4 win test; multi-hop descendants are excluded (one Salvatore = one hop)."""
        if not self.stats:
            return False
        base = self.stats.get(body.get("id"))
        if base is None or not getattr(base, "name", None):
            return False
        energy = len(body.get("energies") or [])
        extra = 1 if (board.reusable_energy_in_hand and not board.energy_attached) else 0
        for cid in set(self.deck):
            st = self.stats.get(cid)
            if (st is None or getattr(st, "evolvesFrom", None) != base.name
                    or getattr(st, "hasAbility", False)):
                continue
            if not board.deck_definitely_has(cid):
                continue
            if self._develop_wins(obs, board, opp, cid, energy + extra, body=body):
                return True
        return False

    def _retreat_ko_candidate(self, obs, board, opp, opp_player, *, supporter_spent: bool = True):
        """``(prizes, active_survives)`` for the best benched body that KOs the opponent's Active AFTER a
        retreat plus this turn's one attach — but that does NOT already KO at its current Energy (that
        single-step case is the existing ``_retreat_to_lethal_tactical`` hook's job). Among the KO-capable
        bodies (all take the same prize off the shared target) it prefers the one that SURVIVES the
        opponent's post-KO Incoming. None when no benched body needs the attach to reach a KO. Reuses the
        shared sound KO valuation (``_best_affordable_ko_value``: Weakness/Resistance, ex-immunity).

        The line's attach capacity is the typed Attach Budget built for THIS benched body (ADR-0075)
        — ``benched=True``, because the attach can be made before the retreat and no modelled accel
        clause requires an Active target, so it is a strict superset naming a real sequence.
        ``supporter_spent`` DEFAULTS TRUE and that is load-bearing (ADR-0075). A bare retreat spends
        no card and is tiered ``_PLANNER_ENABLER_FREE`` for exactly that reason, so its Budget must
        not quietly include a Supporter's yield — a KO funded by Hilda's fetch is not a free-enabler
        KO, and crediting it as one inverts ADR-0031's rule that an enabler PRESERVING deck/slot
        resources outranks a tutor reaching the SAME KO. Only :meth:`_supporter_ko_candidate`, whose
        committed first step IS that Supporter, passes False."""
        me = self._my_player(obs)
        best = None                                   # (prizes, survives)
        for p in (me.get("bench") or []):
            if not p:
                continue
            energy = len(p.get("energies") or [])
            if self._best_affordable_ko_value(obs, board, opp, p.get("id"), energy, body=p) > 0:
                continue                              # retreat alone already KOs — existing hook owns it
            budget, attack_p = self._ko_line_pricing(p.get("id"), p, benched=True,
                                                     supporter_spent=supporter_spent)
            if budget is None or self._best_affordable_ko_value(
                    obs, board, opp, p.get("id"), energy, body=p,
                    budget=budget, attack_p=attack_p) <= 0:
                continue
            cand = (self._prize_value(opp), self._survives_after_ko(p.get("id"), p.get("hp", 0), opp_player))
            if best is None or cand > best:           # prefer more prizes, then survival (bool > bool)
                best = cand
        return best

    def _tutor_evolve_ko_candidate(self, obs, board, opp, opp_player, retreat_on_menu: bool):
        """``(prizes, active_survives)`` if playing an **evolution-tutor Supporter** (Salvatore: evolve
        one of my in-play Pokémon straight from the deck — the ``rush_evolve`` tag) unlocks an
        otherwise-missed KO of the opponent's Active: some DIRECT, no-Ability evolution still LIKELY in
        my deck (``deck_contains_probability`` majority-odds — rank-grade, the win rung upstream owns
        the certain case), put onto an in-play body and carried to the Active (a benched body needs the
        retreat still on the menu), affords a KO with the body's Energy plus this turn's one attach.
        No closed-form hook scores a Supporter first-step, so this is net-new (the a212 shape:
        Salvatore -> Mega Starmie onto a setup Staryu -> free retreat -> attach -> Jetting Blow).
        None when no such evolution reaches a KO.

        The Budget is built for the FETCHED evolution (ADR-0075) — its stats gate every accel
        clause's target restriction — over the body the Energy carries through, with
        ``supporter_spent=True`` because Salvatore IS the Supporter this line plays."""
        me = self._my_player(obs)
        # (body, benched) rather than a flat list: the Budget must know where the target SITS, and a
        # bench-restricted accel clause funds one and not the other (ADR-0075 decision 4). The flat
        # `active + bench` this replaced lost that, silently.
        bodies = [(p, False) for p in (me.get("active") or []) if p]
        if retreat_on_menu:
            bodies += [(p, True) for p in (me.get("bench") or []) if p]
        best = None
        for body, benched in bodies:
            base = self.stats.get(body.get("id")) if self.stats else None
            if base is None or not getattr(base, "name", None):
                continue
            energy = len(body.get("energies") or [])
            for cid in set(self.deck):
                st = self.stats.get(cid)
                if (st is None or getattr(st, "evolvesFrom", None) != base.name
                        or getattr(st, "hasAbility", False)):
                    continue
                # ADR-0074 decision 1 forbids a THRESHOLD: the retired `<= 0.5` cut-off scored a
                # 0.51 fetch and a 0.99 fetch identically and a 0.49 one at zero — the same
                # boolean-collapse defect #175 exists to remove. The odds are now the weight.
                present_p = board.deck_contains_probability(cid)
                if present_p <= 0.0:
                    continue                          # provably gone — nothing to rank
                budget, attack_p = self._ko_line_pricing(cid, body, benched=benched,
                                                         supporter_spent=True)
                if budget is None or self._best_affordable_ko_value(
                        obs, board, opp, cid, energy, body=body,
                        budget=budget, attack_p=attack_p) <= 0:
                    continue
                my_hp = getattr(st, "hp", 0) or 0
                cand = (self._prize_value(opp),
                        bool(my_hp) and self._survives_after_ko(cid, my_hp, opp_player),
                        present_p)
                if best is None or _composed_rank(cand) > _composed_rank(best):
                    best = cand
        return best

    def _supporter_ko_candidate(self, obs, select, board, option, opp, opp_player):
        """``(prizes, active_survives)`` if playing a **tutor-energy Supporter** (Hilda: search an Energy
        into hand — the ``tutor_energy`` tag) unlocks an otherwise-missed retreat→attach→KO. The Supporter
        SUPPLIES the attachable Energy the plain retreat line lacks: with that fetched Energy modelled as
        this turn's one attach, a benched body KOs the opponent's Active after a retreat. The enabling
        first step here is the Supporter, not a retreat/evolve — no closed-form hook scores it, so it is
        net-new (corpus 4298). Fires ONLY when no reusable Energy is already in hand (else the plain
        retreat line covers it) AND the turn's one attach is still available (else the fetched Energy can't
        power the KO this turn). None otherwise. Reuses the sound retreat-KO valuation."""
        if board.energy_attached or board.reusable_energy_in_hand:
            return None
        if not self._is_energy_tutor(obs, select, option):
            return None
        # The Supporter leg stays OPEN here, and that is the opposite of the sibling Salvatore line
        # (`_tutor_evolve_ko_candidate`, which passes supporter_spent=True). The discriminator is
        # whether THIS line's Supporter contributes to the Budget:
        #   * Hilda is `tutor_energy` with a readable deck-fetch clause, so she IS the Budget's
        #     energy source for her own line — closing the leg would delete the very yield the line
        #     depends on and make it structurally dead (measured: her Budget is size 1 open, 0 closed).
        #   * Salvatore is `rush_evolve` with NO accel tag, so it contributes nothing and merely
        #     SPENDS the slot — leaving the leg open there would let the Budget assume a different
        #     Supporter is also played, which is the illegal two-Supporter turn.
        # Double-counting is structurally impossible either way: each Supporter is a separate
        # alternative play-set, so a hand holding both Hilda and Crispin still yields size 1, never 2.
        return self._retreat_ko_candidate(obs, board, opp, opp_player, supporter_spent=False)

    def _evolve_ko_candidate(self, obs, select, board, option, opp, opp_player):
        """``(prizes, active_survives)`` if EVOLVING the Active unlocks a KO of the opponent's Active this
        turn — the evolved form (the option's in-hand card) inherits the Active's Energy and, with this
        turn's one attach, its best affordable attack KOs. Evolving then attacking is legal the same turn
        (rules.md §evolution). No closed-form hook scores an evolve-unlock, so this is always net-new.
        Survival uses the evolved form's HP (closed-form approximation; the P3 engine-sim is exact).
        None when evolving doesn't reach a KO.

        The Budget is built for the EVOLVED form at ``benched=False`` (ADR-0075) — this line evolves
        the ACTIVE, so the target sits Active and a bench-restricted clause (Wondrous Patch) must NOT
        fund it."""
        evolved_id = self._option_card_id(obs, select, option)
        if evolved_id is None:
            return None
        energy = board.my_active_energy
        ma = next((p for p in (self._my_player(obs).get("active") or []) if p), None)
        budget, attack_p = self._ko_line_pricing(evolved_id, ma, benched=False,
                                                 supporter_spent=True)   # an EVOLVE spends none
        if budget is None or self._best_affordable_ko_value(
                obs, board, opp, evolved_id, energy, body=ma,
                budget=budget, attack_p=attack_p) <= 0:
            return None
        estat = self.stats.get(evolved_id) if self.stats else None
        my_hp = getattr(estat, "hp", 0) or 0          # evolved max HP — P3 engine-sim resolves damage exactly
        return (self._prize_value(opp), self._survives_after_ko(evolved_id, my_hp, opp_player))

    def _free_evolve_ko_candidate(self, obs, select, board, option, opp, opp_player,
                                  retreat_on_menu: bool):
        """``(prizes, active_survives)`` if a FREE direct-evolve of a BENCHED body unlocks an
        otherwise-missed KO of the opponent's Active — the CHEAPEST enabler of all: the evolved form
        is already in hand and the engine only emits this type-9 EVOLVE option for a body legally
        evolvable this turn (its presence IS the legality signal — no ``appearThisTurn`` read needed),
        so no card leaves the deck and no tutor is spent. The benched body, evolved, carries its
        Energy plus this turn's one attach and — reaching the Active via the retreat still on the menu
        — affords a KO. Mirrors ``_tutor_evolve_ko_candidate``'s benched-body + retreat modelling, but
        keyed on the in-hand evolved form the option names (not a deck fetch). None when no retreat is
        available to promote the benched attacker, or the evolution doesn't reach a KO.

        The Budget is built for the EVOLVED form at ``benched=True`` (ADR-0075) — the evolve happens
        on the Bench and the retreat follows, so a bench-restricted clause legitimately funds this
        line."""
        if not retreat_on_menu:
            return None                                   # a benched attacker needs the retreat to attack
        evolved_id = self._option_card_id(obs, select, option)
        if evolved_id is None:
            return None
        idx = option.get("inPlayIndex")
        bench = self._my_player(obs).get("bench") or []
        body = bench[idx] if (idx is not None and 0 <= idx < len(bench)) else None
        if body is None:
            return None
        energy = len(body.get("energies") or [])
        budget, attack_p = self._ko_line_pricing(evolved_id, body, benched=True,
                                                 supporter_spent=True)   # an EVOLVE spends none
        if budget is None or self._best_affordable_ko_value(
                obs, board, opp, evolved_id, energy, body=body,
                budget=budget, attack_p=attack_p) <= 0:
            return None
        estat = self.stats.get(evolved_id) if self.stats else None
        my_hp = getattr(estat, "hp", 0) or 0
        return (self._prize_value(opp),
                bool(my_hp) and self._survives_after_ko(evolved_id, my_hp, opp_player))

    # ---- leaf evaluation (ADR-0031 decision 4): scalar over the resulting end-of-turn board ---------
    def _leaf_value(self, *, prizes: float, active_survives: bool, threat_removed: float = 0.0,
                    development: float = 0.0, value: float = 0.0, readiness: float = 0.0,
                    line: float = 0.0) -> float:
        """The leaf-eval scalar over a resulting board: prizes taken (dominant, KO_SCORE-weighted) +
        the threat removed + my Active's survival vs Incoming + MY-side ``readiness`` (the board-state
        value function, `_readiness`; 0 for closed-form candidates) + the signed ``line`` account (the path
        term of `turn_value = readiness(end) + Σ ability-fire credits − Σ spend costs`, `_line_account`;
        0 off the engine-sim path) + the Base Automatic Value Model's re-centred P(win) (``value ∈ [-0.5,
        0.5]``, Tier-5/ADR-0042; 0 when off/absent). The legacy ``development`` term (`_board_development`)
        is retained for back-compat (default 0) — the engine-sim leaf now feeds ``readiness`` instead. EVERY
        positional term is capped and their capped sum stays below one prize, so a bigger KO always ranks
        first — a positional score can NEVER outrank a real prize (the hard-rung invariant, ADR-0031
        decision 3). The learned term REFINES; it never overrides a sound rung. ``line`` is a pure path
        term (additive, no state double-count — its referent is the ACTION taken, not the resulting board)."""
        return (KO_SCORE * prizes
                + min(_PLANNER_THREAT_CAP, _PLANNER_THREAT_W * threat_removed)
                + (_PLANNER_SURVIVAL_W if active_survives else 0.0)
                + min(_PLANNER_DEV_CAP, _PLANNER_DEV_W * development)
                + min(_READINESS_CAP, readiness)
                + _PLANNER_VALUE_W * value
                + min(_LINE_CAP, line))

    def _survives_after_ko(self, my_id, my_hp, opp_player) -> bool:
        """True if my body (``my_id`` at ``my_hp``) survives the opponent's Incoming AFTER I KO their
        Active this turn — their best affordable REMAINING attacker (a benched body they promote) can't
        KO it. The 1-ply survival term for the leaf-eval (ADR-0031 decision 2); the opponent's Active is
        excluded because the line Knocks it Out. False when my HP is unknown."""
        bench = (opp_player or {}).get("bench") or []
        return bool(my_hp) and self._incoming_worst(my_id, my_hp, bench) < my_hp

    def _incoming_worst(self, my_id, my_hp: int, opp_bodies) -> int:
        """The worst Weakness/Resistance-adjusted damage the opponent's affordable attackers among
        ``opp_bodies`` could deal to my body next turn — the closed-form **Incoming** (CONTEXT.md).
        A thin adapter over ``CombatMath.reachable_incoming`` (ADR-0064): the reachability read now
        counts each body's CURRENT form AND one reachable EVOLUTION hop (their promote→evolve→attach→
        attack development step), not just the current body. Still an upper-bound (a form's biggest
        attack is credited once it can pay its cheapest, worst-case), so a survival check stays
        conservative. The energy policy is the per-decision budget (``_incoming_budget``): ``None``
        → worst-case ceiling (unmatched Read); a charged dict → per-attack typed affordability under
        the matched-Read burst budget. 0 when unknown."""
        my_stat = self.stats.get(my_id) if (self.stats and my_id is not None) else None
        if not (my_stat and my_hp):                       # unknown my card → no claim (contract-preserving)
            return 0
        model = self._state_model
        if model is None:
            return 0                                      # no snapshot → no claim, as above
        # AREA-AT-DAMAGE-TIME (ADR-0070 §9): ACTIVE, declared explicitly. `_survives_after_ko` asks
        # about the body that will be Active AFTER my line resolves — the lethal tiers promote a
        # benched body before it swings — so its CURRENT board area is irrelevant here. Inferring the
        # area from the board would hand those bodies bench immunity and manufacture phantom lethals.
        #
        # Off the SNAPSHOT (POC-T1), with `bodies=` naming the post-line opponent side (the caller
        # excludes the Active my line Knocks Out) and the threaded `_incoming_budget` as the policy.
        return int(model.theirs.reachable_incoming(
            {"id": my_id, "hp": my_hp}, bodies=opp_bodies,
            context=self._opp_attack_context, my_benched=False))

    def _threat_magnitude(self, opp) -> float:
        """The threat magnitude of the opponent's Active — its biggest printed attack — as the
        ``threat_removed`` term when a line KOs it. A coarse "how dangerous was the body I removed"
        signal; 0 when unknown."""
        stat = self.stats.get((opp or {}).get("id")) if (self.stats and opp) else None
        return float(getattr(stat, "maxDamage", 0) or 0) if stat else 0.0

    def _my_player(self, obs) -> dict:
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        return players[yi] if 0 <= yi < len(players) and players[yi] else {}

    def _opp_player(self, obs) -> dict:
        state = obs.get("current") or {}
        players = state.get("players") or []
        oi = 1 - state.get("yourIndex", 0)
        return players[oi] if 0 <= oi < len(players) and players[oi] else {}

    def _leaf_state_model(self, end, my_index: int):
        """The simulated end-of-turn board, as a :class:`StateModel` for `state_value` to score.

        The engine hands back an observation-shaped dict, which is exactly what `StateModel.build`
        takes, so this is a construction rather than a translation — no second reading of the board
        is created and nothing here re-derives a fact the snapshot already owns.

        Three suppliers are threaded because `state_value`'s families genuinely need them and the
        model is the only route to them (the sole-supplier ruling): ``deck`` for the Count Triple and
        the evolution topology, ``role_worth`` for the deck-DECLARED Roles that `readiness` and
        `development` weigh by (Roles are declaration, not card data), and ``needs`` for the
        assignment the `hand` family's `set_keep_v2` spine reads. ``needs`` resolves LAZILY — the
        model invokes the callable only if some family asks — so a leaf that never reaches the hand
        term pays nothing for the DP, which is the whole point of ADR-0068's laziness.

        ``my_index`` is passed explicitly rather than left to ``yourIndex``: the simulated board is
        handed back from whichever seat the sim ended on, and reading the wrong side would score the
        opponent's position and rank every candidate backwards.

        ``turn_boosts`` is DELIBERATELY not threaded, and this says so because the omission looks
        exactly like the bug it is not (Issue #282). `StateModel.build` takes the match-scoped
        `TurnBoostTracker` and the Pilot's live per-decision snapshot passes it; this board is
        different in kind. `_simulate_line` stops when the select passes to the opponent, so ``end``
        is MY END-OF-TURN board — and a flat Trainer boost is *"During this turn"*
        (`data/EN_Card_Data.csv`, Premium Power Pro / Black Belt's Training), so by then it has
        expired. Handing the live tracker over would inject a dead boost into the context that
        `state_value`'s `threat` reads, over-claiming a Knock Out I could not actually take next
        turn — the one direction an offensive gate must not fail in. The boost's real value is
        already in this board: the sim CASHED it, so the prize it bought is in ``prize_race``. The
        Tool half is different again and needs no thread — an attached Tool is visible board state
        and `_SideBase.damage_boosts` reads it straight off the holder."""
        return StateModel.build(
            end, combat=self.combat, my_index=my_index, deck=self.deck,
            role_worth=self._role_value,
            # The BOUND METHOD, not a closure over ``end`` (Issue #400 Phase 2). `StateModel.build`
            # binds a board-bound supplier to the observation it is building, so a hypothetical
            # reached through `rebuilt` resolves its OWN hand instead of inheriting this one's — the
            # staleness that made `state_value`'s `hand` family constant across a whole
            # `composer.compose` call and priced a fetch at exactly 0.0.
            needs=self._leaf_needs_resolution)

    def _leaf_needs_resolution(self, end, my_index: int):
        """The `needs.Resolution` for a simulated end board's HAND, or None when there is no hand to
        resolve.

        The sim only injects my hand when the hand-value plumbing is on, and a board without one
        cannot be asked what its hand covers — so this returns None and `state_value`'s `hand` family
        prices a REAL zero (no cards, no coverage) rather than a hidden one. Never raises: a
        featurize slip must not crash ranking, exactly as the retired `pilot._hand_readiness`
        established (POC-T4/5 deleted that term; the never-raises contract outlived it).

        `include_general=False` keeps the LATENT worth out of the assignment and hands it over as
        `latent_worth` instead, because the two enter `hand` as separate legs and letting the general
        slot carry it as well would price one card twice — this module's headline rule, one seam
        over.

        **The live `_state_model` is saved and restored around the hypothetical build (POC-T4/5,
        Issue #386), and this is the ONE place that requirement belongs.** `_board_hypothetical`
        reaches `_snapshot`, which *builds and STASHES* the per-decision model — deliberate for a
        caller that wants to evaluate against the hypothetical board, and correct for every caller
        this method had before the composer was armed, all of which ran under `_planning` with the
        live readers stood down. This one does not: `state_value`'s `hand` family calls it through
        `needs` during a LIVE decision, three times on an ordinary board, and without the restore
        every later reader of `self._state_model` in the same `explain()` sees the HYPOTHETICAL
        end-of-turn board.

        The damage was silent and specific. `_attach_value` reads `self._state_model.mine`; against
        the leaked leaf model `_attach_body_view` returned None, `can_attack_tonight` went False,
        and a one-shot Energy that unlocks a 210-damage attack THIS TURN read as evaporating for
        nothing — `this_turn` 90.0 -> 0.0, marginal +90.0 -> -30.0, with nothing about the attach
        changed. A snapshot taken as a side effect of building a Board is safe only while nobody
        builds a Board speculatively. The composer does, constantly."""
        cur = (end or {}).get("current") or {}
        players = cur.get("players") or []
        me = players[my_index] if 0 <= my_index < len(players) and players[my_index] else {}
        if not me.get("hand"):
            return None
        mobs = {**end, "current": {**cur, "yourIndex": my_index}}
        live_model = getattr(self, "_state_model", None)
        try:
            board = self._board_hypothetical(mobs)
            rows = self._needs_hand_rows(mobs, board)
            if not rows:
                return None
            slots, elig = self._resolve_needs(mobs, board, rows, include_general=False)
            # Deferred import: `_GENERAL_WORTH_W` lives in `common.pilot`, which imports THIS
            # module, so a top-level import would be a cycle. Function-local rather than a second
            # copy of the constant — a hand-kept duplicate is the drift ADR-0087 charges for.
            from common.pilot import _GENERAL_WORTH_W
            covered = {i for i, e in enumerate(elig) if e}
            latent = sum(_GENERAL_WORTH_W * self._role_value(r["cid"])
                         for i, r in enumerate(rows) if i not in covered)
            return needs.Resolution(slots=tuple(slots), eligibility=tuple(elig),
                                    resupply=tuple([0.0] * len(slots)),
                                    hand_ids=tuple(r["cid"] for r in rows),
                                    latent_worth=float(latent))
        except Exception:
            return None
        finally:
            # Restore unconditionally: the early `return None` paths above build a Board too.
            self._state_model = live_model

    def _board_hypothetical(self, obs):
        """Build a :class:`Board` on a HYPOTHETICAL obs (a simmed end-of-turn board) for FEATURES
        only, without letting it pollute the live turn-scoped memory.

        Passing the **Carried State** snapshot is what guarantees that (ADR-0068 decision 2): the
        phase hysteresis and path stickiness are read from the snapshot and their new values
        discarded, so the build cannot write them at all. This replaced a hand-written
        snapshot-and-restore around the call — a guard every future hypothetical-build site would
        otherwise have had to remember, and the third copy of which this phase declined to write.

        **What it does NOT guard is the `_state_model` stash**, and that matters since POC-T4/5.
        `_board` reaches `_snapshot`, whose job is to *build AND STASH* the per-decision model onto
        `self._state_model`. Callers that build a hypothetical board and then evaluate something
        AGAINST it depend on exactly that (`tests/strategy/test_hand_size_relief.py` is the clearest
        example), so the stash is deliberate here and stays. The caller that must NOT leak is
        `_leaf_needs_resolution`, which runs inside a LIVE decision — it does the save/restore
        itself, where the requirement actually lives."""
        return self._board(obs, (obs or {}).get("select"), carried=self.carried())

    def _line_account(self, traces, indices) -> float:
        """The SIGNED path term of `turn_value = readiness(end) + Σ ability-fire credits − Σ spend costs`
        (t0-planner-disposition.md Decision 1) for the CHOSEN options at ONE step: the POSITIVE weight of
        every `_ABILITY_FIRE_IDS` rule that fired (using a beneficial setup Ability — value the end board
        can't show) MINUS the magnitude of every NEGATIVE `_CLASS_B_SPEND_IDS` rule that fired (consuming a
        scarce resource — spent cards don't show, hand hidden). REUSES the LIVE tuned weights
        (`OptionTrace.fired` carries the effective weight); never re-derived, never a score of the resulting
        BOARD (the classification guard against state-summing drift — the referent is always the ACTION)."""
        total = 0.0
        for i in indices:
            if not (0 <= i < len(traces)):
                continue
            for h, w in (getattr(traces[i], "fired", None) or ()):
                hid = getattr(h, "id", None)
                if w > 0 and hid in _ABILITY_FIRE_IDS:
                    total += w
                elif w < 0 and hid in _CLASS_B_SPEND_IDS:
                    total += w                            # w is negative — a spend subtracts
            total += getattr(traces[i], "attach_spend", 0.0) or 0.0   # the burst evaporation loss
        return total

    def _simulate_line(self, obs, first_step, max_steps: int = 40, *, opponent_reply: bool = False):
        """Forward-simulate a candidate line through the Engine Search to my end-of-turn board.

        **No production caller — the RUNTIME ROLLOUT ROLE is retired** (POC-T4/5, Issue #386;
        Issue #263 § *Parity + retirement*). Nothing in a live decision sims a line any more: the
        develop rollout, `_commit_best`'s engine ranking and `_engine_leaf_value` are all deleted, and
        ranking end states is the composer's job, done closed-form off `apply_option`. What survives
        here is the OFFLINE engine forward-sim primitive its instruments still drive —
        `tools/train/family_diag.py`'s per-family attribution, the cgpy↔native agreement lane
        (`tests/strategy/test_engine_agreement_engine.py`) and the determinism backstop — because
        those measure the ENGINE, not the retired rung. The `_search_api` seam it reads is preserved
        by name for the same reason plus `fate()`'s ENGINE-RESOLVED route.

        **Issue #178's ``stream`` half is DELETED with its only reader.** `_develop_rollout_line`
        read it to refuse an unreproducible ranking outright (all-or-nothing); with no rung ranking
        sim values, a bit that exists to demote one has nothing to demote, and an unread bit is the
        kind of forward contract ADR-0102 stopped accepting. ``coins`` stays — it is the
        *is this line RNG-free* fact the win rung's own verdict driver speaks in
        (`_rng_probe(prize=False)`, preserved by name).

        Steps ``first_step``, then re-runs my own closed-form policy (``decide``) on each
        intermediate SearchState until my turn ends (the select passes to the opponent) or the game
        finishes — the ADR-0031 "re-running the policy on each intermediate SearchState." Returns
        ``(end_obs_dict, my_index, start_prizes, result)`` or **None** when the search is unavailable,
        the observation carries no ``search_begin_input``, or anything errors (the caller falls back to
        the closed-form value — never crashes). The 5th tuple element is the SIGNED ``line`` account (the
        path term of `turn_value = readiness(end) + Σ ability-fire credits − Σ spend costs`): the net
        `_line_account` over MY chosen actions along the line — the first step plus every greedy
        continuation step. Opponent-reply steps (Tier-6) never contribute.

        With ``opponent_reply=True`` (Tier-6, ADR-0043) the sim does NOT stop at my turn end: it keeps
        stepping through the OPPONENT's turn using our own policy as the reply proxy, until it is my
        turn again or the game finishes — so the returned board is the start of MY next turn, seeing
        the opponent's best (proxy) answer. Every step decrements the per-move ``_search_steps``
        budget; the sim halts when it is spent (returns the board reached so far).

        Heuristic, not sound (ADR-0031): coins auto-resolve (``manual_coin=False``) and the opponent's
        hidden zones are predicted from my own deck list, so the end-of-turn board is trusted for
        ranking, not as a guarantee. The live game is untouched (the search forks an independent sim).
        Lazy DLL import keeps the fast unit suite from ever loading the native engine.

        The 6th tuple element is ``coins`` — a ``LogType.COIN`` flip appeared along the line
        (``manual_coin=False`` auto-resolves them), measured on the logs by `_rng_probe`. Absent
        under a backend that emits no logs, where behavior is unchanged.

        The measurement the deleted ``stream`` bit was minted for is kept on the record because it
        is the reason no rung may rank a sim value again: on ml f24 (2026-07-27, Issue #178) all 13
        candidate first actions carried ``SHUFFLE`` + ``DRAW`` and **not one COIN**, and each one's
        leaf value swung across processes — 7000 / 162 / 129 / 122 / 89 / 57.5 on the same first
        step. A shuffle-riding sim returns one SAMPLE, not a distribution."""
        if not (obs or {}).get("search_begin_input") or not first_step:
            return None
        cgapi = getattr(self, "_search_api", None)     # injectable search backend (leaf-lab harness sets
        if cgapi is None:                              # cgpy's `cg.api`-shaped surface to re-score tagged
            try:                                       # correction boards offline); production uses native
                from cg import api as cgapi
            except Exception:
                return None
        from dataclasses import asdict
        cur = obs.get("current") or {}
        my_index = cur.get("yourIndex", 0)
        players = cur.get("players") or []
        me = players[my_index] if 0 <= my_index < len(players) and players[my_index] else {}
        opp = players[1 - my_index] if 0 <= 1 - my_index < len(players) and players[1 - my_index] else {}
        start_prizes = len(me.get("prize") or [])
        yd, yp, od, op_, oh = self._seed_zones(obs, me, opp)   # ADR-0050: exact own split when anchored

        def budget_ok() -> bool:
            if not opponent_reply:
                return True                            # Tier-1 sims are unbudgeted (the original path)
            self._search_steps = getattr(self, "_search_steps", 0) + 1
            return self._search_steps <= self.search_budget

        self._planning = True                          # never nest a search inside the reply policy
        line_val = 0.0
        try:
            root = self._evaluate(obs, carried=self.carried())   # the root re-score reads the phase/
            line_val += self._line_account(root.options,         # path memories from the Carried
                                           list(first_step))     # State snapshot and writes neither,
                                                                 # so the live turn is untouched by
                                                                 # construction (ADR-0068) — this was
                                                                 # a hand-written save/restore pair
            ob = cgapi.to_observation_class(obs)
            st = cgapi.search_begin(ob, yd, yp, od, op_, oh, [], manual_coin=False)
            st = cgapi.search_step(st.searchId, list(first_step))
            crossed_my_turn_end = False
            # WP-N5b/N5d: the end obs is OPPONENT-perspective (my turn passed), so my hand is hidden.
            # To let the leaf value it, capture a HELD-CONTEXT snapshot from the
            # LAST my-perspective step — the hand, plus the turn facts the N5d deployability
            # counterfactual read: the attach/Supporter quotas, my bodies
            # with their fresh `appearThisTurn` bits (the end board may reset them), bench fullness.
            # Injected into the end obs (the `heldCtx` private key beside the injected `hand`).
            # Seeded from the live start-of-turn state (fallback if the turn ends before any
            # my-select). v1 caveat: the capture is BEFORE my final action, so it is one action
            # stale.
            #
            # Gated — off = the sim is byte-identical.
            #
            # **POC-T3 (Issue #262) tried arming this unconditionally and MEASURED it worse.**
            # `state_value`'s `hand` family has no data without this capture, and a family that can
            # never receive data is the silent-zero the registry exists to prevent — so arming it
            # looked obviously right. It is not, and the reason is the v1 caveat two lines up: the
            # snapshot is taken BEFORE my final action, so it is one action stale, and *how* stale
            # differs per branch (a line that ends the turn at once captures its start-of-turn hand;
            # a line that plays three cards captures the hand after two). Fed into the one family
            # whose whole job is pricing what leaving my hand COSTS, that made a branch which SPENT a
            # card score a HIGHER hand value than one that spent nothing — 83686860|1|decision|13,
            # hand +0.586 for the play against +0.442 for End. The Discrimination Gate agreed:
            # 104 unruled OK->MISS armed against 67 unarmed.
            #
            # Fixing it properly needs a snapshot at the TRUE end of my turn, which this loop cannot
            # take: the end observation is opponent-perspective, so my hand is hidden by then. That
            # is a substrate gap, not a tuning choice. So the capture stays off, `hand` prices a
            # REAL zero on the leaf path (no hand on the board, no coverage), and the gap is NAMED in
            # `state_value.REGISTRY`'s `hand.blind_to` where Issue #263 reads it as a blind spot
            # rather than discovering it as a mystery. Old Issue #145's grill item 3
            # (*"`leaf_hand_value` fate"*) therefore stays open, with a measurement attached.
            capture_hand = getattr(self, "leaf_hand_value", False)

            def _held_snapshot(player: dict, current: dict):
                if not player.get("hand"):
                    return None
                return {"hand": player["hand"],
                        "supporterPlayed": bool(current.get("supporterPlayed")),
                        "energyAttached": bool(current.get("energyAttached")),
                        "bodies": (player.get("active") or []) + (player.get("bench") or []),
                        "benchFull": len([b for b in (player.get("bench") or []) if b])
                                     >= (player.get("benchMax") or 5)}

            my_ctx = _held_snapshot(me, cur) if capture_hand else None
            coin_t = getattr(getattr(cgapi, "LogType", None), "COIN", None)

            def _saw_coin(ob) -> bool:
                return coin_t is not None and any(getattr(lg, "type", None) == coin_t
                                                  for lg in (getattr(ob, "logs", None) or ()))

            coins = False
            for _ in range(max_steps):
                o = st.observation
                coins = coins or _saw_coin(o)
                c = o.current
                if c is None or c.result != -1 or o.select is None:
                    break                                 # game over
                mine = c.yourIndex == my_index
                if not mine and not opponent_reply:
                    break                                 # Tier-1: stop at my turn end
                if not mine:
                    crossed_my_turn_end = True             # into the opponent's reply now
                elif crossed_my_turn_end:
                    break                                 # back to MY next turn — the depth-2 leaf
                if not budget_ok():
                    break                                 # per-move engine budget spent
                odict = _prune_none(asdict(o))
                if capture_hand and mine and not crossed_my_turn_end:
                    pcur = odict.get("current") or {}
                    ph = pcur.get("players") or []
                    meh = ph[my_index] if 0 <= my_index < len(ph) and ph[my_index] else {}
                    my_ctx = _held_snapshot(meh, pcur) or my_ctx
                dec = self._evaluate(odict)
                if mine and not crossed_my_turn_end:       # only MY within-turn actions carry a line term
                    line_val += self._line_account(dec.options, dec.chosen)
                st = cgapi.search_step(st.searchId, list(dec.chosen))
            coins = coins or _saw_coin(st.observation)       # the final step's logs (a coin-won attack)
            end = _prune_none(asdict(st.observation))
            if capture_hand and my_ctx:                   # inject my hidden hand + held-context
                epl = (end.get("current") or {}).get("players") or []
                if 0 <= my_index < len(epl) and isinstance(epl[my_index], dict):
                    epl[my_index]["hand"] = my_ctx["hand"]
                    epl[my_index]["heldCtx"] = {k: v for k, v in my_ctx.items() if k != "hand"}
            result = st.observation.current.result if st.observation.current else -1
            cgapi.search_end()
            return (end, my_index, start_prizes, result, line_val, coins)
        except Exception:
            try:
                cgapi.search_end()
            except Exception:
                pass
            return None
        finally:
            self._planning = False
