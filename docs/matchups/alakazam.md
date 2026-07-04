# vs Alakazam (Powerful Hand) — Counterplay Doctrine

> Phase-A deliverable of `/matchup-genie`. The **objective** game-plan against ONE opponent archetype;
> the machine `src/common/scouting/briefs/alakazam.json` Brief is generated from this **after sign-off**
> (ADR-0027). Shared across all our decks — write deck-neutral; each agent relativizes it.

**Slug:** `alakazam` · **Status:** `locked → shipping` · **Last grilled:** 2026-07-04 · **Author:** matchup-genie + Richard
**Covers** (from `data/meta/decks/index.json`): `Alakazam`, `Alakazam / Frillish` — every variant routes to this one Brief.
**Meta note:** rank **2** by play-rate (**32.1%** — one of the two most-played decks), 53.6% win-rate, 1735 episodes. A grindy single-prize hand-size deck.

## Progress checklist (resumability — keep current)

- [x] Phase 0 facts dumped (`dump_deck.py --deck-dir data/meta/decks/alakazam`) + `covers` read from index.json
- [x] Phase 1 how-it-wins confirmed (user: "otherwise good, continue"; tempo=midrange; **headline lever = hand disruption**)
- [x] Phase 2 counterplay research synthesised (9 sources, confidence **high**, 38/55 claims verified, 0 mechanics conflicts)
- [x] Phase 3 weakness grill: `8/8` seams locked
- [x] Phase 4 Brief-field reconciliation complete (3 opponent_properties incl. 2 new keys, 3 threats, 3 targets + 1 anti-target)
- [x] Phase 5 signed off → Phase B authorised (user: "tempo lever, and use opp_hand_size_attacker, go")
- [x] Phase B: Brief emitted `src/common/scouting/briefs/alakazam.json`, 2 keys registered, `validate_brief.py alakazam` → **Brief OK** (0 warnings)

Open seams to grill: Darkness weakness, fragile deep evo (Abra 50 / Kadabra 80), hand-size dependence (single-target, Active-only), draw-engine dependence (Dudunsparce self-recurs), single-prize prize-economy, tempo/donk window, Battle Cage anti-spread, Enhanced Hammer special-energy denial (threat-to-us). Open questions: tempo = slow vs midrange; which new opponent_properties keys to mint.

## 1 · How it wins

