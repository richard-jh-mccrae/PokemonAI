"""DOCTRINE: Shuffle-Refresh — ADR-0024. One file, end to end.

A Shuffle-Refresh Supporter shuffles your whole hand into the deck then draws (Lillie's Determination,
Judge, Harlequin, Lacey; Function Tag `shuffle_hand`). It presents NO select, so it is the Fetch
comparator's decision (A) ONLY — *whether to play it* — and it REUSES Fetch's `_grab_value_of` for the
gain side rather than restating a value model. The dominant misplay is refreshing away a working hand,
so v1 (Layer A) plays it ONLY when the hand is dead (`refresh-when-hand-is-dead` + the two keep-value
floors in `HYPOTHESES`). `ShuffleRefreshMixin` is the Pilot-side `Board.hand_is_dead` (a full real-menu
play-scan) + `deck_holds_a_need`. See docs/general-strategy.md and
docs/adr/0024-shuffle-refresh-is-fetch-decision-a-over-keep-value.md.
"""
from __future__ import annotations

from common.strategy.context import _ATTACH, _EVOLVE, _PLAY
from common.strategy.strategy import Hypothesis


class ShuffleRefreshMixin:
    """The Pilot-side closed-form half of the Shuffle-Refresh doctrine (mixed into `Pilot`). No new
    value model — `_deck_holds_a_need` reuses Fetch's `_grab_value_of`; `_hand_is_dead` scans the real
    menu through the shared `_option_trace`. Reads shared Pilot helpers + the per-decision `Board`."""

    def _has_shuffle_refresh(self, me: dict) -> bool:
        """True iff a Shuffle-Refresh (a `shuffle_hand`-tagged card) is in my hand — the cheap guard that
        gates the dead-hand scan (no refresh in hand -> the gate can never fire, so don't compute it)."""
        if not self.functions:
            return False
        return any(c and "shuffle_hand" in self.functions.tags(c.get("id"))
                   for c in (me.get("hand") or []))

    def _deck_holds_a_need(self, board, plan) -> bool:
        """True iff my deck still holds a card I currently LACK — any deck card with positive grab-value
        (`_grab_value_of`, the shared Fetch comparator). The gain-exists guard for the refresh: don't
        shuffle for a fresh hand when the deck has nothing left worth drawing. Skips provably-gone ids."""
        seen: set = set()
        for cid in self.deck:
            if cid in seen or cid in board.deck_empty_ids:
                continue
            seen.add(cid)
            if self._grab_value_of(board, cid, plan) > 0:
                return True
        return False

    def _hand_is_dead(self, obs: dict, select: dict, board) -> bool:
        """True iff NO option on the current menu develops the hand — no non-refresh PLAY / EVOLVE /
        ATTACH scores positive, and no Pokémon PLAY is even a (non-discouraged) development out. Scans the
        REAL menu options (so attach / evolve are seen with their true scores + tactical), the same
        scoring idiom as `_fetch_fills_a_need`. The Shuffle-Refresh fallback gate (ADR-0024): a refresh is
        reached only when nothing else is worth doing, so every useful play (develop / evolve / attach /
        fetch / gust KO / clutch heal) keeps the hand 'live'. ATTACK / RETREAT / END are excluded — they
        don't consume a hand card and coexist with a refresh (a dead-hand + lethal refreshes THEN attacks).
        The refresh cards themselves (`shuffle_hand`) are excluded, else a hand of only refreshes is never
        dead. A bare Pokémon bench-development isn't positively scored in SETUP, so it counts structurally."""
        for i, o in enumerate((select or {}).get("option") or []):
            if o.get("type") not in (_PLAY, _EVOLVE, _ATTACH):
                continue                                     # board actions coexist with a refresh
            cid = self._option_card_id(obs, select, o)
            tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
            if "shuffle_hand" in tags:                       # don't count the refresh as its own out
                continue
            score = self._option_trace(obs, select, board, o, i).score
            if score > 0:
                return False                                 # an endorsed play -> hand is live
            stat = self.stats.get(cid) if (self.stats and cid is not None) else None
            if o.get("type") == _PLAY and stat is not None and stat.hp > 0 and score >= 0:
                return False                                 # a (non-discouraged) Pokémon development -> live
        return True


