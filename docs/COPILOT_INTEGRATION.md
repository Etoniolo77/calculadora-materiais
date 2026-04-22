# Integração Copilot - Extração de PDF

Data: 2026-04-21

## 1. Objetivo
Permitir extração semântica de PDFs usando Copilot/endpoint corporativo, com fallback automático para parser padrão.

## 2. Variáveis de ambiente
- `COPILOT_EXTRACT_WEBHOOK_URL` (obrigatória)
- `COPILOT_EXTRACT_API_KEY` (opcional)
- `COPILOT_EXTRACT_TIMEOUT_SEC` (opcional, padrão `90`)

## 3. Contrato HTTP (request)
`POST` em `COPILOT_EXTRACT_WEBHOOK_URL`

Headers:
- `Content-Type: application/json`
- `Accept: application/json`
- `X-API-Key: <token>` (opcional)

Body:
```json
{
  "prompt": "instruções de extração",
  "pdf_base64": "<arquivo_pdf_em_base64>"
}
```

## 4. Contratos aceitos (response)
Formato A (direto):
```json
{
  "postes": [],
  "cabos": [],
  "ordem": ""
}
```

Formato B (encapsulado):
```json
{
  "result": {
    "postes": [],
    "cabos": [],
    "ordem": ""
  }
}
```

Formato C (JSON dentro de string):
```json
{
  "content": "{\"postes\": [], \"cabos\": [], \"ordem\": \"\"}"
}
```

## 5. Campos esperados
Estrutura mínima:
- `postes`: lista
- `cabos`: lista
- `ordem`: string (opcional)

Poste:
- `id` (ex: `P1`)
- `tipo` (ex: `C12/600`, `DT11/300`)
- `estruturas` (lista)
- `trafo` (`null` ou string)
- `estais` (int)
- `chave` (`null` ou string)

Cabo:
- `tipo` (`MT` ou `BT`)
- `descricao` (string)
- `metros` (número)

## 6. Teste local com mock
1. Subir mock:
```bash
python scripts/mock_copilot_extractor.py
```

2. Configurar ambiente:
```bash
set COPILOT_EXTRACT_WEBHOOK_URL=http://127.0.0.1:8765/extract
```

3. Abrir app e selecionar:
- Sidebar -> `Extração de PDF` -> `Copilot`

4. Enviar um PDF e validar:
- Mensagem de sucesso com `IA (COPILOT)`
- Estruturas/cabos preenchidos
- Fallback para padrão em caso de falha de endpoint

## 7. Segurança e governança
- Nunca registrar `pdf_base64` em logs.
- Recomendado usar endpoint interno com autenticação e auditoria.
- Monitorar taxa de fallback para identificar degradação do provedor IA.
