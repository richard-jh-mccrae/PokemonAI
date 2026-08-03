---
name: issue-sequence
description: "Implement a given list of already-specced GitHub issues, in a given order, on one shared branch/PR — one issue at a time, each in a fresh subagent, with autonomous scope-creep triage (auto-expand small growth, spin off and re-queue a new issue for large growth or a discovered blocker). Use when the user wants to run/batch/queue a specific ordered list of issue numbers, e.g. \"/issue-sequence 281,280,282\" or \"implement 281 then 280 then 282 as one PR\"."
disable-model-invocation: true
---

Implement the ordered list of issue numbers the user gave you, on `richard-jh-mccrae/PokemonAI`, as
one continuous batch: one branch, one PR, issues landed serially in the given order. This skill does
not decide the order — the caller already did (dependency chains, "largest first", file contention
between two issues, whatever). Never re-sort what you were given.

Because this can run for hours across many issues, you (the invoking session) are the **orchestrator**
only. You do not write any code yourself. Every issue is executed by a fresh subagent so its internal
work never bloats your context — there is no tool that lets you invoke `/compact` on demand, so
subagent isolation is the substitute: you keep only each subagent's final report, not its transcript.

## Step 1 — Resolve the queue

Parse the issue numbers from the argument (comma- or space-separated). For each, in the given order:

```
gh issue view <N> --repo richard-jh-mccrae/PokemonAI --json number,title,state,labels,body
```

- If it's closed already, or missing a build-ready status chip (`status:3-build` or equivalent —
  see `docs/agents/issue-tracker.md`), stop and tell the user rather than guessing whether to skip
  or grill/spec it first.
- Look for a shared parent epic (an issue whose sub-issues cover most/all of the queue — check the
  `parent`/`sub-issues` fields `gh issue view` surfaces, or cross-references in the bodies). If found,
  keep its number and its "standing discipline" section handy — you'll paste that into every
  per-issue subagent prompt alongside the sub-issue's own body, the same way a parent issue's shared
  rules apply to each of its children.

This queue is **live state you hold in your own context**, not something the Task tool tracks
authoritatively — it will very likely be mutated mid-run (Step 5). Mirror it into `TaskCreate` /
`TaskUpdate` (one task per queued issue, `metadata: {issue: N}`) purely so the user has visibility;
your own ordered list is the thing you actually iterate.

## Step 2 — One branch, created once

If you're resuming an interrupted run (a branch matching `claude/issue-<first>-sequence*` already
has commits referencing these issues), reuse it and skip straight to whichever queued issue isn't
closed/committed yet. Otherwise, fetch and branch fresh off latest `main`:

```
git fetch origin main
git checkout -b claude/issue-<first-issue-number>-sequence origin/main
```

## Step 3 — Per-issue execution

For each item in the queue, in order:

1. Spawn one `Agent` call, `general-purpose`, **`run_in_background: false`** — you need its result
   before deciding what runs next, and foreground is how you catch a mid-run developer question
   instead of it sitting silently in a completed background result.
