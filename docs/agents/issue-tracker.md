# Issue tracker: GitHub (via the GitHub MCP server)

Issues and PRDs for this repo live as **GitHub issues** on `richard-jh-mccrae/PokemonAI`.

> **Environment note.** This repo is driven mostly from Claude Code on the web / mobile, where
> there is **no `gh` CLI** — all GitHub operations go through the **GitHub MCP tools**
> (`mcp__github__*`). Use those, not `gh`. (On a local machine that happens to have `gh`, the
> equivalent `gh issue …` commands work too, but the MCP tools are the portable path.)
>
> Every tool below takes `owner: "richard-jh-mccrae"`, `repo: "PokemonAI"`. Load a tool's schema
> with ToolSearch (`select:mcp__github__issue_write`, …) before first use in a session.

## ⚠️ Before filing: an issue that asserts a GAP must carry its PRIOR ART

**The most expensive issue in this repo is one that proposes building something that already
exists.** It has happened repeatedly. The worked example: a spec was written to add *"energy count +
type requirements"* labelling. Both were already shipped fields on `AttackStat`
(`src/common/scouting/provider.py`, ADR-0032):

```python
cost: int = 0            # energy count (efficiency tiebreaks, affordability)
energyTypes: tuple = ()  # the cost's per-slot Energy TYPE codes (EnergyType enum…)
```

**Why searching failed to prevent it, and why "search harder" is not the fix.** The agent searched
for the name it had just invented — *energy requirement*, *energy cost labelling* — and found
nothing. It exists under `cost` + `energyTypes`. **An absence of the name you invented is
indistinguishable from an absence of the capability**, so the search *confirmed* the false belief
instead of refuting it. Searching harder for the wrong string returns the same nothing.

So every issue whose premise is *"X does not exist"* carries this section, and it is not optional:

```markdown
## Prior art
Searched: <the queries you actually ran>, plus the ADR index / CONTEXT-MAP / glossary
Nearest existing: <symbol, file, owning ADR>   ← name something, or you have not searched
Insufficient because: <specific reason>        ← or: "it isn't — closing this instead"
```

Three rules make it work:

1. **Search by BEHAVIOUR or DATA, never by your proposed feature name.** Ask "where would the
   capability live" (the call site, the select context, the dataclass, the oracle), not "is my label
   present."
2. **Consult the four registries first — they are cheaper than any grep and they are authoritative.**
   `docs/adr/README.md` is a number → file → **status** map of everything built;
   [`CONTEXT-MAP.md`](../../CONTEXT-MAP.md) indexes the per-context `CONTEXT.md` files;
   `docs/adr/0065-glossary.md` is the ubiquitous language. All three would have returned ADR-0032 /
   `AttackStat` in seconds. Whichever agent memory is loaded is a fourth.
3. **"Nearest existing" is mandatory and load-bearing.** If you cannot name the closest thing that
   already exists, you have not searched — you have failed to find, which is a different result. The
   line also forces behaviour-search: you cannot name a nearest neighbour you never looked for.

This makes the absence claim **falsifiable** — a reviewer reruns the queries — instead of an
assertion nothing downstream can check. `/implement` re-verifies it at build time as an independent
second check (`.claude/skills/implement/SKILL.md` step 0); the two exist because either can be
skipped or wrong, and they fail for different reasons.

Applies to **every** creation path: `issue_write`, `gh issue create`, `/qa`, `/to-tickets`,
`/wayfinder` child tickets, and the background-task chips (`spawn_task`) — a chip is an issue body
with a shorter life, and a future session builds from its text with nothing in between.

A **self-filed** issue — same session files it and then builds it — additionally gets flagged as
self-filed to `/code-review`'s Spec axis, which is told to distrust it *more*, not less. It inherits
the implementer's misreading and cannot catch it.

## Conventions

- **Create an issue** → `issue_write` with `method: "create"` (`title`, `body`, `labels`, `assignees`).
- **Read an issue** → `issue_read` with `method: "get"` (details), `"get_comments"` (comments),
  `"get_labels"`, `"get_sub_issues"` (children), `"get_parent"`.
- **List issues** → `list_issues` (`state: OPEN|CLOSED`, `labels`, `orderBy`/`direction`).
- **Comment** → `add_issue_comment` (`issue_number`, `body`).
- **Apply / remove labels, assign, close** → `issue_write` with `method: "update"` (`issue_number`,
  plus `labels`, `assignees`, `state: "closed"`, `state_reason: "completed"|"not_planned"`).
  Updating `labels`/`assignees` **replaces** the set — read the current values first if you mean to add.
- **Search** → `search_issues` for text/complex queries; `list_issues` for straight retrieval.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature
requests; `/triage` reads this flag.)_ While `no`, PRs are not part of the triage queue; read them
with `pull_request_read` only when explicitly asked.

