"""The retirement ledger: every deleted Hypothesis id that `src/` prose still names, and where to read why.

A rung that is folded into an equation stops existing as an `id=`, but the prose that named it does not
follow it out. The 2026-08-07 documentation audit found that to be the single most common defect in the
repo: comments asserting that a `Board` field "gates `promote-the-powered-attacker`" when no such
Hypothesis has existed since ADR-0100, or that a line "gets `_HAND_SIZE_ATTACKER_BOOST`" when the
constant was deleted by Issue #213. A reader believes it, and builds against a scoring layer that is gone.

`tests/test_retired_rung_ids.py` is the guard. Every backticked kebab-case token in `src/**/*.py` must be
either a live string in `src/`, or a key here. A NEW dead reference fails the suite; nothing else in the
repo notices one today.

The value is the pointer, not the prose. Each entry names the module whose FOLD MAP explains where the
logic went — `baseline_energy.py` for the nineteen attach rungs, `baseline_promote.py` for the seven
promote rungs, and so on. Those fold maps are maintained beside the code they describe, so this ledger
stays a one-line redirect rather than a second copy that can rot on its own.

Two things this ledger is NOT:

* **Not an amnesty.** An entry records that a dead id is *mentioned*, not that the mention is correct.
  Many seeded entries are exactly the false claims the audit found — prose asserting a retired rung
  still fires. Those are defects to delete during the reduction pass, and deleting them shrinks this
  ledger, which is the intended direction of travel.
* **Not shipped.** It lives in `tests/` deliberately. `src/common/` is packaged into every Kaggle
  submission (ADR-0004), and a retirement record is build-time history, not runtime data.

Seeded 2026-08-07 with the 81 ids then referenced across 202 sites. `MAX_RETIRED` below is a ratchet: it
may be lowered, never raised.

Prior art for the shape: `tests/test_adr_index.py` carries its one known gap as data with its reason
rather than as a silence, for the same purpose — so that a NEW instance fails instead of joining a
backlog nobody is counting.
"""
from __future__ import annotations

