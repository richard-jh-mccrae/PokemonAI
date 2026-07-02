# Phase B — author the executable `strategy.py` (gated; human commits)

Only after the doc is signed off. This turns the locked doctrine into the real
`Strategy(name, lines, roles, params, hypotheses)` the Pilot plays, and proves it before the human
commits. Mirror the shape of `/blunder-buster` steps 3–8 — the difference is a fresh deck has **no
Corrections**, so the accuracy gate is per-Hypothesis trigger checks + suite-green + Playability
(not the weight-fitting Verifier).

## 1 · Author against the LIVE source — never from memory

These files drift; read them now, don't trust this doc's snapshot of them:

- **`src/common/pilot.py`** — the `Context` and `Board` fields a `when(ctx)` may read. This is the
  *only* vocabulary a trigger has. Common fields seen in existing rules: `c.plan`, `c.option_type`,
  `c.select_context`, `c.tags`, `c.roles`, `c.stat`, `c.is_attack`, `c.is_ko`, `c.tactical`,
  `c.option_area`, `c.target_is_threat`, `c.attach_target_area`, `c.attach_target_roles`, and
  `c.board.*` (`my_bench`, `turn`, `active_doomed`, `hand_startable`, `wincon_in_play`,
  `my_active_energy`, `reusable_energy_in_hand`, …). **Confirm each field exists before using it.**
- **`src/cg/api.py`** — `SelectContext` / `OptionType` / `AreaType` / `EnergyType` int values. Pull
  the constants you need as module-level ints with a comment (mirror the existing strategy files).
- **`src/common/cards.py`** + the dump — the Function **tags** available on `c.tags`.
- **`src/common/strategy/baseline/baseline_*.py`** (deck-agnostic rules, clustered by
  decision-context; ADR-0025) + **`src/agents/<deck>/strategy.py`** — existing Hypotheses
  as **style examples**. Match their shape exactly: a pure, total `lambda c: …` predicate, a seed
  `weight` in-band ([docs/weights.md](../../../docs/weights.md)), `status="assumed"`, a `rationale`
  that reads as plain competitive reasoning.

## 2 · Map each doc disposition to code

| Doc disposition | Code |
|---|---|
| covers-as-is | nothing — the General Strategy already fires |
| override-candidate (seed weight) | a `{hyp_id: weight}` entry — seed it in `src/agents/<deck>/tuned.json` (the machine-overrides file `main.py` loads), or as a deck Hypothesis re-stating the id only if it must be deck-conditional |
| conflicts | override the offending id toward `0`, and/or a deck Hypothesis that outweighs it — document why |
| gap → new Hypothesis | **GENERAL (the priority):** if the trigger reads only universal `tags`/`roles`/`board`/`stat` and helps *any* deck, add it to the matching `src/common/strategy/baseline/baseline_<context>.py` cluster (ADR-0025) — flag the promotion for separate review. **DECK (otherwise):** a new `Hypothesis(...)` in `strategy.py` when it reads `card_id`s / the Line / deck roles, or must override a misplaying general rule |
| Role / Line / param | fill `roles={cardId: [...]}`, `lines=[Line(path=[...], payoff=...)]`, `params={...}` |

This is the §4 expand-vs-override decision, made executable. **Default toward expanding the General
Strategy** — a universal rule (reads only tags/stat/board/roles) lifts every future deck, so it's the
priority when it applies; it goes in the matching `strategy/baseline/baseline_<context>.py` cluster.
Only genuinely deck-bound rules (read `card_id`s / deck `roles` / the deck's Line, or override a
general rule that misplays *this* deck) go in `strategy.py`. When unsure, keep it in the deck file —
local is safe; promotion to general is a deliberate, separately-reviewed step.

## 3 · Gate 1 — per-Hypothesis trigger checks (the from-scratch Verifier)

For **each** authored Hypothesis, write a test that builds the engine observation by hand and
asserts the trigger fires where intended and **not** on an obvious counter-case. Use
`tests/pilot_helpers.py` (lib-free — no native engine needed). The pattern, from
`tests/strategy/test_general_strategy.py`:

```python
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from pilot_helpers import make_select, state, opt, poke, PLAY  # etc.
from agents.<deck>.strategy import STRATEGY   # or import the candidate Hypothesis directly

def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}

def test_<id>_fires_on_intended_and_not_counter():
    pilot = Pilot(STRATEGY, deck=[1]*60, general_strategy=GENERAL_STRATEGY, stats=..., functions=...)
    intended = make_select([opt(PLAY, area=HAND, index=0)], current=state(...intended board...))
    assert "<id>" in _fired(pilot.explain(intended).options[0])
    counter = make_select([opt(PLAY, area=HAND, index=0)], current=state(...counter board...))
    assert "<id>" not in _fired(pilot.explain(counter).options[0])
```

Put these in `tests/test_<deck>_triggers.py`. Tag each with `@pytest.mark.req(...)` if you mint REQ
ids. **Too narrow** → the intended assert fails (broaden the trigger). **Too broad** → the counter
assert fails (tighten it). Iterate until both hold for every authored rule.

## 4 · Gate 2 — suite-green

`python -m pytest tests/ -q` must stay green. This catches a trigger that over-fires on existing
behaviour or breaks another deck / the Pilot's Playability invariants.

## 5 · Gate 3 — Playability on the real engine

`python tools/sim/check_agent.py <deck>` — runs a full self-match and the packaged Bundle. It must
pass with no crash, timeout, or illegal move. This is the literal "ready to be played" bar; a
strategy that loads and tests green but times out in a real game is not done.

## 6 · Present the diff — the human commits

Show `src/agents/<deck>/strategy.py` + `tests/test_<deck>_triggers.py` (+ `tuned.json` if you
seeded overrides) as a diff, with a one-line note per Hypothesis: id, the doctrine it encodes, seed
weight + band, and the trigger-check result. Set `status="assumed"` (or `"testing"` once you've
exercised it). The ladder A/B is the only thing that promotes a rule to `confirmed`/`refuted` — the
skill never self-validates that. The human reviews and commits.

## Anti-patterns

- A trigger that reads a `card_id` when a `tag`/`role` would do — brittle, doesn't generalise.
- A trigger referencing a `Context` field that doesn't exist — it'll throw or silently never fire.
  Author against `pilot.py`, not memory.
- A positional weight that can suppress a **Knock Out** — a KO outranks any heuristic
  ([[forgo-ko-corrections-are-refuted]]). If a rule could fire on a lethal option, gate it out.
- Inventing final tuned weights — you seed; the ladder tunes. Seeds belong in-band, not precision-
  fitted by hand.
