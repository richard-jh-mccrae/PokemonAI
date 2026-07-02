# Agent Runtime (`common/`)

Deck-agnostic runtime agent code, shared across deck builds. It defines the **Pilot**
decision architecture and the **Base Value Model**, and its first capability is
**Scouting** — recognize the opponent's deck from what it reveals and produce the **Read**.

Shared game/meta vocabulary (`Archetype`, `Main-line` / `Sub-line` / `Engine Pokémon`,
`Meta`, `Rank Band`) is defined in the [Meta Tracker](../../CONTEXT.md) context and reused here.

## Language

### Scouting

**Read**:
The live, per-turn assessment of the current matchup: the most-likely opponent
Archetype(s) with confidence, predicted development, and the resulting threats and
targets. Pure data — it describes the matchup, it does not act on it.
_Avoid_: matchup, scout result, prediction

**Posture**:
How the agent changes play in response to the Read — a deck-agnostic generic core in the
Pilot (seek `targets`, avoid `threats`, calibrate aggression to favourability) plus
deck-specific Read-conditioned Hypotheses, all scaled by the Read's confidence. A
*consumer* of the Read, not part of Scouting itself.
_Avoid_: stance, strategy

**Signature**:
A card highly diagnostic of an Archetype — it appears in most of that archetype's
decks and few others (high likelihood ratio), so revealing it sharply moves
recognition (e.g. Solrock → Mega Lucario ex). Derived from the data, not curated;
surfaced in the artifact for explainability and fast-path recognition.
_Avoid_: tell, flag, marker

**Threat**:
An attacker the recognized Archetype relies on, described *objectively* — the
Pokémon, its damage output, energy cost (tempo to come online), key abilities, and
prize value (ex/Mega). Whether it actually KOs *my* board is the consumer's job.
_Avoid_: danger, attacker

**Target**:
A high-value point of attack on the opponent's board, described *objectively* —
their engine/setup Pokémon, the fragile pre-evolutions of their win-condition, and
ex/Mega bodies (prize math), with weakness/HP exposed as data. Which target *I* can
exploit is the consumer's job.
_Avoid_: weak point, mark

**Representative Build**:
The recency-weighted most-common decklist of an Archetype — the baseline the Read
predicts against (drives `expected_cards` and `evolution_paths`). The latest
dominant variant, not an all-time average.
_Avoid_: canonical deck, average deck

**Dossier**:
The per-Archetype compiled scouting profile in the shipped artifact — card-inclusion
likelihoods, Signatures, Representative Build, evolution lines, threats and targets,
all referencing cards by id. Band-independent; per-band frequency is blended into a
single shipped `priors` map.
_Avoid_: profile, card pool

**Matchup Brief**:
The hand-authored, *objective* strategic profile of one opponent Archetype — how it wins, its
tempo, its exploitable weakness, and which Threats / Targets matter against it. Captures the
strategic understanding the auto-compiled Dossier lacks: the Dossier has the *cards*, the Brief has
the *gameplan against them*. Shared across all our decks; each agent *relativizes* it to its own
cards. Authored, not compiled — so it lives beside the artifact, never inside it (the artifact is
regenerated from the meta and would clobber it).
_Avoid_: Dossier (the auto-compiled card profile), Doctrine (a deck's own STRATEGY.md or a
card-mechanic Mixin), scouting report, matchup table (the compiled win-rates)

**Scout**:
The stateful runtime component (`common/scouting`) that accumulates revealed-card
evidence across a match and produces the Read each decision. Owns the match-scoped
state, auto-reset, and the loaded artifact + card-stat cache; exposes
`.observe(obs) -> Read`.
_Avoid_: recognizer, detector

### Card knowledge

