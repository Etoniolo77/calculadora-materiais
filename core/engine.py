"""
=== PROPOSTA DE ALTERAÇÃO - engine.py ===
Corrige: C2, C3, C4, A1, A2, A3, A4, M3, B2
Veja: RELATORIO_INCONSISTENCIAS.md para detalhes
"""

import json
import os
import re
from pathlib import Path

import pandas as pd

# [FIX C2] REMOVIDO: caminhos legados de planilhas antigas não são mais usados.

# SQLite Database Loader (substitui JSON/Pickle)
try:
    from .database_sqlite import SQLiteDatabaseLoader as DatabaseLoader  # type: ignore
except ImportError:
    try:
        from database_sqlite import SQLiteDatabaseLoader as DatabaseLoader
    except ImportError:
        from database_loader import DatabaseLoader

try:
    from .project_paths import OFFICIAL_MANUAL_CORRECTIONS_PATH, ensure_runtime_dirs
except ImportError:
    from project_paths import (  # type: ignore
        OFFICIAL_MANUAL_CORRECTIONS_PATH,
        ensure_runtime_dirs,
    )

# Mapeamento de Diâmetros para Códigos SAP de Cintas
CINTA_SAP_MAP = {
    100: "30053132",
    140: "30053133",
    160: "30053134",
    180: "30053136",
    200: "30053137",
    220: "30053138",
    230: "30053139",
    240: "30053140",
    260: "30053141",
    280: "30053143",
    290: "30053144",
    300: "30053145",
    320: "30053146",
    340: "30053148",
    360: "30053149",
    380: "30053150",
}

# Mapeamento de Bitolas para Códigos SAP de Alças MT (Alumínio Nu)
ALCA_MT_NU_MAP = {
    "4ANA": "30050155",
    "2ANA": "30050152",
    "4AN": "30050155",
    "2AN": "30050152",
    "1/0ANA": "30050150",
    "2/0ANA": "30050151",
    "3/0ANA": "30050153",
    "4/0ANA": "30050154",
    "336": "30050149",
}

# Alças para Cabos Protegidos MT
ALCA_MT_PROT_MAP = {
    "35": "10000994",
    "50": "10000995",
    "70": "10004273",
    "150": "30050157",
    "185": "30050159",
}

# Mapeamento Manual de Estruturas sem DB
MANUAL_EST_MAP = {
    "BR1579": [("30053140", 1), ("30053137", 1)],
}

SMTR_VARIANTS = [
    "SMTR - CABO AL 3C 2X120MM2+70MM2 1KV",
    "SMTR - CABO AL 3C 2X70MM2+70MM2 1KV",
    "SMTR - CABO AL 4C 3X35MM2+35MM2 1KV",
    "SMTR - CABO AL 4C 3X70MM2+70MM2 1KV",
    "SMTR - CABO AL PE RET 4C 3X120MM2 70MM2 1KV",
    "SMTR - CABO MULT XLPENI AL 3C 2X35MM2+35MM2 1KV",
]

# Adesivos refletivos para identificação de trafo (ESTF + 6 dígitos).
ESTF_STICKER_MAP = {
    "A": "30058669",
    "B": "30058670",
    "C": "30058671",
    "D": "30058672",
    "E": "30058673",
    "F": "30058674",
    "G": "30058687",
    "H": "30058688",
    "I": "30058675",
    "J": "30058689",
    "K": "30058676",
    "L": "30058677",
    "M": "30058678",
    "N": "30058679",
    "P": "30058680",
    "Q": "30058681",
    "R": "30058682",
    "S": "30058683",
    "T": "30058684",
    "U": "30058685",
    "V": "30058690",
    "W": "30058691",
    "X": "30058692",
    "Y": "30058693",
    "Z": "30058686",
    "0": "30058702",
    "1": "30058694",
    "2": "30058695",
    "3": "30058696",
    "4": "30058697",
    "5": "30058698",
    "6": "30058699",
    "7": "30058700",
    "8": "30058701",
}

# ─────────────────────────────────────────────────────────────────────────────
# ALIASES DE ESTRUTURAS
# Mapeia nomes curtos/alternativos usados em PDFs para o código canônico do DB.
# REGRA: nunca alterar o extrator para corrigir nomenclatura de projeto.
#        Aliases aqui permitem que o mesmo extrator funcione com múltiplos projetos.
#
# Formato: 'ALIAS_NO_PDF': 'CODIGO_NO_BANCO'
# ─────────────────────────────────────────────────────────────────────────────
STRUCTURE_ALIASES = {
    # ── Estruturas secundárias de ramal ──────────────────────────────────────
    # Prefixo numérico (1S2, 2S2, etc.) é tratado no parser como multiplicador.
    # Aqui mantemos apenas normalização de sufixo de ocorrência visual.
    "S1(1)": "S1",
    "S2(1)": "S2",
    "S3(1)": "S3",
    "S4(1)": "S4",
    "1S1(1)": "S1",
    "1S2(1)": "S2",
    "1S3(1)": "S3",
    "1S4(1)": "S4",
    "1S1": "S1",
    "1S2": "S2",
    "1S3": "S3",
    "1S4": "S4",
    # ── Hastes de aterramento ─────────────────────────────────────────────────
    # H3/H5 = Haste 5/8" (Catálogo CPFL)
    "H5": "1HASTE",
    "H3": "1HASTE",
    "H1": "1HASTE",
    "HASTE": "1HASTE",
    # ── Estruturas N (neutro/passagem) — variações regionais ─────────────────
    "N1F": "N1",
    "N2F": "N2",
    # N3F tem composição própria revisada pelo especialista; não deve colapsar em N3.
    "N3F": "N3F",
    # N4F tem composição própria revisada pelo especialista; não deve colapsar em N4.
    "N4F": "N4F",
    "N5F": "N5",
    "N1A": "N1",
    "N2A": "N2",
    # ── Estruturas B (bifurcação/derivação) ──────────────────────────────────
    "B1F": "B1",
    "B2F": "B2",
    "B3F": "B3",
    "B4F": "B4",
    # ── Estruturas ET (entroncamento) ─────────────────────────────────────────
    "ET1": "ET1T",
    "ET2": "ET2T",
    "ET3": "ET3T",
    "ET4": "ET4A",
    # ── Estruturas U (ultima) ─────────────────────────────────────────────────
    "U1F": "U1",
    "U2F": "U2",
    "U3F": "U3",
    "U4F": "U4",
    # ── Estruturas M (montagem especial / medição) ────────────────────────────
    "M1F": "M1",
    "M2F": "M2",
    # ── Abreviações de estai ──────────────────────────────────────────────────
    "EST": "ESTAI",
    "ESTAI1": "ESTAI",
    # ── Outros aliases comuns de campo ───────────────────────────────────────
    # Adicionar novos aliases aqui conforme novos projetos forem testados.
    # Formato: 'ALIAS_NO_PDF': 'CODIGO_NO_BANCO'
    # Sempre documentar: alias → destino — fonte/norma.
}

# Ferragens de Fixação para Cintas (Poste Circular)
FASTENER_BOLT = "30058226"  # PARAFUSO CAB QUAD 16MM 125MM AC
FASTENER_WASHER = "30050463"  # ARRUELA LISA QUAD AC 16MM 38MM
CROSSARM_STD = "30054575"  # CRUZETA P/POSTE AC 1010/20 2,4M
TRAFO_SUPPORT_TRI = "30060418"  # SUPORTE TRANSF ACO POST CON CIR 210MM


