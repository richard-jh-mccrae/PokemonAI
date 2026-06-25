"""Render the self-contained HTML meta dashboard from the extract store.

All metrics are per-Episode (encounter-weighted). Plotly.js is inlined so the
file opens offline with no network. See CONTEXT.md for Play rate / Win rate.
"""
from __future__ import annotations

import datetime as _dt
import html
from collections import Counter, defaultdict
from pathlib import Path

import plotly.graph_objects as go
from plotly.io import to_html
from plotly.offline import get_plotlyjs

from . import config
from .cards import load_cards
from .store import connect, load_episodes

_BAND_ORDER = [b[0] for b in config.BANDS]


def _sides(ep: dict):
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


def _rate_table(episodes: list[dict], key: str):
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
        for s in _sides(ep):
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


def _rate_bar(rows: list[dict], band: str, what: str = "deck archetypes") -> go.Figure:
    """Horizontal play-rate bars (one bar per archetype), coloured by win rate."""
    rows = rows[:15][::-1]
    wins = [(r["win_rate"] if r["win_rate"] is not None else 0.5) for r in rows]
    fig = go.Figure(go.Bar(
        x=[r["play_rate"] * 100 for r in rows],
        y=[r["name"] for r in rows],
        orientation="h",
        marker=dict(color=[w * 100 for w in wins], colorscale="RdYlGn", cmin=30, cmax=70,
                    colorbar=dict(title="win %")),
        text=[f"{r['play_rate']*100:.0f}%  (n={r['episodes']}"
              + (f", win {r['win_rate']*100:.0f}%)" if r["win_rate"] is not None else ")")
              for r in rows],
        textposition="auto",
    ))
    fig.update_layout(title=f"{band} — {what} by play rate",
                      height=max(360, 28 * len(rows) + 90), margin=dict(l=10, r=10, t=40, b=30),
                      xaxis_title="play rate (% of episodes)", template="plotly_white")
    fig.update_yaxes(automargin=True)  # room for long archetype names
    return fig


def _trend_fig(episodes: list[dict], top_names: list[str]) -> go.Figure:
    by_date_total: Counter = Counter()
    by_date_name: defaultdict[str, Counter] = defaultdict(Counter)
    for ep in episodes:
        d = (ep.get("end_time") or ep.get("created_at") or "")[:10]
        if not d:
            continue
        by_date_total[d] += 1
        for nm in {ep["arch0"], ep["arch1"]}:            # by archetype, not individual Pokémon
            by_date_name[nm][d] += 1
    dates = sorted(by_date_total)[-30:]
    fig = go.Figure()
    for nm in top_names:
        fig.add_trace(go.Scatter(
            x=dates, y=[(by_date_name[nm][d] / by_date_total[d] * 100 if by_date_total[d] else 0) for d in dates],
            mode="lines+markers", name=nm))
    fig.update_layout(title="Deck archetype play rate over time (all bands)",
                      height=420, margin=dict(l=10, r=10, t=40, b=30),
                      yaxis_title="play rate (%)", template="plotly_white", hovermode="x unified")
    return fig


_CAT_ORDER = [("pokemon", "Pokémon"), ("item", "Items"), ("tool", "Tools"),
              ("supporter", "Supporters"), ("stadium", "Stadiums"),
              ("basic_energy", "Basic Energy"), ("special_energy", "Special Energy")]


def _archetype_decks(band_eps: list[dict], name: str) -> list[list[int]]:
    """Every decklist labelled with this archetype (matching side only)."""
    out = []
    for e in band_eps:
        if e["arch0"] == name:
            out.append(e["deck0"])
        if e["arch1"] == name:
            out.append(e["deck1"])
    return out


def _modal_deck(decks: list[list[int]]):
    """The most-common exact 60-card list + how many decks ran it."""
    keyed = Counter(tuple(sorted(d)) for d in decks)
    (best, freq), = keyed.most_common(1)
    return list(best), freq


def _flex_cards(decks: list[list[int]], modal_ids: set[int], cards: dict) -> list[str]:
    """Cards that vary across this archetype's lists (tech / flex slots)."""
    n = len(decks)
    inc = Counter()
    for d in decks:
        inc.update(set(d))
    flex = [f"{cards.get(cid, {}).get('name', cid)} ({c / n * 100:.0f}%)"
            for cid, c in inc.most_common() if 0.15 <= c / n <= 0.85 and cid not in modal_ids]
    return flex[:10]


def _decklist_html(deck_ids: list[int], cards: dict) -> str:
    cc = Counter(deck_ids)
    by_cat: defaultdict[str, list] = defaultdict(list)
    for cid, k in cc.items():
        card = cards.get(cid, {})
        by_cat[card.get("category", "?")].append((k, card.get("name", str(cid))))
    parts = []
    for cat, label in _CAT_ORDER:
        items = by_cat.get(cat)
        if not items:
            continue
        items.sort(key=lambda x: (-x[0], x[1]))
        total = sum(k for k, _ in items)
        cs = " · ".join(f"{k} {html.escape(nm)}" for k, nm in items)
        parts.append(f"<div class='cat'><span class='cl'>{label} ({total})</span> {cs}</div>")
    return "".join(parts)


