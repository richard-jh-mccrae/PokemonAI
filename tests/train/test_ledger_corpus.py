"""The dashboard's arithmetic: agreement per deck, gaps per affected decision, regressions."""
from __future__ import annotations

from types import SimpleNamespace

from train.ledger_corpus import _satisfies_human, payload, render_markdown


def row(deck, row_id, *, agrees, graded=True, gaps=(), chosen=(0,), correct=(1,)):
    return {"deck": deck, "key": f"1-{row_id}", "id": row_id, "scope": "decision",
            "context": "Main", "category": "test", "graded": graded,
            "chosen": list(chosen), "correct": list(correct) if graded else [],
            "exact": False, "agrees": agrees if graded else None,
            "chosen_label": "a", "correct_label": "b", "rationale": "why",
            "gaps": list(gaps), "elapsed_seconds": 0.1,
            "ledger": {"value": 0.0, "backend": "ledger", "weights": "w",
                       "prices": [{"action": "x", "selection": [0], "swing": -0.2,
                                   "ends_turn": False}]}}


def test_payload_reports_per_deck_agreement_and_the_generality_floor():
    rows = [row("a_deck", "r1", agrees=True), row("a_deck", "r2", agrees=True),
            row("b_deck", "r3", agrees=True), row("b_deck", "r4", agrees=False),
            row("b_deck", "r5", agrees=None, graded=False)]
    result = payload(rows)
    assert result["decks"]["a_deck"]["agreement"] == 1.0
    assert result["decks"]["b_deck"]["agreement"] == 0.5
    assert result["decks"]["b_deck"]["ungraded"] == 1
    assert result["generality_floor"] == 0.5


def test_gap_census_counts_decisions_affected_not_mentions():
    rows = [row("a_deck", "r1", agrees=True, gaps=["unknown card 5", "no formula for x"]),
            row("a_deck", "r2", agrees=True, gaps=["unknown card 5"]),
            row("a_deck", "r3", agrees=True)]
    result = payload(rows)
    assert result["decks"]["a_deck"]["gap_census"] == {"unknown card 5": 2,
                                                       "no formula for x": 1}
    # One decision with two gap kinds is ONE affected decision, not two.
    assert result["decks"]["a_deck"]["gap_decisions"] == 2


def test_any_recorded_alternative_ruling_satisfies():
    """Frames like 6154988eb489 rule several picks equally correct; grading only the primary
    `correct` list was mis-reporting the alternatives as misses."""
    from common.option_equivalence import option_equivalence

    correction = SimpleNamespace(correct=[0], correct_alternatives=[[1], [6]])
    options = [{"type": 7, "index": index} for index in range(8)]
    equivalence = option_equivalence(options, {"current": {"players": []}})
    assert _satisfies_human([0], correction, equivalence)
    assert _satisfies_human([6], correction, equivalence)
    assert not _satisfies_human([3], correction, equivalence)


def test_regressions_name_frames_that_used_to_agree():
    baseline = payload([row("a_deck", "r1", agrees=True), row("a_deck", "r2", agrees=False)])
    result = payload([row("a_deck", "r1", agrees=False), row("a_deck", "r2", agrees=False)],
                     baseline=baseline)
    assert result["regressions"] == ["r1"]


def test_markdown_render_carries_the_rationale_beside_the_miss():
    rendered = render_markdown(payload([row("a_deck", "r1", agrees=False)]))
    assert "rationale: why" in rendered
    assert "priced -0.2000 x" in rendered
    assert "Generality floor" in rendered


def test_the_real_producer_feeds_the_dashboard_shape():
    """Every other test here builds rows with the `row()` fixture, a hand-maintained mirror of
    `_replay_one`'s output — the check-the-serializer trap. This replays ONE real correction
    frame through the real producer (fresh runtime, live Ledger brain, cgpy previews) and runs
    the result through payload + render_markdown, so a shape drift between the producer and
    the consumers fails here instead of shipping silently."""
    from pathlib import Path

    from train.blunder.store import load_corrections
    from train.ledger_corpus import _replay_one

    store = (Path(__file__).resolve().parents[2] / "data" / "corrections"
             / "mega_starmie_20260813_c9991b12")
    frame = next(record for record in load_corrections(store)
                 if record.obs is not None
                 and (record.obs.get("select") or {}).get("context") == 0
                 and int((record.obs.get("current") or {}).get("turn", 0)) > 0)
    produced = _replay_one("mega_starmie", frame)

    assert produced["backend"] == "ledger"      # the live brain answered, not a fallback
    fixture_keys = set(row("a_deck", "r1", agrees=True)) - {"ledger"}
    assert fixture_keys <= set(produced), fixture_keys - set(produced)
    if "ledger" in produced:                    # misses carry the price breakdown
        assert set(row("a_deck", "r1", agrees=True)["ledger"]) <= set(produced["ledger"])

    rendered = render_markdown(payload([produced]))
    assert "Generality floor" in rendered


def _archived_frame(deck_dir="mega_starmie_20260813_c9991b12"):
    from pathlib import Path

    from train.blunder.store import load_corrections

    store = Path(__file__).resolve().parents[2] / "data" / "corrections" / deck_dir
    return next(record for record in load_corrections(store)
                if record.obs is not None
                and record.obs.get("own_prizes") is None
                and int((record.obs.get("current") or {}).get("turn", 0)) > 0)


def _deck(deck_name="mega_starmie"):
    from pathlib import Path

    path = (Path(__file__).resolve().parents[2] / "src" / "agents" / deck_name / "deck.csv")
    return tuple(int(value) for value in path.read_text().splitlines() if value.strip())


