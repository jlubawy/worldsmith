"""A mountain of TNT, with a fuse running out to a big red button.

A huge lumpy heap of TNT, 45 blocks across and 30 tall, with wobbly towers
of it sprouting from the top and loose blocks tumbled round the foot, inside
a red-and-white danger ring. Every block you can see is TNT; the inside is
sand, so there's only (only!) a few thousand of them.

A line of redstone dust runs from the heap to a button at the front: press
it and the whole lot goes up. Nothing happens until someone presses it (or
lights the TNT). That many explosions will freeze the server for a while,
and the crater reaches well past the danger ring, where `./mc undo` can't
put things back. Set it off somewhere you don't mind.

Front faces the player. Coordinates: u right, v up (0 = feet level), w
forward (0 = front of the build). See lib/build.py.
"""

import math
import random

RADIUS = 22        # the heap, at the ground
PEAK = 30          # and how tall it gets
RING = 24          # radius of the danger ring
FUSE = 12          # blocks of redstone from the button to the heap
CENTER = FUSE + RADIUS + 1
TOWERS = 9


def _heights(rng):
    """How tall the heap stands in each column: a steep dome with lumps."""
    bumps = [(rng.uniform(0, 2 * math.pi), rng.randint(2, 7), rng.uniform(0.04, 0.1))
             for _ in range(4)]
    heights = {}
    for u in range(-RADIUS - 2, RADIUS + 3):
        for w in range(-RADIUS - 2, RADIUS + 3):
            d = math.hypot(u, w)
            angle = math.atan2(w, u)
            lump = 1 + sum(size * math.sin(n * angle + phase) for phase, n, size in bumps)
            d = max(0, d / lump + rng.uniform(-0.5, 0.5))
            if d > RADIUS or (w < -RADIUS and abs(u) <= 1):   # clear of the fuse
                continue
            heights[(u, w)] = round(PEAK * (1 - (d / RADIUS) ** 1.4))
    return heights


def _heap(s, heights):
    """TNT wherever it shows, from the top of a column down to the lowest of
    its neighbours; sand below that."""
    for (u, w), top in heights.items():
        around = [heights.get((u + du, w + dw), -1)
                  for du, dw in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        shell = min(top, min(around) + 1)
        if shell > 0:
            s.fill((u, 0, CENTER + w), (u, shell - 1, CENTER + w), "sand")
        s.fill((u, max(shell, 0), CENTER + w), (u, top, CENTER + w), "tnt")


def _towers(s, rng, heights):
    """Stacks of TNT leaning out of the upper slopes, stepping over as they go."""
    for n in range(TOWERS):
        angle = n * 2 * math.pi / TOWERS + rng.uniform(-0.3, 0.3)
        reach = rng.uniform(3, 9)
        u, w = round(reach * math.cos(angle)), round(reach * math.sin(angle))
        v = heights.get((u, w), PEAK)
        for step in range(rng.randint(8, 16)):
            if step and step % 4 == 0:
                u += round(math.cos(angle))
                w += round(math.sin(angle))
            s.set((u, v + step, CENTER + w), "tnt")


def _tumbled(s, rng):
    """Loose TNT that's rolled off the heap: odd blocks and little stacks."""
    for _ in range(40):
        angle = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(RADIUS + 0.5, RING - 1.5)
        u, w = round(d * math.cos(angle)), round(d * math.sin(angle))
        if u == 0 and w < 0:
            continue                      # keep the fuse clear
        s.fill((u, 0, CENTER + w), (u, rng.choice((0, 0, 0, 1, 2)), CENTER + w), "tnt")


def _ring(s):
    """Red and white stripes round the heap, on the ground."""
    for u in range(-RING, RING + 1):
        for w in range(-RING, RING + 1):
            if RING - 1 <= math.hypot(u, w) < RING + 0.5:
                stripe = (math.atan2(w, u) * 24 / math.pi) % 2 < 1
                s.set((u, -1, CENTER + w), "red_concrete" if stripe else "white_concrete")


def _fuse(s):
    """Redstone dust from the button straight into the front of the heap."""
    s.fill((0, 0, 1), (0, 0, CENTER - RADIUS - 1), "redstone_wire")
    s.set((0, 0, CENTER - RADIUS), "tnt")   # the lumps might leave a gap here
    s.set((0, 0, 0), "red_concrete")
    s.set((0, 1, 0), 'stone_button ["facing_direction"=1]', check=True)


def build(s):
    rng = random.Random(3)   # the same heap every time
    heights = _heights(rng)
    s.fill((-RING - 1, 0, 0), (RING + 1, PEAK + 18, CENTER + RING + 1), "air")
    s.fill((-RING - 1, -2, 0), (RING + 1, -1, CENTER + RING + 1), "grass_block")
    _ring(s)
    _heap(s, heights)
    _towers(s, rng, heights)
    _tumbled(s, rng)
    _fuse(s)
