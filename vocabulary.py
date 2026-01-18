"""
Vocabulário Dinâmico - Normalização de termos técnicos para redes de distribuição
Aprende com correções do usuário e persiste em JSON.
"""
import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Tuple


class VocabularyManager:
    """
    Gerencia vocabulário técnico com:
    - Normalização de termos regionais
    - Sinônimos e siglas
    - Aprendizado com correções
    - Persistência em JSON
    """
    
    VOCAB_FILE = "vocabulary.json"
    
    # Vocabulário inicial (padrão)
    DEFAULT_VOCAB = {
        # Equipamentos
        "trafo": "transformador",
        "trfo": "transformador",
        "tf": "transformador",
        "chave faca": "chave_seccionadora",
        "chave-faca": "chave_seccionadora",
        "chave seccionadora": "chave_seccionadora",
        "seccionadora": "chave_seccionadora",
        "religador": "religador",
        "recloser": "religador",
        "para-raios": "para_raios",
        "pára-raios": "para_raios",
        "pararaios": "para_raios",
        "pr": "para_raios",
        
        # Estruturas
        "cruzeta de 2 vias": "cruzeta_m2",
        "cruzeta 2 vias": "cruzeta_m2",
        "cruzeta m2": "cruzeta_m2",
        "cruzeta de 4 vias": "cruzeta_m4",
        "cruzeta 4 vias": "cruzeta_m4",
        "cruzeta m4": "cruzeta_m4",
        
        # Postes
        "poste de concreto": "poste_concreto",
        "poste concreto": "poste_concreto",
        "poste circular": "poste_circular",
        "poste duplo t": "poste_dt",
        "poste dt": "poste_dt",
        "duplo t": "poste_dt",
        
        # Condutores
        "cabo aluminio": "cabo_al",
        "cabo al": "cabo_al",
        "cabo cobre": "cabo_cu",
        "cabo cu": "cabo_cu",
        "multiplex": "cabo_multiplex",
        "xlpe": "cabo_xlpe",
        "protegido": "cabo_protegido",
        
        # Acessórios
        "bracadeira": "bracadeira",
        "braçadeira": "bracadeira",
        "estai": "estai",
        "estribo": "estribo",
        "estribeira": "estribeira",
        "alca": "alca_preformada",
        "alça": "alca_preformada",
        "alça preformada": "alca_preformada",
        
        # Tipos de serviço
        "extensao": "extensao_rede",
        "extensão": "extensao_rede",
        "melhoria": "melhoria_rede",
        "reforco": "reforco_rede",
        "reforço": "reforco_rede",
        "regularizacao": "regularizacao",
        "regularização": "regularizacao",
    }
    
    # Siglas comuns
    DEFAULT_SIGLAS = {
        "MT": "média_tensão",
        "BT": "baixa_tensão",
        "AT": "alta_tensão",
        "SE": "subestação",
        "ET": "estação_transformadora",
        "RD": "rede_distribuição",
        "RL": "ramal_ligação",
        "IP": "iluminação_pública",
        "UC": "unidade_consumidora",
        "kVA": "kilovolt_ampere",
        "kV": "kilovolt",
        "AWG": "american_wire_gauge",
        "MCM": "mil_circular_mils",
    }
    
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.vocab_path = self.base_dir / self.VOCAB_FILE
        
        # Carregar vocabulário
        self.synonyms: Dict[str, str] = {}
        self.siglas: Dict[str, str] = {}
        self.user_corrections: List[Dict] = []
        
        self._load()
    
    def _load(self):
        """Carrega vocabulário do JSON ou usa padrão"""
        if self.vocab_path.exists():
            try:
                with open(self.vocab_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.synonyms = data.get('synonyms', self.DEFAULT_VOCAB.copy())
                    self.siglas = data.get('siglas', self.DEFAULT_SIGLAS.copy())
                    self.user_corrections = data.get('corrections', [])
            except Exception as e:
                print(f"Aviso: Erro ao carregar vocabulário: {e}. Usando padrão.")
                self._use_defaults()
        else:
            self._use_defaults()
            self._save()  # Criar arquivo inicial
    
    def _use_defaults(self):
        """Usa vocabulário padrão"""
        self.synonyms = self.DEFAULT_VOCAB.copy()
        self.siglas = self.DEFAULT_SIGLAS.copy()
        self.user_corrections = []
    
    def _save(self):
        """Persiste vocabulário em JSON"""
        try:
            data = {
                'synonyms': self.synonyms,
                'siglas': self.siglas,
                'corrections': self.user_corrections
            }
            with open(self.vocab_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Aviso: Erro ao salvar vocabulário: {e}")
    
    def normalize(self, term: str) -> str:
        """
        Normaliza um termo para forma padrão.
        
        Args:
            term: Termo original (pode conter variações regionais)
            
        Returns:
            Termo normalizado
        """
        if not term:
            return term
            
        # Lowercase para busca
        term_lower = term.lower().strip()
        
        # Buscar em sinônimos
        if term_lower in self.synonyms:
            return self.synonyms[term_lower]
        
        # Buscar em siglas (case-sensitive)
        term_upper = term.upper().strip()
        if term_upper in self.siglas:
            return self.siglas[term_upper]
        
        # Retornar original se não encontrar
        return term
    
    def add_synonym(self, regional: str, standard: str):
        """
        Adiciona sinônimo ao vocabulário.
        
        Args:
            regional: Termo regional/variante
            standard: Termo padronizado
        """
        regional_lower = regional.lower().strip()
        standard_lower = standard.lower().strip()
        
        self.synonyms[regional_lower] = standard_lower
        
        # Registrar correção
        self.user_corrections.append({
            'from': regional,
            'to': standard,
            'type': 'synonym'
        })
        
        self._save()
    
    def add_sigla(self, sigla: str, meaning: str):
        """
        Adiciona sigla ao vocabulário.
        
        Args:
            sigla: Sigla (ex: "MT")
            meaning: Significado (ex: "média_tensão")
        """
        self.siglas[sigla.upper().strip()] = meaning.lower().strip()
        
        self.user_corrections.append({
            'from': sigla,
            'to': meaning,
            'type': 'sigla'
        })
        
        self._save()
    
    def get_confidence(self, term: str) -> float:
        """
        Retorna score de confiança para um termo.
        - 1.0: termo padronizado conhecido
        - 0.8: sigla conhecida
        - 0.5: termo desconhecido
        
        Args:
            term: Termo a avaliar
            
        Returns:
            Score de confiança (0.0 - 1.0)
        """
        term_lower = term.lower().strip()
        term_upper = term.upper().strip()
        
        # É um sinônimo conhecido?
        if term_lower in self.synonyms:
            return 1.0
        
        # É o próprio valor padronizado?
        if term_lower in self.synonyms.values():
            return 1.0
        
        # É uma sigla conhecida?
        if term_upper in self.siglas:
            return 0.8
        
        # Desconhecido
        return 0.5
    
    def get_all_synonyms(self, standard_term: str) -> List[str]:
        """
        Retorna todos os sinônimos de um termo padronizado.
        
        Args:
            standard_term: Termo padronizado
            
        Returns:
            Lista de sinônimos
        """
        standard_lower = standard_term.lower().strip()
        return [k for k, v in self.synonyms.items() if v == standard_lower]
    
    def search(self, query: str, limit: int = 10) -> List[Tuple[str, str, float]]:
        """
        Busca termos no vocabulário.
        
        Args:
            query: Termo de busca
            limit: Máximo de resultados
            
        Returns:
            Lista de (termo, padronizado, score)
        """
        query_lower = query.lower().strip()
        results = []
        
        for term, standard in self.synonyms.items():
            if query_lower in term or query_lower in standard:
                results.append((term, standard, 1.0))
        
        for sigla, meaning in self.siglas.items():
            if query_lower in sigla.lower() or query_lower in meaning:
                results.append((sigla, meaning, 0.8))
        
        return results[:limit]
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do vocabulário"""
        return {
            'total_synonyms': len(self.synonyms),
            'total_siglas': len(self.siglas),
            'user_corrections': len(self.user_corrections)
        }


# Singleton para uso global
_vocabulary_instance: Optional[VocabularyManager] = None


def get_vocabulary(base_dir: str = ".") -> VocabularyManager:
    """Retorna instância singleton do VocabularyManager"""
    global _vocabulary_instance
    if _vocabulary_instance is None:
        _vocabulary_instance = VocabularyManager(base_dir)
    return _vocabulary_instance


if __name__ == "__main__":
    # Teste
    vocab = VocabularyManager()
    
    print("=== Teste de Vocabulário ===\n")
    
    # Testar normalização
    termos_teste = [
        "trafo",
        "chave faca",
        "para-raios",
        "cruzeta de 2 vias",
        "MT",
        "BT",
        "termo_desconhecido"
    ]
    
    for termo in termos_teste:
        normalizado = vocab.normalize(termo)
        confianca = vocab.get_confidence(termo)
        print(f"  '{termo}' → '{normalizado}' (confiança: {confianca:.1f})")
    
    print(f"\nEstatísticas: {vocab.get_stats()}")
