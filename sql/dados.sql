-- =============================================================================
-- dados.sql: carga dos CSVs de dados/tratados no banco criado por schema.sql
--
-- Execute com o psql A PARTIR DA RAIZ DO REPOSITÓRIO (os caminhos do \copy são relativos):
--     psql -d mamiferos_mg -f sql/dados.sql
--
-- Etapas:
--   1. \copy dos CSVs (geometria em EWKT) para tabelas temporárias de preparo;
--   2. relatório de geometrias inválidas na origem;
--   3. inserção nas tabelas finais com ST_MakeValid + ST_CollectionExtract + ST_Multi,
--      reprojeção das ocorrências (EPSG:4326 -> EPSG:4674) e cálculo de áreas/comprimentos;
--   4. relações espaciais: ocorrencia.id_uc (ST_Within) e tabela rodovia_uc (ST_Intersects);
--   5. verificação final.
-- =============================================================================

\set ON_ERROR_STOP on
SET client_encoding TO 'UTF8';

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. Preparo
-- -----------------------------------------------------------------------------

CREATE TEMP TABLE stg_uc (
    id_uc integer, cod_origem text, nome text, esfera text, sigla_categoria text,
    ato_legal text, municipios text, bioma text, geom text
) ON COMMIT DROP;

CREATE TEMP TABLE stg_rodovia (
    id_trecho integer, id_cide integer, numero_rodovia text, codigo_snv text, jurisdicao text,
    tipo_trecho text, sigla_superficie text, local_inicio text, local_fim text,
    km_inicial numeric, km_final numeric, extensao_km numeric, geom text
) ON COMMIT DROP;

CREATE TEMP TABLE stg_ocorrencia (
    id_ocorrencia bigint, taxon_key text, data_evento date, ano smallint, mes smallint,
    base_registro text, codigo_instituicao text, num_individuos integer,
    incerteza_coord_m numeric, licenca text, id_dataset uuid, geom text
) ON COMMIT DROP;

\copy categoria_uc    FROM 'dados/tratados/categoria_uc.csv'        WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy tipo_superficie FROM 'dados/tratados/tipo_superficie.csv'     WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy taxon           FROM 'dados/tratados/taxon.csv'               WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy stg_uc          FROM 'dados/tratados/unidade_conservacao.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy stg_rodovia     FROM 'dados/tratados/rodovia_1.csv'           WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy stg_rodovia     FROM 'dados/tratados/rodovia_2.csv'           WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy stg_ocorrencia  FROM 'dados/tratados/ocorrencia.csv'          WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

-- -----------------------------------------------------------------------------
-- 2. Diagnóstico das geometrias de origem
-- -----------------------------------------------------------------------------

\echo '--- Geometrias inválidas na origem (corrigidas com ST_MakeValid na etapa 3) ---'
SELECT 'unidade_conservacao' AS camada,
       count(*) FILTER (WHERE NOT ST_IsValid(ST_GeomFromEWKT(geom))) AS invalidas,
       count(*) AS total
  FROM stg_uc
UNION ALL
SELECT 'rodovia',
       count(*) FILTER (WHERE NOT ST_IsValid(ST_GeomFromEWKT(geom))), count(*)
  FROM stg_rodovia
UNION ALL
SELECT 'ocorrencia',
       count(*) FILTER (WHERE NOT ST_IsValid(ST_GeomFromEWKT(geom))), count(*)
  FROM stg_ocorrencia;

-- -----------------------------------------------------------------------------
-- 3. Tabelas finais
-- -----------------------------------------------------------------------------

INSERT INTO unidade_conservacao (id_uc, cod_origem, nome, esfera, sigla_categoria, ato_legal,
                                 municipios, bioma, area_ha, geom)
SELECT id_uc, cod_origem, nome, esfera, sigla_categoria, ato_legal, municipios, bioma,
       round((ST_Area(g::geography) / 10000.0)::numeric, 2),
       g
  FROM (SELECT s.*,
               ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_GeomFromEWKT(s.geom)), 3)) AS g
          FROM stg_uc s) t;

INSERT INTO rodovia (id_trecho, id_cide, numero_rodovia, codigo_snv, jurisdicao, tipo_trecho,
                     sigla_superficie, local_inicio, local_fim, km_inicial, km_final,
                     extensao_km, comprimento_km, geom)
