---
source: youtube
handle: learnthetcg
title: Learn the TCG — Fundamentals (playlist)
author_display: MellowMagikarp
url: https://www.youtube.com/watch?v=w_L0uLKFcSY
source_id: learnthetcg-fundamentals (curated series — no single playlist covers all 6; per-episode ids below)
kind: series
body_kind: transcript
date: 2025-03
vintage: sv-era
language: en
access: complete
ingested: 2026-07-09
covers: The strategic layer above sequencing — win-condition ID, the prize trade & prize mapping, KO-target selection, discard/thinning, and how to plan a single turn.
episodes:
  - n: 1
    title: identifying win conditions
    id: w_L0uLKFcSY
    date: 2025-03-04
    access: complete
  - n: 2
    title: how to decide what to KO
    id: d6BSd1eg2VQ
    date: 2025-03-09
    access: complete
  - n: 3
    title: Learn what to discard
    id: yK8e09nSNGQ
    date: 2025-05-05
    access: complete
  - n: 4
    title: the best players think about this every game (prize trade & mapping)
    id: muajLFMUO5A
    date: 2025-06-03
    access: complete
  - n: 5
    title: How to plan a turn
    id: 6VVehtADyAU
    date: 2025-06-11
    access: complete
  - n: 6
    title: 5 and a half tips to improve at pokemon
    id: owUa7ohI7R0
    date: 2025-07-21
    access: complete
---

# Strategy Digest — Learn the TCG: Fundamentals (series)

> ℹ️ **Vintage: SV-era (Mar–Jul 2025, ~Regulation H/I).** Not a dead format, but the **card, deck and
> matchup examples are real Pokémon TCG** (Gardevoir, Dragapult–Dusknoir, Charizard, Archaludon, Flareon,
> Roaring Moon, Raging Bolt, Gholdengo; Iono, Boss's Orders, Counter Catcher, Ultra Ball, Fezandipiti,
> Buddy-Buddy Poffin, Brier, Durant/Dnorr, Iron Hands, Dialga, …) that are **not necessarily in the
> competition's Mega-era simulator pool.** The *principles* below are format-independent and transfer;
> the card/deck names are the author's **illustrations** only — verify any against `data/EN_Card_Data.csv`
> before acting, and never promote one to an `opponent`/`our-deck` entry.

> English distillation of an external human-authored source. Not a transcript reproduction. Card claims
> are the author's; the engine + `data/EN_Card_Data.csv` remain ground truth (the downstream grill
> verifies before shipping). Series Digest — each claim is tagged with its episode + cite, e.g. `[E4 4:14]`.

