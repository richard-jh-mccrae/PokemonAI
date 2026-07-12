"""MatchupPlan — the unified opponent target-priority spine (ADR-0051).

Pure/offline (mirrors test_scouting_briefs). The spine assigns every opponent body one
(role, priority); the Pilot's snipe/gust consumers read `priority(body_id)`. Tiers and
γ-scaling are exercised here without the engine.
"""
from common.scouting.matchup_plan import build_matchup_plan


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
    # A draw ENGINE (Dudunsparce / Budew class) is a poor target in every deck, so the general
    # card-fact tier de-prioritizes it even when the opponent is unrecognized (γ=0) — no Brief.
    plan = build_matchup_plan(draw_engine_ids={66}, gamma=0.0)
    assert plan.priority(66) < 0


def test_general_avoid_beats_read_intel_attacker():
    # The Read's observed layer labels any body with a printed attack "attacker"; the general
    # draw-engine fact must still win so the agent never chips the engine over a real target.
    plan = build_matchup_plan(read_roles={66: "attacker"}, draw_engine_ids={66}, gamma=1.0)
    assert plan.priority(66) < 0


def test_curated_brief_overrides_the_general_engine_fact():
    # The Brief is the most specific tier: if it deliberately calls the engine a disruption
    # target for THIS matchup, that intent wins over the general avoid.
    plan = build_matchup_plan(brief_roles={66: "disruption_target"}, draw_engine_ids={66}, gamma=1.0)
    assert plan.priority(66) > 0


def test_matchup_claims_are_silent_at_zero_gamma():
    # ANTI-REGRESSION INVARIANT (ADR-0051): an unrecognized opponent (γ=0) gets NO matchup
    # override — neutral matchups are provably untouched. Only the general card fact remains.
    plan = build_matchup_plan(brief_roles={1031: "prize_liability"},
                              read_roles={5: "attacker"}, draw_engine_ids={66}, gamma=0.0)
    assert plan.priority(1031) == 0.0        # Brief claim silent
    assert plan.priority(5) == 0.0           # Read-Intel claim silent
    assert plan.priority(66) < 0             # general card fact still applies


def test_matchup_priority_scales_with_confidence():
    # Confidence grows as cards are revealed → the override strengthens proportionally.
    weak = build_matchup_plan(brief_roles={1031: "prize_liability"}, gamma=0.3)
    strong = build_matchup_plan(brief_roles={1031: "prize_liability"}, gamma=1.0)
    assert 0 < weak.priority(1031) < strong.priority(1031)
