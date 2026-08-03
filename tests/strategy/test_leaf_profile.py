"""Issue #138 Phase 0b — the **Leaf Profile** pin (ADR-0068 decision 1).

Because StateModel fields are lazy, the cost of an evaluation is set by the field SET it touches —
and that set is invisible in the source. Nothing in a future `state_value` term will say "this line
costs you the Needs assignment DP on every one of a dozen forked leaves". So the field set is pinned
here: it grows, this fails, and somebody has to re-measure deliberately.

Pinned as a field-SET SNAPSHOT and deliberately NOT as wall-clock — a timing assertion is flaky
across the Windows and Linux CI runners. The measured timings are PR evidence (recorded in the commit
and in ADR-0068's consequences), not assertions.

Both profiles are reported PER SIDE, which is what keeps the side-sharing rationale falsifiable: the
design claims the expensive clusters sit on opposite sides of the table, so the split is the number
that would refute it.
"""
import json
import sys
from pathlib import Path

import pytest

from common.state_model import StateModel

REPO = Path(__file__).resolve().parents[2]

#: The exact model field set ONE per-decision `Board` build touches, as measured on real correction
#: frames. Every entry traces to a field migrated in 0b under ADR-0068 decision 3's criteria; the
#: `theirs.*.prize_value` rows are the prize map the cross-side race composite reads.
#: **Re-measured 2026-07-27 (#142, Phase 1d).** **Famine** is now read off the model on EVERY
#: decision, not only on a menu offering an attach, so the deck-availability chain
#: (`visible_counts` -> `unseen_counts` -> `deck_energy_counts` -> the two typed leg projections)
#: moved out of `ATTACH_DECIDER_PROFILE` and into the per-decision cost. Measured on these frames,
#: dragapult_ex, the retired premise vs the oracle: **1.216 ms -> 1.511 ms per Board build
#: (+0.294 ms, +24%)**. Paid once per decision — every field here memoizes for the life of the snapshot, and
#: both Budget legs share the one `deck_energy_counts` derivation, so the second leg is an extra
#: `attach_budget` assembly rather than a second walk over my zones. Accepted: it is the price of
#: the famine premise being typed and accelerator-aware at all, which is the entire point of the
#: phase, and it is ~3 orders below the per-match budget (grader: 2 vCPUs x ~10 min/match).
#:
#: **Re-measured 2026-08-01 (POC-T1, Issue #260).** The bypass census moved onto the model, so THEIR
#: half's clock family now appears here — the reads are not new work, they are the same reads through
#: the snapshot instead of around it (`theirs.incoming` is the folded doom read; `theirs.turns_to_ko_me`
#: the `opponent_target_value` removal Δ; `theirs.*.attached_types` the deny relevance read). Cost,
#: measured per Board build over each agent's committed correction corpus, this tree vs `origin/main`:
#: **dragapult_ex 1.527 -> 1.554 ms (+1.8%), mega_lucario 1.428 -> 1.581 ms (+10.7%),
#: mega_starmie 1.626 -> 1.749 ms (+7.6%)**. The delta is memo-KEY construction, not derivation: the
#: clock memos key by VALUE now (a canonical projection) rather than by `id()`, because the deny and
#: target instruments hand them TEMPORARY body dicts whose addresses can be reallocated. Keys are
#: cached per object (`_Lazily._key`), which is what keeps the increase in single digits rather than
#: the ~25% a naive re-canonicalisation per read measured. Accepted on the same grounds as above.
#: **Re-measured 2026-08-02 (Issue #261 item 2d).** The Prize Path's their-side gained a second
#: ROUTE to my Bench — the shared-budget rider harvest (ADR-0086 decision 5's sharpening), which
#: `_their_turns_to_ko`'s printed-damage read structurally cannot express. Three fields:
#: `theirs.bench_harvest_clock` plus the two raw opponent-board arguments it takes.
#:
#: The pin caught a real defect before it merged, which is the whole point of it. The obvious
#: spelling asked the clock PER BODY, and the rider budget is a property of the BENCH — so each
#: member re-derived the same payload table and re-ran the same subset search. Measured as an exact
#: in-process A/B (the leg live vs neutered, same pilot, same frames, so machine noise cancels):
#: **+2.48 / +2.65 / +2.71 ms per Board build (+36% / +36% / +32%)** on dragapult_ex / mega_lucario /
#: mega_starmie. Solving the clock ONCE for the whole Bench (`CombatMath.bench_harvest_clock`, which
#: `turns_to_ko_me`'s bench leg now reads underneath, so there is still one derivation) brings that
#: to **+1.75 / +1.56 / +0.33 ms (+24.8% / +21.8% / +3.7%)**. Accepted on the same grounds as the two
#: re-measures above: paid once per decision, memoised for the life of the snapshot, and ~3 orders
#: below the per-match budget (grader: 2 vCPUs x ~10 min/match).
PER_DECISION_PROFILE = frozenset({
    "mine.active",
    "mine.active.energy_count",       # ← POC-T1: Board's `my_active_energy`, off its one home
    "mine.active.energy_key",
    "mine.active.stat",            # the fail-OPEN unreadable-body check the famine read makes first
    "mine.active_famine",
    "mine.attach_budget",
    "mine.attack_blocked",
    "mine.bench",
    "mine.bench_count",               # ← POC-T1: bench occupancy has ONE derivation now
    "mine.bench_full",
    "mine.bodies",
    "mine.body_raws",
    "mine.deck_count",
    "mine.deck_energy_counts",
    "mine.deck_energy_types",
    "mine.deck_energy_types_provable",
    "mine.discard_energy_counts",
    "mine.hand_energy_counts",
    "mine.hand_energy_types",
    "mine.hand_ids",
    "mine.hand_size",                 # ← POC-T1: Board's `my_hand_size`, off its one home
    "mine.prizes_hidden",
    "mine.prizes_remaining",
    "mine.reachable_attach",
    "mine.unseen_counts",
    "mine.visible_counts",
    "model.prize_race",
    "theirs.active",
    "theirs.active.prize_value",
    "theirs.active.attached_types",   # ← POC-T1: Deny Relevance, off the model's BodyView
    "theirs.active_raw",              # ← #261 2d: the harvest clock's opponent-Active argument
    "theirs.bench",
    "theirs.bench.attached_types",
    "theirs.bench.prize_value",
    "theirs.bench_harvest_clock",     # ← #261 2d: the Prize Path's RIDER route to my Bench
    "theirs.bodies",
    "theirs.body_raws",               # ← #261 2d: that clock's opponent-board argument
    "theirs.discard_energy_counts",
    "theirs.discard_ids",             # ← POC-T1: `opp_has_played_gust`, off the public zone
    "theirs.hand_size",               # ← POC-T1: THE supplier of the opponent hand count
    "theirs.incoming",                # ← POC-T1: the FOLDED doom read, at the `UNCHARGED` policy
    "theirs.prizes_remaining",
    "theirs.turns_to_ko_me",          # ← POC-T1: `opponent_target_value`'s removal Δ
})

