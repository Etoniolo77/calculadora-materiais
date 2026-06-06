# Changelog — Calculadora de Materiais

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
