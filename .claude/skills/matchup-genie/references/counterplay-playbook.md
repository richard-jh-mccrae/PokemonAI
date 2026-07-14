# Counterplay playbook — how to interrogate an opponent deck into a weakness map

Read this before Phase 3. The goal of the grill is to leave **no seam unexamined**: by the end you
should be able to name, for this deck, exactly *how it wins*, *where it's soft*, and *what we do about
it* — and to have pinned each answer to a Brief field. The user is the domain authority; your job is to
drag the tacit "this deck folds to X" knowledge out of them and ground it in the dump + research.

This is the deck-genie grill **flipped**: deck-genie asks "how do we USE our card?"; here you ask "how do
we BEAT their deck?" The subject is the opponent; the output is objective and deck-neutral.

## Discipline (borrowed from grill-me / deck-genie)

- **One seam at a time.** Pick a weakness hypothesis, push until it's *resolved* (weakness + exploit +
  Brief field), then move on. Depth-first, not breadth-first.
- **Propose, then test.** Bring a hypothesis from the dump + research ("its whole engine is Dudunsparce
  — gust it turn 2 and they brick, right?") and make the user confirm/refine/reject. A sharp wrong guess
  beats an open question.
- **Chase the edges.** The real doctrine is in the carve-out: "we race it — *unless* it opens Snorlax."
  Find the exception; it's usually the rule.
- **Tie every answer to a Brief field.** Every "we beat it by…" must resolve to an `opponent_properties`
  key, a `threat`, or a `target` — something the runtime could one day read. If it can't, flag it
  (it may need a new key, i.e. new consumer infra).
- **Objective, not relativized.** Write "this deck is slow; it's raceable" — never "our Cinderace
  out-races it." Relativization is each agent's job downstream.
- **Confirm before you write.** The user's "yes" promotes a seam from draft to locked.

## The two card-level signals (mirror the auto-Dossier vocab)

Every opponent card sorts into at most one of these — the same vocabulary the auto-Dossier
(`compile_scouting._dossier_intel`) and [CONTEXT.md](../../../CONTEXT.md) use, so the Brief speaks the
runtime's language:

| Signal | Question it answers | Brief field |
|---|---|---|
| **Threat** | which of their Pokémon do we have to *respect / answer*? | `threats[]` |
| **Target** | which of their Pokémon do we *disrupt / snipe*, and why? | `targets[]` with a `role` |

Target roles (exactly these five, all feeding the ADR-0051 MatchupPlan): **`prize_liability`** (the
wincon body / ex / Mega-ex — KO or gust it), **`fragile_preevo`** (low-HP pre-evo of the wincon — snipe
before it evolves), **`disruption_target`** (their key supporter/enabler whose removal strangles setup —
the **explicit "hunt this" role**; use it, not `engine`, when you want an agent to target it),
**`engine`** (a plain accelerant — **NEUTRAL** / informational, NOT targeted), **`avoid`** (a
matchup-specific decoy or untouchable body — a benched Tera-ex, a self-shuffler — never sink removal
here; do NOT use it for generic draw engines, which the general `draw`-tag tier already handles).
Attackers go in `threats`, not `targets`.

**`prize_liability` means THE WINCON — not "any fat multi-prize body".** It is the top priority (100) and
carries the gust's wincon-denial bump. A 2-prize SUPPORT ex (a draw engine, a tutor, a pivot) is **not**
the payoff — role it `disruption_target` (60) so it ranks BELOW the win-condition. It remains a fine gust
target regardless: the gust already values it at its 2 prizes. Get this wrong and the agent drags a
support body up over the body whose loss actually ends the game (all of them are 2 prizes, so prize value
alone TIES them and the role is the only tiebreak).

⚠️ **Card facts cannot make this call for you.** In the Dragapult deck the support **Latias ex** hits for
200 — *exactly as hard as the Dragapult ex wincon*. Nothing in the card data says which is the payoff.
Only the Brief knows. Name the win-condition explicitly, exactly once.

**Untargetable payoffs — check BEFORE you role a wincon.** Some payoffs cannot be hit where they sit:
- **Tera Pokémon** (`Category: Tera(<Type>)` in `EN_Card_Data.csv` → engine `CardData.tera` → `CardStat.tera`)
  take **NO damage from attacks while BENCHED** (rules.md §185). That label is exactly what marks a body
  **non-snipable**. 32 cards carry it (Dragapult ex, Terapagos ex, the Ogerpon/Eeveelution ex line, …).
- **Prevent-all-damage walls** — e.g. Crustle blocks ALL damage from Pokémon ex, and every one of our
  win-conditions is an ex (an `ignoresEffects` attack pierces it — check before writing one off).

You may still role a Tera-ex wincon **`prize_liability`**: the bench-snipe boost auto-stands-down on a
benched Tera (`_snipe_matchup_tactical`), while the **gust** legitimately drags it Active — where the
immunity does NOT apply — and KOs it there. But NEVER role a body positively expecting a *snipe* to reach
it through Tera/prevent-all immunity: the counters land nowhere. If the payoff can only be answered by
denying its line, role the **pre-evo** `fragile_preevo` and leave the payoff out.

## Weakness question banks

Walk these seams. Each resolved seam → a §3 block in `MATCHUP.md` + a Brief field.

### Tempo & the race clock
- When does the payoff come **online** (energy + turn)? How many turns of setup before it's taking
  prizes? → sets `tempo` (fast / midrange / slow) and the window we exploit.
- Is there a **stabilise-then-grind** vs **race** answer? What board flips it?
- Does it have a **turn-1/2 dead-draw** line (needs a specific piece to function)? How often does it brick?

### Engine dependence (the disruption seam)
- What's the **consistency core** (the draw/search Pokémon it can't function without)? If we gust + KO
  it, does the deck stall? → a `target` role `disruption_target` (the explicit "hunt this enabler" role;
  `engine` is now neutral, and `opp_is_engine_dependent` is retired/unwired — ADR-0051).
