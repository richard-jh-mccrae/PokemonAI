"""The rollout LEAF: what a candidate turn's END state is worth.

One engine-backed term (`KO_SCORE x state_value`, ADR-0092) plus the closed-form account: survival, threat,
development, and the line's own spend. `turn_value = leaf(end) - sum(spend)` — a development that consumed a one-shot
is not free just because the end board looks the same."""
from __future__ import annotations


from common import needs
from common.state_model import StateModel
from common.strategy.context import KO_SCORE
from common.strategy.planning.readiness import _READINESS_CAP
from common.strategy.planning.turn_line import _prune_none


# Leaf-eval term weights (ADR-0031 decision 4). Prizes KO_SCORE-weighted + DOMINANT — positional terms
# sum below one prize, never outrank real KO (hard-rung invariant, decision 3). Automatic Value Model (ADR-0007) replaces later.
_PLANNER_SURVIVAL_W = 50.0     # my Active survives predicted Incoming after the line (full turn)

_PLANNER_THREAT_W = 0.1        # per-point value of threat magnitude removed by the KO …

_PLANNER_THREAT_CAP = 100.0    # … capped, so a big threat still can't rival a prize

_PLANNER_DEV_W = 1.0           # development left on my end-of-turn board (engine-rank phase: bodies

_PLANNER_DEV_CAP = 100.0       # + attached Energy, `_board_development`) … capped below a prize

_PLANNER_VALUE_W = 80.0        # Tier-5 (ADR-0042): the Automatic Value Model's P(win) on the simmed
                               # end-of-turn board scales into a sub-prize band (< one KO_SCORE), so
                               # the learned leaf breaks prize-EQUAL ties, never overriding a prize

_LINE_CAP = 100.0             # the line account's POSITIVE contribution is capped here so the hard-rung
                              # invariant holds strictly: max positional (readiness 300 + survival 50 +
                              # threat 100 + value 40 + line 100) = 590 < 1000 = KO_SCORE, so no path term
                              # can lift a positional board over a real prize. The NEGATIVE side (a spend
                              # penalty) is uncapped — it only ever LOWERS a value, never inverts a prize.

_CLASS_B_SPEND_IDS = frozenset({   # the "spend account" rules (t0-planner-disposition.md Decision 1): a
    # NEGATIVE tuned weight whose referent is the SPEND of a scarce resource (a wasted Ultra Ball /
    # `discard_eot` Energy / the one-per-turn Supporter slot / a held gust/heal) — invisible on the end
    # board (spent cards don't show; hand hidden) and legitimately additive along the line (pure spends
    # don't double-count state). REUSED from the live tuned weight set (`OptionTrace.fired`), never
    # re-derived. `turn_value = readiness(end) − Σ spend_costs(line)`.
    # SCOPE, since the stale-membership audit below had to establish it anyway: `_line_account`'s only
    # callers are inside `_simulate_line`, which POC-T4/5 retired as a RUNTIME rollout and kept as the
    # OFFLINE engine primitive the instruments drive. So this account prices no shipped decision today
    # — which is a reason to keep it honest, not a licence to let it rot.
    # NB the five `discard_eot` burst rungs that used to lead this list are DELETED (ADR-0069 §7).
    # Their referent — spending a one-shot Energy that buys nothing — is now the decider's
    # EVAPORATION LOSS, carried on `OptionTrace.attach_spend` and added below, so the account keeps
    # the signal without keeping the weight coincidences.
    # ⚠️ Thirteen dead members were dropped by PR #448, and they did NOT leave together: six went at
    # POC-T4/5, three in merges from 2026-07-18/19/27, and four were never ids at all (stems whose real
    # rungs carried `-dont-shuffle` / `-at-discard`). A member no Strategy ships can never reach
    # `OptionTrace.fired`, so the set read at three times its true size for weeks, costing nothing and
    # showing nothing. `tests/strategy/test_rung_id_literals_are_live.py` is the interlock.
    "dont-rush-evolve-without-target", "dont-refresh-into-a-probable-miss",
    "dont-lunar-cycle-away-the-last-attachable-f", "dont-search-an-empty-deck",
    "dont-search-a-probable-whiff",
})

