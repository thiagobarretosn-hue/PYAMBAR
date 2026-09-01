# -*- coding: utf-8 -*-
"""
Nome do arquivo: _trecho_slope_utils.py
Localizacao: PYAMBAR(lab).extension/lib/Snippets/

Descricao:
Camada Revit do corretor de inclinacao por bitola (Fase B do spec
docs/superpowers/specs/2026-07-30-inclinacao-por-bitola-design.md).

O encadeamento do trecho vem de Snippets._pipe_scanner_engine.montar_trechos —
o MESMO codigo puro que o check do Pipe Doctor usa. Isso garante que o trecho
que o relatorio acusa e exatamente o trecho que esta ferramenta corrige.
O calculo das cotas vem de Snippets._slope_geometry.plan_trecho_z (puro).

Aqui fica so o que precisa da API: coletar a rede local, classificar as pontas
e reescrever a geometria.

Autor: Thiago Barreto Sobral Nunes
Data: 30.07.2026
Versao: 1.0
"""

import clr
clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import XYZ, Line, LocationCurve, ConnectorType, Domain

from Snippets._pipe_scanner_engine import (
    montar_trechos, config_interna, alvo_para_raio)
from Snippets._slope_geometry import (
    PONTA_ABSORVE, PONTA_LIVRE, PONTA_RIGIDA, decidir_ancora,
    horizontal_length, plan_trecho_z
)
from Snippets._prumada_utils import (
    is_pipe, is_nearly_vertical, get_connectors, get_endpoint_connector,
    get_connected_ref, _reconnect_plain, _move_and_connect
)

# Tolerancia para casar um ponto planejado com uma extremidade real (ft).
TOL_PONTA = 0.02

# Estados possiveis de uma ponta de trecho.
# PONTA_LIVRE / PONTA_ABSORVE / PONTA_RIGIDA vem de _slope_geometry (importadas
# acima) para que decidir_ancora() possa ser pura. Reexportadas daqui porque
# este e o modulo que os call-sites ja conheciam.


def _id_val(element_id):
    return element_id.Value if hasattr(element_id, 'Value') else element_id.IntegerValue


def _tupla(pt):
    return (pt.X, pt.Y, pt.Z)


# ------------------------------------------------------------ coleta da rede

def coletar_rede_local(pipe_inicial, max_elementos=300):
    """BFS pelos conectores a partir do tubo.

    Devolve (pipes, conectores, elem_por_id) no formato que o engine puro
    espera. Coleta so a vizinhanca conectada — nao varre o documento inteiro.
    """
    doc = pipe_inicial.Document
    vistos = set()
    fila = [pipe_inicial.Id]
    pipes = []
    conectores = []
    elem_por_id = {}
    cid = 0

    while fila and len(vistos) < max_elementos:
        eid = fila.pop()
        chave = _id_val(eid)
        if chave in vistos:
            continue
        vistos.add(chave)

        elem = doc.GetElement(eid)
        if elem is None:
            continue
        elem_por_id[chave] = elem

        if is_pipe(elem):
            loc = elem.Location
            if not isinstance(loc, LocationCurve):
                continue
            curva = loc.Curve
            raio = 0.05
            try:
                raio = elem.Diameter / 2.0
            except Exception:
                pass
            pipes.append({'id': chave, 'cat': 'pipe', 'type_id': 0,
                          'p0': _tupla(curva.GetEndPoint(0)),
                          'p1': _tupla(curva.GetEndPoint(1)),
                          'radius': raio})

        for conn in get_connectors(elem):
            try:
                # Conector logico (de sistema) nao tem Origin - so os fisicos
                # de extremidade interessam, mesmo filtro do Pipe Doctor.
                if conn.Domain != Domain.DomainPiping:
                    continue
                if conn.ConnectorType != ConnectorType.End:
                    continue

                outro_id = None
                if conn.IsConnected:
                    for ref in conn.AllRefs:
                        if ref.ConnectorType != ConnectorType.End:
                            continue
                        if _id_val(ref.Owner.Id) == chave:
                            continue
                        outro_id = _id_val(ref.Owner.Id)
                        fila.append(ref.Owner.Id)
                        break

                cid += 1
                conectores.append({'cid': cid, 'elem_id': chave,
                                   'origin': _tupla(conn.Origin),
                                   'direction': _tupla(conn.CoordinateSystem.BasisZ),
                                   'connected': outro_id is not None,
                                   'other_id': outro_id})
            except Exception:
                continue

    return pipes, conectores, elem_por_id