def test_stamping_prizes_makes_deck_knowledge_exact():
    """An archived frame with no own-prize anchor overcounts the deck by exactly the prize
    count; stamping restores the live shell's information state (deck total == deckCount)."""
    from common.board import BoardState
    from common.engine import stamp_own_prizes

    frame = _archived_frame()
    deck = _deck()
    obs = frame.obs
    current = obs["current"]
    me = current["players"][int(current.get("yourIndex") or 0)]
    prize_count = len(me.get("prize") or ())
    assert prize_count > 0

    before = BoardState.root(obs, decklist=deck)
    before_pool = dict(before.deck_counts or ())
    assert sum(before_pool.values()) == int(me["deckCount"]) + prize_count

    assert stamp_own_prizes(obs, deck) is True
    after = BoardState.root(obs, decklist=deck)
    assert sum(count for _, count in after.own_prizes) == prize_count
    assert sum(count for _, count in after.deck_counts) == int(me["deckCount"])
    # The stamp only names cards that were actually in the unseen pool.
    for card_id, count in after.own_prizes:
        assert before_pool.get(card_id, 0) >= count


def test_stamping_respects_an_existing_anchor():
    from common.engine import stamp_own_prizes

    frame = _archived_frame()
    obs = frame.obs
    assert stamp_own_prizes(obs, _deck()) is True
    anchored = obs["own_prizes"]
    assert stamp_own_prizes(obs, _deck()) is False       # second call must not re-roll
    assert obs["own_prizes"] is anchored


def test_retired_rulings_are_listed_not_graded():
    """A ruling dispositioned in reviewed.json leaves the graded pool and shows in its own
    dashboard section — grading it would score the brain against a retired verdict."""
    retired = [{"deck": "a_deck", "key": "1-9", "id": "r9",
                "disposition": "refuted", "round": "2026-07-13"}]
    result = payload([row("a_deck", "r1", agrees=True)], retired=retired)
    assert result["decks"]["a_deck"]["retired"] == 1
    assert result["decks"]["a_deck"]["graded"] == 1      # the retired frame is not in rows
    rendered = render_markdown(result)
    assert "Retired rulings (1)" in rendered
    assert "refuted" in rendered


def test_sweep_partitions_reviewed_before_replaying(monkeypatch):
    """sweep() must consult reviewed.json: a dispositioned key never reaches _replay_one."""
    from types import SimpleNamespace

    import train.ledger_corpus as module

    def correction(episode, frame, agent="a_deck"):
        return SimpleNamespace(id=f"{episode}-{frame}", episode_id=episode, agent=agent,
                               obs={"current": {}}, scope="decision",
                               decision={"frame": frame}, correct=[0],
                               correct_alternatives=(), category="test", rationale="")

    kept, dropped = correction("ep", 1), correction("ep", 2)
    monkeypatch.setattr(module, "load_corrections", lambda store: [kept, dropped])
    monkeypatch.setattr(module, "_replay_one",
                        lambda deck, c, overrides=None: row(deck, c.id, agrees=True))
    reviewed = {"ep-2": {"disposition": "covered", "round": "2026-07-01"}}
    result = module.sweep(store="unused", decks=("a_deck",), reviewed=reviewed)
    assert [r["id"] for r in result["rows"]] == ["ep-1"]
    assert [r["id"] for r in result["retired"]] == ["ep-2"]


def test_damage_targets_are_priced_with_engine_facts():
    """Frame 82749168-50, a Damage-context menu with a free 50 HP KO: a bare provider prices
    every target zero (ADR-0148); with fact sources passed through, the ruled snipe wins."""
    from pathlib import Path

    from train.blunder.store import load_corrections
    from train.ledger_corpus import _replay_one

    store = (Path(__file__).resolve().parents[2] / "data" / "corrections"
             / "mega_starmie_20260630_b7e483a")
    frame = next(record for record in load_corrections(store)
                 if record.obs is not None and str(record.episode_id) == "82749168"
                 and int((record.decision or {}).get("frame", -1)) == 50)
    produced = _replay_one("mega_starmie", frame)
    assert produced["backend"] == "ledger"
    assert produced["agrees"] is True


def test_a_crashed_decision_is_surfaced_even_when_it_agrees():
    """A dead brain that happened to pick the ruled action must show as a CRASH in the
    human-facing dashboard, never as a quiet success."""
    crashed = row("a_deck", "r1", agrees=True)
    crashed["backend"] = "last-resort-fallback"
    crashed["fallback"] = {"cause": "exception:ValueError",
                           "error": {"type": "ValueError", "message": "boom"}}
    result = payload([crashed, row("a_deck", "r2", agrees=True)])
    assert result["decks"]["a_deck"]["fallbacks"] == 1
    rendered = render_markdown(result)
    assert "Crashed decisions (1)" in rendered
    assert "exception:ValueError" in rendered and "boom" in rendered


def test_the_started_twin_wins_the_attach_on_both_re_ruled_frames():
    """The 2026-08-20 sitting's twin-attach frames (83116501-89 re-ruled to [5], 82752045-97
    to [4]): with rental energy priced dead on the bench (ADR-0150), the basic-{W}-to-the-
    started-body ruling wins at default weights."""
    from train.ledger_corpus import _replay_one

    for store_dir, episode, frame_no in (
            ("mega_starmie_20260701_fa8f649", "83116501", 89),
            ("mega_starmie_20260630_b7e483a", "82752045", 97)):
        from pathlib import Path

        from train.blunder.store import load_corrections

        store = Path(__file__).resolve().parents[2] / "data" / "corrections" / store_dir
        record = next(r for r in load_corrections(store)
                      if str(r.episode_id) == episode
                      and int((r.decision or {}).get("frame", -1)) == frame_no)
        produced = _replay_one("mega_starmie", record)
        assert produced["backend"] == "ledger"
        assert produced["agrees"] is True, (episode, frame_no, produced["chosen_label"])
