# Issue sequence — prerequisites for starting Issue #263 (POC-T4, the Turn Planner)

Compiled 2026-08-03 from a review of all 30 open issues on `richard-jh-mccrae/PokemonAI`, against
Issue #263's own blocker ruling, Issue #278's track acceptance, Issue #298's gating ruling, and
`docs/plans/value-system-poc-plan.md`'s critical path (**T0 → T3 → T3.5 → T4 → T5**).

This is a **sequencing document**, not a spec. Each issue named below is authoritative for its own
scope; nothing here re-scopes any of them.

---

## 0 · Already satisfied — verify, do not rebuild

Issue #263's body names four hard blockers. All four have landed:

| blocker | state | verified at source |
|---|---|---|
| Issue #262 (POC-T3, `state_value`) | closed | `src/common/state_value.py` ships 7 `TermFamily` entries |
| Issue #299 (POC-A2.1/1, seam fate routing) | closed | `apply_option.fate(..., clauses_cover=...)` at `src/common/apply_option.py:596`; `ENGINE_ROUTE_KINDS` at `:260` |
| Issue #300 (POC-A2.1/4, audit teeth) | closed | the `clauses_cover` tri-state precedence table, `apply_option.py:54-64` |
| Issue #260 (POC-T1, StateModel) | closed | prerequisite of Issue #270 below |

