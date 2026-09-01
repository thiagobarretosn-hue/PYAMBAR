# -*- coding: utf-8 -*-
"""
_mep_branch_takeoff.py — derivacao de um ramal paralelo para um tronco.

Dois tubos PARALELOS lado a lado, mas o alvo e um tronco CONTINUO (sem ponta
livre onde o ramal chega). Nao e o desvio do _mep_offset_jog, que liga duas
pontas frente a frente: aqui sai um joelho da ponta solta do ramal, um trecho
atravessa o offset e entra no tronco com Wye (45) ou Te (90), dividindo-o.

    ramal (curto)          tronco (longo, continuo)
        |                        |
        |                        |
        +----- joelho 45 ----.   |
                              \\  |
                               >-<  Wye no tronco
                                  |

Geometria: com angulo A e offset L, o trecho sobe ``L / tan(A)`` ao longo do
eixo — 45 graus sobe L, 90 graus nao sobe nada (trecho perpendicular).

REQUER Transaction ativa. A escolha do angulo vem de fora (o snippet nao abre
dialogo), igual ao desvio.
"""

import math

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    BuiltInParameter, ElementId, Line, LocationCurve, SubTransaction, XYZ
)
from Autodesk.Revit.DB.Plumbing import Pipe, PlumbingUtils

from pyrevit import revit
from pyrevit.compat import get_elementid_value_func as _get_func

from Snippets._mep_angled_junction import create_angled_junction
from Snippets._mep_common import advance_for, conn_at as _conn_at
from Snippets._mep_common import system_type_id as _tipo_de_sistema

get_id_val = _get_func()

PARALLEL_DOT = 0.999     # ramal e tronco tem de ser paralelos
MIN_OFFSET = 1.0 / 12.0  # ft (25 mm) — abaixo disso e emenda, nao derivacao
MAX_OFFSET = 4.0         # ft (~1.2 m) — acima disso sao redes distintas.
                         # NAO e o mesmo limite do _mep_offset_jog (2 ft):
                         # la e o quanto um desvio de dois joelhos vence;
                         # aqui e o alcance de uma derivacao para o tronco.
END_MARGIN = 0.25        # ft — folga minima nas pontas do tronco
# Um tronco tem de ser SUBSTANCIALMENTE maior que o ramal. Aceitar empate
# fazia dois ramais irmaos — mesmo comprimento, os dois apontando para a
# mesma prumada — virarem par de derivacao: um deles era eleito "tronco" e
# ganhava um desvio em U ate o outro, em vez de cada um fazer seu te.
FATOR_TRONCO = 2.0
MIN_STUB = 0.25          # ft — sobra minima de tubo
CONNECT_TOL = 0.02       # ft
EXTEND_MAX = 4.0         # ft — quanto o tronco pode esticar para alcancar
FOLGA_ENTRADA = 0.25     # ft — piso do trecho reto antes do fitting do tronco
# 3x o diametro, nao 2x: MEDIDO no Wye deste projeto, o conector do branch
# fica a 0.532 ft (162 mm) do centro da peca. Com folga de 2 diametros o
# trecho nascia com 152 mm — menor que o alcance do proprio fitting — e o
# conector caia ATRAS da ponta do tubo, com a montagem falhando em "so 2 de 3
# ligacoes fecharam". Para 3" a folga passa a 229 mm, que acomoda a peca.
FOLGA_POR_DIAMETRO = 3.0 # a folga real e o maior entre o piso acima e este
                         # fator vezes o diametro: 76 mm fixos apertavam um
                         # tubo de 4" e sobravam num de 1".

# Combinacoes de obra. A mudanca angular TOTAL e ditada pelo fitting do tronco
# (Te = 90, Wye = 45); o que varia e fazer essa mudanca com um joelho ou com
# dois menores — dois joelhos dao curva mais suave.
#   (rotulo, angulo_de_cada_joelho, n_joelhos, angulo_de_entrada_no_tronco)
ESTRATEGIAS = {
    'te': [
        ("1 joelho de 90 + Te", 90.0, 1, 90.0),
        ("2 joelhos de 45 + Te", 45.0, 2, 90.0),
    ],
    'wye': [
        ("1 joelho de 45 + Wye", 45.0, 1, 45.0),
        ("2 joelhos de 22.5 + Wye", 22.5, 2, 45.0),
    ],
}


