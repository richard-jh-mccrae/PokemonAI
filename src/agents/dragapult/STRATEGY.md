# Dragapult ex — Playing Doctrine

> Phase-A deliverable of `/deck-genie`. The human-readable strategy the deck plays; the executable
> `strategy.py` is generated from this **after sign-off** (ADR-0017). Build on the
> [General Strategy](../../../docs/general-strategy.md): reuse, override, or extend — don't restate.

**Status:** `drafting` · **Last grilled:** 2026-06-29 · **Author:** deck-genie + Richard

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped (engine-verified; Risky Ruins + Tera double-checked)
- [x] Phase 1 overview confirmed (2026-06-29)
- [ ] Phase 2 research synthesised + confirmed
- [ ] Phase 3 card-by-card: `0/24` cards locked
- [ ] Phase 4 General-Strategy disposition complete
- [ ] Phase 5 signed off → Phase B authorised

Cards still to grill: all 24. Open questions: (1) readiness energy = 1 (Jet Headbutt) vs 2 (Phantom
Dive); (2) Munkidori opportunistic-relay sequencing vs Phantom Dive line; (3) Crushing Hammer reliance.

## 1 · Overview  *(CONFIRMED 2026-06-29)*

> **User intent (confirmed):** (1) Gameplan = **spread + 2HKO control**. (2) **Risky Ruins is
> deliberate Munkidori ammo + bench tax** — the self-damage on your own non-{D} Basics is *fuel*:
> Munkidori's Adrena-Brain relays those counters onto the opponent, and symmetric Risky-Ruins damage
> also softens *their* bench alongside Phantom Dive. NOT anti-synergy. (3) **Munkidori is
> supportive-only** — opportunistic counter-relay when {D} is online; do **not** contort the main
> Dreepy→Dragapult line to force a Munkidori turn. Reconciliation: Risky Ruins earns its slot for the
> bench tax even when Munkidori isn't online; Munkidori is the upside when it is.

- **Win condition:** Spread + 2HKO control. **Dragapult ex** (Stage 2, 320 HP, Tera, 2 prize) attacks
  with **Phantom Dive** (Fire+Psychic, 200 to Active **+ 6 damage counters spread on the opponent's
  bench**). The bench counters, recycled/moved by **Munkidori** (`Adrena-Brain`: move up to 3 counters
  from your mon to theirs, needs {D} attached) and finished by **Boss's Orders** gusts, convert the
  spread into prizes — drag up a softened benched mon and KO it, or 2HKO the Active while the bench
  rots. Prize math: opponent must take 6 (your Dragapult ex are 2-prizers ×3 = the liability); you take
  6 via Phantom-Dive 2HKOs + bench KOs enabled by spread + gust.
- **Line(s):** **Dreepy (Basic, Dragon) → Drakloak (Stage 1) → Dragapult ex (Stage 2)** · 4/4/3.
  **online at:** engine-derived = 1 energy (Jet Headbutt, C/70) — but the *real* payoff Phantom Dive
  needs 2 (F+P). **Open question: set `Ready(energy=2)`?**
- **Main attacker(s):** Dragapult ex (Phantom Dive primary; Jet Headbutt = cheap 70 filler/early).
- **Supporting Pokémon:**
  - **Munkidori** ×2 (Basic, Psychic, 110HP) — counter-mover engine (`Adrena-Brain`, needs {D}); also
    Mind Bend (PC/60 + Confuse). The spread-payoff multiplier.
  - **Dunsparce→Dudunsparce** 1/1 — draw engine (`Run Away Draw`: draw 3, shuffle itself back).
  - **Budew** ×1 (Grass, 30HP) — Itchy Pollen = opponent item-lock for a turn (tempo disruptor).
  - **Fezandipiti ex** ×1 (Basic, Darkness, 210HP, 2 prize) — `Flip the Script` draw-3-after-KO;
    Darkness so **Risky-Ruins-exempt**; can supply {D} for Munkidori indirectly.
  - **Meowth ex** ×1 (Basic, Colorless, 170HP, 2 prize) — `Last-Ditch Catch` on bench-drop: tutor any
    Supporter; Tuck Tail returns itself to hand (recover the 2-prize liability).
- **Engine (draw/search):** Lillie's Determination (draw 6, or 8 at 6 prizes) ×4, Poké Pad (search a
  non-Rule-Box Pokémon) ×4, Ultra Ball ×4, Buddy-Buddy Poffin (2 Basics ≤70HP to bench) ×4, Poké Pad,
  Drakloak `Recon Directive` (dig top-2 keep 1), Dudunsparce, Crispin (search+attach), Meowth tutor.
- **Acceleration:** thin — **Crispin** (search 2 basic energy of different types, attach 1) + **Rosa's
  Encouragement** (attach up to 2 basic energy from **discard** to a Stage 2 = Dragapult; gated on
  having more prizes left than opponent) + manual attach. No ability-based accel.
- **Disruption:** Boss's Orders ×3 (gust), Crushing Hammer ×4 (coin-flip energy denial), Budew
  (item-lock), Judge ×1 / Unfair Stamp [ACE SPEC] (hand disruption to small hands).
- **Recovery:** Night Stretcher ×3 (Pokémon or basic energy from discard → hand), Rosa's (energy from
  discard), Meowth Tuck Tail.
- **Energy:** **9 total** — 4 Psychic, 3 Fire, 2 Darkness. All basic. Energy-tight. Phantom Dive = 1F+1P;
  Munkidori ability = ≥1 {D}; Fezandipiti Cruel Arrow = 3 (CCC). No special energy.
- **User context:** *(pending — fold in Phase 1)*

## 2 · Research synthesis (cited)

*(Phase 2 — pending Phase 1 confirmation.)*

## 3 · Card-by-card

