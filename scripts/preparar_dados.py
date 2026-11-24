#!/usr/bin/env python3
"""Tratamento dos dados brutos -> dados/tratados/ (prontos para \\copy no PostGIS).

Uso (a partir da raiz do repositório):
    pip install -r scripts/requirements.txt
    python scripts/preparar_dados.py

Entradas  (dados/brutos/): 3 zips de shapefiles da IDE-Sisema (MG) e 1 zip do GBIF.
Saídas    (dados/tratados/): CSVs com geometria em EWKB hexadecimal (polígonos e linhas)
ou EWKT (pontos), SRID 4674, e o relatório scripts/relatorio_tratamento.txt.

O script é determinístico (não há aleatoriedade) e idempotente.
"""
import csv
import io
import re
import sys
import zipfile
from collections import Counter, OrderedDict
from datetime import date
from pathlib import Path

import shapefile  # pyshp
from shapely import wkb
from shapely.geometry import MultiLineString, MultiPolygon, shape
from shapely.validation import make_valid

RAIZ = Path(__file__).resolve().parent.parent
BRUTOS = RAIZ / "dados" / "brutos"
TRATADOS = RAIZ / "dados" / "tratados"
SRID = 4674
LIMITE_BYTES_PARTE = 40_000_000  # < 50 MB por arquivo (limite do GitHub: 100 MB)

# Caixa envolvente de Minas Gerais (com pequena margem), em graus (SIRGAS 2000)
MG_LON = (-51.10, -39.80)
MG_LAT = (-22.95, -14.20)
INCERTEZA_MAX_M = 10_000  # registros GBIF menos precisos que isso são descartados

relatorio = []


def log(msg=""):
    print(msg)
    relatorio.append(msg)


# --------------------------------------------------------------------------- util
def abrir_shp(zip_path, base):
    z = zipfile.ZipFile(zip_path)
    return shapefile.Reader(
        shp=io.BytesIO(z.read(base + ".shp")),
        shx=io.BytesIO(z.read(base + ".shx")),
        dbf=io.BytesIO(z.read(base + ".dbf")),
        encoding="utf-8",
    )


def limpa(txt):
    """Remove espaços extras; vazio vira None."""
    if txt is None:
        return None
    txt = re.sub(r"\s+", " ", str(txt)).strip()
    return txt or None


PARTICULAS = {"da", "de", "do", "das", "dos", "e", "em", "na", "no", "nas", "nos", "a", "o"}
SIGLAS = {"rppn", "apa", "mg", "br", "ii", "iii", "iv", "vi"}


def titulo(txt):
    """CAIXA ALTA -> Título (mantém partículas em minúsculas e siglas em maiúsculas)."""
    if txt is None:
        return None
    saida = []
    for i, p in enumerate(txt.lower().split(" ")):
        if i > 0 and p in PARTICULAS:
            saida.append(p)
        elif p in SIGLAS:
            saida.append(p.upper())
        else:
            saida.append(p[:1].upper() + p[1:])
    return " ".join(saida)


def sem_acento(txt):
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn")


def garante_valida(geom, tipo):
    """Valida (ST_MakeValid equivalente), remove vazias e converte para MULTI*."""
    if not geom.is_valid:
        geom = make_valid(geom)
    # make_valid pode devolver GeometryCollection: mantém só a parte do tipo esperado
    if geom.geom_type == "GeometryCollection":
        partes = [g for g in geom.geoms if g.geom_type.startswith(tipo)]
        geom = MultiPolygon(partes) if tipo == "Polygon" else MultiLineString(partes)
    if geom.geom_type == tipo:
        geom = (MultiPolygon if tipo == "Polygon" else MultiLineString)([geom])
    if geom.is_empty or not geom.is_valid:
        return None
    return geom


def ewkb(geom):
    return wkb.dumps(geom, hex=True, srid=SRID)


def escreve_csv(caminho, colunas, linhas):
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(colunas)
        w.writerows(linhas)


# --------------------------------------------------------------------------- UCs
CATEGORIAS_FEDERAL = {
    "Reserva Particular do Patrimônio Natural": "RPPN",
    "Parque": "PAR",
    "Área de Proteção Ambiental": "APA",
    "Floresta": "FLO",
    "Reserva de Desenvolvimento Sustentável": "RDS",
    "Reserva Biológica": "REBIO",
    "Estação Ecológica": "ESEC",
}
CATEGORIAS_ESTADUAL = {"FLOE": "FLO"}  # demais siglas já coincidem com o domínio


def biomas_federal(rec):
    nomes = [("amazonia", "Amazonia"), ("caatinga", "Caatinga"), ("cerrado", "Cerrado"),
             ("matlantica", "Mata Atlantica"), ("pampa", "Pampa"), ("pantanal", "Pantanal")]
    achados = []
    for campo, nome in nomes:
        try:
            if float(rec[campo] or 0) > 0:
                achados.append(nome)
        except ValueError:
            pass
    return "/".join(sorted(achados)) or None


