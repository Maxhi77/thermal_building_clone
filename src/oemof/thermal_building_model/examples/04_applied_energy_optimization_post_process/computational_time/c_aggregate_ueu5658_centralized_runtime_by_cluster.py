from __future__ import annotations

import argparse
import gc
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from b_aggregate_centralized_runtime_averages import (
    iter_solution_times,
    iter_solution_times_from_pickle_ops,
    load_pickle,
    write_xlsx,
)


SCRIPT_DIR = Path(__file__).resolve().parent
ARCHIVE_UEU_ROOT = (
    Path("M:/04_ArchivMA/Hillen Maximilian")
    / ("Ver" + chr(0x00F6) + "ffentlichungen")
    / "UEU"
)
UEU_CASE = "processed_bds_in_DENI03403000SEC5658"
DEFAULT_INPUT_ROOT = ARCHIVE_UEU_ROOT / UEU_CASE
DEFAULT_OUTPUT = SCRIPT_DIR / "centralized_runtime_by_cluster_DENI03403000SEC5658.xlsx"

RESULT_FILE_PATTERN = re.compile(
    r"^res_cen_t(?P<temperature>\d+)_(?P<constraint>cmin|cmax)_"
    r"simple_(?P<objective>[^_]+)_(?P<factor>.+)\.pkl$"
)
COMBINATION_PATTERN = re.compile(
    r"^combined_cluster_sfh_(?P<sfh_cluster>.+)_mfh_(?P<mfh_cluster>.+)$"
)
DEFAULT_TEMPERATURE_LEVELS = (50, 80)
DEFAULT_CONSTRAINTS = ("cmin", "cmax")


