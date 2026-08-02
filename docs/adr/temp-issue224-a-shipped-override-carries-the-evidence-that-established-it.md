# ADR-TEMP-224 — A shipped override carries the evidence that established it, and an unaudited one says so

**Status:** Accepted (2026-08-02, Issue #224). Build: Issue #224. **Refines ADR-0032** (the Damage
Formula / Attack Effects) and **completes ADR-0083** rather than overturning either: the
deltas-only override discipline stands, and so does "a fit may only claim a variable the harness
controls". What this adds is the obligation that a shipped fact be *checkable after the fact*, not
merely re-derivable.

**Context issues:** Issue #224 (this build), Issue #213 / ADR-0083 (the harness fix that produced
the evidence preserved here), Issue #225 (the four text-verified scalers), Issue #275 (owns their
measurement debt), ADR-0032 (the Damage Formula).

**Number is a temp.** Authored as `ADR-TEMP-224` per `docs/adr/README.md` §"Temp naming"; `/open-pr`
assigns the real number at rebase. **Cite it as ADR-TEMP-224, Issue #224** until then.

## Context

`src/common/attack_overrides.json` ships 117 engine-derived card facts that the damage oracle trusts
over the text parsers. The measurements that justify them lived in `reports/attack_audit/
measurements.json`, which is gitignored — and which, as of this build, **exists nowhere at all**.
So a shipped override could not be checked against its own evidence. It could only be *re-derived*,
by re-driving the engine for hours.

That is not a hypothetical cost. It is exactly how a wrong fact survived. Attack 274 (Skeledirge,
Torcherto) shipped `{"scaleVar": "atk_hand", "scalePerUnit": 5}` for an attack that does not scale on
hand size at all — it scales on the combined bench count. The fitter is conservative by construction
(exact integer fit, zero residuals, positive slope, ≥3 points) and it *still* emitted that, because
bench was a variable the harness neither swept nor recorded, so hand size was the only thing it could
fit. Re-measurement showed 274's dealt damage is not linear in hand size at any point (27→160,
21→160, 11→140, 12→160, 13→140): today's fitter emits nothing for it. The shipped value was a stale
artifact of a measurement nobody could see.

ADR-0083 fixed the *fitter*. It did not fix the **auditability gap**, which is what let the bad entry
sit unnoticed — and which ADR-0083's own Consequences recorded as owed.

Two facts found during this build shaped the decision, neither anticipated by the issue's sketch:

1. **There is nothing to backfill *from*.** `measurements.json` is absent from the worktree and from
   the main checkout. Backfill is not "read the old file"; it is a pool-wide recapture.
2. **Not every override is a fit.** Four of the thirteen scalers (120, 292, 390, 425) were shipped by
   Issue #225 as *text-verified* — one human reading one card's printed sentence — with the debt owned
   by Issue #275. Two of them (120, 425) are **provably unfittable on the harness's current axes**.
   Provenance is therefore not one kind of thing, and a generator that treats "measured" as the only
   legitimate source would delete them.

## Decision

### 1. The provenance is a committed SIDECAR, not an inline block

`src/common/attack_overrides.provenance.json`, keyed by `attackId`, beside the table it documents.

Two reasons, neither of them taste. ADR-0032 states the table's goal is *a readable list of
engine-only knowledge*; ~13 measurement rows wrapped around each of 117 entries is not that. And
`load_attack_overrides` parses that file on every provider build — on the Kaggle grader, inside a
10-minute-per-match budget — so inline evidence would be parsed and discarded on every load, forever,
to serve a reader who is never present at runtime.

The cost of two files is drift, and drift is the solvable half: §2 makes them a single emission and
`tests/sim/test_attack_override_provenance.py` fails when they disagree. Readability and runtime cost
are not recoverable once inline.

### 2. Deriving a value and recording what established it are ONE operation

`derive_entries` returns `{attackId: Derivation(fields, evidence)}`; each of the three derivation
rules (`_coin_bounds`, `_fixed_damage`, `_scaler`) returns the delta it establishes *and the records
that establish it*. `derive_overrides` is that function with the evidence dropped. `main` writes both
files from the same merged result, and the table is emitted from the sidecar's own `fields`.

Provenance that is *computed alongside* cannot describe a derivation that did not happen. Provenance
written *separately* is a second description of the same thing, free to disagree — which is the
failure this ADR exists to end, reintroduced one level down.

### 3. The record keeps the REJECTED axes, not only the winning one

A fitted scaler's evidence is every vanilla, coin-free record for that attack — the axis that won and
the axes that did not.

This is the load-bearing clause. A **flat** hand axis is what proves hand size was measured and does
not move the damage; ADR-0083 §3 already makes flat a distinct answer from noisy for exactly this
reason. For 274 the energy and hand rows read 100/100 *because the benches are pinned across them* —
that flatness is what makes hand size unfittable now, and its absence is what made the spurious fit
possible. Keeping only the fitted points would preserve the conclusion and discard the reason it is
sound.

### 4. Three methods, because "measured" and "read off the card" and "nobody knows" must not look alike

`engine_fit` | `text_verified` | `unaudited`. A closed vocabulary, documented inside the file itself
so a reader never leaves it to learn what a row claims.

