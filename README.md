# Bedrock Server

A Minecraft Bedrock server that runs either at home (Docker on your computer)
or in the cloud (an AWS Lightsail server made with Pulumi). You can move worlds
back and forth between them, and build things in them from scripts.
Everything goes through `./mc`. Run `./mc help` for the full list of commands.

Players connect on port **19132**, using your computer's LAN IP at home, the
cloud server's IP, or your own domain name if you set one up (see [DNS](#dns)).

## Getting started

You need Docker (Docker Desktop on a Mac) and Python 3. The cloud part also
needs the AWS CLI, Pulumi and Node.js, and the DNS part needs `gcloud`.

```sh
./mc setup              # a few questions; answers saved locally (below)
./mc use world --new    # create a world and start the server
```

`setup` asks for a server name, the gamertags allowed on the cloud server, a
time zone, your LAN IP, and optionally a DNS name and an AWS region. It
creates the server identity key too. Your answers go in two files that git
ignores, so nothing personal gets committed:

| File | Holds | Synced to the cloud |
| --- | --- | --- |
| `config.env` | server name, allowlist, operators, time zone | yes |
| `.env` | active world, this machine's IP, DNS settings | no |

Run `./mc setup` again whenever you want to change something. Each question
shows your saved answer, so Enter keeps it. Afterwards, `./mc restart` applies
the changes at home and `./mc cloud deploy` applies them in the cloud.

## Everyday commands

```sh
./mc status                 # active world and whether the server is up
./mc worlds                 # all worlds and where each one lives
./mc use creative --new     # create a world and switch to it
./mc use world              # switch back
./mc logs                   # follow the log (ctrl-c to stop following)
./mc cmd say hello          # run a console command
./mc where                  # where everyone is (block coordinates + facing)
./mc build watchtower Steve # build a design in front of Steve, facing him
./mc undo                   # put back what the last build replaced
./mc backup                 # snapshot the active world into backups/
./mc stop | start | restart
```

Put `--cloud` first to do any of these on the cloud server, for example
`./mc --cloud status` or `./mc --cloud use creative`.

## Worlds

The server runs one world at a time. Every world is a folder in `data/worlds/`,
and `./mc use <world>` picks which one is live. Switching takes a few seconds,
and the other worlds sit untouched on disk.

- **Gameplay defaults for every world** are in [worlds/defaults.env](worlds/defaults.env).
- **Settings for one world** go in `worlds/<world>.env`, which only needs the
  settings that differ from the defaults. Copy
  [worlds/example.env.sample](worlds/example.env.sample) to start one. It's
  easiest to create this file *before* the first `./mc use <world> --new`,
  because the seed and game mode matter most when the world is first
  generated.
- Apply changes with `./mc restart`.

A typo can't create an empty world by accident: `use` refuses to make a world
that doesn't exist unless you add `--new`.

## Home and cloud

A world lives in exactly one place at a time. That way progress never splits
into two diverging copies.

```sh
./mc push world    # move 'world' from this computer to the cloud and start it there
./mc pull world    # move it back and start it here
```

A move stops the world on the side it's leaving and saves a tarball in that
side's `backups/`. It then starts the world on the other side, deletes it from
the old side, and leaves a marker there so the world can't be restarted as a
blank copy. `./mc worlds` shows where each world lives.

The moves refuse to overwrite a world that already exists on the other side.

### Home

Runs on your computer through Docker, so it's only up while the computer is
awake. Online mode is off, so nobody needs an Xbox sign-in on the LAN.

Players at home join with your computer's LAN IP (`PUBLIC_IP` in `.env`). It's
worth reserving that address in your router so it doesn't change.

### Cloud

Lightsail `small_3_0`: 2 GB of RAM, **$12/month** flat, which includes the
static IP and transfer. There's also a daily whole-disk snapshot that is kept
for 7 days (a few cents a month). Lightsail bills the server whether it's
running or stopped, so the only way to stop paying is to tear it down (see
below).

