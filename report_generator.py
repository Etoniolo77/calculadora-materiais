"""
Gerador de Relatório Técnico para Projetos de Distribuição
Gera relatórios em Markdown ou JSON com rastreabilidade completa.
"""
import json
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


class ReportGenerator:
    """
    Gera relatórios técnicos estruturados com:
    - Sumário do projeto
    - Dados extraídos com referências
    - Não-conformidades detectadas
    - Itens de baixa confiança
    - BOM consolidado
    """
    
    def __init__(self, extraction: Dict, project_name: str = "Projeto"):
        self.extraction = extraction
        self.project_name = project_name
        self.timestamp = datetime.now()
    
    def generate_markdown(self) -> str:
        """Gera relatório em formato Markdown"""
        lines = []
        
        # Cabeçalho
        lines.extend([
            f"# Relatório Técnico - {self.project_name}",
            "",
            f"> Gerado em: {self.timestamp.strftime('%d/%m/%Y às %H:%M')}",
            "",
            "---",
            "",
        ])
        
        # Sumário
        summary = self.extraction.get('summary', {})
        lines.extend([
            "## 1. Resumo da Extração",
            "",
            "| Elemento | Quantidade |",
            "|----------|------------|",
            f"| Postes | {summary.get('total_poles', 0)} |",
            f"| Estruturas | {summary.get('total_structures', 0)} |",
            f"| Cabos | {summary.get('total_cables', 0)} |",
            f"| Equipamentos | {summary.get('total_equipments', 0)} |",
            "",
        ])
        
        # Postes e Estruturas
        pole_map = self.extraction.get('pole_map', {})
        if pole_map:
            lines.extend([
                "## 2. Postes e Estruturas",
                "",
            ])
            
            for pole_id, data in sorted(pole_map.items()):
                pole_type = data.get('Pole', 'Desconhecido')
                structures = data.get('Est', [])
                trafo = data.get('Trafo')
                chave = data.get('Chave')
                
                lines.append(f"### {pole_id} - {pole_type}")
                
                if structures:
                    lines.append(f"- **Estruturas:** {', '.join(structures)}")
                if trafo:
                    lines.append(f"- **Transformador:** {trafo}")
                if chave:
                    lines.append(f"- **Chave:** {chave}")
                
                lines.append("")
        
        # Cabos
        cables = self.extraction.get('cables', [])
        if cables:
            lines.extend([
                "## 3. Cabos",
                "",
                "| Tipo | Descrição | Quantidade |",
                "|------|-----------|------------|",
            ])
            
            for cable in cables:
                tipo = cable.get('Tipo', '-')
                desc = cable.get('Desc', '-')
                qty = cable.get('Qtd', 0)
                lines.append(f"| {tipo} | {desc} | {qty:.1f}m |")
            
            lines.append("")
        
        # Equipamentos
        equipments = self.extraction.get('equipments', [])
        if equipments:
            lines.extend([
                "## 4. Equipamentos",
                "",
                "| Tipo | Descrição | Qtd | Estado | Pág. |",
                "|------|-----------|-----|--------|------|",
            ])
            
            for equip in equipments:
                tipo = equip.get('type', '-')
                desc = equip.get('description', '-')[:40]
                qty = equip.get('qty', 1)
                state = equip.get('state', '-')
                meta = equip.get('metadata', {})
                page = meta.get('page', '-')
                
                lines.append(f"| {tipo} | {desc} | {qty} | {state} | {page} |")
            
            lines.append("")
        
        # Validação Técnica
        validation = self.extraction.get('validation', {})
        if validation:
            lines.extend([
                "## 5. Validação Técnica",
                "",
            ])
            
            errors = validation.get('errors', 0)
            warnings = validation.get('warnings', 0)
            
            if errors > 0:
                lines.append(f"> [!CAUTION]")
                lines.append(f"> **{errors} erro(s)** encontrado(s) que requerem atenção.")
                lines.append("")
            
            if warnings > 0:
                lines.append(f"> [!WARNING]")
                lines.append(f"> **{warnings} aviso(s)** de possíveis problemas.")
                lines.append("")
            
            issues = validation.get('issues', [])
            if issues:
                lines.extend([
                    "### Issues Detectadas",
                    "",
                ])
                
                for issue in issues:
                    severity = issue.get('severity', 'info')
                    code = issue.get('code', '')
                    message = issue.get('message', '')
                    source = issue.get('source', '')
                    suggestion = issue.get('suggestion')
                    
                    icon = "❌" if severity == "error" else "⚠️" if severity == "warning" else "ℹ️"
                    lines.append(f"- {icon} **[{code}]** {message}")
                    lines.append(f"  - Fonte: `{source}`")
                    if suggestion:
                        lines.append(f"  - Sugestão: {suggestion}")
                
                lines.append("")
        
        # Log de Extração (resumido)
        extraction_log = self.extraction.get('extraction_log', [])
        if extraction_log:
            lines.extend([
                "## 6. Rastreabilidade",
                "",
                f"Total de {len(extraction_log)} item(ns) registrado(s) no log de extração.",
                "",
            ])
        
        # Rodapé
        lines.extend([
            "---",
            "",
            "*Relatório gerado automaticamente pelo Agente IA de Engenharia Elétrica*",
        ])
        
        return "\n".join(lines)
    
    def generate_json(self) -> str:
        """Gera relatório em formato JSON"""
        report = {
            'metadata': {
                'project_name': self.project_name,
                'generated_at': self.timestamp.isoformat(),
                'version': '1.0'
            },
            'extraction': self.extraction
        }
        return json.dumps(report, ensure_ascii=False, indent=2)
    
    def save(self, output_path: str, format: str = 'markdown'):
        """
        Salva relatório em arquivo.
        
        Args:
            output_path: Caminho do arquivo de saída
            format: 'markdown' ou 'json'
        """
        path = Path(output_path)
        
        if format == 'json':
            content = self.generate_json()
            if not path.suffix:
                path = path.with_suffix('.json')
        else:
            content = self.generate_markdown()
            if not path.suffix:
                path = path.with_suffix('.md')
        
        path.write_text(content, encoding='utf-8')
        return str(path)


