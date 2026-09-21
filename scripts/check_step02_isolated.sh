#!/usr/bin/env bash
# Linux/WSL PR gate: prepare locked dependencies BEFORE this offline entry.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
for tool in unshare ip mount setpriv env; do
  command -v "$tool" >/dev/null
done
test -x backend/.venv/bin/python
# Do not inherit open network descriptors, proxy settings, tokens, or startup hooks.
# A new PID namespace and private /proc prevent access to host process descriptors.
exec env -i HOME="$HOME" PATH="$PATH" LANG=C.UTF-8 \
  unshare --user --map-root-user --net --mount --pid --fork --mount-proc \
  bash -eu -c '
    mount --make-rprivate /
    ip link set lo up
    if [ -f /init ] && grep -qi microsoft /proc/sys/kernel/osrelease; then
      # WSL native Windows programs bypass Linux networking. Block their interpreter
      # only in this private mount namespace; host WSL interop remains unchanged.
      mount --bind /usr/bin/false /init
    fi
    exec setpriv --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all \
      backend/.venv/bin/python -X utf8 scripts/check_step02.py --require-os-isolation
  ' </dev/null
