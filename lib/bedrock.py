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
