# Seam handoff: held-card risk (fetch-early vs fetch-late — disruption exposure)

**Parallel-session slot B.**
**Status: ✅ BUILT 2026-07-19, suite-green — target 85163634-17 promoted TARGET → PIN.**

## Build findings (settling the three open questions below at source)

1. **WHERE the term lands:** a new stand-down Hypothesis, `dont-fetch-before-the-deadline` (−60,
   `doctrine_fetch.py` whether-to-play), sized to cancel the whole endorsement stack (confirmed-hit
   15 + need 8 + wincon-tutor 25 + junk-shed 12 — the `dont-tutor-the-baseless-wincon-turn-one`
   idiom). The currency-zone rule is honored by MUTUAL EXCLUSION: its `when` excludes the
   starved-and-developed board that `dont-costly-tutor-when-starved-and-developed` (−30) already
   prices — one rung per jurisdiction, never both (verified by
   `test_deadline_rung_leaves_the_starved_and_developed_board_to_its_own_rung`).
2. **The DEADLINE predicate** had to be two-sided: *unplayable this turn* alone regressed three
   `test_fetch_doctrine` whether-to-play pins whose synthetic wincon has NO base anywhere — a
   baseless payoff has no deadline, so "wait" prices nothing. The shipped predicate
   (`Context.fetch_target_deferred`) is **unplayable this turn AND provably playable NEXT turn**
   (base-named body already in play — `appearThisTurn`/own-first-turn bans lapse, rules.md §4
   verified at rulebook L123-128 — or a held base benchable now). Exactly the doc's "the wincon is
   wanted next turn, not this one". No quota gate was built.
3. **What the Read exposes — verified at source, and it reshaped the form:** on the ep85163634
   board the matched Read (conf 0.878, Latias/Mega Kangaskhan/Meowth) exposes **zero**
   Judge/Harlequin — and the opponent's actual deck confirms it (no hand-strip cards at all). So a
   Read-gated veto alone can NEVER flip this target; the load-bearing leg is the deadline (benefit
   this turn = 0) plus the `cost_discard` price paid a turn early. The Read enters as the WIDENER:
   `Board.opp_hand_strip_odds` (max `copies_left_odds` over the rep build's `hand_disruption` cards
   — Judge/Harlequin/Unfair Stamp, tags verified) lets a FREE fetch defer too when ≥ 0.5; fail-open
   0.0 (no rep → no exposure → no veto), and a strip card in their HAND under-counts — the safe
   suppressor direction.
4. **A second leg the brief's RED plan missed:** with Ultra Ball stood down, the next pick was NOT
   the +266.9 attack but the Lillie's refresh (+11.7, tier 3) — which shuffles away the very Ultra
   Ball the deferred plan needs: the fetch-LATE re-access risk, self-inflicted.
   `dont-shuffle-away-the-deferred-fetch` (−20, cancels the flat CYCLE credit) reads the same
   deadline predicate from the hand (`Context.refresh_shuffles_deferred_fetch`); a genuinely
   stripping Judge still clears it on its strip credits. Kept OUT of the keep-cost currency on the
   `hold-successor-when-doomed` precedent (a deadline premise the closure doesn't model).

Tests: `tests/strategy/test_held_card_risk.py` (fixture replay chosen==[5] + both rungs' bands,
strip-read fail-open, first-turn evolution ban, currency-zone exclusion). Corpus: 40 passed
(all six hold-the-fetch pins hold), 3 remaining targets still xfail.
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
