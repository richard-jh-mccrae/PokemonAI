<!-- Strategy Proposal queue — matchup-brief proposal from the Dragapult ex counterplay doctrine.
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md
Producer: matchup-genie (ADR-0046) — proposes only; /update-strategy authors src/common/scouting/briefs/dragapult_ex.json behind the brief-validator gate. -->

## dragapult-ex-counterplay-brief
- id: dragapult-ex-counterplay-brief
- source: matchup-genie
- target_layer: matchup-brief
- for: opponent:Dragapult ex
- candidate_signal: Brief fields — opponent_properties {opp_tempo, opp_spreads_bench (NEW), opp_item_locks (NEW)} + threats[] + targets[]. Two keys (`opp_spreads_bench`, `opp_item_locks`) are newly minted in src/common/scouting/opponent_properties.json with consumer:"unwired" — forward contracts; each needs a Board field + lever wired before it moves play. `opp_tempo` + the `fragile_preevo`/`prize_liability` target roles ride existing wiring (fragile_preevo lever acts on ship; opp_tempo is intel-only/unwired).
- verification_contract: brief-validator
- provenance: docs/matchups/dragapult_ex.md (locked doctrine, 2026-07-09; §3 seam map, §4 threats/targets, §7 decisions D1–D3)
- status: open

**Spec (authoring spec — the locked Brief content; author the JSON from this, do NOT hand-invent fields):**

**slug / label / covers** — from `data/meta/decks/index.json`, copy `covers` VERBATIM (routes every variant to this one Brief):
- slug: `dragapult_ex`
- label: `Dragapult ex`
- covers: `Dragapult ex`, `Dragapult ex / Dusknoir`, `Dragapult ex / Dusknoir / N’s Zoroark ex`

**tempo:** `midrange` (Stage-2 wincon, online turn 2–3 via Rare Candy + heavy search; no attack before ~T2 and no energy accel beyond Crispin; durable-grindy once online).

**summary (objective, deck-neutral):** Beat Dragapult ex by racing the roots it can't protect — NOT by out-grinding the wall. The Active Dragapult is a 320-HP / no-weakness / **Tera** body you usually can't OHKO and **can't even touch on the Bench** (Tera ex take no attack damage while Benched — engine-enforced, rulebook Appendix 6), so don't spend chip on it; it's only a **2-prize** ex, an even trade when you *can* reach 320. Instead: (1) race the fragile pre-evos — KO Dreepy (70) / Drakloak (90) before they become the wall, clearing multiples to beat the 4-4-3; (2) gust the **non-Tera** support ex (Fezandipiti / Latias / Meowth) for clean 2-prize swings that also strip recovery, pivot, and toolbox; (3) starve the spread by keeping our Bench thin and high-HP — Phantom Dive's 6 counters hit the **Bench only** (never the Active) and it's a **flat 200** with no boost, so a >~200-HP Active dodges the OHKO; (4) tax the low energy (only 8 basic; Phantom Dive needs exactly one Fire + one Psychic) with denial/removal, and sequence our Items before Budew's one-turn lock, then delete the 30-HP Budew. Close fast to starve Fezandipiti's reactive draw-3. NOTE the Dusknoir/N’s Zoroark ex variants (in `covers`) add damage-counter manipulation that amplifies the spread — this base list runs neither, so card-level intel below grounds only in the base build.

**opponent_properties:**
- `opp_tempo: "midrange"` — registered key (unwired/intel). The race clock: online T2–3, no pre-T2 attack, Crispin-only accel.
- `opp_spreads_bench: true` — **NEW key (D1), registered consumer:"unwired"** — forward contract, needs a Board field + lever wired before it affects play. Rationale: Phantom Dive places 6 free damage counters on the opponent's **Bench** every turn and converts the accumulated chip into multi-prize turns (next Phantom Dive / Fezandipiti Cruel Arrow) — presenting a wide/fragile Bench feeds it; posture = keep Bench thin + high-HP; the threat is to the Bench, not the Active.
- `opp_item_locks: true` — **NEW key (D2), registered consumer:"unwired"** — forward contract, needs a Board field + lever wired before it affects play. Rationale: Budew Itchy Pollen locks our Item cards for one turn (taxes Ball/Candy/Poffin engines); posture = sequence our Items before the lock, lean on Supporters/Abilities the locked turn, snipe the 30-HP body to stop repeats.
- **`opp_is_engine_dependent`: deliberately NOT set (false).** HIGH-BAR wired key (~4% wrong-assertion cost). Consistency is distributed across a redundant trainer engine (Ultra Ball / Poffin / Poké Pad / Brock's / Crispin / Lillie's) + banked-on-entry Meowth + Drakloak dig — no single Pokémon whose removal strangles setup. Do not assert.

