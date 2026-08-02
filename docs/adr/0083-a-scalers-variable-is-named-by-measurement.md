# ADR-0083 — A visible-state scaler's VARIABLE is named by measurement, and a fit may only claim a variable the sweep controls

**Status:** Accepted (grilled 2026-07-30, `/grill-with-docs` on Issue #213 — twelve locked
decisions). Build: Issue #213. **Refines ADR-0032** (the Damage Formula / Attack Effects) rather
than overturning it: the `base + per_unit × count(variable)` shape and the override table's
deltas-only, conservative-by-construction discipline both stand. What this adds is a rule about
*where the variable's NAME may come from*, and a corresponding obligation on the measurement
harness.

**Context issues:** Issue #213 (this grill / build), Issue #188 (consumes the threat-rank half),
ADR-0032 (the Damage Formula), ADR-0064 + its Amendment A (the Incoming reads), ADR-0072 (the two
mid-build merit gates this cleared).

**Number is a rebase artifact.** `docs/adr/README.md` records six collisions in four days and
concludes: claim nothing, cite the issue, renumber at rebase. 0082 is claimed by Issue #188's grill
on an unmerged branch, so this took 0083 and expects to move. **Cite it as ADR-0083, Issue #213.**

## Context

Two attacks in the pool scale on the **combined** bench count — Skeledirge's Torcherto (274) and
Lillie's Clefairy ex's Full Moon Rondo (371) — and they carry byte-identical text: *"This attack
does 20 more damage for each Benched Pokémon (both yours and your opponent's)."*

They were priced differently, and both wrongly. 371 had no scaler at all, so a full board read as
its printed 20 instead of 200. 274 shipped an engine-fitted override naming the attacker's **hand
size** at 5 damage per card — a variable that has nothing to do with the card.

The obvious fix is one regex in `_SCALE_FAMILIES`. It is the wrong fix, and the reason it is wrong
is the whole point of this ADR.

**The override would have shadowed it.** Overrides apply *after* parsing, so adding the regex would
have fixed 371 and left 274 exactly as wrong, with the two identical texts still priced differently
— the acceptance criterion met in letter only.

**And the bad fit was not a fluke.** `derive_overrides` emits a scaler only on an EXACT integer
linear fit — zero residuals, positive slope, at least three distinct points. That guard did its job
and still produced a wrong answer, because the harness offered the fitter only two variables it
recorded (`myHandSize`, `attackerEnergies`) while the variable that actually moved the damage was
one it neither swept nor recorded: both seats benched every drawn basic, uncapped and unlogged. The
fitter fitted the only thing it could see. A conservative fit over an uncontrolled variable is not
conservative — it is confidently wrong, and it outranks the parser by construction.

Re-measurement confirms it: 274's dealt damage is not linear in hand size at all (hand 27→160,
21→160, 11→140, 12→160, 13→140), so today's fitter would emit nothing for it. The shipped override
was a stale artifact of a measurement nobody could audit, because `reports/attack_audit/` is
gitignored.

## Decision

### 1. The engine fit is authoritative for a scaler's variable; no text parser is added for this family

`_SCALE_FAMILIES` is not extended for the combined-bench family. The fact is measured and shipped
through the override table. This ratifies what `src/common/CONTEXT.md` already said about the Damage
Formula — *fitted by sweep-probing the engine, never text-parsed* — for the case where the two
sources disagree.

The alternative (parse as a seed, let the engine correct it) was considered and rejected **for
naming the variable**. It is a fine story for magnitudes; it is a bad one here, because the failure
mode is precisely a plausible-looking name that no measurement supports, and a regex is exactly the
mechanism that produces plausible-looking names.

*Accepted cost, stated plainly:* the override table is keyed per `attackId`, so a future card with
this text needs its own audited entry rather than inheriting a pattern. With two attacks in the pool
that is cheap; at twenty it would argue for revisiting this.

### 2. A fit may only claim a variable the harness CONTROLS and RECORDS

The corollary, and the part that generalises past this issue. Concretely (REQ-AUDIT-0018):

- Every plan pins **both** seats' bench counts; only a bench sweep moves one, and it pins the other.
  Pinning them across the *energy and hand* sweeps too is the root-cause fix — with the benches
  loose, a bench scaler can still fit hand size, which is how this started.
