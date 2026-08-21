import argparse
import csv
import pickle
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

SRC_DIR = Path(__file__).resolve().parents[5]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from oemof.thermal_building_model.helpers.price_scenarios import (
    PRICE_SCENARIO_CONFIGS,
    normalize_price_scenario_name,
    parse_price_scenarios,
    scenario_output_cluster_name,
)


BASE_DIR = Path(__file__).resolve().parent
EXAMPLES_DIR = BASE_DIR.parents[1]
DEFAULT_ARCHIVE_UEU_CASE_ROOT = Path(
    r"M:\04_ArchivMA\Hillen Maximilian\Veröffentlichungen\UEU"
    r"\processed_bds_in_DENI03403000SEC5658"
)
DEFAULT_INPUT_ROOT = (
    DEFAULT_ARCHIVE_UEU_CASE_ROOT.parent
    if DEFAULT_ARCHIVE_UEU_CASE_ROOT.exists()
    else EXAMPLES_DIR / "03_applied_energy_optimization"
)
DEFAULT_UEU_CASE = "processed_bds_in_DENI03403000SEC5658"
DEFAULT_OUTPUT_ROOT = EXAMPLES_DIR / f"04_post_processed_cen_{date.today().strftime('%Y%m%d')}"

RESULT_PATTERN = re.compile(
    r"^res_cen_t(?P<temperature>\d+)_(?P<constraint>[^_]+)_"
    r"(?:(?P<simple>simple)_)?(?P<objective>[^_]+)_(?P<factor>.+)\.pkl$"
)


def _parse_csv_values(raw: Optional[str]) -> List[str]:
    if raw is None:
        return []
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _parse_temperature_levels(raw: Optional[str]) -> Optional[set[int]]:
    values = _parse_csv_values(raw)
    if not values:
        return None
    return {int(value) for value in values}


def _resolve_user_path(path: Path) -> Path:
    return Path(str(path)).expanduser().resolve()


def _looks_like_ueu_case_dir(path: Path) -> bool:
    return path.name.startswith("processed_bds_in")


def _infer_price_scenario_name(ueu_case: str, record: Optional[Dict[str, Any]] = None) -> str:
    if isinstance(record, dict) and record.get("price_scenario_name") is not None:
        return normalize_price_scenario_name(record.get("price_scenario_name"))

    for scenario_name in sorted(PRICE_SCENARIO_CONFIGS, key=len, reverse=True):
        if scenario_name == "ref":
            continue
        if str(ueu_case).endswith(f"_{scenario_name}"):
            return scenario_name
    return "ref"


def _infer_base_ueu_case(ueu_case: str) -> str:
    price_scenario_name = _infer_price_scenario_name(ueu_case)
    if price_scenario_name == "ref":
        return ueu_case
    suffix = f"_{price_scenario_name}"
    return str(ueu_case)[: -len(suffix)] if str(ueu_case).endswith(suffix) else ueu_case


def _parse_price_scenarios(raw: Optional[str]) -> List[str]:
    if raw is None:
        return []
    return parse_price_scenarios(raw)


def _resolve_input_cases(
    input_root: Path,
    ueu_cases: List[str],
    price_scenarios: List[str],
) -> List[Tuple[str, Path]]:
    if _looks_like_ueu_case_dir(input_root):
        if ueu_cases and input_root.name not in ueu_cases:
            raise ValueError(
                "When --input-root points directly to a processed_bds_in... folder, "
                "--ueu-case must be omitted or match that folder name."
            )
        return [(input_root.name, input_root)]

    if not ueu_cases:
        ueu_cases = [DEFAULT_UEU_CASE]

    resolved_cases = []
    for ueu_case in ueu_cases:
        if price_scenarios:
            for price_scenario in price_scenarios:
                output_case = scenario_output_cluster_name(ueu_case, price_scenario)
                resolved_cases.append((output_case, input_root / output_case))
        else:
            resolved_cases.append((ueu_case, input_root / ueu_case))
    return resolved_cases


