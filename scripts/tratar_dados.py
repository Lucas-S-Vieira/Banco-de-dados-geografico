#!/usr/bin/env python3
"""
Tratamento dos dados brutos (dados/brutos) -> dados prontos para importação (dados/tratados).

Usa somente a biblioteca padrão do Python (3.8+). Lê os shapefiles diretamente de dentro
dos .zip baixados da IDE-Sisema e o CSV do download do GBIF, e grava CSVs em UTF-8 com a
geometria em EWKT, prontos para \\copy (ver sql/dados.sql).

Uso (a partir da raiz do repositório):
    python3 scripts/tratar_dados.py
"""
import csv
import io
import os
import re
import struct
import sys
import unicodedata
import zipfile
from collections import Counter, OrderedDict

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRUTOS = os.path.join(RAIZ, 'dados', 'brutos')
TRATADOS = os.path.join(RAIZ, 'dados', 'tratados')

ZIP_RODOVIAS = 'ide_0401_mg_rodovias_lin.zip'
ZIP_UC_EST = 'ide_2010_mg_unidades_conservacao_estaduais_pol.zip'
ZIP_UC_FED = 'ide_2010_mg_unidades_conservacao_federais_pol.zip'
ZIP_GBIF = 'gbif_0012809-261118162104854.zip'

CASAS_DECIMAIS = 6          # ~0,1 m; muito abaixo da precisão posicional das fontes
INCERTEZA_MAX_M = 10000     # ocorrências com incerteza de coordenada maior que isso são descartadas
SRID = 4674

log_linhas = []


def log(msg):
    print(msg)
    log_linhas.append(msg)


# ----------------------------------------------------------------------------- texto

def limpar_texto(valor):
    """Normaliza texto: NFC, sem NUL, espaços colapsados; vazio -> None."""
    if valor is None:
        return None
    valor = unicodedata.normalize('NFC', valor.replace('\x00', ''))
    valor = re.sub(r'\s+', ' ', valor).strip()
    return valor or None


def decodificar(b, contador):
    """Os .cst declaram UTF-8, mas alguns campos têm bytes Latin-1; usa cp1252 como reserva."""
    try:
        return b.decode('utf-8')
    except UnicodeDecodeError:
        contador['campos_recodificados_cp1252'] += 1
        return b.decode('cp1252', errors='replace')


