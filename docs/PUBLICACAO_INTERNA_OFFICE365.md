# Publicação Interna - Office 365 + Teams

Data: 2026-04-21

## 1. Objetivo
Publicar a Calculadora internamente (rede corporativa), sem migração de mainframe, com acesso por URL interna e opção de aba no Teams.

## 2. Pré-requisitos
- Windows Server interno (ou VM Windows interna)
- Python 3.10+ instalado
- IIS instalado com:
  - URL Rewrite
  - ARR (Application Request Routing)
  - WebSocket habilitado
- Acesso ao repositório em pasta local

## 3. Setup da aplicação
No diretório do projeto:

```powershell
.\scripts\setup_internal_publish.ps1
```

## 4. Subir Streamlit local (backend de aplicação)
```powershell
.\scripts\start_internal_streamlit.ps1 -BindAddress 127.0.0.1 -Port 8501
```

Verificar saúde:
```powershell
.\scripts\healthcheck_internal_streamlit.ps1 -BindAddress 127.0.0.1 -Port 8501
```

Parar:
```powershell
.\scripts\stop_internal_streamlit.ps1
```

## 5. IIS Reverse Proxy
1. Criar um site no IIS (ex: `calculadora-interna`).
2. Associar binding interno (ex: `https://calculadora.suaempresa.local`).
3. Copiar o template [web.config.template](C:\Users\EvandroCesarToniolo\Projetos_Antigravity\02_PROJETOS\PRJ-13-Calculadora\deploy\iis\web.config.template) para a raiz do site como `web.config`.
4. Garantir que ARR está com proxy habilitado.
5. Validar no navegador corporativo:
   - `https://calculadora.suaempresa.local`

Automação opcional (PowerShell):
```powershell
.\scripts\configure_iis_reverse_proxy.ps1 `
  -SiteName "calculadora-interna" `
  -SitePath "C:\inetpub\wwwroot\calculadora-interna" `
  -Binding "*:443:calculadora.suaempresa.local" `
  -CreateSiteIfMissing
```

## 6. Publicar no Teams (Tab)
1. No Teams, abrir o canal/equipe alvo.
2. Adicionar uma nova aba tipo `Website`.
3. Informar URL interna HTTPS da calculadora.
4. Nome sugerido: `Calculadora Materiais`.

## 7. Variáveis de IA (opcional)
Para Claude:
- `ANTHROPIC_API_KEY`

Para Copilot endpoint corporativo:
- `COPILOT_EXTRACT_WEBHOOK_URL`
- `COPILOT_EXTRACT_API_KEY` (opcional)
- `COPILOT_EXTRACT_TIMEOUT_SEC` (opcional)

## 8. Checklist de go-live
- Healthcheck local: OK
- Upload de PDF real: OK
- Gate de qualidade funcionando: OK
- Exportação CSV/PDF funcionando: OK
- Acesso via Teams Tab: OK
- Logs sem erro crítico em `storage\streamlit.err.log`: OK

## 9. Operação diária
- Start:
  - `.\scripts\start_internal_streamlit.ps1`
  - fallback sem venv: `.\scripts\start_internal_streamlit.ps1 -UseSystemPython`
- Stop:
  - `.\scripts\stop_internal_streamlit.ps1`
- Health:
  - `.\scripts\healthcheck_internal_streamlit.ps1`

## 10. Observações de ambiente
- Em máquinas com hardening, `venv/ensurepip` pode falhar por política de permissão.
- Nesses casos, usar fallback com Python global e manter o runtime validado.
