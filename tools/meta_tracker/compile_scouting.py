"""Compile the meta into the shipped Scouting artifact (see docs/scouting.md).

Pure and native-lib-free: reads episode dicts (as `store.load_episodes` returns) plus
card metadata (`cards.json`), and emits the artifact dict the runtime Scout loads. Each
episode contributes two recency-weighted deck observations (one per side). `now` is
injected so decay is deterministic and testable.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from .archetype import evolution_lines, is_engine
from .cards import is_attacker, is_exclass, stage_rank


def decay_weight(end_time: str | None, now: str, half_life_days: float) -> float:
    """``0.5 ** (age_days / half_life)`` — recent episodes weigh more."""
    try:
        age = (datetime.fromisoformat(now) - datetime.fromisoformat(end_time)).total_seconds() / 86400.0
    except Exception:
        return 1.0
    age = max(age, 0.0)
    return 0.5 ** (age / half_life_days)


def _deck_observations(episodes, now, half_life_days):
    """Flatten episodes into ``(archetype, deck, band, weight)`` per side."""
    obs = []
    for ep in episodes:
        w = decay_weight(ep.get("end_time"), now, half_life_days)
        band = ep.get("band")
        for side in ("0", "1"):
            arch = ep.get("arch" + side)
            if arch:
                obs.append((arch, ep.get("deck" + side) or [], band, w))
    return obs


def _band_balanced_priors(obs) -> dict[str, float]:
    """Per-band recency-weighted play rate, averaged across bands, then normalized."""
    band_arch: dict = defaultdict(lambda: defaultdict(float))
    band_total: dict = defaultdict(float)
    archetypes = set()
    for arch, _deck, band, w in obs:
        band_arch[band][arch] += w
        band_total[band] += w
        archetypes.add(arch)

    acc: dict = defaultdict(float)
    for band, arch_w in band_arch.items():
        total = band_total[band] or 1.0
        for arch in archetypes:
            acc[arch] += arch_w.get(arch, 0.0) / total
    nbands = len(band_arch) or 1
    for arch in acc:
        acc[arch] /= nbands

    s = sum(acc.values()) or 1.0
    return {arch: acc[arch] / s for arch in acc}


def _card_inclusion(obs) -> dict[str, dict[int, float]]:
    """Per archetype, the recency-weighted fraction of its decks containing each card."""
    arch_total: dict = defaultdict(float)
    arch_card: dict = defaultdict(lambda: defaultdict(float))
    for arch, deck, _band, w in obs:
        arch_total[arch] += w
        for c in set(deck):
            arch_card[arch][c] += w
    return {arch: {c: arch_card[arch][c] / arch_total[arch] for c in arch_card[arch]}
            for arch in arch_card}


def _background(obs) -> dict[int, float]:
    """Recency-weighted fraction of *all* decks containing each card."""
    total = 0.0
    card: dict = defaultdict(float)
    for _arch, deck, _band, w in obs:
        total += w
        for c in set(deck):
            card[c] += w
    return {c: card[c] / total for c in card} if total else {}


def _matchups(episodes, now, half_life_days, *, marginal_prior, pair_prior, mean=0.5):
    """Recency-weighted win-rate per archetype and per ordered matchup.

    Each *decisive* episode (``winner_index`` 0/1; draws and unknowns excluded)
    contributes to both sides. Marginals shrink toward ``mean`` (=0.5) and each pairwise
    cell shrinks toward its archetype marginal, so a 1-game record reads near-neutral,
    not 100%. Bands are pooled on purpose: win-rate is a ratio, so an over-sampled band
    doesn't bias it the way it biases play-rate (hence no band-balancing here).
    """
    m_win: dict = defaultdict(float)   # weighted wins, per archetype
    m_dec: dict = defaultdict(float)   # weighted decisive games, per archetype
    p_win: dict = defaultdict(float)   # weighted wins, per (archetype, opponent)
    p_dec: dict = defaultdict(float)   # weighted decisive games, per (archetype, opponent)
    for ep in episodes:
        wi = ep.get("winner_index")
        a0, a1 = ep.get("arch0"), ep.get("arch1")
        if wi is None or not a0 or not a1:
            continue
        w = decay_weight(ep.get("end_time"), now, half_life_days)
        for me, opp, idx in ((a0, a1, 0), (a1, a0, 1)):
            win = w if wi == idx else 0.0
            m_win[me] += win
            m_dec[me] += w
            p_win[(me, opp)] += win
            p_dec[(me, opp)] += w

    marginal = {a: (m_win[a] + marginal_prior * mean) / (m_dec[a] + marginal_prior)
                for a in m_dec}
    out: dict = {}
    for a in marginal:
        vs = {opp: {"win_rate": round((p_win[(me, opp)] + pair_prior * marginal[a])
                                      / (dec + pair_prior), 4),
                    "n": round(dec, 3)}
              for (me, opp), dec in p_dec.items() if me == a}
        out[a] = {"win_rate": round(marginal[a], 4), "n": round(m_dec[a], 3), "vs": vs}
    return out


def _signatures(incl_arch, background, *, min_inclusion, min_lift, top) -> list[dict]:
    """High-lift cards: common in this archetype, rare elsewhere."""
    out = []
    for c, p in incl_arch.items():
        bg = background.get(c, 0.0)
        lift = p / bg if bg > 0 else float("inf")
        if p >= min_inclusion and lift >= min_lift:
            out.append({"cardId": c, "lift": lift})
    out.sort(key=lambda s: s["lift"], reverse=True)
    return out[:top]


def _representative_build(arch_obs) -> list[int]:
    """The recency-weighted most-common decklist among an archetype's deck observations."""
    weight: dict = defaultdict(float)
    sample: dict = {}
    for _arch, deck, _band, w in arch_obs:
        key = tuple(sorted(deck))
        weight[key] += w
        sample[key] = deck
    if not weight:
        return []
    best = max(weight, key=lambda k: weight[k])
    return list(sample[best])


