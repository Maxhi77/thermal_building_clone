#!/usr/bin/env bash
set -uo pipefail

# Stop local centralized runs started by run_centralized.sh.
# The matcher is intentionally narrow: only Python commands containing PY_SCRIPT are stopped.
PY_SCRIPT="${PY_SCRIPT:-centralized_supply_multiple_buildings_multiple_heat_carrier_levels.py}"
DRY_RUN=false
FORCE=false

usage() {
  cat <<EOF
Usage: $0 [--dry-run] [--force]

Options:
  --dry-run          Show matching local processes without stopping them.
  --force           Send SIGKILL to processes still alive after SIGTERM.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --force)
      FORCE=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

pids=()
while read -r pid comm cmd; do
  if [[ -z "${pid:-}" || -z "${comm:-}" || -z "${cmd:-}" ]]; then
    continue
  fi
  if [[ "$comm" == python* && "$cmd" == *"$PY_SCRIPT"* ]]; then
    pids+=("$pid")
  fi
done < <(ps -u "$USER" -o pid= -o comm= -o args=)

echo "Stopping local centralized runs: script=$PY_SCRIPT dry_run=$DRY_RUN force=$FORCE"

if [[ ${#pids[@]} -eq 0 ]]; then
  echo "No matching local centralized Python runs found."
  exit 0
fi

echo "Matching local centralized Python runs:"
ps -o pid,etimes,cmd -p "$(IFS=,; echo "${pids[*]}")"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "Dry-run only. No processes stopped."
  exit 0
fi

kill -TERM "${pids[@]}"
sleep 2

remaining=()
for pid in "${pids[@]}"; do
  if kill -0 "$pid" 2>/dev/null; then
    remaining+=("$pid")
  fi
done

if [[ ${#remaining[@]} -gt 0 && "$FORCE" == "true" ]]; then
  echo "Force-stopping remaining PIDs: ${remaining[*]}"
  kill -KILL "${remaining[@]}"
elif [[ ${#remaining[@]} -gt 0 ]]; then
  echo "Still running after SIGTERM: ${remaining[*]} (rerun with --force if needed)"
fi

echo "Stop command finished."
