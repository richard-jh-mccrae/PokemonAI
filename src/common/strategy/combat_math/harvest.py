"""Bench spread and the HARVEST: which benched bodies a spread attack can KO, and which of them fall
under EVERY optimal allocation rather than merely some.

The two readings pull opposite ways — per-body worst case over-counts a THREAT and over-credits a
RESCUE — so the caller names which question it is asking (`combat_math.policy`)."""
from __future__ import annotations


from common.strategy.combat_math.policy import HARVEST_POSSIBLE, HARVEST_UNAVOIDABLE


_BENCH_SNIPE = 0.005       # per-point value of an attack's bench-snipe/spread rider

_BENCH_SNIPE_CAP = 0.9     # sub-prize tiebreak: never overrides a prize (ADR-0022 #14)


class HarvestMixin:
    """Bench spread, and which knock-outs are unavoidable."""

    # ``opp_bench`` is ((cardId, hp), …) — the Board snapshot, not body dicts.
    def bench_ko_indices(self, opp_bench, reach: int) -> frozenset:
        """WHICH benched Pokémon ``reach`` damage Knocks Out — indices into ``opp_bench``. The bench KO
        rule, stated ONCE: bench damage ignores Weakness/Resistance and Tera bodies take none (ADR-0022)."""
        if reach <= 0:
            return frozenset()
        return frozenset(i for i, (cid, hp) in enumerate(opp_bench)
                         if hp and hp <= reach and not self.is_tera(cid))

    def snipe_ko_prizes(self, opp_bench, rider: int) -> int:
        """Max prize among the opponent's benched Pokémon a bench-snipe ``rider`` KNOCKS OUT; 0 when it
        finishes nothing. DERIVED from :meth:`bench_ko_indices`."""
        bench = list(opp_bench)
        return max((self.prize_value({"id": bench[i][0]})
                    for i in self.bench_ko_indices(bench, rider)), default=0)

    @staticmethod
    def best_ko_subset(items, budget: int) -> frozenset:
        """Indices of the max-total-prize subset of ``items`` (``[(hp, prize), …]``) whose total HP fits
        in ``budget``. Ties break to the cheaper set; empty frozenset when nothing is affordable."""
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
        """Spread still owed to fell every body in ``needs`` after spending the INDIVISIBLE ``snipes``
        optimally (ADR-0071 decision 2). Greedy: exact for equal-size units, an over-stating bound otherwise."""
        rest = list(needs)
        for unit in sorted(snipes, reverse=True):
            if unit <= 0 or not rest:
                continue
            i = max(range(len(rest)), key=lambda j: rest[j])
            rest[i] = max(0, rest[i] - unit)
        return sum(rest)

    @staticmethod
    def _harvest_optima(items, snipes, spread: int):
        """``(objective key, [optimal subsets])`` for ONE payload. EVERY subset tying at the best
        objective, because the two Harvest Readings are the union and the intersection of that set."""
        best_key, optimal = None, []
        for mask in range(1 << len(items)):          # bench <= 5 -> <= 32 subsets
            chosen = [i for i in range(len(items)) if mask & (1 << i)]
            residual = HarvestMixin._harvest_residual([items[i][0] for i in chosen], snipes)
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
        Harvest** (ADR-0071). ``items`` = ``((hp, prize, is_key), …)``; ``reading`` picks SOME vs EVERY optimum."""
        return HarvestMixin._read_optima(HarvestMixin._harvest_optima(items, snipes, spread)[1], reading)

    def _harvest_items(self, bench, key_ids):
        """``(items, index map)`` for :meth:`best_harvest` — my benched bodies riders can reach. Tera
        bodies take NO attack damage while Benched (rules.md §11), so they drop, index map and all."""
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
        """The Bench Harvest over MY benched body dicts — indices into ``my_bench``. ``payloads`` are the
        CANDIDATE ``(snipes, spread)`` attacks: WHICH one they use is part of the solve, not a pre-filter."""
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

    def bench_harvest_clock(self, my_bench, opp_bodies, *, charged: dict | None = None,
                            max_t: int = 8, key_ids=frozenset(),
                            reading: str = HARVEST_POSSIBLE,
                            opp_active: dict | None = None) -> dict:
        """``{bench index: first turn it falls in the harvest}`` for the WHOLE Bench in one solve — absent
        means it survives ``max_t``. The rider budget belongs to the BENCH, so per-body is a whole re-solve."""
        bench = list(my_bench)
        if not bench:
            return {}
        horizon = max(1, int(max_t))
        first: dict = {}
        seen: dict = {}
        for t in range(1, horizon + 1):
            for pair in self._bench_payload_pairs(opp_bodies, t, charged=charged,
                                                  opp_active=opp_active):
                seen[pair] = seen.get(pair, 0) + 1
            payloads = [([s] * k if s else [], p * k) for (s, p), k in seen.items()]
            for i in self.bench_harvest(bench, payloads, reading=reading, key_ids=key_ids):
                first.setdefault(i, t)
            if len(first) == len(bench):
                break                                 # every body accounted for — no later turn adds
        return first

    def spread_ko_prizes(self, opp_bench, spread: int) -> int:
        """Max total prizes from distributing a ``spread`` across the opponent's Bench to KNOCK OUT
        benched Pokémon (spread counters ignore W/R; Tera take none). 0 when nothing is finishable."""
        if spread <= 0:
            return 0
        items = [(hp, self.prize_value({"id": cid})) for cid, hp in opp_bench
                 if hp and hp <= spread and not self.is_tera(cid)]
        return sum(items[i][1] for i in self.best_ko_subset(items, spread))

    def bench_snipe_bonus(self, opp_bench, attack_id) -> float:
        """Sub-prize tiebreak (ADR-0022 #14): an attack that ALSO snipes a benched Pokémon is worth a
        little extra board value — scaled by the rider, capped below a prize."""
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
