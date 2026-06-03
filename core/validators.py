"""
=== PROPOSTA DE ALTERAÇÃO - validators.py ===
Corrige: B4 (unidade de esforço "kg" → "daN")
Veja: RELATORIO_INCONSISTENCIAS.md para detalhes
"""
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum

try:
    from .database_sqlite import DatabaseLoader
except ImportError:
    try:
        from database_sqlite import DatabaseLoader  # type: ignore
    except ImportError:
        DatabaseLoader = None  # type: ignore


class IssueSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class TechnicalIssue:
    """Representa uma não-conformidade técnica"""
    code: str
    message: str
    severity: IssueSeverity
    source: str
    suggestion: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            'code': self.code,
            'message': self.message,
            'severity': self.severity.value,
            'source': self.source,
            'suggestion': self.suggestion
        }


@dataclass
class ExtractionItem:
    """Item extraído com metadados de rastreabilidade"""
    value: str
    item_type: str
    page: int = 0
    bbox: tuple = field(default_factory=tuple)
    source_text: str = ""
    confidence: float = 1.0
    
    def to_dict(self) -> Dict:
        return {
            'value': self.value,
            'type': self.item_type,
            'page': self.page,
            'bbox': self.bbox,
            'source_text': self.source_text,
            'confidence': self.confidence
        }


