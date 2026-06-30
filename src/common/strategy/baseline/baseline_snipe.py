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
    # --- the unified threat order (ADR-0020 follow-up): a benched KO is a PRIZE; else snipe the
    # biggest attacker. These supersede the four flat priorities below (kept for back-compat / other
    # decks) by firing higher — `_target_threat_rank` sees already-evolved ex attackers and hand-size
    # lines the flat rules miss, and never picks a low-HP SUPPORT body. ---
    Hypothesis(
        id="snipe-for-the-ko",
        rationale="When an attack lets you choose which benched Pokémon to damage and the snipe rider "
                  "KNOCKS ONE OUT (its remaining HP <= the rider, which ignores Weakness/Resistance), "
                  "take that KO — it's a free PRIZE and one fewer future attacker. Outranks every "
                  "positional snipe priority (a guaranteed prize beats chipping a scarier body), so the "
                  "agent never passes up a benched knockout (Noctowl at 50, Applin at 40) to poke a "
                  "high-HP threat it can't finish.",
        when=lambda c: c.select_context == _DAMAGE and c.target_kos,
        weight=60, status="testing"),
    Hypothesis(
        id="snipe-the-top-threat",
        rationale="When no benched target can be KO'd, hit the BIGGEST threat — the body whose own or "
                  "eventual (forward-evolution) attack damage is greatest (`board.strongest_threat_rank`). "
                  "Unlike the flat weakest/evolving rules this sees an already-evolved ex / Mega ex "
                  "attacker by its PRINTED damage (Dragapult ex 200, Mega Lucario ex 270 — the "
                  "descendants-only forward signal scores them 0), prefers the more-developed body on a "
                  "shared line (Drakloak over Dreepy), and boosts a line that CERTAINLY reaches a "
                  "hand-size attacker (Kadabra → Alakazam, whose 10 printed damage hides it) — a "
                  "card-fact read, not a meta guess. So the agent snipes the real attacker, never a "
                  "low-HP SUPPORT Pokémon. Stands down on a KO target (that's snipe-for-the-ko).",
        when=lambda c: c.select_context == _DAMAGE and c.target_is_top_threat and not c.target_kos,
        weight=30, status="testing"),
    Hypothesis(
        id="snipe-the-threat",
        rationale="When an attack lets you choose which benched Pokémon to damage, hit the biggest "
                  "threat. A benched Pokémon already carrying Energy is closest to attacking, so "
                  "sniping it (chip or Knock Out) denies the opponent their next attacker rather "
                  "than poking a bare, not-yet-online benchsitter. Co-fires with `snipe-the-top-threat` "
                  "(the energized body is also the highest-ranked when none is bigger), reinforcing the "
                  "energized pick; the threat RANK (`_target_threat_rank`) already tiers energized "
                  "targets above bare ones, so this is the legible imminence signal on top of it.",
        when=lambda c: c.select_context == _DAMAGE and c.target_is_threat,
        weight=20, status="testing"),
    # NOTE: the flat `snipe-the-weakest` / `snipe-the-evolving-threat` / `snipe-the-strongest-evolving-
    # threat` priorities were RETIRED — `snipe-the-top-threat` (the unified `_target_threat_rank`)
    # subsumes all three: it sees already-evolved ex attackers (printed damage, which the descendants-
    # only forward signal scored 0), tiers energized bodies above bare ones, and never piles onto a
    # low-HP SUPPORT mon the way `snipe-the-weakest` did (the round-b7e483a bad-target blunders). A
    # genuine knockout is `snipe-for-the-ko`. The `EVOLVING_THREAT_DMG` floor below stays (the Read
    # consumer and `target_is_strongest_forward` may still reference it).
]
