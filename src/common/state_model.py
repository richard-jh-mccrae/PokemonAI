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

    Two regimes, ONE interface: before the first deck-revealing search the legs diverge; once that
    search anchors the prizes (``prizes_hidden == 0``) all three collapse to the same integer. So no
    consumer ever branches on "are we anchored?" — the reason this shape beats a bare expectation.
    """
    floor: int = 0
    expected: float = 0.0
    ceiling: int = 0

    @property
    def anchored(self) -> bool:
        """True once the legs have collapsed — the count is exactly known."""
        return self.floor == self.ceiling

    @property
    def possible(self) -> bool:
        """Not provably absent — the fail-open presence gate (ADR-0067's deck-presence direction)."""
        return self.ceiling > 0


def count_triple(unseen: int, prizes_hidden: int, deck_count: int) -> CountTriple:
    """The three legs for ``unseen`` copies split over ``deck_count`` deck slots and
    ``prizes_hidden`` face-down prizes. Pure; total; never raises.

    Anchored (``prizes_hidden <= 0``) every unseen copy is in the deck, so the legs collapse. The
    floor is the pigeonhole surplus (copies that CANNOT all be prized), matching the sound step
    ``deck_odds.p_contains`` already takes at ``u > k``.
    """
    try:
        u, k, d = max(0, int(unseen)), max(0, int(prizes_hidden)), max(0, int(deck_count))
    except Exception:
        return CountTriple()                       # unreadable inputs claim nothing (fail-closed)
    if u == 0 or d == 0:
        return CountTriple()                       # no copies unseen, or no deck left to hold them
    if k == 0:
        n = min(u, d)                              # anchored: the split is resolved
        return CountTriple(floor=n, expected=float(n), ceiling=n)
    return CountTriple(floor=max(0, u - k),        # pigeonhole: this many cannot all be prized
                       expected=u * d / float(d + k),
                       ceiling=min(u, d))


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

    def with_(self, name, value) -> "CarriedState":
        """A NEW snapshot with ``name`` set — the channel is immutable, so an update is a rebind at
        the caller rather than a mutation anyone else can observe."""
        if name not in self.MEMBERS:
            raise ValueError(f"undeclared Carried State member: {name!r}")
        return CarriedState(tuple(sorted(
            [(k, v) for k, v in self.values if k != name] + [(name, value)],
            key=lambda kv: kv[0])))


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
        return sum(self.attached_types.values())

    @lazy
    def energy_key(self) -> tuple:
        """The attached Energy as a HASHABLE tuple of card ids — the value-memo key component for
        every read that depends on what this body is carrying.

        The engine gives them as bare ids, so the coercion below is a cheap guard rather than a
        real branch: a memo key must never be the thing that raises, and ``len()``-only readers
        would not have noticed a wrong shape. One accessor, so no memo re-invents it."""
        return tuple(e.get("id") if isinstance(e, dict) else e
                     for e in (self.body.get("energies") or ()))

    @lazy
    def attacks(self) -> tuple:
        stat = self.stat
        return tuple(stat.attacks or ()) if stat is not None else ()

    def attack_slots(self, attack_id) -> tuple:
        """The attack's per-slot typed cost shape (0 = colourless); empty when unresolvable."""
        return self._memoized(("attack_slots", attack_id),
                              lambda: self._combat._attack_slots(attack_id) or ())

    @lazy
    def prize_value(self) -> int:
        """Prizes the opponent takes for knocking this body out — card knowledge, so it stays on the
        combat oracle (ADR-0052) and the model only holds the answer."""
        return self._combat.prize_value(self.body)


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


class MySide(_SideBase):
    """MY half — the side with open information: real hand cards, the **Attach Budget**, per-body
    **Reachable Attach** and readiness, Needs coverage, and my deck's typed availability."""

    _probe_prefix = "mine"

    def __init__(self, player: dict, *, combat, deck=None, deck_empty=frozenset(),
                 own_prizes=None, needs=None, energy_attached=False, supporter_played=False,
                 more_prizes_than_opp=False, turn=0, probe=None):
        super().__init__(player, combat=combat, probe=probe, prefix="mine")
        self._deck = tuple(deck or ())
        self._deck_empty = frozenset(deck_empty or ())
        self._own_prizes = own_prizes
        self._needs = needs
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

    @lazy
    def needs(self):
        """The position's Needs slots (deadline-tagged, ADR-0065's glossary) as resolved by the
        caller, or None when not supplied. The model does not own the Needs engine; it holds the
        resolution so several equations read one assignment instead of each re-running the DP."""
        resolver = self._needs
        return resolver() if callable(resolver) else resolver

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
                               provable: bool = False):
        """The Budget toward a card id rather than a body in play — for a HYPOTHETICAL attacker the
        board does not carry yet (the composed KO line's evolved form, #142).

        This is the real primitive and :meth:`attach_budget` is the BodyView-shaped face of it: the
        Budget reads its target only through the ``CardStat`` and the area, which is exactly this
        pair. Callers that assembled the zone arguments by hand went around the memo and had to keep
        seven kwargs in step with it; there is one assembly now."""
        key = ("attach_budget", card_id, not benched, bool(manual_spent), bool(provable))
        return self._memoized(key, lambda: self._combat.attach_budget(
            {"id": card_id}, self.hand_ids,
            energy_attached=self.energy_attached or bool(manual_spent),
            supporter_played=self.supporter_played,
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
                    copies: int = 0, pool: int = 0, draws: int = 0) -> float:
        """P(``body`` is ready to use the attack this turn) — the EV variant, and the ONLY place an
        honest probability enters the affordability family (ADR-0067's split). Fails closed at 0.0."""
        if body is None:
            return 0.0
        return self._combat.readiness_p(body.body, attack_id, budget=self.attach_budget(body),
                                        enabler_budget=enabler_budget, copies=copies,
                                        pool=pool, draws=draws)

    def turns_to_afford(self, body: BodyView | None, *, attaches_per_turn: int = 1) -> int | None:
        """**The Two Clocks**, my half (ADR-0070 §6): the earliest future turn ``body``'s line is
        ARMED — the MAX of the energy-deficit leg and the FORWARD-HOP leg, never the sum.

        The mirror of :meth:`TheirSide.turns_to_afford`, which has carried this read since the deny
        clock (S1c) but only for the opponent's bodies. The evolve decider needs it for MY bodies:
        evolving removes one forward hop, so the Δ across the hop is what an evolve buys on the
        armed side — and where the energy leg dominates, that Δ is honestly zero. Uses the
        pool-level forward index (my own deck's forward forms are exactly the right availability
        gate for my line). None when unknown — fail-closed, the caller then makes no claim."""
        if body is None:
            return None
        return self._memoized(("mine_turns_to_afford", id(body.body), attaches_per_turn),
                              lambda: self._combat.turns_to_afford(
                                  body.body, attaches_per_turn=attaches_per_turn, typed=True))

    @lazy
    def famine(self) -> bool:
        """My Active can reach NO attack this turn, even under the full Attach Budget — the sound
        definition of famine (ADR-0067), never "0 Energy attached". False when there is no Active
        (no claim rather than a false alarm)."""
        return self.active is not None and not self.reachable_attach(self.active, None)


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
        cross-decision inference with no Phase-1 consumer, and belongs behind the facade."""
        return int(self.player.get("handCount") or 0)

    @lazy
    def deck_count(self) -> int:
        return int(self.player.get("deckCount") or 0)

    # -- the clock family (ADR-0064 / the Threat-Clock unification) -----------------------------
    def incoming(self, my_body: dict | None, t: int = 1, *, evo_min_energy: int = 0,
                 context: dict | None = None) -> int:
        """Worst W/R-adjusted damage their affordable attackers could deal ``my_body`` at future turn
        ``t`` — the Threat-Clock curve, memoized per ``(body, t)``. ``t=1`` is Reachable Incoming."""
        key = ("incoming", id(my_body) if my_body is not None else None, t, evo_min_energy)
        return self._memoized(key, lambda: self._combat.incoming(
            my_body, self.body_raws, t, forward_ids=self._forward_ids,
            charged=self._charged, evo_min_energy=evo_min_energy, context=context))

    def reachable_incoming(self, my_body: dict | None, *, evo_min_energy: int = 0,
                           context: dict | None = None) -> int:
        """``incoming(t=1)`` — their next single development step. Delegates, so the one-step read
        stays identical to the curve by construction."""
        return self.incoming(my_body, 1, evo_min_energy=evo_min_energy, context=context)

    def turns_to_afford(self, body: BodyView, *, attaches_per_turn: int = 1) -> int | None:
        """The earliest future turn ``body``'s line is ARMED — its biggest attack's cost payable.
        None when unknown (fail-closed: the caller emits no deny slot)."""
        return self._memoized(("turns_to_afford", id(body.body), attaches_per_turn),
                              lambda: self._combat.turns_to_afford(
                                  body.body, forward_ids=self._forward_ids,
                                  attaches_per_turn=attaches_per_turn))

    def turns_to_ko_me(self, my_body: dict | None) -> int:
        """The ACTIVE-area survival clock — accumulating, per ADR-0071 decision 4.

        UNCONSUMED today: both live callers reach `CombatMath` directly (`pilot.py`'s evolve read and
        `survival_shift`). Deliberately NOT bench-aware — it is one-sided, so it cannot see MY bench,
        and a Bench Harvest is a fact about the whole bench. A caller wanting the benched area must
        pass `my_bench` / `key_ids` / `reading` itself (`MySide.bench_raws` supplies the first);
        through here it would silently get the solo body at the conservative reading."""
        return self._memoized(("turns_to_ko_me", id(my_body) if my_body is not None else None),
                              lambda: self._combat.turns_to_ko_me(my_body, self.body_raws,
                                                                  charged=self._charged))

    def discard_recur_fuel(self, body: BodyView) -> int:
        """Basic Energy their discard can reload onto ``body`` (the Aura-Jab class) — the recursion
        half of the discard read, which makes a KO'd threat's line persistent."""
        return self._memoized(("discard_recur_fuel", id(body.body)),
                              lambda: self._combat.discard_recur_fuel(
                                  body.body, self.discard_energy_counts,
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
    prize_map: tuple = ()                          # ((their body card id, prizes it yields), …)

    @property
    def prize_diff(self) -> int:
        """Positive = I am ahead on the count."""
        return self.opp_prizes_remaining - self.my_prizes_remaining

    def ko_wins_now(self, prizes: int) -> bool:
        """Would taking ``prizes`` prizes end the game in my favour right now?"""
        return prizes >= self.my_prizes_remaining > 0


class StateModel(_Lazily):
    """The snapshot. Build it with :meth:`build`; read fields off :attr:`mine` / :attr:`theirs` and
    the cross-side derivations here."""

    _probe_prefix = "model"

    def __init__(self, *, mine: MySide, theirs: TheirSide, state: dict,
                 carried: CarriedState = CarriedState(), probe=None):
        super().__init__(probe=probe)
        self.mine = mine
        self.theirs = theirs
        self.state = state or {}
        #: A FROZEN snapshot of the Carried State channel. The model reads it; it never writes it.
        self.carried = carried

    # -- construction ---------------------------------------------------------------------------
    @classmethod
    def build(cls, obs: dict, *, combat, my_index=None, deck=None, deck_empty=frozenset(),
              needs=None, read=None, brief=None, matchup_plan=None, posture_confidence=0.0,
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
                      own_prizes=(obs or {}).get("own_prizes"), needs=needs,
                      energy_attached=bool(state.get("energyAttached")),
                      supporter_played=bool(state.get("supporterPlayed")),
                      more_prizes_than_opp=(my_prizes > opp_prizes),
                      turn=state.get("turn", 0), probe=probe)
        theirs = their_side if their_side is not None else TheirSide(
            opp, combat=combat, read=read, brief=brief, matchup_plan=matchup_plan,
            posture_confidence=posture_confidence, favorability=favorability,
            matchup_coverage=matchup_coverage, opponent=opponent, forward_ids=forward_ids,
            charged=charged, probe=probe)
        return cls(mine=mine, theirs=theirs, state=state, carried=carried, probe=probe)

    # -- turn / quota facts (observation reads, not Carried State) ------------------------------
    @property
    def turn(self) -> int:
        return int(self.state.get("turn") or 0)

    @property
    def energy_attached(self) -> bool:
        return bool(self.state.get("energyAttached"))

    @property
    def supporter_played(self) -> bool:
        return bool(self.state.get("supporterPlayed"))

    @property
    def stadium(self) -> tuple:
        return tuple((c or {}).get("id") for c in (self.state.get("stadium") or ()))

    # -- the cross-side derivation --------------------------------------------------------------
    @lazy
    def prize_race(self) -> PrizeRace:
        """The one canonical prize-race read (see :class:`PrizeRace`)."""
        return PrizeRace(
            my_prizes_remaining=self.mine.prizes_remaining,
            opp_prizes_remaining=self.theirs.prizes_remaining,
            prize_map=tuple((b.card_id, b.prize_value) for b in self.theirs.bodies))

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
        MUST make before passing ``their_side`` to :meth:`build`."""
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