def _match_result_file(path: Path) -> Optional[Dict[str, Any]]:
    match = RESULT_PATTERN.match(path.name)
    if not match:
        return None
    info = match.groupdict()
    info["temperature"] = int(info["temperature"])
    info["result_kind"] = "simple" if info.get("simple") else "full"
    info.pop("simple", None)
    return info


def _remove_series(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            key: _remove_series(value)
            for key, value in obj.items()
            if not isinstance(value, pd.Series)
        }
    if isinstance(obj, list):
        return [_remove_series(value) for value in obj if not isinstance(value, pd.Series)]
    if isinstance(obj, tuple):
        return tuple(_remove_series(value) for value in obj if not isinstance(value, pd.Series))
    return obj


def _matching_full_result_path(path: Path, info: Dict[str, Any]) -> Optional[Path]:
    if info["result_kind"] != "simple":
        return path
    full_name = path.name.replace("_simple_", "_", 1)
    full_path = path.with_name(full_name)
    return full_path if full_path.exists() else None


def _load_matching_full_results(
    path: Path,
    info: Dict[str, Any],
    cache: Dict[Path, Optional[Dict[Any, Any]]],
    skipped: List[Dict[str, Any]],
) -> Optional[Dict[Any, Any]]:
    full_path = _matching_full_result_path(path, info)
    if full_path is None:
        return None
    if full_path in cache:
        return cache[full_path]

    try:
        raw = _load_pickle(full_path)
    except Exception as exc:
        skipped.append({"file": str(full_path), "reason": f"technology_load_error: {exc}"})
        cache[full_path] = None
        return None

    if not isinstance(raw, dict):
        skipped.append(
            {
                "file": str(full_path),
                "reason": f"technology_unexpected_type: {type(raw).__name__}",
            }
        )
        cache[full_path] = None
        return None

    cache[full_path] = raw
    return raw


def _is_building_results_block(key: Any, value: Any) -> bool:
    if not isinstance(key, str) or not isinstance(value, dict):
        return False
    if "buildings_in_cluster" in value:
        return True
    return any(component_key.startswith(f"building_{key}") for component_key in value)


def _prepare_building_results_block(value: Dict[str, Any]) -> Dict[str, Any]:
    prepared = dict(value)
    if "strategy" not in prepared and "refurbishment_status" in prepared:
        prepared["strategy"] = prepared["refurbishment_status"]
    return prepared


