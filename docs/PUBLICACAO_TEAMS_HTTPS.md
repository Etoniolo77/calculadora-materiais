# Publicacao no Teams com HTTPS

Data: 2026-04-22  
Projeto: PRJ-13-Calculadora

## 1) Premissas
- A aplicacao local deve responder em:
  - `http://localhost:8080/health`
- Para Teams Tab funcionar, a URL deve ser HTTPS valida e dominio deve estar em `validDomains`.

Referencias Microsoft:
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/create-personal-tab
- https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/create-tab-pages/content-page

## 2) Fluxo rapido (ngrok)
1. Configurar token ngrok (uma unica vez):
```bat
scripts\configurar_ngrok_token.bat
```

2. Publicar tunel HTTPS para Teams:
```bat
scripts\publicar_teams_https.bat
```

3. Copiar URL HTTPS gerada (exemplo):
- `https://abc123.ngrok-free.app`

## 3) Configuracao no Teams (Developer Portal)
- Website / Content URL: usar a URL HTTPS do ngrok.
- Health opcional: `https://.../health`
- `validDomains`: adicionar somente o dominio, sem `https`, por exemplo:
  - `abc123.ngrok-free.app`

## 4) Observacoes importantes
- `localhost` e `192.168.x.x` nao funcionam como URL final de Tab no Teams fora da maquina/rede.
- Se o tunel expirar, gere nova URL com `publicar_teams_https.bat` e atualize no Teams.
