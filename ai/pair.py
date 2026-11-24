"""The Twin Archivists' world: two bodies bound by a key (design doc 5.6).

What this file owns (everything else about the fight lives in the normal casting contract):
- the second combatant (Archivist Ink) and the link between the two twins;
- PROCEDURAL GENERATION: at the start of every round each twin is dealt a new element, and a new
  weakness is drawn for it from the two elements that really beat it in the type chart. The two
  weaknesses are always different, so one JOIN gives one spell per twin. A seeded generator of its
  own is used, so the same seed deals the same elements and the battle's own rolls are untouched;
- STEERING on screen: each twin has a Kinematic body on a small field, moved by its plan's
  Movement (arrive, pursue, evade, wander, hold) plus a separation push so the pair never merge;
- the mirror of the twins in the `enemies` table, so Ada can SELECT their names and weaknesses.
Movement is only for show: no damage roll or decision reads a position. Never imports pygame.

STATUS: second combatant, weakness re-roll, restore link, steering bodies, ASCII stage.
"""

from __future__ import annotations

import random

from ai import steering
from ai.steering import Kinematic, Movement, Vec, WanderState
from magic.rules import BattleState, Combatant

NATURAL = ("Fire", "Tide", "Nature", "Storm", "Earth", "Frost", "Wind")   # the elements dealt
FIELD_W, FIELD_H = 150.0, 40.0              # pixels: the little stage the twins move on
ADA_AT = Vec(14.0, 20.0)
HOMES = {"quill": Vec(132.0, 11.0), "ink": Vec(132.0, 29.0)}    # where each twin waits
FRONTS = {"quill": Vec(54.0, 13.0), "ink": Vec(54.0, 27.0)}     # where each twin strikes from
STEPS, DT = 40, 0.05                        # two seconds of steering per turn
APART = 14.0                                # twins push each other away inside this distance
STAGE_COLS = 48

NAMES = ("quill", "ink")


def attackers_x2(element: str, chart: dict) -> list[str]:
    """The natural elements whose spells hit `element` for x2 (the candidates for its weakness)."""
    return [a for a in NATURAL if chart.get((a, element), 1.0) >= 2.0]


