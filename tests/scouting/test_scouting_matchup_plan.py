"""MatchupPlan — the unified opponent target-priority spine (ADR-0051).

Pure/offline (mirrors test_scouting_briefs). The spine assigns every opponent body one
(role, priority); the Pilot's snipe/gust consumers read `priority(body_id)`. Tiers and
γ-scaling are exercised here without the engine.

Issue #395 added the CLOSED role vocabulary and its lint. Those tests walk the REAL shipped
`artifact.json` and `briefs/*.json` — `test_scouting_briefs.py`'s real-directory tests are the prior
art — and each carries a vacuity guard plus a positive control on the same run, because *"found
nothing"* and *"my instrument is broken"* return the same empty list.
"""
import json
from pathlib import Path

from common.scouting.artifact import load_artifact
from common.scouting.briefs import load_briefs
from common.scouting.matchup_plan import (_GENERAL, _MATCHUP, ROLE_REGISTRY, BodyFacts,
                                          build_matchup_plan, derive_general_roles, role_priority,
                                          roles_in_brief, roles_in_dossiers, undeclared_roles)

_SCOUTING = Path(__file__).resolve().parents[2] / "src" / "common" / "scouting"
_BRIEFS = _SCOUTING / "briefs"
_SCHEMA = _SCOUTING / "brief.schema.json"

# The three cards the Issue #395 `avoid` defect turns on, with the facts it turns on. Verified at
# source (data/EN_Card_Data.csv) rather than recalled: all three carry the `draw` Function Tag and
# they differ ONLY in prize value, which is exactly what the gate reads.
DUDUNSPARCE = 66            # 140 HP, Stage 1, 1 prize  — Run Away Draw. `avoid` is CORRECT here.
FEZANDIPITI = 140           # 210 HP, Pokémon ex, 2 prizes — the Dragapult chip-then-gust line.
MEGA_KANGASKHAN = 756       # 300 HP, Mega Pokémon ex, 3 prizes — a wall AND a draw engine.


def _facts(cid, prize, *tags):
    return {cid: BodyFacts(tags=frozenset(tags), prize_value=prize)}


def test_brief_wincon_and_preevo_outrank_a_plain_body():
    # A matched Brief names the wincon body (prize_liability) and its pre-evo (fragile_preevo);
    # an unnamed body carries no matchup priority. Doctrine: the ready wincon is the top target.
    plan = build_matchup_plan(brief_roles={1031: "prize_liability", 1030: "fragile_preevo"}, gamma=1.0)
    assert plan.priority(1031) > 0                    # wincon body is a target
    assert plan.priority(1030) > 0                    # its pre-evo is a target
    assert plan.priority(999) == 0.0                  # a body the Brief doesn't name
    assert plan.priority(1031) >= plan.priority(1030)  # ready wincon >= its developing pre-evo


def test_avoid_role_is_a_negative_priority():
    # `avoid` (a matchup-specific decoy) must never read as a target — it de-prioritizes.
    plan = build_matchup_plan(brief_roles={66: "avoid", 1031: "prize_liability"}, gamma=1.0)
    assert plan.priority(66) < 0
    assert plan.priority(66) < plan.priority(1031)


def test_general_draw_engine_is_avoided_without_a_read():
    # A 1-prize draw ENGINE (Dudunsparce / Budew class) is a poor target in every deck, so the
    # general card-fact tier de-prioritizes it even when the opponent is unrecognized (γ=0).
    general = derive_general_roles(_facts(DUDUNSPARCE, 1, "draw"))
    plan = build_matchup_plan(general_roles=general, gamma=0.0)
    assert plan.priority(DUDUNSPARCE) < 0


def test_general_avoid_beats_read_intel_attacker():
    # The Read's observed layer labels any body with a printed attack "attacker"; the general
    # card fact must still win so the agent never chips a 1-prize engine over a real target.
    general = derive_general_roles(_facts(DUDUNSPARCE, 1, "draw"))
    plan = build_matchup_plan(read_roles={DUDUNSPARCE: "attacker"}, general_roles=general, gamma=1.0)
    assert plan.priority(DUDUNSPARCE) < 0


def test_curated_brief_overrides_the_general_engine_fact():
    # The Brief is the most specific tier: if it deliberately calls the engine a disruption
    # target for THIS matchup, that intent wins over the general avoid.
    general = derive_general_roles(_facts(DUDUNSPARCE, 1, "draw"))
    plan = build_matchup_plan(brief_roles={DUDUNSPARCE: "disruption_target"},
                              general_roles=general, gamma=1.0)
    assert plan.priority(DUDUNSPARCE) > 0


