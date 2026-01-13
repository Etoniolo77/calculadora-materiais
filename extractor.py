import pdfplumber
import re
import math

class ProjectExtractor:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.text = ""
        self.strikethrough_text = ""  # Texto tachado (material existente)

    def extract_text(self):
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                full_text = []
                strikethrough_parts = []
                
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        full_text.append(page_text)
                    
                    # Detectar texto tachado
                    strikethrough_parts.extend(self._detect_strikethrough(page))
                
                self.text = "\n".join(full_text)
                self.strikethrough_text = " ".join(strikethrough_parts)
            return self.text
        except Exception as e:
            return f"Erro ao ler PDF: {e}"
    
    def _detect_strikethrough(self, page):
        """
        Detecta palavras tachadas (strikethrough) na página.
        Retorna lista de palavras tachadas.
        """
        strikethrough_words = []
        
        try:
            words = page.extract_words()
            lines = page.lines
            
            for word in words:
                # Verificar se há linhas horizontais cruzando a palavra
                word_middle_y = (word['top'] + word['bottom']) / 2
                
                for line in lines:
                    # Linha horizontal (top ~= bottom)
                    if abs(line['top'] - line['bottom']) < 2:
                        # Linha no meio da palavra (strikethrough)
                        if word['top'] < line['top'] < word['bottom']:
                            # Linha cruza horizontalmente
                            if not (line['x1'] < word['x0'] or line['x0'] > word['x1']):
                                strikethrough_words.append(word['text'])
                                break  # Já encontrou, não precisa checar mais linhas
        except:
            pass  # Se falhar, continua sem strikethrough detection
        
        return strikethrough_words

    def extract_project_info(self):
        """Tenta extrair informações de cabeçalho como Código do Projeto."""
        info = {'Ordem': ''}
        # Padrão para código de 10 digitos geralmente
        match = re.search(r'(\d{10})', self.text)
        if match:
            info['Ordem'] = match.group(1)
        return info

    def extract_gps_distances(self):
        """
        Extrai coordenadas GPS (P1- X Y) e calcula distancias entre postes sequenciais.
        Retorna lista de vãos: [{'De': 'P1', 'Para': 'P2', 'Dist': 35.5}, ...]
        """
        # Padrão: P1- 335827.8 m 7763508.0 m
        gps_pattern = r'(P\d+)[-\s]+(\d{6,7}[.,]\d)\s*m\s+(\d{7,8}[.,]\d)\s*m'
        matches = re.findall(gps_pattern, self.text)
        
        coords = {}
        for pid, x, y in matches:
            xf = float(x.replace(',', '.'))
            yf = float(y.replace(',', '.'))
            coords[pid] = (xf, yf)
            
        spans = []
        # Ordenar chaves P1, P2...
        sorted_pids = sorted(coords.keys(), key=lambda k: int(k.replace('P', '')))
        
        for i in range(len(sorted_pids) - 1):
            p_curr = sorted_pids[i]
            p_next = sorted_pids[i+1]
            
            x1, y1 = coords[p_curr]
            x2, y2 = coords[p_next]
            
            # Distancia Euclidiana
            dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            spans.append({'De': p_curr, 'Para': p_next, 'Dist': round(dist, 2)})
            
        return spans

    def find_structures_per_pole(self):
        """
        Tenta associar estruturas a cada poste (P1, P2...).
        Retorna: {'P1': {'Pole': '', 'Est': ['N1', 'U3'], 'Trafo': None, ...}, ...}
        """
        if not self.text:
            return {}

        # Limpar texto mas MANTER newlines para detectar P2\nC12x1000
        clean_text = self.text.replace('\\', ' ').replace('/', ' ')
        # NÃO fazer .replace('\n', ' ') aqui!
        
        # PASSO 1: Pular seção GPS
        # A seção GPS contém "P1- coordenadas" e termina antes dos dados reais
        # Buscar por "SIRGAS" ou similar e pular até encontrar P1 com tipo de poste
        data_start = 0
        gps_marker = clean_text.find("SIRGAS")
        if gps_marker > 0:
            # Procurar próximo P1 após GPS (com margem de segurança)
            search_start = clean_text.find("P1", gps_marker + 200)
            if search_start > 0:
                data_start = search_start
        
        search_text = clean_text[data_start:]
        
        # PASSO 2: Buscar por ANCHOR COMPOSTO: P# seguido de TipoPoste
        # Padrão flexível: P2 ... (até 200 chars) ... C12x1000
        # Melhora: Capturar componentes separadamente para tolerar espaços
        # Grupo 1 (PID), Grupo 2 (Tipo), Grupo 3 (Altura), Grupo 4 (Esforço)
        pole_anchor_pattern = r'(P\d+)[\s\S]{0,200}?([A-Z]{1,2})\s*(\d{2})\s*[xX ]\s*(\d{3,4})'
        matches = list(re.finditer(pole_anchor_pattern, search_text))
        
        if not matches:
            # Fallback: se não encontrou com padrão completo, tenta busca simples
            # mas validando conteúdo depois
            return {}
        
        pole_map = {}
        
        # PASSO 3: Para cada anchor, extrair bloco até próximo poste
        for i, match in enumerate(matches):
            p_id = match.group(1)  # P1, P2, etc.
            
            # Reconstruir tipo normalizado: "C" + "12" + "/" + "600" -> "C12/600"
            p_type = f"{match.group(2)}{match.group(3)}/{match.group(4)}"
            
            # Normalizar DI -> DT se necessário (mas manter DI se for o real)
            # Na verdade, vamos respeitar o que vier
            
            block_start = match.start()
            block_end = matches[i+1].start() if i+1 < len(matches) else len(search_text)
            
            block_text = search_text[block_start:block_end]
            
            # PASSO 4: Extrair estruturas e hardware do bloco
            structures = self._extract_structures(block_text)
            hardware = self._extract_hardware(block_text)
            
            pole_map[p_id] = {
                'Pole': p_type,
                'Est': structures,
                **hardware,
                'Raw': block_text[:500]  # Debug
            }
        
        return pole_map
    
    def _extract_structures(self, text):
        """
        Extrai estruturas de um bloco de texto.
        Retorna lista de estruturas válidas.
        """
        structures = []
        
        # Padrão: U4, N1, 1S4, ET1T, etc.
        pattern = r'\b([A-Z]{1,2}\d[A-Z0-9]*|ET\d+[A-Z]*|[1-4]S\d)\b'
        
        # Blacklist - coisas que não são estruturas
        blacklist = {
            'MT', 'BT', 'KV', 'TF', 'VA', 'HV', 'LV', 'AC', 'DC',
            'P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9',
            'C1', 'C2', 'D1', 'D2', 'F1', 'F2', 'F3',
            'M1', 'M2', 'M3', 'H1', 'H2', 'H3', 'H4', 'H5',
            'DI', 'DT', 'FT', 'PT'  # Tipos de poste
        }
        
        for match in re.finditer(pattern, text):
            est = match.group(1)
            
            # Validações
            if len(est) < 2:
                continue
            if est in blacklist:
                continue
            
            # NOVO: Verificar se está em texto tachado (material existente)
            if self.strikethrough_text and est in self.strikethrough_text:
                continue  # Pular - material já existe
            
            # Adicionar se não duplicado
            if est not in structures:
                structures.append(est)
        
        return sorted(structures)
    
    def _extract_hardware(self, text):
        """
        Extrai hardware adicional: Trafo, Chave, Estai, etc.
        Retorna dicionário com os dados.
        """
        hardware = {
            'Trafo': None,
            'Chave': None,
            'Estai': {'Tipo': None, 'Qtd': 0},
            'Aterramento': {'Qtd': 0},
            'ParaRaio': None
        }
        
        # Transformador: buscar padrão kVA
        trafo_match = re.search(r'(\d+)\s*[kK]VA', text)
        if trafo_match:
            kva = trafo_match.group(1)
            # Determinar MONO ou TRI (heurística: <= 25 = MONO)
            tipo = "MONO" if int(kva) <= 25 else "TRI"
            hardware['Trafo'] = f"{tipo}-{kva}kVA"
        
        # Chave
        chave_match = re.search(r'(FUSIVEL|FACA|RELIGADORA|CHAVE)', text, re.IGNORECASE)
        if chave_match:
            hardware['Chave'] = chave_match.group(1).upper()
        
        # Estai (count)
        estai_matches = re.findall(r'(ESTAI|ANCORA|CC)', text, re.IGNORECASE)
        if estai_matches:
            hardware['Estai']['Qtd'] = len(estai_matches)
            hardware['Estai']['Tipo'] = estai_matches[0].upper()
        
        # Aterramento (count)
        aterr_matches = re.findall(r'(HASTE|ATERRAMENTO|MALHA)', text, re.IGNORECASE)
        hardware['Aterramento']['Qtd'] = len(aterr_matches)
        
        # Para-raio
        pr_match = re.search(r'(PARA-RAIO|DPS|PÁRA-RAIO)', text, re.IGNORECASE)
        if pr_match:
            hardware['ParaRaio'] = "Sim"
        
        return hardware

    def find_cables(self):
        """Extrai metragens de cabos do texto."""
        content = self.text.replace('\n', ' ')
        cables_found = []
        
        # Regex melhorado para capturar cabos no formato correto
        # MT 3x2ANA(4ANA) 24.9m ou BT 1x3x120(70)AX 24.26m
        # Padrão: (MT|BT) seguido de: números, x, letras, opcionalmente (numeros/letras), mais letras, espaço, metragem
        cable_pattern = r'((?:MT|BT)\s+[\d]+x[\d]+(?:x[\d]+)?(?:[A-Z]+)?(?:\([\d]+[A-Z]*\))?[A-Z]*)\s+([\d]+(?:[.,][\d]+)?)m'
        
        for match in re.finditer(cable_pattern, content, re.IGNORECASE):
            desc = match.group(1).strip()
            qty_str = match.group(2).replace(',', '.')
            qty = float(qty_str)
            
            tipo = 'MT' if 'MT' in desc.upper() else 'BT'
            
            cables_found.append({
                'Tipo': tipo,
                'Desc': desc,
                'Qtd': qty
            })
        
        return cables_found

    def get_summary_structures(self, pole_map):
        """Quantifica total de estruturas para o resumo inicial."""
        summary = {}
        for p_data in pole_map.values():
            for est in p_data['Est']:
                summary[est] = summary.get(est, 0) + 1
        return summary
