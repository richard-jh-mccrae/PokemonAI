"""`_incoming_budget` base_attach — the pure core of a RULED sweep (its runner is deleted).

**Ruling:** `_incoming_budget` KEEPS `base_attach: 1`; the stricter `{base_attach: 2}` stays
doom-consumer-only. Every committed correction was replayed twice through fresh shipped Pilots with
zero decision flips; the evidence and its Corpus Provenance stamp are in
`ADR-0064`, and ADR-0089 decision 1 is why the runner is gone.
"""
from __future__ import annotations


# ------------------------------------------------------------------------------ pure core
def upgrade_charged(charged):
    """A matched `{base_attach: 1}` becomes `{base_attach: 2}`; None (an unmatched worst-case ceiling)
    and any other budget pass through untouched — the sweep must never move an unmatched read."""
    if isinstance(charged, dict) and charged.get("base_attach") == 1:
        return {**charged, "base_attach": 2}
    return charged


def wrap_reachable(combat) -> None:
    """Monkeypatch ``combat.reachable_incoming``'s ``charged`` through :func:`upgrade_charged` — the one seam."""
    inner = combat.reachable_incoming

    def wrapped(my_body, opp_bodies, **kw):
        kw["charged"] = upgrade_charged(kw.get("charged"))
        return inner(my_body, opp_bodies, **kw)

    combat.reachable_incoming = wrapped


def verdict(chosen_stock, chosen_up, *, correct) -> str:
    if chosen_stock == chosen_up:
        return "SAME"
    if correct is not None and chosen_up == correct:
        return "IMPROVED"
    if correct is not None and chosen_stock == correct:
        return "REGRESSED"
    return "MOVED"