def _arch_details_html(band_eps: list[dict], rows: list[dict], cards: dict) -> str:
    """Collapsible archetype cards: summary stats + full decklist + flex slots."""
    blocks = []
    for r in rows[:15]:
        decks = _archetype_decks(band_eps, r["name"])
        if not decks:
            continue
        modal, freq = _modal_deck(decks)
        win = f"{r['win_rate']*100:.0f}% win" if r["win_rate"] is not None else "win —"
        summary = (f"{html.escape(r['name'])}<span class='mut'> — {r['play_rate']*100:.1f}% play · "
                   f"{win} · n={r['episodes']}</span>")
        flex = _flex_cards(decks, set(modal), cards)
        flex_html = (f"<div class='flex'><span class='cl'>Flex slots</span> {html.escape(' · '.join(flex))}</div>"
                     if flex else "")
        body = (f"<div class='dl'><div class='mut'>most-common list — {freq} of {len(decks)} decks "
                f"({sum(Counter(modal).values())} cards)</div>"
                f"{_decklist_html(modal, cards)}{flex_html}</div>")
        blocks.append(f"<details><summary>{summary}</summary>{body}</details>")
    return "".join(blocks)


def _merge_map(eps: list[dict]) -> dict[str, str]:
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


_CSS = """
body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:24px;color:#1b1f24;background:#fff}
h1{margin:0 0 4px} .sub{color:#667;margin-bottom:18px}
.band{margin:34px 0 8px;border-top:3px solid #e3e7ec;padding-top:14px}
.grid{display:flex;flex-wrap:wrap;gap:18px;align-items:flex-start}
.col{flex:1 1 460px;min-width:380px}
details{border:1px solid #e3e7ec;border-radius:6px;margin:6px 0;padding:5px 11px;background:#fafbfc}
details[open]{background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.06)}
summary{cursor:pointer;font-size:13px}
.dl{margin:9px 2px 4px;font-size:12.5px;line-height:1.75}
.cat{margin:2px 0} .cl{display:inline-block;min-width:108px;color:#3a4b6d;font-weight:600}
.mut{color:#889;font-weight:400} .flex{margin-top:5px;color:#667}
.rows{max-width:940px} h3{margin:18px 0 6px}
"""


def build_dashboard(db_path=None, out_path=None) -> Path:
    out = Path(out_path) if out_path else config.DASHBOARD
    out.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    eps = load_episodes(conn)
    conn.close()
    cards = load_cards()

    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    if not eps:
        out.write_text(f"<html><body><h1>Pokémon TCG Meta</h1>"
                       f"<p>No episodes in the store yet. Run the daily pipeline.</p>"
                       f"<p class=sub>generated {now}</p></body></html>", encoding="utf-8")
        return out

    merge = _merge_map(eps)  # fold subset-variant archetypes into their fullest superset
    eps = [{**e, "arch0": merge.get(e["arch0"], e["arch0"]),
            "arch1": merge.get(e["arch1"], e["arch1"])} for e in eps]

    by_band: dict[str, list[dict]] = {b: [] for b in _BAND_ORDER}
    for ep in eps:
        by_band.setdefault(ep["band"] or "?", []).append(ep)

    overall = _rate_table(eps, "arch")
    top_names = [r["name"] for r in overall[:8]]

    sections = [to_html(_trend_fig(eps, top_names), include_plotlyjs=False, full_html=False)]
    for band in _BAND_ORDER:
        band_eps = by_band.get(band) or []
        if not band_eps:
            continue
        arch = _rate_table(band_eps, "arch")
        bar = to_html(_rate_bar(arch, band), include_plotlyjs=False, full_html=False)
        sections.append(
            f"<div class='band'><h2>{band} <span class=sub>({len(band_eps)} episodes)</span></h2>"
            f"{bar}"
            f"<h3>Decks <span class=sub>(click a row for the full decklist)</span></h3>"
            f"<div class='rows'>{_arch_details_html(band_eps, arch, cards)}</div></div>")

    counts = " · ".join(f"{b}: {len(by_band.get(b) or [])}" for b in _BAND_ORDER)
    page = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>Pokémon TCG Meta</title><style>{_CSS}</style>"
            f"<script>{get_plotlyjs()}</script></head><body>"
            f"<h1>Pokémon TCG — Deck Meta</h1>"
            f"<div class=sub>{len(eps)} episodes &nbsp;|&nbsp; {counts} &nbsp;|&nbsp; generated {now}</div>"
            f"{''.join(sections)}</body></html>")
    out.write_text(page, encoding="utf-8")
    return out