class TechnicalValidator:
    """
    Validador de regras técnicas para projetos de distribuição.
    
    Verifica:
    - Compatibilidade poste × estrutura
    - Esforço mínimo do poste
    - Vão máximo por condutor
    - Configurações de equipamentos
    """
    
    # Regras de esforço mínimo por equipamento (em daN)
    ESFORCO_MINIMO = {
        'trafo_15kva': 300,
        'trafo_25kva': 300,
        'trafo_37.5kva': 400,
        'trafo_45kva': 400,
        'trafo_75kva': 600,
        'trafo_112.5kva': 600,
        'trafo_150kva': 1000,
        'trafo_225kva': 1000,
        'religador': 600,
        'chave_tripolar': 400,
    }
    
    # Vão máximo por bitola de condutor (metros)
    VAO_MAXIMO = {
        '35': 60,
        '50': 55,
        '70': 50,
        '120': 45,
        '185': 40,
        '240': 35,
        '1/0': 55,
        '2/0': 50,
        '3/0': 45,
        '4/0': 40,
        '336': 35,
    }
    
    # Altura mínima do poste por nível de tensão
    ALTURA_MINIMA = {
        'bt': 9,
        'mt': 11,
        'at': 13,
    }
    
    # Estruturas que exigem poste DT
    ESTRUTURAS_DT_OBRIGATORIO = {'M4', 'M6', 'TE4'}
    
    # Estruturas que exigem poste circular
    ESTRUTURAS_CIRCULAR_OBRIGATORIO = {'N1', 'N2', 'N3', 'N4', 'B1', 'B2', 'B3', 'B4'}
    _catalog_loader = None
    _catalog_ready = False
    
    def __init__(self):
        self.issues: List[TechnicalIssue] = []
        self.catalog_loader = self._get_catalog_loader()
    
    def validate(self, extraction: Dict) -> List[TechnicalIssue]:
        """
        Executa todas as validações no resultado da extração.
        """
        self.issues = []
        
        pole_map = extraction.get('pole_map', {})
        cables = extraction.get('cables', [])
        
        for pole_id, pole_data in pole_map.items():
            self._validate_pole(pole_id, pole_data)
        
        for cable in cables:
            self._validate_cable(cable)
        
        return self.issues
    
    def _validate_pole(self, pole_id: str, pole_data: Dict):
        """Valida um poste e suas estruturas"""
        
        pole_type = pole_data.get('Pole', 'Desconhecido')
        structures = pole_data.get('Est', [])
        trafo = pole_data.get('Trafo')
        
        pole_info = self._parse_pole_type(pole_type)
        
        if trafo:
            self._validate_trafo_esforco(pole_id, pole_info, trafo)
        
        for est in structures:
            self._validate_structure_pole_compatibility(pole_id, est, pole_info)
        
        if pole_info.get('altura'):
            self._validate_altura_minima(pole_id, pole_info, structures)
    
    def _validate_cable(self, cable: Dict):
        """Valida um cabo"""
        desc = cable.get('Desc', '')
        qty = cable.get('Qtd', 0)
        
        bitola = self._extract_bitola(desc)
        
        if bitola and bitola in self.VAO_MAXIMO:
            max_vao = self.VAO_MAXIMO[bitola]
            if qty > max_vao and qty < max_vao * 2:
                self.issues.append(TechnicalIssue(
                    code="VAO_001",
                    message=f"Cabo {bitola}mm² com {qty}m pode exceder vão máximo ({max_vao}m)",
                    severity=IssueSeverity.WARNING,
                    source=f"Cabo: {desc}",
                    suggestion=f"Verificar se há apoios intermediários no trecho"
                ))
    
    def _validate_trafo_esforco(self, pole_id: str, pole_info: Dict, trafo: str):
        """Valida se esforço do poste comporta o transformador"""
        import re
        
        esforco = pole_info.get('esforco', 0)
        
        match = re.search(r'(\d+)\s*kva', trafo.lower())
        if match:
            potencia = int(match.group(1))
            key = f'trafo_{potencia}kva'
            
            if key in self.ESFORCO_MINIMO:
                esforco_min = self.ESFORCO_MINIMO[key]
                
                if esforco < esforco_min:
                    # [FIX B4] Unidade corrigida de "kg" para "daN"
                    self.issues.append(TechnicalIssue(
                        code="ESF_001",
                        message=f"Poste {pole_id} com esforço {esforco} daN insuficiente para {trafo}",
                        severity=IssueSeverity.ERROR,
                        source=pole_id,
                        suggestion=f"Esforço mínimo recomendado: {esforco_min} daN"
                    ))
    
    def _validate_structure_pole_compatibility(self, pole_id: str, structure: str, pole_info: Dict):
        """Valida compatibilidade estrutura × tipo de poste"""
        
        struct_clean = structure.replace('(R)', '').strip().upper()
        
        is_dt = pole_info.get('is_dt', False)
        supported_types = self._get_supported_pole_types(struct_clean)

        if supported_types:
            wants_dt = "DT" in supported_types and "CIRCULAR" not in supported_types and "ALL" not in supported_types
            wants_circular = "CIRCULAR" in supported_types and "DT" not in supported_types and "ALL" not in supported_types

            if wants_dt and not is_dt:
                self.issues.append(TechnicalIssue(
                    code="COMP_001",
                    message=f"Estrutura {struct_clean} requer poste DT, mas {pole_id} é circular",
                    severity=IssueSeverity.ERROR,
                    source=pole_id,
                    suggestion="Substituir por poste tipo DT"
                ))

            if wants_circular and is_dt:
                self.issues.append(TechnicalIssue(
                    code="COMP_002",
                    message=f"Estrutura {struct_clean} é típica de poste circular, mas {pole_id} é DT",
                    severity=IssueSeverity.INFO,
                    source=pole_id,
                    suggestion="Verificar se estrutura está correta para DT"
                ))
            return
        
        if struct_clean in self.ESTRUTURAS_DT_OBRIGATORIO and not is_dt:
            self.issues.append(TechnicalIssue(
                code="COMP_001",
                message=f"Estrutura {struct_clean} requer poste DT, mas {pole_id} é circular",
                severity=IssueSeverity.ERROR,
                source=pole_id,
                suggestion=f"Substituir por poste tipo DT"
            ))
        
        if struct_clean in self.ESTRUTURAS_CIRCULAR_OBRIGATORIO and is_dt:
            self.issues.append(TechnicalIssue(
                code="COMP_002",
                message=f"Estrutura {struct_clean} é típica de poste circular, mas {pole_id} é DT",
                severity=IssueSeverity.INFO,
                source=pole_id,
                suggestion=f"Verificar se estrutura está correta para DT"
            ))
    
    def _validate_altura_minima(self, pole_id: str, pole_info: Dict, structures: List):
        """Valida altura mínima do poste por nível de tensão"""
        
        altura = pole_info.get('altura', 0)
        
        has_mt = any(s.upper().startswith(('N', 'B', 'U', 'M', 'CE', 'TE')) for s in structures)
        nivel = 'mt' if has_mt else 'bt'
        
        altura_min = self.ALTURA_MINIMA.get(nivel, 9)
        
        if altura < altura_min:
            self.issues.append(TechnicalIssue(
                code="ALT_001",
                message=f"Poste {pole_id} com {altura}m pode ser insuficiente para {nivel.upper()}",
                severity=IssueSeverity.WARNING,
                source=pole_id,
                suggestion=f"Altura mínima recomendada: {altura_min}m"
            ))
    
    def _parse_pole_type(self, pole_type: str) -> Dict:
        """
        Extrai informações do tipo de poste.
        Ex: "DT12/1000" -> {is_dt: True, altura: 12, esforco: 1000}
        Ex: "C11/600" -> {is_dt: False, altura: 11, esforco: 600}
        """
        import re
        
        info = {
            'is_dt': False,
            'altura': 0,
            'esforco': 0,
            'raw': pole_type
        }
        
        if not pole_type or pole_type == 'Desconhecido':
            return info
        
        pole_upper = pole_type.upper().replace('(E)', '').strip()
        
        if pole_upper.startswith('DT') or pole_upper.startswith('RT'):
            info['is_dt'] = True
        
        match = re.search(r'(\d{1,2})[/xX](\d{3,4})', pole_upper)
        if match:
            info['altura'] = int(match.group(1))
            info['esforco'] = int(match.group(2))
        
        return info
    
    def _extract_bitola(self, cable_desc: str) -> Optional[str]:
        """Extrai bitola do cabo da descrição"""
        import re
        
        match = re.search(r'(\d+(?:/\d)?)\s*(?:mm|mcm)?', cable_desc.lower())
        if match:
            return match.group(1)
        return None

    @classmethod
    def _get_catalog_loader(cls):
        if cls._catalog_loader is not None:
            return cls._catalog_loader
        if DatabaseLoader is None:
            return None
        try:
            loader = DatabaseLoader()
            loader.load_all()
            if loader.is_loaded:
                cls._catalog_loader = loader
                cls._catalog_ready = True
                return cls._catalog_loader
        except Exception:
            pass
        cls._catalog_ready = False
        return None

    def _get_supported_pole_types(self, structure_code: str) -> set[str]:
        loader = self.catalog_loader
        if not loader or not getattr(loader, "is_loaded", False):
            return set()
        try:
            return set(loader.get_structure_supported_pole_types(structure_code))
        except Exception:
            return set()
    
    def get_summary(self) -> Dict:
        """Retorna resumo das validações"""
        errors = sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)
        warnings = sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)
        infos = sum(1 for i in self.issues if i.severity == IssueSeverity.INFO)
        
        return {
            'total': len(self.issues),
            'errors': errors,
            'warnings': warnings,
            'infos': infos,
            'issues': [i.to_dict() for i in self.issues]
        }


if __name__ == "__main__":
    validator = TechnicalValidator()
    
    extraction = {
        'pole_map': {
            'P2': {'Pole': 'C11/400', 'Est': ['N1', 'B2'], 'Trafo': 'TRI-75kVA'},
            'P3': {'Pole': 'DT12/1000', 'Est': ['M4', 'CE4'], 'Trafo': None},
            'P4': {'Pole': 'C9/300', 'Est': ['ET4A'], 'Trafo': 'MONO-15kVA'},
        },
        'cables': [
            {'Tipo': 'MT', 'Desc': 'CABO AL 35mm² XLPE', 'Qtd': 65},
        ]
    }
    
    issues = validator.validate(extraction)
    
    print("=== Validação Técnica ===\n")
    for issue in issues:
        print(f"[{issue.severity.value.upper()}] {issue.code}: {issue.message}")
        print(f"  Fonte: {issue.source}")
        if issue.suggestion:
            print(f"  Sugestão: {issue.suggestion}")
        print()
    
    print(f"Resumo: {validator.get_summary()}")
