# Ledger corpus dashboard

Generated 2026-08-20T12:40:27.747372+00:00 at `3c2d4399bbf4`.

| deck | graded | agrees | agreement | ungraded | gap-affected decisions | fallbacks |
|---|---|---|---|---|---|---|
| dragapult_ex | 54 | 9 | 16.7% | 0 | 44 | 0 |
| mega_lucario | 70 | 25 | 35.7% | 0 | 30 | 0 |
| mega_starmie | 347 | 108 | 31.1% | 0 | 233 | 0 |

**Generality floor (worst deck): 16.7%**

## Misses (the triage queue: read the rationale first)

### dragapult_ex `83686860-11` (Discard, missed_win)

- Ledger chose `[1, 2]` Basic {R} Energy, Basic {D} Energy
- ruling was `[0]` Lillie's Determination
- rationale: Discard a fire energy when we otherwise have no energy is a bad trade.
- priced -0.0655 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[2,{"id":2,"playerIndex":1}]]]', '[1,{"playerIndex":1,"type":3},[[2,{"id":7,"playerIndex":1}]]]'))
- priced -0.1095 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[2,{"id":1227,"playerIndex":1}]]]', '[1,{"playerIndex":1,"type":3},[[2,{"id":7,"playerIndex":1}]]]'))
- priced -0.1095 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[2,{"id":1080,"playerIndex":1}]]]', '[1,{"playerIndex":1,"type":3},[[2,{"id":7,"playerIndex":1}]]]'))

### dragapult_ex `83686860-13` (Main, wasted_resource)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[1]` End turn
- rationale: CRITICAL: We just discarded two energy to fetch a drakloak for next turn, then immediatly shuffle our hand away with Lillie's. thus, we completely wasted two energies AND an ultra ball for zero gain.
- priced +0.3482 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### dragapult_ex `83686860-29` (Main, wasted_resource)

- Ledger chose `[7]` End turn
- ruling was `[0]` Evolve Drakloak → Dreepy (bench 1 · 70/70 · 1⚡)
- rationale: CRITICAL: better the fully charge single wincon line then spread out energy
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1450 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":2,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":170,"id":1071,"maxHp":170,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1450 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":2,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[5],"energyCards":[{"id":5,"playerIndex":1}],"hp":70,"id":119,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `83686860-35` (ToHand, wasted_resource)

- Ledger chose `[0]` (card)
- ruling was `[1]` (card)
- rationale: CRITICAL: must never select Cinderace, its pointless outside of opening turn.
- priced +0.0910 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[12,{"id":666,"playerIndex":1}]]]',))
- priced +0.0900 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[12,{"id":1080,"playerIndex":1}]]]',))

### dragapult_ex `83686860-45` (Main, wasted_resource)

- Ledger chose `[8]` End turn
- ruling was `[4]` Attach Basic {R} Energy → Drakloak (bench 1 · 90/90 · 1⚡)
- rationale: CRITICAL: never ever ever attach invalid energy to our wincons. they require one fire and one psychic and now you have attached two psychics. must first verify pokemons energy needs, then attach correct energy.
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0170 ActionIdentity(kind='ability', parts=('[1,{"type":10},[[5,{"appearThisTurn":false,"energies":[5],"energyCards":[{"id":5,"playerIndex":1}],"hp":90,"id":120,"maxHp":90,"playerIndex":1,"preEvolution":[{"id":119,"playerIndex":1}],"tools":[]}]]]',))
- priced -0.0170 ActionIdentity(kind='ability', parts=('[1,{"type":10},[[5,{"appearThisTurn":false,"energies":[2],"energyCards":[{"id":2,"playerIndex":1}],"hp":90,"id":120,"maxHp":90,"playerIndex":1,"preEvolution":[{"id":119,"playerIndex":1}],"tools":[]}]]]',))

### dragapult_ex `85045840-10` (Main, wasted_resource)

- Ledger chose `[3]` End turn
- ruling was `[2]` Attach Basic {P} Energy → Dreepy (active · 70/70)
- rationale: Gusting up the Snover doesnt help us here. save boss's orders for a time when it is actually valuable.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1440 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":5,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1585 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))

### dragapult_ex `85045840-12` (Main, wasted_resource)

- Ledger chose `[2]` End turn
- ruling was `[1]` Attach Basic {P} Energy → Dreepy (active · 70/70)
- rationale: Nothing in our hand that we wish to discard, therefor should save ultra ball for another occasion.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1440 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":5,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1585 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))

### dragapult_ex `85045840-14` (ToHand, wasted_resource)

- Ledger chose `[2]` Dreepy
- ruling was `[1]` Budew
- rationale: CRITICAL: You discarded our Drakloak (stage 1) in exchange for a Dragapult (stage 2). nonsensical.
- priced +0.0430 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":119,"playerIndex":0}]]]',))
- priced +0.0430 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":120,"playerIndex":0}]]]',))
- priced -0.0070 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":140,"playerIndex":0}]]]',))

### dragapult_ex `85045840-6` (Main, wasted_resource)

- Ledger chose `[5]` End turn
- ruling was `[2]` Play Poké Pad
- rationale: The Kyogre has a single energy, however its attack requires that the opponent has energy in its discard pile to do damage. thus this kyogre cannot hurt us, it is no threat. therefor we should save the crushing hammer for another opportunity.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0115 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1152,"playerIndex":0}]]]',))
- priced -0.1215 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))

### dragapult_ex `85045840-8` (Main, slow_setup)

- Ledger chose `[4]` End turn
- ruling was `[1]` Play Poké Pad
- rationale: This is a note for the match strategy of this deck. Our goal is to setup our bench and draw engines as quickely as possible. The Pokepad can fetch a drakloak while the ultraball can fetch a dunsparce (discard crushing hammer and energy). id discard energy over boss orders because we can recycle it with a night stretcher and because we have trainers like Crispin for energy acceleration. With such a first turn, our second turn will allow for Drakloak's extra card draw PLUS dudunspace's 3 card draw at the sacrifice of an ultra ball and an energy. 
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0115 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1152,"playerIndex":0}]]]',))
- priced -0.1440 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":5,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `85046350-21` (Main, misattachment)

- Ledger chose `[5]` End turn
- ruling was `[1]` Attach Basic {D} Energy → Dreepy (active · 70/70)
- rationale: CRITICAL: dunspace and dudunspace are not meant to be powered up with energy. only do so if no other options and we are desperate. this line of pokemon is a draw engine 99%

RE-RULED 2026-07-29 (user): correct moves [2] -> [1] — attach the {D} to the ACTIVE Dreepy, not the benched one. The original ruling (don't power up the Dunsparce/Dudunsparce DRAW ENGINE) stands and is unchanged; what changes is WHICH Dreepy. The line is: attach {D} to the Active Dreepy, retreat it into Budew (the retreat cost DISCARDS that {D}, rules.md L89), evolve Drakloak onto the benched Dreepy that already holds the {R}, then Itchy Pollen for the Item lock.

WHY {D} AND WHY THE ACTIVE. {D} appears in NO typed cost this deck pays — Bite / Dragon Headbutt / Phantom Dive are all {R}{P}, Mind Bend is {P}+colourless — so it only ever pays a colourless slot and is the deck's one fungible Energy. Spending it to pay a retreat costs nothing the win condition needs; attaching it to the benched Dreepy instead parks a dead card on a wincon body. Engine-verified that this is unpunished: retreat does NOT trigger the in-play Risky Ruins ('puts a Basic non-{D} Pokemon onto their Bench'), because cgpy calls `_after_benched` only from the play-from-hand and put-from-deck paths, never from `_do_switch` — matching the rulebook, which words retreat as a SWITCH (L142) and reserves 'put onto your Bench' for playing from hand (L109/121).

OWNER #165 (Turn Planner). By ADR-0070 amendment J's test the attach is individually worthless — {D} pays neither {P} nor {R}{P}, so it does nothing for the Active Dreepy's own attacks — and pays only as step 1 of attach -> retreat -> promote -> lock: a Maneuver. It needs NO new heuristic: once the planner commits 'this body retreats this turn', Energy attached to it is SPENT rather than banked, its build value is 0, and the existing attach marginal prefers the most fungible card by itself.

NOTE this frame is the one the DELETED f21 energized-line guard was named after ('a wincon Line body is already being energized -> develop it, don't retreat for the lock'). This re-ruling says the retreat-for-the-lock is right ON f21 ITSELF, which undercuts that guard at its own source — independently of the paired-A/B result on the blanket removal.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0625 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":7,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.0625 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":7,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":305,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `85046350-31` (ToActive, slow_setup)

- Ledger chose `[2]` Dunsparce (bench 3 · 70/70 · 1⚡)
- ruling was `[1]` Budew (bench 2 · 30/30)
- rationale: CRITICAL: avoid promoting dreepy/drakloak/dragapult line until its fully evolve and fully powered. until its fully powered, we perfer drakloak for its draw engine ability. also, we wanna item lock our opponent when we can. 
- priced +0.0520 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[7],"energyCards":[{"id":7,"playerIndex":0}],"hp":70,"id":305,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0440 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":30,"id":235,"maxHp":30,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0320 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[2],"energyCards":[{"id":2,"playerIndex":0}],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `85046350-32` (Main, wasted_resource)

- Ledger chose `[4]` End turn
- ruling was `[1]` Evolve Drakloak → Dreepy (active · 70/70 · 1⚡)
- rationale: CRITICAL: We are about to KO their active, so why play Crushing hammer first?
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1920 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1120,"playerIndex":0}]]]',))
- priced -0.1970 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))

### dragapult_ex `85046350-45` (Main, sequencing_error)

- Ledger chose `[1]` Play Lillie's Determination
- ruling was `[2]` Play Poké Pad
- rationale: CRITICAL: Play pokepad before lillies as to get a new pokemon on our bench first.
- priced +0.4069 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0400 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1152,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### dragapult_ex `85046350-79` (Main, wasted_resource)

- Ledger chose `[0]` Play Night Stretcher
- ruling was `[4]` Play Boss’s Orders
- rationale: CRITICAL: We know that we have no pokemon in deck that we can fetch with buddy-buddy poffin, therefor save it in hand for eventual ultra ball discard
- priced +0.0275 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1097,"playerIndex":0}]]]',))
- priced +0.0166 ActionIdentity(kind='attack', parts=('[0,{"attackId":154,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### dragapult_ex `85046350-81` (Main, wrong_supporter)

- Ledger chose `[0]` Play Night Stretcher
- ruling was `[2]` Play Boss’s Orders
- rationale: I would have gusted up their Roserade, attacked it with Phantom Dive, and KO'd it and the Gible for 2 prize cards. We know that we will need to face off against the Garchomp eventually, but atleast KOing their Roserade will reduce the dmg delt by the Garchomp. See Roserade's ability, Cheer on to Glory.
- priced +0.0275 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1097,"playerIndex":0}]]]',))
- priced +0.0166 ActionIdentity(kind='attack', parts=('[0,{"attackId":154,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### dragapult_ex `85046350-85` (Main, misattachment)

- Ledger chose `[0]` Play Night Stretcher
- ruling was `[3]` Attach Basic {P} Energy → Dreepy (bench 2 · 50/70 · 1⚡)
- rationale: Better to fully energize a single Dreepy/Drakloak/Dragapult then to spread out the energies.
- priced +0.0275 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1097,"playerIndex":0}]]]',))
- priced +0.0166 ActionIdentity(kind='attack', parts=('[0,{"attackId":154,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### dragapult_ex `85785609-22` (ToHand, misattachment)

- Ledger chose `[0]` Basic {R} Energy
- ruling was `[3]` Basic {D} Energy
- rationale: I would have fetched the darkness energy to attach to the Munkidori. then use its ability to move damage from dreepy to opponents dreepy
- priced +0.0500 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":2,"playerIndex":0}]]]',))
- priced +0.0500 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":5,"playerIndex":0}]]]',))
- priced +0.0305 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":7,"playerIndex":0}]]]',))

### dragapult_ex `85785609-4` (SetupBenchPokemon, wasted_resource)

- Ledger chose `[]` 
- ruling was `[0]` Munkidori
- rationale: This is odd, it shows that to play Munkidori is the only option, though i know the rules do not require playing all basic pokemon to the bench at startup.

Here we do not want to bench this second Munkidori. with this deck, we typically only ever need a single Munkidori in play. this second copy is a perfect fodder for Ultra Ball.

### dragapult_ex `85785609-82` (Main, slow_setup)

- Ledger chose `[6]` End turn
- ruling was `[1]` Evolve Drakloak → Dreepy (active · 30/70 · 2⚡)
- rationale: be more aggresive here. we could have KO'd opponents active by evolving our active dreepy, using Crispin to fetch and attach Darkness energy to Munkidori then using its ability to shift 20 dmg to opponents active, then attacking with Dragon Headbutt (after using Recon Directive.)
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0153 ActionIdentity(kind='attack', parts=('[0,{"attackId":151,"type":13},[]]',))
- priced -0.1298 ActionIdentity(kind='evolve', parts=('[0,{"type":9},[[2,{"id":120,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[5,2],"energyCards":[{"id":5,"playerIndex":0},{"id":2,"playerIndex":0}],"hp":30,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `85786096-24` (Main, slow_setup)

- Ledger chose `[6]` End turn
- ruling was `[0]` Attach Basic {R} Energy → Fezandipiti ex (active · 210/210)
- rationale: CRITICAL: Our matchup posture should know that our opponent only has these three Staryu's as basics which can be benched after match setup, thus this stadium only hurts us.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1945 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":2,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":210,"id":140,"maxHp":210,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1945 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":2,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `85786096-25` (Main, slow_setup)

- Ledger chose `[5]` End turn
- ruling was `[0]` Attach Basic {R} Energy → Fezandipiti ex (active · 210/210)
- rationale: CRITICAL: Our Dreepy doesnt need energy just yet. We should attache to Fez, retreat, promote Budew, then item lock with Itchy Pollen
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1945 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":2,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":210,"id":140,"maxHp":210,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1945 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":2,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `85786096-70` (Main, slow_setup)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[2]` Play Crispin
- rationale: CRITICAL: Our active Dragapult needs an energy, thus Crispin. Could then have also attached a psychic energy to the benched Drakloak
- priced +0.1862 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1220 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1198,"playerIndex":0}]]]',))

### dragapult_ex `85786096-86` (AttachTo, slow_setup)

- Ledger chose `[]` 
- ruling was `[1]` Basic {P} Energy
- rationale: CRITICAL: WHy the fuck would you attach darkness energy to our dragon line that needs specifically fire and psychic???
- priced +0.0000 ActionIdentity(kind='decline', parts=())
- priced +0.0000 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":7,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":5,"playerIndex":0}]]]',))

### dragapult_ex `86089120-14` (Main, wrong_supporter)

- Ledger chose `[4]` End turn
- ruling was `[1]` Attach Basic {P} Energy → Dreepy (active · 70/70)
- rationale: Gusting up their main attacker only helps them. IF you want to gust, gust up their non-attacking supporter pokemone, Lunatone
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0850 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":7,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.0960 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":5,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `86089638-18` (Main, misattachment)

- Ledger chose `[10]` End turn
- ruling was `[8]` Attach Basic {P} Energy → Dreepy (bench 1 · 70/70 · 1⚡)
- rationale: power up our main line. meowth IS just a wall for now
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0685 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))
- priced -0.1105 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":7,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":170,"id":1071,"maxHp":170,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `86090164-17` (Main, wrong_supporter)

- Ledger chose `[5]` Play Lillie's Determination
- ruling was `[0]` Attach Basic {P} Energy → Dreepy (active · 70/70)
- rationale: 
- priced +0.1679 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.2145 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":5,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `86090164-40` (Main, wrong_supporter)

