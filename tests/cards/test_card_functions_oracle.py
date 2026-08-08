"""Golden oracle: a few unambiguous, deterministic cards must carry their function tag in the
*shipped* `card_functions.json` — an end-to-end regression gate over the whole
probe -> classify -> accumulate pipeline (the unit tests only cover the pure pieces).

Keyed by card *name* (survives reprints/id churn). On a Standard-format pool update these may
need refreshing — a failure means "a known tag disappeared", which is exactly worth a look.
Stochastic tags (recycle/energy_denial/heal) are deliberately excluded; they vary per build.
"""
import json
import re
from pathlib import Path

import pytest

import build_card_functions            # the real builder: its loaders and its two default paths
from common import card_tags
from common.scouting.card_text import normalize_card_name
# The classifier's OWN derived set, imported rather than re-transcribed — a second copy of it is the
# drift `unsourced_tag_instances` exists to detect (Issue #395 D6.1).
from meta_tracker.card_functions import DERIVED_TAGS
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
    # tutor_energy — a `search` refinement, curated because the probe only sees the generic
    # DECK->HAND move. Discard-pile retrieval stays `recycle` and a top-N look stays `dig`.
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
    """The tag is the POOL-wide family index the HIDDEN-DECK half needs; a body already in play is
    answered by `card_text.name_in_family`. Derived from the printed name, never a pasted id list."""
    nm2ids, table = name_tags
    # `normalize_card_name` is the ONE apostrophe-folding implementation (the pool mixes U+2019,
    # U+02BC and ASCII WITHIN one family), imported rather than restated.
    family = sorted(cid for name, ids in nm2ids.items() for cid in ids
                    if normalize_card_name(name).startswith("Team Rocket's "))
    assert len(family) == 65, f"the printed-name family moved: {len(family)}"

    cards = load_cards()
    pokemon = [c for c in family if cards[c].get("category") == "pokemon"]
    assert len(pokemon) == 52, f"the POKEMON half moved: {len(pokemon)}"
    missing = [c for c in pokemon if "team_rocket" not in table.get(c, [])]
    assert missing == [], f"Team Rocket's Pokemon with no `team_rocket` tag: {missing}"

    # …and nothing OUTSIDE that set carries it: a false YES is the direction a membership oracle
    # must never fail in.
    tagged = sorted(cid for cid, tags in table.items() if "team_rocket" in tags)
    assert tagged == pokemon, f"tagged but not a Team Rocket's Pokemon: {set(tagged) - set(pokemon)}"

    # The named exclusions, by id, so a later sweep does not have to rediscover why they are absent.
    for cid in (1256, 1257, 1134):
        assert "team_rocket" not in table.get(cid, []), cid
    # Positive control on the same run: the exclusion assertion above is discriminating, not vacuous
    # — these three ARE in the pool and two of them DO carry other tags.
    assert all(cid in cards for cid in (1256, 1257, 1134))
    assert table.get(1134) == ["search"], table.get(1134)


# --- override <-> table reconciliation (REQ-FUNC-0016, Issue #375) ----------------------------

def _unreconciled(overrides: dict[int, list[str]],
                  table: dict[int, list[str]]) -> dict[int, list[str]]:
    """``{cardId: [curated tags absent from the shipped table]}`` — empty iff the two stores agree."""
    out = {}
    for cid, tags in overrides.items():
        shipped = set(table.get(cid, []))
        gap = [t for t in tags if t not in shipped]
        if gap:
            out[cid] = gap
    return out


@pytest.mark.req("REQ-FUNC-0016")
def test_every_curated_override_tag_reached_the_shipped_table():
    """`function_overrides.json` is a standing INSTRUCTION to the builder, not a record: a tag left
    there after being retired is a pending re-introduction the next build applies."""
    overrides = build_card_functions._load_overrides(build_card_functions.DEFAULT_OVERRIDES)
    table = build_card_functions._load_table(build_card_functions.DEFAULT_OUT)
    # Guard the instrument before trusting its silence: an empty read of either store would make the
    # reconciliation below vacuously green.
    assert len(overrides) > 50, f"override store looks unread: {len(overrides)} numeric keys"
    assert len(table) > 50, f"shipped table looks unread: {len(table)} cards"

    assert _unreconciled(overrides, table) == {}, (
        "curated override tags that never reached the shipped table — the next "
        "`python tools/build_card_functions.py` will ADD them; reconcile the two stores")

    # Positive control on the same run: an empty result above must mean "they agree", not "the sweep
    # cannot see a divergence". Both shapes a real divergence takes are injected and must be caught.
    seeded = dict(overrides)
    a_real_card = min(overrides)
    seeded[a_real_card] = list(overrides[a_real_card]) + ["__never_a_real_tag__"]
    seeded[10 ** 9] = ["__override_for_a_card_the_table_lacks__"]
    assert _unreconciled(seeded, table) == {
        a_real_card: ["__never_a_real_tag__"],
        10 ** 9: ["__override_for_a_card_the_table_lacks__"],
    }


