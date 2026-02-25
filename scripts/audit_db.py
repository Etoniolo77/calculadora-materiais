import json
import sqlite3
import os

def audit():
    unified_path = 'unified_db.json'
    db_path = 'materials.db'
    
    if not os.path.exists(unified_path) or not os.path.exists(db_path):
        print("Arquivos de dados não encontrados.")
        return

    with open(unified_path, 'r', encoding='utf-8') as f:
        unified_data = json.load(f)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Verificar SAP Library
    cursor.execute("SELECT codigo FROM materiais")
    db_sap_codes = {str(row[0]) for row in cursor.fetchall()}
    json_sap_codes = set(unified_data['sap_library'].keys())
    
    missing_sap = json_sap_codes - db_sap_codes
    print(f"SAP Library: {len(json_sap_codes)} no JSON, {len(db_sap_codes)} no DB. Faltando: {len(missing_sap)}")

    # 2. Verificar Estruturas
    cursor.execute("SELECT codigo FROM estruturas")
    db_structures = {str(row[0]) for row in cursor.fetchall()}
    json_structures = set(unified_data['structures'].keys())
    
    missing_structs = json_structures - db_structures
    print(f"Estruturas: {len(json_structures)} no JSON, {len(db_structures)} no DB. Faltando: {len(missing_structs)}")
    
    if missing_structs:
        print(f"Exemplos de estruturas faltando: {list(missing_structs)[:10]}")

    # 3. Verificar se as estruturas no DB têm materiais
    cursor.execute("""
        SELECT e.codigo, COUNT(em.id) 
        FROM estruturas e 
        LEFT JOIN estrutura_materiais em ON e.id = em.estrutura_id 
        GROUP BY e.codigo 
        HAVING COUNT(em.id) = 0
    """)
    empty_structs = cursor.fetchall()
    print(f"Estruturas no DB sem nenhum material: {len(empty_structs)}")
    if empty_structs:
        print(f"Exemplos: {[row[0] for row in empty_structs[:10]]}")

    conn.close()

if __name__ == "__main__":
    audit()
