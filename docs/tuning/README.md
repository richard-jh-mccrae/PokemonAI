# Tuning docs

How the agent learns from flagged mistakes, and the record of each tuning run.

- **[methodology.md](methodology.md)** — how it works, from first principles + the actual math
  (linear scoring, ranking labels, soft-margin perceptron, regularisation, the pocket, the adoption
  gate, W-vs-H). Written for a non-specialist and for explaining the process to a data scientist.
- **[runs/](runs/)** — one succinct Markdown report per `/blunder-buster` run: what was tuned, why,
  and by how much; the new-rule proposals; and the corrections that still need a rule. `tune.py`
  writes the diagnosis; the skill appends the rules it authored + the retest before/after.
