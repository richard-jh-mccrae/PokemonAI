"""The preview seam: engine successors WITHOUT the per-node DecisionState build (ADR-0146).

Measured on the plain providers, ~0.3–0.5 ms of every ~0.8 ms preview node was
`with_observation` (the canonical walk) plus `semantic_key` (the hash walk) — paid only to key
the provider's engine map. The Ledger needs neither: the preview walk never merges
transpositions, so a per-successor identity token keys the map for free, and `PreviewState`
carries just the raw printout, the seat, and a lazily-enumerated menu. Bellman's own path is
untouched — it keeps DecisionState successors through the same `_bind`/`_key` hooks.

This module must stay free of any offline-engine reference: it ships in the Kaggle bundle,
whose packager scans content. Offline providers REGISTER their preview variants here
(`register_preview_variant`, done at the bottom of their own excluded-from-bundle modules)."""
from __future__ import annotations

from functools import partial
from itertools import count

from common.native_engine import NativeCgTransitionProvider
from common.options import enumerate_legal_actions


class PreviewState:
    """Everything a preview node is ever asked for: the printout, the seat, the menu."""

    __slots__ = ("obs", "root_seat", "preview_key", "_legal")

    def __init__(self, obs, root_seat: int, preview_key: str):
        self.obs = obs
        self.root_seat = int(root_seat)
        self.preview_key = preview_key
        self._legal = None

    @property
    def legal_actions(self) -> tuple:
        if self._legal is None:
            self._legal = enumerate_legal_actions(self.obs)
        return self._legal


class PreviewBinding:
    """Successors become PreviewStates; map keys become identity tokens (roots keep theirs)."""

    def _bind(self, state, observation):
        return PreviewState(observation, state.root_seat,
                            f"preview:{next(self._preview_tokens)}")

    def _key(self, state) -> str:
        key = getattr(state, "preview_key", None)
        return state.semantic_key if key is None else key


class LedgerNativeProvider(PreviewBinding, NativeCgTransitionProvider):
    backend = "native-cg-ledger"

    def __init__(self, root, **kwargs):
        self._preview_tokens = count()
        super().__init__(root, **kwargs)


_PREVIEW_VARIANTS: dict[type, type] = {NativeCgTransitionProvider: LedgerNativeProvider}


def register_preview_variant(base: type, variant: type) -> None:
    _PREVIEW_VARIANTS[base] = variant


def preview_provider_factory(factory):
    """The Ledger's provider for a runtime-configured factory: registered engine seams map to
    their preview variants; anything else (test doubles) is used as given, which is correct —
    just slower, since its successors carry full DecisionStates."""
    if factory is None:
        return LedgerNativeProvider
    target = getattr(factory, "func", factory)      # unwrap functools.partial
    mapped = _PREVIEW_VARIANTS.get(target)
    if mapped is None:
        return factory
    if hasattr(factory, "func"):                    # keep the partial's bound kwargs
        return partial(mapped, *factory.args, **factory.keywords)
    return mapped


__all__ = ("LedgerNativeProvider", "PreviewBinding", "PreviewState",
           "preview_provider_factory", "register_preview_variant")
