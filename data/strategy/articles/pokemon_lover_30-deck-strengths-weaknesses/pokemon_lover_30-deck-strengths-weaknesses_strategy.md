---
source: note_com
handle: pokemon_lover
title: 【ポケカカード考察その21】各環境デッキの強みと弱みまとめ【全30デッキ】
author_display: こう@ポケカ (Kou)
url: https://note.com/pokemon_lover/n/n7b04420a354c
source_id: n7b04420a354c
kind: single
body_kind: article
date: 2026-03
vintage: current
language: ja
access: complete
ingested: 2026-07-08
covers: Strengths/weaknesses + ★ ratings for 30 current-meta decks, and how the field revolves around Unfair Stamp.
---

# Strategy Digest — 30-deck meta strengths & weaknesses (Kou@Pokeka)

> ✅ **Vintage: CURRENT — this is our live competition meta (2026-03, "Munkidori-zero" week 6).** Not
> stale, not a foreign pool: every pivotal card was verified in `data/EN_Card_Data.csv` by JP↔EN Card-ID
> join (Unfair Stamp #1080, Recon Directive/Drakloak #120, Lunar Cycle/Lunatone #675, Jetting Blow/Mega
> Starmie #1031, Mega Brave/Mega Lucario #1212, Torrential Pump/Wellspring Ogerpon #108, Itchy
> Pollen/Budew #235). The article literally covers our three agents — Dragapult ex, Mega Lucario ex, Mega
> Starmie ex. Ratings/tiers are the author's opinion; card claims are the author's — verify vs the engine
> before shipping any Hypothesis.

> English distillation (full translation retained locally in `translate.txt`, gitignored). Deck names
> mapped best-effort to English archetypes; unverified terms are flagged. `[?]` = couldn't confirm the
> exact card vs the pool.

## Agent-Doctrine

### general — the cross-cutting meta reads (highest value; new Scouting/posture + Planner signals)

- **[general → Scouting Read + posture]** **Unfair Stamp is the meta's pivot.** It's an ACE SPEC Item
  usable **only if one of your Pokémon was KO'd on the opponent's last turn** — a comeback hand-disruptor
  (shuffle hands, redraw). Post-rotation there is **no second strong interaction**, so the field splits
  into *Stamp users* and *Stamp targets*, and **surviving the one Stamp is usually enough to win**.
  *Candidate signal:* a new Read — "opponent likely runs Unfair Stamp"; a **posture lever: after I take a
  KO that lets the opponent Stamp, expect a wrecked hand next turn → don't overcommit my hand, hold a
  recovery out** (ties to dead-hand / Shuffle-Refresh recovery). Our ex/Mega decks are prime targets. This
  is the single most important read in the doc.

- **[general → tempo / Match Planner]** **Comeback tools are scarce this format** (Iono & Counter Catcher
  rotated out), so **falling behind is hard to reverse and aggro is under-punished** — pressing tempo and
  going first are strong. *Candidate signal:* format-wide tempo bias — Match Planner RACE-mode weighting,
  `preferred_start`; "press the lead, it sticks."

- **[general → disruption-aware sequencing]** **Budew's Itchy Pollen item-lock** is a live axis: if the
  opponent can item-lock next turn, **front-load this turn's item usage before the lock lands** (and we
  can weaponize it offensively). *Candidate signal:* the sequencing Digest's hold-vs-play-at-EOT rule,
  Read "opp runs Budew," Turn Planner ordering. Cross-links [[strategy-ingest-skill]] sequencing Digest.

- **[general → prize economy]** **Non-ex attackers that KO ex/Mega (Alakazam, Honchkrow) are prize-trade
  predators.** Against them our Mega (3-prize) bodies are liabilities. *Candidate signal:* prize-economy
  Read — interpose cheap attackers, avoid feeding 2-for-1s (ties to interpose-cheap-attacker-promote,
  prize-redundant-target).

