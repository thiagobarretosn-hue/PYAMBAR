# -*- coding: utf-8 -*-
"""Onde colocar a tag de um tubo horizontal — a parte que nao precisa do Revit.

Logica pura (sem clr, sem Autodesk). O script.py le a geometria e passa tuplas.

DE ONDE VEM A REGRA
-------------------
Nao e chute: sao **62 tags reais** das aranhas do `MIIQLUX-SEW-RSR - 2026`,
medidas em 08/09/2026 decompondo o vetor tag-menos-meio-do-tubo em componente
PERPENDICULAR e PARALELA ao tubo.

**Lado** — a tag vai para o lado OPOSTO ao centro da aranha: bateu em **51 de
62 (82,3%)**. Nao e 100% porque parte das tags foi movida a mao para escapar de
sobreposicao (o log do ModelLogger mostra 5 `Mover` depois de 6 `Identificador`).

**Distancia** — mediana de |perpendicular| por faixa de comprimento do tubo:

    < 0,25 ft  (n=10) -> 1,00      0,5 - 1,0 ft (n=12) -> 0,54
    0,25-0,5   (n=21) -> 0,60      >= 1,0 ft    (n=19) -> 0,50

Monotonica, e o motivo e fisico: tubo curto nao oferece espaco, entao a tag se
afasta mais. A paralela ficou perto de zero (mediana 0,18) — a tag mora no meio
do tubo.

ATE ONDE ESTA REGRA CHEGA — o numero honesto
---------------------------------------------
Rodando a regra contra as 57 tags reais e comparando com a posicao que o Thiago
de fato usou:

    lado certo ....... 78,9%      erro mediano ..... 0,41 ft
    erro <= 0,50 ft .. 32 de 57   erro so da distancia (lado dado) .. 0,34 ft

Ou seja: **a posicao exata nao e funcao deterministica da geometria.** Parte das
tags foi movida a mao para escapar de colisao, e isso nao esta na geometria do
tubo. A regra acerta a TENDENCIA, nao o ponto.

Isso e diferente do caso da ChamadaDeDetalhe, onde o angulo previsto bateu em
7 de 7. Aqui a ferramenta serve como primeira passada — poe todas as tags numa
posicao plausivel de uma vez, e sobra ajustar as que se encostarem.

Criterios de lado testados contra as mesmas 57 (o implementado venceu):

    fora do centroide dos tubos .. 78,9%   <- este
    fora do centro do plywood .... 71,9%
    sempre +Y da vista ........... 57,9%

**Nao ha deteccao de colisao entre tags.** Seria o proximo ganho real, ja que e
a causa dos ajustes manuais — mas exige medir o texto renderizado, e nao ha
ground truth para calibrar.

ARMADILHA DA API (medida, nao suposta)
--------------------------------------
`IndependentTag.Create` **nao respeita o ponto pedido** — desviou 0,15 a 0,31 ft
nos probes. Depois de criar, setar `tag.TagHeadPosition = ponto` zera o desvio.
Sem isso toda tag nasce fora do lugar.
"""
import math

#: Tolerancia para separar tubo deitado de subida. Um trecho de drenagem cai
#: 1/4" por pe e continua sendo horizontal; a subida do aparelho tem dxy ~ 0.
TOL_HORIZONTAL = 0.01

#: Distancia perpendicular por faixa de comprimento (ft) — medianas medidas.
DIST_CURTO = 1.0     # < 0,25 ft
DIST_MEDIO = 0.6     # 0,25 - 0,5
DIST_MEIO = 0.55     # 0,5 - 1,0
DIST_LONGO = 0.5     # >= 1,0

FAIXA_CURTO = 0.25
FAIXA_MEDIO = 0.5
FAIXA_MEIO = 1.0


def distancia_perpendicular(comprimento):
    """Quanto afastar a tag do eixo do tubo, em pes."""
    if comprimento < FAIXA_CURTO:
        return DIST_CURTO
    if comprimento < FAIXA_MEDIO:
        return DIST_MEDIO
    if comprimento < FAIXA_MEIO:
        return DIST_MEIO
    return DIST_LONGO


def _comprimento_xy(p0, p1):
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    return math.sqrt(dx * dx + dy * dy)


def eh_horizontal(p0, p1, tol=TOL_HORIZONTAL):
    """True para trecho deitado; False para subida de aparelho."""
    return _comprimento_xy(p0, p1) > tol


def centroide(pontos):
    """Media dos pontos, ou None se a lista e vazia."""
    if not pontos:
        return None
    n = float(len(pontos))
    return (sum(p[0] for p in pontos) / n,
            sum(p[1] for p in pontos) / n,
            sum(p[2] for p in pontos) / n)


def posicao_da_tag(p0, p1, centro_da_rede):
    """(x, y, z) da cabeca da tag, ou None se o tubo e degenerado.

    Meio do tubo, deslocado perpendicularmente para o lado oposto ao centro
    da rede, pela distancia da faixa de comprimento.
    """
    comprimento = _comprimento_xy(p0, p1)
    if comprimento <= 0:
        return None

    ux = (p1[0] - p0[0]) / comprimento
    uy = (p1[1] - p0[1]) / comprimento

    meio_x = (p0[0] + p1[0]) / 2.0
    meio_y = (p0[1] + p1[1]) / 2.0
    meio_z = (p0[2] + p1[2]) / 2.0

    # normal do tubo no plano XY
    nx, ny = -uy, ux

    sinal = 1.0
    if centro_da_rede is not None:
        # componente da normal no vetor que sai do centro em direcao ao tubo
        fora = (meio_x - centro_da_rede[0]) * nx + (meio_y - centro_da_rede[1]) * ny
        if fora < 0:
            sinal = -1.0
        # fora == 0 e degenerado (tubo passa pelo centro): fica o sinal +1,
        # que ainda tira a tag de cima do tubo

    dist = distancia_perpendicular(comprimento) * sinal
    return (meio_x + nx * dist, meio_y + ny * dist, meio_z)
