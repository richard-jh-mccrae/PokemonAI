"""Cross-check function tags against card rules-text — an *independent* oracle for the probe.

The tags are derived by **probing** the engine; we deliberately never parse text (it's lossy —
see docs/card-functions.md). That makes the text a perfect independent check: agreement raises
confidence, disagreement points at exactly the cards to inspect.

  * **unsupported** — a behavioral tag whose card text shows *no* supporting cue → suspect the
    probe produced a false positive (or the effect is on a part the text doesn't spell out).
  * **missing** — a *strong*, unambiguous text cue with *no* matching tag → suspect the probe
    missed it (precondition never aligned, evolution not reached, …).

Pure & lib-free: the caller passes each card's text. The lib shell that gathers engine text and
the frozen Bellman report lives under ``deprecated/bellman/tag_tools``. Heuristic, not a gate — text is noisy
(that's *why* we probe), so a flag means "inspect", not "wrong".
"""
from __future__ import annotations

# A damage-counter *move* (off mine, onto the opponent's) is self-heal + snipe — the Munkidori
# class. Reuse `heal`+`spread` for it (no new vocabulary), so cues below recognize it.
def _counter_move(t: str) -> bool:
    return "damage counter" in t and "move" in t

# Behavioral tag → broad predicate: is there *any* supporting cue? (the false-positive / unsupported
# check). Table is behavioral-only — structural facts (ex/trainer-type/ACE SPEC) aren't tagged.
_CUES = {
    "draw":            lambda t: "draw" in t or ("look at" in t and "into your hand" in t),
    "search":          lambda t: "search your deck" in t,
    # a `search` refinement: deck-search specifically for an Energy card INTO HAND. Deck-search
    # only — discard-pile retrieval is `recycle` and a top-N look is `dig`.
    "tutor_energy":    lambda t: "search your deck" in t and "energy" in t and "into your hand" in t,
    "dig":             lambda t: "look at the top" in t or "look at the bottom" in t,
    "heal":            lambda t: "heal" in t or ("remove" in t and "damage counter" in t)
                                 or _counter_move(t),
    "gust":            lambda t: "opponent" in t and ("switch" in t or "active spot" in t),
    "switch":          lambda t: "switch your active" in t or "switch this pokémon" in t
                                 or ("switch" in t and "benched" in t and "opponent" not in t),
    "poison":          lambda t: "poisoned" in t,
    "burn":            lambda t: "burned" in t,
    "sleep":           lambda t: "asleep" in t,
    "paralyze":        lambda t: "paralyzed" in t,
    "confuse":         lambda t: "confused" in t,
    # placing counters on bench / "in any way" / moving onto opponent — but not *preventing*
    # them (Battle Cage protects the bench; opposite of spread).
    "spread":          lambda t: "damage counter" in t and "prevent" not in t
                                 and ("bench" in t or "in any way" in t
                                      or ("move" in t and "opponent" in t)),
    "energy_accel":    lambda t: "attach" in t and "energy" in t,
    # denial = discarding the *opponent's* Energy ("Energy from 1 of your opponent's Pokémon"),
    # not self-mill ("Energy card you discarded") — require the "energy from … opponent" shape.
    "energy_denial":   lambda t: "discard" in t and "energy from" in t and "opponent" in t,
    # opponent's hand reset/discarded (Iono/Judge/Xerosic: "opponent … their hand … discard/
    # shuffle") — never a discard-*pile* clause (Levincia/Neutralization Zone reference that).
    "hand_disruption": lambda t: ("opponent" in t or "each player" in t) and "hand" in t
                                 and ("shuffle" in t or "discard" in t) and "discard pile" not in t,
    # *retrieving* from discard pile (into hand/deck/bench, yours or — both-player stadiums —
    # theirs), but never the negated "can't be put … from the discard pile" (Neutralization Zone).
    "recycle":         lambda t: "discard pile" in t and "can't" not in t
                                 and ("into your" in t or "into their" in t or "onto your bench" in t),
}
BEHAVIORAL = frozenset(_CUES)

# High-precision cues for the MISSING check — only tags whose phrasing rarely false-matches.
# `heal` is included only via specific phrasings, never the bare word, so it cannot over-flag.
_MISSING_CUES = {
    tag: _CUES[tag] for tag in
    ("poison", "burn", "sleep", "paralyze", "confuse", "spread", "search", "dig",
     "hand_disruption", "recycle", "energy_denial", "tutor_energy")
}
_MISSING_CUES["heal"] = lambda t: _counter_move(t) or ("heal" in t and "damage" in t)


def audit_card(tags, text: str) -> tuple[list[str], list[str]]:
    """``(unsupported, missing)`` for one card given its tags and rules text: a behavioral tag with no
    text cue, and a strong unambiguous cue with no tag. Pure; case-insensitive; tolerates empty."""
    t = (text or "").lower().replace("’", "'")   # normalize curly apostrophe -> cues match
    have = set(tags)
    unsupported = sorted(tag for tag in have if tag in BEHAVIORAL and not _CUES[tag](t))
    missing = sorted(tag for tag, cue in _MISSING_CUES.items() if tag not in have and cue(t))
    return unsupported, missing
