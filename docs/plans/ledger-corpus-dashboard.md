# Ledger corpus dashboard

Generated 2026-08-21T10:37:02.850095+00:00 at `f41fab1aa2bb`.

| deck | graded | agrees | agreement | ungraded | retired | gap-affected decisions | fallbacks |
|---|---|---|---|---|---|---|---|
| dragapult_ex | 43 | 23 | 53.5% | 0 | 11 | 21 | 0 |
| mega_lucario | 52 | 28 | 53.8% | 0 | 18 | 17 | 0 |
| mega_starmie | 327 | 166 | 50.8% | 0 | 20 | 162 | 0 |

**Generality floor (worst deck): 50.8%**

## Retired rulings (49) — dispositioned in reviewed.json, not graded

- dragapult_ex `85045840-10`: fixed (2026-08-02)
- dragapult_ex `85045840-12`: fixed (2026-08-02)
- dragapult_ex `85045840-8`: covered (2026-07-09)
- dragapult_ex `85046350-20`: covered (2026-08-03)
- dragapult_ex `85046350-45`: covered (2026-07-09)
- dragapult_ex `85785609-82`: deferred-multi-turn (2026-08-20)
- dragapult_ex `86089120-14`: transposition (2026-08-02)
- dragapult_ex `86090676-18`: refuted (2026-08-20)
- dragapult_ex `86091435-119`: refuted (2026-07-19)
- dragapult_ex `86091435-13`: refuted (2026-08-20)
- dragapult_ex `86091435-68`: refuted (2026-07-19)
- mega_lucario `83661652-19`: refuted (2026-07-22)
- mega_lucario `83661652-3`: refuted (2026-08-03)
- mega_lucario `83661652-30`: refuted (2026-08-03)
- mega_lucario `83661652-33`: covered (2026-08-03)
- mega_lucario `83661652-44`: covered (2026-08-03)
- mega_lucario `84071010-15`: fixed (2026-07-13)
- mega_lucario `84071010-30`: covered (2026-07-09)
- mega_lucario `84890060-48`: covered (2026-07-10)
- mega_lucario `85058051-4`: covered (20260715)
- mega_lucario `85058574-109`: covered (2026-07-11)
- mega_lucario `85709280-17`: covered (2026-07-13)
- mega_lucario `85709280-51`: covered (2026-07-13)
- mega_lucario `85785067-14`: covered (2026-08-03)
- mega_lucario `85785606-1`: covered (2026-08-03)
- mega_lucario `86090147-5`: refuted (2026-08-20)
- mega_lucario `86090666-9`: refuted (2026-08-20)
- mega_lucario `86091172-30`: refuted (2026-08-20)
- mega_lucario `86091172-8`: refuted (2026-08-20)
- mega_starmie `81904451-37`: deferred-multi-turn (2026-08-20)
- mega_starmie `81904451-50`: deferred-multi-turn (2026-08-20)
- mega_starmie `81905522-47`: deferred (2026-08-21)
- mega_starmie `81905522-64`: deferred (2026-08-21)
- mega_starmie `82228640-53`: deferred (2026-08-21)
- mega_starmie `82523164-55`: deferred-multi-turn (2026-08-20)
- mega_starmie `82867148-87`: deferred (2026-08-21)
- mega_starmie `83667237-107`: deferred-multi-turn (2026-08-20)
- mega_starmie `91394270-85`: refuted (2026-08-20)
- mega_starmie `92091149-60`: refuted (2026-08-20)
- mega_starmie `92102433-10`: deferred (2026-08-20)
- mega_starmie `92104376-7`: refuted (2026-08-20)
- mega_starmie `92131448-22`: deferred (2026-08-16)
- mega_starmie `92457318-44`: deferred (2026-08-20)
- mega_starmie `92459166-92`: refuted (2026-08-20)
- mega_starmie `92645419-116`: refuted (2026-08-20)
- mega_starmie `92646350-132`: refuted (2026-08-16)
- mega_starmie `92708809-35`: refuted (2026-08-20)
- mega_starmie `92708809-42`: refuted (2026-08-20)
- mega_starmie `92708809-57`: refuted (2026-08-20)

## Misses (the triage queue: read the rationale first)

### dragapult_ex `83686860-11` (Discard, missed_win)

- Ledger chose `[1, 2]` Basic {R} Energy, Basic {D} Energy
- ruling was `[0]` Lillie's Determination
- rationale: Discard a fire energy when we otherwise have no energy is a bad trade.
- priced +0.1520 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[2,{"id":2,"playerIndex":1}]]]', '[1,{"playerIndex":1,"type":3},[[2,{"id":7,"playerIndex":1}]]]'))
- priced +0.1080 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[2,{"id":1227,"playerIndex":1}]]]', '[1,{"playerIndex":1,"type":3},[[2,{"id":7,"playerIndex":1}]]]'))
- priced +0.1080 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[2,{"id":1080,"playerIndex":1}]]]', '[1,{"playerIndex":1,"type":3},[[2,{"id":7,"playerIndex":1}]]]'))

### dragapult_ex `83686860-13` (Main, wasted_resource)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[1]` End turn
- rationale: CRITICAL: We just discarded two energy to fetch a drakloak for next turn, then immediatly shuffle our hand away with Lillie's. thus, we completely wasted two energies AND an ultra ball for zero gain.
- priced +0.4080 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### dragapult_ex `83686860-45` (Main, wasted_resource)

- Ledger chose `[6]` Ability: Drakloak (bench 1 · 90/90 · 1⚡)
- ruling was `[4]` Attach Basic {R} Energy → Drakloak (bench 1 · 90/90 · 1⚡)
- rationale: CRITICAL: never ever ever attach invalid energy to our wincons. they require one fire and one psychic and now you have attached two psychics. must first verify pokemons energy needs, then attach correct energy.
- priced +0.2500 ActionIdentity(kind='ability', parts=('[1,{"type":10},[[5,{"appearThisTurn":false,"energies":[5],"energyCards":[{"id":5,"playerIndex":1}],"hp":90,"id":120,"maxHp":90,"playerIndex":1,"preEvolution":[{"id":119,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.2500 ActionIdentity(kind='ability', parts=('[1,{"type":10},[[5,{"appearThisTurn":false,"energies":[2],"energyCards":[{"id":2,"playerIndex":1}],"hp":90,"id":120,"maxHp":90,"playerIndex":1,"preEvolution":[{"id":119,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0725 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":2,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[5],"energyCards":[{"id":5,"playerIndex":1}],"hp":90,"id":120,"maxHp":90,"playerIndex":1,"preEvolution":[{"id":119,"playerIndex":1}],"tools":[]}]]]',))

### dragapult_ex `85045840-14` (ToHand, wasted_resource)

- Ledger chose `[2]` Dreepy
- ruling was `[1]` Budew
- rationale: CRITICAL: You discarded our Drakloak (stage 1) in exchange for a Dragapult (stage 2). nonsensical.
- priced +0.2425 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":119,"playerIndex":0}]]]',))
- priced +0.2425 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":120,"playerIndex":0}]]]',))
- priced +0.1925 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":140,"playerIndex":0}]]]',))

### dragapult_ex `85046350-32` (Main, wasted_resource)

- Ledger chose `[3]` Retreat
- ruling was `[1]` Evolve Drakloak → Dreepy (active · 70/70 · 1⚡)
- rationale: CRITICAL: We are about to KO their active, so why play Crushing hammer first?
- priced +0.0325 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))
- priced +0.0133 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1120,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### dragapult_ex `85046350-85` (Main, misattachment)

- Ledger chose `[8]` Retreat
- ruling was `[3]` Attach Basic {P} Energy → Dreepy (bench 2 · 50/70 · 1⚡)
- rationale: Better to fully energize a single Dreepy/Drakloak/Dragapult then to spread out the energies.
- priced +1.5106 ActionIdentity(kind='attack', parts=('[0,{"attackId":154,"type":13},[]]',))
- priced +0.2255 ActionIdentity(kind='attack', parts=('[0,{"attackId":153,"type":13},[]]',))
- priced +0.2125 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))

### dragapult_ex `85785609-22` (ToHand, misattachment)

- Ledger chose `[0]` Basic {R} Energy
- ruling was `[3]` Basic {D} Energy
- rationale: I would have fetched the darkness energy to attach to the Munkidori. then use its ability to move damage from dreepy to opponents dreepy
- priced +0.0500 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":2,"playerIndex":0}]]]',))
- priced +0.0500 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":5,"playerIndex":0}]]]',))
- priced +0.0305 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":7,"playerIndex":0}]]]',))

### dragapult_ex `85786096-24` (Main, slow_setup)

- Ledger chose `[1]` Attach Basic {R} Energy → Dreepy (bench 1 · 70/70)
- ruling was `[0]` Attach Basic {R} Energy → Fezandipiti ex (active · 210/210)
- rationale: CRITICAL: Our matchup posture should know that our opponent only has these three Staryu's as basics which can be benched after match setup, thus this stadium only hurts us.
- priced +0.0475 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":2,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0394 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":2,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":210,"id":140,"maxHp":210,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0394 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":2,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":305,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `85786096-25` (Main, slow_setup)

- Ledger chose `[1]` Attach Basic {R} Energy → Dreepy (bench 1 · 70/70)
- ruling was `[0]` Attach Basic {R} Energy → Fezandipiti ex (active · 210/210)
- rationale: CRITICAL: Our Dreepy doesnt need energy just yet. We should attache to Fez, retreat, promote Budew, then item lock with Itchy Pollen
- priced +0.0475 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":2,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0394 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":2,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":210,"id":140,"maxHp":210,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0394 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":2,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":305,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `85786096-86` (AttachTo, slow_setup)

- Ledger chose `[]` 
- ruling was `[1]` Basic {P} Energy
- rationale: CRITICAL: WHy the fuck would you attach darkness energy to our dragon line that needs specifically fire and psychic???
- priced +0.0000 ActionIdentity(kind='decline', parts=())
- priced +0.0000 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":7,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":5,"playerIndex":0}]]]',))

### dragapult_ex `86089638-18` (Main, misattachment)

- Ledger chose `[6]` Play Ultra Ball
- ruling was `[8]` Attach Basic {P} Energy → Dreepy (bench 1 · 70/70 · 1⚡)
- rationale: power up our main line. meowth IS just a wall for now
- priced +0.0965 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))
- priced +0.0725 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":5,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[2],"energyCards":[{"id":2,"playerIndex":0}],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0573 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":7,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":170,"id":1071,"maxHp":170,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `86091435-20` (Main, wasted_resource)

- Ledger chose `[1]` End turn
- ruling was `[0]` Retreat
- rationale: CRITICAL: Should retreat into Budew, then attack to item lock
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0553 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))

### dragapult_ex `86091435-35` (Main, sequencing_error)

- Ledger chose `[0]` Evolve Dragapult ex → Drakloak (active · 90/90 · 2⚡)
- ruling was `[1]` Play Poké Pad
- rationale: RE-RULED 2026-07-26 (user, #167 decision-5 sitting): correct is [1] Play Poké Pad, not [2] Ability. Poké Pad's job in this deck is fetching the 2nd Drakloak (4x in deck, no Rule Box, 1 in play) so a bench Dreepy — both appearThisTurn=False, so legally evolvable — becomes a 2nd Recon Directive body: two digs instead of one. Resolving the DETERMINISTIC tutor first also thins the deck by a known non-{P} card, improving both digs; waiting reveals nothing. Then Recon x2, and branch: on a {P}, attach and evolve the Active for Phantom Dive {R}{P} 200; otherwise retreat the Drakloak (cost 1, discarding the dead {D}), promote Budew and item-lock with Itchy Pollen. ORIGINAL TAG 2026-07-15, superseded but retained as provenance — correct=[2] 'Ability: Drakloak (active · 90/90 · 2⚡)', rationale: "CRITICAL: Always use Drakloak's ability before evolving it." That principle SURVIVES (the line still uses Recon before any evolve); what it got wrong was the first action, because it did not see the Poké Pad → 2nd Drakloak line.
- priced +0.4540 ActionIdentity(kind='evolve', parts=('[0,{"type":9},[[2,{"id":121,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[2,7],"energyCards":[{"id":2,"playerIndex":0},{"id":7,"playerIndex":0}],"hp":90,"id":120,"maxHp":90,"playerIndex":0,"preEvolution":[{"id":119,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.1675 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1152,"playerIndex":0}]]]',))
- priced +0.0900 ActionIdentity(kind='ability', parts=('[0,{"type":10},[[4,{"appearThisTurn":false,"energies":[2,7],"energyCards":[{"id":2,"playerIndex":0},{"id":7,"playerIndex":0}],"hp":90,"id":120,"maxHp":90,"playerIndex":0,"preEvolution":[{"id":119,"playerIndex":0}],"tools":[]}]]]',))

### dragapult_ex `86091435-49` (ToHand, sequencing_error)

- Ledger chose `[1]` (card)
- ruling was `[]` 
- rationale: 
- priced +0.0750 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[12,{"id":1152,"playerIndex":0}]]]',))
- priced +0.0500 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[12,{"id":5,"playerIndex":0}]]]',))

