Codebase for the Kaggle **Pokémon TCG AI Battle Challenge — Strategy** competition. Goal: a Python agent that builds a deck and plays the Pokémon TCG (NOT Pokemon TCG Pocket mobile app) via a provided native simulator. Strategy category = the agent's decision-making/search approach is the deliverable.

## Conventions (override global standards)

- **No CI for this repo.** Skip the global GitHub-Actions / `.github/workflows/ci.yml`
  mandate entirely — don't scaffold or maintain it, and don't treat CI as part of an
  accepted plan here. Tests and docs still apply (run the suite locally:
  `python -m pytest tests/ -q`).

## Secrets

`kaggle_api_token/` holds a real Kaggle API token (`instructions.txt`). **Never commit it or paste the token into code, configs, or chat.** A root `.gitignore` already excludes `kaggle_api_token/`, `data/meta/`, and `reports/`; the Kaggle CLI reads the token from `KAGGLE_API_TOKEN` or `%USERPROFILE%\.kaggle\access_token` (preferred for the scheduled task).
