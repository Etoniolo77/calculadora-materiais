"""
patch_missing_structures.py
===========================
Adiciona/corrige materiais de estruturas ausentes no materials.db.
Executar após identificar gaps de integridade.

ESTRUTURAS CORRIGIDAS:
  - 1S3  : Estrutura de ancoragem de ramal 3 fios
  - 1HASTE: Haste de aterramento 5/8" 2.4m (alias de H5)
  - S3/S4: alias resolvidos via STRUCTURE_ALIASES no engine.py

FONTE: Catálogo técnico CPFL / Norma NE-01-0074
"""
import sqlite3

DB_PATH = "materials.db"

# Materiais a inserir/corrigir por estrutura
# Formato: (codigo_estrutura, tipo_poste, [(sap, descricao, quantidade)])
PATCHES = [
    # 1S3 — Estrutura de Ramal 3 fios (simples, armação secundária 1x3)
    # Similar a 1S4, mas para 3 derivações
    ("1S3", "ALL", [
        ("10004454", "ARMACAO SECUNDARIA 1X3",  1.0),
        ("10002167", "ISOLADOR ROLDANA 76X79MM", 1.0),
        ("VERIFICAR-POSTE", "PARAFUSO M16 x 250MM AC (verificar diametro poste)", 1.0),
    ]),

    # 1HASTE — Haste de Ancoragem (H3/H5 são aliases)
    # H5 = Haste 5/8" x 2.4m para aterramento/ancoragem
    ("1HASTE", "ALL", [
        ("30056366", "HASTE AT SIM AC 1020 COBR 5/8POL 2,4M", 1.0),
    ]),

    # Garantir que S3/S4 sem alias ainda mostrem algo útil
    # (o alias no engine.py já redireciona, mas por segurança)
    ("S3", "ALL", [
        ("VERIFICAR", "USAR ALIAS S3->1S3 (ver engine.py STRUCTURE_ALIASES)", 1.0),
    ]),
    ("S4", "ALL", [
        ("VERIFICAR", "USAR ALIAS S4->1S4 (ver engine.py STRUCTURE_ALIASES)", 1.0),
    ]),
]

def apply_patches():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for struct_code, pole_type, materials in PATCHES:
        # Verificar se a estrutura existe
        cursor.execute("SELECT id FROM estruturas WHERE codigo=? AND tipo_poste=?", 
                       (struct_code, pole_type))
        row = cursor.fetchone()
        
        if not row:
            # Criar a estrutura se não existir
            cursor.execute("""
                INSERT INTO estruturas (codigo, tipo_poste)
                VALUES (?, ?)
            """, (struct_code, pole_type))
            struct_id = cursor.lastrowid
            print(f"[CREATED] Estrutura {struct_code} ({pole_type}) criada no banco.")
        else:
            struct_id = row[0]
        
        # Remover materiais antigos de placeholder (VERIFICAR)
        cursor.execute("""
            DELETE FROM estrutura_materiais 
            WHERE estrutura_id=? AND material_codigo='VERIFICAR'
        """, (struct_id,))
        deleted = cursor.rowcount
        
        # Inserir/atualizar materiais
        for sap, desc, qty in materials:
            # Verificar se já existe
            cursor.execute("""
                SELECT id FROM estrutura_materiais 
                WHERE estrutura_id=? AND material_codigo=?
            """, (struct_id, sap))
            
            if cursor.fetchone():
                # Atualizar
                cursor.execute("""
                    UPDATE estrutura_materiais 
                    SET material_descricao=?, quantidade=?
                    WHERE estrutura_id=? AND material_codigo=?
                """, (desc, qty, struct_id, sap))
                action = "UPDATED"
            else:
                # Inserir
                cursor.execute("""
                    INSERT INTO estrutura_materiais 
                    (estrutura_id, material_codigo, material_descricao, quantidade)
                    VALUES (?, ?, ?, ?)
                """, (struct_id, sap, desc, qty))
                action = "INSERTED"
            
            print(f"[{action}] {struct_code} | {sap} | {desc[:40]} | qty={qty}")
        
        if deleted > 0:
            print(f"  (removidos {deleted} placeholders VERIFICAR de {struct_code})")
    
    conn.commit()
    conn.close()
    print("\n[OK] Patch aplicado com sucesso!")

if __name__ == "__main__":
    apply_patches()
    
    # Verificação pós-patch
    print("\n=== VERIFICACAO POS-PATCH ===")
    conn = sqlite3.connect(DB_PATH)
    for code in ["1S3", "1S4", "1HASTE"]:
        cur = conn.execute("""
            SELECT e.codigo, em.material_codigo, em.material_descricao, em.quantidade
            FROM estruturas e JOIN estrutura_materiais em ON e.id=em.estrutura_id
            WHERE e.codigo=?
        """, (code,))
        rows = cur.fetchall()
        print(f"\n{code}:")
        for r in rows:
            print(f"  SAP={r[1]} | {r[2][:40]} | qty={r[3]}")
    conn.close()
