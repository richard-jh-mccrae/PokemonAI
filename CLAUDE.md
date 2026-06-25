Codebase for the Kaggle **Pokémon TCG AI Battle Challenge — Strategy** competition. Goal: a Python agent that builds a deck and plays the Pokémon TCG (NOT Pokemon TCG Pocket mobile app) via a provided native simulator. Strategy category = the agent's decision-making/search approach is the deliverable.

## Conventions (override global standards)

- **Windows + Linux are both first-class.** Dev/build is on Windows; the Kaggle grader is
  Linux — both must work. `.github/workflows/ci.yml` runs the pytest suite + the Scouting
  coverage gate on `windows-latest` and `ubuntu-latest` (Python 3.12). The committed
  `cg/cg.dll` (Windows) and `cg/libcg.so` (Linux) let the native engine load on both, so the
  whole suite runs offline. Keep code cross-platform: `pathlib` not string paths, explicit
  `encoding="utf-8"`, no OS-only assumptions.
- **CI runs tests only.** The rest of the global CI spec (Doxygen / Sphinx / GitHub Pages /
  PDF) stays out until those toolchains exist here. Run locally: `python -m pytest tests/ -q`.
  Details: `docs/ci.md`.

## Secrets

`kaggle_api_token/` holds a real Kaggle API token (`instructions.txt`). **Never commit it or paste the token into code, configs, or chat.** A root `.gitignore` already excludes `kaggle_api_token/`, `data/meta/`, and `reports/`; the Kaggle CLI reads the token from `KAGGLE_API_TOKEN` or `%USERPROFILE%\.kaggle\access_token` (preferred for the scheduled task).