- **[general → bench discipline]** **Board-wipe / spread is everywhere** (Cursed Bomb: Diancie, Greninja;
  Dragapult Phantom Dive; Froslass+Munkidori damage-counters). Wide/fragile benches get punished (HP40
  Applin dies to spread). *Candidate signal:* bench-management (don't over-extend fragile pre-evos);
  `fragile_preevo` awareness.

- **[general → type/tech Read]** **Weakness axes are load-bearing, and Clefairy (ピッピ) is the field's
  teched counter to the two pillars** (Dragapult & Lucario) — it shows up in a dozen lists "for Dragapult
  & Lucario." Psychic (超) KOs Mega Lucario; Fire (炎) wrecks grass/Venusaur. *Candidate signal:* our Read
  already does Weakness; add "expect Clefairy tech when I pilot a pillar," and respect Psychic on Lucario.

- **[general → engine-dependence targeting]** **Psyduck (damage-cap ability) hard-counters big single
  hits** (Dragapult, Diancie), and many decks brick without their draw engine / a key card. *Candidate
  signal:* opponent engine-dependence Read (Brief `opponent_properties`) — target the engine; recognize
  when a Psyduck caps our own payoff.

### our-deck — how the meta author sees OUR three agents (→ deck-align)

- **[our-deck:dragapult_ex → src/agents/dragapult_ex/STRATEGY.md]** Rated the **clear #1**. Wins on
  Phantom Dive + Cursed Bomb board-destruction, Recon Directive draw, Budew item-lock, and strong Unfair
  Stamp use (Power★★★★★, Late★★★★★). **Weaknesses to internalize:** bricks without early draw/Balls
  (Early★★★), **Psyduck caps its damage**, energy attrition if its energized attackers are repeatedly
  KO'd. Variants: Bomb / Munkidori / Blaziken (Munkidori & Blaziken add Psyduck & Clefairy tech + more
  space). *Candidate signal:* deck-align — confirm our build exploits the #1 positioning; add a Psyduck
  answer / energy-attrition plan.

- **[our-deck:mega_lucario → src/agents/mega_lucario/STRATEGY.md]** Turn-2 **Mega Brave 270 one-shots** off
  the Lunar Cycle (Lunatone+Solrock, discard Fighting → draw 3) engine; gusts with Hariyama/"Dosukoi
  Catcher"[?]; Wild Press pushes non-ex; Belt/Cape/Munkidori variants (Power★★★★★, Early★★★★★).
  **Weaknesses:** **Psychic Weakness**, being one-shot in return, needing Protein[?] to close, Cape
  broken by Tool Scrapper/Jamming Tower; **its positioning worsened after CL Fukuoka** and numbers fell.
  *Candidate signal:* deck-align — respect Psychic matchups; late-game (Late★★★) recovery vs Unfair.

- **[our-deck:mega_starmie → src/agents/mega_starmie/STRATEGY.md]** **Fastest early game** (Jetting Blow),
  spread via Froslass+Munkidori, Mega Froslass finisher, Mitsuru endurance (Early★★★★★). **But rated
  weakest of the three late** (Power★★★, Late★★): **unstable once Starmie is KO'd, weak to Unfair Stamp,
  can't win if the opponent sets up cleanly** — matches the meta's "aggro fell off once engines settled."
  *Candidate signal:* deck-align — **our agent is the Cinderace/Mega Starmie build**, which differs from
  the article's Froslass-spread build; treat this as meta-context on the *wincon*, and prioritize a
  post-KO stability / Unfair-recovery plan.

## Process

- **The Unfair-Stamp "did I just enable it?" check** is a great blunder-inspector lens: many losses in
  this format trace to handing the opponent a KO that turned on Unfair Stamp, then over-committing.
- **Meta shape for our gauntlet/Scouting artifact:** Dragapult #1; then Mega Lucario, Alakazam, Honchkrow;
  Basic-ex (Raging Bolt, Clefairy/Ogerpon) resurgent. Useful to weight opponent priors.

## Out-of-Scope

- The four-phase meta-history narrative (aggro → two-pillar → CL Fukuoka → collapse) — context, not
  agent-actionable · *non-actionable*.
- CL Fukuoka Top-4 result list (Absol/Kangaskhan, Arboliva/Ogerpon, …) — evidence for the Unfair-Stamp
  read, not portable doctrine · *non-actionable*.
- Author's ★ ratings as absolute truth — opinion; kept as priors, not facts · *non-actionable*.

## Opponent field (→ matchup-genie; compact — threat → exploitable weakness → Unfair posture)

Best-effort archetype mapping; **Brief status** noted. Existing Brief: **Alakazam** (`docs/matchups/alakazam.md`).
All others are **new** unless a Brief already exists in `src/common/scouting/briefs/`.

