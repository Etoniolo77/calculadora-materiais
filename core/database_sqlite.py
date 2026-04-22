"""
Database Loader - Versão SQLite
Substitui database_loader.py com interface idêntica mas usando SQLite
"""
import sqlite3
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class SAPCodesProxy:
    """
    Proxy que simula um dicionário mas faz queries SQL.
    Suporta: `code in proxy`, `proxy[code]`, `proxy.get(code)`, `proxy.keys()`, `proxy.values()`
    """
    
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
    
    def __contains__(self, code: str) -> bool:
        cursor = self.conn.execute(
            "SELECT 1 FROM materiais WHERE codigo = ? LIMIT 1",
            (str(code),)
        )
        return cursor.fetchone() is not None
    
    def __getitem__(self, code: str) -> str:
        cursor = self.conn.execute(
            "SELECT descricao FROM materiais WHERE codigo = ?",
            (str(code),)
        )
        result = cursor.fetchone()
        if result:
            return result[0]
        raise KeyError(code)
    
    def get(self, code: str, default: str = None) -> str:
        try:
            return self[code]
        except KeyError:
            return default
    
    def keys(self):
        cursor = self.conn.execute("SELECT codigo FROM materiais")
        return [row[0] for row in cursor.fetchall()]
    
    def values(self):
        cursor = self.conn.execute("SELECT descricao FROM materiais")
        return [row[0] for row in cursor.fetchall()]
    
    def items(self):
        cursor = self.conn.execute("SELECT codigo, descricao FROM materiais")
        return list(cursor.fetchall())


