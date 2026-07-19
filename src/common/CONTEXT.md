# Agent Runtime (`common/`)

Deck-agnostic runtime agent code, shared across deck builds. It defines the **Pilot**
decision architecture and the **Automatic Value Model**, and its first capability is
**Scouting** — recognize the opponent's deck from what it reveals and produce the **Read**.

Shared game/meta vocabulary (`Archetype`, `Main-line` / `Sub-line` / `Engine Pokémon`,
`Meta`, `Rank Band`) is defined in the [Meta Tracker](../../CONTEXT.md) context and reused here.

## Language

### Opponent Model

**Opponent Model** (ADR-0047):
The single match-scoped **facade** for all opponent *knowledge*, surfaced as `board.opponent`. A pure
knowledge layer — it answers *what is true / probable about the opponent* and never decides; the
Pilot/Planner consume it. Composes three subsystems: **Identity** (the Read), **Resources**, and
**Dispositions**. One `observe(obs)` fan-out (one write seam), one read surface. Two epistemic tiers,
never one confidence number: *calibrated* (Resources, Read confidence) and *asserted* (Dispositions).
Fails OPEN, never fabricates, never downgrades a certainty into a guess (**sound-or-silent**).
_Avoid_: "the opponent model" for the Read alone; naming any single subsystem "model"; putting Briefs
(a prescriptive *input*) or posture-scoring (a Pilot *decision*) inside it.

**Resources** (ADR-0047):
The Opponent-Model subsystem for the opponent's *remaining outs* — `copies_left(card)`,
`deckout_in_turns`, `hand_size_delta`, `last_turn_dumped`, `took_ko_this_turn`. Match-scoped
(`opponent_resources.py`, like `deck_tracker.py`); the opponent-side mirror of `deck_odds`/`deck_tracker`.
Mostly *probabilistic* (hypergeometric over unseen copies across hidden prizes) with a few *sound* anchors
(visible board/discard, exact `deckCount`).
_Avoid_: `opponent_model.py` (renamed to free the umbrella term); "opponent deck odds" (that's the own-side module).

**Dispositions** (ADR-0047):
The Opponent-Model subsystem of high-bar behavioral booleans about how the opponent plays
(`opp_is_engine_dependent`, `opp_comeback_disruptor`; `scouting/opponent_properties.json`). The *asserted*
epistemic tier — asserted only on strong evidence (a wrong claim is priced ~4%). Briefs are the *input*
that asserts them, not part of the subsystem.
_Avoid_: "opponent properties" as a synonym for the file only; conflating with the prescriptive Brief.

### Scouting

**Read**:
The live, per-turn assessment of the current matchup: the most-likely opponent
Archetype(s) with confidence, predicted development, and the resulting threats and
targets. Pure data — it describes the matchup, it does not act on it. The **Identity** subsystem of the
Opponent Model (ADR-0047) — *who they are*.
_Avoid_: matchup, scout result, prediction, "the opponent model" (that is the umbrella facade)

**Posture**:
How the agent changes play in response to the Read — the Read-conditioned Levers
(matchup favorability, Read-accurate development, Matchup-Brief doctrine), each scaled by
the Read's confidence (γ) so an unrecognized opponent moves nothing. Generic
"seek targets / avoid threats" is deliberately absent (ADR-0026) — card facts already
cover it. A *consumer* of the Read, not part of Scouting itself. **Observable** (ADR-0041):
each decision's Decision Telemetry carries a compact `posture` block (believed archetype,
applied γ, matched Brief) so a blunder is tied to the matchup it happened in.
_Avoid_: stance, strategy, seek/avoid (the retired ADR-0008 framing)

**Lever**:
One Read/Brief-conditioned behavior change, γ-scaled. Realized **sharpen-first**: the
signal feeds the existing decision machinery that already owns the behavior (e.g. the
snipe threat order) rather than a parallel rule; a new Hypothesis is minted only for a
behavior nothing owns yet. Never overrides a KO; kill-switched and A/B-measured before
default-ON.
_Avoid_: rule (a Hypothesis is one *kind* of lever realization), boost (the additive
mechanics inside a rank, not the lever itself)

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

