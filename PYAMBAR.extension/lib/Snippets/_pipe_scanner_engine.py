# -*- coding: utf-8 -*-
"""Engine puro do PipeDoctor — deteccao de erros de modelagem PLB.

PURO: sem clr/Autodesk/pyrevit. Recebe tuplas/dicts de floats (pes, unidade
interna do Revit) e devolve achados estruturados. Testado em CPython
(dev-tools/tests/test_pipe_scanner_engine.py); roda identico em IronPython 3.

Estruturas de entrada (montadas pelo script.py do PipeDoctor):
  elemento pipe:    {'id': int, 'cat': 'pipe', 'type_id': int,
                     'p0': (x,y,z), 'p1': (x,y,z), 'radius': float}
  elemento pontual: {'id': int, 'cat': 'fitting'|'accessory'|'fixture',
                     'type_id': int, 'origin': (x,y,z)}
  conector:         {'cid': int, 'elem_id': int, 'origin': (x,y,z),
                     'direction': (x,y,z), 'connected': bool,
                     'other_id': int ou None}

Achado (saida — 'valor' ja em unidade de exibicao):
  {'check': str, 'ids': [int, ...], 'valor': float ou None,
   'unidade': 'mm'|'graus'|None, 'detalhe': str, 'severidade': str}
"""
import math

# Regra de desvio contra o alvo da bitola - compartilhada com o corretor
# (Snippets/_trecho_slope_utils) para relatorio e correcao nao discordarem.
from Snippets._slope_geometry import (
    DESVIO_ABAIXO, DESVIO_OK, classificar_desvio)

MM_POR_PE = 304.8
CELULA_GRID = 0.5  # pes (~15 cm)

SEVERIDADE = {
    'falso_conectado': 'critico',
    'duplicado': 'critico',
    'sobreposto': 'critico',
    'inclinacao': 'critico',
    'encaixado': 'alto',
    'conexao_com_desvio': 'alto',
    'fora_de_prumo': 'medio',
    'open_end': 'info',
}

CHECK_ORDER = ['falso_conectado', 'duplicado', 'sobreposto', 'inclinacao',
               'encaixado', 'conexao_com_desvio', 'fora_de_prumo', 'open_end']

DEFAULT_CONFIG_MM = {
    'tol_falso_conectado_mm': 5.0,
    'tol_duplicado_mm': 5.0,
    'tol_encaixado_mm': 10.0,
    'tol_gap_conexao_mm': 1.0,
    'overlap_minimo_mm': 1.0,
    'tol_angulo_conexao_graus': 0.5,
    'angulo_quase_vertical_graus': 10.0,
    'tol_prumo_graus': 0.3,
    # --- inclinacao por bitola (drenagem) ---
    'inclinacao_bitola_limite_mm': 50.8,          # 2" - ate aqui vale o alvo "pequena"
    'inclinacao_alvo_pequena_pol_pe': 0.25,       # 1/4"/ft
    'inclinacao_alvo_grande_pol_pe': 0.125,       # 1/8"/ft
    'inclinacao_tolerancia_pct': 10.0,
    'min_trecho_mm': 76.2,                        # 3" - trecho menor nao e cobrado
}


def config_interna(cfg_mm):
    """Mescla defaults + overrides e converte *_mm para pes (chave sem sufixo)."""
    cfg = dict(DEFAULT_CONFIG_MM)
    cfg.update(cfg_mm or {})
    interna = {}
    for chave, valor in cfg.items():
        if chave.endswith('_mm'):
            interna[chave[:-3]] = valor / MM_POR_PE
        else:
            interna[chave] = valor
    return interna