_ABILITY_FIRE_IDS = frozenset({    # the "ability-readiness co-equal — fire it = value" rules
    # (t0-planner-disposition.md class A): a POSITIVE tuned weight whose referent is the ACTION of USING a
    # beneficial setup Ability (draw/dig/accel) — Lunatone's Lunar Cycle draw-3, Drakloak's Recon Directive.
    # Its value (the CARDS drawn) is a future resource the end board can't show; the greedy continuation
    # converges the boards, so the leaf can't see the draw. Credited POSITIVELY along the simmed line
    # (symmetric to the spend account), REUSED from the live tuned weight set — never re-derived.
    # `advance-the-accel-pieces` / `feed-the-firing-accelerator` are DELETED (ADR-0069 §7) and are
    # deliberately NOT re-routed: their referent was the ATTACH side of acceleration, whose value is
    # now the decider's `accel_value` — forward build the end board DOES show (Energy landing on
    # bench bodies), so crediting it here as well would double-count. `use-acceleration` survives and
    # keeps the PLAY-side credit, which the end board genuinely cannot show.
    # `use-the-draw-engine-ability` left with the SEQUENCING cluster at POC-T4/5 (Issue #386) — see
    # the ⚠️ on `_CLASS_B_SPEND_IDS` above for why an unshipped member is inert rather than wrong,
    # and `baseline/__init__.py` for where its claim went (the composer scores the dig's successor
    # states, so the draw is priced by the board it reaches rather than credited flat here).
    "fire-lunar-cycle", "lunar-cycle-the-weak-preevo-last-f",
    "use-acceleration", "bench-the-comeback-drawer",
})


