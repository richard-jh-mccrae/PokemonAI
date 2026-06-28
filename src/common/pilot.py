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
_ATTACH = 8   # OptionType.ATTACH — attach an Energy (the one irreversible per-turn commitment)
_EVOLVE = 9   # OptionType.EVOLVE — evolve a Pokémon in play
_RETREAT = 12 # OptionType.RETREAT — swap the Active out (changes which Pokémon can attack)
_BENCH = 5    # AreaType.BENCH
_ACTIVE = 4   # AreaType.ACTIVE
_CARD = 3     # OptionType.CARD (a card-target option, e.g. an attack's snipe target)
_DAMAGE = 15  # SelectContext.DAMAGE — choose which Pokémon an attack deals damage to (a bench snipe)
_SWITCH = 3   # SelectContext.SWITCH — swap into the Active Spot (my own retreat OR a Boss's gust target)
_MAIN = 0     # SelectContext.MAIN — the open turn menu (where attack-last sequencing applies)
_ATTACK = 13  # OptionType.ATTACK
_END = 14     # OptionType.END — end the turn
KO_SCORE = 1000  # an option that knocks out the target dominates a mere chip
_OPENER_TAG = "opener"     # Function Tag: a card whose Ability opens the Active Spot (Explosiveness)
_STARTER_ROLE = "starter"  # deck Role: a card the deck intends to open with
_EFFICIENCY = 0.1          # per-Energy tiebreak: among equal-outcome attacks prefer the cheaper one;
                           # far below prize granularity (1) so it never overrides prize value