Issue #298 (POC-A2.1 parent) has **8 of 8 sub-issues closed**. Its ruled gating set for Issue #263
(Issues #299 + #300) is therefore discharged. Two issues were *spun off* from that track after the
sub-issue list was frozen — Issues #349 and #350 — and both are live prerequisites. See lane B.

Issue #278 (POC-T3.5) is the remaining **declared** blocker: *"Blocks #263 — T4's 1-ply ordering is
built on `state_value`; a term that mis-prices combat mis-orders every candidate that touches it."*
It stands at 11 of 13 sub-issues closed, plus three siblings filed after the fact.

---

## The sequence

Lanes A and B are independent and can run in parallel. **Within lane A, land one at a time** —
Issue #278's standing discipline: eight of these move scoring, and a flip that cannot be attributed
to a cause defeats the wave packet.

### Lane A — close out Issue #278 (POC-T3.5)

**A1 · Issue #329** — *T3.5/14: `threat` saturates into one bit; the cap binds on 100% of inputs.*
Blocked by Issue #281, which has landed — **this is unblocked now and is the natural head of the
lane**. `threat` currently returns exactly `0.0` or exactly `_THREAT_CAP` (0.1) and never anything
between, so a 1-prize Basic prices identically to a 3-prize Mega ex. Under Issue #263's uniform
1-ply ordering that is not "undervalued", it is a whole axis of discrimination the beam cannot rank
on. Its own body requires it land *after* Issue #281 so the scale is measured against the corrected
gate; that condition is now met.

It also has to precede A4: `threat` is the term that *opposes* `survival`, and Issue #330's central
argument rests on the ≤ 0.1 vs ≈ −6.0 asymmetry. Measuring `survival` against a `threat` that is
about to be re-scaled would measure the wrong thing.

**A2 · Issue #332** — *`readiness` funds the Active over the benched successor.*
Smallest of the three decider-split issues, needs no ruling first, and its own body says so. Two
ruled frames where every other family is flat at `0.0000`, so the signal is unusually clean.

**A3 · Issue #351** — *`readiness_p` counts an evaporating Energy on a body that cannot attack.*
Same function as A2 (`_readiness_odds`), so it belongs in the same lane rather than a second pass
over the same code. Its measurement: 25 of 1015 corpus bodies hold a `discard_eot` Energy, the
forward clock moves on all 25, and `_readiness_odds` moves on **none** — a benched Mega Starmie ex
reads `readiness_p == 1.0`. Issue #286's shipped fix is completely masked by it.

This is a genuine Issue #263 prerequisite rather than tidy-up, and the issue states the risk
precisely: `pilot._attach_value` already carries an EVAPORATION gate that `state_value` has no
equivalent of, so **the composer would regress against the incumbent Pilot on a shipped deck**
(`mega_starmie` runs 4 Ignition Energy in 13). Its three options must be *ruled*, not defaulted
into — option 3 (accept the masking, because `attack_ev` prices the swing that cashes the Energy)
is defensible but must be argued and written into `readiness.blind_to` as a verdict.

**A4 · Issue #330** — *`survival` makes the agent play WRONG on 12 ruled frames.* ⚠️ **ruling first**
The largest of the decider-split three, and the one whose answer most directly shapes Issue #263.
`survival` decides 22 of the 44 gating frames across both sets; on two frames the agent **declines a
banked prize** (`prize_race` +1.25 and +1.06) because `survival` charges more against it.

The ruling matters here more than the code, because **option 1 of the three is literally
Issue #263's job** — *"`attack_ev` should be wired, and the asymmetry is then justified"*. Confirmed
at source: `attack_ev` is defined at `state_value.py:800` and referenced only from tests, the audit
report, and one prose docstring mention. No production caller exists, and the develop-rollout leaf is
end-board-only. So the module header's own justification for capping `threat` while leaving
`survival` uncapped — *"crediting the full prize on the board as well would pay twice"* — is
discharged by nothing shipped.

**Recommendation:** rule option 1, and scope the *demonstration* (that the 12 frames resolve once
`score(sequence) = state_value(end) + EV(terminal)` is live) into Issue #263's acceptance rather than
building a `survival` bound here. Issue #263 already commits to that formula in
§ *Terminal-action valuation*. Rule it explicitly either way — do not let it default.

**A5 · Issue #331** — *`development` credits a card play that nothing charges for.* ⚠️ **ruling first**
Filed at `status:2-spec` for exactly this reason. Arming `leaf_hand_value` was already tried and
measured **worse** (104 unruled `OK → MISS` armed against 67 unarmed), and the measurement is
preserved in `planner._simulate_line`'s comment block. Do not re-run that experiment.

Its option 1 is *"leave the ruling — Issue #263's 1-ply ordering scores REAL boards where `hand` is
fully live, so the defect may not survive the composer at all."* **Recommendation: rule option 1 or
option 3** (hold the 5 frames out against the named omission), both of which cost nothing and unblock
the lane. Option 2 — a snapshot at the true end of my turn — has **no owner today** and would be a
substrate build sitting on the critical path.

**A6 · Issue #289** — *T3.5/11: known top-of-deck.* ⚠️ **the schedule question — see §Decisions**
Ruled **build**, with a full spec posted 2026-08-02 (54 user stories, 10 implementation decisions,
8 fixture groups, a `slowking` runnable scaffold, and new corpus frames). This is by a wide margin
the largest remaining item in the lane, and its own spec requires an internal two-step landing
(scaffold + frames first, scoring surfaces second) because the new frames move both gates for a
reason unrelated to the scoring change.

**A7 · Issue #291** — *T3.5/13: closeout.* **Must be last, and must not be skipped.**
Blocked by every other issue in the track. Three deliverables, and the third is the one Issue #263
cannot start without:

1. Reconcile `docs/plans/term-sufficiency-audit.md` — record whether the audit's own prediction
   (F1 + F2 + F4 are one shared damage context) held.
2. Re-measure the 15 deferred frames. Both outcomes are written down in advance; note the
   concentration finding (all 15 are `mega_starmie`), not only the count.
3. **Record the P95 per-decision wall-clock.** Issue #263 § *Acceptance* requires *"per-decision
   wall-clock within the measured budget on the corpus P95"*, and § *Beam-quality package* sizes beam
   width against a measured number. Without this, Issue #263's structural caps are guesses — which
   is exactly what its own "no silent caps" discipline forbids.

### Lane B — apply-seam silent zeros (parallel to A; both must land before Issue #263)

Both were spun off Issue #302 after Issue #298's sub-issue list was frozen, so neither appears in
that track's gating ruling. Both are nonetheless prerequisites, and both say so in their own bodies.

**B1 · Issue #350** — *`cost` is undeclared vocabulary: no cost value has a write-set.*
`snapshot_coverage.VOCABULARY_KEYS` is `("kind", "rider", "effect")`; `cost` is absent, so no cost
value can fail `clauses_writing_unhomed()` however undeclared it is. The issue states the T4
consequence in as many words: *"it matters at T4, when the seam differences a play: a `cost` whose
write is undeclared prices at exactly 0, so Ultra Ball's two discarded cards and Kofu's two bottomed
ones would look free."* Kofu's `bottom_2` is the sharp case — it writes `deck_order`, the registry's
one `hidden` zone.

Cheap: a ruling plus five entries, no new machinery. `CLAUSE_PARAMETERS` (Issue #302) is the
key-axis precedent for the value-axis fix.

**B2 · Issue #349** — *the board-scaled magnitude: no clause field says "for each".*
Issue #263 **deletes the 2 heal timing rungs** and prices heal by differencing the survival term —
the family the issue names as *"the family that motivated differencing"*. Heal magnitudes are
**live**: `planner._heal_candidate` and `planner._heal_averts_doom` both read `clause["amount"]` and
compare it to incoming damage. Fennel heals 40 from *each* of your Pokémon, and `amount: 40`
under-states a 5-body board by 160. A composer differencing that clause prices the play at a fifth of
its effect.

Land the field and its readers together, or land the field explicitly inert — the issue is explicit
that a silent landing changes survival reads.

### Lane C — integration and CI hygiene (parallel; C1 recommended, C2/C3 optional)

**C1 · Issue #270** — *POC-A3: cross-track integration tests, Issue #260's StateModel API vs
Issue #262's consumption.* Both prerequisites are merged, so this is ready today. It exists for a
failure mode invisible to either PR alone: semantic drift where absence is expressible as a value
that reads as a measurement (the ADR-0093 defect class). Issue #263 builds a beam on top of both
tracks and evaluates that seam once per candidate per decision — a semantic mismatch found *after*
the composer lands is found through a mis-ordered beam, which is the hardest possible place to see
it. **Recommended before Issue #263, not after.**

**C2 · Issue #352** — *`probe_card` flake.* Not a logical prerequisite. It is a pre-existing flake in
CI's determinism backstop that lands red on unrelated PRs (it has now done so twice, both times on
docs-only commits), and Issue #263's PR will be one of the largest in the project. Fixing it first
buys a clean signal on a PR where a red run is expensive to attribute. Note the reproduction must be
on Linux or by forcing the exhaustion condition — it does not reproduce on Windows.

**C3 · Issue #339** — *the leaf gate's baseline-provenance table is 5 movements stale, one of them a
ruling-bearing re-capture.* Issue #263 will move both baselines again and produce the largest wave-3
packet in the project. Correcting the provenance record **before** adding to it is cheaper than
reconstructing it afterwards, and a ruling-bearing re-capture that is not in the table is precisely
the kind of gap that makes a baseline stop functioning as a ruling record.

---

## Decisions owed before the lane can be walked

Four. Three are ordinary rulings; one is a schedule call.

**D1 · Issue #330's ruling** (A4 above). Recommendation: option 1, with the demonstration scoped into
Issue #263's acceptance.

**D2 · Issue #331's ruling** (A5 above). Recommendation: option 1 or option 3. Option 2 has no owner
and would put a substrate build on the critical path.

**D3 · Issue #275 agenda item 1 — does the defender-side attach sweep axis pull ahead of
Issue #263?** The issue's own § *Sequencing* argues yes and stops short of ruling it: *"the Turn
Planner prices every unbuilt trainer family as an end-state difference, and that differencing reads
the damage oracle underneath — so a systematic blind spot in defender-side state propagates into
every option the planner values."* The concrete finding behind it is sharper than a missing axis:
running the harness as it stands on attack 425 would not fail to fit it, it would **confirm the wrong
answer**, because the default panel puts non-`{ex}` bodies on the defender's side.

**Recommendation: pull axis 1 (defender attach) ahead; leave axes 2–4 deferred.** Axis 1 is the one
with reuse beyond these four cards — it is also what would let the audit verify defender-side
condition gates it cannot reach today. Axes 3 and 4 serve two cards *provably absent* from the pool
as exercised, so they buy insurance rather than correctness. Note Issue #275 is at
`status:1-grilling` and would need a spec pass first, which is itself a reason to scope it to one
axis.

**D4 · Issue #289's position — critical path, or beside Issue #263?**
Build-versus-declare is already ruled (build), so this is purely *when*. Two facts pull in opposite
directions:

- Issue #278 blocks Issue #263, and Issue #289 is one of its sub-issues — strictly, it must land.
  But Issue #278's own acceptance already anticipates an exception: *"all 13 sub-issues closed, **or
  explicitly closed with a recorded developer ruling** (#289 is the expected candidate)"*.
- Issue #289's subject touches **no composer machinery**. Its three consumers are the odds machinery,
  `hand`'s `re_access` leg, and a terminal-action damage model for one attack on one deck. Issue #263
  composes all three, but none of them shapes the composer's code — the same relationship
  Issue #298 used to rule Issues #301–#306 as *beside* rather than *blocking*.

**Recommendation: split it.** Land the part that closes Issue #278's contract — decision D8's
registry work (the corrected `deck_order` rationale plus the homed Known Top zone, which is also
Issue #290's item 2) — inside lane A, and run the full Known Top build **beside** Issue #263 on
Issue #301's precedent. That keeps Issue #278's acceptance honest while taking a 54-story build with
its own two-step gate-landing off the critical path. It is the single largest schedule lever in this
document.

If the answer is instead "keep it in the path", then A6 should be split internally per its own spec
(scaffold + corpus frames first, ruled; scoring surfaces second) and budgeted accordingly.

---

## Explicitly NOT prerequisites

Recorded so they are not swept in by proximity.

| issue | why not |
|---|---|
| Issue #273 (POC-B3, time budget) | *"Prerequisite: Issue #263 merged."* Runs after, alongside the first ladder submission. Issue #291's P95 is the number Issue #263 starts from; Issue #273 is the deeper read against the grader's real hardware. |
| Issue #264 (POC-T5, purge + integration) | Explicitly downstream — T4 → T5. |
| Issue #347 (60 expired `covered` closures) | A **human ruling sitting**, not agent work. Feeds Issue #146 (Phase 3), not Issue #263. |
| Issue #272 (POC-B1/B2 calibration) | Issue #330 *concretises* it — Issue #330 supplies the measurement Issue #272 asks for. Issue #272 may close into Issue #330. |
| Issue #271 (corpus representativeness) | `status:1-grilling`; a corpus question, not a seam or term one. |
| Issue #353 (whole-game note scoring) | Zero affected entries remain; a judgment call about the notes format. Unrelated. |
| Issues #190, #146–#150, #151, #149 | Later phases and post-competition work. |

---

## The dependency tree

**Read the shape first: this graph is WIDE at the root and NARROW at the tip.** That is the opposite
of what a prerequisite tree usually looks like, and it is not an accident — every upstream track
(T0, T1, T3, and Issue #298's eight sub-issues) has already merged, so what remains is four lanes
with no dependency on each other, converging on one closeout node.

```
LEGEND
  ■  build-ready         spec is at build depth; start coding
  ◆  ruling owed first   a developer decision, then build (or then NOTHING — see D1/D2)
  ▲  grill owed first    status:1-grilling → /grill-with-docs → /to-spec → /implement
  ──→   hard prerequisite — the downstream work is wrong or impossible without it
  ┄┄→   advisory ordering — same file, or "measure this after that". Order matters; dependency does not.
```

```
● TODAY ─ all four lanes are unblocked right now
│
│   ┌─────────────────────────────────────────────────────────────────────┐
│   │  ANSWER THESE FIRST — each can DELETE work from the tree below      │
│   │    ◆ D1  rule Issue #330   → option 1 removes an entire landing     │
│   │    ◆ D2  rule Issue #331   → option 1 or 3 removes an entire landing│
│   │    ◆ D4  place Issue #289  → "split" moves the 54-story build off   │
│   │                              the critical path                      │
│   │    ◆ D3  Issue #275 in-path? → "no" removes LANE 5 entirely         │
│   └─────────────────────────────────────────────────────────────────────┘
│
├── LANE 1 ── Issue #278 (POC-T3.5) closeout
│   │         Develop in PARALLEL. LAND ONE AT A TIME — Issue #278's standing
│   │         discipline; a flip that cannot be attributed to a cause defeats
│   │         the wave packet. The arrows below are LANDING order, not
│   │         development order.
│   │
│   ├─■ #329  T3.5/14 · threat saturates into one bit
│   │  │      Head of the lane: Issue #281 landed, so it is unblocked, and it
│   │  │      re-scales the term Issue #330's whole argument is measured against.
│   │  ┊
│   │  ┊┄┄→ (measurement hygiene, not a blocker: no frame overlap between the
│   │  ┊     five Issue #329 names and the twelve Issue #330 names)
│   │  ▼
│   ├─◆ #330  survival out-scales everything · 12 ruled frames played wrong
│   │  │      D1. Answer BEFORE writing code: option 1 ("wire attack_ev — that
│   │  │      is Issue #263's job") means this lands ZERO code here and becomes
│   │  │      an acceptance clause on Issue #263 instead.
│   │  ▼
│   ├─◆ #331  development credits a play nothing charges for · 5 frames
│   │  │      D2. Same shape: option 1 ("leave it — the composer scores REAL
│   │  │      boards where `hand` is live") or option 3 (hold the frames out)
│   │  │      both land zero code. Option 2 is a substrate build with no owner.
│   │  ▼
│   ├─■ #332  readiness funds the Active over the benched successor
│   │  │      Smallest, no ruling owed, cleanest signal (every other family
│   │  │      flat at 0.0000 on both frames).
│   │  ┊
│   │  ┊┄┄→ (file contention: both edit `_readiness_odds`. Either order works;
│   │  ┊     they are DIFFERENT facts — which body to fund vs which Energy counts)
│   │  ▼
│   ├─■ #351  readiness_p counts an evaporating Energy on a body that cannot attack
│   │  │      Unmasks Issue #286. Carries its own embedded ruling (its three
│   │  │      options must be decided, not defaulted into).
│   │  ▼
│   └─◆ #289  T3.5/11 · known top-of-deck
│      │      D4. Build-vs-declare is ALREADY RULED (build) and the spec is
│      │      written. The open question is only WHERE:
│      │        · "split"   → registry half (spec D8) lands here; the Known Top
│      │                      build runs BESIDE Issue #263 on Issue #301's precedent
│      │        · "in-path" → full build here, itself split two ways per its own
│      │                      spec (scaffold + corpus frames, ruled; then scoring)
│      ▼
│    ┌───────────────────────────────────────────────────────────────┐
│    │  ■ #291  T3.5/13 CLOSEOUT — THE SINGLE JOIN NODE              │
│    │  Formally blocked only by Issue #289 (the last open           │
│    │  registered sub-issue). In practice it must be LAST overall,  │
│    │  because two of its three deliverables go stale the moment    │
│    │  anything downstream of them lands:                           │
│    │    1 reconcile the audit report + its verdict                 │
│    │    2 re-measure the 15 deferred frames                        │
│    │    3 record the P95 per-decision wall-clock ◄── Issue #263    │
│    │      sizes its beam against THIS NUMBER                       │
│    └───────────────────────────────────────────────────────────────┘
│                                    ▲          ▲
├── LANE 2 ── apply-seam vocabulary  │          │
│   │         Serial: both edit `snapshot_coverage.py`.
│   │         Gate-NEUTRAL one first, scoring-mover second.
│   │
│   ├─■ #350  `cost` is undeclared vocabulary — no cost value has a write-set
│   │  │      Gate-neutral by its own acceptance (`CLAUSE_WRITES` has no runtime
│   │  │      consumer today). A ruling + five entries, no new machinery.
│   │  ▼
│   └─■ #349  the board-scaled magnitude — no clause field says "for each"
│      │      Heal magnitudes ARE live (`_heal_candidate`, `_heal_averts_doom`),
│      │      so this one moves scoring. Land the field and its readers together,
│      │      or land the field explicitly inert.
│      └──────────────────────────────────────────────► joins at #291
│
├── LANE 5 ── conditional on D3 ── Issue #275 defender-side attack audit
│   │         ▲ #275  GRILL (status:1-grilling) → spec → build AXIS 1 ONLY
│   │         Feeds #291 because it changes the damage oracle, which every
│   │         state_value read sits on. Defer axes 2–4 (they serve two cards
│   │         provably absent from the pool as exercised).
│   └──────────────────────────────────────────────────► joins at #291
│
├── LANE 3 ── integration ── joins at Issue #263 directly (tests only, no scoring change)
│   └─■ #270  POC-A3 cross-track integration tests
│             Ready today (Issues #260 + #262 both merged). Catches semantic
│             drift BEFORE the composer builds a beam on the seam — after
│             Issue #263 lands, the same drift is only visible as a mis-ordered beam.
│
└── LANE 4 ── CI hygiene (optional) ── joins at Issue #263 directly
    ├─▲ #352  probe_card flake — GRILL first (confirming the mechanism is task 1).
    │         Not a logical prerequisite; buys a clean CI signal on what will be
    │         one of the largest PRs in the project. Reproduce on Linux only.
    └─■ #339  the leaf gate's baseline-provenance table is 5 movements stale.
              Correct the record before Issue #263 adds to it.

                                    │
                                    ▼
                    ►►► Issue #263 — POC-T4, the Turn Planner ◄◄◄
                                    │
                                    ├──► Issue #273  POC-B3 per-decision time budget
                                    └──► Issue #264  POC-T5 purge + integration
```

### Why the branch points sit where they do

- **Four lanes at the root, not one sequence**, because lanes 1/2/3/4 share no file, no term and no
  measurement. Lane 1 is `state_value.py` + the Pilot; lane 2 is `snapshot_coverage.py` +
  `card_effects.json`; lane 3 is `tests/` only; lane 4 is CI and a probe harness.
- **Lane 1 is serial for LANDING only.** Issue #278 says it outright: *"develop in parallel, land one
  at a time."* Five of its nodes are independently developable today; what serialises them is the
  gate-attribution rule, not a code dependency.
- **The only true many-to-one join is Issue #291**, and it joins there because of *measurement*
  staleness, not compilation order — its P95 and its 15-frame re-measurement are only meaningful once
  everything that moves scoring or per-decision cost has landed.
- **Lanes 3 and 4 bypass Issue #291** and attach straight to Issue #263, because neither changes a
  score or a per-decision cost.

### The collapsed tree, if the recommended rulings are taken

D1 = option 1 · D2 = option 1 · D4 = split · D3 = yes (axis 1). The tree shortens to:

```
● TODAY
├─ LANE 1:  #329 → #332 → #351 → #289(registry half) ────┐
├─ LANE 2:  #350 → #349 ─────────────────────────────────┤
├─ LANE 5:  #275 grill → build axis 1 ───────────────────┤
│                                                        ▼
│                                                    ■ #291 ──┐
├─ LANE 3:  #270 ────────────────────────────────────────────┤
└─ LANE 4:  #352, #339 (optional) ───────────────────────────┤
                                                             ▼
                                                   ► Issue #263
```

Six landings on the critical path (Issues #329, #332, #351, #289-registry, #350, #349) plus
Issue #291, with Issues #330 and #331 discharged as rulings that cost no code and Issue #289's
54-story build running beside Issue #263 rather than in front of it.

---

## Summary — the minimum walk

**Hard minimum** (nothing optional, D4 answered "split"): Issues #329, #332, #351, #350, #349, #291,
plus rulings on Issues #330 and #331 and the registry half of Issue #289.
**Recommended** adds Issues #270, #275 (axis 1 only), #352 and #339.
