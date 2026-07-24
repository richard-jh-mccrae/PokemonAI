# Issue tracker: GitHub (via the GitHub MCP server)

Issues and PRDs for this repo live as **GitHub issues** on `richard-jh-mccrae/PokemonAI`.

> **Environment note.** This repo is driven mostly from Claude Code on the web / mobile, where
> there is **no `gh` CLI** — all GitHub operations go through the **GitHub MCP tools**
> (`mcp__github__*`). Use those, not `gh`. (On a local machine that happens to have `gh`, the
> equivalent `gh issue …` commands work too, but the MCP tools are the portable path.)
>
> Every tool below takes `owner: "richard-jh-mccrae"`, `repo: "PokemonAI"`. Load a tool's schema
> with ToolSearch (`select:mcp__github__issue_write`, …) before first use in a session.

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
`issue_read` first and fall back to `pull_request_read`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue with `issue_write` (`method: "create"`).

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

**One-time label setup.** The `wayfinder:*` labels (`wayfinder:map`, `wayfinder:research`,
`wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task`) and `ready-for-agent` must exist in
the repo before they can be applied. Check with `get_label`; create any missing ones through the
GitHub UI (or `gh label create` locally) the first time you run `/wayfinder` or `/to-spec`.
