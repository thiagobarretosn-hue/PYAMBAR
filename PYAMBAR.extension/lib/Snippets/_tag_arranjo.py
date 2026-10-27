# -*- coding: utf-8 -*-
"""Arranjo de tags com chamada ortogonal — a parte que nao precisa do Revit.

Logica pura (sem clr, sem Autodesk). O script le a vista, mede a caixa REAL de
cada tag (bbox com o leader desligado, ver memoria api-tags) e passa dicts.
Tudo em coordenadas de TELA da vista (u = RightDirection, v = UpDirection), em pes.

REGRAS (de onde vem cada uma)
-----------------------------
- Chamada **po** — perna perpendicular + ombro horizontal, 1 dobra a 90 graus.
  No estudo de legibilidade de Barth et al. (2015) foi a lida mais rapido. Quando
  a tag fica na altura do elemento a chamada e reta (0 dobras), melhor ainda.
- O Revit liga o ombro na LATERAL da tag, na altura do TagHeadPosition (medido
  06/10/2026). Por isso a cabeca fica sempre deslocada na horizontal mais que meia
  largura + ombro minimo: o ombro nunca entra no texto.
- Chamadas nao se cruzam; tag nao fica sobre tag, sobre outro elemento nem sobre
  o desenho; anotacao alinhada (colunas/linhas) — manuais de desenho e o que o
  BIMLOGiQ declara medir (retangulo x retangulo e linha x retangulo).
- Unir duas tags numa so (varias chamadas) SO quando o texto e 100% igual
  (decisao do Thiago, 06/10/2026). Empilhar e livre.

MODELO
------
item   = {'id', 'ax', 'ay', 'w', 'h', 'ox', 'oy', 'texto', 'grupo'}
         (ax, ay) ponta da chamada; w x h caixa do texto; (ox, oy) centro da
         caixa MENOS a cabeca (familia alinhada a esquerda tem ox != 0).
rotulo = um ou mais itens de texto igual que viram UMA tag.
"""
import math
import random
import struct

#: versao do MOTOR, lida pelo relatorio do botao. O script.py e relido a cada
#: clique, mas este modulo pode ficar na memoria do pyRevit depois de trocar
#: de branch: o relatorio mostra as duas e acusa a diferenca (teste A/B).
VERSAO_MOTOR = '0.30'

#: ordem das contagens guardadas no cache da parte fixa (tupla, nao dict)
_CONTA_FIXA = ('tag', 'simbolo', 'linha', 'chamada_tag', 'cruza_tubo')

#: Pesos do custo. Os "duros" (sobreposicao, cruzamento) ficam ordens de grandeza
#: acima dos "esteticos" (comprimento, dobra, alinhamento) de proposito.
PESOS = {
    'tag': 1000.0,          # tag sobre tag (por ocorrencia, + proporcional a area)
    'simbolo': 400.0,       # tag sobre o simbolo de outro elemento etiquetavel
    # Calibrado em 08/10/2026 contra a vista ajustada a mao pelo Thiago (CIQ
    # nivel 2): o arranjo dele aceita texto sobre o fundo para ficar perto e
    # evita tubo/conduite. Com estes pesos o motor passa a preferir o arranjo
    # dele (estetica 0,89 x) e o resultado fica no perfil dele: 3 textos sobre
    # MEP (dele 3), cabeca-elemento mediana 10,1 mm (dele 9,9), 2 conflitos.
    'linha': 60.0,          # tag sobre tubo/conduite (linha com largura)
    'linha_fundo': 5.0,     # tag sobre o fundo (DWG da arquitetura, sem largura)
    'cruza': 300.0,         # chamada cruzando chamada
    'chamada_tag': 300.0,   # chamada atravessando a caixa de outra tag
    'chamada_simb': 60.0,   # chamada passando por cima de outro simbolo
    'fora': 1e6,            # fora do recorte da vista
    'comp': 8.0,            # comprimento da chamada / alcance (4 -> 8 em 08/10/2026)
    'dobra': 1.5,           # chamada com dobra a 90 graus (vs reta)
    'dobra45': 0.6,         # dobra a 45 graus: preferida (Thiago, 06/10/2026)
    'dobra60': 0.9,         # 60 graus: quando 45 nao cabe e 90 obrigaria a afastar
    'dobra30': 1.0,         # 30 graus: perna deitada, so quando o resto nao cabe
    'uniao_longa': 2.0,     # tag unida so fica se custar menos que separada x este fator
                            # (1,4 -> 2,0: o Thiago reuniu os stubs que o motor soltava)
    'alinha': 3.0,          # bonus: borda alinhada com tag vizinha (cai com o comprimento)
    'comp_longo': 60.0,     # chamada alem de 60% do alcance pesa ao QUADRADO (20 -> 60)
    'lado_errado': 40.0,    # margem: tag fora do lado do sistema (quente esq, fria dir)
    'dentro': 1000.0,       # margem: texto dentro do desenho
    'perna_margem': 0.0,           # margem: custo por passo de perna (o script liga)
    'chamada_sobre_linha': 0.0,    # chamada correndo sobre linha, por passo (margem liga: 30;
                                   # no CIQ nao ajudou e custou 60% de tempo)
    'chamada_cruza_tubo': 0.0,     # margem: chamada atravessando outro tubo, por cruzamento (o script liga)
    'contra_livre': 5.0,    # stub: texto do lado do conduite que chega (o Thiago poe
                            # do lado livre em 68% dos casos; 5 -> 74%, 15 -> 83%)
    'desliza': 3.0,         # ponto deslizante: afastar-se da posicao ideal (por alcance)
}

EPS = 1e-9


# ---------------------------------------------------------------- geometria

def _sobrepoe(a, b):
    """Caixas (x0, y0, x1, y1) se sobrepoem (borda encostada nao conta)."""
    return a[0] < b[2] - EPS and b[0] < a[2] - EPS and a[1] < b[3] - EPS and b[1] < a[3] - EPS


def _area_sobreposta(a, b):
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    if dx <= 0 or dy <= 0:
        return 0.0
    return dx * dy


def _orient(ax, ay, bx, by, cx, cy):
    v = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    if v > EPS:
        return 1
    if v < -EPS:
        return -1
    return 0


def segmentos_cruzam(s, t):
    """Cruzamento proprio de dois segmentos (encostar na ponta nao conta)."""
    o1 = _orient(s[0], s[1], s[2], s[3], t[0], t[1])
    o2 = _orient(s[0], s[1], s[2], s[3], t[2], t[3])
    o3 = _orient(t[0], t[1], t[2], t[3], s[0], s[1])
    o4 = _orient(t[0], t[1], t[2], t[3], s[2], s[3])
    return o1 * o2 < 0 and o3 * o4 < 0


def _recorte(s, c):
    """Fracao (t0, t1) do segmento dentro da caixa, ou None (Liang-Barsky)."""
    x0, y0, x1, y1 = s
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - c[0]), (dx, c[2] - x0), (-dy, y0 - c[1]), (dy, c[3] - y0)):
        if abs(p) < EPS:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            if r > t0:
                t0 = r
        else:
            if r < t0:
                return None
            if r < t1:
                t1 = r
    if t1 - t0 <= EPS:
        return None
    return t0, t1


def chamadas_encostam(s, t, tol, ancoras=()):
    """Duas chamadas de tags DIFERENTES se cruzam, se sobrepoem ou chegam a
    menos de 'tol' uma da outra? O teste de cruzamento proprio (um X) deixava
    passar ombro correndo sobre ombro e ombro encostando em T no cotovelo da
    vizinha — e ali o leitor troca as tags (caso 403/503, 07/10/2026).

    Contato colado a uma ancora (ponta da chamada no elemento) nao conta: dois
    passes no mesmo lugar tem chamadas que NASCEM juntas, e isso e inevitavel.
    Mas so quando as DUAS nascem ali: perna que passa por cima da ancora da
    vizinha e cruzamento (Red 7" descendo sobre o proprio tubo por cima do
    Pex Elbow, DEM 105, 09/10/2026).
    """
    # rejeicao rapida pelo retangulo envolvente (a maioria dos pares)
    if (min(s[0], s[2]) - tol > max(t[0], t[2]) or min(t[0], t[2]) - tol > max(s[0], s[2])
            or min(s[1], s[3]) - tol > max(t[1], t[3]) or min(t[1], t[3]) - tol > max(s[1], s[3])):
        return False
    if segmentos_cruzam(s, t):
        return True
    for (px, py), seg in (((s[0], s[1]), t), ((s[2], s[3]), t),
                          ((t[0], t[1]), s), ((t[2], t[3]), s)):
        if dist_ponto_segmento(px, py, seg) < tol:
            perto_de_ancora = False
            for ax, ay in ancoras:
                if (math.hypot(px - ax, py - ay) < 2 * tol
                        and min(math.hypot(seg[0] - ax, seg[1] - ay),
                                math.hypot(seg[2] - ax, seg[3] - ay)) < 2 * tol):
                    perto_de_ancora = True
                    break
            if not perto_de_ancora:
                return True
    return False


#: cotangente exata dos angulos usados (tan(45) em ponto flutuante nao e 1)
_COT = {45: 1.0, 60: 1.0 / math.sqrt(3.0), 30: math.sqrt(3.0)}


def _cot(angulo):
    return _COT.get(angulo) or 1.0 / math.tan(math.radians(angulo))


def custo_comprimento(P, comp, alcance):
    """Linear ate 60% do alcance; dali em diante cresce ao quadrado."""
    L = comp / max(alcance, EPS)
    return P['comp'] * L + P.get('comp_longo', 0.0) * max(0.0, L - 0.6) ** 2


def _env_segs(g):
    """Retangulo envolvente so das CHAMADAS (guardado na propria geometria)."""
    e = g.get('_env_segs')
    if e is None:
        xs = [v for sg in g['segs'] for v in (sg[0], sg[2])] or [0.0]
        ys = [v for sg in g['segs'] for v in (sg[1], sg[3])] or [0.0]
        e = (min(xs), min(ys), max(xs), max(ys)) if g['segs'] else None
        g['_env_segs'] = e if e is not None else False
    return e or None


def _env_perto(a, b, tol):
    if a is None or b is None:
        return False
    return not (a[0] - tol > b[2] or b[0] - tol > a[2] or a[1] - tol > b[3] or b[1] - tol > a[3])


def _peso_dobra(P, angulo):
    if angulo == 45:
        return P['dobra45']
    if angulo == 60:
        return P.get('dobra60', P['dobra'])
    if angulo == 30:
        return P.get('dobra30', P['dobra'])
    return P['dobra']


def _sobreposicao_paralela(s, t, tol, sen_max=0.09):
    """Comprimento de 's' que corre ao longo de 't' (quase paralelos, ate 5
    graus, e a menos de 'tol' um do outro). 0 se nao correm juntos."""
    dx, dy = s[2] - s[0], s[3] - s[1]
    Ls = math.hypot(dx, dy)
    ex, ey = t[2] - t[0], t[3] - t[1]
    Lt = math.hypot(ex, ey)
    if Ls < EPS or Lt < EPS:
        return 0.0
    ux, uy = dx / Ls, dy / Ls
    if abs(ux * ey - uy * ex) / Lt > sen_max:
        return 0.0
    # distancia de t a reta de s
    d0 = abs((t[0] - s[0]) * uy - (t[1] - s[1]) * ux)
    d1 = abs((t[2] - s[0]) * uy - (t[3] - s[1]) * ux)
    if min(d0, d1) > tol:
        return 0.0
    a = (t[0] - s[0]) * ux + (t[1] - s[1]) * uy
    b = (t[2] - s[0]) * ux + (t[3] - s[1]) * uy
    return max(0.0, min(Ls, max(a, b)) - max(0.0, min(a, b)))


def segmento_na_caixa(s, c):
    """O segmento passa por dentro da caixa?"""
    return _recorte(s, c) is not None


def comprimento_na_caixa(s, c):
    """Quanto do segmento fica dentro da caixa (pes)."""
    r = _recorte(s, c)
    if r is None:
        return 0.0
    return (r[1] - r[0]) * math.hypot(s[2] - s[0], s[3] - s[1])


def dist_ponto_segmento(px, py, s):
    x0, y0, x1, y1 = s
    dx, dy = x1 - x0, y1 - y0
    den = dx * dx + dy * dy
    t = 0.0 if den < EPS else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / den))
    cx, cy = x0 + dx * t, y0 + dy * t
    return math.hypot(px - cx, py - cy)


def _direcao(s, sen_max=0.09):
    """'h', 'v' ou 'o' (inclinada) — a mesma tolerancia de
    _sobreposicao_paralela: so linhas da mesma classe podem ser paralelas."""
    dx, dy = abs(s[2] - s[0]), abs(s[3] - s[1])
    L = math.hypot(dx, dy)
    if L < EPS or dy <= sen_max * L:
        return 'h'
    if dx <= sen_max * L:
        return 'v'
    return 'o'


def _caixa_do_segmento(s):
    return (min(s[0], s[2]), min(s[1], s[3]), max(s[0], s[2]), max(s[1], s[3]))


def _chave_fixa(caixa, segs, ancoras, meus):
    """Chave do cache da parte fixa: um bytes so com os floats EXATOS
    (struct, sem arredondar) e os ids. Tuplas de floats ocupavam ~1 kB por
    chave; isto ocupa ~0,2 kB (auditoria 12/10/2026)."""
    vals = list(caixa)
    for sg in segs:
        vals.extend(sg[:4])
    for a in ancoras:
        vals.extend(a[:2])
    cab = struct.pack('<HH%dd' % len(vals), len(segs), len(ancoras), *vals)
    return cab + u'\x00'.join(sorted(u'{}'.format(x) for x in meus)).encode('utf-8')


# ------------------------------------------------------------- grade espacial

class Grade(object):
    """Hash espacial simples: celula -> lista de chaves."""

    def __init__(self, celula):
        self.celula = float(celula)
        self.mapa = {}

    def _celulas(self, caixa):
        c = self.celula
        i0, i1 = int(math.floor(caixa[0] / c)), int(math.floor(caixa[2] / c))
        j0, j1 = int(math.floor(caixa[1] / c)), int(math.floor(caixa[3] / c))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                yield (i, j)

    def por(self, chave, caixa):
        for k in self._celulas(caixa):
            self.mapa.setdefault(k, []).append(chave)

    def tirar(self, chave, caixa):
        for k in self._celulas(caixa):
            lst = self.mapa.get(k)
            if lst and chave in lst:
                lst.remove(chave)

    def perto(self, caixa):
        vistos = set()
        for k in self._celulas(caixa):
            for chave in self.mapa.get(k, ()):
                if chave not in vistos:
                    vistos.add(chave)
                    yield chave