2. Give it a fully self-contained prompt (it has no memory of this conversation). Include:
   - The repo path and branch name — already checked out, tell it not to create or switch branches.
   - **Pre-work rebase** (every issue except the very first item in the queue — that branch was just
     created fresh off `main` in Step 2, so there is nothing to rebase yet): before touching any code
     or fetching the issue body, run `git fetch origin main && git rebase origin/main`. This is the
     subagent's literal first action — it runs because the *previous* queued issue just finished
     cleanly (full local test suite passing is part of what `/implement`'s report-back already
     gates on in Step 3.3, so reaching this subagent at all means that condition held). If the
     rebase reports conflicts, resolve them immediately, before reading the issue body or writing any
     issue code — a conflict is this subagent's first problem to solve, not something to defer. Prefer
     the textually obvious resolution (e.g. both sides added independent lines/files); if a conflict is
     semantic — two sides changed the same logic and picking one silently drops behavior — treat it as
     an ambiguity stop-and-ask (below) rather than guessing. Only once the rebase is clean does the
     subagent move on to fetching the issue and building it. Note this in the final report even when
     there was nothing to resolve (`rebase: clean, no conflicts` / `rebase: resolved N conflicts in
     <files>` / `rebase: NEEDS DEVELOPER INPUT, see below`).
   - Its issue number, and to fetch the full body + comments itself
     (`gh issue view <N> --repo richard-jh-mccrae/PokemonAI --comments`).
   - The parent epic's standing-discipline section, if you found one in Step 1, pasted verbatim —
     don't make the subagent re-fetch and re-derive it.
   - **The build instruction**: invoke the `implement` skill (`Skill` tool) to actually do the work.
     It already runs premise-check → TDD → full test suite → `/code-review` → commit → issue-status
     advance. You are overriding only its PR and gate behavior (below) — everything else in
     `/implement` stands.
   - **PR discipline** (Step 4).
   - **Gate discipline** (Step 5 — for this repo specifically, since it's a standing project rule,
     not something tied to any one issue: `data/leaf_lab/baseline.json` and
     `data/decider_lab/baseline.json`, when they exist, are never re-captured without a developer
     verdict).
   - **Scope-creep triage** (Step 6) — paste the full decision procedure, don't summarize it. This is
     the part most likely to be shortcut under time pressure, and it's the part that most needs to
     survive verbatim.
   - **Ambiguity stop-and-ask**: reuse `/implement`'s own step-0 format (plain text, recommended
     option first, both plain-English and technical explanation for each option). If it fires, that
     question must be the first line of the subagent's final report, marked
     `NEEDS DEVELOPER INPUT:` — you cannot answer on the developer's behalf.
   - What its **final report** must cover: pre-work rebase result (per above), files/functions
     touched, suite result, gate-diff result (clean, or N flips packeted — name the file), PR state,
     issue-tracker status, and — always, explicitly, even when the answer is "no" — whether it
     triaged any scope creep this run.
3. Read the report.
   - **Developer question present** → relay it verbatim to the user in chat. Wait for the actual
     answer (do not answer on their behalf, do not proceed past it). Once you have it, `SendMessage`
     addressed to that subagent (by name/ID) with the answer — this **resumes** it with full context
     of what it had already done; it does not restart. Only after it reports back clean do you move
     to the next queued item.
   - **New issue filed (Tier 2 triage fired)** → insert it into your in-context queue at the reported
     position, add a `TaskCreate` entry for it, and tell the user inline, plainly — e.g. "Issue #281
     turned up a blocker for #286; filed Issue #NNN and queued it immediately before #286." No
     permission needed to proceed; visibility is not optional.
   - **Clean** → mark that queue item done, move to the next.

## Step 4 — PR discipline

- **First item that actually lands a commit**: invoke `/open-pr` to create the PR. Title states the
  shared parent epic if you found one in Step 1 (`Issue #<parent>: <short description>`), otherwise
  the first issue number; body lists every issue number in the queue as it stood at PR-creation time.
  **Do not arm the 5-minute CI check-in / auto-fix loop yet** — local pytest and local gate diffs are
  this run's authority, not GitHub CI, and the next queued issue must never wait on a CI run.
- **Every other item** (including ones inserted mid-run by Tier-2 triage, and a blocked issue's
  second pass after its prerequisite lands): commit, then plain `git push` — no ADR finalization, no
  CI wait. This item's subagent already rebased onto `main` as its first action (Step 3's pre-work
  rebase) before it wrote any code, so there is nothing left to reconcile at push time; a second
  rebase immediately before pushing would be redundant, not additive. Update the PR body's issue list
  if the queue changed.
- **Last item in the queue** — whatever it ends up being after any insertions — gets the full
  `/open-pr` ceremony: rebase onto `main`, finalize any temp-named ADRs, push, finalized PR body
  covering the whole batch. Only now is it fine to arm the CI check-in loop, since nothing downstream
  in this run is waiting on it.

