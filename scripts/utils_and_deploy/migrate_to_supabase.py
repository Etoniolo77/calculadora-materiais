import sqlite3
import os
import sys
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# Resolver caminhos
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"
SQLITE_DB_PATH = PROJECT_ROOT / "data" / "materials.db"

# Carregar variáveis do .env do backend
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    print(f"[AVISO] Arquivo .env não encontrado em {ENV_PATH}. Usando variáveis de ambiente globais.")

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

def migrate():
    if not SUPABASE_DB_URL or "SEU_PROJETO" in SUPABASE_DB_URL:
        print("[ERRO] SUPABASE_DB_URL não configurado ou com valor padrão no seu .env!")
        print("Edite o arquivo backend/.env e informe a Connection URI do seu banco Supabase.")
        sys.exit(1)
        
    if not SQLITE_DB_PATH.exists():
        print(f"[ERRO] Banco de dados SQLite local não encontrado em: {SQLITE_DB_PATH}")
        sys.exit(1)

    print(f"--- INICIANDO MIGRAÇÃO DO SQLITE PARA SUPABASE POSTGRESQL ---")
    print(f"Origem (SQLite): {SQLITE_DB_PATH}")
    print(f"Destino (Supabase): {SUPABASE_DB_URL.split('@')[-1]}") # Printa apenas host e porta sem credenciais

    # Conectar SQLite
    lite_conn = sqlite3.connect(SQLITE_DB_PATH)
    lite_cur = lite_conn.cursor()

    # Conectar Postgres
    try:
        pg_conn = psycopg2.connect(SUPABASE_DB_URL)
        pg_cur = pg_conn.cursor()
    except Exception as e:
        print(f"[ERRO] Falha ao conectar ao banco de dados Supabase: {e}")
        lite_conn.close()
        sys.exit(1)

    try:
        # 1. Habilitar pg_trgm no destino
        print("\nHabilitando extensão pg_trgm...")
        pg_cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        
        # 2. Migrar materiais
        print("\n[1/3] Carregando materiais...")
        lite_cur.execute("SELECT codigo, descricao FROM materiais")
        materials = lite_cur.fetchall()
        print(f"Encontrados {len(materials)} materiais no SQLite. Iniciando inserção...")
        
        # Batch insert com ON CONFLICT UPDATE
        pg_query = """
            INSERT INTO materiais (codigo, descricao) 
            VALUES %s 
            ON CONFLICT (codigo) DO UPDATE 
            SET descricao = EXCLUDED.descricao
        """
        execute_values(pg_cur, pg_query, materials, page_size=1000)
        print(f"[OK] {len(materials)} materiais sincronizados no Supabase.")

        # 3. Migrar estruturas
        print("\n[2/3] Carregando estruturas...")
        lite_cur.execute("SELECT id, codigo, tipo_poste FROM estruturas")
        estruturas = lite_cur.fetchall()
        print(f"Encontradas {len(estruturas)} estruturas no SQLite. Iniciando inserção...")
        
        # Limpar tabela destino ou fazer ON CONFLICT
        # Para estruturas, id é SERIAL. Vamos garantir o ID exato para manter integridade com as relações.
        pg_query = """
            INSERT INTO estruturas (id, codigo, tipo_poste) 
            VALUES %s 
            ON CONFLICT (id) DO UPDATE 
            SET codigo = EXCLUDED.codigo, tipo_poste = EXCLUDED.tipo_poste
        """
        execute_values(pg_cur, pg_query, estruturas, page_size=1000)
        print(f"[OK] {len(estruturas)} estruturas sincronizadas.")

        # 4. Migrar estrutura_materiais
        print("\n[3/3] Carregando estrutura_materiais...")
        lite_cur.execute("SELECT id, estrutura_id, material_codigo, material_descricao, quantidade FROM estrutura_materiais")
        em_rows = lite_cur.fetchall()
        print(f"Encontradas {len(em_rows)} relações estrutura-materiais no SQLite. Iniciando inserção...")
        
        # Normalizar quantidades e limpar NaNs/valores nulos
        normalized_em = []
        for r in em_rows:
            rid, est_id, m_code, m_desc, qty = r
            # Normalizar quantidade
            try:
                qty_val = float(qty)
                if qty_val != qty_val:  # NaN check
                    qty_val = 0.0
            except:
                qty_val = 0.0
            normalized_em.append((rid, est_id, m_code, m_desc or '', qty_val))

        pg_query = """
            INSERT INTO estrutura_materiais (id, estrutura_id, material_codigo, material_descricao, quantidade) 
            VALUES %s 
            ON CONFLICT (id) DO UPDATE 
            SET estrutura_id = EXCLUDED.estrutura_id,
                material_codigo = EXCLUDED.material_codigo,
                material_descricao = EXCLUDED.material_descricao,
                quantidade = EXCLUDED.quantidade
        """
        execute_values(pg_cur, pg_query, normalized_em, page_size=1000)
        print(f"[OK] {len(normalized_em)} materiais de estruturas sincronizados.")

        # 5. Ajustar sequências do SERIAL no Postgres
        print("\nSincronizando sequências do SERIAL do PostgreSQL...")
        pg_cur.execute("SELECT setval('estruturas_id_seq', COALESCE((SELECT MAX(id)+1 FROM estruturas), 1), false)")
        pg_cur.execute("SELECT setval('estrutura_materiais_id_seq', COALESCE((SELECT MAX(id)+1 FROM estrutura_materiais), 1), false)")
        
        pg_conn.commit()
        print("\n=============================================")
        print("MIGRAÇÃO DE DADOS COMPLETA COM SUCESSO!")
        print("=============================================")

    except Exception as e:
        pg_conn.rollback()
        print(f"\n[ERRO CRÍTICO] Falha durante a migração. Nenhuma alteração foi salva no Supabase. Detalhe: {e}")
    finally:
        lite_conn.close()
        pg_conn.close()

if __name__ == "__main__":
    migrate()
