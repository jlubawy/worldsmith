"""The Eiffel Tower: four curving lattice legs, three platforms, an antenna.

Roughly one block to four and a half metres, so the model stands 76 blocks
tall on a 29-block square of legs. The legs follow the real tower's
exponential curve, the four great arches open under the first platform, and
every face is braced with crossed diagonals the whole way up.

Front faces the player. Coordinates: u right, v up (0 = feet level), w
forward (0 = front of the build). See lib/build.py.

It's a big build: a few hundred commands, so give it a minute.
"""

import math

# Heights above the ground the tower stands on.
DECK1 = 13     # first platform
DECK2 = 26     # second platform
TOP = 63       # top platform
ROOF = 67      # over the lantern room
HEIGHT = 76    # tip of the antenna
ARCH_LOW = 7   # the ironwork under the first platform reaches down to here
ARCH_RISE = 4  # how far a great arch's crown rises into it

CENTER = 18    # w of the tower's axis; the plaza starts a few blocks ahead
PAD = 16       # half-width of the plaza

# With --around, the player stands here: in the middle of the arches.
AROUND = (0, CENTER)

POST = "polished_andesite"   # legs, girders and arch ribs
LATTICE = "iron_bars"        # the openwork between them
FLOOR = "dark_oak_planks"    # platform decks

CORNERS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
FACES = ("front", "back", "left", "right")

# Where the crossed bracing starts and stops. The decks close off 13 and 26.
BAYS = ((DECK1, 19), (19, DECK2), (DECK2, 35), (35, 44), (44, 53), (53, TOP))


# -- the curve --------------------------------------------------------------

def _radius(v):
    """Half the distance between opposite legs at height v.

    The real tower's profile is close to an exponential: 14 blocks at the
    ground, 7 at the first platform, 4 at the second, then a slender shaft
    that stops narrowing at 2 (5 blocks across) near the top.
    """
    return max(2, round(1 + 13 * math.exp(-v / 17)))


def _thickness(v):
    """How wide a single leg is: chunky below the first platform, slimmer above."""
    return 3 if v < DECK1 else 2


def _gap(v):
    """Half the open span between two legs on one face."""
    return _radius(v) - _thickness(v)


def _reach(v):
    """Half the span from the axis to a leg's inner edge, where bracing lands."""
    return _radius(v) - 1


def _leg_box(v, su, sw):
    """The (u, w) box one leg fills at height v."""
    r, t = _radius(v), _thickness(v)
    us = sorted((su * r, su * (r - t + 1)))
    ws = sorted((CENTER + sw * r, CENTER + sw * (r - t + 1)))
    return (us[0], ws[0]), (us[1], ws[1])


def _on_face(face, a, v):
    """(u, v, w) of the point `a` blocks along `face` from the axis, at height v."""
    r = _radius(v)
    if face == "front":
        return (a, v, CENTER - r)
    if face == "back":
        return (a, v, CENTER + r)
    if face == "left":
        return (-r, v, CENTER + a)
    return (r, v, CENTER + a)


def _columns(s, points, block):
    """Place points as vertical fills, so a near-vertical run costs one command."""
    runs = {}
    for u, v, w in points:
        runs.setdefault((u, w), set()).add(v)
    for (u, w), heights in sorted(runs.items()):
        levels = sorted(heights)
        start = prev = levels[0]
        for v in levels[1:]:
            if v > prev + 1:
                s.fill((u, start, w), (u, prev, w), block)
                start = v
            prev = v
        s.fill((u, start, w), (u, prev, w), block)


# -- the parts --------------------------------------------------------------

def _legs(s):
    """The four legs, as one fill per stretch that doesn't move."""
    for su, sw in CORNERS:
        start, box = 0, None
        for v in range(0, TOP + 2):
            here = _leg_box(v, su, sw) if v <= TOP else None
            if here != box:
                if box is not None:
                    (u1, w1), (u2, w2) = box
                    s.fill((u1, start, w1), (u2, v - 1, w2), POST)
                box, start = here, v