# ---------------------------------------------------------------------------
# Deteccao
# ---------------------------------------------------------------------------

def _eixo_e_pontas(pipe):
    """(p0, p1, eixo, comprimento) do tubo, ou None."""
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return None
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    vec = p1 - p0
    comp = vec.GetLength()
    if comp < 1e-9:
        return None
    return p0, p1, vec.Normalize(), comp


def pontas_livres(pipe):
    """[(conector, livre, fixo)] de todas as pontas soltas, da mais alta."""
    info = _eixo_e_pontas(pipe)
    if info is None:
        return []
    p0, p1, _eixo, _comp = info
    saida = []
    try:
        conns = list(pipe.ConnectorManager.Connectors)
    except Exception:
        return []
    for conn in conns:
        if conn.IsConnected:
            continue
        if conn.Origin.DistanceTo(p0) < 0.01:
            saida.append((conn, p0, p1))
        elif conn.Origin.DistanceTo(p1) < 0.01:
            saida.append((conn, p1, p0))
    # Desempate ESTAVEL: num tubo horizontal as duas pontas tem o mesmo Z e a
    # ordenacao so por altura deixava a escolha por conta da ordem do
    # ConnectorManager, que muda entre execucoes. O mesmo cenario dava
    # "candidato valido" numa rodada e "e caso de desvio" na seguinte.
    saida.sort(key=lambda x: (-x[1].Z, x[1].X, x[1].Y))
    return saida


def _ponta_livre_mais_alta(pipe, preferir_baixa=False):
    """(conector, ponto_livre, ponto_fixo) da ponta solta escolhida.

    Por padrao a mais alta; ``preferir_baixa`` inverte. So faz diferenca
    quando o tubo tem as DUAS pontas livres — com uma so, ela e usada e nao
    ha o que perguntar.
    """
    todas = pontas_livres(pipe)
    if not todas:
        return None
    return todas[-1] if preferir_baixa else todas[0]


def _tem_ponta_de_frente(tronco, livre_ramal, saida_ramal, tol=4.0):
    """True se o tronco tem ponta LIVRE olhando para a ponta do ramal.

    ``saida_ramal`` e a direcao de SAIDA da ponta livre (do fixo para o livre),
    nao o eixo do tubo: o eixo aponta de p0 para p1, e qual deles e a ponta
    livre e arbitrario — usar o eixo fazia esta checagem acertar ou errar
    conforme a ordem interna dos endpoints.

    Esse e o caso do DESVIO (dois joelhos entre duas pontas), nao o da
    derivacao. Sem esta checagem o mesmo par aparecia nas duas janelas e a
    derivacao tentava montar depois que o desvio ja tinha resolvido.
    """
    try:
        conns = list(tronco.ConnectorManager.Connectors)
    except Exception:
        return False
    for conn in conns:
        if conn.IsConnected:
            continue
        if conn.Origin.DistanceTo(livre_ramal) > tol:
            continue
        try:
            if conn.CoordinateSystem.BasisZ.DotProduct(saida_ramal) < -0.9:
                return True      # aponta de volta para o ramal: e desvio
        except Exception:
            pass
    return False


def _rejeita(lista, ramal, tronco, motivo):
    """Anota por que um candidato foi barrado, se alguem estiver ouvindo."""
    if lista is None:
        return
    try:
        lista.append((get_id_val(ramal.Id), get_id_val(tronco.Id), motivo))
    except Exception:
        pass