**Stat Provider**:
The ONE card-knowledge seam — the interface every consumer asks for engine-derived card facts:
`get(card_id)` → **CardStat**, `attack(attack_id)` → **AttackStat** (the Attack Effect record), and the
cross-card queries (forward-evolution index, name resolution). Two adapters share the same record
classes: the engine-backed runtime one (eager-builds its tables in the pregame window, audit overrides
included) and the dict-backed test one. Single-card *interpretation* (prize value, is-an-ex-body,
is-Energy/Supporter/Tool, cheapest-attack affordability) lives on the **records themselves**, so a
hand-built record in a test answers exactly like the engine path; the provider answers only lookups and
cross-card questions. Fail-open: unknown id → `None`, and each consumer keeps its own site-specific
default — a my-side affordability read fails *closed* (`or 99`), an opponent-threat read fails
*worst-case* (`or 0`); those defaults are epistemics, not interpretation, and stay at the call site.
_(ADR-0056, built 2026-07-13 — retired the Pilot's seven attack-fact constructor arguments, the
parallel per-mechanic dicts, and the synth fallback.)_
_Avoid_: provider (bare — say Stat Provider), card database, CardStat/AttackStat (the records it hands
out, not the seam), Function Tag / Effect Clause (behavioral JSON tables — separate, offline-built feeds)

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

**KO Oracle**:
The ONE closed-form home for combat judgment — *can X KO Y, what is that KO worth, how fast
does either side fell a body* (`strategy/combat.py`, `CombatMath`, ADR-0052). Owns the damage
core (composing the pure `damage.py` seam), reachability (cheapest / affordable / maxed /
can-damage), the shared KO-valuation band every hypothetical attacker is priced on
(retreat/gust/promote/attach/boost lookaheads), bench-rider prize math, typed affordability,
the worst-case Incoming family, and `turns_to_ko`. Built from the knowledge seams (the Stat
Provider, Function Tags, the transient tracker) with per-decision facts as call arguments —
no Pilot, no Board, standalone-testable. The Pilot delegates through thin wrappers; the
card-level KO fallback (`minCostDamage` × attack-blind W/R) is retired — no record, no claim.
_Avoid_: Tactical Evaluator (the Score component that RANKS options — it consumes this),
Lethal Solver (the sound win rung — a consumer), damage oracle (the `damage.py` per-attack
seam this composes), combat module (bare)

**Card-Worth Oracle** (ADR-0065):
The ONE closed-form home for card keep/shed valuation — every equation is `value = Worth × Odds`.
Four modules, four glossary terms ([0065-glossary](../../docs/adr/0065-glossary.md), the authority):
**Worth** ([card_worth.py](card_worth.py) — the one tuned role/tag tier currency; no opinion about
probability), **Odds** ([deck_odds.py](deck_odds.py) — pure deck math: the draw-window
hypergeometrics plus the Deck-Content Odds estimate above; no opinion about value), **Gates**
([gate_library.py](gate_library.py) — WHEN a card's Worth is live: the `deploy_odds` deadline
factor, the closing-edge spike, the quota window; all four legs built — evolution, fetcher,
pressure, quota), **Closure** ([fetch_closure.py](fetch_closure.py) — WHAT can
reach what: the tutor/search graph over the card representation, never a text parse). Pure modules,
no Pilot imports; the Pilot resolves board facts and delegates (`_role_value` / `_keep_cost` /
`_deploy_odds` / `_card_reaccess_outs`). `keep_cost = Worth × Gates × (1 − re-access Odds over the
Closure)` — consumed by the gamble keep-floor and the refresh SHED; the doctrines stay the deciders.
_Avoid_: value bare (ambiguous — Worth, the Worth×Odds product, or the Tier-0 tactical score; see
the glossary), "the reachability module" (say Closure), gate for a rung-level deadline predicate
(the glossary reserves Gates for `deploy_odds`-style factors inside Worth)

