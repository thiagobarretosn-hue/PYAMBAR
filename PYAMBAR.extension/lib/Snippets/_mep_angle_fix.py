# -*- coding: utf-8 -*-
"""
_mep_angle_fix.py — o que fazer quando o ramal chega num angulo sem peca.

O catalogo de juncoes e curto: no PVC DWV deste projeto so ha te de 90 e wye
de 45. Um ramal que cruza o tronco a 22,5 ou a 60 graus e geometricamente
valido e mesmo assim nao tem peca — a ferramenta recusava e contava `no_tee`,
sem dizer o que faltava.

Ha duas saidas, nesta ordem:

1. **Joelho de ajuste.** Recuar `d` ao longo do ramal ate um ponto J e sair
   de J para o tronco no angulo que a juncao exige. O joelho em J tem dobra
   exatamente ``|theta - alvo|``; se essa dobra existir na familia de curvas,
   o ramal nao precisa sair do lugar.

2. **Rotacionar o ramal.** Quando nenhuma dobra serve, so girando o tubo ate
   um angulo que tenha peca. Mexe no que o usuario desenhou, entao **exige
   autorizacao** — nunca e feito por conta propria.

Geometria do caso 1, com v = eixo do tronco e n = perpendicular no plano dos
dois tubos:

    J   = P + d*(cos T * v + sin T * n)
    w   = cos A * v + sin A * n
    J - P - t*w  paralelo a v   =>   t = d * sin T / sin A
    P'  = P + (d*cos T - t*cos A) * v

`t` e o comprimento do trecho novo e `P'` o ponto de entrada no tronco, que
anda em relacao ao cruzamento original.
"""

import math

# Tolerancia para dar um angulo por "igual" ao da peca.
#
# Com 0,5 grau um tronco com inclinacao de esgoto ja saia da conta: 1/8" por pe
# desvia 0,60 grau, entao um ramal a 90 do tubo virava 89,4 e a ferramenta
# PERGUNTAVA o que fazer, por um decimo de grau. Inclinacao e desalinhamento
# de obra sao ruido, nao intencao de projeto — perto de 90 e te, perto de 45 e
# wye, e pronto.
#
# 5 graus cobre 1/8" e 1/4" por pe (0,60 e 1,19) com folga, e ainda deixa de
# fora o que e angulo de verdade: 22,5 e 60 continuam sendo perguntados.
# Faixas de decisao — que peca o angulo do ramal PEDE.
#
# Tolerancia nao servia: ela pergunta sempre que o angulo sai do valor exato,
# e um tronco com inclinacao de esgoto ja tirava o ramal de 90 (1/8" por pe
# desvia 0,60 grau). O que decide nao e a distancia ate o valor de catalogo, e
# a INTENCAO: perto de 45 o projetista quis um wye, perto de 90 quis um te.
#
# So a faixa do meio e duvida de verdade, e ali a ferramenta pergunta.
#
# O angulo e medido entre EIXOS, sempre em [0, 90]: um ramal a 150 graus e o
# mesmo que a 30 pelo outro lado, e cai na faixa do wye.
FAIXA_WYE_ATE = 59.0     # ate aqui: wye de 45, sem perguntar
FAIXA_TE_ACIMA = 71.0    # daqui para cima: te de 90, sem perguntar
                         # entre as duas: pergunta

ANGULO_WYE = 45.0
ANGULO_TE = 90.0

TOL_GRAUS = 5.0      # casar angulo medido com angulo de catalogo
MIN_TRECHO = 0.25    # ft — trecho novo curto demais nao comporta as pecas


def peca_para(theta):
    """(angulo_da_juncao, precisa_perguntar) para um ramal que chega em ``theta``.

    Devolve (None, True) na faixa do meio, onde so o usuario sabe se quer o
    te ou o wye.
    """
    if theta < FAIXA_WYE_ATE:
        return ANGULO_WYE, False
    if theta <= FAIXA_TE_ACIMA:
        return None, True
    return ANGULO_TE, False


def dobra_necessaria(theta, alvo):
    """Dobra do joelho que leva um ramal de ``theta`` a chegar em ``alvo``."""
    return abs(theta - alvo)


def geometria(theta, alvo, recuo):
    """(comprimento_do_trecho, deslocamento_da_entrada) para o recuo dado.

    ``deslocamento`` e quanto o ponto de entrada anda ao longo do tronco em
    relacao ao cruzamento original: positivo no sentido do eixo do tronco.
    Devolve (None, None) quando o alvo e degenerado.
    """
    t_rad, a_rad = math.radians(theta), math.radians(alvo)
    if abs(math.sin(a_rad)) < 1e-9:
        return None, None
    trecho = recuo * math.sin(t_rad) / math.sin(a_rad)
    desloc = recuo * math.cos(t_rad) - trecho * math.cos(a_rad)
    return trecho, desloc