### dragapult_ex `86091435-60` (Main, sequencing_error)

- Ledger chose `[1]` Play Buddy-Buddy Poffin
- ruling was `[2]` Attach Basic {P} Energy → Dreepy (active · 70/70)
- rationale: CRITICAL: Attach energy before shuffling. this is definitely a regression of hypothesis and weights
- priced +0.4892 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.3376 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.1200 ActionIdentity(kind='ability', parts=('[0,{"type":10},[[5,{"appearThisTurn":false,"energies":[2,5],"energyCards":[{"id":2,"playerIndex":0},{"id":5,"playerIndex":0}],"hp":90,"id":120,"maxHp":90,"playerIndex":0,"preEvolution":[{"id":119,"playerIndex":0}],"tools":[]}]]]',))

### dragapult_ex `86091435-96` (Main, wasted_resource)

- Ledger chose `[5]` Attach Basic {D} Energy → Dunsparce (bench 4 · 70/70)
- ruling was `[0]` Play Lillie's Determination
- rationale: CRITICAL: Why attach Darkness energy on pokemon that needs fire and psychic? such a blunder. Our hand isnt so useful at the moment, shuffle it in with Lillies
- priced +0.3871 ActionIdentity(kind='attack', parts=('[0,{"attackId":153,"type":13},[]]',))
- priced +0.1477 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0645 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":7,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":305,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `86091728-12` (Main, sequencing_error)

- Ledger chose `[3]` Attach Basic {P} Energy → Dreepy (active · 70/70)
- ruling was `[]` 
- rationale: For this turn, we focus on setup. I would evolve active Dreepy to Drakloak, use Recon Directive, playin Cripsin to fetch on darkness and one fire where Crispin bonus attach is fire to active drakloak. then attach for turn psychic to active drakloak. then attack for 70 dmg.
- priced +0.0815 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":5,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0715 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1198,"playerIndex":0}]]]',))
- priced +0.0438 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":5,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":112,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `86091728-19` (Main, sequencing_error)

- Ledger chose `[0]` Play Ultra Ball
- ruling was `[3]` Attach Basic {P} Energy → Dreepy (bench 2 · 70/70)
- rationale: We dont need to fetch anything at the moment.
- priced +0.0770 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))
- priced +0.0633 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":7,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":112,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0475 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":5,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":119,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### dragapult_ex `86091728-43` (ToBench, wasted_resource)

- Ledger chose `[0, 2]` Dunsparce, Budew
- ruling was `[2, 3]` Budew, Dreepy
- rationale: CRITICAL: When searching with buddy buddy, when can see in deck that there is no Dudunspace there, thus its in prize cards, thus dont fetch dunspace. get budew instead
- priced +0.7375 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":235,"playerIndex":0}]]]', '[{"playerIndex":0,"type":3},[[1,{"id":305,"playerIndex":0}]]]'))
- priced +0.6675 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":119,"playerIndex":0}]]]', '[{"playerIndex":0,"type":3},[[1,{"id":305,"playerIndex":0}]]]'))
- priced +0.5025 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":119,"playerIndex":0}]]]', '[{"playerIndex":0,"type":3},[[1,{"id":235,"playerIndex":0}]]]'))

### dragapult_ex `86091728-47` (ToHand, wasted_resource)

- Ledger chose `[0]` (card)
- ruling was `[1]` (card)
- rationale: CRITICAL: We could have used Night Stretcher to recycle Drakloak, evolve a dreepy, then use Recond Directive ability.
- priced +0.0750 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[12,{"id":1121,"playerIndex":0}]]]',))
- priced +0.0500 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[12,{"id":1097,"playerIndex":0}]]]',))

### mega_lucario `83661652-31` (ToHand, wasted_resource)

- Ledger chose `[7]` Lunatone
- ruling was `[1]` Mega Lucario ex
- rationale: CRITICAL: we discarded a riolu to fetch a riolu. what a waste!
- priced +0.2525 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":675,"playerIndex":0}]]]',))
- priced +0.2425 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":677,"playerIndex":0}]]]',))
- priced +0.1925 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":676,"playerIndex":0}]]]',))

### mega_lucario `83661652-40` (Main, wasted_resource)

- Ledger chose `[2]` Play Solrock
- ruling was `[3]` Play Riolu
- rationale: CRITICAL: Just shuffled in the pre evolution to our main line attacker, Riolu! bad bad
- priced +0.3450 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":676,"playerIndex":0}]]]',))
- priced +0.3200 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":677,"playerIndex":0}]]]',))
- priced +0.0949 ActionIdentity(kind='attack', parts=('[0,{"attackId":979,"type":13},[]]',))

### mega_lucario `83966336-9` (ToHand, slow_setup)

- Ledger chose `[5]` Riolu
- ruling was `[2]` Basic {F} Energy
- rationale: CRITICAL: we need energy, be sure to fetch it with this.
- priced +0.2425 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":677,"playerIndex":0}]]]',))
- priced +0.1925 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":676,"playerIndex":0}]]]',))
- priced +0.1925 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":675,"playerIndex":0}]]]',))

### mega_lucario `83967841-14` (ToHand, slow_setup)

- Ledger chose `[4]` Makuhita
- ruling was `[0]` Basic {F} Energy
- rationale: CRITICAL: we already have lunatone in hand but dont have any energy. we typically only ever need a single lunatone and a single solrcok in play at any given time.
- priced +0.2699 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":673,"playerIndex":1}]]]',))
- priced +0.2525 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":675,"playerIndex":1}]]]',))
- priced +0.2425 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":677,"playerIndex":1}]]]',))

### mega_lucario `83967841-17` (Main, wasted_resource)

- Ledger chose `[2]` Play Ultra Ball
- ruling was `[3]` End turn
- rationale: CRITICAL: still just setting up. nothing needs evolving. just save the ultra ball for next turn.
- priced +0.0906 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0550 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1141,"playerIndex":1}]]]',))

### mega_lucario `84071010-64` (Main, wasted_resource)

- Ledger chose `[1]` Attach Basic {F} Energy → Lunatone (bench 1 · 110/110 · 1⚡)
- ruling was `[2]` Attach Basic {F} Energy → Makuhita (bench 2 · 80/80)
- rationale: avoid attaching energy to lunatone unless only option
- priced +2.9236 ActionIdentity(kind='attack', parts=('[0,{"attackId":982,"type":13},[]]',))
- priced +0.1268 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0650 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":6,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":0}],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `84889011-12` (ToHand, wasted_resource)

- Ledger chose `[3]` Riolu
- ruling was `[0]` Makuhita
- rationale: CRITICAL: already have solrock on board, so dont fetch it. we typically only ever need one solrock and one lunatone in play
- priced +0.2425 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":677,"playerIndex":0}]]]',))
- priced +0.1925 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":676,"playerIndex":0}]]]',))
- priced +0.1675 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":673,"playerIndex":0}]]]',))

### mega_lucario `84889011-24` (Main, wasted_resource)

- Ledger chose `[3]` Play Meowth ex
- ruling was `[5]` Attach Basic {F} Energy → Solrock (bench 1 · 110/110)
- rationale: CRITICAL: The winning line was missed. Could have attached energy to Solrock. Retreated and promoted Solrock. Played two Premium Power Pros such that Solrock would swing for 130, OHKOing opponent for the win.
- priced +0.4525 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1071,"playerIndex":0}]]]',))
- priced +0.2570 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0750 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":6,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":676,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `84889011-7` (ToHand, wasted_resource)

- Ledger chose `[2]` Lunatone
- ruling was `[4]` Riolu
- rationale: CRITICAL: Already have lunatone on board, do not then fetch one
- priced +0.2525 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":675,"playerIndex":0}]]]',))
- priced +0.2425 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":677,"playerIndex":0}]]]',))
- priced +0.1925 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":676,"playerIndex":0}]]]',))

### mega_lucario `84890060-12` (Main, misattachment)

- Ledger chose `[0]` Play Ultra Ball
- ruling was `[2]` End turn
- rationale: We have a mega lucario in hand with a riolu on bench. also have lunatone and solrcok in play. nothing else that we really need at this point.
- priced +0.0300 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))
- priced +0.0012 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_lucario `84890060-26` (ToHand, wasted_resource)

- Ledger chose `[2]` Riolu
- ruling was `[1]` Basic {F} Energy
- rationale: CRITICAL: you had the chance to fetch an energy, which could be attached to Mega Lucario, then free retreat to lucario and KO opponent with Aura Jab. that then would have recycled 2 energies from discard to be placed on solrock and lunatone.
- priced +0.3303 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":677,"playerIndex":1}]]]',))
- priced +0.2525 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":675,"playerIndex":1}]]]',))
- priced +0.1925 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":676,"playerIndex":1}]]]',))

### mega_lucario `85058051-13` (ToHand, wasted_resource)

- Ledger chose `[3]` Riolu
- ruling was `[2]` Lunatone
- rationale: CRITICAL: There was a win on this turn. fetch lunatone with ultra ball, attack for 70 dmg, win!
- priced +0.3887 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":677,"playerIndex":1}]]]',))
- priced +0.1925 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":676,"playerIndex":1}]]]',))
- priced +0.1925 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":675,"playerIndex":1}]]]',))

### mega_lucario `85058574-121` (AttachFrom, wrong_attack)

- Ledger chose `[1]` Solrock (bench 2 · 110/110)
- ruling was `[3]` Hariyama (bench 4 · 150/150)
- rationale: PLANNER / multi-turn (re-tagged [2]->[3], user-confirmed 2026-07-22). Neither the corpus's Mega Lucario ex nor a Solrock is right. The opponent can't KO any of our Pokemon next turn, and the active Mega Lucario ex is ALREADY a next-turn KO (one manual F -> Mega Brave 270 > Dragapult's 190 left) without this route. So the Aura Jab energy stages the NEXT 1-prize attacker: route >=2 F to Hariyama (Wild Press 210), skipping the weaker Solrock and the 3-prize Mega Lucario liability (force-8-prizes doctrine). Assumes a fully-energized backup Dragapult promotes after we KO; the commit-to-Hariyama call rests on an odds calc (turns until an energy/fetch reaches the benched Mega Lucario ~ 3). TURN-PLANNER scope, NOT the single-turn energy oracle.
- priced +0.1250 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":676,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[{"id":1174,"playerIndex":1}]}]]]',))
- priced +0.0950 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0889 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":150,"id":674,"maxHp":150,"playerIndex":1,"preEvolution":[{"id":673,"playerIndex":1}],"tools":[]}]]]',))

### mega_lucario `85058574-71` (ToHand, wasted_resource)

- Ledger chose `[18]` Boss’s Orders
- ruling was `[11]` Fighting Gong
- rationale: I would have fetched fighting gong, then used that to fetch an energy, then discarded that energy to draw 3 cards using Lunatones ability.
- priced +0.1175 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":1182,"playerIndex":1}]]]',))
- priced +0.0825 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0825 ActionIdentity(kind='card', parts=('[{"playerIndex":1,"type":3},[[1,{"id":1080,"playerIndex":1}]]]',))

### mega_lucario `85058574-87` (Main, wasted_resource)

- Ledger chose `[6]` Play Ultra Ball
- ruling was `[0]` Attach Air Balloon → Mega Lucario ex (active · 330/340 · 2⚡)
- rationale: CRITICAL: attaching air balloon to a benched mon doesnt really make sense. its purpose is to allow our active to retreat for free.
- priced +1.1737 ActionIdentity(kind='attack', parts=('[1,{"attackId":983,"type":13},[]]',))
- priced +0.5176 ActionIdentity(kind='attack', parts=('[1,{"attackId":982,"type":13},[]]',))
- priced +0.0229 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))

### mega_lucario `85058574-88` (Main, wrong_attack)

- Ledger chose `[0]` Play Ultra Ball
- ruling was `[1]` Attack with Aura Jab
- rationale: CRITICAL: Pilot chose Mega Brave which makes sense when considering this turn in isolation, because that is the only attack that KOs the Munkidori. BUT using Mega Brave now means that we cannot use it next turn, when the opponents energized Dragapult Ex will surely be promoted. It would have been more match strategic to attack with Aura Jab as to attach 3 energy to our bench pokemon in preparation for fighting the Dragapults. i would have attached two energy to the Riolu and one to the Hariyama
- priced +1.1737 ActionIdentity(kind='attack', parts=('[1,{"attackId":983,"type":13},[]]',))
- priced +0.5176 ActionIdentity(kind='attack', parts=('[1,{"attackId":982,"type":13},[]]',))
- priced +0.0229 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))