def find_takeoff_pairs(pipes, preferir_baixa=False, rejeitados=None):
    """Pares (ramal curto com ponta solta, tronco continuo paralelo).

    ``rejeitados``: lista opcional que recebe (ramal, tronco, motivo) de cada
    candidato barrado. E o que permite ao diagnostico contar a MESMA historia
    que a execucao — enquanto `explicar` reimplementava estes criterios por
    conta propria, as duas divergiram duas vezes e o relatorio descrevia um
    par que o motor nunca chegou a tentar.

    O ramal e sempre o mais CURTO e entra pela ponta solta mais alta; o tronco
    e o mais longo e sera dividido para receber o Wye/Te. Pares em que o
    tronco tem ponta livre de frente para o ramal sao do DESVIO, nao daqui.
    """
    validos = [p for p in pipes if p is not None and p.IsValidObject]
    pares = []
    usados = set()

    # do mais curto para o mais longo: o curto e quem deriva
    ordenados = []
    for pipe in validos:
        info = _eixo_e_pontas(pipe)
        if info:
            ordenados.append((info[3], pipe, info))
    ordenados.sort(key=lambda x: x[0])

    for comp_r, ramal, info_r in ordenados:
        if get_id_val(ramal.Id) in usados:
            continue
        # Percorrer TODAS as pontas livres, na ordem de preferencia: eleger
        # uma antes de saber qual e o tronco pode fixar justamente a ponta que
        # aponta para o lado oposto, e ai nenhum par valido aparece.
        pontas = pontas_livres(ramal)
        if preferir_baixa:
            pontas = list(reversed(pontas))
        if not pontas:
            continue

        melhor = None
        candidatos = []
        for conn_r, livre_r, fixo_r in pontas:
            _p0r, _p1r, eixo_r, _cr = info_r
            saida_r = livre_r - fixo_r
            if saida_r.GetLength() < 1e-9:
                continue
            saida_r = saida_r.Normalize()
            for comp_t, tronco, info_t in ordenados:
                if tronco.Id == ramal.Id:
                    continue
                if comp_t < comp_r * FATOR_TRONCO:
                    # nao basta ser maior: tem de ser tronco de verdade
                    _rejeita(rejeitados, ramal, tronco,
                             "tubo de {:.1f} ft nao e tronco para um ramal de "
                             "{:.1f} ft (minimo {:.0f}x)".format(
                                 comp_t, comp_r, FATOR_TRONCO))
                    continue
                if get_id_val(tronco.Id) in usados:
                    continue
                p0t, p1t, eixo_t, comp_tt = info_t
                if abs(eixo_t.DotProduct(eixo_r)) < PARALLEL_DOT:
                    _rejeita(rejeitados, ramal, tronco, "nao sao paralelos")
                    continue
                try:
                    if abs(ramal.Diameter - tronco.Diameter) > 1e-6:
                        pass       # diametros diferentes sao normais aqui (reducao)
                except Exception:
                    continue
                # offset = distancia perpendicular entre os eixos
                v = livre_r - p0t
                ao_longo = v.DotProduct(eixo_t)
                perp = v - eixo_t.Multiply(ao_longo)
                offset = perp.GetLength()
                if offset < MIN_OFFSET:
                    _rejeita(rejeitados, ramal, tronco,
                             "offset {:.1f} mm — pequeno demais (minimo {:.0f} "
                             "mm), e emenda".format(offset * 304.8,
                                                    MIN_OFFSET * 304.8))
                    continue
                if offset > MAX_OFFSET:
                    _rejeita(rejeitados, ramal, tronco,
                             "offset {:.1f} mm — grande demais (maximo {:.0f} "
                             "mm)".format(offset * 304.8, MAX_OFFSET * 304.8))
                    continue
                if _tem_ponta_de_frente(tronco, livre_r, saida_r):
                    _rejeita(rejeitados, ramal, tronco,
                             "o tronco tem ponta livre DE FRENTE — e caso de "
                             "desvio (2 joelhos), nao de derivacao")
                    continue
                cand = dict(ramal=ramal, tronco=tronco, conn_ramal=conn_r,
                            livre=livre_r, fixo=fixo_r, eixo=saida_r,
                            comp_ramal=comp_r, comp_tronco=comp_tt,
                            p0t=p0t, p1t=p1t, eixo_tronco=eixo_t,
                            offset=offset,
                            lado=perp.Normalize() if offset > 1e-9 else None,
                            t_livre=ao_longo,
                            # quao longe fica o ponto de entrada no tronco: o
                            # offset sozinho elege um tronco quase alinhado ainda
                            # que a entrada caia dezenas de pes adiante
                            dist_entrada=abs(ao_longo))
                candidatos.append(cand)
                if melhor is None or offset < melhor['offset']:
                    melhor = cand
            if melhor is not None:
                break     # esta ponta ja rendeu par; a outra nao interessa
        if melhor and melhor['lado'] is not None:
            # Guardar os outros troncos possiveis: quando ha mais de um, so o
            # usuario sabe em qual deles quer derivar — a ferramenta escolhe
            # por menor offset, que nem sempre e o tubo pretendido.
            viaveis = [c for c in candidatos if c['lado'] is not None]
            viaveis.sort(key=lambda c: (c['offset'], c['dist_entrada']))
            melhor['alternativas'] = viaveis
            pares.append(melhor)
            usados.add(get_id_val(ramal.Id))
            usados.add(get_id_val(melhor['tronco'].Id))
    return pares


