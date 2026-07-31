# The Decision Gate's blessed disagreements — a triage

> ## ⚠️ Re-derived 2026-07-31 over the FULL corpus (Issue #241)
>
> Every count below was computed over a **332-frame** capture that was missing 40 replayable records
> and mis-naming 163 more. The instrument moved, so the readings moved with it. The originals are
> kept, not overwritten — they were correct about the corpus they described.
>
> | | as written (`e50735a`, 332 frames) | re-derived (372 frames) |
> |---|---|---|
> | labelled frames | 331 | **371** |
> | agree | 230 | **253** |
> | **disagreements** | **101** | **118** |
> | Tier B (`covered`, still missing) | 28 | **43** |
>
> **The Tier B delta is fully attributed**, which is the point of landing the re-key separately
> (ADR-TEMP-241 decision 5):
>
> ```
> 43  =  28 (as written)  +  14 (frames the 332 could not see)  +  1 (agent drift)   0 resolved
> ```
>
> The method reproduces **28 exactly** against the original `e50735a` capture, and the re-key commit
> moves it by **0** — independent confirmation that the relabel changed no ruling. The 14 newly
> visible frames are appended to Issue #238 as *unadjudicated candidates*; this document does not
> rule them, and neither does the issue that widened the corpus.
>
> Tier A's 18 `refuted` labels re-derive to **20** over the full set. Sections below are unedited
> apart from this block — where a number in them disagrees with this table, this table is the later
> reading and the section is the original one.

**What this is.** `data/decider_lab/baseline.json` records what the shipped agent DECIDES on every
replayable Correction, and the Decision Gate defends that record against regression. On **101** of
its 331 labelled frames the recorded decision **contradicts a human ruling**. Nothing about that is
hidden — but until this pass nothing examined it either, and the gate will defend those 101 wrong
answers exactly as vigorously as the 230 right ones.

**This does not change the gate, and must not.** The gate's job is regression detection and it does
that correctly; a build that fixes one of these shows up as a `FIX` row, which is the system working.
The risk this document exists to blunt is the *opposite* reading — that a green Decision Gate means
the agent is right. It does not. It means nothing moved.

Written 2026-07-30, closing item 1 of `decision-gate-rebuild-handoff.md`. The tiers below are the
input to the correction rounds **Issue #146** owns.

## Read the headline number carefully: 101, not 111

The hand-off recorded **111**. Ten of those were never disagreements — they were a **vocabulary
mismatch**, now ruled by ADR-0085 Amendment J. A Correction's `correct` names *the card the ruling
was about*; a multi-pick select returns *every* index the engine demands. Comparing them by equality
scored `DISCARD` at 1/12 purely because the agent picks `[2, 3]` where the ruling says `[2]`. Read as
satisfaction (`correct ⊆ chosen`) the same corpus reads 10/12, and the corpus-wide agree rate moves
220/331 → **230/331** with **no decision changed**.

That is worth stating plainly because it sets the standard for the rest of this triage: **the first
question about a disagreement is whether it is real**, and roughly a tenth of them were not.

## The tiers, highest value first

| tier | what it is | n | the work |
|---|---|---|---|
| **B** | reviewed and marked `covered` — yet the agent still misses | **28** | **start here.** A rule believed to handle this frame does not. |
| **C** | never been through a blunder round | **55** | fresh signal for Issue #146's next rounds |
| **A** | reviewed and marked `refuted` — the *label* is wrong | **18** | no fix owed; the agent is right to disagree |

### By context

