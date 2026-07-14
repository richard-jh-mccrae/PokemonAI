# ADR-0035: Per-deck specialization of General-Strategy weights is a two-layer override — authored seeds under learned deltas

**Status.** Accepted (grilled 2026-07-02, `/grill-with-docs`) and **BUILT** — `/deck-align` is shipped
(`.claude/skills/deck-align/`) and `Strategy.weight_overrides` is live and consumed by `Pilot._weight`.
*(Status corrected 2026-07-14: it still read "build pending" long after the build landed.)* Ships with `/deck-align`
([ADR-0036](0036-deck-strategies-realign-against-the-evolving-general-strategy.md)). Written against
main's [ADR-0034](0034-deck-rules-fold-general-when-vocabulary-is-general.md) fold state
(mega_starmie `hypotheses=[]`).

**Context.** After ADR-0034, essentially **all** doctrine lives in the General Strategy and a deck
expresses itself through declarations (Roles / Lines / params). The one authored expression a deck
still lacks is a **seed-level weight** for a general rule: the Pilot scores general + deck
Hypotheses as one flat concat with **no id dedupe** (redeclaring an id double-fires), and the only
per-id override surface is `overrides` (`tuned.json`) — which [ADR-0018](0018-applying-tuner-output.md)
defines as **tuner-owned sparse deltas**: `tune.py` rewrites the file wholesale each run
(`tuner/io.py sparse_overrides` vs the authored seeds), so a hand-authored entry is **clobbered by
the next tune**. deck-genie's "per-deck strength stays tunable by id via `tuned.json`" therefore
names a *learned* path only; an *authored, doctrine-driven* band difference (deck wants
`advance-the-accel-pieces` at 30 where the general seed is 15) has no durable home. The gap also
caps ADR-0034 itself: a fold is gated **score-equal**, so a deck rule whose weight differs from the
general twin's seed **cannot fold at all** without changing someone's behavior.

**Decision.**

1. **New declarative field `Strategy.weight_overrides: dict[str, float]`** — authored per-deck seed
   overrides of Hypothesis weights **by id** (general ids), doctrine-driven, sparse, **used
   sparingly**: the default is to accept the general seed (the tuner refines later); write an
   override only when the `score_diff` corpus shows the band gap flips real decisions, or the deck
   doctrine demands the band.
2. **Precedence, low to high:** authored `Hypothesis.weight` < `Strategy.weight_overrides` <
   `tuned.json` (learned) < `AGENT_OVERLAY` (experiment, ADR-0021). `Pilot._weight` resolves the
   chain — a **replacement** (lookup) chain of absolute weights, not additive; no `Pilot.__init__`
   signature change (the Pilot already holds `self.strategy`). A deferred **pooled general-tuned**
   layer slots between the authored seed and `weight_overrides` (see Consequences).
3. **The tuner's seed baseline becomes the authored-effective weight** — `_build_pilot`'s
   `seeds = {h.id: h.weight}` merges in `strategy.weight_overrides`, so `sparse_overrides` keeps
   emitting only *genuine learned deltas* and the fit starts from the deck's authored
   specialization.
4. **Folds gain the weight-differing case:** general keeps (or takes) the universal seed; the
   origin deck records its band in `weight_overrides` — score-equal for the origin deck, the
   general seed for everyone else. Removes ADR-0034's same-weight-only constraint.
5. **Touchpoints:** `brief.py` effective-weight comparison includes the new layer;
   `test_tuned_wiring`-style validation extends to `weight_overrides` keys (every key a real
   Hypothesis id); deck-genie's override-candidate disposition points here, never at hand-edited
   `tuned.json`.

**Considered options.**

- **Hand-edit `tuned.json`** — rejected: clobbered by the next `tune.py` run; mixes authored
  doctrine into a machine-owned artifact, breaking ADR-0018's "the file *is* exactly the deltas the
  tuner found" property.
- **Thin delta-Hypothesis in the deck** (same trigger, weight = the delta, additive co-fire) —
  rejected as the general mechanism: the duplicated trigger drifts from its general twin and the
  deck keeps a rule whose whole point was to fold. Still fine where a deck adds a genuinely
  *distinct* reason on the same decision.
- **Always accept the general seed** — rejected: a doctrine-critical band difference would force
  keeping the deck rule alive purely to hold a number, blocking its fold.

**Consequences.** Ownership stays legible: `strategy.py` carries **all authored** doctrine
including specialization; `tuned.json` carries **only learned** deltas. The
[src/common/CONTEXT.md](../../src/common/CONTEXT.md) **General Strategy** entry now names both
layers. Build lands with `/deck-align` (Pilot resolution + tuner seed merge + brief/tests +
deck-genie pointer fix).

**Deferred seam — pooled general tuning (accepted 2026-07-02, build-gated).** Eventually the chain
gains a shared learned layer: authored seed < **general tuned** (pooled fit over ALL decks'
Corrections on general ids; a machine-owned `common/tuned.json` + provenance sidecar, shipped free
via ADR-0004 packaging) < `weight_overrides` < deck `tuned.json` < `AGENT_OVERLAY`. Rationale
mirrors ADR-0034: doctrine lives general, so learning about it should pool — corrections are
expensive, pooling multiplies data per rule, and a new deck inherits the learned prior from its
declarations alone. Deck layers stay above it: an authored override is a deviation claim the
population average must not erase. Two rules the build must honor: (a) because the chain is
replacement, an id under `weight_overrides` stops receiving pooled learning — `/deck-align`
hygiene flags overlays whose underlying general value has drifted since authoring (ADR-0036);
(b) each fit's baseline is the full chain below it (general fit vs authored seeds; deck fit vs
seed + general tuned + `weight_overrides`), else lower-layer values reappear as spurious sparse
deltas. **Trigger:** a second deck playing and generating Corrections — until then the pooled fit
is identical to the per-deck fit and the layer is dead weight. Naming: never "overlay" for this —
**Overlay** is the ADR-0021 experiment layer.
