from __future__ import annotations

import argparse
import gc
import math
import os
import pickle
import re
import struct
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape


SCRIPT_DIR = Path(__file__).resolve().parent
ARCHIVE_UEU_ROOT = (
    Path("M:/04_ArchivMA/Hillen Maximilian")
    / ("Ver" + chr(0x00F6) + "ffentlichungen")
    / "UEU"
)
DEFAULT_INPUT_DIR = Path(
    r"C:\Users\hill_mx\Desktop\From Luis\Case Studies\Small New\processed_bds_in_DENI03403000SEC5658"
)
DEFAULT_OUTPUT = SCRIPT_DIR / "centralized_runtime_averages_DENI03403000SEC5658.xlsx"

RESULT_FILE_PATTERN = re.compile(
    r"^res_cen_t(?P<t_level>50|80)_(?P<c_bound>cmin|cmax)_simple_co2_.+\.pkl$"
)
T_LEVELS = ("t50", "t80")
C_BOUNDS = ("cmin", "cmax")


def load_pickle(path: Path) -> Any:
    with path.open("rb") as file:
        return pickle.load(file)


def iter_solution_times(result_data: Any) -> Iterable[float | None]:
    if not isinstance(result_data, dict):
        return

    for result in result_data.values():
        if not isinstance(result, dict) or "time" not in result:
            continue
        value = result["time"]
        if value is None:
            yield None
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            yield None
            continue
        if math.isfinite(numeric_value):
            yield numeric_value
        else:
            yield None


def iter_point_solution_times(result_data: Any) -> Iterable[tuple[Any, Any, float | None]]:
    if not isinstance(result_data, dict):
        return

    for result_key, result in result_data.items():
        if (
            not isinstance(result_key, tuple)
            or len(result_key) < 2
            or not isinstance(result, dict)
            or "time" not in result
        ):
            continue

        value = result["time"]
        if value is None:
            yield result_key[0], result_key[1], None
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            yield result_key[0], result_key[1], None
            continue
        if math.isfinite(numeric_value):
            yield result_key[0], result_key[1], numeric_value
        else:
            yield result_key[0], result_key[1], None