## Step 5 — Gate discipline (skip entirely if this repo has no gate baselines)

If `data/leaf_lab/baseline.json` and/or `data/decider_lab/baseline.json` exist, run after every
issue's change:

```
python tools/train/leaf_lab.py diff --baseline data/leaf_lab/baseline.json
python tools/train/decider_lab.py diff --baseline data/decider_lab/baseline.json
```

On any unruled flip (leaf: `OK → MISS`; decider: `agree → disagree`): **never** run `capture` /
`restamp` to update the baseline — that needs a developer verdict the subagent doesn't have. Instead
append to a run-scoped packet file, `docs/plans/issue-sequence-<first-issue>-wave3-packet.md`
(create it on first flip), modeled on this repo's existing `data/leaf_lab/wave3-rulings.md`
convention but pre-ruling:

```markdown
# Wave-3 packet — issue-sequence run (<first-issue>, ...)

Gate flips from this batch, pending developer ruling. None conformed into either baseline.json —
a baseline is a ruling record, not something a sub-issue may recapture on its own recognizance.

## Flips

| frame | gate | issue | old | new | recommendation |
|---|---|---|---|---|---|
```

A flip is never a stop condition. Record it, keep going.

## Step 6 — Scope-creep triage

Hand this to every subagent verbatim. Apply it the moment creep is noticed — not retroactively at
the end of the issue.

**Tier 1 — moderate creep → auto-expand in place, no new issue.** All must hold:
- Stays inside the same file(s)/module the issue already touches, or an obviously-adjacent spot
  (a sibling function in the same file).
- No new architectural/design decision — no new ADR, no "pick between two approaches" call.
- Doesn't muddy what a resulting gate flip should be attributed to — still honestly describable as
  "fixing what this issue says," not a second independent fix riding along.
- Fits inside the same TDD cycle without materially changing the issue's size.

→ Just build it. State the expansion explicitly in the commit message and the final report:
`scope note: also fixed X because Y — still issue #N, not separable.`

**Tier 2 — large growth, or a discovered blocker (for this issue or a later queued one) → spin off
a new issue, do not build it inline.** Trips on any of:
- Needs its own design decision, or touches a subsystem/file this issue wasn't scoped for.
- Bundling it would make a gate flip's cause ambiguous — never let one commit answer for two
  independent causes.
- It's a genuine blocker: this issue's fix is wrong/incomplete without it, or a **later** queued
  issue rests on a premise this work just falsified, or is missing a prerequisite because of it.

When Tier 2 trips:
1. Write a full spec for the new issue at the same bar as the issues already in this queue: problem
   statement, why it matters, the central factual claim that must hold, acceptance criteria,
   dependencies, verify-at-source pointers. Match the sibling issues' structure if there's a shared
   parent epic; otherwise follow `docs/agents/issue-tracker.md`.
2. File it: `gh issue create --repo richard-jh-mccrae/PokemonAI` with label `status:3-build` — it
   arrives pre-specced and ready to build, so it skips the grilling/spec-draft chips.
3. Decide placement:
   - **Blocks a specific later queued issue, not this one** → insert immediately before that issue.
   - **Blocks this issue itself** (can't be finished correctly without it) → don't force a half-fix
     through. Commit only what this issue can honestly claim without the prerequisite, say so plainly
     in the final report, and insert the new issue immediately next — followed by **this issue again**
     so it can be finished once the prerequisite lands.
   - **Otherwise** (a general follow-on nothing downstream depends on yet) → insert immediately after
     this issue.
4. Report the new issue's number, one-line spec summary, and chosen position in the final report, so
   the orchestrator can update the live queue.

Never build a Tier-2 issue inline "while you're already in there" — that is exactly the bundling
this batch's serial-landing discipline exists to prevent, and it is what makes a later gate flip
unattributable.

## Step 7 — Closeout

Once the queue is empty — including anything inserted along the way — run the final `/open-pr` pass
(Step 4's last-item case). If a wave-3 packet file exists, present it to the user for ruling; do not
act on its contents yourself.
