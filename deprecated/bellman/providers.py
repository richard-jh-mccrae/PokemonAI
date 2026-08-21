"""Bellman-search bindings for the live transition providers.

The search protocol needs three hooks the live seams no longer carry: commutativity footprints
(sleep-set pruning), the lethal gate's per-action coverage check, and forced-End resolution.
"""
from __future__ import annotations

from functools import partial

from common.engine import terminal_effects_supported
from common.engine import CgpyTransitionProvider
from common.native_engine import NativeCgTransitionProvider
from common.option_equivalence import option_in_play_source_id
from common.refresh import played_card_id
from common.strategy.context import _ACTIVE, _BENCH

from .commutativity import action_footprint
from .transition_value import end_has_forced_value_change


class BellmanNativeProvider(NativeCgTransitionProvider):
    def footprint(self, state, action):
        return action_footprint(state, action, cards=self.cards)

    def terminal_action_supported(self, state, action) -> bool:
        kind = action.identity.kind
        options = tuple((state.obs.get("select") or {}).get("option") or ())
        option_index = action.selection[0] if len(action.selection) == 1 else -1
        option = options[option_index] if 0 <= option_index < len(options) else {}
        current = state.obs.get("current") or {}
        players = current.get("players") or ()
        mine = players[state.root_seat] if state.root_seat < len(players) else {}
        card_id = played_card_id(state, action)
        if card_id is None and kind in {"attach", "evolve"}:
            hand_index = option.get("index")
            hand = mine.get("hand") or ()
            if isinstance(hand_index, int) and 0 <= hand_index < len(hand) and hand[hand_index]:
                card_id = int(hand[hand_index]["id"])
        if card_id is None and kind in {"ability", "skill"}:
            card_id = option_in_play_source_id(option, state.obs)
        recipient_id = None
        if kind == "attach":
            area = option.get("inPlayArea")
            index = option.get("inPlayIndex")
            bodies = (mine.get("active") if area == _ACTIVE else
                      mine.get("bench") if area == _BENCH else ()) or ()
            body = bodies[index] if isinstance(index, int) and 0 <= index < len(bodies) else None
            recipient_id = int(body["id"]) if body and body.get("id") is not None else None
        return terminal_effects_supported(
            state, action, card_id=card_id, recipient_id=recipient_id,
            effects=self.effects, stats=self.stats)

    def resolve_end(self, state, action):
        if end_has_forced_value_change(state, self.registry):
            return self.transition(state, action)
        return None


class BellmanCgpyProvider(CgpyTransitionProvider):
    def footprint(self, state, action):
        return action_footprint(state, action, cards=self.cards)

    def resolve_end(self, state, action):
        return self.transition(state, action)


_SEARCH_VARIANTS: dict[type, type] = {
    NativeCgTransitionProvider: BellmanNativeProvider,
    CgpyTransitionProvider: BellmanCgpyProvider,
}


def bellman_provider_factory(factory):
    """Map a runtime-configured live factory to its search-capable variant; the seam-mapping
    twin of ``common.ledger.seam.preview_provider_factory``. Unknown factories pass through."""
    if factory is None:
        return BellmanNativeProvider
    is_partial = isinstance(factory, partial)
    target = factory.func if is_partial else factory
    mapped = _SEARCH_VARIANTS.get(target)
    if mapped is None:
        return factory
    if is_partial:
        return partial(mapped, *factory.args, **factory.keywords)
    return mapped


__all__ = ("BellmanCgpyProvider", "BellmanNativeProvider", "bellman_provider_factory")
