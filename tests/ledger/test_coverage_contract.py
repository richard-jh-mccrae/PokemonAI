from common.ledger.coverage import (
    DIRECT_CAPABILITY_CLAUSES,
    SUCCESSOR_CLAUSES,
    unowned_clause_kinds,
    unowned_observation_fields,
)


def test_every_observation_field_has_a_value_legal_belief_or_identity_owner():
    assert unowned_observation_fields() == ()


def test_every_clause_is_directly_valued_or_owned_by_engine_successor_differencing():
    assert unowned_clause_kinds() == ()
    assert not DIRECT_CAPABILITY_CLAUSES & SUCCESSOR_CLAUSES
