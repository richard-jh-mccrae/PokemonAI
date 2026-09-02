from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    if GIT is None:
        pytest.skip("git unavailable; cannot verify line-ending policy")
    return subprocess.run(
        [GIT, *args],
        cwd=cwd,
        check=True,
        encoding="utf-8",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _check_attr(path: str, *attrs: str) -> dict[str, str]:
    proc = _git(REPO, "check-attr", *attrs, "--", path)
    result: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        _, attr, value = line.split(": ", 2)
        result[attr] = value
    return result


def _committed_probe_blob(tmp_path: Path, repo_name: str, payload: bytes) -> str:
    repo = tmp_path / repo_name
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "line-endings@example.invalid")
    _git(repo, "config", "user.name", "Line Endings Policy Test")
    (repo / ".gitattributes").write_bytes((REPO / ".gitattributes").read_bytes())
    (repo / "probe.py").write_bytes(payload)
    _git(repo, "add", ".gitattributes", "probe.py")
    _git(repo, "commit", "-q", "-m", f"commit {repo_name}")
    return _git(repo, "rev-parse", "HEAD:probe.py").stdout.strip()


@pytest.mark.req("REQ-LINEEND-0001")
def test_python_files_are_normalized_to_lf_by_policy():
    attrs = _check_attr("tests/__line_endings_probe__.py", "text", "eol")

    assert attrs == {"text": "set", "eol": "lf"}


@pytest.mark.req("REQ-LINEEND-0002")
def test_committed_data_and_native_wrapper_are_not_normalized_by_policy():
    data_attrs = _check_attr("data/__line_endings_probe__.json", "text")
    cg_attrs = _check_attr("src/cg/__line_endings_probe__.py", "text")

    assert data_attrs == {"text": "unset"}
    assert cg_attrs == {"text": "unset"}


@pytest.mark.req("REQ-LINEEND-0003")
def test_windows_and_linux_python_writes_commit_to_the_same_blob(tmp_path: Path):
    crlf_blob = _committed_probe_blob(tmp_path, "crlf", b"print('same')\r\n")
    lf_blob = _committed_probe_blob(tmp_path, "lf", b"print('same')\n")

    assert crlf_blob == lf_blob


@pytest.mark.parametrize("native_eol", ["lf", "crlf"])
def test_frozen_chain_bytes_are_independent_of_native_checkout(native_eol):
    if GIT is None:
        pytest.skip("git unavailable; cannot verify line-ending policy")
    path = "src/cgpy/defs/chain_overrides.json"
    assert _check_attr(path, "text", "eol") == {"text": "set", "eol": "crlf"}
    checked_out = subprocess.run(
        [GIT, "-c", f"core.eol={native_eol}", "cat-file", "--filters", f"HEAD:{path}"],
        cwd=REPO, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    assert checked_out == (REPO / path).read_bytes()
