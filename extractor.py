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
        Analisa a página para identificar palavras em caixas (NOVO) ou tachadas (REMOVER).
        """
        words = page.extract_words()
        rects = page.rects  
        lines = page.lines  
        
        # Tentar reconstruir retângulos a partir de linhas se rects estiver vazio
        rect_zones = []
        for r in rects:
            rect_zones.append({'x0': r['x0'], 'top': r['top'], 'x1': r['x1'], 'bottom': r['bottom']})
            
        if not rect_zones and lines:
            # Heurística simples: linhas horizontais e verticais próximas
            for line in lines:
                # Se for uma linha de borda de tabela ou caixa, costuma ter espessura ou ser longa
                pass # Implementação complexa, manteremos foco nos rects por ora
        
        for word in words:
            word_key = (page_num, round(word['x0'], 1), round(word['top'], 1), round(word['x1'], 1), round(word['bottom'], 1))
            state = 'EXISTING' 
            
            # 1. Verificar se está dentro de uma CAIXA (NOVO)
            # Aumentamos a margem de tolerância (tol)
            tol = 3
            for r in rect_zones:
                if (r['x0'] - tol <= word['x0'] <= r['x1'] + tol and 
                    r['top'] - tol <= word['top'] <= r['bottom'] + tol):
                    state = 'NEW'
                    break
            
            # 2. Se não for novo, verificar se é REMOÇÃO (strikethrough)
            if state == 'EXISTING':
                for line in lines:
                    if abs(line['top'] - line['bottom']) < 3: # Linha horizontal
                        # Se a linha cruza o centro vertical da palavra
                        mid_y = (word['top'] + word['bottom']) / 2
                        if abs(line['top'] - mid_y) < 4:
                            # E está dentro dos limites horizontais
                            if not (line['x1'] < word['x0'] or line['x0'] > word['x1']):
                                state = 'REMOVAL'
                                break
            
            self.visual_states[word_key] = state

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
        Identifica postes e associa estruturas, agora filtrando por estado visual.
        Retorna: {'P1': {'Pole': '', 'Est': ['N1', 'U3'], 'Trafo': None, ...}, ...}
        """
        # Precisamos trabalhar com as palavras e suas coordenadas para manter o estado visual
        pole_map = {}
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                # 0. Analisar visuais da página (RETOS e LINHAS)
                self._analyze_page_visuals(page, i)
                
                words = page.extract_words()
                # Sort words by top then x0
                words.sort(key=lambda w: (w['top'], w['x0']))
                
                current_pid = None
                p_x, p_y = 0, 0
                
                # Regex para Poste: P1, P-1, P.1, POSTE 1
                p_regex = re.compile(r'^(P[\.\-]?\d+|POSTE?\s*\d+)$')
                # Regex para Tipo de Poste: C12/600, DT11/300, etc.
                t_regex = re.compile(r'^([A-Z]{1,2}\d{2}[xX/ \-]\d{3,4})$')
                # Estruturas padrão: N1, B2, U3, 1S3, BR1579, ET4A etc.
                s_regex = re.compile(r'^([A-Z]{1,2}\d+[A-Z0-9]*|ET\d+[A-Z]*|[1-4]S\d|BR\d+)$')

                for j, word in enumerate(words):
                    raw_text = word['text'].strip().upper()
                    # Fragmentar por vírgula para lidar com "U3,1S3(1)"
                    fragments = re.split(r'[,\s]+', raw_text) # Removi a barra / da fragmentação para não quebrar C12/600
                    
                    w_key = (i, round(word['x0'], 1), round(word['top'], 1), round(word['x1'], 1), round(word['bottom'], 1))
                    state = self.visual_states.get(w_key, 'EXISTING')

                    for text in fragments:
                        text = text.replace('(', '').replace(')', '').strip()
                        if not text: continue
                        
                        # 1. Detectar Poste (PID)
                        if p_regex.match(text):
                            if word['top'] > 50: 
                                current_pid = text
                                if current_pid not in pole_map:
                                    pole_map[current_pid] = {'Pole': 'Desconhecido', 'Est': [], 'Trafo': None, 'Chave': None, 'IsNew': (state == 'NEW')}
                                    p_x, p_y = word['x0'], word['top']
                                if state == 'NEW': pole_map[current_pid]['IsNew'] = True

                        # 2. Detectar Tipo (Âncora alternativa se PID estiver longe)
                        elif t_regex.match(text):
                            found_type = text.replace('X', '/').replace('x', '/').replace(' ', '').replace('-', '/')
                            
                            # Tentar associar ao PID atual ou criar âncora por posição
                            if current_pid and abs(word['top'] - p_y) < 100:
                                pole_map[current_pid]['Pole'] = found_type
                                # NOVO CRITÉRIO: Se o TIPO estiver em caixa, o POSTE FÍSICO é novo
                                if state == 'NEW':
                                    pole_map[current_pid]['IsNew'] = True
                            else:
                                anchor_id = f"REF_{int(word['top'])}"
                                if anchor_id not in pole_map:
                                    pole_map[anchor_id] = {'Pole': found_type, 'Est': [], 'Trafo': None, 'Chave': None, 'IsNew': (state == 'NEW')}
                                current_pid = anchor_id
                                p_x, p_y = word['x0'], word['top']

                        # 3. Detectar Estrutura
                        elif s_regex.match(text):
                            if current_pid and abs(word['top'] - p_y) < 250:
                                if state == 'NEW':
                                    if text not in pole_map[current_pid]['Est']:
                                        pole_map[current_pid]['Est'].append(text)
                                elif state == 'REMOVAL':
                                    if f"{text}(R)" not in pole_map[current_pid]['Est']:
                                        pole_map[current_pid]['Est'].append(f"{text}(R)")

                        # 4. Hardware (Trafo)
                        elif current_pid and ("KVA" in text or "K.VA" in text):
                            kva_match = re.search(r'(\d+)', text)
                            if kva_match:
                                kva = kva_match.group(1)
                                tipo = "MONO" if int(kva) <= 25 else "TRI"
                                if state == 'NEW':
                                    pole_map[current_pid]['Trafo'] = f"{tipo}-{kva}kVA"
                                elif state == 'REMOVAL':
                                    pole_map[current_pid]['Trafo'] = f"{tipo}-{kva}kVA(R)"

        # Filtro Rigoroso Recalibrado
        cleaned_map = {}
        for p_id, data in pole_map.items():
            if p_id == "P1": continue 
            
            is_pole_new = data.get('IsNew', False)
            has_relevant_content = len(data['Est']) > 0 or data['Trafo']
            
            if is_pole_new or has_relevant_content:
                if not is_pole_new:
                    data['Pole'] = f"{data['Pole']}(E)" 
                
                if 'IsNew' in data: del data['IsNew']
                cleaned_map[p_id] = data
                
        return cleaned_map

    def find_cables(self):
        """Extrai cabos e suas metragens, priorizando a descrição completa."""
        cables_found = []
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                # 0. Analisar visuais da página
                self._analyze_page_visuals(page, i)
                
                words = page.extract_words()
                # Reconstruir linhas para busca de metragem
                lines_data = {}
                for w in words:
                    y = round(w['top'], 0)
                    if y not in lines_data: lines_data[y] = []
                    lines_data[y].append(w)
                
                for y in sorted(lines_data.keys()):
                    line_words = sorted(lines_data[y], key=lambda w: w['x0'])
                    line_text = " ".join([w['text'] for w in line_words]).upper()
                    
                    if ("MT" in line_text or "BT" in line_text) and ("M" in line_text or "METROS" in line_text):
                        # Identificar o ponto de início (MT/BT)
                        start_idx = -1
                        for j, word in enumerate(line_words):
                            if word['text'].upper() in ["MT", "BT"]:
                                start_idx = j; break
                        
                        if start_idx != -1:
                            target_word = line_words[start_idx]
                            w_key = (i, round(target_word['x0'], 1), round(target_word['top'], 1), round(target_word['x1'], 1), round(target_word['bottom'], 1))
                            state = self.visual_states.get(w_key, 'EXISTING')
                            
                            if state != 'EXISTING':
                                # Capturar tudo ate a metragem
                                remaining_text = " ".join([w['text'] for w in line_words[start_idx:]]).upper()
                                # Regex aprimorado: (MT ... ) (Qtd) M
                                match = re.search(r'((?:MT|BT).*?)\s+([\d,.]+)\s*M', remaining_text)
                                if match:
                                    desc = match.group(1).strip()
                                    raw_qty = match.group(2).replace(',', '.')
                                    try:
                                        qty = float(raw_qty)
                                        tipo = 'MT' if 'MT' in desc else 'BT'
                                        if state == 'REMOVAL':
                                            desc += " (RETIRADA)"
                                        cables_found.append({'Tipo': tipo, 'Desc': desc, 'Qtd': qty})
                                    except: pass
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
