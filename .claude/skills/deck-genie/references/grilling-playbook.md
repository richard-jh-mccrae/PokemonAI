# Grilling playbook — how to interrogate a deck into a doctrine

Read this before Phase 3. The goal of the grill is to leave **no card and no turn ambiguous**: by
the end you should be able to explain, for every card, exactly when it's played and why — and for
every common situation, what the deck does. The user is the domain authority; your job is to drag
the tacit knowledge out of them and pin it to the Pilot's decision model.

## Discipline (borrowed from grill-me)

- **One branch at a time.** Pick a card or a question, push on it until it's *resolved*, then move
  on. Don't spray ten questions across ten cards — you'll get mush. Depth-first, not breadth-first.
- **Propose, then test.** Don't ask open "how do you play X?" into the void. Bring a hypothesis
  from the dump + the research ("Cinderace opens and Turbo-Flares T1, then sits as a wall — right?")
  and make the user confirm, refine, or reject. A sharp wrong guess gets a better answer than a
  vague question.
- **Chase the edges.** The interesting doctrine is in the exceptions: "always search the wincon —
  *unless* what?" Find the carve-out. That carve-out is usually the real rule.
- **Tie every answer to a mechanism.** Every "play it here" must resolve to a Role, a Function Tag,
  a Plan mode, a board condition, or a sequencing priority — something a `when(ctx)` could later
  read. If an answer can't be grounded in `Context`/`Board`, flag it (it may need new infra).
- **Confirm before you write.** The user's "yes" is what promotes a line from draft to locked. Mark
  unconfirmed lines clearly in the doc.

## The three signals every card maps onto

**Before grilling a card, put its full mechanical profile on the table from the dump** — the
CardStat row, its `card_functions.json` function tags, and the exact cost/damage/effect text of its
attacks and abilities — **plus its researched purpose from Phase 2** (the per-card deep dive or
per-trainer finding: its job, companions, setup, anti-patterns). The grill is about *usage*; the
mechanics must already be explicit, pulled from the engine + tags, never recalled from memory, and the
research means you **open with a sharp hypothesis to confirm/refine, not an open question into the
void.** A card you can't see the stats, tags, and researched purpose for is a card you can't grill.

**Cover every trainer (point 4).** After the Pokémon plan is locked, walk **every** Supporter / Item /
Tool / Stadium / special Energy — none is skipped. The Phase-2 trainer pass already pinned each one's
purpose and priority; the grill confirms it and resolves the sequencing/priority order between them.

Keep these straight (from [docs/card-functions.md](../../../docs/card-functions.md)) — they never
overlap, and the grill assigns each card all three where relevant:

| Signal | Question it answers | Where it lives |
|---|---|---|
| **Function Tag** | what does the card mechanically *do*? (`draw`, `search`, `gust`, `heal`…) | shipped `card_functions.json` (already in the dump) |
| **Role** | what does *this deck* use it for? (`win_condition`, `accel_source`, `starter`, `tutor`…) | `Strategy.roles` you author |
| **CardStat** | structural fact (HP, weakness, prize, cost, stage) | engine, in the dump |

A Function Tag is universal and already given; a **Role is your editorial decision** about intent.
Most of Phase 3 is assigning Roles and discovering where the deck's intent diverges from the
generic behaviour the tags already trigger.

## Per-category question banks

### Main attacker(s) / win-condition line

