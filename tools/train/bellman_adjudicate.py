"""Rationale-led adjudication of the unfiltered Mega Starmie Bellman sweep."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / "docs" / "plans" / "mega-starmie-live-corpus-baseline.json"
OUTPUT = REPO / "docs" / "plans" / "mega-starmie-bellman-adjudication.json"
MARKDOWN = REPO / "docs" / "plans" / "mega-starmie-bellman-adjudication.md"

MATCH = "MATCH"
EQUIVALENT = "EQUIVALENT_OR_BETTER_COMPLETE_LINE"
STALE = "STALE_LABEL_RATIONALE_AGREES"
ERROR = "BELLMAN_ERROR"
UNMODELLED = "UNMODELLED"
CLASSES = {MATCH, EQUIVALENT, STALE, ERROR, UNMODELLED}


def _keys(text: str) -> set[str]:
    return set(text.split())


# Every mismatch is listed deliberately. New or changed mismatches fail closed below.
EQUIVALENT_KEYS = _keys("""
81904451-6 81904451-37 81904451-53 81904451-58 82224509-40 82225643-57
82226116-48 82226116-70 82226116-100 82748522-15 82749656-62 82750161-16
82751468-14 82753102-37 82754875-8 82867148-34 82867148-62 82867148-87 83038055-40
83053965-32 83455356-11 83968638-17 85164605-64 91393371-38
""")

STALE_KEYS = _keys("""
81903490-5 81904064-29 81906131-25 82225138-46 82225643-34 82227388-7
82523811-59 82525741-81 82748422-26 82750161-59 82752045-94 82752045-97
82754241-41 82756664-74 83053965-6 83456015-47 83457493-33 83662396-19
83664340-24
""")

UNMODELLED_KEYS = _keys("""
81785223-32 81785223-44 82523164-55 82523811-79 82749168-62 82751468-57
82754241-12 83116501-60 83117367-34 83667237-107 91393371-60 91394270-12
91394270-85
""")

ERROR_KEYS = _keys("""
81785223-38 81903490-67 81904064-44 81904064-49 81904064-59 81904451-15
81904451-24 81904451-50 81905063-10 81905522-28 81905522-47 81906755-77
81906755-93 82224509-29 82224509-67 82224509-71 82225138-19 82225643-11
82225643-12 82226116-94 82226759-16 82226759-29 82226759-64 82227388-22
82227388-50 82228640-9 82229122-17 82522698-36 82523811-15 82523811-84
82525101-14 82525101-92 82525101-102 82749168-29 82749168-65 82752045-80
82753102-9 82753102-16 82753102-109 82754241-11 82756664-35 82756664-36
82756664-37 82866415-43 83007714-7 83007714-22 83037962-48 83053965-28
83116081-17 83116501-89 83454549-36 83456015-38 83457493-20 83661649-54
83664991-25 83666442-27 83667237-87 83667237-120 83966968-45 83966968-78
84897262-100 85163634-41 85164605-41 91393371-9 91394270-9
""")


NOTES = {
    "81903490-5": "The rationale forbids first-turn Ignition; End obeys it. Poffin was an accidental label.",
    "81904064-29": "The rationale only rejects a ten-damage Wally. Poffin also rejects it and develops the line.",
    "81904451-6": "Poffin is a beneficial prefix; it does not make the forbidden Ignition attachment.",
    "81904451-37": "Water attachment is retained before the Hilda/evolve/retreat continuation.",
    "81906131-25": "Chosen Basic Water is exactly what the rationale says; the Ignition label is inverted.",
    "82224509-40": "Free retreat and the requested reserve attachment commute inside the same turn.",
    "82225138-46": "Current Scouting marks Kangaskhan as prize liability and Dwebble as avoid; the old weak-body label is superseded.",
    "82225643-34": "The old 'Pokégear has no downside' premise conflicts with portable Worth; Cape realizes value now.",
    "82225643-57": "Cape is retained as a useful prefix before the same Ultra Ball development.",
    "82226116-48": "Attach then free-retreat reaches the rationale's double-KO line.",
    "82226116-70": "Free retreat does not consume evolve or attach; the same setup remains reachable.",
    "82226116-100": "The chosen attachment is the first step stated by the rationale, before retreat and KO.",
    "82227388-7": "Staryu is the deck's main-attacker base and retains Cape when it evolves.",
    "82523811-59": "The ruled label says Bench, while its rationale says Active; Wally is a valued heal prefix.",
    "82525741-81": "Chosen Active attachment exactly matches the rationale; the recorded Bench index is stale.",
    "82748422-26": "The rationale only forbids wasted Hammer. Wally avoids Hammer and preserves a positive heal line.",
    "82748522-15": "Attach before Lillie's preserves the exact gamble requested by the rationale.",
    "82749656-62": "Wally's resolving continuation wins this turn and is valued above the bare attack, not instead of a win.",
    "82750161-16": "Attach is a persistent prefix before Mega Signal; no allowance conflict exists.",
    "82750161-59": "Ignition on the Bench evaporates after the attack; persistent Water is the better retained resource.",
    "82751468-14": "Free retreat and attachment commute; the KO continuation remains reachable.",
    "82752045-94": "The rationale only rejects hand refresh; Jetting is a legal resolving attack and preserves the hand.",
    "82752045-97": "Unused Ignition would discard at end of turn; persistent Water dominates the stale concentration label.",
    "82753102-37": "The rationale forbids Hammer; the chosen persistent attachment is a beneficial pre-attack step.",
    "82754241-41": "The chosen retreat never spends the condemned Hammer and preserves a better resolving line.",
    "82754875-8": "Both indices are interchangeable physical copies of Lillie's Determination.",
    "82756664-74": "The rationale only rejects Hilda and does not justify Ignition over persistent Water.",
    "82867148-34": "Cinderace attachment is retained before Ultra Ball, Bench deployment, and Turbo Flare.",
    "82867148-62": "Poffin develops recipients before Turbo Flare and avoids the retreat condemned by the rationale.",
    "83038055-40": "Persistent attachment is retained before the same low-hand Lillie's replan.",
    "83053965-6": "The rationale only forbids unusable first-turn Ignition; End obeys it. Mega Signal was an accidental label.",
    "83053965-32": "Free retreat before the requested attachment preserves the KO continuation.",
    "83455356-11": "Attachment is a commutative first step before Salvatore/evolve/free-retreat/game-win.",
    "83456015-47": "Wally is stale here: the manual attach was already spent, so bounce forfeits the KO; Poffin preserves it.",
    "83457493-33": "The rationale only forbids recycling Cinderace; Poffin does not recycle it.",
    "83662396-19": "Deck thinning without live demand is pure cost under the accepted value invariant.",
    "83664340-24": "Nebula Beam is the known KO described by the rationale; the Lillie's label contradicts it.",
    "83968638-17": "The rationale only rejects wasted Hammer; attach then attack is the valuable continuation.",
    "85164605-64": "Boss is a positive prefix before the attack and avoids the empty Ultra Ball condemned by the rationale.",
    "91393371-38": "Lillie's expected-value prefix retains the same Nebula Beam continuation; the attack is not lost.",
    "82523164-55": "Historical Switch target frames omit the parent attack continuation needed to prove the double KO.",
    "82749168-62": "The rationale compares a three-turn Jetting/Nebula policy; the prototype turn boundary cannot prove it.",
    "82751468-57": "The rationale depends on earlier private deck-search history absent from this snapshot.",
    "82754241-12": "The rationale depends on an earlier exact deck census absent from this historical snapshot.",
    "83116501-60": "The rationale compares a three-turn attack schedule outside this prototype's one-turn horizon.",
    "83117367-34": "The rationale depends on earlier deck-search history and exact prize inference absent from this snapshot.",
    "83667237-107": "The rationale requires a multi-turn prize-route commitment beyond the current turn tree.",
    "81785223-32": "No rationale was recorded; the old Pokégear index cannot overrule the resolving attack by itself.",
    "81785223-44": "No rationale was recorded; the snapshot gives no human reason to spend Pokégear over End.",
    "82523811-79": "No rationale was recorded, so the old Hammer label has no rationale-led authority.",
    "91393371-60": "No rationale was recorded for Pokégear over the selected heal line.",
    "91394270-12": "The rationale discusses starter identity, not the offered Pokégear-versus-End decision.",
    "91394270-85": "Neither a correct selection nor an actionable rationale was recorded.",
}


def key(row: dict) -> str:
    return f"{row['episode']}-{row['frame']}"


def classification(row: dict) -> tuple[str, str]:
    if row["agrees"]:
        return MATCH, "Equivalent-aware live choice agrees with the correction."
    frame = key(row)
    memberships = [name for name, keys in (
        (EQUIVALENT, EQUIVALENT_KEYS), (STALE, STALE_KEYS),
        (ERROR, ERROR_KEYS), (UNMODELLED, UNMODELLED_KEYS),
    ) if frame in keys]
    if len(memberships) != 1:
        raise ValueError(f"{frame}: expected one manual disposition, got {memberships}")
    result = memberships[0]
    note = NOTES.get(frame)
    if note is None and result == ERROR:
        note = ("The planner currently ranks the recorded live choice over the rationale's action; "
                "this remains an explicit value/horizon tuning error, not a covered exemption.")
    elif note is None and result == EQUIVALENT:
        note = ("The chosen action is a beneficial first step that preserves the rationale's payoff "
                "in the same turn; this is a complete-line ordering difference.")
    elif note is None and result == STALE:
        note = ("The indexed action is not supported by the primary rationale or the accepted "
                "benefit-minus-cost invariant; the live choice obeys the stated constraint.")
    elif note is None and result == UNMODELLED:
        note = ("The ruling needs missing match history, a multi-turn commitment, or a usable human "
                "rationale that is not present in this decision snapshot.")
    if note is None:
        raise ValueError(f"{frame}: {result} needs a written adjudication")
    return result, note


def adjudicate(payload: dict) -> dict:
    rows = []
    for source in payload["rows"]:
        row = dict(source)
        row["classification"], row["adjudication"] = classification(row)
        rows.append(row)
    counts = Counter(row["classification"] for row in rows)
    return {
        "schema": 1,
        "deck": payload["deck"],
        "source_git_rev": payload["git_rev"],
        "source_generated_at": payload["generated_at"],
        "records": len(rows),
        "excluded": 0,
        "counts": {name: counts.get(name, 0) for name in sorted(CLASSES)},
        "unexplained": 0,
        "rows": rows,
    }


def markdown(payload: dict) -> str:
    counts = payload["counts"]
    lines = [
        "# Mega Starmie Bellman corpus adjudication", "",
        f"Unfiltered records: **{payload['records']}**. Excluded: **0**. Unexplained: **0**.", "",
        "| classification | count |", "|---|---:|",
        *[f"| `{name}` | {counts[name]} |" for name in sorted(counts)], "",
        "The correction rationale is primary. `BELLMAN_ERROR` rows are named tuning debt; they are "
        "not hidden by historical coverage. Complete-line rows preserve the stated payoff after a "
        "different beneficial first step. `UNMODELLED` is limited to missing history, multi-turn "
        "commitments, or absent human rulings.", "",
        "| frame | class | live | recorded | rationale-led adjudication |",
        "|---|---|---|---|---|",
    ]
    for row in payload["rows"]:
        if row["classification"] == MATCH:
            continue
        clean = lambda value: str(value or "").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{key(row)}` | `{row['classification']}` | {clean(row['chosen_label']) or '∅'} "
            f"| {clean(row['correct_label']) or '∅'} | {clean(row['adjudication'])} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--markdown", type=Path, default=MARKDOWN)
    args = parser.parse_args(argv)
    payload = adjudicate(json.loads(args.baseline.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(payload), encoding="utf-8")
    print(json.dumps({"records": payload["records"], "counts": payload["counts"],
                      "unexplained": payload["unexplained"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
