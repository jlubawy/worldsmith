#!/usr/bin/env bash
# Ask which design in builds/ to build, then hand it to ./mc build.
#
#   .vscode/build.sh [--cloud] -- [player] [build options]
#
# Arguments before -- go ahead of "build", the rest after the design.
set -euo pipefail
cd "$(dirname "$0")/.."

before=()
while [[ $# -gt 0 && $1 != -- ]]; do before+=("$1"); shift; done
[[ $# -gt 0 ]] && shift

# A blank prompt arrives as an empty argument; catch it before the menu.
args=("$@")
for i in "${!args[@]}"; do
  if [[ ${args[i]} == --at && -z ${args[i+1]:-} ]]; then
    echo "--at needs X,Y,Z,FACING, e.g. 6,76,-68,south" >&2
    exit 1
  fi
done

designs=()
for f in builds/*.py; do
  name=$(basename "$f" .py)
  [[ $name == _* ]] || designs+=("$name")
done

PS3="Which design? "
select design in "${designs[@]}"; do
  [[ -n $design ]] && break
done
[[ -n ${design:-} ]] || exit 1

exec ./mc ${before[@]+"${before[@]}"} build "$design" "$@"
