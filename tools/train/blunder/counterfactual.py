"""Record an executable ideal turn through cgpy and prove safe adjacent action swaps.

The recorder keeps semantic option identities, never menu positions alone. Commutativity is earned
only when cgpy can execute both orders from the same fork and their complete state signatures match.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, is_dataclass

from .decode import option_label

_AREAS = {1: "deck", 2: "hand", 3: "discard", 4: "active", 5: "bench",
          6: "prize", 7: "stadium", 12: "looking"}
_PLAY = 7
_MAIN = 0
_OPTION_TYPE = {"Play": 7, "Attach": 8, "Evolve": 9, "Ability": 10,
                "Discard": 11, "Retreat": 12, "Attack": 13, "End": 14}


class ChoiceUnavailable(ValueError):
    pass


def _prune_none(value):
    if isinstance(value, dict):
        return {key: _prune_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_prune_none(item) for item in value]
    return value


def _card_at(obs: dict, *, area, index, seat):
    if not isinstance(index, int) or index < 0:
        return None
    current = obs.get("current") or {}
    if area == 12:
        zone = current.get("looking") or []
    elif area == 7:
        zone = current.get("stadium") or []
    elif area == 1 and (obs.get("select") or {}).get("deck") is not None:
        zone = (obs.get("select") or {}).get("deck") or []
    else:
        players = current.get("players") or []
        key = _AREAS.get(area)
        if key is None or not isinstance(seat, int) or not 0 <= seat < len(players):
            return None
        zone = (players[seat] or {}).get(key) or []
    return zone[index] if index < len(zone) and isinstance(zone[index], dict) else None


def _selector(option: dict, obs: dict) -> dict:
    seat = option.get("playerIndex", (obs.get("current") or {}).get("yourIndex", 0))
    refs = []
    locators = (("source", "area", "index"), ("target", "inPlayArea", "inPlayIndex"))
    for role, area_key, index_key in locators:
        area = option.get(area_key)
        if role == "source" and area is None and option.get("type") == _PLAY:
            area = 2
        if area is None:
            continue
        index = option.get(index_key)
        card = _card_at(obs, area=area, index=index, seat=seat)
        refs.append({"role": role, "area": area, "seat": seat, "index": index,
                     "card_id": card.get("id") if card else None,
                     "serial": card.get("serial") if card else None})
    ignored = {"area", "index", "inPlayArea", "inPlayIndex", "playerIndex"} if refs else set()
    literal = {key: deepcopy(value) for key, value in sorted(option.items()) if key not in ignored}
    exact = {"literal": literal, "refs": refs}
    equivalent = deepcopy(exact)
    for ref in equivalent["refs"]:
        ref.pop("serial", None)
        ref.pop("index", None)
    return {"exact": exact, "equivalent": equivalent}


def choice_reference(option: dict, obs: dict, *, position: int) -> dict:
    """A selected menu option with exact and duplicate-card-equivalent identities."""
    return {"position": position, "option": deepcopy(option),
            "label": option_label(option, obs.get("current") or {}, select=obs.get("select")),
            "selector": _selector(option, obs)}


def _migrated_selector_match(wanted: dict, offered: dict) -> bool:
    """Accept one unambiguous legacy replay identity after enum/card-id migration."""
    left, right = wanted["selector"]["exact"], offered["selector"]["exact"]
    left_literal, right_literal = dict(left["literal"]), dict(right["literal"])
    left_literal["type"] = _OPTION_TYPE.get(left_literal.get("type"), left_literal.get("type"))
    if left_literal != right_literal or len(left["refs"]) != len(right["refs"]):
        return False
    for before, after in zip(left["refs"], right["refs"]):
        if any(before.get(key) != after.get(key) for key in ("role", "area", "seat")):
            return False
        if before.get("role") == "source" and before.get("card_id") != after.get("card_id"):
            return False
        if (before.get("role") != "source" and before.get("card_id") != after.get("card_id")
                and before.get("serial") != after.get("serial")):
            return False
    return True


def resolve_choice(obs: dict, references: list[dict]) -> list[int]:
    """Resolve saved semantic choices against a new menu; refuse missing or ambiguous identities."""
    options = (obs.get("select") or {}).get("option") or []
    live = [choice_reference(option, obs, position=i) for i, option in enumerate(options)]
    chosen = []
    for wanted in references:
        exact = [row["position"] for row in live
                 if row["selector"]["exact"] == wanted["selector"]["exact"]
                 and row["position"] not in chosen]
        if len(exact) == 1:
            chosen.append(exact[0])
            continue
        equivalent = [row["position"] for row in live
                      if row["selector"]["equivalent"] == wanted["selector"]["equivalent"]
                      and row["position"] not in chosen]
        if not equivalent:
            migrated = [row["position"] for row in live
                        if _migrated_selector_match(wanted, row) and row["position"] not in chosen]
            if len(migrated) != 1:
                raise ChoiceUnavailable(f"{wanted.get('label') or 'choice'} is not offered uniquely")
            chosen.append(migrated[0])
            continue
        chosen.append(min(equivalent))
    return chosen


class _AuditedRng:
    def __init__(self, seed: int):
        from cgpy.rng import SeededRng
        self._inner = SeededRng(seed)
        self.events = []

    def __deepcopy__(self, memo):
        clone = type(self)(0)
        clone._inner = deepcopy(self._inner, memo)
        clone.events = deepcopy(self.events, memo)
        return clone

    def shuffle(self, seq, *, seat):
        self.events.append(["shuffle", seat])
        return self._inner.shuffle(seq, seat=seat)

    def coin(self, seat=None):
        self.events.append(["coin", seat])
        return self._inner.coin(seat)

    def hand_pick(self, seat, hand):
        self.events.append(["hand-pick", seat])
        return self._inner.hand_pick(seat, hand)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _enum_value(enum_type, value):
    if isinstance(value, int):
        return value
    token = "".join(ch.lower() for ch in str(value) if ch.isalnum())
    for member in enum_type:
        if "".join(ch.lower() for ch in member.name if ch.isalnum()) == token:
            return int(member)
    raise ValueError(f"unknown {enum_type.__name__} value {value!r}")


def _wire_select(select: dict) -> dict:
    from cgpy.schema import OptionType, SelectContext, SelectType
    out = deepcopy(select)
    out["type"] = _enum_value(SelectType, out["type"])
    out["context"] = _enum_value(SelectContext, out["context"])
    for option in out.get("option") or []:
        option["type"] = _enum_value(OptionType, option["type"])
    return out


class CgpyBackend:
    name = "cgpy"

    @classmethod
    def start(cls, replay: dict, *, frame: int, rng_seed: int):
        from cgpy.search import state_from_visualize
        from meta_tracker.parse import extract_decks
        film = replay["steps"][0][0].get("visualize") or []
        if not 0 <= frame < len(film):
            raise ValueError(f"frame {frame} is outside the replay")
        row = film[frame]
        current, select = row.get("current") or {}, row.get("select")
        if not isinstance(select, dict) or not select.get("option"):
            raise ValueError(f"frame {frame} has no selectable menu")
        seat = int(current.get("yourIndex", 0))
        engine = state_from_visualize(current, extract_decks(replay), seat=seat,
                                      select=_wire_select(select), rng=_AuditedRng(rng_seed))
        return cls(), engine, seat, int(current.get("turn", 0))

    def fork(self, engine):
        return engine.fork()

    def observation(self, engine, seat):
        from cgpy.search import export_token
        raw = engine.observation(viewer=seat, sbi_token=export_token(engine.gs))
        return _prune_none(asdict(raw) if is_dataclass(raw) else deepcopy(raw))

    def step(self, engine, choice):
        engine.step(list(choice))

    def randomness(self, engine):
        return tuple(tuple(event) for event in getattr(engine.gs.rng, "events", ()))

    def signature(self, engine, seat):
        from cgpy.search import export_internals
        obs = self.observation(engine, seat)
        obs.pop("logs", None)
        players = []
        for board in engine.gs.players:
            players.append({zone: [[serial, engine.gs.card_id(serial)] for serial in getattr(board, zone)]
                            for zone in ("deck", "hand", "prize", "discard")})
        randomizer = getattr(getattr(engine.gs.rng, "_inner", None), "_r", None)
        payload = {"observation": obs, "hidden_zones": players,
                   "internals": export_internals(engine.gs),
                   "random_state": repr(randomizer.getstate()) if randomizer else None}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CounterfactualRecorder:
    def __init__(self, engine, backend, *, seat: int, turn: int, rng_seed: int = 0):
        self.engine, self.backend = engine, backend
        self.seat, self.turn, self.rng_seed = seat, turn, rng_seed
        self.steps = []
        self._history = []
        self._block_starts = {}
        self._block_ends = {}

    @classmethod
    def from_replay(cls, replay: dict, *, frame: int, rng_seed: int = 0):
        backend, engine, seat, turn = CgpyBackend.start(replay, frame=frame, rng_seed=rng_seed)
        return cls(engine, backend, seat=seat, turn=turn, rng_seed=rng_seed)

    def _done(self, obs: dict) -> bool:
        current = obs.get("current") or {}
        return (current.get("result", -1) != -1 or not obs.get("select")
                or current.get("yourIndex") != self.seat or current.get("turn") != self.turn)

    def view(self) -> dict:
        obs = self.backend.observation(self.engine, self.seat)
        done = self._done(obs)
        select = obs.get("select") or {}
        options = [] if done else [choice_reference(option, obs, position=i)
                                   for i, option in enumerate(select.get("option") or [])]
        return {"status": "complete" if done else "recording", "backend": self.backend.name,
                "step_count": len(self.steps), "context": select.get("context"),
                "select_type": select.get("type"), "min_count": select.get("minCount", 0),
                "max_count": select.get("maxCount", 0), "options": options}

    def choose(self, positions: list[int]) -> dict:
        obs = self.backend.observation(self.engine, self.seat)
        if self._done(obs):
            raise ValueError("the counterfactual turn is already complete")
        select = obs.get("select") or {}
        options = select.get("option") or []
        minimum, maximum = int(select.get("minCount", 0)), int(select.get("maxCount", 0))
        if not minimum <= len(positions) <= maximum or len(set(positions)) != len(positions):
            raise ValueError(f"choose {minimum}..{maximum} distinct options")
        if any(not isinstance(pos, int) or not 0 <= pos < len(options) for pos in positions):
            raise ValueError("counterfactual choice is outside the current menu")
        context = int(select.get("context", -1))
        new_block = not self.steps or context == _MAIN
        block = 0 if not self.steps else self.steps[-1]["block"] + int(new_block)
        before = self.engine
        self._block_starts.setdefault(block, before)
        references = [choice_reference(options[pos], obs, position=pos) for pos in positions]
        after = self.backend.fork(before)
        self.backend.step(after, positions)
        record = {"block": block, "context": context, "select_type": select.get("type"),
                  "choice": references, "label": " + ".join(ref["label"] for ref in references)}
        self._history.append(before)
        self.steps.append(record)
        self.engine = after
        self._block_ends[block] = after
        return self.view()

    def undo(self) -> dict:
        if not self.steps:
            raise ValueError("counterfactual recording has no step to undo")
        self.engine = self._history.pop()
        self.steps.pop()
        self._block_starts.clear()
        self._block_ends.clear()
        for i, record in enumerate(self.steps):
            block = record["block"]
            self._block_starts.setdefault(block, self._history[i])
            after = self._history[i + 1] if i + 1 < len(self._history) else self.engine
            self._block_ends[block] = after
        return self.view()

    def _replay_block(self, engine, records):
        current = self.backend.fork(engine)
        for record in records:
            obs = self.backend.observation(current, self.seat)
            if int((obs.get("select") or {}).get("context", -1)) != record["context"]:
                raise ChoiceUnavailable(f"expected context {record['context']} is not active")
            positions = resolve_choice(obs, record["choice"])
            self.backend.step(current, positions)
        return current

    def _relations(self) -> list[dict]:
        blocks = {}
        for record in self.steps:
            blocks.setdefault(record["block"], []).append(record)
        out = []
        ids = sorted(blocks)
        for left, right in zip(ids, ids[1:]):
            lrows, rrows = blocks[left], blocks[right]
            if lrows[0]["context"] != _MAIN or rrows[0]["context"] != _MAIN:
                continue
            relation = {"left_block": left, "right_block": right,
                        "left": lrows[0]["label"], "right": rrows[0]["label"]}
            base = self._block_starts[left]
            try:
                swapped = self._replay_block(base, rrows)
            except (ChoiceUnavailable, ValueError) as exc:
                relation.update(status="ordered", reason=f"right action is unavailable before left: {exc}")
                out.append(relation)
                continue
            try:
                swapped = self._replay_block(swapped, lrows)
            except (ChoiceUnavailable, ValueError) as exc:
                relation.update(status="ordered", reason=f"left action is unavailable after right: {exc}")
                out.append(relation)
                continue
            original = self._block_ends[right]
            base_rng = len(self.backend.randomness(base))
            if (len(self.backend.randomness(original)) > base_rng
                    or len(self.backend.randomness(swapped)) > base_rng):
                relation.update(status="branch-dependent", reason="an order consumed randomness")
            elif self.backend.signature(original, self.seat) == self.backend.signature(swapped, self.seat):
                relation.update(status="commutes", reason="both orders reach the same engine state")
            else:
                relation.update(status="ordered", reason="both orders are legal but reach different engine states")
            out.append(relation)
        return out

    def payload(self) -> dict:
        view = self.view()
        return {"schema": "counterfactual-turn/v1", "backend": self.backend.name,
                "rng_seed": self.rng_seed,
                "status": "complete" if view["status"] == "complete" else "partial",
                "steps": deepcopy(self.steps), "adjacent_relations": self._relations(),
                "randomness": [list(event) for event in self.backend.randomness(self.engine)],
                "end_state_digest": self.backend.signature(self.engine, self.seat)}


def _block_signatures(proof: dict) -> list[dict]:
    blocks = {}
    for step in proof.get("steps") or ():
        block = step.get("block")
        row = {"context": step.get("context"),
               "choice": [choice.get("selector", {}).get("equivalent")
                          for choice in step.get("choice") or ()]}
        blocks.setdefault(block, {"block": block, "label": step.get("label"), "steps": []})
        blocks[block]["steps"].append(row)
    return [blocks[key] for key in sorted(blocks)]


def grade_counterfactual(ideal: dict, candidate: dict) -> dict:
    """Grade two executable turn proofs; equal end states accept any proved action ordering."""
    if ideal.get("status") != "complete" or candidate.get("status") != "complete":
        return {"status": "ungradeable", "reason": "both turn proofs must be complete",
                "end_state_match": False, "first_divergence": None}
    if ideal.get("backend") != candidate.get("backend") or ideal.get("rng_seed") != candidate.get("rng_seed"):
        return {"status": "ungradeable", "reason": "backend or RNG seed differs",
                "end_state_match": False, "first_divergence": None}
    expected, observed = _block_signatures(ideal), _block_signatures(candidate)
    end_match = ideal.get("end_state_digest") == candidate.get("end_state_digest")
    if end_match:
        ordering = "exact" if expected == observed else "equivalent-reorder"
        return {"status": "match", "ordering": ordering,
                "basis": "seeded-sample" if ideal.get("randomness") or candidate.get("randomness")
                else "deterministic",
                "end_state_match": True, "first_divergence": None}
    limit = max(len(expected), len(observed))
    index = next((i for i in range(limit)
                  if i >= len(expected) or i >= len(observed) or expected[i] != observed[i]), 0)
    return {"status": "mismatch", "ordering": None, "end_state_match": False,
            "first_divergence": {"block": index,
                                 "expected": expected[index]["label"] if index < len(expected) else None,
                                 "observed": observed[index]["label"] if index < len(observed) else None}}
