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
_ZONE = {2: "hand", 3: "discard", 4: "active", 5: "bench"}
_HAND = 2     # AreaType.HAND
_DECK = 1     # AreaType.DECK — a search candidate; ids are revealed in the select's `deck` list
_DISCARD = 3  # AreaType.DISCARD — a recover-from-discard candidate (Night Stretcher), in player.discard
_PLAY = 7     # OptionType.PLAY — play a card from hand (encoded as a bare hand `index`, no `area`)
_BENCH = 5    # AreaType.BENCH
_CARD = 3     # OptionType.CARD (a card-target option, e.g. an attack's snipe target)
_DAMAGE = 15  # SelectContext.DAMAGE — choose which Pokémon an attack deals damage to (a bench snipe)
_ATTACK = 13  # OptionType.ATTACK
KO_SCORE = 1000  # an option that knocks out the target dominates a mere chip
_OPENER_TAG = "opener"     # Function Tag: a card whose Ability opens the Active Spot (Explosiveness)
_STARTER_ROLE = "starter"  # deck Role: a card the deck intends to open with
_EFFICIENCY = 0.1          # per-Energy tiebreak: among equal-outcome attacks prefer the cheaper one;
                           # far below prize granularity (1) so it never overrides prize value


def choose_plan(state: dict, strategy, stats=None) -> Plan:
    """Pick this turn's Plan. SETUP until a win-condition Line's payoff is in play with enough
    energy to attack; then RACE. A Line's `ready.energy` is the threshold; when unset (None) it is
    derived from the engine — the payoff's cheapest attack cost, so a 1-Energy attack counts.
    (STABILIZE / CLOSE arrive with their own signals.)"""
    me = state["players"][state["yourIndex"]]
    board = [p for p in (me.get("active") or []) + (me.get("bench") or []) if p]
    for line in strategy.lines:
        threshold = line.ready.energy
        if threshold is None:                          # derive "online" from the cheapest attack
            threshold = _min_attack_cost(stats, line.payoff)
        if any(p["id"] == line.payoff and len(p.get("energies", [])) >= threshold for p in board):
            return Plan.RACE
    return Plan.SETUP


def _min_attack_cost(stats, payoff: int, default: int = 1) -> int:
    """The payoff's cheapest attack's energy cost, read off the engine CardStat (`default` when
    unknown — never 0, so a Pokémon is never 'online' with no Energy)."""
    stat = stats.get(payoff) if stats else None
    cost = getattr(stat, "minAttackCost", None) if stat else None
    return cost if cost is not None else default


@dataclass
class Board:
    """Per-decision board summary (shared by every option) — the cross-option signals a
    Hypothesis trigger reads (bench size, my/opp Active, opponent bench, energy/turn)."""
    my_bench: int = 0
    my_active_id: int | None = None
    my_active_energy: int = 0
    my_active_hp: int = 0
    opp_active_id: int | None = None
    opp_active_hp: int = 0
    opp_bench: tuple = ()          # ((cardId, hp), …) of the opponent's benched Pokémon
    turn: int = 0
    energy_attached: bool = False  # have I already attached Energy this turn?
    hand_startable: bool = False   # a card in hand can take the Active Spot (opener tag / starter role)
    active_doomed: bool = False    # the opponent can Knock Out my Active next turn (incoming-KO estimate)
    reusable_energy_in_hand: bool = False  # a plain (non-discard) Energy is in hand — a reusable
                                           # alternative to a discard-at-end-of-turn Energy
    wincon_in_play: bool = False   # my win-condition (a Line payoff / win_condition role) is already
                                   # on my Active or Bench — so a search needn't fetch another copy


