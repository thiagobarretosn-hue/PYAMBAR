# -*- coding: utf-8 -*-
"""Geometria pura para igualar cota e inclinacao entre tubos.

Modulo PURO (sem clr/Autodesk) - roda em CPython e IronPython 3.
Trabalha com pontos como tuplas/listas (x, y, z) em pes (unidade interna Revit).

Usado por Snippets._match_elevation_utils (camada Revit) e coberto por
dev-tools/tests/test_slope_geometry.py.

Convencoes:
- slope = dz / dxy (razao). 0.02 = 2%.
- "pivo" = extremidade do alvo mais proxima (em XY) da referencia; ela recebe
  a cota da extremidade correspondente da referencia e nao se move mais.
- O sinal da inclinacao do alvo e PRESERVADO quando o alvo ja tem inclinacao
  (o projetista ja definiu o sentido de escoamento). Se o alvo esta horizontal,
  ele passa a descer se afastando da referencia.
"""

import math

# Abaixo disto o tubo e considerado horizontal (sem sentido de escoamento).
SLOPE_ZERO_TOL = 1e-4       # razao (0.01%)

# Acima disto o tubo e considerado vertical demais para ter "uma" cota.
VERTICAL_RATIO = 3.7        # dz > 3.7 * dxy  (~15 graus da vertical)

# Deslocamento em Z abaixo do qual nao vale a pena mexer no tubo.
MOVE_TOL = 1e-4             # pes (~0.03 mm)

# Abaixo disto o tubo e degenerado: o Revit acusa "A linha e muito curta" e
# nao consegue aplicar inclinacao nele.
MIN_PIPE_LENGTH = 0.01      # pes (~3 mm)

# Divergencia entre o que gravamos e o que sobrou no modelo acima da qual o
# Revit claramente nao respeitou a inclinacao. 5e-4 (~0.03 graus) fica bem
# abaixo da menor inclinacao de projeto (1/16" por pe = 5.2e-3) e bem acima do
# ruido numerico do Revit ao regenerar (~2e-5, medido em modelo real).
SLOPE_VERIFY_TOL = 5e-4

# Vereditos de slope_verdict().
SLOPE_OK = 'ok'                  # o Revit respeitou
SLOPE_ACHATADO = 'achatado'      # pedimos inclinacao e sobrou tubo horizontal
SLOPE_INVERTIDO = 'invertido'    # o escoamento aponta para o lado errado
SLOPE_ALTERADO = 'alterado'      # sentido mantido, valor mexido

# Nao foi possivel medir (regeneracao falhou, conector invalidado). NAO e OK:
# a instrumentacao existe para acabar com falha silenciosa e nao pode ter uma.
SLOPE_INDETERMINADO = 'indeterminado'

# Estados de uma ponta de trecho. Vivem aqui (e nao em _trecho_slope_utils)
# para que decidir_ancora() seja pura e testavel sem o Revit.
PONTA_LIVRE = 'livre'          # conector aberto: nada resiste ao movimento
PONTA_ABSORVE = 'absorve'      # da em prumada: o tubo vertical estica/encurta
PONTA_RIGIDA = 'rigida'        # da em rede horizontal ou aparelho: nao cede