| ctx | name | disagreements | refuted | covered | unreviewed | likely owner |
|---|---|---|---|---|---|---|
| 0 | `MAIN` | 85 | 15 | 24 | 46 | Issue #165 (Turn Planner) |
| 2 | `SETUP_BENCH_POKEMON` | 2 | 0 | 1 | 1 | Issue #197 |
| 3 | `SWITCH` | 2 | 1 | 1 | 0 | promote/retreat |
| 5 | `TO_BENCH` | 1 | 0 | 0 | 1 | promote/retreat |
| 7 | `TO_HAND` | 6 | 0 | 1 | 5 | hand selection |
| 8 | `DISCARD` | 2 | 1 | 1 | 0 | discard selection |
| 15 | `DAMAGE` | 2 | 1 | 0 | 1 | snipe (ADR-0085 decision 7) |
| 21 | `ATTACH_FROM` | 1 | 0 | 0 | 1 | attach |
| | **total** | **101** | **18** | **28** | **55** | |

### By blunder category

| category | n | refuted | covered | unreviewed |
|---|---|---|---|---|
| `wasted_resource` | 37 | 3 | 8 | 26 |
| `sequencing_error` | 24 | 7 | 6 | 11 |
| `misattachment` | 15 | 1 | 10 | 4 |
| `slow_setup` | 6 | 0 | 1 | 5 |
| `bad_target` | 5 | 2 | 2 | 1 |
| `wrong_supporter` | 5 | 3 | 1 | 1 |
| `bad_retreat` | 4 | 1 | 0 | 3 |
| `missed_win` | 2 | 0 | 0 | 2 |
| `wrong_attack` | 2 | 1 | 0 | 1 |
| `missed_disruption` | 1 | 0 | 0 | 1 |
## Tier B — `covered`, but still missing (28) — the highest-value class

These frames went through a blunder round and were closed as *covered by a shipped rule*. The agent
still gets them wrong. One of two things is true of each: the rule never covered it, or **the rule is
gone**.

**Thirteen of the 28 name a rung the deletion passes deleted.** Cross-referencing each review note
against the authoritative `RETIRED` lists the four decider sweeps carried:

| frame | ctx | coverage claimed by | the review note that no longer holds |
|---|---|---|---|
| `81903490-27` | 0 | `dont-waste-discard-energy` | dont-waste-discard-energy sinks Ignition->Staryu to -20 (below End); Basic->Staryu +10 - real Pilot digs  |
| `81903490-49` | 0 | `dont-waste-discard-energy` | dont-waste-discard-energy sinks Ignition->Cinderace to -20; Basic->Cinderace +10 - attaches Basic not Ign |
| `81904451-50` | 0 | `dont-waste-discard-energy` | dont-waste-discard-energy sinks Ignition->Cinderace to -35 (dead last); Hilda endorsed via tutor-the-winc |
| `81904451-6` | 0 | `dont-waste-discard-energy` | dont-waste-discard-energy sinks Ignition->Cinderace to -20; Basic->Cinderace +10 - develops then attaches |
| `81905522-47` | 0 | `power-up-attacker` | attack-last defers the Attack; real Pilot evolves the wincon first; Basic-attach (power-up-attacker 15) o |
| `81906131-25` | 0 | `dont-waste-discard-energy` | degenerate record (chosen == correct); the intent is already handled by dont-waste-discard-energy |
| `82524455-27` | 0 | `build-active-wincon` | Real Pilot decide() now picks the attach (build-active-wincon fires +20; retest chosen [3]->[2]=correct). |
| `82750161-59` | 0 | `concentrate-energy-on-wincon`, `dont-waste-discard-energy` | concentrate-energy-on-wincon: agent attaches a reusable Basic to the 1-energy benched Mega (priority winc |
| `82752045-80` | 0 | `concentrate-energy-on-wincon` | develop-before-KO already covered by concentrate-energy-on-wincon for evolved benched wincons; here the b |
| `82752045-97` | 0 | `concentrate-energy-on-wincon` | concentrate-energy-on-wincon: agent attaches Basic to the most-built benched Mega over the bare one; reco |
| `82756664-74` | 0 | `conserve-burst-when-no-ko` | Value-model / dig-before-commit: real Pilot plays Hilda (informative tutor +20) then attaches same turn ( |
| `83007714-7` | 0 | `dont-waste-discard-energy` | FIXED in the real Pilot by the new prefer-active-attach-in-setup (+8): energy now goes to the ACTIVE Cind |
| `83116501-89` | 0 | `concentrate-energy-on-wincon` | Fixed this round via the _priority_wincon_slot doomed-active skip: with the Active doomed (70HP Mega, 1e) |

This is a **coverage claim that expired with the thing it named**, and it is the same failure shape
as the hand-off's own lesson about the gates: *a measured claim expires when the thing it measured
moves.* The deletion passes retired these rungs on the premise that the new equation subsumed them.
For these 13 frames that premise is measurably false — the equation does not reach the decision the
deleted rung was closed against. That is a genuine finding for Issue #146, and it is the strongest
single lead in this document.

⚠️ Not every `dont-waste-discard-energy` mention is automatically a defect: some notes cite the rung
as *one* reason among several, and the modern attach equation may reach the same call by another
route. Each needs the frame opened. What is not in doubt is that the stated justification no longer
exists.

### All 28 `covered` frames
| frame | ctx | agent | category | agent played | human ruled | review note |
|---|---|---|---|---|---|---|
| `81903490-27` | 0 | mega_starmie | misattachment | Attach Ignition Energy → Staryu | Attach Basic {W} Energy → Staryu | dont-waste-discard-energy sinks Ignition->Staryu to -20 (below End); Basic->Staryu +10 - real Pilot digs first |
| `81903490-49` | 0 | mega_starmie | misattachment | Attach Ignition Energy → Cinderace | Attach Basic {W} Energy → Cinderace | dont-waste-discard-energy sinks Ignition->Cinderace to -20; Basic->Cinderace +10 - attaches Basic not Ignition |
| `81904451-50` | 0 | mega_starmie | misattachment | Attach Ignition Energy → Cinderace | Play Hilda | dont-waste-discard-energy sinks Ignition->Cinderace to -35 (dead last); Hilda endorsed via tutor-the-wincon (4 |
| `81904451-6` | 0 | mega_starmie | misattachment | Attach Ignition Energy → Cinderace | Attach Basic {W} Energy → Cinderace | dont-waste-discard-energy sinks Ignition->Cinderace to -20; Basic->Cinderace +10 - develops then attaches Basi |
| `81905522-47` | 0 | mega_starmie | sequencing_error | Attack | Attach Basic {W} Energy → Staryu | attack-last defers the Attack; real Pilot evolves the wincon first; Basic-attach (power-up-attacker 15) outran |
| `81906131-25` | 0 | mega_starmie | bad_target | Attach Ignition Energy → Cinderace | Attach Ignition Energy → Cinderace | degenerate record (chosen == correct); the intent is already handled by dont-waste-discard-energy |
| `82524455-27` | 0 | mega_starmie | sequencing_error | Attack | Attach Basic {W} Energy → Mega Starmie | Real Pilot decide() now picks the attach (build-active-wincon fires +20; retest chosen [3]->[2]=correct). W-ro |
| `82748422-26` | 0 | mega_starmie | wasted_resource | Play Crushing Hammer | Attach Basic {W} Energy → Mega Starmie | play-energy-denial stands down when active_cheap_attack_kos (Jetting Blow KOs the Active): the strip is moot,  |
| `82750161-59` | 0 | mega_starmie | misattachment | Attach Basic {W} Energy → Mega Starmie | Attach Ignition Energy → Mega Starmie  | concentrate-energy-on-wincon: agent attaches a reusable Basic to the 1-energy benched Mega (priority wincon);  |
| `82751468-14` | 0 | mega_starmie | misattachment | Attach Basic {W} Energy → Cinderace (a | Attach Basic {W} Energy → Mega Starmie | Planner ko_for_prizes line executes the human's exact intent (retreat Cinderace -> promote/attach a benched Me |
| `82752045-80` | 0 | mega_starmie | sequencing_error | Attack with Jetting Blow | Play Night Stretcher | develop-before-KO already covered by concentrate-energy-on-wincon for evolved benched wincons; here the bench  |
| `82752045-97` | 0 | mega_starmie | misattachment | Attach Basic {W} Energy → Mega Starmie | Attach Ignition Energy → Mega Starmie  | concentrate-energy-on-wincon: agent attaches Basic to the most-built benched Mega over the bare one; recorded  |
| `82754241-41` | 0 | mega_starmie | wasted_resource | Play Crushing Hammer | Attack with Turbo Flare | play-energy-denial: wasted-Crushing-Hammer blunder resolved - Pilot no longer plays the Hammer, takes a KO att |
| `82754875-8` | 0 | mega_starmie | wasted_resource | Play Mega Signal | Play Lillie's Determination | agent tutors the win-condition via Mega Signal (53: fetch-when-it-fills-a-need + tutor-the-wincon); bulk-draw- |
| `82756664-74` | 0 | mega_starmie | wasted_resource | Play Hilda | Attach Ignition Energy → Mega Starmie  | Value-model / dig-before-commit: real Pilot plays Hilda (informative tutor +20) then attaches same turn (attac |
| `82866415-43` | 0 | mega_starmie | wasted_resource | Play Lillie's Determination | Attach Hero’s Cape → Mega Starmie ex ( | deploy-hp-tool + hold-irreplaceable-tool-dont-shuffle deploy the Cape (tier-2) and suppress Lillie's (-30); ag |
| `83007714-7` | 0 | mega_starmie | misattachment | Attach Basic {W} Energy → Staryu (benc | Attach Ignition Energy → Cinderace (ac | FIXED in the real Pilot by the new prefer-active-attach-in-setup (+8): energy now goes to the ACTIVE Cinderace |
| `83053965-32` | 0 | mega_starmie | misattachment | Attach Basic {W} Energy → Cinderace (a | Attach Basic {W} Energy → Mega Starmie | Planner ko_for_prizes line executes the human's exact intent: real Pilot decide()->[3] Retreat, planned='retre |
| `83116081-17` | 0 | mega_starmie | slow_setup | Play Harlequin | Play Lillie's Determination | Value-model judgment (contradictory pair): correct wants Lillie's over Harlequin (both score 28, tie), but the |
| `83116501-89` | 0 | mega_starmie | misattachment | Attach Basic {W} Energy → Mega Starmie | Attach Ignition Energy → Mega Starmie  | Fixed this round via the _priority_wincon_slot doomed-active skip: with the Active doomed (70HP Mega, 1e), the |
| `83456015-47` | 0 | mega_starmie | wrong_supporter | Play Lillie's Determination | Play Wally's Compassion | per human ack 2026-07-03: the intended Wally's->Ignition->Nebula sequence belongs to turn 8's PRE-ATTACH decis |
| `83661649-54` | 0 | mega_starmie | sequencing_error | Attack with Jetting Blow | Attach Basic {W} Energy → Mega Starmie | _wins_now fix (gate on active_can_ko): Jetting Blow's KO-class score was a 1-prize BENCH snipe (20HP Staryu),  |
| `85046350-45` | 0 | dragapult_ex | sequencing_error | Play Lillie's Determination | Play Poké Pad | CRITICAL: real Pilot decide()=[2]=Play Poké Pad=correct, deterministic 5/5 (gamble_lines ON default). The reco |
| `85058051-4` | 0 | mega_lucario | wasted_resource | Attach Air Balloon → Solrock (active · | Play Ultra Ball | wasted_resource 'no plan to retreat solrock, waste (Air Balloon on Solrock)': the flagged waste is COVERED. re |
| `83661652-3` | 2 | mega_lucario | wasted_resource | Meowth ex | Meowth ex | FIXED on investigation (not a mislabel): the Pilot literally could not DECLINE an optional single-pick (decide |
| `82523164-55` | 3 | mega_starmie | bad_target | Centiskorch | Dwebble | gust-snipe-synergy: drags the 70HP Dwebble so the 50 snipe finishes the 20HP one (2 prizes); recorded correct  |
| `83661652-31` | 7 | mega_lucario | wasted_resource | Riolu | Mega Lucario ex | Root is the f30 discard (now prevented by keep-line-base-at-discard): with Riolu no longer pitched, the discar |
| `83661652-30` | 8 | mega_lucario | sequencing_error | Riolu, Makuhita | Lillie's Determination | CRITICAL 'dont discard our main line attacker': keep-line-base-at-discard covers it — real Pilot decide() at t |

## Tier C — never reviewed (55)

No blunder round has looked at these. They are the fresh signal, and the `MAIN` bulk of them (46) is
the Turn Planner's domain — Issue #165 — where a decision is a whole-turn maneuver whose value is the
END state, not a single option's score. Expect a meaningful share to be *planner* frames rather than
scorer frames; the hand-off's own note about `82756021-57` is the warning that per-leg reasoning does
not always survive contact with the planner.

Ranked by category above: `wasted_resource` (37 across all tiers) and `sequencing_error` (24) are the
two that dominate, and both are shapes a turn-level planner addresses more naturally than a leaf
weight does.
| frame | ctx | agent | category | agent played | human ruled |
|---|---|---|---|---|---|
| `82522698-36` | 0 | mega_starmie | sequencing_error | Play Harlequin | Attach Basic {W} Energy → Mega Starmie |
| `82523811-84` | 0 | mega_starmie | wasted_resource | Play Salvatore | Attach Basic {W} Energy → Mega Starmie |
| `82523811-93` | 0 | mega_starmie | sequencing_error | Play Harlequin | Attach Basic {W} Energy → Mega Starmie |
| `82525101-110` | 0 | mega_starmie | wasted_resource | Play Salvatore | Attach Basic {W} Energy → Mega Starmie |
| `82525741-78` | 0 | mega_starmie | wasted_resource | Play Buddy-Buddy Poffin | Evolve: Mega Starmie ex |
| `82749168-88` | 0 | mega_starmie | sequencing_error | Play Pokégear 3.0 | Attack with Nebula Beam |
| `82751468-57` | 0 | mega_starmie | missed_disruption | Play Salvatore | Play Boss’s Orders |
| `82752045-18` | 0 | mega_starmie | wasted_resource | Play Hilda | Attack with Turbo Flare |
| `82752045-94` | 0 | mega_starmie | wasted_resource | Play Lillie's Determination | Attack with Nebula Beam |
| `82753102-109` | 0 | mega_starmie | slow_setup | Play Boss’s Orders | Attack with Nebula Beam |
| `82754241-12` | 0 | mega_starmie | sequencing_error | Play Buddy-Buddy Poffin | Play Ultra Ball |
| `82756664-35` | 0 | mega_starmie | misattachment | Attach Basic {W} Energy → Staryu (benc | Attach Basic {W} Energy → Mega Starmie |
| `82867148-62` | 0 | mega_starmie | bad_retreat | Retreat | Attack with Turbo Flare |
| `83037962-48` | 0 | mega_starmie | misattachment | Attach Basic {W} Energy → Mega Starmie | Attach Basic {W} Energy → Staryu (benc |
| `83037962-49` | 0 | mega_starmie | misattachment | Play Harlequin | Attack with Jetting Blow |
| `83038055-40` | 0 | mega_starmie | sequencing_error | Play Mega Signal | Play Lillie's Determination |
| `83038055-51` | 0 | mega_starmie | sequencing_error | Play Lillie's Determination | Attack with Nebula Beam |
| `83053965-6` | 0 | mega_starmie | wasted_resource | Attach Ignition Energy → Cinderace (ac | Play Mega Signal |
| `83663053-22` | 0 | mega_starmie | missed_win | Play Pokégear 3.0 | Attack with Jetting Blow |
| `83664340-24` | 0 | mega_starmie | wasted_resource | Play Crushing Hammer | Play Lillie's Determination |
| `83664991-43` | 0 | mega_starmie | sequencing_error | Play Lillie's Determination | Attack with Turbo Flare |
| `83665798-39` | 0 | mega_starmie | missed_win | Play Lillie's Determination | Attack with Jetting Blow |
| `83686860-45` | 0 | dragapult_ex | wasted_resource | Attach Basic {P} Energy → Drakloak (be | Attach Basic {R} Energy → Drakloak (be |
| `83966336-27` | 0 | mega_lucario | slow_setup | Play Team Rocket's Petrel | Play Team Rocket's Petrel |
| `85058574-87` | 0 | mega_lucario | wasted_resource | Attach Air Balloon → Solrock (bench 2  | Attach Air Balloon → Mega Lucario ex ( |
| `85164131-31` | 0 | mega_starmie | wasted_resource | Attack with Jetting Blow | Attack with Nebula Beam |
| `85164605-41` | 0 | mega_starmie | wasted_resource | Play Salvatore | Play Mega Signal |
| `85709280-111` | 0 | mega_lucario | misattachment | Play Judge | Attack with Mega Brave |
| `85709280-17` | 0 | mega_lucario | slow_setup | Attach Basic {F} Energy → Solrock (act | ? |
| `85709280-51` | 0 | mega_lucario | slow_setup | Play Solrock | ? |
| `86088989-4` | 0 | mega_lucario | wasted_resource | Play Makuhita | Play Poké Pad |
| `86089617-4` | 0 | mega_lucario | wasted_resource | Play Premium Power Pro | End turn |
| `86090147-22` | 0 | mega_lucario | wasted_resource | Attach Air Balloon → Meowth ex (active | Retreat |
| `86090147-5` | 0 | mega_lucario | slow_setup | Play Meowth ex | ? |
| `86090164-52` | 0 | dragapult_ex | bad_retreat | Retreat | Evolve Dudunsparce → Dunsparce (bench  |
| `86090164-67` | 0 | dragapult_ex | bad_retreat | Retreat | Evolve Dudunsparce → Dunsparce (bench  |
| `86090164-78` | 0 | dragapult_ex | wasted_resource | Attach Basic {D} Energy → Dragapult ex | ? |
| `86090666-9` | 0 | mega_lucario | wasted_resource | Attach Basic {F} Energy → Riolu (activ | ? |
| `86090676-18` | 0 | dragapult_ex | wasted_resource | Play Crispin | ? |
| `86091172-30` | 0 | mega_lucario | wasted_resource | Attach Basic {F} Energy → Lunatone (ac | ? |
| `86091172-8` | 0 | mega_lucario | wasted_resource | Attach Basic {F} Energy → Lunatone (ac | ? |
| `86091435-13` | 0 | dragapult_ex | wasted_resource | Play Boss’s Orders | Retreat |
| `86091435-60` | 0 | dragapult_ex | sequencing_error | Play Lillie's Determination | Attach Basic {P} Energy → Dreepy (acti |
| `86091435-96` | 0 | dragapult_ex | wasted_resource | Attach Basic {D} Energy → Drakloak (be | Play Lillie's Determination |
| `86091728-12` | 0 | dragapult_ex | sequencing_error | Play Crispin | ? |
| `86091728-19` | 0 | dragapult_ex | sequencing_error | Play Ultra Ball | Attach Basic {P} Energy → Dreepy (benc |
| `85785609-4` | 2 | dragapult_ex | wasted_resource | Munkidori | Munkidori |
| `86091728-43` | 5 | dragapult_ex | wasted_resource | Dunsparce, Dreepy | Budew, Dreepy |
| `84889011-7` | 7 | mega_lucario | wasted_resource | Lunatone | Riolu |
| `86088989-29` | 7 | mega_lucario | wrong_supporter | Judge | Lillie's Determination |
| `86091435-49` | 7 | dragapult_ex | sequencing_error | Basic {P} Energy | ? |
| `86091435-69` | 7 | dragapult_ex | wasted_resource | Fezandipiti ex | Dudunsparce |
| `86091728-47` | 7 | dragapult_ex | wasted_resource | Ultra Ball | Night Stretcher |
| `81905522-75` | 15 | mega_starmie | bad_target | Hariyama | Riolu |
| `85058574-121` | 21 | mega_lucario | wrong_attack | Lunatone (bench 1 · 110/110) | Hariyama (bench 4 · 150/150) — stage t |

## Tier A — `refuted` labels (18) — no fix owed

The Correction itself is wrong. The agent disagreeing with it is the agent being **right**, and a
build that "fixed" one of these would be a regression wearing a `FIX` label.

They still count against the agree rate, which is the one piece of unfinished business in this tier:
**the 230/331 readout is pessimistic by up to 18 frames.** The honest denominator for "is the agent
right" is nearer 230/313. Recording that in the corpus rather than in this file is a Corrections-schema
question — it belongs with ADR-0082's Claim vocabulary and with Issue #229, which is already open on
the neighbouring question of what a Correction may record.

Three of the 18 also cite a deleted rung in their refutation note (`82525741-81`
`build-active-wincon`, `82867148-87` `dont-waste-discard-energy`, `85058574-114` `attach-energy-last`).
They are listed here rather than in Tier B because a refuted label owes no fix either way — but if
Tier B's deleted-rung finding turns out to be real, these three are worth re-reading, since their
refutation rests on the same vanished premise.

One of these is a snipe RECORDED MISS — `82749168-38`, whose refutation note *is* ADR-0085 decision
7's ruling. Its sibling `81905522-75` (the two-identical-Riolu transposition) is equally ruled and
equally permanent, but lands in **Tier C** below because the ruling lives in the ADR and in
`snipe_decider_sweep.py`'s `RECORDED_MISSES`, never in `reviewed.json`. That split is worth noticing:
a frame can be thoroughly ruled and still read as "never reviewed" here, because this triage keys on
one store and the project rules frames in several. Tier C is a *starting* list, not a backlog.
| frame | ctx | agent | category | agent played | human ruled | review note |
|---|---|---|---|---|---|---|
| `81904451-37` | 0 | mega_starmie | sequencing_error | Attack | Play Hilda | forgoes a KO (tactical ~1000) — over-eager; a positional rule must never override a Knock Out |
| `81905522-64` | 0 | mega_starmie | sequencing_error | Attack | Attach Basic {W} Energy → Staryu | forgoes a 209-damage attack — over-eager |
| `81906755-93` | 0 | mega_starmie | sequencing_error | Attack | Attach Basic {W} Energy → Staryu | forgoes a KO (tactical ~1000) — over-eager |
| `82524455-6` | 0 | mega_starmie | wasted_resource | Play Buddy-Buddy Poffin | Attach Basic {W} Energy → Staryu | Requires deck-content certainty (no Staryu left in deck) not soundly derivable from one obs: only 1 of 3 Stary |
| `82525741-58` | 0 | mega_starmie | wasted_resource | Play Boss’s Orders | Attach Basic {W} Energy → Mega Starmie | Chosen Boss's Orders reaches a guaranteed KO (gust-for-the-ko fires: gust_best_ko_prizes 1 > active_ko_prizes  |
| `82525741-81` | 0 | mega_starmie | misattachment | Attach Basic {W} Energy → Mega Starmie | Attach Basic {W} Energy → Mega Starmie | Mis-tagged: correct [2] == chosen [2] (both attach {W} to bench0) — structurally unsatisfiable (no ranking con |
| `82753102-9` | 0 | mega_starmie | sequencing_error | Attach Ignition Energy → Cinderace (ac | Play Pokégear 3.0 | forgo-KO: the Ignition->Mega attach is LETHAL (_attach_lethal_tactical 1041 = KO-class; Ignition CCC unlocks N |
| `82756664-36` | 0 | mega_starmie | sequencing_error | Play Lillie's Determination | Attach Hero’s Cape → Mega Starmie ex ( | forgo-KO: agent retreats into a ready benched attacker that KOs (retreat-to-lethal 1061); the recorded Hero's  |
| `82756664-9` | 0 | mega_starmie | sequencing_error | Play Lillie's Determination | Attach Hero’s Cape → Staryu (bench 1 · | ADR-0028 tradeoff ACCEPTED (2026-07-01, retested through the real Pilot): the original shuffle-away blunder IS |
| `82867148-87` | 0 | mega_starmie | bad_retreat | Attach Basic {W} Energy → Cinderace (b | Attach Ignition Energy → Staryu (bench | literal Ignition->Staryu dominated by reusable Water->Staryu (dont-waste-discard-energy soundly avoids wasting |
| `83661652-19` | 0 | mega_lucario | wrong_supporter | Play Boss’s Orders | Attach Basic {F} Energy → Lunatone (ac | wrong-seat / non-doctrine attacker (user ruling 2026-07-22): the correct line 'attach {F} to Lunatone, attack  |
| `83662396-19` | 0 | mega_starmie | sequencing_error | Attack with Turbo Flare | Play Mega Signal | forgo-KO: Turbo Flare is a KO (tac 1000.9, weakness) on the 70HP opp Active; Mega Signal is ALSO a redundant t |
| `83966968-78` | 0 | mega_starmie | wrong_supporter | Play Boss’s Orders | Play Harlequin | CRITICAL refuted (human ack 2026-07-09): Boss's->gust Cinderace is the only KO; Harlequin forgoes it. test_blu |
| `85058574-114` | 0 | mega_lucario | wrong_attack | Play Poké Pad | Attach Basic {F} Energy → Mega Lucario | CRITICAL, human-acknowledged 2026-07-10. Spec does not survive the board: the Bench IS full (5), but Poke Pad  |
| `86091435-119` | 0 | dragapult_ex | wrong_supporter | Play Boss’s Orders | Play Night Stretcher | refuted-by-better-line (human ack 2026-07-19, gusting grill): the ADR-0066 widened bench oracle finds gust-Dur |
| `83966968-79` | 3 | mega_starmie | bad_target | opp Cinderace (bench 1 · 110/160) | opp Mega Starmie ex (bench 2 · 230/330 | CRITICAL refuted (human ack 2026-07-09): benched Mega Starmie ex 230/330 un-KO-able (max 210<230, Nebula unaff |
| `86091435-68` | 8 | dragapult_ex | wasted_resource | Drakloak, Lillie's Determination | Lillie's Determination, Crushing Hamme | user re-review 2026-07-19 (seam-D shadow evidence): the recorded correct [Lillie's + Crushing Hammer] mis-spec |
| `82749168-38` | 15 | mega_starmie | bad_target | opp Hoothoot (bench 2 · 70/70) | opp Dragapult ex (bench 1 · 320/320) | correct=[0] snipes the benched Dragapult ex, a [Tera] ex that takes NO attack damage while Benched (data/EN_Ca |

## Reproducing this

The disagreement set is whatever the committed baseline says it is:

```bash
python tools/train/decider_lab.py diff --baseline data/decider_lab/baseline.json
```

The per-context agree lines in that output are this document's top table. The tiers come from joining
`data/decider_lab/baseline.json` (`rows[].key`, `chosen`, `correct`) to `data/corrections/reviewed.json`
(`disposition`) on `<episode>-<frame>`, and the labels from the `data/corrections/*/corrections.jsonl`
records. Agreement is `gates.satisfies_human`, never `==` — see ADR-0085 Amendment J.

**When the baseline is re-captured, this document goes stale.** It is a reading of one capture
(`e50735a`, 332 frames, 2026-07-30), not a standing truth.