def alvo_para_raio(radius_ft, cfg_mm=None):
    """Inclinacao alvo (razao dz/dxy) para um raio de tubo em pes.

    Regra de drenagem por gravidade: bitola pequena escoa com mais caimento.
    O limite e por DIAMETRO (`inclinacao_bitola_limite_mm`, default 50.8 = 2");
    aqui comparamos o raio, entao o limite e dividido por 2.

    FONTE UNICA da regra — `_trecho_slope_utils.alvo_para_bitola` (que recebe um
    trecho) e `_aranha_rules.regras_para` (que so tem a bitola) ambos delegam
    para ca, para nao divergirem com o tempo.
    """
    cfg = config_interna(cfg_mm)
    limite_raio = cfg['inclinacao_bitola_limite'] / 2.0
    if radius_ft <= limite_raio + 1e-6:
        return cfg['inclinacao_alvo_pequena_pol_pe'] / 12.0
    return cfg['inclinacao_alvo_grande_pol_pe'] / 12.0


# ---------------------------------------------------------------- vetores

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norma(v):
    return math.sqrt(_dot(v, v))


def _dist(a, b):
    return _norma(_sub(a, b))


def _normalizar(v):
    n = _norma(v)
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def _angulo_graus(a, b):
    d = _dot(_normalizar(a), _normalizar(b))
    d = max(-1.0, min(1.0, d))
    return math.degrees(math.acos(d))


# ---------------------------------------------------------------- grid

class SpatialGrid(object):
    """Hash espacial 3D: consulta de vizinhos em 27 celulas (3x3x3)."""

    def __init__(self, cell_size):
        self.cell = float(cell_size)
        self.buckets = {}

    def _key(self, pt):
        return (int(math.floor(pt[0] / self.cell)),
                int(math.floor(pt[1] / self.cell)),
                int(math.floor(pt[2] / self.cell)))

    def insert(self, pt, item):
        self.buckets.setdefault(self._key(pt), []).append((pt, item))

    def neighbors(self, pt):
        kx, ky, kz = self._key(pt)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for entry in self.buckets.get((kx + dx, ky + dy, kz + dz), ()):
                        yield entry


def _achado(check, ids, valor, unidade, detalhe, severidade=None):
    return {'check': check, 'ids': list(ids), 'valor': valor,
            'unidade': unidade, 'detalhe': detalhe,
            'severidade': severidade or SEVERIDADE[check]}


# ---------------------------------------------------------------- checks: pipes

def check_fora_de_prumo(pipes, cfg):
    """Check 6: pipe quase-vertical com desvio do prumo perfeito."""
    achados = []
    for p in pipes:
        d = _normalizar(_sub(p['p1'], p['p0']))
        ang_z = _angulo_graus(d, (0.0, 0.0, 1.0))
        desvio = min(ang_z, 180.0 - ang_z)
        if cfg['tol_prumo_graus'] < desvio < cfg['angulo_quase_vertical_graus']:
            achados.append(_achado('fora_de_prumo', [p['id']], desvio, 'graus',
                                   'desvio do prumo'))
    return achados


def _direcao_canonica(v, casas=3):
    """Direcao normalizada com sinal canonico (unifica antiparalelos)."""
    d = _normalizar(v)
    for c in d:
        if abs(c) > 1e-9:
            if c < 0:
                d = (-d[0], -d[1], -d[2])
            break
    return (round(d[0], casas), round(d[1], casas), round(d[2], casas))


def check_sobrepostos(pipes, cfg):
    """Check 3: pares de pipes colineares com trechos sobrepostos.

    Agrupa por direcao quantizada; dentro do grupo compara pares (grupos de
    mesma direcao sao pequenos o suficiente para O(k2) em python puro).
    """
    grupos = {}
    for p in pipes:
        v = _sub(p['p1'], p['p0'])
        if _norma(v) < 1e-9:
            continue
        grupos.setdefault(_direcao_canonica(v), []).append(p)
    achados = []
    for grupo in grupos.values():
        for i in range(len(grupo)):
            for j in range(i + 1, len(grupo)):
                a, b = grupo[i], grupo[j]
                d = _normalizar(_sub(a['p1'], a['p0']))
                w = _sub(b['p0'], a['p0'])
                t = _dot(w, d)
                perp = _sub(w, (d[0] * t, d[1] * t, d[2] * t))
                if _norma(perp) >= min(a['radius'], b['radius']):
                    continue
                ta1 = _dot(_sub(a['p1'], a['p0']), d)
                tb1 = t + _dot(_sub(b['p1'], b['p0']), d)
                lo = max(min(0.0, ta1), min(t, tb1))
                hi = min(max(0.0, ta1), max(t, tb1))
                overlap = hi - lo
                if overlap > cfg['overlap_minimo']:
                    achados.append(_achado(
                        'sobreposto', [a['id'], b['id']],
                        overlap * MM_POR_PE, 'mm',
                        'trecho sobreposto no mesmo eixo'))
    return achados


