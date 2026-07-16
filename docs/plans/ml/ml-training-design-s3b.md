# Build Session 3b Design — Expert-Iteration Targets, Loss & Matchup Weight Tables (LOCKED)

**Status:** design locked 2026-07-13 (Fable 5 design grill; user-approved forks). The Build Session 3b
sessions **execute** this — deviations get recorded here with a reason. Depends on the Value-Net Gate (a
validated value net); plumbing may start earlier against the committed seed model.

**Grounding (verified at design time):**
- Apprentice = the linear layer: `score = Σ w·fired + tactical` (`src/common/pilot.py:1117`);
  per-option `OptionTrace.fired` via `pilot.explain(obs)` (`tools/train/tuner/featurize.py`).
- Weight resolution chain: `tuned.json` override > `Strategy.weight_overrides` > authored
  weight (`pilot.py:1122` `_weight`) — **no matchup axis exists today**.
- Proven fitter: soft-margin structured perceptron with pocket, L2-pull-to-seed, ±100 band
  clamp (`tools/train/tuner/fit.py` — `ranking_constraint`, `fit_weights`).
- Every recorded step obs carries `search_begin_input` (opaque engine fork string); self-play
  logs know BOTH sides, so `cg.api.search_begin(obs, your_deck, your_prize, opponent_deck,
  opponent_prize, opponent_hand, opponent_active)` is fully specifiable offline.
- Read/γ replayable offline via `pilot._board` (same fact Build Session 2a relies on).

## D1 — The expert: one-step value lookahead over the real option menu

Expert config = the shipped Pilot with all sound tiers ON plus the **Value-Net-Gate-passed value net**.
For a sampled decision frame, the expert scores each legal option `i`:

1. Fork the engine from the frame (`search_begin` with the replay's known both-sides state).
2. `search_step(option_i)` → resulting obs′.
3. `V_i` = value-net P(win) on `board(obs′)` — with a **terminal override**: engine says the
   line wins → 1.0, loses → 0.0, draws → 0.5 (sound results outrank the net, same invariant
   as the planner's rungs).

Expert preference = descending `V_i`; per-option margins `ΔV` are retained. Mid-turn options
evaluate on the same-seat obs′; turn-enders on the end-of-turn state — consistent because
features are seat-relative to my obs. Stochastic effects (coin attacks): v1 accepts one
engine sample; the θ threshold below absorbs the noise (expectimax over outcomes = v2).

**v1 scope:** single-pick contexts only (MAIN + single selects). Multi-pick (discard-2,
multi-grab) deferred — the set-difference diff exists in `featurize.py` but expert
enumeration over subsets doesn't; don't fake it.

**Frame sampling** (forks are the cost driver): (1) ambiguity filter first — frames where the
apprentice's top-2 score gap is below a margin (no fork needed to detect); (2) uniform random
residual for coverage; stratified per agent and per decision context. Sample budget is a CLI
parameter; record it in the run manifest.

## D2 — Targets & loss: disagreement constraints through the existing fitter (user-locked)

Where `V(expert_best) − V(apprentice_choice) ≥ θ`, emit a **machine Correction** (Work Package 3's C2
provenance tag; `chosen`=[apprentice pick], `correct`=[expert best], rationale auto-generated
with ΔV, obs embedded) → `featurize` → `ranking_constraint` → `fit_weights` **unchanged**
(pocket, L2-to-seed, band clamp, reviewed.json flow all reused).

This deliberately unifies Work Package 3 and Work Package 4: the blunder labeler IS the disagreement detector; Build Session 3b
adds the fit extensions, not a second pipeline. θ is tuned by Build Session 3a's human precision review
(sample flagged disagreements, measure precision, set θ before mass production).

**Outer loop:** fit → replay apprentice over the sampled frames → re-detect disagreements →
refit. v1 runs ≤ 2 rounds; record the disagreement rate per round (the convergence metric).
The expert is FIXED within a round; the value net only retrains in the outer rotation loop
(Work Package 6).

**v2 escalation (explicit, not v1):** soft cross-entropy over softmax of option scores toward
the expert's value distribution (torch SGD) — only if constraint-based fitting saturates
(disagreement rate plateaus above target with constraints exhausted).

## D3 — Matchup-conditioned weight tables (the learned Brief counterpart)

**Semantics:** `effective(h) = base(h) + γ · delta[arch★][h.id]`, where `base` is today's
resolution chain untouched, `arch★` = the Read's top candidate, γ = posture confidence.
γ-scaling makes it fail-open: unrecognized opponent ⇒ exactly today's behavior.

**Artifact:** `src/agents/<agent>/tuned.matchups.json` — `{archetype: {hyp_id: delta}}` +
meta (provenance like `tuned.meta.json`). Loaded via a new Pilot ctor arg alongside
`overrides`; kill-switch param `matchup_weights`, **default OFF until the Adoption Gate flips it**.

**Runtime:** at `decide()`/`explain()` entry, after `_board`: cache
`(γ, deltas-for-top-arch)` iff `γ ≥ γ_min`, else empty; `_weight(h)` adds
`γ · deltas.get(h.id, 0.0)` to the resolved base. One dict lookup per fired Hypothesis —
negligible cost.

**Training partition:** a frame trains `delta[A]` iff its **replayed Read** has `γ ≥ γ_min`
and top candidate = A; otherwise it trains the base fit. Same γ-gate at train and runtime
(no skew). Default `γ_min = 0.35` — tune in-session, but train/runtime must share the value
(ship it inside `tuned.matchups.json` meta).

**Delta fit:** reuse `fit_weights` per archetype partition with `seeds = fitted base`
(so the pull-to-seed regularizes the DELTA toward 0); `reg = 2×DEFAULT_REG` (deltas earn
their move), then `delta = result − base` clamped to **±30** — a matchup table sharpens
doctrine, it never inverts it (authored weights live at the ±100 scale).

## D4 — Adoption Gate & neutrality

- The Adoption Gate as defined in the playbook: paired matchup×seat-balanced win-delta on the Work Package 2 harness,
  checkpoint pool included; ladder stays final arbiter.
- **Neutrality invariant:** with `matchup_weights` ON but `γ < γ_min` (or no Read), decisions
  must be bit-identical to OFF — verified with `tools/sim/score_diff.py` over a γ=0 obs
  corpus before any A/B.
- Base-fit regression: after expert-iteration refit, the existing correction corpus's
  satisfied-rate (`satisfied_after_fit`) must not drop vs the pre-fit ledger — machine
  constraints must not bulldoze human-reviewed ones (they share one fit; refuted/reviewed
  exclusions apply to machine corrections identically).

## Non-goals (v2 backlog, with triggers)

- Compound-feature construction (Soemers co-active pairs correlating with apprentice-vs-expert
  error) — trigger: disagreement rate plateaus with existing Hypothesis vocabulary exhausted.
- Soft cross-entropy loss (see D2), multi-pick selects, expectimax over coin outcomes,
  multi-turn expert rollouts, per-archetype expert configs.
- Touching `tactical` — the combat term stays a fixed bias in constraints (as today), never a
  fitted quantity.