def _extract_centralized_selection(record: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    results = record.get("results")
    if not isinstance(results, dict):
        return {}, {}

    selection: Dict[str, Any] = {}
    buildings: Dict[str, Any] = {}
    for key, value in results.items():
        if key in {"Electricity", "NaturalGas", "BioGas", "Hydrogen", "heat_grid"}:
            selection[key] = value
            continue
        if _is_building_results_block(key, value):
            building_block = _prepare_building_results_block(value)
            selection[key] = building_block
            buildings[key] = building_block

    return selection, buildings


def _technology_payload(
    record: Dict[str, Any],
    technology_record: Optional[Dict[str, Any]],
    keep_series: bool,
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[str]]:
    source_record = technology_record if isinstance(technology_record, dict) else record
    selection, buildings = _extract_centralized_selection(source_record)
    if not keep_series:
        selection = _remove_series(selection)
        buildings = _remove_series(buildings)
    technology_source = "record" if isinstance(record.get("results"), dict) else None
    if technology_record is not None and technology_record is not record:
        technology_source = "matching_full_file"
    return selection, buildings, technology_source


def _electricity_grid_compat(record: Dict[str, Any], keep_series: bool) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    electricity_grid = record.get("electricity_grid")
    if not isinstance(electricity_grid, dict):
        return {}, {}

    cleaned = electricity_grid if keep_series else _remove_series(electricity_grid)
    compat = {
        "investment_cost": cleaned.get("investment_cost", 0.0),
        "investment_co2": cleaned.get("investment_co2", 0.0),
        "added_trafo_capacity": cleaned.get("capacity", 0.0),
        "added_line_length": 0.0,
        "added_trafo_cost": cleaned.get("investment_cost", 0.0),
        "added_line_cost": 0.0,
        "added_trafo_co2": cleaned.get("investment_co2", 0.0),
        "added_line_co2": 0.0,
    }
    return cleaned, compat


def _as_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return out


def _is_valid_record(record: Any) -> bool:
    if not isinstance(record, dict):
        return False
    return all(_as_float(record.get(key)) is not None for key in ("co2", "peak", "totex"))


def _record_sort_key(entry: Dict[str, Any]) -> Tuple[Any, ...]:
    metadata = entry["metadata"]
    key = entry.get("key")
    key_tuple = key if isinstance(key, tuple) else (str(key),)
    return (
        metadata["combined_cluster"],
        metadata["temperature_level"],
        metadata["constraint_type"],
        metadata["file_objective"],
        key_tuple,
        metadata["source_file"],
    )


def _load_pickle(path: Path) -> Any:
    with path.open("rb") as fh:
        return pickle.load(fh)


def _iter_result_files(
    centralized_dir: Path,
    result_kind: str,
    temperature_levels: Optional[set[int]],
) -> Iterable[Tuple[Path, Dict[str, Any]]]:
    for path in sorted(centralized_dir.glob("res_cen_t*.pkl")):
        info = _match_result_file(path)
        if info is None:
            continue
        if result_kind != "both" and info["result_kind"] != result_kind:
            continue
        if temperature_levels is not None and info["temperature"] not in temperature_levels:
            continue
        yield path, info


def _load_centralized_records_for_dir(
    centralized_dir: Path,
    ueu_case: str,
    combined_cluster: str,
    result_kind: str,
    temperature_levels: Optional[set[int]],
    keep_series: bool,
) -> Tuple[Dict[Tuple[Any, ...], Dict[str, Any]], List[Dict[str, Any]]]:
    records: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    skipped: List[Dict[str, Any]] = []
    full_result_cache: Dict[Path, Optional[Dict[Any, Any]]] = {}

    for path, info in _iter_result_files(centralized_dir, result_kind, temperature_levels):
        try:
            raw = _load_pickle(path)
        except Exception as exc:
            skipped.append({"file": str(path), "reason": f"load_error: {exc}"})
            continue

        if not isinstance(raw, dict):
            skipped.append({"file": str(path), "reason": f"unexpected_type: {type(raw).__name__}"})
            continue

        full_results = None
        if info["result_kind"] == "simple":
            full_results = _load_matching_full_results(path, info, full_result_cache, skipped)

        for key, record in raw.items():
            if not _is_valid_record(record):
                skipped.append(
                    {
                        "file": str(path),
                        "key": repr(key),
                        "reason": "invalid_or_incomplete_objectives",
                    }
                )
                continue

            cleaned = record if keep_series else _remove_series(record)
            technology_record = full_results.get(key) if isinstance(full_results, dict) else None
            selection, buildings, technology_source = _technology_payload(
                record=record,
                technology_record=technology_record,
                keep_series=keep_series,
            )
            electricity_grid, electricity_grid_compat = _electricity_grid_compat(record, keep_series)
            price_scenario_name = _infer_price_scenario_name(ueu_case, record)
            metadata = {
                "ueu_case": ueu_case,
                "base_ueu_case": _infer_base_ueu_case(ueu_case),
                "price_scenario_name": price_scenario_name,
                "price_scenario": record.get("price_scenario"),
                "combined_cluster": combined_cluster,
                "temperature_level": info["temperature"],
                "constraint_type": info["constraint"],
                "file_objective": info["objective"],
                "file_factor_token": info["factor"],
                "result_kind": info["result_kind"],
                "source_file": path.name,
                "source_dir": str(centralized_dir),
                "technology_source": technology_source,
                "technology_source_file": (
                    _matching_full_result_path(path, info).name
                    if technology_source == "matching_full_file" and _matching_full_result_path(path, info) is not None
                    else path.name if technology_source == "record" else None
                ),
            }
            entry = {
                "key": key,
                "co2": _as_float(record.get("co2")),
                "peak": _as_float(record.get("peak")),
                "totex": _as_float(record.get("totex")),
                "peak_from_grid": _as_float(record.get("peak_from_grid")),
                "peak_into_grid": _as_float(record.get("peak_into_grid")),
                "peak_reduction_factor": _as_float(record.get("peak_reduction_factor")),
                "refurbish": record.get("refurbish"),
                "time": _as_float(record.get("time")),
                "metadata": metadata,
                "record": cleaned,
                "selection": selection,
                "buildings": buildings,
                "building_ids": sorted(buildings),
                "heat_grid": selection.get("heat_grid", {}),
                "electricity_grid": electricity_grid,
                "Electricity_Grid": electricity_grid_compat,
            }
            record_key = (
                combined_cluster,
                info["temperature"],
                info["constraint"],
                info["objective"],
                key,
                path.name,
            )
            records[record_key] = entry

    return records, skipped


def _collect_simple_full_consistency_rows(
    centralized_dir: Path,
    ueu_case: str,
    combined_cluster: str,
    temperature_levels: Optional[set[int]],
) -> List[Dict[str, Any]]:
    statuses: Dict[Tuple[Any, ...], Dict[str, Any]] = {}

    for path, info in _iter_result_files(centralized_dir, "both", temperature_levels):
        base = {
            "ueu_case": ueu_case,
            "base_ueu_case": _infer_base_ueu_case(ueu_case),
            "price_scenario_name": _infer_price_scenario_name(ueu_case),
            "combined_cluster": combined_cluster,
            "temperature_level": info["temperature"],
            "constraint_type": info["constraint"],
            "file_objective": info["objective"],
            "file_factor_token": info["factor"],
        }
        kind = info["result_kind"]

        try:
            raw = _load_pickle(path)
        except Exception as exc:
            scenario_key = (
                info["temperature"],
                info["constraint"],
                info["objective"],
                info["factor"],
                "__file_load__",
            )
            row = statuses.setdefault(scenario_key, {**base, "key": "__file_load__"})
            row[f"{kind}_file"] = path.name
            row[f"{kind}_exists"] = True
            row[f"{kind}_valid"] = False
            row[f"{kind}_reason"] = f"load_error: {exc}"
            continue

        if not isinstance(raw, dict):
            scenario_key = (
                info["temperature"],
                info["constraint"],
                info["objective"],
                info["factor"],
                "__file_type__",
            )
            row = statuses.setdefault(scenario_key, {**base, "key": "__file_type__"})
            row[f"{kind}_file"] = path.name
            row[f"{kind}_exists"] = True
            row[f"{kind}_valid"] = False
            row[f"{kind}_reason"] = f"unexpected_type: {type(raw).__name__}"
            continue

        for key, record in raw.items():
            scenario_key = (
                info["temperature"],
                info["constraint"],
                info["objective"],
                info["factor"],
                key,
            )
            row = statuses.setdefault(scenario_key, {**base, "key": repr(key)})
            row[f"{kind}_file"] = path.name
            row[f"{kind}_exists"] = True
            row[f"{kind}_valid"] = _is_valid_record(record)
            if not row[f"{kind}_valid"]:
                row[f"{kind}_reason"] = "invalid_or_incomplete_objectives"

    rows = []
    for row in statuses.values():
        simple_valid = bool(row.get("simple_valid"))
        full_valid = bool(row.get("full_valid"))
        if simple_valid and not full_valid:
            issue = "simple_valid_full_missing_or_invalid"
        elif full_valid and not simple_valid:
            issue = "full_valid_simple_missing_or_invalid"
        elif row.get("simple_exists") and row.get("full_exists") and not simple_valid and not full_valid:
            issue = "both_invalid"
        else:
            continue

        rows.append(
            {
                **row,
                "simple_exists": bool(row.get("simple_exists")),
                "simple_valid": simple_valid,
                "full_exists": bool(row.get("full_exists")),
                "full_valid": full_valid,
                "issue": issue,
            }
        )

    return sorted(
        rows,
        key=lambda row: (
            row["combined_cluster"],
            row["temperature_level"],
            row["constraint_type"],
            row["file_objective"],
            row["file_factor_token"],
            row["key"],
            row["issue"],
        ),
    )


def _write_pickle(path: Path, obj: Any) -> None:
    with path.open("wb") as fh:
        pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)


