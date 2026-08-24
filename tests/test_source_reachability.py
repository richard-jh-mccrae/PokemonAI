import importlib
import ast
from pathlib import Path

from common.cards import card_store
from source_reachability import EXTERNAL_FUNCTIONS, _referenced_functions, analyze


ROOT = Path(__file__).resolve().parents[1]


def test_shipped_source_has_no_unreachable_module_or_top_level_function():
    report = analyze(ROOT)

    assert report.unreachable_modules == ()
    assert report.unreachable_functions == ()


def test_dynamic_card_discovery_is_an_executed_positive_control():
    report = analyze(ROOT)
    module_name = "common.cards.pokemon_cards.mega_starmie_ex_1031"
    module = importlib.import_module(module_name)

    assert module_name in report.dynamic_modules
    assert card_store()[module.CARD.card_id] is module.CARD


def test_reflective_provider_registration_is_an_executed_positive_control():
    from common.engine import CgpyTransitionProvider, LedgerCgpyProvider
    from common.ledger.seam import preview_provider_factory

    assert "common.ledger.seam.register_preview_variant" in EXTERNAL_FUNCTIONS
    assert preview_provider_factory(CgpyTransitionProvider) is LedgerCgpyProvider


def test_unrelated_method_names_cannot_hide_dead_top_level_functions():
    trees = {
        "target": ast.parse("def collision():\n    return 1\n"),
        "caller": ast.parse("class Value:\n    def run(self):\n        return self.collision()\n"),
    }
    definitions = {("target", "collision"): trees["target"].body[0]}

    assert _referenced_functions(trees, set(trees), definitions, set()) == set()

    trees["caller"] = ast.parse("import target\ntarget.collision()\n")
    assert _referenced_functions(trees, set(trees), definitions, set()) == {
        ("target", "collision")}