- Ledger chose `[1]` Attack with Dragon Headbutt
- ruling was `[0]` Evolve Dudunsparce → Dunsparce (bench 4 · 70/70)
- rationale: CRITICAL: Important to get our Dudunspace online if able such to draw 3.
- priced +1.2783 ActionIdentity(kind='attack', parts=('[1,{"attackId":152,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.4675 ActionIdentity(kind='evolve', parts=('[1,{"type":9},[[2,{"id":66,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":305,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `86090164-52` (Main, bad_retreat)

- Ledger chose `[24]` Attack with Dragon Headbutt
- ruling was `[1]` Evolve Dudunsparce → Dunsparce (bench 4 · 70/70)
- rationale: CRITICAL: Dont retreat our active that can KO their active, this wastes energy.
- priced +1.3733 ActionIdentity(kind='attack', parts=('[1,{"attackId":152,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0725 ActionIdentity(kind='ability', parts=('[1,{"type":10},[[4,{"appearThisTurn":false,"energies":[5,2],"energyCards":[{"id":5,"playerIndex":1},{"id":2,"playerIndex":1}],"hp":80,"id":120,"maxHp":90,"playerIndex":1,"preEvolution":[{"id":119,"playerIndex":1}],"tools":[]}]]]',))

### dragapult_ex `86090164-67` (Main, bad_retreat)

- Ledger chose `[6]` Attack with Dragon Headbutt
- ruling was `[1]` Evolve Dudunsparce → Dunsparce (bench 4 · 70/70)
- rationale: CRITICAL: This deck is insanely retreat happy. look into this. it keeps retreating our active out that can KO our opponent for a weak pokemon that cannot KO our opponent.
- priced +1.2558 ActionIdentity(kind='attack', parts=('[1,{"attackId":152,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1600 ActionIdentity(kind='ability', parts=('[1,{"type":10},[[4,{"appearThisTurn":false,"energies":[2,5],"energyCards":[{"id":2,"playerIndex":1},{"id":5,"playerIndex":1}],"hp":70,"id":120,"maxHp":90,"playerIndex":1,"preEvolution":[{"id":119,"playerIndex":1}],"tools":[]}]]]',))

### dragapult_ex `86090164-78` (Main, wasted_resource)

- Ledger chose `[1]` Play Lillie's Determination
- ruling was `[]` 
- rationale: CRITICAL: A waste to attach a darkness energy to Dragapult
- priced +1.2383 ActionIdentity(kind='attack', parts=('[1,{"attackId":153,"type":13},[]]',))
- priced +0.0157 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### dragapult_ex `86090676-18` (Main, wasted_resource)

- Ledger chose `[4]` End turn
- ruling was `[]` 
- rationale: CRITICAL: Look into this Crispin play. i dont believe that the agent fetched 2 energies like Crispin allows. Should have used this card to attach two energies to Fexandipiti, prepaing for a 100 dmg attack next turn.
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1300 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":5,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":210,"id":140,"maxHp":210,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1790 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1198,"playerIndex":1}]]]',))

### dragapult_ex `86090676-39` (Main, wasted_resource)

- Ledger chose `[5]` End turn
- ruling was `[2]` Attach Basic {P} Energy → Dreepy (bench 2 · 70/70)
- rationale: CRITICAL: you just attached a 4th energy to a pokemon that requires only 3 to attack. what the fuck. this should be covered by our features. this is nuts
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0970 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":5,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":305,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.0970 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":5,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `86091435-119` (Main, wrong_supporter)

- Ledger chose `[5]` Ability: Drakloak (bench 3 · 90/90 · 1⚡)
- ruling was `[2]` Play Night Stretcher
- rationale: CRITICAL: The opponents active is their main threat that we want to KO. it has only a single energy while we have full health and full energy. attack the damn thing!

I say play Night Stretch, fetch fire energy, attach it to benched Dragapult. Use drakloaks's ability, us ulta ball to get dundunspace (discard buddy buddy poffin and Munkidori), use dudunspaces ability. eventually attack with Phanton Dive, KO Relicanth.
- priced +1.0179 ActionIdentity(kind='attack', parts=('[0,{"attackId":154,"type":13},[]]',))
- priced +0.0205 ActionIdentity(kind='ability', parts=('[0,{"type":10},[[5,{"appearThisTurn":false,"energies":[7],"energyCards":[{"id":7,"playerIndex":0}],"hp":90,"id":120,"maxHp":90,"playerIndex":0,"preEvolution":[{"id":119,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### dragapult_ex `86091435-13` (Main, wasted_resource)

- Ledger chose `[4]` End turn
- ruling was `[3]` Retreat
- rationale: wasted Boss's Orders here. doesnt really make a difference
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1030 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))
- priced -0.2580 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))

### dragapult_ex `86091435-20` (Main, wasted_resource)

- Ledger chose `[1]` End turn
- ruling was `[0]` Retreat
- rationale: CRITICAL: Should retreat into Budew, then attack to item lock
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.2580 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))

### dragapult_ex `86091435-30` (Main, wasted_resource)

- Ledger chose `[2]` End turn
- ruling was `[0]` Ability: Drakloak (active · 90/90 · 2⚡)
- rationale: CRITICAL: Never attach a useless energy to a pokemon ever. this would only be relevant if we planned to retreat, in which we'd immediately discard the darkness energy, which isnt a bad idea, given then we could promote our Budew to item lock our opponent
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0320 ActionIdentity(kind='ability', parts=('[0,{"type":10},[[4,{"appearThisTurn":true,"energies":[2,7],"energyCards":[{"id":2,"playerIndex":0},{"id":7,"playerIndex":0}],"hp":90,"id":120,"maxHp":90,"playerIndex":0,"preEvolution":[{"id":119,"playerIndex":0}],"tools":[]}]]]',))
- priced -0.1850 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))

### dragapult_ex `86091435-35` (Main, sequencing_error)

- Ledger chose `[2]` Ability: Drakloak (active · 90/90 · 2⚡)
- ruling was `[1]` Play Poké Pad
- rationale: RE-RULED 2026-07-26 (user, #167 decision-5 sitting): correct is [1] Play Poké Pad, not [2] Ability. Poké Pad's job in this deck is fetching the 2nd Drakloak (4x in deck, no Rule Box, 1 in play) so a bench Dreepy — both appearThisTurn=False, so legally evolvable — becomes a 2nd Recon Directive body: two digs instead of one. Resolving the DETERMINISTIC tutor first also thins the deck by a known non-{P} card, improving both digs; waiting reveals nothing. Then Recon x2, and branch: on a {P}, attach and evolve the Active for Phantom Dive {R}{P} 200; otherwise retreat the Drakloak (cost 1, discarding the dead {D}), promote Budew and item-lock with Itchy Pollen. ORIGINAL TAG 2026-07-15, superseded but retained as provenance — correct=[2] 'Ability: Drakloak (active · 90/90 · 2⚡)', rationale: "CRITICAL: Always use Drakloak's ability before evolving it." That principle SURVIVES (the line still uses Recon before any evolve); what it got wrong was the first action, because it did not see the Poké Pad → 2nd Drakloak line.
- priced +0.1105 ActionIdentity(kind='ability', parts=('[0,{"type":10},[[4,{"appearThisTurn":false,"energies":[2,7],"energyCards":[{"id":2,"playerIndex":0},{"id":7,"playerIndex":0}],"hp":90,"id":120,"maxHp":90,"playerIndex":0,"preEvolution":[{"id":119,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0280 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1152,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### dragapult_ex `86091435-49` (ToHand, sequencing_error)

- Ledger chose `[1]` (card)
- ruling was `[]` 
- rationale: 
- priced +0.0750 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[12,{"id":1152,"playerIndex":0}]]]',))
- priced +0.0500 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[12,{"id":5,"playerIndex":0}]]]',))

### dragapult_ex `86091435-60` (Main, sequencing_error)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[2]` Attach Basic {P} Energy → Dreepy (active · 70/70)
- rationale: CRITICAL: Attach energy before shuffling. this is definitely a regression of hypothesis and weights
- priced +0.4429 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0835 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### dragapult_ex `86091435-68` (Discard, wasted_resource)

- Ledger chose `[0, 4]` Risky Ruins, Crushing Hammer
- ruling was `[1, 4]` Lillie's Determination, Crushing Hammer
- rationale: CRITICAL: Dont ever discard a Drakloak when it can instead just evolve our active Dreepy, and then use its Recon Directive ability
- priced -0.0825 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1120,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":1260,"playerIndex":0}]]]'))
- priced -0.1265 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1227,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":1260,"playerIndex":0}]]]'))
- priced -0.1265 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1120,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":1227,"playerIndex":0}]]]'))

### dragapult_ex `86091728-12` (Main, sequencing_error)

- Ledger chose `[6]` End turn
- ruling was `[]` 
- rationale: For this turn, we focus on setup. I would evolve active Dreepy to Drakloak, use Recon Directive, playin Cripsin to fetch on darkness and one fire where Crispin bonus attach is fire to active drakloak. then attach for turn psychic to active drakloak. then attack for 70 dmg.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1215 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":5,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1315 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1198,"playerIndex":0}]]]',))

### dragapult_ex `86091728-19` (Main, sequencing_error)

- Ledger chose `[7]` End turn
- ruling was `[3]` Attach Basic {P} Energy → Dreepy (bench 2 · 70/70)
- rationale: We dont need to fetch anything at the moment.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1075 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))
- priced -0.1300 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":7,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":112,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `86091728-43` (ToBench, wasted_resource)

- Ledger chose `[0, 2]` Dunsparce, Budew
- ruling was `[2, 3]` Budew, Dreepy
- rationale: CRITICAL: When searching with buddy buddy, when can see in deck that there is no Dudunspace there, thus its in prize cards, thus dont fetch dunspace. get budew instead
- priced +0.3530 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":235,"playerIndex":0}]]]', '[{"playerIndex":0,"type":3},[[1,{"id":305,"playerIndex":0}]]]'))
- priced +0.2030 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":119,"playerIndex":0}]]]', '[{"playerIndex":0,"type":3},[[1,{"id":305,"playerIndex":0}]]]'))
- priced +0.1280 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":305,"playerIndex":0}]]]',))

### dragapult_ex `86091728-47` (ToHand, wasted_resource)

- Ledger chose `[0]` (card)
- ruling was `[1]` (card)
- rationale: CRITICAL: We could have used Night Stretcher to recycle Drakloak, evolve a dreepy, then use Recond Directive ability.
- priced +0.0750 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[12,{"id":1121,"playerIndex":0}]]]',))
- priced +0.0500 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[12,{"id":1097,"playerIndex":0}]]]',))

### mega_lucario `83661652-19` (Main, wrong_supporter)

- Ledger chose `[2]` Play Lillie's Determination
- ruling was `[0]` Attach Basic {F} Energy → Lunatone (active · 110/110 · 1⚡)
- rationale: Poor use of Boss's Orders. i get that it is a stall tactic, but a poor one. Should have attached energy to Lunatone, played lillie's, eventually attacked with lunatone.
- priced +0.1215 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0025 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":677,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_lucario `83661652-3` (SetupBenchPokemon, wasted_resource)

- Ledger chose `[]` 
- ruling was `[0]` Meowth ex
- rationale: CRITICAL: Playing Meowth during setup doesnt allow us to use Last-Ditch Catch ability, thus should be avoided when able.

### mega_lucario `83661652-30` (Discard, sequencing_error)

- Ledger chose `[3, 4]` Gravity Mountain, Basic {F} Energy
- ruling was `[0]` Lillie's Determination
- rationale: CRITICAL: dont discard our main line attacker unless we really dont need it (have lots on board)
- priced -0.0100 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1252,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":6,"playerIndex":0}]]]'))
- priced -0.0540 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1227,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":6,"playerIndex":0}]]]'))
- priced -0.0735 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1227,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":1252,"playerIndex":0}]]]'))

### mega_lucario `83661652-31` (ToHand, wasted_resource)

- Ledger chose `[7]` Lunatone
- ruling was `[1]` Mega Lucario ex
- rationale: CRITICAL: we discarded a riolu to fetch a riolu. what a waste!
- priced +0.0905 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":675,"playerIndex":0}]]]',))
- priced +0.0805 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":677,"playerIndex":0}]]]',))
- priced +0.0055 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":676,"playerIndex":0}]]]',))

### mega_lucario `83966336-27` (Main, slow_setup)

- Ledger chose `[1]` Play Lillie's Determination
- ruling was `[0]` Play Team Rocket's Petrel
- rationale: RE-RULED 2026-07-27 (user, #175 Discrimination-Gate review; supersedes the original "Petrel grabbed a Supporter we already hold" ruling). Petrel IS the right first action -- what was wrong is WHAT it fetched. Given the opponent's poor setup, do NOT gamble on Lillie's for a quick KO: fetch Air Balloon, attach it to the Active Riolu, retreat, promote Solrock. Their bench is 3 Solrocks with NO Lunatone, so Cosmic Beam "does nothing" -- their only live line is Riolu -> Mega Lucario ex + 1 {F} for Aura Jab 130, which KOs either body. So the retreat does not dodge a KO, it CHOOSES which card eats it: Solrock costs 1 prize and zero attached energy and we hold a second one, while Riolu is the Mega Lucario ex base. Measured: leaving Riolu Active exposes it on 63.9% of their turns; after the retreat only ~18.6% (they need the KO *and* a Boss's Orders to gust it back up). Lillie's is then played NEXT turn, still at exactly 6 prizes for the draw-8. TURN-PLANNER scope (#165): the payoff is positional and spans fetch->attach->retreat->promote, which no single-action decider can express.
- priced +0.4932 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1330 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1219,"playerIndex":0}]]]',))

### mega_lucario `83966336-9` (ToHand, slow_setup)

- Ledger chose `[5]` Riolu
- ruling was `[2]` Basic {F} Energy
- rationale: CRITICAL: we need energy, be sure to fetch it with this.
- priced +0.1120 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":677,"playerIndex":0}]]]',))
- priced +0.0620 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":675,"playerIndex":0}]]]',))
- priced +0.0370 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":673,"playerIndex":0}]]]',))

### mega_lucario `83967841-14` (ToHand, slow_setup)

- Ledger chose `[2]` Lunatone
- ruling was `[0]` Basic {F} Energy
- rationale: CRITICAL: we already have lunatone in hand but dont have any energy. we typically only ever need a single lunatone and a single solrcok in play at any given time.
- priced +0.0770 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":675,"playerIndex":1}]]]',))
- priced +0.0670 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":677,"playerIndex":1}]]]',))
- priced +0.0603 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":673,"playerIndex":1}]]]',))

### mega_lucario `84071010-15` (Main, missed_win)

- Ledger chose `[1]` Play Lillie's Determination
- ruling was `[0]` Play Team Rocket's Petrel
- rationale: RE-RULED 2026-07-13 during the `retreat_enabler_lethal` build; PROPAGATED to this record 2026-07-29 by ADR-0082 decision 5 / Issue #211. The ruling itself is not new -- reviewed.json's `84071010-15` entry (disposition `fixed`, round 2026-07-13) already records it verbatim: "Fixture re-tagged correct=[0] (Petrel), category missed_win." Only the FIXTURE was re-tagged then; this record kept the superseded 2026-07-05 ruling for 16 days, which is the exact drift ADR-0082 exists to make loud. The 2026-07-05 original is preserved verbatim at the end of this note.

The line is deterministic and wins on turn 3. Re-verified at source 2026-07-29 (data/EN_Card_Data.csv, docs/rules.md): our Active Makuhita (673) is 50/80 with retreat 2 and ZERO Energy attached, so it cannot pay a retreat unaided, and the manual attach is already spent. Team Rocket's Petrel (1219) searches the deck for *a Trainer card* -- a Pokemon Tool is a Trainer -- and Air Balloon (1174, 'the Retreat Cost of the Pokemon this card is attached to is {C}{C} less') is in the deck. Balloon onto Makuhita makes the retreat 2-2 = 0, so it is free; Tools are unlimited per turn (rules.md S3) and the one manual retreat is unspent. Retreat, promote the benched Mega Lucario ex (678) which ALREADY holds one {F}, and Aura Jab ({F}, 130) clears the opponent's Active Riolu (677, 80 HP). Their bench is 0 of 5, so rules.md S7 condition 2 -- 'opponent has no Pokemon in play to replace a KO'd Active' -- ends the match.

The superseded ruling declined that for a stochastic 8-card redraw. Its full text: "Our hand is rather dead here, would rather shuffle in it for 8 new cards"
- priced +0.2418 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0805 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1219,"playerIndex":0}]]]',))

### mega_lucario `84071010-41` (ToHand, wasted_resource)

- Ledger chose `[0]` Makuhita
- ruling was `[1]` Solrock
- rationale: should grab a solrock in this case. our mega lucario is safe and energized while we have single lunatone on bench. give it a solrock to allow us to use lunatones draw ability.
- priced +0.0025 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":673,"playerIndex":0}]]]',))
- priced +0.0025 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":676,"playerIndex":0}]]]',))
- priced -0.1340 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":674,"playerIndex":0}]]]',))

### mega_lucario `84071010-64` (Main, wasted_resource)

- Ledger chose `[5]` Play Lillie's Determination
- ruling was `[2]` Attach Basic {F} Energy → Makuhita (bench 2 · 80/80)
- rationale: avoid attaching energy to lunatone unless only option
- priced +2.2361 ActionIdentity(kind='attack', parts=('[0,{"attackId":982,"type":13},[]]',))
- priced +0.1168 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_lucario `84889011-12` (ToHand, wasted_resource)

- Ledger chose `[3]` Riolu
- ruling was `[0]` Makuhita
- rationale: CRITICAL: already have solrock on board, so dont fetch it. we typically only ever need one solrock and one lunatone in play
- priced +0.0595 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":677,"playerIndex":0}]]]',))
- priced -0.0155 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":673,"playerIndex":0}]]]',))
- priced -0.0155 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":676,"playerIndex":0}]]]',))

### mega_lucario `84889011-24` (Main, wasted_resource)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[5]` Attach Basic {F} Energy → Solrock (bench 1 · 110/110)
- rationale: CRITICAL: The winning line was missed. Could have attached energy to Solrock. Retreated and promoted Solrock. Played two Premium Power Pros such that Solrock would swing for 130, OHKOing opponent for the win.
- priced +0.2925 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0155 ActionIdentity(kind='ability', parts=('[0,{"type":10},[[4,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":0}],"hp":80,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `84889011-7` (ToHand, wasted_resource)

- Ledger chose `[2]` Lunatone
- ruling was `[4]` Riolu
- rationale: CRITICAL: Already have lunatone on board, do not then fetch one
- priced +0.0770 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":675,"playerIndex":0}]]]',))
- priced +0.0670 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":677,"playerIndex":0}]]]',))
- priced -0.0080 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":673,"playerIndex":0}]]]',))

### mega_lucario `84889539-26` (ToHand, wasted_resource)

- Ledger chose `[4]` Riolu
- ruling was `[3]` Makuhita
- rationale: CRITICAL: Two things
1) We have Hariyama in hand, so fetching a Makuhita is a natural choice
2) playing this card reveals our entire deck thus prize cards. we can see our only two lunatones in our prize cards meaning that solrock is USELESS in play until we retrieve those.
- priced +0.1255 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":677,"playerIndex":1}]]]',))
- priced +0.1187 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":673,"playerIndex":1}]]]',))
- priced +0.0505 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":676,"playerIndex":1}]]]',))

### mega_lucario `84889539-87` (AttachFrom, misattachment)

- Ledger chose `[0]` Solrock (bench 1 · 110/110)
- ruling was `[3]` Riolu (bench 4 · 80/80)
- rationale: CRITICAL: Solrock is worthless without a Lunatone in play. Lunatone is near worthless without a Solrock in play. write that down.
- priced -0.0150 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":676,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.0150 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":673,"maxHp":80,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.0150 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":80,"id":677,"maxHp":80,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `84890060-11` (Main, misattachment)

