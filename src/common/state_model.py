"""The **StateModel** — one enriched, two-sided board snapshot per decision point (ADR-0068).

Every value equation reads this instead of re-deriving its own slice of the board. Three
load-bearing properties: **lazy** (each field memoizes on first access, so an unread field costs
nothing), **pure** (building writes nothing outside the model's own memo — cross-decision memory
lives in :class:`CarriedState`), and **reused by SIDE, never by patch**, guarded by
:attr:`StateModel.opponent_fingerprint`, which hashes their side WHOLESALE so an unanticipated
disruption invalidates by construction.

There is no ``apply(action)`` delta path. The one sanctioned route to a hypothetical board is the
apply seam (`common.apply_option`, ADR-0098) plus :meth:`StateModel.rebuilt`, which synthesizes a
fresh observation and rebuilds rather than mutating a model. Surviving direct ``CombatMath`` bypasses
are enumerated and reasoned in `tests/strategy/test_combat_bypass_census.py`.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import NamedTuple

from common import card_worth
from common.board_cards import body_card_ids, body_unit_codes
from common.deck_odds import p_contains
from common.strategy.combat import UNCHARGED     # the doom policy — see `TheirSide.doomed`
from common.strategy.combat import SurvivalClock
from common.strategy.combat import LinePrize
from common.strategy.context import PRIZE_CARDS
from common.strategy.damage_context import SideFacts
from common.strategy.damage_context import bench_gate_context
from common.strategy.damage_context import damage_context as _assemble_damage_context

#: Sentinel for "use the policy threaded at :meth:`StateModel.build`". An explicit ``charged=None``
#: means the worst-case CEILING, not "unset" — a plain ``None`` default would collapse the two.
_THREADED = object()

#: Fallback Bench cap when an observation omits the engine's own ``benchMax`` (rulebook L75).
_BENCH_MAX = 5

# ── the lazy field descriptor ──────────────────────────────────────────────────────────────────

class lazy:
    """A memoized StateModel field, computed on first read. Access is recorded on the owner's
    ``_probe`` when one is attached — instrumentation only, never consulted by a derivation."""

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
        """``_canonical(value)``, memoized per OBJECT. Keyed on ``id()`` yet sound: the entry holds a
        reference to the object, so its address cannot be reused while the entry lives."""
        if value is None or isinstance(value, (int, float, bool, str)):
            return value
        if isinstance(value, (list, tuple)):
            # Per-ELEMENT: counterfactual lists are FRESH objects differing from the real one by a
            # single entry, so caching the sequence wholesale would miss every time.
            return tuple(self._key(v) for v in value)
        hit = self._canon.get(id(value))
        if hit is not None and hit[0] is value:
            return hit[1]
        canon = _canonical(value)
        self._canon[id(value)] = (value, canon)
        return canon

    def _memoized(self, key, make):
        """Memo for a PARAMETERISED derivation, keyed by argument rather than by field name."""
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
    """A hidden-zone count in all three honest epistemics (ADR-0068): sound ``floor``, hypergeometric
    ``expected``, sound ``ceiling``, ``p_any`` (ADR-0074). Leg assignment: ``src/common/CONTEXT.md``."""
    floor: int = 0
    expected: float = 0.0
    ceiling: int = 0
    p_any: float = 0.0

    @property
    def possible(self) -> bool:
        """Not provably absent — the fail-open presence gate (ADR-0067)."""
        return self.ceiling > 0


def count_triple(unseen: int, prizes_hidden: int, deck_count: int) -> CountTriple:
    """The legs for ``unseen`` copies split over ``deck_count`` deck slots and ``prizes_hidden``
    face-down prizes. Pure; total; never raises. ``p_any`` IS ``deck_odds.p_contains`` (ADR-0074)."""
    try:
        u, k, d = max(0, int(unseen)), max(0, int(prizes_hidden)), max(0, int(deck_count))
    except Exception:
        return CountTriple()                       # unreadable inputs claim nothing (fail-closed)
    if u == 0 or d == 0:
        return CountTriple()
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
    """The narrow, DECLARED channel of facts persisting across decision points (ADR-0068). Read IN as
    an argument and handed BACK as a return value, so no derivation mutates state on read."""
    values: tuple = ()                             # ((name, value), …)

    MEMBERS = ("phase_prev", "my_path_prev", "known_top")

    @classmethod
    def of(cls, **members) -> "CarriedState":
        """A snapshot from keyword members. Unknown names are REJECTED — the channel stays narrow."""
        unknown = set(members) - set(cls.MEMBERS)
        if unknown:
            raise ValueError(f"undeclared Carried State member(s): {sorted(unknown)}")
        return cls(tuple(sorted(members.items(), key=lambda kv: kv[0])))

    def get(self, name, default=None):
        """The member's carried value, or ``default`` — the fail-closed read for an absent belief."""
        for k, v in self.values:
            if k == name:
                return v
        return default


# ── body views ────────────────────────────────────────────────────────────────────────────────

class ForwardPayoff(NamedTuple):
    """What a body's evolution line still OWES it — both sides' ``forward_payoff`` answer. The
    their-side supplier fails OPEN on ``reachable``; the divergence is argued at that method."""

    #: Best printed damage anywhere in the forward closure MINUS the card's own, floored at 0.
    owed_damage: float
    #: How many evolutions away that best form is; 0 when the card is already the best form.
    hops: int
    #: Is every step of that path still available (not provably outside my deck)?
    reachable: bool


class AttackPayoff(NamedTuple):
    """What a body can actually pay off with on THIS board — :meth:`_SideBase.attack_payoff`'s answer.
    Id and damage travel together: they are only sound as a pair, naming the same attack."""

    attack_id: int | None
    #: That attack's damage on this board, matchup-free — printed, with the attack's own board
    #: conditions applied (an unmet bench-partner condition reads 0). Never negative.
    damage: float


