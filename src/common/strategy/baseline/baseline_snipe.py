"""BASELINE cluster: SNIPE — choosing WHICH benched Pokémon to damage at a DAMAGE select (ADR-0025).

The four bench-snipe priorities (energized threat > evolving threat > weakest), guarded so they never
double-count. Pure data, no Mixin. `EVOLVING_THREAT_DMG` (the line-becomes-an-attacker floor) lives
here because only the snipe rules read it.
"""
from common.strategy.context import _DAMAGE
from common.strategy.strategy import Hypothesis

# Evolution line "becomes an attacker" once it can OHKO a median body (median HP = 100; 100 is
# ~p76 of damaging attacks). Tunable seed for `snipe-the-evolving-threat` (ADR-0020, docs/rules.md).
EVOLVING_THREAT_DMG = 100

HYPOTHESES = [
    # --- unified threat order (ADR-0020 follow-up): a benched KO is a PRIZE; else snipe the
    # biggest attacker. Supersedes the four flat priorities below (kept for back-compat / other
    # decks) by firing higher — `_target_threat_rank` sees already-evolved ex attackers and hand-size
    # lines the flat rules miss, never picks a low-HP SUPPORT body. ---
    Hypothesis(
        id="snipe-for-the-ko",
        rationale="If a damage-select's snipe rider KOs the target (remaining HP <= rider, which ignores "
                  "Weakness/Resistance), take it — a free prize beats any positional snipe. Outranks every "
                  "other snipe priority.",
        when=lambda c: c.select_context == _DAMAGE and c.target_kos,
        weight=60, status="testing"),
    Hypothesis(
        id="snipe-the-top-threat",
        rationale="When no target can be KO'd, hit the biggest threat by `board.strongest_threat_rank` "
                  "(own or forward-evolution damage) — sees already-evolved ex/Mega ex attackers by "
                  "printed damage, prefers the more-developed body on a shared line, and boosts lines "
                  "that certainly reach a hand-size attacker, so it never pokes a low-HP support mon. "
                  "Stands down on a KO target (that's snipe-for-the-ko).",
        when=lambda c: c.select_context == _DAMAGE and c.target_is_top_threat and not c.target_kos,
        weight=30, status="testing"),
    Hypothesis(
        id="snipe-the-threat",
        rationale="A benched Pokémon already carrying Energy is closest to attacking, so sniping it "
                  "denies the opponent their next attacker rather than poking a bare benchsitter. "
                  "Co-fires with `snipe-the-top-threat` (`_target_threat_rank` already tiers energized "
                  "targets above bare ones) as the legible imminence signal on top of it.",
        when=lambda c: c.select_context == _DAMAGE and c.target_is_threat,
        weight=20, status="testing"),
    # NOTE: flat `snipe-the-weakest` / `snipe-the-evolving-threat` / `snipe-the-strongest-evolving-
    # threat` priorities were RETIRED — `snipe-the-top-threat` (unified `_target_threat_rank`)
    # subsumes all three: sees already-evolved ex attackers (printed damage, which the descendants-
    # only forward signal scored 0), tiers energized bodies above bare ones, never piles onto a
    # low-HP SUPPORT mon like `snipe-the-weakest` did (round-b7e483a bad-target blunders). Genuine
    # knockout is `snipe-for-the-ko`. `EVOLVING_THREAT_DMG` floor below stays (Read consumer +
    # `target_is_strongest_forward` may still reference it).
]
