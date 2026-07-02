"""tuned.json overrides round-trip and are applied by the Pilot."""
from common.pilot import Pilot
from common.strategy import Hypothesis, Strategy
from pilot_helpers import HAND, MAIN, card_opt, make_select, state

from train.tuner.io import authored_seeds, load_overrides, sparse_overrides, write_overrides


def test_written_overrides_change_the_pilots_decision(tmp_path):
    """REQ-TUNER-0005: a tuned weight written to tuned.json round-trips and the Pilot applies
    it by id — a 0-weight Hypothesis, boosted via the overrides, flips the decision."""
    boost = Hypothesis("boost", "", when=lambda c: c.card_id == 222, weight=0)  # off by default
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=MAIN,
                      current=state(hand=[111, 222]))

    assert Pilot(Strategy(hypotheses=[boost]), deck=[1] * 60).decide(obs) == [0]  # tie → first

    path = tmp_path / "tuned.json"
    write_overrides({"boost": 50.0}, path)
    assert load_overrides(path) == {"boost": 50.0}

    pilot = Pilot(Strategy(hypotheses=[boost]), deck=[1] * 60, overrides=load_overrides(path))
    assert pilot.decide(obs) == [1]      # the boosted Hypothesis now favors option 1


def test_sparse_overrides_keeps_only_changed_weights():
    """REQ-TUNER-0011: tuned.json records only weights that differ from the authored seeds, so
    its contents are exactly the overrides that take effect (not a no-op full snapshot)."""
    seeds = {"a": 10.0, "b": -5.0, "c": 25.0}
    fit = {"a": 10.0, "b": 40.0, "c": 25.004}      # only b changed; a unchanged; c rounds back to seed
    assert sparse_overrides(fit, seeds) == {"b": 40.0}


def test_authored_seeds_merge_weight_overrides_as_the_baseline():
    """REQ-WEIGHTS-0003 (ADR-0035): the tuner's seed baseline is the authored-EFFECTIVE weight
    (Hypothesis defaults merged with the deck's ``weight_overrides``), so ``sparse_overrides``
    emits only genuine learned deltas — a fit equal to the authored override ships nothing."""
    general = Strategy(hypotheses=[Hypothesis("g", "", when=lambda c: True, weight=15.0)])
    deck = Strategy(hypotheses=[Hypothesis("d", "", when=lambda c: True, weight=10.0)],
                    weight_overrides={"g": 30.0})
    seeds = authored_seeds(general, deck)
    assert seeds == {"g": 30.0, "d": 10.0}
    assert sparse_overrides({"g": 30.0, "d": 10.0}, seeds) == {}   # fit == authored → no delta ships
    assert sparse_overrides({"g": 35.0}, seeds) == {"g": 35.0}     # a genuine learned delta ships
