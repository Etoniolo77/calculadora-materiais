#!/usr/bin/env python3
"""
Regenera data/estruturas_materiais.csv a partir da aba "Lista Consolidada"
do workbook oficial de referência.
"""

from __future__ import annotations

import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXCEL_PATH = PROJECT_ROOT / "docs" / "Referencia_Tecnica" / "ESTRUTURAS PARA CALCULADORA MATERIAS.xlsx"
OUTPUT_CSV = PROJECT_ROOT / "data" / "estruturas_materiais.csv"
BACKUP_DIR = PROJECT_ROOT / "data" / "_backup_mestre"
SOURCE_SHEET = "Lista Consolidada"

EXPECTED_COLS = {
    "Estrutura": "estrutura_codigo",
    "Código Hana": "material_codigo",
    "Descricao": "material_descricao",
    "Descrição": "material_descricao",
    "Quantidade": "quantidade",
    "Aplicação": "estrutura_tipo_poste",
    "Aplicacao": "estrutura_tipo_poste",
}


def _normalize_header(value: str) -> str:
    return str(value or "").strip()


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def _clean_qty(value: object) -> str:
    text = _clean_text(value).upper().replace(" ", "")
    if not text:
        return ""
    text = text.replace("KG", "")
    text = text.replace(",", ".")
    return text


def backup_current_csv() -> None:
    if not OUTPUT_CSV.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"estruturas_materiais_backup_{timestamp}.csv"
    shutil.copy2(OUTPUT_CSV, backup_file)
    print(f"[OK] Backup criado: {backup_file}")


def main() -> int:
    if not EXCEL_PATH.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {EXCEL_PATH}")

    print(f"Lendo workbook: {EXCEL_PATH}")
    df = pd.read_excel(EXCEL_PATH, sheet_name=SOURCE_SHEET)
    raw_cols = [_normalize_header(col) for col in df.columns]

    rename_map: dict[str, str] = {}
    for col in raw_cols:
        if col in EXPECTED_COLS:
            rename_map[col] = EXPECTED_COLS[col]

    missing = {"estrutura_codigo", "material_codigo", "material_descricao", "quantidade", "estrutura_tipo_poste"} - set(rename_map.values())
    if missing:
        raise ValueError(f"Colunas obrigatorias ausentes na aba '{SOURCE_SHEET}': {sorted(missing)}")

    df.columns = raw_cols
    df = df.rename(columns=rename_map)
    df = df[list(rename_map.values())].copy()

    df["estrutura_codigo"] = df["estrutura_codigo"].map(_clean_text).str.upper()
    df["material_codigo"] = df["material_codigo"].map(_clean_text).str.split(".").str[0]
    df["material_descricao"] = df["material_descricao"].map(_clean_text)
    df["quantidade"] = df["quantidade"].map(_clean_qty)
    df["estrutura_tipo_poste"] = df["estrutura_tipo_poste"].map(_clean_text).str.upper()

    df = df[
        (df["estrutura_codigo"] != "")
        & (df["material_codigo"].str.fullmatch(r"\d{8}", na=False))
        & (df["material_descricao"] != "")
        & (df["quantidade"] != "")
    ].copy()

    # Mantém a primeira ocorrência para linhas idênticas.
    df = df.drop_duplicates(
        subset=[
            "estrutura_codigo",
            "material_codigo",
            "material_descricao",
            "quantidade",
            "estrutura_tipo_poste",
        ]
    )

    backup_current_csv()
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8",
        quoting=csv.QUOTE_MINIMAL,
    )

    print(f"[OK] CSV atualizado: {OUTPUT_CSV}")
    print(f"  Linhas: {len(df)}")
    print(f"  Estruturas unicas: {df['estrutura_codigo'].nunique()}")
    print(f"  Materiais unicos: {df['material_codigo'].nunique()}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[ERRO] {exc}")
        raise
