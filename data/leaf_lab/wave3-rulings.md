# Wave-3 ruling record — the POC-T3 leaf swap (Issue #262)

The developer's per-frame verdicts on the wave-3 packet
([Issue #262 comment](https://github.com/richard-jh-mccrae/PokemonAI/issues/262#issuecomment-5152637450)),
recorded here because most of them change **nothing on disk**: a `REVERT` leaves the recorded label
standing, needs no ledger entry, and shows up only as the Discrimination Gate staying red on that
frame. Without this file the gate's red state has no name attached to it, which is the one thing
`CLAUDE.md` says a ruling record exists to prevent.

This is a **record, not an instrument**. Nothing reads it. `data/leaf_lab/baseline.json` is still the
gate's reference and is still untouched.

## Verdict vocabulary

| verdict | what the developer said | what it changes |
|---|---|---|
| `REVERT` | my recorded pick stands; the new T3 leaf is wrong | nothing — the frame keeps failing the gate |
| `REFUTED` | my recorded pick was wrong too | `reviewed.json` gains a `refuted` entry; the frame stops grading |
| `UN-VOID` | a standing refutation of my pick is withdrawn | that `reviewed.json` entry is removed; the frame re-enters gating |
| `CONFORM` | the new leaf's pick is right; absorb it | the baseline re-captures that row |

## Verdicts

### Batch 1 (2026-08-02, commit `97c3d76`)

| frame | packet rec | verdict | developer's line |
|---|---|---|---|
| `81785223\|0\|decision\|32` | CONFORM | **REFUTED** | Pokégear is not the play with nearly every Supporter already in hand — evolve Staryu → Mega Starmie ex, Hilda for Energy, attach to the Active, Jetting Blow |
| `81785223\|0\|decision\|44` | CONFORM | **REFUTED** | as 32 |
| `81904064\|0\|decision\|44` | REVERT-worthy † | **REVERT** | Lillie's stands; retreating is absurd with the opponent's Active on no Energy and three Energy up off Ignition — Nebula Beam |
| `81904064\|0\|decision\|59` | REVERT-worthy † | **REVERT** | Salvatore stands; evolve the benched Staryu and Jetting Blow for the Knock Out |
| `81904451\|0\|decision\|24` | CONFORM | **REVERT** | Hilda stands — fetch Starmie, evolve, then attack |
| `81904451\|0\|decision\|37` | CONFORM | **REVERT** + UN-VOID | as 24 |
| `81904451\|0\|decision\|50` | REVERT-worthy † | **REVERT** | as 24 |
| `81904451\|0\|decision\|53` | CONFORM | **REVERT** + UN-VOID | as 24, with a Mega Signal in hand |

### Batch 2 (2026-08-02, commit `fab1fb0`)

| frame | packet rec | verdict | developer's line |
|---|---|---|---|
| `81905522\|0\|decision\|28` | CONFORM | **REVERT** | evolve the active Staryu, Lillie's, attach, Knock Out the Active and snipe Riolu |
| `81905522\|0\|decision\|64` | CONFORM | **REVERT** + UN-VOID | attach to Staryu first; Mega Lucario ex is out of one-shot range, so gust up Hariyama (no Energy) and Jetting Blow it, sniping Lucario into Nebula Beam range |
| `81906131\|1\|decision\|25` | CONFORM | **REVERT** | Buddy-Buddy Poffin is vital BEFORE attacking with Turbo Flare |
| `81906755\|1\|decision\|93` | CONFORM (low conf.) | **REVERT** + UN-VOID | attach to the active Starmie before attacking, Salvatore to evolve a benched Staryu, attack and snipe Raging Bolt ex |

### Batch 3 (2026-08-02)

| frame | packet rec | verdict | developer's line |
|---|---|---|---|
| `82225138\|0\|decision\|82` | REVERT-worthy † | **REVERT** | Buddy-Buddy Poffin, then Pokégear, re-decide on the new information (Hilda to fetch Energy for Staryu, or Salvatore to evolve it), then Nebula Beam |
| `82225643\|1\|decision\|57` | REVERT-worthy † | **REVERT** | Items should be used before attacking when they help — with no mainline attacker to replace the Active, Ultra Ball finds a Staryu to evolve next turn, and Hero's Cape gives the mainline attacker more HP |
| `82227388\|0\|decision\|43` | REVERT-worthy † | **REVERT** | the Active is doomed but we have healing — Wally's Compassion, attach Ignition Energy, Nebula Beam |
| `82227388\|0\|decision\|50` | REVERT-worthy † | **REVERT** | as 43: doomed, so heal, then sequence before attaching Ignition Energy and attacking with Nebula Beam |
| `82228017\|0\|decision\|16` | CONFORM | **REVERT** | Cinderace's Turbo Flare gives 3 Energy to Benched Pokémon, so lay down a bench at any cost while it is empty before attacking — Buddy-Buddy Poffin first |

† one of the 15 the developer deferred to Issue #278 S13
([comment](https://github.com/richard-jh-mccrae/PokemonAI/issues/262#issuecomment-5153527951)); the
per-frame verdict supersedes that deferral.

## Card facts, verified at source

Checked against `data/EN_Card_Data.csv` and `docs/rulebook.txt` rather than recalled, because several
went into committed ledger reasons:

- **Staryu (Basic) → Mega Starmie ex (Stage 1)** is a single hop — no intermediate Starmie.
- **Jetting Blow** `{W}` / 120, *"also does 50 damage to 1 of your opponent's Benched Pokémon
  (Don't apply Weakness and Resistance for Benched Pokémon)"*. **Nebula Beam** 3 Energy / 210.
- **Turbo Flare** is Cinderace's (Stage 2) attack: 1 Energy, 50 damage, search up to 3 Basic Energy
  onto Benched Pokémon.
- **Tera Pokémon ex take NO attack damage while Benched**, from *both* players' attacks
  (`docs/rulebook.txt` Appendix 6 L356; `docs/rules.md:185`). **Wellspring Mask Ogerpon ex** is
  Tera(Water) and **Teal Mask Ogerpon ex** is Tera(Grass) — neither is a legal snipe target on the
  Bench. This corrected a rationale already committed in batch 1.
- Legal snipe targets named above: **Riolu** (Basic, 70 HP) and **Raging Bolt ex** (Basic, 240 HP,
  category *Ancient*, not Tera).
- **Hariyama** is retreat **3**, not 2 as the `81905522|64` rationale said. The discrepancy cuts in
  the line's favour, so the reasoning holds.

## Open discrepancies (flagged, not resolved)

1. `81906131|1|decision|25` carries a `covered` entry reading *"degenerate record (chosen ==
   correct)"* — filed as structurally unsatisfiable. The developer's *"my ruling stands"* contradicts
   that framing. One of the two readings is wrong; the entry is non-voiding either way, so the frame
   still gates and nothing was changed.
2. `82227388|0|decision|50`'s recorded pick is Pokégear 3.0, but the rationale leads with the heal.
   Read as `REVERT` (the label stands, the heal falling later in the same turn), consistent with the
   `covered` entry's *"human wanted Pokegear as the first dev"*.

## The pattern these verdicts are making

17 frames ruled, **zero CONFORM**. The packet recommended CONFORM on 10 of them and every one was
overturned, so the packet's read was wrong and should not be trusted for the remainder.

Two things recur:

- **Four of the six voided frames fell to one misreading.** `81904451|37`, `|53`, `81905522|64` and
  `81906755|93` all carried a refutation of the form *"forgoes a KO / a 209-damage attack —
  over-eager"*. None of the developer's lines forgoes the attack; each **sequences it later in the
  same turn**. `81904451|58` and `82525741|81` are the two survivors, and `|58` carries the identical
  reason — it has NOT been ruled and must not be assumed.
- **Every `covered` entry on the batch-3 frames dismisses the same thing as a nicety** —
  *"same-turn ordering nicety"*, *"first-dev-differs"*, *"attack-last"*. The developer's rationales
  say the opposite: the ordering **is** the decision (bench before Turbo Flare; Item before
  attacking; heal before attaching).

Both point at one gap: the leaf cannot represent **sequencing within a turn**, so it prices a
develop-then-attack line and an attack-now line as the same board and lets `survival` break the tie
toward passivity. That is a T3 finding, not the Issue #278 artifact the deferral assumed — but it is
recorded here as an observation over 17 frames, not yet a diagnosis.
