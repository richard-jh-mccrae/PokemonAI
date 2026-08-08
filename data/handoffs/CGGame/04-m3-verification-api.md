# M3 — verification API + `CG_ENGINE=py` selection ✅ DONE (2026-07-11)

**Goal:** cgpy becomes (a) a drop-in engine for the existing harness with agents unchanged,
and (b) the fixture-seedable, clonable oracle that unblocks the deferred multi-step lethal
verification tool.

## Outcome (all gates green)

- **Built:** `src/cgpy/search.py` (structured seeding: MAIN, unambiguous trainer mid-effect
  selects — the fetch-class fixtures — and any select via the cgpy state token; native-verbatim
  validation/errors; deterministic prediction reshuffle per pin §4; clone-per-step sessions with
  native error strings), `src/cgpy/game.py` + `compat/` + `alias.py` (the `cg` surface;
  `CG_ENGINE=py` at the four harness entry points, additive lines only), `Engine.fork()`,
  manual-coin as COIN_HEAD selects in `chain.py`, `visualize_data` god frames (CamelCase log
  names probed from trace god_logs). `GameState.clone()` stopped deep-copying the immutable
  CardDB (~15× faster forks).
- **Gate (a) drop-in:** `battle.py` under `CG_ENGINE=py` — 2+20 mirror + 20 ml-vs-dx games,
  agents unchanged, **zero crashes**, ~1.5 games/s (results were appended to `data/battles.jsonl`
  during the run and reverted — cgpy rows don't belong in the native ledger).
- **Gate (b) verdict agreement:** `tests/strategy/test_engine_agreement_engine.py` — on every
  draw-free seeded fixture the two engines agree (f110 **True on both** — the whole
  fetch→attach→retreat→promote→attack→win cascade; f26/f48/f24 refute on both). f15's recorded
  `correct` ([1] Lillie's) is draw-6-dependent (not prediction-invariant) — excluded there,
  pinned deterministically in `test_lethal_cgpy.py` via the Petrel line instead.
- **Gate (c) clone safety:** `tests/parity/test_clone_safety.py` — fork at EVERY select of every
  committed trace, fork and original replay identically (29/29 traces).
- **Item 5 (lethal tool on cgpy):** `tests/lethal_helpers.py::engine_confirms_py` (DLL-free, and
  **no `search_begin_input` needed** — proven by stripping f110's blob → still True);
  `lethal_probe.py --engine py`; `tests/strategy/test_lethal_cgpy.py` hand-drives the two
  deferred retreat-to-promote WIN lines (f15 Petrel→Air Balloon→retreat→promote→Aura Jab; f24
  attach→PPP×2→retreat→promote→Cosmic Beam) to the engine's win verdict by card identity — the
  committed Phase-3 ground truth. Tests: `tests/parity/test_search_api.py`,
  `test_compat_game.py`, `test_clone_safety.py`.

**Deliberately out of scope (raise, never guess):** token-less seeding of ability/attack-rider
mid-effect selects, multi-pose op programs (Hilda/Crispin sequences), LOOKING states, setup-phase
selects with a facedown own active. The planner catches the ValueError → verdict None (sound).

## Build items

1. **`src/cgpy/search.py`**
   - `state_from_obs(obs_dict, your_deck, your_prize, opp_deck, opp_prize, opp_hand,
     opp_active, manual_coin=False)` — SAME signature/validation/error messages as
     `cg.api.search_begin` (`src/cg/api.py:517`) minus the opaque blob: reconstruct hidden
     zones from the predictions (obs supplies everything visible; `select.deck` overrides
     `your_deck` when present; a facedown opp active requires `opp_active`). Apply cgpy's own
     deterministic shuffle to predicted zones (the native fork reshuffles too — pinned, M0).
   - `state_from_visualize(frame, decks)` — god-view seeding for differential/fixture use.
   - Search semantics: persistent `dict[searchId -> Engine]`, **clone-per-step** (that's why
     the native has SearchRelease), `search_end()` clears. `manual_coin=True` ⇒ every
     `coin()` poses a `COIN_HEAD` (ctx 46) YesNo instead of consuming RNG.
2. **`src/cgpy/compat/` + `alias.py`** — `cgpy.compat` mirrors the `cg` package surface
   (`api` re-exports schema enums/dataclasses + `all_card_data()`/`all_attack()` from CardDB +
   `to_observation_class` + `search_*`; `game` re-exports cgpy.game; `sim` exposes a dummy
   `lib_path="cgpy"`); `alias.install()` = `sys.modules["cg"] = cgpy.compat` (+ submodules);
   `install_if_enabled()` gates on env `CG_ENGINE=py`. Meta-path/sys.modules wins over the
   path-based import, so `src/cg/` stays untouched.
   - A `src/cgpy/game.py` module-level singleton mirroring `cg/game.py` exactly
     (`battle_start(deck0,deck1) -> (obs, StartData)` with an attribute-compatible StartData;
     `battle_select` raising the same exceptions; `visualize_data()` — string-enum god frames,
     +1 `selected` offset — needed for `--save-replays`-class consumers, can come last).
3. **Wire-up (additive lines only):** `pyengine…install_if_enabled()` calls at the top of
   `tools/sim/battle.py` main, `tools/sim/_agent_server.py`, `tools/sim/_battle_worker.py`,
   `tests/conftest.py`. `CG_ENGINE` unset ⇒ byte-identical behavior to today.
4. **Cross-checks (the M3 gate):**
   - `tools/sim/battle.py <agent> <agent> -n 20` runs end-to-end with `CG_ENGINE=py`, agents
     unchanged, zero crashes.
   - `_engine_confirms_win` verdict agreement: replay recorded planner calls through both
     engines (the planner drivers are `src/common/strategy/planner.py:529` `_engine_confirms_win`
     and `:1413` `_simulate_line`) — verdicts must agree wherever the outcome is
     prediction-invariant.
   - Clone-safety test: clone mid-cascade at every select of every fixture trace; both copies
     replay identically.
5. **Unblock the lethal tool:** implement the harness from
   [pokemonai-handoff-lethal-multistep-verification-tool.md](../../../docs/adr/0050-multi-step-lethal-verification-tool.md)
   on cgpy — seed from a captured correction fixture (structured state, NO
   `search_begin_input` needed), drive a whole candidate turn through `decide()` to a win
   verdict, dump each reached select's option encodings. First real targets: the two deferred
   retreat-to-promote maneuvers
   ([pokemonai-handoff-retreat-to-promote-maneuvers-grill.md](../../../docs/adr/0100-the-promote-retreat-equation-is-the-sub-lethal-residual-in-damage.md)).

## Cautions

- The planner treats an unresolved opponent select as REFUTE and an unaccounted coin as
  undetermined — the cgpy search must surface the same shapes (COIN_HEAD selects, opponent
  turns) so those soundness rules keep working.
- `search_begin_input` truthiness: consumers only check presence (planner bails when absent).
  cgpy obs carry a token (`"cgpy"`); `compat.api.search_begin` must accept an obs with the
  token and rebuild from structured state.
- Performance: pure-Python is slower than the DLL; battle.py throughput will drop — fine
  (verification is the point; native remains available for bulk self-play).