# ---------------------------------------------------------------------------
# Geometria
# ---------------------------------------------------------------------------

def folga_para(pipe):
    """Trecho reto antes do fitting: proporcional ao diametro, com piso."""
    try:
        return max(FOLGA_ENTRADA, FOLGA_POR_DIAMETRO * pipe.Diameter)
    except Exception:
        return FOLGA_ENTRADA


def avanco_estrategia(offset, ang_joelho, n_joelhos, folga=FOLGA_ENTRADA):
    """Quanto a derivacao sobe no eixo do tronco, nessa estrategia.

    Um joelho: o trecho vai direto no angulo de entrada.
    Dois joelhos: trecho 1 no angulo do joelho, trecho 2 (comprimento ``folga``)
    no dobro dele — que e o angulo de entrada no fitting.
    """
    if n_joelhos <= 1:
        if ang_joelho >= 89.99:
            return 0.0
        return offset / math.tan(math.radians(ang_joelho))

    th = math.radians(ang_joelho)
    th2 = 2.0 * th
    lat2 = folga * math.sin(th2)
    lat1 = offset - lat2
    if lat1 < 0 or math.sin(th) < 1e-9:
        return None
    c1 = lat1 / math.sin(th)
    return c1 * math.cos(th) + folga * math.cos(th2)


def entry_param(par, angle_deg):
    """Parametro (ao longo do tronco, a partir de p0t) do ponto de entrada.

    O ramal sai da ponta solta e sobe no sentido de saida dela; a entrada no
    tronco fica ``avanco`` a frente da projecao da ponta livre.
    """
    if isinstance(angle_deg, tuple):
        _rot, ang_j, n_j, _ang_e = angle_deg[:4]
        avanco = avanco_estrategia(par['offset'], ang_j, n_j,
                                   folga_para(par['ramal']))
    else:
        avanco = advance_for(par['offset'], angle_deg)
    if avanco is None:
        return None
    # sentido de saida do ramal projetado no eixo do tronco
    sentido = 1.0 if par['eixo'].DotProduct(par['eixo_tronco']) > 0 else -1.0
    return par['t_livre'] + sentido * avanco