# --------------------------------------------------------------------- uniao

def _arvore(pts):
    """Arvore geradora minima (Prim, O(n^2)): [(comprimento, i, j)]."""
    n = len(pts)
    if n < 2:
        return []
    dentro = [False] * n
    dist = [float('inf')] * n
    pai = [-1] * n
    dist[0] = 0.0
    arestas = []
    for _ in range(n):
        u = min((i for i in range(n) if not dentro[i]), key=lambda i: dist[i])
        dentro[u] = True
        if pai[u] >= 0:
            arestas.append((dist[u], pai[u], u))
        for v in range(n):
            if not dentro[v]:
                d = math.hypot(pts[u][0] - pts[v][0], pts[u][1] - pts[v][1])
                if d < dist[v]:
                    dist[v] = d
                    pai[v] = u
    return arestas


def _componentes(idx, arestas):
    """Pedacos de 'idx' ligados pelas 'arestas' (lista de listas, ordem estavel)."""
    pai = dict((i, i) for i in idx)

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    for _d, a, b in arestas:
        pai[raiz(a)] = raiz(b)
    grupos = {}
    for i in idx:
        grupos.setdefault(raiz(i), []).append(i)
    return sorted(grupos.values(), key=lambda g: min(g))


def _espalho(pts, idx):
    return max([math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1])
                for a in idx for b in idx] or [0.0])


