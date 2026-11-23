"""Every guardian brain shares: perceive, change mode, think, act, move.

One turn of a GuardianBrain:
1. Perception turns the battle state into a Percept 
2. The mode (a small state machine written as a `match` statement in each guardian just like the troll we did in class) reacts
   to what was perceived: for example the Knight becomes "afraid" once Ada finds his weakness.
3. Think arbitrates between strategic goals, whose desirability depends on the Percept and
   on the mode, and processes the chosen plan (ai/goals.py): this yields one Intent.
4. A guardian may overrule that intent with a design rule (example the Slime's teaching
   LIMIT). It happens here, in the decision, so the intent, the mode and explain()
   always describe the action the style will write.
5. The plan also gives a Movement order, which the screen turns into steering
   (ai/steering.py).
ai/styles.py then writes the Intent as SQL, and the Intent is thrown away.

REMEMBER: NO MACHINE LEARNING IN THIS HOUSE GIRLS
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ai.base import Intent
from ai.goals import Context, Evaluator, Think
from ai.perception import Perception, Percept, summary
from ai.steering import Movement
from magic.rules import BattleState

REST = Intent("rest", None, "scry")


@dataclass(frozen=True)
class Override:
    """A design rule replacing what Think chose this turn."""
    intent: Intent
    plan: str                    # the plan it stands for, so mode_after() follows what was done
    movement: Movement
    reason: str                  # shown in explain()


class GuardianBrain:
    technique = "goal-driven guardian"
    start_mode = "idle"

    repeat_penalty = 1.0

    def __init__(self, costs: dict[str, int], evaluators: list[Evaluator]):
        self.perception = Perception(costs)
        self.think = Think(evaluators, self.repeat_penalty)
        self.mode = self.start_mode
        self.movement = Movement("hold")
        self.percept: Percept | None = None
        self.turns = 0                                   # its own turns, starting at 1
        self._last: dict = {}

    # what each guardian decides

    def next_mode(self, p: Percept, rng: random.Random) -> str:
        """The state machine: a 'match' on the current mode, guarded by the Percept."""
        return self.mode

    def mode_after(self, plan: str | None, mode: str) -> str:
        """The mode the guardian is in once it has acted (default: unchanged)."""
        return mode

    def overrule(self, intent: Intent, state: BattleState) -> Override | None:
        """A rule that replaces Think's choice this turn (default: none)."""
        return None

    def idle_movement(self) -> Movement:
        """How it moves while it waits for its turn."""
        return Movement("wander", "home")

    def mode_details(self) -> dict:
        return {}

    # the turn

    def decide(self, state: BattleState, rng: random.Random) -> Intent:
        self.turns += 1
        p = self.percept = self.perception.sense(state)
        previous = self.mode
        mode = self.next_mode(p, rng)
        ctx = Context(p, rng)
        intent = self.think.think(ctx, mode) or REST        # nothing possible: rest a turn
        plan, movement = self.think.current_name, ctx.movement
        plan_text = self.think.describe()
        override = self.overrule(intent, state)
        if override is not None:
            ctx.trace.append(f"overruled {intent.action}")
            intent, plan, movement = override.intent, override.plan, override.movement
            self.think.drop()                               # the replaced plan does not resume
        self.mode = self.mode_after(plan, mode)
        self.movement = movement or self.idle_movement()
        self._last = {
            "technique": self.technique,
            "mode": f"{previous} -> {self.mode}",
            **self.mode_details(),
            "sees": summary(p),
            "noticed": "; ".join(self.perception.log) or "nothing new",
            "goals": ", ".join(f"{k} {v:.2f}" for k, v in
                               sorted(self.think.scores.items(), key=lambda kv: -kv[1])),
            "plan": plan_text,
            "steps": " / ".join(ctx.trace),
            "intent": intent.action,
            "movement": f"{self.movement.behaviour} {self.movement.target}",
        }
        if override is not None:
            self._last["overruled"] = override.reason
        return intent

    def explain(self) -> dict:
        return dict(self._last)