class Pair:
    def __init__(self, seed: int):
        self.rng = random.Random(seed * 1_000_003 + 5)     # dealing: never the battle's own rng
        self.visual = random.Random(seed * 7919 + 11)      # wandering: for show only
        self.history: list[dict] = []                      # what was dealt, round by round
        self.twin_id: int | None = None
        self.bodies: dict[str, Kinematic] = {
            n: Kinematic(HOMES[n], max_speed=70.0, max_accel=260.0) for n in NAMES}
        self.ada = Kinematic(ADA_AT)
        self._wander = {n: WanderState() for n in NAMES}

    # ------------------------------------------------------------ setting up

    def attach(self, conn, state: BattleState, chart: dict) -> None:
        """Build the second combatant from its row in `enemies` and deal the first elements."""
        row = conn.execute("SELECT id, name, hp, max_hp, element, weakness, speed FROM enemies "
                           "WHERE id != ? ORDER BY id", (state.foe_id,)).fetchone()
        self.twin_id, name, hp, max_hp, element, weakness, speed = row
        # mp 0 on purpose: both twins draw on the first one's pool (the key that binds them).
        state.twin = Combatant(name, hp, max_hp, 0, 0, 0, speed, element, weakness)
        state.twin.runes = set(state.foe.runes)
        self.reroll(state, chart)
        self.sync(conn, state)

    def members(self, state: BattleState) -> dict[str, Combatant]:
        return {"quill": state.foe, "ink": state.twin}

    # ------------------------------------------------------------ procedural generation

    def reroll(self, state: BattleState, chart: dict) -> None:
        """Deal each twin an element and a weakness that really beats it. The weaknesses differ."""
        first, second = self.rng.sample(NATURAL, 2)
        options_a, options_b = attackers_x2(first, chart), attackers_x2(second, chart)
        for _ in range(50):
            weak_a, weak_b = self.rng.choice(options_a), self.rng.choice(options_b)
            if weak_a != weak_b:
                break
        else:                                               # cannot happen on the natural wheel
            weak_a, weak_b = options_a[0], next(w for w in options_b if w != options_a[0])
        state.foe.element, state.foe.weakness = first, weak_a
        state.twin.element, state.twin.weakness = second, weak_b
        self.history.append({"round": state.turn, "quill": (first, weak_a),
                             "ink": (second, weak_b)})

    def end_of_round(self, state: BattleState, chart: dict) -> None:
        self.reroll(state, chart)

    # ------------------------------------------------------------ the tables

    def sync(self, conn, state: BattleState) -> None:
        """Mirror both twins into `enemies` (hp, shared mp, this round's element and weakness)."""
        for who, row_id in (("quill", state.foe_id), ("ink", self.twin_id)):
            c = self.members(state)[who]
            conn.execute("UPDATE enemies SET hp = ?, mp = ?, element = ?, weakness = ? "
                         "WHERE id = ?", (c.hp, state.foe.mp, c.element, c.weakness, row_id))

    # ------------------------------------------------------------ steering

    def places(self, who: str) -> dict[str, Kinematic]:
        other = self.bodies["ink" if who == "quill" else "quill"]
        return {"ada": self.ada, "partner": other,
                "home": Kinematic(HOMES[who]), "front": Kinematic(FRONTS[who])}

    def obey(self, movements: dict[str, Movement] | None) -> None:
        """Walk both bodies for one turn. A body whose twin has fallen stays where it dropped."""
        if not movements:
            return
        for _ in range(STEPS):
            for who in NAMES:
                body, order = self.bodies[who], movements.get(who, Movement("hold"))
                accel = steering.steer(order, body, self.places(who), self._wander[who],
                                       self.visual)
                accel = accel + self._separation(who)
                body.integrate(accel, DT)
                body.position = Vec(min(max(body.position.x, 4.0), FIELD_W - 4.0),
                                    min(max(body.position.y, 4.0), FIELD_H - 4.0))

    def _separation(self, who: str) -> Vec:
        """Reynolds' separation: the twins are a pair, not one body."""
        me, other = self.bodies[who], self.bodies["ink" if who == "quill" else "quill"]
        away = me.position - other.position
        distance = away.length()
        if 0 < distance < APART:
            return away.normalized() * (me.max_accel * (APART - distance) / APART)
        return Vec()

    def settle(self, state: BattleState) -> None:
        """A fallen twin stops where it dropped (called by the brain's hold order too)."""
        for who, c in self.members(state).items():
            if not c.alive:
                self.bodies[who].velocity = Vec()

    # ------------------------------------------------------------ the terminal's view

    def distance(self, a: str, b: str) -> float:
        pa = self.ada if a == "ada" else self.bodies[a]
        pb = self.ada if b == "ada" else self.bodies[b]
        return (pa.position - pb.position).length()

    def render(self, state: BattleState) -> list[str]:
        """A one-line stage: A is Ada, Q and I the twins (x when fallen)."""
        cells = ["."] * STAGE_COLS

        def put(position: Vec, char: str) -> None:
            col = min(STAGE_COLS - 1, max(0, int(position.x / FIELD_W * STAGE_COLS)))
            while cells[col] != "." and col < STAGE_COLS - 1:
                col += 1
            cells[col] = char

        put(self.ada.position, "A")
        for who, char in (("quill", "Q"), ("ink", "I")):
            alive = self.members(state)[who].alive
            put(self.bodies[who].position, char if alive else "x")
        return ["  " + "".join(cells),
                f"  A Ada   Q {state.foe.name}   I {state.twin.name}   x fallen twin"]


def make_pair(seed: int) -> Pair:
    return Pair(seed)