def feasibility(par, angle_deg):
    """(cabe, precisa_esticar, motivo) da derivacao nesse angulo.

    Alem da geometria, checa se o trecho entre o joelho e a juncao tem
    comprimento FISICO. Com offset muito pequeno o avanco vira alguns
    centimetros: cabe no papel, mas nao existe tubo de 6 cm entre um joelho e
    um wye de 3". Sem essa checagem a montagem falhava la na frente com
    "nem te nem wye serviram para este angulo" — culpando o angulo por um
    problema de espaco.
    """
    t = entry_param(par, angle_deg)
    if t is None:
        return False, 0.0, "o offset nao cabe nesta combinacao de joelhos"

    ang_joelho = n_joelhos = None
    if isinstance(angle_deg, (tuple, list)) and len(angle_deg) >= 3:
        ang_joelho, n_joelhos = angle_deg[1], angle_deg[2]
    # So com UM joelho da para calcular o trecho aqui; com dois a geometria e
    # outra.
    #
    # O comprimento do trecho e offset/sin(A), NAO o avanco no eixo
    # (offset/tan(A)). Com joelho de 90 o avanco e sempre zero — o trecho nao
    # corre no eixo, ele atravessa o offset — e medir o avanco condenava a
    # estrategia "1 joelho de 90" em todos os casos, por mais folgado que o
    # offset fosse.
    if ang_joelho and n_joelhos == 1:
        seno = math.sin(math.radians(ang_joelho))
        if abs(seno) < 1e-9:
            return False, 0.0, "angulo de joelho degenerado"
        comprimento = par['offset'] / seno
        minimo = folga_para(par['ramal'])
        if comprimento < minimo:
            return False, 0.0, (
                "o trecho entre o joelho e a juncao ficaria com {:.0f} mm — "
                "minimo {:.0f} mm para as pecas caberem".format(
                    comprimento * 304.8, minimo * 304.8))

    comp = par['comp_tronco']
    if t < END_MARGIN:
        falta = END_MARGIN - t
        if falta > EXTEND_MAX:
            return False, 0.0, ("entrada cairia {:.2f} ft antes do tronco"
                                .format(falta))
        return True, falta, ""
    if t > comp - END_MARGIN:
        falta = t - (comp - END_MARGIN)
        if falta > EXTEND_MAX:
            return False, 0.0, ("entrada cairia {:.2f} ft depois do tronco"
                                .format(falta))
        return True, falta, ""
    return True, 0.0, ""


# ---------------------------------------------------------------------------
# Execucao
# ---------------------------------------------------------------------------

def _set_free_end(pipe, ponta_livre, novo_ponto):
    """Leva a ponta livre ate novo_ponto sem inverter o tubo."""
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return False
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    if ponta_livre.DistanceTo(p0) < 0.03:
        fixo, livre_e_p0 = p1, True
    elif ponta_livre.DistanceTo(p1) < 0.03:
        fixo, livre_e_p0 = p0, False
    else:
        return False
    if fixo.DistanceTo(novo_ponto) < MIN_STUB:
        return False
    orig = ponta_livre - fixo
    novo = novo_ponto - fixo
    if orig.GetLength() < 1e-9 or novo.GetLength() < 1e-9:
        return False
    if novo.Normalize().DotProduct(orig.Normalize()) < 0.9:
        return False          # o novo ponto ficaria atras: inverteria o tubo
    try:
        if livre_e_p0:
            loc.Curve = Line.CreateBound(novo_ponto, fixo)
        else:
            loc.Curve = Line.CreateBound(fixo, novo_ponto)
    except Exception:
        return False
    return True


