# -*- coding: utf-8 -*-
"""Regras de decisao da Tags Organizadas que nao precisam do Revit.

Logica pura (sem clr/Autodesk), testada em dev-tools/tests/test_tag_regras.py.
Nasceu na auditoria de 12/10/2026: tres bugs vinham de regra DUPLICADA ou de
ordem errada entre ler e apagar — aqui cada regra mora num lugar so.
"""
import io
import json
import math
import os
import re


# ---------------------------------------------------------------- refazer

def tags_para_apagar(refs_por_tag, recriaveis):
    """Quais tags o 'Refazer' pode apagar.

    refs_por_tag: [(id_da_tag, [chave do elemento marcado, ...])].
    recriaveis: chaves que o botao VAI etiquetar de novo nesta vista.

    So apaga a tag cujas referencias o botao recria TODAS. Antes o 'Refazer'
    apagava por categoria e o botao recriava so parte (planta: Elbow/Cap de
    conexao, curva Bend, peca aninhada) — a tag manual sumia e nao voltava.
    Tag que marca um elemento recriavel e outro nao fica: nada se perde, e o
    recriavel e pulado como 'ja tem tag'."""
    saida = []
    for tid, chaves in refs_por_tag:
        chaves = list(chaves)
        if chaves and all(k in recriaveis for k in chaves):
            saida.append(tid)
    return saida


def recriaveis_sem_sobra(refs_por_tag, unidades):
    """Chaves que o 'Refazer' pode apagar sem deixar unidade sem tag.

    unidades: [(recria, gatilho)] — recria = chaves cujas tags o botao refaz
    se a unidade ficar livre (o ponto; os tubos do trecho; os retos do
    trecho de conduite); gatilho = chaves que, ainda com tag, fazem o
    levantar() seguinte pular a unidade (o trecho inteiro, conexoes
    incluidas).

    Tira a unidade em que sobra alguma tag e repete ate estabilizar. Sem
    isso, uma tag de varias referencias que sobrevive (o pente que junta
    retos de trechos diferentes, ou uma tag manual multipla) deixava um
    trecho com as tags apagadas e sem tag nova (revisao 13/10/2026)."""
    ativas = [(set(r), set(g)) for r, g in unidades]
    while True:
        chaves = set(k for r, _g in ativas for k in r)
        apagar = set(tags_para_apagar(refs_por_tag, chaves))
        ficam = set(k for tid, ks in refs_por_tag if tid not in apagar for k in ks)
        novas = [u for u in ativas if not (u[1] & ficam)]
        if len(novas) == len(ativas):
            return chaves
        ativas = novas


def parte_aceita(cat, part_type, nome_minusculo, em_planta):
    """Filtro de PartType e de familia de uma categoria do registro.

    part_type: str(MEPModel.PartType) ou None; nome_minusculo: 'familia : tipo'
    em minusculas."""
    partes = cat.get('partes_planta' if em_planta else 'partes') or cat.get('partes')
    if partes and (part_type is None or part_type not in partes):
        return False
    excluir = cat.get('excluir_familia')
    if excluir and any(x in nome_minusculo for x in excluir):
        return False
    return True


# ------------------------------------------------------------ modo automatico

def ler_pedido_auto(caminho):
    """Le o AUTO.json de uso unico e APAGA o arquivo ANTES de interpretar.

    Antes o json era lido e so depois apagado: arquivo quebrado levantava
    erro antes do remove, ficava no disco, e TODO clique seguinte no botao
    caia no modo automatico e quebrava de novo (auditoria 12/10/2026).
    Levanta ValueError com mensagem clara se o conteudo nao serve."""
    with io.open(caminho, 'rb') as f:
        dados = f.read()
    os.remove(caminho)
    # o '>' e o Out-File do PowerShell 5.1 gravam UTF-16: ler como utf-8
    # levantava erro ANTES do remove e o botao ficava preso no modo automatico
    texto = None
    for cod in ('utf-8-sig', 'utf-16'):
        try:
            texto = dados.decode(cod)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if texto is None:
        raise ValueError(u'AUTO.json com codificacao desconhecida (apagado)')
    try:
        pedido = json.loads(texto)
    except ValueError as ex:
        raise ValueError(u'AUTO.json invalido (apagado): {}'.format(ex))
    if not isinstance(pedido, dict) or not isinstance(pedido.get('vistas'), list):
        raise ValueError(u'AUTO.json sem a lista "vistas" (apagado)')
    return pedido


