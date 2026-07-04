# vs Mega Lucario ex / Solrock (Hariyama & Lunatone variants) — Counterplay Doctrine

> Phase-A deliverable of `/matchup-genie`. The **objective** game-plan against ONE opponent archetype
> (here: two tech variants of the same core); the machine
> `src/common/scouting/briefs/hariyama_mega_lucario_ex_solrock.json` Brief is generated from this **after
> sign-off** (ADR-0027). Shared across all our decks — write deck-neutral; each agent relativizes it.

**Slug:** `hariyama_mega_lucario_ex_solrock` (canonical = the #1 meta build) · **Status:** `shipped` · **Last grilled:** 2026-07-04 · **Author:** matchup-genie + Richard
**Covers** (union of both variants' `index.json` covers): `Hariyama / Mega Lucario ex`, `Hariyama / Mega Lucario ex / Solrock`, `Mega Lucario ex`, `Lunatone / Mega Lucario ex / Solrock` — every variant routes to this one Brief.

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped (both variants) + `covers` read from index.json
- [x] Phase 1 how-it-wins confirmed (user 2026-07-04: gameplan confirmed as-is; **tempo = midrange**, not fast)
- [x] Phase 2 counterplay research synthesised (engine/rules-grounded; web coverage nil for MEG set) — every claim re-verified vs the Phase-0 dump
- [x] Phase 3 weakness grill: **8 seams locked** + donk non-seam resolved; both property calls answered by user
- [x] Phase 4 Brief-field reconciliation: threats/targets locked; `opponent_properties = { opp_tempo: midrange }` (assert-true-only)
- [x] Phase 5 signed off (user 2026-07-04 "Ship it") → Phase B emitted `briefs/hariyama_mega_lucario_ex_solrock.json`

User calls (2026-07-04): **(1)** `opp_is_engine_dependent` = **FALSE** — Trainer-backstopped; engine disruption is a tempo lever, not a kill (omitted from JSON). **(2)** `opp_donk_vulnerable` = **FALSE** — Basic-dense; the real early lever is the Riolu snipe (already `fragile_preevo`) (omitted from JSON).
Resolved this pass: Premium Power Pro applies **before** weakness (damage-calc order, docs/rules.md L126); exact stacking across copies not sim-probed (not load-bearing — the threat is "big boost," Mega Brave 300 with one copy).

## The two variants (same archetype, tech split)

Both are the **Riolu → Mega Lucario ex** core + **Solrock/Lunatone** engine + **Makuhita/Hariyama** tech.
They diverge only in line-thickness, energy count, and the single ACE SPEC:

| | Hariyama build (rank **1**, 43.8% play, 43% win, n=2372) | Lunatone build (rank 10, 3.1% play, 49.7% win, n=168) |
|---|---|---|
| Mega line | 3 Riolu / **4** Mega Lucario ex | **4** Riolu / 4 Mega Lucario ex |
| Solrock/Lunatone | 3 Solrock / 2 Lunatone | **4** Solrock / 2 Lunatone |
| Hariyama line | **2** Makuhita / **2** Hariyama | 1 Makuhita / 1 Hariyama |
| ACE SPEC | **Hero's Cape** (+100 HP wall) | **Deluxe Bomb** (120 counter-punch to our attacker) |
| Gravity Mountain | 2 | 1 |
| Switch / Boss's Orders | 2 / 2 | 3 / 1 |
| Fighting Energy | 13 | 15 |

Objective read: the **Hariyama build leans harder on gust-disruption + the wall** (2-2 Hariyama, Hero's
Cape, 2 Gravity Mountain); the **Lunatone build is leaner/faster** (thicker Riolu+Solrock, more Switch,
Deluxe Bomb punish). Same win con, same seams — one Brief.

## 1 · How it wins

- **Win condition:** grind 6 prizes behind **Mega Lucario ex** (Mega-ex, 340 HP, **gives up 3 prizes**),
  backed by cheap 1-prize Fighting attackers. Prize math: their Mega = 3, everything else = 1.
- **Line(s):** **Riolu (Basic, 80 HP) → Mega Lucario ex (Mega ex, 340 HP)** — a **single hop, no
  intermediate** (verified: rulebook Appendix 1 + engine dump; and Mega-ex do NOT end turn on evolving
  per the sim delta, so they evolve **and attack** the same turn). Secondary: Makuhita → Hariyama; Solrock
  + Lunatone stand alone.
- **Online at:** Mega Lucario can **Aura Jab (1 F, 130 dmg)** as early as T2 and **Mega Brave (2 F, 270)**
  by ~T2–3. Fast.
- **Main attacker(s):**
  - **Mega Lucario ex** — *Aura Jab* (F, 130) also **attaches up to 3 F Energy from discard to your
    bench** (self-fuelling accel); *Mega Brave* (FF, 270) but **can't be used on consecutive turns**.
  - **Hariyama** — *Wild Press* (FFF, 210, 70 recoil); and **Heave-Ho Catcher** (on evolving from hand,
    **gust an opponent's benched Pokémon Active** — a free Boss's Orders).
  - **Solrock** — *Cosmic Beam* (F, **fixed 70**, ignores Weakness/Resistance) but does nothing without
    Lunatone benched.
- **Engine (draw/search):** **Lunar Cycle** (Lunatone: with Solrock in play, discard a F Energy → draw 3,
  once/turn) + a deep Trainer suite: **Carmine** (discard hand, draw 5), **Lillie's Determination**
  (shuffle hand, draw 6 / 8 if still on 6 prizes), **Dusk Ball**, **Fighting Gong** (tutor a Basic F
  Energy **or** Basic F Pokémon), **Poké Pad** (tutor a non-Rule-Box Pokémon).
- **Acceleration:** **Aura Jab** moves energy from discard to the bench; the deck runs 13–15 basic F.
- **Disruption (to US):** **Boss's Orders** + **Hariyama's Heave-Ho Catcher** gust our bench up; **Premium
  Power Pro** (×4) gives F attacks **+30 to our Active** this turn (Mega Brave → 300, Aura Jab → 160);
  **Gravity Mountain** shaves **−30 HP off every Stage-2** in play (one-sided — their Mega ex is *not*
  Stage 2, so it only hurts *our* Stage-2 bodies).
- **Tempo:** **midrange** (user call, 2026-07-04). It *can* show a 270–300 hit by ~T2–3, but the real
  prize cadence is even, not explosive: it must set up (evolve Riolu, pair Solrock+Lunatone for draw,
  bank energy) and **Mega Brave locks out every other turn** — so it doesn't take prizes on a fast clock.
  Counter-posture: a genuine race is on the table (not forced stabilise-then-grind).
- **User context:** two decks flagged as variants of one archetype; produce a single merged Brief.

## 2 · Counterplay research (cited)

**Coverage caveat (honest).** This is a **competition-specific set (MEG) with simulator deltas** — there
is **no external web meta** for it. The Phase-2 fan-out found zero live/replay web sources; the doctrine
below is derived from the project's own **authoritative** files and **cross-checked against every stat in
the Phase-0 engine dump** (all exact). Confidence: **medium** (engine facts are hard; the *counter-lines*
are principled, not tournament-proven). No web-vs-engine conflicts (there is no web to conflict).

**Key-card findings** (how each functions + how we blunt it — all engine-verified):
- **Mega Lucario ex:** the wincon AND the accelerator. *Mega Brave* 270 (300 w/ Premium Power Pro) but
  **self-locks next turn**; *Aura Jab* 130 **reattaches 3 F from discard to bench** (self-fuelling).
  Blunt it: OHKO via **Psychic weakness** (~170 = the 340 body → **3 prizes**); exploit the off-turn.
- **Riolu:** 80-HP, 1-prize, Psychic-weak, **sole single-hop path** to the Mega. Blunt it: **snipe/gust +
  KO before it evolves** — a 1-prize KO denies a 3-prize payoff (the best trade in the matchup).
- **Hariyama:** 210 *Wild Press* (70 recoil) + **Heave-Ho Catcher** (free Boss's Orders on evolve — drags
  our bench up the same turn). Blunt it: **snipe Makuhita** (80 HP) before it evolves; don't leave a
  fragile body benched into the gust.
- **Solrock / Lunatone:** the **interlocked draw engine** — Lunar Cycle (draw 3) needs Solrock in play;
  Cosmic Beam (70, weakness-proof) needs Lunatone benched. Both **Grass-weak, 110 HP**. Blunt it: **KO the
  exposed half** to break the pair — but note the deep Trainer suite backstops raw draw (see seam 5).

**Web-vs-engine conflicts surfaced:** none (no web coverage of this set).

**Sources** (authoritative project files the synthesis grounded in — the "meta" here is the sim's replay
meta, not the physical TCG):
- `data/EN_Card_Data.csv` — per-card engine stats (HP, weakness, attacks, costs, damage).
- `docs/rules.md` — rules digest (weakness ×2, Mega-ex = 3 prizes `[PROJECT-VERIFIED]`, damage-calc order).
- `data/meta/decks/{hariyama,lunatone}_mega_lucario_ex_solrock/deck.txt` — the exported meta lists.
- `src/agents/mega_lucario/STRATEGY.md` — our in-house grilled doctrine for this exact deck (mirror-side
  knowledge: energy engine, Mega Brave lock, Solrock/Lunatone dependency).

## 3 · Exploitable seams (the weakness map)

### Seam 1 — The entire line is Psychic-weak (the dominant structural seam)
- **Weakness:** Riolu, Makuhita, Hariyama, **and the 340-HP Mega Lucario ex** all take **×2 from Psychic**
  (docs/rules.md L113). ~**170** effective Psychic damage OHKOs the Mega and claims **3 prizes** in one hit.
- **Exploit:** lead Psychic damage into *any* body; the whole board is target-rich. A Psychic OHKO on the
  Mega is a 3-for-(1 or 2) prize swing — the single best exchange available.
- **Maps to:** `target: Mega Lucario ex` role `prize_liability`; weakness itself is **auto-Dossier-derivable**
  (a card-stat) → **no new `opponent_properties` key** needed.

### Seam 2 — 3-prize payoff rides on a fragile 80-HP Riolu (single hop, no intermediate)
- **Weakness:** the wincon must route through Riolu (Basic, 80 HP, 1 prize, Psychic-weak) and survive a
  turn to evolve. No middle stage to hide behind (verified: Riolu → Mega Lucario ex directly).
- **Exploit:** **snipe / gust + KO Riolu before it evolves** — deny the 3-prize body for a 1-prize KO.
- **Maps to:** `target: Riolu` role `fragile_preevo`.

### Seam 3 — Hariyama's disruption also rides on a fragile 80-HP Makuhita
- **Weakness:** the 210-damage gust-on-evolve Hariyama comes only through Makuhita (Basic, 80 HP, 1 prize,
  Psychic-weak).
- **Exploit:** snipe Makuhita to deny the secondary attacker + its Heave-Ho Catcher gust before it comes online.
- **Maps to:** `target: Makuhita` role `fragile_preevo`.

### Seam 4 — The draw/attack engine is Grass-weak and interlocked
- **Weakness:** Lunar Cycle (draw 3) needs **Solrock** in play; Cosmic Beam (70) needs **Lunatone** benched.
  Both are 110-HP **Grass-weak** Basics — a Grass hit OHKOs (≥55). Break one half → the pair collapses.
- **Exploit:** KO/gust the exposed half (Grass weakness makes it cheap) to shut off the draw-3 **and**
  Solrock's weakness-proof chip attacker.
- **Maps to:** `target: Solrock` + `target: Lunatone`, role `engine`. Grass weakness is auto-Dossier-derivable.

### Seam 5 — Engine disruption is a TEMPO hit, not a kill (Trainer-backstopped) — *user-confirmed*
- **Weakness (bounded):** removing Solrock/Lunatone stops the *repeatable* Lunar Cycle draw, but the deck
  keeps a deep redundant Trainer engine (Carmine, Lillie's Determination, Dusk Ball, Fighting Gong, Poké Pad).
- **Exploit:** disrupt the engine for **tempo/consistency pressure**, but **don't over-invest** expecting a
  brick — the deck rebuilds off Supporters.
- **Maps to:** `opponent_properties.opp_is_engine_dependent` = **FALSE** (user 2026-07-04, Trainer-backstopped)
  → **omitted** from the JSON (assert-true-only). Solrock/Lunatone stay `engine` targets (tempo lever).

### Seam 6 — Mega Brave self-locks every other turn
- **Weakness:** after a 270 (300) Mega Brave, that Mega **can't Mega Brave next turn** — its off-turn ceiling
  drops to Aura Jab's 130 (160).
- **Exploit:** on the turn after a big hit, a 150–200-HP body survives; use the window to counter-KO, heal,
  or reposition a fresh attacker before the next 270.
- **Maps to:** `threat: Mega Lucario ex` `why` + §5 doctrine (a timing lever, no boolean property).

### Seam 7 — Aura Jab's accel needs Fighting Energy in the discard
- **Weakness:** the self-fuel loop reattaches energy **from discard**; early game the discard bank is thin,
  and mono-F means no energy-type fallback.
- **Exploit:** **pressure early** — KO attackers before the discard fills — to starve the reattach engine.
- **Maps to:** §5 doctrine + `opp_tempo = midrange` (the race window exists early; no separate property).

### Seam 8 — Gravity Mountain is one-sided; ACE SPEC varies by variant
- **Weakness:** Gravity Mountain (−30 to **Stage 2**) does **not** touch their own Mega (MEGA ≠ Stage 2,
  rulebook App. 26) — pure anti-*our*-Stage-2 tech, and **overwriteable**. ACE SPEC is a single card:
  **Hero's Cape** (Mega → 440 HP wall) in the #1 build, **Deluxe Bomb** (120 counter-punch to our attacker,
  even on KO — bypasses weakness as counters) in the lean build.
- **Exploit:** if we run a stadium, **overwrite Gravity Mountain** (erases the −30 tax free). Plan for a
  possible 440-HP Mega (two-hit or chip-then-Psychic-OHKO math). Against the lean build, don't KO into
  Deluxe Bomb with a fragile attacker we can't afford to lose.
- **Maps to:** §5 doctrine (situational, single-card — no boolean property).

### Non-seam (resolved) — donk vulnerability — *user-confirmed FALSE*
- The deck opens on 80-HP (Riolu/Makuhita) or 110-HP (Solrock/Lunatone) Basics, but it is **Basic-dense**
  and floods the board — a true single-Basic donk is unlikely. The real early lever is the **Riolu snipe**
  (already `fragile_preevo`). `opp_donk_vulnerable = FALSE` (user 2026-07-04) → **omitted** from the JSON.

## 4 · Threats & targets (objective card-level intel)

- **Threats** (attackers to respect):
  - `Mega Lucario ex` — 340 HP / 3 prizes; Mega Brave 270 (300 w/ Premium Power Pro), Aura Jab 130 + energy
    reattach. Both the wincon and the accelerator. *(Also a `target` below — the one card that is genuinely
    both: respect it defensively, and it's a 3-prize OHKO-via-weakness opportunity offensively.)*
  - `Hariyama` — Wild Press 210 (70 recoil) + Heave-Ho Catcher free gust-on-evolve; enables surprise KOs on
    our bench the same turn it develops.
- **Targets** (what to disrupt or snipe), by role:
  - `fragile_preevo`: `Riolu` — 80 HP, sole single-hop path to the 3-prize Mega; snipe before it evolves.
  - `fragile_preevo`: `Makuhita` — 80 HP, sole path to the 210 gust-attacker Hariyama.
  - `prize_liability`: `Mega Lucario ex` — Mega-ex = 3 prizes, Psychic-weak (~170 to OHKO); force it Active
    / OHKO via weakness for a game-swinging prize haul.
  - `engine`: `Solrock` — the higher-value engine half: enables Lunar Cycle draw **and** is the Cosmic Beam
    attacker; KO breaks both.
  - `engine`: `Lunatone` — the draw-3 half (needs Solrock); KO/gust throttles card flow.

_Boss's Orders is disruption we play around (noted in §5), **not** listed as a threat — the threat vocab
is attackers; a gust Supporter is board-context, not a body to respect._

## 5 · Objective counterplay summary

Beat this deck by **exploiting its Psychic weakness and its prize economy**, not by out-slugging it. The
whole line — including the 340-HP, **3-prize** Mega Lucario ex — folds to ~170 Psychic, so a Psychic OHKO
on the Mega is a game-swinging 3-for-1(/2). Failing the weakness angle, **snipe the fragile 80-HP pre-evos**
(Riolu denies the wincon, Makuhita denies the gust-attacker) — a 1-prize KO that erases a 3-prize (or 210)
payoff. It's **midrange**: a genuine race is on the table, and the discard-fuelled accel + Mega Brave's
every-other-turn lockout give real early/off-turn windows — pressure early, and expect only ~130 the turn
after a 270. Disrupt the Solrock+Lunatone engine for **tempo**, not as a kill (the Trainer suite rebuilds).
Keep our own multi-prize bodies off the bench (Boss's Orders + Hariyama's gust reach past our Active), run
a stadium to overwrite Gravity Mountain, and respect the single-card ACE SPEC swing (440-HP Mega, or a
120-damage Deluxe Bomb counter-punch).

## 6 · Brief preview (pre-JSON — filled in Phase 4, emitted in Phase 6)

```
opponent_properties = {
  "opp_tempo": "midrange"                     # user-confirmed; the only asserted lever
  # opp_is_engine_dependent = FALSE (seam 5) and opp_donk_vulnerable = FALSE (non-seam) — user-confirmed
  # 2026-07-04; assert-true-only, so both are OMITTED from the JSON (recorded in §3 so they aren't re-litigated)
}
threats = [ Mega Lucario ex, Hariyama ]
targets = [ Riolu (fragile_preevo), Makuhita (fragile_preevo),
            Mega Lucario ex (prize_liability), Solrock (engine), Lunatone (engine) ]
```

No new `opponent_properties` key minted — the two type-weaknesses are auto-Dossier-derivable, and the
timing/stadium/ACE-SPEC seams are doctrine-level (no boolean lever with a consumer). Vocabulary stays small.

## 7 · Open questions / deferred

- **Both user calls resolved (2026-07-04):** `opp_is_engine_dependent` = FALSE, `opp_donk_vulnerable` =
  FALSE. `opponent_properties` ships as just `{ "opp_tempo": "midrange" }` (assert-true-only); the false
  judgments live in §3 so a future revisit doesn't re-litigate them.
- Canonical slug = `hariyama_mega_lucario_ex_solrock` (the #1 build; its `deck.csv` is the validator's
  card-check target — every shared Pokémon lives there). `covers` = **union** of both variants' index
  entries → the validator will **warn** that `covers` diverges from `index.json[hariyama].covers` (which
  lacks the Lunatone string); that warning is **expected and correct** (deliberate two-variant merge).
- Premium Power Pro cross-copy stacking not sim-probed (not load-bearing).
- Deferred: if the meta-tracker later splits these variants or a new tech emerges, re-verify the trainer
  lines and re-confirm the merge.