def iter_solution_times_from_pickle_ops(path: Path) -> Iterable[float | None]:
    time_memo_ids = set()
    next_memo_id = 0
    pending_time_key = False
    data = path.read_bytes()
    position = 0
    length = len(data)

    while position < length:
        opcode = data[position]
        position += 1

        if opcode == 0x94:  # MEMOIZE
            if pending_time_key:
                time_memo_ids.add(next_memo_id)
            next_memo_id += 1
            continue

        if opcode == 0x71:  # BINPUT
            arg = data[position]
            position += 1
            if pending_time_key:
                time_memo_ids.add(arg)
            continue

        if opcode == 0x72:  # LONG_BINPUT
            arg = int.from_bytes(data[position : position + 4], "little")
            position += 4
            if pending_time_key:
                time_memo_ids.add(arg)
            continue

        if opcode == 0x8C:  # SHORT_BINUNICODE
            string_length = data[position]
            position += 1
            value = data[position : position + string_length]
            position += string_length
            if value == b"time":
                pending_time_key = True
            continue

        if opcode == 0x58:  # BINUNICODE
            string_length = int.from_bytes(data[position : position + 4], "little")
            position += 4
            value = data[position : position + string_length]
            position += string_length
            if value == b"time":
                pending_time_key = True
            continue

        if opcode == 0x8D:  # BINUNICODE8
            string_length = int.from_bytes(data[position : position + 8], "little")
            position += 8
            value = data[position : position + string_length]
            position += string_length
            if value == b"time":
                pending_time_key = True
            continue

        if opcode == 0x68:  # BINGET
            arg = data[position]
            position += 1
            if arg in time_memo_ids:
                pending_time_key = True
            continue

        if opcode == 0x6A:  # LONG_BINGET
            arg = int.from_bytes(data[position : position + 4], "little")
            position += 4
            if arg in time_memo_ids:
                pending_time_key = True
            continue

        if pending_time_key and opcode == 0x4E:  # NONE
            yield None
            pending_time_key = False
            continue

        if pending_time_key and opcode == 0x47:  # BINFLOAT
            yield struct.unpack(">d", data[position : position + 8])[0]
            position += 8
            pending_time_key = False
            continue

        if pending_time_key and opcode == 0x46:  # FLOAT
            end_position = data.index(b"\n", position)
            yield float(data[position:end_position].decode("ascii"))
            position = end_position + 1
            pending_time_key = False
            continue

        if pending_time_key and opcode == 0x4A:  # BININT
            yield float(int.from_bytes(data[position : position + 4], "little", signed=True))
            position += 4
            pending_time_key = False
            continue

        if pending_time_key and opcode == 0x4B:  # BININT1
            yield float(data[position])
            position += 1
            pending_time_key = False
            continue

        if pending_time_key and opcode == 0x4D:  # BININT2
            yield float(int.from_bytes(data[position : position + 2], "little"))
            position += 2
            pending_time_key = False
            continue

        if pending_time_key:
            pending_time_key = False

        if opcode in {0x80, 0x4B}:  # PROTO, BININT1
            position += 1
        elif opcode in {0x4D}:  # BININT2
            position += 2
        elif opcode in {0x4A}:  # BININT
            position += 4
        elif opcode == 0x47:  # BINFLOAT
            position += 8
        elif opcode == 0x95:  # FRAME
            position += 8
        elif opcode in {0x43, 0x55}:  # SHORT_BINBYTES, SHORT_BINSTRING
            item_length = data[position]
            position += 1 + item_length
        elif opcode in {0x42, 0x54}:  # BINBYTES, BINSTRING
            item_length = int.from_bytes(data[position : position + 4], "little")
            position += 4 + item_length
        elif opcode in {0x8E, 0x96}:  # BINBYTES8, BYTEARRAY8
            item_length = int.from_bytes(data[position : position + 8], "little")
            position += 8 + item_length
        elif opcode in {0x46, 0x49, 0x4C, 0x50}:  # FLOAT, INT, LONG, PERSID
            position = data.index(b"\n", position) + 1
        elif opcode == 0x63:  # GLOBAL
            position = data.index(b"\n", data.index(b"\n", position) + 1) + 1
        elif opcode == 0x8A:  # LONG1
            item_length = data[position]
            position += 1 + item_length
        elif opcode == 0x8B:  # LONG4
            item_length = int.from_bytes(data[position : position + 4], "little")
            position += 4 + item_length


def empty_bucket() -> dict[str, Any]:
    return {
        "time_sum_seconds": 0.0,
        "valid_solution_count": 0,
        "none_time_count": 0,
        "files_read": 0,
        "files_failed": 0,
        "result_entries_scanned": 0,
    }


def empty_point_bucket() -> dict[str, Any]:
    return {
        "time_sum_seconds": 0.0,
        "valid_solution_count": 0,
        "none_time_count": 0,
    }


