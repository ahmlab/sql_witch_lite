"""
Brain constructor.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol

from magic.rules import BattleState

# Every kind a foe intent can have. Scry is when you try to see in the future
KINDS = frozenset({"attack", "heal", "ward", "relevance", "dispel", "scry", "restore"})


@dataclass(frozen=True)
class Intent:
    """A smal description of an action"""
    action: str                  # what the brain wants, in its own words
    target: str | None = None    # combatant name the intent is aimed at, if any
    kind: str = "attack"         # one of KINDS
    params: Mapping[str, Any] = field(default_factory=dict, compare=True, hash=False)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown intent kind {self.kind!r}; expected one of {sorted(KINDS)}")
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))

# This is how we are gonna build our brains
class Brain(Protocol):
    """Every foe AI has this shape, so any brain can be paired with any style."""

    def decide(self, state: BattleState, rng: random.Random) -> Intent:
        ...

    def explain(self) -> dict:
        """The reasoning behind the last decision, for the F1 overlay and the report."""
        ...


class RandomBrain:
    """This is a random brain, witches used it to do experiments and learn about the boss possible behaviors"""

    def __init__(self, legal_intents: Callable[[BattleState], list[Intent]]):
        self.legal_intents = legal_intents
        self._last: dict = {}

    def decide(self, state: BattleState, rng: random.Random) -> Intent:
        options = self.legal_intents(state)
        if not options:
            # Every foe has a free action (a look, a rest), so an empty list is a bug in
            # legal_intents, not a situation to paper over.
            raise ValueError("RandomBrain: legal_intents returned no options")
        choice = rng.choice(options)
        self._last = {"technique": "uniform random (baseline)",
                      "choices": [i.action for i in options],
                      "probability": 1 / len(options),
                      "picked": choice.action}
        return choice

    def explain(self) -> dict:
        return dict(self._last)
