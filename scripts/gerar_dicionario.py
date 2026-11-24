#!/usr/bin/env python3
"""Gera a seção de tabelas do DICIONARIO.md a partir do catálogo do banco (tipos, nulos,
PK/FK, nº de registros, exemplos reais) + descrições escritas abaixo.

Uso: python scripts/gerar_dicionario.py <banco> > docs/dicionario_tabelas.md
Requer psql no PATH e o banco já carregado (schema + carga + pos_carga).
"""
import subprocess
import sys

BANCO = sys.argv[1]

DESC = {
 "categoria_uc": ("Domínio: categorias de UC (SNUC) e equivalência IUCN.", {
  "cod_categoria": "Sigla da categoria (ESEC, REBIO, PAR, MONA, RVS, RPPN, APA, FLO, RDS).",
  "nome": "Nome da categoria.", "grupo": "Grupo do SNUC: PROTECAO_INTEGRAL ou USO_SUSTENTAVEL.",
  "cat_iucn": "Categoria de manejo IUCN equivalente (Ia, II, III, IV, V, VI)."}),
 "superficie_rodovia": ("Domínio: situação/superfície do trecho rodoviário (convenção SNV/DNIT).", {
  "cod_superficie": "Código da superfície/situação do trecho.", "descricao": "Descrição do código."}),
 "taxon": ("Domínio: táxons de mamíferos citados nas ocorrências.", {
  "taxon_key": "Chave do táxon no GBIF Backbone (taxonKey).",
  "nivel_taxonomico": "Nível em que o registro foi identificado (SPECIES, GENUS, FAMILY...).",
  "nome_cientifico": "Nome científico com autoria.", "especie": "Espécie (NULL se identificado em nível superior).",
  "genero": "Gênero.", "familia": "Família.", "ordem": "Ordem."}),
 "unidade_conservacao": ("Unidades de conservação estaduais e federais (polígonos).", {
  "id_uc": "Identificador interno desta base (sequencial na carga).",
  "nome": "Nome da UC. Estaduais vêm sem acentos na fonte; federais foram convertidas de CAIXA ALTA para Título.",
  "cod_categoria": "Categoria da UC (FK para categoria_uc).",
  "esfera": "Esfera administrativa: ESTADUAL (IEF/MG) ou FEDERAL (ICMBio).",
  "id_origem": "Campo id do shapefile de origem (único dentro da esfera).",
  "cd_cnuc": "Código no Cadastro Nacional de UCs (somente federais; NULL nas estaduais).",
  "ato_legal": "Ato legal de criação, como informado na fonte.",
  "bioma": "Bioma(s) separados por '/'. Federais: derivado das colunas de área por bioma da fonte (>0).",
  "municipios": "Municípios de MG abrangidos, separados por '; '.",
  "area_oficial_ha": "Área oficial (ha) do ato de criação. Somente federais: a coluna área oficial das estaduais tem unidades inconsistentes na fonte.",
  "area_ha": "Área calculada (ha) sobre o elipsoide a partir da geometria (coluna gerada).",
  "geom": "Limite da UC."}),
 "rodovia": ("Trechos de rodovias federais e estaduais (linhas).", {
  "id_trecho": "Identificador do trecho (campo id da fonte).", "id_cide": "Identificador do trecho na base CIDE.",
  "codigo_rod": "Número da rodovia, sem prefixo (ex.: 040).",
  "codigo_snv": "Código do trecho no SNV, como informado na fonte.",
  "tipo_trecho": "Eixo Principal ou Acesso.", "uf": "Unidade da federação (MG).",
  "local_inicio": "Local de início do trecho.", "local_fim": "Local de fim do trecho.",
  "km_inicio": "Quilometragem inicial.", "km_fim": "Quilometragem final.",
  "extensao_km": "Extensão (km) informada na fonte.",
  "extensao_geom_km": "Extensão (km) calculada sobre o elipsoide a partir da geometria (coluna gerada). Pode diferir de extensao_km.",
  "cod_superficie": "Situação/superfície do trecho (FK para superficie_rodovia).",
  "jurisdicao": "ESTADUAL ou FEDERAL.", "dt_inicio_vigencia": "Início de vigência do registro.",
  "dt_fim_vigencia": "Fim de vigência do registro.", "referencia": "Base de referência da fonte (cide2021).",
  "geom": "Traçado do trecho."}),
 "ocorrencia_mamifero": ("Registros de ocorrência de mamíferos em MG (pontos).", {
  "gbif_id": "Identificador da ocorrência no GBIF (gbifID).", "taxon_key": "Táxon (FK para taxon).",
  "dataset_key": "UUID do conjunto de dados de origem no GBIF (usar para atribuição).",
  "instituicao": "Código da instituição publicadora.", "colecao": "Código da coleção.",
  "tipo_registro": "Base do registro (basisOfRecord): observação humana, espécime preservado etc.",
  "data_evento": "Data completa do evento; NULL quando a fonte só tem ano/mês.",
  "ano": "Ano do evento.", "n_individuos": "Número de indivíduos, quando informado.",
  "incerteza_m": "Incerteza da coordenada (m), quando informada. Registros > 10 km foram descartados.",
  "localidade": "Descrição textual do local, quando informada.",
  "licenca": "Licença do registro no GBIF (CC0_1_0 ou CC_BY_4_0).",
  "ocorrencia_ref": "Identificador/URL da ocorrência no publicador original.",
  "id_uc": "UC que contém o ponto (ST_Within), derivada em pos_carga.sql; NULL fora de UC. Em sobreposição, a de menor área.",
  "geom": "Localização do registro (longitude/latitude)."}),
 "rodovia_uc": ("Associativa: trechos de rodovia que cruzam UCs (derivada espacialmente).", {
  "id_trecho": "Trecho de rodovia (FK).", "id_uc": "UC cruzada (FK).",
  "extensao_km": "Extensão (km) do trecho dentro da UC, medida sobre o elipsoide."}),
}
ORDEM = ["categoria_uc", "superficie_rodovia", "taxon", "unidade_conservacao", "rodovia",
         "ocorrencia_mamifero", "rodovia_uc"]


