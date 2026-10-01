# -*- coding: utf-8 -*-
"""Interferencia entre VARIOS modelos vinculados, por conta propria.

POR QUE (Thiago, 30/09/2026)
----------------------------
> "quero poder gerar o relatorio para mais de um projeto linkado ao mesmo
>  tempo... interferencias dos tubos para dutos de todos os links"

O Interference Check do Revit faz *projeto atual x UMA fonte* por execucao e
nao tem API ([[api-interferencia-vinculos]]). Aqui o par vem de qualquer
combinacao dos modelos escolhidos, numa passada so.

O QUE DECIDE O CUSTO ([[api-clash-geometrico]], medido no CIQ)
--------------------------------------------------------------
Perguntar ao Revit par a par custa 123 ms por consulta — 6 minutos num
modelo. Pegar a CAIXA de todos os elementos de uma vez custa 0,03 ms cada
(6751 elementos de 25 documentos em 140 ms) e o cruzamento aqui, em memoria,
leva 5 ms. O Revit so e chamado depois, para confirmar os candidatos com o
solido (1,3 ms cada). Dai este modulo ser PURO: ele recebe caixas ja em
coordenadas do host e devolve os pares a confirmar.

A CAIXA (o que o script monta e passa)
--------------------------------------
    {'arquivo': 'CIQ-PLB-DRAINAGE.rvt',  # onde o elemento mora
     'id': 10225063, 'uniqueId': '...', 'categoria': u'Tubulação',
     'descricao': 'PVC 3"',
     'min': (x, y, z), 'max': (x, y, z),   # JA nas coordenadas do host
     'conectados': (10225064, ...)}        # ids do MESMO arquivo

Puro: sem `clr`, sem Revit — roda em CPython, testado em
`dev-tools/tests/test_clash.py`.
"""

VERSAO = 1
SOBREPOSICAO = u'Sobreposição'
ERRO = 'erro'
#: volume de intersecao abaixo disto e encaixe de peca, nao interferencia
#: (pol³; o fitting encosta no tubo por construcao)
VOLUME_MINIMO = 0.5


#: os dois lados do cruzamento: DE (a) contra CONTRA (b)
AMBOS = ('a', 'b')


def caixa(arquivo, ident, categoria, descricao, minimo, maximo,
          unique_id='', conectados=(), lados=AMBOS):
    """Uma caixa envolvente, ja nas coordenadas do modelo anfitriao.

    `lados` diz de que lado do cruzamento o elemento entra (v2, 30/09/2026:
    "poder escolher o que x o que e melhor"). Quem esta so em 'a' nunca e
    comparado com outro 'a' — tubo x tubo nao vira achado quando o pedido e
    tubo x duto. Categoria marcada nas duas colunas fica com os dois lados.
    """
    return {'arquivo': arquivo, 'id': ident, 'uniqueId': unique_id,
            'categoria': categoria or u'Elemento', 'descricao': descricao or '',
            'min': tuple(minimo), 'max': tuple(maximo),
            'conectados': tuple(conectados or ()),
            'lados': tuple(lados or AMBOS)}


# ------------------------------------------------------------- o cruzamento

def cruzar(caixas, mesmo_modelo=True, folga=0.0):
    """Os pares cujas caixas se tocam. -> [(i, j)] com i < j na ordem dada.

    Varredura ordenada por X: a lista e percorrida uma vez e, para cada
    caixa, so as seguintes que ainda comecam antes do fim dela sao testadas.
    O que sai daqui e CANDIDATO — quem decide e o solido, depois.

    `mesmo_modelo=False` ignora pares dentro do mesmo arquivo (o Interference
    Check nativo daquele modelo sozinho ja cobre isso).
    `folga` alarga a caixa nos tres eixos (pes) — 0 = criterio do Revit.
    """
    ordem = sorted(range(len(caixas)), key=lambda i: caixas[i]['min'][0])
    pares = []
    for posicao, i in enumerate(ordem):
        a = caixas[i]
        limite = a['max'][0] + folga
        for j in ordem[posicao + 1:]:
            b = caixas[j]
            if b['min'][0] - folga > limite:
                break               # ordenado por X: daqui pra frente, nao ha
            if not mesmo_modelo and _mesmo_arquivo(a, b):
                continue
            if not casam(a, b):
                continue
            if _separadas(a, b, folga):
                continue
            pares.append((i, j) if i < j else (j, i))
    return sorted(set(pares))


def casam(a, b):
    """True se os dois estao em lados opostos do cruzamento.

    Sem lados declarados, tudo casa com tudo (o comportamento de antes).
    """
    la = a.get('lados') or AMBOS
    lb = b.get('lados') or AMBOS
    return ('a' in la and 'b' in lb) or ('b' in la and 'a' in lb)


def _separadas(a, b, folga=0.0):
    for eixo in (1, 2):             # X ja foi decidido pela varredura
        if b['min'][eixo] - folga > a['max'][eixo]:
            return True
        if b['max'][eixo] + folga < a['min'][eixo]:
            return True
    return False


def _mesmo_arquivo(a, b):
    return (a['arquivo'] or '').lower() == (b['arquivo'] or '').lower()


