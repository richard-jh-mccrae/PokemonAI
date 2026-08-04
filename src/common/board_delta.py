"""**The closed-form board delta** — one engine step, synthesized arithmetically (POC-T4/1,
Issue #382, under the seam contract ADR-0098 froze at POC-T0).

`common.apply_option` owns the CONTRACT (which fates exist, which kind resolves to which, what a
refusal means). This module owns the ARITHMETIC: given a live observation and one option off its
select menu, what does the *next* observation look like? `apply_option` then rebuilds a fresh
`StateModel` over the result, and the planner differences the two.

## Copy-on-write, never in-place — and never a deep copy either

Three facts force a FRESH observation rather than a mutated one (Issue #382 design ruling 1):

* ``state_value`` memoizes its per-family dict onto the model under ``("state_value",)``
  (`state_value.py`), and **nothing invalidates that key** — a mutated model returns a stale scalar
  in silence.
* The seam's own contract: *"Never mutates ``model``: the planner holds the pre-state while it
  evaluates alternatives"* (`apply_option.apply_option`).
* `state_model.StateModel` is a PURE snapshot (ADR-0068). Purity is what lets a model be shared
  across evaluations at all.

And three facts forbid a deep copy: 1-ply ordering runs this once per candidate per decision, the
grader is 2 vCPUs for ~10 minutes a match, and an observation carries both players' whole zone
listings. So every function here rebuilds only the dicts and lists on the PATH to what it writes and
shares every untouched object by reference. A hypothetical board and its pre-state therefore share
the opponent's entire `PlayerState` by identity whenever the transition never reached across the
table — which is exactly the precondition `StateModel.shares_opponent_with` guards, and why
:class:`Delta` reports it rather than leaving the caller to re-derive it.

## What "one engine step" means, measured rather than assumed

The unit here is **the engine's own step**, not the human notion of a play. That distinction is not
pedantic — it is the single most load-bearing fact this module was built on, and it was measured on
the committed native traces (`tests/fixtures/parity/*.trace.json.gz`, `parity-trace/1`) rather than
recalled:

* **`_RETREAT` carries NO target.** Every one of the 5807 retreat options offered across the
  committed parity corpus, and all 146 in the 372-frame corrections corpus both ADR-0072 gates
  replay, is the bare dict ``{"type": 12}``. The engine answers it by spending the once-per-turn
  retreat allowance and posing FOLLOW-UP selects — `_DISCARD_ENERGY` (context 30) for the cost, then
  `_SWITCH` (context 3) for who is promoted. So the closed-form transition for a retreat OPTION is
  the allowance spend and nothing else; the swap belongs to the later decision points, which the
  composer visits as decision points of their own (Issue #263 § *Every fresh decision point is a
  composer decision*). Modelling the swap here would diverge from the engine on the very next frame.
* **A Trainer whose effect opens a select does not reach the discard on the same step.** Measured on
  the same corpus: an Item or Supporter followed by a `_TO_HAND` / `_DISCARD` / `_SWITCH` select
  moves ONLY `hand` (plus `supporterPlayed`), while one that resolves immediately moves
  `hand` + `discard` together. The card is in flight, and a floor that discarded it eagerly would be
  wrong on the majority of Trainer plays.
* **A Basic Pokémon deploy and a Stadium play settle inside one step.** ~1720 Basic deploys across
  the corpus move exactly `hand` + `bench` and return to the MAIN menu; a Stadium play moves `hand`,
  the shared `stadium` and `stadiumPlayed`, plus the displaced Stadium into its OWNER's discard.

Everything this module cannot write in one step it REFUSES, by raising :class:`Unmodellable` for
`apply_option` to turn into a `Refusal`. A refusal is always-expand (`apply_option.must_expand`); a
wrong delta is a mis-priced sequence with nothing to say so.

## Rules read at source, never from memory

* `docs/rules.md` §3 — the per-turn allowances: *"Attach an Energy | 1"*, *"Play a Stadium | 1 (and
  only if it differs from the one in play)"*, *"Retreat (manual) | 1 (pay the Retreat cost in Energy;
  card effects can switch for free)"*.
* `docs/rules.md` §4 — *"Evolving keeps attached cards + damage counters; **clears** Special
  Conditions and attack effects."*
* `docs/rules.md` §8 — Special Conditions live on the **Active only**, and are *"cleared when it
  leaves the Active spot OR evolves"*. The engine puts the five flags on `PlayerState`, which is why
  clearing them is a player-level write and not a body-level one.
* `docs/rulebook.txt` L135-137 — *"Only one Stadium can be in play at a time—if a new one comes into
  play, discard the old one and end its effects."*; L78 — *"Each player has their own discard pile"*,
  which is why displacement writes whichever discard owned the old Stadium.
* `src/common/board_cards.py` — the ``energies`` / ``energyCards`` split. ``energies`` is NOT a card
  list: it is the Energy UNITS the attached cards provide, and the coincidence that Basic Energy card
  ids equal their `EnergyType` codes stops at the ninth card (Ignition Energy is card 17 and renders
  ``[0, 0, 0]``). So an attach appends the CARD to ``energyCards`` and the card's PROVISION to
  ``energies``, from `CardFunctions.energy_provision` — never the card id.

The synthesized body shapes are copied from what the engine actually produced on those traces, field
for field (`alakazam_9000` f122/f127 for the evolve stack, f22 for the deploy), so a diff against the
next recorded frame is a diff about the rules and not about a spelling.
"""
from __future__ import annotations