#: The model fields the ATTACH DECIDER adds on any menu that offers an energy attach (#139,
#: ADR-0069), measured on the mega_starmie attach corpus. They are NOT in the per-decision profile
#: above because the sampled `dp_*` frames happen to carry no attach option — the two sets are
#: measurements of different menus, not a discrepancy.
#:
#: The cluster it drags in is the deck-availability chain (`visible_counts` -> `unseen_counts` ->
#: `deck_energy_counts` -> `deck_energy_types`), which the Attach Budget needs to know which colours
#: the deck can still yield (ADR-0067's fail-OPEN presence gate). That is a deliberate, bounded cost:
#: one pass over my zones per decision, memoized for the whole decision, and it is the price of the
#: Budget being typed at all. Everything else here is body-view construction (dict wrapping, no
#: derivation) plus the memoized per-body Budget and reachable-damage reads.
#: **Re-measured 2026-07-27 (#142).** This set has COLLAPSED, and the collapse is the finding: the
#: deck-availability chain it used to name is now paid on every decision by the famine read, so the
#: attach decider adds essentially nothing over the baseline. The cost moved — it did not grow.
ATTACH_DECIDER_PROFILE = frozenset({
    "mine.best_reachable_damage",
})

#: The model fields the PROMOTE/RETREAT DECIDER adds (#141, ADR-0100) on any menu where it prices an
#: option — a TO_ACTIVE/SWITCH body pick, or a MAIN menu carrying a RETREAT (which is why they show
#: up on the attach corpus at all: those frames are open turn menus).
#:
#: Each read is RULED, not incidental:
#:   * `theirs.active_raw` / `theirs.body_raws` — the survival clock's opponent side, for §4's
#:     per-body `exposure` and `preservation`.
#:   * `mine.bench_raws` — the Bench Harvest's input, for the preservation leg's bench reading.
#:
#: **Re-measured 2026-08-01 (POC-T1, Issue #260).** `theirs.incoming` has LEFT this set — not because
#: §6's `tempo_denied` stopped reading the curve, but because the per-decision build now reads it too
#: (the folded doom read), so it nets out of the "what does this decider ADD" subtraction. The ruling
#: that it is legitimate cost for THIS decider is unchanged; see PER_DECISION_PROFILE.
#:
#: **Re-measured 2026-08-02 (Issue #261 item 2d).** `theirs.active_raw` and `theirs.body_raws` have
#: LEFT for the same reason and with the same caveat: the Prize Path's rider route reads both on
#: EVERY decision now, so they net out of this subtraction. §4's `exposure`/`preservation` still read
#: them, and this decider still pays for them — see PER_DECISION_PROFILE.
PROMOTE_DECIDER_PROFILE = frozenset({
    "mine.bench_raws",
})