def sql(q):
    out = subprocess.run(["psql", "-d", BANCO, "-At", "-F", "\t", "-c", q], capture_output=True,
                         text=True, check=True).stdout
    return [l.split("\t") for l in out.splitlines()]


def md(x):
    return str(x).replace("|", "\\|").replace("\n", " ")


for t in ORDEM:
    desc, cols = DESC[t]
    n = sql(f"select count(*) from {t}")[0][0]
    geo = sql(f"select type, srid from geometry_columns where f_table_name='{t}'")
    cab = f"### Tabela `{t}`\n\n{desc} "
    cab += (f"**Geometria:** {geo[0][0].title()} · **SRID:** {geo[0][1]} · " if geo else "**Sem geometria** · ")
    print(cab + f"**Registros:** {int(n):,}".replace(",", ".") + "\n")
    print("| Coluna | Tipo | Tam./Domínio | Nulo? | PK/FK | Descrição | Exemplo |")
    print("|---|---|---|---|---|---|---|")
    pk = {r[0] for r in sql(f"""select a.attname from pg_index i join pg_attribute a on a.attrelid=i.indrelid
        and a.attnum=any(i.indkey) where i.indrelid='{t}'::regclass and i.indisprimary""")}
    fk = {r[0]: f"{r[1]}.{r[2]}" for r in sql(f"""select a.attname, c2.relname, a2.attname from pg_constraint c
        join pg_class c2 on c2.oid=c.confrelid join pg_attribute a on a.attrelid=c.conrelid and a.attnum=c.conkey[1]
        join pg_attribute a2 on a2.attrelid=c.confrelid and a2.attnum=c.confkey[1]
        where c.conrelid='{t}'::regclass and c.contype='f'""")}
    for nome, tipo, tam, nulo, gerada in sql(f"""select column_name, data_type, coalesce(character_maximum_length::text,
        case when numeric_precision is not null and data_type='numeric' then numeric_precision||','||numeric_scale end,''),
        is_nullable, is_generated from information_schema.columns where table_name='{t}' order by ordinal_position"""):
        if nome == "geom":
            tipo = "geometry"
            tam = f"{geo[0][0].title()}, {geo[0][1]}"
            ex = "(geometria)"
        else:
            r = sql(f"select {nome}::text from {t} where {nome} is not null order by 1 limit 1 offset 3")
            r = r or sql(f"select {nome}::text from {t} where {nome} is not null limit 1")
            ex = r[0][0][:45] if r else "—"
        tipo = {"character varying": "varchar", "character": "char", "double precision": "float8"}.get(tipo, tipo)
        marca = "PK" if nome in pk else (f"FK → {fk[nome]}" if nome in fk else "")
        if t == "rodovia_uc" and nome in pk and nome in fk:
            marca = f"PK, FK → {fk[nome]}"
        if gerada == "ALWAYS":
            tipo += " (gerada)"
        print(f"| `{nome}` | {tipo} | {tam} | {'Sim' if nulo == 'YES' else 'Não'} | {marca} | "
              f"{md(cols[nome])} | {md(ex)} |")
    print()
