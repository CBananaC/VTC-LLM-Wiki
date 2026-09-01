#!/usr/bin/env python3
"""Create a logical four-column reconstruction of Davidson Table 4.14."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TABLE_ID = "DAV25-TBL-P0095-C0002"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def source_line_ids(table: dict[str, Any], start: int, end: int) -> list[str]:
    ids: list[str] = []
    for row in table["content"]["rows"]:
        if start <= row["row_index"] <= end:
            ids.extend(row["source_line_ids"])
    return list(dict.fromkeys(ids))


def cell(text: str, column: str) -> dict[str, str]:
    return {"column": column, "text": text}


def main() -> None:
    args = parse_args()
    data = json.loads(args.tables_json.read_text(encoding="utf-8"))
    source_table = next(table for table in data["tables"] if table["table_id"] == TABLE_ID)

    columns = [
        {"column_id": "disorder", "header": "Disorder", "order": 1},
        {"column_id": "pathological_basis", "header": "Pathological basis", "order": 2},
        {"column_id": "predisposing_conditions", "header": "Predisposing conditions", "order": 3},
        {"column_id": "other_features", "header": "Other features", "order": 4},
    ]

    logical_rows = [
        {
            "row_id": "column-header",
            "row_type": "column_header",
            "source_row_indices": [2, 3],
            "source_line_ids": source_line_ids(source_table, 2, 3),
            "cells": [
                cell("Disorder", "disorder"),
                cell("Pathological basis", "pathological_basis"),
                cell("Predisposing conditions", "predisposing_conditions"),
                cell("Other features", "other_features"),
            ],
        },
        {
            "row_id": "section-acquired-systemic",
            "row_type": "section_header",
            "merged_across_columns": True,
            "text": "Acquired systemic amyloidosis",
            "source_row_indices": [4],
            "source_line_ids": source_line_ids(source_table, 4, 4),
        },
        {
            "row_id": "reactive-aa",
            "row_type": "data",
            "source_row_indices": list(range(5, 21)),
            "source_line_ids": source_line_ids(source_table, 5, 20),
            "cells": [
                cell("Reactive (AA) amyloidosis", "disorder"),
                cell(
                    "Increased production of serum amyloid A as part of prolonged or recurrent acute inflammatory response",
                    "pathological_basis",
                ),
                cell(
                    "Chronic infection (tuberculosis, bronchiectasis, chronic abscess, osteomyelitis)\nChronic inflammatory diseases (untreated rheumatoid arthritis, familial Mediterranean fever)",
                    "predisposing_conditions",
                ),
                cell(
                    "90% of patients present with non-selective proteinuria or nephrotic syndrome",
                    "other_features",
                ),
            ],
        },
        {
            "row_id": "light-chain-al",
            "row_type": "data",
            "source_row_indices": list(range(21, 37)),
            "source_line_ids": source_line_ids(source_table, 21, 36),
            "cells": [
                cell("Light chain amyloidosis (AL)", "disorder"),
                cell(
                    "Increased production of monoclonal light chain",
                    "pathological_basis",
                ),
                cell(
                    "Monoclonal gammopathies, including myeloma, benign gammopathies and plasmacytoma",
                    "predisposing_conditions",
                ),
                cell(
                    "Restrictive cardiomyopathy, peripheral and autonomic neuropathy, carpal tunnel syndrome, proteinuria, spontaneous purpura, amyloid nodules and plaques\nMacroglossia occurs rarely but is pathognomonic\nPrognosis is poor",
                    "other_features",
                ),
            ],
        },
        {
            "row_id": "dialysis-associated",
            "row_type": "data",
            "source_row_indices": list(range(37, 51)),
            "source_line_ids": source_line_ids(source_table, 37, 50),
            "cells": [
                cell("Dialysis-associated (Aβ₂M) amyloidosis", "disorder"),
                cell(
                    "Accumulation of circulating β₂-microglobulin due to failure of renal catabolism in kidney failure",
                    "pathological_basis",
                ),
                cell("Renal dialysis", "predisposing_conditions"),
                cell(
                    "Carpal tunnel syndrome, chronic arthropathy and pathological fractures secondary to amyloid bone cyst formation\nManifestations occur 5–10 years after the start of dialysis",
                    "other_features",
                ),
            ],
        },
        {
            "row_id": "senile-systemic",
            "row_type": "data",
            "source_row_indices": list(range(51, 57)),
            "source_line_ids": source_line_ids(source_table, 51, 56),
            "cells": [
                cell("Senile systemic amyloidosis", "disorder"),
                cell(
                    "Normal transthyretin protein deposited in tissues",
                    "pathological_basis",
                ),
                cell("Age > 70 years", "predisposing_conditions"),
                cell(
                    "Feature of normal ageing (affects > 90% of 90-year-olds)\nUsually asymptomatic",
                    "other_features",
                ),
            ],
        },
        {
            "row_id": "section-hereditary-systemic",
            "row_type": "section_header",
            "merged_across_columns": True,
            "text": "Hereditary systemic amyloidosis",
            "source_row_indices": [57],
            "source_line_ids": source_line_ids(source_table, 57, 57),
        },
        {
            "row_id": "hereditary-systemic",
            "row_type": "data",
            "source_row_indices": list(range(58, 77)),
            "source_line_ids": source_line_ids(source_table, 58, 76),
            "cells": [
                cell("> 20 forms of hereditary systemic amyloidosis", "disorder"),
                cell(
                    "Production of protein with an abnormal structure that predisposes to amyloid fibril formation. Most commonly due to pathogenic variants in transthyretin gene",
                    "pathological_basis",
                ),
                cell("Autosomal dominant inheritance", "predisposing_conditions"),
                cell(
                    "Peripheral and autonomic neuropathy, cardiomyopathy\nRenal involvement unusual\n10% of gene carriers are asymptomatic throughout life",
                    "other_features",
                ),
            ],
        },
    ]

    output = {
        "schema_version": "vtc-davidson25.table-4-14.logical-reconstruction.v1",
        "record_type": "logical_table_reconstruction_candidate",
        "book_id": "DAV25",
        "table_id": TABLE_ID,
        "name": "4.14 Causes of amyloidosis",
        "source": data["source"],
        "location": source_table["location"],
        "chapter_number": 4,
        "chapter_title": "Clinical immunology",
        "pdf_page": 95,
        "printed_page": 76,
        "layout": {
            "column_count": 4,
            "columns": columns,
            "header_source_row_indices": [2, 3],
            "section_header_rows": ["section-acquired-systemic", "section-hereditary-systemic"],
            "coordinate_system": "PDF points from top-left; see source location bbox",
            "source_table_record": str(args.tables_json.resolve()),
        },
        "rows": logical_rows,
        "reconstruction_method": "logical row/column grouping from generated coordinate table layer, compared with rendered PDF page 95",
        "status": "generated_candidate",
        "verification_status": "visually_checked_layout_not_character_proofread",
        "limitations": [
            "The logical row grouping is reconstructed; merged-cell geometry is represented semantically rather than redrawn.",
            "Text follows the generated embedded-text layer with limited visual normalization of line wrapping and β2 notation.",
            "Medical content should be checked against the source page before use as verified study evidence.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "rows": len(logical_rows), "data_rows": sum(row["row_type"] == "data" for row in logical_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
