"""
=== PROPOSTA DE ALTERAÇÃO - extractor.py ===
Corrige: C1 (triple return), M4 (visual_states vazio), M5 (get_word_state placeholder)
Veja: RELATORIO_INCONSISTENCIAS.md para detalhes
"""
import pdfplumber
import re
import math
import json
import base64
import os
from collections import Counter
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
        # [FIX M4] Cache de estados visuais agora é POPULADO corretamente
        self.visual_states = {}
        
        # Vocabulário dinâmico para normalização
        self.vocabulary = get_vocabulary() if HAS_VOCABULARY else None
        
        # Log de extração com rastreabilidade
        self.extraction_log: List[Dict] = []

        # Equipamentos extraídos
        self.equipments: List[Dict] = []

        # Metadados por item
        self.metadata_cache: Dict[str, ExtractionMetadata] = {}

        # Cache texto → lista de estados (populado em _analyze_page_visuals)
        # Permite que get_word_state() filtre por texto real da palavra
        self._text_state_cache: Dict[str, List[str]] = {}

    def extract_text(self):
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                full_text = []
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text:
                        full_text.append(page_text)
                    
                    # [FIX M4] Analisar estados visuais e POPULAR o cache
                    self._analyze_page_visuals(page, i)
                
                self.text = "\n".join(full_text)
            return self.text
        except Exception as e:
            return f"Erro ao ler PDF: {e}"

    def _analyze_page_visuals(self, page, page_num):
        """
        [FIX M4] Agora POPULA self.visual_states com os estados visuais das palavras.
        Extrai zonas de RETÂNGULOS (caixas) e LINHAS (tachados), e classifica
        cada palavra do PDF como NEW, REMOVAL ou EXISTING.
        Retorna (rect_zones, lines) para uso em find_structures_per_pole().
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
        
        # [FIX M4] Popular visual_states com cada palavra da página
        words = page.extract_words()
        for w in words:
            w_key = (page_num, round(w['x0'], 1), round(w['top'], 1), 
                     round(w['x1'], 1), round(w['bottom'], 1))
            
            state = 'EXISTING'  # Default
            
            # Verificar se está dentro de um retângulo (NEW)
            for r in rect_zones:
                # Ignorar retângulos muito grandes (bordas de página)
                if (r['x1'] - r['x0'] > 300 or r['bottom'] - r['top'] > 60):
                    continue
                if (r['x0'] - 2.0 <= w['x0'] <= r['x1'] + 2.0 and 
                    r['top'] - 2.0 <= w['top'] <= r['bottom'] + 2.0):
                    state = 'NEW'
                    break
            
            # Verificar se está tachado por uma linha (REMOVAL)
            if state != 'NEW':
                for l in lines:
                    if (abs(l['top'] - l['bottom']) < 3 and 
                        abs(l['top'] - (w['top'] + w['bottom']) / 2) < 5):
                        if not (l['x1'] < w['x0'] or l['x0'] > w['x1']):
                            state = 'REMOVAL'
                            break
            
            self.visual_states[w_key] = state

            # Popular cache texto→estado para get_word_state()
            txt_key = w['text'].strip().upper()
            if txt_key:
                self._text_state_cache.setdefault(txt_key, []).append(state)

        return rect_zones, lines

    def get_word_state(self, word_text: str, search_area_text: str = "") -> str:
        """
        Retorna o estado visual (NEW / EXISTING / REMOVAL) de uma palavra.

        Prioridade de lookup:
        1. Correspondência exata no _text_state_cache (texto → lista de estados).
        2. Correspondência parcial: alguma chave do cache CONTÉM word_text.
        3. Fallback: EXISTING (sem evidência visual).

        O estado retornado é o mais frequente entre as ocorrências encontradas.
        """
        if not self._text_state_cache:
            return 'EXISTING'

        from collections import Counter

        key = word_text.strip().upper()
        if not key:
            return 'EXISTING'

        # 1. Correspondência exata
        if key in self._text_state_cache:
            counts = Counter(self._text_state_cache[key])
            return counts.most_common(1)[0][0]

        # 2. Correspondência parcial (word_text contido em alguma chave do cache)
        matching_states = []
        for cached_text, states in self._text_state_cache.items():
            if key in cached_text or cached_text in key:
                matching_states.extend(states)

        if matching_states:
            counts = Counter(matching_states)
            return counts.most_common(1)[0][0]

        return 'EXISTING'

    def extract_project_info(self):
        """Tenta extrair informações de cabeçalho prioritariamente DIAGRAMA."""
        info = {'Ordem': ''}
        
        match_diagram = re.search(r'DIAGRAMA\s*[:.-]*\s*(\d{8,14})', self.text, re.IGNORECASE)
        if match_diagram:
            info['Ordem'] = match_diagram.group(1)
        else:
            match_generic = re.search(r'(?<!\d)(\d{10,12})(?!\d)', self.text)
            if match_generic:
                info['Ordem'] = match_generic.group(1)
                
        return info

    # ─── RULE-009/010: Extração por Caixas (PDFs sem prefixo P) ──────────────

    # Regex para tipo de poste dentro de caixa: ex '12/300', '11/300DT', '12/1000-BCT'
    _BOX_TYPE_REGEX = re.compile(
        r'(\d{1,2})[/xX](\d{3,4})[\s\-]?(DT|RT|FIBRA|BCT|F)?', re.I
    )
    # Regex para estrutura: N3F, N4F, B2, ET4A etc.
    _BOX_EST_REGEX  = re.compile(
        r'^([A-Z]{1,2}\d+[A-Z0-9]*)$', re.I
    )
    # Regex para estruturas secundárias: 1-S3(1), 2-S4(1), 1S3(1)
    _BOX_SEC_REGEX  = re.compile(
        r'(\d+)[\s\-]*([A-Z]{1,2}\d+[A-Z0-9]*)(?:\((\d+)\))?', re.I
    )
    # Regex KVA para transformadores dentro de caixa
    _BOX_TRAFO_REGEX= re.compile(r'(\d+[,.]?\d*)\s*KVA', re.I)
    # Regex estai
    _BOX_ESTAI_REGEX= re.compile(r'(\d+)[\s\-]*ESTAI', re.I)

    def _find_poles_from_boxes(self, page, page_num):
        """
        RULE-009: Extração de postes a partir de caixas retangulares.
        Usado quando o PDF não contém prefixos P1/P2... explícitos.
        
        Cada caixa candidata é inspecionada:
        - Se contiver tipo de poste (ex: 12/1000, 11/300DT) → é um poste
        - Estruturas e acessórios são extraídos do texto concatenado
        - IDs sequenciais gerados: PA, PB, PC... ou P1, P2 a partir de context
        
        RULE-010: Normalização de texto com hífens concatenados
        Ex: 'N3F-11/300DT-1-S3(1)' → tipo=11/300DT, est=[N3F], sec=[1S3(1)]
        """
        page_h = page.height
        legend_y = page_h * 0.82
        all_words = page.extract_words(keep_blank_chars=False)
        rects = page.rects
        
        # Filtrar caixas candidatas da área do diagrama
        candidate_rects = [
            r for r in rects
            if r['top'] < legend_y
            and 20 < (r['x1'] - r['x0']) < 300
            and 8  < (r['bottom'] - r['top']) < 150
        ]
        
        boxes = []
        for r in sorted(candidate_rects, key=lambda r: (r['top'], r['x0'])):
            # Coletar palavras com centro dentro do retângulo
            words_in = []
            for wd in all_words:
                cx = (wd['x0'] + wd['x1']) / 2
                cy = (wd['top'] + wd['bottom']) / 2
                if (r['x0'] - 3 <= cx <= r['x1'] + 3 and
                        r['top'] - 3 <= cy <= r['bottom'] + 3):
                    t = wd['text'].replace('(cid:13)', ' ').strip()
                    if t:
                        words_in.append(t)
            
            if not words_in:
                continue
            
            # Texto completo da caixa para análise
            combined = ' '.join(words_in).upper()
            
            # RULE-010: expandir tokens concatenados por hífen
            # Ex: 'N4F-11/300DT' → tokens ['N4F', '11/300DT']
            expanded_tokens = []
            for raw_token in re.split(r'[\s;,]+', combined):
                sub = re.split(r'(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])', raw_token)
                expanded_tokens.extend(sub)
            
            # Detectar tipo de poste
            type_match = self._BOX_TYPE_REGEX.search(combined)
            if not type_match:
                continue  # sem tipo de poste → não é caixa de poste
            
            altura = type_match.group(1)
            esforco = type_match.group(2)
            sufixo = (type_match.group(3) or '').upper()
            
            # Normalizar tipo
            if sufixo in ('DT', 'RT'):
                pole_type = f"DT{altura}/{esforco}"
            elif sufixo in ('FIBRA', 'F'):
                pole_type = f"C{altura}/{esforco}"  # fibra = circular
            elif sufixo == 'BCT':
                pole_type = f"C{altura}/{esforco}"
            else:
                pole_type = f"C{altura}/{esforco}"
            
            # Extrair estruturas principais
            estruturas = []
            trafo_desc = None
            estais = 0
            sec_structs = []
            
            for token in expanded_tokens:
                token = token.strip('-').strip()
                if not token:
                    continue
                
                # Trafo
                kva_m = self._BOX_TRAFO_REGEX.search(token)
                if kva_m:
                    kva = kva_m.group(1).replace(',', '.')
                    trafo_desc = f"TRI-{kva}kVA" if float(kva) > 37.5 else f"MONO-{kva}kVA"
                    continue
                
                # Estai
                estai_m = self._BOX_ESTAI_REGEX.search(token)
                if estai_m:
                    estais = int(estai_m.group(1))
                    continue
                
                # Estrutura principal: N3F, N4F, B2, ET4A...
                if self._BOX_EST_REGEX.match(token) and not self._BOX_TYPE_REGEX.search(token):
                    estruturas.append(token)
                    continue
                
                # Estrutura secundária: 1-S3(1), 2-S4(1), 1S3(1)
                sec_m = self._BOX_SEC_REGEX.match(token)
                if sec_m:
                    qty_s = int(sec_m.group(1))
                    code_s = sec_m.group(2)
                    # Normalizar: remover prefixo numérico se já faz parte do código
                    if not self._BOX_TYPE_REGEX.search(code_s):
                        for _ in range(qty_s):
                            sec_structs.append(code_s)
            
            boxes.append({
                'rect': r,
                'pole_type': pole_type,
                'estruturas': estruturas + sec_structs,
                'trafo': trafo_desc,
                'estais': estais,
                'center': ((r['x0'] + r['x1']) / 2, (r['top'] + r['bottom']) / 2),
            })
        
        return boxes

    def find_structures_per_pole(self):
        """
        Identifica postes e associa estruturas.
        
        RULE-009: Detecção automática de layout:
        - Se o PDF contiver ≥1 P_ID explícito (P1, P2...) → modo clássico
        - Se não contiver nenhum → modo por caixas (_find_poles_from_boxes)
        """
        self.last_pole_map = {}
        pole_map = self.last_pole_map
        self.last_labeled_items = []
        labeled_items = self.last_labeled_items

        # ── RULE-009: Detectar layout do PDF automaticamente ─────────────────
        # Pré-escanear palavras (com coordenadas) para verificar P_IDs explícitos.
        # Usa os mesmos filtros RULE-001/002/003 para evitar falsos positivos
        # (ex: 'onde ficará o P5.' em nota de texto).
        p_id_regex_prescan = re.compile(r'\b(P[\d]+)\b', re.IGNORECASE)
        explicit_p_ids_found = set()

        with pdfplumber.open(self.pdf_path) as _pdf_prescan:
            for _page in _pdf_prescan.pages:
                _ph = _page.height
                _ly = _ph * 0.85                      # RULE-001
                for _w in _page.extract_words():
                    if _w['top'] > _ly: continue      # RULE-001: ignorar legenda
                    token = _w['text'].strip().rstrip('.')
                    if re.match(r'^P\d+$', token, re.I):  # token isolado P_ID
                        # RULE-002: ignorar GPS refs (P1=)
                        _after = _w['text'][_w['text'].index(token)+len(token):].strip()
                        if _after.startswith('='): continue
                        explicit_p_ids_found.add(token.upper())

        has_explicit_pids = len(explicit_p_ids_found) >= 2

        if not has_explicit_pids:
            # MODO POR CAIXAS: extração a partir de retângulos com tipologia interna
            print(f"[LAYOUT] Modo por caixas ativado (P_IDs isolados encontrados: {explicit_p_ids_found or 'nenhum'})")
            with pdfplumber.open(self.pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    boxes = self._find_poles_from_boxes(page, i)
                    # Gerar IDs sequenciais por posição topológica (Y depois X)
                    boxes_sorted = sorted(boxes, key=lambda b: (b['center'][1], b['center'][0]))
                    for idx, box in enumerate(boxes_sorted):
                        p_id = f"P{idx+1}"
                        pole_map[p_id] = {
                            'Pole': box['pole_type'],
                            'Est': box['estruturas'],
                            'Trafo': box.get('trafo'),
                            'Estai': box.get('estais', 0),
                        }
                        print(f"  [CAIXA] {p_id}: {box['pole_type']} | Est={box['estruturas']} | Trafo={box.get('trafo')}")
            return pole_map

        def _normalize_pole_type(raw: str) -> str:
            norm = raw.replace('X', '/').replace('x', '/').replace(' ', '').replace('-', '/')
            # OCR comum: "DT" lido como "DI"
            if re.match(r'^DI\d{1,2}/\d{3,4}$', norm, re.IGNORECASE):
                norm = "DT" + norm[2:]
            return norm.upper()

        def _is_valid_structure_token(token: str) -> bool:
            tk = str(token or "").strip().upper()
            if not tk:
                return False
            if re.match(r'^P\d+$', tk):
                return False
            if tk in {"R0", "RO", "O", "0"}:
                return False
            if re.match(r'^ET\d{3,}$', tk):
                return False
            if re.match(r'^BR\d{3,5}$', tk):
                return True
            if re.match(r'^ET\d{1,2}[A-Z]{0,2}$', tk):
                return True
            if re.match(r'^[1-4]S\d$', tk):
                return True
            if re.match(r'^[A-Z]{1,2}\d{1,2}[A-Z]{0,2}$', tk):
                return True
            return False

        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                rect_zones, lines = self._analyze_page_visuals(page, i)
                raw_words = page.extract_words()

                
                # RECONSTRUÇÃO ESPACIAL: Agrupar caracteres fragmentados
                # PDFs CAD-convertidos fragmentam tokens como "N4F" em "N", "4", "F"
                # com gaps variáveis. A estratégia:
                #   1. Ordenar por linha (top) e depois por x0
                #   2. Unir fragmentos na mesma linha com gap_x < GAP_MAX_PX
                #   3. Inserir espaço apenas se gap_x > SPACE_MIN_PX (evitar "N 4 F")
                #   4. Tolerar variação vertical de até VERT_TOL_PX (texto levemente inclinado)
                words = []
                GAP_MAX_PX   = 18   # era 12 — aumentado para cobrir fragmentação CAD
                SPACE_MIN_PX = 3    # gap acima disto → inserir espaço (palavra separada real)
                VERT_TOL_PX  = 12   # era 10 — tolerância linha base

                # Mapa de substituição de ligaduras/caracteres especiais de PDF
                _CID_RE = re.compile(r'\(cid:\d+\)', re.IGNORECASE)
                _LIGATURE_MAP = {
                    'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬀ': 'ff', 'ﬃ': 'ffi', 'ﬄ': 'ffl',
                    '\u0000': '', '\ufffd': '',
                }

                def _clean_fragment(t: str) -> str:
                    t = _CID_RE.sub('', t)
                    for src, dst in _LIGATURE_MAP.items():
                        t = t.replace(src, dst)
                    return t.replace('(CID:13)', '').replace('(CID:3)', '').strip()

                if raw_words:
                    raw_words.sort(key=lambda w: (round(w['top'], 1), w['x0']))
                    current_word = raw_words[0].copy()
                    current_word['text'] = _clean_fragment(current_word['text'])

                    # Altura máxima do diagrama (excluir legendas de rodapé: >85% da página)
                    page_h = page.height
                    legend_y_threshold = page_h * 0.85

                    def get_frag_state(w):
                        # Ignorar retângulos de legenda/rodapé (Y > 85% da página)
                        for r in rect_zones:
                            if r['top'] > legend_y_threshold: continue
                            if (r['x1'] - r['x0'] > 300 or r['bottom'] - r['top'] > 60): continue
                            if (r['x0'] - 2.0 <= w['x0'] <= r['x1'] + 2.0 and r['top'] - 2.0 <= w['top'] <= r['bottom'] + 2.0):
                                return 'NEW'
                        for l in lines:
                            if abs(l['top'] - l['bottom']) < 3 and abs(l['top'] - (w['top']+w['bottom'])/2) < 5:
                                if not (l['x1'] < w['x0'] or l['x0'] > w['x1']): return 'REMOVAL'
                        return 'EXISTING'

                    current_word['state'] = get_frag_state(current_word)

                    for next_w in raw_words[1:]:
                        next_text = _clean_fragment(next_w['text'])
                        if not next_text:
                            continue
                        dist_x  = next_w['x0'] - current_word['x1']
                        dist_y  = abs(next_w['top'] - current_word['top'])

                        # Detectar separador decimal: "3,60" → não inserir espaço
                        is_decimal = (
                            (next_text == ',' or current_word['text'].endswith(','))
                            and bool(re.match(r'\d', next_text))
                        )

                        if dist_y < VERT_TOL_PX and -2 <= dist_x < GAP_MAX_PX:
                            # Mesmo token: unir
                            sep = '' if (dist_x <= SPACE_MIN_PX or is_decimal) else ' '
                            current_word['text'] += sep + next_text
                            current_word['x1']     = next_w['x1']
                            current_word['bottom'] = max(current_word['bottom'], next_w['bottom'])

                            ns = get_frag_state(next_w)
                            if ns == 'REMOVAL' or current_word['state'] == 'REMOVAL':
                                current_word['state'] = 'REMOVAL'
                            elif ns == 'NEW' or current_word['state'] == 'NEW':
                                current_word['state'] = 'NEW'
                        else:
                            if current_word['text']:
                                words.append(current_word)
                            current_word = next_w.copy()
                            current_word['text']  = next_text
                            current_word['state'] = get_frag_state(current_word)

                    if current_word['text']:
                        words.append(current_word)
                
                # Regex patterns
                p_regex = re.compile(r'\b(P[\.\-]?\d+|POSTE?\s*\d+)\b', re.I)
                t_regex = re.compile(r'^([A-Z]{1,2}\d{1,2}[xX/ \-]\d{3,4})', re.I)
                # Padrões que NÃO são estruturas — devem ser excluídos antes de tentar s_regex:
                # 1. Cabos do tipo MT/BT + número + X (ex: MT3X2ANA, BT1X3X120)
                # 2. Bitola de alumínio tipo AXnn (ex: AX24, AX35, AX70)
                # 3. Cabos numéricos tipo NxN (ex: 3X120, 1X3X120)
                _CABLE_STRUCT_RE = re.compile(
                    r'^(?:(?:MT|BT)\d+[Xx]|[Aa][Xx]\d+|\d+[Xx]\d)',
                    re.I
                )
                s_regex = re.compile(r'^([A-Z]{1,2}\d+[A-Z0-9]*|[1-4]S\d|ET\d+[A-Z]*|BR\d+)', re.I)
                trafo_regex = re.compile(r'(?:3\s*Ø\s*)?(\d+[,.]?\d*)\s*KVA', re.I)

                for word in words:
                    text_clean = word['text'].upper().strip()
                    raw_text = re.sub(r'(\d+)\s*([,.]?)\s*(\d+)\s*KVA', r'\1\2\3KVA', text_clean)
                    
                    center = ((word['x0'] + word['x1'])/2, (word['top'] + word['bottom'])/2)
                    state = word['state']
                    
                    p_match = p_regex.search(raw_text)
                    if p_match:
                        p_id = p_match.group(1).strip().upper()
                        # FILTRO 1: ignorar area de legenda/rodape (Y > 85% pagina)
                        # FILTRO 2: ignorar referencias GPS como 'P1= 301103.5 M'
                        # FILTRO 3: ignorar P_ID no meio de frase longa (ex: 'ARVORES ENTRE P1 E P2')
                        after_match = raw_text[p_match.end():].strip()
                        is_gps_ref = after_match.startswith('=')
                        is_in_sentence = len(raw_text) > 30 and p_match.start() > 5
                        if word['top'] > 50 and word['top'] < legend_y_threshold and not is_gps_ref and not is_in_sentence:
                            pole_map[p_id] = {
                                'id': p_id,
                                'pos': center,
                                'Pole': 'Desconhecido',
                                'Est': [],
                                'Trafo': None,
                                'IsNew': (state == 'NEW'),
                                'IsNewContent': False,
                                'IsInDiagram': True   # detectado na area real do diagrama
                            }
                            # Extrair estruturas/tipo embutidos na MESMA palavra composta
                            # Ex: 'P1 N4F,1S4(1)' ou 'P2 D11/300'
                            rest = raw_text[p_match.end():].strip()
                            if rest:
                                safe_rest = re.sub(r'(\d),(\d)', r'\1DOT\2', rest)
                                for chunk in re.split(r'[,;\s]+', safe_rest):
                                    chunk = chunk.replace('DOT', ',').strip()
                                    if not chunk: continue
                                    if t_regex.match(chunk):
                                        norm = _normalize_pole_type(chunk)
                                        pole_map[p_id]['Pole'] = norm
                                        pole_map[p_id]['IsNewContent'] = True
                                    elif s_regex.match(chunk) and len(chunk) >= 2 and not _CABLE_STRUCT_RE.match(chunk):
                                        # Ignorar IDs de poste (P1, P2...) e padrões de cabo como estruturas
                                        if re.match(r'^P\d+$', chunk, re.IGNORECASE):
                                            continue
                                        if _is_valid_structure_token(chunk) and chunk not in pole_map[p_id]['Est']:
                                            pole_map[p_id]['Est'].append(chunk)
                                        pole_map[p_id]['IsNewContent'] = True
                    else:
                        safe_text = re.sub(r'(\d),(\d)', r'\1DOT\2', raw_text)
                        for text in re.split(r'[,;]+', safe_text):
                            text = text.replace('DOT', ',').strip()
                            if not text: continue
                            
                            is_est = s_regex.match(text) and not _CABLE_STRUCT_RE.match(text) and _is_valid_structure_token(text)
                            labeled_items.append({
                                'text': text, 'pos': center, 'state': state,
                                'type': 'TYPE' if t_regex.match(text) else (
                                    'TRAFO' if trafo_regex.search(text) else (
                                        'EST' if is_est else None
                                    )
                                )
                            })
                            if t_regex.match(text) and len(text) > 8:
                                for sub in re.split(r'[,; ]+', text)[1:]:
                                    if s_regex.match(sub) and not _CABLE_STRUCT_RE.match(sub) and _is_valid_structure_token(sub):
                                        labeled_items.append({'text': sub, 'pos': center, 'state': state, 'type': 'EST'})

        # Associação por Proximidade (Nearest Neighbor)
        # Range ampliado para 999px para cobrir diagramas A3 inteiros
        for item in labeled_items:
            if not item['type'] or not pole_map: continue
            
            best_p = None
            min_dist = 999999
            
            for p_id, p_data in pole_map.items():
                dx = item['pos'][0] - p_data['pos'][0]
                dy = item['pos'][1] - p_data['pos'][1]
                dist = math.sqrt(dx**2 + dy**2)
                
                if dist < min_dist and dist < 999:   # range ampliado de 600→999
                    min_dist = dist
                    best_p = p_id
            
            if best_p:
                p_data = pole_map[best_p]
                state = item['state']
                text = item['text']
                
                if item['type'] == 'TYPE':
                    norm_type = _normalize_pole_type(text)
                    current_is_new = p_data.get('IsTypeNew', False)
                    if state == 'NEW':
                        p_data['Pole'] = norm_type
                        p_data['IsTypeNew'] = True
                        p_data['IsNewContent'] = True
                    elif state == 'REMOVAL' and not current_is_new:
                        p_data['Pole'] = f"{norm_type}(R)"
                    elif not current_is_new and (p_data['Pole'] == 'Desconhecido' or '(R)' in p_data['Pole']):
                        if '(R)' not in p_data['Pole']:
                            p_data['Pole'] = norm_type
                            # Marcar como conteúdo (modo permissivo resolve na limpeza final)
                            p_data['IsNewContent'] = True

                elif item['type'] == 'EST':
                    est_matches = re.findall(r'([A-Z]{1,2}\d+[A-Z0-9]*)', text)
                    for est_code in (est_matches if est_matches else [text]):
                        # Ignorar IDs de poste (P1, P2, P10...) na lista de estruturas
                        if re.match(r'^P\d+$', est_code, re.IGNORECASE):
                            continue
                        if not _is_valid_structure_token(est_code):
                            continue
                        norm_text = self.normalize_term(est_code)
                        # Aceitar NEW e EXISTING (modo permissivo aplicado na limpeza final)
                        if state in ('NEW', 'EXISTING'):
                            if state == 'NEW':
                                p_data['IsNewContent'] = True
                            if norm_text not in p_data['Est']:
                                p_data['Est'].append(norm_text)

                elif item['type'] == 'TRAFO':
                    is_trifasico = "3Ø" in text or "TRI" in text or ("3" in text.split("Ø")[0] if "Ø" in text else False)
                    is_bifasico  = "2Ø" in text or "BI" in text or ("2" in text.split("Ø")[0] if "Ø" in text else False)
                    kva_match = trafo_regex.search(text)
                    if kva_match:
                        kva = kva_match.group(1).replace(',', '.')
                        prefix = "TRI" if is_trifasico else ("BI" if is_bifasico else ("MONO" if float(kva) <= 37.5 else "TRI"))
                        desc = f"{prefix}-{kva}kVA"
                        if state in ('NEW', 'EXISTING'):
                            p_data['Trafo'] = desc
                            if state == 'NEW':
                                p_data['IsNewContent'] = True

        # ─── LIMPEZA FINAL ───────────────────────────────────────────────────
        # MODO PERMISSIVO: Se nenhum poste tem IsNew=True (PDF sem caixas individuais),
        # aceitar todos os postes com tipo ou estrutura detectados.
        any_new = any(d.get('IsNew') or d.get('IsNewContent') for d in pole_map.values())
        
        cleaned_map = {}
        for p_id, data in pole_map.items():
            is_new_pole    = data.get('IsNew', False)
            is_type_new    = data.get('IsTypeNew', False)
            has_new_content = data.get('IsNewContent', False)
            has_type       = data.get('Pole', 'Desconhecido') != 'Desconhecido'
            has_structures  = bool(data.get('Est'))
            is_in_diagram   = data.get('IsInDiagram', False)

            # Critério de inclusão:
            # Normal: tem NEW ou está confirmado no diagrama
            # Permissivo (any_new=False): tem tipo ou estrutura detectados
            include = (is_new_pole or has_new_content or is_in_diagram) if any_new else (has_type or has_structures or is_in_diagram)

            if include:
                # Marcar tipo como EXISTING se não foi confirmado como NEW
                if not is_new_pole and not is_type_new and has_type:
                    pole_raw = data['Pole']
                    if '(E)' not in pole_raw and '(R)' not in pole_raw:
                        # Modo permissivo: manter sem sufixo (é novo projeto)
                        pass

                items_to_del = ['pos', 'id', 'IsNew', 'IsNewContent', 'IsTypeNew', 'IsInDiagram', 'state']
                for k in items_to_del:
                    if k in data: del data[k]

                cleaned_map[p_id] = data

        # Fallback de inferência por caixas: quando o modo com P_ID explícito deixa
        # postes sem tipologia, usa o tipo dominante detectado por boxes.
        if has_explicit_pids and cleaned_map:
            unknown_ids = [pid for pid, d in cleaned_map.items() if d.get('Pole', 'Desconhecido') == 'Desconhecido']
            if unknown_ids:
                box_poles = []
                with pdfplumber.open(self.pdf_path) as pdf:
                    for i, page in enumerate(pdf.pages):
                        box_poles.extend(self._find_poles_from_boxes(page, i))

                typed_boxes = [b for b in box_poles if str(b.get('pole_type', '')).strip() and b.get('pole_type') != 'Desconhecido']
                if typed_boxes:
                    counts = Counter([b['pole_type'] for b in typed_boxes])
                    dominant_type, dominant_count = counts.most_common(1)[0]
                    dominant_ratio = dominant_count / max(1, len(typed_boxes))

                    if dominant_ratio >= 0.6:
                        dominant_structs = []
                        for b in typed_boxes:
                            if b['pole_type'] == dominant_type and b.get('estruturas'):
                                dominant_structs = list(b['estruturas'])
                                break

                        for pid in unknown_ids:
                            cleaned_map[pid]['Pole'] = dominant_type
                            if not cleaned_map[pid].get('Est') and dominant_structs:
                                cleaned_map[pid]['Est'] = dominant_structs.copy()

        return cleaned_map

    def find_cables(self):
        """
        Extrai cabos e suas metragens da legenda/quadro de materiais do PDF.

        Estratégia (V4):
        1. Agrupa palavras por linha (tolerância vertical 4px — aumentada de 3px).
        2. Filtra linhas que contenham ao menos uma keyword de cabo E uma quantidade em metros.
        3. Regex em cascata:
           a. Captura preferencial: "MT ..." ou "BT ..." antes da metragem.
           b. Captura por padrão de cabo: "CABO|FIO|COND|MULTIPLEX|AL ..." antes da metragem.
           c. Fallback genérico: qualquer descrição antes da metragem (se a linha passar no
              filtro de keyword).
        4. Classificação MT vs BT por palavras-chave na descrição extraída.
        5. Deduplicação: ignora cabo já capturado com mesma desc + qtd.
        """
        cables_found = []
        seen = set()  # deduplicação (desc_upper, qty)
        print("--- DEBUG: INICIANDO FIND_CABLES (V4) ---")

        keywords = ["MT", "BT", "CABO", "FIO", "COND", "AL", "COBRE", "MULTIPLEX", "NU", "PROTEGIDO"]

        # Regex em cascata — do mais específico ao mais genérico
        _CABLE_PATTERNS = [
            # 1. Linha que começa com MT ou BT (ex: "MT CABO AL NU 35MM2 15KV 250 M")
            re.compile(r'^((?:MT|BT)\b.*?)\s+([\d]{1,5}(?:[,.]\d+)?)\s*(?:M\b|METROS)\b', re.I),
            # 2. Linha com descrição de cabo antes da metragem
            re.compile(r'((?:CABO|FIO|COND|MULTIPLEX)\b.*?)\s+([\d]{1,5}(?:[,.]\d+)?)\s*(?:M\b|METROS)\b', re.I),
            # 3. Qualquer palavra técnica + metragem (fallback)
            re.compile(r'(\b(?:AL\b|COBRE\b|NU\b|PROTEG\w*\b).*?)\s+([\d]{1,5}(?:[,.]\d+)?)\s*(?:M\b|METROS)\b', re.I),
            # 4. Genérico: captura tudo antes de "NNN M" — só se passou no filtro de keyword
            re.compile(r'^(.+?)\s+([\d]{1,5}(?:[,.]\d+)?)\s*(?:M\b|METROS)\b', re.I),
        ]

        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                self._analyze_page_visuals(page, i)

                words = page.extract_words()
                lines_data = {}
                for w in sorted(words, key=lambda w: w['top']):
                    placed = False
                    for y_key in list(lines_data.keys()):
                        if abs(w['top'] - y_key) <= 4.0:   # tolerância aumentada de 3→4px
                            lines_data[y_key].append(w)
                            placed = True
                            break
                    if not placed:
                        lines_data[w['top']] = [w]

                for y in sorted(lines_data.keys()):
                    line_words = sorted(lines_data[y], key=lambda w: w['x0'])
                    line_text = " ".join([w['text'] for w in line_words]).upper().strip()

                    # Pré-filtro rápido
                    has_keyword = any(k in line_text for k in keywords)
                    has_meter   = bool(re.search(r'\d\s*(?:M\b|METROS\b)', line_text))
                    if not (has_keyword and has_meter):
                        continue

                    # Tentar cada padrão até obter match válido
                    matched = False
                    for pattern in _CABLE_PATTERNS:
                        m = pattern.search(line_text)
                        if not m:
                            continue
                        desc    = m.group(1).strip()
                        raw_qty = m.group(2).replace(',', '.')
                        try:
                            qty = float(raw_qty)
                        except ValueError:
                            continue

                        # Descartar valores absurdos (coordenadas GPS, códigos, etc.)
                        if qty <= 0 or qty > 15000:
                            continue
                        # Descartar descrições muito curtas (ruído)
                        if len(desc) < 2:
                            continue

                        # Classificar MT vs BT
                        desc_up = desc.upper()
                        if any(k in desc_up for k in ("15KV", "25KV", "13KV", "34KV", " MT", "MT ")):
                            tipo = 'MT'
                        elif any(k in desc_up for k in ("0.6/1", "1KV", " BT", "BT ", "MULTIPLEX")):
                            tipo = 'BT'
                        elif desc_up.startswith("MT"):
                            tipo = 'MT'
                        else:
                            tipo = 'BT'

                        key = (desc_up, qty)
                        if key in seen:
                            matched = True
                            break
                        seen.add(key)
                        cables_found.append({'Tipo': tipo, 'Desc': desc, 'Qtd': qty})
                        matched = True
                        break

                    if not matched:
                        print(f"[CABO] Linha ignorada (sem match): {line_text[:80]}")

        print(f"--- DEBUG: FIND_CABLES encontrou {len(cables_found)} cabos ---")
        return cables_found

    def get_summary_structures(self, pole_map):
        """Quantifica total de estruturas para o resumo inicial."""
        summary = {}
        for p_data in pole_map.values():
            for est in p_data['Est']:
                summary[est] = summary.get(est, 0) + 1
        return summary

    # ═══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DO AGENTE IA
    # ═══════════════════════════════════════════════════════════════════════════
    
    def extract_equipment(self) -> List[Dict]:
        """
        Extrai equipamentos: chaves, religadores, para-raios, aterramentos.
        Retorna lista com metadados de rastreabilidade.
        """
        equipments = []
        
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
                            first_word = line_words[0] if line_words else None
                            state = 'EXISTING'
                            bbox = (0, 0, 0, 0)
                            
                            if first_word:
                                w_key = (page_num, round(first_word['x0'], 1), 
                                        round(first_word['top'], 1),
                                        round(first_word['x1'], 1), 
                                        round(first_word['bottom'], 1))
                                # [FIX M4] Agora visual_states está populado corretamente
                                state = self.visual_states.get(w_key, 'EXISTING')
                                bbox = (first_word['x0'], first_word['top'],
                                       line_words[-1]['x1'], first_word['bottom'])
                            
                            if state != 'EXISTING':
                                qty_match = re.search(r'(\d+)\s*(?:UN|PÇ|PC)', line_text)
                                qty = int(qty_match.group(1)) if qty_match else 1
                                
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
                                
                                self._log_extraction('equipment', equip_type, line_text, page_num + 1)
        
        self.equipments = equipments
        return equipments
    
    def extract_with_metadata(self) -> Dict:
        """
        Extração completa com metadados de rastreabilidade.
        """
        self.extract_text()
        
        pole_map = self.find_structures_per_pole()
        cables = self.find_cables()
        equipments = self.extract_equipment()
        
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
        
        if HAS_VALIDATOR:
            validator = TechnicalValidator()
            issues = validator.validate(result)
            result['validation'] = validator.get_summary()
        
        return result
    
    def validate_extraction(self, extraction: Dict = None) -> Dict:
        """Executa validação técnica na extração."""
        if extraction is None:
            extraction = self.extract_with_metadata()
        
        if not HAS_VALIDATOR:
            return {'error': 'Módulo validators.py não disponível'}
        
        validator = TechnicalValidator()
        issues = validator.validate(extraction)
        return validator.get_summary()
    
    def get_low_confidence_items(self, threshold: float = 0.7) -> List[Dict]:
        """Retorna itens com score de confiança abaixo do threshold."""
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
            'source_text': source[:100],
            'page': page,
            'timestamp': None
        })
    
    def normalize_term(self, term: str) -> str:
        """Normaliza um termo usando o vocabulário dinâmico."""
        if self.vocabulary:
            return self.vocabulary.normalize(term)
        return term
    
    def get_extraction_report(self) -> str:
        """Gera relatório em Markdown da extração."""
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

    # ═══════════════════════════════════════════════════════════════════════════
    # EXTRAÇÃO VIA API ANTHROPIC (modo avançado, opt-in)
    # ═══════════════════════════════════════════════════════════════════════════

    # Prompt de extração — instrui Claude a retornar JSON estruturado
    _CLAUDE_EXTRACTION_PROMPT = """Você é um especialista em projetos elétricos de distribuição.
