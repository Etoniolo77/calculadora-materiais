from database_sqlite import SQLiteDatabaseLoader

loader = SQLiteDatabaseLoader()
loader.load_all()

print("="*80)
print("DIAGNÓSTICO FINAL (9xxxx & PARAFUSO)")
print("="*80)

# 1. Verificar Postes
print("\n1. Buscando 11M 600DAN (Sem códigos 9xxxx?)")
# Termos da busca real: POSTE, CIRCULAR, CONCR, 11M, 600DAN
termos_busca = ['POSTE', 'CIRCULAR', 'CONCR', '11M', '600DAN']
results = loader.find_material_by_description(termos_busca, limit=20)
if not results:
    print("  Nenhum poste encontrado com esses termos (esperado se só havia 9xxxx).")
else:
    for code, desc, score in results:
        print(f"  {code} | {score} | {desc}")
        if str(code).startswith('9'):
            print("  ERRO: Código 9xxxx ainda presente!")

# 2. Verificar Parafuso M16x400 através da engine (simulada)
print("\n2. Simulando Engine para Parafuso M16x400 (ex: N3)")
# Precisamos da lógica da ENGINE agora, não apenas do loader.
# Vamos importar engine se possivel ou simular o fix
from engine import MaterialEngine
engine = MaterialEngine()
engine.load_databases() # Carrega DBs

# Simular chamada de explode_structures para N3
mats = engine.explode_structures({'N3': 1}, pole_mapping=None)
achou = False
for m in mats:
    if "400" in m['Descrição'] and "PARAFUSO" in m['Descrição'].upper():
        print(f"  Item Explodido: {m['Código SAP']} | {m['Descrição']}")
        if m['Código SAP'] == '30058241':
            print("  SUCESSO: Código corrigido para 30058241")
            achou = True
        elif 'VERIFICAR' in str(m['Código SAP']):
            print("  FALHA: Ainda está como VERIFICAR")
            
if not achou:
    print("  AVISO: Item M16x400 não encontrado na explosão de N3.")
