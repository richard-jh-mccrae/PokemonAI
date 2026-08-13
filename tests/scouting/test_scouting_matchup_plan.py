"""MatchupPlan — the unified opponent target-priority spine (ADR-0051). Pure/offline.

The spine assigns every opponent body one (role, priority); the Pilot's snipe/gust consumers read
`priority(body_id)`. The Issue #395 role-vocabulary lint walks the REAL shipped `artifact.json` and
`briefs/*.json`, each with a vacuity guard and a positive control on the same run — "found nothing"
and "my instrument is broken" return the same empty list.
"""
import json
from pathlib import Path

from common.scouting.artifact import load_artifact
from common.scouting.briefs import load_briefs
from common.scouting.matchup_plan import (ASSIGNERS, BRIEF_BY, DERIVED_BY, READ_BY,
                                          ROLE_REGISTRY, BodyFacts, build_matchup_plan,
                                          derive_general_roles, role_priority,
                                          roles_in_brief, roles_in_dossiers, undeclared_roles)

_SCOUTING = Path(__file__).resolve().parents[2] / "src" / "common" / "scouting"
_BRIEFS = _SCOUTING / "briefs"
_SCHEMA = _SCOUTING / "brief.schema.json"

# All three carry the `draw` Function Tag and differ ONLY in prize value, which is what the gate
# reads. Verified at source in data/EN_Card_Data.csv.
DUDUNSPARCE = 66            # 140 HP, Stage 1, 1 prize  — Run Away Draw. `avoid` is CORRECT here.
FEZANDIPITI = 140           # 210 HP, Pokémon ex, 2 prizes — the Dragapult chip-then-gust line.
MEGA_KANGASKHAN = 756       # 300 HP, Mega Pokémon ex, 3 prizes — a wall AND a draw engine.


def _facts(cid, prize, *tags):
    return {cid: BodyFacts(tags=frozenset(tags), prize_value=prize)}


def test_brief_primary_and_derived_preevo_outrank_a_plain_body():
    # Doctrine: the Brief names the ready primary; card facts name its developing pre-evo.
    plan = build_matchup_plan(brief_roles={1031: "prize_liability"},
                              general_roles={1030: "fragile_preevo"}, gamma=1.0)
    assert plan.priority(1031) > 0                    # primary body is a target
    assert plan.priority(1030) > 0                    # its pre-evo is a target
    assert plan.priority(999) == 0.0                  # a body the Brief doesn't name
    assert plan.priority(1031) >= plan.priority(1030)  # ready primary >= its developing pre-evo


def test_avoid_role_is_a_negative_priority():
    plan = build_matchup_plan(brief_roles={66: "avoid", 1031: "prize_liability"}, gamma=1.0)
    assert plan.priority(66) < 0
    assert plan.priority(66) < plan.priority(1031)


def test_general_draw_engine_is_avoided_without_a_read():
    # The general card-fact tier fires even when the opponent is unrecognized (γ=0).
    general = derive_general_roles(_facts(DUDUNSPARCE, 1, "draw"))
    plan = build_matchup_plan(general_roles=general, gamma=0.0)
    assert plan.priority(DUDUNSPARCE) < 0


def test_general_avoid_beats_read_intel_attacker():
    # The Read labels any body with a printed attack "attacker"; the general card fact must win.
    general = derive_general_roles(_facts(DUDUNSPARCE, 1, "draw"))
    plan = build_matchup_plan(read_roles={DUDUNSPARCE: "attacker"}, general_roles=general, gamma=1.0)
    assert plan.priority(DUDUNSPARCE) < 0


def test_curated_brief_overrides_the_general_engine_fact():
    # The Brief is the most specific tier, so its per-matchup intent wins.
    general = derive_general_roles(_facts(DUDUNSPARCE, 1, "draw"))
    plan = build_matchup_plan(brief_roles={DUDUNSPARCE: "disruption_target"},
                              general_roles=general, gamma=1.0)
    assert plan.priority(DUDUNSPARCE) > 0


def test_matchup_claims_are_silent_at_zero_gamma():
    # ADR-0051 invariant: an unrecognized opponent gets NO matchup override, only card facts.
    plan = build_matchup_plan(brief_roles={1031: "prize_liability"}, read_roles={5: "attacker"},
                              general_roles=derive_general_roles(_facts(DUDUNSPARCE, 1, "draw")),
                              gamma=0.0)
    assert plan.priority(1031) == 0.0        # Brief claim silent
    assert plan.priority(5) == 0.0           # Read-Intel claim silent
    assert plan.priority(DUDUNSPARCE) < 0    # general card fact still applies