### mega_lucario `85059103-39` (ToHand, other)

- Ledger chose `[9]` Lunatone
- ruling was `[7]` Solrock
- rationale: CRITICAL: We have a Lunatone in play, a few energy cards in hand plus a fully energized Lucario. we need a solrock to utilize Lunatone's draw 3 ability.

Then we wanna start draw 3 each turn, discarding energy that can be recycled with Lucario's Aura Jab attack.
- priced +0.2525 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":675,"playerIndex":0}]]]',))
- priced +0.2425 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":677,"playerIndex":0}]]]',))
- priced +0.1925 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":676,"playerIndex":0}]]]',))

### mega_lucario `85059103-9` (ToHand, wrong_attack)

- Ledger chose `[7]` Boss’s Orders
- ruling was `[3]` Team Rocket's Petrel
- rationale: CRITICAL: Dont fetch a lillie's when we already have one in our hand.

Here I would have fetch a Petrel, which can be used to fetch a fighting gong, which can be used to fetch a solrock. then we can discard an energy card to draw three cards. 
- priced +0.1250 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1182,"playerIndex":0}]]]',))
- priced +0.0900 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0900 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1213,"playerIndex":0}]]]',))

### mega_lucario `85709280-42` (Main, slow_setup)

- Ledger chose `[6]` Play Ultra Ball
- ruling was `[1]` Attach Air Balloon → Meowth ex (active · 170/170)
- rationale: CRITICAL: A worthless attach. We need our Meowth Ex out of the active spot so that we can attack. SHould have attached Air Balloon to Meowth, then promote Solrock, then play Premium Power Pro, and KO opponent.
- priced +0.0959 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))
- priced +0.0200 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1174,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":170,"id":1071,"maxHp":170,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0200 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1174,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":1}],"hp":110,"id":676,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `85785606-19` (Main, wrong_supporter)

- Ledger chose `[5]` Ability: Lunatone (bench 2 · 110/110)
- ruling was `[1]` Attach Basic {F} Energy → Solrock (active · 80/110)
- rationale: Gusting is not helpful here
- priced +0.1350 ActionIdentity(kind='ability', parts=('[0,{"type":10},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0725 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":6,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":0}],"hp":80,"id":677,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0625 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":6,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":676,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `85785606-21` (Main, wrong_supporter)

- Ledger chose `[4]` Ability: Lunatone (bench 2 · 110/110)
- ruling was `[0]` Attach Basic {F} Energy → Solrock (active · 80/110)
- rationale: CRITICAL: Get Solrock attacking.
- priced +0.1350 ActionIdentity(kind='ability', parts=('[0,{"type":10},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0725 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":6,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":0}],"hp":80,"id":677,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0625 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":6,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":676,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_lucario `86088989-29` (ToHand, wrong_supporter)

- Ledger chose `[5]` Boss’s Orders
- ruling was `[1]` Lillie's Determination
- rationale: CRITICAL: Lillies would have been far more helpful here.
- priced +0.1250 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1182,"playerIndex":0}]]]',))
- priced +0.0900 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1213,"playerIndex":0}]]]',))
- priced +0.0900 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1227,"playerIndex":0}]]]',))

### mega_lucario `86089617-4` (Main, wasted_resource)

- Ledger chose `[2]` Attach Basic {F} Energy → Lunatone (active · 110/110)
- ruling was `[4]` End turn
- rationale: CRITICAL: We cannot attack this turn, so a complete waste
- priced +0.0410 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":6,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0550 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1141,"playerIndex":1}]]]',))

### mega_lucario `86090147-22` (Main, wasted_resource)

- Ledger chose `[5]` Play Lunatone
- ruling was `[7]` Retreat
- rationale: After Lillie's, we got some really great stuff, but they must be used properly.

retreat meowth, promote solrock, attach energy to solrock (never should have attached to meowth before, so could have used air balloon). play lunatone, makuhita. attack with solrock

- priced +0.3400 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":675,"playerIndex":0}]]]',))
- priced +0.2625 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":673,"playerIndex":0}]]]',))
- priced +0.1800 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":676,"playerIndex":0}]]]',))

### mega_starmie `1002062899305-13` (Main, wrong_attack)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[2]` Attack with Water Gun
- rationale: CRITICAL: no attack still? this is a huge problem
- priced +0.0572 ActionIdentity(kind='attack', parts=('[0,{"attackId":1486,"type":13},[]]',))
- priced +0.0199 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `1002062899305-64` (Main, sequencing_error)

- Ledger chose `[1]` Attach Ignition Energy → Mega Starmie ex (active · 70/330)
- ruling was `[6]` Play Pokégear 3.0
- rationale: CRITICAL: this pilot just attached energy before playing pokegear when we just explicitly made that a rule not to do such a thing. we have a real supporter need for a Wallys Compassion. Need to attempt to get it.
- priced +0.5016 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.3700 ActionIdentity(kind='evolve', parts=('[0,{"type":9},[[2,{"id":1031,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.3178 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))

### mega_starmie `160106599249705-16` (Main, slow_setup)

- Ledger chose `[0]` Play Mega Signal
- ruling was `[1]` Attack with Turbo Flare
- rationale: CRITICAL: you didnt attack, why? this is the second of such blunders that are extremly critical. what is happening here?
- priced +0.3916 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0180 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `26001818654643-22` (ToHand, wrong_supporter)

- Ledger chose `[1]` (card)
- ruling was `[0]` (card)
- rationale: CRITICAL: 1) we already have a harlequin in hand. 2) dont want to play harlequin this turn anyways. 3) we really want a second starmie.
- priced +0.0900 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[12,{"id":1223,"playerIndex":0}]]]',))
- priced +0.0750 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[12,{"id":1225,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='decline', parts=())

### mega_starmie `26001818654643-49` (Main, other)

- Ledger chose `[3]` Attach Basic {W} Energy → Mega Starmie ex (active · 330/330 · 1⚡)
- ruling was `[8]` Play Hilda
- rationale: RULED 2026-08-20 (owner-approved triage batch A): the note ENDORSES the agent's own pick, so correct = chosen. Original note: "the sequence carried out by our pilot in this turn is perfect, well done"
- priced +0.4543 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0517 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0188 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `26001818654643-76` (Main, other)

- Ledger chose `[5]` Attach Basic {W} Energy → Mega Starmie ex (active · 330/330 · 1⚡)
- ruling was `[9]` Attack with Jetting Blow
- rationale: RULED 2026-08-20 (owner-approved triage batch A): the note ENDORSES the agent's own pick, so correct = chosen. Original note: "Game winning move found and taken without any intermediate moves, excellent."
- priced +103.4552 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0712 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0645 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `81785223-32` (Main, sequencing_error)

- Ledger chose `[3]` Evolve Mega Starmie ex → Staryu (bench 2 · 70/70)
- ruling was `[4]` Play Pokégear 3.0
- rationale: 
- priced +0.7835 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.3700 ActionIdentity(kind='evolve', parts=('[0,{"type":9},[[2,{"id":1031,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.3178 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))

### mega_starmie `81785223-38` (Main, sequencing_error)

- Ledger chose `[3]` Evolve Mega Starmie ex → Staryu (bench 2 · 70/70)
- ruling was `[4]` Play Pokégear 3.0
- rationale: Should play Pokegear  3.0 to dig for supporter earlier in turn
- priced +0.6788 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.3700 ActionIdentity(kind='evolve', parts=('[0,{"type":9},[[2,{"id":1031,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.3178 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))

### mega_starmie `81785223-44` (Main, sequencing_error)

- Ledger chose `[3]` Evolve Mega Starmie ex → Staryu (bench 2 · 70/70)
- ruling was `[4]` Play Pokégear 3.0
- rationale: 
- priced +2.5191 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.3700 ActionIdentity(kind='evolve', parts=('[0,{"type":9},[[2,{"id":1031,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.3178 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))

### mega_starmie `81785223-45` (Damage, sequencing_error)

- Ledger chose `[0]` opp Latias ex (bench 1 · 60/210)
- ruling was `[2]` opp Lillie’s Clefairy ex (bench 3 · 70/190 · 1⚡)
- rationale: 
- priced +0.1533 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":60,"id":184,"maxHp":210,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1533 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":90,"id":108,"maxHp":210,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1451 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":1}],"hp":70,"id":272,"maxHp":190,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `81903490-27` (Main, misattachment)

- Ledger chose `[6]` Play Buddy-Buddy Poffin
- ruling was `[0]` Attach Basic {W} Energy → Staryu (active · 70/70)
- rationale: Save ignition energy either for Mega Starmie Ex or Cinderace in special cases if no Mega Starmie Ex, Staru is benched, and basic energy
- priced +0.2010 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.0746 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0700 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `81903490-49` (Main, misattachment)

- Ledger chose `[6]` Play Salvatore
- ruling was `[1]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: Never attach ignition energy to Cinderace when basic energy available
- priced +1.0055 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))
- priced +0.0938 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0466 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `81903490-74` (Main, sequencing_error)

- Ledger chose `[2]` Play Salvatore
- ruling was `[5]` Evolve Mega Starmie ex → Staryu (active · 70/70 · 1⚡)
- rationale: Most often should Evolve active Staru to mega starmie ex if have the chance. only case not to is if attachking with mega starmie ex doesnt win and then next turn mega starmie ex will die and opponent has less than 3 prize cards left, causing loss of game
- priced +1.0504 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))
- priced +0.9544 ActionIdentity(kind='evolve', parts=('[0,{"type":9},[[2,{"id":1031,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.6400 ActionIdentity(kind='evolve', parts=('[0,{"type":9},[[2,{"id":1031,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `81903490-8` (ToHand, wasted_resource)

- Ledger chose `[0]` Staryu
- ruling was `[1]` Mega Starmie ex
- rationale: Ultra balls should be usually used to find main pokemon, in this case Mega Starmie Ex
- priced +0.2425 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1030,"playerIndex":0}]]]',))
- priced +0.2425 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":1031,"playerIndex":0}]]]',))
- priced -0.0054 ActionIdentity(kind='card', parts=('[{"playerIndex":0,"type":3},[[1,{"id":666,"playerIndex":0}]]]',))

### mega_starmie `81903490-93` (ToHand, other)

- Ledger chose `[1]` Staryu
- ruling was `[2]` Basic {W} Energy
- rationale: use night stretcher to get basic energy if dont already have energy in hand and active pokemon needs an energy. typically dont need cinderace after SETUP stage
- priced +0.2700 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[3,{"id":1030,"playerIndex":0}]]]',))
- priced +0.0500 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[3,{"id":3,"playerIndex":0}]]]',))
- priced +0.0146 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[3,{"id":666,"playerIndex":0}]]]',))

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
- priced +0.4510 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.3700 ActionIdentity(kind='evolve', parts=('[0,{"type":9},[[2,{"id":1031,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0503 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `81904451-17` (Main, bad_retreat)

- Ledger chose `[2]` End turn
- ruling was `[0]` Attack with Water Gun
- rationale: Attack when able over retreat in most cases.
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0266 ActionIdentity(kind='attack', parts=('[0,{"attackId":1486,"type":13},[]]',))
- priced -0.0990 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))

### mega_starmie `81904451-53` (Main, sequencing_error)

- Ledger chose `[5]` Play Salvatore
- ruling was `[6]` Play Mega Signal
- rationale: Should have found mega starmie ex with Mega Signal
- priced +1.0698 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.9963 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))
- priced +0.2975 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1225,"playerIndex":0}]]]',))

### mega_starmie `81904451-58` (Main, sequencing_error)

- Ledger chose `[5]` Play Salvatore
- ruling was `[6]` Play Mega Signal
- rationale: Should have found Mega Starmie ex
- priced +1.2837 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.9963 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))
- priced +0.2975 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1225,"playerIndex":0}]]]',))

### mega_starmie `81904451-6` (Main, misattachment)

- Ledger chose `[2]` Play Buddy-Buddy Poffin
- ruling was `[0]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: never attach ignition energy to Cinderace if basic energy available. ignition energy discards at end of turn.
- priced +0.9472 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.0451 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `81906131-25` (Main, bad_target)

- Ledger chose `[1]` Play Buddy-Buddy Poffin
- ruling was `[4]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: RULED 2026-08-20 (owner-approved triage batch B, extracted from the note): 'never attach ignition energy to Cinderace when can attach basic' -> the basic {W} option; also the ADR-0150 rental doctrine. Supersedes the recorded Ignition pick. Original note: "never attach ignition energy to Cinderace when can attach basic energy"
- priced +0.9180 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1086,"playerIndex":1}]]]',))
- priced +0.0743 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0098 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1120,"playerIndex":1}]]]',))

### mega_starmie `81906755-93` (Main, sequencing_error)

- Ledger chose `[10]` Attack with Jetting Blow
- ruling was `[3]` Attach Basic {W} Energy → Staryu (bench 1 · 70/70)
- rationale: attach energy when able and pokemons need it
- priced +3.6208 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.6660 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1189,"playerIndex":1}]]]',))
- priced +0.0517 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82224509-40` (Main, misattachment)

- Ledger chose `[8]` Retreat
- ruling was `[2]` Attach Basic {W} Energy → Mega Starmie ex (bench 2 · 330/330)
- rationale: Cinderace already had all the energy it needed, so dont waste more energy on it, attach to the benched mon without any energy.
- priced +0.4526 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))
- priced +0.2549 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0443 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1182,"playerIndex":1}]]]',))

### mega_starmie `82224509-46` (Main, sequencing_error)

- Ledger chose `[3]` Play Mega Signal
- ruling was `[1]` Play Boss’s Orders
- rationale: should have boss's orders the preevolution to the opponents main attacker
- priced +1.5997 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +1.3922 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0180 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1145,"playerIndex":1}]]]',))