def test_matchup_claims_are_silent_at_zero_gamma():
    # ANTI-REGRESSION INVARIANT (ADR-0051): an unrecognized opponent (γ=0) gets NO matchup
    # override — neutral matchups are provably untouched. Only the general card fact remains.
    plan = build_matchup_plan(brief_roles={1031: "prize_liability"}, read_roles={5: "attacker"},
                              general_roles=derive_general_roles(_facts(DUDUNSPARCE, 1, "draw")),
                              gamma=0.0)
    assert plan.priority(1031) == 0.0        # Brief claim silent
    assert plan.priority(5) == 0.0           # Read-Intel claim silent
    assert plan.priority(DUDUNSPARCE) < 0    # general card fact still applies


def test_matchup_priority_scales_with_confidence():
    # Confidence grows as cards are revealed → the override strengthens proportionally.
    weak = build_matchup_plan(brief_roles={1031: "prize_liability"}, gamma=0.3)
    strong = build_matchup_plan(brief_roles={1031: "prize_liability"}, gamma=1.0)
    assert 0 < weak.priority(1031) < strong.priority(1031)


# --- the CLOSED role vocabulary (Issue #395 D2/D3) --------------------------------------------


def test_every_role_string_in_the_shipped_artifacts_is_declared():
    """**The lint that would have caught `attacker`.** The shipped `artifact.json` assigns it to 530
    opponent bodies across 122 archetypes — the largest role population in the artifact — and it was
    not in the consumed table, so `_ROLE_PRIORITY.get(role or "", 0)` resolved every one to 0 with no
    error, no log and no test.

    Walks BOTH stores (dossiers and every Brief) rather than a hand-kept list: *a hand-kept list is
    precisely what a new role string would not be added to.*"""
    artifact = load_artifact()
    dossier_roles = roles_in_dossiers(artifact.dossiers)
    brief_roles = sorted({r for b in load_briefs()
                          for r in roles_in_brief({"targets": [
                              {"role": t.get("role")} for t in (b.targets or [])]})})

    # Guard the instrument before trusting its silence: an empty read of either store would make
    # the assertions below vacuously green.
    assert len(artifact.dossiers) > 50, f"artifact looks unread: {len(artifact.dossiers)} archetypes"
    assert len(dossier_roles) >= 4, dossier_roles
    assert len(brief_roles) >= 3, brief_roles

    assert undeclared_roles(dossier_roles) == [], (
        "role strings in artifact.json with no ROLE_REGISTRY entry: %s"
        % undeclared_roles(dossier_roles))
    assert undeclared_roles(brief_roles) == [], (
        "role strings in briefs/*.json with no ROLE_REGISTRY entry: %s"
        % undeclared_roles(brief_roles))

    # The walk really reached `attacker` — the string the whole lint exists for. If the artifact is
    # ever rebuilt without it, this says so instead of quietly passing.
    assert "attacker" in dossier_roles, dossier_roles
    # Both stores reach the MATCHUP tier, so nothing in them may be a general-only role.
    for role in set(dossier_roles) | set(brief_roles):
        assert _MATCHUP in ROLE_REGISTRY[role].tiers, (role, ROLE_REGISTRY[role].tiers)


def test_the_role_vocabulary_audit_actually_bites_with_a_positive_control():
    """The positive control, on the same run as the green pass above.

    Bites through each walk as well as directly, because the walk is the half that was missing — a
    table that would have bitten is worth nothing until the walk arrives (the lesson Issue #350
    recorded one store over)."""
    assert undeclared_roles(["a_role_nobody_declared"]) == ["a_role_nobody_declared"]
    fabricated = {"Some Deck": {"targets": [{"cardId": 1, "role": "__typo__"},
                                            {"cardId": 2, "role": "engine"}],
                                "card_inclusion": {"1": 0.5}}}
    assert roles_in_dossiers(fabricated) == ["__typo__", "engine"]      # …and skips non-role blocks
    assert undeclared_roles(roles_in_dossiers(fabricated)) == ["__typo__"]
    assert undeclared_roles(roles_in_brief({"targets": [{"role": "__typo__"},
                                                        {"role": "avoid"}]})) == ["__typo__"]
    # …and the real stores stay green on this same run, so the bite above is discrimination rather
    # than an instrument that reddens on everything.
    assert undeclared_roles(roles_in_dossiers(load_artifact().dossiers)) == []


