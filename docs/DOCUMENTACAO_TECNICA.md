---
title: Documentação Técnica - Calculadora de Materiais
description: Detalhamento da arquitetura oficial, motor de cálculo (Engine) e estrutura de dados (SQLite)
tags: [python, fastapi, sqlite, engenharia, bom]
---

# ⚡ Calculadora de Materiais (BOM Engine)

A **Calculadora de Materiais** é o sistema core para automação de listas de materiais da Eletromarquez. Ela automatiza a "explosão" de estruturas elétricas (ex: B1, N1, S1) em componentes individuais, integrando normas técnicas e códigos SAP atualizados.

## 🏗️ Arquitetura do Sistema

O sistema é dividido em camadas modulares para garantir que a lógica de negócio (cálculos) seja independente da interface de usuário:

1. **Camada de API (`backend/app_fastapi.py`)**: Stack oficial de execução e integração com o frontend.
2. **Camada de Interface (`frontend/`)**: Frontend estático servido pelo FastAPI para upload, revisão e exportação.
3. **Motor de Cálculo (`core/engine.py`)**: A "inteligência" que decide quais materiais compõem cada poste, baseado em cargas, alturas e tipos de estruturas.
4. **Persistência de Dados (`core/database_sqlite.py` + `data/materials.db`)**: Banco **SQLite com FTS5 (Full Text Search)** para buscas instantâneas por termos técnicos.
5. **Extrator de PDF (`core/extractor.py`)**: O componente responsável pela visão computacional e processamento de linguagem natural (NLP) do projeto.

## 📄 Lógica de Extração de PDF (`extractor.py`)

A extração de dados de projetos elétricos é a tarefa mais complexa do sistema, pois os PDFs são desenhos técnicos (CAD) convertidos, onde a posição visual é crucial.

### 1. Detecção de Estados Visuais (Algoritmo de "Visão")
O extrator utiliza o `pdfplumber` para não apenas ler texto, mas analisar objetos geométricos:
- **Itens NOVOS (Caixas)**: O sistema identifica retângulos (`rects`) ao redor das palavras. Se uma estrutura (ex: "N1") estiver dentro de um retângulo, ela é marcada como `state='NEW'`.
- **Itens REMOVIDOS (Tachados)**: Identifica linhas horizontais que cruzam o centro das palavras. Se uma linha cruza uma estrutura, ela é mapeada com o sufixo `(R)` (ex: `N1(R)`).
- **Itens EXISTENTES**: Texto sem marcações gráficas adicionais.

### 2. Âncoras e Associação (Inteligência Espacial)
Como o texto extraído de um PDF pode vir fora de ordem, o sistema utiliza **Âncoras de Poste**:
- Busca por identificadores de poste (P1, P2...).
- Busca por tipos de poste (C12/600, DT11/300) usando Regex.
- **Lógica de Proximidade**: Estruturas e equipamentos são associados a um poste se estiverem dentro de um limite de coordenadas (`bbox`) vertical (tolerância de ~250 pixels).

### 3. Extração de Cabos e Metragens
Utiliza uma lógica de "Varredura de Linha":
- Identifica palavras-chave `MT` ou `BT`.
- Captura a descrição técnica do cabo.
- Busca o número seguido da letra `M` (ex: `120 M`) na mesma linha de base para definir a quantidade.

### 4. Vocabulário e Rastreabilidade
- **VocabularyManager**: Normaliza termos (ex: transforma "CH" em "CHAVE") antes do processamento.
- **Metadados**: Cada item extraído carrega sua página de origem, coordenadas (`bbox`) e nível de confiança, permitindo auditoria.

## 🗄️ Sistema de Dados e Migração (`materials.db`)

Para garantir a performance e a integridade dos dados, o sistema utiliza um banco de dados SQLite. O arquivo `migrate_to_sqlite.py` é o responsável por construir este banco a partir das fontes de verdade (JSON).

