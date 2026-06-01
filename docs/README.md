# ⚡ Calculadora de Materiais - Eletromarquez

Este projeto é uma ferramenta web para auxiliar engenheiros e programadores na extração, cálculo e geração de Listas de Materiais (BOM - Bill of Materials) a partir de projetos de redes elétricas em PDF.

## Stack Oficial

- **Backend oficial**: `FastAPI`
- **Frontend oficial**: `HTML/CSS/JS` estático em `frontend/`
- **Motor de negócio**: módulos em `core/`

## 🚀 Funcionalidades

- **Extração Automática**: Processamento de arquivos PDF para detectar automaticamente postes, estruturas, cabos e suas respectivas quantidades.
- **Cálculo Inteligente**: Motor de cálculo que "explode" estruturas técnicas em componentes individuais (parafusos, braçadeiras, cruzetas, etc.) baseados no tipo de poste e normas técnicas.
- **Edição Flexível**: Interface interativa para adicionar, remover ou modificar postes e equipamentos manualmente.
- **Geração de Relatório**: Exportação da lista consolidada de materiais em formato PDF profissional.
- **Busca de Materiais**: Integração com banco de dados SQLite para traduzir descrições técnicas em códigos SAP atualizados.

## 🛠️ Tecnologias Utilizadas

- **Interface oficial**: HTML/CSS/JS servido pelo FastAPI
- **Processamento de Dados**: Pandas
- **Extração de PDF**: pdfplumber
- **Geração de PDF**: ReportLab
- **Banco de Dados**: SQLite 3

## 📂 Estrutura do Projeto

Principais pastas e arquivos:

- `backend/app_fastapi.py`: API oficial e entrega do frontend.
- `frontend/`: interface oficial para operação.
- `core/engine.py`: motor de cálculo de materiais.
- `core/extractor.py`: leitura e interpretação dos PDFs.
- `core/database_sqlite.py`: acesso ao banco oficial.
- `data/materials.db`: banco SQLite oficial.
- `backend_runtime/`: backend compilado para distribuição interna sem fontes Python principais.
- `data/unified_db.json`: base consolidada oficial.
- `data/vocabulary.json`: vocabulário técnico oficial.
- `storage/manual_corrections.json`: aprendizado operacional e correções manuais.

## ⚙️ Como Executar

1. **Instale as dependências**:
   ```bash
   pip install -r core/requirements.txt
   ```

2. **Inicie a aplicação oficial**:
   ```bash
   powershell -ExecutionPolicy Bypass -File .\scripts\start_internal_fastapi.ps1
   ```

3. **Acesse**:
   - `http://127.0.0.1:8600/`

4. **Utilização**:
   - Faça o upload do arquivo PDF do projeto.
   - Revise os dados extraídos.
   - Ajuste os tipos de postes e equipamentos.
   - Exporte CSV ou PDF após validar a BOM.

## 🧹 Limpeza e Manutenção

Para manter a integridade do banco de dados ou migrar novos dados de planilhas Excel para o SQLite, utilize os scripts em `scripts/` sempre apontando para a pasta oficial `data/`.

## 🏢 Publicação Interna (Office 365 / Teams)

Guia operacional completo:
- [PUBLICACAO_INTERNA_OFFICE365.md](C:\Users\EvandroCesarToniolo\Projetos_Antigravity\02_PROJETOS\PRJ-13-Calculadora\docs\PUBLICACAO_INTERNA_OFFICE365.md)

---
*Desenvolvido para otimização de fluxos de engenharia elétrica.*