- Ledger chose `[8]` End turn
- ruling was `[1]` Attach Basic {F} Energy → Solrock (bench 1 · 110/110)
- rationale: dont attach energy nor attack for lunatone when there are other options
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1150 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))
- priced -0.1375 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":6,"playerIndex":1}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[{"id":1174,"playerIndex":1}]}]]]',))

### mega_lucario `84890060-26` (ToHand, wasted_resource)

- Ledger chose `[2]` Riolu
- ruling was `[1]` Basic {F} Energy
- rationale: CRITICAL: you had the chance to fetch an energy, which could be attached to Mega Lucario, then free retreat to lucario and KO opponent with Aura Jab. that then would have recycled 2 energies from discard to be placed on solrock and lunatone.
- priced +0.0760 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":677,"playerIndex":1}]]]',))
- priced +0.0275 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":675,"playerIndex":1}]]]',))
- priced -0.0575 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":676,"playerIndex":1}]]]',))

### mega_lucario `84890060-48` (ToHand, wasted_resource)

- Ledger chose `[16]` Boss’s Orders
- ruling was `[9]` Fighting Gong
- rationale: A fighting gong would have yielded us an energy to attach to our wincon, then free retreat into it and KO opponent.
- priced -0.1075 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":1182,"playerIndex":1}]]]',))
- priced -0.1425 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":1227,"playerIndex":1}]]]',))
- priced -0.1425 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":1213,"playerIndex":1}]]]',))

### mega_lucario `85058051-13` (ToHand, wasted_resource)

- Ledger chose `[3]` Riolu
- ruling was `[2]` Lunatone
- rationale: CRITICAL: There was a win on this turn. fetch lunatone with ultra ball, attack for 70 dmg, win!
- priced +0.1525 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":677,"playerIndex":1}]]]',))
- priced +0.0050 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":675,"playerIndex":1}]]]',))
- priced -0.0200 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":676,"playerIndex":1}]]]',))

### mega_lucario `85058051-4` (Main, wasted_resource)

- Ledger chose `[4]` End turn
- ruling was `[1]` Play Ultra Ball
- rationale: we have no plan to retreat solrock here, waste.

For this first turn, we had a great opportunity for an early draw engine. we could have played ultra ball, given back Petrel and Lillie, fetched Lunatone, then discarded a single energy to draw three. attaching one energy to solrock was a good move.
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0290 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))
- priced -0.1750 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1174,"playerIndex":1}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":110,"id":676,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `85058574-109` (Main, other)

- Ledger chose `[10]` Ability: Lunatone (bench 1 · 110/110)
- ruling was `[9]` Evolve Mega Lucario ex → Riolu (bench 3 · 20/80)
- rationale: This is a match planer note: Here we are facing a fully energyized Dragapult while opponent has two drakloaks on bench, one of them with a single energy. we cannot KO the Dragapult in a single turn and those Drakloaks are draw engines and will become future Dragapults. Opponent also still needs his full 6 prize cards.

We have the ability to fully heal our Lucario with Wallys Compassion, we can gust with Boss's Orders, and an Ultra Ball can fetch a Hariyama which can also gust. 

Given our hand, playing around the Dragapult and KOing the Drakloaks could effictively hamstring our opponent while keeping alive just long enough to eventually KO that Dragapult in future turns.

Thus i would gust the single energy Drakloak, KO it, and place 3 discarded energy on our benched Rioulu and Hariyama. Next turn id gust the other Drakloak, KOing it.

then we would have only 2 prize cards remaining. 

We have a Meowth ex in hand, which can fetch our decked Boss's Orders to gust the Fezandiptit, KOing that for our final 2 prize cards.
- priced +0.2650 ActionIdentity(kind='attack', parts=('[1,{"attackId":982,"type":13},[]]',))
- priced +0.0225 ActionIdentity(kind='ability', parts=('[1,{"type":10},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_lucario `85058574-114` (Main, wrong_attack)

- Ledger chose `[9]` End turn
- ruling was `[1]` Attach Basic {F} Energy → Mega Lucario ex (active · 340/340)
- rationale: CRITICAL: Dont play Poke Pad when we do not intent to fetch a pokemon with it. these cards are perfect fodder for ultra balls
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0419 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1142,"playerIndex":1}]]]',))
- priced -0.0450 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":6,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":340,"id":678,"maxHp":340,"playerIndex":1,"preEvolution":[{"id":677,"playerIndex":1}],"tools":[]}]]]',))

### mega_lucario `85058574-121` (AttachFrom, wrong_attack)

- Ledger chose `[0]` Lunatone (bench 1 · 110/110)
- ruling was `[3]` Hariyama (bench 4 · 150/150)
- rationale: PLANNER / multi-turn (re-tagged [2]->[3], user-confirmed 2026-07-22). Neither the corpus's Mega Lucario ex nor a Solrock is right. The opponent can't KO any of our Pokemon next turn, and the active Mega Lucario ex is ALREADY a next-turn KO (one manual F -> Mega Brave 270 > Dragapult's 190 left) without this route. So the Aura Jab energy stages the NEXT 1-prize attacker: route >=2 F to Hariyama (Wild Press 210), skipping the weaker Solrock and the 3-prize Mega Lucario liability (force-8-prizes doctrine). Assumes a fully-energized backup Dragapult promotes after we KO; the commit-to-Hariyama call rests on an odds calc (turns until an energy/fetch reaches the benched Mega Lucario ~ 3). TURN-PLANNER scope, NOT the single-turn energy oracle.
- priced -0.0150 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.0150 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":676,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[{"id":1174,"playerIndex":1}]}]]]',))
- priced -0.0150 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":280,"id":678,"maxHp":340,"playerIndex":1,"preEvolution":[{"id":677,"playerIndex":1}],"tools":[]}]]]',))

### mega_lucario `85058574-69` (Main, wasted_resource)

- Ledger chose `[2]` End turn
- ruling was `[1]` Play Team Rocket's Petrel
- rationale: CRITICAL: Dont play Premium Power Pro unless we intend to attack this turn. Given Riolu's attack went last turn, he cannot use it this turn as well.
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1075 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1219,"playerIndex":1}]]]',))
- priced -0.2050 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1141,"playerIndex":1}]]]',))

### mega_lucario `85058574-71` (ToHand, wasted_resource)

- Ledger chose `[18]` Boss’s Orders
- ruling was `[11]` Fighting Gong
- rationale: I would have fetched fighting gong, then used that to fetch an energy, then discarded that energy to draw 3 cards using Lunatones ability.
- priced -0.0130 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":1182,"playerIndex":1}]]]',))
- priced -0.0480 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":1227,"playerIndex":1}]]]',))
- priced -0.0480 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":1080,"playerIndex":1}]]]',))

### mega_lucario `85058574-87` (Main, wasted_resource)

- Ledger chose `[8]` Attack with Mega Brave
- ruling was `[0]` Attach Air Balloon → Mega Lucario ex (active · 330/340 · 2⚡)
- rationale: CRITICAL: attaching air balloon to a benched mon doesnt really make sense. its purpose is to allow our active to retreat for free.
- priced +1.0359 ActionIdentity(kind='attack', parts=('[1,{"attackId":983,"type":13},[]]',))
- priced +0.2827 ActionIdentity(kind='attack', parts=('[1,{"attackId":982,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_lucario `85058574-88` (Main, wrong_attack)

- Ledger chose `[2]` Attack with Mega Brave
- ruling was `[1]` Attack with Aura Jab
- rationale: CRITICAL: Pilot chose Mega Brave which makes sense when considering this turn in isolation, because that is the only attack that KOs the Munkidori. BUT using Mega Brave now means that we cannot use it next turn, when the opponents energized Dragapult Ex will surely be promoted. It would have been more match strategic to attack with Aura Jab as to attach 3 energy to our bench pokemon in preparation for fighting the Dragapults. i would have attached two energy to the Riolu and one to the Hariyama
- priced +1.0359 ActionIdentity(kind='attack', parts=('[1,{"attackId":983,"type":13},[]]',))
- priced +0.2827 ActionIdentity(kind='attack', parts=('[1,{"attackId":982,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_lucario `85059103-39` (ToHand, other)

- Ledger chose `[9]` Lunatone
- ruling was `[7]` Solrock
- rationale: CRITICAL: We have a Lunatone in play, a few energy cards in hand plus a fully energized Lucario. we need a solrock to utilize Lunatone's draw 3 ability.

Then we wanna start draw 3 each turn, discarding energy that can be recycled with Lucario's Aura Jab attack.
- priced +0.1025 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":675,"playerIndex":0}]]]',))
- priced +0.0925 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":677,"playerIndex":0}]]]',))
- priced +0.0175 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":673,"playerIndex":0}]]]',))

### mega_lucario `85059103-84` (Main, other)

- Ledger chose `[14]` End turn
- ruling was `[3]` Attach Basic {F} Energy → Riolu (bench 3 · 80/80 · 1⚡)
- rationale: as a general rule, dont energize Meowth, its a tutor fetch engine.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1029 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":6,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":673,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1225 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":6,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `85059103-9` (ToHand, wrong_attack)

- Ledger chose `[7]` Boss’s Orders
- ruling was `[3]` Team Rocket's Petrel
- rationale: CRITICAL: Dont fetch a lillie's when we already have one in our hand.

Here I would have fetch a Petrel, which can be used to fetch a fighting gong, which can be used to fetch a solrock. then we can discard an energy card to draw three cards. 
- priced +0.1250 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1182,"playerIndex":0}]]]',))
- priced +0.0900 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0900 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1213,"playerIndex":0}]]]',))

### mega_lucario `85709280-17` (Main, slow_setup)

- Ledger chose `[2]` Play Fighting Gong
- ruling was `[]` 
- rationale: CRITICAL: For this turn, we need to grab a lunatone as to match our solrock, allowing it to attack. obviously the system isnt aware that lunatone is required for solrock to attack, otherwise it would not have attached energy and attempting attacking int he first place. review that, !.

Also, given the fan has -30 resistance to fighting energy, it would have worked to fetch a Team Rocket's Petrel with the Meowth ex, then play Petrel to fetch a Premium Power Pro, used that on the Solrock to KO the opponents active.
- priced +0.0310 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1142,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0695 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1071,"playerIndex":1}]]]',))

### mega_lucario `85709280-42` (Main, slow_setup)

- Ledger chose `[7]` End turn
- ruling was `[1]` Attach Air Balloon → Meowth ex (active · 170/170)
- rationale: CRITICAL: A worthless attach. We need our Meowth Ex out of the active spot so that we can attack. SHould have attached Air Balloon to Meowth, then promote Solrock, then play Premium Power Pro, and KO opponent.
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1377 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))
- priced -0.1795 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1174,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":170,"id":1071,"maxHp":170,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `85709280-55` (Main, misattachment)

- Ledger chose `[6]` End turn
- ruling was `[0]` Attach Air Balloon → Meowth ex (active · 170/170)
- rationale: Ait Balloons are for retreating active for free, not anyother reasons.
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1795 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1174,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":170,"id":1071,"maxHp":170,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1795 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1174,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":1}],"hp":110,"id":676,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `85785067-42` (Main, slow_setup)

- Ledger chose `[5]` End turn
- ruling was `[4]` Ability: Lunatone (bench 3 · 110/110)
- rationale: Our hand is empty, would have been better investment to discard energy and draw 3
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0740 ActionIdentity(kind='ability', parts=('[0,{"type":10},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1270 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":6,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":340,"id":678,"maxHp":340,"playerIndex":0,"preEvolution":[{"id":677,"playerIndex":0}],"tools":[]}]]]',))

### mega_lucario `85785067-54` (Main, slow_setup)

- Ledger chose `[5]` End turn
- ruling was `[4]` Ability: Lunatone (active · 80/110)
- rationale: Hand empty, we are still setting up and desperately need cards. discard energy, use lunatones ability to draw 3. our discarded enegyer can be recycled with Aura Jab
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0270 ActionIdentity(kind='ability', parts=('[0,{"type":10},[[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1270 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":6,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":0}],"hp":340,"id":678,"maxHp":340,"playerIndex":0,"preEvolution":[{"id":677,"playerIndex":0}],"tools":[]}]]]',))

### mega_lucario `85785606-19` (Main, wrong_supporter)

- Ledger chose `[5]` Ability: Lunatone (bench 2 · 110/110)
- ruling was `[1]` Attach Basic {F} Energy → Solrock (active · 80/110)
- rationale: Gusting is not helpful here
- priced +0.1580 ActionIdentity(kind='ability', parts=('[0,{"type":10},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1265 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":6,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":676,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `85785606-21` (Main, wrong_supporter)

- Ledger chose `[4]` Ability: Lunatone (bench 2 · 110/110)
- ruling was `[0]` Attach Basic {F} Energy → Solrock (active · 80/110)
- rationale: CRITICAL: Get Solrock attacking.
- priced +0.1580 ActionIdentity(kind='ability', parts=('[0,{"type":10},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1265 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":6,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":676,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `86088989-29` (ToHand, wrong_supporter)

- Ledger chose `[5]` Boss’s Orders
- ruling was `[1]` Lillie's Determination
- rationale: CRITICAL: Lillies would have been far more helpful here.
- priced +0.1250 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1182,"playerIndex":0}]]]',))
- priced +0.0900 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1213,"playerIndex":0}]]]',))
- priced +0.0900 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1227,"playerIndex":0}]]]',))

### mega_lucario `86088989-63` (AttachFrom, misattachment)