def encontrar_trecho(pipe, cfg_mm=None):
    """Trecho horizontal que contem o tubo. Devolve (trecho, elem_por_id).

    trecho e None se o tubo nao entra em trecho nenhum (vertical, sem
    comprimento horizontal).
    """
    cfg = config_interna(cfg_mm)
    pipes, conectores, elem_por_id = coletar_rede_local(pipe)
    alvo = _id_val(pipe.Id)
    for trecho in montar_trechos(pipes, conectores, cfg):
        if alvo in trecho['ids']:
            return trecho, elem_por_id
    return None, elem_por_id


# ------------------------------------------------------ classificar as pontas

def _classificar_ponta(pipe, ponto, elem_por_id):
    """Diz se a ponta do trecho pode ceder ao movimento."""
    conn = get_endpoint_connector(pipe, XYZ(*ponto))
    if conn is None or not conn.IsConnected:
        return PONTA_LIVRE
    ref = get_connected_ref(conn, pipe.Id)
    if ref is None:
        return PONTA_LIVRE

    vizinho = ref.Owner
    if is_pipe(vizinho) and is_nearly_vertical(vizinho):
        return PONTA_ABSORVE

    # Fitting: se algum vizinho dele e prumada, o desnivel e absorvido la.
    for c in get_connectors(vizinho):
        try:
            if c.ConnectorType != ConnectorType.End or not c.IsConnected:
                continue
            for r in c.AllRefs:
                if r.ConnectorType != ConnectorType.End:
                    continue
                dono = r.Owner
                if _id_val(dono.Id) in (_id_val(vizinho.Id), _id_val(pipe.Id)):
                    continue
                if is_pipe(dono) and is_nearly_vertical(dono):
                    return PONTA_ABSORVE
        except Exception:
            continue
    return PONTA_RIGIDA


def classificar_pontas(trecho, elem_por_id):
    """Estados das duas pontas do trecho: (estado_ini, estado_fim).

    Publica para que a UI monte o aviso do que sera arrastado ANTES de pedir
    confirmacao para inclinar um trecho travado.

    Devolve (None, None) se o trecho tem elemento nao resolvido.
    """
    pontos = trecho['pontos']
    pipe_ini = elem_por_id.get(trecho['ids'][0])
    pipe_fim = elem_por_id.get(trecho['ids'][-1])
    if pipe_ini is None or pipe_fim is None:
        return None, None
    return (_classificar_ponta(pipe_ini, pontos[0], elem_por_id),
            _classificar_ponta(pipe_fim, pontos[-1], elem_por_id))


def escolher_ancora(trecho, elem_por_id, permitir_travado=False):
    """Decide qual ponta do trecho fica parada.

    Devolve (indice_do_ponto_ancora, motivo) ou (None, motivo_da_recusa).

    A regra vive em Snippets._slope_geometry.decidir_ancora (pura, testada);
    aqui fica so a leitura do estado das pontas via API.

    permitir_travado=True aceita trecho preso nas duas pontas, ancorando na
    jusante e empurrando a montante. So passar True depois de mostrar ao
    usuario o que sera arrastado.
    """
    pontos = trecho['pontos']
    estado_ini, estado_fim = classificar_pontas(trecho, elem_por_id)
    if estado_ini is None:
        return None, "Trecho com elemento nao resolvido"

    return decidir_ancora(estado_ini, estado_fim, pontos[0][2], pontos[-1][2],
                          len(pontos), permitir_travado)


def alvo_para_bitola(trecho, cfg_mm=None):
    """Inclinacao alvo (razao) da bitola do trecho.

    Wrapper de `_pipe_scanner_engine.alvo_para_raio` — a regra mora la, para
    nao divergir de `_aranha_rules`, que so tem a bitola e nao um trecho.
    """
    return alvo_para_raio(trecho['radius'], cfg_mm)


def inclinacao_atual(trecho):
    """Inclinacao medida do trecho (razao), ponta a ponta pelo desenvolvido."""
    pontos = trecho['pontos']
    desenvolvido = 0.0
    for i in range(len(pontos) - 1):
        desenvolvido += horizontal_length(pontos[i], pontos[i + 1])
    if desenvolvido < 1e-9:
        return 0.0
    return abs(pontos[-1][2] - pontos[0][2]) / desenvolvido