# ── v1 = Layer A (the dead-hand fallback trigger) + the two explicit keep-value floors ──
HYPOTHESES = [
    Hypothesis(
        id="attach-before-hand-shuffle",
        rationale="Attach the Energy you are holding BEFORE playing a card that throws your hand away "
                  "(Function Tag `shuffle_hand`, e.g. Harlequin / Lillie's Determination — each "
                  "'shuffle your hand into your deck'). That card discards any Energy still in hand, "
                  "so playing it first wastes the attachment you could have made (and can shuffle away "
                  "a game-winning Energy). Fires only when a reusable Energy is in hand and you have "
                  "not yet attached this turn — weighted to push the hand-shuffle below an endorsed "
                  "attach AND below 0. Belt-and-suspenders: `_finish_turn_last` ALSO tiers any "
                  "`shuffle_hand` Supporter structurally (tier 3, after the tier-2 Energy attach), so "
                  "the attach precedes the shuffle even if this weight ever fails to fire; the weight "
                  "additionally GATES whether to refresh at all (don't, while a held Energy is unplaced).",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.reusable_energy_in_hand and not c.board.energy_attached,
        weight=-60, status="testing"),
    Hypothesis(
        id="hold-wincon-dont-shuffle",
        rationale="Don't shuffle a usable win-condition out of your hand with a hand-shuffling draw "
                  "Supporter (Function Tag `shuffle_hand`, e.g. Lillie's Determination / Judge — "
                  "'shuffle your hand into your deck'). When the win-condition (a Line payoff) is in "
                  "hand, refilling sends it back into the deck, costing the turn you could deploy it — "
                  "hold it and dig another way. Complements `attach-before-hand-shuffle` (which guards "
                  "held Energy) and `keep-key-cards-at-discard` (which guards a cost-discard): this "
                  "guards the hand-shuffle of the PAYOFF itself. Moderate — it nets negative against "
                  "`dig-before-commit` but is NOT absolute, so a genuinely dead hand still refills (the "
                  "win-condition returns to the deck, recoverable; only a tempo cost). Stands down when "
                  "the win-condition is already in PLAY (`wincon_in_play`): the hand copy is then a "
                  "redundant duplicate, safe to shuffle away — don't protect a dead second payoff (the "
                  "ep82226759 Harlequin shape: a Mega Starmie ex Active with a second copy in hand).",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.wincon_in_hand and not c.board.wincon_in_play,
        weight=-25, status="assumed"),
    Hypothesis(
        id="hold-wincon-with-base-dont-shuffle",
        rationale="Strengthen the hold (`hold-wincon-dont-shuffle`) when the held win-condition has a "
                  "base ALREADY IN PLAY to evolve it onto next turn — a Line pre-evolution on the Bench "
                  "(`line_preevo_in_play`, e.g. a benched Staryu under a Mega Starmie ex in hand). Then "
                  "the shuffle is not a mere recoverable tempo cost: it shuffles away the payoff of a "
                  "concrete, imminent evolution (the base is being built — energise it, evolve it, "
                  "attack), so HOLD it firmly and take the board action (a developing attack / attach) "
                  "this turn instead. Stacks on the base hold (−25) to net the `shuffle_hand` PLAY below "
                  "0 even against `dig-before-commit` (+20) + `refresh-when-hand-is-dead` (+8) — so "
                  "`_finish_turn_last` tiers it BELOW the attack (the develop-then-deploy line), the "
                  "ep82867148 f52 shape (3 Mega in hand, a benched Staryu, Turbo Flare available). "
                  "Narrow: a base in PLAY plus the payoff in hand is the high-confidence deploy-soon "
                  "case; with no base in play the moderate base hold still allows a dead-hand refill.",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.wincon_in_hand and c.board.line_preevo_in_play and not c.board.wincon_in_play,
        weight=-15, status="testing"),
    Hypothesis(
        id="refresh-when-hand-is-dead",
        rationale="Play a Shuffle-Refresh (Function Tag `shuffle_hand`, e.g. Lillie's Determination / "
                  "Judge — 'shuffle your hand into your deck, then draw') ONLY when your hand is dead: no "
                  "other card in it yields a positive-scoring play this turn (`Board.hand_is_dead`, a full "
                  "play-scan of the hand) AND the deck still holds a card you lack (`deck_holds_a_need`). "
                  "ADR-0024 decision (A) — a refresh is not a dig (it DESTROYS the hand), so it is a "
                  "last-resort hand reload, reached only when nothing else is worth doing; this is 'use "
                  "your key cards first' proven structurally (every useful card outscores the refresh). "
                  "Reuses the Fetch keep-value comparator: a live card keeps the hand off this gate, so we "
                  "never shuffle away a hand we'd fetch back. Small positive — beats End (≈0), loses to any "
                  "real play; a dead hand can't contain a better Supporter, so the one-per-turn slot "
                  "economy is subsumed. Never preempts an attack (the scan is hand-only; the turn-ending "
                  "attack stays a last-tier `_finish_turn_last` commitment, after the tier-3 shuffle, so a "
                  "dead-hand + lethal refreshes THEN KOs the same turn). Layer A; the stochastic pull-EV "
                  "refinement is deferred.",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.hand_is_dead and c.board.deck_holds_a_need,
        weight=8, status="testing"),
]