@dataclass
class Context:
    """What the Score layer knows about one option — the input a Hypothesis trigger reads."""
    plan: Plan
    select_context: int | None
    option_type: int | None
    card_id: int | None
    option_area: int | None = None  # AreaType of the option's target (4=active, 5=bench) — attach targeting
    attach_target_area: int | None = None  # for an attach, the AreaType of the Pokémon receiving the
                                           # Energy (4=active can attack this turn, 5=bench cannot)
    attach_target_roles: list = field(default_factory=list)  # deck Roles of that receiving Pokémon
    target_energy: int | None = None  # attack-target snipe signal: Energy on the targeted benched
                                      # Pokémon (None off a Damage/bench-target option)
    target_is_threat: bool = False  # the attack target already carries Energy -> closest to attacking
    roles: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    stat: object | None = None     # the option card's engine CardStat (hp/weakness/prize value/…)
    board: Board = field(default_factory=Board)   # per-decision board summary (same for all options)
    is_attack: bool = False
    tactical: float = 0.0          # the option's closed-form combat value (>= KO_SCORE on a knockout)
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
                 functions=None, attacks=None, attack_costs=None, search_budget=0):
        self.strategy = strategy
        self.general = general_strategy or Strategy()   # deck-agnostic shared hypotheses (ADR-0008)
        self.overrides = overrides or {}                # machine-written weight overrides, by hyp id
        self.deck = list(deck)
        self.stats = stats
        self.functions = functions
        self.attacks = attacks or {}                    # attackId -> printed damage
        self.attack_costs = attack_costs or {}          # attackId -> Energy count (efficiency tiebreak)
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
        attack_id = option.get("attackId")
        dmg = self.attacks.get(attack_id, 0)
        opp = self._opp_active(obs)
        hp = (opp or {}).get("hp", 0)
        dmg = self._weakness_adjusted(obs, opp, dmg)
        eff = _EFFICIENCY * self.attack_costs.get(attack_id, 0)   # cheaper of equal outcomes wins
        if hp and dmg >= hp:
            return KO_SCORE + self._prize_value(opp) - eff   # among KOs, prefer higher-prize then cheaper
        return dmg - eff

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
        plan = choose_plan(state, self.strategy, self.stats) if state.get("players") else Plan.SETUP
        cid = self._option_card_id(obs, select, option)
        roles = self.strategy.roles.get(cid, []) if cid is not None else []
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        is_attack = option.get("type") == _ATTACK
        target_energy = self._target_energy(obs, select, option)
        at_target = self._attach_target(obs, option)   # the Pokémon an attach option puts Energy on
        at_roles = self.strategy.roles.get(at_target.get("id"), []) if at_target else []
        return Context(plan=plan, select_context=select.get("context"),
                       option_type=option.get("type"), card_id=cid, option_area=option.get("area"),
                       attach_target_area=option.get("inPlayArea"), attach_target_roles=at_roles,
                       target_energy=target_energy, target_is_threat=bool(target_energy),
                       roles=roles, tags=tags, stat=stat, board=board, is_attack=is_attack,
                       tactical=tactical, is_ko=is_attack and tactical >= KO_SCORE)

    def _attach_target(self, obs: dict, option: dict) -> dict | None:
        """The Pokémon an attach option puts Energy on — encoded as `inPlayArea`/`inPlayIndex`
        (distinct from `area`/`index`, which point at the Energy card in hand). None when absent."""
        area, index = option.get("inPlayArea"), option.get("inPlayIndex")
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
        return cards[index]

    def _target_energy(self, obs: dict, select: dict, option: dict) -> int | None:
        """Energy attached to the Pokémon an attack-target option points at — the snipe 'threat'
        signal: a benched Pokémon already carrying Energy is closest to attacking. Defined only for
        bench attack-target options (SelectContext DAMAGE, OptionType CARD, AreaType BENCH); None
        otherwise so non-target options carry no signal (cf. ``_option_card_id`` resolution)."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        poke = self._option_pokemon(obs, select, option)
        return len(poke.get("energies") or []) if poke else None

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
            my_active_hp=(ma or {}).get("hp", 0),
            opp_active_id=(oa or {}).get("id"),
            opp_active_hp=(oa or {}).get("hp", 0),
            opp_bench=tuple((b.get("id"), b.get("hp", 0)) for b in (opp.get("bench") or []) if b),
            turn=state.get("turn", 0),
            energy_attached=bool(state.get("energyAttached")),
            hand_startable=self._hand_startable(me.get("hand") or []),
            active_doomed=self._active_doomed(ma, oa),
            reusable_energy_in_hand=self._has_reusable_energy(me.get("hand") or []),
            wincon_in_play=self._wincon_in_play(me),
        )

    def _wincon_in_play(self, me: dict) -> bool:
        """True if my win-condition is already in play — a Strategy Line payoff or a card carrying the
        `win_condition` / `primary_attacker` Role sitting on my Active or Bench. Lets a 'fetch the
        win-condition' Hypothesis stand down once the payoff is on the board (don't pull a dead copy)."""
        wincon = {line.payoff for line in self.strategy.lines}
        wincon |= {cid for cid, r in self.strategy.roles.items()
                   if {"win_condition", "primary_attacker"} & set(r)}
        if not wincon:
            return False
        board = (me.get("active") or []) + (me.get("bench") or [])
        return any(p and p.get("id") in wincon for p in board)

    def _has_reusable_energy(self, hand: list) -> bool:
        """True if a **reusable** (non-discard) Energy is in hand — a *typed* Energy card (hp 0 with a
        real `energyType`) that is not tagged `discard_eot`. Used to prefer a Basic over a
        discard-at-end-of-turn Energy when both are available (deck-agnostic). NB the engine reports
        `energyType == 0` for Trainers *and* colourless special energies (e.g. Ignition), so a typed
        basic Energy is `energyType not in (None, 0)` — that excludes Trainers and Ignition."""
        for c in hand:
            cid = c.get("id") if c else None
            if cid is None:
                continue
            stat = self.stats.get(cid) if self.stats else None
            tags = self.functions.tags(cid) if self.functions else []
            if stat and stat.hp == 0 and stat.energyType not in (None, 0) and "discard_eot" not in tags:
                return True
        return False

    def _active_doomed(self, ma: dict | None, oa: dict | None) -> bool:
        """True if the opponent's Active can Knock Out my Active next turn — its biggest attack
        (doubled when my Active is Weak to the attacker's type) >= my Active's remaining HP. A
        closed-form threat estimate off engine stats (attack-affordability refinement is future)."""
        my_hp = (ma or {}).get("hp", 0)
        if not (self.stats and ma and oa and my_hp):
            return False
        opp_stat = self.stats.get(oa.get("id"))
        if not opp_stat:
            return False
        incoming = opp_stat.maxDamage or 0
        my_stat = self.stats.get(ma.get("id"))
        if (my_stat and my_stat.weakness is not None and opp_stat.energyType is not None
                and my_stat.weakness == opp_stat.energyType):
            incoming *= 2
        return incoming >= my_hp

    def _hand_startable(self, hand: list) -> bool:
        """True if a card in hand can take the Active Spot — a Pokémon with the `opener`
        Function Tag (Explosiveness-type) or the deck's `starter` Role — so a no-Basic hand is
        keepable (a Basic would prevent the mulligan prompt entirely)."""
        for c in hand:
            cid = c.get("id") if c else None
            if cid is None:
                continue
            if self.functions and _OPENER_TAG in self.functions.tags(cid):
                return True
            if _STARTER_ROLE in self.strategy.roles.get(cid, []):
                return True
        return False

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


def _fires(h, ctx: Context) -> bool:
    try:
        return bool(h.when(ctx))
    except Exception:
        return False
