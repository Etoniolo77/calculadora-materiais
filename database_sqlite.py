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
    
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(os.getcwd())
        self.db_path = self.base_dir / self.DB_FILE
        self.conn: Optional[sqlite3.Connection] = None
        self.is_loaded = False
        
        # Compatibilidade com código legado - usa proxy para queries SQL
        self._sap_proxy = None  # Inicializado após load_all
        self.unified_db = None
    
    @property
    def sap_codes(self):
        """Retorna proxy que simula dict mas faz queries SQL."""
        if self._sap_proxy is None and self.conn:
            self._sap_proxy = SAPCodesProxy(self.conn)
        return self._sap_proxy if self._sap_proxy else {}
    
    def load_all(self, force_legacy: bool = False) -> None:
        """Conecta ao banco SQLite."""
        if not self.db_path.exists():
            print(f"⚠ Banco SQLite não encontrado: {self.db_path}")
            print("  Execute 'python migrate_to_sqlite.py' primeiro.")
            return
        
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            
            # Contar registros para log
            cursor = self.conn.execute("SELECT COUNT(*) FROM materiais")
            mat_count = cursor.fetchone()[0]
            
            cursor = self.conn.execute("SELECT COUNT(*) FROM estruturas")
            est_count = cursor.fetchone()[0]
            
            print(f"✓ SQLite conectado: {mat_count} materiais, {est_count} estruturas")
            
            # Carregar unified_db.json para metadados (cinta_lookup, etc)
            unified_path = self.base_dir / "unified_db.json"
            if unified_path.exists():
                import json
                with open(unified_path, 'r', encoding='utf-8') as f:
                    self.unified_db = json.load(f)
                print("✓ Unified DB carregado para metadados")
            
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
        """
        if not self.conn:
            return []
        
        if isinstance(search_terms, str):
            search_terms = [search_terms]
        
        exclude_upper = [t.upper() for t in exclude_terms] if exclude_terms else []
        
        # Construir query FTS5 com prefixo (*) para simular "contains" do legado
        fts_query = " OR ".join([f'"{term}"*' for term in search_terms])
        
        try:
            # Aumentar limit no SQL para permitir filtragem posterior e encontrar melhores scores
            # Como a busca é OR, termos comuns ("POSTE") retornam milhares de resultados.
            # Precisamos buscar muitos para garantir que o Python encontre os que tem maior interseção.
            sql_limit = 1000 
            
            cursor = self.conn.execute(
                """
                SELECT codigo, descricao
                FROM materiais_fts 
                WHERE materiais_fts MATCH ?
                LIMIT ?
                """,
                (fts_query, sql_limit)
            )
            
            results = []
            for row in cursor.fetchall():
                desc_upper = row[1].upper()
                
                # Verificar exclusões (termos)
                if any(ex in desc_upper for ex in exclude_upper):
                    continue
                
                # REGRA DE NEGÓCIO: Filtrar códigos de desativação (começando com 9)
                if str(row[0]).startswith('9'):
                    continue

                score = sum(1 for term in search_terms if term.upper() in desc_upper)
                results.append((row[0], row[1], score))
            
            results.sort(key=lambda x: x[2], reverse=True)
            return results[:limit]
            
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
        """Busca materiais na tabela BOM como fallback."""
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
        
        if not materials:
            print(f"⚠ Estrutura {structure_code} não encontrada no SQLite")
            return [{'code': 'VERIFICAR', 'desc': f'VERIFICAR ESTRUTURA {structure_code}', 'qty': 1}]
        
        return materials
    
    def get_bom_items(self, categoria: str, subcategoria: str) -> List[Dict]:
        """Retorna itens BOM para uma categoria/subcategoria específica."""
        if not self.conn:
            return []
        
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
