# -*- coding: utf-8 -*-
"""
Utilitarios de prumada - alinhamento de tubos verticais em eixo unico.

Extraido do Nivelar Pro v4.0. Usado por:
- Nivelar Pro (SnapMEP > Tools)
- Conectar Movendo / Conectar Puxando (SnapMEP > Conect)

Conceitos:
- Cadeia (prumada): tubos quase verticais conectados em sequencia
  atraves de fittings (couplings, tes)
- Eixo unico: toda a cadeia e aprumada no MESMO XY de referencia
- Ancora: extremidade conectada que define o XY (base tem prioridade;
  se so o topo esta conectado, o topo e a ancora)

IMPORTANTE: funcoes que modificam o modelo exigem Transaction ativa.
"""

import math

from Autodesk.Revit.DB import (
    BuiltInCategory, LocationCurve, Line, XYZ, ElementId, ConnectorType
)

from Snippets._mep_connector_utils import connect_elements

ALIGN_TOL = 0.0001  # ft (~0.03 mm) - tolerancia para considerar no eixo.
                    # Nao relaxar: residuo maior passa como "aprumado" mas o
                    # Revit exibe Inclinacao gigante (ex: 3379"/12") no tubo.


def _id_val(element_id):
    return element_id.Value if hasattr(element_id, 'Value') else element_id.IntegerValue


def is_pipe(elem):
    return (elem is not None and elem.Category is not None
            and _id_val(elem.Category.Id) == int(BuiltInCategory.OST_PipeCurves))


def is_nearly_vertical(pipe):
    """Tubo quase vertical: angulo < 15 graus da vertical (dz > 3.7 * dxy).
    Exclui tubos a 45 graus ou qualquer inclinacao intencional.
    """
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return False
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    dz = abs(p1.Z - p0.Z)
    dxy = math.sqrt((p1.X - p0.X) ** 2 + (p1.Y - p0.Y) ** 2)
    if dxy < 0.00001:   # ja perfeitamente vertical
        return dz > 0.001
    return dz > 3.7 * dxy


def is_plumb(pipe):
    """Tubo perfeitamente vertical (dentro da tolerancia)."""
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return True
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    dxy = math.sqrt((p1.X - p0.X) ** 2 + (p1.Y - p0.Y) ** 2)
    return dxy < ALIGN_TOL


def get_endpoint_connector(pipe, point, tolerance=None):
    """Retorna o conector mais proximo do ponto, ou None."""
    if tolerance is None:
        try:
            loc = pipe.Location
            if isinstance(loc, LocationCurve):
                tolerance = min(0.05, loc.Curve.Length / 3.0)
            else:
                tolerance = 0.01
        except Exception:
            tolerance = 0.01
    try:
        for conn in pipe.ConnectorManager.Connectors:
            # Conector logico (de sistema) nao tem Origin e lanca excecao.
            # Guardar POR CONECTOR - guardar o loop inteiro descartaria os
            # conectores validos que viessem depois do primeiro logico.
            try:
                if conn.Origin.DistanceTo(point) < tolerance:
                    return conn
            except Exception:
                continue
    except Exception:
        pass
    return None


def get_connected_ref(connector, own_id):
    """Retorna o conector fisico do elemento vizinho (ignora sistema logico)."""
    try:
        for ref in connector.AllRefs:
            if ref.Owner.Id != own_id and ref.ConnectorType == ConnectorType.End:
                return ref
    except Exception:
        pass
    return None


def get_connectors(elem):
    """Conectores de pipe (ConnectorManager) ou fitting (MEPModel)."""
    try:
        return list(elem.ConnectorManager.Connectors)
    except Exception:
        pass
    try:
        return list(elem.MEPModel.ConnectorManager.Connectors)
    except Exception:
        return []


def get_pipe_endpoints(pipe):
    """Retorna (p_bot, p_top) ordenados por Z, ou None."""
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return None
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    return (p0, p1) if p0.Z <= p1.Z else (p1, p0)


def build_chains(pipes):
    """Agrupa tubos em cadeias conectadas (prumadas), atravessando fittings."""
    by_id = {}
    for p in pipes:
        by_id[_id_val(p.Id)] = p

    parent = {k: k for k in by_id}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for pid, pipe in by_id.items():
        for conn in get_connectors(pipe):
            ref = get_connected_ref(conn, pipe.Id)
            if not ref:
                continue
            owner = ref.Owner
            oid = _id_val(owner.Id)
            if oid in by_id:
                union(pid, oid)
                continue
            # vizinho e fitting: verificar se conecta a outro tubo selecionado
            for fconn in get_connectors(owner):
                fref = get_connected_ref(fconn, owner.Id)
                if fref:
                    fid = _id_val(fref.Owner.Id)
                    if fid in by_id and fid != pid:
                        union(pid, fid)

    chains = {}
    for pid in by_id:
        chains.setdefault(find(pid), []).append(by_id[pid])
    return list(chains.values())


