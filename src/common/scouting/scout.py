"""Scout: accumulate revealed-card evidence across a match and produce the Read.

Reads ObservationState only; card stats come from an injected provider. `observe` never raises."""
from __future__ import annotations

from common.observation import ObservationState
from .read import EvoPath, Intel, Read
from .scorer import posterior


class Scout:
    def __init__(self, artifact, provider=None, *, k: int = 3,
                 confidence_threshold: float = 0.6):
        self.artifact = artifact
        self.provider = provider
        self.k = k
        self.confidence_threshold = confidence_threshold
        self._evidence: set[int] = set()
        self._opp_in_play: list[int] = []
        self._last_turn: int | None = None

    def observe(self, state: ObservationState) -> Read:
        try:
            self._maybe_reset(state.turn.number)
            self._absorb(state)
            candidates, unknown_mass = posterior(
                self.artifact.priors, self.artifact.card_inclusion,
                self.artifact.background, self._evidence,
            )
            top = candidates[: self.k]
            threats, targets = self._observed_intel()
            arch = self._confident_archetype(top)        # adds dossier's PREDICTED intel (ADR-0027)
            if arch is not None:
                threats = self._merge_intel(threats, self._dossier_intel(arch, "threats"))
                targets = self._merge_intel(targets, self._dossier_intel(arch, "targets"))
            expected = self._expected_cards(top)
            evolution = self._evolution_paths(top)
            return Read(candidates=candidates, unknown_mass=unknown_mass,
                        confidence=self._confidence(top), evolution_paths=evolution,
                        expected_cards=expected, threats=threats, targets=targets)
        except Exception:
            return Read()

    def _maybe_reset(self, turn: int) -> None:
        # A turn counter only ever increases within a match; a drop means a new match began.
        if self._last_turn is not None and turn < self._last_turn:
            self._evidence.clear()
        self._last_turn = turn

    def _absorb(self, state: ObservationState) -> None:
        self._opp_in_play = []
        for body in state.them.bodies:
            self._add_body(body)
            self._opp_in_play.append(body.card.card_id)
        for card in state.them.discard:
            self._evidence.add(card.card_id)
        opponent_seat = 1 - state.seat
        for event in state.events:
            fields = dict(event.public_fields)
            if fields.get("playerIndex") == opponent_seat and fields.get("cardId"):
                self._evidence.add(int(fields["cardId"]))

    def _add_body(self, body) -> None:
        self._evidence.add(body.card.card_id)
        self._evidence.update(card.card_id for card in (
            body.energy_cards + body.tools + body.pre_evolution))

    def _observed_intel(self) -> tuple[list[Intel], list[Intel]]:
        """Objective threats/targets from the opponent's board now (`seen=True`)."""
        threats, targets = [], []
        for cid in self._opp_in_play:
            st = self.provider.get(cid) if self.provider else None
            targets.append(Intel(cardId=cid, role=self._target_role(st), seen=True))
            if st and st.maxDamage > 0:
                threats.append(Intel(cardId=cid, role="backup_attacker", seen=True))
        return threats, targets

    @staticmethod
    def _target_role(st) -> str:
        if st and st.is_ex_body:
            return "primary_attacker"
        if st and st.maxDamage > 0:
            return "backup_attacker"
        if st:
            return "support_pokemon"
        return "unknown"

    def _dossier_intel(self, arch: str, key: str) -> list[Intel]:
        """The recognized archetype's dossier ``threats``/``targets`` as Intel — the PREDICTED layer
        (ADR-0027). ``seen`` reflects whether the card is on the board now."""
        entries = (self.artifact.dossiers.get(arch) or {}).get(key) or []
        return [Intel(cardId=e["cardId"], role=e.get("role", "unknown"),
                      seen=e["cardId"] in self._opp_in_play)
                for e in entries if e.get("cardId") is not None]

    @staticmethod
    def _merge_intel(observed: list[Intel], predicted: list[Intel]) -> list[Intel]:
        """Merge observed + predicted Intel by ``cardId`` — the dossier (predicted) role wins."""
        by_id = {i.cardId: i for i in observed}
        for p in predicted:
            by_id[p.cardId] = p
        return list(by_id.values())

    def _confident_archetype(self, top) -> str | None:
        if top and top[0][1] >= self.confidence_threshold:
            return top[0][0]
        return None

    def _expected_cards(self, top, limit: int = 8) -> list[tuple[int, float]]:
        """The confident archetype's Representative-Build cards not yet revealed."""
        arch = self._confident_archetype(top)
        if arch is None:
            return []
        build = (self.artifact.dossiers.get(arch) or {}).get("representative_build") or []
        incl = self.artifact.card_inclusion.get(arch, {})
        ranked, seen = [], set()
        for c in build:
            if c in self._evidence or c in seen:
                continue
            seen.add(c)
            ranked.append((c, incl.get(c, 0.0)))
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:limit]

    def _evolution_paths(self, top) -> list[EvoPath]:
        """Predict each in-play opponent Pokémon's line top (dossier evolution lines)."""
        arch = self._confident_archetype(top)
        if arch is None:
            return []
        lines = (self.artifact.dossiers.get(arch) or {}).get("evolution_lines") or []
        paths = []
        for cid in self._opp_in_play:
            for line in lines:
                if cid in line and line[-1] != cid:
                    paths.append(EvoPath(seen_cardId=cid, line=list(line), top_cardId=line[-1]))
                    break
        return paths

    @staticmethod
    def _confidence(top) -> tuple[float, float]:
        if not top:
            return (0.0, 0.0)
        lead = top[0][1]
        second = top[1][1] if len(top) > 1 else 0.0
        return (lead, lead - second)