@pytest.mark.req("REQ-FUNC-0016")
def test_meowth_ex_does_not_carry_the_retired_stall_play_role(name_tags):
    """The reason is recorded once at the point of temptation, `_note_1071_stall_retired` in
    `function_overrides.json`. The consumer that moves is `Pilot._is_draw_engine_body`."""
    nm2ids, table = name_tags
    ids = nm2ids.get("Meowth ex", [])
    assert ids, "Meowth ex not in the pool (rotated out? refresh the oracle)"
    for cid in ids:
        assert "stall" not in table.get(cid, []), \
            f"Meowth ex ({cid}) carries the retired `stall` play-role again: {table.get(cid)}"
    # Positive control on the SAME expression: `stall` is still shipped vocabulary, so the absence
    # above is a ruling about this card rather than a tag that vanished from the table.
    keeps_stall = sorted(cid for cid, tags in table.items() if "stall" in tags)
    assert keeps_stall, "no card ships `stall` at all — the assertion above would pass vacuously"
    assert not set(keeps_stall) & set(ids), keeps_stall


# --- the closed tag vocabulary, and rebuild-reachability (REQ-FUNC-0017/0018, Issue #395) ------
# Both walk the SHIPPED stores through the builder's own loaders, with a vacuity guard and control.


@pytest.mark.req("REQ-FUNC-0018")
def test_every_tag_in_the_shipped_table_is_declared():
    """Walks the store rather than a hand-kept list: a hand-kept list is precisely what a new tag
    value would not be added to."""
    table = build_card_functions._load_table(build_card_functions.DEFAULT_OUT)
    vocab = card_tags.tag_vocabulary({str(k): v for k, v in table.items()})
    # Guard the instrument before trusting its silence.
    assert len(table) > 50, f"shipped table looks unread: {len(table)} cards"
    assert len(vocab) > 20, f"vocabulary walk looks empty: {vocab}"

    assert card_tags.undeclared_tags(vocab) == [], (
        "tags in the shipped table with no `card_tags.TAG_REGISTRY` entry: %s"
        % card_tags.undeclared_tags(vocab))
    # The parametric families are reached by the walk, so the registry's PREFIX entries are doing
    # work rather than sitting unexercised beside a table of plain names.
    assert {card_tags.is_parametric(t) for t in vocab} >= {"dig:", "provides:"}
    # Every declared tag says what it is; a reason-less entry is an undocumented one.
    assert [t for t, e in card_tags.TAG_REGISTRY.items() if not e.reason.strip()] == []
    assert [t for t, e in card_tags.TAG_REGISTRY.items() if e.source not in card_tags.SOURCES] == []


@pytest.mark.req("REQ-FUNC-0018")
def test_the_tag_vocabulary_audit_actually_bites_with_a_positive_control():
    """Both shapes a real divergence takes: a name nothing declared, and a PARAMETRIC tag whose
    suffix is not an integer (a family accepting any suffix would exempt `dig:many`)."""
    assert card_tags.undeclared_tags(["__never_a_real_tag__"]) == ["__never_a_real_tag__"]
    assert card_tags.undeclared_tags(["dig:many"]) == ["dig:many"]
    assert card_tags.undeclared_tags(["dig:2"]) == []
    # …and the same call on a fabricated table finds the bad one WITHOUT flagging its legitimate
    # neighbours, so the result above is discrimination rather than a walk that reached nothing.
    fabricated = {"999": ["draw", "__typo__"], "_note": "prose", "1000": ["provides:1"]}
    assert card_tags.undeclared_tags(card_tags.tag_vocabulary(fabricated)) == ["__typo__"]
    assert card_tags.tag_vocabulary(fabricated) == ["__typo__", "draw", "provides:1"]


