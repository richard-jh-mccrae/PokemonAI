---
name: code-as-docs
description: "The documentation policy for this repo: the code is the documentation. Read before writing any comment, docstring, ADR or doc, and before building anything that might already exist. Covers the discovery protocol (scan the code for what is built and where to wire in), the comment/docstring size budget, what earns prose at all, and the retirement protocol for deleted names."
---

# Code as documentation

A 2026-08-07 audit read every doc and 6,471 comments in this repo. It found **194 false claims in
source prose**, **43 stale documents**, and **11 ADRs describing modules that no longer behave that
way**. Nothing was lying on purpose. Documentation had simply been written faster than it could be
maintained, and nothing ever checked it.

The conclusion that matters:

> Docs that named a **mechanism** and argued for it stayed true for months.
> Docs that **enumerated** ids, weights, flags and statuses went ~50% false in one refactor cycle.

Because the enumeration already exists in code as `Hypothesis(id=…, weight=…)`, and the doc is a
second copy nothing keeps in sync. So:

**Prose may explain WHY. It may not enumerate WHAT.**

## 1. The order of authority

When two sources disagree, this is the order — no exceptions, no judgement call:

1. **The running code** (and `src/cg/api.py` for engine behaviour, `docs/rules.md` + `docs/rulebook.txt` for game rules, `data/EN_Card_Data.csv` for card facts)
2. **The tests** — they are executable claims, and they fail when they go stale
3. **ADRs** — authoritative about the *decision that was taken*, never about the *current shape of the code*
4. **Everything else** — narrative, and the first thing to distrust

A doc that contradicts the code is **a bug in the doc**. Fix or delete it in the same commit that
finds it; never work around it, and never quietly assume the doc was right.

## 2. Discovery — before you build anything

The most expensive documentation failure is not a wrong comment. It is building something that
already exists, or bolting a second mechanism beside the one that was supposed to own the decision.
Both start with reading prose instead of code.

Before writing code, answer these **against the tree, not against the issue**:

1. **Does this already exist?** Search by *behaviour and data*, never by the feature name the spec
   invented. A grep for a name nobody chose returns nothing whether or not the capability is there.
   Start from the seam: `src/common/runtime.py`'s `PROFILE` lists every shipped kill-switch;
   `src/common/sound_rules.py`'s `WHITELIST` lists every rung allowed to bypass the value stack;
   `CONTEXT-MAP.md` indexes the per-context glossaries.
2. **Where does this decision already live?** Almost every decision in this agent is owned by one
   module. Find that owner and extend it. If you find yourself adding a second place that answers the
   same question, stop — that is the defect the decider swaps (ADR-0069/0070/0080/0085/0086/0100)
   were built to remove, and re-introducing it is worse than not building.
3. **What is the seam?** Name the function or class you will extend and the test that covers it,
   before editing. If no test covers it, that is the first thing to write.
4. **A negative result needs a positive control.** Before concluding "nothing does X", point the same
   query at something that must match. If that stays quiet, your instrument is broken, not the
   codebase. **File existence is never evidence of file content** — if the claim is about what is
   inside a module, open it and quote it.

Report the outcome in one line before building. *Already exists* → stop and say where.

## 3. The size budget — enforced

| Prose | Budget |
|---|---|
| `#` comment block | **2 lines** |
| Function / class docstring | **2 lines** |
| Module docstring | **15 lines** |
| Any prose line | **120 characters** |

`tools/doc_budget.py` computes this; `tests/test_comment_budget.py` is the gate. Run
`python -m tools.doc_budget --detail <path>` for a worklist.

**Needing more than 2 lines is a signal, not an exception to argue for.** It means one of:

- the reasoning belongs in an ADR, and the code should carry a one-line pointer to it;
- the code needs a better name, and then the comment is unnecessary;
- the invariant belongs in a test, where it will fail when it stops being true.

**Over-budget prose is TRIAGED, never truncated.** Sort each block before cutting it, because two
different things are in there and only one is disposable:

| Kind | Recognise it by | Action |
|---|---|---|
| Restatement / enumeration | it repeats the next line, or lists ids, weights, flags, statuses, %-complete | **delete** — the code is the copy that stays true |
| Measured evidence | it reports something someone RAN: a corpus count, an A/B delta, a CI, "zero decisions moved" | **relocate** to the owning ADR, leave a one-line pointer |

Deleting measured evidence is the one irreversible move in a reduction pass: it is not recoverable
from the code, because it is not a fact about the code. It is a fact about an experiment, and losing
it means the next person re-runs it — or worse, re-litigates a decision it already settled.

## 4. What earns prose

**Write a comment for:** a non-obvious *why*; a constraint that would otherwise be re-litigated
("this must stay LF or the parity harness re-diffs"); a trap that has already cost someone
("`inspect.getsource` reads this docstring — see the test"); a pointer to the ADR that ruled it.

**Never write a comment that:** restates the next line; enumerates ids, weights, flags or statuses;
quotes a measurement as current fact; describes what a *different* module does; says "TODO" without
a tracked issue; or claims a default (`default OFF`, `armed-off`, `kill-switched`) — those live in
`runtime.PROFILE` and the audit found several comments contradicting it.

## 5. The retirement protocol

When you delete a named thing — a Hypothesis id, a constant, a flag, a module — the prose that named
it does not follow it out. That single failure produced the largest family of defects in the audit.

So, in the **same commit** as the deletion:

1. `grep -rn '<the-name>' src/ tools/ tests/ docs/` and delete every mention that asserts it is live.
2. Record where the logic went in the **owning module's fold map** — the docstring at the top of the
   `baseline_*` / `doctrine_*` module. `baseline_energy.py` is the worked example: it names all
   nineteen deleted attach rungs and what each became. That is the one place a reader should land.
3. If a deliberate tombstone must stay in `src/` prose, add a `Fold(adr, symbol, note)` to
   `tools/rung_registry.py` naming where the claim went. Prefer deleting the prose — the registry
   carries a shrink-only ceiling, and every raise must be argued at the constant.

A retired id sitting in a **live string literal** — a frozenset member, an inline tuple a `_tier`
predicate matches — reads as LIVE to any prose scan, which silences the alarm on the prose naming it.
That masking has now hidden the same class of defect at two layers (`planner._CLASS_B_SPEND_IDS`, then
`pilot._finish_turn_last`). `tests/strategy/test_rung_id_literals_are_live.py` is the interlock: it
AST-walks for literals compared against a Hypothesis id and holds them to the shipped roster.

## 6. The gates that enforce this

None of the above survives on good intentions; the audit is what good intentions produced. These run
in the suite:

| Gate | Enforces |
|---|---|
| `tests/test_rung_registry.py` | `src/` prose may not name a Hypothesis id that does not exist |
| `tests/strategy/test_rung_id_literals_are_live.py` | a literal a module MATCHES on must be a shipped id |
| `tests/test_doc_links_resolve.py` | every Markdown link points at a file that exists |
| `tests/test_comment_budget.py` | the size budget (arms itself when the reduction pass reaches zero) |
| `tests/test_adr_index.py` | the ADR index matches `docs/adr/` on disk |
| `tests/test_baseline_provenance.py` | `docs/ci.md`'s tables match the committed baselines |

The last one is the pattern to copy. `docs/ci.md` was the only large doc in the repo that survived
the audit intact, and it survived because a test parses its numbers and asserts them. **If a doc must
carry facts, make a test read them. Otherwise it will rot, and you will not find out.**
