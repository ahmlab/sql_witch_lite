from __future__ import annotations

import math

import pygame

from engine import render


def draw_barracks(canvas: pygame.Surface, t: int, ground_y: int = 60) -> None:
    pygame.draw.rect(canvas, render.INK, (0, 0, 320, ground_y))
    pygame.draw.rect(canvas, render.NIGHT, (0, 8, 320, ground_y - 8))
    for x in range(0, 320, 40):
        pygame.draw.rect(canvas, render.DUSK, (x + 4, 14, 32, ground_y - 14))
        pygame.draw.circle(canvas, render.DUSK, (x + 20, 14), 16)
        pygame.draw.rect(canvas, render.INK, (x + 10, 20, 20, ground_y - 20))
        pygame.draw.circle(canvas, render.INK, (x + 20, 20), 10)
    pygame.draw.rect(canvas, render.BARK, (0, 6, 320, 3))
    for i, x in enumerate(range(8, 320, 14)):
        if (x // 14) % 3 == 1:
            continue
        sway = 1 if (t // 400 + i) % 4 == 0 else 0
        pygame.draw.polygon(canvas, render.SLATE, [(x - 2, 9), (x + 2, 9), (x + sway, 14)])
    for x in (60, 260):
        pygame.draw.rect(canvas, render.CREAM, (x - 1, 30, 3, 8))
        flame = render.GOLD if (t // 130 + x) % 3 else render.BUTTER
        pygame.draw.polygon(canvas, flame, [(x - 2, 30), (x + 3, 30), (x + 1, 25 - (t // 90) % 2)])
    pygame.draw.rect(canvas, render.SLATE, (0, ground_y, 320, 180 - ground_y))
    for y in range(ground_y + 6, 180, 8):
        pygame.draw.line(canvas, render.DUSK, (0, y), (320, y))
        for x in range((y // 8 % 2) * 10, 320, 20):
            pygame.draw.line(canvas, render.DUSK, (x, y - 7), (x, y))


def draw_count(canvas, centre, t, flash, fainted, shielded, moving):
    cx, cy = render.snap(centre[0]), render.snap(centre[1])
    pygame.draw.ellipse(canvas, render.INK, (cx - 13, cy + 16, 26, 5))
    if fainted:
        pygame.draw.rect(canvas, render.WINE, (cx - 16, cy + 11, 32, 6))
        pygame.draw.rect(canvas, render.PARCHMENT, (cx - 4, cy + 10, 8, 4))
        return
    if shielded:
        spin = t / 900
        for i in range(16):
            angle = i / 16 * math.tau + spin
            x = render.snap(cx + math.cos(angle) * 19)
            y = render.snap(cy + 2 + math.sin(angle) * 23)
            colour = render.GOLD if i % 4 == 0 else render.AMBER
            pygame.draw.rect(canvas, colour, (x, y, 1, 2))
    bob = render.snap(math.sin(t / 260))
    if flash:
        cape = lining = coat = skin = gold = render.WHITE
    else:
        cape, lining, coat, skin, gold = render.WINE, render.RED, render.INK, render.PARCHMENT, render.GOLD
    top = cy - 8 + bob
    pygame.draw.polygon(canvas, cape, [(cx - 13, cy + 17), (cx - 7, top), (cx + 7, top), (cx + 13, cy + 17)])
    pygame.draw.polygon(canvas, lining, [(cx - 9, cy + 17), (cx - 5, top + 3), (cx + 5, top + 3), (cx + 9, cy + 17)])
    pygame.draw.rect(canvas, coat, (cx - 5, top + 1, 10, 24 - bob))
    pygame.draw.line(canvas, gold, (cx, top + 3), (cx, cy + 14))
    pygame.draw.polygon(canvas, cape, [(cx - 11, cy - 9 + bob), (cx - 3, cy - 6 + bob), (cx - 7, cy - 18 + bob)])
    pygame.draw.polygon(canvas, cape, [(cx + 11, cy - 9 + bob), (cx + 3, cy - 6 + bob), (cx + 7, cy - 18 + bob)])
    pygame.draw.rect(canvas, skin, (cx - 4, cy - 16 + bob, 8, 9))
    if not flash:
        pygame.draw.rect(canvas, render.INK, (cx - 4, cy - 17 + bob, 8, 3))
        pygame.draw.polygon(canvas, render.INK, [(cx - 1, cy - 14 + bob), (cx + 1, cy - 14 + bob), (cx, cy - 12 + bob)])
        blink = (t // 2600) % 5 == 0 and (t % 2600) < 120
        if not blink:
            pygame.draw.rect(canvas, render.RED, (cx - 3, cy - 12 + bob, 2, 1))
            pygame.draw.rect(canvas, render.RED, (cx + 1, cy - 12 + bob, 2, 1))
        canvas.set_at((cx - 1, cy - 8 + bob), render.WHITE)
        canvas.set_at((cx + 1, cy - 8 + bob), render.WHITE)
        pygame.draw.circle(canvas, gold, (cx, cy - 4 + bob), 1)
    box = pygame.Rect(cx + 7, cy - 1 + bob, 9, 10)
    pygame.draw.rect(canvas, render.BARK if not flash else render.WHITE, box)
    pygame.draw.rect(canvas, render.LEATHER if not flash else render.WHITE, box, 1)
    for row in range(3):
        y = box.y + 2 + row * 3
        pygame.draw.line(canvas, render.SAND, (box.x + 1, y), (box.right - 2, y))
        slide = (t // 400 + row) % 4
        canvas.set_at((box.x + 1 + slide, y), render.GOLD)
        canvas.set_at((box.x + 6, y), render.GOLD)


def draw_bat(canvas: pygame.Surface, pos: tuple[float, float], t: int, phase: float,
             flash: bool = False, state: str = "hover") -> None:
    x, y = render.snap(pos[0]), render.snap(pos[1])
    body = render.WHITE if flash else (render.SLATE if state == "flee" else render.DUSK)
    edge = render.WHITE if flash else render.INK
    speed = 40 if state == "dive" else 70
    up = math.sin(t / speed + phase) > 0
    wing_y = y - 3 if up else y + 1
    pygame.draw.polygon(canvas, edge, [(x - 1, y - 1), (x - 6, wing_y), (x - 4, y + 1)])
    pygame.draw.polygon(canvas, edge, [(x + 1, y - 1), (x + 6, wing_y), (x + 4, y + 1)])
    pygame.draw.rect(canvas, body, (x - 1, y - 2, 3, 4))
    if not flash:
        eye = render.GOLD if state == "dive" else (render.GREY if state == "flee" else render.RED)
        canvas.set_at((x - 1, y - 1), eye)
        canvas.set_at((x + 1, y - 1), eye)


def draw_squad_labels(canvas, counts, quorum, pos=(128, 23)):
    f = render.font()
    y = pos[1]
    for squad in sorted(counts):
        n = counts[squad]
        if not n:
            continue
        colour = render.GOLD if squad in quorum else render.GREY
        f.draw(canvas, f"{squad}: {'|' * n} {n}", (pos[0], y), colour, shadow=render.INK)
        y += 8


def draw_null_void(canvas, t, ground_y=60):
    canvas.fill(render.INK)
    for row, y in enumerate(range(4, ground_y - 4, 10)):
        for col, x in enumerate(range(4 + (row % 2) * 6, 320, 24)):
            if (col * 7 + row * 3 + t // 900) % 13 == 0:
                render.font().draw(canvas, "NULL", (x, y), render.NIGHT)
            elif (col + row) % 3 == 0:
                pygame.draw.rect(canvas, render.NIGHT, (x, y + 1, 16, 5), 1)
    pygame.draw.rect(canvas, render.NIGHT, (0, ground_y, 320, 180 - ground_y))
    for x in range(0, 320, 16):
        pygame.draw.line(canvas, render.DUSK, (x, ground_y), (x, 180))
    pygame.draw.line(canvas, render.VIOLET, (0, ground_y), (320, ground_y))


EYES = {"listening": render.LILAC, "mirroring": render.GOLD, "doubting": render.AQUA,
        "hunting": render.RED, "unravelling": render.GREY}


def noise(a, b):
    return (a * 73856093 ^ b * 19349663) % 97


def null_shape(canvas, cx, cy, colour, fill=None):
    hat = [(cx - 9, cy - 12), (cx + 1, cy - 30), (cx + 10, cy - 12)]
    robe = [(cx - 5, cy - 1), (cx - 12, cy + 17), (cx + 12, cy + 17), (cx + 5, cy - 1)]
    if fill is not None:
        pygame.draw.polygon(canvas, fill, hat)
        pygame.draw.polygon(canvas, fill, robe)
        pygame.draw.ellipse(canvas, fill, (cx - 6, cy - 12, 12, 11))
    pygame.draw.polygon(canvas, colour, hat, 1)
    pygame.draw.line(canvas, colour, (cx - 13, cy - 12), (cx + 14, cy - 12))
    pygame.draw.ellipse(canvas, colour, (cx - 6, cy - 12, 12, 11), 1)
    pygame.draw.polygon(canvas, colour, robe, 1)


def draw_null(canvas, centre, t, flash, fainted, element, veiled, mode="listening"):
    cx, cy = render.snap(centre[0]), render.snap(centre[1])
    if fainted:
        for i in range(10):
            canvas.set_at((cx - 14 + i * 3, cy + 14 + (i % 2)), render.GREY)
        return
    float_y = render.snap(math.sin(t / 420) * 2)
    cy += float_y
    colour = render.WHITE if flash else render.ELEMENT_COLOURS.get(element, render.LILAC)
    pygame.draw.ellipse(canvas, render.NIGHT, (cx - 12, cy + 18 - float_y, 24, 4))
    for i in range(4):
        life = (t / 9 + i * 25) % 100
        x = cx - 10 + (i * 7) % 21
        y = render.snap(cy + 16 - life * 0.35)
        if life < 70:
            pygame.draw.rect(canvas, render.VIOLET if life < 40 else render.DUSK, (x, y, 3, 2), 1)
    glitch = not flash and (t % 1700) < 160
    if glitch:
        null_shape(canvas, cx - 2, cy, render.AQUA)
        null_shape(canvas, cx + 2, cy, render.RED)
    null_shape(canvas, cx, cy, colour, fill=render.INK)
    if not flash:
        step = t // 80
        for i in range(7):
            n = noise(step, i)
            x = cx - 6 + n % 13
            y = cy + 2 + (n // 13) % 14
            if abs(x - cx) * 2 < (y - cy) + 10:
                canvas.set_at((x, y), render.DUSK if i % 2 else render.VIOLET)
        render.font().draw(canvas, "NULL", (cx - 7, cy + 4), render.VIOLET)
        eye = EYES.get(mode, render.LILAC)
        canvas.set_at((cx - 2, cy - 7), eye)
        canvas.set_at((cx + 2, cy - 7), eye)
        if mode in ("mirroring", "hunting"):
            canvas.set_at((cx - 3, cy - 7), eye)
            canvas.set_at((cx + 3, cy - 7), eye)
    if glitch:
        band = cy - 4 + (t // 40) % 12
        pygame.draw.line(canvas, render.FOAM, (cx - 9, band), (cx + 9, band))
    if veiled:
        spin = t / 500
        ring = render.ELEMENT_COLOURS.get(element, render.VIOLET) if element else render.VIOLET
        for i in range(24):
            if (i // 3) % 2:
                continue
            angle = i / 24 * math.tau - spin
            canvas.set_at((render.snap(cx + math.cos(angle) * 19),
                           render.snap(cy + 1 + math.sin(angle) * 24)), ring)
