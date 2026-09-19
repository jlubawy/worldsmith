#!/usr/bin/env bash
# Worldsmith: run a Bedrock Edition game server at home or in the cloud, move
# worlds between them, and build in them. `./mc help` for usage.
# Unofficial; see the Legal section of the README.
set -euo pipefail

cd "$(dirname "$0")"

CONTAINER=minecraft-bedrock
REMOTE_DIR=/opt/minecraft
REMOTE_USER=ubuntu
# Keepalives: a dropped connection fails in ~1 minute instead of hanging forever.
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ConnectTimeout=10
          -o ServerAliveInterval=15 -o ServerAliveCountMax=4)

# Written by `./mc setup`, neither committed to git:
#   config.env  server settings (name, allowlist, time zone); synced to the cloud
#   .env        this machine's settings (active world, IP, DNS); never synced
CONFIG=config.env
DNS_TTL=300
EULA_URL=https://www.minecraft.net/eula

die() { echo "mc: $*" >&2; exit 1; }
say() { echo "==> $*" >&2; }

load_config() {
  local f
  set -a
  for f in "$CONFIG" .env; do
    # shellcheck source=/dev/null
    [[ -f $f ]] && . "./$f"
  done
  set +a
}

usage() {
  cat <<'EOF'
Usage: ./mc [--cloud] <command>

Without --cloud, commands act on the server on this machine. With --cloud,
they run on the cloud server (your config is synced first).

  setup                  answer a few questions; saved to config.env

  status                 active world and whether the server is up
  worlds                 list worlds and where each one lives
  use <world> [--new]    switch the active world and (re)start the server;
                         --new is required to create a world that doesn't exist
  start | stop | restart
  logs                   follow the server log
  cmd <command...>       run a server console command, e.g. `./mc cmd say hi`
  where [player] [--json]
                         where players are: block coordinates and facing
  backup [world]         snapshot a world into backups/ (keeps the last 10)

Building (designs live in builds/):
  build <design> [player] [--distance N | --around] [--up N] [--dry-run]
                         build a design in front of a player, facing them
  undo                   put back what the last build replaced
  builds                 list builds that can be undone

Moving worlds (a world lives in exactly one place at a time):
  push <world>           move a world from here to the cloud and start it there
  pull <world>           move a world from the cloud to here and start it here

Cloud server:
  cloud deploy           sync config and prepare the server (run after `pulumi up`)
  cloud ssh              open a shell on it
  cloud ip               print its address

DNS (optional, Google Cloud DNS; set up with ./mc setup):
  dns                    show where your server's name points
  dns cloud | home       point it at the cloud server or at this machine
EOF
}

# --- world state -------------------------------------------------------------

valid_world() {
  [[ ${1:-} =~ ^[A-Za-z0-9_-]+$ ]] || die "world names may only use letters, digits, - and _ (got '${1:-}')"
}

active_world() { sed -n 's/^WORLD=//p' .env 2>/dev/null | tail -1; }

set_active_world() {
  if [[ -f .env ]] && grep -q '^WORLD=' .env; then
    sed -i.bak "s/^WORLD=.*/WORLD=$1/" .env && rm -f .env.bak
  else
    echo "WORLD=$1" >> .env
  fi
}

world_dir() { echo "data/worlds/$1"; }
# Left behind when a world moves away, so it can't be silently recreated empty.
tombstone() { echo "data/worlds/.$1.moved"; }

is_cloud_host() { grep -q '^COMPOSE_FILE=.*compose.cloud.yaml' .env 2>/dev/null; }

running() { [[ $(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null) == true ]]; }

# Refuse to start a world that would be generated from scratch by accident.
eula_accepted() { [[ ${EULA:-} == TRUE ]]; }

