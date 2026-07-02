# ADR-0028: +HP Tool deploy is survival-turns board-math — proactive default, not hold-for-breakpoint

**Status.** Accepted (grilled 2026-06-30, `/grill-with-docs`) and **BUILT** test-first (`/tdd`,
2026-06-30/07-01; `tests/strategy/test_tool_doctrine.py`, full suite 694 passed). **Reverses** the reactive
"hold for an HP breakpoint" Hero's Cape doctrine (STRATEGY.md §3 + the `baseline_tool.py` rules
landed 2026-06-28) and **promotes** the Tool Baseline Cluster into a **Tool Doctrine**
(`common/strategy/doctrines/doctrine_tool.py` + a `ToolMixin`). All decisions below shipped, incl. the
predict-next-attacker generalization (decision 4, isolated to the `ToolMixin`), the wall rung and the
doomed→successor redirect (decision 5), and the KO-invariant (decision 5, characterization-tested).
Still-deferred seams are listed in Consequences. Sibling to the **Gust** ([ADR-0022](0022-gust-is-closed-form-lethal-lookahead.md)),
**Fetch** ([ADR-0023](0023-fetch-is-a-shared-value-comparator.md)) and **Shuffle-Refresh**
([ADR-0024](0024-shuffle-refresh-is-fetch-decision-a-over-keep-value.md)) doctrines.

**Context.** **Hero's Cape** (1159) is a **Pokémon Tool, ACE SPEC, +100 HP** to the holder — the deck's
only ACE SPEC, a hard one-of, **unrecoverable** once lost (Night Stretcher returns a Pokémon or Basic
Energy, not a Tool; no second copy is legal), and it **transfers on evolution** (rulebook.txt:125 — a
Cape on Staryu rides up to Mega Starmie ex). All verified at source, not recalled.