The cloud always runs with **Xbox sign-in required and the allowlist on** (set
in [compose.cloud.yaml](compose.cloud.yaml)). Anyone not listed in
`ALLOW_LIST_USERS` (set with `./mc setup`) can't join. `./mc` refuses to start a
cloud world while that list is empty.

#### First-time setup

1. **Create an AWS account** and give the CLI credentials:
   ```sh
   brew install awscli
   aws login              # signs the CLI in through your browser
   aws sts get-caller-identity   # should print your account
   ```
   If your AWS CLI has no `aws login`, create an access key for an IAM user
   instead and run `aws configure`.

2. **Pick a region and list your players:** run `./mc setup` and answer the
   AWS region question (for example `us-west-2`) and the allowlist question.
   Setup creates the Pulumi stack in that region. The region is fixed once
   the server exists.

3. **Create the server:**
   ```sh
   cd infra
   export PULUMI_CONFIG_PASSPHRASE=   # the stack has no secrets; empty is fine
   pulumi up
   cd ..
   ```
   This creates the server, a static IP, and the firewall (TCP 19132 and UDP
   19140–19159 open, SSH key-only using `~/.ssh/id_ed25519.pub`).

4. **Prepare the server and move a world in:**
   ```sh
   ./mc cloud deploy      # waits for first boot, installs the config
   ./mc push world
   ```

5. **Point your DNS name at it** (if you set one up): `./mc dns cloud`

`./mc cloud ssh` opens a shell on the server, and `./mc cloud ip` prints its
address.

#### Stopping the cloud bill

Pull every world home first. **Destroying the server deletes the worlds on
it.**

```sh
./mc --cloud worlds          # nothing should say "here"
cd infra && pulumi destroy
```

Afterwards, check the Lightsail console for leftover snapshots. They cost a
few cents a month each until deleted.

## DNS

Optional. If you have a domain in Google Cloud DNS, give `./mc setup` a name
(like `mc.example.com`), the zone and its project. Players can then save one
address, and you point it wherever the server is running:

```sh
./mc dns           # show where the name points now
./mc dns cloud     # point it at the Lightsail server
./mc dns home      # point it at this computer (its PUBLIC_IP)
```

After a move, `push` and `pull` tell you if the name still points at the
other side. This uses your active gcloud account, which needs permission to
edit records in that zone.

| Server is | Name points at | Who can connect |
| --- | --- | --- |
| In the cloud | the Lightsail static IP | anyone on the allowlist, anywhere |
| At home | this computer's LAN IP | only devices on the home network |

With the 5-minute TTL, most devices pick up a change within a few minutes. A
device that already looked the name up may hold the old address a little
longer.

