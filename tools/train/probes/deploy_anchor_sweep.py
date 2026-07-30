"""Deploy-seam anchor sweep — can the DEPLOY corpus derive the **Worth Damage Rate**?

The question ADR-0083 (Issue #197) decision 4 left open, and ADR-0080 (Issue #199) made urgent by
ruling the rate MOOT for deny rather than deriving it. The Deploy Marginal has two Worth-denominated
legs (slot displacement, ability yield) that must reach a damage-scale score, so it needs the bridge
deny no longer does.

An anchor requires a HUMAN-RULED comparison in which a Worth-denominated object and a
damage-denominated one are BOTH nonzero:

    deploy ruled OVER attack  =>  worth x rate > damage  =>  LOWER bound
    attack ruled OVER deploy  =>  worth x rate < damage  =>  UPPER bound

ADR-0080's deny sweep failed because its single candidate priced 0.0 on both sides, so the rate
divided out. This asks the same question of the deploy corpus, which is natively play-side and was
therefore the more promising seam (ADR-0078 decision 3 says as much).

**Result, 2026-07-29: NO USABLE ANCHOR, and the reason is structural.** See the report this prints,
and ADR-0083 Amendment A. Both sides do price nonzero here (Riolu `win_condition_base` 20.0 against
Lunatone's Power Gem 50), so this is not deny's failure mode — but every candidate ruling turns out to
be a **sequencing** claim rather than an exclusive choice: benching Basics is "as many as you want, in
any order" and only the attack ends the turn (`docs/rulebook.txt` L120-122), so "play Riolu, THEN
attack" is ONE legal turn. Such a ruling is an ADR-0072 **Endorsement Claim** and asserts only
`deploy_value > 0`, which every positive rate satisfies.

The general form, which no additional corpus capture can escape: **a deploy is never exclusive with a
damage-denominated option.** Benching consumes no attach, no Supporter slot, and does not end the
turn, so it cannot TRADE against an attack or an attach. The only genuine competitor for a Bench slot
is another deploy, and that comparison is worth-versus-worth, carrying no rate information. The same
commutativity that let ADR-0083 decision 6 rule out a set-level planner is what closes this seam as a
rate anchor.

    python tools/train/probes/deploy_anchor_sweep.py             # the report
    python tools/train/probes/deploy_anchor_sweep.py --census    # + the select-context census

Offline and read-only. No engine, no Pilot: it reads the corrections corpus, the card CSV, the
shipped Function Tags and each agent's declared Roles, and prices worth through the real
`card_worth.role_value`.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.card_worth import role_value  # noqa: E402

#: `cg.api` owns these numbers, but importing it MAPS THE NATIVE LIBRARY, and this probe must stay
#: DLL-free (the `tools/train/gates.py` precedent). Written literally, and cheap to re-check.
OPTION_TYPE = {1: "YES", 2: "NO", 3: "CARD", 6: "ENERGY", 7: "PLAY", 8: "ATTACH",
               9: "EVOLVE", 10: "ABILITY", 12: "RETREAT", 13: "ATTACK", 14: "END"}
_ZONE = {2: "hand", 3: "discard", 4: "active", 5: "bench"}

AGENTS = ("mega_lucario", "dragapult_ex", "mega_starmie")


def _card_table():
    """id -> {name, hp, attacks[(name, cost, damage)]} straight off the shipped CSV."""
    out: dict = {}
    with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cid = int(r["Card ID"])
            hp = r["HP"].strip()
            dmg = r["Damage"].strip().rstrip("+x").replace("×", "")
            e = out.setdefault(cid, {"name": r["Card Name"],
                                     "hp": int(hp) if hp.isdigit() else 0, "attacks": []})
            e["attacks"].append((r["Move Name"], r["Cost"], int(dmg) if dmg.isdigit() else 0))
    return out


def _agent_roles(agent: str) -> dict:
    """The deck's declared `Strategy.roles` (cardId -> [Role]); {} if the agent has no strategy yet."""
    p = REPO / "src" / "agents" / agent / "strategy.py"
    if not p.exists():
        return {}
    spec = importlib.util.spec_from_file_location(f"_{agent}_strategy", p)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:                                    # pragma: no cover - diagnostic
        print(f"!! could not load {agent} strategy: {exc}", file=sys.stderr)
        return {}
    strat = getattr(mod, "STRATEGY", None)
    return dict(getattr(strat, "roles", {}) or {}) if strat is not None else {}


CARDS = _card_table()
TAGS = json.loads((REPO / "src" / "common" / "card_functions.json").read_text(encoding="utf-8"))
ROLES_BY_AGENT = {a: _agent_roles(a) for a in AGENTS}


def _opt_type(o: dict) -> str:
    t = o.get("type")
    return t.upper() if isinstance(t, str) else OPTION_TYPE.get(t, str(t))


def _card_id_at(dec: dict, o: dict):
    """The card id an option refers to, where the obs zones resolve it. A PLAY carries a bare hand
    index and no `area` (`strategy/context.py`), which is why the area lookup falls back to hand."""
    cur = dec.get("current") or {}
    players = cur.get("players") or []
    yi = cur.get("yourIndex", 0)
    pi = o.get("playerIndex", yi)
    me = players[pi] if 0 <= pi < len(players) and players[pi] else {}
    idx = o.get("index")
    zone = _ZONE.get(o.get("area"), "hand" if _opt_type(o) == "PLAY" else None)
    if not zone or idx is None:
        return None
    z = me.get(zone) or []
    return (z[idx] or {}).get("id") if 0 <= idx < len(z) and z[idx] else None


