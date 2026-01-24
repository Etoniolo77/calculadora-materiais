from extractor import ProjectExtractor
import json

pdf_path = "c:/Users/EvandroCesarToniolo/Projetos_Antigravity/13_Calculadora_Materiais/PROJETO_DESE_4001770660_F01-01_Rev0 (2).pdf"

def test_new_logic():
    ext = ProjectExtractor(pdf_path)
    ext.extract_text()
    print("--- Estados Visuais Amostra ---")
    for k, v in list(ext.visual_states.items())[:20]:
        print(f"{k}: {v}")
    
    res = ext.find_structures_per_pole()
    
    print("\n--- Poles Detectados (Raw) ---")
    for pid, pdata in ext.last_pole_map.items():
        print(f"ID: {pid:5} | NEW: {pdata.get('IsNew')} | POLE: {pdata['Pole']} | EST: {len(pdata['Est'])}")
    
    print("\n--- Resultado Final ---")
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    test_new_logic()
