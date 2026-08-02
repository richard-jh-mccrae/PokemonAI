"""Playability — BACKWARD line topology: can a card held in hand ever reach the board at all?
(ADR-0103, Issue #288; the term-sufficiency audit's finding F12.)

`development.line_topology` asks the FORWARD question — is this line's payoff still reachable? This
module is its mirror, and until Issue #288 nothing asked it: an Evolution card realises nothing at
all unless a body it can be put onto can itself reach the board. `slowking` runs 2× Metagross
(``evolvesFrom`` **Metang**, verified at ``data/EN_Card_Data.csv`` id 276) and lists neither Metang
nor Beldum, so both copies are 170-HP dead cards for the whole match; every other deck reaches the
same state transiently the moment a line's base is prized or discarded out.

Pure over the card pool and three ZONE reads — the caller resolves the zones (the `gate_library`
pattern) and this module owns only the graph walk:

* **the chain, not one hop.** A Metang in hand does not make a Metagross playable when every Beldum
  is gone: the Metang cannot reach the board either, so neither can what sits on top of it. Each
  step grounds out the moment it finds a body already IN PLAY (nothing further is owed) or a Basic.
* **the Rare Candy escape.** *"Choose 1 of your Basic Pokémon in play. If you have a Stage 2 card in
  your hand that evolves from that Pokémon, put that card onto the Basic Pokémon to evolve it,
  skipping the Stage 1"* (card text, ``data/EN_Card_Data.csv`` id 1079). A missing Stage 1 therefore
  does NOT prove a Stage 2 dead, and `grimmsnarl_ex` — 1 Rare Candy plus the Marnie's Impidimp ->
  Morgrem -> Grimmsnarl ex line — is a shipped deck that reaches exactly that board. Omitting the
  escape would have made this gate strip a deck's win condition while the enabler sat in hand, which
  is a worse error than the one it fixes.
* **fail OPEN — *unreadable is not unplayable*.** An unknown card, or one whose ``evolvesFrom`` names
  a card the pool holds no printing of, makes NO claim and keeps everything. Only a base that is
  **provably** absent from all three zones takes anything away. Same direction as
  `gate_library.deploy_odds`, and for the same reason: a missed slot sheds a good card, which is the
  wrong way to be wrong. `Zones.rare_candy` carries the same rule for the escape itself: it is
  TRI-STATE, and ``None`` (no Function Tag table to read) keeps the escape open rather than
  collapsing to "no Rare Candy". Holding that epistemic HERE rather than at each call site is what
  stops two callers of one oracle from failing in opposite directions.

**Deliberately NOT an escape: the `opener` route.** Cinderace (id 666, Stage 2, ``evolvesFrom``
Raboot) carries *Explosiveness* — *"If this Pokémon is in your hand when you are setting up to play,
you may put it face down in the Active Spot"* (card text verified) — and `mega_starmie` runs 4 with
no Raboot on the list. It is nonetheless correctly UNPLAYABLE here, because this oracle answers "can
it be played **from hand**", and Explosiveness is not that route: it reaches only the ACTIVE spot,
only during Set Up, before any consumer of this module runs. Every site that asks — the discard and
refresh keep-value sites (mid-match) and `_deploy_decision` (BENCH capacity) — is a place a
setup-only opener genuinely cannot go. The shipped `dont-fetch-the-setup-only-opener` rung rests on
exactly this reading (*"in hand it is a dead card"*), and ADR-0081's `_route_only_at_setup` is where
the Set-Up route is modelled instead.

The deck zone must be the SOUND *"not provably gone"* read (the tracker's exact unseen counts, or
the decklist minus what is visible) — never *"seen"*. A base sitting in the discard with a copy
still unseen in deck or a face-down prize is still reachable, and calling it gone would shed a live
card on a guess.

Names, not ids, throughout: an evolution identifies its previous stage by NAME
(``CardStat.evolvesFrom``) and reprints share a name across ids — Beldum is both 85 and 274 — so an
id-keyed walk would miss the reprint. This is the same rule `_deck_body_names` records.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The Function Tag marking a card that puts a Stage 2 from hand straight onto its root Basic
#: (Rare Candy, id 1079 — the pool's only printing today). A tag rather than a hard-coded id so the
#: behavioural claim lives where every other one does (ADR-0006).
RARE_CANDY_TAG = "rare_candy"


@dataclass(frozen=True)
class Zones:
    """Where a card can be found, as card NAMES, plus what is known about Rare Candy.

    ``in_play`` and ``reachable`` are deliberately separate rather than unioned: a base already IN
    PLAY ends the walk (there is nothing left to assemble under it), while a base merely reachable
    still owes its own playability, which is what makes the chain a chain.

    ``rare_candy`` is TRI-STATE, and the third state is the one that matters. ``True`` = one is
    reachable, ``False`` = provably none, ``None`` = **the caller could not tell** (no Function Tag
    table). A missing tag table is missing EVIDENCE, so it must not read as "no Rare Candy" — that
    would let the gate call a Stage 2 dead on the strength of a fact it never checked. ``None``
    therefore keeps the escape open for Stage 2s and changes nothing for any other card, which is
    both fail directions correct at once and, being inside the oracle, identical for every caller.
    """
    in_play: frozenset
    reachable: frozenset            # in hand, or still "not provably gone" from the deck
    rare_candy: bool | None = None


def zones(stats, *, in_play_ids=(), hand_ids=(), deck_ids=(), rare_candy_reachable=None) -> Zones:
    """Build the `Zones` name-sets from id iterables, resolved through ``stats``.

    ``rare_candy_reachable`` is the caller's read of whether a `RARE_CANDY_TAG` card is in hand or
    still unseen in deck — it needs the Function Tag table, which this module deliberately does not
    take (it stays pure over the stat pool). Pass ``None`` when there is no table to read."""
    def _names(ids) -> frozenset:
        found = set()
        for i in (ids or ()) if stats is not None else ():
            st = stats.get(i) if i is not None else None
            if st is not None and getattr(st, "name", None):
                found.add(st.name)
        return frozenset(found)

    return Zones(in_play=_names(in_play_ids),
                 reachable=_names(hand_ids) | _names(deck_ids),
                 rare_candy=None if rare_candy_reachable is None else bool(rare_candy_reachable))


def playable_from_hand(cid, *, stats, zones: Zones) -> bool:
    """Can the card ``cid``, held in hand, EVER be put into play?

    True for everything that is not an Evolution Pokémon (a Basic needs only a Bench slot; a Trainer
    or Energy needs nothing this question can answer) and for every Evolution whose chain still
    grounds out. False ONLY when the chain is provably broken — see the module docstring for the
    three rules that decide that."""
    if stats is None or cid is None:
        return True
    return _playable(stats.get(cid), stats=stats, zones=zones, seen=frozenset())


def _playable(stat, *, stats, zones: Zones, seen: frozenset) -> bool:
    """The recursion. ``seen`` carries the previous-stage NAMES already on this path, so a malformed
    pool where two cards evolve from each other terminates (and grounds out unplayable — such a
    chain never reaches a Basic, exactly as `_stranded_evolution_set` has always ruled)."""
    base = getattr(stat, "evolvesFrom", None) if stat is not None else None
    if not base:
        return True                       # unknown card, Trainer/Energy, or a Basic — no claim owed
    base_ids = stats.ids_for_name(base)
    if not base_ids:
        return True                       # unreadable is not unplayable
    if base in zones.in_play:
        return True                       # the body is already down; evolve onto it
    if base not in seen and base in zones.reachable and any(
            _playable(stats.get(i), stats=stats, zones=zones, seen=seen | {base})
            for i in base_ids):
        return True
    return _rare_candy_reaches(stat, stats=stats, zones=zones, base_ids=base_ids)


def _rare_candy_reaches(stat, *, stats, zones: Zones, base_ids) -> bool:
    """The Stage-2 escape: with a Rare Candy reachable, a Stage 2 needs only its ROOT Basic, not the
    Stage 1 in between. The root is read off the chain (some printing of the Stage 1 whose own
    ``evolvesFrom`` names it) rather than declared, so it cannot drift from the card data — the same
    two-hop verification `planner._stage2_roots_at` does for the Rare Candy KO line.

    The root is confirmed to BE a Basic (`_is_basic`) rather than assumed to be one from its position
    two hops down. The card says *"Choose 1 of your Basic Pokémon in play"*, and a chain deeper than
    Basic → Stage 1 → Stage 2 would otherwise let this escape fire on a body Rare Candy cannot
    legally target."""
    if zones.rare_candy is False or not getattr(stat, "stage2", False):
        return False
    if zones.rare_candy is None:
        return True                   # no tag table to read — no claim about the escape either way
    for s1_id in base_ids:
        s1 = stats.get(s1_id)
        root = getattr(s1, "evolvesFrom", None) if s1 is not None else None
        if root and _is_basic(root, stats) and (root in zones.in_play or root in zones.reachable):
            return True
    return False


def _is_basic(name, stats) -> bool:
    """Some printing under ``name`` is a Basic Pokémon — it evolves from nothing. Truthiness, not
    ``is None``, so this module and `gate_library.is_evolution` cannot disagree about a card whose
    ``evolvesFrom`` is an empty string."""
    return any(not getattr(stats.get(i), "evolvesFrom", None) for i in stats.ids_for_name(name))
