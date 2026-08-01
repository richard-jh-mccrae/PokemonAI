"""ADR-0064 Decision 3 — the predicted-LOSS rung (`Pilot._predicted_loss`).

A candidate end board whose only Pokémon is a doomed Active (my Bench EMPTY + budgeted Incoming ≥ my
HP) is a predicted game loss, priced at ``-KO_SCORE`` (a terminal loss rung, not the flat
``_PLANNER_SURVIVAL_W`` nudge). The rung stands down the moment a bench body can soak — that's a
recoverable lost body, not a loss.
"""
from common.cards import CardFunctions
from common.pilot import KO_SCORE, Pilot
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy

MY = 1031           # Mega Starmie ex ({L}-weak — Fighting un-adjusted)
RIOLU = 677
MEGA_LUC = 678
FIGHTING = 6
ACC_STAB, AURA_JAB, MEGA_BRAVE = 900, 982, 983


def _armed(me=None, opp=None):
    """A Pilot with the per-decision StateModel installed — the rung reads its Threat Clock through
    the snapshot now (POC-T1, Issue #260), so a board that never had one makes no claim by design.
    The `me`/`opp` handed to the rung are a SIMULATED end board and reach it as `bodies=`; the
    snapshot supplies only the threaded energy policy and forward index, so the obs it is built on
    just has to be a coherent board."""
    p = _pilot()
    p._snapshot({"current": {"yourIndex": 0,
                             "players": [me or {"active": [], "bench": []},
                                         opp or {"active": [], "bench": []}]}})
    return p


def _pilot():
    stats = DictCardStatProvider({
        MY: CardStat(MY, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                     minAttackCost=1, attacks=(), energyType=3),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=80, maxDamage=30, minAttackCost=2,
                        minCostDamage=30, attacks=(ACC_STAB,), energyType=6),
        MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, megaEx=True, maxDamage=270,
                           minAttackCost=1, minCostDamage=130, attacks=(AURA_JAB, MEGA_BRAVE),
                           evolvesFrom="Riolu", energyType=6),
    }, attacks={
        ACC_STAB: AttackStat(ACC_STAB, damage=30, cost=2, energyTypes=(FIGHTING, FIGHTING)),
        AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,)),
        MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING)),
    })
    return Pilot(Strategy(roles={}, lines=[]), deck=[1] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=stats, functions=CardFunctions({}))


def _me(active_hp, bench_ids=()):
    return {"active": [{"id": MY, "hp": active_hp}],
            "bench": [{"id": b, "hp": 80, "energies": []} for b in bench_ids]}


def _opp(riolu_energy):
    # a benched Riolu one hop from Mega Lucario ex, holding `riolu_energy` {F}
    return {"active": [{"id": RIOLU, "hp": 80, "energies": []}],
            "bench": [{"id": RIOLU, "hp": 80, "energies": [FIGHTING] * riolu_energy}]}


def test_loss_rung_fires_on_bench_empty_doomed_active():
    # My Active at 270, empty bench; their bench Riolu (1 F) can evolve → Mega Brave 270 → exact KO.
    p = _armed(_me(270), _opp(riolu_energy=1))
    assert p._predicted_loss(_me(270), _opp(riolu_energy=1)) == -KO_SCORE


def test_loss_rung_stands_down_when_a_bench_body_can_soak():
    # Same lethal Incoming, but I have a benched body — a lost Active is recoverable, not a game loss.
    p = _armed(_me(270, bench_ids=(RIOLU,)), _opp(riolu_energy=1))
    assert p._predicted_loss(_me(270, bench_ids=(RIOLU,)), _opp(riolu_energy=1)) == 0.0


def test_loss_rung_stands_down_when_the_active_survives():
    # Their bench Riolu has 0 F: the evolved form reaches only Aura Jab 130 < 270 → survives (ceiling
    # still credits the evolved max here, so use a higher HP to prove the survive path).
    p = _armed(_me(400), _opp(riolu_energy=1))
    assert p._predicted_loss(_me(400), _opp(riolu_energy=1)) == 0.0   # 400 HP > 270 worst-case → safe


def test_loss_rung_does_not_fire_on_a_bare_zero_energy_pre_evo_phantom():
    # The bounded-pessimism guard: an opponent's 0-Energy benched pre-evo (Riolu) is NOT a credible
    # next-turn game-ender — it needs the evolution in hand plus a from-scratch attach. The ±50
    # survival term may still be pessimistic, but the -KO_SCORE catastrophe rung must not fire (else
    # a lone Active reads as a turn-2 game loss off a phantom evolution).
    p = _armed(_me(270), _opp(riolu_energy=0))
    assert p._predicted_loss(_me(270), _opp(riolu_energy=0)) == 0.0


def test_loss_rung_zero_without_an_active():
    p = _armed({"active": [], "bench": []}, _opp(riolu_energy=1))
    assert p._predicted_loss({"active": [], "bench": []}, _opp(riolu_energy=1)) == 0.0