class AttackProfile(NamedTuple):
    """Everything ONE named attack of mine is worth asking about — :meth:`StateModel.attack_profile`.
    ONE record, not a family of accessors: the fields are only sound TOGETHER. Facts, never prices."""

    attack_id: int | None
    #: Can the attacker pay this cost and legally use it this turn, under the FULL Attach Budget?
    affordable: bool
    #: Damage against THEIR Active at ``bound="exact"`` — W/R, prevention, boosts and scalers applied.
    damage: float
    #: The same read at ``bound="min"`` / ``"max"`` — a conditional or coin attack's FLOOR and CEILING.
    damage_floor: float
    damage_ceiling: float
    #: Does the RECORD carry a conditional clause (``damageMin``/``damageMax``)? Not inferable from
    #: the three numbers: an unmet `requiresBench` gate also spreads the bounds, and is not a coin.
    conditional: bool
    #: Damage MATCHUP-FREE (no defender), board conditions applied — what a NEXT-turn quantity needs.
    printed: float
    #: ``bench_snipe`` is the INDIVISIBLE single-target rider; ``bench_spread`` the DISTRIBUTABLE
    #: counter total. Both ignore Weakness and Resistance by rule (ADR-0022).
    bench_snipe: int
    bench_spread: int
    #: Prizes each rider's own allocation takes on their Bench — the shipped `CombatMath` knapsacks.
    snipe_ko_prizes: int
    spread_ko_prizes: int
    #: ``((hp_remaining, prize_value), …)`` for the benched bodies a rider can reach — bench-immune
    #: bodies (`docs/rules.md` §11) and empty slots excluded.
    rider_targets: tuple
    #: The energy-recycle rider's printed ceiling (Aura Jab: *"attach up to 3"*). Carried BESIDE
    #: ``recover_units`` because that min-of-three bounds cannot say WHICH one bound.
    recover_n: int
    #: …the Energy it would ACTUALLY attach that a recipient can use — min of that ceiling, the
    #: matching fuel in the rider's source zone, and the recipients' need. Fractional for a deck rider.
    recover_units: float
    #: ATTACKER-side next-turn locks (ADR-0033): ``self_lock`` is *"can't use attacks"*,
    #: ``same_attack_lock`` is *"can't use THIS attack"* — priced apart by `strategy/sequence.py`.
    self_lock: bool
    same_attack_lock: bool


#: The fail-closed profile — every leg at its zero, so a caller never has a ``None`` branch to forget.
_EMPTY_ATTACK_PROFILE = AttackProfile(
    attack_id=None, affordable=False, damage=0.0, damage_floor=0.0, damage_ceiling=0.0,
    conditional=False, printed=0.0, bench_snipe=0, bench_spread=0, snipe_ko_prizes=0,
    spread_ko_prizes=0, rider_targets=(), recover_n=0, recover_units=0.0, self_lock=False,
    same_attack_lock=False)


class BodyView(_Lazily):
    """One Pokémon in play, with its typed Energy and its attacks' typed cost shapes. Typed reads
    delegate to ``CombatMath``: the model holds RESULTS, the oracle keeps the arithmetic."""

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
        """Damage counters ON this body — ``(maxHp - hp) // 10``, floored at 0. A counter is 10 damage
        (`docs/rulebook.txt` L172), so this is the COUNTABLE a scaler names, not the damage."""
        body = self.body
        return max(0, int(body.get("maxHp") or 0) - int(body.get("hp") or 0)) // 10

    @lazy
    def is_ex(self) -> bool:
        """This body is a Pokémon ``{ex}`` — **including a Mega Evolution Pokémon ex**, which IS an
        ``{ex}`` (`docs/rulebook.txt` L337). False without a resolvable stat."""
        return bool(self.stat is not None and self.stat.is_ex_body)

    @lazy
    def is_stage2(self) -> bool:
        """This body is a Stage 2 (engine ``CardData.stage2``). Fail-CLOSED: the scaler that reads
        this counts the ATTACKER's own Bench, so over-reading manufactures a phantom lethal."""
        return bool(getattr(self.stat, "stage2", False))

    @lazy
    def attached_types(self) -> dict:
        """``{EnergyType: count}`` attached — the typed supply a cost shape is matched against."""
        return self._combat.attached_type_counts(self.body)

    @lazy
    def energy_count(self) -> int:
        """Energy UNITS attached — the raw count the rules speak in. Deliberately NOT
        ``sum(attached_types.values())``, which counts only the TYPED Basic Energy a matcher resolves."""
        return len(self.energy_key)

    @lazy
    def energy_key(self) -> tuple:
        """The attached Energy as a HASHABLE tuple of ``EnergyType`` UNIT codes — what the cards
        PROVIDE, never card ids (those live on ``energyCards``). One Ignition contributes ``(0, 0, 0)``."""
        return body_unit_codes(self.body)

    # No `payoff_attack` here on purpose: "which attack pays best" needs the attacker's BENCH, which
    # a view of one body cannot see. It lives once, on :meth:`_SideBase.attack_payoff`.

    @lazy
    def prize_value(self) -> int:
        """Prizes the opponent takes for knocking this body out — card knowledge (ADR-0052)."""
        return self._combat.prize_value(self.body)

    @lazy
    def tool_ids(self) -> tuple:
        """Pokémon Tool card ids attached to this body, in attach order. Homes the ``attached_tools``
        zone of the §3c completeness contract (:mod:`common.snapshot_coverage`)."""
        return tuple((c or {}).get("id") if isinstance(c, dict) else c
                     for c in (self.body.get("tools") or ())
                     if (c.get("id") if isinstance(c, dict) else c) is not None)

    @lazy
    def grant(self) -> dict:
        """The live ADR-0033 transient grant on this body — ``{}`` when none or untracked. Homes the
        ``transient_grants`` §3c zone; keys are the tracker's own vocabulary."""
        return dict(self._combat._grant(self.body) or {})

    @lazy
    def new_in_play(self) -> bool:
        """This body ENTERED PLAY this turn (``appearThisTurn``), so it cannot be evolved. Homes the
        ``new_in_play`` §3c zone; absent reads False — the PERMISSIVE direction for an evolve."""
        return bool(self.body.get("appearThisTurn"))