def parse_csv_values(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_temperature_levels(raw: str | None) -> tuple[int, ...] | None:
    values = parse_csv_values(raw)
    if not values:
        return None
    return tuple(sorted({int(value.removeprefix("t")) for value in values}))


def parse_constraints(raw: str | None) -> tuple[str, ...] | None:
    values = parse_csv_values(raw)
    if not values:
        return None
    invalid = [value for value in values if value not in DEFAULT_CONSTRAINTS]
    if invalid:
        raise ValueError(f"Only cmin and cmax are supported, got: {', '.join(invalid)}")
    return tuple(values)


def parse_combination_name(name: str) -> dict[str, str]:
    match = COMBINATION_PATTERN.match(name)
    if match is None:
        return {
            "combined_cluster_combination": name,
            "sfh_cluster": "",
            "mfh_cluster": "",
        }

    return {
        "combined_cluster_combination": name,
        "sfh_cluster": match.group("sfh_cluster"),
        "mfh_cluster": match.group("mfh_cluster"),
    }


def match_result_file(path: Path) -> dict[str, Any] | None:
    match = RESULT_FILE_PATTERN.match(path.name)
    if match is None:
        return None

    info = match.groupdict()
    info["temperature"] = int(info["temperature"])
    return info


def empty_bucket() -> dict[str, Any]:
    return {
        "time_sum_seconds": 0.0,
        "valid_solution_count": 0,
        "none_time_count": 0,
        "files_read": 0,
        "files_failed": 0,
        "result_entries_scanned": 0,
    }


def read_solution_times(path: Path, load_pickles: bool) -> Iterable[float | None]:
    if not load_pickles:
        yield from iter_solution_times_from_pickle_ops(path)
        return

    result_data = load_pickle(path)
    yield from iter_solution_times(result_data)
    del result_data
    gc.collect()


def average_seconds(time_sum_seconds: float, valid_solution_count: int) -> float | None:
    if valid_solution_count == 0:
        return None
    return time_sum_seconds / valid_solution_count


def aggregate_runtime_by_cluster(
    input_root: Path,
    combined_cluster_glob: str,
    temperature_levels: tuple[int, ...] | None,
    constraints: tuple[str, ...] | None,
    max_files: int | None,
    load_pickles: bool,
    print_progress: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    selected_temperatures = set(temperature_levels or DEFAULT_TEMPERATURE_LEVELS)
    selected_constraints = set(constraints or DEFAULT_CONSTRAINTS)
    discovered_temperatures = set(selected_temperatures)
    discovered_constraints = set(selected_constraints)

    buckets: dict[tuple[str, str, int], dict[str, Any]] = defaultdict(empty_bucket)
    file_rows: list[dict[str, Any]] = []
    processed_files = 0

    combination_dirs = [
        path
        for path in sorted(input_root.glob(combined_cluster_glob))
        if path.is_dir() and path.name.startswith("combined_cluster_")
    ]

    for combination_index, combination_dir in enumerate(combination_dirs, start=1):
        centralized_dir = combination_dir / "centralized"
        if not centralized_dir.is_dir():
            continue

        combination_info = parse_combination_name(combination_dir.name)

        for file_path in sorted(centralized_dir.glob("res_cen_t*_c*_simple_*.pkl")):
            if max_files is not None and processed_files >= max_files:
                break

            file_info = match_result_file(file_path)
            if file_info is None:
                continue

            temperature = file_info["temperature"]
            constraint = file_info["constraint"]
            if temperature not in selected_temperatures or constraint not in selected_constraints:
                continue

            discovered_temperatures.add(temperature)
            discovered_constraints.add(constraint)
            bucket_key = (combination_dir.name, constraint, temperature)
            bucket = buckets[bucket_key]
            bucket["files_read"] += 1

            file_time_sum = 0.0
            file_valid_count = 0
            file_none_count = 0
            file_entry_count = 0
            error_message = ""

            try:
                for time_value in read_solution_times(file_path, load_pickles):
                    file_entry_count += 1
                    if time_value is None:
                        file_none_count += 1
                        continue
                    numeric_value = float(time_value)
                    if not math.isfinite(numeric_value):
                        file_none_count += 1
                        continue
                    file_valid_count += 1
                    file_time_sum += numeric_value
            except Exception as exc:  # pragma: no cover - diagnostic export path
                bucket["files_failed"] += 1
                error_message = f"{type(exc).__name__}: {exc}"

            bucket["time_sum_seconds"] += file_time_sum
            bucket["valid_solution_count"] += file_valid_count
            bucket["none_time_count"] += file_none_count
            bucket["result_entries_scanned"] += file_entry_count

            file_average_seconds = average_seconds(file_time_sum, file_valid_count)
            file_rows.append(
                {
                    **combination_info,
                    "temperature_level": temperature,
                    "t_level": f"t{temperature}",
                    "constraint_type": constraint,
                    "objective": file_info["objective"],
                    "factor_token": file_info["factor"],
                    "file_name": file_path.name,
                    "valid_solution_count": file_valid_count,
                    "none_time_count": file_none_count,
                    "result_entries_scanned": file_entry_count,
                    "average_seconds_in_file": file_average_seconds,
                    "average_hours_in_file": (
                        file_average_seconds / 3600
                        if file_average_seconds is not None
                        else None
                    ),
                    "error": error_message,
                }
            )
            processed_files += 1

        if print_progress:
            print(
                f"processed_combination={combination_index}/{len(combination_dirs)} "
                f"name={combination_dir.name} files_total={processed_files}",
                flush=True,
            )

        if max_files is not None and processed_files >= max_files:
            break

    summary_rows: list[dict[str, Any]] = []
    for combination_dir in combination_dirs:
        combination_info = parse_combination_name(combination_dir.name)
        for constraint in sorted(discovered_constraints):
            for temperature in sorted(discovered_temperatures):
                bucket = buckets[(combination_dir.name, constraint, temperature)]
                avg_seconds = average_seconds(
                    bucket["time_sum_seconds"],
                    bucket["valid_solution_count"],
                )
                summary_rows.append(
                    {
                        **combination_info,
                        "temperature_level": temperature,
                        "t_level": f"t{temperature}",
                        "constraint_type": constraint,
                        "average_seconds": avg_seconds,
                        "average_hours": (
                            avg_seconds / 3600 if avg_seconds is not None else None
                        ),
                        "time_sum_seconds": bucket["time_sum_seconds"],
                        "valid_solution_count": bucket["valid_solution_count"],
                        "none_time_count": bucket["none_time_count"],
                        "files_read": bucket["files_read"],
                        "files_failed": bucket["files_failed"],
                        "result_entries_scanned": bucket["result_entries_scanned"],
                    }
                )

    wide_rows = make_wide_rows(
        summary_rows,
        sorted(discovered_constraints),
        sorted(discovered_temperatures),
    )
    return summary_rows, wide_rows, file_rows


def make_wide_rows(
    summary_rows: list[dict[str, Any]],
    constraints: list[str],
    temperatures: list[int],
) -> list[dict[str, Any]]:
    rows_by_combination: dict[str, dict[str, Any]] = {}
    for row in summary_rows:
        combination = row["combined_cluster_combination"]
        wide_row = rows_by_combination.setdefault(
            combination,
            {
                "combined_cluster_combination": combination,
                "sfh_cluster": row["sfh_cluster"],
                "mfh_cluster": row["mfh_cluster"],
            },
        )
        prefix = f"{row['constraint_type']}_t{row['temperature_level']}"
        wide_row[f"{prefix}_average_seconds"] = row["average_seconds"]
        wide_row[f"{prefix}_average_hours"] = row["average_hours"]
        wide_row[f"{prefix}_valid_solution_count"] = row["valid_solution_count"]
        wide_row[f"{prefix}_files_read"] = row["files_read"]

    columns = ["combined_cluster_combination", "sfh_cluster", "mfh_cluster"]
    for constraint in constraints:
        for temperature in temperatures:
            prefix = f"{constraint}_t{temperature}"
            columns.extend(
                [
                    f"{prefix}_average_seconds",
                    f"{prefix}_average_hours",
                    f"{prefix}_valid_solution_count",
                    f"{prefix}_files_read",
                ]
            )

    return [
        {column: row.get(column) for column in columns}
        for row in rows_by_combination.values()
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate average runtimes from UEU 5658 centralized simple result files "
            "by sfh/mfh cluster combination, temperature level, and cmin/cmax strategy."
        )
    )
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--combined-cluster-glob", default="combined_cluster_*")
    parser.add_argument(
        "--temperature-levels",
        default=None,
        help="Comma-separated levels, e.g. 50,80. Default: 50,80.",
    )
    parser.add_argument(
        "--constraints",
        default=None,
        help="Comma-separated strategies, e.g. cmin,cmax. Default: cmin,cmax.",
    )
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument(
        "--load-pickles",
        action="store_true",
        help="Fully unpickle files instead of scanning only time values.",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    summary_rows, wide_rows, file_rows = aggregate_runtime_by_cluster(
        input_root=args.input_root,
        combined_cluster_glob=args.combined_cluster_glob,
        temperature_levels=parse_temperature_levels(args.temperature_levels),
        constraints=parse_constraints(args.constraints),
        max_files=args.max_files,
        load_pickles=args.load_pickles,
        print_progress=not args.quiet,
    )

    write_xlsx(
        args.output,
        {
            "summary_wide": wide_rows,
            "summary_long": summary_rows,
            "file_details": file_rows,
        },
    )

    total_files = sum(row["files_read"] for row in summary_rows)
    total_failed_files = sum(row["files_failed"] for row in summary_rows)
    total_valid_times = sum(row["valid_solution_count"] for row in summary_rows)
    print(f"input_root={args.input_root}")
    print(f"output={args.output}")
    print(f"combined_cluster_combinations={len(wide_rows)}")
    print(f"summary_rows={len(summary_rows)}")
    print(f"simple_files_read={total_files}")
    print(f"valid_solution_times={total_valid_times}")
    print(f"failed_files={total_failed_files}")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
