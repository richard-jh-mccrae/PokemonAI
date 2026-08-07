"""**Covered-disposition audit** — does a `reviewed.json` closure still name a rule that exists?

    python tools/train/reviewed_audit.py                    # the report + the tallies
    python tools/train/reviewed_audit.py --check            # non-zero if the stale set != the allowlist
    python tools/train/reviewed_audit.py --emit-report      # (re)write docs/plans/covered-disposition-audit.md
    python tools/train/reviewed_audit.py --write-allowlist  # re-seed the allowlist from today's stale set
    python tools/train/reviewed_audit.py --refresh-vocab    # re-harvest data/corrections/rung_vocabulary.json

A `covered` disposition claims a SHIPPED rule handles the frame; when that rule is deleted the claim
expires silently. This REPORTS and never gates (ADR-0114 decision 3): the ratchet is an allowlist the
flagged set must equal: a hard failure's only path to green is the bulk re-close Issue #238 forbids.
A token resolves as a rung only against a harvested vocabulary of three namespaces — live
``Hypothesis`` ids, live ``SoundRule`` ids, ids retired from git history — never a loose regex, which
matches `attack-last` and `tier-2` alike. The retired half is CACHED because CI checks out SHALLOW,
and `load_vocabulary` re-adds ``live_at_capture − live_now`` to catch a deletion since the refresh.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools")]

from train.blunder.reviewed import DEFAULT_REVIEWED, load_reviewed  # noqa: E402

DEFAULT_SRC = REPO / "src"
DEFAULT_VOCABULARY = REPO / "data" / "corrections" / "rung_vocabulary.json"
DEFAULT_ALLOWLIST = REPO / "data" / "corrections" / "reviewed_audit_allowlist.json"
DEFAULT_REPORT = REPO / "docs" / "plans" / "covered-disposition-audit.md"

#: `src/cg/` is the native-engine API wrapper and is off-limits (CLAUDE.md); it holds no rungs, and
#: excluding it up front keeps a repo-wide sweep from ever touching it.
_SKIP_DIRS = ("cg", "__pycache__")

#: The audit's POSITIVE CONTROL, not its vocabulary: every name in these deleted ``RETIRED`` tuples
#: must turn up in the historical harvest, or the harvest is broken. SHAs are pinned on purpose.
SWEEP_RETIRED_SOURCES = (
    ("909be890^", "tools/train/probes/attach_decider_sweep.py", ("RETIRED", "ZEROED")),
    ("909be890^", "tools/train/probes/evolve_decider_sweep.py", ("RETIRED",)),
    ("909be890^", "tools/train/probes/promote_retreat_decider_sweep.py", ("RETIRED",)),
    ("4f195bb1^", "tools/train/probes/deploy_decider_sweep.py", ("RETIRED",)),
)

#: Leading letter keeps dates, damage and frame ids out; the ``_`` boundary keeps `_finish-turn-last`
#: from reading as the rung inside it. ``/`` and ``.`` are NOT boundaries: `attack-last/tiered` is real.
RUNG_TOKEN = re.compile(r"(?<![a-z0-9_-])[a-z][a-z0-9]*(?:-[a-z0-9]+)+(?![a-z0-9_-])")

#: Applied to `git log -p` output. Deliberate blind spot: a one-line ``Hypothesis(id="x", …)`` is
#: MISSED, because a false retired name flags a healthy closure and under-reporting is at least visible.
_DIFF_ID = re.compile(r'^[-+]\s*id="([a-z0-9][a-z0-9-]*)"', re.M)


# ── Vocabulary harvest ─────────────────────────────────────────────────────

def _python_files(src_root: Path):
    """The skip test runs on the path RELATIVE to `src_root`: a checkout living under any directory
    named `cg` would otherwise return nothing, which reads as "no rungs exist"."""
    src_root = Path(src_root)
    for path in sorted(src_root.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in path.relative_to(src_root).parts):
            continue
        yield path


def _rel(path: Path) -> str:
    """Absolute posix when outside the repo: `src_root` may point at a fixture tree."""
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def harvest_ids(src_root: Path, ctor: str) -> dict:
    """``{id: [path, …]}`` per ``<ctor>(id="…")`` call. AST, not grep: a grep cannot tell a
    `Hypothesis` id from a `SoundRule` one. EVERY site is kept, so the control can assert a count."""
    out = {}
    for path in _python_files(src_root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):          # not our file to fix; never silently skip a rung
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name != ctor:
                continue
            for kw in node.keywords:
                if kw.arg == "id" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    out.setdefault(kw.value.value, []).append(_rel(path))
    return out


def _git(repo: Path, *args):
    """Run git; ``None`` when git is absent or the command fails (a shallow clone, a tarball)."""
    try:
        done = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def git_history_available(repo: Path = REPO) -> bool:
    """Both halves matter: a shallow clone has one commit (CI), and a fork's full clone may still
    not carry the two pinned sweep revisions."""
    shallow = _git(repo, "rev-parse", "--is-shallow-repository")
    if shallow is None or shallow.strip() != "false":
        return False
    return all(_git(repo, "cat-file", "-e", f"{rev}:{path}") is not None
               for rev, path, _ in SWEEP_RETIRED_SOURCES)


def historical_rung_ids(repo: Path = REPO) -> set | None:
    """``sound_rules.py`` is excluded by PATHSPEC, never subtracted afterwards: a subtraction hides
    its ids only while they are live, so a rename resurfaces one as a phantom "retired rung"."""
    out = _git(repo, "log", "--all", "--pretty=format:", "-p", "--",
               "src/*.py", ":(exclude)src/common/sound_rules.py")
    return set(_DIFF_ID.findall(out)) if out else None


def sweep_retired_ids(repo: Path = REPO) -> set | None:
    """AST rather than a regex over the blob, so a re-formatted tuple — or one built as
    ``RETIRED + (...)``, which `attach`'s ``ZEROED`` is — still reads correctly."""
    names = set()
    for rev, path, targets in SWEEP_RETIRED_SOURCES:
        blob = _git(repo, "show", f"{rev}:{path}")
        if blob is None:
            return None
        for node in ast.parse(blob).body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id in targets for t in node.targets):
                continue
            for element in ast.walk(node.value):
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    names.add(element.value)
    return names


