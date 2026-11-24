-- =============================================================================
-- Mamíferos, Unidades de Conservação e Rodovias de Minas Gerais
-- schema.sql: extensão, tabelas, restrições e índices
-- SRID: 4674 (SIRGAS 2000, coordenadas geográficas). Ver DICIONARIO.md.
-- Execute em um banco vazio:  psql -d mamiferos_mg -f sql/schema.sql
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS postgis;

SET client_encoding TO 'UTF8';

DROP TABLE IF EXISTS rodovia_uc, ocorrencia, rodovia, unidade_conservacao,
                     taxon, tipo_superficie, categoria_uc CASCADE;

-- -----------------------------------------------------------------------------
-- Tabelas de domínio (sem geometria)
-- -----------------------------------------------------------------------------

CREATE TABLE categoria_uc (
    sigla   varchar(5)  PRIMARY KEY,
    nome    varchar(60) NOT NULL UNIQUE,
    grupo   varchar(20) NOT NULL
            CHECK (grupo IN ('PROTECAO_INTEGRAL', 'USO_SUSTENTAVEL'))
);
COMMENT ON TABLE categoria_uc IS 'Categorias de unidade de conservação do SNUC (Lei 9.985/2000) presentes na base.';

CREATE TABLE tipo_superficie (
    sigla     char(3)     PRIMARY KEY,
    descricao varchar(80) NOT NULL UNIQUE
);
COMMENT ON TABLE tipo_superficie IS 'Situação física/superfície de trechos rodoviários (siglas do SNV/DNIT).';

CREATE TABLE taxon (
    taxon_key        varchar(12)  PRIMARY KEY,
    nome_cientifico  varchar(150) NOT NULL,
    nivel_taxonomico varchar(12)  NOT NULL
                     CHECK (nivel_taxonomico IN ('CLASSE', 'ORDEM', 'FAMILIA', 'GENERO',
                                                 'ESPECIE', 'SUBESPECIE', 'SEM_NIVEL')),
    ordem            varchar(40),
    familia          varchar(40),
    genero           varchar(40),
    especie          varchar(80)
);
COMMENT ON TABLE taxon IS 'Táxons (Backbone Taxonomy do GBIF) referenciados pelas ocorrências.';

-- -----------------------------------------------------------------------------
-- Tabelas espaciais
-- -----------------------------------------------------------------------------

CREATE TABLE unidade_conservacao (
    id_uc           integer      PRIMARY KEY,
    cod_origem      varchar(20)  NOT NULL UNIQUE,
    nome            varchar(150) NOT NULL,
    esfera          varchar(8)   NOT NULL CHECK (esfera IN ('ESTADUAL', 'FEDERAL')),
    sigla_categoria varchar(5)   NOT NULL REFERENCES categoria_uc (sigla),
    ato_legal       varchar(300),
    municipios      varchar(400),
    bioma           varchar(60),
    area_ha         numeric(12,2) NOT NULL CHECK (area_ha > 0),
    geom            geometry(MultiPolygon, 4674) NOT NULL,
    CONSTRAINT uc_geom_valida CHECK (ST_IsValid(geom) AND NOT ST_IsEmpty(geom))
);
COMMENT ON TABLE unidade_conservacao IS 'Unidades de conservação estaduais (IEF) e federais (ICMBio) em Minas Gerais.';