The shipped doctrine was **reactive**: `deploy-hp-tool-on-breakpoint` (+50) fired ONLY when the Active
wincon was `active_doomed` AND +100 dodged the incoming OHKO; otherwise `save-tool-for-the-attacker`
(−15) + `protect-ace-spec-tool` (−10) held it. A prior correction asking to deploy it was **refuted**
(reviewed.json `82756664-9`: *"deliberately hold the one-per-deck ACE SPEC… Turn-1 Cape deploy is a
fine tool-timing judgment"*). That whole doctrine rests on **"holding = safe."**

**That premise is false for this deck.** It runs **six** hand-shuffle Supporters (4× Lillie's
Determination + 2× Harlequin; `shuffle_hand`), so the most likely fate of a held Cape is the agent
**shuffling its own irreplaceable ACE SPEC back into the deck**. Observed live (episode 82866415,
frames 43 + 48; user corrections, one rationale *"Attach the fucking cape before shuffling!!"*). Root
cause, from the live trace: the negative "protect" weights drag the Cape-attach to **score ≤ 0**, and
`_finish_turn_last` (pilot.py:439) drops any ≤0 option to **tier 4** — *below* the tier-3 Shuffle-Refresh
— so Lillie's (+20 `dig-before-commit`, tier 3) fires first and shuffles the Cape away. **The protection
weights are the bug.** A tool-attach scoring **> 0** would be **tier 2**, *above* the shuffle (pilot.py:445).

**Tool removal is real but matchup-dependent.** Tool Scrapper, Megaton Blower (ACE SPEC), Jellicent ex,
and ~8 attacks that "discard all Tools from your opponent's Active" exist in the format
(`data/EN_Card_Data.csv`). So early deploy is not risk-free — but the self-shuffle loss is far more
frequent and self-inflicted, and seeing the opponent's removal needs the Read (Posture). Net: deploy.

**Decision.**

1. **Reverse the doctrine — proactive default deploy, not hold-for-breakpoint.** Because holding is the
   *least* safe option in this deck, the Cape goes down on the body that carries the game by default; the
   breakpoint is one of several triggers, no longer the only one.

2. **Promote to a Tool Doctrine.** The model carries closed-form board-math that cannot be a tunable
   weight (the Doctrine-defining trait, per [src/common/CONTEXT.md](../../src/common/CONTEXT.md)), so
   `baseline_tool.py` becomes `doctrines/doctrine_tool.py` + a `ToolMixin`.

3. **Survival-turns is the value model.** For one of my bodies, `survival_turns = ceil(remaining_hp /
   incoming_per_turn)`; a +HP Tool earns its slot when +`hpBonus` raises that by **≥ 1** ("survives 2
   turns instead of 1"). **Two distinct deploy drivers**, both retained: an **anti-shuffle floor** (the
   high-frequency driver — never sit on the Cape into a hand-shuffle) and **at-risk value** (the
   refinement that triggers a proactive deploy when a body genuinely gains a turn, and chooses *which*
   body when there is a real threat). On a healthy Active the survival-test does not fire — there the
   anti-shuffle floor is the driver and the Active wincon is the default target.

4. **Predict the opponent's next attacker.** Generalize incoming damage from "opponent's current Active
   only" (`_incoming_active_damage`) to `opp_best_attack_vs(body)` = the max weakness-adjusted damage over
   every opponent Pokémon that could **afford to attack next turn** (attached energy ≥ its attack cost,
   allowing +1 for their attach). The hardest-hitting affordable body *is* the predicted promotion. For a
   **benched** body of mine, incoming = the opponent's best **bench-snipe** damage only (snipe-only — we do
   NOT assume the opponent gusts my bench body Active; that needs predicting their Boss's Orders).

5. **Target picker** (wincon always has priority): **(a)** the Active wincon if the Cape *saves* it (gains
   a turn) or as the anti-shuffle default; **(b)** else, if the Active is **doomed even through +100**, the
   **next-in-line we will promote** (our own promote-priority: ready benched wincon → a Staryu we can
   evolve → the staller) — the Cape rides up the line; **(c)** a benched line-piece being **sniped down**
   (the snipe-survival case); **(d)** a defensive **wall** (e.g. a re-emerged Cinderace) only if +100 buys
   it a turn AND no wincon need outranks it; **(e) never** a body the opponent KOs even at +100; **never**
   override a lethal KO (deploy is positional — the KO invariant of reviewed.json `82756664-36` stands).

6. **Belt-and-suspenders**, because each covers a case the other cannot. **Suspenders (the primary fix):**
   the Doctrine scores the picked target's attach **positive** → tier 2 → attached *before* the tier-3
   shuffle. **Belt:** a new `hold-irreplaceable-tool-dont-shuffle` Hypothesis (mirror of
   `hold-wincon-dont-shuffle`) penalises a `shuffle_hand` play while holding an unattached irreplaceable
   Tool — the case the positive deploy *cannot* reach (the only target is a bad one, so **hold** rather
   than fritter or shuffle).

7. **Reconcile the three existing tool weights.** `deploy-hp-tool-on-breakpoint` (+50, Active-only) is
   **replaced** — subsumed by survival-turns (which also covers bench + the doomed→successor case).
   `save-tool-for-the-attacker` (−15) + `protect-ace-spec-tool` (−10) are **re-scoped** to fire only on a
   body the picker *rejected* (a spent/off-line opener), never on a wincon **line-piece** — that mis-fire
   (−25 on a benched Staryu) is exactly what broke correction #2.

8. **New infra** (general, deck-agnostic; read off engine stats): `CardStat.benchSnipeDamage` (wire the
   existing `parse_attack_bench_snipe` parser into a field, the mirror of `hpBonus`/`handSizeDamage`); the
   generalized `opp_best_attack_vs`; the `survival_turns` primitive; and a "our next promotion" predictor
   reusing the existing promote-priority. Keyed on `CardStat.aceSpec` / `hpBonus` / `tool` + the wincon
   Roles — **general**, not mega_starmie-hardcoded, so any deck with a +HP Tool inherits it.

**Considered options.**

- **Narrow fix only — keep the reactive breakpoint, add just the anti-shuffle gate** — rejected: fixes the
  shuffle but leaves the Cape mostly idle in hand until a breakpoint, contradicting the deck owner's
  "deploy it ~99%" intent and ignoring that holding is the riskiest option here.
- **Gust-reachable bench incoming** (assume the opponent can Boss's my benched body Active and hit it with
  their full attack) — rejected: it *suppresses* correction #2 (a gusted 70-HP Staryu eats 210 Nebula and
  dies even at 170, so "buys no turn" → don't Cape), and it requires predicting the opponent holding Boss's,
  which is unobservable. Snipe-only matches the observed-correct play and is sound.
- **Keep "holding = safe" / hold-for-breakpoint** — rejected: it is the bug. Six self-shuffle Supporters
  make holding the *most* likely way to lose the one-of ACE SPEC.
- **Leave the negative weights, just add a bigger positive that out-scores them** — rejected: semantically
  muddled (penalise-then-override) and fragile against retuning. Re-scope the negatives to fire only on a
  genuinely off-line body.
- **A standalone, deck-hardcoded Hero's-Cape rule** — rejected: the pattern (an irreplaceable +HP Tool, a
  deck that shuffles its own hand) is general; key it on `aceSpec`/`hpBonus`/`tool`, as the existing rules
  already do.