**threats** (attackers/disruption to respect — card + why):
- `Dragapult ex` — the wincon and turn-clock: Phantom Dive ({R}{P}, 2 energy) = flat 200 to the Active + 60 spread (6 counters) on our Bench every turn, taking prizes on two axes. 320 HP, NO weakness, **Tera → a benched copy takes no attack damage** (can't be sniped/spread on the Bench), 2 prizes. Near-impossible to OHKO but only 2 prizes and a flat 200 with no innate boost — out-HP the 200 (a >~200-HP Active survives), deny it at the pre-evo stage, and even-trade the tank only when you can actually reach 320. Do NOT waste chip on the Active or removal on a benched copy.
- `Fezandipiti ex` — recovery engine + finisher: Flip the Script draws 3 once/turn after any of their Pokémon are KO'd (refuels after trades); Cruel Arrow (CCC, 0 → 100 to ANY Pokémon, ignores Bench W/R) converts spread-softened bodies into extra prizes, but at 3 energy (deck runs only 8) it's situational, not an every-turn clock. Respect the draw-3 refuel; close fast to starve it. (Also a prize_liability target.)
- `Latias ex` — Eon Blade ({P}{P}{C}, 200) is a one-off punch that OHKOs ~200-HP bodies then self-locks Latias next turn; Skyliner gives all their Basics free retreat (free pivots when energy-tight or Budew-locked). Respect the single Eon Blade window — don't leave a ≤200-HP body Active into a powered Latias. (Also a prize_liability target.)
- `Budew` — Itchy Pollen (no energy, 10 dmg) locks us out of ALL Item cards next turn, kneecapping item-reliant setup while Dragapult assembles. 30 HP, retreat 0, Fire weak, re-usable if left alive. Sequence Items before the lock, lean on Supporters/Abilities the locked turn, then OHKO the 30-HP body to deny repeat locks.

**targets** (disrupt / snipe — card + role + why; roles ∈ fragile_preevo / prize_liability / engine):
- `Dreepy` — **fragile_preevo** — 70-HP Basic base of the wincon line, 1 prize, NOT Tera (valid target). KO/snipe it while still a Basic before Rare Candy/evolution turns it into the 320 wall — tempo denial, not prize value. Clear multiples to beat the 4-4-3 redundancy; 70 HP dies to most single hits and to spread.
- `Drakloak` — **fragile_preevo** — 90-HP Stage 1, 1 prize, NOT Tera. Also the deck's real dig engine (Recon Directive: look top 2, take 1) AND the rebuild hop for a KO'd Dragapult, so gust/snipe strips consistency + delays the wall in one shot. No weakness but low HP — dies to a ~90 snipe or two spread hits.
- `Fezandipiti ex` — **prize_liability** — benched 2-prize ex, 210 HP, FIGHTING weak, NOT Tera. Gust it Active and KO (doubled by Fighting) to bank 2 cheap prizes AND delete the recovery draw-3 + Cruel Arrow finisher at once. Not disabled by their own Watchtower (it's Darkness, not Colorless).
- `Latias ex` — **prize_liability** — passive 2-prize bench-sitter (Skyliner enabler), 210 HP, DARKNESS weak, NOT Tera. Gust+KO costs them nothing defensively while banking 2 prizes and stripping their pivot mobility. Skyliner is Psychic, so Colorless-only ability locks (incl. their own Watchtower) don't stop it — you must remove the body.
- `Meowth ex` — **prize_liability** — 170-HP 2-prize ex, FIGHTING weak, Colorless. Last-Ditch Catch tutors a Supporter on entry but the value is **banked on entry (can't be denied after it lands)**, so don't treat it as a strangleable engine — punish the soft 170-HP body: gust/snipe and KO in one turn (before Tuck Tail CCC bounces it to hand to re-use). Its own ability is shut off by their Watchtower (Colorless).
- *(No `engine`-role target: consistency is distributed + banked; there is no single strangleable engine — hence `opp_is_engine_dependent` is false. Drakloak's engine-ness is folded into its fragile_preevo why.)*

**sources** (for the Brief `sources[]`):
- Three decks to beat Dragapult ex — Stéphane Ivanoff — https://alexschemanske.substack.com/p/three-decks-to-beat-dragapult-ex
- Dragapult: Phantom Diving to Victory — Going Second (Spenser Gow) — https://goingsecond.substack.com/p/dragapult-phantom-diving-to-victory
- Dragapult ex Counters? — Pokémon Forums — https://community.pokemon.com/en-us/discussion/14286/dragapult-ex-counters
- Dragapult ex deck guide — PokeBeach — https://www.pokebeach.com/?p=319761
- Enter the Dragapult: the new format and its top decks — PokeBeach — https://www.pokebeach.com/2026/05/enter-the-dragapult-the-new-format-and-its-top-decks
- Fezandipiti ex (SFA 38) / Latias ex (SSP 76) / Meowth ex (POR 62) — Limitless TCG
- engine ground truth — data/EN_Card_Data.csv + dump_deck.py + docs/rules.md (Tera bench-immunity Appendix 6, weakness ×2, damage order)

**Apply notes for update-strategy:**
- Copy `covers` verbatim from index.json (the `N’s` uses a curly apostrophe U+2019). Expect NO validator warn: covers matches index.json and no other shipped Brief covers these strings.
- Every threat/target card is in the base deck list (validator hard-fails otherwise): Dragapult ex, Fezandipiti ex, Latias ex, Budew, Dreepy, Drakloak, Meowth ex — all present.
- Both new opponent_properties keys are already registered in `src/common/scouting/opponent_properties.json` (consumer:"unwired") — validator will not warn on unknown keys. Call out in the diff that each is an inert forward contract (needs consumer wiring before it affects play).
- Run `python .claude/skills/matchup-genie/scripts/validate_brief.py dragapult_ex` + `python -m pytest tests/ -q` before the diff. Commit message begins with `matchup: `.
