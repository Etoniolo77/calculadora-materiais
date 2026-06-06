-- ----------------------------------------------------
-- SCRIPT DE CRIAÇÃO DO SCHEMA NO SUPABASE (POSTGRESQL)
-- ----------------------------------------------------

-- 1. Habilitar a extensão pg_trgm para buscas aproximadas por similaridade de texto (FTS substituto)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2. Tabela de Materiais (Códigos SAP)
CREATE TABLE IF NOT EXISTS materiais (
    codigo VARCHAR(100) PRIMARY KEY,
    descricao TEXT NOT NULL
);

-- 3. Tabela de Estruturas
CREATE TABLE IF NOT EXISTS estruturas (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(100) NOT NULL,
    tipo_poste VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 4. Tabela de Composição de Estruturas (Materiais da Estrutura)
CREATE TABLE IF NOT EXISTS estrutura_materiais (
    id SERIAL PRIMARY KEY,
    estrutura_id INTEGER REFERENCES estruturas(id) ON DELETE CASCADE,
    material_codigo VARCHAR(100) NOT NULL,
    material_descricao TEXT,
    quantidade NUMERIC(12, 4) NOT NULL
);

-- 5. Índices para Otimização de Performance
CREATE INDEX IF NOT EXISTS idx_estruturas_codigo ON estruturas(codigo);
CREATE INDEX IF NOT EXISTS idx_estrutura_materiais_est_id ON estrutura_materiais(estrutura_id);

-- 6. Índice GIN para buscas textuais rápidas com similaridade (substitui o FTS5 MATCH do SQLite)
CREATE INDEX IF NOT EXISTS idx_materiais_descricao_trgm ON materiais USING gin (descricao gin_trgm_ops);
