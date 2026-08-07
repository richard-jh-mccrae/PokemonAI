"""The scaled threat read (Issue #213): `CombatMath.threat_ceiling` / `forward_threat_ceiling`.

The snipe rank and the forced-promotion read used to rank bodies by `CardStat.maxDamage` and the
forward index — PRINTED damage, the base term of the Damage Formula with the whole
`per_unit x count(variable)` term dropped. So Alakazam ranked at its forward index's 10 and
Lillie's Clefairy ex at 20, and a flat `+500` boost keyed off a Function Tag covering exactly one
card in the pool papered over the symptom for Alakazam alone.

`threat_ceiling` prices the same question against the LIVE board. It is deliberately
defender-free and Weakness/Resistance-free: it answers "how dangerous is this body", not "how much
does it hit MY current Active for" — folding W/R in would make the snipe order swing on my own
Active's typing.

Driven through the real provider (`_build_pilot`), never a hand-built table: a synthetic stat table
can describe a board that cannot exist and will happily manufacture a passing test.
"""
import pytest

ALAKAZAM, KADABRA = 743, 742          # Powerful Hand: 2 counters per card in hand = 20/card
CLEFAIRY_EX = 272                     # Full Moon Rondo: printed 20, +20 per COMBINED bench body
SKELEDIRGE = 203                      # Torcherto: printed 60, same combined-bench family
LUCARIO_LINE = 1031                   # a plain printed-damage body, no scaler


@pytest.fixture(scope="module")
def combat():
    from train.tune import _build_pilot
    return _build_pilot("mega_lucario")[0].combat


@pytest.mark.req("REQ-THREATCEIL-0001")
def test_a_hand_size_attacker_is_priced_off_the_opponents_hand(combat):
    # The printed number is 0 and the card-level roll-up is 0 too — the entire threat lives in
    # the scaling term. This is the `ms f85` gap the forced-promotion read has carried as a TODO.
    assert combat.threat_ceiling(ALAKAZAM, context={"atk_hand": 0}) == 0
    assert combat.threat_ceiling(ALAKAZAM, context={"atk_hand": 7}) == 140


@pytest.mark.req("REQ-THREATCEIL-0001")
def test_a_combined_bench_attacker_is_priced_off_both_benches(combat):
    # Engine-confirmed: printed + 20 x (my bench + their bench).
    assert combat.threat_ceiling(CLEFAIRY_EX, context={"both_bench": 0}) == 20
    assert combat.threat_ceiling(CLEFAIRY_EX, context={"both_bench": 9}) == 200
    assert combat.threat_ceiling(SKELEDIRGE, context={"both_bench": 9}) == 240


@pytest.mark.req("REQ-THREATCEIL-0001")
def test_an_absent_variable_degrades_to_the_printed_base(combat):
    # Fail-safe, not fail-loud: a context missing the scaler's variable contributes 0 to the
    # term, leaving the printed base — never a crash and never an invented number.
    assert combat.threat_ceiling(CLEFAIRY_EX, context=None) == 20
    assert combat.threat_ceiling(CLEFAIRY_EX, context={}) == 20
    assert combat.threat_ceiling(ALAKAZAM, context={}) == 0


@pytest.mark.req("REQ-THREATCEIL-0001")
def test_the_read_is_defender_free_so_the_snipe_order_cannot_swing_on_my_typing(combat):
    # Same body, same context, one number — there is no defender argument to vary.
    assert combat.threat_ceiling(SKELEDIRGE, context={"both_bench": 4}) == 140
    assert combat.threat_ceiling(LUCARIO_LINE, context={"both_bench": 4}) == \
        combat.threat_ceiling(LUCARIO_LINE, context={"both_bench": 0})


@pytest.mark.req("REQ-THREATCEIL-0002")
def test_the_forward_read_prices_what_the_line_evolves_into(combat):
    # Kadabra's own attack is small; its LINE reaches Alakazam. The printed forward index reads
    # 10 here — "Alakazam's printed 10 hides the real threat", the gap this closes.
    assert combat.forward_threat_ceiling(KADABRA, context={"atk_hand": 7}) == 140
    assert combat.forward_threat_ceiling(KADABRA, context={"atk_hand": 0}) == 10


@pytest.mark.req("REQ-THREATCEIL-0002")
def test_the_forward_read_is_empty_for_a_dead_end_line(combat):
    assert combat.forward_threat_ceiling(ALAKAZAM, context={"atk_hand": 7}) == 0


@pytest.mark.req("REQ-THREATCEIL-0002")
def test_unknown_ids_read_zero_rather_than_guessing(combat):
    assert combat.threat_ceiling(None, context={"atk_hand": 7}) == 0
    assert combat.threat_ceiling(10_000_000, context={"atk_hand": 7}) == 0
    assert combat.forward_threat_ceiling(None, context={"atk_hand": 7}) == 0


@pytest.mark.req("REQ-THREATCEIL-0003")
def test_the_card_level_fallback_still_credits_hand_size_without_attack_records(combat):
    # No AttackStat resolves, so the read drops to the card-level roll-up — which must still credit
    # the hand-size scaler.
    from common.scouting.provider import CardStat, DictCardStatProvider
    from common.strategy.combat import CombatMath
    blind = CombatMath(DictCardStatProvider({
        ALAKAZAM: CardStat(ALAKAZAM, name="Alakazam", hp=140, maxDamage=0,
                           handSizeDamage=20, attacks=(1072,)),
    }), functions=None, transients=None)
    assert blind.threat_ceiling(ALAKAZAM, context={"atk_hand": 7}) == 140
    assert blind.threat_ceiling(ALAKAZAM, context={"atk_hand": 0}) == 0