def generate_report_from_extraction(extraction: Dict, 
                                   project_name: str = "Projeto",
                                   output_path: str = None,
                                   format: str = 'markdown') -> str:
    """
    Função utilitária para gerar relatório.
    
    Args:
        extraction: Resultado de ProjectExtractor.extract_with_metadata()
        project_name: Nome do projeto
        output_path: Caminho para salvar (opcional)
        format: 'markdown' ou 'json'
        
    Returns:
        String com o relatório ou caminho do arquivo salvo
    """
    generator = ReportGenerator(extraction, project_name)
    
    if output_path:
        return generator.save(output_path, format)
    
    if format == 'json':
        return generator.generate_json()
    
    return generator.generate_markdown()


if __name__ == "__main__":
    # Teste com dados simulados
    extraction = {
        'pole_map': {
            'P2': {'Pole': 'C11/600', 'Est': ['N1', 'B2'], 'Trafo': 'TRI-75kVA', 'Chave': None},
            'P3': {'Pole': 'DT12/1000', 'Est': ['M4', 'CE4'], 'Trafo': None, 'Chave': 'TRIPOLAR'},
        },
        'cables': [
            {'Tipo': 'MT', 'Desc': 'CABO AL 35mm² XLPE', 'Qtd': 65.5},
            {'Tipo': 'BT', 'Desc': 'MULTIPLEX 3x70+70', 'Qtd': 120.0},
        ],
        'equipments': [
            {
                'type': 'para_raios',
                'description': 'PARA-RAIOS 15KV POLIMERICO',
                'qty': 3,
                'state': 'NEW',
                'metadata': {'page': 1, 'confidence': 0.8}
            }
        ],
        'validation': {
            'total': 2,
            'errors': 1,
            'warnings': 1,
            'infos': 0,
            'issues': [
                {
                    'code': 'ESF_001',
                    'message': 'Poste P2 com esforço 600kg insuficiente para TRI-75kVA',
                    'severity': 'error',
                    'source': 'P2',
                    'suggestion': 'Esforço mínimo recomendado: 1000kg'
                },
                {
                    'code': 'VAO_001',
                    'message': 'Cabo 35mm² com 65m pode exceder vão máximo (60m)',
                    'severity': 'warning',
                    'source': 'Cabo: MT 35mm²',
                    'suggestion': 'Verificar apoios intermediários'
                }
            ]
        },
        'extraction_log': [
            {'type': 'structure', 'value': 'N1', 'page': 1},
            {'type': 'equipment', 'value': 'para_raios', 'page': 1},
        ],
        'summary': {
            'total_poles': 2,
            'total_structures': 4,
            'total_cables': 2,
            'total_equipments': 1
        }
    }
    
    print("=== Relatório Markdown ===\n")
    report = generate_report_from_extraction(extraction, "Projeto Teste")
    print(report)