# ── the two sides ─────────────────────────────────────────────────────────────────────────────

class _SideBase(_Lazily):
    """What both sides expose. Asymmetric detail lives in the two subclasses deliberately: my hand is
    cards and theirs is a number, and making that an AttributeError is the point."""

    def __init__(self, player: dict, *, combat, probe=None, prefix="side", turn_boosts=()):
        super().__init__(probe=probe)
        self._probe_prefix = prefix
        self.player = player or {}
        self._combat = combat
        #: This side's this-turn flat damage-boost PLAYS — ``((amount, attackerEnergyType|None,
        #: vsExOnly), …)``. Threaded in: it is a LOG fact no snapshot of the board could recover.
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
        return None if self.active is None else self.active.body

    @lazy
    def body_raws(self) -> tuple:
        return tuple(b.body for b in self.bodies)

    @lazy
    def bench_names(self) -> tuple:
        """The BENCHED bodies' card names, in bench order — ``""`` for an unresolvable card, so the
        tuple stays positional. Bench only: an Active Lunatone does not satisfy *"on your Bench"*."""
        return tuple((b.stat.name if b.stat is not None else "") for b in self.bench)

    @lazy
    def in_play_names(self) -> tuple:
        """Every IN-PLAY body's card name — Active first, then Bench, ``""`` when unresolvable. The
        Bench IS in play alongside the Active (`docs/rulebook.txt` L559), so an Active counts itself."""
        return tuple((b.stat.name if b.stat is not None else "") for b in self.bodies)

    @lazy
    def in_play_attack_names(self) -> tuple:
        """Per IN-PLAY body (Active first, then Bench), that body's printed attack NAMES. NESTED
        because the predicate counts BODIES; an unresolvable body contributes () — fail-closed."""
        attack_stat = self._combat.attack_stat      # hoisted: the accessor rebuilds a fallback lambda
        out = []
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
        """The BENCHED bodies' raw engine dicts — the Bench Harvest's input (ADR-0071 decision 7)."""
        return tuple(b.body for b in self.bench)

    def attack_payoff(self, body) -> AttackPayoff:
        """The best attack ``body`` can actually pay off with **on this board**, and its damage — the
        conditional counterpart of ``CardStat.maxDamage`` (ADR-0109). Matchup-free, ``bound="exact"``."""
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
        """The :class:`BodyView` for ``body`` — the raw-engine-dict adapter. Lookup is by IDENTITY
        against this side's bodies; a body not in play (a hypothetical) gets a fresh, BENCHED view."""
        if body is None or isinstance(body, BodyView):
            return body
        for view in self.bodies:
            if view.body is body:
                return view
        return BodyView(body, combat=self._combat, is_active=False, probe=self._probe,
                        prefix=f"{self._probe_prefix}.hypothetical")

    @lazy
    def bench_count(self) -> int:
        """Bodies on this side's Bench. **THE** supplier of the count."""
        return len(self.bench)

    @lazy
    def bench_full(self) -> bool:
        """No room left on this side's Bench. Reads the engine's own ``benchMax``, falling back to
        the shipped 5 only when the observation omits it."""
        return self.bench_count >= int(self.player.get("benchMax") or _BENCH_MAX)

    @lazy
    def conditions(self) -> frozenset:
        """The Special Conditions on this side's ACTIVE — a SIDE-level read describing a BODY, since
        only the Active can carry one (`docs/rules.md` §8). The whole set, not just the blocking two."""
        return frozenset(c for c in ("poisoned", "burned", "asleep", "paralyzed", "confused")
                         if self.player.get(c))

    # -- hand ------------------------------------------------------------------------------------
    @property
    def hand_size(self) -> int:
        """Cards in this side's hand — **required of both subclasses**, declared here because
        :attr:`damage_facts` reads it off a plain ``_SideBase``. The two derivations differ."""
        raise NotImplementedError(f"{type(self).__name__} must answer hand_size")

    # -- prizes / zones -------------------------------------------------------------------------
    @lazy
    def prizes_remaining(self) -> int:
        return len(self.player.get("prize") or [])

    @lazy
    def prizes_taken(self) -> int:
        """Prizes this side has ALREADY taken. Deliberately NOT ``PRIZE_CARDS - prizes_remaining``:
        an ABSENT ``prize`` zone would then claim all six taken, so absence is checked first."""
        prize = self.player.get("prize")
        return max(0, PRIZE_CARDS - len(prize)) if prize is not None else 0

    @lazy
    def discard_energy_counts(self) -> dict:
        """``{EnergyType: count}`` of Basic Energy in this side's discard — a PUBLIC zone in both
        directions, so a sound count and never an estimate."""
        out: Counter = Counter()
        for card in (self.player.get("discard") or []):
            cid = (card or {}).get("id")
            stat = self._combat._card_stat(cid) if cid is not None else None
            if stat is not None and stat.is_typed_basic_energy:
                out[stat.energyType] += 1
        return dict(out)

    @lazy
    def discard_ids(self) -> tuple:
        """Every card id in this side's discard, in zone order — the full public contents. Ordered
        because the zone is; ids rather than stats because every downstream oracle keys on the id."""
        return tuple((c or {}).get("id") for c in (self.player.get("discard") or [])
                     if (c or {}).get("id") is not None)

    @lazy
    def discard_energy_total(self) -> int:
        """EVERY Energy card in this side's discard, Basic and Special alike — what an UNTYPED
        Riptide-class scaler counts. :attr:`discard_energy_counts` is the typed histogram."""
        return sum(1 for cid in self.discard_ids
                   if (st := self._combat._card_stat(cid)) is not None and st.is_energy)

    # -- the Damage Formula's per-side countables (POC-T3.5, Issue #279) ------------------------
    @lazy
    def damage_boosts(self) -> tuple:
        """Flat damage boosts live for THIS side's attacks — ``((amount, type, vsEx), …)``. Two
        sources: this turn's tracked Trainer plays (:attr:`_turn_boosts`) and the Active's Tools."""
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
        """This side's :class:`~common.strategy.damage_context.SideFacts` — what this side HAS, never
        what it is doing; the ``atk_``/``def_`` split is `damage_context`'s decision alone."""
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
        else ``(None, None)`` — the honest answer for the opponent. :class:`MySide` overrides it."""
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
        #: The deck tracker's exact prize multiset once a search ANCHORED it, else ``None``. ``None``
        #: and ``{}`` differ: None is *"claim nothing"*, ``{}`` is an anchor saying *"no prizes left"*.
        self._own_prizes = own_prizes
        #: The caller-supplied Needs resolution and Role-Worth resolver. Both are RESOLVERS rather
        #: than facts — neither is derivable from the snapshot the model holds.
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
        """Cards in my hand — the COUNT, deliberately not ``len(hand_ids)``, which drops a card the
        observation gives without an ``id``. ``handCount`` is the authority where present."""
        count = self.player.get("handCount")
        return int(count) if count is not None else len(self.player.get("hand") or [])

    @lazy
    def hand_energy_counts(self) -> dict:
        """``{EnergyType: count}`` of Basic Energy in my hand — the manual attach's immediately
        playable supply, as a COUNT because "one {R} left" and "three" are different decisions."""
        counts: Counter = Counter()
        for cid in self.hand_ids:
            stat = self._combat._card_stat(cid)
            if stat is not None and stat.is_typed_basic_energy:
                counts[stat.energyType] += 1
        return dict(counts)

    @lazy
    def hand_energy_types(self) -> frozenset:
        return frozenset(self.hand_energy_counts)

    def role_worth(self, card_id) -> float:
        """A card's **Worth** in `card_worth` points, via the caller's ``card_id -> Worth`` callable —
        Roles are DECLARED, not card facts. Without a resolver this is 0 for any Pokémon."""
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
        """My card copies provably OUTSIDE the deck: hand, discard, every board body (attached Energy
        CARDS, Tools, stacked pre-evolutions) and any FACE-UP prize. The walk is `body_card_ids`."""
        counts: Counter = Counter()
        for zone in ("hand", "discard"):
            for card in (self.player.get(zone) or []):
                if card and card.get("id") is not None:
                    counts[card["id"]] += 1
        for prize in (self.player.get("prize") or []):
            if prize and prize.get("id") is not None:      # face-down prizes are None
                counts[prize["id"]] += 1
        for body in self.body_raws:
            for cid in body_card_ids(body):
                counts[cid] += 1
        return counts

    @lazy
    def unseen_counts(self) -> dict:
        """``{card id: copies not provably outside my deck}`` — decklist minus visible, minus the
        prized copies once ``own_prizes`` anchors them."""
        unseen = Counter(self._deck)
        unseen.subtract(self.visible_counts)
        if self._own_prizes:
            unseen.subtract(Counter({int(k): v for k, v in dict(self._own_prizes).items()}))
        return {cid: n for cid, n in unseen.items() if n > 0}

    @lazy
    def prizes_hidden(self) -> int:
        """Face-down prizes of mine. 0 once ``own_prizes`` anchors them — the regime switch every
        leg of the Count Triple collapses on."""
        if self._own_prizes:
            return 0
        return sum(1 for p in (self.player.get("prize") or [])
                   if not (isinstance(p, dict) and p.get("id") is not None))

    @lazy
    def deck_count(self) -> int:
        """Cards left in my deck. Pre-anchor this is the unseen pool minus the hidden prize slots;
        anchored it is the unseen pool itself."""
        return max(0, sum(self.unseen_counts.values()) - self.prizes_hidden)

    @lazy
    def deck_energy_counts(self) -> dict:
        """``{EnergyType: CountTriple}`` — per-type Basic Energy still in my deck, in all three
        epistemics. The ONE derivation the three side-level legs below project from."""
        per_type: Counter = Counter()
        for cid, n in self.unseen_counts.items():
            stat = self._combat._card_stat(cid)
            if stat is not None and stat.is_typed_basic_energy:
                per_type[stat.energyType] += n
        hidden, deck = self.prizes_hidden, self.deck_count
        return {t: count_triple(n, hidden, deck) for t, n in per_type.items()}

    @lazy
    def deck_energy_types(self) -> frozenset:
        """Basic-Energy TYPES my deck can still yield — the SOUND *not-provably-empty* set
        (``ceiling > 0``, ADR-0067). Fails OPEN by design; ``deck_empty`` can only narrow it."""
        return self._narrowed(frozenset(t for t, c in self.deck_energy_counts.items()
                                        if c.possible))

    @lazy
    def deck_energy_types_provable(self) -> frozenset:
        """The same set on the ``floor >= 1`` leg — the **Provable Budget**'s deck argument, failing
        CLOSED. Expect it EMPTY pre-anchor; a consumer about to SPEND something that expires takes it."""
        return self._narrowed(frozenset(t for t, c in self.deck_energy_counts.items()
                                        if c.floor >= 1))

    @lazy
    def deck_energy_p(self) -> dict:
        """``{EnergyType: P(my deck still holds >=1)}`` — the Probability Leg (ADR-0074). Read ONLY
        by a consumer whose output is a compared SCALAR; a type narrowed away reads 0.0."""
        allowed = self.deck_energy_types                    # already `_narrowed`, so sound-capped
        return {t: (c.p_any if t in allowed else 0.0)
                for t, c in self.deck_energy_counts.items()}

    def _deck_facts(self) -> tuple:
        """``(cards left in my deck, {EnergyType: Basic-Energy count})`` — exact, or ``(None, None)``
        while the prizes are unresolved, because an unseen copy could still be sitting in a prize."""
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
        inputs are sound, so the intersection stays sound on either leg."""
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
        """This turn's full **Attach Budget** toward ``body`` (ADR-0067), memoized per body by VALUE.
        ``manual_spent`` closes the manual leg — the attach marginal's counterfactual (ADR-0069 §2)."""
        if body is None:
            return None
        return self.attach_budget_for_card(body.card_id, benched=not body.is_active,
                                           manual_spent=manual_spent, provable=provable)

    def attach_budget_for_card(self, card_id, *, benched: bool, manual_spent: bool = False,
                               provable: bool = False, supporter_spent: bool = False):
        """The Budget toward a card id rather than a body in play — the real primitive, for a
        HYPOTHETICAL attacker. ``supporter_spent`` closes the Supporter leg (ADR-0075 decision 3)."""
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
        None scans EVERY attack. A COST question only — the rules half is :attr:`attack_blocked`."""
        if body is None:
            return False
        key = ("reachable_attach", body.card_id, body.is_active, body.energy_key,
               attack_id, bool(provable))
        return self._memoized(key, lambda: self._combat.reachable_attach(
            body.body, attack_id, budget=self.attach_budget(body, provable=provable)))

    @lazy
    def attack_blocked(self) -> bool:
        """The rules forbid me an attack this turn AT ALL: Asleep or Paralyzed (`docs/rulebook.txt`
        L190 / L206), or the first player on turn 1 (L152; ``turn <= 1`` is the shipped idiom)."""
        if self.turn <= 1:
            return True
        return bool(self.player.get("asleep") or self.player.get("paralyzed"))

    @lazy
    def active_famine(self) -> bool:
        """**Famine**: my Active cannot attack this turn — :attr:`attack_blocked` composed with
        :meth:`reachable_attach`. Fails OPEN on an unreadable body: "I cannot tell" is not a famine."""
        if self.attack_blocked:
            return True                     # the rules settle it without reading a single stat
        body = self.active
        if body is None or body.stat is None:
            return False                    # an unreadable body is not a demonstrable famine
        return not self.reachable_attach(body)

    def best_reachable_damage(self, body: BodyView | None, *, extra_unit_codes=(),
                              manual_spent: bool = False) -> float:
        """Biggest PRINTED damage ``body`` can reach this turn under its Budget, optionally over a
        body carrying ``extra_unit_codes``: ``EnergyType`` UNIT codes, **never card ids** (Issue #418)."""
        if body is None:
            return 0.0
        extra = tuple(extra_unit_codes)
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
        """Biggest damage ``body`` can reach AGAINST ``defender`` — the damage-model sibling, so
        Weakness, Resistance, prevention and boosts reach the answer. ``context`` is `attacker="mine"`."""
        if body is None:
            return 0.0
        target = defender.body if defender is not None else None
        key = ("best_reachable_damage_vs", body.card_id, body.is_active, body.energy_key,
               self._key(target), self._key(context))
        return self._memoized(key, lambda: self._combat.best_reachable_damage_vs(
            body.body, target, budget=self.attach_budget(body), context=context))

    def best_reachable_bench_damage(self, body: BodyView | None,
                                    defender: BodyView | None) -> float:
        """Biggest damage ``body`` can put on ONE of their BENCHED bodies — the snipe RIDER route,
        not printed damage. No ``context``: a rider is a constant no scaler reaches (ADR-0022)."""
        if body is None:
            return 0.0
        target = defender.body if defender is not None else None
        key = ("best_reachable_bench_damage", body.card_id, body.is_active, body.energy_key,
               self._key(target))
        return self._memoized(key, lambda: self._combat.best_reachable_bench_damage(
            body.body, target, budget=self.attach_budget(body)))

    def readiness_p(self, body: BodyView | None, attack_id=None, *, enabler_budget=None,
                    copies: int = 0, pool: int = 0, draws: int = 0, weighted: bool = True) -> float:
        """P(``body`` is ready to use the attack this turn) — the ONLY honest probability in the
        affordability family. ``weighted`` also prices the deck-fetch leg by :attr:`deck_energy_p`."""
        if body is None:
            return 0.0
        return self._combat.readiness_p(body.body, attack_id, budget=self.attach_budget(body),
                                        enabler_budget=enabler_budget, copies=copies,
                                        pool=pool, draws=draws,
                                        p_by_type=self.deck_energy_p if weighted else None)

    def turns_to_afford(self, body, *, attaches_per_turn: int = 1,
                        exclude_expiring: bool = False) -> int | None:
        """**The Two Clocks**, my half (ADR-0070 §6): the earliest future turn ``body``'s line is ARMED
        — MAX of the energy-deficit and forward-hop legs. ``exclude_expiring`` drops end-of-turn fuel."""
        view = self.view_of(body)
        if view is None:
            return None
        return self._memoized(("mine_turns_to_afford", self._key(view.body), attaches_per_turn,
                               bool(exclude_expiring)),
                              lambda: self._combat.turns_to_afford(
                                  self._combat.without_expiring_energy(view.body)
                                  if exclude_expiring else view.body,
                                  attaches_per_turn=attaches_per_turn, typed=True))

    @lazy
    def needs(self):
        """The caller-resolved Needs slots (ADR-0065), or None. The model holds the resolution so
        several equations read one assignment; it never owns the DP."""
        resolver = self._needs
        return resolver() if callable(resolver) else resolver

    # -- evolution topology (the forward closure over MY decklist) ------------------------------
    @lazy
    def forward_index(self) -> dict:
        """``{pre-evolution NAME: (card ids in my deck that evolve from it, …)}``. Evolution is by
        NAME (`docs/rules.md` §4). MY deck only: a form I do not run is not a form my line reaches."""
        index: dict = {}
        for cid in set(self._deck):
            stat = self._combat._card_stat(cid)
            base = getattr(stat, "evolvesFrom", None) if stat is not None else None
            if base:
                index.setdefault(base, []).append(cid)
        return {name: tuple(sorted(ids)) for name, ids in index.items()}

    def forward_form_ids(self, card_id) -> frozenset:
        """Every card id in ``card_id``'s forward closure, multi-hop, from MY decklist — not the
        universal pool the Pilot's `_forward_card_ids` reads. Cycle-guarded against a data slip."""
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
        """:class:`ForwardPayoff` for ``card_id``'s line — what evolving it still OWES. Card knowledge
        plus my zones; fails closed at ``ForwardPayoff(0.0, 0, True)`` on an unknown card."""
        return self._memoized(("forward_payoff", card_id), lambda: self._forward_payoff(card_id))

    def _forward_payoff(self, card_id) -> "ForwardPayoff":
        stat = self._combat._card_stat(card_id) if card_id is not None else None
        if stat is None:
            return ForwardPayoff(0.0, 0, True)
        own = float(getattr(stat, "maxDamage", 0) or 0)
        held = set(self.hand_ids)
        unseen = self.unseen_counts
        best = ForwardPayoff(0.0, 0, True)
        # `seen` guards a self-referential decklist: the rules cannot produce an evolution cycle,
        # but a data slip must not hang a value equation on the grader.
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
        #: The Opponent Model facade (ADR-0047) — all opponent knowledge beyond the visible zones.
        self.opponent = opponent
        self._forward_ids = forward_ids
        self._charged = charged

    @lazy
    def hand_size(self) -> int:
        """Cards in their hand. The engine gives the count and never the contents, so this is the
        whole of their hand knowledge — and **THE** supplier of the opponent hand count."""
        return int(self.player.get("handCount") or 0)

    @lazy
    def deck_count(self) -> int:
        return int(self.player.get("deckCount") or 0)

    # -- the clock family (ADR-0064 / the Threat-Clock unification) -----------------------------
    def _bodies(self, bodies):
        """The opponent board a clock read runs against — their real one unless a COUNTERFACTUAL
        list is supplied (a removal Δ, a spliced strip, one body alone). A first-class question."""
        return self.body_raws if bodies is None else tuple(bodies)

    def _charged_policy(self, charged):
        """The energy policy for one clock read: the Read's threaded budget unless the consumer names
        its own. ``None`` passed explicitly is the worst-case CEILING, distinct from "unset"."""
        return self._charged if charged is _THREADED else charged

    def incoming(self, my_body: dict | None, t: int = 1, *, bodies=None,
                 charged=_THREADED, forward_ids=_THREADED, evo_min_energy: int = 0,
                 context: dict | None = None, my_benched: bool = False,
                 opp_active: dict | None = None, switch_enabler: bool = False) -> int:
        """Worst W/R-adjusted damage their affordable attackers could deal ``my_body`` at future turn
        ``t`` — the Threat-Clock curve. ``t=1`` is Reachable Incoming. EVERY argument is in the key."""
        opp_bodies = self._bodies(bodies)
        policy = self._charged_policy(charged)
        fwd = self._forward_ids if forward_ids is _THREADED else forward_ids
        # `fwd` goes into the key AS THE CALLABLE, not its id(): a function is hashable, so a fresh
        # closure can only cost a memo MISS, never an id collision serving another index's answer.
        key = ("incoming", self._key(my_body), t, self._key(opp_bodies), self._key(policy), fwd,
               evo_min_energy, self._key(context), bool(my_benched), self._key(opp_active),
               bool(switch_enabler))
        return self._memoized(key, lambda: self._combat.incoming(
            my_body, opp_bodies, t, forward_ids=fwd,
            charged=policy, evo_min_energy=evo_min_energy, context=context,
            my_benched=my_benched, opp_active=opp_active, switch_enabler=switch_enabler))

    def reachable_incoming(self, my_body: dict | None, **kwargs) -> int:
        """``incoming(t=1)`` — their next single development step."""
        return self.incoming(my_body, 1, **kwargs)

    def doomed(self, my_body: dict | None, **kwargs) -> bool:
        """Can they Knock Out ``my_body`` next turn? — the composed survival boolean. Defaults to
        :data:`~common.strategy.combat.UNCHARGED`, the doom policy; other kwargs reach :meth:`incoming`."""
        hp = (my_body or {}).get("hp", 0)
        if not hp:
            return False                              # no live body: no claim, never a doom cry
        kwargs.setdefault("charged", UNCHARGED)
        return int(self.incoming(my_body, 1, **kwargs)) >= hp

    def turns_to_afford(self, body, *, attaches_per_turn: int = 1, fuelled: bool = True) -> int | None:
        """The earliest future turn ``body``'s line is ARMED. None when unknown (fail-closed).
        ``fuelled`` credits the line's own discard RECURSION at the ``self_arming`` scope (Issue #204)."""
        view = self.view_of(body)
        if view is None:
            return None
        raw = view.body
        fuel = self._arming_recur_fuel(view) if fuelled else 0
        if fuel:
            # The reload is TYPED, so the augmented body must carry typed UNIT CODES, not bare
            # counts, or the oracle's typed leg would read them as colourless.
            raw = dict(raw, energies=list(raw.get("energies") or ()) + self._recur_unit_codes(view, fuel))
        return self._memoized(("turns_to_afford", self._key(raw), attaches_per_turn),
                              lambda: self._combat.turns_to_afford(
                                  raw, forward_ids=self._forward_ids,
                                  attaches_per_turn=attaches_per_turn))

    def _arming_recur_fuel(self, view: "BodyView") -> int:
        """The discard reload that reaches ``view``'s OWN attack cost. Distinct from
        :meth:`discard_recur_fuel`, the fail-OPEN "could they refuel at all" the doom relax takes."""
        return self._memoized(("arming_recur_fuel", self._key(view.body)),
                              lambda: self._combat.discard_recur_fuel(
                                  view.body, self.discard_energy_counts,
                                  forward_ids=self._forward_ids, scope="self_arming"))

    def _recur_unit_codes(self, view: "BodyView", count: int) -> list:
        """``count`` ``EnergyType`` UNIT codes of the recur line's own type — typed, because the
        clock matches a cost SHAPE. Returns fewer than asked when the discard cannot supply them."""
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
                out.append(int(st.energyType))
        return out

    def _recur_form_ids(self, view: "BodyView") -> tuple:
        """``view``'s line — its own card id then its forward forms — in the order the recursion
        oracle scans them, so the reloaded type is read off the form that oracle picked."""
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
        """The ACTIVE-area survival clock — accumulating, per ADR-0071 decision 4. Every argument is
        in the memo key. Reads :meth:`survival_clock`'s ``.turns``, so both routes share ONE memo."""
        return self.survival_clock(
            my_body, bodies=bodies, charged=charged, my_benched=my_benched, my_bench=my_bench,
            key_ids=key_ids, reading=reading, opp_active=opp_active,
            switch_enabler=switch_enabler, context=context).turns

    def survival_clock(self, my_body: dict | None, *, bodies=None, charged=_THREADED,
                       my_benched: bool = False, my_bench=(),
                       key_ids=frozenset(), reading: str | None = None,
                       opp_active: dict | None = None, switch_enabler: bool = False,
                       context: dict | None = None) -> SurvivalClock:
        """The ACTIVE-area survival clock at BOTH resolutions — :meth:`turns_to_ko_me`'s integer plus
        the interpolated crossing point (ADR-0117), off ONE accumulation and ONE memo entry."""
        opp_bodies = self._bodies(bodies)
        policy = self._charged_policy(charged)
        key = ("survival_clock", self._key(my_body), self._key(opp_bodies), self._key(policy),
               bool(my_benched), self._key(tuple(my_bench or ())), frozenset(key_ids or ()),
               reading, self._key(opp_active), bool(switch_enabler), self._key(context))
        extra = {} if reading is None else {"reading": reading}
        return self._memoized(key, lambda: self._combat.survival_clock(
            my_body, opp_bodies, charged=policy, my_benched=my_benched,
            my_bench=my_bench, key_ids=key_ids, opp_active=opp_active,
            switch_enabler=switch_enabler, context=context, **extra))

    def bench_harvest_clock(self, my_bench, *, bodies=None, charged=_THREADED,
                            key_ids=frozenset(), reading: str | None = None,
                            opp_active: dict | None = None) -> dict:
        """``{bench index: first turn it falls in the harvest}`` over MY whole Bench — the
        shared-budget clock, solved once. :meth:`turns_to_ko_me` reads it underneath."""
        opp_bodies = self._bodies(bodies)
        policy = self._charged_policy(charged)
        key = ("bench_harvest_clock", self._key(tuple(my_bench or ())), self._key(opp_bodies),
               self._key(policy), frozenset(key_ids or ()), reading, self._key(opp_active))
        extra = {} if reading is None else {"reading": reading}
        return self._memoized(key, lambda: self._combat.bench_harvest_clock(
            my_bench, opp_bodies, charged=policy, key_ids=key_ids,
            opp_active=opp_active, **extra))

    def discard_recur_fuel(self, body) -> int:
        """Basic Energy their discard can reload onto ``body`` (the Aura-Jab class), which makes a
        KO'd threat's line persistent. Takes a :class:`BodyView` or a raw engine dict."""
        view = self.view_of(body)
        if view is None:
            return 0
        return self._memoized(("discard_recur_fuel", self._key(view.body)),
                              lambda: self._combat.discard_recur_fuel(
                                  view.body, self.discard_energy_counts,
                                  forward_ids=self._forward_ids))

    # -- evolution topology (the forward closure over the POOL) ---------------------------------
    def forward_payoff(self, card_id) -> "ForwardPayoff":
        """:class:`ForwardPayoff` for one of THEIR bodies, so removing it can be priced for what it
        DENIES. ``reachable`` is not computable on a hidden deck and fails OPEN — always True."""
        return self._memoized(("their_forward_payoff", card_id),
                              lambda: ForwardPayoff(
                                  *self._combat.forward_payoff_terms(
                                      card_id, forward_ids=self._forward_ids),
                                  True))

    def forward_line_prize(self, card_id) -> "LinePrize":
        """:class:`~common.strategy.combat.LinePrize` for one of THEIR bodies — the PRIZE its line
        presents (ADR-0119), through the same ``forward_ids`` gate and the same fail-OPEN read."""
        return self._memoized(
            ("their_forward_line_prize", card_id),
            lambda: self._combat.forward_line_prize(card_id, forward_ids=self._forward_ids))


# ── the model ─────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PrizeRace:
    """The cross-side prize composite (ADR-0068 decision 4). Top-level because it reads BOTH sides;
    per-body prize YIELD stays on the combat oracle."""
    my_prizes_remaining: int = 0
    opp_prizes_remaining: int = 0

    # No `ko_wins_now` helper on purpose: the KO-wins question is NOT one line — the live win rung
    # composes it with the simultaneous-draw guard (a recoil KO makes it a draw).


class StateModel(_Lazily):
    """The snapshot. Build it with :meth:`build`; read fields off :attr:`mine` / :attr:`theirs` and
    the cross-side derivations here."""

    _probe_prefix = "model"

    #: The observation :meth:`build` was handed and the knowledge seams it came with. ``(None, {})``
    #: on a directly-constructed model, which is why :meth:`rebuilt` raises rather than guessing.
    _origin: tuple = (None, {})

    def __init__(self, *, mine: MySide, theirs: TheirSide, state: dict, my_index: int = 0,
                 carried: CarriedState = CarriedState(), probe=None):
        super().__init__(probe=probe)
        self.mine = mine
        self.theirs = theirs
        self.state = state or {}
        #: Which seat is mine — the Stadium's owner cannot be read off either side's PlayerState.
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
        """The snapshot for one decision point — cheap, because it computes nothing yet. ``needs`` may
        be a Resolution or a board-bound ``(obs, my_index) -> Resolution`` supplier, re-bound on rebuild."""
        state = (obs or {}).get("current") or {}
        players = state.get("players") or []
        mi = state.get("yourIndex", 0) if my_index is None else my_index
        me = players[mi] if 0 <= mi < len(players) and players[mi] else {}
        opp = players[1 - mi] if 0 <= 1 - mi < len(players) and players[1 - mi] else {}
        my_prizes, opp_prizes = len(me.get("prize") or []), len(opp.get("prize") or [])
        boosts_for = getattr(turn_boosts, "boosts_for", None)
        # Bound to THIS observation; `_origin` keeps the unbound supplier so `rebuilt` re-binds.
        resolver = (lambda: needs(obs, mi)) if callable(needs) else needs
        mine = MySide(me, combat=combat, deck=deck, deck_empty=deck_empty,
                      own_prizes=(obs or {}).get("own_prizes"), needs=resolver, role_worth=role_worth,
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
        """**The ONE sanctioned route to a hypothetical board** (Issue #382): a FRESH model over
        ``obs``, never a patch. ``reuse_their_side`` requires the caller to have proven sharing."""
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
        """The observation :meth:`build` was handed, or ``{}`` — the whole envelope the apply seam
        needs (the live ``select``, the ``own_prizes`` anchor). A reference, not a copy."""
        return self._origin[0] or {}

    # -- the knowledge seams, as public reads -------------------------------------------------
    # Three accessors, so no caller reaches across a module boundary for `model.mine._combat`.
    @property
    def combat(self):
        """The `CombatMath` oracle this snapshot was built with. The apply seam needs it to resolve a
        card that is not on the board yet — the one in hand being played."""
        return self.mine._combat

    @property
    def deck(self) -> tuple:
        """My DECKLIST as declared to :meth:`build` — the 60 cards, not what is left in the deck.
        ``()`` when none was threaded; the emptiness question is :attr:`MySide.deck_count`'s."""
        return self.mine._deck

    @property
    def my_pokemon_koed_last_turn(self) -> bool:
        """The exact log-derived Resource fact, or False without the opponent-model seam."""
        return bool(getattr(getattr(self.theirs, "opponent", None), "my_pokemon_koed_last_turn", False))

    def card_stat(self, card_id):
        """This card's `CardStat`, or None — the model's own door onto the Stat Provider, so the
        seam's telemetry can name a card without reaching into another object's privates."""
        return self.mine._combat._card_stat(card_id)

    # -- turn / quota facts: the per-turn ALLOWANCES, and the §3c contract's homes for them ------
    # A differencing system must see that a play SPENT one, or it prices the spend at 0.
    @property
    def energy_attached(self) -> bool:
        return bool(self.state.get("energyAttached"))

    @property
    def supporter_played(self) -> bool:
        return bool(self.state.get("supporterPlayed"))

    @property
    def retreated(self) -> bool:
        """The one Retreat for this turn is spent. Homes the ``allowance_retreat_used`` zone — an
        illegal option priced like a legal one is a phantom line, not a small error."""
        return bool(self.state.get("retreated"))

    @property
    def stadium_played(self) -> bool:
        return bool(self.state.get("stadiumPlayed"))

    @property
    def stadium(self) -> tuple:
        """Stadium card ids in play (0- or 1-long) — the engine's shape, and what the fingerprint
        hashes."""
        return tuple((c or {}).get("id") for c in (self.state.get("stadium") or ()))

    @property
    def stadium_id(self):
        return self.stadium[0] if self.stadium else None

    @property
    def stadium_is_theirs(self) -> bool:
        """The Stadium in play is THEIRS. False when none is out or the card carries no
        ``playerIndex`` — an unowned Stadium is nobody's to be punished for."""
        card = (self.state.get("stadium") or [None])[0]
        if not card:
            return False
        owner = card.get("playerIndex")
        return owner is not None and owner != self.my_index

    # -- the cross-side derivation --------------------------------------------------------------
    @lazy
    def prize_race(self) -> PrizeRace:
        return PrizeRace(my_prizes_remaining=self.mine.prizes_remaining,
                         opp_prizes_remaining=self.theirs.prizes_remaining)

    def damage_context(self, *, attacker: str) -> dict:
        """The Damage Formula's scaler context from THIS model, memoized per ``attacker`` direction
        (``"mine"``/``"theirs"``). Identity-stable for the model's lifetime, so clock memo keys HIT."""
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
        """:class:`AttackProfile` for ONE attack of one of MY bodies. On the model, not `MySide`:
        the legs need THEIR Active, THEIR Bench and both sides' scaler context. Fails closed."""
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
        # Their Bench as the rider oracles want it: (card id, remaining HP). The oracles apply the
        # bench rules themselves, so this forms no second opinion about who is reachable.
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
        """``((hp_remaining, prize_value), …)`` for the benched bodies a rider can reach. Immunity is
        the SAME predicate the rider oracles use (`CombatMath.is_tera`), so the two cannot disagree."""
        return tuple((hp, int(self.combat.prize_value({"id": cid})))
                     for cid, hp in bench_pairs if not self.combat.is_tera(cid))

    def _recover_units(self, stat) -> float:
        """`Pilot._recover_units`' three bounds — printed ceiling, matching fuel in the rider's source
        zone, recipients' need — re-derived from model facts. ⚠️ A SECOND copy; nothing stops drift."""
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
        forward form's, whichever is dearer. An unreadable attack contributes cost 0, never 99."""
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
        """A WHOLESALE hash of everything that could change their side's derivations — their whole
        ``PlayerState`` plus the shared Stadium, the transient-grant generation and their turn boosts."""
        return hash((_canonical(self.theirs.player), self.stadium, self._transient_generation,
                     self.theirs._turn_boosts))

    @lazy
    def _transient_generation(self):
        tracker = getattr(self.mine._combat, "_transients", None)
        return getattr(tracker, "generation", None) if tracker is not None else None

    def shares_opponent_with(self, other: "StateModel") -> bool:
        """True when ``other``'s :attr:`theirs` may be reused for this board — the check a caller MUST
        make before passing ``their_side``. **Kept deliberately with no runtime caller** (Issue #150)."""
        return (other is not None
                and self.opponent_fingerprint == other.opponent_fingerprint)


def _canonical(value):
    """A hashable, order-faithful projection of an engine zone/record. Order is MEANING here: which
    body sits in ``active`` versus ``bench`` is exactly what a gust changes."""
    if isinstance(value, dict):
        return tuple((k, _canonical(v)) for k, v in sorted(value.items(), key=lambda kv: str(kv[0])))
    if isinstance(value, (list, tuple)):
        return tuple(_canonical(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((str(v) for v in value)))
    return value
