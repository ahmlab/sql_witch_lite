"""Goal behaviour

- An AtomicGoal is one action: it emits one Intent (and a movement) when processed.
- A CompositeGoal is a plan: a stack of subgoals processed front first, over several turns.

STATUS: atomic and composite goals

This pill is hard to swallow and to be honest is too much for the current gameplay that we have
however in order to create bosses that can really feel different we need a smart goal behaviour

"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from ai.base import Intent
from ai.perception import Percept
from ai.steering import Movement

COMMITMENT = 1.25            # a new plan must beat the current one by 25% to replace it
NOISE = (0.85, 1.15)         # for more naturality each desirability is multiplied by a random factor in this range 


class Status(Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Context:
    """What one turn of goal processing reads and writes."""
    percept: Percept
    rng: random.Random
    intent: Intent | None = None
    movement: Movement | None = None
    trace: list[str] = field(default_factory=list)

    def emit(self, intent: Intent, movement: Movement | None = None) -> None:
        self.intent = intent
        if movement is not None:
            self.movement = movement


class Goal:
    name = "goal"

    def __init__(self):
        self.status = Status.INACTIVE

    def activate(self, ctx: Context) -> None:
        self.status = Status.ACTIVE

    def process(self, ctx: Context) -> Status:
        raise NotImplementedError

    def terminate(self, ctx: Context) -> None:
        pass

    def step(self, ctx: Context) -> Status:
        """Run the goal through its life cycle once."""
        match self.status:
            case Status.INACTIVE:
                self.activate(ctx)
            case Status.COMPLETED | Status.FAILED:
                return self.status
        if self.status is Status.ACTIVE:              # activate() sometimes fail we need to check it
            self.status = self.process(ctx)
        match self.status:
            case Status.COMPLETED | Status.FAILED:
                self.terminate(ctx)
        return self.status

    def describe(self) -> str:
        return f"{self.name}[{self.status.value}]"


class AtomicGoal(Goal):
    """One action. It fails at once if the Percept says it cannot be done for example if you have no MP."""

    def __init__(self, name: str, intent: Intent | None = None,
                 movement: Movement | None = None,
                 requires: Callable[[Percept], bool] = lambda p: True):
        super().__init__()
        self.name, self.intent, self.movement, self.requires = name, intent, movement, requires

    def activate(self, ctx: Context) -> None:
        self.status = Status.ACTIVE if self.requires(ctx.percept) else Status.FAILED

    def process(self, ctx: Context) -> Status:
        if self.intent is not None:
            ctx.emit(self.intent, self.movement)
        elif self.movement is not None:
            ctx.movement = self.movement               # a pure reposition costs no turn
        ctx.trace.append(f"do {self.name}")
        return Status.COMPLETED


class CompositeGoal(Goal):
    """A plan: subgoals done front first. If one fails, the whole plan fails (and Think
    picks another), which is how a guardian reacts when the situation changes mid plan."""

    def __init__(self, name: str, subgoals: list[Goal]):
        super().__init__()
        self.name, self.subgoals = name, list(subgoals)

    def process(self, ctx: Context) -> Status:
        while self.subgoals:
            current = self.subgoals[0]
            match current.step(ctx):
                case Status.COMPLETED:
                    self.subgoals.pop(0)
                    if ctx.intent is not None:             # the turn's action is chosen
                        return Status.ACTIVE if self.subgoals else Status.COMPLETED
                case Status.FAILED:
                    ctx.trace.append(f"{self.name}: {current.name} failed")
                    return Status.FAILED
                case _:
                    return Status.ACTIVE
        return Status.COMPLETED

    def describe(self) -> str:
        inner = " > ".join(g.describe() for g in self.subgoals)
        return f"{self.name}[{self.status.value}]" + (f" ({inner})" if inner else "")


@dataclass
class Evaluator:
    """Scores one strategic goal and knows how to build its plan."""
    name: str
    desirability: Callable[[Percept, str], float]      
    plan: Callable[[Percept], Goal]


class Think(Goal):
    """The top level goal: arbitration, then the chosen plan."""
    name = "think"

    def __init__(self, evaluators: list[Evaluator], repeat_penalty: float = 1.0):
        super().__init__()
        if not evaluators:
            raise ValueError("Think needs at least one evaluator")
        names = [e.name for e in evaluators]
        if len(set(names)) != len(names):
            raise ValueError(f"evaluator names must be unique: {names}")
        self.evaluators = evaluators
        self.current: Goal | None = None
        self.current_name: str | None = None
        self.scores: dict[str, float] = {}
        # Diminishing returns: each back to back restart of the same plan multiplies its
        # score by repeat_penalty once more (1.0 = no penalty).
        self.repeat_penalty = repeat_penalty
        self.last_plan: str | None = None
        self.repeats = 0

    def arbitrate(self, ctx: Context, mode: str, blocked: frozenset[str] = frozenset()) -> None:
        """Score every strategic goal; keep the current plan unless another clearly wins.
        Leaves no plan (current is None) when every goal is blocked or scores 0."""
        low, high = NOISE
        current_ok = (self.current is not None and self.current.status is Status.ACTIVE
                      and self.current_name not in blocked)
        self.scores = {}
        candidates = []
        for e in self.evaluators:
            score = 0.0 if e.name in blocked else \
                max(0.0, e.desirability(ctx.percept, mode)) * ctx.rng.uniform(low, high)
            if e.name == self.last_plan and not current_ok:
                score *= self.repeat_penalty ** self.repeats
            self.scores[e.name] = round(score, 3)
            if e.name not in blocked and score > 0:      # unrounded: tiny scores still count
                candidates.append(e.name)
        if not candidates:
            ctx.trace.append("no goal left to try")
            self.drop()
            return
        best = max(candidates, key=self.scores.get)
        if current_ok and self.scores[best] < self.scores[self.current_name] * COMMITMENT:
            ctx.trace.append(f"keep {self.current_name}")
            return
        evaluator = next(e for e in self.evaluators if e.name == best)
        self.current, self.current_name = evaluator.plan(ctx.percept), best
        self.repeats = self.repeats + 1 if best == self.last_plan else 1
        self.last_plan = best
        ctx.trace.append(f"new plan: {best}")

    def think(self, ctx: Context, mode: str, max_replans: int | None = None) -> Intent | None:
        """One turn: arbitrate, process the plan, and replan if it ends without acting.
        By default every goal gets its chance"""
        self.status = Status.ACTIVE
        blocked: set[str] = set()
        attempts = len(self.evaluators) if max_replans is None else max_replans
        for _ in range(attempts):
            self.arbitrate(ctx, mode, frozenset(blocked))
            if self.current is None:
                break
            self.current.step(ctx)
            if ctx.intent is not None:
                return ctx.intent
            # The plan failed (or finished) without acting: set it aside for this turn.
            ctx.trace.append(f"drop {self.current_name} this turn")
            blocked.add(self.current_name)
            self.drop()
        return None

    def drop(self) -> None:
        """Abandon the current plan (it will not resume next turn)."""
        self.current = self.current_name = None

    def describe(self) -> str:
        return self.current.describe() if self.current else "(no plan)"