# ------------------------------------------------------------------ numeros

_NUMERO = re.compile(u'^(?:(\\d+)\\s+)?(\\d+\\.?\\d*|\\.\\d+)(?:/(\\d+\\.?\\d*|\\.\\d+))?$')


def ler_numero(txt, marca=None):
    """Numero > 0 digitado na janela, ou None se nao der para ler.

    Aceita decimal com ponto ou virgula, fracao ('1/32') e misto ('1 1/2').
    marca: a marca de unidade que o CAMPO aceita no fim — u'"' (campo em
    polegadas), u"'" (campo em pes) ou None (metrico ou contagem: nenhuma).
    Marca que contradiz o campo (18" no campo em pes) e recusada: antes
    virava 18 pes em silencio. Infinito e 'inf' tambem (revisao 13/10/2026)."""
    t = (txt or u'').strip().replace(u',', u'.')
    if t[-1:] in (u'"', u"'"):
        if t[-1:] != marca:
            return None
        t = t[:-1].rstrip()
    m = _NUMERO.match(t)
    if m is None or (m.group(1) and not m.group(3)):
        return None
    try:
        v = float(m.group(2)) / float(m.group(3) or 1)
    except ZeroDivisionError:
        return None
    v += int(m.group(1) or 0)
    return v if 0 < v and not math.isinf(v) else None


# ------------------------------------------------------------------ resumo

def resumo_escolha(escolha, contagens, ja=None):
    """Frase do rodape da janela: quantos elementos vao ser etiquetados e,
    com 'Refazer', quantas tags que JA existem vao ser apagadas e refeitas.

    escolha: {'categorias': {chave: {'ativo': bool}}, 'arranjo': {'refazer'}};
    contagens: {chave: sem tag}; ja: {chave: ja com tag}. Antes, com Refazer,
    a frase so contava os sem tag e dizia que 'as tags desses elementos'
    seriam apagadas — elementos sem tag (revisao 13/10/2026)."""
    n_cat = 0
    n_el = 0
    n_ja = 0
    for chave, c in escolha.get('categorias', {}).items():
        if c.get('ativo'):
            n_cat += 1
            n_el += int(contagens.get(chave) or 0)
            n_ja += int((ja or {}).get(chave) or 0)
    if not n_cat:
        return u'Nenhuma categoria marcada.'
    txt = u'{} categoria(s), {} elemento(s)/trecho(s) sem tag nesta vista.'.format(n_cat, n_el)
    if (escolha.get('arranjo') or {}).get('refazer'):
        # 'ate': tag manual que o botao nao recria (Bend, stub com Stubs
        # desligado, pente misto) segura o elemento e ele nao e refeito
        return txt + (u' Com "Refazer", até {} elemento(s)/trecho(s) que já têm tag nessas '
                      u'categorias terão a tag apagada e refeita.').format(n_ja)
    return txt + u' As tags que já existem ficam onde estão e viram obstáculo.'


def limitar_selecao(ids, maximo=100):
    """(ids a selecionar, rotulo do link) — o link do pyRevit com milhares de
    ids trava o painel de saida (mesmo limite do PipeDoctor)."""
    ids = list(ids)
    if len(ids) > maximo:
        return ids[:maximo], u'selecionar as primeiras {} de {}'.format(maximo, len(ids))
    return ids, u'selecionar {}'.format(len(ids))


# ------------------------------------------------------------------ trama

