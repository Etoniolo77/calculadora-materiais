"""
Database Loader - Versão Supabase PostgreSQL (Ponte de Compatibilidade)
Substitui o database_sqlite.py anterior para conectar ao Supabase na nuvem.
"""

from __future__ import annotations

import os
import json
import math
import psycopg2
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

try:
    from .project_paths import OFFICIAL_UNIFIED_DB_PATH, BACKEND_DIR
except ImportError:
    from project_paths import OFFICIAL_UNIFIED_DB_PATH, BACKEND_DIR  # type: ignore

# Carregar variáveis do .env do backend
ENV_PATH = BACKEND_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")


class SAPCodesProxy:
    """Proxy que simula dicionário usando queries SQL no PostgreSQL."""

    def __init__(self, loader: SupabaseDatabaseLoader):
        self.loader = loader

    def __contains__(self, code: str) -> bool:
        conn = self.loader.get_conn()
        if not conn:
            return False
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM materiais WHERE codigo = %s LIMIT 1",
                    (str(code),),
                )
                return cursor.fetchone() is not None
        except Exception as e:
            print(f"[Supabase] Erro em __contains__: {e}")
            return False

    def __getitem__(self, code: str) -> str:
        conn = self.loader.get_conn()
        if not conn:
            raise KeyError(code)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT descricao FROM materiais WHERE codigo = %s",
                    (str(code),),
                )
                result = cursor.fetchone()
                if result:
                    return result[0]
            raise KeyError(code)
        except Exception as e:
            print(f"[Supabase] Erro em __getitem__: {e}")
            raise KeyError(code)

    def get(self, code: str, default: str = None) -> str:
        try:
            return self[code]
        except KeyError:
            return default

    def keys(self):
        conn = self.loader.get_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT codigo FROM materiais")
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            print(f"[Supabase] Erro em keys(): {e}")
            return []

    def values(self):
        conn = self.loader.get_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT descricao FROM materiais")
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            print(f"[Supabase] Erro em values(): {e}")
            return []

    def items(self):
        conn = self.loader.get_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT codigo, descricao FROM materiais")
                return list(cursor.fetchall())
        except Exception as e:
            print(f"[Supabase] Erro em items(): {e}")
            return []


