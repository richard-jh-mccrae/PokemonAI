# Evaluation statistics

`sim.eval_run` retains the pure statistical planning contract from the retired legacy evaluation
runner. It does not run games or provide a command-line interface.

The helpers size paired common-opponent evaluations at 95% confidence and 80% power:

- `preset_delta()` resolves `quick` (5%), `default` (3%), and `fine` (2%).
- `per_arm_games()` calculates the total games required by one arm.
- `games_per_matchup()` spreads that total across opponents, rounding up.
- `matchup_cells()` creates the opponent-by-seat plan. Direct candidate-versus-baseline games are
  intentionally excluded because they are informational rather than part of the paired estimate.
