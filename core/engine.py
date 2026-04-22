"""
=== PROPOSTA DE ALTERAÇÃO - engine.py ===
Corrige: C2, C3, C4, A1, A2, A3, A4, M3, B2
Veja: RELATORIO_INCONSISTENCIAS.md para detalhes
"""
import pandas as pd
import re
import os
import json

# Caminhos padrão (Relativos ao diretório do script)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KITS_PATH = os.path.join(BASE_DIR, 'Biblioteca_Kits', 'Biblioteca de Kits', 'Materiais dos Kits Construtivos 19-06-2023.xlsx')
SAP_PATH = os.path.join(BASE_DIR, 'Codigos de Materiais Novos.xlsx')
# [FIX C2] REMOVIDO: CALC_PATH apontava para arquivo inexistente 'CALC rev1 - Copia.xlsx'

# SQLite Database Loader (substitui JSON/Pickle)
try:
    from .database_sqlite import SQLiteDatabaseLoader as DatabaseLoader  # type: ignore
except ImportError:
    try:
        from database_sqlite import SQLiteDatabaseLoader as DatabaseLoader
    except ImportError:
        from database_loader import DatabaseLoader

# Mapeamento de Diâmetros para Códigos SAP de Cintas
CINTA_SAP_MAP = {
    100: "30053132", 140: "30053133", 160: "30053134", 180: "30053136",
    200: "30053137", 220: "30053138", 230: "30053139", 240: "30053140",
    260: "30053141", 280: "30053143", 290: "30053144", 300: "30053145",
    320: "30053146", 340: "30053148", 360: "30053149", 380: "30053150"
}

# Mapeamento de Bitolas para Códigos SAP de Alças MT (Alumínio Nu)
ALCA_MT_NU_MAP = {
    '4ANA': '30050155', '2ANA': '30050152', '1/0ANA': '30050150',
    '2/0ANA': '30050151', '3/0ANA': '30050153', '4/0ANA': '30050154',
    '336': '30050149'
}

# Alças para Cabos Protegidos MT
ALCA_MT_PROT_MAP = {
    '35': '10000994', '50': '10000995', '70': '10004273', '150': '30050157', '185': '30050159'
}

# Mapeamento Manual de Estruturas sem DB
MANUAL_EST_MAP = {
    'BR1579': [('30053140', 1), ('30053137', 1)],
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
    # S3/S4 são abreviações de 1S3/1S4 (Norma Enel/CPFL)
    'S3':     '1S3',
    'S4':     '1S4',
    'S3(1)':  '1S3',
    'S4(1)':  '1S4',
    '1S3(1)': '1S3',
    '1S4(1)': '1S4',
    '2S3':    '1S3',   # prefixo numérico de quantidade, não de tipo
    '2S4':    '1S4',

    # ── Hastes de aterramento ─────────────────────────────────────────────────
    # H3/H5 = Haste 5/8" (Catálogo CPFL)
    'H5':   '1HASTE',
    'H3':   '1HASTE',
    'H1':   '1HASTE',
    'HASTE':'1HASTE',

    # ── Estruturas N (neutro/passagem) — variações regionais ─────────────────
    'N1F':  'N1',
    'N2F':  'N2',
    'N3F':  'N3',
    'N4F':  'N4',
    'N5F':  'N5',
    'N1A':  'N1',
    'N2A':  'N2',

    # ── Estruturas B (bifurcação/derivação) ──────────────────────────────────
    'B1F':  'B1',
    'B2F':  'B2',
    'B3F':  'B3',
    'B4F':  'B4',

    # ── Estruturas ET (entroncamento) ─────────────────────────────────────────
    'ET1':  'ET1T',
    'ET2':  'ET2T',
    'ET3':  'ET3T',
    'ET4':  'ET4A',

    # ── Estruturas U (ultima) ─────────────────────────────────────────────────
    'U1F':  'U1',
    'U2F':  'U2',
    'U3F':  'U3',
    'U4F':  'U4',

    # ── Estruturas M (montagem especial / medição) ────────────────────────────
    'M1F':  'M1',
    'M2F':  'M2',

    # ── Abreviações de estai ──────────────────────────────────────────────────
    'EST':   'ESTAI',
    'ESTAI1':'ESTAI',

    # ── Outros aliases comuns de campo ───────────────────────────────────────
    # Adicionar novos aliases aqui conforme novos projetos forem testados.
    # Formato: 'ALIAS_NO_PDF': 'CODIGO_NO_BANCO'
    # Sempre documentar: alias → destino — fonte/norma.
}