from dataclasses import dataclass

from common import snapshot_coverage
from common.board_cards import body_unit_codes
# `cg.api.AreaType`, from the ONE module that already holds those numbers DLL-free and has them
# pinned to the engine enum by a test (`test_area_constants_match_the_engine_enums`). Re-spelling
# them here would be a second copy of the same constants in the same change.
from common.option_equivalence import AREA_ACTIVE, AREA_BENCH, AREA_HAND
from common.strategy.context import _ATTACH, _EVOLVE, _PLAY, _RETREAT

#: `cg.api.SelectContext.MAIN`. The only context this module transitions at — see :func:`transition`
#: for the measurement behind that boundary. It matters most for `_ATTACH`: at MAIN an Energy attach
#: is the turn's ONE manual attachment (`docs/rules.md` §3), while an attach posed from inside a
#: card's effect (`_ATTACH_FROM` / `_ATTACH_TO`) is the card doing the work and spends no allowance.
CONTEXT_MAIN = 0

#: The five Special-Condition flags, on `PlayerState` rather than on the body (`docs/rules.md` §8:
#: only the Active can carry one, so the engine has no per-body home for them).
CONDITION_FLAGS = ("poisoned", "burned", "asleep", "paralyzed", "confused")

#: Fallback Bench cap when an observation omits the engine's own ``benchMax`` — the shipped format's
#: 5 (`docs/rulebook.txt` L75). Same constant and same reason as `state_model._BENCH_MAX`; only a
#: hand-built board ever reaches it.
_BENCH_MAX = 5


class Unmodellable(Exception):
    """*"This option's board change is not closed-form under the current vocabulary."*

    Raised INSIDE a modelled kind, and converted by `apply_option` into a `Refusal` at
    ``OPTION_SCOPE`` — never into a silently-unchanged observation, which would price the option at
    exactly 0.0 delta and read at ordering time as *never explore this*.

    The message is destined for the telemetry line and the modelling backlog, so it follows the
    seam's own convention where it can: ``"<card id> <card name>: <what is missing>"``."""


@dataclass(frozen=True)
class Delta:
    """One engine step, as a fresh observation plus what it actually wrote.

    ``writes`` is in `snapshot_coverage` zone vocabulary — the same field names
    `apply_option.Footprint` speaks — so a test can assert a transition wrote its declared set and
    nothing else without a second spelling of the zone names existing anywhere.

    ``shares_opponent`` is the copy-on-write dividend made explicit: True when the synthesis never
    touched their `PlayerState` nor the shared Stadium, which is precisely when
    `StateModel.build(..., their_side=)` may reuse the pre-state's already-built (and possibly
    already-derived) opponent half. Reported rather than re-derived, because the caller cannot see
    which objects the synthesis shared."""

    #: The synthesized observation. Structurally shared with the pre-state everywhere it could be.
    obs: dict
    #: `snapshot_coverage` zone ids this step ASSIGNED. Exhaustive over assignments and asserted
    #: EXACTLY, per case, by `test_every_transition_writes_exactly_its_declared_set` — which is what
    #: makes a FORGOTTEN write a failure and not only an extra one.
    #:
    #: Assignments, not the closure of everything downstream: a Tool landing on the Active also moves
    #: `this_turn_damage_boosts`, because `_SideBase.damage_boosts` DERIVES that zone from the
    #: holder's tools. Declaring derived zones here would make this set a second, hand-kept model of
    #: the snapshot's own dependency graph — the drift ADR-0087 charges for one store over.
    writes: frozenset[str]
    #: Their `PlayerState` and the shared Stadium are the pre-state's own objects.
    shares_opponent: bool = True


# ── copy-on-write scaffolding ─────────────────────────────────────────────────────────────────────
#
# **PUBLIC since POC-T4/2** (Issue #383), and the promotion is the point rather than an oversight.
# `common.board_expectation` synthesizes the board a REVEAL resolves to and needs exactly this
# scaffolding — and `state_model.py` already paid for the general rule these three would otherwise
# break: *"a private reach across a module boundary is how a refactor inside `MySide` breaks a caller
# nothing warned about"*, which is why it exposed `combat` / `deck` / `card_stat()` rather than let
# the apply seam reach in. Same answer here, one module out: a second consumer means a public name,
# never an underscore reached across a boundary.


def fork(obs: dict) -> tuple[dict, dict, list]:
    """Fresh ``obs`` / ``current`` / ``players`` containers, sharing every zone below them.

    Three dicts and one list per transition, whatever the board holds. Everything a step does not
    write — both hands, both decks, every body, the logs, the select — stays the pre-state's own
    object, which is what makes the pre-state safe to keep evaluating alternatives against."""
    new_obs = dict(obs or {})
    current = dict(new_obs.get("current") or {})
    players = list(current.get("players") or [])
    current["players"] = players
    new_obs["current"] = current
    return new_obs, current, players


def fork_player(players: list, index: int) -> dict:
    """A fresh copy of one side's `PlayerState`, spliced into ``players``. Its zone lists are still
    shared — the caller forks whichever list it writes."""
    seat = dict(players[index] or {})
    players[index] = seat
    return seat


