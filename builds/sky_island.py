"""Floating sky island, reached by a railed half-step stairway.

The origin is where the stairway starts: the first step is at w=0, and v=0 is
the level you stand on there. The block row behind the origin (w=-1, v=0) is
opened up, so a stairway leaving a parapet or a wall has a way out.

Built for the watchtower's south lookout:

    ./mc build sky_island --at 6,76,-68,south

Everything is plain full blocks and slabs (no facing states to get wrong),
so it works in any direction.
"""

import math
import random

RISE = 16          # blocks the stairway climbs (two half-steps per block)
RADIUS = 11        # island radius before the wobble
DEPTH = 11         # rock below the grass at the centre
FLOOR_V = 4        # nothing hangs below this (keeps clear of terrain/trees)

STEPS = RISE * 2
TOP_V = RISE - 1                   # the island's grass layer
CENTRE_W = STEPS + RADIUS - 2      # overlap the stairway's end by 2 blocks

FLOWERS = ["poppy", "dandelion", "azure_bluet", "cornflower"]
LEAVES = 'oak_leaves ["persistent_bit"=true]'


def build(s):
    rng = random.Random(7)  # same island every time for the same seed
    opening(s)
    island(s, rng)
    stairway(s)


def opening(s):
    s.fill((-1, 0, -1), (1, 0, -1), "air")


def stairway(s):
    """Walkway three wide, alternating slab and full block: half a block up
    per step, so nobody has to jump. Curbs and fences either side."""
    for i in range(STEPS):
        v = i // 2
        step = "stone_brick_slab" if i % 2 == 0 else "stone_bricks"
        s.fill((-1, v, i), (1, v, i), step)
        s.fill((-1, v + 1, i), (1, v + 3, i), "air")          # headroom
        for u in (-2, 2):
            s.set((u, v, i), "stone_bricks")
            s.set((u, v + 1, i), "oak_fence")
            if i % 6 == 3:
                s.set((u, v + 2, i), "lantern", check=True)


def island_radius(angle, rng_phase):
    a, b = rng_phase
    return RADIUS + 1.6 * math.sin(3 * angle + a) + 1.0 * math.sin(5 * angle + b)


def island(s, rng):
    phase = (rng.uniform(0, 6.28), rng.uniform(0, 6.28))
    cells = {}
    for u in range(-RADIUS - 3, RADIUS + 4):
        for dw in range(-RADIUS - 3, RADIUS + 4):
            d = math.hypot(u, dw)
            r = island_radius(math.atan2(dw, u), phase)
            if d <= r:
                cells[(u, dw)] = d / r

    # Body: grass, a few layers of dirt, then rock tapering to jagged points.
    for (u, dw), t in cells.items():
        w = CENTRE_W + dw
        top = TOP_V + (1 if t < 0.3 else 0)                  # gentle hill in the middle
        depth = DEPTH * (1 - t ** 1.4) + rng.uniform(0, 2.5)
        if t < 0.6 and rng.random() < 0.12:
            depth += rng.uniform(2, 6)                        # stalactites
        bottom = max(FLOOR_V, round(top - max(2, depth)))
        s.set((u, top, w), "grass_block")
        dirt_low = max(bottom, top - 3)
        if dirt_low <= top - 1:
            s.fill((u, dirt_low, w), (u, top - 1, w), "dirt")
        if bottom <= dirt_low - 1:
            rock = rng.choice(["stone", "stone", "andesite", "tuff"])
            s.fill((u, bottom, w), (u, dirt_low - 1, w), rock)
            # Ore flecks in the rock.
            if rng.random() < 0.18:
                ore = rng.choices(["coal_ore", "iron_ore", "copper_ore", "diamond_ore"], [5, 4, 3, 1])[0]
                s.set((u, rng.randint(bottom, dirt_low - 1), w), ore)
        # The underside: moss and the odd glowing block, lovely at night.
        roll = rng.random()
        if bottom < dirt_low:
            if roll < 0.10:
                s.set((u, bottom, w), "glowstone")
            elif roll < 0.15:
                s.set((u, bottom, w), "shroomlight")
            elif roll < 0.50:
                s.set((u, bottom, w), "moss_block")
        cells[(u, dw)] = (t, top)

    tree_at = (0, CENTRE_W + 1)
    pond = {(u, CENTRE_W + dw) for u in range(3, 7) for dw in range(2, 5)
            if ((u - 4.5) / 2.2) ** 2 + ((dw - 3) / 1.6) ** 2 <= 1}
    path = {(0, w) for w in range(STEPS, tree_at[1] - 2)}
    campfire = (-5, CENTRE_W + 3)

    # Pond: water flush with the grass, walled in by the ground around it.
    for i, (u, w) in enumerate(sorted(pond)):
        top = cells[(u, w - CENTRE_W)][1]
        s.set((u, top, w), "water")
        if i % 3 == 1:
            s.set((u, top + 1, w), "waterlily")

    # A mossy path from the stairway to the tree.
    for (u, w) in path:
        if (u, w - CENTRE_W) in cells:
            s.set((u, cells[(u, w - CENTRE_W)][1], w), "mossy_cobblestone")

    # Oak tree: trunk and a round canopy of leaves that never decay.
    tu, tw = tree_at
    ground = cells[(tu, tw - CENTRE_W)][1]
    trunk_top = ground + 6
    s.fill((tu, ground + 1, tw), (tu, trunk_top, tw), "oak_log")
    centre_v = trunk_top - 1
    for du in range(-4, 5):
        for dv in range(-2, 4):
            for dw in range(-4, 5):
                if (du, dw) == (0, 0) and dv <= 1:
                    continue
                dist = math.sqrt(du * du + (dv * 1.3) ** 2 + dw * dw)
                if dist <= 3.6 and not (dist > 3.1 and rng.random() < 0.5):
                    s.set((tu + du, centre_v + dv, tw + dw), LEAVES)

    # Campfire with a cobble ring, and flowers and grass everywhere else.
    cu, cw = campfire
    cground = cells[(cu, cw - CENTRE_W)][1]
    for du in (-1, 0, 1):
        for dw in (-1, 0, 1):
            if (du, dw) != (0, 0):
                s.set((cu + du, cground, cw + dw), "cobblestone")
    s.set((cu, cground + 1, cw), "campfire")

    busy = pond | path | {(cu + du, cw + dw) for du in (-1, 0, 1) for dw in (-1, 0, 1)}
    for (u, dw), (t, top) in cells.items():
        w = CENTRE_W + dw
        if (u, w) in busy or math.hypot(u - tu, w - tw) < 1.5 or t > 0.93:
            continue
        roll = rng.random()
        if roll < 0.07:
            s.set((u, top + 1, w), rng.choice(FLOWERS))
        elif roll < 0.30:
            s.set((u, top + 1, w), "short_grass")

    # Lamp posts around the rim.
    for k in range(8):
        angle = k * math.tau / 8 + 0.3
        r = island_radius(angle, phase) - 1.5
        u, dw = round(r * math.cos(angle)), round(r * math.sin(angle))
        if (u, dw) in cells and (u, CENTRE_W + dw) not in busy and abs(u) > 2:
            top = cells[(u, dw)][1]
            s.set((u, top + 1, CENTRE_W + dw), "oak_fence")
            s.set((u, top + 2, CENTRE_W + dw), "lantern", check=True)
