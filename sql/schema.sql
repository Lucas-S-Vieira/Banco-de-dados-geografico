-- =====================================================================
-- Base: Mamíferos, Unidades de Conservação e Rodovias em Minas Gerais
-- Disciplina CSI803 - Banco de Dados Geográficos (UFOP)
-- SRID adotado em todas as geometrias: EPSG:4674 (SIRGAS 2000)
-- Execução: psql -d <banco> -v ON_ERROR_STOP=1 -f sql/schema.sql
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------
-- Tabelas de domínio (sem geometria)
-- ---------------------------------------------------------------------
CREATE TABLE categoria_uc (
    cod_categoria varchar(5)  PRIMARY KEY,
    nome          varchar(60) NOT NULL,
    grupo         varchar(20) NOT NULL
                  CHECK (grupo IN ('PROTECAO_INTEGRAL', 'USO_SUSTENTAVEL')),
    cat_iucn      varchar(3)  NOT NULL
                  CHECK (cat_iucn IN ('Ia', 'II', 'III', 'IV', 'V', 'VI'))
);
COMMENT ON TABLE categoria_uc IS
    'Categorias de unidade de conservação (SNUC) e correspondência com a IUCN.';

CREATE TABLE superficie_rodovia (
    cod_superficie varchar(3)  PRIMARY KEY,
    descricao      varchar(60) NOT NULL
);
COMMENT ON TABLE superficie_rodovia IS
    'Códigos de situação/superfície do trecho rodoviário (convenção SNV/DNIT).';

INSERT INTO categoria_uc (cod_categoria, nome, grupo, cat_iucn) VALUES
    ('ESEC',  'Estação Ecológica',                      'PROTECAO_INTEGRAL', 'Ia'),
    ('REBIO', 'Reserva Biológica',                      'PROTECAO_INTEGRAL', 'Ia'),
    ('PAR',   'Parque (Nacional ou Estadual)',          'PROTECAO_INTEGRAL', 'II'),
    ('MONA',  'Monumento Natural',                      'PROTECAO_INTEGRAL', 'III'),
    ('RVS',   'Refúgio de Vida Silvestre',              'PROTECAO_INTEGRAL', 'IV'),
    ('RPPN',  'Reserva Particular do Patrimônio Natural','USO_SUSTENTAVEL',  'IV'),
    ('APA',   'Área de Proteção Ambiental',             'USO_SUSTENTAVEL',   'V'),
    ('FLO',   'Floresta (Nacional ou Estadual)',        'USO_SUSTENTAVEL',   'VI'),
    ('RDS',   'Reserva de Desenvolvimento Sustentável', 'USO_SUSTENTAVEL',   'VI');

INSERT INTO superficie_rodovia (cod_superficie, descricao) VALUES
    ('PAV', 'Pavimentada'),
    ('DUP', 'Duplicada'),
    ('IMP', 'Implantada (sem pavimento)'),
    ('LEN', 'Leito natural'),
    ('PLA', 'Planejada'),
    ('EOP', 'Em obras de pavimentação'),
    ('EOD', 'Em obras de duplicação');

CREATE TABLE taxon (
    taxon_key        varchar(12)  PRIMARY KEY,
    nivel_taxonomico varchar(10)  NOT NULL
                     CHECK (nivel_taxonomico IN ('CLASS', 'ORDER', 'FAMILY', 'GENUS',
                                                 'SPECIES', 'SUBSPECIES', 'UNRANKED')),
    nome_cientifico  varchar(120) NOT NULL,
    especie          varchar(60),
    genero           varchar(60),
    familia          varchar(60),
    ordem            varchar(60)
);
COMMENT ON TABLE taxon IS
    'Táxons de mamíferos referenciados pelas ocorrências (chave do GBIF Backbone).';

-- ---------------------------------------------------------------------
-- Tabelas espaciais
-- ---------------------------------------------------------------------
CREATE TABLE unidade_conservacao (
    id_uc           integer      PRIMARY KEY,
    nome            varchar(150) NOT NULL,
    cod_categoria   varchar(5)   NOT NULL REFERENCES categoria_uc (cod_categoria),
    esfera          varchar(8)   NOT NULL CHECK (esfera IN ('ESTADUAL', 'FEDERAL')),
    id_origem       integer      NOT NULL,
    cd_cnuc         varchar(15)  UNIQUE,
    ato_legal       varchar(200) NOT NULL,
    bioma           varchar(60),
    municipios      text         NOT NULL,
    area_oficial_ha numeric(12,2) CHECK (area_oficial_ha >= 0),
    area_ha         numeric(12,2) GENERATED ALWAYS AS
                    (round((ST_Area(geom::geography) / 10000)::numeric, 2)) STORED,
    geom            geometry(MultiPolygon, 4674) NOT NULL,
    UNIQUE (esfera, id_origem),
    CONSTRAINT uc_geom_valida CHECK (ST_IsValid(geom) AND NOT ST_IsEmpty(geom))
);
COMMENT ON TABLE unidade_conservacao IS
    'Unidades de conservação estaduais e federais de Minas Gerais (IDE-Sisema).';

