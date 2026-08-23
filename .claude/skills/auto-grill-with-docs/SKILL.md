---
name: auto-grill-with-docs
description: Repository-grounded design discovery with automatic recommendations and one approval.
disable-model-invocation: true
---

# Auto Grill With Docs

Reach a complete, evidence-backed design before specification without asking the developer to
approve each resolvable decision. Use `/domain-modeling` for approved terminology and ADRs. Route
ordinary chat prose through `/caveman`.

## 1. Establish evidence

Read the originating issue, relevant code, tests, `CONTEXT-MAP.md`, applicable `CONTEXT.md` files,
and ADRs. Resolve repository facts from their source; apply `/code-as-docs`'s authority order when
sources disagree. Do not ask the developer to recall them.

Find the originating issue in this order: issue number in the invocation or conversation, branch
name, then a uniquely matching workflow-status issue. If status, temporary ADR naming, or handoff
needs an issue and none can be resolved, hard stop.

Completion: every material claim has repository evidence, or the missing evidence is a hard stop.

## 2. Discover and order decisions

Inspect every applicable dimension: ownership and source of truth; interfaces and seams; domain
terminology; identity and losslessness; schema and versioning; failure and fallback semantics;
hidden-information boundaries; determinism and reproducibility; performance budgets; concurrency
and lifecycle; migration and compatibility; observability; testing; documentation and ADR impact;
and scope and rollout. Mark inapplicable dimensions internally.

Classify each material result as `FACT`, `DICTATED`, `CLEAR_WINNER`, `DEFAULTED_TRADEOFF`, or
`HARD_STOP`. `FACT` is evidence only. `DICTATED` follows an authoritative requirement or existing
convention. `CLEAR_WINNER` dominates realistic alternatives. `DEFAULTED_TRADEOFF` has a clear best
option without unknown product intent. A `HARD_STOP` needs the developer.

Rank alternatives: correctness and robustness; architectural soundness and modularity;
verifiability; completeness; performance. State the cost of the winner. A small diff, low blast
radius, or postponed refactor never improves its rank.

Order decisions by dependency. Recalculate each downstream decision when an upstream decision
changes.

Completion: every applicable dimension is classified and every material decision has alternatives,
evidence, dependencies, domain impact, and a highest behavioral testing seam.

## 3. Hard stops

Hard stop only for unknowable product intent, no defensible winner, equally authoritative decision
sources that materially conflict, a changed product outcome, an unclear public or persistent
compatibility promise, an unresolved required issue, missing required evidence, or a developer
request for interactive handling.

Ask one hard-stop question at a time using `/grill-with-docs`'s question format. After the answer,
update the inventory and dependent decisions, then resume discovery.

Completion: no hard stop remains unresolved.

## 4. Consolidated review

Present one review in dependency order. Give each material decision a stable `AG-01`, `AG-02`, … ID.
For durable ownership, schema, migration, or hidden-information decisions, use a full block:

```markdown
### AG-01 — <title>

**Decision:** <recommended option>
**Classification:** DICTATED | CLEAR_WINNER | DEFAULTED_TRADEOFF
**Alternatives considered:** <realistic alternatives>
**Why:** <ranking-based reasoning>
**Cost accepted:** <cost>
**Repository evidence:** <paths, ADRs, issue sections>
**Dependencies:** <IDs or none>
**Domain-doc impact:** <none, glossary term, or ADR>
**Testing seam:** <highest behavioral seam>
```

The review includes: recommended architecture; all auto-decisions; resolved hard stops; proposed
glossary changes; proposed temporary ADRs; testing seams; explicit out of scope; and risks and
limitations. Compact low-impact decisions only after all fields remain visible.

Before approval, do not mutate `CONTEXT.md`, ADRs, issue labels, or issue comments. If the developer
changes an ID, show only recalculated decisions and consequences, then request approval again.

End exactly with:

```text
Reply `approve` to accept all recommended decisions and testing seams and continue to `/to-spec`, or name any decision ID to change.
```

Wait for approval.

Completion: the developer explicitly approves the current review.

## 5. Apply the approved design

Update the mapped `CONTEXT.md` only for approved domain terms; keep entries free of implementation
detail. Create an ADR only for a hard-to-reverse, surprising decision selected after a real trade-off.
Use `docs/adr/temp-issue<N>-<slug>.md` and `ADR-TEMP-<N>`; leave `docs/adr/README.md` unchanged.

If the issue is `status:1-grilling`, replace only that label with `status:2-spec`. Preserve every
non-status label. Leave `status:2-spec` unchanged. Never advance to `status:3-build`.

After documentation and status updates, state that decisions and testing seams are approved, then
invoke `/to-spec` with the full inventory. Do not make it rediscover or change approved decisions.
If the developer requested no `/to-spec`, stop after documentation and status handling.

If evidence reads, documentation writes, issue updates, or `/to-spec` fail, state the exact failed
step. Do not claim it completed or advance a dependent workflow step.

Completion: approved documentation and status changes succeed, and `/to-spec` is invoked unless
explicitly declined.