def _without(cards, index: int) -> list:
    """``cards`` minus the entry at ``index`` — a new list, the entries themselves shared."""
    out = list(cards or ())
    del out[index]
    return out


def _card_ref(card: dict, seat: int) -> dict:
    """A card as it appears in a *stack* — id / serial / playerIndex, and nothing else.

    The shape the engine writes into ``preEvolution`` (measured: `alakazam_9000` f122, where the
    evolved-over Litwick arrives as ``{"id": 109, "serial": 6, "playerIndex": 0}`` even though the
    body it came from carried hp, energies and its own stack). A body's state does not survive being
    stacked under its evolution — only the card does."""
    ref = {"id": card.get("id"), "serial": card.get("serial")}
    if card.get("playerIndex") is not None:
        ref["playerIndex"] = card["playerIndex"]
    else:
        ref["playerIndex"] = seat
    return ref


def _body_at(seat: dict, area: int, index):
    """The body an ``(inPlayArea, inPlayIndex)`` reference names, or None when it cannot resolve.

    None rather than a raise: the ordering hot path visits every option on a live menu, and an
    option this seam cannot resolve must refuse (visibly, always-expanded) rather than forfeit the
    match on an `IndexError`."""
    if not isinstance(index, int) or index < 0:
        return None
    zone = {AREA_ACTIVE: "active", AREA_BENCH: "bench"}.get(area)
    if zone is None:
        return None
    bodies = seat.get(zone) or ()
    return bodies[index] if index < len(bodies) else None


def _replace_body(seat: dict, area: int, index: int, body: dict) -> None:
    """Splice ``body`` into a FRESH copy of its zone list on ``seat``."""
    zone = "active" if area == AREA_ACTIVE else "bench"
    bodies = list(seat.get(zone) or ())
    bodies[index] = body
    seat[zone] = bodies


def take_from_hand(seat: dict, index, what: str) -> dict:
    """Remove and return my hand card at ``index``, resyncing ``handCount``.

    Every transition that plays a card does exactly this, and each one used to spell the bounds
    check and the count resync for itself — four copies of two lines, which is three chances for one
    of them to forget the count and leave a snapshot claiming a card it no longer holds.

    Raises :class:`Unmodellable` rather than `IndexError`: the ordering hot path visits every option
    on a live menu, and a raise there is a forfeited grader match over an option we merely could not
    resolve."""
    hand = seat.get("hand") or ()
    if not isinstance(index, int) or not 0 <= index < len(hand):
        raise Unmodellable(f"{what} names hand index {index!r}, which this snapshot cannot resolve "
                           f"(hand of {len(hand)})")
    card = hand[index]
    seat["hand"] = _without(hand, index)
    if seat.get("handCount") is not None:
        seat["handCount"] = len(seat["hand"])
    return card


def _clear_conditions(seat: dict) -> bool:
    """Clear the five Special-Condition flags; True when any was set.

    `docs/rules.md` §8 — they live on the Active alone and are cleared when it leaves the Active
    spot or evolves. Returns whether anything moved so the caller only declares the
    ``special_conditions`` write when it happened, which keeps the per-kind write assertions exact."""
    hit = [f for f in CONDITION_FLAGS if seat.get(f)]
    for flag in hit:
        seat[flag] = False
    return bool(hit)


# ── card knowledge ────────────────────────────────────────────────────────────────────────────────


def _stat(combat, card_id):
    """This card's `CardStat`, or None. Through the combat oracle's own accessor (ADR-0056's Stat
    Provider seam) rather than a second table — the model reads its facts the same way."""
    getter = getattr(combat, "_card_stat", None)
    return getter(card_id) if getter is not None and card_id is not None else None


def _provided_units(combat, card_id, stat, *, onto_evolution: bool) -> tuple:
    """The `EnergyType` UNIT codes attaching this Energy CARD puts on ``energies``.

    Composed, not invented: the colour is ``CardStat.energyType`` and the count is
    `CardFunctions.energy_provision` — the same pair `CombatMath._special_energy_groups` reads for
    the HAND leg of the Attach Budget, so a hypothetical attach and the real board it models agree
    (Issue #142). A Basic Energy is one unit of its own colour and carries no tag — the case that
    would otherwise fail closed to nothing.

    Ignition Energy (17) is the worked example the ``energies``/``energyCards`` split exists for:
    ``energyType`` colourless, provision 1 on a Basic and 3 on an Evolution, so it renders
    ``[0]`` or ``[0, 0, 0]`` and NEVER ``[17]`` (`common/board_cards.py`).

    Fail-CLOSED (ADR-0067): an untagged Special Energy raises rather than attaching zero units,
    because zero units is a real, plausible board that under-reports the attach."""
    colour = getattr(stat, "energyType", None)
    if colour is None:
        raise Unmodellable(
            f"{card_id} {getattr(stat, 'name', '?')}: attached Energy with no `energyType` — the "
            f"unit colour is unknown, and a guessed colour funds attacks it cannot pay for")
    if stat.is_basic_energy:
        return (int(colour),)
    functions = getattr(combat, "functions", None)
    count = 0
    if functions is not None:
        count = functions.energy_provision(card_id, evolution=onto_evolution)
    if count <= 0:
        raise Unmodellable(
            f"{card_id} {getattr(stat, 'name', '?')}: Special Energy with no `provides:N` Function "
            f"Tag — how many units it provides is unknown, and 0 would under-report the attach")
    return (int(colour),) * int(count)


