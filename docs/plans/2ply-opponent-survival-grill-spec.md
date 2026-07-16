# 2-ply opponent survival / return-KO reachability — GRILL SPEC (to grill, not built)

**Status:** grill spec — seeds the session, no decisions locked. Companion to
[board-state-valuation-grill.md](board-state-valuation-grill.md) (the leaf — my-side readiness; this doc
is its deliberately-excluded opponent-facing counterpart), [ply1-turn-search-grill-spec.md](ply1-turn-search-grill-spec.md)
(the sound within-turn search; this layer is heuristic, sits above it), and
[t0-planner-disposition.md](t0-planner-disposition.md) (class D — opponent-facing — is this doc's scope).
[hypergeometric-fetch-closure.md](hypergeometric-fetch-closure.md) is the deferred probability refinement
this layer will eventually want. Graduates to an ADR (next free **0064**, unless ply-1/leaf claim it first
— check `docs/adr/README.md`) once grilled.

## Thesis

Two of the leaf's `readiness` design is deliberately silent on the opponent's board — that's this layer's
job (`board-state-valuation-grill.md` §Target: "the opponent is NOT modelled here — the survival term + the
later 2-ply own that"). This spec is that survival/2-ply layer: **how much development can the opponent's
board reach by their next turn, and does it kill me or let them punish a greedy promote/hold** — a bounded,
heuristic, one-development-step lookahead (promote + evolve + attach + attack), NOT a full search.

## THE VERIFIED GAP — a precise, code-cited starting point

`Pilot._incoming_worst` (`src/common/strategy/planner.py:2056-2075`) is the closed-form "Incoming" the
survival term (`_PLANNER_SURVIVAL_W = 50.0`, flat) and `_survives_after_ko` already use. Read closely:

```python
for p in opp_bodies:
    pstat = self.stats.get(p.get("id"))          # <-- looks up the body AS IT CURRENTLY IS
    energy = len(p.get("energies") or []) + 1     # allows ONE attach next turn
    if pstat.can_pay_cheapest(energy):
        worst = max(worst, int(self._predicted_max_damage(pstat, {"id": my_id})))
```

It allows **one Energy attach**, but **never an evolution**. A benched Riolu is scored as Riolu's own
(trivial) attack — never as "could evolve to Mega Lucario ex and swing for real damage." This is the
exact, named gap the user's worked example exposes, and it is entirely mechanical to state: extend the
per-body loop to also consider **one reachable evolution step** of `p`, gated on availability.

## The worked example — VERIFIED numbers (never recalled; read from `pilot._attack_stat` / `EN_Card_Data.csv`)

Board: my Active is a Mega Starmie at **270 HP remaining**, 1 energy, empty bench, hand = Lillie's
Determination + Wally's Compassion, no energy attached yet this turn. Opponent's Active = Riolu; their
bench has one more Riolu with 1 Energy. I can KO their Active Riolu this turn.

**Verified card facts** (`data/EN_Card_Data.csv`, `pilot._attack_stat` via the live provider):
- `Riolu` (id 677) → `Mega Lucario ex` (id 678, HP 340) — **single hop**, confirmed both in
  `docs/rulebook.txt` Appendix 1 and `docs/rules.md` §4: *"`Riolu` → `Mega Lucario ex` is a single hop."*
- **Aura Jab** (attack id 982): damage **130**, cost **1**.
- **Mega Brave** (attack id 983): damage **270**, cost **2**, `nextTurnSameAttackLock=True` (can't reuse
  next turn — this is the card fact behind the ep85058574 correction *"using Mega Brave now means we
  cannot use it next turn"*; it also matters symmetrically for THIS layer's own next-ply reasoning).
- `docs/rules.md` §4 (`[RULE: rulebook L335]`): evolving into a Mega ex **does NOT end the turn** — *"you
  can evolve into the Mega and still act/attack"* — the opposite of the old Mega-EX rule. This is what
  makes the opponent's worst-case turn (promote → evolve → attach → attack) legal in ONE turn.

**The two variants, both arithmetically exact:**
- Bench Riolu has **1 energy**: opponent's worst case = promote it, evolve to Mega Lucario ex (legal,
  doesn't cost the turn), attach the 2nd energy (now affords Mega Brave, cost 2), attack for **270** —
  EXACTLY KOs my 270-HP Mega Starmie. Correct answer: play **Wally's Compassion** (defensive).
- Bench Riolu has **0 energy**: even after one attach next turn they have only 1 energy — affords only
  **Aura Jab (130 < 270)**, no KO. Correct answer: play **Lillie's Determination** (greedy is fine).

`_incoming_worst` as written returns **Riolu's own attack** in both variants (never reaching Mega Brave),
so `_survives_after_ko` reports "survives" in variant 1 too — the false negative is exact and reproducible.

## The prize-math promote scenarios — MOSTLY ALREADY BUILT (a sharper starting point than "build from scratch")

The user's other two scenarios (opp at 2–3 prizes, my Mega Lucario ex KO'd, promote Hariyama not the
3-prize Mega Lucario / promote Mega Lucario when the opponent can't punish) map almost exactly onto
**existing, shipped hypotheses** — `src/common/strategy/baseline/baseline_promote.py`:

- `interpose-the-cheap-attacker-to-preserve-the-wincon` (+50): promote a cheap body over the wincon when
  `opp_prizes_remaining >= 2` and `bench_wincon_prize_value > card_prize_value` — **exactly** "opp at 2-3
  prizes, don't feed them the 3-prize Mega Lucario."
- `dont-promote-into-their-prize-reach` (−20): softens promoting the wincon further when
  `card_prize_value >= opp_prizes_remaining >= 2`.
- Together these already implement the DEFAULT half of the user's example (scenario 2: opp prize-rich →
  interpose the cheap attacker).

**The gap is scenario 3 — the flip when the opponent CAN'T punish.** `interpose` fires on exactly THREE
drivers (weakness trade / an accel_source powering an underpowered finisher / a shown gust) — **none of
them is "the opponent's board literally cannot afford to KO my wincon next turn."** That's a 4th driver
this layer supplies: a return-KO reachability veto, reusing the extended `_incoming_worst`
(promote+evolve+attach) to check whether the opponent's BEST reachable next-turn attack actually threatens
the wincon. When it can't (their attacker is under-energized and can't evolve+attach to a lethal number
this turn), `interpose` should STAND DOWN and `promote-the-ready-wincon` (+40) should win instead.

**This reframes the deliverable:** not a new promote family, but ONE new opponent-reachability primitive
(the extended `_incoming_worst`) that (a) fixes the leaf's survival term, AND (b) becomes `interpose`'s
missing 4th driver / a new stand-down condition. One piece of machinery, two consumers.

## Grill questions

1. **The reachability primitive itself.** Extend `_incoming_worst` (or a new sibling) to try, per opponent
   body: current attack, OR one evolution step's attack if that evolution is "available" (the availability
   gate is the crux — see Q3). Cap at ONE evolution hop (mirrors the leaf's own hop-discount) and ONE
   attach (existing behavior) — no deeper opponent search; this stays a bounded, heuristic lookahead, not
   a tree.
2. **Consumers.** (a) The leaf's survival term — swap the flat `_PLANNER_SURVIVAL_W = 50.0` bit for
   something MAGNITUDE-aware: a bench-empty active-KO is a **game LOSS**, not a flat penalty — it should
   scale toward `KO_SCORE`-class, not sit as a sub-prize nudge (verify this doesn't violate the hard-rung
   invariant — a LOSS estimate is not a positional score, decide how it's expressed). (b) `interpose`'s
   4th driver / a stand-down condition on `dont-promote-into-their-prize-reach` when the reachability read
   says no punish is possible.
3. **Availability gate (the hardest part — bounded pessimism, not blind pessimism).** "Could this body
   reach a lethal evolved attack" needs SOME bound on whether the evolution card is actually gettable —
   simplest first cut: is it anywhere in their deck+hand at all (mirrors the leaf's v1 coarse evo-gate,
   `board-state-valuation-grill.md`), sharpened later by the deferred hypergeometric work
   (`hypergeometric-fetch-closure.md`) and the Read/Scouting layer (`src/common/scouting/`,
   `board.opponent` facade, ADR-0047) for archetype-level "do they even run this line." AVOID the phantom-
   threat failure mode (assume-they-have-everything → play scared, the mirror image of the phantom-KO
   bug already guarded against on OUR side, `_develop_rollout_line`'s `>= KO_SCORE` defer).
4. **Symmetry with `nextTurnSameAttackLock`.** If the opponent's best attack is transient-locked from a
   PRIOR turn (`TransientTracker`, ADR-0033 — the same mechanic Mega Brave's lockout uses), this layer
   must read that state, not just energy/evolution — else it manufactures a threat that can't legally fire.
5. **Scope boundary vs the leaf and vs ply-1 search.** This layer is explicitly HEURISTIC (predicted
   opponent zones, no manual-coin resolution needed since it's not simulating a full turn) — unlike the
   win rung (sound) and unlike ply-1 (sound, own moves only). It must never be allowed to override a sound
   win/KO rung; it only ever adjusts sub-prize survival scoring and promote-family drivers.
6. **Cost.** One extra reachability pass per opponent body per candidate line — bounded by bench size
   (typically ≤5), cheap; confirm against the Kaggle ~10min/match budget once wired (no hard caps needed
   yet per standing instruction — this is a grill/measure-first task).

## Scope

- **IN:** the extended opponent reachability primitive (one evolve + one attach); wiring it into the
  leaf's survival term (magnitude-aware) and into `interpose`/`dont-promote-into-their-prize-reach`'s
  missing driver; the coarse availability gate; `TransientTracker` lockout-awareness.
- **OUT:** a full opponent search/tree (that's what makes this "2-ply" heuristic rather than exhaustive —
  ply-1's exhaustive search is MY moves only), the fine hypergeometric draw-odds (deferred, its own note),
  per-card situational opponent modeling, anything requiring a learned opponent model.

## Success measure

The two named scenarios above (bench-energy 1 → defend; bench-energy 0 → develop) must rank correctly once
wired — they are exact, arithmetic, reproducible test cases, not vibes. Regression bench: the class-D
correction set in `t0-planner-disposition.md` (bad_target 26, prize-math, `ignored_threat`,
`missed_disruption` — e.g. ep84889539 *"KOing the Hariyama awakens their 440HP beast... better to attack
but NOT KO"*). No regression on `interpose`/`dont-promote-into-their-prize-reach`'s existing passing cases
when the new driver/stand-down is added (the reviewed correction corpus + the tuner's score-diff gate).

## Where things live

- **The gap:** `_incoming_worst`, `_survives_after_ko` — `src/common/strategy/planner.py:2048-2075`.
  Leaf survival term: `_leaf_value`, `_PLANNER_SURVIVAL_W` — `planner.py:2019-2044`.
- **The promote family:** `src/common/strategy/baseline/baseline_promote.py` — `interpose-the-cheap-
  attacker-to-preserve-the-wincon`, `dont-promote-into-their-prize-reach`, `promote-the-ready-wincon`.
- **Card/attack facts:** `pilot._attack_stat(attack_id)` (`src/common/pilot.py:1920`), `CardStat`/
  `data/EN_Card_Data.csv` — **verify at source**, per `CLAUDE.md`, never recall (this doc's own numbers
  were pulled this way — the pattern to repeat when building).
- **Rules:** `docs/rules.md` §4 (evolution timing, the Mega-ex turn-not-ending delta) — the authority for
  whether the opponent's worst-case line is even legal.
- **Lockout state:** `TransientTracker` (ADR-0033) — `nextTurnSameAttackLock`/next-turn-grant tracking.
- **The Read / bounded pessimism:** `src/common/scouting/`, `board.opponent` facade (ADR-0047),
  `opponent_resources.py` (`hand_size_delta` etc.).
- **Deferred sharpening:** [hypergeometric-fetch-closure.md](hypergeometric-fetch-closure.md).

## Builder gotchas (carried forward — a remote/fresh session needs these without local memory)

- **This layer is HEURISTIC, not sound** — unlike the win rung and unlike ply-1's search. It must never
  preempt a sound win/KO; it only refines sub-prize survival/promote scoring (mirrors the leaf's
  capped-below-a-prize invariant).
- **Bounded pessimism, not blind pessimism** — assuming the opponent has every possible piece manufactures
  phantom threats (play scared, chip the deck's actual win rate) exactly as assuming they have nothing
  manufactures phantom safety (the bug this doc opens with). The coarse "is it anywhere in deck+hand" gate
  is the deliberate middle ground for v1; sharpen only with real probability (the hypergeometric note),
  never a magic-number fudge.
- **A magnitude-aware survival term is a scale change** — re-check every consumer/threshold sized against
  the old flat `_PLANNER_SURVIVAL_W = 50.0` before shipping a bigger number (the ADR-0060 lesson: a big
  new positive/negative term silently voids guards calibrated against the old scale).
- **Verify every card/rule fact at the point of use** — this doc's own numbers (Mega Brave 270/cost-2/
  lockout, the single-hop evolution, the turn-not-ending delta) were pulled from `pilot._attack_stat` and
  `docs/rules.md` this session; a builder must re-verify for whatever card/matchup a real correction names,
  never assume this doc's examples generalize to other decks.
- **`tune.py` clobbers `tuned.json`**; **`src/cg/` is off-limits**; retest through the real `decide()`,
  never an isolated hand-built probe (manufactures phantom misplays by omitting realistic options).

## Related

[[posture-target-selection-gap]] · [[snipe-threat-two-signals]] · [[promote-after-ko-priority]] ·
[[opponent-model-facade-adr-0047]] · [[prize-economy-fetch-grilled]] · [[readiness-leaf-spend-account]].
ADRs: 0031 (Turn Planner), 0033 (TransientTracker), 0040 (Match Objectives / Path Denial), 0044 (opponent-
choice snipe reads), 0047 (Opponent Model facade).
