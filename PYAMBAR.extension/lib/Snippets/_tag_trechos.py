# -*- coding: utf-8 -*-
"""Onde vao as tags de um elemento LINEAR (conduite) — logica pura, sem Revit.

O script le do Revit, ja projetado na tela da vista (u, v em pes):
  retos    = {id: ((u0, v0), (u1, v1))}       conduites (trechos retos)
  ligacoes = [(id_a, id_b), ...]               pares ligados por conector,
                                               incluindo as conexoes (curvas)
  conexoes = set(ids)                          ids que sao conexao, nao reto

e recebe de volta as ESTACOES: onde cada tag deve ficar e, para cada uma, os
pontos alternativos ao longo do conduite (o motor `_tag_arranjo` desliza a
ponta da chamada entre eles para achar espaco livre).

REGRA (Thiago, 08/10/2026)
--------------------------
- "Um Smurf" = trecho continuo de conduite + curvas, de ponta a ponta.
- Pelo menos UMA tag por Smurf, e mais uma a cada X pes:
  n = 1 + floor(L / X), L = soma dos RETOS do trecho.
- As tags ficam espalhadas por igual ao longo do trecho: estacao i em
  (i + 0.5) * L / n.
- A ponta da chamada so cai em RETO, longe das pontas do reto (curva e caixa
  ficam livres); se o trecho so tem reto curto, usa o meio do maior.

Medido no CIQ nivel 2: 120 Smurfs, L mediano 10,8 ft; com X = 25 -> 186 tags.
"""
import math


# ------------------------------------------------------------------ trechos

def trechos(retos, ligacoes, conexoes=()):
    """Componentes conexos: listas de ids (retos e conexoes) de cada Smurf.

    Componente feito so de conexoes (sem nenhum reto) e descartado.
    """
    adj = {}
    for k in list(retos) + list(conexoes):
        adj.setdefault(k, set())
    for a, b in ligacoes:
        if a in adj and b in adj and a != b:
            adj[a].add(b)
            adj[b].add(a)
    vistos = set()
    saida = []
    for k in sorted(adj, key=str):
        if k in vistos:
            continue
        comp = []
        pilha = [k]
        vistos.add(k)
        while pilha:
            n = pilha.pop()
            comp.append(n)
            for m in sorted(adj[n], key=str):
                if m not in vistos:
                    vistos.add(m)
                    pilha.append(m)
        if any(c in retos for c in comp):
            saida.append(comp)
    return saida, adj


def ordenar(comp, adj):
    """Ordem de ponta a ponta: busca em profundidade a partir de uma PONTA
    (no com um so vizinho). Trecho com ramificacao fica na ordem da busca —
    serve para espalhar as tags, nao precisa ser um caminho perfeito."""
    dentro = set(comp)
    pontas = [c for c in comp if len(adj[c] & dentro) <= 1]
    inicio = sorted(pontas or comp, key=str)[0]
    ordem = []
    vistos = set([inicio])
    pilha = [inicio]
    while pilha:
        n = pilha.pop()
        ordem.append(n)
        for m in sorted(adj[n] & dentro, key=str, reverse=True):
            if m not in vistos:
                vistos.add(m)
                pilha.append(m)
    return ordem


def caminho(ordem, retos):
    """Retos na ordem do trecho, cada um ORIENTADO no sentido da caminhada:
    [(id, (u0, v0), (u1, v1))] — o p0 de cada reto e a ponta mais perto do
    fim do reto anterior."""
    saida = []
    fim = None
    for k in ordem:
        if k not in retos:
            continue
        a, b = retos[k]
        if fim is not None and _d(b, fim) < _d(a, fim):
            a, b = b, a
        saida.append((k, a, b))
        fim = b
    return saida


# ----------------------------------------------------------------- estacoes

def quantas_tags(comprimento, x_pes):
    """1 + floor(L / X): no minimo uma, e mais uma a cada X pes."""
    if x_pes <= 0:
        return 1
    return 1 + int(math.floor(comprimento / float(x_pes) + 1e-9))