def municipios_estadual(txt):
    txt = limpa(txt)
    if not txt:
        return None
    return "; ".join(m.strip() for m in txt.split("/") if m.strip())


def municipios_federal(txt):
    """'AIURUOCA (MG), ALAGOA (MG), ...' -> 'Aiuruoca; Alagoa; ...' (somente os de MG)."""
    txt = limpa(txt)
    if not txt:
        return None
    mg = []
    for item in txt.split(","):
        m = re.match(r"^\s*(.+?)\s*\(MG\)\s*$", item)
        if m:
            mg.append(titulo(m.group(1)))
    return "; ".join(mg) or None


def trata_ucs():
    log("== Unidades de conservação ==")
    linhas, contagem = [], Counter()
    id_uc = 0
    fontes = [
        ("ESTADUAL", "ide_2010_mg_unidades_conservacao_estaduais_pol"),
        ("FEDERAL", "ide_2010_mg_unidades_conservacao_federais_pol"),
    ]
    for esfera, base in fontes:
        r = abrir_shp(BRUTOS / (base + ".zip"), base)
        campos = [f[0] for f in r.fields[1:]]
        for sr in r.iterShapeRecords():
            rec = dict(zip(campos, sr.record))
            geom = garante_valida(shape(sr.shape.__geo_interface__), "Polygon")
            if geom is None:
                contagem["descartada_geom"] += 1
                continue
            if not shape(sr.shape.__geo_interface__).is_valid:
                contagem["corrigida_make_valid"] += 1
            id_uc += 1
            if esfera == "ESTADUAL":
                cat = CATEGORIAS_ESTADUAL.get(limpa(rec["categoria"]), limpa(rec["categoria"]))
                nome = limpa(rec["nome_uc"])
                ato = limpa(rec["ato_legal"])
                bioma = limpa(rec["bioma"])
                munic = municipios_estadual(rec["municipios"])
                area_of, cnuc = None, None  # area_ofic da fonte tem unidades inconsistentes
                id_origem = int(rec["id"])
            else:
                cat = CATEGORIAS_FEDERAL[limpa(rec["categoria"])]
                nome = titulo(limpa(rec["nome_uc"]))
                ato = limpa(rec["cria_ato"])
                bioma = biomas_federal(rec)
                munic = municipios_federal(rec["municipio"])
                area_of = round(float(limpa(rec["ha_total"]).replace(",", ".")), 2) if limpa(rec["ha_total"]) else None
                cnuc = limpa(rec["cd_cnuc"])
                id_origem = int(rec["id"])
            contagem[esfera] += 1
            linhas.append([id_uc, nome, cat, esfera, id_origem, cnuc, ato, bioma, munic,
                           area_of, ewkb(geom)])
    # cd_cnuc deve ser único: se repetir, mantém só na primeira ocorrência
    vistos = set()
    for l in linhas:
        if l[5] in vistos:
            log(f"  cd_cnuc repetido ({l[5]}) -> anulado em id_uc={l[0]}")
            l[5] = None
        elif l[5]:
            vistos.add(l[5])
    escreve_csv(
        TRATADOS / "unidade_conservacao.csv",
        ["id_uc", "nome", "cod_categoria", "esfera", "id_origem", "cd_cnuc", "ato_legal",
         "bioma", "municipios", "area_oficial_ha", "geom"],
        linhas,
    )
    log(f"  linhas gravadas: {len(linhas)}  {dict(contagem)}")


# --------------------------------------------------------------------------- Rodovias
def trata_rodovias():
    log("== Rodovias ==")
    base = "ide_0401_mg_rodovias_lin"
    r = abrir_shp(BRUTOS / (base + ".zip"), base)
    campos = [f[0] for f in r.fields[1:]]
    contagem = Counter()
    linhas = []
    for sr in r.iterShapeRecords():
        rec = dict(zip(campos, sr.record))
        contagem["lidas"] += 1
        if not limpa(rec["codigo_rod"]):  # trechos sem nenhum atributo descritivo
            contagem["descartada_sem_atributos"] += 1
            continue
        original = shape(sr.shape.__geo_interface__)
        geom = garante_valida(original, "LineString")
        if geom is None:
            contagem["descartada_geom"] += 1
            continue
        if not original.is_valid:
            contagem["corrigida_make_valid"] += 1
        iso = lambda d: d.isoformat() if isinstance(d, date) else None
        linhas.append([
            int(rec["id"]),
            int(rec["id_cide"]) if rec["id_cide"] is not None else "",
            limpa(rec["codigo_rod"]),
            limpa(rec["codigo_snv"]),
            limpa(rec["tipo_trech"]),
            limpa(rec["unidade_fe"]),
            limpa(rec["local_inic"]),
            limpa(rec["local_fim"]),
            round(float(rec["quilometra"]), 3),
            round(float(rec["quilometr0"]), 3),
            round(float(rec["extensao"]), 3),
            limpa(rec["superficie"]),
            (limpa(rec["jurisdicao"]) or "").upper(),
            iso(rec["dt_ini"]),
            iso(rec["dt_fim"]),
            limpa(rec["referencia"]),
            ewkb(geom),
        ])
    colunas = ["id_trecho", "id_cide", "codigo_rod", "codigo_snv", "tipo_trecho", "uf",
               "local_inicio", "local_fim", "km_inicio", "km_fim", "extensao_km",
               "cod_superficie", "jurisdicao", "dt_inicio_vigencia", "dt_fim_vigencia",
               "referencia", "geom"]
    # divide em partes < LIMITE_BYTES_PARTE
    for antigo in TRATADOS.glob("rodovia_*.csv"):
        antigo.unlink()
    parte, tamanho, f, w = 0, 0, None, None
    for l in linhas:
        tam = sum(len(str(x)) + 1 for x in l)
        if f is None or tamanho + tam > LIMITE_BYTES_PARTE:
            if f:
                f.close()
            parte += 1
            f = open(TRATADOS / f"rodovia_{parte:02d}.csv", "w", newline="", encoding="utf-8")
            w = csv.writer(f, lineterminator="\n")
            w.writerow(colunas)
            tamanho = 0
        w.writerow(l)
        tamanho += tam
    f.close()
    log(f"  linhas gravadas: {len(linhas)} em {parte} arquivo(s)  {dict(contagem)}")


