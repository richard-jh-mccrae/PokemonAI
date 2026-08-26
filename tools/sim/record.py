"""Capture a Battle match into a cabt-`visualize`-shaped replay film (grilled 2026-07-05, Tier-5
finish plan).

`battle.py`'s `play_match` shuttles each seat's observation to its process-isolated agent and reads
back a choice — everything a training film needs. Process isolation is the ONLY collision-free path
(the in-process selfplay loader collides in `sys.modules` on two decks' bare
``from strategy import STRATEGY``), so the cross-deck gauntlet corpus is recorded HERE, off the same
loop that already runs the A/B, and emitted in the exact `visualize` shape the shipped readers expect
(`train.blunder.decisions._film` / `iter_decisions`, the Corpus readers, `meta_tracker`) —
one corpus format across every replay tool, no new extractor.

The one subtlety is the cabt film's **+1 offset**: the choice made in response to the prompt at frame
``i`` is recorded in frame ``i+1``'s ``selected`` (and the obs aligned to that decision is frame
``i+1``'s ``obs``). `MatchRecorder` reproduces that convention so `iter_decisions` recovers each
choice option-for-option, exactly as it does off a real `env.toJSON()` film.
"""
from __future__ import annotations


class MatchRecorder:
    """Accumulate one match's ``(obs, choice)`` steps, then emit a `visualize`-shaped replay dict.
    `finish`'s ``winner`` is the ENGINE seat (0/1) or None."""

    def __init__(self) -> None:
        self._steps: list[tuple[dict, list]] = []   # (obs shown to the actor, the choice it returned)
        self._terminal: dict | None = None
        self._winner: int | None = None
        self._visualizer: list[dict] | None = None

    def step(self, obs: dict, choice) -> None:
        """Record one engine step: the observation shown to the acting seat and the option indices it
        chose in response (the film's +1-offset pairs this choice with THIS obs's prompt)."""
        self._steps.append((obs, list(choice) if choice is not None else None))

    def finish(self, terminal_obs: dict, winner: int | None,
               visualizer: list[dict] | None = None) -> None:
        """Close with the legal terminal observation and the engine's full-information viewer film."""
        self._terminal = terminal_obs
        self._winner = winner
        self._visualizer = visualizer

    def _frame(self, obs: dict, selected) -> dict:
        """One `visualize` frame: `obs`/`current`/`select` snapshot at this state, plus ``selected`` =
        the choice made in RESPONSE to the PREVIOUS frame's prompt (the cabt +1-offset)."""
        obs = obs or {}
        return {"obs": obs, "current": obs.get("current"), "select": obs.get("select"),
                "selected": selected}

    def _rewards(self) -> list[int]:
        """Seat-indexed rewards `winner_index` reads: seat 0 win → ``[1, -1]``, seat 1 → ``[-1, 1]``,
        a draw / unfinished → ``[0, 0]`` (equal rewards → no win label)."""
        if self._winner == 0:
            return [1, -1]
        if self._winner == 1:
            return [-1, 1]
        return [0, 0]

    def _action(self, frame: int, decklists) -> list:
        if frame == 0:
            return ([None, None] if decklists is None else
                    [list(deck) if deck is not None else None for deck in decklists])
        obs, choice = self._steps[frame - 1]
        actor = ((obs or {}).get("current") or {}).get("yourIndex")
        action = [None, None]
        if actor in (0, 1):
            action[actor] = choice
        return action

    def _replay_steps(self, frames: list[dict]) -> list[list[dict]]:
        def row(action, observation, status, reward=0):
            return {"action": action, "info": {}, "observation": observation,
                    "reward": reward, "status": status}

        opening = [row([], {}, "ACTIVE"), row([], {}, "ACTIVE")]
        opening[0]["visualize"] = frames
        steps = [opening]
        rewards = self._rewards()
        for frame in frames:
            current = frame.get("current") or {}
            actor = current.get("yourIndex")
            terminal = current.get("result") not in (None, -1)
            action = frame.get("action") or [None, None]
            steps.append([
                row(action[seat], frame.get("obs") if seat == actor else {},
                    "DONE" if terminal else "ACTIVE" if seat == actor else "INACTIVE",
                    rewards[seat] if terminal else 0)
                for seat in (0, 1)
            ])
        return steps

    def _require_full_information(self, frames: list[dict]) -> None:
        if self._visualizer is None or len(self._visualizer) != len(frames):
            raise ValueError("replay visualizer is missing full-information frames")
        for frame in frames:
            players = ((frame.get("current") or {}).get("players") or [])
            if len(players) != 2:
                raise ValueError("replay visualizer is missing full-information players")
            for player in players:
                for area in ("hand", "prize"):
                    cards = player.get(area) if isinstance(player, dict) else None
                    if not isinstance(cards, list) or any(not isinstance(card, dict)
                                                          for card in cards):
                        raise ValueError(
                            f"replay visualizer has incomplete full-information {area}")

    def replay(self, *, episode_id: int, team_names: list[str], decklists=None,
               require_visualizer: bool = False) -> dict:
        """The full replay dict — the `visualize` film with +1-OFFSET selections, seat-indexed
        ``rewards``, and ``info``. The same envelope `selfplay` writes, byte-shape for byte-shape."""
        frames: list[dict] = []
        prev_choice = None
        for obs, choice in self._steps:
            frames.append(self._frame(obs, prev_choice))
            prev_choice = choice
        if self._terminal is not None:
            frames.append(self._frame(self._terminal, prev_choice))   # gives the last decision its +1 obs
        if self._visualizer is not None and len(self._visualizer) == len(frames):
            for index, (frame, visual) in enumerate(zip(frames, self._visualizer)):
                if not isinstance(visual, dict):
                    continue
                merged = dict(visual)
                merged["obs"] = frame["obs"]
                current = visual.get("current")
                if isinstance(current, dict):
                    actor = (frame.get("current") or {}).get("yourIndex")
                    merged["current"] = dict(current)
                    merged["current"]["yourIndex"] = actor
                else:
                    merged["current"] = frame["current"]
                merged.setdefault("select", frame["select"])
                merged.setdefault("selected", frame["selected"])
                frames[index] = merged
        for index, frame in enumerate(frames):
            frame["action"] = self._action(index, decklists)
        if require_visualizer:
            self._require_full_information(frames)
        return {
            "steps": self._replay_steps(frames),
            "rewards": self._rewards(),
            "info": {"EpisodeId": episode_id, "TeamNames": list(team_names)},
        }
