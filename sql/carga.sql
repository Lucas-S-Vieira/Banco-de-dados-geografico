-- Carga dos dados tratados (dados/tratados/*.csv) via \copy.
-- Execute A PARTIR DA RAIZ DO REPOSITÓRIO (os caminhos são relativos):
--   psql -d <banco> -v ON_ERROR_STOP=1 -f sql/carga.sql
-- Geometrias: EWKB hexadecimal (polígonos/linhas) e EWKT (pontos), SRID 4674.
-- As colunas geradas (area_ha, extensao_geom_km) são calculadas pelo banco.

BEGIN;

\copy taxon (taxon_key, nivel_taxonomico, nome_cientifico, especie, genero, familia, ordem) FROM 'dados/tratados/taxon.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

\copy unidade_conservacao (id_uc, nome, cod_categoria, esfera, id_origem, cd_cnuc, ato_legal, bioma, municipios, area_oficial_ha, geom) FROM 'dados/tratados/unidade_conservacao.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

-- Rodovias: dividida em 2 arquivos (< 50 MB cada) por causa do limite do GitHub
\copy rodovia (id_trecho, id_cide, codigo_rod, codigo_snv, tipo_trecho, uf, local_inicio, local_fim, km_inicio, km_fim, extensao_km, cod_superficie, jurisdicao, dt_inicio_vigencia, dt_fim_vigencia, referencia, geom) FROM 'dados/tratados/rodovia_01.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy rodovia (id_trecho, id_cide, codigo_rod, codigo_snv, tipo_trecho, uf, local_inicio, local_fim, km_inicio, km_fim, extensao_km, cod_superficie, jurisdicao, dt_inicio_vigencia, dt_fim_vigencia, referencia, geom) FROM 'dados/tratados/rodovia_02.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

\copy ocorrencia_mamifero (gbif_id, taxon_key, dataset_key, instituicao, colecao, tipo_registro, data_evento, ano, n_individuos, incerteza_m, localidade, licenca, ocorrencia_ref, geom) FROM 'dados/tratados/ocorrencia_mamifero.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

COMMIT;
