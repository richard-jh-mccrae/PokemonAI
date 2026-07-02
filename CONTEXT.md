# Pokémon TCG Meta Analysis

Glossary for the daily pipeline that pulls match replays from the official daily top-episode export and reports the deck **Meta** the agent will face. Game-rule terms (energy, evolution, prize) follow standard Pokémon TCG usage and the enums in `src/cg/api.py`; only project-specific terms are defined here.

## Language

**Simulation Competition**:
The Kaggle competition `pokemon-tcg-ai-battle`, where agents play ranked matches. The source of all match data.
_Avoid_: "the comp", "Kaggle" (ambiguous)

**Strategy Competition**:
The sibling competition `pokemon-tcg-ai-battle-challenge-strategy` (share-your-approach writeup). Not a data source; shares the leaderboard/rating with the Simulation Competition.

**Episode**:
One recorded ranked match between two teams, identified by an episode ID.
_Avoid_: game, match (reserve "Episode" for the recorded artifact)

**Replay**:
The downloadable full-information record of an Episode — both teams' complete 60-card Decks, every action across all frames, and the winner. Distinct from the agent's in-game Observation, which hides the opponent.
_Avoid_: log ("logs" is the per-action event list *inside* a replay)

**Deck**:
A legal 60-card list (by card ID) a team submits. Obtained from a Replay's full-information frame, never from the agent Observation.

**Meta**:
The distribution of Decks currently in active play — what the agent expects to be matched against. Rank-dependent, because matchmaking pairs teams of similar rating. Reported per Rank Band.
_Avoid_: metagame

**Rank Band**:
A **contiguous percentile tier over the top 50%** of the ladder (Elite ~2%, High ~10%, Mid ~50%), assigned to an Episode by its participants' current rating (leaderboard name→score join). The bottom of the ladder is intentionally dropped — the data source is the top-rated daily export, so we keep only refined decks. The Meta is reported per band so skill-level shifts are visible.
_Avoid_: tier, bracket, stratum, Low band (dropped)

**Skill Rating**:
A per-Submission rating (Gaussian N(μ,σ²), μ₀=600; matchmaking pairs similar μ). Only the leaderboard `publicScore` (≈μ) is used here — to map an Episode's participants to a Rank Band. σ is not exposed.
_Avoid_: ELO, score (use "Skill Rating"; "score" = the displayed publicScore value)

**Main-line Pokémon**:
A Deck's primary win-condition evolution line(s) — **up to three**, ranked by investment (copies of the top stage, then stage height, then ex/Mega-ex, then printed damage). They define an Archetype's name. A Main line need not deal printed damage — some win-conditions attack via an ability/effect (e.g. Alakazam). Engine Pokémon are excluded. Top priority: make the Main-line Pokémon in active play immediately visible.
_Avoid_: key Pokémon, primary attacker

**Engine Pokémon**:
A consistency/disruption/tech Pokémon played across many Archetypes (e.g. Dudunsparce, Budew, Munkidori) that is **never** treated as a Main line — it would drown out real win-conditions. Curated in `config.ENGINE_POKEMON`; still counted in Sub-line/usage stats.
_Avoid_: support Pokémon (too broad)

**Sub-line Pokémon**:
Any Pokémon in the Deck beyond its Main Lines — secondary attackers, Engine Pokémon, and tech one-ofs that support the Main Lines.
_Avoid_: tech, splash (these are *kinds* of Sub-line, not the category)

**Archetype**:
A group of Decks sharing the same Main Lines, named after them (e.g. "Cinderace / Mega Starmie ex"). The unit by which the Meta is counted and named.
_Avoid_: deck type, build

**Variant Cluster**:
A set of subset-related Archetypes that share their primary Main line, folded into one unit labelled by its most common member (e.g. the ±Cramorant Hop's Trevenant builds collapse to one). The unit the deck export and a Matchup Brief address — the export's `covers` list is exactly the cluster's member Archetype strings. Non-destructive: the store keeps the precise Archetype labels (`dashboard._merge_map`).
_Avoid_: variant, merge group

**Representative Build**:
The single most-common *exact* 60-card Deck actually observed for an Archetype or Variant Cluster (recency-weighted, all Bands pooled) — a real legal list, never a per-slot reconstruction. What the deck export ships per cluster.
_Avoid_: modal deck, average list

**Play rate**:
The share of Episodes in a Rank Band in which a Main-line Pokémon or Archetype appears. Encounter-weighted (counted per Episode, not per team) — because matchmaking pairs similar ratings and active agents play more, so they are genuinely faced more often.
_Avoid_: usage rate, pick rate

**Win rate**:
Among the Episodes where a Pokémon/Archetype appeared, the share it won (from the Replay result/`rewards`).

**Matchup**:
The **Win rate** of one Archetype *against a specific opponent Archetype* — an ordered
pair (A-beats-B ≠ B-beats-A), recency-weighted and shrunk toward A's overall Win rate
then 0.5 so thin records stay neutral. Compiled into the Scouting artifact
(`dossier.matchups`) and consumed as *favorability* (how favored the agent is vs the
predicted opponent). An **offline statistic** — distinct from the Agent Runtime **Read**,
which is the live per-turn assessment (the Read glossary deprecates "matchup" for *that*
live sense).
_Avoid_: "the Read" (that's live/per-turn); counter (a card-level tech, not a rate)

**Top Deck**:
A Deck with a high **Win rate** within the kept (refined) Bands — genuinely strong. Refinement is ensured by the top-rated source + band filter rather than a per-Submission confidence proxy.
_Avoid_: best deck, meta deck

**Common Deck**:
A Deck with high **Play rate** (per-Episode encounter rate) in a Band, regardless of Win rate. What you are most often matched against; distinct from a Top Deck.