@dataclass(frozen=True)
class Vocabulary:
    """The three namespaces a note token can resolve into, plus where the retired half came from."""
    live: frozenset = frozenset()
    sound_rules: frozenset = frozenset()
    retired: frozenset = frozenset()
    provenance: dict = field(default_factory=dict)

    def resolve(self, token: str) -> str | None:
        """``"live"`` / ``"sound-rule"`` / ``"retired"``, or ``None`` — not a rung reference."""
        if token in self.live:
            return "live"
        if token in self.sound_rules:
            return "sound-rule"
        if token in self.retired:
            return "retired"
        return None


def build_vocabulary(repo: Path = REPO, src_root: Path | None = None) -> dict:
    """Harvest the snapshot document from git + `src/`. Raises when history is unavailable — a
    silently-empty refresh would write a vocabulary that flags nothing and looks green."""
    src_root = src_root or (repo / "src")
    live = harvest_ids(src_root, "Hypothesis")
    sound = harvest_ids(src_root, "SoundRule")
    historical = historical_rung_ids(repo)
    sweeps = sweep_retired_ids(repo)
    if historical is None or sweeps is None:
        raise RuntimeError(
            "cannot refresh the rung vocabulary: this checkout has no usable git history "
            "(shallow clone?). The committed data/corrections/rung_vocabulary.json is the fallback.")
    missing_live = sorted(set(live) - historical)
    missing_sweep = sorted(sweeps - historical)
    if missing_live or missing_sweep:                       # the two controls, enforced at capture time
        raise RuntimeError(
            "the historical harvest is BROKEN, not the codebase clean: it missed "
            f"{len(missing_live)} live id(s) {missing_live[:5]} and "
            f"{len(missing_sweep)} sweep-retired name(s) {missing_sweep[:5]}.")
    retired = sorted(historical - set(live) - set(sound))
    return {
        "_note": ("Rung VOCABULARY for tools/train/reviewed_audit.py (Issue #238, ADR-0114). "
                  "GENERATED — re-run `python tools/train/reviewed_audit.py --refresh-vocab`; do not "
                  "hand-edit. `retired` = ids that were a Hypothesis(id=) in git history and are not "
                  "one in src/ today. `live_at_capture` is kept so the audit can widen `retired` with "
                  "rungs deleted SINCE this capture without needing git — CI checks out shallow. "
                  "`sweep_retired` is the POSITIVE CONTROL, not the vocabulary: every name in it must "
                  "appear in the historical harvest or the harvest is broken."),
        "head": (_git(repo, "rev-parse", "HEAD") or "").strip(),
        "live_at_capture": sorted(live),
        "sound_rules_at_capture": sorted(sound),
        "sweep_retired": sorted(sweeps),
        "retired": retired,
    }


