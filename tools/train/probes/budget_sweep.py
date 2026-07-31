"""`_incoming_budget` base_attach — the pure core of a RULED sweep (its runner is deleted).

The doom-shadow grill (2026-07-23) proved generic supporter accel (Crispin/Waitress — pool-generic
`energy_accel` Supporters) beats an `attached + 1` affordability read by one in ANY deck, and the
DOOM consumer shipped on the stricter `{base_attach: 2}` accordingly. `_incoming_budget`'s own
consumers still run `{base_attach: 1}` behind a matched Read: the ±50 survival nudge
(`_incoming_worst` / `_survives_after_ko`), the `-KO_SCORE` loss rung (`_predicted_loss`), and the
promote stand-down (`opp_cannot_punish_wincon`). All of them — and none of the doom path — flow
through ONE seam: `combat.reachable_incoming(charged=...)`.

**The question is ANSWERED and the answer is written down**, so under ADR-TEMP-243 decision 1 this
is a RULING, not a runnable diagnostic: the sweep replayed every committed correction twice through
fresh shipped Pilots — stock, and with `reachable_incoming` wrapped so a matched `{base_attach: 1}`
budget is upgraded to `{base_attach: 2}` — and found **zero decision flips**. Ruling:
`_incoming_budget` KEEPS `base_attach: 1`; the stricter `_DOOM_CHARGED` stays doom-consumer-only.

Re-confirmed against the WIDENED corpus before the runner was deleted, because the original was a
count over 332 frames of a 372-frame corpus (ADR-0087's 40 missing records): **measured at `4be1db3`,
372 frames — 371 SAME, 1 SKIP, 0 IMPROVED / REGRESSED / MOVED.** Recorded with its **Corpus
Provenance** stamp in `docs/plans/doom-shadow-grill-handoff.md`.

What survives here is the pure core the ruling was computed with — engine-free, corpus-free, and
covered by `REQ-BUDGETSWEEP`. It reads no corpus at all, which is why this module carries no Corpus
Reader and needs none.
"""
from __future__ import annotations


# ------------------------------------------------------------------------------ pure core
def upgrade_charged(charged):
    """The budget under study: a matched `{base_attach: 1}` becomes `{base_attach: 2}` (the
    generic-supporter attach the grill proved); None (unmatched → worst-case ceiling) and any
    other budget pass through untouched — the sweep must never move an unmatched read."""
    if isinstance(charged, dict) and charged.get("base_attach") == 1:
        return {**charged, "base_attach": 2}
    return charged


def wrap_reachable(combat) -> None:
    """Monkeypatch ``combat.reachable_incoming`` so its ``charged`` kwarg flows through
    :func:`upgrade_charged` — the one seam every `_incoming_budget` consumer (and no doom
    consumer) crosses. Everything else passes verbatim."""
    inner = combat.reachable_incoming

    def wrapped(my_body, opp_bodies, **kw):
        kw["charged"] = upgrade_charged(kw.get("charged"))
        return inner(my_body, opp_bodies, **kw)

    combat.reachable_incoming = wrapped


def verdict(chosen_stock, chosen_up, *, correct) -> str:
    """Classify one frame's decision pair against the recorded human pick."""
    if chosen_stock == chosen_up:
        return "SAME"
    if correct is not None and chosen_up == correct:
        return "IMPROVED"
    if correct is not None and chosen_stock == correct:
        return "REGRESSED"
    return "MOVED"
