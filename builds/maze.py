"""A hedge maze with a beacon burning in the middle.

Two-block-wide corridors, hedges too tall to see over, and a beam of light
from the centre so nobody can get properly lost: head for the beam. A few
extra gaps are knocked through the walls so it's forgiving, and there's a
way in at the front and a way out at the back.

The maze is the same every time for a given SEED. Change SEED for a new one.

Front faces the player. Coordinates: u right, v up (0 = feet level), w
forward (0 = front of the build). See lib/build.py.
"""

import random

SEED = 5
CELLS = 9                      # cells across; the middle nine are the clearing
PITCH = 3                      # two blocks of corridor, one of hedge
SIZE = CELLS * PITCH + 1       # 28 blocks square
FRONT = 2                      # how far ahead of the player the maze starts
LOOPS = CELLS * 2              # extra gaps, so it's forgiving

# With --around, the player stands here: just inside the entrance.
AROUND = (0, FRONT + 1)

# Two courses of moss with a leafy top. The leaves are marked permanent or
# they'd rot away with no tree to hold them.
HEDGE = "moss_block"
LEAVES = 'oak_leaves ["persistent_bit"=true]'
GROUND = "grass_block"


def _cell(i, j):
    """The blocks a cell covers: the two-wide gap between hedges."""
    return range(PITCH * i + 1, PITCH * i + PITCH), range(PITCH * j + 1, PITCH * j + PITCH)


def _between(one, two):
    """The hedge blocks standing between two neighbouring cells."""
    (i1, j1), (i2, j2) = sorted((one, two))
    if i1 != i2:
        return {(PITCH * i2, b) for b in _cell(i1, j1)[1]}
    return {(a, PITCH * j2) for a in _cell(i1, j1)[0]}


def _dig(rng):
    """Hedge blocks left standing after a depth-first maze is dug out."""
    walls = {(a, b) for a in range(SIZE) for b in range(SIZE)
             if a % PITCH == 0 or b % PITCH == 0}

    seen, stack = {(0, 0)}, [(0, 0)]
    while stack:
        i, j = stack[-1]
        nearby = [(i + di, j + dj) for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1))
                  if 0 <= i + di < CELLS and 0 <= j + dj < CELLS
                  and (i + di, j + dj) not in seen]
        if not nearby:
            stack.pop()
            continue
        step = rng.choice(nearby)
        walls -= _between((i, j), step)
        seen.add(step)
        stack.append(step)

    # Knock a few more through, so every wrong turn isn't a dead end.
    for _ in range(LOOPS):
        i, j = rng.randrange(CELLS - 1), rng.randrange(CELLS - 1)
        walls -= _between((i, j), rng.choice(((i + 1, j), (i, j + 1))))

    # A clearing of nine cells in the middle for the beacon.
    middle = CELLS // 2
    for a in range(PITCH * (middle - 1) + 1, PITCH * (middle + 1) + PITCH):
        for b in range(PITCH * (middle - 1) + 1, PITCH * (middle + 1) + PITCH):
            walls.discard((a, b))

    # In at the front, out at the back.
    for b in _cell(middle, 0)[0]:
        walls.discard((b, 0))
        walls.discard((b, SIZE - 1))
    return walls


def _runs(cells):
    """Cover a set of blocks with as few straight runs as possible."""
    left, out = set(cells), []
    for along_b, shortest in ((True, 2), (False, 1)):
        groups = {}
        for a, b in sorted(left):
            key, step = (a, b) if along_b else (b, a)
            groups.setdefault(key, []).append(step)
        for key, steps in sorted(groups.items()):
            start = prev = steps[0]
            for step in steps[1:] + [None]:
                if step is None or step > prev + 1:
                    if prev - start + 1 >= shortest:
                        out.append(((key, start), (key, prev)) if along_b
                                   else ((start, key), (prev, key)))
                        left -= {(key, x) if along_b else (x, key)
                                 for x in range(start, prev + 1)}
                    start = step
                prev = step
    return out


def build(s):
    rng = random.Random(SEED)
    walls = _dig(rng)
    at = lambda a, v, b: (a - SIZE // 2, v, FRONT + b)

    s.fill(at(0, 0, 0), at(SIZE - 1, 6, SIZE - 1), "air")
    s.fill(at(0, -2, 0), at(SIZE - 1, -1, SIZE - 1), GROUND)

    for (a1, b1), (a2, b2) in _runs(walls):
        s.fill(at(a1, 0, b1), at(a2, 1, b2), HEDGE)
        s.fill(at(a1, 2, b1), at(a2, 2, b2), LEAVES)

    # Lights in the paths, so the maze is walkable after dark and nothing
    # spawns in it to frighten anyone.
    for a in range(1, SIZE, 5):
        for b in range(1, SIZE, 5):
            if (a, b) not in walls:
                s.set(at(a, -1, b), "sea_lantern")

    # The beacon, on the iron it needs to light, at the centre of the clearing.
    middle = SIZE // 2
    s.fill(at(middle - 1, -1, middle - 1), at(middle + 1, -1, middle + 1), "iron_block")
    s.set(at(middle, 0, middle), "beacon")