def aggregate_runtime_averages(
    input_dir: Path,
    print_progress: bool = False,
    max_files: int | None = None,
    load_pickles: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[tuple[str, str, str, str], dict[str, Any]]]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(empty_bucket)
    point_buckets: dict[tuple[str, str, str, str], dict[str, Any]] = defaultdict(empty_point_bucket)
    file_rows = []
    processed_total_files = 0
    combination_dirs = [
        row
        for row in sorted(input_dir.iterdir())
        if row.is_dir() and row.name.startswith("combined_cluster_")
    ]

    for combination_index, combination_dir in enumerate(combination_dirs, start=1):
        centralized_dir = combination_dir / "centralized"
        if not centralized_dir.is_dir():
            continue

        for file_path in sorted(centralized_dir.glob("res_cen_t*_c*_simple_co2_*.pkl")):
            if max_files is not None and processed_total_files >= max_files:
                break

            match = RESULT_FILE_PATTERN.match(file_path.name)
            if match is None:
                continue

            t_level = "t" + match.group("t_level")
            c_bound = match.group("c_bound")
            bucket_key = (combination_dir.name, c_bound, t_level)
            bucket = buckets[bucket_key]
            bucket["files_read"] += 1

            file_valid_count = 0
            file_none_count = 0
            file_time_sum = 0.0
            file_entry_count = 0
            error_message = ""

            try:
                result_data = load_pickle(file_path)
                solution_times = (
                    iter_solution_times(result_data)
                    if load_pickles
                    else iter_solution_times_from_pickle_ops(file_path)
                )

                for time_value in solution_times:
                    file_entry_count += 1
                    if time_value is None:
                        file_none_count += 1
                        continue
                    file_valid_count += 1
                    file_time_sum += time_value

                for co2_factor, peak_factor, time_value in iter_point_solution_times(result_data):
                    point_label = make_point_label(co2_factor, peak_factor)
                    point_bucket = point_buckets[
                        (combination_dir.name, c_bound, t_level, point_label)
                    ]
                    if time_value is None:
                        point_bucket["none_time_count"] += 1
                        continue
                    point_bucket["valid_solution_count"] += 1
                    point_bucket["time_sum_seconds"] += time_value
                del result_data
            except Exception as exc:  # pragma: no cover - diagnostic export path
                bucket["files_failed"] += 1
                error_message = f"{type(exc).__name__}: {exc}"
            finally:
                if load_pickles:
                    gc.collect()

            bucket["valid_solution_count"] += file_valid_count
            bucket["none_time_count"] += file_none_count
            bucket["time_sum_seconds"] += file_time_sum
            bucket["result_entries_scanned"] += file_entry_count

            file_rows.append(
                {
                    "combined_cluster_combination": combination_dir.name,
                    "c_bound": c_bound,
                    "t_level": t_level,
                    "file_name": file_path.name,
                    "valid_solution_count": file_valid_count,
                    "none_time_count": file_none_count,
                    "result_entries_scanned": file_entry_count,
                    "average_seconds_in_file": (
                        file_time_sum / file_valid_count if file_valid_count else None
                    ),
                    "error": error_message,
                }
            )
            processed_total_files += 1

        if max_files is not None and processed_total_files >= max_files:
            break

        if print_progress:
            processed_files = sum(
                buckets[(combination_dir.name, c_bound, t_level)]["files_read"]
                for c_bound in C_BOUNDS
                for t_level in T_LEVELS
            )
            valid_solutions = sum(
                buckets[(combination_dir.name, c_bound, t_level)]["valid_solution_count"]
                for c_bound in C_BOUNDS
                for t_level in T_LEVELS
            )
            print(
                f"processed_combination={combination_index}/{len(combination_dirs)} "
                f"name={combination_dir.name} files={processed_files} "
                f"valid_solution_times={valid_solutions}",
                flush=True,
            )

    long_rows = []
    combination_names = [row.name for row in combination_dirs]
    for combination_name in combination_names:
        for c_bound in C_BOUNDS:
            for t_level in T_LEVELS:
                bucket = buckets[(combination_name, c_bound, t_level)]
                valid_count = bucket["valid_solution_count"]
                average_seconds = (
                    bucket["time_sum_seconds"] / valid_count if valid_count else None
                )
                long_rows.append(
                    {
                        "combined_cluster_combination": combination_name,
                        "c_bound": c_bound,
                        "t_level": t_level,
                        "average_seconds": average_seconds,
                        "average_hours": (
                            average_seconds / 3600 if average_seconds is not None else None
                        ),
                        "valid_solution_count": valid_count,
                        "none_time_count": bucket["none_time_count"],
                        "files_read": bucket["files_read"],
                        "files_failed": bucket["files_failed"],
                        "result_entries_scanned": bucket["result_entries_scanned"],
                    }
                )

    return long_rows, file_rows, point_buckets


