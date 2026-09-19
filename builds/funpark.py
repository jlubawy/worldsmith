"""A fun park with a long roller coaster: a lift hill, big drops, camelbacks.

The track zigzags back and forth in sixteen lanes, climbing and dropping
along each one, so the ride is nearly a kilometre of rail in a park 52
blocks across. It starts with a 30-block lift hill, and every climb after
that is powered, so a cart never stalls.

The station is at the front, where the track comes back down to the ground.
Take a minecart from the chest, put it on the rails by the button, get in
and press the button. The cart comes back and stops at the station on its
own. Press the button again for another ride.

Front faces the player. Coordinates: u right, v up (0 = feet level), w
forward (0 = front of the build). See lib/build.py.
"""

LEFT = -23           # u of the first lane, the lift hill
PITCH = 3            # lanes are three apart: two blocks of air between them
LANES = 16
FRONT = 4            # w of the straight back to the station
NEAR = 8             # where the lanes turn round at the front
BACK = 58            # and at the back
LIFT = 30            # top of the lift hill

PARK_U = (-26, 25)
PARK_W = (0, 61)

# How each lane climbs and drops, in riding order: each number is a height
# the track goes to (a block up or down per block forward), and ("flat", n)
# holds the height for n blocks. The lift hill is first, and the last entry
# is the straight back to the station, which comes down to the ground there.
PROFILES = [
    [LIFT],
    [4],
    [16, 8],
    [20, 3],
    [14, 6, 12],
    [22, 5],
    [10, 3, 9],
    [18, 4],
    [12, 5, 12],
    [24, 3],
    [8, 2, 10, 4],
    [16, 3],
    [11, 4, 9],
    [15, 2],
    [9, 3, 8],
    [14, 4],
    [("flat", 30), 0],
]

BED = "polished_andesite"    # under the rails
RAINBOW = ("red_concrete", "orange_concrete", "yellow_concrete", "lime_concrete",
           "light_blue_concrete", "blue_concrete", "purple_concrete", "magenta_concrete")

# Bedrock's rail_direction values, by world compass direction.
STRAIGHT = {"north": 0, "south": 0, "east": 1, "west": 1}
ASCENDING = {"east": 2, "west": 3, "north": 4, "south": 5}
CURVE = {frozenset(("south", "east")): 6, frozenset(("south", "west")): 7,
         frozenset(("north", "west")): 8, frozenset(("north", "east")): 9}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}
LOCAL = {(0, 1): "forward", (0, -1): "back", (1, 0): "right", (-1, 0): "left"}


def _lane_u(k):
    return LEFT + PITCH * k


def _corners():
    """The loop's corners in riding order, starting at the foot of the lift."""
    points = [(_lane_u(0), FRONT), (_lane_u(0), BACK)]
    for k in range(1, LANES):
        ends = (BACK, NEAR) if k % 2 else (NEAR, BACK)
        if k == LANES - 1:
            ends = (BACK, FRONT)
        points += [(_lane_u(k), ends[0]), (_lane_u(k), ends[1])]
    return points


def _heights(start, length, ops):
    """Height at each of a straight's length + 1 blocks, corner to corner.

    The block after a corner stays level, and so does the one before the
    next corner: rails only curve on the level.
    """
    hs = [start, start]
    for op in ops:
        if isinstance(op, tuple):
            hs += [hs[-1]] * op[1]
            continue
        while hs[-1] != op:
            hs.append(hs[-1] + (1 if op > hs[-1] else -1))
        hs.append(op)  # level for a block at every crest and dip
    if len(hs) > length + 1:
        raise ValueError(f"profile {ops} doesn't fit in {length} blocks")
    return hs + [hs[-1]] * (length + 1 - len(hs))


def _track():
    """Every block of the loop in riding order, as (u, v, w), and where the
    straight back to the station starts in that list."""
    corners = _corners()
    lanes = iter(PROFILES)
    cells, v, home = [], 0, 0
    for i, (a, b) in enumerate(zip(corners, corners[1:] + corners[:1])):
        length = abs(b[0] - a[0]) + abs(b[1] - a[1])
        du, dw = (b[0] - a[0]) // length, (b[1] - a[1]) // length
        turn = i % 2 == 1 and i != len(corners) - 1
        if i == len(corners) - 1:
            home = len(cells)
        hs = _heights(v, length, [] if turn else next(lanes))
        cells += [(a[0] + du * j, hs[j], a[1] + dw * j) for j in range(length)]
        v = hs[-1]
    if v != 0:
        raise ValueError("the track doesn't come back down to the station")
    return cells, home


