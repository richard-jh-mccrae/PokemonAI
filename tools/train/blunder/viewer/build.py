"""Vendor + build the official cabt visualizer for offline use (ADR-0014).

One-time setup: clones Kaggle/kaggle-environments, builds the cabt visualizer with
pnpm (via corepack), and copies the self-contained ``dist`` into ``./dist`` so the
tagging shell's iframe and ``env.render(mode="html")`` work fully offline. Re-run after
bumping the installed ``kaggle-environments`` version. Requires Node + corepack.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent                 # tools/train/blunder/viewer
SRC = HERE / ".src"                                    # gitignored working clone
REPO_URL = "https://github.com/Kaggle/kaggle-environments.git"
VIS_DIR = "kaggle_environments/envs/cabt/visualizer/default"
# package name per VISUALIZER_README ("@kaggle-environments/<name>-visualizer")
FILTER = "@kaggle-environments/cabt-visualizer"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True, shell=(sys.platform == "win32"))


def main() -> None:
    if not SRC.exists():
        run(["git", "clone", "--depth", "1", REPO_URL, str(SRC)])
    # invoke pnpm through corepack — no global shim needed; scope install to the
    # visualizer package and its workspace deps (trailing '...')
    run(["corepack", "pnpm", "install", "--filter", FILTER + "..."], cwd=SRC)
    run(["corepack", "pnpm", "--filter", FILTER, "build"], cwd=SRC)

    dist_src = SRC / VIS_DIR / "dist"
    if not dist_src.exists():
        raise SystemExit(f"build produced no dist at {dist_src} -- check the --filter name")
    dst = HERE / "dist"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(dist_src, dst)
    print("vendored official cabt viewer ->", dst)


if __name__ == "__main__":
    main()