CREATE TABLE rodovia (
    id_trecho          integer      PRIMARY KEY,
    id_cide            integer      NOT NULL,
    codigo_rod         varchar(10)  NOT NULL,
    codigo_snv         varchar(15)  NOT NULL,
    tipo_trecho        varchar(20)  NOT NULL CHECK (tipo_trecho IN ('Eixo Principal', 'Acesso')),
    uf                 char(2)      NOT NULL,
    local_inicio       varchar(120) NOT NULL,
    local_fim          varchar(120),
    km_inicio          numeric(8,3) NOT NULL CHECK (km_inicio >= 0),
    km_fim             numeric(8,3) NOT NULL CHECK (km_fim >= 0),
    extensao_km        numeric(8,3) NOT NULL CHECK (extensao_km >= 0),
    extensao_geom_km   numeric(10,3) GENERATED ALWAYS AS
                       (round((ST_Length(geom::geography) / 1000)::numeric, 3)) STORED,
    cod_superficie     varchar(3)   NOT NULL REFERENCES superficie_rodovia (cod_superficie),
    jurisdicao         varchar(8)   NOT NULL CHECK (jurisdicao IN ('ESTADUAL', 'FEDERAL')),
    dt_inicio_vigencia date         NOT NULL,
    dt_fim_vigencia    date         NOT NULL,
    referencia         varchar(20)  NOT NULL,
    geom               geometry(MultiLineString, 4674) NOT NULL,
    CONSTRAINT rodovia_geom_valida CHECK (ST_IsValid(geom) AND NOT ST_IsEmpty(geom))
);
COMMENT ON TABLE rodovia IS
    'Trechos de rodovias federais e estaduais de Minas Gerais (IDE-Sisema, ref. CIDE 2021).';

CREATE TABLE ocorrencia_mamifero (
    gbif_id        bigint       PRIMARY KEY,
    taxon_key      varchar(12)  NOT NULL REFERENCES taxon (taxon_key),
    dataset_key    uuid         NOT NULL,
    instituicao    varchar(64),
    colecao        varchar(64),
    tipo_registro  varchar(20)  NOT NULL
                   CHECK (tipo_registro IN ('HUMAN_OBSERVATION', 'PRESERVED_SPECIMEN',
                                            'MATERIAL_SAMPLE', 'MATERIAL_CITATION',
                                            'MACHINE_OBSERVATION')),
    data_evento    date,
    ano            smallint     CHECK (ano BETWEEN 1700 AND 2100),
    n_individuos   integer      CHECK (n_individuos > 0),
    incerteza_m    numeric(8,1) CHECK (incerteza_m >= 0),
    localidade     text,
    licenca        varchar(10)  NOT NULL CHECK (licenca IN ('CC0_1_0', 'CC_BY_4_0')),
    ocorrencia_ref text,
    id_uc          integer      REFERENCES unidade_conservacao (id_uc) ON DELETE SET NULL,
    geom           geometry(Point, 4674) NOT NULL,
    CONSTRAINT ocorrencia_geom_valida CHECK (ST_IsValid(geom) AND NOT ST_IsEmpty(geom))
);
COMMENT ON TABLE ocorrencia_mamifero IS
    'Registros de ocorrência de mamíferos em Minas Gerais (GBIF).';
COMMENT ON COLUMN ocorrencia_mamifero.id_uc IS
    'Derivado em sql/pos_carga.sql: UC que contém o ponto (ST_Within); NULL se fora de UC.';

-- Tabela associativa (relação espacial materializada): rodovia x UC
CREATE TABLE rodovia_uc (
    id_trecho   integer      NOT NULL REFERENCES rodovia (id_trecho) ON DELETE CASCADE,
    id_uc       integer      NOT NULL REFERENCES unidade_conservacao (id_uc) ON DELETE CASCADE,
    extensao_km numeric(8,3) NOT NULL CHECK (extensao_km > 0),
    PRIMARY KEY (id_trecho, id_uc)
);
COMMENT ON TABLE rodovia_uc IS
    'Trechos de rodovia que cruzam UCs, com a extensão (km) do trecho dentro da UC. Derivada em sql/pos_carga.sql.';

-- ---------------------------------------------------------------------
-- Índices espaciais (GiST) e de apoio
-- ---------------------------------------------------------------------
CREATE INDEX idx_uc_geom         ON unidade_conservacao  USING GIST (geom);
CREATE INDEX idx_rodovia_geom    ON rodovia              USING GIST (geom);
CREATE INDEX idx_ocorrencia_geom ON ocorrencia_mamifero  USING GIST (geom);

CREATE INDEX idx_uc_categoria        ON unidade_conservacao (cod_categoria);
CREATE INDEX idx_rodovia_codigo      ON rodovia (codigo_rod);
CREATE INDEX idx_rodovia_superficie  ON rodovia (cod_superficie);
CREATE INDEX idx_ocorrencia_taxon    ON ocorrencia_mamifero (taxon_key);
CREATE INDEX idx_ocorrencia_uc       ON ocorrencia_mamifero (id_uc);
CREATE INDEX idx_rodovia_uc_uc       ON rodovia_uc (id_uc);