def _units_for_cards(combat, cards, *, onto_evolution: bool) -> list:
    """Every Energy CARD's provision, concatenated in attachment order — the ``energies`` list.

    Derived rather than carried, because the provision is a property of the HOLDER as well as of the
    card: Ignition Energy provides {C} on a Basic and {C}{C}{C} on an Evolution, so the same attached
    card renders differently before and after an evolution."""
    out: list = []
    for card in cards or ():
        card_id = (card or {}).get("id")
        stat = _stat(combat, card_id)
        if stat is None:
            raise Unmodellable(f"{card_id}: no `CardStat` for an attached Energy card, so its "
                               f"provision cannot be re-derived")
        out.extend(_provided_units(combat, card_id, stat, onto_evolution=onto_evolution))
    return out


def card_clauses(combat, card_id) -> tuple:
    """This card's Effect Clauses off the combat oracle's own `CardEffects`, or ``()``.

    **One home for the walk**, because three modules now need it and each would otherwise spell
    ``getattr(getattr(combat, "effects", None), "clauses", ...)`` for itself — a message chain
    repeated is a message chain that drifts. `state_model.StateModel` added `combat` and
    `card_stat()` as public reads for exactly this reason; this is the same move one level out.

    ⚠️ **``()`` is *undeclared*, never *writes nothing*.** A card the compendium has never heard of
    is indistinguishable here from one with no effect, and every caller has to join that against
    whether the card carries printed text at all — the same residue `apply_option.fate` documents for
    its `clauses_cover=None`. Premium Power Pro (1141), Black Belt's Training (1211) and Brave Bangle
    (1175) are the worked cases: `card_effects.json` returns nothing for any of them while their whole
    effect is the parsed `CardStat.damageBoost` triple."""
    effects = getattr(combat, "effects", None)
    return tuple(effects.clauses(card_id) if effects is not None else ())


def _clause_writes(combat, card_id) -> frozenset:
    """Every `snapshot_coverage` zone this card's Effect Clauses write, unioned over all four
    vocabulary axes (``kind`` / ``rider`` / ``effect`` / ``cost``).

    The registry is the source, so a clause value nobody declared cannot quietly union to nothing:
    `snapshot_coverage.undeclared_clauses` raises the flag one layer up (the audit test walks the
    whole compendium), and here an undeclared value is treated as *unknown*, which refuses.

    ⚠️ **An empty union is not proof the card writes nothing** — a card the compendium has never
    heard of unions to the empty set, which is the blind spot `apply_option.footprints_writing_unhomed`
    names by card: Premium Power Pro (1141), Black Belt's Training (1211) and Brave Bangle (1175) all
    return no clauses while their whole effect is the parsed `CardStat.damageBoost` triple. So the
    CALLERS here never treat "wrote nothing" as a licence on its own — see :func:`_play`."""
    out: set = set()
    for clause in card_clauses(combat, card_id):
        for value in snapshot_coverage.clause_values(clause):
            if value not in snapshot_coverage.CLAUSE_WRITES:
                raise Unmodellable(
                    f"{card_id}: clause value {value!r} is not in `snapshot_coverage.CLAUSE_WRITES` "
                    f"— the vocabulary moved underneath the seam")
            if value in snapshot_coverage.NONDETERMINISTIC_CLAUSES:
                raise Unmodellable(
                    f"{card_id}: clause {value!r} consults RNG — a simulated shuffle is one sample, "
                    f"not a distribution (the engine has no deal-seed)")
            if value in snapshot_coverage.REVEALING_CLAUSES:
                raise Unmodellable(
                    f"{card_id}: clause {value!r} REVEALS information — it belongs to an Expectation "
                    f"node over outcome classes (POC-T4/2, Issue #383), not to a point transition")
            out |= snapshot_coverage.CLAUSE_WRITES[value]
    return frozenset(out)


