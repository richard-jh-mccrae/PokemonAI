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
accepts). A general ``apply(action)`` delta path is deliberately ABSENT: the engine already hands us
an authoritative post-action board at every simulated leaf, so such a path would re-predict in
Python what the simulator just computed (a second rules engine, whose failure mode is silent
divergence in every downstream equation), and the my-side affordability cluster invalidates wholesale
under one manual attach anyway.

Composes the knowledge seams (the Stat Provider ADR-0056, ``CardFunctions``, ``CombatMath``
ADR-0052, the Read) and takes per-decision facts as explicit arguments. It never imports or reads a
Pilot or a Board — the dependency runs one way, exactly as ``CombatMath`` does.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from common.deck_odds import p_contains          # the Probability Leg's one implementation

#: Sentinel for "use the policy threaded at :meth:`StateModel.build`". A clock consumer that wants a
#: DIFFERENT conservatism than the Read's — the catastrophe-grade doom budget, the deny Δ's zero-attach
#: budget, the ceiling — passes ``charged=`` explicitly, and ``None`` there means the worst-case
#: ceiling rather than "unset". The per-consumer conservatism is a PARAMETER by ADR-0064 Decision 1, so
#: the two readings must be distinguishable; a plain ``None`` default silently collapses them.
_THREADED = object()

def CURRENT_FORMS_ONLY(_card_id):
    """A forward-availability gate that admits NOTHING — "read the bodies as they stand".

    A named module-level callable rather than an inline ``lambda`` at each call site, so the clock
    memo can reuse an answer across a decision: the memo keys on the callable itself, and a fresh
    closure per call would key differently every time. The one live consumer is
    `Board.incoming_active_damage`, which asks what the body in FRONT of me hits for today (a +HP
    Tool's survival breakpoint) rather than what its line becomes.
    """
    return ()


#: Fallback Bench cap for an observation that omits the engine's own ``benchMax`` — the shipped
#: format's 5 (`docs/rules.md` §7). Only a hand-built board ever reaches it; a real observation
#: carries the field, and reading it is what keeps the model honest if the format ever changes.
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
    def attached_types(self) -> dict:
        """``{EnergyType: count}`` attached — the typed supply a cost shape is matched against."""
        return self._combat.attached_type_counts(self.body)

    @lazy
    def energy_count(self) -> int:
        """Energy UNITS attached — the raw count the rules speak in (a retreat cost is "discard this
        many Energy", `docs/rules.md` §4).

        Deliberately NOT ``sum(attached_types.values())``, which is what it used to be: that counts
        only the TYPED Basic Energy the colour matcher can resolve, so a Special Energy or an
        unresolvable card provides a unit with no type and the two numbers legitimately differ. The
        typed histogram is :attr:`attached_types` and it is the right read for a COST SHAPE; this is
        the right read for a count, and the distinction is why they are two fields rather than one
        (POC-T1, Issue #260 — the raw-read migration surfaced call sites that meant the count)."""
        return len(self.energy_key)

    @lazy
    def energy_key(self) -> tuple:
        """The attached Energy as a HASHABLE tuple of card ids — the value-memo key component for
        every read that depends on what this body is carrying.

        The engine gives them as bare ids, so the coercion below is a cheap guard rather than a
        real branch: a memo key must never be the thing that raises, and ``len()``-only readers
        would not have noticed a wrong shape. One accessor, so no memo re-invents it."""
        return tuple(e.get("id") if isinstance(e, dict) else e
                     for e in (self.body.get("energies") or ()))

    # `attacks` and `attack_slots` were DELETED by POC-T1 (Issue #260): zero consumers, and both
    # were pass-throughs to card knowledge that has a home already — `stat.attacks` and
    # `CombatMath._attack_slots`. A body VIEW of a fact that does not depend on the body is a second
    # place to look for it, which is the cost the model exists to remove rather than to add.

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
    def serial(self):
        """The body's match-unique serial — the key ADR-0033 transient grants are stored under.
        None when the observation carries no serial (a hand-built body)."""
        return self.body.get("serial")

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

    def __init__(self, player: dict, *, combat, probe=None, prefix="side"):
        super().__init__(probe=probe)
        self._probe_prefix = prefix
        self.player = player or {}
        self._combat = combat

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
    def bench_raws(self) -> tuple:
        """The BENCHED bodies' raw engine dicts — the Bench Harvest's input (ADR-0071 decision 7).

        A shared rider budget is a fact about the whole bench, so a per-body survival read cannot
        express it; the snapshot owns the list because it is lazy and pure (ADR-0068), which is what
        stops the bench shifting under a memoized clock."""
        return tuple(b.body for b in self.bench)

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

    # -- prizes / zones -------------------------------------------------------------------------
    @lazy
    def prizes_remaining(self) -> int:
        """Prizes this side still needs to take."""
        return len(self.player.get("prize") or [])

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

        A discard pile is public in **both** directions (`docs/rules.md` — "DISCARD [pub — both may
        look]"), so this is sound knowledge about the opponent, not an estimate, and it belongs on
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