**Function Tag**:
A coarse label for a *behavioral* function a card performs (`draw`, `search`, `energy_accel`,
`gust`, `heal`, `spread`, `poison`, …) — derived offline by **probing** the card in the engine
(reading the `Log`/`SelectContext` its play produces) plus a thin curated override, shipped in
`card_functions.json` for O(1) mid-match lookup. **Behavioral only**: structural facts (ex/Mega
→ prizes, trainer subtype, ACE SPEC) are read straight off the engine's `CardData`, never tagged.
A *routing hint*, not an outcome — the Search API still resolves exact effects.
_Avoid_: ability/effect (the card's full behavior; a tag is the coarse category), structural tag
(ex/trainer-type — those come from `CardData`), embedding (a rejected approach — use exact tags)

**Attack Effect**:
The per-attack, machine-readable effect facts of a *single* attack — its damage and energy cost plus
the **effect modifiers** that bend the closed-form damage math: ignores-Ability / ignores-Weakness /
ignores-Resistance, self-recoil, bench-snipe rider, hand-size scaling, "no damage to the Active",
conditional / coin-flip damage, the **energy-recover rider** ("attach up to N Basic {X} Energy
from your discard pile" — the Aura Jab / Regi Charge class: the Tactical layer credits the
recoverable fuel as development value, and charges a **self-lock cost** on a next-turn-locking nuke
when a lock-free attack was affordable), and the **bench-partner condition** ("does nothing without
<X> on your Bench" — the oracle zeroes exact/min on the live board; "max" keeps printed since the
opponent can bench the partner first). The card-tier sibling for Trainers is the **damage-boost
fact** (`CardStat.damageBoost` — Premium Power Pro / Maximum Belt: this-turn plays tracked
match-scoped by `TurnBoostTracker`, attached Tools read off the holder, both priced before W/R and
crossing-checked by the boost-lethal tactical). **Attack-keyed** (by `attackId`) — the attack-tier counterpart to the
card-tier structural stats (`CardStat`) and the behavioral, card-level `Function Tag`. Consumed by the
closed-form (**Tier-0**) combat math so the agent picks the right attack *before* paying the Engine
Search sim budget — e.g. Mega Starmie ex's Nebula Beam lands through Crustle's ex-damage immunity
because it *ignores Abilities*, while its Jetting Blow does not. Derived and **verified against the
simulator** (the differential damage audit — actual dealt HP vs closed-form prediction), never recalled
from memory. Realized as the `AttackStat` record the stat provider builds beside `CardStat`.
_Avoid_: Function Tag (behavioral, coarse, card-level), CardStat / structural fact (card-level, not
per-attack), damage table (the raw printed number — an Attack Effect carries the modifiers that bend it)

**Damage Formula**:
The closed-form damage expression of a single attack — `base + per_unit × count(variable)` over a
CLOSED vocabulary of state variables (own/opponent hand size, attached Energy, discard-pile Energy,
…), evaluated against the live board at decision time. Damage that scales on **visible** state is
thereby *exact* (Alakazam's hand-size counters, Kyogre's discard count); a **hidden**-state scaler
(Mega Abomasnow ex's deck-discard) is bounded soundly via the deck tracker (pigeonhole floor) and
estimated via Deck-Content Odds; only **true randomness** (coin flips) is carried as measured
`min`/`max` bounds — my Lethal math reads the floor (sound), Incoming reads the ceiling (worst-case).
Fitted by sweep-probing the engine (varying one state variable and regressing the dealt damage),
never text-parsed.
_Avoid_: expected value (a probability blend — breaks soundness in both directions), printed damage
(the base term only), bounds (the coin-RNG fallback, not the general shape)

**Effect Clause**:
One machine-readable clause of a Trainer's or Ability's effect — `{kind, amount, target restriction,
rider}` — so a multi-clause card is a LIST of clauses (Wally's Compassion = heal(all, Mega-only) +
bounce-Energy(→hand)). The parametric card-tier counterpart of the attack-tier **Attack Effect**:
the **Function Tag** stays the coarse boolean *routing trigger* (`heal`), the Effect Clause carries
the *quantities the math reads* (150 vs 60 vs all; the Energy-discard cost; the Mega-only gate).
Measured from the engine probe's own logs (heal amount = the `HP_CHANGE` value, restriction = which
targets the select actually offers), with a hand-authored override tail for clauses no probe board
can trigger. Shipped as `card_effects.json` beside the tag table.
_Avoid_: Function Tag (boolean, coarse — a Clause is parametric), card text (the free-text source;
a Clause is the measured, structured fact), effect (unqualified — say which tier)

**Transient Effect**:
A one-turn effect an ATTACK grants — "during your (opponent's) next turn …": a damage shield
(takes-less / prevent-all), a self-lock (can't attack / can't reuse the same attack), a next-turn
damage bonus, a retreat-lock. Invisible in the observation (no per-Pokémon effect state), so it is
**inferred from the ATTACK log stream** by the match-scoped `TransientTracker` — deterministic,
serial-bound (leaving the Active ends the match-by-serial), expiring when the granter's next turn
starts. Consumed by the damage oracle (a live shield joins the defender math, pierced by
ignores-effects attacks) and by Incoming (a locked attacker threatens 0, a bonused one more).
_Avoid_: status/Special Condition (poison/sleep/… — engine-exposed player flags, a different
mechanism), buff/debuff (vague), effect (unqualified — say which tier)

**Hand Refresh**:
The umbrella concept for a card that throws your whole hand away to draw a fresh one. Splits by
*where the old hand goes*, because that governs recoverability and the pull pool: a **Shuffle-Refresh**
sends the hand into the *deck* then draws (recoverable — the cards rejoin what you can pull); a
**Discard-Refresh** sends it to the *discard* then draws (gone unless a `recycle` card retrieves it).
_Avoid_: hand dump, draw supporter (too broad), discard-hand (only one of the two sub-kinds)

**Shuffle-Refresh**:
A Hand Refresh that shuffles your hand into your *deck* and then draws (Lillie's Determination, Judge,
Harlequin, Lacey). Tagged `shuffle_hand`. Some are also `hand_disruption` (both players refresh — Judge,
Harlequin). Distinct from `recycle` (that pulls *out of* the discard, the opposite direction).
_Avoid_: discard_hand / recycle_hand (misname the motion — it's hand→deck, not a discard or a discard-pull)

**Discard-Refresh**:
A Hand Refresh that sends your hand to the *discard* and then draws (Larry's Skill, Amarys; and a few
attacks). Out of scope for the current Shuffle-Refresh build; noted as the sibling mechanic.
_Avoid_: discard_hand (reserve a precise tag if/when this is built)

**Evolving Threat**:
A benched pre-evolution whose evolution line eventually reaches an attacker (a form that can OHKO a
typical Active) — worth sniping *before* it comes online, even while it still carries no Energy.
A purely **generic, deck-agnostic** structural fact: derived by inverting the engine card table's
`evolvesFrom` into a forward map and reading the line's eventual damage. Distinct from a **Threat**
(the attacker itself, already a payoff) and from an **EvoPath** (the *opponent-specific* prediction
from the Read's Dossier — what *this* archetype actually runs). The generic forward map is the
provider primitive both will share; the Read later refines an Evolving Threat's *accuracy*.
_Avoid_: evolution threat / future attacker (use "Evolving Threat"), EvoPath (that's the Read's
opponent-specific line), fragile_preevo (that's the `Intel.role` label, not the card-knowledge fact)

**Irreplaceable Tool**:
A one-per-deck Pokémon Tool with no recovery path — an **ACE SPEC** (read off `CardData`, max one per
deck) that, once lost, is gone for the game (no second copy is legal; a `recycle` card returns a Pokémon
or Energy, never a Tool — e.g. Hero's Cape). Its scarcity governs how it is played: never frittered on
an off-role body, and **never voluntarily shuffled away** by a Hand Refresh while a target exists.
_Avoid_: ACE SPEC (the structural fact; an Irreplaceable Tool is the *play* consequence of it), one-of
(a deckbuild count, not the no-recovery property)

### Decision Architecture

**Fetch**:
A card that presents a *choose-from-deck* select — the engine reveals a set of deck cards and the
agent picks **which** to pull (Ultra Ball, Nest Ball, Mega Signal, Buddy-Buddy Poffin). Spans the
Function Tags `search` / `dig` / `bench_fill` / `tutor_*`. Distinct from **draw** (random
top-of-deck, no pick — Professor's Research / Iono), which the doctrine excludes. Governed by the
**Fetch Doctrine** (the `search`-family section of [general-strategy.md](../../docs/general-strategy.md)):
the whether-to-play / what-to-grab / what-to-discard decisions a fetch entails.
_Avoid_: tutor (TCG jargon for the same thing — say "fetch"/"search"), draw (no pick)

**Deck-Content Odds**:
The **probabilistic** read of my own deck — `P(deck still contains card C)` — the COMPLEMENT to the
**sound** deck-emptiness oracle (`deck_definitely_empty_of`, which is certain-or-silent). A card's
unseen copies (decklist − visible) are split **hypergeometrically** over the hidden face-down prize
slots ([deck_odds.py](deck_odds.py); `Board.deck_contains_probability`, ADR-0029). It **agrees with the
sound oracle at the extremes** (provably-empty → 0.0; pigeonhole-certain or prize-resolved → 1.0) and
estimates the uncertain middle the sound oracle is silent on — answering *"should I keep hunting C?"*
when the prizes are still hidden. Consumed as a **soft** whiff suppressor (`dont-search-a-probable-whiff`),
never replacing the sound gate. Own-deck only.
_Avoid_: deck tracker / deck-emptiness oracle (that's the SOUND, certain-or-silent half — these two are
deliberately distinct epistemics), Scout/Read (that's opponent-deck recognition)

**Stranded Payoff**:
An evolved win-condition (a Stage-1/2/Mega) fetched or held with **no deployable base** — no Line
pre-evolution in play **or hand** to evolve it from. A dead card until a base appears, so at a search
the **base** outranks it (`fetch-base-before-stranded-payoff`). The signal is `wincon_base_deployable`
(a base IS in play/hand → the payoff is deployable, prefer it again). Purely structural (Line path +
visible zones); needs no deck deduction.
_Avoid_: dead draw (that's any unplayable card — a Stranded Payoff is specifically the *evolved
win-condition* with no base)

**Acceleration Recipient**:
A **benched** Line member (a pre-evolution or the payoff) that a bench-targeting accelerator loads
Energy onto — e.g. Cinderace's Turbo Flare attaches 3 Basic Energy to the Bench, so a benched Staryu
is its recipient. With **no** recipient the acceleration is wasted, so developing one is the top setup
priority while the accelerator is Active (`accel_recipient_missing` → `develop-the-accel-recipient`).
_Avoid_: target (overloaded — reserve "recipient" for the body that *receives* accelerated Energy)

**Pilot**:
A deck's complete in-match decision engine — the shared `common/` component behind every
choice. A deck customises it only by supplying a Strategy.
_Avoid_: agent (the Kaggle entry function), brain, AI

**Plan**:
The Pilot's current-turn strategic mode — one of a closed set (`SETUP`, `RACE`,
`STABILIZE`, `CLOSE`) — chosen by shared Pilot logic parameterized by the Strategy's
win-condition-readiness predicate. It conditions option scoring.
_Avoid_: Strategy, Posture, AttackPlan (that's the Score-layer attack choice)

**Strategy**:
A deck's static, declared doctrine — win-condition line(s), setup priorities, energy
targets, and per-Function-Tag / per-card weights — supplied by `agents/<deck>/strategy.py`
as a registry of named, testable hypotheses.
_Avoid_: the Strategy Category (the competition), Plan, "hard-coded logic"

**General Strategy**:
The deck-agnostic baseline of Hypotheses shipped in `common/`, applied to every deck beneath
its own Strategy — generic competence (tempo, prize-awareness) keyed on universal Function Tags
and engine card stats. The Pilot scores it together with the deck Strategy; a deck specialises
or disables one of its rules by overriding the weight **by id** — an **authored seed override**
(declared in the deck's Strategy, doctrine-driven) or a **learned override** (tuner-written,
from replays/training); the learned layer wins.
_Avoid_: Strategy (the per-deck doctrine), Playbook, Posture (the opponent-driven generic core)

**Doctrine**:
A self-contained module for ONE card archetype (Gust, Fetch, Shuffle-Refresh, Tool) owning BOTH its
positional Hypotheses AND the Pilot-side closed-form code it needs — a `*Mixin` the Pilot inherits —
so it reads "one file, end to end." Each is anchored to its own ADR and lives in
`common/strategy/doctrines/`. The defining trait is the Mixin: a Doctrine carries closed-form
tactical code (a KO oracle, a value comparator) that can't be expressed as a tunable weight.
_Avoid_: rule group / category (a Baseline Cluster is those); General Strategy (the assembled whole)

**Baseline Cluster**:
A grouping of deck-agnostic General-Strategy Hypotheses by the **decision-context** they fire on
(`energy` / `snipe` / `promote` / `retreat` / `bench` / `tool` / `evolution` / `heal` / `opening` /
`sequencing` / `disruption`), one per `common/strategy/baseline/baseline_<context>.py`. Pure data —
weights only, NO Pilot Mixin (the contrast with a Doctrine). A findability split only: the Pilot
still scores every rule as one flat sum, so cluster boundaries and order are irrelevant at runtime.
_Avoid_: doctrine (reserve that for the archetype+Mixin files), module (too generic)

**Role**:
A deck's purpose-label assigned to one of its cards/lines (`win_condition`,
`primary_attacker`, `accel_source`, `starter`, …) — the per-deck overlay on the universal
Function Tag. Drawn from a closed, shared vocabulary (extended by process) so roles stay
comparable across decks.
_Avoid_: Function Tag (universal/mechanical; a Role is per-deck/intentional), job, slot

**Hypothesis**:
A named, testable claim in a Strategy that biases scoring — carrying a rationale, a
trigger condition, a tunable weight, and a test status (`assumed` → `testing` →
`confirmed` → `refuted`). The unit the Strategy-Category writeup is organised around.
_Avoid_: rule, heuristic (too generic), magic number

**Correction**:
A labelled blunder record — `(state, chosen, correct, attribution, rationale)` — from
marking a decision in any replay featuring this deck (ours or a peer's). The curated unit of
weight tuning; may also create or edit a Hypothesis (its reasoning becomes the `rationale`).
_Avoid_: annotation, fix, label (too generic)

**Tactical Evaluator**:
The shared, Search-backed Score component that ranks combat options (attacker × attack ×
target) by engine-computed outcomes (KO / bench-snipe / prize math), not authored damage
numbers. Hypotheses bias it.
_Avoid_: AttackPlan (the deck-specific instance in `demos/rules-based-lucario.py`), damage table

**Lethal**:
A win available on the CURRENT turn — a reachable sequence of this-turn actions that takes my last
Prize(s) or leaves the opponent with no Pokémon in play, provable **with certainty** from known
information (board + hand + closed-form damage + the sound deck oracle; coins forced to their worst
outcome). *Sound by definition*: a merely-likely win, or one that needs an unknown draw or an
unforced coin, is **not** a Lethal — so the Pilot may safely commit to it. Multi-turn prize-race
planning is a separate problem, out of scope here.
_Avoid_: winning move (too vague — a Lethal is the whole guaranteed win, not one good option), KO
(one knockout; a Lethal may need several enabling steps first), prize race (the deferred multi-turn
tempo problem)

**Lethal Line**:
The specific ORDERED list of this-turn actions that realises a Lethal — the enabling develops
(attach / evolve / retreat / gust / …) ending in the turn-closing attack. The **shortest** confirmed
line is the one taken ("take exactly those decisions"). Once locked it is authoritative: the Pilot
executes its steps and takes nothing outside it that turn.
_Avoid_: Plan (the turn-mode `SETUP`/`RACE`/…; a Lethal Line is a concrete action list), combo,
sequence (too generic)

**Lethal Solver**:
The eager, deck-agnostic Pilot routine that runs at the START of every turn: it works **backward
from prizes** to generate candidate Lethal Lines by closed-form KO math, confirms a candidate by
forward-simulating it through the **Engine Search** (winner `result` == me), and LOCKS the first
confirmed line for execution. Sound by construction — it never locks a false Lethal (misses cost a
turn; a phantom win loses the game). Subsumes the scattered per-action lethal lookaheads.
_Avoid_: Tactical Evaluator (scores *all* combat options; the Lethal Solver only seeks a guaranteed
win), Posture (opponent-driven), bare "search"

**Engine Search**:
The simulator's own forward lookahead, exposed to the agent (`search_begin` / `search_step` /
`search_end` / `search_release`, `cg/api.py`): it forks an INDEPENDENT copy of the position from an
observation's `search_begin_input` — the live game is untouched — and plays hypothetical moves,
returning the exact resulting State, including `result` (the winner). The authority behind Lethal
confirmation; `manual_coin` forces coin outcomes for worst-case (sound) checks. Realises the design's
**Tier-1 Search** seam (Tier-0 = closed-form). It requires *predicted* hidden zones (my deck/prizes,
the opponent's deck/hand/prizes/face-down Active), so its verdict is trusted only for outcomes
**invariant** to those predictions.
_Avoid_: rollout (implies a random playout; this is exact deterministic stepping), Base Value Model
(the learned win-prob estimator — the Engine Search is exact rules, not learned), Scout/Read

**Turn Planner**:
The eager whole-turn optimizer that runs FIRST at the start of my turn — the generalization of the
**Lethal Solver** from the *win* goal to a **Goal Ladder**. It generates a few **Candidate Turn Lines**
by working backward from a closed, prioritized set of **Turn Goals**, simulates each through the
**Engine Search** to its end-of-turn board, ranks them by a leaf evaluation (the Tier-0 board heuristic
now; the Base Value Model later), and commits to the best — planning the whole turn *before* the first
action, then executing it one step per decision. **Heuristic, not sound** (only its top rung, the
Lethal Line, is guaranteed); plans THIS turn only (multi-turn tempo / prize-math is a separate problem).
Realises the designed **Tier-1 Search** (ADR-0008 M3).
_Avoid_: Plan (the coarse turn-MODE `SETUP`/`RACE`/…; the Turn Planner is the concrete action
optimizer, not the mode), Lethal Solver (the win-only special case it subsumes), search (bare)

**Turn Goal**:
One achievable outcome on the current turn, drawn from the CLOSED, PRIORITIZED **Goal Ladder** the Turn
Planner works backward from — win (the Lethal) › KO the opponent's key threat › KO the Active for the
most prizes › stabilise (heal / deny an incoming KO) then attack › develop optimally toward the
win-condition. The ladder *is* the objective; the leaf evaluation breaks ties within a goal.
_Avoid_: Plan (the mode), win-condition (the deck's Line payoff, a Role — not a per-turn goal), Posture
(opponent-driven aggression calibration, not a turn goal)

**Turn Line**:
The ordered sequence of THIS turn's actions that achieves a **Turn Goal** (attach / evolve / retreat /
play / attack, in order) — the generalization of a **Lethal Line** (which is exactly the Turn Line for
the *win* goal). Generated backward from the goal, scored by simulating it through the Engine Search to
end-of-turn, and executed one step per decision as the engine re-opens the menu.
_Avoid_: Lethal Line (the win-goal special case), Plan (the mode), plan / sequence (too generic)

**Incoming**:
The closed-form estimate of the worst damage the opponent can deal to one of my bodies next turn —
from their best **affordable** attacker (one whose attached Energy can pay an attack now, allowing for
one attach), not merely their current Active. The hardest-hitting affordable body is the opponent's
predicted next promotion. A weakness-adjusted board-math estimate, not a guarantee. For a *benched*
body, Incoming counts only true bench-snipe (the body is assumed to stay benched).
_Avoid_: Threat (the objective attacker description from the Read; Incoming is the math *against my
specific body*), active_doomed (a boolean derived from Incoming, not the magnitude)

**Survival Window**:
How many turns one of my bodies withstands the predicted **Incoming** before it is Knocked Out. The
lever a defensive +HP Tool pays for: the Tool earns its slot when its boost widens this window by a
full turn ("survives 2 turns instead of 1"); on a body that dies anyway even with the boost, it buys
nothing. Drives both *whether* to deploy a +HP Tool and *which* body gets it.
_Avoid_: breakpoint (one threshold; the Window is the turn count across repeated hits), heal value
(restoring HP, not extending the count against future Incoming)

**Base Value Model**:
The single deck-agnostic, replay-trained estimator of win probability from a game state;
the project's one learned component, used as Search leaf-evaluation or Score tiebreaker
and gated by the Read's confidence.
_Avoid_: policy (it scores states, not moves), RL agent, neural net, card embedding

### Strategy lifecycle

**Fold**:
Moving a deck Hypothesis into the General Strategy because its trigger vocabulary is (or has
become) universal — Roles / Function Tags / Board signals / params, no card ids — under a
card-name-free id; the deck's declarations remain its opt-in (ADR-0034). Score-equal for the
origin deck by the Score-Diff Gate; a residual band difference becomes an authored weight
override. Covers the retire-into-an-existing-successor case too (a NOTE names the successor).
_Avoid_: promotion / expansion (older phrasings), migration (direction-ambiguous), deletion
(loses the provenance)

**Alignment Pass**:
The recurring reconciliation of one deck's Strategy against the *current* General Strategy and
Pilot systems — Folds, vocabulary/wiring modernization, and Disposition refresh — scoped by the
deck's Alignment Ledger and gated by the Score-Diff Gate (ADR-0036).
_Avoid_: tuning (weight fitting from Corrections, ADR-0018), refactor (a shape-only code change),
sync (too vague)

**Alignment Ledger**:
The per-deck record of the General-Strategy state (commit) the deck was last aligned against —
the diff base that scopes the next Alignment Pass.
_Avoid_: Progress checklist (deck-genie's authoring resumability), changelog

**Disposition**:
The recorded verdict of reconciling one deck card/rule against the General Strategy —
`covers-as-is` / `override-candidate` / `conflicts` / `gap`. Authored by deck-genie, kept current
by Alignment Passes; lives in the deck's STRATEGY.md.
_Avoid_: status (a Hypothesis' test journey), verdict (the blunder Verifier's output)

**Score-Diff Gate**:
The mechanical behavior-neutrality proof for a Strategy/Pilot change: replay a recorded corpus
(Correction `obs`, replay films) through the pre- and post-change Pilot and diff per-frame —
`scores` mode (per-option scores identical; the Fold bar) or `choice` mode (chosen option
identical; the vocabulary-fix bar). Intended divergences are enumerated and justified, and
escalate to match-level A/B.
_Avoid_: divergence replay (unshipped synonym), A/B (match-level winrate evidence — the
complementary gate), regression test (a fixed assert on one state)
