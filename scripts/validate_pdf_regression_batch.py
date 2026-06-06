#!/usr/bin/env python3
"""
Executa uma regressao funcional em lote sobre PDFs oficiais do PRJ-13.

Fluxo:
1. Extrai poste, cabos e equipamentos com ProjectExtractor.
2. Calcula BOM com MaterialEngine.
3. Audita cobertura de estruturas.
4. Gera CSV consolidado para comparacao manual ou futura baseline.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.engine import MaterialEngine
from core.extractor import ProjectExtractor


DEFAULT_PDF_DIR = (
    PROJECT_ROOT
    / "docs"
    / "Diagramas de Testes"
    / "Diagramas para iniciar os trabalhos de revisão da calculadora"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "storage" / "regression_reports"
KNOWN_BENIGN_AUDIT_STRUCTURES = {"SMTR"}


def _normalize_issue_list(items: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for item in items:
        value = str(item.get("structure") or "").strip()
        if value:
            values.append(value)
    return sorted(set(values))


def _count_bom_rows(bom_rows: list[dict[str, Any]]) -> dict[str, Any]:
    codes = [str(row.get("Código SAP") or "").strip() for row in bom_rows]
    valid_codes = [code for code in codes if code]
    return {
        "bom_items": len(bom_rows),
        "bom_unique_sap": len(set(valid_codes)),
        "bom_verificar": sum(1 for code in valid_codes if code.upper() == "VERIFICAR"),
        "bom_total_qty": round(
            sum(float(row.get("Quantidade") or 0) for row in bom_rows), 3
        ),
    }


def process_pdf(pdf_path: Path, engine: MaterialEngine) -> dict[str, Any]:
    started_at = datetime.now()
    row: dict[str, Any] = {
        "pdf_name": pdf_path.name,
        "pdf_path": str(pdf_path),
        "status": "OK",
        "error": "",
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": "",
        "elapsed_seconds": 0.0,
    }

    try:
        extractor = ProjectExtractor(str(pdf_path))
        extraction = extractor.extract_with_metadata()

        pole_map = extraction.get("pole_map", {}) or {}
        cables = extraction.get("cables", []) or []
        validation = extraction.get("validation", {}) or {}

        bom_rows = engine.process_form_data(pole_map, cables)
        audit = engine.audit_structure_coverage(pole_map, cables)

        summary = extraction.get("summary", {}) or {}
        bom_counts = _count_bom_rows(bom_rows)
        audit_poles = list(audit.get("poles", []) or [])
        audit_details = [
            detail
            for pole in audit_poles
            for detail in (pole.get("details", []) or [])
        ]
        mismatch_structures = _normalize_issue_list(
            [detail for detail in audit_details if not detail.get("ok")]
        )
        context_missing_structures = _normalize_issue_list(
            [detail for detail in audit_details if detail.get("context_missing")]
        )
        benign_structures = sorted(
            {
                structure
                for structure in mismatch_structures
                if structure in KNOWN_BENIGN_AUDIT_STRUCTURES
            }
        )
        actionable_mismatch_count = max(
            int(audit.get("mismatch_count") or 0) - len(benign_structures), 0
        )
        pole_ids = [str(pole_id) for pole_id in sorted(pole_map.keys(), key=str)]

        row.update(
            {
                "total_poles": int(summary.get("total_poles") or len(pole_map)),
                "total_structures": int(
                    summary.get("total_structures")
                    or sum(len((pdata or {}).get("Est", []) or []) for pdata in pole_map.values())
                ),
                "total_cables": int(summary.get("total_cables") or len(cables)),
                "total_equipments": int(
                    summary.get("total_equipments") or len(extraction.get("equipments", []) or [])
                ),
                "validation_errors": int(validation.get("errors") or 0),
                "validation_warnings": int(validation.get("warnings") or 0),
                "validation_infos": int(validation.get("infos") or 0),
                "validation_issues": len(validation.get("issues", []) or []),
                "audit_ok": bool(audit.get("ok")),
                "audit_mismatch_count": int(audit.get("mismatch_count") or 0),
                "audit_actionable_mismatch_count": actionable_mismatch_count,
                "audit_total_structures": int(audit.get("total_structures") or 0),
                "audit_unresolved_structures": "; ".join(mismatch_structures),
                "audit_context_missing_structures": "; ".join(context_missing_structures),
                "audit_known_benign_structures": "; ".join(benign_structures),
                "pole_ids": ", ".join(pole_ids),
            }
        )
        row.update(bom_counts)
    except Exception as exc:
        row["status"] = "ERROR"
        row["error"] = str(exc)
    finally:
        finished_at = datetime.now()
        row["finished_at"] = finished_at.isoformat(timespec="seconds")
        row["elapsed_seconds"] = round((finished_at - started_at).total_seconds(), 3)

    return row


def _iter_pdfs(pdf_dir: Path, limit: int | None = None) -> list[Path]:
    pdfs = sorted(
        [path for path in pdf_dir.rglob("*.pdf") if path.is_file()],
        key=lambda path: (path.name.lower(), str(path).lower()),
    )
    if limit is not None:
        return pdfs[:limit]
    return pdfs


def _default_output_path(output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"regressao_pdfs_{timestamp}.csv"


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "pdf_name",
        "pdf_path",
        "status",
        "error",
        "started_at",
        "finished_at",
        "elapsed_seconds",
        "total_poles",
        "total_structures",
        "total_cables",
        "total_equipments",
        "bom_items",
        "bom_unique_sap",
        "bom_verificar",
        "bom_total_qty",
        "validation_errors",
        "validation_warnings",
        "validation_infos",
        "validation_issues",
        "audit_ok",
        "audit_mismatch_count",
        "audit_actionable_mismatch_count",
        "audit_total_structures",
        "audit_unresolved_structures",
        "audit_context_missing_structures",
        "audit_known_benign_structures",
        "pole_ids",
    ]

    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def build_report(
    pdf_dir: Path,
    output_path: Path,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    engine = MaterialEngine()
    engine.load_databases()

    pdfs = _iter_pdfs(pdf_dir, limit=limit)
    if not pdfs:
        raise FileNotFoundError(f"Nenhum PDF encontrado em: {pdf_dir}")

    rows = [process_pdf(pdf_path, engine) for pdf_path in pdfs]
    write_csv(rows, output_path)
    return rows


def _print_summary(rows: list[dict[str, Any]], output_path: Path) -> None:
    status_counts = Counter(str(row.get("status") or "").upper() for row in rows)
    ok_count = sum(1 for row in rows if str(row.get("status") or "").upper() == "OK")
    error_count = sum(1 for row in rows if str(row.get("status") or "").upper() == "ERROR")
    mismatch_count = sum(
        int(row.get("audit_mismatch_count") or 0)
        for row in rows
        if row.get("status") == "OK"
    )
    actionable_mismatch_count = sum(
        int(row.get("audit_actionable_mismatch_count") or 0)
        for row in rows
        if row.get("status") == "OK"
    )

    print(f"[OK] Relatorio gerado: {output_path}")
    print(f"[OK] PDFs processados: {len(rows)}")
    print(f"[OK] Status OK: {ok_count}")
    print(f"[OK] Status ERROR: {error_count}")
    print(f"[OK] Mismatches totais: {mismatch_count}")
    print(f"[OK] Mismatches acionaveis: {actionable_mismatch_count}")
    if status_counts:
        print(f"[INFO] Distribuicao de status: {dict(status_counts)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera um CSV de regressao funcional para PDFs do PRJ-13."
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=DEFAULT_PDF_DIR,
        help="Pasta raiz com os PDFs de teste.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Arquivo CSV de saida. Se omitido, usa storage/regression_reports.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita a quantidade de PDFs processados.",
    )
    args = parser.parse_args()

    output_path = args.output or _default_output_path(DEFAULT_OUTPUT_DIR)
    rows = build_report(args.pdf_dir, output_path, limit=args.limit)
    _print_summary(rows, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