# ---------------------------------------------------------------- checks: duplicidade

def _ponto_chave(elem):
    if elem['cat'] == 'pipe':
        p0, p1 = elem['p0'], elem['p1']
        return ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0, (p0[2] + p1[2]) / 2.0)
    return elem['origin']


def _eh_duplicado(a, b, tol):
    if a['cat'] == 'pipe':
        direto = _dist(a['p0'], b['p0']) < tol and _dist(a['p1'], b['p1']) < tol
        invertido = _dist(a['p0'], b['p1']) < tol and _dist(a['p1'], b['p0']) < tol
        return direto or invertido
    return _dist(a['origin'], b['origin']) < tol


def check_duplicados(elementos, cfg):
    """Check 2: mesmo tipo + mesma posicao. Retorna (achados, pares_flagrados)."""
    tol = cfg['tol_duplicado']
    grid = SpatialGrid(CELULA_GRID)
    achados = []
    pares = set()
    for e in elementos:
        pt = _ponto_chave(e)
        for _, outro in grid.neighbors(pt):
            if outro['type_id'] != e['type_id'] or outro['cat'] != e['cat']:
                continue
            if _eh_duplicado(e, outro, tol):
                par = tuple(sorted((e['id'], outro['id'])))
                if par not in pares:
                    pares.add(par)
                    achados.append(_achado('duplicado', list(par), None, None,
                                           'mesmo tipo na mesma posicao'))
        grid.insert(pt, e)
    return achados, pares


def pares_conectados(conectores):
    """Set de pares (id_a, id_b) com conexao logica entre si."""
    pares = set()
    for c in conectores:
        if c['connected'] and c['other_id'] is not None:
            pares.add(tuple(sorted((c['elem_id'], c['other_id']))))
    return pares


def check_encaixados(fittings, pares_con, pares_excluidos, cfg):
    """Check 4: fittings com origens proximas SEM conexao logica entre si."""
    tol = cfg['tol_encaixado']
    grid = SpatialGrid(CELULA_GRID)
    achados = []
    vistos = set()
    for f in fittings:
        for _, outro in grid.neighbors(f['origin']):
            if _dist(f['origin'], outro['origin']) >= tol:
                continue
            par = tuple(sorted((f['id'], outro['id'])))
            if par in vistos or par in pares_con or par in pares_excluidos:
                continue
            vistos.add(par)
            achados.append(_achado(
                'encaixado', list(par),
                _dist(f['origin'], outro['origin']) * MM_POR_PE, 'mm',
                'fittings sobrepostos sem conexao entre si'))
        grid.insert(f['origin'], f)
    return achados


# ---------------------------------------------------------------- checks: conectores

def check_falso_conectado(conectores, cfg):
    """Check 1: conectores abertos de elementos diferentes praticamente
    coincidentes, sem conexao logica. Retorna (achados, cids_flagrados)."""
    tol = cfg['tol_falso_conectado']
    grid = SpatialGrid(CELULA_GRID)
    achados = []
    cids = set()
    for c in conectores:
        if c['connected']:
            continue
        for _, outro in grid.neighbors(c['origin']):
            if outro['elem_id'] == c['elem_id']:
                continue
            gap = _dist(c['origin'], outro['origin'])
            if gap < tol:
                achados.append(_achado(
                    'falso_conectado', [c['elem_id'], outro['elem_id']],
                    gap * MM_POR_PE, 'mm',
                    'conectores abertos coincidentes sem conexao'))
                cids.add(c['cid'])
                cids.add(outro['cid'])
        grid.insert(c['origin'], c)
    return achados, cids


