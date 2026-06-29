"""BASELINE cluster: SNIPE — choosing WHICH benched Pokémon to damage at a DAMAGE select (ADR-0025).

The four bench-snipe priorities (energized threat > evolving threat > weakest), guarded so they never
double-count. Pure data, no Mixin. `EVOLVING_THREAT_DMG` (the line-becomes-an-attacker floor) lives
here because only the snipe rules read it.
"""
from common.strategy.context import _DAMAGE
from common.strategy.strategy import Hypothesis

# An evolution line "becomes an attacker" once it can OHKO a median body (median HP = 100; 100 is
# ~p76 of damaging attacks). Tunable seed for `snipe-the-evolving-threat` (ADR-0020, docs/rules.md).
EVOLVING_THREAT_DMG = 100

HYPOTHESES = [
    Hypothesis(
        id="snipe-the-threat",
        rationale="When an attack lets you choose which benched Pokémon to damage, hit the biggest "
                  "threat. A benched Pokémon already carrying Energy is closest to attacking, so "
                  "sniping it (chip or Knock Out) denies the opponent their next attacker rather "
                  "than poking a bare, not-yet-online benchsitter.",
        when=lambda c: c.select_context == _DAMAGE and c.target_is_threat,
        weight=20, status="testing"),
    Hypothesis(
        id="snipe-the-weakest",
        rationale="When an attack lets you choose a benched Pokémon to damage and none is a live "
                  "Energy-threat, hit the LOWEST-HP one — it's closest to a knockout (a prize, and "
                  "one fewer future attacker) and avoids dumping a small snipe into a high-HP wall "
                  "it can't dent. Ranks below `snipe-the-threat`, so an energy-bearing attacker is "
                  "still sniped first.",
        when=lambda c: c.select_context == _DAMAGE and c.target_is_weakest,
        weight=15, status="testing"),
    Hypothesis(
        id="snipe-the-evolving-threat",
        rationale="When an attack lets you choose a benched Pokémon to damage and none carries "
                  "Energy, hit a fragile pre-evolution whose evolution line becomes a real attacker "
                  "(its line eventually deals >= 100 — enough to OHKO a typical Active, e.g. Riolu → "
                  "Mega Lucario ex). Sniping it now, before it evolves and powers up, denies that "
                  "future threat. Fires only when the target carries no Energy — the energized case "
                  "is `snipe-the-threat`, so the two never double-count — and ranks below it (an "
                  "energized attacker hits sooner). Stacks additively with `snipe-the-weakest`: a "
                  "low-HP evolving target is the best snipe of all. Generic (any deck); the Read "
                  "refines its accuracy at M2.",
        when=lambda c: c.select_context == _DAMAGE and not c.target_is_threat
        and (c.target_forward_damage or 0) >= EVOLVING_THREAT_DMG,
        weight=18, status="testing"),
    Hypothesis(
        id="snipe-the-strongest-evolving-threat",
        rationale="Among benched pre-evolutions whose lines become attackers, snipe the MOST dangerous "
                  "one — the line that eventually deals the most damage (Riolu → Mega Lucario ex 270, "
                  "online at a single Energy, over Makuhita → Hariyama 210). Breaks the tie that the "
                  "flat `snipe-the-evolving-threat` (any line >= 100) leaves, and stacks high enough to "
                  "outweigh `snipe-the-weakest` so the scariest FUTURE attacker is chipped even when it "
                  "is not the lowest-HP body on the Bench. Fires only on the strongest forward threat "
                  "that carries no Energy, and ONLY when no benched target is already energized — an "
                  "imminent (energized) attacker is `snipe-the-threat`'s job and outranks a latent "
                  "evolving one, so this stands down whenever such a threat is on the Bench.",
        when=lambda c: c.select_context == _DAMAGE and c.target_is_strongest_forward
        and not c.target_is_threat and not c.board.bench_threat_present,
        weight=20, status="testing"),
]