- Ledger chose `[3]` Riolu (bench 4 · 80/80 · 2⚡)
- ruling was `[2]` Solrock (bench 3 · 110/110)
- rationale: CRITICAL: Why give a third energy to Riolu/Lucario who need only 2?? This must never happen again. Solrock would have been better here for the third energy.
- priced +0.0850 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[6,6],"energyCards":[{"id":6,"playerIndex":0},{"id":6,"playerIndex":0}],"hp":80,"id":677,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.0150 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":673,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.0150 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":20,"id":673,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `86090147-20` (Main, wasted_resource)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[4]` Play Poké Pad
- rationale: Fetch a pokemon for our bench first, then Lillie's Determination.
- priced +0.3186 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0445 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1213,"playerIndex":0}]]]',))
- priced +0.0430 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1152,"playerIndex":0}]]]',))

### mega_lucario `86090147-22` (Main, wasted_resource)

- Ledger chose `[8]` End turn
- ruling was `[7]` Retreat
- rationale: After Lillie's, we got some really great stuff, but they must be used properly.

retreat meowth, promote solrock, attach energy to solrock (never should have attached to meowth before, so could have used air balloon). play lunatone, makuhita. attack with solrock

- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1050 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":675,"playerIndex":0}]]]',))
- priced -0.1225 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":673,"playerIndex":0}]]]',))

### mega_lucario `86090147-5` (Main, slow_setup)

- Ledger chose `[3]` End turn
- ruling was `[]` 
- rationale: CRITICAL: Complete blundering of the trainer use and retreat/promotions.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0245 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1152,"playerIndex":0}]]]',))
- priced -0.0665 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1071,"playerIndex":0}]]]',))

### mega_lucario `86090666-9` (Main, wasted_resource)

- Ledger chose `[6]` Play Lillie's Determination
- ruling was `[]` 
- rationale: 
- priced +0.2768 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1145 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))

### mega_lucario `86091172-30` (Main, wasted_resource)

- Ledger chose `[15]` Ability: Lunatone (active · 80/110 · 1⚡)
- ruling was `[]` 
- rationale: 
- priced +0.0085 ActionIdentity(kind='ability', parts=('[1,{"type":10},[[4,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":1}],"hp":80,"id":675,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1072 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":6,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":1}],"hp":80,"id":675,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `86091172-8` (Main, wasted_resource)

- Ledger chose `[1]` Play Poké Pad
- ruling was `[]` 
- rationale: 
- priced +0.0550 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1152,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1750 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":6,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `1002062899305-13` (Main, wrong_attack)

- Ledger chose `[4]` End turn
- ruling was `[2]` Attack with Water Gun
- rationale: CRITICAL: no attack still? this is a huge problem
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0436 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced -0.1278 ActionIdentity(kind='attack', parts=('[0,{"attackId":1486,"type":13},[]]',))

### mega_starmie `1002062899305-64` (Main, sequencing_error)

- Ledger chose `[8]` End turn
- ruling was `[6]` Play Pokégear 3.0
- rationale: CRITICAL: this pilot just attached energy before playing pokegear when we just explicitly made that a rule not to do such a thing. we have a real supporter need for a Wallys Compassion. Need to attempt to get it.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0984 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))
- priced -0.1225 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `160106599249705-8` (Main, other)

- Ledger chose `[1]` Play Buddy-Buddy Poffin
- ruling was `[]` 
- rationale: After 15 seconds deliberation, we played Pokegear. with that much time, we should have considered our basic needs first. first is to attach energy, second is benching staryu. we can bench staryus with buddy buddy. pokegear can perhaps fetch a hilda. play buddy buddy first to thin deck. then pokegear. if no hilda, then we must gamble with lilles for fetching an energy. shuffling away a starmie, which is a discounted need for next turn is worth it, because without energy, the starmie (and Cinderace) are worthless.
- priced +0.6440 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.0479 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `26001818654643-11` (Main, other)

- Ledger chose `[3]` End turn
- ruling was `[1]` Attack with Water Gun
- rationale: CRITICAL: why are we not attacking when energized? this is a consistent problem that shows something is seriously wrong with how we evaluate end of turn and dealing damage.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1100 ActionIdentity(kind='attack', parts=('[0,{"attackId":1486,"type":13},[]]',))
- priced -0.1740 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))

### mega_starmie `26001818654643-18` (Main, other)

- Ledger chose `[12]` End turn
- ruling was `[]` 
- rationale: Here, our primary needs are met, energy and mega starmie. and energy needs doubly met with ignition energy. thus immediate action is to evolve active staryu to starmie and attach iginition energy in any order.

Then, we have free fetch cards of buddy buddy poffin and pokegear. play buddy buddy first to thin deck and then pokegear. Pokegear might yield a choice that provides a supporter to use this turn. Our next need is a second Mega Starmie. Therefor Hilda and then Salvatore. Hilda over Salvatore because we have a staryu that was benced last turn, and hilda also fetches an energy for us.

After pokegear and replanning, we will have a choice to use a supporter. Our next turn need will be intensely an energy card because our ignition energy will be discarded. thus, dont shuffle away our hand with Harlequin. Also, opponent has only 5 cards in hand, so disruption value is 5-4(avg) or one card reduction, which is small. Bosses Orders doesnt help us. So IF we play a supporter, its dependant on what Pokegear provides and if that supporter can fetch us a starmie.

again, crushing hammer useless.

These are very straight forward decisions derived from our NEEDS.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0915 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1000 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `26001818654643-22` (ToHand, wrong_supporter)

- Ledger chose `[1]` (card)
- ruling was `[0]` (card)
- rationale: CRITICAL: 1) we already have a harlequin in hand. 2) dont want to play harlequin this turn anyways. 3) we really want a second starmie.
- priced +0.0900 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[12,{"id":1223,"playerIndex":0}]]]',))
- priced +0.0750 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[12,{"id":1225,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='decline', parts=())

### mega_starmie `26001818654643-31` (Main, other)

- Ledger chose `[1]` Play Lillie's Determination
- ruling was `[]` 
- rationale: Our needs this turn: attach energy (covered). future needs 1 and 2 turns away: attach energy (covered) eventually healing (not covered).

so we immediately attach to our active to cover that need and attaching to bench should never even be considered. that decision branch should never be walked down and the needs system should determine that.

then we are left with an actual decision that is in fact easy to decide. we have 4 cards in hand. a salvatore (useless with staryu), ultra ball (want to fetch staryu, but our only other staryu is in discard, ultra ball = useless), and a second energy (a next turn need). Thus hypergeometric odds must weigh the discounted value of a single energy versus shuffling away that energy plus two useless cards to draw 8 cards. an easy decision to play lillies, again, not by walking down branches but by considering present turn needs versus discounted future turn needs and computing odds.

These decisions should be almost instantaneous.
- priced +0.1313 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0570 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `26001818654643-44` (Main, other)

- Ledger chose `[10]` Attack with Jetting Blow
- ruling was `[]` 
- rationale: This is a seemingly more complex turn given our large hand with three different supporters, but, using needs, we see that all we need is to attach an energy to our active as to build towards Nebula Beam.

Attaching to bench shall never be considered.
2 Salvatores are useless, never walk that branch
Ultra Ball worthess (stryu discared), never walk that branch
Wallys worthless, ignored.
Lillies shuffles away our one need, dont consider.

SO our only choice is between attaching the ignition energy for immediate nebula beam satisfaction or attaching basic energy as to build towards nebula beam over 2 turns.

ignition is a fine choice, can argue basic energy because it doesnt discard, but that is a wash decision.
- priced +0.0646 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0175 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `26001818654643-49` (Main, other)

- Ledger chose `[9]` Attack with Jetting Blow
- ruling was `[]` 
- rationale: the sequence carried out by our pilot in this turn is perfect, well done
- priced +0.0646 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0175 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `26001818654643-58` (Main, other)

- Ledger chose `[8]` Play Wally's Compassion
- ruling was `[]` 
- rationale: perfectly executed turn in no time at all, well done
- priced +0.0915 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))
- priced +0.0646 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `26001818654643-72` (Main, other)

- Ledger chose `[11]` Attack with Jetting Blow
- ruling was `[]` 
- rationale: i see that to attach our only type of energy to our full HP primary attacker active took 3 seconds. you must analyze which branches we walked down. yes, we have many cards, supporter in hand, but our only real need is to attach this energy and attack. future needs our energy attachments on following turns, which we also have in hand. thus i see no reason to debate here. can this decision making be optimized and made more efficient here?
- priced +0.0646 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0079 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))

### mega_starmie `26001818654643-72` (Main, misattachment)

- Ledger chose `[11]` Attack with Jetting Blow
- ruling was `[5]` Attach Basic {W} Energy → Mega Starmie ex (active · 330/330 · 1⚡)
- rationale: CRITICAL: an absolutelt nonsensical choice to attach to our benched starmie when our active starmie still needs 2 more energy to reach nebula beam. true that our opponent has used 3/4 Wallys Compassions, but still, dont diversify like this when both starmies has full HP
- priced +0.0646 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0079 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))

### mega_starmie `26001818654643-76` (Main, other)

- Ledger chose `[5]` Attach Basic {W} Energy → Mega Starmie ex (active · 330/330 · 1⚡)
- ruling was `[]` 
- rationale: Game winning move found and taken without any intermediate moves, excellent.
- priced +103.1422 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0020 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0020 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `81785223-28` (Damage, bad_target)

- Ledger chose `[0]` opp Latias ex (bench 1 · 210/210)
- ruling was `[1]` opp Lillie’s Clefairy ex (bench 2 · 190/190 · 1⚡)
- rationale: Should have snipped benched Pokemon with energy attached. That is a higher threat
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":210,"id":184,"maxHp":210,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":20,"playerIndex":1}],"hp":190,"id":272,"maxHp":190,"playerIndex":1,"preEvolution":[],"tools":[{"id":1172,"playerIndex":1}]}]]]',))

### mega_starmie `81785223-32` (Main, sequencing_error)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[4]` Play Pokégear 3.0
- rationale: 
- priced +0.1004 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0927 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `81785223-38` (Main, sequencing_error)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[4]` Play Pokégear 3.0
- rationale: Should play Pokegear  3.0 to dig for supporter earlier in turn
- priced +0.0370 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0844 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `81785223-39` (Damage, bad_target)

- Ledger chose `[0]` opp Latias ex (bench 1 · 110/210)
- ruling was `[2]` opp Lillie’s Clefairy ex (bench 3 · 70/190 · 1⚡)
- rationale: Should snipe highest threat Pokemon, in this case the only benched pokemon with energy.
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":184,"maxHp":210,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":90,"id":108,"maxHp":210,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":20,"playerIndex":1}],"hp":70,"id":272,"maxHp":190,"playerIndex":1,"preEvolution":[],"tools":[{"id":1172,"playerIndex":1}]}]]]',))

### mega_starmie `81785223-44` (Main, sequencing_error)

- Ledger chose `[6]` Attack with Jetting Blow
- ruling was `[4]` Play Pokégear 3.0
- rationale: 
- priced +2.0155 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0662 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `81785223-45` (Damage, sequencing_error)

- Ledger chose `[0]` opp Latias ex (bench 1 · 60/210)
- ruling was `[2]` opp Lillie’s Clefairy ex (bench 3 · 70/190 · 1⚡)
- rationale: 
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":60,"id":184,"maxHp":210,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":90,"id":108,"maxHp":210,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":1}],"hp":70,"id":272,"maxHp":190,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `81903490-27` (Main, misattachment)

- Ledger chose `[7]` End turn
- ruling was `[0]` Attach Basic {W} Energy → Staryu (active · 70/70)
- rationale: Save ignition energy either for Mega Starmie Ex or Cinderace in special cases if no Mega Starmie Ex, Staru is benched, and basic energy
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1515 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1535 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))

### mega_starmie `81903490-49` (Main, misattachment)

- Ledger chose `[6]` Play Salvatore
- ruling was `[1]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: Never attach ignition energy to Cinderace when basic energy available
- priced +0.0485 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1074 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `81903490-74` (Main, sequencing_error)

- Ledger chose `[3]` Play Night Stretcher
- ruling was `[5]` Evolve Mega Starmie ex → Staryu (active · 70/70 · 1⚡)
- rationale: Most often should Evolve active Staru to mega starmie ex if have the chance. only case not to is if attachking with mega starmie ex doesnt win and then next turn mega starmie ex will die and opponent has less than 3 prize cards left, causing loss of game
- priced +0.0580 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1097,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1860 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))

### mega_starmie `81903490-8` (ToHand, wasted_resource)

- Ledger chose `[0]` Staryu
- ruling was `[1]` Mega Starmie ex
- rationale: Ultra balls should be usually used to find main pokemon, in this case Mega Starmie Ex
- priced +0.0880 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1030,"playerIndex":0}]]]',))
- priced +0.0880 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1031,"playerIndex":0}]]]',))
- priced -0.1599 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":666,"playerIndex":0}]]]',))

### mega_starmie `81903490-93` (ToHand, other)

- Ledger chose `[1]` Staryu
- ruling was `[2]` Basic {W} Energy
- rationale: use night stretcher to get basic energy if dont already have energy in hand and active pokemon needs an energy. typically dont need cinderace after SETUP stage
- priced +0.1335 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[3,{"id":1030,"playerIndex":0}]]]',))
- priced -0.0865 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[3,{"id":3,"playerIndex":0}]]]',))
- priced -0.1219 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[3,{"id":666,"playerIndex":0}]]]',))

### mega_starmie `81904064-19` (ToHand, other)

- Ledger chose `[0]` Ignition Energy
- ruling was `[1]` Basic {W} Energy
- rationale: ignition energy is discarded at end of turn so needs using wisely. in this case, a basic energy would have been enough to kill opponents active AND do bench damge.
- priced +0.0500 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":17,"playerIndex":0}]]]',))
- priced +0.0500 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":3,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='decline', parts=())

### mega_starmie `81904064-29` (Main, wasted_resource)

- Ledger chose `[1]` Play Buddy-Buddy Poffin
- ruling was `[3]` Play Lillie's Determination
- rationale: using wally's compassion to heal 10 damage is far too low. save wally's compassion for when it will prevent mega starmie ex from dying next turn
- priced +0.1715 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0058 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))

### mega_starmie `81904064-49` (Main, sequencing_error)

- Ledger chose `[2]` Attack with Nebula Beam
- ruling was `[0]` Play Pokégear 3.0
- rationale: use useful items if able
- priced +2.9339 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0807 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `81904064-59` (Main, sequencing_error)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[1]` Play Salvatore
- rationale: Use Salvatore to get other Mega Starmie ex if no other supporter is a better choice
- priced +1.0199 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0277 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `81904451-15` (Main, misattachment)

- Ledger chose `[1]` Play Lillie's Determination
- ruling was `[2]` Play Hilda
- rationale: save boss's orders for when it can kill an otherwise benched pokemon OR it forces opponent to stall (move up benched poikemon with high retreat and no energy attached). Hilda is important to get an energy and Mega Starmie early game.
- priced +0.0981 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0105 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1225,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `81904451-17` (Main, bad_retreat)

- Ledger chose `[2]` End turn
- ruling was `[0]` Attack with Water Gun
- rationale: Attack when able over retreat in most cases.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.2616 ActionIdentity(kind='attack', parts=('[0,{"attackId":1486,"type":13},[]]',))
- priced -0.2950 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))

### mega_starmie `81904451-24` (Main, sequencing_error)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[1]` Play Hilda
- rationale: play hilda to get Mega Starmie. then attach energy and attack
- priced +0.2320 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0630 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1225,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `81904451-37` (Main, sequencing_error)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[1]` Play Hilda
- rationale: get mega starmie with hilda, then free retreat cinderace to mega starmie and attack
- priced +1.0888 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.1299 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0570 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1225,"playerIndex":0}]]]',))

### mega_starmie `81904451-53` (Main, sequencing_error)

- Ledger chose `[1]` Play Hilda
- ruling was `[6]` Play Mega Signal
- rationale: Should have found mega starmie ex with Mega Signal
- priced +0.9436 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.1943 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1225,"playerIndex":0}]]]',))
- priced +0.1930 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))

### mega_starmie `81904451-58` (Main, sequencing_error)

- Ledger chose `[1]` Play Hilda
- ruling was `[6]` Play Mega Signal
- rationale: Should have found Mega Starmie ex
- priced +0.9126 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.1792 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1225,"playerIndex":0}]]]',))
- priced +0.1780 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))

### mega_starmie `81904451-6` (Main, misattachment)

- Ledger chose `[2]` Play Buddy-Buddy Poffin
- ruling was `[0]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: never attach ignition energy to Cinderace if basic energy available. ignition energy discards at end of turn.
- priced +0.5202 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1412 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `81905063-10` (Main, sequencing_error)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[2]` Play Buddy-Buddy Poffin
- rationale: could have fetched two staryu first. that also allows full knowledge of whats in prize cards via what is in deck
- priced +0.2644 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.1020 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1086,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `81905063-16` (Main, bad_retreat)

- Ledger chose `[2]` End turn
- ruling was `[0]` Attack with Water Gun
- rationale: why retreat when could have attacked? this wasted an energy and damage to opponent
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.2247 ActionIdentity(kind='attack', parts=('[1,{"attackId":1486,"type":13},[]]',))
- priced -0.2905 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))

### mega_starmie `81905522-28` (Main, sequencing_error)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[1]` Evolve Mega Starmie ex → Staryu (active · 70/70 · 1⚡)
- rationale: Typically alwasys evolve active to mega starmie if able to, especially since energy already attached
- priced +0.0994 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0806 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `81905522-47` (Main, sequencing_error)

- Ledger chose `[16]` Attack with Turbo Flare
- ruling was `[5]` Attach Basic {W} Energy → Staryu (bench 2 · 70/70)
- rationale: attach energy when able
- priced +0.1327 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1045 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `81905522-64` (Main, sequencing_error)

- Ledger chose `[15]` Attack with Jetting Blow
- ruling was `[5]` Attach Basic {W} Energy → Staryu (bench 1 · 70/70)
- rationale: attach energy when able
- priced +0.2045 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.1248 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `81905522-75` (Damage, bad_target)

- Ledger chose `[0]` opp Hariyama (bench 1 · 150/150)
- ruling was `[3]` opp Riolu (bench 4 · 80/80)
- rationale: Hariyama is strongest benched pokemon, but is not threat due to no energy. Riolu can become mega lucario, so snipe that instead
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":150,"id":674,"maxHp":150,"playerIndex":1,"preEvolution":[{"id":673,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":677,"maxHp":80,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `81906131-25` (Main, bad_target)

- Ledger chose `[1]` Play Buddy-Buddy Poffin
- ruling was `[2]` Attach Ignition Energy → Cinderace (active · 160/160)
- rationale: never attach ignition energy to Cinderace when can attach basic energy
- priced +0.5090 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1086,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0939 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `81906755-77` (Main, sequencing_error)

- Ledger chose `[7]` End turn
- ruling was `[0]` Play Salvatore
- rationale: fetch a mega starmie when able, then evolve staryu if able
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0296 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced -0.0720 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1097,"playerIndex":1}]]]',))

### mega_starmie `81906755-93` (Main, sequencing_error)

- Ledger chose `[10]` Attack with Jetting Blow
- ruling was `[3]` Attach Basic {W} Energy → Staryu (bench 1 · 70/70)
- rationale: attach energy when able and pokemons need it
- priced +3.2264 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0445 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82224509-29` (Main, sequencing_error)

- Ledger chose `[6]` Attack with Turbo Flare
- ruling was `[4]` Evolve Mega Starmie ex → Staryu (bench 2 · 70/70)
- rationale: fine to evolve bench into main attacker because opponent has no threatening cards.
- priced +1.3230 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1240 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82224509-31` (AttachFrom, misattachment)

- Ledger chose `[0]` Mega Starmie ex (bench 1 · 330/330 · 3⚡)
- ruling was `[1]` Staryu (bench 2 · 70/70)
- rationale: dont attach more energy on a pokemon than it needs. Mega Starmie already had 3 basic energy, therefor should have attached on the other benched mon without any energy
- priced +0.0850 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3,3,3],"energyCards":[{"id":3,"playerIndex":1},{"id":3,"playerIndex":1},{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced -0.0150 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82224509-40` (Main, misattachment)

- Ledger chose `[7]` Attack with Turbo Flare
- ruling was `[2]` Attach Basic {W} Energy → Mega Starmie ex (bench 2 · 330/330)
- rationale: Cinderace already had all the energy it needed, so dont waste more energy on it, attach to the benched mon without any energy.
- priced +0.0083 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1090 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82224509-41` (Main, sequencing_error)

- Ledger chose `[3]` Attack with Turbo Flare
- ruling was `[4]` Retreat
- rationale: When main attacker has full energy on bench, retreat into it to finish off the opponent
- priced +0.0083 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1320 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))

### mega_starmie `82224509-46` (Main, sequencing_error)

- Ledger chose `[4]` Attack with Jetting Blow
- ruling was `[1]` Play Boss’s Orders
- rationale: should have boss's orders the preevolution to the opponents main attacker
- priced +1.2205 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +1.0017 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82224509-47` (Damage, bad_target)

- Ledger chose `[0]` opp Lunatone (bench 1 · 110/110)
- ruling was `[2]` opp Riolu (bench 3 · 80/80)
- rationale: should snipe preevolution to opponents main attacker
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":676,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":677,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82224509-56` (Damage, bad_target)