def horizontal_length(p0, p1):
    """Comprimento da projecao em planta."""
    return math.sqrt((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2)


def length_3d(p0, p1):
    """Comprimento real do segmento."""
    return math.sqrt((p1[0] - p0[0]) ** 2 +
                     (p1[1] - p0[1]) ** 2 +
                     (p1[2] - p0[2]) ** 2)


def is_degenerate(p0, p1, min_length=MIN_PIPE_LENGTH):
    """True se o segmento e curto demais para existir como tubo."""
    return length_3d(p0, p1) < min_length


def is_vertical(p0, p1):
    """True se o segmento e vertical ou quase (nao tem cota unica)."""
    dz = abs(p1[2] - p0[2])
    dxy = horizontal_length(p0, p1)
    if dxy < 1e-5:
        return dz > 1e-3
    return dz > VERTICAL_RATIO * dxy


def signed_slope(p0, p1):
    """Inclinacao de p0 para p1: (z1 - z0) / comprimento_horizontal.

    Positiva se sobe indo de p0 para p1. Retorna 0.0 se o segmento e vertical
    ou de comprimento horizontal nulo.
    """
    dxy = horizontal_length(p0, p1)
    if dxy < 1e-9:
        return 0.0
    return (p1[2] - p0[2]) / dxy


def slope_magnitude(p0, p1):
    """Valor absoluto da inclinacao (sem sentido)."""
    return abs(signed_slope(p0, p1))


def xy_distance(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def resolve_connect_slope(target_slope, neighbor_slopes, pipe_slope):
    """Decide qual inclinacao o tubo deve ter depois de ser conectado.

    Todos os valores sao razoes ASSINADAS na mesma convencao: positivo = sobe
    indo da extremidade que conecta para a extremidade livre.

    Args:
        target_slope: inclinacao do conector alvo (BasisZ.Z / dxy).
        neighbor_slopes: inclinacoes dos demais conectores conectados do
            fitting alvo. Apontam para dentro, por isso o sinal e invertido.
        pipe_slope: inclinacao que o tubo movido tinha ANTES da operacao.

    Returns:
        float com a inclinacao a gravar, ou None se nao ha nada a gravar.

    Ordem de prioridade:
        1. O conector alvo manda, quando ele proprio e inclinado.
        2. Joelho/tee horizontal: derivar da media dos vizinhos inclinados.
        3. Nada derivavel: PRESERVAR a inclinacao original do tubo.
           Nunca achatar um tubo inclinado so porque o fitting e horizontal.
    """
    if abs(target_slope) > SLOPE_ZERO_TOL:
        return target_slope

    uteis = [s for s in (neighbor_slopes or []) if abs(s) > SLOPE_ZERO_TOL]
    if uteis:
        return -(sum(uteis) / len(uteis))

    if abs(pipe_slope) > SLOPE_ZERO_TOL:
        return pipe_slope

    return None


def slope_verdict(intended, measured, tol=SLOPE_VERIFY_TOL):
    """Compara a inclinacao que gravamos com a que sobrou depois do Revit.

    Gravar a curva nao garante o resultado: se o fitting alvo nao aceita
    ajuste de inclinacao (conector sem Allow Slope Adjustments), o Revit
    resolve o conflito torcendo o angulo do fitting ou achatando o tubo, e
    nao avisa. Esta funcao existe para que isso deixe de ser silencioso.

    Args:
        intended: inclinacao assinada que foi gravada. None quando nao havia
            nada a gravar - nesse caso nao ha o que verificar.
        measured: inclinacao assinada remedida no modelo, mesma convencao.
        tol: divergencia tolerada.

    Returns:
        (veredito, diferenca_absoluta). Veredito e uma das constantes
        SLOPE_OK / SLOPE_ACHATADO / SLOPE_INVERTIDO / SLOPE_ALTERADO.
    """
    if intended is None:
        return SLOPE_OK, 0.0

    diff = abs(measured - intended)
    if diff <= tol:
        return SLOPE_OK, diff

    queriamos_inclinado = abs(intended) > SLOPE_ZERO_TOL
    sobrou_inclinado = abs(measured) > SLOPE_ZERO_TOL

    if queriamos_inclinado and not sobrou_inclinado:
        return SLOPE_ACHATADO, diff

    if queriamos_inclinado and sobrou_inclinado and intended * measured < 0:
        return SLOPE_INVERTIDO, diff

    return SLOPE_ALTERADO, diff


def decidir_ancora(estado_ini, estado_fim, z_ini, z_fim, n_pontos,
                   permitir_travado=False):
    """Qual ponta do trecho fica parada. Puro: recebe estados ja classificados.

    A ancora e a ponta que NAO pode se mover. Entre pontas igualmente moveis
    vence a de menor cota — numa rede por gravidade, a jusante.

    Trecho travado nas duas pontas: por padrao recusa (era o unico
    comportamento ate agora). Com permitir_travado=True, ancora mesmo assim na
    jusante e deixa a montante ser empurrada. Numa rede por gravidade isso e o
    fisicamente correto: o coletor nao se mexe, e os aparelhos a montante tem
    folga vertical. Quem chama deve mostrar ao usuario o que sera arrastado
    ANTES de passar True.

    Returns:
        (indice_do_ponto_ancora, motivo) ou (None, motivo_da_recusa).
    """
    ultimo = n_pontos - 1
    travado_ini = estado_ini == PONTA_RIGIDA
    travado_fim = estado_fim == PONTA_RIGIDA

    if travado_ini and travado_fim:
        if not permitir_travado:
            return None, ("Trecho travado nas duas pontas — nada pode ceder. "
                          "Solte uma ponta ou ajuste a prumada antes.")
        if z_ini <= z_fim:
            return 0, "ancora a jusante (inicio); a montante sera empurrada"
        return ultimo, "ancora a jusante (fim); a montante sera empurrada"

    if travado_ini:
        return 0, "ancora na ponta travada (inicio)"
    if travado_fim:
        return ultimo, "ancora na ponta travada (fim)"

    if z_ini <= z_fim:
        return 0, "ancora a jusante (ponta mais baixa)"
    return ultimo, "ancora a jusante (ponta mais baixa)"


def oriented_slope(p0, p1):
    """Inclinacao assinada com sentido ESTAVEL, independente da ordem dos pontos.

    signed_slope() depende de quem e p0. O Revit troca a ordem dos endpoints ao
    reconectar (visto em log real: o mesmo tubo passou de [lig/-0.011, livre]
    para [lig/+0.011, lig]), entao comparar antes/depois com signed_slope
    acusaria INVERTIDO onde nada girou.

    Aqui a curva e sempre orientada do extremo de menor (x, y) para o maior,
    o que da um sinal reproduzivel para o mesmo tubo fisico.
    """
    dxy = horizontal_length(p0, p1)
    if dxy < 1e-9:
        return 0.0
    a, b = p0, p1
    if (p0[0], p0[1]) > (p1[0], p1[1]):
        a, b = p1, p0
    return (b[2] - a[2]) / dxy


def describe_network_change(item):
    """Frase para um tubo VIZINHO que mudou de inclinacao, ou ''.

    Diferente de describe_slope_report: aqui nao pedimos nada a este tubo, ele
    foi arrastado pela operacao. Por isso o texto fala de mudanca, nao de
    pedido nao atendido.
    """
    if not item or item.get('verdict') == SLOPE_OK:
        return ""
    rotulo = {SLOPE_ACHATADO: "inclinacao PERDIDA (ficou horizontal)",
              SLOPE_INVERTIDO: "inclinacao INVERTIDA (escoamento ao contrario)",
              SLOPE_ALTERADO: "inclinacao ALTERADA",
              SLOPE_INDETERMINADO: "nao foi possivel remedir"}
    return "tubo {}: {} — antes {:.4f}, agora {:.4f}".format(
        item.get('id', '?'), rotulo.get(item.get('verdict'), item.get('verdict')),
        item.get('before') or 0.0, item.get('after') or 0.0)


def describe_slope_report(report):
    """Frase curta para o usuario, ou '' quando a inclinacao sobreviveu.

    Puro de proposito: a formatacao do aviso e a parte que mais muda e a que
    mais erra, entao fica aqui onde da para testar sem o Revit.

    Distingue quem falhou. Se 'applied' e False, a inclinacao nunca chegou a
    ser gravada (tubo curto demais, geometria degenerada) - a culpa e nossa e
    a mensagem NAO pode acusar o Revit.
    """
    if not report or report.get('verdict') == SLOPE_OK:
        return ""

    if report.get('verdict') == SLOPE_INDETERMINADO:
        return ("nao foi possivel verificar a inclinacao depois da conexao - "
                "confira este tubo a mao")

    if not report.get('applied', True):
        return ("inclinacao nao foi gravada (tubo curto demais ou geometria "
                "degenerada): pedimos {:.4f}, sobrou {:.4f}".format(
                    report.get('intended') or 0.0,
                    report.get('measured') or 0.0))

    rotulo = {SLOPE_ACHATADO: "inclinacao PERDIDA (tubo ficou horizontal)",
              SLOPE_INVERTIDO: "inclinacao INVERTIDA (escoamento ao contrario)",
              SLOPE_ALTERADO: "inclinacao ALTERADA pelo Revit"}
    msg = rotulo.get(report['verdict'], report['verdict'])
    msg += ": pedimos {:.4f}, sobrou {:.4f}".format(
        report.get('intended') or 0.0, report.get('measured') or 0.0)
    if report.get('allows_slope') is False:
        msg += " - o fitting alvo nao aceita ajuste de inclinacao"
    return msg


def closest_endpoints(ref_pts, tgt_pts):
    """Par de extremidades mais proximas em planta.

    Retorna (i_ref, i_tgt) - indices 0/1 em ref_pts e tgt_pts.
    """
    best = None
    for i in (0, 1):
        for j in (0, 1):
            d = xy_distance(ref_pts[i], tgt_pts[j])
            if best is None or d < best[0]:
                best = (d, i, j)
    return best[1], best[2]


# Veredito de um trecho contra o alvo da bitola.
DESVIO_OK = 'ok'
DESVIO_ABAIXO = 'abaixo'      # nao escoa - e o erro que importa
DESVIO_ACIMA = 'acima'        # excesso: residuo de fitting rolado, informativo


def classificar_desvio(atual, alvo, tolerancia_pct):
    """Compara a inclinacao medida com o alvo da bitola.

    Regra unica do projeto — usada pelo check do Pipe Doctor e pelo lote do
    Inclinar Trecho, para o relatorio e a correcao nunca discordarem.

    Args:
        atual: inclinacao medida (razao dz/dxy, sem sinal).
        alvo: inclinacao alvo da bitola (razao).
        tolerancia_pct: folga aceita, em % do alvo.

    Returns:
        DESVIO_OK, DESVIO_ABAIXO ou DESVIO_ACIMA.
    """
    if alvo <= 0:
        return DESVIO_OK
    desvio_pct = (atual - alvo) / alvo * 100.0
    if abs(desvio_pct) <= tolerancia_pct:
        return DESVIO_OK
    return DESVIO_ABAIXO if desvio_pct < 0 else DESVIO_ACIMA


def plan_trecho_z(pontos, ancora_idx, alvo):
    """Novas cotas de uma polilinha de trecho, com a ancora parada.

    A ancora e a extremidade a JUSANTE (ligacao no coletor). Ela nao se move e
    o resto do trecho SOBE, ganhando `alvo` de inclinacao por unidade de
    comprimento horizontal DESENVOLVIDO — somado ao longo do percurso, nao em
    linha reta. Curvas em planta e o salto sobre cada fitting entram na conta.

    Args:
        pontos: lista de (x, y, z) na ordem do percurso.
        ancora_idx: indice da extremidade fixa (0 ou -1 / len-1).
        alvo: inclinacao alvo como razao (0.0208333 = 1/4"/ft).

    Returns:
        Lista de novas cotas Z, na mesma ordem de `pontos`.

    Levanta ValueError se a polilinha tem menos de 2 pontos ou nao tem
    comprimento horizontal.
    """
    if len(pontos) < 2:
        raise ValueError("Trecho precisa de pelo menos 2 pontos")

    ancora = ancora_idx % len(pontos)

    # Distancia horizontal desenvolvida de cada ponto ate a ancora.
    acumulado = [0.0] * len(pontos)
    for i in range(ancora + 1, len(pontos)):
        acumulado[i] = acumulado[i - 1] + horizontal_length(pontos[i - 1], pontos[i])
    for i in range(ancora - 1, -1, -1):
        acumulado[i] = acumulado[i + 1] + horizontal_length(pontos[i + 1], pontos[i])

    if max(acumulado) < 1e-9:
        raise ValueError("Trecho sem comprimento horizontal")

    z_ancora = pontos[ancora][2]
    return [z_ancora + alvo * d for d in acumulado]


def plan_new_z(ref_pts, tgt_pts):
    """Calcula as cotas que o tubo alvo deve assumir.

    ref_pts / tgt_pts: ((x, y, z), (x, y, z)) na ordem da curva (endpoint 0, 1).

    Retorna dict:
        new_z      -> (z0, z1) novas cotas, na MESMA ordem de tgt_pts
        dz         -> (dz0, dz1) deslocamento vertical de cada extremidade
        pivot      -> indice (0 ou 1) da extremidade travada do alvo
        ref_index  -> indice da extremidade da referencia usada como cota
        slope      -> inclinacao (magnitude) aplicada
        moved      -> False se nada muda (ja esta na cota e inclinacao)

    Levanta ValueError se referencia ou alvo forem verticais / degenerados.
    """
    if is_vertical(ref_pts[0], ref_pts[1]):
        raise ValueError("Tubo de referencia e vertical - nao tem cota unica")
    if is_vertical(tgt_pts[0], tgt_pts[1]):
        raise ValueError("Tubo alvo e vertical - nao ha cota a igualar")

    tgt_len = horizontal_length(tgt_pts[0], tgt_pts[1])
    if tgt_len < 1e-6:
        raise ValueError("Tubo alvo sem comprimento horizontal")

    i_ref, pivot = closest_endpoints(ref_pts, tgt_pts)
    other = 1 - pivot

    z_pivot = ref_pts[i_ref][2]
    slope = slope_magnitude(ref_pts[0], ref_pts[1])

    # Sentido: preserva o do alvo se ele ja e inclinado; senao desce se
    # afastando da referencia (o pivo e o ponto alto).
    tgt_slope = signed_slope(tgt_pts[pivot], tgt_pts[other])
    if abs(tgt_slope) > SLOPE_ZERO_TOL:
        direction = 1.0 if tgt_slope > 0 else -1.0
    else:
        direction = -1.0

    z_other = z_pivot + direction * slope * tgt_len

    new_z = [0.0, 0.0]
    new_z[pivot] = z_pivot
    new_z[other] = z_other

    dz = (new_z[0] - tgt_pts[0][2], new_z[1] - tgt_pts[1][2])
    moved = abs(dz[0]) > MOVE_TOL or abs(dz[1]) > MOVE_TOL

    return {
        'new_z': (new_z[0], new_z[1]),
        'dz': dz,
        'pivot': pivot,
        'ref_index': i_ref,
        'slope': slope,
        'moved': moved,
    }