- **Win condition:** Grind out 6 prizes with a recurring **single-prize** attacker whose damage scales with hand size. **Alakazam** (MEG 56, Stage 2, 140 HP, **1 prize**) attacks with **Powerful Hand** (`P` cost, base 0): *place 2 damage counters on the opponent's Active for each card in your hand* → **20 damage × cards in hand**. A ~10-card hand = **200** to the Active. Prize math: **every** Pokémon in the deck is **1 prize** (no ex / Mega-ex) — the deck is prize-efficient and recurs its attackers (Night Stretcher, Sacred Ash, Lana's Aid), so it's an attrition grinder, not a prize-race.
- **Line(s):** `Abra` (Basic, 50 HP) → `Kadabra` (Stage 1, 80 HP) → `Alakazam` (Stage 2, 140 HP), or `Abra` → **Rare Candy** → `Alakazam` (skip Kadabra). **Online turn 2–3** (Rare Candy enables a turn-2 Alakazam). Only **1 Psychic energy** is needed to attack (Powerful Hand costs `P`), so the deck is almost energy-independent.
- **Main attacker(s):** `Alakazam` (Powerful Hand — the scaling payoff, single-target on the Active only). Secondary/filler: `Kadabra` Super Psy Bolt (30), `Dudunsparce` Land Crush (90 for CCC — rarely used; it's a draw pivot).
- **Engine (draw/search):** massive draw + search — **Kadabra Psychic Draw** (+2 on evolve) and **Alakazam Psychic Draw** (+3 on evolve) fire the moment you evolve; **Dudunsparce Run Away Draw** (draw 3, then shuffle itself + attached back into deck) is the **repeatable** draw engine; **Enriching Energy** [ACE SPEC] draws 4 on attach; **Dawn** (Basic+Stage1+Stage2), **Hilda** (Evolution + Energy), **Poké Pad** (non-Rule-Box Pokémon), **Buddy-Buddy Poffin** (2 ≤70-HP Basics to bench), **Telepath Psychic Energy** (search 2 Basic P to bench on attach), **Rare Candy** ×4. This is a very consistent Stage-2 engine whose whole job is to make the hand **big** right before Powerful Hand.
- **Acceleration:** N/A for attacking (Powerful Hand is `P`/1 energy). "Acceleration" here is *card* acceleration (draw), not energy.
- **Disruption (what it does to US):** **Boss's Orders ×3** (gust our bench piece up), **Enhanced Hammer ×4** (discard a **Special** Energy from our Pokémon — hurts special-energy-reliant decks), **Battle Cage** stadium (prevents damage counters on **Benched** Pokémon from opponent attacks/abilities — an **anti-spread** tech that blunts bench-snipe decks).
- **Tempo:** **midrange** (confirmed) — Stage 2 but Rare-Candy-fast and heavily redundant; comes online ~turn 2–3. There is still an early window before Alakazam + a big hand exist.
- **User context:** the **best defensive lever is hand disruption** (Judge / Harlequin / Unfair Stamp — shuffle-down the opponent's hand). Because Powerful Hand damage *is* the hand size, forcing Alakazam to attack from a small hand craters its output. This is deck-relative tech (needs our pool to have a shuffle-down), but it points at the deck's defining objective seam.

## 2 · Counterplay research (cited)

Engine-grounded synthesis; a web counterplay sweep (5 angles, 5 key cards, 77 agents, 9 sources,
**confidence high**, 38/55 claims survived adversarial verification, **0 mechanics conflicts**) folded on
lock. Per CLAUDE.md the web is a *strategy* prior only — every load-bearing mechanic rests on verified
engine facts.

**How it's beaten (objective):** don't out-grind the hand-size race — **win the prize race on even
trades** and **remove the body**. Four levers do the work:
- **(a) Hand disruption, timed to the swing turn** (the headline, user-named). Powerful Hand has **no
  damage floor** (base 0), so a shuffle-hand-down landed *on or immediately before* their Powerful Hand
  turn cuts that KO proportionally (2-card hand = 40). Their redundant draw (Psychic Draw on evolve,
  repeatable Dudunsparce, Enriching draw-4) **refills fast**, so off-turn disruption is refunded — it's a
  **timing-dependent tempo lever, not an auto-win**. (Web note: the archetype only became viable *because
  Iono rotated out* — shuffle-down was historically its defining counter.)
- **(b) Wall the Active.** Powerful Hand is **Active-only, single-target, zero bench spread**. A high-HP or
  expendable Active absorbs the hit while the real board builds behind it; promoting a fresh full-HP Active
  after a KO resets their damage clock and forces multi-turn hoarding — each turn a fresh disruption window.
- **(c) Darkness weakness (×2), and avoid Fighting.** A Darkness attacker OHKOs Alakazam (140 → 70-base)
  for trivial cost; since it's the deck's **only** attacker, that trade is heavily in our favor. **The
  whole Psychic line RESISTS Fighting (−30)** — Fighting attackers are the wrong type into it.
- **(d) Race the setup + remove the pre-evos.** Stage-2 line off a **50 HP Abra / 80 HP Kadabra**; press
  a 1-prize board hard before Alakazam stabilizes T2–T3.

**Key-card findings (function + how we blunt it):**
- **Alakazam (MEG 56)** — sole win condition + payoff (Powerful Hand, no cap). Blunt: KO the body (Darkness
  ×2, or any 140 hit); the **Psychic line does NOT self-shuffle**, so a KO is a genuine rebuild — real
  tempo denial. Do **not** try to out-grind its hand size.
- **Abra / Kadabra** — the fragile pre-evos (50 / 80 HP, 1 prize, Darkness-weak, Fighting-resist). Remove
  before Alakazam lands: each one buys a turn and taxes their search. **Battle Cage caveat:** it blocks
  damage *counters* on the **bench**, so bench-snipe onto a benched Abra is blanked while the Cage is up —
  **gust it Active** (Active hits land normally) or overwrite the Cage with our own stadium.
- **Dudunsparce** — **NOT a target (a trap).** Run Away Draw self-shuffles it + attached cards back into
  the deck, so any KO/gust is refunded. Ignore it; hit the hand-size seam (which blunts it for free).
- **Battle Cage** — 1-copy symmetric anti-bench stadium (blocks bench *counters* from opp attacks/abilities;
  attack *damage* to the bench still lands). Beat it as a **stadium** (overwrite with our own) or route all
  pressure to the **Active**, where it gives zero protection.
- **Enhanced Hammer ×4** — special-energy denial. **Engine diverges from real-TCG:** hits **ANY** of our
  Pokémon (not Active-only) and runs **4 copies**. Blunt: attack off **Basic** energy where possible
  (makes all 4 dead cards); if we must run special energy, don't pre-load it on a single body.

**Web-vs-engine conflicts surfaced:** none on mechanics. Two engine divergences the Brief follows over the
web: **Enhanced Hammer** = any-Pokémon / 4 copies (web = Active-only / 1–2); **Powerful Hand** places damage
**counters** (web says "damage") — identical numbers, but counter-placement is why their own Battle Cage
shields their bench, and why any anti-counter tech would blunt them. Meta "auto-loss" framing (Dragapult ex
spread, Team Rocket's Articuno) is directional web opinion, not engine-decidable — noted, not encoded.

**Sources** (web strategy priors; engine facts — `data/EN_Card_Data.csv`, `docs/rules.md` — are primary):
- Alakazam (MEG 56) — <https://limitlesstcg.com/cards/MEG/56> · Battle Cage (PFL 85) — <https://limitlesstcg.com/cards/PFL/85> · Enhanced Hammer (TWM 148) — <https://limitlesstcg.com/cards/TWM/148>
- Alakazam deck overview / matchups — <https://limitlesstcg.com/decks/350> · list — <https://limitlesstcg.com/decks/list/25939>
- "This Deck is Legitimately Broken (with the Right Matchups)" — <https://www.pokebeach.com/2026/04/this-deck-is-legitimately-broken-with-the-right-matchups>
- Alakazam Dudunsparce deck tech — <https://pokemon.cardsrealm.com/en-us/articles/pokemon-tcg-standard-deck-tech-alakazam-dudunsparce>
- "…can draw you cards for days" (Iono-was-the-counter) — <https://www.wargamer.com/pokemon-trading-card-game/alakazam-card-draw>
- Best Alakazam Deck Guide — <https://deltiasgaming.com/pokemon-tcg-best-alakazam-deck-guide-mega-evolution/>

## 3 · Exploitable seams (the weakness map)

### Seam 1 — Powerful Hand damage *is* the hand size (the headline)
- **Weakness:** Alakazam's only damage is `20 × cards-in-hand`, base 0 — **no damage floor**. A shrunk
  hand craters it: 4 cards = 80, 2 cards = 40.
- **Exploit:** **hand disruption** (shuffle-hand-down: Judge / Harlequin / Unfair Stamp) landed **on or
  immediately before their Powerful Hand turn**. Their draw refills fast (Psychic Draw on evolve, repeatable
  Dudunsparce, Enriching draw-4), so it's a **timing-dependent tempo lever, not an auto-win** — off-turn
  disruption is refunded. (Historically Iono was *the* counter; the archetype rose when Iono rotated out.)
- **Maps to:** **NEW key** `opp_hand_size_attacker = true` (mint + flag, consumer: unwired) + `threat: Alakazam`.

### Seam 2 — Powerful Hand is Active-only, single-target, zero bench spread
- **Weakness:** it can only ever damage the **Active**. No bench pressure at all; our bench develops freely.
- **Exploit:** **wall the Active** — park a high-HP or expendable body to eat the hit while the real board
  builds; **promote a fresh full-HP Active after a KO** to reset their damage clock. A body it can't OHKO
  from a modest hand forces multi-turn hoarding — each turn a fresh hand-disruption window.
- **Maps to:** same **`opp_hand_size_attacker`** key (the wall-the-Active dimension) + counterplay prose.

### Seam 3 — Darkness weakness ×2, and it RESISTS Fighting (−30)
- **Weakness:** the whole Alakazam line is Darkness-weak (140 → 70-base OHKO) — and it's the deck's **only**
  attacker, so a weakness trade is heavily one-sided.
- **Exploit:** attack with **Darkness**; **never Fighting** — Abra/Kadabra/Alakazam all resist Fighting −30.
- **Maps to:** type intel (already in the auto-Dossier's card facts) → counterplay prose + `target` notes,
  not a Board key.

### Seam 4 — Fragile deep evo + midrange setup window
- **Weakness:** Stage-2 line off a **50 HP Abra / 80 HP Kadabra** (1 prize each, Darkness-weak). Alakazam
  isn't online until ~T2–T3 (Rare Candy). No wall exists before it evolves.
- **Exploit:** pressure a 1-prize board early and **KO/gust the pre-evos before Alakazam lands** — each one
  buys a turn and taxes their search. **Battle Cage caveat:** it blocks bench damage *counters*, so a
  benched-Abra snipe is blanked while the Cage is up — **gust it Active** (Active hits land normally) or
  overwrite the Cage with our own stadium.
- **Maps to:** `opp_tempo = "midrange"` + `target: Abra` / `target: Kadabra` role `fragile_preevo`.
  (Donk: considered and **rejected** — 50 HP Abra is soft but Buddy Poffin + 4 Dawn / 4 Poké Pad refill and
  protect it; not a reliable donk. `opp_donk_vulnerable` left false.)

### Seam 5 — All-single-prize economy: race even trades, don't chase multi-prize
- **Weakness:** **no ex / Mega** anywhere — every body is 1 prize, so there's **no multi-prize insurance**
  and no 2-for-1 gust swing for us to farm. But the flip side is *ours*: the **Psychic attacker line does
  NOT self-shuffle**, so every KO on Abra/Kadabra/Alakazam is **real progress toward 6**, and recursion is
  finite (Night Stretcher ×3, Sacred Ash ×1, Lana's Aid ×1).
- **Exploit:** **win the prize race on even trades** — keep cheap single-prize attackers coming; sustained
  pressure outruns their ability to re-assemble the attacker. Don't try to out-grind the hand-size race.
- **Maps to:** **NEW key** `opp_single_prize = true` (mint + flag, consumer: unwired).

### Seam 6 — Dudunsparce is a TRAP, not a target
- **Weakness (inverted):** Run Away Draw self-shuffles Dudunsparce + attached cards back into the deck, so
  a KO/gust spent on it is **refunded** — the wrong target.
- **Exploit:** **ignore it.** Attack the shared hand-size seam (Seam 1), which blunts this draw engine for
  free, and remove the Psychic line (Seam 5) instead.
- **Maps to:** an explicit **anti-target** note in §4 / the Brief `targets` reasoning (flag, not a kill).

### Seam 7 — The disruption package to respect (Boss's Orders / Enhanced Hammer / Battle Cage)
- **Weakness (to us, not theirs):** the deck's proactive tools are **Boss's Orders ×3** (its only reach to
  our bench — gusts a fragile piece Active to pick it off around our wall), **Enhanced Hammer ×4** (engine:
  strips a **Special** Energy from **ANY** of our Pokémon, not just Active), and **Battle Cage** (shields
  *their* bench counters).
- **Exploit:** don't leave a fragile key piece benched assuming Powerful Hand can't touch it (Boss's reaches
  it); attack off **Basic** energy where possible to make all 4 Hammers dead cards, and don't pre-load
  special energy on a single body; beat Battle Cage as a stadium (overwrite) or ignore it by hitting Active.
- **Maps to:** `threat: Boss's Orders`, `threat: Enhanced Hammer` + counterplay prose (Battle Cage handled
  as a stadium note; energy denial vs *them* is near-useless — they attack off 1 Basic).

## 4 · Threats & targets (objective card-level intel)

- **Threats** (respect):
  - `Alakazam (MEG 56)` — the sole win condition. Powerful Hand (`P`, base 0) = 20 × hand size on the Active,
    **no cap** — OHKOs essentially any single Active given a big enough hand; Darkness-weak, Active-only.
  - `Boss's Orders` — the deck's **only** reach to our bench; gusts a fragile piece Active to KO around a wall.
  - `Enhanced Hammer` — special-energy tax; **engine hits ANY of our Pokémon** (not Active-only), **×4**.
- **Targets** (disrupt / snipe), by role:
  - `engine`: `Alakazam (MEG 56)` — sole attacker; the Psychic line does **NOT self-shuffle**, so KOing the
    body is real prize progress **and** tempo denial (slow to re-assemble). Remove it; don't out-grind its
    hand. (Darkness ×2, or any 140 hit.)
  - `fragile_preevo`: `Abra` — 50 HP, 1 prize, Darkness-weak, base of the only win line. KO pre-evolution to
    deny an Alakazam + tax their search. **Battle Cage:** gust it Active (bench snipe blanked while Cage up).
  - `fragile_preevo`: `Kadabra` — 80 HP, 1 prize, Darkness-weak middle + draw node (Psychic Draw +2). Same
    Battle Cage caveat — route the hit through the Active.
  - **Anti-target (do NOT snipe):** `Dudunsparce` — Run Away Draw refunds any KO/gust (self-shuffles back).
    Hit the hand-size seam instead. (Flagged in the Brief target reasoning, not listed as a target row.)
  - `prize_liability`: **none** — the deck runs no ex / Mega-ex; no multi-prize body to farm.

## 5 · Objective counterplay summary

Beat Alakazam by **winning the prize race on even trades and removing the body — never by out-grinding its
hand**. Its damage *is* its hand size (Powerful Hand, no floor, Active-only), so the premium lever is
**hand disruption timed to the swing turn** (off-turn is refunded by its fast draw), backed by **walling the
Active** and **promoting a fresh body after each KO** to reset the damage clock. Attack through **Darkness
weakness** (its only attacker folds to a ×2 trade) and **never with Fighting** (the whole line resists −30).
Race the **midrange setup window**: KO/gust the fragile **Abra/Kadabra** pre-evos Active before Alakazam
stabilizes — and because every body is **1 prize** and the Psychic line doesn't self-recur, each KO is real
progress toward six. **Do not** sink resources into **Dudunsparce** (it self-shuffles — refunded) or into
**energy denial** (it attacks off one Basic). Respect **Boss's Orders** (don't bench a snipeable key piece)
and attack off **Basic** energy to blank its four **Enhanced Hammers**.

## 6 · Brief preview (pre-JSON — filled in Phase 4, emitted in Phase 6)

```
tempo = "midrange"
opponent_properties = {
  "opp_hand_size_attacker": true,   # NEW KEY — mint + flag (consumer: unwired). Damage = 20 x hand size,
                                    #   Active-only, no floor. Levers: value hand-disruption (timed to the
                                    #   swing turn) + high-HP walling; discount chip/out-grind lines.
  "opp_single_prize":       true,   # NEW KEY — mint + flag (consumer: unwired). No ex/Mega; no multi-prize
                                    #   swing to farm, BUT the attacker line doesn't self-shuffle so each KO
                                    #   is real progress. Lever: value even-trade tempo over multi-prize burst.
  "opp_tempo":              "midrange"  # reuse — Alakazam online ~T2-3; a real early window before the wall.
}
threats = [
  { "card": "Alakazam",       "why": "Sole win condition; Powerful Hand 20 x hand size on the Active, no cap; Darkness-weak, Active-only." },
  { "card": "Boss's Orders",  "why": "The deck's only reach to our bench; gusts a fragile piece Active to KO around a wall." },
  { "card": "Enhanced Hammer","why": "Special-energy tax; engine strips it from ANY of our Pokemon (not Active-only), x4." }
]
targets = [
  { "card": "Alakazam", "role": "engine",         "why": "Sole attacker; Psychic line does NOT self-shuffle, so KO = real prize + tempo denial. Darkness x2. Do not out-grind its hand." },
  { "card": "Abra",     "role": "fragile_preevo", "why": "50 HP, 1 prize, Darkness-weak base of the only win line; KO pre-evo (gust Active under Battle Cage) to deny an Alakazam + tax search." },
  { "card": "Kadabra",  "role": "fragile_preevo", "why": "80 HP, 1 prize, Darkness-weak middle + draw node; KO before Alakazam lands. Route the hit through the Active (Battle Cage)." }
]
# Anti-target flagged in Abra/engine reasoning: Dudunsparce self-shuffles (Run Away Draw) — never spend a KO/gust on it.
```

## 7 · Open questions / deferred

**Resolved at grill (2026-07-04):**
- `opp_hand_size_attacker` — **minted** (dedicated key over reusing `opp_is_engine_dependent`; captures both
  the hand-disruption and the Active-only/wall dimensions).
- `opp_single_prize` — **minted** (objective prize-economy property; reusable for any single-prize toolbox).
- `opp_donk_vulnerable` — **rejected** (50 HP Abra is soft but Poffin + heavy search protect it; not reliable).
- Alakazam — **threat + target `engine`** (the sole un-shuffling body to remove).
- Boss's Orders + Enhanced Hammer added as `threats` (disruption to respect, though not attackers).

**Deferred (not blocking the Brief — inert data today):**
- Both new keys await consumer wiring before they change any play (forward contracts; flagged in the Phase-B diff).
- Hand-disruption / own-stadium / high-HP-wall / Darkness-attacker are **deck-relative capabilities** — each
  agent maps them to its own roster (`/deck-genie` relativization), not encoded as objective Board keys.
- Meta "auto-loss" framing (Dragapult ex spread, Team Rocket's Articuno) is directional web opinion — noted,
  not encoded (and Battle Cage blunts naive bench-spread anyway).