def _partir(pts, idx, arestas, max_n, espalho_max, vao_natural=1.5):
    """Corta o grupo pela arvore ate cada pedaco caber (n e espalhamento).

    Vao natural (aresta >= vao_natural x a mediana) corta primeiro: dois
    grupos distintos lado a lado viram duas tags, nunca 8 + resto misturado
    (Thiago, 08/10/2026). Sem vao natural (fileira uniforme), corta onde as
    metades ficam mais equilibradas (6 + 6, nao 8 + 4)."""
    if len(idx) < 2:
        return [idx]
    if len(idx) <= max_n and (espalho_max is None or _espalho(pts, idx) <= espalho_max):
        return [idx]
    dentro = set(idx)
    minhas = [e for e in arestas if e[1] in dentro and e[2] in dentro]
    comps = sorted(e[0] for e in minhas)
    mediana = comps[len(comps) // 2]
    maior = max(minhas, key=lambda e: e[0])
    if maior[0] >= vao_natural * mediana and maior[0] > 1e-9:
        corte = maior
    else:
        def equilibrio(e):
            resto = [o for o in minhas if o is not e]
            tam = [len(c) for c in _componentes(idx, resto)]
            return (min(tam), e[0])
        corte = max(minhas, key=equilibrio)
    resto = [e for e in minhas if e is not corte]
    saida = []
    for parte in _componentes(idx, resto):
        saida.extend(_partir(pts, parte, resto, max_n, espalho_max, vao_natural))
    return saida


def unir_iguais(itens, raio, max_chamadas=4, sem_uniao=(), estilo='ramos', espalho_max=None):
    """Agrupa itens de MESMO grupo e texto 100% igual pelo agrupamento NATURAL.

    Cada grupo vira um rotulo (uma tag com varias chamadas). Arvore geradora
    minima entre os iguais; aresta > raio separa (raio = maior vao entre dois
    vizinhos de uma mesma tag). Pedaco grande demais (mais que max_chamadas
    ou espalhado mais que espalho_max) e cortado no MAIOR VAO — ou, numa
    fileira uniforme, ao meio (`_partir`). Encher ate max_chamadas a partir
    do mais a esquerda misturava grupos vizinhos: com raio de 4" no CIQ os
    grupos se espalhavam por 145 mm de papel e o arranjo desfazia tudo em
    tags soltas (08/10/2026). Texto vazio nunca une.

    estilo: 'ramos' = cada elemento com o seu cotovelo no mesmo ombro (pernas
    paralelas, ramificacoes ortogonais); 'leque' = cotovelo comum (MergeElbows).

    sem_uniao: grupos que nunca unem — conduite (todo Smurf diz 'Smurf / O3/4"'
    e uma tag servindo dois Smurfs confunde) e item com ponto deslizante.
    """
    por_chave = {}
    for it in itens:
        por_chave.setdefault((it.get('grupo', ''), it.get('texto', '')), []).append(it)

    rotulos = []
    for (grupo, texto), lista in sorted(por_chave.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        lista = sorted(lista, key=lambda i: (i['ax'], i['ay']))
        if not texto.strip() or max_chamadas < 2 or grupo in sem_uniao \
                or any(it.get('alternativas') for it in lista):
            for it in lista:
                rotulos.append(_rotulo([it]))
            continue
        pts = [(it['ax'], it['ay']) for it in lista]
        arestas = [e for e in _arvore(pts) if e[0] <= raio]
        for comp in _componentes(list(range(len(lista))), arestas):
            for parte in _partir(pts, comp, arestas, max_chamadas, espalho_max):
                r = _rotulo([lista[i] for i in sorted(parte)])
                if len(parte) > 1:
                    r['estilo'] = estilo
                rotulos.append(r)
    return rotulos


def _livre(membros):
    """Direcao livre media (vetor unitario) se TODOS os membros tem 'livre'."""
    ds = [m.get('livre') for m in membros]
    if not ds or any(d is None for d in ds):
        return None
    sx, sy = sum(d[0] for d in ds), sum(d[1] for d in ds)
    n = math.hypot(sx, sy)
    return (sx / n, sy / n) if n > EPS else None


def _lado_pref(membros):
    """Lado (+1/-1) preferido comum a todos os membros, ou None."""
    lados = set(m.get('lado_pref') for m in membros)
    return lados.pop() if len(lados) == 1 else None


def _rotulo(membros):
    base = membros[0]
    return {
        # estilo margem: agua quente a esquerda, fria a direita (33/34 nos
        # cortes do MOTION, 08/10/2026)
        'lado_pref': _lado_pref(membros),
        # stub: ponta de conduite; a tag vai ALEM da ponta, do lado oposto ao
        # conduite que chega (ajuste manual do Thiago, 08/10/2026)
        'livre': _livre(membros),
        'ids': [m['id'] for m in membros],
        'ancoras': [(m['ax'], m['ay']) for m in membros],
        'w': max(m['w'] for m in membros), 'h': max(m['h'] for m in membros),
        'ox': base.get('ox', 0.0), 'oy': base.get('oy', 0.0),
        'texto': base.get('texto', ''), 'grupo': base.get('grupo', ''),
        # uma caixa por linha do texto (silhueta()); None = retangulo
        'silhueta': base.get('silhueta'),
        # conexao segue o lado do sistema com menos forca que tubo (manuais do
        # MOTION: tubo 19/19, conexao 13/16 — Pex Plug na ponta oposta fica
        # do lado mais perto, DEM 98, 09/10/2026)
        'lado_fraco': any(m.get('lado_fraco') for m in membros),
        'membros': list(membros),
        # ponto deslizante (elemento linear): [{'id','ax','ay','desvio'}]
        'alternativas': list(base.get('alternativas') or []) if len(membros) == 1 else [],
        # tubo alinhado sem chamada (Installation Plans em planta)
        'alinhar': bool(base.get('alinhar')) and len(membros) == 1,
    }


# --------------------------------------------------------------- candidatas

def geometria(rot, lado, attach_x, hy, angulo=90, ombro_min=0.0):
    """Monta a tag e as chamadas para um lado (+1 direita, -1 esquerda).

    attach_x: onde o ombro encosta na caixa. angulo 90 = perna vertical (po);
    45 = perna diagonal (do), que o estudo de Barth et al. mostrou ser a
    PREFERIDA pelos leitores. Devolve dict com 'head', 'caixa', 'segs'
    (chamadas como segmentos) e 'elbows' (um por ancora), ou None quando a
    diagonal nao cabe antes do ombro.

    hy e a altura do OMBRO, que e o CENTRO vertical da caixa do texto: o Revit
    liga a chamada ali, nao no TagHeadPosition (medido 07/10/2026 nas duas
    familias do CIQ — com o cotovelo na altura da cabeca o ombro saia torto
    exatamente 'oy'). A cabeca devolvida fica em hy - oy.
    """
    w, h, ox, oy = rot['w'], rot['h'], rot['ox'], rot['oy']
    if lado > 0:
        hx = attach_x - ox + w / 2.0
    else:
        hx = attach_x - ox - w / 2.0
    cx, cy = hx + ox, hy
    caixa = (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)
    segs = []
    elbows = []
    comp = 0.0
    dobras = 0
    if len(rot['ancoras']) > 1 and rot.get('estilo') == 'leque':
        return _geometria_mesclada(rot, lado, attach_x, hy, angulo, ombro_min,
                                   hx, oy, caixa)
    # 'ramos' (e o caso de uma ancora so): cada ancora com o SEU cotovelo no
    # ombro comum — pernas paralelas, uma ramificacao por elemento
    inicios = []
    for ax, ay in rot['ancoras']:
        d = abs(ay - hy)
        if d <= EPS:
            # chamada reta: cotovelo no MEIO do ombro, nunca em cima da ancora —
            # trecho ponta-cotovelo de comprimento zero o Revit desenha SEM
            # seta (Smurf colado no tubo, Thiago 08/10/2026; 65 de 390 tags)
            elbows.append(((ax + attach_x) / 2.0, hy))
            inicios.append(ax)
            continue
        dobras += 1
        if angulo != 90:
            # perna inclinada no sentido da tag (angulo medido da horizontal);
            # o cotovelo nao pode passar da entrada do ombro
            ex = ax + lado * d * _cot(angulo)
            if lado * (attach_x - ex) < ombro_min - EPS:
                return None
            elbows.append((ex, hy))
            inicios.append(ex)
            segs.append((ax, ay, ex, hy))
            comp += d * math.hypot(1.0, _cot(angulo))
        else:
            elbows.append((ax, hy))
            inicios.append(ax)
            segs.append((ax, ay, ax, hy))
            comp += d
    inicio = min(inicios) if lado > 0 else max(inicios)
    segs.append((inicio, hy, attach_x, hy))               # ombro (comum)
    comp += abs(attach_x - inicio)
    # a chamada mais longa (perna + ombro ate o texto) de um so elemento
    maior = 0.0
    for (ax, ay), (ex, _ey) in zip(rot['ancoras'], elbows):
        maior = max(maior, math.hypot(ex - ax, hy - ay) + abs(attach_x - ex))
    return {'head': (hx, hy - oy), 'caixa': caixa, 'silhueta': rot.get('silhueta'), 'segs': segs, 'elbows': elbows,
            'lado': lado, 'comp': comp, 'comp_max': maior, 'dobras': dobras,
            'angulo': angulo if dobras else 0, 'ancoras': list(rot['ancoras'])}


def _geometria_mesclada(rot, lado, attach_x, hy, angulo, ombro_min, hx, oy, caixa):
    """Tag unida com cotovelos MESCLADOS (MergeElbows do Revit): um cotovelo
    comum, um ombro so. E o que o Thiago fez a mao nas tags unidas (07/10/2026):
    o cotovelo fica sobre a ancora do lado da tag — a perna dela sai a 45 ou 90
    graus — e as outras convergem em diagonal para o mesmo ponto."""
    perto = max(rot['ancoras'], key=lambda a: lado * a[0])
    d = abs(perto[1] - hy)
    ex = perto[0] + (lado * d * _cot(angulo) if angulo != 90 else 0.0)
    if lado * (attach_x - ex) < ombro_min - EPS:
        return None
    if d <= EPS:
        ex = (perto[0] + attach_x) / 2.0        # ancora reta: sem seta (ver geometria)
    # nenhuma ancora pode ficar ALEM do cotovelo (a perna voltaria para tras)
    for ax, _ay in rot['ancoras']:
        if lado * (ax - ex) > EPS:
            return None
    segs = []
    comp = 0.0
    dobras = 0
    for ax, ay in rot['ancoras']:
        L = math.hypot(ex - ax, hy - ay)
        if L > EPS:
            segs.append((ax, ay, ex, hy))
            comp += L
            dobras += 1
    segs.append((ex, hy, attach_x, hy))
    comp += abs(attach_x - ex)
    return {'head': (hx, hy - oy), 'caixa': caixa, 'silhueta': rot.get('silhueta'), 'segs': segs,
            'elbows': [(ex, hy)] * len(rot['ancoras']), 'lado': lado, 'comp': comp,
            'dobras': dobras, 'angulo': angulo if d > EPS else 0, 'mesclada': True,
            'ancoras': list(rot['ancoras'])}


def _candidatas_alinhadas(rot, cfg):
    """Tag de tubo ALINHADA, sem chamada (Installation Plans em planta, PH3
    UNIT B5, 23/10/2026): o texto corre no sentido do tubo, ao lado dele
    (acima ou abaixo; no vertical, a direita ou a esquerda), centrado no
    pedaco — no meio ou a 35/65% —, e nunca em cima da linha. Pedaco onde o
    texto nao cabe nao gera candidata: ali so a chamada a 45 graus serve.

    Usa as 'alternativas' com 'seg' (u0, v0, u1, v1): cada pedaco do trecho na
    trama. A caixa gira com o tubo; a cabeca vem do deslocamento medido com a
    tag horizontal (ox, oy = centro - cabeca), girado 90 graus no vertical."""
    P = cfg.get('pesos', PESOS)
    w, h = rot['w'], rot['h']
    ox, oy = rot.get('ox', 0.0), rot.get('oy', 0.0)
    # caixa do TEXTO de verdade, nao a do rotulo da familia: o rotulo do tipo
    # 1,5 mm tem 9,4 mm de largura e o '1/2"' ~3,5 mm — com a caixa do rotulo
    # 10 tags de tubo da PH3 cairam na chamada (23/10/2026). O rotulo e
    # centrado: o centro do texto e o centro da caixa medida.
    alt = cfg.get('alinhada_texto')
    if alt:
        linhas = [l.strip() for l in (rot.get('texto') or u'').replace(u'\r', u'').split(u'\n')]
        linhas = [l for l in linhas if l and l != u'()'] or [u'']
        w = min(w, max(largura_texto(l) for l in linhas) / 1000.0 * alt)
        # o texto fica no TOPO da caixa do rotulo, nao no meio: medido na PH3
        # (23/10/2026, tags 9840225/9840226 na imagem exportada) — caixa de
        # 4,16 mm acima da cabeca, letra de 1,5 mm, centro do texto a ~3,5 mm
        # da cabeca (e nao a 2,08). Com o meio (ou a base) da caixa, o texto
        # caia EM CIMA do tubo.
        # medido na imagem (23/10/2026, mede_textos.py): o centro da letra
        # fica 0,52 x altura abaixo do topo da caixa — com 0,85/2 o texto
        # saia 0,14 mm mais baixo que o previsto e a distancia ao tubo mudava
        # 0,3 mm de um lado para o outro
        oy = oy + h / 2.0 - alt * (0.52 + 0.6 * (len(linhas) - 1))
        # girada (TagOrientation.Vertical) o texto sai 0,4 x altura mais perto
        # da cabeca que o deslocamento girado preve: medido 2,0 mm a direita
        # e 0,8 a esquerda com 1,4 pedido (mede_textos.py, 23/10/2026)
        oy_v = oy - 0.4 * alt
        h = min(h, len(linhas) * alt)
        centro = cfg.get('alinhada_centro')
        if centro is not None:
            # centro do texto MEDIDO na familia (mm de papel -> pes no cfg):
            # a familia nova (26/10/2026) tem rotulo centrado, base a 1,25 mm,
            # e desenha igual nas duas orientacoes — 2,9 mm acima da cabeca,
            # 0 ao longo (mede_cabeca.py, 11 H e 15 V na PH3 B8). As formulas
            # acima sao da familia antiga e erravam ~1 mm com ela
            ox, oy = 0.0, centro
            # girada sai ~0,3 mm mais longe da cabeca (medido na aplicacao:
            # -2,7 e +2,1 com 2,4 pedido) — centro proprio da vertical
            oy_v = cfg.get('alinhada_centro_v', centro)
    else:
        oy_v = oy
    folga = cfg['folga']
    gap = cfg.get('alinhada_gap', folga)
    # distancia FIXA do eixo do tubo ao centro do texto: o projeto usa
    # 1,2-1,5 mm em todas (PH3, mediana 1,4); a nossa variava 1,8-2,1
    dist = cfg.get('alinhada_dist') or (h / 2.0 + gap)
    alcance = max(cfg['alcance'], EPS)
    principal = rot['ids'][0] if rot.get('ids') else None
    pares = rot.get('par') or {}
    vistos = set()
    saida = []
    for alt in rot.get('alternativas') or []:
        seg = alt.get('seg')
        if not seg or alt.get('id') in vistos:
            continue
        vistos.add(alt.get('id'))
        x0, y0, x1, y1 = seg
        L = math.hypot(x1 - x0, y1 - y0)
        if L < w + 2.0 * folga:
            continue
        dx, dy = (x1 - x0) / L, (y1 - y0) / L
        vertical = abs(dy) > abs(dx)
        bw, bh = (h, w) if vertical else (w, h)
        n = (1.0, 0.0) if vertical else (0.0, 1.0)
        t_min = (w / 2.0 + folga) / L
        bases = [0.5, 0.35, 0.65, 0.2, 0.8]
        estacao, lado_par = pares.get(alt.get('id')) or (None, None)
        t_par = None
        if estacao is not None:
            # par colado / fila: as tags na MESMA estacao
            s0 = y0 if vertical else x0
            ds = dy if vertical else dx
            t_par = (estacao - s0) / (ds * L) if abs(ds) > EPS else None
            if t_par is not None:
                t_par = min(1.0 - t_min, max(t_min, t_par))
                bases.append(t_par)
        # lado padrao: ACIMA do tubo horizontal, a ESQUERDA do vertical;
        # abaixo/direita so quando nao cabe (Thiago, 23/10/2026). No par
        # colado manda o lado de fora
        lado_bom = lado_par if lado_par is not None else (-1 if vertical else 1)
        ts = sorted(set(min(1.0 - t_min, max(t_min, t)) for t in bases))
        for t in ts:
            cx0, cy0 = x0 + dx * t * L, y0 + dy * t * L
            for lado in (1, -1):
                # distancia por LADO (Thiago, 26/10/2026): acima/abaixo no
                # horizontal, direita/esquerda no vertical — o "outro lado"
                # saia longe com uma distancia so
                lados = cfg.get('alinhada_dist_lados') or {}
                d_lado = lados.get(('V' if vertical else 'H', lado), dist)
                cx, cy = cx0 + n[0] * lado * d_lado, cy0 + n[1] * lado * d_lado
                if vertical:
                    head = (cx + oy_v, cy - ox)
                else:
                    head = (cx - ox, cy - oy)
                if t_par is not None:
                    extra = 0.0 if abs(t - t_par) * L < EPS + 1e-4 else P.get('alinhada_fora_do_par', 3.0)
                else:
                    extra = P.get('alinhada_desvio', 1.0) * abs(t - 0.5) * L / alcance
                if lado != lado_bom:
                    extra += P.get('alinhada_dentro_do_par', 30.0) if lado_par is not None \
                        else P.get('alinhada_lado', 2.0)
                if alt.get('id') != principal:
                    extra += P.get('alinhada_outro_pedaco', 1.0)
                saida.append({'head': head, 'caixa': (cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0),
                              'silhueta': None, 'segs': [], 'elbows': [], 'lado': lado, 'comp': 0.0,
                              'dobras': 0, 'angulo': 0, 'ancoras': [(cx0, cy0)], 'ids': [alt.get('id')],
                              'alinhada': 'V' if vertical else 'H', 'extra': extra})
    return saida


def parear_alinhados(rotulos, dist_max, sobre_min, fila_max=0.0):
    """Tubos colados (quente/frio correndo juntos) e FILAS de tubos paralelos.
    Grava em rot['par'] {id do pedaco: (estacao, lado)}:
    - par: o vizinho paralelo mais perto (eixos a ate 'dist_max', correndo
      juntos ao menos 'sobre_min') da o lado de fora (+1 acima/a direita);
    - fila: paralelos a ate 'fila_max' um do outro e de comprimento parecido
      (correm juntos 70% do menor) levam as tags na MESMA estacao, o centro
      do trecho comum a todos — as descidas de 1/2" da PH3 "alinhadas
      bonitinhas" (Thiago, 23/10/2026). Sem fila, a estacao e a do par.
    estacao = x no horizontal, y no vertical (None = livre); lado None = livre."""
    pecas = []
    for i, r in enumerate(rotulos):
        if not r.get('alinhar'):
            continue
        for a in r.get('alternativas') or []:
            s = a.get('seg')
            if not s:
                continue
            L = math.hypot(s[2] - s[0], s[3] - s[1])
            if L < EPS:
                continue
            vert = abs(s[3] - s[1]) > abs(s[2] - s[0])
            if vert and abs(s[2] - s[0]) > 0.02 * L or not vert and abs(s[3] - s[1]) > 0.02 * L:
                continue        # so ortogonal: e o que a planta tem
            eixo = (s[0] + s[2]) / 2.0 if vert else (s[1] + s[3]) / 2.0
            ini, fim = sorted((s[1], s[3]) if vert else (s[0], s[2]))
            pecas.append((i, a.get('id'), vert, eixo, ini, fim))
    # fila: uniao por vizinhanca (cadeia) de paralelos de comprimento parecido
    pai = list(range(len(pecas)))

    def raiz(k):
        while pai[k] != k:
            pai[k] = pai[pai[k]]
            k = pai[k]
        return k
    for k, (i, _a, vert, eixo, ini, fim) in enumerate(pecas):
        for m in range(k + 1, len(pecas)):
            j, _b, vert_b, eixo_b, ini_b, fim_b = pecas[m]
            if j == i or vert_b != vert:
                continue
            d = abs(eixo - eixo_b)
            sobre = min(fim, fim_b) - max(ini, ini_b)
            if EPS < d <= fila_max and sobre >= max(sobre_min, 0.7 * min(fim - ini, fim_b - ini_b)):
                pai[raiz(m)] = raiz(k)
    grupos = {}
    for k in range(len(pecas)):
        grupos.setdefault(raiz(k), []).append(k)
    estacao_fila = {}
    for membros in grupos.values():
        if len(membros) < 2:
            continue
        a = max(pecas[k][4] for k in membros)
        b = min(pecas[k][5] for k in membros)
        if b - a >= sobre_min:
            for k in membros:
                estacao_fila[k] = (a + b) / 2.0
    for k, (i, aid, vert, eixo, ini, fim) in enumerate(pecas):
        melhor = None
        for j, bid, vert_b, eixo_b, ini_b, fim_b in pecas:
            if j == i or vert_b != vert:
                continue
            d = abs(eixo - eixo_b)
            sobre = min(fim, fim_b) - max(ini, ini_b)
            if d < EPS or d > dist_max or sobre < sobre_min:
                continue
            if melhor is None or d < melhor[0]:
                melhor = (d, (max(ini, ini_b) + min(fim, fim_b)) / 2.0, 1 if eixo > eixo_b else -1)
        estacao = estacao_fila.get(k, melhor[1] if melhor else None)
        lado = melhor[2] if melhor else None
        if estacao is not None or lado is not None:
            rotulos[i].setdefault('par', {})[aid] = (estacao, lado)


def _mesmo_texto(centrais, rot, lado, cfg):
    """Variantes das candidatas centrais do lado com as setas de 'rot'
    (deslocadas): mesmo texto, mesma altura de ombro, so a perna muda."""
    w, ox, oy = rot['w'], rot['ox'], rot['oy']
    saida = []
    for g0 in centrais:
        if (lado is not None and g0['lado'] != lado) or not g0.get('dobras'):
            continue
        hx, hyc = g0['head']
        ld = g0['lado']
        attach_x = hx + ox - w / 2.0 if ld > 0 else hx + ox + w / 2.0
        g = geometria(rot, ld, attach_x, hyc + oy, g0.get('angulo') or 90, cfg.get('ombro_min', 0.0))
        if g is not None:
            saida.append(g)
    return saida


def candidatas(rot, cfg, vizinhos=()):
    """Candidatas do rotulo. Com 'alternativas' (elemento linear), a ponta da
    chamada pode DESLIZAR ao longo do elemento: gera as candidatas de cada ponto
    alternativo e cobra 'desliza' pelo afastamento da posicao ideal. Cada
    geometria leva 'ids' — o elemento que a tag vai referenciar naquele ponto."""
    alts = rot.get('alternativas') or []
    if not alts:
        saida = _candidatas_fixas(rot, cfg, vizinhos)
        for g in saida:
            g['ids'] = list(rot['ids'])
        # margem: a seta pode pegar a BORDA da peca, do lado do texto, e a
        # perna corre ao lado do proprio tubo em vez de cima dele (Pex Elbow
        # no pe do Blue, DEM 57 Copiar 1, 12/10/2026 — 1,6 mm do centro)
        # a seta nao sai da peca. Com 'miolo' (caixa real da peca na vista,
        # faixa central) a seta vai a borda do miolo do lado do texto; sem ele,
        # no maximo 90% do raio do simbolo (o tampao ficou com a seta no tubo —
        # o LocationPoint dele e o conector, na borda; DEM 57, 12/10/2026)
        # Planta (Perto, Installation Plans): o mesmo, tambem na tag unida —
        # cada seta na borda da SUA peca, so quando a perna correria sobre o
        # ramal ou a corrida (a seta central nao paga nada a mais). E o TEXTO
        # FICA ONDE ESTAVA: a variante lateral reaproveita a posicao de texto
        # de cada candidata central e so troca a seta. Gerando de novo, o texto
        # andava junto e saia do recorte (te vertical 9815625, PH3 A2 IP001,
        # Thiago 27/10/2026)
        membros = rot.get('membros') or ()
        ancoras = list(rot['ancoras'])
        if cfg.get('ponta_lateral') and len(membros) == len(ancoras) \
                and (len(ancoras) == 1 or not cfg.get('margem')):
            P = cfg.get('pesos', PESOS)
            laterais = []
            # planta: a seta so conta como fora do eixo se sair ao menos a
            # folga da chamada — a 0,35 mm a perna ainda corria sobre a
            # corrida do te vertical 9820198 (tubo + folga = 0,44 mm)
            minimo = EPS if cfg.get('margem') else max(EPS, cfg.get('folga_chamada', 0.0))
            def borda(m, ax, lado):
                meio = m.get('miolo')
                d = min(cfg['ponta_lateral'], 0.9 * m.get('r', 0.0))
                x_seta = (meio[2] if lado > 0 else meio[0]) if meio else ax + lado * d
                return x_seta if lado * (x_seta - ax) >= minimo else None
            for lado in (1, -1):
                novas = []
                for m, (ax, ay) in zip(membros, ancoras):
                    x_seta = borda(m, ax, lado)
                    if x_seta is None and not cfg.get('margem'):
                        # planta: do lado do texto a borda e o proprio eixo (te
                        # de corrida vertical com o ramal do outro lado) — a
                        # seta sai pelo outro lado (9820198, PH3 A2, 27/10/2026)
                        x_seta = borda(m, ax, -lado)
                    novas.append((x_seta, ay) if x_seta is not None else (ax, ay))
                if novas == ancoras:
                    continue
                r = dict(rot, ancoras=novas)
                if cfg.get('margem'):
                    gerar = [g for g in _candidatas_fixas(r, cfg, vizinhos) if g['lado'] == lado]
                else:
                    gerar = _mesmo_texto(saida, r, lado, cfg)
                for g in gerar:
                    g['ids'] = list(rot['ids'])
                    g['extra'] = g.get('extra', 0.0) + P.get('ponta_lateral', 0.0)
                    laterais.append(g)
            if laterais and P.get('ponta_no_eixo'):
                for g in saida:
                    g['extra'] = g.get('extra', 0.0) + P['ponta_no_eixo']
            saida.extend(laterais)
        return saida
    P = cfg.get('pesos', PESOS)
    alcance = max(cfg['alcance'], EPS)
    saida = []
    # tubo alinhado (Installation Plans): sem chamada quando cabe; a chamada a
    # 45 graus fica como recurso e paga 'chamada_tubo'
    alinhar = rot.get('alinhar') and cfg.get('alinhar_tubos')
    if alinhar:
        saida.extend(_candidatas_alinhadas(rot, cfg))
    penal = P.get('chamada_tubo', 40.0) if alinhar else 0.0
    for alt in alts:
        if alt.get('normal'):
            for g in _candidatas_pente(rot, alt, cfg):
                saida.append(g)
            continue
        r = dict(rot)
        # feixe de Smurfs: a alternativa traz uma ponta por membro
        r['ancoras'] = list(alt.get('ancoras') or [(alt['ax'], alt['ay'])])
        r['ids'] = list(alt.get('ids') or [alt['id']])
        extra = P.get('desliza', 0.0) * abs(alt.get('desvio', 0.0)) / alcance
        for g in _candidatas_fixas(r, cfg, vizinhos):
            g['ids'] = list(r['ids'])
            g['extra'] = extra + penal
            saida.append(g)
    return saida


def geometria_pente(rot, ancoras, normal, ponta, e, lado, attach_x, ombro_min=0.0):
    """Pente: as pontas estao numa linha perpendicular ao tronco (ancoras em
    ordem ao longo de 'normal'); o cotovelo fica NESSA linha, 'e' alem da
    ancora da ponta escolhida ('alto' = ultima, no sentido de 'normal';
    'baixo' = primeira, no sentido contrario). Uma linha so atravessa o feixe,
    com uma seta por conduite; dali o ombro horizontal ate a tag.

    Testado no Revit 08/10/2026 (14 Smurfs, MergeElbows): renderiza limpo.
    Devolve None se o ombro nao cabe ou voltaria por cima da propria linha.
    """
    if ponta == 'alto':
        fim, ini, d = ancoras[-1], ancoras[0], normal
    else:
        fim, ini, d = ancoras[0], ancoras[-1], (-normal[0], -normal[1])
    ex, ey = fim[0] + d[0] * e, fim[1] + d[1] * e
    if lado * (attach_x - ex) < ombro_min - EPS:
        return None
    # linha quase horizontal: o ombro so pode seguir no mesmo sentido dela
    if abs(d[1]) < 0.2 and lado * d[0] < 0:
        return None
    w, h, ox, oy = rot['w'], rot['h'], rot['ox'], rot['oy']
    hx = attach_x - ox + w / 2.0 if lado > 0 else attach_x - ox - w / 2.0
    cx = hx + ox
    caixa = (cx - w / 2.0, ey - h / 2.0, cx + w / 2.0, ey + h / 2.0)
    segs = [(ini[0], ini[1], ex, ey), (ex, ey, attach_x, ey)]
    return {'head': (hx, ey - oy), 'caixa': caixa, 'silhueta': rot.get('silhueta'), 'segs': segs,
            'elbows': [(ex, ey)] * len(ancoras), 'lado': lado,
            'comp': e + abs(attach_x - ex), 'dobras': 1, 'angulo': 45,
            'mesclada': True, 'pente': True, 'ancoras': list(ancoras)}


def _candidatas_pente(rot, alt, cfg):
    P = cfg.get('pesos', PESOS)
    alcance = max(cfg['alcance'], EPS)
    passo = cfg['passo']
    ombro = cfg['ombro_min']
    e0 = max(cfg.get('perna_min', 0.0), passo)
    extra = P.get('desliza', 0.0) * abs(alt.get('desvio', 0.0)) / alcance
    saida = []
    for ponta in alt.get('pontas', ('baixo', 'alto')):
        for ke in range(6):
            e = e0 + ke * passo * 2
            fim = alt['ancoras'][-1] if ponta == 'alto' else alt['ancoras'][0]
            sx = alt['normal'][0] if ponta == 'alto' else -alt['normal'][0]
            ex = fim[0] + sx * e
            for lado in (1, -1):
                borda = ex + lado * ombro
                base = math.ceil(borda / passo) * passo if lado > 0 else math.floor(borda / passo) * passo
                for i in range(int(cfg.get('n_ombro', 6))):
                    g = geometria_pente(rot, alt['ancoras'], alt['normal'], ponta, e, lado,
                                        base + lado * i * passo * 2, ombro)
                    if g is None:
                        continue
                    g['ids'] = list(alt['ids'])
                    g['extra'] = extra
                    saida.append(g)
    return saida


def _candidatas_fixas(rot, cfg, vizinhos=()):
    """Posicoes possiveis: lado x afastamento do ombro x altura, em grade.

    A grade e GLOBAL (multiplos de cfg['passo']): tags vizinhas caem nas mesmas
    colunas e linhas, e e isso que as alinha. 'vizinhos' (geometrias ja postas)
    geram candidatas de empilhamento: mesma borda, logo acima ou abaixo.
    """
    passo = cfg['passo']
    ombro = cfg['ombro_min']
    alcance = cfg['alcance']
    folga = cfg['folga']
    xs = [a[0] for a in rot['ancoras']]
    ys = [a[1] for a in rot['ancoras']]
    ymeio = (min(ys) + max(ys)) / 2.0
    perna_min = cfg.get('perna_min', 0.0)
    angulos = cfg.get('angulos', (90, 45))
    if cfg.get('margem'):
        return _candidatas_margem(rot, cfg, vizinhos, xs, ys, ymeio, perna_min, angulos)
    n_x = max(1, int(cfg.get('n_ombro', 6)))
    passo_y = cfg.get('passo_y') or passo
    n_y = int(alcance / passo_y)
    saida = []
    for lado in (1, -1):
        borda = (max(xs) + ombro) if lado > 0 else (min(xs) - ombro)
        if lado > 0:
            x_base = math.ceil(borda / passo) * passo
        else:
            x_base = math.floor(borda / passo) * passo
        y_base = round(ymeio / passo) * passo
        for i in range(n_x):
            attach = x_base + lado * i * passo * 2
            for j in range(-n_y, n_y + 1):
                hy = y_base + j * passo_y
                if not _pernas_ok(ys, hy, perna_min):
                    continue
                _junta(saida, rot, lado, attach, hy, ombro, angulos)
        # reta: na altura exata da ancora (so com uma ancora)
        if len(rot['ancoras']) == 1:
            saida.append(geometria(rot, lado, borda, ys[0]))
    # empilhar junto das vizinhas ja postas
    h = rot['h']
    for g in vizinhos:
        c = g['caixa']
        for lado in (1, -1):
            if lado > 0:
                attach = c[0]
                if attach < max(xs) + ombro - EPS:
                    continue
            else:
                attach = c[2]
                if attach > min(xs) - ombro + EPS:
                    continue
            for alvo_cy in (c[3] + folga + h / 2.0, c[1] - folga - h / 2.0):
                hy = alvo_cy
                if abs(hy - ymeio) <= alcance and _pernas_ok(ys, hy, perna_min):
                    _junta(saida, rot, lado, attach, hy, ombro, angulos)
    return saida


def _candidatas_margem(rot, cfg, vizinhos, xs, ys, ymeio, perna_min, angulos):
    """Estilo MARGEM (installation plans, 08/10/2026): o texto vai FORA do
    desenho, numa coluna de cada lado; a chamada atravessa o desenho (perna
    vertical + ombro horizontal, ou reta). cfg['margem'] = (x0, y0, x1, y1)
    do desenho; cfg['margem_gap'] = afastamento da coluna a borda.

    Medido no MOTION: nos cortes 22 das 25 cabecas do Thiago ficam fora do
    recorte, a esquerda e a direita."""
    passo = cfg['passo']
    passo_y = cfg.get('passo_y') or passo
    ombro = cfg['ombro_min']
    m = cfg['margem']
    gap = cfg.get('margem_gap', ombro)
    alcance = cfg['alcance']
    lo = max(m[1], ymeio - alcance)
    hi = min(m[3], ymeio + alcance)
    # faixa de alturas de ombro: no F10 (181 pernas do projeto) a maior tem
    # 73 mm e 99% ficam abaixo de 52 — testar o desenho inteiro multiplicava
    # as candidatas e o motor levava minutos por corte (09/10/2026)
    ap = cfg.get('alcance_perna')
    if ap:
        lo = max(lo, min(ys) - ap)
        hi = min(hi, max(ys) + ap)
    saida = []
    # lado do sistema e REGRA, nao preferencia: quente sempre a esquerda, fria
    # sempre a direita (Thiago, 09/10/2026 — como custo, 2 tags de tubo quente
    # atravessavam para a direita no DEM 105)
    lados = (rot['lado_pref'],) if rot.get('lado_pref') else (1, -1)
    for lado in lados:
        attach = (m[2] + gap) if lado > 0 else (m[0] - gap)
        if lado * (attach - (max(xs) if lado > 0 else min(xs))) < ombro - EPS:
            continue
        j = int(math.floor(lo / passo_y))
        while j * passo_y <= hi + EPS:
            hy = j * passo_y
            if _pernas_ok(ys, hy, perna_min):
                _junta(saida, rot, lado, attach, hy, ombro, angulos)
            j += 1
        # reta: na altura exata da ancora (uma ancora so)
        if len(rot['ancoras']) == 1:
            g = geometria(rot, lado, attach, ys[0])
            if g is not None:
                saida.append(g)
    # empilhar junto das vizinhas ja postas na mesma coluna
    h = rot['h']
    folga = cfg['folga']
    for g in vizinhos:
        c = g['caixa']
        lado = g['lado']
        if lado not in lados:
            continue
        attach = c[0] if lado > 0 else c[2]
        for hy in (c[3] + folga + h / 2.0, c[1] - folga - h / 2.0):
            if lo - h <= hy <= hi + h and _pernas_ok(ys, hy, perna_min):
                _junta(saida, rot, lado, attach, hy, ombro, angulos)
    return saida


def _junta(saida, rot, lado, attach, hy, ombro, angulos, diag_min=0.0):
    for ang in angulos:
        g = geometria(rot, lado, attach, hy, ang, ombro)
        if g is None:
            continue
        # perna inclinada curta some no papel (a seta nem aparece): o Thiago
        # trocou por ortogonal no DEM 98 (09/10/2026)
        if ang != 90 and diag_min and any(
                math.hypot(t[2] - t[0], t[3] - t[1]) < diag_min for t in g['segs'][:-1]):
            continue
        saida.append(g)


def _pernas_ok(ys, hy, perna_min):
    """Perna vertical ou e zero (chamada reta) ou tem o minimo — nada de degrau
    de 1 mm, que no papel parece erro de desenho."""
    for y in ys:
        d = abs(y - hy)
        if EPS < d < perna_min:
            return False
    return True


# --------------------------------------------------------------------- custo

class Cena(object):
    """Obstaculos fixos + rotulos ja postos, com grade espacial."""

    def __init__(self, cfg, linhas=(), simbolos=(), caixas_fixas=(), limites=None):
        self.cfg = cfg
        cel = max(cfg['alcance'], 1e-3)
        self.limites = limites
        # linha = (x0, y0, x1, y1[, meia_largura]); conduite e tubo tem largura
        # real no desenho, e um feixe de conduites e uma faixa, nao um fio
        # grade das linhas FINA (5 passos ~ uma tag): o DWG tem milhares de
        # segmentos e a celula grande fazia cada candidata testar ~110 deles
        self.linhas = []
        self.larg = []
        self.parede = []
        self.env_linhas = []
        self.g_linhas = Grade(cfg['passo'] * 5)
        # grades por ORIENTACAO e so de tubos: 'corre paralelo' so pode valer
        # para linha da mesma direcao, e 'corta tubo' so para linha com
        # largura. No F10 (vinculos com ~2000 arestas) o custo testava 33
        # milhoes de pares inuteis — ombro horizontal x montante vertical
        self.g_dir = {'h': Grade(cfg['passo'] * 5), 'v': Grade(cfg['passo'] * 5),
                      'o': Grade(cfg['passo'] * 5)}
        self.g_tubos = Grade(cfg['passo'] * 5)
        for i, s in enumerate(linhas):
            m = s[4] if len(s) > 4 else 0.0
            self.linhas.append(tuple(s[:4]))
            self.larg.append(m)
            # 6o campo opcional: 'parede' (paga 'linha_parede', nao 'linha')
            self.parede.append(len(s) > 5 and s[5] == 'parede')
            c = _caixa_do_segmento(s)
            env = (c[0] - m, c[1] - m, c[2] + m, c[3] + m)
            self.env_linhas.append(env)
            self.g_linhas.por(i, env)
            self.g_dir[_direcao(s)].por(i, env)
            if m > 0:
                self.g_tubos.por(i, env)
        self.simbolos = list(simbolos)          # (x, y, r, dono)
        self.g_simb = Grade(cel)
        for i, s in enumerate(self.simbolos):
            self.g_simb.por(i, (s[0] - s[2], s[1] - s[2], s[0] + s[2], s[1] + s[2]))
        # caixa fixa = (x0, y0, x1, y1[, 'cota']): a chamada atravessa cota
        # sem drama — linha de chamada e de cota se cruzam no projeto (Thiago,
        # DEM 57, 12/10/2026); texto sobre a cota continua proibido
        self.fixas = [tuple(c[:4]) for c in caixas_fixas]
        self.fixa_cota = [len(c) > 4 and c[4] == 'cota' for c in caixas_fixas]
        self.g_fixas = Grade(cel)
        for i, c in enumerate(self.fixas):
            self.g_fixas.por(i, c)
        self.postos = {}                         # idx rotulo -> geometria
        self.g_postos = Grade(cel)
        self._cache_fixo = {}                    # ver _fixo
        self._cache_velho = {}
        # piso da poda com a parte fixa: compensa onde a mesma candidata e
        # buscada muitas vezes (margem: 6 recomecos + acabamento). Na planta
        # (perto) cada candidata e vista ~1 vez e o piso so encarecia
        self.piso_fixo = bool(cfg.get('piso_fixo', cfg.get('margem')))
        # entradas por geracao (no maximo 2 geracoes, ~0,66 kB cada em
        # CPython). Bancada, corte de 26 tags (~100 mil posicoes): teto 40
        # mil 288 s, 60 mil 224 s (~80 MB no maximo), 100 mil 211 s, sem
        # teto 206 s — o original levava 527 s
        self.teto_cache = int(cfg.get('teto_cache', 60000))

    # -- postos
    def _env(self, g):
        cx = [g['caixa'][0], g['caixa'][2]]
        cy = [g['caixa'][1], g['caixa'][3]]
        for s in g['segs']:
            cx += [s[0], s[2]]
            cy += [s[1], s[3]]
        return (min(cx), min(cy), max(cx), max(cy))

    def por(self, idx, g):
        self.postos[idx] = g
        self.g_postos.por(idx, self._env(g))

    def tirar(self, idx):
        g = self.postos.pop(idx, None)
        if g is not None:
            self.g_postos.tirar(idx, self._env(g))

    def vizinhos(self, caixa):
        return [self.postos[i] for i in self.g_postos.perto(caixa)]

    # -- custo de uma geometria contra a cena
    def custo(self, idx, g, rot, detalhe=False, limite=None):
        """limite: _melhor passa o melhor custo ja achado; depois do bloco das
        tags postas (o unico com desconto) o custo so sobe, entao ao passar do
        limite a candidata ja perdeu e o resto (linhas, tubos) nao roda."""
        P = self.cfg.get('pesos', PESOS)
        folga = self.cfg['folga']
        cx = g['caixa']
        env = self._env(g)
        c = self.custo_proprio(g, rot)
        conta = {'tag': 0, 'simbolo': 0, 'linha': 0, 'cruza': 0, 'chamada_tag': 0, 'cruza_tubo': 0}
        # tag x tag postas (as fixas estao em _fixo)
        area = max((cx[2] - cx[0]) * (cx[3] - cx[1]), EPS)
        alinhadas = 0          # bonus limitado a 2 (uma acima, uma abaixo)
        tol_chamada = self.cfg.get('folga_chamada', 0.0)
        resp = self.cfg.get('respiro_alinhada', 0.0)
        meus_anc = list(g.get('ancoras', rot['ancoras']))
        g_env = _env_segs(g)
        for j in self.g_postos.perto(env):
            if j == idx:
                continue
            o = self.postos[j]
            ancs = meus_anc + list(o.get('ancoras', ()))
            # linha contra linha quando ha silhueta: a vizinha encaixa no vazio
            # da 2a linha curta (ZZ_MARGEM4_DEM 105, 09/10/2026)
            a_tag = textos_sobrepoem(g, o, folga)
            if a_tag > 0.0:
                c += P['tag'] * (1.0 + a_tag / area)
                conta['tag'] += 1
            elif resp and bool(g.get('alinhada')) != bool(o.get('alinhada')):
                # respiro: tag de conexao/parede ENCOSTADA no texto do tubo
                # some no desenho; o projeto leva para longe com chamada
                # comprida (Thiago, PH3 23/10/2026)
                oc = o['caixa']
                d = math.hypot(max(0.0, cx[0] - oc[2], oc[0] - cx[2]), max(0.0, cx[1] - oc[3], oc[1] - cx[3]))
                if d < resp:
                    c += P.get('respiro', 15.0) * (1.0 - d / resp)
            o_env = _env_segs(o)
            perto_ch = _env_perto(g_env, o_env, tol_chamada)
            perto_cx = _env_perto(g_env, o['caixa'], 0.0)
            for s in g['segs']:
                if perto_ch:
                    for t in o['segs']:
                        if chamadas_encostam(s, t, tol_chamada, ancs):
                            c += P['cruza']
                            conta['cruza'] += 1
                if perto_cx and _segmento_no_texto(s, o):
                    c += P['chamada_tag']
                    conta['chamada_tag'] += 1
            if _env_perto(o_env, cx, 0.0):
                for t in o['segs']:
                    if _segmento_no_texto(t, g):
                        c += P['chamada_tag']
                        conta['chamada_tag'] += 1
            # alinhamento: mesma borda de entrada, vizinha na vertical
            if o['lado'] == g['lado'] and abs(o['caixa'][1] - cx[1]) < 4 * (cx[3] - cx[1]):
                borda_o = o['caixa'][0] if o['lado'] > 0 else o['caixa'][2]
                borda_g = cx[0] if g['lado'] > 0 else cx[2]
                if abs(borda_o - borda_g) < self.cfg['passo'] * 0.25 and alinhadas < 2:
                    # alinhar nao justifica ir longe: o bonus some quando a
                    # chamada chega ao alcance (07/10/2026 — tags iam para
                    # colunas a 30 mm com lugar livre a 12 mm)
                    c -= P['alinha'] * max(0.0, 1.0 - g['comp'] / max(self.cfg['alcance'], EPS))
                    alinhadas += 1
            # ja perdeu: nem o bonus que ainda pode vir (alinhamento, no
            # maximo 2) traz de volta abaixo do limite. Na margem toda tag
            # posta e vizinha (a chamada cruza o desenho) e este laco era
            # metade do tempo do motor (auditoria 12/10/2026)
            if limite is not None and c - P['alinha'] * (2 - alinhadas) >= limite:
                return c
        if limite is not None and c >= limite:
            return c
        # tudo daqui para baixo so depende da geometria e dos obstaculos FIXOS
        # (nao das tags postas): calculado uma vez e guardado (_fixo). As
        # parcelas somam na mesma ordem de antes — o custo sai identico
        ent, meus, meus_anc = self._fixo(g, rot)
        for k in range(4):
            for v in self._bloco(ent, k, g, meus, meus_anc):
                c += v
            if limite is not None and c >= limite:
                return c
        if detalhe:
            for k in range(4):
                if ent[4 + k]:
                    for nome, n in zip(_CONTA_FIXA, ent[4 + k]):
                        conta[nome] += n
            return c, conta
        return c

    def custo_fixo(self, g, rot):
        """Soma da parte do custo que nao depende das tags postas (recorte de
        caixa fixa, simbolo, linhas, chamada sobre linha e cortando tubo).
        Junto com custo_proprio e o piso exato da poda em _melhor."""
        ent, meus, meus_anc = self._fixo(g, rot)
        if ent[8] is None:
            ent[8] = sum(sum(self._bloco(ent, k, g, meus, meus_anc)) for k in range(4))
        return ent[8]

    def _fixo(self, g, rot):
        """(entrada, meus, ancoras) da parte fixa do custo. Entrada = lista de
        9: parcelas dos 4 blocos, contagens dos 4 blocos (tupla na ordem de
        _CONTA_FIXA, ou None se zero) e o total. Os 4 blocos (caixas fixas e simbolos,
        linhas, chamada sobre linha, chamada cortando tubo) sao calculados SO
        quando pedidos (_bloco): custo() para no meio quando passa do limite,
        como antes — na planta com DWG de 5000 linhas calcular tudo de uma vez
        deixava o motor 50% mais lento.

        No F10 o motor chamava custo() ~1200 vezes por busca e recalculava
        essa parte de cada candidata a cada fase (reinicios, reparo, pares,
        abrir espaco) — ~50 vezes por tag. Ela so depende da caixa, das
        chamadas, de QUEM a tag marca e de onde a seta cai (auditoria
        12/10/2026). Os pesos da cena sao fixos depois de criada."""
        # atalho: a mesma geometria pergunta 2x por busca (piso e custo)
        ids_rot = tuple(rot['ids'])
        memo = g.get('_fixo')
        if memo is not None and memo[0] == ids_rot and memo[1] is self:
            return memo[2], memo[3], memo[4]
        meus_anc = tuple(g.get('ancoras', rot['ancoras']))
        meus = set(ids_rot) | set(g.get('ids', ()))
        r = None
        if self.piso_fixo:
            # cache GLOBAL so na margem (a mesma posicao volta em cada
            # recomeco); na planta montar a chave custava mais que o calculo
            chave = _chave_fixa(g['caixa'], g['segs'], meus_anc, meus)
            r = self._cache_fixo.get(chave)
            if r is None:
                r = self._cache_velho.get(chave)
                if r is not None:
                    self._guardar_fixo(chave, r)     # ainda em uso: promove
        if r is None:
            # 9 casas e nada da geometria: quem pede um bloco ja tem a
            # geometria na mao (2,3 kB por entrada caiu para ~0,5 kB)
            r = [None] * 9
            if self.piso_fixo:
                self._guardar_fixo(chave, r)
        g['_fixo'] = (ids_rot, self, r, meus, meus_anc)
        return r, meus, meus_anc

    def _guardar_fixo(self, chave, r):
        """Cache de duas geracoes: cheia a atual, ela vira a velha e a velha
        vai embora. Memoria limitada a 2x o teto e o que ainda esta em uso
        sobrevive (limpar tudo de uma vez jogava fora o trabalho a cada
        estouro). Nunca muda o resultado — o cache e memoizacao pura."""
        if len(self._cache_fixo) >= self.teto_cache:
            self._cache_velho = self._cache_fixo
            self._cache_fixo = {}
        self._cache_fixo[chave] = r

    def _bloco(self, ent, k, g, meus, meus_anc):
        if ent[k] is None:
            parcelas, conta = (self._fixo_caixas, self._fixo_linhas, self._fixo_sobre,
                               self._fixo_tubos)[k](g, meus, list(meus_anc))
            ent[k] = tuple(parcelas)
            ent[4 + k] = tuple(conta.get(n, 0) for n in _CONTA_FIXA) if any(conta.values()) else None
        return ent[k]

    def _fixo_caixas(self, g, meus, meus_anc):
        """Bloco 0: caixas fixas (tags e textos existentes, cotas) e simbolos."""
        P = self.cfg.get('pesos', PESOS)
        folga = self.cfg['folga']
        cx = g['caixa']
        caixa_f = (cx[0] - folga / 2.0, cx[1] - folga / 2.0, cx[2] + folga / 2.0, cx[3] + folga / 2.0)
        env = self._env(g)
        area = max((cx[2] - cx[0]) * (cx[3] - cx[1]), EPS)
        conta = {'tag': 0, 'simbolo': 0, 'chamada_tag': 0}
        b_fixas = []
        for j in self.g_fixas.perto(env):
            f = self.fixas[j]
            if _sobrepoe(caixa_f, f):
                b_fixas.append(P['tag'] * (1.0 + _area_sobreposta(caixa_f, f) / area))
                conta['tag'] += 1
            for s in g['segs']:
                if segmento_na_caixa(s, f):
                    if self.fixa_cota[j]:
                        b_fixas.append(P.get('chamada_cota', P['chamada_tag']))
                    else:
                        b_fixas.append(P['chamada_tag'])
                        conta['chamada_tag'] += 1
        # simbolos (elementos): a tag nao cobre nenhum; a chamada nao passa
        # por cima de simbolo alheio. Tag unida: so a perna da PROPRIA peca e
        # isenta — a perna do te azul descia cruzando o te vermelho da mesma
        # tag (PH3 B5, tag 9846750, Thiago 27/10/2026)
        anc_de = dict(zip(g.get('ids') or (), meus_anc))
        for j in self.g_simb.perto(env):
            x, y, r, dono = self.simbolos[j]
            if cx[0] - r < x < cx[2] + r and cx[1] - r < y < cx[3] + r:
                b_fixas.append(P['simbolo'])
                conta['simbolo'] += 1
            if dono in meus and (len(anc_de) < 2 or dono not in anc_de):
                continue
            a = anc_de.get(dono)
            peso = P.get('chamada_membro', P['chamada_simb']) if a is not None else P['chamada_simb']
            for s in g['segs']:
                if a is not None and abs(s[0] - a[0]) < EPS and abs(s[1] - a[1]) < EPS:
                    continue            # a perna que sai da propria peca
                if dist_ponto_segmento(x, y, s) < r:
                    b_fixas.append(peso)
                    break
        return b_fixas, conta

    def _fixo_linhas(self, g, meus, meus_anc):
        """Bloco 1: linhas do desenho debaixo do texto."""
        P = self.cfg.get('pesos', PESOS)
        cx = g['caixa']
        conta = {'linha': 0}
        b_linhas = []
        # linhas do desenho sob a tag: pelo COMPRIMENTO coberto, em alturas de
        # tag (arco tesselado em 20 pedacos pesa o mesmo que uma reta)
        # altura de REFERENCIA fixa (3 passos ~ 3 mm de papel), nao a da tag: com
        # a altura da propria tag o stub de 1 linha pagava 2,7x mais pela mesma
        # linha encostada e fugia para longe
        alt = max(self.cfg['passo'] * 3.0, EPS)
        # folga do texto ate tubo/parede (linha com largura): o texto de 1,5 mm
        # a 0,2-0,5 mm do tubo vizinho parece EM CIMA dele no papel (PH3 UNIT
        # B5, 23/10/2026). 0 = so conta o que encosta (os outros templates)
        fl = self.cfg.get('folga_linha', 0.0)
        busca = (cx[0] - fl, cx[1] - fl, cx[2] + fl, cx[3] + fl) if fl else cx
        # tag alinhada: o PROPRIO tubo (a linha que passa pela ancora) nao e
        # obstaculo — o texto corre colado nele de proposito
        proprio = meus_anc[0] if g.get('alinhada') and meus_anc else None
        for j in self.g_linhas.perto(busca):
            e = self.env_linhas[j]
            m = self.larg[j]
            if proprio is not None and m and dist_ponto_segmento(proprio[0], proprio[1], self.linhas[j]) < 1e-6:
                continue
            f = fl if m else 0.0
            if e[0] > cx[2] + f or e[2] < cx[0] - f or e[1] > cx[3] + f or e[3] < cx[1] - f:
                continue
            caixa_l = (cx[0] - m - f, cx[1] - m - f, cx[2] + m + f, cx[3] + m + f) if m else cx
            comp = comprimento_na_caixa(self.linhas[j], caixa_l)
            if comp > 0.0:
                # linha sem largura = fundo (DWG da arquitetura): o Thiago poe
                # texto sobre ela para ficar perto (29 de 49 tags que ele moveu,
                # 08/10/2026); sobre tubo/conduite, nao (1 de 49)
                peso = P['linha'] if m else P.get('linha_fundo', P['linha'])
                if self.parede[j]:
                    # texto sobre parede: evitar, mas mais barato que chamada
                    # longa a 45 para fugir dela — o vao entre paredes do
                    # banheiro (18 mm) nao cabe o texto do Pex Tee (Thiago, PH3)
                    peso = P.get('linha_parede', peso)
                b_linhas.append(peso * comp / alt * (1.0 + 2.0 * m / alt))
                conta['linha'] += 1
        return b_linhas, conta

    def _fixo_sobre(self, g, meus, meus_anc):
        """Bloco 2: chamada correndo colada numa linha do desenho."""
        P = self.cfg.get('pesos', PESOS)
        b_sobre = []
        # chamada correndo SOBRE uma linha do desenho (paralela e colada): some
        # no desenho — perna em cima do montante no corte 04 do MOTION
        tol = self.cfg.get('tol_paralela', self.cfg.get('folga_chamada', 0.0))
        peso_sobre = P.get('chamada_sobre_linha', 0.0)
        if peso_sobre and tol > 0:
            n_segs = len(g['segs'])
            for i_s, s in enumerate(g['segs']):
                # a PERNA (nao o ombro) pode correr ao lado do proprio tubo
                perna = i_s < n_segs - 1
                Ls = math.hypot(s[2] - s[0], s[3] - s[1])
                if Ls < EPS:
                    continue
                cs = (min(s[0], s[2]) - tol, min(s[1], s[3]) - tol, max(s[0], s[2]) + tol, max(s[1], s[3]) + tol)
                for j in self.g_dir[_direcao(s)].perto(cs):
                    if self.parede[j]:
                        continue    # chamada ao longo da parede continua visivel
                    # folga larga so para TUBO (linha com largura): o Thiago
                    # afastou o ombro colado no tubo; nos montantes do corte 4 mm
                    # nao cabem (o tubo corre a menos de 1" deles)
                    t_j = tol if self.larg[j] > 0 else min(tol, self.cfg.get('folga_chamada', tol))
                    # descarte barato pela caixa (a grade devolve a celula
                    # inteira; quase nenhuma linha esta a menos de t_j)
                    e = self.env_linhas[j]
                    if (e[0] > cs[2] - tol + t_j or e[2] < cs[0] + tol - t_j
                            or e[1] > cs[3] - tol + t_j or e[3] < cs[1] + tol - t_j):
                        continue
                    # tubo que sai da propria peca: so conta se a perna estiver
                    # EM CIMA dele (ao lado e o desenho do Thiago, DEM 57)
                    if perna and self.larg[j] > 0 and self._toca_ancora(j, meus_anc):
                        t_j = min(t_j, self.cfg.get('folga_chamada', 0.0) * 0.5)
                    sob = _sobreposicao_paralela(s, self.linhas[j], t_j + self.larg[j])
                    if sob > 0.0:
                        # ao lado de TUBO a perna some (caro); ao lado de frame/
                        # fundo o projeto aceita para manter 90 graus (F10: 0
                        # diagonal; a perna do cotovelo colado no montante
                        # pagava 335 e virava diagonal, 09/10/2026)
                        p_j = peso_sobre if self.larg[j] > 0 else P.get('chamada_sobre_fundo', peso_sobre)
                        b_sobre.append(p_j * sob / max(self.cfg['passo'], EPS))
        return b_sobre, {}

    def _fixo_tubos(self, g, meus, meus_anc):
        """Bloco 3: chamada cortando outro tubo."""
        P = self.cfg.get('pesos', PESOS)
        conta = {'cruza_tubo': 0}
        b_tubos = []
        # chamada ATRAVESSANDO um tubo (linha com largura) que nao e o da
        # propria tag: a Red 6" descia cortando o tubo de baixo e o Pex Tee
        # passava por cima do azul (DEM 105, 09/10/2026 — o Thiago sobe)
        peso_tubo = P.get('chamada_cruza_tubo', 0.0)
        if peso_tubo:
            for s in g['segs']:
                for j in self.g_tubos.perto(_caixa_do_segmento(s)):
                    if self.larg[j] <= 0 or not segmentos_cruzam(s, self.linhas[j]):
                        continue
                    ln = self.linhas[j]
                    if any(dist_ponto_segmento(ax, ay, ln) <= self.larg[j] + EPS for ax, ay in meus_anc):
                        continue
                    b_tubos.append(peso_tubo)
                    conta['cruza_tubo'] += 1
        return b_tubos, conta

    def _toca_ancora(self, j, ancoras):
        """Tubo j comeca ou termina na peca marcada (ponta a ate 2 passos)."""
        ln = self.linhas[j]
        lim = self.larg[j] + 2.0 * self.cfg['passo']
        for ax, ay in ancoras:
            for px, py in ((ln[0], ln[1]), (ln[2], ln[3])):
                if math.hypot(px - ax, py - ay) <= lim:
                    return True
        return False

    def custo_proprio(self, g, rot):
        """Parte do custo que so depende da propria geometria (nada da cena):
        limites, texto dentro do desenho, perna, ombro, lado, comprimento e
        dobra. Sempre soma — e o piso exato da poda em _melhor (12/10/2026: o
        piso so tinha comprimento e dobra; perna, ombro e lado ficavam de fora
        e a poda quase nao cortava — 600 mil custos para 12 tags, 5 a 10 min
        por vista no Revit)."""
        P = self.cfg.get('pesos', PESOS)
        cx = g['caixa']
        c = 0.0
        if self.limites is not None:
            L = self.limites
            if cx[0] < L[0] or cx[1] < L[1] or cx[2] > L[2] or cx[3] > L[3]:
                c += P['fora']
        # estilo margem: texto dentro do desenho
        mg = self.cfg.get('margem')
        if mg and _sobrepoe(cx, mg):
            c += P.get('dentro', P['tag'])
        # margem: perna (trecho ate o cotovelo) longa custa; o ombro e longo
        # por natureza e o comprimento total nao separa uma da outra. O Thiago
        # encurtou pernas de 29 mm para 11 mm no DEM 105 (09/10/2026)
        if mg and P.get('perna_margem'):
            perna = sum(math.hypot(s[2] - s[0], s[3] - s[1]) for s in g['segs'][:-1])
            c += P['perna_margem'] * perna / max(self.cfg['passo'], EPS)
        # margem: ombro atravessando o desenho tambem paga por mm — sem isso o
        # Pex Plug na ponta esquerda ia para a direita com 58 mm de chamada
        # tendo lugar a 12 mm (DEM 98, 09/10/2026)
        if mg and P.get('ombro_margem') and g['segs']:
            s = g['segs'][-1]
            c += P['ombro_margem'] * math.hypot(s[2] - s[0], s[3] - s[1]) / max(self.cfg['passo'], EPS)
        lado_pref = rot.get('lado_pref') or rot.get('lado_pref_suave')
        if lado_pref and g['lado'] != lado_pref:
            c += P.get('lado_errado_fraco', P.get('lado_errado', 0.0)) if rot.get('lado_fraco') \
                else P.get('lado_errado', 0.0)
        # lado livre (stub): texto do lado do conduite que chega custa a mais
        livre = rot.get('livre')
        if livre:
            meus_anc = list(g.get('ancoras', rot['ancoras']))
            ax = sum(a[0] for a in meus_anc) / len(meus_anc)
            ay = sum(a[1] for a in meus_anc) / len(meus_anc)
            if ((cx[0] + cx[2]) / 2.0 - ax) * livre[0] + ((cx[1] + cx[3]) / 2.0 - ay) * livre[1] < 0:
                c += P.get('contra_livre', 0.0)
        # estetica
        if self.cfg.get('comp_por_chamada') and g.get('comp_max') is not None:
            # tag unida (Installation Plans): o linear paga a tinta toda, o
            # quadratico so a chamada mais LONGA. Somando, a unida de dois Pex
            # Tee (20 mm cada, 40 de tinta) pagava 106 contra 22 das separadas
            # e virava duas tags; o Thiago manteve unida (PH3 B5, 27/10/2026)
            A = max(self.cfg['alcance'], EPS)
            c += P['comp'] * g['comp'] / A + P.get('comp_longo', 0.0) * max(0.0, g['comp_max'] / A - 0.6) ** 2
            c += g.get('extra', 0.0)
        else:
            c += custo_comprimento(P, g['comp'], self.cfg['alcance']) + g.get('extra', 0.0)
        c += _peso_dobra(P, g.get('angulo')) * g['dobras']
        return c


# ----------------------------------------------------------------- otimizar

def _melhor(cena, idx, rot):
    env_busca = _envelope_ancoras(rot, cena.cfg['alcance'] + rot['w'])
    viz = cena.vizinhos(env_busca)
    P = cena.cfg.get('pesos', PESOS)

    # Poda exata: os termos de conflito so SOMAM; o unico desconto e o bonus de
    # alinhamento, limitado pelo numero de vizinhas. Entao, em ordem do custo
    # proprio (piso), quando piso - bonus_max >= melhor custo, nenhuma das
    # seguintes vence — mesmo resultado da busca completa, bem mais rapido.
    bonus_max = P['alinha'] * 2
    cands = [(cena.custo_proprio(g, rot), g) for g in candidatas(rot, cena.cfg, viz)]
    cands.sort(key=lambda t: t[0])
    melhor, melhor_c = None, None
    for piso, g in cands:
        if melhor_c is not None and piso - bonus_max >= melhor_c:
            break
        # piso mais alto: + a parte fixa (em cache). A candidata que corta tubo
        # ou cai em cima de cota sai aqui sem olhar as tags postas. Folga de
        # 1e-6 para o arredondamento: a escolha continua a da busca completa
        if (cena.piso_fixo and melhor_c is not None
                and piso + cena.custo_fixo(g, rot) - bonus_max >= melhor_c + 1e-6):
            continue
        c = cena.custo(idx, g, rot, limite=melhor_c)
        if melhor_c is None or c < melhor_c:
            melhor, melhor_c = g, c
    return melhor, melhor_c


def _envelope_ancoras(rot, margem):
    pts = list(rot['ancoras'])
    for a in rot.get('alternativas') or []:
        pts.extend(a.get('ancoras') or [(a['ax'], a['ay'])])
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs) - margem, min(ys) - margem, max(xs) + margem, max(ys) + margem)


