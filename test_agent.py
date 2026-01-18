"""Script de teste para verificar a implementação do Agente IA"""
from extractor import ProjectExtractor
from report_generator import generate_report_from_extraction
import json

# PDF de teste
PDF_PATH = "PROJETO_DESE_4001759672_F01-01_Rev0 - PROGRAMADO 21-12.pdf"

print("=" * 60)
print("TESTE DO AGENTE IA DE ENGENHARIA ELÉTRICA")
print("=" * 60)

# 1. Extração com metadados
print("\n[1/4] Extraindo dados do PDF...")
extractor = ProjectExtractor(PDF_PATH)
result = extractor.extract_with_metadata()

# 2. Resumo
print("\n[2/4] RESUMO DA EXTRAÇÃO:")
summary = result.get('summary', {})
print(f"  - Postes: {summary.get('total_poles', 0)}")
print(f"  - Estruturas: {summary.get('total_structures', 0)}")
print(f"  - Cabos: {summary.get('total_cables', 0)}")
print(f"  - Equipamentos: {summary.get('total_equipments', 0)}")

# 3. Validação
print("\n[3/4] VALIDAÇÃO TÉCNICA:")
val = result.get('validation', {})
print(f"  - Erros: {val.get('errors', 0)}")
print(f"  - Avisos: {val.get('warnings', 0)}")
print(f"  - Informações: {val.get('infos', 0)}")

if val.get('issues'):
    print("\n  Issues encontradas:")
    for issue in val['issues'][:5]:  # Limitar a 5
        print(f"  [{issue.get('severity', '?').upper()}] {issue.get('message', '-')}")

# 4. Detalhes
print("\n[4/4] DETALHES:")
print(f"\n  Postes detectados: {list(result.get('pole_map', {}).keys())}")
print(f"\n  Cabos: {len(result.get('cables', []))}")
for c in result.get('cables', [])[:3]:
    print(f"    - {c.get('Tipo')}: {c.get('Desc')} ({c.get('Qtd')}m)")

print("\n" + "=" * 60)
print("TESTE CONCLUÍDO COM SUCESSO!")
print("=" * 60)

# Salvar relatório
print("\nGerando relatório...")
report = generate_report_from_extraction(result, "Projeto Teste", "Relatorio_Teste.md")
print(f"Relatório salvo em: {report}")
