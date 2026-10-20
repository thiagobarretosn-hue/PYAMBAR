# -*- coding: utf-8 -*-
"""Qual room vale para um elemento — as decisoes, puras.

Pedido do Thiago em 14/09/2026: no Unit Mapper, "ao inves de usarmos o sufixo
inicial, ele usar o ambiente". Estudo: docs/specs/2026-09-14-param-flow-design.md
(sinal Room).

MEDIDO NO MIIQLUX-SEW-RSR (14/09/2026, 36 rooms no host, 0 nos 5 links;
2.752 pecas com Unit ID dentro de algum room):

    criterio quando o ponto cai em 2+ rooms     Unit ID igual ao da peca
    primeiro room achado                        1.614 (59%)
    room do nivel MAIS ALTO                     2.206 (80%)   <- escolhido
    room do nivel mais baixo                    1.614 (59%)

As alturas dos rooms se sobrepunham (o do LEVEL 3 ia ate 35,29 ft e o do
LEVEL 4 comecava em 31,83) — o Thiago confirmou: ERA UM ERRO DO MODELO. Com
rooms corretos cada ponto cai num room so e o desempate nao entra; ele fica
como seguranca, e a janela AVISA quantos elementos cairam em 2+ rooms.
O offset vertical piorou o acerto (0 ft: 2.206; 2 ft: 1.701) — padrao 0.
Os 80% foram medidos COM o erro; os restantes incluem tubo passando no room
do vizinho do mesmo andar (604 x 601).
"""

#: tokens da lista "parametro do room" que nao sao parametros
PARAM_NUMERO = u'(Número)'
PARAM_NOME = u'(Nome)'


def dentro_da_caixa(ponto, minimo, maximo, folga=0.0):
    """Pre-filtro barato antes do IsPointInRoom."""
    for i in range(3):
        if ponto[i] < minimo[i] - folga or ponto[i] > maximo[i] + folga:
            return False
    return True


#: Para onde o room "cresce" com o offset — o mesmo do SyncFromRoom
#: (`probe_points`): base estendida para baixo = ponto erguido; topo estendido
#: para cima = ponto baixado. Pedido do Thiago em 16/09/2026.
DIRECAO_BASE = 'base'
DIRECAO_TOPO = 'topo'
DIRECAO_AMBOS = 'ambos'
DIRECOES = ((DIRECAO_BASE, u'Só base ↓'), (DIRECAO_TOPO, u'Só topo ↑'),
            (DIRECAO_AMBOS, u'Base e topo ↕'))
_SETAS = {DIRECAO_BASE: u'↓', DIRECAO_TOPO: u'↑', DIRECAO_AMBOS: u'↕'}
_APELIDOS = {'top': DIRECAO_TOPO, 'both': DIRECAO_AMBOS}   # config do SyncFromRoom


def normalizar_direcao(bruta):
    texto = u'{}'.format(bruta or u'').strip().lower()
    texto = _APELIDOS.get(texto, texto)
    return texto if texto in _SETAS else DIRECAO_BASE


def pontos_de_sondagem(ponto, offset_ft=0.0, direcao=DIRECAO_BASE):
    """O ponto e, com offset, o ponto erguido (base do room estendida para
    baixo — o tubo sob o piso entra no room de cima) e/ou baixado (topo
    estendido para cima)."""
    pontos = [tuple(ponto)]
    if offset_ft and offset_ft > 0:
        direcao = normalizar_direcao(direcao)
        if direcao in (DIRECAO_BASE, DIRECAO_AMBOS):
            pontos.append((ponto[0], ponto[1], ponto[2] + offset_ft))
        if direcao in (DIRECAO_TOPO, DIRECAO_AMBOS):
            pontos.append((ponto[0], ponto[1], ponto[2] - offset_ft))
    return pontos


def normalizar_offsets(bruto):
    """{chave do room: {'offset_ft': >= 0, 'direcao': ...}} — o que nao se
    entende some (config e escrita a mao as vezes)."""
    saida = {}
    if not isinstance(bruto, dict):
        return saida
    for chave, dados in bruto.items():
        chave = u'{}'.format(chave or u'').strip()
        if not chave or not isinstance(dados, dict):
            continue
        try:
            offset = float(dados.get('offset_ft'))
        except (TypeError, ValueError):
            continue
        saida[chave] = {'offset_ft': abs(offset),
                        'direcao': normalizar_direcao(dados.get('direcao'))}
    return saida


