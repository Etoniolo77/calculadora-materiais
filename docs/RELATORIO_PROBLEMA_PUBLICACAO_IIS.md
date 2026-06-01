# Relatório Técnico - Problema de Renderização via IIS (localhost:8080)

> Documento historico do incidente com Streamlit. Mantido apenas como evidencia de causa raiz e da decisao de abandono do stack antigo.

Data: 2026-04-21  
Projeto: PRJ-13-Calculadora  
Ambiente: Windows local (máquina do usuário), IIS + ARR + Streamlit

## 1. Objetivo
Publicar localmente a aplicação Streamlit atrás do IIS (reverse proxy) em `http://localhost:8080`.

## 2. Sintoma Atual
- A URL `http://localhost:8080` abre a página base do Streamlit, mas fica em loading infinito (skeleton), sem renderizar o app.
- Não há erro explícito no browser após os ajustes mais recentes.

## 3. Evidências Confirmadas
1. Backend Streamlit responde localmente:
- `http://127.0.0.1:8501/_stcore/health` => `200 OK` com `ok`.

2. Proxy IIS responde para health:
- `http://localhost:8080/_stcore/health` => `200 OK` com `ok`.

3. WebSocket via proxy está funcionando:
- Teste com `curl` em `http://localhost:8080/_stcore/stream` retornou:
  - `HTTP/1.1 101 Switching Protocols`
  - `X-Powered-By: ARR/3.0`
  - `Sec-Websocket-Protocol: streamlit` (quando enviado no request)

4. Host-config responde via proxy:
- `http://localhost:8080/_stcore/host-config` => `200 OK` com JSON.

## 4. Erros Encontrados no Caminho (já tratados)
1. `HTTP 500.50` (URL Rewrite module error):
- Causa: `HTTP_X_FORWARDED_PROTO` não permitido em server variables.
- Ação: removido bloco `<serverVariables>` do `web.config`.

2. `HTTP 502.3 Bad Gateway`:
- Causa intermitente por backend Streamlit não ativo.
- Ação: backend levantado manualmente e validado com healthcheck.

3. Falha de setup da venv:
- `ensurepip` com `PermissionError` e bloqueios de ambiente/rede.
- Ação: fallback para Python global (`C:\Python314\python.exe`) adotado.

## 5. Configuração Atual Relevante
Arquivo: `C:\inetpub\wwwroot\calculadora-local\web.config`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <webSocket enabled="true" />
    <rewrite>
      <rules>
        <rule name="ReverseProxyToStreamlit" stopProcessing="true">
          <match url="(.*)" />
          <action type="Rewrite" url="http://127.0.0.1:8501/{R:1}" />
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
```

Proxy ARR habilitado:
- `system.webServer/proxy enabled=True`.

WebSocket habilitado:
- `system.webServer/webSocket enabled=True`.

## 6. Comandos de Diagnóstico já executados com sucesso
```powershell
Invoke-WebRequest "http://127.0.0.1:8501/_stcore/health" -UseBasicParsing
Invoke-WebRequest "http://localhost:8080/_stcore/health" -UseBasicParsing
Invoke-WebRequest "http://localhost:8080/_stcore/host-config" -UseBasicParsing
curl.exe -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: SGVsbG8sIHdvcmxkIQ==" -H "Sec-WebSocket-Protocol: streamlit" http://localhost:8080/_stcore/stream
```

## 7. Diagnóstico de Causa Raiz (2026-04-22)
Foram identificadas duas causas estruturais combinadas:

1. Configuração IIS incompleta para Streamlit em tempo real:
- O template original podia reintroduzir configurações que causaram `500.50` (`serverVariables`).
- Não havia regra explícita para `_stcore/stream` (WebSocket) nem desativação de compressão no site proxy.

2. Instabilidade de runtime com Python 3.14 + watcher:
- Evidência em `storage/streamlit.err.log` com erro fatal em `watchdog`/`_PySemaphore_Wakeup`.
- Esse comportamento pode derrubar ou degradar a sessão durante bootstrap WebSocket e manter o frontend em skeleton.

## 8. Correções Aplicadas no Projeto
1. Harden de template IIS (`deploy/iis/web.config.template`):
- Adicionada regra dedicada para `_stcore/stream`.
- Mantida regra de proxy geral para demais rotas.
- Removido uso de `<serverVariables>`.
- Desativada compressão dinâmica/estática no site proxy (`urlCompression`).

2. Harden de inicialização Streamlit (`scripts/start_internal_streamlit.ps1`):
- Flags fixas adicionadas:
  - `--server.enableCORS false`
  - `--server.enableXsrfProtection false`
  - `--server.enableWebsocketCompression false`
  - `--server.fileWatcherType none`

3. Harden de setup (`scripts/setup_internal_publish.ps1` e `.streamlit/config.toml`):
- Persistidas configurações equivalentes:
  - `enableWebsocketCompression = false`
  - `fileWatcherType = "none"`
  - `runOnSave = false`

4. Script de IIS reforçado (`scripts/configure_iis_reverse_proxy.ps1`):
- Além de copiar `web.config`, agora garante ARR Proxy habilitado com `appcmd`.

## 9. Procedimento de Execução (padrão definitivo)
```powershell
# no projeto
.\scripts\stop_internal_streamlit.ps1
.\scripts\setup_internal_publish.ps1 -AllowSystemPythonFallback
.\scripts\start_internal_streamlit.ps1 -UseSystemPython -NoBrowser

