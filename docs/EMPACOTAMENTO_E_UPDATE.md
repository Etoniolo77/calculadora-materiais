# Empacotamento e Update Privado (Windows)

## Decisão de distribuição

O GitHub fica restrito ao desenvolvimento e versionamento do código. Usuários finais não recebem acesso ao repositório.

Para distribuir para colaboradores, publique apenas o pacote gerado em SharePoint, Teams ou pasta de rede com permissão corporativa. Isso evita expor o repositório inteiro para quem só precisa usar a aplicação.

> Observação de propriedade intelectual: o pacote atual ainda contém arquivos Python necessários ao runtime local. Para proteção mais forte, o próximo nível é gerar executável com PyInstaller/Nuitka. Mesmo assim, para 10 usuários internos, SharePoint/Teams privado já elimina o principal risco: acesso amplo ao repositório.

## 1) Instalação no notebook do colaborador

No pacote entregue ao usuário final:

1. Executar `INSTALAR_APP.cmd`.
2. Isso instala em `%LOCALAPPDATA%\CalculadoraMateriais`.
3. Cria atalhos na Área de Trabalho:
   - `Calculadora Materiais`

### Observação importante (máquina sem Python)

Na primeira abertura, o app tenta instalar Python automaticamente nesta ordem:

1. `winget`
2. instalador local em `scripts/bootstrap/python-installer.exe` (se existir no pacote)
3. download direto do instalador oficial do Python

Se o ambiente bloquear internet e `winget`, inclua previamente o instalador em:

`scripts/bootstrap/python-installer.exe`

## 2) Uso diário do colaborador

1. Abrir `Calculadora Materiais`.
2. Para atualizar, usar o botão **Buscar Atualizacao** dentro da própria aplicação.

## 2.1) Acesso corporativo (login local)

Para liberar o uso da aplicação:

1. Informar e-mail corporativo com domínio `@eletromarquez.com.br`.
2. Informar o PIN corporativo: `Eletro2026`.

Observação:

- Se o domínio do e-mail não for `eletromarquez.com.br`, o acesso é bloqueado.
- Se o PIN estiver incorreto, o acesso é bloqueado.

## 3) Como publicar uma nova versão (operação do time técnico)

### 3.1 Atualizar versão local

Editar `app_version.json`:

```json
{
  "version": "1.0.1"
}
```

### 3.2 Gerar pacote zip e manifesto privado

No PRJ-13:

```powershell
.\scripts\package_release.ps1
```

Saída esperada:

- `dist\CalculadoraMateriais-1.0.1.zip`
- `dist\update_manifest.json`

### 3.3 Publicar pacote privado

1. Enviar `CalculadoraMateriais-1.0.1.zip` e `update_manifest.json` para SharePoint, Teams ou pasta de rede.
2. Garantir que `update/update_config.json` esteja preenchido com o caminho do manifesto:

```json
{
  "manifest_url": "https://SEU-SHAREPOINT/update_manifest.json"
}
```

Também funciona com caminho de rede/local:

```json
{
  "manifest_url": "\\\\SERVIDOR\\Apps\\CalculadoraMateriais\\update_manifest.json"
}
```

## 4) Segurança operacional

1. O update gera backup automático antes de aplicar:
   - `archive\updates\backup-pre-update-YYYYMMDD-HHMMSS.zip`
2. O backend é encerrado antes da cópia dos novos arquivos.
3. Se a versão remota for igual ou menor, o update não aplica (exceto com `-Force`).

## 5) Comandos úteis

Atualizar manual por terminal (opcional, fallback):

```powershell
.\scripts\update_app.ps1 -TargetVersion "1.0.1" -PackageUrl "https://github.com/SEU_OWNER/SEU_REPO/releases/download/v1.0.1/CalculadoraMateriais-1.0.1.zip"
```

Para pasta de rede:

```powershell
.\scripts\update_app.ps1 -TargetVersion "1.0.1" -PackageUrl "\\SERVIDOR\Apps\CalculadoraMateriais\CalculadoraMateriais-1.0.1.zip"
```
