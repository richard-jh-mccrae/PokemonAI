"""Extract the native engine's effect-DSL vocabulary from `src/cg/libcg.so` (ADR-0050).

The Linux build of the engine is not stripped: every `Chain::` effect primitive, `State::` game
op, and damage-pipeline free function is present as a mangled C++ symbol. This tool mines those
symbols and freezes them into `src/cgpy/defs/dsl_vocabulary.json` — names, parameter lists, and
arities. The vocabulary is the checklist the cgpy interpreter implements 1:1, and the drift
check (`--check`) fails loudly if a future engine update adds/changes symbols (the competition
warns enums may grow mid-competition — the same applies to the DSL).

Names and arities come from the binary; op *semantics* are pinned behaviorally by the parity
corpus, never assumed from a name.

Usage:
    python tools/parity/extract_dsl.py            # regenerate the committed vocabulary
    python tools/parity/extract_dsl.py --check    # exit 1 if the binary and the file disagree

Demangling uses `c++filt` when available (binutils; present in Git Bash on Windows and on the
Linux CI runner). Without it the tool still emits mangled names but cannot compute arities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SO_PATH = REPO / "src" / "cg" / "libcg.so"
OUT_PATH = REPO / "src" / "cgpy" / "defs" / "dsl_vocabulary.json"

# The engine families worth freezing. Chain:: is the effect DSL proper; State:: is the game-op
# surface the cgpy state model mirrors; the free functions are the damage/trigger pipeline.
_FREE_FUNCTIONS = (
    "CalcDamage",
    "AfterDamage",
    "AfterAbility",
    "AfterEffect",
    "AfterAttackDamageChangeCoin",
    "AfterAttackDamageChangeCoinUntilTail",
    "AfterAttackDamageChangeTargetCountEnemyCoin",
    "PullTrigger",
    "SelectedDisableAttack",
    "SelectedFirstEffect",
)

_MANGLED_RE = re.compile(rb"_Z[A-Za-z0-9_]+")
# Compiler clone suffixes (".cold", ".constprop.0", ".isra.0", ...) ride on the symbol name and
# would break demangling; the base mangled name is what matters.
_CLONE_SUFFIX_RE = re.compile(r"\.(cold|constprop|isra|part)(\.\d+)?$")


def extract_mangled(so_bytes: bytes) -> list[str]:
    """All distinct base mangled C++ names in the binary (clone suffixes stripped)."""
    names = set()
    for m in _MANGLED_RE.finditer(so_bytes):
        s = m.group().decode("ascii", errors="ignore")
        s = _CLONE_SUFFIX_RE.sub("", s)
        names.add(s)
    return sorted(names)


def demangle(names: list[str]) -> dict[str, str]:
    """mangled -> demangled via one batched c++filt call ({} if c++filt is unavailable)."""
    filt = shutil.which("c++filt")
    if not filt:
        return {}
    proc = subprocess.run(
        [filt], input="\n".join(names), capture_output=True, text=True, encoding="utf-8"
    )
    out = proc.stdout.splitlines()
    if len(out) != len(names):  # c++filt echoes one line per input line; anything else is broken
        return {}
    return dict(zip(names, out))


def split_params(sig: str) -> list[str] | None:
    """Top-level parameter type list of a demangled signature, or None if it has no arg list.

    `Chain::condition(ConditionType, int, ComparatorType)` -> ["ConditionType", "int",
    "ComparatorType"]. Handles nested template/paren commas by depth tracking; tolerates
    cv-qualifier suffixes (`State::getEffect() const`).
    """
    for suffix in (" const", " volatile", " &", " &&"):
        while sig.endswith(suffix):
            sig = sig[: -len(suffix)]
    lp = sig.find("(")
    if lp < 0 or not sig.endswith(")"):
        return None
    body = sig[lp + 1 : -1]
    if not body:
        return []
    params, depth, cur = [], 0, ""
    for ch in body:
        if ch in "(<[":
            depth += 1
        elif ch in ")>]":
            depth -= 1
        if ch == "," and depth == 0:
            params.append(cur.strip())
            cur = ""
        else:
            cur += ch
    params.append(cur.strip())
    return params


_METHOD_RE = re.compile(r"^(?:non-virtual thunk to )?(Chain|State)::([~A-Za-z_][A-Za-z0-9_]*)\(")
_ENUM_RE = re.compile(r"\b([A-Z][A-Za-z]*Type|TargetPlayer|Comparator[A-Za-z]*)\b")


def build_vocabulary(so_bytes: bytes) -> dict:
    """The frozen vocabulary: Chain ops, State ops, pipeline free functions, referenced enums."""
    mangled = extract_mangled(so_bytes)
    dem = demangle(mangled)
    chain: dict[str, list] = {}
    state: dict[str, list] = {}
    free: dict[str, list] = {}
    enums: set[str] = set()

    for m in mangled:
        d = dem.get(m)
        if not d or d == m:  # not demangleable -> not a C++ signature we care about
            continue
        hit = _METHOD_RE.match(d)
        params = split_params(d)
        if hit and params is not None:
            cls, meth = hit.groups()
            if meth.startswith("~") or meth == "operator":
                continue
            bucket = chain if cls == "Chain" else state
            entry = {"params": params, "arity": len(params) if params != ["" ] else 0}
            if params == [""]:
                entry = {"params": [], "arity": 0}
            bucket.setdefault(meth, [])
            if entry not in bucket[meth]:
                bucket[meth].append(entry)
            enums.update(_ENUM_RE.findall(d))
            continue
        for fn in _FREE_FUNCTIONS:
            if d.startswith(fn + "(") and params is not None:
                free.setdefault(fn, [])
                entry = {"params": params if params != [""] else [], "arity": 0 if params == [""] else len(params)}
                if entry not in free[fn]:
                    free[fn].append(entry)
                enums.update(_ENUM_RE.findall(d))

    for bucket in (chain, state, free):
        for k in bucket:
            bucket[k].sort(key=lambda e: (e["arity"], json.dumps(e["params"])))

    return {
        "schema": "dsl-vocabulary/1",
        "source": {
            "file": "src/cg/libcg.so",
            "sha256": hashlib.sha256(so_bytes).hexdigest(),
        },
        "chain_ops": dict(sorted(chain.items())),
        "state_ops": dict(sorted(state.items())),
        "free_functions": dict(sorted(free.items())),
        "enums_referenced": sorted(enums),
    }


def render(vocab: dict) -> str:
    return json.dumps(vocab, indent=1, ensure_ascii=False, sort_keys=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Freeze the native engine's effect-DSL vocabulary.")
    ap.add_argument("--check", action="store_true",
                    help="drift check: exit 1 if the binary and the committed file disagree")
    ap.add_argument("--so", default=str(SO_PATH), help="path to libcg.so")
    ap.add_argument("--out", default=str(OUT_PATH), help="vocabulary JSON path")
    args = ap.parse_args(argv)

    so_bytes = Path(args.so).read_bytes()
    vocab = build_vocabulary(so_bytes)
    if not vocab["chain_ops"]:
        print("error: no Chain:: symbols recovered (c++filt missing, or a stripped binary?)")
        return 2

    out = Path(args.out)
    if args.check:
        if not out.exists():
            print(f"drift check FAILED: {out} missing")
            return 1
        committed = json.loads(out.read_text(encoding="utf-8"))
        fresh, old = dict(vocab), dict(committed)
        fresh.pop("source", None), old.pop("source", None)  # sha differs per rebuild of the lib
        if fresh != old:
            def keys(d):
                return {sec: set(d.get(sec, {})) for sec in ("chain_ops", "state_ops", "free_functions")}
            fk, ok = keys(fresh), keys(old)
            for sec in fk:
                added, removed = fk[sec] - ok[sec], ok[sec] - fk[sec]
                if added:
                    print(f"drift: NEW {sec}: {sorted(added)}")
                if removed:
                    print(f"drift: REMOVED {sec}: {sorted(removed)}")
            print("drift check FAILED: binary and committed vocabulary disagree "
                  "(regenerate + re-verify the parity corpus)")
            return 1
        print(f"drift check OK: {len(vocab['chain_ops'])} chain ops, "
              f"{len(vocab['state_ops'])} state ops")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(vocab), encoding="utf-8")
    print(f"wrote {out}  ({len(vocab['chain_ops'])} chain ops, {len(vocab['state_ops'])} state "
          f"ops, {len(vocab['free_functions'])} pipeline functions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