- Ledger chose `[0]` opp Lunatone (bench 1 · 60/110)
- ruling was `[1]` opp Mega Lucario ex (bench 2 · 340/340)
- rationale: snipe the opponents main attacker
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":60,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":340,"id":678,"maxHp":340,"playerIndex":0,"preEvolution":[{"id":677,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":673,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82224509-67` (Main, sequencing_error)

- Ledger chose `[6]` Attack with Jetting Blow
- ruling was `[5]` Play Crushing Hammer
- rationale: opponents active is their main attacker with an energy on it, thats a huge threat. use crushing hammer.
- priced +1.2115 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.1490 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82224509-71` (Main, sequencing_error)

- Ledger chose `[4]` Play Wally's Compassion
- ruling was `[2]` Play Lillie's Determination
- rationale: hand wasnt very useful, therefor use lillie's determintation to swap it out
- priced +103.3240 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +1.2134 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.3583 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1229,"playerIndex":1}]]]',))

### mega_starmie `82225138-19` (Main, other)

- Ledger chose `[3]` End turn
- ruling was `[0]` Play Harlequin
- rationale: never play salvatore when no staryu is on board to evolve. hand also sucked, so use harlequin
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1447 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))
- priced -0.1455 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))

### mega_starmie `82225138-46` (Damage, bad_target)

- Ledger chose `[0]` opp Mega Kangaskhan ex (bench 1 · 300/300)
- ruling was `[1]` opp Dwebble (bench 2 · 70/70)
- rationale: when snipping for only 50 dmg, dont snipe a big wall, go for a weak mon
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":300,"id":756,"maxHp":300,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":344,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82225643-11` (Main, sequencing_error)

- Ledger chose `[9]` End turn
- ruling was `[0]` Play Pokégear 3.0
- rationale: Though ignition energy will be helpful in this current board state, Pokegear 3.0's should have been used first to look for supports that could have helped to find basic energy. ignition energy is such a good card, that it should be saved when able.
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1059 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1122,"playerIndex":1}]]]',))
- priced -0.1245 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":17,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82225643-12` (Main, sequencing_error)

- Ledger chose `[6]` Attack with Turbo Flare
- ruling was `[1]` Play Crushing Hammer
- rationale: Rioulu would not have died from this attack, and next turn he might evolve to opponents main attacker, mega lucario, thus playing the crushing hammers could have reduced its threat through energy removal.
- priced +0.1956 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1059 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1122,"playerIndex":1}]]]',))

### mega_starmie `82225643-34` (Main, sequencing_error)

- Ledger chose `[5]` Attack with Jetting Blow
- ruling was `[0]` Play Pokégear 3.0
- rationale: Use pokegear 3.0 to find supporter when able. there is no downside in having an extra support in hand.
- priced +2.3257 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +1.1369 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82226116-100` (Main, sequencing_error)

- Ledger chose `[0]` Play Night Stretcher
- ruling was `[13]` Retreat
- rationale: Should have attached basic energy to benched main line attacker, giving it enough energy to KO opponents active. then retreat cinderace into that main line attacker.
- priced +0.1075 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1097,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0473 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `82226116-48` (Main, bad_retreat)

- Ledger chose `[12]` Attack with Turbo Flare
- ruling was `[13]` Retreat
- rationale: Should have retreated to the folly powered up Mega Starmie which would have setup a double KO with Jetting Blow attack.
- priced +0.1156 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1000 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82226116-70` (Main, sequencing_error)

- Ledger chose `[0]` Play Wally's Compassion
- ruling was `[11]` Evolve Mega Starmie ex → Staryu (bench 2 · 70/70)
- rationale: Should evolve benched staryu to mega starmie and attached an energy to it first.
- priced +1.0331 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.8657 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.3373 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))

### mega_starmie `82226116-94` (ToActive, sequencing_error)

- Ledger chose `[0]` Cinderace (bench 1 · 120/160 · 1⚡)
- ruling was `[1]` Staryu (bench 2 · 70/70)
- rationale: Should have advanced staryu because we have mega starmie in hand ready to evolve it plus energy to attach.
- priced +0.0480 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":120,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0320 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82226759-16` (Main, sequencing_error)

- Ledger chose `[1]` Play Lillie's Determination
- ruling was `[0]` Evolve Mega Starmie ex → Staryu (bench 1 · 70/70)
- rationale: In this deck, evolving benched stryu to mega starmie is typically best, even if its now a benched mega without energy. here its early game with no real opponent threat yet. also mega starmie requires only single energy to do damage. After evolving, could have played lillie's determination to potentially find more basic energy.
- priced +2.4039 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0427 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82226759-29` (Main, sequencing_error)

- Ledger chose `[4]` Attack with Jetting Blow
- ruling was `[0]` Evolve Mega Starmie ex → Staryu (bench 1 · 70/70)
- rationale: evolve the benched staryu first.
- priced +2.0471 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1688 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1223,"playerIndex":1}]]]',))

### mega_starmie `82226759-51` (Damage, bad_target)

- Ledger chose `[0]` opp Alakazam (bench 1 · 140/140)
- ruling was `[3]` opp Abra (bench 4 · 50/50)
- rationale: Should kill the 50HP benched Abra for an additional prize card. 
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":140,"id":743,"maxHp":140,"playerIndex":0,"preEvolution":[{"id":741,"playerIndex":0},{"id":742,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":858,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":742,"maxHp":80,"playerIndex":0,"preEvolution":[{"id":741,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82227388-22` (Main, sequencing_error)

- Ledger chose `[7]` Attack with Turbo Flare
- ruling was `[2]` Attach Basic {W} Energy → Staryu (bench 2 · 70/70)
- rationale: Attach basic energy when able. in this case, attach to the weaker benched pokemon because we know that Cinderace's Turbo Flare attack will provide a full 3 basic energy to Mega Starmie.
- priced +0.1426 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0541 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `82227388-30` (Main, sequencing_error)

- Ledger chose `[7]` Attack with Jetting Blow
- ruling was `[2]` Attach Basic {W} Energy → Staryu (bench 2 · 70/70)
- rationale: Attch energy to benched pokemon when able and they need it. also should use Pokegear 3.0 to potentially find a useful supporter.
- priced +1.3948 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +1.0968 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82227388-43` (Main, sequencing_error)

- Ledger chose `[11]` Attack with Jetting Blow
- ruling was `[7]` Play Wally's Compassion
- rationale: Here, we could have played Wally's Compassion to fully heal our active. then played ignition energy to attack with Nebula Beam again.
- priced +0.2789 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.1911 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82227388-50` (Main, sequencing_error)

- Ledger chose `[5]` Play Wally's Compassion
- ruling was `[2]` Play Pokégear 3.0
- rationale: Play Pokegear 3.0 when able to find useful supporters.
- priced +0.2280 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.2067 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))
- priced +0.1020 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))

### mega_starmie `82228017-4` (Main, sequencing_error)

- Ledger chose `[3]` End turn
- ruling was `[1]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: When no staryus on board that need evolving and already 2 mega starmies in hand, dont waste the mega signal.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0429 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.0970 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":1159,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82228640-25` (Main, misattachment)

- Ledger chose `[9]` End turn
- ruling was `[5]` Attach Basic {W} Energy → Mega Starmie ex (active · 280/330)
- rationale: Should have attached basic energy instead of ignition energy to active mega starmie, as its Jetting Blow is enough to KO opponents active while also sniping bench. Plus, Ignition Energy discards at end of turn, so should be saved for only when needed.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0721 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":280,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced -0.0721 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":280,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82228640-48` (Main, misattachment)

- Ledger chose `[5]` Attack with Jetting Blow
- ruling was `[2]` Attach Basic {W} Energy → Mega Starmie ex (active · 310/430 · 1⚡)
- rationale: attach energy when able and a pokemon needs it before attacking.
- priced +0.2160 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1151 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":280,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82228640-53` (Main, sequencing_error)

- Ledger chose `[7]` Attack with Jetting Blow
- ruling was `[2]` Attach Basic {W} Energy → Mega Starmie ex (active · 190/430 · 1⚡)
- rationale: attach energy when able and needed prior to attacking.
- priced +0.2459 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1391 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":190,"id":1031,"maxHp":430,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[{"id":1159,"playerIndex":0}]}]]]',))

### mega_starmie `82228640-7` (Main, sequencing_error)

- Ledger chose `[2]` End turn
- ruling was `[0]` Attach Basic {W} Energy → Staryu (active · 70/70)
- rationale: attach energy first. ultra ball is saved to find mega starmie, which we already have in hand. also dont use ultra ball and discard hilda, when hilda can find mega starmie AND an energy card, far better than ultra ball.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0670 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))
- priced -0.0907 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82229122-45` (Main, bad_target)

- Ledger chose `[15]` Attack with Nebula Beam
- ruling was `[16]` Retreat
- rationale: This requires Posture and Tier 1 search. Crustle is immune to Ex attackers, thus should retreat to Cinderace who would have KO'd it. Also, when playing Crustle deck, will need to rely on Staryu and Cinderace almost fully.
- priced +0.8743 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1075 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82522698-36` (Main, sequencing_error)

- Ledger chose `[7]` Attack with Nebula Beam
- ruling was `[5]` Attach Basic {W} Energy → Mega Starmie ex (bench 1 · 330/330)
- rationale: Harelquin throws away our hand. we had an enery that we could have attached to the benched Mega Starmie first.
- priced +0.0870 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0045 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1223,"playerIndex":1}]]]',))

### mega_starmie `82522726-23` (Main, sequencing_error)

- Ledger chose `[0]` Play Salvatore
- ruling was `[2]` Evolve Mega Starmie ex → Staryu (active · 70/70 · 1⚡)
- rationale: Could have evolved active to mega starmie and attacked to win the game. always look for game winning move first.
- priced +0.0785 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1189,"playerIndex":1}]]]',))
- priced +0.0262 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82522726-7` (Main, sequencing_error)

- Ledger chose `[4]` End turn
- ruling was `[0]` Attach Basic {W} Energy → Staryu (active · 70/70)
- rationale: Attach energy prior to throwing away hand
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0960 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1225 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1223,"playerIndex":1}]]]',))

### mega_starmie `82523164-11` (Main, misattachment)

- Ledger chose `[1]` Play Lillie's Determination
- ruling was `[2]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: If there is basic energy in hand, a pokemon in play who needs an energy, always play that energy before throwing away hand with either Lillie's Determination or Harleguin
- priced +0.0357 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1719 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82523811-105` (Main, sequencing_error)

- Ledger chose `[5]` Attack with Jetting Blow
- ruling was `[4]` Attach Ignition Energy → Mega Starmie ex (active · 60/330 · 1⚡)
- rationale: Attaching Ignition Energy then attack with nebula beam would have one the game. before using cards that throw away hand like Harelquin or lillie's determination, a full review of possible moves must be made.
- priced +1.2640 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1005 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1145,"playerIndex":1}]]]',))

### mega_starmie `82523811-15` (Main, sequencing_error)

- Ledger chose `[6]` End turn
- ruling was `[3]` Play Crushing Hammer
- rationale: Riolu had 1 energy, and if it became a mega lucario could have OHKO our active staryu
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1260 ActionIdentity(kind='attack', parts=('[1,{"attackId":1486,"type":13},[]]',))
- priced -0.1510 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82523811-41` (Damage, bad_target)

- Ledger chose `[0]` opp Hariyama (bench 1 · 150/150)
- ruling was `[4]` opp Riolu (bench 5 · 80/80)
- rationale: Rioulu becomes Mega Lucario who needs only a single energy to deal significant damge, thus Rioulu is the snipe target.
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":150,"id":674,"maxHp":150,"playerIndex":0,"preEvolution":[{"id":673,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":676,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82523811-59` (Main, misattachment)

- Ledger chose `[8]` Attack with Jetting Blow
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (active · 400/430 · 1⚡)
- rationale: SHould have added a second energy to the active Mega Starmie. this is became it has 400HP and cannot die next turn while we also have two more energies in hand. thus in two turns we can have a Mega Starmie with full energy to use Nebula Beam
- priced +1.5966 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0764 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":400,"id":1031,"maxHp":430,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[{"id":1159,"playerIndex":1}]}]]]',))

### mega_starmie `82523811-61` (Damage, bad_target)

- Ledger chose `[0]` opp Hariyama (bench 1 · 150/150)
- ruling was `[3]` opp Riolu (bench 4 · 180/180)
- rationale: Riolu > Mega Lucario = Scary
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":150,"id":674,"maxHp":150,"playerIndex":0,"preEvolution":[{"id":673,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":100,"id":674,"maxHp":150,"playerIndex":0,"preEvolution":[{"id":673,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82523811-79` (Main, sequencing_error)

- Ledger chose `[1]` Attack with Jetting Blow
- ruling was `[0]` Play Crushing Hammer
- rationale: 
- priced +1.2397 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0830 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1120,"playerIndex":1}]]]',))

### mega_starmie `82523811-84` (Main, wasted_resource)

- Ledger chose `[9]` Attack with Jetting Blow
- ruling was `[4]` Attach Basic {W} Energy → Mega Starmie ex (active · 160/430 · 1⚡)
- rationale: Playing Salvatore when we do not have an in-play Staryu is 100% wasteful. never do this. Should have attached basic energy to bench, full HP Mega Starmie instead.
- priced +0.1968 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0055 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82523811-93` (Main, sequencing_error)

- Ledger chose `[6]` Attack with Jetting Blow
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (active · 330/330 · 1⚡)
- rationale: Attach energy in hand to mon who needs it before throwing away hand
- priced +1.1116 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0295 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82523811-95` (Main, sequencing_error)

- Ledger chose `[1]` Attack with Jetting Blow
- ruling was `[0]` Attach Basic {W} Energy → Mega Starmie ex (active · 330/330 · 1⚡)
- rationale: Always attach energy in hand to a mon who needs it before ending turn with attack
- priced +1.1248 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0475 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82524455-27` (Main, sequencing_error)

- Ledger chose `[3]` Attack with Jetting Blow
- ruling was `[2]` Attach Basic {W} Energy → Mega Starmie ex (active · 280/330 · 1⚡)
- rationale: Attach available energy before ending turn
- priced +1.4989 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0806 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":true,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":280,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82524455-55` (Main, sequencing_error)

- Ledger chose `[4]` End turn
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (active · 120/330)
- rationale: Could have attached energy, attacked, and won
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0985 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":120,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced -0.1170 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1097,"playerIndex":1}]]]',))

### mega_starmie `82524455-6` (Main, wasted_resource)

- Ledger chose `[2]` Play Buddy-Buddy Poffin
- ruling was `[3]` Attach Basic {W} Energy → Staryu (active · 70/70)
- rationale: I had just played Buddy-buddy poffin and received no Staryu's back, thus i know that non are in my deck. therefor its a waste to play a second buddy'buddy poffin. that extra card in hand might come in useful later with an Ultra Ball. This requires a knowledge of what is in our deck, that should become fully known once we search it the first time. our prize cards can then be deduced from this.
- priced +0.1620 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1086,"playerIndex":1}]]]',))
- priced +0.1090 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1145,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82525101-102` (Main, sequencing_error)

- Ledger chose `[2]` Attack with Jetting Blow
- ruling was `[0]` Play Crushing Hammer
- rationale: Could have played two crushing hammers, then attacked
- priced +0.1447 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0895 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1120,"playerIndex":1}]]]',))

### mega_starmie `82525101-110` (Main, wasted_resource)

- Ledger chose `[7]` Attack with Jetting Blow
- ruling was `[4]` Attach Basic {W} Energy → Mega Starmie ex (active · 60/330 · 1⚡)
- rationale: Salvatore is worthless when no Staryu in play
- priced +0.1890 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0046 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":60,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82525101-69` (Main, sequencing_error)

- Ledger chose `[0]` Play Harlequin
- ruling was `[2]` Attach Basic {W} Energy → Mega Starmie ex (active · 60/330)
- rationale: Attach available energy to a mon who needs it prior to throwing away hand. Cards that throw away hands need a through review.
- priced +0.0267 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1223,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0670 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82525101-87` (Main, sequencing_error)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (active · 330/330 · 1⚡)
- rationale: attach energy before throwing away hand
- priced +1.3049 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0926 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82525101-92` (Main, sequencing_error)

- Ledger chose `[3]` Attack with Jetting Blow
- ruling was `[0]` Play Crushing Hammer
- rationale: Could have used two crushing hammers, attached energy, then attacked
- priced +1.3306 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0475 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82525741-100` (Main, sequencing_error)

- Ledger chose `[6]` Play Wally's Compassion
- ruling was `[10]` Attack with Jetting Blow
- rationale: Attack for the win when able
- priced +102.1490 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.1260 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))
- priced +0.0170 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82525741-58` (Main, wasted_resource)

- Ledger chose `[3]` Play Lillie's Determination
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (active · 210/330 · 1⚡)
- rationale: Boss's up Staryu will KO the Staryu, but we could have just done more damage to the main threat active starmie instead. that main threat will now just return to active will more HP than it otherwise would have had.
- priced +0.1916 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0278 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82525741-77` (Main, sequencing_error)

- Ledger chose `[6]` Play Lillie's Determination
- ruling was `[0]` Attach Basic {W} Energy → Mega Starmie ex (active · 310/430 · 1⚡)
- rationale: Attach before throwing away hand
- priced +0.1030 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0331 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82525741-78` (Main, wasted_resource)

- Ledger chose `[9]` End turn
- ruling was `[0]` Evolve Mega Starmie ex → Staryu (bench 1 · 70/70)
- rationale: From previous deck scans, we should have known that there are no Staryus left in deck, therefor save buddy buddy for possible ultra ball discard
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0044 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced -0.0906 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `82525741-81` (Main, misattachment)

- Ledger chose `[5]` End turn
- ruling was `[2]` Attach Basic {W} Energy → Mega Starmie ex (bench 1 · 330/330)
- rationale: Should have attached second energy to our active to power it up towards Nebula Beam
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0044 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced -0.1000 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82717711-37` (Main, slow_setup)

- Ledger chose `[0]` Attack with Turbo Flare
- ruling was `[1]` Retreat
- rationale: Should have free retreated to fully powered mega starmie for a Jetting Block attack.
- priced +0.9088 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1200 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))

### mega_starmie `82748422-26` (Main, wasted_resource)

- Ledger chose `[5]` Attack with Jetting Blow
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (active · 280/330 · 1⚡)
- rationale: Playing Crushing Hammer here was worthless, given that Jetting Blow will KO Cinderace. 
- priced +1.3129 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1219 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":280,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82748422-51` (Main, sequencing_error)

