# -*- coding: utf-8 -*-
"""Qual planta abrir para a aranha, e a caixa que a envolve — puro.

Pedido do Thiago em 14/09/2026: o botao da lupa "deve abrir a vista principal
e selecionar a aranha e dar zoom"; decisao dele: a vista principal e a PLANTA
DO NIVEL da aranha, com o nome seguindo um padrao da aba Configuracao.

POR QUE NAO BASTA O NOME
------------------------
Medido no MIIQLUX-SEW-RSR - 2026 em 14/09/2026, no LEVEL 2:

    FloorPlan        02 - LEVEL 2
    EngineeringPlan  02 - LEVEL 2     <- mesmo nome, outro tipo
    FloorPlan        02 - LEVEL 1     <- nome de outro nivel, presa ao LEVEL 2
    FloorPlan        COTAS

Por isso a escolha filtra pelo NIVEL e prefere FloorPlan antes de olhar o nome.
"""

#: `{nivel}` vira o nome do nivel. O padrao medido: a planta tem o nome dele.
MARCA_NIVEL = '{nivel}'
PADRAO_PLANTA = MARCA_NIVEL
TIPO_PREFERIDO = 'FloorPlan'


def nome_esperado(padrao, nivel):
    padrao = (padrao or '').strip() or PADRAO_PLANTA
    return padrao.replace(MARCA_NIVEL, nivel or '')


def _igual(a, b):
    return (a or '').strip().lower() == (b or '').strip().lower()


def escolher_planta(candidatas, nivel, padrao=None):
    """(candidata, motivo) — ou (None, motivo).

    `candidatas`: dicts com 'nome', 'tipo' (nome do ViewType) e 'nivel' (nome
    do GenLevel); o resto (o id) volta intacto. Ordem de preferencia, sempre
    so entre as plantas DO NIVEL, FloorPlan antes das outras:
    nome do padrao > nome igual ao do nivel > a primeira em ordem alfabetica.
    """
    if not nivel:
        return None, u'não sei o nível da aranha'
    do_nivel = [c for c in candidatas or [] if _igual(c.get('nivel'), nivel)]
    if not do_nivel:
        return None, u'nenhuma planta no nível {}'.format(nivel)
    preferidas = [c for c in do_nivel if c.get('tipo') == TIPO_PREFERIDO]
    grupo = preferidas or do_nivel

    esperado = nome_esperado(padrao, nivel)
    for candidata in grupo:
        if _igual(candidata.get('nome'), esperado):
            return candidata, u'padrão "{}"'.format(esperado)
    for candidata in grupo:
        if _igual(candidata.get('nome'), nivel):
            return candidata, (u'nenhuma planta "{}": usei a com o nome do '
                               u'nível'.format(esperado))
    candidata = sorted(grupo, key=lambda c: c.get('nome') or '')[0]
    return candidata, (u'nenhuma planta "{}" nem "{}": usei "{}"'.format(
        esperado, nivel, candidata.get('nome')))


def caixa(pontos_min, pontos_max, folga=0.0):
    """((x, y, z), (x, y, z)) que envolve todas as caixas, com folga em volta.

    None sem nenhuma caixa. Em pes, como a API.
    """
    pontos_min = list(pontos_min or [])
    pontos_max = list(pontos_max or [])
    if not pontos_min or not pontos_max:
        return None
    menor = tuple(min(p[i] for p in pontos_min) - folga for i in range(3))
    maior = tuple(max(p[i] for p in pontos_max) + folga for i in range(3))
    return menor, maior