# Ferragens de Fixação para Cintas (Poste Circular)
FASTENER_BOLT = "30058226"   # PARAFUSO CAB QUAD 16MM 125MM AC
FASTENER_WASHER = "30050463" # ARRUELA LISA QUAD AC 16MM 38MM
CROSSARM_STD = "30054575"    # CRUZETA P/POSTE AC 1010/20 2,4M
TRAFO_SUPPORT_TRI = "30060418" # SUPORTE TRANSF ACO POST CON CIR 210MM


class MaterialEngine:
    def __init__(self):
        self.desc_to_sap = {} 
        # [FIX M3] Removidos: self.df_kits e self.df_sap (nunca populados, código legado morto)
        self.depara = {}
        self.is_loaded = False
        
        # Database Loader
        self.db_loader = None
        self.detected_cables = {'MT': None, 'BT': None}
        self.audit_log = []
        self.manual_corrections_path = os.path.join(BASE_DIR, "manual_corrections.json")
        self.manual_corrections = self._load_manual_corrections()
        
        # [FIX A1] Mapeamento de Cintas ampliado com postes faltantes
        self.clamp_logic = {
            # Poste 12m 1000daN
            ('C12/1000', 'N'): [('30053140', 2)],
            ('C12/1000', 'B'): [('30053140', 1), ('30053141', 1)],
            ('C12/1000', 'U'): [('30053140', 2)],
            ('C12/1000', 'S'): [('30053143', 1)],
            
            # Poste 12m 600daN
            ('C12/600', 'N'): [('30053137', 2)],
            ('C12/600', 'B'): [('30053137', 1), ('30053138', 1)],
            ('C12/600', 'U'): [('30053137', 2)], 
            ('C12/600', 'S'): [('30053140', 1)],
            
            # Poste 12m 400daN (NOVO - Faltava)
            ('C12/400', 'N'): [('30053136', 2)],
            ('C12/400', 'B'): [('30053136', 1), ('30053137', 1)],
            ('C12/400', 'U'): [('30053136', 2)],
            ('C12/400', 'S'): [('30053139', 1)],
            
            # Poste 12m 300daN
            ('C12/300', 'N'): [('30053136', 2)],
            ('C12/300', 'B'): [('30053136', 1), ('30053137', 1)],
            ('C12/300', 'U'): [('30053136', 2)], 
            ('C12/300', 'S'): [('30053138', 1)],
            
            # Poste 11m 1000daN (NOVO - Faltava)
            ('C11/1000', 'N'): [('30053140', 2)],
            ('C11/1000', 'B'): [('30053140', 1), ('30053141', 1)],
            ('C11/1000', 'U'): [('30053140', 2)],
            ('C11/1000', 'S'): [('30053143', 1)],
            
            # Poste 11m 600daN
            ('C11/600', 'N'): [('30053137', 2)], 
            ('C11/600', 'B'): [('30053137', 1), ('30053138', 1)],
            ('C11/600', 'U'): [('30053137', 2)],
            ('C11/600', 'S'): [('30053140', 1)],
            
            # Poste 11m 400daN (NOVO - Faltava)
            ('C11/400', 'N'): [('30053136', 2)],
            ('C11/400', 'B'): [('30053136', 1), ('30053137', 1)],
            ('C11/400', 'U'): [('30053136', 2)],
            ('C11/400', 'S'): [('30053138', 1)],

            ('C11/300', 'N'): [('30053136', 2)],
            ('C11/300', 'B'): [('30053136', 1), ('30053137', 1)],
            ('C11/300', 'U'): [('30053136', 2)],
            ('C11/300', 'S'): [('30053138', 1)],

            # === POSTES DUPLO T (DT / D) - Ferragens de Fixação ===
            # Postes DT não usam Cintas, usam Parafusos Passantes e Arruelas.
            # Mapeando tipos comuns encontrados nos novos diagramas.
            ('DT11/300', 'N'): [('30058234', 1), ('30050463', 2)],
            ('DT11/300', 'B'): [('30058234', 1), ('30050463', 2)],
            ('DT11/300', 'U'): [('30058234', 1), ('30050463', 2)],
            ('DT11/300', 'S'): [('30058234', 1), ('30050463', 2)],

            ('D11/300', 'N'): [('30058234', 1), ('30050463', 2)],
            ('D11/300', 'B'): [('30058234', 1), ('30050463', 2)],
            ('D11/300', 'U'): [('30058234', 1), ('30050463', 2)],
            ('D11/300', 'S'): [('30058234', 1), ('30050463', 2)],

            ('DT12/300', 'N'): [('30058234', 1), ('30050463', 2)],
            ('DT12/300', 'B'): [('30058234', 1), ('30050463', 2)],
            ('DT12/300', 'U'): [('30058234', 1), ('30050463', 2)],
            ('DT12/300', 'S'): [('30058234', 1), ('30050463', 2)],
        }

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
            with open(self.manual_corrections_path, "w", encoding="utf-8") as f:
                json.dump(self.manual_corrections, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] Falha ao salvar manual_corrections.json: {e}")

    def register_manual_correction(self, sap_code: str, description: str, source: str = "ui") -> bool:
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
        """Converte score de busca em confiança normalizada (0..1)."""
        try:
            s = float(score)
        except (ValueError, TypeError):
            return 0.85
        conf = 0.55 + (0.08 * s)
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
        termos_busca = ['POSTE']
        
        if 'C' in p_type:
            termos_busca.extend(['CIRCULAR', 'CONCR', 'CIRC'])
        elif 'DT' in p_type or 'DUPLO T' in p_type or 'D' in p_type:
            # [FIX] Usar DUPL para bater com DUPLO e DUPL (banco usa DUPL T)
            termos_busca.extend(['DUPL', 'DT'])
            if 'DT' not in termos_busca: termos_busca.append('DT')
        
        # [FIX C4] import re removido — já importado no topo do arquivo
        nums = re.findall(r'\d+', p_type)
        if len(nums) >= 2:
            h = nums[0]
            c = nums[1]
            termos_busca.append(f'{h}M')
            termos_busca.append(f'{c}DAN')
        elif len(nums) == 1:
            termos_busca.append(f'{nums[0]}M')
        
        # [FIX] Se for DT ou D, excluir termos de MADEIRA ou MAD para evitar falso positivo
        exclude_terms = ['CONEXAO', 'TOPO', 'BRACADEIRA', 'LUMINARIA', 'SUPORTE']
        if 'DT' in p_type or 'DUPLO' in p_type or ('D' in p_type and 'DAN' in p_type):
            exclude_terms.extend(['MAD', 'MADEIRA', 'EUCAL'])
        
        if self.db_loader:
            results = self.db_loader.find_material_by_description(termos_busca, limit=1, exclude_terms=exclude_terms)
            if results:
                return results[0][0], results[0][1]
                
        return "VERIFICAR", f"POSTE {pole_type}"

    def clean_code(self, val):
        try:
            if pd.isna(val) or val == "": return ""
            s = str(val).split('.')[0].strip()
            if s.isdigit(): return s
            return s
        except:
            return str(val).strip()

    def get_vivid_code(self, code, description):
        code = self.clean_code(code)
        
        if code in self.depara: 
            return self.depara[code]
        
        if code.startswith('3'): 
            return code
            
        if code.startswith('1'):
            desc_up = str(description).upper()
            if "CINTA" in desc_up or "BRAÇADEIRA" in desc_up:
                return code
            return code

        desc_clean = str(description).upper().replace('SUCATA', '').strip()
        if desc_clean in self.desc_to_sap: return self.desc_to_sap[desc_clean]
        
        words = [w for w in desc_clean.split() if len(w) > 3]
        if len(words) >= 2:
            for sap_desc, sap_code in self.desc_to_sap.items():
                if all(w in sap_desc for w in words[:2]):
                    return sap_code
        return None if code.startswith('9') else code

    def resolve_clamps(self, pole_type, structures, p_id=""):
        """Retorna as braçadeiras E materiais das estruturas baseado no poste e estruturas."""
        mats = []
        p_type = str(pole_type).upper()
        p_type_norm = p_type.replace('x', '/').replace(' ', '')
        p_id_label = p_id if p_id else p_type_norm
        
        # 1. Adicionar o próprio POSTE
        pole_str = str(pole_type).upper()
        if "(E)" not in pole_str and "(R)" not in pole_str:
            p_clean = pole_str.split('(')[0].strip()
            p_code, p_desc = self.get_pole_sap(p_clean)
            mats.append({
                'Origem': f'Poste {p_id}', 
                'Código SAP': p_code, 
                'Descrição': p_desc, 
                'Quantidade': 1
            })

        # 2. Braçadeiras e Ferragens (Somente para Novos)
        for est_raw in structures:
            est_str = str(est_raw).upper()
            if "(E)" in est_str or "(R)" in est_str: continue
            
            est = est_str.strip()
            est_cat = ''
            if est.startswith('N') or est.startswith('ET'): est_cat = 'N'
            elif est.startswith('B'): est_cat = 'B'
            elif est.startswith('U'): est_cat = 'U'
            elif 'S' in est: est_cat = 'S'
            elif est.startswith('M'): est_cat = 'N'
            
            lookup = (p_type_norm.split('(')[0], est_cat)
            if lookup in self.clamp_logic:
                for sap, qty in self.clamp_logic[lookup]:
                    desc = (self.db_loader.sap_codes.get(str(sap)) if self.db_loader else None) or f"BRACADEIRA SAP {sap}"
                    mats.append({
                        'Origem': f'Ferragem {est} em {p_id}',
                        'Código SAP': sap,
                        'Descrição': desc,
                        'Quantidade': qty
                    })
        
        # 3. Parafusos e Arruelas de fixação (Para cada cinta adicionada)
        if "CIRCULAR" in p_type_norm or " C " in p_type_norm or pole_str.startswith('C'):
            cintas_adicionadas = [m for m in mats if "CINTA" in m['Descrição'].upper() or "BRACADEIRA" in m['Descrição'].upper()]
            for cinta in cintas_adicionadas:
                mats.append({
                    'Origem': f'Fixação em {p_id}',
                    'Código SAP': FASTENER_BOLT,
                    'Descrição': self.db_loader.get_sap_description(FASTENER_BOLT) if self.db_loader else "PARAFUSO FIXACAO",
                    'Quantidade': 1 * cinta['Quantidade']
                })
                mats.append({
                    'Origem': f'Fixação em {p_id}',
                    'Código SAP': FASTENER_WASHER,
                    'Descrição': self.db_loader.get_sap_description(FASTENER_WASHER) if self.db_loader else "ARRUELA FIXACAO",
                    'Quantidade': 2 * cinta['Quantidade']
                })
        
        # 4. Explodir estruturas em materiais componentes (Somente para Novos)
        if self.db_loader and self.is_loaded:
            for est_raw in structures:
                est_str = str(est_raw).upper()
                suffix = " (RETIRADA)" if "(R)" in est_str else ""
                if "(E)" in est_str or "(R)" in est_str: continue
                
                est = est_str.strip()

                # NORMALIZAR: aplicar aliases antes de buscar no banco
                # Ex: S3 -> 1S3, H5 -> 1HASTE (ver STRUCTURE_ALIASES no topo do arquivo)
                est_canonical = STRUCTURE_ALIASES.get(est, est)
                if est_canonical != est:
                    print(f"[ALIAS] {est} -> {est_canonical} em Poste {pole_type}")

                structure_materials = self.db_loader.explode_structure(est_canonical, pole_type_str=pole_type)

                # Auditoria (Gap Analysis) — usa nome original para rastreabilidade
                if not structure_materials or (len(structure_materials) == 1 and structure_materials[0]['code'] == 'VERIFICAR'):
                    self.audit_log.append({
                        'type': 'Estrutura Nao Encontrada',
                        'item': est,
                        'item_canonical': est_canonical,
                        'source': f'Poste {pole_type}',
                        'severity': 'Alta'
                    })

                for mat in structure_materials:
                    code = mat['code']
                    desc = str(mat['desc'])
                    qty = mat['qty']
                    
                    desc_upper = desc.upper()
                    # --- LÓGICA DE CINTAS DINÂMICAS ---
                    if ("CINTA" in desc_upper or "BRAÇADEIRA" in desc_upper) and "ALÇA" not in desc_upper:
                        cat = "CINTA 1"
                        if "ESTAI" in desc_upper: cat = "ESTAI 1"
                        elif "NIVEL" in desc_upper: cat = "NIVEL 1"
                        elif "RECK" in desc_upper or "REK" in desc_upper: cat = "RECK 1"
                        elif "SECUNDARIA" in desc_upper: cat = "SECUNDARIA"
                        elif "LUMINARIA" in desc_upper: cat = "LUMINARIA"
                        
                        diameter = None
                        lookup_table = self.db_loader.unified_db.get('cinta_lookup', {}) if (self.db_loader and self.db_loader.unified_db) else {}
                        
                        p_normalized = p_type.replace('DT', '').replace('RT', '').replace('C', '').replace('/', '-').replace(' ', '').strip()
                        p_keys = [p_normalized, p_normalized.replace('-', '/'), p_type]
                        
                        for pk in p_keys:
                            if pk in lookup_table:
                                diameter = lookup_table[pk].get(cat)
                                if diameter: break
                        
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
                    
                    elif "ALÇA" in desc_upper and (code == "VERIFICAR" or code == "VERIFICAR-CABO"):
                        mt_c = self.detected_cables.get('MT')
                        if mt_c:
                            mt_c_up = mt_c.upper()
                            resolved = False
                            for bitola, sap in ALCA_MT_NU_MAP.items():
                                if bitola in mt_c_up:
                                    code = sap
                                    desc = (self.db_loader.sap_codes[sap] if self.db_loader and sap in self.db_loader.sap_codes else f"ALÇA {bitola}") + suffix
                                    resolved = True; break
                            
                            if not resolved:
                                for bitola, sap in ALCA_MT_PROT_MAP.items():
                                    if bitola in mt_c_up:
                                        code = sap
                                        desc = (self.db_loader.sap_codes[sap] if self.db_loader and sap in self.db_loader.sap_codes else f"ALÇA {bitola}") + suffix
                                        resolved = True; break
                            
                            if resolved and code != "VERIFICAR" and self.db_loader:
                                rich_desc = self.db_loader.get_sap_description(code)
                                if rich_desc: desc = rich_desc + suffix
                    
                    # Verificação Manual para Estruturas como BR1579
                    if code == "VERIFICAR" and est in MANUAL_EST_MAP:
                        for m_sap, m_qty in MANUAL_EST_MAP[est]:
                            m_desc = self.db_loader.sap_codes.get(m_sap, f"ITEM {m_sap}") if self.db_loader else m_sap
                            mats.append({
                                'Origem': f'Estrutura {est} (Manual)',
                                'Código SAP': m_sap,
                                'Descrição': m_desc + suffix,
                                'Quantidade': m_qty * qty
                            })
                        continue

                    # Correção Específica para Parafusos M16x400
                    if (code == "VERIFICAR-POSTE" or "VERIFICAR" in code) and "PARAFUSO" in desc_upper and "400" in desc_upper:
                         code = "30058241"
                         if self.db_loader and code in self.db_loader.sap_codes:
                             desc = self.db_loader.sap_codes[code] + suffix
                         else:
                             desc = f"PARAFUSO CAB QUAD 16MM 400MM AC{suffix}"

                    mats.append({
                        'Origem': f'Estrutura {est} em {p_id}',
                        'Código SAP': code,
                        'Descrição': desc,
                        'Quantidade': qty
                    })
                    
                    # INJEÇÃO: Cruzeta para estruturas de montagem
                    if est in ['B2F', 'ET1T', 'ET4A'] and CROSSARM_STD not in [m['Código SAP'] for m in mats]:
                         mats.append({
                            'Origem': f'Suporte em {p_id}',
                            'Código SAP': CROSSARM_STD,
                            'Descrição': self.db_loader.get_sap_description(CROSSARM_STD),
                            'Quantidade': 1
                        })
        
        return mats
    
    def resolve_cables_direct(self, cables):
        """Resolve cabos diretamente no CALC por descrição"""
        mats = []
        
        for cabo in cables:
            desc = cabo.get('Desc', '')
            if "(E)" in desc: continue
            qtd = cabo.get('Qtd', 0)
            tipo = cabo.get('Tipo', '')
            
            if tipo in self.detected_cables and not self.detected_cables[tipo]:
                self.detected_cables[tipo] = desc
            # [FIX C4] import re removido
            
            termos_busca = ['CABO']
            
            if tipo == 'BT':
                termos_busca.append('AL')
                if '120' in desc: termos_busca.append('120MM2')
                elif '70' in desc: termos_busca.append('70MM2')
                elif '35' in desc: termos_busca.append('35MM2')
            
            elif tipo == 'MT':
                termos_busca.append('MT')
                if 'ANA' in desc.upper():
                    termos_busca.append('ALUMINIO')
            
            if len(termos_busca) == 1:
                numeros = re.findall(r'\d+', desc)
                if numeros: termos_busca.append(numeros[-1])

            if self.db_loader:
                exclude_terms = ['EMENDA', 'TERMINAL', 'CONECTOR', 'LUVA', 'SELA', 'PRENSA', 'AMORTECEDOR', 'GRAMPO']
                results = self.db_loader.find_material_by_description(termos_busca, limit=1, exclude_terms=exclude_terms)
                
                if results:
                    code, desc_found, score = results[0]
                    mats.append({
                        'Origem': f'Cabo {tipo}',
                        'Código SAP': code,
                        'Descrição': desc_found,
                        'Quantidade': qtd,
                        'Confiança': self._confidence_from_score(score)
                    })
                else:
                    mats.append({
                        'Origem': f'Cabo {tipo}',
                        'Código SAP': 'VERIFICAR',
                        'Descrição': desc,
                        'Quantidade': qtd,
                        'Confiança': 0.2
                    })
            else:
                mats.append({
                    'Origem': f'Cabo {tipo}',
                    'Código SAP': 'VERIFICAR',
                    'Descrição': desc,
                    'Quantidade': qtd,
                    'Confiança': 0.2
                })
        
        return mats
    
    # [FIX B2] resolve_poles_direct() REMOVIDO — funcionalidade idêntica a get_pole_sap()

    def resolve_transformers_direct(self, transformers):
        """Resolve transformadores diretamente no CALC"""
        mats = []
        
        for transf in transformers:
            t_type = str(transf).upper()
            
            termos_busca = ['TRAFO']
            
            if 'MONO' in t_type:
                termos_busca.extend(['MONOF', '1F'])
            elif 'TRI' in t_type:
                termos_busca.extend(['TRIF', '3F'])
            
            # [FIX C4] import re removido
            nums = re.findall(r'(\d+\.?\d*)', t_type)
            if nums:
                potencia = nums[0]
                termos_busca.append(f'{potencia}KVA')
            
            if self.db_loader:
                exclude_terms = ['SUCATA', 'BUCHA', 'PROTECAO', 'SUPORTE', 'RELIG', 'CHAVE']
                results = self.db_loader.find_material_by_description(termos_busca, limit=1, exclude_terms=exclude_terms)
                
                if not results:
                    termos_alt = [t if t != 'TRAFO' else 'TRANSFORMADOR' for t in termos_busca]
                    results = self.db_loader.find_material_by_description(termos_alt, limit=1)

                if results:
                    code, desc, score = results[0]
                    mats.append({
                        'Origem': 'Transformador',
                        'Código SAP': code,
                        'Descrição': desc,
                        'Quantidade': 1,
                        'Confiança': self._confidence_from_score(score)
                    })
                else:
                    mats.append({
                        'Origem': 'Transformador',
                        'Código SAP': 'VERIFICAR',
                        'Descrição': f'TRAFO {t_type}',
                        'Quantidade': 1,
                        'Confiança': 0.2
                    })
            else:
                mats.append({
                    'Origem': 'Transformador',
                    'Código SAP': 'VERIFICAR',
                    'Descrição': f'TRAFO {t_type}',
                    'Quantidade': 1,
                    'Confiança': 0.2
                })
        
        return mats

    def resolve_ramal_direct(self, ramal_desc):
        """Busca o código SAP do ramal de ligação pela descrição"""
        if not ramal_desc or not self.db_loader:
            return "VERIFICAR", ramal_desc

        desc_upper = ramal_desc.upper()
        termos = ["CABO"]
        
        if "MULT" in desc_upper: termos.append("MULT")
        if "CONCENTRICO" in desc_upper: termos.append("CONCENTRICO")
        
        # [FIX C4] import re removido
        nums = re.findall(r'\b(\d{2,3})\b', desc_upper)
        if nums:
            termos_completos = termos + [f"{nums[0]}MM2"]
            results = self.db_loader.find_material_by_description(termos_completos, limit=1)
            if results: return results[0][0], results[0][1]
            
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

    def process_form_data(self, pole_map):
        """
        Processa os dados vindos do Grid do novo app.py
        pole_map: {'P1': {'Pole': ..., 'Est': [], 'Trafo': ..., 'Chave': ..., 'Estai': 2, ...}}
        """
        self.audit_log = []
        results = []
        
        for p_id, data in pole_map.items():
            # 1. Poste e Estruturas
            clamp_mats = self.resolve_clamps(data['Pole'], data['Est'], p_id=p_id)
            results.extend(clamp_mats)
            
            # 2. Transformador
            if data.get('Trafo') and data['Trafo'] != "None":
                # [FIX A2] Corrigido: era `continue` que pulava TODO o poste.
                # Agora apenas ignora o transformador existente sem afetar outros itens.
                if "(E)" not in str(data['Trafo']):
                    t_val = str(data['Trafo']).upper()
                    
                    # A. Incluir o Equipamento Transformador em si
                    transf_mats = self.resolve_transformers_direct([t_val])
                    for tm in transf_mats:
                        tm['Origem'] = f"Trafo {p_id}"
                        results.append(tm)
                    
                    # B. Incluir o Kit de Hardware (Acessórios)
                    kit_key = None
                    if "MONO" in t_val:
                        kit_key = "TRAFO_MONO"
                    else:
                        kit_key = "TRAFO_TRI_45"
                    
                    if kit_key and self.db_loader and self.db_loader.unified_db:
                        kit_mats = self.db_loader.unified_db.get('hardware_kits', {}).get(kit_key, [])
                        for m in kit_mats:
                            results.append({
                                'Origem': f"Hardware Trafo {p_id}",
                                'Código SAP': m['sap'],
                                'Descrição': m['desc'],
                                'Quantidade': m['qty']
                            })
                        
                        # Injetar Suporte de Trafo para Postes Circulares
                        if "C" in str(data['Pole']).upper():
                            results.append({
                                'Origem': f"Suporte Trafo {p_id}",
                                'Código SAP': TRAFO_SUPPORT_TRI,
                                'Descrição': self.db_loader.get_sap_description(TRAFO_SUPPORT_TRI),
                                'Quantidade': 1
                            })

            # 3. Chave (resolução determinística + fallback controlado)
            if data.get('Chave'):
                chave_desc = f"CHAVE {data['Chave']}"
                chave_sap = "VERIFICAR"
                chave_conf = 0.2
                
                # Tentar resolver pelo banco de dados
                if self.db_loader:
                    chave_upper = str(data['Chave']).upper()
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
                
                results.append({
                    'Origem': f"Chave {p_id}", 
                    'Código SAP': chave_sap, 
                    'Descrição': chave_desc, 
                    'Quantidade': 1,
                    'Confiança': chave_conf
                })
            
            # 4. Estai
            val_estai = data.get('Estai')
            qtd_estai = 0
            tipo_estai = ""
            
            if isinstance(val_estai, dict):
                qtd_estai = int(val_estai.get('Qtd', 0))
                tipo_estai = val_estai.get('Type', '')
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
                
                results.append({'Origem': f"Estai {p_id}", 'Código SAP': '30056363', 'Descrição': f'HASTE ANCOR AC 1020 3200DAN 16MM 1,6M{desc_extra}{suffix}', 'Quantidade': qtd_estai})
                results.append({'Origem': f"Estai {p_id}", 'Código SAP': '30054507', 'Descrição': f'CORDOALHA ACO CARB 9,5MM 7F CL.B MR/SM{suffix}', 'Quantidade': qtd_estai * 10})
            
            # 5. Aterramento
            val_aterr = data.get('Aterramento')
            qtd_aterr = 0
            if isinstance(val_aterr, dict):
                qtd_aterr = int(val_aterr.get('Qtd', 0))
            elif val_aterr is not None:
                try:
                    qtd_aterr = int(val_aterr)
                except (ValueError, TypeError):
                    qtd_aterr = 0
                
            if qtd_aterr > 0:
                results.append({'Origem': f"Aterramento {p_id}", 'Código SAP': '30056366', 'Descrição': 'HASTE AT SIM AC 1020 COBR 5/8POL 2,4M', 'Quantidade': qtd_aterr})
            
            # 6. Para-Raio (resolução determinística + fallback controlado)
            val_pr = data.get('ParaRaio')
            qtd_pr = 0
            tipo_pr = ""
            if isinstance(val_pr, dict):
                qtd_pr = int(val_pr.get('Qtd', 0))
                tipo_pr = val_pr.get('Type', '')
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
                sap_pr = 'VERIFICAR'
                desc_pr = f'CONJUNTO PARA-RAIO - {t_clean}{suffix}'
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
                
                results.append({
                    'Origem': f"Para-Raio {p_id}",
                    'Código SAP': sap_pr,
                    'Descrição': desc_pr,
                    'Quantidade': qtd_pr,
                    'Confiança': conf_pr
                })

            # 7. Ramal
            val_ramal = data.get('Ramal', {})
            if isinstance(val_ramal, dict):
                qtd_ramal = float(val_ramal.get('Qtd', 0))
                tipo_ramal = val_ramal.get('Type', '')
                
                if qtd_ramal > 0 and tipo_ramal:
                    code, desc = self.resolve_ramal_direct(tipo_ramal)
                    results.append({'Origem': f"Ramal {p_id}", 'Código SAP': code, 'Descrição': desc, 'Quantidade': qtd_ramal})

        # Agregação Final
        results = self.aggregate_materials(results)
        return results

    def aggregate_materials(self, materials_list):
        """Agrega materiais por Código SAP, somando quantidades e unindo origens."""
        aggregated = {}
        for mat in materials_list:
            mat = self._ensure_confidence(mat)
            mat = self._apply_manual_correction(mat)
            sap = str(mat['Código SAP'])
            
            # FILTRO DE SEGURANÇA: Remover materiais desativados (Série 9)
            if sap.startswith('9'):
                continue
                
            key = sap if sap != 'VERIFICAR' and sap is not None else f"VERIFICAR-{mat['Descrição']}"
            
            if key in aggregated:
                aggregated[key]['Quantidade'] += mat['Quantidade']
                aggregated[key]['Confiança'] = min(
                    float(aggregated[key].get('Confiança', 1.0)),
                    float(mat.get('Confiança', 1.0))
                )
                current_orig = aggregated[key]['Origem']
                new_orig = mat['Origem']
                if len(current_orig) < 150 and new_orig not in current_orig:
                     aggregated[key]['Origem'] += f", {new_orig}"
            else:
                aggregated[key] = mat.copy()
        
        return list(aggregated.values())

    def process_cables(self, cables_list):
        """
        Processa a lista de cabos extraídos e busca seus códigos SAP.
        cables_list: [{'Tipo': 'BT', 'Desc': '1x3x120(70)', 'Qtd': 24.2}, ...]
        """
        return self.resolve_cables_direct(cables_list)