**Pilot**:
A deck's complete in-match decision engine — the shared `common/` component behind every
choice. A deck customises it only by supplying a Strategy.
_Avoid_: agent (the Kaggle entry function), brain, AI

**Deployment Profile**:
The one table of shipped kill-switch values — `common/runtime.py` `PROFILE` (ADR-0055): ON
entries are A/B-cleared or user-decided; armed-off entries stay dark until their evidence
gate clears. The Pilot ctor stays the *raw-scoring* layer (features off — the neutral
substrate tests and probes construct); `make_agent(STRATEGY)` is the whole per-agent shell
(each `main.py` is ~5 lines) and resolves every flag as `params.get(flag, PROFILE[flag])`,
so a deck's own params and the `AGENT_OVERLAY` A/B lever keep forcing any switch.
tune/retest/score_diff build through the same profile — a retest decides with the live
agent's backstops, structurally.
_Avoid_: kill-switch smear (the retired per-main.py literals), defaults (ambiguous — say
ctor default vs shipped value)

**Plan**:
The Pilot's current-turn strategic mode — one of a closed set (`SETUP`, `RACE`,
`STABILIZE`, `CLOSE`) — DERIVED each turn as a pure function of the Match Objectives (readiness,
KO Race, both Prize Paths), memoryless (transitions run backwards as freely as forwards) with a
hysteretic label (anti-oscillation). **Advisory by contract**: a legibility label plus small
confidence-scaled weight bands — never an eligibility gate (no rule keys `plan == X`); a wrong
phase read biases a few points for a turn, it cannot silence a rule family. Ablation must land
within noise. _(Accepted design 2026-07-06: the closed set grows to six — +`STALL` (build while
declining giant-waking KOs) / +`SACRIFICE` (trade the Active, race on prize math) — as the tempo/
defensive **mode** axis of the Match Planner's **Game Plan**, which DIRECTS the Turn Goal. The
advisory/gate-ban contract STANDS — the mode still never gates a rule; it steers only via the
directed Turn Goal seam.)_
_Avoid_: Strategy, Posture, AttackPlan (that's the Score-layer attack choice), phase gate (banned
— the label never gates rule eligibility), state machine (it is derived, not authored/transitioned)

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
Carries `posture_mismatch` (ADR-0041): the human's verdict that the agent's opponent Read was
wrong here — a matchup-doctrine miss routed to the believed archetype's Brief, not a weight.
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
(attach / evolve / retreat / gust / …) ending in the turn-closing attack; exactly the **Turn Line**
of the *win* goal. The **shortest** confirmed line is the one taken ("take exactly those
decisions"). Once locked it is authoritative: an engine-verified lock **materialises** the
confirmed step sequence and replays it for the rest of the turn (each pick identity-matched to the
live select; outcome-invariant picks stay policy-driven), falling back to per-decision
re-derivation on any divergence — never a blind index, never anything outside the line.
_Avoid_: Plan (the turn-mode `SETUP`/`RACE`/…; a Lethal Line is a concrete action list), combo,
sequence (too generic)

**Lethal Solver**:
The **Turn Planner's sound top rung** — the *win* Turn Goal, not a standalone routine. One
generator family proposes candidate Lethal Lines (a direct KO, or enabling develops — attach /
retreat / evolve / energy-tutor / gust — ending in the winning attack), each proved closed-form at
worst case (damage floors, coins forced worst) and confirmed by driving it through the **Engine
Search** to the engine's own verdict: a refute drops the candidate; an unreachable verdict (an
unforced coin, engine absent) keeps the sound closed-form lock. It preempts every heuristic Turn
Goal — no positional value can outrank it. Sound by construction — it never locks a false Lethal
(misses cost a turn; a phantom win loses the game).
_Avoid_: Tactical Evaluator (scores *all* combat options; the Lethal Solver only seeks a guaranteed
win), Posture (opponent-driven), bare "search", standalone solver (it is a rung of the Turn Planner)

