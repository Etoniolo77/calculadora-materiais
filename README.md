# ⚡ Calculadora de Materiais - Eletromarquez

Este projeto é uma ferramenta web desenvolvida em Python (Streamlit) para auxiliar engenheiros e programadores na extração, cálculo e geração de Listas de Materiais (BOM - Bill of Materials) a partir de projetos de redes elétricas em PDF.

## 🚀 Funcionalidades

- **Extração Automática**: Processamento de arquivos PDF para detectar automaticamente postes, estruturas, cabos e suas respectivas quantidades.
- **Cálculo Inteligente**: Motor de cálculo que "explode" estruturas técnicas em componentes individuais (parafusos, braçadeiras, cruzetas, etc.) baseados no tipo de poste e normas técnicas.
- **Edição Flexível**: Interface interativa para adicionar, remover ou modificar postes e equipamentos manualmente.
- **Geração de Relatório**: Exportação da lista consolidada de materiais em formato PDF profissional.
- **Busca de Materiais**: Integração com banco de dados SQLite para traduzir descrições técnicas em códigos SAP atualizados.

## 🛠️ Tecnologias Utilizadas

- **Interface**: [Streamlit](https://streamlit.io/)
- **Processamento de Dados**: Pandas
- **Extração de PDF**: pdfplumber
- **Geração de PDF**: ReportLab
- **Banco de Dados**: SQLite 3

## 📂 Estrutura do Projeto

Principais arquivos e suas funções:

- `app.py`: Interface principal do usuário e fluxo da aplicação.
- `engine.py`: O "cérebro" do sistema. Contém a lógica de cálculo de materiais e resolução de tipos de postes/braçadeiras.
- `extractor.py`: Responsável por ler o PDF e identificar padrões de texto (regex) para extrair dados do projeto.
- `database_sqlite.py` & `database_loader.py`: Gerenciam a conexão e o carregamento dos materiais para o banco de dados local.
- `final_report.py`: Script para formatação e geração do relatório final de materiais em PDF.
- `materials.db`: Banco de dados SQLite contendo os códigos SAP e composições de kits.
- `requirements.txt`: Lista de dependências Python necessárias.

## ⚙️ Como Executar

1.  **Instale as dependências**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Inicie a aplicação**:
    ```bash
    streamlit run app.py
    ```

3.  **Utilização**:
    - Faça o upload do arquivo PDF do projeto na barra lateral.
    - Revise os dados extraídos na área central.
    - Ajuste os tipos de postes e equipamentos nos painéis expansíveis.
    - Clique em "Exportar PDF" para obter a lista final.

## 🧹 Limpeza e Manutenção

Para manter a integridade do banco de dados ou migrar novos dados de planilhas Excel para o SQLite, utilize os scripts `migrate_to_sqlite.py` e `database_loader.py`.

---
*Desenvolvido para otimização de fluxos de engenharia elétrica.*
