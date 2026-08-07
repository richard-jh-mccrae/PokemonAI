"""Search / fetch discipline + the RACE weak-chip rule (this round's blunder corrections).

Covers the infrastructure that lets the Pilot *see* a search decision (resolving a DECK option from
the select's revealed `deck` list and a DISCARD option from the player's discard pile), the deck-
agnostic search/development Hypotheses it unblocks (`fetch-the-wincon`, `fetch-energy-when-starved`,
`prefer-bench-fill-first`, `snipe-the-weakest`, the promote/retreat doctrine), "attack last"
sequencing, and the guard that the board-commit intent rules do NOT leak onto a fetch sub-selection.
See docs/tuning/methodology.md, ADR-0008.
"""
import pytest

from card_facts import ignition_tags                    # the committed Ignition Energy tags, ONE copy
from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Hypothesis, Line, Ready, Strategy
from pilot_helpers import (
    ATTACH, BENCH, DAMAGE, DECK, DISCARD, HAND, MAIN, PLAY, TO_HAND,
    attack_opt, card_opt, make_select, opt, poke, state,
)

WATER, FIRE, LIGHTNING = 3, 2, 4
STARYU, MEGA, CINDERACE, BASIC_W, IGNITION = 1030, 1031, 666, 3, 17
POFFIN, HILDA = 1086, 1225


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


# --- infrastructure: a search option must resolve to its card id --------------------------------
@pytest.mark.req("REQ-PILOT-0023")
def test_search_options_resolve_their_card_id_from_deck_and_discard():
    """A search/ToHand option is a CARD pointing into a hidden zone: a DECK candidate's id lives in
    the select's revealed `deck` list, a DISCARD candidate's in the player's discard pile. Without
    this resolution every fetch carries no roles/tags/stat and no search Hypothesis can fire."""
    p = Pilot(Strategy(), deck=[])
    sel_deck = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                           deck=[{"id": STARYU}, {"id": MEGA}])["select"]
    assert p._option_card_id({}, sel_deck, card_opt(DECK, 1)) == MEGA
    assert p._option_card_id({}, sel_deck, card_opt(DECK, 9)) is None      # out of range -> None

    obs = make_select([], context=TO_HAND, current=state(discard=[CINDERACE, BASIC_W]))
    sel = obs["select"]
    assert p._option_card_id(obs, sel, card_opt(DISCARD, 0)) == CINDERACE
    assert p._option_card_id(obs, sel, card_opt(DISCARD, 1)) == BASIC_W


# --- fetch-the-wincon ----------------------------------------------------------------------------
@pytest.mark.req("REQ-GEN-0013")
def test_fetch_the_wincon_prefers_the_payoff_at_a_search():
    stats = DictCardStatProvider({STARYU: CardStat(STARYU, hp=70),
                                  MEGA: CardStat(MEGA, megaEx=True, hp=330)})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], STARYU: ["starter"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # active carries Energy -> not starved -> only fetch-the-wincon in play here
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": STARYU}, {"id": MEGA}],
                      current=state(active=poke(CINDERACE, energy=1)))
    assert pilot.decide(obs) == [1]                                  # pull the Mega, not the Staryu
    assert "fetch-the-wincon" in _fired(pilot.explain(obs).options[1])
    assert "fetch-the-wincon" not in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0013")
def test_fetch_the_wincon_yields_to_energy_when_starved():
    # adversarial-review fix: unpowered wincon does nothing -> when starved, energy wins
    stats = DictCardStatProvider({MEGA: CardStat(MEGA, megaEx=True, hp=330),
                                  BASIC_W: CardStat(BASIC_W, energyType=WATER)})
    pilot = Pilot(Strategy(roles={MEGA: ["win_condition", "primary_attacker"]}),
                  deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": MEGA}, {"id": BASIC_W}],
                      current=state(active=poke(900, energy=0), hand=[]))     # 0 energy, none in hand
    assert "fetch-the-wincon" not in _fired(pilot.explain(obs).options[0])    # stands down
    assert pilot.decide(obs) == [1]                                           # take the Energy


