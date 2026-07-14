"""Brief-consumer runtime: load Matchup Briefs + match one to the Read (ADR-0027).

Offline, synthetic briefs. The bridge (load + match) mirrors artifact.load_artifact +
matchup.matchup_favorability; the γ-gated consumers are the ADR-0038 Tactical levers (test_posture_read).
"""
import json

import pytest

from common.scouting.briefs import Brief, load_briefs, match_brief, resolve_brief_cards
from common.scouting.matchup_plan import build_matchup_plan
from common.scouting.provider import EngineCardStatProvider
from common.scouting.read import Read


def _write_brief(d, slug, covers, **extra):
    brief = {"slug": slug, "label": extra.get("label", slug), "covers": covers,
             "tempo": extra.get("tempo", "midrange"), "summary": extra.get("summary", ""),
             "opponent_properties": extra.get("opponent_properties", {}),
             "threats": extra.get("threats", []), "targets": extra.get("targets", [])}
    (d / f"{slug}.json").write_text(json.dumps(brief), encoding="utf-8")


def _read(*candidates):
    """A Read whose candidates are (archetype, posterior) pairs, highest first."""
    return Read(candidates=list(candidates))


def test_load_briefs_reads_a_well_formed_brief(tmp_path):
    _write_brief(tmp_path, "alakazam", ["Alakazam", "Alakazam / Frillish"], label="Alakazam")
    briefs = load_briefs(tmp_path)
    assert len(briefs) == 1
    assert briefs[0].slug == "alakazam"
    assert "Alakazam / Frillish" in briefs[0].covers