### mega_starmie `82224509-56` (Damage, bad_target)

- Ledger chose `[2]` opp Makuhita (bench 3 · 80/80)
- ruling was `[1]` opp Mega Lucario ex (bench 2 · 340/340)
- rationale: snipe the opponents main attacker
- priced +0.2231 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":673,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1973 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":60,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1549 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":340,"id":678,"maxHp":340,"playerIndex":0,"preEvolution":[{"id":677,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82224509-67` (Main, sequencing_error)

- Ledger chose `[8]` Retreat
- ruling was `[5]` Play Crushing Hammer
- rationale: opponents active is their main attacker with an energy on it, thats a huge threat. use crushing hammer.
- priced +1.6026 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +1.0066 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.4714 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))

### mega_starmie `82224509-71` (Main, sequencing_error)

- Ledger chose `[4]` Play Wally's Compassion
- ruling was `[2]` Play Lillie's Determination
- rationale: hand wasnt very useful, therefor use lillie's determintation to swap it out
- priced +103.8713 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +1.4662 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.8436 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1229,"playerIndex":1}]]]',))

### mega_starmie `82225138-19` (Main, other)

- Ledger chose `[3]` End turn
- ruling was `[0]` Play Harlequin
- rationale: never play salvatore when no staryu is on board to evolve. hand also sucked, so use harlequin
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0240 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))
- priced -0.0240 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))

### mega_starmie `82225643-11` (Main, sequencing_error)

- Ledger chose `[7]` Attach Hero’s Cape → Staryu (bench 1 · 70/70)
- ruling was `[0]` Play Pokégear 3.0
- rationale: Though ignition energy will be helpful in this current board state, Pokegear 3.0's should have been used first to look for supports that could have helped to find basic energy. ignition energy is such a good card, that it should be saved when able.
- priced +0.2200 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1472 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1120,"playerIndex":1}]]]',))
- priced +0.1112 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82225643-12` (Main, sequencing_error)

- Ledger chose `[5]` Attach Hero’s Cape → Staryu (bench 1 · 70/70)
- ruling was `[1]` Play Crushing Hammer
- rationale: Rioulu would not have died from this attack, and next turn he might evolve to opponents main attacker, mega lucario, thus playing the crushing hammers could have reduced its threat through energy removal.
- priced +0.4368 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.2200 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1542 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1120,"playerIndex":1}]]]',))

### mega_starmie `82225643-34` (Main, sequencing_error)

- Ledger chose `[1]` Attach Hero’s Cape → Mega Starmie ex (active · 300/330 · 3⚡)
- ruling was `[0]` Play Pokégear 3.0
- rationale: Use pokegear 3.0 to find supporter when able. there is no downside in having an extra support in hand.
- priced +2.7509 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +1.4807 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.2339 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3,3,3],"energyCards":[{"id":3,"playerIndex":1},{"id":3,"playerIndex":1},{"id":3,"playerIndex":1}],"hp":300,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82225643-57` (Main, sequencing_error)

- Ledger chose `[3]` Attach Hero’s Cape → Mega Starmie ex (active · 170/330 · 3⚡)
- ruling was `[11]` Play Ultra Ball
- rationale: item cards should be used if they can be helpful prior to attacking. in this case, we have no mainline attacker available to replace our active, thus we should utlra ball to find a staryu thus that we can evolve it next turn. also, hero's capre should be used to give our main line aactive attacker more health.
- priced +1.8028 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +1.6147 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.2940 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3,3,3],"energyCards":[{"id":3,"playerIndex":1},{"id":3,"playerIndex":1},{"id":3,"playerIndex":1}],"hp":170,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82226116-100` (Main, sequencing_error)

- Ledger chose `[0]` Play Night Stretcher
- ruling was `[13]` Retreat
- rationale: Should have attached basic energy to benched main line attacker, giving it enough energy to KO opponents active. then retreat cinderace into that main line attacker.
- priced +0.5288 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.2200 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1097,"playerIndex":0}]]]',))
- priced +0.0652 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `82226116-7` (Main, sequencing_error)

- Ledger chose `[0]` Attach Ignition Energy → Cinderace (active · 160/160)
- ruling was `[1]` End turn
- rationale: Never ever ever play ignition energy on first turn when going first. cannot attack in this situation and then ignition energy is discarded.
- priced +0.2866 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82226116-70` (Main, sequencing_error)

- Ledger chose `[0]` Play Wally's Compassion
- ruling was `[11]` Evolve Mega Starmie ex → Staryu (bench 2 · 70/70)
- rationale: Should evolve benched staryu to mega starmie and attached an energy to it first.
- priced +2.2717 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +1.7987 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.5178 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))

### mega_starmie `82226116-94` (ToActive, sequencing_error)

- Ledger chose `[0]` Cinderace (bench 1 · 120/160 · 1⚡)
- ruling was `[1]` Staryu (bench 2 · 70/70)
- rationale: Should have advanced staryu because we have mega starmie in hand ready to evolve it plus energy to attach.
- priced +0.0480 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":120,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0260 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82226759-64` (Main, sequencing_error)

- Ledger chose `[4]` Play Pokégear 3.0
- ruling was `[3]` Play Harlequin
- rationale: This require Posture, but opponents deck requires a large hand to deal heavy damage. therefor play harlequin to reduce their handsize.
- priced +1.2380 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.8100 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1223,"playerIndex":1}]]]',))
- priced +0.2785 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1097,"playerIndex":1}]]]',))

### mega_starmie `82227388-22` (Main, sequencing_error)

- Ledger chose `[3]` Play Pokégear 3.0
- ruling was `[2]` Attach Basic {W} Energy → Staryu (bench 2 · 70/70)
- rationale: Attach basic energy when able. in this case, attach to the weaker benched pokemon because we know that Cinderace's Turbo Flare attack will provide a full 3 basic energy to Mega Starmie.
- priced +0.3721 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0554 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))
- priced +0.0406 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82227388-30` (Main, sequencing_error)

- Ledger chose `[3]` Play Pokégear 3.0
- ruling was `[2]` Attach Basic {W} Energy → Staryu (bench 2 · 70/70)
- rationale: Attch energy to benched pokemon when able and they need it. also should use Pokegear 3.0 to potentially find a useful supporter.
- priced +1.9187 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +1.5831 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0584 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `82227388-50` (Main, sequencing_error)

- Ledger chose `[5]` Play Wally's Compassion
- ruling was `[2]` Play Pokégear 3.0
- rationale: Play Pokegear 3.0 when able to find useful supporters.
- priced +1.1391 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +1.0811 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))
- priced +1.0013 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))

### mega_starmie `82227388-7` (Main, misattachment)

- Ledger chose `[0]` Attach Hero’s Cape → Cinderace (active · 160/160 · 1⚡)
- ruling was `[4]` End turn
- rationale: Save Hero's cape for our own main attacker.
- priced +0.2200 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":1159,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.2200 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":1159,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82228640-25` (Main, misattachment)

- Ledger chose `[0]` Attach Ignition Energy → Mega Starmie ex (active · 280/330)
- ruling was `[5]` Attach Basic {W} Energy → Mega Starmie ex (active · 280/330)
- rationale: Should have attached basic energy instead of ignition energy to active mega starmie, as its Jetting Blow is enough to KO opponents active while also sniping bench. Plus, Ignition Energy discards at end of turn, so should be saved for only when needed.
- priced +0.4251 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":280,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.3854 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":280,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.2345 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":1159,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":280,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82228640-7` (Main, sequencing_error)

- Ledger chose `[1]` Play Ultra Ball
- ruling was `[0]` Attach Basic {W} Energy → Staryu (active · 70/70)
- rationale: attach energy first. ultra ball is saved to find mega starmie, which we already have in hand. also dont use ultra ball and discard hilda, when hilda can find mega starmie AND an energy card, far better than ultra ball.
- priced +0.0575 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))
- priced +0.0453 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82229122-45` (Main, bad_target)

- Ledger chose `[3]` Attach Basic {W} Energy → Staryu (bench 2 · 70/70)
- ruling was `[16]` Retreat
- rationale: This requires Posture and Tier 1 search. Crustle is immune to Ex attackers, thus should retreat to Cinderace who would have KO'd it. Also, when playing Crustle deck, will need to rely on Staryu and Cinderace almost fully.
- priced +1.3491 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.2600 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0406 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82522698-62` (Main, sequencing_error)

- Ledger chose `[4]` Attach Basic {W} Energy → Mega Starmie ex (active · 310/330 · 1⚡)
- ruling was `[15]` Attack with Jetting Blow
- rationale: When the choice is present to win the game, always take that choice immediately
- priced +101.2687 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0467 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":310,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0383 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82522726-23` (Main, sequencing_error)