def format_point_value(value: Any) -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isfinite(numeric_value):
        return f"{numeric_value:g}"
    return str(value)


def make_point_label(co2_factor: Any, peak_factor: Any) -> str:
    return f"co2_{format_point_value(co2_factor)}_peak_{format_point_value(peak_factor)}"


def default_point_output_for(output: Path) -> Path:
    if "runtime_averages" in output.stem:
        point_stem = output.stem.replace("runtime_averages", "runtime_point_comparison")
    else:
        point_stem = output.stem + "_point_comparison"
    return output.with_name(point_stem + output.suffix)


def make_wide_rows(long_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_combination: dict[str, dict[str, Any]] = {}
    for row in long_rows:
        combination = row["combined_cluster_combination"]
        wide_row = by_combination.setdefault(
            combination, {"combined_cluster_combination": combination}
        )
        prefix = f"{row['c_bound']}_{row['t_level']}"
        wide_row[f"{prefix}_average_seconds"] = row["average_seconds"]
        wide_row[f"{prefix}_average_hours"] = row["average_hours"]
        wide_row[f"{prefix}_valid_solution_count"] = row["valid_solution_count"]
        wide_row[f"{prefix}_none_time_count"] = row["none_time_count"]
        wide_row[f"{prefix}_files_read"] = row["files_read"]

    columns = ["combined_cluster_combination"]
    for c_bound in C_BOUNDS:
        for t_level in T_LEVELS:
            prefix = f"{c_bound}_{t_level}"
            columns.extend(
                [
                    f"{prefix}_average_seconds",
                    f"{prefix}_average_hours",
                    f"{prefix}_valid_solution_count",
                    f"{prefix}_none_time_count",
                    f"{prefix}_files_read",
                ]
            )

    return [{column: row.get(column) for column in columns} for row in by_combination.values()]


def make_point_comparison_sheets(
    long_rows: list[dict[str, Any]],
    point_buckets: dict[tuple[str, str, str, str], dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    combination_names = sorted(
        {row["combined_cluster_combination"] for row in long_rows}
    )
    sheets = {}

    for c_bound in C_BOUNDS:
        for t_level in T_LEVELS:
            point_labels = sorted(
                {
                    point_label
                    for _, point_c_bound, point_t_level, point_label in point_buckets
                    if point_c_bound == c_bound and point_t_level == t_level
                }
            )
            columns = ["combined_cluster_combination", *point_labels]
            rows = []

            for combination_name in combination_names:
                row = {"combined_cluster_combination": combination_name}
                for point_label in point_labels:
                    point_bucket = point_buckets.get(
                        (combination_name, c_bound, t_level, point_label)
                    )
                    if not point_bucket or not point_bucket["valid_solution_count"]:
                        row[point_label] = None
                        continue
                    row[point_label] = (
                        point_bucket["time_sum_seconds"]
                        / point_bucket["valid_solution_count"]
                    )
                rows.append({column: row.get(column) for column in columns})

            sheets[f"{c_bound}_{t_level}"] = rows

    return sheets


def cell_xml(value: Any, row_number: int, column_number: int) -> str:
    cell_ref = f"{column_name(column_number)}{row_number}"
    if value is None:
        return f'<c r="{cell_ref}"/>'
    if isinstance(value, bool):
        return f'<c r="{cell_ref}" t="b"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return f'<c r="{cell_ref}"><v>{value}</v></c>'
    text = escape(str(value))
    return f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def column_name(column_number: int) -> str:
    name = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def worksheet_xml(rows: list[dict[str, Any]], columns: list[str]) -> str:
    sheet_rows = []
    header_cells = [
        cell_xml(column, 1, column_index)
        for column_index, column in enumerate(columns, start=1)
    ]
    sheet_rows.append(f'<row r="1">{"".join(header_cells)}</row>')

    for row_index, row in enumerate(rows, start=2):
        cells = [
            cell_xml(row.get(column), row_index, column_index)
            for column_index, column in enumerate(columns, start=1)
        ]
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    max_column = column_name(len(columns))
    max_row = max(len(rows) + 1, 1)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="A1:{max_column}{max_row}"/>'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft"/></sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        f'<autoFilter ref="A1:{max_column}{max_row}"/>'
        '</worksheet>'
    )


def write_xlsx(path: Path, sheets: dict[str, list[dict[str, Any]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    sheet_names = list(sheets)
    sheet_columns = {
        name: list(rows[0].keys()) if rows else ["empty"]
        for name, rows in sheets.items()
    }
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    workbook_sheets = []
    workbook_rels = []
    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
    ]

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
            'Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
            'Target="docProps/app.xml"/>'
            '</Relationships>',
        )
        archive.writestr(
            "docProps/core.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<dc:creator>thermal_building_model</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>'
            '</cp:coreProperties>',
        )
        archive.writestr(
            "docProps/app.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            '<Application>Python</Application>'
            '</Properties>',
        )

        for sheet_index, sheet_name in enumerate(sheet_names, start=1):
            relation_id = f"rId{sheet_index}"
            workbook_sheets.append(
                f'<sheet name="{escape(sheet_name)}" sheetId="{sheet_index}" r:id="{relation_id}"/>'
            )
            workbook_rels.append(
                f'<Relationship Id="{relation_id}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{sheet_index}.xml"/>'
            )
            content_types.append(
                f'<Override PartName="/xl/worksheets/sheet{sheet_index}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
            archive.writestr(
                f"xl/worksheets/sheet{sheet_index}.xml",
                worksheet_xml(sheets[sheet_name], sheet_columns[sheet_name]),
            )

        content_types.append("</Types>")
        archive.writestr("[Content_Types].xml", "".join(content_types))
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(workbook_sheets)}</sheets>'
            '</workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(workbook_rels)}'
            '</Relationships>',
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate average computational times from centralized simple result pickles "
            "by combined cluster combination, cmin/cmax, and t50/t80."
        )
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--point-output",
        type=Path,
        default=None,
        help=(
            "Second Excel output with one sheet per cmin/cmax and t50/t80; "
            "rows are cluster combinations and columns are CO2/peak points."
        ),
    )
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument(
        "--load-pickles",
        action="store_true",
        help="Fully unpickle files instead of scanning only time values.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    long_rows, file_rows, point_buckets = aggregate_runtime_averages(
        args.input_dir,
        print_progress=not args.quiet,
        max_files=args.max_files,
        load_pickles=args.load_pickles,
    )
    wide_rows = make_wide_rows(long_rows)
    point_output = args.point_output or default_point_output_for(args.output)
    point_sheets = make_point_comparison_sheets(long_rows, point_buckets)
    write_xlsx(
        args.output,
        {
            "summary_wide": wide_rows,
            "summary_long": long_rows,
            "file_details": file_rows,
        },
    )
    write_xlsx(point_output, point_sheets)

    total_valid = sum(row["valid_solution_count"] for row in long_rows)
    total_none = sum(row["none_time_count"] for row in long_rows)
    total_files = sum(row["files_read"] for row in long_rows)
    total_failed_files = sum(row["files_failed"] for row in long_rows)
    print(f"input_dir={args.input_dir}")
    print(f"output={args.output}")
    print(f"point_output={point_output}")
    print(f"combined_cluster_combinations={len(wide_rows)}")
    print(f"summary_rows={len(long_rows)}")
    print(f"simple_files_read={total_files}")
    print(f"valid_solution_times={total_valid}")
    print(f"none_or_invalid_times_ignored={total_none}")
    print(f"failed_files={total_failed_files}")
    sys.stdout.flush()
    # Some loaded optimization objects keep Python alive after printing.
    os._exit(0)


if __name__ == "__main__":
    main()