# --------------------------------------------------------------------------- GBIF
BASES_PERMITIDAS = {"HUMAN_OBSERVATION", "PRESERVED_SPECIMEN", "MATERIAL_SAMPLE",
                    "MATERIAL_CITATION", "MACHINE_OBSERVATION"}  # exclui FOSSIL_SPECIMEN


def trata_gbif():
    log("== Ocorrências de mamíferos (GBIF) ==")
    z = zipfile.ZipFile(BRUTOS / "0012809-261118162104854.zip")
    nome_csv = z.namelist()[0]
    texto = io.TextIOWrapper(z.open(nome_csv), encoding="utf-8", newline="")
    leitor = csv.DictReader(texto, delimiter="\t", quoting=csv.QUOTE_NONE)
    contagem = Counter()
    taxons = OrderedDict()
    linhas = []
    vistos = set()
    for rec in leitor:
        contagem["lidas"] += 1
        gid = int(rec["gbifID"])
        if gid in vistos:
            contagem["descartada_duplicada"] += 1
            continue
        vistos.add(gid)
        lat, lon = float(rec["decimalLatitude"]), float(rec["decimalLongitude"])
        if not (MG_LON[0] <= lon <= MG_LON[1] and MG_LAT[0] <= lat <= MG_LAT[1]):
            contagem["descartada_fora_de_mg"] += 1
            continue
        incerteza = rec["coordinateUncertaintyInMeters"]
        if incerteza and float(incerteza) > INCERTEZA_MAX_M:
            contagem["descartada_incerteza_alta"] += 1
            continue
        if rec["basisOfRecord"] not in BASES_PERMITIDAS:
            contagem["descartada_fossil"] += 1
            continue
        tk = rec["taxonKey"]
        if tk not in taxons:
            taxons[tk] = [tk, rec["taxonRank"], limpa(rec["scientificName"]),
                          limpa(rec["species"]), limpa(rec["genus"]), limpa(rec["family"]),
                          limpa(rec["order"])]
        # data completa (AAAA-MM-DD) quando disponível
        ev = rec["eventDate"][:10]
        data_evento = ev if re.fullmatch(r"\d{4}-\d{2}-\d{2}", ev) else ""
        linhas.append([
            gid, tk, rec["datasetKey"], limpa(rec["institutionCode"]),
            limpa(rec["collectionCode"]), rec["basisOfRecord"], data_evento,
            int(rec["year"]) if rec["year"] else "",
            int(float(rec["individualCount"])) if rec["individualCount"] else "",
            float(incerteza) if incerteza else "",
            limpa(rec["locality"]), rec["license"], limpa(rec["occurrenceID"]),
            f"SRID={SRID};POINT({lon:.6f} {lat:.6f})",
        ])
        contagem["gravadas"] += 1
    escreve_csv(
        TRATADOS / "ocorrencia_mamifero.csv",
        ["gbif_id", "taxon_key", "dataset_key", "instituicao", "colecao", "tipo_registro",
         "data_evento", "ano", "n_individuos", "incerteza_m", "localidade", "licenca",
         "ocorrencia_ref", "geom"],
        linhas,
    )
    escreve_csv(
        TRATADOS / "taxon.csv",
        ["taxon_key", "nivel_taxonomico", "nome_cientifico", "especie", "genero", "familia", "ordem"],
        taxons.values(),
    )
    log(f"  ocorrências: {len(linhas)}  taxa distintos: {len(taxons)}  {dict(contagem)}")


if __name__ == "__main__":
    TRATADOS.mkdir(parents=True, exist_ok=True)
    trata_ucs()
    trata_rodovias()
    trata_gbif()
    (RAIZ / "scripts" / "relatorio_tratamento.txt").write_text("\n".join(relatorio) + "\n",
                                                                encoding="utf-8")