def create_takeoff(par, angle_deg):
    """Monta a derivacao: joelho no ramal, trecho, Wye/Te no tronco.

    Sequencia:
      1. estica o tronco se a entrada cair fora dele (ate EXTEND_MAX)
      2. calcula o vertice do joelho e o ponto de entrada no tronco
      3. encurta/estica o ramal ate o vertice
      4. cria o trecho do vertice ate a entrada
      5. joelho entre ramal e trecho (o Revit deduz o angulo da geometria)
      6. Wye/Te no tronco: divide e liga as tres pontas

    Tudo em SubTransaction: falhando qualquer passo, nada sobra.
    """
    doc = revit.doc
    ok, esticar, _motivo = feasibility(par, angle_deg)
    if not ok:
        return None, _motivo or "nao cabe"
    passo = "inicio"

    sub = SubTransaction(doc)
    sub.Start()
    try:
        tronco = par['tronco']
        info_t = _eixo_e_pontas(tronco)
        if info_t is None:
            raise Exception("tronco sem curva")
        p0t, p1t, eixo_t, comp_t = info_t

        passo = "calcular entrada"
        t_entrada = entry_param(par, angle_deg)

        # 1. esticar o tronco se a entrada cair fora
        passo = "esticar o tronco"
        if esticar > 0.0:
            if t_entrada < END_MARGIN:
                alvo = p0t + eixo_t.Multiply(t_entrada - END_MARGIN)
                if not _set_free_end(tronco, p0t, alvo):
                    raise Exception("nao consegui esticar o inicio do tronco")
            else:
                alvo = p0t + eixo_t.Multiply(t_entrada + END_MARGIN)
                if not _set_free_end(tronco, p1t, alvo):
                    raise Exception("nao consegui esticar o fim do tronco")
            doc.Regenerate()
            info_t = _eixo_e_pontas(tronco)
            p0t, p1t, eixo_t, comp_t = info_t
            t_entrada = entry_param(par, angle_deg)

        entrada = p0t + eixo_t.Multiply(t_entrada)

        # 2. vertices: com 1 joelho o trecho vai direto; com 2, ha um
        # trecho intermediario no angulo do joelho e o final no dobro dele.
        if isinstance(angle_deg, tuple):
            _rot, ang_j, n_j, _ang_e = angle_deg[:4]
        else:
            ang_j, n_j = angle_deg, 1

        sentido = 1.0 if par['eixo'].DotProduct(eixo_t) > 0 else -1.0
        subir = eixo_t.Multiply(sentido)          # sentido de subida do ramal
        para_tronco = par['lado'].Negate()        # do ramal para o tronco

        vertices = []                             # pontos onde nasce joelho
        if n_j <= 1:
            avanco = avanco_estrategia(par['offset'], ang_j, 1,
                                       folga_para(par['ramal']))
            v1 = entrada - subir.Multiply(avanco)                  - para_tronco.Multiply(par['offset'])
            vertices = [v1]
            pontos = [v1, entrada]
        else:
            th = math.radians(ang_j)
            th2 = 2.0 * th
            folga = folga_para(par['ramal'])
            d2 = subir.Multiply(math.cos(th2)) +                  para_tronco.Multiply(math.sin(th2))
            v2 = entrada - d2.Multiply(folga)
            lat1 = par['offset'] - folga * math.sin(th2)
            if lat1 < 0 or math.sin(th) < 1e-9:
                raise Exception("offset pequeno demais para dois joelhos")
            c1 = lat1 / math.sin(th)
            d1 = subir.Multiply(math.cos(th)) +                  para_tronco.Multiply(math.sin(th))
            v1 = v2 - d1.Multiply(c1)
            vertices = [v1, v2]
            pontos = [v1, v2, entrada]

        passo = "levar o ramal ate o primeiro joelho"
        if not _set_free_end(par['ramal'], par['livre'], vertices[0]):
            raise Exception("nao consegui levar o ramal ate o joelho")
        doc.Regenerate()

        passo = "criar os trechos"
        trechos = []
        for k in range(len(pontos) - 1):
            t_novo = Pipe.Create(doc, _sistema(par['ramal']),
                                 par['ramal'].PipeType.Id,
                                 par['ramal'].ReferenceLevel.Id,
                                 pontos[k], pontos[k + 1])
            try:
                t_novo.get_Parameter(
                    BuiltInParameter.RBS_PIPE_DIAMETER_PARAM).Set(
                        par['ramal'].Diameter)
            except Exception:
                pass
            trechos.append(t_novo)
        doc.Regenerate()

        passo = "criar os joelhos"
        anterior = par['ramal']
        for k, vert in enumerate(vertices):
            c_ant = _conn_at(anterior, vert)
            c_prox = _conn_at(trechos[k], vert)
            if not (c_ant and c_prox):
                raise Exception("conectores do joelho {} nao achados".format(k + 1))
            doc.Create.NewElbowFitting(c_ant, c_prox)
            doc.Regenerate()
            anterior = trechos[k]

        trecho = trechos[-1]

        passo = "dividir o tronco e criar Wye/Te"
        # 6. juncao no tronco
        #
        # BreakCurve exige um ponto SOBRE a curva: fora dela devolve "The given
        # point is not on the pipe curve" e derruba a montagem inteira. O ponto
        # de entrada vem de conta geometrica e pode cair alguns milimetros fora
        # (ou passar da ponta, quando o tronco encolheu num passo anterior),
        # entao projeta-se no eixo e confere-se que sobrou tubo dos dois lados.
        try:
            curva = tronco.Location.Curve
            p_ini = curva.GetEndPoint(0)
            p_fim = curva.GetEndPoint(1)
            eixo_tr = (p_fim - p_ini)
            comp_tr = eixo_tr.GetLength()
            if comp_tr < 1e-9:
                raise Exception("tronco degenerado")
            eixo_tr = eixo_tr.Normalize()
            t_ent = (entrada - p_ini).DotProduct(eixo_tr)
            if t_ent < END_MARGIN or t_ent > comp_tr - END_MARGIN:
                raise Exception(
                    "a entrada cairia a {:.2f} ft do inicio de um tronco de "
                    "{:.2f} ft — fora da margem de {:.2f} ft para dividir"
                    .format(t_ent, comp_tr, END_MARGIN))
            entrada = p_ini + eixo_tr.Multiply(t_ent)
        except Exception:
            raise

        novo_id = PlumbingUtils.BreakCurve(doc, tronco.Id, entrada)
        doc.Regenerate()
        tronco2 = doc.GetElement(novo_id)
        if tronco2 is None:
            raise Exception("BreakCurve falhou no tronco")

        c1 = _conn_at(tronco, entrada)
        c2 = _conn_at(tronco2, entrada)
        c3 = _conn_at(trecho, entrada)
        if not (c1 and c2 and c3):
            raise Exception("conectores da juncao nao encontrados")

        try:
            doc.Create.NewTeeFitting(c1, c2, c3)
        except Exception as erro_te:
            # angulo fora do que o Te aceita (45): montar a juncao em angulo
            from Snippets._mep_angled_junction import (
                limpar_motivos, MOTIVOS as MOTIVOS_JUNCAO)
            limpar_motivos()
            inst = create_angled_junction(tronco, tronco2, trecho, entrada,
                                          c3.CoordinateSystem.BasisZ)
            if inst is None:
                # Dizer O QUE barrou, e nao so "o angulo": a causa costuma ser
                # familia sem o angulo pedido, falta de espaco ou peca sem
                # parametro de tamanho — e o motivo generico mandava procurar
                # no lugar errado.
                detalhe = "; ".join(MOTIVOS_JUNCAO[-3:]) or str(erro_te)
                raise Exception("te recusou e a juncao em angulo nao saiu: "
                                "{}".format(detalhe))
        doc.Regenerate()

        sub.Commit()
        return trecho, ""
    except Exception as exc:
        sub.RollBack()
        detalhe = str(exc) or exc.__class__.__name__
        return None, "{}: {}".format(passo, detalhe)


