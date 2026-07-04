"""DOCTRINE: Tool (Pokémon Tool equip) — ADR-0028. One file, end to end.

A Pokémon Tool equips at an ATTACH select. A +HP Tool (Hero's Cape: +100 HP, ACE SPEC,
irreplaceable) is deployed **PROACTIVELY** onto the body that carries the game — the win-condition
by default — **not** held for an HP breakpoint, because a deck that shuffles its own hand (Lillie's /
Harlequin; Function Tag `shuffle_hand`) would otherwise shuffle the one-of ACE SPEC back into the
deck (the protect-weights drag the equip to ≤0, which `_finish_turn_last` drops BELOW the shuffle).
The target body is chosen by **survival-turns** board-math (`ceil(hp / incoming)`; the boost earns
its slot when it adds a full turn) with the win-condition always taking priority. `ToolMixin` is the
Pilot-side closed-form half: the +HP-tool guard, the irreplaceable-tool guard, and the
`_tool_deploy_slot` target picker. See docs/adr/0028-tool-deploy-is-survival-turns-board-math.md.
"""
from __future__ import annotations

from common.strategy.context import _ACTIVE, _ATTACH, _BENCH, _PLAY, _WINCON_ROLES
from common.strategy.strategy import Hypothesis

# A non-win-condition WALL earns the one-per-deck ACE SPEC +HP Tool only when it is actually dying
# soon — baseline survival this many turns or fewer. A safe body's survival 'gain' is nominal (the
# Tool is better spent as tempo; the held ACE SPEC stays shuffle-safe). ep83665798 f12.
_WALL_THREAT_TURNS = 2


def _is_hp_tool(stat, tags) -> bool:
    """A Pokémon Tool that grants flat HP — Function Tag `tool` + a parsed `CardStat.hpBonus` > 0
    (e.g. Hero's Cape +100; restricted-condition tools parse to 0, so they're excluded). The deploy /
    target machinery only reasons about +HP tools."""
    return bool(stat and "tool" in tags and getattr(stat, "hpBonus", 0) > 0)