- A cap is a **target**, not just a ceiling: the drive waits (within bench patience) for both seats
  to reach it. A ceiling alone still fires at whatever the shuffle benched.
- Both bench counts are recorded on **every** measurement, unconditionally, so the historical
  confound is visible in retrospect rather than silent.
- When patience runs out the attack fires anyway and the record carries the **actual** counts. A
  missed target must degrade to a duplicate fit point, never a wrong one.

### 3. The bench family's variable is named by JOINING two single-variable sweeps

One sweep cannot name it. Sweeping the attacker's bench yields the *same* slope for an
attacker-bench scaler and a combined-bench one; a defender-bench scaler yields none. So
(REQ-AUDIT-0019) the derivation runs two independent single-variable sweeps and joins their slopes:

| attacker slope | defender slope | emitted variable |
|---|---|---|
| positive | flat | `atk_bench` |
| flat | positive | `def_bench` |
| positive | equal to attacker's | **`both_bench`** |
| positive, unequal | positive, unequal | none — gap ledger |

Three guards make it honest, each earned from how the original defect happened:

- **Both axes must be measured** before anything is named. One axis alone cannot separate
  `atk_bench` from `both_bench`, and the conservative answer to an ambiguity is silence.
- **The pinned seat must be provably constant** across an axis, read off the records rather than
  trusted from the plan — patience can run out and a seat can drift.
- **Flat and noisy are distinguished.** Flat (every measurement equal) is slope 0, the legitimate
  answer for the seat a one-sided scaler ignores. Noisy (no exact fit) rejects the whole family.
  Conflating them would let a noisy axis masquerade as a one-sided scaler.

REQ-AUDIT-0008 stays literally true: each sweep still varies exactly one state variable. It is the
*derivation* that joins them.

### 4. `both_` is a third direction class in the scaling-variable vocabulary

Every existing variable is attacker- or defender-relative (`atk_*` / `def_*`). A variable counting
both sides at once is the first that is neither, and the pool holds a second instance of the shape
(96 Teal Mask Ogerpon ex, *"for each Energy attached to both Active Pokémon"*), so this is a class
rather than a one-off.

The per-decision damage context computes the combined value as the sum of the two per-side counts it
already holds. Because that sum is direction-symmetric, **one key is correct whichever side is
attacking** — no mirroring logic, and the oracle keeps a single dictionary lookup per scaler with no
expression evaluation. Rejected alternative: letting `scaleVar` hold an expression
(`"atk_bench+def_bench"`), which would turn a closed vocabulary of named facts into a mini-language
inside the damage oracle.

### 5. One card fact, one representation

The same discipline applied to the fact that motivated leg 1. Hand-size damage had **four**
representations: a dedicated regex pair feeding a stored field, the Damage Formula's scaling parse
over the *same sentence*, a Function Tag, and a flat `+500` rank boost. Three are retired:

- `AttackStat.handSizeDamage` is now a **property** derived from the scaling term, so it cannot
  drift from the scaler and it honours an engine-fitted override for free (a stored field is fixed
  at parse time and would not have).
- The dedicated regex pair is deleted, verified equivalent across all 1,556 pool attacks first.
- The flat `_HAND_SIZE_ATTACKER_BOOST` is deleted; see §6.
- The **Function Tag survives**, as a routing trigger for the hand-disruption reads only. Routing is
  what a Function Tag is for; it was never a damage input.

The card-level credit moves into one shared `CombatMath.card_level_damage` fallback that both
fallback paths reach. They previously hand-rolled it and did it *differently* — one as an
either/or against the printed roll-up, the other added unconditionally beside the per-attack oracle.

### 6. The threat rank prices the Damage Formula, and its flat proxy is deleted in the same change

