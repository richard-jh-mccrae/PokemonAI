# Seam handoff: held-card risk (fetch-early vs fetch-late — disruption exposure)

**Parallel-session slot B.**
**Corpus acceptance target:** `85163634-17` (mega_starmie), xfail-strict — Ultra Ball played one turn
early (+45: `play-a-tutor-for-the-unfound-wincon` +25, `fetch-when-it-fills-a-need` +8,
`costly-fetch-sheds-junk` +12) over the deferred +266.9 attack; the human: "this move was taken one
turn too early … fetching it now risks enticing our opponent to disrupt us."

## Grill status: ✅ design grilled (spec Round 8 §5) — application seams OPEN

`docs/plans/hypergeometric-fetch-closure.md` Round 8 §5 specifies the closed form: holding a fetched
key across k opponent turns exposes it to THEIR symmetric refreshes (Judge/Harlequin);
**P(stripped before my deadline)** comes from the matched Read's rep build minus tracker-observed
plays (`copies_left_odds` pointed at their disruption count). It prices **fetch-early** (certainty
now, exposure until the deadline) vs **fetch-late** (no exposure, re-access risk) — both sides
closed-form, both legs already exist in the codebase (the closure re-access via
`fetch_closure`/`deck_odds`; the opponent rep via the Read).

**Open questions to settle (grill briefly, then build):**
1. WHERE the term lands: a graded penalty inside the whether-to-play comparator (modulating the +25
   tutor rung's band) vs a new stand-down Hypothesis. The currency-zone rule says it must REPLACE
   the jurisdiction it prices, not stack beside `dont-costly-tutor-when-starved-and-developed` (−30).
2. The DEADLINE parameter: "when will the fetched card be used?" — for the ep85163634 board the
   wincon is wanted next turn, not this one. The evolution gate (`gate_library.deploy_odds`) knows
   deployable-now; a "usable-this-turn" predicate for the FETCHED card is the missing leg (relates
   to the quota gate, scope doc Stage 4 — do NOT build the full quota gate for this; the narrow
   "fetched target not playable this turn" predicate suffices).
3. The opponent-side probability: `copies_left_odds` exists for the opponent rep — verify what the
   Read actually exposes for Judge/Harlequin counts (scouting briefs / opponent_properties) before
   promising the exact form; fail direction = suppressor (no rep → assume no exposure → no veto).

## Build plan

1. RED: the corpus xfail + a focused test on the recorded board (fetch stands down; next best is the
   attack — mirror `test_deferred_cluster_pins`' shape).
2. Implement the exposure term per the settled placement; wire the Read's disruption count with the
   fail-open default.
3. Re-audit the fetch pins: `test_fetch_doctrine.py` (whether-to-play band tests), the hold-the-fetch
   corpus PINS (`83007714-8`, `85045840-12`, `83967841-17`, `83661652-29`, `82525741-78`,
   `85046350-79` — six passing pins that must NOT regress), broad strategy/blunder/agents.
4. Promote the target; update the findings doc.

## Conflicts with other seams

Touches `doctrine_fetch.py`'s **whether-to-play** section — seam C (tutor-chain) edits the **grab**
section of the same file; coordinate merge order (textual conflicts only). Do not run alongside the
discard convergence (seam D). Corpus-file edit on promotion.