check_startable() {
  local w=$1 allow_new=${2:-}
  eula_accepted || die "the server needs you to accept Mojang's EULA first; run ./mc setup"
  [[ -n $w ]] || die "no active world; pick one with ./mc use <world>"
  if [[ -f $(tombstone "$w") ]]; then
    die "world '$w' $(cat "$(tombstone "$w")"). Bring it back with ./mc pull $w (or push, from the other side)"
  fi
  if [[ ! -d $(world_dir "$w") && -z $allow_new ]]; then
    die "no world named '$w' here. Create it with ./mc use $w --new"
  fi
  if is_cloud_host && ! WORLD=$w docker compose config 2>/dev/null | grep -Eq 'ALLOW_LIST_USERS: "?[^" ]'; then
    die "no gamertags allowed on the cloud (ALLOW_LIST_USERS); run ./mc setup"
  fi
}

# --- setup ---------------------------------------------------------------------

# prompt VAR "question" [default]: read an answer; Enter keeps the default,
# "-" clears it.
prompt() {
  local var=$1 question=$2 default=${3:-} answer
  if [[ -n $default ]]; then
    read -r -p "$question [$default]: " answer || true
  else
    read -r -p "$question: " answer || true
  fi
  answer=${answer:-$default}
  [[ $answer == - ]] && answer=""
  [[ $answer != *[\"\$\`\\]* ]] || die "please don't use quotes, \$, \` or backslashes"
  printf -v "$var" '%s' "$answer"
}

detect_lan_ip() {
  ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null ||
    hostname -I 2>/dev/null | awk '{print $1}' || true
}

detect_tz() {
  readlink /etc/localtime 2>/dev/null | sed -n 's|.*/zoneinfo/||p' ||
    cat /etc/timezone 2>/dev/null || true
}

set_env_var() {  # set_env_var KEY VALUE in .env
  touch .env
  if grep -q "^$1=" .env; then
    sed -i.bak "s|^$1=.*|$1=$2|" .env && rm -f .env.bak
  else
    echo "$1=$2" >> .env
  fi
}

cmd_setup() {
  [[ -t 0 ]] || die "setup asks questions; run it in a terminal"
  is_cloud_host && die "run setup on your own computer; ./mc cloud deploy copies it here"
  load_config
  local eula server_name allow ops tz lan dns_name dns_zone="" dns_project="" region

  echo "Saved to $CONFIG (not committed). Enter keeps the [value]; - clears it."
  echo
  echo "The game server software belongs to Mojang and is covered by their End"
  echo "User License Agreement: $EULA_URL"
  prompt eula "Have you read it, and do you accept it? (yes/no)" "$(eula_accepted && echo yes || echo no)"
  case $eula in
    y|yes|Y|YES|Yes) eula=TRUE ;;
    *) eula=FALSE ;;
  esac
  echo
  prompt server_name "Server name in the server list" "${SERVER_NAME:-My Server}"
  prompt allow "Gamertags allowed on the cloud server, comma-separated" "${ALLOW_LIST_USERS:-}"
  prompt ops "Gamertags with operator powers (optional)" "${OPS:-}"
  prompt tz "Time zone" "${TZ:-$(detect_tz)}"
  prompt lan "This machine's LAN IP, for players at home" "$(sed -n 's/^PUBLIC_IP=//p' .env 2>/dev/null | tail -1 || true)"
  [[ -n $lan ]] || lan=$(detect_lan_ip)
  [[ $lan =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "'$lan' isn't an IPv4 address"

  echo
  echo "Optional: a name like mc.example.com in Google Cloud DNS, for ./mc dns."
  prompt dns_name "DNS name (blank to skip)" "${DNS_NAME:-}"
  dns_name=${dns_name%.}
  if [[ -n $dns_name ]]; then
    prompt dns_zone "Cloud DNS zone name" "${DNS_ZONE:-}"
    prompt dns_project "Google Cloud project holding that zone" "${DNS_PROJECT:-}"
    [[ -n $dns_zone && -n $dns_project ]] || die "DNS needs both a zone and a project"
  fi

  cat > "$CONFIG" <<EOF
# Written by ./mc setup; run it again to change these. Not committed to git.

# Whether you accepted Mojang's EULA ($EULA_URL).
# The server refuses to start unless this is TRUE.
EULA="$eula"

# Shown in the server list.
SERVER_NAME="$server_name"
# Who may join the cloud server (Xbox sign-in required there), and who gets
# operator powers. Comma-separated gamertags.
ALLOW_LIST_USERS="$allow"
OPS="$ops"
TZ="$tz"
EOF
  [[ -s .env ]] && grep -q '^WORLD=' .env || set_env_var WORLD world
  set_env_var PUBLIC_IP "$lan"
  set_env_var DNS_NAME "$dns_name"
  set_env_var DNS_ZONE "$dns_zone"
  set_env_var DNS_PROJECT "$dns_project"

  if [[ ! -f keys/server_identity_key.pem ]]; then
    mkdir -p keys && chmod 700 keys
    openssl ecparam -name secp384r1 -genkey -noout -out keys/server_identity_key.pem
    chmod 600 keys/server_identity_key.pem
    say "created the server identity key in keys/ (keep it private)"
  fi

  echo
  if [[ -f infra/Pulumi.prod.yaml ]]; then
    say "cloud stack already set up ($(sed -n 's/^ *aws:region: *//p' infra/Pulumi.prod.yaml))"
  elif command -v pulumi > /dev/null; then
    prompt region "AWS region for a cloud server (blank to skip)" ""
    if [[ -n $region ]]; then
      mkdir -p ~/.pulumi-minecraft
      [[ -d infra/node_modules ]] || npm install --prefix infra --no-fund --no-audit > /dev/null
      # Only a brand-new stack gets a region: changing it on one that already
      # has a server would replace everything, world included.
      if (cd infra && PULUMI_CONFIG_PASSPHRASE= pulumi stack init prod > /dev/null 2>&1); then
        (cd infra && PULUMI_CONFIG_PASSPHRASE= pulumi config set aws:region "$region")
        say "cloud stack ready; create the server with: cd infra && PULUMI_CONFIG_PASSPHRASE= pulumi up"
      else
        say "a 'prod' stack already exists in ~/.pulumi-minecraft; left it as it is"
      fi
    fi
  fi

  say "saved $CONFIG. Apply with ./mc restart (and ./mc cloud deploy for the cloud)"
  [[ $eula == TRUE ]] || say "you didn't accept the EULA, so the server won't start"
}

# --- local commands ------------------------------------------------------------

cmd_status() {
  local w; w=$(active_world)
  echo "world:  ${w:-(none)}"
  if running; then
    echo "server: running ($(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' "$CONTAINER"))"
  else
    echo "server: stopped"
  fi
}

cmd_worlds() {
  local active; active=$(active_world)
  mkdir -p data/worlds
  local names
  names=$(
    { find data/worlds -mindepth 1 -maxdepth 1 -type d -exec basename {} \;
      find data/worlds -mindepth 1 -maxdepth 1 -name '.*.moved' -exec basename {} .moved \; | sed 's/^\.//'
      find worlds -maxdepth 1 -name '*.env' ! -name defaults.env -exec basename {} .env \;
    } | sort -u
  )
  [[ -n $names ]] || { echo "(no worlds yet — create one with ./mc use <world> --new)"; return; }
  local w mark where
  while read -r w; do
    mark=" "; [[ $w == "$active" ]] && mark="*"
    if [[ -d $(world_dir "$w") ]]; then where="here"
    elif [[ -f $(tombstone "$w") ]]; then where=$(cat "$(tombstone "$w")")
    else where="settings only, not generated yet"
    fi
    printf '%s %-20s %s\n' "$mark" "$w" "$where"
  done <<< "$names"
}

cmd_use() {
  local w=${1:-} new=${2:-}
  valid_world "$w"
  [[ -z $new || $new == --new ]] || die "unknown option '$new'"
  check_startable "$w" "$new"
  if [[ ! -d $(world_dir "$w") ]]; then
    say "creating new world '$w'"
  fi
  set_active_world "$w"
  docker compose up -d >&2
  say "'$w' is starting — ./mc logs to watch"
}

cmd_start() {
  check_startable "$(active_world)"
  docker compose up -d >&2
}

cmd_restart() {
  check_startable "$(active_world)"
  docker compose up -d --force-recreate >&2
}

cmd_stop() { docker compose stop >&2; }

cmd_logs() { docker compose logs -f --tail 100; }

cmd_where() {
  running || die "server is not running"
  python3 lib/bedrock.py where "$@"
}

cmd_build() {
  running || die "server is not running"
  python3 lib/build.py run "$@"
}

cmd_undo() {
  running || die "server is not running"
  python3 lib/build.py undo
}

cmd_builds() { python3 lib/build.py list; }

cmd_cmd() {
  [[ $# -gt 0 ]] || die "usage: ./mc cmd <console command>"
  running || die "server is not running"
  docker exec "$CONTAINER" send-command "$*"
}

# Write a tarball of world $1 and print its path. Pauses saving if it's live.
make_archive() {
  local w=$1 out
  [[ -d $(world_dir "$w") ]] || die "no world named '$w' here"
  mkdir -p backups
  out="backups/$w-$(date +%Y%m%d-%H%M%S).tar.gz"
  local live=
  if running && [[ $(active_world) == "$w" ]]; then live=1; fi
  if [[ -n $live ]]; then
    docker exec "$CONTAINER" send-command save hold >&2
    sleep 2
    docker exec "$CONTAINER" send-command save query >&2
    sleep 2
  fi
  tar -czf "$out" -C data/worlds "$w" || { [[ -n $live ]] && docker exec "$CONTAINER" send-command save resume >&2; die "tar failed"; }
  if [[ -n $live ]]; then
    docker exec "$CONTAINER" send-command save resume >&2
  fi
  tar -tzf "$out" > /dev/null || die "archive $out is unreadable"
  echo "$out"
}

cmd_backup() {
  local w=${1:-$(active_world)}
  valid_world "$w"
  local out; out=$(make_archive "$w")
  say "wrote $out"
  # Keep the 10 newest snapshots of this world.
  ls -1t backups/"$w"-*.tar.gz 2>/dev/null | tail -n +11 | while read -r old; do rm -f "$old"; done
}

# --- internal steps used by push/pull (run on either side) ---------------------

# Fail unless world $1 can be received here.
cmd__can_receive() {
  local w=$1
  valid_world "$w"
  [[ ! -d $(world_dir "$w") ]] || die "world '$w' already exists on the receiving side; refusing to overwrite it"
  if is_cloud_host && ! WORLD=$w docker compose config 2>/dev/null | grep -Eq 'ALLOW_LIST_USERS: "?[^" ]'; then
    die "ALLOW_LIST_USERS is empty in worlds/defaults.env; the cloud server would admit nobody"
  fi
}

# Stop the server if $1 is live, archive it, print the archive path.
cmd__archive() {
  local w=$1
  valid_world "$w"
  if running && [[ $(active_world) == "$w" ]]; then
    say "stopping the server so '$w' is saved cleanly"
    docker compose stop >&2
  fi
  make_archive "$w"
}

cmd__restore() {
  local archive=$1 w
  # `|| true`: head exits early, and pipefail would count tar's SIGPIPE.
  w=$(tar -tzf "$archive" | head -1 | cut -d/ -f1 || true)
  valid_world "$w"
  cmd__can_receive "$w"
  mkdir -p data/worlds
  tar -xzf "$archive" -C data/worlds
  rm -f "$(tombstone "$w")"
}

cmd__drop() {
  local w=$1 dest=$2
  valid_world "$w"
  [[ -d $(world_dir "$w") ]] || die "no world named '$w' here"
  rm -rf "$(world_dir "$w")"
  echo "was moved to $dest on $(date '+%Y-%m-%d %H:%M')" > "$(tombstone "$w")"
}

# --- cloud plumbing ------------------------------------------------------------

cloud_host() {
  if [[ -n ${MC_HOST:-} ]]; then echo "$MC_HOST"; return; fi
  if [[ -s .cloud-host ]]; then cat .cloud-host; return; fi
  refresh_cloud_host
}

refresh_cloud_host() {
  local ip
  ip=$(cd infra && PULUMI_CONFIG_PASSPHRASE=${PULUMI_CONFIG_PASSPHRASE-} pulumi stack output publicIp 2>/dev/null) ||
    die "couldn't read the server address from Pulumi. Run \`pulumi up\` in infra/, or set MC_HOST"
  echo "$ip" > .cloud-host
  echo "$ip"
}

rsh() { ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$(cloud_host)" "$@"; }

# Run ./mc on the cloud server with the given arguments. Interactive commands
# get a TTY so ctrl-c reaches the remote process.
remote_mc() {
  local tty=()
  [[ ${1:-} == logs && -t 0 ]] && tty=(-t)
  rsh "${tty[@]}" "cd $REMOTE_DIR && ./mc $(printf '%q ' "$@")"
}

sync_config() {
  local h; h=$(cloud_host)
  rsync -az -e "ssh ${SSH_OPTS[*]}" compose.yaml compose.cloud.yaml mc "$CONFIG" "$REMOTE_USER@$h:$REMOTE_DIR/"
  rsync -az --delete --exclude __pycache__ -e "ssh ${SSH_OPTS[*]}" lib/ "$REMOTE_USER@$h:$REMOTE_DIR/lib/"
  rsync -az --delete --exclude __pycache__ -e "ssh ${SSH_OPTS[*]}" builds/ "$REMOTE_USER@$h:$REMOTE_DIR/builds/"
  rsync -az --delete -e "ssh ${SSH_OPTS[*]}" worlds/ "$REMOTE_USER@$h:$REMOTE_DIR/worlds/"
  # Same identity key in both places, so players aren't asked to re-trust.
  rsync -az -e "ssh ${SSH_OPTS[*]}" keys/ "$REMOTE_USER@$h:$REMOTE_DIR/keys/"
}

cmd_cloud() {
  local sub=${1:-}
  case $sub in
    deploy)
      # Without it the redeployed server would refuse to start.
      eula_accepted || die "accept Mojang's EULA in ./mc setup before deploying"
      local h; h=$(refresh_cloud_host)
      say "waiting for $h to finish first-boot setup"
      rsh 'cloud-init status --wait > /dev/null; docker compose version > /dev/null' ||
        die "docker isn't ready on $h; check /var/log/cloud-init-output.log there"
      sync_config
      rsh "cd $REMOTE_DIR && touch .env &&
           { grep -q '^WORLD=' .env || echo 'WORLD=world' >> .env; } &&
           { grep -q '^COMPOSE_FILE=' .env || echo 'COMPOSE_FILE=compose.yaml:compose.cloud.yaml' >> .env; } &&
           sed -i '/^PUBLIC_IP=/d' .env && echo 'PUBLIC_IP=$h' >> .env"
      if rsh "docker inspect -f '{{.State.Running}}' $CONTAINER 2>/dev/null" | grep -q true; then
        # `up -d` recreates the container only if its config changed, so a
        # deploy that just updates scripts doesn't kick players off.
        remote_mc start
      fi
      say "cloud server ready at $h. Move a world there with ./mc push <world>"
      ;;
    ssh) exec ssh "${SSH_OPTS[@]}" -t "$REMOTE_USER@$(cloud_host)" "cd $REMOTE_DIR && exec \$SHELL -l" ;;
    ip) cloud_host ;;
    *) die "usage: ./mc cloud deploy|ssh|ip" ;;
  esac
}

dns_configured() { [[ -n ${DNS_NAME:-} && -n ${DNS_ZONE:-} && -n ${DNS_PROJECT:-} ]]; }

dns_fqdn() { echo "${DNS_NAME%.}."; }

home_ip() { sed -n 's/^PUBLIC_IP=//p' .env 2>/dev/null | tail -1; }

dns_current() {
  gcloud dns record-sets describe "$(dns_fqdn)" --type=A --zone="$DNS_ZONE" \
    --project="$DNS_PROJECT" --format='value(rrdatas[0])' 2>/dev/null || true
}

cmd_dns() {
  dns_configured || die "no DNS name set up; add one with ./mc setup"
  local target=${1:-show} ip current
  current=$(dns_current)
  case $target in
    show)
      local where="not set"
      if [[ $current == "$(home_ip)" ]]; then where="home"
      elif [[ -n $current && $current == "$(cloud_host 2>/dev/null || true)" ]]; then where="cloud"
      elif [[ -n $current ]]; then where="unknown address"
      fi
      echo "${DNS_NAME%.} -> ${current:-(no record)} ($where)"
      return ;;
    cloud) ip=$(refresh_cloud_host) ;;
    home) ip=$(home_ip); [[ -n $ip ]] || die "no PUBLIC_IP in .env; run ./mc setup" ;;
    *) die "usage: ./mc dns [cloud|home]" ;;
  esac

  if [[ $current == "$ip" ]]; then
    say "${DNS_NAME%.} already points at $ip"
    return
  fi
  local verb=update
  [[ -n $current ]] || verb=create
  gcloud dns record-sets "$verb" "$(dns_fqdn)" --type=A --ttl="$DNS_TTL" --rrdatas="$ip" \
    --zone="$DNS_ZONE" --project="$DNS_PROJECT" > /dev/null
  say "${DNS_NAME%.} -> $ip ($target). Devices pick it up within ~$((DNS_TTL / 60)) minutes"
}

