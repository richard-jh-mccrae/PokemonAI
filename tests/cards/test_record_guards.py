"""The guard rails fire: duplicate ids refuse to load, records refuse to mutate.

A guard nobody has ever seen raise protects nothing — each ValueError path gets a synthetic
trigger here, with caches cleared so the real store is untouched afterwards."""
from __future__ import annotations

import dataclasses
import importlib

import pytest

import common.cards as cards
from common.cards import play_clauses
from common.cards.card_facts import (
    Ability, Attack, BASIC, Clause, PokemonCard, TrainerCard, ITEM, COLORLESS)


def _fake_package(tmp_path, monkeypatch, name, modules):
    pkg = tmp_path / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    for module_name, body in modules.items():
        (pkg / f"{module_name}.py").write_text(body, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return importlib.import_module(name)


CARD_BODY = "class _C:\n    card_id = {cid}\nCARD = _C()\n"


def test_a_duplicate_card_id_in_one_package_refuses_to_load(tmp_path, monkeypatch):
    package = _fake_package(tmp_path, monkeypatch, "fake_pkg_duplicate", {
        "card_a": CARD_BODY.format(cid=1),
        "card_b": CARD_BODY.format(cid=1),
    })
    with pytest.raises(ValueError, match="duplicate card id"):
        cards._load_package(package)


def test_distinct_ids_load_cleanly(tmp_path, monkeypatch):
    package = _fake_package(tmp_path, monkeypatch, "fake_pkg_distinct", {
        "card_a": CARD_BODY.format(cid=1),
        "card_b": CARD_BODY.format(cid=2),
    })
    assert set(cards._load_package(package)) == {1, 2}


def _mon(card_id, attacks=()):
    return PokemonCard(card_id=card_id, name=f"M{card_id}", hp=10, energy_type=COLORLESS,
                       stage=BASIC, attacks=tuple(attacks))


def test_an_attack_id_on_two_cards_refuses_to_index(monkeypatch):
    shared = Attack(attack_id=7, name="X", cost=(), damage=0)
    monkeypatch.setattr(cards, "pokemon_card_store",
                        lambda: {1: _mon(1, [shared]), 2: _mon(2, [shared])})
    cards.attack_index.cache_clear()
    try:
        with pytest.raises(ValueError, match="two cards"):
            cards.attack_index()
    finally:
        cards.attack_index.cache_clear()


def test_a_card_id_in_two_stores_refuses_to_union(monkeypatch):
    clash = TrainerCard(card_id=1, name="T", kind=ITEM)
    monkeypatch.setattr(cards, "pokemon_card_store", lambda: {1: _mon(1)})
    monkeypatch.setattr(cards, "trainer_card_store", lambda: {1: clash})
    monkeypatch.setattr(cards, "energy_card_store", lambda: {})
    cards.card_store.cache_clear()
    try:
        with pytest.raises(ValueError, match="more than one store"):
            cards.card_store()
    finally:
        cards.card_store.cache_clear()


def test_records_and_clause_parameters_are_immutable():
    mon = _mon(1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        mon.hp = 999
    clause = Clause("draw", amount=3)
    with pytest.raises(TypeError):
        clause.params["amount"] = 99


def test_the_first_clause_of_a_kind_wins():
    doubled = Attack(attack_id=1, name="X", cost=(), damage=0,
                     clauses=(Clause("scale", per_unit=10), Clause("scale", per_unit=99)))
    assert doubled.clause("scale").per_unit == 10


def test_play_clauses_offers_own_and_ability_clauses_but_never_attack_ones():
    assert play_clauses(None) == ()
    trainer = TrainerCard(card_id=2, name="T", kind=ITEM,
                          clauses=(Clause("fetch", target="pokemon"),))
    assert [c.kind for c in play_clauses(trainer)] == ["fetch"]
    mon = PokemonCard(
        card_id=3, name="M", hp=10, energy_type=COLORLESS, stage=BASIC,
        abilities=(Ability(name="A", clauses=(Clause("draw", amount=3),)),),
        attacks=(Attack(attack_id=9, name="Hit", cost=(), damage=10,
                        clauses=(Clause("bench_snipe", amount=50),)),))
    assert [c.kind for c in play_clauses(mon)] == ["draw"]