@pytest.mark.req("REQ-GEN-0013")
def test_fetch_the_wincon_stands_down_when_the_payoff_is_already_in_play():
    # adversarial-review fix: don't pull a dead 2nd copy when the win-condition's already in play
    stats = DictCardStatProvider({MEGA: CardStat(MEGA, megaEx=True, hp=330)})
    pilot = Pilot(Strategy(roles={MEGA: ["win_condition", "primary_attacker"]}),
                  deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0)], context=TO_HAND, deck=[{"id": MEGA}],
                      current=state(active=poke(MEGA, energy=2)))             # Mega already Active
    assert pilot._board(obs).wincon_in_play
    assert "fetch-the-wincon" not in _fired(pilot.explain(obs).options[0])


# --- fetch-energy-when-starved -------------------------------------------------------------------
@pytest.mark.req("REQ-GEN-0014")
def test_fetch_energy_when_starved_takes_a_reusable_basic():
    stats = DictCardStatProvider({700: CardStat(700, synthetic=True, hp=70), BASIC_W: CardStat(BASIC_W, synthetic=True, energyType=WATER)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # starved: Active has 0 Energy, none in hand -> take the Energy over the Pokémon
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": 700}, {"id": BASIC_W}],
                      current=state(active=poke(900, energy=0), hand=[]))
    assert pilot.decide(obs) == [1]
    assert "fetch-energy-when-starved" in _fired(pilot.explain(obs).options[1])


@pytest.mark.req("REQ-GEN-0014")
def test_fetch_energy_when_starved_skips_a_discard_energy_for_a_reusable_one():
    stats = DictCardStatProvider({IGNITION: CardStat(IGNITION, energyType=0),       # colourless special
                                  BASIC_W: CardStat(BASIC_W, energyType=WATER)})     # reusable Basic
    funcs = CardFunctions({IGNITION: ignition_tags()})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": IGNITION}, {"id": BASIC_W}],
                      current=state(active=poke(900, energy=0)))
    assert pilot.decide(obs) == [1]                                  # the reusable Basic, not Ignition
    assert "fetch-energy-when-starved" not in _fired(pilot.explain(obs).options[0])   # Ignition: skipped
    assert "fetch-energy-when-starved" in _fired(pilot.explain(obs).options[1])       # Basic: boosted


