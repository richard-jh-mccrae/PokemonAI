---
source: youtube
handle: MellowMagikarp
title: the single most important skill
url: https://www.youtube.com/watch?v=Jru0f1x7E14
source_id: Jru0f1x7E14
kind: single
body_kind: transcript
date: 2025-02
vintage: sv-era
language: en
access: complete
ingested: 2026-07-08
covers: Sequencing — the order you take turn actions to maximise the odds of your desired outcome.
---

# Strategy Digest — the single most important skill (Sequencing)

> ℹ️ **Vintage: SV-era (Feb 2025, ~Regulation G/H).** Not a dead format, but its **card examples are real
> Pokémon TCG** cards (Fezandipiti, Arven, Iono, Poké Gear, Maridon/Electric Generator, Raging Bolt,
> Palkia VSTAR, Pidgeot ex, …) that are **not necessarily in the competition's Mega-era simulator pool**.
> The *principles* below are format-independent and transfer directly; the card names are the author's
> **illustrations** only — verify any against `data/EN_Card_Data.csv` before acting, never promote one to
> an opponent/our-deck entry.

> English distillation of an external human-authored source. Not a transcript reproduction. Card claims
> are the author's; the engine + `data/EN_Card_Data.csv` remain ground truth. Cite anchors `[m:ss]` are
> from the source video.

**Routing note (important):** nearly all Agent-Doctrine here is `general` and lands in the **Turn Planner
/ Lethal Solver layer (code), not new `when()` weights** — sequencing *is* the Planner's job (action
ordering within a turn). A few points sharpen existing hypotheses (`attach-energy-last`, the
Shuffle-Refresh and Deck-Content-Odds doctrines). Treat Candidate Signals as pointers into those systems.

## Agent-Doctrine

### general

- **[general → Turn Planner]** Sequencing = the *order* you take turn actions (play from hand, use
  abilities, use in-play cards like stadiums) chosen to **maximise P(desired outcome)** — usually
  P(drawing one or more specific cards). The same 5-card hand can be right or wrong purely by order. `[0:00]`
  *Candidate signal:* this is the Turn Planner's whole domain (`plan_turn`, ADR-0031/0037) — the leaf
  ordering of a turn's actions; not a weight.

- **[general → Turn Planner / Match Planner]** **Have a plan for the turn before acting.** Mindless
  card-playing sharply raises misplay odds; the plan's best goal shifts by game stage (early = set up /
  find Basics). `[2:41]` `[3:00]` *Candidate signal:* the Match/Turn Planner's directed goal
  (ADR-0045 Game Plan) — plan first, then order actions toward it.

- **[general → `attach-energy-last` + a retreat-timing rule]** **Leave options open: defer the
  committing actions.** Don't attach energy early or retreat early "for no real benefit" — save both for
  late in the turn so draws can still redirect them. `[1:43]` `[1:56]` *Candidate signal:* existing
  `attach-energy-last` hypothesis; a sibling **"don't retreat early"** sequencing rule (Turn Planner).

- **[general → Turn Planner exceptions]** **Known exceptions to defer-committing-actions:** (a) retreat
  *before* evolving into a higher-retreat-cost Pokémon; (b) attach energy *early* to lower the hand for a
  "draw-up-to" effect, or *before* a hand-shuffling supporter (Iono). `[2:12]` `[2:20]` *Candidate signal:*
  Turn Planner ordering constraints; ties to the hand-size condition before a draw-up-to.

- **[general → Deck-Content-Odds / search sequencing]** **Thinning:** remove non-target cards from the
  deck to raise P(drawing the target); and its inverse — sometimes *leave* Basics in the deck so a
  shuffle-draw (Iono) can hit them. Always ask "do I have a way to thin toward what I need?" `[3:09]`
  `[3:57]` `[4:57]` *Candidate signal:* Deck-Content-Odds (ADR-0029, `deck_odds.py`/`deck_tracker.py`),
  `dont-search-an-empty-deck` / `dont-tutor-the-held-wincon`.

