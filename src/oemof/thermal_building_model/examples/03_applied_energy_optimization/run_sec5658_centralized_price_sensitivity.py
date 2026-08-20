from __future__ import annotations

import argparse
import csv
import importlib.util
import multiprocessing as mp
import os
import pickle
import sys
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from oemof.thermal_building_model.helpers.price_scenarios import (
    DEFAULT_PRICE_SCENARIOS,
    normalize_price_scenario_name,
    parse_price_scenarios,
    scenario_output_cluster_name,
)

DEFAULT_INPUT_AND_RESULT_ROOT = SCRIPT_DIR
DEFAULT_UEU_NAME = "processed_bds_in_DENI03403000SEC5658"
DEFAULT_PROCESSED_DIR = DEFAULT_INPUT_AND_RESULT_ROOT / DEFAULT_UEU_NAME
DEFAULT_HEAT_GRID_LENGTH = 1146.15
DEFAULT_SFH_K = "reference"
DEFAULT_MFH_K = "reference"
DEFAULT_STATUS_DIRNAME = "_centralized_price_sensitivity_status"
DEFAULT_SOLVER = "gurobi"
DEFAULT_SOLVER_THREADS = "auto"
RUN_CONFIGS = [
    {
        "temp": 50,
        "scenario_mode": "capex_min_only",
        "co2_factors": [0.65, 0.6, 0.55, 0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2],
        "peak_factors": [1.0],
    },
    {
        "temp": 80,
        "scenario_mode": "capex_min_only",
        "co2_factors": [1.0],
        "peak_factors": [1.0],
    },
    {
        "temp": 80,
        "scenario_mode": "capex_max_only",
        "co2_factors": [1.0],
        "peak_factors": [0.5, 0.4, 0.3, 0.2, 0.1, 0.05, 0.01],
    },
]


CEN = None