def arranjar(rotulos, cena, rodadas=4, progresso=None):
    """Poe cada rotulo na melhor posicao e depois repara os conflitos.

    1) Gulosa: primeiro os mais apertados (mais ancoras alheias por perto),
       porque sao os que tem menos opcao.
    2) Reparo: quem ficou com conflito duro (sobreposicao, cruzamento) sai da
       cena e e recolocado com todos os outros ja no lugar. Repete enquanto
       melhorar, ate 'rodadas'.
    3) Tag unida cara e desfeita (ver abaixo). ATENCAO: isso ACRESCENTA
       rotulos ao fim da lista 'rotulos'; o indice desfeito some da cena.
    Devolve {idx: geometria} — indices validos na lista 'rotulos' ja mutada.

    progresso(n, total): chamado ao longo de TODAS as fases (recomecos,
    acabamento, unioes). Pode levantar excecao para cancelar — o script
    desfaz tudo. Antes so a 1a de 6 ordens avisava: a barra chegava a 100%
    e o Revit ficava minutos parado sem sinal (auditoria 12/10/2026).
    """
    alcance = cena.cfg['alcance']
    if cena.cfg.get('alinhar_tubos') and cena.cfg.get('par_max'):
        parear_alinhados(rotulos, cena.cfg['par_max'], cena.cfg.get('par_sobre', 0.0),
                         cena.cfg.get('fila_max', 0.0))
    todas = [(i, a) for i, r in enumerate(rotulos) for a in r['ancoras']]
    g_anc = Grade(alcance)
    for k, (i, a) in enumerate(todas):
        g_anc.por(k, (a[0], a[1], a[0], a[1]))

    def aperto(i):
        env = _envelope_ancoras(rotulos[i], alcance)
        return sum(1 for k in g_anc.perto(env) if todas[k][0] != i)

    # tag de tubo alinhada primeiro: tem pouca opcao e e a principal da
    # planta; conexao e parede se arrumam em volta (Thiago, 23/10/2026)
    prima = cena.cfg.get('alinhar_tubos')
    ordem = sorted(range(len(rotulos)), key=lambda i: (not (prima and rotulos[i].get('alinhar')), -aperto(i)))
    ordens = [ordem]
    # Perto (Installation Plans) tambem, quando o template pede: a tag de
    # Pex Tee so achava lugar se a vizinha subisse — o Thiago subiu a vizinha
    # (PH3 B5, 9846752/9846750, 27/10/2026)
    n_reinicios = int(cena.cfg.get('reinicios', 0))
    if n_reinicios:
        # varias ordens de colocacao e fica a mais barata: a gulosa numa ordem
        # so travava o DEM 105 (Elbows unidos a direita, Plugs a esquerda e a
        # Red 7" sem saida a 90 graus). "Maximo de combinacoes" (Thiago,
        # 09/10/2026). Semente fixa: o mesmo desenho da o mesmo resultado.
        y = lambda i: sum(a[1] for a in rotulos[i]['ancoras']) / len(rotulos[i]['ancoras'])
        x = lambda i: sum(a[0] for a in rotulos[i]['ancoras']) / len(rotulos[i]['ancoras'])
        ordens += [sorted(ordem, key=lambda i: -y(i)), sorted(ordem, key=y), sorted(ordem, key=x)]
        sorteio = random.Random(7)
        while len(ordens) < n_reinicios:
            o = list(ordem)
            sorteio.shuffle(o)
            ordens.append(o)
        ordens = ordens[:max(1, n_reinicios)]
        if prima:
            # em toda ordem a tag de tubo alinhada continua na frente
            ordens = [sorted(o, key=lambda i: not rotulos[i].get('alinhar')) for o in ordens]
    originais = list(rotulos)
    # barra: uma fase por ordem de colocacao, + acabamento, + unioes
    n_um = max(1, len(ordem))
    fases = len(ordens) + (1 if len(ordens) > 1 else 0) + 1
    def tique(fase, n=0):
        if progresso is not None:
            progresso(fase * n_um + min(int(n), n_um), fases * n_um)
    melhor = None
    for k_ordem, ordem in enumerate(ordens):
        for i in list(cena.postos):
            cena.tirar(i)
        rotulos[:] = originais
        _colocar(rotulos, cena, ordem, rodadas, lambda n, _t, k=k_ordem: tique(k, n),
                 acabamento=len(ordens) == 1)
        if len(ordens) == 1:
            break
        nota = sum(cena.custo(i, g, rotulos[i]) for i, g in cena.postos.items())             + 1e6 * (len(rotulos) - len(cena.postos))
        if melhor is None or nota < melhor[0] - EPS:
            melhor = (nota, dict(cena.postos), list(rotulos), ordem)
    if melhor is not None:
        for i in list(cena.postos):
            cena.tirar(i)
        rotulos[:] = melhor[2]
        for i, g in melhor[1].items():
            cena.por(i, g)
        ordem = melhor[3]
        # acabamento caro uma vez so, no melhor (no DEM 51 1 do F10 o motor
        # levou 828 s com os pares dentro de cada recomeco, 09/10/2026)
        fase = len(ordens)
        tique(fase, 0)
        _recolocar_pares(rotulos, cena, tique=lambda f: tique(fase, f * n_um / 2.0))
        if cena.cfg.get('abrir_espaco'):
            _abrir_espaco(rotulos, cena, cena.cfg['abrir_espaco'],
                          tique=lambda f: tique(fase, n_um / 2.0 + f * n_um / 2.0))
        _endireitar_curtas(rotulos, cena)

    # tag unida que saiu cara (pernas longas, aperto) ou que nao achou lugar
    # vira DUAS tags (corte no maior vao) ou, em ultimo caso, tags separadas.
    # Unir e para LIMPAR o desenho; se a uniao espalha chamada pelo desenho,
    # ela perdeu o motivo de existir. Antes so havia "tudo junto ou tudo
    # solto": grupo de 4 stubs virava 4 tags (auditoria 08/10/2026).
    fator = cena.cfg.get('pesos', PESOS)['uniao_longa']
    # mesma ordem de antes (a de colocacao); depois as que nem acharam lugar
    unidas = [i for i in list(cena.postos) + [j for j in range(len(rotulos)) if j not in cena.postos]
              if len(rotulos[i]['ancoras']) > 1 and rotulos[i].get('membros')]
    for k_uni, i in enumerate(unidas):
        tique(fases - 1, k_uni * n_um / float(len(unidas)))
        rot = rotulos[i]
        g = cena.postos.get(i)
        c_uni = cena.custo(i, g, rot) if g is not None else float('inf')
        if g is not None:
            cena.tirar(i)
        opcoes = [(c_uni, None)]
        for partes in _particoes(rot):
            c, _novos = _por_partes(cena, rotulos, partes, rot.get('estilo'))
            _desfazer_partes(cena, rotulos, _novos)
            opcoes.append((c, partes))
        # a uniao so cai se custar 'fator' vezes mais que as tags SEPARADAS
        # (regra de antes — comparar com as metades desfazia unioes boas e
        # AUMENTAVA as tags, 390 -> 394 no CIQ); caindo, as metades ganham das
        # separadas se nao custarem 'fator' vezes mais que elas
        c_sep = opcoes[-1][0]
        if c_uni <= c_sep * fator:
            escolha = opcoes[0]
        elif len(opcoes) == 3 and opcoes[1][0] <= c_sep * fator:
            escolha = opcoes[1]
        else:
            escolha = opcoes[-1]
        if escolha[1] is None:
            if g is not None:
                cena.por(i, g)
        else:
            _por_partes(cena, rotulos, escolha[1], rot.get('estilo'))
    tique(fases, 0)
    return dict(cena.postos)