def faixa_dominante(alturas, tol):
    """Faixa (z_min, z_max) da TRAMA: a altura onde corre a maior parte dos
    tubos horizontais, +- tol.

    alturas: [(z, peso)] — z de cada tubo horizontal, peso = comprimento.
    No Installation Plans so a trama recebe tag; o que desce nas paredes
    (tubo vertical, te da descida, CPVC, misturador, caixa) fica para os
    cortes (Thiago, IP001 7 PAV, 14/10/2026: trama a 25.502 mm, tes e CPVC
    da parede a 23.4-23.8 m). None se nao ha tubo horizontal."""
    alturas = [(float(z), float(p)) for z, p in alturas if p > 0]
    if not alturas:
        return None
    melhor = None
    for z0, _p in alturas:
        perto = [(z, p) for z, p in alturas if abs(z - z0) <= tol]
        soma = sum(p for _z, p in perto)
        if melhor is None or soma > melhor[0] + 1e-9:
            melhor = (soma, perto)
    perto = melhor[1]
    centro = sum(z * p for z, p in perto) / sum(p for _z, p in perto)
    return (centro - tol, centro + tol)


def na_faixa(z, faixa):
    """True se a altura z esta na faixa (ou se nao ha faixa)."""
    return faixa is None or faixa[0] <= z <= faixa[1]


# ------------------------------------------------------- trechos em planta

def trechos_de_planta(tubos, lig2, tes, na_trama=None, instalacao=False, minimo=0.0, texto_min=0.0):
    """Quais tubos recebem tag numa PLANTA: [(tubo_escolhido, [tubos do trecho])].

    tubos: {k: {'vis': comprimento visivel na vista, 'diam': diametro}}.
    lig2: [(k1, k2)] — tubos ligados por conexao de 2 bocas (bend, luva,
          reducao) ou direto.
    tes: [[k, ...]] — tubos de cada te (3+ bocas).
    na_trama: tubos da trama (None = todos).

    Trecho = tubos ligados por conexao de 2 bocas DA MESMA BITOLA: o te
    divide e a mudanca de bitola divide (Thiago, 23/10/2026: "se a bitola
    variar, deve-se colocar uma tag").

    Sem 'instalacao' (Slab Passes etc.): trecho com comprimento visivel total
    abaixo de 'minimo' fica sem tag; a tag vai no tubo mais longo da trama.

    Com 'instalacao' (Installation Plans, PH3 UNIT B5):
    - a tag vai no tubo da trama que ENCOSTA na descida (o que alimenta o
      ponto); sem descida, no mais longo — 3 de 3 trechos do projeto;
    - ramal que vai para descida sempre recebe tag, mesmo curto (353-570 mm);
    - so cai o trecho SEM descida, mais curto que o texto ('texto_min') e com
      um vizinho de MESMA bitola do outro lado de um te — a linha continua
      igual antes ou depois ("o segmento anterior ou posterior for da mesma
      bitola"); os dois de 3/4" entre tes, 303 e 411 mm, ficaram sem tag."""
    na_trama = set(tubos) if na_trama is None else set(na_trama)
    pai = dict((k, k) for k in tubos)

    def raiz(k):
        while pai[k] != k:
            pai[k] = pai[pai[k]]
            k = pai[k]
        return k

    viz2 = dict((k, set()) for k in tubos)
    for a, b in lig2:
        if a not in tubos or b not in tubos or a == b:
            continue
        viz2[a].add(b)
        viz2[b].add(a)
        if abs(tubos[a]['diam'] - tubos[b]['diam']) < 1e-6:
            pai[raiz(a)] = raiz(b)
    tes_de = dict((k, []) for k in tubos)
    for te in tes:
        membros = [k for k in te if k in tubos]
        for k in membros:
            tes_de[k].append(membros)
    grupos = {}
    for k in sorted(tubos):
        grupos.setdefault(raiz(k), []).append(k)
    saida = []
    for g in sorted(grupos.values(), key=lambda g: min(g)):
        cand = [k for k in g if k in na_trama and tubos[k]['vis'] > 1e-9]
        if not cand:
            continue
        mais_longo = lambda ks: max(ks, key=lambda x: (tubos[x]['vis'], -x if isinstance(x, int) else 0))
        if not instalacao:
            if sum(tubos[k]['vis'] for k in g) < minimo:
                continue
            saida.append((mais_longo(cand), g))
            continue
        descida = [k for k in cand if any(o not in na_trama for o in viz2[k])]
        if not descida:
            curto = sum(tubos[k]['vis'] for k in cand) < texto_min
            diam = tubos[g[0]]['diam']
            mesma = any(abs(tubos[o]['diam'] - diam) < 1e-6
                        for k in g for te in tes_de[k] for o in te if o not in g)
            if curto and mesma:
                continue
        saida.append((mais_longo(descida or cand), g))
    return saida


