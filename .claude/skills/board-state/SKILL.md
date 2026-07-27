---
name: board-state
description: Print the COMPLETE board state of one diagnostic frame — both sides' active/bench/hand/deck/discard/prizes, the turn-so-far allowances (energy attached? supporter played? retreated?), the options offered and the ruling — by running tools/train/frame_view.py and relaying its output verbatim as a phone-width plain-text list. Use whenever the user names a frame key like "82756664-97" and wants the board pulled up: "board state for 82756664-97", "pull up the full board state of f97", "what's the state at 83686860-29", "/board-state <key>". Do NOT reconstruct a board state by hand or from memory — the script is the single source of truth.
argument-hint: "the frame key, e.g. 82756664-97 (--brief to drop card rule text, --width N to widen)"
---

# board-state — the full board state of one frame, from the script

Diagnosing a frame always starts with "pull up the board state for `<ep>-<frame>`". Doing that by
hand is slow and, worse, **inconsistent** — a different subset of the state each time, formatted a
different way, so two sittings on the same frame aren't comparable. `tools/train/frame_view.py` is
the single deterministic answer. Your job here is to **run it and relay it** — not to rebuild it.

## Do exactly this

**1. Run the script.** The argument is the frame key.

```
python tools/train/frame_view.py <key>
```

e.g. `python tools/train/frame_view.py 82756664-97`. Pass through what the user asked for:
`--brief` (drop attack/ability rule text — the bulk of the length), `--width N` (they're on a wide
terminal), `--deck-order` (the raw deck order), `--replay <path>` (they named a replay file).

**2. Print its stdout into the chat, verbatim, inside a fenced code block.** The whole thing, top
to bottom. That output *is* the deliverable.

The fence is **not optional**. The read-out is laid out for a phone — every line is pre-wrapped to
38 characters, and the indentation is what carries the structure. Unfenced, the chat client reflows
it and the column collapses into mush. Fence it and the layout survives.

**3. Stop there.** No summary, no analysis, no "key takeaways", no next-step suggestion — unless
the user asks. They asked for the board state; give them the board state and wait.

## Hard rules

- **Never hand-build a board state.** Not a single HP total, energy count or hand list from memory
  or from reading the JSON yourself. If the script won't resolve the frame, say so and stop (see
  below) — a reconstructed dump is exactly the inconsistency this skill exists to end.
- **Never reformat it.** No markdown tables, no re-ordering the sections, no collapsing the zones
  into prose, no re-wrapping to a different width, no trimming "for brevity" — the fixed shape is
  the whole point, and the user asked for a plain-text list at a phone-readable width specifically.
- **Never abridge it in the reply.** If the output feels long, that is what `--brief` is for — ask,
  or run it. Silently printing half the zones is the failure mode this skill was built to end.
- **Never drop the visibility labels.** `[hidden from you]` marks a zone the agent could **not**
  see; the full-information film lists it anyway. Reasoning "it should have known" off a hidden
  zone is the trap those labels exist to stop, and stripping them re-opens it.
- **Never re-attribute the turn flags.** The read-out names the **turn player** who owns
  `energy attached` / `supporter played` / `retreated` / `stadium played`. A seat is regularly
  prompted *out of turn* — a post-KO promotion is prompted during the opponent's turn — and then
  those flags are the opponent's, and the output says so. Don't paraphrase them as "you".

## When the frame won't resolve

The script exits non-zero and names every store it searched. Raw replays are not committed
(ADR-0002), so on a fresh clone only **tagged** frames (the Correction log) and fixtured frames
resolve. Relay the error, then offer the two real options:

- `python tools/train/frame_view.py --list <episode>` — the frame keys that *do* resolve for that
  episode (the script prints these automatically on a miss). Plain `--list` covers every episode.
- `--replay <file>` — with the episode's film on disk, **any** frame resolves, not just tagged ones.

A scoped Correction key (`<ep>-t<turn>s<seat>`, `<ep>-m<seat>`) names a Turn or a whole Match, not
one frame, so it has no single board state. The script says so; pass the Anchor frame instead.

## Width

The default column is **38 characters**, sized for reading on a handset — every line is wrapped to
it with a hanging indent, so nothing is truncated and nothing needs a wide terminal. Card zones are
grouped by category and comma-joined rather than given a line each, which is what keeps a 25-card
deck to a handful of lines. `--width N` widens it for a desktop terminal; `--brief` drops card rule
text and keeps every zone, count and flag.

## What the read-out contains

So you can answer follow-ups without re-running or guessing — sections in fixed order:

- **header** — the frame key, turn, which store the snapshot came from, our agent and build, and
  whether it is the full-information film or the narrower per-seat Observation.
- **THE DECISION** — the `SelectContext` in plain English, every option offered resolved to the
  card/slot it names, what the agent chose, the human ruling (`correct`, category, rationale) when
  the frame is a tagged Correction, and the agent's own `live_trace` scores.
- **TURN STATE** — turn number, first player, **turn player**, each per-turn allowance with what it
  means for what's still legal, action count, the Stadium in play, and the match result.
- **each side, asked seat first** — prizes remaining and their contents, Active (with HP remaining,
  damage, effect-modified vs printed max HP, stage, type, weakness, retreat cost, prize value,
  attached energy and tools, what it evolved from, its attacks and abilities), special conditions,
  the Bench, the hand, the deck and the discard — each labelled for visibility.

Card facts (printed HP, weakness, retreat, attack names and costs, prize value) come from the
committed tables in `src/cgpy/defs/` — never from memory, per `CLAUDE.md`. Affordability is
deliberately **not** computed: the read-out puts attached energy and each attack's printed cost side
by side and leaves that judgment to the reader.
