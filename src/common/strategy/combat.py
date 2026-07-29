"""CombatMath — the KO oracle (ADR-0052): one closed-form home for damage/KO judgment.

Constructed from the knowledge seams — the Stat Provider (ADR-0056), ``CardFunctions``, and the
match-scoped ``TransientTracker`` — and handed per-decision facts (the damage context, the
opponent's bench) as explicit call arguments. Composes the pure ``damage.py`` seam; never reads
a Pilot or a Board, so it is testable standalone and injectable wherever combat judgment is
needed (the doctrines' future explicit dependency).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations

from common.deck_odds import draw_hit_probability
from common.strategy.context import KO_SCORE
from common.strategy.damage import compute_active_damage, wr_adjust

# The Harvest Readings (ADR-0071 decision 3) — WHICH survival question a caller is asking. One read
# cannot serve both: per-body worst case is conservative for a THREAT read (it over-counts their
# reach) and inflationary for a RESCUE read (it over-credits saving one body), and those pull
# opposite ways. Caller-passed, never inferred from the board — the same convention as `charged`
# (ADR-0064 Decision 1) and `my_benched` (ADR-0070 §9), with the conservative one as the default.
HARVEST_POSSIBLE = "possible"          # in the harvest under SOME optimal allocation — threat/doom
HARVEST_UNAVOIDABLE = "unavoidable"    # ...under EVERY optimal allocation — rescue/value

# Tactical scalars owned by the oracle (ADR-0052) — used solely by closed-form combat valuation.
_EFFICIENCY = 0.1          # per-Energy tiebreak: among equal-outcome attacks prefer the cheaper one;
                           # far below prize granularity (1) so it never overrides prize value
_BENCH_SNIPE = 0.005       # per-point value of an attack's bench-snipe/spread rider, capped below —
_BENCH_SNIPE_CAP = 0.9     # a sub-prize tiebreak: the equal-outcome KO that ALSO snipes wins,
                           # without ever overriding a prize (ADR-0022 #14)
_ACCEL_TAGS = frozenset({"tutor_energy", "energy_accel"})   # the Function-Tag ROUTING gate of the
                           # Attach Budget: a tag says a card MIGHT supply Energy, an Effect Clause
                           # says how much (ADR-0067) — an untagged card is never even inspected
_RECUR_RELOAD_CAP = 3      # the max Basic Energy a `discard_energy_recur` line reloads from its OWN
                           # discard in one turn — VERIFIED at source (EN_Card_Data.csv): Mega Lucario
                           # ex 678 Aura Jab up to 3 Basic {F}; Archaludon ex 190 Assemble Alloy up to
                           # 2 Basic {M}. Bounds the discard-fuel above the strongest verified reload.


DISCARD_SUPPLY = "discard"     # the shared capacity group every discard-drawing effect competes in


@dataclass(frozen=True)
class AttachUnit:
    """ONE Energy unit that could sit on a body — the atom of the **Attach Budget**.

    ``types``: the EnergyTypes this unit may take. Empty = ANY type (an attached Energy whose card
    doesn't resolve — fail-open, matching :meth:`CombatMath.attack_type_payable`'s ``wild_units``).
    A colourless/special unit carries ``{0}`` and so pays only colourless slots.

    ``groups``: capacity groups this unit draws from, each policed by the Budget's ``caps``. Two
    kinds compose: a per-CARD group whose cap is one-per-colour realises "up to 2 Basic Energy of
    DIFFERENT types" (Crispin), and ``DISCARD_SUPPLY``, whose cap is the visible pile, stops the
    turn's discard-drawing effects from collectively claiming Energy the pile does not hold.

    ``source``: the ZONE this unit is drawn from, ``"deck"`` marking the only uncertain one — the
    hidden zone whose fetch can whiff (ADR-0074, #175). Everything else is certain at decision time
    (an Energy in hand, a discard-sourced attach over the public pile, an Energy already attached)
    and carries ``None``, contributing probability 1.0. Purely descriptive: no affordability check
    reads it, so the boolean Budget is unchanged by its presence.
    """
    types: frozenset = field(default_factory=frozenset)
    groups: tuple = ()
    source: str | None = None


@dataclass(frozen=True)
class Budget:
    """The **Attach Budget** — this turn's full attach capacity toward ONE body (ADR-0067).

    ``options`` are the legal play-sets (the Items always play; each Supporter is an alternative to
    every other; the single manual attach picks one Energy source). Affordability asks whether ANY
    option pays, so a Supporter choice that is smaller but better-TYPED is never lost to a bigger
    one — exact, not a best-by-count guess. Options are not disjoint: the no-Supporter and
    no-manual-attach sets are emitted alongside their supersets, which is harmless because
    payability is monotone in units, so a subset never wins where its superset loses.

    ``caps`` bound how many units of each type a group may realise at once, so a set of units can
    be individually legal yet jointly infeasible — which is exactly the truth about one discard
    pile shared by two accelerators. An option therefore carries units it may not be able to use
    together: read it through :attr:`size` or :func:`_can_pay`, never as a raw ``len``.
    """
    options: tuple = ((),)
    caps: dict = field(default_factory=dict)

    @property
    def size(self) -> int:
        """Units the best option can SIMULTANEOUSLY realise under ``caps`` — the Budget's headline
        magnitude. Counting raw units would over-report: two Wondrous Patches over a single {P} in
        the discard are two units but one attach."""
        return max((self._realisable(option) for option in self.options), default=0)

    def realising_p(self, slots, p_by_type: dict, attached=()) -> float:
        """P(this Budget actually pays ``slots``) — the **Probability Leg** applied to the assignment
        the payment really uses (ADR-0074 decision 3, #175).

        Prices the DEPENDENCY, not the pantry: over every feasible assignment of units to slots
        (``attached`` Energy first, then one Budget option), the probability is the product of
        ``p_by_type`` over the distinct **deck-sourced** types that assignment consumes; every
        certain unit — attached, in hand, from the public discard — contributes 1.0. The maximum
        over assignments is returned, so a KO payable entirely from hand scores exactly 1.0 even on
        a deck depleted of the type some *other* card in the option could have fetched. 0.0 when no
        assignment pays at all.

        Distinct TYPES, not units: two deck units of one colour are priced at P(>=1 copy), not
        P(>=1) squared. The per-card one-per-colour cap (Crispin's "2 Basic Energy of DIFFERENT
        types") makes same-type double demand off a single card impossible; across two fetch cards
        it is an over-claim, stated here rather than silently modelled.
        """
        if not slots:
            return 1.0
        best = 0.0
        for option in self.options:
            p = _pay_best_p(tuple(slots), tuple(attached) + tuple(option), self.caps, p_by_type)
            if p > best:
                best = p
                if best >= 1.0:
                    break                          # certain — no assignment can beat it
        return best

    def _realisable(self, units) -> int:
        n = len(units)
        while n > 0 and not _can_pay((0,) * n, units, self.caps):
            n -= 1
        return n


@dataclass(frozen=True)
class _AttachCtx:
    """Per-decision zone facts the clause interpreter reads (never board objects).

    The two Energy zones are read at DIFFERENT precisions on purpose (ADR-0067): the deck is
    hidden, so it is a *not-provably-empty* type SET; the discard is public, so it is an exact
    per-type COUNT that caps what the turn's discard-drawing effects can jointly take."""
    deck: frozenset = field(default_factory=frozenset)
    discard: dict = field(default_factory=dict)
    benched: bool = False
    more_prizes: bool = False

    def source_types(self, source) -> frozenset:
        """The Energy types a clause's SOURCE zone can still supply; empty for an unmodelled zone
        (fail-CLOSED — an unreadable source yields nothing)."""
        if source == "deck":
            return self.deck
        if source == "discard":
            return frozenset(t for t, n in self.discard.items() if n > 0)
        return frozenset()

    def condition_met(self, condition) -> bool:
        """A clause's play CONDITION; False for an unmodelled one (fail-CLOSED)."""
        return {"more_prizes_remaining_than_opp": self.more_prizes}.get(condition, False)


@dataclass(frozen=True)
class _Contribution:
    """What one playable hand card offers: units it attaches BY ITS EFFECT (independent of the
    turn's manual attach), units it merely puts in HAND (which the manual attach must play), and
    the per-card capacity ``cap`` its own group is policed by ({} when it needs no group)."""
    is_supporter: bool
    effect_units: tuple
    hand_yields: tuple
    group: object = None
    cap: dict = field(default_factory=dict)


def _pay_best_p(slots, units, caps, p_by_type: dict) -> float:
    """Max over feasible assignments of ``units`` to ``slots`` of the product of ``p_by_type`` over
    the distinct DECK-sourced types the assignment consumes (ADR-0074). 0.0 when nothing pays.

    Mirrors :func:`_can_pay`'s matcher exactly — same slot ordering, same per-group capacity
    charging — so an assignment this scores is one ``_can_pay`` would have accepted, and a Budget
    that cannot pay scores 0.0 rather than a probability. Bounded identically (<=4 slots, a handful
    of units, a few colours), with the search pruned the moment a branch cannot beat the incumbent.
    """
    caps = caps or {}
    if len(units) < len(slots):
        return 0.0
    ordered = sorted(slots, key=lambda s: s in (0, None))

    def assign(index, used, spent, taken: frozenset, running: float) -> float:
        if running <= 0.0:
            return 0.0
        if index == len(ordered):
            return running
        want = ordered[index]
        best = 0.0
        for j, unit in enumerate(units):
            if used & (1 << j):
                continue
            if want not in (0, None):
                if unit.types and want not in unit.types:
                    continue
                choices = (want,)
            else:
                choices = tuple(sorted(unit.types)) or (None,)
            for chosen in choices:
                charged, blocked = spent, False
                for group in unit.groups:
                    key = (group, chosen)
                    if charged.get(key, 0) >= caps.get(group, {}).get(chosen, 0):
                        blocked = True
                        break
                    charged = {**charged, key: charged.get(key, 0) + 1}
                if blocked:
                    continue
                nxt, nrun = taken, running
                if unit.source == "deck" and chosen is not None and chosen not in taken:
                    nxt = taken | {chosen}         # each deck TYPE priced once, not per unit
                    nrun = running * float(p_by_type.get(chosen, 0.0))
                got = assign(index + 1, used | (1 << j), charged, nxt, nrun)
                if got > best:
                    best = got
                    if best >= 1.0:
                        return best                # certain — cannot be beaten
        return best

    return assign(0, 0, {}, frozenset(), 1.0)


def _can_pay(slots, units, caps=None) -> bool:
    """Can ``units`` cover an attack's per-slot cost ``slots`` (EnergyType codes; 0 = colourless)?

    Exact. Every slot — colourless ones too — is matched to a DISTINCT unit that takes one concrete
    type from its pool, and each choice is charged against every capacity group the unit belongs to
    (``caps``: group -> {EnergyType: max units}). Charging colourless slots matters: an Energy spent
    paying a colourless slot still leaves the discard pile, so skipping it would let one card in the
    pile fund two slots. A unit inside a group with no pool to name a type from cannot be charged,
    so it is refused — fail-CLOSED, per ADR-0067.

    Bounded and tiny: costs run to 4 slots, budgets to a handful of units, pools to a few colours.
    Typed slots are ordered first so an impossible colour prunes before any colourless branching."""
    caps = caps or {}
    if len(units) < len(slots):
        return False
    ordered = sorted(slots, key=lambda s: s in (0, None))

    def assign(index, used, spent):
        if index == len(ordered):
            return True
        want = ordered[index]
        for j, unit in enumerate(units):
            if used & (1 << j):
                continue
            if want not in (0, None):
                if unit.types and want not in unit.types:
                    continue
                choices = (want,)
            else:
                choices = tuple(sorted(unit.types)) or (None,)
            for chosen in choices:
                charged, blocked = spent, False
                for group in unit.groups:
                    key = (group, chosen)
                    if charged.get(key, 0) >= caps.get(group, {}).get(chosen, 0):
                        blocked = True
                        break
                    charged = {**charged, key: charged.get(key, 0) + 1}
                if not blocked and assign(index + 1, used | (1 << j), charged):
                    return True
        return False

    return assign(0, 0, {})


def _matched_slots(slots, units, caps=None) -> int:
    """How many of ``slots`` ``units`` can SIMULTANEOUSLY pay — the partial-credit reading of
    :func:`_can_pay`, and the arithmetic behind typed slot-fraction build progress (ADR-0069 §3).

    Defined AS a search over sub-costs of :func:`_can_pay` rather than as a second assignment
    routine: "fits" (build) and "reaches" (:meth:`CombatMath.reachable_attach`) must be the same
    matcher, so a partial match can never disagree with the payability it is a fraction of. Bounded
    and tiny — costs run to a handful of slots, so the ``2**len(slots)`` subset walk is smaller than
    the assignment inside it.
    """
    n = len(slots)
    if n == 0 or not units:
        return 0
    for k in range(min(n, len(units)), 0, -1):
        for subset in combinations(range(n), k):
            if _can_pay(tuple(slots[i] for i in subset), units, caps):
                return k
    return 0


class CombatMath:
    """The oracle instance the Pilot builds once and delegates to.

    Args:
        stats: the Stat Provider (``get``/``attack``/forward queries), or None (stat-blind —
            every read fails open to 0/None exactly like a stat-blind Pilot).
        functions: ``CardFunctions`` (defender-side prevention tags), or None.
        transients: the match-scoped ``TransientTracker`` (live next-turn grants keyed by body
            serial, ADR-0033), or None — no live shields/locks are then modeled.
        effects: ``CardEffects`` (ADR-0032 Effect Clauses), or None — the Attach Budget then reads
            no yields at all and is empty (fail-CLOSED, ADR-0067).
    """

    def __init__(self, stats, functions, transients=None, effects=None):
        self.stats = stats
        self.functions = functions
        self._transients = transients
        self.effects = effects

    # --- record access (the Stat Provider seam, ADR-0056) ------------------------------
    def attack_stat(self, attack_id):
        """The attack's ``AttackStat`` off the provider; None unknown / stat-blind."""
        if self.stats is None:
            return None
        return getattr(self.stats, "attack", lambda _aid: None)(attack_id)

    def attack_cost(self, attack_id, default=99):
        """The attack's Energy count; ``default`` when no record resolves (99 = fail-closed)."""
        st = self.attack_stat(attack_id)
        return st.cost if st is not None else default

    def attack_damage(self, attack_id) -> int:
        """The attack's printed damage; 0 for an unknown attack."""
        st = self.attack_stat(attack_id)
        return st.damage if st is not None else 0

    def _card_stat(self, card_id):
        return self.stats.get(card_id) if (self.stats and card_id is not None) else None

    def _grant(self, poke: dict | None) -> dict | None:
        """The live transient grant on a body (serial-gated), or None."""
        if self._transients is None:
            return None
        return self._transients.grant_for_serial((poke or {}).get("serial"))

    # --- the damage core ----------------------------------------------------------------
    def predicted_damage(self, attacker_id: int | None, attack_id, defender: dict | None, *,
                         bound: str = "exact", context: dict | None = None) -> float:
        """The damage oracle (ADR-0032 E1): damage ``attack_id`` deals to the defending Active —
        the ONE closed-form path every Tier-0 damage estimate routes through. Resolves ids to
        stats/tags, then delegates to the pure ``compute_active_damage`` (the unit the engine
        audit diffs). Honors the attack's ignore flags: Nebula Beam lands 210 through Crustle's
        ex-prevention; Jetting Blow is zeroed (its bench rider is a separate path). ``bound``
        picks a conditional attack's floor/ceiling/printed — Lethal reads "min", Incoming "max"."""
        d_id = (defender or {}).get("id")
        return compute_active_damage(
            self.attack_stat(attack_id),
            self._card_stat(attacker_id),
            self._card_stat(d_id),
            frozenset(self.functions.tags(d_id)) if (self.functions and d_id is not None)
            else frozenset(),
            bound=bound, context=context,
            defender_transient=self._grant(defender))

    def predicted_max_damage(self, attacker_stat, defender: dict | None, *,
                             exclude_attack=None, context: dict | None = None) -> float:
        """The worst damage ``attacker_stat``'s attacks deal to ``defender`` — max over the
        per-attack oracle when EVERY attack's record resolves (a partially-known table never
        SHRINKS a worst case), else the card-level ``maxDamage`` x W/R (``wr_adjust`` — the one
        card-level rule). ``context`` prices the attacker's scalers (the opponent-context dict
        the Pilot stashes per decision — hand size, bench, attached Energy, open discard).

        NOTE: does NOT filter by the opponent's Energy affordability — the Incoming estimate
        assumes the opponent can power its biggest attack (conservative over-estimate; see
        docs/todo/incoming-affordability.md before changing this)."""
        if not attacker_stat:
            return 0
        aids = tuple(a for a in (attacker_stat.attacks or ()) if a != exclude_attack)
        if aids and all(self.attack_stat(a) is not None for a in aids):
            # bound="max": Incoming is the WORST case — a coin/conditional attack threatens its
            # ceiling ("If heads, +20" counts the 20), so survival math never under-plans
            return max(self.predicted_damage(attacker_stat.cardId, a, defender, bound="max",
                                             context=context)
                       for a in aids)
        d_stat = self._card_stat((defender or {}).get("id"))
        return wr_adjust(attacker_stat, d_stat, attacker_stat.maxDamage or 0)

    # --- card-tier combat facts -----------------------------------------------------------
    def prize_value(self, poke: dict | None) -> int:
        """Prizes a knockout of this body yields — Mega ex 3, ex 2, else 1 (the record's own
        question, ADR-0056); 1 for an unknown body."""
        stat = self._card_stat((poke or {}).get("id"))
        return stat.prize_value if stat else 1

    def is_tera(self, card_id) -> bool:
        """A Tera Pokémon — takes NO damage from attacks while BENCHED (engine ``CardData.tera``),
        so no bench-snipe/spread math may ever credit damage against it there. Fail-open (False)
        without stats: a phantom snipe-prize vs Tera could lock a false Lethal."""
        st = self._card_stat(card_id)
        return bool(getattr(st, "tera", False))

    def rider_snipe(self, attack_id) -> int:
        """The attack's unconditional bench-snipe rider damage (0 unknown)."""
        st = self.attack_stat(attack_id)
        return st.benchSnipe if st else 0

    def rider_spread(self, attack_id) -> int:
        """The attack's distributable opp-bench spread total (0 unknown)."""
        st = self.attack_stat(attack_id)
        return st.benchSpread if st else 0

    def rider_recoil(self, attack_id) -> int:
        """The attack's unconditional self-damage (0 unknown).

        UNCONSUMED: zero callers and zero tests. Its siblings `rider_snipe`/`rider_spread` are both
        live. Recoil IS priced — but through `_recoil_flips_doom`, which reads `AttackStat.recoil`
        directly, so this accessor never got wired. Delete on the next combat pass unless a caller
        appears."""
        st = self.attack_stat(attack_id)
        return st.recoil if st else 0

    # --- bench-rider prize math (opp_bench = ((cardId, hp), …), the Board snapshot) -------
    def bench_ko_indices(self, opp_bench, reach: int) -> frozenset:
        """WHICH benched Pokémon ``reach`` damage Knocks Out — indices into ``opp_bench``.

        The bench Knock Out rule itself, stated ONCE: bench HP within the damage, bench damage
        ignores Weakness/Resistance (ADR-0022), Tera bodies take none while benched.
        `snipe_ko_prizes` is derived from this rather than restating it, so the two can never drift
        (the `_build_standing` / `_affords` one-function-owns-the-fact lesson).

        ``reach`` is any bench-reaching damage a single body could take — a single-target snipe
        rider, or a distributable spread total pointed entirely at one body ("in any way you like",
        so all of it may land on one). The rule does not care which produced it, and naming it
        ``reach`` rather than ``rider`` keeps that honest.

        Added by #199 (ADR-0080) for the Deny Relevance redundancy gate, which needs the IDENTITY of
        the bodies that die — the doctrine's *"or maybe its a benched pokemon that we can snipe and
        KO, same thing, no hammer on that specific pokemon"* — where the aggregate prize read alone
        cannot say which body it meant."""
        if reach <= 0:
            return frozenset()
        return frozenset(i for i, (cid, hp) in enumerate(opp_bench)
                         if hp and hp <= reach and not self.is_tera(cid))

    def snipe_ko_prizes(self, opp_bench, rider: int) -> int:
        """Max prize among the opponent's benched Pokémon a bench-snipe ``rider`` KNOCKS OUT —
        bench HP <= rider (bench snipes ignore Weakness/Resistance, ADR-0022); Tera bodies take
        none. 0 when the rider finishes nothing. DERIVED from `bench_ko_indices` (#199)."""
        bench = list(opp_bench)
        return max((self.prize_value({"id": bench[i][0]})
                    for i in self.bench_ko_indices(bench, rider)), default=0)

    @staticmethod
    def best_ko_subset(items, budget: int) -> frozenset:
        """Indices of the max-total-prize subset of ``items`` (``[(hp, prize), …]``) whose total
        HP fits in ``budget`` — a small knapsack (bench <= 5, so <= 32 subsets). Ties break to the
        cheaper set (fewest counters). Empty frozenset when nothing is affordable."""
        best_prize, best_cost, best_mask = 0, 0, 0
        for mask in range(1 << len(items)):          # bench <= 5 -> <= 32 subsets
            cost = prize = 0
            for i, (hp, pv) in enumerate(items):
                if mask & (1 << i):
                    cost, prize = cost + hp, prize + pv
            if cost <= budget and (prize > best_prize
                                   or (prize == best_prize and prize and cost < best_cost)):
                best_prize, best_cost, best_mask = prize, cost, mask
        return frozenset(i for i in range(len(items)) if best_mask & (1 << i))

    @staticmethod
    def _harvest_residual(needs: list, snipes: list) -> int:
        """Spread still owed to fell every body in ``needs`` after spending the INDIVISIBLE
        ``snipes`` optimally — the allocation core of :meth:`best_harvest` (ADR-0071 decision 2).

        Each snipe unit lands entirely on ONE body (single-target text), so a unit applied to a body
        saves ``min(unit, that body's remaining need)``. Maximising the total saved is a separable
        concave problem under a unit budget, so assigning the LARGEST unit to the LARGEST remaining
        need is exact for equal-size units — the shipped case, since a turn's payload is re-read off
        the same attacker pool each turn. Unequal sizes fall back to the same greedy, which is a
        bound rather than a proof; it can only OVER-state the residual, i.e. under-state their reach
        on the rescue reading and never manufacture a phantom knockout."""
        rest = list(needs)
        for unit in sorted(snipes, reverse=True):
            if unit <= 0 or not rest:
                continue
            i = max(range(len(rest)), key=lambda j: rest[j])
            rest[i] = max(0, rest[i] - unit)
        return sum(rest)

    @staticmethod
    def _harvest_optima(items, snipes, spread: int):
        """``(objective key, [optimal subsets])`` for ONE payload — the solver core.

        Returns EVERY subset tying at the best objective, because the two Harvest Readings are the
        union and the intersection of exactly that set."""
        best_key, optimal = None, []
        for mask in range(1 << len(items)):          # bench <= 5 -> <= 32 subsets
            chosen = [i for i in range(len(items)) if mask & (1 << i)]
            residual = CombatMath._harvest_residual([items[i][0] for i in chosen], snipes)
            if residual > spread:
                continue                             # the shared budget does not stretch this far
            key = (sum(items[i][1] for i in chosen),         # prize — their win condition
                   sum(1 for i in chosen if items[i][2]),    # ...then my role-carrying bodies
                   -residual)                                # ...then the cheapest allocation
            if best_key is None or key > best_key:
                best_key, optimal = key, [frozenset(chosen)]
            elif key == best_key:
                optimal.append(frozenset(chosen))
        return best_key, optimal

    @staticmethod
    def _read_optima(optimal, reading: str) -> frozenset:
        """Collapse the tied-optimal subsets to one answer under ``reading``."""
        if not optimal:
            return frozenset()
        if reading == HARVEST_UNAVOIDABLE:
            return frozenset.intersection(*optimal)
        return frozenset().union(*optimal)

    @staticmethod
    def best_harvest(items, snipes, spread: int, *, reading: str = HARVEST_POSSIBLE) -> frozenset:
        """Indices of MY benched bodies the opponent takes with a SHARED rider budget — the **Bench
        Harvest** (ADR-0071). ``items`` = ``((hp, prize, is_key), …)`` of the bodies riders can
        reach; ``snipes`` = the indivisible single-target units (one per turn read); ``spread`` =
        the total divisible counter budget ("in any way you like").

        Their objective is max total PRIZE, then — strictly SUB-prize, never overriding a real prize
        difference — the count of my role-carrying bodies, then the cheapest allocation (decision 8:
        the `opponent_target_value` discipline applied to their model of us).

        ``reading`` selects WHICH question is being asked (decision 3), because one answer cannot
        serve both consumers:
        - ``HARVEST_POSSIBLE`` — in the harvest under SOME optimal allocation. The conservative
          default: a threat/doom read must not call a body safe just because they could kill a
          different one.
        - ``HARVEST_UNAVOIDABLE`` — in the harvest under EVERY optimal allocation. The rescue/value
          read: a knockout they can simply redirect is worth nothing to deny, so rescuing that body
          credits zero.

        Generalises :meth:`best_ko_subset` rather than calling it: once the budget accumulates over
        turns each candidate subset has its own post-snipe residual, so the knapsack's fixed-HP
        items no longer compose (ADR-0071 amendment A)."""
        return CombatMath._read_optima(CombatMath._harvest_optima(items, snipes, spread)[1], reading)

    def _harvest_items(self, bench, key_ids):
        """``(items, index map)`` for :meth:`best_harvest` — my benched bodies riders can reach.

        Tera bodies take NO attack damage while Benched (rules.md §11), so they are dropped rather
        than scored, and drop out of the index map with them."""
        items, idx = [], []
        for i, b in enumerate(bench or ()):
            hp = (b or {}).get("hp", 0)
            if not hp or self.is_tera((b or {}).get("id")):
                continue
            items.append((int(hp), self.prize_value(b), (b or {}).get("id") in key_ids))
            idx.append(i)
        return items, idx

    def bench_harvest(self, my_bench, payloads, *, reading: str = HARVEST_POSSIBLE,
                      key_ids=frozenset()) -> frozenset:
        """The Bench Harvest over MY benched body dicts — indices into ``my_bench``.

        ``payloads`` are the CANDIDATE attacks, each ``(snipes, spread)``: attacking ends their turn,
        so they commit to one attack, and WHICH one is part of the choice being solved — not a
        pre-filter. Selecting a payload by a proxy metric (largest total rider) is unsound: a 70
        single-target snipe beats a 60 spread on that sum, yet the spread takes three 20 HP bodies
        where the snipe takes one. Under-reading their reach that way is the phantom-safety fail
        direction ADR-0070 §9 refused, so every candidate is scored and the opponent's own objective
        picks (ADR-0071 amendment F).

        ``key_ids`` is the deck-DECLARED role-carrying set, passed in because `CombatMath` is
        deck-agnostic."""
        items, idx = self._harvest_items(my_bench, key_ids)
        best_key, optimal = None, []
        for snipes, spread in payloads:
            key, opts = self._harvest_optima(items, snipes, spread)
            if key is None:
                continue
            if best_key is None or key > best_key:
                best_key, optimal = key, list(opts)
            elif key == best_key:
                optimal.extend(opts)                 # tied attacks widen the allocation choice
        return frozenset(idx[i] for i in self._read_optima(optimal, reading))

    def spread_ko_prizes(self, opp_bench, spread: int) -> int:
        """Max total prizes from distributing a ``spread`` (Phantom Dive's ``benchSpread``) across
        the opponent's Bench to KNOCK OUT benched Pokémon — the ``best_ko_subset`` knapsack
        (spread counters ignore W/R; Tera bodies take none). 0 when nothing is finishable."""
        if spread <= 0:
            return 0
        items = [(hp, self.prize_value({"id": cid})) for cid, hp in opp_bench
                 if hp and hp <= spread and not self.is_tera(cid)]
        return sum(items[i][1] for i in self.best_ko_subset(items, spread))

    # --- typed affordability ---------------------------------------------------------------
    def attached_type_counts(self, target: dict) -> dict:
        """{EnergyType: count} of the SPECIFIC (typed Basic) Energy attached to ``target`` — a
        special/colourless Energy reports type 0 and pays a colourless slot only, so it isn't
        counted. Fail-open: an unresolvable id is skipped (undercount only relaxes a suppression)."""
        counts: Counter = Counter()
        for eid in (target.get("energies") or []):
            est = self._card_stat(eid)
            t = getattr(est, "energyType", None) if est else None
            if t not in (None, 0):
                counts[t] += 1
        return counts

    def attack_type_payable(self, aid, target: dict | None, *, extra_type=None,
                            extra_units: int = 0, wild_units: int = 0) -> bool:
        """Sound-or-silent TYPE affordability on top of the count check: every SPECIFIC-type slot
        of ``aid``'s cost (``AttackStat.energyTypes``) must be covered by the target's attached
        typed Energy, plus ``extra_units`` of ``extra_type`` when that is a specific type — a
        colourless/special extra (type 0/None, e.g. Ignition's {C}{C}{C}) pays colourless slots
        only — plus ``wild_units`` hypothetical attaches of UNKNOWN type, each able to cover any
        one specific slot (fail-open: the hand/deck might supply the needed type). An attached
        Energy whose type can't be resolved counts as wild too. True whenever the attack record
        doesn't resolve (the count check stays the sole authority — never a false suppression)."""
        ast = self.attack_stat(aid)
        types = getattr(ast, "energyTypes", ()) if ast else ()
        need = Counter(t for t in types if t not in (0, None))
        if not need or target is None:
            return True
        attached = self.attached_type_counts(target)
        if extra_type not in (None, 0) and extra_units > 0:
            attached = attached.copy()
            attached[extra_type] += extra_units
        unresolved = sum(
            1 for eid in (target.get("energies") or [])
            if getattr(self._card_stat(eid), "energyType", None) is None)
        missing = sum(max(0, n - attached.get(t, 0)) for t, n in need.items())
        return missing <= wild_units + unresolved

    # --- reachability (can X KO / hurt Y) ---------------------------------------------------
    def can_ko_cheapest(self, my_stat, defender: dict | None) -> bool:
        """The attacker's CHEAPEST attack would Knock Out ``defender`` this turn — per-attack
        oracle over the cheapest-cost attacks (prevention is attack-scoped: an ignore-flag attack
        still KOs through a wall). Fail-closed on missing stats/HP/records — the card-level
        ``minCostDamage`` fallback is RETIRED (ADR-0052): no record, no claim."""
        hp = (defender or {}).get("hp", 0)
        if not (my_stat and hp):
            return False
        cheap = [aid for aid in (my_stat.attacks or ())
                 if self.attack_cost(aid, None) == my_stat.minAttackCost
                 and self.attack_stat(aid) is not None]
        return any(self.predicted_damage(my_stat.cardId, aid, defender) >= hp for aid in cheap)

    def can_ko_affordable(self, attacker: dict | None, defender: dict | None) -> bool:
        """The attacker's best attack it can currently AFFORD (its attached Energy) KOs
        ``defender`` this turn — scans every affordable attack, so a big non-cheapest KO is seen
        (Mega Starmie at CCC KOs with Nebula Beam though Jetting Blow can't). Fail-closed."""
        if not (attacker and defender):
            return False
        stat = self._card_stat(attacker.get("id"))
        hp = defender.get("hp", 0)
        if not (stat and hp):
            return False
        energy = len(attacker.get("energies") or [])
        return any(self.predicted_damage(attacker.get("id"), aid, defender) >= hp
                   for aid in (stat.attacks or ()) if self.attack_cost(aid) <= energy)

    def can_damage(self, attacker: dict | None, defender: dict | None) -> bool:
        """The attacker, with its CURRENT Energy, has an affordable attack dealing >0 damage to
        ``defender`` — 'can they hurt me with what they hold NOW'. A conditional attack that
        computes to 0 (Riptide off an empty discard) or an all-unaffordable set is NO threat.
        Fail-closed."""
        if not (attacker and defender):
            return False
        stat = self._card_stat(attacker.get("id"))
        if not (stat and defender.get("hp")):
            return False
        energy = len(attacker.get("energies") or [])
        return any(self.predicted_damage(attacker.get("id"), aid, defender) > 0
                   for aid in (stat.attacks or ()) if self.attack_cost(aid) <= energy)

    def maxed_kos(self, attacker: dict | None, defender: dict | None) -> bool:
        """The attacker's BIGGEST-damage attack (fully powered, IGNORING current Energy) would KO
        ``defender`` — 'could I KO if I loaded up?'. When False the defender is un-KO-able this
        turn even maxed, so a one-shot burst buys no KO. Fail-closed."""
        if not (attacker and defender):
            return False
        stat = self._card_stat(attacker.get("id"))
        hp = defender.get("hp", 0)
        if not (stat and hp and stat.attacks):
            return False
        best_aid = max(stat.attacks, key=self.attack_damage)    # biggest printed attack
        return self.predicted_damage(attacker.get("id"), best_aid, defender) >= hp

    # --- Incoming (worst-case, opponent-static — the survival reads) ------------------------
    def forward_card_ids(self, card_id) -> frozenset:
        """Card ids the body's evolution line evolves INTO (the provider primitive; empty when
        no provider / dead-end / unknown id)."""
        fci = getattr(self.stats, "forward_card_ids", None)
        return fci(card_id) if (fci is not None and card_id is not None) else frozenset()

    def incoming_active_damage(self, ma: dict | None, oa: dict | None, *,
                               context: dict | None = None) -> int:
        """Closed-form worst damage the opponent's Active deals my Active next turn — its biggest
        attack (per-attack ceiling), honoring a live transient grant on THEIR Active: a self-lock
        means no attack at all, a same-attack lock excludes that one, a self-bonus raises the hit.
        0 when unknown. WORST-CASE by design — affordability deliberately NOT charged (the hidden
        burst-Energy lesson; docs/todo/incoming-affordability.md)."""
        if not (self.stats and ma and oa):
            return 0
        opp_stat = self._card_stat(oa.get("id"))
        if not opp_stat:
            return 0
        grant = self._grant(oa) or {}
        if grant.get("self_lock"):
            return 0
        dmg = self.predicted_max_damage(opp_stat, ma, exclude_attack=grant.get("same_lock"),
                                        context=context)
        return int(dmg + grant.get("self_bonus", 0)) if dmg else int(dmg)

    def forward_incoming_damage(self, ma: dict | None, oa: dict | None, opp: dict | None, *,
                                context: dict | None = None) -> int:
        """Worst-case incoming if the opponent EVOLVES their Active's line next turn (play AS IF
        they evolve): for each forward form affordable on their Energy + one attach, a
        ``hand_size_attacker`` contributes its hand-scaled counters (W/R-free, hand one short —
        a card is spent evolving), ANY form its printed damage W/R-adjusted vs my Active. 0 when
        unknown / no ``opp`` dict (the forward read needs their hand size)."""
        if not (self.stats and self.functions and ma and oa and opp):
            return 0
        if not self._card_stat(ma.get("id")):
            return 0
        hand = max(0, (opp.get("handCount", 0) or 0) - 1)   # ≥1 card spent to play the evolution
        oa_energy = len(oa.get("energies") or [])
        best = 0
        for fid in self.forward_card_ids(oa.get("id")):
            fstat = self._card_stat(fid)
            if not fstat:
                continue
            if (fstat.minAttackCost or 0) > oa_energy + 1:   # unaffordable even with next turn's attach
                continue
            if "hand_size_attacker" in self.functions.tags(fid):
                best = max(best, (fstat.handSizeDamage or 0) * hand)   # counters ignore W/R
            best = max(best, int(self.predicted_max_damage(fstat, ma, context=context)))
        return best

    def active_doomed(self, ma: dict | None, oa: dict | None, opp: dict | None = None, *,
                      context: dict | None = None) -> bool:
        """The opponent can Knock Out my Active next turn — its biggest CURRENT attack OR the
        attack its Active reaches by EVOLVING >= my Active's HP. WORST-CASE (the ceiling): Energy
        affordability is deliberately not charged — a hidden Ignition-class burst reaches a costly
        nuke in one turn (the planner_6858 lesson). A survival read must never under-prepare."""
        my_hp = (ma or {}).get("hp", 0)
        if not my_hp:
            return False
        threat = max(self.incoming_active_damage(ma, oa, context=context),
                     self.forward_incoming_damage(ma, oa, opp, context=context))
        return threat >= my_hp

    def doomed_incoming(self, ma: dict | None, oa: dict | None, *, charged: dict | None = None,
                        context: dict | None = None) -> int:
        """The Threat-Clock CURVE re-expression of the survival doom read (S1b of
        docs/plans/opponent-value-equation-unification.md): worst incoming to ``ma`` from the
        opponent's Active ``oa`` via :meth:`incoming` at t=1. Returns the DAMAGE — the caller
        compares it to my HP (``>= my_hp`` ⇒ doomed).

        NOT byte-identical to :meth:`active_doomed`, by design — ADR-0064 §2 keeps that one
        unconditionally worst-case. The curve (a) gates the current form on affordability
        (``can_pay_cheapest`` under one attach) and (b) omits the ``hand_size_attacker`` forward
        counter. Those two are exactly the divergences the doom SHADOW measures before any survival
        swap. ``charged`` selects the policy — ``None`` = ceiling, the survival read's worst-case."""
        if not oa:
            return 0
        return int(self.incoming(ma, [oa], 1, charged=charged, context=context))

    # --- reachable Attach: MY next DEVELOPMENT step (issue #137 / ADR-0067) -----------------
    def attach_budget(self, target: dict | None, hand_ids, *, energy_attached: bool = False,
                      supporter_played: bool = False, deck_energy_types=(),
                      hand_energy_types=(), discard_energy_counts=None,
                      target_benched: bool = False, more_prizes_than_opp: bool = False) -> Budget:
        """This turn's FULL Energy-attach capacity toward ``target`` — the **Attach Budget**.

        Enumerates the manual attach (iff ``energy_attached`` is False) plus the attach EFFECT of
        every PLAYABLE accel/tutor card in ``hand_ids``, each at its **Effect-Clause-quantified**
        yield — never a flat ``+1`` (that under-read IS the f70 bug: Crispin attaches one Basic by
        its effect AND hands a second of a different type the manual attach then plays, reaching a
        2-cost typed attack from zero).

        Two epistemics, split by what is uncertain (ADR-0067):
        - **Yield fails CLOSED.** Function Tags only ROUTE (``_ACCEL_TAGS``); the amounts, source
          zone, target restriction and play conditions come from Effect Clauses. An unmodelled
          clause kind, target class, source zone or condition contributes **zero** — the oracle
          never guesses a yield, so a PROVABLE famine still fires its stall.
        - **Deck presence fails OPEN.** ``deck_energy_types`` is the *not-provably-empty* typed
          set (the sound emptiness oracle, per type), not a provably-present one: with a thin
          3-copy Energy suite nothing is provable before a search anchors the prizes, and a strict
          gate would re-fire the very famine this exists to kill. The honest hypergeometric lives
          in :meth:`readiness_p` alone.

        Quotas are structural, never a branch thicket: Items all play; each Supporter is a separate
        alternative play-set (one Supporter per turn — a tutor Supporter and the manual attach CAN
        co-occur, two Supporters cannot); and the single manual attach plays exactly ONE Energy
        source (an Energy already in hand, or one a played card fetched there).

        A Pokémon-borne accel is deliberately never counted: its acceleration is an ATTACK
        (Cinderace's Turbo Flare), and attacking ends the turn, so it can never fund another
        attack this turn — the self-side mirror of ADR-0064's attack-based-accel exclusion.

        Zone facts arrive as ARGUMENTS (no Board, no Pilot). ``deck_energy_types`` /
        ``hand_energy_types`` are EnergyType codes; ``discard_energy_counts`` is a
        ``{EnergyType: count}`` map — the discard is PUBLIC, so its yields are capped at the
        supply really sitting there (two Wondrous Patches over one {P} is one attach), while the
        hidden deck stays a type set. ``target_benched`` places the body for a bench-restricted
        clause, and ``more_prizes_than_opp`` answers Rosa's Encouragement's prize gate.
        """
        ctx = _AttachCtx(deck=frozenset(deck_energy_types or ()),
                         discard=dict(discard_energy_counts or {}),
                         benched=bool(target_benched), more_prizes=bool(more_prizes_than_opp))
        target_stat = self._card_stat((target or {}).get("id"))
        items, supporters = [], []
        for group, cid in enumerate(hand_ids or ()):
            contrib = self._attach_contribution(cid, group, target_stat, ctx)
            if contrib is not None:
                (supporters if contrib.is_supporter else items).append(contrib)
        playsets = [items] + ([] if supporter_played else [items + [s] for s in supporters])

        caps = {DISCARD_SUPPLY: dict(ctx.discard)}
        caps.update({c.group: c.cap for c in items + supporters if c.group is not None})

        special = self._special_energy_groups(hand_ids, target_stat)
        options = set()
        for playset in playsets:
            # The manual attach plays exactly ONE source, but a source is a GROUP: a Basic Energy is
            # one unit, a Special Energy is however many its provision prints (#142).
            groups = [(AttachUnit(frozenset(hand_energy_types)),)] if hand_energy_types else []
            groups += [(u,) for c in playset for u in c.hand_yields]
            groups += list(special)
            manual = [()] if energy_attached else [()] + groups
            effect = tuple(u for c in playset for u in c.effect_units)
            options.update(effect + m for m in manual)
        return Budget(options=tuple(sorted(options, key=lambda o: (-len(o), str(o)))), caps=caps)

    def _special_energy_groups(self, hand_ids, target_stat) -> tuple:
        """Manual-attach source groups for the SPECIAL Energy in hand — one group per card, sized by
        its `provides:N` Function Tag and coloured by its ``energyType`` (#142).

        A Special Energy is not one unit of its own colour, so the hand leg's typed-Basic count
        cannot see it: Ignition Energy provides {C}{C}{C} on an Evolution, which is a Mega Starmie ex
        armed from ZERO by a single attach. Left unmodelled it is a FALSE FAMINE on a shipped deck —
        the same bug class as the retired `+1`, one zone over.

        Colour follows :meth:`_attached_units` exactly, so a hypothetical attach and the real board
        it models agree: a colourless provision carries ``{0}`` and pays colourless slots only.
        Fail-CLOSED on an untagged card, an unknown stat or an unknown target."""
        if target_stat is None or not self.functions:
            return ()
        evolution = getattr(target_stat, "evolvesFrom", None) is not None
        groups = []
        for cid in (hand_ids or ()):
            stat = self._card_stat(cid)
            if stat is None or not stat.is_special_energy:
                continue
            count = self.functions.energy_provision(cid, evolution=evolution)
            if count <= 0:
                continue
            etype = getattr(stat, "energyType", None)
            pool = frozenset() if etype is None else frozenset({etype})
            groups.append(tuple(AttachUnit(pool) for _ in range(count)))
        return tuple(groups)

    def _attach_contribution(self, card_id, group: int, target_stat, ctx: _AttachCtx):
        """What one hand card offers the Budget, or None if it offers nothing (fail-CLOSED)."""
        tags = frozenset(self.functions.tags(card_id)) if self.functions else frozenset()
        stat = self._card_stat(card_id)
        if not (tags & _ACCEL_TAGS) or stat is None or not (stat.is_item or stat.is_supporter):
            return None                        # untagged, unknown, or a Pokémon (attack-based accel)
        clauses = self.effects.clauses(card_id) if self.effects else ()
        gid = group if any(cl.get("distinct_types") for cl in clauses) else None
        effect = [u for cl in clauses for u in self._accel_units(cl, target_stat, ctx, gid)]
        yields = [u for cl in clauses for u in self._hand_yield_units(cl, target_stat, ctx, gid)]
        # "of DIFFERENT types" bounds the card two ways. Its per-COLOUR half is the group cap below
        # (two units can never share a colour). Its COUNT half must be settled here, because when a
        # card yields fewer units than it prints, the card text does not say WHICH half is lost.
        #
        # Crispin over a deck down to one not-provably-empty colour finds ONE Energy — and "put 1 of
        # them into your hand. Attach the other" leaves it open whether that lone card is the
        # put-in-hand half or the attach half. Ruled FAIL-CLOSED (ADR-0067, grilled 2026-07-24): the
        # HAND half survives, so the unit needs the turn's manual attach and is worth nothing once
        # that is spent. The braver reading would have the card attach by itself with the attach
        # already gone — a claim no source settles, in the direction ADR-0067 forbids guessing in.
        while (gid is not None and effect
               and len(effect) + len(yields) > len(self._palette(effect + yields))):
            effect.pop()
        if not (effect or yields):
            return None
        cap = {t: 1 for t in self._palette(effect + yields)} if gid is not None else {}
        return _Contribution(stat.is_supporter, tuple(effect), tuple(yields), gid, cap)

    @staticmethod
    def _palette(units) -> frozenset:
        """Every colour the card's units could take — the width of its distinct-types capacity."""
        return frozenset(t for u in units for t in u.types)

    @staticmethod
    def _unit_groups(source, group) -> tuple:
        """The capacity groups a unit answers to: its card's distinct-types group (when it has one)
        and, for anything drawn from the public discard, the shared pile."""
        return tuple(g for g in (group, DISCARD_SUPPLY if source == "discard" else None)
                     if g is not None)

    def _accel_units(self, clause: dict, target_stat, ctx: _AttachCtx, group) -> tuple:
        """Units an ``accel`` clause attaches BY ITS EFFECT — independent of the manual attach."""
        if clause.get("kind") != "accel" or not self._accel_target_ok(clause, target_stat, ctx):
            return ()
        condition = clause.get("condition")
        if condition is not None and not ctx.condition_met(condition):
            return ()
        source = clause.get("source")
        pool = self._clause_pool(ctx.source_types(source), clause.get("energy_type"))
        groups = self._unit_groups(source, group)
        return tuple(AttachUnit(pool, groups, source)
                     for _ in range(int(clause.get("amount") or 0))) if pool else ()

    def _hand_yield_units(self, clause: dict, target_stat, ctx: _AttachCtx, group: int) -> tuple:
        """Units a clause puts in HAND rather than attaching — playable only via the turn's ONE
        manual attach, so they compete for it instead of summing.

        Two shapes: an ``accel`` clause's ``to_hand`` rider (Crispin's "put 1 of them into your
        hand" half — carried HERE and not as a ``fetch`` clause, because a ``fetch`` row would
        re-arm the gamble energy-closure that `effect_overrides.json` deliberately excludes it
        from), and a plain deck ``fetch`` of an Energy (Fighting Gong's {F}-locked search, Hilda).
        A ``to_hand`` rider rides its clause's own target/condition gates: an accel the body can't
        legally receive is not played for its hand half either."""
        kind = clause.get("kind")
        source = clause.get("source")
        if kind == "accel":
            if not self._accel_target_ok(clause, target_stat, ctx):
                return ()
            condition = clause.get("condition")
            if condition is not None and not ctx.condition_met(condition):
                return ()
            pool = self._clause_pool(ctx.source_types(source), clause.get("energy_type"))
            amount = int(clause.get("to_hand") or 0)
        elif kind == "fetch" and clause.get("zone") == "deck":
            if clause.get("target") not in ("basic_energy", "energy"):
                return ()                      # a Pokémon/Trainer fetch is no Energy at all
            pool, source = self._clause_pool(ctx.deck, clause.get("energy_type")), "deck"
            amount = 1
        else:
            return ()
        return tuple(AttachUnit(pool, self._unit_groups(source, group), source)
                     for _ in range(amount)) if pool else ()

    @staticmethod
    def _clause_pool(available: frozenset, energy_type) -> frozenset:
        """The colours a clause can actually deliver: its source zone's, narrowed by a type lock."""
        return available if energy_type is None else available & {energy_type}

    @staticmethod
    def _accel_target_ok(clause: dict, target_stat, ctx: _AttachCtx) -> bool:
        """May this ``accel`` clause legally attach to the body being budgeted? Fail-CLOSED on an
        unknown body or an unmodelled target class — a restricted accel never funds a body it
        cannot reach (Wondrous Patch is BENCHED-{P}-only; Rosa's Encouragement is Stage-2-only)."""
        if target_stat is None:
            return False
        target_type = clause.get("target_type")
        if target_type is not None and getattr(target_stat, "energyType", None) != target_type:
            return False
        target = clause.get("target")
        if target in (None, "any_pokemon"):
            return True
        if target == "stage2":
            return bool(getattr(target_stat, "stage2", False))
        if target == "benched":
            return ctx.benched
        return False

    def _attached_units(self, body: dict | None) -> tuple:
        """The Energy already ON the body, as Budget units — a typed Basic keeps its colour, a
        colourless/special one pays colourless slots only, an unresolvable card is wild (fail-open,
        exactly as :meth:`attack_type_payable` treats it)."""
        units = []
        for eid in ((body or {}).get("energies") or ()):
            etype = getattr(self._card_stat(eid), "energyType", None)
            units.append(AttachUnit(frozenset() if etype is None else frozenset({etype})))
        return tuple(units)

    def _attack_slots(self, attack_id) -> tuple:
        """An attack's per-slot cost as EnergyType codes; () when no record resolves OR the cost is
        0 (the pinned unknown/0-cost quirk) — the caller then makes no claim."""
        ast = self.attack_stat(attack_id)
        if ast is None:
            return ()
        return tuple(ast.energyTypes) or (0,) * int(ast.cost or 0)

    def reachable_attach(self, my_body: dict | None, attack_id=None, *, budget: Budget) -> bool:
        """Can ``my_body`` PAY (and legally use) an attack THIS turn under ``budget``? — the
        self-side mirror of :meth:`reachable_incoming` (ADR-0064), the **Reachable Attach** oracle.

        ``attack_id`` None asks the FAMINE question: is ANY attack reachable? (Scanning all attacks
        rather than the cheapest-by-count is what makes the boolean sound once types matter — a
        cheap ``{F}{F}`` can be unpayable while a dearer ``●●●`` is not.) So a famine — the premise
        the stall-gust family had wrong at f70 — is ``not reachable_attach(active, None)``, never
        "0 Energy attached".

        Affordability is per-slot TYPED against attached Energy plus the Budget, and any single
        Budget option may pay. Transient attack locks are honoured (ADR-0033): a blanket
        ``self_lock`` body reaches nothing and a ``same_lock`` attack is skipped, so "payable" can
        never mean an attack the engine will not offer. Fail-CLOSED throughout: an unknown body,
        an unresolvable attack record or a 0-cost quirk makes NO claim."""
        stat = self._card_stat((my_body or {}).get("id"))
        if stat is None or budget is None:
            return False
        grant = self._grant(my_body) or {}
        if grant.get("self_lock"):
            return False
        attack_ids = (attack_id,) if attack_id is not None else tuple(stat.attacks or ())
        attached = self._attached_units(my_body)
        return any(_can_pay(slots, attached + tuple(option), budget.caps)
                   for aid in attack_ids if aid != grant.get("same_lock")
                   for slots in (self._attack_slots(aid),) if slots
                   for option in budget.options)

    def reachable_attach_p(self, my_body: dict | None, attack_id=None, *, budget: Budget,
                           p_by_type=None) -> float:
        """The EV reading of :meth:`reachable_attach`: P(``my_body`` can really pay an attack this
        turn), taking the BEST attack by probability (ADR-0074 decision 6, #175).

        Exactly 1.0 when a payable attack needs nothing from the deck, and 0.0 whenever the boolean
        oracle says nothing is payable at all — the two readings agree on feasibility by
        construction, because both walk the same locks, the same attacks and the same matcher. With
        no probability map it degenerates to ``1.0 if reachable_attach(...) else 0.0``, so an
        unweighted caller is unchanged.

        For RANKED consumers only. A gating consumer takes :meth:`reachable_attach` — see **Leg
        Assignment** in ``src/common/CONTEXT.md``."""
        stat = self._card_stat((my_body or {}).get("id"))
        if stat is None or budget is None:
            return 0.0
        grant = self._grant(my_body) or {}
        if grant.get("self_lock"):
            return 0.0
        if not p_by_type:
            return 1.0 if self.reachable_attach(my_body, attack_id, budget=budget) else 0.0
        attack_ids = (attack_id,) if attack_id is not None else tuple(stat.attacks or ())
        attached = self._attached_units(my_body)
        best = 0.0
        for aid in attack_ids:
            if aid == grant.get("same_lock"):
                continue
            slots = self._attack_slots(aid)
            if not slots:
                continue                       # unresolvable cost makes NO claim, either direction
            p = budget.realising_p(slots, p_by_type, attached=attached)
            if p > best:
                best = p
                if best >= 1.0:
                    break
        return best

    def attach_units(self, card_id, count: int = 1) -> tuple:
        """``count`` Budget units of the Energy card ``card_id`` — the PROVISION an attach delivers.

        The same typing rule :meth:`_attached_units` applies to Energy already in play, so a
        hypothetical body built from these units is indistinguishable from the real board it
        models: a typed Basic keeps its colour, a colourless/special Energy (Ignition's {C}{C}{C})
        carries ``{0}`` and so pays colourless slots ONLY, and an unresolvable card is wild."""
        etype = getattr(self._card_stat(card_id), "energyType", None)
        pool = frozenset() if etype is None else frozenset({etype})
        return tuple(AttachUnit(pool) for _ in range(max(0, int(count))))

    @staticmethod
    def wild_units(count: int = 1) -> tuple:
        """``count`` UNTYPED Budget units — Energy whose colour is not yet chosen (an accelerator's
        routed Basics, drawn from a zone the recipient pick does not fix). Each pays any one slot:
        fail-OPEN, exactly as :meth:`attack_type_payable` treats an unresolvable attached Energy."""
        return tuple(AttachUnit(frozenset()) for _ in range(max(0, int(count))))

    def matched_slots(self, my_body: dict | None, attack_id, *, extra_units=()) -> tuple:
        """``(matched, total)`` typed cost slots of ``attack_id`` that ``my_body``'s attached Energy
        plus ``extra_units`` covers — the typed BUILD read (ADR-0069 §3).

        Uses the matcher :meth:`reachable_attach` uses, so build progress and reachability can never
        disagree: an Energy that fills no slot scores no build (off-type waste is then an emergent
        zero, not a separate flag) and a colourless slot absorbs any type (so a genuinely usable
        off-colour attach is never mislabeled). ``(0, 0)`` when no cost record resolves — the caller
        then makes no typed claim and falls back to the count reading."""
        slots = self._attack_slots(attack_id)
        if not slots:
            return (0, 0)
        units = self._attached_units(my_body) + tuple(extra_units)
        return (_matched_slots(slots, units), len(slots))

    def best_reachable_damage(self, my_body: dict | None, *, budget: Budget) -> float:
        """The biggest PRINTED damage among the attacks ``my_body`` can reach this turn under
        ``budget`` — the counterfactual leg of the attach marginal (ADR-0069 §2).

        ANY reachable attack, not the biggest one it might someday afford: a doomed Active that
        unlocks a smaller real attack tonight is credited for exactly that (the Mega-Starmie tempo
        case the rung layer's biggest-attack-only exemption lost). Opponent-independent — the
        overkill cap, not this read, owns "a bigger attack buys nothing". Fail-CLOSED at 0.0."""
        stat = self._card_stat((my_body or {}).get("id"))
        if stat is None or budget is None:
            return 0.0
        return float(max((self.attack_damage(aid) for aid in (stat.attacks or ())
                          if self.reachable_attach(my_body, aid, budget=budget)), default=0))

    def readiness_p(self, my_body: dict | None, attack_id=None, *, budget: Budget,
                    enabler_budget: Budget | None = None,
                    copies: int = 0, pool: int = 0, draws: int = 0, p_by_type=None) -> float:
        """P(``my_body`` is READY to use the attack this turn) — the EV variant of
        :meth:`reachable_attach`, and the probabilistic MIDDLE the interim promote/retreat
        ``fetch_enables_p`` never had (it shipped a bare 1.0/0.0).

        1.0 when ``budget`` — what I hold NOW — already reaches. Otherwise, if drawing a still-in-
        deck enabler WOULD reach (``enabler_budget``, the same Budget computed as though that card
        were in hand), the exact hypergeometric that the turn's remaining dig finds one:
        ``draw_hit_probability(copies, pool, draws)``. Fail-CLOSED at 0.0 — no enabler modelled, or
        an enabler that still would not pay, is worth nothing, never its bare draw odds.

        ``p_by_type`` (ADR-0074 decision 6, #175) additionally prices the DECK-fetch leg inside each
        Budget: this method priced the *draw* honestly while leaving deck presence a fail-open
        boolean, so a line resting on the last copy of a colour read the same as one resting on
        three. Omitted, every reading is 1.0/0.0 and the result is byte-identical to before."""
        now = self.reachable_attach_p(my_body, attack_id, budget=budget, p_by_type=p_by_type)
        if now >= 1.0:
            return 1.0
        if enabler_budget is None:
            return now
        via = self.reachable_attach_p(my_body, attack_id, budget=enabler_budget,
                                      p_by_type=p_by_type)
        if via <= 0.0:
            return now                             # no enabler pays -> only what I already hold
        return max(now, via * draw_hit_probability(copies, pool, draws))

    # --- reachable Incoming: the opponent's next DEVELOPMENT step (ADR-0064) ----------------
    def reachable_incoming(self, my_body: dict | None, opp_bodies, *, forward_ids=None,
                           charged: dict | None = None, evo_min_energy: int = 0,
                           context: dict | None = None, my_benched: bool = False) -> int:
        """The **Incoming that counts ONE development step** (ADR-0064): worst W/R-adjusted damage
        the opponent's affordable attackers among ``opp_bodies`` could deal ``my_body`` NEXT TURN —
        each body's CURRENT form plus its reachable EVOLUTION forms (promote → evolve → attach →
        attack, legal in one turn per rules.md §4), under one attach's Energy. The leaf survival term
        and the promote stand-down share it.

        This is ``incoming(t=1)`` and DELEGATES to :meth:`incoming` — the one implementation, so the
        one-step read stays byte-identical with the N-turn Threat-Clock curve by construction
        (Threat-Clock unification S1; docs/plans/opponent-value-equation-unification.md). All
        arguments (``forward_ids`` availability gate, ``charged`` energy policy, ``evo_min_energy``
        bare-pre-evo guard, transient locks) are documented on :meth:`incoming`."""
        return self.incoming(my_body, opp_bodies, 1, forward_ids=forward_ids, charged=charged,
                             my_benched=my_benched,
                             evo_min_energy=evo_min_energy, context=context)

    def _promotion_open(self, opp_bodies, opp_active, *, switch_enabler: bool = False) -> bool:
        """Can a BENCHED opponent body attack next turn — the promotion gate (ADR-0071 decision 6).

        Retreat is an ordinary turn action (rules.md:74) limited to once per turn and paid in
        **Energy discard** (:89), and attacking ends the turn, so retreat-then-attack is legal in ONE
        turn: a benched attacker owes Energy, never tempo. Open when their Active can pay its printed
        retreat cost, when ``switch_enabler`` says a switch-class out cannot be ruled out, or when
        ``opp_active`` is absent — a body removed from the list is a body that was Knocked Out, and
        the replacement Active is chosen from the Bench for FREE (rulebook.txt:176), which is exactly
        the case `survival_shift` constructs. Fail-OPEN on an unreadable retreat cost.

        ``switch_enabler`` is caller-computed: whether they hold a Switch is a Read/deck-tracker
        question, and `CombatMath` is board-only and deck-agnostic. Every leg here fails OPEN, because
        this gate can only ever make a threat read LESS pessimistic and a survival read must never
        under-prepare (CONTEXT.md, Threat Clock)."""
        if opp_active is None or switch_enabler:
            return True
        if not any(b is opp_active for b in opp_bodies):
            return True                               # their Active is off the board — free promotion
        st = self._card_stat(opp_active.get("id"))
        cost = getattr(st, "retreatCost", None) if st else None
        if cost is None:
            return True                               # unreadable -> admit (pessimistic on threat)
        return len(opp_active.get("energies") or []) >= int(cost)

    def incoming(self, my_body: dict | None, opp_bodies, t: int = 1, *, forward_ids=None,
                 charged: dict | None = None, evo_min_energy: int = 0,
                 context: dict | None = None, my_benched: bool = False,
                 opp_active: dict | None = None, switch_enabler: bool = False) -> int:
        """Worst W/R-adjusted damage the opponent's affordable attackers among ``opp_bodies`` could
        deal ``my_body`` at future turn ``t`` — the **Threat-Clock curve**, the N-turn generalisation
        of ``reachable_incoming`` (ADR-0064 was ``t=1``; S1 of
        docs/plans/opponent-value-equation-unification.md). 0 when unknown.

        Over ``t`` turns the opponent has had ``t`` attach-turns, so ``t`` moves ONLY the ENERGY
        budget — the evolution reach is already MAXIMAL at ``t=1`` (``forward_card_ids`` is
        all-descendants, existence-gated: every forward form is considered under the current energy
        budget, per ADR-0064's availability gate). Card-effect acceleration and discard-recur fuel
        are NOT modelled here (S2 layers them onto the budget); this is the visible-clock read.
        ``t`` is clamped to ``>= 1``; ``t=1`` reproduces ``reachable_incoming`` exactly.

        ``forward_ids``: callable ``cardId -> iterable`` of the forward card ids to consider — the
        AVAILABILITY gate (ADR-0064 Decision 4: pool-forward existence for the threat read,
        matched-Read rep list for the safety read). None → ``forward_card_ids`` (the pool-level index).

        ``charged``: the ENERGY policy (ADR-0064 Decision 1) — the per-consumer conservatism the
        unification keeps as a PARAMETER (survival passes the ceiling, deny/board-clock the slow read).
        - ``None`` → **ceiling** (worst-case, the hidden-burst-safe survival read): a form contributes
          its biggest attack once it can pay its CHEAPEST under ``attached + t`` attaches; the bigger
          attack's affordability is NOT charged. Mirrors the historical ``_incoming_worst`` at ``t=1``.
        - ``{"base_attach": int, "burst_on_evo": int}`` → **charged**: per-attack typed-cost
          affordability under ``attached + t*base_attach`` manual attaches (each wild — pays any one
          typed slot) + ``burst_on_evo`` colourless-only units available ONLY when the attacking form
          is an Evolution (a matched-Read burst-Energy allowance: Ignition provides {C} on a Basic but
          {C}{C}{C} on an Evolution, so the +2 lands only on an evolved form; it pays colourless slots
          only, never a typed {F}{F}). The burst is a single-card allowance — flat in ``t``, not scaled.

        ``evo_min_energy``: the minimum Energy an opponent body must ALREADY carry for its forward
        evolution forms to count (default 0 — credit every pre-evolution). A catastrophe-grade consumer
        (the ``-KO_SCORE`` loss rung) passes 1: a bare 0-Energy pre-evolution is not a credible
        game-ender (it needs the evolution IN HAND plus a from-scratch attach), and crediting it
        manufactures phantom doom (the bounded-pessimism guard, ADR-0064). The current form is always
        counted regardless.

        Transient locks (ADR-0033) are honoured on a body's CURRENT form only — a self-lock skips it
        entirely, a same-attack lock excludes that attack, a self-bonus raises the hit; a forward
        form is grant-free (evolving clears attack effects, rules.md §4). Benched bodies carry no
        grant (serial-gated), so only their live Active is ever lock-adjusted."""
        my_hp = (my_body or {}).get("hp", 0)
        if not (self.stats and my_hp):
            return 0
        turns = max(1, int(t))
        worst = 0
        for form_id, form_body, attached, grant, is_current in self._attacker_forms(
                opp_bodies, forward_ids=forward_ids, evo_min_energy=evo_min_energy,
                opp_active=opp_active, switch_enabler=switch_enabler):
            worst = max(worst, self._reach_form_damage(
                my_body, form_id, form_body, attached, charged, context,
                exclude=grant.get("same_lock") if is_current else None,
                bonus=grant.get("self_bonus", 0) if is_current else 0,
                attaches=turns, my_benched=my_benched))
        return worst

    def _attacker_forms(self, opp_bodies, *, forward_ids=None, evo_min_energy: int = 0,
                        opp_active=None, switch_enabler: bool = False):
        """Every opponent FORM that could attack next turn — ``(form_id, form_body, attached, grant,
        is_current)`` per form, current forms plus their forward evolutions.

        ONE enumeration, because two reads consume it: :meth:`incoming` (the damage curve) and
        :meth:`_bench_payload` (the rider payload). Keeping them separate let them drift — the rider
        read silently skipped the ``evo_min_energy`` bounded-pessimism guard (ADR-0064), crediting a
        bare 0-Energy pre-evolution's riders where the damage read would not. Same reasoning as
        `_build_standing` in ADR-0070: one function owns the fact, so the readings cannot disagree.

        Applies the transient self-lock (a body that cannot attack at all is skipped entirely,
        ADR-0033) and the promotion gate (ADR-0071 decision 6). A forward form is grant-free —
        evolving clears attack effects (rules.md §4)."""
        fwd = forward_ids if forward_ids is not None else self.forward_card_ids
        promotable = self._promotion_open(opp_bodies, opp_active,
                                          switch_enabler=switch_enabler)
        for body in opp_bodies:
            if not body:
                continue
            if not promotable and opp_active is not None and body is not opp_active:
                continue                              # stuck behind an Active that can't pay retreat
            grant = self._grant(body) or {}
            if grant.get("self_lock"):
                continue                              # this body can't attack at all next turn
            attached = len(body.get("energies") or [])
            yield body.get("id"), body, attached, grant, True
            if attached < evo_min_energy:
                continue                              # bare pre-evo — not a credible evolving threat
            for fid in (fwd(body.get("id")) or ()):   # forward forms — carry the attached Energy
                yield fid, {"id": fid, "energies": body.get("energies") or []}, attached, grant, False

    def _bench_rider(self, attack_id) -> int:
        """What ``attack_id`` puts on ONE of my BENCHED bodies: its snipe and spread riders, summed
        (an attack carrying both can aim both at the same body — the worst case, and the additive
        convention `objectives.py` already uses over a bench pool). Riders ignore Weakness and
        Resistance (ADR-0022), so this is deliberately NOT routed through the W/R damage oracle."""
        return self.rider_snipe(attack_id) + self.rider_spread(attack_id)

    def _reach_form_damage(self, my_body, form_id, form_body, attached, charged, context, *,
                           exclude, bonus, attaches: int = 1, my_benched: bool = False) -> int:
        """The worst damage ONE attacker form (current or evolved) deals ``my_body`` under the
        ``charged`` energy policy (see :meth:`incoming`), given ``attaches`` manual attach-turns of
        Energy available (1 = the ADR-0064 one-step read; the Threat-Clock curve passes ``t``). 0
        when the form resolves no stat, cannot afford to attack, or deals nothing.

        ``my_benched`` is the AREA-AT-DAMAGE-TIME of ``my_body`` (ADR-0070 §9): an attack's printed
        damage lands on the ACTIVE, so a benched body is reachable only by the snipe/spread riders —
        and not at all if it is Tera (rules.md §185). The attacker-side self-bonus grant raises
        printed damage, not a rider, so it is not applied on the bench path."""
        stat = self._card_stat(form_id)
        if not stat:
            return 0
        if my_benched and self.is_tera((my_body or {}).get("id")):
            return 0                                  # Tera: no attack damage while Benched
        if charged is None:                           # ceiling: pay cheapest, credit biggest
            if not self._affords(stat, form_body, None, attached, attaches, charged):
                return 0
            if my_benched:
                return max((self._bench_rider(aid) for aid in (stat.attacks or ())
                            if aid != exclude), default=0)
            dmg = self.predicted_max_damage(stat, my_body, exclude_attack=exclude, context=context)
            return int(dmg) + bonus if dmg else 0
        best = 0
        for aid in (stat.attacks or ()):
            if aid == exclude:
                continue
            if not self._affords(stat, form_body, aid, attached, attaches, charged):
                continue                              # unaffordable in count or in colour
            best = max(best, self._bench_rider(aid) if my_benched
                       else int(self.predicted_damage(form_id, aid, my_body,
                                                      bound="max", context=context)))
        if my_benched:
            return best
        return best + bonus if best else 0

    def turns_to_ko(self, attacker_id, energy: int, body: dict | None, *,
                    context: dict | None = None) -> float | None:
        """Feasibility turns for ``attacker_id`` (carrying ``energy``) to fell ``body`` — hp over
        its best affordable per-turn damage vs THAT defender (W/R + riders per the oracle). None
        when it deals no damage (infeasible). The mechanical core of the KO Race (ADR-0040) —
        surcharges/γ-modulation stay with the objectives that own them."""
        import math
        hp = (body or {}).get("hp", 0)
        stat = self._card_stat(attacker_id)
        if not (hp and stat):
            return None
        best = 0
        for aid in (stat.attacks or ()):
            if self.attack_cost(aid) > energy:
                continue
            best = max(best, self.predicted_damage(attacker_id, aid, body, context=context))
        if best <= 0:
            return None
        return float(math.ceil(hp / best))

    def turns_to_afford(self, body: dict | None, *, forward_ids=None,
                        attaches_per_turn: int = 1, max_hops: int = 3,
                        typed: bool = False) -> int | None:
        """The earliest future turn ``body``'s LINE is ARMED — its biggest-damage attack's COST is
        payable (NOT lethality — the armed-threshold blocker) — the Threat Clock's affordability +
        evolve leg behind the deny-slot deadline (S1c of
        docs/plans/opponent-value-equation-unification.md). The MAX of two PARALLEL legs (never the
        sum): the ENERGY deficit (max ``maxDamageCost`` over the body's current + forward forms,
        minus attached, at ``attaches_per_turn``) and the FORWARD hops (the ``evolvesFrom``
        name-chain depth to the deepest owed form, one evolve/turn, depth-guarded by ``max_hops``).
        None when the body/its stats are unknown or no form's biggest-attack cost is known
        (fail-closed — the caller emits no deny slot).

        Shares the forward index and the energy model with :meth:`incoming` — the Threat Clock's two
        legs (the damage curve + the affordability clock) in ONE home. ``forward_ids`` overrides the
        forward callable (the availability gate); ``attaches_per_turn`` is the policy attach rate
        (1 = the slow deny read, the per-consumer conservatism kept as a parameter). The deny-clock
        consumer ``pilot._opp_turns_to_ready`` DELEGATES here (byte-identical).

        ``typed`` picks the energy leg's reading, and it is a FAIL-DIRECTION choice, not a quality
        one — which is why it is a per-consumer parameter like ``charged`` rather than a fix applied
        everywhere. The default COUNT reading (cost minus attached) over-credits off-colour Energy,
        so a body reads armed sooner than it is: pessimistic about THEIR clock, which is the safe
        direction for a threat read. ``typed=True`` counts only Energy that fills a slot of the
        payoff's real cost shape, by the same matcher :meth:`reachable_attach` uses — correct for MY
        bodies, where over-crediting a {D} toward a {P} would price an unpayable line as armed
        (ADR-0070 §2: the evolve decider's deploy delta rides this clock)."""
        from common import needs
        cid = (body or {}).get("id")
        st = self._card_stat(cid)
        if st is None:
            return None
        fwd = forward_ids if forward_ids is not None else self.forward_card_ids
        fwd_stats = [self._card_stat(f) for f in (fwd(cid) or ())]
        costs = [c for c in (getattr(s, "maxDamageCost", None)
                             for s in (st, *fwd_stats) if s is not None) if c is not None]
        if not costs:
            return None
        deepest = max(((s, getattr(s, "maxDamageCost", 0) or 0) for s in (st, *fwd_stats)
                       if s is not None and getattr(s, "maxDamageCost", None) is not None),
                      key=lambda pair: pair[1], default=(None, 0))[0]
        deficit = max(costs) - len((body or {}).get("energies") or [])
        if typed and deepest is not None:
            aid = max((getattr(deepest, "attacks", None) or ()), key=self.attack_damage, default=None)
            if aid is not None:
                matched, slots = self.matched_slots(body, aid)
                if slots:
                    deficit = slots - matched
        parent = {s.name: getattr(s, "evolvesFrom", None) for s in fwd_stats
                  if s is not None and s.name}
        hops = 0
        for name in parent:
            d, n = 0, name
            while n and n != st.name and d <= max_hops:
                d, n = d + 1, parent.get(n)
            if n == st.name:
                hops = max(hops, d)
        return needs.turns_to_ready(energy_deficit=deficit, evolve_hops=hops,
                                    attaches_per_turn=attaches_per_turn)

    def _bench_payload_pairs(self, opp_bodies, t: int, *, charged=None, opp_active=None,
                             switch_enabler: bool = False) -> set:
        """Every ``(snipe, spread)`` rider payload their board could put on my Bench at turn ``t``.

        Attacking ends their turn (rules.md §5), so a turn's bench damage is ONE attack's payload
        from ONE attacker — but the CHOICE of attack belongs to the harvest solver, not to a
        pre-filter here, so this returns all of them. The two halves stay SPLIT because they
        allocate differently: the snipe is indivisible and the spread is not (ADR-0071 decision 2)."""
        pairs = set()
        for form_id, form_body, attached, grant, is_current in self._attacker_forms(
                opp_bodies, opp_active=opp_active, switch_enabler=switch_enabler):
            stat = self._card_stat(form_id)
            if not stat:
                continue
            for aid in (stat.attacks or ()):
                if is_current and aid == grant.get("same_lock"):
                    continue
                if not self._affords(stat, form_body, aid, attached, t, charged):
                    continue
                pair = (self.rider_snipe(aid), self.rider_spread(aid))
                if any(pair):
                    pairs.add(pair)
        return pairs

    def _affords(self, stat, form_body, aid, attached: int, t: int, charged) -> bool:
        """Whether ``aid`` is payable at turn ``t`` under the ``charged`` policy (see :meth:`incoming`).

        ONE function owns affordability, so the damage read (:meth:`_reach_form_damage`) and the
        rider read (:meth:`_bench_payload`) cannot drift about which attacks are on the menu — the
        `_build_standing` lesson from ADR-0070, applied here because #163 added a second consumer.

        Under the ceiling policy (``charged is None``) the question is per-FORM, not per-attack: a
        form contributes once it can pay its CHEAPEST attack, and ``aid`` is then irrelevant."""
        if charged is None:                           # ceiling: pay cheapest, credit anything
            return bool(stat.can_pay_cheapest(attached + t))
        base = charged.get("base_attach", 1)
        # Ignition-class colourless burst lands its full {C}{C}{C} only on an Evolution (rules.md /
        # card text) — a Basic form gets the plain single attach, no burst. A single-card allowance,
        # so it is flat in the turn count, never scaled by ``t``.
        burst = charged.get("burst_on_evo", 0) if getattr(stat, "evolvesFrom", None) else 0
        wild = t * base
        if self.attack_cost(aid) > attached + wild + burst:
            return False
        return bool(self.attack_type_payable(aid, form_body, wild_units=wild))

    def turns_to_ko_me(self, my_body: dict | None, opp_bodies, *, charged: dict | None = None,
                       max_t: int = 8, context: dict | None = None, my_benched: bool = False,
                       my_bench=(), key_ids=frozenset(), reading: str = HARVEST_POSSIBLE,
                       opp_active: dict | None = None, switch_enabler: bool = False) -> int:
        """The earliest future turn the opponent's board can KO ``my_body`` — the survival-window
        inversion of the Threat-Clock curve — or ``max_t + 1`` when it survives the horizon.

        **Damage ACCUMULATES** (ADR-0071 decision 4). The Active leg is
        ``min{ t : Σᵢ₌₁..ᵗ incoming(i) ≥ hp }``: counters persist, so a body that survives one swing
        is not safe forever. That is not a new semantic — CONTEXT.md's Threat Clock already specified
        *"accumulating over turns when one hit doesn't KO"*, and the offensive twin
        :meth:`turns_to_ko` is already rate-based; the one-swing reading was the outlier. The sum of
        per-turn maxima errs PESSIMISTIC — it charges nothing for the retreat that switching
        attackers costs — which is the bounded-pessimism convention (ADR-0064) and the direction that
        deflates rescue credit. So this is deliberately NOT the exact mirror of single-attacker
        :meth:`turns_to_ko`.

        The BENCH leg asks the shared-budget question instead: the first ``t`` at which ``my_body``
        falls in the :meth:`bench_harvest` of ``t`` allocated payloads. The two areas never contend —
        printed damage always lands on the Active and riders always on the Bench — so they are
        independent by card mechanics rather than by assumption.

        ``my_bench`` / ``key_ids`` / ``reading`` are the harvest inputs; omitting ``my_bench`` reads
        the body ALONE, which reproduces the per-body answer for an undeclared caller, and the
        default ``reading`` is the conservative one. Removing an opponent body can only RAISE the
        result, so the Δ across a removal is the turns of survival bought."""
        hp = (my_body or {}).get("hp", 0)
        if not hp:
            return max_t + 1
        horizon = max(1, int(max_t))
        if my_benched:
            bench = list(my_bench) or [my_body]
            try:
                me = next(i for i, b in enumerate(bench) if b is my_body)
            except StopIteration:                     # not in the snapshot — read it alone
                bench, me = [my_body], 0
            # Count, per candidate attack, how many of turns 1..t it is affordable for — they commit
            # to a bench line and use it whenever they can, and counters PERSIST, so `k` turns of one
            # attack is `k` indivisible snipes plus `k` spreads of divisible budget.
            seen: dict = {}
            for t in range(1, horizon + 1):
                for pair in self._bench_payload_pairs(opp_bodies, t, charged=charged,
                                                      opp_active=opp_active):
                    seen[pair] = seen.get(pair, 0) + 1
                payloads = [([s] * k if s else [], p * k) for (s, p), k in seen.items()]
                if me in self.bench_harvest(bench, payloads, reading=reading, key_ids=key_ids):
                    return t
            return horizon + 1
        dealt = 0
        for t in range(1, horizon + 1):
            dealt += self.incoming(my_body, opp_bodies, t, charged=charged, context=context,
                                   opp_active=opp_active, switch_enabler=switch_enabler)
            if dealt >= hp:
                return t
        return horizon + 1


    def discard_recur_fuel(self, body: dict | None, opp_discard_energy: dict | None, *,
                           forward_ids=None) -> int:
        """The extra Basic Energy a `discard_energy_recur` line can reload from the opponent's DISCARD
        next turn — the Threat Clock's discard-fuel input (S2 of
        docs/plans/opponent-value-equation-unification.md). A refueler taps its own discard as an
        extra energy reservoir beyond the 1 manual attach/turn, so its line is faster (lower
        :meth:`turns_to_afford`) and more dangerous (higher :meth:`incoming`). Verified card facts
        (EN_Card_Data.csv): Mega Lucario ex 678 Aura Jab attaches up to 3 Basic {F} from its discard
        to its Bench; Archaludon ex 190 Assemble Alloy up to 2 Basic {M} to its {M} Pokémon.

        Returns ``min(discard count of the line's own type, _RECUR_RELOAD_CAP)`` — the reload TYPE is
        the recur form's own ``energyType`` (verified {F}/{M}). 0 when no form in the body's line
        (current + forward) carries the tag, no Basic Energy of the line's type sits in the discard,
        or functions/stats are blind (fail-open). Pure: a caller models the fuel by augmenting a
        body's ``energies`` and re-reading the clock — the live reads are unchanged (S2 shadow-only)."""
        if not (self.functions and self.stats) or not opp_discard_energy:
            return 0
        st = self._card_stat((body or {}).get("id"))
        if st is None:
            return 0
        fwd = forward_ids if forward_ids is not None else self.forward_card_ids
        forms = [st, *(self._card_stat(f) for f in (fwd(st.cardId) or ()))]
        recur = next((s for s in forms if s is not None
                      and "discard_energy_recur" in self.functions.tags(s.cardId)), None)
        if recur is None or recur.energyType is None:
            return 0
        return min(int(opp_discard_energy.get(recur.energyType, 0)), _RECUR_RELOAD_CAP)

    def attack_realising_p(self, attack_id, *, budget, body=None, p_by_type=None) -> float:
        """P(``budget`` plus ``body``'s attached Energy really pays ``attack_id``) — the Probability
        Leg applied to ONE attack's typed cost (ADR-0074, #175). 1.0 with no probability map (an
        unweighted caller), and 1.0 for a cost this oracle cannot resolve — an unknown cost makes no
        claim, so it must not manufacture a discount either."""
        if not p_by_type:
            return 1.0
        slots = self._attack_slots(attack_id)
        if not slots:
            return 1.0
        return budget.realising_p(slots, p_by_type, attached=self._attached_units(body))

    # --- KO valuation (the shared band every hypothetical attacker is priced on) ------------
    def bench_snipe_bonus(self, opp_bench, attack_id) -> float:
        """Sub-prize tiebreak (ADR-0022 #14): an attack that ALSO snipes a benched Pokémon is
        worth a little extra board value — scaled by the rider, capped below a prize; 0 with no
        clean rider or no benched target."""
        rider = self.rider_snipe(attack_id)
        if rider <= 0 or not opp_bench:
            return 0
        return min(_BENCH_SNIPE_CAP, _BENCH_SNIPE * rider)

    def bench_spread_bonus(self, opp_bench, attack_id) -> float:
        """Sub-prize tiebreak for a distributable bench SPREAD that doesn't finish a bench mon —
        it still pre-loads the Bench. Mirrors ``bench_snipe_bonus``; nonzero only for spreads."""
        spread = self.rider_spread(attack_id)
        if spread <= 0 or not opp_bench:
            return 0
        return min(_BENCH_SNIPE_CAP, _BENCH_SNIPE * spread)

    def best_affordable_ko_value(self, opp: dict, attacker_id: int | None, energy: int, *,
                                 opp_bench=(), bound: str = "exact", body: dict | None = None,
                                 extra_type=None, extra_units: int = 0,
                                 boost_amount: int = 0, boost_type=None,
                                 promote_bench_names=None, attack_p=None,
                                 budget: Budget | None = None) -> float:
        """The best KO value ``attacker_id`` (carrying ``energy`` Energy) reaches against the
        opponent's Active — KO_SCORE + prize − efficiency + bench-snipe rider, the ONE band every
        hypothetical attacker is priced on (retreat/gust/promote/attach/boost lookaheads). 0 if no
        affordable attack knocks the defender out; ``bound="min"`` for the Lethal Solver's sound
        floor (a coin-conditional KO never locks a phantom).

        ``body`` (the attacker's on-board dict) arms the ``attack_type_payable`` guard: an attack
        whose SPECIFIC-type slots the body's attached Energy provably can't cover is dropped even
        when the count suffices. Energy beyond the body's attached cards — a planned attach — is
        ``extra_units`` of ``extra_type`` when the caller knows the card, else counted WILD
        (fail-open). ``boost_amount``/``boost_type`` price a typed flat this-turn damage boost
        through the oracle's own ``atk_boosts`` context (attacker-type gate, before-W/R placement).
        ``promote_bench_names`` names the bodies that WILL sit on my Bench after the presumed
        promote/retreat — a ``requiresBench`` attack whose partner is provably benched then reads
        its printed damage rather than the does-nothing floor. ``opp_bench`` is the Board's
        ``((cardId, hp), …)`` snapshot behind the rider tiebreaks.

        ``attack_p`` (ADR-0074, #175) weights each candidate attack by P(the Energy it needs is
        really there) — ``attack_p(attack_id) -> float``. It is the RANKED-consumer hook and is
        omitted by every lock: with it absent the method is byte-identical to before. Because the
        weight is applied per attack BEFORE the max, the winner is the attack with the best
        *expected* value, not the best value that might not happen.

        ``budget`` (ADR-0075, #177) replaces the COUNT with the **Attach Budget** — the typed
        capacity toward THIS attacker. Affordability then asks the one predicate
        :meth:`reachable_attach` asks, ``_can_pay`` per slot over each option, so a planned attach
        pays a specific-type slot only when the cards really produce that colour. ``energy`` and
        ``extra_units``/``extra_type`` are IGNORED on this leg — the Budget is the whole truth — and
        the count gate is subsumed (``_can_pay`` refuses when there are fewer units than slots).

        **Refusal and ranking are separate** (ADR-0075 decision 7). ``budget`` decides WHETHER the
        KO is real: it fails CLOSED, so an attack whose slots do not resolve is skipped and makes no
        claim, where ``attack_type_payable`` would fail open. ``attack_p`` decides what a real KO is
        WORTH. The order is refuse-then-weight — a refused attack never reaches the multiply, so an
        unpayable attack and a certain-but-worthless one stay distinguishable."""
        stat = self._card_stat(attacker_id)
        opp_hp = (opp or {}).get("hp", 0)
        if not (stat and opp_hp):
            return 0.0
        wild = (max(0, energy - len(body.get("energies") or []) - extra_units)
                if body is not None else 0)
        if extra_type is None and extra_units:
            wild += extra_units     # UNKNOWN-type extra stays wild — only a provably-colourless
                                    # extra (extra_type=0, Ignition) is strict; never false-suppress
        ctx = None
        if boost_amount or promote_bench_names is not None:
            ctx = {}
            if boost_amount:
                ctx["atk_boosts"] = ((boost_amount, boost_type, False),)
            if promote_bench_names is not None:
                ctx["atk_bench_names"] = tuple(promote_bench_names)
        attached = self._attached_units(body) if budget is not None else ()
        best = 0.0
        for aid in (stat.attacks or ()):
            cost = self.attack_cost(aid)
            if budget is not None:
                # TYPED leg (ADR-0075): the Budget is authoritative and exclusive — `energy` and the
                # wild extras are not consulted. Fail-CLOSED on an unresolvable cost, matching
                # `reachable_attach`: no slots, no claim (the fail-open `attack_type_payable` would
                # have counted it). Verified inert on real data — no card prints a 0-cost attack.
                slots = self._attack_slots(aid)
                if not slots or not any(_can_pay(slots, attached + tuple(option), budget.caps)
                                        for option in budget.options):
                    continue
            else:
                if cost > energy:                               # can't afford this attack right now
                    continue
                if body is not None and not self.attack_type_payable(
                        aid, body, extra_type=extra_type, extra_units=extra_units, wild_units=wild):
                    continue                                    # count met, a specific-type slot is not
            eff_bound = bound
            if bound == "min" and promote_bench_names is not None:
                ast = self.attack_stat(aid)                     # a requiresBench-only conditional whose
                if (ast is not None and getattr(ast, "requiresBench", None)                # partner is
                        and all(n in promote_bench_names for n in ast.requiresBench)       # provably
                        and (ast.damageMax is None or ast.damageMax == ast.damage)):       # benched
                    eff_bound = "exact"     # is deterministic — read printed, not the does-nothing floor
            # per-attack oracle (ADR-0032): prevention is attack-scoped — a benched non-ex (or an
            # ignore-flag attack) still registers its KO against a prevent_ex_damage wall
            dmg = self.predicted_damage(attacker_id, aid, opp, bound=eff_bound, context=ctx)
            if dmg >= opp_hp:
                val = (KO_SCORE + self.prize_value(opp) - _EFFICIENCY * cost
                       + self.bench_snipe_bonus(opp_bench, aid) + self.bench_spread_bonus(opp_bench, aid))
                if attack_p is not None:
                    val *= max(0.0, min(1.0, float(attack_p(aid))))   # ranked consumer: EV, not claim
                best = max(best, val)
        return best