*(Phase 3 — pending. One block per card, mechanics pre-filled from the verified dump below.)*

## 4 · Combos, sequencing & opening hands

*(Phase 3/4 — pending.)*

## 5 · General-Strategy disposition table

*(Phase 4 — pending.)*

## 6 · New deck Hypotheses (drafts)

*(Phase 4 — pending.)*

## 7 · Roles, Lines, params (pre-code)

*(Phase 4 — pending.)*

## 8 · Open questions / deferred

- **Risky Ruins is symmetric self-damage:** 2 counters on every Basic non-{D} Pokémon *either* player
  benches. Hits your own Dreepy/Munkidori/Dunsparce/Budew/Meowth ex (Fezandipiti exempt). Intent to
  confirm: spread-amplifier + opponent-setup tax, or anti-synergy to cut?
- **Readiness energy:** 1 (Jet Headbutt) vs 2 (Phantom Dive). Engine default = 1; likely want 2.
- **Tera nuance:** Dragapult ex benched is immune to *attack* damage but **not** to counter-placing
  effects (Phantom Dive / Munkidori / Risky Ruins place counters, bypassing Tera).

---

## Appendix · Engine-verified card facts (Phase 0 substrate — do not hand-edit)

> Source: `dump_deck.py dragapult` + direct `cg.api` probe (2026-06-29). Engine is ground truth.

### Pokémon (18)
- **4× Dreepy** — Basic Dragon · 70 HP · 1 prize · weak none · retreat 1. `P — Petty Grudge` (10);
  `FP — Bite` (40). *(no function tags)*
- **4× Drakloak** — Stage 1 Dragon · 90 HP · 1 prize · retreat 1 · from Dreepy. tags `dig`,`draw`.
  **Ability Recon Directive:** look at top 2, put 1 in hand, other to bottom. `FP — Dragon Headbutt` (70).
- **3× Dragapult ex** — Stage 2 Dragon · **320 HP** · **2 prize** · **ex, Tera** · retreat 1 · from Drakloak.
  tag `spread`. `C — Jet Headbutt` (70); **`FP — Phantom Dive` (200): put 6 damage counters on opponent's
  benched Pokémon any way you like.**
- **2× Munkidori** — Basic Psychic · 110 HP · 1 prize · weak Darkness · resist Fighting · retreat 1.
  tags `confuse`,`heal`,`spread`. **Ability Adrena-Brain:** once/turn, if it has {D} attached, move up to
  3 damage counters from 1 of your Pokémon to 1 of opponent's. `PC — Mind Bend` (60): Active now Confused.
- **1× Dunsparce** — Basic Colorless · 70 HP · 1 prize · weak Fighting · retreat 1. `C — Trading Places` (0):
  switch this with a benched Pokémon. `CC — Ram` (20).
- **1× Dudunsparce** — Stage 1 Colorless · 140 HP · 1 prize · weak Fighting · retreat 3 · from Dunsparce.
  tags `draw`,`stall`. **Ability Run Away Draw:** once/turn, draw 3; if you did, shuffle this + attached
  into deck. `CCC — Land Crush` (90).
- **1× Budew** — Basic Grass · 30 HP · 1 prize · weak Fire · retreat 0. `(free) — Itchy Pollen` (10):
  opponent can't play Item cards during their next turn.
- **1× Fezandipiti ex** — Basic Darkness · 210 HP · 2 prize · ex · weak Fighting · retreat 1.
  **Ability Flip the Script:** once/turn, if any of your Pokémon were KO'd during opponent's last turn,
  draw 3 (max 1/turn). `CCC — Cruel Arrow` (0): 100 damage to 1 of opponent's Pokémon (no W/R on bench).
- **1× Meowth ex** — Basic Colorless · 170 HP · 2 prize · ex · weak Fighting · retreat 1. tags `search`,`stall`.
  **Ability Last-Ditch Catch:** on play from hand to bench, search deck for a Supporter to hand (max 1
  "Last-Ditch"/turn). `CCC — Tuck Tail` (60): put this + all attached into your hand.

### Trainers (33)
- **Supporter** — 4× **Lillie's Determination** (`draw`): shuffle hand, draw 6 (8 if exactly 6 prizes left).
  3× **Boss's Orders** (`gust`): switch in 1 of opponent's benched Pokémon to Active. 2× **Crispin**
  (`energy_accel`,`search`): search 2 basic energy of different types, 1 to hand + attach the other to 1 of
  your Pokémon. 1× **Judge** (`draw`,`hand_disruption`): both shuffle hands, draw 4. 1× **Rosa's
  Encouragement** (usable only if you have more prizes left than opponent): attach up to 2 basic energy
  from discard to 1 of your **Stage 2** Pokémon.
- **Item** — 4× **Buddy-Buddy Poffin** (`search`,`bench_fill`): 2 Basics ≤70HP to bench. 4× **Poké Pad**
  (`search`): search a non-Rule-Box Pokémon to hand. 4× **Ultra Ball** (`search`): discard 2, search any
  Pokémon. 4× **Crushing Hammer** (`energy_denial`): flip; heads → discard 1 energy from opponent. 3×
  **Night Stretcher** (`recycle`): a Pokémon or basic energy from discard → hand. 1× **Unfair Stamp**
  **[ACE SPEC]** (`draw`,`hand_disruption`): only if your Pokémon were KO'd last turn — both shuffle hands,
  you draw 5, opponent draws 2.
- **Stadium** — 2× **Risky Ruins** (id 1260): whenever any player benches a Basic **non-{D}** Pokémon
  during their turn, place 2 damage counters on it. **(SYMMETRIC — hits your own non-Dark Basics.)**

### Energy (9)
- 4× Psychic · 3× Fire · 2× Darkness. All basic.