def _sistema(pipe):
    """Tipo de sistema para os trechos novos. Ver _mep_common.system_type_id."""
    return _tipo_de_sistema(pipe, revit.doc)


def explicar(pipes):
    """Linhas dizendo, par a par, por que virou (ou nao) uma derivacao.

    Usa a MESMA busca da execucao e so descreve o que ela devolveu — pares
    aceitos com as estrategias que cabem, e cada candidato barrado com o
    criterio que o barrou. Reimplementar os criterios aqui foi fonte de dois
    enganos: o diagnostico dizia "candidato valido" para um par que o motor
    tinha descartado, e num deles deu vereditos opostos em rodadas seguidas.
    """
    validos = [p for p in pipes if p is not None and p.IsValidObject]
    if len(validos) < 2:
        return ["**Fase 0e:** menos de dois tubos com curva."]

    rejeitados = []
    try:
        pares = find_takeoff_pairs(validos, rejeitados=rejeitados)
    except Exception as erro:
        return ["**Fase 0e:** a busca falhou: {}".format(erro)]

    linhas = []
    for par in pares:
        rid = get_id_val(par['ramal'].Id)
        tid = get_id_val(par['tronco'].Id)
        alternativas = par.get('alternativas') or []
        linhas.append(
            "  - `{}` -> `{}`: candidato valido — offset {:.1f} mm, tronco de "
            "{:.2f} ft{}".format(
                rid, tid, par['offset'] * 304.8, par['comp_tronco'],
                "  ({} tronco(s) possivel(is))".format(len(alternativas))
                if len(alternativas) > 1 else ""))
        for rotulo, ang_j, n_j, ang_e in (ESTRATEGIAS['te'] + ESTRATEGIAS['wye']):
            cabe, _falta, motivo = feasibility(par, (rotulo, ang_j, n_j, ang_e))
            linhas.append("      {}: {}".format(
                rotulo, "cabe" if cabe else ("NAO — " + (motivo or "?"))))

    for rid, tid, motivo in rejeitados:
        linhas.append("  - `{}` -> `{}`: {}".format(rid, tid, motivo))

    if not linhas:
        linhas.append("  nenhum par avaliado")
    return linhas


