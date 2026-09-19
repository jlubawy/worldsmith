"""Build designs in front of a player, with undo.

A design is a Python file in builds/ with a `build(site)` function. It places
blocks in the player's frame of reference, so it doesn't care which way they
face:

    u  right (+) / left (-)
    v  up from the player's feet level (0 = the layer they stand in)
    w  forward, away from the player (0 = `distance` blocks ahead)

Before anything is placed, the whole area the design touches is saved as a
structure inside the world, and `undo` loads it back.

    python3 lib/build.py run <design> [player] [--distance N | --around] [--up N] [--dry-run]
    python3 lib/build.py run <design> --at X,Y,Z,FACING [--dry-run]

--at places the design's origin (u=v=w=0) at a fixed block, facing a compass
direction, without needing a player: for attaching builds to each other.
--around builds the design with the player inside it, at the spot the design
names in its AROUND = (u, w) setting. It first waits for them to stand still,
so walls can't land on a moving player.
    python3 lib/build.py undo
    python3 lib/build.py list
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys
import time
from datetime import datetime

from bedrock import FACINGS, Location, ask, loaded, players, run_many, where

ROOT = pathlib.Path(__file__).resolve().parent.parent
DESIGNS = ROOT / "builds"

# Largest structure /structure save accepts, and largest single /fill.
MAX_STRUCTURE = (64, 384, 64)
MAX_FILL = 32768

LADDER_FACING = {"north": 2, "south": 3, "west": 4, "east": 5}
ERROR_WORDS = re.compile(r"invalid|unknown|syntax error|can't|cannot|could not|not loaded|outside|out of the world", re.I)

Point = tuple[int, int, int]


def _direction_name(vec: tuple[int, int]) -> str:
    return next(name for name, d in FACINGS.items() if d == vec)


class Site:
    """Records commands for a design, translating the player's frame to world coordinates."""

    def __init__(self, x: int, y: int, z: int, facing: str):
        self.origin = (x, y, z)
        self.facing = facing
        fx, fz = FACINGS[facing]
        self.fwd = (fx, fz)
        self.right = (-fz, fx)
        self.commands: list[str] = []
        self.checks: list[tuple[Point, str]] = []
        self._lo: list[int] | None = None
        self._hi: list[int] | None = None

    # -- coordinates --------------------------------------------------------

    def at(self, u: int, v: int, w: int) -> Point:
        ox, oy, oz = self.origin
        return (ox + u * self.right[0] + w * self.fwd[0],
                oy + v,
                oz + u * self.right[1] + w * self.fwd[1])

    def direction(self, local: str) -> str:
        """World compass direction for 'forward', 'back', 'left' or 'right'."""
        fx, fz = self.fwd
        rx, rz = self.right
        return _direction_name({"forward": (fx, fz), "back": (-fx, -fz),
                                "right": (rx, rz), "left": (-rx, -rz)}[local])

    def _touch(self, *points: Point) -> None:
        for p in points:
            if self._lo is None:
                self._lo, self._hi = list(p), list(p)
            else:
                for i in range(3):
                    self._lo[i] = min(self._lo[i], p[i])
                    self._hi[i] = max(self._hi[i], p[i])

    @property
    def bounds(self) -> tuple[Point, Point]:
        if self._lo is None:
            raise ValueError("the design placed nothing")
        return tuple(self._lo), tuple(self._hi)

    # -- placing blocks -----------------------------------------------------

    def fill(self, a: Point, b: Point, block: str, mode: str = "") -> None:
        """Fill the box between two (u, v, w) corners. mode: hollow, outline, keep, …"""
        p, q = self.at(*a), self.at(*b)
        lo = [min(p[i], q[i]) for i in range(3)]
        hi = [max(p[i], q[i]) for i in range(3)]
        self._touch(tuple(lo), tuple(hi))
        if mode in ("hollow", "outline"):
            # Splitting would put walls inside the box; these must stay whole.
            self.commands.append(self._fill_cmd(lo, hi, block, mode))
            return
        # Split by layers so no single fill exceeds the game's limit.
        layer = (hi[0] - lo[0] + 1) * (hi[2] - lo[2] + 1)
        step = max(1, MAX_FILL // layer)
        y = lo[1]
        while y <= hi[1]:
            top = min(hi[1], y + step - 1)
            self.commands.append(self._fill_cmd([lo[0], y, lo[2]], [hi[0], top, hi[2]], block, mode))
            y = top + 1

    @staticmethod
    def _fill_cmd(lo, hi, block, mode) -> str:
        return f"fill {lo[0]} {lo[1]} {lo[2]} {hi[0]} {hi[1]} {hi[2]} {block} {mode}".rstrip()

    def set(self, p: Point, block: str, check: bool = False) -> None:
        """Place one block. check=True verifies it's still there afterwards,
        for blocks that pop off without support (ladders, torches, …)."""
        x, y, z = self.at(*p)
        self._touch((x, y, z))
        self.commands.append(f"setblock {x} {y} {z} {block}")
        if check:
            self.checks.append(((x, y, z), block.split(" ")[0]))

    def ladder(self, a: Point, b: Point, faces: str) -> None:
        """A ladder column from a to b, facing `faces` (forward/back/left/right).
        It needs a solid block directly behind it, opposite that direction."""
        state = f'ladder ["facing_direction"={LADDER_FACING[self.direction(faces)]}]'
        self.fill(a, b, state)
        (u1, v1, w1), (u2, v2, w2) = a, b
        for v in range(min(v1, v2), max(v1, v2) + 1):
            self.checks.append((self.at(u1, v, w1), "ladder"))


# -- journal of builds (for undo), kept inside the world folder so it moves with it

def _world() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("WORLD="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no WORLD in .env")


def _journal_path() -> pathlib.Path:
    return ROOT / "data" / "worlds" / _world() / "mc-builds.json"


def _load_journal() -> list[dict]:
    path = _journal_path()
    return json.loads(path.read_text()) if path.exists() else []


def _save_journal(entries: list[dict]) -> None:
    _journal_path().write_text(json.dumps(entries, indent=2) + "\n")


# -- commands ---------------------------------------------------------------------

def _load_design(name: str):
    path = DESIGNS / f"{name}.py"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in DESIGNS.glob("*.py"))) or "none"
        raise SystemExit(f"no design '{name}' (available: {available})")
    spec = importlib.util.spec_from_file_location(f"design_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pick_player(name: str | None) -> str:
    if name:
        return name
    online = players()
    if len(online) == 1:
        return online[0]
    raise SystemExit("say which player to build in front of: " + (", ".join(online) or "nobody is online"))


def _wait_until_still(player: str, seconds: int = 3, timeout: float = 120):
    """The player's location once they've stayed on one block for `seconds`."""
    send(f"tell {player} Building around you: stand still for a few seconds.")
    last, still, deadline = None, 0, time.time() + timeout
    while time.time() < deadline:
        loc = where(player)
        if loc is None:
            raise SystemExit(f"{player} went offline")
        here = (loc.x, loc.y, loc.z, loc.facing)
        still = still + 1 if here == last else 0
        last = here
        if still >= seconds:
            return loc
        time.sleep(1)
    raise SystemExit(f"{player} didn't stand still for {seconds}s; nothing built")


def run(design_name: str, player: str | None, distance: int | None, dry_run: bool, up: int = 0,
        at: tuple[int, int, int, str] | None = None) -> int:
    design = _load_design(design_name)
    if at is not None:
        ax, ay, az, facing = at
        if facing not in FACINGS:
            raise SystemExit(f"facing must be one of {', '.join(FACINGS)}")
        # A stand-in "player" one block behind the origin, so ahead(1) is the origin.
        fx, fz = FACINGS[facing]
        player = "-"
        loc = Location("-", "overworld", ax - fx, ay, az - fz, 0.0, facing)
        distance = 1
    else:
        player = _pick_player(player)
        if distance is None:
            if not hasattr(design, "AROUND"):
                raise SystemExit(f"{design_name} doesn't say where a player fits inside (AROUND)")
            loc = where(player) if dry_run else _wait_until_still(player)
        else:
            loc = where(player)
        if loc is None:
            raise SystemExit(f"{player} is not online")
        if loc.dimension != "overworld":
            raise SystemExit(f"{player} is in the {loc.dimension}; builds are overworld-only for now")

    if distance is None:
        # Shift the origin so the player lands on the design's AROUND spot.
        au, aw = design.AROUND
        probe = Site(0, 0, 0, loc.facing)
        dx, _, dz = probe.at(au, 0, aw)
        x, y, z = loc.x - dx, loc.y, loc.z - dz
    else:
        x, y, z = loc.ahead(distance)
    site = Site(x, y + up, z, loc.facing)
    design.build(site)
    lo, hi = site.bounds
    size = tuple(hi[i] - lo[i] + 1 for i in range(3))
    if any(size[i] > MAX_STRUCTURE[i] for i in range(3)):
        raise SystemExit(f"design is {size[0]}x{size[1]}x{size[2]}; undo supports up to "
                         f"{MAX_STRUCTURE[0]}x{MAX_STRUCTURE[1]}x{MAX_STRUCTURE[2]}")

    if at is not None:
        print(f"{design_name} at ({at[0]}, {at[1]}, {at[2]}), facing {at[3]}")
    else:
        where_text = "around them" if distance is None else f"front {distance} blocks ahead"
        print(f"{design_name} for {player} at ({loc.x}, {loc.y}, {loc.z}): facing {loc.facing}, {where_text}")
    print(f"area {lo} to {hi} ({size[0]}x{size[1]}x{size[2]}), {len(site.commands)} commands")
    if dry_run:
        print("\n".join(site.commands))
        return 0

    journal = _load_journal()
    number = max((e["number"] for e in journal), default=0) + 1
    structure = f"mcundo_{number}"

    with loaded(lo, hi):
        reply = ask(f"structure save {structure} {lo[0]} {lo[1]} {lo[2]} {hi[0]} {hi[1]} {hi[2]} false disk true")
        if not reply.startswith("Saved a structure"):
            raise SystemExit(f"couldn't save the undo snapshot, nothing built: {reply.splitlines()[0]}")
        journal.append({"number": number, "structure": structure, "design": design_name,
                        "player": player, "min": lo, "max": hi,
                        "time": datetime.now().isoformat(timespec="seconds")})
        _save_journal(journal)

        # Send everything in batches; run_many waits for the server to finish
        # (about 20 commands a second) and returns every reply.
        print(f"placing: about {len(site.commands) // 20 + 1}s", flush=True)
        replies = run_many(site.commands)
        errors = [line.strip() for line in replies.splitlines() if ERROR_WORDS.search(line)]

        missing = []
        for (bx, by, bz), block in site.checks:
            reply = ask(f"testforblock {bx} {by} {bz} {block}")
            if not reply.startswith("Successfully"):
                missing.append(reply.splitlines()[0])

    print(f"built (undo #{number}: ./mc undo)")
    for line in errors:
        print(f"  command error: {line}")
    for line in missing:
        print(f"  check failed: {line}")
    return 1 if errors or missing else 0


def undo() -> int:
    journal = _load_journal()
    if not journal:
        raise SystemExit("nothing to undo in this world")
    entry = journal[-1]
    lo, hi = tuple(entry["min"]), tuple(entry["max"])
    with loaded(lo, hi):
        reply = ask(f"structure load {entry['structure']} {lo[0]} {lo[1]} {lo[2]}")
        if not reply.startswith("Loaded a structure"):
            raise SystemExit(f"undo failed, nothing changed: {reply.splitlines()[0]}")
        ask(f"structure delete {entry['structure']}")
    journal.pop()
    _save_journal(journal)
    print(f"undid #{entry['number']} ({entry['design']} from {entry['time']})")
    return 0


def list_builds() -> int:
    journal = _load_journal()
    if not journal:
        print("no builds to undo in this world")
    for e in reversed(journal):
        print(f"#{e['number']:<3} {e['design']:<16} {e['time']}  by {e['player']}  {tuple(e['min'])} to {tuple(e['max'])}")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("run", "undo", "list"):
        print(__doc__.split("\n\n")[-1], file=sys.stderr)
        return 2
    if argv[0] == "undo":
        return undo()
    if argv[0] == "list":
        return list_builds()

    args = argv[1:]
    dry_run = "--dry-run" in args
    around = "--around" in args
    args = [a for a in args if a != "--around"]
    at = None
    if "--at" in args:
        i = args.index("--at")
        parts = args[i + 1].split(",") if i + 1 < len(args) else []
        del args[i:i + 2]
        try:
            at = (int(parts[0]), int(parts[1]), int(parts[2]), parts[3])
        except (IndexError, ValueError):
            at = None
        if at is None or len(parts) != 4:
            raise SystemExit("--at takes X,Y,Z,FACING, e.g. --at 6,76,-68,south")
    opts = {"--distance": 3, "--up": 0}
    for flag in opts:
        if flag in args:
            i = args.index(flag)
            opts[flag] = int(args[i + 1])
            del args[i:i + 2]
    args = [a for a in args if a != "--dry-run"]
    if not args:
        raise SystemExit("usage: build.py run <design> [player] [--distance N] [--up N] [--dry-run]")
    distance = None if around else opts["--distance"]
    return run(args[0], args[1] if len(args) > 1 else None, distance, dry_run, opts["--up"], at)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