def _shapes(s, cells):
    """(rail_direction, kind) for every block; kind is up, down, level or curve."""
    def toward(a, b):
        return s.direction(LOCAL[(b[0] - a[0], b[2] - a[2])])

    shapes = []
    for i, cur in enumerate(cells):
        prev, nxt = cells[i - 1], cells[(i + 1) % len(cells)]
        ahead, behind = toward(cur, nxt), toward(cur, prev)
        if nxt[1] > cur[1]:
            shapes.append((ASCENDING[ahead], "up"))
        elif prev[1] > cur[1]:
            shapes.append((ASCENDING[behind], "down"))
        elif ahead == OPPOSITE[behind]:
            shapes.append((STRAIGHT[ahead], "level"))
        else:
            shapes.append((CURVE[frozenset((ahead, behind))], "curve"))
        if shapes[-1][1] in ("up", "down") and ahead != OPPOSITE[behind]:
            raise ValueError(f"a slope on a corner at {cur}")
    return shapes


def _coaster(s):
    cells, home = _track()
    shapes = _shapes(s, cells)
    # The station brakes: the first three blocks of the drop at the end.
    # Unpowered they stop the cart; the button powers them (the power runs
    # along all three) and it rolls off down the slope.
    brakes = [i for i in range(home, len(cells)) if shapes[i][1] == "down"][:3]

    for i, ((u, v, w), (direction, kind)) in enumerate(zip(cells, shapes)):
        # Power every climb, and every fourth level block to keep the speed
        # up, but not on the way home: the cart has to slow down to stop.
        boost = kind == "up" or (kind == "level" and i % 4 == 0 and i < home)
        if v >= 2 and i % 3 == 0:
            colour = RAINBOW[((u - LEFT) // PITCH) % len(RAINBOW)]
            s.fill((u, 0, w), (u, v - 2, w), colour)
        s.set((u, v - 1, w), "redstone_block" if boost else BED)
        if boost:
            s.set((u, v, w), f'golden_rail ["rail_direction"={direction},"rail_data_bit"=true]')
        elif i in brakes:
            s.set((u, v, w), f'golden_rail ["rail_direction"={direction},"rail_data_bit"=false]')
        else:
            s.set((u, v, w), f'rail ["rail_direction"={direction}]')
    return [cells[i] for i in brakes]


def _station(s, brakes):
    """The button, on a post in front of the middle brake, and a chest of carts."""
    u, v, w = brakes[1]
    s.fill((u, 0, w - 1), (u, v - 1, w - 1), "stone_bricks")
    s.set((u, v, w - 1), 'stone_button ["facing_direction"=1]', check=True)
    s.set((u + 2, 0, w - 2), "chest")
    x, y, z = s.at(u + 2, 0, w - 2)
    s.commands.append(f"replaceitem block {x} {y} {z} slot.container 0 minecart 4")

    # A path in from the front of the park, under an arch.
    s.fill((u - 1, -1, PARK_W[0]), (u + 1, -1, w - 2), "polished_andesite")
    for side in (u - 2, u + 2):
        s.fill((side, 0, 1), (side, 4, 1), "white_concrete")
        s.set((side, 5, 1), "sea_lantern")
    s.fill((u - 2, 5, 1), (u + 2, 5, 1), "red_concrete")
    s.set((u, 5, 1), "sea_lantern")


def _grounds(s):
    """Clear the site, lay grass, and light it so nothing spawns in the park."""
    (u0, u1), (w0, w1) = PARK_U, PARK_W
    s.fill((u0, 0, w0), (u1, LIFT + 4, w1), "air")
    s.fill((u0, -2, w0), (u1, -2, w1), "dirt")
    s.fill((u0, -1, w0), (u1, -1, w1), "grass_block")
    # Between the lanes, where nothing stands on them.
    for k in range(-1, LANES):
        for w in range(w0 + 2, w1, 5):
            s.set((_lane_u(k) + 1, -1, w), "sea_lantern")


def build(s):
    _grounds(s)
    brakes = _coaster(s)
    _station(s, brakes)
