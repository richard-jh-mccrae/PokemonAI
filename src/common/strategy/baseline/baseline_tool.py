"""BASELINE cluster: TOOL — Pokémon Tool equips at an ATTACH select (ADR-0025). A one-shot equip:
hold it for the win-condition, be extra-careful with an irreplaceable ACE SPEC, and deploy a +HP Tool
only on the survival breakpoint. Pure data, no Mixin (HP math reads CardStat / Board signals).
"""
from common.strategy.context import _ACTIVE, _ATTACH, _WINCON_ROLES
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="save-tool-for-the-attacker",
        rationale="A Pokémon Tool (Function Tag `tool`, e.g. Hero's Cape) is a one-shot equip — don't "
                  "spend it on an off-role Pokémon (a spent opener / accelerator). Hold it for the "
                  "win-condition / primary attacker that will actually carry the game.",
        when=lambda c: c.option_type == _ATTACH and "tool" in c.tags
        and not (_WINCON_ROLES & set(c.attach_target_roles)),
        weight=-15, status="testing"),
    Hypothesis(
        id="protect-ace-spec-tool",
        rationale="An ACE SPEC card is limited to one per deck and is usually irreplaceable (no second "
                  "copy; not recoverable from the discard). So beyond the usual 'hold a Tool for the "
                  "attacker' reluctance, be EXTRA reluctant to spend an ACE SPEC Tool (e.g. Hero's Cape) "
                  "on an off-role Pokémon — a wasted one-of ACE SPEC is gone for the whole game. Stacks "
                  "additively on `save-tool-for-the-attacker` and reads the structural `aceSpec` fact "
                  "off CardStat; fires only off the win-condition, like the base rule.",
        when=lambda c: c.option_type == _ATTACH and "tool" in c.tags
        and c.stat is not None and getattr(c.stat, "aceSpec", False)
        and not (_WINCON_ROLES & set(c.attach_target_roles)),
        weight=-10, status="testing"),
    Hypothesis(
        id="deploy-hp-tool-on-breakpoint",
        rationale="Deploy a +HP Pokémon Tool the turn it changes a combat outcome — not before. Fires "
                  "when your Active win-condition is about to be Knocked Out (`active_doomed`) AND the "
                  "Tool's flat HP boost would lift it ABOVE the incoming hit (e.g. +100 takes 330 -> "
                  "430, dodging a Lightning OHKO that 330 wouldn't survive). Reads the per-Tool HP off "
                  "`CardStat.hpBonus` (parsed from the Tool's text — the engine has no structured field) "
                  "and the weakness-aware `Board.incoming_active_damage`, so it generalises to ANY "
                  "unconditional +HP Tool and ANY weakness — the deck need not hardcode the bonus. Don't "
                  "equip early (that just exposes an irreplaceable card — e.g. an ACE SPEC Hero's Cape — "
                  "to removal); don't waste it when the boost wouldn't save the Pokémon anyway. Gated to "
                  "the win-condition Active (don't burn a one-shot Tool on a disposable body) and a "
                  "positional weight, so a lethal/KO still outranks it.",
        when=lambda c: c.option_type == _ATTACH and "tool" in c.tags
        and c.stat is not None and getattr(c.stat, "hpBonus", 0) > 0
        and c.attach_target_area == _ACTIVE and bool(_WINCON_ROLES & set(c.attach_target_roles))
        and c.board.active_doomed
        and c.board.incoming_active_damage < c.board.my_active_hp + c.stat.hpBonus,
        weight=50, status="testing"),
]