- **`engine_fit`** carries evidence rows. Two entries have them today: 274 and 371, transcribed from
  Issue #224's preserved worked example — the only surviving copy of that measurement. Per-row hand
  size and energy count could not be recovered and are recorded as `null` rather than as a plausible
  number, because inventing one is the precise failure this file guards against.
- **`text_verified`** carries an `owner` (the issue that owes the measurement) and a `note` giving
  the printed sentence and why the harness cannot fit it. A debt with no owner is a TODO nobody holds.
- **`unaudited`** carries neither, and that *is* the claim.

### 5. The 111 legacy entries are classified and FROZEN, not re-driven

Every pre-existing entry is recorded as `unaudited` at its exact shipped value. Nothing shipped
changes. The gate then bites on everything new or changed:

- an override with no provenance row fails (this is the check that would have flagged 274);
- a row whose recorded `fields` differ from the table fails — including for the legacy 111, whose
  entire status is *this exact value, on no surviving evidence*;
- the `unaudited` id set is asserted as a **subset** of the bootstrap set. Backfilling one shrinks it
  and passes untouched; adding a new one fails.

The subset asymmetry is the whole gate. It makes paying the debt free and makes adding to it loud.

Recording the debt rather than paying it in one go is a correctness choice, not a budget one. A
pool-wide recapture would *change* shipped damage values rather than merely document them (ADR-0083's
Consequences: the old measurements are stale for bench-sensitive attacks), which is a different
deliverable requiring its own gate runs — and because the generator is authoritative for what it
measures, a regenerate would silently drop all four text-verified entries, reverting 425 Tenacious
Tail to computing **zero** damage. That is the blind spot Issue #225 shipped to close.

### 6. The generator may retract what it authored; it may not retract what a human ruled

The merge rule, and the part that generalises past this issue. A previously `engine_fit` entry the
fresh measurements no longer support is **dropped** — that is exactly the correct outcome for 274. An
attack the run never measured, a `text_verified` ruling, and an `unaudited` legacy value are
**preserved and reported**. `--prune` opts into dropping the last of those.

Without this, the intended workflow is unsafe: per-attack recapture (`audit_attack(274, sweep=True)`)
is a *partial* measurement set, and a generator that rewrites the table wholesale from it would
delete the other 116 entries. The rule also makes the "measured it, and it establishes nothing"
case loud instead of silent, which is the shape of every regression this ADR is about.

### 7. Both stores are written byte-identically on Windows and Linux

`Path.write_text` translates `\n` to the platform newline, so the same generator run produced a
different file on each OS and a regenerate read as a whole-file rewrite. Both stores are committed
CRLF, so the generator pins CRLF explicitly and a test asserts the committed bytes agree. CLAUDE.md
already required binary-safe writes to committed data; this is the generator honouring it.

## Consequences

- **The auditability debt is now countable.** 111 `unaudited`, 4 `text_verified`, 2 `engine_fit`.
  Before this it was 117 entries that all looked alike.
- **Backfilling is incremental and cheap.** A recapture of one attack flips one row and shrinks the
  frozen set; no test edit is needed except the ruled count, which is the point — a backfill should
  be visible.
- **`.github/filters.yml` names the two stores under `sim`.** `common_agent_core` matches
  `src/common/*.py` — `.py` only — so a table-only diff previously reached the suite through the
  `any` fail-safe. It ran, but by accident; now the provenance gate runs on a table edit by design.
- **Issue #275 gains a second reason to exist.** It already owed the four text-verified measurements;
  those four are now the only `text_verified` rows in a file that counts them.
- **The docs figure was wrong and is corrected.** `docs/attack-effects.md` said 119 attacks; the table
  holds 117. A count nobody checks is the same class of rot as an override nobody can check.

## Alternatives rejected

- **Inline `provenance` block per entry.** One file, cannot desynchronise. Destroys ADR-0032's stated
  goal for the table and pays the parse cost at runtime on the grader, to serve a reader who is never
  there. Drift is the cheaper problem, and §2 solves it.
- **Re-drive the whole pool and backfill for real.** The honest-looking answer. It changes shipped
  values rather than documenting them, needs its own gate runs, and — because the generator is
  authoritative — silently deletes the four entries the harness provably cannot fit, re-opening 425's
  zero-damage blind spot. A different deliverable wearing this issue's name.
- **Re-drive only the 13 scalers.** Narrower and aimed at the real risk class, but it carries the
  deletion hazard undiminished and buys evidence for 9 of 117.
- **Provenance for new entries only; record nothing for the existing 117.** Cheapest. Leaves an
  unaudited entry byte-indistinguishable from an audited one — the exact condition this issue calls
  intolerable, with a date attached. It is the only option that builds a gate you cannot trust.
- **A content hash instead of the recorded value.** Same detection power. Shows the reader two opaque
  hex strings where the value itself shows them what moved.
- **A fourth method for "transcribed from an issue body".** Over-modelling for two entries. `274` and
  `371` *were* established by engine measurement; where the surviving rows came from, and what they
  lost on the way, belongs in the row's `note` — which is where it is.