CREATE TABLE rodovia (
    id_trecho        integer      PRIMARY KEY,
    id_cide          integer      NOT NULL UNIQUE,
    numero_rodovia   char(3)      CHECK (numero_rodovia ~ '^[0-9]{3}$'),
    codigo_snv       varchar(12),
    jurisdicao       varchar(8)   CHECK (jurisdicao IN ('ESTADUAL', 'FEDERAL')),
    tipo_trecho      varchar(14)  CHECK (tipo_trecho IN ('EIXO_PRINCIPAL', 'ACESSO')),
    sigla_superficie char(3)      REFERENCES tipo_superficie (sigla),
    local_inicio     varchar(120),
    local_fim        varchar(120),
    km_inicial       numeric(8,3) CHECK (km_inicial >= 0),
    km_final         numeric(8,3) CHECK (km_final >= 0),
    extensao_km      numeric(8,3) CHECK (extensao_km >= 0),
    comprimento_km   numeric(10,3) NOT NULL CHECK (comprimento_km >= 0),
    geom             geometry(MultiLineString, 4674) NOT NULL,
    CONSTRAINT rodovia_geom_valida CHECK (ST_IsValid(geom) AND NOT ST_IsEmpty(geom))
);
COMMENT ON TABLE rodovia IS 'Trechos de rodovias federais e estaduais em Minas Gerais (SRE/DER-MG, base CIDE 2021).';

CREATE TABLE ocorrencia (
    id_ocorrencia      bigint       PRIMARY KEY,
    taxon_key          varchar(12)  NOT NULL REFERENCES taxon (taxon_key),
    data_evento        date,
    ano                smallint     CHECK (ano BETWEEN 1800 AND 2100),
    mes                smallint     CHECK (mes BETWEEN 1 AND 12),
    base_registro      varchar(20)  NOT NULL
                       CHECK (base_registro IN ('OBSERVACAO_HUMANA', 'ESPECIME_PRESERVADO',
                                                'AMOSTRA_MATERIAL', 'CITACAO_MATERIAL',
                                                'OBSERVACAO_MAQUINA')),
    codigo_instituicao varchar(80),
    num_individuos     integer      CHECK (num_individuos >= 0),
    incerteza_coord_m  numeric(9,1) CHECK (incerteza_coord_m >= 0),
    licenca            varchar(10)  NOT NULL CHECK (licenca IN ('CC-BY-4.0', 'CC0-1.0')),
    id_dataset         uuid         NOT NULL,
    id_uc              integer      REFERENCES unidade_conservacao (id_uc),
    geom               geometry(Point, 4674) NOT NULL,
    CONSTRAINT ocorrencia_geom_valida CHECK (ST_IsValid(geom) AND NOT ST_IsEmpty(geom)),
    CONSTRAINT ocorrencia_data_coerente CHECK (data_evento IS NULL OR ano IS NULL
                                               OR EXTRACT(YEAR FROM data_evento) = ano)
);
COMMENT ON TABLE ocorrencia IS 'Registros de ocorrência de mamíferos em Minas Gerais (download GBIF 0012809-261118162104854).';

-- Associação N:N materializada a partir de ST_Intersects(rodovia.geom, unidade_conservacao.geom)
CREATE TABLE rodovia_uc (
    id_trecho      integer       NOT NULL REFERENCES rodovia (id_trecho) ON DELETE CASCADE,
    id_uc          integer       NOT NULL REFERENCES unidade_conservacao (id_uc) ON DELETE CASCADE,
    comprimento_km numeric(10,3) NOT NULL CHECK (comprimento_km >= 0),
    PRIMARY KEY (id_trecho, id_uc)
);
COMMENT ON TABLE rodovia_uc IS 'Trechos rodoviários que intersectam unidades de conservação e a extensão (km) dentro de cada UC.';

-- -----------------------------------------------------------------------------
-- Índices
-- -----------------------------------------------------------------------------

CREATE INDEX unidade_conservacao_geom_gix ON unidade_conservacao USING gist (geom);
CREATE INDEX rodovia_geom_gix             ON rodovia             USING gist (geom);
CREATE INDEX ocorrencia_geom_gix          ON ocorrencia          USING gist (geom);

CREATE INDEX unidade_conservacao_categoria_idx ON unidade_conservacao (sigla_categoria);
CREATE INDEX rodovia_superficie_idx            ON rodovia (sigla_superficie);
CREATE INDEX ocorrencia_taxon_idx              ON ocorrencia (taxon_key);
CREATE INDEX ocorrencia_uc_idx                 ON ocorrencia (id_uc);
CREATE INDEX rodovia_uc_uc_idx                 ON rodovia_uc (id_uc);
