# Changelog — Calculadora de Materiais

## 1.0.38 — 2026-06-10 — Fonte única: Excel "Lista Consolidada" + Aplicação

Correção definitiva da composição de estruturas (supersede os tapa-buracos da 1.0.37).

### Dados / pipeline
- **Reimportação fiel do Excel mestre** (`scripts/utils_and_deploy/import_estruturas_aplicacao.py`):
  a aba "Lista Consolidada" passa a ser a fonte única. `estrutura_materiais` ganha a
  coluna **`aplicacao`** (por material) e as **quantidades em texto** são parseadas
  (`"4,5MTS"`→4.5; `"2,4KG (15MTS)"`→15). `estruturas` colapsa para 1 linha por código.
  Backup das tabelas antigas em `data/_backup_mestre/`.

### Engine (`core/database_sqlite.py`, `core/aplicacao.py`)
- **`explode_structure` seleciona material por tipo de poste** via a coluna Aplicação
  (`aplicacao_matches`): `ALL`, `12X600 CIRCULAR`, `TODOS EXETO 11X300DT…`, `NO CABO …`.
  Acaba com o "menu" de cintas/suportes — cada poste recebe só o que se aplica a ele.
- Resolve de uma vez, na fonte: cintas/suportes por diâmetro, quantidades de cabo
  protegido (4,5) e cordoalha (15 m), e remove os códigos velhos. Validado no OV
  4001739539 (P4 C12/600: cintas B-20:2/B-24:1, suporte 255mm:2, sem 240mm).

### Validação
- 36 testes unitários + regressão dos 13 PDFs (13 OK, 0 mismatches acionáveis).

## 1.0.37 — 2026-06-10

### Engine (`core/engine.py`) — correções de BOM do trafo (OV 4001739539)
- **Poste-trafo migrado para o Supabase como fonte única**: quando o poste tem
  estrutura ET de trafo resolvível no banco (ET1T/ET4A/ET1BR), o transformador e
  acessórios vêm dessa estrutura (códigos novos). O caminho legado
  (`resolve_transformers_direct` textual + `hardware_kits` do unified_db +
  suporte hardcoded) é pulado. Elimina códigos velhos duplicados (10002581,
  10004254, 10010733, 10011197, 10012874) e o trafo duplicado.
- **Parafuso M16 (30058226) por cinta removido**: as estruturas do banco já
  trazem seus parafusos; a regra duplicava (aparecia em P2/P3).
- **Cordoalha de aterramento (30054511)**: placeholder unitário vira 15 m por descida.
- **Película dígito 9 → 30058699** (mesma do 6, basta virar); resolve token órfão
  e a soma correta quando o código tem 6 e 9.

### Dados
- **`cinta_lookup` (data/unified_db.json)** corrigido/expandido com a tabela
  canônica de diâmetros por poste e categoria (CINTA/NIVEL/ESTAI/RECK níveis 1 e 2).
  Antes só havia "CINTA 1" com o maior diâmetro (ex.: 12/600 = 240; correto = 200).
- **Supabase `estrutura_materiais`**: cabo protegido 16mm (30051709) ajustado de 1
  para **4.5** nas 12 estruturas ET de trafo monofásico.

> Pendente nesta versão: seleção de cinta/suporte por diâmetro na estrutura de
> trafo (menu B-18..B-38 / suportes 240–400mm) — requer regra de suporte e
> validação com a extração real do projeto.

## 1.0.36 — 2026-06-10

### Engine (`core/engine.py`)
- **Cabo MT NX2ANA — multiplicador de vias dinâmico** (`resolve_cables_direct`): o
  número de vias de 2AWG SPARROW (fases) agora vem do prefixo "NX" da descrição
  (3X→3, 1X/sem prefixo→1) em vez de fixo em 3. O neutro 4AWG ROSE segue 1× o trecho.
  Corrige OV 4001739539, onde uma derivação **1F** (`MT 1x2ANA(4ANA)`) faturava
  304.38 m de SPARROW (101.46 × 3) quando o correto é 101.46 m.