- Ledger chose `[0]` Play Salvatore
- ruling was `[2]` Evolve Mega Starmie ex → Staryu (active · 70/70 · 1⚡)
- rationale: Could have evolved active to mega starmie and attacked to win the game. always look for game winning move first.
- priced +1.3111 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1189,"playerIndex":1}]]]',))
- priced +1.0850 ActionIdentity(kind='evolve', parts=('[1,{"type":9},[[2,{"id":1031,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.7600 ActionIdentity(kind='evolve', parts=('[1,{"type":9},[[2,{"id":1031,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82523164-75` (Main, sequencing_error)

- Ledger chose `[1]` Attach Hero’s Cape → Mega Starmie ex (active · 210/330 · 3⚡)
- ruling was `[8]` Attack with Nebula Beam
- rationale: Attcking with Nebula Beam would have been a win, always take the winning move when able first
- priced +101.6743 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.2755 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3,3,3],"energyCards":[{"id":3,"playerIndex":1},{"id":3,"playerIndex":1},{"id":3,"playerIndex":1}],"hp":210,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.2200 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82523811-15` (Main, sequencing_error)

- Ledger chose `[1]` Attach Hero’s Cape → Staryu (bench 1 · 70/70)
- ruling was `[3]` Play Crushing Hammer
- rationale: Riolu had 1 energy, and if it became a mega lucario could have OHKO our active staryu
- priced +0.2200 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1112 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0752 ActionIdentity(kind='attack', parts=('[1,{"attackId":1486,"type":13},[]]',))

### mega_starmie `82523811-41` (Damage, bad_target)

- Ledger chose `[3]` opp Makuhita (bench 4 · 80/80)
- ruling was `[4]` opp Riolu (bench 5 · 80/80)
- rationale: Rioulu becomes Mega Lucario who needs only a single energy to deal significant damge, thus Rioulu is the snipe target.
- priced +0.2231 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":673,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.2047 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":150,"id":674,"maxHp":150,"playerIndex":0,"preEvolution":[{"id":673,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.2012 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":677,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82523811-59` (Main, misattachment)

- Ledger chose `[8]` Attack with Jetting Blow
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (active · 400/430 · 1⚡)
- rationale: SHould have added a second energy to the active Mega Starmie. this is became it has 400HP and cannot die next turn while we also have two more energies in hand. thus in two turns we can have a Mega Starmie with full energy to use Nebula Beam
- priced +1.7461 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0460 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":400,"id":1031,"maxHp":430,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[{"id":1159,"playerIndex":1}]}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82523811-61` (Damage, bad_target)

- Ledger chose `[4]` opp Makuhita (bench 5 · 80/80)
- ruling was `[3]` opp Riolu (bench 4 · 180/180)
- rationale: Riolu > Mega Lucario = Scary
- priced +0.2231 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":80,"id":673,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.2047 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":150,"id":674,"maxHp":150,"playerIndex":0,"preEvolution":[{"id":673,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.1973 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82523811-84` (Main, wasted_resource)

- Ledger chose `[2]` Attach Basic {W} Energy → Mega Starmie ex (bench 1 · 330/330 · 1⚡)
- ruling was `[4]` Attach Basic {W} Energy → Mega Starmie ex (active · 160/430 · 1⚡)
- rationale: Playing Salvatore when we do not have an in-play Staryu is 100% wasteful. never do this. Should have attached basic energy to bench, full HP Mega Starmie instead.
- priced +0.6099 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0645 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0162 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":160,"id":1031,"maxHp":430,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[{"id":1159,"playerIndex":1}]}]]]',))

### mega_starmie `82524455-6` (Main, wasted_resource)

- Ledger chose `[2]` Play Buddy-Buddy Poffin
- ruling was `[3]` Attach Basic {W} Energy → Staryu (active · 70/70)
- rationale: I had just played Buddy-buddy poffin and received no Staryu's back, thus i know that non are in my deck. therefor its a waste to play a second buddy'buddy poffin. that extra card in hand might come in useful later with an Ultra Ball. This requires a knowledge of what is in our deck, that should become fully known once we search it the first time. our prize cards can then be deduced from this.
- priced +0.5590 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1086,"playerIndex":1}]]]',))
- priced +0.2260 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1145,"playerIndex":1}]]]',))
- priced +0.0746 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82525101-110` (Main, wasted_resource)

- Ledger chose `[6]` Attach Hero’s Cape → Mega Starmie ex (active · 60/330 · 1⚡)
- ruling was `[4]` Attach Basic {W} Energy → Mega Starmie ex (active · 60/330 · 1⚡)
- rationale: Salvatore is worthless when no Staryu in play
- priced +0.5979 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.1719 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":60,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0075 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1120,"playerIndex":1}]]]',))

### mega_starmie `82525101-69` (Main, sequencing_error)

- Ledger chose `[3]` Attach Basic {W} Energy → Mega Starmie ex (bench 1 · 330/330 · 1⚡)
- ruling was `[2]` Attach Basic {W} Energy → Mega Starmie ex (active · 60/330)
- rationale: Attach available energy to a mon who needs it prior to throwing away hand. Cards that throw away hands need a through review.
- priced +0.0450 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0312 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1223,"playerIndex":1}]]]',))
- priced +0.0132 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":60,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82525101-92` (Main, sequencing_error)

- Ledger chose `[2]` Attach Basic {W} Energy → Mega Starmie ex (active · 330/330 · 1⚡)
- ruling was `[0]` Play Crushing Hammer
- rationale: Could have used two crushing hammers, attached energy, then attacked
- priced +1.7723 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0712 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82525741-100` (Main, sequencing_error)

- Ledger chose `[6]` Play Wally's Compassion
- ruling was `[10]` Attack with Jetting Blow
- rationale: Attack for the win when able
- priced +102.6785 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.6100 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))
- priced +0.0605 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82525741-58` (Main, wasted_resource)

- Ledger chose `[0]` Play Boss’s Orders
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (active · 210/330 · 1⚡)
- rationale: Boss's up Staryu will KO the Staryu, but we could have just done more damage to the main threat active starmie instead. that main threat will now just return to active will more HP than it otherwise would have had.
- priced +0.9744 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.5454 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1182,"playerIndex":0}]]]',))
- priced +0.0365 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":210,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82525741-77` (Main, sequencing_error)

- Ledger chose `[1]` Attach Basic {W} Energy → Staryu (bench 1 · 70/70)
- ruling was `[0]` Attach Basic {W} Energy → Mega Starmie ex (active · 310/430 · 1⚡)
- rationale: Attach before throwing away hand
- priced +0.4621 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.1102 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0406 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82525741-81` (Main, misattachment)

- Ledger chose `[3]` Attach Basic {W} Energy → Staryu (bench 2 · 70/70)
- ruling was `[2]` Attach Basic {W} Energy → Mega Starmie ex (bench 1 · 330/330)
- rationale: Should have attached second energy to our active to power it up towards Nebula Beam
- priced +0.4621 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0406 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0383 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82748422-51` (Main, sequencing_error)

- Ledger chose `[1]` Play Buddy-Buddy Poffin
- ruling was `[2]` Attack with Jetting Blow
- rationale: could have just attacked for the win
- priced +103.9620 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +1.1650 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82748522-15` (Main, sequencing_error)

- Ledger chose `[2]` Attach Basic {W} Energy → Staryu (active · 70/70)
- ruling was `[1]` Play Lillie's Determination
- rationale: Hilda was not helpful here because i already had an energy and two mega starmies in hand. The opponent was a huge threat due to a nearly full bench. thus i should have played lillie's determination in hopes of filling my bench for protection.
- priced +0.0453 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0095 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1225,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82749168-38` (Damage, bad_target)

- Ledger chose `[1]` opp Hoothoot (bench 2 · 70/70)
- ruling was `[0]` opp Dragapult ex (bench 1 · 320/320)
- rationale: Dargapult is the real threat here, snipe that.
- priced +0.1950 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":172,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1602 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":320,"id":121,"maxHp":320,"playerIndex":0,"preEvolution":[{"id":119,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82749168-65` (Main, wasted_resource)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[1]` Attack with Jetting Blow
- rationale: Lillie's just shuffled back our Ignition Energy, which might come in handy for our benched mega starmie. ignition energy highly valuable in this instance.
- priced +3.7581 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +2.4791 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0652 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))

### mega_starmie `82749168-88` (Main, sequencing_error)

- Ledger chose `[4]` Play Pokégear 3.0
- ruling was `[8]` Attack with Nebula Beam
- rationale: Could have just attacked for the win
- priced +101.5068 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +101.2326 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0435 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1122,"playerIndex":1}]]]',))

### mega_starmie `82749656-62` (Main, sequencing_error)

- Ledger chose `[0]` Evolve Mega Starmie ex → Staryu (bench 2 · 70/70)
- ruling was `[12]` Attack with Jetting Blow
- rationale: For any turn, do a consideration if there is a winning move as step 1, always. if there is, take that move immediately.
- priced +0.2998 ActionIdentity(kind='evolve', parts=('[0,{"type":9},[[2,{"id":1031,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1771 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0406 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82750161-59` (Main, misattachment)

- Ledger chose `[8]` Attach Basic {W} Energy → Mega Starmie ex (active · 300/330 · 2⚡)
- ruling was `[1]` Attach Ignition Energy → Mega Starmie ex (bench 1 · 330/330 · 1⚡)
- rationale: Since i can KO the opponents active with jetting blow, i would have attached an energy to the benched mega starmie.
- priced +1.7586 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0546 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3,3],"energyCards":[{"id":3,"playerIndex":1},{"id":3,"playerIndex":1}],"hp":300,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0406 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82751468-14` (Main, misattachment)

- Ledger chose `[4]` Retreat
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (bench 1 · 330/330)
- rationale: Here, we could have attached to Mega Starmie, retreated Cinderace, and KO'd the opponents active while sniping their bench. that would have been the better move. especially since we have additional protection with Wallys Compassion in our deck
- priced +0.2698 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))
- priced +0.0798 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0211 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82751468-57` (Main, missed_disruption)

- Ledger chose `[1]` Play Salvatore
- ruling was `[11]` Play Boss’s Orders
- rationale: We had already searched deck earlier in game, thus we know that one Mega Starmie is in the discard. that means this Salvatore play was a wasted use of a supporter. instead, a boss's orders could have gusted up the opponents main attacker that has no energy on it, potentially stalling them.
- priced +0.4812 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.3178 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1189,"playerIndex":1}]]]',))
- priced +0.0220 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":210,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `82751468-68` (Main, sequencing_error)

- Ledger chose `[2]` Evolve Mega Starmie ex → Staryu (bench 1 · 20/70)
- ruling was `[6]` Attack with Nebula Beam
- rationale: Attacking with Nebula Beam would have won the game.
- priced +103.9554 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.5537 ActionIdentity(kind='evolve', parts=('[1,{"type":9},[[2,{"id":1031,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":20,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.5015 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1189,"playerIndex":1}]]]',))

### mega_starmie `82752045-80` (Main, sequencing_error)

- Ledger chose `[11]` Attack with Jetting Blow
- ruling was `[8]` Play Night Stretcher
- rationale: We might as well recycle an energy to attach to our benched Mega Starmie at this point.
- priced +2.6764 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +1.2162 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1097,"playerIndex":1}]]]',))

### mega_starmie `82752604-106` (Main, sequencing_error)

- Ledger chose `[0]` Attach Basic {W} Energy → Mega Starmie ex (active · 210/330 · 1⚡)
- ruling was `[6]` Attack with Jetting Blow
- rationale: Attaching energy was meaningless that we could just attach and win the game.
- priced +103.7167 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.2484 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))
- priced +0.0220 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":210,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82752604-14` (Main, missed_ko)

- Ledger chose `[4]` Play Mega Signal
- ruling was `[0]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: a crushing hammer must never ever ever be played when opponents active pokemon has no energy attached
- priced +0.0960 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced +0.0938 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0406 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82752604-16` (Main, wasted_resource)

- Ledger chose `[0]` Play Mega Signal
- ruling was `[2]` Attack with Turbo Flare
- rationale: Shuffling here is a critial blunder. we have two staryus on the bench and two mega starmies in the hand. one staryu is about to receive 3 water energy. absolute critical blunder.
- priced +0.3983 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0960 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `82752604-88` (Main, sequencing_error)

- Ledger chose `[9]` Retreat
- ruling was `[2]` Attach Basic {W} Energy → Mega Starmie ex (bench 2 · 270/330 · 1⚡)
- rationale: attach energy to pokemon who need it prior to attacking

Also, the opponetns active has 320 HP. one Jetting Blow + Nebula Beam = 320. thus we could have done jetting blow this turn and knocked out their benched dreepy, then performed a nebula beam the following turn to KO the Dragapult, winning the game.
- priced +2.4610 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +1.3183 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.2893 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))

### mega_starmie `82753102-109` (Main, slow_setup)

- Ledger chose `[0]` Play Salvatore
- ruling was `[5]` Attack with Nebula Beam
- rationale: absolute critical blunder. had chance to KO opponents main line attacker capable of doing immense damage given the hand size of the opponent. about time we read posture.
- priced +2.0398 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +1.9002 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.3178 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1189,"playerIndex":1}]]]',))

### mega_starmie `82753102-37` (Main, wasted_resource)

- Ledger chose `[1]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- ruling was `[3]` Play Harlequin
- rationale: CRITICAL, never play crushing hammer when opponents active has no energy attached.
- priced +0.2834 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1223,"playerIndex":1}]]]',))
- priced +0.1133 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82753102-9` (Main, sequencing_error)

- Ledger chose `[2]` Attach Ignition Energy → Cinderace (active · 160/160)
- ruling was `[0]` Play Pokégear 3.0
- rationale: Should have played Pokegear 3.0 first in hopes of receiving a Hilda. 
- priced +0.3046 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":17,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1147 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))
- priced +0.0482 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1122,"playerIndex":1}]]]',))

### mega_starmie `82754241-11` (ToHand, other)

- Ledger chose `[0]` (card)
- ruling was `[1]` (card)
- rationale: lillie's determination is typically a better pick then harlequin, especially early game when lillie's allows for drawing 8 cards.
- priced +0.0900 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[12,{"id":1223,"playerIndex":1}]]]',))
- priced +0.0900 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[12,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='decline', parts=())

### mega_starmie `82754241-41` (Main, wasted_resource)

- Ledger chose `[2]` Retreat
- ruling was `[1]` Attack with Turbo Flare
- rationale: wasted crushing hammer. we are about to KO their active.
- priced +2.0210 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0120 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `82754875-52` (Main, missed_disruption)

- Ledger chose `[2]` Attack with Turbo Flare
- ruling was `[0]` Play Boss’s Orders
- rationale: Here is the perfect example of gusting to stall the opponent. They have Psyduck or fezandipiti that can be gusted up, both require single energy to retreat, which could have prevented an attack by the opponent during their following turn. stalling is important for us here because we have no bench.
- priced +0.5686 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0260 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":130,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82754875-8` (Main, wasted_resource)

- Ledger chose `[1]` Play Mega Signal
- ruling was `[2]` Play Lillie's Determination
- rationale: It must be set hard in stone that to develop a bench prior to attacking with Turbo Flare is key to this decks strategy as to allow for rapid energy acceleration. Therefor should play Lillie's Determinatin in hopes of a Staryu or Budd-Buddy poffin
- priced +1.2295 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.1492 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0310 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))

### mega_starmie `82756021-101` (Main, sequencing_error)

