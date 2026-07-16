"""The executable Tier Map — the single source of truth for the T0–T6 architecture and which
runtime kill-switch (``PROFILE`` flag in ``common.runtime``) governs each tier / sub-tier.

This is the machine-readable twin of ``docs/naming-convention.md`` + ``docs/architecture/tiers.md``.
Its first consumer is the **Agent Brief** (``tools/submit/brief.py``), which renders, per built
agent, exactly which tiers and sub-tiers are enabled vs disabled. Pure stdlib (a built agent is
stdlib-only; this module is import-safe from the runtime and from build tools alike).

**Invariant (pinned by ``tests/common/test_tiers.py``):** every ``PROFILE`` kill-switch appears in
exactly ONE tier node. Adding a flag to ``PROFILE`` without placing it here fails the test — so the
Brief can never silently omit a capability.

Node shape:
    id       — "T3" (tier) or "T3.1" (sub-tier), the naming-convention label
    name     — human name; a reference expands as "T3.1 - Match Objectives, Prize Path"
    flags    — the PROFILE switches that govern this node (may be empty)
    structural — True = always on, no kill-switch (e.g. T0 fallback, T1.4)
    status   — design status for nodes with no live switch: "grilled, unbuilt" / "unbuilt (research)"
    sub      — child sub-tier nodes
    note     — governing-ADR / caveat shown in the Brief
"""
from __future__ import annotations

# Ordered T0–T6. Flag → tier assignments are grounded in each flag's ADR (see the comment in
# common.runtime.PROFILE) and docs/architecture/tiers.md.
TIERS: list[dict] = [
    {
        "id": "T0", "name": "Rules & Tuned Scoring", "status": "built",
        "structural": True,   # the universal fallback + non-MAIN scorer; no kill-switch
        "flags": [],
        "note": "Hypotheses + Tactical + compendium, corrections-tuned. Always on — the backbone "
                "every other tier degrades to.",
        "sub": [],
    },
    {
        "id": "T1", "name": "Turn Planner", "status": "built",
        "flags": ["planner_engine_rank", "promote_ko_aware", "disruptor_lock_maneuver"],
        "note": "The Goal Ladder: rank reachable end-of-turn boards, commit the best.",
        "sub": [
            {"id": "T1.1", "name": "Win Rung (Lethal Solver)",
             "flags": ["lethal_family", "lethal_verify", "lethal_veto", "lethal_seed_exact",
                       "boost_lethal", "retreat_enabler_lethal", "play_accel_lethal"],
             "note": "The sound, locking win rung — engine-verified lethal (ADR-0030/0037/0050)."},
            {"id": "T1.2", "name": "KO the Key Threat", "flags": ["planner_key_threat"],
             "note": "ADR-0031 Goal-Ladder rung."},
            {"id": "T1.3", "name": "KO for Prizes", "flags": ["enabler_item_composer"],
             "note": "Item-tutor / Rare-Candy → evolve → energy → KO composer (min-bound)."},
            {"id": "T1.4", "name": "Stabilize-then-KO", "structural": True, "flags": [],
             "note": "Structural Goal-Ladder rung — no dedicated kill-switch."},
            {"id": "T1.5", "name": "Develop", "flags": ["develop_rollout"],
             "note": "Within-turn develop-rollout rung (armed-ON, ladder-testing)."},
        ],
    },
    {
        "id": "T2", "name": "Chance & EV (Gamble Lines)", "status": "built",
        "flags": ["gamble_lines"],
        "note": "ADR-0039 closed-form expectimax; joins T1's ladder as a candidate rung below T1.1.",
        "sub": [],
    },
    {
        "id": "T3", "name": "Match Objectives", "status": "built",
        "flags": ["match_planner_steer", "forgo_ko"],
        "note": "Per-turn match-scale intent (ADR-0040) + the Match Planner's Game Plan (ADR-0045).",
        "sub": [
            {"id": "T3.1", "name": "Prize Path (+ Denial)",
             "flags": ["objectives_path", "prize_economy_fetch", "snipe_prize_redundant"],
             "note": "Two-sided cheapest KO route + 'force 7' denial and its offensive twin "
                     "(don't chip a body I need not KO) (ADR-0040/0044/0048)."},
            {"id": "T3.2", "name": "KO Race", "flags": ["objectives_race"],
             "note": "Closed-form turns-to-KO both directions (ADR-0040)."},
            {"id": "T3.3", "name": "Derived Phases", "flags": ["objectives_phases"],
             "note": "Advisory STABILIZE/CLOSE bands (ADR-0040)."},
        ],
    },
    {
        "id": "T4", "name": "Opponent Model", "status": "built",
        "flags": ["posture", "forced_promotion",
                  "evolving_wincon_priority", "ko_target_whiff", "opp_resource_reads"],
        "note": "The γ-gated Read + predicted-overlay reads (ADR-0026/0044/0047); fails open on an "
                "unrecognized opponent.",
        "sub": [
            {"id": "T4.1", "name": "Read", "structural": True, "flags": [],
             "note": "Deck-agnostic opponent recognition; enabled with the T4 'posture' switch."},
            {"id": "T4.2", "name": "Posture", "structural": True, "flags": [],
             "note": "Favorability + accurate-dev levers; enabled with the T4 'posture' switch."},
            {"id": "T4.3", "name": "Matchup Briefs", "flags": ["matchup_targeting"],
             "note": "ADR-0051 MatchupPlan target-priority spine (hand-authored counterplay)."},
            {"id": "T4.4", "name": "Learned Matchup Weights", "status": "grilled, unbuilt",
             "flags": [],
             "note": "The learned counterpart to Briefs (ML Build Session 3b-2); no runtime switch "
                     "yet — flips at the Adoption Gate."},
        ],
    },
    {
        "id": "T5", "name": "Automatic Value Model", "status": "built, gated:off",
        "flags": ["value_model"],
        "note": "Learned leaf-refinement (ADR-0042). Ships dark; flips at the Adoption Gate. "
                "Being rebuilt by the value net (ML Build Session 2a).",
        "sub": [],
    },
    {
        "id": "T6", "name": "Escalation Search", "status": "built, gated:off",
        "flags": [],
        "note": "Narrow bounded look-ahead for the hardest ties (ADR-0043).",
        "sub": [
            {"id": "T6.1", "name": "Two-ply search", "flags": ["escalation", "search_budget"],
             "note": "The built escalation policy; needs escalation=on AND search_budget>0."},
            {"id": "T6.2", "name": "Sampled-Belief Search", "status": "unbuilt (research)",
             "flags": [],
             "note": "The value-net-backed decision-time search upgrade path (SoG shape)."},
        ],
    },
]

