"""Evaluate the Twin Archivists with scripted players: python -m sim.twin_eval --n 300

Same method as the other guardians (docs/AI.md, design doc 9.1): each scripted player is a
different level of understanding of the lesson, the brain is compared with a RandomBrain
baseline, and everything is seeded so the table can be reproduced.

- novice:  never learns. Casts her strongest spell, with no target in the row.
- aimer:   copies WHERE and ORDER BY and aims at one twin's weakness. Without JOIN a spell
           has no target name, so it lands on the first twin only: the other one restores it.
- joiner:  uses the twins' own trick: one JOIN puts each twin's weakness spell and name in a row.
"""

from __future__ import annotations

import argparse
import math
import statistics
import time
from collections import Counter

from ai.archivists import twin_legal_intents
from ai.base import RandomBrain
from magic.battle import Battle
from magic.guard import Miscast

JOIN_CHEAP = ("SELECT s.name, e.name FROM spells AS s JOIN enemies AS e "
              "ON s.element = e.weakness WHERE s.kind = 'attack' AND s.mp_cost <= {cost}")
STRONG = "SELECT name FROM spells WHERE kind = 'attack' ORDER BY power DESC LIMIT 1"
HEAL = ("SELECT name FROM spells WHERE kind = 'heal' AND mp_cost <= {mp} "
        "ORDER BY power DESC LIMIT 1")
AIMED = ("SELECT name FROM spells WHERE kind = 'attack' AND element = '{weak}' "
         "AND mp_cost <= {mp} ORDER BY power DESC LIMIT 1")


def novice(battle: Battle) -> str:
    return STRONG


def aimer(battle: Battle) -> str:
    state = battle.state
    if state.ada.hp_ratio < 0.35 and state.ada.mp >= 8:
        return HEAL.format(mp=state.ada.mp)
    target = state.foe if state.foe.alive else state.twin
    return AIMED.format(weak=target.weakness, mp=state.ada.mp)


def joiner(battle: Battle) -> str:
    state = battle.state
    if state.ada.hp_ratio < 0.35 and state.ada.mp >= 8:
        return HEAL.format(mp=state.ada.mp)
    return JOIN_CHEAP.format(cost=3)


PLAYERS = {"novice": novice, "aimer": aimer, "joiner": joiner}


def fight(seed: int, player, brain_factory=None, max_rounds: int = 40) -> dict:
    battle = Battle(seed=seed, guardian="twins")
    if brain_factory is not None:
        battle.brain = brain_factory()
    actions, decision_ms = [], []
    dealt = casting = restores = 0
    while battle.whose_turn != "over" and battle.state.turn <= max_rounds:
        if battle.whose_turn == "ada":
            try:
                battle.ada_cast(player(battle))
            except Miscast:
                for _ in range(4):                       # a free look, then she moves on
                    battle.ada_cast("SELECT name FROM enemies")
        else:
            start = time.perf_counter()
            turn = battle.foe_act()
            decision_ms.append((time.perf_counter() - start) * 1000)
            actions.append(turn.reasoning.get("intent") or turn.reasoning.get("picked", "?"))
            dealt += sum(c.damage for c in turn.report.casts if c.target == battle.state.ada.name)
            casting += bool(turn.report.casts)
            restores += any(c.kind == "restore" and c.amount for c in turn.report.casts)
    return {"win": battle.winner == "ada", "rounds": battle.state.turn,
            "ada_hp": battle.state.ada.hp, "actions": actions, "ms": decision_ms,
            "dealt": dealt, "casting": casting, "restores": restores}


def entropy(actions: list[str]) -> float:
    counts = Counter(actions)
    total = sum(counts.values())
    return -sum(c / total * math.log2(c / total) for c in counts.values())


def summarize(label: str, runs: list[dict]) -> None:
    wins = sum(r["win"] for r in runs)
    pooled = [a for r in runs for a in r["actions"]]
    sequences = {tuple(r["actions"][:8]) for r in runs[:100]}
    ms = [m for r in runs for m in r["ms"]]
    turns = sum(len(r["actions"]) for r in runs)
    print(f"{label:<34} win {100 * wins / len(runs):5.1f}%  rounds {statistics.mean(r['rounds'] for r in runs):5.1f}"
          f"  Ada HP left {statistics.mean(r['ada_hp'] for r in runs):5.1f}"
          f"  entropy {entropy(pooled):4.2f} bits  distinct openings {len(sequences):3d}"
          f"  decision {statistics.mean(ms):5.2f} ms")
    print(f"{'':<34} damage to Ada per twin turn {sum(r['dealt'] for r in runs) / turns:5.1f}"
          f"   turns that cast {100 * sum(r['casting'] for r in runs) / turns:4.0f}%"
          f"   restores per battle {statistics.mean(r['restores'] for r in runs):4.2f}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the Twin Archivists.")
    parser.add_argument("--n", type=int, default=300, help="battles per row")
    parser.add_argument("--seed", type=int, default=1, help="first seed")
    args = parser.parse_args(argv)
    seeds = range(args.seed, args.seed + args.n)
    print(f"Twin Archivists, {args.n} seeded battles per row (Ada level 4, 105 HP)\n")
    for name, player in PLAYERS.items():
        summarize(f"{name} vs PairBrain", [fight(s, player) for s in seeds])
    baseline = lambda: RandomBrain(twin_legal_intents)
    print()
    summarize("joiner vs RandomBrain (baseline)", [fight(s, joiner, baseline) for s in seeds])
    summarize("aimer vs RandomBrain (baseline)", [fight(s, aimer, baseline) for s in seeds])
    summarize("novice vs RandomBrain (baseline)", [fight(s, novice, baseline) for s in seeds])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
