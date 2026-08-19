from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import pickle
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DEFAULT_INPUT_AND_RESULT_ROOT = SCRIPT_DIR
DEFAULT_PROCESSED_DIRS = [
    DEFAULT_INPUT_AND_RESULT_ROOT / "processed_bds_in_DENI03403000SEC5101",
    DEFAULT_INPUT_AND_RESULT_ROOT / "processed_bds_in_DENI03403000SEC4580",
]
DEFAULT_COMBINATION_CONFIG = SCRIPT_DIR / "centralized_k_combinations_by_ueu.json"
DEFAULT_COMBINATION_CONFIGS = {
    "processed_bds_in_DENI03403000SEC4580": {
        "heat_grid_length": 2723.29,
        "sfh_k": [1, 2, 4, 6, 8, 10, "reference"],
        "mfh_k": [1, 2, 3, 4, 6, 10, "reference"],
    },
    "processed_bds_in_DENI03403000SEC5101": {
        "heat_grid_length": 890.35,
        "sfh_k": [1, 2, "reference"],
        "mfh_k": [1, 2, 3, 4, 6, 10, 14, 18, "reference"],
    },
    "processed_bds_in_DENI03403000SEC5658": {
        "heat_grid_length": 1146.15,
        "sfh_k": [1, 2, 4, 6, 8, 10, 14, 18, "reference"],
        "mfh_k": [1, 2, 3, 4, 5, 6, "reference"],
    },
}
DEFAULT_STATUS_DIRNAME = "_centralized_serial_peak_subset_status"
DEFAULT_TEMP = 50
DEFAULT_SCENARIO_MODE = "capex_min_only"
DEFAULT_RUN_CONFIGS = [
    (50, "capex_min_only"),
    (80, "capex_max_only"),
]
DEFAULT_CO2_FACTORS = [1.0, 0.85]
DEFAULT_PEAK_FACTORS = [1.0, 0.65,0.2]
DEFAULT_SOLVER = "gurobi"
DEFAULT_SOLVER_THREADS = 0


def _load_centralized_module():
    module_path = SCRIPT_DIR / "centralized_supply_multiple_buildings_multiple_heat_carrier_levels.py"
    spec = importlib.util.spec_from_file_location("centralized_supply_runtime", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import centralized module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CEN = _load_centralized_module()


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


def _parse_float_list(raw: str) -> list[float]:
    return [float(token.strip()) for token in str(raw).split(",") if token.strip()]


def _parse_path_list(raw: str) -> list[Path]:
    paths = [Path(token.strip()) for token in str(raw).split(";") if token.strip()]
    if not paths:
        raise ValueError("At least one processed directory is required.")
    return paths


def _resolve_input_processed_dir(path: Path, input_root: Path | None) -> Path:
    if path.is_absolute():
        return path.resolve()
    if input_root is not None:
        return (input_root / path).resolve()
    return path.resolve()


def _derive_output_processed_dir(
    input_processed_dir: Path,
    *,
    output_dir: Path | None,
    output_ueu_name: str | None,
    output_suffix: str,
    result_storage_root: Path | None,
) -> Path:
    if output_dir is not None:
        return output_dir.resolve()

    output_root = result_storage_root.resolve() if result_storage_root is not None else input_processed_dir.parent
    output_name = output_ueu_name.strip() if output_ueu_name else f"{input_processed_dir.name}{output_suffix}"
    return (output_root / output_name).resolve()


def _normalize_scenario_mode(raw: str) -> str:
    aliases = {
        "capex_min": "capex_min_only",
        "cmin": "capex_min_only",
        "capex_max": "capex_max_only",
        "cmax": "capex_max_only",
    }
    scenario_mode = str(raw).strip()
    return aliases.get(scenario_mode, scenario_mode)


def _parse_run_configs(raw: str) -> list[tuple[int, str]]:
    run_configs = []
    for token in str(raw).split(";"):
        token = token.strip()
        if not token:
            continue
        try:
            temp_raw, scenario_mode = token.split(":", maxsplit=1)
        except ValueError as exc:
            raise ValueError(
                f"Invalid run config {token!r}. Expected format like "
                "'50:capex_min_only;80:capex_max_only'."
            ) from exc
        run_configs.append((int(temp_raw.strip()), _normalize_scenario_mode(scenario_mode)))
    if not run_configs:
        raise ValueError("At least one run config is required.")
    return run_configs


def _format_k(k_value: Any) -> str:
    return CEN._format_k_for_folder(k_value)


def _load_combination_config(path: Path, ueu_name: str) -> dict[str, Any]:
    if path.is_file():
        with open(_to_long_path(path), "r", encoding="utf-8") as fh:
            config = json.load(fh)
    else:
        print(f"combination config not found, using built-in defaults: {path}", flush=True)
        config = DEFAULT_COMBINATION_CONFIGS
    if ueu_name not in config:
        raise KeyError(f"{ueu_name} not found in {path}")
    return config[ueu_name]


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
        / f"res_cen_t{int(temp)}_{scenario_token}_simple_co2_{CEN._co2_factor_to_suffix(co2_factor)}.pkl"
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


def _combo_complete(
    processed_dir: Path,
    sfh_k: Any,
    mfh_k: Any,
    temp: int,
    scenario_token: str,
    co2_factors: list[float],
    peak_factors: list[float],
) -> bool:
    return all(
        _simple_file_has_peak_entries(
            _simple_file_path(processed_dir, sfh_k, mfh_k, temp, scenario_token, co2_factor),
            co2_factor,
            peak_factors,
        )
        for co2_factor in co2_factors
    )


def _combo_complete_for_scenarios(
    processed_dir: Path,
    sfh_k: Any,
    mfh_k: Any,
    temp: int,
    scenario_tokens: list[str],
    co2_factors: list[float],
    peak_factors: list[float],
) -> bool:
    return all(
        _combo_complete(
            processed_dir,
            sfh_k,
            mfh_k,
            temp,
            scenario_token,
            co2_factors,
            peak_factors,
        )
        for scenario_token in scenario_tokens
    )


def _missing_simple_co2_by_scenario_for_combo(
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
                _simple_file_path(
                    processed_dir,
                    sfh_k,
                    mfh_k,
                    temp,
                    scenario_token,
                    co2_factor,
                ),
                co2_factor,
                peak_factors,
            )
        ]
        if missing:
            missing_by_scenario[scenario_token] = missing
    return missing_by_scenario