- Ledger chose `[1]` Play Salvatore
- ruling was `[4]` Attack with Jetting Blow
- rationale: just attack for the win and be done
- priced +103.4270 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.4660 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1189,"playerIndex":1}]]]',))
- priced +0.0875 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1225,"playerIndex":1}]]]',))

### mega_starmie `82756021-57` (Damage, bad_target)

- Ledger chose `[0]` opp Makuhita (bench 1 · 80/80 · 1⚡)
- ruling was `[2]` opp Mega Lucario ex (bench 3 · 340/340 · 1⚡)
- rationale: Benched Mega Lucario with single energy is our next threat. should be sniping that right away. need to build in awareness of prize card math. with this opponent, we must kill 2 mega lucarios for 6 prizr cards and the win. attacking any other pokemon is a waste.
- priced +0.2686 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":0}],"hp":80,"id":673,"maxHp":80,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1973 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1814 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":676,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82756664-103` (Damage, bad_target)

- Ledger chose `[2]` opp Solrock (bench 3 · 110/110 · 1⚡)
- ruling was `[1]` opp Mega Lucario ex (bench 2 · 290/340 · 5⚡)
- rationale: Benched mega lucario is the largest imediate threat. we must snipe that
- priced +0.2243 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[6],"energyCards":[{"id":6,"playerIndex":0}],"hp":110,"id":676,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1973 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":675,"maxHp":110,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1580 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[6,6,6,6,6],"energyCards":[{"id":6,"playerIndex":0},{"id":6,"playerIndex":0},{"id":6,"playerIndex":0},{"id":6,"playerIndex":0},{"id":6,"playerIndex":0}],"hp":290,"id":678,"maxHp":340,"playerIndex":0,"preEvolution":[{"id":677,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82756664-35` (Main, misattachment)

- Ledger chose `[0]` Attach Hero’s Cape → Cinderace (active · 30/130 · 1⚡)
- ruling was `[5]` Attach Basic {W} Energy → Mega Starmie ex (bench 1 · 330/330 · 2⚡)
- rationale: Prioritize fully loading a main attacker with energy over spreading out energy
- priced +0.5763 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.4307 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":30,"id":666,"maxHp":130,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.3233 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))

### mega_starmie `82756664-36` (Main, sequencing_error)

- Ledger chose `[0]` Attach Hero’s Cape → Cinderace (active · 30/130 · 1⚡)
- ruling was `[1]` Attach Hero’s Cape → Mega Starmie ex (bench 1 · 330/330 · 2⚡)
- rationale: attach the fucking heros cape already!
- priced +0.5763 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.4307 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":30,"id":666,"maxHp":130,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.3233 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))

### mega_starmie `82756664-74` (Main, wasted_resource)

- Ledger chose `[10]` Attach Basic {W} Energy → Mega Starmie ex (bench 2 · 330/330 · 1⚡)
- ruling was `[3]` Attach Ignition Energy → Mega Starmie ex (active · 30/330)
- rationale: Hilda was pointless given we have 2 energy in hand and know that 3rd mega starmie is in prize cards
- priced +0.0450 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0163 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":17,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":30,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0037 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82756664-9` (Main, sequencing_error)

- Ledger chose `[0]` Attach Hero’s Cape → Cinderace (active · 130/130 · 1⚡)
- ruling was `[1]` Attach Hero’s Cape → Staryu (bench 1 · 70/70)
- rationale: best not to shuffle back a heros cape when we are able to use it. plus, next turn we can evolve to mega starmie with 3 energy due to Turbo Flare energy acceleration. this, albeit small, is a very good opening hand.
- priced +0.4693 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.2200 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":130,"id":666,"maxHp":130,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.2200 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82756664-97` (ToActive, missed_disruption)

- Ledger chose `[1]` Mega Starmie ex (bench 2 · 330/330 · 1⚡)
- ruling was `[0]` Cinderace (bench 1 · 30/130 · 1⚡)
- rationale: Here is a great example of more nuanced play strategy. the opponents active has less than 50HP and our benched Mega Starmie has less than 3 energy. perfect situation to promote Cinderace, KO opponents active for 3 prize cards, and energy accelerate our mega starmie. This requires forward search i imagine. but we need to be able to spot moves like this.
- priced +0.3290 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.1980 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":30,"id":666,"maxHp":130,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0708 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `82866415-48` (Main, sequencing_error)

- Ledger chose `[2]` Attach Hero’s Cape → Mega Starmie ex (active · 280/330 · 3⚡)
- ruling was `[3]` Attach Hero’s Cape → Staryu (bench 1 · 70/70 · 1⚡)
- rationale: There is a clear bug with our ACE-SPEC Hero's Cape. here it should be attached to the benched Staryu with a single energy as to protect it from Jetting Blow
- priced +1.1391 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +1.0013 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.2431 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":1159,"playerIndex":0}],[4,{"appearThisTurn":true,"energies":[3,3,3],"energyCards":[{"id":3,"playerIndex":0},{"id":3,"playerIndex":0},{"id":3,"playerIndex":0}],"hp":280,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `82867148-48` (Discard, sequencing_error)

- Ledger chose `[7, 8]` Basic {W} Energy, Basic {W} Energy
- ruling was `[1]` Lillie's Determination
- rationale: CRITICAL: gave away boss's orders and Harlequin, key disruptors when we had two copies of lillie's and three mega starmies. discarding should weigh discarding duplicate hards more heavily
- priced +0.4016 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":3,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":3,"playerIndex":0}]]]'))
- priced +0.3857 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1031,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":3,"playerIndex":0}]]]'))
- priced +0.3186 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1227,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":3,"playerIndex":0}]]]'))

### mega_starmie `82867148-62` (Main, bad_retreat)

- Ledger chose `[7]` Play Buddy-Buddy Poffin
- ruling was `[8]` Attack with Turbo Flare
- rationale: CRITICAL: Should almost never retreat Cinderace into a Staryu with so many energies
- priced +1.3230 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.6485 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `83007714-135` (Main, slow_setup)

- Ledger chose `[1]` Play Night Stretcher
- ruling was `[9]` Attack with Nebula Beam
- rationale: Again, many other corrections state this, we need a hard rule that every single turn begins by analyzing if there is a match winning decision present. if there is, take it immediately to win the match.
- priced +102.2790 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.3192 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.2200 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1097,"playerIndex":1}]]]',))

### mega_starmie `83007714-7` (Main, misattachment)

- Ledger chose `[3]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- ruling was `[1]` Attach Ignition Energy → Cinderace (active · 160/160)
- rationale: CRITICAL: this is a regression, used to be fixed. In SETUP stage, Cinderace leasding with Staryu on bench. this is perfect. Cinderace must get the energy here.
- priced +0.0938 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0770 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))
- priced +0.0466 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":17,"playerIndex":1}],[4,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `83007714-8` (Main, wasted_resource)

- Ledger chose `[0]` Play Ultra Ball
- ruling was `[2]` End turn
- rationale: We have the Mega Starmie that we need and a Staryu on the bench, thus tossing the supporters is a poor trade. should simply not have played Ultra Ball in this instance.
- priced +0.0495 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))
- priced +0.0358 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))

### mega_starmie `83037962-48` (Main, misattachment)

- Ledger chose `[2]` Attach Basic {W} Energy → Mega Starmie ex (active · 210/330 · 1⚡)
- ruling was `[3]` Attach Basic {W} Energy → Staryu (bench 1 · 70/70)
- rationale: CRITICAL: Placed second energy on active doomed mega starmie. this deosnt allow it to attack with Nebula Beam, and we can see that opponent can perhaps use an ignition energy to be able to do Nebula Beam and kill us next turn. we must assume that worst case scenario. therefor should start powering up our reserve benched staryu
- priced +0.9772 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0220 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":210,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0016 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `83037962-49` (Main, misattachment)

- Ledger chose `[1]` Play Harlequin
- ruling was `[2]` Attack with Jetting Blow
- rationale: CRITICAL: shuffle logic needs work. here we disrupt our opponent, which is good. however we also give back a Mega Starmie AND an energy that we need next turn. poor gamble in my opinion
- priced +0.9772 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0355 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))
- priced +0.0010 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1097,"playerIndex":0}]]]',))

### mega_starmie `83037962-78` (Main, missed_win)

- Ledger chose `[6]` Play Wally's Compassion
- ruling was `[9]` Attack with Nebula Beam
- rationale: CRITICAL: playing Wallys Compassion has a COST that must be considered. we remove all energy from our wincon and heal them. but now we are no longer able to KO the opponent and win the match. huge blunder. Wallys Compassion usage cost must be considered along with whether or not we have an Ignition Energy in hand.
- priced +103.7602 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.8575 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))
- priced +0.3460 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))

### mega_starmie `83038055-51` (Main, sequencing_error)

- Ledger chose `[1]` Play Mega Signal
- ruling was `[3]` Attack with Nebula Beam
- rationale: Here our hand is quite strong for next turn, would not have shuffled it back. Shuffling requires an awareness of our hand strength for the following turn
- priced +0.9324 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.6006 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0960 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))

### mega_starmie `83053965-28` (Main, wasted_resource)

- Ledger chose `[1]` Play Crushing Hammer
- ruling was `[2]` Play Hilda
- rationale: CRITICAL: Our agent needs to start planning its turn ahead of time, mapping out potential outcomes, and then picking best path. if it did so, it would have seen that it can KO opponents active via Hilda for energy grab, attach to mega starmie, retreat to mega starmie, and jetting blow.
- priced +0.1054 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0132 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1120,"playerIndex":1}]]]',))
- priced +0.0018 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))

### mega_starmie `83053965-32` (Main, misattachment)

- Ledger chose `[0]` Attach Basic {W} Energy → Cinderace (active · 150/160)
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (bench 1 · 330/330)
- rationale: CRITICAL - Should have retreated Cinderace, attached to Meta Starmie, and KO'd opponents active
- priced +0.0879 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":150,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0406 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0018 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))

### mega_starmie `83053965-91` (Main, sequencing_error)

- Ledger chose `[7]` Attach Basic {W} Energy → Mega Starmie ex (bench 1 · 430/430 · 2⚡)
- ruling was `[13]` Retreat
- rationale: CRITICAL: This is another multi decision example showing that we need a turn planner system. it would have been better to retreat cinderance into mega starmie, attach 3rd energy, KO fezandipiti for 2 prize cards. 
- priced +0.3053 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0823 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[3,3],"energyCards":[{"id":3,"playerIndex":1},{"id":3,"playerIndex":1}],"hp":430,"id":1031,"maxHp":430,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[{"id":1159,"playerIndex":1}]}]]]',))
- priced +0.0255 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `83054602-32` (Main, sequencing_error)

- Ledger chose `[0]` Play Wally's Compassion
- ruling was `[3]` End turn
- rationale: CRITICAL: Attachng energy and then playing wallys compassion is never to be allowed. wallys has a cost of returning all energy to hand, losing our initiative.
- priced +0.2258 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1229,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0600 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))

### mega_starmie `83116081-21` (AttachFrom, slow_setup)

- Ledger chose `[1]` Staryu (bench 2 · 70/70)
- ruling was `[0]` Staryu (bench 1 · 70/70 · 1⚡)
- rationale: Fill up one wincons energy before spreading to other mons. Thus here, specific for this deck, with Cinderace's Turbo Flare, place all three energy on a single staryu if that staryu had 0 energy.
- priced +0.0883 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0537 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":true,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `83116081-76` (Main, other)

- Ledger chose `[2]` Play Buddy-Buddy Poffin
- ruling was `[5]` Play Wally's Compassion
- rationale: CRITICAL: Our active wincon was low on health and opponent could possibly KO it next turn. also, opponents active was KO'able with our Jetting Blow. Should have healed with Wally, attached single energy, KO opponent
- priced +3.2402 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.5455 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.1411 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))

### mega_starmie `83116501-70` (Main, wasted_resource)

- Ledger chose `[0]` Attach Ignition Energy → Mega Starmie ex (active · 330/330)
- ruling was `[7]` Attach Basic {W} Energy → Mega Starmie ex (active · 330/330)
- rationale: Here, 120 dmg with Jetting Blow + 50 dmg to benched rioulu is perferrable given that Nebula Beam will not KO Mega Lucario anyways
- priced +0.0995 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0746 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.0383 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `83117367-34` (Main, other)

- Ledger chose `[3]` Attack with Jetting Blow
- ruling was `[2]` Play Harlequin
- rationale: CRITICAL: Via Hilda, we have searched out deck. thus we know that there is a single Mega Starmie in our prize cards and non in deck. therefor Salvatore is a waste. a rule must be made that checking deck contents must be performed prior to any search card.
- priced +0.9530 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.8773 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `83117367-45` (Main, other)

- Ledger chose `[1]` Play Harlequin
- ruling was `[0]` Play Lillie's Determination
- rationale: CRITICAL: Via Hilda, we have searched out deck. thus we know that there is a single Mega Starmie in our prize cards and non in deck. therefor Salvatore is a waste. a rule must be made that checking deck contents must be performed prior to any search card.

PLUS, we need energy! CRITICAL CRITICAL
- priced +0.2164 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))
- priced +0.1683 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `83456015-35` (Main, sequencing_error)

- Ledger chose `[1]` Attach Ignition Energy → Mega Starmie ex (active · 210/330 · 1⚡)
- ruling was `[3]` Play Wally's Compassion
- rationale: CRITICAL: This is critical because of sequencing. Our opponent has mega starmie that can do 210 dmg. our active has 210 HP. the opponent's deck commonly runs ignition energy, thus we should prepare ourselves for that by healing first, then attaching Ignition Energy ourselves, then attacking for KO. Also might as well play the pokegear 3.0 before attaching.
- priced +0.9502 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.4527 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":210,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.2478 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))

### mega_starmie `83456015-38` (Main, ignored_threat)

- Ledger chose `[1]` Play Wally's Compassion
- ruling was `[6]` Attack with Nebula Beam
- rationale: CRITICAL: Complete blunder. We had opportunity to KO their main attacker for 3 prize points but we instead gusted up their 1 prize point pre-evolution.
- priced +3.4607 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.4425 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0538 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1229,"playerIndex":0}]]]',))

### mega_starmie `83457493-20` (Main, wrong_supporter)

- Ledger chose `[0]` Play Salvatore
- ruling was `[3]` Play Boss’s Orders
- rationale: We do not have energy to power Cinderace, thus we are behind in tempo. The Salvatore however nice, doesnt help our immediate turn. we need to stall our opponent here given the real risk they evolve into Mega Lucario and KO our Cinderace, putting us even further behind. 

Boss's Orders up their benched mon with hghest retreat cost and least amount of energy and lowest threat. That is Makuhita 
- priced +0.9860 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1189,"playerIndex":1}]]]',))
- priced +0.1713 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1182,"playerIndex":1}]]]',))
- priced +0.0138 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))

### mega_starmie `83457493-33` (Main, wasted_resource)

- Ledger chose `[0]` Play Night Stretcher
- ruling was `[3]` End turn
- rationale: CRITICAL: Cinderace shall never be recycled with Night Stretch because it can never be played outside of match setup.
- priced +0.0010 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1097,"playerIndex":1}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0240 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1086,"playerIndex":1}]]]',))

### mega_starmie `83661649-30` (Main, wrong_attack)

- Ledger chose `[0]` Play Harlequin
- ruling was `[2]` Attack with Jetting Blow
- rationale: Jetting Blow is better here to do some bench sniping because Nebula Beam will not KO them anyway. and one jetting blow + one nebula beam will KO them. also, worth anticipating that they will use wally compassion to fully heal.
- priced +1.0717 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.9339 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0841 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))

### mega_starmie `83661649-45` (Damage, bad_target)

- Ledger chose `[0]` opp Staryu (bench 1 · 70/70 · 1⚡)
- ruling was `[1]` opp Mega Starmie ex (bench 2 · 430/430)
- rationale: wasteful attacking staryu when we know that they will promote mega starmie next.
- priced +0.3728 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1267 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":430,"id":1031,"maxHp":430,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[{"id":1159,"playerIndex":1}]}]]]',))

### mega_starmie `83662396-19` (Main, sequencing_error)

- Ledger chose `[1]` Attack with Turbo Flare
- ruling was `[0]` Play Mega Signal
- rationale: should pull out a mega starmie here just to thin the deck.
- priced +1.3760 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[1,{"type":14},[]]',))
- priced -0.0210 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1145,"playerIndex":1}]]]',))

### mega_starmie `83663053-22` (Main, missed_win)

- Ledger chose `[3]` Play Pokégear 3.0
- ruling was `[5]` Attack with Jetting Blow
- rationale: Clear win path here in single decision, just attack with jetting blow
- priced +102.7283 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0522 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1122,"playerIndex":1}]]]',))
- priced +0.0060 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1225,"playerIndex":1}]]]',))

### mega_starmie `83664340-45` (Main, misattachment)

- Ledger chose `[2]` Attach Basic {W} Energy → Staryu (bench 2 · 70/70)
- ruling was `[0]` Attach Basic {W} Energy → Mega Starmie ex (active · 60/330)
- rationale: This conflicts with dont-feed-the-doomed but is still the better option. we need to keep pressure on our opponent by attacking and bench sniping. next turn we have both basic and ignition energy, thus we can keep attacking with our follow up Starmie. in this case, its better to feed the dammed.
- priced +0.0406 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0383 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0245 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":17,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":60,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `83664991-43` (Main, sequencing_error)

- Ledger chose `[4]` Retreat
- ruling was `[1]` Play Harlequin
- rationale: RULED 2026-08-20 (owner-approved triage batch B, extracted from the note): 'a perfect time to play Harlequin' + attack-last: Harlequin first, the Turbo Flare chip follows (the prior attack ruling is the follow-up, preserved below). Original note: "CRITICAL: This was a missed opportunity for prize math in our favor. save the ignition energy for next turn and chip them a bit with Cinderace. Also, opponent has 8 cards in hand, a perfect time to play Harlequin."
- priced +0.4218 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))
- priced +0.4075 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0913 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))

### mega_starmie `83665798-12` (Main, wasted_resource)

- Ledger chose `[0]` Play Mega Signal
- ruling was `[7]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: CRITICAL: Our Cinderace is not in danger here, therefor using Heros Cape here was a waste.
- priced +0.2260 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1145,"playerIndex":1}]]]',))
- priced +0.2200 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.2200 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":1159,"playerIndex":1}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `83665798-39` (Main, missed_win)

