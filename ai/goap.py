from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Act:
    name: str
    move: str
    needs: tuple
    gives: tuple
    cost: float


@dataclass
class Plan:
    steps: list = field(default_factory=list)
    cost: float = math.inf
    searched: int = 0
    goal: str = ""

    @property
    def found(self):
        return self.cost < math.inf

    @property
    def first(self):
        return self.steps[0].move if self.steps else None

    def line(self):
        if not self.found:
            return f"{self.goal}: no plan ({self.searched} states searched)"
        path = " > ".join(s.name for s in self.steps) or "already there"
        return f"{self.goal}: {path} (cost {self.cost:.1f}, {self.searched} states searched)"


def holds(world, pairs):
    return all(world.get(k, False) == v for k, v in pairs)


def price(act, world):
    cost = act.cost(world) if callable(act.cost) else act.cost
    return max(1.0, cost)


def plan(start, goal, acts, goal_name="", max_steps=4):
    want = tuple(goal.items())
    def guess(world):
        return 0.0 if holds(world, want) else 1.0

    tie = itertools.count()
    key = frozenset(start.items())
    heap = [(guess(start), next(tie), 0.0, key, [])]
    best = {key: 0.0}
    searched = 0
    while heap:
        _, _, spent, key, path = heapq.heappop(heap)
        if spent > best.get(key, math.inf):
            continue
        world = dict(key)
        searched += 1
        if holds(world, want):
            return Plan(path, spent, searched, goal_name)
        if len(path) >= max_steps:
            continue
        for a in acts:
            if not holds(world, a.needs):
                continue
            nxt = {**world, **dict(a.gives)}
            nkey = frozenset(nxt.items())
            cost = spent + price(a, world)
            if cost < best.get(nkey, math.inf) - 1e-9:
                best[nkey] = cost
                heapq.heappush(heap, (cost + guess(nxt), next(tie), cost, nkey, path + [a]))
    return Plan([], math.inf, searched, goal_name)