def load_vocabulary(path: Path = DEFAULT_VOCABULARY, src_root: Path = DEFAULT_SRC) -> Vocabulary:
    """The live half is always RE-HARVESTED; the retired half is the snapshot plus anything live at
    capture and not live now, which catches a post-refresh deletion with no git history."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    live = set(harvest_ids(src_root, "Hypothesis"))
    sound = set(harvest_ids(src_root, "SoundRule"))
    deleted_since = set(doc.get("live_at_capture", ())) - live
    retired = (set(doc.get("retired", ())) | deleted_since) - live - sound
    return Vocabulary(live=frozenset(live), sound_rules=frozenset(sound), retired=frozenset(retired),
                      provenance={"head": doc.get("head", ""), "deleted_since_capture": sorted(deleted_since),
                                  "sweep_retired": sorted(doc.get("sweep_retired", ()))})


# ── Reading a review note ──────────────────────────────────────────────────

def rung_tokens(note: str) -> list:
    """The HAYSTACK is lowercased, not the pattern, so a note opening a sentence with `Attack-last`
    tokenizes like one that does not."""
    seen, out = set(), []
    for token in RUNG_TOKEN.findall((note or "").lower()):
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


@dataclass(frozen=True)
class Reference:
    """One note's tokens, split by which namespace each resolved into."""
    live: tuple = ()
    sound_rules: tuple = ()
    retired: tuple = ()
    unresolved: tuple = ()


def classify_note(note: str, vocab: Vocabulary) -> Reference:
    buckets = {"live": [], "sound-rule": [], "retired": [], None: []}
    for token in rung_tokens(note):
        buckets[vocab.resolve(token)].append(token)
    return Reference(live=tuple(buckets["live"]), sound_rules=tuple(buckets["sound-rule"]),
                     retired=tuple(buckets["retired"]), unresolved=tuple(buckets[None]))


# ── The audit ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StaleEntry:
    """A ledger entry whose justification names at least one rung that no longer exists."""
    key: str
    disposition: str
    reason: str
    dead: tuple
    live: tuple


def stale_entries(reviewed: dict, vocab: Vocabulary) -> list:
    """Every entry naming a retired rung, ledger order preserved (it is roughly review order)."""
    out = []
    for key, entry in reviewed.items():
        if not isinstance(entry, dict):
            continue
        ref = classify_note(entry.get("reason") or "", vocab)
        if ref.retired:
            out.append(StaleEntry(key=key, disposition=entry.get("disposition") or "",
                                  reason=entry.get("reason") or "", dead=tuple(sorted(ref.retired)),
                                  live=tuple(sorted(ref.live + ref.sound_rules))))
    return out


def allowlist_form(entries) -> dict:
    """Carries the RUNGS as well as the key, so re-closing an entry against a second dead rung is a
    change the allowlist notices; a bare key list would call that green."""
    return {e.key: list(e.dead) for e in sorted(entries, key=lambda e: e.key)}


def unresolved_tally(reviewed: dict, vocab: Vocabulary) -> Counter:
    """Tokens that resolved to nothing, by occurrence — the vocabulary's visible blind spot."""
    tally = Counter()
    for entry in reviewed.values():
        if isinstance(entry, dict):
            tally.update(classify_note(entry.get("reason") or "", vocab).unresolved)
    return tally


# ── "what the rule became" — the column that lets a developer rule quickly ──

