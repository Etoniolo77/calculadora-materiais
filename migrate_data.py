import json
import os
import re
import pdfplumber
from pathlib import Path
from database_loader import DatabaseLoader

def extract_pdf_data():
    """Extrai estruturas dos PDFs usando lógica de tabela robusta"""
    base_dir = Path(".")
    pdf_files = list(base_dir.glob("Estruturas *.pdf"))
    pdf_results = {}
    
    for pdf_path in pdf_files:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    current_structure = None
                    for table in tables:
                        for row in table:
                            if not any(row): continue
                            row_vals = [str(x or '').strip() for x in row]
                            
                            # Detectar Header Tabela -> Skip
                            if "ESTRUTURA" in row_vals[0] or "MATERIAL" in row_vals[4]:
                                continue
                                
                            # Atualizar Estrutura (Forward Fill)
                            cand = row_vals[0]
                            if cand and len(cand) < 6 and not cand.lower().startswith('ver'):
                                match = re.match(r'^([A-Z0-9]+)', cand)
                                if match:
                                    current_structure = match.group(1)
                                    if current_structure not in pdf_results:
                                        pdf_results[current_structure] = []
                            
                            if not current_structure: continue
                            
                            # Extrair dados
                            code = None
                            idx_sap = -1
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
                            
                            # Quantidade
                            qty = 1.0
                            if idx_sap + 1 < len(row_vals):
                                try:
                                    q_str = row_vals[idx_sap+1].replace(',', '.').split()[0]
                                    qty = float(q_str)
                                except: pass
                                
                            desc = row_vals[idx_sap+2] if idx_sap + 2 < len(row_vals) else ""
                            col_circ = row_vals[-2]
                            col_dt = row_vals[-1]
                            
                            qty_dt = qty
                            has_circ = (col_circ.upper() == 'X' or re.match(r'^\d+x?$', col_circ))
                            has_dt = (col_dt.upper() == 'X' or re.match(r'^\d+x?.*$', col_dt))
                            
                            if re.match(r'^\d+x', col_dt):
                                try:
                                    qty_dt = float(col_dt.split('x')[0])
                                    has_dt = True
                                except: pass
                                
                            target_list = pdf_results[current_structure]
                            
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
                                
        except Exception as e:
            print(f"Erro no PDF {pdf_path}: {e}")
            
    return pdf_results

