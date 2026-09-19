"""A volcano with a lava fountain in its crater and lava running down its sides.

A jagged cone of basalt and blackstone, steep near the top, with a lake of
lava in the crater. Out of the lake rises a column of lava: each block of it
sits on lava, so it can't fall and spills sideways instead, then drops back
into the lake. Two streams pour over the rim and down the slopes.

There's nothing that burns anywhere near it: the ground round the foot is
bare stone, wide enough that lava reaching the bottom stops on it.

Front faces the player. Coordinates: u right, v up (0 = feet level), w
forward (0 = front of the build). See lib/build.py.
"""

import math
import random

HEIGHT = 34        # the rim
BASE = 22          # radius at the foot
TOP = 9            # radius of the flat-topped rim
CRATER = 5         # radius of the lava lake inside it
LAKE = 4           # how deep the lake is
FOUNTAIN = 9       # how far the fountain rises above the rim
APRON = 6          # bare stone round the foot
CENTER = APRON + BASE + 1

ROCK = (["blackstone"] * 8 + ["basalt"] * 5 + ["tuff"] * 4
        + ["cobbled_deepslate"] * 2 + ["magma"])


def _height(d, wobble):
    """How tall the cone stands at distance d from the middle."""
    d *= wobble
    if d <= TOP:
        return HEIGHT
    if d >= BASE:
        return -1
    t = (BASE - d) / (BASE - TOP)
    return round(HEIGHT * t ** 1.7)   # steeper towards the top, like a real one


def _cone(s, rng):
    a, b = rng.uniform(0, 2 * math.pi), rng.uniform(0, 2 * math.pi)
    heights = {}
    for u in range(-BASE - 2, BASE + 3):
        for w in range(-BASE - 2, BASE + 3):
            d = math.hypot(u, w)
            angle = math.atan2(w, u)
            wobble = 1 + 0.07 * math.sin(3 * angle + a) + 0.04 * math.sin(7 * angle + b)
            h = _height(d, wobble)
            if d < CRATER + 2:
                h = HEIGHT              # no low spots in the rim for the lake to leak out
            if h < 0:
                continue
            heights[(u, w)] = h
            # Hotter rock near the top: more magma.
            block = "magma" if d < TOP + 3 and rng.random() < 0.25 else rng.choice(ROCK)
            s.fill((u, -2, CENTER + w), (u, h, CENTER + w), block)
    return heights


def _crater(s):
    """Hollow out the crater and fill it with lava."""
    for u in range(-CRATER, CRATER + 1):
        for w in range(-CRATER, CRATER + 1):
            if math.hypot(u, w) < CRATER:
                s.fill((u, HEIGHT - LAKE, CENTER + w), (u, HEIGHT, CENTER + w), "air")
                s.fill((u, HEIGHT - LAKE, CENTER + w), (u, HEIGHT - 1, CENTER + w), "lava")
                s.set((u, HEIGHT - LAKE - 1, CENTER + w), "magma")


def _fountain(s):
    """A column of lava sources, bottom up, standing in the middle of the lake,
    and a ring of them round its top that falls back like spray."""
    top = HEIGHT + FOUNTAIN
    for v in range(HEIGHT, top + 1):
        s.set((0, v, CENTER), "lava")
    for u in range(-2, 3):
        for w in range(-2, 3):
            if 1 <= math.hypot(u, w) <= 2.3:
                s.set((u, top - 1, CENTER + w), "lava")


def _streams(s, heights):
    """Lava sources just outside the rim, to run down the slopes."""
    for angle in (-math.pi / 2 + 0.3, math.pi * 0.75):   # front, and back left
        u = round((TOP + 1) * math.cos(angle))
        w = round((TOP + 1) * math.sin(angle))
        s.set((u, heights[(u, w)] + 1, CENTER + w), "lava")


def build(s):
    rng = random.Random(11)   # the same volcano every time
    size = BASE + APRON
    s.fill((-size, 0, CENTER - size), (size, HEIGHT + FOUNTAIN + 4, CENTER + size), "air")
    s.fill((-size, -3, CENTER - size), (size, -1, CENTER + size), "blackstone")
    heights = _cone(s, rng)
    _crater(s)
    _fountain(s)
    _streams(s, heights)
