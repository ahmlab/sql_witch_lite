"""The Nested Lich (second guardian after the Knight, it teaches SUBQUERY)

I copied knight.py and changed it, like the team lead said :)

Mechanic: the Lich hides inside layers (shells). His element changes every round
(Shadow, Frost or Fire), so his weakness changes too. He also has two layers of defence:
the Veil of Layers (a Ward of Relevance) and the Bone Ward. Every spell he casts is a query
with another query inside it (a subquery), so his very first cast is the Invitation
that teaches SUBQUERY.

Techniques (no machine learning!):
- Perception (ai/perception.py): he sees both HP bars, his MP and his wards, he knows what
  he can afford and he remembers Ada's casts (how much she hurts him, if she hit his weakness).

- Stance, a state machine written with match/case: lurking, pressing, besieged, desperate,
  winded.

- Goal-driven behaviour: Think scores six goals:
      execute       finish a weak Ada with Soul Rend
      nest          go home and build the layers: Veil of Layers, then Bone Ward
                    (a plan inside a plan, that is why he is "nested")
      siphon        heal himself with Life Siphon when he is hurt
      press         close in and strike twice
      bone          just put the Bone Ward up again
      catch_breath  wait and get MP back

- Steering (ai/steering.py): he floats to the front to attack, goes back home to build his
  layers, and keeps his distance (evade) when Ada found his weakness.

STATUS: perception, stance switch, six goal plans, steering orders, shell shifting.
"""

import random

from ai.base import Intent
from ai.goals import AtomicGoal, CompositeGoal, Evaluator
from ai.guardian import GuardianBrain
from ai.steering import Movement

# Each action casts exactly one spell of the Lich (data/foe_spells.csv, foe_id 4).
ACTION_SPELLS = {
    "strike": "Bone Dart", "heavy": "Grave Chill", "finisher": "Soul Rend",
    "veil": "Veil of Layers", "bone": "Bone Ward", "siphon": "Life Siphon",
}
DEFAULT_COSTS = {"strike": 3, "heavy": 6, "finisher": 10, "veil": 6, "bone": 5, "siphon": 8}
LICH_INTENTS = {
    "strike": Intent("strike", "Ada", "attack"),
    "heavy": Intent("heavy", "Ada", "attack"),
    "finisher": Intent("finisher", "Ada", "attack"),
    "veil": Intent("veil", None, "relevance"),
    "bone": Intent("bone", None, "ward"),
    "siphon": Intent("siphon", None, "heal"),
    "rest": Intent("rest", None, "scry"),
}

# The shells: (element, weakness). They only use pairs that exist in the type chart.
SHELLS = [("Shadow", "Light"), ("Frost", "Fire"), ("Fire", "Tide")]

FINISH_BELOW = 0.35        # Ada's HP ratio under which he goes for the kill
DESPERATE_BELOW = 0.3      # his own HP ratio under which he is desperate
PRESS_BELOW = 0.6          # Ada's HP ratio under which he presses
HURT_BELOW = 0.6           # his own HP ratio under which he wants to heal
RECOVERED_MP = 14          # a winded lich waits for this much MP


def lich_legal_intents(state, costs=None):
    """What he can do right now (used by the RandomBrain baseline). Resting is free,
    everything else needs the MP of its spell."""
    if costs is None:
        costs = DEFAULT_COSTS
    options = []
    for action, intent in LICH_INTENTS.items():
        if action == "rest":
            options.append(intent)
        elif action in costs and costs[action] <= state.foe.mp:
            options.append(intent)
    return options


def shift_shell(state, conn, rng):
    """Called at the end of every round (ai/roster.py -> magic/battle.py).
    The Lich puts on a new shell: a different element and a different weakness.
    The enemies table must say the same, or queries would read old facts."""
    options = []
    for shell in SHELLS:
        if shell[0] != state.foe.element:
            options.append(shell)
    element, weakness = rng.choice(options)
    state.foe.element = element
    state.foe.weakness = weakness
    conn.execute("UPDATE enemies SET element = ?, weakness = ? WHERE id = ?",
                 (element, weakness, state.foe_id))


# how much each stance likes each goal (1.0 = neutral)
STANCE_BIAS = {
    "lurking":   {"nest": 1.0, "press": 1.0},
    "pressing":  {"press": 1.3, "execute": 1.2, "bone": 0.7},
    "besieged":  {"nest": 0.7, "bone": 1.5, "siphon": 1.4, "press": 1.1},
    "desperate": {"execute": 1.3, "siphon": 1.5, "press": 1.1, "nest": 0.7},
    "winded":    {"catch_breath": 2.0, "press": 0.6},
}


def _bias(goal, mode):
    if mode in STANCE_BIAS and goal in STANCE_BIAS[mode]:
        return STANCE_BIAS[mode][goal]
    return 1.0


# desirabilities (how much he wants each goal right now, 0 = not at all)