def migrate():
    print("--- INICIANDO CONSOLIDAÇÃO DO BANCO DE DADOS UNIFICADO ---")
    
    # 1. Carregar Dados Legados (Excel)
    db = DatabaseLoader()
    db.load_all(force_legacy=True)
    
    # 2. Extrair Dados Novos (PDF)
    pdf_structures = extract_pdf_data()
    print(f"Estruturas extraídas dos PDFs: {len(pdf_structures)}")
    
    unified_db = {
        "metadata": {
            "version": "2.0",
            "description": "Banco Consolidado (Excel + Kits + PDF) com Hardwares Especiais",
            "generated_at": "2026-01-13"
        },
        "sap_library": db.sap_codes,
        "structures": {},
        "hardware_kits": {},
        "cinta_lookup": {
            # Baseado na Imagem: Poste -> {Tipo -> Diâmetro}
            "9/300":  {"CINTA 1": 180, "NIVEL 1": 180, "ESTAI 1": 180, "RECK 1": 200},
            "9/600":  {"CINTA 1": 200, "NIVEL 1": 200, "ESTAI 1": 200, "RECK 1": 220},
            "11/300": {"CINTA 1": 180, "NIVEL 1": 180, "ESTAI 1": 180, "RECK 1": 200}, # Assumi igual 9/300 (fallback)
            "11/600": {"CINTA 1": 200, "NIVEL 1": 200, "ESTAI 1": 200, "RECK 1": 240},
            "12/300": {"CINTA 1": 180, "NIVEL 1": 180, "ESTAI 1": 180, "RECK 1": 200, "CINTA 2": 200, "NIVEL 2": 200, "ESTAI 2": 200, "RECK 2": 220, "SECUNDARIA": 240, "LUMINARIA": 240},
            "12/600": {"CINTA 1": 200, "NIVEL 1": 200, "ESTAI 1": 200, "RECK 1": 220, "CINTA 2": 220, "NIVEL 2": 220, "ESTAI 2": 220, "RECK 2": 240, "SECUNDARIA": 260, "LUMINARIA": 260},
            "12/1000": {"CINTA 1": 240, "NIVEL 1": 240, "ESTAI 1": 240, "RECK 1": 260, "CINTA 2": 260, "NIVEL 2": 260, "ESTAI 2": 260, "RECK 2": 280, "SECUNDARIA": 300, "LUMINARIA": 300},
            "12/1500": {"CINTA 1": 300, "NIVEL 1": 300, "ESTAI 1": 300, "RECK 1": 320, "CINTA 2": 320, "NIVEL 2": 320, "ESTAI 2": 320, "RECK 2": 340, "SECUNDARIA": 360, "LUMINARIA": 360},
            "13/1000": {"CINTA 1": 240, "NIVEL 1": 240, "ESTAI 1": 240, "RECK 1": 260, "CINTA 2": 260, "NIVEL 2": 260, "ESTAI 2": 260, "RECK 2": 280, "SECUNDARIA": 300, "LUMINARIA": 320},
            "13/1500": {"CINTA 1": 300, "NIVEL 1": 300, "ESTAI 1": 300, "RECK 1": 320, "CINTA 2": 320, "NIVEL 2": 320, "ESTAI 2": 320, "RECK 2": 340, "SECUNDARIA": 360, "LUMINARIA": 380},
            "14/1000": {"CINTA 1": 240, "NIVEL 1": 240, "ESTAI 1": 240, "RECK 1": 260, "CINTA 2": 260, "NIVEL 2": 260, "ESTAI 2": 260, "RECK 2": 280, "SECUNDARIA": 300, "LUMINARIA": 320},
            "DT 12/1000": {"CINTA 1": 240, "SECUNDARIA": 300} # Exemplo DT
        }
    }
    
    # Adicionar itens de hardware de Trafos (Imagens)
    unified_db["hardware_kits"]["TRAFO_MONO"] = [
        {"sap": "10005317", "qty": 1, "desc": "PARA RAIO DISTR ZNO 12KV 10KA S/CENT"},
        {"sap": "10006953", "qty": 3, "desc": "CONECTOR TERM ESTRANGUL TIPO 4 1FURO"},
        {"sap": "30028581", "qty": 1, "desc": "CONECTOR TERM ESTRANGUL TIPO 1 1FURO"},
        {"sap": "10004254", "qty": 5, "desc": "CABO E ISO CU PVC BWF 70 MM2 750V PR"},
        {"sap": "10010733", "qty": 7, "desc": "CABO PROTEGIDO CU 15KV XLPE CZ 16MM2"},
        {"sap": "10002581", "qty": 2, "desc": "COBERTURA PROTETORA PARA TERM. DE EQPTO"},
        {"sap": "10011197", "qty": 3, "desc": "CONECTOR CUNHA CN51 PROT CORR GALVÂNICA"},
        {"sap": "10004823", "qty": 2, "desc": "KS"},
        {"sap": "30028579", "qty": 1, "desc": "CONECTOR 4 DERIVACOES"},
        {"sap": "10003042", "qty": 3, "desc": "CONECTOR CUNHA RAMAL TIPO I"},
        {"sap": "10003043", "qty": 3, "desc": "CONECTOR CUNHA RAMAL TIPO II"}
    ]
    
    unified_db["hardware_kits"]["TRAFO_TRI_45"] = [
        {"sap": "10005317", "qty": 3, "desc": "PARA RAIO DISTR ZNO 12KV 10KA S/CENT"},
        {"sap": "10006953", "qty": 4, "desc": "CONECTOR TERM ESTRANGUL TIPO 4 2FUROS"},
        {"sap": "30028581", "qty": 3, "desc": "CONECTOR TERM ESTRANGUL TIPO 1 1FURO"},
        {"sap": "10004254", "qty": 8, "desc": "CABO E ISO CU PVC BWF 70MM2 750V PR"},
        {"sap": "10010733", "qty": 12, "desc": "CABO PROTEGIDO CU 15KV XLPE CZ 16MM2"},
        {"sap": "10002581", "qty": 6, "desc": "COBERTURA PROTETORA PARA TERM. DE EQPTO"},
        {"sap": "10000436", "qty": 6, "desc": "CONECTOR CUNHA RD CN5"},
        {"sap": "10011197", "qty": 3, "desc": "CONECTOR CUNHA CN51 PROT CORR GALVÂNICA"},
        {"sap": "10011198", "qty": 3, "desc": "CONECTOR CUNHA CN53 PROT CORR GALVÂNICA"},
        {"sap": "30028579", "qty": 1, "desc": "CONECTOR 4 DERIVACOES"},
        {"sap": "10003042", "qty": 6, "desc": "CONECTOR CUNHA RAMAL TIPO I"},
        {"sap": "10003043", "qty": 3, "desc": "CONECTOR CUNHA RAMAL TIPO II"},
        {"sap": "10004823", "qty": 6, "desc": "CONECT PARAF FEN LIG CO 10-35MM2"},
        {"sap": "30000243", "qty": 3, "desc": "ELO FUSIVEL K 6A 500MM"},
        {"sap": "10005181", "qty": 1, "desc": "FITA ISOL AUTOF PT 69KV 19MM ROL 10M"},
        {"sap": "30001112", "qty": 1, "desc": "FITA ISOLANTE ADES PT 19MM ROL 20M"},
        {"sap": "10000487", "qty": 12, "desc": "CONECTOR PERFURANTE 120-35"},
        {"sap": "30003850", "qty": 3, "desc": "PARA RAIOS DIS BT 0,6KV 10KA 280V S/CENT"}
    ]
    
    # Manter Estais legados por enquanto configurados
    unified_db["hardware_kits"]["ESTAI_CC_14M"] = [{"sap": "30056363", "desc": "HASTE ANCOR AC 1020 3200DAN 16MM 1,6M", "qty": 1}, {"sap": "30054507", "desc": "CORDOALHA ACO CARB 9,5MM 7F CL.B MR/SM", "qty": 14}]
    unified_db["hardware_kits"]["PARA_RAIO_CONJUNTO"] = [{"sap": "30053319", "desc": "COBERTURA PROT PARA-RAIO 13,8KV", "qty": 1}]

    # 3. Descobrir TODAS as Estruturas
    all_struct_codes = set(db.kit_rules.keys())
    for nivel in db.master_bom: all_struct_codes.update(db.master_bom[nivel].keys())
    all_struct_codes.update(pdf_structures.keys())
    
    # 4. Mesclar com Prioridade e Adicionar Manuais de ET
    # ET1T e ET4A são estações transformadoras comuns em projetos
    if "ET1T" not in pdf_structures:
        pdf_structures["ET1T"] = [dict(m, type="ALL") for m in unified_db["hardware_kits"]["TRAFO_MONO"]]
    if "ET4A" not in pdf_structures:
        pdf_structures["ET4A"] = [dict(m, type="ALL") for m in unified_db["hardware_kits"]["TRAFO_TRI_45"]]

    all_struct_codes.update(pdf_structures.keys())

    for code in sorted(all_struct_codes):
        if len(code) > 12: continue # Lixo
        
        mats = []
        if code in pdf_structures:
            mats = pdf_structures[code]
        else:
            # Legado
            legacy_mats = db.explode_structure(code)
            for m in legacy_mats:
                mats.append({
                    "sap": str(m['code']),
                    "desc": m['desc'],
                    "qty": float(m['qty']),
                    "type": "ALL" # Legado não tem separação
                })
        
        if mats:
            unified_db["structures"][code] = mats
            for m in mats:
                if not m['sap'].startswith("VERIFICAR"):
                    unified_db["sap_library"][m['sap']] = m['desc']

    # 5. Salvar
    with open("unified_db.json", "w", encoding="utf-8") as f:
        json.dump(unified_db, f, indent=2, ensure_ascii=False)
        
    print(f"CONSOLIDAÇÃO CONCLUÍDA. {len(unified_db['structures'])} estruturas salvas.")

if __name__ == "__main__":
    migrate()
