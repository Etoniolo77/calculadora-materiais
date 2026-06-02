"""
Database Loader - Versão SQLite (runtime oficial)

IMPORTANTE:
- Runtime da calculadora lê SEMPRE do banco oficial: data/materials.db
- Excel é somente fonte de alimentação do banco (scripts de atualização),
  não fonte direta de runtime.
"""

from __future__ import annotations

import csv
import json
import math
import sqlite3
from typing import Dict, List, Optional, Tuple

try:
    from .project_paths import OFFICIAL_DB_PATH, OFFICIAL_UNIFIED_DB_PATH
except ImportError:
    from project_paths import OFFICIAL_DB_PATH, OFFICIAL_UNIFIED_DB_PATH  # type: ignore


class SAPCodesProxy:
    """Proxy que simula dicionário usando queries SQL."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __contains__(self, code: str) -> bool:
        cursor = self.conn.execute(
            "SELECT 1 FROM materiais WHERE codigo = ? LIMIT 1",
            (str(code),),
        )
        return cursor.fetchone() is not None

    def __getitem__(self, code: str) -> str:
        cursor = self.conn.execute(
            "SELECT descricao FROM materiais WHERE codigo = ?",
            (str(code),),
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
    """Carregador de banco usando SQLite com fonte oficial fixa em data/materials.db."""

    def __init__(self, base_dir: str = "."):
        self.db_path = OFFICIAL_DB_PATH
        self.unified_path = OFFICIAL_UNIFIED_DB_PATH
        self.conn: Optional[sqlite3.Connection] = None
        self.is_loaded = False
        self._sap_proxy = None
        self.unified_db = None
        self._csv_structures_cache: Dict[str, List[Dict]] = {}

    @property
    def sap_codes(self):
        if self._sap_proxy is None and self.conn:
            self._sap_proxy = SAPCodesProxy(self.conn)
        return self._sap_proxy if self._sap_proxy else {}

    def load_all(self, force_legacy: bool = False) -> None:
        """Conecta ao banco SQLite oficial e carrega metadados complementares."""
        if not self.db_path.exists():
            print(f"[ERRO] Banco SQLite oficial não encontrado: {self.db_path}")
            print("  Execute: python scripts/update_and_sync_materials.py")
            self.is_loaded = False
            return

        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row

            cursor = self.conn.execute("SELECT COUNT(*) FROM materiais")
            mat_count = cursor.fetchone()[0]

            cursor = self.conn.execute("SELECT COUNT(*) FROM estruturas")
            est_count = cursor.fetchone()[0]

            print(
                "[OK] SQLite oficial conectado: "
                f"{mat_count} materiais, {est_count} estruturas ({self.db_path})"
            )

            if self.unified_path.exists() and self.unified_path.stat().st_size > 0:
                with open(self.unified_path, "r", encoding="utf-8") as f:
                    self.unified_db = json.load(f)
                print(f"[OK] Unified DB carregado: {self.unified_path}")
            else:
                self.unified_db = {}
                print(f"[AVISO] unified_db.json não encontrado: {self.unified_path}")

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
            (str(code),),
        )
        result = cursor.fetchone()
        return result[0] if result else f"SAP {code}"

    def find_material_by_description(
        self, search_terms, limit: int = 5, exclude_terms: List[str] = None
    ) -> List[Tuple[str, str, int]]:
        """
        Busca materiais por termos na descrição usando FTS5.
        Retorna lista de tuplas (codigo, descricao, score).
        """
        if not self.conn:
            return []

        if isinstance(search_terms, str):
            search_terms = [search_terms]

        terms_upper = [t.upper() for t in search_terms]
        exclude_upper = [t.upper() for t in exclude_terms] if exclude_terms else []

        def _apply_filters(rows):
            out = []
            for row in rows:
                desc_upper = row[1].upper()
                if any(ex in desc_upper for ex in exclude_upper):
                    continue
                if str(row[0]).startswith("9"):
                    continue
                out.append(row)
            return out

        def _idf_score(desc_upper: str, idf_map: dict) -> float:
            base = sum(idf_map.get(t, 0.5) for t in terms_upper if t in desc_upper)
            length_penalty = 1.0 / (1.0 + len(desc_upper) / 200.0)
            return base * length_penalty

        try:
            and_query = " AND ".join([f'"{t}"*' for t in search_terms])
            cursor = self.conn.execute(
                "SELECT codigo, descricao FROM materiais_fts WHERE materiais_fts MATCH ? LIMIT 500",
                (and_query,),
            )
            rows = _apply_filters(cursor.fetchall())

            if not rows:
                or_query = " OR ".join([f'"{t}"*' for t in search_terms])
                cursor = self.conn.execute(
                    "SELECT codigo, descricao FROM materiais_fts WHERE materiais_fts MATCH ? LIMIT 1000",
                    (or_query,),
                )
                rows = _apply_filters(cursor.fetchall())

            if not rows:
                return []

            n_docs = len(rows)
            idf_map = {}
            for term in terms_upper:
                df = sum(1 for r in rows if term in r[1].upper())
                idf_map[term] = math.log((n_docs + 1) / (df + 1)) + 1.0

            scored = [
                (row[0], row[1], _idf_score(row[1].upper(), idf_map)) for row in rows
            ]
            scored.sort(key=lambda x: x[2], reverse=True)
            return scored[:limit]

        except Exception as e:
            print(f"Erro na busca FTS: {e}")
            return self._fallback_search(search_terms, limit, exclude_terms)

    def _fallback_search(
        self, search_terms: List[str], limit: int, exclude_terms: List[str] = None
    ) -> List[Tuple[str, str, int]]:
        """Busca fallback sem FTS."""
        cursor = self.conn.execute("SELECT codigo, descricao FROM materiais")
        results = []

        exclude_upper = [t.upper() for t in exclude_terms] if exclude_terms else []

        for row in cursor.fetchall():
            desc_upper = row[1].upper()

            if any(ex in desc_upper for ex in exclude_upper):
                continue
            if str(row[0]).startswith("9"):
                continue

            score = sum(1 for term in search_terms if term.upper() in desc_upper)
            if score > 0:
                results.append((row[0], row[1], score))

        results.sort(key=lambda x: x[2], reverse=True)
        return results[:limit]

    def explode_structure(
        self, structure_code: str, nivel: int = 1, pole_type_str: str = ""
    ) -> List[Dict]:
        """
        Retorna lista de materiais para uma estrutura, filtrada por tipo de poste.
        Sem fallback em tabelas legadas de BOM.
        """
        if not self.conn:
            return [
                {
                    "code": "VERIFICAR",
                    "desc": f"BD não conectado - {structure_code}",
                    "qty": 1,
                }
            ]

        structure_code = str(structure_code).strip().upper()

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

        cursor = self.conn.execute(
            """
            SELECT e.id, e.tipo_poste
            FROM estruturas e
            WHERE e.codigo = ? AND (e.tipo_poste = ? OR e.tipo_poste = 'ALL')
            ORDER BY CASE WHEN e.tipo_poste = ? THEN 0 ELSE 1 END
            """,
            (structure_code, tipo_filtro, tipo_filtro),
        )

        estruturas = cursor.fetchall()

        if not estruturas:
            cursor = self.conn.execute(
                "SELECT id FROM estruturas WHERE codigo = ?",
                (structure_code,),
            )
            estruturas = cursor.fetchall()

        if not estruturas:
            csv_fallback = self._explode_structure_from_csv(
                structure_code,
                pole_type_str=pole_type_str,
                is_dt=is_dt,
            )
            if csv_fallback:
                print(
                    f"[FALLBACK-CSV] Estrutura {structure_code} carregada da lista consolidada"
                )
                return csv_fallback

            print(
                f"[AVISO] Estrutura {structure_code} não encontrada no SQLite oficial"
            )
            return [
                {
                    "code": "VERIFICAR",
                    "desc": f"VERIFICAR ESTRUTURA {structure_code}",
                    "qty": 1,
                }
            ]

        materials = []
        seen_materials = set()
        for est_row in estruturas:
            est_id = est_row[0]

            cursor = self.conn.execute(
                """
                SELECT material_codigo, material_descricao, quantidade
                FROM estrutura_materiais
                WHERE estrutura_id = ?
                """,
                (est_id,),
            )

            for mat_row in cursor.fetchall():
                dedupe_key = (
                    str(mat_row[0] or "").strip(),
                    str(mat_row[1] or "").strip(),
                    float(mat_row[2] or 0),
                )
                if dedupe_key in seen_materials:
                    continue
                seen_materials.add(dedupe_key)
                materials.append(
                    {
                        "code": mat_row[0],
                        "desc": mat_row[1] or self.get_sap_description(mat_row[0]),
                        "qty": mat_row[2],
                    }
                )

        if not materials:
            print(
                f"[AVISO] Estrutura {structure_code} sem composição no SQLite oficial"
            )
            return [
                {
                    "code": "VERIFICAR",
                    "desc": f"VERIFICAR ESTRUTURA {structure_code}",
                    "qty": 1,
                }
            ]

        return materials

    def _load_csv_structures_cache(self) -> None:
        if self._csv_structures_cache:
            return

        csv_path = self.db_path.parent / "estruturas_materiais.csv"
        if not csv_path.exists():
            return

        try:
            with csv_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    code = str(row.get("estrutura_codigo", "") or "").strip().upper()
                    sap = str(row.get("material_codigo", "") or "").strip()
                    desc = str(row.get("material_descricao", "") or "").strip()
                    if not code or not sap:
                        continue
                    try:
                        qty = float(
                            str(row.get("quantidade", "1") or "1").replace(",", ".")
                        )
                    except ValueError:
                        qty = 1.0

                    tipo_raw = (
                        str(row.get("estrutura_tipo_poste", "ALL") or "ALL")
                        .upper()
                        .strip()
                    )
                    tipo_norm = "ALL"
                    if "DT" in tipo_raw or "MADEIRA" in tipo_raw:
                        tipo_norm = "DT"
                    elif "CIRCULAR" in tipo_raw or "FIBRA" in tipo_raw:
                        tipo_norm = "CIRCULAR"

                    self._csv_structures_cache.setdefault(code, []).append(
                        {
                            "code": sap,
                            "desc": desc or self.get_sap_description(sap),
                            "qty": qty,
                            "type": tipo_norm,
                        }
                    )
        except Exception as e:
            print(f"[AVISO] Falha ao carregar fallback CSV de estruturas: {e}")

    def _explode_structure_from_csv(
        self, structure_code: str, pole_type_str: str = "", is_dt: bool = False
    ) -> List[Dict]:
        self._load_csv_structures_cache()
        code = str(structure_code or "").strip().upper()
        rows = list(self._csv_structures_cache.get(code, []))
        if not rows:
            return []

        wanted_type = "DT" if is_dt else "CIRCULAR"
        filtered = [r for r in rows if r.get("type") in {wanted_type, "ALL"}]
        if not filtered:
            filtered = rows

        out: Dict[str, Dict] = {}
        for r in filtered:
            sap = str(r.get("code", "") or "").strip()
            if not sap:
                continue
            if sap not in out:
                out[sap] = {
                    "code": sap,
                    "desc": str(r.get("desc", "") or self.get_sap_description(sap)),
                    "qty": 0.0,
                }
            out[sap]["qty"] += float(r.get("qty", 0) or 0)

        return list(out.values())

    def get_bom_items(self, categoria: str, subcategoria: str) -> List[Dict]:
        """Compatibilidade: tabela BOM legada desabilitada no runtime atual."""
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