Note: GitHub shares one number space across issues and PRs, so a bare `#42` may be either — try
`issue_read` first and fall back to `pull_request_read`. Once you know which it is, say so: refer to
it in prose as **Issue #42** or **PR #42**, never as a bare `#42` (per `CLAUDE.md`).

## Progress-tracking status ladder

One **status chip** per issue tells you where it is in the `grill → spec → build` pipeline at a
glance — the point is to resume on/off work without re-reading. An issue carries exactly **one**
`status:*` label at a time; each stage moves it to the next (remove the old one, add the new one —
`issue_write` `labels` replaces the set, so include only the new status plus any non-status labels).

| Chip | Meaning | Advanced by |
|------|---------|-------------|
| `status:1-grilling` | Filed; decisions not locked yet. Run `/grill-with-docs`. | You, when filing the issue |
| `status:2-spec` | **Grilling complete** — decisions locked. Next: `/to-spec`. | You, when the grill ends |
| `status:3-build` | **Spec complete** — ready for `/implement`. | `/to-spec` (automatic) |
| `status:4-done` | **Build + tests complete — finished.** | `/implement` (automatic), then close the issue |

Only the `1→2` hop is manual (no skill writes issues during a grill); `/to-spec` sets `3-build` and
`/implement` sets `4-done` + closes. A **closed** issue is also "finished" — the chip just lets a
finished issue stay visible on an open board.

**One issue per feature.** The originating issue is the unit of tracking — `/to-spec` posts the spec
as a **comment on that same issue** and advances its chip, rather than spawning a second issue. Keep
the spec, the discussion, and the status all on one issue. That post is **automatic**: `/to-spec`
publishes the finished spec in the same turn it writes it, without asking first — a spec that only
ever appeared in chat is not published.

## When a skill says "publish to the issue tracker"

Post onto the **originating issue** (comment or body) and advance its status chip. Only create a new
issue with `issue_write` (`method: "create"`) when there is no originating issue to attach to.

## When a skill says "fetch the relevant ticket"

`issue_read` (`method: "get"`) for the body, then `method: "get_comments"` for the discussion.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue; its **tickets** are child (sub-)issues.

- **Map**: one issue labelled `wayfinder:map`, holding the Destination / Notes / Decisions-so-far /
  Not-yet-specified / Out-of-scope body. Create with `issue_write` (`method: "create"`,
  `labels: ["wayfinder:map"]`).
- **Child ticket**: create the ticket issue with `issue_write` (`labels: ["wayfinder:<type>"]`,
  one of `research` / `prototype` / `grilling` / `task`), then attach it to the map with
  `sub_issue_write` (`method: "add"`, `issue_number: <map#>`, `sub_issue_id: <child DB id>`).
  ⚠️ `sub_issue_id` is the child's **database id**, *not* its `#number` — get it from the
  `issue_write`/`issue_read` result's `id` field. Put `Part of #<map>` at the top of the child body
  as a human-readable backstop.
- **Blocking**: the GitHub MCP server does **not** expose native issue-dependency edges, so use the
  body convention — a `**Blocked by:** #<n>, #<n>` line at the top of each child body (or
  `None — can start immediately`). A ticket is **unblocked** when every issue on that line is closed.
- **Frontier query**: `issue_read` (`method: "get_sub_issues"`) on the map → keep the open children
  whose `Blocked by` issues are all closed and that have no assignee; first in map order wins.
- **Claim**: `issue_write` (`method: "update"`, `assignees: ["<you>"]`) — the session's first write,
  before any other work, so concurrent sessions skip it.
- **Resolve**: `add_issue_comment` with the answer → `issue_write` (`method: "update"`,
  `state: "closed"`, `state_reason: "completed"`) → append a one-line context pointer (gist + link)
  to the map's Decisions-so-far via another `issue_write` update of the map body.

**One-time label setup.** Labels must exist in the repo before they can be applied (the GitHub API
rejects an unknown label, and this environment's MCP server is read-only for labels — `get_label`
only, no create). Create them once via the GitHub UI (repo → Issues → Labels → New label) or with
`gh` on a machine that has it:

```sh
# Progress-tracking status ladder
gh label create "status:1-grilling" -c "#ededed" -d "Decisions not locked yet — run /grill-with-docs"
gh label create "status:2-spec"     -c "#fbca04" -d "Grilling complete — next: /to-spec"
gh label create "status:3-build"    -c "#1d76db" -d "Spec complete — ready for /implement"
gh label create "status:4-done"     -c "#0e8a16" -d "Build + tests complete — finished"

# Only if you use /wayfinder for big/foggy work
gh label create "wayfinder:map"       -c "#5319e7" -d "Wayfinder map issue"
gh label create "wayfinder:research"  -c "#c5def5" -d "Wayfinder research ticket"
gh label create "wayfinder:prototype" -c "#c5def5" -d "Wayfinder prototype ticket"
gh label create "wayfinder:grilling"  -c "#c5def5" -d "Wayfinder grilling ticket"
gh label create "wayfinder:task"      -c "#c5def5" -d "Wayfinder task ticket"
```
