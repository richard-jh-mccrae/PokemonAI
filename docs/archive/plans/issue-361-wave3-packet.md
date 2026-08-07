# Issue #361 — wave-3 gate-flip packet

**No flip was CONFORMED.** Neither `data/leaf_lab/baseline.json` nor `data/decider_lab/baseline.json`
was touched: a baseline is a ruling record, and auto-recapture is how the old Decision Gate died
(`CLAUDE.md`, ADR-0072). Proof, taken before the first source edit and again after the last one:

```
ed12a86760d42c9178a51ff2b0fc260d  data/leaf_lab/baseline.json      (pre == post)
bcc5c07433d733333155d4a5f0e51d5e  data/decider_lab/baseline.json   (pre == post)
```

Issue #361 landed **alone** on its branch specifically so any flip would be unambiguously
attributable to it. It changes a shipped damage number (attacks 651 and 708 fall from a frozen flat
`80` to `40 × count`), which moves the damage oracle and therefore `state_value`'s `threat` and
`survival` terms — a legitimate cause of movement, not a bug.

## Flips

| frame | gate | issue | old | new | recommendation |
|---|---|---|---|---|---|
| — | — | — | — | — | **none: this change moved neither gate** |

**Zero rows, and the reason is checkable rather than lucky.** Both gate runs' *entire stdout* is
byte-identical before and after the change (`diff` clean, not merely the same summary line):

| gate | pre-change | post-change |
|---|---|---|
| Discrimination (`leaf_lab diff`) | FAIL — 1 unruled, 65 ruled, 3 voided, 199 gated | FAIL — 1 unruled, 65 ruled, 3 voided, 199 gated |
| Decision (`decider_lab diff`) | PASS — 0 unruled, agree 250/347, 0 picks moved | PASS — 0 unruled, agree 250/347, 0 picks moved |
| CI audit (`ci_audit_gate.py`) | OK — 59 match, 13 gaps, **0 over-prediction** | OK — 59 match, 13 gaps, **0 over-prediction** |

The single Discrimination-Gate `unruled` is the **known pre-existing red** on
`81906755|1|decision|9`, developer-ruled REVERT in commit `a878ed7`; `main` is red on it and this
branch inherits it unchanged. Nothing beyond that one appeared.

**Why zero is the expected answer here, stated so it is not mistaken for a gate that did not run.**
Cards **462 Team Rocket's Weezing** and **501 Palpitoad** are absent from every `src/agents/*/deck.csv`
(6 decks) and from every fixture in `tests/fixtures/corrections/` (208 files). Re-derived on this
branch rather than inherited from Issue #361's body, and with a positive control in each direction:
the same deck scan finds 121/1031/1030/666/163 in the decks that run them, and the same fixture walk
finds *card* id 708 in five fixtures — so neither instrument is silently quiet. No corpus frame can
present an attack neither
seat holds, so no frame's `threat`/`survival` reads either number. The gates therefore have nothing
to say about this change, which is a different statement from "the change was harmless": the
correctness evidence is `tests/parity/test_damage_goldens.py`, where the engine and the agent are
driven over the same hand-built board and pinned EQUAL at counts 1–4.

Re-run once more against the final tree after the two Leaf-Profile / vocabulary declarations landed:
all three gate outputs remained byte-identical to the pre-change readings, and both baseline hashes
above are unchanged.

## Follow-ups filed rather than built

* **Issue #364** — no audit sweep axis varies WHICH cards are in play, so this family is unfittable;
  it owns the measurement debt and is the `owner` on both provenance rows.
* **Issue #365** — attacks `707` / `710` / `1214` (`Round` on Tympole / Seismitoad / Wigglytuff) still
  price to ZERO agent-side though the engine prices them and the vocabulary can now express them.
  Deliberately not bundled: three more moved numbers would have made this packet ambiguous.