SELECT id_trecho, id_cide, numero_rodovia, codigo_snv, jurisdicao, tipo_trecho,
       sigla_superficie, local_inicio, local_fim, km_inicial, km_final, extensao_km,
       round((ST_Length(g::geography) / 1000.0)::numeric, 3),
       g
  FROM (SELECT s.*,
               ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_GeomFromEWKT(s.geom)), 2)) AS g
          FROM stg_rodovia s) t;

-- GBIF publica coordenadas em WGS 84 (EPSG:4326); reprojeção explícita para SIRGAS 2000.
INSERT INTO ocorrencia (id_ocorrencia, taxon_key, data_evento, ano, mes, base_registro,
                        codigo_instituicao, num_individuos, incerteza_coord_m, licenca,
                        id_dataset, geom)
SELECT id_ocorrencia, taxon_key, data_evento, ano, mes, base_registro, codigo_instituicao,
       num_individuos, incerteza_coord_m, licenca, id_dataset,
       ST_Transform(ST_GeomFromEWKT(geom), 4674)
  FROM stg_ocorrencia;

ANALYZE unidade_conservacao;
ANALYZE rodovia;
ANALYZE ocorrencia;

-- -----------------------------------------------------------------------------
-- 4. Relações espaciais materializadas
-- -----------------------------------------------------------------------------

-- 4.1 Cada ocorrência recebe a UC que a contém. Onde UCs se sobrepõem (ex.: Parque dentro
--     de uma APA), escolhe-se a de MENOR área, isto é, a mais específica.
UPDATE ocorrencia o
   SET id_uc = sub.id_uc
  FROM (SELECT DISTINCT ON (o2.id_ocorrencia) o2.id_ocorrencia, u.id_uc
          FROM ocorrencia o2
          JOIN unidade_conservacao u ON ST_Within(o2.geom, u.geom)
         ORDER BY o2.id_ocorrencia, u.area_ha ASC) sub
 WHERE o.id_ocorrencia = sub.id_ocorrencia;

-- 4.2 Trechos de rodovia que atravessam UCs, com a extensão (km) dentro de cada UC.
INSERT INTO rodovia_uc (id_trecho, id_uc, comprimento_km)
SELECT id_trecho, id_uc, km
  FROM (SELECT r.id_trecho, u.id_uc,
               round((ST_Length(ST_Intersection(r.geom, u.geom)::geography) / 1000.0)::numeric, 3) AS km
          FROM rodovia r
          JOIN unidade_conservacao u ON ST_Intersects(r.geom, u.geom)) t
 WHERE km > 0;

COMMIT;

ANALYZE;

-- -----------------------------------------------------------------------------
-- 5. Verificação final
-- -----------------------------------------------------------------------------

\echo '--- Contagem de registros e validade das geometrias ---'
SELECT 'unidade_conservacao' AS tabela, GeometryType(geom) AS tipo, ST_SRID(geom) AS srid,
       count(*) AS registros, count(*) FILTER (WHERE NOT ST_IsValid(geom)) AS invalidas
  FROM unidade_conservacao GROUP BY 2, 3
UNION ALL
SELECT 'rodovia', GeometryType(geom), ST_SRID(geom), count(*),
       count(*) FILTER (WHERE NOT ST_IsValid(geom))
  FROM rodovia GROUP BY 2, 3
UNION ALL
SELECT 'ocorrencia', GeometryType(geom), ST_SRID(geom), count(*),
       count(*) FILTER (WHERE NOT ST_IsValid(geom))
  FROM ocorrencia GROUP BY 2, 3
ORDER BY 1;

\echo '--- Tabelas sem geometria ---'
SELECT 'categoria_uc' AS tabela, count(*) AS registros FROM categoria_uc
UNION ALL SELECT 'tipo_superficie', count(*) FROM tipo_superficie
UNION ALL SELECT 'taxon', count(*) FROM taxon
UNION ALL SELECT 'rodovia_uc', count(*) FROM rodovia_uc;

\echo '--- Ocorrências dentro de alguma UC ---'
SELECT count(*) FILTER (WHERE id_uc IS NOT NULL) AS dentro_de_uc, count(*) AS total
  FROM ocorrencia;
