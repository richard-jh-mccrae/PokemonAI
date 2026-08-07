"""The Turn Planner in parts: one module per ladder rung, each a `*Mixin` the `PlannerMixin` composes.

`wins` / `ladder` / `gamble` are the rungs in priority order and `ko_classes` is what they argue
over; `leaf` is what ranks any of them. `turn_line` and `readiness` carry records and constants
only. The spine keeps `plan_turn` and the commit decision, and nothing here imports it back."""
