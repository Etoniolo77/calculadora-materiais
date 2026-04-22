# 📋 EXTRACTOR_RULES.md — Registro de Regras do Extrator

> **Objetivo:** Documentar cada regra, filtro e heurística aplicada no `extractor.py`.
> Qualquer alteração de regra DEVE ser registrada aqui primeiro.
> Isso permite rastrear impactos entre projetos e facilitar rollback cirúrgico.

---

## Como Usar Este Arquivo

| Ação | Passos |
|------|--------|
| **Adicionar regra** | 1. Criar entrada neste arquivo → 2. Implementar no `extractor.py` → 3. Testar com TODOS os PDFs listados em `Diagramas de Testes/` |
| **Remover regra** | 1. Verificar impacto nas PDFs afetadas → 2. Remover entrada → 3. Remover código |
| **Identificar conflito** | Cada regra lista os PDFs que a motivaram → verificar se há conflito antes de alterar |

---

## 🔧 Regras Ativas

---

### RULE-001 — Filtro de Área de Legenda (Threshold 85%)

**Arquivo:** `extractor.py` → `find_structures_per_pole()` → função `get_frag_state()`

**Motivação:** PDFs com tabela de rodapé (carimbo técnico, legendas, selos) contêm
retângulos na parte inferior da página. Esses retângulos interferiam na classificação
visual dos elementos (NEW/EXISTING) do diagrama.

**Implementação:**
```python
page_h = page.height
legend_y_threshold = page_h * 0.85

def get_frag_state(w):
    for r in rect_zones:
        if r['top'] > legend_y_threshold: continue  # REGRA: ignora rodapé
        ...
```

**Projetos testados:**
- ✅ `PROJETO_DESE_4001863357_F01-01_Rev0 (2).pdf` — rodapé em Y>1044 (pág. 1190px)
- ✅ `PROJETO_DESE_4001759672_F01-01_Rev0 - PROGRAMADO 21-12.pdf` — confirmado OK

**Risco de regressão:** Baixo. Threshold de 85% é conservador o suficiente para
não afetar diagramas com postes na parte inferior.

**Data:** 2026-02-25 | **Motivado por:** Projeto 4001863357

---

### RULE-002 — Filtro de ID de Poste com Referência GPS (P1=...)

**Arquivo:** `extractor.py` → `find_structures_per_pole()` → loop de palavras

**Motivação:** Alguns PDFs contêm uma tabela de coordenadas geográficas no corpo
do diagrama com linhas como `P1= 301103.5 M / 782...`. O regex de poste capturava
`P1` dessas linhas como postes reais, criando entradas falsas no pole_map.

**Implementação:**
```python
after_match = raw_text[p_match.end():].strip()
is_gps_ref = after_match.startswith('=')  # P1= 301103...
if not is_gps_ref:
    pole_map[p_id] = {...}
```

**Projetos testados:**
- ✅ `PROJETO_DESE_4001863357_F01-01_Rev0 (2).pdf` — havia P1= P2= P3= P4= P5= na área GPS

**Risco de regressão:** Baixo. Apenas descarta quando o próximo caractere é `=`.

**Data:** 2026-02-25 | **Motivado por:** Projeto 4001863357

---

### RULE-003 — Filtro de ID de Poste em Frase Longa

**Arquivo:** `extractor.py` → `find_structures_per_pole()` → loop de palavras

**Motivação:** Texto descritivo como `'ARVORES ENTRE O PONTO P1 E P2'` continha
IDs de postes que eram capturados como postes reais.

**Implementação:**
```python
is_in_sentence = len(raw_text) > 30 and p_match.start() > 5
if not is_in_sentence:
    pole_map[p_id] = {...}
```

**Projetos testados:**
- ✅ `PROJETO_DESE_4001863357_F01-01_Rev0 (2).pdf` — tinha frase de observação com P1 e P2

**Risco de regressão:** Médio. Se um PDF tiver a nota de poste precedida por texto
longo na mesma palavra reconstruída, pode falhar.
**Mitigação:** O filtro `p_match.start() > 5` só ativa se P_ID não estiver no início
do token.

**Data:** 2026-02-25 | **Motivado por:** Projeto 4001863357

---

### RULE-004 — Flag IsInDiagram para Preservar Postes Sem Tipo/Estrutura

**Arquivo:** `extractor.py` → `find_structures_per_pole()` → limpeza final

**Motivação:** Postes do tipo "passagem" (sem estrutura construtiva nova) eram
descartados pela limpeza final porque tinham `Pole='Desconhecido'` e `Est=[]`.

**Implementação:**
```python
# Ao criar o poste no pole_map:
pole_map[p_id] = {
    ...
    'IsInDiagram': True  # preserva mesmo sem tipo/estrutura
}

# Na limpeza final:
include = (is_new_pole or has_new_content or is_in_diagram) if any_new else (...)
```

