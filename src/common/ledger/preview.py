"""Price one option: the engine plays it, BoardState digests the reprint, the Ledger differences.

Every transition node the providers emit is priced here. A forced follow-up chain (Ultra Ball's
discard pick, then its fetch pick) is resolved inside the preview — each sub-menu chosen by the
same Ledger greedily, expected value at chance points — and the sub-choices are ADVISORY: the
real prompt re-decides on the real board when it arrives. A capped or unpriceable chain scores
the last board it could see and logs the gap; it never deletes the root option (the end-chain
lesson: a cap must not veto the action carrying the turn's value)."""
from __future__ import annotations

from dataclasses import dataclass

from common.algebra import (Actor, Chance, Choice, Deterministic, Refresh, RevealChoice,
                            Terminal, Unknown)
from common.board import BoardState
from common.solver import MAIN_DECISION_CONTEXT

from .chance import refresh_swing
from .evaluate import evaluate
from .worth import LedgerContext

CHAIN_DEPTH_CAP = 16
CHAIN_NODE_CAP = 128
#: Swings closer than this are one ULP-storm, not a preference (the float-noise-floor lesson).
NOISE_FLOOR = 1e-9


@dataclass(frozen=True)
class OptionPrice:
    action: object
    swing: float
    ends_turn: bool
    gaps: tuple[str, ...]


def price_actions(state, board: BoardState, baseline: float, provider,
                  ctx: LedgerContext) -> tuple[OptionPrice, ...]:
    prices = []
    for action in provider.actions(state):
        if action.identity.kind == "end":
            # The one free action: ending the turn is the zero every other option must beat.
            prices.append(OptionPrice(action, 0.0, True, ()))
            continue
        walk = _Walk(provider, ctx, board.decklist)
        value, ends_turn = walk.node(state, board, provider.transition(state, action),
                                     CHAIN_DEPTH_CAP)
        prices.append(OptionPrice(action, value - baseline, ends_turn, tuple(walk.gaps)))
    return tuple(prices)


class _Walk:
    """One root option's preview: a node budget, a gap log, and the recursion over nodes."""

    def __init__(self, provider, ctx: LedgerContext, decklist):
        self.provider = provider
        self.ctx = ctx
        self.decklist = decklist
        self.gaps: list[str] = []
        self.nodes = 0

    def node(self, state, board: BoardState, node, depth: int) -> tuple[float, bool]:
        self.nodes += 1
        if isinstance(node, Terminal):
            successor = board.advance(node.state.obs)
            return evaluate(successor, self.ctx).total, True
        if isinstance(node, Deterministic):
            return self.deterministic(node.state, board.advance(node.state.obs), depth)
        if isinstance(node, Chance):
            value, ends = 0.0, False
            for edge in node.children:
                child_value, child_ends = self.node(state, board, edge.node, depth - 1)
                value += edge.probability * child_value
                ends = ends or child_ends
            return value, ends
        if isinstance(node, Refresh):
            swing, gaps = refresh_swing(
                state.obs, board, 0.0, node.card_id, node.draws, node.opponent_shuffles,
                self.ctx, lambda synthetic: evaluate(synthetic, self.ctx))
            self.gaps.extend(gaps)
            return swing, False
        if isinstance(node, RevealChoice):
            by_label = {edge.label: edge.node for edge in node.choices}
            value = 0.0
            for outcome in node.outcomes:
                best = max(self.node(state, board, by_label[label], depth - 1)[0]
                           for label in outcome.choices)
                value += outcome.probability * best
            return value, False
        if isinstance(node, Choice):
            chooser = max if node.actor is Actor.OURS else min
            return chooser((self.node(state, board, edge.node, depth - 1)
                            for edge in node.children), key=lambda pair: pair[0])
        if isinstance(node, Unknown):
            self.gaps.append(f"unpriceable: {node.reason} ({node.missing_fact})")
            return evaluate(board, self.ctx).total, False
        self.gaps.append(f"unpriceable: undeclared node {type(node).__name__}")
        return evaluate(board, self.ctx).total, False

    def deterministic(self, state, board: BoardState, depth: int) -> tuple[float, bool]:
        context = int(((state.obs.get("select") or {}).get("context",
                                                           MAIN_DECISION_CONTEXT)))
        if context == MAIN_DECISION_CONTEXT:
            return evaluate(board, self.ctx).total, False
        if depth <= 0 or self.nodes >= CHAIN_NODE_CAP:
            self.gaps.append("chain capped; scored mid-effect board")
            return evaluate(board, self.ctx).total, False
        actions = self.provider.actions(state)
        if not actions:
            self.gaps.append("forced menu offered no actions; scored mid-effect board")
            return evaluate(board, self.ctx).total, False
        chooser = max if self.provider.actor(state) is Actor.OURS else min
        outcomes = (self.node(state, board, self.provider.transition(state, action),
                              depth - 1)
                    for action in actions)
        return chooser(outcomes, key=lambda pair: pair[0])


__all__ = ("CHAIN_DEPTH_CAP", "CHAIN_NODE_CAP", "NOISE_FLOOR", "OptionPrice", "price_actions")