- Ledger chose `[3]` Play Lillie's Determination
- ruling was `[4]` Attack with Jetting Blow
- rationale: no reason to play lillies here, just attack for win. i think that the lethal line needs to be able to consider multiple decisions to a victory, then to take the shortest path.
- priced +102.8562 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +1.4307 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.1889 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))

### mega_starmie `83966968-78` (Main, wrong_supporter)

- Ledger chose `[12]` Play Boss’s Orders
- ruling was `[2]` Play Harlequin
- rationale: CRITICAL: Its highly important that we evolve our benched staryu or we risk loses a second mega starmie. deck has one mega starmie and 3 mega signals and 2 savaltores and 2 hildas. lots of chances that lead to mega starmie.
- priced +0.5521 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1182,"playerIndex":0}]]]',))
- priced +0.4732 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0170 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":0}],"hp":210,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `83966968-79` (Switch, bad_target)

- Ledger chose `[0]` opp Cinderace (bench 1 · 110/160)
- ruling was `[1]` opp Mega Starmie ex (bench 2 · 230/330)
- rationale: CRITICAL: Concerning prize math, KO'ing a Cinderace does not help us. we still need to KO 2 mega starmies. 
- priced +0.6771 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":110,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.4765 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":230,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.4149 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `83967840-54` (Discard, wasted_resource)

- Ledger chose `[1, 4]` Salvatore, Salvatore
- ruling was `[2]` Lillie's Determination
- rationale: i would have discarded one of our lillie's given that we have 2 in hand
- priced +0.1945 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1189,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":1189,"playerIndex":0}]]]'))
- priced +0.1625 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1189,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":666,"playerIndex":0}]]]'))
- priced +0.1195 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1189,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":1227,"playerIndex":0}]]]'))

### mega_starmie `83969481-55` (Main, wasted_resource)

- Ledger chose `[1]` Play Lillie's Determination
- ruling was `[4]` Attack with Jetting Blow
- rationale: During the end game where we have a single mega starmie against their two, id rather not shuffle back our wallys compassion. he can really save us against a nebula beam
- priced +0.7485 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0232 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `84897262-110` (ToHand, missed_win)

- Ledger chose `[0]` Staryu
- ruling was `[1]` Basic {W} Energy
- rationale: Grab energy first, attach to active, attack, win match
- priced +0.2700 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[3,{"id":1030,"playerIndex":1}]]]',))
- priced +0.0500 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[3,{"id":3,"playerIndex":1}]]]',))
- priced +0.0230 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[3,{"id":1031,"playerIndex":1}]]]',))

### mega_starmie `85163079-30` (Main, missed_win)

- Ledger chose `[2]` Attack with Jetting Blow
- ruling was `[0]` Play Boss’s Orders
- rationale: Should have gusted up their future wincon and KO it
- priced +2.0037 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +1.7301 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `85163079-51` (Main, missed_win)

- Ledger chose `[4]` Retreat
- ruling was `[1]` Attach Basic {W} Energy → Mega Starmie ex (active · 210/330 · 2⚡)
- rationale: Too conservative to attach energy to Cinderace. Our Mega Starmie is lost next turn, so be it, hit the opponent with everything we got and hope for an opportunity next turn.
- priced +0.3516 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.1367 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))
- priced +0.0415 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":3,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[3,3],"energyCards":[{"id":3,"playerIndex":0},{"id":3,"playerIndex":0}],"hp":210,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))

### mega_starmie `85163634-17` (Main, missed_win)

- Ledger chose `[2]` Play Ultra Ball
- ruling was `[5]` Attack with Turbo Flare
- rationale: Only issue with this blunder is that this move was taken one turn too early. we dont need the Starmie now. fetching it now risks enticing our opponent to disrupt us with a judge or harlequin or something. there is no cost to just wait a turn and fetch our Starmie then.
- priced +0.2513 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.0563 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0135 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))

### mega_starmie `85164605-41` (Main, wasted_resource)

- Ledger chose `[0]` Play Salvatore
- ruling was `[3]` Play Mega Signal
- rationale: Mega Signal, an Item, is less expensive than a Supporter, just play that instead
- priced +0.9604 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.7360 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1189,"playerIndex":1}]]]',))
- priced +0.6400 ActionIdentity(kind='evolve', parts=('[1,{"type":9},[[2,{"id":1031,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[3,3,3],"energyCards":[{"id":3,"playerIndex":1},{"id":3,"playerIndex":1},{"id":3,"playerIndex":1}],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `85164605-64` (Main, wasted_resource)

- Ledger chose `[3]` Play Ultra Ball
- ruling was `[5]` Attack with Jetting Blow
- rationale: CRITICAL: Played Ultra ball for nothing. MUST check deck and discard and prize cards prior to playing fetch cards always, as to verify what exists.
- priced +3.2067 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +1.6067 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.1546 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1121,"playerIndex":1}]]]',))

### mega_starmie `91393233-9` (Main, sequencing_error)

- Ledger chose `[2]` Play Buddy-Buddy Poffin
- ruling was `[3]` Attach Basic {W} Energy → Staryu (active · 70/70)
- rationale: CRITICAL: Play "free" cards that give us more information and a better board state, thus buddy buddy poffin and pokegear.

Also a failed calculation by PLANNED gamble. it states 71% chance to get a Mega Starmie to win the game. but it forgot that Mega Starmie also requires energy AND we can only evolve our Staryu via Salvatore this turn. Thus fetching Salvatore is our only win possibility.
- priced +0.5590 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.2208 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1227,"playerIndex":0}]]]',))
- priced +0.0531 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `91393371-38` (Main, sequencing_error)

- Ledger chose `[0]` Play Lillie's Determination
- ruling was `[3]` Attack with Nebula Beam
- rationale: CRITICAL: We had a chance to KO their 2 prize active but didnt take it. non-sensiscal
- priced +2.6496 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +1.6158 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0217 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))

### mega_starmie `91393371-60` (Main, sequencing_error)

- Ledger chose `[1]` Play Wally's Compassion
- ruling was `[5]` Play Pokégear 3.0
- rationale: 
- priced +1.3732 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +1.2287 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.8605 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1229,"playerIndex":1}]]]',))

### mega_starmie `91393371-9` (Main, sequencing_error)

- Ledger chose `[3]` Play Salvatore
- ruling was `[4]` Play Pokégear 3.0
- rationale: CRITICAL: Collect information before commiting our supporter. play Pokegear, and if we got a Hilda, we could have used that to fetch a basic energy as to not use our ignition energy.
- priced +0.4385 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1189,"playerIndex":1}]]]',))
- priced +0.2306 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":17,"playerIndex":1}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0731 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))

### mega_starmie `91394270-102` (ToActive, sequencing_error)

- Ledger chose `[0]` Mega Starmie ex (bench 1 · 270/330)
- ruling was `[1]` Cinderace (bench 2 · 160/160)
- rationale: Promote Cinderace. we can always retreat him from free during turn depending on the card that we draw.
- priced +0.0260 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":270,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced -0.0764 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":10,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced -0.2438 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `91394270-12` (Main, sequencing_error)

