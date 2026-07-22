# Snipe-targeting grill (#3) — scope finding (handoff, 2026-07-22)

**For a session picking up snipe grill #3** (`valuation-systems-coverage-review.md` ranked #3;
companion: `turn-planner-snipe-and-gust-scenarios.md` §A). This handoff **re-scopes #3** after a
full corpus sweep + live retests on `origin/main` (post gust-value merge, PR #128). The headline:
**the role-ranking layer is already solved; the only live gap is the threshold-race.**

## What was swept

All **23 `Damage`-context (snipe-target) disagreements** in the corrections corpus (chosen ≠ correct),
each retested through the shipped Pilot (`tools/train/retest_one.py <agent> <ep>-<frame>`).

## Finding 1 — every no-KO ROLE read already passes on main

The role-ranking rungs in `baseline_snipe.py` (`snipe-the-top-threat` +30 / `snipe-the-threat` +20 /
`snipe-the-evolving-threat` +45 / `snipe-the-forced-promotion` +40 / `snipe-on-the-path` +12),
reading `_target_energy` / `_target_forward_damage`, correctly handle **every** no-KO role pick:

| frame | no-KO role read | main |
|---|---|---|
| `82756664-103` | Solrock → Mega Lucario ex 290 (5⚡) | ✓ |
| `82756021-57` | Makuhita → Mega Lucario ex 340 (1⚡) | ✓ |
| `82752604-62` | Dreepy → Drakloak 90 (1⚡, evolving) | ✓ |
| `82523811-41/61` | Makuhita → Riolu (Mega Lucario pre-evo) | ✓ |
| `85164131-22` | Cinderace 260 → Staryu 70 (answerable body ignored) | ✓ |
| `82225138-46` | Kangaskhan wall → Dwebble (weak over wall) | ✓ |
| `82753102-85` · `81785223-28` · `82224509-47` · `85164605-48/68` | main-attacker / energized / snipe-KO | ✓ |

**⇒ the role-ranking layer needs no new anchor.** The coverage-doc line "Snipe ⚠️ 16/19, three known
misses" overcounts: the "already-evolved printed damage" miss (`82749168-38`) is refuted (Tera-benched
immunity), and the role reads all pass.

## Finding 2 — the only LIVE no-KO snipe failure is the threshold-race

Filtering the 23 to what still fails on main:
- **`83667237-107`** — the **threshold-race** (the sole live gap). Pilot takes an on-path body
  (`snipe-on-the-path` +12); Makuhita scores **0**. This is a **multi-turn race computation**, not a
  single-turn role rank: over my setup window, prefer the snipe that puts a body under my finisher's
  KO threshold (here: Makuhita 80 dies to 50+50 over 2 Jetting Blow turns, gated on "if they don't
  evolve it"; the opp discard `{F}` is a *risk* — it lets them evolve out — not a threat gauge). See
  the coverage-review "Opponent-read grill findings (2026-07-22)" for the full user ruling.
- `81905522-75` — pure two-identical-Riolu **transposition** (unfixable by any value term).
- everything else — refuted (`82749168-38`) or KO-settled (`snipe-for-the-ko` +60).

## Re-scoped #3 — build target

**Threshold-race only.** One live corpus anchor (`83667237-107`) + the described-but-uncaptured
`ep83037962-49` case (a play/attack frame, not a snipe-select — needs a captured follow-up frame or a
grilled synthetic). Signals: `my_snipe_per_turn × turns_to_finisher ≥ target_hp`, an **evolve-out
veto** (discount a pre-evo whose evolution lifts it out of range — the discard-`{F}` read is the risk
input here), and prize-plan relaxation of the redundant guard with the chip **banked for a later
gust-KO** (ties to the gust-value equation, built separately). Root cause is the shared
`strongest_threat_rank` + prize-guard machinery (the 16 passing frames ride it) — grill frame-by-frame,
then a `snipe_sweep` bench (the 23 DAMAGE frames; hold the role reads, fix the ruled threshold-race).
**Do NOT blind-build.**
