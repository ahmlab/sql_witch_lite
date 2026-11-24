"""The Twin Archivists, Quill and Ink: one joint brain for two bodies (design doc 5.6).

Mechanic: two foes bound by a key. They share one spell book and one mana pool. If one twin
falls, the other restores it, so both must be hit in the SAME query; their weaknesses re-roll
every round (ai/pair.py). Only a JOIN puts the right target name in each row, so JOIN is the
rune Ada learns from their very first query: they JOIN to find their target too.

Techniques, all rule-based (no learning), the same loop as the Knight (ai/guardian.py):
- Perception (PairPerception): HP of each twin, who has fallen, who is weaker, whether Ada
  knows JOIN and whether her last cast hit both twins at once, a pair-wide threat estimate and
  the shared mana pool.
- State machine, a `match` statement: bonded, pressed, bereaved, desperate, winded. The mode
  colours their priorities.
- Goal-driven behaviour (Buckland ch. 9): Think scores seven goals from the Percept and the mode
  and runs the winner as a plan. The goals are joint moves, one intent for each twin:
      restore   the living twin gets the fallen one back up (the most important goal)
      mend      heal the wounded twin before it can fall
      guard     put a ward on the weaker twin
      volley    both twins cast at Ada
      barrage   the big spell plus a small one, to finish Ada
      strike    one twin casts at Ada (when only one is alive, or mana is short)
      rest      read their own rows and regain mana
  A plan that becomes impossible fails and Think replans, as for the Knight.
- Steering (ai/steering.py, ai/pair.py): the healthier twin leads, the other shadows it
  (pursue); the weaker twin retreats (evade) to be guarded or mended; the living twin walks to
  the fallen one to restore it (arrive); both wander while they rest.
Never imports pygame.

STATUS: perception, mode machine, seven goals, a movement order for each twin.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, fields

from ai.base import Intent
from ai.goals import AtomicGoal, CompositeGoal, Evaluator, Goal
from ai.guardian import GuardianBrain
from ai.perception import THREAT_SMOOTHING, Perception, Percept
from ai.steering import Movement
from magic.rules import BattleState

# Each action casts these spells (data/foe_spells.csv, foe_id 4), one row per spell.
ACTION_SPELLS = {
    "strike": ["Index Slash"],
    "volley": ["Index Slash", "Paper Cut"],
    "barrage": ["Footnote Barrage", "Paper Cut"],
    "restore": ["Restore Index"],
    "mend": ["Restore Index"],
    "guard": ["Binding Seal"],
}
DEFAULT_COSTS = {"strike": 5, "volley": 8, "barrage": 11, "restore": 8, "mend": 8, "guard": 5}

DESPERATE_BELOW = 0.3         # the pair's combined HP ratio under which they are desperate
MEND_BELOW = 0.55             # a living twin under this ratio is worth healing
FINISH_BELOW = 0.55           # Ada under this ratio: the big spell is worth its mana


def intents_for(state=None) -> dict[str, Intent]:
    return {
        "strike": Intent("strike", "Ada", "attack"),
        "volley": Intent("volley", "Ada", "attack"),
        "barrage": Intent("barrage", "Ada", "attack"),
        "rest": Intent("rest", None, "scry"),
    }


BASE_INTENTS = intents_for()


def twin_legal_intents(state: BattleState) -> list[Intent]:
    """Everything the pair may ever do. RandomBrain samples uniformly from this list."""
    legal = list(BASE_INTENTS.values())
    for who in ("quill", "ink"):
        legal += [Intent("mend", who, "restore"), Intent("guard", who, "ward"),
                  Intent("restore", who, "restore")]
    return legal


# ------------------------------------------------------------------ perception

@dataclass(frozen=True)
class PairPercept(Percept):
    quill_ratio: float = 1.0
    ink_ratio: float = 1.0
    down: int = 0                        # how many twins have fallen
    fallen: str | None = None            # "quill" / "ink": the one to restore
    lead: str = "quill"                  # the healthier living twin
    partner: str | None = "ink"          # the other one (may be the fallen twin)
    weaker: str | None = None            # the living twin with less HP (None if only one lives)
    gap: float = 0.0                     # how lopsided their HP is
    ada_hits_both: bool = False          # her last cast hit both twins
    ada_knows_join: bool = False
    fresh_unison: float = 0.0            # fades from 1.0 after she hits both


@dataclass
class PairPerception(Perception):
    pair_seen: int = 0
    pair_threat: float = 0.0
    last_both_turn: int | None = None

    def sense(self, state: BattleState) -> PairPercept:
        base = super().sense(state)
        q, i = state.foe, state.twin
        total = q.max_hp + i.max_hp
        names = {state.foe.name, state.twin.name}
        for cast in state.ada_casts[self.pair_seen:]:
            if cast.scry:
                continue
            self.pair_threat = (THREAT_SMOOTHING * cast.damage / total
                                + (1 - THREAT_SMOOTHING) * self.pair_threat)
            if names <= set(cast.targets):
                self.last_both_turn = cast.turn
                self.log.append(f"turn {cast.turn}: she hit BOTH of us in one query")
        self.pair_seen = len(state.ada_casts)
        last = next((c for c in reversed(state.ada_casts) if not c.scry), None)

        alive = [(who, c) for who, c in (("quill", q), ("ink", i)) if c.alive]
        fallen = next((who for who, c in (("quill", q), ("ink", i)) if not c.alive), None)
        lead = max(alive, key=lambda wc: wc[1].hp_ratio)[0] if alive else "quill"
        partner = "ink" if lead == "quill" else "quill"
        weaker = (min(alive, key=lambda wc: wc[1].hp_ratio)[0] if len(alive) == 2 else None)
        age = None if self.last_both_turn is None else state.turn - self.last_both_turn

        values = {f.name: getattr(base, f.name) for f in fields(Percept)}
        values.update(
            my_hp_ratio=(q.hp + i.hp) / total, my_ward=q.ward + i.ward,
            threat=round(self.pair_threat, 3),
            quill_ratio=q.hp_ratio, ink_ratio=i.hp_ratio,
            down=2 - len(alive), fallen=fallen, lead=lead, partner=partner, weaker=weaker,
            gap=abs(q.hp_ratio - i.hp_ratio),
            ada_hits_both=bool(last and names <= set(last.targets)),
            ada_knows_join="JOIN" in state.ada.runes,
            fresh_unison=0.0 if age is None else max(0.0, 1.0 - age / 3),
        )
        return PairPercept(**values)


# ------------------------------------------------------------------ desirabilities

BIAS = {   # how each mode colours each goal (1.0 = neutral)
    "bonded":    {"volley": 1.2, "guard": 0.8},
    "pressed":   {"guard": 1.7, "mend": 1.4, "volley": 0.9},
    "bereaved":  {"restore": 1.4, "strike": 1.2},
    "desperate": {"barrage": 1.4, "guard": 1.2, "mend": 1.2},
    "winded":    {"rest": 2.0, "volley": 0.6},
}


def _bias(goal: str, mode: str) -> float:
    return BIAS.get(mode, {}).get(goal, 1.0)


def _restore(p: PairPercept, mode: str) -> float:
    if p.fallen is None or not p.can("restore"):
        return 0.0
    return 2.2 * _bias("restore", mode)


def _mend(p: PairPercept, mode: str) -> float:
    if p.down or p.weaker is None or not p.can("mend"):
        return 0.0
    ratio = min(p.quill_ratio, p.ink_ratio)
    if ratio >= MEND_BELOW:
        return 0.0
    return (0.6 + 2.0 * (MEND_BELOW - ratio)) * _bias("mend", mode)


def _guard(p: PairPercept, mode: str) -> float:
    if p.weaker is None or not p.can("guard") or p.my_ward >= 8:
        return 0.0
    # Perception: if she can hit both at once, standing walls matter more than another volley.
    return (0.3 + 2.5 * p.threat + 0.6 * p.fresh_unison) * _bias("guard", mode)


def _volley(p: PairPercept, mode: str) -> float:
    if p.down or not p.can("volley"):
        return 0.0
    return (0.9 + 0.5 * (1 - p.ada_hp_ratio)) * _bias("volley", mode)


def _barrage(p: PairPercept, mode: str) -> float:
    if p.down or not p.can("barrage") or p.ada_hp_ratio >= FINISH_BELOW:
        return 0.0
    return (1.2 + (FINISH_BELOW - p.ada_hp_ratio)) * _bias("barrage", mode)


def _strike(p: PairPercept, mode: str) -> float:
    if not p.can("strike"):
        return 0.0
    base = 0.85 if p.down else 0.45          # alone, or short of mana for a volley
    return base * _bias("strike", mode)


def _rest(p: PairPercept, mode: str) -> float:
    return 0.15 * _bias("rest", mode) + (0.7 if not p.can("strike") else 0.0)


# ------------------------------------------------------------------ plans

def _move(name: str, behaviour: str, target: str) -> AtomicGoal:
    return AtomicGoal(name, movement=Movement(behaviour, target))


def _act(name: str, intent: Intent, movement: Movement, need: str | None) -> AtomicGoal:
    return AtomicGoal(name, intent, movement,
                      requires=lambda p, n=need: n is None or p.can(n))


def _plan_restore(p: PairPercept) -> Goal:
    walk = Movement("arrive", "partner")                  # the living twin goes to the fallen one
    return CompositeGoal("restore", [_move("go to the fallen twin", "arrive", "partner"),
                                     _act("restore", Intent("restore", p.fallen, "restore"),
                                          walk, "restore")])


def _plan_mend(p: PairPercept) -> Goal:
    walk = Movement("arrive", "partner")
    return CompositeGoal("mend", [_move("go to the wounded twin", "arrive", "partner"),
                                  _act("mend", Intent("mend", p.weaker, "restore"), walk, "mend")])


def _plan_guard(p: PairPercept) -> Goal:
    stand = Movement("arrive", "front")
    return CompositeGoal("guard", [_move("cover the weaker twin", "arrive", "front"),
                                   _act("guard", Intent("guard", p.weaker, "ward"), stand,
                                        "guard")])


def _plan_attack(action: str):
    def plan(p: PairPercept) -> Goal:
        return CompositeGoal(action, [_move("take position", "arrive", "front"),
                                      _act(action, BASE_INTENTS[action],
                                           Movement("arrive", "front"), action)])
    return plan


def _plan_rest(p: PairPercept) -> Goal:
    return CompositeGoal("rest", [_move("drift home", "wander", "home"),
                                  _act("rest", BASE_INTENTS["rest"], Movement("wander", "home"),
                                       None)])


EVALUATORS = [
    Evaluator("restore", _restore, _plan_restore),
    Evaluator("mend", _mend, _plan_mend),
    Evaluator("guard", _guard, _plan_guard),
    Evaluator("volley", _volley, _plan_attack("volley")),
    Evaluator("barrage", _barrage, _plan_attack("barrage")),
    Evaluator("strike", _strike, _plan_attack("strike")),
    Evaluator("rest", _rest, _plan_rest),
]

# What the OTHER twin does while the lead carries out a plan (the lead's order is the plan's own).
PARTNER_ORDER = {
    "restore": Movement("hold"),                      # the fallen twin lies where it fell
    "mend": Movement("hold"),
    "guard": Movement("evade", "ada"),                # the guarded twin keeps its distance
    "volley": Movement("pursue", "partner"),          # shadows the leader
    "barrage": Movement("pursue", "partner"),
    "strike": Movement("pursue", "partner"),
    "rest": Movement("wander", "home"),
}


class PairBrain(GuardianBrain):
    technique = "joint goals + mode machine (Buckland ch. 9)"
    start_mode = "bonded"
    repeat_penalty = 0.6                   # they vary their tactics

    def __init__(self, costs: dict[str, int] | None = None):
        super().__init__(costs or dict(DEFAULT_COSTS), EVALUATORS)
        self.perception = PairPerception(costs or dict(DEFAULT_COSTS))
        self.movements: dict[str, Movement] = {}
        self._twins = ""

    def next_mode(self, p: PairPercept, rng: random.Random) -> str:
        """The mode machine. Order matters: the first matching case wins."""
        match self.mode:
            case _ if p.my_hp_ratio < DESPERATE_BELOW:
                return "desperate"                       # nothing left to protect
            case _ if p.down:
                return "bereaved"                        # one of us has fallen
            case _ if not p.can("strike"):
                return "winded"                          # not even one blade's worth of mana
            case "winded" if p.my_mp < 10:
                return "winded"                          # wait until a volley is affordable
            case _ if p.ada_hits_both or p.fresh_unison > 0.5:
                return "pressed"                         # she found the way to hit us both
            case "pressed" if p.fresh_unison > 0:
                return "pressed"
            case _:
                return "bonded"

    def idle_movement(self) -> Movement:
        return Movement("wander", "home")

    def decide(self, state: BattleState, rng: random.Random) -> Intent:
        intent = super().decide(state, rng)
        p = self.percept
        plan = self.think.current_name
        lead_order = self.movement
        partner_order = PARTNER_ORDER.get(plan, Movement("wander", "home"))
        self.movements = {p.lead: lead_order}
        if p.partner is not None:
            self.movements[p.partner] = Movement("hold") if p.fallen == p.partner else partner_order
        self._twins = (f"Quill {p.quill_ratio:.0%} / Ink {p.ink_ratio:.0%}, "
                       f"fallen: {p.fallen or 'none'}, lead: {p.lead}")
        self._last["twins"] = self._twins
        self._last["movement"] = ", ".join(
            f"{who} {m.behaviour} {m.target}" for who, m in self.movements.items())
        return intent

    def mode_details(self) -> dict:
        return {"twins": self._twins} if self._twins else {}
