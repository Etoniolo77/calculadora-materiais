---
trigger: always_on
---

# PRJ-13 — Calculadora BOM

Ferramenta web para geração de BOM (Bill of Materials) a partir de PDFs de projetos elétricos. Extrai estruturas, postes, cabos e transformadores e mapeia para códigos SAP.

## Stack

- **Backend**: FastAPI (`backend/app_fastapi.py`, porta 8600) + motor em `core/`
- **Frontend**: HTML/CSS/JS vanilla (`frontend/`) — sem framework
- **Banco**: SQLite (`core/materials.db`) com tabela `materiais` (codigo, descricao)
- **Build**: PyInstaller para distribuição standalone

## Arquivos críticos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `core/engine.py` (81KB) | Lógica de cálculo BOM, mapeamentos SAP hardcoded |
| `core/extractor.py` (90KB) | Processamento de PDF com pdfplumber |
| `core/database_sqlite.py` | Acesso ao SQLite via `SAPCodesProxy` |
| `core/vocabulary.py` | Sinônimos e siglas técnicas |
| `core/validators.py` | Validação de regras de esforço e vão |
| `backend/app_fastapi.py` | API, autenticação HMAC-SHA256, endpoints |
| `frontend/app.js` (34KB) | State management + DOM — monolítico |
| `data/Bases_Dados/*.xlsx` | Fonte de alimentação do banco (não runtime) |

## Fontes de dados

- **SQLite** (`core/materials.db`): fonte primária de códigos SAP em runtime
- **Excel** (`data/Bases_Dados/`): alimenta o SQLite via `scripts/update_materiais_from_excel.py`
- **PDF**: entrada do usuário — processado por `extractor.py`
- **JSON** (`core/vocabulary.json`): sinônimos e mapeamentos semânticos

## Mapeamentos SAP hardcoded em engine.py

```
CINTA_SAP_MAP: diâmetros → códigos (ex: 100mm → 30053132)
ALCA_MT_NU_MAP: bitolas → alças (ex: 4ANA → 30050155)
ALCA_MT_PROT_MAP: cabos protegidos
MANUAL_EST_MAP: estruturas sem DB (fallback)
```

Atenção: estes mapeamentos devem eventualmente ser migrados para o SQLite.

## Padrões do projeto

- autenticação via HMAC-SHA256 com PIN em `auth/auth_config.json`
- versão em `app_version.json` — atualizar manualmente
- scripts de manutenção de banco em `scripts/`
- documentação técnica em `docs/`

## Skills a usar neste projeto

- `fastapi-excel-pipeline` — para qualquer novo endpoint que leia Excel ou banco
- `python-patterns` — padrões gerais de código Python
- `api-patterns` — design de endpoints
- `systematic-debugging` — para bugs em `engine.py` ou `extractor.py`
- `testing-patterns` — cobertura de `core/engine.py` é crítica

## Atenção — problemas conhecidos

- `frontend/app.js` é monolítico (34KB): não refatorar sem escopo definido
- mapeamentos SAP estão em 3 lugares (SQLite + Excel + hardcoded): usar SQLite como fonte de verdade
- `legacy/` contém código descontinuado: não referenciar
- credenciais em `auth/auth_config.json`: não adicionar mais segredos neste arquivo

## Iniciar localmente

```powershell
cd backend
python run_server.py
# Ou: uvicorn app_fastapi:app --port 8600 --reload
```
