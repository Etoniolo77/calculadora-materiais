import json
from engine import MaterialEngine

def test_bom_filtering():
    engine = MaterialEngine()
    engine.load_databases()
    
    # Simular dados do PDF extraídos para o Projeto 4001770660
    pole_map = {
        "P1": {
            "Pole": "C12/1000",
            "Est": ["ET4A", "M2M(R)", "S2(R)", "S1(R)"],
            "Trafo": None
        },
        "P2": {
            "Pole": "C12/1000",
            "Est": ["ET1T", "B2F"],
            "Trafo": "TRI-112.5kVA"
        },
        "P3": {
            "Pole": "C11/300,2S2(2)+1S1(R)(E)",
            "Est": ["S2(R)", "S1(R)"],
            "Trafo": None
        }
    }
    
    print("\n--- INICIANDO PROCESSAMENTO DE MATERIAIS ---")
    results = engine.process_form_data(pole_map)
    
    print(f"\nTotal de itens gerados: {len(results)}")
    
    # 1. Verificar se P3 gerou materiais (NÃO DEVE GERAR nada de estruturas)
    p3_mats = [m for m in results if "P3" in m['Origem']]
    print(f"Materiais P3: {len(p3_mats)} (Esperado: 0)")
    
    # 2. Verificar se P1 e P2 geraram o poste C12/1000 (qualquer material: Concreto ou Fibra)
    poste_mats = [m for m in results if "12" in m['Descrição'] and "1000" in m['Descrição'] and "POSTE" in m['Descrição']]
    print(f"Postes 12/1000 Novos: {len(poste_mats)} (Esperado: 2)")
    
    # 3. Verificar Gap Analysis
    print(f"\nGaps de Integridade: {len(engine.audit_log)}")
    for gap in engine.audit_log:
        print(f"  - {gap['type']}: {gap['item']} em {gap['source']}")

    # 4. Mostrar todos os materiais do P2 para conferência
    p2_mats = [m for m in results if "P2" in m['Origem']]
    print(f"\nMateriais P2 (Total {len(p2_mats)}):")
    for m in p2_mats:
        print(f"  - [{m['Código SAP']}] {m['Descrição']} (Qtd: {m['Quantidade']})")

if __name__ == "__main__":
    test_bom_filtering()
