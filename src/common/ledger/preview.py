"""Price one option: the engine plays it, BoardState digests the reprint, the Ledger differences.

Every transition node the providers emit is priced here. A forced follow-up chain (Ultra Ball's
discard pick, then its fetch pick) is resolved inside the preview — each sub-menu chosen by the
same Ledger greedily, expected value at chance points — and the sub-choices are ADVISORY: the
real prompt re-decides on the real board when it arrives. A capped or unpriceable chain scores
the last board it could see and logs the gap; it never deletes the root option (the end-chain
lesson: a cap must not veto the action carrying the turn's value)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from common.algebra import (Actor, Chance, Choice, Deterministic, Refresh, RevealChoice,
                            Terminal, Unknown)
from common.board import BoardState
from common.strategy.context import _MAIN

from .chance import refresh_value
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
        swing = value - baseline
        if not math.isfinite(swing):
            # Belt behind the weights' finite check: a NaN/inf swing would make every price
            # unrankable. Score neutral, SAY SO — a visible gap, never a silent absorb.
            walk.gaps.append(f"non-finite price for {action.identity}; scored zero")
            swing = 0.0
        prices.append(OptionPrice(action, swing, ends_turn, tuple(walk.gaps)))
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
        # The budget binds EVERY recursive node type, not just forced-menu walks: a wide or
        # nested chance tree must also land on the cap instead of running past it.
        if depth <= 0 or self.nodes >= CHAIN_NODE_CAP:
            if isinstance(node, Deterministic):
                board = board.advance(node.state.obs)
            self.gaps.append("chain capped; scored mid-effect board")
            return evaluate(board, self.ctx).total, False
        if isinstance(node, Deterministic):
            return self.deterministic(node.state, board.advance(node.state.obs), depth)
        if isinstance(node, Chance):
            value, ends = 0.0, False
            for edge in node.children:
                child_value, child_ends = self.node(state, board, edge.node, depth - 1)
                value += edge.probability * child_value
                # MAY-end counts as ends: never gamble the turn away while a sure positive
                # turn-continuing play remains (the attack-last lesson).
                ends = ends or child_ends
            return value, ends
        if isinstance(node, Refresh):
            value, gaps = refresh_value(
                state.obs, board, node.card_id, node.draws, node.opponent_shuffles,
                lambda synthetic: evaluate(synthetic, self.ctx))
            self.gaps.extend(gaps)
            return value, False
        if isinstance(node, RevealChoice):
            chooser = max if node.actor is Actor.OURS else min
            priced = {edge.label: self.node(state, board, edge.node, depth - 1)
                      for edge in node.choices}
            value, ends = 0.0, False
            for outcome in node.outcomes:
                best_value, best_ends = chooser((priced[label] for label in outcome.choices),
                                                key=lambda pair: pair[0])
                value += outcome.probability * best_value
                # MAY-end counts as ends here too: the leg the revealed set selects decides.
                ends = ends or best_ends
            return value, ends
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
        raw_context = (state.obs.get("select") or {}).get("context")
        context = _MAIN if raw_context is None else int(raw_context)
        if context == _MAIN:
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