def test_matchup_priority_scales_with_confidence():
    weak = build_matchup_plan(brief_roles={1031: "prize_liability"}, gamma=0.3)
    strong = build_matchup_plan(brief_roles={1031: "prize_liability"}, gamma=1.0)
    assert 0 < weak.priority(1031) < strong.priority(1031)


# --- the CLOSED role vocabulary (Issue #395 D2/D3) --------------------------------------------


def test_every_role_string_in_the_shipped_artifacts_is_declared():
    """Walks BOTH stores rather than a hand-kept list — a hand-kept list is precisely what a new
    role string would not be added to, and `_ROLE_PRIORITY.get(role, 0)` swallows an unknown one."""
    artifact = load_artifact()
    dossier_roles = roles_in_dossiers(artifact.dossiers)
    brief_roles = sorted({r for b in load_briefs()
                          for r in roles_in_brief({"pokemon": b.pokemon})})

    # Guard the instrument: an empty read of either store makes the assertions below vacuous.
    assert len(artifact.dossiers) > 50, f"artifact looks unread: {len(artifact.dossiers)} archetypes"
    assert len(dossier_roles) >= 4, dossier_roles
    assert len(brief_roles) >= 3, brief_roles

    assert undeclared_roles(dossier_roles) == [], (
        "role strings in artifact.json with no ROLE_REGISTRY entry: %s"
        % undeclared_roles(dossier_roles))
    assert undeclared_roles(brief_roles) == [], (
        "role strings in briefs/*.json with no ROLE_REGISTRY entry: %s"
        % undeclared_roles(brief_roles))

    # The walk really reached `attacker` — the string the whole lint exists for.
    assert "attacker" in dossier_roles, dossier_roles
    # Per store, not pooled: a role only the Read emits must not become legal in a hand-written Brief.
    for role in dossier_roles:
        assert READ_BY in ROLE_REGISTRY[role].assigners, (role, ROLE_REGISTRY[role].assigners)
    for role in brief_roles:
        assert BRIEF_BY in ROLE_REGISTRY[role].assigners, (role, ROLE_REGISTRY[role].assigners)


def test_the_role_vocabulary_audit_actually_bites_with_a_positive_control():
    """Bites through each WALK as well as directly: a table that would have bitten is worth nothing
    until the walk that feeds it arrives."""
    assert undeclared_roles(["a_role_nobody_declared"]) == ["a_role_nobody_declared"]
    fabricated = {"Some Deck": {"targets": [{"cardId": 1, "role": "__typo__"},
                                            {"cardId": 2, "role": "engine"}],
                                "card_inclusion": {"1": 0.5}}}
    assert roles_in_dossiers(fabricated) == ["__typo__", "engine"]      # …and skips non-role blocks
    assert undeclared_roles(roles_in_dossiers(fabricated)) == ["__typo__"]
    assert roles_in_brief({"pokemon": [{"roles": ["primary_attacker", "support"]}]}) == ["engine", "prize_liability"]
    # the real stores stay green on this same run, so the bite is discrimination, not a red-on-all
    assert undeclared_roles(roles_in_dossiers(load_artifact().dossiers)) == []


def test_the_brief_schema_has_the_compact_doctrine_roles():
    """The doctrine vocabulary is schema-validated and includes Pilot-consumed roles."""
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    enum = set(schema["properties"]["pokemon"]["items"]["properties"]["roles"]["items"]["enum"])
    assert enum, "the schema's role enum is empty — the assertion below would pass vacuously"
    assert {"primary_attacker", "backup_attacker", "support", "energy_accel"} <= enum
    # `support` is doctrine, not a MatchupPlan role: the resolver maps it to neutral `engine`.
    assert "support" in enum and "unknown" not in enum


