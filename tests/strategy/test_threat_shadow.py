"""Threat-Clock unification S1b — the doom SHADOW (design:
docs/plans/opponent-value-equation-unification.md).

``CombatMath.doomed_incoming`` re-expresses the survival doom read as a query against the
``incoming(t=1)`` curve (ceiling policy). It is deliberately NOT byte-identical to ``active_doomed``
— ADR-0064 §2 kept that one unconditionally worst-case — because the curve gates the current form
on affordability (``can_pay_cheapest``). The two therefore DIVERGE on exactly that case; the shadow
emits both + the agreement bit, DECIDING NOTHING, so a corpus sweep can adjudicate the divergence
before any survival swap.

Issue #213 RETIRED a second claimed divergence — that the curve omits the ``hand_size_attacker``
forward counter. It was never true on a production path: the hand-size attack carries the Damage
Formula's ``atk_hand`` scaler, every Incoming call site threads the damage context, and the curve
therefore prices it (in fact slightly HIGHER than the retired hand-rolled branch did). The claim
was retracted rather than implemented, the branch deleted, and the equivalence pinned below —
REQ-DOOMSHADOW-0002, which pins the AFFORDABILITY divergence, is untouched by any of it.
"""
import types

from common.strategy.combat import CombatMath
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider

MY = 1031
OPP = 700
BIG = 701           # {C}{C} 300 — lethal vs my 270 HP, costs 2 Energy


def _combat():
    stats = DictCardStatProvider({
        MY: CardStat(MY, name="My Body", hp=330, maxDamage=100, minAttackCost=1, attacks=()),
        OPP: CardStat(OPP, name="Opp Attacker", hp=200, maxDamage=300, minAttackCost=2,
                      minCostDamage=300, attacks=(BIG,)),
    }, attacks={BIG: AttackStat(BIG, damage=300, cost=2, energyTypes=(0, 0))})
    return CombatMath(stats, functions=None, transients=None)


MY_BODY = {"id": MY, "hp": 270}


def _opp(n):
    return {"id": OPP, "hp": 200, "energies": [0] * n}


# REQ-DOOMSHADOW-0001 — where the Active can afford its lethal attack, curve and incumbent AGREE.
def test_doomed_incoming_agrees_when_the_active_can_afford_its_lethal():
    c = _combat()
    oa = _opp(2)                                        # 2 Energy → affords {C}{C} 300 >= my 270
    assert c.incoming(MY_BODY, [oa], 1) == 300
    assert c.doomed_incoming(MY_BODY, oa) >= MY_BODY["hp"]        # curve: doomed
    assert c.active_doomed(MY_BODY, oa) is True                   # incumbent: doomed → agree


# REQ-DOOMSHADOW-0002 — the KNOWN affordability divergence (the shadow's whole reason to exist).
def test_doomed_incoming_diverges_on_the_unaffordable_current_form():
    # 0-Energy opp Active with a 2-cost lethal. active_doomed is UNCONDITIONAL worst-case → doomed
    # (the hidden-burst-safe survival stance, ADR-0064). The curve gates on can_pay_cheapest(0+1) →
    # the 2-cost attack is unreachable next turn → NOT doomed. This divergence is DATA for the sweep,
    # not a bug — it is why the swap is shadowed, not blind.
    c = _combat()
    oa = _opp(0)
    assert c.active_doomed(MY_BODY, oa) is True                   # incumbent doom (worst-case)
    assert c.doomed_incoming(MY_BODY, oa) == 0                    # curve: current form unaffordable
    assert not (c.doomed_incoming(MY_BODY, oa) >= MY_BODY["hp"])  # → curve reads "survives" (diverges)


# REQ-DOOMSHADOW-0003 — the Pilot emits the shadow (shape + agreement bit) and DECIDES NOTHING.
def test_threat_shadow_emits_the_agreement_bit_and_respects_the_midsim_guard():
    from train.tune import _build_pilot
    p = _build_pilot("mega_lucario")[0]
    p._planning = False
    obs = {"current": {"yourIndex": 0, "players": [
        {"active": [{"id": MY, "hp": 270, "energies": []}]},
        {"active": [{"id": OPP, "hp": 200, "energies": []}]},
    ]}}
    board = types.SimpleNamespace(active_doomed=True)
    p._snapshot(obs)                  # the shadow reads both policies off the snapshot (POC-T1)
    sh = p._threat_shadow(obs, board)
    assert sh is not None
    assert set(sh) >= {"doom_old", "doom_curve", "doom_incoming", "my_hp", "agree",
                       "doom_charged", "matched", "decided", "doom_final"}
    # doom_old is the worst-case oracle COMPUTED FRESH (post-swap the Board bit is the DECIDED
    # value, exposed separately as doom_final — which mirrors what was fed in here).
    ma = obs["current"]["players"][0]["active"][0]
    opp = obs["current"]["players"][1]
    assert sh["doom_old"] == p.combat.active_doomed(ma, opp["active"][0])
    assert sh["doom_final"] is True
    assert sh["agree"] == (sh["doom_old"] == sh["doom_curve"])
    # mid-sim → sparse (no shadow work during rollouts)
    p._planning = True
    assert p._threat_shadow(obs, board) is None
    # no live Active on either side → sparse
    p._planning = False
    assert p._threat_shadow({"current": {"yourIndex": 0, "players": [{}, {}]}}, board) is None


# REQ-DOOMSHADOW-0004 — the RETIRED divergence: the two reads agree on the hand-size family.
# Driven through the real provider, because the claim was always about real card records: Powerful
# Hand's `atk_hand` scaler, Kadabra's forward line, and a live damage context.
def test_the_two_doom_reads_agree_on_a_hand_size_attacker():
    from train.tune import _build_pilot
    combat = _build_pilot("mega_lucario")[0].combat
    ALAKAZAM, KADABRA = 743, 742
    my = {"id": MY, "hp": 130}                      # 140 kills, 120 does not
    opp = {"handCount": 7}
    ctx = {"atk_hand": 7}
    for body in ({"id": ALAKAZAM, "hp": 140, "energies": [5]},       # already the attacker
                 {"id": KADABRA, "hp": 90, "energies": [5]}):        # one evolution away
        worst = combat.active_doomed(my, body, context=ctx)
        curve = combat.doomed_incoming(my, body, context=ctx)
        assert curve == 140                          # 20 dmg/card x a 7-card hand
        assert worst is True and (curve >= my["hp"]) is True         # they AGREE
    # ...and with no context the scaling term contributes 0 to BOTH, so they still agree. This is
    # the case the retired branch used to make diverge, by crediting a card-level roll-up that the
    # curve had no equivalent for.
    kadabra = {"id": KADABRA, "hp": 90, "energies": [5]}
    assert combat.active_doomed(my, kadabra, context=None) is False
    assert combat.doomed_incoming(my, kadabra, context=None) < my["hp"]