- **[general → Turn Planner / Shuffle-Refresh]** **Draw-that-adds before guaranteed search.** Play
  "draw cards on top of hand" abilities — and especially **"draw up to N" (Iono/Professor's Research)
  after emptying the hand** — *before* committing a tutor, so you don't remove your own outs by fetching a
  piece you could have drawn. `[6:52]` `[7:16]` `[7:23]` *Candidate signal:* Turn Planner draw/search
  ordering; Shuffle-Refresh doctrine (ADR-0024, hand→deck→draw).

- **[general → Lethal Solver / one-out recognition]** **Guaranteed vs random ordering flips on outs.**
  Usually keep options open (do the random/search-y thing last); **but when you have exactly one line to
  win, do the guaranteed effect first and go all-in.** For a 2-piece combo, order to preserve the most
  outs (use the flexible draw before the committing tutor). `[6:37]` `[7:27]` *Candidate signal:* Lethal
  Solver (ADR-0030) — one-out / must-line detection changes the ordering rule.

- **[general → Deck-Content-Odds / Lethal]** **Count your outs.** Quantify how many cards in the deck
  complete your line and don't shrink that count by tutoring a piece you could have drawn (his example:
  6→4 outs = losing a third). `[8:01]` *Candidate signal:* `deck_odds.py` out-counting; Lethal Solver.

- **[general → Turn Planner]** **"Look at top X then shuffle" cards (Poké Gear / Great Ball): use draw
  effects *before* them** (Fez-then-PokéGear ≈ seeing 10 cards); and use "see top N" thinners (Trekking
  Shoes) before them for extra depth. Reverse only when the thing you seek isn't what that card finds.
  `[8:47]` `[9:29]` `[10:03]` *Candidate signal:* Turn Planner draw/dig ordering.

- **[general → disruption-aware sequencing + Scouting Read]** **Hold a dig/supporter-search for next
  turn** (you top-deck a card and see one more), **except** play it end-of-turn when you expect item-lock
  or hand-disruption from the opponent. `[10:17]` `[10:46]` *Candidate signal:* opponent-conditioned
  ordering — ties to the Scouting Read/posture (item-lock / hand-disruption archetype); the "if X play at
  EOT" branch is a matchup-gated Turn-Planner tweak, not a flat weight.

- **[general (low priority) → conceal-information]** **Don't broadcast your answer:** avoid tutoring your
  one perfect card as the last visible action before attacking (Pidgeot) — it invites disruption. Keep
  concealment from harming the higher-priority goals. `[1:27]` `[1:31]` *Candidate signal:* low value vs an
  agent opponent; a weak Turn-Planner tiebreak at most — see Out-of-Scope.

## Process

- **Sequencing reduces variance — "makes your own luck."** Frame apparent bad luck as "did I misplay / did
  they play well?" A useful evaluation lens for our blunder-inspector: many "variance" losses are
  sequencing misplays. `[15:51]` `[16:04]`
- **Content-longevity discipline** (author's, not ours): he avoids soon-to-rotate cards as examples. For
  our Digests, the analogue is the vintage/card-pool caveat above.

## Out-of-Scope

- Real-TCG SV card examples used only to illustrate the principles (Fezandipiti, Arven, Iono, Poké Gear,
  Great Ball, Trekking Shoes, Maridon + Electric Generator, Raichu, Greninja, Palkia VSTAR, Raging Bolt,
  Teal Mask Ogerpon, Dusknoir/Dusclops, Rare Candy, Super Rod, Nest Ball, Ultra Ball, Pal Pad, Night
  Stretcher) · *(illustrations; verify vs competition pool before use)*.
- Caleb Gomber's regional top-4 replay walkthrough — a worked example of the principles, not portable
  doctrine · *non-actionable*.
- Concealing information / "mind games" vs a *human* reading your tempo and hand — the competition
  opponent is another agent, so bluff-value is marginal · *non-actionable (agent context)*.

---

<!-- Buckets fully triaged. Provenance complete. -->