def estacoes(comprimento, x_pes):
    """Distancias ao longo do trecho onde as tags devem ficar."""
    n = quantas_tags(comprimento, x_pes)
    return [(i + 0.5) * comprimento / n for i in range(n)]


def _faixas(cam, margem_frac=0.15, margem_max=1.0):
    """[(id, s0, s1, p0, p1, s_ini, s_fim)] — trecho util de cada reto em
    distancia acumulada (s), sem as pontas."""
    saida = []
    s = 0.0
    for k, a, b in cam:
        L = _d(a, b)
        m = min(L * margem_frac, margem_max)
        saida.append((k, s, s + L, a, b, s + m, s + L - m))
        s += L
    return saida, s


def _ponto(faixa, s):
    k, s0, s1, a, b, _i, _f = faixa
    L = s1 - s0
    t = 0.0 if L <= 0 else (s - s0) / L
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def alternativas(cam, s_ideal, janela, passo, margem_frac=0.15, margem_max=1.0):
    """Pontos possiveis para a ponta da chamada ao redor da estacao ideal.

    Varre os retos de 'passo' em 'passo' dentro de [s_ideal - janela,
    s_ideal + janela], so na parte util (sem as pontas). Se nada cair na
    janela (estacao sobre uma curva, retos curtos), devolve o meio do reto mais
    perto. Cada ponto: {'id', 'ax', 'ay', 'desvio'}.
    """
    faixas, _L = _faixas(cam, margem_frac, margem_max)
    saida = []
    for f in faixas:
        _k, _s0, _s1, _a, _b, si, sf = f
        if sf < si:
            continue
        lo = max(si, s_ideal - janela)
        hi = min(sf, s_ideal + janela)
        if hi < lo:
            continue
        n = max(1, int(math.floor((hi - lo) / passo)) + 1)
        for j in range(n):
            s = lo + j * passo if n > 1 else (lo + hi) / 2.0
            u, v = _ponto(f, s)
            saida.append({'id': f[0], 'ax': u, 'ay': v, 'desvio': abs(s - s_ideal),
                          'dir': _direcao(f)})
    if not saida and faixas:
        f = min(faixas, key=lambda f: abs((f[1] + f[2]) / 2.0 - s_ideal) - (f[2] - f[1]) * 1e-3)
        s = (f[1] + f[2]) / 2.0
        u, v = _ponto(f, s)
        saida.append({'id': f[0], 'ax': u, 'ay': v, 'desvio': abs(s - s_ideal),
                      'dir': _direcao(f)})
    return saida


def itens_lineares(retos, ligacoes, conexoes, x_pes, janela, passo, quantos=None,
                   evitar=None):
    """Tudo junto: uma entrada por tag a criar.

    quantos: {indice do trecho: n} — quantas tags individuais o trecho ainda
    precisa (o pente ja deu as outras); ausente = a regra 1 + floor(L/X).
    evitar: {indice do trecho: [s, ...]} — posicoes (distancia ao longo do
    trecho) onde ja ha tag de pente; as estacoes individuais ficam longe delas.

    Devolve [{'trecho': n, 'ax', 'ay', 'id', 'alternativas': [...]}]: (ax, ay)
    e 'id' sao o ponto ideal (a alternativa de menor desvio); o motor pode
    trocar por outra das 'alternativas'.
    """
    comps, adj = trechos(retos, ligacoes, conexoes)
    saida = []
    for n, comp in enumerate(comps):
        cam = caminho(ordenar(comp, adj), retos)
        _faixa, L = _faixas(cam)
        posicoes = estacoes(L, x_pes)
        if quantos is not None:
            k = quantos.get(n, len(posicoes))
            if k <= 0:
                continue
            longe = (evitar or {}).get(n) or []
            if longe:
                posicoes = sorted(posicoes, key=lambda s: -min(abs(s - e) for e in longe))
            posicoes = sorted(posicoes[:k])
        for s in posicoes:
            alts = alternativas(cam, s, janela, passo)
            if not alts:
                continue
            melhor = min(alts, key=lambda a: a['desvio'])
            saida.append({'trecho': n, 'ax': melhor['ax'], 'ay': melhor['ay'],
                          'id': melhor['id'], 'alternativas': alts})
    return saida


