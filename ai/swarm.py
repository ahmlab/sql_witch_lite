from __future__ import annotations

import math
from dataclasses import dataclass, field

from ai.steering import Kinematic, Vec, arrive

NEAR = 22.0
TOO_CLOSE = 7.0
QUORUM = 3
REGROUP_MS = 700

STATE_WEIGHTS = {
    "hover":   (1.8, 0.6, 0.8, 1.2),
    "dive":    (0.8, 1.0, 0.4, 2.0),
    "flee":    (2.6, 0.2, 0.2, 0.7),
    "regroup": (1.2, 0.8, 1.6, 1.8),
}
STATE_SPEED = {"hover": 70, "dive": 120, "flee": 60, "regroup": 95}


@dataclass
class Bat:
    name: str
    squad: str
    body: Kinematic
    phase: float = 0.0
    state: str = "hover"
    timer: int = 0


def next_state(bat, squad_size, biting):
    match bat.state:
        case _ if biting:
            return "dive"
        case "regroup" if bat.timer > 0:
            return "regroup"
        case _ if squad_size < QUORUM:
            return "flee"
        case _:
            return "hover"


@dataclass
class Flock:
    bats: dict = field(default_factory=dict)

    def sync(self, alive, posts, rng):
        names = {name for name, _ in alive}
        for name in list(self.bats):
            if name not in names:
                del self.bats[name]
        for name, squad in alive:
            if name in self.bats:
                bat = self.bats[name]
                if bat.squad != squad:
                    bat.squad = squad
                    bat.state = "regroup"
                    bat.timer = REGROUP_MS
                continue
            post = posts.get(squad, Vec())
            start = post + Vec(rng.uniform(-6, 6), rng.uniform(-4, 4))
            self.bats[name] = Bat(name, squad, Kinematic(start, max_speed=70, max_accel=260),
                                  rng.uniform(0, math.tau))

    def neighbours(self, bat):
        return [b for b in self.bats.values() if b is not bat and b.squad == bat.squad
                and (b.body.position - bat.body.position).length() < NEAR]

    def steer(self, bat, target):
        me = bat.body
        near = self.neighbours(bat)
        sep = align = coh = Vec()
        if near:
            for other in near:
                away = me.position - other.body.position
                d = away.length()
                if d < TOO_CLOSE:
                    sep = sep + away.normalized() * (1 - d / TOO_CLOSE)
            n = len(near)
            avg_vel = Vec(sum(b.body.velocity.x for b in near) / n,
                          sum(b.body.velocity.y for b in near) / n)
            align = avg_vel - me.velocity
            centre = Vec(sum(b.body.position.x for b in near) / n,
                         sum(b.body.position.y for b in near) / n)
            coh = centre - me.position
        ws, wa, wc, wh = STATE_WEIGHTS[bat.state]
        home = arrive(me, target, slow_radius=18.0)
        return (sep.normalized() * me.max_accel * ws
                + align.truncated(me.max_accel) * wa
                + coh.normalized() * me.max_accel * 0.3 * wc
                + home * wh)

    def update(self, posts, dt, t_ms, biting=False, count_pos=None):
        sizes = {}
        for bat in self.bats.values():
            sizes[bat.squad] = sizes.get(bat.squad, 0) + 1
        for bat in self.bats.values():
            bat.timer = max(0, bat.timer - int(dt * 1000))
            bat.state = next_state(bat, sizes[bat.squad], biting)
            bat.body.max_speed = STATE_SPEED[bat.state]
            post = posts.get(bat.squad, Vec())
            wobble = Vec(math.cos(t_ms / 420 + bat.phase) * 6, math.sin(t_ms / 300 + bat.phase) * 3)
            if bat.state == "flee" and count_pos is not None:
                out = (post - count_pos).normalized() * 14
                wobble = wobble * 2.2 + out
            bat.body.integrate(self.steer(bat, post + wobble), dt)


def squad_posts(squads, centre, biting, ada):
    posts = {}
    for i, squad in enumerate(sorted(squads)):
        angle = math.pi * (0.85 + 0.45 * i)
        spot = centre + Vec(math.cos(angle) * 24, math.sin(angle) * 10 - 8)
        if biting:
            spot = spot + (ada - spot) * 0.55
        posts[squad] = spot
    return posts