**Consequences.** The build adds the `ToolMixin` board-math (`opp_best_attack_vs`, `survival_turns`, the
target picker, the next-promotion predictor), one `CardStat` field (`benchSnipeDamage`), the
`hold-irreplaceable-tool-dont-shuffle` Hypothesis, the positive `deploy-*` deploy rungs, the re-scoped
`save-tool`/`protect-ace-spec` guards, the removal of `deploy-hp-tool-on-breakpoint`, and tests
(test-first; the tagged frames 82866415 / 82867148 become regression cases). The reactive doctrine in
STRATEGY.md §3 is rewritten; while `82756664-36` (KO outranks a positional Cape deploy) **stands**
and is preserved by decision 5. **Accepted residual exposure:** proactive deploy gives up a small amount
to opponent Tool removal — accepted as far cheaper than the self-shuffle loss, and revisitable once the
Read/Posture can see a tool-remover (**deferred seams:** gust-reachability for bench incoming; tool-removal
awareness; the damage-boost OHKO-line model for Maximum Belt et al., a noted sibling). Glossary in
[src/common/CONTEXT.md](../../src/common/CONTEXT.md); doctrine in
[STRATEGY.md §3](../../src/agents/mega_starmie/STRATEGY.md).

**Post-build note (2026-07-01) — accepted branch-(3) limitation (decision 5(d)).** Retesting the
Cape corrections through the shipped Pilot (`pilot.explain`, runtime `tuned.json`) shows decision 5(d)
— the non-wincon **wall** rung, `_best_gain_slot(wincon=False)` at `doctrine_tool.py:172` — fires
whenever an off-line Active gains a survival turn *and* the wincon line is only **benched** (benched
bodies take `bench_snipe`-only incoming, so decision 5(a/c) can't select them). Two corrections land
here and are **both accepted as-is** (dispositioned `refuted`, reviewed.json `82227388-7` + `82756664-9`):
- **`82227388-7`** (turn-1 Active Cinderace 160hp, bench 2× Staryu, opp Cinderace affords Turbo Flare 50):
  the wall gains 2 turns (`survival_gain(160,50,100)=2`), so the Cape deploys on Cinderace rather than
  holding. We accept proactive-deploy over hold (six self-shuffle Supporters make holding the riskier line).
- **`82756664-9`** (Active Cinderace 130hp, benched Staryu): the Cape deploys on the Cinderace wall over
  the human's benched Staryu. The *original shuffle-away blunder is gone*, but branch(3) targets the
  present-survival wall over the future-wincon line piece. Accepted; note the anti-shuffle argument does
  **not** favour Cinderace over the (equally shuffle-safe) Staryu here — this is purely present-survival >
  future value.

**Known cost we are choosing to bear:** Cinderace is a terminal Stage-2 (`←Raboot`, a separate Fire line),
so a Cape on it can **never** transfer up to Mega Starmie ex — branch(3) treats the one-of ACE SPEC like a
fungible +HP tool. A future refinement (deferred, not scheduled) would add a "carrier retains the Cape's
value" gate (wincon or a body that can transfer it up) before branch(3) commits an **irreplaceable** tool;
until then `82227388-7`/`82756664-9` stand refuted by explicit decision, not fixed.
