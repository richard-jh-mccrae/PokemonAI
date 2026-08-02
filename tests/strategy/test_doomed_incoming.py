"""``CombatMath.doomed_incoming`` — the survival doom read as a query against the ``incoming(t=1)``
curve, and where it deliberately diverges from the DOOM policy.

Rehomed from `test_threat_shadow.py`, which Issue #261 item 2h deleted with `_threat_shadow`. Only
one of that file's four cases was about the shadow (the emitter's shape and its mid-sim guard); the
other three are properties of the curve itself and of the policy read off it, so they survive the
diagnostic that used to be the excuse for computing them.

The divergence is intentional and is the whole content of the file. `doomed_incoming` gates the
current form on affordability (``can_pay_cheapest``); the DOOM policy is unconditionally worst-case,
because ADR-0064 §2 keeps survival fail-direction on the side of assuming the worse outcome for me
(`sound_rules`: `doom-ceiling-fail-direction`). They therefore agree wherever the Active can afford
its lethal and split where it cannot.

Issue #213 RETIRED a second claimed divergence — that the curve omits the ``hand_size_attacker``
forward counter. It was never true on a production path: the hand-size attack carries the Damage
Formula's ``atk_hand`` scaler, every Incoming call site threads the damage context, and the curve
therefore prices it (in fact slightly HIGHER than the retired hand-rolled branch did). The claim was
retracted rather than implemented, the branch deleted, and the equivalence pinned below.
"""
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy.combat import CombatMath

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


def _doom(oracle, ma, oa, *, context=None) -> bool:
    """The DOOM policy read, oracle-level. POC-T1 (Issue #260) folded `active_doomed` onto the curve
    and then deleted it once the census moved its consumers onto the snapshot, where the composed
    form lives as `TheirSide.doomed`; this is the same composition without a model to hand."""
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
    """The KNOWN divergence, and the reason the two readings are not one. A 0-Energy opp Active with
    a 2-cost lethal: the DOOM policy is UNCONDITIONAL worst-case → doomed (the hidden-burst-safe
    survival stance, ADR-0064). The curve gates on `can_pay_cheapest(0+1)` → the 2-cost attack is
    unreachable next turn → NOT doomed. A fail-direction policy choice, not a bug."""
    c = _combat()
    oa = _opp(0)
    assert _doom(c, MY_BODY, oa) is True                          # doom policy (worst-case)
    assert c.doomed_incoming(MY_BODY, oa) == 0                    # curve: current form unaffordable
    assert not (c.doomed_incoming(MY_BODY, oa) >= MY_BODY["hp"])  # → curve reads "survives"


def test_the_two_doom_reads_agree_on_a_hand_size_attacker():
    """The RETIRED divergence (Issue #213). Driven through the real provider, because the claim was
    always about real card records: Powerful Hand's `atk_hand` scaler, Kadabra's forward line, and a
    live damage context."""
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
    # ...and with no context the scaling term contributes 0 to BOTH, so they still agree. This is
    # the case the retired branch used to make diverge, by crediting a card-level roll-up that the
    # curve had no equivalent for.
    kadabra = {"id": KADABRA, "hp": 90, "energies": [5]}
    assert _doom(combat, my, kadabra, context=None) is False
    assert combat.doomed_incoming(my, kadabra, context=None) < my["hp"]
