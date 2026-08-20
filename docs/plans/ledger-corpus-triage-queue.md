# Ledger corpus triage queue — DEFERRED

Saved 2026-08-20 during the ledger tuning-round planning session (dashboard @ `3c2d4399`).
These 40 corpus entries cannot be graded as rulings and are set aside for a later sitting.
Until then they still count as misses in `tools/train/ledger_corpus.py` output. The doctrine
conflict at the bottom is also deferred by the owner's decision.

## Empty ruling `[]` — no correct action recorded (33)

The grader treats `correct == []` as "declining was correct", so any chosen action grades
as a miss. Six of these have rationales that PRAISE the chosen move. Each needs either a
real ruling, `correct = chosen`, or a `reviewed.json` disposition.

dragapult_ex: 86090164-78, 86090676-18, 86091435-49, 86091728-12
mega_lucario: 85709280-17, 86090147-5, 86090666-9, 86091172-30, 86091172-8
mega_starmie: 160106599249705-8, 26001818654643-18, 26001818654643-31 (praise),
26001818654643-44, 26001818654643-49 (praise), 26001818654643-58 (praise),
26001818654643-72 (praise; DUPLICATE id, see below), 26001818654643-76 (praise),
91394270-85, 92091149-14, 92091149-60, 92102433-10, 92104376-7, 92104376-81,
92131448-22, 92131448-8, 92455378-89, 92457318-44, 92459166-92, 92645419-116,
92708809-35, 92708809-42, 92708809-57, 92711683-19

## Investigation notes, not rulings (3)

- dragapult_ex 85785609-4 — "This is odd" setup-bench note; also contradicts itself.
- mega_starmie 92591287-73 — evolve priced −0.4158 vs decline −0.1320 (inverted); bug note.
- mega_starmie 92710760-56 — "Something happened here causing us to freeze"; bug report.

## Ruling contradicts its own rationale (3)

- mega_lucario 83661652-3 — ruling plays Meowth ex; rationale says avoid playing Meowth at setup.
- mega_starmie 81906131-25 — ruling attaches Ignition; rationale says never attach Ignition here.
- mega_starmie 83664991-43 — ruling is the attack; rationale calls it "a perfect time to play Harlequin".

## Ruling says it hardly matters (1)

- dragapult_ex 86091435-13 — "doesnt really make a difference".

## Data bug to fix alongside

- `mega_starmie 26001818654643-72` appears TWICE in the dashboard with contradictory entries
  (one praise + ruling `[]`, one ruling `[5]` calling the turn nonsensical). The store dedupes
  by Scope subject, so two records share a subject or the dedupe misses; find and fix.

## Footnote — graded but noisy rationales (4, stay in the corpus)

86090164-67, 91394270-12, 92458248-23, 92591287-35 carry valid rulings whose rationales are
investigation notes; they stay graded, flagged here for context only.

## Doctrine conflict — DEFERRED by owner 2026-08-20

"Fully load one attacker" vs "spread the energy a little" on mega_starmie. Concentrate side:
85046350-85 (dragapult), 82752045-97, 83116501-89, 82756664-35, 26001818654643-72 (second
entry). Diversify side: 92645419-25 ("i would diversify energy a little by placing 2 energy
on one staryu and one on another"). Any single pricing rule fails one side; no tuning target
until the owner rules the doctrine.
