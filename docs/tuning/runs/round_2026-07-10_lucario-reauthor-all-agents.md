# blunder-buster round — 2026-07-10 (ALL agents)

Trigger: `/blunder-buster @data/corrections/mega_lucario_20260709_e2f0a07-dirty` (14 new corrections,
8 CRITICAL). Scope executed = **every agent with `own` corrections** (`tune.py` with no `--agent`), per the
skill's default. Analysis-only round: proposals routed, nothing authored or committed — `/update-strategy`
drains the queue.

## Method note — the "W-route satisfied" count is again not the truth

`tune.py` reported **26/34** W-route constraints satisfied for mega_lucario and filed f88 under
`skipped: tactical`. A real-Pilot `decide()` sweep of all 14 corrections shows **13 still blunder** on the
shipped agent; only f109 is degenerate (`chosen == correct`). Same lesson as the dragapult round
([[wroute-satisfied-not-fixed]], [[skipped-frames-need-retest-triage]]). The weight deltas the fit produced
for the "satisfied" frames (`power-up-attacker` 15 → 3.22, `grab-a-draw-supporter-in-setup` 10 → 4.0,
`prefer-wincon-line-piece` 18 → 15, …) are **mis-fits**: they sand down general rules for every deck and fix
none of these frames. `src/agents/*/tuned.json` currently carries them — `/update-strategy` should author
the roots below and drop the nudges.

The sweep also surfaced a frame `tune.py` has silently skipped every round: **84889539 f48**
(`ignored_threat`), which is the same "don't wake the giant" doctrine as the new CRITICAL f88.

## Terminal outcomes — every open correction, every agent

### mega_lucario — the new round (store `mega_lucario_20260709_e2f0a07-dirty`)

| correction | CRIT | outcome | evidence |
|---|:--:|---|---|
| 85058051 f4 | | proposal-routed | `a-tool-attach-is-not-an-energy-attach` (general-hypothesis) |
| 85058051 f13 | ✔ | proposal-routed | `lethal-bench-the-attack-enabler` (planner-code) |
| 85058574 f16 | | proposal-routed | `lunar-cycle-beats-an-inert-bench-attach` (deck-strategy) |
| 85058574 f69 | ✔ | proposal-routed | `dont-buff-an-attack-you-cannot-use` (general-hypothesis) |
| 85058574 f71 | | proposal-routed | `grab-what-advances-the-plan-not-a-redundant-supporter` |
| 85058574 f87 | ✔ | proposal-routed | `a-tool-attach-is-not-an-energy-attach` |
| 85058574 f88 | ✔ | proposal-routed | `dont-wake-the-giant-with-the-self-locking-ko` (planner-code) |
| 85058574 f109 | | proposal-routed | `dragapult-matchup-plan-the-drakloaks-are-the-target` (matchup-brief) |
| 85058574 f114 | ✔ | proposal-routed | `dont-play-a-search-item-with-nothing-to-find` |
| 85058574 f121 | ✔ | proposal-routed | `dont-fund-the-non-attacking-engine-body` (cross-agent) |
| 85059103 f1 | | proposal-routed | `open-with-an-attacker-not-the-pure-engine` |
| 85059103 f9 | ✔ | proposal-routed | `grab-what-advances-the-plan-not-a-redundant-supporter` |
| 85059103 f39 | ✔ | proposal-routed | `no-phantom-grab-lethal-check-the-retreat-and-the-necessity` (planner-code) |
| 85059103 f84 | | proposal-routed | `dont-fund-the-non-attacking-engine-body` (cross-agent) |

All 8 CRITICALs land on a proposal. None reaches `refuted` or `capability-gap`, so no hard-stop was raised.

### mega_lucario — carried from earlier rounds

| correction | outcome | evidence |
|---|---|---|
| 84071010 f15 | proposal-routed | `lethal-retreat-enabler` (open, `blunder-20260709-mega_lucario.md`) |
| 84889539 f48 | proposal-routed | folded into `dont-wake-the-giant-with-the-self-locking-ko`; was `skipped: tactical` |
| 84890060 f48 | **covered** | real-Pilot `decide()` = `[9]` = Fighting Gong = `correct`; the applied `lethal-recover-the-energy-that-wins` grab tactical prices it 1001, and the grab is both legal (Lunatone Active, 1{F}, retreat 1) and necessary (benched Mega at 0 Energy). Ledgered — it is the counter-fixture the phantom-grab-lethal proposal must not regress. |

### mega_starmie

| correction | outcome | evidence |
|---|---|---|
| 81785223 f45 | proposal-routed | `snipe-order-a-ko-dominates-the-positional-stack` (its half needs human confirmation — the correction carries **no rationale**) |
| 82753102 f63 | proposal-routed | same proposal |
| 82754241 f45 | proposal-routed | same proposal |
| 83967840 f54 | **covered** | retest `fixed=True` — the applied `discard-a-draw-duplicate-before-an-evolution-tutor` sheds the duplicate Lillie's. The W-route stays UNSATISFIED because a rule fix is invisible to the weight fit. Ledgered. |

### dragapult_ex — already routed, no new work

Its whole open set (`85046350:f18` open; `85045840:f14`, `85046350:f21`, `f31`, `f85` unsatisfied) is
covered by the four still-open proposals in `blunder-20260709-dragapult_ex.md`. The **f21 attach-target
half** was merged into this round's cross-agent `dont-fund-the-non-attacking-engine-body`; a note in that
file points at it so `/update-strategy` authors the suppressor once.

## The root, in one paragraph

The general layer keeps missing on mega_lucario because three seams were never exercised by the two earlier
decks. **(1) Non-energy attaches** — Air Balloon is the first non-HP Tool; it is not even `tool`-tagged, so
`power-up-attacker` scores it as Energy. **(2) Non-attacking bodies** — Lunatone (pure engine) and Meowth ex
(2-prize supporter tutor) share the Bench with real attackers, and `attach_target_needs` ("carries fewer
Energy than its cheapest attack cost") *ranks the non-attacker highest*. **(3) Conditional and self-locking
attacks** — Cosmic Beam's `requiresBench`, Mega Brave's and Accelerating Stab's next-turn locks. The Lethal
Solver's generator family never benches a body; `active_attack_payable` is energy-math only. Every proposal
below is a signal/gate correction to an existing rule or a missing Planner arm, not a new deck weight.

## Queue

`data/strategy/proposals/blunder-20260710-round.md` — 12 proposals: 3 `planner-code`, 7
`general-hypothesis`, 1 `deck-strategy`, 1 `matchup-brief`. Fixtures under
`tests/fixtures/corrections/` (18 written this round). Dashboard refreshed: `reports/blunders.html`.
