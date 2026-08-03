"""**Covered-disposition audit** — does a `reviewed.json` closure still name a rule that exists?

    python tools/train/reviewed_audit.py                    # the report + the tallies
    python tools/train/reviewed_audit.py --check            # non-zero if the stale set != the allowlist
    python tools/train/reviewed_audit.py --emit-report      # (re)write docs/plans/covered-disposition-audit.md
    python tools/train/reviewed_audit.py --write-allowlist  # re-seed the allowlist from today's stale set
    python tools/train/reviewed_audit.py --refresh-vocab    # re-harvest data/corrections/rung_vocabulary.json

A `covered` disposition is a claim about the **shipped agent**: *"a rule we ship already handles this
frame, so hold it off fresh work."* When the rule it names is later deleted, the claim expires — but
it expires **silently**, because the ledger stores the justification as opaque prose and nothing ever
reads it back. Issue #238 found 13 such closures by hand. This module is the mechanical version.

## Why this REPORTS and does not gate (ADR-0114 decision 3)

It flags dozens of committed entries. A hard failure would red `main` on day one with no path to
green except re-closing them in bulk — and a bulk re-close is exactly what Issue #238 forbids
(*"Each needs the frame opened … not a bulk re-open"*). So the ratchet is an **allowlist**: the
flagged set must equal `data/corrections/reviewed_audit_allowlist.json`, which IS the developer's
worklist. Ruling a frame and re-closing it against a live rule removes it from both. A *new* stale
closure is red immediately.

## The vocabulary is CURATED, never a loose regex (ADR-0114 decision 2)

A review note is prose. A bare `[a-z-]+` scan over these notes matches `attack-last` (46 times),
`first-dev-differs`, `tier-2`, `hand-quality` — none of which is a rung. So a token becomes a rung
reference only by resolving against a harvested vocabulary:

* **live** — every ``Hypothesis(id=…)`` reachable in `src/`, read by AST at audit time. Never a hand
  list: a rung deleted tomorrow leaves the live set tomorrow.
* **sound rules** — every ``SoundRule(id=…)`` in `src/`. A separate live namespace, harvested for one
  reason: 15 of them are hyphenated ids that were never Hypotheses, and without this they would
  resolve as *retired rungs*.
* **retired** — every id that WAS a ``Hypothesis(id=…)`` at some commit and is not one now, harvested
  from git history. This is the definitionally correct instrument — "was a rung, is not now" — and it
  needs no prose parsing at all.

Anything in none of the three is **not a rung reference** and is never flagged; the count of those is
reported separately so the vocabulary's own blind spots stay visible.

**The retired half is CACHED, and that is not laziness.** `.github/workflows/ci.yml` checks out with
`actions/checkout@v4` at its default depth — a shallow clone, where `git log --all` sees one commit.
So the harvest is snapshotted to `data/corrections/rung_vocabulary.json` by `--refresh-vocab`, and
the audit reads the snapshot. Two things keep the snapshot honest:

1. `load_vocabulary` adds ``live_at_capture − live_now`` to the retired set, so a rung deleted after
   the last refresh is caught with no git access at all;
2. a test re-runs the git harvest and asserts the snapshot still matches — skipped, loudly, on a
   shallow clone.

## The controls the harvest is worthless without

`CLAUDE.md`: an instrument that finds nothing and a broken instrument return the same empty output.
Two structural controls, both asserted by test:

* every one of the **95** live ids appears in the historical harvest (a diff scan that cannot see a
  rung that is in the tree right now cannot be trusted about one that left);
* every name in the four decider sweeps' ``RETIRED``/``ZEROED`` tuples — the authoritative deletion
  lists Issue #238 cross-referenced by hand — appears in it too.

Both pass, which is what licenses the zeros: `dont-waste-discard-energy`,
`concentrate-energy-on-wincon`, `build-active-wincon`, `power-up-attacker` and
`conserve-burst-when-no-ko` have **0** live definitions while `prefer-active-attach-in-setup` and
`use-acceleration` have **1** each.

Offline, read-only, no engine and no Pilot — the audit is pure functions over plain dicts, so it runs
in the fast cross-platform suite. `--refresh-vocab` is the one subcommand that shells out to git.
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

#: The four ``*_decider_sweep.py`` probes carried an authoritative ``RETIRED`` tuple naming the rungs
#: their deletion pass removed. All four lists were themselves deleted once the swap was done —
#: ADR-0085 Amendment J removed the OLD arm that consumed them (`909be890`), and the deploy sweep went
#: with the corpus-reader refactor (`4f195bb1`). They are read from history as the audit's POSITIVE
#: CONTROL, not as its vocabulary: every name here must turn up in the historical harvest, or the
#: harvest is broken rather than the codebase clean. Pinned by SHA on purpose — a moving ref would
#: make the control's meaning depend on when it ran.
SWEEP_RETIRED_SOURCES = (
    ("909be890^", "tools/train/probes/attach_decider_sweep.py", ("RETIRED", "ZEROED")),
    ("909be890^", "tools/train/probes/evolve_decider_sweep.py", ("RETIRED",)),
    ("909be890^", "tools/train/probes/promote_retreat_decider_sweep.py", ("RETIRED",)),
    ("4f195bb1^", "tools/train/probes/deploy_decider_sweep.py", ("RETIRED",)),
)

#: A rung id: lowercase, hyphenated, starting with a letter, bounded so a longer token never yields a
#: short false hit. Starting with a letter is what keeps dates (`2026-08-02`), damage (`120-dmg`) and
#: frame ids (`81785223-32`) out of the token stream entirely; the ``_`` in the boundary keeps a
#: private name (`_finish-turn-last`) from being read as the rung inside it.
#:
#: ``/`` and ``.`` are deliberately NOT boundary characters. Notes really do write `attack-last/tiered`
#: and `reactive-disruption/Posture`, so excluding a slash-adjacent token would lose real rung
#: references to buy a slightly quieter blind-spot tally. Measured both ways on the committed ledger:
#: the flagged set is IDENTICAL at 60 either way — only the unresolved count moves.
RUNG_TOKEN = re.compile(r"(?<![a-z0-9_-])[a-z][a-z0-9]*(?:-[a-z0-9]+)+(?![a-z0-9_-])")

#: `^[-+]` then optional space then `id="…"` — a Hypothesis id sits on its own line inside the
#: constructor call, so a prose mention (`# … id="x"`) cannot match. Applied to `git log -p` output.
#:
#: **Known blind spot, chosen deliberately:** a Hypothesis written entirely on one line
#: (``Hypothesis(id="x", …)``) is missed, so a rung that only ever existed in that form and was later
#: deleted would not enter the retired vocabulary. Widening the pattern to match `id="…"` anywhere on
#: a diff line is the obvious fix and is worse: it would sweep in every prose mention and every
#: non-Hypothesis `id=` in `src/` history, and a FALSE retired name flags a closure that is actually
#: fine — a worse failure than missing one. Under-reporting is visible in the unresolved tally; a
#: false flag is not visible at all. No rung in this repo's history is written that way (every
#: `Hypothesis(` call in `src/` today spans lines, and both structural controls pass).
_DIFF_ID = re.compile(r'^[-+]\s*id="([a-z0-9][a-z0-9-]*)"', re.M)


# ---------------------------------------------------------------------------
# Vocabulary harvest
# ---------------------------------------------------------------------------

def _python_files(src_root: Path):
    """Every Python file under `src_root`, skipping `src/cg/` and caches.

    The skip test is applied to the path RELATIVE to `src_root`, never the absolute one: a checkout
    that happens to live under any directory named `cg` would otherwise skip the entire tree and
    return nothing, which reads as "no rungs exist" rather than as a broken walk."""
    src_root = Path(src_root)
    for path in sorted(src_root.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in path.relative_to(src_root).parts):
            continue
        yield path


def _rel(path: Path) -> str:
    """Repo-relative posix path where possible, absolute posix otherwise — `src_root` is a public
    parameter and may legitimately point at a fixture tree outside the repo."""
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def harvest_ids(src_root: Path, ctor: str) -> dict:
    """``{id: [path, …]}`` for every ``<ctor>(id="…")`` call under `src_root`, definition sites in
    walk order.

    AST, not grep: a constructor call is a syntactic fact, and the alternative (`grep 'id="…"'`)
    over-counts by 15 on this tree — it cannot tell a `Hypothesis` id from a `SoundRule` one, which
    is precisely the distinction that decides whether a token is a live rung or a retired one.

    Every site is kept rather than the first, so the positive control can assert what it actually
    claims — `use-acceleration` is live **once** — instead of merely asserting the key is present.
    """
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
    """True when this checkout carries enough history to re-derive the retired vocabulary.

    Both halves matter: a shallow clone has one commit (CI), and even a full clone of a *fork* might
    not carry the two pinned sweep revisions."""
    shallow = _git(repo, "rev-parse", "--is-shallow-repository")
    if shallow is None or shallow.strip() != "false":
        return False
    return all(_git(repo, "cat-file", "-e", f"{rev}:{path}") is not None
               for rev, path, _ in SWEEP_RETIRED_SOURCES)


def historical_rung_ids(repo: Path = REPO) -> set | None:
    """Every id that has EVER been written as ``id="…"`` on its own line in a `src/` Python file.

    ``sound_rules.py`` is excluded by pathspec rather than subtracted afterwards: its ids are live
    Sound Rules, and a subtraction would only hide them while they are live — the moment one is
    renamed it would re-appear as a phantom "retired rung"."""
    out = _git(repo, "log", "--all", "--pretty=format:", "-p", "--",
               "src/*.py", ":(exclude)src/common/sound_rules.py")
    return set(_DIFF_ID.findall(out)) if out else None


def sweep_retired_ids(repo: Path = REPO) -> set | None:
    """The four decider sweeps' ``RETIRED``/``ZEROED`` names, read out of git history by AST.

    AST rather than a regex over the blob so a re-formatted tuple (or one built as ``RETIRED +
    (...)``, which `attach`'s ``ZEROED`` is) still reads correctly."""
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
    """The committed snapshot, re-based on TODAY's `src/`.

    The live half is always re-harvested, never read from the file. The retired half is the snapshot
    PLUS anything that was live at capture and is not live now — which is how a rung deleted after
    the last refresh is caught on a checkout with no git history."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    live = set(harvest_ids(src_root, "Hypothesis"))
    sound = set(harvest_ids(src_root, "SoundRule"))
    deleted_since = set(doc.get("live_at_capture", ())) - live
    retired = (set(doc.get("retired", ())) | deleted_since) - live - sound
    return Vocabulary(live=frozenset(live), sound_rules=frozenset(sound), retired=frozenset(retired),
                      provenance={"head": doc.get("head", ""), "deleted_since_capture": sorted(deleted_since),
                                  "sweep_retired": sorted(doc.get("sweep_retired", ()))})


# ---------------------------------------------------------------------------
# Reading a review note
# ---------------------------------------------------------------------------

def rung_tokens(note: str) -> list:
    """The hyphenated candidate tokens in a review note, lowercased and de-duplicated, in order.

    Lowercasing the haystack (not the pattern) is deliberate: rung ids are lowercase by convention,
    and a note that opens a sentence with `Attack-last` or writes `Single-frame` should tokenize the
    same way as one that does not."""
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


# ---------------------------------------------------------------------------
# The audit
# ---------------------------------------------------------------------------

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
    """``{ledger key: [dead rung, …]}`` — the committed shape.

    Keyed by entry AND carrying the rungs, so re-closing an entry against a *second* dead rung is a
    change the allowlist notices. A bare key list would have called that green."""
    return {e.key: list(e.dead) for e in sorted(entries, key=lambda e: e.key)}


def unresolved_tally(reviewed: dict, vocab: Vocabulary) -> Counter:
    """Tokens that resolved to nothing, by occurrence — the vocabulary's visible blind spot."""
    tally = Counter()
    for entry in reviewed.values():
        if isinstance(entry, dict):
            tally.update(classify_note(entry.get("reason") or "", vocab).unresolved)
    return tally


# ---------------------------------------------------------------------------
# "what the rule became" — the column that lets a developer rule quickly
# ---------------------------------------------------------------------------

_ARROW = re.compile(r"\s(?:->|\u2192)\s")
_BULLET = re.compile(r"^\s*[*\u2022]\s")
#: A block that says a rung is GONE outranks one that merely mentions it. Without this, `pilot.py`'s
#: live signal docstrings win the race for a rung whose fold map lives one directory away.
_RETIREMENT = re.compile(r"\b(RETIRED|retired|DELETED|deleted|EMERGENT|FOLDED|folded|SUPERSEDED|"
                         r"subsumed|removed with)\b")
_SENTENCE = re.compile(r"(?<=[.!?])\s")


def _prose_blocks(src_root: Path = DEFAULT_SRC) -> list:
    """``[(path, block text)]`` over every docstring and comment run under `src/`.

    Docstrings come from the AST (so a string that is merely assigned is not mistaken for prose) and
    are split into fold-map bullets; comment runs are joined so a wrapped `# RETIRED …` note reads as
    one block."""
    blocks = []
    for path in _python_files(src_root):
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = _rel(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                if doc:
                    blocks.extend((rel, chunk) for chunk in _split_blocks(doc))
        run = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                run.append(stripped.lstrip("#").lstrip(":").strip())   # `#:` is this repo's attr-doc marker
            elif run:
                blocks.append((rel, " ".join(run)))
                run = []
        if run:
            blocks.append((rel, " ".join(run)))
    return blocks


def _split_blocks(doc: str) -> list:
    """A docstring -> bullets and paragraphs, each collapsed to one line."""
    out, current = [], []
    for line in doc.splitlines():
        if _BULLET.match(line) or not line.strip():
            if current:
                out.append(" ".join(current))
            current = [line.strip()] if line.strip() else []
        else:
            current.append(line.strip())
    if current:
        out.append(" ".join(current))
    return [b for b in out if b]


def _rank(rel: str) -> int:
    """Prefer the file a reader would look in for a rung that is gone — the fold maps first."""
    if "/baseline/baseline_" in rel:
        return 0
    if "/doctrines/doctrine_" in rel:
        return 1
    if "/strategy/" in rel:
        return 2
    return 3


def fold_map_targets(rungs, src_root: Path = DEFAULT_SRC) -> dict:
    """``{rung: "what it became"}`` for the rungs given, read out of `src/`'s own fold maps.

    Two match shapes, because the fold maps use both. `baseline_promote` / `baseline_retreat` /
    `baseline_evolution` name a rung in full; `baseline_energy`'s bullets ABBREVIATE — ``concentrate
    / build-active / power-up / spread … -> the ATTACK AXIS`` — so `concentrate-energy-on-wincon`,
    `build-active-wincon` and `power-up-attacker` appear there only as a hyphen-prefix.

    **Ranked by where the answer lives, not by how the name matched.** Preferring an exact hit first
    handed `concentrate-energy-on-wincon` to a *live* signal docstring in `context.py` while its own
    fold map — which spells it `concentrate` — sat one directory away, and handed
    `retreat-to-ready-attacker` to the promote cluster's phrase *"the retreat comparison uses"*. So
    the order is: the fold-map file, then a block that says the rung is GONE, then an exact name,
    then the shorter block. The abbreviation leg is fenced three ways on top of that — only on an
    arrow bullet, only BEFORE the arrow (the left-hand side is the name list, the right-hand side is
    prose), and only against a ``/`` separator (see `_abbreviated_hit`).

    Empty string when nothing in `src/` names the rung. That is a real answer — some rungs were
    deleted with no fold map written — and it is better than inventing a target.

    **Known limitation, cosmetic:** a fold map written as an unpunctuated TABLE rather than as prose
    (`src/agents/mega_starmie/strategy.py`'s rename table) has no sentence boundary to stop at, so
    2 of the 25 cells the current corpus produces run on into the following row. The head of every
    cell is the right answer; only the tail is noise. Truncating at the next arrow would fix those
    two and break every target that legitimately contains one — `attach-energy-last`'s does."""
    wanted = set(rungs)
    best = {}
    for rel, block in _prose_blocks(src_root):
        lowered = block.lower()
        arrow = _ARROW.search(block)
        retirement = 0 if _RETIREMENT.search(block) else 1
        for rung in wanted:
            hit, exact = lowered.find(rung), 0
            if hit < 0 and arrow:
                hit, exact = _abbreviated_hit(lowered, rung, arrow.start()), 1
            if hit < 0:
                continue
            score = (_rank(rel), retirement, exact, len(block))
            if rung not in best or score < best[rung][0]:
                best[rung] = (score, _target_phrase(block, hit))
    return {rung: best.get(rung, ((), ""))[1] for rung in wanted}


def _abbreviated_hit(lowered: str, rung: str, limit: int) -> int:
    """Position of the longest usable hyphen-prefix of `rung` inside the bullet's NAME LIST, or -1.

    "Inside the name list" is what makes this safe, and it was got wrong first: a bare length fence
    let `develop` (7 chars, a perfectly ordinary English word) claim both
    `develop-the-wincon-base-first` and `develop-turbo-flare-recipient` off a sentence about the
    forgo-KO directive. A fold map writes its names slash-separated — ``concentrate / build-active /
    power-up / spread / … -> the ATTACK AXIS`` — so the prefix must be FOLLOWED by ``/`` and either
    preceded by one or sitting at the head of the bullet. Prose cannot satisfy that; a name list
    always does. (A weaker version accepting a backtick on either side let the bare word ``keep``
    claim `keep-line-base-at-discard` off an unrelated keep-cost docstring.)"""
    parts = rung.split("-")
    for cut in range(len(parts) - 1, 0, -1):
        prefix = "-".join(parts[:cut])
        for match in re.finditer(rf"(?<![a-z0-9-]){re.escape(prefix)}(?![a-z0-9-])", lowered):
            if match.start() >= limit:
                continue
            before = lowered[:match.start()].rstrip().rstrip("*").rstrip()
            after = lowered[match.end():].lstrip()
            if after.startswith("/") and (not before or before.endswith("/")):
                return match.start()
    return -1


def _target_phrase(block: str, hit: int, limit: int = 170) -> str:
    """The fold-map target for the name at `hit` — the SENTENCE it sits in, minus everything up to
    the arrow inside that sentence.

    Sentence-bounded on purpose. Comment runs are joined into one block, so *"the first arrow after
    the hit"* reached across four unrelated notes and answered `play-energy-denial` with a sentence
    about an unrelated 80-damage blunder."""
    starts = [m.end() for m in _SENTENCE.finditer(block, 0, hit)]
    start = starts[-1] if starts else 0
    end = next((m.start() for m in _SENTENCE.finditer(block, hit)), len(block))
    sentence = block[start:end]
    arrow = _ARROW.search(sentence, hit - start)
    tail = " ".join((sentence[arrow.end():] if arrow else sentence).split())
    return tail if len(tail) <= limit else tail[:limit].rsplit(" ", 1)[0] + "…"


# ---------------------------------------------------------------------------
# The generated worklist (ADR-0114 decision 4)
# ---------------------------------------------------------------------------

#: The frames Issue #238 named by hand, kept so the generated report can RECONCILE against them
#: (acceptance criterion 5). This is data about the ISSUE, not about the codebase — the audit never
#: consults it to decide anything. The body's 13 and the three `refuted` re-reads are already ledger
#: keys; the comment's 14 are Decision-Gate Frame Keys (`<ep>|<seat>|decision|<frame>`), whose ledger
#: key is `<ep>-<frame>`.
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
        "* by disposition: " + ", ".join(f"`{d}` **{len(v)}**" for d, v in sorted(by_disposition.items())),
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _json(doc) -> str:
    """`ensure_ascii=False` so the `_note` fields keep their real em dashes, matching
    `review_correction._save` rather than the gate artifacts (which are ASCII-escaped)."""
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def _write_lf(path: Path, text: str) -> None:
    """LF-framed UTF-8 bytes. `Path.write_text` frames per the WRITING platform, and these files are
    committed — dev is Windows, the grader is Linux, so the framing is chosen rather than inherited
    (the same defect `gates.write_json_artifact` documents at length).

    Not `gates.write_json_artifact` itself, for three reasons that each rule it out: this writer also
    emits Markdown, it keeps the trailing newline those files carry, and `gates` is the *gate* module
    — ADR-0114 decision 5 is precisely that a ledger rule does not live behind a Correction-keyed
    gate function. It is the third LF writer in the repo and the duplication is real; what it must
    never become is a writer that frames newlines differently from the other two."""
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
    print("  by disposition        : " + ", ".join(
        f"{d}={n}" for d, n in sorted(Counter(e.disposition for e in entries).items())))
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
