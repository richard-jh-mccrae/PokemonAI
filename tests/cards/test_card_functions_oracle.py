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

from common.scouting.card_text import normalize_card_name
from meta_tracker.cards import load_cards

TABLE = Path(__file__).resolve().parents[2] / "src" / "common" / "card_functions.json"

# (card name, tag it must carry) — only reliable, deterministic tags.
ORACLE = [
    ("Ultra Ball", "search"),
    ("Switch", "switch"),
    ("Judge", "hand_disruption"),
    ("Judge", "draw"),
    ("Dragapult ex", "spread"),                 # Stage-2 costliest-attack spread (Phantom Dive)
    ("Munkidori", "confuse"),                   # Mind Bend -> Confused (per-condition, not vague status)
    ("Drakloak", "draw"),                       # Stage-1 ability (Recon Directive — look top 2, draw 1)
    ("Fan Rotom", "search"),                    # basic ability (Fan Call)
    ("Teal Mask Ogerpon ex", "energy_accel"),   # basic ability (Teal Dance — a *true* accel)
    ("Tatsugiri", "dig"),                       # basic ability (Attract Customers)
    # curated overrides the probe can't reach (function_overrides.json) — guard they ship:
    ("Munkidori", "heal"),                      # Adrena-Brain: moves counters off mine
    ("Munkidori", "spread"),                    # Adrena-Brain: ...onto opponent's
    # tutor_energy — deck-search an Energy card into hand (`search` refinement, curated in
    # function_overrides.json; probe only sees the generic DECK→HAND move). Enables the Turn
    # Planner's Supporter-enabled KO line (ADR-0031). Discard-pile energy retrieval stays `recycle`,
    # top-N look stays `dig`, Pokémon energy-tutor attacks/abilities out of scope (not a
    # Trainer play-event) — none of those carry this tag.
    ("Energy Search", "tutor_energy"),          # Item: search a Basic Energy → hand
    ("Energy Search Pro", "tutor_energy"),      # Item (ACE SPEC): any # of Basic Energy → hand
    ("Fighting Gong", "tutor_energy"),          # Item: a Basic {F} Energy or {F} Basic → hand
    ("Colress’s Tenacity", "tutor_energy"),     # Supporter: a Stadium + an Energy → hand
    ("Crispin", "tutor_energy"),                # Supporter: 2 Basic Energy → 1 to hand, 1 attached
    ("Larry’s Skill", "tutor_energy"),          # Supporter: Pokémon + Supporter + Basic Energy → hand
    ("Ethan's Adventure", "tutor_energy"),      # Supporter: Ethan's Pokémon / Basic {R} Energy → hand
    ("Hilda", "tutor_energy"),                  # Supporter: an Evolution + an Energy → hand (fixed 4298)
    ("Firebreather", "tutor_energy"),           # Supporter: up to 7 Basic {R} Energy → hand
    ("Enhanced Hammer", "energy_denial"),       # discards opponent's Special Energy
    ("Sacred Ash", "recycle"),                  # Pokémon from discard back to deck
    ("Telepath Psychic Energy", "search"),      # special Energy that tutors on attach (probe can't reach)
    ("Hop’s Bag", "search"),                    # name-restricted tutor, probe deck can't satisfy
    ("Thwackey", "search"),                     # precondition-gated tutor (Festival Lead)
    ("Xerosic’s Machinations", "hand_disruption"),
    ("Kyogre", "recycle"),
    ("Battle Cage", "bench_guard"),             # new vocab: protects bench from attack/ability effects
    ("Cinderace", "opener"),                    # new vocab: Explosiveness — non-Basic that may open (curated override)
    ("Meowth ex", "supporter_tutor"),           # Last-Ditch Catch: bench-drop → fetch a Supporter
    #                                             (was `stall`; re-modeled 2026-07-03, STRATEGY.md §3)
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


@pytest.mark.req("REQ-FUNC-0013")
def test_team_rocket_tag_covers_the_whole_POKEMON_family_and_nothing_else(name_tags):
    """**Issue #374 — the owner-family membership index, as a Function Tag.**

    Nine cards in the pool gate an effect on *"Team Rocket's Pokemon"* — 15 Team Rocket's Energy
    (attach-legal only to one), 414 Articuno, 431 Mewtwo ex (*can't attack unless you have 4 or more
    in play*), 436 Orbeetle, 1154 Hypnotizer, 1216 Ariana, 1217 Archer, 1218 Giovanni, 1220 Proton.

    **What was missing is narrower than "nothing could answer it", and the narrower claim is the true
    one.** For a body already IN PLAY the question is free: the dump carries `name`, `CardStat.name`
    holds it, and `provider.applies_to_holder` already answers it through
    `card_text.name_in_family`. What has no answer is the HIDDEN-DECK half — *"search your deck for
    up to 3 Basic Team Rocket's Pokemon"* (1220) — because deciding which unseen cards qualify needs
    an index over the POOL, not a test against one visible name. That is the *"no build-time family
    index over the pool"* Issue #301 recorded, and why those cards' clause sets could only be
    `partial`. No STRUCTURAL field can supply it: the dump carries
    `stage`/`ex`/`megaEx`/`tera`/`aceSpec`/`evolvesFrom`/`energy` and nothing naming an owner family,
    and the 52 members spread across 8 different energy types.

    The tag IS that index. Derived here from the printed name rather than from a pasted id list, so
    the assertion re-derives the population instead of agreeing with whatever was committed.

    **Two deliberate exclusions, asserted so neither reads as an oversight.** 1256 Team Rocket's
    Watchtower is a NAME red herring: its text is *"{C} Pokemon in play (both yours and your
    opponent's) have no Abilities"*, which runs no membership test at all. 1257 Factory and 1134
    Transceiver run a DIFFERENT test — substring *"Team Rocket"* over SUPPORTER NAMES — which the
    developer ruled out of scope for the stadium."""
    nm2ids, table = name_tags
    # `normalize_card_name` is the ONE apostrophe-folding implementation (the pool mixes U+2019,
    # U+02BC and ASCII WITHIN one family). Imported rather than restated — a second transcription is
    # the drift `unknown_zones` exists to prevent, one store over.
    family = sorted(cid for name, ids in nm2ids.items() for cid in ids
                    if normalize_card_name(name).startswith("Team Rocket's "))
    assert len(family) == 65, f"the printed-name family moved: {len(family)}"

    cards = load_cards()
    pokemon = [c for c in family if cards[c].get("category") == "pokemon"]
    assert len(pokemon) == 52, f"the POKEMON half moved: {len(pokemon)}"
    missing = [c for c in pokemon if "team_rocket" not in table.get(c, [])]
    assert missing == [], f"Team Rocket's Pokemon with no `team_rocket` tag: {missing}"

    # …and nothing OUTSIDE that set carries it — a tag that leaked onto the Trainers would answer
    # "is this a Team Rocket's Pokemon?" with a false yes, which is the direction a membership
    # oracle must never fail in.
    tagged = sorted(cid for cid, tags in table.items() if "team_rocket" in tags)
    assert tagged == pokemon, f"tagged but not a Team Rocket's Pokemon: {set(tagged) - set(pokemon)}"

    # The named exclusions, by id, so a later sweep does not have to rediscover why they are absent.
    for cid in (1256, 1257, 1134):
        assert "team_rocket" not in table.get(cid, []), cid
    # Positive control on the same run: the exclusion assertion above is discriminating, not vacuous
    # — these three ARE in the pool and two of them DO carry other tags.
    assert all(cid in cards for cid in (1256, 1257, 1134))
    assert table.get(1134) == ["search"], table.get(1134)