_STALL_RETREAT = 2         # retreat cost that makes a stranded energyless body a real tempo cost — the
                           # defensive stall-gust only bothers with a target this expensive to retreat


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
    incoming_active_damage: int = 0  # closed-form estimate of the opponent's biggest attack vs my
                                     # Active (weakness-doubled) — the margin behind active_doomed,
                                     # exposed so a +HP tool can test it crosses a survival breakpoint
    active_cheap_attack_kos: bool = False  # my Active's CHEAPEST attack would KO the opponent's Active
                                           # this turn (closed-form) — so a costly burst Energy
                                           # (e.g. Ignition->Nebula) is unnecessary; the cheap attack does it
    gust_best_ko_prizes: int = 0   # best prizes among the opponent's benched Pokémon my Active could KO
                                   # after gusting one to the Active Spot (0 if none) — the whether-to-play
                                   # gate for a gust Supporter (Boss's Orders). ADR-0022.
    active_ko_prizes: int = 0      # prizes from KOing the opponent's CURRENT Active with my cheapest
                                   # attack (0 if I can't) — the baseline a gust must beat (gusting
                                   # removes this Active, so it's only worth the Supporter for a bigger KO)
    my_prizes_remaining: int = 0   # prizes I still need to take (len of my prize pile); 0 when the obs
                                   # doesn't populate it. A gust KO reaching this count WINS (ADR-0022)
    reusable_energy_in_hand: bool = False  # a plain (non-discard) Energy is in hand — a reusable
                                           # alternative to a discard-at-end-of-turn Energy
    wincon_in_play: bool = False   # my win-condition (a Line payoff / win_condition role) is already
                                   # on my Active or Bench — so a search needn't fetch another copy
    wincon_in_hand: bool = False   # the win-condition card is already in my hand — so a tutor needn't
                                   # dig for another copy
    line_preevo_in_play: bool = False  # a non-payoff member of a Line's path (a pre-evolution) is in
                                       # play — so there's something a rush-evolve tutor can evolve
    weakest_bench_hp: int | None = None  # least HP among the opponent's benched snipe targets at a
                                         # DAMAGE select — the target closest to a knockout
    bench_wincon_ready: bool = False   # a benched win-condition / primary attacker already carries
                                       # enough Energy to attack — a finisher to retreat into
    active_is_wincon: bool = False     # my Active IS the win-condition / primary attacker
    stall_target_exists: bool = False  # the opponent has an energyless, high-retreat benched Pokémon —
                                       # a candidate to strand Active with a defensive stall-gust (ADR-0022)


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
    attach_target_needs: bool = False  # the receiving Pokémon still needs Energy to attack (has fewer
                                       # than its cheapest attack cost) — gates "attach to the needy"
    card_is_line_preevo: bool = False  # this option's card is a non-payoff member of a Line's path (a
                                       # pre-evolution that builds toward the win-condition)
    card_is_wincon: bool = False       # this option's card IS the win-condition (a Line payoff /
                                       # win_condition / primary_attacker)
    target_energy: int | None = None  # attack-target snipe signal: Energy on the targeted benched
                                      # Pokémon (None off a Damage/bench-target option)
    target_is_threat: bool = False  # the attack target already carries Energy -> closest to attacking
    target_hp: int | None = None    # HP of the targeted benched Pokémon (None off a Damage option)
    target_is_weakest: bool = False  # this snipe target has the least HP on the opponent's Bench
    target_forward_damage: int | None = None  # Evolving Threat signal (ADR-0020): max damage the
                                              # snipe target's evolution line eventually reaches
                                              # (None off a Damage option / no chain / no provider)
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
    deferred: bool = False       # a turn-ending attack held behind beneficial development (attack-last)


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
        board = self._board(obs, select)
        traces = [self._option_trace(obs, select, board, o, i) for i, o in enumerate(options)]
        max_count = select.get("maxCount", 0)
        order = sorted(range(len(options)), key=lambda i: traces[i].score, reverse=True)
        order = self._finish_turn_last(options, traces, order, max_count, select.get("context"))
        return Decision(chosen=order[:max_count], options=traces)

    def _finish_turn_last(self, options: list, traces: list, order: list, max_count: int,
                          select_context: int | None) -> list:
        """Sequence the turn's commitments LAST. The engine re-presents the open turn menu after each
        non-ending action, so the whole turn still happens — which means you should take the most
        informative, reversible actions first and the irreversible ones last:

          tier 0  informative development — draw / search, fill the Bench, evolve a benched Pokémon,
                  play a Pokémon. Free, and reveals a better target before you commit.
          tier 1  the Energy attach — the one irreversible per-turn commitment. Dig first, THEN attach.
          tier 2  the turn-ENDING attack, plus Retreat / End / non-beneficial options.

        An option is sequenced early only when a Hypothesis endorses it (score > 0). A knockout is
        never forfeited: an Evolve of the Active drops to tier 2 when a KO is on the menu, and the KO
        attack outscores everything else in tier 2. Stable within a tier (keeps the score order).
        Only at a single-pick MAIN menu; every other context (snipe, search, mulligan) is untouched."""
        if max_count != 1 or len(order) < 2 or select_context != _MAIN:
            return order
        ko_available = any(options[i].get("type") == _ATTACK and traces[i].tactical >= KO_SCORE
                           for i in order)

        def _tier(i: int) -> int:
            o = options[i]
            t = o.get("type")
            if t in (_ATTACK, _END, _RETREAT):                       # turn-ender / swaps the Active
                return 2
            if t == _EVOLVE and o.get("inPlayArea") == _ACTIVE and ko_available:
                return 2                                             # would forfeit an available KO
            if traces[i].score <= 0:                                 # only an endorsed action sequences early
                return 2
            return 1 if t == _ATTACH else 0                          # attach (commit) after informative dev

        if any(_tier(i) < 2 for i in order):                         # legibility: mark the held-back attacks
            for i in order:
                if options[i].get("type") == _ATTACK:
                    traces[i].deferred = True
        return sorted(order, key=_tier)                             # stable -> within a tier, score order

    def _option_trace(self, obs: dict, select: dict, board: Board, option: dict,
                      index: int) -> OptionTrace:
        tactical = (self._tactical(obs, option)
                    + self._gust_tactical(obs, select, board, option)
                    + self._gust_target_tactical(obs, select, board, option)
                    + self._gust_stall_target_tactical(obs, select, board, option))
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

    def _gust_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for PLAYING a gust card (Function Tag `gust`, e.g. Boss's Orders) when
        the gust takes my LAST prize(s) — winning the game. Structural (not a tunable weight), so it
        lives in the Tactical layer like every other knockout rather than as a positional Hypothesis.
        Fires only when the best gustable KO reaches my remaining prize count AND a direct attack on
        the current Active does NOT (else just attack — don't spend the Supporter). 0 otherwise — the
        non-lethal gust is the tunable `gust-for-the-ko` Hypothesis. ADR-0022."""
        if option.get("type") != _PLAY:
            return 0
        cid = self._option_card_id(obs, select, option)
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        mp = board.my_prizes_remaining
        if ("gust" in tags and mp > 0
                and board.gust_best_ko_prizes >= mp and board.active_ko_prizes < mp):
            return KO_SCORE + board.gust_best_ko_prizes
        return 0

    def _gust_target_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for a gust TARGET option — at a SWITCH select, choosing WHICH of the
        opponent's benched Pokémon to drag into the Active Spot (Boss's Orders; ADR-0022). Scores each
        opponent-owned bench target by whether my Active can KO it after the gust, plus its prize value,
        so the agent drags up the most valuable KO-able body. Guarded to opponent-owned options
        (`playerIndex != yourIndex`) because SWITCH is ALSO my own retreat. 0 for an un-KO-able target
        (a non-KO gust is a blunder) and off any non-gust SWITCH option. The threat / evolving-threat /
        weakest tie-breaks among equal targets are the (widened) snipe Hypotheses."""
        if (select.get("context") != _SWITCH or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return 0
        yi = (obs.get("current") or {}).get("yourIndex", 0)
        if option.get("playerIndex", yi) == yi:          # my own retreat, not a gust of the opponent
            return 0
        target = self._option_pokemon(obs, select, option)
        if not target:
            return 0
        my_stat = self.stats.get(board.my_active_id) if self.stats else None
        if not self._can_ko(my_stat, target):
            return 0
        return KO_SCORE + self._prize_value(target) + self._gust_target_denial(board, target)

    def _gust_stall_target_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """Small value for a defensive stall-gust TARGET — at a SWITCH select, an ENERGYLESS,
        high-retreat (>= `_STALL_RETREAT`) opponent benched Pokémon is the body to strand Active (it
        can't attack and costs them a retreat). Scaled by `retreatCost` so the most expensive-to-retreat
        body wins; far below a KO target's KO_SCORE, so it only decides among non-KO options (a real KO
        always outranks a stall). Owner-guarded; 0 otherwise. ADR-0022."""
        if (select.get("context") != _SWITCH or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return 0
        yi = (obs.get("current") or {}).get("yourIndex", 0)
        if option.get("playerIndex", yi) == yi:
            return 0
        target = self._option_pokemon(obs, select, option)
        if not target or (target.get("energies") or []):       # energized -> not a stall body (a gift)
            return 0
        stat = self.stats.get(target.get("id")) if self.stats else None
        return stat.retreatCost if (stat and stat.retreatCost >= _STALL_RETREAT) else 0

    def _gust_target_denial(self, board: Board, target: dict) -> int:
        """Defensive value of removing `target` via the gust: if it is a LIVE threat — it carries
        Energy AND its biggest attack (weakness-doubled vs my Active) would KO my Active — return my
        Active's prize value, so a live attacker that would take my win-condition outranks a bigger but
        INERT prize (prizes-first is a trap; ADR-0022). 0 for an inert / non-threatening target."""
        if not (self.stats and target and (target.get("energies") or [])):
            return 0
        t_stat = self.stats.get(target.get("id"))
        if not t_stat:
            return 0
        incoming = t_stat.maxDamage or 0
        my_stat = self.stats.get(board.my_active_id)
        if (my_stat and my_stat.weakness is not None and t_stat.energyType is not None
                and my_stat.weakness == t_stat.energyType):
            incoming *= 2
        if board.my_active_hp and incoming >= board.my_active_hp:
            return self._prize_value({"id": board.my_active_id})
        return 0

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
        card_is_line_preevo = cid is not None and cid in self._line_preevo_set()
        card_is_wincon = cid is not None and cid in self._wincon_set()
        is_attack = option.get("type") == _ATTACK
        target_energy = self._target_energy(obs, select, option)
        target_hp = self._target_hp(obs, select, option)
        target_is_weakest = (target_hp is not None and board.weakest_bench_hp is not None
                             and target_hp == board.weakest_bench_hp)
        target_forward_damage = self._target_forward_damage(obs, select, option)
        at_target = self._attach_target(obs, option)   # the Pokémon an attach option puts Energy on
        at_roles = self.strategy.roles.get(at_target.get("id"), []) if at_target else []
        return Context(plan=plan, select_context=select.get("context"),
                       option_type=option.get("type"), card_id=cid, option_area=option.get("area"),
                       attach_target_area=option.get("inPlayArea"), attach_target_roles=at_roles,
                       attach_target_needs=self._attach_target_needs(at_target),
                       card_is_line_preevo=card_is_line_preevo, card_is_wincon=card_is_wincon,
                       target_energy=target_energy, target_is_threat=bool(target_energy),
                       target_hp=target_hp, target_is_weakest=target_is_weakest,
                       target_forward_damage=target_forward_damage,
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

    def _attach_target_needs(self, target: dict | None) -> bool:
        """True if the Pokémon an attach option targets still needs Energy to attack — it carries
        fewer Energy than its cheapest attack cost. Lets `power-up-attacker` fire only on a Pokémon
        that benefits from the attachment, so the agent spreads Energy to the bare bench attacker
        instead of piling a needless surplus on an already-online one (the over-attach blunders).

        Fail-open: when the receiving Pokémon (or its attack cost) can't be resolved, assume it
        needs Energy — only SUPPRESS the attachment when we can positively confirm the target is
        already online, so a missing-target option keeps the default attach-every-turn behavior."""
        if not target:
            return True
        have = len((target.get("energies") or []))
        return have < _min_attack_cost(self.stats, target.get("id"))

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

    def _target_hp(self, obs: dict, select: dict, option: dict) -> int | None:
        """Remaining HP of the benched Pokémon an attack-target option points at — the snipe
        'weakest' signal (lowest HP = closest to a knockout). Defined only for bench attack-target
        options (DAMAGE / CARD / BENCH); None otherwise (cf. ``_target_energy``)."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        poke = self._option_pokemon(obs, select, option)
        return (poke or {}).get("hp") if poke else None

    def _target_forward_damage(self, obs: dict, select: dict, option: dict) -> int | None:
        """Max damage the benched snipe target's evolution line eventually reaches — the Evolving
        Threat signal (ADR-0020): a fragile pre-evolution worth sniping before it comes online.
        Defined only for bench attack-target options (DAMAGE / CARD / BENCH).

        FAIL-CLOSED by construction (``_context`` is not exception-wrapped): returns None whenever
        the provider, the method, the target Pokémon, its card id, or a forward chain is missing —
        so a gap leaves the signal silent rather than crashing the decision."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        fwd = getattr(self.stats, "forward_max_damage", None)   # None if no/old provider
        if fwd is None:
            return None
        poke = self._option_pokemon(obs, select, option)
        cid = (poke or {}).get("id")
        return (fwd(cid) or None) if cid is not None else None

    def _board(self, obs: dict, select: dict | None = None) -> Board:
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
            incoming_active_damage=self._incoming_active_damage(ma, oa),
            active_cheap_attack_kos=self._active_cheap_attack_kos(ma, oa),
            gust_best_ko_prizes=self._gust_best_ko_prizes(ma, opp),
            active_ko_prizes=self._active_ko_prizes(ma, oa),
            my_prizes_remaining=len(me.get("prize") or []),
            reusable_energy_in_hand=self._has_reusable_energy(me.get("hand") or []),
            wincon_in_play=self._wincon_in_play(me),
            wincon_in_hand=self._wincon_in_hand(me),
            line_preevo_in_play=self._line_preevo_in_play(me),
            weakest_bench_hp=self._weakest_snipe_hp(obs, select),
            bench_wincon_ready=self._bench_wincon_ready(me),
            active_is_wincon=bool(ma) and ma.get("id") in self._wincon_set(),
            stall_target_exists=self._stall_target_exists(opp),
        )

    def _wincon_set(self) -> set:
        """Card ids that ARE the win-condition — a Strategy Line payoff or a card carrying the
        `win_condition` / `primary_attacker` Role."""
        wincon = {line.payoff for line in self.strategy.lines}
        wincon |= {cid for cid, r in self.strategy.roles.items()
                   if {"win_condition", "primary_attacker"} & set(r)}
        return wincon

    def _wincon_in_hand(self, me: dict) -> bool:
        """True if the win-condition card is already in my hand — a tutor needn't dig for another."""
        wincon = self._wincon_set()
        return bool(wincon) and any(c and c.get("id") in wincon for c in (me.get("hand") or []))

    def _line_preevo_set(self) -> set:
        """Card ids that are a non-payoff member of a Line's path — a pre-evolution that builds
        toward the win-condition payoff (e.g. Staryu on the Staryu → Mega Starmie line)."""
        return {cid for line in self.strategy.lines for cid in line.path if cid != line.payoff}

    def _line_preevo_in_play(self, me: dict) -> bool:
        """True if a non-payoff member of any Line's path (a pre-evolution) is on my Active/Bench —
        so a rush-evolve tutor has something to evolve toward the payoff."""
        preevos = self._line_preevo_set()
        if not preevos:
            return False
        board = (me.get("active") or []) + (me.get("bench") or [])
        return any(p and p.get("id") in preevos for p in board)

    def _bench_wincon_ready(self, me: dict) -> bool:
        """True if a benched win-condition / primary attacker already carries enough Energy to attack
        (>= its cheapest attack cost) — a powered finisher worth retreating into."""
        wincon = self._wincon_set()
        if not wincon:
            return False
        return any(p and p.get("id") in wincon
                   and len(p.get("energies") or []) >= _min_attack_cost(self.stats, p.get("id"))
                   for p in (me.get("bench") or []))

    def _weakest_snipe_hp(self, obs: dict, select: dict | None) -> int | None:
        """Least HP among the benched Pokémon a DAMAGE select can snipe — the target closest to a
        knockout (a prize). None off a Damage select. Resolves each option's target the same way
        the snipe Hypotheses do, so the owner/zone indexing matches `target_energy`."""
        if not select or select.get("context") != _DAMAGE:
            return None
        hps = []
        for o in (select.get("option") or []):
            if o.get("type") == _CARD and o.get("area") == _BENCH:
                poke = self._option_pokemon(obs, select, o)
                hp = (poke or {}).get("hp") or 0
                if hp:
                    hps.append(hp)
        return min(hps) if hps else None

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

    def _incoming_active_damage(self, ma: dict | None, oa: dict | None) -> int:
        """Closed-form estimate of the damage the opponent's Active would deal to my Active next turn
        — its biggest attack, doubled when my Active is Weak to the attacker's type. 0 when unknown.
        The magnitude behind `_active_doomed`; exposed on the Board so a +HP tool (Hero's Cape) can
        test whether it crosses a survival breakpoint."""
        if not (self.stats and ma and oa):
            return 0
        opp_stat = self.stats.get(oa.get("id"))
        if not opp_stat:
            return 0
        incoming = opp_stat.maxDamage or 0
        my_stat = self.stats.get(ma.get("id"))
        if (my_stat and my_stat.weakness is not None and opp_stat.energyType is not None
                and my_stat.weakness == opp_stat.energyType):
            incoming *= 2
        return incoming

    def _active_doomed(self, ma: dict | None, oa: dict | None) -> bool:
        """True if the opponent's Active can Knock Out my Active next turn — its biggest attack
        (doubled when my Active is Weak to the attacker's type) >= my Active's remaining HP. A
        closed-form threat estimate off engine stats (attack-affordability refinement is future)."""
        my_hp = (ma or {}).get("hp", 0)
        return bool(my_hp) and self._incoming_active_damage(ma, oa) >= my_hp

    def _can_ko(self, my_stat, defender: dict | None) -> bool:
        """My Active's CHEAPEST attack would Knock Out `defender` this turn — its cheapest-cost attack
        damage, doubled when the defender is Weak to my Active's type, >= the defender's remaining HP.
        The shared closed-form KO oracle (ADR-0022) behind both the current-Active KO checks and the
        gust whether-to-play signal. Fail-closed when stats / HP are missing."""
        hp = (defender or {}).get("hp", 0)
        if not (my_stat and hp):
            return False
        dmg = my_stat.minCostDamage or 0
        d_stat = self.stats.get(defender.get("id")) if self.stats else None
        if (d_stat and d_stat.weakness is not None and my_stat.energyType is not None
                and d_stat.weakness == my_stat.energyType):
            dmg *= 2
        return dmg >= hp

    def _active_cheap_attack_kos(self, ma: dict | None, oa: dict | None) -> bool:
        """True if my Active's cheapest attack KOs the opponent's CURRENT Active this turn — so a costly
        burst Energy (e.g. Ignition -> Nebula Beam) is unnecessary. The mirror of `_active_doomed`
        (me attacking them, cheapest attack), via the shared `_can_ko` oracle."""
        if not (self.stats and ma and oa):
            return False
        return self._can_ko(self.stats.get(ma.get("id")), oa)

    def _active_ko_prizes(self, ma: dict | None, oa: dict | None) -> int:
        """Prizes from Knocking Out the opponent's CURRENT Active with my cheapest attack this turn
        (0 if I can't) — the baseline a gust must beat (gusting benches their current Active, so a gust
        is only worth the Supporter for a strictly bigger KO)."""
        if not (self.stats and ma and oa):
            return 0
        return self._prize_value(oa) if self._can_ko(self.stats.get(ma.get("id")), oa) else 0

    def _gust_best_ko_prizes(self, ma: dict | None, opp: dict | None) -> int:
        """Best prizes among the opponent's benched Pokémon my Active could Knock Out this turn after
        gusting it to the Active Spot — the whether-to-play signal for a gust Supporter (ADR-0022).
        Applies the shared `_can_ko` oracle to each bench defender; the max `_prize_value` among the
        KO-able ones (0 if none). Closed-form off engine stats, no Search."""
        if not (self.stats and ma and opp):
            return 0
        my_stat = self.stats.get(ma.get("id"))
        best = 0
        for b in (opp.get("bench") or []):
            if b and self._can_ko(my_stat, b):
                best = max(best, self._prize_value(b))
        return best

    def _stall_target_exists(self, opp: dict | None) -> bool:
        """True if the opponent has an ENERGYLESS, high-retreat (>= `_STALL_RETREAT`) benched Pokémon —
        the defensive stall-gust candidate (drag it Active so they must spend a turn retreating it
        before they can attack). Energyless = can't attack once stranded; high-retreat = a real tempo
        cost. Closed-form off engine stats; needs `CardStat.retreatCost`. ADR-0022."""
        if not (self.stats and opp):
            return False
        for b in (opp.get("bench") or []):
            if not b or (b.get("energies") or []):
                continue
            stat = self.stats.get(b.get("id"))
            if stat and stat.retreatCost >= _STALL_RETREAT:
                return True
        return False

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