**Engine Search**:
The simulator's own forward lookahead, exposed to the agent (`search_begin` / `search_step` /
`search_end` / `search_release`, `cg/api.py`): it forks an INDEPENDENT copy of the position from an
observation's `search_begin_input` — the live game is untouched — and plays hypothetical moves,
returning the exact resulting State, including `result` (the winner). The authority behind Lethal
confirmation; `manual_coin` forces coin outcomes for worst-case (sound) checks. Realises the design's
**Tier-1 Search** seam (Tier-0 = closed-form). It requires *predicted* hidden zones (my deck/prizes,
the opponent's deck/hand/prizes/face-down Active), so its verdict is trusted only for outcomes
**invariant** to those predictions.
_Avoid_: rollout (implies a random playout; this is exact deterministic stepping), Automatic Value Model
(the learned win-prob estimator — the Engine Search is exact rules, not learned), Scout/Read

**Match Planner**:
The Pilot's match-scale planner and the top of the decision hierarchy — it runs first each turn, above
the **Turn Planner**. It ranks candidate routes to victory over the whole board and both prize counts
(which Knock-Outs bank my six prizes, a board-out, stall-to-set-up-then-sprint, stabilize-to-survive),
scores each route's feasibility as a **confidence**, and commits a **Game Plan** that directs this
turn's **Turn Goal** (and projects the next one or two). **Grown from the Tier-3 Match Objectives** —
the two-sided **Prize Path**, the **KO Race**, and the forward **Threat Clock** are its primitives, not
separate layers. Re-derived every turn (memoryless; it adapts as the opponent counters). It DIRECTS the
Turn Planner's goal but never gates a rule (ADR-0040's gate-ban stands) and never LOCKS — low confidence
defers to the Turn Planner's own goal and the tuned scoring. Parallel to the Turn Planner one scope up
(`plan_match` : match :: `plan_turn` : turn). _(Accepted design 2026-07-06, `/grill-with-docs`; build in
progress.)_
_Avoid_: Turn Planner (one scope down — the this-turn action optimizer that executes the goal), Plan
(the coarse turn-MODE label the Game Plan derives), Strategy (the deck's static declared doctrine),
Posture (the opponent-Read levers), Escalation Search (the opponent-choice engine tree — the Match
Planner is opponent-static closed-form).

**Game Plan**:
The Match Planner's output — the chosen route to victory (or a ranked few) with a **confidence**, and
the **directed Turn Goal** it hands the Turn Planner for the current turn. A ranking/steering object
re-derived each turn, never a lock (the phantom-lethal-at-match-scale mistake): when confidence is low
the Pilot falls back to the Turn Planner's own goal and the tuned weights. The concrete, confidence-
scored match intent that today's advisory **Plan** label only gestured at.
_Avoid_: Plan (the coarse SETUP/RACE/STABILIZE/CLOSE label — a Game Plan is the full routed strategy +
confidence a Plan is *derived from*), Prize Path (one primitive it consumes), Turn Line (the concrete
action sequence the Turn Planner builds to execute the goal), lock/commitment (a Game Plan never locks).

**Turn Planner**:
The eager whole-turn optimizer and the Pilot's ONE planning entry point, running FIRST at the start
of my turn. It **contains the Lethal Solver as its sound top rung**: the win goal is generated,
verified, and locked before — and immune to — every heuristic goal below it. Below the win rung it
generates a few **Candidate Turn Lines** by working backward from a closed, prioritized set of
**Turn Goals**, simulates each through the **Engine Search** to its end-of-turn board, ranks them by
a leaf evaluation (the Tier-0 board heuristic now; the Automatic Value Model later), and commits to the
best — planning the whole turn *before* the first action, then executing it one step per decision.
**Heuristic below the top rung** (only the win rung's Lethal Line is guaranteed); plans THIS turn
only (multi-turn tempo / prize-math is a separate problem). Realises the designed **Tier-1 Search**
(ADR-0008 M3).
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

**Chance Node**:
The single point in a candidate Turn Line where the action's outcome is stochastic at plan time — a
Hand Refresh's draw, a fetch against uncertain deck contents, a coin-flip attack. Own-side only (the
opponent's hidden zones are Posture/Read territory, not a Chance Node).
_Avoid_: randomness/RNG (vague), determinization (a sampled resolution — the rejected Monte-Carlo
mechanism), hidden information (the opponent's zones — explicitly out of scope)

**Outcome Class**:
The macro-partition of a Chance Node's outcomes that share one best follow-up ("≥1 {W} Basic Energy
among the 6 drawn" vs "none") — never raw card permutations. Weighted exactly: own-deck composition
is known (decklist − seen), with prize uncertainty split hypergeometrically (Deck-Content Odds).
_Avoid_: outcome/branch (unqualified), sample (implies Monte-Carlo)

**Gamble Line**:
A Turn Line containing exactly ONE Chance Node, valued by the exact-probability EV over its Outcome
Classes — each branch's best follow-up valued closed-form — and competing on the Goal Ladder against
deterministic lines by that EV. Deliberately probabilistic: it can NEVER outrank the sound win rung
(a Lethal preempts every gamble), and its EV never feeds the sound Lethal/Incoming math (which stay
worst-case). Depth-1 by definition; a line needing two gambles is not generated.
_Avoid_: Lethal Line (sound, worst-case — the opposite epistemic), expected value / EV (bare — say
whose: the sound math forbids it, a Gamble Line is built on it), risky line (unquantified)

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

**Threat Clock**:
The **Match Planner**'s defensive primitive — a closed-form, opponent-static projection of *when* each
opponent body could Knock Out one of my bodies. For every opponent attacker (a visible current form, a
form its line forward-evolves INTO, or a Read-predicted not-yet-benched attacker) it computes the
earliest future turn it can afford a KO of a given body of mine: Energy modeled at the ~1-attach/turn
rule floor plus known acceleration (`energy_accel`), evolution at one turn per hop, gated by the form's
real attack cost and its Weakness/Resistance-adjusted damage, accumulating over turns when one hit
doesn't KO (the **Survival Window** generalized). A benched attacker carries a promotion surcharge
(bringing it Active), reduced when the opponent holds a promotion enabler (a `switch`/`gust` card, or a
cheap/free retreat vs a stuck Active) and waived for a true bench-snipe. The Read γ-sharpens the attach
rate and which line the opponent actually runs; with no Read it is pure card fact (the base fallback).
Feeds the Match Planner's confidence (defensive survival) and the proactive prep it directs (pre-snipe /
pre-gust / heal-a-turn-early). Same worst-case-but-accurate epistemic as Incoming/Survival Window/KO
Race — never a claim about opponent CHOICE (that stays the parked Escalation Search). Its Energy model
is ~1 attach/turn (Read-γ-sharpenable for a burst-Energy archetype), so it does NOT feed the
survival-critical one-turn `active_doomed` boolean, which stays **worst-case** — a hidden Ignition-class
burst must never be under-counted (the planner_6858 finding: a mirror opponent at 1 Energy still bursts
to its nuke next turn). A survival read must never under-prepare; a prep read off by a turn is
recoverable. _(Built 2026-07-07, `/tdd`; complements — does not replace — the worst-case reads.)_
_Avoid_: Incoming (the single-turn magnitude against one body — the Threat Clock is the multi-turn
energy/evolution-aware turns-to-KO that subsumes it), Survival Window (the single-body case this
generalizes across bodies, forward forms, and the energy timeline), Escalation Search (opponent-choice
engine tree — the Threat Clock is opponent-static closed-form), Evolving Threat (the offensive snipe
signal — the Threat Clock is the defensive projection that consumes the same forward-evo index).

**KO Race**:
The closed-form turns-to-KO computation, both directions: the fewest of MY turns to fell a standing
target under my best attack SEQUENCE (damage accumulation across turns, snipe riders credited to
Prize-Path targets), and the fewest of THEIR turns to fell each of my bodies (Survival Window
generalized board-wide). Opponent-static per computation, re-derived every turn. Feeds
attack-sequence choice (the a21472 class), Prize-Path feasibility weights, and race posture
(ahead/behind in turns). Exact arithmetic under the standing-board assumption — never a claim about
opponent choice; boards where opponent CHOICE dominates are the (deferred) engine-tree escalation.
_Avoid_: Survival Window (the single-body defensive case this generalizes), lookahead/tree search
(the engine-simmed branching this deliberately is not), tempo (vague — say turns-ahead/behind)

**Prize Path**:
One concrete route to a side's remaining prizes: an assignment of KOs over the other side's
KO-able bodies whose prize values ({1,2,3} — regular/ex/Mega-ex) sum to the prizes that side still
needs. Computed BOTH directions every turn — my cheapest feasible acquisition path over their board,
and their cheapest path over mine — feasibility-weighted (damage math, replacement, tempo),
re-derived fresh each turn with mild stickiness. A ranking OBJECTIVE that conditions decisions
(KO-target choice, promote, bench discipline); never a lock (the phantom-lethal mistake at match
scale). Small by construction: ≤6 bodies a side, subset-sums over {1,2,3}.
_Avoid_: prize race (the whole dynamic; a Path is one route through it), win condition (a deck
Role), Lethal (sound, this-turn — a Path is fuzzy and multi-turn), plan/lock (it never commits)

**Path Denial**:
Shaping my board so the opponent's cheapest Prize Path lengthens — bench discipline (never gift the
body that completes their ≤6-prize route), promote order (interpose generalized), KO-priority on
their path-critical attackers. The defensive half of the two-sided Prize-Path objective: "make them
take 7 prizes, not 6."
_Avoid_: stalling (a play-role), walling (one tactic; Denial is the objective it serves)

**Prize-Redundant Target**:
An opponent body whose Knock-Out would NOT advance my remaining prize count — its prize value
overshoots what my cheapest **Prize Path** already secures (the *second* Mega ex when one Mega + a
small already reaches my count). Chip or snipe spent on it is wasted: I take my prizes elsewhere and
gust *around* it. The OFFENSIVE twin of **Path Denial** — Denial lengthens *their* path, this refuses
to shorten a target off *mine* — realized (ADR-0044) as a suppression of the snipe threat-rank boost
on an off-Path, prize-redundant, non-imminent body (γ / `objectives_path`-gated).
_Avoid_: off-path (bare — a low-prize off-path body can still be the right `+1`; the point is prize-
*redundant*), Path Denial (the defensive their-side twin), Threat (magnitude, prize-blind)

**Prize-Economy Fetch**:
The FETCH-seam realization of **Path Denial** (ADR-0048): once my multi-prize win-condition is in
play, a grab prefers developing a cheap (1-prize-forward) **attacker** line over a redundant
high-prize line, so the opponent must Knock Out MORE, SMALLER bodies to reach six ("force eight
prizes of work for a six-prize game"). Scored by the grab's **forward-payoff prize value** (the
prize value of what the pre-evolution evolves INTO — Riolu→Mega = 3, Makuhita→Hariyama = 1 — not the
card's own), gated on `wincon_in_play`, **attacker-lines only**, a small **positive** tie-break
dominated by every real need and deck-overridable (`fetch_priority` / `weight_overrides`). The
FETCH-seam sibling of the promote-seam Interpose trio and the bench-seam `_bench_shortens_their_path`.
_Avoid_: Prize-Redundant Target (the OFFENSIVE snipe twin — this is the fetch/development side), Path
Denial (the umbrella objective; this is one seam of it), `card_prize_value` (the grabbed card's own
prizes — this term reads the forward *payoff's* prizes)

**Secondary Line**:
A declared **non-win-condition** evolution `Line` (a `Line` whose `role` is not a win-condition role,
e.g. `secondary_attacker` — Makuhita → Hariyama) — a deck's cheap-attacker line recognized as
first-class so its pre-evolutions earn line-piece development credit, **without** its payoff being
mislabeled a win-condition. Its pre-evos join the **recognized-line** set (`card_is_recognized_line_preevo`,
which the preference rungs and **Prize-Economy Fetch** read) but NOT the narrow **win-condition
pre-evo** set (`_line_preevo_set`, which feeds `wincon_base_deployable` and the deploy/hold machinery —
kept separate on purpose, ADR-0048). Distinguished from the win-condition Line by the role-gated
`_wincon_set()`.
_Avoid_: win-condition Line (the primary payoff line), Sub-line Pokémon (the Meta-Tracker
deck-composition term — a Secondary Line is a runtime Strategy structure), Role (a per-card label; a
Secondary Line is a whole path)

**Forced-Promotion Read**:
The 1-ply prediction of WHICH benched body the opponent brings to the Active Spot when a promotion is
**forced** — their Active is doomed (I KO it this turn, or it is already at 0 HP). Corrects
**Incoming**'s affordability guess ("the hardest-hitting *affordable* body is the predicted next
promotion"): under a forced promote the opponent brings up their highest-VALUE ready body — the
win-condition by eventual attack power, **energy-independent** (they have acceleration to power it) —
not the energized bench-sitter that merely happens to be affordable now. Scoped (ADR-0044) to the
OFFENSIVE pre-chip: it redirects the snipe target, a soft non-committal chip, and does NOT relax
Incoming's worst-case *defensive* read. γ-sharpenable via the Read.
_Avoid_: Incoming (the defensive worst-case; this is the offensive promote-target guess), interpose
promote (that is MY promote choice — this predicts THEIRS), Threat (the objective Read description)

**Automatic Value Model**:
The single deck-agnostic, replay-trained estimator of win probability from a game state; the
project's one learned component (ADR-0007/0042). Realized as a **dependency-free logistic** whose
FEATURES are the Tier-3/Tier-4 objective primitives (race delta, both Prize-Path turns, favorability,
development, prize/hand/energy counts) — the symbolic tiers do the credit assignment, so the learned
layer is a thin, legible linear model, not a raw-board encoder. Trained offline in pure Python
(`tools/train/value/`) on mined replay states (label = eventual winner), shipped as a JSON artifact
a pure-stdlib runtime evaluates (`common/value/`). **Absent-safe** (no artifact → null model, P=0.5,
zero influence) and **refines judgment only** — a capped sub-prize planner-leaf term + `win_prob`
telemetry, NEVER overriding a sound rung.
_Avoid_: policy (it scores states, not moves), RL agent, neural net, card embedding, LightGBM/GBDT
(the inference model is a stdlib logistic — a tree ensemble stays a rejected/deferred alternative)

**Escalation Search**:
The Tier-6 budgeted engine tree (ADR-0043) for the opponent-CHOICE residue the opponent-static
closed-form tiers can't see. Triggered ONLY on a close attack tie (top ATTACK options within an ε),
it sims each tied attack two-ply — my turn AND the opponent's reply (our own policy as the proxy) —
via the Engine Search, ranks by the leaf (Automatic Value Model when present, else closed-form), and
commits only a strict improvement over the tuned tie-pick. Hard per-move step budget; the tuned pick
is the guaranteed fallback (budget spent / engine absent → defer). Default OFF (a search seam ships
only after its budgeted ladder A/B).
_Avoid_: Engine Search (the primitive it drives — Escalation Search is the budgeted policy over it),
Lethal Solver (sound, this-turn win; escalation is heuristic tie-breaking), Turn Planner (the whole
optimizer; escalation is its last, opt-in rung)

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