# After a move, say so if DNS still points at the other side.
dns_hint() {
  dns_configured || return 0
  local side=$1 want current
  if [[ $side == home ]]; then want=$(home_ip); else want=$(cloud_host); fi
  current=$(dns_current)
  [[ $current == "$want" ]] || say "${DNS_NAME%.} points at ${current:-nothing}; run ./mc dns $side to send players here"
}

cmd_push() {
  local w=${1:-}
  valid_world "$w"
  [[ -d $(world_dir "$w") ]] || die "no world named '$w' here"
  local h; h=$(cloud_host)
  sync_config
  remote_mc _can_receive "$w"

  local archive; archive=$(cmd__archive "$w")
  say "uploading $archive to $h"
  scp "${SSH_OPTS[@]}" -q "$archive" "$REMOTE_USER@$h:$REMOTE_DIR/backups/"
  remote_mc _restore "backups/$(basename "$archive")"
  remote_mc use "$w"
  cmd__drop "$w" cloud
  say "'$w' now lives in the cloud (local copy kept in $archive)"
  dns_hint cloud
}

cmd_pull() {
  local w=${1:-}
  valid_world "$w"
  cmd__can_receive "$w"
  local h; h=$(cloud_host)

  local remote_archive; remote_archive=$(remote_mc _archive "$w" | tail -1)
  say "downloading $remote_archive from $h"
  mkdir -p backups
  scp "${SSH_OPTS[@]}" -q "$REMOTE_USER@$h:$REMOTE_DIR/$remote_archive" backups/
  cmd__restore "backups/$(basename "$remote_archive")"
  remote_mc _drop "$w" home
  cmd_use "$w"
  say "'$w' now lives here (cloud copy kept in $remote_archive on the server)"
  dns_hint home
}

# --- dispatch --------------------------------------------------------------------

main() {
  load_config
  case ${1:-help} in
    help|-h|--help|setup) ;;
    *) [[ -f $CONFIG ]] || die "no $CONFIG yet; run ./mc setup first" ;;
  esac

  if [[ ${1:-} == --cloud ]]; then
    shift
    case ${1:-} in
      push|pull|cloud|dns) die "'$1' already talks to the cloud; drop --cloud" ;;
      ''|help|-h|--help) usage; return ;;
    esac
    sync_config
    remote_mc "$@"
    return
  fi

  local cmd=${1:-help}
  shift || true
  case $cmd in
    setup|status|worlds|use|start|stop|restart|logs|cmd|where|build|undo|builds|backup|push|pull|cloud|dns) "cmd_$cmd" "$@" ;;
    _can_receive|_archive|_restore|_drop) "cmd_$cmd" "$@" ;;
    help|-h|--help) usage ;;
    *) usage >&2; exit 1 ;;
  esac
}

main "$@"