def check_conexao_com_desvio(conectores, cfg):
    """Check 5: pares conectados com gap entre origens ou eixos fora de 180."""
    por_par = {}
    for c in conectores:
        if not c['connected'] or c['other_id'] is None:
            continue
        par = tuple(sorted((c['elem_id'], c['other_id'])))
        por_par.setdefault(par, []).append(c)
    achados = []
    for par, lista in por_par.items():
        lado_a = [c for c in lista if c['elem_id'] == par[0]]
        lado_b = [c for c in lista if c['elem_id'] == par[1]]
        if not lado_a or not lado_b:
            continue
        melhor = None
        for ca in lado_a:
            for cb in lado_b:
                gap = _dist(ca['origin'], cb['origin'])
                if melhor is None or gap < melhor[0]:
                    melhor = (gap, ca, cb)
        gap, ca, cb = melhor
        if gap > cfg['tol_gap_conexao']:
            achados.append(_achado('conexao_com_desvio', list(par),
                                   gap * MM_POR_PE, 'mm',
                                   'gap entre conectores conectados'))
            continue
        ang = _angulo_graus(ca['direction'], cb['direction'])
        desvio = abs(180.0 - ang)
        if desvio > cfg['tol_angulo_conexao_graus']:
            achados.append(_achado('conexao_com_desvio', list(par),
                                   desvio, 'graus',
                                   'eixos desalinhados na conexao'))
    return achados


def check_open_ends(conectores, cids_excluidos):
    """Check 7: conectores abertos (informativo)."""
    achados = []
    for c in conectores:
        if c['connected'] or c['cid'] in cids_excluidos:
            continue
        achados.append(_achado('open_end', [c['elem_id']], None, None,
                               'conector aberto'))
    return achados


# ------------------------------------------------- check: inclinacao por bitola
#
# A unidade de analise e o TRECHO, nao o tubo. Um toco de 4 cm entre dois
# fittings nao tem inclinacao propria - ele herda a do trecho. Medir tubo a
# tubo transforma folga de encaixe em falso positivo.

ORDEM_SEVERIDADE = {'critico': 0, 'alto': 1, 'medio': 2, 'info': 3}

# Quantos fittings seguidos atravessar antes de desistir de achar o proximo tubo.
MAX_NOS_SEGUIDOS = 4

# Produto escalar minimo (em modulo) para considerar que ha passagem reta num
# fitting de 3+ conectores. -0.9 ~ ate 25 graus fora da reta.
DOT_PASSAGEM_RETA = -0.9


def _horizontal(a, b):
    return math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)


def _extremidade(p, idx):
    return p['p0'] if idx == 0 else p['p1']


def _eh_vertical(p, cfg):
    d = _normalizar(_sub(p['p1'], p['p0']))
    ang = _angulo_graus(d, (0.0, 0.0, 1.0))
    return min(ang, 180.0 - ang) < cfg['angulo_quase_vertical_graus']


def _mapa_conectores(conectores):
    por_elem = {}
    for c in conectores:
        por_elem.setdefault(c['elem_id'], []).append(c)
    return por_elem


def _conector_na_ponta(p, idx, por_elem, tol):
    """Conector do tubo p mais proximo da extremidade idx."""
    alvo = _extremidade(p, idx)
    melhor = None
    for c in por_elem.get(p['id'], ()):
        d = _dist(c['origin'], alvo)
        if melhor is None or d < melhor[0]:
            melhor = (d, c)
    if melhor is None or melhor[0] > tol:
        return None
    return melhor[1]