**Projetos testados:**
- ✅ `PROJETO_DESE_4001863357_F01-01_Rev0 (2).pdf` — P1 aparecia isolado sem estrutura

**Risco de regressão:** Médio-alto. Pode incluir postes de outros PDFs que eram
intencionalmente excluídos por serem referências e não postes reais.
**Mitigação:** A flag só é setada quando o poste passou pelos filtros RULE-001,
RULE-002 e RULE-003.

**Data:** 2026-02-25 | **Motivado por:** Projeto 4001863357

---

### RULE-005 — Modo Permissivo (any_new=False)

**Arquivo:** `extractor.py` → `find_structures_per_pole()` → limpeza final

**Motivação:** PDFs sem retângulos individuais por elemento (todos EXISTING) eram
completamente descartados. O modo permissivo aceita todos os postes quando
nenhum tem estado NEW.

**Implementação:**
```python
any_new = any(d.get('IsNew') or d.get('IsNewContent') for d in pole_map.values())
include = (...) if any_new else (has_type or has_structures or is_in_diagram)
```

**Projetos testados:**
- ✅ Projeto de manutenção (sem caixas NEW) — aceitaria todos os postes como válidos

**Risco de regressão:** Alto. PDFs mistos (com alguns NEW e alguns EXISTING) são
tratados pelo branch `any_new=True`, não afetando esse risco.

**Data:** 2026-02-25 | **Motivado por:** Análise geral do sistema

---

### RULE-006 — Filtro de P+Dígito como Estrutura

**Arquivo:** `extractor.py` → `find_structures_per_pole()` → associação EST

**Motivação:** IDs de postes (`P1`, `P2`) eram adicionados como estruturas de
outros postes quando apareciam em fragmentos concatenados.

**Implementação:**
```python
for est_code in est_matches:
    if re.match(r'^P\d+$', est_code, re.IGNORECASE):
        continue  # pular IDs de poste
```

**Projetos testados:**
- ✅ `PROJETO_DESE_4001863357_F01-01_Rev0 (2).pdf` — P1 tinha ['P2'] como estrutura falsa

**Risco de regressão:** Baixo. `P` seguido de dígito puro não é nome de estrutura válida.

**Data:** 2026-02-25 | **Motivado por:** Projeto 4001863357

---

### RULE-007 — Range de Associação 999px (Diagramas A3)

**Arquivo:** `extractor.py` → `find_structures_per_pole()` → nearest neighbor

**Motivação:** Range original de 600px era insuficiente para diagramas A3 com
postes distantes na lateral da folha.

**Implementação:**
```python
if dist < min_dist and dist < 999:  # ampliado de 600→999
```

**Projetos testados:**
- ✅ `PROJETO_DESE_4001863357_F01-01_Rev0 (2).pdf` — estruturas a ~700px do poste

**Risco de regressão:** Médio. Em projetos com muitos postes próximos, pode
associar estrutura ao poste errado.
**Mitigação:** A lógica sempre escolhe o mais próximo (min_dist), então o range
maior só impacta quando não há outro poste mais próximo.

**Data:** 2026-02-25 | **Motivado por:** Projeto 4001863357

---

### RULE-008 — Extração de Estruturas Embutidas no Token do Poste

**Arquivo:** `extractor.py` → `find_structures_per_pole()` → criação de poste no pole_map

**Motivação:** Alguns PDFs têm o ID do poste e suas estruturas na mesma palavra
reconstituída: `'P1 N4F,1S4(1)'`. O loop de associação não encontrava essas
estruturas porque o poste já era detectado primeiro.

**Implementação:**
```python
rest = raw_text[p_match.end():].strip()
if rest:
    for chunk in re.split(r'[,;\s]+', safe_rest):
        if t_regex.match(chunk): pole_map[p_id]['Pole'] = norm
        elif s_regex.match(chunk): pole_map[p_id]['Est'].append(chunk)
```

**Projetos testados:**
- ✅ `PROJETO_DESE_4001863357_F01-01_Rev0 (2).pdf`

**Risco de regressão:** Baixo. Só ativa quando há conteúdo após o ID do poste.

**Data:** 2026-02-25 | **Motivado por:** Projeto 4001863357

---

### RULE-009 — Detecção Automática de Layout (Modo por Caixas)

**Arquivo:** `extractor.py` → `find_structures_per_pole()` → pré-scan + `_find_poles_from_boxes()`

**Motivação:** Alguns PDFs não usam prefixos `P1/P2/P3...` para identificar postes.
Em vez disso, o tipo do poste e suas estruturas aparecem **dentro de retângulos**
(caixas) no diagrama. Ex: caixa contendo `'N4F-11/300DT 1-S4(1) 3-ESTAI 3/8"'`.