- What's the **payoff attack**, its cost, and its damage? What does it OHKO / 2HKO in the meta?
- When is the Line **online**? Cheapest attack cost, or does the deck wait for the big attack?
  (Sets `Ready(energy=…)`; the engine defaults to the cheapest attack — confirm that's intended.)
- What's the **fastest legal path** to the payoff (which tutors/accelerators, in what order)?
- Is the attacker a **multi-prize liability** (ex/Mega-ex)? When is it safe to bench it early vs.
  keep it in hand? (Interacts with `dont-bench-multiprize`.)
- After a KO of the attacker, what's the **successor plan**? Do you run multiple copies / a backup?
- Which attack do you pick when **both are legal** — the cheap snipe or the big hit? What board
  states flip that choice?

### Supporting Pokémon (openers, accelerators, walls, pivots)

- What's its **job** — open the active, accelerate energy, wall while you set up, pivot, snipe?
- Does it have an **opener** ability (start from hand)? Does that keep an otherwise-mulligan hand?
- If it accelerates, **where does the energy go** (bench/active, which targets) and how fast?
- Is it a **stall/wall** that should decline to attack to buy tempo? (`stall` play-role.)
- When does it **stay active** vs. retreat/get replaced?

### Supporters (one per turn — the scarcest action)

- It's your **once-per-turn** Supporter — so what's the **priority order** when you hold several?
- Is it a **draw refill**, a **tutor**, **disruption**, or a **clutch defensive** play?
- Which to play on a **fresh hand** vs. a **flooded** hand vs. a **dead** hand?
- Any with a **hold condition** (e.g. heal that bounces energy — play only when the active is
  doomed; `clutch_heal`)? Pin the exact trigger.
- Does any **rush-evolve** (collapse two setup turns into one)? When is that worth the card?

### Items (unlimited per turn — sequencing matters most)

- **Sequencing within a turn**: bench-fill and deck-thinning first (raises later draw quality), then
  tutors, then irreversible plays? Confirm the ladder for this deck.
- Search items: **what do you fetch** in priority order, and when does the priority flip (energy-
  starved → fetch energy over the wincon; wincon already in play → fetch the next piece)?
- Disruption items (e.g. hammers): **spam early** or **hold for a key energy**? Coin-flip ones —
  how much do you rely on them?
- Recovery: **what comes back first** from the discard, and at what point in the game?
- Tools: which Pokémon wears it, and what breakpoint does it cross (e.g. +HP to survive an OHKO)?
- **ACE SPEC** (CardData `aceSpec` — one per deck, immense power → restricted): grill it thoroughly
  and on its own. It's singular and usually irreplaceable (no second copy; often not recoverable),
  so the doctrine is *when* to deploy the single copy for maximum impact, not just *where* — don't
  fritter it. The dump flags it `[ACE SPEC]`; treat that flag as "stop and design this carefully."

### Energy

- Count and types — is the deck **energy-tight**? How many attachments to go online?
- **Special energy** behaviour (discard-at-EOT, type-conditional output) — what does it enable, and
  what's the discipline (don't waste it on a benched/can't-attack target; reserve for the wincon)?
- Is any energy a **finite, non-recyclable** resource (few copies, can't be recovered from discard)?
  If so, when do you **spend vs conserve** it, and what's the cheaper sustainable alternative? (This
  vein — e.g. "Ignition is a finite burst; default to Water" — is often the deck's central decision.)
- Manual attach vs. **acceleration** — which targets get the manual drop when both want energy?

### Cross-card: combos, sequencing, opening hands, plan mapping

- **Combos**: name each multi-card engine (A fetches B which powers C). What's the minimum hand to
  execute it? What breaks it?
- **Opening hands**: the dream open; the median open; the survivable-but-bad open. Mulligan keeps —
  what's the worst hand you *keep*? Going first vs. second — what changes?
- **Sequencing ladder**: write the default order of operations for a developing turn, and the
  carve-outs that reorder it (an ability that needs energy first; deck-thinning before drawing).
- **Plan mapping**: define SETUP / RACE / STABILIZE / CLOSE for this deck — the board reads that
  flip between them, and what each mode prioritises. RACE when the Line is `ready`; what does
  STABILIZE look like when you're behind on prizes?

## Turning answers into the doc

Each resolved card → a card entry in STRATEGY.md (Role, usage, sequencing, combos, anti-patterns) +
its General-Strategy disposition. Each resolved cross-card pattern → either a disposition on an
existing general Hypothesis or a drafted new deck Hypothesis (id + rationale + trigger sketch + seed
weight). Keep the **progress checklist** current so the session is resumable.