# Flags whose live state is an integer budget, not a boolean (on = value > 0).
_BUDGET_FLAGS = {"search_budget"}


def _iter_nodes(tiers=None):
    """Yield (node, parent_or_None) for every tier and sub-tier, depth-first."""
    for tier in (TIERS if tiers is None else tiers):
        yield tier, None
        for sub in tier.get("sub", []):
            yield sub, tier


def flag_owner() -> dict[str, str]:
    """`{flag: node_id}` — the one node that governs each PROFILE flag. Used by the drift test."""
    owner: dict[str, str] = {}
    for node, _ in _iter_nodes():
        for flag in node.get("flags", []):
            if flag in owner:
                raise ValueError(f"flag {flag!r} claimed by both {owner[flag]} and {node['id']}")
            owner[flag] = node["id"]
    return owner


def _flag_on(flag: str, effective: dict) -> bool:
    """Is a single governing flag live? Budget flags are on when > 0; the rest are truthy."""
    val = effective.get(flag)
    return (val or 0) > 0 if flag in _BUDGET_FLAGS else bool(val)


def _node_state(node: dict, effective: dict) -> dict:
    """Resolve one node's live enabled/disabled state against the effective flag values.

    Returns `{id, name, note, flags:[{name,on}], state, detail}` where `state` is one of
    `on` | `off` | `partial` | `unbuilt` (design status, no live switch)."""
    flags = node.get("flags", [])
    flag_states = [{"name": f, "on": _flag_on(f, effective)} for f in flags]
    if node.get("status", "").endswith("unbuilt") or "unbuilt" in node.get("status", ""):
        state, detail = "unbuilt", node.get("status", "unbuilt")
    elif node.get("structural"):
        state, detail = "on", "structural (always on)"
    elif not flags:
        state, detail = "on", "structural (always on)"
    else:
        on = sum(1 for fs in flag_states if fs["on"])
        if on == len(flags):
            state, detail = "on", ""
        elif on == 0:
            state, detail = "off", ""
        else:
            state, detail = "partial", f"{on}/{len(flags)} switches on"
    return {"id": node["id"], "name": node["name"], "note": node.get("note", ""),
            "status": node.get("status", ""), "flags": flag_states, "state": state, "detail": detail}


def resolve(effective: dict) -> list[dict]:
    """The Tier Map resolved against a deck's effective flags (``params.get(flag, PROFILE[flag])``).

    Returns one entry per tier: `{id, name, status, note, state, detail, flags, sub:[...]}` — a
    render-ready tree the Brief turns into nested drop-downs. `effective` is the fully-merged flag
    dict (Strategy params over PROFILE defaults), exactly as ``runtime.build_pilot`` computes it.
    """
    out = []
    for tier in TIERS:
        node = _node_state(tier, effective)
        node["sub"] = [_node_state(s, effective) for s in tier.get("sub", [])]
        out.append(node)
    return out


def effective_flags(params: dict, profile: dict) -> dict:
    """`{flag: value}` = the deck's `params` over the `PROFILE` defaults, for every governed flag.

    Mirrors ``runtime.build_pilot``'s ``{k: merged.get(k, v) for k, v in PROFILE.items()}`` but
    stays declarative (no Pilot build) so the Brief computes it without running the agent."""
    return {flag: params.get(flag, profile.get(flag)) for flag in flag_owner()}
