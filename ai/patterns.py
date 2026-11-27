from __future__ import annotations

import math
from collections import Counter

PLAIN = "plain"
FADE = 0.6
OLD = 0.1
FLOOR = 0.05
SURE = {
    "no tells yet": 0.0,
    "streak 2": 0.6,
    "streak 3": 0.75,
    "streak 4+": 0.85,
    "swing": 0.65,
    "cycle": 0.6,
    "habit": 0.4,
}


def signature(runes):
    return "+".join(sorted(runes)) or PLAIN


def unsure(dist):
    return -sum(p * math.log2(p) for p in dist.values() if p > 0)


def streak(history):
    n = 0
    for t in reversed(history):
        if t != history[-1]:
            break
        n += 1
    return n


def memory(history, old=()):
    w = Counter()
    weight = 1.0
    for t in reversed(history):
        w[t] += weight
        weight *= FADE
    for t in old:
        w[t] += OLD / len(old)
    return w


def spot_tell(history):
    n = streak(history) if history else 0
    match history:
        case []:
            return "no tells yet", None
        case [*_, last] if n >= 4:
            return "streak 4+", last
        case [*_, last] if n == 3:
            return "streak 3", last
        case [*_, a, b, c, d, e, f] if (a, b, c) == (d, e, f) and len({a, b, c}) == 3:
            return "cycle", d
        case [*_, a, b, c, d] if a == c and b == d and a != b:
            return "swing", c
        case [*_, last] if n == 2:
            return "streak 2", last
        case [*_, a, b, c] if a == c and a != b:
            return "swing", b
        case _:
            return "habit", None


def read_tells(history, vocab, old=()):
    rule, guess = spot_tell(history)
    w = memory(history, old)
    if rule == "habit":
        guess = max(w, key=w.get)
    sure = SURE[rule]
    pool = {t: w.get(t, 0.0) + FLOOR for t in set(vocab) | set(w)}
    if guess is None:
        total = sum(pool.values())
        return {t: v / total for t, v in pool.items()}, rule, None
    others = {t: v for t, v in pool.items() if t != guess}
    total = sum(others.values())
    if not others or total <= 0:
        return {guess: 1.0}, rule, guess
    dist = {t: (1 - sure) * v / total for t, v in others.items()}
    dist[guess] = sure
    return dist, rule, guess
