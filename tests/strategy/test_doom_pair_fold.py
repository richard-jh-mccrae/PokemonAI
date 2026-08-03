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

from common.strategy.combat import CURRENT_FORMS_ONLY, UNCHARGED

REPO = Path(__file__).resolve().parents[2]

#: The three agents whose correction runs the ruled corpus is drawn from. The fold is checked over
#: EVERY committed frame of all three, not only the 15 — "the 15" was a property of one sweep, and a
#: pin scoped to it would narrow silently as the corpus grows (ADR-0089 decision 2: a ruling is
#: re-derived, not inherited).
AGENTS = ("mega_starmie", "mega_lucario", "dragapult_ex")

#: …and the fifteen frames the grill ruled BY NAME (`doom-shadow-grill-handoff.md`, RULED appendix),
#: as `episode_id-frame`. Asserted present and byte-identical individually, because "the corpus was
#: covered" is a weaker claim than "these frames were covered": the whole sweep found agreement on
#: 259/274 and it is exactly these fifteen where the two reads disagreed, so they are the frames a
#: fold could plausibly move.
RULED_15 = (
    "81904451-17", "82749168-21", "82749168-29", "81904064-44", "85163634-17",
    "85058574-69", "85058574-71", "86091435-13", "86091435-20", "86091435-30",
    "86091435-35", "86091435-60", "86091435-62", "86091435-68", "86091435-69",
)


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
                key = f"{rec.get('episode_id')}-{(rec.get('decision') or {}).get('frame')}"
                yield run.name, i, obs, key


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
    for run, i, obs, _key in frames:
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
        model = pilot._state_model
        assert model.theirs.incoming(ma, 1, bodies=[oa], charged=UNCHARGED,
                                     forward_ids=CURRENT_FORMS_ONLY, context=ctx) == \
            _legacy_current(pilot.combat, ma, oa, context=ctx), f"{where}: current-form damage moved"
        assert model.theirs.doomed(ma, bodies=[oa], context=ctx) == \
            _legacy_doomed(pilot.combat, ma, oa, opp, context=ctx), f"{where}: the doom bit moved"
        checked += 1
    assert checked >= 20, f"{agent}: only {checked} frames carried a live Active pair — too thin to pin"


def test_the_fold_reads_one_curve_at_two_policies():
    """The structural claim, stated as code: doom IS `incoming` under `UNCHARGED`, and the surviving
    divergence from `doomed_incoming` is that method's `charged=None` ceiling — one implementation,
    two policies. If a future edit re-splits them this fails before any corpus does."""
    pilot = _pilot("mega_lucario")
    frames = [obs for _run, _i, obs, _k in _frames("mega_lucario")]
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
        assert model.theirs.doomed(ma, bodies=[oa], context=ctx) == (doom >= ma["hp"])
        # the doom policy is strictly the more pessimistic of the two — that is what makes it the
        # one policy a catastrophe-grade boolean may take (`sound_rules: doom-ceiling-fail-direction`)
        assert doom >= ceiling, "the doom policy must never read BELOW the ceiling"
        seen_divergence = seen_divergence or doom > ceiling
    assert seen_divergence, ("the two policies never diverged on this corpus — the divergence this "
                            "fold turns into a parameter is what the 15 ruled frames measured, so "
                            "its disappearance is a finding, not a pass")


@pytest.mark.parametrize("frame_key", RULED_15)
def test_each_RULED_frame_is_byte_identical(frame_key):
    """The fifteen by name. `test_the_fold_is_byte_identical_to_the_deleted_pair` already covers
    them inside its corpus walk, but only as anonymous members of a few hundred — and a walk that
    silently stopped finding them would still pass. These are the frames the grill ruled one at a
    time; they are asserted one at a time."""
    for agent in AGENTS:
        for _run, _i, obs, key in _frames(agent):
            if key != frame_key:
                continue
            pilot = _pilot(agent)
            ma, oa, opp = _sides(obs)
            assert ma and oa, f"{frame_key}: the ruled frame must carry a live Active pair"
            model = pilot._snapshot(obs)
            ctx = pilot._damage_context(obs, attacker_is_me=False)
            assert model.theirs.doomed(ma, bodies=[oa], context=ctx) == \
                _legacy_doomed(pilot.combat, ma, oa, opp, context=ctx), f"{frame_key}: doom moved"
            return
    pytest.fail(f"{frame_key} is not in the committed corrections corpus — the ruled 15-frame "
                "corpus this fold was measured against has moved, so re-derive the ruling")


def test_the_declared_self_lock_divergence_is_MEASURED_not_assumed():
    """The one behaviour change the corpus cannot show, shown directly.

    `_attacker_forms` used to skip a self-locked body's WHOLE line; it now skips only the locked
    form and still yields its FORWARD forms, because evolving clears attack effects
    (`docs/rulebook.txt` L215: *"When a Pokémon evolves or moves to the Bench, it recovers from all
    Special Conditions"*; `docs/rules.md` §4 for attack effects). The corpus walk asserts no frame
    carries a live lock rather than exercising one — the tracker is empty on a replayed frame — so
    without this the fold's only real divergence would be untested.

    Both halves are asserted: the locked form contributes nothing, and its forward form still does.
    The direction matters — the old pair got this right by accident (`forward_incoming_damage` never
    consulted the lock), so had the fold inherited `incoming`'s skip it would have made a survival
    read LESS pessimistic than the read it replaced."""
    from common.cards import CardFunctions
    from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
    from common.strategy.combat import CombatMath

    PRE, EVO, SMALL, BIG = 900001, 900002, 51, 52
    stats = DictCardStatProvider({
        PRE: CardStat(PRE, name="Locked Base", hp=90, energyType=6, minAttackCost=1,
                      maxDamage=60, attacks=(SMALL,)),
        EVO: CardStat(EVO, name="Its Evolution", hp=300, evolvesFrom="Locked Base", energyType=6,
                      minAttackCost=1, maxDamage=200, attacks=(BIG,)),
        1: CardStat(1, synthetic=True, name="My Body", hp=150),
    }, attacks={SMALL: AttackStat(SMALL, damage=60, cost=1),
                BIG: AttackStat(BIG, damage=200, cost=1)})

    class _Locked:
        """A tracker whose grant self-locks serial 7 — ADR-0033's "this body cannot attack at all"."""
        def grant_for_serial(self, serial):
            return {"self_lock": True} if serial == 7 else None

    combat = CombatMath(stats, functions=CardFunctions({}), transients=_Locked())
    ma, oa = {"id": 1, "hp": 150}, {"id": PRE, "serial": 7, "hp": 90, "energies": [6]}

    # the locked body itself contributes nothing — its own 60 is off the table
    assert combat.incoming(ma, [oa], 1, charged=UNCHARGED,
                           forward_ids=CURRENT_FORMS_ONLY) == 0
    # …and its EVOLUTION still threatens 200, because the lock is a fact about that Pokémon
    assert combat.incoming(ma, [oa], 1, charged=UNCHARGED) == 200
    assert combat.incoming(ma, [oa], 1, charged=UNCHARGED) >= ma["hp"]      # so: still doomed

    # the OLD pair agreed with the new reading here — this is a fix to `incoming`, not to the pair
    assert _legacy_current(combat, ma, oa) == 0
    assert _legacy_forward(combat, ma, oa, {"handCount": 0}) == 200