def _colocar(rotulos, cena, ordem, rodadas, progresso=None, acabamento=True):
    """Gulosa na ordem dada + reparo + (margem) fases de acabamento. Sem
    'acabamento', pula as fases caras (pares) — os recomecos comparam so o
    barato e o acabamento roda uma vez no melhor."""
    for n, i in enumerate(ordem):
        g, _c = _melhor(cena, i, rotulos[i])
        if g is not None:
            cena.por(i, g)
        if progresso is not None:
            progresso(n, len(ordem))

    duro = cena.cfg.get('pesos', PESOS)['cruza'] * 0.5
    for _r in range(rodadas):
        mudou = 0
        for i in ordem:
            atual = cena.postos.get(i)
            if atual is None:
                continue
            c_atual = cena.custo(i, atual, rotulos[i])
            if c_atual < duro:
                continue
            cena.tirar(i)
            g, c = _melhor(cena, i, rotulos[i])
            if g is not None and c < c_atual - EPS:
                cena.por(i, g)
                mudou += 1
            else:
                cena.por(i, atual)
        if not mudou:
            break

    if cena.cfg.get('polir'):
        # polimento: o reparo so revisita tag COM conflito; a gulosa deixa
        # tag sem conflito num lugar ruim porque o bom estava ocupado quando
        # ela foi posta (Pex Tee a 45 graus com 42 mm, o 90 de 19 mm custava
        # menos com tudo no lugar — PH3 23/10/2026). Cada tag sai e volta no
        # melhor lugar com as outras fixas, enquanto melhorar
        for _r in range(rodadas):
            mudou = 0
            for i in ordem:
                atual = cena.postos.get(i)
                if atual is None:
                    continue
                c_atual = cena.custo(i, atual, rotulos[i])
                cena.tirar(i)
                g, c = _melhor(cena, i, rotulos[i])
                if g is not None and c < c_atual - 0.5:
                    cena.por(i, g)
                    mudou += 1
                else:
                    cena.por(i, atual)
            if not mudou:
                break

    if cena.cfg.get('margem'):
        _trocar_alturas(rotulos, cena, rodadas)
        _liberar_lado(rotulos, cena)
        if acabamento:
            _recolocar_pares(rotulos, cena, tique=lambda f: progresso and progresso(len(ordem), len(ordem)))
            if cena.cfg.get('abrir_espaco'):
                _abrir_espaco(rotulos, cena, cena.cfg['abrir_espaco'],
                              tique=lambda f: progresso and progresso(len(ordem), len(ordem)))
            _endireitar_curtas(rotulos, cena)