def conectados(a, b):
    """True se um esta ligado ao outro (tubo e o te dele).

    No mesmo modelo, cada conexao vira um par de caixas que se tocam. Sem
    este descarte o relatorio nasce com milhares de falsos: no CIQ, 7999 dos
    9385 candidatos eram do mesmo arquivo ([[api-clash-geometrico]]).
    """
    if not _mesmo_arquivo(a, b):
        return False
    return b['id'] in a['conectados'] or a['id'] in b['conectados']


def filtrar(caixas, pares):
    """Tira o que nao e interferencia de verdade. -> ([(i, j)], descartados)."""
    vale, descartados = [], 0
    for i, j in pares:
        if conectados(caixas[i], caixas[j]):
            descartados += 1
            continue
        vale.append((i, j))
    return vale, descartados


# -------------------------------------------------------------- o resultado

def _lado(cx):
    return {'vinculo': cx['arquivo'], 'categoria': cx['categoria'],
            'descricao': cx['descricao'], 'id': cx['id'],
            'uniqueId': cx.get('uniqueId', ''),
            'ponto': {'min': list(cx['min']), 'max': list(cx['max'])}}


def par_de_modelos(a, b):
    """'CIQ-PLB-SEW-RSR.rvt × MEC-UNIT 207.rvt' — o agrupamento da janela."""
    nomes = sorted([a['arquivo'] or u'(sem modelo)',
                    b['arquivo'] or u'(sem modelo)'], key=lambda n: n.lower())
    return nomes[0] if nomes[0] == nomes[1] else u'{} × {}'.format(*nomes)


def par_de_categorias(a, b):
    nomes = sorted([a['categoria'], b['categoria']], key=lambda n: n.lower())
    return nomes[0] if nomes[0] == nomes[1] else u'{} × {}'.format(*nomes)


ATENCAO = 'atencao'
SEM_SOLIDO = u'sem sólido para medir — as caixas se cruzam; conferir'


def achado(a, b, volume=None, sem_solido=False):
    """Um conflito. `volume` em pol³ (None = nao medido).

    `sem_solido` (30/09/2026): familia so com linhas nao tem solido nem em
    Fine. Antes o par sumia (virava so um numero no rodape); agora entra
    como ATENCAO — quem olha decide, a ferramenta nao esconde.
    """
    # A e o lado "Verificar estes", B o "contra estes" (01/10/2026): a
    # varredura devolve o par em qualquer ordem, e a janela agrupa
    # "Categoria A › Categoria B" ou o inverso
    if 'a' not in a.get('lados', AMBOS) and 'a' in b.get('lados', AMBOS):
        a, b = b, a
    if sem_solido:
        medida, gravidade = SEM_SOLIDO, ATENCAO
    elif volume is not None:
        medida, gravidade = u'sobreposição de {}'.format(
            volume_texto(volume)), ERRO
    else:
        medida, gravidade = u'sobreposição', ERRO
    return {'regra': par_de_categorias(a, b), 'nivel': par_de_modelos(a, b),
            'a': _lado(a), 'b': _lado(b), 'medida': medida,
            'valor': volume, 'gravidade': gravidade}


def orientar(conflito, categorias_a):
    """Relatorio de antes de 01/10: A pelo NOME da categoria escolhida em
    "Verificar estes". So troca quando so o B e de la — nos dois (tudo
    contra tudo) ou em nenhum, fica como veio. -> True se trocou.
    """
    b = conflito.get('b')
    if not b or not categorias_a:
        return False
    marcadas = set((c or u'').lower() for c in categorias_a)
    a_marcada = (conflito['a'].get('categoria') or u'').lower() in marcadas
    b_marcada = (b.get('categoria') or u'').lower() in marcadas
    if a_marcada or not b_marcada:
        return False
    conflito['a'], conflito['b'] = b, conflito['a']
    return True


def volume_texto(volume):
    if volume is None:
        return u'—'
    if volume < 1:
        return u'{:.2f} pol³'.format(volume)
    if volume < 1728:
        return u'{:.0f} pol³'.format(volume)
    return u'{:.2f} pé³'.format(volume / 1728.0)


def chave_do_achado(ach):
    """Estavel entre execucoes e independente da ordem dos lados.

    Igual ao parser do HTML do Revit: `arquivo#id` dos dois lados, ordenados.
    Reexportar nao pode renomear conflito que ja tem status.
    """
    lados = sorted(u'{}#{}'.format((lado.get('vinculo') or '').lower(),
                                   lado['id'])
                   for lado in (ach['a'], ach['b']))
    return u'|'.join(lados)


def montar_relatorio(achados, projeto, gerado_em, modelos, parametros):
    return {
        'fonte': 'clash',
        'versao': VERSAO,
        'projeto': projeto,
        'gerado_em': gerado_em,
        'lajes': list(modelos),       # a janela chama de `lajes` o escopo
        'parametros': parametros,
        'achados': [dict(a, chave=chave_do_achado(a)) for a in achados],
    }


def resumo(achados):
    """[(par de modelos, quantos)] — do maior para o menor."""
    contagem = {}
    for ach in achados:
        contagem[ach['nivel']] = contagem.get(ach['nivel'], 0) + 1
    return sorted(contagem.items(), key=lambda par: (-par[1], par[0].lower()))
