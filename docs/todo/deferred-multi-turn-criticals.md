# TODO — the two multi-turn CRITICAL corrections (`a21472`, `b4649`)

**Status:** open (2026-07-01), split out of the Turn Planner build
([ADR-0031](../adr/0031-turn-planner-is-goal-directed-engine-simulated-tier1-search.md)) as **out of
this-turn scope**. The Planner fixed the three *this-turn* CRITICALs that named it (`7f48`, `0cbc`, `4298`
— gated in [test_planner_engine.py](../../tests/strategy/test_planner_engine.py)). These two were deferred because
they need capability the Planner deliberately lacks: reasoning across **more than one of my turns** and
about the **opponent's prize trajectory**.

**Re-measured through the shipped Pilot (2026-07-01) — the two are NOT in the same place:**

| id | today, on its captured state | what it needs |
|----|------------------------------|---------------|
| `a21472f6f4d2` | **still a live blunder** — Pilot plays `[2]` Nebula, human-correct is `[1]` Jetting | multi-turn attack-*sequence* optimisation |
| `b4649ba9c304` | **already covered** — Pilot plays `[2]` (the human-correct move); blunder no longer reproduces | a general Prize-Race Planner (aspirational; **no live failing example**) |

So the actionable gap is **`a21472`**. `b4649` is kept here as a *characterised, covered* case + a pointer
to the general capability — not a regression to fix. (This is the [old-build real-Pilot re-measure] lesson:
the real-Pilot measure beats the captured-blunder assumption; always replay before treating a stale
correction as open.)

> ⚠️ **Verify every card/attack/rule fact at source before acting** (per `CLAUDE.md`): Pokémon **TCG**
> Scarlet & Violet with competition simulator deltas — read `docs/rules.md` / `docs/rulebook.txt` /
> `data/EN_Card_Data.csv` / the engine, never memory. This already bit us: the `a21472` human note says
> "100 dmg to the benched Riolu"; `Jetting Blow` actually snipes **50** (×2 over the line = 100).

## Why deferred (shared)

The shipped Planner is **this-turn scope** with a **1-ply** threat read (closed-form *Incoming* / Survival
Window). It has no forward search across my own successive turns and no model of the opponent's choices or
prize race. Both corrections are optimal only once you plan **≥2 of my turns** (and, for `b4649`, reason
about *whose* KO advances *whose* win). That is the designed-but-unbuilt **M3 deep search + M4 value model**
(and the **Prize-Race Planner**):

- [ADR-0031](../adr/0031-turn-planner-is-goal-directed-engine-simulated-tier1-search.md) — this-turn Turn
  Planner; its **multi-turn** note carves these two out.
- [ADR-0030](../adr/0030-winning-this-turn-is-an-eager-engine-verified-lethal-solver.md) — carves `b4649`
  into a future **Prize-Race Planner** (fuzzy, opponent-modelled, non-committal — the *wrong* home for a
  hard lock).
- [roadmap-search-posture-learning.md](roadmap-search-posture-learning.md) — **M3 Tier-1 Search** (budgeted
  escalation) + **M4 Value Model** (replay-trained leaf-eval), the capabilities these need.

**Do not** bolt multi-turn onto the closed-form Planner; it belongs behind the engine-search escalation +
the value-model leaf-eval, exactly where the roadmap puts it.

> **Correction ([ADR-0040](../adr/0040-match-judgment-is-per-turn-closed-form-objectives.md),
> 2026-07-05): the prescription above is PARTIALLY REVERSED.** Opponent-*static* multi-turn
> arithmetic — the **KO Race** (turns-to-KO attack sequences, riders credited to Prize-Path
> targets) — is closed-form at the same epistemic tier as Incoming/Survival Window and is the
> designed home for `a21472` ([Tier 3](../architecture/tier-3-match-objectives.md)), NOT the engine
> tree. The engine-search escalation keeps only the opponent-*choice*-dominated residue
> ([Tier 6](../architecture/tier-6-escalation-search.md)). `b4649`'s "Prize-Race Planner" is
> realized as the two-sided **Prize Path** objective (Tier 3): fuzzy, γ-gated, non-committal — as
> ADR-0030 required.

---

