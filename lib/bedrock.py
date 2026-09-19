"""Talk to the running Bedrock server: send console commands, read replies.

Runs on the machine hosting the server (./mc forwards it with --cloud).
Build scripts can import it:

    from bedrock import where, send
    here = where("Steve")
    x, y, z = here.ahead(5)          # 5 blocks in front of them, at their feet
    send(f"setblock {x} {y} {z} diamond_block")

Or from the shell: ./mc where [player] [--json]
"""

from __future__ import annotations

import json
import re
import math
import subprocess
import sys
import time
from dataclasses import asdict, dataclass

CONTAINER = "minecraft-bedrock"

# querytarget reports a player's eye position; feet are this far below.
EYE_HEIGHT = 1.62

DIMENSIONS = {0: "overworld", 1: "nether", 2: "the_end"}

# Bedrock yaw: 0 faces +Z (south), 90 faces -X (west), 180 faces -Z (north),
# -90 faces +X (east). (dx, dz) is one block in that direction.
FACINGS = {"south": (0, 1), "west": (-1, 0), "north": (0, -1), "east": (1, 0)}


def send(command: str) -> None:
    """Run a console command. Its output only appears in the server log."""
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "send-command", command],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"send-command failed: {(result.stdout + result.stderr).strip()}")


def send_many(commands: list[str], batch: int = 50) -> None:
    """Queue many commands quickly: each docker exec feeds the server a batch
    of lines. They queue up: the server runs about 20 a second (one per tick),
    so use run_many to wait for them to finish."""
    for i in range(0, len(commands), batch):
        send("\n".join(commands[i:i + batch]))


def run_many(commands: list[str]) -> str:
    """Run commands, wait until the server has worked through all of them, and
    return every reply they logged.

    Ends the batch with a uniquely named scoreboard objective: its reply can
    only appear once everything queued before it has run.
    """
    marker = f"mcsync{int(time.time() * 1000) % 10**9}"
    window_start = time.time() - 5
    already = len(_logs_since(window_start))
    send_many(commands + [f"scoreboard objectives add {marker} dummy"])
    deadline = time.time() + 30 + len(commands) / 10   # twice the expected time
    while time.time() < deadline:
        time.sleep(1)
        log = _logs_since(window_start)[already:]
        end = log.find(marker)
        if end != -1:
            send(f"scoreboard objectives remove {marker}")
            return LOG_PREFIX.sub("", log[:log.rfind("\n", 0, end) + 1])
    raise TimeoutError(f"the server didn't finish {len(commands)} commands in time")


def _logs_since(since: float) -> str:
    result = subprocess.run(
        ["docker", "logs", "--since", f"{since:.3f}", CONTAINER],
        capture_output=True, text=True, check=True,
    )
    return result.stdout + result.stderr


LOG_PREFIX = re.compile(r"^\[[\d\- :]+ [A-Z]+\] ", re.M)


def ask(command: str, markers: list[str] | None = None, timeout: float = 5.0) -> str:
    """Run a command and return its reply from the server log.

    Console replies carry no request id, so this returns whatever the log
    gains after the command is sent, with the timestamp prefix removed. Pass
    `markers` to skip unrelated lines (a player joining, say): the reply then
    starts at the first new occurrence of any of them.
    """
    window_start = time.time() - 5  # slack for clock skew with the daemon
    already = len(_logs_since(window_start))
    send(command)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.2)
        new = LOG_PREFIX.sub("", _logs_since(window_start)[already:]).lstrip("\n")
        if not new:
            continue
        if markers is None:
            time.sleep(0.2)  # let a multi-line reply finish
            return LOG_PREFIX.sub("", _logs_since(window_start)[already:]).lstrip("\n")
        hits = [i for m in markers if (i := new.find(m)) != -1]
        if hits:
            return new[min(hits):]
    raise TimeoutError(f"no reply to {command!r} within {timeout}s")


def players() -> list[str]:
    """Names of everyone online."""
    reply = ask("list", ["There are ", "There is "])
    count = re.match(r"There (?:are|is) (\d+)/", reply)
    if not count or count.group(1) == "0":
        return []
    names_line = reply.partition("\n")[2].split("\n", 1)[0]
    return [n.strip() for n in names_line.split(",") if n.strip()]


