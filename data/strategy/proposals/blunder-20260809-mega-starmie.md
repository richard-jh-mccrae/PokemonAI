<!-- Strategy Proposal queue — blunder-buster round 2026-08-09.
Source: data/corrections/mega_starmie_20260809_da61a511-dirty/corrections.jsonl.
Terminal outcomes: 8 proposal-routed; 91394270-t10s0 refuted by the user's explicit disposition.
Every listed route was re-measured through the shipped Pilot; see the referenced state fixtures. -->

## Let the Composer sequence before a hand-refresh gamble
- id: starmie-composer-before-hand-refresh-gamble
- source: blunder-buster
- target_layer: turn-sequencer
- candidate_signal: existing Composer action tiers and hand-shuffle tag; no new board signal.
- verification_contract: composer-retest
- provenance: data/corrections/mega_starmie_20260809_da61a511-dirty/corrections.jsonl (91393233:t2s0, CRITICAL) | fixture tests/fixtures/corrections/ms_gamble_requires_all_win_line_pieces_f9.json
- status: applied
- for: deck:mega_starmie

**Spec (authoring spec — thin fodder):**
The Planner commits Lillie's Determination as a 71% Mega-Starmie gamble before the Composer sees the menu.
That deletes the held Energy and hides the available Pokégear reveal. A gamble for a single missing Energy or
evolution is legitimate; it must merely defer when the Composer has an available pre-shuffle action. In this
state it must take Pokégear, select any revealed Hilda to fetch both Starmie and Energy, then attach before a
hand refresh remains eligible. Keep the gamble's existing odds calculation unchanged.

## Compose informative Items before irreversible commitments
- id: starmie-compose-information-before-commitment
- source: blunder-buster
- target_layer: composer-differencer
- candidate_signal: existing Item/Supporter classification plus the Pokégear reveal transition; no new game-state signal.
- verification_contract: composer-retest
- provenance: data/corrections/mega_starmie_20260809_da61a511-dirty/corrections.jsonl (91393371:f9, CRITICAL; 91393371:t6s1; 91394270:f9, CRITICAL; 91394270:f12, CRITICAL) | fixtures tests/fixtures/corrections/ms_information_before_commitment_91393371_f9.json + ms_information_before_commitment_91393371_t6.json + ms_information_before_commitment_91394270_f9.json + ms_information_before_commitment_91394270_f12.json
- status: applied
- for: deck:mega_starmie

**Spec (authoring spec — thin fodder):**
Pokégear is a free information action: it can reveal the Supporter that decides the rest of the turn. The Composer
instead commits Salvatore in both turn-2 states and commits a retreat before Pokégear in the turn-6 state. Model
the reveal before a Supporter, retreat, or Energy commitment when the Item remains legal, so the continuation can
choose Hilda/Salvatore/Wally's from the revealed menu rather than pre-spending the relevant resource.

## Let a guaranteed wincon KO preempt composition
- id: starmie-lethal-prioritizes-wincon-or-prize-ko
- source: blunder-buster
- target_layer: lethal-solver
- candidate_signal: existing deterministic KO, prize, and opponent main-attacker/wincon Role facts; no new signal.
- verification_contract: composer-retest
- provenance: data/corrections/mega_starmie_20260809_da61a511-dirty/corrections.jsonl (91393371:f38, CRITICAL) | fixture tests/fixtures/corrections/ms_lethal_preempts_weaker_attack_f38.json
- status: applied
- for: deck:mega_starmie

**Spec (authoring spec — thin fodder):**
When two offered attacks are deterministic Knock Outs, rank a KO of the opponent's wincon/main-attacker Role
first; otherwise rank strictly by prize/terminal value. At this frame the choice was a KO of a two-prize
supporter versus a KO of a one-prize supporter. The current trace gives the former a higher tactical value but
the Composer commits the latter. Surface and lock this terminal ordering before composition can choose it.

## Do not attach Energy that Wally's Compassion immediately returns
- id: starmie-compose-wally-before-energy-bounce
- source: blunder-buster
- target_layer: composer-differencer
- candidate_signal: existing Wally's heal/bounce transition and attached-Energy state; no new signal.
- verification_contract: composer-retest
- provenance: data/corrections/mega_starmie_20260809_da61a511-dirty/corrections.jsonl (91393371:f69, CRITICAL) | fixture tests/fixtures/corrections/ms_wally_before_energy_bounce_f69.json
- status: applied
- for: deck:mega_starmie

**Spec (authoring spec — thin fodder):**
At turn 6, the damaged benched Mega Starmie has one Energy. Attaching a Basic Water and then choosing Wally's
Compassion wastes that attachment because Wally's heals the target and returns its attached Energy to hand.
The composed ordering must see that dependency and place Wally's before any attachment whose only recipient is
the heal target.

## Promote the recoverable attacker over the one-hit liability
- id: starmie-promote-recoverable-attacker-over-fragile-base
- source: blunder-buster
- target_layer: value-equation
- candidate_signal: existing promotion equation's reach, exposure, and retreat-cost terms; inspect why its Cinderace and 10-HP Staryu choices tie.
- verification_contract: composer-retest
- provenance: data/corrections/mega_starmie_20260809_da61a511-dirty/corrections.jsonl (91394270:t11s0) | fixture tests/fixtures/corrections/ms_promote_recoverable_attacker_f102.json
- status: applied
- for: deck:mega_starmie

**Spec (authoring spec — thin fodder):**
Promotion is a cost-benefit decision. With no attached Energy and none in hand, the three bodies have no immediate
attack benefit, so rank their current effective retreat costs: Cinderace (0) over Staryu (1) over Mega Starmie ex
(2). Make this a small mobility tie-break, not a replacement for reach, HP, or prize exposure. If an Energy is in
hand, leave the existing Mega-Starmie evaluation available; its HP and immediate payoff may then justify promotion.
