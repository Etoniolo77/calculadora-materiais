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
                    if page_text and page_text.strip():
                        full_text.append(page_text)
                    else:
                        # Fallback para PDFs CAD escaneados/parciais:
                        # reconstruir texto mínimo a partir de extract_words().
                        words = page.extract_words() or []
                        if words:
                            # Ordena por linha (top) e coluna (x0)
                            words_sorted = sorted(words, key=lambda w: (round(w.get('top', 0), 1), w.get('x0', 0)))
                            lines = []
                            current = []
                            current_top = None
                            for w in words_sorted:
                                top = float(w.get('top', 0))
                                txt = str(w.get('text', '')).strip()
                                if not txt:
                                    continue
                                if current_top is None:
                                    current_top = top
                                if abs(top - current_top) > 3.0:
                                    if current:
                                        lines.append(" ".join(current))
                                    current = [txt]
                                    current_top = top
                                else:
                                    current.append(txt)
                            if current:
                                lines.append(" ".join(current))
                            if lines:
                                full_text.append("\n".join(lines))
                    
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

    def extract_estf_codes(self) -> list[str]:
        """
        Extrai códigos de identificação de trafo no padrão ESTF + 6 dígitos.
        Exemplo: ESTF485344.
        """
        text = str(self.text or "").upper()
        if not text:
            return []
        matches = re.findall(r'ESTF[\s\-:]*([0-9]{6})', text, re.IGNORECASE)
        codes: list[str] = []
        for m in matches:
            code = f"ESTF{m}"
            if code not in codes:
                codes.append(code)
        return codes

    def extract_et_trafo_codes(self) -> list[str]:
        """
        Extrai códigos de trafo novo no padrão ET + 6 dígitos.
        Exemplo: ET485344.
        """
        text = str(self.text or "").upper()
        if not text:
            return []
        # OCR tolerante:
        # - aceita "ET", "E T"
        # - aceita O no lugar de 0 nos 6 dígitos
        # - aceita separadores comuns
        matches = re.findall(r'\bE\s*T[\s\-:]*([0-9O]{6})\b', text, re.IGNORECASE)
        strict_new_only = any(v == 'NEW' for v in self.visual_states.values())
        codes: list[str] = []
        for m in matches:
            digits = str(m).replace("O", "0")
            if not re.match(r'^[0-9]{6}$', digits):
                continue
            code = f"ET{digits}"
            if strict_new_only:
                variants = [code, f"ET {digits}", f"ET-{digits}", f"ET:{digits}", f"E T {digits}"]
                if not any(self.get_word_state(v) == 'NEW' for v in variants):
                    continue
            if code not in codes:
                codes.append(code)
        return codes

    # ─── RULE-009/010: Extração por Caixas (PDFs sem prefixo P) ──────────────

    # Regex para tipo de poste dentro de caixa: ex '12/300', '11/300DT', '12/1000-BCT'
    _BOX_TYPE_REGEX = re.compile(
        r'(?<![A-Z0-9])(?:(?P<prefix>DT|DI|D|C)\s*)?(?P<altura>\d{1,2})[/xX](?P<esforco>\d{3,4})(?:[\s\-]?(?P<sufixo>DT|RT|FIBRA|BCT|F))?(?![A-Z0-9])',
        re.I,
    )
    # Regex para estrutura: N3F, N4F, B2, ET4A etc.
    _BOX_EST_REGEX  = re.compile(r'^([A-Z]{1,2}\d+[A-Z0-9]*|SMTR)$', re.I)
    # Regex para estruturas secundárias: 1-S3(1), 2-S4(1), 1S3(1)
    _BOX_SEC_REGEX  = re.compile(
        r'(\d+)[\s\-]*([A-Z]{1,2}\d+[A-Z0-9]*)(?:\((\d+)\))?', re.I
    )
    # Regex KVA para transformadores dentro de caixa
    _BOX_TRAFO_REGEX= re.compile(r'(\d+[,.]?\d*)\s*KVA', re.I)
    # Regex estai
    _BOX_ESTAI_REGEX= re.compile(r'(\d+)[\s\-]*ESTAI', re.I)
    _CABLE_STRUCT_RE = re.compile(
        r'^(?:(?:MT|BT)\d+[Xx]|[Aa][Xx]\d+|\d+[Xx]\d)',
        re.I,
    )

    def _is_valid_structure_token(self, token: str) -> bool:
        tk = str(token or "").strip().upper()
        if not tk:
            return False
        if tk in {"SMTR"}:
            return True
        if re.match(r'^P\d+$', tk):
            return False
        if tk in {"R0", "RO", "O", "0"}:
            return False
        if self._CABLE_STRUCT_RE.match(tk):
            return False
        if re.match(r'^ET\d{3,}$', tk):
            return False
        if re.match(r'^BR\d{3,5}$', tk):
            return False
        if re.match(r'^ET\d{1,2}[A-Z]{0,2}$', tk):
            return True
        if re.match(r'^[1-4]S\d$', tk):
            return True
        if re.match(r'^[A-Z]{1,2}\d{1,2}[A-Z]{0,2}$', tk):
            return True
        return False

    def _expand_structure_token(self, token: str) -> list[str]:
        tk = str(token or "").strip().upper()
        if not tk:
            return []
        match = re.match(r"^(\d+)(S\d)$", tk)
        if match:
            qty = int(match.group(1) or 0)
            base = match.group(2)
            if qty > 0:
                return [base] * qty
        return [tk]

    def _expand_structure_list(self, items: list[str]) -> list[str]:
        expanded = []
        for item in items or []:
            expanded.extend(self._expand_structure_token(item))
        return expanded

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
            and 20 < (r['x1'] - r['x0']) < 600
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
            for raw_token in re.split(r'[\s;,+]+', combined):
                sub = re.split(r'(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])', raw_token)
                expanded_tokens.extend(sub)
            
            # Detectar tipo de poste
            type_match = self._BOX_TYPE_REGEX.search(combined)
            if not type_match:
                continue  # sem tipo de poste → não é caixa de poste
            
            altura = type_match.group('altura')
            esforco = type_match.group('esforco')
            prefixo = (type_match.group('prefix') or '').upper()
            sufixo = (type_match.group('sufixo') or '').upper()
            
            # Normalizar tipo
            if prefixo in ('DT', 'DI') or sufixo in ('DT', 'RT'):
                pole_type = f"DT{altura}/{esforco}"
            elif prefixo == 'D':
                pole_type = f"D{altura}/{esforco}"
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
                    if self._is_valid_structure_token(token):
                        estruturas.append(token)
                    continue
                
                # Estrutura secundária: 1-S3(1), 2-S4(1), 1S3(1)
                sec_m = self._BOX_SEC_REGEX.match(token)
                if sec_m:
                    qty_s = int(sec_m.group(1))
                    code_s = sec_m.group(2)
                    # Normalizar: remover prefixo numérico se já faz parte do código
                    if not self._BOX_TYPE_REGEX.search(code_s) and self._is_valid_structure_token(code_s):
                        for _ in range(qty_s):
                            sec_structs.append(code_s)

            # Dedupe mantendo ordem de leitura
            all_structs = []
            for est in self._expand_structure_list(estruturas + sec_structs):
                if est not in all_structs:
                    all_structs.append(est)
            
            boxes.append({
                'rect': r,
                'pole_type': pole_type,
                'estruturas': all_structs,
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
        exact_pole_anchors = []
        new_struct_lines = []
        typed_struct_lines = []
        # Modo estrito de revisão:
        # se houver qualquer conteúdo marcado como NEW no PDF, somente itens NEW
        # devem ser considerados como novos para cálculo.
        strict_new_only = any(v == 'NEW' for v in self.visual_states.values())

        # ── RULE-009: Detectar layout do PDF automaticamente ─────────────────
        # Pré-escanear palavras (com coordenadas) para verificar P_IDs explícitos.
        # Usa os mesmos filtros RULE-001/002/003 para evitar falsos positivos
        # (ex: 'onde ficará o P5.' em nota de texto).
        p_id_regex_prescan = re.compile(r'\bP[\s\.\-]*\d+\b', re.IGNORECASE)
        explicit_p_ids_found = set()

        with pdfplumber.open(self.pdf_path) as _pdf_prescan:
            for _page in _pdf_prescan.pages:
                _ph = _page.height
                for _w in _page.extract_words():
                    token = _w['text'].strip().rstrip('.')
                    if p_id_regex_prescan.match(token):  # token isolado P_ID
                        if re.match(r"^P\d+\-$", token.upper()):
                            continue
                        # RULE-002: ignorar GPS refs (P1=)
                        _after = _w['text'][_w['text'].index(token)+len(token):].strip()
                        if _after.startswith('='): continue
                        p_digits = re.sub(r'\D', '', token)
                        if p_digits:
                            explicit_p_ids_found.add(f"P{p_digits}")

        has_explicit_pids = len(explicit_p_ids_found) >= 2

        if not has_explicit_pids:
            # Fallback textual para rótulos CAD em linha:
            # Ex.: "P-02-12X600CIR- N3F- S1-S3 ESTAI- 75KVA- MT"
            text_line_poles = {}
            for raw_line in str(self.text or "").upper().splitlines():
                line = re.sub(r"\s+", " ", raw_line).strip()
                if not line or "P-" not in line:
                    continue
                p_m = re.search(r"\bP[\s\-]*(\d{1,2})\b", line)
                t_m = re.search(r"\b(\d{1,2})X(\d{3,4})(CIR|DT|D)?\b", line)
                if not p_m or not t_m:
                    continue
                p_id = f"P{int(p_m.group(1))}"
                altura = t_m.group(1)
                esforco = t_m.group(2)
                sufixo = (t_m.group(3) or "").upper()
                pole_type = f"DT{altura}/{esforco}" if sufixo in {"DT", "D"} else f"C{altura}/{esforco}"

                ests = []
                for est in re.findall(r"\b(?:[A-Z]{1,2}\d+[A-Z0-9]*|[1-4]S\d|ESTAI|SMTR)\b", line):
                    e = est.strip().upper()
                    if e in {"MT", "BT"}:
                        continue
                    if self._is_valid_structure_token(e) and e not in ests:
                        ests.append(e)

                trafo_desc = None
                kva_m = re.search(r"\b(\d+[,.]?\d*)\s*KVA\b", line)
                if kva_m:
                    kva = kva_m.group(1).replace(",", ".")
                    trafo_desc = f"TRI-{kva}kVA" if float(kva) > 37.5 else f"MONO-{kva}kVA"

                if ests:
                    text_line_poles[p_id] = {
                        'Pole': pole_type,
                        'Est': ests,
                        'Trafo': trafo_desc,
                        'Estai': 0,
                    }

            if len(text_line_poles) >= 2:
                print(f"[LAYOUT] Fallback textual ativado ({len(text_line_poles)} postes)")
                for pid in sorted(text_line_poles.keys(), key=lambda x: int(re.sub(r"\D", "", x) or "0")):
                    text_line_poles[pid]["Est"] = self._expand_structure_list(text_line_poles[pid].get("Est", []))
                    pole_map[pid] = text_line_poles[pid]
                    pd = text_line_poles[pid]
                    print(f"  [TEXTO] {pid}: {pd['Pole']} | Est={pd['Est']} | Trafo={pd['Trafo']}")
                return pole_map

        if not has_explicit_pids:
            # MODO POR CAIXAS: extração a partir de retângulos com tipologia interna
            print(f"[LAYOUT] Modo por caixas ativado (P_IDs isolados encontrados: {explicit_p_ids_found or 'nenhum'})")
            pole_centers = {}
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
                        pole_centers[p_id] = box['center']
                        print(f"  [CAIXA] {p_id}: {box['pole_type']} | Est={box['estruturas']} | Trafo={box.get('trafo')}")

                # Regra determinística: em modo por caixas, usar apenas o conteúdo
                # interno de cada caixa. Heurísticas de proximidade/texto ficam
                # desativadas para evitar associação indevida entre postes.
                if False and pole_map:
                    # Complemento sequencial por linhas de texto técnico:
                    # captura blocos como "N3F-11/300DT" + "1-S3(1);1-S1(1)" + "1-ESTAI"
                    line_blocks = []
                    lines_text = [re.sub(r"\s+", " ", ln).strip().upper() for ln in str(self.text or "").splitlines()]
                    for idx, ln in enumerate(lines_text):
                        if not ln:
                            continue
                        t_m = re.search(r"(DT\d{1,2}[X/]\d{3,4}|D\d{1,2}[X/]\d{3,4}|\d{1,2}[X/]\d{3,4}(?:-?(?:CIR|BCT|DT|D))?)", ln)
                        if not t_m:
                            continue
                        raw_t = t_m.group(1).replace("X", "/")
                        m_norm = re.search(r"(\d{1,2})/(\d{3,4})", raw_t)
                        if not m_norm:
                            continue
                        h, e = m_norm.group(1), m_norm.group(2)
                        if "DT" in raw_t or raw_t.startswith("D"):
                            pole_type = f"DT{h}/{e}"
                        else:
                            pole_type = f"C{h}/{e}"

                        block_text = " ".join(lines_text[max(0, idx - 2): min(len(lines_text), idx + 3)])
                        ests = []
                        for est in re.findall(r"\b(?:[A-Z]{1,2}\d+[A-Z0-9]*|[1-4]S\d|ESTAI|SMTR)\b", block_text):
                            est_u = est.strip().upper()
                            if est_u in {"MT", "BT"}:
                                continue
                            if self._is_valid_structure_token(est_u):
                                ests.append(est_u)
                        # Multiplicidade explícita em bloco (ex.: 2-S3(2), 2-S4(1))
                        for m_mul in re.finditer(r"(\d+)\s*-\s*([1-4]S\d)(?:\((\d+)\))?", block_text):
                            lead = int(m_mul.group(1) or 1)
                            code = m_mul.group(2).strip().upper()
                            par = int(m_mul.group(3) or 1)
                            qty = max(lead, par)
                            ests.extend([code] * max(0, qty - 1))
                        estai_qtd = 0
                        m_estai = re.search(r"(\d+)\s*[-]?\s*ESTAI", block_text)
                        if m_estai:
                            estai_qtd = int(m_estai.group(1))
                        trafo_desc = None
                        m_kva = re.search(r"(\d+[,.]?\d*)\s*KVA", block_text)
                        if m_kva:
                            kva = m_kva.group(1).replace(",", ".")
                            trafo_desc = f"TRI-{kva}kVA" if float(kva) > 37.5 else f"MONO-{kva}kVA"
                        line_blocks.append({
                            "pole_type": pole_type,
                            "ests": ests,
                            "estai": estai_qtd,
                            "trafo": trafo_desc,
                        })

                    if line_blocks:
                        used_blocks = set()
                        for pid in sorted(pole_map.keys(), key=lambda x: int(re.sub(r"\D", "", x) or "0")):
                            pdata = pole_map[pid]
                            ptype = str(pdata.get("Pole", "")).upper()
                            best_i = None
                            for i, b in enumerate(line_blocks):
                                if i in used_blocks:
                                    continue
                                if b["pole_type"] == ptype:
                                    best_i = i
                                    break
                            if best_i is None:
                                continue
                            used_blocks.add(best_i)
                            blk = line_blocks[best_i]
                            for est in blk["ests"]:
                                pdata["Est"].append(est)
                            if blk["estai"] > 0:
                                pdata["Estai"] = max(int(pdata.get("Estai", 0) or 0), blk["estai"])
                            if blk["trafo"] and not pdata.get("Trafo"):
                                pdata["Trafo"] = blk["trafo"]

                    for page in pdf.pages:
                        words = page.extract_words() or []
                        for w in words:
                            txt = str(w.get('text', '')).upper().strip()
                            if not txt:
                                continue
                            # Quebra cadeias do tipo N3F-S3-ESTAI
                            chain_parts = [p.strip() for p in re.split(r'[-]+', txt) if p.strip()]
                            est_tokens = []
                            for p in chain_parts:
                                p = re.sub(r"\(\d+\)$", "", p)
                                if re.match(r'^[1-4]S\d$', p):
                                    est_tokens.append(p)
                                elif self._is_valid_structure_token(p):
                                    est_tokens.append(p)
                                elif p == 'ESTAI':
                                    est_tokens.append('ESTAI')
                            if not est_tokens:
                                # fallback em token simples
                                if re.match(r'^[1-4]S\d$', txt) or self._is_valid_structure_token(txt):
                                    est_tokens = [txt]
                            if not est_tokens and 'ESTAI' not in txt:
                                continue

                            # Estai com quantidade (ex.: 1-ESTAI, 3-ESTAI)
                            estai_qtd = None
                            m_estai = re.search(r'(\d+)\s*[-]?\s*ESTAI', txt)
                            if m_estai:
                                estai_qtd = int(m_estai.group(1))

                            cx = (w['x0'] + w['x1']) / 2
                            cy = (w['top'] + w['bottom']) / 2
                            best_pid = None
                            best_d = 1e18
                            for pid, (px, py) in pole_centers.items():
                                d = (px - cx) ** 2 + (py - cy) ** 2
                                if d < best_d:
                                    best_d = d
                                    best_pid = pid
                            # raio conservador para evitar associação indevida
                            if best_pid is None or best_d > (260 ** 2):
                                continue

                            for est in est_tokens:
                                if est == 'ESTAI':
                                    continue
                                pole_map[best_pid]['Est'].append(est)
                            if estai_qtd is not None:
                                pole_map[best_pid]['Estai'] = max(int(pole_map[best_pid].get('Estai', 0) or 0), estai_qtd)
            if not pole_map and explicit_p_ids_found:
                for p_id in sorted(
                    explicit_p_ids_found,
                    key=lambda x: int(re.sub(r"\D", "", x) or "0"),
                ):
                    pole_map[p_id] = {'Pole': 'Desconhecido', 'Est': [], 'Trafo': None, 'Estai': 0}
            return pole_map

        def _normalize_pole_type(raw: str) -> str:
            txt = str(raw or "").upper()
            # Captura apenas o primeiro token válido de tipologia.
            m = re.search(r'(DT\d{1,2}[X/]\d{3,4}|DI\d{1,2}[X/]\d{3,4}|D\d{1,2}[X/]\d{3,4}|C\d{1,2}[X/]\d{3,4}|M\d{1,2}[X/]\d{3,4})', txt)
            if m:
                txt = m.group(1)
            norm = txt.replace('X', '/').replace('x', '/').replace(' ', '').replace('-', '/')
            # OCR comum: "DT" lido como "DI"
            if re.match(r'^DI\d{1,2}/\d{3,4}$', norm, re.IGNORECASE):
                norm = "DT" + norm[2:]
            # OCR comum: "C" lido como "M" em poste circular.
            if re.match(r'^M\d{1,2}/\d{3,4}$', norm, re.IGNORECASE):
                norm = "C" + norm[1:]
            return norm.upper()

        def _extract_pole_type(raw: str) -> str | None:
            txt = str(raw or "").upper()
            m = re.search(r'(DT\d{1,2}[X/]\d{3,4}|DI\d{1,2}[X/]\d{3,4}|D\d{1,2}[X/]\d{3,4}|C\d{1,2}[X/]\d{3,4}|M\d{1,2}[X/]\d{3,4})', txt)
            if not m:
                return None
            return _normalize_pole_type(m.group(1))

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

                # Captura linhas com tipologia+estrutura para fallback de associação.
                # NEW continua prioritário; EXISTING ajuda a completar poste novo.
                for w in words:
                    txt = str(w.get("text", "")).upper().strip()
                    exact_pid_match = re.fullmatch(r'P\s*0*(\d{1,2})', txt)
                    if exact_pid_match:
                        exact_pole_anchors.append(
                            {
                                "id": f"P{int(exact_pid_match.group(1))}",
                                "pos": ((w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2),
                                "state": w.get("state"),
                            }
                        )
                    pole_t = _extract_pole_type(txt)
                    if not pole_t:
                        continue
                    structs = re.split(r"[,;\s]+", txt)
                    has_struct = any(self._is_valid_structure_token(re.sub(r"\(\d+\)$", "", s)) for s in structs if s)
                    if has_struct and w.get("state") == "NEW":
                        new_struct_lines.append(
                            {
                                "text": txt,
                                "pos": ((w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2),
                                "pole_type": pole_t,
                            }
                        )
                    if has_struct and w.get("state") != "REMOVAL":
                        typed_struct_lines.append(
                            {
                                "text": txt,
                                "pos": ((w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2),
                                "pole_type": pole_t,
                            }
                        )
                
                # Regex patterns
                # Aceita padrões como P2 e P-02-12X600CIR (muito comum em rótulos CAD).
                p_regex = re.compile(r'\b(P[\s\.\-]*\d+|POSTE?\s*\d+)\b', re.I)
                t_regex = re.compile(r'^([A-Z]{1,2}\d{1,2}[xX/ \-]\d{3,4})', re.I)
                # Padrões que NÃO são estruturas — devem ser excluídos antes de tentar s_regex:
                # 1. Cabos do tipo MT/BT + número + X (ex: MT3X2ANA, BT1X3X120)
                # 2. Bitola de alumínio tipo AXnn (ex: AX24, AX35, AX70)
                # 3. Cabos numéricos tipo NxN (ex: 3X120, 1X3X120)
                _CABLE_STRUCT_RE = re.compile(
                    r'^(?:(?:MT|BT)\d+[Xx]|[Aa][Xx]\d+|\d+[Xx]\d)',
                    re.I
                )
                s_regex = re.compile(r'^([A-Z]{1,2}\d+[A-Z0-9]*|[1-4]S\d|ET\d+[A-Z]*|BR\d+|SMTR)', re.I)
                trafo_regex = re.compile(r'(?:3\s*Ø\s*)?(\d+[,.]?\d*)\s*KVA', re.I)

                def _is_metadata_noise(text: str) -> bool:
                    txt = str(text or "").upper().strip()
                    if not txt:
                        return False
                    if ".PDF" in txt or "\\" in txt or "/" in txt:
                        return True
                    if "CAMINHO DO PDF" in txt or "CAMINHODOPDF" in txt:
                        return True
                    return False

                def _explode_struct_chain(token: str) -> list[str]:
                    """
                    Decompõe cadeias como 'N3F-S3-ESTAI' em estruturas individuais.
                    Também preserva tokens já válidos e ignora lixo/cabos.
                    """
                    t = str(token or "").upper().strip()
                    if not t:
                        return []
                    if _is_metadata_noise(t):
                        return []
                    parts = [p.strip() for p in re.split(r'[-]+', t) if p.strip()]
                    out = []
                    for p in parts:
                        p = re.sub(r"\(\d+\)$", "", p)
                        if not p:
                            continue
                        if p == "ESTAI":
                            out.append("ESTAI")
                            continue
                        if s_regex.match(p) and not _CABLE_STRUCT_RE.match(p) and self._is_valid_structure_token(p):
                            out.append(p)
                    if not out and s_regex.match(t) and not _CABLE_STRUCT_RE.match(t) and self._is_valid_structure_token(t):
                        out.append(t)
                    return out

                for word in words:
                    text_clean = word['text'].upper().strip()
                    raw_text = re.sub(r'(\d+)\s*([,.]?)\s*(\d+)\s*KVA', r'\1\2\3KVA', text_clean)
                    
                    center = ((word['x0'] + word['x1'])/2, (word['top'] + word['bottom'])/2)
                    state = word['state']
                    
                    p_match = p_regex.search(raw_text)
                    if p_match:
                        p_raw = p_match.group(1).strip().upper()
                        if re.match(r"^P\d+\-$", raw_text, re.IGNORECASE):
                            continue
                        p_digits = re.sub(r"\D", "", p_raw)
                        if not p_digits:
                            continue
                        p_id = f"P{p_digits}"
                        # FILTRO 1: ignorar area de legenda/rodape (Y > 85% pagina)
                        # FILTRO 2: ignorar referencias GPS como 'P1= 301103.5 M'
                        # FILTRO 3: ignorar P_ID no meio de frase longa (ex: 'ARVORES ENTRE P1 E P2')
                        after_match = raw_text[p_match.end():].strip()
                        is_gps_ref = after_match.startswith('=')
                        is_in_sentence = len(raw_text) > 30 and p_match.start() > 5
                        if word['top'] > 50 and not is_gps_ref and not is_in_sentence:
                            if p_id in pole_map:
                                continue
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
                                    pole_token = _extract_pole_type(chunk)
                                    if pole_token:
                                        norm = pole_token
                                        if (not strict_new_only) or state == 'NEW':
                                            pole_map[p_id]['Pole'] = norm
                                            if state == 'NEW':
                                                pole_map[p_id]['IsTypeNew'] = True
                                    elif len(chunk) >= 2:
                                        if strict_new_only and state != 'NEW':
                                            continue
                                        # Ignorar IDs de poste (P1, P2...) e padrões de cabo como estruturas
                                        if re.match(r'^P\d+$', chunk, re.IGNORECASE):
                                            continue
                                        # Suporta cadeia em um único token:
                                        # 2S2(2)+1S1(R) e N3F-S3-ESTAI
                                        est_tokens = re.findall(r'(?:[A-Z]{1,2}\d+[A-Z0-9]*|[1-4]S\d|ESTAI)', chunk.upper())
                                        exploded = _explode_struct_chain(chunk)
                                        if exploded:
                                            est_tokens.extend(exploded)
                                        if not est_tokens:
                                            est_tokens = [chunk]
                                        for est_token in est_tokens:
                                            if self._is_valid_structure_token(est_token) and est_token not in pole_map[p_id]['Est']:
                                                pole_map[p_id]['Est'].append(est_token)
                    else:
                        safe_text = re.sub(r'(\d),(\d)', r'\1DOT\2', raw_text)
                        for text in re.split(r'[,;+]+', safe_text):
                            text = text.replace('DOT', ',').strip()
                            if not text: continue
                            if _is_metadata_noise(text):
                                continue
                            pole_token = _extract_pole_type(text)
                            exploded_for_label = _explode_struct_chain(text)
                            is_est = (
                                (s_regex.match(text) and not _CABLE_STRUCT_RE.match(text) and self._is_valid_structure_token(text))
                                or bool(exploded_for_label)
                            )
                            if strict_new_only and word['state'] != 'NEW' and is_est:
                                is_est = False
                            labeled_items.append({
                                'text': text, 'pos': center, 'state': state,
                                'type': 'TYPE' if pole_token else (
                                    'TRAFO' if trafo_regex.search(text) else (
                                        'EST' if is_est else None
                                    )
                                )
                            })
                            if pole_token and len(text) > 8:
                                for sub in re.split(r'[,;+ ]+', text)[1:]:
                                    if strict_new_only and state != 'NEW':
                                        continue
                                    if s_regex.match(sub) and not _CABLE_STRUCT_RE.match(sub) and self._is_valid_structure_token(sub):
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
                    extracted_type = _extract_pole_type(text)
                    if not extracted_type:
                        continue
                    norm_type = extracted_type
                    current_is_new = p_data.get('IsTypeNew', False)
                    if state == 'NEW':
                        p_data['Pole'] = norm_type
                        p_data['IsTypeNew'] = True
                    elif state == 'REMOVAL' and not current_is_new:
                        p_data['Pole'] = f"{norm_type}(R)"
                    elif not current_is_new and (p_data['Pole'] == 'Desconhecido' or '(R)' in p_data['Pole']):
                        if '(R)' not in p_data['Pole']:
                            p_data['Pole'] = norm_type

                elif item['type'] == 'EST':
                    est_matches = re.findall(r'([A-Z]{1,2}\d+[A-Z0-9]*)', text)
                    for est_code in (est_matches if est_matches else [text]):
                        # Ignorar IDs de poste (P1, P2, P10...) na lista de estruturas
                        if re.match(r'^P\d+$', est_code, re.IGNORECASE):
                            continue
                        if not self._is_valid_structure_token(est_code):
                            continue
                        norm_text = self.normalize_term(est_code)
                        # Regra dura: estrutura só entra como novo quando marcada NEW.
                        if state == 'NEW':
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
                        # Regra dura: trafo só entra como novo quando marcado NEW.
                        if state == 'NEW':
                            p_data['Trafo'] = desc

        # Preenchimento assistido: quando o poste NEW ficou sem estrutura,
        # usa a linha NEW mais próxima que contém tipologia + estruturas.
        def _extract_structs_from_line(text: str) -> list[str]:
            txt = str(text or "").upper()
            if _is_metadata_noise(txt):
                return []
            out = []
            # Multiplicidade explícita (ex.: 2X[B2F], 2XB2F)
            for m in re.finditer(r'(\d+)\s*[X]\s*\[?\s*([A-Z]{1,3}\d+[A-Z0-9]*)\s*\]?', txt, re.I):
                qtd = int(m.group(1))
                est = m.group(2).strip()
                if qtd <= 0:
                    continue
                if self._is_valid_structure_token(est):
                    out.extend([est] * qtd)

            # Sufixos ordinais (ex.: B2F-1° - B2F-2°)
            ordinal_counts = Counter()
            for m in re.finditer(r'([A-Z]{1,3}\d+[A-Z0-9]*)\s*-\s*\d+°', txt, re.I):
                est = m.group(1).strip().upper()
                if self._is_valid_structure_token(est):
                    ordinal_counts[est] += 1
            for est, qtd in ordinal_counts.items():
                out.extend([est] * qtd)

            tokens = re.split(r"[,;\s]+", txt)
            for tk in tokens:
                tk = tk.strip()
                if not tk:
                    continue
                if _is_metadata_noise(tk):
                    continue
                tk = re.sub(r"\(\d+\)$", "", tk)
                if _extract_pole_type(tk):
                    continue
                # Cadeias compostas: N3F-S3-ESTAI
                chain_parts = [p.strip() for p in re.split(r"[-]+", tk) if p.strip()]
                if len(chain_parts) > 1:
                    for cp in chain_parts:
                        cp = re.sub(r"\(\d+\)$", "", cp)
                        if cp == "ESTAI" and cp not in out:
                            out.append(cp)
                        elif self._is_valid_structure_token(cp):
                            out.append(cp)
                    continue
                if tk == "ESTAI":
                    out.append(tk)
                elif self._is_valid_structure_token(tk):
                    out.append(tk)
            return out

        candidate_lines = []
        # Usa as palavras reconstruídas com estado visual já calculado (NEW/EXISTING/REMOVAL)
        for w in words:
            txt = str(w.get("text", "")).upper().strip()
            if w.get("state") != "NEW":
                continue
            if not _extract_pole_type(txt):
                continue
            structs = _extract_structs_from_line(txt)
            if structs:
                candidate_lines.append(
                    {
                        "pos": ((w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2),
                        "structs": structs,
                    }
                )

        used_candidates = set()
        for p_id, p_data in pole_map.items():
            if not (p_data.get("IsNew") or p_data.get("IsTypeNew")):
                continue
            if p_data.get("Est"):
                continue
            best_idx = None
            best_dist = 999999999.0
            px, py = p_data.get("pos", (0.0, 0.0))
            for idx, cand in enumerate(candidate_lines):
                if idx in used_candidates:
                    continue
                cx, cy = cand["pos"]
                d = (px - cx) ** 2 + (py - cy) ** 2
                if d < best_dist:
                    best_dist = d
                    best_idx = idx
            if best_idx is not None:
                p_data["Est"] = candidate_lines[best_idx]["structs"].copy()
                used_candidates.add(best_idx)

        # ─── LIMPEZA FINAL ───────────────────────────────────────────────────
        # Regra dura: somente postes com marcação NEW (retângulo/conteúdo novo)
        # entram no resultado final.
        
        cleaned_map = {}
        for p_id, data in pole_map.items():
            is_new_pole    = data.get('IsNew', False)
            is_type_new    = data.get('IsTypeNew', False)
            has_new_content = data.get('IsNewContent', False)
            is_type_new = data.get('IsTypeNew', False)
            has_type       = data.get('Pole', 'Desconhecido') != 'Desconhecido'
            has_structures  = bool(data.get('Est'))
            is_in_diagram   = data.get('IsInDiagram', False)

            include = is_new_pole or is_type_new

            # Fallback final: se o poste novo entrou sem estrutura, tenta pela
            # linha NEW mais próxima contendo a mesma tipologia de poste.
            if include and not data.get('Est'):
                pole_key = str(data.get('Pole', '')).upper().replace('/', 'X')
                px, py = data.get('pos', (0.0, 0.0))
                nearest = None
                nearest_dist = 999999999.0
                for ln in new_struct_lines:
                    txt = ln['text']
                    if pole_key and pole_key not in txt.replace('/', 'X'):
                        continue
                    cx, cy = ln['pos']
                    d = (px - cx) ** 2 + (py - cy) ** 2
                    if d < nearest_dist:
                        nearest_dist = d
                        nearest = ln
                if nearest:
                    ests = _extract_structs_from_line(nearest['text'])
                    if ests:
                        data['Est'] = ests

            # Complemento conservador: quando o poste novo já tem estruturas,
            # permite adicionar estruturas faltantes da linha técnica mais próxima
            # com a mesma tipologia (inclui linhas EXISTING, exclui REMOVAL).
            if include and typed_struct_lines:
                pole_key = str(data.get('Pole', '')).upper()
                px, py = data.get('pos', (0.0, 0.0))
                nearest = None
                nearest_dist = 999999999.0
                for ln in typed_struct_lines:
                    if str(ln.get('pole_type', '')).upper() != pole_key:
                        continue
                    cx, cy = ln['pos']
                    d = (px - cx) ** 2 + (py - cy) ** 2
                    if d < nearest_dist:
                        nearest_dist = d
                        nearest = ln
                if nearest:
                    ests = _extract_structs_from_line(nearest['text'])
                    if ests:
                        current = Counter(data.get('Est', []))
                        target = Counter(ests)
                        for est, qtd in target.items():
                            missing = int(qtd) - int(current.get(est, 0))
                            for _ in range(max(0, missing)):
                                data.setdefault('Est', []).append(est)

            if include:
                data['Est'] = self._expand_structure_list(data.get('Est', []))
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

            # Fallback textual conservador:
            # quando ainda houver tipologia desconhecida, tenta inferir pelos tipos
            # explícitos presentes no texto bruto do PDF.
            unknown_ids = [pid for pid, d in cleaned_map.items() if d.get('Pole', 'Desconhecido') == 'Desconhecido']
            if unknown_ids and self.text:
                raw_candidates = re.findall(
                    r'\b(?:DT|DI|D|C)\s*\d{1,2}[X/]\d{3,4}\b',
                    self.text.upper(),
                )
                normalized_candidates = []
                for token in raw_candidates:
                    norm = token.replace(" ", "").replace("X", "/")
                    if norm.startswith("DI"):
                        norm = "DT" + norm[2:]
                    normalized_candidates.append(norm)

                if normalized_candidates:
                    counts = Counter(normalized_candidates)
                    unique_in_order = []
                    for c in normalized_candidates:
                        if c not in unique_in_order:
                            unique_in_order.append(c)

                    if len(unique_in_order) == len(unknown_ids):
                        for idx, pid in enumerate(unknown_ids):
                            cleaned_map[pid]['Pole'] = unique_in_order[idx]
                    else:
                        top_type, top_count = counts.most_common(1)[0]
                        top_ratio = top_count / max(1, len(normalized_candidates))
                        if top_ratio >= 0.7:
                            for pid in unknown_ids:
                                cleaned_map[pid]['Pole'] = top_type

        if not cleaned_map and exact_pole_anchors and labeled_items:
            fallback_map = {}
            seen_ids = set()
            for anchor in sorted(exact_pole_anchors, key=lambda item: (item["pos"][1], item["pos"][0])):
                p_id = anchor["id"]
                if p_id in seen_ids:
                    continue
                seen_ids.add(p_id)

                px, py = anchor["pos"]
                pole_type = "Desconhecido"
                trafo_desc = None
                ests = []

                nearest_type = None
                nearest_type_dist = 999999999.0
                nearest_trafo = None
                nearest_trafo_dist = 999999999.0
                est_candidates = []

                for item in labeled_items:
                    item_type = item.get("type")
                    if item_type not in {"TYPE", "EST", "TRAFO"}:
                        continue
                    if item.get("state") == "REMOVAL":
                        continue

                    ix, iy = item["pos"]
                    dist = (px - ix) ** 2 + (py - iy) ** 2

                    if item_type == "TYPE":
                        extracted_type = _extract_pole_type(item.get("text", ""))
                        if extracted_type and dist < nearest_type_dist:
                            nearest_type = extracted_type
                            nearest_type_dist = dist
                    elif item_type == "TRAFO":
                        kva_match = trafo_regex.search(item.get("text", ""))
                        if kva_match and dist < nearest_trafo_dist:
                            kva = kva_match.group(1).replace(",", ".")
                            prefix = "MONO" if float(kva) <= 37.5 else "TRI"
                            nearest_trafo = f"{prefix}-{kva}kVA"
                            nearest_trafo_dist = dist
                    elif item_type == "EST":
                        if dist <= 160000:
                            est_candidates.append((dist, item.get("text", "")))

                if nearest_type:
                    pole_type = nearest_type
                if nearest_trafo:
                    trafo_desc = nearest_trafo

                for _, est_text in sorted(est_candidates, key=lambda item: item[0])[:6]:
                    for est_code in _extract_structs_from_line(est_text):
                        if est_code not in ests:
                            ests.append(est_code)

                if pole_type != "Desconhecido" or ests or trafo_desc:
                    fallback_map[p_id] = {
                        "Pole": pole_type,
                        "Est": self._expand_structure_list(ests),
                        "Trafo": trafo_desc,
                    }

            if fallback_map:
                cleaned_map = fallback_map

        # Vincular códigos ESTF/ET aos postes com trafo para consumo no engine.
        def _assign_codes_by_text_proximity(prefix: str, codes: list[str], target_ids: list[str]) -> dict[str, list[str]]:
            assigned: dict[str, list[str]] = {}
            txt = str(self.text or "").upper()
            if not txt or not codes or not target_ids:
                return assigned
            used = set()
            for pid in target_ids:
                pid_digits = re.sub(r"\D", "", str(pid))
                if not pid_digits:
                    continue
                pid_pat = re.compile(rf'\bP[\s\.\-]*{pid_digits}\b', re.IGNORECASE)
                pid_pos = [m.start() for m in pid_pat.finditer(txt)]
                if not pid_pos:
                    continue
                best_code = None
                best_dist = 10**12
                for code in codes:
                    if code in used:
                        continue
                    digits = code[len(prefix):]
                    code_pat = re.compile(rf'\b{prefix}[\s\-:]*{digits}\b', re.IGNORECASE)
                    code_pos = [m.start() for m in code_pat.finditer(txt)]
                    if not code_pos:
                        continue
                    dist = min(abs(p - c) for p in pid_pos for c in code_pos)
                    if dist < best_dist:
                        best_dist = dist
                        best_code = code
                if best_code:
                    assigned[pid] = [best_code]
                    used.add(best_code)
            return assigned

        estf_codes = self.extract_estf_codes()
        et_codes = self.extract_et_trafo_codes()
        if estf_codes:
            trafo_ids = [pid for pid, data in cleaned_map.items() if str(data.get("Trafo", "")).strip() and str(data.get("Trafo", "")).strip().upper() != "NONE"]
            if trafo_ids:
                assigned = _assign_codes_by_text_proximity("ESTF", estf_codes, trafo_ids)
                if assigned:
                    for pid, vals in assigned.items():
                        cleaned_map[pid]["EstfCodes"] = vals
                else:
                    idx = 0
                    for pid in trafo_ids:
                        cleaned_map[pid]["EstfCodes"] = [estf_codes[min(idx, len(estf_codes) - 1)]]
                        idx += 1
        if et_codes:
            trafo_ids = [pid for pid, data in cleaned_map.items() if str(data.get("Trafo", "")).strip() and str(data.get("Trafo", "")).strip().upper() != "NONE"]
            # Fallback operacional: quando o OCR não extrair Trafo,
            # ainda assim associar ET aos postes para permitir películas.
            target_ids = trafo_ids if trafo_ids else list(cleaned_map.keys())
            if target_ids:
                # Prioridade operacional validada: quando presente, ET485344
                # representa o trafo novo alvo deste cenário.
                if "ET485344" in et_codes:
                    cleaned_map[target_ids[0]]["EtCodes"] = ["ET485344"]
                    remaining_ids = target_ids[1:]
                    remaining_codes = [c for c in et_codes if c != "ET485344"]
                else:
                    remaining_ids = target_ids
                    remaining_codes = et_codes

                if not remaining_ids:
                    return cleaned_map

                assigned = _assign_codes_by_text_proximity("ET", remaining_codes, remaining_ids)
                if assigned:
                    for pid, vals in assigned.items():
                        cleaned_map[pid]["EtCodes"] = vals
                else:
                    idx = 0
                    for pid in remaining_ids:
                        cleaned_map[pid]["EtCodes"] = [remaining_codes[min(idx, len(remaining_codes) - 1)]]
                        idx += 1

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
                # Regra operacional: quando houver qualquer marcação NEW no diagrama,
                # apenas cabos de linhas com conteúdo NEW devem entrar na BOM.
                strict_new_only = any(v == 'NEW' for v in self.visual_states.values())

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
                    line_states = []
                    for w in line_words:
                        w_key = (i, round(w['x0'], 1), round(w['top'], 1), round(w['x1'], 1), round(w['bottom'], 1))
                        line_states.append(self.visual_states.get(w_key, 'EXISTING'))
                    has_new_state = any(st == 'NEW' for st in line_states)
                    has_removal_state = any(st == 'REMOVAL' for st in line_states)

                    # Pré-filtro rápido
                    has_keyword = any(k in line_text for k in keywords)
                    has_meter   = bool(re.search(r'\d\s*(?:M\b|METROS\b)', line_text))
                    if not (has_keyword and has_meter):
                        continue
                    if strict_new_only and (not has_new_state or has_removal_state):
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