# ------------------------------------------------------------ aplicar no Revit

def _reescrever_tubo(pipe, ponto_fixo, ponto_movel):
    """Grava a nova curva do tubo e arrasta o fitting da ponta movel.

    ponto_fixo / ponto_movel: (x, y, z) ja com as cotas novas. X e Y nunca
    mudam — so a cota. Preserva a orientacao original da curva (endpoint 0 -> 1)
    para o Revit nao acusar "tubo modificado para direcao oposta".
    """
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return False, "Sem LocationCurve"

    curva = loc.Curve
    p0_atual = curva.GetEndPoint(0)
    p1_atual = curva.GetEndPoint(1)

    novo_fixo = XYZ(ponto_fixo[0], ponto_fixo[1], ponto_fixo[2])
    novo_movel = XYZ(ponto_movel[0], ponto_movel[1], ponto_movel[2])

    if novo_fixo.DistanceTo(novo_movel) < 0.001:
        return False, "Tubo degenerado apos o ajuste"

    # Qual endpoint atual corresponde ao lado fixo (compara so em planta)
    d0 = horizontal_length(_tupla(p0_atual), ponto_fixo)
    d1 = horizontal_length(_tupla(p1_atual), ponto_fixo)
    p0_e_o_fixo = d0 <= d1

    conn_fixo = get_endpoint_connector(pipe, p0_atual if p0_e_o_fixo else p1_atual)
    conn_movel = get_endpoint_connector(pipe, p1_atual if p0_e_o_fixo else p0_atual)
    ref_fixo = get_connected_ref(conn_fixo, pipe.Id) if (conn_fixo and conn_fixo.IsConnected) else None
    ref_movel = get_connected_ref(conn_movel, pipe.Id) if (conn_movel and conn_movel.IsConnected) else None

    for conn, ref in ((conn_fixo, ref_fixo), (conn_movel, ref_movel)):
        if ref:
            try:
                conn.DisconnectFrom(ref)
            except Exception:
                pass

    try:
        if p0_e_o_fixo:
            loc.Curve = Line.CreateBound(novo_fixo, novo_movel)
        else:
            loc.Curve = Line.CreateBound(novo_movel, novo_fixo)
    except Exception as erro:
        for conn, ref in ((conn_fixo, ref_fixo), (conn_movel, ref_movel)):
            if ref and conn and not conn.IsConnected:
                try:
                    conn.ConnectTo(ref)
                except Exception:
                    pass
        return False, "Revit rejeitou a nova curva: {}".format(str(erro))

    _reconnect_plain(pipe, novo_fixo, ref_fixo)
    _move_and_connect(pipe, novo_movel, ref_movel)
    return True, None


def aplicar_inclinacao(trecho, ancora_idx, alvo, elem_por_id):
    """Reescreve as cotas do trecho inteiro. Deve rodar dentro de Transaction.

    Devolve (ajustados, falhas) — falhas e uma lista de (id, motivo).
    """
    pontos = trecho['pontos']
    novos_z = plan_trecho_z(pontos, ancora_idx, alvo)

    # pontos vem em pares por tubo: [entrada_0, saida_0, entrada_1, saida_1, ...]
    ordem = range(len(trecho['ids']))
    if ancora_idx != 0:
        ordem = list(reversed(list(ordem)))

    ajustados = 0
    falhas = []
    for k in ordem:
        pipe = elem_por_id.get(trecho['ids'][k])
        if pipe is None:
            falhas.append((trecho['ids'][k], "Elemento nao encontrado"))
            continue

        i_ent, i_sai = 2 * k, 2 * k + 1
        p_ent = (pontos[i_ent][0], pontos[i_ent][1], novos_z[i_ent])
        p_sai = (pontos[i_sai][0], pontos[i_sai][1], novos_z[i_sai])

        # Caminhando a partir da ancora, o lado ja resolvido e o mais proximo dela.
        if ancora_idx == 0:
            fixo, movel = p_ent, p_sai
        else:
            fixo, movel = p_sai, p_ent

        ok, motivo = _reescrever_tubo(pipe, fixo, movel)
        if ok:
            ajustados += 1
        else:
            falhas.append((trecho['ids'][k], motivo))

    return ajustados, falhas