class SQLiteDatabaseLoader:
    """
    Carregador de banco de dados usando SQLite.
    Interface idêntica ao DatabaseLoader original para compatibilidade.
    """
    
    DB_FILE = "materials.db"

    # Ordem de busca do banco: cwd → pasta do script → ../data → ../../data
    _DB_SEARCH_PATHS = [
        Path(os.getcwd()) / "materials.db",
        Path(__file__).parent / "materials.db",
        Path(__file__).parent.parent / "data" / "materials.db",
        Path(__file__).parent.parent.parent / "data" / "materials.db",
    ]

    # Ordem de busca do unified_db.json (metadata de cintas, kits, etc.)
    _UNIFIED_SEARCH_PATHS = [
        Path(os.getcwd()) / "unified_db.json",
        Path(__file__).parent / "unified_db.json",
        Path(__file__).parent.parent / "data" / "unified_db.json",
        Path(__file__).parent.parent.parent / "data" / "unified_db.json",
    ]

    def __init__(self, base_dir: str = "."):
        # Resolver o caminho real do banco percorrendo a lista de candidatos
        self.db_path = self._resolve_path(self._DB_SEARCH_PATHS, "materials.db")
        self.base_dir = self.db_path.parent if self.db_path else Path(os.getcwd())
        self.conn: Optional[sqlite3.Connection] = None
        self.is_loaded = False

        # Compatibilidade com código legado - usa proxy para queries SQL
        self._sap_proxy = None  # Inicializado após load_all
        self.unified_db = None

    @staticmethod
    def _resolve_path(candidates: list, label: str) -> Optional[Path]:
        """Retorna o primeiro Path da lista que existe e tem tamanho > 0."""
        for p in candidates:
            if p.exists() and p.stat().st_size > 0:
                print(f"[DB] {label} encontrado em: {p}")
                return p
        print(f"[AVISO] {label} não encontrado em nenhum dos caminhos: {[str(c) for c in candidates]}")
        return candidates[0]  # Retorna o primeiro para mensagem de erro clara

    @property
    def sap_codes(self):
        """Retorna proxy que simula dict mas faz queries SQL."""
        if self._sap_proxy is None and self.conn:
            self._sap_proxy = SAPCodesProxy(self.conn)
        return self._sap_proxy if self._sap_proxy else {}

    def load_all(self, force_legacy: bool = False) -> None:
        """Conecta ao banco SQLite."""
        if not self.db_path or not self.db_path.exists():
            print(f"[AVISO] Banco SQLite nao encontrado: {self.db_path}")
            print("  Execute 'python scripts/migrate_to_sqlite.py' a partir da raiz do projeto.")
            return
        
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            
            # Contar registros para log
            cursor = self.conn.execute("SELECT COUNT(*) FROM materiais")
            mat_count = cursor.fetchone()[0]
            
            cursor = self.conn.execute("SELECT COUNT(*) FROM estruturas")
            est_count = cursor.fetchone()[0]
            
            print(f"[OK] SQLite conectado: {mat_count} materiais, {est_count} estruturas")
            
            # Carregar unified_db.json para metadados (cinta_lookup, etc)
            # Percorre lista de candidatos para encontrar o arquivo
            unified_path = self._resolve_path(self._UNIFIED_SEARCH_PATHS, "unified_db.json")
            if unified_path and unified_path.exists():
                import json
                with open(unified_path, 'r', encoding='utf-8') as f:
                    self.unified_db = json.load(f)
                print(f"[OK] Unified DB carregado: {unified_path}")
            
            self.is_loaded = True
            
        except Exception as e:
            print(f"Erro ao conectar SQLite: {e}")
            self.is_loaded = False
    
    def get_sap_description(self, code: str) -> str:
        """Retorna descrição do código SAP."""
        if not self.conn:
            return f"SAP {code}"
        
        cursor = self.conn.execute(
            "SELECT descricao FROM materiais WHERE codigo = ?",
            (str(code),)
        )
        result = cursor.fetchone()
        return result[0] if result else f"SAP {code}"
    
    def find_material_by_description(self, search_terms, limit: int = 5, exclude_terms: List[str] = None) -> List[Tuple[str, str, int]]:
        """
        Busca materiais por termos na descrição usando FTS5.
        Retorna lista de tuplas (codigo, descricao, score).

        Estratégia de scoring (melhorada):
        1. Tenta primeiro AND entre todos os termos — resultado preciso e pequeno.
        2. Se AND retornar zero resultados, cai para OR (comportamento anterior).
        3. Score é ponderado por IDF simples: termos raros valem mais que termos comuns.
           score = soma(IDF(term)) para cada term presente na descrição.
           IDF(term) = log(N / df) onde df = número de docs que contêm o termo.
        4. Penaliza descrições muito longas (material mais específico bate melhor).
        """
        if not self.conn:
            return []

        if isinstance(search_terms, str):
            search_terms = [search_terms]

        terms_upper   = [t.upper() for t in search_terms]
        exclude_upper = [t.upper() for t in exclude_terms] if exclude_terms else []

        def _apply_filters(rows):
            out = []
            for row in rows:
                desc_upper = row[1].upper()
                if any(ex in desc_upper for ex in exclude_upper):
                    continue
                if str(row[0]).startswith('9'):
                    continue
                out.append(row)
            return out

        def _idf_score(desc_upper: str, idf_map: dict) -> float:
            """Soma IDF dos termos presentes; penaliza descrições longas."""
            base = sum(idf_map.get(t, 0.5) for t in terms_upper if t in desc_upper)
            # Penalidade leve por comprimento (preferir descrição mais específica)
            length_penalty = 1.0 / (1.0 + len(desc_upper) / 200.0)
            return base * length_penalty

        try:
            import math

            # ── Fase 1: tentar AND (FTS5: todos os termos obrigatórios) ─────────
            and_query = " AND ".join([f'"{t}"*' for t in search_terms])
            cursor = self.conn.execute(
                "SELECT codigo, descricao FROM materiais_fts WHERE materiais_fts MATCH ? LIMIT 500",
                (and_query,)
            )
            rows = _apply_filters(cursor.fetchall())

            # ── Fase 2: fallback OR se AND não retornou nada ─────────────────────
            if not rows:
                or_query = " OR ".join([f'"{t}"*' for t in search_terms])
                cursor = self.conn.execute(
                    "SELECT codigo, descricao FROM materiais_fts WHERE materiais_fts MATCH ? LIMIT 1000",
                    (or_query,)
                )
                rows = _apply_filters(cursor.fetchall())

            if not rows:
                return []

            # ── Calcular IDF simples ──────────────────────────────────────────────
            n_docs = len(rows)
            idf_map = {}
            for term in terms_upper:
                df = sum(1 for r in rows if term in r[1].upper())
                idf_map[term] = math.log((n_docs + 1) / (df + 1)) + 1.0

            # ── Pontuar e ordenar ─────────────────────────────────────────────────
            scored = [
                (row[0], row[1], _idf_score(row[1].upper(), idf_map))
                for row in rows
            ]
            scored.sort(key=lambda x: x[2], reverse=True)
            return scored[:limit]

        except Exception as e:
            print(f"Erro na busca FTS: {e}")
            return self._fallback_search(search_terms, limit, exclude_terms)
    
    def _fallback_search(self, search_terms: List[str], limit: int, exclude_terms: List[str] = None) -> List[Tuple[str, str, int]]:
        """Busca fallback sem FTS."""
        cursor = self.conn.execute("SELECT codigo, descricao FROM materiais")
        results = []
        
        exclude_upper = [t.upper() for t in exclude_terms] if exclude_terms else []
        
        for row in cursor.fetchall():
            desc_upper = row[1].upper()
            
            # Verificar exclusões (termos)
            if any(ex in desc_upper for ex in exclude_upper):
                continue
            
            # REGRA DE NEGÓCIO: Filtrar códigos de desativação (começando com 9)
            if str(row[0]).startswith('9'):
                continue
            
            score = sum(1 for term in search_terms if term.upper() in desc_upper)
            if score > 0:
                results.append((row[0], row[1], score))
        
        results.sort(key=lambda x: x[2], reverse=True)
        return results[:limit]
    
    def explode_structure(self, structure_code: str, nivel: int = 1, pole_type_str: str = "") -> List[Dict]:
        """
        Retorna lista de materiais para uma estrutura, filtrada por tipo de poste.
        """
        if not self.conn:
            return [{'code': 'VERIFICAR', 'desc': f'BD não conectado - {structure_code}', 'qty': 1}]
        
        structure_code = str(structure_code).strip()
        
        # Determinar tipo de poste
        is_dt = False
        if pole_type_str:
            p_upper = pole_type_str.upper()
            if p_upper.startswith("DT") or p_upper.startswith("RT") or "DUPLO T" in p_upper:
                is_dt = True
        
        tipo_filtro = 'DT' if is_dt else 'CIRCULAR'
        
        cursor = self.conn.execute(
            """
            SELECT e.id, e.tipo_poste
            FROM estruturas e
            WHERE e.codigo = ? AND (e.tipo_poste = ? OR e.tipo_poste = 'ALL')
            ORDER BY CASE WHEN e.tipo_poste = ? THEN 0 ELSE 1 END
            """,
            (structure_code, tipo_filtro, tipo_filtro)
        )
        
        estruturas = cursor.fetchall()
        
        if not estruturas:
            cursor = self.conn.execute(
                "SELECT id FROM estruturas WHERE codigo = ?",
                (structure_code,)
            )
            estruturas = cursor.fetchall()
        
        if not estruturas:
            return self._explode_from_bom(structure_code)
        
        materials = []
        for est_row in estruturas:
            est_id = est_row[0]
            
            cursor = self.conn.execute(
                """
                SELECT material_codigo, material_descricao, quantidade
                FROM estrutura_materiais
                WHERE estrutura_id = ?
                """,
                (est_id,)
            )
            
            for mat_row in cursor.fetchall():
                materials.append({
                    'code': mat_row[0],
                    'desc': mat_row[1] or self.get_sap_description(mat_row[0]),
                    'qty': mat_row[2]
                })
            
            if materials:
                break
        
        if not materials:
            return self._explode_from_bom(structure_code)
        
        return materials
    
    def _explode_from_bom(self, structure_code: str) -> List[Dict]:
        """Busca materiais na tabela BOM como fallback (tabela legada — pode não existir)."""
        try:
            cursor = self.conn.execute(
                """
                SELECT bi.material_codigo, bi.material_descricao, bi.quantidade
                FROM bom_itens bi
                JOIN bom_categorias bc ON bi.categoria_id = bc.id
                WHERE bc.subcategoria LIKE ?
                LIMIT 50
                """,
                (f"%{structure_code}%",)
            )
            materials = []
            for row in cursor.fetchall():
                materials.append({
                    'code': row[0],
                    'desc': row[1] or self.get_sap_description(row[0]),
                    'qty': row[2]
                })
            if materials:
                return materials
        except Exception:
            pass  # tabela bom_itens não existe no schema atual

        print(f"[AVISO] Estrutura {structure_code} nao encontrada no SQLite")
        return [{'code': 'VERIFICAR', 'desc': f'VERIFICAR ESTRUTURA {structure_code}', 'qty': 1}]

    def get_bom_items(self, categoria: str, subcategoria: str) -> List[Dict]:
        """Retorna itens BOM para uma categoria/subcategoria específica (tabela legada)."""
        if not self.conn:
            return []
        try:
            cursor = self.conn.execute(
                """
                SELECT bi.material_codigo, bi.material_descricao, bi.quantidade
                FROM bom_itens bi
                JOIN bom_categorias bc ON bi.categoria_id = bc.id
                WHERE bc.categoria = ? AND bc.subcategoria = ?
                """,
                (categoria, subcategoria)
            )
            return [
                {'codigo': row[0], 'descricao': row[1], 'quantidade': row[2]}
                for row in cursor.fetchall()
            ]
        except Exception:
            return []
    
    def find_structure_in_standards(self, structure_code: str) -> List[Dict]:
        """Compatibilidade - busca estrutura (usa explode_structure internamente)."""
        return self.explode_structure(structure_code)
    
    def close(self):
        """Fecha conexão com o banco."""
        if self.conn:
            self.conn.close()
            self.conn = None


# Alias para compatibilidade com imports existentes
DatabaseLoader = SQLiteDatabaseLoader


if __name__ == "__main__":
    # Teste
    loader = SQLiteDatabaseLoader()
    loader.load_all()
    
    if loader.is_loaded:
        print("\n--- Teste de Descrição SAP ---")
        print(loader.get_sap_description("30053492"))
        
        print("\n--- Teste de sap_codes proxy ---")
        print("30053492 in sap_codes:", "30053492" in loader.sap_codes)
        print("sap_codes['30053492']:", loader.sap_codes.get("30053492", "N/A"))
        
        print("\n--- Teste de Busca FTS ---")
        results = loader.find_material_by_description(["POSTE", "CONCRETO"], limit=5)
        for code, desc, score in results:
            print(f"  [{score}] {code}: {desc[:50]}...")
        
        print("\n--- Teste de Explosão ---")
        materials = loader.explode_structure("B1")
        for mat in materials[:5]:
            print(f"  - {mat['code']}: {mat['desc'][:40]}... x{mat['qty']}")
        
        loader.close()