def test_the_brief_schemas_role_enum_equals_the_registrys_matchup_tier():
    """`brief.schema.json` declares a role enum and **nothing in `src/` or `tests/` loaded it**;
    `.claude/skills/matchup-genie/scripts/validate_brief.py` genuinely enforces it and had zero
    automated callers. So a hand-edited Brief with a typo'd role shipped green, and the schema could
    drift from the consumed table indefinitely. This is the join."""
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    enum = set(schema["properties"]["targets"]["items"]["properties"]["role"]["enum"])
    assert enum, "the schema's role enum is empty — the assertion below would pass vacuously"
    assert enum == {r for r, e in ROLE_REGISTRY.items() if _MATCHUP in e.tiers}


def test_the_registry_is_a_well_formed_ordinal_ladder():
    """The ORDER is the load-bearing part (D1's ordinal finding), so it is asserted directly rather
    than left implied by the numbers."""
    p = {name: r.priority for name, r in ROLE_REGISTRY.items()}
    assert p["prize_liability"] > p["fragile_preevo"] > p["disruption_target"] \
        > p["attacker"] > p["enabler"] > p["engine"] == 0 > p["avoid"]
    # Every role says why it sits there, and names at least one tier allowed to assign it.
    assert [r for r, e in ROLE_REGISTRY.items() if not e.reason.strip()] == []
    assert [r for r, e in ROLE_REGISTRY.items()
            if not e.tiers or set(e.tiers) - {_GENERAL, _MATCHUP}] == []


def test_the_530_shipped_attacker_assignments_are_no_longer_inert():
    """**D3, stated as the behaviour rather than as a table entry.** `attacker` resolving to a real
    priority is the single most valuable change here: it makes a role that already exists in the
    shipped data actually do something.

    Its rank is asserted relative to its neighbours rather than as a magnitude — a body that attacks
    is a real steer but not automatically a better removal target than the wincon or its fragile
    pre-evolution, and it must outrank a plain engine."""
    assert role_priority("attacker") > 0
    assert role_priority("prize_liability") > role_priority("attacker") > role_priority("engine")
    plan = build_matchup_plan(read_roles={345: "attacker"}, gamma=1.0)
    assert plan.priority(345) > 0
    # An unroled body still falls through to 0 — that fallback is for a body with NO role, and it is
    # no longer also the silent fallback for a role the table forgot.
    assert plan.priority(999) == 0.0


# --- the `avoid` prize gate (Issue #395 D4) ---------------------------------------------------
#
# EVERY pre-existing test of this rule passed card id 66 — the ONE card where it is correct — and the
# derivation itself had no direct test at all. That is why the defect survived, so these use
# multi-prize bodies by name.


def test_avoid_still_fires_on_a_one_prize_draw_engine():
    """The half that was always right: a 1-prize utility body is a poor place to spend removal, and
    dragging a Dudunsparce to the Active with a gust is a wasted turn."""
    assert derive_general_roles(_facts(DUDUNSPARCE, 1, "draw")) == {DUDUNSPARCE: "avoid"}


def test_avoid_no_longer_fires_on_fezandipiti_ex_two_prizes():
    """210 HP, Pokémon ex, `draw` tag. The developer's line — put ONE damage counter on it to take it
    to 200, then gust it next turn for the KO and the match — was being steered against by a rule
    written for the Dudunsparce class. It is now a TARGET, at the top of the ladder, because two
    prizes is what a body worth removing looks like."""
    assert derive_general_roles(_facts(FEZANDIPITI, 2, "draw")) == {FEZANDIPITI: "prize_liability"}
    assert role_priority("prize_liability") > 0


def test_avoid_no_longer_fires_on_mega_kangaskhan_ex_three_prizes():
    """300 HP, Mega Pokémon ex, `draw`/`stall`/`dig:2`. A wall AND a draw engine — and THREE prizes,
    which is precisely why it is a prime removal target rather than one to leave alone. Carrying
    THREE utility tags does not save it: the gate is the prize count."""
    roles = derive_general_roles(_facts(MEGA_KANGASKHAN, 3, "draw", "stall", "dig:2"))
    assert roles == {MEGA_KANGASKHAN: "prize_liability"}