def _write_rows(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(dict.fromkeys(key for row in rows for key in row.keys()))
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _front_summary_rows(front: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for idx, entry in enumerate(front):
        metadata = entry["metadata"]
        rows.append(
            {
                "idx": idx,
                "ueu_case": metadata["ueu_case"],
                "base_ueu_case": metadata.get("base_ueu_case"),
                "price_scenario_name": metadata.get("price_scenario_name"),
                "combined_cluster": metadata["combined_cluster"],
                "temperature_level": metadata["temperature_level"],
                "constraint_type": metadata["constraint_type"],
                "file_objective": metadata["file_objective"],
                "file_factor_token": metadata["file_factor_token"],
                "key": repr(entry["key"]),
                "co2": entry["co2"],
                "peak": entry["peak"],
                "totex": entry["totex"],
                "peak_from_grid": entry["peak_from_grid"],
                "peak_into_grid": entry["peak_into_grid"],
                "peak_reduction_factor": entry["peak_reduction_factor"],
                "refurbish": entry["refurbish"],
                "time": entry["time"],
                "source_file": metadata["source_file"],
                "technology_source": metadata.get("technology_source"),
                "technology_source_file": metadata.get("technology_source_file"),
                "building_count": len(entry.get("building_ids", [])),
                "has_heat_grid": bool(entry.get("heat_grid")),
                "has_electricity_grid": bool(entry.get("electricity_grid")),
            }
        )
    return rows


def _skipped_row_matches_group(
    row: Dict[str, Any],
    temperature_level: int,
    constraint_type: str,
) -> bool:
    file_name = Path(str(row.get("file", ""))).name
    return f"_t{temperature_level}_{constraint_type}_" in file_name


def _save_outputs(
    output_dir: Path,
    records: Dict[Tuple[Any, ...], Dict[str, Any]],
    front: List[Dict[str, Any]],
    skipped: List[Dict[str, Any]],
    consistency_rows: List[Dict[str, Any]],
    meta: Dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_pickle(output_dir / "centralized_records.pkl", records)
    _write_pickle(output_dir / "centralized_front.pkl", front)
    _write_pickle(output_dir / "centralized_package.pkl", [records, front])
    _write_pickle(output_dir / "meta.pkl", meta)
    _write_rows(output_dir / "summary.csv", _front_summary_rows(front))
    _write_rows(output_dir / "skipped.csv", skipped)
    _write_rows(output_dir / "simple_full_consistency.csv", consistency_rows)


def _process_centralized_dir(
    centralized_dir: Path,
    input_case_root: Path,
    output_case_root: Path,
    ueu_case: str,
    result_kind: str,
    temperature_levels: Optional[set[int]],
    keep_series: bool,
) -> List[Dict[str, Any]]:
    combined_cluster = centralized_dir.parent.name
    records, skipped = _load_centralized_records_for_dir(
        centralized_dir=centralized_dir,
        ueu_case=ueu_case,
        combined_cluster=combined_cluster,
        result_kind=result_kind,
        temperature_levels=temperature_levels,
        keep_series=keep_series,
    )
    consistency_rows = _collect_simple_full_consistency_rows(
        centralized_dir=centralized_dir,
        ueu_case=ueu_case,
        combined_cluster=combined_cluster,
        temperature_levels=temperature_levels,
    )

    grouped: Dict[Tuple[int, str], Dict[Tuple[Any, ...], Dict[str, Any]]] = {}
    for key, entry in records.items():
        metadata = entry["metadata"]
        group_key = (metadata["temperature_level"], metadata["constraint_type"])
        grouped.setdefault(group_key, {})[key] = entry

    summaries = []
    for (temperature_level, constraint_type), temp_records in sorted(grouped.items()):
        front = sorted(temp_records.values(), key=_record_sort_key)
        output_dir = output_case_root / combined_cluster / f"t{temperature_level}" / constraint_type
        temp_skipped = [
            row for row in skipped
            if _skipped_row_matches_group(row, temperature_level, constraint_type)
        ]
        temp_consistency_rows = [
            row for row in consistency_rows
            if row["temperature_level"] == temperature_level
            and row["constraint_type"] == constraint_type
        ]
        meta = {
            "ueu_case": ueu_case,
            "base_ueu_case": _infer_base_ueu_case(ueu_case),
            "price_scenario_name": _infer_price_scenario_name(ueu_case),
            "combined_cluster": combined_cluster,
            "temperature_level": temperature_level,
            "constraint_type": constraint_type,
            "input_dir": str(centralized_dir),
            "input_case_root": str(input_case_root),
            "result_kind": result_kind,
            "keep_series": keep_series,
            "record_count": len(temp_records),
            "front_count": len(front),
            "skipped_count": len(temp_skipped),
            "simple_full_consistency_issue_count": len(temp_consistency_rows),
            "pareto_pruning": False,
        }
        _save_outputs(output_dir, temp_records, front, temp_skipped, temp_consistency_rows, meta)
        summaries.append(
            {
                "ueu_case": ueu_case,
                "base_ueu_case": _infer_base_ueu_case(ueu_case),
                "price_scenario_name": _infer_price_scenario_name(ueu_case),
                "combined_cluster": combined_cluster,
                "temperature_level": temperature_level,
                "constraint_type": constraint_type,
                "status": "ok",
                "records": len(temp_records),
                "front": len(front),
                "skipped": len(temp_skipped),
                "simple_full_consistency_issues": len(temp_consistency_rows),
                "output_dir": str(output_dir),
            }
        )

    if not grouped:
        consistency_groups = sorted(
            {
                (row["temperature_level"], row["constraint_type"])
                for row in consistency_rows
            }
        )
        for temperature_level, constraint_type in consistency_groups:
            output_dir = output_case_root / combined_cluster / f"t{temperature_level}" / constraint_type
            temp_skipped = [
                row for row in skipped
                if _skipped_row_matches_group(row, temperature_level, constraint_type)
            ]
            temp_consistency_rows = [
                row for row in consistency_rows
                if row["temperature_level"] == temperature_level
                and row["constraint_type"] == constraint_type
            ]
            meta = {
                "ueu_case": ueu_case,
                "base_ueu_case": _infer_base_ueu_case(ueu_case),
                "price_scenario_name": _infer_price_scenario_name(ueu_case),
                "combined_cluster": combined_cluster,
                "temperature_level": temperature_level,
                "constraint_type": constraint_type,
                "input_dir": str(centralized_dir),
                "input_case_root": str(input_case_root),
                "result_kind": result_kind,
                "keep_series": keep_series,
                "record_count": 0,
                "front_count": 0,
                "skipped_count": len(temp_skipped),
                "simple_full_consistency_issue_count": len(temp_consistency_rows),
                "pareto_pruning": False,
            }
            _save_outputs(output_dir, {}, [], temp_skipped, temp_consistency_rows, meta)

            summaries.append(
                {
                    "ueu_case": ueu_case,
                    "base_ueu_case": _infer_base_ueu_case(ueu_case),
                    "price_scenario_name": _infer_price_scenario_name(ueu_case),
                    "combined_cluster": combined_cluster,
                    "temperature_level": temperature_level,
                    "constraint_type": constraint_type,
                    "status": "no_valid_records",
                    "records": 0,
                    "front": 0,
                    "skipped": len(temp_skipped),
                    "simple_full_consistency_issues": len(temp_consistency_rows),
                    "output_dir": str(output_dir),
                }
            )

        if not consistency_groups:
            summaries.append(
                {
                    "ueu_case": ueu_case,
                    "base_ueu_case": _infer_base_ueu_case(ueu_case),
                    "price_scenario_name": _infer_price_scenario_name(ueu_case),
                    "combined_cluster": combined_cluster,
                    "temperature_level": "",
                    "constraint_type": "",
                    "status": "no_valid_records",
                    "records": 0,
                    "front": 0,
                    "skipped": len(skipped),
                    "simple_full_consistency_issues": len(consistency_rows),
                    "output_dir": "",
                }
            )

    return summaries


def run_post_processing(
    input_root: Path,
    output_root: Path,
    ueu_cases: List[str],
    price_scenarios: List[str],
    combined_cluster_glob: str,
    result_kind: str,
    temperature_levels: Optional[set[int]],
    keep_series: bool,
) -> List[Dict[str, Any]]:
    all_summaries: List[Dict[str, Any]] = []

    for ueu_case, input_case_root in _resolve_input_cases(input_root, ueu_cases, price_scenarios):
        output_case_root = output_root / ueu_case
        if not input_case_root.exists():
            all_summaries.append(
                {
                    "ueu_case": ueu_case,
                    "base_ueu_case": _infer_base_ueu_case(ueu_case),
                    "price_scenario_name": _infer_price_scenario_name(ueu_case),
                    "combined_cluster": "",
                    "temperature_level": "",
                    "constraint_type": "",
                    "status": "missing_input_case_root",
                    "records": 0,
                    "front": 0,
                    "skipped": 0,
                    "output_dir": "",
                }
            )
            continue

        centralized_dirs = sorted(
            path / "centralized"
            for path in input_case_root.glob(combined_cluster_glob)
            if (path / "centralized").is_dir()
        )
        if not centralized_dirs:
            all_summaries.append(
                {
                    "ueu_case": ueu_case,
                    "base_ueu_case": _infer_base_ueu_case(ueu_case),
                    "price_scenario_name": _infer_price_scenario_name(ueu_case),
                    "combined_cluster": "",
                    "temperature_level": "",
                    "constraint_type": "",
                    "status": "no_centralized_dirs",
                    "records": 0,
                    "front": 0,
                    "skipped": 0,
                    "output_dir": "",
                }
            )
            continue

        for centralized_dir in centralized_dirs:
            all_summaries.extend(
                _process_centralized_dir(
                    centralized_dir=centralized_dir,
                    input_case_root=input_case_root,
                    output_case_root=output_case_root,
                    ueu_case=ueu_case,
                    result_kind=result_kind,
                    temperature_levels=temperature_levels,
                    keep_series=keep_series,
                )
            )

    output_root.mkdir(parents=True, exist_ok=True)
    _write_rows(output_root / "summary.csv", all_summaries)
    return all_summaries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Post-process centralized district-level optimization results without Pareto pruning."
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        default=DEFAULT_INPUT_ROOT,
        help=(
            "Directory containing processed_bds_in... folders, or one processed_bds_in... "
            "case folder directly."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Output root. Keep this path short on Windows to avoid MAX_PATH errors.",
    )
    parser.add_argument(
        "--ueu-case",
        default=None,
        help=(
            "Comma-separated UEU case folders. Omit this when --input-root points "
            "directly to one processed_bds_in... folder. With --price-scenarios, "
            "provide the base UEU folder name without the price-scenario suffix."
        ),
    )
    parser.add_argument(
        "--price-scenarios",
        default=None,
        help=(
            "Comma-separated centralized price scenarios to process, or 'all'. "
            "Non-ref scenarios are expected in folders named like "
            "processed_bds_in_DENI..._<price_scenario>."
        ),
    )
    parser.add_argument("--combined-cluster-glob", default="combined_cluster_*")
    parser.add_argument(
        "--result-kind",
        choices=["simple", "full", "both"],
        default="simple",
        help="Load simple files by default; full files can be very large.",
    )
    parser.add_argument("--temperature-levels", default=None, help="Comma-separated levels, e.g. 50,80.")
    parser.add_argument(
        "--keep-series",
        action="store_true",
        help="Keep pandas Series in records. Default removes them to keep output files smaller.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    summaries = run_post_processing(
        input_root=_resolve_user_path(args.input_root),
        output_root=_resolve_user_path(args.output_root),
        ueu_cases=_parse_csv_values(args.ueu_case),
        price_scenarios=_parse_price_scenarios(args.price_scenarios),
        combined_cluster_glob=args.combined_cluster_glob,
        result_kind=args.result_kind,
        temperature_levels=_parse_temperature_levels(args.temperature_levels),
        keep_series=args.keep_series,
    )
    ok = sum(1 for row in summaries if row["status"] == "ok")
    print(f"Processed centralized outputs: ok={ok} total_rows={len(summaries)} output_root={args.output_root}")


if __name__ == "__main__":
    main()