def _opening(v):
    """Half-width of the open space under a great arch at height v."""
    gap = _gap(v)
    if v < ARCH_LOW:
        return gap                         # below this the legs stand clear
    climb = (v - ARCH_LOW + 1) / (ARCH_RISE + 1)
    return int(gap * math.sqrt(max(0.0, 1 - climb * climb)))


def _arches(s):
    """The four great arches: ironwork between the legs, curving away underneath."""
    for v in range(ARCH_LOW, DECK1):
        gap, open_half = _gap(v), _opening(v)
        if open_half >= gap:
            continue
        for face in FACES:
            if open_half == 0:             # the arch has closed: a solid panel
                s.fill(_on_face(face, -gap, v), _on_face(face, gap, v), LATTICE)
                continue
            for side in (1, -1):
                s.fill(_on_face(face, side * (open_half + 1), v),
                       _on_face(face, side * gap, v), LATTICE)
                s.set(_on_face(face, side * (open_half + 1), v), POST)


def _bracing(s):
    """Crossed diagonals on every face of every bay, following the taper."""
    for v0, v1 in BAYS:
        for face in FACES:
            for rising in (1, -1):
                points = []
                for v in range(v0, v1 + 1):
                    across = (2 * (v - v0) / (v1 - v0) - 1) * _reach(v) * rising
                    points.append(_on_face(face, round(across), v))
                _columns(s, points, LATTICE)
        if v0 not in (DECK1, DECK2):
            _ring(s, v0)


def _ring(s, v):
    """A girder running right around the tower, tying the four legs together."""
    r = _radius(v)
    s.fill((-r, v, CENTER - r), (r, v, CENTER + r), POST, "outline")


def _platform(s, v, over):
    """A deck overhanging the tower by `over`, with a girder under it and a rail on it."""
    r = _radius(v) + over
    s.fill((-r, v - 1, CENTER - r), (r, v - 1, CENTER + r), POST, "outline")
    s.fill((-r, v, CENTER - r), (r, v, CENTER + r), FLOOR)
    s.fill((-r, v + 1, CENTER - r), (r, v + 1, CENTER + r), LATTICE, "outline")
    for du in (-r + 2, r - 2):
        for dw in (-r + 2, r - 2):
            s.set((du, v + 1, CENTER + dw), "lantern", check=True)


def _top(s):
    """The lantern room above the top platform, and the antenna over it."""
    s.fill((-1, TOP + 1, CENTER - 1), (1, ROOF - 1, CENTER + 1), "glass", "hollow")
    s.set((0, TOP + 2, CENTER), "sea_lantern")
    s.fill((-2, ROOF, CENTER - 2), (2, ROOF, CENTER + 2), POST)
    s.fill((0, ROOF + 1, CENTER), (0, HEIGHT - 2, CENTER), LATTICE)
    s.set((0, HEIGHT - 1, CENTER), "sea_lantern")
    s.set((0, HEIGHT, CENTER), "end_rod")


def build(s):
    # A flat plaza to stand the tower on, with a cobblestone kerb, and clear
    # sky above it: the legs are 29 blocks apart and won't fit a hillside.
    s.fill((-PAD, -3, CENTER - PAD), (PAD, -1, CENTER + PAD), "stone_bricks")
    s.fill((-PAD, -1, CENTER - PAD), (PAD, -1, CENTER + PAD), "cobblestone", "outline")
    s.fill((-PAD, 0, CENTER - PAD), (PAD, HEIGHT + 1, CENTER + PAD), "air")

    _legs(s)
    _arches(s)
    _bracing(s)
    _platform(s, DECK1, over=2)
    _platform(s, DECK2, over=2)
    _platform(s, TOP, over=2)
    _top(s)

    # Light at the foot of each leg, the way the real one is lit from below.
    for su, sw in CORNERS:
        s.set((su * (PAD - 1), 0, CENTER + sw * (PAD - 1)), "lantern", check=True)