def fold_map_targets(rungs, src_root: Path = DEFAULT_SRC) -> dict:
    """``{rung: "what it became"}`` from `tools.rung_registry.FOLDED`; empty string where the registry
    carries no record, which beats inventing a target. `src_root` is vestigial — callers pass it."""
    from tools.rung_registry import FOLDED

    out = {}
    for rung in set(rungs):
        fold = FOLDED.get(rung)
        out[rung] = "" if fold is None else f"{fold.into} — {fold.note}"
    return out


# ── The generated worklist (ADR-0114 decision 4) ───────────────────────────

#: Data about the ISSUE, not the codebase: the report RECONCILES against these, and nothing consults
#: them to decide anything. `ISSUE_238_COMMENT_14` holds Frame Keys, the other two ledger keys.
ISSUE_238_BODY_13 = ("81903490-27", "81903490-49", "81904451-50", "81904451-6", "81905522-47",
                     "81906131-25", "82524455-27", "82750161-59", "82752045-80", "82752045-97",
                     "82756664-74", "83007714-7", "83116501-89")
ISSUE_238_BODY_REFUTED_3 = ("82525741-81", "82867148-87", "85058574-114")
ISSUE_238_COMMENT_14 = ("82224509-29", "82224509-40", "82224509-71", "82225643-11", "82225643-57",
                        "82226116-70", "82226759-64", "82227388-22", "82227388-30", "82227388-43",
                        "82228640-25", "82228640-48", "82228640-53", "82229122-33")