def _write_status_row(path: Path, row: dict[str, Any]) -> None:
    _mkdir(path.parent)
    exists = path.is_file()
    columns = [
        "timestamp",
        "status",
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
    processed_dir: Path,
    ueu_name: str,
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
        "ueu": ueu_name,
        "temp": temp,
        "scenario_mode": scenario_mode,
        "sfh_k": _format_k(sfh_k),
        "mfh_k": _format_k(mfh_k),
        "co2_factors": ",".join(str(x) for x in co2_factors),
        "peak_factors": ",".join(str(x) for x in peak_factors),
        "output_dir": str(output_dir),
        "message": message,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run centralized combined-cluster jobs serially for a small "
            "CO2/peak subset, with one unrestricted Gurobi solve at a time. "
            "Defaults target SEC5101 and SEC4580 below this script's "
            "03_applied_energy_optimization folder."
        )
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=None,
        help="Optional single processed directory override.",
    )
    parser.add_argument(
        "--processed-dirs",
        type=str,
        default=";".join(str(path) for path in DEFAULT_PROCESSED_DIRS),
        help="Semicolon-separated processed directories, run in this order.",
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        default=None,
        help="Base directory containing input processed UEU folders. Relative processed dirs are resolved below this.",
    )
    parser.add_argument(
        "--result-storage-root",
        type=Path,
        default=None,
        help="Base directory where output processed UEU folders are written. Default: input processed dir parent.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Single output processed UEU folder. Only valid with one input processed dir.",
    )
    parser.add_argument(
        "--output-ueu-name",
        type=str,
        default=None,
        help="Output UEU folder name below --result-storage-root, e.g. processed_bds_in_DENI03403000SEC5658_time.",
    )
    parser.add_argument(
        "--output-suffix",
        type=str,
        default="",
        help="Suffix appended to the input UEU folder name for output, e.g. _time.",
    )
    parser.add_argument("--combination-config", type=Path, default=DEFAULT_COMBINATION_CONFIG)
    parser.add_argument("--temp", type=int, default=DEFAULT_TEMP)
    parser.add_argument("--scenario-mode", type=str, default=DEFAULT_SCENARIO_MODE)
    parser.add_argument(
        "--run-configs",
        type=str,
        default=";".join(f"{temp}:{scenario}" for temp, scenario in DEFAULT_RUN_CONFIGS),
        help=(
            "Semicolon-separated runs in execution order, e.g. "
            "'50:capex_min_only;80:capex_max_only'."
        ),
    )
    parser.add_argument("--co2-factors", type=str, default=",".join(str(x) for x in DEFAULT_CO2_FACTORS))
    parser.add_argument("--peak-factors", type=str, default=",".join(str(x) for x in DEFAULT_PEAK_FACTORS))
    parser.add_argument("--solver", type=str, default=DEFAULT_SOLVER)
    parser.add_argument(
        "--solver-threads",
        type=int,
        default=DEFAULT_SOLVER_THREADS,
        help="Use 0 for Gurobi automatic thread choice.",
    )
    parser.add_argument("--price-scenario", type=str, default="ref")
    parser.add_argument("--max-combos", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _run_config(
    args: argparse.Namespace,
    input_processed_dir: Path,
    output_processed_dir: Path,
    input_root: Path,
    output_root: Path,
    input_ueu_name: str,
    output_ueu_name: str,
    heat_grid_length: float,
    sfh_values: list[Any],
    mfh_values: list[Any],
    temp: int,
    scenario_mode: str,
) -> None:
    co2_factors = _parse_float_list(args.co2_factors)
    peak_factors = _parse_float_list(args.peak_factors)
    scenario_tokens = CEN._expected_scenario_tokens_for_mode(scenario_mode, temp)
    if scenario_tokens is None:
        raise ValueError(
            f"Cannot pre-check scenario_mode={scenario_mode}, temp={temp}. "
            "Use a specific scenario mode such as capex_min_only or capex_max_only."
        )
    if not scenario_tokens:
        print(f"skip run temp={temp} scenario_mode={scenario_mode}: no expected scenarios")
        return

    status_dir = output_processed_dir / DEFAULT_STATUS_DIRNAME
    status_csv = status_dir / "run_status.csv"
    error_dir = status_dir / "errors"
    _mkdir(status_dir)

    CEN.INPUT_ROOT = str(input_root)
    CEN.RESULT_STORAGE_ROOT = str(output_root)
    CEN.SOLVER = str(args.solver)
    CEN.SOLVER_THREADS = int(args.solver_threads)

    combos = [(sfh_k, mfh_k) for sfh_k in sfh_values for mfh_k in mfh_values]
    if args.max_combos is not None:
        combos = combos[: args.max_combos]

    print(f"input_processed_dir={input_processed_dir}")
    print(f"output_processed_dir={output_processed_dir}")
    print(f"input_ueu={input_ueu_name}")
    print(f"output_ueu={output_ueu_name}")
    print(f"input_root={CEN.INPUT_ROOT}")
    print(f"result_storage_root={CEN.RESULT_STORAGE_ROOT}")
    print(f"combinations={len(combos)}")
    print(f"temp={temp} scenario_mode={scenario_mode} scenarios={scenario_tokens} co2={co2_factors} peak={peak_factors}")
    print(f"solver={CEN.SOLVER} solver_threads={CEN.SOLVER_THREADS}")
    if args.dry_run:
        print("dry_run=true")

    for index, (sfh_k, mfh_k) in enumerate(combos, start=1):
        label = f"{index}/{len(combos)} sfh={_format_k(sfh_k)} mfh={_format_k(mfh_k)}"
        missing_simple_co2_by_scenario = {
            scenario_token: co2_factors for scenario_token in scenario_tokens
        }
        if not args.overwrite:
            missing_simple_co2_by_scenario = _missing_simple_co2_by_scenario_for_combo(
                output_processed_dir,
                sfh_k,
                mfh_k,
                temp,
                scenario_tokens,
                co2_factors,
                peak_factors,
            )

        if not missing_simple_co2_by_scenario:
            print(f"skip complete {label}")
            _write_status_row(
                status_csv,
                _status_row(
                    "skipped_complete",
                    output_processed_dir,
                    output_ueu_name,
                    temp,
                    scenario_mode,
                    sfh_k,
                    mfh_k,
                    co2_factors,
                    peak_factors,
                ),
            )
            continue

        missing_text = "; ".join(
            f"{scenario_token}={','.join(str(x) for x in missing_co2)}"
            for scenario_token, missing_co2 in missing_simple_co2_by_scenario.items()
        )
        print(f"start {label} missing_simple_co2={missing_text}", flush=True)
        _write_status_row(
            status_csv,
            _status_row(
                "dry_run_planned" if args.dry_run else "start",
                output_processed_dir,
                output_ueu_name,
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
            continue

        try:
            CEN.run_main(
                heat_grid_temperature=temp,
                ueu=input_ueu_name,
                heat_grid_length=heat_grid_length,
                sfh_k_value=sfh_k,
                mfh_k_value=mfh_k,
                scenario_mode=scenario_mode,
                co2_reduction_factors_to_run=co2_factors,
                peak_reduction_factors_to_run=peak_factors,
                missing_simple_co2_by_scenario=missing_simple_co2_by_scenario,
                price_scenario_name=args.price_scenario,
                output_ueu=output_ueu_name,
            )
        except Exception as exc:
            _mkdir(error_dir)
            error_path = error_dir / (
                f"error_T{temp}_sfh_{_format_k(sfh_k)}_mfh_{_format_k(mfh_k)}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
            with open(_to_long_path(error_path), "w", encoding="utf-8") as fh:
                fh.write(f"combo={label}\n")
                fh.write(f"exception={repr(exc)}\n\n")
                fh.write(traceback.format_exc())
            print(f"error {label}: {error_path}", flush=True)
            _write_status_row(
                status_csv,
                _status_row(
                    "error",
                    output_processed_dir,
                    output_ueu_name,
                    temp,
                    scenario_mode,
                    sfh_k,
                    mfh_k,
                    co2_factors,
                    peak_factors,
                    message=str(error_path),
                ),
            )
            continue

        complete = _combo_complete_for_scenarios(
            output_processed_dir, sfh_k, mfh_k, temp, scenario_tokens, co2_factors, peak_factors
        )
        status = "finished_complete" if complete else "finished_incomplete"
        print(f"{status} {label}", flush=True)
        _write_status_row(
            status_csv,
            _status_row(
                status,
                output_processed_dir,
                output_ueu_name,
                temp,
                scenario_mode,
                sfh_k,
                mfh_k,
                co2_factors,
                peak_factors,
            ),
        )

    print(f"status_csv={status_csv}")


def main() -> None:
    args = parse_args()
    processed_dirs = [args.processed_dir] if args.processed_dir is not None else _parse_path_list(args.processed_dirs)
    run_configs = _parse_run_configs(args.run_configs)
    input_root = args.input_root.resolve() if args.input_root is not None else None
    result_storage_root = args.result_storage_root.resolve() if args.result_storage_root is not None else None

    if args.output_dir is not None and len(processed_dirs) != 1:
        raise SystemExit("--output-dir is only valid with exactly one input processed dir.")
    if args.output_dir is not None and (args.output_ueu_name or args.output_suffix):
        raise SystemExit("--output-dir cannot be combined with --output-ueu-name or --output-suffix.")
    if args.output_ueu_name is not None and len(processed_dirs) != 1:
        raise SystemExit("--output-ueu-name is only valid with exactly one input processed dir.")

    print(f"processed_dirs={[str(path) for path in processed_dirs]}")
    print(f"run_configs={run_configs}")
    for processed_index, processed_dir_raw in enumerate(processed_dirs, start=1):
        input_processed_dir = _resolve_input_processed_dir(processed_dir_raw, input_root)
        if not input_processed_dir.is_dir():
            raise SystemExit(f"Input processed directory not found: {input_processed_dir}")

        output_processed_dir = _derive_output_processed_dir(
            input_processed_dir,
            output_dir=args.output_dir,
            output_ueu_name=args.output_ueu_name,
            output_suffix=args.output_suffix,
            result_storage_root=result_storage_root,
        )
        input_and_result_root = input_processed_dir.parent
        output_root = output_processed_dir.parent
        input_ueu_name = input_processed_dir.name
        output_ueu_name = output_processed_dir.name

        config = _load_combination_config(args.combination_config, input_ueu_name)
        heat_grid_length = float(config["heat_grid_length"])
        sfh_values = config["sfh_k"]
        mfh_values = config["mfh_k"]

        print(f"\nprocessed_dir {processed_index}/{len(processed_dirs)} {input_processed_dir}")
        print(f"output_dir {output_processed_dir}")
        for run_index, (temp, scenario_mode) in enumerate(run_configs, start=1):
            print(f"\nrun_config {run_index}/{len(run_configs)} temp={temp} scenario_mode={scenario_mode}")
            _run_config(
                args,
                input_processed_dir,
                output_processed_dir,
                input_and_result_root,
                output_root,
                input_ueu_name,
                output_ueu_name,
                heat_grid_length,
                sfh_values,
                mfh_values,
                temp,
                scenario_mode,
            )


if __name__ == "__main__":
    main()
