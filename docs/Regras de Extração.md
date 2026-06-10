# Regras de Extração — Calculadora BOM (PRJ-13)

> Documento canônico das regras, filtros e heurísticas aplicadas na extração de
> postes, estruturas, cabos e equipamentos a partir dos PDFs de projeto elétrico.
> Substitui o antigo `EXTRACTOR_RULES.md`.
>
> **Arquivos-fonte:** `core/extractor.py` (extração) e `core/engine.py` (resolução SAP).
> **Validação:** qualquer alteração de regra deve passar por
> `scripts/extractor_snapshot.py` (snapshot per-poste) e
> `scripts/validate_pdf_regression_batch.py` (regressão extrator+engine+BOM) sobre
> os 13 PDFs em `docs/Diagramas de Testes/`.

**Atualizado:** 2026-06-10

---

## 1. Estados visuais (NEW / EXISTING / REMOVAL)

Toda a lógica de extração depende da classificação visual de cada fragmento de texto,
feita em `_analyze_page_visuals()` e na função interna `get_frag_state()`:

| Estado | Detecção | Significado |
|--------|----------|-------------|
| **NEW** | texto dentro de retângulo vermelho pequeno (≤300px largura, ≤60px altura) | item novo (faz parte do escopo) |
| **REMOVAL** | texto cruzado por linha horizontal (riscado) | item a ser retirado |
| **EXISTING** | nenhum dos anteriores | item pré-existente, mantido |

- **`strict_new_only`**: `True` quando existe **qualquer** estado NEW no PDF (todo projeto
  de revisão). É **recalculado após `_analyze_page_visuals` popular `self.visual_states`**
  — não pode ser lido no início da função (o cache de estados ainda está vazio).
- Em modo `strict_new_only`, apenas conteúdo NEW (e EXISTING que complementa poste NEW)
  entra no resultado.

---

## 2. Espinha dorsal canônica de postes (spine)

**Princípio:** a lista de P_IDs reais do prescan é a fonte de verdade dos postes do projeto.
Nenhuma estratégia isolada de detecção (caixa, proximidade, texto) é confiável em todos os
layouts; o prescan é. Implementado como camada de completude antes da atribuição ESTF/ET.

### 2.1 Prescan de P_IDs (`explicit_p_ids_found`)
- Captura tokens isolados `P\d+` na área do diagrama.
- `has_explicit_pids = len(...) >= 2` → ativa modo clássico (diagrama); senão, modo por caixas.

### 2.2 IDs canônicos
- Normaliza `P01 → P1` (remove zero à esquerda).
- Descarta tokens GPS concatenados tipo `P012527247760809` (mais de 2 dígitos).
- Mescla chaves duplicadas no resultado, mantendo a entrada mais rica (mais estruturas/tipo).

### 2.3 Completude do spine
Para cada P_ID canônico ausente do resultado mas com **conteúdo NEW próprio**:
- **Propriedade por âncora mais próxima**: um token NEW pertence ao poste cuja âncora de
  desenho é a mais próxima (raio ≤120px) — impede que vizinhos roubem conteúdo em layouts densos.
- **Extração robusta**: usa `_extract_structs_from_line()` e `_extract_pole_type()` direto no
  texto do token. **Não** confia no campo `type` do `labeled_item`, que falha em tokens
  compostos como `U3,1S3(1)` ou `H5-3/8M11x300,CE4,1S4(1)`.

### 2.4 Regra de inclusão (por precedência)
| Condição (do poste dono) | Resultado |
|--------------------------|-----------|
| tipo do poste é **NEW** | poste novo completo |
| tipo do poste é **EXISTING** + estrutura **NEW** | **retrofit** — tipo recebe sufixo `(E)` |
| sem tipo próprio, mas há tipo NEW vizinho | poste novo com esse tipo |
| só conteúdo EXISTING/REMOVAL (ou NEW de vizinho) | **excluído** (drop correto) |

### 2.5 Retrofit `(E)`
Poste existente que recebe apenas estrutura nova:
- Mantém só as estruturas NEW (`EstNew`).
- Tipo recebe sufixo `(E)` (ex.: `C12/600(E)`).
- O engine **não fatura o poste** (`resolve_clamps` ignora tipos com `(E)`/`(R)`), mas
  resolve as ferragens da estrutura nova pela tipologia (o `(E)` é removido na normalização).

---

## 3. Filtros de P_ID (evitam falsos postes)

