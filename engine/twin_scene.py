"""The Twin Archivists on screen: the Archive backdrop, two scholars bound by a golden key, and a
battle scene that knows there are two of them.

TwinScene is a BattleScene (engine/scenes.py) with a second foe: its own HP bar, its own flash and
bolt target, the restore beat (a fallen twin gets up again), and one steering body for each twin,
moved by the movement orders the pair's brain planned (ai/archivists.py). The golden chain between
them is the key that binds them: it glows when one restores the other.
Everything here is looks only. No rule reads a position or a colour.

STATUS: archive backdrop, Quill and Ink sprites, two HP panels, restore beat, two steering bodies.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pygame

from ai import steering
from ai.steering import Kinematic, Movement, Vec, WanderState
from engine import render
from engine.grimoire import draw_foe_book
from engine.scenes import (ADA_AT, ADA_BODY, ADA_FEET, ARENA, BattleScene, Popup, draw_ada)
from magic.cast import CastReport

NAMES = ("quill", "ink")
HOMES = {"quill": (256, 40), "ink": (284, 47)}          # where each twin waits (screen pixels)
FRONTS = {"quill": (200, 42), "ink": (212, 53)}         # where each twin strikes from
APART = 22.0                                            # the twins push each other apart inside this
ROBES = {"quill": (render.NAVY, render.SKY), "ink": (render.WINE, render.PEACH)}


# ------------------------------------------------------------------ the Archive

def draw_archive(canvas: pygame.Surface, t: int, ground_y: int = 60) -> None:
    """A library at night: shelves of coloured spines, a round window, floating candles."""
    pygame.draw.rect(canvas, render.NIGHT, (0, 0, 320, ground_y))
    pygame.draw.rect(canvas, render.DUSK, (0, 0, 320, 6))
    spines = (render.WINE, render.NAVY, render.FOREST, render.AMBER, render.VIOLET,
              render.TEAL, render.RUST, render.LEATHER)
    for shelf_x in (4, 82, 160, 238):                                  # four bookcases
        case = pygame.Rect(shelf_x, 8, 76, ground_y - 8)
        pygame.draw.rect(canvas, render.BARK, case)
        for row in range(3):
            top = case.y + 3 + row * 15
            pygame.draw.rect(canvas, render.INK, (case.x + 3, top, case.w - 6, 12))
            x = case.x + 4
            index = shelf_x + row * 7
            while x < case.right - 8:
                width = 2 + (index * 5) % 3
                height = 8 + (index * 3) % 4
                pygame.draw.rect(canvas, spines[(index * 7) % len(spines)],
                                 (x, top + 12 - height, width, height))
                x += width + 1
                index += 1
            pygame.draw.line(canvas, render.LEATHER, (case.x + 3, top + 12),
                             (case.right - 4, top + 12))
    for x, phase in ((76, 0), (154, 400), (232, 800), (310, 1200)):    # floating candles
        bob = round(math.sin((t + phase) / 500) * 2)
        pygame.draw.rect(canvas, render.CREAM, (x - 1, 22 + bob, 3, 7))
        flame = render.BUTTER if (t // 130 + x) % 3 else render.GOLD
        pygame.draw.polygon(canvas, flame, [(x - 2, 22 + bob), (x + 2, 22 + bob),
                                            (x, 16 + bob - (t // 110 + x) % 2)])
    pygame.draw.rect(canvas, render.LEATHER, (0, ground_y, 320, 180 - ground_y))      # floor
    for y in range(ground_y + 5, 180, 7):
        pygame.draw.line(canvas, render.BARK, (0, y), (320, y))
        for x in range((y // 7 % 2) * 14, 320, 28):
            pygame.draw.line(canvas, render.BARK, (x, y - 6), (x, y))
    pygame.draw.rect(canvas, render.RUST, (170, ground_y + 3, 140, 5))                # a rug


# ------------------------------------------------------------------ the twins

def draw_twin(canvas: pygame.Surface, centre: tuple[float, float], t: int, flash: bool,
              fainted: bool, who: str, moving: bool, element) -> None:
    """Quill (blue robe, a feather pen) or Ink (wine robe, an inkwell). An orb over the head
    shows the element they were dealt this round."""
    cx, cy = render.snap(centre[0]), render.snap(centre[1])
    robe, skin = ROBES[who]
    pygame.draw.ellipse(canvas, render.SLATE, (cx - 11, cy + 15, 22, 5))             # shadow
    if fainted:
        pygame.draw.polygon(canvas, robe, [(cx - 16, cy + 17), (cx + 14, cy + 17),
                                           (cx + 10, cy + 9), (cx - 12, cy + 9)])
        pygame.draw.circle(canvas, skin, (cx - 14, cy + 11), 4)                       # head
        pygame.draw.rect(canvas, render.GOLD, (cx - 16, cy + 16, 30, 1))
        for i, mark in enumerate("zZ"[: 1 + (t // 600) % 2]):                         # out cold
            render.font().draw(canvas, mark, (cx - 10 + i * 5, cy - 2 - i * 4), render.LILAC)
        return
    bob = 1 if moving and (t // 140) % 2 else 0
    cloth = render.WHITE if flash else robe
    trim = render.WHITE if flash else render.GOLD
    face = render.WHITE if flash else skin
    pygame.draw.polygon(canvas, cloth, [(cx - 9, cy + 17), (cx + 9, cy + 17),
                                        (cx + 5, cy - 6 - bob), (cx - 5, cy - 6 - bob)])
    pygame.draw.line(canvas, trim, (cx - 9, cy + 16), (cx + 9, cy + 16))             # hem
    pygame.draw.line(canvas, trim, (cx - 5, cy + 2), (cx + 5, cy + 2))               # belt
    pygame.draw.circle(canvas, face, (cx, cy - 10 - bob), 5)                         # head
    pygame.draw.polygon(canvas, cloth, [(cx - 6, cy - 12 - bob), (cx + 6, cy - 12 - bob),
                                        (cx, cy - 20 - bob)])                         # a cap
    pygame.draw.line(canvas, trim, (cx - 6, cy - 12 - bob), (cx + 6, cy - 12 - bob))
    if not flash:
        for x in (cx - 3, cx + 2):                                                    # eyes
            canvas.set_at((x, cy - 10 - bob), render.INK)
        pygame.draw.rect(canvas, render.INK, (cx - 4, cy - 11 - bob, 4, 3), 1)        # spectacles
        pygame.draw.rect(canvas, render.INK, (cx + 1, cy - 11 - bob, 4, 3), 1)
    if who == "quill":
        pygame.draw.line(canvas, render.WHITE, (cx - 11, cy + 4), (cx - 15, cy - 12))  # feather pen
        pygame.draw.polygon(canvas, render.CREAM, [(cx - 15, cy - 12), (cx - 18, cy - 4),
                                                   (cx - 13, cy - 6)])
    else:
        pygame.draw.rect(canvas, render.INK, (cx - 15, cy + 2, 6, 7))                 # inkwell
        pygame.draw.rect(canvas, render.SLATE, (cx - 14, cy, 4, 2))
        pygame.draw.rect(canvas, render.LILAC, (cx - 14, cy + 4, 4, 2))
    colour = render.ELEMENT_COLOURS.get(element, render.GREY)
    glow = 2 + (t // 300) % 2
    pygame.draw.circle(canvas, render.INK, (cx, cy - 27 - bob), glow + 2)             # element orb
    pygame.draw.circle(canvas, colour, (cx, cy - 27 - bob), glow)


def draw_key_chain(canvas: pygame.Surface, a: tuple[int, int], b: tuple[int, int], t: int,
                   linked: bool, pulse: int) -> None:
    """The golden chain that binds the twins. It sags between them, goes grey and dashed when
    one has fallen, and flares while one restores the other."""
    (ax, ay), (bx, by) = (a[0], a[1] - 2), (b[0], b[1] - 2)
    steps = 12
    lit = pulse > 0
    for i in range(steps):
        if not linked and i % 2:
            continue
        u = i / (steps - 1)
        x = render.snap(ax + (bx - ax) * u)
        y = render.snap(ay + (by - ay) * u + math.sin(u * math.pi) * 6)
        colour = (render.BUTTER if (i + t // 90) % 3 == 0 else render.GOLD) if linked \
            else render.GREY
        if lit and abs((i / steps) - (1 - pulse / 900)) < 0.2:
            colour = render.WHITE
        canvas.set_at((x, y), colour)
        canvas.set_at((x, y + 1), render.AMBER if linked else render.SLATE)
    mid_x, mid_y = (ax + bx) // 2, (ay + by) // 2 + 6
    pygame.draw.rect(canvas, render.GOLD if linked else render.GREY, (mid_x - 2, mid_y - 2, 5, 5))
    pygame.draw.rect(canvas, render.INK, (mid_x - 2, mid_y - 2, 5, 5), 1)               # the key


# ------------------------------------------------------------------ the scene

class TwinScene(BattleScene):
    INK_PANEL = pygame.Rect(128, 3, 120, 20)

    def __init__(self, game, guardian: str = "twins", battle=None):
        super().__init__(game, guardian, battle)
        state = self.battle.state
        self.shown["twin"] = [state.twin.hp, 0]
        self.bars["twin"] = [float(state.twin.hp), 0.0]
        self.flash["twin"] = 0
        self.bodies = {n: Kinematic(Vec(*HOMES[n]), max_speed=55 if n == "quill" else 50,
                                    max_accel=200.0) for n in NAMES}
        self.orders = {n: Movement("wander", "home") for n in NAMES}
        self.wanders = {n: WanderState() for n in NAMES}
        self.pulse = 0                                  # ms left of the restore glow on the chain
        self.shown_elements = (state.foe.element, state.twin.element)

    # ------------------------------------------------------------ who is who

    def side_of(self, name: str) -> str:
        state = self.battle.state
        if name == state.ada.name:
            return "ada"
        return "twin" if name == state.twin.name else "foe"

    def twin_xy(self, side: str) -> tuple[int, int]:
        body = self.bodies["ink" if side == "twin" else "quill"]
        return render.snap(body.position.x), render.snap(body.position.y)

    def foe_xy(self) -> tuple[int, int]:
        return self.twin_xy("foe")

    def _hit(self, side: str, damage: int, crit: bool, spell: str = ""):
        def effect():
            ada_hand = (ADA_AT[0] + 22, ADA_AT[1] + 2)
            there = ada_hand if side == "ada" else self.twin_xy(side)
            here = self.twin_xy("foe") if side == "ada" else ada_hand
            self.fx.bolt(here, there, render.ELEMENT_COLOURS.get(self._element_of(spell),
                                                                  render.LILAC))
            self.shown[side][0] = max(0, self.shown[side][0] - damage)
            self.flash[side] = 160
            x, y = (ADA_AT[0] + 18, ADA_AT[1] - 6) if side == "ada" else \
                (there[0], there[1] - 24)
            self.popups.append(Popup(str(damage), (x, y), render.GOLD if crit else render.WHITE))
            if crit:
                self.game.shake()
        return effect

    # ------------------------------------------------------------ the restore beat

    def _restored(self, side: str, amount: int):
        def effect():
            self.shown[side][0] += amount
            x, y = self.twin_xy(side)
            self.fx.burst(x, y, count=18, speed=60,
                          colours=(render.GOLD, render.BUTTER, render.WHITE))
            self.pulse = 900
        return effect

    def narrate(self, report: CastReport) -> None:
        """Everything the base scene tells, plus a twin getting back up. Events keep their order."""
        chunk: list[tuple] = []
        for event in report.events:
            if event[0] != "restore":
                chunk.append(event)
                continue
            if chunk:
                super().narrate(replace(report, events=chunk))
                chunk = []
            _, _, spell, target, amount, revived = event
            who = target.split()[-1]
            words = f"{who} gets back up" if revived else f"{who} is healed"
            self.say(f"{spell}: {words} (+{amount})", 1000,
                     self._restored(self.side_of(target), amount), "hp_up")
        if chunk:
            super().narrate(replace(report, events=chunk))

    def _sync_shown(self) -> None:
        super()._sync_shown()
        state = self.battle.state
        self.shown["twin"] = [state.twin.hp, 0]
        self.shown_elements = (state.foe.element, state.twin.element)

    def _tell_round_end(self) -> None:
        before = set(self.rounds_told)
        super()._tell_round_end()
        if set(self.rounds_told) != before:                     # a round just ended: new deal
            self.say("The twins' elements are dealt again.", 800, self._shuffle_orbs, "scry")

    def _shuffle_orbs(self) -> None:
        state = self.battle.state
        self.shown_elements = (state.foe.element, state.twin.element)
        for side in ("foe", "twin"):
            x, y = self.twin_xy(side)
            self.fx.burst(x, y - 27, count=8, speed=40,
                          colours=(render.LILAC, render.WHITE, render.GOLD))

    # ------------------------------------------------------------ turns

    def foe_turn(self) -> None:
        turn = self.battle.foe_act()
        self.foe_sql, self.foe_report, self.reasoning = turn.sql, turn.report, turn.reasoning
        movements = getattr(self.battle.brain, "movements", None)
        if movements:
            self.orders = {n: movements.get(n, Movement("wander", "home")) for n in NAMES}
        if turn.movement is not None:
            self.order = turn.movement
        self.say("The twins cast!", 650, None, "scry" if turn.report.scry else "cast")
        self.narrate(turn.report)
        if turn.invitation:
            rune = turn.invitation

            def learn():
                self.editor.unlocked.add(rune)
                self.glow = (rune, self.time)
            self.say(f"{rune} glows in their book!", 1200, learn, "invitation")
            self.say(f"Ada copies the rune: {rune}", 1200)
        self._tell_round_end()

    # ------------------------------------------------------------ moving

    def _places(self, who: str) -> dict[str, Kinematic]:
        other = self.bodies["ink" if who == "quill" else "quill"]
        return {"home": Kinematic(Vec(*HOMES[who])), "front": Kinematic(Vec(*FRONTS[who])),
                "ada": Kinematic(Vec(*ADA_BODY)), "partner": other}

    def _update_body(self, dt: int) -> None:
        idle = Movement("wander", "home")
        for who in NAMES:
            body = self.bodies[who]
            order = idle if self.phase == "input" else self.orders.get(who, idle)
            accel = steering.steer(order, body, self._places(who), self.wanders[who],
                                   self.game.vfx)
            other = self.bodies["ink" if who == "quill" else "quill"]
            away = body.position - other.position
            if 0 < away.length() < APART:                       # separation: a pair, not a blob
                accel = accel + away.normalized() * (body.max_accel * (APART - away.length())
                                                     / APART)
            body.integrate(accel, dt / 1000)
            p = body.position
            x, y = min(max(p.x, ARENA.left), ARENA.right), min(max(p.y, ARENA.top), ARENA.bottom)
            if (x, y) != (p.x, p.y):
                body.position, body.velocity = Vec(x, y), Vec()
        self.body = self.bodies["quill"]
        self.pulse = max(0, self.pulse - dt)

    def _update_visuals(self, dt: int) -> None:
        for side in ("ada", "foe", "twin"):
            self.flash[side] = max(0, self.flash[side] - dt)
            for slot in (0, 1):
                target, current = self.shown[side][slot], self.bars[side][slot]
                step = 60 * dt / 1000
                self.bars[side][slot] = target if abs(target - current) <= step else \
                    current + step * (1 if target > current else -1)
        for popup in self.popups:
            popup.age += dt
        self.popups = [p for p in self.popups if p.age < 800]

    # ------------------------------------------------------------ drawing

    def draw(self, canvas):
        state = self.battle.state
        draw_archive(canvas, self.time)
        flashing = lambda side: self.flash[side] > 0 and (self.time // 40) % 2 == 0
        order = sorted(("foe", "twin"), key=lambda s: self.twin_xy(s)[1])     # lower is in front
        both_up = state.foe.alive and state.twin.alive
        draw_key_chain(canvas, self.twin_xy("foe"), self.twin_xy("twin"), self.time,
                       both_up and self.bars["foe"][0] > 0 and self.bars["twin"][0] > 0,
                       self.pulse)
        for side in order:
            who = "quill" if side == "foe" else "ink"
            body = self.bodies[who]
            element = self.shown_elements[0 if side == "foe" else 1]
            draw_twin(canvas, self.twin_xy(side), self.time, flashing(side),
                      self.bars[side][0] <= 0, who, body.velocity.length() > 5, element)
        draw_ada(canvas, ADA_FEET, self.flash["ada"] > 0 and (self.time // 40) % 2 == 0)

        self._draw_foe_panel(canvas)
        glow_word = self.glow[0] if self.glow and self.time - self.glow[1] < 4000 else None
        draw_foe_book(canvas, "Archivist Twins", self.foe_sql, self.foe_report, glow_word,
                      self.time)
        self._draw_ada_panel(canvas)
        self._draw_narration(canvas)
        self.grimoire.draw(canvas, self.time, focused=self.phase == "input")
        self._draw_page_heat(canvas)
        self.fx.draw(canvas)
        self._draw_guide_button(canvas)
        self._draw_tables_button(canvas)
        if self.tables_open:
            self._draw_tables(canvas)
        if self.game.debug:
            self._draw_debug(canvas)
        self.guide.draw(canvas, self.time)

    def _draw_foe_panel(self, canvas):
        """Two panels, one for each twin. The mana pool is shared, so it is shown once."""
        f, state = render.font(), self.battle.state
        for side, combatant, box in (("foe", state.foe, self.FOE_PANEL),
                                     ("twin", state.twin, self.INK_PANEL)):
            box = pygame.Rect(box)
            render.panel(canvas, box)
            f.draw(canvas, combatant.name.split()[-1].upper(), (box.x + 4, box.y + 3), render.INK)
            f.draw(canvas, "HP", (box.x + 4, box.y + 11), render.AMBER)
            hp = round(self.bars[side][0])
            render.meter(canvas, pygame.Rect(box.x + 14, box.y + 11, 100, 5), hp,
                         combatant.max_hp, render.hp_colour(hp, combatant.max_hp))
            if side == "foe":
                mp = round(self.bars["foe"][1])
                f.draw(canvas, f"SHARED MP {mp}/{combatant.max_mp}", (box.x + 42, box.y + 3),
                       render.NAVY)
            elif hp <= 0:
                f.draw(canvas, "FALLEN", (box.x + 42, box.y + 3), render.RED)
        if state.foe.exhausted:
            f.draw(canvas, "EXHAUSTED", (self.INK_PANEL.right + 4, 6), render.RED,
                   shadow=render.INK)