def _load_centralized_module():
    module_path = SCRIPT_DIR / "centralized_supply_multiple_buildings_multiple_heat_carrier_levels.py"
    spec = importlib.util.spec_from_file_location("centralized_supply_runtime", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import centralized module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _to_long_path(path: Path) -> str:
    resolved = path.resolve()
    path_str = str(resolved)
    if os.name != "nt":
        return path_str
    if path_str.startswith("\\\\?\\"):
        return path_str
    if path_str.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path_str[2:]
    return "\\\\?\\" + path_str


def _mkdir(path: Path) -> None:
    Path(_to_long_path(path)).mkdir(parents=True, exist_ok=True)


@contextmanager
def _job_file_lock(lock_path: Path, poll_seconds: float = 5.0):
    _mkdir(lock_path.parent)
    lock_name = _to_long_path(lock_path)
    while True:
        try:
            fd = os.open(lock_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(f"pid={os.getpid()}\n")
                fh.write(f"created={datetime.now().isoformat(timespec='seconds')}\n")
            break
        except FileExistsError:
            print(f"waiting for job lock: {lock_path}", flush=True)
            time.sleep(poll_seconds)
    try:
        yield
    finally:
        try:
            os.remove(lock_name)
        except FileNotFoundError:
            pass


def _format_k(k_value: Any) -> str:
    if isinstance(k_value, str) and k_value.lower() == "reference":
        return "reference"
    return f"k{int(k_value):02d}"


def _expected_scenario_tokens_for_mode(scenario_mode: str, heat_grid_temperature: int | None = None) -> list[str] | None:
    if scenario_mode == "capex_min_only":
        return ["cmin"]
    if scenario_mode == "capex_max_only":
        if heat_grid_temperature is not None and int(heat_grid_temperature) == 50:
            return []
        return ["cmax"]
    if scenario_mode in {"capex_min_max_only", "cmin_cmax_only"}:
        if heat_grid_temperature is not None and int(heat_grid_temperature) == 50:
            return ["cmin"]
        return ["cmin", "cmax"]
    return None


def _co2_factor_to_suffix(factor: float) -> str:
    value = float(factor)
    if value.is_integer():
        return str(int(value))
    suffix = f"{value:.6f}".rstrip("0").rstrip(".")
    if suffix.startswith("-0."):
        return "m0" + suffix[3:]
    if suffix.startswith("0."):
        return "0" + suffix[2:]
    return suffix.replace(".", "")


def _actual_output_ueu_name(output_base_ueu_name: str, price_scenario: str) -> str:
    return scenario_output_cluster_name(output_base_ueu_name, price_scenario)


def _actual_output_processed_dir(output_root: Path, output_base_ueu_name: str, price_scenario: str) -> Path:
    return output_root / _actual_output_ueu_name(output_base_ueu_name, price_scenario)


def _simple_file_path(
    processed_dir: Path,
    sfh_k: Any,
    mfh_k: Any,
    temp: int,
    scenario_token: str,
    co2_factor: float,
) -> Path:
    return (
        processed_dir
        / f"combined_cluster_sfh_{_format_k(sfh_k)}_mfh_{_format_k(mfh_k)}"
        / "centralized"
        / f"res_cen_t{int(temp)}_{scenario_token}_simple_co2_{_co2_factor_to_suffix(co2_factor)}.pkl"
    )


def _simple_file_has_peak_entries(path: Path, co2_factor: float, peak_factors: list[float]) -> bool:
    if not path.is_file():
        return False
    try:
        with open(_to_long_path(path), "rb") as fh:
            payload = pickle.load(fh)
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    for peak_factor in peak_factors:
        key = (co2_factor, peak_factor, "co2")
        if key not in payload:
            return False
    return True


def _missing_simple_co2_by_scenario(
    processed_dir: Path,
    sfh_k: Any,
    mfh_k: Any,
    temp: int,
    scenario_tokens: list[str],
    co2_factors: list[float],
    peak_factors: list[float],
) -> dict[str, list[float]]:
    missing_by_scenario = {}
    for scenario_token in scenario_tokens:
        missing = [
            co2_factor
            for co2_factor in co2_factors
            if not _simple_file_has_peak_entries(
                _simple_file_path(processed_dir, sfh_k, mfh_k, temp, scenario_token, co2_factor),
                co2_factor,
                peak_factors,
            )
        ]
        if missing:
            missing_by_scenario[scenario_token] = missing
    return missing_by_scenario


def _all_complete(
    processed_dir: Path,
    sfh_k: Any,
    mfh_k: Any,
    temp: int,
    scenario_tokens: list[str],
    co2_factors: list[float],
    peak_factors: list[float],
) -> bool:
    return not _missing_simple_co2_by_scenario(
        processed_dir,
        sfh_k,
        mfh_k,
        temp,
        scenario_tokens,
        co2_factors,
        peak_factors,
    )


def _write_status_row(path: Path, row: dict[str, Any]) -> None:
    _mkdir(path.parent)
    exists = path.is_file()
    columns = [
        "timestamp",
        "status",
        "price_scenario",
        "ueu",
        "temp",
        "scenario_mode",
        "sfh_k",
        "mfh_k",
        "co2_factors",
        "peak_factors",
        "output_dir",
        "message",
    ]
    with open(_to_long_path(path), "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        if not exists:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in columns})


def _status_row(
    status: str,
    price_scenario: str,
    processed_dir: Path,
    temp: int,
    scenario_mode: str,
    sfh_k: Any,
    mfh_k: Any,
    co2_factors: list[float],
    peak_factors: list[float],
    message: str = "",
) -> dict[str, Any]:
    output_dir = (
        processed_dir
        / f"combined_cluster_sfh_{_format_k(sfh_k)}_mfh_{_format_k(mfh_k)}"
        / "centralized"
    )
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "price_scenario": price_scenario,
        "ueu": processed_dir.name,
        "temp": temp,
        "scenario_mode": scenario_mode,
        "sfh_k": _format_k(sfh_k),
        "mfh_k": _format_k(mfh_k),
        "co2_factors": ",".join(str(x) for x in co2_factors),
        "peak_factors": ",".join(str(x) for x in peak_factors),
        "output_dir": str(output_dir),
        "message": message,
    }


def _resolve_processed_dir(path: Path, input_root: Path | None) -> Path:
    if path.is_absolute():
        return path.resolve()
    if input_root is not None:
        return (input_root / path).resolve()
    return path.resolve()


def _derive_output_base_ueu_name(input_processed_dir: Path, output_ueu_name: str | None, output_suffix: str) -> str:
    if output_ueu_name:
        return output_ueu_name.strip()
    return f"{input_processed_dir.name}{output_suffix}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run centralized SEC5658 price sensitivity only for "
            "sfh_reference/mfh_reference with a reduced CO2/peak grid."
        )
    )
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument(
        "--input-root",
        type=Path,
        default=None,
        help="Base directory containing the input processed UEU folder.",
    )
    parser.add_argument(
        "--result-storage-root",
        type=Path,
        default=None,
        help="Base directory where output processed UEU folders are written.",
    )
    parser.add_argument(
        "--output-ueu-name",
        type=str,
        default=None,
        help="Base output UEU name before price-scenario suffixes.",
    )
    parser.add_argument(
        "--output-suffix",
        type=str,
        default="",
        help="Suffix appended to the input UEU name before price-scenario suffixes.",
    )
    parser.add_argument(
        "--price-scenarios",
        type=str,
        default=",".join(DEFAULT_PRICE_SCENARIOS),
        help="Comma-separated price scenarios, or 'all'.",
    )
    parser.add_argument("--heat-grid-length", type=float, default=DEFAULT_HEAT_GRID_LENGTH)
    parser.add_argument("--sfh-k", type=str, default=DEFAULT_SFH_K)
    parser.add_argument("--mfh-k", type=str, default=DEFAULT_MFH_K)
    parser.add_argument("--host-name", type=str, default="unknown")
    parser.add_argument("--job-start", type=int, default=0, help="Start index in the global job list.")
    parser.add_argument("--max-jobs", type=int, default=None, help="Maximum number of selected jobs to run.")
    parser.add_argument("--workers", type=int, default=None, help="Number of parallel worker processes.")
    parser.add_argument("--serial", action="store_true", help="Run selected jobs sequentially.")
    parser.add_argument("--solver", type=str, default=DEFAULT_SOLVER)
    parser.add_argument(
        "--solver-threads",
        type=str,
        default=DEFAULT_SOLVER_THREADS,
        help="Solver threads per job, or 'auto' to divide CPU cores by --workers.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _parse_k(raw: str) -> Any:
    value = str(raw).strip()
    if value.lower() == "reference":
        return "reference"
    return int(value)


def _resolve_solver_threads(raw_value: Any, n_cores: int, requested_workers: int | None) -> int:
    value = str(raw_value).strip().lower()
    if not value or value == "auto":
        if requested_workers is None:
            return 1
        return max(1, n_cores // max(1, int(requested_workers)))
    if value in {"0", "unlimited", "gurobi_auto"}:
        return 0
    try:
        threads = int(value)
    except Exception as exc:
        raise ValueError(
            "--solver-threads must be a positive integer, 0, 'unlimited', 'gurobi_auto', or 'auto'"
        ) from exc
    if threads < 0:
        raise ValueError("--solver-threads must be >= 0")
    return threads


def _build_jobs(
    *,
    args: argparse.Namespace,
    input_processed_dir: Path,
    output_root: Path,
    input_root: Path,
    output_base_ueu_name: str,
    price_scenarios: list[str],
    sfh_k: Any,
    mfh_k: Any,
) -> list[tuple[Any, ...]]:
    jobs = []
    for price_scenario in price_scenarios:
        normalized_price_scenario = normalize_price_scenario_name(price_scenario)
        for run_config in RUN_CONFIGS:
            jobs.append(
                (
                    args,
                    input_processed_dir,
                    output_root,
                    input_root,
                    output_base_ueu_name,
                    normalized_price_scenario,
                    sfh_k,
                    mfh_k,
                    run_config,
                )
            )
    return jobs


def _run_one_config(
    *,
    args: argparse.Namespace,
    input_processed_dir: Path,
    output_root: Path,
    input_root: Path,
    output_base_ueu_name: str,
    price_scenario: str,
    sfh_k: Any,
    mfh_k: Any,
    run_config: dict[str, Any],
) -> None:
    temp = int(run_config["temp"])
    scenario_mode = str(run_config["scenario_mode"])
    co2_factors = list(run_config["co2_factors"])
    peak_factors = list(run_config["peak_factors"])
    scenario_tokens = _expected_scenario_tokens_for_mode(scenario_mode, temp)
    if scenario_tokens is None:
        raise ValueError(f"Cannot pre-check scenario_mode={scenario_mode}, temp={temp}.")
    if not scenario_tokens:
        print(f"skip temp={temp} scenario_mode={scenario_mode}: no expected scenarios", flush=True)
        return

    actual_output_processed_dir = _actual_output_processed_dir(
        output_root,
        output_base_ueu_name,
        price_scenario,
    )
    status_dir = actual_output_processed_dir / DEFAULT_STATUS_DIRNAME
    status_csv = status_dir / "run_status.csv"
    error_dir = status_dir / "errors"
    _mkdir(status_dir)

    missing_simple_co2_by_scenario = {
        scenario_token: co2_factors for scenario_token in scenario_tokens
    }
    if not args.overwrite:
        missing_simple_co2_by_scenario = _missing_simple_co2_by_scenario(
            actual_output_processed_dir,
            sfh_k,
            mfh_k,
            temp,
            scenario_tokens,
            co2_factors,
            peak_factors,
        )

    label = (
        f"price={price_scenario} temp={temp} scenario_mode={scenario_mode} "
        f"sfh={_format_k(sfh_k)} mfh={_format_k(mfh_k)}"
    )
    if not missing_simple_co2_by_scenario:
        print(f"skip complete {label}", flush=True)
        _write_status_row(
            status_csv,
            _status_row(
                "skipped_complete",
                price_scenario,
                actual_output_processed_dir,
                temp,
                scenario_mode,
                sfh_k,
                mfh_k,
                co2_factors,
                peak_factors,
            ),
        )
        return

    missing_text = "; ".join(
        f"{scenario_token}={','.join(str(x) for x in missing_co2)}"
        for scenario_token, missing_co2 in missing_simple_co2_by_scenario.items()
    )
    print(f"start {label} missing_simple_co2={missing_text}", flush=True)
    _write_status_row(
        status_csv,
        _status_row(
            "dry_run_planned" if args.dry_run else "start",
            price_scenario,
            actual_output_processed_dir,
            temp,
            scenario_mode,
            sfh_k,
            mfh_k,
            co2_factors,
            peak_factors,
            message=f"missing_simple_co2={missing_text}",
        ),
    )
    if args.dry_run:
        return

    try:
        if CEN is None:
            raise RuntimeError("Centralized module was not loaded.")
        lock_path = status_dir / "locks" / f"T{temp}.lock"
        with _job_file_lock(lock_path):
            CEN.run_main(
                heat_grid_temperature=temp,
                ueu=input_processed_dir.name,
                heat_grid_length=float(args.heat_grid_length),
                sfh_k_value=sfh_k,
                mfh_k_value=mfh_k,
                scenario_mode=scenario_mode,
                co2_reduction_factors_to_run=co2_factors,
                peak_reduction_factors_to_run=peak_factors,
                missing_simple_co2_by_scenario=missing_simple_co2_by_scenario,
                price_scenario_name=price_scenario,
                output_ueu=output_base_ueu_name,
            )
    except Exception as exc:
        _mkdir(error_dir)
        error_path = error_dir / (
            f"error_price_{price_scenario}_T{temp}_sfh_{_format_k(sfh_k)}_"
            f"mfh_{_format_k(mfh_k)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        with open(_to_long_path(error_path), "w", encoding="utf-8") as fh:
            fh.write(f"label={label}\n")
            fh.write(f"input_root={input_root}\n")
            fh.write(f"output_root={output_root}\n")
            fh.write(f"exception={repr(exc)}\n\n")
            fh.write(traceback.format_exc())
        print(f"error {label}: {error_path}", flush=True)
        _write_status_row(
            status_csv,
            _status_row(
                "error",
                price_scenario,
                actual_output_processed_dir,
                temp,
                scenario_mode,
                sfh_k,
                mfh_k,
                co2_factors,
                peak_factors,
                message=str(error_path),
            ),
        )
        return

    complete = _all_complete(
        actual_output_processed_dir,
        sfh_k,
        mfh_k,
        temp,
        scenario_tokens,
        co2_factors,
        peak_factors,
    )
    status = "finished_complete" if complete else "finished_incomplete"
    print(f"{status} {label}", flush=True)
    _write_status_row(
        status_csv,
        _status_row(
            status,
            price_scenario,
            actual_output_processed_dir,
            temp,
            scenario_mode,
            sfh_k,
            mfh_k,
            co2_factors,
            peak_factors,
        ),
    )


def _worker(job: tuple[Any, ...]) -> None:
    global CEN
    (
        job_idx,
        host_name,
        solver,
        solver_threads,
        args,
        input_processed_dir,
        output_root,
        input_root,
        output_base_ueu_name,
        price_scenario,
        sfh_k,
        mfh_k,
        run_config,
    ) = job

    if not args.dry_run:
        CEN = _load_centralized_module()
        CEN.INPUT_ROOT = str(input_root)
        CEN.RESULT_STORAGE_ROOT = str(output_root)
        CEN.SOLVER = str(solver).strip()
        CEN.SOLVER_THREADS = int(solver_threads)

    print(
        f"host={host_name} job={job_idx} dispatch: "
        f"price={price_scenario} temp={run_config['temp']} "
        f"scenario_mode={run_config['scenario_mode']} "
        f"solver={str(solver).strip()} solver_threads={int(solver_threads)}",
        flush=True,
    )
    try:
        _run_one_config(
            args=args,
            input_processed_dir=input_processed_dir,
            output_root=output_root,
            input_root=input_root,
            output_base_ueu_name=output_base_ueu_name,
            price_scenario=price_scenario,
            sfh_k=sfh_k,
            mfh_k=mfh_k,
            run_config=run_config,
        )
    except Exception:
        print(
            f"host={host_name} job={job_idx} failed before job status logging:\n"
            f"{traceback.format_exc()}",
            flush=True,
        )


def main() -> None:
    args = parse_args()
    if args.job_start < 0:
        raise ValueError("--job-start must be >= 0")
    if args.max_jobs is not None and args.max_jobs <= 0:
        raise ValueError("--max-jobs must be > 0 when provided")
    if args.workers is not None and args.workers <= 0:
        raise ValueError("--workers must be > 0 when provided")
    if not str(args.solver).strip():
        raise ValueError("--solver must not be empty")
    if args.output_ueu_name and args.output_suffix:
        raise ValueError("--output-ueu-name and --output-suffix are mutually exclusive.")

    input_root_arg = args.input_root.resolve() if args.input_root is not None else None
    input_processed_dir = _resolve_processed_dir(args.processed_dir, input_root_arg)
    if not input_processed_dir.is_dir():
        raise SystemExit(f"Input processed directory not found: {input_processed_dir}")

    input_root = input_processed_dir.parent
    output_root = (
        args.result_storage_root.resolve()
        if args.result_storage_root is not None
        else input_processed_dir.parent
    )
    output_base_ueu_name = _derive_output_base_ueu_name(
        input_processed_dir,
        args.output_ueu_name,
        args.output_suffix,
    )
    price_scenarios = parse_price_scenarios(args.price_scenarios)
    sfh_k = _parse_k(args.sfh_k)
    mfh_k = _parse_k(args.mfh_k)

    _mkdir(output_root)
    jobs_raw = _build_jobs(
        args=args,
        input_processed_dir=input_processed_dir,
        output_root=output_root,
        input_root=input_root,
        output_base_ueu_name=output_base_ueu_name,
        price_scenarios=price_scenarios,
        sfh_k=sfh_k,
        mfh_k=mfh_k,
    )
    total_jobs = len(jobs_raw)
    if args.job_start >= total_jobs:
        print(f"No jobs for host {args.host_name}: job_start={args.job_start} >= total_jobs={total_jobs}")
        raise SystemExit(0)
    end_idx = total_jobs if args.max_jobs is None else min(total_jobs, args.job_start + args.max_jobs)
    selected_jobs_raw = jobs_raw[args.job_start:end_idx]
    if not selected_jobs_raw:
        print("No selected jobs after slicing.")
        raise SystemExit(0)

    n_cores = os.cpu_count() or 1
    solver_threads = _resolve_solver_threads(args.solver_threads, n_cores, args.workers)
    default_workers = 1 if solver_threads == 0 else max(1, n_cores // solver_threads)
    workers = args.workers if args.workers is not None else default_workers
    workers = max(1, min(workers, len(selected_jobs_raw)))
    solver = str(args.solver).strip()
    selected_jobs = [
        (args.job_start + idx, args.host_name, solver, solver_threads, *job)
        for idx, job in enumerate(selected_jobs_raw)
    ]

    print(f"input_processed_dir={input_processed_dir}")
    print(f"input_root={input_root}")
    print(f"result_storage_root={output_root}")
    print(f"output_base_ueu_name={output_base_ueu_name}")
    print(f"price_scenarios={price_scenarios}")
    print(f"sfh_k={_format_k(sfh_k)} mfh_k={_format_k(mfh_k)}")
    print(f"run_configs={RUN_CONFIGS}")
    print(
        f"host={args.host_name} total_jobs={total_jobs} "
        f"selected_range=[{args.job_start},{end_idx}) selected_jobs={len(selected_jobs)} "
        f"workers={workers} solver={solver} solver_threads={solver_threads}"
    )
    if args.dry_run:
        print("dry_run=true")

    if args.serial or workers == 1:
        for job in selected_jobs:
            _worker(job)
    else:
        with mp.Pool(processes=workers) as pool:
            pool.map(_worker, selected_jobs)


if __name__ == "__main__":
    main()