- Ledger chose `[1]` Play Mega Signal
- ruling was `[0]` Play Pokégear 3.0
- rationale: CRITICAL: Why our ideal starter?
- priced +0.0960 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced +0.0438 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))
- priced +0.0018 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))

### mega_starmie `91394270-9` (Main, sequencing_error)

- Ledger chose `[1]` Play Salvatore
- ruling was `[2]` Play Pokégear 3.0
- rationale: CRITICAL: Obtain free information with Pokegear. if it finds Hilda, we then can fetch an energy for our Cinderace. We dont need a Starmie now anyways, we have a Mega Signal, which is cheaper to use than Salvatore.
- priced +0.8660 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))
- priced +0.2260 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced +0.0431 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `92090133-14` (Main, missed_win)

- Ledger chose `[0]` Play Hilda
- ruling was `[1]` Play Harlequin
- rationale: Worth gambling here in hopes of getting a Stryu or something that can fetch a staryu as to take full advantage of Turbo Flare
- priced +0.0866 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0420 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1225,"playerIndex":0}]]]',))
- priced +0.0408 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))

### mega_starmie `92091149-14` (Main, missed_win)

- Ledger chose `[1]` Play Staryu
- ruling was `[2]` Attack with Turbo Flare
- rationale: RULED 2026-08-20 (owner-approved triage batch B, extracted from the note): 'didnt attack when had the chance' -> Turbo Flare. Original note: "CRITICAL: didnt attack when had the chance"
- priced +0.6150 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.1000 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1030,"playerIndex":1}]]]',))
- priced +0.0960 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1145,"playerIndex":1}]]]',))

### mega_starmie `92092096-21` (Main, missed_win)

- Ledger chose `[1]` Attach Hero’s Cape → Cinderace (active · 160/160)
- ruling was `[3]` Attach Basic {W} Energy → Cinderace (active · 160/160)
- rationale: CRITICAL: Our Cinderace needs to attack to apply pressure and to accelerate energy,
- priced +0.2200 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":1159,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.2200 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":1159,"playerIndex":0}],[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":0,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0995 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))

### mega_starmie `92102433-89` (ToActive, missed_win)

- Ledger chose `[1]` Mega Starmie ex (bench 2 · 330/330 · 1⚡)
- ruling was `[0]` Cinderace (bench 1 · 160/160)
- rationale: CRITICAL: They have a stadium in play that prevents damage done to non-rule box. this means we cannot damage their pokemon except for with mega starmie's nebula beam, which ignores effects. thus we promoto Cinderace, attach energy, attack with Turbo Flare and give 2 eneergy to starmie giving it a total of 3 for Nebula Beam next turn
- priced +0.0600 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[3],"energyCards":[{"id":3,"playerIndex":1}],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced +0.0260 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0242 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `92104376-60` (Main, wasted_resource)

- Ledger chose `[0]` Play Mega Signal
- ruling was `[7]` Attack with Jetting Blow
- rationale: Our active is not doomed. Just attack and snipe one of their Riolus
- priced +1.4808 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.0658 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1227,"playerIndex":1}]]]',))
- priced +0.0180 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1145,"playerIndex":1}]]]',))

### mega_starmie `92104376-81` (Main, wasted_resource)

- Ledger chose `[10]` Evolve Mega Starmie ex → Staryu (bench 3 · 70/70)
- ruling was `[1]` Attach Ignition Energy → Mega Starmie ex (active · 200/330 · 1⚡)
- rationale: RULED 2026-08-20 (owner-approved triage batch A): the note ENDORSES the agent's own pick, so correct = chosen. The chosen attach IS the develop the note asks for. Original note: "develop before attacking."
- priced +0.5014 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.3280 ActionIdentity(kind='evolve', parts=('[1,{"type":9},[[2,{"id":1031,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0700 ActionIdentity(kind='attach', parts=('[1,{"type":8},[[2,{"id":3,"playerIndex":1}],[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `92104376-86` (ToActive, prize_mismanagement)

- Ledger chose `[1]` Mega Starmie ex (bench 2 · 330/330)
- ruling was `[0]` Cinderace (bench 1 · 160/160)
- rationale: CRITICAL: for this deck, we want opponent to take out a starmie, cinderace, and one more starmie for 7 total prize cards. here we could have promoted cinderace, attached to him, attacked, getting our benched starmie to 3 energy while putting their mega lucario into KO range.
- priced +0.0260 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":330,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))
- priced -0.2300 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced -0.2438 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":160,"id":666,"maxHp":160,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `92129564-22` (Main, sequencing_error)

- Ledger chose `[0]` Play Mega Signal
- ruling was `[1]` Attack with Water Gun
- rationale: why not attack?
- priced +0.2260 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced +0.0680 ActionIdentity(kind='attack', parts=('[0,{"attackId":1486,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `92131448-44` (Discard, misattachment)

- Ledger chose `[0, 5]` Salvatore, Ignition Energy
- ruling was `[0, 1]` Salvatore, Mega Signal
- rationale: given a mega starmie and salvatore in hand, we can discard the second salvatore and mega signal. crushing hammer is useful during this turn.
- priced +0.2025 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1189,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":17,"playerIndex":0}]]]'))
- priced +0.2025 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1145,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":17,"playerIndex":0}]]]'))
- priced +0.1945 ActionIdentity(kind='card', parts=('[0,{"playerIndex":0,"type":3},[[2,{"id":1145,"playerIndex":0}]]]', '[0,{"playerIndex":0,"type":3},[[2,{"id":1189,"playerIndex":0}]]]'))

### mega_starmie `92455378-14` (Main, slow_setup)

- Ledger chose `[5]` Play Buddy-Buddy Poffin
- ruling was `[3, 5]` Play Pokégear 3.0, Play Buddy-Buddy Poffin
- rationale: Collect free information first with pokegear and buddy buddy. would be nice to find a hilda
- priced +0.5590 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1086,"playerIndex":0}]]]',))
- priced +0.4190 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))
- priced +0.0358 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `92455378-89` (Main, sequencing_error)

- Ledger chose `[1]` Attach Ignition Energy → Mega Starmie ex (active · 70/330)
- ruling was `[]` 
- rationale: 
- priced +0.5016 ActionIdentity(kind='attach', parts=('[0,{"type":8},[[2,{"id":17,"playerIndex":0}],[4,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1031,"maxHp":330,"playerIndex":0,"preEvolution":[{"id":1030,"playerIndex":0}],"tools":[]}]]]',))
- priced +0.2200 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1097,"playerIndex":0}]]]',))
- priced +0.0534 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `92458248-23` (Main, sequencing_error)

- Ledger chose `[6]` Play Mega Signal
- ruling was `[0]` Play Pokégear 3.0
- rationale: CRITICAL: Again, game froze on my turn, HUGE ISSUE!
- priced +0.2260 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced +0.1147 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1121,"playerIndex":0}]]]',))
- priced +0.0488 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))

### mega_starmie `92459166-120` (Main, sequencing_error)

- Ledger chose `[3]` Retreat
- ruling was `[1]` Attack with Jetting Blow
- rationale: CRITICAL: given their active lucario has 220 HP, a nebula beam does not KO it, but two jetting blows does. with two jetting blows and sniping their benched lucario, we can KO both of their lucarios next turn
- priced +0.8395 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.7837 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.2788 ActionIdentity(kind='retreat', parts=('[0,{"type":12},[]]',))

### mega_starmie `92459166-82` (Main, sequencing_error)

- Ledger chose `[1]` Attack with Jetting Blow
- ruling was `[0]` Play Crushing Hammer
- rationale: play the available hammer first before attacking
- priced +1.9805 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))
- priced -0.0003 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1120,"playerIndex":0}]]]',))

### mega_starmie `92591287-49` (Main, wasted_resource)

- Ledger chose `[1]` Play Mega Signal
- ruling was `[3]` Attack with Nebula Beam
- rationale: CRITICAL: Save blunder as this matches other frame.
- priced +0.4446 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.0180 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1097,"playerIndex":0}]]]',))

### mega_starmie `92591287-80` (Damage, bad_target)

- Ledger chose `[1]` opp Staryu (bench 2 · 70/70)
- ruling was `[0]` opp Mega Starmie ex (bench 1 · 280/330)
- rationale: Snipe their fully evolved primary attacker
- priced +0.3200 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.1363 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":false,"energies":[],"energyCards":[],"hp":280,"id":1031,"maxHp":330,"playerIndex":1,"preEvolution":[{"id":1030,"playerIndex":1}],"tools":[]}]]]',))

### mega_starmie `92644488-14` (Main, sequencing_error)

- Ledger chose `[1]` Play Salvatore
- ruling was `[0]` Play Pokégear 3.0
- rationale: CRITICAL: Play Pokegear first. we hope to fetch a Hilda as to fetch an energy
- priced +0.8560 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1189,"playerIndex":0}]]]',))
- priced +0.0530 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1122,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='end', parts=('[0,{"type":14},[]]',))

### mega_starmie `92645419-137` (Main, missed_disruption)

- Ledger chose `[3]` Retreat
- ruling was `[0]` Play Harlequin
- rationale: CRITICAL: disrupt with harlequin and refil our hand. every other card we have in this hand is literally worthless
- priced +0.2076 ActionIdentity(kind='attack', parts=('[1,{"attackId":965,"type":13},[]]',))
- priced +0.1812 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1223,"playerIndex":1}]]]',))
- priced +0.1736 ActionIdentity(kind='retreat', parts=('[1,{"type":12},[]]',))

### mega_starmie `92645419-25` (AttachFrom, misattachment)

- Ledger chose `[0]` Staryu (bench 1 · 70/70 · 2⚡)
- ruling was `[1]` Staryu (bench 2 · 70/70)
- rationale: with this board setup, where their active is doomed during our next turn, i would diversify energy a little by placing 2 energy on one staryu and one on another 

NOTE 2026-08-20 (user, doctrine articulation — ruling UNCHANGED): this is a TEMPO play; read the opponent's board and weigh their strength against ours. We have an easy KO next turn (likely Cinderace again; if not, Starmie's Jetting Blow), so there is no immediate need for Nebula Beam — hence diversify. The concentrate rulings elsewhere in the corpus stay the default when the opponent has a live threat.
- priced +0.1128 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":true,"energies":[3,3],"energyCards":[{"id":3,"playerIndex":1},{"id":3,"playerIndex":1}],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))
- priced +0.0883 ActionIdentity(kind='card', parts=('[1,{"playerIndex":1,"type":3},[[5,{"appearThisTurn":true,"energies":[],"energyCards":[],"hp":70,"id":1030,"maxHp":70,"playerIndex":1,"preEvolution":[],"tools":[]}]]]',))

### mega_starmie `92645419-64` (Main, wasted_resource)

- Ledger chose `[0]` Play Wally's Compassion
- ruling was `[3]` Attack with Nebula Beam
- rationale: CRITICAL: Nebula Beam converts the doomed active into 210 damage and starts the faster prize line; healing delays damage and increases Resentful Refrain.
- priced +1.0495 ActionIdentity(kind='attack', parts=('[1,{"attackId":1487,"type":13},[]]',))
- priced +0.9774 ActionIdentity(kind='attack', parts=('[1,{"attackId":1488,"type":13},[]]',))
- priced +0.1177 ActionIdentity(kind='play', parts=('[1,{"type":7},[[2,{"id":1229,"playerIndex":1}]]]',))

### mega_starmie `92646350-34` (Main, sequencing_error)

- Ledger chose `[2]` Play Mega Signal
- ruling was `[0]` Play Harlequin
- rationale: CRITICAL: must gamble for staryus
- priced +1.0542 ActionIdentity(kind='attack', parts=('[0,{"attackId":965,"type":13},[]]',))
- priced +0.0310 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1145,"playerIndex":0}]]]',))
- priced +0.0000 ActionIdentity(kind='ability', parts=('[{"area":7,"index":0,"type":10},[]]',))

### mega_starmie `92646350-79` (Main, misattachment)

- Ledger chose `[0]` Play Wally's Compassion
- ruling was `[8]` Attack with Nebula Beam
- rationale: CRITICAL: never waste an energy attaching to pokemon that has no use for it
- priced +1.5236 ActionIdentity(kind='attack', parts=('[0,{"attackId":1487,"type":13},[]]',))
- priced +1.3183 ActionIdentity(kind='attack', parts=('[0,{"attackId":1488,"type":13},[]]',))
- priced +0.1958 ActionIdentity(kind='play', parts=('[0,{"type":7},[[2,{"id":1223,"playerIndex":0}]]]',))