def test_the_registry_is_a_well_formed_ordinal_ladder():
    """The ORDER is the load-bearing part (D1's ordinal finding), so it is asserted directly rather
    than left implied by the numbers."""
    p = {name: r.priority for name, r in ROLE_REGISTRY.items()}
    assert p["prize_liability"] > p["fragile_preevo"] > p["disruption_target"] \
        > p["attacker"] > p["enabler"] > p["engine"] == 0 > p["avoid"]
    # Every role says why it sits there, and names at least one tier allowed to assign it.
    assert [r for r, e in ROLE_REGISTRY.items() if not e.reason.strip()] == []
    assert [r for r, e in ROLE_REGISTRY.items()
            if not e.assigners or set(e.assigners) - set(ASSIGNERS)] == []


def test_the_530_shipped_attacker_assignments_are_no_longer_inert():
    """Rank asserted relative to its neighbours, not as a magnitude: attacking is a real steer but
    not automatically a better removal target than the primary attacker or its fragile pre-evolution."""
    assert role_priority("attacker") > 0
    assert role_priority("prize_liability") > role_priority("attacker") > role_priority("engine")
    plan = build_matchup_plan(read_roles={345: "attacker"}, gamma=1.0)
    assert plan.priority(345) > 0
    # 0 is the fallback for a body with NO role — no longer also the fallback for a forgotten one.
    assert plan.priority(999) == 0.0


# --- the `avoid` prize gate (Issue #395 D4) ---------------------------------------------------
# Named multi-prize bodies: every earlier test passed card 66, the one where the rule is correct.


def test_avoid_still_fires_on_a_one_prize_draw_engine():
    """A 1-prize utility body is a poor place to spend removal."""
    assert derive_general_roles(_facts(DUDUNSPARCE, 1, "draw")) == {DUDUNSPARCE: "avoid"}


def test_avoid_no_longer_fires_on_fezandipiti_ex_two_prizes():
    """210 HP, Pokémon ex, `draw` tag — but two prizes, so the chip-then-gust line is a TARGET."""
    assert derive_general_roles(_facts(FEZANDIPITI, 2, "draw")) == {FEZANDIPITI: "prize_liability"}
    assert role_priority("prize_liability") > 0


def test_avoid_no_longer_fires_on_mega_kangaskhan_ex_three_prizes():
    """Three utility tags do not save a 3-prize body: the gate is the prize count."""
    roles = derive_general_roles(_facts(MEGA_KANGASKHAN, 3, "draw", "stall", "dig:2"))
    assert roles == {MEGA_KANGASKHAN: "prize_liability"}


def test_the_general_tier_no_longer_overwrites_the_dossiers_prize_liability():
    """`_GENERAL` fires UNSCALED by γ and is written AFTER Read-Intel, so an over-broad general rule
    overwrites a correct dossier role at full strength against an unrecognised opponent."""
    general = derive_general_roles(_facts(MEGA_KANGASKHAN, 3, "draw", "stall"))
    plan = build_matchup_plan(read_roles={MEGA_KANGASKHAN: "prize_liability"},
                              general_roles=general, gamma=1.0)
    assert plan.role(MEGA_KANGASKHAN) == "prize_liability"
    assert plan.priority(MEGA_KANGASKHAN) > 0
    # Positive control: the general tier still WINS where it fires, so the survival above is the
    # gate declining rather than the tier order silently changing.
    still = derive_general_roles(_facts(DUDUNSPARCE, 1, "draw"))
    overwritten = build_matchup_plan(read_roles={DUDUNSPARCE: "prize_liability"},
                                     general_roles=still, gamma=1.0)
    assert overwritten.role(DUDUNSPARCE) == "avoid"


def test_the_avoid_inconsistency_between_two_prize_engines_is_gone():
    """`prize_liability` on a 2-prize SUPPORT ex is an over-claim card facts cannot avoid; correcting
    it is the curated Brief's job (derive-first, Brief-corrects)."""
    meowth = derive_general_roles(_facts(1071, 2, "search", "supporter_tutor"))[1071]
    assert meowth == derive_general_roles(_facts(FEZANDIPITI, 2, "draw"))[FEZANDIPITI]
    assert meowth != "avoid"
    assert derive_general_roles({}) == {}


# --- the widened derived tier (Issue #395 D5) --------------------------------------------------
# Every input already ships: prize value, `_threat_damage_pair`'s ceilings, `CardStat` fields.


