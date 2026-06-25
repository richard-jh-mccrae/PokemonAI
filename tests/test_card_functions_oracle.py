"""Golden oracle: a few unambiguous, deterministic cards must carry their function tag in the
*shipped* `card_functions.json` — an end-to-end regression gate over the whole
probe -> classify -> accumulate pipeline (the unit tests only cover the pure pieces).

Keyed by card *name* (survives reprints/id churn). On a Standard-format pool update these may
need refreshing — a failure means "a known tag disappeared", which is exactly worth a look.
Stochastic tags (recycle/energy_denial/heal) are deliberately excluded; they vary per build.
"""
import json
from pathlib import Path

import pytest

from meta_tracker.cards import load_cards

TABLE = Path(__file__).resolve().parents[1] / "my_submissions" / "common" / "card_functions.json"

# (card name, tag it must carry) — only reliable, deterministic tags.
ORACLE = [
    ("Ultra Ball", "search"),
    ("Switch", "switch"),
    ("Judge", "hand_disruption"),
    ("Judge", "draw"),
    ("Dragapult ex", "spread"),                 # Stage-2 costliest-attack spread (Phantom Dive)
    ("Munkidori", "confuse"),                   # Mind Bend → Confused (per-condition, not vague status)
    ("Drakloak", "draw"),                       # Stage-1 ability (Recon Directive — look top 2, draw 1)
    ("Fan Rotom", "search"),                    # basic ability (Fan Call)
    ("Teal Mask Ogerpon ex", "energy_accel"),   # basic ability (Teal Dance — a *true* accel)
    ("Tatsugiri", "dig"),                       # basic ability (Attract Customers)
    # curated overrides the probe can't reach (function_overrides.json) — guard they ship:
    ("Munkidori", "heal"),                      # Adrena-Brain: move counters off mine
    ("Munkidori", "spread"),                    # Adrena-Brain: ...onto the opponent's
    ("Enhanced Hammer", "energy_denial"),       # discards opponent's Special Energy
    ("Sacred Ash", "recycle"),                  # Pokémon from discard back to deck
    ("Telepath Psychic Energy", "search"),      # special Energy that tutors on attach (probe can't reach)
    ("Hop’s Bag", "search"),                    # name-restricted tutor the probe deck can't satisfy
    ("Thwackey", "search"),                     # precondition-gated tutor (Festival Lead)
    ("Xerosic’s Machinations", "hand_disruption"),
    ("Kyogre", "recycle"),
    ("Battle Cage", "bench_guard"),             # new vocab: protects the bench from attack/ability effects
    ("Meowth ex", "stall"),                     # play-role seed (curated, pending replay-usage)
    ("Mega Kangaskhan ex", "stall"),
    ("Dudunsparce", "stall"),
]


@pytest.fixture(scope="module")
def name_tags():
    cards = load_cards()
    table = {int(k): v for k, v in json.loads(TABLE.read_text(encoding="utf-8")).items()}
    nm2ids: dict[str, list[int]] = {}
    for cid, c in cards.items():
        nm2ids.setdefault(c.get("name"), []).append(cid)
    return nm2ids, table


@pytest.mark.req("REQ-FUNC-0013")
@pytest.mark.parametrize("name,tag", ORACLE)
def test_known_card_has_expected_tag(name, tag, name_tags):
    nm2ids, table = name_tags
    ids = nm2ids.get(name, [])
    assert ids, f"oracle card {name!r} not in the pool (rotated out? refresh the oracle)"
    assert any(tag in table.get(cid, []) for cid in ids), \
        f"{name!r} lost its {tag!r} tag (ids={ids}) — probe/classify pipeline regression?"
