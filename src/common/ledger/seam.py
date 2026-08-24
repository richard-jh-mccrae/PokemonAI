"""The preview seam: engine successors WITHOUT the per-node DecisionState build (ADR-0146).

The Ledger's preview needs neither the canonical state copy nor the semantic key the providers
built per successor to key their engine maps: the preview walk never merges transpositions, so
a per-successor identity token keys the map for free, and `PreviewState` carries just the raw
printout, the seat, and a lazily-enumerated menu. Bellman's own path is untouched — it keeps
DecisionState successors through the same `_bind`/`_key` hooks. Measurements live in ADR-0146.

This module must stay free of any offline-engine reference: it ships in the Kaggle bundle,
whose packager scans content. Offline providers REGISTER their preview variants here
(`register_preview_variant`, done at the bottom of their own excluded-from-bundle modules)."""
from __future__ import annotations

from functools import partial
from itertools import count

from common.native_engine import NativeCgTransitionProvider
from common.observation import ObservationStateBuilder
from common.observation.provider import ProviderState


class PreviewState(ProviderState):
    """Preview printout, seat, menu, and root deck knowledge for hidden-zone determinization.
    ObservationState supplies the root knowledge, avoiding DecisionState construction."""

    __slots__ = ("preview_key",)

    def __init__(self, payload, observation, preview_key: str, *,
                 deck=(), deck_counts=(), prize_counts=(), actor_seat=None,
                 belief_token=None, recycled_card_ids=(), **_ignored):
        if not hasattr(observation, "seat"):
            observation = ObservationStateBuilder(deck or None).root(payload)
        super().__init__(payload, observation, token=preview_key, deck=deck,
                         deck_counts=deck_counts, prize_counts=prize_counts,
                         actor_seat=actor_seat, belief_token=belief_token,
                         recycled_card_ids=recycled_card_ids)
        self.preview_key = preview_key

    @property
    def semantic_key(self) -> str:
        """The identity token doubles as the key for providers that were not remapped."""
        return self.preview_key


class PreviewBinding:
    """Successors become PreviewStates; map keys become identity tokens (roots keep theirs)."""

    def _bind(self, state, observation):
        child, _delta = ObservationStateBuilder(state.observation.decklist).advance(
            state.observation, observation)
        metadata = getattr(self, "_provider_metadata", {}).pop(id(observation), {})
        return PreviewState(observation, child, f"preview:{next(self._preview_tokens)}",
                            actor_seat=metadata.get("actor_seat"),
                            belief_token=metadata.get("belief_token"),
                            recycled_card_ids=metadata.get("recycled_card_ids", ()))

    def _key(self, state) -> str:
        key = getattr(state, "preview_key", None)
        return state.semantic_key if key is None else key


class LedgerNativeProvider(PreviewBinding, NativeCgTransitionProvider):
    backend = "native-cg-ledger"

    def __init__(self, root, **kwargs):
        # Identity keys never merge hidden worlds, and choosing per-world inside a forced menu
        # would decide on facts the player cannot know (strategy fusion). One world, always.
        if int(kwargs.get("world_count", 1)) != 1:
            raise ValueError("the preview seam is single-world (ADR-0146)")
        self._preview_tokens = count()
        super().__init__(root, **kwargs)


_PREVIEW_VARIANTS: dict[type, type] = {NativeCgTransitionProvider: LedgerNativeProvider}


def register_preview_variant(base: type, variant: type) -> None:
    _PREVIEW_VARIANTS[base] = variant


def preview_provider_factory(factory):
    """Map registered engine factories to preview variants.
    Preserve unregistered test doubles, whose successors may carry full DecisionStates."""
    if factory is None:
        return LedgerNativeProvider
    is_partial = isinstance(factory, partial)
    target = factory.func if is_partial else factory
    mapped = _PREVIEW_VARIANTS.get(target)
    if mapped is None:
        return factory
    if is_partial:                                  # keep the partial's bound kwargs
        return partial(mapped, *factory.args, **factory.keywords)
    return mapped


__all__ = ("LedgerNativeProvider", "PreviewBinding", "PreviewState",
           "preview_provider_factory", "register_preview_variant")
