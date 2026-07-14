# TODO — delete the two dead accessor families

Deferred cleanup, agreed 2026-07-14. **Behavior-neutral in both cases** (zero `src/` readers), so
this is dead-weight removal, not a fix. Do it on the next combat/scouting pass.

---

## 1. The Brief `threats` half — delete, don't wire

**Delete:** `Board.brief_is_threat` / `brief_target_role` / `brief_target_ids`
(`src/common/pilot.py:553-575`), the `Board.brief_threat_ids` field + its compute
(`pilot.py:430`, `:3011`, `:3152`), and the threat half of `resolve_brief_cards`
(`src/common/scouting/briefs.py:95`).

**Keep:** `threats[]` in the Brief JSON and `brief.schema.json` — it is the authoring rationale the
matchup-genie writes and a human reads when tuning. It does not need a runtime consumer, and
pretending it has one is what produced this orphan.

**Why not implement it** (grilled 2026-07-14 — do not re-litigate without new evidence):

1. **The list is not well-typed for the accessor.** Across the 8 shipped Briefs, `threats[]` contains
   *Trainer* cards — `Boss's Orders` + `Enhanced Hammer` (alakazam), `Boss's Orders` (hop),
   `Maximum Belt` (kyogre). Those never occupy a board slot, so `brief_is_threat(card_id)` asked about
   an opponent body can never match them.
2. **The Pokémon entries are mostly already routed.** Threats ⊆ targets in `archaludon_ex_cinderace`
   and `cinderace_mega_starmie_ex`; Mega Lucario ex, Fezandipiti ex and Latias ex are in both lists in
   their Briefs. That overlap already reaches the Pilot through `brief_target_roles` → `MatchupPlan`,
   carrying a *priority number*, not a bool.
3. **The defensive residue is already computed, and computed better.** `Objectives._predicted_max_damage`
   (`objectives.py:243`) walks every opponent body — Active *and* Bench — and prices max damage against
   my body straight off card facts; `Read.threats` Intel supplies the *unseen* attackers with a
   γ-scaled deploy lead (`objectives.py:249-258`). A bool carries strictly **less** information than
   the number the damage math already holds. Same shape as the `bench_threat_present` fossil (WP1).
4. **What is genuinely non-derivable does not fit a bool anyway.** The value in the `why` prose is
   *defensive doctrine about MY board* — "seat a non-ex Active" (Maximum Belt), "don't pre-load Special
   Energy on one body" (Enhanced Hammer), "a gust does NOT disable the +30 aura" (Hop's Snorlax),
   "sequence Items before the lock" (Budew). None of that is "is card X a threat: yes/no". Its correct
   home is a registered **`opponent_properties`** lever
   (`src/common/scouting/opponent_properties.json` → `board.opp_property` / `opponent.disposition`),
   which is exactly where `opp_comeback_disruptor` and `opp_ex_damage_immune` already live.

⚠️ **Naming trap for whoever picks this up:** `Read.threats` and `Brief.threats` are two *different*
data sources sharing a name. The Read's come from the mined archetype **dossier**
(`scout.py:109` ← `artifact.py:51`) and **are consumed**. The Brief's are hand-authored and are not.
A grep for "are threats consumed?" answers yes — about the wrong one.

**This does not close the posture gap.** It only stops a wrong-shaped surface from *looking* like it
might. Defensive posture closes one `opponent_properties` lever at a time, each driven by an actual
correction. See `[[posture-target-selection-gap]]`.

---

## 2. `CombatMath.rider_recoil` — a duplicate, not dead logic

**Recoil is fully priced.** The Pilot has its own private copy and calls that:

```
Pilot._rider_recoil        (pilot.py:1934)  <- called by _recoil_flips_doom (pilot.py:2089)
CombatMath.rider_recoil    (combat.py:132)  <- zero callers, zero tests
```

Same body, same `AttackStat.recoil` read. **The same shadowing exists for the siblings:** every caller
in the codebase — `pilot.py`, `planner.py`, `objectives.py`, `doctrine_gust.py` — uses the Pilot's
underscore `self._rider_snipe` / `self._rider_spread`, while `CombatMath.rider_snipe` / `rider_spread`
are only ever called from *inside* `combat.py` (lines 361, 369). Snipe and spread got away with the
duplication because both copies have callers; recoil is where it became visible, because the Pilot's
copy won and CombatMath's got nothing.

So this is an **ADR-0052 consolidation leftover** — that ADR made `CombatMath`/`damage.py` the one home
for combat facts, and these three private Pilot accessors were supposed to go with it.

**Do:** delete `Pilot._rider_snipe` / `_rider_spread` / `_rider_recoil` and repoint every caller at
`CombatMath`. Not a delete of `rider_recoil` in isolation — that would leave the duplication in place
and just remove the evidence of it.

**Scope:** 5 modules, mechanical, behavior-neutral. Wants its own commit.
