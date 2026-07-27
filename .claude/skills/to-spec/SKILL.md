---
name: to-spec
description: Turn the current conversation into a spec and publish it to the project issue tracker — no interview, just synthesis of what you've already discussed.
disable-model-invocation: true
---

This skill takes the current conversation context and codebase understanding and produces a spec (you may know this document as a PRD). Do NOT interview the user — just synthesize what you already know.

The issue tracker and triage label vocabulary should have been provided to you — run `/setup-matt-pocock-skills` if not.

## Process

1. Explore the repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary vocabulary throughout the spec, and respect any ADRs in the area you're touching.

2. Sketch out the seams at which you're going to test the feature. Existing seams should be preferred to new ones. Use the highest seam possible. If new seams are needed, propose them at the highest point you can. The fewer seams across the codebase, the better - the ideal number is one.

Check with the user that these seams match their expectations.

3. Write the spec using the template below.

4. **Publish it to the issue — automatically, in the same turn you finish writing it.** See "Publishing" below. The spec is not "done" when it appears in chat; it is done when it is on the issue.

## Publishing (automatic — do not ask first)

The moment the spec is written, publish it. Do **not** print the spec and stop, do **not** ask "shall I post this?", and do **not** wait for approval — publishing is part of producing the spec, and the originating issue is the single unit of progress-tracking for this repo (see `docs/agents/issue-tracker.md`). The only thing you check with the user is the seams (step 2), before the spec exists.

All GitHub operations go through the GitHub MCP tools (`mcp__github__*`) with `owner: "richard-jh-mccrae"`, `repo: "PokemonAI"` — load each schema with ToolSearch (`select:mcp__github__issue_read,mcp__github__add_issue_comment,mcp__github__issue_write,mcp__github__list_issues`) before first use.

1. **Find the originating issue** — the one you were grilling. In order: an issue number named in this conversation; an issue number in the branch name; otherwise `list_issues` with `labels: ["status:2-spec"]` and pick the one whose subject matches this work. If exactly one candidate fits, use it without asking. If several plausibly fit, ask which — that is the one question worth stopping for.

2. **Post the spec verbatim** with `add_issue_comment` (`issue_number`, `body` = the full spec, every section, no summarizing or trimming). Post as a comment rather than opening a second issue. A GitHub comment caps at 65 536 characters; if the spec exceeds that, split it across sequential comments at section boundaries, each headed `Spec (part N/M)`.

3. **Advance the status chip** from `status:2-spec` to `status:3-build` with `issue_write` (`method: "update"`). `labels` **replaces** the set, so read the current labels first (`issue_read`, `method: "get_labels"`) and send back every non-status label plus `status:3-build`. No other triage.

4. **Report the result** — link the comment URL returned by the API, so the user can see where the spec landed. If any step fails (missing label, permissions, API error), say so plainly with the error and leave the spec in chat as the fallback; never claim it was published when it wasn't.

If there is genuinely no originating issue, create one with `issue_write` (`method: "create"`), the spec as the body, labelled `status:3-build`.

## Spec template

<spec-template>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A LONG, numbered list of user stories. Each user story should be in the format of:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

This list of user stories should be extremely extensive and cover all aspects of the feature.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets. They may end up being outdated very quickly.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision and note briefly that it came from a prototype. Trim to the decision-rich parts — not a working demo, just the important bits.

## Testing Decisions

A list of testing decisions that were made. Include:

- A description of what makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- Prior art for the tests (i.e. similar types of tests in the codebase)

## Out of Scope

A description of the things that are out of scope for this spec.

## Further Notes

Any further notes about the feature.

</spec-template>