def _stadium_gate(current: dict, combat, *, why: str) -> None:
    """Refuse while a Stadium whose effect WRITES the board is in play.

    **Measured, not anticipated.** The parity lane's first full sweep found 82 divergences over 41
    steps, and every one of them was a live board-level effect re-writing a body the moment it
    entered or changed — a class the option's own clauses cannot see, because the card doing the work
    belongs to the board rather than to the play:

    * **Risky Ruins (1260)**, a `stadium_trigger`: *"Whenever any player puts a Basic non-{D} Pokémon
      onto their Bench during their turn, place 2 damage counters on that Pokémon."* 28 deploys
      arrived at full HP in the seam and at 2 counters in the engine.
    * **Gravity Mountain (1252)**, a `stadium_static` `hp_delta`: *"Each Stage 2 Pokémon in play (both
      yours and your opponent's) gets -30 HP."* 7 evolutions into a Stage 2 arrived 30 HP too high —
      Dragapult ex at 320/320 where the engine says 290/290.

    So the gate is *"is a Stadium with a NON-EMPTY `CLAUSE_WRITES` union in play?"*, read off the same
    registry every other refusal here consults. A Stadium whose effects are `damage_reduction` /
    `damage_boost` / `prevent_damage` writes nothing (declared empty, deliberately — `CombatMath`
    reads those off the `stadium` zone when it prices an attack and stores nothing), so those do not
    gate. Cost of the gate, measured on the same corpus: **104 refused steps of 14581** (67 Risky
    Ruins, 37 Gravity Mountain).

    **Three callers, and the third is the one nobody would guess.** A body ENTERING play is what a
    trigger fires on (`_play`'s deploy) and a body CHANGING stage is what a static HP delta re-reads
    (`_evolve`) — but **displacing** the Stadium ENDS its effect (`docs/rulebook.txt` L137: *"discard
    the old one and end its effects"*), which re-writes every body it was modifying. Verified on the
    corpus rather than reasoned: `ml_dx_2001` carries Dragapult ex at **290/290 while Gravity Mountain
    is in play (f172) and at 320/320 once it is gone (f181)**. The committed corpus happens to contain
    zero steps that play a QUIET Stadium over a writing one — all four displacements play a writing
    Stadium, which refuses on its own union — so the parity lane's clean sweep does not cover that
    path, and the gate is here on the rule rather than on the measurement.

    Refused rather than modelled, and that is a scope ruling worth stating: applying a Stadium's
    trigger means reading its clause parameters and its restriction (*"Basic non-{D}"*) and deciding
    which body it lands on — clause APPLICATION, which is what POC-T4/2 (Issue #383) scopes. Half of
    it here would be exactly the three-quarters-of-a-card modelling Issue #300's `_covers` verdict
    exists to refuse."""
    card = (current.get("stadium") or [None])[0]
    if not card:
        return
    card_id = card.get("id")
    try:
        writes = _clause_writes(combat, card_id)
    except Unmodellable as gap:
        raise Unmodellable(f"a Stadium is in play whose effect the seam cannot model — {gap}")
    if writes:
        stat = _stat(combat, card_id)
        raise Unmodellable(
            f"{card_id} {getattr(stat, 'name', '?')} is in play and its effect writes "
            f"{sorted(writes)}; {why} — the transition would produce a board the engine does not "
            f"(measured: Risky Ruins' 2 counters on a benched Basic, Gravity Mountain's -30 on a "
            f"Stage 2, and that same -30 coming BACK when the Stadium is displaced)")


# ── the four transitions ──────────────────────────────────────────────────────────────────────────


def _attach(obs, option, *, seat_index, combat) -> Delta:
    """Energy or Tool from hand onto a body in play.

    Both arrive as `OptionType.ATTACH` — *"a Pokémon Tool… arrives as OptionType.ATTACH exactly like
    an Energy"* (`common/strategy/context.py`) — and they write different zones, which is why the
    branch is on `CardStat.cardType` rather than on the option.

    Only the Energy leg spends the allowance: `docs/rules.md` §3 limits the *manual* attachment to
    one per turn, while a Tool is an ordinary Trainer play with no such cap."""
    new_obs, current, players = fork(obs)
    me = fork_player(players, seat_index)
    card = take_from_hand(me, option.get("index"), "attach")
    stat = _stat(combat, card.get("id"))
    if stat is None:
        raise Unmodellable(f"{card.get('id')}: no `CardStat` for the attached card")

    area, index = option.get("inPlayArea"), option.get("inPlayIndex")
    target = _body_at(me, area, index)
    if target is None:
        raise Unmodellable(f"attach names ({area!r}, {index!r}), which is not a body on my board")

    body = dict(target)
    writes = {"my_hand_ids"}
    if stat.is_tool:
        body["tools"] = list(body.get("tools") or ()) + [card]
        writes.add("attached_tools")
        # A Tool's flat HP grant lands the instant it is attached, on BOTH the current and the
        # maximum — measured on `ms_mirror_1000` f13, where Hero's Cape (1159, *"+100 HP"*) takes a
        # Staryu from 70/70 to 170/170. Gated through `CardStat.applies_to_holder`, the ONE place
        # every holder condition is evaluated (Issue #306): Brave Bangle reaches only a holder with
        # no Rule Box, and a Tool's family gate is the same test. `damage_counters` is the zone,
        # because it is what homes the HP read — the same reading `snapshot_coverage` gives Gravity
        # Mountain's `hp_delta`.
        bonus = int(getattr(stat, "hpBonus", 0) or 0)
        if bonus and stat.applies_to_holder(_stat(combat, target.get("id"))):
            body["hp"] = int(body.get("hp") or 0) + bonus
            body["maxHp"] = int(body.get("maxHp") or 0) + bonus
            writes.add("damage_counters")
    elif stat.is_energy:
        target_stat = _stat(combat, target.get("id"))
        onto_evolution = getattr(target_stat, "evolvesFrom", None) is not None
        units = _provided_units(combat, card.get("id"), stat, onto_evolution=onto_evolution)
        body["energyCards"] = list(body.get("energyCards") or ()) + [card]
        body["energies"] = list(body_unit_codes(body)) + list(units)
        # The turn's one MANUAL attachment (`docs/rules.md` §3). Unconditional because
        # :func:`transition` already refuses anything that is not the MAIN menu — an attach posed
        # from inside a card's effect is the card doing the work and spends no allowance, and it
        # never reaches here.
        current["energyAttached"] = True
        writes.update({"attached_energy", "allowance_energy_attached"})
    else:
        raise Unmodellable(
            f"{card.get('id')} {stat.name}: an ATTACH of a card that is neither Energy nor a Tool — "
            f"the seam has no structural transition for it")
    _replace_body(me, area, index, body)
    return Delta(obs=new_obs, writes=frozenset(writes))