class MaterialEngine:
    def __init__(self):
        self.desc_to_sap = {}
        # [FIX M3] Removidos: self.df_kits e self.df_sap (nunca populados, código legado morto)
        self.depara = {}
        self.is_loaded = False

        # Database Loader
        self.db_loader = None
        self.detected_cables = {"MT": None, "BT": None}
        self.selected_smtr_structure = None
        self.current_trafo_context = None
        self.current_estai_context = None
        self.audit_log = []
        ensure_runtime_dirs()
        self.manual_corrections_path = str(OFFICIAL_MANUAL_CORRECTIONS_PATH)
        self.manual_corrections = self._load_manual_corrections()

        # [FIX A1] Mapeamento de Cintas ampliado com postes faltantes
        self.clamp_logic = {
            # Poste 12m 1000daN
            ("C12/1000", "N"): [("30053140", 2)],
            ("C12/1000", "B"): [("30053140", 1), ("30053141", 1)],
            ("C12/1000", "U"): [("30053140", 2)],
            ("C12/1000", "S"): [("30053143", 1)],
            # Poste 12m 600daN
            ("C12/600", "N"): [("30053137", 2)],
            ("C12/600", "B"): [("30053137", 1), ("30053138", 1)],
            ("C12/600", "U"): [("30053137", 2)],
            ("C12/600", "S"): [("30053140", 1)],
            # Poste 12m 400daN (NOVO - Faltava)
            ("C12/400", "N"): [("30053136", 2)],
            ("C12/400", "B"): [("30053136", 1), ("30053137", 1)],
            ("C12/400", "U"): [("30053136", 2)],
            ("C12/400", "S"): [("30053139", 1)],
            # Poste 12m 300daN
            ("C12/300", "N"): [("30053136", 2)],
            ("C12/300", "B"): [("30053136", 1), ("30053137", 1)],
            ("C12/300", "U"): [("30053136", 2)],
            ("C12/300", "S"): [("30053138", 1)],
            # Poste 11m 1000daN (NOVO - Faltava)
            ("C11/1000", "N"): [("30053140", 2)],
            ("C11/1000", "B"): [("30053140", 1), ("30053141", 1)],
            ("C11/1000", "U"): [("30053140", 2)],
            ("C11/1000", "S"): [("30053143", 1)],
            # Poste 11m 600daN
            ("C11/600", "N"): [("30053137", 2)],
            ("C11/600", "B"): [("30053137", 1), ("30053138", 1)],
            ("C11/600", "U"): [("30053137", 2)],
            ("C11/600", "S"): [("30053140", 1)],
            # Poste 11m 400daN (NOVO - Faltava)
            ("C11/400", "N"): [("30053136", 2)],
            ("C11/400", "B"): [("30053136", 1), ("30053137", 1)],
            ("C11/400", "U"): [("30053136", 2)],
            ("C11/400", "S"): [("30053138", 1)],
            ("C11/300", "N"): [("30053136", 2)],
            ("C11/300", "B"): [("30053136", 1), ("30053137", 1)],
            ("C11/300", "U"): [("30053136", 2)],
            ("C11/300", "S"): [("30053138", 1)],
            # === POSTES DUPLO T (DT / D) - Ferragens de Fixação ===
            # Postes DT não usam Cintas, usam Parafusos Passantes e Arruelas.
            # Mapeando tipos comuns encontrados nos novos diagramas.
            ("DT11/300", "N"): [("30058234", 1), ("30050463", 2)],
            ("DT11/300", "B"): [("30058234", 1), ("30050463", 2)],
            ("DT11/300", "U"): [("30058234", 1), ("30050463", 2)],
            ("DT11/300", "S"): [("30058234", 1), ("30050463", 2)],
            ("D11/300", "N"): [("30058234", 1), ("30050463", 2)],
            ("D11/300", "B"): [("30058234", 1), ("30050463", 2)],
            ("D11/300", "U"): [("30058234", 1), ("30050463", 2)],
            ("D11/300", "S"): [("30058234", 1), ("30050463", 2)],
            ("DT12/300", "N"): [("30058234", 1), ("30050463", 2)],
            ("DT12/300", "B"): [("30058234", 1), ("30050463", 2)],
            ("DT12/300", "U"): [("30058234", 1), ("30050463", 2)],
            ("DT12/300", "S"): [("30058234", 1), ("30050463", 2)],
        }

    def _normalize_pole_type(self, pole_type: str) -> str:
        """
        Normaliza tipologia de poste para reduzir ruído de OCR/entrada.
        Exemplos:
        - DI10/300 -> DT10/300
        - M11/300  -> C11/300
        """
        raw = str(pole_type or "").upper().strip()
        if not raw:
            return raw
        norm = raw.replace("X", "/").replace(" ", "")

        # Quando houver sufixos misturados (ex.: C09/600,2S2(2)/FL), captura
        # apenas o primeiro token que representa tipologia de poste.
        m = re.search(
            r"(DT\d{1,2}/\d{3,4}|D\d{1,2}/\d{3,4}|C\d{1,2}/\d{3,4}|M\d{1,2}/\d{3,4}|DI\d{1,2}/\d{3,4})",
            norm,
        )
        if m:
            norm = m.group(1)

        # OCR comum: DI ao invés de DT
        if re.match(r"^DI\d{1,2}/\d{3,4}$", norm):
            norm = "DT" + norm[2:]

        # OCR comum: M ao invés de C para circular
        if re.match(r"^M\d{1,2}/\d{3,4}$", norm):
            norm = "C" + norm[1:]

        return norm

    def _structure_exists_in_db(self, structure_code: str, pole_type: str = "") -> bool:
        """
        Verifica se a estrutura existe no banco para a tipologia do poste
        (ou fallback ALL), sem depender de alias.
        """
        if not self.db_loader:
            return False
        return self.db_loader.structure_exists(structure_code, pole_type)

    def _list_structure_candidates(self, prefix: str) -> list[str]:
        if not self.db_loader:
            return []
        return self.db_loader.list_structure_candidates(prefix)


    def _resolve_transformer_signature(self, trafo_desc: str) -> list[str]:
        txt = str(trafo_desc or "").upper().strip()
        if not txt:
            return []
        match = re.search(r"(MONO|TRI|BI)[-\s]*([0-9]+(?:[.,][0-9]+)?)\s*KVA", txt)
        if not match:
            return []
        phase = match.group(1)
        kva_raw = match.group(2).replace(" ", "")
        kva_dot = kva_raw.replace(",", ".")
        kva_comma = kva_raw.replace(".", ",")
        terms = [f"{kva_dot}KVA", f"{kva_comma}KVA"]
        if phase == "MONO":
            terms.extend(["MONO", "1F"])
        elif phase == "TRI":
            terms.extend(["TRIFASICO", "TRIFÁSICO", "3F"])
        elif phase == "BI":
            terms.extend(["BIFASICO", "BIFÁSICO", "2F"])
        return terms

    def _get_est_category(self, est_code: str) -> str:
        est = str(est_code or "").upper().strip()
        if est.startswith("N") or est.startswith("ET") or est.startswith("CE"):
            return "N"
        if est.startswith("B"):
            return "B"
        if est.startswith("U"):
            return "U"
        if "S" in est:
            return "S"
        if est.startswith("M"):
            return "N"
        return ""

    def _resolve_clamp_lookup(self, pole_type: str, est_cat: str) -> tuple[str, str] | None:
        p_type = self._normalize_pole_type(str(pole_type).upper())
        p_type_norm = p_type.replace("x", "/").replace(" ", "")
        lookup = (p_type_norm.split("(")[0], est_cat)
        if lookup in self.clamp_logic:
            return lookup

        m = re.match(r"^C(\d{1,2})/(\d{3,4})$", lookup[0])
        if not m:
            return None

        altura = int(m.group(1))
        esforco = int(m.group(2))
        candidates = []
        for (pt_key, cat_key), _mats in self.clamp_logic.items():
            if cat_key != est_cat:
                continue
            m2 = re.match(r"^C(\d{1,2})/(\d{3,4})$", pt_key)
            if not m2:
                continue
            h2 = int(m2.group(1))
            e2 = int(m2.group(2))
            score = (0 if e2 == esforco else 1, abs(h2 - altura))
            candidates.append((score, pt_key))
        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        return (candidates[0][1], est_cat)

    def _infer_trafo_context(self, pole_map, p_id) -> str:
        if not pole_map or p_id not in pole_map:
            return ""
        data = pole_map[p_id]
        t_val = data.get("Trafo")
        if t_val and str(t_val).upper() != "NONE":
            return str(t_val)

        # 2. Buscar em outros postes do mesmo projeto
        for other_id, p_data in pole_map.items():
            t_other = p_data.get("Trafo")
            if t_other and str(t_other).upper() != "NONE":
                return str(t_other)

        # 3. Fallback inteligente baseado em outras estruturas do poste
        ests = data.get("Est", []) or []
        is_trifasico = False
        for est in ests:
            e_up = str(est).upper()
            if any(term in e_up for term in ["3F", "4F", "B3", "N3", "U3", "S3", "CE3", "CE4"]):
                is_trifasico = True
                break

        if is_trifasico:
            return "TRI-45KVA"
        else:
            return "MONO-15KVA"

    def _resolve_contextual_structure_code(
        self,
        structure_code: str,
        pole_type: str = "",
        trafo_desc: str = "",
        estai_value=None,
    ) -> str | None:
        raw = str(structure_code or "").upper().strip()
        if not raw or not self.db_loader:
            return None

        if raw == "XH5":
            qty = 1
            try:
                qty = max(1, int(estai_value or 1))
            except Exception:
                qty = 1
            prefixes = [f"{qty}XH5", "1XH5"]
            for prefix in prefixes:
                candidates = self._list_structure_candidates(prefix)
                if candidates:
                    return candidates[0]
            return None

        if raw not in {"ET1BR", "ET1T", "ET4", "ET4A"}:
            return None

        terms = self._resolve_transformer_signature(trafo_desc)
        if not terms:
            return None

        prefix = {
            "ET1BR": "ET1BR PARA ET1T",
            "ET1T": "ET1T",
            "ET4": "ET4A",
            "ET4A": "ET4A",
        }.get(raw, raw)
        candidates = self._list_structure_candidates(prefix)
        if not candidates:
            return None

        scored = []
        for cand in candidates:
            score = sum(1 for term in terms if term in cand)
            scored.append((score, cand))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if scored and scored[0][0] > 0:
            return scored[0][1]
        return None

    def _resolve_structure_code(
        self,
        structure_code: str,
        pole_type: str = "",
        trafo_desc: str = "",
        estai_value=None,
    ) -> tuple[str, bool]:
        """
        Resolve código de estrutura para busca no banco.
        Regra: tentar código exato primeiro; usar alias somente como fallback.
        Retorna (codigo_resolvido, alias_aplicado).
        """
        raw = str(structure_code or "").upper().strip()
        if not raw:
            return raw, False

        aliased = STRUCTURE_ALIASES.get(raw, raw)

        # Política principal para evitar comportamento assintomático:
        # exato no BD sempre vence; alias só quando exato não existir.
        if self._structure_exists_in_db(raw, pole_type):
            return raw, False

        trafo_ctx = trafo_desc or self.current_trafo_context or ""
        estai_ctx = estai_value if estai_value is not None else self.current_estai_context

        contextual = self._resolve_contextual_structure_code(
            raw,
            pole_type=pole_type,
            trafo_desc=trafo_ctx,
            estai_value=estai_ctx,
        )
        if contextual and self._structure_exists_in_db(contextual, pole_type):
            return contextual, True

        if raw == "SMTR":
            smtr_variant = self.selected_smtr_structure or self._detect_smtr_variant()
            if smtr_variant and self._structure_exists_in_db(smtr_variant, pole_type):
                return smtr_variant, True
        if aliased != raw and self._structure_exists_in_db(aliased, pole_type):
            return aliased, True

        # Fallback legado: mantém comportamento anterior quando não há sinal
        # claro no banco (importante para não quebrar fluxos antigos).
        return aliased, aliased != raw

    def _prime_detected_cables(self, cables_list):
        for c in cables_list or []:
            tipo = str(c.get("Tipo", "") or "").upper().strip()
            desc = str(c.get("Desc", "") or "").strip()
            if tipo in {"MT", "BT"} and desc and not self.detected_cables.get(tipo):
                self.detected_cables[tipo] = desc

    def _detect_smtr_variant(self, cables_list=None):
        cable_descs = []
        if cables_list:
            cable_descs.extend(
                str(c.get("Desc", "") or "").upper() for c in cables_list if c
            )
        for key in ("BT", "MT"):
            val = str(self.detected_cables.get(key, "") or "").upper().strip()
            if val:
                cable_descs.append(val)

        if not cable_descs:
            return None

        for desc in cable_descs:
            compact = re.sub(r"[^A-Z0-9]+", "", desc.upper())
            if "XLPENI" in desc and "35" in desc:
                return "SMTR - CABO MULT XLPENI AL 3C 2X35MM2+35MM2 1KV"
            if (
                any(term in desc for term in ["PE RET", "PRET", "PE RET."])
                and "120" in desc
                and "70" in desc
            ):
                return "SMTR - CABO AL PE RET 4C 3X120MM2 70MM2 1KV"
            if "3X70" in desc and any(
                term in desc for term in ["(70)", "+70", "70MM2"]
            ):
                return "SMTR - CABO AL 4C 3X70MM2+70MM2 1KV"
            if "2X70" in desc and any(
                term in desc for term in ["(70)", "+70", "70MM2"]
            ):
                return "SMTR - CABO AL 3C 2X70MM2+70MM2 1KV"
            if "3X35" in desc and any(
                term in desc for term in ["(35)", "+35", "35MM2"]
            ):
                return "SMTR - CABO AL 4C 3X35MM2+35MM2 1KV"
            if "2X120" in desc or "120MM2+70MM2" in desc:
                return "SMTR - CABO AL 3C 2X120MM2+70MM2 1KV"
            if "3X7070" in compact:
                return "SMTR - CABO AL 4C 3X70MM2+70MM2 1KV"
            if "2X7070" in compact:
                return "SMTR - CABO AL 3C 2X70MM2+70MM2 1KV"
            if "3X3535" in compact:
                return "SMTR - CABO AL 4C 3X35MM2+35MM2 1KV"
            if "2X12070" in compact:
                return "SMTR - CABO AL 3C 2X120MM2+70MM2 1KV"

        return None

    def _expand_composite_structures(self, structures: list[str]) -> list[str]:
        """
        Expande estruturas compostas separadas por hífen, + ou /.

        Exemplos:
        - U4-1S4      -> [U4, 1S4]
        - U3-CE1      -> [U3, CE1]
        - U4-1S4-CE3  -> [U4, 1S4, CE3]
        """
        expanded: list[str] = []
        for raw in structures or []:
            token = str(raw or "").upper().strip()
            token = re.sub(r"\s+", "", token)
            if not token:
                continue

            parts = re.split(r"(?<=[A-Z0-9])[\-+/](?=[A-Z0-9])", token)
            parts = [p.strip() for p in parts if p and p.strip()]
            if not parts:
                continue

            for part in parts:
                if not part:
                    continue

                # Remove sufixo de ocorrência visual (ex.: S2(1), CE4(2)).
                part_clean = re.sub(r"\(\d+\)$", "", part)

                # Regra operacional: prefixo numérico em token de estrutura
                # representa multiplicador, não código canônico.
                # Exemplos: 2S2 => S2 + S2 ; 1S4 => S4.
                m_mul = re.match(r"^(\d+)([A-Z][A-Z0-9]*)$", part_clean)
                if m_mul:
                    qty = int(m_mul.group(1))
                    base = m_mul.group(2)
                    # Regra generalista: qualquer estrutura com numeral
                    # antecedendo o código representa multiplicador.
                    # Ex.: 1S4 => S4, 2CE2 => CE2+CE2, 3SMTR => SMTR+SMTR+SMTR.
                    if qty > 0:
                        expanded.extend([base] * qty)
                        continue

                expanded.append(part_clean)

        return expanded

    def _load_manual_corrections(self):
        """Carrega correções manuais de SAP por descrição."""
        if not os.path.exists(self.manual_corrections_path):
            return {}
        try:
            with open(self.manual_corrections_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f"[WARN] Falha ao carregar manual_corrections.json: {e}")
        return {}

    def _save_manual_corrections(self):
        """Persiste correções manuais."""
        try:
            Path(self.manual_corrections_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.manual_corrections_path, "w", encoding="utf-8") as f:
                json.dump(self.manual_corrections, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] Falha ao salvar manual_corrections.json: {e}")

    def register_manual_correction(
        self, sap_code: str, description: str, source: str = "ui"
    ) -> bool:
        """Registra correção manual para reaproveitamento em próximos cálculos."""
        sap = str(sap_code or "").strip()
        desc = str(description or "").strip()
        if not sap or not desc:
            return False
        if sap.upper().startswith("VERIFICAR"):
            return False
        key = desc.upper()
        self.manual_corrections[key] = {
            "sap": sap,
            "descricao": desc,
            "source": source,
        }
        self._save_manual_corrections()
        return True

    def _confidence_from_score(self, score):
        """Converte score de busca em confiança normalizada (0..1) adaptada para pg_trgm."""
        try:
            s = float(score)
        except (ValueError, TypeError):
            return 0.85
        
        # Para pg_trgm (similaridade 0..1):
        # 0.30 é um match sólido (~75% de confiança)
        # 0.50 é um match excelente (~90% de confiança)
        # 1.00 é idêntico (~99% de confiança)
        if s >= 0.5:
            conf = 0.90 + (0.09 * (s - 0.5) / 0.5)
        elif s >= 0.3:
            conf = 0.75 + (0.15 * (s - 0.3) / 0.2)
        else:
            conf = 0.40 + (0.35 * s / 0.3)
            
        return max(0.40, min(0.99, round(conf, 2)))

    def _apply_manual_correction(self, mat):
        """Aplica de-para manual pela descrição quando SAP vier como VERIFICAR."""
        sap = str(mat.get("Código SAP", "") or "").strip()
        if sap and not sap.upper().startswith("VERIFICAR"):
            return mat
        desc = str(mat.get("Descrição", "") or "").strip().upper()
        if not desc:
            return mat
        correction = self.manual_corrections.get(desc)
        if correction:
            mat["Código SAP"] = correction.get("sap", mat.get("Código SAP"))
            mat["Descrição"] = correction.get("descricao", mat.get("Descrição"))
            mat["Confiança"] = max(float(mat.get("Confiança", 0.2)), 0.95)
            mat["Origem"] = f"{mat.get('Origem', '')} [CORRECAO-MANUAL]".strip()
        return mat

    def _ensure_confidence(self, mat):
        """Garante que todo material tenha campo de confiança."""
        if "Confiança" in mat:
            try:
                mat["Confiança"] = float(mat["Confiança"])
                return mat
            except (ValueError, TypeError):
                pass
        sap = str(mat.get("Código SAP", "") or "")
        mat["Confiança"] = 0.2 if sap.upper().startswith("VERIFICAR") else 0.9
        return mat

    def _resolve_verificar_parafuso(
        self, code: str, desc: str, structure_code: str = ""
    ):
        """
        Resolve automaticamente itens VERIFICAR de parafuso M16 x comprimento.
        Retorna (code, desc) resolvido ou (code, desc) original quando não achar.
        """
        code_str = str(code or "").upper()
        desc_str = str(desc or "")
        desc_up = desc_str.upper()

        if not self.db_loader:
            return code, desc
        if "PARAF" not in desc_up:
            return code, desc
        if "VERIFICAR" not in code_str:
            return code, desc

        # Extrai comprimento de "M16 x 400", "16MM 400MM", etc.
        length_mm = None
        m = re.search(r"M\s*16\s*[Xx]\s*(\d{2,4})", desc_up)
        if m:
            length_mm = m.group(1)
        if not length_mm:
            m = re.search(r"PARAF\w*\s+(\d{2,4})\s*MM", desc_up)
            if m:
                length_mm = m.group(1)
        if not length_mm:
            m = re.search(r"16\s*MM.*?(\d{2,4})\s*MM", desc_up)
            if m:
                length_mm = m.group(1)
        if not length_mm and "..." in desc_up:
            est_up = str(structure_code or "").upper().strip()
            # Heurística de engenharia: estruturas secundárias 1S3/1S4 usam, em geral,
            # parafuso M16 x 250mm para fixação em poste.
            if est_up in {"1S3", "1S4", "S3", "S4", "1S3(1)", "1S4(1)"}:
                length_mm = "250"
        if not length_mm:
            return code, desc

        # Quando o cadastro vier sem bitola explícita (ex.: "PARAFUSO 400mm"),
        # assumimos M16 para estruturas de rede de distribuição.
        bitola_mm = "16MM"
        if re.search(r"\b12\s*MM\b", desc_up):
            bitola_mm = "12MM"
        elif re.search(r"\b10\s*MM\b", desc_up):
            bitola_mm = "10MM"

        terms = ["PARAFUSO", bitola_mm, f"{length_mm}MM"]

        # Refina tipo do parafuso quando a descrição já trouxer pista.
        if "FRANCES" in desc_up:
            terms.append("FRANCES")
        if "OLHAL" in desc_up:
            terms.append("OLHAL")
        if "QUAD" in desc_up or "CAB" in desc_up:
            terms.append("QUAD")

        candidates = self.db_loader.find_material_by_description(
            terms,
            limit=12,
            exclude_terms=["PORCA", "ARRUELA", "SUPORTE", "CONECTOR"],
        )
        if not candidates:
            return code, desc

        # Seleção estável:
        # 1) deve conter 16MM e comprimento exato
        # 2) preferir AC
        # 3) preferir série 30058 (cadastro consolidado no projeto)
        # 4) maior score original
        filtered = []
        for sap, sap_desc, score in candidates:
            d = str(sap_desc).upper()
            if bitola_mm not in d or f"{length_mm}MM" not in d:
                continue
            ac_bonus = 1 if " AC" in d else 0
            family_bonus = 1 if str(sap).startswith("30058") else 0
            filtered.append((sap, sap_desc, score, ac_bonus, family_bonus))

        if not filtered:
            return code, desc

        filtered.sort(key=lambda x: (x[4], x[3], float(x[2])), reverse=True)
        best = filtered[0]
        return best[0], best[1]

    def load_databases(self):
        """Carrega todas as bases de dados"""
        if not self.is_loaded:
            print("Carregando bases de dados...")
            self.db_loader = DatabaseLoader()
            self.db_loader.load_all()
            self.is_loaded = True
            print("Bases carregadas!")

    def get_pole_sap(self, pole_type):
        """Tenta encontrar o código SAP do poste na base carregada usando busca por termos."""
        p_type = str(pole_type).upper()
        if p_type.replace(" ", "") in {"C12/1000", "12X1000CIR", "C12X1000"}:
            return "10054741", (
                self.db_loader.get_sap_description("10054741")
                if self.db_loader
                else "POSTE CIRC CONCR 12M 1000DAN C-23"
            )
        termos_busca = ["POSTE"]

        if "C" in p_type:
            termos_busca.extend(["CIRCULAR", "CONCR", "CIRC"])
        elif "DT" in p_type or "DUPLO T" in p_type or "D" in p_type:
            # [FIX] Usar DUPL para bater com DUPLO e DUPL (banco usa DUPL T)
            termos_busca.extend(["DUPL", "DT"])
            if "DT" not in termos_busca:
                termos_busca.append("DT")

        # [FIX C4] import re removido — já importado no topo do arquivo
        nums = re.findall(r"\d+", p_type)
        if len(nums) >= 2:
            try:
                h = str(int(nums[0]))
                c = str(int(nums[1]))
            except Exception:
                h = nums[0]
                c = nums[1]
            termos_busca.append(f"{h}M")
            termos_busca.append(f"{c}DAN")
        elif len(nums) == 1:
            try:
                h = str(int(nums[0]))
            except Exception:
                h = nums[0]
            termos_busca.append(f"{h}M")

        # [FIX] Se for DT ou D, excluir termos de MADEIRA ou MAD para evitar falso positivo
        exclude_terms = ["CONEXAO", "TOPO", "BRACADEIRA", "LUMINARIA", "SUPORTE"]
        if "DT" in p_type or "DUPLO" in p_type or ("D" in p_type and "DAN" in p_type):
            exclude_terms.extend(["MAD", "MADEIRA", "EUCAL"])

        if self.db_loader:
            results = self.db_loader.find_material_by_description(
                termos_busca, limit=1, exclude_terms=exclude_terms
            )
            if results:
                return results[0][0], results[0][1]

        return "VERIFICAR", f"POSTE {pole_type}"

    def clean_code(self, val):
        try:
            if pd.isna(val) or val == "":
                return ""
            s = str(val).split(".")[0].strip()
            if s.isdigit():
                return s
            return s
        except:
            return str(val).strip()

    def get_vivid_code(self, code, description):
        code = self.clean_code(code)

        if code in self.depara:
            return self.depara[code]

        if code.startswith("3"):
            return code

        if code.startswith("1"):
            desc_up = str(description).upper()
            if "CINTA" in desc_up or "BRAÇADEIRA" in desc_up:
                return code
            return code

        desc_clean = str(description).upper().replace("SUCATA", "").strip()
        if desc_clean in self.desc_to_sap:
            return self.desc_to_sap[desc_clean]

        words = [w for w in desc_clean.split() if len(w) > 3]
        if len(words) >= 2:
            for sap_desc, sap_code in self.desc_to_sap.items():
                if all(w in sap_desc for w in words[:2]):
                    return sap_code
        return None if code.startswith("9") else code

    def resolve_clamps(self, pole_type, structures, p_id=""):
        """Retorna as braçadeiras E materiais das estruturas baseado no poste e estruturas."""
        mats = []
        p_type = self._normalize_pole_type(str(pole_type).upper())
        p_type_norm = p_type.replace("x", "/").replace(" ", "")
        is_dt_pole = p_type_norm.startswith("DT") or p_type_norm.startswith("D")
        p_id_label = p_id if p_id else p_type_norm
        expanded_structures = self._expand_composite_structures(structures)
        est_cats_with_clamp_logic = set()
        # Contador por categoria para permitir variação por nível quando
        # houver estruturas repetidas no mesmo poste (ex.: B2F 1º/2º).
        cat_level_counter = {}
        # Quando alguma estrutura do mesmo poste já contém a cruzeta padrão,
        # evitamos injeção adicional de suporte (dupla contagem).
        pole_has_crossarm_from_structure = False
        repeated_b2f_on_pole = (
            sum(1 for s in expanded_structures if str(s).upper().strip() == "B2F") > 1
        )
        b2f_count_on_pole = sum(
            1 for s in expanded_structures if str(s).upper().strip() == "B2F"
        )
        has_et1t_on_pole = any(
            str(s).upper().strip() == "ET1T" for s in expanded_structures
        )
        b2f_non_repeating_saps = {"30053443", "30056458"}

        # 1. Adicionar o próprio POSTE
        pole_str = str(pole_type).upper()
        if "(E)" not in pole_str and "(R)" not in pole_str:
            p_clean = pole_str.split("(")[0].strip()
            p_code, p_desc = self.get_pole_sap(p_clean)
            mats.append(
                {
                    "Origem": f"Poste {p_id}",
                    "Código SAP": p_code,
                    "Descrição": p_desc,
                    "Quantidade": 1,
                }
            )

        # Pré-análise das estruturas do poste para evitar injeções duplicadas.
        if self.db_loader and self.is_loaded:
            for est_raw in expanded_structures:
                est = str(est_raw).upper().strip()
                if "(E)" in est or "(R)" in est:
                    continue
                est_canonical, _ = self._resolve_structure_code(est, pole_type)
                structure_materials = self.db_loader.explode_structure(
                    est_canonical, pole_type_str=pole_type
                )
                if any(
                    str(sm.get("code", "")).strip() == CROSSARM_STD
                    for sm in structure_materials
                ):
                    pole_has_crossarm_from_structure = True
                    break

        # 2. Braçadeiras e Ferragens (Somente para Novos)
        for est_raw in expanded_structures:
            est_str = str(est_raw).upper()
            if "(E)" in est_str or "(R)" in est_str:
                continue

            est = est_str.strip()
            if est == "B2F":
                # B2F é tratado por regra contextual do poste (nível/combinação),
                # evitando duplicidade com a lógica genérica de ferragens.
                continue
            if est in {"ET4A", "ET1T"}:
                # ET4A segue estritamente a composição do banco revisado.
                # Sem complemento por lógica genérica de ferragens.
                continue
            if est == "SMTR":
                # SMTR deve seguir estritamente a composição da base (especialista),
                # sem complemento pela lógica genérica de ferragens.
                continue
            est_cat = self._get_est_category(est)

            lookup = self._resolve_clamp_lookup(pole_type, est_cat)
            if lookup and lookup in self.clamp_logic:
                est_cats_with_clamp_logic.add(est_cat)
                clamp_items = list(self.clamp_logic[lookup])
                # Regra de nível para postes cônicos/circulares:
                # estruturas repetidas da mesma categoria (ex.: B2F 1º/2º)
                # usam cintas de diâmetros diferentes por ocorrência.
                if (
                    est_cat == "B"
                    and lookup[0].startswith("C")
                    and len(clamp_items) >= 2
                    and all(float(q) == 1 for _, q in clamp_items[:2])
                ):
                    lvl_idx = cat_level_counter.get(est_cat, 0)
                    chosen_idx = min(lvl_idx, len(clamp_items) - 1)
                    sap, qty = clamp_items[chosen_idx]
                    desc = (
                        self.db_loader.sap_codes.get(str(sap))
                        if self.db_loader
                        else None
                    ) or f"BRACADEIRA SAP {sap}"
                    mats.append(
                        {
                            "Origem": f"Ferragem {est} em {p_id}",
                            "Código SAP": sap,
                            "Descrição": desc,
                            "Quantidade": qty,
                        }
                    )
                    cat_level_counter[est_cat] = lvl_idx + 1
                else:
                    for sap, qty in clamp_items:
                        desc = (
                            self.db_loader.sap_codes.get(str(sap))
                            if self.db_loader
                            else None
                        ) or f"BRACADEIRA SAP {sap}"
                        mats.append(
                            {
                                "Origem": f"Ferragem {est} em {p_id}",
                                "Código SAP": sap,
                                "Descrição": desc,
                                "Quantidade": qty,
                            }
                        )

        # 3. Injeção automática de fixação desativada.
        # Motivo: em cenários reais auditados, essa regra genérica duplicava
        # parafusos/arruelas já contemplados pela estrutura técnica revisada.
        # A fixação deve vir da composição técnica do banco (estrutura_materiais).

        # 4. Explodir estruturas em materiais componentes (Somente para Novos)
        if self.db_loader and self.is_loaded:
            for est_raw in expanded_structures:
                est_str = str(est_raw).upper()
                suffix = " (RETIRADA)" if "(R)" in est_str else ""
                if "(E)" in est_str or "(R)" in est_str:
                    continue

                est = est_str.strip()

                # Resolve estrutura com prioridade para código exato no BD.
                est_canonical, alias_applied = self._resolve_structure_code(
                    est, pole_type
                )
                if alias_applied:
                    print(f"[ALIAS] {est} -> {est_canonical} em Poste {pole_type}")

                structure_materials = self.db_loader.explode_structure(
                    est_canonical, pole_type_str=pole_type
                )
                current_est_has_crossarm = any(
                    str(sm.get("code", "")).strip() == CROSSARM_STD
                    for sm in structure_materials
                )

                # Auditoria (Gap Analysis) — usa nome original para rastreabilidade
                if not structure_materials or (
                    len(structure_materials) == 1
                    and structure_materials[0]["code"] == "VERIFICAR"
                ):
                    self.audit_log.append(
                        {
                            "type": "Estrutura Nao Encontrada",
                            "item": est,
                            "item_canonical": est_canonical,
                            "source": f"Poste {pole_type}",
                            "severity": "Alta",
                        }
                    )

                for mat in structure_materials:
                    code = mat["code"]
                    desc = str(mat["desc"])
                    qty = mat["qty"]
                    est_cat = self._get_est_category(est)
                    strict_db_structure = est in {
                        "ET1T",
                        "ET4A",
                        "SMTR",
                    } or est.startswith("SMTR")

                    desc_upper = desc.upper()
                    is_cinta_bracadeira = (
                        "CINTA" in desc_upper
                        or "BRAÇADEIRA" in desc_upper
                        or "BRACADEIRA" in desc_upper
                    ) and "ALÇA" not in desc_upper

                    if strict_db_structure:
                        mats.append(
                            {
                                "Origem": f"Estrutura {est} em {p_id}",
                                "Código SAP": code,
                                "Descrição": desc + suffix,
                                "Quantidade": qty,
                            }
                        )
                        continue

                    # Evita dupla contagem de cintas: se a categoria da estrutura já foi
                    # resolvida pela clamp_logic, ignora a cinta vinda da explosão de kit.
                    if (
                        is_cinta_bracadeira
                        and est_cat in est_cats_with_clamp_logic
                        and est not in {"SMTR", "ET1T", "ET4A", "B2F"}
                    ):
                        continue

                    # --- LÓGICA DE CINTAS DINÂMICAS ---
                    if is_cinta_bracadeira:
                        # Regra de negócio: poste DT/retangular não usa cinta circular.
                        if is_dt_pole:
                            continue
                        cat = "CINTA 1"
                        if "ESTAI" in desc_upper:
                            cat = "ESTAI 1"
                        elif "NIVEL" in desc_upper:
                            cat = "NIVEL 1"
                        elif "RECK" in desc_upper or "REK" in desc_upper:
                            cat = "RECK 1"
                        elif "SECUNDARIA" in desc_upper:
                            cat = "SECUNDARIA"
                        elif "LUMINARIA" in desc_upper:
                            cat = "LUMINARIA"

                        diameter = None
                        lookup_table = (
                            self.db_loader.unified_db.get("cinta_lookup", {})
                            if (self.db_loader and self.db_loader.unified_db)
                            else {}
                        )

                        p_normalized = (
                            p_type.replace("DT", "")
                            .replace("RT", "")
                            .replace("C", "")
                            .replace("/", "-")
                            .replace(" ", "")
                            .strip()
                        )
                        p_keys = [p_normalized, p_normalized.replace("-", "/"), p_type]

                        for pk in p_keys:
                            if pk in lookup_table:
                                diameter = lookup_table[pk].get(cat)
                                if diameter:
                                    break

                        if diameter and diameter in CINTA_SAP_MAP:
                            code = CINTA_SAP_MAP[diameter]
                            if self.db_loader and code in self.db_loader.sap_codes:
                                desc = self.db_loader.sap_codes[code] + suffix
                            else:
                                desc = f"CINTA POSTE AC ZC F {diameter}MM{suffix}"
                        elif diameter:
                            code = "VERIFICAR"
                            desc = f"CINTA POSTE AC ZC F {diameter}MM (SAP DESCONHECIDO){suffix}"
                        elif code == "VERIFICAR-POSTE" or code == "10004437":
                            desc = f"CINTA (DIAMETRO NAO ENCONTRADO PARA POSTE {p_type}){suffix}"

                    elif "ALÇA" in desc_upper and (
                        code == "VERIFICAR" or code == "VERIFICAR-CABO"
                    ):
                        mt_c = self.detected_cables.get("MT")
                        if mt_c:
                            mt_c_up = mt_c.upper()
                            resolved = False
                            for bitola, sap in ALCA_MT_NU_MAP.items():
                                if bitola in mt_c_up:
                                    code = sap
                                    desc = (
                                        self.db_loader.sap_codes[sap]
                                        if self.db_loader
                                        and sap in self.db_loader.sap_codes
                                        else f"ALÇA {bitola}"
                                    ) + suffix
                                    resolved = True
                                    break

                            if not resolved:
                                for bitola, sap in ALCA_MT_PROT_MAP.items():
                                    if bitola in mt_c_up:
                                        code = sap
                                        desc = (
                                            self.db_loader.sap_codes[sap]
                                            if self.db_loader
                                            and sap in self.db_loader.sap_codes
                                            else f"ALÇA {bitola}"
                                        ) + suffix
                                        resolved = True
                                        break

                            if resolved and code != "VERIFICAR" and self.db_loader:
                                rich_desc = self.db_loader.get_sap_description(code)
                                if rich_desc:
                                    desc = rich_desc + suffix

                    # Verificação Manual para Estruturas como BR1579
                    if code == "VERIFICAR" and est in MANUAL_EST_MAP:
                        for m_sap, m_qty in MANUAL_EST_MAP[est]:
                            m_desc = (
                                self.db_loader.sap_codes.get(m_sap, f"ITEM {m_sap}")
                                if self.db_loader
                                else m_sap
                            )
                            mats.append(
                                {
                                    "Origem": f"Estrutura {est} (Manual)",
                                    "Código SAP": m_sap,
                                    "Descrição": m_desc + suffix,
                                    "Quantidade": m_qty * qty,
                                }
                            )
                        continue

                    # Regra operacional para B2F em dois níveis no mesmo poste:
                    # alguns itens de montagem terminal não se repetem por nível.
                    if (
                        est == "B2F"
                        and repeated_b2f_on_pole
                        and str(code).strip() in b2f_non_repeating_saps
                    ):
                        continue
                    if est == "B2F" and str(code).strip() == "30053143":
                        continue

                    # Correção automática para VERIFICAR-POSTE de parafusos M16 x comprimento
                    code, resolved_desc = self._resolve_verificar_parafuso(
                        code, desc, structure_code=est
                    )
                    if resolved_desc:
                        desc = (
                            str(resolved_desc) + suffix
                            if suffix and suffix not in str(resolved_desc)
                            else str(resolved_desc)
                        )

                    mats.append(
                        {
                            "Origem": f"Estrutura {est} em {p_id}",
                            "Código SAP": code,
                            "Descrição": desc,
                            "Quantidade": qty,
                        }
                    )

                    # INJEÇÃO: Cruzeta para estruturas de montagem
                    # Evita duplicidade quando a própria composição da estrutura
                    # já contém a cruzeta padrão.
                    if est in ["ET1T", "ET4A"] and CROSSARM_STD not in [
                        m["Código SAP"] for m in mats
                    ]:
                        if (not current_est_has_crossarm) and (
                            not pole_has_crossarm_from_structure
                        ):
                            mats.append(
                                {
                                    "Origem": f"Suporte em {p_id}",
                                    "Código SAP": CROSSARM_STD,
                                    "Descrição": self.db_loader.get_sap_description(
                                        CROSSARM_STD
                                    ),
                                    "Quantidade": 1,
                                }
                            )

        # Regra contextual B2F por poste:
        # - Duplo nível (ex.: B2F 1º/2º): usa distribuição revisada
        # - Simples com ET1T: usa distribuição revisada
        if b2f_count_on_pole >= 2:
            mats.extend(
                [
                    {
                        "Origem": f"Ferragem B2F em {p_id}",
                        "Código SAP": "30053141",
                        "Descrição": self.db_loader.get_sap_description("30053141"),
                        "Quantidade": 3,
                    },
                    {
                        "Origem": f"Estrutura B2F em {p_id}",
                        "Código SAP": "30058120",
                        "Descrição": self.db_loader.get_sap_description("30058120"),
                        "Quantidade": 5,
                    },
                    {
                        "Origem": f"Estrutura B2F em {p_id}",
                        "Código SAP": "30058097",
                        "Descrição": self.db_loader.get_sap_description("30058097"),
                        "Quantidade": 2,
                    },
                ]
            )
        elif b2f_count_on_pole == 1 and has_et1t_on_pole:
            mats.extend(
                [
                    {
                        "Origem": f"Ferragem B2F em {p_id}",
                        "Código SAP": "30053140",
                        "Descrição": self.db_loader.get_sap_description("30053140"),
                        "Quantidade": 1,
                    },
                    {
                        "Origem": f"Ferragem B2F em {p_id}",
                        "Código SAP": "30053141",
                        "Descrição": self.db_loader.get_sap_description("30053141"),
                        "Quantidade": 3,
                    },
                    {
                        "Origem": f"Estrutura B2F em {p_id}",
                        "Código SAP": "30058120",
                        "Descrição": self.db_loader.get_sap_description("30058120"),
                        "Quantidade": 3,
                    },
                    {
                        "Origem": f"Estrutura B2F em {p_id}",
                        "Código SAP": "30058097",
                        "Descrição": self.db_loader.get_sap_description("30058097"),
                        "Quantidade": 3,
                    },
                ]
            )

        return mats

    def _sum_materials_by_sap(self, rows):
        totals = {}
        for row in rows or []:
            sap = str(row.get("Código SAP", "") or "").strip()
            if not sap or sap.upper().startswith("VERIFICAR"):
                continue
            try:
                qty = float(row.get("Quantidade", 0) or 0)
            except (TypeError, ValueError):
                qty = 0.0
            totals[sap] = totals.get(sap, 0.0) + qty
        return totals

    def audit_structure_coverage(self, pole_map, cables_list=None):
        """
        Auditoria generalista: valida se cada estrutura lida está refletida no cálculo
        com os mesmos materiais/quantidades da composição técnica (SQLite).
        """
        report = {
            "ok": True,
            "total_structures": 0,
            "mismatch_count": 0,
            "poles": [],
        }

        if not pole_map:
            return report

        if not (self.db_loader and self.is_loaded):
            report["ok"] = False
            report["mismatch_count"] = 1
            report["poles"].append(
                {
                    "pole_id": "GLOBAL",
                    "ok": False,
                    "details": [
                        {
                            "structure": "N/A",
                            "ok": False,
                            "reason": "database_not_loaded",
                            "missing": [],
                        }
                    ],
                }
            )
            return report

        if cables_list:
            self._prime_detected_cables(cables_list)
        if not self.selected_smtr_structure:
            self.selected_smtr_structure = self._detect_smtr_variant(cables_list)

        smtr_seen = False

        for p_id, data in sorted((pole_map or {}).items(), key=lambda kv: kv[0]):
            pole_type = self._normalize_pole_type(data.get("Pole", "Desconhecido"))
            ests = list(data.get("Est", []) or [])
            self.current_trafo_context = self._infer_trafo_context(pole_map, p_id)
            self.current_estai_context = data.get("Estai")
            expanded = self._expand_composite_structures(ests)
            pole_details = []
            pole_ok = True

            for est in expanded:
                est_up = str(est or "").upper().strip()
                if not est_up or "(E)" in est_up or "(R)" in est_up:
                    continue

                # Regra global já aplicada no cálculo principal:
                # SMTR é processada apenas uma vez por projeto.
                if est_up == "SMTR":
                    if smtr_seen:
                        continue
                    smtr_seen = True

                report["total_structures"] += 1

                canonical, _ = self._resolve_structure_code(
                    est_up,
                    pole_type,
                    trafo_desc=data.get("Trafo", ""),
                    estai_value=data.get("Estai"),
                )

                expected_rows = self.db_loader.explode_structure(
                    canonical, pole_type_str=pole_type
                )

                # Para categorias com clamp_logic, itens de cinta/bracadeira da
                # estrutura-base são substituídos por lógica dinâmica de poste.
                # Portanto, não devem gerar falso positivo na auditoria.
                est_cat = self._get_est_category(est_up)
                lookup_key = self._resolve_clamp_lookup(pole_type, est_cat)
                has_clamp_logic = bool(lookup_key and lookup_key in self.clamp_logic)
                p_type_norm = str(pole_type or "").upper().replace(" ", "")
                is_dt_pole = p_type_norm.startswith("DT") or p_type_norm.startswith("D")

                # Esperado: cálculo da estrutura isolada aplicando as MESMAS regras
                # generalistas do motor (cintas dinâmicas, filtros e fallbacks).
                isolated_rows = self.resolve_clamps(
                    pole_type,
                    [est_up],
                    p_id=f"{p_id}__AUDIT",
                )
                isolated_rows = [
                    r
                    for r in isolated_rows
                    if not str(r.get("Origem", "")).startswith("Poste ")
                ]
                actual_by_sap = self._sum_materials_by_sap(isolated_rows)

                expected_by_sap = {}
                valid_expected_count = 0
                verificar_expected_count = 0
                for m in expected_rows or []:
                    code = str(m.get("code", "") or "").strip()
                    desc = str(m.get("desc", "") or "")
                    try:
                        qty = float(m.get("qty", 0) or 0)
                    except (TypeError, ValueError):
                        qty = 0.0

                    desc_up = desc.upper()
                    is_cinta_bracadeira = (
                        "CINTA" in desc_up
                        or "BRAÇADEIRA" in desc_up
                        or "BRACADEIRA" in desc_up
                    ) and "ALÇA" not in desc_up

                    if is_cinta_bracadeira and (has_clamp_logic or is_dt_pole):
                        continue

                    if not code or code.upper().startswith("VERIFICAR"):
                        verificar_expected_count += 1
                        continue

                    valid_expected_count += 1
                    expected_by_sap[code] = expected_by_sap.get(code, 0.0) + qty

                unresolved_expected = (
                    valid_expected_count == 0 and verificar_expected_count > 0
                )
                contextual_without_trafo = (
                    est_up in {"ET1BR", "ET1T", "ET4", "ET4A"}
                    and not str(data.get("Trafo", "") or "").strip()
                    and canonical == est_up
                    and unresolved_expected
                )

                missing = []
                for sap, expected_qty in expected_by_sap.items():
                    actual_qty = float(actual_by_sap.get(sap, 0.0) or 0.0)
                    if actual_qty + 1e-9 < expected_qty:
                        missing.append(
                            {
                                "sap": sap,
                                "expected": round(expected_qty, 3),
                                "actual": round(actual_qty, 3),
                                "shortfall": round(expected_qty - actual_qty, 3),
                            }
                        )

                detail_ok = (not missing) and (
                    (not unresolved_expected) or contextual_without_trafo
                )
                if not detail_ok:
                    pole_ok = False
                    report["mismatch_count"] += 1

                pole_details.append(
                    {
                        "structure": est_up,
                        "canonical": canonical,
                        "ok": detail_ok,
                        "reason": ""
                        if detail_ok
                        else (
                            "unresolved_expected_structure"
                            if unresolved_expected
                            else "quantity_mismatch"
                        ),
                        "context_missing": contextual_without_trafo,
                        "missing": missing,
                    }
                )

            if not pole_ok:
                report["ok"] = False

            report["poles"].append(
                {
                    "pole_id": p_id,
                    "pole_type": pole_type,
                    "ok": pole_ok,
                    "details": pole_details,
                }
            )

        return report

    def resolve_cables_direct(self, cables):
        """Resolve cabos diretamente no CALC por descrição"""
        mats = []

        for cabo in cables:
            desc = cabo.get("Desc", "")
            if "(E)" in desc:
                continue
            qtd = cabo.get("Qtd", 0)
            tipo = cabo.get("Tipo", "")
            desc_up = str(desc).upper()

            if tipo in self.detected_cables and not self.detected_cables[tipo]:
                self.detected_cables[tipo] = desc
            # [FIX C4] import re removido

            termos_busca = ["CABO"]

            if tipo == "BT":
                termos_busca.append("AL")
                if "120" in desc:
                    termos_busca.append("120MM2")
                elif "70" in desc:
                    termos_busca.append("70MM2")
                elif "35" in desc:
                    termos_busca.append("35MM2")

            elif tipo == "MT":
                termos_busca.append("MT")
                if "ANA" in desc.upper():
                    termos_busca.append("ALUMINIO")

            if len(termos_busca) == 1:
                numeros = re.findall(r"\d+", desc)
                if numeros:
                    termos_busca.append(numeros[-1])

            if self.db_loader:
                # Regra determinística para cabo MT 3X2ANA(4ANA):
                #  - 1 via de 4AWG ROSE (mesma metragem do trecho)
                #  - 3 vias de 2AWG SPARROW (3 x metragem do trecho)
                if tipo == "MT" and ("2ANA" in desc_up or "4ANA" in desc_up or "2AN" in desc_up or "4AN" in desc_up):
                    mats.append(
                        {
                            "Origem": f"Cabo {tipo}",
                            "Código SAP": "10050897",
                            "Descrição": self.db_loader.get_sap_description("10050897")
                            or "CABO NU ALUMINIO 4AWG 7F ROSE",
                            "Quantidade": qtd,
                            "Confiança": 0.98,
                        }
                    )
                    mats.append(
                        {
                            "Origem": f"Cabo {tipo}",
                            "Código SAP": "10050898",
                            "Descrição": self.db_loader.get_sap_description("10050898")
                            or "CABO NU CAA AL 2AWG SPARROW",
                            "Quantidade": qtd * 3,
                            "Confiança": 0.98,
                        }
                    )
                    continue

                exclude_terms = [
                    "EMENDA",
                    "TERMINAL",
                    "CONECTOR",
                    "LUVA",
                    "SELA",
                    "PRENSA",
                    "AMORTECEDOR",
                    "GRAMPO",
                ]
                results = self.db_loader.find_material_by_description(
                    termos_busca, limit=1, exclude_terms=exclude_terms
                )

                if results:
                    code, desc_found, score = results[0]
                    mats.append(
                        {
                            "Origem": f"Cabo {tipo}",
                            "Código SAP": code,
                            "Descrição": desc_found,
                            "Quantidade": qtd,
                            "Confiança": self._confidence_from_score(score),
                        }
                    )
                else:
                    mats.append(
                        {
                            "Origem": f"Cabo {tipo}",
                            "Código SAP": "VERIFICAR",
                            "Descrição": desc,
                            "Quantidade": qtd,
                            "Confiança": 0.2,
                        }
                    )
            else:
                mats.append(
                    {
                        "Origem": f"Cabo {tipo}",
                        "Código SAP": "VERIFICAR",
                        "Descrição": desc,
                        "Quantidade": qtd,
                        "Confiança": 0.2,
                    }
                )

        return mats

    # [FIX B2] resolve_poles_direct() REMOVIDO — funcionalidade idêntica a get_pole_sap()

    def resolve_transformers_direct(self, transformers, voltage_class: str = "HV"):
        """Resolve transformadores diretamente no CALC"""
        mats = []

        for transf in transformers:
            t_type = str(transf).upper()

            termos_busca = ["TRAFO"]

            if "MONO" in t_type:
                termos_busca.extend(["MONOF", "1F"])
                is_kv_explicit = any(v in t_type for v in ["20,3", "20.3", "34,5", "34.5", "345"])
                is_hv_explicit = any(v in t_type for v in ["7,96", "7.96", "13,8", "13.8", "HV"])
                if is_kv_explicit:
                    termos_busca.append("KV")
                elif is_hv_explicit:
                    termos_busca.append("HV")
                else:
                    if voltage_class == "HV":
                        termos_busca.append("HV")
                    else:
                        termos_busca.append("KV")
            elif "TRI" in t_type:
                termos_busca.extend(["TRIF", "3F"])

            # [FIX C4] import re removido
            nums = re.findall(r"(\d+\.?\d*)", t_type)
            if nums:
                potencia = nums[0]
                termos_busca.append(f"{potencia}KVA")

            if self.db_loader:
                exclude_terms = [
                    "SUCATA",
                    "BUCHA",
                    "PROTECAO",
                    "SUPORTE",
                    "RELIG",
                    "CHAVE",
                ]
                results = self.db_loader.find_material_by_description(
                    termos_busca, limit=1, exclude_terms=exclude_terms
                )

                if not results:
                    termos_alt = [
                        t if t != "TRAFO" else "TRANSFORMADOR" for t in termos_busca
                    ]
                    results = self.db_loader.find_material_by_description(
                        termos_alt, limit=1
                    )

                if results:
                    code, desc, score = results[0]
                    mats.append(
                        {
                            "Origem": "Transformador",
                            "Código SAP": code,
                            "Descrição": desc,
                            "Quantidade": 1,
                            "Confiança": self._confidence_from_score(score),
                        }
                    )
                else:
                    mats.append(
                        {
                            "Origem": "Transformador",
                            "Código SAP": "VERIFICAR",
                            "Descrição": f"TRAFO {t_type}",
                            "Quantidade": 1,
                            "Confiança": 0.2,
                        }
                    )
            else:
                mats.append(
                    {
                        "Origem": "Transformador",
                        "Código SAP": "VERIFICAR",
                        "Descrição": f"TRAFO {t_type}",
                        "Quantidade": 1,
                        "Confiança": 0.2,
                    }
                )

        return mats

    def resolve_ramal_direct(self, ramal_desc):
        """Busca o código SAP do ramal de ligação pela descrição"""
        if not ramal_desc or not self.db_loader:
            return "VERIFICAR", ramal_desc

        desc_upper = ramal_desc.upper()
        termos = ["CABO"]

        if "MULT" in desc_upper:
            termos.append("MULT")
        if "CONCENTRICO" in desc_upper:
            termos.append("CONCENTRICO")

        # [FIX C4] import re removido
        nums = re.findall(r"\b(\d{2,3})\b", desc_upper)
        if nums:
            termos_completos = termos + [f"{nums[0]}MM2"]
            results = self.db_loader.find_material_by_description(
                termos_completos, limit=1
            )
            if results:
                return results[0][0], results[0][1]

            termos.append(nums[0])

        results = self.db_loader.find_material_by_description(termos, limit=5)
        if results:
            for code, desc, score in results:
                if "MED " not in desc.upper() and "MEDIDOR" not in desc.upper():
                    return code, desc

            return results[0][0], results[0][1]

        return "VERIFICAR", ramal_desc

    # [FIX C2, C3, M3] explode_structures() REMOVIDO
    # Este método era código legado que tentava ler arquivos inexistentes (CALC rev1 - Copia.xlsx)
    # e continha variáveis fora de escopo (calc_rows). Toda a lógica migrou para
    # process_form_data() + resolve_clamps() usando o DatabaseLoader/SQLite.

    def process_form_data(self, pole_map, cables_list=None):
        """
        Processa os dados vindos do Grid do novo app.py
        pole_map: {'P1': {'Pole': ..., 'Est': [], 'Trafo': ..., 'Chave': ..., 'Estai': 2, ...}}
        """
        self.audit_log = []
        results = []
        smtr_applied = False
        self.detected_cables = {"MT": None, "BT": None}
        self._prime_detected_cables(cables_list)
        self.selected_smtr_structure = self._detect_smtr_variant(cables_list)

        # Detecção de classe de tensão (HV vs KV) do projeto
        project_voltage_class = "HV"
        for p_id, data in (pole_map or {}).items():
            t_val = str(data.get("Trafo") or "").upper()
            if "20,3" in t_val or "34,5" in t_val or "34.5" in t_val or "20.3" in t_val or " KV" in t_val:
                project_voltage_class = "KV"
                break
            p_type = data.get("Pole", "")
            ests = list(data.get("Est", []) or [])
            for est in ests:
                resolved_est, _ = self._resolve_structure_code(est, pole_type=p_type, trafo_desc=data.get("Trafo", ""))
                if resolved_est:
                    resolved_est_up = resolved_est.upper()
                    if "20,3KV" in resolved_est_up or "34,5KV" in resolved_est_up or resolved_est_up.endswith(" KV") or " KV " in resolved_est_up:
                        project_voltage_class = "KV"
                        break
            if project_voltage_class == "KV":
                break

        # 0. Pré-normalização de tipologia e fallback para postes "Desconhecido"
        # usando o tipo dominante já identificado no mesmo projeto.
        normalized_types = {}
        known_types = []
        for p_id, data in pole_map.items():
            p_norm = self._normalize_pole_type(data.get("Pole", "Desconhecido"))
            normalized_types[p_id] = p_norm
            if p_norm and p_norm != "DESCONHECIDO":
                known_types.append(p_norm)

        # Regra determinística: não inferir tipologia por "tipo dominante".
        # Quando o extrator não identificar o poste, manter DESCONHECIDO para
        # expor erro de extração em vez de mascarar com heurística.

        for p_id, data in pole_map.items():
            # 1. Poste e Estruturas
            pole_type = normalized_types.get(
                p_id, self._normalize_pole_type(data.get("Pole", "Desconhecido"))
            )
            ests = list(data.get("Est", []) or [])
            self.current_trafo_context = self._infer_trafo_context(pole_map, p_id)
            self.current_estai_context = data.get("Estai")
            if any(str(e).upper().strip() == "SMTR" for e in ests):
                if smtr_applied:
                    ests = [e for e in ests if str(e).upper().strip() != "SMTR"]
                else:
                    smtr_applied = True
            clamp_mats = self.resolve_clamps(pole_type, ests, p_id=p_id)
            results.extend(clamp_mats)
            estf_codes = [
                str(c or "").upper().strip()
                for c in (data.get("EstfCodes", []) or [])
                if str(c or "").strip()
            ]
            et_codes = [
                str(c or "").upper().strip()
                for c in (data.get("EtCodes", []) or [])
                if str(c or "").strip()
            ]
            # Regra operacional:
            # - ET+6 => trafo novo (prioritário)
            # - ESTF+6 => trafo existente quando não houver ET.
            trafo_new_by_code = bool(et_codes)
            trafo_existing_by_code = bool(estf_codes) and not trafo_new_by_code

            # 2. Transformador
            if data.get("Trafo") and data["Trafo"] != "None":
                # [FIX A2] Corrigido: era `continue` que pulava TODO o poste.
                # Agora apenas ignora o transformador existente sem afetar outros itens.
                # Regra operacional generalista:
                # - trafo existente: bloquear apenas itens de equipamento novo
                #   (trafo e chave nova), mantendo demais componentes aplicáveis.
                # - trafo novo: fluxo completo normal.
                if "(E)" not in str(data["Trafo"]) and not trafo_existing_by_code:
                    t_val = str(data["Trafo"]).upper()

                    # A. Incluir o Equipamento Transformador em si
                    transf_mats = self.resolve_transformers_direct([t_val], voltage_class=project_voltage_class)
                    if not trafo_new_by_code:
                        transf_mats = [
                            tm
                            for tm in transf_mats
                            if str(tm.get("Código SAP", "")).strip()
                            not in {"10000173", "30053053"}
                        ]
                    for tm in transf_mats:
                        tm["Origem"] = f"Trafo {p_id}"
                        results.append(tm)

                    # B. Incluir o Kit de Hardware (Acessórios)
                    kit_key = None
                    if "MONO" in t_val:
                        kit_key = "TRAFO_MONO"
                    else:
                        kit_key = "TRAFO_TRI_45"

                    if kit_key and self.db_loader and self.db_loader.unified_db:
                        # Evita dupla contagem: ET4/ET4A já contempla ferragens e
                        # conexões que se sobrepõem ao kit padrão de trafo mono.
                        est_norm = {
                            self._resolve_structure_code(
                                str(e).upper().strip(), pole_type
                            )[0]
                            for e in data.get("Est", [])
                        }
                        skip_hw_kit = bool(est_norm.intersection({"ET4", "ET4A"}))
                        if not skip_hw_kit:
                            kit_mats = self.db_loader.unified_db.get(
                                "hardware_kits", {}
                            ).get(kit_key, [])
                            for m in kit_mats:
                                results.append(
                                    {
                                        "Origem": f"Hardware Trafo {p_id}",
                                        "Código SAP": m["sap"],
                                        "Descrição": m["desc"],
                                        "Quantidade": m["qty"],
                                    }
                                )

                        # Injetar Suporte de Trafo para Postes Circulares
                        if "C" in str(pole_type).upper():
                            results.append(
                                {
                                    "Origem": f"Suporte Trafo {p_id}",
                                    "Código SAP": TRAFO_SUPPORT_TRI,
                                    "Descrição": self.db_loader.get_sap_description(
                                        TRAFO_SUPPORT_TRI
                                    ),
                                    "Quantidade": 1,
                                }
                            )
            # D. Adesivos de identificação:
            # Regra final: carregar películas sempre que houver ET+6,
            # mesmo se Trafo vier vazio na extração.
            id_codes = et_codes if trafo_new_by_code else []
            for id_code in id_codes:
                code_txt = str(id_code or "").upper().strip()
                if not code_txt:
                    continue
                tokens = ["E", "T"]
                tokens.extend(re.findall(r"(\d)", code_txt))
                missing_tokens = set()
                for tk in tokens:
                    sap_sticker = ESTF_STICKER_MAP.get(tk)
                    if not sap_sticker:
                        missing_tokens.add(tk)
                        continue
                    results.append(
                        {
                            "Origem": f"Identificacao Trafo {p_id} ({code_txt})",
                            "Código SAP": sap_sticker,
                            "Descrição": self.db_loader.get_sap_description(
                                sap_sticker
                            ),
                            "Quantidade": 1,
                            "Confiança": 0.99,
                        }
                    )
                if missing_tokens:
                    self.audit_log.append(
                        {
                            "type": "ESTF sem mapeamento de adesivo",
                            "item": code_txt,
                            "source": f"Poste {p_id}",
                            "severity": "Media",
                            "missing_tokens": sorted(missing_tokens),
                        }
                    )

            # 3. Chave (resolução determinística + fallback controlado)
            if data.get("Chave"):
                chave_desc = f"CHAVE {data['Chave']}"
                chave_sap = "VERIFICAR"
                chave_conf = 0.2

                # Tentar resolver pelo banco de dados
                if self.db_loader:
                    chave_upper = str(data["Chave"]).upper()
                    termos = ["CHAVE"]
                    if "FUSIVEL" in chave_upper:
                        termos.extend(["FUSIVEL", "DISTRIBUICAO"])
                    elif "FACA" in chave_upper:
                        termos.extend(["FACA", "SECCIONADORA"])
                    elif "SECC" in chave_upper:
                        termos.extend(["SECCIONADORA"])
                    elif "RELIG" in chave_upper:
                        termos.extend(["RELIGADOR"])

                    exclude_terms = ["SUPORTE", "BASE", "PARAFUSO", "CONECTOR", "CABO"]
                    results_chave = self.db_loader.find_material_by_description(
                        termos,
                        limit=3,
                        exclude_terms=exclude_terms,
                    )
                    if results_chave:
                        best = results_chave[0]
                        chave_sap = best[0]
                        chave_desc = best[1]
                        chave_conf = self._confidence_from_score(best[2])

                results.append(
                    {
                        "Origem": f"Chave {p_id}",
                        "Código SAP": chave_sap,
                        "Descrição": chave_desc,
                        "Quantidade": 1,
                        "Confiança": chave_conf,
                    }
                )

            # 4. Estai
            val_estai = data.get("Estai")
            qtd_estai = 0
            tipo_estai = ""

            if isinstance(val_estai, dict):
                qtd_estai = int(val_estai.get("Qtd", 0))
                tipo_estai = val_estai.get("Type", "")
            elif val_estai is not None:
                try:
                    qtd_estai = int(val_estai)
                except (ValueError, TypeError):
                    qtd_estai = 0

            if qtd_estai > 0:
                is_ret = "(R)" in str(tipo_estai)
                t_clean = str(tipo_estai).replace("(R)", "").strip()
                suffix = " (RETIRADA)" if is_ret else ""

                desc_extra = f" - {t_clean}" if t_clean else ""
                estai_struct = "ESTAI"
                if "28" in t_clean:
                    estai_struct = "28M"
                elif "14" in t_clean:
                    estai_struct = "14M"

                estai_mats = []
                if self.db_loader and self.is_loaded:
                    estai_mats = self.db_loader.explode_structure(
                        estai_struct, pole_type_str=pole_type
                    )
                    if not estai_mats and estai_struct != "14M":
                        estai_mats = self.db_loader.explode_structure(
                            "14M", pole_type_str=pole_type
                        )

                if estai_mats:
                    for em in estai_mats:
                        results.append(
                            {
                                "Origem": f"Estai {p_id}",
                                "Código SAP": em.get("code", "VERIFICAR"),
                                "Descrição": f"{em.get('desc', 'ITEM ESTAI')}{desc_extra}{suffix}",
                                "Quantidade": float(em.get("qty", 0) or 0) * qtd_estai,
                            }
                        )
                else:
                    # Fallback seguro caso catálogo esteja indisponível.
                    results.append(
                        {
                            "Origem": f"Estai {p_id}",
                            "Código SAP": "30056363",
                            "Descrição": f"HASTE ANCOR AC 1020 3200DAN 16MM 1,6M{desc_extra}{suffix}",
                            "Quantidade": qtd_estai,
                        }
                    )
                    results.append(
                        {
                            "Origem": f"Estai {p_id}",
                            "Código SAP": "30054507",
                            "Descrição": f"CORDOALHA ACO CARB 9,5MM 7F CL.B MR/SM{suffix}",
                            "Quantidade": qtd_estai * 10,
                        }
                    )

            # 5. Aterramento
            val_aterr = data.get("Aterramento")
            qtd_aterr = 0
            if isinstance(val_aterr, dict):
                qtd_aterr = int(val_aterr.get("Qtd", 0))
            elif val_aterr is not None:
                try:
                    qtd_aterr = int(val_aterr)
                except (ValueError, TypeError):
                    qtd_aterr = 0

            if qtd_aterr > 0:
                results.append(
                    {
                        "Origem": f"Aterramento {p_id}",
                        "Código SAP": "30056366",
                        "Descrição": "HASTE AT SIM AC 1020 COBR 5/8POL 2,4M",
                        "Quantidade": qtd_aterr,
                    }
                )

            # 6. Para-Raio (resolução determinística + fallback controlado)
            val_pr = data.get("ParaRaio")
            qtd_pr = 0
            tipo_pr = ""
            if isinstance(val_pr, dict):
                qtd_pr = int(val_pr.get("Qtd", 0))
                tipo_pr = val_pr.get("Type", "")
            elif val_pr is not None:
                try:
                    qtd_pr = int(val_pr)
                except (ValueError, TypeError):
                    qtd_pr = 0

            if qtd_pr > 0:
                is_ret = "(R)" in str(tipo_pr)
                t_clean = str(tipo_pr).replace("(R)", "").strip()
                suffix = " (RETIRADA)" if is_ret else ""

                # Tentar resolver pelo banco de dados
                sap_pr = "VERIFICAR"
                desc_pr = f"CONJUNTO PARA-RAIO - {t_clean}{suffix}"
                conf_pr = 0.2

                if self.db_loader:
                    termos_pr = ["PARA-RAIO", "POLIMERICO", "DISTRIBUICAO"]
                    if "CRUZETA" in t_clean.upper():
                        termos_pr.append("CRUZETA")
                    if "ESTACAO" in t_clean.upper():
                        termos_pr.append("ESTACAO")

                    exclude_pr = ["SUPORTE", "PARAFUSO", "ARRUELA", "CABO", "CONECTOR"]
                    results_pr = self.db_loader.find_material_by_description(
                        termos_pr,
                        limit=3,
                        exclude_terms=exclude_pr,
                    )
                    if results_pr:
                        best = results_pr[0]
                        sap_pr = best[0]
                        desc_pr = best[1] + suffix
                        conf_pr = self._confidence_from_score(best[2])

                results.append(
                    {
                        "Origem": f"Para-Raio {p_id}",
                        "Código SAP": sap_pr,
                        "Descrição": desc_pr,
                        "Quantidade": qtd_pr,
                        "Confiança": conf_pr,
                    }
                )

            # 7. Ramal
            val_ramal = data.get("Ramal", {})
            if isinstance(val_ramal, dict):
                qtd_ramal = float(val_ramal.get("Qtd", 0))
                tipo_ramal = val_ramal.get("Type", "")

                if qtd_ramal > 0 and tipo_ramal:
                    code, desc = self.resolve_ramal_direct(tipo_ramal)
                    results.append(
                        {
                            "Origem": f"Ramal {p_id}",
                            "Código SAP": code,
                            "Descrição": desc,
                            "Quantidade": qtd_ramal,
                        }
                    )

        # Ajuste fino orientado por validação especialista para perfil ET4-U3-S3.
        # Agregação Final
        results = self.aggregate_materials(results)
        return results

    def aggregate_materials(self, materials_list):
        """Agrega materiais por Código SAP, somando quantidades e unindo origens."""

        def _clean_qty(value):
            try:
                q = float(value)
            except (TypeError, ValueError):
                return 0
            if abs(q) < 1e-9:
                return 0
            if abs(q - round(q)) < 1e-9:
                return int(round(q))
            return round(q, 3)

        aggregated = {}
        for mat in materials_list:
            mat = self._ensure_confidence(mat)
            mat = self._apply_manual_correction(mat)
            sap = str(mat["Código SAP"])

            # FILTRO DE SEGURANÇA: Remover materiais desativados (Série 9)
            if sap.startswith("9"):
                continue

            key = (
                sap
                if sap != "VERIFICAR" and sap is not None
                else f"VERIFICAR-{mat['Descrição']}"
            )

            if key in aggregated:
                aggregated[key]["Quantidade"] += mat["Quantidade"]
                aggregated[key]["Confiança"] = min(
                    float(aggregated[key].get("Confiança", 1.0)),
                    float(mat.get("Confiança", 1.0)),
                )
                current_orig = aggregated[key]["Origem"]
                new_orig = mat["Origem"]
                if len(current_orig) < 150 and new_orig not in current_orig:
                    aggregated[key]["Origem"] += f", {new_orig}"
            else:
                aggregated[key] = mat.copy()

        out = list(aggregated.values())
        filtered = []
        for item in out:
            item["Quantidade"] = _clean_qty(item.get("Quantidade", 0))
            try:
                qty = float(item["Quantidade"])
            except (TypeError, ValueError):
                qty = 0.0
            if qty > 0:
                filtered.append(item)
        return filtered

    def process_cables(self, cables_list):
        """
        Processa a lista de cabos extraídos e busca seus códigos SAP.
        cables_list: [{'Tipo': 'BT', 'Desc': '1x3x120(70)', 'Qtd': 24.2}, ...]
        """
        return self.resolve_cables_direct(cables_list)
