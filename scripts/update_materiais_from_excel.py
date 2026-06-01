#!/usr/bin/env python3
"""
Script para atualizar a lista mestre de materiais a partir do Excel de referência.

IMPORTANTE:
- Apenas a aba "Lista Consolidada" é fonte de dados.
- As demais abas do arquivo Excel são ignoradas por serem rascunhos/intermediárias.

Lê ESTRUTURAS PARA CALCULADORA MATERIAS.xlsx e atualiza unified_db.json
com novos códigos SAP e descrições.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

import pandas as pd

# Caminhos
EXCEL_PATH = Path("docs/Referencia_Tecnica/ESTRUTURAS PARA CALCULADORA MATERIAS.xlsx")
DB_PATH = Path("data/unified_db.json")
BACKUP_PATH = Path("data/_backup_mestre")
SOURCE_SHEET = "Lista Consolidada"


def backup_current_db():
    """Cria backup do banco atual antes de modificar"""
    if not DB_PATH.exists():
        print("AVISO: Banco de dados nao encontrado. Sera criado novo.")
        return

    BACKUP_PATH.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_PATH / f"unified_db_backup_{timestamp}.json"

    with open(DB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[OK] Backup criado: {backup_file}")


def load_current_db() -> Dict:
    """Carrega banco de dados atual"""
    if not DB_PATH.exists():
        return {
            "metadata": {
                "version": "4.0",
                "description": "Unified DB atualizado com Excel de Referência",
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "sources": ["ESTRUTURAS PARA CALCULADORA MATERIAS.xlsx"],
            },
            "sap_library": {},
        }

    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def read_excel_materials(excel_path: Path) -> Dict[str, str]:
    """
    Lê materiais do Excel.

    Espera estrutura:
    - Coluna A: Código SAP (8 dígitos)
    - Coluna B: Descrição do material

    Returns:
        Dict {codigo_sap: descricao}
    """
    if not excel_path.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {excel_path}")

    print(f"Lendo {excel_path.name}...")

    # Verificar abas disponíveis
    xls = pd.ExcelFile(excel_path)
    print(f"Abas disponiveis: {', '.join(xls.sheet_names)}")

    if SOURCE_SHEET not in xls.sheet_names:
        raise ValueError(
            f"Aba '{SOURCE_SHEET}' nao encontrada! "
            f"Abas disponiveis: {', '.join(xls.sheet_names)}"
        )

    ignored = [s for s in xls.sheet_names if s != SOURCE_SHEET]
    if ignored:
        print(f"  [INFO] Abas ignoradas: {', '.join(ignored)}")

    print(f"\n[FONTE DA VERDADE] Processando aba exclusiva: '{SOURCE_SHEET}'")
    df = pd.read_excel(excel_path, sheet_name=SOURCE_SHEET)

    # Mostrar estrutura
    print(f"  Colunas: {df.columns.tolist()}")
    print(f"  Linhas: {len(df)}")

    # Detectar colunas de código e descrição
    codigo_col = None
    desc_col = None

    for col in df.columns:
        col_lower = str(col).lower()
        # Procurar por "Código Hana" ou variações
        if any(x in col_lower for x in ["código", "codigo", "hana", "sap", "material"]):
            codigo_col = col
        # Procurar por "Descrição" ou variações
        elif any(x in col_lower for x in ["descrição", "descricao", "descri"]):
            desc_col = col

    # Se não detectou, usar as duas primeiras colunas
    if codigo_col is None:
        codigo_col = df.columns[0] if len(df.columns) > 0 else None
    if desc_col is None:
        desc_col = df.columns[1] if len(df.columns) > 1 else None

    if not codigo_col or not desc_col:
        raise ValueError(
            f"Nao foi possivel identificar colunas de codigo/descricao. "
            f"Colunas disponiveis: {df.columns.tolist()}"
        )

    print(f"  Mapeamento: '{codigo_col}' -> '{desc_col}'")

    # Processar linhas
    materiais = {}
    count = 0
    erros = 0

    for idx, row in df.iterrows():
        codigo = str(row[codigo_col]).strip()
        desc = str(row[desc_col]).strip() if desc_col else ""

        # Validar código SAP (8 dígitos)
        if codigo and codigo != "nan" and len(codigo) == 8 and codigo.isdigit():
            if desc and desc != "nan":
                materiais[codigo] = desc
                count += 1
            else:
                erros += 1
        elif codigo and codigo != "nan":
            erros += 1

    print(f"  [OK] {count} materiais validos extraidos")
    if erros > 0:
        print(f"  [AVISO] {erros} linhas ignoradas (codigo invalido ou sem descricao)")

    return materiais


def merge_materials(
    current_db: Dict, new_materials: Dict[str, str]
) -> tuple[Dict, Dict]:
    """
    Merge novos materiais com banco atual.

    Returns:
        (updated_db, stats)
    """
    stats = {
        "total_antes": len(current_db.get("sap_library", {})),
        "novos": 0,
        "atualizados": 0,
        "mantidos": 0,
    }

    sap_lib = current_db.get("sap_library", {})

    for codigo, descricao in new_materials.items():
        if codigo not in sap_lib:
            # Novo material
            sap_lib[codigo] = descricao
            stats["novos"] += 1
        elif sap_lib[codigo] != descricao:
            # Material existe mas descrição diferente
            print(f"  AVISO: Atualizado {codigo}:")
            print(f"     Antes: {sap_lib[codigo]}")
            print(f"     Depois: {descricao}")
            sap_lib[codigo] = descricao
            stats["atualizados"] += 1
        else:
            # Material já existe com mesma descrição
            stats["mantidos"] += 1

    current_db["sap_library"] = sap_lib
    stats["total_depois"] = len(sap_lib)

    # Atualizar metadata
    current_db["metadata"]["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    if "ESTRUTURAS PARA CALCULADORA MATERIAS.xlsx" not in current_db["metadata"].get(
        "sources", []
    ):
        current_db["metadata"]["sources"].append(
            "ESTRUTURAS PARA CALCULADORA MATERIAS.xlsx"
        )

    return current_db, stats


def save_db(db: Dict, path: Path):
    """Salva banco de dados atualizado"""
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"[OK] Banco atualizado salvo: {path}")


def main():
    """Execução principal"""
    print("=" * 60)
    print("ATUALIZACAO DA LISTA MESTRE DE MATERIAIS")
    print("=" * 60)

    try:
        # 1. Backup
        print("\n[1/5] Criando backup...")
        backup_current_db()

        # 2. Carregar banco atual
        print("\n[2/5] Carregando banco atual...")
        current_db = load_current_db()
        print(f"   Materiais atuais: {len(current_db.get('sap_library', {}))}")

        # 3. Ler materiais do Excel
        print("\n[3/5] Lendo materiais do Excel...")
        new_materials = read_excel_materials(EXCEL_PATH)
        print(f"   Materiais do Excel: {len(new_materials)}")

        # 4. Merge
        print("\n[4/5] Mesclando materiais...")
        updated_db, stats = merge_materials(current_db, new_materials)

        # 5. Salvar
        print("\n[5/5] Salvando banco atualizado...")
        save_db(updated_db, DB_PATH)

        # 6. Relatório
        print("\n" + "=" * 60)
        print("RELATORIO DE ATUALIZACAO")
        print("=" * 60)
        print(f"Materiais antes:      {stats['total_antes']:>6}")
        print(f"Novos adicionados:    {stats['novos']:>6}")
        print(f"Atualizados:          {stats['atualizados']:>6}")
        print(f"Mantidos:             {stats['mantidos']:>6}")
        print(f"{'-' * 30}")
        print(f"Materiais depois:     {stats['total_depois']:>6}")
        print("=" * 60)

        if stats["novos"] > 0 or stats["atualizados"] > 0:
            print("\n[OK] Atualizacao concluida com sucesso!")
        else:
            print("\n[OK] Nenhuma alteracao necessaria. Banco ja esta atualizado.")

        return 0

    except Exception as e:
        print(f"\n[ERRO] {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
