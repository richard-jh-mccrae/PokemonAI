"""The small shared reads every family makes: this option's Pokemon, my Active, a card's `AttackStat`, the damage
context.

Nothing here decides anything — they are accessors over the raw observation, kept together so a decider reads a fact
instead of re-walking the state dict for it."""
from __future__ import annotations


from common.state_model import MySide, TheirSide
from common.strategy.context import _DECK, _HAND, _LOOKING, _PLAY, _ZONE
from common.strategy.damage_context import damage_context as _assemble_damage_context



class ViewsMixin:
    """Accessors over the raw observation dict, shared by every decision family."""

    def _option_pokemon(self, obs: dict, select: dict, option: dict) -> dict | None:
        """The board card/Pokémon dict an option's (area, index, playerIndex) points at, or None.
        AreaType -> zone via ``_ZONE`` (2=hand, 3=discard, 4=active, 5=bench); the owner defaults to
        me. A play-from-hand option (OptionType PLAY) carries only a bare hand `index` (no `area`),
        so it resolves against the hand — without this every Trainer/Pokémon play would have no card
        id, and so no roles/tags/stat, silently disabling every such Hypothesis on plays. A DECK
        search option (TO_HAND/ToField etc.) carries `area=DECK`, but the deck is hidden from the
        player zones — its revealed candidates live in the select's own ``deck`` list, so resolve
        there (this is what lets a 'fetch the win-condition' Hypothesis see a search's targets)."""
        area, index = option.get("area"), option.get("index")
        if area is None and option.get("type") == _PLAY:
            area = _HAND
        if area is None or index is None:
            return None
        if area == _DECK:                                  # search candidates revealed on the select
            deck = (select or {}).get("deck") or []
            return deck[index] if 0 <= index < len(deck) else None
        state = obs.get("current") or {}
        if area == _LOOKING:                               # a face-up reveal (Pokégear/search top-N):
            looking = state.get("looking") or []           # candidates live in current.looking, not a
            return looking[index] if 0 <= index < len(looking) else None   # player zone (None = facedown)
        players = state.get("players") or []
        pi = option.get("playerIndex", state.get("yourIndex", 0))
        if not (0 <= pi < len(players)) or players[pi] is None:
            return None
        cards = players[pi].get(_ZONE.get(area))
        if not cards or not (0 <= index < len(cards)) or cards[index] is None:
            return None
        return cards[index]

    def _option_card_id(self, obs: dict, select: dict, option: dict) -> int | None:
        poke = self._option_pokemon(obs, select, option)
        return poke.get("id") if poke else None

    def _my_active(self, obs: dict) -> dict | None:
        """My Active Pokémon dict (mirror of `_opp_active`)."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        if not (0 <= yi < len(players)) or players[yi] is None:
            return None
        actives = players[yi].get("active") or []
        return actives[0] if actives and actives[0] else None

    def _my_active_id(self, obs: dict) -> int | None:
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        if not (0 <= yi < len(players)) or players[yi] is None:
            return None
        actives = players[yi].get("active") or []
        return actives[0].get("id") if actives and actives[0] else None

    def _opp_active(self, obs: dict) -> dict | None:
        state = obs.get("current") or {}
        players = state.get("players") or []
        oi = 1 - state.get("yourIndex", 0)
        if not (0 <= oi < len(players)) or players[oi] is None:
            return None
        actives = players[oi].get("active") or []
        return actives[0] if actives else None

    def _my_bench_raws(self, obs: dict) -> list:
        """MY benched bodies' raw dicts — the Bench Harvest's input, from the SNAPSHOT when one is
        built (ADR-0068 keeps it lazy and pure, so the bench cannot shift under a memoized clock) and
        off the observation otherwise."""
        if self._state_model is not None:
            return list(self._state_model.mine.bench_raws)
        return [p for p in ((self._my_player(obs) or {}).get("bench") or []) if p]

    def _my_in_play_raws(self, obs: dict) -> list:
        """Every in-play body on MY side, Active first — the board scope a BOARD-LEVEL grant reads."""
        me = self._my_player(obs) or {}
        return [p for p in ((me.get("active") or []) + (me.get("bench") or [])) if p]

    def _stat_of(self, card_id):
        """This card's ``CardStat``, or None — the provider read as a CALLABLE, which is the shape
        `common.retreat_cost` takes so a `StateModel` (whose accessor is `card_stat()`, not a
        mapping) can supply the same card knowledge the Pilot does."""
        return self.stats.get(card_id) if self.stats else None

    def _attack_stat(self, attack_id):
        """The attack's ``AttackStat`` (ADR-0032) — the KO oracle's provider read (ADR-0056/0052).
        None for an unknown attack or a stat-blind Pilot (no record, no damage)."""
        return self.combat.attack_stat(attack_id)

    def _attack_cost(self, attack_id, default=99):
        """The attack's Energy count off the ONE record; ``default`` carries the caller's
        epistemics (99 fail-closed / 0 tiebreak-neutral / None identity-compare)."""
        return self.combat.attack_cost(attack_id, default)

    def _attack_damage(self, attack_id) -> int:
        return self.combat.attack_damage(attack_id)

    def _hand_count_of(self, obs: dict, card_id) -> int:
        """Copies of `card_id` in MY hand (the stacking read for a Power-Pro-class crossing)."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        return sum(1 for c in (me.get("hand") or []) if c and c.get("id") == card_id)

    def predicted_damage(self, attacker_id: int | None, attack_id, defender: dict | None, *,
                         bound: str = "exact", context: dict | None = None) -> float:
        """The damage oracle (ADR-0032 E1) — delegates to the KO oracle (`CombatMath`, ADR-0052),
        the one closed-form combat home."""
        return self.combat.predicted_damage(attacker_id, attack_id, defender,
                                            bound=bound, context=context)

    def _predicted_max_damage(self, attacker_stat, defender: dict | None, *,
                              exclude_attack=None) -> float:
        """The worst damage `attacker_stat`'s attacks deal to `defender` (Incoming's magnitude) —
        the KO oracle's `predicted_max_damage`, handed the per-decision opponent context this
        Pilot stashes (`_opp_attack_context`, set by `_board`)."""
        return self.combat.predicted_max_damage(
            attacker_stat, defender, exclude_attack=exclude_attack,
            context=self._opp_attack_context)

    def _damage_context(self, obs: dict, *, attacker_is_me: bool = True) -> dict:
        """Visible-state counts for the oracle's scaling term (ADR-0032 Damage Formula),
        ATTACKER-relative: ``attacker_is_me=True`` prices MY attack this decision;
        ``False`` mirrors every key for the opponent-as-attacker (the Incoming direction —
        their hand/bench/Active-Energy AND their discard, all open information). Includes the
        attacker's discard Energy histograms (Riptide-class scalers).

        **The assembly is no longer here** (POC-T3.5, Issue #279). This method used to BE the
        builder — the only full construction of the context anywhere — and POC-T3.5 needed a second
        one on the StateModel, because ``state_value(model)`` may read nothing but the model
        (the sole-supplier ruling — `docs/plans/value-system-poc-plan.md` §4-T0, restated on
        `state_value`) and so cannot be handed a context threaded down from here. Two
        hand-rolled builders of one fact is the exact defect ``CombatMath.card_level_damage`` was
        extracted to end (*"One fact, two hand-rolled call sites, free to drift — and they did"*),
        so the shape moved out rather than being copied: the per-side countables are gathered by
        ``_SideBase.damage_facts`` and assembled by ``common.strategy.damage_context``, and
        ``test_damage_context`` pins this method and :meth:`StateModel.damage_context` key-for-key on
        corpus frames.

        What remains here is the ADAPTER: which raw player dict is whose, which side plays the
        attacker's role, and the two per-decision facts a board snapshot cannot recover on its own —
        the tracked this-turn damage-boost PLAYS (a log fact; the played card is in the discard by
        the time anyone reads the board) and the deck tracker's anchored resolution of my deck.

        The two side views are built here rather than read off ``self._state_model``, and that is a
        SEQUENCING fact rather than a preference: ``_board`` resolves the opponent-as-attacker
        context before the snapshot exists, because the snapshot's own ``TheirSide`` takes the Read's
        clock policy as a constructor argument and the Read is resolved further down. Constructing a
        side is free (every field is lazy, ADR-0068), so the adapter pays for the fields it reads and
        nothing else.
        """
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        prizes = obs.get("own_prizes")             # exact prize multiset from deck-tracker, or None
        if prizes:                                 # keys are card ids: coerce str->int so a
            prizes = {int(k): v for k, v in prizes.items()}    # JSON-captured obs matches the deck
        # `own_prizes` is the ONE anchor MySide needs for the exact deck facts the hidden
        # deck-discard scalers read (only MY deck can be exact): the model derives the pair itself
        # from it (`MySide._deck_facts`, Issue #297), where the tracker's answer used to be threaded
        # in beside it. `damage_context` reads the pair off the ATTACKER alone and drops the
        # defender's, so the derivation is wasted work on the defending side — but it is one lazy
        # Counter walk behind `damage_facts`, and paying it is what removes the second supplier.
        mine = MySide(me, combat=self.combat, deck=self.deck, own_prizes=prizes,
                      turn_boosts=self._turn_boosts.boosts_for(yi))
        theirs = TheirSide(opp, combat=self.combat,
                           turn_boosts=self._turn_boosts.boosts_for(1 - yi))
        atk, dfn = (mine, theirs) if attacker_is_me else (theirs, mine)
        return _assemble_damage_context(atk.damage_facts, dfn.damage_facts)

    def _my_damage_context(self, obs: dict) -> dict:
        """MY-attacker Damage Formula context for THIS decision, built at most once.

        The missing mirror of `_opp_attack_context`, which `_board` has cached per decision since
        ADR-0032 P1 for exactly this reason. My own direction had no such home, so the three
        per-OPTION consumers rebuilt it — once per ATTACK option on the menu, plus once per
        boost-card option — each getting a fresh, identical dict. That was already waste; POC-T3.5
        (Issue #279) made it worth removing by routing the gather through the model's lazy typed
        side views, which pay descriptor overhead the old raw-dict walk did not.

        **Measured** over mega_starmie's 140 committed correction frames, this tree vs `main`: the
        builder itself **0.019 → 0.084 ms/call**, one `Board` build (which calls it once, for the
        OPPONENT direction) **2.07 → 2.22 ms/decision (+7%)**, and the whole `explain()` decision
        path **5.31 → 5.33 ms** — inside run-to-run noise (the unchanged tree spread 5.05–5.71 ms
        over three passes). Without this cache the same `explain()` measured ~5.65 ms, so collapsing
        the per-option rebuilds is what keeps the extraction free where it is actually paid for.

        A **freshly-allocated dict per call is also the wrong thing to hand downstream**, which is
        the substrate's own argument one layer down: every clock read that prices a scaler carries
        the context in its memo key, and a new object cannot hit the memo the previous one filled.

        Keyed by the observation's IDENTITY and sound *because the entry holds the obs*: a cached
        object cannot be collected, so its address cannot be reused under a live entry — the same
        argument `_Lazily._key` makes for its own projection cache. A hypothetical board (a planner
        leaf, a re-scored root) is a different obs and rebuilds; the model's purity contract
        (ADR-0068) is what says the observation does not change under a snapshot.

        **The obs is not the whole key**, and the second half is a sequencing fact rather than a
        proof: the context also reads `_turn_boosts`, which is match-scoped mutable state. It is
        safe because `_evaluate` consumes the log stream ONCE, before `_board`, so the tracker
        cannot move between two reads within a decision — and because a planner leaf runs with
        `_planning` set, which suppresses `observe` outright (the engine-sim future must never
        mutate match state). Anything that later observes mid-decision must invalidate here too.
        """
        if self._my_attack_context_obs is not obs:
            self._my_attack_context_obs, self._my_attack_context = obs, self._damage_context(obs)
        return self._my_attack_context

    def _discard_energy_counts(self, discard: list) -> tuple[int, dict]:
        """Energy histograms of a (fully visible) discard pile: ``(all Energy cards,
        {energyType: Basic-Energy count})`` — the units behind the Riptide-class discard scalers.
        Resolved via CardStat.cardType (BASIC_ENERGY=5, SPECIAL_ENERGY=6); unknown cards count 0."""
        total, by_type = 0, {}
        for c in discard:
            cid = (c or {}).get("id")
            st = self.stats.get(cid) if (self.stats and cid is not None) else None
            if st is not None and st.is_energy:           # any Energy card
                total += 1
            if st is not None and st.is_typed_basic_energy:   # Basic Energy, by type
                by_type[st.energyType] = by_type.get(st.energyType, 0) + 1
        return total, by_type