| Regra | Filtro | Motivação |
|-------|--------|-----------|
| **Legenda/rodapé** | ignora retângulos com `top > 85%` da altura da página | carimbo técnico tem retângulos que confundem o estado visual |
| **Referência GPS** | descarta `P1= 301103.5` e `P10-313425/7754582` (par UTM `\d{5,}/\d{5,}`) | tabela de coordenadas no corpo do diagrama |
| **Frase longa** | descarta P_ID dentro de texto descritivo (`len>30 e start>5 e texto após`) | notas como "árvores entre P1 e P2" |
| **P+dígito como estrutura** | `^P\d+$` nunca é tratado como estrutura | IDs em fragmentos concatenados |

---

## 4. Detecção de tipologia de poste

- Token de tipo: `C/D/DT/M + altura/esforço` (ex.: `C12/300`, `DT11/600`).
- Normalizações de OCR: `DI → DT`, `M → C` (circular), `X → /`.
- Modo por caixas (`_find_poles_from_boxes`): tipo e estruturas vêm de dentro de retângulos;
  tokens concatenados por hífen (`N4F-11/300DT-1-S3(1)`) são expandidos.

---

## 5. Associação de estruturas (modo clássico)

- **Nearest-neighbor** com raio de **999px** (cobre diagramas A3); sempre escolhe o poste
  mais próximo.
- **Viés para NEW**: estrutura em estado NEW prefere poste com marcação NEW se estiver
  dentro de 1.5× a distância do mais próximo geral (evita que poste existente roube
  estrutura nova de vizinho).
- Estruturas embutidas no token do poste (`P1 N4F,1S4(1)`) são extraídas na criação.

---

## 6. Resolução de estrutura → código SAP (engine)

Ordem em `_resolve_structure_code()`:
1. Código exato no banco (Supabase) **sempre vence**.
2. Resolução contextual (depende de tipo de poste, kVA do trafo, estai).
3. Variante de **SMTR/SMFL** (ver §7).
4. Alias (`STRUCTURE_ALIASES`) só como fallback.

**Aliases conhecidos:** `S3→1S3`, `S4→1S4`, `H5/H3→1HASTE`, variantes com sufixo `(1)`.

Estruturas contextuais de trafo (`ET1T`, `ET4`, `ET4A`, `ET1BR`) resolvem pelo kVA + fase +
códigos ET/ESTF, não por busca direta de nome.

---

## 7. Variantes de SMTR / SMFL (rede secundária)

SMTR (montagem de rede secundária) e SMFL escolhem sua variante pela **bitola do cabo BT**:

| Padrão na descrição do cabo | Variante |
|-----------------------------|----------|
| `3X70` + (70) | `... AL 4C 3X70MM2+70MM2 1KV` |
| `2X70` + (70) | `... AL 3C 2X70MM2+70MM2 1KV` |
| `3X35` + (35) | `... AL 4C 3X35MM2+35MM2 1KV` |
| `2X120` / `120MM2+70MM2` | `... AL 3C 2X120MM2+70MM2 1KV` |
| `3X120` + `70` | `... AL PE RET 4C 3X120MM2 70MM2 1KV` |
| `XLPENI` + `35` | `... MULT XLPENI AL 3C 2X35MM2+35MM2 1KV` |

> Para `3X120+70` o catálogo só tem a variante **PE RET** (polietileno reticulado), então o
> padrão mapeia para ela mesmo sem o termo "PE RET" no texto do cabo.

---

## 8. Extração de cabos (`find_cables`)

- Filtro: linha precisa ter keyword de cabo (MT/BT/CABO/AL/...) **e** metragem (`NNN M`).
- Cascata de regex (do específico ao genérico): `MT/BT ...` → `CABO/FIO/...` → `AL/COBRE/NU...` → genérico.
- Classificação MT vs BT por palavras-chave (`15KV`/`MT` vs `1KV`/`BT`/`MULTIPLEX`).

**Faturável vs contexto (modo revisão):**
| Estado do cabo | Tratamento |
|----------------|-----------|
| **NEW** | faturado; tem **precedência** na detecção de variante (retornado primeiro) |
| **EXISTING** com bitola | **não faturado** (marcado `(E)`), mas serve de **contexto** para a variante SMTR/SMFL — montagem nova sobre rede secundária existente |
| **REMOVAL** | descartado totalmente |

> O engine pula cabos com `(E)` no faturamento (`resolve_cables_direct`), mas a detecção de
> variante lê a bitola — resolvendo SMTR/SMFL mesmo quando a rede secundária é pré-existente.

