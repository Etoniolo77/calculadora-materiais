# ⚡ Calculadora de Materiais — Eletromarquez

Ferramenta web para extração, cálculo e geração de Listas de Materiais (BOM — Bill of Materials)
a partir de projetos de redes elétricas em PDF.

## Stack oficial

- **Backend**: FastAPI (`backend/app_fastapi.py` em dev; `api/index.py` na Vercel)
- **Frontend**: HTML/CSS/JS estático em `frontend/`
- **Motor de negócio**: módulos em `core/`
- **Banco (runtime)**: **Supabase (PostgreSQL)** — códigos SAP e estruturas
- **Hospedagem (produção)**: **Vercel** (serverless) + Supabase

## 🚀 Funcionalidades

- **Extração automática**: detecta postes, estruturas, cabos, transformadores e quantidades no PDF.
- **Cálculo inteligente**: "explode" estruturas técnicas em componentes (parafusos, braçadeiras, cruzetas…) por tipo de poste e norma.
- **Edição assistida**: interface para revisar/ajustar postes e equipamentos antes do cálculo.
- **Relatório PDF**: exportação da BOM consolidada (layout econômico para impressão).
- **De-para SAP**: tradução de descrições técnicas em códigos SAP via Supabase.

## 🛠️ Tecnologias

- Processamento de dados: Pandas
- Extração de PDF: pdfplumber
- Geração de PDF: ReportLab
- Banco: Supabase (PostgreSQL); `data/unified_db.json` como base consolidada de composições

## 📂 Estrutura

- `api/index.py` — entrypoint da Vercel (serverless).
- `backend/app_fastapi.py` — API e entrega do frontend (dev local).
- `frontend/` — interface (HTML/CSS/JS).
- `core/engine.py` — motor de cálculo de materiais.
- `core/extractor.py` — leitura e interpretação dos PDFs.
- `core/database_sqlite.py` — acesso ao banco (proxy Supabase).
- `data/unified_db.json` — composições de estruturas/kits.
- `data/vocabulary.json` — vocabulário técnico.
- `docs/Regras de Extração.md` — regras canônicas do extrator/engine.

## ⚙️ Executar localmente

```powershell
pip install -r requirements.txt
python backend/run_server.py        # ou: uvicorn backend.app_fastapi:app --port 8600 --reload
# Acesse http://127.0.0.1:8600/
```

Fluxo de uso: upload do PDF → revisar dados extraídos → ajustar postes/equipamentos → exportar CSV/PDF após validar a BOM.

## ☁️ Produção (Vercel + Supabase)

- Deploy: `vercel --prod` (projeto já linkado em `.vercel/`).
- Roteamento em `vercel.json` (`/api/*` → `api/index.py`; `/` → `frontend/index.html`).
- O banco de produção é o Supabase; alterações de **código** (extrator/engine/frontend) não exigem
  mudança no Supabase. Atualização de **dados** (materiais/estruturas) usa os scripts em
  `scripts/utils_and_deploy/` (`migrate_to_supabase.py`, `update_*_from_excel.py`).

## 🧹 Manutenção de dados

Scripts em `scripts/utils_and_deploy/` para sincronizar materiais/estruturas do Excel para o Supabase.
Regressão do extrator: `scripts/extractor_snapshot.py` (snapshot per-poste) e
`scripts/validate_pdf_regression_batch.py` (extrator + engine + BOM sobre os PDFs de teste).

---
*Desenvolvido para otimização de fluxos de engenharia elétrica · Eletromarquez.*