A public name pointing at a home-network address works as long as the router
passes it through. If the name fails at home while the IP works,
the router is blocking private addresses in DNS answers ("DNS rebinding
protection"). Use the IP at home in that case.

## Joining

**Play → Servers → Add Server**, enter your DNS name or the server's IP and
port `19132`.

- **Phones, tablets and PCs** can all add servers by address.
- **Xbox, PlayStation and Switch** only list Microsoft's featured servers. They
  need a workaround such as [BedrockConnect](https://github.com/Pugmatt/BedrockConnect).
- It won't appear under **LAN Games**. Add it by address, even at home.

## Building

```sh
./mc build <design> [player] [--distance N] [--up N] [--dry-run]
./mc undo          # revert the most recent build
./mc builds        # builds that can be undone, newest first
```

A build goes in front of the player (3 blocks ahead by default), with its
front facing them. `--up` raises it, and `--dry-run` prints the commands
without placing anything. You can leave out the player when only one person
is online.

Before placing anything, the builder:
1. keeps the area loaded, even if nobody is standing nearby,
2. saves everything in the area as a structure inside the world (that's what
   `undo` loads back, so an undo restores exactly what was there), and
3. afterwards reports any command errors, plus any block that fell off (a
   ladder or torch with nothing to hang on).

Undo history is per world, in `data/worlds/<world>/mc-builds.json`, and it
moves with the world when you push or pull.

### Writing a design

A design is a file in [builds/](builds/) with a `build(site)` function. It
works in the player's frame: `u` is right, `v` is up from their feet, and `w`
is forward from the front of the build. See
[builds/watchtower.py](builds/watchtower.py).

```python
def build(s):
    s.fill((-2, 0, 0), (2, 4, 4), "stone_bricks", "hollow")    # a 5x5x5 room
    s.fill((0, 0, 0), (0, 1, 0), "air")                        # door facing the player
    s.ladder((1, 0, 3), (1, 4, 3), faces="back")               # on the back wall
    s.set((-1, 0, 1), "torch", check=True)
```

## Building with scripts

[lib/bedrock.py](lib/bedrock.py) talks to the running server. It sends
console commands and reads their replies from the log. It runs on whichever
machine hosts the server, so for the cloud run it there (`./mc cloud ssh`) or
through `./mc --cloud …`.

```sh
./mc where                      # everyone online
./mc --cloud where Steve --json # one player, machine-readable
```

```
Steve                overworld  x=0 y=61 z=-61  facing east
```

- **`x y z`** is the block the player is standing *in*, at foot level. The
  block they're standing *on* is `y - 1`. (The server reports eye height,
  1.62 blocks up; `where` corrects for it.)
- **`facing`** is the nearest compass direction, which is what you want for
  lining up a build.

In a Python build script:

```python
from bedrock import where, send, ask

here = where("Steve")                      # None if they're offline
x, y, z = here.ahead(5)                    # 5 blocks in front, at their feet
send(f"fill {x-2} {y} {z-2} {x+2} {y+4} {z+2} glass hollow")
reply = ask("testforblock 0 64 0 air", ["Successfully found", "The block at"])
```

`send` runs a command without waiting. `ask` waits for the reply and returns
it, given the text every possible reply starts with.

## Server console

Bedrock has no RCON. Use `./mc cmd <command>` for one-off commands. For an
interactive console, run `docker attach minecraft-bedrock` (on the cloud, run
it from `./mc cloud ssh`). Detach with **ctrl-p ctrl-q**, because ctrl-c
stops the server.

## Networking (NetherNet)

Bedrock 1.26 uses a transport called NetherNet. It's the only one current
clients can join with: under the older `raknet` transport the server logs a
`TRANSPORT TYPE ERROR`. It needs two sets of ports:

| Port | Protocol | Purpose |
| --- | --- | --- |
| 19132 | TCP | the join handshake (it's HTTP) |
| 19140–19159 | UDP | gameplay, one port per connected player |

Docker publishes both sets, and the Lightsail firewall opens them. The server
runs behind Docker's network translation, so it can't see the address players
actually reach. `PUBLIC_IP` in `.env` tells it which address to hand out:
your LAN IP at home, and the static IP in the cloud (`./mc cloud deploy`
sets that one).

**Server identity.** Every Bedrock server has an identity key, and players
are asked to trust it. Without a saved key the server makes a new one on every
start, and everyone has to re-accept it. `keys/server_identity_key.pem` is
created once and used both at home and in the cloud, so restarts and moves
don't prompt anyone. Keep it private: it's in `.gitignore` and synced to the
cloud over SSH.

**LAN Games list.** Automatic LAN discovery doesn't pass through Docker, so
the server won't show up there. Add it by address.

## Files

```
mc                    the command-line tool
lib/bedrock.py        send commands to the server and read replies (where, …)
lib/build.py          builds designs in front of a player, with undo
builds/               designs
compose.yaml          the server container, used in both places
compose.cloud.yaml    cloud-only overrides (sign-in + allowlist)
worlds/defaults.env   settings for every world
worlds/<world>.env    per-world overrides (optional)
config.env            your server settings, from ./mc setup (gitignored)
.env                  this machine's world, IP and DNS settings (gitignored)
keys/                 the server identity key (gitignored, synced to the cloud)
infra/                Pulumi stack for the Lightsail server
data/                 worlds and server files (gitignored)
backups/              world snapshots (gitignored)
```

Pulumi keeps this project's state in `~/.pulumi-minecraft` on your computer,
separate from your usual Pulumi login. If you lose that folder, Pulumi loses
track of the server. The server itself keeps running, and you can delete or
re-import it from the Lightsail console.