def _evolve(obs, option, *, seat_index, combat) -> Delta:
    """The Evolution card from hand REPLACES the body in play, keeping what it was carrying.

    `docs/rules.md` §4: *"Evolving keeps attached cards + damage counters; clears Special Conditions
    and attack effects."* So the new body inherits ``energies`` / ``energyCards`` / ``tools`` and the
    damage already on it, the old body's CARD is pushed onto ``preEvolution``, and the conditions
    clear — the last only when the target is the Active, since `docs/rules.md` §8 gives no other body
    a condition to clear.

    Damage is carried as a DELTA rather than as an HP number, which is the whole subtlety: the new
    body has a different maximum, so ``hp = new max − damage already taken``. Measured shape,
    `alakazam_9000` f127: an undamaged 80 HP body evolving into a 140 HP one arrives at 140/140 with
    ``appearThisTurn: true`` and a two-deep ``preEvolution`` stack."""
    new_obs, current, players = fork(obs)
    me = fork_player(players, seat_index)
    card = take_from_hand(me, option.get("index"), "evolve")
    stat = _stat(combat, card.get("id"))
    if stat is None or not stat.hp:
        raise Unmodellable(f"{card.get('id')}: no `CardStat` HP for the Evolution card, so the "
                           f"evolved body's maximum is unknown")

    area, index = option.get("inPlayArea"), option.get("inPlayIndex")
    target = _body_at(me, area, index)
    if target is None:
        raise Unmodellable(f"evolve names ({area!r}, {index!r}), which is not a body on my board")
    _stadium_gate(current, combat,
                  why="a body CHANGING stage is what a static HP delta re-reads")

    tools = list(target.get("tools") or ())
    energy_cards = list(target.get("energyCards") or ())
    target_stat = _stat(combat, target.get("id"))
    was_evolution = getattr(target_stat, "evolvesFrom", None) is not None

    # Both of these are what *"evolving keeps attached cards"* (`docs/rules.md` §4) actually means:
    # the cards carry, and so do their EFFECTS — re-evaluated against the body they are now on.
    #
    #   * A Tool's flat grant re-applies to the new maximum. Measured on `ms_mirror_1000` f20:
    #     evolving into Mega Starmie ex (1031, 310 HP) under a Hero's Cape lands at 410, not 310.
    #   * A Special Energy's PROVISION can change with the stage. Ignition Energy provides {C} on a
    #     Basic and {C}{C}{C} on an Evolution, so the same card renders `[0]` before and `[0, 0, 0]`
    #     after — measured on `v2_ms_mirror_5001` f60 and `v2_ms_ml_5300` f35.
    max_hp = int(stat.hp) + sum(
        int(getattr(t_stat, "hpBonus", 0) or 0)
        for t_stat in (_stat(combat, (t or {}).get("id")) for t in tools)
        if t_stat is not None and t_stat.applies_to_holder(stat))
    units_before = tuple(_units_for_cards(combat, energy_cards, onto_evolution=was_evolution))
    if units_before != tuple(body_unit_codes(target)):
        # A SELF-CHECK, not a formality: if the provision model already disagrees with the engine
        # about the body as it stands, re-deriving the post-evolution list from the same model would
        # be compounding an error we can already see. Fail closed and name it.
        raise Unmodellable(
            f"the attached-Energy provision model disagrees with this board before the evolution "
            f"even happens (seam {units_before}, engine {tuple(body_unit_codes(target))}), so the "
            f"re-derived post-evolution units cannot be trusted")
    taken = max(0, int(target.get("maxHp") or 0) - int(target.get("hp") or 0))
    body = {
        "id": card.get("id"),
        "serial": card.get("serial"),
        "playerIndex": card.get("playerIndex", seat_index),
        "hp": max(0, max_hp - taken),
        "maxHp": max_hp,
        "appearThisTurn": True,
        "energies": _units_for_cards(combat, energy_cards, onto_evolution=True),
        "energyCards": energy_cards,
        "tools": tools,
        "preEvolution": list(target.get("preEvolution") or ()) + [_card_ref(target, seat_index)],
    }
    _replace_body(me, area, index, body)
    writes = {"my_hand_ids", "bodies_in_play"}
    if area == AREA_ACTIVE and _clear_conditions(me):
        writes.add("special_conditions")
    return Delta(obs=new_obs, writes=frozenset(writes))


