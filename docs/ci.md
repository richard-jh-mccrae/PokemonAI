# Continuous integration

`.github/workflows/ci.yml` has two Linux/Python 3.12 jobs:

1. the full retained test suite against the native engine;
2. Bellman and parity tests with the pure-Python cgpy engine selected.

Run the same primary check locally with:

```bash
python -m pytest tests -q
```

The former decider, leaf, tuner, composer, and value-stack gates were deleted with those systems.