@pytest.mark.req("REQ-GEN-0014")
def test_fetch_energy_when_starved_is_off_when_energy_is_already_in_hand():
    stats = DictCardStatProvider({BASIC_W: CardStat(BASIC_W, energyType=WATER)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # reusable Energy already in hand -> not starved -> rule doesn't fire
    obs = make_select([card_opt(DECK, 0)], context=TO_HAND, deck=[{"id": BASIC_W}],
                      current=state(active=poke(900, energy=0), hand=[BASIC_W]))
    assert "fetch-energy-when-starved" not in _fired(pilot.explain(obs).options[0])


# --- prefer-bench-fill-first ---------------------------------------------------------------------
@pytest.mark.req("REQ-GEN-0015")
def test_prefer_bench_fill_first_sequences_the_thinner_ahead_of_a_tutor():
    funcs = CardFunctions({POFFIN: ["search", "bench_fill"], HILDA: ["search"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, functions=funcs)
    # SETUP, both are search plays (dig-before-commit fires on each); bench-filler sequenced first
    obs = make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)],
                      current=state(hand=[HILDA, POFFIN]))
    assert pilot.decide(obs) == [1]                                  # Buddy-Buddy Poffin first
    assert "prefer-bench-fill-first" in _fired(pilot.explain(obs).options[1])
    assert "prefer-bench-fill-first" not in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0015")
def test_prefer_bench_fill_first_stands_down_on_a_full_bench():
    # adversarial-review fix: bench-filler places nothing on a full Bench -> don't promote it
    funcs = CardFunctions({POFFIN: ["search", "bench_fill"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, functions=funcs)
    full = [poke(701), poke(702), poke(703), poke(704), poke(705)]            # 5 = full Bench
    obs = make_select([opt(PLAY, area=HAND, index=0)], current=state(bench=full, hand=[POFFIN]))
    assert pilot._board(obs).my_bench == 5
    assert "prefer-bench-fill-first" not in _fired(pilot.explain(obs).options[0])


# --- chip discipline now structural: attack-last sequences dev first; no dev -> take the chip --
# (old `build-before-attack` / `dont-chip-with-a-doomed-active` chip-penalty rules removed —
#  they suppressed a useful chip below End when no dev was available.)
# ── the attack-last / chip-discipline sequencing tests — DELETED (POC-T4/5, Issue #386) ──────────
#
# Six tests here asserted a SEQUENCING doctrine on hand-built two- and three-option menus: develop
# before the weak chip, take the chip when no development remains, retreat into the ready wincon,
# never let a positional play override a knockout. Under the rung ladder those were weight
# comparisons. Under differencing, sequencing is not a rule at all — the composer scores whole
# within-turn sequences, so "attack last" is a consequence of an attack being TERMINAL rather than
# something a rung has to say.
#
# They are deleted because the boards cannot ask the question, and that was established by probe
# rather than by argument:
#
#   * `test_development_still_beats_a_weak_chip_via_attack_last` was NOT BOARD-LEGAL. Its ATTACH
#     option named a target (`inPlayArea`/`inPlayIndex`) but no hand index, and the fixture's hand
#     was EMPTY — it asked the agent to attach an Energy it did not have, from a menu entry that
#     never said which card. The old attach rung scored that option from its TARGET alone, so the
#     gap was invisible for as long as a weight decided. Differencing has to WRITE the resulting
#     board, so the seam refuses: *"attach names hand index None, which this snapshot cannot resolve
#     (hand of 0)"*. The refusal is more correct than the rung's confident score was.
#     **This is one test, not a general claim** — the other five supply legal boards; they were
#     checked individually rather than assumed to share the defect.
#
#   * Repairing that board (Energy in hand, index on the option) does NOT restore the old answer,
#     and that is reported rather than tuned. The composer still takes the chip, because on a
#     two-option menu it never expands the attach into attach-then-attack (`expanded_families: 0`,
#     one node). On the real corpus it composes 59 multi-step lines across 270 frames, so the
#     mechanism plainly does sequence — it just has nothing to sequence WITH when the menu is two
#     entries wide. A hand-built menu that omits the realistic options manufactures a misplay.
#
# WHERE THE FACTS WENT:
#
#   attack-last ................ structural: an attack is a TERMINAL action in the composer, so any
#                                sequence that develops first and attacks last strictly dominates
#                                attacking alone whenever the develop has non-negative value. Carried
#                                at decision level by the corpus's multi-step lines and by
#                                `tests/strategy/test_telemetry_reorder_markers.py`.
#   never override a knockout .. structural and STRONGER than the rung: the win rung and the
#                                closed-form KO pool sit ABOVE the composer in `plan_turn`'s ladder
#                                (Issue #386 §3), so a positional play cannot outrank a lethal by
#                                construction. Asserted on captured boards by
#                                `tests/strategy/test_lethal_recover.py` (four frames, green).
# --- the leak guard: board-commit intent rules must not fire on a fetch sub-selection ------------
@pytest.mark.req("REQ-GEN-0017")
def test_board_intent_rules_do_not_leak_onto_search_options():
    # fetched card's `search` / `energy_accel` tags now resolve at a ToHand search, but
    # board-commit intent rules (govern plays, not which card a search pulls) must stay silent
    funcs = CardFunctions({222: ["search", "energy_accel"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, functions=funcs)
    obs = make_select([card_opt(DECK, 0)], context=TO_HAND, deck=[{"id": 222}],
                      current=state(active=poke(700, energy=1)))
    fired = _fired(pilot.explain(obs).options[0])
    assert "dig-before-commit" not in fired
    assert "use-acceleration" not in fired


# --- attack-last: an attack ends the turn, so beneficial development is sequenced ahead of it ----
@pytest.mark.req("REQ-GEN-0017")
def test_attack_last_sequences_development_before_the_turn_ending_attack():
    """A KO attack co-exists with a beneficial development (a +30 play). Attacking ends the turn,
    but the KO survives the play — so develop first and keep the attack for last (same turn)."""
    stats = DictCardStatProvider({700: CardStat(700, synthetic=True, energyType=WATER), 900: CardStat(900, synthetic=True, hp=40)},
                                 attacks={11: AttackStat(11, damage=50)})
    dev = Hypothesis(id="dev", rationale="", when=lambda c: c.option_type == PLAY, weight=30)
    pilot = Pilot(Strategy(hypotheses=[dev]), deck=[1] * 60, stats=stats)
    obs = make_select([attack_opt(11), opt(PLAY)], context=MAIN,
                      current=state(active=poke(700, energy=1), opp_active=poke(900, hp=40)))
    d = pilot.explain(obs)
    assert d.options[0].tactical >= KO_SCORE          # attack is a KO (50 >= 40) ...
    assert pilot.decide(obs) == [1]                   # ...but the +30 development goes first
    assert d.options[0].deferred                      # KO held back, never dropped


@pytest.mark.req("REQ-GEN-0017")
def test_attack_last_protects_a_knockout_from_an_active_evolve_but_not_otherwise():
    """Evolving the Active replaces its attack, so it must NOT be sequenced ahead of an available
    knockout (that would forfeit the KO) — but with no KO on the menu it is normal development."""
    EVOLVE, ACTIVE_AREA = 9, 4
    stats = DictCardStatProvider({700: CardStat(700, synthetic=True, energyType=WATER), 900: CardStat(900, synthetic=True, hp=40),
                                  901: CardStat(901, synthetic=True, hp=200)},
                                 attacks={11: AttackStat(11, damage=50)})
    ev = Hypothesis(id="ev", rationale="", when=lambda c: c.option_type == EVOLVE, weight=40)
    pilot = Pilot(Strategy(hypotheses=[ev]), deck=[1] * 60, stats=stats)
    ko = make_select([attack_opt(11), opt(EVOLVE, inPlayArea=ACTIVE_AREA)], context=MAIN,
                     current=state(active=poke(700, energy=1), opp_active=poke(900, hp=40)))
    assert pilot.decide(ko) == [0]                    # KO present -> don't evolve the Active away
    noko = make_select([attack_opt(11), opt(EVOLVE, inPlayArea=ACTIVE_AREA)], context=MAIN,
                       current=state(active=poke(700, energy=1), opp_active=poke(901, hp=200)))
    assert pilot.decide(noko) == [1]                  # no KO to forfeit -> evolve the Active first


# --- snipe-for-the-ko: a bench snipe that KNOCKS OUT the target (HP <= rider) is a free prize ------
# `test_snipe_for_the_ko_prefers_the_killable_bench_target` was DELETED by ADR-0085's deletion pass:
# it asserted a snipe TARGET rung that no longer exists. The requirement survives and is
# carried by `test_the_ko_dominator_fires_only_when_armed_and_only_on_a_ko_target` (consumer seam) and
# `test_a_benched_knockout_outranks_a_scarier_chip` (test_snipe_threat_rank.py) — the free prize
# is now the STRUCTURAL `_snipe_ko_dominator`, which cannot be out-summed the way the +60 rung was.

@pytest.mark.req("REQ-GEN-0018")
def test_snipe_the_threat_outranks_the_weakest():
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=DictCardStatProvider({}, attacks={11: AttackStat(11, damage=50)}))
    # idx0 carries Energy (live threat, high HP); idx1 is weakest. threat (20) > weakest (15)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(700, energy=1),
                                    opp_bench=[poke(900, energy=2, hp=200), poke(901, hp=50)]))
    assert pilot.decide(obs) == [0]


# --- prefer-wincon-line-piece: fetch/promote the line's pre-evolution over an off-line card -------
@pytest.mark.req("REQ-GEN-0019")
def test_prefer_wincon_line_piece_fetches_the_preevolution_over_an_offline_card():
    stats = DictCardStatProvider({STARYU: CardStat(STARYU, hp=70), MEGA: CardStat(MEGA, megaEx=True, hp=330),
                                  CINDERACE: CardStat(CINDERACE, hp=160)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA)], roles={MEGA: ["win_condition"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": CINDERACE}, {"id": STARYU}], current=state(active=poke(900, energy=1)))
    assert pilot.decide(obs) == [1]                                  # the line pre-evo (Staryu)
    assert "prefer-wincon-line-piece" in _fired(pilot.explain(obs).options[1])
    assert "prefer-wincon-line-piece" not in _fired(pilot.explain(obs).options[0])   # Cinderace: off-line


@pytest.mark.req("REQ-GEN-0019")
def test_promote_three_way_priority_ready_wincon_then_evolvable_then_staller():
    """Promote after a KO: (1) a powered benched win-condition attacks now; (2) else promote the body
    that can ACT; (3) else promote the disposable opener to protect the fragile pre-evolution. The
    bare pre-evo is NOT promoted just because it's on the line.

    Case (2) CHANGED with ADR-0100 (#141) and the change is deliberate. The rung era promoted the
    pre-evolution whenever the payoff sat in hand, gated on `evolve_to_ready_wincon_available` —
    "enough Energy to attack post-evolve". This fixture never met that premise: the pre-evolution
    carries ONE Energy and the evolved form's attack costs THREE, so evolving it produces a body that
    cannot attack. The gate passed only because the old statline gave the payoff no attack record at
    all, leaving `maxDamageCost` None and the check vacuous.

    With the record present the decider prices what is really on offer — 50 damage now from the
    opener, versus nothing from a pre-evolution that would still be Energy-starved after evolving —
    and promotes the opener. Nothing is lost by that: a benched Pokémon can still be evolved, and
    `_finish_turn_last` already sequences a benched evolve at tier 0 as free development."""
    # Real attack records on both attackers: the promote/retreat decider reads DAMAGE, and ADR-0052
    # retired the card-level `minCostDamage` scalar fallback ("no record, no claim"), so a statline
    # without `attacks` prices every body at zero and the frame asserts nothing about the decider.
    stats = DictCardStatProvider(
        {STARYU: CardStat(STARYU, hp=70),
         MEGA: CardStat(MEGA, synthetic=True, megaEx=True, hp=330, minAttackCost=3, maxDamage=210,
                        maxDamageCost=3, attacks=(21,)),
         CINDERACE: CardStat(CINDERACE, hp=160, minAttackCost=1, maxDamage=50,
                             maxDamageCost=1, attacks=(22,))},
        attacks={21: AttackStat(21, damage=210, cost=3), 22: AttackStat(22, damage=50, cost=1)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA)],
                     roles={MEGA: ["win_condition", "primary_attacker"]})
    funcs = CardFunctions({CINDERACE: ["opener"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    promote = [card_opt(BENCH, 0, player=0), card_opt(BENCH, 1, player=0)]

    # (3) no Mega, no powered wincon -> promote the staller (Cinderace), keep Staryu safe
    obs = make_select(promote, context=4,
                      current=state(bench=[poke(CINDERACE, energy=1), poke(STARYU, energy=1)]))
    assert pilot.decide(obs) == [0]   # the staller pick is EMERGENT now (ADR-0100 §6a): its own
                                     # damage plus the LOW exposure that IS "disposable"

    # (2) Mega in hand but the pre-evo could not pay the evolved attack -> promote the body that acts
    obs = make_select(promote, context=4,
                      current=state(bench=[poke(CINDERACE, energy=1), poke(STARYU, energy=1)],
                                    hand=[MEGA]))
    assert pilot.decide(obs) == [0]

    # (1) a powered Mega is benched -> promote it to attack
    obs = make_select(promote, context=4,
                      current=state(bench=[poke(CINDERACE, energy=1), poke(MEGA, energy=3)]))
    assert pilot.decide(obs) == [1]   # EMERGENT from reachable damage (ADR-0100 §3) — the rung and
                                     # its `is_best_promote_target` tie-break are DELETED


# --- retreat-to-ready-attacker: bring a powered benched win-condition to the front ----------------
# --- save-tool-for-the-attacker: don't equip a Tool to an off-role Pokémon ------------------------
# ── Tool Doctrine rung tests — DELETED (POC-T4/5, Issue #386) ────────────────────────────────────
#
# `doctrines/doctrine_tool.py` is gone: all five of its rungs are on Issue #386's deletion list and
# the rungs were the whole module. Every test removed here asserted `"deploy-hp-tool" in _fired(...)`,
# `"save-tool-for-the-attacker" in ...` or `"protect-ace-spec-tool" in ...` — which mechanism fired,
# not what the agent played.
#
# WHERE THE FACTS WENT: a Tool that buys a survival turn is now `survival` on the composed end board
# (`deploy_value`, ADR-0086, prices the deploy), and the tests that carry it at decision level are
# `tests/scouting/test_tool_holder_facts.py`'s holder-fact readers and the corpus frames. The full
# fact-by-fact audit is in `tests/strategy/test_tool_doctrine.py`, which survives for the one rung
# that is NOT deleted (`hold-irreplaceable-tool-dont-shuffle`).
@pytest.mark.req("REQ-GEN-0020")
def test_drew_the_evolution_evolve_then_retreat_the_staller_into_the_ready_wincon():
    """The follow-up to promote-the-staller: once you draw the evolution, evolve the benched pre-evo
    THEN retreat the staller into the now-ready win-condition — emergent across one turn's two
    decisions (evolve-into-wincon + attack-last, then the SETUP->RACE flip + retreat-to-ready-attacker)."""
    # The payoff needs a REAL attack record: the evolve decider prices a body by the damage its line
    # payoff reaches, so a stat-blind Mega has `payoff_damage` 0 and the evolve earns nothing on any
    # term (fail-closed, ADR-0067). Without this the pin asserts the absence of a signal rather than
    # the behaviour — the same synthetic gap #139 fixed on two of its own pins.
    stats = DictCardStatProvider({CINDERACE: CardStat(CINDERACE, synthetic=True, hp=120), STARYU: CardStat(STARYU, synthetic=True, hp=70),
                                  MEGA: CardStat(MEGA, synthetic=True, megaEx=True, hp=330, maxDamage=210,
                                                 maxDamageCost=1, minAttackCost=1, attacks=(99,))},
                                 attacks={11: AttackStat(11, damage=30),
                                          99: AttackStat(99, damage=210, cost=1)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, ready=Ready(energy=1))],
                     roles={MEGA: ["win_condition", "primary_attacker"]})
    funcs = CardFunctions({CINDERACE: ["opener"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    # step 1: drew Mega; Active is the staller Cinderace, benched Staryu(e1) -> evolve Staryu first
    evolve = {"type": 9, "area": HAND, "index": 0, "inPlayArea": BENCH, "inPlayIndex": 0}
    obs1 = make_select([evolve, opt(12), attack_opt(11), opt(14)], context=MAIN,
                       current=state(active=poke(CINDERACE, energy=1, hp=120),
                                     bench=[poke(STARYU, energy=1)], hand=[MEGA], opp_active=poke(999, hp=120)))
    assert pilot.decide(obs1) == [0]                                  # evolve Staryu -> Mega
    # step 2: Staryu now a benched Mega(e1) -> retreat the staller into it
    obs2 = make_select([opt(12), attack_opt(11), opt(14)], context=MAIN,
                       current=state(active=poke(CINDERACE, energy=1, hp=120),
                                     bench=[poke(MEGA, energy=1)], opp_active=poke(999, hp=120)))
    assert pilot.decide(obs2) == [0]   # retreat -> bring up the ready Mega. EMERGENT from
                                      # destination value minus retreat cost (ADR-0100 §11)