def discover_vertical_chain(start_pipe, max_pipes=100):
    """Descobre a prumada conectada a partir de UM tubo, navegando pela rede.

    Nao exige selecao: atravessa fittings e coleta tubos quase verticais
    fora de grupos. Ramais horizontais interrompem a navegacao (nao entram).
    """
    if not is_pipe(start_pipe) or not is_nearly_vertical(start_pipe):
        return []
    seen = set([_id_val(start_pipe.Id)])
    chain = [start_pipe]
    queue = [start_pipe]
    while queue and len(chain) < max_pipes:
        pipe = queue.pop(0)
        for conn in get_connectors(pipe):
            ref = get_connected_ref(conn, pipe.Id)
            if not ref:
                continue
            neighbors = [ref.Owner]
            if not is_pipe(ref.Owner):
                # atravessar o fitting para achar os proximos tubos
                for fconn in get_connectors(ref.Owner):
                    fref = get_connected_ref(fconn, ref.Owner.Id)
                    if fref:
                        neighbors.append(fref.Owner)
            for elem in neighbors:
                if not is_pipe(elem):
                    continue
                eid = _id_val(elem.Id)
                if eid in seen:
                    continue
                seen.add(eid)
                if (is_nearly_vertical(elem)
                        and elem.GroupId == ElementId.InvalidElementId):
                    chain.append(elem)
                    queue.append(elem)
    return chain


# Desvio angular maximo aceito entre eixos de conectores ao reconectar.
# Acima disso o fitting e rotacionado — ConnectTo com eixos tortos faz o
# Revit re-inclinar o tubo ao reconciliar no regenerate.
_AXIS_TOL = 1e-5  # rad


def _axes_antiparallel(conn_a, conn_b):
    """True se os eixos dos conectores ja estao opostos (prontos p/ conectar)."""
    try:
        dir_a = conn_a.CoordinateSystem.BasisZ
        dir_b = conn_b.CoordinateSystem.BasisZ
        return abs(dir_a.AngleTo(dir_b) - math.pi) < _AXIS_TOL
    except Exception:
        return True


def _reconnect_plain(pipe, point, other_ref):
    """Reconecta o lado ancorado (posicoes ja coincidem).

    Se o eixo do conector vizinho ficou torto (orientacao herdada do tubo
    inclinado), rotaciona o fitting no lugar antes de conectar — a translacao
    e ~zero porque as origens ja coincidem."""
    if not other_ref:
        return
    new_conn = get_endpoint_connector(pipe, point)
    if not new_conn:
        return
    if not _axes_antiparallel(new_conn, other_ref):
        try:
            connect_elements(other_ref.Owner, other_ref, new_conn,
                             tolerance=_AXIS_TOL, auto_disconnect=True)
            return
        except Exception:
            pass
    try:
        new_conn.ConnectTo(other_ref)
    except Exception:
        try:
            connect_elements(other_ref.Owner, other_ref, new_conn,
                             tolerance=_AXIS_TOL, auto_disconnect=True)
        except Exception:
            pass


def _move_and_connect(pipe, point, other_ref):
    """Move o fitting vizinho para o eixo do tubo e reconecta (arrasta ramais)."""
    if not other_ref:
        return
    new_conn = get_endpoint_connector(pipe, point)
    if not new_conn:
        return
    try:
        connect_elements(other_ref.Owner, other_ref, new_conn,
                         tolerance=_AXIS_TOL, auto_disconnect=True)
    except Exception:
        pass


