"""Central configuration for the meta_tracker pipeline.

Paths are resolved relative to the repo root so the package works regardless of
the current working directory.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PKG = Path(__file__).resolve().parent

# --- Data source ---------------------------------------------------------
COMPETITION = "pokemon-tcg-ai-battle"  # the Simulation comp (leaderboard for rating->band)
EPISODES_INDEX = "kaggle/pokemon-tcg-ai-battle-episodes-index"  # official daily top-episode export

# --- Paths ---------------------------------------------------------------
CARDS_JSON = PKG / "cards.json"
DATA_DIR = REPO / "data" / "meta"
DB_PATH = DATA_DIR / "meta.db"
DECKS_DIR = DATA_DIR / "decks"   # deck export: data/meta/decks/<slug>/ + index.json (gitignored)
REPORTS_DIR = REPO / "reports"
DASHBOARD = REPORTS_DIR / "meta_dashboard.html"

# --- Deck export ---------------------------------------------------------
EXPORT_TOP_N = 10            # clusters exported to DECKS_DIR (head of play-rate ranking; ADR-0027)

# --- Rank bands (percentile of the ladder, by participant rating) --------
# Contiguous over top 50%; episodes below 50th percentile are "lower rated"
# tier, dropped. (name, low_pct_inclusive, high_pct_exclusive).
BANDS: list[tuple[str, float, float]] = [
    ("Elite", 0.0, 2.0),
    ("High", 2.0, 10.0),
    ("Mid", 10.0, 50.0),
]

# --- Download budget (per run) -------------------------------------------
DAILY_EPISODE_CAP = 1500       # max new episode files downloaded per run (override with --cap)
LIST_PAGES_PER_DATASET = 5     # file-listing pages scanned per dataset per run (~200 ids/page).
                               # Kept small + cursor-resumed across runs, avoids ListDatasetFiles 403s.

# --- Politeness / robustness ---------------------------------------------
REQUEST_SLEEP_S = 0.3        # pause between CLI calls
MAX_RETRIES = 3
BACKOFF_BASE_S = 2.0
SUBPROCESS_TIMEOUT_S = 120   # per kaggle CLI call; a hung call can't freeze the run

# --- Archetype / strength heuristics -------------------------------------
MAIN_LINE_MIN_COPIES = 2     # a main line needs >= this many of its top stage
MAX_MAIN_LINES = 3           # up to three main lines name an archetype
SETTLED_MIN_EPISODES = 30    # sigma proxy: a submission is "settled" past this

# Consistency / tech "engine" Pokémon that should never *name* an archetype —
# appear across many decks, win-condition-agnostic. Forced to sub-line
# (still shown in usage stats). Matched by exact name or "<name> " prefix
# (so "Fezandipiti" also catches "Fezandipiti ex"). Editable list.
ENGINE_POKEMON = {
    "Dudunsparce", "Budew", "Munkidori", "Fezandipiti",
    "Squawkabilly", "Kirlia", "Mimikyu",
}
