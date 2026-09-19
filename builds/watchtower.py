"""Stone watchtower: 5x5, three floors, ladder inside, glass-roofed lookout.

Front door faces the player. Coordinates: u right, v up (0 = feet level),
w forward (0 = front wall). See lib/build.py.
"""

TOP = 11  # the lookout floor

# With --around, the player stands here: centre of the ground floor.
AROUND = (0, 2)


def build(s):
    # Site: a 7x7 stone foundation (flattens small bumps and fills dips),
    # a cobblestone apron around the base, and clear air above.
    s.fill((-3, -3, -1), (3, -1, 5), "stone_bricks")
    s.fill((-3, -1, -1), (3, -1, 5), "cobblestone")
    s.fill((-3, 0, -1), (3, TOP + 5, 5), "air")

    # Shell and corner pillars.
    s.fill((-2, 0, 0), (2, TOP, 4), "stone_bricks", "hollow")
    for u in (-2, 2):
        for w in (0, 4):
            s.fill((u, 0, w), (u, TOP + 3, w), "polished_andesite")

    # Floors: ground, first floor, lookout.
    for v in (-1, 5, TOP):
        s.fill((-1, v, 1), (1, v, 3), "spruce_planks")

    # Doorway with a carved lintel.
    s.fill((0, 0, 0), (0, 1, 0), "air")
    s.set((0, 2, 0), "chiseled_stone_bricks")

    # Windows: small ones on the ground floor, tall ones upstairs.
    for p in [(-2, 3, 2), (2, 3, 2), (0, 3, 4)]:
        s.set(p, "glass_pane")
    for side in [(0, 0), (-2, 2), (2, 2), (0, 4)]:
        u, w = side
        s.fill((u, 7, w), (u, 8, w), "glass_pane")

    # Ladder up the back wall, through holes in both upper floors.
    s.ladder((1, 0, 3), (1, TOP, 3), faces="back")

    # Lookout: crenellated parapet, pillars carry a glass roof.
    for u in range(-2, 3):
        for w in range(0, 5):
            on_edge = u in (-2, 2) or w in (0, 4)
            if on_edge and (u + w) % 2 == 0:
                s.set((u, TOP + 1, w), "stone_bricks")
    s.fill((-2, TOP + 4, 0), (2, TOP + 4, 4), "glass")

    # Light.
    s.set((-1, 0, 1), "torch", check=True)
    s.set((-1, 6, 1), "lantern", check=True)
    s.set((-1, TOP + 1, 1), "lantern", check=True)
    s.set((-3, 0, -1), "lantern", check=True)
    s.set((3, 0, -1), "lantern", check=True)