def _execute(p, mode):
    if p.ada_hp_ratio >= FINISH_BELOW or not p.can("finisher"):
        return 0.0
    return 1.5 * _bias("execute", mode)


def _nest(p, mode):
    # Perception: if Ada already hits his weakness the veil is worth less, because
    # super-effective spells go through the veil anyway.
    if p.my_relevance or not p.can("veil"):
        return 0.0
    return 1.3 * (1 - 0.8 * p.weakness_known) * _bias("nest", mode)


def _siphon(p, mode):
    if p.my_hp_ratio >= HURT_BELOW or not p.can("siphon"):
        return 0.0
    return (0.6 + (1 - p.my_hp_ratio)) * _bias("siphon", mode)


def _press(p, mode):
    if not p.can("strike"):
        return 0.0
    return (0.7 + 0.5 * (1 - p.ada_hp_ratio)) * _bias("press", mode)


def _bone(p, mode):
    if not p.can("bone") or p.my_ward >= 5:
        return 0.0
    return (0.35 + 3 * p.threat) * _bias("bone", mode)


def _catch_breath(p, mode):
    score = 0.15 * _bias("catch_breath", mode)
    if not p.can("strike"):
        score = score + 0.6
    return score


# plans (each one is a goal made of smaller goals)

def _act(action, movement):
    # an action goal can only run if he can pay for the spell (resting is always possible)
    def can_do(p):
        return action == "rest" or p.can(action)
    return AtomicGoal(action, LICH_INTENTS[action], movement, requires=can_do)


def _move(name, behaviour, target):
    return AtomicGoal(name, movement=Movement(behaviour, target))


def _plan_execute(p):
    return CompositeGoal("execute", [_move("hunt", "pursue", "ada"),
                                     _act("finisher", Movement("pursue", "ada"))])


def _plan_nest(p):
    # A plan inside a plan: "layers" is itself a plan with two spells.
    layers = CompositeGoal("layers", [_act("veil", Movement("arrive", "home")),
                                      _act("bone", Movement("arrive", "home"))])
    return CompositeGoal("nest", [_move("float home", "arrive", "home"), layers])


def _plan_siphon(p):
    return CompositeGoal("siphon", [_move("back off", "evade", "ada"),
                                    _act("siphon", Movement("evade", "ada"))])


def _plan_press(p):
    # Grave Chill first if he can pay for it and still strike next turn, if not two strikes
    first = "strike"
    if p.can_afford("heavy", "strike"):
        first = "heavy"
    return CompositeGoal("press", [_move("float closer", "arrive", "front"),
                                   _act(first, Movement("arrive", "front")),
                                   _act("strike", Movement("arrive", "front"))])


def _plan_bone(p):
    return CompositeGoal("bone", [_move("to the crypt", "arrive", "home"),
                                  _act("bone", Movement("arrive", "home"))])


def _plan_catch_breath(p):
    return CompositeGoal("catch_breath", [_move("drift", "wander", "home"),
                                          _act("rest", Movement("wander", "home"))])


EVALUATORS = [
    Evaluator("execute", _execute, _plan_execute),
    Evaluator("nest", _nest, _plan_nest),
    Evaluator("siphon", _siphon, _plan_siphon),
    Evaluator("press", _press, _plan_press),
    Evaluator("bone", _bone, _plan_bone),
    Evaluator("catch_breath", _catch_breath, _plan_catch_breath),
]


class LichBrain(GuardianBrain):
    technique = "goal-driven behaviour + stance switch (Buckland ch. 9)"
    start_mode = "lurking"
    repeat_penalty = 0.55          # so he does not do the same trick forever

    def __init__(self, costs=None):
        if costs is None:
            costs = dict(DEFAULT_COSTS)
        super().__init__(costs, EVALUATORS)

    def next_mode(self, p, rng):
        match self.mode:
            case _ if p.my_hp_ratio < DESPERATE_BELOW:
                return "desperate"                     # nothing to lose
            case _ if not p.can("strike"):
                return "winded"                        # no MP
            case "winded" if p.my_mp < RECOVERED_MP:
                return "winded"                        # wait until he has some MP
            case "lurking" | "winded" | "pressing" | "desperate" if p.weakness_known > 0.5:
                return "besieged"                      # Ada found his weakness
            case "lurking" | "winded" | "desperate" if p.ada_hp_ratio < PRESS_BELOW:
                return "pressing"                      # she is weak: attack
            case "pressing" if p.ada_hp_ratio >= PRESS_BELOW:
                return "lurking"                       # she is fine again
            case "besieged" if p.weakness_known <= 0.3 and p.my_relevance:
                return "lurking"                       # the veil is up and she stopped
            case "winded" | "desperate":
                return "lurking"
            case mode:
                return mode

    def idle_movement(self):
        match self.mode:
            case "pressing" | "desperate":
                return Movement("arrive", "front")
            case "besieged":
                return Movement("evade", "ada")
            case _:
                return Movement("wander", "home")      # floats around his crypt