def straighten_pipe(pipe, ref_x, ref_y, anchor_top):
    """Apruma o tubo no eixo (ref_x, ref_y).

    anchor_top=False: reconecta inferior no lugar, move fitting superior.
    anchor_top=True:  reconecta superior no lugar, move fitting inferior.

    Retorna (ok, motivo) - motivo preenchido apenas em falha.
    """
    pts = get_pipe_endpoints(pipe)
    if not pts:
        return False, "Sem LocationCurve (nao e tubo reto editavel)"
    p_bot, p_top = pts

    # Orientacao original da curva (endpoint 0 -> 1). Reconstruir sempre
    # bottom->top inverteria tubos cuja curva original e top->bottom, e o
    # Revit rejeita: "tubo modificado para direcao oposta / conexoes invalidas".
    _oc = pipe.Location.Curve
    _p0_is_bot = _oc.GetEndPoint(0).Z <= _oc.GetEndPoint(1).Z

    # Guard contra Line de comprimento zero
    if abs(p_top.Z - p_bot.Z) < 0.001:
        return False, "Altura vertical quase zero - nao ha como aprumar"

    on_axis = (abs(p_bot.X - ref_x) < ALIGN_TOL and abs(p_bot.Y - ref_y) < ALIGN_TOL
               and abs(p_top.X - ref_x) < ALIGN_TOL and abs(p_top.Y - ref_y) < ALIGN_TOL)
    if on_axis:
        return True, None

    conn_bot = get_endpoint_connector(pipe, p_bot)
    conn_top = get_endpoint_connector(pipe, p_top)

    bot_ref = get_connected_ref(conn_bot, pipe.Id) if (conn_bot and conn_bot.IsConnected) else None
    top_ref = get_connected_ref(conn_top, pipe.Id) if (conn_top and conn_top.IsConnected) else None

    # Desconectar antes de mudar a curva
    if bot_ref:
        try:
            conn_bot.DisconnectFrom(bot_ref)
        except Exception:
            pass
    if top_ref:
        try:
            conn_top.DisconnectFrom(top_ref)
        except Exception:
            pass

    # Corrigir curva do tubo para o eixo da prumada, PRESERVANDO a orientacao
    # original (endpoint 0 -> 1) para nao reverter o tubo.
    low_pt = XYZ(ref_x, ref_y, p_bot.Z)
    high_pt = XYZ(ref_x, ref_y, p_top.Z)
    try:
        if _p0_is_bot:
            pipe.Location.Curve = Line.CreateBound(low_pt, high_pt)
        else:
            pipe.Location.Curve = Line.CreateBound(high_pt, low_pt)
    except Exception as curve_err:
        # Reverter desconexoes para nao deixar o modelo inconsistente
        if bot_ref and conn_bot and not conn_bot.IsConnected:
            try:
                conn_bot.ConnectTo(bot_ref)
            except Exception:
                pass
        if top_ref and conn_top and not conn_top.IsConnected:
            try:
                conn_top.ConnectTo(top_ref)
            except Exception:
                pass
        return False, "Revit rejeitou a nova curva: {}".format(str(curve_err))

    new_bot = XYZ(ref_x, ref_y, p_bot.Z)
    new_top = XYZ(ref_x, ref_y, p_top.Z)

    if anchor_top:
        _reconnect_plain(pipe, new_top, top_ref)
        _move_and_connect(pipe, new_bot, bot_ref)
    else:
        _reconnect_plain(pipe, new_bot, bot_ref)
        _move_and_connect(pipe, new_top, top_ref)

    return True, None


def process_chain(pipes, failures):
    """Apruma uma cadeia inteira no mesmo eixo XY.
    Registra motivos de falha em failures (id -> motivo).
    """
    infos = []
    for p in pipes:
        pts = get_pipe_endpoints(p)
        if pts:
            infos.append((p, pts[0], pts[1]))
        else:
            failures[_id_val(p.Id)] = "Sem LocationCurve (nao e tubo reto editavel)"
    if not infos:
        return

    lowest = min(infos, key=lambda t: t[1].Z)
    highest = max(infos, key=lambda t: t[2].Z)

    conn_low = get_endpoint_connector(lowest[0], lowest[1])
    conn_high = get_endpoint_connector(highest[0], highest[2])

    if conn_low and conn_low.IsConnected:
        anchor_top = False
        ref = lowest[1]
    elif conn_high and conn_high.IsConnected:
        anchor_top = True
        ref = highest[2]
    else:
        anchor_top = False
        ref = lowest[1]

    # Processar a partir da ancora: de baixo para cima (ou o inverso)
    if anchor_top:
        ordered = sorted(infos, key=lambda t: t[2].Z, reverse=True)
    else:
        ordered = sorted(infos, key=lambda t: t[1].Z)

    for info in ordered:
        pid = _id_val(info[0].Id)
        try:
            ok, reason = straighten_pipe(info[0], ref.X, ref.Y, anchor_top)
            if ok:
                failures.pop(pid, None)
            else:
                failures[pid] = reason
        except Exception as e:
            failures[pid] = "Erro inesperado: {}".format(str(e))


def align_pipes(pipes, max_passes=3):
    """Fluxo completo: cadeias + passadas de verificacao ate o prumo.

    Requer Transaction ativa.
    Retorna (alinhados, nao_alinhados, failures {id: motivo}).
    """
    failures = {}
    pipes = [p for p in pipes if is_pipe(p)]
    if not pipes:
        return [], [], failures
    doc = pipes[0].Document

    for chain in build_chains(pipes):
        process_chain(chain, failures)

    for _ in range(max_passes):
        try:
            doc.Regenerate()
        except Exception:
            pass
        pending = [p for p in pipes if not is_plumb(p)]
        if not pending:
            break
        for chain in build_chains(pending):
            process_chain(chain, failures)

    try:
        doc.Regenerate()
    except Exception:
        pass

    aligned = [p for p in pipes if is_plumb(p)]
    not_aligned = [p for p in pipes if not is_plumb(p)]
    return aligned, not_aligned, failures