def _refazer_na_altura(rot, g, hy, cfg):
    """A mesma tag (lado e coluna) noutra altura de ombro: melhor angulo valido."""
    attach = g['caixa'][0] if g['lado'] > 0 else g['caixa'][2]
    melhores = []
    _junta(melhores, rot, g['lado'], attach, hy, cfg['ombro_min'], cfg.get('angulos', (90,)))
    return melhores


def _trocar_alturas(rotulos, cena, rodadas):
    """Estilo margem: duas tags do MESMO lado cujas chamadas se cruzam trocam
    de altura (a de cima desce, a de baixo sobe). Com o lado fixo pelo sistema
    a colocacao gulosa deixava cruzamentos que so uma troca desfaz (DEM 105,
    09/10/2026). Fica a troca se o custo das duas cair."""
    for _r in range(rodadas):
        mudou = False
        idx = list(cena.postos)
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                i, j = idx[a], idx[b]
                gi, gj = cena.postos.get(i), cena.postos.get(j)
                if gi is None or gj is None or gi['lado'] != gj['lado']:
                    continue
                if not any(segmentos_cruzam(s, t) for s in gi['segs'] for t in gj['segs']):
                    continue
                antes = cena.custo(i, gi, rotulos[i]) + cena.custo(j, gj, rotulos[j])
                hyi = (gi['caixa'][1] + gi['caixa'][3]) / 2.0
                hyj = (gj['caixa'][1] + gj['caixa'][3]) / 2.0
                cena.tirar(i)
                cena.tirar(j)
                melhor = None
                for ni in _refazer_na_altura(rotulos[i], gi, hyj, cena.cfg):
                    for nj in _refazer_na_altura(rotulos[j], gj, hyi, cena.cfg):
                        cena.por(i, ni)
                        cena.por(j, nj)
                        c = cena.custo(i, ni, rotulos[i]) + cena.custo(j, nj, rotulos[j])
                        cena.tirar(i)
                        cena.tirar(j)
                        if melhor is None or c < melhor[0]:
                            melhor = (c, ni, nj)
                if melhor is not None and melhor[0] < antes - EPS:
                    cena.por(i, melhor[1])
                    cena.por(j, melhor[2])
                    mudou = True
                else:
                    cena.por(i, gi)
                    cena.por(j, gj)
        if not mudou:
            break