def offset_do_room(offsets, chave, padrao_ft=0.0, padrao_direcao=DIRECAO_BASE):
    """(offset_ft, direcao, proprio): o do room quando ele tem, senao o padrao."""
    proprio = (offsets or {}).get(chave) if chave else None
    if proprio:
        return proprio['offset_ft'], proprio['direcao'], True
    return (padrao_ft or 0.0), normalizar_direcao(padrao_direcao), False


def seta_da_direcao(direcao):
    return _SETAS[normalizar_direcao(direcao)]


# ── fora de room (16/09/2026) ────────────────────────────────────────────────
# Pedido do Thiago: "parametrizar o projeto todo de uma vez". Cadeia escolhida
# por ele, nesta ordem; o que nenhuma resolve cai no sufixo. Medido no MIIQLUX
# (spec Param Flow): vizinho de rede acerta o Unit ID em 93%; proximidade 93%
# a 1 ft, 86% a 3 ft, 71% a 10 ft — por isso o limite padrao e 3 ft.

FONTE_VERTICAL = u'room acima/abaixo'
FONTE_GRUPO = u'grupo'
FONTE_REDE = u'rede'
FONTE_PROXIMO = u'room mais próximo'
FONTES_AUTO = (FONTE_VERTICAL, FONTE_GRUPO, FONTE_REDE, FONTE_PROXIMO)
LIMITE_PROXIMO_PADRAO = 3.0   # pes


def distancia_vertical(z, faixa):
    baixo, alto = faixa
    if baixo <= z <= alto:
        return 0.0
    return baixo - z if z < baixo else z - alto


def escolher_na_vertical(candidatos, z):
    """Entre os rooms cuja planta contem o elemento, o mais perto em altura
    (`faixa_z`); empate fica com o do nivel mais alto, como em `escolher_room`."""
    melhor, melhor_d = None, None
    for candidato in candidatos or []:
        d = distancia_vertical(z, candidato['faixa_z'])
        if (melhor is None or d < melhor_d
                or (d == melhor_d and candidato['elevacao'] > melhor['elevacao'])):
            melhor, melhor_d = candidato, d
    return melhor


def distancia_xy_da_caixa(ponto, minimo, maximo):
    """Distancia em planta do ponto a caixa (0 dentro). Room em L conta pela
    caixa: aproximacao aceita — quem cai na caixa esta colado no room."""
    dx = max(minimo[0] - ponto[0], 0.0, ponto[0] - maximo[0])
    dy = max(minimo[1] - ponto[1], 0.0, ponto[1] - maximo[1])
    return (dx * dx + dy * dy) ** 0.5


def mais_proximo(pares, limite):
    """(distancia, item) mais perto e dentro do limite, ou (None, None)."""
    melhor = (None, None)
    for distancia, item in pares or []:
        if distancia is None or distancia > limite:
            continue
        if melhor[0] is None or distancia < melhor[0]:
            melhor = (distancia, item)
    return melhor


def unit_pela_rede(camadas):
    """`camadas`: Unit IDs dos vizinhos com room, da camada mais perto para a
    mais longe. A primeira camada com valor decide: unanime -> o valor;
    divergente -> None (a peca liga duas unidades: nao chutar)."""
    for camada in camadas or []:
        valores = set(v for v in camada if v)
        if not valores:
            continue
        return valores.pop() if len(valores) == 1 else None
    return None


def escolher_room(candidatos):
    """O room do nivel mais alto; empate fica com o primeiro. None se vazio.

    `candidatos`: dicts com 'elevacao'.
    """
    escolhido = None
    for candidato in candidatos or []:
        if escolhido is None or candidato['elevacao'] > escolhido['elevacao']:
            escolhido = candidato
    return escolhido


def unit_do_room(info, nome_param):
    """Texto do Unit ID tirado do room: parametro, numero ou nome."""
    if not info:
        return u''
    nome_param = (nome_param or u'').strip() or u'Unit ID'
    if nome_param == PARAM_NUMERO:
        valor = info.get('numero')
    elif nome_param == PARAM_NOME:
        valor = info.get('nome')
    else:
        valor = (info.get('valores') or {}).get(nome_param)
    return (u'{}'.format(valor) if valor is not None else u'').strip()