Analise este diagrama técnico (desenho de engenharia elétrica) e extraia as informações dos postes e cabos.

Retorne EXCLUSIVAMENTE um JSON válido, sem texto antes ou depois, no formato:
{
  "postes": [
    {
      "id": "P1",
      "tipo": "C12/600",
      "estruturas": ["N4F", "1S3"],
      "trafo": null,
      "estais": 0,
      "chave": null
    }
  ],
  "cabos": [
    {
      "tipo": "MT",
      "descricao": "CABO AL NU 35MM2 15KV",
      "metros": 250
    }
  ],
  "ordem": ""
}

Regras:
- "tipo" do poste: use o formato C{altura}/{esforco} para circulares (ex: C12/600) ou DT{altura}/{esforco} para Duplo T (ex: DT11/300)
- "estruturas": lista de códigos de estrutura conforme o diagrama (ex: N4F, B2, U1, ET4A, 1S3, 1S4)
- "trafo": string como "MONO-15kVA" ou "TRI-75kVA" (null se não houver)
- "tipo" do cabo: "MT" para média tensão, "BT" para baixa tensão
- "metros": número (apenas o valor numérico, sem unidade)
- "ordem": número da ordem de serviço se encontrado no cabeçalho (string vazia se não encontrar)
- Postes marcados com retângulo ou caixa indicam equipamento NOVO
- Postes com texto tachado indicam REMOÇÃO (incluir mesmo assim mas com sufixo R ex: "C12/600(R)")
- Se não encontrar postes ou cabos, retorne listas vazias []"""

    def _normalize_ai_payload(self, data: Dict, provider: str) -> dict:
        """Normaliza payload de IA para o formato interno da aplicação."""
        pole_map = {}
        for poste in data.get('postes', []):
            p_id = str(poste.get('id', 'P?')).upper().strip()
            tipo = str(poste.get('tipo', 'Desconhecido')).strip()
            estruturas = [str(e).upper().strip() for e in poste.get('estruturas', []) if e]
            trafo = poste.get('trafo') or None
            estais = int(poste.get('estais', 0) or 0)
            chave = poste.get('chave') or None

            pole_map[p_id] = {
                'Pole': tipo,
                'Est': estruturas,
                'Trafo': trafo,
                'Estai': {'Type': 'CC - 14M', 'Qtd': estais},
                'Chave': chave,
                'ParaRaio': {'Type': 'CRUZETA', 'Qtd': 0},
                'Aterramento': {'Qtd': 0},
                'Ramal': {'Type': None, 'Qtd': 0.0},
            }

        cables = []
        for cabo in data.get('cabos', []):
            tipo_cabo = str(cabo.get('tipo', 'BT')).upper()
            desc = str(cabo.get('descricao', '')).strip()
            metros = cabo.get('metros', 0)
            try:
                metros = float(str(metros).replace(',', '.'))
            except (ValueError, TypeError):
                metros = 0.0
            if desc and metros > 0:
                cables.append({'Tipo': tipo_cabo, 'Desc': desc, 'Qtd': metros})

        ordem = str(data.get('ordem', '')).strip()

        result = {
            'pole_map': pole_map,
            'cables': cables,
            'ordem': ordem,
            'raw_ai': data,
            'ai_provider': provider,
        }
        print(f"[{provider.upper()}-PDF] Extraídos: {len(pole_map)} postes, {len(cables)} cabos")
        return result

    def extract_with_ai(self, pdf_bytes: bytes, provider: str = "claude") -> dict:
        """Despacha extração avançada para o provedor configurado."""
        p = (provider or "").strip().lower()
        if p == "claude":
            return self.extract_with_claude(pdf_bytes)
        if p == "copilot":
            return self.extract_with_copilot(pdf_bytes)
        raise RuntimeError(f"Provedor de IA não suportado: {provider}")

    def extract_with_claude(self, pdf_bytes: bytes) -> dict:
        """
        Extrai postes e cabos usando a API Anthropic com suporte nativo a PDF.

        Retorna dict com chaves 'pole_map' e 'cables' no mesmo formato do
        find_structures_per_pole() e find_cables(), prontos para uso no engine.

        Lança RuntimeError se a API não estiver disponível ou retornar erro.
        """
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("Biblioteca 'anthropic' não instalada. Execute: pip install anthropic")

        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY não encontrada nas variáveis de ambiente.")

        client = anthropic.Anthropic(api_key=api_key)

        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode('utf-8')

        print("[CLAUDE-PDF] Enviando PDF para API Anthropic...")
        try:
            response = client.beta.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                betas=["pdfs-2024-09-25"],
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": self._CLAUDE_EXTRACTION_PROMPT,
                        },
                    ],
                }],
            )
        except Exception as e:
            raise RuntimeError(f"Erro na chamada à API Anthropic: {e}")

        raw_text = response.content[0].text.strip()
        print(f"[CLAUDE-PDF] Resposta recebida ({len(raw_text)} chars)")

        # Extrair JSON mesmo que venha com markdown ```json ... ```
        json_match = re.search(r'\{[\s\S]*\}', raw_text)
        if not json_match:
            raise RuntimeError(f"Claude não retornou JSON válido. Resposta: {raw_text[:300]}")

        try:
            data = json.loads(json_match.group(0))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Falha ao parsear JSON do Claude: {e}\nJSON: {raw_text[:300]}")

        return self._normalize_ai_payload(data, provider="claude")

    def extract_with_copilot(self, pdf_bytes: bytes) -> dict:
        """
        Extrai postes e cabos via endpoint corporativo do Copilot.

        Variáveis de ambiente esperadas:
        - COPILOT_EXTRACT_WEBHOOK_URL (obrigatória)
        - COPILOT_EXTRACT_API_KEY (opcional)
        - COPILOT_EXTRACT_TIMEOUT_SEC (opcional, padrão 90)
        """
        from urllib.request import Request, urlopen
        from urllib.error import URLError, HTTPError

        webhook_url = os.environ.get("COPILOT_EXTRACT_WEBHOOK_URL", "").strip()
        if not webhook_url:
            raise RuntimeError(
                "COPILOT_EXTRACT_WEBHOOK_URL não configurada. "
                "Defina o endpoint corporativo para extração via Copilot."
            )

        api_key = os.environ.get("COPILOT_EXTRACT_API_KEY", "").strip()
        timeout = int(os.environ.get("COPILOT_EXTRACT_TIMEOUT_SEC", "90"))

        payload = {
            "prompt": self._CLAUDE_EXTRACTION_PROMPT,
            "pdf_base64": base64.standard_b64encode(pdf_bytes).decode("utf-8"),
        }
        body = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if api_key:
            headers["X-API-Key"] = api_key

        print("[COPILOT-PDF] Enviando PDF para endpoint corporativo...")
        req = Request(webhook_url, data=body, headers=headers, method="POST")

        try:
            with urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore")[:300]
            raise RuntimeError(f"Erro HTTP no endpoint Copilot: {e.code} - {detail}")
        except URLError as e:
            raise RuntimeError(f"Falha de conexão no endpoint Copilot: {e.reason}")
        except Exception as e:
            raise RuntimeError(f"Erro ao chamar endpoint Copilot: {e}")

        data = self._parse_copilot_response(raw)

        return self._normalize_ai_payload(data, provider="copilot")

    def _parse_copilot_response(self, raw: str) -> Dict:
        """
        Interpreta resposta do endpoint Copilot e retorna payload canônico:
        {"postes": [...], "cabos": [...], "ordem": "..."}.
        """
        # Aceita payload já em JSON ou texto contendo JSON
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"content": raw}

        if isinstance(parsed, dict) and "postes" in parsed and "cabos" in parsed:
            return parsed

        if isinstance(parsed, dict) and isinstance(parsed.get("result"), dict):
            result = parsed["result"]
            if "postes" in result and "cabos" in result:
                return result

        if isinstance(parsed, dict) and isinstance(parsed.get("content"), str):
            content = parsed["content"]
            match = re.search(r"\{[\s\S]*\}", content)
            if not match:
                raise RuntimeError("Copilot não retornou JSON válido em 'content'.")
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Falha ao parsear JSON do Copilot: {e}")
            if "postes" in payload and "cabos" in payload:
                return payload
            raise RuntimeError("JSON de conteúdo Copilot sem chaves esperadas ('postes'/'cabos').")

        raise RuntimeError("Formato de resposta do Copilot não reconhecido.")
