import pdfplumber
import re
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Importar vocabulário dinâmico (se disponível)
try:
    from vocabulary import VocabularyManager, get_vocabulary
    HAS_VOCABULARY = True
except ImportError:
    HAS_VOCABULARY = False

# Importar validador (se disponível)
try:
    from validators import TechnicalValidator, ExtractionItem
    HAS_VALIDATOR = True
except ImportError:
    HAS_VALIDATOR = False


@dataclass
class ExtractionMetadata:
    """Metadados de rastreabilidade para cada item extraído"""
    page: int = 0
    bbox: Tuple[float, float, float, float] = field(default_factory=lambda: (0, 0, 0, 0))
    source_text: str = ""
    confidence: float = 1.0
    state: str = "NEW"  # NEW, EXISTING, REMOVAL
    
    def to_dict(self) -> Dict:
        return {
            'page': self.page,
            'bbox': self.bbox,
            'source_text': self.source_text,
            'confidence': self.confidence,
            'state': self.state
        }


class ProjectExtractor:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.text = ""
        # Cache de estados visuais por palavra: {(page_num, x0, y0, x1, y1): 'NEW'|'REMOVAL'|'EXISTING'}
        self.visual_states = {}
        
        # Vocabulário dinâmico para normalização
        self.vocabulary = get_vocabulary() if HAS_VOCABULARY else None
        
        # Log de extração com rastreabilidade
        self.extraction_log: List[Dict] = []
        
        # Equipamentos extraídos
        self.equipments: List[Dict] = []
        
        # Metadados por item
        self.metadata_cache: Dict[str, ExtractionMetadata] = {}

    def extract_text(self):
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                full_text = []
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text:
                        full_text.append(page_text)
                    
                    # Analisar estados visuais da página
                    self._analyze_page_visuals(page, i)
                
                self.text = "\n".join(full_text)
            return self.text
        except Exception as e:
            return f"Erro ao ler PDF: {e}"

    def _analyze_page_visuals(self, page, page_num):
        """
        Extrai zonas de RETÂNGULOS (caixas) e LINHAS (tachados).
        Retorna (rect_zones, lines).
        """
        rect_zones = []
        for r in page.rects:
            rect_zones.append({
                'x0': r['x0'], 'top': r['top'], 'x1': r['x1'], 'bottom': r['bottom']
            })
            
        lines = []
        for l in page.lines:
            lines.append({
                'x0': l['x0'], 'top': l['top'], 'x1': l['x1'], 'bottom': l['bottom']
            })
            
        return rect_zones, lines

    def get_word_state(self, word_text, search_area_text):
        """
        Tenta encontrar o estado visual de uma palavra específica no texto global.
        Como o extract_text perde a coordenada exata às vezes na busca via Regex,
        esta é uma aproximação baseada na primeira ocorrência encontrada com aquele texto.
        """
        # Heurística simples: busca o estado da palavra no dicionário visual_states
        for (p, x0, y0, x1, y1), state in self.visual_states.items():
            # Nota: Isso pode falhar se houver a mesma palavra com estados diferentes.
            # Idealmente o Regex deveria trabalhar com objetos 'word' do pdfplumber.
            pass
        return 'NEW' # Placeholder para o refatoramento abaixo

    def extract_project_info(self):
        """Tenta extrair informações de cabeçalho prioritariamente DIAGRAMA."""
        info = {'Ordem': ''}
        
        # 1. Tentar encontrar "DIAGRAMA <números>"
        match_diagram = re.search(r'DIAGRAMA\s*[:.-]*\s*(\d{8,14})', self.text, re.IGNORECASE)
        if match_diagram:
            info['Ordem'] = match_diagram.group(1)
        else:
            # 2. Fallback: procurar sequência de 10-12 dígitos isolada (padrão antigo)
            match_generic = re.search(r'(?<!\d)(\d{10,12})(?!\d)', self.text)
            if match_generic:
                info['Ordem'] = match_generic.group(1)
                
        return info

    def find_structures_per_pole(self):
        """
        Identifica postes e associa estruturas usando proximidade de centroide e reconstrução espacial.
        """
        self.last_pole_map = {}
        pole_map = self.last_pole_map
        self.last_labeled_items = []
        labeled_items = self.last_labeled_items
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                rect_zones, lines = self._analyze_page_visuals(page, i)
                raw_words = page.extract_words()
                
                # RECONSTRUÇÃO ESPACIAL: Agrupar caracteres fragmentados
                words = []
                if raw_words:
                    # Pré-processar estados visuais dos fragmentos
                    raw_words.sort(key=lambda w: (w['top'], w['x0']))
                    current_word = raw_words[0].copy()
                    
                    # Heurística de estado inicial do fragmento
                    def get_frag_state(w):
                        for r in rect_zones:
                            if (r['x1'] - r['x0'] > 300 or r['bottom'] - r['top'] > 60): continue
                            if (r['x0'] - 2.0 <= w['x0'] <= r['x1'] + 2.0 and r['top'] - 2.0 <= w['top'] <= r['bottom'] + 2.0):
                                return 'NEW'
                        for l in lines:
                            if abs(l['top'] - l['bottom']) < 3 and abs(l['top'] - (w['top']+w['bottom'])/2) < 5:
                                if not (l['x1'] < w['x0'] or l['x0'] > w['x1']): return 'REMOVAL'
                        return 'EXISTING'

                    current_word['state'] = get_frag_state(current_word)
                    
                    for next_w in raw_words[1:]:
                        # Mesma região de linha e proximidade horizontal (somente se estiver à direita)
                        # Aumentei a tolerância vertical, mas a horizontal deve ser para a direita
                        dist_x = next_w['x0'] - current_word['x1']
                        if abs(next_w['top'] - current_word['top']) < 10 and -2 <= dist_x < 12:
                            # Se for vírgula decimal, não adiciona espaço
                            is_decimal = (next_w['text'] == ',' or current_word['text'].endswith(',')) and re.match(r'\d', next_w['text'] or current_word['text'][-1:])
                            if dist_x > 1 and not is_decimal:
                                current_word['text'] += " "
                            current_word['text'] += next_w['text']
                            current_word['x1'] = next_w['x1']
                            current_word['bottom'] = max(current_word['bottom'], next_w['bottom'])
                            
                            # Herança de estado
                            ns = get_frag_state(next_w)
                            if ns == 'REMOVAL' or current_word['state'] == 'REMOVAL':
                                current_word['state'] = 'REMOVAL'
                            elif ns == 'NEW' or current_word['state'] == 'NEW':
                                current_word['state'] = 'NEW'
                        else:
                            current_word['text'] = current_word['text'].replace('(CID:13)', '').replace('(CID:3)', '').strip()
                            words.append(current_word)
                            current_word = next_w.copy()
                            current_word['state'] = get_frag_state(current_word)
                    words.append(current_word)
                
                # Regex patterns aprimorados (case-insensitive)
                # p_regex: Captura ID do poste em qualquer parte do texto aglutinado
                p_regex = re.compile(r'\b(P[\.\-]?\d+|POSTE?\s*\d+)\b', re.I)
                # t_regex: De C12x1000 até C11x300. 
                t_regex = re.compile(r'^([A-Z]{1,2}\d{1,2}[xX/ \-]\d{3,4})', re.I)
                # s_regex: Estruturas
                s_regex = re.compile(r'^([A-Z]{1,2}\d+[A-Z0-9]*|[1-4]S\d|ET\d+[A-Z]*|BR\d+)', re.I)
                # trafo_regex: Captura padrões como 112,5KVA ou 3Ø 112.5kVA. 
                # Suporta decimais com vírgula ou ponto e o prefixo 3Ø.
                trafo_regex = re.compile(r'(?:3\s*Ø\s*)?(\d+[,.]?\d*)\s*KVA', re.I)

                for word in words:
                    # Limpar ruídos comuns
                    text_clean = word['text'].upper().strip()
                    raw_text = re.sub(r'(\d+)\s*([,.]?)\s*(\d+)\s*KVA', r'\1\2\3KVA', text_clean)
                    # print(f"DEBUG: Processing Word -> '{raw_text}'")
                    
                    center = ((word['x0'] + word['x1'])/2, (word['top'] + word['bottom'])/2)
                    state = word['state']
                    
                    # Detecção de Poste (mais tolerante)
                    p_match = p_regex.search(raw_text)
                    if p_match:
                        p_id = p_match.group(1).strip().upper()
                        if word['top'] > 50:
                            print(f"DEBUG: Poste Detectado -> {p_id} em {center} | TEXT: '{raw_text}'")
                            pole_map[p_id] = {
                                'id': p_id,
                                'pos': center,
                                'Pole': 'Desconhecido',
                                'Est': [],
                                'Trafo': None,
                                'IsNew': (state == 'NEW'),
                                'IsNewContent': False
                            }
                    else:
                        # Processar como label técnico
                        safe_text = re.sub(r'(\d),(\d)', r'\1DOT\2', raw_text)
                        for text in re.split(r'[,;]+', safe_text):
                            text = text.replace('DOT', ',').strip()
                            if not text: continue
                            
                            labeled_items.append({
                                'text': text, 'pos': center, 'state': state,
                                'type': 'TYPE' if t_regex.match(text) else (
                                    'TRAFO' if trafo_regex.search(text) else (
                                        'EST' if s_regex.match(text) else None
                                    )
                                )
                            })
                            if t_regex.match(text) and len(text) > 8:
                                for sub in re.split(r'[,; ]+', text)[1:]:
                                    if s_regex.match(sub):
                                        labeled_items.append({'text': sub, 'pos': center, 'state': state, 'type': 'EST'})

        # Associação por Proximidade (Nearest Neighbor)
        for item in labeled_items:
            if not item['type'] or not pole_map: continue
            
            # Encontrar poste mais próximo
            best_p = None
            min_dist = 999999
            
            for p_id, p_data in pole_map.items():
                # Distância Euclidiana entre centros
                dx = item['pos'][0] - p_data['pos'][0]
                dy = item['pos'][1] - p_data['pos'][1]
                dist = math.sqrt(dx**2 + dy**2)
                
                # Raio de busca generoso (600px) para acomodar labels muito afastadas em projetos A0/A1
                if dist < min_dist and dist < 600: 
                    min_dist = dist
                    best_p = p_id
            
            if best_p:
                p_data = pole_map[best_p]
                state = item['state']
                text = item['text']
                
                # Regra Crucial: Só incluímos no mapa o que for "NEW" (instalação)
                # No entanto, se o TIPO de poste for detectado, associamos mesmo sendo EXISTING
                # para servir de referência, mas a lógica de limpeza no final filtrará.
                
                if item['type'] == 'TYPE':
                    norm_type = text.replace('X', '/').replace('x', '/').replace(' ', '').replace('-', '/')
                    # Prioridade: NEW > REMOVAL > EXISTING
                    # Se já temos um tipo NEW, não sobrescrevemos com REMOVAL
                    current_is_new = p_data.get('IsTypeNew', False)
                    if state == 'NEW':
                        p_data['Pole'] = norm_type
                        p_data['IsTypeNew'] = True
                        p_data['IsNewContent'] = True
                    elif state == 'REMOVAL' and not current_is_new:
                        p_data['Pole'] = f"{norm_type}(R)"
                        # Omitimos IsNewContent = True para remoções
                    elif not current_is_new and (p_data['Pole'] == 'Desconhecido' or '(R)' in p_data['Pole']):
                         # Se for EXISTING e não tivermos nada melhor
                         if '(R)' not in p_data['Pole']:
                             p_data['Pole'] = norm_type

                elif item['type'] == 'EST':
                    est_matches = re.findall(r'([A-Z]{1,2}\d+[A-Z0-9]*)', text)
                    for est_code in (est_matches if est_matches else [text]):
                        norm_text = self.normalize_term(est_code)
                        if state == 'NEW':
                            p_data['IsNewContent'] = True
                            if norm_text not in p_data['Est']:
                                p_data['Est'].append(norm_text)
                        # Ignoramos (R) e (E) da lista UI para evitar confusão do usuário

                elif item['type'] == 'TRAFO':
                    is_trifasico = "3Ø" in text or "TRI" in text or "3" in text.split("Ø")[0] if "Ø" in text else False
                    is_bifasico = "2Ø" in text or "BI" in text or "2" in text.split("Ø")[0] if "Ø" in text else False
                    kva_match = trafo_regex.search(text)
                    if kva_match:
                        kva = kva_match.group(1).replace(',', '.')
                        prefix = "TRI" if is_trifasico else ("BI" if is_bifasico else ("MONO" if float(kva) <= 37.5 else "TRI"))
                        desc = f"{prefix}-{kva}kVA"
                        if state == 'NEW':
                            p_data['Trafo'] = desc
                            p_data['IsNewContent'] = True
                        # Remover else para (R) -> Trafo de remoção não deve poluir o UI se o foco for instalação

        # Limpeza final: Apenas postes novos ou com conteúdo novo
        cleaned_map = {}
        for p_id, data in pole_map.items():
            is_new_pole = data.get('IsNew', False)
            is_type_new = data.get('IsTypeNew', False)
            has_new_content = data.get('IsNewContent', False)
            
            if is_new_pole or has_new_content:
                # Se o poste ou o tipo for novo, não marcamos com (E)
                if not is_new_pole and not is_type_new:
                    # Se chegamos aqui e Pole não é Desconhecido, ele é existente com conteúdo novo
                    if data['Pole'] != 'Desconhecido':
                        data['Pole'] = f"{data['Pole']}(E)"
                
                # Remover metadados internos de processamento
                items_to_del = ['pos', 'id', 'IsNew', 'IsNewContent', 'IsTypeNew', 'state']
                for k in items_to_del:
                    if k in data: del data[k]
                    
                cleaned_map[p_id] = data
                
        return cleaned_map

    def find_cables(self):
        """Extrai cabos e suas metragens, priorizando a descrição completa."""
        cables_found = []
        print("--- DEBUG: INICIANDO FIND_CABLES (V3) ---")
        
        keywords = ["MT", "BT", "CABO", "FIO", "COND", "AL", "COBRE", "MULTIPLEX", "NU"]
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                # 0. Analisar visuais da página
                self._analyze_page_visuals(page, i)
                
                words = page.extract_words()
                # Reconstruir linhas com tolerância vertical (3px) para corrigir desalinhamentos
                lines_data = {}
                # Ordenar por TOP para facilitar agrupamento
                sorted_words_p = sorted(words, key=lambda w: w['top'])
                
                for w in sorted_words_p:
                    # Tentar encontrar uma linha existente próxima
                    placed = False
                    for y_key in list(lines_data.keys()):
                        if abs(w['top'] - y_key) <= 3.0: # Tolerância de 3 pontos
                            lines_data[y_key].append(w)
                            placed = True
                            break
                    if not placed:
                        lines_data[w['top']] = [w]
                
                for y in sorted(lines_data.keys()):
                    # Ordenar palavras da linha por X0
                    line_words = sorted(lines_data[y], key=lambda w: w['x0'])
                    line_text = " ".join([w['text'] for w in line_words]).upper()
                    
                    # Verificação Otimista: Tem alguma palavra chave?
                    has_keyword = any(k in line_text for k in keywords)
                    has_meter = "M" in line_text or "METROS" in line_text
                    
                    if has_keyword and has_meter:
                         # Tentativa 1: Regex com Prefixo MT/BT
                         match = re.search(r'((?:MT|BT).*?)\s+([\d,.]+)\s*(?:M|METROS)\b', line_text)
                         
                         # Tentativa 2: Regex Genérico (Captura tudo até a quantidade)
                         if not match:
                             match = re.search(r'(.*?)\s+([\d,.]+)\s*(?:M|METROS)\b', line_text)
                             
                         if match:
                            desc = match.group(1).strip()
                            raw_qty = match.group(2).replace(',', '.')
                            try:
                                qty = float(raw_qty)
                                
                                # SANITY CHECK: Ignorar valores absurdos (provavelmente coordenadas UTM)
                                if qty > 10000:
                                    continue
                                
                                # Inferir Tipo
                                if "MT" in desc or "15KV" in desc or "25KV" in desc:
                                    tipo = 'MT'
                                else:
                                    tipo = 'BT'
                                    
                                # Verificar estado visual (primeira palavra)
                                first_word = line_words[0]
                                w_key = (i, round(first_word['x0'], 1), round(first_word['top'], 1), round(first_word['x1'], 1), round(first_word['bottom'], 1))
                                # Como o estado é aproximado, vamos confiar no 'NEW' se o texto for novo
                                # Mas se a linha toda for existing, marcamos existing
                                
                                desc_final = desc
                                cables_found.append({'Tipo': tipo, 'Desc': desc_final, 'Qtd': qty})
                            except Exception as e:
                                pass
        return cables_found
        return cables_found
        return cables_found

    def get_summary_structures(self, pole_map):
        """Quantifica total de estruturas para o resumo inicial."""
        summary = {}
        for p_data in pole_map.values():
            for est in p_data['Est']:
                summary[est] = summary.get(est, 0) + 1
        return summary

    # ═══════════════════════════════════════════════════════════════════════════
    # NOVOS MÉTODOS - Agente IA Engenharia Elétrica
    # ═══════════════════════════════════════════════════════════════════════════
    
    def extract_equipment(self) -> List[Dict]:
        """
        Extrai equipamentos: chaves, religadores, para-raios, aterramentos.
        Retorna lista com metadados de rastreabilidade.
        """
        equipments = []
        
        # Regex para equipamentos comuns
        patterns = {
            'chave_seccionadora': r'(?:CHAVE|CH)[.\s-]?(?:FACA|SECCIONA|TRIPOLAR|SECCION)',
            'religador': r'RELIGADOR|RECLOSER',
            'para_raios': r'(?:PARA|PÁRA)[.-]?RAIOS?|P/?R\b',
            'aterramento': r'ATERRAMENTO|AT(?:ERR)?\.?\s*(?:TEMP|PERM)?',
            'capacitor': r'CAPACITOR|BANCO\s*CAP',
            'regulador': r'REGULADOR|REG\.?\s*TENS',
        }
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                words = page.extract_words()
                
                # Reconstruir texto por linhas
                lines_data = {}
                for w in words:
                    y = round(w['top'], 0)
                    if y not in lines_data:
                        lines_data[y] = []
                    lines_data[y].append(w)
                
                for y in sorted(lines_data.keys()):
                    line_words = sorted(lines_data[y], key=lambda w: w['x0'])
                    line_text = " ".join([w['text'] for w in line_words]).upper()
                    
                    for equip_type, pattern in patterns.items():
                        if re.search(pattern, line_text, re.IGNORECASE):
                            # Verificar estado visual
                            first_word = line_words[0] if line_words else None
                            state = 'EXISTING'
                            bbox = (0, 0, 0, 0)
                            
                            if first_word:
                                w_key = (page_num, round(first_word['x0'], 1), 
                                        round(first_word['top'], 1),
                                        round(first_word['x1'], 1), 
                                        round(first_word['bottom'], 1))
                                state = self.visual_states.get(w_key, 'EXISTING')
                                bbox = (first_word['x0'], first_word['top'],
                                       line_words[-1]['x1'], first_word['bottom'])
                            
                            # Só incluir novos ou em remoção
                            if state != 'EXISTING':
                                # Tentar extrair quantidade
                                qty_match = re.search(r'(\d+)\s*(?:UN|PÇ|PC)', line_text)
                                qty = int(qty_match.group(1)) if qty_match else 1
                                
                                # Normalizar com vocabulário
                                normalized_type = equip_type
                                if self.vocabulary:
                                    normalized_type = self.vocabulary.normalize(equip_type)
                                
                                equip = {
                                    'type': normalized_type,
                                    'description': line_text.strip(),
                                    'qty': qty,
                                    'state': state,
                                    'metadata': ExtractionMetadata(
                                        page=page_num + 1,
                                        bbox=bbox,
                                        source_text=line_text,
                                        confidence=0.8 if qty_match else 0.6,
                                        state=state
                                    ).to_dict()
                                }
                                equipments.append(equip)
                                
                                # Log de extração
                                self._log_extraction('equipment', equip_type, line_text, page_num + 1)
        
        self.equipments = equipments
        return equipments
    
    def extract_with_metadata(self) -> Dict:
        """
        Extração completa com metadados de rastreabilidade.
        Retorna dicionário com pole_map, cables, equipments e metadata.
        """
        # Extrair texto primeiro
        self.extract_text()
        
        # Extrair componentes
        pole_map = self.find_structures_per_pole()
        cables = self.find_cables()
        equipments = self.extract_equipment()
        
        # Construir resultado com metadados
        result = {
            'pole_map': pole_map,
            'cables': cables,
            'equipments': equipments,
            'extraction_log': self.extraction_log,
            'summary': {
                'total_poles': len(pole_map),
                'total_structures': sum(len(p['Est']) for p in pole_map.values()),
                'total_cables': len(cables),
                'total_equipments': len(equipments),
            }
        }
        
        # Validação técnica (se disponível)
        if HAS_VALIDATOR:
            validator = TechnicalValidator()
            issues = validator.validate(result)
            result['validation'] = validator.get_summary()
        
        return result
    
    def validate_extraction(self, extraction: Dict = None) -> Dict:
        """
        Executa validação técnica na extração.
        
        Args:
            extraction: Resultado de extract_with_metadata() ou None para nova extração
            
        Returns:
            Dicionário com issues de validação
        """
        if extraction is None:
            extraction = self.extract_with_metadata()
        
        if not HAS_VALIDATOR:
            return {'error': 'Módulo validators.py não disponível'}
        
        validator = TechnicalValidator()
        issues = validator.validate(extraction)
        return validator.get_summary()
    
    def get_low_confidence_items(self, threshold: float = 0.7) -> List[Dict]:
        """
        Retorna itens com score de confiança abaixo do threshold.
        Útil para revisão manual.
        
        Args:
            threshold: Score mínimo de confiança (default 0.7)
            
        Returns:
            Lista de itens de baixa confiança
        """
        low_confidence = []
        
        for equip in self.equipments:
            metadata = equip.get('metadata', {})
            if metadata.get('confidence', 1.0) < threshold:
                low_confidence.append({
                    'type': 'equipment',
                    'value': equip.get('type'),
                    'description': equip.get('description'),
                    'confidence': metadata.get('confidence'),
                    'page': metadata.get('page'),
                    'suggestion': 'Verificar manualmente no PDF'
                })
        
        return low_confidence
    
    def _log_extraction(self, item_type: str, value: str, source: str, page: int):
        """Adiciona entrada ao log de extração para rastreabilidade"""
        self.extraction_log.append({
            'type': item_type,
            'value': value,
            'source_text': source[:100],  # Limitar tamanho
            'page': page,
            'timestamp': None  # Pode ser preenchido se necessário
        })
    
    def normalize_term(self, term: str) -> str:
        """
        Normaliza um termo usando o vocabulário dinâmico.
        
        Args:
            term: Termo original
            
        Returns:
            Termo normalizado
        """
        if self.vocabulary:
            return self.vocabulary.normalize(term)
        return term
    
    def get_extraction_report(self) -> str:
        """
        Gera relatório em Markdown da extração.
        
        Returns:
            String com relatório formatado
        """
        extraction = self.extract_with_metadata()
        
        lines = [
            "# Relatório de Extração",
            "",
            "## Resumo",
            f"- **Postes:** {extraction['summary']['total_poles']}",
            f"- **Estruturas:** {extraction['summary']['total_structures']}",
            f"- **Cabos:** {extraction['summary']['total_cables']}",
            f"- **Equipamentos:** {extraction['summary']['total_equipments']}",
            "",
        ]
        
        # Validação
        if 'validation' in extraction:
            val = extraction['validation']
            lines.extend([
                "## Validação Técnica",
                f"- Erros: {val.get('errors', 0)}",
                f"- Avisos: {val.get('warnings', 0)}",
                f"- Informações: {val.get('infos', 0)}",
                "",
            ])
            
            if val.get('issues'):
                lines.append("### Issues Encontradas")
                for issue in val['issues']:
                    severity = issue.get('severity', 'info').upper()
                    lines.append(f"- [{severity}] {issue.get('message')}")
                lines.append("")
        
        # Itens de baixa confiança
        low_conf = self.get_low_confidence_items()
        if low_conf:
            lines.extend([
                "## Itens para Revisão Manual",
                ""
            ])
            for item in low_conf:
                lines.append(f"- **{item['type']}**: {item['value']} (confiança: {item['confidence']:.1%})")
            lines.append("")
        
        return "\n".join(lines)
