"""Follow-up-select probe for multi-step lethal authoring (ADR-0050 Phase 2C).

Given a seeded correction fixture and a first step, drive the engine cascade through the pilot's own
policy and dump every follow-up select it reaches — the select's ``context`` and each option's
RESOLVED ``card_id`` / ``inPlayArea`` / ``inPlayIndex`` — so a Phase-3 follow-up-steering hook (e.g.
"at a Trainer-tutor, pick a retreat Tool"; "play the Tool onto the Active") is authored against real
engine encodings instead of guesses. Seeds the exact own deck/prize split (``_seed_zones``), so the
probe sees the same reachable options the live verify does.

    python tools/sim/lethal_probe.py <fixture.json> [--agent mega_lucario] [--step 0]

See docs/adr/0050-multi-step-lethal-verification-tool.md.
"""
from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.strategy.planner import _prune_none  # noqa: E402


def _option_record(pilot, od, sel, opt) -> dict:
    """One option's encoding, resolved: menu index + type + the card it points at + in-play target."""
    return {
        "index": opt.get("index"),
        "type": opt.get("type"),
        "card_id": pilot._option_card_id(od, sel, opt),
        "inPlayArea": opt.get("inPlayArea"),
        "inPlayIndex": opt.get("inPlayIndex"),
        "attackId": opt.get("attackId"),
        "playerIndex": opt.get("playerIndex"),
    }


def probe_follow_ups(pilot, obs, first_step, *, max_selects: int = 24) -> list[dict]:
    """Drive ``first_step`` through the pilot's seeded engine search and return one record per follow-up
    select the policy reaches: ``{step, context, type, maxCount, options: [...], chosen}``. ``chosen``
    is what ``decide()`` picked (used to walk the cascade); ``options`` is the FULL resolved menu (the
    authoring surface). Stops at a verdict, when control passes to the opponent, or at ``max_selects``.
    Returns ``[]`` when the engine is unavailable or the obs carries no seed (never raises)."""
    if not (obs or {}).get("search_begin_input"):
        return []
    try:
        from cg import api as cgapi
    except Exception:
        return []
    cur = obs.get("current") or {}
    yi = cur.get("yourIndex", 0)
    players = cur.get("players") or []
    me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
    opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
    yd, yp, od_, op_, oh = pilot._seed_zones(obs, me, opp)

    out: list[dict] = []
    was_planning = pilot._planning
    pilot._planning = True
    try:
        st = cgapi.search_begin(cgapi.to_observation_class(obs), yd, yp, od_, op_, oh, [],
                                manual_coin=True)
        for step in ([first_step] if first_step and not isinstance(first_step[0], list) else first_step):
            st = cgapi.search_step(st.searchId, list(step))
        for n in range(max_selects):
            o = st.observation
            c = o.current
            if c is None or c.result != -1 or o.select is None:
                break                                          # verdict / no more selects
            if c.yourIndex != yi:
                break                                          # passed to the opponent
            od = _prune_none(asdict(o))
            sel = od.get("select") or {}
            opts = sel.get("option") or []
            chosen = list(pilot.decide(od))
            out.append({
                "step": n,
                "context": sel.get("context"),
                "type": sel.get("type"),
                "maxCount": sel.get("maxCount"),
                "options": [_option_record(pilot, od, sel, opt) for opt in opts],
                "chosen": chosen,
            })
            st = cgapi.search_step(st.searchId, chosen)
        cgapi.search_end()
    except Exception:
        try:
            cgapi.search_end()
        except Exception:
            pass
    finally:
        pilot._planning = was_planning
    return out


def _build_pilot(agent: str):
    from cg.api import all_attack
    from common.cards import CardFunctions
    from common.effects import CardEffects
    from common.pilot import Pilot
    from common.scouting.provider import (
        EngineCardStatProvider, build_attack_stats, load_attack_overrides,
        parse_attack_bench_snipe, parse_attack_recoil)
    from common.strategy import Strategy
    from common.strategy.general_strategy import GENERAL_STRATEGY
    deck = [int(x) for x in (REPO / "src" / "agents" / agent / "deck.csv")
            .read_text(encoding="utf-8").split("\n")[:60]]
    atk = all_attack()
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    return Pilot(Strategy(), deck, general_strategy=GENERAL_STRATEGY, stats=EngineCardStatProvider(),
                 functions=fns, effects=CardEffects.load(),
                 attacks={a.attackId: a.damage for a in atk},
                 attack_costs={a.attackId: len(a.energies) for a in atk},
                 recoil={a.attackId: parse_attack_recoil(a.text) for a in atk},
                 bench_snipe={a.attackId: parse_attack_bench_snipe(a.text) for a in atk},
                 attack_stats=build_attack_stats(atk, load_attack_overrides()),
                 lethal_verify=True, lethal_family=True, lethal_veto=True)


def main(argv=None):
    import argparse
    import json

    from cg.api import all_card_data

    ap = argparse.ArgumentParser(description="Probe a seeded fixture's follow-up selects (ADR-0050)")
    ap.add_argument("fixture", help="tests/fixtures/corrections/<name>.json (must carry a seed)")
    ap.add_argument("--agent", default="mega_lucario")
    ap.add_argument("--step", type=int, nargs="+", default=[0], help="first-step option index/indices")
    args = ap.parse_args(argv)

    names = {c.cardId: c.name for c in all_card_data()}
    obs = json.loads(Path(args.fixture).read_text(encoding="utf-8"))["obs"]
    pilot = _build_pilot(args.agent)
    for rec in probe_follow_ups(pilot, obs, list(args.step)):
        print(f"[{rec['step']}] ctx={rec['context']} type={rec['type']} max={rec['maxCount']} "
              f"chosen={rec['chosen']}")
        for o in rec["options"]:
            tgt = f" @area{o['inPlayArea']}i{o['inPlayIndex']}" if o["inPlayArea"] is not None else ""
            atk = f" atk{o['attackId']}" if o["attackId"] is not None else ""
            print(f"    {o['index']:>3} t{o['type']} {names.get(o['card_id'], o['card_id'])}{tgt}{atk}")


if __name__ == "__main__":
    main()