def _is_pokemon(cid) -> bool:
    return bool(cid) and CARDS.get(cid, {}).get("hp", 0) > 0


def _worth(agent, cid):
    """Worth-scale value through the REAL oracle — declared Roles + shipped Function Tags."""
    roles = ROLES_BY_AGENT.get(agent, {}).get(cid, [])
    return role_value(roles, tags=TAGS.get(str(cid), [])), roles


def _best_attack(dec):
    """(max printed damage, attacker name) for my Active — the damage-scale side of the comparison."""
    cur = dec.get("current") or {}
    players = cur.get("players") or []
    me = players[cur.get("yourIndex", 0)] if players else {}
    act = next((c for c in (me.get("active") or []) if c), None)
    if not act:
        return 0, "?"
    c = CARDS.get(act.get("id"), {})
    return max((d for _, _, d in c.get("attacks", [])), default=0), c.get("name", "?")


def records():
    """Every ruled record in the tracked corpus: (agent, key, decision, chosen, correct, note)."""
    for jf in sorted((REPO / "data" / "corrections").glob("*/corrections.jsonl")):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            dec = d.get("decision") or {}
            yield (d.get("agent"), f'{d.get("episode_id")}-{dec.get("frame")}',
                   dec, d.get("chosen") or [], d.get("correct"), d.get("note") or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--census", action="store_true", help="also print the select-context census")
    args = ap.parse_args()

    ctx = Counter()
    deploy_frames, candidates = 0, []

    for agent, key, dec, chosen, correct, note in records():
        opts = dec.get("options") or []
        ctx[str(dec.get("select_context"))] += 1
        if not opts or correct is None:
            continue
        deploys = [(i, _card_id_at(dec, o)) for i, o in enumerate(opts)
                   if _opt_type(o) == "PLAY" and _is_pokemon(_card_id_at(dec, o))]
        if deploys:
            deploy_frames += 1
        attacks = [i for i, o in enumerate(opts) if _opt_type(o) == "ATTACK"]
        if not deploys or not attacks:
            continue

        corr_deploy = [(i, c) for i, c in deploys if i in correct]
        rej_deploy = [(i, c) for i, c in deploys if i not in correct]
        chose_attack = any(i in chosen for i in attacks)
        corr_attack = any(i in correct for i in attacks)

        if corr_deploy and chose_attack:
            direction, subject = "DEPLOY > ATTACK (lower bound)", corr_deploy
        elif corr_attack and rej_deploy:
            direction, subject = "ATTACK > DEPLOY (upper bound)", rej_deploy
        else:
            continue
        dmg, attacker = _best_attack(dec)
        for _i, cid in subject:
            w, roles = _worth(agent, cid)
            candidates.append((key, agent, direction, CARDS.get(cid, {}).get("name"), w, roles,
                               attacker, dmg, note))

    if args.census:
        print("SELECT-CONTEXT CENSUS")
        for c, n in ctx.most_common():
            print(f"  {c:22s} {n:4d}")
        print(f"  {'TOTAL':22s} {sum(ctx.values()):4d}\n")

    print("=" * 100)
    print(f"deploy-involved ruled frames : {deploy_frames}")
    print(f"cross-scale candidates       : {len(candidates)}")
    print("=" * 100)

    lower, upper = [], []
    for key, agent, direction, name, w, roles, attacker, dmg, note in candidates:
        print(f"\n{key}  [{agent}]  {direction}")
        print(f"  deploy : {name:22s} worth={w:5.1f}  roles={roles or '[]'}")
        print(f"  attack : {attacker:22s} max printed damage={dmg}")
        if not w:
            print("  => DEGENERATE: worth 0, the rate divides out (ADR-0080's failure mode)")
        elif direction.startswith("DEPLOY"):
            lower.append(dmg / w)
            print(f"  => rate > {dmg / w:.2f}")
        else:
            upper.append(dmg / w)
            print(f"  => rate < {dmg / w:.2f}")
        if note:
            print(f"  note   : {note[:160]}")

    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    if lower:
        print(f"  lower bounds : {['%.2f' % v for v in lower]}  (tightest: rate > {max(lower):.2f})")
    if upper:
        print(f"  upper bounds : {['%.2f' % v for v in upper]}  (tightest: rate < {min(upper):.2f})")
    if not upper:
        print("  upper bounds : NONE — no ruling anywhere puts an attack over a deploy.")
    print("""
  NOT A USABLE ANCHOR. Read the candidate notes: every one is a SEQUENCING ruling ("play Riolu,
  THEN attack"), not an exclusive choice. Benching Basics is unlimited and any-order and only the
  attack ends the turn (docs/rulebook.txt L120-122), so both actions fit in ONE turn. That makes
  each an ADR-0072 ENDORSEMENT claim, asserting only `deploy_value > 0` — which every positive rate
  satisfies, exactly as ADR-0080 found for the lone Hammer frame.

  STRUCTURAL, not a corpus gap: a deploy is never exclusive with a damage-denominated option. It
  consumes no attach, no Supporter slot, and does not end the turn, so it cannot trade against an
  attack or an attach. The only real competitor for a Bench slot is another deploy — worth versus
  worth, carrying no rate information. Capturing more frames cannot change this.

  Consequence: ADR-0083 decision 4 is re-opened. See ADR-0083 Amendment A.""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
