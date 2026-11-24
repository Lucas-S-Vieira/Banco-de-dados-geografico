-- Consultas espaciais de exemplo e verificações (executar após carga e pos_carga).

-- ---------------------------------------------------------------------
-- A) Verificações do checklist de entrega
-- ---------------------------------------------------------------------

-- A1. Tabelas espaciais, tipos geométricos e SRID registrados
SELECT f_table_name AS tabela, type AS tipo_geometria, srid
  FROM geometry_columns
 WHERE f_table_schema = 'public'
 ORDER BY f_table_name;

-- A2. Número de feições por tabela espacial (total >= 500)
SELECT 'unidade_conservacao' AS tabela, count(*) AS feicoes FROM unidade_conservacao
UNION ALL SELECT 'rodovia', count(*) FROM rodovia
UNION ALL SELECT 'ocorrencia_mamifero', count(*) FROM ocorrencia_mamifero;

-- A3. Geometrias inválidas, vazias ou nulas (esperado: 0 em todas as linhas)
SELECT 'unidade_conservacao' AS tabela,
       count(*) FILTER (WHERE NOT ST_IsValid(geom)) AS invalidas,
       count(*) FILTER (WHERE ST_IsEmpty(geom))     AS vazias,
       count(*) FILTER (WHERE geom IS NULL)         AS nulas
  FROM unidade_conservacao
UNION ALL
SELECT 'rodovia', count(*) FILTER (WHERE NOT ST_IsValid(geom)),
       count(*) FILTER (WHERE ST_IsEmpty(geom)), count(*) FILTER (WHERE geom IS NULL)
  FROM rodovia
UNION ALL
SELECT 'ocorrencia_mamifero', count(*) FILTER (WHERE NOT ST_IsValid(geom)),
       count(*) FILTER (WHERE ST_IsEmpty(geom)), count(*) FILTER (WHERE geom IS NULL)
  FROM ocorrencia_mamifero;

-- ---------------------------------------------------------------------
-- B) Consultas de exemplo
-- ---------------------------------------------------------------------

-- B1. Riqueza de espécies e nº de registros por UC (via chave id_uc)
SELECT u.nome, u.esfera, count(*) AS registros,
       count(DISTINCT t.especie) AS especies
  FROM ocorrencia_mamifero o
  JOIN unidade_conservacao u ON u.id_uc = o.id_uc
  JOIN taxon t ON t.taxon_key = o.taxon_key
 GROUP BY u.id_uc, u.nome, u.esfera
 ORDER BY especies DESC, registros DESC
 LIMIT 10;

-- B2. Percentual de registros dentro de UCs, por ordem de mamíferos
SELECT t.ordem,
       count(*) AS registros,
       round(100.0 * count(o.id_uc) / count(*), 1) AS pct_em_uc
  FROM ocorrencia_mamifero o
  JOIN taxon t ON t.taxon_key = o.taxon_key
 GROUP BY t.ordem
 ORDER BY registros DESC;

-- B3. Rodovias que mais atravessam UCs (km dentro de UC), via tabela rodovia_uc
SELECT r.jurisdicao, r.codigo_rod, count(DISTINCT ru.id_uc) AS qtd_ucs,
       round(sum(ru.extensao_km), 1) AS km_em_uc
  FROM rodovia_uc ru
  JOIN rodovia r ON r.id_trecho = ru.id_trecho
 GROUP BY r.jurisdicao, r.codigo_rod
 ORDER BY km_em_uc DESC
 LIMIT 10;

-- B4. Ocorrências a até 1 km de uma rodovia (proximidade; medida em metros via geography)
SELECT r.codigo_rod, r.jurisdicao, count(*) AS registros_ate_1km
  FROM rodovia r
  JOIN ocorrencia_mamifero o
    ON r.geom && ST_Expand(o.geom, 0.01)  -- pré-filtro com índice GiST (~1,1 km)
   AND ST_DWithin(r.geom::geography, o.geom::geography, 1000)
 GROUP BY r.codigo_rod, r.jurisdicao
 ORDER BY registros_ate_1km DESC
 LIMIT 10;

-- B5. Registros de mamíferos fora de qualquer UC, mas a < 500 m de uma UC
SELECT count(*) AS registros_no_entorno
  FROM ocorrencia_mamifero o
 WHERE o.id_uc IS NULL
   AND EXISTS (SELECT 1 FROM unidade_conservacao u
                WHERE u.geom && ST_Expand(o.geom, 0.01)  -- pré-filtro com índice GiST
                  AND ST_DWithin(o.geom::geography, u.geom::geography, 500));

-- B6. UCs por categoria e grupo, com área total (ha)
SELECT c.nome AS categoria, c.grupo, count(*) AS qtd, round(sum(u.area_ha)) AS area_total_ha
  FROM unidade_conservacao u
  JOIN categoria_uc c USING (cod_categoria)
 GROUP BY c.nome, c.grupo
 ORDER BY area_total_ha DESC;