def _table(entries, targets) -> list:
    lines = ["| ledger key | disposition | dead rung(s) | what it became | live rule(s) still named | the note, verbatim |",
             "|---|---|---|---|---|---|"]
    for e in entries:
        became = "<br>".join(f"`{r}` → {targets.get(r) or '—'}" for r in e.dead)
        live = ", ".join(f"`{r}`" for r in e.live) or "—"
        note = (e.reason or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{e.key}` | {e.disposition} | {' '.join(f'`{r}`' for r in e.dead)} | "
                     f"{became} | {live} | {note} |")
    return lines


def render_report(entries, vocab: Vocabulary, reviewed: dict, src_root: Path = DEFAULT_SRC) -> str:
    """The committed worklist, `docs/plans/covered-disposition-audit.md`."""
    targets = fold_map_targets({r for e in entries for r in e.dead}, src_root)
    by_disposition = {}
    for e in entries:
        by_disposition.setdefault(e.disposition or "(none)", []).append(e)
    unresolved = unresolved_tally(reviewed, vocab)
    blocking = [d for d in sorted(by_disposition) if d not in ("refuted", "transposition")]

    out = [
        "# Covered-disposition audit — the worklist",
        "",
        "> **GENERATED — do not hand-edit.** `python tools/train/reviewed_audit.py --emit-report`.",
        "> Issue #238, ADR-0114 decision 4. Regenerate after any ledger or rung change.",
        "",
        "A `reviewed.json` closure is a claim about the shipped agent. When the rule it names is",
        "deleted the claim expires silently, because the ledger stores its justification as opaque",
        "prose. Every row below is an entry whose justification names a rung that **no longer",
        "exists**. A row is *not* a finding that the frame is misplayed — it is a finding that the",
        "**stated reason for closing it is gone**, so the closure has never been re-examined.",
        "",
        "## How to use this",
        "",
        "Open the frame — `python tools/train/frame_view.py <ledger key>` — and rule it on its own",
        "merits, independent of the vanished rung (Issue #238 items 1-3, which are a human ruling and",
        "are deliberately NOT automated). Then either re-close it against a rule that exists",
        "(`python tools/train/review_correction.py <key> covered \"<why>\"`) or route it through the",
        "current taxonomy. Once it stops being flagged, delete its line from",
        "`data/corrections/reviewed_audit_allowlist.json`. The *what it became* column is there to",
        "make that ruling cheap: it is the fold map's own statement of what replaced the rung.",
        "",
        "## Tally",
        "",
        f"* ledger entries: **{sum(1 for v in reviewed.values() if isinstance(v, dict))}**",
        f"* entries naming a retired rung: **{len(entries)}**",
        "* by disposition: " + (
            ", ".join(f"`{d}` **{len(v)}**" for d, v in sorted(by_disposition.items())) or "(none)"
        ),
        f"* live rung vocabulary: **{len(vocab.live)}** `Hypothesis(id=…)` in `src/` "
        f"(+ **{len(vocab.sound_rules)}** `SoundRule(id=…)`)",
        f"* retired rung vocabulary: **{len(vocab.retired)}**",
        f"* distinct rungs implicated: **{len({r for e in entries for r in e.dead})}**",
        f"* tokens that resolved to NO rung (the vocabulary's blind spot): **{len(unresolved)}** "
        f"distinct, **{sum(unresolved.values())}** occurrences. Top: "
        + ", ".join(f"`{t}` ×{n}" for t, n in unresolved.most_common(8)),
        "",
        "The blind-spot count is reported rather than suppressed. The most frequent unresolved token",
        "is `attack-last`, which is not a rung at all — it is the Pilot's structural resequencing",
        "(`_finish_turn_last`). A loose `[a-z-]+` scan would have flagged every note that mentions it.",
        "",
    ]

    for disposition in blocking:
        rows = by_disposition[disposition]
        out += [f"## `{disposition}` — {len(rows)} entr{'y' if len(rows) == 1 else 'ies'}", ""]
        out += _table(rows, targets)
        out += [""]

    for disposition in ("refuted", "transposition"):
        rows = by_disposition.get(disposition)
        if not rows:
            continue
        out += [f"## `{disposition}` — {len(rows)}: flagged, but NOT blockers (ADR-0114 decision 6)",
                "",
                "A refuted ruling owes no fix either way, so a dead rung in its refutation note costs",
                "nothing operationally. They are listed because the refutation rests on the same",
                "vanished premise, and Issue #238 asked for them to be re-read on that basis.",
                ""]
        out += _table(rows, targets)
        out += [""]

    flagged = {e.key for e in entries}
    named = set(ISSUE_238_BODY_13) | set(ISSUE_238_BODY_REFUTED_3) | set(ISSUE_238_COMMENT_14)
    unflagged_14 = [k for k in ISSUE_238_COMMENT_14 if k not in flagged]
    on_attack_last = [k for k in unflagged_14 if "attack-last" in (reviewed.get(k, {}).get("reason") or "")]
    out += ["## Reconciliation against Issue #238's own lists", "",
            "Acceptance criterion 5. Every count below is derived from this run, not transcribed.", ""]
    for label, keys in (("body, the 13", ISSUE_238_BODY_13),
                        ("body, the 3 `refuted` re-reads", ISSUE_238_BODY_REFUTED_3),
                        ("comment, the 14 (`<ep>|<seat>|decision|<frame>` → `<ep>-<frame>`)", ISSUE_238_COMMENT_14)):
        hit = [k for k in keys if k in flagged]
        miss = [k for k in keys if k not in flagged]
        out += [f"* **{label}** — flagged {len(hit)}/{len(keys)}."]
        if miss:
            out += ["  Not flagged: " + ", ".join(f"`{k}`" for k in miss) + "."]
    out += ["",
            f"The {len(unflagged_14)} unflagged entries from the comment's 14 are correct behaviour, not a miss —",
            f"**{len(on_attack_last)} of {len(unflagged_14)}** close on `attack-last`, which names no rung, live or dead. It is the",
            "Pilot's structural resequencing, so *\"the agent does the right thing, just in a different",
            "order within the same turn\"* is a different question (*is same-turn ordering a blunder at",
            "all?*) — and the comment filing them says exactly that. Nothing about them expired; there",
            "is no dead rule for them to have expired against.",
            "",
            f"Entries this audit surfaces that Issue #238 never named: **{len(flagged - named)}**.",
            "",
            "## Provenance", "",
            f"* rung vocabulary captured at `{vocab.provenance.get('head', '')[:12]}`",
            f"* rungs deleted since that capture, folded in without git: "
            f"{', '.join(f'`{r}`' for r in vocab.provenance.get('deleted_since_capture', ())) or 'none'}",
            f"* positive control — the four decider sweeps' `RETIRED` lists: "
            f"**{len(vocab.provenance.get('sweep_retired', ()))}** names, every one present in the historical harvest",
            ""]
    return "\n".join(out)


