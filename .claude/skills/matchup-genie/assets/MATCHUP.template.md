# vs <Archetype label> — Counterplay Doctrine

> Phase-A deliverable of `/matchup-genie`. The **objective** game-plan against ONE opponent archetype;
> the machine `src/common/scouting/briefs/<slug>.json` Brief is generated from this **after sign-off**
> (ADR-0027). Shared across all our decks — write deck-neutral; each agent relativizes it.

**Slug:** `<slug>` · **Status:** `drafting | locked | shipped` · **Last grilled:** <date> · **Author:** matchup-genie + <user>
**Covers** (from `data/meta/decks/index.json`): `<archetype string>`, `<variant>`, … — every variant routes to this one Brief.

## Progress checklist (resumability — keep current)

- [ ] Phase 0 facts dumped (`dump_deck.py --deck-dir data/meta/decks/<slug>`) + `covers` read from index.json
- [ ] Phase 1 how-it-wins confirmed
- [ ] Phase 2 counterplay research synthesised + confirmed
- [ ] Phase 3 weakness grill: `<n>/<total>` seams locked
- [ ] Phase 4 Brief-field reconciliation complete (opponent_properties + threats + targets)
- [ ] Phase 5 signed off → Phase B authorised

Open seams to grill: <list>. Open questions: <list>.

## 1 · How it wins

- **Win condition:** <how the opponent takes 6 prizes; prize math given Mega-ex=3 / ex=2 / else=1>
- **Line(s):** <basic → payoff path(s)> · **online at:** <energy / turn the payoff comes up>
- **Main attacker(s):** <the threats — payoff + secondary attackers>
- **Engine (draw/search):** <the consistency core> · **Acceleration:** <…> · **Disruption:** <what it does to US>
- **Tempo:** <fast / midrange / slow — when it starts taking prizes; the race clock>
- **User context:** <anything the user supplied>

## 2 · Counterplay research (cited)

<How the archetype wins per the web AND how it is beaten: known bad matchups, disruption that hurts it,
the tempo window before it stabilises, tech that answers it. Mark thin sourcing as an assumption. Cite
every source.>

**Key-card findings** (its threats + engine — how each functions and how to neutralize it):
- **<Card>:** <what it does + how we blunt it (gust / snipe / disrupt / out-tempo)>

**Web-vs-engine conflicts surfaced:** <guide claims the engine facts contradict — or "none">

**Sources:** <name — URL> · <name — URL>

## 3 · Exploitable seams (the weakness map)

One block per seam. Each must resolve to a Brief field (an `opponent_properties` key and/or a threat/target).

### <Seam name, e.g. "Engine-dependent setup">
- **Weakness:** <the concrete vulnerability, grounded in the dump/research>
- **Exploit:** <what WE do about it — objective, deck-neutral>
- **Maps to:** <`opponent_properties.<key>` = <value> | `target: <Card>` role `<role>` | `threat: <Card>`>

## 4 · Threats & targets (objective card-level intel)

- **Threats** (attackers to respect): `<Card>` — <why it's dangerous / what it OHKOs>
- **Targets** (what to disrupt or snipe), by role:
  - `fragile_preevo`: `<Card>` — <low-HP pre-evo of the wincon; snipe before it evolves>
  - `prize_liability`: `<Card>` — <ex/Mega-ex; denies/gives multiple prizes>
  - `engine`: `<Card>` — <consistency Pokémon; gust+KO to strangle setup>

## 5 · Objective counterplay summary

<2-4 sentences, deck-neutral: the posture that beats this deck — race it / stabilize then grind /
disrupt its engine / deny the donk. This is what each of our agents relativizes to its own cards.>

## 6 · Brief preview (pre-JSON — filled in Phase 4, emitted in Phase 6)

```
opponent_properties = { "<key>": <value>, ... }   # each from assets/opponent_properties.json (flag new keys)
threats             = [ { "card": "<name>", "why": "<…>" }, ... ]
targets             = [ { "card": "<name>", "role": "<fragile_preevo|prize_liability|engine>", "why": "<…>" }, ... ]
```

## 7 · Open questions / deferred

<New opponent-property keys minted (need consumer wiring), unresolved reads, or claims waiting on evidence.>