def test_the_general_tier_no_longer_overwrites_the_dossiers_prize_liability():
    """The composed consequence, which is the one that actually cost decisions.

    `_GENERAL` provenance fires UNSCALED by γ and `build_matchup_plan` writes it AFTER Read-Intel, so
    the ungated rule overwrote the `prize_liability` the dossier had correctly assigned to a 3-prize
    body — at full strength, against an opponent we had not even recognised."""
    general = derive_general_roles(_facts(MEGA_KANGASKHAN, 3, "draw", "stall"))
    plan = build_matchup_plan(read_roles={MEGA_KANGASKHAN: "prize_liability"},
                              general_roles=general, gamma=1.0)
    assert plan.role(MEGA_KANGASKHAN) == "prize_liability"
    assert plan.priority(MEGA_KANGASKHAN) > 0
    # Positive control on the same run: the general tier still WINS where it fires, so the survival
    # of the dossier role above is the gate declining to fire — not the tier order silently changing.
    still = derive_general_roles(_facts(DUDUNSPARCE, 1, "draw"))
    overwritten = build_matchup_plan(read_roles={DUDUNSPARCE: "prize_liability"},
                                     general_roles=still, gamma=1.0)
    assert overwritten.role(DUDUNSPARCE) == "avoid"


def test_the_avoid_inconsistency_between_two_prize_engines_is_gone():
    """Meowth ex (170 HP, 2 prizes) carries `search`/`supporter_tutor` and no `draw`, so it ESCAPED
    the −80 that caught Fezandipiti ex — the old rule was not even consistent among ex engines. Both
    now land on the same side, and for the same stated reason.

    That the derived role is `prize_liability` on a 2-prize SUPPORT ex is an over-claim the deriver
    cannot avoid (matchup-genie's playbook: *"card facts cannot make this call for you"*), and
    correcting it is the curated Brief's job — the derive-first / Brief-corrects split."""
    meowth = derive_general_roles(_facts(1071, 2, "search", "supporter_tutor"))[1071]
    assert meowth == derive_general_roles(_facts(FEZANDIPITI, 2, "draw"))[FEZANDIPITI]
    assert meowth != "avoid"
    assert derive_general_roles({}) == {}


# --- the widened derived tier (Issue #395 D5) --------------------------------------------------
#
# The general tier stops being one hard-coded rule. Every input already ships, which was D5's
# FINDING rather than its proposal: prize value, the two damage ceilings `_threat_damage_pair`
# already computes, and three parsed `CardStat` fields.


def _body(prize=1, tags=(), own=0.0, fwd=0.0, boost=0, retreat=False, fuel=False):
    return BodyFacts(tags=frozenset(tags), prize_value=prize, own_damage=own, forward_damage=fwd,
                     damage_boost=boost, grants_free_retreat=retreat, ability_fuel=fuel)


def test_the_derived_tier_names_every_role_it_declares_a_general_tier_for():
    """The registry says which roles the `_GENERAL` tier may assign; this is the other half of that
    claim — each one is actually reachable from card facts alone. A role declared general that no
    derivation can produce is the mirror of the defect this issue is about."""
    one_of_each = {
        1: _body(prize=1, tags=("draw",)),                       # avoid
        2: _body(prize=2),                                       # prize_liability
        3: _body(prize=1, fwd=120),                              # fragile_preevo
        4: _body(prize=1, own=120),                              # attacker
        5: _body(prize=1, boost=30),                             # enabler
        6: _body(prize=1, tags=("energy_accel",)),               # engine
    }
    derived = set(derive_general_roles(one_of_each).values())
    assert derived == {r for r, e in ROLE_REGISTRY.items() if _GENERAL in e.tiers}
    # Every body in the fixture got a role, so the equality above is a match rather than a set that
    # happened to line up after some inputs fell through unread.
    assert len(derive_general_roles(one_of_each)) == len(one_of_each)