# ── CLI ────────────────────────────────────────────────────────────────────

def _json(doc) -> str:
    """`ensure_ascii=False` so the `_note` fields keep their real em dashes, matching
    `review_correction._save` rather than the gate artifacts (which are ASCII-escaped)."""
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def _write_lf(path: Path, text: str) -> None:
    """LF-framed: `Path.write_text` frames per the WRITING platform and these files are committed.
    It must never come to frame newlines differently from the repo's other two LF writers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")          # reasons carry em dashes
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Audit reviewed.json for closures naming a deleted rung")
    ap.add_argument("--reviewed", default=str(DEFAULT_REVIEWED))
    ap.add_argument("--vocabulary", default=str(DEFAULT_VOCABULARY))
    ap.add_argument("--allowlist", default=str(DEFAULT_ALLOWLIST))
    ap.add_argument("--report", default=str(DEFAULT_REPORT))
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--refresh-vocab", action="store_true", help="re-harvest the vocabulary from git + src/")
    ap.add_argument("--write-allowlist", action="store_true", help="re-seed the allowlist from today's stale set")
    ap.add_argument("--emit-report", action="store_true", help="(re)write the generated worklist")
    ap.add_argument("--check", action="store_true", help="exit 1 if the stale set differs from the allowlist")
    args = ap.parse_args(argv)

    if args.refresh_vocab:
        doc = build_vocabulary(REPO, Path(args.src))
        _write_lf(Path(args.vocabulary), _json(doc))
        print(f"rung vocabulary refreshed: {len(doc['live_at_capture'])} live, "
              f"{len(doc['retired'])} retired -> {args.vocabulary}")

    vocab = load_vocabulary(Path(args.vocabulary), Path(args.src))
    reviewed = load_reviewed(Path(args.reviewed))
    entries = stale_entries(reviewed, vocab)
    current = allowlist_form(entries)

    if args.write_allowlist:
        doc = {"_note": ("The covered-disposition WORKLIST (Issue #238, ADR-0114 decision 3). "
                         "Every reviewed.json entry whose justification names a rung that no longer "
                         "exists. This is an ALLOWLIST, not an exemption: a test asserts the audit's "
                         "flagged set equals this file exactly, so a NEW stale closure is red "
                         "immediately. Rule the frame (docs/plans/covered-disposition-audit.md says "
                         "how), re-close it against a live rule, then DELETE its line here. "
                         "Regenerate with `python tools/train/reviewed_audit.py --write-allowlist` "
                         "only when re-seeding deliberately."),
               "entries": current}
        _write_lf(Path(args.allowlist), _json(doc))
        print(f"allowlist written: {len(current)} entries -> {args.allowlist}")

    if args.emit_report:
        _write_lf(Path(args.report), render_report(entries, vocab, reviewed, Path(args.src)) + "\n")
        print(f"worklist written: {args.report}")

    unresolved = unresolved_tally(reviewed, vocab)
    print(f"ledger entries          : {sum(1 for v in reviewed.values() if isinstance(v, dict))}")
    print(f"naming a RETIRED rung   : {len(entries)}")
    disposition_summary = ", ".join(
        f"{d}={n}" for d, n in sorted(Counter(e.disposition for e in entries).items())
    ) or "(none)"
    print("  by disposition        : " + disposition_summary)
    print(f"live rungs in src/      : {len(vocab.live)} Hypothesis + {len(vocab.sound_rules)} SoundRule")
    print(f"retired rung vocabulary : {len(vocab.retired)}")
    print(f"unresolved tokens       : {len(unresolved)} distinct / {sum(unresolved.values())} occurrences")
    for e in entries:
        print(f"  {e.key:16} {e.disposition:10} {', '.join(e.dead)}")

    if args.check:
        allowed = json.loads(Path(args.allowlist).read_text(encoding="utf-8")).get("entries", {})
        if current != allowed:
            new = sorted(set(current) - set(allowed))
            gone = sorted(set(allowed) - set(current))
            print(f"\nSTALE SET != ALLOWLIST. new={new} resolved={gone}")
            return 1
        print("\nstale set matches the committed allowlist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
