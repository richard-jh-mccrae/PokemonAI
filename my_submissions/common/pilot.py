"""The Pilot: a deck-agnostic Sense -> Plan -> Score -> Act decision engine (ADR-0008).

Tiny public interface (`decide`; `explain` adds the per-decision trace). Scoring merges a
deck-agnostic **General Strategy** (shared
hypotheses in `common/`) with the deck's own Strategy; per-hypothesis weights resolve by id
through machine-written `overrides` (0 disables). Operates on the raw observation dict the
engine passes, so the fast unit suite needs no native lib.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from common.strategy import Plan, Strategy

# AreaType values used to resolve a CARD option to its card id (see cg/api.py).
_ZONE = {2: "hand", 4: "active", 5: "bench"}
_ATTACK = 13  # OptionType.ATTACK
KO_SCORE = 1000  # an option that knocks out the target dominates a mere chip


def choose_plan(state: dict, strategy) -> Plan:
    """Pick this turn's Plan. SETUP until a win-condition Line's payoff is in play with
    enough energy; then RACE. (STABILIZE / CLOSE arrive with their own signals.)"""
    me = state["players"][state["yourIndex"]]
    board = [p for p in (me.get("active") or []) + (me.get("bench") or []) if p]
    for line in strategy.lines:
        if any(p["id"] == line.payoff and len(p.get("energies", [])) >= line.ready.energy
               for p in board):
            return Plan.RACE
    return Plan.SETUP


@dataclass
class Board:
    """Per-decision board summary (shared by every option) — the cross-option signals a
    Hypothesis trigger reads (bench size, my/opp Active, opponent bench, energy/turn)."""
    my_bench: int = 0
    my_active_id: int | None = None
    my_active_energy: int = 0
    opp_active_id: int | None = None
    opp_active_hp: int = 0
    opp_bench: tuple = ()          # ((cardId, hp), …) of the opponent's benched Pokémon
    turn: int = 0
    energy_attached: bool = False  # have I already attached Energy this turn?


@dataclass
class Context:
    """What the Score layer knows about one option — the input a Hypothesis trigger reads."""
    plan: Plan
    select_context: int | None
    option_type: int | None
    card_id: int | None
    roles: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    stat: object | None = None     # the option card's engine CardStat (hp/weakness/prize value/…)
    board: Board = field(default_factory=Board)   # per-decision board summary (same for all options)
    is_attack: bool = False
    is_ko: bool = False            # this option is an attack that knocks out the opponent's Active


@dataclass
class OptionTrace:
    """Why one option scored what it did — the legibility record (ADR-0008): which
    Hypotheses fired (general + deck) with their effective weights, plus the combat term."""
    index: int
    score: float
    plan: Plan
    card_id: int | None
    fired: list                  # [(Hypothesis, effective_weight)] whose trigger fired
    tactical: float = 0.0


@dataclass
class Decision:
    """A scored decision: the chosen option indices and the per-option OptionTrace."""
    chosen: list
    options: list = field(default_factory=list)


class Pilot:
    def __init__(self, strategy, deck, *, general_strategy=None, overrides=None, stats=None,
                 functions=None, attacks=None, search_budget=0):
        self.strategy = strategy
        self.general = general_strategy or Strategy()   # deck-agnostic shared hypotheses (ADR-0008)
        self.overrides = overrides or {}                # machine-written weight overrides, by hyp id
        self.deck = list(deck)
        self.stats = stats
        self.functions = functions
        self.attacks = attacks or {}
        self.search_budget = search_budget

    def decide(self, obs: dict) -> list[int]:
        """The highest-scoring legal selection (the grader hot path): the deck on the initial
        selection, else option indices (count in [minCount, maxCount], unique, in range)."""
        return self._evaluate(obs).chosen

    def explain(self, obs: dict) -> Decision:
        """Same choice as `decide`, plus the per-option trace (which Hypotheses fired, the
        Plan, the card) — the legibility record the writeup is generated from (ADR-0008)."""
        return self._evaluate(obs)

    def _evaluate(self, obs: dict) -> Decision:
        select = obs.get("select")
        if select is None:                       # initial deck-submission step
            return Decision(chosen=list(self.deck))
        options = select.get("option") or []
        board = self._board(obs)
        traces = [self._option_trace(obs, select, board, o, i) for i, o in enumerate(options)]
        max_count = select.get("maxCount", 0)
        order = sorted(range(len(options)), key=lambda i: traces[i].score, reverse=True)
        return Decision(chosen=order[:max_count], options=traces)

    def _option_trace(self, obs: dict, select: dict, board: Board, option: dict,
                      index: int) -> OptionTrace:
        tactical = self._tactical(obs, option)
        ctx = self._context(obs, select, board, option, tactical)
        hyps = (*self.general.hypotheses, *self.strategy.hypotheses)
        fired = [(h, self._weight(h)) for h in hyps if _fires(h, ctx)]
        score = sum(w for _, w in fired) + tactical
        return OptionTrace(index=index, score=score, plan=ctx.plan, card_id=ctx.card_id,
                           fired=fired, tactical=tactical)

    def _weight(self, h) -> float:
        """Effective weight: a machine-written override by id, else the authored default
        (0 disables). ADR-0008 tunables: shared defaults -> per-deck/machine overrides."""
        return self.overrides.get(h.id, h.weight)

    def _tactical(self, obs: dict, option: dict) -> float:
        """Closed-form combat value (Tier-0): printed damage (x2 on Weakness) vs the opponent
        Active's HP. A knockout dominates; otherwise the chip is worth its damage."""
        if option.get("type") != _ATTACK:
            return 0
        dmg = self.attacks.get(option.get("attackId"), 0)
        opp = self._opp_active(obs)
        hp = (opp or {}).get("hp", 0)
        dmg = self._weakness_adjusted(obs, opp, dmg)
        if hp and dmg >= hp:
            return KO_SCORE + self._prize_value(opp)   # among KOs, prefer the higher-prize target
        return dmg

    def _prize_value(self, poke: dict | None) -> int:
        """Prizes a knockout yields — Mega ex 3, ex 2, else 1 (read off the engine CardStat)."""
        stat = self.stats.get((poke or {}).get("id")) if self.stats else None
        if stat and stat.megaEx:
            return 3
        if stat and stat.ex:
            return 2
        return 1

    def _weakness_adjusted(self, obs: dict, opp: dict | None, dmg: float) -> float:
        """Double the damage when the defending Active is Weak to my Active's type (x2, S&V;
        Active only). Closed-form Tier-0; Tier-1 Search resolves the exact figure."""
        if not (self.stats and opp and dmg):
            return dmg
        defender = self.stats.get(opp.get("id"))
        attacker = self.stats.get(self._my_active_id(obs))
        if (defender and attacker and defender.weakness is not None
                and defender.weakness == attacker.energyType):
            return dmg * 2
        return dmg

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

    def _context(self, obs: dict, select: dict, board: Board, option: dict,
                 tactical: float = 0.0) -> Context:
        state = obs.get("current") or {}
        plan = choose_plan(state, self.strategy) if state.get("players") else Plan.SETUP
        cid = self._option_card_id(obs, option)
        roles = self.strategy.roles.get(cid, []) if cid is not None else []
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        is_attack = option.get("type") == _ATTACK
        return Context(plan=plan, select_context=select.get("context"),
                       option_type=option.get("type"), card_id=cid, roles=roles, tags=tags,
                       stat=stat, board=board, is_attack=is_attack,
                       is_ko=is_attack and tactical >= KO_SCORE)

    def _board(self, obs: dict) -> Board:
        """Summarise the shared board once per decision (see Board)."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        ma = next((p for p in (me.get("active") or []) if p), None)
        oa = next((p for p in (opp.get("active") or []) if p), None)
        return Board(
            my_bench=sum(1 for b in (me.get("bench") or []) if b),
            my_active_id=(ma or {}).get("id"),
            my_active_energy=len((ma or {}).get("energies") or []),
            opp_active_id=(oa or {}).get("id"),
            opp_active_hp=(oa or {}).get("hp", 0),
            opp_bench=tuple((b.get("id"), b.get("hp", 0)) for b in (opp.get("bench") or []) if b),
            turn=state.get("turn", 0),
            energy_attached=bool(state.get("energyAttached")),
        )

    def _option_card_id(self, obs: dict, option: dict) -> int | None:
        area, index = option.get("area"), option.get("index")
        if area is None or index is None:
            return None
        state = obs.get("current") or {}
        players = state.get("players") or []
        pi = option.get("playerIndex", state.get("yourIndex", 0))
        if not (0 <= pi < len(players)) or players[pi] is None:
            return None
        cards = players[pi].get(_ZONE.get(area))
        if not cards or not (0 <= index < len(cards)) or cards[index] is None:
            return None
        return cards[index].get("id")


def _fires(h, ctx: Context) -> bool:
    try:
        return bool(h.when(ctx))
    except Exception:
        return False