def test_load_briefs_is_fail_safe(tmp_path):
    _write_brief(tmp_path, "good", ["Good"])
    (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")
    (tmp_path / "noslug.json").write_text('{"covers": ["X"]}', encoding="utf-8")   # missing slug
    briefs = load_briefs(tmp_path)
    assert [b.slug for b in briefs] == ["good"]                    # bad files skipped, good kept
    assert load_briefs(tmp_path / "nope") == []                   # missing dir -> []


def test_match_brief_routes_top_candidate_via_covers(tmp_path):
    _write_brief(tmp_path, "alakazam", ["Alakazam", "Alakazam / Frillish"])
    _write_brief(tmp_path, "hariyama", ["Hariyama / Mega Lucario ex"])
    briefs = load_briefs(tmp_path)
    # top candidate is a VARIANT string (not the label) -> still routes to alakazam Brief
    m = match_brief(briefs, _read(("Alakazam / Frillish", 0.7), ("Hariyama / Mega Lucario ex", 0.2)))
    assert m is not None and m.slug == "alakazam"


def test_match_brief_none_when_unrecognized(tmp_path):
    _write_brief(tmp_path, "alakazam", ["Alakazam"])
    briefs = load_briefs(tmp_path)
    assert match_brief(briefs, _read(("Some Off-Meta Deck", 0.3))) is None   # no covering Brief
    assert match_brief(briefs, _read()) is None                              # no candidates
    assert match_brief(briefs, None) is None                                 # no Read


# ---- resolve_brief_cards: name-keyed threats/targets -> card ids (the Board consumer's substrate) ----

def _ml_brief(**extra):
    """A Mega Lucario ex Brief carrying threats + role-tagged targets (name-keyed)."""
    return Brief(slug="ml", label="ML", covers=["Mega Lucario ex"],
                 threats=extra.get("threats", [{"card": "Mega Lucario ex", "why": "270"}]),
                 targets=extra.get("targets", [{"card": "Riolu", "role": "fragile_preevo", "why": "snipe"}]))


def test_resolve_brief_cards_maps_names_to_ids_and_roles():
    # A threat name -> a threat id; a target name -> {id: role}. Names resolve via the injected lookup.
    name_ids = {"Mega Lucario ex": {678}, "Riolu": {677}}
    threat_ids, target_roles = resolve_brief_cards(_ml_brief(), lambda n: name_ids.get(n, ()))
    assert threat_ids == frozenset({678})
    assert target_roles == {677: "fragile_preevo"}


def test_resolve_brief_cards_skips_unresolvable_names():
    # A name the lookup doesn't know resolves to no id -> silently skipped, never raises.
    threat_ids, target_roles = resolve_brief_cards(
        _ml_brief(targets=[{"card": "Ghost Card", "role": "engine", "why": "?"}]),
        lambda n: {"Mega Lucario ex": {678}}.get(n, ()))
    assert threat_ids == frozenset({678})
    assert target_roles == {}                    # "Ghost Card" unknown -> dropped


def test_resolve_brief_cards_maps_a_name_to_all_its_ids():
    # A name printed under several card ids (reprints) maps ALL of them to the role.
    _, target_roles = resolve_brief_cards(
        _ml_brief(threats=[], targets=[{"card": "Riolu", "role": "fragile_preevo", "why": "x"}]),
        lambda n: {"Riolu": {677, 6771}}.get(n, ()))
    assert target_roles == {677: "fragile_preevo", 6771: "fragile_preevo"}


def test_resolve_brief_cards_lists_a_card_that_is_both_threat_and_target():
    # Mega Lucario ex is BOTH a threat (respect) and a prize_liability target (exploit) -> both outputs.
    brief = _ml_brief(threats=[{"card": "Mega Lucario ex", "why": "270"}],
                      targets=[{"card": "Mega Lucario ex", "role": "prize_liability", "why": "3 prizes"}])
    threat_ids, target_roles = resolve_brief_cards(brief, lambda n: {"Mega Lucario ex": {678}}.get(n, ()))
    assert threat_ids == frozenset({678})
    assert target_roles == {678: "prize_liability"}


# ---- shipped-dir invariants (ADR-0038 hardening): the REAL briefs/ dir stays collision-free ----

def test_shipped_briefs_have_no_covers_collision():
    """REQ-BRIEF-0001: no archetype string appears in two shipped Briefs' `covers` — match_brief
    returns the alphabetically-first covering Brief, so an overlap would misroute SILENTLY."""
    seen: dict[str, str] = {}
    for brief in load_briefs():                    # the real src/common/scouting/briefs/ dir
        for arch in brief.covers:
            assert arch not in seen, (
                f"archetype {arch!r} covered by both {seen[arch]!r} and {brief.slug!r} — "
                f"every archetype string must route to exactly ONE Brief")
            seen[arch] = brief.slug


@pytest.mark.req("REQ-BRIEF-0003")
def test_dragapult_brief_ranks_its_wincon_above_its_support_exes():
    """The Dragapult ex Brief roled its three NON-Tera 2-prize support ex's (Fezandipiti / Latias /
    Meowth) `prize_liability` and left the actual win-condition — Dragapult ex — with NO role at all.
    The `why` texts say why: "NOT Tera (valid target)". It was a WORKAROUND for the missing Tera guard:
    roling the Tera wincon would have made the snipe chip an immune body.

    `_snipe_tera_veto` removed that constraint (the snipe now stands down on a benched Tera
    structurally, while the GUST legitimately drags it Active — where the immunity does not apply), so
    the roles can now say what they mean. The wincon must OUT-RANK the support ex's: they are all worth
    2 prizes, so without this the gust would drag up a support body over the body whose loss ends the
    game."""
    prov = EngineCardStatProvider()
    brief = next(b for b in load_briefs() if b.slug == "dragapult_ex")
    _, roles = resolve_brief_cards(brief, prov.ids_for_name)
    plan = build_matchup_plan(brief_roles=roles, gamma=1.0)

    def _pri(name):
        return max(plan.priority(i) for i in prov.ids_for_name(name))

    wincon = _pri("Dragapult ex")
    assert wincon > 0, "the Dragapult ex WINCON must carry a target role (it had none)"
    for support in ("Fezandipiti ex", "Latias ex", "Meowth ex"):
        assert wincon > _pri(support), (
            f"Dragapult ex (the win-condition) must out-rank the support ex {support!r} — all are "
            f"2-prize bodies, so the gust would otherwise drag up a support body over the wincon")


def _ancestor_names(prov, cid: int) -> set[str]:
    """Every pre-evolution NAME above ``cid`` in its line (walks ``CardStat.evolvesFrom``)."""
    names: set[str] = set()
    stat = prov.get(cid)
    name = getattr(stat, "evolvesFrom", None) if stat else None
    while name and name not in names:
        names.add(name)
        nxt = None
        for i in (prov.ids_for_name(name) or ()):
            s = prov.get(i)
            if s and getattr(s, "evolvesFrom", None):
                nxt = s.evolvesFrom
                break
        name = nxt
    return names


@pytest.mark.req("REQ-BRIEF-0002")
def test_shipped_briefs_never_neutralize_a_wincon_line_payoff():
    """ADR-0051: the `engine` role resolves to priority 0 AND — as the top (curated) tier of
    `build_matchup_plan`, which is last-write-wins — it OVERRIDES whatever the Read would have
    contributed. So an `engine` row is an ACTIVE suppressor, not merely inert data.

    A Brief that roles a pre-evolution `fragile_preevo` ("snipe it to deny the payoff") and then
    roles that same line's PAYOFF `engine` contradicts itself and pins the win-condition at
    priority 0. That was the alakazam bug: Powerful Hand has no printed damage (maxDamage 0), so
    the GENERIC threat model read the wincon as harmless too — it had zero priority from every
    path, and the agent never targeted it.

    OMITTING the payoff from `targets` stays legitimate and is NOT pinned here — a payoff can be
    genuinely UNTARGETABLE: Crustle prevents ALL damage from Pokémon ex (and every one of our
    win-conditions is an ex), and Dragapult ex is a **Tera** (`Category: Tera(Dragon)`,
    `CardStat.tera`) — Tera Pokémon take NO damage from attacks while BENCHED (rules.md §185), which
    is precisely what the Tera label identifies. This pins only the explicit NEUTRALIZATION of a
    payoff the Brief simultaneously snipes the pre-evo of, which is always a contradiction.
    """
    prov = EngineCardStatProvider()
    for brief in load_briefs():
        _, target_roles = resolve_brief_cards(brief, prov.ids_for_name)
        preevo_names = {getattr(prov.get(i), "name", None)
                        for i, r in target_roles.items() if r == "fragile_preevo"}
        for cid, role in target_roles.items():
            if role != "engine":
                continue
            clash = _ancestor_names(prov, cid) & preevo_names
            assert not clash, (
                f"{brief.slug}: target {getattr(prov.get(cid), 'name', cid)!r} is roled `engine` "
                f"(priority 0) but it is the PAYOFF of the line whose pre-evolution(s) "
                f"{sorted(clash)} the SAME Brief roles `fragile_preevo`. The Brief snipes the "
                f"pre-evo to deny a payoff it then declares neutral — pinning the win-condition at "
                f"priority 0 (ADR-0051). Role the payoff `prize_liability`, or drop the `engine` row.")
