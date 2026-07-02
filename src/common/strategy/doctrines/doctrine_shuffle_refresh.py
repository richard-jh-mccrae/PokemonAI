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
            if "shuffle_hand" in tags:                       # don't count refresh as its own out
                continue
            score = self._option_trace(obs, select, board, o, i).score
            if score > 0:
                return False                                 # endorsed play -> hand is live
            stat = self.stats.get(cid) if (self.stats and cid is not None) else None
            if o.get("type") == _PLAY and stat is not None and stat.hp > 0 and score >= 0:
                return False                                 # non-discouraged Pokémon development -> live
        return True


# ── v1 = Layer A (dead-hand fallback trigger) + the two explicit keep-value floors ──
HYPOTHESES = [
    Hypothesis(
        id="attach-before-hand-shuffle",
        rationale="Attach held Energy BEFORE playing a `shuffle_hand` card (Harlequin / Lillie's "
                  "Determination), since that card discards any Energy still in hand — playing it first "
                  "wastes the attach and can shuffle away a game-winning Energy. Fires only with a "
                  "reusable Energy in hand, not yet attached this turn; belt-and-suspenders with "
                  "`_finish_turn_last`'s structural tiering (tier 3 shuffle after tier-2 attach). Stands "
                  "down when the Energy has NO placeable home (`not energy_placeable`), so it never vetoes "
                  "a bench-finding refresh (ep83038055 f40).",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.reusable_energy_in_hand and not c.board.energy_attached
        and c.board.energy_placeable,
        weight=-60, status="testing"),
    Hypothesis(
        id="hold-wincon-dont-shuffle",
        rationale="Don't shuffle a usable win-condition (a Line payoff) out of hand with a `shuffle_hand` "
                  "Supporter — refilling sends it back into the deck, costing the turn to deploy it, so "
                  "hold it and dig another way. Moderate (nets negative against `dig-before-commit` but "
                  "not absolute, so a genuinely dead hand still refills); stands down when the "
                  "win-condition is already in PLAY (`wincon_in_play`) — a redundant hand duplicate is "
                  "safe to shuffle (the ep82226759 Harlequin shape: Mega Starmie ex Active, second copy in "
                  "hand).",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.wincon_in_hand and not c.board.wincon_in_play,
        weight=-25, status="assumed"),
    Hypothesis(
        id="hold-wincon-with-base-dont-shuffle",
        rationale="Strengthen `hold-wincon-dont-shuffle` when the win-condition's base is ALREADY IN PLAY "
                  "to evolve onto next turn (`line_preevo_in_play`, e.g. benched Staryu under a Mega "
                  "Starmie ex in hand) — this is a concrete imminent evolution, not just recoverable "
                  "tempo, so hold firmly and develop instead. Stacks on the base hold (−25) to net the "
                  "shuffle below 0 even against `dig-before-commit` (+20) + `refresh-when-hand-is-dead` "
                  "(+8), tiering it below the attack (ep82867148 f52: 3 Mega in hand, benched Staryu, "
                  "Turbo Flare available); narrow to base-in-play, else the moderate hold still allows a "
                  "dead-hand refill.",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.wincon_in_hand and c.board.line_preevo_in_play and not c.board.wincon_in_play,
        weight=-15, status="testing"),
    Hypothesis(
        id="refresh-when-hand-is-dead",
        rationale="Play a Shuffle-Refresh (Function Tag `shuffle_hand`) ONLY when the hand is dead — no "
                  "card yields a positive-scoring play (`Board.hand_is_dead`, a full play-scan) AND the "
                  "deck still holds a needed card (`deck_holds_a_need`) — ADR-0024 decision (A): a refresh "
                  "DESTROYS the hand, so it's last-resort, reusing the Fetch keep-value comparator so a "
                  "live card is never shuffled away. Small positive (beats End, loses to any real play); "
                  "never preempts an attack, since `_finish_turn_last` keeps the attack after the tier-3 "
                  "shuffle so a dead-hand + lethal refreshes THEN KOs same turn. Layer A; stochastic "
                  "pull-EV refinement deferred.",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.hand_is_dead and c.board.deck_holds_a_need,
        weight=8, status="testing"),
    Hypothesis(
        id="hold-successor-when-doomed",
        rationale="Don't shuffle away the hand when the Active win-condition is DOOMED and the hand holds "
                  "the rebuild successor (`wincon_in_hand` PLUS `line_preevo_in_play`) — the case the "
                  "other holds miss, since they stand down once the win-condition is in PLAY, but an "
                  "about-to-be-KO'd in-play copy makes the hand copy the NEXT attacker, not a redundant "
                  "duplicate. Also fixes a dead-hand-scan false positive (`refresh-when-hand-is-dead` +8 "
                  "fires post-attach though the hand holds what's needed next turn): hold the successor "
                  "and develop instead (ep83037962 f49 — Harlequin gambling away a benchable Mega Starmie "
                  "ex + two Water). Weighted (−35) to net below 0 against `dig-before-commit` (+20) + "
                  "`refresh-when-hand-is-dead` (+8); narrow, so a healthy board still cycles freely.",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.active_doomed and c.board.wincon_in_hand and c.board.line_preevo_in_play,
        weight=-35, status="testing"),
]