#: The model fields the DENY-SLOT keep price adds (ADR-0080 / Issue #187), on any menu where a
#: forced discard prices a held denier. New as a MODEL read in POC-T1 (Issue #260): the deadline
#: grade always read this clock, it just read it around the snapshot.
#:
#: Both entries are ruled cost for this consumer, not a leak:
#:   * `theirs.turns_to_afford` — the deny slot's `/2^t` deadline grade IS this clock. A Hammer on a
#:     body three turns from arming is worth a fraction of one on a body arming next turn.
#:   * `theirs.discard_recur_fuel` — the clock's own input since Issue #204; a refueler reloads
#:     outside the attach quota, so the bare quota does not merely under-state its clock, it is wrong.
#:
#: ⚠️ **UNEXERCISED by this file's corpus, as of Issue #261 item 2h — the CONSUMER is live, the
#: corpus just never reaches it.** Measured 2026-08-02: `_frames()` carries SelectContexts
#: `{0, 2, 7, 22}` and `_attach_frames()` only `{0}` — **no `_DISCARD` select among them** — and
#: `_resolve_needs` runs once per pass emitting only `line` / `fund_attack` / `general` slots. A deny
#: slot never opens here, so the deadline grade is never reached, so neither field is read.
#:
#: Both fields WERE being read on every frame in this file until item 2h — by `_recur_shadow`, which
#: ran on every decision and which that item deleted. So this test was crediting the deny slot for a
#: diagnostic's reads. Nothing about the deny clock changed: `_resolve_needs` still emits
#: `needs.deny_slot(..., turns_to_ready=_opp_turns_to_ready(p))`, that delegates to
#: `TheirSide.turns_to_afford`, and that consumes `discard_recur_fuel` on its `fuelled` leg
#: (Issue #204). `deny_relevance` ships ON.
#:
#: Kept defined, and kept in `LEAF_PROFILE` — the cost claim about the consumer is unchanged and
#: still true where it fires — but no longer asserted as ADDED by the attach test, because asserting
#: a read no frame in the corpus makes is how a test goes vacuous. Restoring it to the pinned set is
#: a matter of giving this file a frame with a forced discard and a held denier, not of re-wiring
#: anything.
DENY_SLOT_PROFILE = frozenset({
    "theirs.discard_recur_fuel",
    "theirs.turns_to_afford",
})