- Ledger chose `[1]` Play Buddy-Buddy Poffin
- ruling was `[2]` Attack with Jetting Blow
- rationale: could have just attacked for the win
- priced +103.4032 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.7710 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82748522-15` (Main, sequencing_error)

- Ledger chose `[4]` End turn
- ruling was `[1]` Play Lillie's Determination
- rationale: Hilda was not helpful here because i already had an energy and two mega starmies in hand. The opponent was a huge threat due to a nearly full bench. thus i should have played lillie's determination in hopes of filling my bench for protection.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1163 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1405 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1225,"playerIndex":0}]]]',))

### mega_starmie `82749168-21` (Main, wasted_resource)

- Ledger chose `[8]` End turn
- ruling was `[7]` Attack with Turbo Flare
- rationale: Opponents active has no energy, therefor NEVER play crushing hammer.
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.2245 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1120,"playerIndex":1}]]]',))
- priced -0.2385 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1189,"playerIndex":1}]]]',))

### mega_starmie `82749168-29` (Main, wasted_resource)

- Ledger chose `[16]` End turn
- ruling was `[10]` Play Salvatore
- rationale: Re-ruled 2026-07-28 during #177's grill. Supersedes the original 'attach Basic {W} to a Staryu' tagging (correct=[2]), reached while correcting the chosen [9] Crushing Hammer. Both readings undersold the turn: the opponent's Active, Terapagos ex, is a bare-energy wall (its own printed retreat cost is 2, and with 0 Energy attached it cannot pay that cost this turn -- it is locked in place, not merely slow) with no live attack (Unified Beatdown needs {C}{C} and scales off THEIR bench; Crown Opal needs {G}{W}{L} they don't have), while Dragapult ex on the bench (1 {R} attached, one attach short of Phantom Dive {R}{P} 200 -- 'put 6 damage counters on your opponent's Benched Pokemon') is the real clock. Chosen [9] burns Crushing Hammer for nothing (the wall holds no Energy); correct=[2] denies nothing and forgoes an available 2-prize KO.

The right line is aggressive: Salvatore (evolve a benched Staryu into Mega Starmie ex from deck -- Salvatore's own text permits evolving a body put into play this turn) -> attach Ignition Energy (provides {C}{C}{C} on an Evolution) -> retreat Cinderace (its own printed retreat cost is 0, free) -> Nebula Beam {C}{C}{C} 210 >= Terapagos ex's 130 HP, a 2-prize KO. This spends the ONE Ignition Energy that discards at end of turn regardless (its own text: 'discard it at the end of your turn'), so nothing is wasted by using it here, and it leaves Mega Starmie ex at 0 attached Energy -- accepted, because the hand still holds a SECOND Ignition Energy plus Basic {W} Energy x2 to re-arm next turn regardless of what the opponent promotes: a promoted Hoothoot (70 HP, no energy) dies to a single manual {W} attach + Jetting Blow ({W}, 120 dmg); a promoted/energized Dragapult ex is answered by the second Ignition Energy funding another Nebula Beam (210 dmg -- a serious hit, not by itself lethal to its 320 HP, but the strongest reply available and worth committing to). Crushing Hammer on Dragapult ex + a Turbo Flare develop turn (the deny+develop alternative also considered this grill) is a real, defensible line, but the resource count in hand (2 Ignition + 2 Basic {W}) means the aggressive KO-now line does not actually cost the follow-up -- being aggressive is worth it here specifically because the fuel to answer whatever gets promoted next is already in hand.

Verified at source: Mega Starmie ex's Nebula Beam is {C}{C}{C}/210, Jetting Blow {W}/120 (data/EN_Card_Data.csv id 1031); Hoothoot 70 HP, Dragapult ex 320 HP with Jet Headbutt {C}/70 and Phantom Dive {R}{P}/200 (ids 172, 121); Ignition Energy provides {C}{C}{C} on an Evolution and discards at end of turn (card_functions.json id 17: provides:1, provides_evo:3, discard_eot); Salvatore's printed text permits evolving a Pokemon put into play this turn.
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0719 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced -0.1045 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1189,"playerIndex":1}]]]',))

### mega_starmie `82749168-50` (Damage, bad_target)

- Ledger chose `[0]` opp Dragapult ex (bench 1 · 320/320)
- ruling was `[1]` opp Noctowl (bench 2 · 50/100)
- rationale: snipe for the kill if you can generally
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":320,"id":121,"maxHp":320,"playerIndex":0,"preEvolution":[{"id":119,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":50,"id":173,"maxHp":100,"playerIndex":0,"preEvolution":[{"id":172,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":172,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82749168-61` (Main, misattachment)

- Ledger chose `[9]` Attack with Jetting Blow
- ruling was `[6]` Attach Basic {W} Energy → Mega Starmie ex (active · 330/330 · 2⚡)
- rationale: Pokemon needed only single energy more to be fully powered and we had an energy in our hand. should have attached that one. the ignition energy was wasted.
- priced +1.2094 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0775 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3,3],"energyCards":[{"id":3,"playerIndex":1},{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82749168-65` (Main, wasted_resource)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[1]` Attack with Jetting Blow
- rationale: Lillie's just shuffled back our Ignition Energy, which might come in handy for our benched mega starmie. ignition energy highly valuable in this instance.
- priced +3.3371 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +2.1173 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0841 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))

### mega_starmie `82749168-88` (Main, sequencing_error)

- Ledger chose `[4]` Play Pokégear 3.0
- ruling was `[8]` Attack with Nebula Beam
- rationale: Could have just attacked for the win
- priced +101.1124 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +101.0832 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0285 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1122,"playerIndex":1}]]]',))

### mega_starmie `82749656-62` (Main, sequencing_error)

- Ledger chose `[13]` End turn
- ruling was `[12]` Attack with Jetting Blow
- rationale: For any turn, do a consideration if there is a winning move as step 1, always. if there is, take that move immediately.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0595 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.0595 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82750161-59` (Main, misattachment)

- Ledger chose `[13]` Attack with Jetting Blow
- ruling was `[1]` Attach Ignition Energy → Mega Starmie ex (bench 1 · 330/330 · 1⚡)
- rationale: Since i can KO the opponents active with jetting blow, i would have attached an energy to the benched mega starmie.
- priced +1.5827 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0070 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82751468-14` (Main, misattachment)

- Ledger chose `[5]` End turn
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (bench 1 · 330/330)
- rationale: Here, we could have attached to Mega Starmie, retreated Cinderace, and KO'd the opponents active while sniping their bench. that would have been the better move. especially since we have additional protection with Wallys Compassion in our deck
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1044 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1435 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82751468-57` (Main, missed_disruption)

- Ledger chose `[13]` Attack with Jetting Blow
- ruling was `[11]` Play Boss’s Orders
- rationale: We had already searched deck earlier in game, thus we know that one Mega Starmie is in the discard. that means this Salvatore play was a wasted use of a supporter. instead, a boss's orders could have gusted up the opponents main attacker that has no energy on it, potentially stalling them.
- priced +0.0526 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0720 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1145,"playerIndex":1}]]]',))

### mega_starmie `82752045-80` (Main, sequencing_error)

- Ledger chose `[11]` Attack with Jetting Blow
- ruling was `[8]` Play Night Stretcher
- rationale: We might as well recycle an energy to attach to our benched Mega Starmie at this point.
- priced +2.5452 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +1.1489 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82752045-94` (Main, wasted_resource)

- Ledger chose `[13]` Attack with Jetting Blow
- ruling was `[14]` Attack with Nebula Beam
- rationale: We have an enormous hand with lots of great stuff, probably never shuffle back hand greater than 7 cards. also ignition energy needs to be valued for highly when considering shuffling.
- priced +0.3940 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.2268 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82752045-97` (Main, misattachment)

- Ledger chose `[6]` Attack with Jetting Blow
- ruling was `[1]` Attach Ignition Energy → Mega Starmie ex (bench 1 · 330/330 · 1⚡)
- rationale: SHould build up the one, secondary attacker instead of spreading energy out. the one mega starmie had a single energy, the other non. keep feeding the one mega starmie until it has 3 enegry.
- priced +0.3865 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.2193 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82752604-106` (Main, sequencing_error)

- Ledger chose `[5]` Play Harlequin
- ruling was `[6]` Attack with Jetting Blow
- rationale: Attaching energy was meaningless that we could just attach and win the game.
- priced +103.3389 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.2604 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82752604-14` (Main, missed_ko)

- Ledger chose `[7]` End turn
- ruling was `[0]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: a crushing hammer must never ever ever be played when opponents active pokemon has no energy attached
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0540 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced -0.0954 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82752604-61` (Main, sequencing_error)

- Ledger chose `[3]` Attack with Jetting Blow
- ruling was `[2]` Attach Basic {W} Energy → Staryu (bench 2 · 70/70 · 1⚡)
- rationale: Should have first attached water energy, then play Mega Signal to fetch a Mega Starmie, then evolve the staryu to mega starmie, then attack
- priced +1.3761 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +1.0761 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82752604-88` (Main, sequencing_error)

- Ledger chose `[7]` Attack with Jetting Blow
- ruling was `[2]` Attach Basic {W} Energy → Mega Starmie ex (bench 2 · 270/330 · 1⚡)
- rationale: attach energy to pokemon who need it prior to attacking

Also, the opponetns active has 320 HP. one Jetting Blow + Nebula Beam = 320. thus we could have done jetting blow this turn and knocked out their benched dreepy, then performed a nebula beam the following turn to KO the Dragapult, winning the game.
- priced +1.3600 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.2100 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82753102-109` (Main, slow_setup)

- Ledger chose `[4]` Attack with Jetting Blow
- ruling was `[5]` Attack with Nebula Beam
- rationale: absolute critical blunder. had chance to KO opponents main line attacker capable of doing immense damage given the hand size of the opponent. about time we read posture.
- priced +0.9660 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.9216 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82753102-63` (Damage, bad_target)

- Ledger chose `[0]` opp Dunsparce (bench 1 · 70/70)
- ruling was `[1]` opp Abra (bench 2 · 50/50)
- rationale: reading posture will help this, but opponents main attacker is Alakazam, with abra as basic. should therefor do all possible to kill off the exposed abra on the bench.

This is a critical blunder where awareness of opponents pokemon evolution lines is a must during early game. our agent must scan opponents revealed pokemon to decide in early game who the main targets shall be.
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":305,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":50,"id":741,"maxHp":50,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82753102-9` (Main, sequencing_error)

- Ledger chose `[5]` End turn
- ruling was `[0]` Play Pokégear 3.0
- rationale: Should have played Pokegear 3.0 first in hopes of receiving a Hilda. 
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0379 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced -0.0803 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))

### mega_starmie `82754241-11` (ToHand, other)

- Ledger chose `[0]` (card)
- ruling was `[1]` (card)
- rationale: lillie's determination is typically a better pick then harlequin, especially early game when lillie's allows for drawing 8 cards.
- priced +0.0900 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[12,{"id":1223,"playerIndex":1}]]]',))
- priced +0.0900 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[12,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='decline', parts=())

### mega_starmie `82754241-12` (Main, sequencing_error)

- Ledger chose `[5]` End turn
- ruling was `[2]` Play Ultra Ball
- rationale: complete waste. we know that there are no more staryus in deck therefor this card should be discard fodder for ultra ball
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0410 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1223,"playerIndex":1}]]]',))
- priced -0.1110 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))

### mega_starmie `82754875-52` (Main, missed_disruption)

- Ledger chose `[3]` End turn
- ruling was `[0]` Play Boss’s Orders
- rationale: Here is the perfect example of gusting to stall the opponent. They have Psyduck or fezandipiti that can be gusted up, both require single energy to retreat, which could have prevented an attack by the opponent during their following turn. stalling is important for us here because we have no bench.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1535 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":130,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.2638 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))

### mega_starmie `82756021-101` (Main, sequencing_error)

- Ledger chose `[0]` Play Hilda
- ruling was `[4]` Attack with Jetting Blow
- rationale: just attack for the win and be done
- priced +103.1671 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0275 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1225,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82756021-57` (Damage, bad_target)

- Ledger chose `[0]` opp Makuhita (bench 1 · 80/80 · 1⚡)
- ruling was `[2]` opp Mega Lucario ex (bench 3 · 340/340 · 1⚡)
- rationale: Benched Mega Lucario with single energy is our next threat. should be sniping that right away. need to build in awareness of prize card math. with this opponent, we must kill 2 mega lucarios for 6 prizr cards and the win. attacking any other pokemon is a waste.
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":0}],"hp":80,"id":673,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":676,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":0}],"hp":340,"id":678,"maxHp":340,"playerIndex":0,"preEvolution":[{"id":677,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82756664-103` (Damage, bad_target)

- Ledger chose `[0]` opp Lunatone (bench 1 · 110/110)
- ruling was `[1]` opp Mega Lucario ex (bench 2 · 290/340 · 5⚡)
- rationale: Benched mega lucario is the largest imediate threat. we must snipe that
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[6,6,6,6,6],"energyCards":[{"id":6,"playerIndex":0},{"id":6,"playerIndex":0},{"id":6,"playerIndex":0},{"id":6,"playerIndex":0},{"id":6,"playerIndex":0}],"hp":290,"id":678,"maxHp":340,"playerIndex":0,"preEvolution":[{"id":677,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":0}],"hp":110,"id":676,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82756664-35` (Main, misattachment)

- Ledger chose `[8]` Play Lillie's Determination
- ruling was `[5]` Attach Basic {W} Energy → Mega Starmie ex (bench 1 · 330/330 · 2⚡)
- rationale: Prioritize fully loading a main attacker with energy over spreading out energy
- priced +0.2062 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0749 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82756664-36` (Main, sequencing_error)

- Ledger chose `[4]` Play Lillie's Determination
- ruling was `[1]` Attach Hero’s Cape → Mega Starmie ex (bench 1 · 330/330 · 2⚡)
- rationale: attach the fucking heros cape already!
- priced +0.2062 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.1524 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82756664-37` (Main, bad_retreat)

- Ledger chose `[2]` Attack with Turbo Flare
- ruling was `[3]` Retreat
- rationale: Should retreat to Mega Starmie for the KO and snipe the powered up Riolu
- priced +0.1537 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1125 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))

### mega_starmie `82756664-74` (Main, wasted_resource)

- Ledger chose `[17]` End turn
- ruling was `[3]` Attach Ignition Energy → Mega Starmie ex (active · 30/330)
- rationale: Hilda was pointless given we have 2 energy in hand and know that 3rd mega starmie is in prize cards
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0670 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced -0.1026 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":17,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":30,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82756664-9` (Main, sequencing_error)

- Ledger chose `[2]` Play Lillie's Determination
- ruling was `[1]` Attach Hero’s Cape → Staryu (bench 1 · 70/70)
- rationale: best not to shuffle back a heros cape when we are able to use it. plus, next turn we can evolve to mega starmie with 3 energy due to Turbo Flare energy acceleration. this, albeit small, is a very good opening hand.
- priced +0.1672 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0136 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82756664-97` (ToActive, missed_disruption)

- Ledger chose `[1]` Mega Starmie ex (bench 2 · 330/330 · 1⚡)
- ruling was `[0]` Cinderace (bench 1 · 30/130 · 1⚡)
- rationale: Here is a great example of more nuanced play strategy. the opponents active has less than 50HP and our benched Mega Starmie has less than 3 energy. perfect situation to promote Cinderace, KO opponents active for 3 prize cards, and energy accelerate our mega starmie. This requires forward search i imagine. but we need to be able to spot moves like this.
- priced +0.0600 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0600 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0480 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":30,"id":666,"maxHp":130,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82866415-43` (Main, wasted_resource)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[2]` Attach Hero’s Cape → Mega Starmie ex (active · 280/330 · 3⚡)
- rationale: Attach the fucking cape before shuffling!!
- priced +0.2310 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.1480 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.1050 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))

### mega_starmie `82866415-48` (Main, sequencing_error)

- Ledger chose `[5]` Attack with Jetting Blow
- ruling was `[3]` Attach Hero’s Cape → Staryu (bench 1 · 70/70 · 1⚡)
- rationale: There is a clear bug with our ACE-SPEC Hero's Cape. here it should be attached to the benched Staryu with a single energy as to protect it from Jetting Blow
- priced +0.2235 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0975 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82867148-48` (Discard, sequencing_error)

- Ledger chose `[7, 8]` Basic {W} Energy, Basic {W} Energy
- ruling was `[1]` Lillie's Determination
- rationale: CRITICAL: gave away boss's orders and Harlequin, key disruptors when we had two copies of lillie's and three mega starmies. discarding should weigh discarding duplicate hards more heavily
- priced +0.2966 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":3,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":3,"playerIndex":0}]]]'))
- priced +0.2807 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1031,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":3,"playerIndex":0}]]]'))
- priced +0.2136 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1227,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":3,"playerIndex":0}]]]'))

### mega_starmie `82867148-62` (Main, bad_retreat)

- Ledger chose `[7]` Play Buddy-Buddy Poffin
- ruling was `[8]` Attack with Turbo Flare
- rationale: CRITICAL: Should almost never retreat Cinderace into a Staryu with so many energies
- priced +1.2460 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.2215 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82867148-87` (Main, bad_retreat)

- Ledger chose `[12]` End turn
- ruling was `[8]` Attach Basic {W} Energy → Staryu (bench 2 · 70/70)
- rationale: Typically should attch energy to staryu
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0068 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced -0.0325 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `83007714-135` (Main, slow_setup)

- Ledger chose `[1]` Play Night Stretcher
- ruling was `[9]` Attack with Nebula Beam
- rationale: Again, many other corrections state this, we need a hard rule that every single turn begins by analyzing if there is a match winning decision present. if there is, take it immediately to win the match.
- priced +102.0243 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.1405 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1097,"playerIndex":1}]]]',))
- priced +0.0631 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))

### mega_starmie `83007714-22` (AttachFrom, misattachment)

