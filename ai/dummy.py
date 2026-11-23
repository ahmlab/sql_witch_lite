"""The Training Dummy is the tutorial boss
"""

from __future__ import annotations

import random

from ai.base import Intent
from magic.rules import BattleState

STAND = Intent("stand", None, "scry")
DUMMY_LOOK = "SELECT name, hp FROM enemies"     # no runes: see the module docstring


class DummyBrain:
    """No perception, no goals, no randomness: it never touches the battle's rng."""

    def decide(self, state: BattleState, rng: random.Random) -> Intent:
        return STAND

    def explain(self) -> dict:
        return {"technique": "none: a training dummy", "intent": STAND.action}


def render_dummy(intent: Intent, state: BattleState, turn: int) -> str:
    return DUMMY_LOOK
