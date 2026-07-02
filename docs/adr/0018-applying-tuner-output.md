# ADR-0018: Applying Tuner output — weights auto-load; Hypotheses are LLM-authored behind a Verifier

**Context.** The **Tuner** ([ADR-0017](0017-corrections-compile-to-hypotheses.md)) emits two
things: `tuned.json` (weight overrides) and `missing_hypothesis` **proposals**. This fixes *how*
each becomes a shipped agent improvement — "consistent and accurate." Authoring executable agent
rules from prose is the risky part; marking blunders is expensive, so each must yield maximum,
trustworthy improvement.

**Decision.**

- **Weights apply deterministically — no LLM.** `main.py` loads `tuned.json` as the Pilot's
  `overrides` (mirroring `deck.csv` path resolution); `package_agent` ships it in the Bundle;
  `Pilot._weight(h)` resolves every weight as `overrides.get(h.id, h.weight)` (an unmatched id is
  silently ignored → a no-op). To keep "actually used" verifiable, `tuned.json` is written
  **sparse** — only weights that differ from the authored seed (`tuner.io.sparse_overrides`), so the
  file *is* exactly the deltas that take effect (an empty `{}` means no weight-route corrections
  yet; all leverage is in the proposals). `tune.py` prints the per-id `seed -> new` diff, and
  `tests/agents/test_tuned_wiring.py` asserts every shipped key is a real Hypothesis id.
- **Hypotheses are a hybrid, gated by a deterministic Verifier.** Claude authors the `when()`
  predicate from the Correction **rationale** (the *authoring spec*, not a footnote) + the live
  feature catalog; the **Verifier** accepts it only if, after re-fitting weights over all
  Corrections, it satisfies its target cluster, regresses none previously satisfied, and keeps the
  suite green; the human commits the diff. **No auto-commit of executable code.** *Accuracy comes
  from the Verifier (deterministic, derived from the Corrections), not from who authors.*
- **Proposals are durable, not stdout-only.** `tune.py` writes a committed per-deck snapshot
  `data/proposals/<deck>.json` (`open[]` = `missing_hypothesis` proposals, each carrying
  category/episode/frame + `agent_build`/`built_at`; `skipped[]` = tactical/no-obs). The
  `/blunder-buster` skill reads it instead of re-parsing console text, and its `git` history is a
  per-build timeline of how the agent's open blunders shrink as Hypotheses are authored.
- **Author per cluster.** One Hypothesis per pattern of related Corrections, verified against all
  members — far more robust and higher-leverage than per-correction point-fixes.
- **Invocation: an interactive `/blunder-buster` skill** (Claude session + Verifier). Authoring
  is low-volume and high-stakes (ships executable code), so full context + iteration + human review
  beat headless automation. A programmatic API tool is **deferred** — it bolts onto the same
  Verifier + catalog later.
- **Placement:** universal-feature triggers (`tags`/`roles`/`board`/`stat`) → `general_strategy.py`;
  deck-specific (deck `roles`/`lines`/`card_id`s) → `agents/<deck>/strategy.py`.
- **Status lifecycle:** `assumed` (authored) → `testing` (Verifier passed, committed) →
  `confirmed`/`refuted` (human, after ladder A/B — the documented experiment trail, ADR-0009).

**Considered / rejected.** Pure-Python authoring (can only template point-fixes by `card_id`; can't
generalize a prose rationale). Pure-LLM authoring (no deterministic accuracy gate). A headless API
tool now (generates executable agent code unattended; low volume doesn't justify the risk).

**Consequences.** The inspector's rationale field gets a gentle prompt eliciting the *general rule*
(free prose, no new fields), since capture-time context is freshest. The loop closes end-to-end:
tag → tune → (weights auto-apply) / (author + verify + commit) → ladder. The Verifier (`tools/train/`)
is the reusable trust anchor for both the interactive skill and the future API tool.