- Ledger chose `[0]` Staryu (bench 1 · 70/70 · 1⚡)
- ruling was `[1]` Mega Starmie ex (bench 2 · 330/330)
- rationale: CRITICAL: you attached 3 energy to Staryu instead of making sure that our Mega Starmie had 3 energy. attach the energy to our evolved mainline attacker as priority over the preevolution
- priced +0.0850 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.0150 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `83007714-7` (Main, misattachment)

- Ledger chose `[6]` End turn
- ruling was `[1]` Attach Ignition Energy → Cinderace (active · 160/160)
- rationale: CRITICAL: this is a regression, used to be fixed. In SETUP stage, Cinderace leasding with Staryu on bench. this is perfect. Cinderace must get the energy here.
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0775 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))
- priced -0.0999 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `83037962-48` (Main, misattachment)

- Ledger chose `[8]` Attack with Jetting Blow
- ruling was `[3]` Attach Basic {W} Energy → Staryu (bench 1 · 70/70)
- rationale: CRITICAL: Placed second energy on active doomed mega starmie. this deosnt allow it to attack with Nebula Beam, and we can see that opponent can perhaps use an ignition energy to be able to do Nebula Beam and kill us next turn. we must assume that worst case scenario. therefor should start powering up our reserve benched staryu
- priced +0.2010 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0186 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))

### mega_starmie `83037962-49` (Main, misattachment)

- Ledger chose `[1]` Play Harlequin
- ruling was `[2]` Attack with Jetting Blow
- rationale: CRITICAL: shuffle logic needs work. here we disrupt our opponent, which is good. however we also give back a Mega Starmie AND an energy that we need next turn. poor gamble in my opinion
- priced +0.2010 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0286 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `83037962-78` (Main, missed_win)

- Ledger chose `[6]` Play Wally's Compassion
- ruling was `[9]` Attack with Nebula Beam
- rationale: CRITICAL: playing Wallys Compassion has a COST that must be considered. we remove all energy from our wincon and heal them. but now we are no longer able to KO the opponent and win the match. huge blunder. Wallys Compassion usage cost must be considered along with whether or not we have an Ignition Energy in hand.
- priced +103.1820 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.2723 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))
- priced +0.0843 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))

### mega_starmie `83038055-40` (Main, sequencing_error)

- Ledger chose `[5]` Attack with Nebula Beam
- ruling was `[0]` Play Lillie's Determination
- rationale: we desperately need a bench at this point, so id use lillie's to draw
- priced +3.2956 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.1837 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `83038055-51` (Main, sequencing_error)

- Ledger chose `[1]` Play Mega Signal
- ruling was `[3]` Attack with Nebula Beam
- rationale: Here our hand is quite strong for next turn, would not have shuffled it back. Shuffling requires an awareness of our hand strength for the following turn
- priced +0.2571 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.1403 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0585 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))

### mega_starmie `83053965-28` (Main, wasted_resource)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[2]` Play Hilda
- rationale: CRITICAL: Our agent needs to start planning its turn ahead of time, mapping out potential outcomes, and then picking best path. if it did so, it would have seen that it can KO opponents active via Hilda for energy grab, attach to mega starmie, retreat to mega starmie, and jetting blow.
- priced +0.1108 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1580 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1120,"playerIndex":1}]]]',))

### mega_starmie `83053965-32` (Main, misattachment)

- Ledger chose `[4]` End turn
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (bench 1 · 330/330)
- rationale: CRITICAL - Should have retreated Cinderace, attached to Meta Starmie, and KO'd opponents active
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0863 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":150,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1015 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `83053965-91` (Main, sequencing_error)

- Ledger chose `[12]` Attack with Turbo Flare
- ruling was `[13]` Retreat
- rationale: CRITICAL: This is another multi decision example showing that we need a turn planner system. it would have been better to retreat cinderance into mega starmie, attach 3rd energy, KO fezandipiti for 2 prize cards. 
- priced +0.0997 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0100 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[3,3],"energyCards":[{"id":3,"playerIndex":1},{"id":3,"playerIndex":1}],"hp":430,"id":1031,"maxHp":430,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[{"id":1159,"playerIndex":1}]}]]]',))

### mega_starmie `83116081-76` (Main, other)

- Ledger chose `[2]` Play Buddy-Buddy Poffin
- ruling was `[5]` Play Wally's Compassion
- rationale: CRITICAL: Our active wincon was low on health and opponent could possibly KO it next turn. also, opponents active was KO'able with our Jetting Blow. Should have healed with Wally, attached single energy, KO opponent
- priced +2.8802 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.2780 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `83116501-70` (Main, wasted_resource)

- Ledger chose `[25]` End turn
- ruling was `[7]` Attach Basic {W} Energy → Mega Starmie ex (active · 330/330)
- rationale: Here, 120 dmg with Jetting Blow + 50 dmg to benched rioulu is perferrable given that Nebula Beam will not KO Mega Lucario anyways
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0510 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced -0.0705 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `83116501-89` (Main, misattachment)

- Ledger chose `[23]` Attack with Jetting Blow
- ruling was `[2]` Attach Ignition Energy → Mega Starmie ex (bench 1 · 330/330 · 1⚡)
- rationale: CRITICAL: We should not spread out our energy until either main attacker or backup attacker have full energy. for this deck, that means 3 energy to Mega Starmie
- priced +0.2310 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0025 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `83117367-34` (Main, other)

- Ledger chose `[6]` End turn
- ruling was `[2]` Play Harlequin
- rationale: CRITICAL: Via Hilda, we have searched out deck. thus we know that there is a single Mega Starmie in our prize cards and non in deck. therefor Salvatore is a waste. a rule must be made that checking deck contents must be performed prior to any search card.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0836 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced -0.0900 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))

### mega_starmie `83117367-45` (Main, other)

- Ledger chose `[1]` Play Harlequin
- ruling was `[0]` Play Lillie's Determination
- rationale: CRITICAL: Via Hilda, we have searched out deck. thus we know that there is a single Mega Starmie in our prize cards and non in deck. therefor Salvatore is a waste. a rule must be made that checking deck contents must be performed prior to any search card.

PLUS, we need energy! CRITICAL CRITICAL
- priced +0.2164 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))
- priced +0.1683 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `83456015-35` (Main, sequencing_error)

- Ledger chose `[13]` Attack with Jetting Blow
- ruling was `[3]` Play Wally's Compassion
- rationale: CRITICAL: This is critical because of sequencing. Our opponent has mega starmie that can do 210 dmg. our active has 210 HP. the opponent's deck commonly runs ignition energy, thus we should prepare ourselves for that by healing first, then attaching Ignition Energy ourselves, then attacking for KO. Also might as well play the pokegear 3.0 before attaching.
- priced +0.2310 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0684 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `83457493-20` (Main, wrong_supporter)

- Ledger chose `[0]` Play Salvatore
- ruling was `[3]` Play Boss’s Orders
- rationale: We do not have energy to power Cinderace, thus we are behind in tempo. The Salvatore however nice, doesnt help our immediate turn. we need to stall our opponent here given the real risk they evolve into Mega Lucario and KO our Cinderace, putting us even further behind. 

Boss's Orders up their benched mon with hghest retreat cost and least amount of energy and lowest threat. That is Makuhita 
- priced +0.0440 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1189,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1434 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))

### mega_starmie `83661649-30` (Main, wrong_attack)

- Ledger chose `[0]` Play Harlequin
- ruling was `[2]` Attack with Jetting Blow
- rationale: Jetting Blow is better here to do some bench sniping because Nebula Beam will not KO them anyway. and one jetting blow + one nebula beam will KO them. also, worth anticipating that they will use wally compassion to fully heal.
- priced +0.1890 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0698 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))
- priced +0.0630 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))

### mega_starmie `83661649-45` (Damage, bad_target)

- Ledger chose `[0]` opp Staryu (bench 1 · 70/70 · 1⚡)
- ruling was `[1]` opp Mega Starmie ex (bench 2 · 430/430)
- rationale: wasteful attacking staryu when we know that they will promote mega starmie next.
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":430,"id":1031,"maxHp":430,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[{"id":1159,"playerIndex":1}]}]]]',))

### mega_starmie `83661649-54` (Main, sequencing_error)

- Ledger chose `[13]` Attack with Jetting Blow
- ruling was `[4]` Attach Basic {W} Energy → Mega Starmie ex (active · 210/330 · 1⚡)
- rationale: CRITICAL: Should absolutely attach energy here before attacking. attach basic in preparation for nebula beam next turn.
- priced +1.3095 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0432 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":230,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `83662396-19` (Main, sequencing_error)

- Ledger chose `[1]` Attack with Turbo Flare
- ruling was `[0]` Play Mega Signal
- rationale: should pull out a mega starmie here just to thin the deck.
- priced +0.9616 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1380 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1145,"playerIndex":1}]]]',))

### mega_starmie `83664340-45` (Main, misattachment)

- Ledger chose `[12]` End turn
- ruling was `[0]` Attach Basic {W} Energy → Mega Starmie ex (active · 60/330)
- rationale: This conflicts with dont-feed-the-doomed but is still the better option. we need to keep pressure on our opponent by attacking and bench sniping. next turn we have both basic and ignition energy, thus we can keep attacking with our follow up Starmie. in this case, its better to feed the dammed.
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0700 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced -0.0700 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `83664991-25` (Main, sequencing_error)

- Ledger chose `[5]` Attack with Turbo Flare
- ruling was `[2]` Evolve Mega Starmie ex → Staryu (bench 1 · 70/70 · 3⚡)
- rationale: Here, given that we have two mega starmies, i would have evolved the one with energy and then played harlequin for disruption. we can see that we are able to rush up with starmie to KO active plus bench snipe, therefor we should go into sprint mode hoping to get a quick win.
- priced +0.0642 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0892 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `83664991-43` (Main, sequencing_error)

- Ledger chose `[1]` Play Harlequin
- ruling was `[3]` Attack with Turbo Flare
- rationale: CRITICAL: This was a missed opportunity for prize math in our favor. save the ignition energy for next turn and chip them a bit with Cinderace. Also, opponent has 8 cards in hand, a perfect time to play Harlequin.
- priced +0.0640 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0245 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))

### mega_starmie `83665798-12` (Main, wasted_resource)

- Ledger chose `[0]` Play Mega Signal
- ruling was `[7]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: CRITICAL: Our Cinderace is not in danger here, therefor using Heros Cape here was a waste.
- priced +0.0760 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1145,"playerIndex":1}]]]',))
- priced +0.0274 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `83665798-39` (Main, missed_win)

- Ledger chose `[3]` Play Lillie's Determination
- ruling was `[4]` Attack with Jetting Blow
- rationale: no reason to play lillies here, just attack for win. i think that the lethal line needs to be able to consider multiple decisions to a victory, then to take the shortest path.
- priced +102.3317 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.8802 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.1407 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))

### mega_starmie `83667237-107` (Damage, bad_target)

- Ledger chose `[0]` opp Lunatone (bench 1 · 110/110)
- ruling was `[3]` opp Makuhita (bench 4 · 80/80)
- rationale: This requires planning out prize math against the opponent. We need 4 prize cards, that is a mega Lucario + 1. thus no reason to snipe the second mega lucario. we actually want to avoid that one. we can do so thanks to boss's orders in future turns.
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[6,6],"energyCards":[{"id":6,"playerIndex":1},{"id":6,"playerIndex":1}],"hp":340,"id":678,"maxHp":340,"playerIndex":1,"preEvolution":[{"id":677,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":1}],"hp":150,"id":674,"maxHp":150,"playerIndex":1,"preEvolution":[{"id":673,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `83667237-87` (Main, sequencing_error)

- Ledger chose `[4]` Attack with Jetting Blow
- ruling was `[2]` Play Night Stretcher
- rationale: CRITICAL: We have a Staryu in the discard pile, the whole reason for Night Stretcher! gotta keep our bench filled. When they KO our Starmie, they will still need a single prize card left, perfect for our second Starmie in future turns.
- priced +1.5343 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.1510 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1097,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `83966968-78` (Main, wrong_supporter)

- Ledger chose `[13]` Attack with Jetting Blow
- ruling was `[2]` Play Harlequin
- rationale: CRITICAL: Its highly important that we evolve our benched staryu or we risk loses a second mega starmie. deck has one mega starmie and 3 mega signals and 2 savaltores and 2 hildas. lots of chances that lead to mega starmie.
- priced +0.0151 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1525 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":210,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `83966968-79` (Switch, bad_target)

- Ledger chose `[0]` opp Cinderace (bench 1 · 110/160)
- ruling was `[1]` opp Mega Starmie ex (bench 2 · 230/330)
- rationale: CRITICAL: Concerning prize math, KO'ing a Cinderace does not help us. we still need to KO 2 mega starmies. 
- priced -0.1429 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1431 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":230,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced -0.2090 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `83967840-54` (Discard, wasted_resource)

- Ledger chose `[1, 4]` Salvatore, Salvatore
- ruling was `[2]` Lillie's Determination
- rationale: i would have discarded one of our lillie's given that we have 2 in hand
- priced +0.0445 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1189,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":1189,"playerIndex":0}]]]'))
- priced +0.0125 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1189,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":666,"playerIndex":0}]]]'))
- priced -0.0305 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1189,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":1227,"playerIndex":0}]]]'))

### mega_starmie `84897262-110` (ToHand, missed_win)

- Ledger chose `[0]` Staryu
- ruling was `[1]` Basic {W} Energy
- rationale: Grab energy first, attach to active, attack, win match
- priced +0.2400 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[3,{"id":1030,"playerIndex":1}]]]',))
- priced +0.0200 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[3,{"id":3,"playerIndex":1}]]]',))
- priced -0.0070 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[3,{"id":1031,"playerIndex":1}]]]',))

### mega_starmie `85163079-30` (Main, missed_win)

- Ledger chose `[2]` Attack with Jetting Blow
- ruling was `[0]` Play Boss’s Orders
- rationale: Should have gusted up their future wincon and KO it
- priced +1.5806 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +1.2106 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `85163079-51` (Main, missed_win)

- Ledger chose `[3]` Attack with Jetting Blow
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (active · 210/330 · 2⚡)
- rationale: Too conservative to attach energy to Cinderace. Our Mega Starmie is lost next turn, so be it, hit the opponent with everything we got and hope for an opportunity next turn.
- priced +0.0061 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0850 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3,3],"energyCards":[{"id":3,"playerIndex":0},{"id":3,"playerIndex":0}],"hp":210,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `85163634-17` (Main, missed_win)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[5]` Attack with Turbo Flare
- rationale: Only issue with this blunder is that this move was taken one turn too early. we dont need the Starmie now. fetching it now risks enticing our opponent to disrupt us with a judge or harlequin or something. there is no cost to just wait a turn and fetch our Starmie then.
- priced +0.0716 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0791 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))

### mega_starmie `85163634-41` (Main, wasted_resource)

- Ledger chose `[5]` Attack with Nebula Beam
- ruling was `[0]` Play Lillie's Determination
- rationale: CRITICAL: For the love of god, we are going to KO the active, no other opp pokemon has energy, so why waste the crushing hammer????

I say would rather play Lillie's because our hand is a little dead and we should look for energy to attach to our benched Starmie.
- priced +2.3829 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0848 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `85164131-22` (Damage, wasted_resource)

- Ledger chose `[0]` opp Cinderace (bench 1 · 260/260 · 1⚡)
- ruling was `[1]` opp Staryu (bench 2 · 70/70)
- rationale: CRITICAL: We dont care at all about the benched Cinderace. Our Starmie can OHKO it whenever its promoted. we need to stomp out the next big threat, the opponents eventual win condition.

Our matchup Posture feature should have caught this. needs review!
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":260,"id":666,"maxHp":260,"playerIndex":0,"preEvolution":[],"tools":[{"id":1159,"playerIndex":0}]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `85164605-6` (Main, wasted_resource)

- Ledger chose `[3]` End turn
- ruling was `[0]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: fetching a Mega Starmie here doesnt help us, rather just not do it.
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0804 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.1235 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1145,"playerIndex":1}]]]',))

### mega_starmie `85164605-64` (Main, wasted_resource)

- Ledger chose `[3]` Play Ultra Ball
- ruling was `[5]` Attack with Jetting Blow
- rationale: CRITICAL: Played Ultra ball for nothing. MUST check deck and discard and prize cards prior to playing fetch cards always, as to verify what exists.
- priced +2.0155 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.9205 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0376 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))

### mega_starmie `85164605-68` (Damage, bad_target)

- Ledger chose `[0]` opp Kadabra (bench 1 · 80/80)
- ruling was `[2]` opp Abra (bench 3 · 50/50)
- rationale: Our Mega Starmie can OHKO their strongest attacker, Alakazam, which pilot should know immediatly upon match start when matchup reads opponent. Thus go for the snipe-KO on Abra.
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":742,"maxHp":80,"playerIndex":0,"preEvolution":[{"id":741,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":60,"id":65,"maxHp":60,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":50,"id":741,"maxHp":50,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `91393233-9` (Main, sequencing_error)

- Ledger chose `[1]` Play Lillie's Determination
- ruling was `[3]` Attach Basic {W} Energy → Staryu (active · 70/70)
- rationale: CRITICAL: Play "free" cards that give us more information and a better board state, thus buddy buddy poffin and pokegear.

Also a failed calculation by PLANNED gamble. it states 71% chance to get a Mega Starmie to win the game. but it forgot that Mega Starmie also requires energy AND we can only evolve our Staryu via Salvatore this turn. Thus fetching Salvatore is our only win possibility.
- priced +0.1394 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.1140 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `91393371-60` (Main, sequencing_error)

- Ledger chose `[1]` Play Wally's Compassion
- ruling was `[5]` Play Pokégear 3.0
- rationale: 
- priced +0.1793 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0957 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0326 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1229,"playerIndex":1}]]]',))

### mega_starmie `91393371-9` (Main, sequencing_error)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[4]` Play Pokégear 3.0
- rationale: CRITICAL: Collect information before commiting our supporter. play Pokegear, and if we got a Hilda, we could have used that to fetch a basic energy as to not use our ignition energy.
- priced +0.0361 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0880 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":17,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `91394270-102` (ToActive, sequencing_error)

