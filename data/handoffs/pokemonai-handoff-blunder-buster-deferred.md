# Handoff — improve the `blunder-buster` skill so "deferred" stops being a dumping ground

**Repo:** `C:\Users\Richard\Projects\PokemonAI`
**Next session's task (user's words):** *"update the blunder-buster skill such that it does[n't] keep
leaving unfinished business and stating it as deferred."*
**Date:** 2026-06-28.

## The problem the user is naming
Across this session's blunder-busting on `mega_starmie`, the process repeatedly **punted corrections to
the reviewed ledger as `deferred`** with reasons like "needs Posture / threat-identity / forward-evo /
hand-quality eval / Tier-1 combat lookahead." That's ~10 corrections now sitting in
`data/corrections/reviewed.json` as `deferred`, plus more about to be added. The user's concern: this
is a quiet backlog of unfinished business that gets *named* ("deferred") but never *tracked to done* —
the skill makes deferring too easy and too forgettable.

**The job is to revise the skill (and maybe the ledger/tooling) so a `deferred` is accountable, not a
silent drop.** Confirm the exact desired behavior with the user first — design options below.

## Where it all lives
- **Skill to edit:** `C:\Users\Richard\Projects\PokemonAI\.claude\skills\blunder-buster\SKILL.md`
  — **step 10 "Record what you set aside"** defines the `refuted` / `deferred` / `covered` dispositions.
  `deferred` = "valid but needs new infrastructure; note what's missing." That instruction is the
  thing that's too loose.
- **Ledger:** `data/corrections/reviewed.json` (CLI `tools/train/review_correction.py`, `--list`).
  Loader/partition: `tools/train/blunder/reviewed.py`. `tune.py` already prints a
  `reviewed (excluded): … deferred N` summary each run, so the data is surfaced — just not *actioned*.
- **Roadmap the deferrals map to:** `docs/todo/roadmap-search-posture-learning.md` (M0 forward-evo
  signal, M2 Posture, M3 Tier-1 search, …). Most deferrals are really "blocked on milestone Mx."
- **Method doc** (keep in sync if you change the method): `docs/tuning/methodology.md`.
- **Memory** (`C:\Users\Richard\.claude\projects\C--Users-Richard-Projects-PokemonAI\memory\`):
  `reviewed-ledger.md`, `old-build-real-pilot-backlog.md`, `attack-is-turn-ender-develop-first.md`.

## The deferred items today (the pattern to design against)
Run `python tools/train/review_correction.py --list` for the live set. They cluster by the infra they
wait on — and almost all map to an existing roadmap milestone:
- **Forward-evolution-threat signal (M0):** e.g. `81905522-75`, `82224509-46/47`.
- **Posture / opponent-archetype + threat-identity (M2):** `82224509-56/67`, `82225643-12`,
  `82226759-64`, `82229122-45`.
- **Tier-1 search / combat lookahead (M3):** `82228640-25` (Ignition-vs-basic: does the cheap attack
  suffice?).
- **Hand-quality eval (NOT clearly on the roadmap — a gap):** `82228017-4`, `82224509-71`,
  `82228640-7` (save a wasteful tutor/search when the target is already in hand).

Observation to hand the user: deferrals aren't random — they bucket into ~4 capabilities, 3 of which
are already roadmap milestones. That's the lever for making "deferred" accountable.

## Design options for the skill change (discuss with user, then implement)
1. **Require a milestone link.** A `deferred` MUST cite a concrete milestone id from
   `docs/todo/roadmap-search-posture-learning.md` (or the author must add a new milestone). No vague
   "needs X someday." Encode the milestone in the ledger entry (e.g. add a `blocked_on: "M2"` field).
2. **Reverse index / "unblock on landing."** When a milestone lands, there should be a one-command way
   to list the deferred ids it unblocks and re-surface them as work (e.g. `review_correction.py
   --blocked-on M2`). Add the field + a query.
3. **Recurring deferred audit.** Add a step to the skill: each round, review the deferred bucket and
   re-test any whose blocking infra now exists (real Pilot `decide()`), promoting them back to active.
4. **Raise the bar to defer.** Prefer authoring a partial/heuristic rule (or marking `covered` when
   attack-last/tiered already handles it) over `deferred`; only defer when genuinely impossible now.
5. **Surface, don't bury.** `tune.py` already prints the deferred summary; make the skill *act* on it
   (e.g. fail-loud if the deferred count grew without a milestone link).

My read: the user most wants **(1) + (2) + (3)** — deferrals become tracked, milestone-linked items
with a built-in path back to "done," so the backlog can't silently grow. The "hand-quality eval"
bucket has no milestone yet — flag that it likely needs a new roadmap entry.

## Session history (context; don't re-do)
Big round just completed on build `mega_starmie_20260627_93a70be`: the **attack-last → tiered
turn-sequencer** rebuild + sub-clusters (develop before the turn-ending attack; tier0 dev → tier1
energy attach → tier2 attack), plus snipe-the-weakest, 3-way promote doctrine, retreat-to-ready-
attacker, save-tool, fetch/promote-the-line; **removed** the now-obsolete `build-before-attack` /
`dont-chip` rules. Real-Pilot corpus 43/57, 0 regressions, 422 tests, adversarial-reviewed. User
**submitted agent #4**. Full narrative: `docs/tuning/runs/mega_starmie_20260628-170304.md`.
Key insight baked in: **the real Pilot `decide()` / Verifier is the authoritative fix-measure, not the
tuner's additive W-route** (it over-reports both ways).

**Loose end from the prior /handoff** (separate doc
`C:\Users\Richard\AppData\Local\Temp\pokemonai-handoff-old-build-backlog.md`): the 11 old-build
corrections were triaged (all soft-ordering/deferred-family, none a current blunder) but **not yet
ledgered** — pending user confirmation to close them out (8 `covered`, 3 `deferred`). NB: closing those
will *add 3 more `deferred`* — which is exactly the behavior the user now wants to fix, so consider the
skill change first, or apply the new deferral discipline when ledgering them.

## Standing constraints
- **Caveman-lite** chat (~75%); end every response with a status line (`Done - Still grilling` /
  `Grilling Done` / `Done - Still implementing` / `Implementing Done`).
- **User is the commit gate** — don't commit/push unless asked. Never touch the Kaggle token.
- Editing the skill = editing process: keep `docs/tuning/methodology.md` and memory `reviewed-ledger.md`
  in sync if the disposition mechanics change. If you add a ledger field, update
  `tools/train/blunder/reviewed.py` + `review_correction.py` + `tests/test_reviewed_ledger.py`.
- Windows + Linux first-class (`pathlib`, `encoding="utf-8"`, `PYTHONIOENCODING=utf-8` for the
  `→`/curly chars on Windows). Python docstrings Google style.

## Suggested skills
- **None to auto-invoke.** This is a meta task (editing the `blunder-buster` skill + its tooling), not a
  blunder-busting round — do NOT run `/blunder-buster` here. Edit `SKILL.md` directly and, if the
  disposition schema changes, the ledger tooling + tests above. Pull up the roadmap doc to wire the
  milestone-link option.
