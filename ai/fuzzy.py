from __future__ import annotations


def triangle(x, left, peak, right):
    if x <= left or x >= right:
        return 1.0 if x == peak else 0.0
    if x <= peak:
        return (x - left) / (peak - left)
    return (right - x) / (right - peak)


def left_shoulder(x, full, zero):
    if x <= full:
        return 1.0
    if x >= zero:
        return 0.0
    return (zero - x) / (zero - full)


def right_shoulder(x, zero, full):
    if x >= full:
        return 1.0
    if x <= zero:
        return 0.0
    return (x - zero) / (full - zero)


class FuzzyVar:
    def __init__(self, name, sets):
        self.name = name
        self.sets = sets

    def fuzzify(self, x):
        return {s: round(f(x), 3) for s, f in self.sets.items()}


class FuzzyRules:

    def __init__(self, inputs, rules, output_values):
        self.inputs = {v.name: v for v in inputs}
        self.rules = rules
        self.output_values = output_values
        self.last = {}

    def run(self, **values):
        degrees = {name: var.fuzzify(values[name]) for name, var in self.inputs.items()}
        out = {s: 0.0 for s in self.output_values}
        for conditions, result in self.rules:
            strength = min(degrees[var][s] for var, s in conditions.items())
            out[result] = max(out[result], strength)
        total = sum(out.values())
        if total == 0:
            answer = sum(self.output_values.values()) / len(self.output_values)
        else:
            answer = sum(out[s] * v for s, v in self.output_values.items()) / total
        self.last = {"inputs": degrees, "output": out, "value": round(answer, 3)}
        return answer
