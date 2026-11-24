"""Fight the Nested Lich many times with simple scripted players to check the balance.

python -m sim.lich_eval            (300 battles per player)
python -m sim.lich_eval --n 50

Same idea as the table in docs/AI.md: the guardian should beat the player who ignores its
lesson and lose to the player who uses it. Turns alternate, the Lich opens the round.
"""

import argparse

from ai.base import RandomBrain
from ai.roster import baseline_brain
from magic.battle import Battle

NAME = "Nested Lich"


def blind_player(battle):
    """Never looks at the Lich: casts the first spell of the book."""
    return "SELECT name FROM spells LIMIT 1"


def hand_player(battle):
    """Looks at his weakness (free) and types the element by hand. No subquery.
    (We peek at battle.state.foe.weakness, that is what her scry would show her.)"""
    ada = battle.state.ada
    weakness = battle.state.foe.weakness
    if ada.hp_ratio < 0.4 and ada.mp >= 6:
        return "SELECT name FROM spells WHERE name = 'Mend'"
    if ada.mp >= 12:
        return f"SELECT name FROM spells WHERE kind = 'attack' AND element = '{weakness}' AND power > 40 LIMIT 1"
    if ada.mp >= 7:
        return f"SELECT name FROM spells WHERE kind = 'attack' AND element = '{weakness}' AND power > 30 LIMIT 1"
    return f"SELECT name FROM spells WHERE kind = 'attack' AND element = '{weakness}' AND power < 20 LIMIT 1"


def subquery_player(battle):
    """One query does the looking and the casting: the strongest spell she can pay for, of
    whatever element the Lich is weak to right now."""
    ada = battle.state.ada
    if ada.hp_ratio < 0.4 and ada.mp >= 6:
        return "SELECT name FROM spells WHERE name = 'Mend'"
    weak = "(SELECT weakness FROM enemies WHERE id = 6)"
    return ("SELECT name FROM spells WHERE kind = 'attack' AND element = " + weak +
            " AND power = (SELECT MAX(power) FROM spells WHERE kind = 'attack' AND element = " +
            weak + " AND mp_cost <= (SELECT mp FROM witch))")


PLAYERS = {"blind": blind_player, "by hand": hand_player, "subquery": subquery_player}


def fight(player, seed, random_lich=False):
    brain = None
    if random_lich:
        # the baseline: a Lich that picks any spell he can pay for
        probe = Battle(seed=seed, guardian="lich")
        brain = baseline_brain("lich", probe.conn)
    battle = Battle(seed=seed, guardian="lich", brain=brain)
    for _ in range(400):
        if battle.whose_turn == "over":
            break
        if battle.whose_turn == "ada":
            battle.ada_cast(player(battle))
        else:
            battle.foe_act()
    return battle


def summarize(n, random_lich):
    rows = []
    for label, player in PLAYERS.items():
        wins, rounds, hp_left = 0, 0, 0
        for seed in range(n):
            battle = fight(player, seed, random_lich)
            if battle.winner == "ada":
                wins += 1
            rounds += battle.state.turn
            hp_left += battle.state.ada.hp
        rows.append((label, 100 * wins / n, rounds / n, hp_left / n))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=300)
    args = parser.parse_args()
    for title, random_lich in (("Nested Lich (real brain)", False),
                               ("Nested Lich (RandomBrain baseline)", True)):
        print(f"\n{title}, {args.n} battles each")
        print(f"{'player':<10} {'Ada wins':>9} {'rounds':>7} {'Ada HP left':>12}")
        for label, wins, rounds, hp in summarize(args.n, random_lich):
            print(f"{label:<10} {wins:>8.0f}% {rounds:>7.1f} {hp:>12.1f}")


if __name__ == "__main__":
    main()