class loaded:
    """Keep a box loaded while inside the `with`, even with no player nearby."""

    def __init__(self, lo: tuple[int, int, int], hi: tuple[int, int, int], name: str = "mcbuild"):
        self.lo, self.hi, self.name = lo, hi, name

    def __enter__(self):
        ask(f"tickingarea remove {self.name}")  # leftover from an interrupted run
        reply = ask(f"tickingarea add {self.lo[0]} {self.lo[1]} {self.lo[2]} "
                    f"{self.hi[0]} {self.hi[1]} {self.hi[2]} {self.name}")
        first = reply.splitlines()[0] if reply else ""
        if "ticking area" not in reply.lower() or re.search(r"invalid|cannot|can't|too", first, re.I):
            raise RuntimeError(f"couldn't load the area: {first}")
        # Chunks load in the background. Wait until both far corners answer,
        # or the first commands of a build could land on unloaded ground.
        corners = [self.lo, (self.hi[0], self.lo[1], self.hi[2])]
        deadline = time.time() + 30
        while time.time() < deadline:
            replies = [ask(f"testforblock {x} {y} {z} air") for x, y, z in corners]
            if not any("outside of the world" in r for r in replies):
                return self
            time.sleep(1)
        raise RuntimeError("the area didn't load within 30s")

    def __exit__(self, *exc):
        ask(f"tickingarea remove {self.name}")


def is_empty(lo: tuple[int, int, int], hi: tuple[int, int, int]) -> bool:
    """True if every block in the box is air. One command, any size: the box
    is compared with a same-sized box of open sky directly above it."""
    height = hi[1] - lo[1] + 1
    ref_y = 319 - height + 1          # reference box ends at the build limit
    if ref_y <= hi[1]:
        raise ValueError(f"box is too tall to check ({height} blocks); keep it under {319 // 2}")
    reply = ask(f"testforblocks {lo[0]} {lo[1]} {lo[2]} {hi[0]} {hi[1]} {hi[2]} {lo[0]} {ref_y} {lo[2]}",
                ["blocks compared", "not identical", "rror", "nvalid", "annot"])
    if "blocks compared" in reply:
        return True
    if "not identical" in reply:
        return False
    raise RuntimeError(f"testforblocks failed: {reply.splitlines()[0]}")


def highest_block(x1: int, z1: int, x2: int, z2: int, y_lo: int = 40, y_hi: int = 150) -> int | None:
    """Highest y with any non-air block in the column area (terrain, trees,
    builds), or None if it's all air. Binary search: ~9 commands."""
    lo_x, hi_x = sorted((x1, x2))
    lo_z, hi_z = sorted((z1, z2))
    if is_empty((lo_x, y_lo, lo_z), (hi_x, y_hi, hi_z)):
        return None
    low, high = y_lo, y_hi          # invariant: something at or above `low`; nothing above `high`
    while low < high:
        mid = (low + high + 1) // 2
        if is_empty((lo_x, mid, lo_z), (hi_x, y_hi, hi_z)):
            high = mid - 1
        else:
            low = mid
    return low


@dataclass
class Location:
    player: str
    dimension: str
    x: int          # block coordinates of the block the player stands in
    y: int          # (the block below is the one they stand on)
    z: int
    yaw: float
    facing: str     # nearest cardinal direction: north, south, east, west

    def ahead(self, distance: int) -> tuple[int, int, int]:
        """Block position `distance` blocks in front, at the player's feet level."""
        dx, dz = FACINGS[self.facing]
        return self.x + dx * distance, self.y, self.z + dz * distance


def _facing(yaw: float) -> str:
    yaw = (yaw + 180) % 360 - 180          # normalise to [-180, 180)
    if -45 <= yaw < 45:
        return "south"
    if 45 <= yaw < 135:
        return "west"
    if -135 <= yaw < -45:
        return "east"
    return "north"


def where(player: str) -> Location | None:
    """Where `player` is, or None if they aren't online."""
    reply = ask(f'querytarget @a[name="{player}"]', ["Target data:", "No targets matched"])
    if reply.startswith("No targets matched"):
        return None
    data, _ = json.JSONDecoder().raw_decode(reply[len("Target data:"):].lstrip())
    target = data[0]
    pos = target["position"]
    return Location(
        player=player,
        dimension=DIMENSIONS.get(target["dimension"], str(target["dimension"])),
        x=math.floor(pos["x"]),
        # The small epsilon absorbs float noise like 62.62001 - 1.62.
        y=math.floor(pos["y"] - EYE_HEIGHT + 1e-3),
        z=math.floor(pos["z"]),
        yaw=round(target["yRot"], 1),
        facing=_facing(target["yRot"]),
    )


def _main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--json"]
    as_json = "--json" in argv
    if not args or args[0] != "where":
        print("usage: bedrock.py where [player] [--json]", file=sys.stderr)
        return 2

    names = args[1:] or players()
    if not names:
        print("nobody is online", file=sys.stderr)
        return 1

    found = []
    for name in names:
        loc = where(name)
        if loc is None:
            print(f"{name} is not online", file=sys.stderr)
            continue
        found.append(loc)

    if as_json:
        print(json.dumps([asdict(loc) for loc in found], indent=2))
    else:
        for loc in found:
            print(f"{loc.player:<20} {loc.dimension:<10} x={loc.x} y={loc.y} z={loc.z}  facing {loc.facing}")
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
