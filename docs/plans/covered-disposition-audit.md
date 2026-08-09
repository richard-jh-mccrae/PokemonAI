# Covered-disposition audit — the worklist

> **GENERATED — do not hand-edit.** `python tools/train/reviewed_audit.py --emit-report`.
> Issue #238, ADR-0114 decision 4. Regenerate after any ledger or rung change.

A `reviewed.json` closure is a claim about the shipped agent. When the rule it names is
deleted the claim expires silently, because the ledger stores its justification as opaque
prose. Every row below is an entry whose justification names a rung that **no longer
exists**. A row is *not* a finding that the frame is misplayed — it is a finding that the
**stated reason for closing it is gone**, so the closure has never been re-examined.

## How to use this

Open the frame — `python tools/train/frame_view.py <ledger key>` — and rule it on its own
merits, independent of the vanished rung (Issue #238 items 1-3, which are a human ruling and
are deliberately NOT automated). Then either re-close it against a rule that exists
(`python tools/train/review_correction.py <key> covered "<why>"`) or route it through the
current taxonomy. Once it stops being flagged, delete its line from
`data/corrections/reviewed_audit_allowlist.json`. The *what it became* column is there to
make that ruling cheap: it is the fold map's own statement of what replaced the rung.

## Tally

* ledger entries: **133**
* entries naming a retired rung: **27**
* by disposition: `covered` **21**, `fixed` **2**, `refuted` **4**
* live rung vocabulary: **16** `Hypothesis(id=…)` in `src/` (+ **17** `SoundRule(id=…)`)
* retired rung vocabulary: **175**
* distinct rungs implicated: **11**
* tokens that resolved to NO rung (the vocabulary's blind spot): **173** distinct, **262** occurrences. Top: `attack-last` ×27, `w-route` ×8, `buddy-buddy` ×6, `end-of-turn` ×6, `forgo-ko` ×5, `bench-fill` ×4, `first-dev-differs` ×3, `tier-4` ×3

The blind-spot count is reported rather than suppressed. The most frequent unresolved token
is `attack-last`, which is not a rung at all — it is the Pilot's structural resequencing
(`_finish_turn_last`). A loose `[a-z-]+` scan would have flagged every note that mentions it.

## `covered` — 21 entries

| ledger key | disposition | dead rung(s) | what it became | live rule(s) still named | the note, verbatim |
|---|---|---|---|---|---|
| `82228017-4` | covered | `dig-before-commit` `dont-tutor-the-held-wincon` | `dig-before-commit` → common.composer:compose — a beam over within-turn sequences scores the dig's successor states by construction<br>`dont-tutor-the-held-wincon` → common.composer:compose — shared valuation retired globally | — | Resolved by dont-tutor-the-held-wincon: Mega Signal is a wincon-only tutor (fetch-filter tutor_mega -> {Mega Starmie ex} = the deck's lone Mega ex), so with a Mega already in hand Context.search_redundant_wincon fires (-45), cancelling dig-before-commit; real Pilot retest chosen [0]->[1]=correct (attach). Sound: reads the new fetch-filter machinery on the sound deck-knowledge oracle. |
| `82227388-22` | covered | `dig-before-commit` | `dig-before-commit` → common.composer:compose — a beam over within-turn sequences scores the dig's successor states by construction | — | attack-last: agent develops before attacking; digs before attaching (dig-before-commit reveals a better target) |
| `82228640-7` | covered | `dig-before-commit` | `dig-before-commit` → common.composer:compose — a beam over within-turn sequences scores the dig's successor states by construction | — | Frame fixed by the cost_discard slice: Ultra Ball pays 2 cards to play, so dig-before-commit no longer grants it a free-dig bonus and _finish_turn_last tiers a discard-cost search as a commitment — Ultra Ball drops to score 0 / tier 2, the free Energy attach (needed Staryu) wins. Real Pilot retest chosen [1]->[0]=correct (attach). NOTE the deeper intent (Hilda DOMINATES Ultra Ball: finds Mega+energy; don't burn Hilda to the discard) is a dominated-action / hand-quality judgment still deferred to the value model — but the frame's blunder (Ultra Ball over the free attach) is resolved. |
| `81904064-59` | covered | `dig-before-commit` | `dig-before-commit` → common.composer:compose — a beam over within-turn sequences scores the dig's successor states by construction | — | attack-last defers the KO; real Pilot digs first; Salvatore endorsed (dig-before-commit), played same turn before the KO |
| `81904064-44` | covered | `dig-before-commit` | `dig-before-commit` → common.composer:compose — a beam over within-turn sequences scores the dig's successor states by construction | — | attack-last: real Pilot plays Lillie's Determination first (dig-before-commit), attack deferred — retest [2]->[0]=correct |
| `81904064-49` | covered | `dig-before-commit` | `dig-before-commit` → common.composer:compose — a beam over within-turn sequences scores the dig's successor states by construction | — | attack-last: real Pilot plays Pokegear 3.0 first (dig-before-commit) — retest [2]->[0]=correct |
| `82225138-82` | covered | `prefer-bench-fill-first` | `prefer-bench-fill-first` → common.composer:compose — shared valuation retired globally | — | attack-last: real Pilot plays Buddy-Buddy Poffin first (prefer-bench-fill-first) — retest [6]->[0]=correct |
| `82225643-11` | covered | `dig-before-commit` | `dig-before-commit` → common.composer:compose — a beam over within-turn sequences scores the dig's successor states by construction | — | attack-last: real Pilot plays Pokegear first (dig-before-commit) over the Ignition attach — retest [1]->[0]=correct |
| `82225643-34` | covered | `dig-before-commit` | `dig-before-commit` → common.composer:compose — a beam over within-turn sequences scores the dig's successor states by construction | — | attack-last: real Pilot plays Pokegear first (dig-before-commit) — retest [5]->[0]=correct |
| `82750161-16` | covered | `dont-tutor-the-held-wincon` | `dont-tutor-the-held-wincon` → common.composer:compose — shared valuation retired globally | — | dont-tutor-the-held-wincon suppresses Mega Signal (-17): a Mega is already in hand, so it would dig a redundant wincon; agent plays the broader Hilda tutor |
| `82866415-48` | covered | `deploy-hp-tool` | `deploy-hp-tool` → common.composer:compose — deleted with the Tool doctrine's MAIN-phase half | — | deploy-hp-tool's survival-turns picker targets the benched Staryu (the human's exact label); _finish_turn_last sequences the Cape attach before the attack — retest [6]->[3]=correct. W-route unsatisfiable only because the attack's tactical (209.7) dominates the +40 positional deploy (attack-last) |
| `83054602-32` | covered | `dont-waste-clutch-heal` | `dont-waste-clutch-heal` → common.composer:compose — a heal is priced by the survival delta it buys | — | dont-waste-clutch-heal suppresses Wally's-after-attach to -40 (energyAttached already True); the real Pilot ATTACKS [1] instead of the blunder [0] Wally's — strictly better than the human's End [3]. Blunder (bounce all energy, lose initiative) avoided; first-dev-differs. |
| `83117367-34` | covered | `dont-tutor-the-held-wincon` | `dont-tutor-the-held-wincon` → common.composer:compose — shared valuation retired globally | `dont-search-an-empty-deck` | The CRITICAL intent (Salvatore is a waste) is satisfied: dont-search-an-empty-deck (-60) + dont-tutor-the-held-wincon (-45) sink Salvatore to -85, real Pilot plays a develop (Lillie's [0]) instead, never Salvatore. Harlequin-vs-Lillie's is a supporter-priority value judgment (the human's own preference reverses in slow-setup-83116081-17); not the blunder. |
| `83666442-27` | covered | `recover-to-refill-bench` | `recover-to-refill-bench` → common.composer:compose — shared valuation retired globally | — | recover-to-refill-bench (Night Stretcher +22) AND Lillie's both play this turn (Main re-presents): the human wanted the refresh AND 'a bench for backup'; the empty bench refills first, the refresh follows. First-dev-differs. |
| `83667237-87` | covered | `recover-to-refill-bench` | `recover-to-refill-bench` → common.composer:compose — shared valuation retired globally | — | recover-to-refill-bench: real Pilot plays Night Stretcher to refill the EMPTY bench BEFORE the Jetting Blow KO (retest [4]->[2]); _finish_turn_last tiers tier-0 recover before the tier-4 KO. W-route-blind (KO outscores +22). |
| `83667237-120` | covered | `recover-to-refill-bench` | `recover-to-refill-bench` → common.composer:compose — shared valuation retired globally | — | recover-to-refill-bench (doctrine_fetch.py) endorses Night Stretcher +22 -> real Pilot chosen_after=[3] Night Stretcher, FIXED=True; live_trace was pre-fix build |
| `83966968-45` | covered | `dig-before-commit` | `dig-before-commit` → common.composer:compose — a beam over within-turn sequences scores the dig's successor states by construction | — | attack-last defers the non-lethal Nebula Beam (238<KO); real Pilot plays Harlequin (dig-before-commit +20) first = human's disrupt intent. retest chosen [6]->[2]=Harlequin, FIXED=True |
| `84897262-100` | covered | `dig-before-commit` | `dig-before-commit` → common.composer:compose — a beam over within-turn sequences scores the dig's successor states by construction | — | attack-last defers the non-lethal Nebula Beam (154.7<KO); real Pilot plays Harlequin (dig-before-commit +20) first. retest chosen [5]->[0]=Harlequin, FIXED=True |
| `84071010-30` | covered | `dig-before-commit` `dont-refresh-into-a-probable-miss` | `dig-before-commit` → common.composer:compose — a beam over within-turn sequences scores the dig's successor states by construction<br>`dont-refresh-into-a-probable-miss` → common.composer:compose — shared valuation retired globally | — | CRITICAL 'single card (Lillie's), use it' — COVERED on the current real Pilot: decide()=[0]=Play Lillie's Determination (=correct). attack-last (_finish_turn_last) defers the 169.9 Aura Jab (tier-2, non-KO) via reordered=True, and Lillie's now scores +20 (dig-before-commit) since the old dont-refresh-into-a-probable-miss suppressor no longer fires on this dead 1-card hand. Confirmed via tune._build_pilot('mega_lucario').decide on the captured f30 state. |
| `85045840-8` | covered | `dig-before-commit` `use-the-draw-engine-ability` | `dig-before-commit` → common.composer:compose — a beam over within-turn sequences scores the dig's successor states by construction<br>`use-the-draw-engine-ability` → common.composer:compose — same claim as dig-before-commit: act informatively, then commit | — | degenerate: chosen==correct==Play Poké Pad; real Pilot decide()=[1]=Poké Pad (dig-before-commit sequences it first, reordered). The wider T1 engine plan (Drakloak Recon + Dudunsparce Run Away Draw) is covered by use-the-draw-engine-ability; the Ultra Ball discard-discipline is the f14 cluster. |
| `85058051-4` | covered | `hold-the-retreat-tool-with-no-retreat` | `hold-the-retreat-tool-with-no-retreat` → common.composer:compose — deleted with the Tool doctrine's MAIN-phase half | — | wasted_resource 'no plan to retreat solrock, waste (Air Balloon on Solrock)': the flagged waste is COVERED. retest_one: live chosen=[0] Attach Air Balloon->Solrock is demoted by hold-the-retreat-tool-with-no-retreat (-12) to score 8; real decide()=[2]=attach energy to arm Cosmic Beam (score 30) -- the 'attaching one energy to solrock was a good move' the human explicitly endorsed in the SAME rationale. Tagged correct=[1] Ultra Ball is a soft draw-engine card-economy preference the human relaxed; tune.py flags the correction contradictory (UNSATISFIED, 'not a weight'). No proposal. |

## `fixed` — 2 entries

| ledger key | disposition | dead rung(s) | what it became | live rule(s) still named | the note, verbatim |
|---|---|---|---|---|---|
| `85045840-10` | fixed | `dont-shed-a-live-card` | `dont-shed-a-live-card` → common.composer:compose — shared valuation retired globally | — | USER RULING 2026-08-02 (Issue #261 wave-2, items 2e+2h): ACCEPT the leaf flip. The SHIPPED DECISION on this frame is unchanged and already plays the human's option -- verified on the pre-change tree too, so the ruling is about the LEAF RANKING only, which moved OK -> MISS (rank 1 -> 2). Cause, located: item 2h re-pointed the fetch doctrine's shed predictor off the deleted _DISCARD ladder onto the keep-value v2 assignment, which prices the Ultra Ball's forced discard at 4.5 (its two cheapest sheds include the held Boss's Orders), so dont-shed-a-live-card fires and the greedy continuation INSIDE the sim declines the fetch. The human's line therefore develops less on the simmed end board (12.5 -> 0.0) while the Ultra-Ball-first line is unaffected (10.025) because _engine_leaf_value forces its first step and cannot decline anything. User's words on accepting: 'the decline agrees with that frame's own rationale' -- this frame's own correction says 'save boss's orders for a time when it is actually valuable', which is exactly what the new predictor refuses to spend. Non-voiding: the correction STANDS and keeps gating; the leaf baseline is re-captured against this ruling. |
| `85045840-12` | fixed | `dont-shed-a-live-card` | `dont-shed-a-live-card` → common.composer:compose — shared valuation retired globally | — | USER RULING 2026-08-02 (Issue #261 wave-2, items 2e+2h): ACCEPT the leaf flip. The SHIPPED DECISION on this frame is unchanged and already plays the human's option -- verified on the pre-change tree too, so the ruling is about the LEAF RANKING only, which moved OK -> MISS (rank 1 -> 2). Cause, located: item 2h re-pointed the fetch doctrine's shed predictor off the deleted _DISCARD ladder onto the keep-value v2 assignment, which prices the Ultra Ball's forced discard at 4.5 (its two cheapest sheds include the held Boss's Orders), so dont-shed-a-live-card fires and the greedy continuation INSIDE the sim declines the fetch. The human's line therefore develops less on the simmed end board (12.5 -> 0.0) while the Ultra-Ball-first line is unaffected (10.025) because _engine_leaf_value forces its first step and cannot decline anything. User's words on accepting: 'the decline agrees with that frame's own rationale' -- this frame's own correction says 'save boss's orders for a time when it is actually valuable', which is exactly what the new predictor refuses to spend. Non-voiding: the correction STANDS and keeps gating; the leaf baseline is re-captured against this ruling. |

## `refuted` — 4: flagged, but NOT blockers (ADR-0114 decision 6)

A refuted ruling owes no fix either way, so a dead rung in its refutation note costs
nothing operationally. They are listed because the refutation rests on the same
vanished premise, and Issue #238 asked for them to be re-read on that basis.

| ledger key | disposition | dead rung(s) | what it became | live rule(s) still named | the note, verbatim |
|---|---|---|---|---|---|
| `82224509-46` | refuted | `gust-for-the-ko` | `gust-for-the-ko` → UNREPLACED — hole is TOTAL: CLAUSE_WRITES['gust'] blocks _covers, so rung, tier and leaf are all silent | — | forgo-KO: agent takes an available KO of the current Active (attack-last develops then KOs, 1001.1). gust-for-the-ko correctly stands down — gusting+KOing the Riolu pre-evo yields the SAME 1 prize as the free attack KO, so spending Boss's Orders for an equal KO (plus 0.5 forward-denial) is strictly worse |
| `82525741-58` | refuted | `gust-for-the-ko` | `gust-for-the-ko` → UNREPLACED — hole is TOTAL: CLAUSE_WRITES['gust'] blocks _covers, so rung, tier and leaf are all silent | — | Chosen Boss's Orders reaches a guaranteed KO (gust-for-the-ko fires: gust_best_ko_prizes 1 > active_ko_prizes 0 — gust the 70HP Staryu, Jetting Blow KOs it for a prize). The correct (attach + chip the 190HP active, no KO) forgoes that KO for positional chip; a positional weight must never override a KO (forgo-ko principle, ADR). Chip-the-bigger-fish-vs-take-the-small-KO lookahead deferred to a separate task. |
| `82524455-6` | refuted | `prefer-bench-fill-first` | `prefer-bench-fill-first` → common.composer:compose — shared valuation retired globally | — | Requires deck-content certainty (no Staryu left in deck) not soundly derivable from one obs: only 1 of 3 Staryu is visible; the other 2 could sit in the 6 hidden prizes, so 'a 2nd Buddy-Buddy whiffs' is a probabilistic read, not a fact. Playing bench-fill turn 1 is sound doctrine (prefer-bench-fill-first). Proper deck-tracking feature spawned as a follow-up task. |
| `83662396-19` | refuted | `dont-tutor-the-held-wincon` | `dont-tutor-the-held-wincon` → common.composer:compose — shared valuation retired globally | — | forgo-KO: Turbo Flare is a KO (tac 1000.9, weakness) on the 70HP opp Active; Mega Signal is ALSO a redundant tutor (Mega already in hand -> dont-tutor-the-held-wincon). A thin-the-deck tutor never overrides a KO. |

## Reconciliation against Issue #238's own lists

Acceptance criterion 5. Every count below is derived from this run, not transcribed.

* **body, the 13** — flagged 0/13.
  Not flagged: `81903490-27`, `81903490-49`, `81904451-50`, `81904451-6`, `81905522-47`, `81906131-25`, `82524455-27`, `82750161-59`, `82752045-80`, `82752045-97`, `82756664-74`, `83007714-7`, `83116501-89`.
* **body, the 3 `refuted` re-reads** — flagged 0/3.
  Not flagged: `82525741-81`, `82867148-87`, `85058574-114`.
* **comment, the 14 (`<ep>|<seat>|decision|<frame>` → `<ep>-<frame>`)** — flagged 2/14.
  Not flagged: `82224509-29`, `82224509-40`, `82224509-71`, `82225643-57`, `82226116-70`, `82226759-64`, `82227388-30`, `82227388-43`, `82228640-25`, `82228640-48`, `82228640-53`, `82229122-33`.

The 12 unflagged entries from the comment's 14 are correct behaviour, not a miss —
**8 of 12** close on `attack-last`, which names no rung, live or dead. It is the
Pilot's structural resequencing, so *"the agent does the right thing, just in a different
order within the same turn"* is a different question (*is same-turn ordering a blunder at
all?*) — and the comment filing them says exactly that. Nothing about them expired; there
is no dead rule for them to have expired against.

Entries this audit surfaces that Issue #238 never named: **25**.

## Provenance

* rung vocabulary captured at `a2b649e58c1f`
* rungs deleted since that capture, folded in without git: `attach-before-hand-shuffle`, `attach-off-color-at-fixed-recipient`, `aurajab-load-the-wincon-line`, `aurajab-skip-partnerless-solrock`, `costly-fetch-sheds-junk`, `demote-needless-search-supporter-in-setup`, `demote-the-costly-chain-opener`, `develop-the-cheap-prize-wall-line`, `develop-the-item-lock-opener`, `dont-costly-tutor-when-starved-and-developed`, `dont-fetch-an-unplayable-evolution-payoff`, `dont-fetch-before-the-deadline`, `dont-fetch-the-setup-only-opener`, `dont-grab-a-baseless-mid-evolution`, `dont-grab-a-card-already-in-hand`, `dont-recycle-the-dead`, `dont-refresh-into-a-probable-miss`, `dont-rush-evolve-without-target`, `dont-search-a-probable-whiff`, `dont-shed-a-key-card`, `dont-shed-a-live-card`, `dont-shuffle-away-the-deferred-fetch`, `dont-spend-the-last-route-to-a-wanted-evolution`, `dont-strand-the-evolving-engine`, `dont-tutor-the-baseless-wincon-turn-one`, `dont-tutor-the-held-wincon`, `feed-the-line-for-disruptor-lock`, `fetch-a-starter`, `fetch-base-before-stranded-payoff`, `fetch-deck-priority`, `fetch-energy-when-starved`, `fetch-the-ability-fuel-color`, `fetch-the-attack-color`, `fetch-the-support`, `fetch-the-wincon`, `fetch-when-it-fills-a-need`, `grab-a-gust-supporter-for-the-ko`, `grab-the-chain-opener`, `grab-what-i-can-play-this-turn`, `gravity-mountain-vs-stage2`, `hold-costly-fetch-when-line-assembled`, `move-counters-off-the-damaged`, `move-max-counters`, `open-the-declared-starter`, `phase-close-stop-developing`, `phase-stabilize-prefer-heal`, `place-counter-to-convert`, `play-a-tutor-for-the-unfound-wincon`, `play-safe-when-ahead-on-prizes`, `prefer-active-attach-in-setup`, `prefer-bench-fill-first`, `prefer-payoff-over-preevo`, `prefer-rush-evolve-tutor`, `prefer-wincon-line-piece`, `recover-to-refill-bench`, `search-the-confirmed-hit`, `use-acceleration`
* positive control — the four decider sweeps' `RETIRED` lists: **45** names, every one present in the historical harvest