class MySide(_SideBase):
    """MY half — the side with open information: real hand cards, the **Attach Budget**, per-body
    **Reachable Attach** and readiness, Needs coverage, and my deck's typed availability."""

    _probe_prefix = "mine"

    def __init__(self, player: dict, *, combat, deck=None, deck_empty=frozenset(),
                 own_prizes=None, energy_attached=False, supporter_played=False,
                 more_prizes_than_opp=False, turn=0, probe=None):
        super().__init__(player, combat=combat, probe=probe, prefix="mine")
        self._deck = tuple(deck or ())
        self._deck_empty = frozenset(deck_empty or ())
        self._own_prizes = own_prizes
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

    # -- deck availability (the Count Triple, ADR-0068 decision 4) ------------------------------
    @lazy
    def visible_counts(self) -> Counter:
        """My card copies provably OUTSIDE the deck: hand, discard, every board body (with its
        attached Energy, Tools and stacked pre-evolutions) and any FACE-UP prize. Face-down prizes
        and the deck itself stay uncounted — precisely the unknowns that keep the sound oracle
        sound."""
        counts: Counter = Counter()
        for zone in ("hand", "discard"):
            for card in (self.player.get(zone) or []):
                if card and card.get("id") is not None:
                    counts[card["id"]] += 1
        for prize in (self.player.get("prize") or []):
            if prize and prize.get("id") is not None:      # revealed; face-down prizes are None
                counts[prize["id"]] += 1
        for body in self.body_raws:
            self._count_in_play(body, counts)
        return counts

    @staticmethod
    def _count_in_play(body: dict, counts: Counter) -> None:
        body = body or {}
        if body.get("id") is not None:
            counts[body["id"]] += 1
        for key in ("energies", "energy", "tools", "preEvolution", "preEvolutions"):
            for card in (body.get(key) or ()):
                cid = card.get("id") if isinstance(card, dict) else card
                if cid is not None:
                    counts[cid] += 1

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

    def turns_to_afford(self, body, *, attaches_per_turn: int = 1) -> int | None:
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
        clock fails in the unsafe direction (it would price a line as armed sooner than it is)."""
        view = self.view_of(body)
        if view is None:
            return None
        return self._memoized(("mine_turns_to_afford", self._key(view.body), attaches_per_turn),
                              lambda: self._combat.turns_to_afford(
                                  view.body, attaches_per_turn=attaches_per_turn, typed=True))

    # `famine` was DELETED by POC-T1 (Issue #260). It was `active_famine` MINUS the rule leg — the
    # affordability half alone — so a consumer taking it would have missed Asleep, Paralyzed and the
    # first player's turn-1 attack ban, which is the f70 blunder class one door over. Two names for
    # one premise, differing silently in what they check, is exactly what the composed read exists to
    # prevent; `active_famine` is the premise.


class TheirSide(_SideBase):
    """THEIR half — the side with hidden information: hand SIZE only, the clock family, the
    archetype Read, and the recursion fuel their discard makes live."""

    _probe_prefix = "theirs"

    def __init__(self, player: dict, *, combat, read=None, brief=None, matchup_plan=None,
                 posture_confidence=0.0, favorability=0.5, matchup_coverage=0.0,
                 opponent=None, forward_ids=None, charged=None, probe=None):
        super().__init__(player, combat=combat, probe=probe, prefix="theirs")
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
        forms only — pass ``lambda _cid: ()`` — which is a real question (`Board`'s
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
        # stable callable (:data:`CURRENT_FORMS_ONLY`).
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
        The discard is public (`docs/rules.md`), so picking the ids out of it is a sound read, not an
        estimate; :attr:`discard_ids` is the zone and the combat oracle resolves each id's type.
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
              read=None, brief=None, matchup_plan=None, posture_confidence=0.0,
              favorability=0.5, matchup_coverage=0.0, opponent=None, forward_ids=None,
              charged=None, carried: CarriedState = CarriedState(), probe=None,
              their_side: TheirSide | None = None) -> "StateModel":
        """The snapshot for one decision point — cheap, because it computes nothing yet.

        ``their_side`` accepts an already-built :class:`TheirSide` for REUSE, and the caller is
        responsible for having checked :attr:`opponent_fingerprint` first. That is the whole sharing
        mechanism: they cannot act during my turn, so their expensive clock derivations survive
        across the selects of a turn and across the planner's forked leaves; #150's sampled worlds
        reuse MY side symmetrically. Sharing is never assumed — a fingerprint mismatch rebuilds.
        """
        state = (obs or {}).get("current") or {}
        players = state.get("players") or []
        mi = state.get("yourIndex", 0) if my_index is None else my_index
        me = players[mi] if 0 <= mi < len(players) and players[mi] else {}
        opp = players[1 - mi] if 0 <= 1 - mi < len(players) and players[1 - mi] else {}
        my_prizes, opp_prizes = len(me.get("prize") or []), len(opp.get("prize") or [])
        mine = MySide(me, combat=combat, deck=deck, deck_empty=deck_empty,
                      own_prizes=(obs or {}).get("own_prizes"),
                      energy_attached=bool(state.get("energyAttached")),
                      supporter_played=bool(state.get("supporterPlayed")),
                      more_prizes_than_opp=(my_prizes > opp_prizes),
                      turn=state.get("turn", 0), probe=probe)
        theirs = their_side if their_side is not None else TheirSide(
            opp, combat=combat, read=read, brief=brief, matchup_plan=matchup_plan,
            posture_confidence=posture_confidence, favorability=favorability,
            matchup_coverage=matchup_coverage, opponent=opponent, forward_ids=forward_ids,
            charged=charged, probe=probe)
        return cls(mine=mine, theirs=theirs, state=state, my_index=mi, carried=carried, probe=probe)

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
        per turn (`docs/rules.md` §4) and the engine has carried ``current.retreated`` all along; the
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

        Two things outside their ``PlayerState`` still move their derivations, so both are folded in:
        the shared ``stadium`` (it can change what their bodies effectively are) and the
        transient-grant generation (a lock or shield I imposed on their Active is honoured by the
        clock reads but lives in the match-scoped tracker, ADR-0033).
        """
        return hash((_canonical(self.theirs.player), self.stadium, self._transient_generation))

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
