"""A rocket on its launch pad: climb the ladder inside, sit in the glass nose.

White hull, red fins and nose cone, and a cockpit of windows right round the
top with a ladder up to it. Sea lanterns inside and on the pad, so it's lit
after dark and nothing spawns on it.

Front faces the player. Coordinates: u right, v up (0 = feet level), w
forward (0 = front of the build). See lib/build.py.
"""

import math

PAD = 12         # radius of the launch pad
BODY = 4         # radius of the hull
TANKS = 22       # top of the cylinder, where the nose cone starts
COCKPIT = 17     # the cockpit floor
WINDOWS = 18     # the bottom row of windows
CEILING = 21
NOSE = 30        # the tip
FIN = 9          # how high the fins reach
CENTER = PAD + 2 # w of the rocket's axis; the pad starts a couple ahead

# With --around, the player stands here: on the pad, in front of the hatch.
AROUND = (0, CENTER - BODY - 3)

HULL = "white_concrete"
TRIM = "red_concrete"
FLOOR = "smooth_stone"


def _disc(radius):
    """Every (u, w) offset inside a circle of this radius."""
    return {(u, w) for u in range(-radius, radius + 1)
            for w in range(-radius, radius + 1)
            if round(math.hypot(u, w)) <= radius}


def _ring(radius):
    """Just the rim of that circle."""
    return _disc(radius) - _disc(radius - 1) if radius else {(0, 0)}


def _layer(s, offsets, v, block):
    """Place a set of offsets at one height, as a fill per contiguous run."""
    rows = {}
    for u, w in offsets:
        rows.setdefault(u, []).append(w)
    for u, ws in sorted(rows.items()):
        ws.sort()
        start = prev = ws[0]
        for w in ws[1:] + [None]:
            if w is None or w > prev + 1:
                s.fill((u, v, CENTER + start), (u, v, CENTER + prev), block)
                start = w
            prev = w


def _hull(s):
    """The cylinder, as one tall fill per block of the rim."""
    for u, w in sorted(_ring(BODY)):
        s.fill((u, 0, CENTER + w), (u, TANKS, CENTER + w), HULL)
    for v in (0, 11, TANKS):                       # red bands round the tank
        _layer(s, _ring(BODY), v, TRIM)
    _layer(s, _disc(BODY - 1), 0, FLOOR)           # something to stand on
    _layer(s, _disc(BODY - 1), COCKPIT, FLOOR)     # the cockpit floor
    _layer(s, _disc(BODY - 1), CEILING, HULL)      # and its ceiling


def _windows(s):
    """Four windows round the cockpit, and the hatch at the bottom."""
    for u, w in ((0, -BODY), (0, BODY), (-BODY, 0), (BODY, 0)):
        a = (-1, 1) if u == 0 else (u, u)
        b = (w, w) if u == 0 else (-1, 1)
        s.fill((a[0], WINDOWS, CENTER + b[0]), (a[1], CEILING - 1, CENTER + b[1]), "glass")
    s.fill((-1, 1, CENTER - BODY), (1, 2, CENTER - BODY), "air")


def _reach(v):
    """How far out along its diagonal a fin still stands at height v."""
    return BODY - 1 + round(2 * (FIN - 1 - v) / (FIN - 1))


def _fins(s):
    """Four fins, set on the diagonals: the hatch and the windows stay clear."""
    for du, dw in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        for step in range(BODY - 1, BODY + 2):
            standing = [v for v in range(FIN) if _reach(v) >= step]
            if not standing:
                continue
            for near in (step - 1, step):    # two blocks wide, so it has no gaps
                s.fill((du * step, 0, CENTER + dw * near),
                       (du * step, max(standing), CENTER + dw * near), TRIM)


def _cone(s):
    """The nose cone: solid discs, narrowing to the tip."""
    for v in range(TANKS + 1, NOSE + 1):
        radius = round(BODY * (NOSE - v) / (NOSE - TANKS))
        _layer(s, _disc(radius), v, TRIM)


def build(s):
    s.fill((-PAD, 0, CENTER - PAD), (PAD, NOSE + 2, CENTER + PAD), "air")
    _layer(s, _disc(PAD), -1, FLOOR)                     # the pad
    for radius in (PAD, PAD - 4):                        # markings on it
        _layer(s, _ring(radius), -1, TRIM)
    for u, w in sorted(_ring(PAD - 2)):                  # floodlights round it
        if (u + w) % 4 == 0:
            s.set((u, -1, CENTER + w), "sea_lantern")

    _hull(s)
    _windows(s)
    _fins(s)
    _cone(s)

    for v in (5, 12, COCKPIT):                           # lit all the way up
        s.set((BODY - 1, v, CENTER), "sea_lantern")
    # Last, so it cuts its own hole through the cockpit floor.
    s.ladder((0, 1, CENTER + BODY - 1), (0, COCKPIT, CENTER + BODY - 1), faces="back")