def _dossier_intel(build, cards):
    """Evolution lines, threats (attackers) and targets (roles) for a build."""
    lines = evolution_lines(Counter(build), cards)
    evo_lines = [sorted(ln.members, key=lambda c: stage_rank(cards.get(c, {}))) for ln in lines]

    attackers = sorted(
        ((c, cards.get(c, {}).get("maxDamage", 0)) for c in set(build) if is_attacker(cards.get(c, {}))),
        key=lambda x: x[1], reverse=True,
    )
    threats = [{"cardId": c, "role": "attacker"} for c, _ in attackers[:6]]

    targets: list[dict] = []
    seen: set[int] = set()
    for ln in lines:
        for c in ln.members:
            if c != ln.top_id and c not in seen:
                targets.append({"cardId": c, "role": "fragile_preevo"})
                seen.add(c)
        if is_exclass(cards.get(ln.top_id, {})) and ln.top_id not in seen:
            targets.append({"cardId": ln.top_id, "role": "prize_liability"})
            seen.add(ln.top_id)
    for c in set(build):
        name = cards.get(c, {}).get("name", "")
        if name and is_engine(name) and c not in seen:
            targets.append({"cardId": c, "role": "engine"})
            seen.add(c)

    return evo_lines, threats, targets


def compile_artifact(episodes, cards, *, now: str, half_life_days: float = 21.0,
                     min_episodes: int = 1, signature_min_inclusion: float = 0.4,
                     signature_min_lift: float = 1.5, signature_top: int = 8,
                     matchup_marginal_prior: float = 2.0,
                     matchup_pair_prior: float = 4.0) -> dict:
    """Compile episodes + card metadata into the artifact dict."""
    if len(episodes) < min_episodes:
        raise ValueError(f"refusing to compile: {len(episodes)} < min_episodes={min_episodes}")

    obs = _deck_observations(episodes, now, half_life_days)
    priors = _band_balanced_priors(obs)
    inclusion = _card_inclusion(obs)
    background = _background(obs)
    matchups = _matchups(episodes, now, half_life_days,
                         marginal_prior=matchup_marginal_prior, pair_prior=matchup_pair_prior)

    dossiers = {}
    for arch in inclusion:
        arch_obs = [o for o in obs if o[0] == arch]
        build = _representative_build(arch_obs)
        evo_lines, threats, targets = _dossier_intel(build, cards)
        mu = matchups.get(arch) or {"win_rate": 0.5, "n": 0.0, "vs": {}}
        dossiers[arch] = {
            "card_inclusion": inclusion[arch],
            "signatures": _signatures(inclusion[arch], background,
                                      min_inclusion=signature_min_inclusion,
                                      min_lift=signature_min_lift, top=signature_top),
            "representative_build": build,
            "evolution_lines": evo_lines,
            "threats": threats,
            "targets": targets,
            "win_rate": mu["win_rate"],   # marginal, recency-weighted, shrunk toward 0.5
            "win_n": mu["n"],             # weighted decisive games (reliability)
            "matchups": mu["vs"],         # {opponent archetype: {win_rate, n}}
        }

    return {
        "meta": {"schema_version": 2, "compiled_at": now,
                 "episode_count": len(episodes), "half_life_days": half_life_days},
        "priors": priors,
        "background": background,
        "dossiers": dossiers,
    }
