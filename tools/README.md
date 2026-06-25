# tools/

Offline build & maintenance scripts. Run from the repo root. Most are pure-Python and read the
card pool from `cards.json`; only `dump_cards`, `build_card_functions`, and `check_agent` load the
native `cg` engine (`my_submissions/cg`). Each script's module docstring has the full usage;
deeper design docs live under `docs/`.

## On a Standard-format update (new set / rotation)

The legal card pool changed → drop the new `cg` engine into `my_submissions/cg`, then regenerate
the data products **in order** (each step reads the previous output):

1. **`python tools/meta_tracker/dump_cards.py`** — refresh `cards.json` from the new engine.
   *Foundation: every tool below reads it.*
2. **`python tools/build_card_functions.py --fresh`** — rebuild the function-tag table
   (`common/card_functions.json`) for the new pool. `--fresh` drops rotated-out cards; then
   **re-run without `--fresh` a few times** to accumulate the rng-gated tags
   (recycle/heal/energy_accel — coverage is monotonic, see `docs/card-functions.md`).
3. **`python tools/build_scouting_artifact.py`** — recompile the scouting artifact
   (`common/scouting/artifact.json`). Needs the meta store; run the daily fetch first if stale.
4. **Re-validate decks**: `python tools/deck_convert.py to-csv <deck.txt> <name>` hard-fails on
   now-illegal cards; then `python tools/sim/check_agent.py <name>`.
5. **`python tools/package_agent.py <name>`** — re-bundle for submission.

## Tool reference

| Tool | Does | Run |
|---|---|---|
| `meta_tracker/dump_cards.py` | Engine pool → `cards.json` (the cache every tool reads) | `python tools/meta_tracker/dump_cards.py` |
| `build_card_functions.py` | Probe the engine → function-tag table `common/card_functions.json`; **accumulates** across runs | `python tools/build_card_functions.py [--fresh] [--limit N]` |
| `audit_card_functions.py` | Cross-check the tag table against card **text** (independent oracle) → flags suspect false-positives / misses | `python tools/audit_card_functions.py [--show 15]` |
| `verify_meta_cards.py` | Same check but **ranked by real usage** in the meta DB → flag-only review list of the popular cards whose tags look wrong (e.g. Munkidori) | `python tools/verify_meta_cards.py [--top 120]` |
| `build_scouting_artifact.py` | Meta store + `cards.json` → `common/scouting/artifact.json` | `python tools/build_scouting_artifact.py [--half-life 21] [--min-episodes 50]` |
| `run_meta_tracker.py` | Daily fetch: download top episodes, band by rating, parse, build HTML dashboard | `python tools/run_meta_tracker.py [--bands Elite High] [--cap 500]` |
| `deck_convert.py` | Limitless `.txt` ↔ `deck.csv` (resolves by card name, asserts the 5 deck rules) | `python tools/deck_convert.py to-csv <deck.txt> <name> [--force]`  ·  `to-txt <deck.csv> [-o out.txt]` |
| `deck_stealer.py` | Pull a team's exact 60-card deck out of a replay → `agents/<name>/deck.csv` | `python tools/deck_stealer.py <replay.json[.gz]> <team> <name> [--force]` |
| `package_agent.py` | Stage agent + `common/` + `cg/` and zip → `dist/<name>.zip` (the shipped bundle) | `python tools/package_agent.py <name> [--out dist]` |
| `sim/check_agent.py` | Gated pre-submit check: contents → legality → playability → deployability | `python tools/sim/check_agent.py <name> [--matches 5] [--no-deployability]` |

Deps: native `cg` for `dump_cards` / `build_card_functions` / `check_agent`; `check_agent`'s
self-play also needs `kaggle_environments` (`tools/sim/requirements.txt`). The rest are
pure-Python. Tests: `python -m pytest tests/ -q`.
