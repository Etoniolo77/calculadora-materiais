"""
export_db_to_excel.py
=====================
Exporta todas as tabelas do materials.db para um único arquivo Excel
com múltiplas abas. Serve como backup auditável antes de remover
os arquivos .xlsx originais da pasta Regras_Kits.

Abas geradas:
  - RESUMO           → contagem geral e metadados da exportação
  - ESTRUTURAS       → tabela de estruturas construtivas
  - MATERIAIS        → tabela de materiais SAP
  - ESTRUTURA_MATS   → relação completa estrutura → materiais (view legível)
  - POR_ESTRUTURA_*  → uma aba por estrutura com seus materiais (opcional --detalhado)

Uso:
  python scripts/export_db_to_excel.py
  python scripts/export_db_to_excel.py --detalhado  (aba por estrutura)
"""
import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH  = DATA_DIR / "materials.db"
OUT_DIR  = BASE_DIR / "Bases_Dados"
OUT_FILE = OUT_DIR / f"EXPORT_DB_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

DETALHADO = "--detalhado" in sys.argv

def main():
    if not DB_PATH.exists():
        print(f"[ERRO] Banco não encontrado: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)

    # ── Carregar tabelas ──────────────────────────────────────────────────────
    df_est = pd.read_sql("SELECT * FROM estruturas ORDER BY codigo, tipo_poste", conn)
    df_mat = pd.read_sql("SELECT * FROM materiais ORDER BY codigo", conn)
    df_rel = pd.read_sql("""
        SELECT
            e.codigo          AS estrutura,
            e.tipo_poste      AS tipo_poste,
            em.material_codigo AS sap,
            em.material_descricao AS descricao,
            em.quantidade     AS quantidade
        FROM estrutura_materiais em
        JOIN estruturas e ON e.id = em.estrutura_id
        ORDER BY e.codigo, e.tipo_poste, em.material_codigo
    """, conn)

    total_relacoes = len(df_rel)
    total_est       = len(df_est)
    total_mat       = len(df_mat)

    conn.close()

    # ── Escrever Excel ────────────────────────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    writer = pd.ExcelWriter(OUT_FILE, engine="openpyxl")

    # Aba RESUMO
    df_resumo = pd.DataFrame({
        "Item": [
            "Data de exportação",
            "Banco de dados",
            "Total de estruturas",
            "Total de materiais SAP",
            "Total de relações estrutura-material",
            "Gerado por",
        ],
        "Valor": [
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            str(DB_PATH.relative_to(BASE_DIR)),
            total_est,
            total_mat,
            total_relacoes,
            "export_db_to_excel.py",
        ]
    })
    df_resumo.to_excel(writer, sheet_name="RESUMO", index=False)

    # Aba ESTRUTURAS
    df_est.to_excel(writer, sheet_name="ESTRUTURAS", index=False)

    # Aba MATERIAIS
    df_mat.to_excel(writer, sheet_name="MATERIAIS", index=False)

    # Aba ESTRUTURA_MATS (view completa)
    df_rel.to_excel(writer, sheet_name="ESTRUTURA_MATS", index=False)

    # Abas detalhadas opcionais (uma por estrutura)
    if DETALHADO:
        estruturas = df_rel["estrutura"].unique()
        print(f"Gerando {len(estruturas)} abas detalhadas...")
        for est in sorted(estruturas):
            df_sub = df_rel[df_rel["estrutura"] == est].drop(columns=["estrutura"])
            sheet_name = est[:31]  # Excel limita a 31 chars
            df_sub.to_excel(writer, sheet_name=sheet_name, index=False)

    # ── Formatar larguras de coluna ───────────────────────────────────────────
    for sheet_name in writer.sheets:
        ws = writer.sheets[sheet_name]
        for col in ws.columns:
            max_len = max(
                (len(str(cell.value)) if cell.value else 0 for cell in col),
                default=10
            )
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

    writer.close()

    print(f"\n[OK] Exportação concluída!")
    print(f"     Arquivo: {OUT_FILE}")
    print(f"     Estruturas: {total_est}")
    print(f"     Materiais SAP: {total_mat}")
    print(f"     Relações: {total_relacoes}")
    print(f"     Abas geradas: {'4 + detalhe' if DETALHADO else '4'}")

if __name__ == "__main__":
    main()
