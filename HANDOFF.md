# HANDOFF — estado do trabalho (CSI803, Banco de Dados Geográficos)

Contexto: exercício "Coleta e Documentação de uma Base de Dados Geográficos" (Prof. Bruno R. Monteiro, UFOP). Requisitos: ≥3 tabelas espaciais, ≥2 tipos geométricos, ≥500 feições, ≥4 colunas não geométricas por tabela espacial, SRID explícito, geometrias válidas, nomes snake_case, licença que permita redistribuição, DICIONARIO.md completo, README com versões e comandos, repositório público.

## Feito (tudo testado em banco limpo: PostgreSQL 16.15 + PostGIS 3.4.2)
- Dados do aluno (dadosMg.zip): rodovias IDE-Sisema (3.444), UCs estaduais (95) e federais (95), ocorrências de mamíferos GBIF (13.655).
- `scripts/preparar_dados.py`: brutos → `dados/tratados/` (limpeza, make_valid, MULTI*, filtros; relatório em `scripts/relatorio_tratamento.txt`).
- `sql/schema.sql` (9 tabelas, PK/FK/CHECK/UNIQUE, colunas geradas `area_ha` e `extensao_geom_km`, GiST), `sql/carga.sql` (\copy), `sql/pos_carga.sql` (`id_uc` via ST_Within, `rodovia_uc` via ST_Intersects), `sql/consultas.sql`.
- `DICIONARIO.md` (tabelas geradas do catálogo por `scripts/gerar_dicionario.py <banco>`), `README.md`, `LICENSE`, `docs/der.png`.
- Resultado verificado: 190 UCs, 3.234 trechos, 13.312 ocorrências (5.193 em UC), 232 pares rodovia×UC; 0 geometrias inválidas/vazias/nulas.

## Decisões tomadas (com o aluno)
- Modelo: UC unificada (estadual+federal) + rodovia + ocorrência; relações: FK `id_uc` por ST_Within e tabela `rodovia_uc`.
- Volume: rodovias com geometria original, carga dividida em 2 CSVs (<50 MB).
- Decisões minhas, documentadas no dicionário: remover 210 trechos sem atributos; descartar ocorrências fora da caixa de MG (17), com incerteza >10 km (324) e fósseis (2); NÃO carregar recordedBy/identifiedBy/rightsHolder (dados pessoais); `id_uc` usa a UC de menor área quando há sobreposição; `area_oficial_ha` das estaduais omitida (unidades inconsistentes na fonte).

## Pendências (precisam do aluno; sem acesso à internet na sessão original)
1. **Licença das camadas IDE-Sisema**: conferir nos metadados e atualizar README/DICIONARIO/LICENSE (campo hoje "a confirmar").
2. **DOI do download GBIF** (`0012809-261118162104854`) para a citação no README.
3. Confirmar datas de coleta (GBIF 18/11/2026 inferida da chave; IDE-Sisema 23/11/2026 inferida dos arquivos) e escala/precisão das camadas.
4. Conferir descrições de `superficie_rodovia` (convenção SNV/DNIT, escritas de memória) e a equivalência IUCN de MONA (III) e RVS (IV).
5. Ocorrências em estados vizinhos dentro da caixa de MG não foram removidas (sem limite estadual); opcional: baixar malha de MG do IBGE e filtrar por ST_Within.
6. Rodar o checklist final no seu PostGIS, publicar o repo como público e conferir que nenhum arquivo passa de 100 MB (maior: ~40 MB).
