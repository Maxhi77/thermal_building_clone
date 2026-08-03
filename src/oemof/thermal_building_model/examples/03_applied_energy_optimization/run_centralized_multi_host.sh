#!/usr/bin/env bash
set -uo pipefail

# Distributed centralized SCIP runs on the fixed remote host list.
REMOTE_EXAMPLE_DIR="${REMOTE_EXAMPLE_DIR:-/home/mh/thermal_building_clone/src/oemof/thermal_building_model/examples/03_applied_energy_optimization}"
PY_SCRIPT="${PY_SCRIPT:-centralized_supply_multiple_buildings_multiple_heat_carrier_levels.py}"
CONDA_SH="${CONDA_SH:-/opt/mambaforge/install_dir/etc/profile.d/conda.sh}"
CONDA_ENV="${CONDA_ENV:-district_opt}"
REMOTE_LOG_DIR="${REMOTE_LOG_DIR:-/home/mh}"

# Read cluster input from the clone's example directory on each host.
INPUT_ROOT="${INPUT_ROOT:-$REMOTE_EXAMPLE_DIR}"
# Keep result files and completion checks on the shared jump storage.
RESULT_STORAGE_ROOT="${RESULT_STORAGE_ROOT:-/jump/mh}"

SCENARIO_MODE="${SCENARIO_MODE:-capex_min_max_only}"   # all | capex_min_only | capex_max_only | capex_min_max_only
SOLVER="${SOLVER:-scip}"
SOLVER_THREADS="${SOLVER_THREADS:-auto}"
TEMPS="${TEMPS:-50,80}"
UEU_CASES="${UEU_CASES:-processed_bds_in_DENI03403000SEC5658:1146.15}"
CO2_FACTORS="${CO2_FACTORS:-1,0.95,0.9,0.85,0.8,0.75,0.7,0.65,0.6,0.55,0.5,0.45,0.4,0.35,0.3,0.25,0.2,0.15,0.1,0.05,0.01,-0.01,-0.05,-0.1,-0.2}"

# Per-host settings. Keep arrays the same length.
HOSTS=(idefix obelix verleihnix methusalix gutemine falbala)
WORKERS_PER_HOST=(30 40 16 60 110 140)

# Requested k values per host (use "reference", not "ref").
SFH_K_PER_HOST=(
  "1,2"
  "4,6"
  "8,10"
  "14"
  "18"
  "reference"
)
MFH_K_PER_HOST=(
  "1,2,3,4,5,6,reference"
  "1,2,3,4,5,6,reference"
  "1,2,3,4,5,6,reference"
  "1,2,3,4,5,6,reference"
  "1,2,3,4,5,6,reference"
  "1,2,3,4,5,6,reference"
)

if [[ ${#HOSTS[@]} -ne ${#WORKERS_PER_HOST[@]} || ${#HOSTS[@]} -ne ${#SFH_K_PER_HOST[@]} || ${#HOSTS[@]} -ne ${#MFH_K_PER_HOST[@]} ]]; then
  echo "HOSTS, WORKERS_PER_HOST, SFH_K_PER_HOST and MFH_K_PER_HOST must have equal length."
  exit 1
fi

successful_hosts=()
failed_hosts=()

for idx in "${!HOSTS[@]}"; do
  host="${HOSTS[$idx]}"
  workers="${WORKERS_PER_HOST[$idx]}"
  sfh_k="${SFH_K_PER_HOST[$idx]}"
  mfh_k="${MFH_K_PER_HOST[$idx]}"

  out_log="${REMOTE_LOG_DIR}/centralized_5658_${host}.out"
  err_log="${REMOTE_LOG_DIR}/centralized_5658_${host}_error.log"

  remote_cmd=$(
    cat <<EOF
set -e
cd "$REMOTE_EXAMPLE_DIR"
source "$CONDA_SH"
conda activate "$CONDA_ENV"

nohup python "$PY_SCRIPT" \
  --host-name "$host" \
  --workers "$workers" \
  --solver "$SOLVER" \
  --solver-threads "$SOLVER_THREADS" \
  --scenario-mode "$SCENARIO_MODE" \
  --temps "$TEMPS" \
  --sfh-k "$sfh_k" \
  --mfh-k "$mfh_k" \
  --ueu-cases "$UEU_CASES" \
  --co2-factors "$CO2_FACTORS" \
  --input-root "$INPUT_ROOT" \
  --result-storage-root "$RESULT_STORAGE_ROOT" \
  > "$out_log" 2> "$err_log" &
echo Started PID: \$!
EOF
  )

  echo "Launching on $host: workers=$workers solver=$SOLVER solver_threads=$SOLVER_THREADS sfh_k=$sfh_k mfh_k=$mfh_k scenario_mode=$SCENARIO_MODE temps=$TEMPS ueu=$UEU_CASES input_root=$INPUT_ROOT result_storage_root=$RESULT_STORAGE_ROOT"
  if ssh "$host" "bash -lc '$remote_cmd'"; then
    successful_hosts+=("$host")
  else
    failed_hosts+=("$host")
    echo "Launch failed on $host (continuing with remaining hosts)." >&2
  fi
done

echo "Submitted on ${#successful_hosts[@]} host(s): ${successful_hosts[*]:-none}"
if [[ ${#failed_hosts[@]} -gt 0 ]]; then
  echo "Failed on ${#failed_hosts[@]} host(s): ${failed_hosts[*]}" >&2
  exit 1
fi

echo "All remote runs submitted."
