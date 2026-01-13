"""
Database Loader - Carrega todas as bases de dados para explosão de materiais
"""
import pandas as pd
import pdfplumber
import os
import re
import pickle
import time
from pathlib import Path
import json # Added for unified_db.json

class DatabaseLoader:
    CACHE_FILE = "database_cache.pkl"

    UNIFIED_DB_FILE = "unified_db.json"

    def __init__(self, base_dir="."): # Kept base_dir parameter for flexibility, but instruction changes it to os.getcwd()
        self.base_dir = Path(os.getcwd()) # Changed as per instruction
        # Dados Legados
        self.sap_codes = {}
        self.kit_library = {}
        self.kit_rules = {}
        self.technical_standards = {}
        self.master_bom = {}
        # Dados Novos
        self.unified_db = None

        # Mapeamento manual de estruturas que não estão nos kits (fallback legado)
        self.structure_materials_map = {
             'U4': [
                {'code': '10004426', 'desc': 'ISOLADOR PILAR PORCELANA 15KV 110KV', 'qty': 1},
                # ... (rest of U4 if needed for fallback, but ideally use JSON)
             ]
             # Outros hardcoded podem ser removidos pois foram migrados
        }
        
    def load_all(self, force_legacy=False):
        """Carrega dados. Prioriza Unified DB se existir, a menos que force_legacy=True."""
        print("Carregando bases de dados...")
        
        # 1. Tentar Unified DB
        unified_path = self.base_dir / self.UNIFIED_DB_FILE
        if unified_path.exists() and not force_legacy:
            print("Carregando Unified Database (JSON)...")
            try:
                with open(unified_path, 'r', encoding='utf-8') as f:
                    self.unified_db = json.load(f)
                
                # Popular helpers para compatibilidade parcial, se necessário, ou apenas usar self.unified_db
                self.sap_codes = self.unified_db.get('sap_library', {})
                # Repovoar mapa manual se quiser garantir (opcional)
                
                print(f"OK: Unified DB carregado. {len(self.unified_db.get('structures', {}))} estruturas.")
                return 
            except Exception as e:
                print(f"Erro ao carregar Unified DB: {e}. Tentando legado...")

        # 2. Cache Legado ou Load Full (Fallback)
        if self._load_from_cache():
            print("Bases carregadas do Cache legado!")
            return

        print("Iniciando carregamento completo das bases de dados (legado)...")
        start_time = time.time()
        
        self.load_master_bom()  # NOVO: Carregar BOM primeiro
        self.load_calc_database()  # NOVO: Carregar CALC primeiro (fonte principal)
        self.load_sap_codes()
        self.load_technical_standards()
        self.load_kit_rules()
        
        elapsed = time.time() - start_time
        print(f"OK: Carregamento COMPLETO concluido em {elapsed:.2f}s:")
        print(f"  - {len(self.master_bom)} categorias BOM")
        print(f"  - {len(self.sap_codes)} codigos SAP")
        print(f"  - {len(self.technical_standards)} padroes tecnicos")
        print(f"  - {len(self.kit_rules)} regras de kits")
        
        # Salvar cache para proxima vez
        self._save_to_cache()
        print(f"OK: Carregamento legado concluido.")
    
    def _get_source_files(self):
        """Retorna lista de todos os arquivos fonte para verificar modificação"""
        files = []
        
        # Arquivos principais
        files.append(self.base_dir / "CALC rev2.xlsx")
        files.append(self.base_dir / "CALC rev1 - Copia.xlsx")
        files.append(self.base_dir / "Codigos de Materiais Novos.xlsx")
        files.append(self.base_dir / "Biblioteca_Kits" / "Biblioteca de Kits" / "Materiais dos Kits Construtivos 19-06-2023.xlsx")
        
        # PDFs
        files.extend(list(self.base_dir.glob("PT.DT.PDN*.pdf")))
        
        # Regras Kits
        files.append(self.base_dir / "Regras_Kits" / "Regras Kits" / "4 - Regra Kit - Estrutura Primaria - Isolador.xlsx")
        files.append(self.base_dir / "Regras_Kits" / "Regras Kits" / "5 - Regra Kit - Estrutura Primaria - Fixação.xlsx")
        
        return files

    def _load_from_cache(self):
        """Tenta carregar do cache pickle se estiver atualizado"""
        cache_path = self.base_dir / self.CACHE_FILE
        
        if not cache_path.exists():
            print("Cache não encontrado. Carregando do zero...")
            return False
            
        # Verificar timestamps
        try:
            cache_mtime = cache_path.stat().st_mtime
            source_files = self._get_source_files()
            
            for f in source_files:
                if f.exists():
                    if f.stat().st_mtime > cache_mtime:
                        print(f"Arquivo fonte alterado: {f.name}. Recarregando...")
                        return False
            
            # Se chegou aqui, cache é válido
            print("Carregando bases de dados do CACHE (Rápido)...")
            start = time.time()
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
                self.sap_codes = data.get('sap_codes', {})
                self.kit_library = data.get('kit_library', {})
                self.kit_rules = data.get('kit_rules', {})
                self.technical_standards = data.get('technical_standards', {})
                self.master_bom = data.get('master_bom', {})
            
            print(f"OK: Carregado do CACHE em {time.time() - start:.2f}s")
            return True
            
        except Exception as e:
            print(f"Erro ao ler cache: {e}. Recarregando...")
            return False

    def _save_to_cache(self):
        """Salva estado atual no cache pickle"""
        try:
            cache_path = self.base_dir / self.CACHE_FILE
            data = {
                'sap_codes': self.sap_codes,
                'kit_library': self.kit_library,
                'kit_rules': self.kit_rules,
                'technical_standards': self.technical_standards,
                'master_bom': self.master_bom
            }
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
            print(f"Cache salvo com sucesso em {self.CACHE_FILE}")
        except Exception as e:
            print(f"Erro ao salvar cache: {e}")
    
    def load_master_bom(self):
        """Carrega estrutura mestra compilada do BOM do CALC"""
        try:
            calc_path = self.base_dir / "CALC rev2.xlsx"
            df_bom = pd.read_excel(calc_path, sheet_name='BOM')
            
            for _, row in df_bom.iterrows():
                categoria = str(row['CATEGORIA']).strip()
                estrutura_raw = str(row['ESTRUTURA']).strip()
                codigo = str(row['CODIGO']).strip()
                material = str(row['MATERIAIS']).strip()
                qtde = row['QTDEBASE']
                
                # Normalizar estrutura: extrair código puro (B1, B2F, ET4A, etc.)
                # Formato: "1ª - B1-CIRC CONC 11M..." → B1
                estrutura = self._normalize_structure_code(estrutura_raw)
                
                if categoria not in self.master_bom:
                    self.master_bom[categoria] = {}
                
                if estrutura not in self.master_bom[categoria]:
                    self.master_bom[categoria][estrutura] = []
                
                self.master_bom[categoria][estrutura].append({
                    'codigo': codigo,
                    'descricao': material,
                    'quantidade': qtde
                })
            
            print(f"  + BOM mestre carregado: {len(self.master_bom)} categorias")
        except Exception as e:
            print(f"  AVISO: Erro ao carregar BOM mestre: {e}")
    
    def _normalize_structure_code(self, estrutura_raw):
        """
        Extrai código puro da estrutura removendo prefixos e sufixos.
        Exemplos:
          "1ª - B1-CIRC CONC 11M..." → "B1"
          "2ª - B2F-CIRC..." → "B2F"
          "B1" → "B1"
        """
        import re
        
        # Se já é código simples, retornar
        if len(estrutura_raw) <= 6 and re.match(r'^[A-Z0-9]+$', estrutura_raw):
            return estrutura_raw
        
        # Tentar extrair padrão: "1ª - B1-..." ou "1ª - B2F-..."
        match = re.search(r'(?:^|\s|-)([A-Z]+\d+[A-Z]*?)(?:-|\s|$)', estrutura_raw)
        if match:
            return match.group(1)
        
        # Fallback: retornar original
        return estrutura_raw
    
    def load_calc_database(self):
        """Carrega base CALC com milhares de codigos de materiais"""
        try:
            calc_path = self.base_dir / "CALC rev1 - Copia.xlsx"
            
            # Carregar aba CODIGOS (tem Material Novo, Antigo, Descricao)
            df_codigos = pd.read_excel(calc_path, sheet_name='CODIGOS')
            
            for _, row in df_codigos.iterrows():
                # Código novo (principal)
                code_novo = str(row['Material Novo']).strip()
                desc = str(row['Texto Breve Material']).strip()
                
                if code_novo and code_novo != 'nan':
                    self.sap_codes[code_novo] = desc
                
                # Código antigo (compatibilidade)
                if ' Material Antigo' in df_codigos.columns:
                    code_antigo = str(row[' Material Antigo']).strip()
                    if code_antigo and code_antigo != 'nan':
                        self.sap_codes[code_antigo] = desc
            
            print(f"  + CALC carregado: {len(self.sap_codes)} materiais")
        except Exception as e:
            print(f"  AVISO: Erro ao carregar CALC: {e}")
        
    def load_sap_codes(self):
        """Carrega códigos SAP"""
        try:
            df = pd.read_excel(self.base_dir / "Codigos de Materiais Novos.xlsx")
            for _, row in df.iterrows():
                code = str(row['Material Novo'])
                desc = row['Texto Breve Material']
                self.sap_codes[code] = desc
            print(f"  + Códigos SAP carregados: {len(self.sap_codes)}")
        except Exception as e:
            print(f"  AVISO: Erro ao carregar SAP: {e}")
    
    def load_technical_standards(self):
        """Carrega padrões técnicos PT.DT.PDN (PDFs)"""
        pdf_files = list(self.base_dir.glob("PT.DT.PDN*.pdf"))
        
        for pdf_file in pdf_files:
            try:
                std_name = pdf_file.stem
                tables = self._extract_tables_from_pdf(pdf_file)
                self.technical_standards[std_name] = tables
                print(f"  + {std_name}: {len(tables)} tabelas")
            except Exception as e:
                print(f"  AVISO: Erro em {pdf_file.name}: {e}")
    
    def _extract_tables_from_pdf(self, pdf_path):
        """Extrai tabelas de um PDF"""
        tables = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                page_tables = page.extract_tables()
                if page_tables:
                    for table in page_tables:
                        if table and len(table) > 1:  # Pelo menos header + 1 linha
                            df = pd.DataFrame(table[1:], columns=table[0])
                            tables.append({
                                'page': page_num + 1,
                                'data': df
                            })
        
        return tables
    
    def load_kit_rules(self):
        """Carrega regras de kits (Excels) e Biblioteca de Kits"""
        
        # 1. Carregar Biblioteca de Kits (materiais por código de kit)
        self._load_kit_library()
        
        # 2. Carregar Regras (relaciona estrutura → código kit)
        self._load_kit_rules_files()
        
        print(f"  + Regras de kits carregadas: {len(self.kit_rules)}")
    
    def _load_kit_library(self):
        """Carrega Biblioteca de Kits com materiais por código"""
        try:
            biblioteca_kits = {}
            caminho = self.base_dir / "Biblioteca_Kits" / "Biblioteca de Kits" / "Materiais dos Kits Construtivos 19-06-2023.xlsx"
            
            df = pd.read_excel(caminho, sheet_name='Dados')
            
            # Agrupar materiais por código de kit
            for _, row in df.iterrows():
                codigo_kit = str(row.iloc[0]).strip()
                codigo_material = str(row.iloc[2]).strip()
                desc_material = str(row.iloc[3]).strip()
                qtd = row.iloc[5]
                
                # Ignorar linhas de cabeçalho ou vazias
                if codigo_kit and codigo_material and codigo_kit != 'Código Kit':
                    if codigo_kit not in biblioteca_kits:
                        biblioteca_kits[codigo_kit] = []
                    
                    # Só adicionar materiais com quantidade positiva (não removidos)
                    if pd.notna(qtd) and qtd > 0:
                        biblioteca_kits[codigo_kit].append({
                            'codigo': codigo_material,
                            'descricao': desc_material,
                            'quantidade': qtd
                        })
            
            self.kit_library = biblioteca_kits
            print(f"  + Biblioteca de Kits: {len(biblioteca_kits)} kits")
            
        except Exception as e:
            print(f"  AVISO: Erro ao carregar biblioteca kits: {e}")
    
    def _load_kit_rules_files(self):
        """Carrega regras de kits (estrutura → {nivel → kit}) dos arquivos Excel"""
        try:
            arquivos_processar = [
                "4 - Regra Kit - Estrutura Primaria - Isolador.xlsx",
                "5 - Regra Kit - Estrutura Primaria - Fixação.xlsx",
            ]
            
            for arquivo_nome in arquivos_processar:
                caminho = self.base_dir / "Regras_Kits" / "Regras Kits" / arquivo_nome
                
                if not caminho.exists():
                    continue
                
                df = pd.read_excel(caminho)
                
                # Processar linhas (formato: linha tem múltiplas estruturas separadas por ;)
                for _, row in df.iterrows():
                    estruturas_str = str(row.iloc[0]).strip()
                    nivel_agressao = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else 'Comum'
                    codigo_kit = str(row.iloc[3]).strip()
                    
                    # Verificar se é linha válida
                    if estruturas_str and codigo_kit and estruturas_str != 'Tipo Estrutura':
                        # Separar estruturas
                        if ';' in estruturas_str:
                            estruturas = [e.strip() for e in estruturas_str.split(';')]
                        else:
                            estruturas = [estruturas_str]
                        
                        # Mapear cada estrutura ao kit POR NÍVEL          
                        for est in estruturas:
                            if est and est not in ['nan', 'NaN']:
                                # Criar dict de níveis se não existir
                                if est not in self.kit_rules:
                                    self.kit_rules[est] = {}
                                
                                # Se já existe kit para este nível, concatenar (Isolador + Fixação)
                                if nivel_agressao not in self.kit_rules[est]:
                                    self.kit_rules[est][nivel_agressao] = []
                                
                                # Adicionar kit à lista
                                if isinstance(self.kit_rules[est][nivel_agressao], list):
                                    self.kit_rules[est][nivel_agressao].append(codigo_kit)
                                else:
                                    # Converter single para lista
                                    old_kit = self.kit_rules[est][nivel_agressao]
                                    self.kit_rules[est][nivel_agressao] = [old_kit, codigo_kit]
            
        except Exception as e:
            print(f"  AVISO: Erro ao carregar regras kits: {e}")
    
    def get_sap_description(self, code):
        """Retorna descrição do código SAP"""
        return self.sap_codes.get(str(code), f"SAP {code}")
    
    def find_material_by_description(self, search_terms, limit=5):
        """
        Busca materiais por termos na descrição.
        search_terms: lista de termos ou string única
        Retorna lista de tuplas (code, description, score)
        """
        if isinstance(search_terms, str):
            search_terms = [search_terms]
        
        search_terms =  [term.upper() for term in search_terms]
        results = []
        
        for code, desc in self.sap_codes.items():
            desc_upper = desc.upper()
            
            # Calcular score (quantos termos foram encontrados)
            score = sum(1 for term in search_terms if term in desc_upper)
            
            if score > 0:
                results.append((code, desc, score))
        
        # Ordenar por score (maior primeiro)
        results.sort(key=lambda x: x[2], reverse=True)
        
        return results[:limit]
    
    def find_structure_in_standards(self, structure_code):
        """Busca estrutura nos padrões técnicos"""
        materials = []
        
        # Percorrer todos os padrões técnicos
        for std_name, tables in self.technical_standards.items():
            for table_info in tables:
                df = table_info['data']
                
                # Procurar estrutura nas tabelas
                # Adaptar conforme formato real das tabelas
                for col in df.columns:
                    if structure_code in str(df[col].values):
                        # Encontrou - extrair materiais desta linha/seção
                        # Implementação específica conforme formato
                        pass
        
        return materials
    
    def explode_structure(self, structure_code, nivel=1, pole_type_str=""):
        """
        Retorna lista de materiais filtrada pelo tipo de poste.
        pole_type_str: ex "DT 12/1000", "11/400"
        """
        materials = []
        structure_code = str(structure_code).strip()
        
        # Determinar tipo de poste (DT ou Circular)
        is_dt = False
        if pole_type_str:
            p_upper = pole_type_str.upper()
            if p_upper.startswith("DT") or p_upper.startswith("RT") or "DUPLO T" in p_upper:
                is_dt = True
            # Se não começa com DT/RT, assumimos Circular (padrão)
        
        # 1. Unified DB
        if self.unified_db and 'structures' in self.unified_db:
            if structure_code in self.unified_db['structures']:
                raw_mats = self.unified_db['structures'][structure_code]
                for m in raw_mats:
                    m_type = m.get('type', 'ALL')
                    
                    # Filtro
                    include = False
                    if m_type == 'ALL':
                        include = True
                    elif m_type == 'DT' and is_dt:
                        include = True
                    elif m_type == 'CIRCULAR' and not is_dt:
                        include = True
                        
                    if include:
                        materials.append({
                            'code': m['sap'],
                            'desc': m['desc'],
                            'qty': m['qty']
                        })
                return materials
        
        # --- LEGADO ABAIXO --- (Só executa se não achou no Unified)
        
        # 2. Tentar BOM mestre primeiro
        nivel_key = f'ESTRUTURA-{nivel}'
        
        if nivel_key in self.master_bom:
            if structure_code in self.master_bom[nivel_key]:
                bom_mats = []
                suspicious = False
                for mat in self.master_bom[nivel_key][structure_code]:
                    if mat['quantidade'] > 100:
                        suspicious = True
                        break
                    bom_mats.append({
                        'code': mat['codigo'],
                        'desc': mat['descricao'],
                        'qty': mat['quantidade']
                    })
                
                if not suspicious:
                    return bom_mats
        
        # 3. Tentar Kit Library
        if structure_code in self.kit_rules:
            # kit_rules agora é {estrutura: {nivel: [kit1, kit2, ...]}}
            niveis_map = self.kit_rules[structure_code]
            
            prioridade_niveis = ['Comum', 'Baixa agressão', 'Média agressão', 'Alta agressão']
            
            codigos_kit = None
            for nv in prioridade_niveis:
                if nv in niveis_map:
                    codigos_kit = niveis_map[nv]
                    break
            
            if not codigos_kit and niveis_map:
                codigos_kit = list(niveis_map.values())[0]
            
            if codigos_kit and not isinstance(codigos_kit, list):
                codigos_kit = [codigos_kit]
            
            if codigos_kit:
                for codigo_kit in codigos_kit:
                    if codigo_kit in self.kit_library:
                        for mat in self.kit_library[codigo_kit]:
                            materials.append({
                                'code': mat['codigo'],
                                'desc': mat['descricao'],
                                'qty': mat['quantidade']
                            })
                if materials:
                    return materials

        # 3. Busca manual (Estático) - Último recurso
        if structure_code in self.structure_materials_map:
             return self.structure_materials_map[structure_code]
            
        # Tentar mapear códigos similares
        if structure_code == 'A4':
             return self.explode_structure('U4', nivel) # Fallback seguro
        if structure_code == 'P01':
             return self.explode_structure('N1', nivel)
        if structure_code == 'P1': 
             return self.explode_structure('N1', nivel)
                
        print(f"AVISO: Estrutura {structure_code} não encontrada em nenhuma base (Unified, BOM, Kits).")
        return [
            {'code': 'VERIFICAR', 'desc': f'VERIFICAR ESTRUTURA {structure_code}', 'qty': 1}
        ]

if __name__ == "__main__":
    # Teste
    loader = DatabaseLoader()
    loader.load_all()
    
    # Testar explosão
    print("\n" + "="*80)
    print("TESTE DE EXPLOSÃO")
    print("="*80)
    
    for struct in ['B2F', 'ET4A', '1S4', 'N1']:
        print(f"\n{struct}:")
        materials = loader.explode_structure(struct)
        for mat in materials:
            print(f"  - {mat['code']} | {mat['desc']} | x{mat['qty']}")

