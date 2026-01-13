import pdfplumber
import re
import math

class ProjectExtractor:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.text = ""
        # Cache de estados visuais por palavra: {(page_num, x0, y0, x1, y1): 'NEW'|'REMOVAL'|'EXISTING'}
        self.visual_states = {}

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
        """Tenta extrair informações de cabeçalho como Código do Projeto."""
        info = {'Ordem': ''}
        match = re.search(r'(\d{10})', self.text)
        if match:
            info['Ordem'] = match.group(1)
        return info

    def find_structures_per_pole(self):
        """
        Identifica postes e associa estruturas, agora filtrando por estado visual.
        Retorna: {'P1': {'Pole': '', 'Est': ['N1', 'U3'], 'Trafo': None, ...}, ...}
        """
        if not self.text:
            return {}

        # Precisamos trabalhar com as palavras e suas coordenadas para manter o estado visual
        pole_map = {}
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                words = page.extract_words()
                # Sort words by top then x0
                words.sort(key=lambda w: (w['top'], w['x0']))
                
                current_pid = None
                p_x, p_y = 0, 0
                
                # Regex para Poste: P1, P-1, P.1, POSTE 1
                p_regex = re.compile(r'^(P[\.\-]?\d+|POSTE?\s*\d+)$')
                # Regex para Tipo de Poste: C12/600, DT11/300, etc.
                t_regex = re.compile(r'^([A-Z]{1,2}\d{2}[xX/ \-]\d{3,4})$')
                
                # Estruturas padrão
                s_regex = re.compile(r'^([A-Z]{1,2}\d[A-Z0-9]*|ET\d+[A-Z]*|[1-4]S\d)$')

                for j, word in enumerate(words):
                    text = word['text'].strip().upper()
                    w_key = (i, round(word['x0'], 1), round(word['top'], 1), round(word['x1'], 1), round(word['bottom'], 1))
                    state = self.visual_states.get(w_key, 'EXISTING')

                    # 1. Detectar Poste (PID)
                    if p_regex.match(text):
                        # Relaxamos a restrição: apenas ignorar cabeçalho extremo superior
                        if word['top'] > 50: 
                            current_pid = text
                            if current_pid not in pole_map:
                                pole_map[current_pid] = {'Pole': 'Desconhecido', 'Est': [], 'Trafo': None, 'Chave': None, 'State': state}
                                p_x, p_y = word['x0'], word['top']

                    # 2. Detectar Tipo (se houver poste ativo e texto próximo)
                    elif current_pid and t_regex.match(text):
                        if abs(word['top'] - p_y) < 60:
                            norm_type = text.replace('X', '/').replace('x', '/').replace(' ', '').replace('-', '/')
                            # Tags: NEW(vazio), REMOVAL(R), EXISTING(E)
                            tag = ""
                            if state == 'REMOVAL': tag = "(R)"
                            elif state == 'EXISTING': tag = "(E)"
                            pole_map[current_pid]['Pole'] = f"{norm_type}{tag}"

                    # 3. Detectar Estrutura
                    elif current_pid and s_regex.match(text):
                        dy = word['top'] - p_y
                        if -20 < dy < 200:
                            # Apenas incluímos se for NOVO ou REMOÇÃO
                            if state == 'NEW':
                                final_est = text
                                if final_est not in pole_map[current_pid]['Est']:
                                    pole_map[current_pid]['Est'].append(final_est)
                            elif state == 'REMOVAL':
                                final_est = f"{text}(R)"
                                if final_est not in pole_map[current_pid]['Est']:
                                    pole_map[current_pid]['Est'].append(final_est)

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

        # Filtro Absoluto: Manter APENAS os postes detectados como NOVOS (dentro de caixa)
        cleaned_map = {}
        for p_id, data in pole_map.items():
            if data.get('State') == 'NEW':
                # Limpar tags residuais se houver
                data['Pole'] = data['Pole'].replace("(E)", "").replace("(R)", "").strip()
                cleaned_map[p_id] = data
                
        return cleaned_map

    def find_cables(self):
        """Extrai cabos e suas metragens, respeitando o estado visual."""
        cables_found = []
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
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
                    
                    # Regex para metragem: MT ... 24.9m
                    # Buscamos o padrão (MT ou BT) e depois o número seguido de 'm'
                    if ("MT" in line_text or "BT" in line_text) and "M" in line_text:
                        # Identificar qual palavra é o "MT/BT" para pegar o estado dela
                        for j, word in enumerate(line_words):
                            text = word['text'].upper()
                            if text in ["MT", "BT"]:
                                w_key = (i, round(word['x0'], 1), round(word['top'], 1), round(word['x1'], 1), round(word['bottom'], 1))
                                state = self.visual_states.get(w_key, 'EXISTING')
                                
                                if state != 'EXISTING':
                                    # Pegar a metragem na mesma linha
                                    full_line = " ".join([w['text'] for w in line_words[j:]])
                                    match = re.search(r'((?:MT|BT)\s+.*)\s+([\d]+(?:[.,][\d]+)?)M', full_line)
                                    if match:
                                        desc = match.group(1).strip()
                                        qty = float(match.group(2).replace(',', '.'))
                                        tipo = 'MT' if 'MT' in desc else 'BT'
                                        
                                        if state == 'REMOVAL':
                                            desc += " (RETIRADA)"
                                            cables_found.append({'Tipo': tipo, 'Desc': desc, 'Qtd': qty})
                                        elif state == 'NEW':
                                            cables_found.append({'Tipo': tipo, 'Desc': desc, 'Qtd': qty})
                                    break
        return cables_found

    def get_summary_structures(self, pole_map):
        """Quantifica total de estruturas para o resumo inicial."""
        summary = {}
        for p_data in pole_map.values():
            for est in p_data['Est']:
                summary[est] = summary.get(est, 0) + 1
        return summary
