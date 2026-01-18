import pandas as pd
import re
import os

# Caminhos padrão (Relativos ao diretório do script)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KITS_PATH = os.path.join(BASE_DIR, 'Biblioteca_Kits', 'Biblioteca de Kits', 'Materiais dos Kits Construtivos 19-06-2023.xlsx')
SAP_PATH = os.path.join(BASE_DIR, 'Codigos de Materiais Novos.xlsx')
CALC_PATH = os.path.join(BASE_DIR, 'CALC rev1 - Copia.xlsx')

# SQLite Database Loader (substitui JSON/Pickle)
try:
    from database_sqlite import SQLiteDatabaseLoader as DatabaseLoader
except ImportError:
    # Fallback para loader legado se SQLite não disponível
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
    'BR1579': [('30053140', 1), ('30053137', 1)], # Exemplo de composição para BR1579
}

class MaterialEngine:
    def __init__(self):
        self.desc_to_sap = {} 
        self.df_kits = None
        self.df_sap = None
        self.depara = {}
        self.is_loaded = False
        
        # Novo: Database Loader
        self.db_loader = None
        self.detected_cables = {'MT': None, 'BT': None} # Novo: Armazenar cabos detectados
        
        # Mapeamento de Cintas (Braçadeiras) extraído dos Padrões Técnicos (.038)
        # Formato: (Tipo Poste, Estrutura) -> [(SAP, Qtd)]
        self.clamp_logic = {
            # Poste 12m 1000daN
            ('C12/1000', 'N'): [('30053140', 2)], # B24 (Antigo 10004439 -> Novo 30053140)
            ('C12/1000', 'B'): [('30053140', 1), ('30053141', 1)], # B24 + B26 (Antigos 10004439/41 -> Novos 30053140/41)
            ('C12/1000', 'U'): [('30053140', 2)], # U4 usa similar a N
            ('C12/1000', 'S'): [('30053143', 1)], # BT usa B28 (Antigo 10004443 -> Novo 30053143)
            
            # Poste 12m 600daN
            ('C12/600', 'N'): [('30053137', 2)], # B20 (Antigo 10004435 -> Novo 30053137)
            ('C12/600', 'B'): [('30053137', 1), ('30053138', 1)], # B20 + B22 (Antigos 10004435/37 -> Novos 30053137/38)
            ('C12/600', 'U'): [('30053137', 2)], 
            ('C12/600', 'S'): [('30053140', 1)], # BT usa B24
            
            # Poste 12m 300daN
            ('C12/300', 'N'): [('30053136', 2)], # B18 (Antigo 10004433 -> Novo 30053136)
            ('C12/300', 'B'): [('30053136', 1), ('30053137', 1)], # B18 + B20
            ('C12/300', 'U'): [('30053136', 2)], 
            ('C12/300', 'S'): [('30053138', 1)], # B22
            
            # Aproximações para 11m
            ('C11/600', 'N'): [('30053137', 2)], 
            ('C11/600', 'B'): [('30053137', 1), ('30053138', 1)],
            ('C11/600', 'U'): [('30053137', 2)],
            ('C11/600', 'S'): [('30053140', 1)],

            ('C11/300', 'N'): [('30053136', 2)],
            ('C11/300', 'B'): [('30053136', 1), ('30053137', 1)],
            ('C11/300', 'U'): [('30053136', 2)],
            ('C11/300', 'S'): [('30053138', 1)],
        }
    
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
        
        # Identificar tipo
        if 'C' in p_type:
            termos_busca.extend(['CIRCULAR', 'CONCR'])
        elif 'DT' in p_type or 'DUPLO T' in p_type:
            termos_busca.append('DUPLO')
        
        # Extrair altura e carga
        import re
        nums = re.findall(r'\d+', p_type)
        if len(nums) >= 2:
            h = nums[0]
            c = nums[1]
            # Adicionar variações de altura para cobrir "12M" e "12,0M"
            termos_busca.append(f'{h}M')
            termos_busca.append(f'{c}DAN')
        elif len(nums) == 1:
            termos_busca.append(f'{nums[0]}M')
        
        exclude_terms = ['CONEXAO', 'TOPO', 'BRACADEIRA', 'LUMINARIA', 'SUPORTE']
        
        if self.db_loader:
            results = self.db_loader.find_material_by_description(termos_busca, limit=1, exclude_terms=exclude_terms)
            if results:
                return results[0][0], results[0][1] # code, desc
                
        return None, f"POSTE {p_type}"

    def clean_code(self, val):
        try:
            if pd.isna(val) or val == "": return ""
            s = str(val).split('.')[0].strip()
            if s.isdigit(): return s
            return s
        except:
            return str(val).strip()

    # OLD load_databases REMOVED - using new one with DatabaseLoader at line 56

    def get_vivid_code(self, code, description):
        code = self.clean_code(code)
        
        # 1. Prioridade absoluta para o DEPARA (Tradução de códigos antigos/especiais)
        if code in self.depara: 
            return self.depara[code]
        
        # 2. Se for um código SAP válido (novo), retorna
        if code.startswith('3'): 
            return code
            
        # 3. Se for código '1...' checa descrição para ver se não é algo genérico
        if code.startswith('1'):
            desc_up = str(description).upper()
            if "CINTA" in desc_up or "BRAÇADEIRA" in desc_up:
                return code # Será tratado na lógica de cintas dinâmicas
            return code

        desc_clean = str(description).upper().replace('SUCATA', '').strip()
        if desc_clean in self.desc_to_sap: return self.desc_to_sap[desc_clean]
        
        words = [w for w in desc_clean.split() if len(w) > 3]
        if len(words) >= 2:
            for sap_desc, sap_code in self.desc_to_sap.items():
                if all(w in sap_desc for w in words[:2]):
                    return sap_code
        return None if code.startswith('9') else code

    def resolve_clamps(self, pole_type, structures):
        """Retorna as braçadeiras E materiais das estruturas baseado no poste e estruturas."""
        mats = []
        p_type = str(pole_type).replace('x', '/').replace(' ', '').upper() # Normaliza C12x1000 -> C12/1000
        
        # 1. Adicionar o próprio POSTE
        if "(E)" in str(pole_type):
            pass # Ignorar poste existente
        else:
            is_ret = "(R)" in str(pole_type)
            p_clean = str(pole_type).replace("(R)", "").strip()
            suffix = " (RETIRADA)" if is_ret else ""
            
            p_code, p_desc = self.get_pole_sap(p_clean)
            if p_code:
                mats.append({'Origem': 'Poste', 'Código SAP': p_code, 'Descrição': p_desc + suffix, 'Quantidade': 1})
            else:
                mats.append({'Origem': 'Poste', 'Código SAP': 'VERIFICAR', 'Descrição': f'POSTE {p_clean}{suffix}', 'Quantidade': 1})

        # 2. Braçadeiras (mantém lógica existente)
        for est_raw in structures:
            if "(E)" in str(est_raw): continue # Ignorar existentes
            is_ret = "(R)" in str(est_raw)
            est = str(est_raw).replace("(R)", "").strip()
            suffix = " (RETIRADA)" if is_ret else ""
            
            est_cat = ''
            if est.startswith('N'): est_cat = 'N'
            elif est.startswith('B'): est_cat = 'B'
            elif est.startswith('U'): est_cat = 'U'
            elif 'S' in est: est_cat = 'S' # Cobre S1, 1S3, 1S4 etc
            
            lookup = (p_type, est_cat)
            if lookup in self.clamp_logic:
                for sap, qty in self.clamp_logic[lookup]:
                    if self.db_loader and str(sap) in self.db_loader.sap_codes:
                        desc = self.db_loader.sap_codes[str(sap)] + suffix
                    else:
                        desc = f"BRACADEIRA SAP {sap}{suffix}"
                    
                    mats.append({
                        'Origem': f'Ferragem {p_type}+{est}',
                        'Código SAP': sap,
                        'Descrição': desc,
                        'Quantidade': qty
                    })
        
        # 3. NOVO: Explodir estruturas em materiais componentes
        if self.db_loader and self.is_loaded:
            for est_raw in structures:
                if "(E)" in str(est_raw): continue # Ignorar existentes
                is_ret = "(R)" in str(est_raw)
                est = str(est_raw).replace("(R)", "").strip()
                suffix = " (RETIRADA)" if is_ret else ""

                structure_materials = self.db_loader.explode_structure(est, pole_type_str=pole_type)
                for mat in structure_materials:
                    code = mat['code']
                    desc = str(mat['desc']) + suffix
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
                        # Tenta pegar do metadata carregado
                        lookup_table = self.db_loader.unified_db.get('cinta_lookup', {}) if (self.db_loader and self.db_loader.unified_db) else {}
                        
                        p_normalized = p_type.replace('DT', '').replace('RT', '').replace('C', '').replace('/', '-').replace(' ', '').strip()
                        # Tenta diversos formatos de chave
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
                            # Se achou diâmetro mas não o SAP exato, pelo menos dá uma descrição melhor
                            code = "VERIFICAR"
                            desc = f"CINTA POSTE AC ZC F {diameter}MM (SAP DESCONHECIDO){suffix}"
                        elif code == "VERIFICAR-POSTE" or code == "10004437":
                            # Se falhou tudo mas o código era o temporário, tenta dar uma descrição mais rica se puder
                            # Mas mantém o VERIFICAR para o usuário saber que o poste precisa de atenção
                            desc = f"CINTA (DIAMETRO NAO ENCONTRADO PARA POSTE {p_type}){suffix}"
                    
                    elif "ALÇA" in desc_upper and (code == "VERIFICAR" or code == "VERIFICAR-CABO"):
                        mt_c = self.detected_cables.get('MT')
                        if mt_c:
                            mt_c_up = mt_c.upper()
                            resolved = False
                            # Priorizar ANA (Alumínio Nu)
                            for bitola, sap in ALCA_MT_NU_MAP.items():
                                if bitola in mt_c_up:
                                    code = sap
                                    desc = (self.db_loader.sap_codes[sap] if self.db_loader and sap in self.db_loader.sap_codes else f"ALÇA {bitola}") + suffix
                                    resolved = True; break
                            
                            if not resolved:
                                # Tentar Protegido
                                for bitola, sap in ALCA_MT_PROT_MAP.items():
                                    if bitola in mt_c_up:
                                        code = sap
                                        desc = (self.db_loader.sap_codes[sap] if self.db_loader and sap in self.db_loader.sap_codes else f"ALÇA {bitola}") + suffix
                                        resolved = True; break
                            
                            # Se resolveu, tentar buscar descrição rica no banco técnico
                            if resolved and code != "VERIFICAR" and self.db_loader:
                                rich_desc = self.db_loader.get_sap_description(code)
                                if rich_desc: desc = rich_desc + suffix
                    
                    # Verificação Manual para Estruturas como BR1579
                    if code == "VERIFICAR" and est in MANUAL_EST_MAP:
                        # Se for uma estrutura que conhecemos o mapeamento manual
                        for m_sap, m_qty in MANUAL_EST_MAP[est]:
                            m_desc = self.db_loader.sap_codes.get(m_sap, f"ITEM {m_sap}") if self.db_loader else m_sap
                            mats.append({
                                'Origem': f'Estrutura {est} (Manual)',
                                'Código SAP': m_sap,
                                'Descrição': m_desc + suffix,
                                'Quantidade': m_qty * qty
                            })
                        continue # Pula o append do VERIFICAR original

                    # Correção Específica para Parafusos M16x400 vindos como VERIFICAR-POSTE
                    if (code == "VERIFICAR-POSTE" or "VERIFICAR" in code) and "PARAFUSO" in desc_upper and "400" in desc_upper:
                         code = "30058241"
                         if self.db_loader and code in self.db_loader.sap_codes:
                             desc = self.db_loader.sap_codes[code] + suffix
                         else:
                             desc = f"PARAFUSO CAB QUAD 16MM 400MM AC{suffix}"

                    mats.append({
                        'Origem': f'Estrutura {est}',
                        'Código SAP': code,
                        'Descrição': desc,
                        'Quantidade': qty
                    })
        
        return mats
    
    def resolve_cables_direct(self, cables):
        """Resolve cabos diretamente no CALC por descrição"""
        mats = []
        
        for cabo in cables:
            desc = cabo.get('Desc', '')
            if "(E)" in desc: continue # Ignorar cabos existentes
            qtd = cabo.get('Qtd', 0)
            tipo = cabo.get('Tipo', '')
            
            # Novo: Armazenar o primeiro cabo de cada tipo para resoluções dinâmicas (ex: Alças)
            if tipo in self.detected_cables and not self.detected_cables[tipo]:
                self.detected_cables[tipo] = desc
            import re
            
            termos_busca = ['CABO']
            
            # Padrão para cabos multiplexados BT (ex: 3x120+70)
            if tipo == 'BT':
                termos_busca.append('AL')
                if '120' in desc: termos_busca.append('120MM2')
                elif '70' in desc: termos_busca.append('70MM2')
                elif '35' in desc: termos_busca.append('35MM2')
            
            # Padrão para cabos MT (ANA -> ROSE/SPARROW/etc)
            elif tipo == 'MT':
                termos_busca.append('MT')
                if 'ANA' in desc.upper():
                    termos_busca.append('ALUMINIO')
            
            # Fallback if no specific bits found
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
                        'Quantidade': qtd
                    })
                else:
                    mats.append({
                        'Origem': f'Cabo {tipo}',
                        'Código SAP': 'VERIFICAR',
                        'Descrição': desc,
                        'Quantidade': qtd
                    })
            else:
                mats.append({
                    'Origem': f'Cabo {tipo}',
                    'Código SAP': 'VERIFICAR',
                    'Descrição': desc,
                    'Quantidade': qtd
                })
        
        return mats
    
    def resolve_poles_direct(self, pole_types):
        """Resolve postes diretamente no CALC"""
        mats = []
        
        for pole_type in pole_types:
            # Formato: C12/1000 → buscar "POSTE", "CIRCULAR", "12", "1000"
            p_type = str(pole_type).upper()
            
            termos_busca = ['POSTE']
            
            # Identificar tipo
            if p_type.startswith('C'):
                termos_busca.append('CIRCULAR')
                termos_busca.append('CONCR')
            elif p_type.startswith('D'):
                termos_busca.append('DUPLO')
            
            # Extrair altura e carga
            import re
            nums = re.findall(r'\d+', p_type)
            if len(nums) >= 2:
                h = nums[0]
                c = nums[1]
                termos_busca.append(f'{h}M')
                termos_busca.append(f'{h},0M') # Adiciona variação 12,0M
                termos_busca.append(f'{c}DAN')
            elif len(nums) == 1:
                termos_busca.append(f'{nums[0]}M')
            
            exclude_terms = ['CONEXAO', 'TOPO', 'BRACADEIRA', 'LUMINARIA', 'SUPORTE']
            
            if self.db_loader:
                results = self.db_loader.find_material_by_description(termos_busca, limit=1, exclude_terms=exclude_terms)
                
                if results:
                    code, desc, score = results[0]
                    mats.append({
                        'Origem': 'Poste',
                        'Código SAP': code,
                        'Descrição': desc,
                        'Quantidade': 1
                    })
                else:
                    mats.append({
                        'Origem': 'Poste',
                        'Código SAP': 'VERIFICAR',
                        'Descrição': f'POSTE {p_type}',
                        'Quantidade': 1
                    })
            else:
                mats.append({
                    'Origem': 'Poste',
                    'Código SAP': 'VERIFICAR',
                    'Descrição': f'POSTE {p_type}',
                    'Quantidade': 1
                })
        
        return mats
    
    def resolve_transformers_direct(self, transformers):
        """Resolve transformadores diretamente no CALC"""
        mats = []
        
        for transf in transformers:
            # Formato: MONO-5kVA → buscar "TRAFO", "MONO", "5"
            t_type = str(transf).upper()
            
            # Termos de busca mais flexíveis baseados na imagem do usuário
            termos_busca = ['TRAFO']
            
            if 'MONO' in t_type:
                termos_busca.extend(['MONOF', '1F'])
            elif 'TRI' in t_type:
                termos_busca.extend(['TRIF', '3F'])
            
            # Extrair potência (ex: 45kVA -> 45KVA)
            import re
            nums = re.findall(r'(\d+\.?\d*)', t_type)
            if nums:
                potencia = nums[0]
                termos_busca.append(f'{potencia}KVA')
            
            if self.db_loader:
                exclude_terms = ['SUCATA', 'BUCHA', 'PROTECAO', 'SUPORTE', 'RELIG', 'CHAVE']
                results = self.db_loader.find_material_by_description(termos_busca, limit=1, exclude_terms=exclude_terms)
                
                # Se não achou com "TRAFO", tentar "TRANSFORMADOR"
                if not results:
                    termos_alt = [t if t != 'TRAFO' else 'TRANSFORMADOR' for t in termos_busca]
                    results = self.db_loader.find_material_by_description(termos_alt, limit=1)

                if results:
                    code, desc, score = results[0]
                    mats.append({
                        'Origem': 'Transformador',
                        'Código SAP': code,
                        'Descrição': desc,
                        'Quantidade': 1
                    })
                else:
                    mats.append({
                        'Origem': 'Transformador',
                        'Código SAP': 'VERIFICAR',
                        'Descrição': f'TRAFO {t_type}',
                        'Quantidade': 1
                    })
            else:
                mats.append({
                    'Origem': 'Transformador',
                    'Código SAP': 'VERIFICAR',
                    'Descrição': f'TRAFO {t_type}',
                    'Quantidade': 1
                })
        
        return mats

    def resolve_ramal_direct(self, ramal_desc):
        """Busca o código SAP do ramal de ligação pela descrição"""
        if not ramal_desc or not self.db_loader:
            return "VERIFICAR", ramal_desc

        # Limpar descrição para termos de busca
        desc_upper = ramal_desc.upper()
        termos = ["CABO"]
        
        if "MULT" in desc_upper: termos.append("MULT")
        if "CONCENTRICO" in desc_upper: termos.append("CONCENTRICO")
        
        # Extrair bitola (ex: 120, 35, 70, 16, 25)
        import re
        nums = re.findall(r'\b(\d{2,3})\b', desc_upper)
        if nums:
            # Buscar preferencialmente com "MM2" para evitar "120V" ou números de medidores
            termos_completos = termos + [f"{nums[0]}MM2"]
            results = self.db_loader.find_material_by_description(termos_completos, limit=1)
            if results: return results[0][0], results[0][1]
            
            # Fallback para número puro
            termos.append(nums[0])

        results = self.db_loader.find_material_by_description(termos, limit=5)
        if results:
            # Filtrar para evitar medidores
            for code, desc, score in results:
                if "MED " not in desc.upper() and "MEDIDOR" not in desc.upper():
                    return code, desc
            
            return results[0][0], results[0][1] # code, desc
            
        return "VERIFICAR", ramal_desc

    def explode_structures(self, structures_dict, pole_mapping=None):
        """
        pole_mapping: {'P1': {'Pole': 'C12/1000', 'Est': ['N1', 'U3']}, ...}
        """
        self.load_databases()
        results = []
        
        # Proteção: só tenta ler Excel se o arquivo existir (Legado)
        if os.path.exists(CALC_PATH):
            df_calc_mats = pd.read_excel(CALC_PATH, sheet_name='MATERIAIS')
        else:
            df_calc_mats = pd.DataFrame()

        # 1. Explodir Estruturas via Kits/Calculadora
        for name, qtd_proj in structures_dict.items():
            if self.df_kits is not None:
                mask = (self.df_kits[0].astype(str) == str(name)) | (self.df_kits[1].astype(str).str.contains(str(name), case=False, na=False, regex=False))
                kit_rows = self.df_kits[mask]
                
                if not kit_rows.empty:
                    chosen_kit = kit_rows.iloc[0, 0]
                    mats = self.df_kits[self.df_kits[0] == chosen_kit]
                    for _, row in mats.iterrows():
                        v_code = self.get_vivid_code(row[2], row[3])
                        if not v_code or v_code.startswith(('9', '7')) or 'CINTA' in str(row[3]).upper() or 'BRAÇADEIRA' in str(row[3]).upper(): 
                            continue # Pula cintas genéricas, vamos resolver com a lógica de poste
                        
                        desc_final = str(row[3])
                        if self.df_sap is not None and v_code in self.df_sap['Material Novo'].values:
                            desc_final = self.df_sap[self.df_sap['Material Novo'] == v_code]['Texto Breve Material'].iloc[0]
                            
                        results.append({
                            'Origem': name, 'Código SAP': v_code, 
                            'Descrição': desc_final,
                            'Quantidade': abs(float(str(row[5]).replace(',', '.'))) * qtd_proj
                        })

            if not df_calc_mats.empty:
                calc_rows = df_calc_mats[df_calc_mats['ESTRUTURA'].astype(str) == str(name)]
            for _, row in calc_rows.iterrows():
                v_code = self.get_vivid_code(row['CODIGO'], row['MATERIAIS'])
                if v_code and not v_code.startswith(('9', '7')) and not ('CINTA' in str(row['MATERIAIS']).upper()):
                    q = 1.0
                    try: 
                        qv = float(row['QTDEBASE'])
                        q = qv if qv < 50 else 1.0
                    except: pass
                    results.append({
                        'Origem': name, 'Código SAP': v_code, 'Descrição': str(row['MATERIAIS']), 'Quantidade': q * qtd_proj
                    })
        
        if pole_mapping:
            for p_id, data in pole_mapping.items():
                clamp_mats = self.resolve_clamps(data['Pole'], data['Est'])
                results.extend(clamp_mats)

        return results

    def process_form_data(self, pole_map):
        """
        Processa os dados vindos do Grid do novo app.py
        pole_map: {'P1': {'Pole': ..., 'Est': [], 'Trafo': ..., 'Chave': ..., 'Estai': 2, ...}}
        """
        results = []
        
        for p_id, data in pole_map.items():
            # 1. Poste e Estruturas (Reutiliza lógica existente)
            # resolve_clamps já adiciona o poste e as ferragens das estruturas
            clamp_mats = self.resolve_clamps(data['Pole'], data['Est'])
            results.extend(clamp_mats)
            
            # 2. Transformador
            if data.get('Trafo') and data['Trafo'] != "None":
                if "(E)" in str(data['Trafo']): continue # Ignorar trafo existente
                t_val = str(data['Trafo']).upper()
                
                # A. Incluir o Equipamento Transformador em si
                transf_mats = self.resolve_transformers_direct([t_val])
                for tm in transf_mats:
                    tm['Origem'] = f"Trafo {p_id}" # Sobrescrever origem para clareza
                    results.append(tm)
                
                # B. Incluir o Kit de Hardware (Acessórios)
                kit_key = None
                if "MONO" in t_val:
                    kit_key = "TRAFO_MONO"
                elif "TRI" in t_val and "45" in t_val:
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

            # 3. Chave
            if data.get('Chave'):
                chave_sap = "VERIFICAR"
                if "FUSIVEL" in data['Chave']: chave_sap = "30006789" # Exemplo
                results.append({'Origem': f"Chave {p_id}", 'Código SAP': chave_sap, 'Descrição': f"CHAVE {data['Chave']}", 'Quantidade': 1})
            
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
                
                # Itens genéricos de estai (Haste + Cordoalha)
                results.append({'Origem': f"Estai {p_id}", 'Código SAP': '30056363', 'Descrição': f'HASTE ANCOR AC 1020 3200DAN 16MM 1,6M{desc_extra}{suffix}', 'Quantidade': qtd_estai})
                results.append({'Origem': f"Estai {p_id}", 'Código SAP': '30054507', 'Descrição': f'CORDOALHA ACO CARB 9,5MM 7F CL.B MR/SM{suffix}', 'Quantidade': qtd_estai * 10}) # 10m por estai
            
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
            
            # 6. Para-Raio
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
                
                # Código genérico ou específico se disponível
                sap_pr = '30053319' # COBERTURA (exemplo)
                desc_pr = f'CONJUNTO PARA-RAIO - {t_clean}{suffix}'
                results.append({'Origem': f"Para-Raio {p_id}", 'Código SAP': sap_pr, 'Descrição': desc_pr, 'Quantidade': qtd_pr})

            # 7. Ramal
            val_ramal = data.get('Ramal', {})
            if isinstance(val_ramal, dict):
                qtd_ramal = float(val_ramal.get('Qtd', 0))
                tipo_ramal = val_ramal.get('Type', '')
                
                if qtd_ramal > 0 and tipo_ramal:
                    # Tentar encontrar SAP para o tipo de cabo (pode usar resolve_cables ou direto)
                    code, desc = self.resolve_ramal_direct(tipo_ramal)
                    results.append({'Origem': f"Ramal {p_id}", 'Código SAP': code, 'Descrição': desc, 'Quantidade': qtd_ramal})

        return results

    def process_cables(self, cables_list):
        """
        Processa a lista de cabos extraídos e busca seus códigos SAP usando resolve_cables_direct.
        cables_list: [{'Tipo': 'BT', 'Desc': '1x3x120(70)', 'Qtd': 24.2}, ...]
        """
        return self.resolve_cables_direct(cables_list)
