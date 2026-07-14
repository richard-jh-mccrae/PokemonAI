# ADR-0034: Deck rules fold into the General Strategy when their vocabulary is general

**Status.** Accepted and BUILT (2026-07-02) — the first fold round landed (mega_starmie ships
`hypotheses=[]`), and `tools/sim/score_diff.py` is the standing neutrality gate for every
behavior-neutral change since. The policy is now executed by the recurring `/deck-align` pass
([ADR-0036](0036-deck-strategies-realign-against-the-evolving-general-strategy.md)).

**Context.** mega_starmie's `strategy.py` carried 7 deck Hypotheses. A review (2026-07-02) found
6 of 7 were already written in **universal vocabulary** — Roles (`accel_source`, `tutor`,
`win_condition`), Function Tags (`opener`, `discard_eot`, `bench_fill`), and general Board signals
(`accel_recipient_missing`, `wincon_in_hand`, `reusable_energy_in_hand`,
`active_cheap_attack_kos`) — no card ids in any trigger. Their deck-ness was *residence*, not
*content*: each was a general reflex the deck happened to author first. Meanwhile dragapult_ex
(and every future deck) would have had to re-author them. Precedent existed per-case (Hero's Cape
→ Tool doctrine ADR-0028; Ignition discipline → `dont-waste-discard-energy`; gust → ADR-0022) but
no policy.

**Decision.** A deck rule whose trigger reads only universal vocabulary **lives in the General
Strategy**, in the matching `baseline_*` cluster / doctrine (ADR-0025), under a card-name-free id.
The deck's opt-in is its **declarations** — Roles, Lines, params; a role-keyed rule is *general*
because the Role assignment carries the deck intent. Deck-specific judgments with no structural
derivation become **params** a general selector honors (`preferred_start` →
`honor-preferred-start`). A deck Hypothesis remains legitimate only while its trigger genuinely
needs deck-local knowledge no declaration can carry — and folds once its vocabulary proves general.
mega_starmie now ships `hypotheses=[]` (fold table in its strategy.py docstring); per-deck tuning
is unchanged — `tuned.json` overrides any general id per deck (ADR-0009).

**The gate.** A fold must be **score-equal** for the folded deck: same trigger + same weight +
flat-sum scoring (`pilot._option_trace`) ⇒ equal by construction; a broadened trigger must be
provably vacuous on that deck's pool (the `dont-fetch-the-setup-only-opener` structural guard —
`card_stranded_evolution`, full-depth `evolvesFrom`-chain reachability over the deck list — is
TRUE for Cinderace, so −60 fires identically). Proof is mechanical: `tools/sim/score_diff.py`
replays a corpus (206 committed correction obs + a fresh selfplay corpus, 1869 frames) through the
Pilot and diffs per-frame per-option **scores** (fired *ids* are deliberately uncompared — folds
rename). Every fold in this round: 0/1869 divergent. Near-neutral vocabulary fixes gate at
**choice** mode (chosen option unchanged); the `energy_accel`-on-Cinderace fix FAILED that gate
(16 flips toward fetching a dead card) until `fetch-the-support` learned the stranded-evolution
guard — after which it too was fully score-equal. That failure is the policy's argument: fold
mechanically, gate mechanically.

**Consequences.**
- New decks start with the folded reflexes free: opener preference, accel advancement,
  recipient-first, tutor discipline, burst conservation, coin-toss intent, dead-fetch bans —
  declare Roles/Lines/params and play.
- The General Strategy grows role-keyed rules that are SILENT for decks that don't assign the
  Role — general ≠ always-firing.
- Rationales in general rules keep the originating deck as an *example*, not a dependency.
- deck-genie authors declarations-first: a drafted deck rule must justify why no general rule +
  declaration can carry it (general-first placement), and a shipped deck rule is a folding
  candidate once proven.
- `score_diff` is the standing refactor guard (capture → diff) for any behavior-neutral change;
  the mega_starmie 24%-regression episode (two silent behavior changes in a refactor) is the
  scar this closes.