## `a21472f6f4d2` — the live gap: pick the multi-turn attack *sequence*, not the biggest single hit

- **Record:** `data/corrections/mega_starmie_20260701_fa8f649/corrections.jsonl` (id `a21472f6f4d2`, episode `83116501`, seat 0)
- **Fixture:** [tests/fixtures/corrections/planner_a21472.json](../../tests/fixtures/corrections/planner_a21472.json) *(extracted; no test yet)*
- **Category:** `other` (multi-turn). **Today:** `chosen=[2]` (Nebula), `correct=[1]` (Jetting), `planned=None` — **fails**.

**The decision (turn 6, prizes 5–5).** My Active is a **Mega Starmie ex** (330 HP, **6 Energy**); bench is two
Staryu. Opponent Active is a **440-HP wall** (Mega Lucario ex, id 678, 1 Energy) with a benched **Riolu**
(676, its pre-evolution) among others.

- Agent chose `[2]` **Nebula Beam** — score `209.7` (raw damage 210, the biggest single hit).
- Human-correct `[1]` **Jetting Blow** — score `119.9` (120 to the Active **+ 50 to one Benched Pokémon**).

**Why Jetting Blow is right (the multi-turn read).** The 440-HP wall can't be one-shot (Nebula 210 < 440),
so the KO takes **three of my turns regardless of order** — the human's line is **2× Jetting (120+120) + 1×
Nebula (210) = 450 ≥ 440**. Jetting-first *also* starts the **bench snipe** now: 50 per Jetting ×2 = **100
cumulative onto the benched Riolu**, chipping the pre-evolution before it becomes a second Lucario. Today's
`tactical` score is just the attack's raw single-turn damage (`209.7` vs `119.9`), so the greedy pick is
Nebula; it is blind to "same KO in the same number of turns, but Jetting-first adds free, on-tempo bench
damage."

