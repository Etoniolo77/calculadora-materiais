"""
Script de Migração: JSON -> SQLite
Converte unified_db.json e master_data_bom.json para materials.db
"""
import json
import sqlite3
import csv
from pathlib import Path


def create_schema(conn: sqlite3.Connection):
    """Cria as tabelas do banco de dados."""
    cursor = conn.cursor()
    
    # Tabela de materiais SAP
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materiais (
            codigo TEXT PRIMARY KEY,
            descricao TEXT NOT NULL
        )
    """)
    
    # Tabela FTS5 para busca textual rápida
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS materiais_fts 
        USING fts5(codigo, descricao, content='materiais', content_rowid='rowid')
    """)
    
    # Triggers para manter FTS sincronizado
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS materiais_ai AFTER INSERT ON materiais BEGIN
            INSERT INTO materiais_fts(rowid, codigo, descricao) VALUES (new.rowid, new.codigo, new.descricao);
        END
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS materiais_ad AFTER DELETE ON materiais BEGIN
            INSERT INTO materiais_fts(materiais_fts, rowid, codigo, descricao) VALUES('delete', old.rowid, old.codigo, old.descricao);
        END
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS materiais_au AFTER UPDATE ON materiais BEGIN
            INSERT INTO materiais_fts(materiais_fts, rowid, codigo, descricao) VALUES('delete', old.rowid, old.codigo, old.descricao);
            INSERT INTO materiais_fts(rowid, codigo, descricao) VALUES (new.rowid, new.codigo, new.descricao);
        END
    """)
    
    # Tabela de estruturas (B1, N1, U4, etc.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estruturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL,
            tipo_poste TEXT DEFAULT 'ALL'
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_estruturas_codigo ON estruturas(codigo)")
    
    # Tabela de materiais por estrutura
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estrutura_materiais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            estrutura_id INTEGER NOT NULL,
            material_codigo TEXT NOT NULL,
            material_descricao TEXT,
            quantidade REAL NOT NULL,
            FOREIGN KEY (estrutura_id) REFERENCES estruturas(id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_est_mat_estrutura ON estrutura_materiais(estrutura_id)")
    
    # Tabela de categorias BOM (master_data_bom)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bom_categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT NOT NULL,
            subcategoria TEXT NOT NULL,
            UNIQUE(categoria, subcategoria)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bom_cat ON bom_categorias(categoria)")
    
    # Tabela de itens BOM
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bom_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria_id INTEGER NOT NULL,
            material_codigo TEXT NOT NULL,
            material_descricao TEXT,
            quantidade REAL NOT NULL,
            FOREIGN KEY (categoria_id) REFERENCES bom_categorias(id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bom_itens_cat ON bom_itens(categoria_id)")
    
    conn.commit()
    print("[OK] Schema criado com sucesso")


def migrate_unified_db(conn: sqlite3.Connection, json_path: Path):
    """Migra a biblioteca SAP de unified_db.json para SQLite."""
    if not json_path.exists():
        print(f"[AVISO] Arquivo não encontrado: {json_path}")
        return
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    cursor = conn.cursor()
    
    # 1. Migrar SAP Library (materiais)
    sap_library = data.get('sap_library', {})
    materiais_count = 0
    for codigo, descricao in sap_library.items():
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO materiais (codigo, descricao) VALUES (?, ?)",
                (str(codigo), str(descricao))
            )
            materiais_count += 1
        except Exception as e:
            print(f"  Erro ao inserir material {codigo}: {e}")
    
    conn.commit()
    print(f"[OK] {materiais_count} materiais migrados")


def migrate_legacy_structures_from_unified_db(conn: sqlite3.Connection, json_path: Path):
    """Fallback legado: migra estruturas do unified_db.json se o CSV mestre não existir."""
    if not json_path.exists():
        print(f"[AVISO] Arquivo não encontrado: {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    cursor = conn.cursor()
    structures = data.get('structures', {})
    estruturas_count = 0
    materiais_est_count = 0
    
    for codigo_estrutura, materiais_lista in structures.items():
        # Agrupar por tipo de poste
        tipos_encontrados = set()
        for mat in materiais_lista:
            tipos_encontrados.add(mat.get('type', 'ALL'))
        
        for tipo in tipos_encontrados:
            # Inserir estrutura
            cursor.execute(
                "INSERT INTO estruturas (codigo, tipo_poste) VALUES (?, ?)",
                (codigo_estrutura, tipo)
            )
            estrutura_id = cursor.lastrowid
            estruturas_count += 1
            
            # Inserir materiais desta estrutura/tipo
            for mat in materiais_lista:
                mat_tipo = mat.get('type', 'ALL')
                if mat_tipo == tipo:
                    cursor.execute(
                        """INSERT INTO estrutura_materiais 
                           (estrutura_id, material_codigo, material_descricao, quantidade) 
                           VALUES (?, ?, ?, ?)""",
                        (estrutura_id, mat.get('sap', ''), mat.get('desc', ''), mat.get('qty', 1))
                    )
                    materiais_est_count += 1
    
    conn.commit()
    print(f"[OK] {estruturas_count} estruturas legadas migradas")
    print(f"[OK] {materiais_est_count} materiais de estrutura legados migrados")


def _normalize_tipo_poste(value: str) -> str:
    raw = str(value or "ALL").upper().strip()
    if "TODOS EXETO" in raw:
        return "CIRCULAR"
    if "DT" in raw or "MADEIRA" in raw:
        return "DT"
    if "CIRCULAR" in raw or "FIBRA" in raw:
        return "CIRCULAR"
    return "ALL"


def migrate_structures_from_csv(conn: sqlite3.Connection, csv_path: Path):
    """Migra estruturas da lista mestra limpa data/estruturas_materiais.csv."""
    if not csv_path.exists():
        print(f"[AVISO] CSV de estruturas não encontrado: {csv_path}")
        return

    cursor = conn.cursor()
    estruturas_count = 0
    materiais_est_count = 0
    rejected_count = 0
    structure_ids: dict[tuple[str, str], int] = {}

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {
            "estrutura_codigo",
            "material_codigo",
            "material_descricao",
            "quantidade",
            "estrutura_tipo_poste",
        }
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV de estruturas sem colunas obrigatórias: {sorted(missing)}")

        for row in reader:
            estrutura = str(row.get("estrutura_codigo", "") or "").strip().upper()
            material = str(row.get("material_codigo", "") or "").strip()
            desc = str(row.get("material_descricao", "") or "").strip()
            tipo = _normalize_tipo_poste(str(row.get("estrutura_tipo_poste", "ALL")))
            bad_text = " ".join([estrutura, material, desc]).upper()
            if (
                not estrutura
                or not material
                or "VERIFICAR" in bad_text
                or "USAR ALIAS" in bad_text
            ):
                rejected_count += 1
                continue

            try:
                qty = float(str(row.get("quantidade", "1") or "1").replace(",", "."))
            except ValueError:
                qty = 1.0

            key = (estrutura, tipo)
            if key not in structure_ids:
                cursor.execute(
                    "INSERT INTO estruturas (codigo, tipo_poste) VALUES (?, ?)",
                    key,
                )
                structure_ids[key] = cursor.lastrowid
                estruturas_count += 1

            cursor.execute(
                """INSERT INTO estrutura_materiais
                   (estrutura_id, material_codigo, material_descricao, quantidade)
                   VALUES (?, ?, ?, ?)""",
                (structure_ids[key], material, desc, qty),
            )
            materiais_est_count += 1

    conn.commit()
    print(f"[OK] {estruturas_count} estruturas migradas do CSV mestre")
    print(f"[OK] {materiais_est_count} materiais de estrutura migrados do CSV mestre")
    if rejected_count:
        print(f"[AVISO] {rejected_count} linhas de estrutura rejeitadas por dados incompletos/placeholders")


def migrate_master_bom(conn: sqlite3.Connection, json_path: Path):
    """Migra master_data_bom.json para SQLite."""
    if not json_path.exists():
        print(f"[AVISO] Arquivo não encontrado: {json_path}")
        return
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    cursor = conn.cursor()
    categorias_count = 0
    itens_count = 0
    
    for categoria, subcategorias in data.items():
        if not isinstance(subcategorias, dict):
            continue
            
        for subcategoria, itens in subcategorias.items():
            if not isinstance(itens, list):
                continue
            
            # Inserir categoria
            cursor.execute(
                "INSERT OR IGNORE INTO bom_categorias (categoria, subcategoria) VALUES (?, ?)",
                (categoria, subcategoria)
            )
            
            # Buscar ID da categoria
            cursor.execute(
                "SELECT id FROM bom_categorias WHERE categoria = ? AND subcategoria = ?",
                (categoria, subcategoria)
            )
            cat_row = cursor.fetchone()
            if not cat_row:
                continue
            categoria_id = cat_row[0]
            categorias_count += 1
            
            # Inserir itens
            for item in itens:
                cursor.execute(
                    """INSERT INTO bom_itens 
                       (categoria_id, material_codigo, material_descricao, quantidade) 
                       VALUES (?, ?, ?, ?)""",
                    (categoria_id, item.get('codigo', ''), item.get('descricao', ''), item.get('quantidade', 1))
                )
                itens_count += 1
    
    conn.commit()
    print(f"[OK] {categorias_count} categorias BOM migradas")
    print(f"[OK] {itens_count} itens BOM migrados")


def rebuild_fts(conn: sqlite3.Connection):
    """Reconstrói o índice FTS5."""
    cursor = conn.cursor()
    cursor.execute("INSERT INTO materiais_fts(materiais_fts) VALUES('rebuild')")
    conn.commit()
    print("[OK] Índice FTS5 reconstruído")


def validate_migration(conn: sqlite3.Connection):
    """Valida a migração com algumas queries de teste."""
    cursor = conn.cursor()
    
    print("\n--- Validação ---")
    
    # Contagem de materiais
    cursor.execute("SELECT COUNT(*) FROM materiais")
    print(f"Total de materiais: {cursor.fetchone()[0]}")
    
    # Contagem de estruturas
    cursor.execute("SELECT COUNT(*) FROM estruturas")
    print(f"Total de estruturas: {cursor.fetchone()[0]}")
    
    # Contagem de categorias BOM
    cursor.execute("SELECT COUNT(*) FROM bom_categorias")
    print(f"Total de categorias BOM: {cursor.fetchone()[0]}")
    
    # Teste de busca FTS
    cursor.execute("SELECT codigo, descricao FROM materiais_fts WHERE materiais_fts MATCH 'POSTE' LIMIT 3")
    results = cursor.fetchall()
    print(f"Busca FTS 'POSTE': {len(results)} resultados")
    for r in results:
        print(f"  - {r[0]}: {r[1][:50]}...")


def main():
    project_root = Path(__file__).resolve().parents[1]
    data_dir = project_root / "data"
    db_path = data_dir / "materials.db"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Remover banco existente para recriar
    if db_path.exists():
        db_path.unlink()
        print(f"Banco anterior removido: {db_path}")
    
    print(f"\n=== Migração para SQLite ===")
    print(f"Destino: {db_path}\n")
    
    conn = sqlite3.connect(db_path)
    
    try:
        create_schema(conn)
        migrate_unified_db(conn, data_dir / "unified_db.json")
        structures_csv = data_dir / "estruturas_materiais.csv"
        if structures_csv.exists():
            migrate_structures_from_csv(conn, structures_csv)
        else:
            migrate_legacy_structures_from_unified_db(conn, data_dir / "unified_db.json")
        migrate_master_bom(conn, data_dir / "master_data_bom.json")
        rebuild_fts(conn)
        validate_migration(conn)

        print("\n[OK] Migracao concluida com sucesso!")
        print(f"Banco criado: {db_path}")
        print(f"Tamanho: {db_path.stat().st_size / 1024:.1f} KB")
        
    finally:
        conn.close()


if __name__ == "__main__":
    main()
