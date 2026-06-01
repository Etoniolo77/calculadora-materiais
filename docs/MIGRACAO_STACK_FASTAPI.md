# Migracao de Stack - Streamlit para FastAPI + HTML

> Documento historico. Mantido apenas como registro da decisao de migracao. O runtime oficial atual do projeto e `FastAPI + frontend estatico`.

Data: 2026-04-22
Projeto: PRJ-13-Calculadora

## 1. Motivo da migracao
- Publicacao via IIS/ARR com Streamlit permaneceu com loading infinito no frontend, mesmo com:
  - `/ _stcore/health` = 200
  - `/ _stcore/host-config` = 200
  - WebSocket upgrade = 101
- O ambiente apresentou instabilidade adicional com Python 3.14 + watchdog.

Decisao: trocar para stack sem WebSocket para publicacao robusta no IIS.

## 2. Seguranca da mudanca (backup/versionamento)
- Backup local em zip:
  - `archive\backup_pre_migracao_fastapi_20260422_084136.zip`
- Branch de seguranca no GitHub:
  - `backup/pre-migracao-fastapi-20260422`
  - URL: `https://github.com/Etoniolo77/calculadora-materiais/tree/backup/pre-migracao-fastapi-20260422`

## 3. Nova arquitetura
- Backend: FastAPI (`backend/app_fastapi.py`)
- Frontend: HTML/CSS/JS estatico (`frontend/`)
- Reuso da logica legada:
  - `core/extractor.py`
  - `core/engine.py`
  - `core/validators.py`
  - `core/final_report.py`

## 4. Endpoints novos
- `GET /health`
- `GET /` (frontend principal)
- `POST /api/extract` (upload PDF + extracao)
- `POST /api/calculate` (calculo BOM)
- `POST /api/export/csv`
- `POST /api/export/pdf`

## 5. Scripts operacionais
- Start FastAPI:
  - `scripts/start_internal_fastapi.ps1 -UseSystemPython`
- Stop FastAPI:
  - `scripts/stop_internal_fastapi.ps1`
- Healthcheck FastAPI:
  - `scripts/healthcheck_internal_fastapi.ps1`
- Configurar IIS para FastAPI:
  - `scripts/configure_iis_reverse_proxy_fastapi.ps1 -SitePath "C:\inetpub\wwwroot\calculadora-local"`

## 6. Deploy IIS (sem WebSocket)
Template aplicado:
- `deploy/iis/web.fastapi.config.template`

Roteamento:
- `http://localhost:8080/*` -> `http://127.0.0.1:8600/*`

## 7. Checklist de validacao
1. `http://127.0.0.1:8600/health` = 200
2. `http://localhost:8080/health` = 200
3. `http://localhost:8080/` abre frontend FastAPI
4. Upload de PDF conclui extracao
5. Calculo BOM retorna itens
6. Exportacao CSV/PDF funciona
