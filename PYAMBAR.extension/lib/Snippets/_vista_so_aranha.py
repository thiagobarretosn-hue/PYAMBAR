# -*- coding: utf-8 -*-
"""A vista de detalhe mostra a aranha e nada mais — pura, sem Revit.

Pedido do Thiago em 10/09/2026: "na criacao do detalhe so deveria aparecer a
aranha e nada mais; tudo que nao pertence a aranha nao deve aparecer — usar
ocultar na vista. Usamos algo parecido na aplicacao de mapas, pois o filtro da
vista nao supre tudo."

O modelo `ARN TYP` esconde, por filtro, os tubos que nao sao Pre Fab. Mas
filtro nao alcanca a aranha VIZINHA (tambem Pre Fab), linhas de separacao de
ambiente, marcas de outras vistas. Isso so sai elemento a elemento
(`View.HideElements`).

O QUE E DA ARANHA — medido na vista `ARN TYP #R - 02 - LEVEL 2`
-----------------------------------------------------------------
95 elementos coletados na vista. Alem das 21 pecas visiveis:

    Linha de centro   21   20 sao DEPENDENTES das pecas da #R (a linha de
                           centro de cada tubo) — ocultar apagaria o desenho
    Sistemas          21   PipingSystem, sem grafico — um deles e o proprio
                           `KIT ARN TYP #R 1`
    Circuitos          7   ElectricalSystem, sem grafico
    Vistas             1   o recorte DESTA vista (dependente dela)
    anotacoes         16   cotas e tags da propria vista

e o que realmente e de fora: a aranha vizinha `#S` (tubo e duas chapas,
agrupados), 3 linhas de separacao de ambiente. Por isso a regra mantem os
DEPENDENTES e ignora o que nao tem grafico — ocultar so pelas pecas teria
apagado as linhas de centro da propria aranha.

Quem chama monta, para cada elemento visivel, a tupla
    (id, dono_da_vista, pode_ocultar, tem_grafico)
e o conjunto do que e da aranha (pecas + dependentes + subcomponentes + os
dependentes da vista). Aqui so se decide.
"""

MANTIDO_ARANHA = 'aranha'
MANTIDO_PROPRIO = 'da vista'
MANTIDO_SEM_GRAFICO = 'sem gráfico'
MANTIDO_NAO_PODE = 'não pode ocultar'
OCULTAR = 'ocultar'


def classificar(visivel, da_aranha, vista_id):
    """O destino de UM elemento visivel."""
    eid, dono, pode, grafico = visivel
    if eid in da_aranha:
        return MANTIDO_ARANHA
    if dono is not None and dono == vista_id:
        # anotacao desta vista (cotas e tags da aranha nascem aqui)
        return MANTIDO_PROPRIO
    if not grafico:
        return MANTIDO_SEM_GRAFICO
    if not pode:
        return MANTIDO_NAO_PODE
    return OCULTAR


def ids_a_ocultar(visiveis, da_aranha, vista_id):
    """(ids, resumo) — o que ocultar e quantos ficaram por cada motivo."""
    da_aranha = set(da_aranha or ())
    ocultar = []
    resumo = {MANTIDO_ARANHA: 0, MANTIDO_PROPRIO: 0, MANTIDO_SEM_GRAFICO: 0,
              MANTIDO_NAO_PODE: 0, OCULTAR: 0}
    for visivel in visiveis or ():
        destino = classificar(visivel, da_aranha, vista_id)
        resumo[destino] += 1
        if destino == OCULTAR:
            ocultar.append(visivel[0])
    return ocultar, resumo