### 1. Fontes de Dados (Sources)
- **`data/unified_db.json`**: Contém a biblioteca de materiais SAP e as "receitas" das estruturas técnicas.
- **`master_data_bom.json`**: Contém a hierarquia de categorias e subcategorias para o Bill of Materials.
- **`Codigos de Materiais Novos.xlsx`**: Planilha de referência para traduções de códigos antigos.

### 2. Estrutura do Banco (Schema)
O banco possui tabelas otimizadas com índices e triggers:
- **`materiais_fts`**: Tabela virtual que utiliza o algoritmo FTS5 para permitir buscas por "termos aproximados" (ex: buscar "POSTE" retorna todos os postes instantaneamente).
- **Triggers de Sincronização**: Garantem que qualquer alteração na tabela de materiais seja refletida no índice de busca automaticamente.

## 🛠️ Validação Técnica e Vocabulário

Para evitar erros de engenharia, o sistema possui dois guardiões:

### 1. Validador Técnico (`validators.py`)
Implementa as "Regras de Ouro" da engenharia elétrica:
- **Esforço do Poste**: Alerta se um transformador pesado (ex: 75kVA) for colocado em um poste de baixo esforço (ex: 300daN).
- **Compatibilidade**: Garante que estruturas que exigem montagem em Poste Duplo T (DT) não sejam alocadas em postes circulares por engano.
- **Vão Máximo**: Verifica se a metragem de cabo informada excede os limites técnicos de tração para cada bitola.

### 2. Vocabulário Dinâmico (`vocabulary.py`)
Resolve o problema de termos regionais ou siglas:
- Transforma "CH" em "CHAVE SECCIONADORA".
- Transforma "TRAFO" em "TRANSFORMADOR".
- **Aprendizado**: O sistema registra correções e vocabulário operacional na trilha oficial `data/vocabulary.json`.

## 🔄 Procedimento de Manutenção (Segurança)

Para garantir que "nada se perca" (conforme solicitado pelo usuário):
1. **Sempre manter os arquivos oficiais em `data/` atualizados.** A fonte primária operacional é `data/unified_db.json`.
2. Caso o banco `materials.db` precise ser resetado ou atualizado, basta rodar:
   ```bash
   python scripts/migrate_to_sqlite.py
   ```
   Este script apagará o banco antigo e recriará toda a estrutura e índices do zero em segundos.

## 🧠 Lógica do Motor (Engine)

### 1. Explosão de Estruturas
Quando uma estrutura (ex: `N1`) é detectada, o motor realiza os seguintes passos:
- **Consulta ao Banco**: Busca no SQLite a composição padrão da estrutura.
- **Filtro de Poste**: Ajusta os materiais se o poste for **Circular** ou **Duplo T (DT)**.
- **Resolução de Cintas (Braçadeiras)**: Diferente de parafusos fixos, o SAP da cinta depende do diâmetro do poste. O sistema calcula isso dinamicamente usando a `clamp_logic`.

### 2. Regras de Ouro de Negócio
- **Códigos "9xxx"**: São códigos de desativação e são filtrados automaticamente para evitar compras erradas.
- **Códigos "3xxx"**: Prioridade máxima por serem os códigos SAP novos.
- **Tradução Automática**: O sistema resolve descrições genéricas (ex: "CABO 120") para o SAP específico da EDP.

## 📊 Estrutura de Dados (SQLite)

O arquivo `materials.db` contém as seguintes tabelas críticas:
- `materiais`: Catálogo completo de códigos e descrições SAP.
- `estruturas`: Cabeçalho das estruturas técnicas.
- `estrutura_materiais`: A tabela de "receitas", que diz quantos itens de cada SAP vão em cada estrutura.
- `materiais_fts`: Índice de busca rápida para encontrar materiais por palavras-chave.

## 🛠️ Manutenção e Segurança

- **Backup**: O conjunto oficial para runtime é `data/materials.db`, `data/unified_db.json` e `data/vocabulary.json`.
- **Atualização**: Novos kits devem ser adicionados via script de migração (`migrate_to_sqlite.py`) para manter a performance do banco.

---
**Documentação gerada organicamente pelo Antigravity em 18/01/2026.**