class LeafValueMixin:
    """The end-of-turn value a candidate line is ranked by."""

    # ---- leaf evaluation (ADR-0031 decision 4): scalar over the resulting end-of-turn board ---------
    def _leaf_value(self, *, prizes: float, active_survives: bool, threat_removed: float = 0.0,
                    development: float = 0.0, value: float = 0.0, readiness: float = 0.0,
                    line: float = 0.0) -> float:
        """The leaf-eval scalar over a resulting board: prizes taken (dominant, KO_SCORE-weighted) +
        the threat removed + my Active's survival vs Incoming + MY-side ``readiness`` (the board-state
        value function, `_readiness`; 0 for closed-form candidates) + the signed ``line`` account (the path
        term of `turn_value = readiness(end) + Σ ability-fire credits − Σ spend costs`, `_line_account`;
        0 off the engine-sim path) + the Base Automatic Value Model's re-centred P(win) (``value ∈ [-0.5,
        0.5]``, Tier-5/ADR-0042; 0 when off/absent). The legacy ``development`` term (`_board_development`)
        is retained for back-compat (default 0) — the engine-sim leaf now feeds ``readiness`` instead. EVERY
        positional term is capped and their capped sum stays below one prize, so a bigger KO always ranks
        first — a positional score can NEVER outrank a real prize (the hard-rung invariant, ADR-0031
        decision 3). The learned term REFINES; it never overrides a sound rung. ``line`` is a pure path
        term (additive, no state double-count — its referent is the ACTION taken, not the resulting board)."""
        return (KO_SCORE * prizes
                + min(_PLANNER_THREAT_CAP, _PLANNER_THREAT_W * threat_removed)
                + (_PLANNER_SURVIVAL_W if active_survives else 0.0)
                + min(_PLANNER_DEV_CAP, _PLANNER_DEV_W * development)
                + min(_READINESS_CAP, readiness)
                + _PLANNER_VALUE_W * value
                + min(_LINE_CAP, line))

    def _survives_after_ko(self, my_id, my_hp, opp_player) -> bool:
        """True if my body (``my_id`` at ``my_hp``) survives the opponent's Incoming AFTER I KO their
        Active this turn — their best affordable REMAINING attacker (a benched body they promote) can't
        KO it. The 1-ply survival term for the leaf-eval (ADR-0031 decision 2); the opponent's Active is
        excluded because the line Knocks it Out. False when my HP is unknown."""
        bench = (opp_player or {}).get("bench") or []
        return bool(my_hp) and self._incoming_worst(my_id, my_hp, bench) < my_hp

    def _incoming_worst(self, my_id, my_hp: int, opp_bodies) -> int:
        """The worst Weakness/Resistance-adjusted damage the opponent's affordable attackers among
        ``opp_bodies`` could deal to my body next turn — the closed-form **Incoming** (CONTEXT.md).
        A thin adapter over ``CombatMath.reachable_incoming`` (ADR-0064): the reachability read now
        counts each body's CURRENT form AND one reachable EVOLUTION hop (their promote→evolve→attach→
        attack development step), not just the current body. Still an upper-bound (a form's biggest
        attack is credited once it can pay its cheapest, worst-case), so a survival check stays
        conservative. The energy policy is the per-decision budget (``_incoming_budget``): ``None``
        → worst-case ceiling (unmatched Read); a charged dict → per-attack typed affordability under
        the matched-Read burst budget. 0 when unknown."""
        my_stat = self.stats.get(my_id) if (self.stats and my_id is not None) else None
        if not (my_stat and my_hp):                       # unknown my card → no claim (contract-preserving)
            return 0
        model = self._state_model
        if model is None:
            return 0                                      # no snapshot → no claim, as above
        # AREA-AT-DAMAGE-TIME (ADR-0070 §9): ACTIVE, declared explicitly. `_survives_after_ko` asks
        # about the body that will be Active AFTER my line resolves — the lethal tiers promote a
        # benched body before it swings — so its CURRENT board area is irrelevant here. Inferring the
        # area from the board would hand those bodies bench immunity and manufacture phantom lethals.
        #
        # Off the SNAPSHOT (POC-T1), with `bodies=` naming the post-line opponent side (the caller
        # excludes the Active my line Knocks Out) and the threaded `_incoming_budget` as the policy.
        return int(model.theirs.reachable_incoming(
            {"id": my_id, "hp": my_hp}, bodies=opp_bodies,
            context=self._opp_attack_context, my_benched=False))

    def _threat_magnitude(self, opp) -> float:
        """The threat magnitude of the opponent's Active — its biggest printed attack — as the
        ``threat_removed`` term when a line KOs it. A coarse "how dangerous was the body I removed"
        signal; 0 when unknown."""
        stat = self.stats.get((opp or {}).get("id")) if (self.stats and opp) else None
        return float(getattr(stat, "maxDamage", 0) or 0) if stat else 0.0

    def _my_player(self, obs) -> dict:
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        return players[yi] if 0 <= yi < len(players) and players[yi] else {}

    def _opp_player(self, obs) -> dict:
        state = obs.get("current") or {}
        players = state.get("players") or []
        oi = 1 - state.get("yourIndex", 0)
        return players[oi] if 0 <= oi < len(players) and players[oi] else {}

    def _leaf_state_model(self, end, my_index: int):
        """The simulated end-of-turn board, as a :class:`StateModel` for `state_value` to score.

        The engine hands back an observation-shaped dict, which is exactly what `StateModel.build`
        takes, so this is a construction rather than a translation — no second reading of the board
        is created and nothing here re-derives a fact the snapshot already owns.

        Three suppliers are threaded because `state_value`'s families genuinely need them and the
        model is the only route to them (the sole-supplier ruling): ``deck`` for the Count Triple and
        the evolution topology, ``role_worth`` for the deck-DECLARED Roles that `readiness` and
        `development` weigh by (Roles are declaration, not card data), and ``needs`` for the
        assignment the `hand` family's `set_keep_v2` spine reads. ``needs`` resolves LAZILY — the
        model invokes the callable only if some family asks — so a leaf that never reaches the hand
        term pays nothing for the DP, which is the whole point of ADR-0068's laziness.

        ``my_index`` is passed explicitly rather than left to ``yourIndex``: the simulated board is
        handed back from whichever seat the sim ended on, and reading the wrong side would score the
        opponent's position and rank every candidate backwards.

        ``turn_boosts`` is DELIBERATELY not threaded, and this says so because the omission looks
        exactly like the bug it is not (Issue #282). `StateModel.build` takes the match-scoped
        `TurnBoostTracker` and the Pilot's live per-decision snapshot passes it; this board is
        different in kind. `_simulate_line` stops when the select passes to the opponent, so ``end``
        is MY END-OF-TURN board — and a flat Trainer boost is *"During this turn"*
        (`data/EN_Card_Data.csv`, Premium Power Pro / Black Belt's Training), so by then it has
        expired. Handing the live tracker over would inject a dead boost into the context that
        `state_value`'s `threat` reads, over-claiming a Knock Out I could not actually take next
        turn — the one direction an offensive gate must not fail in. The boost's real value is
        already in this board: the sim CASHED it, so the prize it bought is in ``prize_race``. The
        Tool half is different again and needs no thread — an attached Tool is visible board state
        and `_SideBase.damage_boosts` reads it straight off the holder."""
        return StateModel.build(
            end, combat=self.combat, my_index=my_index, deck=self.deck,
            role_worth=self._role_value,
            # The BOUND METHOD, not a closure over ``end`` (Issue #400 Phase 2). `StateModel.build`
            # binds a board-bound supplier to the observation it is building, so a hypothetical
            # reached through `rebuilt` resolves its OWN hand instead of inheriting this one's — the
            # staleness that made `state_value`'s `hand` family constant across a whole
            # `composer.compose` call and priced a fetch at exactly 0.0.
            needs=self._leaf_needs_resolution)

    def _leaf_needs_resolution(self, end, my_index: int):
        """The `needs.Resolution` for a simulated end board's HAND, or None when there is no hand to
        resolve.

        The sim only injects my hand when the hand-value plumbing is on, and a board without one
        cannot be asked what its hand covers — so this returns None and `state_value`'s `hand` family
        prices a REAL zero (no cards, no coverage) rather than a hidden one. Never raises: a
        featurize slip must not crash ranking, exactly as the retired `pilot._hand_readiness`
        established (POC-T4/5 deleted that term; the never-raises contract outlived it).

        `include_general=False` keeps the LATENT worth out of the assignment and hands it over as
        `latent_worth` instead, because the two enter `hand` as separate legs and letting the general
        slot carry it as well would price one card twice — this module's headline rule, one seam
        over.

        **The live `_state_model` is saved and restored around the hypothetical build (POC-T4/5,
        Issue #386), and this is the ONE place that requirement belongs.** `_board_hypothetical`
        reaches `_snapshot`, which *builds and STASHES* the per-decision model — deliberate for a
        caller that wants to evaluate against the hypothetical board, and correct for every caller
        this method had before the composer was armed, all of which ran under `_planning` with the
        live readers stood down. This one does not: `state_value`'s `hand` family calls it through
        `needs` during a LIVE decision, three times on an ordinary board, and without the restore
        every later reader of `self._state_model` in the same `explain()` sees the HYPOTHETICAL
        end-of-turn board.

        The damage was silent and specific. `_attach_value` reads `self._state_model.mine`; against
        the leaked leaf model `_attach_body_view` returned None, `can_attack_tonight` went False,
        and a one-shot Energy that unlocks a 210-damage attack THIS TURN read as evaporating for
        nothing — `this_turn` 90.0 -> 0.0, marginal +90.0 -> -30.0, with nothing about the attach
        changed. A snapshot taken as a side effect of building a Board is safe only while nobody
        builds a Board speculatively. The composer does, constantly."""
        cur = (end or {}).get("current") or {}
        players = cur.get("players") or []
        me = players[my_index] if 0 <= my_index < len(players) and players[my_index] else {}
        if not me.get("hand"):
            return None
        mobs = {**end, "current": {**cur, "yourIndex": my_index}}
        live_model = getattr(self, "_state_model", None)
        try:
            board = self._board_hypothetical(mobs)
            rows = self._needs_hand_rows(mobs, board)
            if not rows:
                return None
            slots, elig = self._resolve_needs(mobs, board, rows, include_general=False)
            # Deferred import: `_GENERAL_WORTH_W` lives in `common.pilot`, which imports THIS
            # module, so a top-level import would be a cycle. Function-local rather than a second
            # copy of the constant — a hand-kept duplicate is the drift ADR-0087 charges for.
            from common.pilot import _GENERAL_WORTH_W
            covered = {i for i, e in enumerate(elig) if e}
            latent = sum(_GENERAL_WORTH_W * self._role_value(r["cid"])
                         for i, r in enumerate(rows) if i not in covered)
            return needs.Resolution(slots=tuple(slots), eligibility=tuple(elig),
                                    resupply=tuple([0.0] * len(slots)),
                                    hand_ids=tuple(r["cid"] for r in rows),
                                    latent_worth=float(latent))
        except Exception:
            return None
        finally:
            # Restore unconditionally: the early `return None` paths above build a Board too.
            self._state_model = live_model

    def _board_hypothetical(self, obs):
        """Build a :class:`Board` on a HYPOTHETICAL obs (a simmed end-of-turn board) for FEATURES
        only, without letting it pollute the live turn-scoped memory.

        Passing the **Carried State** snapshot is what guarantees that (ADR-0068 decision 2): the
        phase hysteresis and path stickiness are read from the snapshot and their new values
        discarded, so the build cannot write them at all. This replaced a hand-written
        snapshot-and-restore around the call — a guard every future hypothetical-build site would
        otherwise have had to remember, and the third copy of which this phase declined to write.

        **What it does NOT guard is the `_state_model` stash**, and that matters since POC-T4/5.
        `_board` reaches `_snapshot`, whose job is to *build AND STASH* the per-decision model onto
        `self._state_model`. Callers that build a hypothetical board and then evaluate something
        AGAINST it depend on exactly that (`tests/strategy/test_hand_size_relief.py` is the clearest
        example), so the stash is deliberate here and stays. The caller that must NOT leak is
        `_leaf_needs_resolution`, which runs inside a LIVE decision — it does the save/restore
        itself, where the requirement actually lives."""
        return self._board(obs, (obs or {}).get("select"), carried=self.carried())

    def _line_account(self, traces, indices) -> float:
        """The SIGNED path term of `turn_value = readiness(end) + Σ ability-fire credits − Σ spend costs`
        (t0-planner-disposition.md Decision 1) for the CHOSEN options at ONE step: the POSITIVE weight of
        every `_ABILITY_FIRE_IDS` rule that fired (using a beneficial setup Ability — value the end board
        can't show) MINUS the magnitude of every NEGATIVE `_CLASS_B_SPEND_IDS` rule that fired (consuming a
        scarce resource — spent cards don't show, hand hidden). REUSES the LIVE tuned weights
        (`OptionTrace.fired` carries the effective weight); never re-derived, never a score of the resulting
        BOARD (the classification guard against state-summing drift — the referent is always the ACTION)."""
        total = 0.0
        for i in indices:
            if not (0 <= i < len(traces)):
                continue
            for h, w in (getattr(traces[i], "fired", None) or ()):
                hid = getattr(h, "id", None)
                if w > 0 and hid in _ABILITY_FIRE_IDS:
                    total += w
                elif w < 0 and hid in _CLASS_B_SPEND_IDS:
                    total += w                            # w is negative — a spend subtracts
            total += getattr(traces[i], "attach_spend", 0.0) or 0.0   # the burst evaporation loss
        return total

    def _simulate_line(self, obs, first_step, max_steps: int = 40, *, opponent_reply: bool = False):
        """Forward-simulate a candidate line through the Engine Search to my end-of-turn board.

        **No production caller — the RUNTIME ROLLOUT ROLE is retired** (POC-T4/5, Issue #386;
        Issue #263 § *Parity + retirement*). Nothing in a live decision sims a line any more: the
        develop rollout, `_commit_best`'s engine ranking and `_engine_leaf_value` are all deleted, and
        ranking end states is the composer's job, done closed-form off `apply_option`. What survives
        here is the OFFLINE engine forward-sim primitive its instruments still drive —
        `tools/train/family_diag.py`'s per-family attribution, the cgpy↔native agreement lane
        (`tests/strategy/test_engine_agreement_engine.py`) and the determinism backstop — because
        those measure the ENGINE, not the retired rung. The `_search_api` seam it reads is preserved
        by name for the same reason plus `fate()`'s ENGINE-RESOLVED route.

        **Issue #178's ``stream`` half is DELETED with its only reader.** `_develop_rollout_line`
        read it to refuse an unreproducible ranking outright (all-or-nothing); with no rung ranking
        sim values, a bit that exists to demote one has nothing to demote, and an unread bit is the
        kind of forward contract ADR-0102 stopped accepting. ``coins`` stays — it is the
        *is this line RNG-free* fact the win rung's own verdict driver speaks in
        (`_rng_probe(prize=False)`, preserved by name).

        Steps ``first_step``, then re-runs my own closed-form policy (``decide``) on each
        intermediate SearchState until my turn ends (the select passes to the opponent) or the game
        finishes — the ADR-0031 "re-running the policy on each intermediate SearchState." Returns
        ``(end_obs_dict, my_index, start_prizes, result)`` or **None** when the search is unavailable,
        the observation carries no ``search_begin_input``, or anything errors (the caller falls back to
        the closed-form value — never crashes). The 5th tuple element is the SIGNED ``line`` account (the
        path term of `turn_value = readiness(end) + Σ ability-fire credits − Σ spend costs`): the net
        `_line_account` over MY chosen actions along the line — the first step plus every greedy
        continuation step. Opponent-reply steps (Tier-6) never contribute.

        With ``opponent_reply=True`` (Tier-6, ADR-0043) the sim does NOT stop at my turn end: it keeps
        stepping through the OPPONENT's turn using our own policy as the reply proxy, until it is my
        turn again or the game finishes — so the returned board is the start of MY next turn, seeing
        the opponent's best (proxy) answer. Every step decrements the per-move ``_search_steps``
        budget; the sim halts when it is spent (returns the board reached so far).

        Heuristic, not sound (ADR-0031): coins auto-resolve (``manual_coin=False``) and the opponent's
        hidden zones are predicted from my own deck list, so the end-of-turn board is trusted for
        ranking, not as a guarantee. The live game is untouched (the search forks an independent sim).
        Lazy DLL import keeps the fast unit suite from ever loading the native engine.

        The 6th tuple element is ``coins`` — a ``LogType.COIN`` flip appeared along the line
        (``manual_coin=False`` auto-resolves them), measured on the logs by `_rng_probe`. Absent
        under a backend that emits no logs, where behavior is unchanged.

        The measurement the deleted ``stream`` bit was minted for is kept on the record because it
        is the reason no rung may rank a sim value again: on ml f24 (2026-07-27, Issue #178) all 13
        candidate first actions carried ``SHUFFLE`` + ``DRAW`` and **not one COIN**, and each one's
        leaf value swung across processes — 7000 / 162 / 129 / 122 / 89 / 57.5 on the same first
        step. A shuffle-riding sim returns one SAMPLE, not a distribution."""
        if not (obs or {}).get("search_begin_input") or not first_step:
            return None
        cgapi = getattr(self, "_search_api", None)     # injectable search backend (leaf-lab harness sets
        if cgapi is None:                              # cgpy's `cg.api`-shaped surface to re-score tagged
            try:                                       # correction boards offline); production uses native
                from cg import api as cgapi
            except Exception:
                return None
        from dataclasses import asdict
        cur = obs.get("current") or {}
        my_index = cur.get("yourIndex", 0)
        players = cur.get("players") or []
        me = players[my_index] if 0 <= my_index < len(players) and players[my_index] else {}
        opp = players[1 - my_index] if 0 <= 1 - my_index < len(players) and players[1 - my_index] else {}
        start_prizes = len(me.get("prize") or [])
        yd, yp, od, op_, oh = self._seed_zones(obs, me, opp)   # ADR-0050: exact own split when anchored

        def budget_ok() -> bool:
            if not opponent_reply:
                return True                            # Tier-1 sims are unbudgeted (the original path)
            self._search_steps = getattr(self, "_search_steps", 0) + 1
            return self._search_steps <= self.search_budget

        self._planning = True                          # never nest a search inside the reply policy
        line_val = 0.0
        try:
            root = self._evaluate(obs, carried=self.carried())   # the root re-score reads the phase/
            line_val += self._line_account(root.options,         # path memories from the Carried
                                           list(first_step))     # State snapshot and writes neither,
                                                                 # so the live turn is untouched by
                                                                 # construction (ADR-0068) — this was
                                                                 # a hand-written save/restore pair
            ob = cgapi.to_observation_class(obs)
            st = cgapi.search_begin(ob, yd, yp, od, op_, oh, [], manual_coin=False)
            st = cgapi.search_step(st.searchId, list(first_step))
            crossed_my_turn_end = False
            # WP-N5b/N5d: the end obs is OPPONENT-perspective (my turn passed), so my hand is hidden.
            # To let the leaf value it, capture a HELD-CONTEXT snapshot from the
            # LAST my-perspective step — the hand, plus the turn facts the N5d deployability
            # counterfactual read: the attach/Supporter quotas, my bodies
            # with their fresh `appearThisTurn` bits (the end board may reset them), bench fullness.
            # Injected into the end obs (the `heldCtx` private key beside the injected `hand`).
            # Seeded from the live start-of-turn state (fallback if the turn ends before any
            # my-select). v1 caveat: the capture is BEFORE my final action, so it is one action
            # stale.
            #
            # Gated — off = the sim is byte-identical.
            #
            # **POC-T3 (Issue #262) tried arming this unconditionally and MEASURED it worse.**
            # `state_value`'s `hand` family has no data without this capture, and a family that can
            # never receive data is the silent-zero the registry exists to prevent — so arming it
            # looked obviously right. It is not, and the reason is the v1 caveat two lines up: the
            # snapshot is taken BEFORE my final action, so it is one action stale, and *how* stale
            # differs per branch (a line that ends the turn at once captures its start-of-turn hand;
            # a line that plays three cards captures the hand after two). Fed into the one family
            # whose whole job is pricing what leaving my hand COSTS, that made a branch which SPENT a
            # card score a HIGHER hand value than one that spent nothing — 83686860|1|decision|13,
            # hand +0.586 for the play against +0.442 for End. The Discrimination Gate agreed:
            # 104 unruled OK->MISS armed against 67 unarmed.
            #
            # Fixing it properly needs a snapshot at the TRUE end of my turn, which this loop cannot
            # take: the end observation is opponent-perspective, so my hand is hidden by then. That
            # is a substrate gap, not a tuning choice. So the capture stays off, `hand` prices a
            # REAL zero on the leaf path (no hand on the board, no coverage), and the gap is NAMED in
            # `state_value.REGISTRY`'s `hand.blind_to` where Issue #263 reads it as a blind spot
            # rather than discovering it as a mystery. Old Issue #145's grill item 3
            # (*"`leaf_hand_value` fate"*) therefore stays open, with a measurement attached.
            capture_hand = getattr(self, "leaf_hand_value", False)

            def _held_snapshot(player: dict, current: dict):
                if not player.get("hand"):
                    return None
                return {"hand": player["hand"],
                        "supporterPlayed": bool(current.get("supporterPlayed")),
                        "energyAttached": bool(current.get("energyAttached")),
                        "bodies": (player.get("active") or []) + (player.get("bench") or []),
                        "benchFull": len([b for b in (player.get("bench") or []) if b])
                                     >= (player.get("benchMax") or 5)}

            my_ctx = _held_snapshot(me, cur) if capture_hand else None
            coin_t = getattr(getattr(cgapi, "LogType", None), "COIN", None)

            def _saw_coin(ob) -> bool:
                return coin_t is not None and any(getattr(lg, "type", None) == coin_t
                                                  for lg in (getattr(ob, "logs", None) or ()))

            coins = False
            for _ in range(max_steps):
                o = st.observation
                coins = coins or _saw_coin(o)
                c = o.current
                if c is None or c.result != -1 or o.select is None:
                    break                                 # game over
                mine = c.yourIndex == my_index
                if not mine and not opponent_reply:
                    break                                 # Tier-1: stop at my turn end
                if not mine:
                    crossed_my_turn_end = True             # into the opponent's reply now
                elif crossed_my_turn_end:
                    break                                 # back to MY next turn — the depth-2 leaf
                if not budget_ok():
                    break                                 # per-move engine budget spent
                odict = _prune_none(asdict(o))
                if capture_hand and mine and not crossed_my_turn_end:
                    pcur = odict.get("current") or {}
                    ph = pcur.get("players") or []
                    meh = ph[my_index] if 0 <= my_index < len(ph) and ph[my_index] else {}
                    my_ctx = _held_snapshot(meh, pcur) or my_ctx
                dec = self._evaluate(odict)
                if mine and not crossed_my_turn_end:       # only MY within-turn actions carry a line term
                    line_val += self._line_account(dec.options, dec.chosen)
                st = cgapi.search_step(st.searchId, list(dec.chosen))
            coins = coins or _saw_coin(st.observation)       # the final step's logs (a coin-won attack)
            end = _prune_none(asdict(st.observation))
            if capture_hand and my_ctx:                   # inject my hidden hand + held-context
                epl = (end.get("current") or {}).get("players") or []
                if 0 <= my_index < len(epl) and isinstance(epl[my_index], dict):
                    epl[my_index]["hand"] = my_ctx["hand"]
                    epl[my_index]["heldCtx"] = {k: v for k, v in my_ctx.items() if k != "hand"}
            result = st.observation.current.result if st.observation.current else -1
            cgapi.search_end()
            return (end, my_index, start_prizes, result, line_val, coins)
        except Exception:
            try:
                cgapi.search_end()
            except Exception:
                pass
            return None
        finally:
            self._planning = False

    def _role_value(self, cid) -> float:
        """WP6/WP7: card ``cid``'s base worth = the MAX claim over its declared / derived Roles
        (`_roles_of` + the line-member derivation below), its behavioural tags (`TAG_TIER` — the
        worth-coverage fix for situational Trainers/special Energy), and the energy / ACE-SPEC
        fallbacks. Delegates to `card_worth.role_value` (ADR-0065) — the ONE currency zone; the Pilot
        only supplies facts.

        **Line-member worth derivation (Round 9 'derive first'; the discard-shadow finding on
        86091435-68).** A non-payoff win-condition Line member (`_line_preevo_set`: Dreepy AND the
        middle Drakloak on Dreepy→Drakloak→Dragapult ex) is worth its `win_condition_base` tier even
        when the deck declared only the base — a Line stage is a plan piece, not junk. WORTH-ONLY: the
        Line-membership fact enters the value currency here but NOT `_roles_of` / `c.roles`. That
        separation outlived its original reason — it kept the tuned discard ladder's routing intact
        across the seam-D migration, and Issue #261 item 2h deleted that ladder — but it stands on its
        own: worth is what a card is WORTH, and `c.roles` is what the deck DECLARED, and a derived
        Line membership is the first and not the second."""
        from common.card_worth import role_value
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        roles = self._roles_of(cid)
        if cid is not None and cid in self._line_preevo_set():
            roles = [*roles, "win_condition_base"]      # derived worth only — not injected into c.roles
        return role_value(
            roles,
            is_ace_spec=bool(st is not None and getattr(st, "aceSpec", False)),
            is_typed_basic_energy=bool(st is not None and getattr(st, "is_typed_basic_energy", False)),
            tags=self.functions.tags(cid) if (self.functions and cid is not None) else ())

    def _keep_cost(self, cid, counts: dict, pool: int, draws: int, board=None,
                   shuffled_copies: int = 1, prizes_hidden: int = 0, deck_count=None) -> float:
        """WP6/WP7: the cost of shuffling ONE held copy of card ``cid`` away = its role worth × how
        UN-recoverable it is (``1 − P(re-draw or re-fetch it in `draws`)`` over the shuffle-grown
        ``pool``, +``shuffled_copies`` outs for the held copies rejoining the deck — 1 for a lone copy;
        a hand-wide summation passes the full duplicate count, `_hand_keep`) × how realisable its role
        is by its deadline (`_deploy_odds`, the gate library — ADR-0065: an undeployable evolution or
        a dead fetcher collapses to 0, shed freely). ``board`` supplies the gate facts; omitted → the
        deadline factor stays 1.0.

        PRE-ANCHOR (``prizes_hidden`` > 0, ``counts`` = the unseen composition): the re-access odds
        are PRIZE-SPLIT-WEIGHTED (`_prize_split_hit`) — the unseen outs split over deck + face-down
        prizes exactly like the gamble's GAIN side, while the shuffled held copies join the pool as
        ``certain`` outs (a hand card is never prize-assignable). Without the weighting the cost side
        counted possibly-prized outs at full strength against a prize-free pool — re-access
        overestimated, keep under-charged, a pre-anchor pro-gamble bias the gain side never had.
        Anchored (``prizes_hidden`` = 0): the plain window draw, unchanged."""
        role_value = self._role_value(cid)
        if role_value <= 0:
            return 0.0
        from common import gate_library
        from common.card_worth import keep_cost
        from common.deck_odds import draw_hit_probability
        outs = self._card_reaccess_outs(cid, counts)
        certain = max(1, shuffled_copies)
        if prizes_hidden > 0:
            d = deck_count if deck_count is not None else max(0, sum(counts.values()) - prizes_hidden)
            reaccess = self._prize_split_hit(outs, d, prizes_hidden, pool, draws, certain=certain)
        else:
            reaccess = draw_hit_probability(outs + certain, pool, draws)
        # The pressure gate (Round 8 §3, the CLOSING edge): a doom-answering card's re-access is not
        # bankable against its deadline — the credit zeroes and the card charges full worth.
        reaccess = gate_library.closing_gate_reaccess(
            reaccess, gate_closing=self._gate_closing(cid, board) if board is not None else False)
        deadline = self._deploy_odds(cid, board, counts) if board is not None else 1.0
        return keep_cost(role_value, reaccess, deadline)

    def _gate_closing(self, cid, board) -> bool:
        """The closing-edge resolver (Round 8 §3: a closing gate SPIKES keep — re-access is not
        bankable against a THIS-TURN deadline, so the card charges full worth). Two closing edges:

        **Deploy-now (ep86091435 f68):** ``cid`` is a hand evolution with an ELIGIBLE in-play base
        this turn (`Board.deploy_now_ids`) — evolving is a live tempo play; pitching/shuffling it
        forfeits the play and re-access can't help (you need it NOW). Fires regardless of doom, and
        REGARDLESS of a same-card copy in play (the benched copy does not cover THIS body's
        evolution — the covered-vs-open discrimination a flat floor misses, ep83686860 f18 keeps
        pitching correctly because its base was placed this turn, so it is NOT in ``deploy_now_ids``).

        **Pressure (the fold of `hold-successor-when-doomed`, ep83037962 f49):** the Active is DOOMED
        and ``cid`` ANSWERS the doom — the SUCCESSOR (a win-condition with a Line pre-evolution in
        play) or an emergency `clutch_heal` / `switch`. Sound facts only; a healthy board with no
        deploy-now keeps the closure discount, so cycling stays free."""
        if cid is not None and cid in getattr(board, "deploy_now_ids", frozenset()):
            return True
        if not getattr(board, "active_doomed", False):
            return False
        if cid in self._wincon_set() and getattr(board, "line_preevo_in_play", False):
            return True
        tags = self.functions.tags(cid) if self.functions else ()
        return "clutch_heal" in tags or "switch" in tags

    def _hand_keep(self, hand_ids, played_cid, counts: dict, pool: int, draws: int, board=None,
                   prizes_hidden: int = 0, deck_count=None) -> float:
        """Σ keep_cost over the hand a refresh shuffles away — the ONE summation BOTH keep-value sites
        read (the WP6 gamble keep-floor below and the refresh SHED, `pilot._refresh_shed_keepcost`), so
        the graded floor is identical by construction. ``hand_ids`` is the hand as a LIST — duplicate
        copies are real cards. The played refresh ``played_cid`` is excluded ONCE (it is discarded, not
        shuffled; a second held copy still shuffles and still charges). Duplicates price MARGINALLY
        (sets-not-sums, spec §Round 7): all k held copies of a card land in the deck together, so each
        copy's re-access odds count all k shuffled siblings as outs — the k-th duplicate is discounted
        by the copies shuffled with it, neither k independent one-ofs (the pre-reconciliation gamble
        over-charge) nor free riders (the pre-reconciliation SHED's frozenset dedup). Pre-anchor,
        ``prizes_hidden`` / ``deck_count`` thread the prize-split weighting into each copy's re-access
        odds (`_keep_cost`); anchored callers pass ``prizes_hidden=0``.

        The QUOTA GATE (spec Round 8 §2, `gate_library.quota_window`): duplicate copies of a
        once-per-turn card (Energy — the manual attach; Supporter — the slot, rules.md §3) charge by
        RANK — the j-th copy's deadline sits j−1 turns away (+1 when this turn's quota is spent:
        `energy_attached`; `supporter_played` or the played refresh itself being a Supporter), and
        each intervening turn widens its re-access window by the natural draw. Rank 1 with the quota
        live is the plain window; non-quota cards keep the uniform marginal price."""
        ids = list(hand_ids)
        if played_cid in ids:
            ids.remove(played_cid)
        from collections import Counter
        from common import gate_library
        played_st = self.stats.get(played_cid) if (self.stats and played_cid is not None) else None
        sup_spent = bool(getattr(board, "supporter_played", False)
                         or (played_st is not None and getattr(played_st, "is_supporter", False)))
        total = 0.0
        for cid, k in Counter(ids).items():
            st = self.stats.get(cid) if self.stats else None
            if st is not None and getattr(st, "is_energy", False):
                spent = bool(getattr(board, "energy_attached", False))
            elif st is not None and getattr(st, "is_supporter", False):
                spent = sup_spent
            else:
                total += k * self._keep_cost(cid, counts, pool, draws, board, shuffled_copies=k,
                                             prizes_hidden=prizes_hidden, deck_count=deck_count)
                continue
            total += sum(self._keep_cost(cid, counts, pool,
                                         gate_library.quota_window(draws, j, quota_spent=spent),
                                         board, shuffled_copies=k,
                                         prizes_hidden=prizes_hidden, deck_count=deck_count)
                         for j in range(1, k + 1))
        return total