#: The CEILING on the model field set one PLANNER-LEAF evaluation may touch.
#:
#: A leaf does not read the model directly — its own terms (`_readiness`, `_incoming_worst`,
#: `_predicted_loss`) are one-sided closed-form reads that predate it. It reads the model *because
#: `_simulate_line` re-runs my policy to end-of-turn*, and every decision inside that line builds a
#: board. So the honest shape of a leaf's model cost is **N per-decision builds**, where N is the
#: number of decisions the simulated line makes — measured at N = 4 on a real turn-1 drive, against a
#: 12.7 ms leaf whose model share is roughly 0.08 ms (under 1%; the engine sim dominates).
#:
#: Pinned as a SUBSET bound rather than an equality because the set legitimately varies with the end
#: board (an empty bench drops the bench prize-map row). Growth BEYOND the per-decision profile is
#: what matters, and it is the tripwire for #145: the moment `state_value` reads a field the ordinary
#: decision path does not — the Needs assignment, the clock curves, the deck Count Triples — this
#: fails, which is exactly when the per-leaf cost needs measuring against the 2-vCPU / ~10-min grader
#: bank and exactly when nobody would otherwise think to look.
#: A leaf's simulated line re-runs my policy to end of turn, so it reaches menus WITH attaches and
#: pays the attach decider's reads too — hence the union rather than the per-decision set alone.
#: Fields the PLANNER LEAF reads beyond the per-decision build and the two deciders — the
#: `ko_for_prizes` KO lines' own cluster. Separate from `PER_DECISION_PROFILE` because that one is
#: pinned with `==` against a bare Board build, which never reaches these.
KO_LINE_PROFILE = frozenset({
    # The Probability Leg (ADR-0074 decision 2, #175). Every `ko_for_prizes` line reads it once #177
    # folded the five `_play_accel_extra` builders onto the typed Budget (ADR-0075 decision 6) — the
    # five joined the two composed lines that already weighted. Admitted to the pin rather than
    # re-measured: it is the THIRD projection of the SAME `deck_energy_counts` derivation already in
    # `PER_DECISION_PROFILE` (`{t: c.p_any ...}` over an already-memoized map), so it is a dict
    # comprehension, not a second walk over my zones.
    "mine.deck_energy_p",
})

