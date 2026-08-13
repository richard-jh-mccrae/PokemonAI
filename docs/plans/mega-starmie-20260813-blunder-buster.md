# Mega Starmie correction pass: 2026-08-13

Source: `data/corrections/mega_starmie_20260813_c9991b12/` (14 records).

## Classification

- New general machinery: setup-only `opener` legality; optional reveal-window Bellman choices;
  simultaneous Active-and-Bench knockout readiness; full refinement of root menus with at most three
  actions.
- General tuning: retain only 25% of safe damage as healable value; remove setup-only Pokemon from
  post-setup hand-resource value.
- Existing behavior confirmed: attack over End, denial before attack, turn-plan opening actions, and
  attaching to the healthy unpowered attacker.
- Annotation limitations: `47126201206d` asks for two information actions in a one-choice Main menu,
  so the regression accepts either as the first action; turn-scope
  records use an empty `correct` array and express the sequence in `turn_plan`; `1fe0da3d8b94` and
  `854d18378289` report freezes rather than a reasoned action preference.

## Bellman terms

- Safe own damage contributes `0.25 * damage_progress`; lethal exposure restores its full liability.
- A fully payable printed attack that can knock out both the opposing Active and a Bench target adds
  both targets' prize values to `multi_target_ko` readiness.
- Reveal outcomes describe which eligible identities appear; each exposed identity and the legal
  decline action lead to separately valued continuations.
- Root menus of three or fewer actions refine every branch; wider menus retain successive halving.
- Every root action receives a 96-node equal probe before the best incomplete continuations receive
  a 256-node refinement. Larger 600- and 1,800-node refinements both exceeded the ten-minute
  packaged-mirror deadline.
- Reveal-choice roots within 0.10 prize-equivalents of the best equal-probe result may use 1,300
  nodes because their chance outcomes each own a selectable
  continuation; this uncertainty budget is effect-shaped and contains no card identity.
- Chance roots within the same margin may use 600 nodes so hidden-draw and coin outcomes are compared
  beyond their shared shallow lower bound. Far-behind uncertainty actions receive no diversity slot.
- Production search has a 15-second refinement deadline after every root action receives its equal
  probe. Expiry uses the existing legal End
  lower bound; it changes resource allocation, not action semantics or turn depth.

No card ID or deck-specific rule was added to common Bellman code. Correction-specific identities
exist only in the regression fixture.

## Validation

- Focused batch: 14/14 pass.
- Full Bellman suite at the behavior-safe deadline: run separately from the mirror gate.
- Packaged native mirror: one match passed in 287.281s (callback avg/min/max
  2.351/0.000/12.250s). The required 10-game serial run did not pass: its first match exceeded
  600s in repeated attempts. Lower 5s, 8s, and 10s decision deadlines caused correction or
  historical tactical regressions, so they were rejected.
