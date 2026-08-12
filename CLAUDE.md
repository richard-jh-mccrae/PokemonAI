# PokémonAI repository guide

The sole agent decision system is the shared Bellman runtime in `src/common/` and
`src/common/runtime.py`. Decks may declare Roles, evolution Lines, starter order, partners, prize
routes, and preferred start in `src/agents/<deck>/strategy.py`; do not add deck-local tactical code.

Always verify rules in `docs/rules.md` / `docs/rulebook.txt` and card facts in
`data/EN_Card_Data.csv` or the engine-backed stat provider. The simulator is authoritative.

Keep Windows and Linux compatibility. Run `python -m pytest tests -q` before publication.
Packaging must remain self-contained and must
not reintroduce Pilot, weighted hypotheses, composer, state-value, decider, or tuner fallbacks.
