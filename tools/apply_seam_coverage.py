"""**POC-A2 (Issue #269)** — the apply-seam coverage census, as a re-runnable measurement.

Answers *what fraction of the real card pool does `common/apply_option.py` actually reach?* by
resolving every **effect site** in the pool to one of Issue #259 §3b's three fates — MODELLED /
ENGINE-RESOLVED / REFUSED — and weighting the answer by exposure rather than by card count alone.

Writes `docs/plans/apply-seam-coverage.md`'s data sections. The prose verdict is authored in that
report; this module owns every number in it, so a re-run after a compendium build regenerates the
tables rather than leaving the report to rot.

## What an "effect site" is, and why the unit is not the card

A card is not one decision. *Buddy-Buddy Poffin* is one `_PLAY`; *Drakloak* is a `_EVOLVE` **and** an
`_ABILITY`, and its attack is a turn-ender the seam never transitions at all. So the unit here is the
**site**: one (card, option kind, effect) triple that the apply-seam will be asked to price. Sites,
not cards, are what the composer's 1-ply ordering actually visits.

Sites are derived structurally, never from a card's name:

* Basic Energy / Pokémon Tool → one `_ATTACH`. Special Energy → `_ATTACH` **with** an effect.
* Item / Supporter / Stadium → one `_PLAY` with an effect.
* Basic Pokémon → one `_PLAY` (deploy); Stage 1/2 → one `_EVOLVE`. Structural unless the card carries
  an on-play / on-evolve triggered Ability, which rides that same option.
* Each **activated** Ability ("Once during your turn…", "As often as you like…") → one `_ABILITY`.
  Passive and checkup-triggered Abilities pose no option and are counted separately.
* Attacks are TERMINAL (`docs/rules.md` §3): no successor state, so no fate. Counted, never scored.

## Sources — all at-source, none from memory (CLAUDE.md)

* Card facts and **effect text**: `tools/meta_tracker/cards.json`, the portable dump of the engine's
  own `all_card_data()` (`tools/meta_tracker/dump_cards.py`). The engine is the authority; the CSV
  `data/EN_Card_Data.csv` is NOT usable here because it carries one attack per card and **no Ability
  text at all**, and Abilities are exactly what the ENGINE-RESOLVED fate is about.
* Effect Clauses: `src/common/card_effects.json` (ADR-0032), through `common.effects.CardEffects`.
* Fates, kind table and clause write-sets: `common.apply_option` / `common.snapshot_coverage`
  themselves — imported, never re-spelled, so the census cannot drift from the seam it measures.
* Our decks: `src/agents/*/deck.csv`. The opponent pool: the scouting artifact's per-archetype
  `representative_build`, weighted by the artifact's own meta `priors`.

## The one judgement call in this report, and why it does not live here

Whether a card's Effect Clauses cover its **whole** printed effect is not mechanically decidable —
`Surfer` carries a `draw` clause and the printed card also switches the Active, and no parser reads
that. It is a hand ruling, one per clause-bearing card, each quoting the leg the clauses miss, and it
is the report's highest-value column. A PARTIAL clause set used to be **worse than none**, because
§3b resolved it to MODELLED and the omitted leg then priced at exactly 0 — the §3c failure, silently.
Issue #299 wired the verdict into `fate` as `clauses_cover`, so a partial set now refuses; the column
survives because it still names the WORK, and because the seam reads the same store to decide it.

The ruling was a table in THIS file until Issue #300 moved it into the compendium
(`card_effects.json`'s `_covers` block, authored in `effect_overrides.json`), where the apply seam
itself reads it. This module now reads the same store: **the census is a report, the compendium is
the truth**, and a report carrying its own private copy of the fact it reports on is the second
loader ADR-0087 charges for — it would drift, and both sides of the diff would share the drift.

Usage:
    python tools/apply_seam_coverage.py [--out PATH] [--json PATH]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from common import apply_option as seam                                        # noqa: E402
from common import snapshot_coverage                                           # noqa: E402
from common.strategy.context import _ABILITY, _ATTACH, _EVOLVE, _PLAY          # noqa: E402
from common.scouting.card_text import (                                        # noqa: E402
    _parse_retreat_free_grant, _parse_tool_attack_cost_reduction, _parse_tool_holder_family,
    _parse_tool_holder_no_rule_box, _parse_tool_hp_bonus, _parse_tool_retreat_free_at_hp,
    _parse_tool_retreat_reduction, parse_card_damage_boost)


CARDS_JSON = _ROOT / "tools" / "meta_tracker" / "cards.json"
EFFECTS_JSON = _ROOT / "src" / "common" / "card_effects.json"
ARTIFACT_JSON = _ROOT / "src" / "common" / "scouting" / "artifact.json"
AGENTS_DIR = _ROOT / "src" / "agents"
DEFAULT_OUT = _ROOT / "docs" / "plans" / "apply-seam-coverage.md"

#: The generated block is spliced BETWEEN these markers, so the report's authored verdict prose and
#: its measured numbers live in one committed file and a re-run refreshes the numbers without
#: touching a word of the prose. A report whose data sat in a second file would drift from it.
BEGIN = "<!-- BEGIN GENERATED: tools/apply_seam_coverage.py -->"
END = "<!-- END GENERATED -->"

# ── report classes ────────────────────────────────────────────────────────────────────────────────
# The three FATES are `seam.FATES`, imported rather than re-spelled. These four classes are the
# report's own taxonomy on top of them: they partition the sites, and they split MODELLED by whether
# the clause set is COMPLETE, because that split is what the fate alone cannot show.

#: MODELLED, and the Effect Clauses cover the whole printed effect.
FULL = "modelled-full"
#: The clauses cover only PART of the printed effect.
#:
#: This used to mean *"MODELLED as far as §3b is concerned"* — the seam had no `clauses_cover` gate,
#: so a partial set priced as a complete one and the uncovered leg differenced to exactly 0. Issue
#: #300 declared the verdict and **Issue #299 wired it**: a partial set now reaches `fate` as
#: `clauses_cover=False`, which fails closed, so these sites are REFUSED (or engine-route candidates)
#: rather than MODELLED. The class survives the ruling because it names WORK — complete the clause
#: set — that is distinct from "no compendium entry at all". The WIRE VALUE survives unrenamed for
#: the same reason `apply_option.ENGINE_ROUTE_KINDS` does: it is the report's stable row identity,
#: printed in four committed tables, in the `### MODELLED-PARTIAL` heading `_partial_rows` splits on,
#: and quoted by three queued sibling issues (Issue #302 / #303 / #304). Renaming it silently would
#: move all of those; the honest alternative taken here is to say plainly, at the definition and
#: directly under the heading, that these no longer resolve to MODELLED — and to print each row's
#: actual `fate` beside it so no reader has to infer it from the label.
PARTIAL = "modelled-partial"

#: REFUSED causes, per the issue's grouping. Each has a different fix, which is the whole point of
#: grouping by cause rather than by card.
GAP = "clause-vocabulary gap"          # (a) fixable by modelling work
OPP_CHOICE = "opponent choice"         # (b) accepted POC unknown — no opponent model
OPP_HIDDEN = "opponent hidden zone"    # (b') their hand / deck / prizes — same accepted unknown
NONDET = "not provably deterministic"  # (c) the engine route's fail-closed gate

# ── text markers ──────────────────────────────────────────────────────────────────────────────────
# Fail-CLOSED by construction (ADR-0067's yield convention): these decide only that an effect
# CANNOT be proved deterministic. Absence of a marker is never itself a proof — it makes a site an
# ENGINE-RESOLVED *candidate*, and the report says so rather than claiming the proof.
#
# Apostrophes in the engine's text are U+2019, so every pattern that would span one uses `.`.

_RNG_OR_HIDDEN = tuple(re.compile(p, re.I) for p in (
    r"\bshuffle",                       # deck ORDER — `snapshot_coverage`'s one HIDDEN zone
    r"\bsearch your deck", r"\bfrom your deck", r"\bfrom their deck",
    r"\blook at the (top|bottom)", r"\breveal the top",
    r"\bflip a coin", r"\bat random",
    r"\bdraws? ",                       # a draw reads the top of a hidden deck
    r"\bdraw \d", r"\bdraw a card", r"\bdraw cards",
    r"\bprize card",                    # prizes are face-down
    r"\b(top|bottom) of (your|their) deck",
))

_OPPONENT_CHOICE = tuple(re.compile(p, re.I) for p in (
    r"your opponent chooses", r"ask your opponent", r"your opponent discards",
    r"each player discards", r"your opponent may", r"your opponent shuffles",
    r"your opponent counts", r"your opponent puts", r"if (yes|no)\b",
))

_OPPONENT_HIDDEN = tuple(re.compile(p, re.I) for p in (
    r"opponent.s hand", r"reveals their hand", r"cards in their hand",
    r"opponent.s deck", r"opponent.s Prize",
))

#: **Effect families**, in resolution order, and whether the *existing* Effect-Clause vocabulary
#: (`snapshot_coverage.CLAUSE_WRITES` keys: accel / coin / draw / energy_provide / energy_recur /
#: fetch / heal) can already express the family.
#:
#: This is what turns "91 sites are a clause-vocabulary gap" into a schedulable number: a gap in an
#: EXPRESSIBLE family is a compendium ENTRY — the builder already knows the shape — while a gap in a
#: NEW-VOCABULARY family needs a clause kind, a write-set in `CLAUSE_WRITES`, and a transition in
#: T4. The two cost wildly different amounts, so the report must not report them as one pile.
#:
#: Ordered because cards compose: *Surfer* switches AND draws, and the switch is why it is played, so
#: the switch family must match first. Order therefore runs new-vocabulary families ahead of the
#: expressible ones — the honest direction, since a card is only fully expressible if NO leg of it
#: needs new vocabulary.
_FAMILIES: tuple[tuple[str, bool, object], ...] = (
    ("gust — pull a benched opponent body Active", False,
     re.compile(r"switch in 1 of your opponent.s benched", re.I)),
    ("energy denial — remove Energy from their body", False,
     re.compile(r"discard (an|a|all) (special )?energy from", re.I)),
    ("tool / special-energy removal", False,
     re.compile(r"pok.mon tools?.{0,60}discard|discard .{0,40}pok.mon tool", re.I | re.S)),
    ("Stadium removal", False, re.compile(r"discard a stadium", re.I)),
    ("evolution shortcut (Rare Candy)", False, re.compile(r"skipping the stage 1", re.I)),
    ("recover discard -> DECK (not to hand)", False,
     re.compile(r"shuffle up to \d+ .* from your discard pile into your deck", re.I)),
    ("damage counters placed or moved", False,
     re.compile(r"damage counters? (on|from)", re.I)),
    ("transient damage grant (this turn)", False,
     re.compile(r"during this turn.*more damage", re.I | re.S)),
    ("energy moved between my bodies", False,
     re.compile(r"\bmove\s+.{0,24}?energy from", re.I)),
    ("switch my own Active", False,
     re.compile(r"switch your active pok.mon|switch it with your active pok.mon", re.I)),
    ("devolve", False, re.compile(r"\bdevolve\b", re.I)),
    ("prize manipulation", False, re.compile(r"prize card", re.I)),
    ("hand disruption — their hand", False,
     re.compile(r"(their|opponent.s) hand", re.I)),
    ("energy attach / acceleration", True,
     re.compile(r"attach (a|an|up to \d+|any number of).*energy", re.I)),
    ("heal", True, re.compile(r"\bheal\b", re.I)),
    ("fetch / search / recover", True,
     re.compile(r"(search your deck|look at the (top|bottom)|from your discard pile into your hand"
                r"|put .* from your discard pile)", re.I)),
    ("draw", True, re.compile(r"\bdraw\b", re.I)),
)

#: An Ability the player ACTIVATES — it appears on the MAIN menu as an `_ABILITY` option. Both
#: Abilities ever observed in the 372-frame corpus (Drakloak's Recon Directive, Lunatone's Lunar
#: Cycle) match the first pattern.
_ACTIVATED = tuple(re.compile(p, re.I) for p in (
    r"once during your turn", r"as often as you like during your turn",
    r"during your turn, you may", r"once during your first turn",
))

#: An Ability that rides the `_PLAY` / `_EVOLVE` option instead of posing its own — its effect is
#: part of that option's transition, so it is what makes an otherwise-structural deploy or evolve
#: carry a card effect.
_ON_PLAY = re.compile(r"when you play this Pok.mon from your hand", re.I)
_ON_EVOLVE = re.compile(r"from your hand to evolve", re.I)


# ── the clause-coverage ruling, read from the compendium ──────────────────────────────────────────

#: The compendium's verdict vocabulary -> this report's MODELLED split. One map rather than a
#: cascade, keyed off `snapshot_coverage`'s own constants so a third verdict cannot be silently
#: dropped on the floor here — it simply has no report class, and :func:`validate` says so.
_VERDICT_CLASS: dict[str, str] = {
    snapshot_coverage.COVERS_FULL: FULL,
    snapshot_coverage.COVERS_PARTIAL: PARTIAL,
}


def _covers_class(entry) -> tuple[str, str] | None:
    """One card's compendium verdict as ``(report class, what the clauses carry or miss)``.

    `None` when the card carries no verdict at all — which :func:`validate` refuses to run on rather
    than defaulting either way, because defaulting would fabricate the report's most important
    column. The verdict itself lives in `card_effects.json`; see this module's header for why it is
    not duplicated here."""
    report_class = _VERDICT_CLASS.get((entry or {}).get("covers"))
    if report_class is None:
        return None
    return report_class, str(entry.get("reason", "")).strip()


# ── loading ───────────────────────────────────────────────────────────────────────────────────────

def load_cards(path: Path = CARDS_JSON) -> dict[int, dict]:
    return {int(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def load_effects(path: Path = EFFECTS_JSON) -> dict[int, list[dict]]:
    return snapshot_coverage.clause_lists(json.loads(path.read_text(encoding="utf-8")))


def load_covers(path: Path = EFFECTS_JSON) -> dict[int, dict]:
    """``{card id: {covers, reason}}`` — the compendium's completeness verdicts, the report's
    MODELLED split. Same file as :func:`load_effects`, one store."""
    return snapshot_coverage.covers_table(json.loads(path.read_text(encoding="utf-8")))


def load_our_decks(agents_dir: Path = AGENTS_DIR) -> dict[str, collections.Counter]:
    """``{agent: Counter(card id -> copies)}`` from each shipped `deck.csv` (one card id per line)."""
    out: dict[str, collections.Counter] = {}
    for p in sorted(agents_dir.glob("*/deck.csv")):
        ids = [int(t) for t in p.read_text(encoding="utf-8").split() if t.strip()]
        out[p.parent.name] = collections.Counter(ids)
    return out


def load_opponent_builds(path: Path = ARTIFACT_JSON) -> tuple[dict[str, collections.Counter],
                                                              dict[str, float]]:
    """``({archetype: Counter}, {archetype: meta prior})`` from the scouting artifact.

    The prior is the artifact's own recency-weighted meta share, so opponent exposure can be
    expressed as *copies in the average deck we will actually face* rather than as an unweighted sum
    over 122 archetypes most of which are noise."""
    art = json.loads(path.read_text(encoding="utf-8"))
    builds, priors = {}, {}
    for name, dossier in art["dossiers"].items():
        build = dossier.get("representative_build") or []
        if not build:
            continue
        builds[name] = collections.Counter(int(c) for c in build)
        priors[name] = float(art.get("priors", {}).get(name, 0.0))
    return builds, priors


# ── site derivation ───────────────────────────────────────────────────────────────────────────────

class Site:
    """One (card, option kind, effect) the apply-seam will be asked to price."""

    __slots__ = ("card_id", "name", "category", "kind", "label", "text", "clauses",
                 "fate", "report_class", "cause", "note", "family", "expressible")

    def __init__(self, card_id, name, category, kind, label, text, clauses):
        self.card_id, self.name, self.category = card_id, name, category
        self.kind, self.label, self.text, self.clauses = kind, label, text, clauses
        self.fate = self.report_class = self.cause = self.note = ""
        self.family, self.expressible = "", False

    @property
    def has_effect(self) -> bool:
        return bool((self.text or "").strip())

    def as_row(self) -> dict:
        return {"card_id": self.card_id, "name": self.name, "category": self.category,
                "kind": self.kind, "site": self.label, "fate": self.fate,
                "class": self.report_class, "cause": self.cause, "note": self.note,
                "family": self.family, "expressible": self.expressible,
                "clauses": self.clauses}


def _ability_mode(text: str) -> str:
    """``activated`` (poses an `_ABILITY` option) / ``on_play`` / ``on_evolve`` (rides that option) /
    ``passive`` (poses no option at all).

    Order matters: Noctowl's Jewel Seeker opens *"Once during your turn, when you play this Pokemon
    from your hand to evolve…"*, and it is the on-evolve trigger that decides where the effect lands,
    not the once-per-turn cap.

    That a rider RIDES is measured, not assumed (**Issue #305**, the report's AMBIGUOUS #3). The
    engine resolves a triggered Ability inside the `_PLAY` / `_EVOLVE` that played the card — a
    `SelectType.YES_NO` / `SelectContext.ACTIVATE` gate naming the card in `contextCard`, then the
    effect's own selects, then MAIN — and poses **no** `OptionType.ABILITY` at any point, including
    on later menus after the gate was DECLINED. Evidence:
    `tests/fixtures/triggered_ability_selects.json` (captured by
    `tools/meta_tracker/probe_triggered_ability.py`), re-driven against the live engine every run by
    `tests/strategy/test_triggered_ability_shape.py`. So these sites stay `_PLAY` / `_EVOLVE` and are
    NOT engine-route eligible under the current kind table."""
    if _ON_EVOLVE.search(text):
        return "on_evolve"
    if _ON_PLAY.search(text):
        return "on_play"
    if any(p.search(text) for p in _ACTIVATED):
        return "activated"
    return "passive"


def _clauses_for(clauses: list[dict], where: str) -> list[dict]:
    """The subset of a card's clauses belonging to one site.

    Routed by the clause's own ``trigger``: `on_evolve` / `on_bench_play` ride the evolve and deploy
    options, `on_attack` belongs to a TERMINAL attack and is no site's, and an untriggered clause on
    a Pokemon is its activated Ability's.

    `on_attach` (Issue #301, Telepath Psychic Energy) needs no branch and deliberately has none: the
    only cards that can carry it are Special Energy, whose sole site IS the `_ATTACH` this function
    is asked for under ``where="activated"``. Giving it a branch would mean inventing a fourth home
    for a trigger that already lands on the one option it can ride."""
    def home(c: dict) -> str:
        trigger = c.get("trigger")
        if trigger == "on_evolve":
            return "on_evolve"
        if trigger == "on_bench_play":
            return "on_play"
        if trigger == "on_attack":
            return "attack"
        return "activated"
    return [c for c in clauses if home(c) == where]


def sites_for(card_id: int, card: dict, clauses: list[dict]) -> tuple[list[Site], dict]:
    """Every apply-seam site on one card, plus the counts of what deliberately is NOT one."""
    cat = card.get("category")
    name = card.get("name", "?")
    aside = {"passive_abilities": 0, "attacks": len(card.get("attacks") or [])}
    out: list[Site] = []

    def mk(kind, label, text, cl):
        out.append(Site(card_id, name, cat, kind, label, text, cl))

    if cat == "basic_energy":
        mk(_ATTACH, "attach", "", [])
        return out, aside
    if cat == "special_energy":
        mk(_ATTACH, "attach", _text(card), _clauses_for(clauses, "activated"))
        return out, aside
    if cat == "tool":
        # Attaching a Tool writes `attached_tools` (homed) and nothing else; the Tool's ongoing
        # effect is a STATIC modifier the stat provider parses (hpBonus / retreatReduction /
        # damageBoost) and `state_value` reads off the body, never a transition this seam applies.
        mk(_ATTACH, "attach", "", [])
        return out, aside
    if cat in ("item", "supporter", "stadium"):
        mk(_PLAY, "play", _text(card), _clauses_for(clauses, "activated"))
        return out, aside
    if cat != "pokemon":
        return out, aside

    stage = card.get("stage")
    modes = [(_ability_mode(a.get("text") or ""), a) for a in (card.get("abilities") or [])]
    riders = {m: a for m, a in modes if m in ("on_play", "on_evolve")}
    aside["passive_abilities"] = sum(1 for m, _ in modes if m == "passive")

    if stage == "basic":
        rider = riders.get("on_play")
        mk(_PLAY, "deploy", (rider or {}).get("text", ""), _clauses_for(clauses, "on_play"))
    else:
        rider = riders.get("on_evolve")
        mk(_EVOLVE, "evolve", (rider or {}).get("text", ""), _clauses_for(clauses, "on_evolve"))
    for mode, ability in modes:
        if mode == "activated":
            mk(_ABILITY, f"ability: {(ability.get('name') or '').strip()}",
               ability.get("text") or "", _clauses_for(clauses, "activated"))
    return out, aside


def _text(card: dict) -> str:
    """A Trainer's or Special Energy's printed effect — the engine files it under ``abilities``."""
    return " ".join(" ".join((a.get("text") or "").split())
                    for a in (card.get("abilities") or [])).strip()


# ── fate resolution ───────────────────────────────────────────────────────────────────────────────

def _hits(text: str, patterns) -> bool:
    return any(p.search(text or "") for p in patterns)


def family(site: "Site") -> tuple[str, bool]:
    """``(effect family, is it expressible in the EXISTING clause vocabulary?)``.

    Falls back on the card's own category rather than on a catch-all, so a Stadium whose text matches
    no family reads as *Stadium static board modifier* — which is the truthful answer, and a
    new-vocabulary one — instead of vanishing into "other"."""
    for name, expressible, pattern in _FAMILIES:
        if pattern.search(site.text or ""):
            return name, expressible
    if site.category == "stadium":
        return "Stadium static board modifier", False
    if site.category == "special_energy":
        return "Special Energy static provision + rider", False
    return "unclassified", False


def refusal_cause(text: str, *, rng_refuses: bool) -> str:
    """The cause a refusal on ``text`` should carry, or ``""`` when nothing in it refuses.

    One cascade, called from both refusal branches of :func:`resolve`, so the two can never drift on
    what counts as opponent choice. ``rng_refuses`` is the one real difference between them: the
    ENGINE-RESOLVED gate is a determinism PROOF and any RNG marker defeats it, while a closed-form
    transition on a MODELLED kind prices the shuffle as a `deck_odds` distribution and is untroubled
    by it.

    Order is a precedence: opponent JUDGEMENT outranks opponent HIDDEN state (a card that reads
    their hand *and* lets them choose is refused for the choice, the harder unknown), and both
    outrank mere RNG."""
    if _hits(text, _OPPONENT_CHOICE):
        return OPP_CHOICE
    if _hits(text, _OPPONENT_HIDDEN):
        return OPP_HIDDEN
    if rng_refuses and _hits(text, _RNG_OR_HIDDEN):
        return NONDET
    return ""


#: Stands in for a live `_search_api` when this census asks the seam for a fate. The census measures
#: *"which fate would this option reach if the caller wired an engine and could prove determinism?"*,
#: which is why ENGINE-RESOLVED here is an upper bound — see the report's Method section.
_ENGINE_SEAM = object()


def clauses_cover(site: Site, covers: dict[int, dict]) -> bool | None:
    """The tri-state `apply_option.fate` takes for ``clauses_cover``, for one site.

    This is the one place the census **extends** the seam rather than mirroring it, and the extension
    is the per-OPTION judgement `fate` explicitly leaves to its caller: `None` from
    `CardEffects.clauses_cover` means *absence of a compendium entry*, which covers both **"this
    option has no printed effect at all"** (structural — a vanilla Basic's deploy, a Basic Energy
    attach) and **"this card HAS an effect and nothing models it"**. Those two must not resolve alike:
    the first is MODELLED by construction, the second is precisely the coverage gap this report
    exists to count. The census can tell them apart because it holds the card's effect text, so it
    answers `None` only for the structural case and `False` for the uncovered one.

    `True` / `False` for a card that IS ruled come straight from the compendium's `_covers` verdict —
    one store (see this module's header), never a second copy of the ruling."""
    if not site.has_effect:
        return None
    judged = _covers_class(covers.get(site.card_id)) if site.clauses else None
    if judged is None:
        return False
    return judged[0] == FULL


def resolve(site: Site, covers: dict[int, dict]) -> Site:
    """Resolve one site to a §3b fate plus a reported class and, when refused, a cause.

    **Calls `apply_option.fate` rather than re-deriving it** (Issue #299). It could not before: the
    fate was a kind-table lookup plus an engine gate on two inputs nothing produces today, so a
    literal call answered REFUSED for every engine-route option and the census had to mirror the
    logic by hand. Now that `fate` takes the per-option `clauses_cover`, the census supplies the two
    judgements it is entitled to make and asks the seam for the answer — so the two cannot drift, and
    the report cannot claim a fate the seam would not return.

    The two supplied judgements, both fail-CLOSED (ADR-0067's yield convention):

    * ``clauses_cover`` — :func:`clauses_cover` above.
    * ``deterministic`` — judged from the printed text: any shuffle, deck read, coin, reveal, prize
      or opponent-judgement marker means *not proved*. **Absence of a marker is not a proof**, which
      is why ENGINE-RESOLVED in this report means *eligible and candidate-deterministic* — an upper
      bound, and every table that carries it says so.

    ``covers`` is the compendium's own verdict block (:func:`load_covers`) — passed in rather than
    read here, so this stays pure and the report cannot consult a different store than the seam.
    """
    how = seam.coverage(site.kind)
    judged = _covers_class(covers.get(site.card_id)) if site.clauses else None
    blocked = refusal_cause(site.text, rng_refuses=True)

    site.fate = seam.fate({"type": site.kind}, depth=0, search_api=_ENGINE_SEAM,
                          deterministic=not blocked, clauses_cover=clauses_cover(site, covers))

    if site.fate == seam.MODELLED:
        site.report_class = FULL
        site.note = judged[1] if judged else (
            "structural: the transition is the same shape for every card of the kind")
        return site

    # A PARTIAL clause set keeps its own report row whatever fate it now reaches. The fate moved in
    # Issue #299 — a partial set is `clauses_cover=False`, so it no longer prices as a complete one —
    # but the WORK it names did not: complete the clauses. Reporting it as an undifferentiated
    # refusal would merge it with cards that have no compendium entry at all, and those are a
    # different backlog. The `fate` column beside it carries where it actually landed.
    partial = bool(judged) and judged[0] == PARTIAL
    site.report_class = PARTIAL if partial else site.fate
    if partial:
        site.note = judged[1]

    if site.fate == seam.REFUSED:
        # RNG counts against the ENGINE route (a determinism PROOF) but NOT against a closed-form
        # transition on a MODELLED kind, where a shuffle prices as a `deck_odds` distribution and §3
        # already says a search-reveal returns an `Expectation`. So the same text is a vocabulary gap
        # on `_PLAY` and a structural nondeterminism refusal on `_ABILITY`.
        site.cause = refusal_cause(site.text, rng_refuses=how != seam.MODELLED) or GAP
    return site


# ── Tool static-effect readback ──────────────────────────────────────────────────────────────────

class _SkillShim:
    """The `.skills` duck-type the stat-provider parsers read, over a `cards.json` record.

    The parsers take the engine's `CardData`; `cards.json` IS that data, dumped. Shimming it keeps
    the Tool measurement on the SAME parsers the Pilot ships, so this report cannot claim a Tool is
    readable that the agent then cannot read."""

    class _Skill:
        # An OBJECT with `.text`, not a dict: `parse_card_damage_boost` reads the attribute
        # directly while the Tool parsers accept either, and a dict would silently score every
        # Tool's damage boost as 0.
        def __init__(self, text: str):
            self.text = text

    def __init__(self, card: dict):
        self.skills = [self._Skill(a.get("text") or "") for a in (card.get("abilities") or [])]


#: Tools whose printed effect is DELIBERATELY not modelled, with the reason. Per "no silent caps",
#: a group that reads as covered when it is not is worse than one that reads as missing — so these
#: are named in the report rather than left to sit in the same "**none**" bucket as an oversight.
#: Ruled at Issue #306; each needs a `state_value` shape that does not exist, not a parser fix.
#:
#: **Brave Bangle (1175) was here and is not any more** (Issue #345). Its entry read *"GATED on a
#: holder predicate we cannot decide — … `CardStat` models `ex`/`megaEx` but not Radiant, so a
#: no-Rule-Box test would fail OPEN and over-credit."* That is a claim about the POOL, and it was
#: never measured against it: a sweep of all 1061 Pokémon bodies finds no Radiant, V, VMAX, VSTAR or
#: V-UNION card, so *"has a Rule Box"* and `CardStat.is_ex_body` are the same 151 bodies — exact,
#: not fail-open. The gate now lives in `CardStat.holderNoRuleBox` and the sweep is a test
#: (`tests/scouting/test_tool_holder_facts.py`) that fails the day the pool gains one.
DELIBERATELY_UNMODELLED_TOOLS = {
    1156: "REACTIVE — draws 2 when the holder is damaged in the Active Spot",
    1161: "REACTIVE — moves an Energy off the attacker when the holder is damaged",
    1167: "REACTIVE — 12 counters onto the attacker when the holder is damaged",
    1163: "REACTIVE — end-of-turn Energy from discard while the holder is Active",
    1172: "REACTIVE — the opponent takes 1 fewer Prize for KOing the holder",
    1180: "EXOTIC — grants an attack printed on the Tool itself, to one named body",
}

#: Why the whole group stays out. Pricing *"when this body is attacked, X happens"* needs a term
#: that values a CONDITIONAL FUTURE event on a body — a `state_value` design question adjacent to
#: Issue #278's survival work, not a `card_text` gap. Inventing a `CardStat` shape for it here would
#: be guessing at the term that has to consume it.
UNMODELLED_TOOLS_REASON = (
    "a term that prices a conditional FUTURE event on a body, which `state_value` has no shape for "
    "(adjacent to Issue #278's survival work) — a design question, not a parser gap")


def tool_static_reads(card: dict) -> list[str]:
    """Which CardStat fields the shipped parsers actually recover from a Tool's printed text.

    Empty means the Tool attaches, writes `attached_tools`, and moves NO term of `state_value` — so
    under 1-ply differencing it prices at ~0 and sorts to the bottom of the menu.

    A field is listed when it is RECOVERED, which is not the same as PRICED: `attackCostReduction`
    (Issue #306) is parsed and has no live consumer yet — see the report's tool verdict, which says
    so rather than letting the row read as covered."""
    c = _SkillShim(card)
    got = []
    if _parse_tool_hp_bonus(c):
        got.append("hpBonus")
    rr = _parse_tool_retreat_reduction(c)
    if rr:
        # SIGNED. Rendered with the sign when negative so a surcharge Tool (Gravity Gemstone) can
        # never be skim-read off this table as a benefit recovered.
        got.append("retreatReduction" if rr > 0 else f"retreatReduction ({rr})")
    if _parse_tool_attack_cost_reduction(c):
        got.append("attackCostReduction")
    if _parse_tool_retreat_free_at_hp(c):
        got.append("retreatFreeAtHp")
    if _parse_retreat_free_grant(c):
        got.append("retreatFreeGrant")
    if parse_card_damage_boost(c)[0]:
        got.append("damageBoost")
    fam = _parse_tool_holder_family(c)
    if fam and got:
        got.append(f"holderNameFamily ({fam})")
    # The second holder gate (Issue #345), reported on the same terms as the family: a gate is only
    # meaningful next to an amount it gates, so it is listed only when something else was recovered.
    if _parse_tool_holder_no_rule_box(c) and got:
        got.append("holderNoRuleBox")
    return got

# ── exposure ──────────────────────────────────────────────────────────────────────────────────────

def our_copies(decks: dict[str, collections.Counter]) -> collections.Counter:
    total = collections.Counter()
    for counter in decks.values():
        total.update(counter)
    return total


def meta_copies(builds: dict[str, collections.Counter], priors: dict[str, float]) -> dict[int, float]:
    """``{card id: expected copies in the deck across the table}`` — each archetype's representative
    build weighted by its meta prior, renormalised over the archetypes that have a build.

    Unweighted copy counts over 122 archetypes would let 100 one-off brews outvote the field."""
    mass = sum(priors.get(a, 0.0) for a in builds) or 1.0
    out: dict[int, float] = collections.defaultdict(float)
    for arch, counter in builds.items():
        w = priors.get(arch, 0.0) / mass
        for cid, n in counter.items():
            out[cid] += w * n
    return dict(out)


# ── report assembly ───────────────────────────────────────────────────────────────────────────────

def validate(pool: set[int], cards: dict[int, dict], effects: dict[int, list[dict]],
             covers: dict[int, dict]) -> list[str]:
    """Every way this census is not entitled to run. Empty is the contract."""
    problems = []
    for cid in sorted(pool):
        if cid not in cards:
            problems.append(f"card {cid} is in a deck but not in cards.json")
        elif cid in effects and _covers_class(covers.get(cid)) is None:
            problems.append(f"card {cid} ({cards[cid]['name']}) has Effect Clauses but no "
                            f"`{snapshot_coverage.COVERS_KEY}` verdict in card_effects.json — "
                            f"defaulting would fabricate the report's most important column. "
                            f"Author it in tools/meta_tracker/effect_overrides.json")
    for kind in sorted(seam.KIND_COVERAGE):
        if seam.KIND_COVERAGE[kind] not in (seam.MODELLED, seam.ENGINE_RESOLVED, seam.TERMINAL,
                                            seam.REFUSED):
            problems.append(f"kind {kind}: unexpected coverage class")
    return problems


def census(pool: set[int], cards, effects, covers) -> tuple[list[Site], dict]:
    sites: list[Site] = []
    aside = collections.Counter()
    for cid in sorted(pool):
        card = cards[cid]
        card_sites, extra = sites_for(cid, card, effects.get(cid, []))
        for s in card_sites:
            resolve(s, covers)
            s.family, s.expressible = family(s)
            sites.append(s)
        aside.update(extra)
    return sites, dict(aside)


def load_strategy_names(agents_dir: Path = AGENTS_DIR) -> dict[str, str]:
    """``{agent: STRATEGY.md text}`` for the decks that have an authored doctrine.

    Used only to flag *win-plan critical path* exposure: a card the deck's own doctrine names is a
    card the agent is supposed to be building around, so a refusal on it is not a tail risk."""
    out = {}
    for p in sorted(agents_dir.glob("*/STRATEGY.md")):
        out[p.parent.name] = p.read_text(encoding="utf-8")
    return out


def on_win_plan(site: Site, decks, strategies) -> list[str]:
    """Decks whose authored doctrine names this card by name."""
    def norm(s: str) -> str:
        return s.replace("’", "'").replace("‘", "'")
    stem = norm(site.name).split(" ex")[0]
    return sorted(agent for agent, text in strategies.items()
                  if site.card_id in decks.get(agent, {}) and stem in norm(text))


def _pct(n: float, d: float) -> str:
    return f"{(100.0 * n / d):.1f}%" if d else "—"


def _table(rows: list[list[str]], header: list[str]) -> str:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def build_report(sites: list[Site], aside: dict, ours: collections.Counter,
                 meta: dict[int, float], decks: dict[str, collections.Counter],
                 n_archetypes: int, strategies: dict[str, str],
                 cards_by_id: dict[int, dict]) -> str:
    """The report's DATA sections. The verdict prose lives in `apply-seam-coverage.md`."""
    L: list[str] = []
    add = L.append
    # Derived, never spelled: a sixth agent deck landed on main (`hydrapple`) and every table header
    # reading "our 5 decks" became a lie the moment it did.
    n_decks = len(decks)

    # Name and predicate agree, and the invariant that used to be an `or` clause is asserted
    # instead: a site with no card effect is structural, and structural is MODELLED-FULL by
    # construction. If that ever stops holding, the headline must be re-derived, not quietly widened.
    effect_bearing = [s for s in sites if s.has_effect]
    stray = [s for s in sites if not s.has_effect and s.report_class != FULL]
    if stray:
        raise AssertionError(
            "effect-free sites that are not MODELLED-FULL: %s — the 'effect-bearing only' headline "
            "would silently omit them" % sorted({(s.card_id, s.report_class) for s in stray}))
    by_fate = collections.Counter(s.fate for s in sites)
    by_class = collections.Counter(s.report_class for s in sites)
    eff_fate = collections.Counter(s.fate for s in effect_bearing)
    eff_class = collections.Counter(s.report_class for s in effect_bearing)

    # Each card's WORST site — the per-CARD view several sections below need, computed once.
    worst_rank = {seam.REFUSED: 0, PARTIAL: 1, seam.ENGINE_RESOLVED: 2, FULL: 3}
    worst: dict[int, str] = {}
    for s in sites:
        cur = worst.get(s.card_id)
        if cur is None or worst_rank[s.report_class] < worst_rank[cur]:
            worst[s.card_id] = s.report_class

    def wsum(pred, weight) -> float:
        return sum(weight.get(s.card_id, 0) for s in sites if pred(s))

    add("<!-- GENERATED by tools/apply_seam_coverage.py — do not hand-edit this section. -->")
    add("")
    add(f"Pool: **{len({s.card_id for s in sites})} distinct cards** — "
        f"{len(decks)} shipped agent decks (`src/agents/*/deck.csv`) plus {n_archetypes} scouting "
        f"archetypes' representative builds. **{len(sites)} apply-seam sites**; "
        f"{aside.get('attacks', 0)} attacks are TERMINAL and {aside.get('passive_abilities', 0)} "
        f"Abilities are passive, so neither is a site.")
    add("")

    add("### Headline — every site")
    add("")
    add("**`engine-resolved` here means *eligible and candidate-deterministic*, not a fate a live "
        "call would return.** `apply_option.fate` refuses unless the caller passes BOTH "
        "`deterministic=True` (a per-option proof nothing produces yet) and a `search_api`, so under "
        "the merged seam as invoked today these refuse too. They are broken out because the work "
        "that would promote them is a determinism PROOF, not a clause kind — a different backlog "
        "from the refusals below.")
    add("")
    add("**Issue #299's ruling is live in these numbers.** The engine route is no longer gated by "
        "`ENGINE_ROUTE_KINDS`; it is open per-option to every declared non-terminal kind, and a "
        "COMPLETE clause set now resolves MODELLED whatever the kind table says. Two movements "
        "follow, in opposite directions, and both are the ruling working as intended: every "
        "deterministic-shaped refusal on a MODELLED kind became an engine-route candidate, and every "
        "PARTIAL clause set stopped counting as MODELLED — `clauses_cover=False` fails closed, which "
        "is the entire reason Issue #300 declared the verdict.")
    add("")
    rows = []
    for fate in (seam.MODELLED, seam.ENGINE_RESOLVED, seam.REFUSED):
        n = by_fate.get(fate, 0)
        rows.append([f"**{fate}**", n, _pct(n, len(sites)),
                     f"{wsum(lambda s, f=fate: s.fate == f, ours)}",
                     _pct(wsum(lambda s, f=fate: s.fate == f, ours), sum(ours.values())),
                     f"{wsum(lambda s, f=fate: s.fate == f, meta):.1f}"])
    add(_table(rows, ["fate", "sites", "% sites", f"copies in our {n_decks} decks", "% our copies",
                      "meta-weighted copies"]))
    add("")
    add("The clause-completeness split — and since Issue #299 the seam **does** tell the two apart, "
        "which is why `modelled-partial` no longer sits inside `modelled` above. A partial set is "
        "`clauses_cover=False`, so it refuses (or takes the engine route) instead of pricing its "
        "uncovered leg at 0:")
    add("")
    add(_table([[f"**{c}**", by_class.get(c, 0), _pct(by_class.get(c, 0), len(sites)),
                 ", ".join(f"{f} {n}" for f, n in sorted(
                     collections.Counter(s.fate for s in sites
                                         if s.report_class == c).items()))]
                for c in (FULL, PARTIAL)], ["class", "sites", "% sites", "fate now"]))
    add("")

    add("The copy columns above sum over SITES, so a card with two of them (a Pokemon that both "
        "evolves and poses an Ability) contributes its copies twice. The copy-weighted question a "
        "deck author actually asks is per CARD — *of the 60 cards I shuffle, how many will the seam "
        "price correctly when I draw them?* — so that answer takes each card's WORST site:")
    add("")
    rows = []
    for cls in (FULL, seam.ENGINE_RESOLVED, PARTIAL, seam.REFUSED):
        n_cards = sum(1 for c in worst.values() if c == cls)
        n_ours = sum(n for cid, n in ours.items() if worst.get(cid) == cls)
        n_meta = sum(v for cid, v in meta.items() if worst.get(cid) == cls)
        rows.append([f"**{cls}**", n_cards, _pct(n_cards, len(worst)), n_ours,
                     _pct(n_ours, sum(ours.values())), f"{n_meta:.1f}",
                     _pct(n_meta, sum(meta.values()))])
    add(_table(rows, ["worst site on the card", "cards", "% cards", f"copies in our {n_decks} decks",
                      "% our copies", "meta copies", "% meta copies"]))
    add("")

    add("### Headline — effect-bearing sites only")
    add("")
    add("A vanilla Basic's deploy and a Basic Energy attach are structural: they carry no card "
        "effect, so counting them inflates MODELLED with sites that were never at risk. This is the "
        "number that answers *how much of the card POOL's text is reachable*.")
    add("")
    rows = []
    for fate in (seam.MODELLED, seam.ENGINE_RESOLVED, seam.REFUSED):
        n = eff_fate.get(fate, 0)
        rows.append([f"**{fate}**", n, _pct(n, len(effect_bearing))])
    add(_table(rows, ["fate", "sites", "% effect-bearing sites"]))
    add("")
    add(_table([[f"**{c}**", eff_class.get(c, 0), _pct(eff_class.get(c, 0), len(effect_bearing))]
                for c in (FULL, PARTIAL)],
               ["clause-completeness split", "sites", "% effect-bearing sites"]))
    add("")

    add("### REFUSED, grouped by cause and ranked by exposure")
    add("")
    refused = [s for s in sites if s.fate == seam.REFUSED]
    for cause in (GAP, OPP_CHOICE, OPP_HIDDEN, NONDET):
        group = sorted((s for s in refused if s.cause == cause),
                       key=lambda s: (-ours.get(s.card_id, 0), -meta.get(s.card_id, 0.0), s.name))
        if not group:
            continue
        n_ours = sum(ours.get(s.card_id, 0) for s in group)
        add(f"#### {cause} — {len(group)} sites, {n_ours} copies across our {n_decks} decks")
        add("")
        add(_table([[s.card_id, s.name, s.label, ours.get(s.card_id, 0),
                     f"{meta.get(s.card_id, 0.0):.2f}", s.family,
                     "yes" if not _hits(s.text, _RNG_OR_HIDDEN) else "",
                     s.note or ""]
                    for s in group],
                   ["id", "card", "site", "our copies", "meta copies", "effect family",
                    "deterministic-shaped", "note"]))
        add("")

    add("### The clause-vocabulary gap, split by effect family")
    add("")
    add("An EXPRESSIBLE gap is a compendium ENTRY — the clause kind exists and the builder already "
        "knows the shape. A NEW-VOCABULARY gap needs a clause kind, a write-set in "
        "`snapshot_coverage.CLAUSE_WRITES`, and a transition in T4. Reporting them as one pile "
        "would put a day of work and a quarter of it in the same number.")
    add("")
    add("**Since Issue #299 this table also counts the MODELLED-PARTIAL sites**, because a partial "
        "clause set now refuses rather than pricing as a complete one — so `fetch` and `draw` rows "
        "here are larger than they were pre-ruling, and the growth is cards whose clauses exist but "
        "are incomplete, not cards with no entry at all. The MODELLED-PARTIAL section below names "
        "them individually with the leg each one misses.")
    add("")
    gap = [s for s in refused if s.cause == GAP]
    fam = collections.defaultdict(lambda: [0, 0, 0.0, False])
    for s in gap:
        row = fam[s.family]
        row[0] += 1
        row[1] += ours.get(s.card_id, 0)
        row[2] += meta.get(s.card_id, 0.0)
        row[3] = s.expressible
    rows = sorted(([k, "existing" if v[3] else "**NEW**", v[0], v[1], f"{v[2]:.2f}"]
                   for k, v in fam.items()), key=lambda r: (-r[3], -float(r[4])))
    add(_table(rows, ["effect family", "clause vocabulary", "sites", "our copies", "meta copies"]))
    add("")
    det = [s for s in gap if not _hits(s.text, _RNG_OR_HIDDEN)]
    rng = [s for s in gap if _hits(s.text, _RNG_OR_HIDDEN)]
    add("**The gap splits again on RNG, and the split matters because the two have different "
        "fixes.** §3b names shuffle-riding as a structural refusal — but that argument is about "
        "the ENGINE route (no deal-seed, so a sim is one sample). On a MODELLED kind a shuffle is "
        "not a refusal at all: deck ORDER is `snapshot_coverage`'s one HIDDEN zone, priced as a "
        "distribution by `deck_odds`, and §3 already says a search-reveal returns an `Expectation`. "
        "So an RNG-shaped card on a MODELLED kind is still a VOCABULARY gap — it just costs an "
        "Expectation node rather than a scalar transition.")
    add("")
    add(_table([
        ["deterministic-shaped (no RNG / hidden-zone marker)", len(det),
         sum(ours.get(s.card_id, 0) for s in det),
         f"{sum(meta.get(s.card_id, 0.0) for s in det):.1f}",
         "**emptied by Issue #299** — a deterministic-shaped option on any declared non-terminal "
         "kind now reaches the engine route, so it is an ENGINE-RESOLVED candidate above rather "
         "than a refusal here"],
        ["RNG-shaped (shuffle / deck read / coin)", len(rng),
         sum(ours.get(s.card_id, 0) for s in rng),
         f"{sum(meta.get(s.card_id, 0.0) for s in rng):.1f}",
         "needs an `Expectation`-returning clause, NOT an engine call — and is structurally "
         "refused ONLY on the engine route"],
    ], ["gap shape", "sites", "our copies", "meta copies", "what it needs"]))
    add("")
    add("The first row is **expected to be empty** and its emptiness is the measurement, not an "
        "omission: it is the exact set Issue #299's ruling moved. A non-zero count here would mean a "
        "deterministic-shaped option is still being refused on a MODELLED kind, which the ruling "
        "says cannot happen — so read it as a live check on the routing rather than as a backlog.")
    add("")
    n_new = sum(v[0] for v in fam.values() if not v[3])
    add(f"**{n_new} of {len(gap)}** gap sites need vocabulary that does not exist yet; "
        f"{len(gap) - n_new} need only a compendium entry in an existing kind.")
    add("")

    add("### Win-plan critical path")
    add("")
    add("A card the deck's own authored doctrine names. `grimmsnarl_ex` and `slowking` ship no "
        "`STRATEGY.md`, so they cannot be scanned and are absent here — not clean.")
    add("")
    rows = []
    for s in sorted(sites, key=lambda s: -ours.get(s.card_id, 0)):
        if s.report_class in (FULL,):
            continue
        hits = on_win_plan(s, decks, strategies)
        if hits:
            rows.append([s.card_id, s.name, s.label, s.report_class, ", ".join(hits),
                         ours.get(s.card_id, 0)])
    add(_table(rows, ["id", "card", "site", "class", "named by", "our copies"])
        if rows else "_none_")
    add("")

    add("### ENGINE-RESOLVED — the modelling backlog")
    add("")
    er = sorted((s for s in sites if s.fate == seam.ENGINE_RESOLVED),
                key=lambda s: (-ours.get(s.card_id, 0), -meta.get(s.card_id, 0.0), s.name))
    add(f"{len(er)} sites, {sum(ours.get(s.card_id, 0) for s in er)} copies across our {n_decks} "
        f"decks. "
        "Each is a CANDIDATE: no RNG, hidden-zone or opponent-choice marker appears in its text, "
        "which is necessary for the `deterministic=True` proof but is not the proof itself.")
    add("")
    add(_table([[s.card_id, s.name, s.label, ours.get(s.card_id, 0),
                 f"{meta.get(s.card_id, 0.0):.2f}"] for s in er],
               ["id", "card", "site", "our copies", "meta copies"]))
    add("")

    add("### MODELLED-PARTIAL — clause sets that cover only part of the card")
    add("")
    partial = sorted((s for s in sites if s.report_class == PARTIAL),
                     key=lambda s: (-ours.get(s.card_id, 0), -meta.get(s.card_id, 0.0), s.name))
    pf = collections.Counter(s.fate for s in partial)
    add(f"{len(partial)} sites, {sum(ours.get(s.card_id, 0) for s in partial)} copies across our "
        f"{n_decks} decks. **These no longer resolve to MODELLED** (Issue #299): a `_covers: partial` "
        f"verdict "
        f"reaches the seam as `clauses_cover=False`, which fails closed exactly as an unproven "
        f"`deterministic` does, so the uncovered leg can no longer difference to a silent 0. They "
        f"land instead on " + ", ".join(f"**{f}** ({n})" for f, n in sorted(pf.items())) + ". The "
        "row is kept because the WORK is unchanged and specific — complete the clause set — and "
        "merging it into the undifferentiated refusals would hide it among cards that have no "
        "compendium entry at all.")
    add("")
    add(_table([[s.card_id, s.name, s.fate, ours.get(s.card_id, 0),
                 f"{meta.get(s.card_id, 0.0):.2f}", s.note] for s in partial],
               ["id", "card", "fate now", "our copies", "meta copies",
                "what the clauses miss"]))
    add("")

    add("### Pokemon Tools — MODELLED to attach, but is the attach worth anything?")
    add("")
    add("A Tool attach is structurally MODELLED: it writes `attached_tools`, which is homed. But "
        "differencing prices the attach at whatever `state_value` reads off the body AFTERWARDS, "
        "and that is the stat provider's parse of the Tool's printed text — not this seam's. A Tool "
        "whose static effect no parser recovers attaches for a delta of ~0 and sorts to the bottom "
        "of every menu. Measured with the SHIPPED parsers (`common.scouting.card_text`):")
    add("")
    rows = []
    tool_sites = sorted((s for s in sites if s.category == "tool"),
                        key=lambda s: (-ours.get(s.card_id, 0), -meta.get(s.card_id, 0.0)))
    unread = 0
    for s in tool_sites:
        reads = tool_static_reads(cards_by_id[s.card_id])
        if reads:
            cell = ", ".join(reads)
        elif s.card_id in DELIBERATELY_UNMODELLED_TOOLS:
            cell = f"none — DELIBERATE: {DELIBERATELY_UNMODELLED_TOOLS[s.card_id]}"
            unread += 1
        else:
            cell = "**none — prices at ~0**"
            unread += 1
        rows.append([s.card_id, s.name, ours.get(s.card_id, 0), f"{meta.get(s.card_id, 0.0):.2f}",
                     cell])
    add(_table(rows, ["id", "tool", "our copies", "meta copies", "CardStat fields recovered"]))
    add("")
    named = sum(1 for s in tool_sites if s.card_id in DELIBERATELY_UNMODELLED_TOOLS)
    residue = (f"The remaining {unread - named} are unexplained and belong to whoever picks this up "
               f"next." if unread > named else "None is left unexplained.")
    add(f"{unread} of {len(tool_sites)} recover nothing, and **{named} of those are DELIBERATE**, "
        f"each named with its reason above — the reactive family needs {UNMODELLED_TOOLS_REASON}. "
        f"{residue}")
    add("")
    add("Two rows that DO recover a field are still only partly modelled, and say so here rather "
        "than reading as covered. **Gravity Gemstone** carries the holder's surcharge as a negative "
        "`retreatReduction`, which is exact (a body only ever pays a Retreat Cost from the Active "
        "Spot, precisely when the clause is live) — but its SYMMETRIC leg, the opponent's Active "
        "paying `{C}` more too, has no per-card field on my Tool that could hold a fact about their "
        "body. **Hop's Choice Band** recovers both its legs, but see the next paragraph on the "
        "cost one.")
    add("")
    add("A field listed here is RECOVERED, which is not the same as PRICED. "
        "`attackCostReduction` (Hop's Choice Band) is parsed and has **no live consumer**: "
        "affordability is asked ~20 times as `_attack_cost(aid) <= energy`, all ATTACK-keyed, and a "
        "body-keyed discount cannot be threaded through them without a redesign — nor safely, since "
        "a wrong credit manufactures a KO_SCORE-class phantom. It is a T4 `state_value` input. "
        "`holderNameFamily` is the opposite: it is a GATE, and every consumer of the amount it "
        "guards (`hpBonus`, `damageBoost`) tests it through `CardStat.applies_to_holder`.")
    add("")

    add("### Per-deck exposure")
    add("")
    add("Per CARD (each card counted once, at its WORST site), so every row totals the deck's 60.")
    add("")
    rows = []
    for agent, counter in sorted(decks.items()):
        per = collections.Counter()
        for cid, n in counter.items():
            per[worst[cid]] += n
        tot = sum(per.values()) or 1
        rows.append([agent, per.get(FULL, 0), per.get(PARTIAL, 0),
                     per.get(seam.ENGINE_RESOLVED, 0), per.get(seam.REFUSED, 0),
                     _pct(per.get(seam.REFUSED, 0) + per.get(PARTIAL, 0), tot)])
    add(_table(rows, ["deck", "modelled-full", "modelled-partial", "engine-resolved", "refused",
                      "% at-risk (partial+refused)"]))
    add("")

    add("### Clause write-set health (`snapshot_coverage`)")
    add("")
    add(f"- `clauses_writing_unhomed()`: `{snapshot_coverage.clauses_writing_unhomed()}`")
    add(f"- `unknown_zones()`: `{snapshot_coverage.unknown_zones()}`")
    add(f"- `unhomed()`: `{snapshot_coverage.unhomed()}`")
    add(f"- `footprints_writing_unhomed()`: `{seam.footprints_writing_unhomed()}`")
    add("")
    # Through `snapshot_coverage.clause_values`, NOT a hand-rolled `kind`-plus-`rider` walk. This
    # table used to keep its own, so a section titled "Clause write-set health" reported on two of
    # the audit's axes: `effect` had been outside it since Issue #300 minted it, and `cost` would
    # have been outside it from Issue #350. One extractor, so the report cannot claim health over
    # ground the audit walks and it does not (Issue #350).
    #
    # Two deliberate consequences, both measured against the committed compendium. The old
    # `used[c.get("kind")] += 1` counted a literal `None` for a clause with no `kind` and rendered it
    # as an UNDECLARED row; the extractor skips it, so that signal moves to the audit test, which is
    # the real gate — 0 of the 116 committed clauses lack a `kind`, so no row changed. And a value
    # carried on two keys of one clause now counts twice (only `gust` is multi-key today), which is
    # what "sites using it" already meant for a `kind`-plus-`rider` clause.
    used = collections.Counter()
    for s in sites:
        for c in s.clauses:
            used.update(snapshot_coverage.clause_values(c))
    add(_table([[k, n, "yes" if snapshot_coverage.CLAUSE_WRITES.get(k) else
                 ("declared EMPTY" if k in snapshot_coverage.CLAUSE_WRITES else "**UNDECLARED**")]
                for k, n in sorted(used.items(), key=lambda kv: (-kv[1], kv[0]))],
               ["/".join(snapshot_coverage.VOCABULARY_KEYS) + " in pool", "sites using it",
                "has a write-set"]))
    add("")
    # ── the THIRD axis (Issue #374) ───────────────────────────────────────────────────────────────
    # The table above reports the health of the VOCABULARY axis. It reported nothing at all about the
    # SELECTOR axis, which is the wider one — and that is the same defect one level up that Issue
    # #350 fixed inside the table itself: a report titled "Clause write-set health" cannot claim
    # health over ground the audit walks and it does not. Read through the same
    # `snapshot_coverage.clause_selectors` extractor the audit uses, for the same reason.
    #
    # `UNCONSUMED` is the honest column: a value can be perfectly well DECLARED and still have no
    # reader, which is the state 33 of the 74 are in. Declared-and-unread is a scheduled gap with a
    # written reason; declared-and-silent would be the vacuous registry this axis was built to avoid.
    add("### Clause selector-value health (`snapshot_coverage`, Issue #374)")
    add("")
    # WHOLE-COMPENDIUM, unlike the pool-scoped table above — deliberately, and said out loud because
    # the two sit next to each other. The audit this mirrors walks every committed clause, so a
    # pool-scoped count here would report health over a strictly smaller set than the check enforces.
    pairs = snapshot_coverage.clause_selectors(load_effects())
    undeclared = snapshot_coverage.undeclared_selector_values(pairs)
    add(f"- `undeclared_selector_values()`: `{undeclared}`")
    add(f"- selector keys / values in the compendium: "
        f"**{len({k for k, _ in pairs})}** / **{len(pairs)}**")
    add(f"- of those, ledgered as reaching no consumer yet "
        f"(`UNCONSUMED_SELECTORS`): **{len(snapshot_coverage.UNCONSUMED_SELECTORS)}**")
    add("")
    by_key = collections.Counter(k for k, _ in pairs)
    unconsumed = collections.Counter(
        e.split("=", 1)[0] for e in snapshot_coverage.UNCONSUMED_SELECTORS)
    add(_table([[k, n, unconsumed.get(k, 0),
                 "yes" if k in snapshot_coverage.CLAUSE_SELECTORS else "**UNDECLARED**"]
                for k, n in sorted(by_key.items(), key=lambda kv: (-kv[1], kv[0]))],
               ["selector key in the compendium", "distinct values", "unconsumed", "declared"]))
    add("")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)

    cards, effects, covers = load_cards(), load_effects(), load_covers()
    decks = load_our_decks()
    builds, priors = load_opponent_builds()
    pool = set().union(*[set(c) for c in decks.values()], *[set(c) for c in builds.values()])

    problems = validate(pool, cards, effects, covers)
    if problems:
        for p in problems:
            print(f"PROBLEM: {p}", file=sys.stderr)
        return 1

    sites, aside = census(pool, cards, effects, covers)
    ours = our_copies(decks)
    meta = meta_copies(builds, priors)
    report = build_report(sites, aside, ours, meta, decks, len(builds),
                          load_strategy_names(), cards)

    block = f"{BEGIN}\n\n{report}\n{END}"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        existing = args.out.read_text(encoding="utf-8")
        i, j = existing.find(BEGIN), existing.find(END)
        if i < 0 or j < 0:
            print(f"{args.out} exists but carries no {BEGIN} / {END} markers — refusing to "
                  f"overwrite authored prose", file=sys.stderr)
            return 1
        block = existing[:i] + block + existing[j + len(END):]
    # Binary write: `Path.write_text` rewrites LF to CRLF on Windows, which would make every re-run
    # a whole-file diff on a repo whose stores are line-ending sensitive.
    args.out.write_bytes(block.encode("utf-8"))
    print(f"wrote {args.out}")
    if args.json:
        args.json.write_bytes(json.dumps([s.as_row() for s in sites], indent=1,
                                         ensure_ascii=False).encode("utf-8"))
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
