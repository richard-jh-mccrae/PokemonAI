"""`submit`: upload a prior build to the Simulation competition (ADR-0019).

Takes a build id (default: the most recent build) — it uploads that build's *exact* zip, never
re-packaging. Gated: refuses a `-dirty` build (so every leaderboard point maps to a commit),
runs the Agent Check, composes the `-m` message, uploads, then records to the committed
`agent_history.jsonl`. Kaggle's ref + score are filled in later by `collect`.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from submit.build import DEFAULT_BUILDS, DEFAULT_HISTORY, DEFAULT_OUT
from submit.history import append_history, read_history

COMPETITION = "pokemon-tcg-ai-battle"   # the Simulation track — agent's graded slug (ADR-0019)
DEFAULT_REPORTS = Path(__file__).resolve().parents[2] / "reports"
DEFAULT_KAGGLE_UPLOAD_TIMEOUT_SECONDS = 120


def compose_message(row: dict) -> str:
    """The `-m` message: the join key (submission id) + a readable state digest."""
    s = row["summary"]
    msg = (f"#{row['submission_id']} {row['agent']} @{row['git_hash']} · Bellman · "
           f"roles:{s['roles']} · lines:{s['lines']} · "
           f"scouting:{'on' if s['scouting'] else 'off'}")
    return msg + (f" · {row['label']}" if row.get("label") else "")


def _default_check(zip_path: Path, name: str):
    import tempfile
    from sim.check_agent import Report, check_artifact

    print(f"checking exact artifact {zip_path.name} (one mirror match)...", flush=True)
    # Windows can briefly retain a native DLL mapping after a timed-out child exits. Cleanup must
    # never replace the real gate result with an unrelated PermissionError traceback.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        stage = check_artifact(
            zip_path, Path(tmp), reports_dir=DEFAULT_REPORTS, label=name)
    return Report(name, [stage])


def _default_upload(zip_path: Path, message: str) -> None:
    import subprocess

    print(f"artifact check passed; uploading {zip_path.name} to {COMPETITION}...", flush=True)
    try:
        subprocess.run(
            ["kaggle", "competitions", "submit", COMPETITION,
             "-f", str(zip_path), "-m", message],
            check=True,
            timeout=DEFAULT_KAGGLE_UPLOAD_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise SystemExit("Kaggle CLI is unavailable; install it and authenticate with `kaggle auth login`.") from exc
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(
            f"Kaggle upload exceeded {DEFAULT_KAGGLE_UPLOAD_TIMEOUT_SECONDS}s; "
            "upload was not recorded locally. Check Kaggle before retrying."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Kaggle upload failed (exit {exc.returncode}); submission was not recorded locally."
        ) from exc


def _resolve(rows: list[dict], build_id: int | None) -> dict:
    if not rows:
        raise SystemExit("no builds yet — run `build <agent>` first")
    if build_id is None:
        return rows[-1]                                  # default: most recent build
    row = next((r for r in rows if r["submission_id"] == build_id), None)
    if row is None:
        raise SystemExit(f"no build #{build_id} in the ledger")
    return row


def submit(build_id: int | None = None, *, out=DEFAULT_OUT, builds=DEFAULT_BUILDS,
           history=DEFAULT_HISTORY, agents_root=None, allow_dirty=False, when=None,
           check_fn=None, upload_fn=None) -> dict:
    """Upload the chosen build (default: latest) and record it. Raises SystemExit *before*
    uploading on any gate failure."""
    row = dict(_resolve(read_history(builds), build_id))   # copy: don't mutate ledger entry
    zip_path = Path(out) / f"{row['artifact']}.zip"
    if not zip_path.exists():
        raise SystemExit(f"build #{row['submission_id']} artifact missing: {zip_path} (rebuild it)")
    if "-dirty" in row["git_hash"] and not allow_dirty:
        raise SystemExit(f"refusing to submit a dirty build ({row['git_hash']}); "
                         "rebuild on a clean commit, or pass allow_dirty=True")
    report = (check_fn(row["agent"], agents_root) if check_fn is not None
              else _default_check(zip_path, row["agent"]))
    if not report.ok:
        bad = next((s for s in getattr(report, "stages", []) if not s.ok), None)
        detail = bad.detail if bad is not None and bad.detail else "no diagnostic was returned"
        raise SystemExit(
            f"SUBMISSION BLOCKED [{report.failed_stage}]\n"
            f"Reason: {detail}\n"
            "Upload: not attempted"
        )
    row["message"] = compose_message(row)
    (upload_fn or _default_upload)(zip_path, row["message"])
    print("Kaggle accepted upload; recording local submission history...", flush=True)
    row["submitted_at"] = (when or datetime.now()).isoformat(timespec="seconds")
    append_history(history, row)
    return row