def _body(prize=1, tags=(), own=0.0, fwd=0.0, boost=0, retreat=False, fuel=False):
    return BodyFacts(tags=frozenset(tags), prize_value=prize, own_damage=own, forward_damage=fwd,
                     damage_boost=boost, grants_free_retreat=retreat, ability_fuel=fuel)


def test_the_derived_tier_names_every_role_it_declares_a_general_tier_for():
    """The registry's other half: a role declared general that no derivation can reach is the mirror
    of a role assigned in the data that the table forgot."""
    one_of_each = {
        1: _body(prize=1, tags=("draw",)),                       # avoid
        2: _body(prize=2),                                       # prize_liability
        3: _body(prize=1, fwd=120),                              # fragile_preevo
        4: _body(prize=1, own=120),                              # attacker
        5: _body(prize=1, boost=30),                             # enabler
        6: _body(prize=1, tags=("energy_accel",)),               # engine
    }
    derived = set(derive_general_roles(one_of_each).values())
    assert derived == {r for r, e in ROLE_REGISTRY.items() if DERIVED_BY in e.assigners}
    # every body got a role, so the equality above is not a set that lined up after silent drops
    assert len(derive_general_roles(one_of_each)) == len(one_of_each)


def test_the_worked_example_re_maps_the_way_the_developer_ruled_it():
    """Human ruling: Crustle is the ATTACKER (it resists ex), the Mega is a wall and draw engine —
    but removal ORDER still puts the 3-prize body first. Card facts verified in EN_Card_Data.csv."""
    crustle, dwebble, mega = 345, 344, 756
    roles = derive_general_roles({
        crustle: _body(prize=1, tags=("prevent_ex_damage",), own=120),
        dwebble: _body(prize=1, fwd=120),
        mega: _body(prize=3, tags=("draw", "stall", "dig:2"), own=200),
    })
    assert roles == {crustle: "attacker", dwebble: "fragile_preevo", mega: "prize_liability"}
    assert all(role_priority(r) > 0 for r in roles.values())
    assert role_priority(roles[mega]) > role_priority(roles[dwebble]) \
        > role_priority(roles[crustle])


def test_a_utility_bodys_incidental_attack_does_not_make_it_an_attacker():
    """`avoid` is checked FIRST: Dudunsparce hits for 90, so an `attacker`-first derivation would
    stop de-prioritizing it."""
    assert derive_general_roles({66: _body(prize=1, tags=("draw", "stall"), own=90)}) \
        == {66: "avoid"}
    # Positive control: strip the utility tags and the SAME body is an attacker, so the result
    # above is the ordering rule firing rather than the damage fact going unread.
    assert derive_general_roles({66: _body(prize=1, own=90)}) == {66: "attacker"}


def test_an_energy_accel_body_is_never_avoided_because_it_accelerates_by_attacking():
    """Deliberately NARROWER than `avoid = engine ∧ prize_value == 1`: that would put −80 on a
    1-prize `energy_accel` body like Cinderace, a deck's MAIN attacker. Only the −80 is narrowed."""
    assert derive_general_roles({1: _body(prize=1, tags=("energy_accel",))}) == {1: "engine"}
    assert derive_general_roles({1: _body(prize=1, tags=("energy_accel",), own=120)}) \
        == {1: "attacker"}
    # a body carrying BOTH still avoids — a narrowing of the trigger, not a hole in it
    assert derive_general_roles({1: _body(prize=1, tags=("energy_accel", "draw"))}) == {1: "avoid"}


def test_enabler_is_derived_from_card_facts_that_already_ship():
    """Each of the three fields alone is enough, and `card_text.py` already parses all three."""
    assert derive_general_roles({1: _body(boost=30)}) == {1: "enabler"}
    assert derive_general_roles({2: _body(retreat=True)}) == {2: "enabler"}
    assert derive_general_roles({3: _body(fuel=True)}) == {3: "enabler"}
    assert role_priority("attacker") > role_priority("enabler") > role_priority("engine")
    assert derive_general_roles({4: _body()}) == {}     # no fact -> silence, not a guess


def test_a_pre_evolution_of_a_non_attacker_is_not_flagged_fragile():
    """`fragile_preevo` denies a payoff, so it needs a payoff that ATTACKS."""
    assert derive_general_roles({1: _body(prize=1, fwd=0.0)}) == {}
    assert derive_general_roles({1: _body(prize=1, fwd=10.0)}) == {1: "fragile_preevo"}
