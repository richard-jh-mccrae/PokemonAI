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

### Decision Architecture

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
or disables one of its rules by overriding the weight **by id** (learned from replays/training,
not authored).
_Avoid_: Strategy (the per-deck doctrine), Playbook, Posture (the opponent-driven generic core)

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

**Base Value Model**:
The single deck-agnostic, replay-trained estimator of win probability from a game state;
the project's one learned component, used as Search leaf-evaluation or Score tiebreaker
and gated by the Read's confidence.
_Avoid_: policy (it scores states, not moves), RL agent, neural net, card embedding