# --------------------------------------------------------------------- pentes

def pentes(retos, ligacoes, conexoes, textos, x_pes, max_pente=8, dist_max=1.0,
           ang_max=10.0, passo=1.0, janela=5.0, margem=0.5, sobreposicao=2.0):
    """Tags de TRONCO: Smurfs paralelos colados ganham tag em 'pente'.

    Aprovado pelo Thiago (08/10/2026). Uma linha perpendicular ao tronco
    atravessa os conduites — uma seta em cada — e o cotovelo fica nessa mesma
    linha, depois do ultimo; dali o ombro horizontal ate a tag. So junta texto
    100% IGUAL (3/4" e 1" no mesmo pente faz o Revit escrever '<varia>').

    1. tronco: retos de trechos diferentes, mesmo texto, paralelos (ang_max),
       a <= dist_max na perpendicular, sobrepostos >= 'sobreposicao' pes;
    2. cortes candidatos a cada 'passo' ao longo dos retos do tronco; cada
       corte pega a CADEIA continua de conduites (vao <= dist_max);
    3. guloso: o corte que atende mais trechos que ainda precisam de tag
       (1 + floor(L/X)); um trecho so ganha nova tag de pente a >= X da
       anterior;
    4. corte com mais de max_pente: dois pentes, um saindo por cada ponta;
       acima de 2 x max_pente, fica a janela central e o resto espera outro
       corte.

    textos: {id do reto: texto da tag}. Devolve (itens_pente, quantos, evitar):
    itens_pente para o motor (alternativas com 'normal' = pente); quantos =
    {trecho: tags individuais que ainda faltam}; evitar = {trecho: [s]}.
    """
    comps, adj = trechos(retos, ligacoes, conexoes)
    sen_max = math.sin(math.radians(ang_max))
    info = []          # por trecho: (caminho, faixas, L, texto)
    precisa = {}
    segs = []          # (trecho, id, a, b, dir, s0, L)
    for n, comp in enumerate(comps):
        cam = caminho(ordenar(comp, adj), retos)
        faixas, L = _faixas(cam)
        ts = [textos.get(k, u'') for k, _a, _b in cam]
        texto = max(set(ts), key=ts.count) if ts else u''
        info.append((cam, faixas, L, texto))
        precisa[n] = quantas_tags(L, x_pes)
        for f in faixas:
            k, s0, s1, a, b = f[0], f[1], f[2], f[3], f[4]
            if s1 - s0 >= 2 * margem + passo:
                segs.append((n, k, a, b, _direcao(f), s0, s1 - s0))

    # 1. retos que tem vizinho paralelo colado (fazem parte de um tronco)
    no_tronco = set()
    for i in range(len(segs)):
        ni, ki, ai, bi, di, _s0i, Li = segs[i]
        for j in range(i + 1, len(segs)):
            nj, kj, aj, bj, dj, _s0j, Lj = segs[j]
            if ni == nj or info[ni][3] != info[nj][3]:
                continue
            if abs(di[0] * dj[1] - di[1] * dj[0]) > sen_max:
                continue
            dx, dy = aj[0] - ai[0], aj[1] - ai[1]
            if abs(dx * di[1] - dy * di[0]) > dist_max:
                continue
            t0 = dx * di[0] + dy * di[1]
            t1 = (bj[0] - ai[0]) * di[0] + (bj[1] - ai[1]) * di[1]
            if min(Li, max(t0, t1)) - max(0.0, min(t0, t1)) >= sobreposicao:
                no_tronco.add(i)
                no_tronco.add(j)
    if not no_tronco:
        return [], None, None
    tronco = [segs[i] for i in sorted(no_tronco)]
    seg_por_id = dict((s[1], s) for s in tronco)

    def corte(g, s_loc, so_trechos=None):
        """Cadeia de conduites cruzada pela perpendicular em g, a s_loc do
        inicio de g: [(lambda, trecho, id, ponto, s_no_trecho)] por lambda."""
        n0, k0, a0, b0, d0, s00, L0 = g
        P = (a0[0] + d0[0] * s_loc, a0[1] + d0[1] * s_loc)
        nrm = (-d0[1], d0[0])
        melhor = {}
        for h in tronco:
            nh, kh, ah, bh, dh, s0h, Lh = h
            if info[nh][3] != info[n0][3]:
                continue
            if so_trechos is not None and nh not in so_trechos:
                continue
            if abs(d0[0] * dh[1] - d0[1] * dh[0]) > sen_max:
                continue
            den = nrm[0] * dh[1] - nrm[1] * dh[0]
            if abs(den) < 1e-9:
                continue
            lam = ((ah[0] - P[0]) * dh[1] - (ah[1] - P[1]) * dh[0]) / den
            u = ((ah[0] - P[0]) * nrm[1] - (ah[1] - P[1]) * nrm[0]) / den
            if u < margem or u > Lh - margem:
                continue
            if abs(lam) > dist_max * (2 * max_pente + 2):
                continue
            if nh not in melhor or abs(lam) < abs(melhor[nh][0]):
                pt = (P[0] + nrm[0] * lam, P[1] + nrm[1] * lam)
                melhor[nh] = (lam, nh, kh, pt, s0h + u)
        cad = sorted(melhor.values(), key=lambda x: x[0])
        if n0 not in melhor:
            return [], nrm
        # so a cadeia continua que contem o proprio g
        i0 = [c[1] for c in cad].index(n0)
        lo = hi = i0
        while lo > 0 and cad[lo][0] - cad[lo - 1][0] <= dist_max + 1e-6:
            lo -= 1
        while hi < len(cad) - 1 and cad[hi + 1][0] - cad[hi][0] <= dist_max + 1e-6:
            hi += 1
        return cad[lo:hi + 1], nrm

    # 2. cortes candidatos
    cortes = []
    for g in tronco:
        L0 = g[6]
        s = margem
        while s <= L0 - margem + 1e-9:
            cad, nrm = corte(g, s)
            if len(cad) >= 2:
                cortes.append((g, s, cad, nrm))
            s += passo

    # 3. guloso
    usados = dict((n, []) for n in range(len(comps)))
    saida = []
    evitar = {}

    def atende(cad):
        return [c for c in cad if precisa[c[1]] > 0
                and all(abs(c[4] - u) >= x_pes for u in usados[c[1]])]

    while True:
        melhor = None
        for item in cortes:
            n_at = len(atende(item[2]))
            if n_at >= 2 and (melhor is None or n_at > melhor[0]
                              or (n_at == melhor[0] and len(item[2]) > len(melhor[1][2]))):
                melhor = (n_at, item)
        if melhor is None:
            break
        # sai da lista ja: se nao virar pente (sem alternativa valida), nao
        # pode ser escolhido de novo — senao o laco nao termina
        cortes.remove(melhor[1])
        g, s_loc, cad, nrm = melhor[1]
        # 4. repartir
        if len(cad) > 2 * max_pente:
            i0 = [c[1] for c in cad].index(g[0])
            ini = max(0, min(i0 - max_pente, len(cad) - 2 * max_pente))
            cad = cad[ini:ini + 2 * max_pente]
        if len(cad) > max_pente:
            meio = _ponto_de_corte(cad, max_pente)
            partes = [(cad[:meio], ('baixo',)), (cad[meio:], ('alto',))]
        else:
            partes = [(cad, ('baixo', 'alto'))]
        for parte, pontas in partes:
            if len(parte) < 2 or not atende(parte):
                continue
            trs = set(c[1] for c in parte)
            # o corte e recalculado a partir de um reto DA PROPRIA parte (o do
            # conduite do meio) — a partir de g, a metade que nao contem g
            # nao achava nada e ficava pendente para sempre
            meio = parte[len(parte) // 2]
            g_p = seg_por_id.get(meio[2], g)
            s_p = meio[4] - g_p[5] if g_p is not g else s_loc
            alts = _alternativas_pente(corte, g_p, s_p, trs, len(parte), passo, janela,
                                       dist_max, pontas, nrm)
            if not alts:
                continue
            ideal = min(alts, key=lambda a: a['desvio'])
            saida.append({'trecho': ('pente', len(saida)), 'texto': info[g[0]][3],
                          'ax': ideal['ancoras'][0][0], 'ay': ideal['ancoras'][0][1],
                          'id': ideal['ids'][0], 'alternativas': alts, 'pente': True,
                          'feixe': len(parte)})
            for c in parte:
                if precisa[c[1]] > 0:
                    precisa[c[1]] -= 1
                usados[c[1]].append(c[4])
                evitar.setdefault(c[1], []).append(c[4])
    return saida, precisa, evitar


def _ponto_de_corte(cad, max_pente, vao_natural=1.5):
    """Indice onde a cadeia do corte se divide em dois pentes (ambos <= max).

    Dois feixes colados (vao <= dist_max) formam uma cadeia so; repartir pelo
    indice do meio jogava um Smurf de um feixe na tag do outro (Thiago,
    08/10/2026). Vao natural (>= vao_natural x a mediana) corta primeiro; sem
    ele, o mais equilibrado."""
    n = len(cad)
    lo, hi = max(1, n - max_pente), min(n - 1, max_pente)
    if lo > hi:
        return n // 2
    vaos = [cad[i][0] - cad[i - 1][0] for i in range(1, n)]
    mediana = sorted(vaos)[len(vaos) // 2]
    i = max(range(lo, hi + 1), key=lambda i: (vaos[i - 1], -abs(n - 2 * i)))
    if vaos[i - 1] >= vao_natural * mediana and vaos[i - 1] > 1e-9:
        return i
    return min(range(lo, hi + 1), key=lambda i: abs(n - 2 * i))


def _alternativas_pente(corte, g, s_loc, trechos_do_pente, n, passo, janela, dist_max, pontas,
                        nrm_ref=None):
    """O pente desliza ao longo do tronco, sempre com os MESMOS trechos.

    nrm_ref: normal do corte original. Retos paralelos podem ter sido
    desenhados em sentidos opostos; recalculado a partir de outro reto, o
    'alto' viraria 'baixo' e a metade sairia por cima da outra — orienta
    tudo pela normal original."""
    alts = []
    passos = int(janela / passo)
    for j in range(-passos, passos + 1):
        s = s_loc + j * passo
        if s < 0 or s > g[6]:
            continue
        cad, nrm = corte(g, s, so_trechos=trechos_do_pente)
        if len(cad) != n:
            continue
        if nrm_ref is not None and nrm[0] * nrm_ref[0] + nrm[1] * nrm_ref[1] < 0:
            nrm = (-nrm[0], -nrm[1])
            cad = list(reversed(cad))
        alts.append({'ids': [c[2] for c in cad], 'ancoras': [c[3] for c in cad],
                     'normal': nrm, 'pontas': pontas, 'desvio': abs(j * passo),
                     'ax': cad[0][3][0], 'ay': cad[0][3][1], 'id': cad[0][2]})
    return alts


# -------------------------------------------------------------------- feixes

def feixes(itens, dist_max=1.0, ang_max=10.0, ao_longo=1.5, max_membros=6):
    """Junta estacoes de Smurfs PARALELOS e lado a lado numa tag so.

    Combinado com o Thiago (08/10/2026): no corredor do 204 correm ~8 Smurfs
    juntos e cada um com a sua tag vira pilha de 'Smurf O3/4"' repetido. Une
    so quem e do MESMO grupo e texto, de trechos diferentes, paralelo (ate
    ang_max graus) e a ate dist_max pes de outro membro na perpendicular;
    feixe maior que max_membros e repartido.

    itens: estacoes com 'trecho', 'grupo', 'texto' e 'alternativas' (com
    'dir'). Devolve a nova lista: membros unidos viram UM item cujas
    alternativas tem 'ids'/'ancoras' (uma ponta por Smurf, alinhadas na
    perpendicular — o feixe desliza junto). Feixe sem posicao comum fica
    separado, como antes.
    """
    n = len(itens)
    sen_max = math.sin(math.radians(ang_max))
    pai = list(range(n))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    alcance = dist_max + ao_longo + 6.0
    for i in range(n):
        a = itens[i]
        for j in range(i + 1, n):
            b = itens[j]
            if a.get('trecho') == b.get('trecho') or a.get('grupo') != b.get('grupo') \
                    or a.get('texto') != b.get('texto'):
                continue
            if abs(a['ax'] - b['ax']) > alcance or abs(a['ay'] - b['ay']) > alcance:
                continue
            if _paralelos_perto(a, b, dist_max, sen_max, ao_longo):
                pai[raiz(i)] = raiz(j)

    grupos = {}
    for i in range(n):
        grupos.setdefault(raiz(i), []).append(i)

    saida = []
    for membros in grupos.values():
        if len(membros) == 1:
            saida.append(itens[membros[0]])
            continue
        for parte in _repartir([itens[i] for i in membros], max_membros):
            if len(parte) == 1:
                saida.append(parte[0])
                continue
            unido = _unir_feixe(parte, dist_max * len(parte), sen_max, ao_longo)
            if unido is None:
                saida.extend(parte)
            else:
                saida.append(unido)
    return saida


def _paralelos_perto(a, b, dist_max, sen_max, ao_longo):
    for p in a['alternativas']:
        d = p.get('dir', (1.0, 0.0))
        for q in b['alternativas']:
            e = q.get('dir', (1.0, 0.0))
            if abs(d[0] * e[1] - d[1] * e[0]) > sen_max:
                continue
            dx, dy = q['ax'] - p['ax'], q['ay'] - p['ay']
            if abs(dx * d[1] - dy * d[0]) <= dist_max and abs(dx * d[0] + dy * d[1]) <= ao_longo:
                return True
    return False


def _repartir(membros, maximo):
    """Feixe grande: ordena na perpendicular e corta em partes de 'maximo'."""
    if len(membros) <= maximo:
        return [membros]
    d = membros[0]['alternativas'][0].get('dir', (1.0, 0.0))
    ordem = sorted(membros, key=lambda m: m['ax'] * -d[1] + m['ay'] * d[0])
    return [ordem[i:i + maximo] for i in range(0, len(ordem), maximo)]


def _unir_feixe(parte, perp_max, sen_max, ao_longo):
    """Um item com alternativas do feixe inteiro, ou None se nao ha posicao
    em que todos os membros tenham ponto na mesma perpendicular."""
    semente = max(parte, key=lambda m: len(m['alternativas']))
    outros = [m for m in parte if m is not semente]
    alts = []
    for a in semente['alternativas']:
        d = a.get('dir', (1.0, 0.0))
        ids, ancoras, desvios = [a['id']], [(a['ax'], a['ay'])], [a['desvio']]
        for m in outros:
            melhor = None
            for b in m['alternativas']:
                e = b.get('dir', (1.0, 0.0))
                if abs(d[0] * e[1] - d[1] * e[0]) > sen_max:
                    continue
                dx, dy = b['ax'] - a['ax'], b['ay'] - a['ay']
                ao = abs(dx * d[0] + dy * d[1])
                if ao > ao_longo or abs(dx * d[1] - dy * d[0]) > perp_max:
                    continue
                if melhor is None or ao < melhor[0]:
                    melhor = (ao, b)
            if melhor is None:
                break
            ids.append(melhor[1]['id'])
            ancoras.append((melhor[1]['ax'], melhor[1]['ay']))
            desvios.append(melhor[1]['desvio'])
        else:
            alts.append({'ids': ids, 'ancoras': ancoras, 'desvio': sum(desvios) / len(desvios),
                         'ax': a['ax'], 'ay': a['ay'], 'id': a['id']})
    if not alts:
        return None
    unido = dict(semente)
    unido['alternativas'] = alts
    unido['feixe'] = len(parte)
    return unido


def _direcao(faixa):
    """Vetor unitario do reto (sentido da caminhada)."""
    a, b = faixa[3], faixa[4]
    L = _d(a, b)
    if L <= 1e-12:
        return (1.0, 0.0)
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])