#: The fields **`state_value`** adds when the planner leaf scores its end board (POC-T3 / Issue #262).
#:
#: This is the tripwire above FIRING and being answered, not being widened away. Its own note
#: says the moment `state_value` reads a field the ordinary decision path does not, *"the per-leaf
#: cost needs measuring against the 2-vCPU / ~10-min grader bank"* — so it was measured, on the same
#: real turn-1 engine drive the tripwire itself uses (`test_planner_engine.py`, dragapult_ex):
#:
#:     leaf, hand-composed (`_leaf_value` + `_readiness` + `_value_term`)   16.76 ms median / 20.98 p95
#:     leaf, `KO_SCORE x state_value(end board)`                             3.83 ms median /  5.31 p95
#:     `state_value` alone, on a FRESH model (the T4 1-ply ordering cost)     247 us median /   354 p95
#:     `state_value` re-scored on a WARM model (the ADR-0068 memo hit)         81 us median /   113 p95
#:
#: **The leaf got ~4x cheaper, not dearer**, which is the opposite of what a wider field set
#: suggests and is worth stating plainly: the retired composition ran `_readiness` over every body
#: with its eleven sub-helpers plus the Tier-5 `_value_term`'s hypothetical board build, and the
#: scalar replaces all of that with reads that memoize on the ONE model. The field count went up
#: because the model is now doing the work that used to happen beside it.
#:
#: Every row below is a read some family in the registry is on record as making:
#:   * `mine.attack_payoff` / `mine.bench_names` — `readiness` prices the best attack a body can actually
#:     pay off with ON THIS BOARD, not the printed `CardStat.maxDamage` roll-up (Issue #287,
#:     ADR-0109), and it asks `readiness_p` about THAT attack rather than about "any attack";
#:     pairing a max-damage payoff with the famine probability saturates the term and prunes the
#:     attach that completes it. `bench_names` is the bench-partner condition's input, and it
#:     REPLACED an inline comprehension inside `damage_facts` rather than adding a walk.
#:
#:     Re-pinned with a measurement, as this pin's own rule demands (60 corpus frames, this box):
#:
#:         `state_value` on a FRESH model   before 8.37 ms median / 17.28 ms p95
#:                                           after 8.14 ms median / 13.79 ms p95
#:         the `attack_payoff` read alone, per body   1.80 us first call / 1.40 us memoized
#:
#:     ~2.7 bodies to a board, so the added work is ~5 us against a fresh-model evaluation
#:     dominated three orders of magnitude over by the model's own lazy derivations. The two rows
#:     that left (`mine.active.payoff_attack`, `mine.bench.payoff_attack`) were the printed-only
#:     body-scoped twin this read replaces; it could not see the Bench, which is the whole bug.
#:   * `mine.*.prize_value` + `theirs.turns_to_ko_me` — `survival`, both areas, Bench-Harvest-aware.
#:   * `theirs.active.hp_remaining` — `threat`'s reachability filter (can I actually reach this KO).
#:   * `mine.forward_index` / `forward_payoff` — `development`'s evolution topology, over MY decklist.
#:   * `mine.mine_turns_to_afford` — the forward leg of `readiness`'s odds, so a mid-turn board with
#:     the attach already spent does not go flat.
#:   * `mine.role_worth` — the deck-DECLARED Roles `readiness` and `development` weigh by.
#:   * `mine.needs` — the `hand` family's `set_keep_v2` spine. LAZY: on a simulated board with no
#:     injected hand the resolver returns None and the DP never runs.
STATE_VALUE_PROFILE = frozenset({
    # `state_value` memoizes its own per-family dict on the model (Issue #262's incremental-eval
    # line), so the scalar itself appears as a cross-side memo key beside the fields it reads.
    "model.state_value",
    "mine.active.attacks",
    "mine.active.hp_remaining",
    "mine.active.prize_value",
    "mine.bench.attacks",
    "mine.bench.hp_remaining",
    "mine.bench.prize_value",
    "mine.bench.stat",
    "mine.bench_names",
    "mine.forward_index",
    "mine.forward_payoff",
    "mine.mine_turns_to_afford",
    "mine.needs",
    "mine.attack_payoff",
    "mine.readiness_p",
    "mine.role_worth",
    "theirs.active.hp_remaining",
    "theirs.reachable_incoming",
    "theirs.turns_to_ko_me",

    # ── POC-T3.5 / Issue #281: `threat`'s reachability gate asks the DAMAGE MODEL ──────────────
    # The gate used to read `mine.best_reachable_damage` — the biggest PRINTED number, which is
    # opponent-independent and therefore wrong in both directions (it missed every Weakness Knock
    # Out and claimed every prevented one). It now reads the sibling against their actual Active,
    # which drags in the Damage Formula's scaler context and, with it, the `damage_facts` gatherer
    # on BOTH sides — that is the whole of the growth below.
    #
    # **Measured before re-pinning**, as this pin's own note demands. On the 40-frame corrections
    # corpus, against a `state_value` whose fresh-model median on those (much richer) boards is
    # ~6.7 ms: `damage_context(attacker="mine")` costs **111 us median / 149 us p95 on a FRESH
    # model** and is memoized per direction for the model's lifetime, so every later reader pays a
    # dict lookup. The damage read itself is not new cost: it is the same per-attack loop under the
    # same Budget filter, one closed-form call (`predicted_damage`) where there used to be one field
    # read (`attack_damage`).
    #
    # **Issue #280 added the SECOND direction** (`survival`'s clocks read `attacker="theirs"`) and
    # re-measured, because the sentence above originally predicted it would cost a dict lookup and
    # that was the one number worth checking rather than inheriting. Same 40 frames, same method:
    # one direction on a fresh model 102 us median, BOTH directions on a fresh model **107 us
    # median** — the second direction is ~5 us, not another 100. The reason is structural rather
    # than lucky: the cost is `_SideBase.damage_facts`, one `@lazy` per SIDE that both directions
    # share, and `damage_context` itself only decides which side's record becomes `atk_`/`def_`.
    # So the profile below does not grow at all for Issue #280 — the second direction reads no
    # field the first did not.
    "mine.best_reachable_damage_vs",
    "model.damage_context",
    # the gatherer, and the per-side countables it walks (`_SideBase.damage_facts`). Both sides,
    # because the Formula's variables are `atk_`/`def_`-relative and one direction needs both.
    "mine.damage_facts",
    "theirs.damage_facts",
    "mine.active.damage_counters",
    "mine.active.is_ex",
    "mine.active.tool_ids",
    "mine.bench.damage_counters",
    "mine.bench.is_ex",
    "mine.bench.is_stage2",
    "mine.damage_boosts",
    "mine.discard_energy_total",
    "mine.discard_ids",
    "mine.prizes_taken",
    # The `theirs.bench.*` half of the SAME gatherer. `damage_facts` is one un-overridden method on
    # `_SideBase` — it walks `bodies` and `bench` for `counters_in_play`, `bench_stage2`,
    # `ex_in_play` and `bench_names` — so these are read on any frame where their Bench is not
    # empty. They are DECLARED rather than measured: the engine-driven frame this ceiling is
    # asserted against happens to reach the leaf with an empty opponent Bench. Safe to declare on a
    # `<=` bound (it is a ceiling, not an equality), and the alternative is a latent failure that
    # arrives the first time the drive benches an opposing body.
    "theirs.bench.damage_counters",
    "theirs.bench.is_ex",
    "theirs.bench.is_stage2",
    "theirs.bench.stat",
    "theirs.active.damage_counters",
    "theirs.active.energy_count",
    "theirs.active.energy_key",
    "theirs.active.is_ex",
    "theirs.active.stat",
    "theirs.active.tool_ids",
    "theirs.bench_count",
    "theirs.damage_boosts",
    "theirs.discard_energy_total",
    "theirs.prizes_taken",

    # ── POC-T3.5 / Issue #284: `threat` reads their BENCH as well as their Active ──────────────
    # The loop returned at most one element, so chip standing on their bench between turns was
    # invisible — `dragapult_ex`'s whole win plan. Widening it adds exactly TWO fields, measured
    # with `_Probe` over a board that actually has an opponent Bench (the engine drive this file
    # pins against reaches the leaf with an empty one, so the measurement had to be made on a
    # constructed board and is DECLARED here on the same `<=` ceiling as the `theirs.bench.*` block
    # above):
    #
    #   * `mine.best_reachable_bench_damage` — the bench route. NOT a second damage read: it is the
    #     attack's printed snipe RIDER under the SAME `reachable_attach` Attach Budget the two
    #     existing reachability reads use, so the added cost is one `max` over the attacker's
    #     attacks, memoized per (attacker, defender) on the model. No `context` — a rider ignores
    #     Weakness and Resistance by rule (ADR-0022), so no Damage Formula scaler reaches it and the
    #     `damage_facts` gatherer above is not touched a third time.
    #   * `theirs.bench.hp_remaining` — the counters themselves, the fact the issue exists for.
    #
    # `theirs.bench.prize_value` is read too and is deliberately NOT listed: `PER_DECISION_PROFILE`
    # already carries it (the Prize Path's bench map), and `LEAF_PROFILE` is their union.
    "mine.best_reachable_bench_damage",
    "theirs.bench.hp_remaining",
})