def _saida_do_no(no_id, ponto_entrada, origem_id, por_elem):
    """Conector de saida de um fitting seguindo a passagem reta.

    Fitting de 2 conectores (joelho, luva, reducao): devolve o outro, qualquer
    que seja o angulo - um joelho de 90 nao encerra o trecho.
    Fitting de 3+ (te, wye): devolve o conector mais antiparalelo a entrada.
    Se nenhum estiver claramente na reta, devolve None e o trecho termina ali.
    """
    conns = por_elem.get(no_id, ())
    entrada = None
    for c in conns:
        if c.get('other_id') != origem_id:
            continue
        d = _dist(c['origin'], ponto_entrada)
        if entrada is None or d < entrada[0]:
            entrada = (d, c)
    if entrada is None:
        return None
    c_ent = entrada[1]

    candidatos = [c for c in conns
                  if c is not c_ent and c.get('connected') and c.get('other_id')]
    if not candidatos:
        return None
    if len(candidatos) == 1:
        return candidatos[0]

    dir_ent = _normalizar(c_ent['direction'])
    melhor = None
    for c in candidatos:
        d = _dot(_normalizar(c['direction']), dir_ent)
        if melhor is None or d < melhor[0]:
            melhor = (d, c)
    if melhor[0] > DOT_PASSAGEM_RETA:
        return None
    return melhor[1]


def _mesma_bitola(a, b):
    return abs(a['radius'] - b['radius']) < 1e-4


def _vizinho_no_trecho(p, idx, pipe_por_id, por_elem, tol):
    """Devolve (id_do_proximo_tubo, extremidade_de_entrada) ou None."""
    c = _conector_na_ponta(p, idx, por_elem, tol)
    if c is None or not c.get('connected') or not c.get('other_id'):
        return None

    prox_id = c['other_id']
    ponto = c['origin']
    origem = p['id']

    for _ in range(MAX_NOS_SEGUIDOS):
        if prox_id in pipe_por_id:
            outro = pipe_por_id[prox_id]
            if not _mesma_bitola(p, outro):
                return None          # muda bitola -> outro trecho, outra regra
            d0 = _dist(_extremidade(outro, 0), ponto)
            d1 = _dist(_extremidade(outro, 1), ponto)
            return (outro['id'], 0 if d0 <= d1 else 1)
        saida = _saida_do_no(prox_id, ponto, origem, por_elem)
        if saida is None:
            return None
        origem = prox_id
        prox_id = saida['other_id']
        ponto = saida['origin']
    return None


def montar_trechos(pipes, conectores, cfg):
    """Encadeia tubos horizontais em trechos.

    Devolve lista de dicts: {'ids': [...], 'pontos': [...], 'radius': float}.
    'pontos' e a polilinha na ordem do percurso, incluindo o salto sobre cada
    fitting - por isso o comprimento desenvolvido sai correto mesmo com curvas
    em planta.
    """
    tol = cfg.get('tol_falso_conectado', 5.0 / MM_POR_PE)
    horizontais = [p for p in pipes
                   if _horizontal(p['p0'], p['p1']) > 1e-9 and not _eh_vertical(p, cfg)]
    pipe_por_id = {}
    for p in horizontais:
        pipe_por_id[p['id']] = p
    por_elem = _mapa_conectores(conectores)

    viz = {}
    for p in horizontais:
        for idx in (0, 1):
            viz[(p['id'], idx)] = _vizinho_no_trecho(p, idx, pipe_por_id, por_elem, tol)

    trechos = []
    visitados = set()
    for semente in horizontais:
        if semente['id'] in visitados:
            continue

        # recuar ate a ponta do trecho (entrada = extremidade 0 da semente)
        atual = (semente['id'], 0)
        vistos_recuo = set([semente['id']])
        while True:
            anterior = viz.get(atual)
            if anterior is None or anterior[0] in vistos_recuo:
                break
            atual = (anterior[0], 1 - anterior[1])
            vistos_recuo.add(anterior[0])

        # avancar montando a cadeia
        cadeia = []
        ids = []
        while True:
            pid, entrada = atual
            if pid in ids:
                break
            cadeia.append(atual)
            ids.append(pid)
            proximo = viz.get((pid, 1 - entrada))
            if proximo is None:
                break
            atual = proximo

        visitados.update(ids)
        pontos = []
        for pid, entrada in cadeia:
            p = pipe_por_id[pid]
            pontos.append(_extremidade(p, entrada))
            pontos.append(_extremidade(p, 1 - entrada))
        trechos.append({'ids': ids, 'pontos': pontos,
                        'radius': pipe_por_id[ids[0]]['radius']})
    return trechos