`_body_threat_rank` and `_forced_promotion_key` ranked bodies by printed `maxDamage` and the
provider's printed forward index — the Damage Formula's base term with the whole scaling term
dropped. `CombatMath.threat_ceiling` / `forward_threat_ceiling` price the same question against the
live board, **defender-free and W/R-free** (folding a defender in would make the snipe order swing
on my own Active's typing).

`_HAND_SIZE_ATTACKER_BOOST` (+500) is deleted in the same change, not a later one: it is a proxy for
exactly the fact the scaled read now computes, so keeping both double-counts one card fact — and as
a flat constant keyed off a tag covering a single card, it could never generalise to any other
scaling attacker.

Behind kill switch `scaled_threat_rank`, shipping **ON**. A flag that ships OFF makes the change a
no-op on the board, and both merit gates measure the ON behaviour — gating on evidence for a state
you then don't ship is not a gate. The switch survives as an incident lever that restores the
printed-only read exactly, pinned in both directions.

## Consequences

- **Adding a scaler family is now harness work, not a regex.** Each of the four deferred candidates
  (`both_active_energy`, `atk_bench_stage2`, `def_counters_all`, `def_ex_in_play`) needs its own
  sweep capability. That is the intended cost of §2, and the per-seat machinery built here makes
  each one cheaper.
- **Existing measurements are stale for bench-sensitive attacks.** Every plan now pins both benches,
  so `reports/attack_audit/` wants a recapture. The seven `atk_active_energy` overrides are on a
  variable the harness genuinely sweeps and are untouched.
- **A silent-skip bug fell out of this and is fixed.** Error records did not carry their sweep
  point, so every failed sweep on a scenario shared one `record_key` with that scenario's panel
  record — and since an error never clobbers a success, the failure vanished. Rare before; routine
  once ten sweep points landed on `vanilla`. Directly contrary to REQ-AUDIT-0006.
- **One re-priced attack has no corpus frames.** Skeledirge appears in zero corrections, so its
  correction rests on engine measurement alone and no corpus gate can see it. Stated rather than
  papered over.
- **Gates.** Decision Gate (`threat_sweep.py --rank`, both sides forced): **0 decided-pick flips
  over 331 frames**. *(The `--rank` mode was deleted by Issue #243: the question is answered here and
  the substance is covered by `tests/strategy/test_scaled_rank_corpus.py`, which since that issue runs
  over the full 372-frame corpus — 7 more Kadabra/Alakazam frames than the 331 measured here, all
  passing.)* Discrimination Gate (`leaf_lab diff` vs the committed baseline): **PASS, 0
  unruled `OK → MISS` over 267 frames**. Doom sweep: 304/319, the same 15 one-directional
  disagreements as before on a larger corpus.

## Alternatives rejected

- **Add the regex, leave the override.** Smallest diff. Ships the fix for 371 and leaves 274 priced
  at 60 + 5×hand — an over-prediction on an empty bench, which is the soundness class the CI audit
  gate exists to fail. Two identical texts stay priced differently.
- **Invert precedence for `scaleVar` only** (parsed beats override for this one field). Fixes 274
  without deleting anything, but makes the precedence rule unguessable from either file: the next
  reader has to know this conversation happened.
- **One combined sweep** (move both benches in lockstep). Half the engine time, but it measures a
  magnitude without naming a variable — you would read the card text to decide whether the slope
  belongs to `atk_bench` or `both_bench`, re-admitting the parser as the authority through the back
  door, one decision after rejecting it.
- **Multivariate fit over uncontrolled points** already in the record set. Cheapest of all, and
  fragile in exactly the way that produced the 274 override.
- **A one-off name** (`bench_total`) instead of a `both_` class. The very next candidate has the
  same shape, so it would name one idea twice with unrelated words.
- **Ship `scaled_threat_rank` OFF and flip later.** Matches how the value model was parked, but the
  ladder is the only valid gain signal and a flag nobody flips is a dead feature — and with the flat
  boost still live behind the OFF branch, the double-count stays open in the code rather than being
  resolved by it.

## Amendment A — a measured BOUND is board-scoped too, and it cannot coexist with a fitted scaler (2026-08-02, Issue #224 follow-up)

Decision 2 says a fit may only claim a variable the harness CONTROLS and RECORDS. It was written
about `scaleVar`. The same defect was live one field over, in the coin bound, and nothing said so.

`_coin_bounds` collapsed fork records with `{r["coin"]: r}` — a dict keyed on `"min"`/`"max"` alone,
over every vanilla record for the attack. But `merge_records` keys a measurement on its sweep point,
so an attack audited with `--sweep` legitimately holds SEVERAL `coin="max"` records on the vanilla
panel, one per board, and for a board-sensitive attack they legitimately differ. The shipped
`damageMin`/`damageMax` was therefore whichever record the dict iteration landed on.

That is 274 again, one field over: variation attributed to the one variable the code recorded (the
coin) while another it did not control (the board) had also moved. It was found by building the
provenance sidecar (ADR-0108), which recorded the full fork set and made the collapse legible; it
was deliberately left unfixed there, because that change was ruled value-preserving.

**The bound is a property of one board, and ships only when the boards agree.** Fork pairs are
grouped by the controlled state they were measured on — a `min` and its `max` always share it, since
`_coin_fork` walks both outcomes of one forked position. Then:

| boards yielding a pair | emitted |
|---|---|
| one | that bound |
| several, all agreeing | that bound — corroboration, per §3's flat-axis argument |
| several, disagreeing | none — gap ledger |
| one board, two different answers | none — a measurement that does not reproduce is not a fact |

The board is the **physical** controlled state; `sweep`/`step` are excluded because they are
provenance labels, not state, and two plans land on the same board by design — the panel point pins
both benches at `_BENCH_REF = 1` and so does the `atk_bench` step-1 sweep point. Keying on the label
would file those as two boards and let one board's self-contradiction read as ordinary board
sensitivity. It also makes the last row REACHABLE: `merge_records` keys on the sweep point, so both
of those records survive the merge and land in one group.

Corroboration is kept rather than refused, and that is the one place this departs from the
conservative default. Several boards agreeing is exactly the evidence §3 already treats as
load-bearing for a FLAT axis: the variable was moved and provably does not shift the answer.
Refusing there would discard the strongest thing the harness can produce. Disagreement is the
opposite case and gets the opposite answer — the pool holds the shape (879 *"Flip a coin for each
{D} Pokémon you have in play"*, 1256 *"Flip a coin for each Energy attached to this Pokémon"*), and
the override table has no form that says "this bound is a function of the board".

That is also the honest objection to the alternative of taking the bound from the un-swept panel
point alone. It is not *arbitrary* — the reference board is a perfectly determinate choice, and the
review was right to say so. It is **silently board-conditional**: it names one board's number as the
attack's own, unconditionally, with nothing in the table marking it as measured at bench 1. Refusing
says the same thing out loud. Where the boards agree, that alternative and this rule emit the same
bound; where they disagree it ships and this rule does not, and that single row is the whole
difference between them.

**And a measured bound may not ship for an attack that HAS a scaler — whoever named it.**
`compute_active_damage` sets `dmg = damageMin/damageMax` — the bound REPLACES the base term — and
only then adds `scalePerUnit × count`. A bound measured on a board where the scaler contributes
already contains that contribution, so shipping both adds it twice: an **over-prediction**, the
single class `ci_audit_gate.py` exists to fail.

The test is the **effective** scaler — `st.scaleVar` or this run's fit — because the oracle adds the
scaling term whenever the field is set and does not care where it came from. Testing only the FIT
was the first version of this rule and `/code-review` refuted it: `_scaler` returns nothing when the
parser has already named the variable, so a parser-named scaler plus a fork pair sailed straight
through — the commoner case, missed by construction. Probed: a printed-60 `atk_hand`/20 attack with
a fork pair measured at hand 6 shipped `damageMax 100`, and the oracle then read **160** at hand 3.

The scaler survives, being base-relative and sound; the bound is dropped and the attack keeps the
text parser's, which is read off the printed sentence and is base-relative too. Recovering the base
as `dealt − scalePerUnit × count` was rejected — it compounds one inference on another, and this
generator's discipline is that an ambiguity emits silence. Measured: **0 of the 117 shipped
entries** carry both, so this is a soundness guard rather than a fix — and it is one `--sweep` run
away from being reachable.

*Accepted cost, stated plainly:* a refused bound leaves **no trace in the provenance sidecar**. That
file's contract (ADR-0108 §2) is that evidence justifies what SHIPPED, and a refused bound did not;
a measurement that established nothing belongs on the gap ledger, which is `diff_attack_audit.py`'s
job. The alternative — recording fork rows on an entry whose fields they do not justify — would make
the sidecar's central promise conditional.

**Nothing shipped changes.** All 99 `damageMin`/`damageMax` entries are classified `unaudited` in
`attack_overrides.provenance.json`, their measurements no longer exist, and ADR-0108's merge rule
preserves an entry no measurement speaks to. The end-to-end regenerate test reproduces both stores
byte-for-byte, so this is a ruling made BEFORE the recapture it governs rather than after — which is
the whole reason to make it now.