# ---------------------------------------------------------------- paredes

def descidas_na_parede(a, b, meia_largura, pontos, tol=0.0):
    """Descidas (pontos XY) dentro de uma parede e onde ancorar a tag.

    a, b: pontas da linha da parede (x, y); meia_largura: metade da espessura.
    pontos: [(x, y)] das descidas (tubo vertical). Devolve (indices dentro,
    ancora (x, y) na linha da parede, na projecao da media das descidas) ou
    ([], None). Installation Plans (PH3, 23/10/2026): as 5 paredes com tag
    sao paredes WALL_ com descida dentro."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return [], None
    dentro = []
    ts = []
    for i, (px, py) in enumerate(pontos):
        t = ((px - a[0]) * dx + (py - a[1]) * dy) / L2
        if t < -1e-3 or t > 1 + 1e-3:
            continue
        qx, qy = a[0] + t * dx, a[1] + t * dy
        if math.hypot(px - qx, py - qy) <= meia_largura + tol:
            dentro.append(i)
            ts.append(t)
    if not dentro:
        return [], None
    t = min(1.0, max(0.0, sum(ts) / len(ts)))
    return dentro, (a[0] + t * dx, a[1] + t * dy)


# ------------------------------------------------- texto da tag alinhada

#: centro do texto acima da BASE do rotulo, em alturas de letra (rotulo com
#: alinhamento vertical 'base'). Medido na imagem exportada da familia
#: Ambar_US_Tag_Pipe_Segment 2026- (PH3 B8 e B5 LEFT, 26/10/2026): 1,66 mm com
#: letra de 2 mm e rotulo em 1,25; 1,65 com o rotulo em 0,0 — e o ajuste
#: manual do Thiago no tipo de 1,5 mm (1,8 / 1,0) fecha em 0,825 x 1,5 = 1,24.
#: Na girada (TagOrientation.Vertical) o texto fica 0,05 x altura mais perto
CENTRO_BASE_H = 0.825
CENTRO_BASE_V = 0.775
#: distancia padrao do eixo do tubo ao centro do texto, em alturas de letra:
#: o controle manual do Thiago da ~1,4 mm com letra de 1,5 e ~1,9 com letra de 2
DIST_EM_LETRAS = 0.95


def centro_do_texto(rotulo):
    """Onde a familia desenha o texto da tag em relacao a cabeca (mm de
    papel), pelo rotulo visivel do tipo: {'h': altura da letra, 'x', 'y':
    posicao do rotulo, 'va': 'base'|'meio'|'topo', 'ha': 'centro'|...}.

    Devolve {'centro_h', 'centro_v', 'ao_longo', 'dist', 'altura'} ou None
    quando o rotulo nao e o caso medido (so 'base' + 'centro' foi medido —
    nos outros o motor fica com o valor fixo do template, sem chute)."""
    if not rotulo or rotulo.get('va') != 'base' or rotulo.get('ha') != 'centro':
        return None
    h = float(rotulo.get('h') or 0.0)
    if h <= 0:
        return None
    y = float(rotulo.get('y') or 0.0)
    return {'centro_h': y + CENTRO_BASE_H * h, 'centro_v': y + CENTRO_BASE_V * h,
            'ao_longo': float(rotulo.get('x') or 0.0), 'dist': DIST_EM_LETRAS * h, 'altura': h}
