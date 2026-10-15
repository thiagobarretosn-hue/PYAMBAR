# -*- coding: utf-8 -*-
"""Decide por qual angulo girar o crop de uma chamada de detalhe.

Logica pura (sem clr, sem Autodesk) — o script.py so le o Revit e passa numeros.

CONTEXTO (medido no MIIQLUX-SEW-RSR - 2026 em 08/09/2026)
---------------------------------------------------------
A ChamadaDeDetalhe orientava a vista pelo angulo dominante das *detail lines*
do attached detail group. Os grupos novos trocaram essas 14 linhas por uma
familia de modelo generico (`Plywood Frame`, 8 x 4 ft): o detail group passou a
ter so cotas e tags, o coletor de linhas voltou vazio e a rotacao parou de
acontecer — em silencio.

Por isso a decisao aqui e por PRIORIDADE, e sempre diz de onde veio:

    1. marcador  — a familia retangular do model group (`Plywood Frame`).
                   `LocationPoint.Rotation` == atan2(BasisX.Y, BasisX.X) em 6 de
                   6 instancias medidas, entao o angulo sai direto e exato.
    2. linhas    — o caminho antigo, que ainda vale para os grupos #I/#I2/#J.
    3. nada      — #H, #I-M e #J-M nao tem nenhuma das duas. Devolver None com
                   fonte None para a ferramenta AVISAR, nunca girar por acaso.

VALIDACAO CONTRA O JULGAMENTO HUMANO (08/09/2026)
--------------------------------------------------
O angulo previsto pelo marcador foi comparado com a rotacao do crop das sete
vistas ARN que o Thiago ja tinha girado a mao — **bateu em 7 de 7**:

    #A 1,39 | #B 38,91 | #T 27,72 | #V 0,01   (identicos)
    #C 0,05 | #D 4,20  | #G 0,00              (a mesma direcao, meia volta)

Os tres ultimos ficaram perto de -180 na mao: mesma direcao de reta, desenho
espelhado. `precisa_rotacionar` deixa esses em 0 — a v5.3 fazia igual, entao
nao e regressao; se o espelho importar, e decisao nova do usuario.
"""
import math

FONTE_MARCADOR = 'marcador'
FONTE_LINHAS = 'linhas'

#: Agrupamento de direcoes quase paralelas (~3 graus). Herdado da v5.3.
TOL_BUCKET = 0.05

#: Abaixo desta razao entre os lados a peca e quase quadrada e o "lado maior"
#: vira ruido de medicao. O Plywood Frame real e 8x4 (razao 2,0) — folga de
#: sobra. So existe para nao girar a vista por causa de meio milimetro.
RAZAO_MIN_LADO_MAIOR = 1.05

#: Comprimento minimo para uma linha entrar na conta (herdado da v5.3).
COMPRIMENTO_MIN = 0.01

#: Distancia de 0 ou de pi abaixo da qual a vista ja esta horizontal.
TOL_JA_HORIZONTAL = 0.01


def normalizar_meia_volta(angulo):
    """Devolve o angulo em [0, pi).

    Direcao de reta nao tem sentido: 30 e 210 graus sao a mesma direcao.
    """
    norm = angulo % math.pi
    if norm < 0:
        norm += math.pi
    return norm


def angulo_do_marcador(rotacao, dx_local, dy_local):
    """Angulo do lado maior de um marcador retangular, ou None se nao decide.

    `rotacao` e a rotacao da instancia; `dx_local`/`dy_local` sao as medidas da
    familia no espaco dela (bounding box do symbol). Se o lado maior for o Y
    local, o angulo do lado maior e a rotacao mais 90 graus.
    """
    if rotacao is None or not dx_local or not dy_local:
        return None
    if dx_local <= 0 or dy_local <= 0:
        return None

    maior = max(dx_local, dy_local)
    menor = min(dx_local, dy_local)
    if maior / menor < RAZAO_MIN_LADO_MAIOR:
        return None

    angulo = rotacao
    if dy_local > dx_local:
        angulo += math.pi / 2.0
    return normalizar_meia_volta(angulo)


def angulo_dominante_de_linhas(linhas):
    """Direcao que soma mais comprimento, ou None se nao ha linha util.

    `linhas` e uma lista de (angulo_em_radianos, comprimento).
    """
    buckets = []   # lista de [chave, comprimento_acumulado]

    for angulo, comprimento in linhas:
        if comprimento is None or comprimento <= COMPRIMENTO_MIN:
            continue
        norm = normalizar_meia_volta(angulo)

        alvo = None
        for par in buckets:
            diff = abs(par[0] - norm)
            if diff < TOL_BUCKET or abs(diff - math.pi) < TOL_BUCKET:
                alvo = par
                break
        if alvo is None:
            buckets.append([norm, comprimento])
        else:
            alvo[1] += comprimento

    if not buckets:
        return None

    return max(buckets, key=lambda par: par[1])[0]


def escolher_angulo(rot_marcador, dx_marcador, dy_marcador, linhas):
    """Decide o angulo e diz de onde ele veio.

    Devolve `(angulo, fonte)`. Fonte e FONTE_MARCADOR, FONTE_LINHAS ou None —
    quem chama usa a fonte para relatar por que nao girou.
    """
    angulo = angulo_do_marcador(rot_marcador, dx_marcador, dy_marcador)
    if angulo is not None:
        return angulo, FONTE_MARCADOR

    angulo = angulo_dominante_de_linhas(linhas or [])
    if angulo is not None:
        return angulo, FONTE_LINHAS

    return None, None


def precisa_rotacionar(angulo):
    """False quando nao ha angulo ou o conteudo ja esta na horizontal."""
    if angulo is None:
        return False
    return (abs(angulo) > TOL_JA_HORIZONTAL
            and abs(angulo - math.pi) > TOL_JA_HORIZONTAL)