#: Retired Hypothesis id -> the module whose fold map / retirement note explains where the logic went.
#: Add an entry ONLY when the mention is a deliberate tombstone; prefer deleting the stale prose.
RETIRED: dict[str, str] = {
    "advance-the-accel-pieces":
        "src/common/strategy/planner.py",
    "advance-the-evolution-line":
        "src/common/strategy/baseline/baseline_evolution.py",
    "arm-the-doomed-active":
        "src/common/pilot.py",
    "attach-energy-last":
        "src/common/pilot.py",
    "aurajab-skip-partnerless-solrock":
        "src/agents/mega_lucario/strategy.py",
    "bench-fill-a-basic":
        "src/common/strategy/doctrines/doctrine_fetch.py",
    "bench-the-supporter-tutor":
        "src/common/strategy/baseline/baseline_sequencing.py",
    "build-active-wincon":
        "src/common/pilot.py",
    "concentrate-accel-on-one-line-body":
        "src/agents/mega_lucario/strategy.py",
    "concentrate-energy-on-wincon":
        "src/agents/mega_lucario/strategy.py",
    "conserve-burst-when-no-ko":
        "src/common/pilot.py",
    "conserve-discard-energy-prefer-basic":
        "src/common/pilot.py",
    "deck-personality-reactivity":
        "src/common/strategy/planner.py",
    "develop-a-basic-in-setup":
        "src/common/currency.py",
    "develop-the-accel-recipient":
        "src/agents/mega_lucario/strategy.py",
    "develop-the-wincon-base-first":
        "src/agents/dragapult_ex/strategy.py",
    "discard-the-dead-opener":
        "src/common/pilot.py",
    "discard-the-hand-duplicate":
        "src/common/strategy/doctrines/doctrine_fetch.py",
    "discard-the-redundant":
        "src/common/strategy/doctrines/doctrine_fetch.py",
    "discard-the-redundant-tutor":
        "src/common/pilot.py",
    "disrupt-when-unfavored":
        "src/common/strategy/baseline/baseline_disruption.py",
    "dont-bench-multiprize":
        "src/agents/dragapult_ex/strategy.py",
    "dont-bench-onto-their-path":
        "src/common/pilot.py",
    "dont-feed-the-doomed":
        "src/common/pilot.py",
    "dont-fund-the-non-attacking-body":
        "src/agents/mega_lucario/strategy.py",
    "dont-open-multiprize-active":
        "src/common/strategy/baseline/baseline_opening.py",
    "dont-open-with-the-engine":
        "src/common/strategy/baseline/baseline_opening.py",
    "dont-pre-bench-a-redundant-utility":
        "src/common/strategy/doctrines/doctrine_fetch.py",
    "dont-pre-bench-the-supporter-tutor":
        "src/common/strategy/doctrines/doctrine_fetch.py",
    "dont-promote-into-their-prize-reach":
        "src/common/strategy/baseline/baseline_promote.py",
    "dont-promote-onto-their-path":
        "src/common/strategy/baseline/baseline_promote.py",
    "dont-refresh-for-nothing":
        "src/common/strategy/doctrines/doctrine_shuffle_refresh.py",
    "dont-shuffle-away-the-bigger-hand":
        "src/common/strategy/baseline/baseline_disruption.py",
    "dont-snipe-a-benched-tera":
        "src/common/pilot.py",
    "dont-waste-discard-energy":
        "src/agents/mega_starmie/strategy.py",
    "dont-waste-off-type-energy":
        "src/common/pilot.py",
    "evolve-into-wincon":
        "src/common/strategy/baseline/baseline_evolution.py",
    "evolve-the-energized-body-first":
        "src/common/pilot.py",
    "feed-the-firing-accelerator":
        "src/common/strategy/planner.py",
    "fetch-the-engine-first":
        "src/common/strategy/doctrines/doctrine_fetch.py",
    "grab-a-draw-supporter-in-setup":
        "src/common/strategy/doctrines/doctrine_fetch.py",
    "grab-what-i-can-play-now":
        "src/common/pilot.py",
    "gravity-mountain-vs-stage2":
        "src/agents/mega_lucario/strategy.py",
    "heal-and-stall":
        "src/common/strategy/planner.py",
    "hold-evolution-until-attacker-ready":
        "src/common/strategy/baseline/baseline_evolution.py",
    "hold-irreplaceable-tool-dont-shuffle":
        "src/common/strategy/doctrines/doctrine_tool.py",
    "hold-line-piece-dont-shuffle":
        "src/common/strategy/doctrines/doctrine_shuffle_refresh.py",
    "hold-position-in-setup":
        "src/common/strategy/baseline/baseline_retreat.py",
    "hold-wincon-with-base-dont-shuffle":
        "src/common/strategy/doctrines/doctrine_shuffle_refresh.py",
    "interpose-the-cheap-attacker-to-preserve-the-wincon":
        "src/common/strategy/baseline/baseline_promote.py",
    "keep-a-bench":
        "src/common/strategy/baseline/__init__.py",
    "keep-engine-supporter-at-discard":
        "src/common/pilot.py",
    "keep-gust-and-recovery-at-discard":
        "src/common/card_worth.py",
    "keep-key-cards-at-discard":
        "src/common/strategy/doctrines/doctrine_fetch.py",
    "never-fetch-cinderace":
        "src/common/strategy/doctrines/doctrine_fetch.py",
    "open-the-accelerator":
        "src/common/strategy/baseline/baseline_opening.py",
    "open-the-item-lock-starter":
        "src/common/strategy/doctrines/doctrine_fetch.py",
    "play-energy-denial":
        "src/common/strategy/baseline/baseline_disruption.py",
    "play-harlequin-vs-hand-size":
        "src/common/strategy/baseline/baseline_disruption.py",
    "power-up-attacker":
        "src/common/strategy/doctrines/doctrine_fetch.py",
    "pre-position-attacker":
        "src/agents/mega_lucario/strategy.py",
    "prefer-going-second":
        "src/common/strategy/baseline/baseline_opening.py",
    "promote-the-accelerator-for-the-ko":
        "src/common/strategy/baseline/baseline_promote.py",
    "promote-the-ko-attacker":
        "src/common/strategy/baseline/baseline_promote.py",
    "promote-the-powered-attacker":
        "src/common/pilot.py",
    "promote-the-ready-wincon":
        "src/common/strategy/baseline/baseline_promote.py",
    "promote-the-staller":
        "src/common/strategy/baseline/baseline_promote.py",
    "refresh-when-hand-is-dead":
        "src/common/strategy/doctrines/doctrine_shuffle_refresh.py",
    "retreat-to-ready-attacker":
        "src/common/strategy/baseline/baseline_retreat.py",
    "risk-scales-with-prize-position":
        "src/common/strategy/baseline/baseline_posture.py",
    "snipe-for-the-ko":
        "src/common/strategy/baseline/baseline_snipe.py",
    "snipe-on-the-path":
        "src/common/strategy/baseline/baseline_snipe.py",
    "snipe-the-evolving-threat":
        "src/common/strategy/baseline/baseline_snipe.py",
    "snipe-the-forced-promotion":
        "src/common/strategy/baseline/baseline_snipe.py",
    "snipe-the-threat":
        "src/common/strategy/baseline/baseline_snipe.py",
    "snipe-the-top-threat":
        "src/common/strategy/baseline/baseline_snipe.py",
    "spread-attach-to-the-needy":
        "src/agents/mega_lucario/strategy.py",
    "start-solrock-over-lunatone":
        "src/common/strategy/baseline/baseline_opening.py",
    "strip-the-stacked-engine-hand":
        "src/common/strategy/baseline/baseline_disruption.py",
    "swap-out-the-locked-attacker":
        "src/common/strategy/baseline/baseline_retreat.py",
    "tutor-the-wincon":
        "src/common/strategy/doctrines/doctrine_fetch.py",
}

#: Ratchet. Lower it as the reduction pass deletes stale mentions; never raise it.
MAX_RETIRED = 81
