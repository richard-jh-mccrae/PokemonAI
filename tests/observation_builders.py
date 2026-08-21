from common.observation import ObservationStateBuilder


def build_observation(printout, *, decklist=None):
    return ObservationStateBuilder(decklist).root(printout)


def advance_observation(parent, printout):
    return ObservationStateBuilder(parent.decklist).advance(parent, printout)[0]