def _liberar_lado(rotulos, cena, rodadas=2):
    """Estilo margem, 2a fase: tag que AINDA cruza outra chamada, cruza um
    tubo que nao e o dela ou ficou com a perna longa demais (cfg
    'perna_libera') pode ir para o outro lado (com custo 'lado_errado') e com
    chamada inclinada (60 ou 30 graus). O lado do sistema e preferencia forte,
    nao regra absoluta — sem espaco, usa o outro lado (Thiago, 09/10/2026: no
    DEM 105 a Red 7" vai para a direita em vez de cortar o tubo de baixo, e o
    Pex Elbow sobe em vez de descer 45 mm). Duas rodadas: a tag que troca de
    lado libera espaco para as que ficaram."""
    cfg = cena.cfg
    angulos = tuple(cfg.get('angulos', (90,)))
    perna_max = cfg.get('perna_libera')
    for _r in range(rodadas):
        mudou = False
        for i in list(cena.postos):
            g = cena.postos.get(i)
            rot = rotulos[i]
            pref = rot.get('lado_pref') or rot.get('lado_pref_suave')
            if g is None or not pref:
                continue
            c_atual, conta = cena.custo(i, g, rot, detalhe=True)
            perna = sum(math.hypot(s[2] - s[0], s[3] - s[1]) for s in g['segs'][:-1])
            longa = perna_max is not None and perna > perna_max
            # conexao (lado_fraco) sempre tenta: o outro lado pode ser so mais
            # perto (Pex Plug na ponta esquerda, DEM 98)
            if not conta['cruza'] and not conta.get('cruza_tubo') and not longa                     and not rot.get('lado_fraco'):
                continue
            livre = dict(rot)
            livre['lado_pref_suave'] = pref
            livre['lado_pref'] = None
            cena.tirar(i)
            # margem: 90 e 60 so — o projeto do Thiago (F10, 46 cortes) tem 0
            # diagonal; 30 graus vinha daqui (34 de 79 diagonais, 09/10/2026)
            cfg['angulos'] = tuple(sorted(set(angulos) | set(cfg.get('angulos_libera', (90, 60, 30))),
                                          reverse=True))
            try:
                n, c_novo = _melhor(cena, i, livre)
            finally:
                cfg['angulos'] = angulos
            if n is not None and c_novo < c_atual - EPS:
                rotulos[i] = livre
                cena.por(i, n)
                mudou = True
            else:
                cena.por(i, g)
        if not mudou:
            break


def _com_problema(cena, i, g, rot):
    """Problema DURO: cruza chamada, corta tubo ou sobrepoe texto. Perna
    longa fica com a troca de lado (mais barata)."""
    _c, conta = cena.custo(i, g, rot, detalhe=True)
    return bool(conta['cruza'] or conta.get('cruza_tubo') or conta['tag'])


def _recolocar_pares(rotulos, cena, rodadas=2, tique=None):
    """Estilo margem, 3a fase: tag que ainda tem problema (cruza, corta tubo,
    perna longa) sai junto com cada vizinha da mesma coluna e as duas sao
    recolocadas nas duas ordens; fica o par mais barato. Uma tag so nao acha
    a saida quando a vizinha ocupa o lugar dela: no DEM 105 a Red 7" foi para
    a direita na altura do Pex Tee, e o Tee subiu 41 mm cortando o tubo azul —
    o Thiago pos o Tee em cima e a Red 7" embaixo (ZZ_MARGEM6 rodar,
    09/10/2026)."""
    for _r in range(rodadas):
        mudou = False
        lista = list(cena.postos)
        for n_i, i in enumerate(lista):
            if tique is not None:
                tique((_r + float(n_i) / max(1, len(lista))) / rodadas)
            gi = cena.postos.get(i)
            if gi is None or not _com_problema(cena, i, gi, rotulos[i]):
                continue
            hi = gi['caixa'][3] - gi['caixa'][1]
            for j in list(cena.postos):
                gi = cena.postos.get(i)
                gj = cena.postos.get(j)
                # vizinha de QUALQUER lado: a saida da tag pode estar ocupada
                # na outra coluna (DEM 105 com uniao de 15 mm, 09/10/2026)
                if j == i or gj is None:
                    continue
                if abs((gj['caixa'][1] + gj['caixa'][3]) - (gi['caixa'][1] + gi['caixa'][3])) / 2.0 > 3 * hi:
                    continue
                antes = cena.custo(i, gi, rotulos[i]) + cena.custo(j, gj, rotulos[j])
                cena.tirar(i)
                cena.tirar(j)
                melhor = None
                for p, q in ((i, j), (j, i)):
                    n_p, _cp = _melhor(cena, p, rotulos[p])
                    if n_p is None:
                        continue
                    cena.por(p, n_p)
                    n_q, _cq = _melhor(cena, q, rotulos[q])
                    if n_q is not None:
                        cena.por(q, n_q)
                        c = cena.custo(p, n_p, rotulos[p]) + cena.custo(q, n_q, rotulos[q])
                        cena.tirar(q)
                        if melhor is None or c < melhor[0]:
                            melhor = (c, {p: n_p, q: n_q})
                    cena.tirar(p)
                if melhor is not None and melhor[0] < antes - EPS:
                    for k, n in melhor[1].items():
                        cena.por(k, n)
                    mudou = True
                    if not _com_problema(cena, i, cena.postos[i], rotulos[i]):
                        break
                else:
                    cena.por(i, gi)
                    cena.por(j, gj)
        if not mudou:
            break


def _altura_ombro(g):
    """Altura do ombro; tag sem chamada (tubo alinhado) usa o centro do texto
    — sem isso o abrir espaco quebrava no Installation Plans (27/10/2026)."""
    if g['segs']:
        return g['segs'][-1][1]
    return (g['caixa'][1] + g['caixa'][3]) / 2.0


def _abrir_espaco(rotulos, cena, n_viz=3, tique=None):
    """Estilo margem, acabamento: tag que AINDA corta tubo ou cruza chamada
    sai junto com as n_viz vizinhas mais proximas (pela altura da ancora, de
    qualquer lado) e o grupo e recolocado — ela primeiro, depois as vizinhas
    de cima para baixo e de baixo para cima. Fica o grupo mais barato. Par
    so nao basta: no DEM 105 2 a Red 7" so desce sem cortar o Blue se o Pex
    Elbow e a Red 6" descerem juntos (ajuste do Thiago, 12/10/2026)."""
    def y_anc(k):
        return sum(a[1] for a in rotulos[k]['ancoras']) / len(rotulos[k]['ancoras'])

    lista = list(cena.postos)
    for n_i, i in enumerate(lista):
        if tique is not None:
            tique(float(n_i) / max(1, len(lista)))
        gi = cena.postos.get(i)
        if gi is None:
            continue
        _c, conta = cena.custo(i, gi, rotulos[i], detalhe=True)
        if not (conta['cruza'] or conta.get('cruza_tubo')):
            continue
        # vizinha = quem OCUPA a faixa de altura perto do ponto da tag (ombro
        # atual), nao quem tem o ponto perto: no DEM 105 2 a Red 7" precisa da
        # altura onde estao o Pex Elbow e a Red 6" da coluna da direita
        yi = y_anc(i)
        viz = sorted((k for k in cena.postos if k != i),
                     key=lambda k: abs(_altura_ombro(cena.postos[k]) - yi))[:n_viz]
        grupo = [i] + viz
        antes = dict((k, cena.postos[k]) for k in grupo)
        c_antes = sum(cena.custo(k, antes[k], rotulos[k]) for k in grupo)
        # a tag problematica pode ir para o outro lado (com a multa) e usar os
        # angulos liberados — no DEM 105 2 a Red 6" desce pela DIREITA (a
        # esquerda tem cota); na fase de liberar lado a direita ainda estava
        # ocupada
        rot_i = rotulos[i]
        pref = rot_i.get('lado_pref') or rot_i.get('lado_pref_suave')
        livre = dict(rot_i, lado_pref=None, lado_pref_suave=pref) if pref else rot_i
        rots = dict((k, rotulos[k]) for k in grupo)
        rots[i] = livre
        cfg = cena.cfg
        angulos = tuple(cfg.get('angulos', (90,)))
        cfg['angulos'] = tuple(sorted(set(angulos) | set(cfg.get('angulos_libera', (90, 60, 30))),
                                      reverse=True))
        melhor = None
        try:
            # 1o: so ela, livre de lado, com as vizinhas paradas — no DEM 15 B2L
            # o Pex Plug tinha lugar a esquerda (61) e o grupo inteiro nunca
            # testava isso (com todas fora ela escolhia a direita)
            cena.tirar(i)
            n, _c_n = _melhor(cena, i, livre)
            if n is not None:
                cena.por(i, n)
                c = cena.custo(i, n, livre) + sum(cena.custo(k, antes[k], rotulos[k]) for k in viz)
                so_ela = dict(antes)
                so_ela[i] = n
                melhor = (c, so_ela)
                cena.tirar(i)
            cena.por(i, antes[i])
            for k in grupo:
                cena.tirar(k)
            # a tag problematica em CADA posicao da fila das vizinhas (por
            # altura, nos dois sentidos): entrando primeiro no melhor lugar
            # dela, as vizinhas cruzavam (DEM 105 2, 12/10/2026)
            ordens = []
            for fila in (sorted(viz, key=y_anc, reverse=True), sorted(viz, key=y_anc)):
                for pos in range(len(fila) + 1):
                    ordens.append(fila[:pos] + [i] + fila[pos:])
            for ordem in ordens:
                postos = {}
                for k in ordem:
                    n, _cn = _melhor(cena, k, rots[k])
                    if n is None:
                        break
                    cena.por(k, n)
                    postos[k] = n
                if len(postos) == len(grupo):
                    c = sum(cena.custo(k, postos[k], rots[k]) for k in grupo)
                    if melhor is None or c < melhor[0]:
                        melhor = (c, postos)
                for k in postos:
                    cena.tirar(k)
        finally:
            cfg['angulos'] = angulos
        if melhor is not None and melhor[0] < c_antes - EPS:
            escolha = melhor[1]
            rotulos[i] = livre
        else:
            escolha = antes
        for k in grupo:
            cena.por(k, escolha[k])