**Capability needed.** Forward search over **my** successive turns: when no this-turn KO exists, rank the
attack by the **multi-turn KO sequence + incidental effects** (here `Jetting Blow`'s 50 bench snipe), scored
by the value model — not by max single-turn damage.

**Verify at source when picking up:** `Jetting Blow` / `Nebula Beam` full effects + costs for Mega Starmie ex
(id 1031) in `data/EN_Card_Data.csv` (Jetting Blow confirmed: 120 + **50 to 1 Benched**, no W/R on the
bench); confirm 678 = Mega Lucario ex @ 440 HP and 676 = Riolu; confirm the sequence KOs via the engine.

---

## `b4649ba9c304` — covered on its state; kept as the Prize-Race exemplar

- **Record:** `data/corrections/mega_starmie_20260701_c1efef0/corrections.jsonl` (id `b4649ba9c304`, episode `83037962`, seat 1)
- **Fixture:** [tests/fixtures/corrections/planner_b4649.json](../../tests/fixtures/corrections/planner_b4649.json) *(extracted; no test yet)*
- **Category:** `misattachment` (mislabelled — it is a **prize-race / tempo** decision). **Today:** `chosen=[2]` == `correct=[2]`, `planned=None` — **already passes**.

**The decision (turn 11, prizes: me 5, opp 3 — I'm behind).** My Active is **Cinderace** (666, 210 HP, 0
Energy); bench is two **Mega Starmie ex** (180 HP, 330 HP), **both 0 Energy**. Opponent Active is a Mega
Starmie ex (190 HP, 3 Energy) with another benched (280 HP).

- Original blunder chose `[3]` attach {W} → **benched** Mega (180/330).
- Human-correct `[2]` attach {W} → **Cinderace** (Active). **The shipped Pilot now plays `[2]`** — tuned
  scoring ranks attach→Active `45` over attach→benched-Mega `35`, a "power the Active attacker" lean.

**Why `[2]` is right (the prize-math read).** Power the Active Cinderace and keep **delaying** with it,
using its Energy-acceleration to build the **330-HP** Mega Starmie into the next attacker. Prize-math (human's
words): *"if the opponent KOs Cinderace they take a prize but are no closer to winning — they still must KO a
Mega Starmie."* Cinderace is a **sacrificial delay-wall**: the prize it yields doesn't advance the opponent's
win path, while it buys the turns to set up the wincon.

**Status & why it stays here.** The captured blunder **no longer reproduces** — the current scoring already
prefers the Active-attacker attach, so there is **no live regression to gate**. But it lands on the right
move via a *general* lean, **not** explicit prize-race reasoning (there is no prize-trajectory model). Kept
as the concrete exemplar for the future **Prize-Race Planner** (per ADR-0030): model the opponent's prize
trajectory and *which* of my Pokémon should absorb the next KO. Inherently fuzzy + opponent-modelled — a
*ranking* input to the value model, **not** a committed lock. **Before building anything for it, mine a
FRESH failing example** — this state is already handled.

*Housekeeping:* because it is covered, consider moving `b4649` to the reviewed ledger
(`data/corrections/reviewed.json`, "covered") so `tune.py` stops resurfacing it as new work.

**Verify at source when picking up:** Cinderace (666) attack + Energy-acceleration Ability, Mega Starmie ex
retreat/attack costs, in `data/EN_Card_Data.csv`; confirm the prize counts + that Cinderace can attack/delay
from the captured state via the engine.

---

## How to pick this up (retest harness — same as the shipped gates)

Both fixtures replay through the shipped Pilot exactly like the fixed CRITICALs
([test_planner_engine.py](../../tests/strategy/test_planner_engine.py) `test_critical_4298_…`):

```python
import json
from pathlib import Path
from train.tune import _build_pilot   # tools/ on sys.path

fx = json.loads(Path("tests/fixtures/corrections/planner_a21472.json").read_text(encoding="utf-8"))
pilot, _ = _build_pilot("mega_starmie")
decision = pilot.explain(fx["obs"])
# a21472 TODAY: decision.chosen == [2] != fx["correct"] == [1]   (the live gap)
# b4649  TODAY: decision.chosen == [2] == fx["correct"]          (already covered — re-verify before building)
```

**Definition of done (`a21472`):** it becomes a real-state regression gate
(`decision.chosen == fx["correct"]`) in `test_planner_engine.py` with a `REQ-PLANNER-00xx` id, built behind
the M3/M4 multi-turn capability — **not** hacked into the closed-form this-turn Planner. Update the ADR-0031
status block + the turn-planner memory when it lands.

**`b4649`:** no gate to build today; if the Prize-Race Planner is pursued proactively, first mine a fresh
failing prize-race example, then gate that.

---

## 2026-07-04 round — three more SOFT multi-turn/forward reads (all deferred here)

Surfaced in the mega_starmie blunder-buster round (all re-measured through the shipped, fully-wired
Pilot — still live, all beyond this-turn scope; all **SOFT**, not CRITICAL). State is embedded in each
Correction's `obs` in `data/corrections/mega_starmie_*/corrections.jsonl` (retrievable by episode/frame),
so no separate fixture is minted until the layer is built.

| id | today, on its captured state | what it needs |
|----|------------------------------|---------------|
| `83661649-30` | live — Pilot develops then would pick max-damage Nebula (209.7) over Jetting (119.9) | multi-turn attack-*sequence* (Jetting Blow's 50 snipe builds a 2-turn KO; also anticipate the opp's Wally heal) — same shape as `a21472` |
| `83667237-107` | live — snipe-the-top-threat targets the 2nd Mega Lucario ex (top threat rank) | opponent **prize-trajectory** model (we want 4 prizes = one Mega Lucario + 1; deny the 2nd via a future Boss's) — same shape as `b4649` |
| `83661649-45` | live — snipe-the-top-threat targets the energized 70-HP Staryu (imminent attacker) | **forward-promotion** read (they'll promote the benched Mega Starmie ex next; pre-chip it) — 1-ply opponent-choice model the closed-form threat read lacks |

**Definition of done (all three):** each becomes a real-state regression gate
(`decision.chosen == correct`) once the M3/M4 multi-turn + opponent-modelling capability exists — the
closed-form this-turn Planner and 1-ply threat read deliberately lack it, so **not** hacked in. The
single-turn heuristics they "lose" to (max-damage attack, snipe-the-top-threat by threat rank) are the
correct closed-form picks; the human's lines span turns / model the opponent's choices.