- Does it lean on a **single Supporter / Item / Stadium**? Is that answerable (hammer, stadium war, item
  lock)?
- What's its **recovery** — can it rebuild the engine after we remove it, or is removal permanent?

### Fragile pre-evos & the donk seam
- What are the **low-HP Basics / pre-evos** on the path to the payoff? Can we snipe one before it evolves
  to deny the whole line? → `target` role `fragile_preevo`.
- Does it run **single-Basic openers** that a fast line can donk or prize early? → `opp_donk_vulnerable`.

### Prize liabilities
- Which bodies are **ex / Mega-ex** (2 / 3 prizes)? When forced Active, do they swing the prize race our
  way on a KO? → `target` role `prize_liability`.
- Does the deck **over-commit** multi-prize bodies to the bench (gust bait)?

### Threats to respect
- What's the **payoff attack** — cost, damage, what it OHKOs in our decks? What's the secondary attacker?
- Any **snipe / spread / bench-hit** we must play around? Any **ability** that throttles us (item lock,
  energy denial, damage prevention)? → `threats[]`, and note the exploit if the threat has a soft flank.

### Type & structural matchup
- Any **weakness type** we can lean on? Any **resistance / defensive tech** that blunts our usual line?
- A **hard structural counter** (e.g. it item-locks → our item-heavy engine suffers) — is that a
  `threat` note or a new `opponent_properties` key?

## Turning answers into the doc + Brief

Each resolved seam → a §3 block (weakness + exploit + "maps to") and the §4 threat/target lists. Each
`opponent_properties` decision → reuse a registered key where one fits, else **mint one BY DEFAULT** in
[src/common/scouting/opponent_properties.json](../../../../src/common/scouting/opponent_properties.json) (`consumer: "unwired"` + a `note`,
flagged in the write-up) — minting-when-nothing-fits is a default action you take yourself, **not a user
question**. Keep the **progress checklist** current so the session is resumable. Phase 6 then emits the JSON.