_CONFLITOS = ('tag', 'cruza', 'cruza_tubo', 'chamada_tag', 'simbolo')


def _endireitar_curtas(rotulos, cena):
    """Estilo margem, acabamento: perna INCLINADA mais curta que
    cfg['perna_diag_min'] vira ortogonal na mesma altura, se isso nao cria
    conflito — inclinada curta some no papel e a seta nem aparece (o Thiago
    fez esse ajuste a mao no DEM 98, 09/10/2026). E acabamento e nao filtro de
    candidata: filtrando antes, a busca gulosa tomava outro caminho e o DEM
    105 perdia o arranjo bom."""
    d_min = cena.cfg.get('perna_diag_min')
    if not d_min:
        return
    for i in list(cena.postos):
        g = cena.postos[i]
        if g.get('angulo') in (0, 90, None):
            continue
        if not any(math.hypot(t[2] - t[0], t[3] - t[1]) < d_min for t in g['segs'][:-1]):
            continue
        hy = g['segs'][-1][1]
        _c, antes = cena.custo(i, g, rotulos[i], detalhe=True)
        cena.tirar(i)
        trocou = False
        for n in _refazer_na_altura(rotulos[i], g, hy, dict(cena.cfg, angulos=(90,))):
            _cn, depois = cena.custo(i, n, rotulos[i], detalhe=True)
            if all(depois.get(k, 0) <= antes.get(k, 0) for k in _CONFLITOS):
                cena.por(i, n)
                trocou = True
                break
        if not trocou:
            cena.por(i, g)


def _particoes(rot):
    """Como desfazer uma tag unida, da menos para a mais tags: duas metades
    (corte no maior vao, `_partir`) e depois uma por elemento."""
    membros = rot['membros']
    saida = []
    if len(membros) >= 3:
        pts = [(m['ax'], m['ay']) for m in membros]
        idx = list(range(len(membros)))
        metades = _partir(pts, idx, _arvore(pts), (len(membros) + 1) // 2, None)
        if len(metades) < len(membros):
            saida.append([[membros[j] for j in sorted(p)] for p in metades])
    saida.append([[m] for m in membros])
    return saida


def _por_partes(cena, rotulos, partes, estilo):
    """Acrescenta um rotulo por parte e poe cada um no melhor lugar. Parte sem
    lugar custa infinito — antes contava zero e a separacao 'vencia' deixando
    elemento SEM tag."""
    novos = []
    custo = 0.0
    for membros in partes:
        r = _rotulo(membros)
        if len(membros) > 1 and estilo:
            r['estilo'] = estilo
        rotulos.append(r)
        k = len(rotulos) - 1
        gm, cm = _melhor(cena, k, r)
        if gm is not None:
            cena.por(k, gm)
            custo += cm
        else:
            custo = float('inf')
        novos.append(k)
    return custo, novos


def _desfazer_partes(cena, rotulos, novos):
    for k in novos:
        if k in cena.postos:
            cena.tirar(k)
    del rotulos[len(rotulos) - len(novos):]


def auditar(rotulos, cena):
    """Conta os conflitos da cena como esta (para linha de base e pente fino)."""
    total = {'tag': 0, 'simbolo': 0, 'linha': 0, 'cruza': 0, 'chamada_tag': 0, 'cruza_tubo': 0,
             'com_conflito': 0}
    for i, g in cena.postos.items():
        _c, conta = cena.custo(i, g, rotulos[i], detalhe=True)
        for k in conta:
            total[k] += conta[k]
        if conta['tag'] or conta['cruza'] or conta['chamada_tag'] or conta['simbolo']:
            total['com_conflito'] += 1
    # tag x tag e cruzamentos foram contados dos dois lados
    total['tag'] //= 2
    total['cruza'] //= 2
    return total


# largura dos caracteres da Arial (milesimos do corpo); o resto vale 556
_ARIAL = dict(zip(u' !"#$%&\'()*+,-./0123456789:;<=>?', (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556)))
_ARIAL.update(zip(u'ABCDEFGHIJKLMNOPQRSTUVWXYZ', (
    667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667,
    778, 722, 667, 611, 722, 667, 944, 667, 667, 611)))
_ARIAL.update(zip(u'abcdefghijklmnopqrstuvwxyz', (
    556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556,
    556, 333, 500, 278, 556, 500, 722, 500, 500, 500)))


def largura_texto(s):
    return sum(_ARIAL.get(ch, 556) for ch in s)


def silhueta(texto, alinhamento):
    """Uma caixa POR LINHA do texto, em fracoes da caixa medida (x da esquerda,
    y de baixo; a linha mais larga ocupa a largura toda). Tag de 2 linhas com a
    2a curta deixa um vazio ao lado dela, e o Thiago encaixa a vizinha ali
    (ZZ_MARGEM4_DEM 105, 09/10/2026: '6"' a esquerda, 'Pex Elbow' ao lado).

    alinhamento: 'esquerda' | 'centro' | 'direita' (o label da familia). None
    quando nao ha o que ganhar (1 linha ou alinhamento desconhecido): o motor
    usa o retangulo. Linha vazia ou '()' (comentario em branco) nao aparece."""
    if alinhamento not in ('esquerda', 'centro', 'direita'):
        return None
    linhas = [l.strip() for l in (texto or u'').replace(u'\r', u'').split(u'\n')]
    linhas = [l for l in linhas if l and l != u'()']
    if len(linhas) < 2:
        return None
    larg = [largura_texto(l) for l in linhas]
    w_max = float(max(larg)) or 1.0
    n = len(linhas)
    pecas = []
    for i, w in enumerate(larg):
        f = w / w_max
        y1 = 1.0 - float(i) / n
        y0 = 1.0 - float(i + 1) / n
        if alinhamento == 'esquerda':
            x0, x1 = 0.0, f
        elif alinhamento == 'direita':
            x0, x1 = 1.0 - f, 1.0
        else:
            x0, x1 = (1.0 - f) / 2.0, (1.0 + f) / 2.0
        pecas.append((x0, y0, x1, y1))
    return pecas


def pecas_do_texto(g, folga=0.0):
    """Caixas reais do texto de uma geometria (uma por linha, ou o retangulo),
    crescidas de folga/2 de cada lado."""
    c = g['caixa']
    f = folga / 2.0
    sil = g.get('silhueta')
    if not sil:
        return [(c[0] - f, c[1] - f, c[2] + f, c[3] + f)]
    w, h = c[2] - c[0], c[3] - c[1]
    return [(c[0] + x0 * w - f, c[1] + y0 * h - f, c[0] + x1 * w + f, c[1] + y1 * h + f)
            for x0, y0, x1, y1 in sil]


def textos_sobrepoem(g, o, folga):
    """Area de texto de g (crescida da folga) sobre o texto de o; 0 se nao
    encostam. Linha contra linha quando ha silhueta."""
    if not _sobrepoe((g['caixa'][0] - folga / 2.0, g['caixa'][1] - folga / 2.0,
                      g['caixa'][2] + folga / 2.0, g['caixa'][3] + folga / 2.0), o['caixa']):
        return 0.0
    area = 0.0
    toca = False
    for a in pecas_do_texto(g, folga):
        for b in pecas_do_texto(o):
            if _sobrepoe(a, b):
                toca = True
                area += _area_sobreposta(a, b)
    return max(area, EPS) if toca else 0.0


def _segmento_no_texto(s, g):
    if not g.get('silhueta'):
        return segmento_na_caixa(s, g['caixa'])
    return any(segmento_na_caixa(s, p) for p in pecas_do_texto(g))


def regiao_do_desenho(recorte, linhas, pontos=()):
    """Estilo margem: largura do desenho REAL dentro do recorte (frame do
    vinculo, tubos, ancoras). O recorte costuma sobrar de um lado — no DEM 105
    passava 28 mm do ultimo montante e a coluna da direita ia junto; o Thiago
    a trouxe 30 mm para dentro (09/10/2026). A altura continua a do recorte."""
    x_min, y_min, x_max, y_max = recorte
    xs = []
    for l in linhas:
        x0, y0, x1, y1 = l[:4]
        if max(y0, y1) < y_min or min(y0, y1) > y_max:
            continue
        a, b = max(min(x0, x1), x_min), min(max(x0, x1), x_max)
        if b >= a:
            xs += [a, b]
    xs += [x for x, y in pontos if x_min <= x <= x_max and y_min <= y <= y_max]
    if not xs:
        return tuple(recorte)
    return (min(xs), y_min, max(xs), y_max)


def cfg_da_escala(escala, passo_mm=1.0, ombro_mm=3.0, folga_mm=0.8, alcance_mm=22.0,
                  raio_uniao_mm=8.0, perna_mm=2.0, n_ombro=6, folga_chamada_mm=0.5,
                  angulos=(90, 45)):
    """Parametros em mm de PAPEL -> pes de modelo na escala da vista."""
    k = float(escala) / 304.8
    return {'passo': passo_mm * k, 'ombro_min': ombro_mm * k, 'folga': folga_mm * k,
            'alcance': alcance_mm * k, 'raio_uniao': raio_uniao_mm * k,
            'perna_min': perna_mm * k, 'n_ombro': n_ombro,
            'folga_chamada': folga_chamada_mm * k, 'angulos': tuple(angulos),
            'pesos': dict(PESOS)}


def cfg_margem(escala, regiao, folga_mm=0.8, raio_uniao_mm=8.0):
    """Configuracao do estilo MARGEM (installation plans, cortes water supply).

    Morava no script.py; veio para ca (auditoria 12/10/2026) para a bancada
    fora do Revit usar EXATAMENTE os mesmos pesos do botao. Cada numero tem a
    calibracao de origem no comentario. regiao = (x0, y0, x1, y1) do desenho."""
    k = float(escala) / 304.8
    largura_mm = max(regiao[2] - regiao[0], regiao[3] - regiao[1]) / k
    # 90 graus e, como recurso caro, 60 (o Thiago inclinou 2 de 11 no DEM
    # 105 ajustado; com dobra60 10 a bancada usa 3)
    cfg = cfg_da_escala(escala, alcance_mm=largura_mm + 60.0, folga_mm=folga_mm,
                        raio_uniao_mm=raio_uniao_mm, angulos=(90, 60))
    P = cfg['pesos']
    # 90 graus e o padrao do projeto: no F10 (46 cortes) o original tem 0
    # diagonal e a aplicacao tinha 26%. Diagonal so quando a ortogonal
    # cortaria tubo ou cruzaria chamada; a troca de lado nao libera 30
    # (Thiago, 09/10/2026)
    P['dobra60'] = 100.0
    # perna ao lado de FRAME (montante, fundo) e aceita para manter 90 —
    # ao lado de tubo continua cara (some no desenho). Bancada F10 fora do
    # Revit, 46 cortes: diagonais 49 -> 20-27, 90 graus 54% -> 60% (=projeto)
    P['chamada_sobre_fundo'] = 1.0
    # alturas de ombro ate 80 mm das ancoras (no projeto a maior perna tem
    # 73 mm); o desenho inteiro multiplicava as candidatas
    cfg['alcance_perna'] = 80.0 * k
    cfg['angulos_libera'] = (90, 60)
    # ombro correndo paralelo a TUBO a menos de 4 mm: ele afastou (corte 04)
    cfg['tol_paralela'] = 4.0 * k
    cfg['margem'] = tuple(regiao)
    cfg['margem_gap'] = 6.0 * k
    P['chamada_sobre_linha'] = 30.0   # perna em cima do montante some
    # cortar tubo e a ultima das ultimas alternativas (Thiago, 09/10/2026):
    # acima de diagonal (40) e de ir para o outro lado (40)
    P['chamada_cruza_tubo'] = 200.0
    # varias ordens de colocacao, fica a mais barata (gulosa numa ordem so
    # travava o DEM 105); custa ~6x o tempo do motor
    cfg['reinicios'] = 6
    # a perna paga por mm (sem isso uma tag do DEM 98 subia 153 mm para nao
    # cruzar) e acima de 35 mm tambem tenta o outro lado (09/10/2026)
    P['perna_margem'] = 0.5
    cfg['perna_libera'] = 35.0 * k
    # conexao/peca: lado do sistema mais fraco, ombro paga por mm (o Pex Plug
    # do DEM 98 ia a direita com 58 mm de chamada tendo lugar a 12 mm a
    # esquerda) e perna inclinada curta vira ortogonal — abaixo de 8 mm a seta
    # some (ajuste do Thiago, 09/10/2026). 15 -> 8 (F10: lado igual ao
    # projeto 76% -> 80%, 10/10/2026)
    P['lado_errado_fraco'] = 8.0
    P['ombro_margem'] = 0.3
    cfg['perna_diag_min'] = 8.0 * k
    # chamada atravessa cota sem drama e a seta pode pegar a BORDA da peca
    # (1,6 mm), com a perna ao lado do proprio tubo (Thiago, DEM 57 Copiar 1,
    # 12/10/2026). 5 -> 15: pode passar pela cota, mas e preferivel que nao;
    # 60 invertia lado demais (F10: lado 84 -> 81%)
    P['chamada_cota'] = 15.0
    P['ponta_lateral'] = 1.0
    cfg['ponta_lateral'] = 1.6 * k
    # tag que ainda corta tubo sai com as 4 vizinhas e o grupo e
    # recolocado (DEM 105 2: a Red 7" desce sem cortar o Blue)
    cfg['abrir_espaco'] = 4
    return cfg