class SupabaseDatabaseLoader:
    """Carregador de banco usando PostgreSQL hospedado no Supabase."""

    def __init__(self, base_dir: str = "."):
        self.conn_str = SUPABASE_DB_URL
        self.unified_path = OFFICIAL_UNIFIED_DB_PATH
        self._conn: Optional[psycopg2.connection] = None
        self.is_loaded = False
        self._sap_proxy = None
        self.unified_db = None
        self._sap_desc_cache: dict[str, str] = {}
        self._find_material_cache: dict[tuple, list[tuple[str, str, float]]] = {}
        self._explode_structure_cache: dict[tuple[str, str], list[dict]] = {}

    def get_conn(self) -> Optional[psycopg2.connection]:
        """Garante e retorna uma conexão ativa e saudável com o Postgres."""
        if self._conn is None or self._conn.closed:
            # Recarregar do ambiente caso tenha mudado
            env_str = os.environ.get("SUPABASE_DB_URL")
            if env_str:
                self.conn_str = env_str
            
            if not self.conn_str or "SEU_PROJETO" in self.conn_str:
                return None
            try:
                self._conn = psycopg2.connect(self.conn_str)
                self._conn.autocommit = True
            except Exception as e:
                print(f"[Supabase] Erro ao conectar ao Postgres: {e}")
                self._conn = None
        return self._conn

    @property
    def sap_codes(self):
        if self._sap_proxy is None:
            self._sap_proxy = SAPCodesProxy(self)
        return self._sap_proxy

    def load_all(self, force_legacy: bool = False) -> None:
        """Verifica conexão com Supabase e carrega unified_db local."""
        conn = self.get_conn()
        if not conn:
            self.is_loaded = False
            return

        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM materiais")
                mat_count = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM estruturas")
                est_count = cursor.fetchone()[0]

            print(
                "[OK] Supabase PostgreSQL conectado: "
                f"{mat_count} materiais, {est_count} estruturas."
            )

            # Carregar o unified_db local
            if self.unified_path.exists() and self.unified_path.stat().st_size > 0:
                with open(self.unified_path, "r", encoding="utf-8") as f:
                    self.unified_db = json.load(f)
                print(f"[OK] Unified DB carregado: {self.unified_path}")
            else:
                self.unified_db = {}
                print(f"[AVISO] unified_db.json não encontrado: {self.unified_path}")

            self.is_loaded = True
        except Exception as e:
            print(f"[Supabase] Erro ao carregar dados: {e}")
            self.is_loaded = False

    def get_sap_description(self, code: str) -> str:
        """Retorna descrição do código SAP."""
        cache_key = str(code or "").strip()
        if cache_key in self._sap_desc_cache:
            return self._sap_desc_cache[cache_key]

        conn = self.get_conn()
        if not conn:
            value = f"SAP {code}"
            self._sap_desc_cache[cache_key] = value
            return value

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT descricao FROM materiais WHERE codigo = %s",
                    (str(code),),
                )
                result = cursor.fetchone()
                value = result[0] if result else f"SAP {code}"
                self._sap_desc_cache[cache_key] = value
                return value
        except Exception as e:
            print(f"[Supabase] Erro em get_sap_description: {e}")
            value = f"SAP {code}"
            self._sap_desc_cache[cache_key] = value
            return value

    def find_material_by_description(
        self, search_terms, limit: int = 5, exclude_terms: List[str] = None
    ) -> List[Tuple[str, str, float]]:
        """
        Busca materiais por termos na descrição usando pg_trgm (similaridade e ILIKE) no Postgres.
        Retorna lista de tuplas (codigo, descricao, score).
        Tenta busca estrita com AND primeiro, e caso não encontre nada, tenta OR com filtragem de termos essenciais.
        """
        conn = self.get_conn()
        if not conn:
            return []

        if isinstance(search_terms, str):
            search_terms = [search_terms]

        normalized_terms = tuple(str(term).strip().upper() for term in search_terms if str(term).strip())
        exclude_upper = tuple(t.upper() for t in exclude_terms) if exclude_terms else tuple()
        cache_key = (normalized_terms, int(limit), exclude_upper)
        if cache_key in self._find_material_cache:
            return list(self._find_material_cache[cache_key])

        # Construir cláusulas WHERE baseadas em ILIKE para filtrar os termos obrigatórios
        query_parts = []
        params = []

        for term in normalized_terms:
            query_parts.append("descricao ILIKE %s")
            params.append(f"%{term}%")

        if not query_parts:
            return []

        where_clause = " AND ".join(query_parts)

        # Tratar exclusões
        if exclude_upper:
            for ex in exclude_upper:
                where_clause += " AND descricao NOT ILIKE %s"
                params.append(f"%{ex}%")

        # Excluir materiais de teste que iniciam com 9
        where_clause += " AND codigo NOT LIKE '9%%'"

        # Termo base para calcular o score de similaridade (pg_trgm)
        base_term = " ".join(search_terms)
        query_params = [base_term] + params + [limit]

        query = f"""
            SELECT codigo, descricao, similarity(descricao, %s) as score
            FROM materiais
            WHERE {where_clause}
            ORDER BY score DESC, descricao
            LIMIT %s
        """

        try:
            with conn.cursor() as cursor:
                cursor.execute(query, query_params)
                rows = cursor.fetchall()
                if rows:
                    result = [(r[0], r[1], float(r[2] or 0)) for r in rows]
                    self._find_material_cache[cache_key] = result
                    return list(result)
        except Exception as e:
            print(f"[Supabase] Erro na busca estrita com pg_trgm: {e}")
            return []

        # Fallback para OR caso a busca estrita com AND não retorne resultados
        or_where = "(" + " OR ".join(query_parts) + ")"
        if exclude_upper:
            for ex in exclude_upper:
                or_where += " AND descricao NOT ILIKE %s"
        or_where += " AND codigo NOT LIKE '9%%'"

        # Aumentamos o limite da busca OR para filtrar depois via termos essenciais
        query_params_or = [base_term] + params + [limit * 10]
        query_or = f"""
            SELECT codigo, descricao, similarity(descricao, %s) as score
            FROM materiais
            WHERE {or_where}
            ORDER BY score DESC, descricao
            LIMIT %s
        """

        try:
            with conn.cursor() as cursor:
                cursor.execute(query_or, query_params_or)
                rows = cursor.fetchall()
        except Exception as e:
            print(f"[Supabase] Erro na busca fallback OR com pg_trgm: {e}")
            return []

        # Filtrar linhas pelos termos essenciais (ex. '15KVA', '12M', '300DAN')
        import re
        essential_patterns = [
            re.compile(r"^\d+(?:\.\d+)?KVA$", re.I),
            re.compile(r"^\d+M$", re.I),
            re.compile(r"^\d+DAN$", re.I),
            re.compile(r"^\d+MM2$", re.I),
            re.compile(r"^(?:HV|KV)$", re.I)
        ]
        essential_terms = []
        for term in search_terms:
            for pattern in essential_patterns:
                if pattern.match(term):
                    essential_terms.append(term.upper())
                    break

        if essential_terms:
            filtered_rows = []
            for r in rows:
                desc_normalized = r[1].upper().replace(" ", "")
                if all(et in desc_normalized for et in essential_terms):
                    filtered_rows.append(r)
            rows = filtered_rows

        result = [(r[0], r[1], float(r[2] or 0)) for r in rows[:limit]]
        self._find_material_cache[cache_key] = result
        return list(result)

    def explode_structure(
        self, structure_code: str, nivel: int = 1, pole_type_str: str = ""
    ) -> List[Dict]:
        """
        Retorna lista de materiais para uma estrutura, filtrada por tipo de poste.
        """
        conn = self.get_conn()
        if not conn:
            return [
                {
                    "code": "VERIFICAR",
                    "desc": f"BD não conectado - {structure_code}",
                    "qty": 1,
                }
            ]

        structure_code = str(structure_code).strip().upper()
        cache_key = (structure_code, str(pole_type_str or "").strip().upper())
        if cache_key in self._explode_structure_cache:
            return list(self._explode_structure_cache[cache_key])

        is_dt = False
        if pole_type_str:
            p_upper = str(pole_type_str).upper()
            if (
                p_upper.startswith("DT")
                or p_upper.startswith("RT")
                or "DUPLO T" in p_upper
            ):
                is_dt = True

        tipo_filtro = "DT" if is_dt else "CIRCULAR"

        try:
            with conn.cursor() as cursor:
                # Busca estruturas que correspondem ao código e tipo de poste
                cursor.execute(
                    """
                    SELECT id, tipo_poste
                    FROM estruturas
                    WHERE codigo = %s AND (tipo_poste = %s OR tipo_poste = 'ALL')
                    ORDER BY CASE WHEN tipo_poste = %s THEN 0 ELSE 1 END
                    """,
                    (structure_code, tipo_filtro, tipo_filtro),
                )
                estruturas = cursor.fetchall()

                # Fallback: se não achar com filtro, tenta achar qualquer uma com esse código
                if not estruturas:
                    cursor.execute(
                        "SELECT id FROM estruturas WHERE codigo = %s",
                        (structure_code,),
                    )
                    estruturas = cursor.fetchall()

                if not estruturas:
                    print(
                        f"[AVISO] Estrutura {structure_code} não encontrada no Supabase"
                    )
                    result = [
                        {
                            "code": "VERIFICAR",
                            "desc": f"VERIFICAR ESTRUTURA {structure_code}",
                            "qty": 1,
                        }
                    ]
                    self._explode_structure_cache[cache_key] = result
                    return list(result)

                materials = []
                seen_materials = set()
                
                for est_row in estruturas:
                    est_id = est_row[0]

                    cursor.execute(
                        """
                        SELECT material_codigo, material_descricao, quantidade
                        FROM estrutura_materiais
                        WHERE estrutura_id = %s
                        """,
                        (est_id,),
                    )

                    for mat_row in cursor.fetchall():
                        m_code = str(mat_row[0] or "").strip()
                        m_desc = str(mat_row[1] or "").strip()
                        m_qty = float(mat_row[2] or 0)
                        
                        dedupe_key = (m_code, m_desc, m_qty)
                        if dedupe_key in seen_materials:
                            continue
                        seen_materials.add(dedupe_key)
                        
                        materials.append(
                            {
                                "code": m_code,
                                "desc": m_desc or self.get_sap_description(m_code),
                                "qty": m_qty,
                            }
                        )

                if not materials:
                    print(
                        f"[AVISO] Estrutura {structure_code} sem composição no Supabase"
                    )
                    result = [
                        {
                            "code": "VERIFICAR",
                            "desc": f"VERIFICAR ESTRUTURA {structure_code}",
                            "qty": 1,
                        }
                    ]
                    self._explode_structure_cache[cache_key] = result
                    return list(result)

                self._explode_structure_cache[cache_key] = materials
                return list(materials)

        except Exception as e:
            print(f"[Supabase] Erro ao explodir estrutura {structure_code}: {e}")
            result = [
                {
                    "code": "VERIFICAR",
                    "desc": f"Erro de banco - {structure_code}",
                    "qty": 1,
                }
            ]
            self._explode_structure_cache[cache_key] = result
            return list(result)

    def get_structure_supported_pole_types(self, structure_code: str) -> set[str]:
        """Retorna os tipos de poste suportados por uma estrutura no catálogo."""
        code = str(structure_code or "").strip().upper()
        if not code:
            return set()

        supported: set[str] = set()
        conn = self.get_conn()
        if not conn:
            return supported

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT DISTINCT tipo_poste FROM estruturas WHERE codigo = %s",
                    (code,),
                )
                for row in cursor.fetchall():
                    value = str(row[0] or "").strip().upper()
                    if value:
                        supported.add(value)
        except Exception as e:
            print(f"[Supabase] Erro em get_structure_supported_pole_types: {e}")

        return supported

    def get_bom_items(self, categoria: str, subcategoria: str) -> List[Dict]:
        """Compatibilidade."""
        return []

    def find_structure_in_standards(self, structure_code: str) -> List[Dict]:
        """Compatibilidade - busca estrutura."""
        return self.explode_structure(structure_code)

    @property
    def conn(self):
        return self.get_conn()

    def list_all_structures(self) -> list[str]:
        """Retorna uma lista de todos os códigos de estruturas cadastrados no Supabase."""
        conn = self.get_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT DISTINCT codigo FROM estruturas WHERE codigo IS NOT NULL ORDER BY codigo"
                )
                return [str(row[0] or "").upper().strip() for row in cursor.fetchall()]
        except Exception as e:
            print(f"[Supabase] Erro em list_all_structures: {e}")
            return []

    def structure_exists(self, structure_code: str, pole_type: str = "") -> bool:
        """Verifica se a estrutura existe no banco Supabase."""
        conn = self.get_conn()
        if not conn:
            return False
        code = str(structure_code or "").strip().upper()
        if not code:
            return False

        is_dt = False
        p_up = str(pole_type or "").upper()
        if p_up.startswith("DT") or p_up.startswith("RT") or "DUPLO T" in p_up:
            is_dt = True
        tipo_filtro = "DT" if is_dt else "CIRCULAR"

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 1
                    FROM estruturas
                    WHERE codigo = %s AND (tipo_poste = %s OR tipo_poste = 'ALL')
                    LIMIT 1
                    """,
                    (code, tipo_filtro),
                )
                if cursor.fetchone():
                    return True

                cursor.execute(
                    "SELECT 1 FROM estruturas WHERE codigo = %s LIMIT 1",
                    (code,),
                )
                return cursor.fetchone() is not None
        except Exception as e:
            print(f"[Supabase] Erro em structure_exists: {e}")
            return False

    def list_structure_candidates(self, prefix: str) -> list[str]:
        """Retorna estruturas que começam com o prefixo especificado."""
        conn = self.get_conn()
        if not conn:
            return []
        pref = str(prefix or "").strip().upper()
        if not pref:
            return []
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT DISTINCT codigo FROM estruturas WHERE UPPER(codigo) LIKE %s ORDER BY codigo",
                    (f"{pref}%",),
                )
                return [str(row[0]).upper().strip() for row in cursor.fetchall()]
        except Exception as e:
            print(f"[Supabase] Erro em list_structure_candidates: {e}")
            return []

    def close(self):
        """Fecha conexão com o banco."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None



# Mantém apelidos idênticos ao SQLiteDatabaseLoader para compatibilidade de imports externos
SQLiteDatabaseLoader = SupabaseDatabaseLoader
DatabaseLoader = SupabaseDatabaseLoader
