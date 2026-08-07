"""One candidate builder per KO SHAPE: evolve into it, Rare Candy into it, pump it, gust to it, retreat into it, tutor
for it, heal through it.

Each returns the same candidate record, so `_best_gamble_line` ranks shapes against each other rather than preferring
whichever it checked first."""
from __future__ import annotations


from common.strategy.context import KO_SCORE
from common.strategy.planning.turn_line import _composed_rank



class KoClassMixin:
    """Per-shape KO candidates, in one comparable form."""

    def _gamble_ko_classes(self, board, stat, ma, opp, hp: int, counts: dict, hand: list,
                           discard_basic_types: set):
        """The KO-enabling **Outcome Classes** of a refresh draw: for each of my Active's attacks
        exactly ONE Energy short whose damage fells the opponent's Active, the class of draws whose
        entry points ASSEMBLE a Basic Energy filling the missing slot (its specific type, or any Basic
        for a colourless slot). Entry points = the literal Basic Energy copies PLUS the **fetch-closure
        outs** (WP1): a drawable card with a `basic_energy` FETCH clause (`card_effects.json`, read by
        `_fetch_reaches_slot`) whose target is still reachable — a whole-deck search (Energy Search /
        Fighting Gong {F}-locked / Energy Search Pro) with a matching Basic still in deck, or a recycle
        (Night Stretcher / Energy Retrieval / Max Rod) with a matching Basic in the visible discard.
        Returns ``[(copies, ko_value, label, sought_ids, (sup_copies, sup_ids)), …]`` — ``sought_ids``
        = the deck card ids that ARE the always-live outs (literal ∪ Item closure); the 5th slot is the
        **post-Item-refresh Supporter supplement** (Hilda / Crispin / the Petrel 2-hop,
        `_supporter_energy_tutor_reaches`), counted by the pricing loop ONLY when the refresh being
        priced is an ITEM (Unfair Stamp) and the Supporter slot is unspent — after a Supporter refresh
        the slot is spent and a drawn Supporter tutor is dead (spec §Missing, the 4-of-5 rule). An
        enabler already in HAND — a held Basic, a held fetch Item that reaches the slot, or (slot
        unspent) a held Supporter tutor that reaches it — voids the class (no gamble needed; playing it
        is the deterministic line). Errs by UNDER-counting the outs only (an endorser)."""
        out = []
        attached = self._attached_type_counts(ma)
        hand_ids = [c.get("id") for c in hand]
        for aid in (stat.attacks or ()):
            cost = self._attack_cost(aid)
            if cost != board.my_active_energy + 1:            # exactly one attach short
                continue
            if self.predicted_damage(board.my_active_id, aid, opp) < hp:
                continue
            ast = self._attack_stat(aid)
            types = getattr(ast, "energyTypes", ()) if ast else ()
            from collections import Counter
            need = Counter(t for t in types if t not in (0, None))
            deficit = {t: n - attached.get(t, 0) for t, n in need.items() if n - attached.get(t, 0) > 0}
            if sum(deficit.values()) > 1:
                continue                                      # more than one specific slot short
            want = next(iter(deficit), None)                  # None -> the short slot is colourless

            def _enables(cid) -> bool:
                est = self.stats.get(cid) if self.stats else None
                if not est or est.is_pokemon:
                    return False
                if not est.is_basic_energy:
                    return False                              # Basics only (a special Energy pays
                et = getattr(est, "energyType", None)         # colourless slots — under-counted, safe)
                return (et == want) if want is not None else True
            if any(_enables(cid) for cid in hand_ids):
                continue                                      # hand already holds the Basic enabler
            if any(self._fetch_reaches_slot(want, cid, counts, discard_basic_types)
                   for cid in hand_ids):                      # …or a held fetch card that reaches it:
                continue                                      # deterministic tutor line — no gamble needed
            if not board.supporter_played and any(
                    self._supporter_energy_tutor_reaches(cid, want, counts, discard_basic_types)
                    for cid in hand_ids):                     # a held Supporter tutor + a live slot is
                continue                                      # the deterministic line too (play it now)
            out_ids = {cid for cid, n in counts.items() if n > 0 and _enables(cid)}   # literal Basics
            for tid, n in counts.items():                     # WP1 closure entry points (fetch clauses)
                if n > 0 and tid not in out_ids and self._fetch_reaches_slot(
                        want, tid, counts, discard_basic_types):
                    out_ids.add(tid)
            sup_ids = sorted(tid for tid, n in counts.items() if n > 0 and tid not in out_ids
                             and self._supporter_energy_tutor_reaches(tid, want, counts,
                                                                      discard_basic_types))
            sought = sorted(out_ids)
            copies = sum(counts[cid] for cid in sought)
            if copies <= 0:
                continue
            label = f"a type-{want} Basic Energy" if want is not None else "any Basic Energy"
            out.append((copies, KO_SCORE + self._prize_value(opp), label, sought,
                        (sum(counts[t] for t in sup_ids), sup_ids)))
        return out

    def _gamble_evolution_ko_classes(self, obs, board, ma, opp, counts: dict, hand: list):
        """WP5: the **evolution-KO** Outcome Class — the highest-value un-built gamble class. Where
        ``_gamble_ko_classes`` prices only the CURRENT Active's attacks, this prices "draw an evolution
        of my (evolution-eligible) Active → evolve it → ITS attack KOs": evolving is legal the same
        turn (Active in play since last turn — `appearThisTurn` False, rules.md §4 L96; turn ≥ 2 is
        already gated upstream), keeps the attached Energy (rules.md §4 L98), and a Mega ex does NOT
        end the turn on evolving (rules.md §4 L103), so the evolved form attacks with the carried Energy
        plus this turn's one attach. Outs = the evolution's deck copies PLUS the Item Pokémon-tutor
        closure that fetches it (Ultra Ball / Poké Pad / Mega Signal). The 5th slot carries the
        **post-Item-refresh Supporter supplement** (Hilda's evolution fetch, Salvatore's rush-evolve,
        the Petrel 2-hop — `_supporter_evolution_tutor_reaches`), counted only when the refresh being
        priced is an ITEM (Unfair Stamp) and the Supporter slot is unspent; after a Supporter refresh
        those tutors are slot-dead. An evolution already in HAND voids the class (the deterministic
        evolve-KO owns it, and puts a KO on the menu → the rung stands down upstream); so does a held
        Supporter evolution-tutor while the slot is unspent. Same 5-tuples; errs by under-counting."""
        if ma.get("appearThisTurn"):                          # placed this turn -> can't evolve (§4 L96)
            return []
        base = self.stats.get(ma.get("id")) if (self.stats and ma.get("id") is not None) else None
        if base is None or not getattr(base, "name", None):
            return []
        energy = board.my_active_energy + 1                   # carried Energy + this turn's one attach
        hand_ids = {c.get("id") for c in hand}
        out = []
        for eid in set(self.deck):                            # DIRECT evolutions of the Active in my deck
            st = self.stats.get(eid) if self.stats else None
            if st is None or getattr(st, "evolvesFrom", None) != base.name:
                continue
            if counts.get(eid, 0) <= 0 or eid in hand_ids:    # none left to draw / in hand (deterministic)
                continue
            if self._best_affordable_ko_value(obs, board, opp, eid, energy, body=ma) <= 0:
                continue                                      # the evolved form doesn't reach a KO
            if not board.supporter_played and any(
                    self._supporter_evolution_tutor_reaches(cid, eid, counts) for cid in hand_ids):
                continue                                      # held Supporter tutor + live slot: det line
            out_ids = {eid}
            for tid, n in counts.items():                     # Item Pokémon-tutor closure (fetch clauses)
                if tid == eid or n <= 0 or tid in hand_ids:
                    continue
                tst = self.stats.get(tid) if self.stats else None
                if tst is None or not getattr(tst, "is_item", False):
                    continue                                  # Supporter tutors join only post-Item-refresh
                if self._fetch_reaches_pokemon(eid, tid, counts):   # honours no-Rule-Box / mega predicate
                    out_ids.add(tid)
            sup_ids = sorted(tid for tid, n in counts.items()
                             if n > 0 and tid != eid and tid not in out_ids and tid not in hand_ids
                             and self._supporter_evolution_tutor_reaches(tid, eid, counts))
            sought = sorted(out_ids)
            copies = sum(counts.get(cid, 0) for cid in sought)
            if copies <= 0:
                continue
            out.append((copies, KO_SCORE + self._prize_value(opp),
                        f"the evolution {st.name}", sought,
                        (sum(counts[t] for t in sup_ids), sup_ids)))
        return out

    def _gamble_pump_ko_classes(self, obs, board, stat, ma, opp, hp: int, counts: dict, hand: list):
        """WP5: the **damage-pump** KO class — my Active's best AFFORDABLE attack (current Energy; the
        boost is the missing piece, not Energy) is short of the KO by ≤ one boost, and drawing a
        ``damageBoost`` Trainer (Premium Power Pro {F}+30 Item; Black Belt's +40-vs-ex Supporter) lifts
        it over. Gates mirror `_boost_lethal_tactical` EXACTLY — the attacker-type gate (``energyType``
        vs ``damageBoostType``, "your {F} Pokémon") and the defender ``{ex}`` gate — so the class never
        over-credits a type-locked pump (provider.py:97-100, VERIFIED parsed). Item boosts are
        always-live outs; Supporter boosts ride the post-Item-refresh supplement (5th slot). A held
        boost that crosses voids the class (the deterministic play-it line). Single-copy only (short by
        ≤ one boost — multi-copy stacking is a deeper hypergeometric, deferred); errs by under-counting."""
        if board.turn <= 1:
            return []
        opp_stat = self.stats.get(opp.get("id")) if (self.stats and opp.get("id") is not None) else None
        ctx = self._damage_context(obs)
        hand_ids = {c.get("id") for c in hand}
        best_dmg = 0
        for aid in (stat.attacks or ()):
            if self._attack_cost(aid) > board.my_active_energy:
                continue                                      # not affordable with current Energy
            dmg = self.predicted_damage(board.my_active_id, aid, opp, context=ctx)
            if dmg >= hp:
                return []                                     # an affordable KO already exists — attack
            best_dmg = max(best_dmg, dmg)
        if best_dmg <= 0:
            return []

        def _crosses(bst) -> bool:
            if bst is None or not getattr(bst, "damageBoost", 0):
                return False
            if bst.damageBoostType is not None and getattr(stat, "energyType", None) != bst.damageBoostType:
                return False                                  # attacker-type gate
            if bst.damageBoostVsEx and not (opp_stat and opp_stat.is_ex_body):
                return False                                  # defender {ex} gate
            if not bst.applies_to_holder(stat):
                return False                                  # the HOLDER gate(s): an owner family
                                                              # ("the Hop's Pokémon this card is
                                                              # attached to", Issue #306) or a
                                                              # no-Rule-Box condition (Brave Bangle,
                                                              # Issue #345). Asked as one test, so a
                                                              # gate added later reaches this site
                                                              # without it being edited — which is
                                                              # exactly what happened at Issue #345.
            return best_dmg < hp <= best_dmg + bst.damageBoost   # short by ≤ this one boost
        if any(_crosses(self.stats.get(cid) if self.stats else None) for cid in hand_ids):
            return []                                         # held boost crosses -> deterministic line
        item_ids = sorted(bid for bid, n in counts.items() if n > 0
                          and getattr(self.stats.get(bid), "is_item", False)
                          and _crosses(self.stats.get(bid)))
        sup_ids = sorted(bid for bid, n in counts.items() if n > 0
                         and getattr(self.stats.get(bid), "is_supporter", False)
                         and _crosses(self.stats.get(bid)))
        if not item_ids and not sup_ids:
            return []
        return [(sum(counts[b] for b in item_ids), KO_SCORE + self._prize_value(opp),
                 "a damage boost for the KO", item_ids,
                 (sum(counts[b] for b in sup_ids), sup_ids))]

    def _gamble_gust_ko_classes(self, obs, board, ma, opp_player, hand: list, counts: dict):
        """WP5: the **gust** KO class — my Active can't KO the current opp Active (else the rung stands
        down upstream), but its affordable attack CAN KO a benched target once that target is dragged
        up (per-target weakness via the shared `_gust_best_ko_prizes` / `_can_ko` oracle). Drawing a
        gust Trainer (Boss's Orders 1182 — a Supporter, so it rides the post-Item-refresh supplement;
        an Item gust would be always-live) enables it. Value = KO_SCORE + the BENCHED target's prize
        (not the current Active's). A held gust that reaches voids the class (the deterministic
        `gust-for-the-ko` line, already a KO on the menu). Errs by under-counting (cheapest-attack KO)."""
        best_prizes = self._gust_best_ko_prizes(ma, opp_player, board.my_active_energy)
        if best_prizes <= 0:
            return []
        hand_ids = {c.get("id") for c in hand}

        def _is_gust_trainer(cid) -> bool:
            st = self.stats.get(cid) if self.stats else None
            return bool(st and (st.is_item or st.is_supporter) and self.functions
                        and "gust" in self.functions.tags(cid))
        if any(_is_gust_trainer(cid) for cid in hand_ids):
            return []                                         # held gust -> deterministic gust-KO line
        item_ids = sorted(bid for bid, n in counts.items() if n > 0 and _is_gust_trainer(bid)
                          and getattr(self.stats.get(bid), "is_item", False))
        sup_ids = sorted(bid for bid, n in counts.items() if n > 0 and _is_gust_trainer(bid)
                         and getattr(self.stats.get(bid), "is_supporter", False))
        if not item_ids and not sup_ids:
            return []
        return [(sum(counts[b] for b in item_ids), KO_SCORE + best_prizes,
                 "a gust for the benched KO", item_ids,
                 (sum(counts[b] for b in sup_ids), sup_ids))]

    def _gamble_survival_classes(self, obs, board, me, counts: dict, hand: list):
        """WP5 (survival): the bench-empty PREDICTED-LOSS class — my Active is doomed (opp KOs it next
        turn, ADR-0064 `active_doomed`) AND my Bench is EMPTY, so a KO of my only Pokémon LOSES the
        game (no Pokémon in play → you lose). Two out families avert it: **bench-fill** — any benchable
        Basic, or Poffin's bench-fill fetch of a ≤70-HP Basic still in deck (a KO is no longer
        game-over); and **heal** — a drawn heal that lifts the Active above the incoming
        (`_heal_averts_doom`, e.g. Wally's on a damaged Mega ex). Value = KO_SCORE (a game loss averted
        is ±KO_SCORE-scale by the loss rung; spec §Round 5), EXEMPT from the keep-value blocker. Item
        outs are always-live; Supporter heals ride the post-Item supplement. A held Basic (bench it) or
        a held heal that averts (play it) voids the class — the deterministic line. Errs by
        under-counting."""
        if not board.active_doomed or any(b for b in (me.get("bench") or [])):
            return []                                         # not doomed, or a bench body already exists

        def _benchable(cid) -> bool:
            st = self.stats.get(cid) if self.stats else None
            return bool(st and st.is_pokemon and not getattr(st, "evolvesFrom", None))
        hand_ids = {c.get("id") for c in hand}
        if any(_benchable(cid) for cid in hand_ids):
            return []                                         # a Basic in hand -> bench it, no gamble
        # bench-fill outs (always-live): benchable Basics + Poffin's fetch of one.
        out_ids = {cid for cid, n in counts.items() if n > 0 and _benchable(cid)}
        for tid, n in counts.items():                         # Poffin: a bench-fill fetch reaching a Basic
            if n > 0 and tid not in out_ids and any(
                    _benchable(bid) and self._fetch_reaches_pokemon(bid, tid, counts) for bid in counts):
                out_ids.add(tid)
        # heal outs: lift the doomed Active above the incoming (Item -> always-live; Supporter -> supp).
        sup_ids: set = set()
        astat = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        ma = next((p for p in (me.get("active") or []) if p), None)
        cur_hp = (ma or {}).get("hp", 0)
        incoming = board.incoming_active_damage
        if incoming and astat and ma and cur_hp < getattr(astat, "hp", 0):   # damage to heal + a threat
            if any(self._heal_averts_doom(cid, astat, cur_hp, incoming) for cid in hand_ids):
                return []                                     # a held heal averts -> deterministic line
            for hid, n in counts.items():
                if n <= 0 or hid in out_ids or not self._heal_averts_doom(hid, astat, cur_hp, incoming):
                    continue
                hst = self.stats.get(hid) if self.stats else None
                (out_ids if getattr(hst, "is_item", False) else sup_ids).add(hid)
        sought = sorted(out_ids)
        sup = sorted(sup_ids)
        copies = sum(counts[cid] for cid in sought)
        sup_copies = sum(counts[s] for s in sup)
        if copies <= 0 and sup_copies <= 0:
            return []
        return [(copies, KO_SCORE, "a Basic or heal to avoid the loss", sought, (sup_copies, sup))]

    def _heal_restriction_ok(self, restriction, astat) -> bool:
        """WP5 survival: can a heal clause with this ``restriction`` target my (doomed) Active
        ``astat``? None / ``active_only`` always can; ``mega_only`` needs a Mega ex; ``psychic_only``
        a {P} body. An unknown restriction fails CLOSED (under-count — the endorser never assumes a
        heal it can't verify reaches my Active).

        The Active-spot reading of :meth:`_heal_restriction_targets`, and byte-identical to it over
        the whole shipped vocabulary — ``active_only`` is exactly the term this method could not
        express, and it is trivially satisfied when the body IS the Active."""
        return self._heal_restriction_targets(restriction, astat, is_active=True)

    def _heal_restriction_targets(self, restriction, stat, *, is_active: bool) -> bool:
        """:meth:`_heal_restriction_ok` asked of ANY of my bodies (Issue #409): can a heal clause
        with this ``restriction`` target the body described by ``stat``, sitting in the Active spot
        or on the Bench?

        ``active_only`` is the whole reason this method exists. It is the one restriction whose
        answer DEPENDS on where the body stands, and the Active-only form had to hardcode it True —
        which is correct for its own caller and would silently offer a benched Cook / Lumiose Galette
        / Jumbo Ice Cream target if reused unchanged. Everything else is a card-fact test that reads
        the same from either area: ``mega_only`` a Mega ex (Wally's Compassion), ``psychic_only`` a
        {P} body (Jacinthe; ``EnergyType.PSYCHIC`` = 5, `cg/api.py`).

        An unknown restriction fails CLOSED, unchanged — the ``active_dragon_only`` (1105 Dragon
        Elixir) and ``arvens_pokemon`` (1130 Arven's Sandwich) strings both land here, and
        `snapshot_coverage.UNCONSUMED_SELECTORS` records the first of them as a known, deliberate
        under-count. Fail-closed is Issue #409 R3's rule at the target select too: a body the term
        cannot price contributes 0.0 rather than a guess."""
        if restriction is None:
            return True
        if restriction == "active_only":
            return is_active
        if restriction == "mega_only":
            return bool(getattr(stat, "megaEx", False))
        if restriction == "psychic_only":
            return getattr(stat, "energyType", None) == 5
        return False

    def _heal_averts_doom(self, cid, astat, cur_hp: int, incoming: int) -> bool:
        """WP5 survival: True iff card ``cid`` has a HEAL clause (`card_effects.json`) that lifts my
        doomed Active from ``cur_hp`` ABOVE the ``incoming`` (so next turn's biggest attack no longer
        KOs it) — ``amount: all`` heals to max HP. Only heals whose restriction can target my Active
        count (`_heal_restriction_ok`); a conditional heal (a `condition` gate) fails closed.

        Issue #349's `each_of` / `amount_per` are deliberately not read, for the reason
        `_heal_candidate`'s docstring gives at length: this asks only what MY ACTIVE ends up on, and a
        per-body distribution gives it the same `amount` a single-target heal would. Reading `each_of`
        as a multiplier would promise a survival the board never delivers; ignoring `amount_per`
        under-counts, which is the direction this method already says it errs in.

        The Active-spot reading of :meth:`_heal_body_averts_doom`."""
        return self._heal_body_averts_doom(cid, astat, is_active=True, cur_hp=cur_hp,
                                           incoming=incoming)

    def _heal_body_averts_doom(self, cid, stat, *, is_active: bool, cur_hp: int,
                               incoming: int, max_hp: int | None = None) -> bool:
        """:meth:`_heal_averts_doom` asked of ANY of my bodies (Issue #409): does a heal clause of
        ``cid`` lift the body described by ``stat`` from ``cur_hp`` ABOVE the ``incoming`` that can
        actually reach it, so the next swing no longer knocks it out?

        This is Issue #409 R2's ``survival_gain`` predicate, and the ``incoming`` a caller hands it
        is what makes it area-correct: for the Active that is the opponent's biggest attack; for a
        BENCHED body it is the snipe/spread reach ONLY (printed damage lands on the Active —
        `CombatMath.form_damage_vs`, ADR-0070 §9), which is usually zero, and a body nobody can hit
        gains nothing from being healed. That asymmetry is derived from a shipped read rather than
        authored, which is why it needs no constant of its own.

        A gated heal (any ``condition``) still can't be promised, unchanged from the Active form —
        this predicate feeds survival claims, and the fail direction it errs in is under-counting.
        Note that is STRICTER than :meth:`_heal_body_candidate`, which evaluates the two
        board-checkable gates; the difference is each caller's own policy and is deliberate.

        ``max_hp`` is the restore ceiling, defaulting to the printed HP — see
        :meth:`_heal_body_candidate` for why a +HP Tool makes that a parameter rather than a read."""
        max_hp = int(max_hp) if max_hp else (getattr(stat, "hp", 0) or 0)
        for cl in (self.effects.clauses(cid) if self.effects else ()):
            if cl.get("kind") != "heal" or cl.get("condition"):
                continue                                      # a gated heal can't be promised
            if not self._heal_restriction_targets(cl.get("restriction"), stat,
                                                  is_active=is_active):
                continue
            amount = cl.get("amount")
            healed = max_hp if amount == "all" else min(max_hp, cur_hp + int(amount or 0))
            if healed > incoming:
                return True
        return False

    def _retreat_snipe_candidate(self, me, others, target_hp: int, extra: int):
        """``active_survives`` (bool) for the best benched body that, once retreated INTO (its Energy
        plus this turn's one attach), affords an attack whose bench-snipe rider KOs the ``target_hp``
        key threat — or None when no benched body reaches one. Among the capable bodies it prefers
        the one that SURVIVES the opponent's remaining Incoming (the sniped threat excluded)."""
        best = None
        for p in (me.get("bench") or []):
            if not p:
                continue
            if not self._affords_snipe_ko(p.get("id"), len(p.get("energies") or []) + extra, target_hp):
                continue
            my_hp = p.get("hp", 0)
            survives = bool(my_hp) and self._incoming_worst(p.get("id"), my_hp, others) < my_hp
            if best is None or survives > best:
                best = survives
        return best

    def _item_evolve_ko_candidate(self, obs, select, board, option, opp, opp_player,
                                  retreat_on_menu: bool):
        """BUILD 3 (`enabler_item_composer`, DEFAULT OFF): ``(prizes, active_survives)`` if an ITEM that
        fetches an evolution Pokémon into HAND composes an otherwise-missed KO of the opponent's Active.
        The COMPOSITE line: play the Item (committed step[0]) → fetch the DIRECT evolution of an in-play,
        THIS-TURN-evolvable body (``appearThisTurn`` False — rules.md §4: a body cannot evolve the turn it
        was played) → evolve it → the evolved form, carrying the body's Energy plus this turn's one attach,
        affords a MIN-BOUND KO. The fetched form must be PROVABLY still in my deck (the tracker's positive
        certainty, ``Board.deck_definitely_has``) and fetchable by THIS item (a `tutor_mega` item reaches
        only a Mega ex; `tutor_pokemon` reaches any). A benched body needs the retreat still on the menu to
        reach the Active.

        SOUND energy accounting: the line's attach capacity is the **Attach Budget** built for THIS
        candidate evolved form (``_ko_line_pricing``, #142/#177) — every playable accelerator at its
        clause-quantified yield, target restrictions resolved against the evolved card's stats, and no
        hardcoded manual(1) + accel(1) ceiling. Every KO goes through
        ``_best_affordable_ko_value(bound="min")`` — a coin-conditional attack floors to its min damage, so
        no phantom KO. Value reflects the downstream evolve+attach KO; the caller tiers step[0] via
        ``_item_enabler_cost`` (slot-conditional, BUILD 4).

        NARROW SCOPE — single Item → single DIRECT evolve → attack. TODO (generality deferred): multi-hop
        evolution chains ACROSS turns, the fetched form deployed onto a DIFFERENT body/energy config than
        the one modelled (#2), and chaining a second Pokémon-tutor. None when no composite reaches a KO."""
        if not self.stats:
            return None
        item_id = self._option_card_id(obs, select, option)
        tags = self.functions.tags(item_id) if (self.functions and item_id is not None) else ()
        mega_only = "tutor_mega" in tags and "tutor_pokemon" not in tags   # the item's fetch class
        me = self._my_player(obs)
        bodies = [(p, False) for p in (me.get("active") or []) if p]
        if retreat_on_menu:
            bodies += [(p, True) for p in (me.get("bench") or []) if p]
        best = None
        for body, benched in bodies:
            if body.get("appearThisTurn"):
                continue                                  # can't evolve a body played this turn (rules.md §4)
            base = self.stats.get(body.get("id"))
            if base is None or not getattr(base, "name", None):
                continue
            energy = len(body.get("energies") or [])
            for cid in set(self.deck):
                st = self.stats.get(cid)
                if st is None or getattr(st, "evolvesFrom", None) != base.name:
                    continue
                if mega_only and not getattr(st, "megaEx", False):
                    continue                              # this item cannot fetch a non-Mega evolution
                # ADR-0074 decision 6 (extended, #175): the Pokemon-presence leg is WEIGHTED, not
                # gated. `deck_definitely_has` needs the anchor, so gating on it made this RANKED
                # line inert pre-anchor — exactly the frames the weighting exists to serve. 0.0 is
                # provably-empty and still drops the line; the Win Rung keeps the sound gate.
                present_p = board.deck_contains_probability(cid)
                if present_p <= 0.0:
                    continue                              # provably gone — no line to rank
                # The Budget is PER TARGET BODY, so it is built for THIS candidate evolved form
                # (its stats gate every accel clause's target restriction), not once for the menu.
                budget, attack_p = self._ko_line_pricing(cid, body, benched=benched)
                if budget is None or self._best_affordable_ko_value(
                        obs, board, opp, cid, energy, bound="min", body=body,
                        attack_p=attack_p, budget=budget) <= 0:
                    continue
                my_hp = getattr(st, "hp", 0) or 0
                cand = (self._prize_value(opp),
                        bool(my_hp) and self._survives_after_ko(cid, my_hp, opp_player),
                        present_p * self._composed_line_p(obs, board, opp, cid,
                                                          energy, body, attack_p,
                                                          budget=budget))
                if best is None or _composed_rank(cand) > _composed_rank(best):
                    best = cand
        return best

    def _rare_candy_ko_candidate(self, obs, select, board, option, opp, opp_player,
                                 retreat_on_menu: bool):
        """BUILD 1 (`enabler_item_composer`, DEFAULT OFF): ``(prizes, active_survives)`` if RARE CANDY
        (id 1079) composes an otherwise-missed KO of the opponent's Active by SKIPPING the Stage 1. The
        legal line (card text, data/EN_Card_Data.csv id 1079; rules.md §4): play Rare Candy (committed
        step[0]) → choose an in-play BASIC (``evolvesFrom`` None) that is NOT ``appearThisTurn`` and NOT on
        turn ≤ 1 ("can't use this card during your first turn or on a Basic Pokémon that was put into play
        this turn") → put an IN-HAND Stage-2 whose chain ROOTS at that Basic (the Stage-2's ``evolvesFrom``
        names a Stage-1 whose ``evolvesFrom`` names the Basic) directly onto it → the Stage-2, carrying the
        Basic's Energy plus this turn's one (sound) attach, affords a MIN-BOUND KO. A benched Basic needs
        the retreat still on the menu to reach the Active.

        Unlike the item tutor, Rare Candy is NOT a tutor — the Stage-2 must ALREADY be in hand
        (``board.hand_ids``), so no ``deck_definitely_has`` whiff-check is needed (in-hand is certain).

        HONEST NOTE (updated 2026-08-06): this branch is **INERT on every shipped deck again**. It was
        recorded inert when none of the then-3 agent decks ran Rare Candy or a Basic→Stage-1→Stage-2 line;
        Issue #288 retired that note because `grimmsnarl_ex` ran both — 1 Rare Candy and Marnie's Impidimp →
        Morgrem → Grimmsnarl ex — and measured the branch correct there on 2026-08-02. PR #436 then deleted
        that deck, and NO surviving deck runs Rare Candy at all (checked across all five `src/agents/*/
        deck.csv`, 2026-08-06), so the branch is forward-looking generality once more. Its real-deck test
        went with the deck; `tests/strategy/test_deferred_planner_cluster.py` carries the whole mechanism on
        a synthetic four-card pool — compose, turn-1, `appearThisTurn`, Stage-2-not-in-hand, and the flag
        gate. The same deletion cost `common.playability`'s Rare Candy escape (ADR-0104 decision 3) its
        shipped-deck instance in the same way.

        Two findings from the 2026-08-02 measurement are worth carrying forward even though the deck is
        gone. The composer is correct on a real engine-backed board, not only on the synthetic pool. And a
        stand-down for want of ENERGY looks exactly like a broken branch from outside — the first probe of
        this code was misread that way, because attack 937 cost {D}{D} and the fixture's Attach Budget could
        offer nothing. None when no composite reaches a KO."""
        if board.turn <= 1:
            return None                                   # Rare Candy is illegal on your first turn
        if not self.stats:
            return None
        me = self._my_player(obs)
        bodies = [(p, False) for p in (me.get("active") or []) if p]
        if retreat_on_menu:
            bodies += [(p, True) for p in (me.get("bench") or []) if p]
        best = None
        for body, benched in bodies:
            if body.get("appearThisTurn"):
                continue                                  # can't Rare Candy a Basic put into play this turn
            base = self.stats.get(body.get("id"))
            if base is None or not getattr(base, "name", None):
                continue
            if getattr(base, "evolvesFrom", None) is not None:
                continue                                  # Rare Candy targets a BASIC only (nothing evolves into it)
            energy = len(body.get("energies") or [])
            for cid in board.hand_ids:                    # the Stage-2 must ALREADY be in hand
                st = self.stats.get(cid)
                if st is None or not getattr(st, "stage2", False):
                    continue                              # a Stage-2 card only
                if not self._stage2_roots_at(st, base.name):
                    continue                              # its chain must root at THIS Basic (skip Stage 1)
                budget, attack_p = self._ko_line_pricing(cid, body, benched=benched)   # per-candidate
                if budget is None or self._best_affordable_ko_value(
                        obs, board, opp, cid, energy, bound="min", body=body,
                        attack_p=attack_p, budget=budget) <= 0:
                    continue
                my_hp = getattr(st, "hp", 0) or 0
                cand = (self._prize_value(opp),
                        bool(my_hp) and self._survives_after_ko(cid, my_hp, opp_player),
                        self._composed_line_p(obs, board, opp, cid, energy, body,
                                              attack_p, budget=budget))
                if best is None or _composed_rank(cand) > _composed_rank(best):
                    best = cand
        return best

    def _tutor_evolution_wins(self, obs, board, opp, body) -> bool:
        """SOUND: some DIRECT evolution of ``body`` (its `evolvesFrom` names the body) is PROVABLY
        still in my deck (the tracker's positive certainty, `Board.deck_definitely_has`), is
        Salvatore-eligible (no Abilities — the card's own fetch filter), and — carrying the body's
        Energy plus this turn's one attach — takes a min-bound winning KO (`_develop_wins`). The
        family's tier-4 win test; multi-hop descendants are excluded (one Salvatore = one hop)."""
        if not self.stats:
            return False
        base = self.stats.get(body.get("id"))
        if base is None or not getattr(base, "name", None):
            return False
        energy = len(body.get("energies") or [])
        extra = 1 if (board.reusable_energy_in_hand and not board.energy_attached) else 0
        for cid in set(self.deck):
            st = self.stats.get(cid)
            if (st is None or getattr(st, "evolvesFrom", None) != base.name
                    or getattr(st, "hasAbility", False)):
                continue
            if not board.deck_definitely_has(cid):
                continue
            if self._develop_wins(obs, board, opp, cid, energy + extra, body=body):
                return True
        return False

    def _retreat_ko_candidate(self, obs, board, opp, opp_player, *, supporter_spent: bool = True):
        """``(prizes, active_survives)`` for the best benched body that KOs the opponent's Active AFTER a
        retreat plus this turn's one attach — but that does NOT already KO at its current Energy (that
        single-step case is the existing ``_retreat_to_lethal_tactical`` hook's job). Among the KO-capable
        bodies (all take the same prize off the shared target) it prefers the one that SURVIVES the
        opponent's post-KO Incoming. None when no benched body needs the attach to reach a KO. Reuses the
        shared sound KO valuation (``_best_affordable_ko_value``: Weakness/Resistance, ex-immunity).

        The line's attach capacity is the typed Attach Budget built for THIS benched body (ADR-0075)
        — ``benched=True``, because the attach can be made before the retreat and no modelled accel
        clause requires an Active target, so it is a strict superset naming a real sequence.
        ``supporter_spent`` DEFAULTS TRUE and that is load-bearing (ADR-0075). A bare retreat spends
        no card and is tiered ``_PLANNER_ENABLER_FREE`` for exactly that reason, so its Budget must
        not quietly include a Supporter's yield — a KO funded by Hilda's fetch is not a free-enabler
        KO, and crediting it as one inverts ADR-0031's rule that an enabler PRESERVING deck/slot
        resources outranks a tutor reaching the SAME KO. Only :meth:`_supporter_ko_candidate`, whose
        committed first step IS that Supporter, passes False."""
        me = self._my_player(obs)
        best = None                                   # (prizes, survives)
        for p in (me.get("bench") or []):
            if not p:
                continue
            energy = len(p.get("energies") or [])
            if self._best_affordable_ko_value(obs, board, opp, p.get("id"), energy, body=p) > 0:
                continue                              # retreat alone already KOs — existing hook owns it
            budget, attack_p = self._ko_line_pricing(p.get("id"), p, benched=True,
                                                     supporter_spent=supporter_spent)
            if budget is None or self._best_affordable_ko_value(
                    obs, board, opp, p.get("id"), energy, body=p,
                    budget=budget, attack_p=attack_p) <= 0:
                continue
            cand = (self._prize_value(opp), self._survives_after_ko(p.get("id"), p.get("hp", 0), opp_player))
            if best is None or cand > best:           # prefer more prizes, then survival (bool > bool)
                best = cand
        return best

    def _tutor_evolve_ko_candidate(self, obs, board, opp, opp_player, retreat_on_menu: bool):
        """``(prizes, active_survives)`` if playing an **evolution-tutor Supporter** (Salvatore: evolve
        one of my in-play Pokémon straight from the deck — the ``rush_evolve`` tag) unlocks an
        otherwise-missed KO of the opponent's Active: some DIRECT, no-Ability evolution still LIKELY in
        my deck (``deck_contains_probability`` majority-odds — rank-grade, the win rung upstream owns
        the certain case), put onto an in-play body and carried to the Active (a benched body needs the
        retreat still on the menu), affords a KO with the body's Energy plus this turn's one attach.
        No closed-form hook scores a Supporter first-step, so this is net-new (the a212 shape:
        Salvatore -> Mega Starmie onto a setup Staryu -> free retreat -> attach -> Jetting Blow).
        None when no such evolution reaches a KO.

        The Budget is built for the FETCHED evolution (ADR-0075) — its stats gate every accel
        clause's target restriction — over the body the Energy carries through, with
        ``supporter_spent=True`` because Salvatore IS the Supporter this line plays."""
        me = self._my_player(obs)
        # (body, benched) rather than a flat list: the Budget must know where the target SITS, and a
        # bench-restricted accel clause funds one and not the other (ADR-0075 decision 4). The flat
        # `active + bench` this replaced lost that, silently.
        bodies = [(p, False) for p in (me.get("active") or []) if p]
        if retreat_on_menu:
            bodies += [(p, True) for p in (me.get("bench") or []) if p]
        best = None
        for body, benched in bodies:
            base = self.stats.get(body.get("id")) if self.stats else None
            if base is None or not getattr(base, "name", None):
                continue
            energy = len(body.get("energies") or [])
            for cid in set(self.deck):
                st = self.stats.get(cid)
                if (st is None or getattr(st, "evolvesFrom", None) != base.name
                        or getattr(st, "hasAbility", False)):
                    continue
                # ADR-0074 decision 1 forbids a THRESHOLD: the retired `<= 0.5` cut-off scored a
                # 0.51 fetch and a 0.99 fetch identically and a 0.49 one at zero — the same
                # boolean-collapse defect #175 exists to remove. The odds are now the weight.
                present_p = board.deck_contains_probability(cid)
                if present_p <= 0.0:
                    continue                          # provably gone — nothing to rank
                budget, attack_p = self._ko_line_pricing(cid, body, benched=benched,
                                                         supporter_spent=True)
                if budget is None or self._best_affordable_ko_value(
                        obs, board, opp, cid, energy, body=body,
                        budget=budget, attack_p=attack_p) <= 0:
                    continue
                my_hp = getattr(st, "hp", 0) or 0
                cand = (self._prize_value(opp),
                        bool(my_hp) and self._survives_after_ko(cid, my_hp, opp_player),
                        present_p)
                if best is None or _composed_rank(cand) > _composed_rank(best):
                    best = cand
        return best

    def _supporter_ko_candidate(self, obs, select, board, option, opp, opp_player):
        """``(prizes, active_survives)`` if playing a **tutor-energy Supporter** (Hilda: search an Energy
        into hand — the ``tutor_energy`` tag) unlocks an otherwise-missed retreat→attach→KO. The Supporter
        SUPPLIES the attachable Energy the plain retreat line lacks: with that fetched Energy modelled as
        this turn's one attach, a benched body KOs the opponent's Active after a retreat. The enabling
        first step here is the Supporter, not a retreat/evolve — no closed-form hook scores it, so it is
        net-new (corpus 4298). Fires ONLY when no reusable Energy is already in hand (else the plain
        retreat line covers it) AND the turn's one attach is still available (else the fetched Energy can't
        power the KO this turn). None otherwise. Reuses the sound retreat-KO valuation."""
        if board.energy_attached or board.reusable_energy_in_hand:
            return None
        if not self._is_energy_tutor(obs, select, option):
            return None
        # The Supporter leg stays OPEN here, and that is the opposite of the sibling Salvatore line
        # (`_tutor_evolve_ko_candidate`, which passes supporter_spent=True). The discriminator is
        # whether THIS line's Supporter contributes to the Budget:
        #   * Hilda is `tutor_energy` with a readable deck-fetch clause, so she IS the Budget's
        #     energy source for her own line — closing the leg would delete the very yield the line
        #     depends on and make it structurally dead (measured: her Budget is size 1 open, 0 closed).
        #   * Salvatore is `rush_evolve` with NO accel tag, so it contributes nothing and merely
        #     SPENDS the slot — leaving the leg open there would let the Budget assume a different
        #     Supporter is also played, which is the illegal two-Supporter turn.
        # Double-counting is structurally impossible either way: each Supporter is a separate
        # alternative play-set, so a hand holding both Hilda and Crispin still yields size 1, never 2.
        return self._retreat_ko_candidate(obs, board, opp, opp_player, supporter_spent=False)

    def _evolve_ko_candidate(self, obs, select, board, option, opp, opp_player):
        """``(prizes, active_survives)`` if EVOLVING the Active unlocks a KO of the opponent's Active this
        turn — the evolved form (the option's in-hand card) inherits the Active's Energy and, with this
        turn's one attach, its best affordable attack KOs. Evolving then attacking is legal the same turn
        (rules.md §evolution). No closed-form hook scores an evolve-unlock, so this is always net-new.
        Survival uses the evolved form's HP (closed-form approximation; the P3 engine-sim is exact).
        None when evolving doesn't reach a KO.

        The Budget is built for the EVOLVED form at ``benched=False`` (ADR-0075) — this line evolves
        the ACTIVE, so the target sits Active and a bench-restricted clause (Wondrous Patch) must NOT
        fund it."""
        evolved_id = self._option_card_id(obs, select, option)
        if evolved_id is None:
            return None
        energy = board.my_active_energy
        ma = next((p for p in (self._my_player(obs).get("active") or []) if p), None)
        budget, attack_p = self._ko_line_pricing(evolved_id, ma, benched=False,
                                                 supporter_spent=True)   # an EVOLVE spends none
        if budget is None or self._best_affordable_ko_value(
                obs, board, opp, evolved_id, energy, body=ma,
                budget=budget, attack_p=attack_p) <= 0:
            return None
        estat = self.stats.get(evolved_id) if self.stats else None
        my_hp = getattr(estat, "hp", 0) or 0          # evolved max HP — P3 engine-sim resolves damage exactly
        return (self._prize_value(opp), self._survives_after_ko(evolved_id, my_hp, opp_player))

    def _free_evolve_ko_candidate(self, obs, select, board, option, opp, opp_player,
                                  retreat_on_menu: bool):
        """``(prizes, active_survives)`` if a FREE direct-evolve of a BENCHED body unlocks an
        otherwise-missed KO of the opponent's Active — the CHEAPEST enabler of all: the evolved form
        is already in hand and the engine only emits this type-9 EVOLVE option for a body legally
        evolvable this turn (its presence IS the legality signal — no ``appearThisTurn`` read needed),
        so no card leaves the deck and no tutor is spent. The benched body, evolved, carries its
        Energy plus this turn's one attach and — reaching the Active via the retreat still on the menu
        — affords a KO. Mirrors ``_tutor_evolve_ko_candidate``'s benched-body + retreat modelling, but
        keyed on the in-hand evolved form the option names (not a deck fetch). None when no retreat is
        available to promote the benched attacker, or the evolution doesn't reach a KO.

        The Budget is built for the EVOLVED form at ``benched=True`` (ADR-0075) — the evolve happens
        on the Bench and the retreat follows, so a bench-restricted clause legitimately funds this
        line."""
        if not retreat_on_menu:
            return None                                   # a benched attacker needs the retreat to attack
        evolved_id = self._option_card_id(obs, select, option)
        if evolved_id is None:
            return None
        idx = option.get("inPlayIndex")
        bench = self._my_player(obs).get("bench") or []
        body = bench[idx] if (idx is not None and 0 <= idx < len(bench)) else None
        if body is None:
            return None
        energy = len(body.get("energies") or [])
        budget, attack_p = self._ko_line_pricing(evolved_id, body, benched=True,
                                                 supporter_spent=True)   # an EVOLVE spends none
        if budget is None or self._best_affordable_ko_value(
                obs, board, opp, evolved_id, energy, body=body,
                budget=budget, attack_p=attack_p) <= 0:
            return None
        estat = self.stats.get(evolved_id) if self.stats else None
        my_hp = getattr(estat, "hp", 0) or 0
        return (self._prize_value(opp),
                bool(my_hp) and self._survives_after_ko(evolved_id, my_hp, opp_player))