def check_inclinacao(pipes, conectores, cfg):
    """Check 8: trecho de drenagem fora da inclinacao padrao da bitola.

    Alvo por bitola (config): ate 2" -> 1/4"/ft; acima -> 1/8"/ft.
    Abaixo do alvo e critico (nao escoa). Acima e apenas informativo - excesso
    em ramal curto e residuo de fitting rolado, nao decisao de projeto.
    """
    limite_raio = cfg['inclinacao_bitola_limite'] / 2.0
    alvo_pequena = cfg['inclinacao_alvo_pequena_pol_pe'] / 12.0
    alvo_grande = cfg['inclinacao_alvo_grande_pol_pe'] / 12.0
    tol_pct = cfg['inclinacao_tolerancia_pct']
    min_trecho = cfg['min_trecho']

    achados = []
    for trecho in montar_trechos(pipes, conectores, cfg):
        pontos = trecho['pontos']
        desenvolvido = 0.0
        for i in range(len(pontos) - 1):
            desenvolvido += _horizontal(pontos[i], pontos[i + 1])
        if desenvolvido < min_trecho:
            continue

        slope = abs(pontos[-1][2] - pontos[0][2]) / desenvolvido
        alvo = alvo_pequena if trecho['radius'] <= limite_raio + 1e-6 else alvo_grande
        if alvo <= 0:
            continue
        desvio_pct = (slope - alvo) / alvo * 100.0
        if classificar_desvio(slope, alvo, tol_pct) == DESVIO_OK:
            continue

        severidade = ('critico'
                      if classificar_desvio(slope, alvo, tol_pct) == DESVIO_ABAIXO
                      else 'info')
        achados.append(_achado(
            'inclinacao', trecho['ids'], slope * 12.0, 'pol_pe',
            'trecho de {:.0f}" a {:.3f}"/ft (alvo {:.3f}"/ft, {:+.0f}%)'.format(
                trecho['radius'] * 24.0, slope * 12.0, alvo * 12.0, desvio_pct),
            severidade))

    achados.sort(key=lambda a: (ORDEM_SEVERIDADE[a['severidade']], a['ids'][0]))
    return achados


# ---------------------------------------------------------------- orquestrador

def run_all_checks(elementos, conectores, cfg_mm=None):
    """Roda os 8 checks e devolve achados ordenados por severidade.

    elementos/conectores: ver docstring do modulo. cfg_mm: overrides em mm/graus.
    """
    cfg = config_interna(cfg_mm)
    pipes = [e for e in elementos if e['cat'] == 'pipe']
    fittings = [e for e in elementos if e['cat'] == 'fitting']

    achados_fc, cids_fc = check_falso_conectado(conectores, cfg)
    achados_dup, pares_dup = check_duplicados(elementos, cfg)
    pares_con = pares_conectados(conectores)

    achados = []
    achados.extend(achados_fc)
    achados.extend(achados_dup)
    achados.extend(check_sobrepostos(pipes, cfg))
    achados.extend(check_encaixados(fittings, pares_con, pares_dup, cfg))
    achados.extend(check_conexao_com_desvio(conectores, cfg))
    achados.extend(check_fora_de_prumo(pipes, cfg))
    achados.extend(check_inclinacao(pipes, conectores, cfg))
    achados.extend(check_open_ends(conectores, cids_fc))

    ordem = {}
    for i, nome in enumerate(CHECK_ORDER):
        ordem[nome] = i
    achados.sort(key=lambda a: ordem.get(a['check'], 99))
    return achados