**Same author as [`mellowmagikarp_sequencing_strategy.md`](mellowmagikarp_sequencing_strategy.md)** ("the
sequencing video" this series repeatedly points back to). That digest owns the *intra-turn ordering*
layer (Turn Planner / Lethal); **this series owns the layer above it** — deciding the turn's *goal*
(win-condition, prize trade, which KO). Where the two touch (turn planning, thinning) the entries below
cross-reference rather than duplicate.

**Routing note (important):** almost everything here is `general`, and most of it lands in the **Match
Planner / Turn Planner / prize-path (code) layer, not new `when()` weights** — win-condition evaluation,
prize mapping and turn-goal selection are the Planners' domain (ADR-0040/0045). A handful are genuinely
net-new general hypotheses (supporter-conservation; own-setup-before-disruption) or point at *unbuilt*
opponent-side infra (opponent rebuild-odds / resource model → "needs a new signal"). Treat Candidate
Signals as pointers, never weights.

## Agent-Doctrine

Convertible to a Pilot Hypothesis / Planner change / Brief — the grill's input. Each entry:
**scope** · **target home** · claim (why it wins) · *candidate signal*.

### general

- **[general → Match Planner / prize-path (code)]** **Ahead/behind is measured in *attacks-to-win*, not
  prize count.** Every turn, compute how many attacks each player still needs to win; the player needing
  fewer is ahead in the prize trade even if behind on prizes taken. A board of all one-prizers vs all
  two-prizers can win the race down 6→4. Re-evaluate *every* turn — the sooner you notice you're behind,
  the more turns you have to find your out. `[E1 0:59]` `[E4 2:32]` `[E4 3:04]` *Candidate signal:* Match
  Planner **Threat Clock** (turns-until-KO, ADR-0045) + **prize-path / KO-race** (ADR-0040) — likely
  already covered; confirm the clock, don't add a weight.

- **[general → Match Planner mode + gamble (code) / a play-safe-when-ahead hypothesis]** **Risk scales
  with prize position.** When **ahead**: minimise whiff — stabilise the board (extra support Pokémon /
  backup attacker), thin dead cards, and identify + play around the opponent's *only* comeback line ("what
  would I not want to draw off an Iono? get rid of it"). When **behind**: take the low-percentage line — the
  gate is *"do I just lose anyway?"* If the safe play also loses, go all-in on the 1% line; never assume the
  opponent sees the winning play — make them prove it. `[E1 1:15]` `[E1 8:27]` `[E4 7:18]` `[E5 4:33]`
  *Candidate signal:* `score_diff` / prize-lead board condition; the **gamble tier** (ADR-0039) already
  models "safe line loses → take variance." Cross-ref [[forgo-ko-corrections-are-refuted]].

- **[general → opponent-choice reads / KO-race (code)]** **Pick the KO that maximises the opponent's whiff
  odds.** When behind you need them to miss (boss / attack / KO); choose the target that leaves them
  needing the most *specific* cards. Count the cards they'll actually see vs the cards they must find —
  KO the **engine/developer** (e.g. their Fezandipiti draw-support) vs the **attacker** based on which
  forces more pieces, and consult their **discard** for what they can still rebuild. `[E2 0:23]`
  `[E2 2:14]` `[E2 3:44]` `[E2 4:25]` *Candidate signal:* **needs a new signal** — an opponent
  *rebuild-odds* estimate (their outs to a fresh attacker); pairs with Deck-Content-Odds applied to the
  opponent and the KO-Race read (blunder correction #30). Cross-ref [[snipe-threat-two-signals]].

- **[general → hand-disruption timing / Read]** **Disrupt a *tailored* hand; don't hoard your own Iono.**
  Iono/hand-disruption is most valuable when the opponent has whittled a big hand down to a few key cards —
  especially right after they Ultra-Ball'd away cards they'd normally keep (they've committed to those few).
  Conversely, don't *hold* your own Iono hoping they brick unless (a) it's a near-unwinnable matchup whose
  only line is their brick, or (b) your hand already fully sets up and plans next turn. `[E2 1:10]`
  `[E6 0:14]` `[E1 4:51]` *Candidate signal:* opponent **hand-size delta + last-turn action** (needs a new
  signal); the **Shuffle-Refresh** hand-quality gate (ADR-0024) for the "play it unless hand is complete"
  side. Cross-ref [[shuffle-refresh-doctrine]].

- **[general → prize-value board shaping (code)]** **Shape the board around prize *values*, two ways.**
  (a) **Odd-prizing / the seven-prize game:** put a single-prize attacker in play so the opponent must
  take seven prizes' worth of KOs to win — an extra attack, and it forces them down to a *single* prize
  (half an Iono; a one-card hand can't Ultra Ball). (b) **Present a single-prize board at the endgame:**
  when the opponent is at two prizes, clear your multi-prize liabilities off the board so they *cannot* take
  their last two, and you win next turn. `[E4 4:06]` `[E4 5:26]` `[E4 5:51]` *Candidate signal:* `prize`
  CardStat (prize value) + board composition; ties to [[interpose-cheap-attacker-promote]] and
  [[promote-after-ko-priority]].

- **[general → Match Planner forgo-KO seam (code)]** **Deny prizes/draw by taking *fewer* KOs.** Decks
  that place damage flexibly (spread / non-OHKO) can deliberately take a **single**-prize turn (so the
  opponent doesn't fall to a prize count that turns on their Counter Catcher) or take **no** KO at all (so
  they don't draw off their own Fezandipiti). Trading a KO now for denied resources later can win the race.
  `[E5 11:58]` `[E5 12:13]` `[E4 10:43]` *Candidate signal:* the Match Planner **forgo-KO seam** (ADR-0045,
  default ON) gated by `score_diff`. **Guard:** must never override a lethal or a losing KO-race — see
  [[forgo-ko-corrections-are-refuted]] / [[attack-is-turn-ender-develop-first]].

- **[general → discard keep-floors hypothesis]** **Discard triage = three buckets + rank-the-rest.** Sort
  the hand into (a) **easy discards** — cards you *want* in the discard, tech for other matchups, and
  diminishing-returns cards (Poffin in the mid/late game); (b) **never discard** — your *last* gusting
  effect (Boss / Counter Catcher), your *last* recovery (Super Rod / Night Stretcher), live matchup tech;
  (c) **need this turn** — found by mentally playing the turn out first. Then rank the leftovers
  least→most important and cut from the bottom. `[E3 0:44]` `[E3 1:18]` `[E3 6:30]` *Candidate signal:* the
  `discard_eot` **keep-floors** rule (already partly built — see [[general-gaps-authored-2026-07-04]]);
  add the "rank remaining, cut lowest" tiebreak. Cross-ref [[ignition-energy-discipline]].

- **[general → deck-thinning valuation / discard sequencing]** **Thin by *playing* dead cards, not
  discarding live ones.** Play Poffin / Nest Ball *out of hand* and spend the Ultra Ball's discard on
  genuinely dead cards instead; don't reflexively discard Ultra Ball with Ultra Ball. Goal: burn the most
  cards from the deck **without** discarding a win-piece — thinning raises the odds you draw what you need.
  `[E3 8:33]` `[E3 10:35]` `[E6 1:53]` *Candidate signal:* a deck-thinning value term on discard-cost cards
  (order the discards: dead-in-hand > playable-from-hand); sibling to `dont-waste-discard-energy`. Cross-ref
  [[ignition-energy-discipline]], [[turbo-flare-recipient-first]].

- **[general → supporter-conservation hypothesis (NET-NEW)]** **Don't spend a draw supporter you don't
  need.** Playing a supporter isn't mandatory just because it's in hand. If the hand already accomplishes
  the turn's goal and there's no dig / disruption / thinning value in drawing, **hold** it — most often the
  card to save is the Boss's Orders (or a new-evolution supporter) for a later, decisive turn. `[E6 2:43]`
  `[E5 5:37]` *Candidate signal:* **needs a new signal** — a "turn-goal-already-satisfied" predicate over
  the Turn Planner's directed goal + hand completeness; the payoff is preserving a scarce future resource,
  not tempo now.

- **[general → Turn Planner directed goal (code)]** **Frame each turn as best-possible vs bare-minimum,
  then take the cheapest line that meets the goal.** Define both the ideal turn *and* the bare minimum the
  prize map requires; ask "does the conservative / bare-minimum play accomplish the same thing while saving
  resources that are more useful later?" — and only spend the extra cards if those saved cards genuinely
  won't matter (in which case playing them *is* thinning). This is the anti-tunnel-vision discipline.
  **Subpar-attack test:** if you whiff the intended attacker, only use a fallback attack if it *reduces
  attacks-to-win* or *makes a future turn easier*; otherwise retreat to a one-prizer / draw / pass instead
  of attacking for its own sake. `[E5 2:38]` `[E5 3:45]` `[E5 7:28]` *Candidate signal:* Turn Planner
  **directed goal** (ADR-0045 Game Plan) + Threat-Clock delta on the fallback attack. Cross-ref
  [[attack-is-turn-ender-develop-first]], and the sequencing digest's *plan-the-turn* entry.

- **[general → deck-knowledge: deck-tracker + Deck-Content-Odds (code)]** **Exploit known deck contents on
  both sides.** Track the cards you send to the *bottom* with Iono and your thinned late-game deck — you can
  often know your bottom ~10 — and sequence shuffle vs no-shuffle to *guarantee* an out (e.g. draw down to a
  two-card deck so the last Counter Catcher is certain; note that "thinning" that could shuffle away your
  guaranteed out is not thinning). Track the **opponent's** discard and resource counts every game so
  endgame deck-out / play-around-their-last-copy lines are exact. `[E5 22:38]` `[E6 3:34]` `[E1 7:17]`
  `[E4 8:36]` *Candidate signal:* own side — `deck_tracker.py` / `deck_odds.py` (built; see
  [[sound-deck-emptiness-oracle]], [[deck-content-odds]]). Opponent side — **needs a new signal** (an
  opponent discard/resource + prized-count model).

### opponent

- **(none.)** Every foreign deck named (Gardevoir, Dragapult–Dusknoir, Charizard, Archaludon, Flareon,
  Roaring Moon, Raging Bolt, Gholdengo, Iron Thorns, …) is a **real-TCG illustration**, not one of our
  tracked simulator Archetypes — **no tracked Archetype match**. Per synthesis Step 0 these stay
  illustrations (Out-of-Scope), not `opponent:` entries.

### our-deck

- **[our-deck:<any> → src/agents/<deck>/STRATEGY.md — realised per deck]** **Match your reactivity to the
  deck you pilot.** Linear/aggressive decks (the video's Roaring Moon, Gholdengo) should play "solitaire" —
  prioritise your own setup and don't over-play-around the opponent; disruptive / flexible-damage decks
  (Gardevoir, Dragapult) should filter each decision through the opponent's *next* turn (take a single
  prize to deny Counter Catcher, forgo a KO to deny draw). `[E5 10:51]` `[E5 11:47]` *Candidate signal:*
  each agent's **Role / deck-intent** (STRATEGY.md) sets a "solitaire vs opponent-filtered" default; the
  opponent-filtered branch consumes the believed archetype (Read). Our aggressive builds (`mega_lucario`,
  `mega_starmie`) lean solitaire; a spread build (`dragapult_ex`) leans opponent-filtered.

## Process

Informs OUR training / gauntlet / self-play workflow — not the Pilot. One line each.

- **Grind volume to learn a deck's lines** — play many games on the ladder to internalise a deck. ≈ our
  **self-play corpus / ladder** loop. `[E6 4:29]`
- **Play your hard matchups from the *other* side** to learn what that deck fears and which Pokémon it
  protects — directly feeds better KO-target selection. ≈ our **non-mirror gauntlet** + `/matchup-genie`
  research. `[E1 6:11]` `[E6 6:08]` Cross-ref [[value-model-needs-nonmirror-gauntlet]].
- **Study strong players' discard / Ultra-Ball choices**, predict the pick, and reason about differences.
  ≈ our **blunder-inspector review lens** (note: ADR-0002 discards ladder *film* for value-model training;
  this is a review-lens analogue, not a training source). `[E3 12:04]`
- **Replay from a key decision and take the *other* line** to see what happens. ≈ our **materialized-replay
  veto / blunder retest**. `[E6 9:03]` Cross-ref [[lethal-solver-plan]].
- **Review every loss for the direct cause; treat "variance" as usually a misplay** — most unlucky-feeling
  losses have a findable mistake. ≈ our **blunder-correction loop** (ADR-0018). `[E6 8:03]` `[E1 18:12]`
- **Know the exact counts in common meta decks** so endgame deck-out and play-around-the-last-copy lines
  are precise. ≈ meta-DB counts / `deck_tracker` priors. `[E1 7:32]`

## Out-of-Scope

Human-improvement advice with no repo home, plus real-TCG illustrations. Captured to prove the source was
fully mined. Non-actionable.

- Real-TCG SV card / deck examples used only to illustrate the principles (full list in the vintage banner)
  · *(illustrations; verify vs competition pool before use, never promote to opponent/our-deck)*.
- Worked replay walkthroughs — EUIC top-4 Dragapult-Durant vs Archaludon `[E1 10:44]` `[E2 5:22]`,
  regional Charizard vs Reggie-Drago `[E4 15:31]`, Gardevoir vs Flareon `[E5 12:29]` — examples of the
  principles, not portable doctrine · *non-actionable*.
- The mental game: nerves, staying present in the current round (not scoreboard-watching), never assuming a
  game is lost before it starts, and being honest about your skill / deck comfort · *non-actionable
  (human)*. (The "never assume lost / always find a win path" attitude is already captured as doctrine via
  the gamble/comeback entry above.)
- Meta observation that the current format is ~60/40 at worst / "any matchup is winnable" — real-TCG meta
  commentary; a mindset, not an agent rule · *non-actionable*.
- "These prize-trade manipulator cards (Brier / Durant / Iron Hands / Dialga) will probably rotate" —
  real-TCG format commentary · *(illustrations)*.

---

<!-- Buckets fully triaged. Provenance complete. Series of 6, all episodes access: complete. -->