def takeoff_pass(elements, angle_deg, in_scope=None):
    """Deriva todos os pares elegiveis. (elementos, n_derivacoes, pulados)."""
    if not angle_deg:
        return elements, 0, []

    from Snippets._mep_batch_connect import is_pipe
    pipes = [e for e in elements if e is not None and e.IsValidObject
             and is_pipe(e)]
    # 5o item da tupla, quando presente, pede a ponta de BAIXO do ramal
    preferir_baixa = bool(isinstance(angle_deg, tuple) and len(angle_deg) > 4
                          and angle_deg[4])
    resultado = list(elements)
    feitos = 0
    pulados = []

    for par in find_takeoff_pairs(pipes, preferir_baixa):
        if in_scope is not None and not in_scope(par['ramal'], par['tronco']):
            continue

        # O tronco eleito e o de menor offset, e um offset pequeno demais nao
        # comporta as pecas. Quando ele nao cabe, tentar os outros candidatos
        # antes de desistir — desistir do ramal inteiro porque o primeiro
        # tronco era apertado deixava de fora uma derivacao perfeitamente
        # possivel no tronco vizinho. Se foi o USUARIO que apontou o tronco,
        # a escolha dele e respeitada e nao ha troca silenciosa.
        tentativas = [par]
        if not par.get('escolha_do_usuario'):
            for cand in (par.get('alternativas') or []):
                if cand is par or cand.get('tronco') is par.get('tronco'):
                    continue
                variante = dict(par)
                variante.update(cand)
                tentativas.append(variante)

        ok = False
        motivo = ""
        for tentativa in tentativas:
            ok, _esticar, motivo = feasibility(tentativa, angle_deg)
            if ok:
                par = tentativa
                break
        if not ok:
            pulados.append((get_id_val(par['ramal'].Id), motivo))
            continue
        novo, motivo_falha = create_takeoff(par, angle_deg)
        if novo is None:
            pulados.append((get_id_val(par['ramal'].Id),
                            motivo_falha or "falhou ao montar a derivacao"))
            continue
        feitos += 1
        resultado.append(novo)

    resultado = [e for e in resultado if e is not None and e.IsValidObject]
    return resultado, feitos, pulados


def tem_ambiguidade(pipes):
    """True se algum ramal candidato tem as DUAS pontas livres.

    So nesse caso faz sentido perguntar "por cima ou por baixo": com uma
    ponta so, nao ha escolha a fazer.
    """
    for par in find_takeoff_pairs(pipes):
        if len(pontas_livres(par['ramal'])) >= 2:
            return True
    return False