@pytest.mark.req("REQ-FUNC-0018")
def test_the_registrys_derived_declarations_match_the_classifiers_own_set():
    """Two descriptions of one behaviour, asserted equal: changing a classify rule without touching
    the registry fails here rather than making `unsourced_tag_instances` quietly wrong."""
    declared = {t for t, e in card_tags.TAG_REGISTRY.items() if e.source == card_tags.DERIVED}
    assert declared == set(DERIVED_TAGS), {
        "declared derived but the classifier cannot emit": sorted(declared - set(DERIVED_TAGS)),
        "emitted by the classifier but not declared derived": sorted(set(DERIVED_TAGS) - declared),
    }
    # A parametric family is never `derived`: the probe emits the plain `dig`, never a depth, so a
    # `dig:N` declared derived would make an unreachable instance look sourced.
    assert not any(card_tags.is_parametric(t) for t in DERIVED_TAGS)


@pytest.mark.req("REQ-FUNC-0017")
def test_every_shipped_tag_instance_is_reachable_by_a_rebuild():
    """`--fresh` must be LOSSLESS: it sets ``prior = {}``, so anything the monotonic accumulate union
    was the only thing preserving dies silently. The direction here is table ⊆ derived ∪ overrides."""
    table = build_card_functions._load_table(build_card_functions.DEFAULT_OUT)
    overrides = build_card_functions._load_overrides(build_card_functions.DEFAULT_OVERRIDES)
    assert len(table) > 50, f"shipped table looks unread: {len(table)} cards"
    assert len(overrides) > 50, f"override store looks unread: {len(overrides)} numeric keys"
    assert len(DERIVED_TAGS) > 10, f"classifier's derived set looks empty: {DERIVED_TAGS}"

    unsourced = card_tags.unsourced_tag_instances(
        {str(k): v for k, v in table.items()},
        {str(k): v for k, v in overrides.items()},
        DERIVED_TAGS)
    assert unsourced == {}, (
        "tag instances no rebuild can re-derive — `--fresh` DELETES these silently; key them in "
        "tools/meta_tracker/function_overrides.json (the only store upstream of the accumulate "
        "step) or remove them: %s" % unsourced)


@pytest.mark.req("REQ-FUNC-0017")
def test_the_rebuild_reachability_audit_actually_bites_with_a_positive_control():
    """Both escapes must go red: a tag no classify rule emits, and a card whose override entry does
    not cover the tag it carries."""
    derived = {"draw"}
    fabricated = {"_note": "prose", "345": ["draw", "prevent_ex_damage"], "66": ["draw"]}
    assert card_tags.unsourced_tag_instances(fabricated, {"345": []}, derived) == \
        {345: ["prevent_ex_damage"]}
    # Covered by the override -> reachable, so the bite above is about sourcing rather than about the
    # walk reaching the card at all.
    assert card_tags.unsourced_tag_instances(
        fabricated, {"345": ["prevent_ex_damage"]}, derived) == {}
    # Reserved keys are skipped rather than `int()`-ed — the capacity D6.5 lifted.
    assert card_tags.unsourced_tag_instances({"_note": "prose"}, {}, derived) == {}


@pytest.mark.req("REQ-FUNC-0017")
def test_crustles_ex_damage_prevention_survives_a_fresh_rebuild(name_tags):
    """The general audits above would catch this loss as one entry in a dict; this names the card
    fact three live consumers depend on, where somebody would otherwise delete it."""
    nm2ids, table = name_tags
    ids = nm2ids.get("Crustle", [])
    assert ids, "Crustle not in the pool (rotated out? refresh the oracle)"
    assert any("prevent_ex_damage" in table.get(cid, []) for cid in ids), \
        f"Crustle lost `prevent_ex_damage` (ids={ids})"
    # …and it is REACHABLE, not merely present: the override store is what survives `--fresh`.
    overrides = build_card_functions._load_overrides(build_card_functions.DEFAULT_OVERRIDES)
    assert any("prevent_ex_damage" in overrides.get(cid, []) for cid in ids), \
        "Crustle's tag is in the table but in no store a rebuild reads — `--fresh` would drop it"


