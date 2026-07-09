# Handoff — make the FETCH decision prize-economy-aware

**Repo:** `C:\Users\Richard\Projects\PokemonAI`
**Next session's task (user's words):** the solrock fetch fix *"relates to how we want to offer prizes
to the opponent … we want to force our opponent to take 8 prize cards instead of 6, ideally they must
KO Solrock, Lucario, Hariyama, then the second Lucario."* Build the general version of that.
**Date raised:** 2026-07-09 (during the `/update-strategy` compilation, grilling the solrock T2 rule).
**Status:** the current fetch rules are a working **gut-feeling proxy**; this is the principled upgrade.

## The idea
Which card you grab at a search should be scored by **prize economy** — how many bodies (and which
prize values) the opponent must KO to reach six, and how much you make them *grind*. Presenting a
layer of cheap **1-prize attackers** (Solrock, Hariyama) in front of the 3-prize Megas forces the
opponent onto an 8-prizes-of-work path for a 6-prize game (odd-prizing / "force the extra turn"), and
denies clean 2-for-1 / 3-for-1 KOs. So a fetch that **develops a cheap attacker layer** or **completes
the missing engine half** can beat fetching a redundant high-prize body — even when the naive grab
value ties.

## What exists today (the proxy — don't rip out, generalise)
The Solrock↔Lunatone pairing doctrine (`src/agents/mega_lucario/strategy.py`, this session's build)
already gets the *direction* right for that deck via role/quantity rules:
- `dont-fetch-the-redundant-piece` (−22) — skip a piece already in play (2nd Solrock / in-play Riolu).
- `dont-fetch-the-inert-engine-piece` (−20) — skip an inert engine half (partner unreachable).
- `fetch-the-missing-engine-half` (+20) — complete the one-of-each engine.

These are **deck-specific and role-keyed**, not a general prize-economy valuation. The user flagged the
`win_condition_base`-redundant extension (skip an in-play Riolu) as a gut feeling that *"isn't 100%
best"* — it works because developing Makuhita→Hariyama (cheap attacker) serves the grind, but the real
driver is prize economy, not "one of each."

## The general build
A prize-economy term in the Fetch value comparator (`src/common/strategy/doctrines/doctrine_fetch.py`,
`_grab_value_of` / the `_TO_HAND` rungs). Score a grab candidate by its contribution to a board that
forces the opponent to take MORE, SMALLER prizes:
- **Prefer developing a cheap (1-prize) attacker layer** when the wincon is 2/3-prize — the bodies you
  trade first, so each opponent KO banks only 1 (`card_prize_value`, `CardStat` / `_prize_value`).
- **Deprioritise a redundant high-prize body** you already field (a 2nd Mega with no complementary
  role) unless the deck's plan genuinely needs the duplicate (dual-Mega — gate on "wincon already
  online" so the FIRST copy is never blocked).
- This is the **FETCH-seam mirror** of the already-shipped **promote-seam** prize-economy trio
  (`baseline_promote.py`: `interpose-the-cheap-attacker-to-preserve-the-wincon` +50,
  `dont-promote-into-their-prize-reach` −20, `dont-promote-onto-their-path` −8) and
  `_bench_shortens_their_path`. Reuse their prize-value math for consistency.

## Provenance / where it connects
- **Proposal:** `data/strategy/proposals/learnthetcg-fundamentals.md` · `prize-value-board-shaping`
  (status **applied/COVERED** — but only at the PROMOTE/bench seams; the FETCH seam is the gap this
  handoff fills). Also `deny-prizes-via-fewer-kos` (the flip side, forgo-KO seam).
- **Corrections that motivated it:** `ml_dont_fetch_redundant_solrock_f12`, `..._inert_..._f26` (both
  land today via the deck rules; a general prize-economy term should subsume the deck-specific halves).
- **Prize signals:** `Context.card_prize_value`, `Pilot._prize_value`, `CardStat` prize/ex flags.
- **Memory:** `[[interpose-cheap-attacker-promote]]`, `[[promote-after-ko-priority]]`,
  `[[deck-content-odds]]` (for reasoning about the opponent's KO count).

## Guardrails
- **Score-diff neutral off-trigger** — a general prize-economy fetch term must not change grabs for
  decks/boards where the naive value already picks right (ADR-0034). Gate on the wincon being
  multi-prize + a cheap-attacker option present.
- **Never override a real need** — energy-when-starved / fetch-the-wincon / the missing-line-piece
  still dominate; prize economy is a TIE-BREAK-to-normal-band term, not a top rung.
- **Ladder-validate** (gauntlet is invalid-for-gain, `[[gauntlet-invalid-ladder-only]]`); ship
  default-on, kill-switched, with blunder-buster telemetry.
- **Don't regress the solrock deck rules** — the general term should let them fold (deck-align), not
  fight them; verify the 7 solrock fixtures still land.