def _retreat(obs, option, *, seat_index, combat) -> Delta:
    """Spend the turn's one manual retreat. **That is the whole step, and it is measured.**

    A retreat OPTION is the bare ``{"type": 12}`` — no promoted body, no Energy to pay with — in
    5807 of 5807 offered occurrences across the committed parity corpus and 146 of 146 in the
    corrections corpus. The engine answers it by setting ``current.retreated`` and posing the cost
    (`_DISCARD_ENERGY`, context 30) and the promotion (`_SWITCH`, context 3) as separate selects, so
    the board at the next frame is otherwise byte-identical.

    ⚠️ **Consequence, stated here because it is invisible from the option:** at 1 ply this delta is
    the allowance alone, so a retreat prices near zero against a leaf that reads the board. The
    maneuver's value lands on the follow-up decision points, which the composer visits in their own
    right (Issue #263 § *Every fresh decision point is a composer decision*). A beam that prunes on
    the 1-ply number alone would therefore never reach a retreat-to-wall line — the f32/f35 class,
    which is one of this track's own acceptance cases. That is a BEAM-ADMISSION ruling owed by the
    composer (**Issue #392**, which blocks Issue #385), not a licence to model a swap the engine did
    not perform: this seam's reference is the recorded native trace, and the trace says the board did
    not move."""
    new_obs, current, _players = fork(obs)
    current["retreated"] = True
    return Delta(obs=new_obs, writes=frozenset({"allowance_retreat_used"}))


def _play(obs, option, *, seat_index, combat) -> Delta:
    """Play a card from hand — the structural half, per card TYPE.

    Two sub-cases settle inside one engine step and are modelled; everything else refuses.

    * **A Basic Pokémon** goes to the Bench with a full HP bar and ``appearThisTurn: true``
      (measured: ~1720 deploys across the corpus move exactly ``hand`` + ``bench`` and return to
      MAIN). A non-Basic Pokémon has no `_PLAY` route — it reaches the board by evolving.
    * **A Stadium** replaces the one in play and spends the one-per-turn allowance
      (`docs/rulebook.txt` L135-137, `docs/rules.md` §3). The displaced Stadium goes to **its owner's**
      discard, which is why both discards can be written from one play (`docs/rulebook.txt` L78).
    * **An Item / Supporter / anything else** refuses. Not for want of a floor — the card leaving my
      hand is trivially structural — but because the EFFECT is the play, and the effect is what a
      differencing composer is asking about. Measured: a Trainer whose effect opens a select does not
      even reach the discard on the same step, so a floor-only delta would be both incomplete and
      wrong. Those plays become Expectation / choice nodes in POC-T4/2 (Issue #383).

    **What the clause-union refusal actually costs, counted rather than waved at.** Issue #382's
    design ruling 2 asks for *"the structural floor plus clause application over the audited
    vocabulary"*, and this module applies NO clauses — any non-empty `CLAUSE_WRITES` union refuses.
    Over the committed parity corpus that is 706 refused `_PLAY` steps of 2398, and they split three
    ways:

    * **~624 are stochastic or revealing** (`draw` / `fetch`) — Expectation nodes by construction,
      which is Issue #383's scope and not a shortfall here.
    * **63 have their write's TARGET chosen at a follow-up select**, so the `_PLAY` option does not
      determine it — structurally the same case as `_RETREAT`. Boss's Orders ×30 poses `_SWITCH`
      (context 3) to pick which of THEIR bodies is gusted; Crispin ×16 poses `_TO_HAND` (7); Wally's
      Compassion ×14 poses (17); Rosa's Encouragement ×2 poses (22). No closed-form transition exists
      for these at this step, whatever the clause vocabulary says.
    * **19 resolve wholly at MAIN**, and of those 13 are the two writing Stadiums (whose effect is the
      BOARD's, not the play's — see :func:`_stadium_gate`). That leaves **6 steps in the whole corpus**
      — Cook ×4, Fennel ×1, Crispin ×1 — where a clause could genuinely be applied here and is not.
      Deferred deliberately: a heal applier built for 6 corpus steps is the thin end of the clause
      application the sub-issue split assigned to Issues #383/#386, and half of it here is exactly the
      three-quarters-of-a-card modelling Issue #300's `_covers` verdict exists to refuse.

    The union is deliberately not the ONLY gate — a card the compendium has never heard of unions to
    the empty set (see :func:`_clause_writes`), which is why the card-TYPE branch decides first and
    the union only narrows it."""
    new_obs, current, players = fork(obs)
    me = fork_player(players, seat_index)
    card = take_from_hand(me, option.get("index"), "play")
    card_id = card.get("id")
    stat = _stat(combat, card_id)
    if stat is None:
        raise Unmodellable(f"{card_id}: no `CardStat` for the played card")

    extra = _clause_writes(combat, card_id)
    if extra:
        raise Unmodellable(
            f"{card_id} {stat.name}: its Effect Clauses write {sorted(extra)} — the structural floor "
            f"is not the whole play, and modelling three quarters of a card is what Issue #300's "
            f"`_covers` verdict exists to prevent")

    if stat.is_pokemon:
        if getattr(stat, "evolvesFrom", None) is not None:
            raise Unmodellable(f"{card_id} {stat.name}: an Evolution has no `_PLAY` route — it "
                               f"reaches the board by evolving")
        if not stat.hp:
            raise Unmodellable(f"{card_id} {stat.name}: no `CardStat` HP, so the deployed body's "
                               f"maximum is unknown")
        _stadium_gate(current, combat,
                      why="a body ENTERING play is what a Stadium trigger fires on")
        bench = list(me.get("bench") or ())
        if len(bench) >= int(me.get("benchMax") or _BENCH_MAX):
            raise Unmodellable(f"{card_id} {stat.name}: the Bench is full, so this deploy is not a "
                               f"legal play on this board")
        bench.append({
            "id": card_id,
            "serial": card.get("serial"),
            "playerIndex": card.get("playerIndex", seat_index),
            "hp": int(stat.hp),
            "maxHp": int(stat.hp),
            "appearThisTurn": True,
            "energies": [], "energyCards": [], "tools": [], "preEvolution": [],
        })
        me["bench"] = bench
        return Delta(obs=new_obs,
                     writes=frozenset({"my_hand_ids", "bodies_in_play", "bench_occupancy"}))

    if stat.is_stadium:
        old = (current.get("stadium") or [None])[0]
        if old and old.get("id") == card_id:
            raise Unmodellable(f"{card_id} {stat.name}: a Stadium of the same name is already in "
                               f"play, so this is not a legal play (`docs/rulebook.txt` L137)")
        # DISPLACEMENT ends the old Stadium's effect (`docs/rulebook.txt` L137), which re-writes every
        # body it was modifying — a Gravity Mountain leaving play gives every Stage 2 its 30 HP back
        # (`ml_dx_2001`: Dragapult ex 290/290 at f172 with GM out, 320/320 at f181 without it). So the
        # gate belongs here as much as on the two body-moving transitions, and this is the caller the
        # parity lane could NOT have found: the committed corpus contains no step that plays a QUIET
        # Stadium over a writing one, so a clean sweep is not evidence about this path.
        _stadium_gate(current, combat,
                      why="DISPLACING it ends its effect on every body it was modifying")
        writes = {"my_hand_ids", "stadium", "allowance_stadium_played"}
        if old is not None:
            owner = old.get("playerIndex")
            owner = seat_index if owner is None else int(owner)
            side = fork_player(players, owner)
            side["discard"] = list(side.get("discard") or ()) + [old]
            writes.add("my_discard_contents" if owner == seat_index
                       else "their_discard_contents")
        played = dict(card)
        played["playerIndex"] = card.get("playerIndex", seat_index)
        current["stadium"] = [played]
        current["stadiumPlayed"] = True
        # `shares_opponent=False` UNCONDITIONALLY, even when the displaced Stadium was my own. The
        # Stadium is a SHARED zone that their side's derivations read (a Gravity Mountain moves their
        # Stage 2s' HP), so a reused `TheirSide` would carry a stale one.
        # `StateModel.opponent_fingerprint` folds `stadium` in for exactly this reason — mirrored
        # here rather than left for the caller to remember.
        return Delta(obs=new_obs, writes=frozenset(writes), shares_opponent=False)

    raise Unmodellable(
        f"{card_id} {stat.name}: a Trainer play is its EFFECT, and the effect is what a differencing "
        f"composer is asking about — the structural floor alone would be a delta the engine does not "
        f"produce (the card does not even reach the discard on the same step when the effect opens a "
        f"select). Expectation / choice nodes are POC-T4/2 (Issue #383)")