LEAF_PROFILE = (PER_DECISION_PROFILE | ATTACH_DECIDER_PROFILE | PROMOTE_DECIDER_PROFILE
                | DENY_SLOT_PROFILE | KO_LINE_PROFILE | STATE_VALUE_PROFILE)


class _Probe:
    """Captures the field set a call touches by handing every model build a shared probe.

    Restores the original **class-dict entry** (the `classmethod` descriptor), not the bound callable
    that attribute access yields — assigning the latter back would leave `StateModel.build` globally
    rebound for every test that runs afterwards, which is test pollution regardless of whether it
    changes an answer.
    """

    def __init__(self):
        self.fields: set = set()

    def __enter__(self):
        self._descriptor = StateModel.__dict__["build"]     # the classmethod itself
        probe, orig = self.fields, StateModel.build         # orig: bound, for delegation

        def build(obs, **kw):
            kw["probe"] = probe
            return orig(obs, **kw)

        StateModel.build = staticmethod(build)
        return self

    def __exit__(self, *exc):
        StateModel.build = self._descriptor                 # exact original semantics restored
        return False

    def split(self) -> dict:
        """The per-side breakdown — the falsifiable half of the sharing rationale."""
        return {
            "mine": {f for f in self.fields if f.startswith("mine")},
            "theirs": {f for f in self.fields if f.startswith("theirs")},
            "cross": {f for f in self.fields if f.startswith("model")},
        }


def _frames(n=8):
    files = sorted((REPO / "tests" / "fixtures" / "corrections").glob("dp_*.json"))[:n]
    return [json.loads(f.read_text(encoding="utf-8"))["obs"] for f in files]


#: Committed mega_starmie frames whose menu DOES offer an energy attach — the attach decider's
#: profile is meaningless on a menu it stays silent on.
_ATTACH_FRAMES = (("82523811", 59), ("83664340", 45), ("82750161", 59))