def sem_acento(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


# ----------------------------------------------------------------------------- DBF / SHP

def ler_dbf(dados, contador):
    n, hlen, rlen = struct.unpack('<IHH', dados[4:12])
    campos = []
    pos = 32
    while dados[pos] != 0x0D:
        d = dados[pos:pos + 32]
        nome = d[:11].split(b'\0')[0].decode('ascii')
        campos.append((nome, chr(d[11]), d[16]))
        pos += 32
    registros = []
    for i in range(n):
        r = dados[hlen + i * rlen: hlen + (i + 1) * rlen]
        p = 1
        reg = {}
        for nome, tipo, tam in campos:
            bruto = r[p:p + tam].replace(b'\x00', b'')
            p += tam
            texto = limpar_texto(decodificar(bruto, contador))
            if texto is not None and tipo in 'NF':
                if set(texto) == {'*'}:          # estouro de campo numérico no DBF
                    contador['numericos_estourados'] += 1
                    texto = None
            reg[nome] = texto
        registros.append(reg)
    return registros


def ler_shp(dados):
    """Retorna lista (uma por registro) de (tipo, partes); cada parte é lista de (x, y)."""
    geoms = []
    pos = 100
    while pos < len(dados):
        _, tam = struct.unpack('>ii', dados[pos:pos + 8])
        conteudo = dados[pos + 8: pos + 8 + tam * 2]
        pos += 8 + tam * 2
        tipo = struct.unpack('<i', conteudo[:4])[0]
        if tipo == 0:
            geoms.append((0, []))
            continue
        if tipo not in (3, 5, 13, 15, 23, 25):
            raise ValueError(f'tipo de geometria shapefile não suportado: {tipo}')
        nparts, npts = struct.unpack('<ii', conteudo[36:44])
        partes_idx = struct.unpack(f'<{nparts}i', conteudo[44:44 + 4 * nparts])
        base = 44 + 4 * nparts
        xy = struct.unpack(f'<{2 * npts}d', conteudo[base: base + 16 * npts])
        pts = list(zip(xy[0::2], xy[1::2]))
        limites = list(partes_idx) + [npts]
        partes = [pts[limites[k]:limites[k + 1]] for k in range(nparts)]
        geoms.append((tipo % 10, partes))
    return geoms


def ler_shapefile_zip(nome_zip, contador):
    with zipfile.ZipFile(os.path.join(BRUTOS, nome_zip)) as z:
        nomes = z.namelist()
        shp = next(n for n in nomes if n.lower().endswith('.shp'))
        dbf = next(n for n in nomes if n.lower().endswith('.dbf'))
        prj = next(n for n in nomes if n.lower().endswith('.prj'))
        wkt_prj = z.read(prj).decode('utf-8', 'replace')
        if 'SIRGAS 2000' not in wkt_prj or '4674' not in wkt_prj:
            raise ValueError(f'{nome_zip}: sistema de referência inesperado: {wkt_prj[:80]}')
        registros = ler_dbf(z.read(dbf), contador)
        geoms = ler_shp(z.read(shp))
    if len(registros) != len(geoms):
        raise ValueError(f'{nome_zip}: DBF e SHP com contagens diferentes')
    return list(zip(registros, geoms))


# ----------------------------------------------------------------------------- geometria -> EWKT

def fmt(v):
    s = f'{v:.{CASAS_DECIMAIS}f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def fmt_pts(pts):
    return ','.join(f'{fmt(x)} {fmt(y)}' for x, y in pts)


def area_assinada(anel):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(anel, anel[1:]):
        s += x1 * y2 - x2 * y1
    return s / 2.0


def ponto_no_anel(pt, anel):
    x, y = pt
    dentro = False
    for (x1, y1), (x2, y2) in zip(anel, anel[1:]):
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xi > x:
                dentro = not dentro
    return dentro


def multipolygon_ewkt(aneis):
    """Shapefile: anéis externos em sentido horário, buracos em anti-horário."""
    aneis = [a if a[0] == a[-1] else a + [a[0]] for a in aneis if len(a) >= 3]
    externos, buracos = [], []
    for a in aneis:
        (externos if area_assinada(a) <= 0 else buracos).append(a)
    if not externos:                       # orientação fora do padrão: trata tudo como externo
        externos, buracos = buracos, []
    poligonos = [[e] for e in externos]
    for b in buracos:
        candidatos = [i for i, e in enumerate(externos) if ponto_no_anel(b[0], e)]
        if candidatos:
            i = min(candidatos, key=lambda k: abs(area_assinada(externos[k])))
            poligonos[i].append(b)
        else:
            poligonos.append([b])
    corpo = ','.join('(' + ','.join('(' + fmt_pts(a) + ')' for a in p) + ')' for p in poligonos)
    return f'SRID={SRID};MULTIPOLYGON({corpo})'


def multilinestring_ewkt(partes):
    partes = [p for p in partes if len(p) >= 2]
    corpo = ','.join('(' + fmt_pts(p) + ')' for p in partes)
    return f'SRID={SRID};MULTILINESTRING({corpo})'


# ----------------------------------------------------------------------------- utilidades

def numero(v):
    if v is None:
        return None
    try:
        f = float(v.replace(',', '.'))
    except ValueError:
        return None
    return f'{f:.3f}'.rstrip('0').rstrip('.') if f != int(f) else str(int(f))


def gravar_csv(nome, colunas, linhas):
    caminho = os.path.join(TRATADOS, nome)
    with open(caminho, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(colunas)
        for linha in linhas:
            w.writerow(['' if linha.get(c) is None else linha[c] for c in colunas])
    tam = os.path.getsize(caminho) / 1e6
    log(f'  -> {nome}: {len(linhas)} registros, {tam:.1f} MB')


# ----------------------------------------------------------------------------- domínios

CATEGORIAS_UC = OrderedDict([
    # sigla: (nome, grupo)   -- Lei 9.985/2000 (SNUC)
    ('ESEC', ('Estação Ecológica', 'PROTECAO_INTEGRAL')),
    ('REBIO', ('Reserva Biológica', 'PROTECAO_INTEGRAL')),
    ('PAR', ('Parque', 'PROTECAO_INTEGRAL')),
    ('MONA', ('Monumento Natural', 'PROTECAO_INTEGRAL')),
    ('RVS', ('Refúgio de Vida Silvestre', 'PROTECAO_INTEGRAL')),
    ('APA', ('Área de Proteção Ambiental', 'USO_SUSTENTAVEL')),
    ('FLO', ('Floresta', 'USO_SUSTENTAVEL')),
    ('RDS', ('Reserva de Desenvolvimento Sustentável', 'USO_SUSTENTAVEL')),
    ('RPPN', ('Reserva Particular do Patrimônio Natural', 'USO_SUSTENTAVEL')),
])

MAPA_CATEGORIA_EST = {'PAR': 'PAR', 'APA': 'APA', 'MONA': 'MONA', 'ESEC': 'ESEC', 'RVS': 'RVS',
                      'FLOE': 'FLO', 'REBIO': 'REBIO', 'RDS': 'RDS'}
MAPA_CATEGORIA_FED = {'reserva particular do patrimonio natural': 'RPPN', 'parque': 'PAR',
                      'area de protecao ambiental': 'APA', 'floresta': 'FLO',
                      'reserva de desenvolvimento sustentavel': 'RDS', 'estacao ecologica': 'ESEC',
                      'reserva biologica': 'REBIO'}
MAPA_GRUPO = {'protecao integral': 'PROTECAO_INTEGRAL', 'uso sustentavel': 'USO_SUSTENTAVEL'}

SUPERFICIES = OrderedDict([
    # Siglas do Sistema Nacional de Viação (SNV/DNIT), usadas no SRE-MG
    ('DUP', 'Pista duplicada'),
    ('PAV', 'Pista simples pavimentada'),
    ('EOD', 'Em obras de duplicação'),
    ('EOP', 'Em obras de pavimentação'),
    ('IMP', 'Implantada (revestimento primário, sem pavimento)'),
    ('LEN', 'Leito natural'),
    ('PLA', 'Planejada'),
])

BIOMAS = {'caatinga': 'Caatinga', 'cerrado': 'Cerrado', 'mata atlantica': 'Mata Atlântica',
          'matlantica': 'Mata Atlântica'}


# ----------------------------------------------------------------------------- camadas

def tratar_uc():
    log('\n== Unidades de conservação (IDE-Sisema: estaduais + federais)')
    contador = Counter()
    linhas = []

    est = ler_shapefile_zip(ZIP_UC_EST, contador)
    log(f'  estaduais lidas: {len(est)}')
    for reg, (tipo, partes) in sorted(est, key=lambda t: float(t[0]['id'])):
        sigla = MAPA_CATEGORIA_EST[reg['categoria']]
        grupo = MAPA_GRUPO[sem_acento(reg['grupo']).lower()]
        assert grupo == CATEGORIAS_UC[sigla][1], (reg['nome_uc'], sigla, grupo)
        biomas = [BIOMAS[sem_acento(b).strip().lower()] for b in (reg['bioma'] or '').split('/') if b.strip()]
        municipios = ', '.join(m.strip() for m in reg['municipios'].split('/')) if reg['municipios'] else None
        linhas.append({
            'cod_origem': 'EST-' + str(int(float(reg['id']))),
            'nome': reg['nome_uc'],
            'esfera': 'ESTADUAL',
            'sigla_categoria': sigla,
            'ato_legal': reg['ato_legal'],
            'municipios': municipios,
            'bioma': '/'.join(dict.fromkeys(biomas)) or None,
            'geom': multipolygon_ewkt(partes),
        })

    fed = ler_shapefile_zip(ZIP_UC_FED, contador)
    log(f'  federais lidas: {len(fed)}')
    for reg, (tipo, partes) in sorted(fed, key=lambda t: int(t[0]['id'])):
        sigla = MAPA_CATEGORIA_FED[sem_acento(reg['categoria']).lower()]
        grupo = MAPA_GRUPO[sem_acento(reg['grupo']).lower()]
        assert grupo == CATEGORIAS_UC[sigla][1], (reg['nome_uc'], sigla, grupo)
        biomas = [BIOMAS[c] for c in ('caatinga', 'cerrado', 'matlantica')
                  if reg.get(c) and float(reg[c]) > 0]
        linhas.append({
            # código CNUC/MMA; UC recém-criada ainda sem CNUC usa 'FED-' + id da camada de origem
            'cod_origem': reg['cd_cnuc'] or 'FED-' + reg['id'],
            'nome': reg['nome_uc'],
            'esfera': 'FEDERAL',
            'sigla_categoria': sigla,
            'ato_legal': reg['cria_ato'],
            'municipios': reg['municipio'],
            'bioma': '/'.join(biomas) or None,
            'geom': multipolygon_ewkt(partes),
        })

    for i, l in enumerate(linhas, start=1):
        l['id_uc'] = i
    log(f'  campos de texto recodificados de cp1252: {contador["campos_recodificados_cp1252"]}')
    gravar_csv('categoria_uc.csv', ['sigla', 'nome', 'grupo'],
               [{'sigla': s, 'nome': n, 'grupo': g} for s, (n, g) in CATEGORIAS_UC.items()])
    gravar_csv('unidade_conservacao.csv',
               ['id_uc', 'cod_origem', 'nome', 'esfera', 'sigla_categoria', 'ato_legal',
                'municipios', 'bioma', 'geom'], linhas)


def tratar_rodovias():
    log('\n== Rodovias (IDE-Sisema / DER-MG, referência CIDE 2021)')
    contador = Counter()
    dados = ler_shapefile_zip(ZIP_RODOVIAS, contador)
    log(f'  trechos lidos: {len(dados)}')
    linhas, sem_atributos, descartados = [], 0, 0
    for reg, (tipo, partes) in sorted(dados, key=lambda t: int(t[0]['id'])):
        if not partes:
            descartados += 1
            continue
        if reg['jurisdicao'] is None and reg['codigo_rod'] is None:
            sem_atributos += 1
        sup = reg['superficie']
        if sup is not None and sup not in SUPERFICIES:
            raise ValueError(f'superfície desconhecida: {sup}')
        tipo_trecho = reg['tipo_trech']
        linhas.append({
            'id_trecho': int(reg['id']),
            'id_cide': int(reg['id_cide']),
            'numero_rodovia': reg['codigo_rod'],
            'codigo_snv': reg['codigo_snv'],
            'jurisdicao': reg['jurisdicao'].upper() if reg['jurisdicao'] else None,
            'tipo_trecho': sem_acento(tipo_trecho).upper().replace(' ', '_') if tipo_trecho else None,
            'sigla_superficie': sup,
            'local_inicio': reg['local_inic'],
            'local_fim': reg['local_fim'],
            'km_inicial': numero(reg['quilometra']),
            'km_final': numero(reg['quilometr0']),
            'extensao_km': numero(reg['extensao']),
            'geom': multilinestring_ewkt(partes),
        })
    log(f'  trechos com geometria nula descartados: {descartados}')
    log(f'  trechos sem nenhum atributo descritivo (mantidos, atributos NULL): {sem_atributos}')
    log(f'  campos numéricos estourados no DBF (-> NULL): {contador["numericos_estourados"]}')
    log(f'  campos de texto recodificados de cp1252: {contador["campos_recodificados_cp1252"]}')
    gravar_csv('tipo_superficie.csv', ['sigla', 'descricao'],
               [{'sigla': s, 'descricao': d} for s, d in SUPERFICIES.items()])
    # dividido em duas partes para ficar abaixo do limite de aviso do GitHub (50 MB por arquivo)
    colunas = ['id_trecho', 'id_cide', 'numero_rodovia', 'codigo_snv', 'jurisdicao', 'tipo_trecho',
               'sigla_superficie', 'local_inicio', 'local_fim', 'km_inicial', 'km_final',
               'extensao_km', 'geom']
    meio = len(linhas) // 2
    gravar_csv('rodovia_1.csv', colunas, linhas[:meio])
    gravar_csv('rodovia_2.csv', colunas, linhas[meio:])


NIVEIS = {'CLASS': 'CLASSE', 'ORDER': 'ORDEM', 'FAMILY': 'FAMILIA', 'GENUS': 'GENERO',
          'SPECIES': 'ESPECIE', 'SUBSPECIES': 'SUBESPECIE', 'UNRANKED': 'SEM_NIVEL'}
BASES = {'HUMAN_OBSERVATION': 'OBSERVACAO_HUMANA', 'PRESERVED_SPECIMEN': 'ESPECIME_PRESERVADO',
         'MATERIAL_SAMPLE': 'AMOSTRA_MATERIAL', 'MATERIAL_CITATION': 'CITACAO_MATERIAL',
         'MACHINE_OBSERVATION': 'OBSERVACAO_MAQUINA'}
LICENCAS = {'CC_BY_4_0': 'CC-BY-4.0', 'CC0_1_0': 'CC0-1.0'}


def tratar_gbif():
    log('\n== Ocorrências de mamíferos (GBIF)')
    with zipfile.ZipFile(os.path.join(BRUTOS, ZIP_GBIF)) as z:
        nome = next(n for n in z.namelist() if n.endswith('.csv'))
        texto = z.read(nome).decode('utf-8')
    leitor = csv.DictReader(io.StringIO(texto), delimiter='\t', quoting=csv.QUOTE_NONE)
    regs = [{k: limpar_texto(v) for k, v in r.items()} for r in leitor]
    log(f'  registros lidos: {len(regs)}')

    motivos = Counter()
    taxons = OrderedDict()
    conflitos_taxon = set()
    linhas = []
    vistos = set()
    for r in regs:
        if r['gbifID'] in vistos:
            motivos['gbifID duplicado'] += 1
            continue
        try:
            lat, lon = float(r['decimalLatitude']), float(r['decimalLongitude'])
        except (TypeError, ValueError):
            motivos['sem coordenadas'] += 1
            continue
        if not (-23.0 <= lat <= -14.0 and -51.5 <= lon <= -39.5):   # envelope de MG com folga
            motivos['coordenada fora do envelope de MG'] += 1
            continue
        if r['basisOfRecord'] == 'FOSSIL_SPECIMEN':
            motivos['registro fóssil'] += 1
            continue
        inc = float(r['coordinateUncertaintyInMeters']) if r['coordinateUncertaintyInMeters'] else None
        if inc is not None and inc > INCERTEZA_MAX_M:
            motivos[f'incerteza de coordenada > {INCERTEZA_MAX_M} m'] += 1
            continue
        if r['taxonRank'] not in NIVEIS:
            motivos['nível taxonômico não mapeado'] += 1
            continue

        chave = r['taxonKey']
        taxon = {
            'taxon_key': chave,
            'nome_cientifico': r['scientificName'],
            'nivel_taxonomico': NIVEIS[r['taxonRank']],
            'ordem': r['order'],
            'familia': r['family'],
            'genero': r['genus'],
            'especie': r['species'],
        }
        if chave in taxons and taxons[chave] != taxon:
            conflitos_taxon.add(chave)     # mesma chave com autoria/nível diferentes: mantém o 1º
        taxons.setdefault(chave, taxon)

        data = None
        if r['eventDate']:
            m = re.match(r'^(\d{4}-\d{2}-\d{2})', r['eventDate'])
            if m and '/' not in r['eventDate']:
                data = m.group(1)
        vistos.add(r['gbifID'])
        linhas.append({
            'id_ocorrencia': r['gbifID'],
            'taxon_key': chave,
            'data_evento': data,
            'ano': r['year'],
            'mes': r['month'],
            'base_registro': BASES[r['basisOfRecord']],
            'codigo_instituicao': r['institutionCode'],
            'num_individuos': r['individualCount'],
            'incerteza_coord_m': numero(r['coordinateUncertaintyInMeters']),
            'licenca': LICENCAS[r['license']],
            'id_dataset': r['datasetKey'],
            'geom': f'SRID=4326;POINT({fmt(lon)} {fmt(lat)})',
        })
    for motivo, n in motivos.most_common():
        log(f'  descartados ({motivo}): {n}')
    log(f'  ocorrências mantidas: {len(linhas)}')
    log(f'  táxons distintos: {len(taxons)}; taxonKey com atributos divergentes entre registros '
        f'(mantida a 1ª ocorrência): {len(conflitos_taxon)} {sorted(conflitos_taxon)}')
    gravar_csv('taxon.csv', ['taxon_key', 'nome_cientifico', 'nivel_taxonomico', 'ordem', 'familia',
                             'genero', 'especie'], list(taxons.values()))
    gravar_csv('ocorrencia.csv',
               ['id_ocorrencia', 'taxon_key', 'data_evento', 'ano', 'mes', 'base_registro',
                'codigo_instituicao', 'num_individuos', 'incerteza_coord_m', 'licenca', 'id_dataset',
                'geom'], linhas)


def main():
    os.makedirs(TRATADOS, exist_ok=True)
    log('Tratamento dos dados brutos -> dados/tratados')
    tratar_uc()
    tratar_rodovias()
    tratar_gbif()
    with open(os.path.join(TRATADOS, 'log_tratamento.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_linhas) + '\n')


if __name__ == '__main__':
    sys.exit(main())