- Ledger chose `[0]` Mega Starmie ex (bench 1 · 270/330)
- ruling was `[1]` Cinderace (bench 2 · 160/160)
- rationale: Promote Cinderace. we can always retreat him from free during turn depending on the card that we draw.
- priced +0.0320 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":270,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0320 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":10,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0284 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `91394270-12` (Main, sequencing_error)

- Ledger chose `[4]` End turn
- ruling was `[0]` Play Pokégear 3.0
- rationale: CRITICAL: Why our ideal starter?
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0660 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced -0.1182 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `91394270-85` (Main, sequencing_error)

- Ledger chose `[0]` Play Wally's Compassion
- ruling was `[]` 
- rationale: CRITICAL: 
- priced +0.1650 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))
- priced +0.1168 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1030,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `91394270-9` (Main, sequencing_error)

- Ledger chose `[3]` Play Mega Signal
- ruling was `[2]` Play Pokégear 3.0
- rationale: CRITICAL: Obtain free information with Pokegear. if it finds Hilda, we then can fetch an energy for our Cinderace. We dont need a Starmie now anyways, we have a Mega Signal, which is cheaper to use than Salvatore.
- priced +0.0640 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0910 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))

### mega_starmie `92091149-14` (Main, missed_win)

- Ledger chose `[4]` End turn
- ruling was `[]` 
- rationale: CRITICAL: didnt attack when had the chance
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0050 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced -0.0510 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1145,"playerIndex":1}]]]',))

### mega_starmie `92091149-33` (Main, missed_win)

- Ledger chose `[4]` Attack with Jetting Blow
- ruling was `[2]` Play Staryu
- rationale: CRITICAL: bench our staryu in hand first before shuffling it away with lillies
- priced +0.9942 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0250 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1030,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='ability', parts=('[{"area":7,"index":0,"type":10},[]]',))

### mega_starmie `92091149-37` (Main, missed_win)

- Ledger chose `[1]` Attack with Jetting Blow
- ruling was `[0]` Play Buddy-Buddy Poffin
- rationale: CRITICAL: Should have fetched two staryu's with buddy buddy poffin and then attacked with Jetting Blow. Snipe Marnies Morgrem.
- priced +1.0512 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.7600 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1086,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `92091149-60` (Main, missed_win)

- Ledger chose `[3]` Play Buddy-Buddy Poffin
- ruling was `[]` 
- rationale: 
- priced +0.7555 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1086,"playerIndex":1}]]]',))
- priced +0.0202 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1229,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='ability', parts=('[{"area":7,"index":0,"type":10},[]]',))

### mega_starmie `92092096-21` (Main, missed_win)

- Ledger chose `[6]` End turn
- ruling was `[3]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: CRITICAL: Our Cinderace needs to attack to apply pressure and to accelerate energy,
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0625 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))
- priced -0.1074 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `92102433-10` (Main, missed_win)

- Ledger chose `[6]` Play Staryu
- ruling was `[]` 
- rationale: I would have sprinted here for aggression. this deck thrives by taking its time to build up a large hand and thus do huge damage.

We have an ignition energy in hand and a savlatore. that ignition energy discards at end of turn, a disadvantage, however we also have lillies which can most likely shuffle up another energy source next turn, we hope. its an odds question
- priced +0.0085 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1030,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1471 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":17,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `92102433-89` (ToActive, missed_win)

- Ledger chose `[1]` Mega Starmie ex (bench 2 · 330/330 · 1⚡)
- ruling was `[0]` Cinderace (bench 1 · 160/160)
- rationale: CRITICAL: They have a stadium in play that prevents damage done to non-rule box. this means we cannot damage their pokemon except for with mega starmie's nebula beam, which ignores effects. thus we promoto Cinderace, attach energy, attack with Turbo Flare and give 2 eneergy to starmie giving it a total of 3 for Nebula Beam next turn
- priced +0.0600 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0320 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0284 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `92103403-10` (Main, sequencing_error)

- Ledger chose `[5]` End turn
- ruling was `[2]` Play Pokégear 3.0
- rationale: fetch information before commiting to a move.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1031 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))
- priced -0.1755 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))

### mega_starmie `92104376-60` (Main, wasted_resource)

- Ledger chose `[5]` Play Lillie's Determination
- ruling was `[7]` Attack with Jetting Blow
- rationale: Our active is not doomed. Just attack and snipe one of their Riolus
- priced +1.1918 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0391 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `92104376-7` (Main, sequencing_error)

- Ledger chose `[0]` Play Buddy-Buddy Poffin
- ruling was `[]` 
- rationale: CRITICAL: Threat Solver missed this one, but perhaps it no longer fires with the Bellman system.
- priced +0.5690 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1086,"playerIndex":1}]]]',))
- priced +0.1330 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1030,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `92104376-81` (Main, wasted_resource)

- Ledger chose `[5]` Play Lillie's Determination
- ruling was `[]` 
- rationale: develop before attacking.
- priced +0.1073 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0075 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `92104376-86` (ToActive, prize_mismanagement)

- Ledger chose `[1]` Mega Starmie ex (bench 2 · 330/330)
- ruling was `[0]` Cinderace (bench 1 · 160/160)
- rationale: CRITICAL: for this deck, we want opponent to take out a starmie, cinderace, and one more starmie for 7 total prize cards. here we could have promoted cinderace, attached to him, attacked, getting our benched starmie to 3 energy while putting their mega lucario into KO range.
- priced +0.0320 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0320 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0284 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `92129564-22` (Main, sequencing_error)

- Ledger chose `[0]` Play Mega Signal
- ruling was `[1]` Attack with Water Gun
- rationale: why not attack?
- priced +0.1090 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1670 ActionIdentity(kind='attack', parts=('[0,{"attackId":1486,"type":13},[]]',))

### mega_starmie `92130512-12` (Main, sequencing_error)

- Ledger chose `[1]` Play Lillie's Determination
- ruling was `[2]` Play Salvatore
- rationale: CRITICAL: evolve our benched staryu when we can. this is about being aggresive when able
- priced +0.1818 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0055 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `92131448-22` (Main, misattachment)

- Ledger chose `[6]` Play Staryu
- ruling was `[]` 
- rationale: CRITICAL: KO their active AND benched wincon preevolutions
- priced +0.0310 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1030,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0035 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))

### mega_starmie `92131448-44` (Discard, misattachment)

- Ledger chose `[0, 5]` Salvatore, Ignition Energy
- ruling was `[0, 1]` Salvatore, Mega Signal
- rationale: given a mega starmie and salvatore in hand, we can discard the second salvatore and mega signal. crushing hammer is useful during this turn.
- priced +0.0780 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1189,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":17,"playerIndex":0}]]]'))
- priced +0.0780 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1145,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":17,"playerIndex":0}]]]'))
- priced +0.0700 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1145,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":1189,"playerIndex":0}]]]'))

### mega_starmie `92131448-8` (Main, misattachment)

- Ledger chose `[7]` End turn
- ruling was `[]` 
- rationale: CRITICAL: you missed a win
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0275 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))
- priced -0.0729 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `92455378-14` (Main, slow_setup)

- Ledger chose `[5]` Play Buddy-Buddy Poffin
- ruling was `[3, 5]` Play Pokégear 3.0, Play Buddy-Buddy Poffin
- rationale: Collect free information first with pokegear and buddy buddy. would be nice to find a hilda
- priced +0.1545 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0887 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `92455378-35` (Main, wasted_resource)

- Ledger chose `[5]` End turn
- ruling was `[3]` Attach Basic {W} Energy → Mega Starmie ex (active · 280/330)
- rationale: dont need to heal here, wasteful
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0496 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":280,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced -0.0670 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `92455378-89` (Main, sequencing_error)

- Ledger chose `[3]` Play Night Stretcher
- ruling was `[]` 
- rationale: 
- priced +0.1330 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1097,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0336 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `92457318-25` (Main, wrong_attack)

- Ledger chose `[2]` End turn
- ruling was `[0]` Attack with Water Gun
- rationale: CRITICAL: why not attack?
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1520 ActionIdentity(kind='attack', parts=('[0,{"attackId":1486,"type":13},[]]',))
- priced -0.2545 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))

### mega_starmie `92457318-44` (Main, sequencing_error)

- Ledger chose `[3]` Play Lillie's Determination
- ruling was `[]` 
- rationale: CRITICAL: Played lillies when had ability to attach energy and play an item first.
- priced +0.0484 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0700 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `92458248-23` (Main, sequencing_error)

- Ledger chose `[6]` Play Mega Signal
- ruling was `[0]` Play Pokégear 3.0
- rationale: CRITICAL: Again, game froze on my turn, HUGE ISSUE!
- priced +0.1165 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced +0.0052 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `92459166-125` (Main, misattachment)

- Ledger chose `[6]` End turn
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (active · 330/330)
- rationale: CRITICAL: This is such an enormous blunder, energy attachment valuing has a bug. our benched weakened starmie has full energy of 3, and you attach there instead of to our active full HP starmie with 0 energy.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0540 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced -0.0642 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))

### mega_starmie `92459166-82` (Main, sequencing_error)

- Ledger chose `[1]` Attack with Jetting Blow
- ruling was `[0]` Play Crushing Hammer
- rationale: play the available hammer first before attacking
- priced +1.1061 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1765 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1120,"playerIndex":0}]]]',))

### mega_starmie `92459166-92` (Main, sequencing_error)

- Ledger chose `[0]` Play Wally's Compassion
- ruling was `[]` 
- rationale: 
- priced +0.1411 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.1218 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))
- priced +0.0760 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1097,"playerIndex":0}]]]',))

### mega_starmie `92591287-35` (Main, wasted_resource)

- Ledger chose `[2]` End turn
- ruling was `[0]` Attack with Nebula Beam
- rationale: CRITICAL: There appears to be an issue with not attack when we have the available energy still. our mirror is attacking with Nebula Beam when it has ignition energy attacked with also a single water basic energy, is that the issue? is the colorless only energy not being considered satisfiable by Nebua Beam, which it is?
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0782 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced -0.2686 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))

### mega_starmie `92591287-49` (Main, wasted_resource)

- Ledger chose `[5]` End turn
- ruling was `[3]` Attack with Nebula Beam
- rationale: CRITICAL: Save blunder as this matches other frame.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0708 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced -0.1320 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))

### mega_starmie `92591287-60` (Main, wasted_resource)

- Ledger chose `[4]` Attack with Turbo Flare
- ruling was `[0]` Play Salvatore
- rationale: CRITICAL: Wallys to heal 50HP is a waste. just fetch and evolve another starmie instead
- priced +0.0781 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0585 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))

### mega_starmie `92591287-73` (EvolvesTo, slow_setup)

- Ledger chose `[]` 
- ruling was `[0]` Mega Starmie ex
- rationale: CRITICAL: We need to analyze what happened here, because the result is confusing. We played Salvatore when we had a Mega Starmie in deck, though non was fetched or evolved.
- priced -0.1320 ActionIdentity(kind='decline', parts=())
- priced -0.4158 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1031,"playerIndex":0}]]]',))

### mega_starmie `92591287-87` (Main, wasted_resource)

- Ledger chose `[3]` End turn
- ruling was `[1]` Play Crushing Hammer
- rationale: CRITICAL: you shuffled away a useful crushing hammer
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0033 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))
- priced -0.0108 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))

### mega_starmie `92644488-14` (Main, sequencing_error)

- Ledger chose `[2]` End turn
- ruling was `[0]` Play Pokégear 3.0
- rationale: CRITICAL: Play Pokegear first. we hope to fetch a Hilda as to fetch an energy
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0710 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))
- priced -0.0790 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `92645419-116` (Main, sequencing_error)

- Ledger chose `[2]` Attack with Jetting Blow
- ruling was `[]` 
- rationale: awkward sequencing
- priced +3.2065 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0377 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1223,"playerIndex":1}]]]',))

### mega_starmie `92645419-127` (AttachFrom, misattachment)

- Ledger chose `[0]` Mega Starmie ex (bench 1 · 20/330 · 1⚡)
- ruling was `[1]` Mega Starmie ex (bench 2 · 330/330)
- rationale: CRITICAL: dont attach energy to our 20HP starmie when we have two other full HP starmies next to it
- priced +0.0192 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":20,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced -0.0150 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced -0.0150 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `92645419-129` (AttachFrom, misattachment)

- Ledger chose `[0]` Mega Starmie ex (bench 1 · 20/330 · 3⚡)
- ruling was `[1]` Mega Starmie ex (bench 2 · 330/330)
- rationale: CRITICAL: never attach energy not required to a pokemon. here, you just attached a 4th energy to starmie that needs max 3
- priced +0.0192 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3,3,3],"energyCards":[{"id":3,"playerIndex":1},{"id":3,"playerIndex":1},{"id":3,"playerIndex":1}],"hp":20,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced -0.0150 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced -0.0150 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `92645419-21` (Main, slow_setup)

- Ledger chose `[1]` Attack with Turbo Flare
- ruling was `[0]` Play Pokégear 3.0
- rationale: CRITICAL: play the pokegear
- priced +0.0655 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1006 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1122,"playerIndex":1}]]]',))

### mega_starmie `92645419-25` (AttachFrom, misattachment)

- Ledger chose `[0]` Staryu (bench 1 · 70/70 · 2⚡)
- ruling was `[1]` Staryu (bench 2 · 70/70)
- rationale: with this board setup, where their active is doomed during our next turn, i would diversify energy a little by placing 2 energy on one staryu and one on another 
- priced +0.0850 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":true,"energies":[3,3],"energyCards":[{"id":3,"playerIndex":1},{"id":3,"playerIndex":1}],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.0150 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `92645419-36` (Main, misattachment)

- Ledger chose `[4]` Attack with Turbo Flare
- ruling was `[0]` Evolve Mega Starmie ex → Staryu (bench 1 · 70/70 · 3⚡)
- rationale: CRITICAL: evolve the staryu with full energy. 
- priced +0.9266 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1089 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1122,"playerIndex":1}]]]',))

### mega_starmie `92645419-64` (Main, wasted_resource)

- Ledger chose `[2]` Attack with Jetting Blow
- ruling was `[3]` Attack with Nebula Beam
- rationale: CRITICAL: Nebula Beam converts the doomed active into 210 damage and starts the faster prize line; healing delays damage and increases Resentful Refrain.
- priced +0.0349 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.1393 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))

### mega_starmie `92646350-20` (Main, sequencing_error)

- Ledger chose `[4]` End turn
- ruling was `[0]` Play Pokégear 3.0
- rationale: CRITICAL: we really need staryus here, such that Cinderaces Turbo Flare attack clearly needs some sort of label OR we can add a deck specific strategy to state this fact. in this way, we must gamble for getting a staryu at all cost. thus pokegear and hope to get lillies, if no lillies, play Harlequin
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0906 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))
- priced -0.1132 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `92646350-34` (Main, sequencing_error)

- Ledger chose `[5]` Attack with Turbo Flare
- ruling was `[0]` Play Harlequin
- rationale: CRITICAL: must gamble for staryus
- priced +0.8503 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='ability', parts=('[{"area":7,"index":0,"type":10},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `92646350-79` (Main, misattachment)

- Ledger chose `[1]` Play Harlequin
- ruling was `[8]` Attack with Nebula Beam
- rationale: CRITICAL: never waste an energy attaching to pokemon that has no use for it
- priced +0.1978 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='ability', parts=('[{"area":7,"index":0,"type":10},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `92708809-20` (Main, sequencing_error)

- Ledger chose `[8]` End turn
- ruling was `[0]` Play Pokégear 3.0
- rationale: CRITICAL: Dont commit with something so valuable as an ignition energy before using our free Pokegears. Also, the staryu already has an energy and can attack!
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1170 ActionIdentity(kind='attack', parts=('[0,{"attackId":1486,"type":13},[]]',))
- priced -0.1245 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `92708809-21` (Main, wasted_resource)

- Ledger chose `[5]` End turn
- ruling was `[0]` Play Pokégear 3.0
- rationale: we have our 3 staryus on board thus there is nothing left to fetch with buddy buddy poffin. therefor save the card for eventual discarding when using an ultra ball
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1245 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))
- priced -0.1550 ActionIdentity(kind='attack', parts=('[0,{"attackId":1486,"type":13},[]]',))

### mega_starmie `92708809-35` (Main, sequencing_error)

- Ledger chose `[10]` Attack with Jetting Blow
- ruling was `[]` 
- rationale: 
- priced +0.2610 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0387 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `92708809-42` (Main, sequencing_error)

- Ledger chose `[8]` Attack with Jetting Blow
- ruling was `[]` 
- rationale: 
- priced +3.0761 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.1170 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":20,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `92708809-57` (Main, sequencing_error)

- Ledger chose `[4]` Play Pokégear 3.0
- ruling was `[]` 
- rationale: 
- priced +0.1445 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0146 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `92710760-56` (EvolvesTo, slow_setup)

- Ledger chose `[0]` Mega Starmie ex
- ruling was `[2]` Mega Starmie ex
- rationale: CRITICAL: Something happened here causing us to freeze
- priced +0.0650 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1031,"playerIndex":0}]]]',))
- priced -0.1500 ActionIdentity(kind='decline', parts=())

### mega_starmie `92711683-19` (Main, sequencing_error)

- Ledger chose `[4]` Play Buddy-Buddy Poffin
- ruling was `[]` 
- rationale: CRITICAL: this turn had a number of key blunders. 
1) Used utlra ball to fetch a staryu when we had a buddy buddy poffin
2) attached heros cape to cinderace instead of our primary attacker
3) attached energy to one staryu but then evolved a different staryu using salvatore
- priced +0.4910 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1086,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0275 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))