# healthcheck local
.\scripts\healthcheck_internal_streamlit.ps1 -BindAddress 127.0.0.1 -Port 8501

# aplicar IIS (como administrador)
.\scripts\configure_iis_reverse_proxy.ps1 `
  -SitePath "C:\inetpub\wwwroot\calculadora-local"
```

## 10. Critérios de Aceite
1. `http://127.0.0.1:8501/_stcore/health` => `200`.
2. `http://localhost:8080/_stcore/health` => `200`.
3. `http://localhost:8080/_stcore/host-config` => `200`.
4. `curl` em `/_stcore/stream` => `101 Switching Protocols`.
5. UI em `http://localhost:8080` renderiza sem loading infinito.

## 11. Estado Final deste atendimento
- Correção estrutural implementada no repositório (IIS + scripts + config Streamlit).
- Fluxo operacional padronizado para evitar regressão de publicação.
- Se persistir instabilidade residual no host atual, próxima ação recomendada é executar com Python 3.12 LTS para eliminar risco específico do stack `Python 3.14 + watchdog` no Windows.

## 12. Decisao de Arquitetura (2026-04-22)
Como o frontend continuou em loading infinito mesmo com handshake e endpoints internos validados, foi aprovada migracao de stack para eliminar dependencia de WebSocket no IIS.

Nova direcao:
- Backend FastAPI (`backend/app_fastapi.py`)
- Frontend estatico HTML/JS (`frontend/`)
- Reuso da logica de negocio em `core/` (extractor, engine, validators, final_report)

Documentacao operacional da migracao:
- `docs/MIGRACAO_STACK_FASTAPI.md`

## 13. Recomendacoes Tecnicas (Calculo e Extracao)
Com base nos testes dos diagramas em `docs/Diagramas de Testes`, recomendamos manter as seguintes melhorias estruturais:

1. Higienizacao de OCR no modo por caixas (ja aplicado)
- Bloquear tokens de cabo/bitola sendo lidos como poste/estrutura (ex.: `3X185AX`, `P01`).
- Resultado esperado: reducao de excesso de materiais e de contagens absurdas de cinta/parafuso.

2. Normalizacao defensiva de entrada (ja aplicado)
- Normalizar `Tipo Poste` no backend (captura apenas tipologia valida, ex.: `C11/300`).
- Normalizar lista de estruturas removendo `Pxx`, duplicidades e sufixos de retirada/existente no campo bruto.

3. Recomendacoes automaticas na interface (ja aplicado)
- API retorna `recommendations` em `extract` e `calculate` com alertas de:
  - postes sem tipologia;
  - postes sem estruturas;
  - estruturas suspeitas de OCR;
  - itens `VERIFICAR` na BOM;
  - possivel excesso de cintas para a quantidade de postes.

4. Melhorias adicionais priorizadas (proxima sprint)
- Alias no banco para estruturas de ramal ausentes (`1S1`, `1S2`) para reduzir `VERIFICAR` residual.
- Regra de inferencia de tipologia quando houver apenas 1 `Pxx` explicito e sem caixa valida.
- Golden tests com PDFs reais para evitar regressao de extração.
