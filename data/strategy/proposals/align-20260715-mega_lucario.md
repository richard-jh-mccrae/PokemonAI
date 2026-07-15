# deck-align hygiene batch — mega_lucario (2026-07-15)

> `/deck-align mega_lucario` pass against ledger `40b918d` (2026-07-03) → HEAD `748a3f3`. The
> fold/vocabulary/wiring axes came back **clean** (no folds: Heave-Ho trio KEEP, Lunar-Cycle rules KEEP,
> `dont-fund-the-non-attacking-body` fold intact, every Context/Board field + enum the deck reads still
> live). The only drift is **3 stale doc/comment truths** — all deck-strategy, score-diff-trivial, zero
> behavior change. Score-diff baseline for the pass: `data/score_diff/mega_lucario.base.json` (335 frames).
>
> Two OPEN tuner corrections (`missed-win-85785067-14`, `misattachment-85785606-1`) are **NOT** in this
> batch — they want a rule authored/tuned from replays, which is `/blunder-buster` territory, not an
> alignment fold.

## reactivity-solitaire-comment-now-wired
- id: ml-align-20260715-reactivity-comment
- source: deck-align
- target_layer: deck-strategy
- candidate_signal: params["reactivity"] (read at src/common/strategy/planner.py:860)
- verification_contract: score-diff
- provenance: src/agents/mega_lucario/strategy.py:368-371 (params block) ; consumer src/common/strategy/planner.py:836-863 (forgo-KO `deck-personality-reactivity` exemption, names mega_lucario)
- status: applied
- for: deck:mega_lucario

**Spec (authoring spec — thin fodder, not finished code):**
The `reactivity="solitaire"` param comment in `strategy.py` still reads *"Declared forward contract
(behavior-neutral) — deck-gating the opponent-filtered seams to a consumer is an A/B follow-up."* That is
now **stale**: the consumer exists and is wired. `planner.py` `_forgo_ko` (line 860) reads
`params.get("reactivity") == "solitaire"` to make a solitaire deck skip the develop/END over-reaction
lines and race its own plan (line-1 alternative-attack exemption keeps Aura Jab reachable) — the docstring
at planner.py:836-841 names mega_lucario explicitly (ml f88/f48). Rewrite the comment to state the param
is now consumed by the forgo-KO rung (still note that `forgo_ko` itself defaults OFF, so the rung is only
reached when that kill-switch is on). **Comment-only edit — no `when()`/weight/param-value change**, so
score-diff must be byte-identical over the baseline; it is a truth-fix, not behavior.

## shuffle-hand-tag-gap-now-satisfied
- id: ml-align-20260715-shuffle-hand-tags-done
- source: deck-align
- target_layer: deck-strategy
- candidate_signal: card_functions.json tags — Judge(1213) & Unfair Stamp(1080) now carry `shuffle_hand`
- verification_contract: score-diff
- provenance: src/agents/mega_lucario/STRATEGY.md §5 (line ~827 `attach-before-hand-shuffle` "Needs Judge tagged `discard_hand` (infra)") + §9 T9' (line ~1132 "Unfair Stamp `shuffle_hand` tag: ADD … pending the gate") ; current tags verified: card_functions.json 1213 & 1080 = ['draw','hand_disruption','shuffle_hand']
- status: applied
- for: deck:mega_lucario

**Spec (authoring spec — thin fodder, not finished code):**
Two STRATEGY.md rows flag the `shuffle_hand` tag as pending infra; both are now **satisfied** in
`card_functions.json` — Judge (1213) and Unfair Stamp (1080) each carry `['draw','hand_disruption',
'shuffle_hand']`. Update the doc so the truth is current:
- §5 disposition row for `attach-before-hand-shuffle` (−60): drop the "**Needs Judge tagged
  `discard_hand`** (infra)" caveat — Judge is tagged `shuffle_hand` (the vocabulary the guard actually
  reads; the old `discard_hand` name was superseded per §5b line 847), so the guard now sees both Lillie's
  and Judge. Mark it live/covered, not pending.
- §9 T9' bullet "Unfair Stamp `shuffle_hand` tag: ADD to card_functions.json (1080)": flip from a pending
  follow-up to **DONE** (1080 is tagged), so `hold-wincon-dont-shuffle` sees Unfair Stamp's shuffle.
Doc-only edit; no code touched → score-diff byte-identical over the baseline. (The separately-noted
Lunatone `draw` / Hariyama `gust` tag gaps in §8 stay OPEN and are intentionally left — §8 already
documents them as low-value, since even tagged, `dig-before-commit` won't fire on an ABILITY use.)

## main-py-wiring-row-now-runtime-shell
- id: ml-align-20260715-mainpy-runtime-row
- source: deck-align
- target_layer: deck-strategy
- candidate_signal: src/agents/mega_lucario/main.py (now `common.runtime.make_agent`, ADR-0055)
- verification_contract: score-diff
- provenance: src/agents/mega_lucario/STRATEGY.md §5b (line ~857 "main.py wiring | REFRESH | current contract: attack_stats + effects + Scout+artifact + briefs + posture + OwnCardModel…") ; current main.py = 5-line `make_agent(STRATEGY)` shell ; ADR-0055 (runtime owns the deployment profile)
- status: applied
- for: deck:mega_lucario

**Spec (authoring spec — thin fodder, not finished code):**
STRATEGY.md §5b's "main.py wiring | REFRESH" row (and any sibling §9/§5b prose citing the hand-wired
`main.py` contract "attack_stats + effects + Scout/artifact + briefs + posture + OwnCardModel/own_prizes;
import path `common.strategy.general_strategy`") describes the **pre-ADR-0055** hand-assembled shell. That
is stale: `main.py` is now the 5-line runtime shell (`from common.runtime import make_agent; agent =
make_agent(STRATEGY)`), and `runtime.py`'s PROFILE is the single source of the deployment profile /
knowledge seams / kill-switches (ADR-0055; the `new-deck-wiring-gap FIXED` finding — omitting a seam is now
structurally impossible, pinned both ways by a test). Update the row to note that the deployment wiring is
owned by `common.runtime` (PROFILE), not enumerated per-deck in main.py, and that each flag resolves as
`params.get(flag, PROFILE[flag])`. Doc-only edit; no code → score-diff byte-identical.