def test_the_worked_example_re_maps_the_way_the_developer_ruled_it():
    """**Crustle / Mega Kangaskhan ex**, the archetype that ships in `artifact.json` with no Brief
    covering it — so it runs on dossier roles alone, which called BOTH Crustle and Mega Kangaskhan
    `attacker` and scored both at 0, while the general `draw` rule then forced the 3-prize Mega to
    `avoid`.

    Card facts verified at source (`data/EN_Card_Data.csv`): Crustle 150 HP, Stage 1, 1 prize,
    Superb Scissors 120, Mysterious Rock Inn prevents all damage from opponent Pokémon ex; Dwebble
    70 HP, 1 prize, its pre-evolution; Mega Kangaskhan ex 300 HP, 3 prizes, Run Errand draws 2 and
    Rapid-Fire Combo hits 200.

    The developer's ruling — *"Crustle IS their main attacker specifically because it resists ex
    Pokémon's attacks, which near every other deck uses as its main. Mega Kangaskhan is a wall and
    draw engine, NOT the main attacker"* — is about which body is the ATTACKER, and that is what the
    derivation now says. The removal ORDER still puts the 3-prize body first, because prize math
    stays in the equation."""
    crustle, dwebble, mega = 345, 344, 756
    roles = derive_general_roles({
        crustle: _body(prize=1, tags=("prevent_ex_damage",), own=120),
        dwebble: _body(prize=1, fwd=120),
        mega: _body(prize=3, tags=("draw", "stall", "dig:2"), own=200),
    })
    assert roles == {crustle: "attacker", dwebble: "fragile_preevo", mega: "prize_liability"}
    # All three were 0 or NEGATIVE before: two inert `attacker`s and a `−80` on the 3-prize body.
    assert all(role_priority(r) > 0 for r in roles.values())
    assert role_priority(roles[mega]) > role_priority(roles[dwebble]) \
        > role_priority(roles[crustle])


def test_a_utility_bodys_incidental_attack_does_not_make_it_an_attacker():
    """Order matters and this is the pair that proves it. Dudunsparce hits for 90 with Land Crush,
    so an `attacker`-first derivation would stop de-prioritizing it and undo D4's surviving half.
    `avoid` is checked FIRST — the same call `_UTILITY_TAGS` already makes for the mirror-image
    question (*is Energy on this body wasted?*)."""
    assert derive_general_roles({66: _body(prize=1, tags=("draw", "stall"), own=90)}) \
        == {66: "avoid"}
    # Positive control on the same run: strip the utility tags and the SAME body is an attacker, so
    # the result above is the ordering rule firing rather than the damage fact going unread.
    assert derive_general_roles({66: _body(prize=1, own=90)}) == {66: "attacker"}


def test_an_energy_accel_body_is_never_avoided_because_it_accelerates_by_attacking():
    """The one place this derivation is deliberately NARROWER than the issue's D5 table, which wrote
    `avoid = engine ∧ prize_value == 1` over `_ENGINE_TAGS`. Taken literally that puts −80 on a
    1-prize `energy_accel` body — on Cinderace, a deck's MAIN attacker — and tells the agent never
    to spend removal there. `strategy/context.py` had already ruled exactly this distinction for the
    mirror-image question, so the gate reads `_UTILITY_TAGS`, which excludes `energy_accel`.

    The neutral `engine` role keeps the wider `_ENGINE_TAGS` membership; only the −80 is narrowed."""
    assert derive_general_roles({1: _body(prize=1, tags=("energy_accel",))}) == {1: "engine"}
    assert derive_general_roles({1: _body(prize=1, tags=("energy_accel",), own=120)}) \
        == {1: "attacker"}
    # …and a body carrying BOTH still avoids, because a utility tag is a positive claim about what
    # the body is for — this is a narrowing of the trigger, not a hole in it.
    assert derive_general_roles({1: _body(prize=1, tags=("energy_accel", "draw"))}) == {1: "avoid"}


def test_enabler_is_derived_from_card_facts_that_already_ship():
    """D5's finding: `enabler` needs NO new Function Tag. Each of the three fields alone is enough,
    and each is already parsed by `card_text.py` onto `CardStat`."""
    assert derive_general_roles({1: _body(boost=30)}) == {1: "enabler"}
    assert derive_general_roles({2: _body(retreat=True)}) == {2: "enabler"}
    assert derive_general_roles({3: _body(fuel=True)}) == {3: "enabler"}
    # …and it ranks below `attacker`, because removing the attacker is the more direct answer.
    assert role_priority("attacker") > role_priority("enabler") > role_priority("engine")
    # A body with no fact at all gets no role — the deriver stays silent rather than guessing.
    assert derive_general_roles({4: _body()}) == {}


def test_a_pre_evolution_of_a_non_attacker_is_not_flagged_fragile():
    """`fragile_preevo` means *deny the payoff before it comes online*, so it needs a payoff that
    ATTACKS. A line that evolves into something harmless is not a threat to pre-empt."""
    assert derive_general_roles({1: _body(prize=1, fwd=0.0)}) == {}
    assert derive_general_roles({1: _body(prize=1, fwd=10.0)}) == {1: "fragile_preevo"}