def _attach_frames():
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-0089).

    `corpus_record` raises on a missing frame, which is what the old `len(out) == len(wanted)` guard
    was for — and it names WHICH frame, where the count could only say one went missing. The raw walk
    also appended per matching line, so a duplicated frame would have inflated the count into a
    silent pass; `load_corrections` dedups."""
    from corpus_helpers import corpus_records
    return [c.obs for c in corpus_records(_ATTACH_FRAMES)]


@pytest.fixture(scope="module")
def pilot():
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot("dragapult_ex")[0]


def test_the_per_decision_build_profile_is_pinned(pilot):
    """The field set a live decision's Board build touches. A migration that drags in a new field —
    especially one of the expensive clusters — moves this and must be measured, not merged."""
    with _Probe() as probe:
        for obs in _frames():
            pilot._board(obs, obs.get("select"), carried=pilot.carried())
    assert probe.fields == PER_DECISION_PROFILE, (
        "the per-decision field set moved — re-measure the cost per side before re-pinning\n"
        f"  added:   {sorted(probe.fields - PER_DECISION_PROFILE)}\n"
        f"  removed: {sorted(PER_DECISION_PROFILE - probe.fields)}")


def test_the_per_decision_profile_touches_both_sides_and_the_cross_side_read(pilot):
    """Reported per side, so the "expensive clusters sit on opposite sides" claim stays checkable."""
    with _Probe() as probe:
        for obs in _frames():
            pilot._board(obs, obs.get("select"), carried=pilot.carried())
    split = probe.split()
    assert split["mine"] and split["theirs"] and split["cross"]


def test_construction_itself_touches_nothing(pilot):
    """The premise under every cost claim here: building the model computes no field, so a consumer
    pays for reads alone. Measured at ~0.004 ms against a ~0.95 ms whole-Board build."""
    with _Probe() as probe:
        for obs in _frames():
            StateModel.build(obs, combat=pilot.combat, deck=pilot.deck)
    assert probe.fields == set()


def test_the_attach_decider_profile_is_pinned(pilot):
    """The attach decider's model reads, pinned on a menu that actually offers an energy attach. Same
    tripwire as the per-decision pin: if the decider starts reading the Needs assignment or a clock
    curve, this moves and the per-leaf cost needs re-measuring before it merges."""
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    ms = _build_pilot("mega_starmie")[0]
    with _Probe() as probe:
        for obs in _attach_frames():
            ms.explain(obs)
    added = probe.fields - PER_DECISION_PROFILE
    expected = ATTACH_DECIDER_PROFILE | PROMOTE_DECIDER_PROFILE   # not DENY_SLOT — see its comment
    assert added == expected, (
        "the decider field set moved — re-measure before re-pinning\n"
        f"  added:   {sorted(added - expected)}\n"
        f"  removed: {sorted(expected - added)}")
    # The tripwire's real claim, kept intact: the ATTACH decider must not reach an expensive cluster
    # it has no term for. The promote/retreat decider's own reads are netted out because it DOES have
    # a term for the clock (ADR-0100 §6's `tempo_denied`) — these frames are open turn menus, where
    # it legitimately prices the retreat option alongside the attach. Since POC-T1 the curve is also
    # in the per-decision set (the folded doom read), so `added` no longer carries it either way; the
    # claim is asserted against the union so it keeps biting if that ever reverses.
    attach_only = added - PROMOTE_DECIDER_PROFILE - DENY_SLOT_PROFILE - PER_DECISION_PROFILE
    assert not any("incoming" in f or "needs" in f for f in attach_only), (
        "the attach decider reached an expensive cluster it has no term for")


def test_an_unread_expensive_cluster_costs_nothing(pilot):
    """Laziness where it matters: reading a cheap my-side field must not drag in their clock curves
    or the deck-count derivation. This is what makes "maximal model, nothing speculative" coherent —
    an offered-but-unread field is free."""
    with _Probe() as probe:
        for obs in _frames():
            StateModel.build(obs, combat=pilot.combat, deck=pilot.deck).mine.prizes_remaining
    assert probe.fields == {"mine.prizes_remaining"}
    assert not any("incoming" in f or "deck_energy" in f for f in probe.fields)

# NB: the two ENGINE-DRIVEN halves of this pin live in `test_planner_engine.py`, not here.
# `test_leaf_profile` collects immediately before `test_lethal_helpers` / `test_lethal_recover`, and
# `ml_lethal_retreat_boost_to_ko_f24` is documented in `planner._develop_rollout_line` as depending on
# "the process's RNG position — the CI heisenbug". Starting a native battle ahead of those pins shifts
# that position and fires the heisenbug (it did, in CI). `test_planner_engine` already drives battles
# AND sorts after the lethal pins, so the engine halves belong there. Everything above is engine-free
# by design — keep it that way.
