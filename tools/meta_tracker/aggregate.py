"""Pure per-Episode aggregation over the extract store — no rendering, no plotly.

The stats the dashboard renders and the deck export ranks by: per-side flattening
(``sides``), per-key play/win rates (``rate_table``), and the variant subset-merge
(``merge_map``). Kept lib-free so both ``dashboard`` (rendering) and ``export_decks``
can import them without dragging Plotly into an offline tool. All metrics are
per-Episode (encounter-weighted) — see CONTEXT.md → Play rate / Win rate / Variant Cluster.
"""
from __future__ import annotations

from collections import Counter, defaultdict


def sides(ep: dict):
    """Yield one record per player side of an episode."""
    for i in (0, 1):
        yield {
            "band": ep["band"],
            "date": (ep.get("end_time") or ep.get("created_at") or "")[:10],
            "arch": ep[f"arch{i}"],
            "mains": ep[f"mains{i}"] or [],
            "subs": ep[f"subs{i}"] or [],
            "energy": ep[f"energy{i}"] or [],
            "won": ep["winner_index"] == i,
            "decided": ep["winner_index"] is not None,
        }


def rate_table(episodes: list[dict], key: str):
    """Per-key play rate (per-episode) + win rate. key in {'mains','arch'}."""
    total = len(episodes)
    appear_eps: Counter = Counter()       # episodes where key value appears (either side)
    deck_app: Counter = Counter()         # side-appearances
    deck_win: Counter = Counter()         # side-appearances that won (decided only)
    deck_dec: Counter = Counter()
    subs: defaultdict[str, Counter] = defaultdict(Counter)
    energy: defaultdict[str, Counter] = defaultdict(Counter)

    for ep in episodes:
        seen = set()
        for s in sides(ep):
            vals = s["mains"] if key == "mains" else [s["arch"]]
            for v in vals:
                if not v:
                    continue
                deck_app[v] += 1
                if s["decided"]:
                    deck_dec[v] += 1
                    deck_win[v] += int(s["won"])
                for sub in s["subs"]:
                    subs[v][sub] += 1
                for en in s["energy"]:
                    energy[v][en] += 1
                seen.add(v)
        for v in seen:
            appear_eps[v] += 1

    out = []
    for v, n_eps in appear_eps.most_common():
        out.append({
            "name": v,
            "play_rate": n_eps / total if total else 0.0,
            "win_rate": deck_win[v] / deck_dec[v] if deck_dec[v] else None,
            "episodes": n_eps,
            "subs": [s for s, _ in subs[v].most_common(4)],
            "energy": [e for e, _ in energy[v].most_common(3)],
        })
    return out


def merge_map(eps: list[dict]) -> dict[str, str]:
    """Subset-merge archetypes that share a primary main line, then label each
    cluster by its **most common** member (not the fullest — a rare 3-main
    variant shouldn't rename the dominant 1-main deck). Non-destructive (view only).
    E.g. the Hop's Trevenant variants collapse to one; plain Alakazam stays 'Alakazam'."""
    mains: dict[str, frozenset] = {}
    primary: defaultdict[str, Counter] = defaultdict(Counter)
    freq: Counter = Counter()
    for e in eps:
        for i in (0, 1):
            name, ml = e[f"arch{i}"], e[f"mains{i}"] or []
            mains[name] = frozenset(ml)
            if ml:
                primary[name][ml[0]] += 1
            freq[name] += 1
    prim = {n: (primary[n].most_common(1)[0][0] if primary[n] else None) for n in mains}

    # Each archetype -> the maximal superset sharing its primary (defines clusters).
    direct: dict[str, str] = {}
    for a in mains:
        best = None
        for b in mains:
            if b != a and mains[a] < mains[b] and prim[a] is not None and prim[a] == prim[b]:
                if best is None or (len(mains[b]), freq[b]) > (len(mains[best]), freq[best]):
                    best = b
        direct[a] = best or a

    def root(n: str) -> str:
        seen = set()
        while direct[n] != n and n not in seen:
            seen.add(n)
            n = direct[n]
        return n

    clusters: defaultdict[str, list] = defaultdict(list)
    for a in mains:
        clusters[root(a)].append(a)
    label: dict[str, str] = {}
    for members in clusters.values():
        rep = max(members, key=lambda m: (freq[m], len(mains[m])))  # most common, tie -> fullest
        for m in members:
            label[m] = rep
    return label


def apply_merge(eps: list[dict], merge: dict[str, str]) -> list[dict]:
    """Relabel each side's archetype to its Variant Cluster (non-destructive copy)."""
    return [{**e, "arch0": merge.get(e["arch0"], e["arch0"]),
             "arch1": merge.get(e["arch1"], e["arch1"])} for e in eps]
