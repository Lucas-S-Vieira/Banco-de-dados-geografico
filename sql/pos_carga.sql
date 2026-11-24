-- Relações espaciais derivadas (executar após sql/carga.sql):
--   psql -d <banco> -v ON_ERROR_STOP=1 -f sql/pos_carga.sql

BEGIN;

-- 1) ocorrencia_mamifero.id_uc: UC que contém o ponto (ST_Within).
--    Em caso de sobreposição de UCs (p.ex. parque dentro de APA), vale a de MENOR área
--    (a mais específica); desempate pelo menor id_uc. Fora de UC: id_uc = NULL.
UPDATE ocorrencia_mamifero o
   SET id_uc = x.id_uc
  FROM (SELECT DISTINCT ON (oc.gbif_id) oc.gbif_id, u.id_uc
          FROM ocorrencia_mamifero oc
          JOIN unidade_conservacao u ON ST_Within(oc.geom, u.geom)
         ORDER BY oc.gbif_id, u.area_ha, u.id_uc) x
 WHERE o.gbif_id = x.gbif_id;

-- 2) rodovia_uc: trechos que cruzam UCs e extensão (km) dentro de cada UC.
--    A interseção é medida sobre o elipsoide (geography); descarta-se contato < 1 m.
INSERT INTO rodovia_uc (id_trecho, id_uc, extensao_km)
SELECT r.id_trecho,
       u.id_uc,
       round((ST_Length(ST_Intersection(r.geom, u.geom)::geography) / 1000)::numeric, 3)
  FROM rodovia r
  JOIN unidade_conservacao u ON ST_Intersects(r.geom, u.geom)
 WHERE ST_Length(ST_Intersection(r.geom, u.geom)::geography) >= 1;

COMMIT;

ANALYZE;