### 8.1 Cabo MT nu CAA `NX2ANA(4ANA)` → ROSE + SPARROW

Cabo MT nu de alumínio/CAA descrito como `NX2ANA(4ANA)` (gatilho: `tipo == "MT"` e a
descrição contém `2ANA`/`4ANA`/`2AN`/`4AN`) é desdobrado em duas linhas de BOM em
`resolve_cables_direct`:

| Código SAP | Material | Função | Quantidade |
|------------|----------|--------|------------|
| `10050897` | CABO NU ALUMINIO 4AWG 7F ROSE | **neutro** | `metragem` (sempre 1× o trecho) |
| `10050898` | CABO NU CAA AL 2AWG SPARROW | **fase(s)** | `metragem × N` |

- **`N` (nº de vias/fases)** vem do prefixo `NX` da descrição: `3X2ANA → 3` (trifásico),
  `2X2ANA → 2` (bifásico), `1X2ANA` ou sem prefixo → `1` (monofásico). Parse:
  `re.search(r"(\d+)\s*X\s*\d*\s*AN", desc_up)`, default `1`.
- **Por que SPARROW é a fase e ROSE o neutro:** em AWG, número menor = condutor mais grosso;
  2AWG (SPARROW) > 4AWG (ROSE), então o SPARROW carrega carga (fases) e o ROSE é o neutro.
- **Regressão (OV 4001739539):** antes o multiplicador era fixo em `3`, faturando 3× o
  SPARROW em derivações 1F/2F. `MT 1x2ANA(4ANA)` com 101.46 m saía 304.38 m; agora sai
  101.46 m. Coberto por `tests/test_production_logic.py::test_mt_cable_sparrow_multiplier_follows_phase_count`.

> **Atenção (escopo futuro):** o gatilho é amplo (qualquer MT com `2AN`/`4AN`). Bitolas
> diferentes que usem nomenclatura parecida (ex.: `1/0`, `4/0` CAA) cairiam nesta regra e
> mapeariam para ROSE/SPARROW — revisar caso surjam.

---

## 8.2 Poste com transformador (fonte = Supabase)

A montagem do poste-trafo segue o Supabase como **fonte única**:

- Se o poste tem uma estrutura ET de trafo resolvível no banco (`ET1T`/`ET4A`/`ET1BR`,
  resolvida por `_resolve_contextual_structure_code` para o código completo como
  `ET1T- MONO 15KVA 1F`), o **transformador e todos os acessórios vêm dessa estrutura**
  (códigos novos). O caminho legado é **pulado** (`trafo_from_db_structure`):
  `resolve_transformers_direct` (busca textual do trafo), os `hardware_kits` do
  `unified_db.json` (`TRAFO_MONO`/`TRAFO_TRI_45`, **códigos velhos**) e o suporte
  hardcoded. Sem isso, novos e velhos coexistiam (10002581, 10004254, 10010733,
  10011197, 10012874 duplicados).
- **Película de identificação** (`ESTF_STICKER_MAP`): o dígito **9 usa a mesma película
  do 6** (`30058699`) — basta virar a peça. Por isso `9 → 30058699`.
- **Cordoalha de aterramento** (`30054511`): quantidade unitária (placeholder) das
  estruturas vira **15 m por descida**.
- **Cinta/suporte por diâmetro** *(pendente)*: a estrutura de trafo no banco lista um
  "menu" de diâmetros (cinta B-18..B-38, suporte 240–400mm). A seleção do item correto
  por diâmetro do poste usa o `cinta_lookup` (tabela canônica por poste × categoria
  CINTA/NIVEL/ESTAI/RECK, níveis 1 e 2). A seleção do **suporte** por diâmetro ainda
  carece de regra/tabela.

## 9. Saída e ordenação

- Postes retornados ordenados **numericamente** (`P1, P2, ..., P10, P11`), não lexicográfico
  — chave `_pole_sort_key` em `backend/app_fastapi.py`.
- `Pole='Desconhecido'` é mantido (exposto para revisão manual) em vez de inferir tipo dominante.

---

## Procedimento ao alterar uma regra

1. `python scripts/extractor_snapshot.py --save baseline.json` (antes).
2. Alterar o código.
3. `python scripts/extractor_snapshot.py --compare baseline.json` → classificar cada diff
   como intencional ou regressão.
4. `python scripts/validate_pdf_regression_batch.py` → confirmar 0 erros / 0 mismatches acionáveis.
5. Registrar a mudança aqui.
