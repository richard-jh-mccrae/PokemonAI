# ADR-0054: The stat provider splits into parser battery, indexes, and records

**Status.** Accepted (2026-07-13) and **BUILT** — `scouting/card_text.py` (parser battery) and
`scouting/forward_index.py` (name-keyed indexes) are merged to main, with `provider.py` re-exporting
every moved name so all historical import paths stay valid. Byte-faithful move; neutrality proven by
score-diff (315 frames × 3 agents, 0 divergent).

**Context.** After ADR-0056 made `scouting/provider.py` the one card-knowledge seam, the
module fused five clusters with no shared state (~1040 lines): the card-text parser battery
(~20 `parse_*` functions + their regexes — the deep core), the forward-evolution index
(`_ForwardIndex`, already deep, merely colocated), the `CardStat` record + `_build_cache`,
`AttackStat` + `build_attack_stats`, and the two adapters. The 0056 series deliberately left
layout alone ("in place, stable imports"); this series is that deferred split. Tests and
tools import `provider.AttackStat` / `CardStat` / `DictCardStatProvider` / `parse_*` /
`_build_cache` heavily, so the import path is load-bearing.

**Decision.**
- **`scouting/card_text.py`** owns the parser battery: free text in, typed facts out. All
  `parse_*` functions, the Tool-skill helpers (`_parse_tool_hp_bonus`,
  `_parse_tool_retreat_reduction`), their regexes, `_sentences`, `_TYPE_LETTER`. No engine
  import, no record types — the shared under-credit doctrine documented in the module.
- **`scouting/forward_index.py`** owns the name-keyed indexes over a built cache:
  `_ForwardIndex` (Evolving Threat, ADR-0020) and `_name_index` (the Brief's name→ids
  bridge, ADR-0027). Type-only import of `CardStat` — no runtime cycle.
- **`provider.py` keeps records, builders, adapters**: `CardStat` + `_build_cache`,
  `AttackStat` + `build_attack_stats` + `load_attack_overrides` (file-IO, not parsing), and
  the two providers. It **re-exports every moved name**, so every historical import path
  (`from common.scouting.provider import parse_attack_recoil, …`) stays valid — the
  re-export block is the documented compatibility surface, not an accident.
- Byte-faithful moves only: code, comments, and ordering copied verbatim; no renames, no
  behavior edits riding along.

**Considered options.** Redirecting all import sites to the new modules (rejected: ~75
files churn for zero information gain; the re-export costs one import block). Moving the
records out with the parsers (rejected: the builders are the records' only writers — they
belong together, and "provider" remains the honest name for records + adapters). A
package split (`scouting/provider/`) (rejected: three flat modules carry it; the package
adds a layer of `__init__` indirection for nothing).

**Consequences.** The parser battery is a standalone text→facts module a reader can hold in
one sitting; new parsers land in `card_text.py`, new record fields and builder folds in
`provider.py`. Import stability proven by the unchanged test suite (no test file touched);
neutrality proven by score-diff `scores` mode (315 frames × 3 agents, 0 divergent).
