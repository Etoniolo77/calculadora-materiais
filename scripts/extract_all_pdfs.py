import json
import os
import re
import pdfplumber
from pathlib import Path

def extract_all_pdfs():
    base_dir = Path(".")
    pdf_files = list(base_dir.glob("Estruturas *.pdf"))
    print(f"Encontrados {len(pdf_files)} PDFs de estruturas.")
    
    unified_db = {
        "metadata": {
            "version": "2.1",
            "description": "Unified DB with Pole Type Conditions (Table Extraction)",
            "generated_at": "2026-01-13"
        },
        "sap_library": {},
        "structures": {},
        "hardware_kits": {}, 
    }
    
    # Pré-carregar kits manuais
    unified_db["hardware_kits"]["ESTAI_CC_14M"] = [{"sap": "30056363", "desc": "HASTE ANCOR AC 1020 3200DAN 16MM 1,6M", "qty": 1}, {"sap": "30054507", "desc": "CORDOALHA ACO CARB 9,5MM 7F CL.B MR/SM", "qty": 14}]
    unified_db["hardware_kits"]["PARA_RAIO_CONJUNTO"] = [{"sap": "30053319", "desc": "COBERTURA PROT PARA-RAIO 13,8KV", "qty": 1}]

    for pdf_path in pdf_files:
        print(f"Processando {pdf_path.name}...")
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    current_structure = None
                    
                    for table in tables:
                        for row in table:
                            # Skip empty rows (all None/Empty)
                            if not any(row): continue
                            
                            # Converter None para string vazia
                            row_vals = [str(x or '').strip() for x in row]
                            
                            # Detectar Header Tabela -> Skip
                            if "ESTRUTURA" in row_vals[0] or "MATERIAL" in row_vals[4]:
                                continue
                                
                            # Atualizar Estrutura (Forward Fill)
                            # Se col 0 tem algo como "N4", atualiza. Se vazio, mantem anterior.
                            cand = row_vals[0]
                            # Heuristica: estrutura tem tamanho pequeno (N4, ET4A)
                            # E não é "ver. POSTE" ou codigo
                            if cand and len(cand) < 6 and not cand.lower().startswith('ver'):
                                # Limpar lixo ex: "N4 MT" -> "N4"
                                match = re.match(r'^([A-Z0-9]+)', cand)
                                if match:
                                    current_structure = match.group(1)
                                    if current_structure not in unified_db["structures"]:
                                        unified_db["structures"][current_structure] = []
                            
                            if not current_structure: continue
                            
                            # Extrair dados
                            # Buscar coluna com código SAP (8 digitos)
                            code = None
                            qty = 0.0
                            desc = ""
                            col_circ = ""
                            col_dt = ""
                            idx_sap = -1
                            
                            # Varrer colunas 1 e 2 procurando o SAP
                            for i in [1, 2]:
                                if i < len(row_vals):
                                    val = row_vals[i]
                                    if re.match(r'^\d{8}$', val):
                                        code = val
                                        idx_sap = i
                                        break
                                    if "ver. POSTE" in val or "ver. CABO" in val:
                                         code = "VERIFICAR-" + val.replace('ver. ', '')
                                         idx_sap = i
                                         break
                            
                            if not code: continue
                            
                            # Qty está logo depois do SAP
                            if idx_sap + 1 < len(row_vals):
                                try:
                                    # "3,60 CM" -> 3.60
                                    q_str = row_vals[idx_sap+1].replace(',', '.').split()[0]
                                    qty = float(q_str)
                                except: qty = 1.0
                                
                            # Descrição está logo depois da Qty
                            if idx_sap + 2 < len(row_vals):
                                desc = row_vals[idx_sap+2]
                                
                            # Circular e DT são as ultimas 2 colunas
                            col_circ = row_vals[-2]
                            col_dt = row_vals[-1]
                            
                            # Lógica de Tipo
                            usage_type = "ALL"
                            qty_dt = qty
                            
                            has_circ = (col_circ.upper() == 'X' or re.match(r'^\d+x?$', col_circ))
                            has_dt = (col_dt.upper() == 'X' or re.match(r'^\d+x?.*$', col_dt))
                            
                            # Override Qty DT
                            if re.match(r'^\d+x', col_dt):
                                try:
                                    qty_dt = float(col_dt.split('x')[0])
                                    has_dt = True
                                except: pass
                                
                            target_list = unified_db["structures"][current_structure]
                            
                            if has_circ and has_dt:
                                if qty_dt != qty:
                                   target_list.append({"sap": code, "desc": desc, "qty": qty, "type": "CIRCULAR"})
                                   target_list.append({"sap": code, "desc": desc, "qty": qty_dt, "type": "DT"})
                                else:
                                   target_list.append({"sap": code, "desc": desc, "qty": qty, "type": "ALL"})
                            elif has_circ:
                                target_list.append({"sap": code, "desc": desc, "qty": qty, "type": "CIRCULAR"})
                            elif has_dt:
                                target_list.append({"sap": code, "desc": desc, "qty": qty, "type": "DT"})
                            else:
                                # Se nenhum marcado, as vezes é erro.
                                # Mas se tem código valido, vamos assumir ALL por segurança?
                                # Ou ignorar? Melhor ignorar item fantasma.
                                pass

                            if code not in unified_db["sap_library"] and not code.startswith("VERIFICAR"):
                                unified_db["sap_library"][code] = desc

        except Exception as e:
            print(f"Erro abrindo {pdf_path}: {e}")

    # --- APLICAR REGRAS DE NEGÓCIO (OVERRIDES) ---
    print("Aplicando regras de negócio (Selas=DT, Cintas=Circular)...")
    for struct_code, items in unified_db["structures"].items():
        for item in items:
            desc_upper = item["desc"].upper()
            
            # Regra 1: Selas são sempre para DT
            if "SELA" in desc_upper:
                item["type"] = "DT"
                
            # Regra 2: Cintas são sempre para Circular
            elif "CINTA" in desc_upper:
                item["type"] = "CIRCULAR"

    # Salvar
    with open("unified_db.json", "w", encoding="utf-8") as f:
        json.dump(unified_db, f, indent=2, ensure_ascii=False)
        
    print(f"MIGRAÇÃO TABELA CONCLUÍDA. {len(unified_db['structures'])} estruturas extraídas.")

if __name__ == "__main__":
    extract_all_pdfs()
