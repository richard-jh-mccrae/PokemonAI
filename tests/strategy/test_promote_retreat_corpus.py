"""Promote/retreat value oracle — CORPUS validation (common/promote_retreat_value.py).

End-to-end proof that the SHADOW, wired through the live Pilot on real boards, RANKS the human-tagged
correct promote/retreat option highest. Fixtures are the frames walked in the grill
(docs/plans/promote-retreat-grill-spec.md §Round-0). While the oracle is REPORTING-ONLY these are the
design proof the swap gate will consume; card facts verified at source.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"

_PROMOTE_CTX = (3, 4)   # _SWITCH / _TO_ACTIVE — every option is a promote/retreat body


def _pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _shadows(agent: str, fixture: str):
    fx = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
    d = _pilot(agent).explain(fx["obs"])
    assert fx["obs"]["select"]["context"] in _PROMOTE_CTX, fx.get("note")
    shadow = {i: t.promote_retreat_shadow for i, t in enumerate(d.options)}
    return fx, shadow


def test_shadow_promotes_the_accelerator_f120():
    """82753102-120 (TO_ACTIVE): the 1-prize accelerator that CAN act (Cinderace) out-ranks the empty
    line piece (Staryu) — readiness carries it, on band value alone (ruling 4: no speculative win)."""
    fx, shadow = _shadows("mega_starmie", "pr_promote_accelerator_f120")
    assert max(shadow, key=shadow.get) == fx["correct"][0], shadow


def test_shadow_promotes_the_ready_wincon_f104():
    """83007714-104 (TO_ACTIVE): two same-prize Mega Starmie ex; the ready 3-Energy Hero's-Cape copy
    out-ranks the empty one on pure `can_attack_now` readiness (the first-bench-slot-blindness fix)."""
    fx, shadow = _shadows("mega_starmie", "pr_promote_ready_wincon_f104")
    assert max(shadow, key=shadow.get) == fx["correct"][0], shadow


def test_shadow_retreats_into_the_ready_wincon_f92():
    """83007714-92 (SWITCH): retreat into the 3-Energy Hero's-Cape Mega (the KO-ready wincon) over the
    unpowered Cinderace. Exercises the voluntary-retreat wiring (retreat cost + forgone attack are a
    constant offset across the destination options, so readiness still decides the pick)."""
    fx, shadow = _shadows("mega_starmie", "pr_retreat_into_ready_wincon_f92")
    assert max(shadow, key=shadow.get) == fx["correct"][0], shadow


# ---- the WHETHER-to-retreat site (MAIN selects, ruling 1) ----------------------------------------

def _whether(agent: str, fixture: str):
    fx = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
    rec = _pilot(agent).explain(fx["obs"]).promote_retreat_shadow
    assert rec is not None and rec.get("site") == "whether", rec
    return fx, rec


def test_whether_dont_retreat_when_the_active_can_attack_f9():
    """81906755-9 (MAIN, bad_retreat): 'don't waste energy by needlessly retreating' — the Active has a
    real attack, so retreating out of it nets NEGATIVE (ruling 1: stay_yield subtraction). The shadow
    says retreat is not worth it, matching the human's don't-retreat."""
    fx, rec = _whether("mega_starmie", "pr_whether_dont_retreat_f9")
    assert rec["worth_it"] is False, rec


def test_whether_should_retreat_into_the_finisher_f37():
    """82756664-37 (MAIN, bad_retreat): 'should retreat to Mega Starmie for the KO and snipe' — the
    benched finisher out-earns staying, so retreating is worth it (value > 0)."""
    fx, rec = _whether("mega_starmie", "pr_whether_should_retreat_f37")
    assert rec["worth_it"] is True, rec
