"""POC-T1 (Issue #260) — the legacy doom pair folds onto the Threat-Clock curve, byte-identically.

`CombatMath.active_doomed` used to be ``max(incoming_active_damage, forward_incoming_damage)``: two
hand-written reads standing beside `incoming`, the curve that answers the same question. Their
agreement with the curve was a MEASUREMENT (259/274 — `doom-shadow-grill-handoff.md`) rather than a
property, and the 15 disagreements were ruled frame-by-frame in that grill's RULED appendix.

The fold makes the divergence a **policy** instead of a second code path: `UNCHARGED` is what "worst
case, affordability not charged on the body as it stands" means, spelled as a parameter of the one
curve. This module is the evidence that the spelling did not change the number.

**The reference oracle below is the DELETED code, verbatim.** That is the point — a pin that
re-derived the expected values from the new implementation would assert nothing. It is a fixture, not
a fallback: nothing imports it, and when a future change means to move the doom read, this test is
what has to be re-ruled rather than quietly re-baselined.

Two divergences are declared rather than pinned, because both are DEFECTS OF THE OLD PAIR that the
fold fixes, both in the pessimistic direction:

1. **A self-locked Active still contributes its FORWARD forms.** Evolving clears attack effects
   (`docs/rules.md` §4), so an ADR-0033 self-lock is a fact about *that* Pokémon. The old pair got
   this right by accident (`forward_incoming_damage` never consulted the lock at all) while
   `incoming`'s shared enumeration got it wrong (it skipped the whole line). The curve is fixed;
   `_legacy_forward` below reproduces the old pair, so on a locked body the two legitimately differ.
2. **The vestigial ``opp`` parameter is gone.** It was never read — passing None silently disabled
   the entire forward leg. No caller relied on it (verified: every live call passed a real dict).
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: The RULED 15-frame divergence corpus (doom-shadow grill, 2026-07-23) is drawn from these three
#: agents' correction runs; the fold is checked over EVERY committed frame of all of them rather
#: than only the 15, because "the 15" was a property of one sweep and this pin should not rot when
#: the corpus widens (ADR-0089 decision 2 — a ruling is re-derived, not inherited).
AGENTS = ("mega_starmie", "mega_lucario", "dragapult_ex")


# ── the reference oracle: the two deleted bodies, verbatim ────────────────────────────────────────
def _legacy_current(combat, ma, oa, *, context=None) -> int:
    """`CombatMath.incoming_active_damage` as it stood before the fold."""
    if not (combat.stats and ma and oa):
        return 0
    opp_stat = combat._card_stat(oa.get("id"))
    if not opp_stat:
        return 0
    grant = combat._grant(oa) or {}
    if grant.get("self_lock"):
        return 0
    dmg = combat.predicted_max_damage(opp_stat, ma, exclude_attack=grant.get("same_lock"),
                                      context=context)
    return int(dmg + grant.get("self_bonus", 0)) if dmg else int(dmg)


def _legacy_forward(combat, ma, oa, opp, *, context=None) -> int:
    """`CombatMath.forward_incoming_damage` as it stood before the fold."""
    if not (combat.stats and ma and oa and opp):
        return 0
    if not combat._card_stat(ma.get("id")):
        return 0
    oa_energy = len(oa.get("energies") or [])
    best = 0
    for fid in combat.forward_card_ids(oa.get("id")):
        fstat = combat._card_stat(fid)
        if not fstat:
            continue
        if (fstat.minAttackCost or 0) > oa_energy + 1:
            continue
        best = max(best, int(combat.predicted_max_damage(fstat, ma, context=context)))
    return best


def _legacy_doomed(combat, ma, oa, opp, *, context=None) -> bool:
    my_hp = (ma or {}).get("hp", 0)
    if not my_hp:
        return False
    return max(_legacy_current(combat, ma, oa, context=context),
               _legacy_forward(combat, ma, oa, opp, context=context)) >= my_hp


# ── the corpus walk ───────────────────────────────────────────────────────────────────────────────
def _pilot(deck):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(deck)[0]


def _frames(agent):
    """Every committed correction frame for ``agent``, as ``(run, index, obs)``."""
    root = REPO / "data" / "corrections"
    if not root.exists():
        return
    for run in sorted(root.iterdir()):
        if not run.name.startswith(agent + "_"):
            continue
        path = run / "corrections.jsonl"
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            obs = rec.get("obs")
            if isinstance(obs, dict) and obs.get("current"):
                yield run.name, i, obs


def _sides(obs):
    state = obs.get("current") or {}
    players = state.get("players") or []
    yi = state.get("yourIndex", 0)
    me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
    opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
    ma = next((p for p in (me.get("active") or []) if p), None)
    oa = next((p for p in (opp.get("active") or []) if p), None)
    return ma, oa, opp


@pytest.mark.parametrize("agent", AGENTS)
def test_the_fold_is_byte_identical_to_the_deleted_pair(agent):
    """`active_doomed` and the raw damage read agree with the pre-fold implementations on every
    committed correction frame — the corpus the 15 ruled divergences were drawn from."""
    frames = list(_frames(agent))
    if not frames:
        pytest.skip(f"no committed correction corpus for {agent}")
    pilot = _pilot(agent)
    checked = 0
    for run, i, obs in frames:
        ma, oa, opp = _sides(obs)
        if not (ma and oa):
            continue
        pilot._snapshot(obs)
        ctx = pilot._damage_context(obs, attacker_is_me=False)
        where = f"{agent}/{run}#{i}"
        # a transient self-lock is the one declared divergence (see the module docstring); the
        # tracker is empty on a replayed frame, but assert the premise rather than assume it
        assert not (pilot.combat._grant(oa) or {}).get("self_lock"), (
            f"{where}: a self-locked Active is the declared divergence — rule it, don't pin it")
        assert pilot.combat.incoming_active_damage(ma, oa, context=ctx) == \
            _legacy_current(pilot.combat, ma, oa, context=ctx), f"{where}: current-form damage moved"
        assert pilot.combat.active_doomed(ma, oa, context=ctx) == \
            _legacy_doomed(pilot.combat, ma, oa, opp, context=ctx), f"{where}: the doom bit moved"
        checked += 1
    assert checked >= 20, f"{agent}: only {checked} frames carried a live Active pair — too thin to pin"


def test_the_fold_reads_one_curve_at_two_policies():
    """The structural claim, stated as code: doom IS `incoming` under `UNCHARGED`, and the surviving
    divergence from `doomed_incoming` is that method's `charged=None` ceiling — one implementation,
    two policies. If a future edit re-splits them this fails before any corpus does."""
    from common.strategy.combat import UNCHARGED
    pilot = _pilot("mega_lucario")
    frames = [obs for _run, _i, obs in _frames("mega_lucario")]
    if not frames:
        pytest.skip("no committed correction corpus")
    seen_divergence = False
    for obs in frames:
        ma, oa, _opp = _sides(obs)
        if not (ma and oa and ma.get("hp")):
            continue
        model = pilot._snapshot(obs)
        ctx = pilot._damage_context(obs, attacker_is_me=False)
        doom = model.theirs.incoming(ma, 1, bodies=[oa], charged=UNCHARGED, context=ctx)
        ceiling = model.theirs.incoming(ma, 1, bodies=[oa], charged=None, context=ctx)
        assert pilot.combat.active_doomed(ma, oa, context=ctx) == (doom >= ma["hp"])
        # the doom policy is strictly the more pessimistic of the two — that is what makes it the
        # one policy a catastrophe-grade boolean may take (`sound_rules: doom-ceiling-fail-direction`)
        assert doom >= ceiling, "the doom policy must never read BELOW the ceiling"
        seen_divergence = seen_divergence or doom > ceiling
    assert seen_divergence, ("the two policies never diverged on this corpus — the divergence this "
                            "fold turns into a parameter is what the 15 ruled frames measured, so "
                            "its disappearance is a finding, not a pass")