@pytest.mark.req("REQ-FUNC-0017")
def test_the_dead_hand_size_attacker_tag_is_gone_rather_than_adopted(name_tags):
    """`hand_size_attacker` was ruled a genuine LEFTOVER: reconciling the store must not launder a
    dead tag into the curated file. The control keeps the absence a ruling, not a rotation."""
    nm2ids, table = name_tags
    ids = nm2ids.get("Alakazam", [])
    assert ids, "Alakazam not in the pool (rotated out? re-rule this deletion)"
    assert all("hand_size_attacker" not in table.get(cid, []) for cid in ids), table
    assert "hand_size_attacker" not in card_tags.TAG_REGISTRY
    overrides = build_card_functions._load_overrides(build_card_functions.DEFAULT_OVERRIDES)
    assert all("hand_size_attacker" not in tags for tags in overrides.values())
    # …and nothing else in the store carries it either, so the ruling is about the tag, not one card.
    assert [cid for cid, tags in table.items() if "hand_size_attacker" in tags] == []


@pytest.mark.req("REQ-FUNC-0018")
def test_every_declared_consumer_really_reads_its_tag_and_inert_tags_really_are_inert():
    """Both directions, and the second is load-bearing: a tag declared INERT must be read by
    nothing, or an "authored ahead of its consumer" label goes stale the moment somebody wires it."""
    src = Path(__file__).resolve().parents[2] / "src"
    # The registry itself names every tag by construction, so it is not evidence about consumers.
    registry = src / "common" / "card_tags.py"
    sources = {p: p.read_text(encoding="utf-8") for p in src.rglob("*.py") if p != registry}
    assert len(sources) > 30, f"source tree looks unread: {len(sources)} modules"
    assert registry.exists()          # …and the exclusion names a real file, not a stale path

    def _module(dotted: str) -> Path:
        return src.joinpath(*dotted.split(".")).with_suffix(".py")

    missing, leaked = {}, {}
    for tag, entry in card_tags.TAG_REGISTRY.items():
        literals = (f'"{tag}"', f"'{tag}'")
        for dotted in entry.consumers:
            path = _module(dotted)
            assert path in sources, f"{tag}: declared consumer {dotted} is not a module"
            if not any(lit in sources[path] for lit in literals):
                missing.setdefault(tag, []).append(dotted)
        if not entry.consumers:
            hits = sorted(p.relative_to(src).as_posix() for p, text in sources.items()
                          if any(lit in text for lit in literals))
            if hits:
                leaked[tag] = hits
    assert missing == {}, f"declared consumers that never name their tag: {missing}"
    assert leaked == {}, (
        "tags declared INERT that something now reads — wire the consumer into TAG_REGISTRY "
        "rather than leaving the registry claiming nothing reads it: %s" % leaked)


@pytest.mark.req("REQ-FUNC-0017")
def test_the_shipped_store_is_byte_identical_to_what_the_builder_writes():
    """The store is a COMMITTED artifact, so its FORMAT is part of it. Asserts BYTES, which also
    covers line endings: the store is `text=auto`, so the CI guard cannot see them (ADR-0116)."""
    shipped = build_card_functions.DEFAULT_OUT.read_bytes()
    table = build_card_functions._load_table(build_card_functions.DEFAULT_OUT)
    assert len(table) > 50, f"shipped table looks unread: {len(table)} cards"
    assert shipped == build_card_functions.shipped_bytes(table), (
        "the committed card_functions.json is not in the builder's own output format — a rebuild "
        "would reformat the whole file and hide the real change inside it")
    assert b"\r\n" not in shipped


@pytest.mark.req("REQ-FUNC-0018")
def test_every_declared_tag_has_a_row_in_the_documented_reference():
    """`docs/card-functions.md` claims to hold *"the full behavioral vocabulary"*; the registry is
    the machine-readable half, and this is what keeps them ONE vocabulary."""
    doc = (Path(__file__).resolve().parents[2] / "docs" / "card-functions.md").read_text(
        encoding="utf-8")
    rows = set(re.findall(r"^\| `([a-z_]+)` \|", doc, flags=re.M))
    assert len(rows) > 20, f"the reference table looks unread: {len(rows)} rows"
    assert sorted(t for t in card_tags.TAG_REGISTRY if t not in rows) == [], (
        "tags declared in card_tags.TAG_REGISTRY with no row in docs/card-functions.md")
    # …and the other direction, so a row for a tag the registry does not declare is caught too — a
    # documented tag nothing declares is a tag the vocabulary lint would reject on sight.
    assert sorted(r for r in rows if r not in card_tags.TAG_REGISTRY) == []
