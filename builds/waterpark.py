"""A water park: a tower, a glass slide and a big pool to land in.

Climb the ladder inside the tower, then take your pick: the slide from
halfway up, or the diving board off the top. Both end in the pool. Sea
lanterns light the whole thing, including the pool floor, so nothing spawns
in it after dark and nobody has to swim in the dark.

Front faces the player. Coordinates: u right, v up (0 = feet level), w
forward (0 = front of the build). See lib/build.py.
"""

# The pool, sunk into a sand beach. Water sits flush with the sand.
BEACH_U = 10
BEACH_W = (0, 24)
POOL_U = 7
POOL_W = (2, 13)
POOL_FLOOR = -4

# The tower stands on the beach behind the pool.
TOWER_U = 3
TOWER_W = (16, 22)
TOWER_TOP = 16       # the top floor; the diving board runs out from it
LANDING = 10         # the floor the slide leaves from

# The slide drops a block for every block forward, so it starts one below
# the landing: water can't run back through the door into the tower.
SLIDE_TOP = LANDING - 1
SLIDE_STEPS = 9      # nine steps down, ending over the pool
BOARD_TIP = 8        # how far forward the diving board reaches

# Stripes up the tower, three blocks each.
BANDS = ("light_blue_concrete", "white_concrete", "yellow_concrete",
         "red_concrete", "lime_concrete")


def _slide(s):
    """A glass half-pipe from the tower down into the pool, with water in it."""
    for step in range(SLIDE_STEPS + 1):
        v, w = SLIDE_TOP - step, TOWER_W[0] - 1 - step
        s.fill((-2, v, w), (2, v, w), "glass")              # the trough floor
        for u in (-2, 2):
            s.fill((u, v + 1, w), (u, v + 3, w), "glass")   # and its sides
        # A source every few steps, so the cascade can't run dry halfway down.
        if step % 3 == 0:
            s.set((0, v + 1, w), "water")
        # Legs down into the pool, every third step, so it isn't floating.
        if step % 3 == 2:
            for u in (-2, 2):
                s.fill((u, POOL_FLOOR, w), (u, v - 1, w), "white_concrete")


def _tower(s):
    """Striped walls, two floors and the ladder joining them."""
    for v in range(0, TOWER_TOP + 1):
        s.fill((-TOWER_U, v, TOWER_W[0]), (TOWER_U, v, TOWER_W[1]),
               BANDS[(v // 3) % len(BANDS)], "outline")

    for v in (LANDING, TOWER_TOP):
        s.fill((-2, v, TOWER_W[0] + 1), (2, v, TOWER_W[1] - 1), "smooth_stone")
        s.set((0, v, TOWER_W[1] - 3), "sea_lantern")

    # Way in at the bottom, and out onto the slide from the landing. The wall
    # under the slide door stays: it's the sill you step over.
    s.fill((-1, 0, TOWER_W[0]), (1, 2, TOWER_W[0]), "air")
    s.fill((-1, LANDING + 1, TOWER_W[0]), (1, LANDING + 2, TOWER_W[0]), "air")

    # Placed last so it cuts its own holes through the floors.
    s.ladder((0, 0, TOWER_W[1] - 1), (0, TOWER_TOP, TOWER_W[1] - 1), faces="back")


def _board(s):
    """The diving board, out over the deep end, with a rail most of the way."""
    s.fill((-1, TOWER_TOP, BOARD_TIP), (1, TOWER_TOP, TOWER_W[0] - 1), "smooth_stone")
    s.fill((-TOWER_U, TOWER_TOP + 1, TOWER_W[0]), (TOWER_U, TOWER_TOP + 1, TOWER_W[1]),
           "glass", "outline")                                  # railing round the top
    s.fill((-1, TOWER_TOP + 1, TOWER_W[0]), (1, TOWER_TOP + 1, TOWER_W[0]), "air")
    for u in (-2, 2):                                           # rails, but not at the end
        s.fill((u, TOWER_TOP, BOARD_TIP + 3), (u, TOWER_TOP + 1, TOWER_W[0] - 1), "glass")


def build(s):
    # Beach, then the pool basin cut into it, then fill the pool. Water stops
    # a block below the sand so it sits flush with the ground you walk on.
    s.fill((-BEACH_U, 0, BEACH_W[0]), (BEACH_U, TOWER_TOP + 6, BEACH_W[1]), "air")
    s.fill((-BEACH_U, -3, BEACH_W[0]), (BEACH_U, -1, BEACH_W[1]), "sand")
    s.fill((-POOL_U, POOL_FLOOR, POOL_W[0]), (POOL_U, -1, POOL_W[1]), "stone")
    s.fill((-POOL_U, POOL_FLOOR + 1, POOL_W[0]), (POOL_U, -1, POOL_W[1]), "water")

    # Lights sunk into the pool floor and the sand, so the park is lit after
    # dark and nothing spawns on it.
    for u in range(-6, 7, 3):
        for w in range(POOL_W[0] + 1, POOL_W[1], 3):
            s.set((u, POOL_FLOOR, w), "sea_lantern")
    for u in (-BEACH_U + 1, BEACH_U - 1):
        for w in range(BEACH_W[0] + 2, BEACH_W[1], 5):
            s.set((u, -1, w), "sea_lantern")

    _tower(s)
    _slide(s)
    _board(s)