#: The transitions, keyed by the engine `OptionType` this seam declares MODELLED. Derived nowhere
#: else: `apply_option.TRANSITION_KINDS` is the contract's answer to *"which kinds does this seam
#: promise?"*, and `test_apply_transitions` asserts the two agree, so a kind promoted in the table
#: without a transition here fails a reading rather than raising on the grader.
TRANSITIONS = {
    _ATTACH: _attach,
    _EVOLVE: _evolve,
    _RETREAT: _retreat,
    _PLAY: _play,
}


def transition(obs: dict, option: dict, *, seat_index: int, combat, context=None) -> Delta:
    """The observation after ``option``, or :class:`Unmodellable`.

    **MAIN-menu options only, and that boundary is measured rather than chosen.** Over the whole
    committed parity corpus, **14 580 of 14 581** modelled steps are posed at `SelectContext.MAIN`;
    the single exception is a `_EVOLVE` posed at context 37 — **Rare Candy's** *"put that card onto
    the Basic Pokémon to evolve it, skipping the Stage 1"* — and answering it does not only evolve
    the body, it also puts the Rare Candy itself into the discard (`trcx_9100` f13). (14 581 is the
    same denominator `tools/train/apply_parity.py` reports as `modelled_steps`, so the two cannot
    quote different populations for one claim.)

    That is the general shape and the reason for the gate: an option posed INSIDE a card's effect
    resolution is one leg of that CARD's step, so it carries writes that belong to the card rather
    than to the option's own kind. The seam models the kind. Refusing costs one step in the whole
    corpus and buys the guarantee that a modelled transition is the option's own transition."""
    if context != CONTEXT_MAIN:
        raise Unmodellable(
            f"select context {context!r} is not the MAIN menu — this option is one leg of a card's "
            f"effect resolving, and that card's other writes ride the same engine step (measured: "
            f"Rare Candy's `_EVOLVE` at context 37 also discards the Rare Candy)")
    kind = int((option or {}).get("type", -1))
    fn = TRANSITIONS.get(kind)
    if fn is None:
        raise Unmodellable(f"option kind {kind} has no closed-form transition in this module")
    return fn(obs or {}, option or {}, seat_index=int(seat_index), combat=combat)


__all__ = ("CONTEXT_MAIN", "CONDITION_FLAGS", "Unmodellable", "Delta", "TRANSITIONS", "transition",
           "fork", "fork_player", "take_from_hand", "card_clauses")