def avaliar(theta, angulos_juncao, angulos_joelho, recuo=1.0):
    """Planos possiveis para um ramal que chega em ``theta``, do melhor ao pior.

    Cada plano e um dict:
      tipo    'direto' | 'joelho' | 'rotacao'
      alvo    angulo da juncao a usar
      dobra   dobra do joelho de ajuste (0 em 'direto')
      trecho  comprimento do trecho novo, em unidades do recuo
      desloc  quanto a entrada anda no tronco
      rotacao graus a girar o ramal (so em 'rotacao')

    'direto' aparece quando o angulo ja bate com uma juncao. 'rotacao' entra
    apenas quando nenhuma dobra do catalogo resolve — e sempre por ultimo,
    porque mexe no tubo que o usuario desenhou.
    """
    # A faixa decide QUE peca o angulo pede; a lista de juncoes disponiveis
    # so confirma se ela existe no tipo de tubo. Fora da faixa do meio nao ha
    # o que perguntar — 22,5 graus e wye, 89,4 e te.
    pedida, perguntar = peca_para(theta)
    if not perguntar and pedida is not None:
        if any(abs(pedida - a) <= TOL_GRAUS for a in angulos_juncao):
            angulos_juncao = [pedida]

    planos = []
    for alvo in sorted(angulos_juncao):
        dobra = dobra_necessaria(theta, alvo)
        if dobra <= TOL_GRAUS:
            planos.append({'tipo': 'direto', 'alvo': alvo, 'dobra': 0.0,
                           'trecho': 0.0, 'desloc': 0.0, 'rotacao': 0.0})
            continue
        if not any(abs(dobra - e) <= TOL_GRAUS for e in angulos_joelho):
            continue
        trecho, desloc = geometria(theta, alvo, recuo)
        if trecho is None or trecho < MIN_TRECHO * recuo:
            continue
        planos.append({'tipo': 'joelho', 'alvo': alvo, 'dobra': dobra,
                       'trecho': trecho, 'desloc': desloc, 'rotacao': 0.0})

    # direto primeiro; depois a menor dobra, e entre iguais o menor desvio
    planos.sort(key=lambda p: (p['tipo'] != 'direto', p['dobra'],
                               abs(p['desloc'])))
    if planos:
        return planos

    # nada no catalogo resolve: so girando o proprio ramal
    for alvo in sorted(angulos_juncao, key=lambda a: abs(a - theta)):
        planos.append({'tipo': 'rotacao', 'alvo': alvo, 'dobra': 0.0,
                       'trecho': 0.0, 'desloc': 0.0,
                       'rotacao': alvo - theta})
    return planos


def descrever(plano):
    """Uma linha explicando o plano, para menu e diagnostico."""
    if plano['tipo'] == 'direto':
        return "juncao de {:g} graus serve direto".format(plano['alvo'])
    if plano['tipo'] == 'joelho':
        return ("joelho de {:g} + juncao de {:g}  (trecho de {:.2f} ft, "
                "entrada anda {:+.2f} ft)".format(
                    plano['dobra'], plano['alvo'], plano['trecho'],
                    plano['desloc']))
    return ("girar o ramal {:+.1f} graus para usar a juncao de {:g}  "
            "— MOVE o tubo desenhado".format(plano['rotacao'], plano['alvo']))


def angulos_de_juncao(pipe):
    """Angulos de ramal das juncoes configuradas no tipo do tubo.

    Le as routing preferences pelo mesmo caminho de _mep_angled_junction, que
    ja mede o angulo instanciando a familia num SubTransaction revertido.
    """
    try:
        from Autodesk.Revit.DB import RoutingPreferenceRuleGroupType
        from Snippets._mep_angled_junction import branch_angle
        from pyrevit import revit
    except Exception:
        return []
    doc = revit.doc
    achados = []
    try:
        nivel_id = pipe.ReferenceLevel.Id
    except Exception:
        nivel_id = None
    try:
        rpm = pipe.PipeType.RoutingPreferenceManager
        n = rpm.GetNumberOfRules(RoutingPreferenceRuleGroupType.Junctions)
    except Exception:
        return []
    for i in range(n):
        try:
            rule = rpm.GetRule(RoutingPreferenceRuleGroupType.Junctions, i)
            symbol = doc.GetElement(rule.MEPPartId)
            if symbol is None:
                continue
            ang = branch_angle(symbol, nivel_id)
            if ang:
                graus = round(math.degrees(ang), 1)
                if not any(abs(graus - a) <= TOL_GRAUS for a in achados):
                    achados.append(graus)
        except Exception:
            pass
    # o te de 90 nem sempre e medido pela familia: ele e o caso trivial
    if not any(abs(90.0 - a) <= TOL_GRAUS for a in achados):
        achados.append(90.0)
    return sorted(achados)


def angulos_de_joelho(pipe):
    """Dobras disponiveis na familia de curvas do tipo do tubo."""
    try:
        from Snippets._mep_offset_jog import available_angles
        return sorted(available_angles(pipe))
    except Exception:
        return []


def explicar(theta, pipe):
    """Linhas de diagnostico para um cruzamento sem peca no angulo."""
    juncoes = angulos_de_juncao(pipe)
    joelhos = angulos_de_joelho(pipe)
    linhas = ["  ramal chega a {:.1f} graus | juncoes: {} | joelhos: {}".format(
        theta, ", ".join("{:g}".format(a) for a in juncoes) or "nenhuma",
        ", ".join("{:g}".format(a) for a in joelhos) or "nenhum")]
    planos = avaliar(theta, juncoes, joelhos)
    if not planos:
        linhas.append("  nao ha juncao configurada neste tipo de tubo")
        return linhas
    for plano in planos:
        linhas.append("    - " + descrever(plano))
    return linhas