- Teste de regressão `test_mt_cable_sparrow_multiplier_follows_phase_count`.

## 1.0.35 — 2026-06-10

### Autenticação Supabase (`frontend/app.js`, `frontend/login.html`)
- **Correção "Sessão inválida ou expirada no Supabase"**: o cookie do backend guardava o
  `access_token` (que expira em 1h) com validade de 7 dias, mas o `refresh_token` nunca era
  reaproveitado — após ~1h toda chamada `/api/*` retornava 401.
- O cliente Supabase passa a usar `persistSession` + `autoRefreshToken` explícitos e re-sincroniza
  o cookie do backend em `TOKEN_REFRESHED`/`SIGNED_IN` (`onAuthStateChange`).
- `ensureAuthenticatedSession` agora renova proativamente a sessão (margem de 60s) antes de sincronizar.
- `apiFetch` recupera 401 automaticamente: renova a sessão, re-sincroniza o cookie e refaz a
  requisição uma vez antes de redirecionar ao login.

## 1.0.34 — 2026-06-06

### Extrator (`core/extractor.py`)
- **Spine canônico de postes**: a lista de P_IDs do prescan virou a fonte de verdade.
  Postes com conteúdo NEW que falhavam na associação por proximidade não são mais descartados
  silenciosamente (resgate de P1/P6 em layouts ramificados). Ver `docs/Regras de Extração.md`.
- **GPS em formato traço**: `P10-313425/7754582` agora é filtrado como referência de coordenada
  (antes corrompia a posição do poste e desalinhava estruturas).
- **`strict_new_only` recalculado** após análise visual da página (antes podia ficar falso e deixar
  passar estruturas EXISTING/REMOVAL).
- **Retrofit `(E)`**: poste existente que recebe só estrutura nova é marcado com sufixo `(E)` e
  traz apenas a estrutura nova (o poste não é faturado).
- **Cabos de contexto**: cabo BT existente é capturado como contexto (marcado `(E)`, não faturado)
  para resolver a variante de SMTR/SMFL quando a rede secundária é pré-existente.
- **Trafo de nota em prosa**: notas como "INSTALAÇÃO DE 1 TRANSFORMADOR DE 45KVA" não são mais
  interpretadas como trafo de poste (evita trafo fantasma).

### Engine (`core/engine.py`)
- **Variante SMTR/SMFL 3X120(70)** → `CABO AL PE RET 4C 3X120MM2 70MM2 1KV`.
- **Parafuso M16 por cinta**: cada cinta de poste passa a injetar 1 parafuso de fixação M16
  (`FASTENER_BOLT` 30058226), antes ausente.
- Poste com sufixo `(E)`/`(R)` não é faturado (correção do round-trip do marcador).

### Backend (`backend/app_fastapi.py`)
- **Ordenação numérica de postes** (P1, P2, … P10, P11) em vez de lexicográfica.
- `_normalize_pole_label` preserva o sufixo `(E)`/`(R)` (round-trip extract → frontend → calculate).
- Recomendações deixam de duplicar erros de validação técnica.

### Frontend (`frontend/`)
- Painéis "Validação Técnica" e "Gate de Qualidade" **unificados** em um único box compacto.
- Correção da textarea de justificativa (perdia foco a cada tecla).
- Alinhamento do checkbox de override; ícone/favicon alterado de "E" para "C".

### Relatório PDF (`core/final_report.py`)
- Fundo escuro do cabeçalho e da tabela removido (economia de tinta); identidade visual mantida
  por textos/linhas azuis.
- Coluna "Item" removida da tabela de materiais.

### Projeto / 5S
- Stack de produção consolidada em **Vercel + Supabase**; removidos artefatos de desktop e IIS
  (instaladores, runtime empacotado, scripts e docs de publicação on-prem).
- Documentação de regras consolidada em `docs/Regras de Extração.md` (substitui `EXTRACTOR_RULES.md`).
- Ferramentas de regressão: `scripts/extractor_snapshot.py` e `scripts/validate_pdf_regression_batch.py`.

Validação: 13/13 PDFs de teste processados, 0 erros, 0 mismatches acionáveis.
