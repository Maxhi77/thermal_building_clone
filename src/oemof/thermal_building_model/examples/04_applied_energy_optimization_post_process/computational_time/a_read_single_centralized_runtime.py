from __future__ import annotations

import argparse
import os
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List


SCRIPT_DIR = Path(__file__).resolve().parent
ARCHIVE_UEU_ROOT = (
    Path("M:/04_ArchivMA/Hillen Maximilian")
    / ("Ver" + chr(0x00F6) + "ffentlichungen")
    / "UEU"
)
DEFAULT_PICKLE = (
    ARCHIVE_UEU_ROOT
    / "processed_bds_in_DENI03403000SEC5658"
    / "combined_cluster_sfh_k04_mfh_k04"
    / "centralized"
    / "res_cen_t50_cmin_co2_1.pkl"
)


def load_pickle(path: Path) -> Any:
    with path.open("rb") as file:
        return pickle.load(file)


def extract_computational_times(result_data: Dict[Any, Any]) -> List[Dict[str, Any]]:
    rows = []
    for result_key, result in result_data.items():
        if not isinstance(result, dict) or "time" not in result:
            continue
        if result["time"] is None:
            row = {
                "result_key": result_key,
                "seconds": None,
            }
            if isinstance(result_key, tuple) and len(result_key) >= 3:
                row.update(
                    {
                        "pareto_key": result_key[0],
                        "co2_factor": result_key[1],
                        "reference": result_key[2],
                    }
                )
            rows.append(row)
            continue

        row = {
            "result_key": result_key,
            "seconds": float(result["time"]),
        }
        if isinstance(result_key, tuple) and len(result_key) >= 3:
            row.update(
                {
                    "pareto_key": result_key[0],
                    "co2_factor": result_key[1],
                    "reference": result_key[2],
                }
            )
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read computational times from one centralized result pickle."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_PICKLE)
    args = parser.parse_args()

    result_data = load_pickle(args.input)
    if not isinstance(result_data, dict):
        raise TypeError(f"Expected dict in pickle, got {type(result_data).__name__}")

    rows = extract_computational_times(result_data)
    print(f"input={args.input}")
    print(f"result_entries={len(result_data)}")
    print(f"time_entries={len(rows)}")

    valid_rows = [row for row in rows if row["seconds"] is not None]
    none_rows = [row for row in rows if row["seconds"] is None]
    total_seconds = sum(row["seconds"] for row in valid_rows)
    if none_rows:
        print(f"time_entries_without_value={len(none_rows)}")
    for row in rows:
        label = row.get("co2_factor", row["result_key"])
        if row["seconds"] is None:
            print(f"co2={label} | seconds=None")
            continue
        print(f"co2={label} | seconds={row['seconds']:.2f} | hours={row['seconds'] / 3600:.2f}")

    print(f"total_seconds={total_seconds:.2f}")
    print(f"total_hours={total_seconds / 3600:.2f}")
    sys.stdout.flush()
    # Some loaded optimization objects keep Python alive after printing.
    os._exit(0)


if __name__ == "__main__":
    main()
