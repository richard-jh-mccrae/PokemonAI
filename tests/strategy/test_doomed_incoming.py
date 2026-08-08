"""``CombatMath.doomed_incoming`` — the survival doom read as a query against the ``incoming(t=1)``
curve, and where it deliberately diverges from the DOOM policy.

The divergence is intentional and is the whole content of the file. `doomed_incoming` gates the
current form on affordability (``can_pay_cheapest``); the DOOM policy is unconditionally worst-case,
because ADR-0064 §2 keeps survival fail-direction on assuming the worse outcome for me
(`sound_rules`: `doom-ceiling-fail-direction`). So they agree wherever the Active can afford its
lethal and split where it cannot.
"""
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy.combat import CombatMath

MY = 1031
OPP = 700
BIG = 701           # {C}{C} 300 — lethal vs my 270 HP, costs 2 Energy


def _combat():
    stats = DictCardStatProvider({
        MY: CardStat(MY, synthetic=True, name="My Body", hp=330, maxDamage=100, minAttackCost=1, attacks=()),
        OPP: CardStat(OPP, synthetic=True, name="Opp Attacker", hp=200, maxDamage=300, minAttackCost=2,
                      minCostDamage=300, attacks=(BIG,)),
    }, attacks={BIG: AttackStat(BIG, damage=300, cost=2, energyTypes=(0, 0))})
    return CombatMath(stats, functions=None, transients=None)


MY_BODY = {"id": MY, "hp": 270}


def _doom(oracle, ma, oa, *, context=None) -> bool:
    """The DOOM policy read at oracle level — the same composition `TheirSide.doomed` performs, but
    without a model to hand."""
    from common.strategy.combat import UNCHARGED
    hp = (ma or {}).get("hp", 0)
    return bool(hp) and int(oracle.incoming(ma, [oa], 1, charged=UNCHARGED, context=context)) >= hp


def _opp(n):
    return {"id": OPP, "hp": 200, "energies": [0] * n}


def test_doomed_incoming_agrees_when_the_active_can_afford_its_lethal():
    """Where the Active can pay for the attack that kills me, curve and policy AGREE."""
    c = _combat()
    oa = _opp(2)                                        # 2 Energy → affords {C}{C} 300 >= my 270
    assert c.incoming(MY_BODY, [oa], 1) == 300
    assert c.doomed_incoming(MY_BODY, oa) >= MY_BODY["hp"]        # curve: doomed
    assert _doom(c, MY_BODY, oa) is True                          # doom policy: doomed → agree


def test_doomed_incoming_diverges_on_the_unaffordable_current_form():
    """The DOOM policy is UNCONDITIONAL worst-case (ADR-0064) while the curve gates on
    `can_pay_cheapest`. A fail-direction policy choice, not a bug."""
    c = _combat()
    oa = _opp(0)
    assert _doom(c, MY_BODY, oa) is True                          # doom policy (worst-case)
    assert c.doomed_incoming(MY_BODY, oa) == 0                    # curve: current form unaffordable
    assert not (c.doomed_incoming(MY_BODY, oa) >= MY_BODY["hp"])  # → curve reads "survives"


def test_the_two_doom_reads_agree_on_a_hand_size_attacker():
    """The RETIRED divergence (Issue #213), driven through the REAL provider because the claim was
    always about real card records."""
    from train.tune import _build_pilot
    combat = _build_pilot("mega_lucario")[0].combat
    ALAKAZAM, KADABRA = 743, 742
    my = {"id": MY, "hp": 130}                      # 140 kills, 120 does not
    ctx = {"atk_hand": 7}                           # the hand-size scaler's measured variable
    for body in ({"id": ALAKAZAM, "hp": 140, "energies": [5]},       # already the attacker
                 {"id": KADABRA, "hp": 90, "energies": [5]}):        # one evolution away
        worst = _doom(combat, my, body, context=ctx)
        curve = combat.doomed_incoming(my, body, context=ctx)
        assert curve == 140                          # 20 dmg/card x a 7-card hand
        assert worst is True and (curve >= my["hp"]) is True         # they AGREE
    # ...and with no context the scaling term contributes 0 to BOTH, which is the case the retired
    # branch made diverge by crediting a card-level roll-up the curve had no equivalent for.
    kadabra = {"id": KADABRA, "hp": 90, "energies": [5]}
    assert _doom(combat, my, kadabra, context=None) is False
    assert combat.doomed_incoming(my, kadabra, context=None) < my["hp"]
