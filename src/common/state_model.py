"""The **StateModel** — one enriched, two-sided board snapshot per decision point (ADR-0068).

Every value equation READS this instead of re-deriving its own slice of the board. It exists because
the same question was being answered three different ways at three different fidelities (the f70
false-famine was one of those answers being wrong), and because the composed ``state_value`` scalar
(#145) cannot be built on top of mutually inconsistent partial reads.

Three properties carry the design, and each is load-bearing rather than stylistic:

**Lazy.** Nothing is computed until something reads it; each field memoizes on first access. So a
consumer pays exactly for the fields it touches and an unread field costs nothing — which is what
lets the model be *maximal* in what it offers while the field list stays driven by real consumers.
The memo graph IS the declared dependency graph (a field may only read fields below it), so the
documented graph cannot drift from the real one.

**Pure.** Same observation in, same answer out; building writes nothing outside the model's own
memo. This is what makes the other two properties sound: a model that rewrote itself on read could
be neither shared across evaluations nor pinned by a cost test. Cross-decision memory lives in the
separate, declared :class:`CarriedState` channel — never in a field that mutates as a side effect of
being computed.

**Reused by SIDE, never by patch.** The opponent cannot act during my turn, so their half is shared
across the selects of a turn and across the planner's forked leaves; symmetrically #150's sampled
worlds share MY half. Sharing is always guarded by :attr:`StateModel.opponent_fingerprint` — derived
WHOLESALE from their entire side rather than from an enumerated field list, so a disruption play
nobody anticipated invalidates by construction (a hand-picked list silently misses Judge's hand/deck
counts and a gust's Active/bench swap — it fails OPEN, the one direction this codebase never
accepts).

**A general ``apply(action)`` delta path is still absent, and there is now exactly ONE sanctioned
route to a hypothetical board — through the apply seam** (`common.apply_option`, ADR-0098; the
transitions landed with POC-T4/1, Issue #382). Recorded here because the paragraph this replaces
refused such a path outright, and a later reader meeting :meth:`StateModel.rebuilt` would otherwise
conclude the rule was silently violated. It was not; the premise moved:

* The OLD refusal rested on *"the engine already hands us an authoritative post-action board at every
  simulated leaf"*. That was true while every hypothetical came from a forked simulation. The
  differencing composer (Issue #263) is precisely the caller for which it is not: it prices a play by
  ``state_value(after) − state_value(before)`` at 1 ply for every option on the menu, and forking the
  native engine per candidate is what ADR-0098 declined on measurement (no deal-seed, and 0 of 372
  gate frames carry `search_begin_input`, so an engine-routed decision is un-gradeable).
* What survives unchanged is the reason the refusal was worth writing down: a hand-written delta
  applied IN PLACE is a second rules engine whose failure mode is silent divergence. So the seam
  never mutates a model. It synthesizes a fresh post-action observation (copy-on-write over the
  pre-state's zones, `common.board_delta`) and calls :meth:`build` again — a fresh model owns a fresh
  memo, which is what makes the ``("state_value",)`` memo staleness hazard impossible by construction
  rather than by discipline. The my-side affordability cluster still invalidates wholesale under one
  manual attach, which is an argument for a fresh model, not against one.
* And the silent-divergence risk is answered by measurement rather than by prohibition: the seam's
  parity lane replays committed native traces one step at a time and diffs the synthesized model
  against the model built from the next recorded frame, with a divergence a ruled seam bug that
  QUARANTINES the option kind (`tests/parity/test_apply_seam_parity.py`).

Composes the knowledge seams (the Stat Provider ADR-0056, ``CardFunctions``, ``CombatMath``
ADR-0052, the Read) and takes per-decision facts as explicit arguments. It never imports or reads a
Pilot or a Board — the dependency runs one way, exactly as ``CombatMath`` does.

**The DELIBERATE bypass list** (POC-T1, Issue #260). The model is the sole data supplier, and after
T1 every board read on a model-covered question goes through it. Four kinds of direct ``CombatMath``
call survive, each for a reason that is a property of the QUESTION rather than an unfinished
migration — so the list is short, closed, and enforced by ``tests/strategy/test_combat_bypass_census``
rather than by review:

1. **Hypothetical enabler Budgets** (``_evolve_income_delta``, ``_promote_closure``). Every argument
   is a model read; what the model cannot supply is the hypothetical TARGET — a form the board does
   not carry in that configuration. A ``MySide`` method per hypothetical would move the assembly, not
   remove it.
2. **The empty-Budget second leg** (``_attach_value``, ``_active_arm_available``; the #142 idiom).
   "What can this body do with what is attached RIGHT NOW" is the baseline half of a counterfactual
   whose other half is the model's full-Budget read. The model route always carries the full Budget,
   so the empty leg has no model expression by construction.
3. **The one-fact-source rule** (``_recur_fueled_oa``). Its ``fueled`` gate and its augmentation must
   read the SAME discard or the doom relax could fire on a read that never counted its own fuel.
4. **Pure card arithmetic over a body dict** (``prize_value``, ``attached_type_counts`` — the Pilot's
   generic adapters and the planner's ``_payable_energy``). No board state, so two readers cannot
   diverge, which is the whole hazard the census exists to close; and every caller passes a synthetic
   or simulated body that is on no board.

Every one of those call sites carries the same note in-line, because a reader arrives at the call,
not at this docstring.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import NamedTuple

from common import card_worth
from common.board_cards import body_card_ids, body_unit_codes   # the ONE walk / the ONE unit read
from common.deck_odds import p_contains          # the Probability Leg's one implementation
from common.strategy.combat import UNCHARGED     # the doom policy — see `TheirSide.doomed`
from common.strategy.context import PRIZE_CARDS  # the rules' own 6 — `prizes_taken`'s other half
from common.strategy.damage_context import SideFacts        # the Damage Formula's ONE context
from common.strategy.damage_context import bench_gate_context   # ...and its matchup-free slice
from common.strategy.damage_context import damage_context as _assemble_damage_context

#: Sentinel for "use the policy threaded at :meth:`StateModel.build`". A clock consumer that wants a
#: DIFFERENT conservatism than the Read's — the catastrophe-grade doom budget, the deny Δ's zero-attach
#: budget, the ceiling — passes ``charged=`` explicitly, and ``None`` there means the worst-case
#: ceiling rather than "unset". The per-consumer conservatism is a PARAMETER by ADR-0064 Decision 1, so
#: the two readings must be distinguishable; a plain ``None`` default silently collapses them.
_THREADED = object()

#: Fallback Bench cap for an observation that omits the engine's own ``benchMax`` — the shipped
#: format's 5 (`docs/rulebook.txt` L75: *"Each player may have up to 5 Pokémon on the Bench at any
#: one time"*, restated at L122). Only a hand-built board ever reaches it; a real observation carries
#: the field, and reading THAT is what keeps the model honest if the format ever changes.
_BENCH_MAX = 5

# ── the lazy field descriptor ──────────────────────────────────────────────────────────────────

class lazy:
    """A memoized StateModel field — computed on first read, cached for the instance's life.

    The whole efficiency argument rests on this: a planner leaf that reads six fields pays for six,
    not for the Needs assignment DP and both clock curves it never touched. Access is recorded on
    the owner's ``_probe`` when one is attached, which is how the **Leaf Profile** measures the field
    set an evaluation actually touches (instrumentation only — never consulted by any derivation, so
    a probed build and an unprobed build return identical values).
    """

    def __init__(self, fn):
        self.fn = fn
        self.name = fn.__name__
        self.__doc__ = fn.__doc__

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        probe = obj._probe
        if probe is not None:
            probe.add(f"{obj._probe_prefix}.{self.name}")
        memo = obj._memo
        if self.name in memo:
            return memo[self.name]
        memo[self.name] = value = self.fn(obj)
        return value


class _Lazily:
    """Mixin supplying the memo dict and the (optional) access probe."""

    _probe_prefix = "?"

    def __init__(self, *, probe=None):
        self._memo: dict = {}
        self._probe = probe
        self._canon: dict = {}

    def _key(self, value):
        """``_canonical(value)``, memoized per OBJECT — the parameterised memos' key primitive.

        The clock reads key by VALUE rather than by ``id()`` because their callers construct
        temporaries (a stripped body, a spliced board — see :meth:`TheirSide.incoming`), and a freed
        temporary's address can be reallocated to a different body. But canonicalising a whole
        opponent board on every read is also the hot path of the per-decision build, so the
        projection is cached.

        Keyed on ``id()`` and yet sound, because the entry **holds a reference to the object**
        alongside its projection: an object that is cached cannot be collected, so its address cannot
        be reused while the entry lives. That is exactly the property a bare ``id()`` memo key lacks.
        The ``is`` re-check costs nothing and makes the invariant local rather than argued.

        Rests on the model's PURITY contract (ADR-0068): the observation does not change under a
        snapshot. Every ``id()``-keyed memo in this module already assumed that; this assumes no more.
        """
        if value is None or isinstance(value, (int, float, bool, str)):
            return value
        if isinstance(value, (list, tuple)):
            # Per-ELEMENT, deliberately. The counterfactual board lists differ from the real one by a
            # single entry (a removal, a spliced strip), and they are FRESH objects every call — so
            # caching the sequence wholesale would miss every time while re-walking every body it
            # shares with the last one. Caching the bodies and re-assembling is O(n) of dict lookups.
            return tuple(self._key(v) for v in value)
        hit = self._canon.get(id(value))
        if hit is not None and hit[0] is value:
            return hit[1]
        canon = _canonical(value)
        self._canon[id(value)] = (value, canon)
        return canon

    def _memoized(self, key, make):
        """Memo for a PARAMETERISED derivation (per-body budgets, the ``incoming(t)`` curve) — the
        same laziness as :class:`lazy`, keyed by argument rather than by field name."""
        if self._probe is not None:
            self._probe.add(f"{self._probe_prefix}.{key[0] if isinstance(key, tuple) else key}")
        memo = self._memo
        if key in memo:
            return memo[key]
        memo[key] = value = make()
        return value


# ── the Count Triple ──────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CountTriple:
    """A hidden-zone count in all three honest epistemics at once (ADR-0068).

    A bare "count" of something that might be sitting in my face-down prizes invites the mistake
    ``counts[T] >= 1`` on a deck that holds zero — an estimate smuggled into sound math, exactly the
    contamination ADR-0067 confines to ``readiness_p``. So the field never offers a bare number; a
    consumer must NAME its epistemic:

    - :attr:`floor` — provably AT LEAST this many (pigeonhole: more unseen copies than hidden prize
      slots). Sound; the only leg safe to compare against a cost.
    - :attr:`expected` — the hypergeometric split of unseen copies over deck and hidden prizes.
      A fraction of a card, for expectation math only; never comparable to a cost.
    - :attr:`ceiling` — provably AT MOST this many; the fail-OPEN leg. 0a's shipped sound type-set
      gate is exactly ``ceiling > 0`` (not-provably-empty), so the triple subsumes it rather than
      adding a third epistemic.
    - :attr:`p_any` — the **Probability Leg** (ADR-0074, #175): P(at least one copy is still in the
      deck), the honest middle the two boolean legs collapse. ≈0.06% wrong at 3 unseen copies where
      ``possible`` is nearly free, ≈13% wrong at 1 where ``floor`` is still zero. Readable ONLY by a
      consumer whose output is a compared scalar; a consumer whose output GATES must take a sound
      leg (see **Leg Assignment** in ``src/common/CONTEXT.md``). There is no threshold anywhere — a
      cut-off turns the estimate back into a boolean and re-imports the error it exists to price.

    Two regimes, ONE interface: before the first deck-revealing search the legs diverge; once that
    search anchors the prizes (``prizes_hidden == 0``) all three collapse to the same integer (and
    ``p_any`` to exactly 1.0 or 0.0). So no consumer ever branches on "are we anchored?" — the
    reason this shape beats a bare expectation.
    """
    floor: int = 0
    expected: float = 0.0
    ceiling: int = 0
    p_any: float = 0.0

    # `anchored` (floor == ceiling) was DELETED by POC-T1 (Issue #260). It offered exactly the
    # branch this class's own docstring forbids — "are we anchored?" — and had no consumer outside
    # its own tests. A reader that genuinely needs the regime compares the legs.

    @property
    def possible(self) -> bool:
        """Not provably absent — the fail-open presence gate (ADR-0067's deck-presence direction)."""
        return self.ceiling > 0


def count_triple(unseen: int, prizes_hidden: int, deck_count: int) -> CountTriple:
    """The legs for ``unseen`` copies split over ``deck_count`` deck slots and ``prizes_hidden``
    face-down prizes. Pure; total; never raises.

    Anchored (``prizes_hidden <= 0``) every unseen copy is in the deck, so the legs collapse. The
    floor is the pigeonhole surplus (copies that CANNOT all be prized), matching the sound step
    ``deck_odds.p_contains`` already takes at ``u > k`` — and ``p_any`` IS that function, so the
    boolean legs and the probability can never disagree about the same ``(u, k, d)`` (ADR-0074).
    """
    try:
        u, k, d = max(0, int(unseen)), max(0, int(prizes_hidden)), max(0, int(deck_count))
    except Exception:
        return CountTriple()                       # unreadable inputs claim nothing (fail-closed)
    if u == 0 or d == 0:
        return CountTriple()                       # no copies unseen, or no deck left to hold them
    if k == 0:
        n = min(u, d)                              # anchored: the split is resolved
        return CountTriple(floor=n, expected=float(n), ceiling=n, p_any=1.0)
    return CountTriple(floor=max(0, u - k),        # pigeonhole: this many cannot all be prized
                       expected=u * d / float(d + k),
                       ceiling=min(u, d),
                       p_any=p_contains(u, k, d))


# ── the Carried State channel ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CarriedState:
    """The narrow, DECLARED channel of facts that persist across decision points (ADR-0068).

    Everything else in the StateModel derives fresh from the observation. These cannot: they are
    memory. A member is read IN as an argument and handed BACK as a return value — the caller stores
    it — so no derivation mutates state as a side effect of being computed. That discipline is what
    keeps the model pure.

    v1 members: ``phase_prev`` (STABILIZE's Schmitt trigger) and ``my_path_prev`` (Prize-Path
    stickiness). Both were previously mutated DURING the Board build and defended by hand-written
    snapshot/restore at two separate planner sites — without which a planner fork's *hypothetical*
    phase leaks into the real game's memory. #149 adds ``known_top`` as a third member, whose update
    watches the observation's event log (shuffles, draws, deck-area moves) and fails CLOSED to None
    so consumers fall back to the ordinary hypergeometric-unknown.

    The StateModel reads a FROZEN snapshot of this as a build input and never writes it.
    """
    values: tuple = ()                             # ((name, value), …) — frozen, hashable-friendly

    #: The declared member names. A member absent from here is not Carried State — it is either an
    #: observation fact or a recomputable memo, and belongs in neither this channel nor a field
    #: that mutates on read.
    MEMBERS = ("phase_prev", "my_path_prev", "known_top")

    @classmethod
    def of(cls, **members) -> "CarriedState":
        """A snapshot from keyword members. Unknown names are REJECTED — the channel stays narrow by
        construction rather than by convention."""
        unknown = set(members) - set(cls.MEMBERS)
        if unknown:
            raise ValueError(f"undeclared Carried State member(s): {sorted(unknown)}")
        return cls(tuple(sorted(members.items(), key=lambda kv: kv[0])))

    def get(self, name, default=None):
        """The member's carried value, or ``default`` when never set (the fail-closed read: an
        absent belief must degrade to the ordinary unknown, never to a confident answer)."""
        for k, v in self.values:
            if k == name:
                return v
        return default

    # `with_` (a single-member rebind) was DELETED by POC-T1 (Issue #260): zero consumers. Every
    # real update writes the WHOLE channel through `CarriedState.of`, which is the shape that keeps
    # the "read in as an argument, handed back as a return value" discipline visible at the caller.


# ── body views ────────────────────────────────────────────────────────────────────────────────

class ForwardPayoff(NamedTuple):
    """What a body's evolution line still OWES it — the answer of BOTH sides' ``forward_payoff``.

    Two suppliers since Issue #285: :meth:`MySide.forward_payoff` computes all three legs from my
    decklist and my zones; :meth:`TheirSide.forward_payoff` computes the first two from card
    knowledge and fails OPEN on the third, because their deck is untracked. The shape is shared so
    the two sides price one line the same way; the divergence is argued at the their-side method.

    NAMED rather than a bare 3-tuple for the reason `state_value.ExposedBody` gives one field over:
    three positional values of three different kinds invite a transposed unpack that still runs and
    still returns a plausible number. Two of these are numbers and one is a flag, so a swap would be
    caught — but only after it had mis-priced a board."""

    #: Best printed damage anywhere in the forward closure MINUS the card's own, floored at 0.
    owed_damage: float
    #: How many evolutions away that best form is. 0 when the card is already the best form.
    hops: int
    #: Is every step of that path still available (not provably outside my deck)?
    reachable: bool


class AttackPayoff(NamedTuple):
    """What a body can actually pay off with on THIS board — :meth:`_SideBase.attack_payoff`'s
    answer.

    ``Attack``-prefixed on purpose: "payoff" is already spoken for one abstraction up, where
    `src/common/CONTEXT.md` uses it for the **Line** payoff — the evolved end-card a development
    line is aimed at (and coins *Stranded Payoff* for the case where it cannot be reached). This is
    the much smaller per-ATTACK quantity, and a bare `Payoff` would quietly overload the term.

    NAMED for the reason its siblings are, and with the id and the damage in ONE record rather than
    two accessors for a sharper reason than transposition: the two are only sound TOGETHER. The
    caller prices ``damage`` and then asks the odds machinery about ``attack_id``, and a consumer
    free to fetch one without the other is free to pair a max-damage payoff with a cheaper attack's
    probability — which saturates the term it feeds and prunes the very attach that would complete
    the payoff. Keeping them in one return makes the mismatch unspellable."""

    #: The attack whose damage this is. ``None`` when no attack record resolves.
    attack_id: int | None
    #: That attack's damage on this board, matchup-free — printed, with the attack's own board
    #: conditions applied (a bench-partner condition unmet reads 0). Never negative.
    damage: float


class AttackProfile(NamedTuple):
    """Everything ONE named attack of mine is worth asking about — :meth:`StateModel.attack_profile`.

    The substrate `attack_ev` needs and the model did not have (POC-T4/3, Issue #384). Its sibling
    :class:`AttackPayoff` answers *which attack pays best, matchup-free*, in two fields; the
    terminal-action term asks a larger question about ONE attack it has already named — its damage
    against the body actually in front of me, whether I can pay for it at all, and the rider /
    economy / lock facts `AttackStat` carries. **None of those last three had ANY model surface**:
    `attack_payoff` drops them by construction, so a `state_value`-side extractor would have had to
    reach past the model to `AttackStat`, which the sole-supplier ruling forbids
    (`docs/plans/value-system-poc-plan.md` §4-T0).

    ONE record rather than a family of accessors, for `AttackPayoff`'s own reason one abstraction
    down: these fields are only sound TOGETHER. The lock legs are priced against the damages of the
    attacks they lock out, and the rider legs against the bodies the damage leg is NOT aimed at — a
    consumer free to fetch one without the others is free to pair a rider's allocation with a
    different attack's lock, which is a phantom line rather than a small error.

    **Facts, never prices.** Every field here is a board or card quantity; the crossing into prizes
    is `state_value`'s and stays there. The two knapsack fields are the exception that proves it —
    they are the answers of shipped ORACLES (`CombatMath.spread_ko_prizes` / `snipe_ko_prizes`)
    about where a rider's payload lands, which is a question about the board and not about value.
    """

    #: The attack this profile is about — echoed back so a caller holding a tuple of profiles never
    #: has to re-associate them with the ids it asked for.
    attack_id: int | None
    #: Can the attacker pay this attack's cost and legally use it this turn, under the FULL Attach
    #: Budget? :meth:`MySide.reachable_attach`'s answer — never a raw energy count.
    affordable: bool
    #: Damage against THEIR Active through the damage model at ``bound="exact"`` — Weakness,
    #: Resistance, a prevention Ability, my live boosts and the Damage Formula's scalers all applied.
    damage: float
    #: The same read at ``bound="min"`` and ``bound="max"``: a conditional or coin attack's sound
    #: FLOOR and its CEILING. A deterministic attack reads its printed damage under every bound, so
    #: the three collapse and a caller needs no archetype branch.
    damage_floor: float
    damage_ceiling: float
    #: Does the RECORD carry a conditional clause — ``damageMin`` or ``damageMax`` set? The
    #: discriminator a bound policy needs, and it is a fact about the card rather than about the
    #: three numbers above, which is why it is carried and not inferred from them: a `requiresBench`
    #: attack whose partner is absent ALSO spreads its bounds (0 at exact/min, printed at max, by the
    #: oracle's own Incoming rule), and reading that spread as a coin would average a board gate.
    conditional: bool
    #: Damage MATCHUP-FREE (no defender), board conditions applied — `attack_payoff`'s read, per
    #: attack. What a NEXT-turn quantity must use: the defender next turn is not this one.
    printed: float
    #: The attack's own bench riders. ``bench_snipe`` is the INDIVISIBLE single-target rider
    #: (Jetting Blow's *"also does 50 damage to 1 of your opponent's Benched Pokémon"*);
    #: ``bench_spread`` is the DISTRIBUTABLE counter total (Phantom Dive's 6 counters -> 60). Both
    #: ignore Weakness and Resistance by rule (ADR-0022).
    bench_snipe: int
    bench_spread: int
    #: Prizes each rider's OWN allocation takes on their Bench — the shipped knapsacks, not a
    #: re-derivation. The spread leg is `CombatMath.spread_ko_prizes` (a SHARED budget across the
    #: whole Bench, so the subset question is a knapsack); the snipe leg is `snipe_ko_prizes` (one
    #: indivisible unit, so the best single body).
    snipe_ko_prizes: int
    spread_ko_prizes: int
    #: ``((hp_remaining, prize_value), …)`` for the benched bodies of theirs a rider can actually
    #: reach — bench-immune bodies (`docs/rules.md` §11) and empty slots excluded. The substrate for
    #: the caller's sub-Knock-Out band; the model says WHICH bodies, the term says what they are
    #: worth.
    rider_targets: tuple
    #: The energy-recycle rider's printed ceiling (Aura Jab: *"attach up to 3"*), and…
    recover_n: int
    #: …the Energy it would ACTUALLY attach that a recipient can ACTUALLY use — the min of that
    #: ceiling, the matching Basic-Energy fuel in the rider's source zone, and the recipients'
    #: remaining need. `Pilot._recover_units`' three closed-form bounds, re-derived from model
    #: facts (Issue #384); fractional for a whole-deck-search rider, whose fuel is an EXPECTED count.
    recover_units: float
    #: The ATTACKER-side next-turn locks (ADR-0033's vocabulary). ``self_lock`` is *"this Pokémon
    #: can't use attacks"*; ``same_attack_lock`` is *"can't use <THIS attack>"*. Two structurally
    #: different things — `strategy/sequence.py` prices them apart, because 270+130 == 130+270 makes
    #: a same-attack lock forfeit nothing while a full lock forfeits a turn of offense.
    self_lock: bool
    same_attack_lock: bool


#: The fail-closed profile — every leg at its zero, no claim made about anything. Returned for an
#: attack whose record does not resolve and for an absent body, so a caller never has a ``None``
#: branch to forget and never reads a plausible number the board does not support. The attack id is
#: filled in per call so telemetry can still name what was asked about.
_EMPTY_ATTACK_PROFILE = AttackProfile(
    attack_id=None, affordable=False, damage=0.0, damage_floor=0.0, damage_ceiling=0.0,
    conditional=False, printed=0.0, bench_snipe=0, bench_spread=0, snipe_ko_prizes=0,
    spread_ko_prizes=0, rider_targets=(), recover_n=0, recover_units=0.0, self_lock=False,
    same_attack_lock=False)


class BodyView(_Lazily):
    """One Pokémon in play, with its typed Energy and its attacks' typed cost shapes.

    The unit both sides share. Typed reads delegate to ``CombatMath`` rather than being
    re-implemented, so the model holds RESULTS while the oracle keeps the arithmetic — one home for
    the question, one home for the maths.
    """

    def __init__(self, body: dict, *, combat, is_active: bool, probe=None, prefix="body"):
        super().__init__(probe=probe)
        self._probe_prefix = prefix
        self.body = body or {}
        self._combat = combat
        self.is_active = bool(is_active)

    @property
    def card_id(self):
        return self.body.get("id")

    @lazy
    def stat(self):
        """The body's ``CardStat``; None when unknown (every downstream read then fails closed)."""
        return self._combat._card_stat(self.card_id)

    @lazy
    def hp_remaining(self) -> int:
        return int(self.body.get("hp") or 0)

    @lazy
    def damage_counters(self) -> int:
        """Damage counters ON this body — ``(maxHp - hp) // 10``, floored at 0.

        A counter is 10 damage (`docs/rulebook.txt` L172: *"put 1 damage counter on your opponent's
        Active Pokémon for each 10 damage"*; the glossary at L533 restates it — *"A counter put on
        your Pokémon to show it has taken 10 damage"*), so the count is the printed COUNTABLE a
        scaler names ("for each damage counter on this Pokémon"), not the damage. Both numbers are
        visible on every body in play, in both directions, which makes the family exactly priceable.

        Fail-closed on a body the observation gives without HP fields: ``maxHp`` and ``hp`` both read
        0 and the body claims no counters, rather than inventing a full bar's worth."""
        body = self.body
        return max(0, int(body.get("maxHp") or 0) - int(body.get("hp") or 0)) // 10

    @lazy
    def is_ex(self) -> bool:
        """This body is a Pokémon ``{ex}`` — **including a Mega Evolution Pokémon ex**, which IS an
        ``{ex}`` (`docs/rulebook.txt` L337). Card knowledge, so the answer comes off the ``CardStat``
        (``is_ex_body``) and the model only holds it. False without a resolvable stat: a body that
        makes no claim is not counted."""
        return bool(self.stat is not None and self.stat.is_ex_body)

    @lazy
    def is_stage2(self) -> bool:
        """This body is a Stage 2 Pokémon (engine ``CardData.stage2``). Fail-CLOSED on an
        unresolvable card, and the direction matters: the scaler that reads this counts the
        ATTACKER's own Bench, so over-reading it inflates MY damage estimate — which is the error
        class that manufactures a phantom lethal."""
        return bool(getattr(self.stat, "stage2", False))

    @lazy
    def attached_types(self) -> dict:
        """``{EnergyType: count}`` attached — the typed supply a cost shape is matched against."""
        return self._combat.attached_type_counts(self.body)

    @lazy
    def energy_count(self) -> int:
        """Energy UNITS attached — the raw count the rules speak in (a retreat cost is paid "in
        Energy", `docs/rules.md` §3 *Action economy*).

        Deliberately NOT ``sum(attached_types.values())``, which is what it used to be: that counts
        only the TYPED Basic Energy the colour matcher can resolve, so a Special Energy or an
        unresolvable card provides a unit with no type and the two numbers legitimately differ. The
        typed histogram is :attr:`attached_types` and it is the right read for a COST SHAPE; this is
        the right read for a count, and the distinction is why they are two fields rather than one
        (POC-T1, Issue #260 — the raw-read migration surfaced call sites that meant the count)."""
        return len(self.energy_key)

    @lazy
    def energy_key(self) -> tuple:
        """The attached Energy as a HASHABLE tuple of ``EnergyType`` codes — the value-memo key
        component for every read that depends on what this body is carrying, and the field
        :attr:`energy_count` measures.

        **Units, not cards** (Issue #297 corrected this docstring, which claimed card ids). The
        engine's ``Pokemon.energies`` is ``list[EnergyType]``: what the attached cards PROVIDE, so
        one Ignition Energy contributes ``(0, 0, 0)`` and one Rock Fighting Energy contributes
        ``(6,)``. That is the right key for this job — it is what a cost shape is paid with — and
        the right length for :attr:`energy_count`; the card identities live on ``energyCards`` and
        are read by :func:`~common.board_cards.body_card_ids`.

        The read itself is :func:`~common.board_cards.body_unit_codes`, shared with
        :attr:`~common.strategy.combat.CombatMath.attached_unit_codes` — one accessor, so no memo
        and no affordability leg re-invents it."""
        return body_unit_codes(self.body)

    # `attacks` and `attack_slots` were DELETED by POC-T1 (Issue #260): zero consumers, and both
    # were pass-throughs to card knowledge that has a home already — `stat.attacks` and
    # `CombatMath._attack_slots`. A body VIEW of a fact that does not depend on the body is a second
    # place to look for it, which is the cost the model exists to remove rather than to add.

    # No `payoff_attack` here, and its absence is the point (Issue #287). "Which attack pays best"
    # cannot be answered from the body alone: Cosmic Beam's damage depends on who is on the attacker's
    # BENCH, which a view of one body cannot see. The question therefore lives one level up, on
    # :meth:`_SideBase.payoff`, and it lives there ONCE — a body-scoped printed-only twin beside it
    # would be a second answer to one question, free to disagree in exactly the case that matters.

    @lazy
    def prize_value(self) -> int:
        """Prizes the opponent takes for knocking this body out — card knowledge, so it stays on the
        combat oracle (ADR-0052) and the model only holds the answer."""
        return self._combat.prize_value(self.body)

    @lazy
    def tool_ids(self) -> tuple:
        """Pokémon Tool card ids attached to this body, in attach order (POC-T1, Issue #260).

        Homes the ``attached_tools`` zone of the §3c completeness contract
        (:mod:`common.snapshot_coverage`). The raws already carried a ``tools`` key and four sites
        walked it by hand for four different questions — a Tool's damage boost, its retreat
        reduction, whether the slot is occupied, whether the Tool is irreplaceable. A Tool play is
        an option the T4 planner must be able to DIFFERENCE, and a zone with no public read prices
        that difference at 0, which under the composer's 1-ply ordering means *never explored*
        (ADR-0092 §3c). Ids rather than resolved stats, for the same reason as
        :attr:`_SideBase.discard_ids`: the id is what every downstream oracle keys on.
        """
        return tuple((c or {}).get("id") if isinstance(c, dict) else c
                     for c in (self.body.get("tools") or ())
                     if (c.get("id") if isinstance(c, dict) else c) is not None)

    @lazy
    def grant(self) -> dict:
        """The live ADR-0033 transient grant on this body — ``{}`` when none, or when the combat
        oracle carries no tracker (POC-T1, Issue #260).

        Homes the ``transient_grants`` zone of the §3c contract. Until now the only snapshot surface
        was :attr:`StateModel._transient_generation`, a PRIVATE cache-invalidation counter — the
        grants themselves were reachable only through ``CombatMath._grant``, which is a bypass on a
        board fact by T1's own acceptance criterion. Keys are the tracker's own vocabulary
        (``self_lock`` / ``same_lock`` / ``self_bonus`` / ``prevent_all`` / ``reduction``); the model
        holds the record and the oracle keeps applying it, exactly as it does for damage."""
        return dict(self._combat._grant(self.body) or {})


# ── the two sides ─────────────────────────────────────────────────────────────────────────────

class _SideBase(_Lazily):
    """What both sides expose. Asymmetric detail lives in the two subclasses, deliberately: my hand
    is cards and theirs is a number, and making that an AttributeError rather than a silently-None
    field is the point."""

    def __init__(self, player: dict, *, combat, probe=None, prefix="side", turn_boosts=()):
        super().__init__(probe=probe)
        self._probe_prefix = prefix
        self.player = player or {}
        self._combat = combat
        #: This side's this-turn flat damage-boost PLAYS, as ``TurnBoostTracker`` recorded them —
        #: ``((amount, attackerEnergyType|None, vsExOnly), …)``. Threaded in rather than derived
        #: because it is a fact about the LOG, not about the board: "During this turn, attacks used
        #: by your … Pokémon do N more damage" leaves no trace in any zone once the card is in the
        #: discard, so no snapshot of the board could recover it. The tracker is match-scoped and
        #: side-keyed, and only :meth:`StateModel.build` knows which seat is which, so the
        #: resolution happens there and the side holds the resolved tuple.
        self._turn_boosts = tuple(turn_boosts or ())

    # -- bodies ---------------------------------------------------------------------------------
    @lazy
    def active(self) -> BodyView | None:
        raw = next((p for p in (self.player.get("active") or []) if p), None)
        return None if raw is None else BodyView(raw, combat=self._combat, is_active=True,
                                                 probe=self._probe,
                                                 prefix=f"{self._probe_prefix}.active")

    @lazy
    def bench(self) -> tuple:
        return tuple(BodyView(p, combat=self._combat, is_active=False, probe=self._probe,
                              prefix=f"{self._probe_prefix}.bench")
                     for p in (self.player.get("bench") or []) if p)

    @lazy
    def bodies(self) -> tuple:
        """Active first, then bench — the iteration order every two-sided read shares."""
        return ((self.active,) if self.active is not None else ()) + self.bench

    @lazy
    def active_raw(self) -> dict | None:
        """The Active's raw engine dict — what ``CombatMath`` entry points still take."""
        return None if self.active is None else self.active.body

    @lazy
    def body_raws(self) -> tuple:
        return tuple(b.body for b in self.bodies)

    @lazy
    def bench_names(self) -> tuple:
        """The BENCHED bodies' card names, in bench order — ``""`` for a body whose card does not
        resolve, so the tuple stays positional rather than silently shortening.

        The Bench and only the Bench, which is the whole content of the fact: a bench-partner
        condition is printed as *"if you have Lunatone on your Bench"* (`data/EN_Card_Data.csv` 676),
        and a Lunatone in the Active spot does not satisfy it. Read by the damage oracle's
        ``requiresBench`` leg through ``atk_bench_names`` and by :meth:`payoff`; it lives here, once,
        because two hand-rolled walks of one fact are free to drift — the ruling
        :func:`~common.strategy.damage_context.damage_context` was extracted under (Issue #279)."""
        return tuple((b.stat.name if b.stat is not None else "") for b in self.bench)

    @lazy
    def in_play_names(self) -> tuple:
        """Every IN-PLAY body's card name — Active first, then Bench — ``""`` when the card does not
        resolve, so the tuple stays positional and an unknown body claims nothing.

        A different fact from :attr:`bench_names`, not a superset of it by accident: the condition
        that reads the Bench is printed *"on your Bench"*, and the filtered count that reads this one
        is printed *"for each Pokémon in play"* — and the Bench IS in play alongside the Active
        (`docs/rulebook.txt` L559: *"Your deck, your discard pile, and your Prize cards are not in
        play, but your Benched Pokémon are."*), so a Weezing in the Active spot DOES count itself.
        Feeds ``both_in_play_named`` through the ``both_in_play_names`` context key (Issue #361)."""
        return tuple((b.stat.name if b.stat is not None else "") for b in self.bodies)

    @lazy
    def in_play_attack_names(self) -> tuple:
        """Per IN-PLAY body (Active first, then Bench), that body's printed attack NAMES.

        The raw material of ``atk_in_play_with_attack`` — *"for each of your Pokémon in play that has
        the Round attack"*. NESTED, one tuple per body, because the predicate counts bodies: a flat
        list of names could not distinguish two Round-havers from one body carrying the name twice.
        A body whose card, or whose attack record, does not resolve contributes an EMPTY tuple —
        fail-closed, because this scaler multiplies MY OWN damage and an over-read is the direction
        that manufactures a phantom lethal (Issue #361)."""
        attack_stat = self._combat.attack_stat      # hoisted: the accessor rebuilds a fallback
        out = []                                    # lambda per call, and this is a per-attack loop
        for b in self.bodies:
            names = []
            for aid in (getattr(b.stat, "attacks", ()) or ()):
                ast = attack_stat(aid)
                if ast is not None and getattr(ast, "name", ""):
                    names.append(ast.name)
            out.append(tuple(names))
        return tuple(out)

    @lazy
    def bench_raws(self) -> tuple:
        """The BENCHED bodies' raw engine dicts — the Bench Harvest's input (ADR-0071 decision 7).

        A shared rider budget is a fact about the whole bench, so a per-body survival read cannot
        express it; the snapshot owns the list because it is lazy and pure (ADR-0068), which is what
        stops the bench shifting under a memoized clock."""
        return tuple(b.body for b in self.bench)

    def attack_payoff(self, body) -> AttackPayoff:
        """The best attack ``body`` can actually pay off with **on this board**, and its damage —
        the conditional counterpart of ``CardStat.maxDamage`` (Issue #287, ADR-0109).

        ``maxDamage`` is the PRINTED roll-up over a card's attacks, and a printed number cannot
        carry a board condition. Solrock's Cosmic Beam is *"70 … If you don't have Lunatone on your
        Bench, this attack does nothing"*, so its roll-up reads 70 on a Bench that will never pay it
        — and a term differencing that number cannot see the Lunatone arrive or leave.

        So this asks the damage oracle instead of forming a second opinion: ``requiresBench`` is
        already parsed off the attack's own sentence
        (:func:`~common.scouting.card_text.parse_attack_bench_requirement`) and
        :func:`~common.strategy.damage.compute_active_damage` already returns 0 for an unmet
        partner. The oracle is called **matchup-free** — no defender, so no Weakness/Resistance and
        no defender-side prevention enters, exactly as the printed roll-up it replaces carried none.
        Whose exposure to whom is `state_value`'s `threat`/`survival` question, and pricing it here
        as well would be the double-counting the registry exists to forbid.

        ``bound="exact"``, deliberately: the ``"max"`` bound keeps a conditional attack's ceiling
        because Incoming is a worst case and the opponent may bench the partner before attacking.
        This read is about MY (or their) board as it stands, where the Bench is what it is.

        The ATTACK ID travels with the damage because the two must name the same attack. A body
        whose biggest attack is gated still has its lesser one — so the fallback is *the best attack
        that pays*, not zero — and the odds leg (`readiness_p`) is asked about the attack whose cost
        actually has to be met. Pairing one attack's payoff with another's probability is the
        saturation defect that pruning story turns on.

        **When NOT ONE of the body's attacks resolves**, this degrades to the card-level
        ``CardStat.maxDamage`` roll-up under a null attack id — `CombatMath.predicted_max_damage`'s
        own per-attack-else-card-level rule, and the same pair the retired `payoff_attack` produced
        in that case. A partial provider is the only way there (`_build_cache` derives `maxDamage`
        from the attack table, so real data cannot have a roll-up without attacks), and it must not
        silently zero a real attacker: this read is a REASON to price 0, never a new way to. An
        unresolvable attack is also an attack whose condition is unreadable, so there is no gate to
        apply and nothing is being waived. ``AttackPayoff(None, 0.0)`` only for a body whose CARD
        does not resolve at all — fail-closed, the model's standing direction.

        Ties resolve to the FIRST attack in the card's own order, deterministic for the same reason
        every other tie-break in this module is.

        Lives on the side base rather than on :class:`BodyView` because the gate reads THIS side's
        Bench, which a body cannot see; and on the base rather than on :class:`MySide` because the
        condition is a fact about the attacker's own bench whichever seat that is — their Solrock is
        as dead without their Lunatone as mine is.

        Memoized by VALUE (card, the gating bench), like every other parameterised read here."""
        view = self.view_of(body)
        stat = view.stat if view is not None else None
        if stat is None:
            return AttackPayoff(None, 0.0)
        key = ("attack_payoff", stat.cardId, self.bench_names)

        def _make() -> AttackPayoff:
            context = bench_gate_context(self.bench_names)
            best, best_damage = None, -1.0
            for aid in (getattr(stat, "attacks", None) or ()):
                if self._combat.attack_stat(aid) is None:
                    continue               # unknown attack: make no claim about it either way
                damage = float(self._combat.predicted_damage(stat.cardId, aid, None,
                                                             bound="exact", context=context))
                if damage > best_damage:
                    best, best_damage = aid, damage
            if best is None:               # nothing resolved: the card-level roll-up, unconditioned
                return AttackPayoff(None, float(getattr(stat, "maxDamage", 0) or 0))
            return AttackPayoff(best, max(0.0, best_damage))

        return self._memoized(key, _make)

    def view_of(self, body) -> "BodyView | None":
        """The :class:`BodyView` for ``body`` — the RAW-engine-dict adapter (POC-T1, Issue #260).

        Every migrated consumer holds a raw engine dict (the Pilot and the planner get their bodies
        from the observation, not from the model), while the model's per-body reads are typed on
        ``BodyView``. Without one adapter each call site grows its own, and a hand-built view is a
        SECOND view of a body the snapshot already holds — it would miss the memo and, worse, could
        disagree with the snapshot's own view about a body's area. So the lookup is by IDENTITY
        against the bodies this side already exposes, and only a body this side does not hold gets a
        fresh view.

        The fallback is deliberate rather than a fail-closed None: the deny instruments price
        HYPOTHETICAL bodies (an Energy-stripped copy of a real one), which are by construction not on
        the board. Such a body is Active iff the body it stands in for is, and the caller knows that —
        hence ``is_active``'s default here is False and a caller pricing a stripped ACTIVE passes the
        real Active through :meth:`view_of` for the area-sensitive reads. ``None`` in, ``None`` out.
        """
        if body is None or isinstance(body, BodyView):
            return body
        for view in self.bodies:
            if view.body is body:
                return view
        return BodyView(body, combat=self._combat, is_active=False, probe=self._probe,
                        prefix=f"{self._probe_prefix}.hypothetical")

    @lazy
    def bench_count(self) -> int:
        """Bodies on this side's Bench. **THE** supplier of the count (POC-T1, Issue #260) — `Board`
        derived ``my_bench`` / ``bench_full`` / the opponent's bench tuple by re-walking the raw
        list at three sites, which is the two-readers-of-one-fact shape ADR-0087 charges for."""
        return len(self.bench)

    @lazy
    def bench_full(self) -> bool:
        """No room left on this side's Bench. Reads the engine's own ``benchMax`` rather than a
        constant, so a format that changes the cap moves the answer instead of the code — and falls
        back to the shipped 5 only when the observation omits it (fail toward the real rule)."""
        return self.bench_count >= int(self.player.get("benchMax") or _BENCH_MAX)

    @lazy
    def conditions(self) -> frozenset:
        """The Special Conditions in force on this side's ACTIVE (POC-T1, Issue #260).

        Homes the ``special_conditions`` zone of the §3c completeness contract. Only the Active can
        carry one (`docs/rules.md` §8), which is why the engine puts the five flags on
        ``PlayerState`` rather than on the body — so this is a SIDE-level read that describes a BODY,
        and the docstring says so rather than leaving the shape to be inferred.

        The whole set, not the two that block acting: :attr:`MySide.attack_blocked` collapses Asleep
        and Paralyzed into one boolean because that is all an affordability question needs, but
        Burned and Poisoned write damage counters at Checkup and Confused taxes an attack, and a
        differencing system that cannot see them prices their removal at 0. Names are the engine's
        own field names, lower-case, so the vocabulary has one spelling."""
        return frozenset(c for c in ("poisoned", "burned", "asleep", "paralyzed", "confused")
                         if self.player.get(c))

    # -- hand ------------------------------------------------------------------------------------
    @property
    def hand_size(self) -> int:
        """Cards in this side's hand — **required of both subclasses**, which is why it is declared
        here even though neither derivation lives here (POC-T3.5, Issue #279).

        The class docstring's rule is that asymmetric detail stays subclass-only, and it still holds
        for the CONTENTS: my hand is cards (:attr:`MySide.hand_ids`) and theirs is nothing at all.
        The SIZE is the one hand fact both sides can answer, which is exactly why the Damage Formula
        names it in both directions (`atk_hand`, `def_hand`) — and why :attr:`damage_facts` may read
        it off a plain ``_SideBase``. The two derivations differ (mine falls back to the card list
        when the observation omits ``handCount``; theirs has only the count), so this stays a
        declaration of the contract rather than an implementation: a subclass that forgets it gets
        this error, not a silently-zero hand feeding a scaler."""
        raise NotImplementedError(f"{type(self).__name__} must answer hand_size")

    # -- prizes / zones -------------------------------------------------------------------------
    @lazy
    def prizes_remaining(self) -> int:
        """Prizes this side still needs to take."""
        return len(self.player.get("prize") or [])

    @lazy
    def prizes_taken(self) -> int:
        """Prizes this side has ALREADY taken — the Damage Formula's ``*_prizes_taken`` countable.

        Deliberately NOT ``_PRIZE_CARDS - prizes_remaining``, and the difference is the fail
        direction rather than a style choice. :attr:`prizes_remaining` reads an absent ``prize`` zone
        as an empty list — the right answer for "how many are left to take" on a board that carries
        no zone — but subtracting that from 6 turns the absence into *"all six taken"*, the maximal
        positive claim, on exactly the hand-built boards where nothing is known. So the zone's
        ABSENCE is checked first and claims 0."""
        prize = self.player.get("prize")
        return max(0, PRIZE_CARDS - len(prize)) if prize is not None else 0

    @lazy
    def discard_energy_counts(self) -> dict:
        """``{EnergyType: count}`` of Basic Energy in this side's discard — a PUBLIC zone in both
        directions, so it is a sound count and never an estimate. Feeds the Attach Budget's
        discard-sourced clauses (mine) and the recursion-fuel read (theirs)."""
        out: Counter = Counter()
        for card in (self.player.get("discard") or []):
            cid = (card or {}).get("id")
            stat = self._combat._card_stat(cid) if cid is not None else None
            if stat is not None and stat.is_typed_basic_energy:
                out[stat.energyType] += 1
        return dict(out)

    @lazy
    def discard_ids(self) -> tuple:
        """Every card id in this side's discard, in zone order — the FULL public contents
        (POC-T0 / Issue #259, ADR-0092's "the StateModel is the SOLE data supplier" ruling).

        A discard pile is public in **both** directions (`docs/rulebook.txt` L541: *"The cards you
        have discarded. These cards are always face up. Anyone can look at these cards at any
        time."*), so this is sound knowledge about the opponent, not an estimate, and it belongs on
        the shared base rather than on `TheirSide` alone. Until now the model exposed only
        :meth:`discard_energy_counts` — a Basic-Energy projection — so every consumer wanting *what
        is actually in there* (a recur target, a Night Stretcher line, a used-up Item count, a rebuilt
        evolution line) had to reach past the model to the raw observation, which is precisely the
        bypass the standing ruling forbids.

        Ids rather than resolved stats, deliberately: a card id is what every downstream oracle keys
        on (`CardStat`, Function Tags, `deck_odds`), and resolving here would make the model hold a
        second opinion about card identity. Ordered rather than a multiset because the zone IS
        ordered and a consumer reasoning about the most recently discarded card (a same-turn
        recursion read) cannot recover that from counts.

        INERT at T0 — no consumer yet; T1 (Issue #260) migrates the raw-observation readers onto it.
        """
        return tuple((c or {}).get("id") for c in (self.player.get("discard") or [])
                     if (c or {}).get("id") is not None)

    @lazy
    def discard_energy_total(self) -> int:
        """EVERY Energy card in this side's discard — Basic and Special alike (POC-T3.5, Issue #279).

        The sibling of :attr:`discard_energy_counts`, and a genuinely different question rather than
        a projection of it: the typed histogram answers *which colours* the pile can supply (the
        Attach Budget's discard clauses, the recursion fuel), while this answers *how many Energy
        cards are in there* — which is what an UNTYPED Riptide-class scaler counts ("for each Energy
        card in your discard pile"). A Special Energy is in one and not the other, so collapsing them
        would under-read that scaler by exactly the Special Energy the pile holds.

        Reads :attr:`discard_ids` rather than re-walking the zone, so the two projections share one
        idea of what the zone contains. Unresolvable cards count 0 (fail-closed)."""
        return sum(1 for cid in self.discard_ids
                   if (st := self._combat._card_stat(cid)) is not None and st.is_energy)

    # -- the Damage Formula's per-side countables (POC-T3.5, Issue #279) ------------------------
    @lazy
    def damage_boosts(self) -> tuple:
        """Flat damage boosts live for THIS side's attacks — ``((amount, type, vsEx), …)``.

        Two sources, both open information in either direction, so both are read whichever side is
        attacking: the this-turn Trainer PLAYS the match-scoped tracker recorded
        (:attr:`_turn_boosts` — Premium Power Pro, Black Belt's Training) and the Tools ATTACHED to
        this side's Active (Maximum Belt), which are visible board state read off the holder.

        The tracker's own contract already draws that line (``transients.TurnBoostTracker``: *"Tool
        boosts are NOT tracked here — an attached Tool is visible board state, read directly at
        damage-context build"*), and this is that build. Play order first, then Tools, which is the
        order the shipped builder produced — the oracle sums them, so order is not load-bearing, but
        matching it keeps the two suppliers comparable key-for-key.

        A Tool whose boost is gated on an owner family (Hop's Choice Band — *"attacks used by the
        Hop's Pokémon this card is attached to"*, Issue #306) contributes only when the holder is in
        that family. The gate is the Tool's own `applies_to_holder`, so this site states the
        condition rather than re-deriving it."""
        out = list(self._turn_boosts)
        active = self.active
        for cid in (active.tool_ids if active is not None else ()):
            stat = self._combat._card_stat(cid)
            if (stat is not None and getattr(stat, "damageBoost", 0)
                    and stat.applies_to_holder(active.stat)):
                out.append((stat.damageBoost, stat.damageBoostType, stat.damageBoostVsEx))
        return tuple(out)

    @lazy
    def damage_facts(self) -> SideFacts:
        """This side's :class:`~common.strategy.damage_context.SideFacts` — every countable the
        Damage Formula can name about ONE side, direction-neutral.

        The gatherer both suppliers share. It records what this side HAS and never what it is doing:
        which of ``atk_``/``def_`` a fact becomes is
        :func:`~common.strategy.damage_context.damage_context`'s decision alone, made once, from the
        two records. That split is what makes a mirrored key impossible to get wrong at a gathering
        site — there is no mirroring here to get wrong.

        The deck leg comes from :meth:`_deck_facts`, which claims nothing on a side whose deck is not
        exactly known (every side but mine, and mine only once the prizes are anchored)."""
        active = self.active
        deck_count, deck_by_type = self._deck_facts()
        return SideFacts(
            hand_size=self.hand_size,
            active_energy=active.energy_count if active is not None else 0,
            bench_count=self.bench_count,
            prizes_taken=self.prizes_taken,
            active_counters=active.damage_counters if active is not None else 0,
            counters_in_play=sum(b.damage_counters for b in self.bodies),
            bench_stage2=sum(1 for b in self.bench if b.is_stage2),
            ex_in_play=sum(1 for b in self.bodies if b.is_ex),
            discard_energy_total=self.discard_energy_total,
            discard_basic_by_type=self.discard_energy_counts,
            bench_names=self.bench_names,
            in_play_names=self.in_play_names,
            in_play_attack_names=self.in_play_attack_names,
            damage_boosts=self.damage_boosts,
            deck_count=deck_count, deck_basic_by_type=deck_by_type)

    def _deck_facts(self) -> tuple:
        """``(deck_count, {EnergyType: Basic-Energy count})`` for a side whose deck is EXACTLY known,
        else ``(None, None)`` — the hook :attr:`damage_facts` reads.

        ``(None, None)`` on this base is the honest answer for the opponent, whose deck contents are
        hidden by construction, and the fail-closed default for a hand-built side. :class:`MySide`
        overrides it."""
        return (None, None)


class MySide(_SideBase):
    """MY half — the side with open information: real hand cards, the **Attach Budget**, per-body
    **Reachable Attach** and readiness, Needs coverage, and my deck's typed availability."""

    _probe_prefix = "mine"

    def __init__(self, player: dict, *, combat, deck=None, deck_empty=frozenset(),
                 own_prizes=None, needs=None, role_worth=None, energy_attached=False,
                 supporter_played=False,
                 more_prizes_than_opp=False, turn=0, probe=None, turn_boosts=()):
        super().__init__(player, combat=combat, probe=probe, prefix="mine",
                         turn_boosts=turn_boosts)
        self._deck = tuple(deck or ())
        self._deck_empty = frozenset(deck_empty or ())
        #: The deck tracker's exact prize multiset once a deck-revealing search has ANCHORED it, and
        #: ``None`` while it has not — the regime switch every leg of the Count Triple collapses on,
        #: and the ONE thing that decides whether this side may state its deck exactly
        #: (:meth:`_deck_facts`). ``None`` and ``{}`` are different answers: None is *"claim
        #: nothing"*, ``{}`` is an anchor that says *"no prizes left"*.
        #:
        #: A ``deck_known=`` constructor argument used to be threaded alongside it, carrying the
        #: tracker's ``{card id: copies left in my deck}`` because :attr:`unseen_counts` could not
        #: be trusted to reproduce it (Issue #279). Issue #297 fixed the field it distrusted — see
        #: :attr:`visible_counts` — so the threading is gone and the model derives the fact.
        self._own_prizes = own_prizes
        #: The caller-supplied Needs resolution and Role-Worth resolver the `state_value` families
        #: read (POC-T3, Issue #262). Both are RESOLVERS rather than facts, for the reason
        #: :meth:`role_worth` spells out: Roles are declared by the Strategy and the assignment is a
        #: DP over the hand, so neither is derivable from the snapshot the model holds.
        self._needs = needs
        self._role_worth = role_worth
        self.energy_attached = bool(energy_attached)
        self.supporter_played = bool(supporter_played)
        self.more_prizes_than_opp = bool(more_prizes_than_opp)
        self.turn = int(turn or 0)

    # -- hand -----------------------------------------------------------------------------------
    @lazy
    def hand_ids(self) -> tuple:
        return tuple(c["id"] for c in (self.player.get("hand") or [])
                     if c and c.get("id") is not None)

    @lazy
    def hand_size(self) -> int:
        """Cards in my hand — the COUNT, and deliberately not ``len(hand_ids)`` (POC-T1, Issue #260).

        :attr:`hand_ids` drops a card the observation gives without an ``id``; a count that inherited
        that filter would under-report the hand by exactly the cards a disruption read cares most
        about. The engine's own ``handCount`` is the authority where it is present — it is what the
        opponent's side reads — and the card list is the fallback for a hand-built board that omits
        it. Mirrors :attr:`TheirSide.hand_size`, so "how big is that hand" has ONE shape on both
        sides even though only mine can also say WHICH cards."""
        count = self.player.get("handCount")
        return int(count) if count is not None else len(self.player.get("hand") or [])

    @lazy
    def hand_energy_counts(self) -> dict:
        """``{EnergyType: count}`` of Basic Energy in my hand — the manual attach's immediately
        playable supply, as a COUNT because "one {R} left" and "three" are different decisions
        (the last-attachable-Energy read)."""
        counts: Counter = Counter()
        for cid in self.hand_ids:
            stat = self._combat._card_stat(cid)
            if stat is not None and stat.is_typed_basic_energy:
                counts[stat.energyType] += 1
        return dict(counts)

    @lazy
    def hand_energy_types(self) -> frozenset:
        """The TYPES of that supply — what the Attach Budget's manual-attach leg takes."""
        return frozenset(self.hand_energy_counts)

    # `needs` (a caller-supplied Needs resolution, held so several equations could share one
    # assignment) was DELETED by POC-T1 (Issue #260) together with its `needs=` constructor chain.
    # It was doubly dead: the ONE production builder never passed it, so the field was never written
    # AND never read. A seat nobody sits in is not architecture — it is a promise the next reader
    # will believe. T3's `readiness` term brings its own supplier when it needs one.

    def role_worth(self, card_id) -> float:
        """A card's **Worth**, in `card_worth` points — what job it does for THIS deck.

        ``role_worth`` is a CALLABLE ``card_id -> Worth``, mirroring :attr:`needs`'s resolver one
        accessor down — a mapping overload was written and removed, because a second accepted
        shape is a second thing to keep in step for no caller that wanted it.

        Roles are DECLARED (`Strategy.roles`), not a card fact: `card_worth.role_value`'s own
        docstring says so outright ("the Pilot supplies ``roles`` / ``tags`` / the two flags"), and
        `CardStat` carries neither. So the resolver is a caller-supplied callable, exactly like
        :attr:`needs` one accessor up, and for the same reason — the model holds the ANSWER so
        several equations read one opinion about what a body is for, instead of each re-deriving it.

        Without a resolver this falls back to what card facts alone can claim (the typed-Basic-Energy
        tier), which is 0 for any Pokémon. That is honest rather than useful, which is why
        `state_value` applies its own floor on top rather than letting an undeclared body price at
        exactly zero — see `state_value._role_relevance`."""
        key = ("role_worth", card_id)
        return self._memoized(key, lambda: self._role_worth_of(card_id))

    def _role_worth_of(self, card_id) -> float:
        if card_id is None:
            return 0.0
        resolver = self._role_worth
        if resolver is not None:
            return float(resolver(card_id) or 0.0)
        stat = self._combat._card_stat(card_id)
        if stat is None:
            return 0.0
        return card_worth.role_value(
            (), is_typed_basic_energy=bool(getattr(stat, "is_typed_basic_energy", False)))

    # -- deck availability (the Count Triple, ADR-0068 decision 4) ------------------------------
    @lazy
    def visible_counts(self) -> Counter:
        """My card copies provably OUTSIDE the deck: hand, discard, every board body (with its
        attached Energy CARDS, Tools and stacked pre-evolutions) and any FACE-UP prize. Face-down
        prizes and the deck itself stay uncounted — precisely the unknowns that keep the sound
        oracle sound.

        The body walk is :func:`~common.board_cards.body_card_ids` — the SAME one
        :meth:`~common.deck_tracker.OwnCardModel._visible` and ``Pilot._visible_card_counts`` take,
        which is the whole point (Issue #297). This used to walk its own key list, and that list led
        with ``energies`` — the Energy UNITS a body's cards PROVIDE, not the cards. It survived on
        the coincidence that the eight Basic Energy card ids equal their ``EnergyType`` codes and
        failed on the ninth Energy in the pool: an attached Ignition (card 17) renders ``[0, 0, 0]``
        and left card 17 counted as still in my deck, an attached Rock Fighting (card 20) renders
        ``[6]`` and decremented Basic {F} Energy instead of itself. Both errors reached the Attach
        Budget through :attr:`unseen_counts`, which is why the fix moved scoring."""
        counts: Counter = Counter()
        for zone in ("hand", "discard"):
            for card in (self.player.get(zone) or []):
                if card and card.get("id") is not None:
                    counts[card["id"]] += 1
        for prize in (self.player.get("prize") or []):
            if prize and prize.get("id") is not None:      # revealed; face-down prizes are None
                counts[prize["id"]] += 1
        for body in self.body_raws:
            for cid in body_card_ids(body):
                counts[cid] += 1
        return counts

    @lazy
    def unseen_counts(self) -> dict:
        """``{card id: copies not provably outside my deck}`` — decklist minus visible. ONE
        derivation, memoized: this exact expression was hand-rolled at four separate sites, which is
        the near-duplicate-read disease #138 exists to cure.

        Anchored (an exact ``own_prizes`` multiset from a deck-revealing search), the prized copies
        are also subtracted — once we know which cards sit in the prizes they are no longer
        candidates for the deck, and leaving them in would keep the Count Triple's legs apart after
        the regime they are supposed to collapse in.
        """
        unseen = Counter(self._deck)
        unseen.subtract(self.visible_counts)
        if self._own_prizes:
            unseen.subtract(Counter({int(k): v for k, v in dict(self._own_prizes).items()}))
        return {cid: n for cid, n in unseen.items() if n > 0}

    @lazy
    def prizes_hidden(self) -> int:
        """Face-down prizes of mine. 0 once the deck-tracker has anchored them (an exact
        ``own_prizes`` multiset from a deck-revealing search) — the regime switch every leg of the
        Count Triple collapses on."""
        if self._own_prizes:
            return 0
        return sum(1 for p in (self.player.get("prize") or [])
                   if not (isinstance(p, dict) and p.get("id") is not None))

    @lazy
    def deck_count(self) -> int:
        """Cards left in my deck. Pre-anchor this is the unseen pool minus the hidden prize slots
        (the composition the existing sites derive); anchored it is the unseen pool itself."""
        return max(0, sum(self.unseen_counts.values()) - self.prizes_hidden)

    @lazy
    def deck_energy_counts(self) -> dict:
        """``{EnergyType: CountTriple}`` — per-type Basic Energy still in my deck, in all three
        epistemics (ADR-0068 decision 4). The one derivation; :attr:`deck_energy_types` is its
        ``ceiling > 0`` projection, so the sound gate and the counts cannot disagree."""
        per_type: Counter = Counter()
        for cid, n in self.unseen_counts.items():
            stat = self._combat._card_stat(cid)
            if stat is not None and stat.is_typed_basic_energy:
                per_type[stat.energyType] += n
        hidden, deck = self.prizes_hidden, self.deck_count
        return {t: count_triple(n, hidden, deck) for t, n in per_type.items()}

    @lazy
    def deck_energy_types(self) -> frozenset:
        """Basic-Energy TYPES my deck can still yield — the SOUND *not-provably-empty* set the
        Attach Budget's deck-fetch leg takes (ADR-0067; 0a's shipped gate). Fails OPEN by design: a
        thin 3-copy suite proves nothing before a search anchors the prizes, and a strict gate would
        re-fire the very f70 famine the oracle exists to kill.

        Derived AS the Count Triple's ``possible`` (``ceiling > 0``) projection rather than from a
        parallel read, so the two epistemics agree by construction. ``deck_empty`` — the caller's
        sound emptiness oracle, when supplied — can only narrow further: both inputs are sound, so
        intersecting them stays sound, and a type is dropped the moment EITHER proves it gone.
        """
        return self._narrowed(frozenset(t for t, c in self.deck_energy_counts.items()
                                        if c.possible))

    @lazy
    def deck_energy_types_provable(self) -> frozenset:
        """The same set on the SOUND leg — the **Provable Budget**'s deck argument (ADR-0067's
        2026-07-27 amendment). A type counts only where the Count Triple's ``floor`` proves at least
        one copy CANNOT be prized (the pigeonhole), so this fails CLOSED where
        :attr:`deck_energy_types` fails open.

        Which leg a consumer takes is decided by what its error costs: a consumer about to STAND
        DOWN takes the open leg (a false famine is the f70 blunder), one about to SPEND something
        that expires unused takes this one. Expect it EMPTY pre-anchor for any realistic Energy
        suite — ``floor`` is zero whenever unseen copies do not outnumber the hidden prize slots —
        and expect both legs to coincide once a deck-revealing search anchors the prizes.
        """
        return self._narrowed(frozenset(t for t, c in self.deck_energy_counts.items()
                                        if c.floor >= 1))

    @lazy
    def deck_energy_p(self) -> dict:
        """``{EnergyType: P(my deck still holds >=1 of it)}`` — the **Probability Leg**'s side-level
        projection (ADR-0074, #175), the third reading of the ONE :attr:`deck_energy_counts`
        derivation alongside :attr:`deck_energy_types` (``ceiling > 0``) and
        :attr:`deck_energy_types_provable` (``floor >= 1``). One derivation, so the boolean legs and
        the probability cannot disagree about the same type.

        Read ONLY by a consumer whose output is a compared SCALAR — the ``ko_for_prizes`` ladder's
        weighted prize term, the attach/promote marginals. A consumer whose output GATES (the Win
        Rung) must take a sound leg; see **Leg Assignment** in ``src/common/CONTEXT.md``. A type the
        sound emptiness oracle has narrowed away reads **0.0** — a probability may sharpen the
        uncertain middle, never resurrect a type proven gone.
        """
        allowed = self.deck_energy_types                    # already `_narrowed`, so sound-capped
        return {t: (c.p_any if t in allowed else 0.0)
                for t, c in self.deck_energy_counts.items()}

    def _deck_facts(self) -> tuple:
        """The Damage Formula's hidden-scaler fuel: ``(cards left in my deck, {EnergyType: Basic
        Energy count})`` — exact, or ``(None, None)`` while the prizes are unresolved.

        A Hammer-lanche-class scaler discards the top N of the ATTACKER's deck and counts the Energy
        among them, so the oracle needs the deck's SIZE and its Energy fuel to turn hidden ORDER into
        a pigeonhole floor / hypergeometric mean (`strategy/damage.py`). Neither is knowable while
        unseen copies could still be sitting in a face-down prize, which is why the pair is absent
        rather than zero until the tracker anchors — see
        :func:`~common.strategy.damage_context.damage_context` for why that distinction is
        load-bearing at the oracle.

        DERIVED from :attr:`unseen_counts` (Issue #297), which is exactly *decklist − visible −
        prizes* once :attr:`_own_prizes` anchors — the same expression the deck tracker's Pilot-side
        consumer computes, now that :attr:`visible_counts` counts attached Energy by CARD. Absent
        before the anchor, because an unseen copy that could still be sitting in a face-down prize
        is not a deck claim."""
        if self._own_prizes is None:               # not anchored -> no exact deck claim
            return (None, None)
        known = self.unseen_counts
        if not known:
            return (None, None)
        by_type: Counter = Counter()
        for cid, n in known.items():
            stat = self._combat._card_stat(cid)
            if stat is not None and stat.is_typed_basic_energy:
                by_type[stat.energyType] += n
        return (sum(known.values()), dict(by_type))

    def _narrowed(self, types: frozenset) -> frozenset:
        """``types`` intersected with what the caller's sound emptiness oracle still allows. Both
        inputs are sound, so intersecting them stays sound on EITHER leg, and a type is dropped the
        moment either proves it gone."""
        if not self._deck_empty:
            return types
        surviving = frozenset(
            stat.energyType for cid in set(self._deck)
            if cid not in self._deck_empty
            and (stat := self._combat._card_stat(cid)) is not None
            and stat.is_typed_basic_energy)
        return types & surviving

    # -- the affordability family (0a's oracle; the model holds the RESULTS) --------------------
    def attach_budget(self, body: BodyView | None, *, manual_spent: bool = False,
                      provable: bool = False):
        """This turn's full **Attach Budget** toward ``body`` (ADR-0067).

        Memoized PER BODY, because the Budget genuinely is per-target: a bench-restricted clause
        (Wondrous Patch) funds one body and not another. Note the dependency edge this creates —
        one manual attach flips ``energy_attached``, changes a body's attached Energy and may spend
        the Supporter quota, invalidating EVERY cached Budget at once. That all-or-nothing pattern
        under the commonest in-turn action is a large part of why a fine-grained ``apply(action)``
        delta path was rejected: it would bookkeep per-field invalidation and then invalidate
        everything anyway (ADR-0068 decision 1).

        ``manual_spent`` forces the manual-attach leg CLOSED — "the Budget this body still has once
        the turn's one attachment is committed". It is what makes the attach marginal a true
        counterfactual (ADR-0069 §2): both legs of ``best_dmg(committed) − best_dmg(baseline)`` must
        price the SAME residual capacity, or every option on a body the accel already reaches would
        read as load-bearing. It only ever narrows the Budget, so a caller that omits it is
        unchanged.

        Keyed by VALUE — ``(card id, benched, manual_spent)`` — not by ``id(body)``. The Budget
        depends on the target only through its ``CardStat`` and its area (that is the whole of what
        ``attach_budget`` reads off it), so a value key is exact; and it lets the decider price a
        HYPOTHETICAL body (the real one plus an option's provision) against the real body's Budget
        without an identity-keyed memo that a freed-and-reallocated dict could collide with.
        """
        if body is None:
            return None
        return self.attach_budget_for_card(body.card_id, benched=not body.is_active,
                                           manual_spent=manual_spent, provable=provable)

    def attach_budget_for_card(self, card_id, *, benched: bool, manual_spent: bool = False,
                               provable: bool = False, supporter_spent: bool = False):
        """The Budget toward a card id rather than a body in play — for a HYPOTHETICAL attacker the
        board does not carry yet (the composed KO line's evolved form, #142).

        This is the real primitive and :meth:`attach_budget` is the BodyView-shaped face of it: the
        Budget reads its target only through the ``CardStat`` and the area, which is exactly this
        pair. Callers that assembled the zone arguments by hand went around the memo and had to keep
        seven kwargs in step with it; there is one assembly now.

        ``supporter_spent`` forces the SUPPORTER leg closed — "the Budget this body still has once
        the turn's one Supporter is committed" (ADR-0075 decision 3). It is the quota twin of
        ``manual_spent`` one leg over, and it exists because a KO line may play a Supporter as its
        own ENABLING step: a `rush_evolve` Salvatore or a `tutor_energy` Hilda spends the slot, so
        the Budget must not then also offer a Crispin play-set — two Supporters in one turn is an
        illegal line and the phantom KO it funds would be silent. Like ``manual_spent`` it only ever
        removes play-sets, so a caller that omits it is unchanged."""
        key = ("attach_budget", card_id, not benched, bool(manual_spent), bool(provable),
               bool(supporter_spent))
        return self._memoized(key, lambda: self._combat.attach_budget(
            {"id": card_id}, self.hand_ids,
            energy_attached=self.energy_attached or bool(manual_spent),
            supporter_played=self.supporter_played or bool(supporter_spent),
            deck_energy_types=(self.deck_energy_types_provable if provable
                               else self.deck_energy_types),
            hand_energy_types=self.hand_energy_types,
            discard_energy_counts=self.discard_energy_counts,
            target_benched=benched,
            more_prizes_than_opp=self.more_prizes_than_opp))

    def reachable_attach(self, body: BodyView | None, attack_id=None, *,
                         provable: bool = False) -> bool:
        """Can ``body`` pay (and legally use) an attack this turn under its Budget? ``attack_id``
        None asks the affordability half of the FAMINE question — is ANY attack reachable, scanning
        every attack rather than the cheapest, which is what makes the boolean sound once costs are
        typed. Works for ANY body and ANY attack, not Active-and-cheapest only.

        ``provable`` selects the **Provable Budget** (ADR-0067's amendment) — the sound deck leg for
        a consumer about to spend something that expires.

        A COST question only: it never asks whether the rules permit an attack at all. That half is
        :attr:`attack_blocked`, and :attr:`active_famine` is the two composed — see the note there.

        Keyed by VALUE, like the Budget it rests on: reachability depends on the body only through
        its ``CardStat``, its area and its attached Energy, so an identity key would buy nothing and
        could collide across a freed-and-reallocated dict."""
        if body is None:
            return False
        key = ("reachable_attach", body.card_id, body.is_active, body.energy_key,
               attack_id, bool(provable))
        return self._memoized(key, lambda: self._combat.reachable_attach(
            body.body, attack_id, budget=self.attach_budget(body, provable=provable)))

    @lazy
    def attack_blocked(self) -> bool:
        """The rules forbid me an attack this turn AT ALL, whatever my Energy says.

        Three facts, all verified at source and none of them expressible as a cost:
        **Asleep** ("If a Pokémon is Asleep, it cannot attack or retreat", `docs/rulebook.txt` L190),
        **Paralyzed** (same wording, L206 — L215 confirms these two are the only conditions that
        block retreat), and the **first player on turn 1** (the starting player skips the attack
        step, rulebook L152 / `docs/rules.md` §first-turn; ``turn <= 1`` is the idiom every other
        site in this codebase already uses for it).

        A SIDE-level read on purpose: the condition flags ride on the engine's ``PlayerState``, not
        on the body, so pushing them into the body-scoped oracle would mean handing ``CombatMath`` a
        player. It stays typed cost plus ADR-0033 locks; this is the layer that knows the rest."""
        if self.turn <= 1:
            return True
        return bool(self.player.get("asleep") or self.player.get("paralyzed"))

    @lazy
    def active_famine(self) -> bool:
        """**Famine**: my Active cannot attack this turn — the premise the stall-gust family had
        wrong at f70, and the one this model exists to answer once (ADR-0067, amended 2026-07-27).

        Composed rather than derived in a consumer, so every reader inherits BOTH halves: the
        rule-level :attr:`attack_blocked` and the affordability :meth:`reachable_attach` over the
        FULL (fail-open) Budget. Never "0 Energy attached", never "the cheapest attack is unpayable",
        and never a body the rules will not let swing however rich its Budget.

        **Fail-OPEN on an unreadable body**, which is the opposite of the oracle it calls.
        :meth:`reachable_attach` fails CLOSED — an unknown ``CardStat`` makes NO claim, so it returns
        False — and negating that would turn "I cannot tell" into "PROVABLE famine", firing the very
        +105 stall this premise exists to kill. The retired signal was explicit about the direction
        ("True on unknown stats — the starved stall-gust must only fire on a PROVABLE famine",
        ep83457493 f20) and it is preserved here rather than inverted. So the unknown body is checked
        BEFORE the oracle is asked, and only the RULE leg may claim a famine without one."""
        if self.attack_blocked:
            return True                     # the rules settle it without reading a single stat
        body = self.active
        if body is None or body.stat is None:
            return False                    # no claim — an unreadable body is not a demonstrable famine
        return not self.reachable_attach(body)

    def best_reachable_damage(self, body: BodyView | None, *, extra_energy_ids=(),
                              manual_spent: bool = False) -> float:
        """Biggest PRINTED damage ``body`` can reach this turn under its Budget — optionally over a
        HYPOTHETICAL body carrying ``extra_energy_ids`` on top of the Energy it already holds.

        The two legs of the attach counterfactual (ADR-0069 §2) are this read with and without the
        option's provision, at the SAME ``manual_spent`` residual capacity. The hypothetical body
        shares the real one's Budget by construction — ``attach_budget`` reads the target only
        through its ``CardStat`` and its area, neither of which an attach changes — so committing an
        Energy never silently re-prices the accel clauses it is being compared against.

        Memoized by VALUE (card, area, attached Energy, provision, residual capacity), so the
        per-option sweep over an attach menu pays once per distinct hypothetical body rather than
        once per option."""
        if body is None:
            return 0.0
        extra = tuple(extra_energy_ids)
        key = ("best_reachable_damage", body.card_id, body.is_active, body.energy_key,
               extra, bool(manual_spent))

        def _make():
            raw = body.body if not extra else dict(
                body.body, energies=list(body.body.get("energies") or ()) + list(extra))
            return self._combat.best_reachable_damage(
                raw, budget=self.attach_budget(body, manual_spent=manual_spent))
        return self._memoized(key, _make)

    def best_reachable_damage_vs(self, body: BodyView | None, defender: BodyView | None, *,
                                 context: dict | None = None) -> float:
        """Biggest damage ``body`` can reach this turn AGAINST ``defender`` — the sibling of
        :meth:`best_reachable_damage` that asks the damage model instead of the printed number, so
        Weakness, Resistance, a prevention Ability and a live damage boost all reach the answer
        (Issue #281, POC-T3.5).

        The two are NOT interchangeable and the incumbent is not the poorer one. `attach_value`'s
        counterfactual wants the opponent-independent printed read by construction (ADR-0069 §2);
        an offensive reachability GATE — *can I actually take this Knock Out* — wants this one. The
        printed read said yes to a Knock Out a Crustle prevents outright and no to the Weakness
        Knock Out `mega_starmie`'s whole doctrine is built on, so the gap was live in both
        directions.

        ``context`` is the Damage Formula's scaler context for the direction being priced —
        :meth:`StateModel.damage_context` at ``attacker="mine"``, since the attacker here is MINE.
        Omitting it is sound but weak: a scaling attack's variable contributes 0
        (`strategy/damage.py`), which under-reads my own damage rather than inventing it.

        Memoized by VALUE on the components the incumbent keys on and that vary here — card, area,
        attached Energy — plus the two that are new: the DEFENDER and the context. The incumbent's
        ``extra_energy_ids`` and ``manual_spent`` legs are deliberately NOT carried: both exist for
        `attach_value`'s counterfactual PAIR (the same body with and without an option's provision,
        at the same residual capacity), a comparison this read is not part of. A keyword no caller
        passes is a surface that can only drift, so the Budget here is always the body's own and
        residual capacity is constant rather than keyed.

        The defender is canonicalised rather than keyed by ``id()`` for :meth:`_Lazily._key`'s
        reason: a counterfactual caller may hand this a temporary body, and a freed temporary's
        address is free to be reallocated."""
        if body is None:
            return 0.0
        target = defender.body if defender is not None else None
        key = ("best_reachable_damage_vs", body.card_id, body.is_active, body.energy_key,
               self._key(target), self._key(context))
        return self._memoized(key, lambda: self._combat.best_reachable_damage_vs(
            body.body, target, budget=self.attach_budget(body), context=context))

    def best_reachable_bench_damage(self, body: BodyView | None,
                                    defender: BodyView | None) -> float:
        """Biggest damage ``body`` can put on ONE of their **BENCHED** bodies this turn — the bench
        route, which is the attack's snipe RIDER and not its printed damage (Issue #284, POC-T3.5).

        The third member of the reachability family, beside :meth:`best_reachable_damage` (printed,
        opponent-independent — `attach_value`'s counterfactual leg) and
        :meth:`best_reachable_damage_vs` (the damage model against a defending ACTIVE). Three
        questions, three methods; see :meth:`~common.strategy.combat.CombatMath.best_reachable_bench_damage`
        for why a rider is a different route rather than a different defender, and why the read is
        the single-target snipe rather than the snipe-plus-spread worst case.

        **No ``context``, and that is not an omission.** The Damage Formula scales an attack's
        damage; a rider is a printed constant that ignores Weakness and Resistance by rule
        (ADR-0022), so no scaler reaches it and a context here would key a memo on a value nothing
        consumes. `_exposed_bodies` records the mirror of this on the other side of the board.

        Memoized by VALUE on the same components as the ``_vs`` sibling minus the context — card,
        area, attached Energy, canonicalised defender. The defender is keyed rather than dropped
        even though only its bench-immunity is read today: it is an input, and a memo that ignored
        an input would be wrong the moment a later leg reads more of it."""
        if body is None:
            return 0.0
        target = defender.body if defender is not None else None
        key = ("best_reachable_bench_damage", body.card_id, body.is_active, body.energy_key,
               self._key(target))
        return self._memoized(key, lambda: self._combat.best_reachable_bench_damage(
            body.body, target, budget=self.attach_budget(body)))

    def readiness_p(self, body: BodyView | None, attack_id=None, *, enabler_budget=None,
                    copies: int = 0, pool: int = 0, draws: int = 0, weighted: bool = True) -> float:
        """P(``body`` is ready to use the attack this turn) — the EV variant, and the ONLY place an
        honest probability enters the affordability family (ADR-0067's split). Fails closed at 0.0.

        ``weighted`` (default True, ADR-0074 decision 6) also prices the deck-fetch leg by
        :attr:`deck_energy_p`. This is a RANKED consumer's reading by construction — it returns a
        compared scalar, never a gate — so the Probability Leg belongs here. Pass ``weighted=False``
        for the pre-#175 fail-open deck leg."""
        if body is None:
            return 0.0
        return self._combat.readiness_p(body.body, attack_id, budget=self.attach_budget(body),
                                        enabler_budget=enabler_budget, copies=copies,
                                        pool=pool, draws=draws,
                                        p_by_type=self.deck_energy_p if weighted else None)

    def turns_to_afford(self, body, *, attaches_per_turn: int = 1,
                        exclude_expiring: bool = False) -> int | None:
        """**The Two Clocks**, my half (ADR-0070 §6): the earliest future turn ``body``'s line is
        ARMED — the MAX of the energy-deficit leg and the FORWARD-HOP leg, never the sum.

        The mirror of :meth:`TheirSide.turns_to_afford`, which has carried this read since the deny
        clock (S1c) but only for the opponent's bodies. The evolve decider needs it for MY bodies:
        evolving removes one forward hop, so the Δ across the hop is what an evolve buys on the
        armed side — and where the energy leg dominates, that Δ is honestly zero. Uses the
        pool-level forward index (my own deck's forward forms are exactly the right availability
        gate for my line). None when unknown — fail-closed, the caller then makes no claim.

        Takes a :class:`BodyView` or a raw engine dict (see :meth:`view_of`), and keyed by VALUE for
        the reason spelled out on :meth:`TheirSide.incoming`. There is deliberately NO ``fuelled`` leg
        here, unlike the their-side twin: ``discard_energy_recur`` is a fact about the OPPONENT's
        clock in every consumer that reads it, and neither shipped line sits in one of our decks — so
        crediting my own reload would be an unexercised code path, and an unexercised credit on MY
        clock fails in the unsafe direction (it would price a line as armed sooner than it is).

        ``exclude_expiring`` (Issue #286, POC-T3.5) asks the same clock about the board this body
        will actually stand on NEXT turn: Energy the rules discard at the END of this turn
        (Ignition's ``discard_eot`` rider) is removed first, through
        :meth:`~common.strategy.combat.CombatMath.without_expiring_energy`. A FORWARD clock counting
        an Energy that will not be there is not conservative, it is wrong — Mega Starmie ex holding
        one Ignition reads *armed now* and is three attaches from Nebula Beam the moment the turn
        ends.

        It is a SIBLING reading and the incumbent is deliberately untouched, because
        :meth:`~common.strategy.combat.CombatMath.turns_to_afford` is shared with the deny clock for
        THEIR bodies (`pilot._opp_turns_to_ready` *"DELEGATES here (byte-identical)"*) and
        `attach_value`'s ADR-0069 counterfactual reads its own leg beside it. Teaching the oracle the
        rider would move corpus-ruled decisions on the other side of the board; a flag nobody else
        passes cannot. Keyed into the memo, and keyed on the REAL body — the hypothetical is derived
        inside, so two callers asking different questions about one body never collide."""
        view = self.view_of(body)
        if view is None:
            return None
        return self._memoized(("mine_turns_to_afford", self._key(view.body), attaches_per_turn,
                               bool(exclude_expiring)),
                              lambda: self._combat.turns_to_afford(
                                  self._combat.without_expiring_energy(view.body)
                                  if exclude_expiring else view.body,
                                  attaches_per_turn=attaches_per_turn, typed=True))

    # `famine` was DELETED by POC-T1 (Issue #260). It was `active_famine` MINUS the rule leg — the
    # affordability half alone — so a consumer taking it would have missed Asleep, Paralyzed and the
    # first player's turn-1 attack ban, which is the f70 blunder class one door over. Two names for
    # one premise, differing silently in what they check, is exactly what the composed read exists to
    # prevent; `active_famine` is the premise.

    @lazy
    def needs(self):
        """The position's Needs slots (deadline-tagged, ADR-0065's glossary) as resolved by the
        caller, or None when not supplied. The model does not own the Needs engine; it holds the
        resolution so several equations read one assignment instead of each re-running the DP."""
        resolver = self._needs
        return resolver() if callable(resolver) else resolver

    # -- evolution topology (the forward closure over MY decklist) ------------------------------
    @lazy
    def forward_index(self) -> dict:
        """``{pre-evolution NAME: (card ids in my deck that evolve from it, …)}``.

        Derived from my decklist and `CardStat.evolvesFrom` — card knowledge plus the deck I
        declared, both of which the snapshot already holds, so this needs no oracle it does not
        have. Evolution is by NAME in this set (`docs/rules.md` §4; the card names its previous
        stage), which is also why an id-keyed index would not work.

        MY deck rather than a universal index on purpose: a forward form I do not run is not a form
        my line can reach, and pricing topology against cards that are not in the box would credit
        an evolution that can never arrive.
        """
        index: dict = {}
        for cid in set(self._deck):
            stat = self._combat._card_stat(cid)
            base = getattr(stat, "evolvesFrom", None) if stat is not None else None
            if base:
                index.setdefault(base, []).append(cid)
        return {name: tuple(sorted(ids)) for name, ids in index.items()}

    def forward_form_ids(self, card_id) -> frozenset:
        """Every card id in ``card_id``'s forward closure — the forms this line can still BECOME,
        multi-hop, from MY decklist (POC-T4/3, Issue #384).

        The flat sibling of :meth:`forward_payoff`, which walks the same closure but needs each
        node's hop count and reachability and so cannot hand back a set. Extracted rather than
        inlined at its one caller because "what can this body become" now has two askers and the
        Riolu -> Mega Lucario ex SINGLE hop is exactly the kind of fact two walks would be free to
        disagree about.

        **MY deck, not the universal pool** — the divergence from the Pilot's
        `_forward_card_ids` (`CardStatProvider.forward_card_ids`, every printing in the set) is
        deliberate and is :attr:`forward_index`'s own standing doctrine: *"a forward form I do not
        run is not a form my line can reach"*. The universal read is right for the Pilot's question
        (what can THEIR benched pre-evolution become — their deck is untracked); it is wrong for
        mine, where the decklist is declared.

        Cycle-guarded for :meth:`_forward_payoff`'s reason: the rules cannot produce an evolution
        cycle, but a data slip must not hang a value equation on the grader."""
        return self._memoized(("forward_form_ids", card_id),
                              lambda: self._forward_form_ids(card_id))

    def _forward_form_ids(self, card_id) -> frozenset:
        stat = self._combat._card_stat(card_id) if card_id is not None else None
        if stat is None:
            return frozenset()
        out: set = set()
        frontier = [getattr(stat, "name", None)]
        while frontier:
            for nxt in self.forward_index.get(frontier.pop() or "", ()):
                if nxt in out:
                    continue
                out.add(nxt)
                nstat = self._combat._card_stat(nxt)
                if nstat is not None:
                    frontier.append(getattr(nstat, "name", None))
        return frozenset(out)

    def forward_payoff(self, card_id) -> "ForwardPayoff":
        """:class:`ForwardPayoff` for ``card_id``'s line — what evolving it still OWES.

        ``owed_damage`` is the best printed damage anywhere in the card's forward closure MINUS the
        card's own, floored at 0 (a forward form that hits softer owes nothing); ``hops`` is how
        many evolutions away that best form is; ``reachable`` is whether every step of that path is
        still available — at least one copy not provably outside my deck, or in hand.

        Reachability is what makes this topology rather than trivia: a Stage-1 whose only two copies
        sit in the discard leaves its base a dead end however well funded it is, and
        :attr:`unseen_counts` is the sound read of "not provably gone" the rest of this class
        already uses. **Card knowledge only** — no engine, no observation beyond the zones the
        snapshot already owns.

        Fails closed at ``ForwardPayoff(0.0, 0, True)`` for an unknown card: no claim, and no
        phantom penalty."""
        return self._memoized(("forward_payoff", card_id), lambda: self._forward_payoff(card_id))

    def _forward_payoff(self, card_id) -> "ForwardPayoff":
        stat = self._combat._card_stat(card_id) if card_id is not None else None
        if stat is None:
            return ForwardPayoff(0.0, 0, True)
        own = float(getattr(stat, "maxDamage", 0) or 0)
        held = set(self.hand_ids)
        unseen = self.unseen_counts
        best = ForwardPayoff(0.0, 0, True)
        # Breadth-first over the forward closure. `seen` guards a self-referential decklist rather
        # than a real evolution cycle — the rules cannot produce one, but a data slip must not hang
        # a value equation on the grader.
        frontier = [(card_id, getattr(stat, "name", None), 0, True)]
        seen = {card_id}
        while frontier:
            _cid, name, hops, live = frontier.pop()
            for nxt in self.forward_index.get(name or "", ()):
                if nxt in seen:
                    continue
                seen.add(nxt)
                nstat = self._combat._card_stat(nxt)
                if nstat is None:
                    continue
                nlive = live and (unseen.get(nxt, 0) > 0 or nxt in held)
                owed = max(0.0, float(getattr(nstat, "maxDamage", 0) or 0) - own)
                if owed > best.owed_damage:
                    best = ForwardPayoff(owed, hops + 1, nlive)
                frontier.append((nxt, getattr(nstat, "name", None), hops + 1, nlive))
        return best


class TheirSide(_SideBase):
    """THEIR half — the side with hidden information: hand SIZE only, the clock family, the
    archetype Read, and the recursion fuel their discard makes live."""

    _probe_prefix = "theirs"

    def __init__(self, player: dict, *, combat, read=None, brief=None, matchup_plan=None,
                 posture_confidence=0.0, favorability=0.5, matchup_coverage=0.0,
                 opponent=None, forward_ids=None, charged=None, probe=None, turn_boosts=()):
        super().__init__(player, combat=combat, probe=probe, prefix="theirs",
                         turn_boosts=turn_boosts)
        self.read = read
        self.brief = brief
        self.matchup_plan = matchup_plan
        self.posture_confidence = float(posture_confidence or 0.0)
        self.favorability = float(favorability if favorability is not None else 0.5)
        self.matchup_coverage = float(matchup_coverage or 0.0)
        #: The Opponent Model facade (ADR-0047) — ALL opponent knowledge beyond the visible zones.
        #: v1 exposes it as a handle rather than growing a rival inference layer here.
        self.opponent = opponent
        self._forward_ids = forward_ids
        self._charged = charged

    @lazy
    def hand_size(self) -> int:
        """Cards in their hand. The engine gives the count and never the contents (``hand`` is None
        for the opponent), so this is the whole of v1's hand knowledge — anything richer is
        cross-decision inference with no Phase-1 consumer, and belongs behind the facade.

        **This is THE supplier of the opponent hand count** (POC-T0 / Issue #259). `Board`'s
        `opp_hand_size` reads ``handCount`` off the raw observation at `pilot.py`, and two readers of
        one fact is the shape ADR-0087 charges for — they cannot disagree today, which is exactly why
        the drift would be invisible when one of them later grows a policy (a Read-adjusted estimate,
        a post-disruption projection). T1 (Issue #260) re-points `Board` here; the frozen contract is
        that the raw read has ONE home and it is this method."""
        return int(self.player.get("handCount") or 0)

    @lazy
    def deck_count(self) -> int:
        return int(self.player.get("deckCount") or 0)

    # -- the clock family (ADR-0064 / the Threat-Clock unification) -----------------------------
    def _bodies(self, bodies):
        """The opponent board a clock read runs against — their real one unless a COUNTERFACTUAL list
        is supplied (POC-T1, Issue #260).

        The removal Δ (``opponent_target_value``: how much survival does killing this body buy?), the
        Energy-strip Δ (Deny Relevance) and the per-body threat read (Snipe Relevance) are all
        questions about a board that is not the board — ``bodies[:i] + bodies[i+1:]``, a stripped copy
        spliced in, one body alone. That is why each of them bypassed the model: the old signature
        could only ask about the WHOLE side, so the model was strictly less expressive than the oracle
        beneath it. It is a first-class question, not an escape hatch, so it becomes a parameter and
        the threaded ``forward_ids`` / ``charged`` policy travels with it.
        """
        return self.body_raws if bodies is None else tuple(bodies)

    def _charged_policy(self, charged):
        """The energy policy for one clock read: the Read's threaded budget unless the consumer names
        its own (ADR-0064 Decision 1 keeps the conservatism per-consumer). ``None`` passed explicitly
        is the worst-case CEILING — a real policy, distinct from "unset", which is why the default is
        a sentinel rather than ``None``."""
        return self._charged if charged is _THREADED else charged

    def incoming(self, my_body: dict | None, t: int = 1, *, bodies=None,
                 charged=_THREADED, forward_ids=_THREADED, evo_min_energy: int = 0,
                 context: dict | None = None, my_benched: bool = False,
                 opp_active: dict | None = None, switch_enabler: bool = False) -> int:
        """Worst W/R-adjusted damage their affordable attackers could deal ``my_body`` at future turn
        ``t`` — the Threat-Clock curve, memoized by VALUE over every argument. ``t=1`` is Reachable
        Incoming.

        ``bodies`` names the counterfactual opponent board (see :meth:`_bodies`); ``charged`` the
        energy policy (see :meth:`_charged_policy`); ``forward_ids`` the AVAILABILITY gate, defaulting
        to the index threaded at build. Overriding the gate is how a caller asks about the CURRENT
        forms only — pass ``combat.CURRENT_FORMS_ONLY`` — which is a real question (`Board`'s
        ``incoming_active_damage`` exposes it so a +HP Tool can test a survival breakpoint against
        what the body in front of me hits for TODAY) and not a way around the index. The remaining
        kwargs are the oracle's own and are documented on ``CombatMath.incoming`` — they are here
        because the bypass census carried them (POC-T1, Issue #260), and a model route that cannot
        express what its callers ask is a route nobody takes.

        **Keyed by VALUE, not by ``id()``.** Every argument is in the key — a memo that silently
        ignores one is a trap this method already had to be fixed for once (Issue #213) — and the key
        canonicalises the body dicts rather than hashing their addresses. Identity keys were safe only
        while every body came off the live observation and outlived the memo; the counterfactual
        callers above construct TEMPORARIES (a stripped copy, a spliced list), and a freed temporary's
        address is free to be reallocated to a different body, which would serve one body's clock as
        another's. Same reasoning as ``MySide.attach_budget``'s value key, one side over.
        """
        opp_bodies = self._bodies(bodies)
        policy = self._charged_policy(charged)
        fwd = self._forward_ids if forward_ids is _THREADED else forward_ids
        # `fwd` goes into the key AS THE CALLABLE, not as its id(): a function is hashable, and the
        # key then holds a reference to it, so a freshly-built closure can only cost a memo MISS —
        # never an id collision serving a different index's answer. Callers wanting reuse pass a
        # stable callable (`combat.CURRENT_FORMS_ONLY`).
        key = ("incoming", self._key(my_body), t, self._key(opp_bodies), self._key(policy), fwd,
               evo_min_energy, self._key(context), bool(my_benched), self._key(opp_active),
               bool(switch_enabler))
        return self._memoized(key, lambda: self._combat.incoming(
            my_body, opp_bodies, t, forward_ids=fwd,
            charged=policy, evo_min_energy=evo_min_energy, context=context,
            my_benched=my_benched, opp_active=opp_active, switch_enabler=switch_enabler))

    def reachable_incoming(self, my_body: dict | None, **kwargs) -> int:
        """``incoming(t=1)`` — their next single development step. Delegates with every kwarg intact,
        so the one-step read stays identical to the curve by construction."""
        return self.incoming(my_body, 1, **kwargs)

    def doomed(self, my_body: dict | None, **kwargs) -> bool:
        """Can they Knock Out ``my_body`` next turn? — the composed survival boolean (POC-T1,
        Issue #260), and the home the folded `CombatMath.active_doomed` moved to.

        The fold made doom *one call into the curve at one policy*, which left the ``>= hp``
        comparison as the only thing still worth naming — and it was being written out at both
        consumers (the live decider and its diagnostic). Two spellings of one composition is the
        drift the fold exists to remove, one level up.

        Defaults to :data:`~common.strategy.combat.UNCHARGED`, the doom policy: the current form
        contributes unconditionally (a body on the board can hold Energy we cannot see) and forward
        forms keep the ``attached + 1`` gate, fail-open on an unresolvable cost. A caller confirming
        or clearing that cry under a different budget passes ``charged=`` like any other clock
        consumer; every other kwarg goes straight through to :meth:`incoming`."""
        hp = (my_body or {}).get("hp", 0)
        if not hp:
            return False                              # no live body: no claim, never a doom cry
        kwargs.setdefault("charged", UNCHARGED)
        return int(self.incoming(my_body, 1, **kwargs)) >= hp

    def turns_to_afford(self, body, *, attaches_per_turn: int = 1, fuelled: bool = True) -> int | None:
        """The earliest future turn ``body``'s line is ARMED — its biggest attack's cost payable.
        None when unknown (fail-closed: the caller emits no deny slot). Takes a :class:`BodyView` or a
        raw engine dict (see :meth:`view_of`).

        ``fuelled`` (default True, **Issue #204**) credits the line's own DISCARD RECURSION on top of
        the one manual attach per turn the clock otherwise assumes, at the ``self_arming`` scope — the
        reading that asks whether the reload reaches THIS body's own cost, quantified by Effect
        Clause. On the two shipped lines that resolves to: **Archaludon ex** yes (Assemble Alloy is an
        Ability firing on the very evolve hop this clock counts, and its {M} may land on the evolved
        body), **Mega Lucario ex** no (Aura Jab is an attack that reloads the BENCH, never the
        attacker). See ``CombatMath.discard_recur_fuel`` for the texts and for the bench-reload gap
        this deliberately leaves unpriced. Without it an Archaludon ex reads two turns from Metal
        Defender {M}{M}{M} when it is one — the bare clock is not conservative there, it is wrong.

        The fuel enters the way the shipped `_recur_fueled_oa` relax already enters it — by augmenting
        the body's ``energies`` and re-reading the clock — rather than as a new oracle parameter, so
        the reload keeps ONE quantifier and the clock keeps ONE energy model.

        Fail direction: more fuel credited ⇒ the opponent reads CLOSER ⇒ the threat read is more
        pessimistic, which is the safe direction for an opponent clock (ADR-0064's bounded pessimism).
        ``fuelled=False`` is the un-fuelled reading, kept for the diagnostic that sizes the delta.
        """
        view = self.view_of(body)
        if view is None:
            return None
        raw = view.body
        fuel = self._arming_recur_fuel(view) if fuelled else 0
        if fuel:
            # The reload is TYPED — `discard_recur_fuel` returns copies of the recur form's own
            # `energyType` — so the augmented body must carry typed ids, not bare counts, or the
            # oracle's typed leg would read them as colourless. The ids come from the discard itself:
            # these are real cards moving zone, not synthesised Energy.
            raw = dict(raw, energies=list(raw.get("energies") or ()) + self._recur_energy_ids(view, fuel))
        return self._memoized(("turns_to_afford", self._key(raw), attaches_per_turn),
                              lambda: self._combat.turns_to_afford(
                                  raw, forward_ids=self._forward_ids,
                                  attaches_per_turn=attaches_per_turn))

    def _arming_recur_fuel(self, view: "BodyView") -> int:
        """The discard reload that reaches ``view``'s OWN attack cost — the clock's reading of the
        recursion (Issue #204). Distinct from :meth:`discard_recur_fuel`, which is the fail-OPEN
        "could they refuel at all" caution the doom relax takes; see
        ``CombatMath.discard_recur_fuel`` for why the two questions have different answers on the two
        shipped lines."""
        return self._memoized(("arming_recur_fuel", self._key(view.body)),
                              lambda: self._combat.discard_recur_fuel(
                                  view.body, self.discard_energy_counts,
                                  forward_ids=self._forward_ids, scope="self_arming"))

    def _recur_energy_ids(self, view: "BodyView", count: int) -> list:
        """``count`` Basic-Energy card ids of the recur line's own type, taken from THEIR DISCARD.

        Real ids rather than a synthetic marker, because the clock's typed leg matches an attack's
        cost SHAPE against attached Energy by card identity — a placeholder would pay a colourless
        slot and no typed one, silently under-crediting exactly the {F}/{M} lines this exists for.
        The discard is public (`docs/rulebook.txt` L541), so picking the ids out of it is a sound
        read, not an estimate; :attr:`discard_ids` is the zone and the combat oracle resolves each id's type.
        Returns fewer ids than asked (possibly none) when the discard cannot supply them — the count
        and the ids then disagree only in the fail-CLOSED direction."""
        stat = view.stat
        recur_type = None
        for cid in self._recur_form_ids(view):
            form = self._combat._card_stat(cid)
            if form is not None and form.energyType is not None:
                recur_type = form.energyType
                break
        if recur_type is None:
            recur_type = getattr(stat, "energyType", None)
        if recur_type is None:
            return []
        out = []
        for cid in self.discard_ids:
            if len(out) >= count:
                break
            st = self._combat._card_stat(cid)
            if st is not None and st.is_typed_basic_energy and st.energyType == recur_type:
                out.append(cid)
        return out

    def _recur_form_ids(self, view: "BodyView") -> tuple:
        """``view``'s line — its own card id then its forward forms — in the order the recursion
        oracle scans them, so the type this side reloads is read off the SAME form that oracle picked
        as the refueler (one fact, one source)."""
        cid = view.card_id
        if cid is None:
            return ()
        fwd = self._forward_ids if self._forward_ids is not None else self._combat.forward_card_ids
        return (cid,) + tuple(fwd(cid) or ())

    def turns_to_ko_me(self, my_body: dict | None, *, bodies=None, charged=_THREADED,
                       my_benched: bool = False, my_bench=(),
                       key_ids=frozenset(), reading: str | None = None,
                       opp_active: dict | None = None, switch_enabler: bool = False,
                       context: dict | None = None) -> int:
        """The ACTIVE-area survival clock — accumulating, per ADR-0071 decision 4.

        **The kwargs are the point** (POC-T0, Issue #259). Every live caller used to bypass this
        method and reach `CombatMath` directly, and the reason was structural rather than habitual:
        the bypasses carry arguments the old one-argument signature could not express — the Bench
        Harvest trio (``my_bench`` / ``key_ids`` / ``reading``, with ``my_benched`` selecting the
        benched leg), ``opp_active``, and ``switch_enabler``. A model route that silently answers a
        DIFFERENT question than the bypass is worse than no route at all, so the fix is to widen the
        signature — never to re-point callers at a narrower one.

        Defaults reproduce the previous behaviour exactly, so this widening moves no decision: the
        solo body at the oracle's own default reading, which is what the single-argument form asked
        for. ``reading=None`` defers to `CombatMath`'s default rather than restating it here, so the
        harvest vocabulary keeps ONE home.

        Every argument is in the memo key. A memo that silently ignores an argument is a trap the
        sibling :meth:`incoming` already had to be fixed for (Issue #213) — two callers passing
        different harvest readings must not share one answer.

        T1 (Issue #260) migrated the bypass census onto this route, adding the two arguments the
        census still could not express — ``bodies`` (the counterfactual opponent board; see
        :meth:`_bodies`) and ``charged`` (the per-consumer energy policy; see
        :meth:`_charged_policy`). Any bypass that deliberately SURVIVES must document why at its call
        site, because "no undocumented CombatMath bypasses on model-covered questions" is T1's
        acceptance criterion, and an undocumented bypass is indistinguishable from an unmigrated one.

        Keyed by VALUE for the reason spelled out on :meth:`incoming` — the removal and strip Δs
        construct temporary body dicts, and an address-keyed memo can serve one temporary's answer for
        the next one allocated at the same address."""
        opp_bodies = self._bodies(bodies)
        policy = self._charged_policy(charged)
        key = ("turns_to_ko_me", self._key(my_body), self._key(opp_bodies), self._key(policy),
               bool(my_benched), self._key(tuple(my_bench or ())), frozenset(key_ids or ()),
               reading, self._key(opp_active), bool(switch_enabler), self._key(context))
        extra = {} if reading is None else {"reading": reading}
        return self._memoized(key, lambda: self._combat.turns_to_ko_me(
            my_body, opp_bodies, charged=policy, my_benched=my_benched,
            my_bench=my_bench, key_ids=key_ids, opp_active=opp_active,
            switch_enabler=switch_enabler, context=context, **extra))

    def bench_harvest_clock(self, my_bench, *, bodies=None, charged=_THREADED,
                            key_ids=frozenset(), reading: str | None = None,
                            opp_active: dict | None = None) -> dict:
        """``{bench index: first turn it falls in the harvest}`` over MY whole Bench — the
        shared-budget clock, solved once for the Bench rather than once per body.

        The sibling :meth:`turns_to_ko_me` answers the SAME question for one member and reads this
        underneath, so the two cannot drift. Memoised on the bench snapshot, which is what makes a
        per-option consumer (the deploy seam's exposure leg re-derives against a hypothetical Bench)
        pay for the real Bench exactly once per decision."""
        opp_bodies = self._bodies(bodies)
        policy = self._charged_policy(charged)
        key = ("bench_harvest_clock", self._key(tuple(my_bench or ())), self._key(opp_bodies),
               self._key(policy), frozenset(key_ids or ()), reading, self._key(opp_active))
        extra = {} if reading is None else {"reading": reading}
        return self._memoized(key, lambda: self._combat.bench_harvest_clock(
            my_bench, opp_bodies, charged=policy, key_ids=key_ids,
            opp_active=opp_active, **extra))

    def discard_recur_fuel(self, body) -> int:
        """Basic Energy their discard can reload onto ``body`` (the Aura-Jab class) — the recursion
        half of the discard read, which makes a KO'd threat's line persistent. Takes a
        :class:`BodyView` or a raw engine dict (see :meth:`view_of`)."""
        view = self.view_of(body)
        if view is None:
            return 0
        return self._memoized(("discard_recur_fuel", self._key(view.body)),
                              lambda: self._combat.discard_recur_fuel(
                                  view.body, self.discard_energy_counts,
                                  forward_ids=self._forward_ids))

    # -- evolution topology (the forward closure over the POOL) ---------------------------------
    def forward_payoff(self, card_id) -> "ForwardPayoff":
        """:class:`ForwardPayoff` for one of THEIR bodies — what its line still OWES it, so that
        removing the body can be priced for what it DENIES (Issue #285, POC-T3.5).

        The mirror of :meth:`MySide.forward_payoff`, and **the mirror is not a copy** — one of the
        three legs cannot be computed for a side whose deck is hidden, and it degrades in the
        OPPOSITE direction from mine, deliberately:

        * ``owed_damage`` / ``hops`` — **computed**, by `CombatMath.forward_payoff_terms` over the
          threaded ``forward_ids`` availability gate (the same callable :meth:`turns_to_afford`
          passes, defaulting to the pool-level index). Card knowledge only: `evolvesFrom` chains and
          printed damage, both of which the stat cache already holds for every card in the set.
        * ``reachable`` — **NOT computable, and therefore always True.** My side reads `hand_ids`
          plus `unseen_counts` to ask *"is a copy of that form still gettable"*; their hand is a
          COUNT (:attr:`hand_size`) and their deck is untracked, so the question has no sound answer
          here. It **fails OPEN**: we cannot prove their line is dead, and claiming so would cancel a
          denial credit against a threat that is perfectly real. That is the opposite fail direction
          from `MySide.forward_payoff`, whose `line_topology` leg CANCELS the credit for a line it
          can prove dead — and the asymmetry is the point, because over-crediting a live opponent
          line is the safe error where under-crediting one is not.

        Consequence worth stating plainly rather than leaving to be discovered: a Staryu on their
        board carries the Mega Starmie ex credit whether or not they run Mega Starmie ex, because the
        pool index is deck-agnostic. `MySide.forward_index` narrows to MY decklist precisely because
        it can; nothing narrows this one. `TheirSide.read` (the archetype Read) is the eventual
        supplier of that narrowing and is not consumed here — it is a matched-Brief probability, not
        a decklist, and threading it would give this a second opinion about the Read.
        """
        return self._memoized(("their_forward_payoff", card_id),
                              lambda: ForwardPayoff(
                                  *self._combat.forward_payoff_terms(
                                      card_id, forward_ids=self._forward_ids),
                                  True))


# ── the model ─────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PrizeRace:
    """The cross-side prize composite (ADR-0068 decision 4).

    Lives at the top level rather than on either side because it inherently reads BOTH — which is
    exactly why the win-with-this-KO arithmetic was previously re-expressed at several sites. Per-body
    prize YIELD stays on the combat oracle (card knowledge, constant all game); only the race is
    board state.
    """
    my_prizes_remaining: int = 0
    opp_prizes_remaining: int = 0

    # `prize_map`, `prize_diff` and `ko_wins_now` were DELETED by POC-T1 (Issue #260): three
    # derivations, zero consumers between them. The map re-stated `theirs.bodies[*].prize_value`,
    # which every reader already reaches through the BodyView it is holding anyway; the two
    # arithmetic helpers restated a subtraction and a comparison over the two counts above, which is
    # the kind of surface that costs nothing to offer and something to keep honest. The KO-wins
    # question in particular is NOT one line — the live win rung composes it with the simultaneous-
    # draw guard (a recoil KO makes it a draw, `docs/rulebook.txt`) — so a bare helper answering the
    # easy half of it is a trap for the next reader, not a convenience.


class StateModel(_Lazily):
    """The snapshot. Build it with :meth:`build`; read fields off :attr:`mine` / :attr:`theirs` and
    the cross-side derivations here."""

    _probe_prefix = "model"

    #: The observation :meth:`build` was handed, and the knowledge seams it was handed WITH — the
    #: only thing a successor snapshot needs that the snapshot itself does not already carry. Set by
    #: :meth:`build`; ``(None, {})`` on a model constructed directly, which is why :meth:`rebuilt`
    #: raises rather than silently rebuilding a model with no Stat Provider.
    _origin: tuple = (None, {})

    def __init__(self, *, mine: MySide, theirs: TheirSide, state: dict, my_index: int = 0,
                 carried: CarriedState = CarriedState(), probe=None):
        super().__init__(probe=probe)
        self.mine = mine
        self.theirs = theirs
        self.state = state or {}
        #: Which seat is mine. Held because a few shared facts are OWNED by a seat — the Stadium is
        #: the live case — and "whose is it?" cannot be answered from either side's PlayerState.
        self.my_index = int(my_index or 0)
        #: A FROZEN snapshot of the Carried State channel. The model reads it; it never writes it.
        self.carried = carried

    # -- construction ---------------------------------------------------------------------------
    @classmethod
    def build(cls, obs: dict, *, combat, my_index=None, deck=None, deck_empty=frozenset(),
              needs=None, role_worth=None, read=None, brief=None, matchup_plan=None,
              posture_confidence=0.0,
              favorability=0.5, matchup_coverage=0.0, opponent=None, forward_ids=None,
              charged=None, carried: CarriedState = CarriedState(), probe=None,
              their_side: TheirSide | None = None, turn_boosts=None) -> "StateModel":
        """The snapshot for one decision point — cheap, because it computes nothing yet.

        ``their_side`` accepts an already-built :class:`TheirSide` for REUSE, and the caller is
        responsible for having checked :attr:`opponent_fingerprint` first. That is the whole sharing
        mechanism: they cannot act during my turn, so their expensive clock derivations survive
        across the selects of a turn and across the planner's forked leaves; #150's sampled worlds
        reuse MY side symmetrically. Sharing is never assumed — a fingerprint mismatch rebuilds.

        ``turn_boosts`` is the match-scoped ``TurnBoostTracker`` (POC-T3.5, Issue #279), resolved to
        a per-side tuple HERE because this is the only place that knows which seat is mine. It is a
        log fact rather than a board fact — a played "during this turn" boost leaves no trace in any
        zone once the card reaches the discard — so no snapshot could recover it; None models a
        board with no live boosts, which is what a hand-built obs and a stat-blind build both want.

        A ``deck_known`` argument used to ride beside ``deck`` / ``own_prizes`` / ``deck_empty``,
        carrying the deck tracker's exact ``{card id: copies left in my deck}`` because the model
        could not reproduce it. Issue #297 fixed the read it distrusted, so ``own_prizes`` is the
        only anchor the model needs — see :meth:`MySide._deck_facts`.
        """
        state = (obs or {}).get("current") or {}
        players = state.get("players") or []
        mi = state.get("yourIndex", 0) if my_index is None else my_index
        me = players[mi] if 0 <= mi < len(players) and players[mi] else {}
        opp = players[1 - mi] if 0 <= 1 - mi < len(players) and players[1 - mi] else {}
        my_prizes, opp_prizes = len(me.get("prize") or []), len(opp.get("prize") or [])
        boosts_for = getattr(turn_boosts, "boosts_for", None)
        mine = MySide(me, combat=combat, deck=deck, deck_empty=deck_empty,
                      own_prizes=(obs or {}).get("own_prizes"), needs=needs, role_worth=role_worth,
                      energy_attached=bool(state.get("energyAttached")),
                      supporter_played=bool(state.get("supporterPlayed")),
                      more_prizes_than_opp=(my_prizes > opp_prizes),
                      turn=state.get("turn", 0), probe=probe,
                      turn_boosts=() if boosts_for is None else tuple(boosts_for(mi)))
        theirs = their_side if their_side is not None else TheirSide(
            opp, combat=combat, read=read, brief=brief, matchup_plan=matchup_plan,
            posture_confidence=posture_confidence, favorability=favorability,
            matchup_coverage=matchup_coverage, opponent=opponent, forward_ids=forward_ids,
            charged=charged, probe=probe,
            turn_boosts=() if boosts_for is None else tuple(boosts_for(1 - mi)))
        model = cls(mine=mine, theirs=theirs, state=state, my_index=mi, carried=carried, probe=probe)
        model._origin = (obs, {
            "combat": combat, "my_index": mi, "deck": deck, "deck_empty": deck_empty,
            "needs": needs, "role_worth": role_worth, "read": read, "brief": brief,
            "matchup_plan": matchup_plan, "posture_confidence": posture_confidence,
            "favorability": favorability, "matchup_coverage": matchup_coverage,
            "opponent": opponent, "forward_ids": forward_ids, "charged": charged,
            "carried": carried, "probe": probe, "turn_boosts": turn_boosts,
        })
        return model

    def rebuilt(self, obs: dict, *, reuse_their_side: bool = False) -> "StateModel":
        """**The ONE sanctioned route to a hypothetical board** — a FRESH model over ``obs``, built
        with exactly the knowledge seams this one was (POC-T4/1, Issue #382).

        Not an ``apply(action)`` path and deliberately not one: it takes a whole observation, so the
        rules arithmetic lives in the apply seam (`common.board_delta`) where the parity lane can
        diff it against a recorded native trace, and this method contributes no rules knowledge of
        its own. See this module's header for why the older blanket refusal of a delta path does not
        cover it.

        **Fresh, never patched.** ``state_value`` memoizes its per-family dict onto the model under
        ``("state_value",)`` and nothing invalidates that key, so a patched model would return a
        stale scalar in silence. A new model owns a new memo; staleness is impossible by
        construction rather than by discipline. :meth:`build` is *"cheap, because it computes nothing
        yet"*, so the fresh model costs three dict allocations plus whatever the caller then reads.

        ``reuse_their_side`` passes this model's already-built (and possibly already-derived)
        :class:`TheirSide` through, which is the sharing mechanism :meth:`shares_opponent_with`
        exists to guard. **The caller must have established that the transition never touched their
        `PlayerState` nor the shared Stadium** — `board_delta.Delta.shares_opponent` is what answers
        that, from the synthesis itself rather than from a hash of the result. Default False: a
        reused side that is stale fails OPEN, and this codebase never takes that direction by
        default.

        Raises `ValueError` on a model that was constructed directly rather than through
        :meth:`build` — it carries no Stat Provider to rebuild with, and a model built with
        ``combat=None`` would answer every card question "unknown" while looking like a board."""
        kwargs = self._origin[1]
        if not kwargs:
            raise ValueError(
                "rebuilt() needs the knowledge seams `build()` was handed; this model was "
                "constructed directly, so there is no Stat Provider to rebuild with")
        if reuse_their_side:
            kwargs = dict(kwargs, their_side=self.theirs)
        return type(self).build(obs, **kwargs)

    @property
    def source_obs(self) -> dict:
        """The observation :meth:`build` was handed, or ``{}``.

        The snapshot holds ``current`` (as :attr:`state`) and each side's `PlayerState`, but the
        apply seam needs the whole envelope — the live ``select`` whose menu an option came from, and
        the ``own_prizes`` anchor `MySide._deck_facts` reads. Exposed as a read rather than re-derived
        because there is nothing to derive it from.

        **Costs nothing to retain**: `state` and both `PlayerState`s are already sub-objects of this
        dict, so holding it adds a reference rather than a copy. Measured cost of the whole
        :attr:`_origin` capture (the 18-key kwargs dict plus this tuple), 60 corpus frames x 200
        passes on this box: **0.40 us against a 3.80 us build** — 10.5% of construction, and 0.016%
        of the ~2.5 ms `state_value` evaluation the build exists to feed."""
        return self._origin[0] or {}

    # -- the knowledge seams, as public reads -------------------------------------------------
    #
    # Three accessors rather than a caller reaching for `model.mine._combat` / `mine._deck`. The
    # sides hold them privately because the sides are what USE them; the apply seam is the first
    # module outside this one that needs them, and a private reach across a module boundary is how
    # a refactor inside `MySide` breaks a caller nothing warned about.
    @property
    def combat(self):
        """The `CombatMath` oracle this snapshot was built with (ADR-0052 / ADR-0056's Stat
        Provider seam behind it). The apply seam needs it to answer *"what card is this?"* about a
        card that is not on the board yet — the one in hand being played."""
        return self.mine._combat

    @property
    def deck(self) -> tuple:
        """My DECKLIST as declared to :meth:`build` — the 60 cards, not what is left in the deck.

        ``()`` when none was threaded, which is the honest answer and not an empty deck: the
        Count Triple's emptiness question is :attr:`MySide.deck_count`'s."""
        return self.mine._deck

    def card_stat(self, card_id):
        """This card's `CardStat`, or None — the model's own door onto the Stat Provider.

        Exists so the seam's telemetry can name a card (`"1182 Boss's Orders: …"`) without reaching
        two levels into another object's privates. Not a `lazy` field: it is parameterised and
        stateless, and the provider memoizes its own table."""
        return self.mine._combat._card_stat(card_id)

    # -- turn / quota facts (observation reads, not Carried State) ------------------------------
    #
    # These are the per-turn ALLOWANCES, and they are the §3c completeness contract's homes for
    # them (`common.snapshot_coverage`). A differencing system has to be able to see that a play
    # SPENT one, or it prices the spend at 0 — so each is a public read even where the same fact is
    # also mirrored onto `MySide` for the affordability cluster's internal use.
    @property
    def energy_attached(self) -> bool:
        """The one manual Energy attachment for this turn is spent."""
        return bool(self.state.get("energyAttached"))

    @property
    def supporter_played(self) -> bool:
        """The one Supporter for this turn is spent."""
        return bool(self.state.get("supporterPlayed"))

    @property
    def retreated(self) -> bool:
        """The one Retreat for this turn is spent (POC-T1, Issue #260).

        Homes the ``allowance_retreat_used`` zone. Retreat is an ordinary turn action limited to once
        per turn (`docs/rules.md` §3 *Action economy*) and the engine has carried
        ``current.retreated`` all along; the
        snapshot simply never surfaced it, so a retreat's own LEGALITY could not be differenced —
        and an illegal option priced like a legal one is a phantom line, not a small error."""
        return bool(self.state.get("retreated"))

    @property
    def stadium_played(self) -> bool:
        """A Stadium has already been played this turn — the third allowance, same shape."""
        return bool(self.state.get("stadiumPlayed"))

    @property
    def stadium(self) -> tuple:
        """Stadium card ids in play (the engine's list is 0- or 1-long). A tuple rather than a
        scalar because that is the shape the engine gives and :attr:`opponent_fingerprint` hashes."""
        return tuple((c or {}).get("id") for c in (self.state.get("stadium") or ()))

    @property
    def stadium_id(self):
        """The Stadium in play, or None — the scalar read `Board.stadium_in_play` wants."""
        return self.stadium[0] if self.stadium else None

    @property
    def stadium_is_theirs(self) -> bool:
        """The Stadium in play is THEIRS. Fails to False when no Stadium is out or the card carries
        no ``playerIndex`` (an unowned Stadium is nobody's to be punished for)."""
        card = (self.state.get("stadium") or [None])[0]
        if not card:
            return False
        owner = card.get("playerIndex")
        return owner is not None and owner != self.my_index

    # -- the cross-side derivation --------------------------------------------------------------
    @lazy
    def prize_race(self) -> PrizeRace:
        """The one canonical prize-race read (see :class:`PrizeRace`)."""
        return PrizeRace(my_prizes_remaining=self.mine.prizes_remaining,
                         opp_prizes_remaining=self.theirs.prizes_remaining)

    def damage_context(self, *, attacker: str) -> dict:
        """The Damage Formula's scaler context, built from THIS model, memoized per direction
        (POC-T3.5, Issue #279).

        ``attacker`` is ``"mine"`` or ``"theirs"`` — the side whose attack is being priced. The
        Formula's variables are named relative to the attacker (``atk_*``/``def_*``), so the two
        directions are different dicts, not one dict read twice: `survival` asks *their attack on
        me* and `threat` asks *my attack on them*, and one dict cannot answer both. ``both_bench``
        and ``both_active_energy`` exist precisely because they are the direction-SYMMETRIC
        variables (ADR-0083 §4, Issue #213).

        **Why the model owns a builder at all**, when the Pilot already had one: ``state_value``
        takes a StateModel and reads nothing else (the sole-supplier ruling —
        `docs/plans/value-system-poc-plan.md` §4-T0, restated on `state_value`), so a context threaded
        down from the Pilot is a second data supplier and is forbidden there. Both suppliers assemble
        through the ONE
        :func:`~common.strategy.damage_context.damage_context`, from the ONE
        :attr:`_SideBase.damage_facts` gatherer, and `test_damage_context` pins them key-for-key on
        corpus frames — because two hand-rolled builders of one fact is exactly the defect
        ``CombatMath.card_level_damage`` was extracted to end.

        **Identity-stable for the model's lifetime**, which is the point of memoizing it here rather
        than letting each consumer build one. Every clock read that prices a scaler carries the
        context in its memo key (:meth:`TheirSide.incoming`, :meth:`TheirSide.turns_to_ko_me`, both
        through ``_Lazily._key``), and that key primitive caches its canonical projection PER OBJECT
        — so a stable dict is canonicalised once and then costs a dict lookup, while a
        freshly-allocated one re-walks the whole context on every read and grows the projection cache
        without bound. The keys are sound either way (the cache holds a reference and re-checks
        identity, so a freed address cannot be reused under a live entry); what identity buys is that
        the memo HITS.

        An unknown direction raises rather than defaulting: a survival read handed MY attacker's
        scalers under-reads their damage, and under-reading incoming damage is the one direction a
        survival estimate may never fail in.
        """
        if attacker == "mine":
            atk, dfn = self.mine, self.theirs
        elif attacker == "theirs":
            atk, dfn = self.theirs, self.mine
        else:
            raise ValueError(f"attacker must be 'mine' or 'theirs', got {attacker!r}")
        return self._memoized(("damage_context", attacker),
                              lambda: _assemble_damage_context(atk.damage_facts, dfn.damage_facts))

    # -- the terminal action's substrate (POC-T4/3, Issue #384) ---------------------------------
    def attack_profile(self, body: "BodyView | None", attack_id) -> AttackProfile:
        """:class:`AttackProfile` for ONE attack of one of MY bodies — the substrate `attack_ev`
        takes and the model did not have.

        Issue #384's body proposes this on :class:`MySide`. It lives on :class:`StateModel` instead
        and the reason is structural rather than stylistic: the damage leg needs THEIR Active, the
        rider legs need THEIR Bench, and the scaler context needs both sides at once. A side cannot
        see the other side, so a `MySide` version would have to be handed the opponent's bodies by
        its caller — which is a second data supplier reaching into `state_value`, exactly what the
        sole-supplier ruling forbids. :meth:`damage_context` sits here for the same reason.

        **ONE accessor, not a family.** Issue #384's constraint, and it is also the sound shape: the
        fields are only sound together (see :class:`AttackProfile`), and a per-field accessor set
        would let a caller pair one attack's rider with another's lock.

        **Everything routes through a shipped oracle.** ``affordable`` is
        :meth:`MySide.reachable_attach` (the full Attach Budget — `threat.blind_to` forbids a raw
        energy-count second opinion outright); the four damage reads are
        :meth:`~common.strategy.combat.CombatMath.predicted_damage`, three against their Active and
        one matchup-free; the two knapsack answers are `spread_ko_prizes` / `snipe_ko_prizes`; the
        rider/lock/economy FACTS come off ``AttackStat`` through ``self.combat.attack_stat``, which
        is the same door :meth:`_SideBase.attack_payoff` already uses. Nothing here is new math.

        ``attacker="mine"`` on the context is not boilerplate — the Damage Formula's variables are
        named relative to the attacker, so handing this the survival direction's dict would read
        THEIR hand as MY damage scaler.

        Fails closed at an all-zero profile: an unresolvable attack, an absent body and an empty
        opponent seat each make NO claim rather than a plausible one. The record is still returned
        so a caller has no ``None`` branch to forget.

        Memoized by VALUE — card, area, attached Energy, the attack, and the opponent's whole
        fingerprint — because every leg but the two card-knowledge ones moves with their board, and
        :attr:`opponent_fingerprint` is the model's own wholesale answer to *did their side change*.
        """
        if body is None:
            return _EMPTY_ATTACK_PROFILE._replace(attack_id=attack_id)
        key = ("attack_profile", body.card_id, body.is_active, body.energy_key, attack_id,
               self.opponent_fingerprint)
        return self._memoized(key, lambda: self._attack_profile(body, attack_id))

    def _attack_profile(self, body: "BodyView", attack_id) -> AttackProfile:
        stat = self.combat.attack_stat(attack_id)
        if stat is None:                       # no record, no claim — the standing direction
            return _EMPTY_ATTACK_PROFILE._replace(attack_id=attack_id)
        defender = self.theirs.active
        target = defender.body if defender is not None else None
        context = self.damage_context(attacker="mine")
        attacker_id = body.card_id

        def _dmg(bound: str, against) -> float:
            return float(self.combat.predicted_damage(attacker_id, attack_id, against,
                                                      bound=bound, context=context))

        snipe, spread = int(stat.benchSnipe or 0), int(stat.benchSpread or 0)
        # Their Bench as the rider oracles want it: (card id, remaining HP) pairs. The oracles apply
        # the bench rules themselves (HP within the payload, bench-immune bodies take none), so this
        # hands them the zone and forms no second opinion about who is reachable.
        bench_pairs = [(v.card_id, v.hp_remaining) for v in self.theirs.bench if v.hp_remaining]
        return AttackProfile(
            attack_id=attack_id,
            affordable=bool(self.mine.reachable_attach(body, attack_id)),
            damage=_dmg("exact", target),
            damage_floor=_dmg("min", target),
            damage_ceiling=_dmg("max", target),
            conditional=(stat.damageMin is not None or stat.damageMax is not None),
            printed=_dmg("exact", None),
            bench_snipe=snipe,
            bench_spread=spread,
            snipe_ko_prizes=int(self.combat.snipe_ko_prizes(bench_pairs, snipe)) if snipe else 0,
            spread_ko_prizes=int(self.combat.spread_ko_prizes(bench_pairs, spread)) if spread else 0,
            rider_targets=self._rider_targets(bench_pairs) if (snipe or spread) else (),
            recover_n=int(stat.recoverN or 0),
            recover_units=self._recover_units(stat),
            self_lock=bool(stat.nextTurnSelfLock),
            same_attack_lock=bool(stat.nextTurnSameAttackLock),
        )

    def _rider_targets(self, bench_pairs) -> tuple:
        """``((hp_remaining, prize_value), …)`` for the benched bodies of theirs a rider can reach.

        The bench-immunity rule is read through the SAME predicate the rider oracles use
        (`CombatMath.is_tera` — `docs/rules.md` §11 scopes a Tera body's immunity to the Bench), so
        this list and the knapsack answers beside it can never disagree about who is on the board.
        """
        return tuple((hp, int(self.combat.prize_value({"id": cid})))
                     for cid, hp in bench_pairs if not self.combat.is_tera(cid))

    def _recover_units(self, stat) -> float:
        """`Pilot._recover_units`' three closed-form bounds, re-derived from model facts.

        The shipped pricer takes a ``Board`` and a raw observation and has no model route at all, so
        the BOUNDS are the spec and the Pilot's plumbing is not (Issue #384). They are, unchanged:

        1. ``recoverN`` — the card's printed ceiling (Aura Jab: *"attach up to 3"*).
        2. the matching Basic-Energy FUEL in the rider's SOURCE zone. ``"discard"`` reads
           :attr:`_SideBase.discard_energy_counts` — a PUBLIC zone in both directions, so a sound
           count and never an estimate; ``"deck"`` reads :attr:`MySide.deck_energy_counts`'
           ``CountTriple.expected`` off the ONE Count Triple derivation (ADR-0077 decision 3 — a
           ranked count consumer reads ``expected``, and anchored the leg collapses to the exact
           integer). An untyped rider takes the cross-type union, which is EXACT rather than a
           second instrument because every type's leg divides the same ``(deck_count,
           prizes_hidden)``.
        3. the recipients' remaining NEED (ADR-0061). Energy nobody can pay an attack with is not
           development: three {F} onto a support Bench is worth nothing, and that is exactly the
           margin that tips Aura Jab over Mega Brave. Need is measured against each recipient's
           FORWARD form too, so a Riolu counts the {F}{F} its Mega Brave will cost rather than the
           {F} its Accelerating Stab costs today. The same gate makes a bench-scoped rider on an
           EMPTY Bench credit 0, which preserves the old empty-Bench guard as a special case.

        The forward closure comes off :attr:`MySide.forward_index` — MY decklist, so a form I do not
        run is not a form my line can reach — and never off a universal card index."""
        ceiling = int(getattr(stat, "recoverN", 0) or 0)
        if not ceiling:
            return 0.0
        etype = getattr(stat, "recoverEnergyType", None)
        if getattr(stat, "recoverSource", None) == "deck":
            counts = self.mine.deck_energy_counts
            fuel = (float(sum(c.expected for c in counts.values())) if etype is None
                    else float(counts[etype].expected) if etype in counts else 0.0)
        else:
            by_type = self.mine.discard_energy_counts or {}
            fuel = float(sum(by_type.values()) if etype is None else by_type.get(etype, 0))
        return max(0.0, min(float(ceiling), fuel,
                            float(self._recover_need(getattr(stat, "recoverTarget", None)))))

    def _recover_need(self, scope) -> int:
        """Total Energy the rider's recipients still LACK to pay an attack — their own or their
        forward evolution's, whichever is dearer, since that is what the line is being built
        toward. 0 when the scope holds no recipient at all.

        Scope is the rider's own ``recoverTarget`` (*"…to your Benched Pokémon"* -> ``"bench"``), so
        a bench-scoped rider on an empty Bench reads 0 and a self-scoped one never credits the
        Bench. An unresolvable attack contributes 0 rather than a guessed cost."""
        pool = []
        if scope in (None, "any", "bench"):
            pool += list(self.mine.bench)
        if scope in (None, "any", "self") and self.mine.active is not None:
            pool.append(self.mine.active)
        total = 0
        for view in pool:
            forms = {view.card_id} | set(self.mine.forward_form_ids(view.card_id))
            costs = [self.combat.attack_cost(aid, default=0)
                     for form in forms
                     for aid in (getattr(self.card_stat(form), "attacks", None) or ())]
            if costs:
                total += max(0, max(costs) - view.energy_count)
        return total

    # -- the sharing guard ----------------------------------------------------------------------
    @lazy
    def opponent_fingerprint(self) -> int:
        """A WHOLESALE hash of everything that could change their side's derivations.

        Deliberately not a hand-picked field list. Their ``PlayerState`` is a closed record, so
        hashing all of it catches a hand-and-deck refresh (Judge moves ``handCount``/``deckCount``
        and nothing else), a gust (which body is Active), an energy strip, a damage-counter transfer
        and a condition inflicted — plus the next disruption card nobody thought of. An enumerated
        list fails OPEN silently; this fails toward a redundant rebuild, which costs time and stays
        correct.

        THREE things outside their ``PlayerState`` still move their derivations, so all three are
        folded in: the shared ``stadium`` (it can change what their bodies effectively are), the
        transient-grant generation (a lock or shield I imposed on their Active is honoured by the
        clock reads but lives in the match-scoped tracker, ADR-0033), and their live damage-BOOST
        plays (:attr:`_SideBase._turn_boosts`).

        The third joined in POC-T3.5 (Issue #279) **with** the field that made it possible to miss.
        A "during this turn" boost is a log fact — the card is in the discard by the time anyone
        reads the board — so it is threaded onto the side rather than derived from it, and a
        threaded field is precisely what the wholesale hash of ``player`` cannot see. A reused
        ``their_side=`` would otherwise have carried a stale boost tuple into their damage context,
        which is the fail-OPEN direction this hash exists to refuse. Inert today (nothing calls
        :meth:`shares_opponent_with` at runtime), which is exactly why it had to be closed now: the
        hole would have surfaced in Issue #150's sampled worlds, one layer away from its cause.
        """
        return hash((_canonical(self.theirs.player), self.stadium, self._transient_generation,
                     self.theirs._turn_boosts))

    @lazy
    def _transient_generation(self):
        """The live-grant generation off the combat oracle's tracker; None when untracked."""
        tracker = getattr(self.mine._combat, "_transients", None)
        return getattr(tracker, "generation", None) if tracker is not None else None

    def shares_opponent_with(self, other: "StateModel") -> bool:
        """True when ``other``'s :attr:`theirs` may be reused for this board — the check a caller
        MUST make before passing ``their_side`` to :meth:`build`.

        **KEPT deliberately with no runtime caller** (POC-T1, Issue #260, which purged the rest of
        the model's unconsumed surface). This, :attr:`opponent_fingerprint` and the ``their_side=``
        reuse path are the SHARING MACHINERY, pre-built for **post-POC Issue #150** (depth-2 search
        over sampled worlds): they cannot act during my turn, so their expensive clock derivations
        survive across the selects of a turn and across a forked leaf, and #150's sampled worlds
        reuse MY half symmetrically. It is not dead surface by the purge's own test — the test is
        "does anything need this?", and a named, dated owner is the answer that keeps a seat.

        The `probe=` instrumentation is kept on the same footing, with a difference worth stating:
        it HAS a live consumer, `tests/strategy/test_leaf_profile.py`, which pins the field set an
        evaluation touches. That is a regression guard, not a runtime path — the cost of a lazy model
        is invisible in the source, so the pin is the only thing that makes it visible.
        """
        return (other is not None
                and self.opponent_fingerprint == other.opponent_fingerprint)


def _canonical(value):
    """A hashable, order-faithful projection of an engine zone/record.

    Order is preserved rather than normalised away, because order carries meaning here: which body
    sits in ``active`` versus ``bench`` is precisely what a gust changes, and a set-shaped
    fingerprint would call that board unchanged.
    """
    if isinstance(value, dict):
        return tuple((k, _canonical(v)) for k, v in sorted(value.items(), key=lambda kv: str(kv[0])))
    if isinstance(value, (list, tuple)):
        return tuple(_canonical(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((str(v) for v in value)))
    return value
