# Dicionário de dados — Mamíferos, Unidades de Conservação e Rodovias em MG

Autor: Lucas Salgado Vieira (matrícula 22.2.8083) · CSI803 – Banco de Dados Geográficos · UFOP · Prof. Bruno R. Monteiro

## 1. Visão geral da base

| Item | Descrição |
|---|---|
| **Título** | Mamíferos, Unidades de Conservação e Rodovias em Minas Gerais (`mamiferos_uc_rodovias_mg`) |
| **Descrição e finalidade** | Base com unidades de conservação (UCs) estaduais e federais, trechos de rodovias federais e estaduais e registros de ocorrência de mamíferos de Minas Gerais. Finalidade: apoiar análises da biodiversidade registrada dentro e no entorno de UCs e da exposição da fauna e das UCs à malha rodoviária. |
| **Fontes** | **UCs estaduais e federais** e **rodovias:** IDE-Sisema/SEMAD-MG, camadas `ide_2010_mg_unidades_conservacao_estaduais_pol`, `ide_2010_mg_unidades_conservacao_federais_pol` e `ide_0401_mg_rodovias_lin` (https://idesisema.meioambiente.mg.gov.br). **Ocorrências:** GBIF.org, download `0012809-261118162104854` (https://www.gbif.org/occurrence/download/0012809-261118162104854), filtro Mammalia, Minas Gerais. |
| **Data de coleta** | GBIF: 23/11/2026, data de criação do download `0012809-261118162104854` (DOI 10.15468/dl.k5vaf5), conferida na API do GBIF. IDE-Sisema: 23/11/2026. |
| **Licença** | GBIF: cada registro é CC0 1.0 (439) ou CC BY 4.0 (12.873), ambas permitem redistribuição (CC BY exige atribuição, ver README). IDE-Sisema, conforme o campo "restrições" de cada metadado (consultado em 23/11/2026): **UCs estaduais sob CC BY 4.0**, que permite redistribuição e produtos derivados com atribuição ao IEF/IDE-Sisema e indicação das alterações; **UCs federais e rodovias**: *"O acesso ao dado é livre"*, sem licença nomeada, redistribuídas com atribuição à fonte. As alterações feitas estão em "Tratamentos aplicados". Licença do código: MIT (ver `LICENSE`). |
| **Cobertura espacial** | Estado de Minas Gerais (UCs, rodovias e ocorrências). |
| **Cobertura temporal** | Rodovias: referência CIDE 2021 (vigência 01/01/2013 a 30/10/2029 na fonte). UCs: versão da camada baixada em 23/11/2026. Ocorrências: de 1901 a 2026. |
| **SRID e justificativa** | **EPSG:4674 (SIRGAS 2000)**, datum oficial do Brasil e CRS nativo das três camadas IDE-Sisema, o que evita reprojeção. As coordenadas do GBIF (WGS 84, EPSG:4326) foram rotuladas como 4674 sem transformação: os dois referenciais coincidem na escala de metros. Medidas em metros/hectares usam `geography` (elipsoide). |
| **Escala e precisão** | Pelos metadados da IDE-Sisema: **UCs estaduais**, escala 1:10.000; **UCs federais**, multiescala de 1:10.000 a 1:250.000 (polígonos de origens diversas, alguns do IBDF/IBAMA, uns pelo memorial descritivo e outros estimados; ver `quali_pol` na fonte); **rodovias**, sem escala declarada (malha estadual compilada pelo DNIT no SNV de nov/2018, atualizada em 12/2021). Ocorrências: coordenadas com 6 casas decimais; incerteza (`incerteza_m`) informada em ~6% dos registros; descartados os com incerteza > 10 km. |
| **Tratamentos aplicados** | 1. Rodovias: removidos 210 trechos sem nenhum atributo descritivo (código, jurisdição, superfície etc.). 2. Geometrias validadas (`make_valid` do Shapely, equivalente a `ST_MakeValid`): 1 UC estadual corrigida (auto-interseção); todas convertidas para `MULTI*`. 3. UCs estaduais e federais unificadas em uma tabela, com `esfera`; categorias padronizadas por sigla; nomes federais de CAIXA ALTA para Título; bioma federal derivado das áreas por bioma; municípios padronizados (separados por `; `, apenas os de MG). 4. Ocorrências: removidos 17 registros fora da caixa envolvente de MG, 324 com incerteza > 10 km e 2 fósseis; mantida data completa só quando disponível; **colunas com dados pessoais (observador, identificador, detentor de direitos) não foram carregadas**. 5. Nomes de tabelas e colunas em `snake_case` sem acentos; texto em UTF-8. 6. Relações espaciais derivadas em SQL (`pos_carga.sql`): `ocorrencia_mamifero.id_uc` (`ST_Within`) e `rodovia_uc` (`ST_Intersects`/`ST_Intersection`). Detalhes e contagens em `scripts/relatorio_tratamento.txt`. |

**Limitações conhecidas:** (i) ocorrências em MG dentro da caixa envolvente mas em estados vizinhos não foram removidas (não há limite estadual na base); (ii) UCs estaduais e federais se sobrepõem em parte (27 pares), por isso `id_uc` usa a UC de menor área; (iii) o GBIF tem viés amostral (mais registros perto de estradas, centros urbanos e UCs com pesquisa ICMBio); (iv) `extensao_km` (fonte) difere de `extensao_geom_km` (geometria) em parte dos trechos.

## 2. Descrição das tabelas

### Tabela `categoria_uc`

Domínio: categorias de UC (SNUC) e equivalência IUCN. **Sem geometria** · **Registros:** 9

| Coluna | Tipo | Tam./Domínio | Nulo? | PK/FK | Descrição | Exemplo |
|---|---|---|---|---|---|---|
| `cod_categoria` | varchar | 5 | Não | PK | Sigla da categoria (ESEC, REBIO, PAR, MONA, RVS, RPPN, APA, FLO, RDS). | MONA |
| `nome` | varchar | 60 | Não |  | Nome da categoria. | Parque (Nacional ou Estadual) |
| `grupo` | varchar | 20 | Não |  | Grupo do SNUC: PROTECAO_INTEGRAL ou USO_SUSTENTAVEL. | PROTECAO_INTEGRAL |
| `cat_iucn` | varchar | 3 | Não |  | Categoria de manejo IUCN equivalente (Ia, II, III, IV, V, VI). | IV |

### Tabela `superficie_rodovia`

Domínio: situação/superfície do trecho rodoviário (convenção SNV/DNIT). **Sem geometria** · **Registros:** 7

| Coluna | Tipo | Tam./Domínio | Nulo? | PK/FK | Descrição | Exemplo |
|---|---|---|---|---|---|---|
| `cod_superficie` | varchar | 3 | Não | PK | Código da superfície/situação do trecho. | IMP |
| `descricao` | varchar | 60 | Não |  | Descrição do código. | Implantada (sem pavimento) |

### Tabela `taxon`

Domínio: táxons de mamíferos citados nas ocorrências. **Sem geometria** · **Registros:** 414

| Coluna | Tipo | Tam./Domínio | Nulo? | PK/FK | Descrição | Exemplo |
|---|---|---|---|---|---|---|
| `taxon_key` | varchar | 12 | Não | PK | Chave do táxon no GBIF Backbone (taxonKey). | 349R5 |
| `nivel_taxonomico` | varchar | 10 | Não |  | Nível em que o registro foi identificado (SPECIES, GENUS, FAMILY...). | FAMILY |
| `nome_cientifico` | varchar | 120 | Não |  | Nome científico com autoria. | Akodon lindberghi Hershkovitz, 1990 |
| `especie` | varchar | 60 | Sim |  | Espécie (NULL se identificado em nível superior). | Akodon montensis |
| `genero` | varchar | 60 | Sim |  | Gênero. | Akodon |
| `familia` | varchar | 60 | Sim |  | Família. | Atelidae |
| `ordem` | varchar | 60 | Sim |  | Ordem. | Artiodactyla |

### Tabela `unidade_conservacao`

Unidades de conservação estaduais e federais (polígonos). **Geometria:** Multipolygon · **SRID:** 4674 · **Registros:** 190

| Coluna | Tipo | Tam./Domínio | Nulo? | PK/FK | Descrição | Exemplo |
|---|---|---|---|---|---|---|
| `id_uc` | integer |  | Não | PK | Identificador interno desta base (sequencial na carga). | 101 |
| `nome` | varchar | 150 | Não |  | Nome da UC. Estaduais vêm sem acentos na fonte; federais foram convertidas de CAIXA ALTA para Título. | APA Estadual Fernao Dias |
| `cod_categoria` | varchar | 5 | Não | FK → categoria_uc.cod_categoria | Categoria da UC (FK para categoria_uc). | APA |
| `esfera` | varchar | 8 | Não |  | Esfera administrativa: ESTADUAL (IEF/MG) ou FEDERAL (ICMBio). | ESTADUAL |
| `id_origem` | integer |  | Não |  | Campo id do shapefile de origem (único dentro da esfera). | 10 |
| `cd_cnuc` | varchar | 15 | Sim |  | Código no Cadastro Nacional de UCs (somente federais; NULL nas estaduais). | 0000.00.0027 |
| `ato_legal` | varchar | 200 | Não |  | Ato legal de criação, como informado na fonte. | DEC 12.888 de 23/03/2026 |
| `bioma` | varchar | 60 | Sim |  | Bioma(s) separados por '/'. Federais: derivado das colunas de área por bioma da fonte (>0). | Caatinga/Cerrado |
| `municipios` | text |  | Não |  | Municípios de MG abrangidos, separados por '; '. | Aiuruoca; Alagoa; Baependi; Itamonte; Pouso A |
| `area_oficial_ha` | numeric | 12,2 | Sim |  | Área oficial (ha) do ato de criação. Somente federais: a coluna área oficial das estaduais tem unidades inconsistentes na fonte. | 1.85 |
| `area_ha` | numeric (gerada) | 12,2 | Sim |  | Área calculada (ha) sobre o elipsoide a partir da geometria (coluna gerada). | 1.85 |
| `geom` | geometry | Multipolygon, 4674 | Não |  | Limite da UC. | (geometria) |

### Tabela `rodovia`

Trechos de rodovias federais e estaduais (linhas). **Geometria:** Multilinestring · **SRID:** 4674 · **Registros:** 3.234

| Coluna | Tipo | Tam./Domínio | Nulo? | PK/FK | Descrição | Exemplo |
|---|---|---|---|---|---|---|
| `id_trecho` | integer |  | Não | PK | Identificador do trecho (campo id da fonte). | 1000 |
| `id_cide` | integer |  | Não |  | Identificador do trecho na base CIDE. | 1001 |
| `codigo_rod` | varchar | 10 | Não |  | Número da rodovia, sem prefixo (ex.: 040). | 010 |
| `codigo_snv` | varchar | 15 | Não |  | Código do trecho no SNV, como informado na fonte. | 010EMG0005 |
| `tipo_trecho` | varchar | 20 | Não |  | Eixo Principal ou Acesso. | Acesso |
| `uf` | char | 2 | Não |  | Unidade da federação (MG). | MG |
| `local_inicio` | varchar | 120 | Não |  | Local de início do trecho. | ABREUS |
| `local_fim` | varchar | 120 | Sim |  | Local de fim do trecho. | ABADIA DOS DOURADOS |
| `km_inicio` | numeric | 8,3 | Não |  | Quilometragem inicial. | 0.000 |
| `km_fim` | numeric | 8,3 | Não |  | Quilometragem final. | 0.250 |
| `extensao_km` | numeric | 8,3 | Não |  | Extensão (km) informada na fonte. | 0.100 |
| `extensao_geom_km` | numeric (gerada) | 10,3 | Sim |  | Extensão (km) calculada sobre o elipsoide a partir da geometria (coluna gerada). Pode diferir de extensao_km. | 0.111 |
| `cod_superficie` | varchar | 3 | Não | FK → superficie_rodovia.cod_superficie | Situação/superfície do trecho (FK para superficie_rodovia). | DUP |
| `jurisdicao` | varchar | 8 | Não |  | ESTADUAL ou FEDERAL. | ESTADUAL |
| `dt_inicio_vigencia` | date |  | Não |  | Início de vigência do registro. | 2013-01-01 |
| `dt_fim_vigencia` | date |  | Não |  | Fim de vigência do registro. | 2029-10-30 |
| `referencia` | varchar | 20 | Não |  | Base de referência da fonte (cide2021). | cide2021 |
| `geom` | geometry | Multilinestring, 4674 | Não |  | Traçado do trecho. | (geometria) |

### Tabela `ocorrencia_mamifero`

Registros de ocorrência de mamíferos em MG (pontos). **Geometria:** Point · **SRID:** 4674 · **Registros:** 13.312

| Coluna | Tipo | Tam./Domínio | Nulo? | PK/FK | Descrição | Exemplo |
|---|---|---|---|---|---|---|
| `gbif_id` | bigint |  | Não | PK | Identificador da ocorrência no GBIF (gbifID). | 1211774269 |
| `taxon_key` | varchar | 12 | Não | FK → taxon.taxon_key | Táxon (FK para taxon). | 349QV |
| `dataset_key` | uuid |  | Não |  | UUID do conjunto de dados de origem no GBIF (usar para atribuição). | 040c5662-da76-4782-a48e-cdea1892d14c |
| `instituicao` | varchar | 64 | Sim |  | Código da instituição publicadora. | FMNH |
| `colecao` | varchar | 64 | Sim |  | Código da coleção. | Dados de Pesquisa SISBio |
| `tipo_registro` | varchar | 20 | Não |  | Base do registro (basisOfRecord): observação humana, espécime preservado etc. | HUMAN_OBSERVATION |
| `data_evento` | date |  | Sim |  | Data completa do evento; NULL quando a fonte só tem ano/mês. | 1914-01-02 |
| `ano` | smallint |  | Sim |  | Ano do evento. | 1914 |
| `n_individuos` | integer |  | Sim |  | Número de indivíduos, quando informado. | 1 |
| `incerteza_m` | numeric | 8,1 | Sim |  | Incerteza da coordenada (m), quando informada. Registros > 10 km foram descartados. | 10.0 |
| `localidade` | text |  | Sim |  | Descrição textual do local, quando informada. | Agricultural College, Vicosa |
| `licenca` | varchar | 10 | Não |  | Licença do registro no GBIF (CC0_1_0 ou CC_BY_4_0). | CC0_1_0 |
| `ocorrencia_ref` | text |  | Sim |  | Identificador/URL da ocorrência no publicador original. | 0220EB99B45B2 |
| `id_uc` | integer |  | Sim | FK → unidade_conservacao.id_uc | UC que contém o ponto (ST_Within), derivada em pos_carga.sql; NULL fora de UC. Em sobreposição, a de menor área. | 10 |
| `geom` | geometry | Point, 4674 | Não |  | Localização do registro (longitude/latitude). | (geometria) |

### Tabela `rodovia_uc`

Associativa: trechos de rodovia que cruzam UCs (derivada espacialmente). **Sem geometria** · **Registros:** 232

| Coluna | Tipo | Tam./Domínio | Nulo? | PK/FK | Descrição | Exemplo |
|---|---|---|---|---|---|---|
| `id_trecho` | integer |  | Não | PK, FK → rodovia.id_trecho | Trecho de rodovia (FK). | 1103 |
| `id_uc` | integer |  | Não | PK, FK → unidade_conservacao.id_uc | UC cruzada (FK). | 12 |
| `extensao_km` | numeric | 8,3 | Não |  | Extensão (km) do trecho dentro da UC, medida sobre o elipsoide. | 0.018 |

## 3. Domínios e valores permitidos

| Campo | Valores |
|---|---|
| `unidade_conservacao.esfera` / `rodovia.jurisdicao` | `ESTADUAL`, `FEDERAL` |
| `categoria_uc.grupo` | `PROTECAO_INTEGRAL`, `USO_SUSTENTAVEL` |
| `rodovia.tipo_trecho` | `Eixo Principal`, `Acesso` |
| `ocorrencia_mamifero.tipo_registro` | `HUMAN_OBSERVATION`, `PRESERVED_SPECIMEN`, `MATERIAL_SAMPLE`, `MATERIAL_CITATION`, `MACHINE_OBSERVATION` |
| `ocorrencia_mamifero.licenca` | `CC0_1_0`, `CC_BY_4_0` |
| `taxon.nivel_taxonomico` | `CLASS`, `ORDER`, `FAMILY`, `GENUS`, `SPECIES`, `SUBSPECIES`, `UNRANKED` |
| `categoria_uc`, `superficie_rodovia` | ver conteúdo das próprias tabelas (inseridas em `sql/schema.sql`) |

## 4. Relacionamentos

- `unidade_conservacao.cod_categoria` → `categoria_uc.cod_categoria`
- `rodovia.cod_superficie` → `superficie_rodovia.cod_superficie`
- `ocorrencia_mamifero.taxon_key` → `taxon.taxon_key`
- `ocorrencia_mamifero.id_uc` → `unidade_conservacao.id_uc` (derivado espacialmente, `ST_Within`)
- `rodovia_uc` (`id_trecho`, `id_uc`) → `rodovia`, `unidade_conservacao` (derivado, `ST_Intersects`)

Diagrama: `docs/der.png`.
