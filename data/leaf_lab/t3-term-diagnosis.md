# `state_value` term diagnosis — the 22 frames (Issue #262)

**Generated, never hand-maintained** — regenerate with `tools/train/family_diag.py`
(see its docstring). Every number is the per-family delta between the developer's ruled
option and the leaf's top-ranked one, both scored on the board
`planner._simulate_line` actually produces. `decider` is the family that has to change
for the frame to flip back.

**Inert on every frame** (flat on both sides of every comparison — a family that did not
participate in any of these decisions at all, which is a blind spot rather than a
mis-weighting): `hand`.

**Deciders:** `development` 10, `survival` 10, `(below floor)` 2

| frame | agent | category | decider | ruled | leaf | Δ development | Δ hand | Δ prize_race | Δ readiness | Δ survival | Δ threat | Δ line |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `83456015\|0\|decision\|38` | mega_starmie | ignored_threat | **development** | Nebula Beam · {C}{C}{C} · 210 dmg | s0 HAND0 = Buddy-Buddy Poffin | -0.3229 | +0.0000 | +0.0000 | -0.0126 | +0.2324 | +0.0000 | +60.0 |
| `85046350\|0\|decision\|21` | dragapult_ex | misattachment | **development** | s0 HAND3 = Basic {D} Energy · onto s0 ACTIVE = Dreepy | s0 HAND1 = Ultra Ball | -0.0537 | +0.0000 | +0.0000 | -0.0030 | +0.0002 | +0.0000 | +0.0 |
| `86089638\|0\|decision\|18` | dragapult_ex | misattachment | **development** | s0 HAND5 = Basic {P} Energy · onto s0 BENCH0 = Dreepy | s0 HAND4 = Ultra Ball | -0.1162 | +0.0000 | +0.0000 | -0.0030 | +0.0005 | +0.0000 | +0.0 |
| `85163634\|1\|decision\|17` | mega_starmie | missed_win | **development** | Turbo Flare · {C} · 50 dmg | s1 HAND0 = Lillie's Determination | -0.2028 | +0.0000 | +0.0000 | -0.0015 | +0.0007 | +0.0000 | +0.0 |
| `82749168\|1\|decision\|65` | mega_starmie | wasted_resource | **development** | Jetting Blow · {W} · 120 dmg | s1 HAND1 = Lillie's Determination | -0.1327 | +0.0000 | +0.0000 | -0.0008 | +0.0005 | +0.0000 | +0.0 |
| `82750161\|1\|decision\|60` | mega_starmie | wasted_resource | **development** | Jetting Blow · {W} · 120 dmg | s1 HAND2 = Buddy-Buddy Poffin | -0.2028 | +0.0000 | +0.0000 | -0.0015 | +0.0007 | +0.0000 | +60.0 |
| `83116501\|0\|decision\|70` | mega_starmie | wasted_resource | **development** | s0 HAND4 = Basic {W} Energy · onto s0 ACTIVE = Mega Starmie ex | s0 HAND1 = Buddy-Buddy Poffin | -0.2028 | +0.0000 | +0.0000 | -0.0015 | +0.0007 | +0.0000 | +60.0 |
| `83457493\|1\|decision\|33` | mega_starmie | wasted_resource | **development** | End | s1 HAND1 = Buddy-Buddy Poffin | -0.2028 | +0.0000 | +0.0000 | -0.0015 | +0.0007 | +0.0000 | +60.0 |
| `83686860\|1\|decision\|13` | dragapult_ex | wasted_resource | **development** | End | s1 HAND0 = Lillie's Determination | -0.0261 | +0.0000 | +0.0000 | -0.0004 | +0.0005 | +0.0000 | +0.0 |
| `83967841\|1\|decision\|17` | mega_lucario | wasted_resource | **development** | End | s1 HAND3 = Ultra Ball | -0.0687 | +0.0000 | +0.0000 | -0.0011 | +0.0002 | +0.0000 | +0.0 |
| `85709280\|1\|decision\|55` | mega_lucario | misattachment | **survival** | s1 HAND4 = Air Balloon · onto s1 ACTIVE = Meowth ex | s1 HAND4 = Air Balloon · onto s1 BENCH0 = Solrock | +0.0000 | +0.0000 | +1.0156 | +0.0000 | -1.4595 | +0.0000 | +0.0 |
| `83966968\|0\|decision\|45` | mega_starmie | missed_disruption | **survival** | s0 HAND2 = Harlequin | Retreat | +0.0548 | +0.0000 | +0.0000 | +0.1003 | -0.5000 | +0.0000 | +0.0 |
| `85163079\|0\|decision\|51` | mega_starmie | missed_win | **survival** | s0 HAND2 = Basic {W} Energy · onto s0 ACTIVE = Mega Starmie ex | s0 HAND2 = Basic {W} Energy · onto s0 BENCH0 = Cinderace | +0.0000 | +0.0000 | +0.0000 | -0.0045 | -2.1562 | +0.1000 | +0.0 |
| `83116501\|0\|decision\|60` | mega_starmie | other | **survival** | Jetting Blow · {W} · 120 dmg | Retreat | +0.0000 | +0.0000 | +0.0000 | +0.0000 | -0.4961 | +0.0000 | +0.0 |
| `82717711\|0\|decision\|37` | mega_starmie | slow_setup | **survival** | Retreat | Turbo Flare · {C} · 50 dmg | +0.0000 | +0.0000 | +0.0000 | +0.0000 | -0.2461 | +0.0000 | +0.0 |
| `85709280\|1\|decision\|42` | mega_lucario | slow_setup | **survival** | s1 HAND3 = Air Balloon · onto s1 ACTIVE = Meowth ex | s1 HAND3 = Air Balloon · onto s1 BENCH0 = Solrock | +0.0000 | +0.0000 | +1.0156 | -0.0000 | -1.3733 | +0.0000 | +0.0 |
| `82752604\|0\|decision\|16` | mega_starmie | wasted_resource | **survival** | Turbo Flare · {C} · 50 dmg | Retreat | +0.0000 | +0.0000 | +0.0000 | +0.0052 | -0.0625 | +0.0000 | +0.0 |
| `83007714\|1\|decision\|8` | mega_starmie | wasted_resource | **survival** | End | Retreat | +0.0000 | +0.0000 | +0.0000 | +0.0000 | -0.1875 | +0.0000 | +0.0 |
| `83686860\|1\|decision\|29` | dragapult_ex | wasted_resource | **survival** | s1 HAND2 = Drakloak · onto s1 BENCH0 = Dreepy | s1 HAND4 = Basic {R} Energy · onto s1 ACTIVE = Meowth ex | +0.0000 | +0.0000 | +0.0000 | +0.0105 | -0.9990 | +0.0000 | +0.0 |
| `83457493\|1\|decision\|31` | mega_starmie | wrong_supporter | **survival** | s1 HAND4 = Harlequin | s1 HAND3 = Boss’s Orders | +0.1097 | +0.0000 | +0.0000 | +0.0221 | -1.1309 | +0.0000 | +0.0 |
| `84071010\|0\|decision\|64` | mega_lucario | wasted_resource | **—** | s0 HAND0 = Basic {F} Energy · onto s0 BENCH1 = Makuhita | s0 HAND0 = Basic {F} Energy · onto s0 BENCH0 = Lunatone | +0.0000 | +0.0000 | +0.0000 | -0.0034 | +0.0000 | +0.0000 | +0.0 |
| `86090164\|1\|turn\|2` | dragapult_ex | wrong_supporter | **—** | s1 HAND0 = Basic {P} Energy · onto s1 ACTIVE = Dreepy | s1 HAND0 = Basic {P} Energy · onto s1 BENCH3 = Dunsparce | +0.0000 | +0.0000 | +0.0000 | -0.0004 | +0.0000 | +0.0000 | +0.0 |