**Detecção:**
O pré-scan verifica se há ≥2 tokens isolados do tipo `P\d+` (sem contexto GPS ou texto)
na área do diagrama. Se não houver, ativa o modo por caixas.

**Implementação:**
```python
# Pré-scan via words com filtros RULE-001/002
explicit_p_ids_found = set()
for _w in _page.extract_words():
    if _w['top'] > _ly: continue  # RULE-001
    token = _w['text'].strip().rstrip('.')
    if re.match(r'^P\d+$', token, re.I):
        if not _after.startswith('='): # RULE-002
            explicit_p_ids_found.add(token.upper())

has_explicit_pids = len(explicit_p_ids_found) >= 2

if not has_explicit_pids:
    boxes = self._find_poles_from_boxes(page, i)
    # IDs gerados sequencialmente por posição
```

**Projetos testados:**
- ✅ `PROJETO_DESE_4001855774_F01-01_Rev0.pdf` — 5/5 caixas detectadas, modo ativado
- ✅ `PROJETO_DESE_4001863357_F01-01_Rev0 (2).pdf` — modo clássico mantido (regressão OK)

**Risco de regressão:** Médio. Se PDF com P_IDs tiver apenas 1 poste explícito,
pode ativar modo por caixas erroneamente.
**Mitigação:** Threshold `>= 2` reduz esse risco. Futuramente pode ser `>= 1`
se confirmado estável.

**Data:** 2026-02-25 | **Motivado por:** Projeto 4001855774

---

### RULE-010 — Normalização de Tokens com Hífens Concatenados

**Arquivo:** `extractor.py` → `_find_poles_from_boxes()`

**Motivação:** No modo por caixas, o PDF concatena tipo+estruturas com hífens:
`'N4F-11/300DT-1-S3(1)'`. O split simples por espaço não separa esses elementos.

**Implementação:**
```python
# Expandir tokens concatenados por hífen
for raw_token in re.split(r'[\s;,]+', combined):
    sub = re.split(r'(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])', raw_token)
    expanded_tokens.extend(sub)
```

**Projetos testados:**
- ✅ `PROJETO_DESE_4001855774_F01-01_Rev0.pdf` — `N4F-11/300DT` → `['N4F', '11/300DT']`

**Risco de regressão:** Baixo. Opera apenas no contexto do método `_find_poles_from_boxes`,
não afetando o modo clássico.

**Data:** 2026-02-25 | **Motivado por:** Projeto 4001855774

---

## 🗄️ Aliases de Estrutura (engine.py)

> Aliases não alteram o extrator — vivem em `engine.py → STRUCTURE_ALIASES`.
> O extrator extrai o nome como está no PDF; o engine normaliza antes de buscar no banco.

| Alias (PDF) | Canônico (DB) | Fonte/Norma |
|-------------|---------------|-------------|
| `S3` | `1S3` | Norma Enel/CPFL — estrutura ancoragem ramal |
| `S4` | `1S4` | Norma Enel/CPFL — estrutura ancoragem ramal |
| `S3(1)` | `1S3` | Variante com sufixo de quantidade |
| `S4(1)` | `1S4` | Variante com sufixo de quantidade |
| `H5` | `1HASTE` | Catálogo CPFL — Haste 5/8" 2.4m |
| `H3` | `1HASTE` | Catálogo CPFL — Haste 5/8" 2.4m |
| `1S3(1)` | `1S3` | Variante alternativa |
| `1S4(1)` | `1S4` | Variante alternativa |

---

## 📑 Projetos de Teste Conhecidos

| Arquivo | Postes | Resultado | Modo | Regras |
|---------|--------|-----------|------|--------|
| `PROJETO_DESE_4001863357_F01-01_Rev0 (2).pdf` | 5 (P1-P5) | ✅ 5/5 | Clássico (P_IDs) | RULE-001..008 |
| `PROJETO_DESE_4001855774_F01-01_Rev0.pdf` | 5 caixas | ✅ 5/5 | Por Caixas | RULE-009, RULE-010 |
| `PROJETO_DESE_4001759672_F01-01_Rev0 - PROGRAMADO 21-12.pdf` | ? | Pendente | — | — |

---

## ⚠️ Antes de Adicionar Nova Regra

1. **Identificar os projetos afetados** (quais PDFs motivaram a mudança)
2. **Testar com TODOS os outros PDFs** da pasta `Diagramas de Testes/`
3. **Documentar risco de regressão** (Baixo / Médio / Alto)
4. **Criar entrada aqui** antes de fazer commit

---

*Criado em 2026-02-25 — Projeto 13_Calculadora_Materiais*