class ToolMixin:
    """The Pilot-side closed-form half of the Tool doctrine (mixed into `Pilot`). Reads shared Pilot
    helpers (`stats`, `functions`, `_wincon_set`) + the per-decision `Board`."""

    def _tool_in_hand(self, me: dict) -> bool:
        """True iff a `tool`-tagged card is in my hand — the cheap guard that gates the (whole-board)
        deploy-target computation, so the common no-Tool case pays nothing."""
        if not self.functions:
            return False
        return any(c and "tool" in self.functions.tags(c.get("id")) for c in (me.get("hand") or []))

    def _hp_tool_in_hand(self, me: dict):
        """(card_id, CardStat) of a +HP Tool in my hand, or (None, None) — the deploy candidate."""
        for c in (me.get("hand") or []):
            cid = c.get("id") if c else None
            if cid is None:
                continue
            stat = self.stats.get(cid) if self.stats else None
            tags = self.functions.tags(cid) if self.functions else []
            if _is_hp_tool(stat, tags):
                return cid, stat
        return None, None

    def _irreplaceable_tool_in_hand(self, me: dict) -> bool:
        """True if an irreplaceable Tool — an ACE SPEC (one-per-deck, unrecoverable) Pokémon Tool — is
        in my hand. The anti-shuffle belt reads this: never voluntarily shuffle it into the deck."""
        if not self.stats:
            return False
        for c in (me.get("hand") or []):
            cid = c.get("id") if c else None
            stat = self.stats.get(cid) if cid is not None else None
            tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
            if stat and "tool" in tags and getattr(stat, "aceSpec", False):
                return True
        return False

    @staticmethod
    def _survival_turns(hp: int, incoming: int) -> float:
        """How many turns a body of `hp` withstands `incoming` damage per turn — `ceil(hp / incoming)`,
        or +inf when nothing can reach it (incoming 0). The survival-turns primitive (ADR-0028)."""
        if incoming <= 0:
            return float("inf")
        return -(-hp // incoming)                            # integer ceil

    def _survival_gain(self, hp: int, incoming: int, bonus: int) -> int:
        """Extra survival turns a +HP boost buys a body — `survival_turns(hp+bonus) − survival_turns(hp)`,
        0 when nothing is incoming (it was already safe) or the body is doomed even at +bonus (both
        finite-and-equal). The defensive value of the Tool on that body."""
        if incoming <= 0 or hp <= 0 or bonus <= 0:
            return 0
        return int(self._survival_turns(hp + bonus, incoming) - self._survival_turns(hp, incoming))

    def _opp_bench_snipe(self, obs: dict) -> int:
        """The opponent Active's bench-snipe rider (e.g. Jetting Blow's 50) — the incoming a benched
        body of mine eats each turn (bench snipes ignore Weakness/Resistance). 0 when unknown."""
        oa = self._opp_active(obs)
        st = self.stats.get(oa.get("id")) if (oa and self.stats) else None
        return getattr(st, "benchSnipeDamage", 0) if st else 0

    def _opp_in_play(self, obs: dict) -> list:
        """The opponent's in-play Pokémon (Active + Bench) — the candidate next attackers."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        return [p for p in ((opp.get("active") or []) + (opp.get("bench") or [])) if p]

    def _opp_best_attack_vs(self, obs: dict, defender_id) -> int:
        """Max weakness-adjusted damage any opponent in-play Pokémon that can AFFORD to attack next turn
        (attached Energy ≥ its cheapest attack cost, allowing one attach) deals to my body `defender_id`
        — the **predicted next attacker** (ADR-0028). Generalises incoming beyond the opponent's current
        Active to a benched body it could promote (the hardest-hitting affordable one is the promotion).
        0 when unknown. Isolated to the Tool doctrine (does not touch the shared `_incoming_active_damage`)."""
        if not self.stats:
            return 0
        best = 0
        for p in self._opp_in_play(obs):
            st = self.stats.get(p.get("id"))
            if not st:
                continue
            if (st.minAttackCost or 0) > len(p.get("energies") or []) + 1:   # unaffordable even w/ attach
                continue
            best = max(best, int(self._predicted_max_damage(st, {"id": defender_id})))
        return best

    def _tool_carrier_candidates(self, obs: dict, me: dict, board, active_incoming: int,
                                 successor_mode: bool) -> list:
        """The bodies that could carry my held +HP Tool, each as
        (slot=(AreaType, inPlayIndex), hp, incoming_per_turn, is_wincon_related). My Active takes the
        predicted `active_incoming` (the opponent's best affordable attacker, not just their current
        Active). A benched body normally takes only the opponent's bench-snipe (snipe-only — assumed to
        stay benched); but when the Active is doomed at +boost (`successor_mode`), a benched body is the
        next promotion and inherits the FULL predicted incoming. A wincon-related body is the
        win-condition itself or a Line pre-evolution (the Tool transfers up on evolution)."""
        wincon = self._wincon_set()
        preevo = self._line_preevo_set()
        out = []
        if next((p for p in (me.get("active") or []) if p), None) is not None:
            out.append(((_ACTIVE, 0), board.my_active_hp, active_incoming, board.active_is_wincon))
        bench_inc = active_incoming if successor_mode else self._opp_bench_snipe(obs)
        for i, b in enumerate(me.get("bench") or []):
            if not b:
                continue
            bid = b.get("id")
            out.append(((_BENCH, i), b.get("hp", 0), bench_inc, bid in wincon or bid in preevo))
        return out

    def _best_gain_slot(self, candidates: list, bonus: int, *, wincon: bool,
                        require_threat: bool = False) -> tuple | None:
        """Among `candidates` of the chosen kind (win-condition-related, or not), the slot where the +HP
        boost buys the MOST survival turns — None if none gains a full turn. Ties favour the Active (the
        body already in the fight). The comparison key is an int tuple, so the slot is never compared
        (the tuple-vs-None crash this avoids).

        `require_threat` (the non-win-condition WALL branch): only a body actually IN DANGER — one whose
        baseline survival is `_WALL_THREAT_TURNS` turns or fewer — is worth the one-per-deck ACE SPEC; a
        safe body's survival 'gain' is nominal (a 160-HP Cinderace vs 20 incoming survives 8 turns → 13,
        a meaningless +5), and the Tool is better spent as tempo (attach Energy) while the held ACE SPEC
        stays shuffle-safe under `hold-irreplaceable-tool-dont-shuffle` (ep83665798 f12)."""
        best_key, best_slot = (0, 0), None
        for slot, hp, incoming, is_wincon in candidates:
            if is_wincon != wincon:
                continue
            if require_threat and self._survival_turns(hp, incoming) > _WALL_THREAT_TURNS:
                continue                          # a wall not actually dying soon — don't burn the ACE SPEC
            key = (self._survival_gain(hp, incoming, bonus), 1 if slot[0] == _ACTIVE else 0)
            if key > best_key:
                best_key, best_slot = key, slot
        return best_slot if best_key[0] >= 1 else None

    def _tool_deploy_slot(self, obs: dict, me: dict, board) -> tuple | None:
        """The (AreaType, inPlayIndex) of the body to equip my held +HP Tool this turn — the
        survival-turns target picker (ADR-0028). None when no +HP Tool in hand or no body worth it.

        Priority: (1) the **win-condition** body that gains the most survival turns (the racing Active,
        a sniped benched Line piece, or — when the Active is doomed even at +boost — the benched
        successor that inherits the full incoming on promotion); then (2) the proactive / anti-shuffle
        default — park it on the Active win-condition so a hand-shuffle can't bury it, UNLESS that Active
        is itself doomed at +boost (never equip a body that dies anyway); then (3) a non-win-condition
        WALL, but ONLY when the boost buys it a real survival turn ('never say never', wincon priority
        already satisfied — e.g. a re-emerged Cinderace that survives 2 turns instead of 1)."""
        _, stat = self._hp_tool_in_hand(me)
        if stat is None:
            return None
        bonus = getattr(stat, "hpBonus", 0)
        active_incoming = self._opp_best_attack_vs(obs, board.my_active_id)    # predict-next-attacker
        successor_mode = bool(board.active_is_wincon and board.my_active_hp > 0   # doomed even at +boost ->
                              and active_incoming >= board.my_active_hp + bonus)  # protect the successor
        candidates = self._tool_carrier_candidates(obs, me, board, active_incoming, successor_mode)
        slot = self._best_gain_slot(candidates, bonus, wincon=True)        # (1) win-condition body
        if slot is not None:
            return slot
        if board.active_is_wincon and not successor_mode:                  # (2) proactive default
            return (_ACTIVE, 0)
        return self._best_gain_slot(candidates, bonus, wincon=False,       # (3) a wall, only if it is
                                    require_threat=True)                   # actually in danger (not a safe body)


# ── deploy rung: positive endorsement so equip scores > 0, tiers BEFORE a hand-shuffle ──
HYPOTHESES = [
    Hypothesis(
        id="deploy-hp-tool",
        rationale="Deploy a +HP Pokémon Tool (Function Tag `tool`, e.g. Hero's Cape +100) onto the body "
                  "the survival-turns picker chose — PROACTIVE (not held for a breakpoint), since a "
                  "hand-shuffle Supporter (Lillie's / Harlequin) would otherwise bury the irreplaceable "
                  "ACE SPEC back in the deck (ADR-0028). Positive weight so the equip tiers (tier-2) "
                  "BEFORE a tier-3 hand-shuffle; reads `Context.attach_is_tool_deploy_target`, and a "
                  "lethal KO still outranks it.",
        when=lambda c: c.attach_is_tool_deploy_target,
        weight=40, status="assumed"),
    Hypothesis(
        id="hold-irreplaceable-tool-dont-shuffle",
        rationale="Don't shuffle an irreplaceable ACE SPEC Tool (e.g. Hero's Cape — one-per-deck, not "
                  "recoverable from discard) away with a `shuffle_hand` Supporter; sent back into the "
                  "deck it's effectively lost for the game. Belt to `deploy-hp-tool`'s suspenders (that "
                  "equips it when a carrier exists, this holds it when none does yet) — mirrors "
                  "`hold-wincon-dont-shuffle` but stronger, since a shuffled wincon is at least recoverable.",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.board.irreplaceable_tool_in_hand,
        weight=-30, status="assumed"),
    # ── WHERE-NOT guards (moved from baseline_tool, re-scoped per ADR-0028): reluctant to fritter
    #    a Tool on an off-line body — but stands DOWN on the body the survival-turns picker chose ──
    Hypothesis(
        id="save-tool-for-the-attacker",
        rationale="A Pokémon Tool (Function Tag `tool`, e.g. Hero's Cape) is a one-shot equip — don't "
                  "spend it on an off-role Pokémon; hold it for the win-condition/primary attacker. "
                  "RE-SCOPED (ADR-0028): stands down on the picker's chosen deploy target "
                  "(`attach_is_tool_deploy_target`, incl. a wincon LINE pre-evolution), firing only on a "
                  "picker-rejected off-line body.",
        when=lambda c: c.option_type == _ATTACH and "tool" in c.tags
        and not (_WINCON_ROLES & set(c.attach_target_roles))
        and not c.attach_is_tool_deploy_target,
        weight=-15, status="testing"),
    Hypothesis(
        id="protect-ace-spec-tool",
        rationale="An ACE SPEC card is one-per-deck and usually irreplaceable, so be EXTRA reluctant to "
                  "spend an ACE SPEC Tool (e.g. Hero's Cape) on an off-role Pokémon. Stacks additively on "
                  "`save-tool-for-the-attacker`, reading the structural `aceSpec` fact off CardStat; same "
                  "RE-SCOPE stand-down on the picker's chosen deploy target (ADR-0028).",
        when=lambda c: c.option_type == _ATTACH and "tool" in c.tags
        and c.stat is not None and getattr(c.stat, "aceSpec", False)
        and not (_WINCON_ROLES & set(c.attach_target_roles))
        and not c.attach_is_tool_deploy_target,
        weight=-10, status="testing"),
]