- **Alakazam (フーディン)** — *EXISTING Brief.* Non-ex KOs ex/Mega, Rare-Candy speed, hand grows; **Genesect denies our Unfair**. Weak to Judge, Team Rocket's Watchtower, Mist/lock-Fighting energy tech, brick without opening Ball.
- **Team Rocket's Honchkrow (ロケット団のドンカラス)** — non-ex KOs ex/Mega, TR-Supporter consistency, Giovanni-heavy (hard to gust-lock), Articuno vs Dragapult/Alakazam. Weak: energy brick, no-Lance-T1, bricks if Stamped without recovery.
- **Team Rocket's Mewtwo ex (ロケット団のミュウツーex)** — TR consistency, exploits Weakness broadly, Clefairy + Articuno tech. Weak: slow energy, no-Lance-T1.
- **N's Zoroark ex** — Trade draw+thinning, two-target sweep, high burst, counter attack, strong Unfair. Weak: hard early board (Pofin/Ciano[?]), slow energy, folds if Zoroark repeatedly one-shot.
- **Raging Bolt ex (タケルライコex)** — jewel/Tera toolbox: uncapped damage, non-ex bench snipe, Clefairy tech, strong Unfair. Weak: **board-wipe + Unfair**, hard to pilot, struggles vs non-ex decks. (Aggro variant: rush + recovers from Stamp; loses to non-ex; Lucario rough.)
- **Clefairy / Ogerpon (ピッピオーガポン)** — wide Weakness coverage, Kangaskhan-stable, fast, big draw resists Unfair, Torrential Pump 2-KO. Weak: non-ex decks; bench-count adjustment starves its damage.
- **Marnie's Grimmsnarl ex** — Froslass+Munkidori+Shadow Bullet spread, Spikemuth Gym evo consistency. Weak: **low Unfair-resistance**, damage-short, folds if one-shot.
- **Arboliva ex (オリーヴァ)** — Oil-Machinegun[?] wipe + Ogerpon/Meganium high damage, Unfair+wipe combo. Weak: high bar for Ogerpon damage, falls behind if slow, low Unfair-resistance.
- **Cynthia's Garchomp ex (シロナのガブリアス)** — King's Call board, HP400 push, lock-Fighting vs Alakazam, recovers from Unfair (Screw Dive[?]). Weak: brick without Gabite, slow energy, forced-second tempo loss.
- **Mega Venusaur ex (メガフシギバナ, 2-line & Meganium)** — high-HP wall, Mitsuru nullify/heal, Meganium+Ogerpon burst. Weak: **helpless vs Fire**, item-lock destabilizes evo, hard to recover post-Unfair, Stage-2 double-line unstable.
- **Crustle (イワパレス)** — Mystic-Stone-Shelter[?] auto-wins some matchups, Kieskiss coin-flip vs non-ex, Articuno shuts Alakazam. Weak: counter cards, time-outs (slow), pilot-hard, non-ex rough.
- **Bomb Diancie ex** — Cursed Bomb wipe + Diancie close, Telepath-Psychic dev, Clefairy tech. Weak: **Psyduck**, Telepath-dependent early, damage-short vs full board.
- **Okidogi (イイネイヌ)** — 230-HP non-ex, Bloodmoon Ursaluna one-shot, Lunar Cycle, Stone Arms accel. Weak: 170 damage short, board-wipe, low Unfair-resistance, one-shot.
- **Steven's Metagross ex (ダイゴのメタグロス)** — Ex-Boot accel, Empoleon wall, Mega Skarmory snipe, Metal Signal evo, Clefairy tech, fast T1-second. Weak: brick without Carry[?], needs second, **Itchy Pollen**, Fire.
- **Eeveelution toolbox (ブイズバレット)** — Jewel-Seeker[?] flex, broad Weakness coverage, Espeon Psycho-Out hand-disrupt, Torrential Pump wipe, big heal, customizable. Weak: brick assembling Terastal+Noctowl, Team Rocket's Watchtower, weak to Unfair.
- **Dipplin (おまつりおんど)** — double-attack + guaranteed search, Unfair on demand, strong slugfest (Power★★★★★). Weak: **HP40 Applin → spread**, brick without Thwackey[?]/Dipplin early.
- **Greninja ex (ボムゲッコウガ)** — Cursed Bomb + Clone Barrage wipe, guaranteed search, Mega Froslass burst. Weak: many evo lines (unstable), **Psychic Weakness → Clefairy**, Froslass-dependent damage.
- **Toxtricity dark-toolbox (ストリンダーバレット)** — Bad-Upper accel flex, Mega Absol hand-disrupt/forced-faint, Sneasel snipe, Unfair+Dark-Claw combo. Weak: heavy early setup (run over), weak to **Unfair** and **Itchy Pollen**.
- **Slowking (ヤドキング)** — Tri-Frost wipe, forced-faint, TM customization, high gotcha factor. Weak: high early brick, Shaymin blanks Tri-Frost, weak to Unfair (high per-turn cost).
- **Mega Sharpedo ex** — Greedy-Fang speed+draw, Hungry-Jaw burst, 0-retreat + Chain-of-Control gust every turn, Judge disruption. Weak: **Lucario**, prize-race loss if slow (it's a Mega), Grass.
- **Hop's Trevenant (ホップのオーロット)** — T1-second Leap&Dodge rush/coin pressure, Telepath+Hop's Bag dev, Psychic vs Lucario, Clefairy vs Dragapult. Weak: coin-flip variance, weak to Unfair, needs second to push.

<!-- 30 decks triaged: 3 our-deck (Dragapult/Lucario/Starmie, incl. variants), ~21 opponent archetypes,
     8 general reads, process + out-of-scope. Full translation local-only (translate.txt). -->
